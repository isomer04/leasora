"""Retrieval-quality regression tests, backed by the real eval harness.

These map to the "ragas-style" retrieval metrics (context precision/recall)
using our own metric functions (services/eval/metrics.py) run against the
real golden dataset + a real ChromaDB retrieval round trip. No LLM calls, so
these stay fast and run in normal CI.
"""

from leasora_api.services.eval.runner import run_retrieval_eval

# Baseline floors from the first real measured run (see tests/evals/baseline.json).
# Regressions below these floors should be investigated, not silently lowered.
# These tests make no LLM calls (real ChromaDB + embedder only), so they stay
# in the default fast suite rather than behind the `eval` marker.
MIN_RECALL_AT_K = 0.70
MIN_PRECISION_AT_K = 0.10
MIN_MRR = 0.55
MIN_REFUSAL_ACCURACY = 0.80


async def test_context_recall_meets_baseline_floor():
    """Recall@k across the golden dataset must not regress below the measured floor."""
    result = await run_retrieval_eval()
    assert result.recall_at_k >= MIN_RECALL_AT_K, (
        f"recall@k {result.recall_at_k:.3f} below floor {MIN_RECALL_AT_K}"
    )


async def test_context_precision_meets_baseline_floor():
    """Precision@k across the golden dataset must not regress below the measured floor."""
    result = await run_retrieval_eval()
    assert result.precision_at_k >= MIN_PRECISION_AT_K, (
        f"precision@k {result.precision_at_k:.3f} below floor {MIN_PRECISION_AT_K}"
    )


async def test_mrr_meets_baseline_floor():
    """MRR across the golden dataset must not regress below the measured floor."""
    result = await run_retrieval_eval()
    assert result.mrr >= MIN_MRR, f"MRR {result.mrr:.3f} below floor {MIN_MRR}"


async def test_refusal_accuracy_meets_baseline_floor():
    """Refusal-gate accuracy across the golden dataset must not regress below the measured floor."""
    result = await run_retrieval_eval()
    assert result.refusal_accuracy >= MIN_REFUSAL_ACCURACY, (
        f"refusal accuracy {result.refusal_accuracy:.3f} below floor {MIN_REFUSAL_ACCURACY}"
    )
