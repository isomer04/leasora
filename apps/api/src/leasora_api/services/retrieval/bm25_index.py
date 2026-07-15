"""In-memory BM25 lexical index for hybrid (lexical + dense) retrieval.

Dense embeddings are good at semantic similarity but can miss exact terms
that matter a lot in leases: statute citations ("§1950.5"), dollar amounts,
and specific phrases like "security deposit". BM25 scores documents by exact
token overlap, which complements dense retrieval for these cases.

The index is built per-lease and kept in memory (no persistence) since it's
cheap to rebuild from the chunks already stored in ChromaDB via
``VectorStore.get_by_lease``. There is no "async" concern here: BM25 scoring
over a single lease's chunk count is fast enough to run inline, but the
build/query methods are still offloaded to a thread for consistency with the
other retrieval components and to avoid blocking the event loop on larger
leases.

A module-level ``BM25Cache`` (LRU, ``max_size=16``) memoizes the built index
per lease_id so subsequent hybrid queries in the same process don't pay the
abuild cost on every request. The cache is invalidated alongside
``QueryCache`` / ``SemanticCache`` by ``IngestPipeline.ingest``.
"""

import asyncio
import re
from collections import OrderedDict
from threading import Lock
from typing import TYPE_CHECKING

from leasora_api.services.retrieval.vector_store import RetrievalResult

if TYPE_CHECKING:
    from rank_bm25 import BM25Okapi

# Default cap on how many leases keep a built BM25 index in process memory.
# Sized for the common single-tenant v1 deployment (per ADR-006) where one
# user is active at a time; a multi-user workload would need a different
# strategy (size-bounded by lease count, or evicted on LLM cost).
DEFAULT_BM25_CACHE_MAX_SIZE = 16

_TOKEN_PATTERN = re.compile(r"[a-z0-9§]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    """Lowercase, alphanumeric (+ section-sign) tokenization for BM25."""
    return _TOKEN_PATTERN.findall(text.lower())


class BM25Index:
    """BM25 lexical index over a single lease's chunks."""

    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._chunks: list[RetrievalResult] = []

    def build(self, chunks: list[RetrievalResult]) -> None:
        """Build the index from a lease's chunks.

        Args:
            chunks: All chunks for a lease (e.g. from
                ``VectorStore.get_by_lease``).
        """
        from rank_bm25 import BM25Okapi

        self._chunks = chunks
        if not chunks:
            self._bm25 = None
            return
        tokenized_corpus = [_tokenize(chunk["text"]) for chunk in chunks]
        self._bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, top_k: int = 20) -> list[tuple[RetrievalResult, float]]:
        """Score chunks against a query and return the top-k by BM25 score.

        Args:
            query: The search query text.
            top_k: Number of results to return.

        Returns:
            List of ``(chunk, score)`` tuples, ranked by score descending.
            Score is BM25's raw score (unbounded, higher is more relevant).
        """
        if self._bm25 is None or not self._chunks:
            return []

        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(
            zip(self._chunks, scores, strict=True), key=lambda pair: pair[1], reverse=True
        )
        return [(chunk, float(score)) for chunk, score in ranked[:top_k]]

    async def abuild(self, chunks: list[RetrievalResult]) -> None:
        """Async wrapper around :meth:`build`."""
        await asyncio.to_thread(self.build, chunks)

    async def asearch(
        self, query: str, top_k: int = 20
    ) -> list[tuple[RetrievalResult, float]]:
        """Async wrapper around :meth:`search`."""
        return await asyncio.to_thread(self.search, query, top_k)


def normalize_scores(scores: list[float]) -> list[float]:
    """Min-max normalize a list of scores into ``[0, 1]``.

    Returns all-zero if the list is empty or all scores are equal (avoids
    division by zero), so fusion degrades gracefully rather than raising.
    """
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [0.0 for _ in scores]
    return [(score - lo) / (hi - lo) for score in scores]


