"""Answer-quality regression tests, backed by the real LLM-as-judge.

These run the full RAG answer flow + LLM judge over the golden dataset's
answerable questions. They make real Groq API calls, so they are kept behind
the `eval` marker and excluded from the default fast test run:

    uv run pytest -m eval
"""

import pytest

from leasora_api.services.eval.runner import run_answer_quality_eval

# Baseline floors from the first measured run.
# floors have wide confidence intervals and should be treated as guardrails
# against gross regressions, not tight SLAs.
MIN_FAITHFULNESS = 0.60
MIN_CORRECTNESS = 0.60
MIN_RELEVANCE = 0.60


@pytest.mark.eval
async def test_faithfulness_meets_baseline_floor():
    """Generated answers must stay grounded in retrieved context."""
    result = await run_answer_quality_eval()
    assert result["faithfulness"] >= MIN_FAITHFULNESS, (
        f"faithfulness {result['faithfulness']:.3f} below floor {MIN_FAITHFULNESS}"
    )


@pytest.mark.eval
async def test_correctness_meets_baseline_floor():
    """Generated answers must match the reference answer's meaning."""
    result = await run_answer_quality_eval()
    assert result["correctness"] >= MIN_CORRECTNESS, (
        f"correctness {result['correctness']:.3f} below floor {MIN_CORRECTNESS}"
    )


@pytest.mark.eval
async def test_relevance_meets_baseline_floor():
    """Generated answers must directly address the question."""
    result = await run_answer_quality_eval()
    assert result["relevance"] >= MIN_RELEVANCE, (
        f"relevance {result['relevance']:.3f} below floor {MIN_RELEVANCE}"
    )
