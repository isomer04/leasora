import pytest

from leasora_api.core.config import Settings, get_settings


def test_settings_singleton():
    """Test that get_settings() returns same instance."""
    settings1 = get_settings()
    settings2 = get_settings()
    assert settings1 is settings2


def test_new_retrieval_quality_settings_have_defaults(monkeypatch):
    """New retrieval quality knobs must load with their documented defaults.

    Clears every env var this test asserts on before constructing
    Settings — ``conftest.py`` loads the developer's real ``.env``, so
    any local override of one of these fields would otherwise make this
    fail spuriously despite the actual field defaults being correct.
    """
    for var in (
        "LEASORA_EMBEDDING_MODEL",
        "LEASORA_RETRIEVAL_TOP_K",
        "LEASORA_REFUSAL_THRESHOLD",
        "LEASORA_RERANK_ENABLED",
        "LEASORA_RERANK_TOP_N",
        "LEASORA_RERANKER_MODEL",
        "LEASORA_HYBRID_ENABLED",
        "LEASORA_HYBRID_ALPHA",
        "LEASORA_CACHE_ENABLED",
        "LEASORA_SEMANTIC_CACHE_ENABLED",
        "LEASORA_RATE_LIMIT_ENABLED",
        "LEASORA_RATE_LIMIT_PER_MINUTE",
        "LEASORA_ANSWER_GUARD_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert settings.retrieval_top_k == 5
        assert settings.refusal_threshold == 0.55
        assert settings.rerank_enabled is False
        assert settings.rerank_top_n == 20
        assert settings.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert settings.hybrid_enabled is False
        assert settings.hybrid_alpha == 0.5
        assert settings.cache_enabled is True
        assert settings.semantic_cache_enabled is False
        assert settings.rate_limit_enabled is True
        assert settings.rate_limit_per_minute == 30
        assert settings.answer_guard_enabled is False
    finally:
        get_settings.cache_clear()


def test_settings_overridable_via_env(monkeypatch):
    """New settings must be overridable via LEASORA_ env vars."""
    monkeypatch.setenv("LEASORA_RETRIEVAL_TOP_K", "8")
    monkeypatch.setenv("LEASORA_RERANK_ENABLED", "true")
    monkeypatch.setenv("LEASORA_HYBRID_ALPHA", "0.7")

    settings = Settings()

    assert settings.retrieval_top_k == 8
    assert settings.rerank_enabled is True
    assert settings.hybrid_alpha == 0.7


def test_hybrid_alpha_rejects_out_of_range(monkeypatch):
    monkeypatch.setenv("LEASORA_HYBRID_ALPHA", "2.0")
    with pytest.raises(Exception):
        Settings()


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        # Comma-separated form — the natural ops .env input.
        (
            "https://a.example.com,https://b.example.com",
            ["https://a.example.com", "https://b.example.com"],
        ),
        # Comma-separated, single entry — should round-trip to a one-item list.
        ("https://only.example.com", ["https://only.example.com"]),
        # JSON-array form — what tooling like `jq -r` produces.
        (
            '["https://a.example.com","https://b.example.com"]',
            ["https://a.example.com", "https://b.example.com"],
        ),
    ],
    ids=["csv-multi", "csv-single", "json-array"],
)
def test_cors_origins_accepts_string_forms(monkeypatch, raw_value, expected):
    """Native Pydantic validator accepts CSV, single, and JSON-array forms."""
    monkeypatch.setenv("LEASORA_CORS_ORIGINS", raw_value)
    settings = Settings()
    assert settings.cors_origins == expected


def test_cors_origins_accepts_python_list_directly():
    """Already-parsed list values (programmatic callers) pass through."""
    settings = Settings(cors_origins=["https://x.example.com"])
    assert settings.cors_origins == ["https://x.example.com"]


def test_groq_api_key_can_be_empty_for_non_llm_startup(monkeypatch):
    """An empty key must not prevent startup; GroqClient validates on use."""
    monkeypatch.setenv("LEASORA_GROQ_API_KEY", "")
    settings = Settings()
    assert settings.groq_api_key == ""


def test_hybrid_enabled_requires_rerank_enabled(monkeypatch):
    """Hybrid retrieval is documented as requiring rerank; refuse to start otherwise."""
    monkeypatch.setenv("LEASORA_HYBRID_ENABLED", "true")
    monkeypatch.setenv("LEASORA_RERANK_ENABLED", "false")
    with pytest.raises(Exception, match="hybrid_enabled=True requires rerank_enabled=True"):
        Settings()


def test_hybrid_enabled_with_rerank_enabled_is_allowed(monkeypatch):
    """The supported configuration (hybrid on, rerank on) must still load."""
    monkeypatch.setenv("LEASORA_HYBRID_ENABLED", "true")
    monkeypatch.setenv("LEASORA_RERANK_ENABLED", "true")
    settings = Settings()
    assert settings.hybrid_enabled is True
    assert settings.rerank_enabled is True


def test_langfuse_defaults_privacy_first(monkeypatch):
    """Privacy-by-default: langfuse must default to OFF with empty host."""
    # Inspect the pydantic field defaults directly, bypassing env / .env.
    fields = Settings.model_fields
    assert fields["langfuse_enabled"].default is False, (
        "langfuse_enabled must default to False (master kill-switch)"
    )
    assert fields["langfuse_host"].default == "", (
        "langfuse_host must default to '' so the wrapper refuses to "
        "fall back to a third-party SaaS default"
    )


def test_langfuse_host_is_overridable(monkeypatch):
    """Self-hosted / hosted Langfuse operator overrides work."""
    monkeypatch.setenv("LEASORA_LANGFUSE_HOST", "http://localhost:3001")
    monkeypatch.setenv("LEASORA_LANGFUSE_ENABLED", "true")
    settings = Settings()
    assert settings.langfuse_host == "http://localhost:3001"
    assert settings.langfuse_enabled is True
