"""Integration tests for the Retry-After header on 429 responses.

The RateLimitError carries a ``retry_after`` (seconds) hint that the
exception handler surfaces as the ``Retry-After`` response header.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import leasora_api.http.deps as deps_module
from leasora_api.core.config import get_settings
from leasora_api.http.deps import InMemoryRateLimiter
from leasora_api.main import create_app

# Rate limit window bounds: fresh bucket can have up to ~61s remaining
# in a 60s window (accounting for clock skew and bucket reset timing)
MAX_RATE_LIMIT_WINDOW_SECONDS = 61


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(deps_module, "_rate_limiter", InMemoryRateLimiter())
    return TestClient(create_app())


def test_429_response_includes_retry_after_header(client, monkeypatch):
    """A 429 must include a Retry-After header with an integer second value."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        first = client.post("/ask", json={"lease_id": "lease-1", "question": "q1?"})
        second = client.post("/ask", json={"lease_id": "lease-1", "question": "q2?"})

    assert first.status_code == 200, "First request should succeed"
    assert second.status_code == 429, "Second request should be rate limited"

    retry_after = second.headers.get("retry-after")
    assert retry_after is not None, "Missing Retry-After header on 429"
    # Per RFC 7231: integer seconds (delta-seconds form).
    assert retry_after.isdigit(), f"Expected integer seconds, got {retry_after!r}"
    seconds = int(retry_after)
    assert 1 <= seconds <= MAX_RATE_LIMIT_WINDOW_SECONDS, "Retry-After must be in valid window"


def test_429_body_shape_preserved(client, monkeypatch):
    """The structured error body must still be present alongside Retry-After."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        client.post("/ask", json={"lease_id": "lease-1", "question": "q1?"})
        second = client.post("/ask", json={"lease_id": "lease-1", "question": "q2?"})

    body = second.json()
    assert body["error_code"] == "RateLimitError", "Error code must be RateLimitError"
    assert "rate limit" in body["detail"].lower(), "Error detail must mention rate limit"


def test_non_429_responses_omit_retry_after(client):
    """A 200 response must not carry a Retry-After header (would be misleading)."""
    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        response = client.post("/ask", json={"lease_id": "lease-1", "question": "q?"})

    assert response.status_code == 200, "Request should succeed"
    assert response.headers.get("retry-after") is None, "Successful response must not have Retry-After"
