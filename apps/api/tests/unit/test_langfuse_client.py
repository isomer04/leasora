"""Tests for the Langfuse client wrapper's no-op + privacy behavior.

These tests must exercise the disabled paths. Each test explicitly clears
keys / disables the flag via ``monkeypatch`` and forces the ``get_settings()``
cache to re-evaluate.

Three privacy invariants are pinned here:

1. ``langfuse_enabled`` is the master kill-switch. When False (the default),
   the wrapper MUST NOT initialize a real Langfuse client.
2. ``langfuse_host`` defaults to an empty string. When ``enabled=True``
   but ``host`` is empty, the wrapper MUST refuse to fall back to a
   third-party SaaS default.
3. The wrapper works as a no-op context manager / call when disabled —
   callers must not need to check ``wrapper.enabled`` themselves.
"""

from __future__ import annotations

import pytest

from leasora_api.core.config import get_settings
from leasora_api.core.langfuse_client import LangfuseClientWrapper


@pytest.fixture(autouse=True)
def _force_langfuse_disabled(monkeypatch):
    """Force the kill-switch off + keys empty for every test in this module.

    Mirrors the prior behavior (keys empty) but additionally clears
    ``langfuse_enabled`` to its default (False). Tests that want to
    exercise the enabled path opt in explicitly.
    """
    monkeypatch.delenv("LEASORA_LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LEASORA_LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LEASORA_LANGFUSE_ENABLED", raising=False)
    monkeypatch.delenv("LEASORA_LANGFUSE_HOST", raising=False)
    settings = get_settings()
    monkeypatch.setattr(settings, "langfuse_enabled", False)
    monkeypatch.setattr(settings, "langfuse_public_key", None)
    monkeypatch.setattr(settings, "langfuse_secret_key", None)
    monkeypatch.setattr(settings, "langfuse_host", "")


def test_disabled_by_default_without_keys():
    """Without configured keys, the wrapper must report disabled."""
    wrapper = LangfuseClientWrapper()
    assert wrapper.enabled is False


def test_master_kill_switch_disables_even_when_keys_set(monkeypatch):
    """`langfuse_enabled=False` overrides any keys accidentally set."""
    settings = get_settings()
    monkeypatch.setattr(settings, "langfuse_enabled", False)  # explicit
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-lf-deadbeef")  # but a key is set
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-lf-deadbeef")
    monkeypatch.setattr(settings, "langfuse_host", "https://cloud.langfuse.com")

    wrapper = LangfuseClientWrapper()
    assert wrapper.enabled is False


def test_enabled_true_without_host_does_not_fall_back_to_saas(monkeypatch):
    """When enabled but host is empty, the wrapper refuses to init.

    Audit fix: the default ``langfuse_host`` is ""; the wrapper must NOT
    silently default to https://cloud.langfuse.com when the operator
    forgot to set the host.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-lf-deadbeef")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-lf-deadbeef")
    monkeypatch.setattr(settings, "langfuse_host", "")  # explicitly empty

    wrapper = LangfuseClientWrapper()
    assert wrapper.enabled is False


def test_start_span_noop_context_manager_does_not_raise():
    """start_span must work as a context manager even when tracing is disabled."""
    wrapper = LangfuseClientWrapper()

    with wrapper.start_span("test-span", input={"question": "test"}) as span:
        span.update(output="result")  # must not raise


def test_start_generation_noop_context_manager_does_not_raise():
    wrapper = LangfuseClientWrapper()

    with wrapper.start_generation("test-gen", model="test-model", input="prompt") as generation:
        generation.update(output="answer", usage_details={"total_tokens": 10})


def test_score_current_trace_noop_does_not_raise():
    wrapper = LangfuseClientWrapper()
    wrapper.score_current_trace("relevance", 0.9)  # must not raise


def test_flush_noop_does_not_raise():
    wrapper = LangfuseClientWrapper()
    wrapper.flush()  # must not raise


def test_enabled_is_idempotent():
    """Repeated .enabled checks must not re-initialize or raise."""
    wrapper = LangfuseClientWrapper()
    assert wrapper.enabled is False
    assert wrapper.enabled is False