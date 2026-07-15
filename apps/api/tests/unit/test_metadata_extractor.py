"""Unit tests for MetadataExtractor (post-ingest LLM metadata extraction)."""

import asyncio
import time
from unittest.mock import MagicMock

from leasora_api.core.exceptions import LLMError
from leasora_api.schemas.domain import MetadataExtractionStatus
from leasora_api.services.ingest.metadata_extractor import MetadataExtractor
from leasora_api.services.retrieval.vector_store import RetrievalResult


def _chunk(id_: str, text: str, page: int) -> RetrievalResult:
    return RetrievalResult(
        id=id_, text=text, metadata={"clause_type": "rental_term", "page": page}, distance=0.0
    )


class FakeVectorStore:
    def __init__(self, chunks: list[RetrievalResult]) -> None:
        self._chunks = chunks

    async def get_by_lease(self, lease_id: str) -> list[RetrievalResult]:
        return self._chunks

    async def add(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError

    async def query(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError

    async def delete_by_lease(self, lease_id: str) -> None:  # pragma: no cover - unused
        return None


def _llm_response(payload: dict) -> tuple[dict, dict]:
    return payload, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


async def test_extract_returns_empty_dict_when_no_chunks():
    extractor = MetadataExtractor(vector_store=FakeVectorStore([]))

    result = await extractor.extract("lease_1")

    assert result == {}


async def test_extract_returns_only_non_null_fields():
    chunks = [_chunk("l::0", "Rent is $1000/month starting Jan 1 2024.", page=1)]
    extractor = MetadataExtractor(vector_store=FakeVectorStore(chunks))

    fake_groq = MagicMock()
    fake_groq.model = "test-model"
    fake_groq.complete_structured.return_value = _llm_response(
        {
            "start_date": "2024-01-01",
            "end_date": None,
            "rent_amount": "$1000/month",
            "location": None,
        }
    )
    extractor._llm_client = fake_groq

    result = await extractor.extract("lease_1")

    assert result == {"start_date": "2024-01-01", "rent_amount": "$1000/month"}


async def test_extract_returns_empty_dict_on_llm_error():
    chunks = [_chunk("l::0", "Rent is $1000/month.", page=1)]
    extractor = MetadataExtractor(vector_store=FakeVectorStore(chunks))

    fake_groq = MagicMock()
    fake_groq.model = "test-model"
    fake_groq.complete_structured.side_effect = LLMError("boom")
    extractor._llm_client = fake_groq

    result = await extractor.extract("lease_1")

    assert result == {}


async def test_extract_returns_empty_dict_on_malformed_schema():
    chunks = [_chunk("l::0", "Rent is $1000/month.", page=1)]
    extractor = MetadataExtractor(vector_store=FakeVectorStore(chunks))

    fake_groq = MagicMock()
    fake_groq.model = "test-model"
    # rent_amount should be a string or null, not a nested object
    fake_groq.complete_structured.return_value = _llm_response(
        {"rent_amount": {"nested": "bad"}}
    )
    extractor._llm_client = fake_groq

    result = await extractor.extract("lease_1")

    assert result == {}


async def test_extract_samples_only_first_n_chunks_by_page():
    many_chunks = [_chunk(f"l::{i}", f"chunk {i}", page=i) for i in range(10)]
    extractor = MetadataExtractor(vector_store=FakeVectorStore(many_chunks))

    fake_groq = MagicMock()
    fake_groq.model = "test-model"
    fake_groq.complete_structured.return_value = _llm_response({"start_date": "2024-01-01"})
    extractor._llm_client = fake_groq

    await extractor.extract("lease_1")

    prompt_used = fake_groq.complete_structured.call_args[0][0]
    # Only the first 5 chunks (page 0-4) should appear in the prompt.
    assert "chunk 4" in prompt_used
    assert "chunk 5" not in prompt_used


async def test_extract_includes_value_chunk_after_matching_heading():
    chunks = [
        _chunk(f"l::{i}", "RENT" if i == 4 else f"chunk {i}", page=i)
        for i in range(8)
    ]
    chunks[5] = _chunk("l::5", "$2,850.00 payable monthly", page=5)
    extractor = MetadataExtractor(vector_store=FakeVectorStore(chunks))
    fake_groq = MagicMock()
    fake_groq.model = "test-model"
    fake_groq.complete_structured.return_value = _llm_response(
        {"rent_amount": "$2,850.00/month"}
    )
    extractor._llm_client = fake_groq

    await extractor.extract("lease_1")

    prompt_used = fake_groq.complete_structured.call_args[0][0]
    assert "$2,850.00 payable monthly" in prompt_used


async def test_extract_result_distinguishes_provider_failure():
    extractor = MetadataExtractor(
        vector_store=FakeVectorStore([_chunk("l::0", "Rent is $1000/month.", 1)])
    )
    fake_groq = MagicMock()
    fake_groq.model = "test-model"
    fake_groq.complete_structured.side_effect = LLMError("boom")
    extractor._llm_client = fake_groq

    result = await extractor.extract_result("lease_1")

    assert result.status == MetadataExtractionStatus.FAILED
    assert result.fields == {}


async def test_concurrent_extraction_for_same_lease_is_deduplicated():
    extractor = MetadataExtractor(
        vector_store=FakeVectorStore([_chunk("l::0", "Rent is $1000/month.", 1)])
    )
    fake_groq = MagicMock()
    fake_groq.model = "test-model"

    def slow_response(*_args):
        time.sleep(0.05)
        return _llm_response({"rent_amount": "$1000/month"})

    fake_groq.complete_structured.side_effect = slow_response
    extractor._llm_client = fake_groq

    results = await asyncio.gather(
        extractor.extract_result("lease_1"),
        extractor.extract_result("lease_1"),
    )

    assert fake_groq.complete_structured.call_count == 1
    assert all(result.status == MetadataExtractionStatus.UPDATED for result in results)