def fuse_results(
    dense_results: list[RetrievalResult],
    bm25_results: list[tuple[RetrievalResult, float]],
    alpha: float = 0.5,
    top_k: int = 5,
) -> list[RetrievalResult]:
    """Fuse dense and BM25 results via normalized weighted score sum.

    Dense ``distance`` is converted to a similarity (``1 - normalized
    distance``) so both signals point the same direction (higher = better)
    before fusing. The fused result's ``distance`` field is set to
    ``1 - fused_score`` so it stays consistent with the "lower distance is
    more relevant" convention used elsewhere.

    Args:
        dense_results: Ranked results from dense (vector) retrieval.
        bm25_results: ``(chunk, score)`` pairs from :meth:`BM25Index.search`.
        alpha: Weight given to the dense signal; ``(1 - alpha)`` weight goes
            to the BM25 signal. ``0.5`` weighs them equally.
        top_k: Number of fused results to return.

    Returns:
        Fused, re-ranked results, deduplicated by chunk ID, limited to
        ``top_k``.
    """
    dense_distances = [r["distance"] for r in dense_results]
    # Negate distances so "lower distance = more relevant" maps to a higher
    # value for `normalize_scores`. Edge case: if all distances are identical
    # (e.g. all 0.0 for perfect matches), normalization returns all zeros,
    # meaning the dense signal contributes nothing to fusion — BM25 alone
    # determines ranking. This is acceptable: when dense can't differentiate,
    # falling back to lexical is the desired hybrid behavior.
    dense_similarities = normalize_scores([-d for d in dense_distances])  # invert: lower distance -> higher score
    dense_scores: dict[str, float] = {
        r["id"]: sim for r, sim in zip(dense_results, dense_similarities, strict=True)
    }

    bm25_raw_scores = [score for _, score in bm25_results]
    bm25_normalized = normalize_scores(bm25_raw_scores)
    bm25_scores: dict[str, float] = {
        chunk["id"]: norm_score
        for (chunk, _), norm_score in zip(bm25_results, bm25_normalized, strict=True)
    }

    all_chunks: dict[str, RetrievalResult] = {}
    for r in dense_results:
        all_chunks[r["id"]] = r
    for chunk, _ in bm25_results:
        all_chunks.setdefault(chunk["id"], chunk)

    fused: list[tuple[RetrievalResult, float]] = []
    for chunk_id, chunk in all_chunks.items():
        dense_score = dense_scores.get(chunk_id, 0.0)
        bm25_score = bm25_scores.get(chunk_id, 0.0)
        fused_score = alpha * dense_score + (1 - alpha) * bm25_score
        fused.append((chunk, fused_score))

    fused.sort(key=lambda pair: pair[1], reverse=True)

    results: list[RetrievalResult] = []
    for chunk, fused_score in fused[:top_k]:
        updated = dict(chunk)
        updated["distance"] = 1.0 - fused_score
        results.append(updated)  # type: ignore[arg-type]
    return results


class BM25Cache:
    """LRU cache of built ``BM25Index`` objects, keyed by lease_id.

    Avoids rebuilding the BM25 index on every hybrid query for a lease by
    keeping one in-memory copy per lease. Sized at ``DEFAULT_BM25_CACHE_MAX_SIZE``
    (16) by default — a hard cap on memory use regardless of ingest activity.
    Invalidation is lease-scoped (``evict_lease``) and is called from
    ``IngestPipeline.ingest`` alongside the other lease-scoped caches.

    Thread-safe: all mutations are protected by a lock so concurrent
    ``asyncio.to_thread`` calls (from BM25Index.abuild/asearch) cannot
    corrupt the OrderedDict.
    """

    def __init__(self, max_size: int = DEFAULT_BM25_CACHE_MAX_SIZE) -> None:
        self.max_size = max_size
        self._store: OrderedDict[str, BM25Index] = OrderedDict()
        self._lock = Lock()

    def get(self, lease_id: str) -> "BM25Index | None":
        """Return the cached index for ``lease_id``, or ``None`` on a miss.

        Promotes the entry to the most-recently-used position so it survives
        subsequent evictions.
        """
        with self._lock:
            index = self._store.get(lease_id)
            if index is not None:
                self._store.move_to_end(lease_id)
            return index

    def set(self, lease_id: str, index: "BM25Index") -> None:
        """Cache ``index`` for ``lease_id``, evicting the LRU entry if at cap."""
        with self._lock:
            self._store[lease_id] = index
            self._store.move_to_end(lease_id)
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def evict_lease(self, lease_id: str) -> int:
        """Drop every cached index for ``lease_id``.

        Called from ``IngestPipeline.ingest`` so a re-ingest never sees a
        stale index built from a previous version of the same lease.

        Returns:
            Number of entries evicted (0 or 1 today, since the cache is
            keyed uniquely by lease_id).
        """
        with self._lock:
            keys_to_remove = [key for key in self._store if key == lease_id]
            for key in keys_to_remove:
                del self._store[key]
            return len(keys_to_remove)

    def clear(self) -> None:
        """Drop every cached index (used by tests)."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# Module-level singleton for the hybrid retrieval hot path. Construction is
# cheap (empty OrderedDict); eviction is handled by IngestPipeline.ingest.
bm25_cache = BM25Cache()
