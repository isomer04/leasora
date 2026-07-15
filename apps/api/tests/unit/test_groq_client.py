from unittest.mock import MagicMock

import pytest

from leasora_api.services.llm.groq_client import GroqClient


def _fake_groq_response(content: str, prompt_tokens: int, completion_tokens: int) -> MagicMock:
    response = MagicMock()
    response.choices[0].message.content = content
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = prompt_tokens + completion_tokens
    return response


class TestGroqClientBasics:
    """Tests for basic Groq client functionality."""

    def test_complete_with_usage_returns_text_and_token_usage(self):
        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.return_value = _fake_groq_response(
            "the answer", prompt_tokens=10, completion_tokens=5
        )

        text, usage = client.complete_with_usage("a prompt")

        assert text == "the answer"
        assert usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    def test_complete_delegates_to_complete_with_usage(self):
        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.return_value = _fake_groq_response(
            "hello", prompt_tokens=1, completion_tokens=1
        )

        text = client.complete("a prompt")

        assert text == "hello"

    def test_complete_with_usage_handles_missing_usage_gracefully(self):
        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        response = MagicMock()
        response.choices[0].message.content = "answer"
        response.usage = None
        client._groq_client.chat.completions.create.return_value = response

        text, usage = client.complete_with_usage("a prompt")

        assert text == "answer"
        assert usage == {}


def _fake_json_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices[0].message.content = content
    response.usage.prompt_tokens = 5
    response.usage.completion_tokens = 5
    response.usage.total_tokens = 10
    return response


class TestStructuredCompletion:
    """Tests for structured (JSON) completion."""

    def test_parses_valid_json(self):
        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.return_value = _fake_json_response(
            '{"answer": "hi", "signal": "standard"}'
        )

        parsed, usage = client.complete_structured("a prompt")

        assert parsed == {"answer": "hi", "signal": "standard"}
        assert usage["total_tokens"] == 10

    def test_strips_code_fences(self):
        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.return_value = _fake_json_response(
            '```json\n{"answer": "hi"}\n```'
        )

        parsed, _usage = client.complete_structured("a prompt")

        assert parsed == {"answer": "hi"}

    def test_raises_llm_error_on_invalid_json(self):
        from leasora_api.core.exceptions import LLMError

        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.return_value = _fake_json_response(
            "not json at all"
        )

        with pytest.raises(LLMError):
            client.complete_structured("a prompt")

    def test_raises_llm_error_on_non_object_json(self):
        from leasora_api.core.exceptions import LLMError

        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.return_value = _fake_json_response("[1, 2, 3]")

        with pytest.raises(LLMError):
            client.complete_structured("a prompt")

    def test_uses_json_object_response_format(self):
        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.return_value = _fake_json_response(
            '{"answer": "hi"}'
        )

        client.complete_structured("a prompt")

        _, kwargs = client._groq_client.chat.completions.create.call_args
        assert kwargs["response_format"] == {"type": "json_object"}


