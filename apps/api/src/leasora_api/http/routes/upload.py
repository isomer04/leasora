"""Lease document upload endpoint.

Clean code design:
- Route focuses on HTTP file handling only
- Delegates to service layer for actual processing
- Uses domain exceptions (caught by middleware)
- Input validation is explicit and centralized

Security Note:
- File type validated to prevent malicious uploads
- File size checked to prevent DoS
- Metadata fields validated for length
"""

import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile

from leasora_api.core.config import get_settings
from leasora_api.core.metrics import record_upload, record_upload_latency
from leasora_api.core.validators import (
    validate_upload_file_type,
    validate_upload_file_size,
    validate_pdf_magic_bytes,
    validate_lease_name,
    validate_metadata_field,
)
from leasora_api.http.deps import enforce_rate_limit
from leasora_api.schemas.response import UploadResponse
from leasora_api.services.ingest.lease_store import lease_store
from leasora_api.services.ingest.metadata_extractor import metadata_extractor
from leasora_api.services.ingest.pipeline import pipeline
from leasora_api.utils.identifiers import generate_lease_id

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=UploadResponse,
    summary="Upload a lease document",
    description="Upload a PDF lease document for analysis",
    dependencies=[Depends(enforce_rate_limit)],
    responses={
        200: {"description": "Lease uploaded successfully"},
        400: {"description": "Invalid file or metadata"},
        413: {"description": "File too large"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def upload_file(
    file: UploadFile = File(..., description="PDF lease document"),
    name: str = Form(..., description="Lease name"),
    tenant: str = Form(default="", description="Tenant name"),
    landlord: str = Form(default="", description="Landlord name"),
) -> UploadResponse:
    """Upload a lease PDF, ingest it, and make it queryable via /ask.

    The system will:
    1. Extract text per page from the PDF
    2. Chunk it clause-aware and tag each chunk with a heuristic clause type
    3. Embed chunks and store them in ChromaDB, scoped by the new lease_id
    4. Make the lease queryable via the /ask endpoint

    Args:
        file: PDF file (max 50MB)
        name: Human-readable lease name
        tenant: Optional tenant name (not yet persisted; reserved for a
            future lease-metadata store)
        landlord: Optional landlord name (same as above)

    Returns:
        Upload status with the real lease ID and chunk count.

    Raises:
        ValidationError: If file or metadata invalid.
        IngestError: If PDF parsing, chunking, embedding, or storage fails
            (e.g. a scanned/image-only PDF with no extractable text).
    """
    validate_upload_file_type(file.content_type or "")
    # Fail fast before writing to disk
    validate_lease_name(name)
    if tenant:
        validate_metadata_field("tenant", tenant)
    if landlord:
        validate_metadata_field("landlord", landlord)

    # Stream the upload to a temp file in chunks to avoid pinning the full
    # 50MB in memory. This keeps memory usage bounded regardless of upload
    # size, then we validate size from what was actually written.
    lease_id = generate_lease_id()
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Store under a server-generated filename (lease_id, not the client's
    # filename) to avoid path traversal / filename-spoofing from user input.
    pdf_path = upload_dir / f"{lease_id}.pdf"

    total_bytes = 0
    chunk_size = 64 * 1024  # 64 KiB chunks
    # Buffer of the first N bytes so we can validate the PDF magic-byte
    # signature before writing the rest to disk.
    pdf_magic_window: bytes = b""
    # Per-request upload timer. ``try/finally`` ensures we
    # observe latency even on validation/ingest failures.
    upload_started = time.perf_counter()
    ingest_status = "ok"
    try:
        with pdf_path.open("wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                # Early rejection: stop writing as soon as we exceed the limit
                if total_bytes > settings.max_upload_size_bytes:
                    break
                # Capture the first ~8 bytes for magic-byte validation. We
                # only need the first 4 (``%PDF``) but buffer an extra few
                # bytes so the matching prefix includes ``%PDF-1.x`` style
                # headers.
                if len(pdf_magic_window) < 8:
                    pdf_magic_window = (
                        pdf_magic_window + chunk[: 8 - len(pdf_magic_window)]
                    )
                f.write(chunk)

        # Magic-byte Validation: Defense-in-Depth
        # ========================================
        # This validation MUST happen BEFORE handing the file to the ingest
        # pipeline. We validate after streaming (not before) so that a client
        # lying about Content-Type is still caught. The validation here is the
        # only defense against spoofing; the extension and Content-Type are
        # client-controlled signals.
        #
        # The ingest pipeline assumes files are already validated. If you add
        # code that uses the file earlier (before this line), move this
        # validation to that point.
        validate_pdf_magic_bytes(pdf_magic_window)

        # Validate file size; oversized uploads are cleaned up below
        validate_upload_file_size(total_bytes)

        result = await pipeline.ingest(str(pdf_path), lease_id=lease_id)
    except Exception as error:
        ingest_status = type(error).__name__
        # Clean up the saved file on any failure (oversized, ingest error,
        # unexpected exception) so failed uploads don't accumulate orphaned
        # PDFs on disk.
        pdf_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
        elapsed_ms = (time.perf_counter() - upload_started) * 1_000.0
        record_upload_latency(elapsed_ms)
        record_upload(ingest_status)

    lease_store.add(
        lease_id=lease_id,
        name=name,
        tenant=tenant,
        landlord=landlord,
        chunk_count=result["chunk_count"],
    )

    logger.info(
        "Ingested lease %s: %d chunks from %s", lease_id, result["chunk_count"], name
    )

    # Extraction runs inline: the detail page shows real values
    # immediately at the cost of a slower upload response.
    try:
        extracted_fields = await metadata_extractor.extract(lease_id)
        if extracted_fields:
            lease_store.update_missing(lease_id, extracted_fields)
    except Exception:
        logger.exception("Metadata extraction/update failed for lease %s", lease_id)

    return UploadResponse(
        lease_id=lease_id,
        name=name,
        status="complete",
        message=f"Lease uploaded and analyzed: {result['chunk_count']} chunks indexed.",
    )
