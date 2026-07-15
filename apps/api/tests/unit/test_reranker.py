import math

import pytest

from leasora_api.services.retrieval.reranker import Reranker, _sigmoid
from leasora_api.services.retrieval.vector_store import RetrievalResult


def _make_candidate(id_: str, text: str, distance: float) -> RetrievalResult:
    return RetrievalResult(
        id=id_,
        text=text,
        metadata={"source": "lease.pdf", "page": 1, "clause_type": "other"},
        distance=distance,
    )


class _FakeCrossEncoder:
    """Stand-in for CrossEncoder that scores by a fixed lookup table."""

    def __init__(self, scores: list[float]) -> None:
        self._scores = scores

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return self._scores


def test_reranker_does_not_load_model_on_construction():
    reranker = Reranker(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
    assert reranker._model is None


def test_rerank_empty_candidates_returns_empty_list():
    reranker = Reranker(model_name="fake-model")
    assert reranker.rerank("query", [], top_k=5) == []


def test_rerank_reorders_by_score_descending():
    reranker = Reranker(model_name="fake-model")
    candidates = [
        _make_candidate("low-score", "irrelevant text", distance=0.1),
        _make_candidate("high-score", "relevant text", distance=0.5),
    ]
    # First candidate scores low, second scores high -> order should flip.
    reranker._model = _FakeCrossEncoder([0.1, 0.9])

    reranked = reranker.rerank("query", candidates, top_k=2)

    assert [r["id"] for r in reranked] == ["high-score", "low-score"]


def test_rerank_respects_top_k():
    reranker = Reranker(model_name="fake-model")
    candidates = [
        _make_candidate("a", "text a", distance=0.1),
        _make_candidate("b", "text b", distance=0.2),
        _make_candidate("c", "text c", distance=0.3),
    ]
    reranker._model = _FakeCrossEncoder([0.5, 0.9, 0.1])

    reranked = reranker.rerank("query", candidates, top_k=2)

    assert len(reranked) == 2
    assert [r["id"] for r in reranked] == ["b", "a"]


def test_rerank_updates_distance_from_score():
    reranker = Reranker(model_name="fake-model")
    candidates = [_make_candidate("a", "text a", distance=0.99)]
    reranker._model = _FakeCrossEncoder([0.8])

    reranked = reranker.rerank("query", candidates, top_k=1)

    assert reranked[0]["distance"] == 1.0 - _sigmoid(0.8)


def test_rerank_calibrates_raw_logits_into_unit_interval():
    """Cross-encoder logits (e.g. ms-marco's ~[-11, 11] range) must map into
    [0, 1] via sigmoid, not pass through `1 - score` directly, or distance
    goes negative/huge and confidence (`1 - distance`) saturates/clips."""
    reranker = Reranker(model_name="fake-model")
    candidates = [
        _make_candidate("strong-match", "relevant text", distance=0.5),
        _make_candidate("weak-match", "irrelevant text", distance=0.5),
    ]
    reranker._model = _FakeCrossEncoder([8.6, -4.3])

    reranked = reranker.rerank("query", candidates, top_k=2)

    for result in reranked:
        assert 0.0 <= result["distance"] <= 1.0
    assert reranked[0]["id"] == "strong-match"
    assert reranked[0]["distance"] == pytest.approx(1.0 - _sigmoid(8.6))
    assert reranked[1]["distance"] == pytest.approx(1.0 - _sigmoid(-4.3))


def test_sigmoid_matches_standard_logistic_function():
    assert _sigmoid(0.0) == pytest.approx(0.5)
    assert _sigmoid(100.0) == pytest.approx(1.0)
    assert _sigmoid(-100.0) == pytest.approx(0.0)
    assert _sigmoid(1.0) == pytest.approx(1.0 / (1.0 + math.exp(-1.0)))


async def test_arerank_offloads_to_thread():
    reranker = Reranker(model_name="fake-model")
    candidates = [_make_candidate("a", "text a", distance=0.5)]
    reranker._model = _FakeCrossEncoder([0.7])

    reranked = await reranker.arerank("query", candidates, top_k=1)

    assert reranked[0]["id"] == "a"
