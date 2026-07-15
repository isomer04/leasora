"""Unit tests for the LLM-as-judge guardrails (mocked LLM client)."""

from leasora_api.services.eval.judges import audit_for_pii, check_answer_grounded


class _FakeLLMClient:
    """Stand-in LLMClient returning a fixed response."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, prompt: str, temperature: float = 0.7) -> str:
        return self._response

    def model(self) -> str:  # pragma: no cover - not used by these tests
        return "fake-model"


class _RaisingLLMClient:
    """Stand-in LLMClient that always raises, to test fail-safe behavior."""

    def complete(self, prompt: str, temperature: float = 0.7) -> str:
        raise RuntimeError("LLM unavailable")


class TestCheckAnswerGrounded:
    """Tests for the check_answer_grounded judge function."""

    def test_returns_true_when_judge_says_grounded(self):
        client = _FakeLLMClient('{"grounded": true, "unsupported_claims": []}')

        grounded, unsupported = check_answer_grounded("context", "answer", llm_client=client)

        assert grounded is True
        assert unsupported == []

    def test_returns_false_with_unsupported_claims(self):
        client = _FakeLLMClient(
            '{"grounded": false, "unsupported_claims": ["claim about pet deposit"]}'
        )

        grounded, unsupported = check_answer_grounded("context", "answer", llm_client=client)

        assert grounded is False
        assert unsupported == ["claim about pet deposit"]

    def test_strips_code_fences(self):
        client = _FakeLLMClient('```json\n{"grounded": true, "unsupported_claims": []}\n```')

        grounded, _ = check_answer_grounded("context", "answer", llm_client=client)

        assert grounded is True

    def test_fails_safe_on_llm_error(self):
        grounded, unsupported = check_answer_grounded(
            "context", "answer", llm_client=_RaisingLLMClient()
        )

        assert grounded is False
        assert unsupported == ["judge_unavailable"]

    def test_fails_safe_on_invalid_json(self):
        client = _FakeLLMClient("not json at all")

        grounded, unsupported = check_answer_grounded("context", "answer", llm_client=client)

        assert grounded is False
        assert unsupported == ["judge_unavailable"]


class TestAuditForPII:
    """Tests for the audit_for_pii judge function."""

    def test_clean_payload(self):
        client = _FakeLLMClient('{"has_pii": false, "findings": []}')

        has_pii, findings = audit_for_pii("Rent is due monthly.", llm_client=client)

        assert has_pii is False
        assert findings == []

    def test_reports_categories_not_raw_values(self):
        client = _FakeLLMClient(
            '{"has_pii": true, "findings": '
            '[{"category": "full_name", "location": "tenant field"}]}'
        )

        has_pii, findings = audit_for_pii("some payload", llm_client=client)

        assert has_pii is True
        assert findings == [{"category": "full_name", "location": "tenant field"}]

    def test_fails_safe_on_llm_error(self):
        has_pii, findings = audit_for_pii("payload", llm_client=_RaisingLLMClient())

        assert has_pii is True
        assert findings == [{"category": "audit_unavailable", "location": "unknown"}]

    def test_fails_safe_on_invalid_json(self):
        client = _FakeLLMClient("garbage response")

        has_pii, findings = audit_for_pii("payload", llm_client=client)

        assert has_pii is True
        assert findings == [{"category": "audit_unavailable", "location": "unknown"}]

    def test_redacts_known_patterns_before_prompting(self):
        """The prompt sent to the judge must never contain a regex-catchable SSN."""
        captured_prompts: list[str] = []

        class _CapturingClient:
            def complete(self, prompt: str, temperature: float = 0.7) -> str:
                captured_prompts.append(prompt)
                return '{"has_pii": false, "findings": []}'

        audit_for_pii("Tenant SSN: 123-45-6789", llm_client=_CapturingClient())

        assert captured_prompts
        assert "123-45-6789" not in captured_prompts[0]
