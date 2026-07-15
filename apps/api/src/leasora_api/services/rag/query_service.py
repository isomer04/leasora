"""RAG query service for answering questions about leases."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from leasora_api.core.config import Settings, get_settings
from leasora_api.core.constants import REFUSAL_MESSAGE
from leasora_api.core.exceptions import LLMError
from leasora_api.core.langfuse_client import langfuse_client
from leasora_api.core.metrics import (
    record_cache,
    record_refusal,
    time_llm,
    time_retrieval,
)
from leasora_api.core.security import redact_pii
from leasora_api.schemas.domain import StructuredAnswer
from leasora_api.schemas.response import AskResponse, SourceReference
from leasora_api.services.llm.groq_client import GroqClient, groq_client
from leasora_api.services.llm.registry import registry
from leasora_api.services.eval.judges import check_answer_grounded
from leasora_api.services.rag.safety import sanitize_chunk
from leasora_api.services.retrieval.bm25_index import BM25Cache, BM25Index, bm25_cache, fuse_results
from leasora_api.services.retrieval.embedder import Embedder, embedder
from leasora_api.services.retrieval.query_cache import QueryCache, query_cache
from leasora_api.services.retrieval.reranker import Reranker, reranker
from leasora_api.services.retrieval.semantic_cache import SemanticCache, cache as semantic_cache
from leasora_api.services.retrieval.vector_store import ChromaStore, RetrievalResult, chroma

if TYPE_CHECKING:
    from leasora_api.core.langfuse_client import LangfuseClientWrapper

logger = logging.getLogger(__name__)

# Returned when the LLM's structured JSON output fails schema validation.
# Distinct from REFUSAL_MESSAGE (which means "not enough context") — this
# means "we had context but the model's output was malformed", so we degrade
# gracefully instead of surfacing a 500 or a raw parsing error to the caller.
STRUCTURED_OUTPUT_FALLBACK_MESSAGE = (
    "I found relevant information but couldn't format a reliable answer. "
    "Please try rephrasing your question."
)


class PromptBuilder:
    """Constructs LLM prompts for question answering."""

    @staticmethod
    def build_rag_prompt(question: str, chunks: list[RetrievalResult]) -> str:
        """Build a grounded RAG prompt from retrieved chunks.

        Each chunk is sanitized (prompt-injection defense) and framed with
        its source document and page number so the LLM can cite it.

        Args:
            question: User's question about the lease.
            chunks: Retrieved chunks, ranked by relevance.

        Returns:
            Formatted prompt for the LLM.
        """
        context_blocks = "\n\n".join(
            f"[Source: {chunk['metadata'].get('source', 'unknown')}, "
            f"Page: {chunk['metadata'].get('page', 'N/A')}]\n"
            f"{sanitize_chunk(chunk['text'])}"
            for chunk in chunks
        )
        template = registry.load_prompt("answer_question")
        return template.format(context=context_blocks, question=question)


class RAGQueryService:
    """Service for answering questions using RAG.

    Orchestrates the RAG pipeline: retrieve context, apply the refusal gate,
    generate a grounded answer, and return real page-cited sources.
    """

    def __init__(
        self,
        *,
        llm_client: GroqClient | None = None,
        embedder_: Embedder | None = None,
        vector_store: ChromaStore | None = None,
        reranker_: Reranker | None = None,
        langfuse: LangfuseClientWrapper | None = None,
        query_cache_: QueryCache | None = None,
        semantic_cache_: SemanticCache | None = None,
        bm25_cache_: BM25Cache | None = None,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        """Initialize RAG service. All params optional; defaults to module singletons."""
        self._llm_client = llm_client if llm_client is not None else groq_client
        self._prompt_builder = prompt_builder if prompt_builder is not None else PromptBuilder()
        self._embedder = embedder_ if embedder_ is not None else embedder
        self._vector_store = vector_store if vector_store is not None else chroma
        self._reranker = reranker_ if reranker_ is not None else reranker
        self._langfuse = langfuse if langfuse is not None else langfuse_client
        self._query_cache = query_cache_ if query_cache_ is not None else query_cache
        self._semantic_cache = semantic_cache_ if semantic_cache_ is not None else semantic_cache
        self._bm25_cache = bm25_cache_ if bm25_cache_ is not None else bm25_cache

    async def answer_question(self, lease_id: str, question: str) -> AskResponse:
        """Answer a question about a lease using RAG.

        Args:
            lease_id: Unique lease identifier.
            question: The question to answer.

        Returns:
            Response with answer, sources, and confidence score. Returns the
            canonical refusal message (no LLM call) when retrieval confidence
            is below the configured threshold.

        Raises:
            LLMError: If LLM service fails.

        Observability:
            Emits a Langfuse "retrieval" span (query, top-k, min distance,
            whether the answer was refused) and, when an answer is generated,
            a "generation" span (model, prompt version, token usage, latency).
            Both are no-ops when Langfuse is not configured (see
            ``core/langfuse_client``). Redacted with ``sanitize_chunk``/kept
            to metadata only where PII could plausibly appear, per ADR-003.

        Caching:
            When ``settings.cache_enabled``, checks the exact-match
            ``QueryCache`` first, then (if ``settings.semantic_cache_enabled``)
            the near-duplicate ``SemanticCache``, both scoped by
            ``lease_id``. On a miss, runs the full flow below and writes the
            result to both caches. Refusals are cached too but are evicted
            (like every other entry) on re-ingest via
            ``QueryCache.evict_lease``/``SemanticCache.evict_lease``, so a
            newly-uploaded lease is never blocked by a stale refusal.
        """
        settings = get_settings()
        # Include `groq_model` alongside retrieval / reranking settings so a
        # model swap invalidates cached answers.
        config_flags = (
            settings.retrieval_top_k,
            settings.refusal_threshold,
            settings.rerank_enabled,
            settings.hybrid_enabled,
            settings.hybrid_alpha,
            settings.groq_model,
            settings.rerank_top_n,
            settings.answer_guard_enabled,
            registry.get_version("answer_question"),
        )


        if settings.cache_enabled:
            cached = self._query_cache.get(lease_id, question, config_flags)
            if cached is not None:
                record_cache("exact", hit=True)
                return cached
            record_cache("exact", hit=False)

        query_vector = await self._embedder.aembed_query(question)

        if settings.cache_enabled and settings.semantic_cache_enabled:
            cached = self._semantic_cache.get(lease_id, query_vector, config_flags)
            if cached is not None:
                record_cache("semantic", hit=True)
                return cached
            record_cache("semantic", hit=False)

        response = await self._answer_question_uncached(
            lease_id, question, query_vector, settings
        )

        if settings.cache_enabled:
            self._query_cache.set(lease_id, question, response, config_flags)
            if settings.semantic_cache_enabled:
                self._semantic_cache.set(
                    lease_id, query_vector, response, config_flags
                )

        return response

    async def _answer_question_uncached(
        self, lease_id: str, question: str, query_vector: list[float], settings: Settings
    ) -> AskResponse:
        """Run the real retrieve -> refuse -> ground -> answer flow (no caching)."""
        dense_top_k = settings.rerank_top_n if settings.rerank_enabled else settings.retrieval_top_k

        with self._langfuse.start_span(
            "retrieval",
            input={"question": redact_pii(question), "lease_id": lease_id},
            metadata={
                "top_k": settings.retrieval_top_k,
                "hybrid_enabled": settings.hybrid_enabled,
                "rerank_enabled": settings.rerank_enabled,
            },
        ) as retrieval_span:
            with time_retrieval():
                chunks = await self._vector_store.query(
                    embedding=query_vector,
                    top_k=dense_top_k,
                    where={"lease_id": {"$eq": lease_id}},
                )

            if settings.hybrid_enabled:
                chunks = await self._hybrid_fuse(lease_id, question, chunks, dense_top_k)

            if settings.rerank_enabled and chunks:
                chunks = await self._reranker.arerank(
                    question, chunks, top_k=settings.retrieval_top_k
                )

            min_distance = min((chunk["distance"] for chunk in chunks), default=1.0)
            refused = not chunks or min_distance > settings.refusal_threshold

            retrieval_span.update(
                output={
                    "retrieved_count": len(chunks),
                    "min_distance": min_distance,
                    "refused": refused,
                }
            )

        if refused:
            # Record a refusal labeled by the top-1 chunk's clause_type
            # when we have one. Falls back to ``"unknown"`` when the
            # retrieval produced no chunks at all.
            clause_type = "unknown"
            if chunks:
                clause_type = str(chunks[0]["metadata"].get("clause_type", "other")) or "other"
            record_refusal(clause_type)
            return AskResponse(answer=REFUSAL_MESSAGE, sources=[], confidence=0.0)

        prompt_version = registry.get_version("answer_question")
        try:
            prompt = self._prompt_builder.build_rag_prompt(question, chunks)
            with self._langfuse.start_generation(
                "answer-generation",
                model=self._llm_client.model,
                input=redact_pii(prompt),
                metadata={"prompt_version": prompt_version},
            ) as generation_span:
                # PII Protocol: Two-Track System
                # ================================
                # The LLM receives the raw prompt (including real tenant names,
                # addresses, contact info) to answer entity questions correctly.
                # Observability systems (Langfuse, logs) see only the redacted
                # version via redact_pii(prompt).
                #
                # Design: This split is intentional and security-critical.
                # - LLM input: raw (for accuracy on entity questions)
                # - Langfuse/logs: redacted (to prevent PII leakage)
                # - API response: redacted (boundary is the user-visible output)
                #
                # See PromptContext in schemas/domain.py for the canonical
                # documentation of this two-track protocol.
                with time_llm():
                    raw_output, usage = await asyncio.to_thread(
                        self._llm_client.complete_structured, prompt, 0.3
                    )
                generation_span.update(output=redact_pii(str(raw_output)), usage_details=usage)
        except LLMError:
            raise
        except Exception as error:
            # Don't interpolate the underlying exception into the LLMError
            # message — httpx/groq error strings frequently echo the prompt
            # or response body, which can carry PII verbatim. The traceback
            # is preserved via `from` for debugging; the surfaced message
            # is static so a user-visible 5xx never carries raw echo.
            logger.exception("Failed to generate answer for lease %s", lease_id)
            raise LLMError("Failed to generate answer") from error

        structured_answer = self._parse_structured_answer(raw_output, lease_id)

        sources = [self._to_source_reference(chunk) for chunk in chunks]
        confidence = max(0.0, min(1.0, 1.0 - min_distance))

        if structured_answer is None:
            return AskResponse(
                answer=STRUCTURED_OUTPUT_FALLBACK_MESSAGE,
                sources=sources,
                confidence=confidence,
            )

        if settings.answer_guard_enabled:
            context_text = "\n\n".join(chunk["text"] for chunk in chunks)
            grounded, unsupported_claims = await asyncio.to_thread(
                check_answer_grounded, context_text, structured_answer.answer
            )
            self._langfuse.score_current_trace(
                "answer_grounded", 1.0 if grounded else 0.0
            )
            if not grounded:
                # Redact unsupported_claims before logging as it may contain
                # verbatim text from the judge. Return sources and confidence
                # so users can audit retrieved clauses and match strength,
                # even when the model diverges from context. The trust boundary
                # is the answer text; sources/confidence provide auditability.
                logger.info(
                    "Answer guard downgraded response for lease %s; unsupported claims: %s",
                    lease_id,
                    redact_pii(str(unsupported_claims)),
                )
                return AskResponse(
                    answer=REFUSAL_MESSAGE, sources=sources, confidence=confidence
                )

        # Apply redact_pii to user-facing fields (answer / quote) before
        # constructing the response. The LLM must see raw text to answer
        # entity questions correctly (see comment on `complete_structured`
        # call above), but the API response is the trust boundary and any
        # regex-catchable PII from a verbatim quote or echoed clause is
        # replaced with [REDACTED_*] placeholders. Sources[*].excerpt is
        # redacted inside _to_source_reference.
        safe_answer = redact_pii(structured_answer.answer)
        safe_quote = redact_pii(structured_answer.quote) if structured_answer.quote else None

        return AskResponse(
            answer=safe_answer,
            sources=sources,
            confidence=confidence,
            quote=safe_quote or None,
            signal=structured_answer.signal,
        )

    @staticmethod
    def _parse_structured_answer(
        raw_output: dict[str, object], lease_id: str
    ) -> StructuredAnswer | None:
        """Validate the LLM's raw JSON output against ``StructuredAnswer``.

        Args:
            raw_output: Parsed JSON dict from ``GroqClient.complete_structured``.
            lease_id: Lease identifier, for logging context only.

        Returns:
            A validated ``StructuredAnswer``, or ``None`` if validation fails
            (malformed/missing fields, invalid signal value, etc.) so the
            caller can degrade gracefully instead of raising a 500.
        """
        try:
            return StructuredAnswer.model_validate(raw_output)
        except ValidationError:
            # raw_output is the LLM's verbatim JSON echo; redact regex-catchable
            # PII (SSN/CC/email/phone) before logging so a structured-output
            # failure never leaks PII into log lines.
            logger.warning(
                "LLM structured output failed validation for lease %s: %s",
                lease_id,
                redact_pii(str(raw_output)[:200]),
            )
            return None

    async def _hybrid_fuse(
        self,
        lease_id: str,
        question: str,
        dense_results: list[RetrievalResult],
        top_k: int,
    ) -> list[RetrievalResult]:
        """Fuse dense retrieval with a per-lease BM25 index.

        Looks up a cached ``BM25Index`` for ``lease_id`` first; on a miss,
        fetches the lease's full stored corpus from ChromaDB and builds +
        caches it. Invalidation is driven by ``IngestPipeline.ingest`` via
        ``bm25_cache.evict_lease`` so a re-ingest never serves a stale
        index.
        """
        settings = get_settings()
        index = self._bm25_cache.get(lease_id)
        if index is None:
            all_chunks = await self._vector_store.get_by_lease(lease_id)
            if not all_chunks:
                return dense_results
            index = BM25Index()
            await index.abuild(all_chunks)
            self._bm25_cache.set(lease_id, index)

        bm25_results = await index.asearch(question, top_k=top_k)

        return fuse_results(
            dense_results, bm25_results, alpha=settings.hybrid_alpha, top_k=top_k
        )

    @staticmethod
    def _to_source_reference(chunk: RetrievalResult) -> SourceReference:
        """Convert a retrieval result into a public SourceReference.

        The excerpt field is a verbatim slice of the source clause, so it
        can carry regex-catchable PII (SSN/CC/email/phone) directly into
        the API response. Apply ``redact_pii`` at the boundary; the raw
        text remains in the vector store and Langfuse receives a redacted
        copy separately.
        """
        metadata = chunk["metadata"]
        excerpt = redact_pii(chunk["text"][:500])
        return SourceReference(
            clause_id=chunk["id"],
            clause_type=str(metadata.get("clause_type", "other")),
            excerpt=excerpt,
            source=metadata.get("source"),
            page=metadata.get("page"),
        )


# Singleton instance for dependency injection
rag_service = RAGQueryService()