class TestRetryBehavior:
    """Tests for retry and backoff behavior on retryable errors."""

    def test_retries_on_retryable_status_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """429 followed by success should retry, not surface the error."""
        from leasora_api.services.llm import groq_client as module

        sleeps: list[float] = []

        class _FakeRateLimitError(Exception):
            status_code = 429

        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"

        # First call raises, second returns a normal response.
        success_response = _fake_groq_response("ok", prompt_tokens=1, completion_tokens=1)
        client._groq_client.chat.completions.create.side_effect = [
            _FakeRateLimitError("rate limited"),
            success_response,
        ]

        monkeypatch.setattr(module.time, "sleep", lambda s: sleeps.append(s))

        text, usage = client._call_groq("p", 0.3)

        assert text.choices[0].message.content == "ok"
        # Two attempts: original + one retry.
        assert client._groq_client.chat.completions.create.call_count == 2
        # Sleep happened with backoff > 0.
        assert sleeps and sleeps[0] > 0

    def test_retries_share_one_deadline_instead_of_a_fresh_budget_each(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A caller's `timeout` bounds the WHOLE call, not each retry.

        Previously every attempt got its own full `timeout`-sized SDK-level
        timeout, so MAX_ATTEMPTS retries could take up to ~4x the caller's
        intended deadline. Simulate wall-clock time advancing past the
        deadline between attempts and assert the retry loop stops instead
        of starting another attempt with a fresh budget.
        """
        from leasora_api.core.exceptions import LLMError
        from leasora_api.services.llm import groq_client as module

        class _FakeRateLimitError(Exception):
            status_code = 429

        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.side_effect = _FakeRateLimitError(
            "rate limited"
        )

        clock = {"now": 1000.0}
        monkeypatch.setattr(module.time, "monotonic", lambda: clock["now"])

        def _fake_sleep(seconds: float) -> None:
            clock["now"] += seconds

        monkeypatch.setattr(module.time, "sleep", _fake_sleep)
        # Deterministic backoff (no jitter) so the deadline math is exact:
        # bigger than the 1.0s overall deadline, so it must trip the
        # "next retry's backoff would exceed the deadline" branch on the
        # very first failure instead of sleeping and retrying.
        monkeypatch.setattr(module, "_compute_backoff", lambda attempt, retry_after: 2.0)

        with pytest.raises(LLMError):
            client._call_groq("p", 0.3, timeout=1.0)

        # Must not have attempted all MAX_ATTEMPTS — the shared deadline
        # should have cut the loop short after the first failed attempt.
        assert client._groq_client.chat.completions.create.call_count == 1

    def test_per_attempt_sdk_timeout_shrinks_toward_the_shared_deadline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each retry's SDK-level timeout is the *remaining* budget, not a
        fresh copy of the original `timeout` — otherwise a slow-but-still-
        erroring attempt could itself run long enough to blow the deadline
        the caller is relying on."""
        from leasora_api.services.llm import groq_client as module

        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.return_value = _fake_groq_response(
            "ok", prompt_tokens=1, completion_tokens=1
        )

        clock = {"now": 1000.0}
        monkeypatch.setattr(module.time, "monotonic", lambda: clock["now"])

        client._call_groq("p", 0.3, timeout=10.0)

        _, kwargs = client._groq_client.chat.completions.create.call_args
        assert kwargs["timeout"] == pytest.approx(10.0)

    def test_does_not_retry_on_non_retryable_status(self) -> None:
        """401 (auth) is a client bug — must surface immediately, no retries."""
        from leasora_api.core.exceptions import LLMError

        class _FakeAuthError(Exception):
            status_code = 401

        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"
        client._groq_client.chat.completions.create.side_effect = _FakeAuthError("bad key")

        with pytest.raises(LLMError):
            client._call_groq("p", 0.3)

        assert client._groq_client.chat.completions.create.call_count == 1


class TestCircuitBreaker:
    """Tests for circuit breaker behavior on repeated failures."""

    def test_trips_circuit_after_repeated_failures(self) -> None:
        """After N consecutive failures the circuit opens and rejects calls fast."""
        from leasora_api.services.llm import groq_client as module

        class _FakeRateLimitError(Exception):
            status_code = 429

        class _ZeroSleep:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, _seconds: float) -> None:
                self.calls += 1

        sleeps = _ZeroSleep()

        client = GroqClient()
        client._groq_client = MagicMock()
        client._model_name = "test-model"

        # First call: exhausts all retries (4 attempts: 1 + 3 retries).
        client._groq_client.chat.completions.create.side_effect = _FakeRateLimitError("429")
        saved_sleep = module.time.sleep
        module.time.sleep = sleeps
        try:
            from leasora_api.core.exceptions import LLMError

            with pytest.raises(LLMError):
                client._call_groq("p", 0.3)
        finally:
            module.time.sleep = saved_sleep

        # Circuit counter increments on each exhausted retry. Force the
        # threshold by directly incrementing the counter to (threshold - 1)
        # so the NEXT call exhausts retries and bumps us over.
        client._consecutive_failures = module._CIRCUIT_FAILURE_THRESHOLD - 1
        client._groq_client.chat.completions.create.side_effect = _FakeRateLimitError("429")
        saved_sleep = module.time.sleep
        module.time.sleep = sleeps
        try:
            from leasora_api.core.exceptions import LLMError

            with pytest.raises(LLMError):
                client._call_groq("p", 0.3)
        finally:
            module.time.sleep = saved_sleep

        # Now the circuit is open. The next call should fail-fast with
        # `_CircuitOpenError` (subclass of LLMError) BEFORE hitting the SDK.
        from leasora_api.core.exceptions import LLMError

        prev_count = client._groq_client.chat.completions.create.call_count
        with pytest.raises(LLMError):  # _CircuitOpenError is a subclass of LLMError
            client._call_groq("p", 0.3)
        # SDK was NOT consulted again — fast-fail in the circuit check.
        assert client._groq_client.chat.completions.create.call_count == prev_count
