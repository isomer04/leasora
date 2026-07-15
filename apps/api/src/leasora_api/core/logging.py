"""Structured logging helpers.

The API writes a single JSON log line per request (the ``access_log``
emitted by :class:`leasora_api.http.middleware.RequestIDMiddleware`). The
emitted record carries:

- ``request_id`` — the per-request UUID surfaced in the response header
- ``lease_id`` — parsed from the request path or body when available
- ``route`` — the matched route template (``/leases/{lease_id}`` instead of
  the literal ``/leases/lease-123``) to keep cardinality bounded
- ``status_code`` — final HTTP status emitted
- ``latency_ms`` — wall-clock duration in milliseconds
- ``user_query_hash`` — HMAC-SHA256 of the user query text, hex-truncated

This module is the only place we touch the underlying log formatter so a
future swap to OpenTelemetry's JSON exporter or a SaaS log shipper stays
in one file.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from contextvars import ContextVar
from typing import Any

from pythonjsonlogger.json import JsonFormatter

# Per-request observability stash.
#
# FastAPI resolves dependencies under an anyio task group. Contextvar
# mutations in those child tasks don't propagate back to the parent ASGI
# middleware task, so the middleware cannot reliably read metadata set in
# ``validate_ask_request``. Keep a tiny process-local stash keyed by the
# current request id instead; it is bounded by the number of in-flight
# requests and popped as soon as the access-log line is emitted.
_MAX_ACCESS_LOG_STASH = 10_000
_stash_lock = threading.Lock()
_access_stash: dict[str, dict[str, str | None]] = {}

# Per-request correlation id, set by `http.middleware.RequestIDMiddleware`.
# Read by `get_logger()`'s formatter so every log line emitted during a
# request includes the id, making it easy to correlate a single user report
# to a server log line. Default None when no request is in flight.
#
# SECURITY: This ID is client-controlled (may be adopted from an incoming
# ``X-Request-ID`` header). Never use as a dict key or correlate state that
# must remain isolated between concurrent requests. Two concurrent requests
# with identical client-supplied IDs would collide. Use
# ``internal_correlation_id_var`` (always server-generated) for that.
#
# This design ensures the user's ID appears in response headers (for
# user-to-operator correlation) while the stash key remains server-generated
# to prevent cross-request state collision.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
# Server-generated per-request key, always unique and regenerated every
# request regardless of any client-supplied ``X-Request-ID``. This is the
# *only* safe dict key for request-scoped state (e.g. access-log stash).
# Using this ensures no collision between concurrent requests, even if a
# client reuses X-Request-ID values or deliberately tries to collide.
internal_correlation_id_var: ContextVar[str | None] = ContextVar(
    "internal_correlation_id", default=None
)
# Request metadata populated by route dependencies (e.g.
# ``validate_ask_request``). Keeping these in ContextVars avoids peeking
# or replaying the raw ASGI body in middleware, which can break Starlette's
# body parser and unnecessarily hold PII in memory.
lease_id_var: ContextVar[str | None] = ContextVar("lease_id", default=None)
user_query_hash_var: ContextVar[str] = ContextVar("user_query_hash", default="")


def _request_id_log_adapter(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Inject the current request id into every JSON log record."""
    request_id = request_id_var.get()
    if request_id is not None:
        event_dict.setdefault("request_id", request_id)
    return event_dict


class _ContextInjectingJsonFormatter(JsonFormatter):
    """JsonFormatter that always includes the current request id, if any."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        request_id = request_id_var.get()
        if request_id is not None:
            log_record.setdefault("request_id", request_id)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with JSON formatting and request-id injection."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Only add handler if none exists (avoid duplicate handlers)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = _ContextInjectingJsonFormatter(
            fmt='%(asctime)s %(levelname)s %(name)s %(message)s',
            rename_fields={"asctime": "timestamp", "levelname": "level"}
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.propagate = False
    return logger


# Access-log helpers

# Hard-coded secret-salt used by ``hash_query`` so PII-rich question text
# never reaches the log line. Operationally, this is a process secret;
# rotating it requires a deploy. The default value exists so the test
# suite + local dev work without a LEASORA_LOG_HASH_SALT env var; the
# real secret is read in ``reconfigure_from_settings``.
_LOG_HASH_SALT = b"leasora-access-log-salt"
_LOG_HASH_TRUNCATE = 16  # hex chars; 64 bits of collision-resistant entropy


def hash_query(text: str) -> str:
    """Return a short, salted HMAC-SHA256 of ``text`` for log cardinality control.

    The full question is never logged; this gives an operator enough
    fidelity to spot duplicate/related questions without ever putting the
    raw text on disk or shipping it to a log aggregator.
    """
    if not text:
        return ""
    digest = hmac.new(_LOG_HASH_SALT, text.encode("utf-8", errors="replace"), hashlib.sha256)
    return digest.hexdigest()[:_LOG_HASH_TRUNCATE]


def stash_request_metadata(
    request_id: str,
    *,
    lease_id: str | None,
    user_query_hash: str,
) -> None:
    """Record request metadata for the access-log middleware.

    Called by route dependencies after validation. The middleware pops
    the entry at response-finally time, so the stash is bounded by active
    requests. A hard cap protects against a pathological client that
    supplies a new request id on every malformed request.
    """
    if not request_id:
        return
    with _stash_lock:
        if len(_access_stash) >= _MAX_ACCESS_LOG_STASH:
            evict_count = max(1, len(_access_stash) // 10)
            for key in list(_access_stash.keys())[:evict_count]:
                _access_stash.pop(key, None)
        _access_stash[request_id] = {
            "lease_id": lease_id,
            "user_query_hash": user_query_hash,
        }


def pop_request_metadata(request_id: str) -> tuple[str | None, str]:
    """Read and remove ``(lease_id, user_query_hash)`` for a request."""
    with _stash_lock:
        entry = _access_stash.pop(request_id, None)
    if entry is None:
        return None, ""
    lease_id = entry.get("lease_id")
    user_hash = entry.get("user_query_hash")
    return (
        lease_id if isinstance(lease_id, str) else None,
        user_hash if isinstance(user_hash, str) else "",
    )


def reconfigure_from_settings(log_hash_salt: str | None) -> None:
    """Reconfigure module-level state (e.g. the HMAC salt) from settings.

    Called once on app startup so operators can rotate the salt via
    ``LEASORA_LOG_HASH_SALT`` without restarting the API *and* editing
    Python source. ``None``/empty values fall back to the hard-coded salt
    so dev environments keep working.
    """
    global _LOG_HASH_SALT
    if log_hash_salt:
        _LOG_HASH_SALT = log_hash_salt.encode("utf-8")
    else:
        _LOG_HASH_SALT = b"leasora-access-log-salt"


class RequestTimer:
    """Wall-clock timer used by the access-log middleware.

    ``start`` is captured at request entry; ``elapsed_ms()`` returns the
    duration in milliseconds at the time of the access-log emission.
    """

    __slots__ = ("_start",)

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        """Return elapsed wall-clock milliseconds (float, rounded at the call site)."""
        return (time.perf_counter() - self._start) * 1_000.0
