"""Integration tests for GET /compare/count and GET /compare/history."""

from fastapi.testclient import TestClient

from leasora_api.services.compare.comparison_store import ComparisonStore


def test_comparison_count_defaults_to_zero(app, monkeypatch, tmp_path):
    test_store = ComparisonStore(tmp_path / "comparisons.json")
    monkeypatch.setattr("leasora_api.http.routes.compare.comparison_store", test_store)

    client = TestClient(app)
    response = client.get("/compare/count")

    assert response.status_code == 200
    assert response.json() == {"count": 0}


def test_comparison_count_reflects_recorded_comparisons(app, monkeypatch, tmp_path):
    test_store = ComparisonStore(tmp_path / "comparisons.json")
    test_store.add(lease_ids=["a", "b"])
    test_store.add(lease_ids=["c", "d"])
    monkeypatch.setattr("leasora_api.http.routes.compare.comparison_store", test_store)

    client = TestClient(app)
    response = client.get("/compare/count")

    assert response.status_code == 200
    assert response.json() == {"count": 2}


def test_comparison_history_paginates(app, monkeypatch, tmp_path):
    test_store = ComparisonStore(tmp_path / "comparisons.json")
    for i in range(3):
        test_store.add(lease_ids=[f"lease_{i}", f"lease_{i}b"])
    monkeypatch.setattr("leasora_api.http.routes.compare.comparison_store", test_store)

    client = TestClient(app)
    response = client.get("/compare/history", params={"page": 1, "page_size": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    # Most recent first
    assert body["items"][0]["lease_ids"] == ["lease_2", "lease_2b"]


def test_comparison_history_empty_state(app, monkeypatch, tmp_path):
    test_store = ComparisonStore(tmp_path / "comparisons.json")
    monkeypatch.setattr("leasora_api.http.routes.compare.comparison_store", test_store)

    client = TestClient(app)
    response = client.get("/compare/history")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_comparison_history_rejects_oversized_page_size(app, monkeypatch, tmp_path):
    test_store = ComparisonStore(tmp_path / "comparisons.json")
    monkeypatch.setattr("leasora_api.http.routes.compare.comparison_store", test_store)

    client = TestClient(app)
    response = client.get("/compare/history", params={"page_size": 1000})

    assert response.status_code == 422
