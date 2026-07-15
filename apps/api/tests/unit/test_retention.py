"""Tests for ``services.ingest.retention``.

Two contracts are pinned here:

1. ``purge_lease`` removes the PDF, lease record, Chroma chunks, BM25 index,
   QueryCache entries, and SemanticCache entries. The returned
   ``DeletionReport`` records what was actually removed. The lease record is
   removed last, so a mid-cascade failure leaves it in place for a retry.
2. A failure in any cascade step is captured on ``report.errors`` rather than
   raising and does not prevent the remaining steps from running.

``purge_lease`` touches module-level storage/cache singletons, so every test
replaces them with lightweight fakes via ``_stub_retention_singletons``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from leasora_api.core.config import get_settings
from leasora_api.services.ingest.lease_store import (
    DeletionReport,
    LeaseStore,
)
from leasora_api.services.ingest.retention import (
    age_days_for_lease,
    purge_lease,
)


class _FakeChroma:
    """Stand-in for the real ``ChromaStore`` singleton."""

    def __init__(self, chunks: list[dict] | None = None, raise_on_delete: bool = False) -> None:
        self.chunks = chunks if chunks is not None else []
        self.deleted: list[str] = []
        self._raise_on_delete = raise_on_delete

    async def get_by_lease(self, lease_id: str) -> list[dict]:
        return self.chunks

    async def delete_by_lease(self, lease_id: str) -> None:
        if self._raise_on_delete:
            raise RuntimeError("chroma delete failed")
        self.deleted.append(lease_id)


class _FakeEvictCache:
    """Stand-in for the real BM25/query/semantic cache singletons."""

    def __init__(self, count: int = 0) -> None:
        self.count = count
        self.evicted: list[str] = []

    def evict_lease(self, lease_id: str) -> int:
        self.evicted.append(lease_id)
        return self.count


@pytest.fixture(autouse=True)
def _stub_retention_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the real Chroma/cache singletons ``retention.py`` imports.

    Without this, ``purge_lease`` runs against a real on-disk ChromaDB
    (``data/chroma``) and the real global BM25/query/semantic caches —
    tests would be side-effectful and environment-coupled. Individual
    tests can still ``monkeypatch.setattr`` again for custom behavior
    (e.g. a chroma that raises).
    """
    monkeypatch.setattr("leasora_api.services.ingest.retention.chroma", _FakeChroma())
    monkeypatch.setattr("leasora_api.services.ingest.retention.bm25_cache", _FakeEvictCache())
    monkeypatch.setattr("leasora_api.services.ingest.retention.query_cache", _FakeEvictCache())
    monkeypatch.setattr("leasora_api.services.ingest.retention.semantic_cache", _FakeEvictCache())


@pytest.fixture(autouse=True)
def _isolated_upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ``upload_dir`` at a tmp, empty directory for every test.

    Prevents a test that forgets to set ``upload_dir`` from unlinking a
    real file under the developer's ``data/uploads``.
    """
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))


# Age helper.

def test_age_days_for_lease_returns_none_for_empty() -> None:
    assert age_days_for_lease("") is None, "age_days_for_lease must return None for empty string"


def test_age_days_for_lease_returns_none_for_unparseable() -> None:
    assert age_days_for_lease("not-a-timestamp") is None, (
        "age_days_for_lease must return None for unparseable timestamp"
    )


def test_age_days_for_lease_known_age() -> None:
    """A timestamp 5 days in the past returns ~5.0."""
    five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    age = age_days_for_lease(five_days_ago)
    assert age is not None, "age_days_for_lease must parse valid ISO timestamp"
    assert 4.99 < age < 5.01, "Age calculation must be accurate to within 0.01 days"


def test_age_days_for_lease_respects_now_override() -> None:
    """Passing ``now=`` makes the age computation deterministic."""
    created = datetime(2020, 1, 1, tzinfo=timezone.utc)
    now = datetime(2020, 1, 11, tzinfo=timezone.utc)
    age = age_days_for_lease(created.isoformat(), now=now)
    assert age == pytest.approx(10.0), "Age calculation with now override must be exactly 10.0 days"


# purge_lease — primitive contract.

async def test_purge_lease_removes_record_and_returns_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``purge_lease`` removes the lease record and reports it."""
    store = LeaseStore(tmp_path / "leases.json")
    store.add("lease_test", "Test", "", "", 0)

    monkeypatch.setattr("leasora_api.services.ingest.retention.lease_store", store)

    report = await purge_lease("lease_test", actor="manual")
    assert isinstance(report, DeletionReport), "purge_lease must return a DeletionReport"
    assert report.lease_record_removed is True, "purge_lease must mark record as removed"
    assert store.get("lease_test") is None, "Record must be deleted from store after purge"


async def test_purge_lease_missing_lease_returns_clean_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A purge for a non-existent lease returns a report with no flags set."""
    store = LeaseStore(tmp_path / "leases.json")
    monkeypatch.setattr("leasora_api.services.ingest.retention.lease_store", store)

    report = await purge_lease("lease_never_existed", actor="manual")
    assert report.lease_record_removed is False, "Non-existent lease must not be marked as removed"
    assert report.errors == [], "Purging non-existent lease should not generate errors"


async def test_purge_lease_removes_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The source PDF on disk is removed."""
    store = LeaseStore(tmp_path / "leases.json")
    store.add("lease_test", "Test", "", "", 0)
    monkeypatch.setattr("leasora_api.services.ingest.retention.lease_store", store)

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    pdf_path = upload_dir / "lease_test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(get_settings(), "upload_dir", str(upload_dir))

    report = await purge_lease("lease_test", actor="manual")
    assert report.pdf_removed is True, "purge_lease must remove the PDF file"
    assert not pdf_path.exists(), "PDF file must be deleted from disk"


