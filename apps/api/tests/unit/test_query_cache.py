from leasora_api.schemas.response import AskResponse
from leasora_api.services.retrieval.query_cache import (
    QueryCache,
    build_cache_key,
    normalize_question,
)


def test_normalize_question_lowercases_and_collapses_whitespace():
    assert normalize_question("  When   IS Rent Due?  ") == "when is rent due?"


def test_build_cache_key_is_deterministic():
    key1 = build_cache_key("lease-1", "When is rent due?", (5, 0.55))
    key2 = build_cache_key("lease-1", "When is rent due?", (5, 0.55))
    assert key1 == key2


def test_build_cache_key_differs_by_lease():
    key1 = build_cache_key("lease-1", "question", ())
    key2 = build_cache_key("lease-2", "question", ())
    assert key1 != key2


def test_build_cache_key_differs_by_config_flags():
    key1 = build_cache_key("lease-1", "question", (True,))
    key2 = build_cache_key("lease-1", "question", (False,))
    assert key1 != key2


def test_cache_miss_returns_none():
    cache = QueryCache()
    assert cache.get("lease-1", "question") is None


def test_cache_set_then_get_returns_stored_response():
    cache = QueryCache()
    response = AskResponse(answer="the answer")

    cache.set("lease-1", "When is rent due?", response)
    result = cache.get("lease-1", "When is rent due?")

    assert result is response


def test_cache_normalizes_question_on_lookup():
    cache = QueryCache()
    response = AskResponse(answer="the answer")

    cache.set("lease-1", "When is rent due?", response)
    result = cache.get("lease-1", "  when   is rent due?  ")

    assert result is response


def test_cache_is_scoped_by_lease():
    cache = QueryCache()
    response = AskResponse(answer="the answer")

    cache.set("lease-1", "When is rent due?", response)
    result = cache.get("lease-2", "When is rent due?")

    assert result is None


def test_cache_respects_config_flags():
    cache = QueryCache()
    response = AskResponse(answer="the answer")

    cache.set("lease-1", "When is rent due?", response, config_flags=(True,))
    result = cache.get("lease-1", "When is rent due?", config_flags=(False,))

    assert result is None


def test_cache_evicts_lru_when_full():
    cache = QueryCache(max_size=2)
    cache.set("lease-1", "q1", AskResponse(answer="a1"))
    cache.set("lease-1", "q2", AskResponse(answer="a2"))
    cache.set("lease-1", "q3", AskResponse(answer="a3"))

    assert cache.get("lease-1", "q1") is None  # evicted
    assert cache.get("lease-1", "q2") is not None
    assert cache.get("lease-1", "q3") is not None


def test_evict_lease_removes_only_that_leases_entries():
    cache = QueryCache()
    cache.set("lease-1", "q1", AskResponse(answer="a1"))
    cache.set("lease-2", "q1", AskResponse(answer="a2"))

    evicted = cache.evict_lease("lease-1")

    assert evicted == 1
    assert cache.get("lease-1", "q1") is None
    assert cache.get("lease-2", "q1") is not None


def test_evict_lease_returns_zero_when_nothing_to_evict():
    cache = QueryCache()
    assert cache.evict_lease("nonexistent-lease") == 0


def test_clear_removes_all_entries():
    cache = QueryCache()
    cache.set("lease-1", "q1", AskResponse(answer="a1"))
    cache.clear()
    assert len(cache) == 0


def test_concurrent_set_and_evict_does_not_corrupt_cache():
    """Hammer ``set`` + ``evict_lease`` in parallel — must not raise or drop entries.
    ``RuntimeError: dictionary changed size during iteration``.
    """
    from concurrent.futures import ThreadPoolExecutor

    cache = QueryCache(max_size=512)
    errors: list[BaseException] = []

    def writer(start: int) -> None:
        try:
            for i in range(200):
                cache.set(f"lease-{i % 8}", f"q-{start}-{i}", AskResponse(answer=f"a-{start}-{i}"))
        except BaseException as exc:  # noqa: BLE001 — surfacing for the assertion
            errors.append(exc)

    def evictor() -> None:
        try:
            for i in range(200):
                cache.evict_lease(f"lease-{i % 8}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def length_probe() -> None:
        try:
            for _ in range(200):
                len(cache)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [
            pool.submit(writer, 0),
            pool.submit(writer, 1),
            pool.submit(writer, 2),
            pool.submit(writer, 3),
            pool.submit(evictor),
            pool.submit(evictor),
            pool.submit(length_probe),
            pool.submit(length_probe),
        ]
        for fut in futures:
            fut.result()

    assert errors == [], f"concurrent mutations raised: {errors!r}"
    # Final length must be a valid int (not a partial read).
    assert isinstance(len(cache), int)
    assert 0 <= len(cache) <= 512

