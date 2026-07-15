"""Unit tests for metrics and structured-logging helpers.

These tests deliberately avoid hitting the HTTP layer so they stay
sub-millisecond even when the optional ``prometheus_client`` dependency
is absent. They verify:

- :func:`hash_query` is deterministic, salt-dependent, and never echoes
  the input text in the output.
- The metric helpers degrade to no-ops when ``prometheus_client`` isn't
  installed (no exceptions).
- :func:`render_metrics` always returns a valid ``(body, content_type)``
  tuple.
"""

from __future__ import annotations

import time

from leasora_api.core.logging import hash_query, reconfigure_from_settings
from leasora_api.core.metrics import (
    metrics_available,
    record_cache,
    record_refusal,
    record_upload,
    record_upload_latency,
    render_metrics,
    time_llm,
    time_retrieval,
)


def test_hash_query_is_deterministic_and_short() -> None:
    a = hash_query("hello world")
    b = hash_query("hello world")
    assert a == b
    assert len(a) == 16  # 16 hex chars per ``_LOG_HASH_TRUNCATE``
    assert all(ch in "0123456789abcdef" for ch in a)


def test_hash_query_does_not_contain_input_text() -> None:
    question = "What's the late fee for late rent?"
    hashed = hash_query(question)
    assert "late" not in hashed
    assert "rent" not in hashed
    assert "?" not in hashed


def test_hash_query_differs_for_different_inputs() -> None:
    assert hash_query("q1") != hash_query("q2")


def test_hash_query_handles_empty_input() -> None:
    assert hash_query("") == ""


def test_reconfigure_from_settings_changes_salt() -> None:
    """Salt rotation flips the hash without invalidating the interface."""
    original = hash_query("rotate me")
    reconfigure_from_settings("super-secret-salt-A")
    rotated = hash_query("rotate me")
    reconfigure_from_settings("")
    restored = hash_query("rotate me")
    assert original != rotated
    assert original == restored


def test_metrics_helpers_never_raise_when_prom_missing(monkeypatch: object) -> None:
    """Even when ``prometheus_client`` isn't installed, the metric helpers
    must NOT raise — they just become no-ops so production never crashes
    on an optional dependency."""

    # We can't import prometheus_client conditionally in the test env,
    # so we simulate "prom missing" by patching module-level symbols to
    # None. The helpers should already handle the None case.
    from leasora_api.core import metrics as metrics_module

    saved = (
        metrics_module.UPLOADS_TOTAL,
        metrics_module.REFUSALS_TOTAL,
        metrics_module.CACHE_TOTAL,
        metrics_module.UPLOAD_LATENCY_MS,
        metrics_module.RETRIEVAL_LATENCY_MS,
        metrics_module.LLM_LATENCY_MS,
    )
    metrics_module.UPLOADS_TOTAL = None
    metrics_module.REFUSALS_TOTAL = None
    metrics_module.CACHE_TOTAL = None
    metrics_module.UPLOAD_LATENCY_MS = None
    metrics_module.RETRIEVAL_LATENCY_MS = None
    metrics_module.LLM_LATENCY_MS = None
    try:
        record_upload("ok")
        record_refusal("rental_term")
        record_cache("exact", hit=True)
        record_upload_latency(123.0)
        with time_retrieval():
            pass
        with time_llm():
            pass
    finally:
        (
            metrics_module.UPLOADS_TOTAL,
            metrics_module.REFUSALS_TOTAL,
            metrics_module.CACHE_TOTAL,
            metrics_module.UPLOAD_LATENCY_MS,
            metrics_module.RETRIEVAL_LATENCY_MS,
            metrics_module.LLM_LATENCY_MS,
        ) = saved


def test_render_metrics_returns_tuple() -> None:
    body, content_type = render_metrics()
    assert isinstance(body, (bytes, bytearray))
    assert content_type.startswith("text/plain")


def test_metrics_available_reflects_install() -> None:
    # Either installed (True) or not (False); both are valid outcomes and
    # the helper just needs to be callable.
    assert isinstance(metrics_available(), bool)


def test_request_timer_advances() -> None:
    from leasora_api.core.logging import RequestTimer

    timer = RequestTimer()
    first = timer.elapsed_ms()
    time.sleep(0.005)
    second = timer.elapsed_ms()
    assert second >= first
    assert second >= 5.0
