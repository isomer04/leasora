"""Comparison history store: a minimal, local, JSON-file-backed log.

Records each ``POST /compare`` request (``id``, ``lease_ids``, ``created_at``)
so the dashboard can show a real "Comparisons" count and history list.
Deliberately not a database — matches this project's single-tenant,
local-v1 scope (see ADR-006), same as ``services/ingest/lease_store.py``.

Concurrency note (mirrors ``LeaseStore``): writes use atomic file
replacement (write to temp + rename) guarded by a process-local
``threading.Lock``. The lock serializes concurrent writes within the
single API worker process; the atomic rename prevents corruption if two
processes race. Both this store and ``LeaseStore`` share a single
worker process.

Retention: ``add()`` trims the store down to the ``max_records`` most recent
entries after each write, so the file doesn't grow unbounded (the same
append-only growth concern ``LeaseStore`` has, addressed here instead of
silently repeated).
"""

import json
import logging
import tempfile
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

from leasora_api.core.config import get_settings
from leasora_api.utils.timestamps import get_timestamp

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RECORDS = 500
_DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class ComparisonRecord(dict[str, Any]):
    """Thin alias so callers get an explicit type name; behaves like a dict."""


class ComparisonStore:
    """JSON-file-backed store for comparison history, keyed by record id."""

    def __init__(
        self,
        path: str | Path = "data/comparisons.json",
        max_records: int = _DEFAULT_MAX_RECORDS,
    ) -> None:
        self._path = Path(path)
        self._lock = Lock()
        self._max_records = max_records

    def _read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            data: list[dict[str, Any]] = json.loads(self._path.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, OSError):
            logger.exception(
                "Failed to read comparison store at %s; treating as empty.", self._path
            )
            return []

    def _write_all(self, data: list[dict[str, Any]]) -> None:
        """Atomically write the full store to disk.

        Writes to a temporary file in the same directory and then renames,
        so a crash mid-write never leaves a corrupted/truncated JSON file.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data, indent=2)
        # Write to a sibling temp file, then atomic-rename to the target.
        # On Windows, os.replace() (via Path.replace) is atomic within the
        # same volume.
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._path.parent,
            suffix=".tmp",
            delete=False,
        )
        try:
            try:
                fd.write(content)
            finally:
                # Close before unlink: on Windows, an open handle blocks
                # deletion. Closing here also ensures the handle is released
                # whether or not the write succeeded.
                fd.close()
            Path(fd.name).replace(self._path)
        except Exception:
            # Best-effort cleanup; the original write/replace exception is
            # the one we want to surface to the caller.
            Path(fd.name).unlink(missing_ok=True)
            raise

    def add(self, lease_ids: list[str]) -> ComparisonRecord:
        """Record a completed comparison request.

        Args:
            lease_ids: The lease IDs that were compared.

        Returns:
            The stored comparison record.
        """
        entry: dict[str, Any] = {
            "id": f"cmp_{uuid.uuid4().hex[:8]}",
            "lease_ids": lease_ids,
            "created_at": get_timestamp(),
        }
        with self._lock:
            data = self._read_all()
            data.append(entry)
            # Retention: keep only the N most recent records (list is stored
            # oldest-first, so trim from the front).
            if len(data) > self._max_records:
                data = data[-self._max_records :]
            self._write_all(data)
        return ComparisonRecord(entry)

    def count(self) -> int:
        """Return the total number of recorded comparisons."""
        with self._lock:
            data = self._read_all()
        return len(data)

    def list_page(
        self, page: int = 1, page_size: int = _DEFAULT_PAGE_SIZE
    ) -> tuple[list[ComparisonRecord], int]:
        """Return a bounded page of comparison history, most recent first.

        Args:
            page: 1-indexed page number. Values below 1 are treated as 1.
            page_size: Records per page, capped server-side at
                ``MAX_PAGE_SIZE`` regardless of what's requested.

        Returns:
            Tuple of (records for this page, total record count).
        """
        page = max(1, page)
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))

        with self._lock:
            data = self._read_all()

        total = len(data)
        # Stored oldest-first; present most-recent-first.
        newest_first = list(reversed(data))
        start = (page - 1) * page_size
        end = start + page_size
        page_records = [ComparisonRecord(entry) for entry in newest_first[start:end]]
        return page_records, total


comparison_store = ComparisonStore(
    get_settings().comparison_store_path,
    max_records=get_settings().comparison_store_max_records,
)
