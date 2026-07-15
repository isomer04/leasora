"""Integration tests for the X-Request-ID middleware.

Verifies:
- An incoming X-Request-ID header is echoed back unchanged.
- A missing X-Request-ID generates a fresh UUID (32 hex chars).
- A path that raises still echoes the id (id propagation through exceptions).
"""

import re
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from leasora_api.main import create_app

UUID_RE = re.compile(r"^[0-9a-f]{32}$")


def _client():
    return TestClient(create_app(), raise_server_exceptions=False)


def test_request_id_echoes_inbound_header():
    client = _client()
    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        response = client.post(
            "/ask",
            json={"lease_id": "lease-1", "question": "When is rent due?"},
            headers={"X-Request-ID": "client-supplied-id-123"},
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "client-supplied-id-123"


def test_request_id_generated_when_absent():
    client = _client()
    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        response = client.post(
            "/ask", json={"lease_id": "lease-1", "question": "When is rent due?"}
        )

    assert response.status_code == 200
    request_id = response.headers.get("x-request-id", "")
    assert UUID_RE.match(request_id), f"Expected a generated UUID-shaped id, got {request_id!r}"


def test_request_id_echoed_on_error_path():
    """A 4xx/5xx response must still carry the X-Request-ID header."""
    client = _client()
    response = client.post(
        "/ask",
        json={"lease_id": "INVALID ID WITH SPACES", "question": "When is rent due?"},
        headers={"X-Request-ID": "trace-42"},
    )

    # ValidationError → 422 from the LeasoraError handler.
    assert response.status_code in (400, 422)
    assert response.headers["x-request-id"] == "trace-42"


def test_request_id_does_not_crash_on_unusually_long_inbound_id():
    """Overly-long ids must not crash; we just generate a fresh one."""
    client = _client()
    too_long = "x" * 500
    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        response = client.post(
            "/ask",
            json={"lease_id": "lease-1", "question": "When is rent due?"},
            headers={"X-Request-ID": too_long},
        )

    assert response.status_code == 200
    echoed = response.headers["x-request-id"]
    # We replace too-long ids with a generated one rather than echoing them.
    assert echoed != too_long
    assert UUID_RE.match(echoed)
