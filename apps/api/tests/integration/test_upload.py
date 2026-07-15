"""Integration test: POST /upload actually ingests the PDF.

Uses the real ChromaStore/IngestPipeline singletons (as the route does) but
points ChromaStore at a temp persist_dir so this test doesn't pollute the
developer's real ``data/chroma``.
"""

from fastapi.testclient import TestClient

from leasora_api.services.eval.runner import DEFAULT_DEMO_LEASE_PDF
from leasora_api.services.ingest.lease_store import LeaseStore
from leasora_api.services.ingest.pipeline import IngestPipeline
from leasora_api.services.retrieval.vector_store import ChromaStore


def test_upload_ingests_pdf_and_returns_real_lease_id(app, monkeypatch, tmp_path):
    if not DEFAULT_DEMO_LEASE_PDF.exists():
        import pytest

        pytest.skip("demo_lease.pdf fixture not present")

    test_store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="upload-test")
    test_pipeline = IngestPipeline(vector_store=test_store)
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    # Patching Details: Import Binding
    # ================================
    # The upload route uses `from ...pipeline import pipeline`, which binds
    # the name into the route's module namespace at import time. Patching the
    # source module's `pipeline` attribute would not affect this already-bound
    # reference. We must patch the route's own module namespace to intercept
    # the lookup.
    #
    # Best practice: Dependency injection (passing pipeline as a parameter)
    # avoids this fragile import-binding pattern and makes mocking explicit
    # in the function signature. For now, this patch location is correct and
    # matches Starlette's module-import semantics.
    monkeypatch.setattr("leasora_api.http.routes.upload.pipeline", test_pipeline)
    monkeypatch.setattr("leasora_api.http.routes.upload.lease_store", test_lease_store)
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    client = TestClient(app)

    with DEFAULT_DEMO_LEASE_PDF.open("rb") as pdf_file:
        response = client.post(
            "/upload",
            files={"file": ("demo_lease.pdf", pdf_file, "application/pdf")},
            data={"name": "Test Upload Lease", "tenant": "", "landlord": ""},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["lease_id"].startswith("lease_")
    assert body["lease_id"] != "placeholder-id"

    # The lease must actually be queryable now (real chunks in the store).
    import asyncio

    chunks = asyncio.run(test_store.get_by_lease(body["lease_id"]))
    assert len(chunks) > 0

    # And it must show up in the lease list/detail endpoints.
    list_response = client.get("/leases")
    assert list_response.status_code == 200
    listed = list_response.json()
    assert any(lease["id"] == body["lease_id"] for lease in listed)

    detail_response = client.get(f"/leases/{body['lease_id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "Test Upload Lease"


def test_upload_rejects_non_pdf_content_type(app):
    client = TestClient(app)
    response = client.post(
        "/upload",
        files={"file": ("not_a_lease.txt", b"hello world", "text/plain")},
        data={"name": "Bad Upload"},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "ValidationError"


def test_upload_rejects_spoofed_pdf_via_magic_bytes(app):
    """A non-PDF payload disguised with a ``.pdf`` name + PDF content-type
    is still rejected — the extension/Content-Type whitelist alone
    (``test_upload_rejects_non_pdf_content_type`` above) would pass this,
    since both signals are client-controlled. Only the real byte stream
    (``core.validators.validate_pdf_magic_bytes``) catches it.
    """
    client = TestClient(app)
    response = client.post(
        "/upload",
        files={
            "file": (
                "fake.pdf",
                b"<html><body>not a real pdf</body></html>",
                "application/pdf",
            )
        },
        data={"name": "Spoofed Upload"},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "ValidationError"


def test_upload_runs_metadata_extraction_and_updates_lease_store(app, monkeypatch, tmp_path):
    """After ingest, upload.py should call the extractor and patch lease_store."""
    if not DEFAULT_DEMO_LEASE_PDF.exists():
        import pytest

        pytest.skip("demo_lease.pdf fixture not present")

    test_store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="upload-extract-test")
    test_pipeline = IngestPipeline(vector_store=test_store)
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    monkeypatch.setattr("leasora_api.http.routes.upload.pipeline", test_pipeline)
    monkeypatch.setattr("leasora_api.http.routes.upload.lease_store", test_lease_store)
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    async def fake_extract(lease_id: str) -> dict[str, str]:
        return {"rent_amount": "$3,000/month", "location": "123 Main St"}

    monkeypatch.setattr(
        "leasora_api.http.routes.upload.metadata_extractor.extract", fake_extract
    )

    client = TestClient(app)
    with DEFAULT_DEMO_LEASE_PDF.open("rb") as pdf_file:
        response = client.post(
            "/upload",
            files={"file": ("demo_lease.pdf", pdf_file, "application/pdf")},
            data={"name": "Extraction Test Lease", "tenant": "", "landlord": ""},
        )

    assert response.status_code == 200
    lease_id = response.json()["lease_id"]

    detail_response = client.get(f"/leases/{lease_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["rent_amount"] == "$3,000/month"
    assert detail["location"] == "123 Main St"
    # Fields not returned by the extractor should keep their placeholder.
    assert detail["start_date"] == "Not yet extracted"


def test_upload_succeeds_even_when_extraction_raises(app, monkeypatch, tmp_path):
    """Extraction failures must never fail the upload response."""
    if not DEFAULT_DEMO_LEASE_PDF.exists():
        import pytest

        pytest.skip("demo_lease.pdf fixture not present")

    test_store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="upload-extract-fail-test")
    test_pipeline = IngestPipeline(vector_store=test_store)
    test_lease_store = LeaseStore(tmp_path / "leases.json")
    monkeypatch.setattr("leasora_api.http.routes.upload.pipeline", test_pipeline)
    monkeypatch.setattr("leasora_api.http.routes.upload.lease_store", test_lease_store)
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    async def failing_extract(lease_id: str) -> dict[str, str]:
        raise RuntimeError("LLM is down")

    monkeypatch.setattr(
        "leasora_api.http.routes.upload.metadata_extractor.extract", failing_extract
    )

    client = TestClient(app)
    with DEFAULT_DEMO_LEASE_PDF.open("rb") as pdf_file:
        response = client.post(
            "/upload",
            files={"file": ("demo_lease.pdf", pdf_file, "application/pdf")},
            data={"name": "Extraction Failure Test Lease", "tenant": "", "landlord": ""},
        )

    assert response.status_code == 200
    lease_id = response.json()["lease_id"]

    detail_response = client.get(f"/leases/{lease_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["rent_amount"] == "Not yet extracted"
