"""Application configuration settings.

A single flat ``Settings`` class, loaded from environment variables with the
``LEASORA_`` prefix. See .env.example for the full list of supported vars.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_APPS_API_DIR = Path(__file__).resolve().parents[3]

# Default path to the env file. Operators can override via the
# ``LEASORA_ENV_FILE`` environment variable.
_DEFAULT_ENV_FILE = _APPS_API_DIR / ".env"


def _resolve_env_file() -> str | None:
    """Resolve the env-file path for ``BaseSettings``.

    Checks ``LEASORA_ENV_FILE`` env var first, then defaults to
    ``apps/api/.env`` resolved against this file's location.
    Returns ``None`` if no env file exists so pydantic-settings
    falls back to OS environment variables.
    """
    override = os.environ.get("LEASORA_ENV_FILE")
    if override:
        path = Path(override)
        if not path.is_absolute():
            path = Path.cwd() / path
    else:
        path = _DEFAULT_ENV_FILE
    return str(path) if path.exists() else None


class Settings(BaseSettings):
    """Aggregated application settings, loaded from ``LEASORA_``-prefixed env vars."""

    model_config = SettingsConfigDict(
        env_prefix="LEASORA_",
        env_file=_resolve_env_file(),
        extra="ignore",
    )

    # Flat config values from environment
    # API
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 30

    # LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    llm_timeout_seconds: int = 60
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_enabled: bool = False
    rerank_top_n: int = 20

    # Local storage
    upload_dir: str = "data/uploads"
    lease_store_path: str = "data/leases.json"
    comparison_store_path: str = "data/comparisons.json"
    comparison_store_max_records: int = 500
    upload_retention_days: int = 30
    # Caps how many chunks per lease are pulled into a comparison prompt, to
    # bound token usage (see `services/compare/comparison_service.py`).
    compare_max_chunks_per_lease: int = 20
    compare_max_concurrent_llm_calls: int = 5
    compare_per_clause_timeout_seconds: float = 30.0
    # Outer-fan-out buffer added on top of the per-clause-deadline ×
    # batch-count so the overall timeout doesn't race the last call's
    # own deadline.
    compare_overall_timeout_buffer_seconds: float = 5.0

    @field_validator("upload_retention_days")
    @classmethod
    def _validate_upload_retention_days(cls, value: int) -> int:
        """Require automatic deletion to remain enabled with a positive period."""
        if value < 1:
            raise ValueError(f"upload_retention_days must be >= 1, got {value}")
        return value

    @field_validator("compare_max_concurrent_llm_calls")
    @classmethod
    def _validate_compare_concurrency(cls, value: int) -> int:
        """Reject 0 or negative concurrency bounds (would deadlock the fan-out).

        ``asyncio.Semaphore(0)`` and ``asyncio.Semaphore(-1)`` both block
        every acquire forever, silently hanging the comparison request.
        Fail closed at config-load time so a misconfigured deployment
        can't deadlock the API.
        """
        if value < 1:
            raise ValueError(
                f"compare_max_concurrent_llm_calls must be >= 1, got {value}"
            )
        return value

    @field_validator(
        "compare_per_clause_timeout_seconds", "compare_overall_timeout_buffer_seconds"
    )
    @classmethod
    def _validate_positive_timeout(cls, value: float) -> float:
        """Reject zero/negative per-clause timeouts or overall buffers.

        A non-positive value here would either fail every LLM call
        instantly or make the overall fan-out deadline race (or precede)
        the last call's own deadline. Fail closed at config-load time,
        matching the pattern used by ``_validate_compare_concurrency``.
        """
        if value <= 0:
            raise ValueError(f"must be > 0, got {value}")
        return value

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    retrieval_top_k: int = 5
    refusal_threshold: float = 0.55
    hybrid_enabled: bool = False
    hybrid_alpha: float = 0.5
    cache_enabled: bool = True
    cache_threshold: float = 0.92
    semantic_cache_enabled: bool = False
    answer_guard_enabled: bool = False

    # Observability
    # Operator-overridable salt used by the access-log HMAC of user
    # queries. Empty default → ``core.logging`` falls back to a
    # hard-coded dev salt so local/test environments still work.
    log_hash_salt: str = ""
    # ------------------------------------------------------------------
    # Langfuse — Privacy-by-default.
    # Lease text is PII-heavy. Sending it to a third-party SaaS by default is a privacy risk.
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = ""

    # Security
    # PII redaction is unconditional at trust boundaries; it is deliberately
    # not configurable for lease content.
    prompt_injection_defense_enabled: bool = True
    max_upload_size_bytes: int = 50 * 1024 * 1024
    # Whether to echo/propagate a per-request `X-Request-ID` header. The
    # middleware always generates one for log correlation even when this is
    # false; setting this to false suppresses the response-header echo.
    request_id_enabled: bool = True
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("hybrid_alpha")
    @classmethod
    def _validate_hybrid_alpha(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"hybrid_alpha must be between 0.0 and 1.0, got {value}")
        return value

    @field_validator("refusal_threshold", "cache_threshold")
    @classmethod
    def _validate_unit_interval(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"must be between 0.0 and 1.0, got {value}")
        return value

    @field_validator("max_upload_size_bytes")
    @classmethod
    def _validate_max_upload_size(cls, value: int) -> int:
        # 1 MiB lower bound (a too-small cap is a config error), 1 GiB upper
        # bound (anything larger is almost certainly a config mistake).
        if not (1024 * 1024 <= value <= 1024 * 1024 * 1024):
            raise ValueError(
                f"max_upload_size_bytes must be between 1 MiB and 1 GiB, got {value}"
            )
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        """Accept comma-separated string or JSON array format."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError(
                        f"cors_origins JSON value must be a list, got {type(parsed).__name__}"
                    )
                return [str(origin).strip() for origin in parsed if str(origin).strip()]
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        if isinstance(value, (list, tuple)):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return value

    @model_validator(mode="after")
    def _hybrid_requires_rerank(self) -> "Settings":
        """Hybrid retrieval assumes reranking; refuse to start otherwise."""
        if self.hybrid_enabled and not self.rerank_enabled:
            raise ValueError(
                "hybrid_enabled=True requires rerank_enabled=True "
                "(see EVALUATION_REPORT.md; hybrid-only degrades refusal accuracy)"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get singleton settings instance.

    Uses LRU cache to ensure only one Settings instance is created
    throughout the application lifecycle.

    Returns:
        Initialized settings instance

    Raises:
        ValidationError: If required settings are missing or invalid
    """
    return Settings()
