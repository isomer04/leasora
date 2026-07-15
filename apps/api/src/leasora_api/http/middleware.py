"""HTTP exception handling and request correlation middleware."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from leasora_api.core.config import get_settings
from leasora_api.core.exceptions import EXCEPTION_TO_STATUS_CODE, LeasoraError
from leasora_api.core.logging import (
    RequestTimer,
    internal_correlation_id_var,
    lease_id_var,
    pop_request_metadata,
    request_id_var,
    user_query_hash_var,
)

logger = logging.getLogger(__name__)

# Maximum allowed length for request IDs (prevents DoS via pathologically long ids)
MAX_REQUEST_ID_LENGTH = 200


async def leasora_error_handler(request: Request, error: Exception) -> JSONResponse:
    """Convert a domain exception into an HTTP error response.

    Registered via ``app.add_exception_handler`` (not ``app.middleware("http")``)
    so it runs inside Starlette's routing/exception layer, underneath
    ``CORSMiddleware``. A plain ASGI middleware that catches exceptions runs
    *outside* CORSMiddleware, which means error responses it returns would be
    missing CORS headers and get rejected by browsers.

    The exception's ``headers`` property (e.g. ``RateLimitError.retry_after``
    -> ``Retry-After``) is forwarded to the response so clients can back
    off correctly.
    """
    assert isinstance(error, LeasoraError)
    status_code = EXCEPTION_TO_STATUS_CODE.get(type(error), 500)
    request_id = request_id_var.get("")
    logger.warning(
        "Domain error in %s %s (request_id=%s): %s",
        request.method,
        request.url.path,
        request_id,
        error.message,
    )
    payload: dict[str, Any] = {
        "detail": error.message,
        "error_code": error.error_code,
    }
    if request_id:
        payload["request_id"] = request_id
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers=error.headers,
    )


async def unhandled_exception_handler(request: Request, error: Exception) -> JSONResponse:
    """Catch-all handler for exceptions that aren't a ``LeasoraError``.

    Includes the per-request identifier in the JSON error body so a user
    reporting "I got a 500" can quote it and an operator can correlate the
    failure to the structured log line emitted by ``logger.exception`` below.
    ``RequestIDMiddleware`` independently returns the same identifier in the
    ``X-Request-ID`` response header.
    """
    request_id = request_id_var.get("")
    logger.exception(
        "Unhandled exception in %s %s (request_id=%s)",
        request.method,
        request.url.path,
        request_id,
    )
    payload: dict[str, Any] = {
        "detail": "An unexpected error occurred. Please try again.",
        "error_code": "INTERNAL_SERVER_ERROR",
    }
    if request_id:
        payload["request_id"] = request_id
    return JSONResponse(status_code=500, content=payload)


# Pure ASGI middlewares (run in registration order, before CORS)

RequestResponseCall = Callable[[Request], Awaitable[None]]


class RequestIDMiddleware:
    """ASGI middleware that propagates an ``X-Request-ID`` per request."""

    HEADER = "x-request-id"

    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Read incoming id from headers (case-insensitive)
        request_id: str | None = None
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == self.HEADER.encode():
                candidate = raw_value.decode("latin-1", errors="replace").strip()
                if candidate and len(candidate) <= MAX_REQUEST_ID_LENGTH:
                    request_id = candidate
                break

        if request_id is None:
            request_id = uuid.uuid4().hex

        token = request_id_var.set(request_id)
        # Server-generated per-request key (UUID), always unique and never
        # adopted from the client. This is the only safe dict key for
        # request-scoped state like the access-log stash. Using a separate
        # server-generated ID prevents collision attacks where a client
        # reuses the same X-Request-ID across multiple concurrent requests.
        stash_key = uuid.uuid4().hex
        stash_key_token = internal_correlation_id_var.set(stash_key)
        timer = RequestTimer()
        status_holder: dict[str, int] = {"status": 500}
        path = scope.get("path", "")

        async def send_with_header(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                if get_settings().request_id_enabled:
                    headers.append(
                        (self.HEADER.encode(), request_id.encode("latin-1"))
                    )
                message["headers"] = headers
            await send(message)

        # Reset per-request observability contextvars. They may have
        # leaked from a previous asyncio task (or our own background
        # warmup); clearing them here guarantees the access-log line
        # reflects only the current request.
        lease_token = lease_id_var.set(None)
        query_hash_token = user_query_hash_var.set("")
        try:
            await self.app(scope, receive, send_with_header)
        finally:
            self._emit_access_log(
                scope=scope,
                request_id=request_id,
                stash_key=stash_key,
                method=scope.get("method", "GET"),
                path=path,
                status=status_holder["status"],
                timer=timer,
            )
            lease_id_var.reset(lease_token)
            user_query_hash_var.reset(query_hash_token)
            internal_correlation_id_var.reset(stash_key_token)
            request_id_var.reset(token)

    @staticmethod
    def _emit_access_log(
        *,
        scope: dict[str, Any],
        request_id: str,
        stash_key: str,
        method: str,
        path: str,
        status: int,
        timer: RequestTimer,
    ) -> None:
        """Emit the structured access-log line.

        Log fields:
        - ``event=access_log``
        - ``request_id`` (echoes the response header)
        - ``method``, ``route`` (matched route template)
        - ``status_code``
        - ``latency_ms`` (rounded to one decimal)
        - ``lease_id`` (None when not peeked; e.g. for /healthz, /metrics)
        - ``user_query_hash`` (HMAC of question text; empty when None)
        """
        # FastAPI/Starlette attaches the matched ``Route`` to ``scope['route']``
        # once routing has run. Prefer its ``path`` template so we get a
        # bounded-cardinality value (``/leases/{lease_id}``) instead of the
        # literal path with a real id. Falls back to the raw path for 404s
        # and uncaught middleware paths.
        #
        # As of FastAPI >=0.116 (starlette >=0.40), ``scope['route'].path``
        # is relative to the ``APIRouter`` it was declared on (e.g. ``""``
        # for a route mounted at the router's root) rather than the full
        # mounted path. The full, prefix-inclusive template is instead
        # stashed on ``scope['fastapi']['effective_route_context'].path``,
        # so we prefer that when present and fall back to the route's own
        # ``path`` for older FastAPI versions / non-APIRoute routes.
        route_template = path
        matched_route = scope.get("route")
        if matched_route is not None:
            route_template = getattr(matched_route, "path", path)
        effective_context = scope.get("fastapi", {}).get("effective_route_context")
        effective_path = getattr(effective_context, "path", None)
        if isinstance(effective_path, str) and effective_path:
            route_template = effective_path

        latency_ms = round(timer.elapsed_ms(), 1)
        # Pull lease_id + user_query_hash from the process-local stash
        # populated by route dependencies (see ``validate_ask_request``).
        # We use a stash instead of relying on contextvars because FastAPI
        # runs dependency resolution under an anyio task group whose
        # contextvar mutations don't propagate back to the ASGI
        # middleware. Falls back to path_params + the contextvars for
        # routes the dependency didn't annotate. Keyed by the
        # server-generated ``stash_key``, NOT the client-influenceable
        # ``request_id``, so a repeated X-Request-ID can't cause two
        # concurrent requests to clobber each other's stashed metadata.
        stashed_lease_id, stashed_query_hash = pop_request_metadata(stash_key)
        lease_id = stashed_lease_id
        if lease_id is None:
            lease_id = lease_id_var.get()
        if lease_id is None:
            path_params = scope.get("path_params") or {}
            param_lease_id = path_params.get("lease_id")
            if isinstance(param_lease_id, str):
                lease_id = param_lease_id
        user_query_hash = stashed_query_hash or user_query_hash_var.get()
        logger.info(
            "access_log method=%s route=%s status=%d latency_ms=%s lease_id=%s user_query_hash=%s",
            method,
            route_template,
            status,
            latency_ms,
            lease_id or "",
            user_query_hash,
            extra={
                "event": "access_log",
                "request_id": request_id,
                "method": method,
                "route": route_template,
                "status_code": status,
                "latency_ms": latency_ms,
                "lease_id": lease_id or None,
                "user_query_hash": user_query_hash,
            },
        )


class MaxBodySizeMiddleware:
    """ASGI middleware that caps the size of a single request body."""

    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = get_settings().max_upload_size_bytes

        # Fast path: Content-Length already known.
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == b"content-length":
                try:
                    content_length = int(raw_value.decode("latin-1"))
                except (ValueError, UnicodeDecodeError):
                    content_length = -1
                if content_length > max_bytes:
                    await self._send_413(send, content_length, max_bytes)
                    return
                break

        # Slow path: stream-cap the receive channel.
        body_bytes = 0
        over_limit = False

        async def wrapped_receive() -> dict[str, Any]:
            nonlocal body_bytes, over_limit
            message = await receive()
            if message["type"] == "http.request" and not over_limit:
                chunk = message.get("body", b"") or b""
                body_bytes += len(chunk)
                if body_bytes > max_bytes:
                    over_limit = True
                    # Signal end-of-body so downstream sees an incomplete
                    # request; we'll intercept the response via send_wrapper.
                    return {
                        "type": "http.request",
                        "body": b"",
                        "more_body": False,
                    }
            return message

        async def send_wrapper(message: dict[str, Any]) -> None:
            """Intercept the response: if the body exceeded the limit, replace
            whatever the downstream app was about to send with a 413."""
            if over_limit and message["type"] == "http.response.start":
                # Suppress the downstream response and send our 413 instead.
                await self._send_413(send, body_bytes, max_bytes)
                return
            if over_limit:
                # Suppress any subsequent body messages from downstream.
                return
            await send(message)

        await self.app(scope, wrapped_receive, send_wrapper)

    async def _send_413(
        self,
        send: Callable[[dict[str, Any]], Awaitable[None]],
        body_bytes: int,
        max_bytes: int,
    ) -> None:
        logger.warning(
            "Rejecting oversize request body: %d bytes (limit %d)", body_bytes, max_bytes
        )
        payload = {
            "detail": (
                f"Request body too large ({body_bytes} bytes, "
                f"limit {max_bytes} bytes)."
            ),
            "error_code": "RequestTooLarge",
        }
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            }
        )

        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(payload).encode("utf-8"),
                "more_body": False,
            }
        )
