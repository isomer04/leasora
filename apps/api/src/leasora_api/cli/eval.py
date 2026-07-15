"""CLI subcommand for running the retrieval/answer-quality eval harness.

`leasora eval` always runs the fast retrieval-only metrics (MRR, recall@k,
precision@k, refusal accuracy). Pass ``--full`` to also run the LLM-as-judge
answer-quality score (requires a working Groq API key; slower and non-free).

Exit code: 0 on full success, 1 if any LLM-as-judge call failed during a
``--full`` run (so a broken judge can't silently produce a 0.0 baseline
that looks like a uniformly-bad model).
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from leasora_api.services.eval.runner import (
    DEFAULT_GOLDEN_DATASET,
    run_answer_quality_eval,
    run_privacy_audit_eval,
    run_retrieval_eval,
)

DEFAULT_RESULTS_PATH = Path(__file__).resolve().parents[3] / "tests" / "evals" / "baseline.json"


def run(argv: list[str] | None = None) -> int:
    """Eval subcommand: `leasora eval [--full] [--out PATH]`"""
    parser = argparse.ArgumentParser(
        prog="leasora eval",
        description="Run the retrieval/answer-quality evaluation harness over the golden dataset.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run the LLM-as-judge answer-quality score (requires a Groq API key)",
    )
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="Apply the cross-encoder reranker on top of retrieval",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Fuse dense retrieval with a BM25 lexical index",
    )
    parser.add_argument(
        "--compare-rerank",
        action="store_true",
        help="Run retrieval eval twice (dense-only vs reranked) and print both",
    )
    parser.add_argument(
        "--compare-hybrid",
        action="store_true",
        help="Run retrieval eval for dense / hybrid / hybrid+rerank and print all three",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_RESULTS_PATH),
        help="Path to write the results JSON (default: tests/evals/baseline.json)",
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_RESULTS_PATH),
        help=(
            "Path to a prior results JSON to compare against. When the file "
            "exists and contains matching retrieval/answer-quality metrics, "
            "the runner prints a diff and exits non-zero if any metric "
            "regresses beyond ``--regression-threshold`` percent. "
            "Defaults to tests/evals/baseline.json — i.e. the same file the "
            "run writes to, so a stale baseline is compared against itself "
            "(a no-op). For a real regression gate, point this at a checked-"
            "in snapshot before running the eval."
        ),
    )
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=5.0,
        help=(
            "Maximum allowed percentage regression on any tracked metric "
            "(MRR / recall@k / precision@k / refusal_accuracy / answer_quality) "
            "before the runner exits non-zero. Default 5%%."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Overall timeout in seconds for the eval run; aborts with a non-zero exit on overrun",
    )

    if argv is None:
        argv = sys.argv[1:]

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0

    had_failures = False
    report: dict[str, Any]

    if args.compare_rerank:
        dense_result = asyncio.run(run_retrieval_eval(DEFAULT_GOLDEN_DATASET, rerank=False))
        reranked_result = asyncio.run(run_retrieval_eval(DEFAULT_GOLDEN_DATASET, rerank=True))
        report = {
            "retrieval_dense": dense_result.to_dict(),
            "retrieval_reranked": reranked_result.to_dict(),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        print("Dense-only retrieval:")
        _print_retrieval_report(dense_result.to_dict())
        print("\nReranked retrieval:")
        _print_retrieval_report(reranked_result.to_dict())
    elif args.compare_hybrid:
        dense_result = asyncio.run(
            run_retrieval_eval(DEFAULT_GOLDEN_DATASET, rerank=False, hybrid=False)
        )
        hybrid_result = asyncio.run(
            run_retrieval_eval(DEFAULT_GOLDEN_DATASET, rerank=False, hybrid=True)
        )
        hybrid_rerank_result = asyncio.run(
            run_retrieval_eval(DEFAULT_GOLDEN_DATASET, rerank=True, hybrid=True)
        )
        report = {
            "retrieval_dense": dense_result.to_dict(),
            "retrieval_hybrid": hybrid_result.to_dict(),
            "retrieval_hybrid_rerank": hybrid_rerank_result.to_dict(),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        print("Dense-only retrieval:")
        _print_retrieval_report(dense_result.to_dict())
        print("\nHybrid (dense + BM25) retrieval:")
        _print_retrieval_report(hybrid_result.to_dict())
        print("\nHybrid + rerank retrieval:")
        _print_retrieval_report(hybrid_rerank_result.to_dict())
    else:
        retrieval_result = asyncio.run(
            run_retrieval_eval(DEFAULT_GOLDEN_DATASET, rerank=args.rerank, hybrid=args.hybrid)
        )
        report = {
            "retrieval": retrieval_result.to_dict(),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        _print_retrieval_report(retrieval_result.to_dict())

        if args.full:
            try:
                if args.timeout is not None:
                    answer_quality = asyncio.run(
                        asyncio.wait_for(
                            run_answer_quality_eval(DEFAULT_GOLDEN_DATASET),
                            timeout=args.timeout,
                        )
                    )
                else:
                    answer_quality = asyncio.run(
                        run_answer_quality_eval(DEFAULT_GOLDEN_DATASET)
                    )
            except asyncio.TimeoutError:
                print(
                    f"\nERROR: eval timed out after {args.timeout}s",
                    file=sys.stderr,
                )
                return 1

            report["answer_quality"] = answer_quality
            _print_answer_quality_report(answer_quality)
            if answer_quality.get("judge_unavailable"):
                had_failures = True
                print(
                    f"\nWARNING: {answer_quality.get('num_judge_failures', 0)}/"
                    f"{answer_quality.get('num_questions', 0)} judge calls failed; "
                    "scores exclude failed verdicts but the baseline is suspect.",
                    file=sys.stderr,
                )

            privacy_audit = run_privacy_audit_eval()
            report["privacy_audit"] = privacy_audit
            _print_privacy_audit_report(privacy_audit)

    out_path = Path(args.out)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nResults written to {out_path}")

    # Regression check: if a baseline file exists, compare per-metric and
    # exit non-zero when any tracked metric regresses beyond the threshold.
    # Skipped when the baseline path equals the output path (we just wrote
    # it) — running the diff against the file we just produced is a no-op
    # that would always "pass".
    baseline_path = Path(args.baseline)
    if baseline_path.resolve() != out_path.resolve() and baseline_path.exists():
        regressed = _compare_against_baseline(baseline_path, report, args.regression_threshold)
        if regressed:
            print(
                f"\nERROR: {len(regressed)} metric(s) regressed beyond "
                f"{args.regression_threshold:.1f}%; see diff above.",
                file=sys.stderr,
            )
            return 1
        print("\nNo metric regressed beyond threshold.")

    return 1 if had_failures else 0


_TRACKED_METRICS = (
    "mrr",
    "recall_at_k",
    "precision_at_k",
    "refusal_accuracy",
)


def _compare_against_baseline(
    baseline_path: Path, report: dict[str, Any], threshold_pct: float
) -> list[str]:
    """Diff the current eval report against a stored baseline.

    Walks ``TRACKED_METRICS`` (and the per-run retrieval/answer_quality
    sub-blocks) and prints a one-line per-metric diff. Returns the names
    of any metric that regressed beyond ``threshold_pct`` so the caller
    can surface a non-zero exit code.
    """
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(
            f"\nWARNING: could not read baseline at {baseline_path}; skipping regression check.",
            file=sys.stderr,
        )
        return []

    print("\nRegression check (current vs baseline):")
    regressed: list[str] = []
    # Top-level retrieval / answer-quality blocks
    retrieval = report.get("retrieval") or {}
    baseline_retrieval = baseline.get("retrieval") or {}
    answer_quality = report.get("answer_quality") or {}
    baseline_answer_quality = baseline.get("answer_quality") or {}
    for metric in _TRACKED_METRICS:
        current = retrieval.get(metric)
        prior = baseline_retrieval.get(metric)
        if _maybe_warn_regression(metric, current, prior, threshold_pct):
            regressed.append(f"retrieval.{metric}")
    if "answer_quality" in answer_quality and "answer_quality" in baseline_answer_quality:
        if _maybe_warn_regression(
            "answer_quality",
            answer_quality.get("answer_quality"),
            baseline_answer_quality.get("answer_quality"),
            threshold_pct,
        ):
            regressed.append("answer_quality.answer_quality")

    return regressed


def _maybe_warn_regression(
    metric: str, current: float | None, prior: float | None, threshold_pct: float
) -> bool:
    """Print a regression line for ``metric``; return True if it regressed.

    A regression is defined as a *drop* in the metric (lower is worse for
    every tracked metric here). Below ``threshold_pct`` is informational,
    at-or-above is a regression.
    """
    if current is None or prior is None:
        print(f"  {metric:18s} (no baseline or current value)")
        return False
    delta = current - prior
    pct = (delta / prior) * 100.0 if prior else 0.0
    flag = " OK"
    if pct <= -threshold_pct:
        flag = " REGRESSION"
    elif pct <= -(threshold_pct / 2.0):
        flag = " WARN"
    print(f"  {metric:18s} {prior:.3f} → {current:.3f} ({pct:+.1f}%){flag}")
    return flag == " REGRESSION"


def _print_retrieval_report(retrieval: dict[str, Any]) -> None:
    print("Retrieval metrics (overall):")
    print(f"  MRR:              {retrieval['mrr']:.3f}")
    print(f"  Recall@k:         {retrieval['recall_at_k']:.3f}")
    print(f"  Precision@k:      {retrieval['precision_at_k']:.3f}")
    print(f"  Refusal accuracy: {retrieval['refusal_accuracy']:.3f}")
    print(f"  Questions:        {retrieval['num_questions']}")

    print("Per-category:")
    for category, scores in retrieval["per_category"].items():
        print(
            f"  {category:14s} mrr={scores['mrr']:.2f} recall={scores['recall_at_k']:.2f} "
            f"precision={scores['precision_at_k']:.2f} refusal_acc={scores['refusal_accuracy']:.2f} "
            f"(n={scores['num_questions']})"
        )


def _print_answer_quality_report(aq: dict[str, Any]) -> None:
    print("\nAnswer quality (LLM-as-judge):")
    print(f"  Overall:      {aq['answer_quality']:.3f}")
    print(f"  Faithfulness: {aq['faithfulness']:.3f}")
    print(f"  Correctness:  {aq['correctness']:.3f}")
    print(f"  Relevance:    {aq['relevance']:.3f}")
    successful = aq.get("num_successful_verdicts", aq.get("num_questions", 0))
    failures = aq.get("num_judge_failures", 0)
    if failures:
        print(f"  Judge calls:   {successful} succeeded, {failures} failed (excluded from mean)")


def _print_privacy_audit_report(audit: dict[str, Any]) -> None:
    print("\nPrivacy audit (LLM-as-judge, detection only — redact_pii is the real control):")
    print(f"  Passed: {audit['passed']}/{audit['total']}")
