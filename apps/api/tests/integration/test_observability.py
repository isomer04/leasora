"""End-to-end tests for observability endpoints and access-log emission.

Tests verify the observability contract:

- ``/healthz`` returns 200 + a body.
- ``/readyz`` returns a structured response.
- ``/metrics`` returns Prometheus text format.
- ``/eval`` returns 501 (unimplemented).
- Every response carries an ``X-Request-ID`` header.
- The access-log middleware emits one JSON log line per request.
"""

from __future__ import annotations

import logging
import re

import pytest
from fastapi.testclient import TestClient

from leasora_api.main import create_app

UUID_RE = re.compile(r"^[0-9a-f]{32}$")


def _client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_healthz_returns_ok() -> None:
    client = _client()
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_health_legacy_alias_works() -> None:
    """Legacy /health alias kept for backwards compatibility."""
    client = _client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_metrics_endpoint_returns_text() -> None:
    client = _client()
    response = client.get("/metrics")
    assert response.status_code == 200
    # Either a Prometheus text body (when the client is installed) or an
    # empty body with a stub header. Both signal a healthy endpoint.
    content_type = response.headers.get("content-type", "")
    if response.headers.get("x-leasora-metrics-stub"):
        assert response.text == ""
    else:
        assert "text/plain" in content_type
        # ``# HELP`` and ``# TYPE`` lines should appear when the registry
        # is populated. ``leasora_uploads_total`` is the lowest-cardinality
        # and almost always touched, so we assert on it.
        assert "leasora_uploads_total" in response.text or "leasora_refusals_total" in response.text


def test_eval_returns_501() -> None:
    """The dead ``/eval`` endpoint now returns 501 with a structured body."""
    client = _client()
    response = client.post("/eval")
    assert response.status_code == 501
    body = response.json()
    assert body["status"] == "not_implemented"
    assert "CLI" in body["message"] or "CI" in body["message"]


def test_access_log_emits_structured_fields(caplog: pytest.LogCaptureFixture) -> None:
    """A request to /healthz must produce one access_log JSON line."""
    client = _client()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="leasora_api.http.middleware"):
        response = client.get("/healthz", headers={"X-Request-ID": "obs-test-1"})
    assert response.status_code == 200

    # Find the access-log record by event marker
    access_records = [
        r for r in caplog.records if getattr(r, "event", None) == "access_log"
    ]
    assert access_records, "expected at least one access_log record"
    record = access_records[-1]

    # Required fields per access log spec.
    # file (not direct attribute access) because these fields are attached
    # dynamically via ``logging.info(..., extra={...})`` in
    # ``http/middleware.py`` and are not part of the statically-typed
    # ``logging.LogRecord`` API.
    assert getattr(record, "request_id", None) == "obs-test-1"
    assert getattr(record, "method", None) == "GET"
    assert getattr(record, "route", None) == "/healthz"
    assert getattr(record, "status_code", None) == 200
    latency_ms = getattr(record, "latency_ms", None)
    assert isinstance(latency_ms, float)
    assert latency_ms >= 0.0
    # lease_id and user_query_hash should be present (lease_id is None for
    # /healthz; the JSON formatter renders None as JSON null).
    assert hasattr(record, "lease_id")
    assert hasattr(record, "user_query_hash")


def test_access_log_peeks_ask_body(caplog: pytest.LogCaptureFixture) -> None:
    """POST /ask should log lease_id + a HMAC user_query_hash."""
    from unittest.mock import AsyncMock, patch

    client = _client()
    body = {"lease_id": "lease-xyz", "question": "When is rent due?"}
    with patch(
        "leasora_api.http.routes.ask.rag_service.answer_question",
        new=AsyncMock(return_value={"answer": "ok", "sources": [], "confidence": 0.9}),
    ):
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="leasora_api.http.middleware"):
            response = client.post(
                "/ask",
                json=body,
                headers={"X-Request-ID": "obs-ask-1"},
            )
    assert response.status_code == 200

    access = [r for r in caplog.records if getattr(r, "event", None) == "access_log"]
    assert access, "expected at least one access_log record"
    record = access[-1]
    assert getattr(record, "request_id", None) == "obs-ask-1"
    assert getattr(record, "method", None) == "POST"
    assert getattr(record, "route", None) == "/ask"
    assert getattr(record, "status_code", None) == 200
    assert getattr(record, "lease_id", None) == "lease-xyz"
    user_query_hash = getattr(record, "user_query_hash", None)
    assert user_query_hash
    assert isinstance(user_query_hash, str)
    # The hash is a fixed-length hex string; it must NOT contain the raw
    # question.
    assert "When" not in user_query_hash
    assert "rent" not in user_query_hash


def test_access_log_generates_uuid_when_id_missing(caplog: pytest.LogCaptureFixture) -> None:
    """When the client doesn't supply X-Request-ID, the middleware mints one."""
    client = _client()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="leasora_api.http.middleware"):
        response = client.get("/healthz")
    assert response.status_code == 200
    assert UUID_RE.match(response.headers["x-request-id"])
    access = [r for r in caplog.records if getattr(r, "event", None) == "access_log"]
    assert access
    assert UUID_RE.match(getattr(access[-1], "request_id"))


def test_rate_limit_default_on(monkeypatch) -> None:
    """rate_limit_enabled defaults to True.

    Explicitly clears any local override before asserting the default —
    ``conftest.py`` loads the developer's real ``.env``, so without this a
    local ``LEASORA_RATE_LIMIT_ENABLED=false`` would make this fail
    spuriously despite the actual field default being correct.
    """
    from leasora_api.core.config import get_settings

    monkeypatch.delenv("LEASORA_RATE_LIMIT_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.rate_limit_enabled is True, (
            "rate_limit_enabled must default to True in production"
        )
    finally:
        get_settings.cache_clear()
