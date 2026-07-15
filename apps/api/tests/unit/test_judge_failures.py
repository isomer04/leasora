"""Unit tests for offline judge failure handling.

Mirrors the runtime ``services/eval/judges.py`` fail-safe pattern: when
the judge LLM call fails or returns bad JSON, the verdict is marked with
``_judge_unavailable=True`` so the eval runner can distinguish a broken
judge from a uniformly-bad model.
"""

import json

from leasora_api.core.exceptions import LLMError
from leasora_api.services.eval.judge import (
    answer_quality_score,
    judge_answer,
)


class _FakeLLMClient:
    """Stand-in LLMClient returning a fixed response."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, prompt: str, temperature: float = 0.7) -> str:
        return self._response


class _RaisingLLMClient:
    """Stand-in LLMClient that always raises (LLMError)."""

    def complete(self, prompt: str, temperature: float = 0.7) -> str:
        raise LLMError("LLM unavailable")


class _RaisingRuntimeClient:
    """Stand-in LLMClient that raises a non-LLMError exception."""

    def complete(self, prompt: str, temperature: float = 0.7) -> str:
        raise RuntimeError("network down")


def test_judge_answer_success_returns_full_dimensions_without_unavailable_flag():
    client = _FakeLLMClient(json.dumps({"faithfulness": 0.9, "correctness": 0.8, "relevance": 0.7}))
    verdict = judge_answer(
        question="q",
        context="c",
        generated_answer="a",
        reference_answer="r",
        llm_client=client,
    )
    assert verdict["faithfulness"] == 0.9
    assert verdict["correctness"] == 0.8
    assert verdict["relevance"] == 0.7
    assert verdict["_judge_unavailable"] is False


def test_judge_answer_marks_unavailable_when_llm_raises():
    client = _RaisingLLMClient()
    verdict = judge_answer("q", "c", "a", "r", llm_client=client)
    assert verdict["_judge_unavailable"] is True
    # Default zero scores are returned on failure so the runner can still
    # aggregate, but the flag tells the runner to exclude this verdict.
    assert verdict["faithfulness"] == 0.0
    assert verdict["correctness"] == 0.0
    assert verdict["relevance"] == 0.0


def test_judge_answer_marks_unavailable_on_bad_json():
    client = _FakeLLMClient("not-json-at-all")
    verdict = judge_answer("q", "c", "a", "r", llm_client=client)
    assert verdict["_judge_unavailable"] is True


def test_judge_answer_marks_unavailable_on_code_fenced_bad_json():
    client = _FakeLLMClient("```json\nnot-valid\n```")
    verdict = judge_answer("q", "c", "a", "r", llm_client=client)
    assert verdict["_judge_unavailable"] is True


def test_answer_quality_score_ignores_unavailable_flag():
    """The mean must not include the _judge_unavailable key, only the dimensions."""
    verdict = {
        "faithfulness": 0.9,
        "correctness": 0.6,
        "relevance": 0.3,
        "_judge_unavailable": True,
    }
    # (0.9 + 0.6 + 0.3) / 3 = 0.6
    assert answer_quality_score(verdict) == 0.6


def test_answer_quality_score_default_for_failure_verdict_is_zero():
    verdict = {
        "faithfulness": 0.0,
        "correctness": 0.0,
        "relevance": 0.0,
        "_judge_unavailable": True,
    }
    assert answer_quality_score(verdict) == 0.0
