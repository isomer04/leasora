"""Integration tests for GET /leases and GET /leases/{id} (lease_store-backed)."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from leasora_api.schemas.domain import MetadataExtractionStatus
from leasora_api.services.ingest.lease_store import LeaseStore
from leasora_api.services.ingest.metadata_extractor import MetadataExtractionResult


def _patch_delete_lease_store(monkeypatch, test_lease_store: LeaseStore) -> None:
    """Point both route lookup and cascade deletion at the isolated test store."""
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)
    monkeypatch.setattr("leasora_api.services.ingest.retention.lease_store", test_lease_store)


def test_list_leases_empty_by_default(app, monkeypatch, tmp_path):
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    client = TestClient(app)
    response = client.get("/leases")

    assert response.status_code == 200
    assert response.json() == []


def test_get_lease_404_when_not_found(app, monkeypatch, tmp_path):
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    client = TestClient(app)
    response = client.get("/leases/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error_code"] == "NotFoundError"


def test_list_and_get_lease_after_add(app, monkeypatch, tmp_path):
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    test_lease_store.add(
        lease_id="lease_abc12345",
        name="Sample Lease",
        tenant="Jane Doe",
        landlord="",
        chunk_count=12,
    )

    client = TestClient(app)

    list_response = client.get("/leases")
    assert list_response.status_code == 200
    body = list_response.json()
    assert len(body) == 1
    assert body[0]["id"] == "lease_abc12345"
    assert body[0]["tenant"] == "Jane Doe"
    assert body[0]["landlord"] == "Not yet extracted"
    assert body[0]["chunk_count"] == 12

    detail_response = client.get("/leases/lease_abc12345")
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "Sample Lease"


def test_delete_lease_404_when_not_found(app, monkeypatch, tmp_path):
    """DELETE returns 404 (not 200/empty) when lease_id doesn't exist."""
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    _patch_delete_lease_store(monkeypatch, test_lease_store)

    client = TestClient(app)
    response = client.delete("/leases/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error_code"] == "NotFoundError"


def test_delete_lease_removes_record_and_returns_report(app, monkeypatch, tmp_path):
    """DELETE cascades: removes the record and returns a DeletionReport."""
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    _patch_delete_lease_store(monkeypatch, test_lease_store)

    test_lease_store.add(
        lease_id="lease_abc12345",
        name="Sample Lease",
        tenant="Jane Doe",
        landlord="",
        chunk_count=12,
    )

    client = TestClient(app)
    response = client.delete("/leases/lease_abc12345")

    assert response.status_code == 200
    body = response.json()
    assert body["lease_id"] == "lease_abc12345"
    assert body["lease_record_removed"] is True
    assert body["actor"] == "manual"
    # Cascade reports per-artifact counts; PDF won't exist in tmp, so pdf_removed=False.
    assert "errors" in body

    # The lease is now gone.
    assert test_lease_store.get("lease_abc12345") is None
    assert client.get("/leases/lease_abc12345").status_code == 404


def test_delete_lease_rejects_invalid_id(app, monkeypatch, tmp_path):
    """DELETE rejects malformed lease_id via the same validator as GET."""
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    _patch_delete_lease_store(monkeypatch, test_lease_store)

    client = TestClient(app)
    response = client.delete("/leases/!!!nope!!!")

    # ValidationError → 422 (Pydantic validation) or 400 (our domain layer).
    assert response.status_code in (400, 422)


def _metadata_test_store(monkeypatch, tmp_path) -> LeaseStore:
    store = LeaseStore(tmp_path / "leases.json")
    store.add(
        lease_id="lease_abc12345",
        name="Sample Lease",
        tenant="Manual Tenant",
        landlord="",
        chunk_count=5,
    )
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", store)
    return store


def test_refresh_metadata_reports_only_fields_actually_updated(app, monkeypatch, tmp_path):
    _metadata_test_store(monkeypatch, tmp_path)
    result = MetadataExtractionResult(
        MetadataExtractionStatus.UPDATED,
        {"tenant": "LLM Tenant", "rent_amount": "$2,000/month"},
    )
    monkeypatch.setattr(
        "leasora_api.http.routes.leases.metadata_extractor.extract_result",
        AsyncMock(return_value=result),
    )

    response = TestClient(app).post("/leases/lease_abc12345/metadata")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "updated"
    assert body["updated_fields"] == ["rent_amount"]
    assert body["lease"]["tenant"] == "Manual Tenant"
    assert body["lease"]["rent_amount"] == "$2,000/month"


def test_refresh_metadata_reports_no_fields_without_false_success(app, monkeypatch, tmp_path):
    _metadata_test_store(monkeypatch, tmp_path)
    result = MetadataExtractionResult(MetadataExtractionStatus.NO_FIELDS, {})
    monkeypatch.setattr(
        "leasora_api.http.routes.leases.metadata_extractor.extract_result",
        AsyncMock(return_value=result),
    )

    response = TestClient(app).post("/leases/lease_abc12345/metadata")

    assert response.status_code == 200
    assert response.json()["status"] == "no_fields"
    assert response.json()["updated_fields"] == []


def test_refresh_metadata_surfaces_provider_failure_as_503(app, monkeypatch, tmp_path):
    _metadata_test_store(monkeypatch, tmp_path)
    result = MetadataExtractionResult(MetadataExtractionStatus.FAILED, {})
    monkeypatch.setattr(
        "leasora_api.http.routes.leases.metadata_extractor.extract_result",
        AsyncMock(return_value=result),
    )

    response = TestClient(app).post("/leases/lease_abc12345/metadata")

    assert response.status_code == 503
    assert response.json()["error_code"] == "LLMError"
