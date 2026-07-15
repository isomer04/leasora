"""Evaluation harness: run the golden dataset through retrieval (+ optionally
the full RAG answer flow) and compute real metrics.

Two modes:
- ``run_retrieval_eval``: fast, no LLM calls. Ingests the golden fixture into
  an isolated temp ChromaDB dir, retrieves for every golden question, and
  computes MRR / recall@k / precision@k / refusal accuracy.
- ``run_full_eval``: also generates answers via ``RAGQueryService`` and scores
  them with the LLM-as-judge for an answer-quality score. Slower and requires
  a working Groq API key; kept separate so the fast path stays usable in CI
  without real credentials.
"""

import asyncio
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from leasora_api.core.config import get_settings
from leasora_api.services.eval.golden import GOLDEN_DIR, load_golden_dataset
from leasora_api.services.eval.judge import answer_quality_score, judge_answer
from leasora_api.services.eval.judges import audit_for_pii
from leasora_api.services.eval.metrics import (
    mean_precision_at_k,
    mean_recall_at_k,
    mrr,
    refusal_accuracy,
)
from leasora_api.services.ingest.pipeline import IngestPipeline
from leasora_api.services.rag.query_service import RAGQueryService
from leasora_api.services.retrieval.bm25_index import BM25Index, fuse_results
from leasora_api.services.retrieval.embedder import Embedder
from leasora_api.services.retrieval.reranker import Reranker
from leasora_api.services.retrieval.vector_store import ChromaStore

GOLDEN_LEASE_ID = "golden-demo-lease"


