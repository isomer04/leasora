"""Integration tests for GET /leases/{lease_id}/chunks."""

import asyncio

from fastapi.testclient import TestClient

from leasora_api.services.ingest.lease_store import LeaseStore
from leasora_api.services.retrieval.vector_store import ChromaStore


def test_get_chunks_404_when_lease_not_found(app, monkeypatch, tmp_path):
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    client = TestClient(app)
    response = client.get("/leases/does-not-exist/chunks")

    assert response.status_code == 404
    assert response.json()["error_code"] == "NotFoundError"


def test_get_chunks_returns_sorted_chunks_with_metadata(app, monkeypatch, tmp_path):
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    test_lease_store.add(
        lease_id="lease_abc12345", name="Test Lease", tenant="", landlord="", chunk_count=2
    )
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    test_store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="chunks-test")
    monkeypatch.setattr("leasora_api.http.routes.leases.chroma", test_store)

    asyncio.run(
        test_store.add(
            ids=["lease_abc12345::0", "lease_abc12345::1"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            documents=["Page 2 clause about rent.", "Page 1 clause about maintenance."],
            metadatas=[
                {"clause_type": "rental_term", "page": 2, "source": "x.pdf", "lease_id": "lease_abc12345"},
                {"clause_type": "maintenance", "page": 1, "source": "x.pdf", "lease_id": "lease_abc12345"},
            ],
        )
    )

    client = TestClient(app)
    response = client.get("/leases/lease_abc12345/chunks")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    # Sorted by page ascending, even though inserted page-2-then-page-1.
    assert [c["page"] for c in body] == [1, 2]
    assert body[0]["clause_type"] == "maintenance"
    assert body[1]["clause_type"] == "rental_term"
    # Per-chunk metadata round-trip: text, source, and id must all come
    # back correctly so the UI can render excerpts and link to chunks.
    assert body[0]["text"] == "Page 1 clause about maintenance."
    assert body[0]["source"] == "x.pdf"
    assert body[0]["id"] == "lease_abc12345::1"
    assert body[1]["text"] == "Page 2 clause about rent."
    assert body[1]["source"] == "x.pdf"
    assert body[1]["id"] == "lease_abc12345::0"


def test_get_chunks_empty_list_when_no_chunks_indexed(app, monkeypatch, tmp_path):
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    test_lease_store.add(
        lease_id="lease_no_chunks", name="Empty Lease", tenant="", landlord="", chunk_count=0
    )
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    test_store = ChromaStore(persist_dir=str(tmp_path / "chroma2"), collection_name="chunks-empty-test")
    monkeypatch.setattr("leasora_api.http.routes.leases.chroma", test_store)

    client = TestClient(app)
    response = client.get("/leases/lease_no_chunks/chunks")

    assert response.status_code == 200
    assert response.json() == []


def test_get_chunks_422_for_invalid_lease_id(app):
    client = TestClient(app)
    response = client.get("/leases/bad$id!/chunks")

    assert response.status_code == 422
