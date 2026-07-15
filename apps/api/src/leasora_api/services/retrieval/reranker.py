"""Cross-encoder reranker for second-stage retrieval refinement.

Dense retrieval (embedder + ChromaDB) is fast but scores query/document
similarity independently of each other (bi-encoder). A cross-encoder scores
the (query, document) pair jointly, which is slower but typically more
accurate at distinguishing close candidates. The reranker takes a larger
candidate set from dense retrieval and re-sorts it, keeping only the top-k.

Lazy-loaded like ``Embedder`` so importing this module or constructing a
``Reranker`` never triggers a model download.
"""

import asyncio
import math
from typing import TYPE_CHECKING

from leasora_api.core.config import get_settings
from leasora_api.services.retrieval.vector_store import RetrievalResult

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder


def _sigmoid(x: float) -> float:
    """Map an unbounded cross-encoder logit to a (0, 1) probability-like score.

    ``cross-encoder/ms-marco-MiniLM-L-6-v2`` ships a
    ``sbert_ce_default_activation_function`` of ``Identity`` in its config
    (it was trained with a ranking loss, not BCE), so ``CrossEncoder.predict``
    returns raw logits roughly in [-11, 11], not [0, 1]. Applying sigmoid
    here keeps ``1 - score`` on the same [0, 1] distance scale dense
    retrieval uses, so ``refusal_threshold`` means the same thing regardless
    of ``rerank_enabled`` and confidence no longer saturates at 1.0.
    """
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


class Reranker:
    """Re-score and re-sort retrieved chunks using a cross-encoder model."""

    def __init__(self, model_name: str | None = None) -> None:
        """Initialize the reranker with a specified cross-encoder model.

        Args:
            model_name: sentence-transformers cross-encoder model identifier.
                Defaults to ``settings.reranker_model`` when not provided.
        """
        self.model_name = model_name or get_settings().reranker_model
        self._model: CrossEncoder | None = None

    def _ensure_loaded(self) -> "CrossEncoder":
        """Lazily construct the CrossEncoder model on first use."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Re-score candidates against the query and return the top-k.

        Args:
            query: The original search query.
            candidates: Dense-retrieval candidates to re-score (typically the
                top ``rerank_top_n`` results from ``VectorStore.query``).
            top_k: Number of results to keep after reranking.

        Returns:
            Candidates re-sorted by cross-encoder score (descending), limited
            to ``top_k``. Each result's ``distance`` field is replaced with
            ``1 - sigmoid(score)`` so lower still means "more relevant" and
            the value stays in [0, 1], consistent with the dense-retrieval
            distance convention.
        """
        if not candidates:
            return []

        model = self._ensure_loaded()
        pairs = [(query, candidate["text"]) for candidate in candidates]
        scores = model.predict(pairs)

        # Sigmoid is monotonic, so sorting by raw score (descending) yields
        # the same order as sorting by the calibrated probability.
        reranked = sorted(
            zip(candidates, scores, strict=True), key=lambda pair: pair[1], reverse=True
        )

        results: list[RetrievalResult] = []
        for candidate, score in reranked[:top_k]:
            updated = dict(candidate)
            updated["distance"] = 1.0 - _sigmoid(float(score))
            results.append(updated)  # type: ignore[arg-type]
        return results

    async def arerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Async wrapper around :meth:`rerank`.

        Cross-encoder scoring is CPU-bound and synchronous, so the blocking
        call is offloaded to a worker thread to avoid stalling the event loop.
        """
        return await asyncio.to_thread(self.rerank, query, candidates, top_k)


# Singleton instance for dependency injection. Construction is cheap because
# the model itself is lazy-loaded on first rerank call, not here.
reranker = Reranker()
