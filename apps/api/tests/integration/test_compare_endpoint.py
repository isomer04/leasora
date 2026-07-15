"""Integration tests for POST /compare (real LLM-powered comparison)."""

import asyncio

from fastapi.testclient import TestClient

from leasora_api.services.compare.comparison_store import ComparisonStore
from leasora_api.services.ingest.lease_store import LeaseStore
from leasora_api.services.retrieval.vector_store import ChromaStore


def test_compare_rejects_wrong_number_of_lease_ids(app):
    client = TestClient(app)
    response = client.post("/compare", json={"lease_ids": ["only-one"]})

    assert response.status_code == 422


def test_compare_rejects_duplicate_lease_ids(app):
    client = TestClient(app)
    response = client.post("/compare", json={"lease_ids": ["same-id", "same-id"]})

    assert response.status_code == 422


def test_compare_rejects_more_than_two_lease_ids(app):
    client = TestClient(app)
    response = client.post("/compare", json={"lease_ids": ["a", "b", "c"]})

    assert response.status_code == 422


def test_compare_404_when_lease_not_found(app, monkeypatch, tmp_path):
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)
    monkeypatch.setattr(
        "leasora_api.services.compare.comparison_service.lease_store", test_lease_store
    )

    client = TestClient(app)
    response = client.post("/compare", json={"lease_ids": ["lease_a", "lease_b"]})

    assert response.status_code == 404


def test_compare_persists_history_and_returns_differences(app, monkeypatch, tmp_path):
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    test_lease_store.add(lease_id="lease_a", name="Lease A", tenant="", landlord="", chunk_count=1)
    test_lease_store.add(lease_id="lease_b", name="Lease B", tenant="", landlord="", chunk_count=1)
    monkeypatch.setattr(
        "leasora_api.services.compare.comparison_service.lease_store", test_lease_store
    )

    test_vector_store = ChromaStore(
        persist_dir=str(tmp_path / "chroma"), collection_name="compare-test"
    )
    asyncio.run(
        test_vector_store.add(
            ids=["lease_a::0"],
            embeddings=[[0.1, 0.2]],
            documents=["Tenant may sublet with consent."],
            metadatas=[{"clause_type": "assignment", "page": 1, "source": "a.pdf", "lease_id": "lease_a"}],
        )
    )
    asyncio.run(
        test_vector_store.add(
            ids=["lease_b::0"],
            embeddings=[[0.3, 0.4]],
            documents=["Rent is $2000/month."],
            metadatas=[{"clause_type": "rental_term", "page": 1, "source": "b.pdf", "lease_id": "lease_b"}],
        )
    )
    monkeypatch.setattr(
        "leasora_api.services.compare.comparison_service.chroma", test_vector_store
    )
    from leasora_api.services.compare.comparison_service import ComparisonService

    monkeypatch.setattr(
        "leasora_api.http.routes.compare.comparison_service",
        ComparisonService(vector_store=test_vector_store),
    )

    test_comparison_store = ComparisonStore(tmp_path / "comparisons.json")
    monkeypatch.setattr("leasora_api.http.routes.compare.comparison_store", test_comparison_store)

    client = TestClient(app)
    response = client.post("/compare", json={"lease_ids": ["lease_a", "lease_b"]})

    assert response.status_code == 200
    body = response.json()
    assert body["lease_ids"] == ["lease_a", "lease_b"]
    # Both clause types are one-sided (assignment only in A, rental_term only in B)
    assert len(body["differences"]) == 2

    # Comparison history should now have exactly one entry.
    assert test_comparison_store.count() == 1
    count_response = client.get("/compare/count")
    assert count_response.json() == {"count": 1}


def test_compare_succeeds_even_when_history_persistence_fails(
    app, monkeypatch, tmp_path
):
    """If ``comparison_store.add`` raises ``OSError`` (disk full, permission
    denied, etc.), the route must still return the comparison response — the
    history write is best-effort and must not downgrade a successful LLM
    comparison into an error.
    """
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    test_lease_store.add(lease_id="lease_a", name="Lease A", tenant="", landlord="", chunk_count=1)
    test_lease_store.add(lease_id="lease_b", name="Lease B", tenant="", landlord="", chunk_count=1)
    monkeypatch.setattr(
        "leasora_api.services.compare.comparison_service.lease_store", test_lease_store
    )

    test_vector_store = ChromaStore(
        persist_dir=str(tmp_path / "chroma-fail"), collection_name="compare-fail-test"
    )
    asyncio.run(
        test_vector_store.add(
            ids=["lease_a::0"],
            embeddings=[[0.1, 0.2]],
            documents=["Tenant may sublet with consent."],
            metadatas=[{"clause_type": "assignment", "page": 1, "source": "a.pdf", "lease_id": "lease_a"}],
        )
    )
    asyncio.run(
        test_vector_store.add(
            ids=["lease_b::0"],
            embeddings=[[0.3, 0.4]],
            documents=["Rent is $2000/month."],
            metadatas=[{"clause_type": "rental_term", "page": 1, "source": "b.pdf", "lease_id": "lease_b"}],
        )
    )
    monkeypatch.setattr(
        "leasora_api.services.compare.comparison_service.chroma", test_vector_store
    )
    from leasora_api.services.compare.comparison_service import ComparisonService

    monkeypatch.setattr(
        "leasora_api.http.routes.compare.comparison_service",
        ComparisonService(vector_store=test_vector_store),
    )

    test_comparison_store = ComparisonStore(tmp_path / "comparisons.json")

    def _raise_oserror(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(test_comparison_store, "add", _raise_oserror)
    monkeypatch.setattr("leasora_api.http.routes.compare.comparison_store", test_comparison_store)

    client = TestClient(app)
    response = client.post("/compare", json={"lease_ids": ["lease_a", "lease_b"]})

    assert response.status_code == 200
    assert len(response.json()["differences"]) == 2
