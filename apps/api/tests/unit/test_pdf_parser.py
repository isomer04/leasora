from pathlib import Path

import pytest

from leasora_api.core.exceptions import ParseError
from leasora_api.services.ingest.pdf_parser import PDFParser

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "data" / "test-fixtures"


def test_parse_missing_file_raises_parse_error():
    parser = PDFParser()
    with pytest.raises(ParseError, match="not found"):
        parser.parse("does/not/exist.pdf")


def test_parse_non_pdf_extension_raises_parse_error(tmp_path):
    fake_file = tmp_path / "lease.txt"
    fake_file.write_text("not a pdf")

    parser = PDFParser()
    with pytest.raises(ParseError, match="Unsupported file format"):
        parser.parse(str(fake_file))


def test_parse_scanned_pdf_raises_parse_error(monkeypatch):
    """A PDF with no extractable text on any page should be rejected."""
    parser = PDFParser()

    class _FakePage:
        def extract_text(self) -> str | None:
            return None

    class _FakePdf:
        pages = [_FakePage(), _FakePage()]

        def __enter__(self) -> "_FakePdf":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    import pdfplumber

    monkeypatch.setattr(pdfplumber, "open", lambda _path: _FakePdf())
    monkeypatch.setattr(Path, "exists", lambda self: True)

    with pytest.raises(ParseError, match="scanned or image-based"):
        parser.parse("fake.pdf")


@pytest.mark.skipif(
    not (FIXTURES_DIR / "demo_lease.pdf").exists(),
    reason="demo_lease.pdf fixture not present",
)
def test_parse_real_pdf_preserves_page_numbers_and_empty_pages():
    """Real digital PDF: page numbers preserved, empty pages kept as empty strings."""
    parser = PDFParser()
    pages = parser.parse(str(FIXTURES_DIR / "demo_lease.pdf"))

    assert pages, "Expected at least one page"
    # Page numbers must be sequential starting at 1, with no gaps.
    page_numbers = [page_num for page_num, _ in pages]
    assert page_numbers == list(range(1, len(pages) + 1))
    # At least one page should have real extracted text.
    assert any(text.strip() for _, text in pages)
