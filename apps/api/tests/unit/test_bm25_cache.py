"""Unit tests for the per-lease BM25 LRU cache.

The cache memoizes a built ``BM25Index`` per lease_id so the hybrid
retrieval hot path doesn't pay the build cost on every request. Ingestion
must evict the right entry; an LRU cap must keep memory bounded.
"""

from leasora_api.services.retrieval.bm25_index import BM25Cache, BM25Index


def test_get_returns_none_on_miss():
    cache = BM25Cache()
    assert cache.get("missing-lease") is None
    assert len(cache) == 0


def test_set_then_get_round_trips_same_index():
    cache = BM25Cache()
    index = BM25Index()
    cache.set("lease-a", index)
    assert cache.get("lease-a") is index


def test_evict_lease_removes_only_target_entry():
    cache = BM25Cache()
    cache.set("lease-a", BM25Index())
    cache.set("lease-b", BM25Index())
    assert len(cache) == 2

    evicted = cache.evict_lease("lease-a")
    assert evicted == 1
    assert cache.get("lease-a") is None
    assert cache.get("lease-b") is not None
    assert len(cache) == 1


def test_evict_lease_returns_zero_when_absent():
    cache = BM25Cache()
    cache.set("lease-a", BM25Index())
    assert cache.evict_lease("never-existed") == 0
    assert len(cache) == 1


def test_lru_cap_evicts_oldest_first():
    cache = BM25Cache(max_size=2)
    cache.set("lease-a", BM25Index())
    cache.set("lease-b", BM25Index())

    # Touch lease-a so lease-b is the LRU eviction candidate.
    assert cache.get("lease-a") is not None
    cache.set("lease-c", BM25Index())

    assert len(cache) == 2
    assert cache.get("lease-a") is not None
    assert cache.get("lease-b") is None
    assert cache.get("lease-c") is not None


def test_clear_empties_cache():
    cache = BM25Cache()
    cache.set("lease-a", BM25Index())
    cache.set("lease-b", BM25Index())
    cache.clear()
    assert len(cache) == 0
    assert cache.get("lease-a") is None
