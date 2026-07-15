"""CLI subcommand for ingesting lease PDFs.

Parses command-line arguments and validates the PDF file before
submitting for ingestion. The actual ingestion logic is delegated
to the ingest service layer (IngestPipeline).
"""

import argparse
import asyncio
import sys
from pathlib import Path

from leasora_api.core.exceptions import IngestError
from leasora_api.services.ingest.pipeline import pipeline
from leasora_api.utils.identifiers import generate_lease_id


def run(argv: list[str] | None = None) -> int:
    """Ingest subcommand: leasora ingest <pdf_path> [--lease-id ID] [--idempotency-key KEY].

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        prog="leasora ingest",
        description="Ingest a lease PDF into the vector store.",
    )
    parser.add_argument("pdf_path", help="Path to lease PDF file")
    parser.add_argument(
        "--lease-id",
        help="Lease ID to store chunks under (default: generated)",
        default=None,
    )
    parser.add_argument(
        "--idempotency-key",
        help="Unique key for idempotent retries (reserved for future use)",
        default=None,
    )

    if argv is None:
        argv = sys.argv[1:]

    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 0

    try:
        _validate_pdf(args.pdf_path)
        lease_id = args.lease_id or generate_lease_id()
        result = asyncio.run(
            pipeline.ingest(args.pdf_path, lease_id=lease_id, idempotency_key=args.idempotency_key)
        )
        print(
            f"Ingested {result['chunk_count']} chunks from {result['source']} "
            f"into lease '{result['lease_id']}'"
        )
        return 0
    except IngestError as error:
        print(f"Error: {error.message}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Unexpected error: {error}", file=sys.stderr)
        return 1


def _validate_pdf(pdf_path: str) -> None:
    """Validate PDF file exists, is a file, and is non-empty before ingestion.

    Args:
        pdf_path: Path to the PDF file.

    Raises:
        IngestError: If validation fails.
    """
    pdf_file = Path(pdf_path)

    if not pdf_file.exists():
        raise IngestError(f"PDF file not found: {pdf_path}")

    if not pdf_file.is_file():
        raise IngestError(f"Path is not a file: {pdf_path}")

    if pdf_file.suffix.lower() != ".pdf":
        raise IngestError(f"File is not a PDF: {pdf_path}")

    if pdf_file.stat().st_size == 0:
        raise IngestError("PDF file is empty")
