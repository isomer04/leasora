"""PII-aware lease deletion policy.

Lease PDFs are the highest-sensitivity artifact this system handles. The
reachable ``DELETE /leases/{id}`` route calls :func:`purge_lease`, which
cascade-deletes a lease's source PDF, Chroma chunks, BM25 index, cached answers,
and metadata record. :func:`age_days_for_lease` supplies audit metadata for the
returned ``DeletionReport``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from leasora_api.core.config import get_settings
from leasora_api.core.validators import validate_lease_id
from leasora_api.services.ingest.lease_store import DeletionReport, lease_store
from leasora_api.services.retrieval.bm25_index import bm25_cache
from leasora_api.services.retrieval.query_cache import query_cache
from leasora_api.services.retrieval.semantic_cache import cache as semantic_cache
from leasora_api.services.retrieval.vector_store import chroma

logger = logging.getLogger(__name__)


def age_days_for_lease(created_at: str, *, now: datetime | None = None) -> float | None:
    """Return the age in days for a lease's ``created_at`` ISO timestamp.

    Args:
        created_at: The lease's ISO ``created_at`` timestamp.
        now: Override for the current time (testing). When ``None``,
            ``datetime.now(timezone.utc)`` is used.

    Returns:
        Age in days as a float, or ``None`` if ``created_at`` is missing or
        unparseable.
    """
    if not created_at:
        return None
    try:
        # Tolerate the trailing ``Z`` and a naive timestamp (no tz).
        ts = created_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
    except ValueError:
        logger.warning("Unparseable created_at timestamp: %r", created_at)
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now is None:
        now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 86400.0


async def purge_lease(
    lease_id: str,
    *,
    actor: str = "manual",
) -> DeletionReport:
    """Fully cascade-delete a lease and every artifact derived from it.

    Best-effort: each step logs and continues on error (so a missing
    file or a chroma race doesn't leave the lease half-deleted), but the
    returned ``DeletionReport`` records what was actually removed so
    callers (and the audit log) can verify.

    The lease metadata record is deleted *last*, after every derived artifact.
    If an earlier step fails (for example, a locked file on Windows or a
    Chroma error), the record stays in place so a retried ``DELETE`` can find
    and finish the cascade instead of orphaning derived artifacts.

    Args:
        lease_id: The lease to purge.
        actor: Caller label stored on the report for the audit trail.

    Returns:
        A populated ``DeletionReport``. ``report.succeeded`` is ``True``
        when no errors occurred AND the lease record was removed.
    """
    validate_lease_id(lease_id)
    report = DeletionReport(lease_id=lease_id, actor=actor)

    # Compute age (best-effort) before we delete the record's timestamp.
    existing = lease_store.get(lease_id)
    if existing is not None:
        created = getattr(existing, "created_at", None)
        report.age_days = age_days_for_lease(created) if created else None

    # 1. Source PDF on disk (server-generated filename: <upload_dir>/<id>.pdf).
    try:
        pdf_path = Path(get_settings().upload_dir) / f"{lease_id}.pdf"
        if pdf_path.exists():
            pdf_path.unlink()
            report.pdf_removed = True
    except Exception as exc:
        report.errors.append(f"pdf_unlink: {exc!r}")

    # 2. Chroma chunks — awaited directly so the report's chunk count and
    # any failure are known before we decide whether to remove the record.
    try:
        chunks = await chroma.get_by_lease(lease_id)
        report.chroma_chunks_removed = len(chunks)
        await chroma.delete_by_lease(lease_id)
    except Exception as exc:
        report.errors.append(f"vector_store.delete_by_lease: {exc!r}")

    # 3. BM25 index entry.
    try:
        report.bm25_index_entries_removed = bm25_cache.evict_lease(lease_id)
    except Exception as exc:
        report.errors.append(f"bm25_cache.evict_lease: {exc!r}")

    # 4. QueryCache (exact-hash answers).
    try:
        report.query_cache_entries_removed = query_cache.evict_lease(lease_id)
    except Exception as exc:
        report.errors.append(f"query_cache.evict_lease: {exc!r}")

    # 5. SemanticCache (near-duplicate answers).
    try:
        report.semantic_cache_entries_removed = semantic_cache.evict_lease(lease_id)
    except Exception as exc:
        report.errors.append(f"semantic_cache.evict_lease: {exc!r}")

    # 6. Lease metadata record (synchronous JSON-file write) — last, and
    # only when every artifact step above succeeded. A mid-cascade failure
    # leaves the record in place so a retried DELETE can find and finish the
    # job instead of orphaning derived artifacts.
    if not report.errors:
        try:
            record_report = lease_store.delete(lease_id)
            report.lease_record_removed = record_report.lease_record_removed
        except Exception as exc:
            report.errors.append(f"lease_store.delete: {exc!r}")

    # Audit log: every deletion is recorded with lease_id, age, and actor.
    logger.info(
        "purge_lease lease_id=%s actor=%s age_days=%s "
        "lease_record_removed=%s pdf_removed=%s chroma_chunks_removed=%d "
        "bm25=%d query_cache=%d semantic_cache=%d errors=%d",
        lease_id,
        actor,
        report.age_days,
        report.lease_record_removed,
        report.pdf_removed,
        report.chroma_chunks_removed,
        report.bm25_index_entries_removed,
        report.query_cache_entries_removed,
        report.semantic_cache_entries_removed,
        len(report.errors),
    )
    return report


async def purge_expired_leases(
    retention_days: int | None = None,
    *,
    now: datetime | None = None,
) -> list[DeletionReport]:
    """Cascade-delete every lease at or beyond the configured retention age.

    Malformed timestamps are skipped, and a failure purging one lease is logged
    without preventing the remaining eligible leases from being processed.
    """
    days = (
        get_settings().upload_retention_days
        if retention_days is None
        else retention_days
    )
    if days < 1:
        raise ValueError(f"retention_days must be >= 1, got {days}")

    try:
        leases = lease_store.list_all()
    except Exception:
        logger.exception("Retention sweep could not list leases")
        return []

    reports: list[DeletionReport] = []
    for lease in leases:
        age_days = age_days_for_lease(lease.created_at or "", now=now)
        if age_days is None or age_days < days:
            continue
        try:
            report = await purge_lease(lease.id, actor="retention")
        except Exception:
            logger.exception("Retention purge failed for lease_id=%s", lease.id)
            continue
        reports.append(report)
        if report.errors:
            logger.warning(
                "Retention purge incomplete for lease_id=%s errors=%s",
                lease.id,
                report.errors,
            )

    logger.info(
        "Retention sweep complete retention_days=%d eligible=%d succeeded=%d",
        days,
        len(reports),
        sum(report.succeeded for report in reports),
    )
    return reports
