"""Lease management endpoints.

Clean code design:
- Routes focus on HTTP interface only
- Delegates to the lease metadata store for persistence
- Uses domain exceptions (caught by middleware)

Note: ``LeaseStore`` is a minimal local JSON-file-backed store (see
``services/ingest/lease_store.py``), not a database. It records what's known
at upload time (name, tenant, landlord, chunk count); fields not yet
extracted from the document itself (dates, rent amount, location) are
surfaced as an explicit placeholder rather than a fabricated value.
"""

from fastapi import APIRouter, Depends

from leasora_api.core.exceptions import LLMError, NotFoundError
from leasora_api.core.security import redact_pii
from leasora_api.core.validators import validate_lease_id
from leasora_api.http.deps import enforce_rate_limit
from leasora_api.schemas.domain import MetadataExtractionStatus
from leasora_api.schemas.request import LeaseMetadata
from leasora_api.schemas.response import ChunkResponse, MetadataRefreshResponse
from leasora_api.services.ingest.lease_store import DeletionReport, lease_store
from leasora_api.services.ingest.metadata_extractor import metadata_extractor
from leasora_api.services.ingest.retention import purge_lease
from leasora_api.services.retrieval.vector_store import chroma

router = APIRouter()


@router.get(
    "",
    response_model=list[LeaseMetadata],
    summary="List all leases",
    description="Retrieve all uploaded leases",
    responses={
        200: {"description": "List of leases"},
        500: {"description": "Server error"},
    },
)
async def list_leases() -> list[LeaseMetadata]:
    """Retrieve a list of all uploaded lease documents.

    Returns:
        All leases recorded by the lease store, most recently uploaded first.
    """
    return lease_store.list_all()


@router.get(
    "/{lease_id}",
    response_model=LeaseMetadata,
    summary="Get a specific lease",
    description="Retrieve detailed information about a lease",
    responses={
        200: {"description": "Lease details"},
        404: {"description": "Lease not found"},
    },
)
async def get_lease(lease_id: str) -> LeaseMetadata:
    """Retrieve full details of a specific lease.

    Args:
        lease_id: Unique lease identifier

    Raises:
        ValidationError: If lease_id format is invalid.
        NotFoundError: If no lease with this ID has been uploaded.
    """
    validate_lease_id(lease_id)
    lease = lease_store.get(lease_id)
    if lease is None:
        raise NotFoundError(f"Lease {lease_id} not found")
    return lease


@router.post(
    "/{lease_id}/metadata",
    response_model=MetadataRefreshResponse,
    summary="Extract or retry lease metadata",
    description="Extract missing lease summary fields from its indexed clauses",
    dependencies=[Depends(enforce_rate_limit)],
    responses={
        200: {"description": "Extraction completed"},
        404: {"description": "Lease not found"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "Metadata provider unavailable"},
    },
)
async def refresh_lease_metadata(lease_id: str) -> MetadataRefreshResponse:
    """Retry extraction with explicit status and updated-field reporting."""
    validate_lease_id(lease_id)
    lease = lease_store.get(lease_id)
    if lease is None:
        raise NotFoundError(f"Lease {lease_id} not found")

    result = await metadata_extractor.extract_result(lease_id)
    if result.status == MetadataExtractionStatus.FAILED:
        raise LLMError("Metadata extraction is temporarily unavailable")
    if not result.fields:
        return MetadataRefreshResponse(
            status=MetadataExtractionStatus.NO_FIELDS,
            updated_fields=[],
            lease=lease,
        )

    updated = lease_store.update_missing(lease_id, result.fields)
    if updated is None:
        raise NotFoundError(f"Lease {lease_id} not found")

    updated_fields = [
        field
        for field in result.fields
        if getattr(lease, field) != getattr(updated, field)
    ]
    status = (
        MetadataExtractionStatus.UPDATED
        if updated_fields
        else MetadataExtractionStatus.NO_FIELDS
    )
    return MetadataRefreshResponse(
        status=status,
        updated_fields=updated_fields,
        lease=updated,
    )


@router.get(
    "/{lease_id}/chunks",
    response_model=list[ChunkResponse],
    summary="List a lease's indexed chunks",
    description="Retrieve all indexed clauses/chunks for a lease, sorted by page",
    responses={
        200: {"description": "List of chunks (empty if none indexed)"},
        404: {"description": "Lease not found"},
    },
)
async def get_lease_chunks(lease_id: str) -> list[ChunkResponse]:
    """Retrieve all indexed chunks for a lease, sorted by page number.

    Args:
        lease_id: Unique lease identifier.

    Returns:
        All chunks stored in the vector store for this lease, sorted by
        ``metadata["page"]`` ascending (``get_by_lease`` itself returns
        chunks unordered). Empty list if the lease exists but has no
        indexed chunks.

    Raises:
        ValidationError: If lease_id format is invalid.
        NotFoundError: If no lease with this ID has been uploaded.
    """
    validate_lease_id(lease_id)
    lease = lease_store.get(lease_id)
    if lease is None:
        raise NotFoundError(f"Lease {lease_id} not found")

    chunks = await chroma.get_by_lease(lease_id)
    # `page` is always set at ingest time (see IngestPipeline.ingest), but
    # fall back to 0 defensively so a missing/legacy value sorts first
    # rather than raising.
    sorted_chunks = sorted(chunks, key=lambda chunk: chunk["metadata"].get("page", 0) or 0)

    return [
        ChunkResponse(
            id=chunk["id"],
            # Full chunk text is shown to the user (verbatim clause excerpt),
            # same trust boundary as AskResponse.sources[*].excerpt in
            # query_service — regex-catchable PII (SSN/CC/email/phone) is
            # redacted at this API boundary.
            text=redact_pii(chunk["text"]),
            clause_type=str(chunk["metadata"].get("clause_type", "other")),
            page=chunk["metadata"].get("page"),
            source=chunk["metadata"].get("source"),
        )
        for chunk in sorted_chunks
    ]


@router.delete(
    "/{lease_id}",
    response_model=DeletionReport,
    summary="Delete a lease and all derived artifacts",
    description=(
        "Cascade-delete a lease's PDF, Chroma chunks, BM25 index entries, "
        "and any cached answers for it. Returns a "
        "``DeletionReport`` describing what was removed."
    ),
    responses={
        200: {"description": "DeletionReport describing what was removed"},
        404: {"description": "Lease not found"},
        500: {"description": "Server error"},
    },
)
async def delete_lease(lease_id: str) -> DeletionReport:
    """Fully cascade-delete a lease and every artifact derived from it.

    Args:
        lease_id: Unique lease identifier.

    Returns:
        A ``DeletionReport`` describing what was removed (PDF, Chroma
        chunks, BM25 entries, query/semantic cache entries, lease record).

    Raises:
        ValidationError: If lease_id format is invalid.
        NotFoundError: If no lease with this ID exists.
    """
    validate_lease_id(lease_id)
    # Existence is checked up front rather than inferred from
    # ``report.lease_record_removed``: ``purge_lease`` only removes the
    # lease record once every artifact step has succeeded (so a
    # mid-cascade failure leaves it in place for a retry), so
    # ``lease_record_removed`` can legitimately be ``False`` for a lease
    # that does exist but failed to fully purge — that should surface as
    # a 200 with ``report.errors`` populated, not a misleading 404.
    if lease_store.get(lease_id) is None:
        raise NotFoundError(f"Lease {lease_id} not found")
    return await purge_lease(lease_id, actor="manual")
