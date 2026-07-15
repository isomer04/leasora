from leasora_api.schemas.response import AskResponse
from leasora_api.services.retrieval.semantic_cache import SemanticCache, cosine_similarity


def test_cosine_similarity_identical_vectors_is_one():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0, "Identical vectors must have similarity of 1.0"


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0, "Orthogonal vectors must have similarity of 0.0"


def test_cosine_similarity_zero_vector_returns_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0, "Zero vector must have 0 similarity with any vector"


def test_cosine_similarity_mismatched_length_returns_zero():
    assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0, "Mismatched vector dimensions must return 0 similarity"


def test_cosine_similarity_empty_vectors_returns_zero():
    assert cosine_similarity([], []) == 0.0, "Empty vectors must return 0 similarity"


def test_cache_miss_returns_none():
    cache = SemanticCache()
    assert cache.get("lease-1", [1.0, 0.0]) is None, "Empty cache must return None for any query"


def test_cache_returns_match_above_threshold():
    cache = SemanticCache(threshold=0.9)
    response = AskResponse(answer="the answer")
    cache.set("lease-1", [1.0, 0.0], response)

    result = cache.get("lease-1", [1.0, 0.0001])  # near-identical vector

    assert result is response, "Near-identical vectors above threshold must return cached response"


def test_cache_returns_none_below_threshold():
    cache = SemanticCache(threshold=0.99)
    response = AskResponse(answer="the answer")
    cache.set("lease-1", [1.0, 0.0], response)

    result = cache.get("lease-1", [0.5, 0.5])  # dissimilar vector

    assert result is None, "Dissimilar vectors below threshold must not return cached response"


def test_cache_is_scoped_by_lease():
    cache = SemanticCache(threshold=0.9)
    response = AskResponse(answer="the answer")
    cache.set("lease-1", [1.0, 0.0], response)

    result = cache.get("lease-2", [1.0, 0.0])

    assert result is None, "Cache must be isolated by lease_id; different lease must miss"


def test_cache_returns_best_match_among_multiple_entries():
    cache = SemanticCache(threshold=0.5)
    weak_match = AskResponse(answer="weak")
    strong_match = AskResponse(answer="strong")
    cache.set("lease-1", [1.0, 0.5], weak_match)
    cache.set("lease-1", [1.0, 0.0], strong_match)

    result = cache.get("lease-1", [1.0, 0.0])

    assert result is strong_match, "Cache must return best match (highest similarity score)"


def test_cache_evicts_oldest_when_full():
    cache = SemanticCache(threshold=0.9, max_size=2)
    cache.set("lease-1", [1.0, 0.0], AskResponse(answer="a1"))
    cache.set("lease-1", [0.0, 1.0], AskResponse(answer="a2"))
    cache.set("lease-1", [0.0, 0.0, 1.0], AskResponse(answer="a3"))

    assert len(cache) == 2, "Cache must respect max_size limit after evicting oldest"


def test_evict_lease_removes_only_that_leases_entries():
    cache = SemanticCache(threshold=0.9)
    cache.set("lease-1", [1.0, 0.0], AskResponse(answer="a1"))
    cache.set("lease-2", [1.0, 0.0], AskResponse(answer="a2"))

    evicted = cache.evict_lease("lease-1")

    assert evicted == 1, "evict_lease must return count of removed entries"
    assert cache.get("lease-1", [1.0, 0.0]) is None, "Evicted lease entries must be removed"
    assert cache.get("lease-2", [1.0, 0.0]) is not None, "Other leases must not be affected by eviction"


def test_evict_lease_returns_zero_when_nothing_to_evict():
    cache = SemanticCache()
    assert cache.evict_lease("nonexistent-lease") == 0, "evict_lease must return 0 for non-existent lease"


def test_clear_removes_all_entries():
    cache = SemanticCache(threshold=0.9)
    cache.set("lease-1", [1.0, 0.0], AskResponse(answer="a1"))
    cache.clear()
    assert len(cache) == 0, "clear must remove all cache entries"


