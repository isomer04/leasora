"""Post-ingest lease metadata extraction.

Extracts parties, dates, rent, and location from the indexed lease chunks.
The prompt includes the first chunks plus later metadata-bearing chunks so a
section heading at the sample boundary cannot hide the value that follows it.
Expected failures are logged and returned as an empty dict so upload itself
can still succeed and the user can retry extraction later.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from threading import Lock
from typing import Any

from pydantic import ValidationError

from leasora_api.core.exceptions import LLMError
from leasora_api.core.langfuse_client import langfuse_client
from leasora_api.core.security import redact_pii
from leasora_api.schemas.domain import ExtractedLeaseMetadata, MetadataExtractionStatus
from leasora_api.services.llm.groq_client import groq_client
from leasora_api.services.llm.registry import registry
from leasora_api.services.rag.safety import sanitize_chunk
from leasora_api.services.retrieval.vector_store import RetrievalResult, VectorStore, chroma

logger = logging.getLogger(__name__)

_EARLY_CHUNKS_TO_SAMPLE = 5
_MAX_CHUNKS_TO_SAMPLE = 12
_IDENTITY_TERMS = re.compile(
    r"(?:landlord|tenant)\s+signature|approved\s+occupants|\bname\s*:",
    re.IGNORECASE,
)
_FIELD_TERMS = re.compile(
    r"\b(?:base\s+rent|monthly\s+rent|rent|commenc\w*|expir\w*|"
    r"lease\s+term|property\s+address|premises\s+located|address)\b",
    re.IGNORECASE,
)
_PARTY_TERMS = re.compile(r"\b(?:tenant|lessee|landlord|lessor)\b", re.IGNORECASE)
_EXTRACT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class MetadataExtractionResult:
    """Internal extraction outcome used by strict retry and best-effort upload flows."""

    status: MetadataExtractionStatus
    fields: dict[str, str]


def _select_metadata_chunks(chunks: list[RetrievalResult]) -> list[RetrievalResult]:
    """Select early context, high-signal chunks, and each signal's successor."""
    ordered = sorted(chunks, key=lambda chunk: chunk["metadata"].get("page", 0) or 0)
    selected = ordered[:_EARLY_CHUNKS_TO_SAMPLE]
    selected_ids = {chunk["id"] for chunk in selected}

    def add_at(index: int) -> None:
        if index >= len(ordered) or len(selected) >= _MAX_CHUNKS_TO_SAMPLE:
            return
        chunk = ordered[index]
        if chunk["id"] not in selected_ids:
            selected.append(chunk)
            selected_ids.add(chunk["id"])

    # Specific identity and field signals run before generic party words.
    # Include the following chunk because headings are commonly split from
    # their values (for example, "RENT" followed by "$2,850 per month").
    for pattern in (_IDENTITY_TERMS, _FIELD_TERMS, _PARTY_TERMS):
        for index, chunk in enumerate(ordered):
            if len(selected) >= _MAX_CHUNKS_TO_SAMPLE:
                break
            if pattern.search(chunk["text"]):
                add_at(index)
                add_at(index + 1)

    return sorted(selected, key=lambda chunk: chunk["metadata"].get("page", 0) or 0)


class MetadataExtractor:
    """Extract parties, dates, rent, and location while deduplicating retries."""

    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self._vector_store = vector_store if vector_store is not None else chroma
        self._llm_client = groq_client
        self._inflight_lock = Lock()
        self._inflight: dict[
            tuple[int, str], asyncio.Task[MetadataExtractionResult]
        ] = {}

    async def extract(self, lease_id: str) -> dict[str, str]:
        """Best-effort compatibility wrapper used by the upload flow."""
        result = await self.extract_result(lease_id)
        return result.fields

    async def extract_result(self, lease_id: str) -> MetadataExtractionResult:
        """Return a status-aware result and share concurrent work per lease."""
        loop = asyncio.get_running_loop()
        key = (id(loop), lease_id)
        with self._inflight_lock:
            task = self._inflight.get(key)
            if task is None or task.done():
                task = loop.create_task(self._extract_once(lease_id))
                self._inflight[key] = task

                def clear(done: asyncio.Future[MetadataExtractionResult]) -> None:
                    with self._inflight_lock:
                        if self._inflight.get(key) is done:
                            del self._inflight[key]

                task.add_done_callback(clear)

        return await asyncio.shield(task)

    async def _extract_once(self, lease_id: str) -> MetadataExtractionResult:
        try:
            chunks = await self._vector_store.get_by_lease(lease_id)
        except Exception:
            logger.exception("Failed to load chunks for metadata extraction (lease %s)", lease_id)
            return MetadataExtractionResult(MetadataExtractionStatus.FAILED, {})

        if not chunks:
            logger.warning("No chunks found for lease %s; metadata extraction cannot run", lease_id)
            return MetadataExtractionResult(MetadataExtractionStatus.FAILED, {})

        try:
            sample = _select_metadata_chunks(chunks)
            chunks_text = "\n\n".join(sanitize_chunk(chunk["text"]) for chunk in sample)
            template = registry.load_prompt("extract_lease_metadata")
            prompt = template.format(chunks_text=chunks_text)

            with langfuse_client.start_generation(
                "metadata-extraction",
                model=self._llm_client.model,
                input=redact_pii(prompt),
                metadata={"lease_id": lease_id},
            ) as generation_span:
                raw_output, usage = await asyncio.wait_for(
                    asyncio.to_thread(self._llm_client.complete_structured, prompt, 0.2),
                    timeout=_EXTRACT_TIMEOUT_SECONDS,
                )
                generation_span.update(
                    output=redact_pii(str(raw_output)), usage_details=usage
                )
        except LLMError:
            logger.exception("LLM metadata extraction failed for lease %s", lease_id)
            return MetadataExtractionResult(MetadataExtractionStatus.FAILED, {})
        except Exception:
            logger.exception("Unexpected error during metadata extraction for lease %s", lease_id)
            return MetadataExtractionResult(MetadataExtractionStatus.FAILED, {})

        return self._parse_result(raw_output, lease_id)

    @staticmethod
    def _parse_result(
        raw_output: dict[str, Any], lease_id: str
    ) -> MetadataExtractionResult:
        try:
            parsed = ExtractedLeaseMetadata.model_validate(raw_output)
        except ValidationError:
            logger.warning(
                "LLM metadata extraction output failed validation for lease %s: %s",
                lease_id,
                redact_pii(str(raw_output))[:200],
            )
            return MetadataExtractionResult(MetadataExtractionStatus.FAILED, {})

        fields = {
            field: value
            for field, value in parsed.model_dump().items()
            if value is not None
        }
        status = (
            MetadataExtractionStatus.UPDATED
            if fields
            else MetadataExtractionStatus.NO_FIELDS
        )
        return MetadataExtractionResult(status, fields)


metadata_extractor = MetadataExtractor()
