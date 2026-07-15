"""Lease metadata store: a minimal, local, JSON-file-backed registry.

Records lease-level metadata (name, tenant, landlord, chunk count, upload
timestamp) that lives alongside a lease's chunks in ChromaDB but isn't
itself a chunk. Deliberately not a database — matches this project's
single-tenant, local-v1 scope (see ADR-006). A single JSON file is
sufficient for a single developer/demo deployment; if multi-user or
concurrent-write support is ever needed, replace this with a real store
(SQLite, Postgres) behind the same ``LeaseStore`` interface.

Concurrency note: writes use atomic file replacement (write to temp +
rename) with a process-local ``threading.Lock``. The lock serializes
concurrent async handlers within the single API worker process; the
atomic rename prevents corruption if two processes race (one wins, one
retries on next read).  Both this store and ``ComparisonStore`` share
a single worker process.
"""

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from leasora_api.core.config import get_settings
from leasora_api.schemas.request import LeaseMetadata
from leasora_api.utils.timestamps import get_timestamp

logger = logging.getLogger(__name__)

# Fields not yet extracted from the document itself (no date/rent extraction
# step exists in the ingest pipeline). Surfaced as this literal placeholder
# rather than a fabricated value, so the UI can render something honest.
_UNKNOWN = "Not yet extracted"


@dataclass
class DeletionReport:
    """Audit-friendly summary of what a single lease-deletion actually removed.

    Returned by ``LeaseStore.delete`` and the broader cascade-deletion
    service so callers can verify what was purged. All counts are
    best-effort: a missing optional artifact (e.g. no PDF on disk) reports
    0, never raises.
    """

    lease_id: str
    lease_record_removed: bool = False
    pdf_removed: bool = False
    chroma_chunks_removed: int = 0
    bm25_index_entries_removed: int = 0
    query_cache_entries_removed: int = 0
    semantic_cache_entries_removed: int = 0
    age_days: float | None = None
    actor: str = "manual"
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        """True when no errors were recorded and the lease record was removed.

        The other artifacts are best-effort (a missing optional artifact
        is not an error). Callers that need a stricter success criterion
        can inspect the individual fields.
        """
        return self.lease_record_removed and not self.errors


