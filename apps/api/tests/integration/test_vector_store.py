"""Small real integration round trip against ChromaDB (no mocks).

Uses a temp directory for the persistent client so this test never touches
the real data/chroma store and is fully isolated/repeatable.
"""

from leasora_api.services.retrieval.vector_store import ChromaStore


async def test_add_and_query_round_trip(tmp_path):
    store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="test-leases")

    ids = ["chunk-1", "chunk-2"]
    embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    documents = ["The rent is due on the first of the month.", "Tenant must maintain the unit."]
    metadatas = [
        {"source": "lease.pdf", "page": 1, "clause_type": "rental_term", "lease_id": "lease-1"},
        {"source": "lease.pdf", "page": 2, "clause_type": "maintenance", "lease_id": "lease-1"},
    ]

    await store.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    results = await store.query(embedding=[1.0, 0.0, 0.0], top_k=2)

    assert len(results) == 2
    # The closest match (identical embedding) should rank first with distance ~0.
    assert results[0]["id"] == "chunk-1"
    assert results[0]["distance"] < results[1]["distance"]
    assert results[0]["metadata"]["clause_type"] == "rental_term"
    assert results[0]["metadata"]["page"] == 1


async def test_query_with_where_filter_scopes_to_lease(tmp_path):
    store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="test-leases-2")

    await store.add(
        ids=["a", "b"],
        embeddings=[[1.0, 0.0], [1.0, 0.0]],
        documents=["lease one clause", "lease two clause"],
        metadatas=[
            {"source": "one.pdf", "page": 1, "clause_type": "other", "lease_id": "lease-a"},
            {"source": "two.pdf", "page": 1, "clause_type": "other", "lease_id": "lease-b"},
        ],
    )

    results = await store.query(
        embedding=[1.0, 0.0], top_k=5, where={"lease_id": {"$eq": "lease-a"}}
    )

    assert len(results) == 1
    assert results[0]["metadata"]["lease_id"] == "lease-a"


async def test_query_empty_collection_returns_empty_list(tmp_path):
    store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="test-empty")
    results = await store.query(embedding=[1.0, 0.0], top_k=5)
    assert results == []
