"""Tests for ``core.validators`` — file-upload hardening."""

from __future__ import annotations

import pytest

from leasora_api.core.config import get_settings
from leasora_api.core.exceptions import ValidationError
from leasora_api.core.validators import (
    ALLOWED_FILE_EXTENSIONS,
    ALLOWED_FILE_TYPES,
    PDF_MAGIC_BYTES,
    get_max_file_size_bytes,
    validate_pdf_magic_bytes,
    validate_upload_file_size,
    validate_upload_file_type,
)


class TestPDFMagicBytesValidation:
    """Tests for PDF magic-byte validation."""

    def test_constant_is_iso_32000_prefix(self) -> None:
        """``PDF_MAGIC_BYTES`` is the well-known ISO 32000 prefix."""
        assert PDF_MAGIC_BYTES == b"%PDF", "ISO 32000 magic bytes must be exactly 4 bytes: %PDF"

    def test_accepts_real_pdf_stream(self) -> None:
        """A real PDF stream (starts with ``%PDF-1.x``) passes the check."""
        real_pdf_head = b"%PDF-1.7\n%binary-stuff\n"
        # Should not raise.
        validate_pdf_magic_bytes(real_pdf_head)

    def test_rejects_renamed_html(self) -> None:
        """HTML spoofed as ``.pdf`` (audit case: JS/HTML-with-.pdf) is rejected."""
        with pytest.raises(ValidationError, match="magic bytes"):
            validate_pdf_magic_bytes(b"<html><body>hi</body></html>")

    def test_rejects_renamed_js(self) -> None:
        """JS spoofed as ``.pdf`` is rejected."""
        with pytest.raises(ValidationError, match="magic bytes"):
            validate_pdf_magic_bytes(b"#!/bin/bash\nrm -rf /\n")

    def test_rejects_empty_payload(self) -> None:
        """Empty payload is rejected (not just a missing-prefix error)."""
        with pytest.raises(ValidationError):
            validate_pdf_magic_bytes(b"")

    def test_validate_pdf_magic_bytes_requires_at_least_4_bytes(self) -> None:
        """A payload shorter than 4 bytes is rejected without crash."""
        with pytest.raises(ValidationError):
            validate_pdf_magic_bytes(b"%PD")


class TestFileTypeWhitelist:
    """Tests for file-type whitelist validation."""

    def test_accepts_pdf_mime_type(self) -> None:
        validate_upload_file_type("application/pdf")

    def test_rejects_html_mime_type(self) -> None:
        with pytest.raises(ValidationError):
            validate_upload_file_type("text/html")

    def test_rejects_empty_mime_type(self) -> None:
        with pytest.raises(ValidationError):
            validate_upload_file_type("")

    def test_allowed_types_include_only_pdf(self) -> None:
        assert ALLOWED_FILE_TYPES == {"application/pdf"}, "Only PDF MIME type must be allowed"
        assert ALLOWED_FILE_EXTENSIONS == {".pdf"}, "Only .pdf file extension must be allowed"


class TestMaxFileSizeBytesConsolidation:
    """Tests for max file size configuration consolidation."""

    def test_single_source_of_truth(self) -> None:
        """``get_max_file_size_bytes()`` returns the configured setting value.

        There is exactly ONE place to tune the max-upload size
        (settings.max_upload_size_bytes), and the ``validators`` module
        exposes a thin alias for callers.
        """
        assert get_max_file_size_bytes() == get_settings().max_upload_size_bytes

    def test_default_is_50_mib(self, monkeypatch) -> None:
        """Default remains 50 MiB; raise or lower via env.

        Clears any local override first — ``conftest.py`` loads the
        developer's real ``.env``, so a local
        ``LEASORA_MAX_UPLOAD_SIZE_BYTES`` override would otherwise make this
        fail spuriously.
        """
        monkeypatch.delenv("LEASORA_MAX_UPLOAD_SIZE_BYTES", raising=False)
        get_settings.cache_clear()
        try:
            settings = get_settings()
            assert settings.max_upload_size_bytes == 50 * 1024 * 1024
        finally:
            get_settings.cache_clear()

    def test_env_override(self, monkeypatch) -> None:
        """An env override flows through to the alias."""
        from leasora_api.core.config import get_settings as _gs

        monkeypatch.setenv("LEASORA_MAX_UPLOAD_SIZE_BYTES", str(1024 * 1024))
        # The ``get_settings`` lru_cache must be cleared so a fresh Settings
        # is constructed under the new env.
        _gs.cache_clear()
        try:
            settings = _gs()
            assert settings.max_upload_size_bytes == 1024 * 1024
            assert get_max_file_size_bytes() == 1024 * 1024
        finally:
            _gs.cache_clear()

    def test_validate_file_size_uses_setting(self, monkeypatch) -> None:
        """The size-limit error message reflects the setting, not a stale constant."""
        from leasora_api.core.config import get_settings as _gs

        # 2 MiB limit; pydantic-settings' validator caps at >=1 MiB.
        monkeypatch.setenv("LEASORA_MAX_UPLOAD_SIZE_BYTES", str(2 * 1024 * 1024))
        _gs.cache_clear()
        try:
            with pytest.raises(ValidationError, match="exceeds maximum"):
                validate_upload_file_size(3 * 1024 * 1024)
        finally:
            _gs.cache_clear()
