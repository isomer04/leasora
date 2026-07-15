"""Langfuse client wrapper with graceful no-op behavior.

Wraps the Langfuse SDK v4 (OpenTelemetry-native) client so the rest of the
codebase never has to check "is Langfuse configured?" before instrumenting a
call. When ``langfuse_public_key``/``langfuse_secret_key`` are unset (local
dev without a self-hosted Langfuse instance, or the test suite), every method
here becomes a no-op context manager / call, so the app and tests run
identically with or without Langfuse configured.

Never pass raw PII or secrets into span input/output/metadata — callers are
responsible for redacting (see ``core/security.redact_pii``) before calling
into this wrapper. This module does not redact on your behalf.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from leasora_api.core.config import get_settings

# Threshold above which repeated Langfuse failures escalate from
# ``logger.exception`` to ``logger.critical`` for operational visibility.
_CRITICAL_AFTER_FAILURES = 5

logger = logging.getLogger(__name__)


class _NoopObservation:
    """Stand-in for a Langfuse span/generation when tracing is disabled."""

    def update(self, **kwargs: Any) -> None:  # noqa: ARG002 - intentional no-op
        return None


class LangfuseClientWrapper:
    """Thin wrapper around the Langfuse SDK with graceful no-op fallback."""

    def __init__(self) -> None:
        self._client: Any = None
        self._enabled = False
        self._initialized = False
        # Track consecutive Langfuse errors to escalate to critical
        # logging after a threshold, allowing operational visibility
        # into sustained outages rather than repeated exception noise.
        self._consecutive_failures = 0

    def _ensure_initialized(self) -> None:
        """Lazily construct the Langfuse client on first use.

        Privacy-by-default: the client is only constructed when ALL
        of the following are true:

        1. ``settings.langfuse_enabled`` is True (master kill-switch).
        2. ``settings.langfuse_public_key`` is set.
        3. ``settings.langfuse_secret_key`` is set.
        4. ``settings.langfuse_host`` is a non-empty string.

        The empty ``langfuse_host`` default ensures a missed setting
        cannot default to a third-party SaaS endpoint.
        """
        if self._initialized:
            return
        self._initialized = True

        settings = get_settings()
        if not settings.langfuse_enabled:
            # Master kill-switch is off — by far the most common case.
            # No-op so callers never need to check availability themselves.
            logger.info(
                "langfuse_enabled=False; LLM tracing disabled (no-op). "
                "Set LEASORA_LANGFUSE_ENABLED=true and credentials to enable."
            )
            return
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            logger.info(
                "Langfuse keys not configured; LLM tracing disabled (no-op)."
            )
            return
        if not settings.langfuse_host:
            logger.warning(
                "langfuse_enabled=True but langfuse_host is empty; "
                "refusing to initialize to avoid falling back to a "
                "third-party SaaS default. Set LEASORA_LANGFUSE_HOST "
                "(e.g. http://localhost:3001 for self-hosted or "
                "https://cloud.langfuse.com for hosted)."
            )
            return

        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            self._enabled = True
        except Exception:
            self._client = None
            self._enabled = False
            self._record_failure(
                "Failed to initialize Langfuse client; tracing disabled."
            )

    @property
    def enabled(self) -> bool:
        """Whether Langfuse tracing is actually active (keys configured + client initialized)."""
        self._ensure_initialized()
        return self._enabled

    @contextmanager
    def start_span(
        self,
        name: str,
        input: Any = None,  # noqa: A002 - matches Langfuse's public parameter name
        metadata: dict[str, Any] | None = None,
    ) -> Generator[Any, None, None]:
        """Start a generic span. No-ops cleanly when tracing is disabled.

        Args:
            name: Span name (e.g. "retrieval").
            input: Input data for the span. Must not contain raw PII/secrets.
            metadata: Additional metadata. Must not contain raw PII/secrets.

        Yields:
            A Langfuse span object (call ``.update(output=..., metadata=...)``
            on it), or a no-op stand-in when tracing is disabled.
        """
        self._ensure_initialized()
        if not self._enabled or self._client is None:
            yield _NoopObservation()
            return

        with self._client.start_as_current_observation(
            name=name, as_type="span", input=input, metadata=metadata or {}
        ) as span:
            yield span

    @contextmanager
    def start_generation(
        self,
        name: str,
        model: str,
        input: Any = None,  # noqa: A002 - matches Langfuse's public parameter name
        metadata: dict[str, Any] | None = None,
    ) -> Generator[Any, None, None]:
        """Start a generation span (LLM call). No-ops cleanly when tracing is disabled.

        Args:
            name: Generation name (e.g. "answer-generation").
            model: Model identifier used for the call.
            input: Input data (e.g. the prompt). Must not contain raw PII/secrets.
            metadata: Additional metadata, e.g. prompt version. Must not contain
                raw PII/secrets.

        Yields:
            A Langfuse generation object (call ``.update(output=...,
            usage_details=...)`` on it), or a no-op stand-in when tracing is
            disabled.
        """
        self._ensure_initialized()
        if not self._enabled or self._client is None:
            yield _NoopObservation()
            return

        with self._client.start_as_current_observation(
            name=name,
            as_type="generation",
            model=model,
            input=input,
            metadata=metadata or {},
        ) as generation:
            yield generation

    def score_current_trace(
        self, name: str, value: float, comment: str | None = None
    ) -> None:
        """Attach a score to the current trace. No-ops when tracing is disabled."""
        self._ensure_initialized()
        if not self._enabled or self._client is None:
            return
        try:
            self._client.score_current_trace(name=name, value=value, comment=comment)
            self._record_success()
        except Exception:
            self._record_failure("Failed to score current Langfuse trace (non-fatal).")

    def flush(self) -> None:
        """Force-flush pending spans. No-ops when tracing is disabled."""
        self._ensure_initialized()
        if not self._enabled or self._client is None:
            return
        try:
            self._client.flush()
            self._record_success()
        except Exception:
            self._record_failure("Failed to flush Langfuse client (non-fatal).")

    def create_prompt(
        self, name: str, prompt: str, version: str, labels: list[str] | None = None
    ) -> bool:
        """Sync a prompt's content to the Langfuse prompt registry.

        No-ops (returns False) when tracing is disabled.

        Args:
            name: Prompt name (matches the local prompt file stem).
            prompt: Full prompt text (body, not including frontmatter).
            version: Version identifier (e.g. content hash or declared version).
            labels: Optional labels (e.g. ``["production"]``) for this version.

        Returns:
            True if the sync call was made (does not guarantee success beyond
            not raising); False if tracing is disabled.
        """
        self._ensure_initialized()
        if not self._enabled or self._client is None:
            return False
        try:
            self._client.create_prompt(
                name=name,
                prompt=prompt,
                labels=labels or [],
                tags=[version],
            )
            self._record_success()
            return True
        except Exception:
            self._record_failure(
                "Failed to sync prompt '%s' to Langfuse (non-fatal).", name
            )
            return False

    # Failure-tracking helpers
    def _record_failure(self, message: str, *args: Any) -> None:
        """Log a Langfuse failure with escalating severity after N consecutive.

        Each Langfuse call site (init, score, flush, create_prompt) routes
        through this method instead of bare ``logger.exception``, so a
        single transient blip doesn't change log shape but a sustained
        outage gets elevated to ``logger.critical``.
        """
        self._consecutive_failures += 1
        if self._consecutive_failures >= _CRITICAL_AFTER_FAILURES:
            logger.critical(
                "Langfuse failure (%d consecutive): " + message,
                self._consecutive_failures,
                *args,
                exc_info=True,
            )
        else:
            logger.exception(message, *args)

    def _record_success(self) -> None:
        if self._consecutive_failures > 0:
            logger.info(
                "Langfuse recovered after %d consecutive failures",
                self._consecutive_failures,
            )
        self._consecutive_failures = 0


# Singleton instance for dependency injection. Construction is cheap because
# the real Langfuse client is lazily created on first use.
langfuse_client = LangfuseClientWrapper()
