"""Groq LLM client with retry and circuit-breaker reliability."""

import logging
import random
import threading
import time
from typing import Any, Protocol

from leasora_api.core.config import get_settings
from leasora_api.core.exceptions import LLMError
from leasora_api.core.json_parse import parse_json_lenient

logger = logging.getLogger(__name__)

# Tunables kept module-local so settings.py doesn't grow 6 fields for an
# internal reliability contract. These are fixed module constants, not
# env-configurable — there is no env var override for them.
_MAX_RETRIES = 3
# Backoff constants for exponential retry with jitter when no server hint available
_BASE_BACKOFF_SECONDS = 0.5  # Initial backoff: 0.5s base with ±50% jitter
_MAX_BACKOFF_SECONDS = 4.0  # Blind exponential backoff cap: ~0.5s → ~1s → ~2s → ~4s max
# Separate, larger cap for honoring an upstream Retry-After hint (as
# opposed to _MAX_BACKOFF_SECONDS, which bounds the no-hint exponential
# backoff path). A real Retry-After value (e.g. 10s) should not be
# clamped down to the small blind-backoff cap, or the client retries
# while still rate-limited and burns its retry budget for nothing.
_MAX_RETRY_AFTER_SECONDS = 30.0  # Server-hint-based backoff cap: respects Retry-After up to 30s
_CIRCUIT_FAILURE_THRESHOLD = 6
_CIRCUIT_RESET_SECONDS = 15.0

# Total attempts per call, including the initial try (public so callers
# like ``comparison_service`` can size their own timeouts around the
# worst-case retry budget of a single ``_call_groq`` invocation).
MAX_ATTEMPTS = _MAX_RETRIES + 1

# HTTP-style statuses from groq SDK or httpx that we treat as transient.
# 429 (rate limited) and 5xx (server error) get retried; 4xx other than
# 429 (auth, bad request, etc.) is a client bug and not retried.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class _CircuitOpenError(LLMError):
    """Raised when the per-process circuit breaker is open.

    Surfaces a static message (no upstream echo, to keep PII out of user
    responses) and lets callers degrade gracefully (e.g. return a partial
    comparison result instead of wedging on a single bad clause type).
    """