class LeaseStore:
    """JSON-file-backed store for lease metadata, keyed by lease_id."""

    def __init__(self, path: str | Path = "data/leases.json") -> None:
        self._path = Path(path)
        self._lock = Lock()

    def _read_all(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        try:
            data: dict[str, dict[str, Any]] = json.loads(self._path.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to read lease store at %s; treating as empty.", self._path)
            return {}

    def _write_all(self, data: dict[str, dict[str, Any]]) -> None:
        """Atomically write the full store to disk.

        Writes to a temporary file in the same directory and then renames,
        so a crash mid-write never leaves a corrupted/truncated JSON file.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data, indent=2)
        # Write to a sibling temp file, then atomic-rename to the target.
        # On Windows, os.replace() is atomic within the same volume.
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._path.parent,
            suffix=".tmp",
            delete=False,
        )
        try:
            fd.write(content)
            fd.close()
            Path(fd.name).replace(self._path)
        except Exception:
            Path(fd.name).unlink(missing_ok=True)
            raise

    def add(
        self,
        lease_id: str,
        name: str,
        tenant: str,
        landlord: str,
        chunk_count: int,
    ) -> LeaseMetadata:
        """Record a newly-ingested lease's metadata.

        Args:
            lease_id: The lease's unique identifier (from ``generate_lease_id``).
            name: Human-readable lease name, as provided at upload time.
            tenant: Tenant name, as provided at upload time (may be empty).
            landlord: Landlord name, as provided at upload time (may be empty).
            chunk_count: Number of chunks the ingest pipeline produced.

        Returns:
            The stored ``LeaseMetadata`` record.
        """
        entry = {
            "id": lease_id,
            "name": name,
            "tenant": tenant or _UNKNOWN,
            "landlord": landlord or _UNKNOWN,
            "start_date": _UNKNOWN,
            "end_date": _UNKNOWN,
            "rent_amount": _UNKNOWN,
            "location": _UNKNOWN,
            "chunk_count": chunk_count,
            "created_at": get_timestamp(),
        }
        with self._lock:
            data = self._read_all()
            data[lease_id] = entry
            self._write_all(data)
        return LeaseMetadata.model_validate(entry)

    def list_all(self) -> list[LeaseMetadata]:
        """Return all recorded leases, most recently uploaded first."""
        with self._lock:
            data = self._read_all()
        entries = sorted(data.values(), key=lambda e: e.get("created_at", ""), reverse=True)
        return [LeaseMetadata.model_validate(entry) for entry in entries]

    def get(self, lease_id: str) -> LeaseMetadata | None:
        """Return a single lease's metadata, or None if not found."""
        with self._lock:
            data = self._read_all()
        entry = data.get(lease_id)
        return LeaseMetadata.model_validate(entry) if entry else None

    def update(self, lease_id: str, fields: dict[str, Any]) -> LeaseMetadata | None:
        """Patch an existing lease record with newly-extracted fields.

        Used by post-ingest metadata extraction (see
        ``services/ingest/metadata_extractor.py``) to fill in
        start_date/end_date/rent_amount/location once the LLM has extracted
        them. Only keys present in ``fields`` are overwritten; unspecified
        fields (including the ``_UNKNOWN`` placeholder) are left as-is.

        Args:
            lease_id: The lease to update.
            fields: Mapping of field name -> new value. Only recognized
                ``LeaseMetadata`` fields should be passed; unknown keys are
                stored as-is but won't validate against the schema on read.

        Returns:
            The updated ``LeaseMetadata``, or ``None`` if no lease with this
            id exists (a no-op, not an error — the caller is expected to log
            and swallow this per the upload-route error-handling contract).
        """
        with self._lock:
            data = self._read_all()
            entry = data.get(lease_id)
            if entry is None:
                return None
            # Defense-in-depth: the metadata extractor is supposed to drop
            # placeholder echoes from the LLM, but if a future caller ever
            # hands us an extracted value that still contains the literal
            # "Not yet extracted" string, silently keep the existing field
            # rather than overwriting it with garbage.
            for key, value in fields.items():
                if isinstance(value, str) and value == _UNKNOWN:
                    continue
                entry[key] = value
            data[lease_id] = entry
            self._write_all(data)
        return LeaseMetadata.model_validate(entry)

    def update_missing(
        self, lease_id: str, fields: dict[str, Any]
    ) -> LeaseMetadata | None:
        """Fill placeholder fields without overwriting user-provided metadata."""
        with self._lock:
            data = self._read_all()
            entry = data.get(lease_id)
            if entry is None:
                return None
            for key, value in fields.items():
                if key not in {
                    "tenant",
                    "landlord",
                    "start_date",
                    "end_date",
                    "rent_amount",
                    "location",
                }:
                    continue
                if entry.get(key, _UNKNOWN) != _UNKNOWN:
                    continue
                if value is None or (isinstance(value, str) and value.strip() in {"", _UNKNOWN}):
                    continue
                entry[key] = value
            data[lease_id] = entry
            self._write_all(data)
        return LeaseMetadata.model_validate(entry)

    def delete(self, lease_id: str) -> DeletionReport:
        """Remove the lease record.

        Plain-record deletion: the source PDF, Chroma chunks, BM25 index,
        and cache entries are NOT removed by this method. Use
        :func:`services.ingest.retention.purge_lease` for the
        full-cascade path that also removes those artifacts and returns
        a populated ``DeletionReport``.

        Returns:
            A ``DeletionReport`` describing what was removed (just the
            lease record; the other counters default to 0).
        """
        report = DeletionReport(lease_id=lease_id)
        with self._lock:
            data = self._read_all()
            if lease_id not in data:
                return report
            del data[lease_id]
            self._write_all(data)
        report.lease_record_removed = True
        return report


lease_store = LeaseStore(get_settings().lease_store_path)
