"""Integration tests for the /ask per-request LLM timeout.

The route handler wraps ``rag_service.answer_question`` in
``asyncio.wait_for(..., timeout=settings.llm_timeout_seconds)`` so a hung
Groq call cannot hold a worker indefinitely. On timeout, the client gets
a 503 with a static "Answer generation timed out" message — the
underlying exception is not echoed (avoids PII leak).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import leasora_api.http.deps as deps_module
from leasora_api.core.config import get_settings
from leasora_api.http.deps import InMemoryRateLimiter
from leasora_api.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(deps_module, "_rate_limiter", InMemoryRateLimiter())
    return TestClient(create_app(), raise_server_exceptions=False)


def test_ask_returns_503_when_llm_hangs(client, monkeypatch):
    """A hung rag_service.answer_question must surface as 503 LLMError."""
    settings = get_settings()
    # Shrink the timeout so the test runs quickly.
    monkeypatch.setattr(settings, "llm_timeout_seconds", 1)

    async def _hang(*args, **kwargs):
        await asyncio.sleep(10)  # longer than the 1s timeout
        return {"answer": "too late", "sources": [], "confidence": 0.9}

    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(side_effect=_hang),
    ):
        response = client.post(
            "/ask", json={"lease_id": "lease-1", "question": "When is rent due?"}
        )

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "LLMError"
    # Static message; no underlying exception interpolation.
    assert body["detail"] == "Answer generation timed out"


def test_ask_200_when_response_fast(client, monkeypatch):
    """A quick LLM response must still succeed (timeout doesn't fire)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_timeout_seconds", 5)

    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        response = client.post(
            "/ask", json={"lease_id": "lease-1", "question": "When is rent due?"}
        )

    assert response.status_code == 200