class LLMClient(Protocol):
    """Protocol for LLM clients (for testing and flexibility)."""

    def complete(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate completion for a given prompt."""

        ...


class GroqClient:
    """Typed wrapper around Groq API.

    Uses lazy initialization to avoid importing Groq SDK if not needed.

    Concurrency note: the per-process circuit-breaker state
    (``_circuit_open_until``, ``_consecutive_failures``) is guarded by a
    plain ``threading.Lock`` because the underlying Groq SDK call is
    synchronous and runs in a worker thread under ``asyncio.to_thread``.
    This lock is never held across an ``await`` and only protects
    counter/timestamp mutations, so contention is bounded to a few
    instructions per call.
    """

    def __init__(self) -> None:
        """Initialize Groq client (lazy-loaded on first use)."""
        self._groq_client: Any = None
        self._model_name: str | None = None
        # Circuit-breaker state. ``_consecutive_failures`` increments on
        # every error after a transient retry exhausts; when it crosses
        # ``_CIRCUIT_FAILURE_THRESHOLD`` the circuit opens for
        # ``_CIRCUIT_RESET_SECONDS`` so we stop hammering a broken
        # upstream. Successes reset the counter.
        self._circuit_lock = threading.Lock()
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _ensure_initialized(self) -> None:
        """Initialize Groq client on first use.

        Raises:
            ImportError: If Groq SDK is not installed
            LLMError: If API key is not configured
        """
        if self._groq_client is not None:
            return

        try:
            from groq import Groq
        except ImportError as error:
            raise ImportError("Groq SDK not installed. Install with: pip install groq") from error

        settings = get_settings()

        if not settings.groq_api_key:
            raise LLMError("LEASORA_GROQ_API_KEY environment variable not set")

        try:
            self._groq_client = Groq(api_key=settings.groq_api_key, timeout=settings.llm_timeout_seconds)
            self._model_name = settings.groq_model
        except Exception as error:
            # Don't interpolate the underlying exception into the surfaced
            # message; SDK init errors can echo config fragments. Traceback
            # preserved via `from` for debuggability.
            logger.exception("Failed to initialize Groq client")
            raise LLMError("Failed to initialize Groq client") from error

    def complete(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate LLM completion for a prompt.

        Args:
            prompt: The input prompt/question
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            LLM-generated response text

        Raises:
            LLMError: If the API call fails
        """
        text, _usage = self.complete_with_usage(prompt, temperature)
        return text

    def complete_with_usage(
        self, prompt: str, temperature: float = 0.7
    ) -> tuple[str, dict[str, int]]:
        """Generate LLM completion for a prompt, returning token usage too.

        Args:
            prompt: The input prompt/question
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            Tuple of (completion text, usage dict with prompt_tokens/
            completion_tokens/total_tokens). Usage dict is empty if the API
            response didn't include usage data.

        Raises:
            LLMError: If the API call fails
        """
        response, usage = self._call_groq(prompt, temperature)
        content = response.choices[0].message.content
        return str(content) if content else "", usage

    @property
    def model(self) -> str:
        """Get the configured model name.

        Returns:
            Model identifier string

        Raises:
            LLMError: If client not initialized
        """
        self._ensure_initialized()
        if self._model_name is None:
            raise LLMError("Model name not available")
        return self._model_name

    def complete_structured(
        self,
        prompt: str,
        temperature: float = 0.3,
        timeout: float | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Generate a JSON-mode completion and parse it into a dict.

        Uses Groq's JSON Object Mode (``response_format={"type": "json_object"}``),
        which is supported broadly across Groq models (unlike strict
        ``json_schema`` mode, currently limited to a small set of GPT-OSS
        models — see https://console.groq.com/docs/structured-outputs).
        JSON Object Mode guarantees syntactically valid JSON but not schema
        compliance, so callers are responsible for validating the returned
        dict against their own schema (see
        ``RAGQueryService._parse_structured_answer`` for an example that
        degrades gracefully on validation failure instead of raising).

        The prompt must itself instruct the model on the desired JSON shape;
        this method only sets the response format, it does not inject schema
        instructions.

        Args:
            prompt: The input prompt, including JSON-shape instructions.
            temperature: Sampling temperature (0.0-1.0).
            timeout: Overall deadline in seconds, shared across the initial
                attempt and all retries (see ``_call_groq``). When ``None``,
                falls back to ``settings.llm_timeout_seconds``.

        Returns:
            Tuple of (parsed JSON dict, token usage dict). Strips common
            code-fence wrapping (```json ... ```) before parsing as a
            fallback for models that don't perfectly respect JSON Object Mode.

        Raises:
            LLMError: If the API call fails, or if the response cannot be
                parsed as JSON even after stripping code fences.
        """
        response, usage = self._call_groq(
            prompt,
            temperature,
            response_format={"type": "json_object"},
            timeout=timeout,
        )
        content = response.choices[0].message.content or ""

        parsed = parse_json_lenient(content)
        if parsed is None:
            # JSON parse failure on the LLM's structured output. Surface
            # a static message; the raw content is kept on the exception
            # `__cause__` for debugging but is not interpolated into a
            # user-visible string.
            raise LLMError("Structured LLM response was not valid JSON") from None

        if not isinstance(parsed, dict):
            raise LLMError("Structured LLM response was valid JSON but not an object")

        return parsed, usage

    def _call_groq(
        self,
        prompt: str,
        temperature: float,
        response_format: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> tuple[Any, dict[str, int]]:
        """Shared Groq API call with retry, backoff, and circuit-break.

        Args:
            prompt: The input prompt.
            temperature: Sampling temperature.
            response_format: Optional response format (e.g. {"type": "json_object"}).
            timeout: Overall deadline in seconds for this call, shared across
                the initial attempt and all retries (not a fresh budget per
                attempt). Defaults to ``settings.llm_timeout_seconds`` when
                not provided — useful when a caller has a tighter deadline
                than the global default.

        Returns:
            Tuple of (raw API response, usage dict).

        Raises:
            LLMError: If the API call fails irrecoverably (non-retryable
                client error, retries exhausted, circuit open, or the
                overall deadline below is exhausted).
            ``_CircuitOpenError`` is a subclass so callers can catch it
                explicitly if they want to degrade differently, but the
                default handler treats it identically to a generic LLMError.
        """
        self._ensure_initialized()

        if self._groq_client is None or self._model_name is None:
            raise LLMError("Groq client not properly initialized")

        self._maybe_close_circuit()

        # All attempts (initial + retries) share one deadline instead of
        # each getting a fresh `timeout`-sized budget — otherwise
        # MAX_ATTEMPTS retries plus backoff sleeps can take up to ~4x the
        # caller's intended timeout, which is exactly the budget a caller
        # (RAGQueryService, bounded by ask.py's asyncio.wait_for; or
        # comparison_service's per-clause timeout) is trying to enforce.
        # A thread running this call can't be forcibly cancelled once the
        # caller's own await gives up, so this bounds how long it keeps
        # burning in the background rather than eliminating that lag.
        overall_budget = timeout if timeout is not None else get_settings().llm_timeout_seconds
        deadline = time.monotonic() + overall_budget

        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        last_error: BaseException | None = None
        for attempt in range(_MAX_RETRIES + 1):
            if self._circuit_is_open():
                logger.warning("Groq circuit breaker open; short-circuiting call")
                raise _CircuitOpenError("Groq provider circuit breaker is open")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._record_failure()
                logger.warning(
                    "LLM completion deadline (%.1fs) exhausted before attempt %d/%d",
                    overall_budget,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                )
                raise LLMError("LLM completion timed out") from last_error
            kwargs["timeout"] = remaining
            try:
                response = self._groq_client.chat.completions.create(**kwargs)
                usage: dict[str, int] = {}
                if getattr(response, "usage", None) is not None:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                self._record_success()
                return response, usage
            except Exception as error:  # noqa: BLE001 - we classify & re-raise below
                last_error = error
                retry_after, status_code = _extract_retry_after_and_status(error)
                if not _is_retryable(error, status_code):
                    self._record_failure()
                    logger.exception("LLM completion failed (non-retryable)")
                    raise LLMError("LLM completion failed") from error
                if attempt >= _MAX_RETRIES:
                    self._record_failure()
                    logger.exception(
                        "LLM completion failed after %d retries", _MAX_RETRIES
                    )
                    raise LLMError("LLM completion failed") from error
                backoff = _compute_backoff(attempt, retry_after)
                if time.monotonic() + backoff >= deadline:
                    self._record_failure()
                    logger.warning(
                        "LLM completion deadline (%.1fs) would be exceeded by the "
                        "next retry's backoff; failing now instead of retrying",
                        overall_budget,
                    )
                    raise LLMError("LLM completion timed out") from error
                logger.warning(
                    "LLM completion failed (attempt %d/%d, status=%s); "
                    "retrying in %.2fs",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    status_code if status_code is not None else "n/a",
                    backoff,
                )
                time.sleep(backoff)

        raise LLMError("LLM completion failed") from last_error

    def _circuit_is_open(self) -> bool:
        with self._circuit_lock:
            return time.monotonic() < self._circuit_open_until

    def _maybe_close_circuit(self) -> None:
        """Half-open: if the reset window has elapsed, clear failure count."""
        with self._circuit_lock:
            if self._circuit_open_until and time.monotonic() >= self._circuit_open_until:
                if self._consecutive_failures > 0:
                    logger.info(
                        "Groq circuit breaker resetting after %.1fs cool-down",
                        _CIRCUIT_RESET_SECONDS,
                    )
                self._consecutive_failures = 0
                self._circuit_open_until = 0.0

    def _record_success(self) -> None:
        with self._circuit_lock:
            self._consecutive_failures = 0

    def _record_failure(self) -> None:
        with self._circuit_lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= _CIRCUIT_FAILURE_THRESHOLD:
                self._circuit_open_until = time.monotonic() + _CIRCUIT_RESET_SECONDS
                logger.error(
                    "Groq circuit breaker tripped after %d consecutive failures; "
                    "open for %.1fs",
                    self._consecutive_failures,
                    _CIRCUIT_RESET_SECONDS,
                )


def _extract_retry_after_and_status(error: BaseException) -> tuple[float | None, int | None]:
    """Pull a ``Retry-After`` hint and HTTP status from a groq/httpx error.

    Best-effort — groq SDK errors expose ``.status_code`` and a
    ``.response.headers`` dict on rate-limit errors but not consistently
    on every failure type. Any attribute lookup failure yields ``(None, None)``
    so the caller falls back to plain exponential backoff.
    """
    status: int | None = getattr(error, "status_code", None)
    retry_after: float | None = None
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers is not None:
        # Try both lowercase and title-case header names for compatibility
        # with different SDK versions.
        try:
            raw = headers.get("retry-after") or headers.get("Retry-After")
        except (AttributeError, TypeError):
            # Headers dict doesn't support .get() in some SDK versions
            raw = None
        if raw is not None:
            try:
                # Retry-After is a delta-seconds value per RFC 7231; the
                # HTTP-date form is rare on rate-limit responses, so we
                # only handle the numeric case.
                retry_after = float(raw)
            except (TypeError, ValueError):
                retry_after = None
    return retry_after, status


def _is_retryable(error: BaseException, status_code: int | None) -> bool:
    """Decide whether to retry a given exception.

    Retryable:
    - HTTP 429 (rate-limited)
    - HTTP 5xx (server-side)
    - Connection / timeout errors (status_code is None and the underlying
      exception is from httpx or the standard socket library).
    """
    if status_code in _RETRYABLE_STATUS_CODES:
        return True
    # A non-retryable HTTP status (e.g. 4xx other than 429) suppresses
    # the module-based fallback below — a 401/403/404-shaped error
    # that's also a "groq" exception is still a client bug, not a
    # transient provider hiccup, and must not be retried.
    if status_code is not None:
        return False
    # Bare connection / timeout issues have no status code but are
    # transient. We duck-type on the exception module name to avoid
    # importing httpx at module scope.
    module = getattr(type(error), "__module__", "") or ""
    if module.startswith("httpx") or module.startswith("groq") or module.startswith(
        ("httpcore", "anyio")
    ):
        return True
    # Last-ditch: connection reset / timeout messages.
    msg = str(error).lower()
    if "timeout" in msg or "connection" in msg or "reset" in msg:
        return True
    return False


def _compute_backoff(attempt: int, retry_after: float | None) -> float:
    """Capped exponential backoff with jitter, honoring ``Retry-After``."""
    if retry_after is not None and retry_after > 0:
        # Honor upstream hint but cap so we don't sleep forever. Uses a
        # larger cap than the no-hint exponential path below, since a
        # real Retry-After value means the provider told us exactly how
        # long it needs — clamping it to the same small cap as blind
        # exponential backoff would defeat the hint and burn retries
        # while still rate-limited.
        return min(retry_after, _MAX_RETRY_AFTER_SECONDS)
    # Jittered exponential: 0.5s, ~1s, ~2s with ±50% jitter, capped.
    base = min(_BASE_BACKOFF_SECONDS * (2**attempt), _MAX_BACKOFF_SECONDS)
    return random.uniform(base * 0.5, base)


# Singleton instance for dependency injection
groq_client = GroqClient()
