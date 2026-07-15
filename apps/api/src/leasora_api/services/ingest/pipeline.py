"""Document ingestion pipeline orchestration.

Coordinates PDF parsing, clause-aware chunking, embedding, and storage in
the vector store. Each chunk is written with ``source``, ``page``, and
``clause_type`` metadata so downstream retrieval can cite pages and filter
by clause type.
"""

import logging
from pathlib import Path
from typing import Any

from leasora_api.core.exceptions import IngestError
from leasora_api.services.ingest.chunker import Chunker
from leasora_api.services.ingest.clause_types import assign_clause_type
from leasora_api.services.ingest.pdf_parser import PDFParser, parser as pdf_parser
from leasora_api.services.retrieval.bm25_index import BM25Cache, bm25_cache
from leasora_api.services.retrieval.embedder import Embedder, embedder
from leasora_api.services.retrieval.query_cache import QueryCache, query_cache
from leasora_api.services.retrieval.semantic_cache import SemanticCache, cache as semantic_cache
from leasora_api.services.retrieval.vector_store import ChunkMetadata, VectorStore, chroma

logger = logging.getLogger(__name__)


class IngestPipeline:
    """Orchestrate document ingestion: parse -> chunk -> embed -> store.

    Uses the module-level ``pdf_parser``, ``embedder``, and ``chroma`` vector
    store singletons so the pipeline can be exercised end-to-end without extra
    wiring, while still allowing tests to swap in fakes via the constructor.
    A fresh ``Chunker`` instance is constructed by default (the chunker is
    stateless, so a module-level singleton added no value).
    """

    def __init__(
        self,
        pdf_parser_: PDFParser | None = None,
        chunker_: Chunker | None = None,
        embedder_: Embedder | None = None,
        vector_store: VectorStore | None = None,
        query_cache_: QueryCache | None = None,
        semantic_cache_: SemanticCache | None = None,
        bm25_cache_: BM25Cache | None = None,
    ) -> None:
        # Explicit `is None` checks (not `x or default`): QueryCache/SemanticCache
        # define __len__, so an empty-but-real instance is falsy and `or` would
        # silently fall back to the module-level singleton instead.
        self._pdf_parser = pdf_parser_ if pdf_parser_ is not None else pdf_parser
        self._chunker = chunker_ if chunker_ is not None else Chunker()
        self._embedder = embedder_ if embedder_ is not None else embedder
        self._vector_store = vector_store if vector_store is not None else chroma
        self._query_cache = query_cache_ if query_cache_ is not None else query_cache
        self._semantic_cache = (
            semantic_cache_ if semantic_cache_ is not None else semantic_cache
        )
        self._bm25_cache = bm25_cache_ if bm25_cache_ is not None else bm25_cache

    async def ingest(
        self,
        pdf_path: str,
        lease_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Ingest a lease document: parse, chunk, embed, and store it.

        Args:
            pdf_path: Path to PDF file.
            lease_id: Unique identifier for the lease these chunks belong to.
            idempotency_key: Optional key for idempotent re-runs (reserved
                for future use; not yet enforced).

        Returns:
            Status dict with ``lease_id``, ``chunk_count``, and ``source``.

        Raises:
            IngestError: If parsing, chunking, or storage fails.
        """
        source = Path(pdf_path).name

        try:
            pages = self._pdf_parser.parse(pdf_path)
        except Exception as error:
            raise IngestError(f"Failed to parse PDF: {error}") from error

        chunk_texts: list[str] = []
        chunk_metadatas: list[ChunkMetadata] = []

        for page_number, page_text in pages:
            if not page_text.strip():
                continue
            for chunk_text in self._chunker.chunk(page_text):
                if not chunk_text.strip():
                    continue
                chunk_texts.append(chunk_text)
                # lease_id is stored per-chunk so retrieval can filter to a single lease.
                chunk_metadatas.append(
                    ChunkMetadata(
                        source=source,
                        page=page_number,
                        clause_type=assign_clause_type(chunk_text),
                        lease_id=lease_id,
                    )
                )

        if not chunk_texts:
            raise IngestError("No extractable clauses found in document")

        try:
            embeddings = await self._embedder.aembed_documents(chunk_texts)
        except Exception as error:
            raise IngestError(f"Failed to embed document chunks: {error}") from error

        ids = [f"{lease_id}::{i}" for i in range(len(chunk_texts))]

        try:
            # Delete any chunks from a previous ingest of this lease_id first.
            # Without this, re-uploading the same lease_id reuses the same
            # deterministic IDs (f"{lease_id}::{i}") and Chroma raises on
            # duplicate IDs, permanently blocking re-ingest.
            await self._vector_store.delete_by_lease(lease_id)
            await self._vector_store.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunk_texts,
                metadatas=chunk_metadatas,
            )
        except Exception as error:
            raise IngestError(f"Failed to store document chunks: {error}") from error

        logger.info("Ingested %d chunks for lease %s from %s", len(chunk_texts), lease_id, source)

        # Invalidate any cached answers for this lease: a re-ingest (or first
        # ingest with a reused lease_id) may change what's retrievable, so
        # stale cached answers must not be served afterward. Also drop the
        # built BM25 index for this lease so the next hybrid query rebuilds
        # from the new corpus.
        evicted_exact = self._query_cache.evict_lease(lease_id)
        evicted_semantic = self._semantic_cache.evict_lease(lease_id)
        evicted_bm25 = self._bm25_cache.evict_lease(lease_id)
        if evicted_exact or evicted_semantic or evicted_bm25:
            logger.info(
                "Evicted %d exact-match, %d semantic cache, and %d BM25 index entries for lease %s",
                evicted_exact,
                evicted_semantic,
                evicted_bm25,
                lease_id,
            )

        return {
            "lease_id": lease_id,
            "source": source,
            "chunk_count": len(chunk_texts),
        }


pipeline = IngestPipeline()