async def test_purge_lease_no_pdf_reports_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A purge when no PDF exists reports pdf_removed=False but no error."""
    store = LeaseStore(tmp_path / "leases.json")
    store.add("lease_test", "Test", "", "", 0)
    monkeypatch.setattr("leasora_api.services.ingest.retention.lease_store", store)

    report = await purge_lease("lease_test", actor="manual")
    assert report.pdf_removed is False, "Missing PDF must report pdf_removed=False"
    assert report.lease_record_removed is True, "Lease record must still be removed despite missing PDF"
    assert report.errors == [], "Missing PDF must not generate an error"


async def test_purge_lease_records_actor_on_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``actor`` argument is preserved on the report for audit purposes."""
    store = LeaseStore(tmp_path / "leases.json")
    store.add("lease_test", "Test", "", "", 0)
    monkeypatch.setattr("leasora_api.services.ingest.retention.lease_store", store)

    report = await purge_lease("lease_test", actor="admin")
    assert report.actor == "admin", "Report must preserve the actor string for audit trail"


async def test_purge_lease_removes_chroma_bm25_and_cache_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Chroma/BM25/query-cache/semantic-cache steps are awaited and counted."""
    store = LeaseStore(tmp_path / "leases.json")
    store.add("lease_test", "Test", "", "", 0)
    monkeypatch.setattr("leasora_api.services.ingest.retention.lease_store", store)

    fake_chroma = _FakeChroma(chunks=[{"id": "c1"}, {"id": "c2"}])
    monkeypatch.setattr("leasora_api.services.ingest.retention.chroma", fake_chroma)
    monkeypatch.setattr(
        "leasora_api.services.ingest.retention.bm25_cache", _FakeEvictCache(count=1)
    )
    monkeypatch.setattr(
        "leasora_api.services.ingest.retention.query_cache", _FakeEvictCache(count=3)
    )
    monkeypatch.setattr(
        "leasora_api.services.ingest.retention.semantic_cache", _FakeEvictCache(count=2)
    )

    report = await purge_lease("lease_test", actor="manual")
    assert report.chroma_chunks_removed == 2, "purge_lease must remove all Chroma chunks"
    assert report.bm25_index_entries_removed == 1, "purge_lease must remove BM25 index entries"
    assert report.query_cache_entries_removed == 3, "purge_lease must remove query cache entries"
    assert report.semantic_cache_entries_removed == 2, "purge_lease must remove semantic cache entries"
    assert fake_chroma.deleted == ["lease_test"], "Chroma delete must be called with correct lease_id"
    assert report.errors == [], "Successful purge must not generate errors"


async def test_purge_lease_captures_chroma_failure_and_keeps_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Chroma failure is captured on ``report.errors`` and does not stop the cascade.

    The lease record is only removed *after* every artifact step, so a
    failing Chroma delete leaves the record in place for a retry instead of
    orphaning the still-present chunks.
    """
    store = LeaseStore(tmp_path / "leases.json")
    store.add("lease_test", "Test", "", "", 0)
    monkeypatch.setattr("leasora_api.services.ingest.retention.lease_store", store)
    monkeypatch.setattr(
        "leasora_api.services.ingest.retention.chroma",
        _FakeChroma(raise_on_delete=True),
    )

    report = await purge_lease("lease_test", actor="manual")

    assert len(report.errors) == 1, "Chroma failure must be recorded in errors list"
    assert "vector_store.delete_by_lease" in report.errors[0], "Error message must reference failed operation"
    # Later cascade steps still ran despite the Chroma failure.
    assert report.bm25_index_entries_removed == 0, "BM25 cache must still be evicted after Chroma failure"
    assert report.query_cache_entries_removed == 0, "Query cache must still be evicted after Chroma failure"
    assert report.semantic_cache_entries_removed == 0, "Semantic cache must still be evicted after Chroma failure"
    assert report.succeeded is False, "Report must mark operation as failed"


async def test_purge_lease_inside_running_event_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``purge_lease`` (a coroutine) can be awaited from a running event loop."""
    store = LeaseStore(tmp_path / "leases.json")
    store.add("lease_async", "Async", "", "", 0)
    monkeypatch.setattr("leasora_api.services.ingest.retention.lease_store", store)

    fake_chroma = _FakeChroma()
    monkeypatch.setattr("leasora_api.services.ingest.retention.chroma", fake_chroma)

    report = await purge_lease("lease_async", actor="manual")

    assert isinstance(report, DeletionReport), "purge_lease must return DeletionReport instance"
    assert report.errors == [], "Successful purge must have no errors"
    assert fake_chroma.deleted == ["lease_async"], "Chroma delete must be called for the lease"


# LeaseStore.delete is callable standalone (record-only path).

def test_lease_store_delete_returns_deletion_report(tmp_path: Path) -> None:
    """``LeaseStore.delete`` returns a DeletionReport (audit-friendly)."""
    store = LeaseStore(tmp_path / "leases.json")
    store.add("lease_test", "Test", "", "", 0)

    report = store.delete("lease_test")
    assert isinstance(report, DeletionReport), "LeaseStore.delete must return a DeletionReport"
    assert report.lease_record_removed is True, "Report must indicate record was removed"
    assert store.get("lease_test") is None, "Record must be deleted from store"


def test_lease_store_delete_missing_lease(tmp_path: Path) -> None:
    """Deleting a non-existent lease returns an empty report (no error)."""
    store = LeaseStore(tmp_path / "leases.json")
    report = store.delete("lease_never_existed")
    assert report.lease_record_removed is False, "Non-existent lease must not be marked as removed"
    assert report.errors == [], "Deleting non-existent lease must not generate errors"
