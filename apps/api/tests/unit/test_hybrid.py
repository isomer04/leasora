from leasora_api.services.retrieval.bm25_index import BM25Index, fuse_results, normalize_scores
from leasora_api.services.retrieval.vector_store import RetrievalResult


def _make_result(id_: str, text: str, distance: float) -> RetrievalResult:
    return RetrievalResult(
        id=id_,
        text=text,
        metadata={"source": "lease.pdf", "page": 1, "clause_type": "other"},
        distance=distance,
    )


def test_normalize_scores_empty_returns_empty():
    assert normalize_scores([]) == []


def test_normalize_scores_min_max():
    assert normalize_scores([0.0, 5.0, 10.0]) == [0.0, 0.5, 1.0]


def test_normalize_scores_all_equal_returns_zeros():
    assert normalize_scores([3.0, 3.0, 3.0]) == [0.0, 0.0, 0.0]


def test_bm25_index_empty_corpus_returns_empty_search():
    index = BM25Index()
    index.build([])
    assert index.search("query", top_k=5) == []


def test_bm25_index_finds_exact_term_match():
    # A 2-document corpus makes BM25's IDF degenerate to 0 for a term that
    # appears in exactly one doc, so this needs enough documents for IDF to
    # meaningfully differentiate matches from non-matches.
    chunks = [
        _make_result("a", "The security deposit is $2,000, per Civil Code Section 1950.5.", 0.0),
        _make_result("b", "Tenant shall maintain the unit in clean condition.", 0.0),
        _make_result("c", "Landlord may enter with 24 hours written notice.", 0.0),
        _make_result("d", "Rent is due on the first of the month.", 0.0),
    ]
    index = BM25Index()
    index.build(chunks)

    results = index.search("security deposit 1950.5", top_k=4)

    assert results[0][0]["id"] == "a"
    assert results[0][1] > results[1][1]


async def test_bm25_index_async_wrappers():
    chunks = [_make_result("a", "rent is due monthly", 0.0)]
    index = BM25Index()
    await index.abuild(chunks)

    results = await index.asearch("rent due", top_k=1)

    assert results[0][0]["id"] == "a"


def test_fuse_results_combines_dense_and_bm25():
    dense = [
        _make_result("dense-only", "semantically similar text", distance=0.2),
    ]
    bm25 = [
        (_make_result("bm25-only", "exact term match §1950.5", distance=0.0), 5.0),
    ]

    fused = fuse_results(dense, bm25, alpha=0.5, top_k=5)

    fused_ids = {r["id"] for r in fused}
    assert "dense-only" in fused_ids
    assert "bm25-only" in fused_ids


def test_fuse_results_deduplicates_overlapping_chunks():
    shared = _make_result("shared", "shared text", distance=0.1)
    dense = [shared]
    bm25 = [(shared, 3.0)]

    fused = fuse_results(dense, bm25, alpha=0.5, top_k=5)

    assert len(fused) == 1
    assert fused[0]["id"] == "shared"


def test_fuse_results_alpha_weights_dense_higher():
    dense_favored = _make_result("dense-favored", "text a", distance=0.0)  # best possible dense score
    bm25_favored = _make_result("bm25-favored", "text b", distance=0.9)  # weak dense score

    dense = [dense_favored, bm25_favored]
    bm25 = [(dense_favored, 0.0), (bm25_favored, 10.0)]  # bm25 strongly favors the other chunk

    fused_dense_heavy = fuse_results(dense, bm25, alpha=1.0, top_k=1)
    assert fused_dense_heavy[0]["id"] == "dense-favored"

    fused_bm25_heavy = fuse_results(dense, bm25, alpha=0.0, top_k=1)
    assert fused_bm25_heavy[0]["id"] == "bm25-favored"


def test_fuse_results_respects_top_k():
    dense = [
        _make_result("a", "text a", distance=0.1),
        _make_result("b", "text b", distance=0.2),
        _make_result("c", "text c", distance=0.3),
    ]
    fused = fuse_results(dense, [], alpha=1.0, top_k=2)
    assert len(fused) == 2
