from leasora_api.services.ingest.chunker import (
    Chunker,
    add_overlap,
    merge_undersized_chunks,
    recursive_chunk,
    split_into_clauses,
)


def test_split_into_clauses_numbered_headings():
    text = "1. First clause here.\n2. Second clause here.\n3. Third clause here."
    clauses = split_into_clauses(text)
    assert len(clauses) == 3
    assert clauses[0].startswith("1.")
    assert clauses[1].startswith("2.")


def test_split_into_clauses_falls_back_to_paragraphs():
    text = "First paragraph of text.\n\nSecond paragraph of text."
    clauses = split_into_clauses(text)
    assert len(clauses) == 2


def test_recursive_chunk_respects_chunk_size():
    text = "word " * 200  # 1000 chars
    chunks = recursive_chunk(text, chunk_size=100)
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert len(chunks) > 1


def test_recursive_chunk_short_text_returns_single_chunk():
    text = "short text"
    chunks = recursive_chunk(text, chunk_size=100)
    assert chunks == ["short text"]


def test_merge_undersized_chunks_combines_short_fragments():
    chunks = ["a" * 10, "b" * 100]
    merged = merge_undersized_chunks(chunks, min_length=80)
    assert len(merged) == 1


def test_add_overlap_prefixes_from_previous_chunk():
    chunks = ["the quick brown fox jumps", "over the lazy dog"]
    overlapped = add_overlap(chunks, overlap=10)
    assert overlapped[0] == chunks[0]
    assert overlapped[1] != chunks[1]
    assert overlapped[1].endswith(chunks[1])


def test_chunker_keeps_small_clauses_whole():
    chunker = Chunker()
    text = "1. Short clause.\n2. Another short clause."
    chunks = chunker.chunk(text, chunk_size=1000)
    assert len(chunks) == 2


def test_chunker_splits_oversized_clauses():
    chunker = Chunker()
    long_clause = "1. " + ("word " * 300)  # > 1000 chars
    chunks = chunker.chunk(long_clause, chunk_size=1000)
    assert len(chunks) > 1


def test_chunker_captures_party_block_above_first_numbered_heading() -> None:
    """Party-identity text before the first ``1.`` heading must be a chunk.

    A real lease starts with a parties block followed by ``1. LEASE TERM``.
    The chunker must keep BOTH so party/identity questions are answerable.
    — previously the preamble was silently dropped, making
    "Who is the landlord?" un-answerable no matter how good retrieval was.
    """
    chunker = Chunker()
    page_text = (
        "LANDLORD: Jane Smith of 100 Oak Avenue, Springfield\n"
        "TENANT: John Doe of 200 Elm Street, Springfield\n"
        "PROPERTY: Suite 5, 300 Main Street, Springfield\n\n"
        "1. LEASE TERM & RENEWAL\n"
        "1.1 This Agreement commences on August 1, 2025."
    )

    chunks = chunker.chunk(page_text)
    joined = "\n".join(chunks)
    assert "LANDLORD: Jane Smith" in joined
    assert "TENANT: John Doe" in joined
    assert "1. LEASE TERM" in joined
    # The preamble is its own chunk (so embeddings pick it up as a unit),
    # not glued onto the heading's chunk — verify the leading chunk starts
    # with the parties block, not with the heading.
    assert chunks[0].startswith("LANDLORD: Jane Smith")


def test_chunker_handles_all_caps_recital_preamble() -> None:
    """ALL-CAPS heading path: recital block above the first ALL-CAPS heading
    is also captured. Same root cause as the numbered-heading case."""
    chunker = Chunker()
    page_text = (
        "RECITALS\n"
        "WHEREAS the Landlord owns the property described herein; and\n"
        "WHEREAS the Tenant wishes to lease the said property;\n\n"
        "RENT\n"
        "The monthly rent shall be five thousand dollars."
    )
    chunks = chunker.chunk(page_text)
    joined = "\n".join(chunks)
    assert "RECITALS" in joined
    assert "RENT" in joined
