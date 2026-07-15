"""PDF parsing service for document ingestion.

Extracts text per page using ``pdfplumber``, preserving page numbers.
Scanned/image-only PDFs raise ``ParseError`` because OCR is not supported.
"""

from __future__ import annotations

from pathlib import Path

from leasora_api.core.exceptions import ParseError


class PDFParser:
    """Extract text from digital PDF documents, one page at a time.

    Pages without extractable text remain in the result as empty strings so
    page-number citations do not shift. A document with no extractable text on
    any page is rejected explicitly rather than producing empty chunks.
    """

    def parse(self, pdf_path: str) -> list[tuple[int, str]]:
        """Parse a PDF and extract text per page.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            List of ``(page_number, text)`` tuples, one per page, in order.
            Page numbers are 1-indexed and empty pages are preserved.

        Raises:
            ParseError: If the file is missing, is not a PDF, cannot be read,
                or contains no extractable text.
        """
        path = Path(pdf_path)
        if not path.exists():
            raise ParseError(f"PDF file not found: {pdf_path}")
        if path.suffix.lower() != ".pdf":
            raise ParseError(f"Unsupported file format: {path.suffix}. Please upload a PDF.")

        import pdfplumber

        pages: list[tuple[int, str]] = []
        total_text_chars = 0

        try:
            with pdfplumber.open(path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    cleaned = text.strip() if text else ""
                    total_text_chars += len(cleaned)
                    pages.append((page_num, cleaned))
        except Exception as error:
            raise ParseError(f"Error extracting PDF: {error}") from error

        if total_text_chars == 0:
            raise ParseError(
                "This PDF appears to be scanned or image-based. OCR is not "
                "supported; please upload a text-based PDF."
            )

        return pages


parser = PDFParser()
