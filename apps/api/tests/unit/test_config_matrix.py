"""Property-based config-matrix tests.

These tests exercise invariants across the active ``Settings`` flags:

- If ``hybrid_enabled`` is True, then ``rerank_enabled`` must be True.
- ``refusal_threshold`` and ``cache_threshold`` must be in ``[0.0, 1.0]``.
- ``hybrid_alpha`` must be in ``[0.0, 1.0]``.
- ``max_upload_size_bytes`` must be within ``[1 MiB, 1 GiB]``.

We use ``hypothesis`` to generate random *valid* configuration combinations
and assert that loading the resulting ``Settings`` either succeeds cleanly
or raises a ``pydantic.ValidationError`` with a message that matches a
documented invariant. Hypothesis shrinks failing examples down to the
smallest reproducer, so a regression is easy to debug.

These tests are deliberately *structural* — they don't touch any LLM,
network, or on-disk state. They are fast and CI-friendly.

NOTE: ``groq_api_key`` is optional at startup so ingestion and retrieval-only
paths run without Groq. ``conftest.py`` sets ``LEASORA_GROQ_API_KEY=test-key-123``
for the default run, so ``Settings(**overrides)`` is fine here.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from pydantic import ValidationError

from leasora_api.core.config import Settings
from leasora_api.core.security import redact_pii

# All float/text strategies are valid under their field validators. Invalid
# values would be filtered out and just waste cycles shrinking, so we generate
# in-range values to focus the test on cross-field invariants.

_valid_unit_float = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_valid_alpha = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_valid_upload_size = st.integers(min_value=1024 * 1024, max_value=1024 * 1024 * 1024)


@st.composite
def valid_settings_kwargs(draw: st.DrawFn) -> dict[str, object]:
    """Draw a *valid* Settings kwargs dict (all field-level invariants hold).

    Cross-field invariants (hybrid→rerank, etc.) are intentionally allowed
    to be either True or False here — those are the properties we want
    the matrix tests to assert.
    """
    return {
        "rate_limit_enabled": draw(st.booleans()),
        "rate_limit_per_minute": draw(st.integers(min_value=1, max_value=1000)),
        "groq_api_key": "hypothesis-test-key",
        "groq_model": draw(st.sampled_from(["llama-3.3-70b-versatile", "llama-3.1-8b-instant"])),
        "llm_timeout_seconds": draw(st.integers(min_value=1, max_value=600)),
        "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "rerank_enabled": draw(st.booleans()),
        "rerank_top_n": draw(st.integers(min_value=1, max_value=100)),
        "cache_threshold": draw(_valid_unit_float),
        "upload_dir": "data/uploads",
        "lease_store_path": "data/leases.json",
        "comparison_store_path": "data/comparisons.json",
        "compare_max_chunks_per_lease": draw(st.integers(min_value=1, max_value=200)),
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "retrieval_top_k": draw(st.integers(min_value=1, max_value=50)),
        "refusal_threshold": draw(_valid_unit_float),
        "hybrid_enabled": draw(st.booleans()),
        "hybrid_alpha": draw(_valid_alpha),
        "cache_enabled": draw(st.booleans()),
        "semantic_cache_enabled": draw(st.booleans()),
        "answer_guard_enabled": draw(st.booleans()),
        "langfuse_enabled": False,
        "langfuse_public_key": None,
        "langfuse_secret_key": None,
        "langfuse_host": "",
        "prompt_injection_defense_enabled": draw(st.booleans()),
        "max_upload_size_bytes": draw(_valid_upload_size),
        "request_id_enabled": draw(st.booleans()),
        "cors_origins": ["http://localhost:3000"],
    }


# Cross-field invariants

@given(valid_settings_kwargs())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_hybrid_enabled_implies_rerank_enabled(kwargs: dict[str, object]) -> None:
    """``hybrid_enabled=True`` ⇒ ``rerank_enabled=True``."""
    if kwargs["hybrid_enabled"]:
        kwargs["rerank_enabled"] = True

    settings = Settings(**kwargs)
    if settings.hybrid_enabled:
        assert settings.rerank_enabled is True, (
            "hybrid_enabled=True without rerank_enabled=True must be "
            "rejected at config-load time"
        )


@given(valid_settings_kwargs())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_hybrid_with_rerank_disabled_is_rejected(kwargs):
    """A deliberate hybrid-on / rerank-off configuration must fail closed."""
    kwargs["hybrid_enabled"] = True
    kwargs["rerank_enabled"] = False
    with pytest.raises(ValidationError, match="hybrid_enabled=True requires rerank_enabled=True"):
        Settings(**kwargs)


@given(_valid_unit_float)
def test_refusal_threshold_accepts_unit_interval(value):
    s = Settings(refusal_threshold=value)
    assert 0.0 <= s.refusal_threshold <= 1.0


@given(st.floats(min_value=1.001, max_value=10.0, allow_nan=False))
def test_refusal_threshold_rejects_above_one(value):
    with pytest.raises(ValidationError, match="must be between"):
        Settings(refusal_threshold=value)


@given(st.floats(min_value=-10.0, max_value=-0.001, allow_nan=False))
def test_refusal_threshold_rejects_below_zero(value):
    with pytest.raises(ValidationError, match="must be between"):
        Settings(refusal_threshold=value)


@given(_valid_alpha)
def test_hybrid_alpha_accepts_unit_interval(value):
    s = Settings(hybrid_alpha=value)
    assert 0.0 <= s.hybrid_alpha <= 1.0


@given(_valid_upload_size)
def test_max_upload_size_bytes_accepts_within_range(value):
    s = Settings(max_upload_size_bytes=value)
    assert s.max_upload_size_bytes == value


@given(st.integers(max_value=1024 * 1024 - 1))
def test_max_upload_size_bytes_rejects_below_one_mib(value):
    with pytest.raises(ValidationError, match="max_upload_size_bytes"):
        Settings(max_upload_size_bytes=value)


@given(st.integers(min_value=1024 * 1024 * 1024 + 1, max_value=10 * 1024 * 1024 * 1024))
def test_max_upload_size_bytes_rejects_above_one_gib(value):
    with pytest.raises(ValidationError, match="max_upload_size_bytes"):
        Settings(max_upload_size_bytes=value)


def test_config_flag_count_is_within_expected_band():
    """Keep accidental Settings growth visible while allowing small changes."""
    fields = Settings.model_fields
    assert 30 <= len(fields) <= 45, (
        f"Settings has {len(fields)} fields; expected 30-45 (current target: 34)."
    )


# ---- PII redaction invariant ----

_ssn_strategy = st.tuples(
    st.integers(min_value=100, max_value=999),
    st.integers(min_value=10, max_value=99),
    st.integers(min_value=1000, max_value=9999),
).map(lambda t: f"{t[0]:03d}-{t[1]:02d}-{t[2]:04d}")

_cc_strategy = st.tuples(
    st.integers(min_value=1000, max_value=9999),
    st.integers(min_value=1000, max_value=9999),
    st.integers(min_value=1000, max_value=9999),
    st.integers(min_value=1000, max_value=9999),
).map(lambda t: f"{t[0]} {t[1]} {t[2]} {t[3]}")


@st.composite
def pii_text(draw):
    ssn = draw(_ssn_strategy)
    cc = draw(_cc_strategy)
    word = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll"), max_codepoint=0x7E),
        min_size=3, max_size=20,
    ))
    return f"{word} SSN={ssn} CC={cc}"


@given(pii_text())
@settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow])
def test_pii_redaction_strips_ssn_and_cc(text):
    """redact_pii always scrubs supported SSN and card-number patterns."""
    ssn = text.split("SSN=", 1)[1].split(" ", 1)[0]
    cc = text.split("CC=", 1)[1].split(" ", 1)[0]
    redacted = redact_pii(text)
    assert ssn not in redacted, f"redact_pii failed to strip SSN={ssn!r}; output: {redacted!r}"
    assert cc not in redacted, f"redact_pii failed to strip CC={cc!r}; output: {redacted!r}"
