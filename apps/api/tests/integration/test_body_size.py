"""Integration tests for the MaxBodySizeMiddleware.

Verifies:
- A request with Content-Length over the cap is rejected with 413 before
  the route handler runs.
- The 413 body has the same shape as other LeasoraError responses
  (``detail`` + ``error_code``).

Note: ``fastapi.testclient.TestClient`` doesn't let callers set
``Content-Length`` reliably, so we go through the raw ASGI app via
``httpx.AsyncClient`` against the in-process ASGI transport. That gives us
a real Content-Length header so the middleware's fast path can reject
before the body is buffered.
"""

import json

import httpx
import pytest

from leasora_api.core.config import get_settings
from leasora_api.main import create_app


def _async_client_with_cap(max_bytes: int):
    """Build an AsyncClient with a custom max-upload setting."""
    settings = get_settings()
    original = settings.max_upload_size_bytes
    settings.max_upload_size_bytes = max_bytes
    transport = httpx.ASGITransport(app=create_app())
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    settings.max_upload_size_bytes = original
    return client


async def test_content_length_over_limit_returns_413():
    """A pre-declared body larger than the cap must be rejected immediately."""
    settings = get_settings()
    original = settings.max_upload_size_bytes
    settings.max_upload_size_bytes = 1024
    try:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            big_body = b"x" * 4096
            response = await client.post(
                "/ask",
                content=big_body,
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 413
        body = response.json()
        assert body["error_code"] == "RequestTooLarge"
        assert "too large" in body["detail"].lower()
    finally:
        settings.max_upload_size_bytes = original


async def test_content_length_at_or_below_limit_is_accepted_by_middleware():
    """Bodies under the cap should pass through to the route (200, 4xx, etc.).

    A 200 here is incidental — the point is the middleware didn't 413.
    """
    from unittest.mock import AsyncMock, patch

    settings = get_settings()
    original = settings.max_upload_size_bytes
    settings.max_upload_size_bytes = 10_000
    try:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            small_body = json.dumps(
                {"lease_id": "lease-1", "question": "When is rent due?"}
            ).encode()
            with patch(
                "leasora_api.http.routes.ask.rag_service.answer_question",
                new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
            ):
                response = await client.post(
                    "/ask",
                    content=small_body,
                    headers={"Content-Type": "application/json"},
                )
        assert response.status_code != 413
        assert response.status_code == 200
    finally:
        settings.max_upload_size_bytes = original


async def test_413_response_carries_request_id_header():
    """Even rejected requests must propagate X-Request-ID for correlation."""
    settings = get_settings()
    original = settings.max_upload_size_bytes
    settings.max_upload_size_bytes = 1024
    try:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            big_body = b"x" * 4096
            response = await client.post(
                "/ask",
                content=big_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Request-ID": "trace-body-cap",
                },
            )
        assert response.status_code == 413
        assert response.headers["x-request-id"] == "trace-body-cap"
    finally:
        settings.max_upload_size_bytes = original


def test_settings_field_validator_rejects_out_of_range_caps():
    """A cap below 1 MiB or above 1 GiB is rejected by the validator."""
    from pydantic import ValidationError

    from leasora_api.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(groq_api_key="k", max_upload_size_bytes=1024)

    with pytest.raises(ValidationError):
        Settings(groq_api_key="k", max_upload_size_bytes=2 * 1024 * 1024 * 1024)
