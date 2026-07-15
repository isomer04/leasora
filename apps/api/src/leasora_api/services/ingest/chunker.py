"""Clause-aware text chunking (split → filter → overlap)."""

import re

# Thresholds ported from the legacy ingest.py clause-chunking pipeline.
RECURSIVE_CHUNK_SIZE = 350
MIN_CHUNK_LENGTH = 80
OVERLAP_CHARS = 50

_NUMBERED_PATTERN = re.compile(r"^\s*\d{1,2}(?:[.\)]\s|\.\d+\s)", re.MULTILINE)
_LETTERED_PATTERN = re.compile(r"^\s*\([a-z]\)|^\s*[A-Z]{1,2}\.\s", re.MULTILINE)
_ALL_CAPS_PATTERN = re.compile(r"^\s*[A-Z][A-Z\s]{5,}\s*$", re.MULTILINE)


def split_into_clauses(text: str) -> list[str]:
    """Split text into clause units based on section boundaries.

    Tries numbered headings, then lettered headings, then ALL-CAPS headings.
    Falls back to paragraph splitting if no heading style is detected.

    Args:
        text: Full text extracted from a single page.

    Returns:
        List of clause texts (non-empty, stripped).
    """
    if _NUMBERED_PATTERN.search(text):
        return _split_by_pattern(text, _NUMBERED_PATTERN)
    if _LETTERED_PATTERN.search(text):
        return _split_by_pattern(text, _LETTERED_PATTERN)
    if _ALL_CAPS_PATTERN.search(text):
        return _split_by_pattern(text, _ALL_CAPS_PATTERN)
    return _split_by_paragraph(text)


def _split_by_pattern(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Split text by a regex pattern, keeping each match as a chunk start.

    Text appearing BEFORE the first matching heading (party-identity blocks,
    recitals, definitions, etc.) is captured as its own preamble chunk so
    callers can answer "who is the landlord?" without losing that context.
    This resolves a chunking gap where preambles were previously dropped.
    """
    matches = list(pattern.finditer(text))
    if not matches:
        return [text.strip()] if text.strip() else []

    clauses: list[str] = []
    # Capture the preamble (everything before the first matched heading) as
    # its own chunk whenever it's non-empty. Party-identity / recital
    # preambles are PII-bearing and high-signal for retrieval ("Who is the
    # landlord?"), so they're always preserved regardless of length; the
    # MIN_CHUNK_LENGTH gate is reserved for other chunk types to avoid
    # pinning stray newlines into the store.
    preamble_end = matches[0].start()
    preamble = text[:preamble_end].strip()
    if preamble:
        clauses.append(preamble)

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        clause = text[start:end].strip()
        if clause:
            clauses.append(clause)
    return clauses


def _split_by_paragraph(text: str) -> list[str]:
    """Split text by paragraphs (double newlines, falling back to single)."""
    paragraphs = re.split(r"\n\s*\n", text)
    if len(paragraphs) <= 1:
        paragraphs = re.split(r"\n(?=\s*\n|\s*[A-Z])", text)
    return [p.strip() for p in paragraphs if p.strip()]


def recursive_chunk(
    text: str,
    chunk_size: int = RECURSIVE_CHUNK_SIZE,
    separators: tuple[str, ...] = ("\n\n", "\n", ". ", " "),
) -> list[str]:
    """Recursively split oversized text into pieces of at most ``chunk_size``.

    Splits on the first available separator (paragraph, then newline, then
    sentence, then space) to keep chunks on natural boundaries wherever
    possible.

    Args:
        text: Text to chunk.
        chunk_size: Maximum characters per chunk.
        separators: Separators to try, in priority order.

    Returns:
        List of text chunks, each at most ``chunk_size`` characters
        (best-effort; a single unsplittable token longer than chunk_size is
        hard-cut).
    """
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    separator = next((s for s in separators if s in text), "")
    if not separator:
        return [text[i : i + chunk_size].strip() for i in range(0, len(text), chunk_size)]

    parts = text.split(separator)
    chunks: list[str] = []
    current = ""
    for i, part in enumerate(parts):
        sep = separator if i < len(parts) - 1 else ""
        if len(current) + len(part) + len(sep) <= chunk_size:
            current += part + sep
        else:
            if current.strip():
                chunks.append(current.strip())
            if len(part) > chunk_size:
                chunks.extend(recursive_chunk(part, chunk_size, separators[1:]))
                current = ""
            else:
                current = part + sep
    if current.strip():
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def merge_undersized_chunks(chunks: list[str], min_length: int = MIN_CHUNK_LENGTH) -> list[str]:
    """Merge chunks shorter than ``min_length`` into a neighboring chunk."""
    merged: list[str] = []
    for chunk in chunks:
        if merged and len(merged[-1]) < min_length:
            merged[-1] = merged[-1] + " " + chunk
        else:
            merged.append(chunk)
    # If the final chunk is too short, fold it into its predecessor.
    # Bind ``merged[-2]`` to a local first — the original line
    # ``merged[-2] = merged[-2] + " " + merged.pop()`` triggers an
    # IndexError because ``merged.pop()`` runs *before* the assignment's
    # right-hand side evaluates ``merged[-2]``.
    if len(merged) > 1 and len(merged[-1]) < min_length:
        tail = merged.pop()
        merged[-1] = merged[-1] + " " + tail
    return merged


def add_overlap(chunks: list[str], overlap: int = OVERLAP_CHARS) -> list[str]:
    """Prefix each chunk (after the first) with a tail slice of its predecessor.

    Preserves context across chunk boundaries. The overlap is trimmed to a
    word boundary so words are not split mid-token.

    Args:
        chunks: Chunks from :func:`recursive_chunk`.
        overlap: Number of characters to carry over from the previous chunk.

    Returns:
        Chunks with overlap prefixes applied (first chunk unchanged).
    """
    out: list[str] = []
    for i, chunk in enumerate(chunks):
        if i > 0:
            tail = chunks[i - 1][-overlap:]
            space = tail.find(" ")
            if space != -1:
                tail = tail[space + 1 :]
            chunk = tail + " " + chunk
        out.append(chunk)
    return out


class Chunker:
    """High-level chunking entry point used by the ingest pipeline."""

    def chunk(
        self,
        text: str,
        chunk_size: int = RECURSIVE_CHUNK_SIZE,
        min_length: int = MIN_CHUNK_LENGTH,
        overlap: int = OVERLAP_CHARS,
    ) -> list[str]:
        """Split a page's text into clause-sized chunks.

        Args:
            text: Text for a single page.
            chunk_size: Maximum chunk size for the recursive splitter,
                AND the threshold above which a clause is recursively
                chunked in the first place. Previously ``chunk_size``
                only controlled the split-into-clauses threshold while a
                hard-coded ``RECURSIVE_CHUNK_SIZE`` (350) was used inside
                the recursive step — so the parameter lied about its
                effect. They are unified here.
            min_length: Undersized fragments below this size are merged
                into a neighboring chunk.
            overlap: Number of characters carried over from the previous
                chunk for continuity.

        Returns:
            List of chunk texts ready for embedding + storage.
        """
        chunks: list[str] = []
        for clause_text in split_into_clauses(text):
            if len(clause_text) > chunk_size:
                sub_chunks = recursive_chunk(clause_text, chunk_size=chunk_size)
                sub_chunks = merge_undersized_chunks(sub_chunks, min_length=min_length)
                sub_chunks = add_overlap(sub_chunks, overlap=overlap)
                chunks.extend(sub_chunks)
            else:
                chunks.append(clause_text)
        return chunks