def _find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` until a ``.git`` directory marks the repo root.

    Avoids hardcoded ``parents[N]`` arithmetic, which breaks silently (or
    with a baffling ``FileNotFoundError``) if this module ever moves.
    """
    current = start
    for _ in range(10):
        if (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError(f"Could not find repo root (.git) walking up from {start}")


def _find_api_root(start: Path) -> Path:
    """Walk up from ``start`` until the ``apps/api`` package root (pyproject.toml)."""
    current = start
    for _ in range(10):
        if (current / "pyproject.toml").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError(f"Could not find apps/api root (pyproject.toml) walking up from {start}")


_MODULE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _find_repo_root(_MODULE_DIR)
_API_ROOT = _find_api_root(_MODULE_DIR)
DEFAULT_GOLDEN_DATASET = _API_ROOT / "tests" / "evals" / "golden" / "questions.jsonl"
DEFAULT_DEMO_LEASE_PDF = _REPO_ROOT / "data" / "test-fixtures" / "demo_lease.pdf"


@dataclass
class RetrievalEvalResult:
    """Aggregate + per-category retrieval metrics for a golden dataset run."""

    mrr: float
    recall_at_k: float
    precision_at_k: float
    refusal_accuracy: float
    num_questions: int
    per_category: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mrr": self.mrr,
            "recall_at_k": self.recall_at_k,
            "precision_at_k": self.precision_at_k,
            "refusal_accuracy": self.refusal_accuracy,
            "num_questions": self.num_questions,
            "per_category": self.per_category,
        }


async def _ingest_golden_fixture(persist_dir: str) -> tuple[ChromaStore, Embedder]:
    """Ingest the demo lease fixture into an isolated ChromaDB directory."""
    if not DEFAULT_DEMO_LEASE_PDF.exists():
        raise FileNotFoundError(
            f"Golden fixture PDF not found at {DEFAULT_DEMO_LEASE_PDF}. "
            "The eval harness requires data/test-fixtures/demo_lease.pdf."
        )

    store = ChromaStore(persist_dir=persist_dir, collection_name=GOLDEN_LEASE_ID)
    embedder = Embedder()
    pipeline = IngestPipeline(embedder_=embedder, vector_store=store)
    await pipeline.ingest(str(DEFAULT_DEMO_LEASE_PDF), lease_id=GOLDEN_LEASE_ID)
    return store, embedder


async def run_retrieval_eval(
    golden_path: str | Path = DEFAULT_GOLDEN_DATASET,
    persist_dir: str | None = None,
    rerank: bool = False,
    hybrid: bool = False,
) -> RetrievalEvalResult:
    """Run the fast retrieval-only eval over the golden dataset.

    Args:
        golden_path: Path to the golden JSONL dataset.
        persist_dir: Optional ChromaDB persist directory. Defaults to a fresh
            temp directory so runs are isolated and repeatable.
        rerank: If True, apply the cross-encoder reranker on top of (dense or
            hybrid) retrieval, so reranked vs non-reranked can be compared
            with the same golden dataset.
        hybrid: If True, fuse dense retrieval with a BM25 lexical index over
            the golden fixture's chunks (see ``services/retrieval/bm25_index.py``),
            so hybrid vs dense-only can be compared with the same golden dataset.

    Returns:
        Aggregate and per-category retrieval metrics.
    """
    import tempfile

    settings = get_settings()
    questions = load_golden_dataset(golden_path)
    reranker = Reranker() if rerank else None

    # ignore_cleanup_errors: ChromaDB's persistent client (sqlite + hnsw index
    # files) can keep file handles open on Windows past the `with` block,
    # which would otherwise raise PermissionError during teardown.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        store, embedder = await _ingest_golden_fixture(persist_dir or tmp_dir)

        rankings: list[tuple[list[str], set[str]]] = []
        refusal_predictions: list[tuple[bool, bool]] = []
        per_category_rankings: dict[str, list[tuple[list[str], set[str]]]] = {}
        per_category_refusals: dict[str, list[tuple[bool, bool]]] = {}

        top_k = settings.retrieval_top_k
        dense_top_k = settings.rerank_top_n if reranker else top_k

        bm25_index = None
        if hybrid:
            all_chunks = await store.get_by_lease(GOLDEN_LEASE_ID)
            bm25_index = BM25Index()
            await bm25_index.abuild(all_chunks)

        for question in questions:
            query_vector = await embedder.aembed_query(question.question)
            results = await store.query(
                embedding=query_vector,
                top_k=dense_top_k,
                where={"lease_id": {"$eq": GOLDEN_LEASE_ID}},
            )
            if bm25_index is not None:
                bm25_results = await bm25_index.asearch(question.question, top_k=dense_top_k)
                results = fuse_results(
                    results, bm25_results, alpha=settings.hybrid_alpha, top_k=dense_top_k
                )
            if reranker and results:
                results = await reranker.arerank(question.question, results, top_k=top_k)

            retrieved_ids = [r["id"] for r in results]
            min_distance = min((r["distance"] for r in results), default=1.0)
            did_refuse = not results or min_distance > settings.refusal_threshold

            relevant = set(question.relevant_clause_ids)
            rankings.append((retrieved_ids, relevant))
            refusal_predictions.append((question.should_refuse, did_refuse))

            per_category_rankings.setdefault(question.category, []).append(
                (retrieved_ids, relevant)
            )
            per_category_refusals.setdefault(question.category, []).append(
                (question.should_refuse, did_refuse)
            )

        per_category: dict[str, dict[str, float]] = {}
        for category, cat_rankings in per_category_rankings.items():
            per_category[category] = {
                "mrr": mrr(cat_rankings),
                "recall_at_k": mean_recall_at_k(cat_rankings, top_k),
                "precision_at_k": mean_precision_at_k(cat_rankings, top_k),
                "refusal_accuracy": refusal_accuracy(per_category_refusals[category]),
                "num_questions": len(cat_rankings),
            }

        return RetrievalEvalResult(
            mrr=mrr(rankings),
            recall_at_k=mean_recall_at_k(rankings, top_k),
            precision_at_k=mean_precision_at_k(rankings, top_k),
            refusal_accuracy=refusal_accuracy(refusal_predictions),
            num_questions=len(questions),
            per_category=per_category,
        )


async def run_answer_quality_eval(
    golden_path: str | Path = DEFAULT_GOLDEN_DATASET,
) -> dict[str, Any]:
    """Run the full RAG flow + LLM judge over the golden dataset's answerable questions.

    Skips ``should_refuse`` questions (no reference answer to judge against).
    Requires a working Groq API key.

    Returns:
        Dict with ``answer_quality`` (mean of faithfulness/correctness/relevance
        across successful verdicts only — failed-judge verdicts are excluded
        from the mean to keep a broken judge from dragging the score to 0.0),
        the individual dimension means, and a ``judge_unavailable`` /
        ``num_judge_failures`` pair so a fully-broken judge is distinguishable
        from a uniformly-bad model in the baseline JSON.
    """
    import tempfile

    questions = [q for q in load_golden_dataset(golden_path) if not q.should_refuse]

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        store, embedder = await _ingest_golden_fixture(tmp_dir)
        service = RAGQueryService(
            embedder_=embedder,
            vector_store=store,
        )

        successful_verdicts: list[dict[str, float]] = []
        judge_failures = 0
        for question in questions:
            response = await service.answer_question(GOLDEN_LEASE_ID, question.question)
            context = "\n\n".join(source.excerpt for source in response.sources)
            verdict = judge_answer(
                question=question.question,
                context=context,
                generated_answer=response.answer,
                reference_answer=question.reference_answer,
            )
            if verdict.get("_judge_unavailable"):
                judge_failures += 1
            else:
                # Narrow to dict[str, float] for the mean computations below —
                # the runtime verdict is a plain mapping of dimension → score,
                # and the type-narrowing here lets statistics.mean accept
                # these without an object-vs-numeric cast at the call site.
                narrowed: dict[str, float] = {
                    k: float(v) for k, v in verdict.items() if isinstance(v, (int, float))
                }
                successful_verdicts.append(narrowed)

        if not successful_verdicts:
            # All judges failed or no answerable questions. Report zeros
            # (mirroring the historical baseline shape) but flag it so the
            # CLI surfaces the failure.
            return {
                "answer_quality": 0.0,
                "faithfulness": 0.0,
                "correctness": 0.0,
                "relevance": 0.0,
                "num_questions": len(questions),
                "num_successful_verdicts": 0,
                "num_judge_failures": judge_failures,
                "judge_unavailable": judge_failures > 0,
            }

        return {
            "answer_quality": statistics.mean(
                answer_quality_score(cast(dict[str, object], v)) for v in successful_verdicts
            ),
            "faithfulness": statistics.mean(v["faithfulness"] for v in successful_verdicts),
            "correctness": statistics.mean(v["correctness"] for v in successful_verdicts),
            "relevance": statistics.mean(v["relevance"] for v in successful_verdicts),
            "num_questions": len(questions),
            "num_successful_verdicts": len(successful_verdicts),
            "num_judge_failures": judge_failures,
            "judge_unavailable": judge_failures > 0,
        }


def run_retrieval_eval_sync(
    golden_path: str | Path = DEFAULT_GOLDEN_DATASET,
) -> RetrievalEvalResult:
    """Synchronous convenience wrapper around :func:`run_retrieval_eval`."""
    return asyncio.run(run_retrieval_eval(golden_path))


def run_privacy_audit_eval() -> dict[str, Any]:
    """Run the privacy auditor over the labeled PII fixture set.

    Offline half of the data-privacy guardrail: audits each fixture payload
    (real Groq calls) and reports pass/fail against the labeled expectations
    in ``tests/evals/golden/pii_fixtures.jsonl``.

    Returns:
        Dict with ``passed``, ``failed``, ``total``, and per-fixture detail.
        A fixture "passes" if the auditor's ``has_pii`` determination is
        consistent with whether the fixture has any expected PII category
        (regex or LLM) at all.
    """
    import json

    fixtures_path = GOLDEN_DIR / "pii_fixtures.jsonl"
    fixtures = []
    with fixtures_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                fixtures.append(json.loads(line))

    results = []
    passed = 0
    for fixture in fixtures:
        payload = fixture["payload"]
        expects_pii = bool(
            fixture["expected_regex_categories"] or fixture["expected_llm_categories"]
        )
        has_pii, findings = audit_for_pii(payload)
        # A fixture with no expected PII at all should not be flagged; a
        # fixture with expected PII (regex or LLM-detectable) should be.
        fixture_passed = has_pii == expects_pii if expects_pii else not has_pii or not findings
        if fixture_passed:
            passed += 1
        results.append(
            {
                "expects_pii": expects_pii,
                "has_pii": has_pii,
                "finding_count": len(findings),
                "passed": fixture_passed,
            }
        )

    return {
        "passed": passed,
        "failed": len(fixtures) - passed,
        "total": len(fixtures),
        "results": results,
    }
