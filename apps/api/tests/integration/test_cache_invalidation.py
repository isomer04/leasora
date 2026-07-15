"""Integration test: re-ingesting a lease must evict its cached answers.

Uses the real ingest pipeline + real embedder against a temp ChromaDB dir,
with dedicated QueryCache/SemanticCache instances so this test doesn't
interfere with (or get interfered with by) the module-level singletons.
Also covers the per-lease BM25 index cache: a re-ingest must drop the
stale ``BM25Index`` so the next hybrid query rebuilds against the new
corpus instead of returning stale results.
"""

from leasora_api.schemas.response import AskResponse
from leasora_api.services.eval.runner import DEFAULT_DEMO_LEASE_PDF
from leasora_api.services.ingest.pipeline import IngestPipeline
from leasora_api.services.retrieval.bm25_index import BM25Cache, BM25Index
from leasora_api.services.retrieval.embedder import Embedder
from leasora_api.services.retrieval.query_cache import QueryCache
from leasora_api.services.retrieval.semantic_cache import SemanticCache
from leasora_api.services.retrieval.vector_store import ChromaStore

# Reuse the same repo-root-marker-based lookup as the eval runner instead of
# a separate hardcoded parents[N] path, so both stay correct if the module
# layout changes.
DEMO_LEASE = DEFAULT_DEMO_LEASE_PDF


async def test_ingest_evicts_existing_cache_entries_for_lease(tmp_path):
    if not DEMO_LEASE.exists():
        import pytest

        pytest.skip("demo_lease.pdf fixture not present")

    lease_id = "lease-cache-invalidation-test"
    store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="cache-test")
    embedder = Embedder()
    query_cache = QueryCache()
    semantic_cache = SemanticCache()
    bm25_cache = BM25Cache()

    pipeline = IngestPipeline(
        embedder_=embedder,
        vector_store=store,
        query_cache_=query_cache,
        semantic_cache_=semantic_cache,
        bm25_cache_=bm25_cache,
    )

    # Seed all three caches as if a previous ingest had already produced
    # answers and a built BM25 index.
    stale_response = AskResponse(answer="stale cached answer")
    query_cache.set(lease_id, "When is rent due?", stale_response)
    semantic_cache.set(lease_id, [1.0, 0.0, 0.0], stale_response)
    bm25_cache.set(lease_id, BM25Index())
    assert query_cache.get(lease_id, "When is rent due?") is not None
    assert semantic_cache.get(lease_id, [1.0, 0.0, 0.0]) is not None
    assert bm25_cache.get(lease_id) is not None

    await pipeline.ingest(str(DEMO_LEASE), lease_id=lease_id)

    assert query_cache.get(lease_id, "When is rent due?") is None
    assert semantic_cache.get(lease_id, [1.0, 0.0, 0.0]) is None
    assert bm25_cache.get(lease_id) is None


async def test_ingest_does_not_evict_other_leases_cache_entries(tmp_path):
    if not DEMO_LEASE.exists():
        import pytest

        pytest.skip("demo_lease.pdf fixture not present")

    lease_id = "lease-cache-invalidation-target"
    other_lease_id = "lease-cache-invalidation-other"
    store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="cache-test-2")
    embedder = Embedder()
    query_cache = QueryCache()
    semantic_cache = SemanticCache()
    bm25_cache = BM25Cache()

    pipeline = IngestPipeline(
        embedder_=embedder,
        vector_store=store,
        query_cache_=query_cache,
        semantic_cache_=semantic_cache,
        bm25_cache_=bm25_cache,
    )

    other_response = AskResponse(answer="other lease's answer")
    query_cache.set(other_lease_id, "some question", other_response)
    semantic_cache.set(other_lease_id, [0.0, 1.0, 0.0], other_response)
    bm25_cache.set(other_lease_id, BM25Index())

    await pipeline.ingest(str(DEMO_LEASE), lease_id=lease_id)

    assert query_cache.get(other_lease_id, "some question") is not None
    assert semantic_cache.get(other_lease_id, [0.0, 1.0, 0.0]) is not None
    assert bm25_cache.get(other_lease_id) is not None