def test_get_skips_entries_cached_under_different_config_flags():
    """Cached under config A, queried under config B → must miss (no stale answer)."""
    cache = SemanticCache(threshold=0.9)
    stale = AskResponse(answer="stale-answer")
    cache.set("lease-1", [1.0, 0.0], stale, config_flags=("rerank_off",))

    # Different config flags → must not serve the stale entry.
    result = cache.get("lease-1", [1.0, 0.0], config_flags=("rerank_on",))

    assert result is None, "Cache must not serve entries cached under different config flags"


def test_get_returns_entry_when_config_flags_match():
    """Cached under config A, queried under config A → must hit."""
    cache = SemanticCache(threshold=0.9)
    response = AskResponse(answer="fresh-answer")
    cache.set("lease-1", [1.0, 0.0], response, config_flags=("rerank_on", 0.55))

    result = cache.get("lease-1", [1.0, 0.0], config_flags=("rerank_on", 0.55))

    assert result is response, "Cache must serve entry when config flags exactly match"


def test_get_treats_missing_config_flags_as_empty():
    """Backwards-compat: existing call sites that don't pass config_flags still work."""
    cache = SemanticCache(threshold=0.9)
    response = AskResponse(answer="legacy-answer")
    cache.set("lease-1", [1.0, 0.0], response)

    # Caller doesn't pass config_flags → still finds the legacy entry.
    assert cache.get("lease-1", [1.0, 0.0]) is response, (
        "Backwards-compat: missing config_flags must match empty config"
    )


def test_lru_promotion_on_hit_protects_hot_entry_from_eviction():
    """Regression: MRU promotion must not evict matching entries.
    guarantees that an accessed entry survives the next ``set`` even when
    the cache is already at capacity.
    """
    cache = SemanticCache(threshold=0.9, max_size=2)
    a = AskResponse(answer="a")
    b = AskResponse(answer="b")
    cache.set("lease-1", [1.0, 0.0], a)
    cache.set("lease-1", [0.0, 1.0], b)

    # Hit on `a` promotes it; b becomes LRU and is now the eviction candidate.
    assert cache.get("lease-1", [1.0, 0.0]) is a

    # Inserting a third entry must evict b (the LRU), not a (just-promoted).
    c = AskResponse(answer="c")
    cache.set("lease-1", [0.0, 0.0, 1.0], c)
    assert len(cache) == 2, "Cache must maintain max_size after LRU eviction"
    assert cache.get("lease-1", [1.0, 0.0]) is a, "Recently accessed entry must not be evicted"
    assert cache.get("lease-1", [0.0, 1.0]) is None, "LRU entry must be evicted"


def test_set_evicts_lru_not_fifo_when_cache_is_full():
    """Once the cache exceeds max_size, the least-recently-used entry is dropped.
    """
    cache = SemanticCache(threshold=0.9, max_size=3)
    a = AskResponse(answer="a")
    b = AskResponse(answer="b")
    c = AskResponse(answer="c")
    d = AskResponse(answer="d")
    cache.set("lease-1", [1.0, 0.0], a)  # 1st (will be LRU)
    cache.set("lease-1", [0.0, 1.0], b)  # 2nd
    cache.set("lease-1", [0.0, 0.0, 1.0], c)  # 3rd

    # Touch `a` so it becomes MRU before the overflow insert.
    assert cache.get("lease-1", [1.0, 0.0]) is a

    # 4th insert should evict `b` (now LRU), not `a`.
    cache.set("lease-1", [1.0, 1.0, 0.0], d)
    assert len(cache) == 3, "Cache must maintain max_size when evicting LRU"
    assert cache.get("lease-1", [1.0, 0.0]) is a, "MRU entry must not be evicted"
    assert cache.get("lease-1", [0.0, 1.0]) is None, "LRU entry must be evicted on overflow"
    assert cache.get("lease-1", [0.0, 0.0, 1.0]) is c, "Non-LRU entries must survive eviction"
    assert cache.get("lease-1", [1.0, 1.0, 0.0]) is d, "New entry must be added to cache"
