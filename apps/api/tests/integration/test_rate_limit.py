"""Integration tests for the config-gated rate limiter.

On a single-tenant local v1, the real driver is LLM cost control,
not public abuse protection. This is a minimal per-process token bucket.
rate limiter — these tests only verify the config-gated on/off behavior and
the 429 response shape.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from leasora_api.core.config import get_settings
from leasora_api.http.deps import InMemoryRateLimiter
import leasora_api.http.deps as deps_module
from leasora_api.main import create_app


@pytest.fixture
def client(monkeypatch):
    """A TestClient with a fresh rate limiter instance per test."""
    monkeypatch.setattr(deps_module, "_rate_limiter", InMemoryRateLimiter())
    app = create_app()
    return TestClient(app)


def test_rate_limit_enabled_by_default_allows_requests_under_limit(client, monkeypatch):
    """Rate limiting is on by default, and requests under the cap succeed."""
    settings = get_settings()
    assert settings.rate_limit_enabled is True
    monkeypatch.setattr(settings, "rate_limit_per_minute", 5)

    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        for _ in range(5):
            response = client.post(
                "/ask", json={"lease_id": "lease-1", "question": "When is rent due?"}
            )
            assert response.status_code == 200


def test_rate_limit_operator_opt_out_allows_many_requests(client, monkeypatch):
    """Operators can disable limiting via LEASORA_RATE_LIMIT_ENABLED=false."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        for _ in range(5):
            response = client.post(
                "/ask", json={"lease_id": "lease-1", "question": "When is rent due?"}
            )
            assert response.status_code == 200


def test_rate_limit_enabled_returns_429_after_limit_exceeded(client, monkeypatch):
    """With rate limiting enabled and a low limit, exceeding it must return 429."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)

    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        first = client.post("/ask", json={"lease_id": "lease-1", "question": "q1?"})
        second = client.post("/ask", json={"lease_id": "lease-1", "question": "q2?"})
        third = client.post("/ask", json={"lease_id": "lease-1", "question": "q3?"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error_code"] == "RateLimitError"


def test_rate_limit_is_per_client(client, monkeypatch):
    """Different client IPs must have independent rate limit buckets."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    limiter = InMemoryRateLimiter()
    limiter.check("client-a", 1)  # client-a has used its one allowed request

    with pytest.raises(Exception):
        limiter.check("client-a", 1)

    # client-b has a completely independent bucket.
    limiter.check("client-b", 1)


def test_metadata_refresh_endpoint_is_rate_limited(client, monkeypatch):
    """The LLM-backed metadata retry must share the API's spend control."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    first = client.post("/leases/does-not-exist/metadata")
    second = client.post("/leases/does-not-exist/metadata")

    assert first.status_code == 404
    assert second.status_code == 429
    assert second.json()["error_code"] == "RateLimitError"
