"""Request validation utilities following Clean Code principles.

Centralizes validation logic to avoid duplication and improve maintainability.
Each validator is a focused, reusable function.
"""

import re
from typing import Pattern

from leasora_api.core.exceptions import ValidationError
from leasora_api.core.config import get_settings

# Lease ID validation. Accepts the server-generated format from
# `generate_lease_id()` (``lease_<8-hex-chars>``) as well as any
# reasonable alphanumeric identifier (for forward compatibility).
LEASE_ID_PATTERN: Pattern[str] = re.compile(r"^[a-zA-Z0-9_\-]{1,100}$")

# Question validation
MAX_QUESTION_LENGTH: int = 1000

# File upload validation (security and practicality limits).
ALLOWED_FILE_TYPES: set[str] = {"application/pdf"}
ALLOWED_FILE_EXTENSIONS: set[str] = {".pdf"}

# PDF magic-byte signature: a real PDF starts with the literal 4 bytes
# ``%PDF`` (per ISO 32000). Rejecting on this prevents validation spoofing.
PDF_MAGIC_BYTES: bytes = b"%PDF"

# Form field validation
MAX_LEASE_NAME_LENGTH: int = 200
MAX_METADATA_FIELD_LENGTH: int = 200


def get_max_file_size_bytes() -> int:
    """Return the configured maximum upload size in bytes.

    Performs deferred lookup via ``get_settings()`` so the env override is
    honored at call time (not import time). This avoids the trap of using
    a constant name (e.g. ``MAX_FILE_SIZE_BYTES``) which would be falsy-
    comparable and break future type checking.
    """
    return get_settings().max_upload_size_bytes


def validate_pdf_magic_bytes(contents: bytes) -> None:
    """Reject a payload that doesn't begin with the ``%PDF`` magic bytes.

    Defense-in-depth against content-type / extension spoofing.
    The HTTP layer's ``Content-Type`` header is client-controlled;
    the file extension is just a label. Only the byte stream confirms
    the payload is a real PDF.

    Args:
        contents: First N bytes of the uploaded payload.

    Raises:
        ValidationError: If the payload doesn't begin with ``%PDF``.
    """
    if not contents or len(contents) < len(PDF_MAGIC_BYTES):
        raise ValidationError(
            "Uploaded file is not a valid PDF (too short or empty)."
        )
    if not contents.startswith(PDF_MAGIC_BYTES):
        raise ValidationError(
            "Uploaded file does not have a valid PDF header "
            "(magic bytes %PDF missing). Rejecting for security."
        )


def validate_lease_id(lease_id: str) -> None:
    """Validate lease ID format.

    Args:
        lease_id: The lease ID to validate

    Raises:
        ValidationError: If validation fails with descriptive message
    """
    if not lease_id or not lease_id.strip():
        raise ValidationError("lease_id is required and cannot be empty")

    if not LEASE_ID_PATTERN.match(lease_id):
        raise ValidationError(
            "lease_id must contain only alphanumeric characters, underscores, and hyphens (1-100 chars)"
        )


def validate_question(question: str) -> None:
    """Validate question text.

    Args:
        question: The question to validate

    Raises:
        ValidationError: If validation fails with descriptive message
    """
    if not question or not question.strip():
        raise ValidationError("question is required and cannot be empty")

    question_length = len(question.strip())
    if question_length > MAX_QUESTION_LENGTH:
        raise ValidationError(
            f"question must be {MAX_QUESTION_LENGTH} characters or less "
            f"(received {question_length})"
        )


def validate_upload_file_type(file_type: str) -> None:
    """Validate uploaded file MIME type for security.

    Args:
        file_type: MIME type of uploaded file

    Raises:
        ValidationError: If file type not allowed

    Clean Code Note:
        Prevents malicious file uploads (e.g., executables, scripts).
        Explicit whitelist approach (secure by default).
    """
    if file_type not in ALLOWED_FILE_TYPES:
        raise ValidationError(
            f"File type '{file_type}' not allowed. "
            f"Allowed types: {', '.join(ALLOWED_FILE_TYPES)}"
        )


def validate_upload_file_size(file_size_bytes: int) -> None:
    """Validate uploaded file size within limits.

    Args:
        file_size_bytes: Size of uploaded file in bytes

    Raises:
        ValidationError: If file exceeds size limit

    Clean Code Note:
        Prevents DoS attacks via oversized uploads.
        Uses the single source of truth in settings (``max_upload_size_bytes``).
    """
    limit = get_max_file_size_bytes()
    if file_size_bytes > limit:
        size_mb = file_size_bytes / (1024 * 1024)
        limit_mb = limit / (1024 * 1024)
        raise ValidationError(
            f"File size {size_mb:.1f}MB exceeds maximum of {limit_mb:.0f}MB"
        )


def validate_lease_name(name: str) -> None:
    """Validate lease name field.

    Args:
        name: Lease name to validate

    Raises:
        ValidationError: If name invalid
    """
    if not name or not name.strip():
        raise ValidationError("Lease name is required and cannot be empty")

    if len(name.strip()) > MAX_LEASE_NAME_LENGTH:
        raise ValidationError(
            f"Lease name must be {MAX_LEASE_NAME_LENGTH} characters or less"
        )


def validate_metadata_field(field_name: str, value: str) -> None:
    """Validate optional metadata fields (tenant, landlord, etc.).

    Args:
        field_name: Name of field (for error messages)
        value: Field value to validate

    Raises:
        ValidationError: If field invalid
    """
    if value and len(value.strip()) > MAX_METADATA_FIELD_LENGTH:
        raise ValidationError(
            f"{field_name} must be {MAX_METADATA_FIELD_LENGTH} characters or less"
        )
