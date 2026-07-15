"""Unit tests for ComparisonService (LLM-powered clause-by-clause comparison).

Mocks GroqClient at the same seam as test_groq_client.py / test_hybrid.py
(RetrievalResult fakes) so no real network/LLM call is made.
"""

from unittest.mock import MagicMock

import pytest

from leasora_api.core.exceptions import LLMError, NotFoundError
from leasora_api.schemas.request import LeaseMetadata
from leasora_api.services.compare.comparison_service import ComparisonService
from leasora_api.services.retrieval.vector_store import RetrievalResult


def _chunk(id_: str, text: str, clause_type: str, lease_id: str, page: int = 1) -> RetrievalResult:
    return RetrievalResult(
        id=id_,
        text=text,
        metadata={"clause_type": clause_type, "lease_id": lease_id, "page": page, "source": "x.pdf"},
        distance=0.0,
    )


class FakeVectorStore:
    """Minimal VectorStore fake returning canned chunks per lease_id."""

    def __init__(self, chunks_by_lease: dict[str, list[RetrievalResult]]) -> None:
        self._chunks_by_lease = chunks_by_lease

    async def get_by_lease(self, lease_id: str) -> list[RetrievalResult]:
        return self._chunks_by_lease.get(lease_id, [])

    async def add(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError

    async def query(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError

    async def delete_by_lease(self, lease_id: str) -> None:  # pragma: no cover - unused
        return None


class FakeLeaseStore:
    def __init__(self, names: dict[str, str]) -> None:
        self._names = names

    def get(self, lease_id: str) -> LeaseMetadata | None:
        if lease_id not in self._names:
            return None
        return LeaseMetadata(
            id=lease_id,
            name=self._names[lease_id],
            tenant="Not yet extracted",
            landlord="Not yet extracted",
            start_date="Not yet extracted",
            end_date="Not yet extracted",
            rent_amount="Not yet extracted",
            location="Not yet extracted",
        )


def _make_llm_response(payload: dict) -> tuple[dict, dict]:
    return payload, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


@pytest.fixture(autouse=True)
def _patch_lease_store(monkeypatch):
    """Patch the module-level lease_store used inside comparison_service."""
    names = {"lease_1": "Lease One", "lease_2": "Lease Two"}
    monkeypatch.setattr(
        "leasora_api.services.compare.comparison_service.lease_store", FakeLeaseStore(names)
    )


async def _run_compare(service: ComparisonService, lease_ids: list[str]):
    return await service.compare(lease_ids)


async def test_compare_raises_not_found_when_lease_missing(monkeypatch):
    vector_store = FakeVectorStore({})
    service = ComparisonService(vector_store=vector_store)

    with pytest.raises(NotFoundError):
        await service.compare(["lease_1", "lease_missing"])


async def test_compare_raises_not_found_when_no_chunks_indexed():
    vector_store = FakeVectorStore({"lease_1": [], "lease_2": []})
    service = ComparisonService(vector_store=vector_store)

    with pytest.raises(NotFoundError):
        await service.compare(["lease_1", "lease_2"])


async def test_compare_one_sided_clause_produces_deterministic_difference():
    chunks = {
        "lease_1": [_chunk("l1::0", "Tenant may sublet with landlord consent.", "assignment", "lease_1")],
        "lease_2": [_chunk("l2::0", "Rent is $1000/month.", "rental_term", "lease_2")],
    }
    vector_store = FakeVectorStore(chunks)
    service = ComparisonService(vector_store=vector_store)

    result = await service.compare(["lease_1", "lease_2"])

    assert len(result.differences) == 2
    types = {d.clause_type for d in result.differences}
    assert types == {"assignment", "rental_term"}
    assignment_diff = next(d for d in result.differences if d.clause_type == "assignment")
    assert "missing from Lease Two" in assignment_diff.difference
    assert assignment_diff.lease2_value == "Not present"


async def test_compare_shared_clause_type_calls_llm_and_parses_result(monkeypatch):
    chunks = {
        "lease_1": [_chunk("l1::0", "Rent is $1000/month.", "rental_term", "lease_1")],
        "lease_2": [_chunk("l2::0", "Rent is $2000/month.", "rental_term", "lease_2")],
    }
    vector_store = FakeVectorStore(chunks)
    service = ComparisonService(vector_store=vector_store)

    fake_groq = MagicMock()
    fake_groq.model = "test-model"
    fake_groq.complete_structured.return_value = _make_llm_response(
        {
            "differences": [
                {
                    "clause_type": "rental_term",
                    "lease1_value": "$1000/month",
                    "lease2_value": "$2000/month",
                    "difference": "Lease 2 rent is double",
                }
            ],
            "insight": "Lease 2 costs significantly more per month.",
        }
    )
    service._llm_client = fake_groq

    result = await service.compare(["lease_1", "lease_2"])

    assert len(result.differences) == 1
    assert result.differences[0].difference == "Lease 2 rent is double"
    assert "Lease 2 costs significantly more per month." in result.key_insights


async def test_compare_drops_clause_on_llm_error_but_keeps_others(monkeypatch):
    chunks = {
        "lease_1": [
            _chunk("l1::0", "Rent is $1000/month.", "rental_term", "lease_1"),
            _chunk("l1::1", "Tenant may sublet.", "assignment", "lease_1"),
        ],
        "lease_2": [
            _chunk("l2::0", "Rent is $2000/month.", "rental_term", "lease_2"),
            _chunk("l2::1", "No subletting allowed.", "assignment", "lease_2"),
        ],
    }
    vector_store = FakeVectorStore(chunks)
    service = ComparisonService(vector_store=vector_store)

    fake_groq = MagicMock()
    fake_groq.model = "test-model"

    def side_effect(prompt, temperature, _timeout=None):
        if "rental_term" in prompt:
            raise LLMError("boom")
        return _make_llm_response(
            {
                "differences": [
                    {
                        "clause_type": "assignment",
                        "lease1_value": "Allowed",
                        "lease2_value": "Not allowed",
                        "difference": "Subletting policy differs",
                    }
                ],
                "insight": None,
            }
        )

    fake_groq.complete_structured.side_effect = side_effect
    service._llm_client = fake_groq

    result = await service.compare(["lease_1", "lease_2"])

    clause_types = {d.clause_type for d in result.differences}
    assert clause_types == {"assignment"}
    assert any("Note: comparison failed for 1 of 2" in insight for insight in result.key_insights)


async def test_compare_drops_clause_on_malformed_llm_output_but_keeps_other_clauses():
    chunks = {
        "lease_1": [
            _chunk("l1::0", "Rent is $1000/month.", "rental_term", "lease_1"),
            _chunk("l1::1", "Tenant may sublet.", "assignment", "lease_1"),
        ],
        "lease_2": [
            _chunk("l2::0", "Rent is $2000/month.", "rental_term", "lease_2"),
            _chunk("l2::1", "No subletting allowed.", "assignment", "lease_2"),
        ],
    }
    vector_store = FakeVectorStore(chunks)
    service = ComparisonService(vector_store=vector_store)

    fake_groq = MagicMock()
    fake_groq.model = "test-model"

    def side_effect(prompt, temperature, _timeout=None):
        if "rental_term" in prompt:
            # Missing required keys inside the difference (schema-invalid)
            return _make_llm_response({"differences": [{"clause_type": "rental_term"}], "insight": None})
        return _make_llm_response(
            {
                "differences": [
                    {
                        "clause_type": "assignment",
                        "lease1_value": "Allowed",
                        "lease2_value": "Not allowed",
                        "difference": "Subletting policy differs",
                    }
                ],
                "insight": None,
            }
        )

    fake_groq.complete_structured.side_effect = side_effect
    service._llm_client = fake_groq

    result = await service.compare(["lease_1", "lease_2"])

    clause_types = {d.clause_type for d in result.differences}
    assert clause_types == {"assignment"}
    assert any("comparison failed" in insight.lower() for insight in result.key_insights)


async def test_compare_raises_llm_error_on_total_failure_with_no_fallback():
    """Single shared clause type, it fails, and there's no one-sided clause
    to fall back on: this must surface as an error, not an empty success."""
    chunks = {
        "lease_1": [_chunk("l1::0", "Rent is $1000/month.", "rental_term", "lease_1")],
        "lease_2": [_chunk("l2::0", "Rent is $2000/month.", "rental_term", "lease_2")],
    }
    vector_store = FakeVectorStore(chunks)
    service = ComparisonService(vector_store=vector_store)

    fake_groq = MagicMock()
    fake_groq.model = "test-model"
    fake_groq.complete_structured.return_value = _make_llm_response(
        {"differences": [{"clause_type": "rental_term"}], "insight": None}
    )
    service._llm_client = fake_groq

    with pytest.raises(LLMError):
        await service.compare(["lease_1", "lease_2"])


async def test_compare_total_llm_failure_with_no_one_sided_clauses_raises():
    chunks = {
        "lease_1": [_chunk("l1::0", "Rent is $1000/month.", "rental_term", "lease_1")],
        "lease_2": [_chunk("l2::0", "Rent is $2000/month.", "rental_term", "lease_2")],
    }
    vector_store = FakeVectorStore(chunks)
    service = ComparisonService(vector_store=vector_store)

    fake_groq = MagicMock()
    fake_groq.model = "test-model"
    fake_groq.complete_structured.side_effect = LLMError("boom")
    service._llm_client = fake_groq

    with pytest.raises(LLMError):
        await service.compare(["lease_1", "lease_2"])


async def test_compare_outer_timeout_treated_as_total_failure(monkeypatch):
    """When the overall fan-out itself times out, the service treats every
    attempted shared clause type as failed. With no one-sided fallback the
    service must surface ``LLMError``; with one-sided clauses it must
    return them and add a note in ``key_insights``.
    """
    import asyncio as _asyncio

    from leasora_api.services.compare import comparison_service as cs_mod

    fake_groq = MagicMock()
    fake_groq.model = "test-model"

    async def _raise_timeout(*_args, **_kwargs):
        raise _asyncio.TimeoutError("outer fan-out timed out")

    monkeypatch.setattr(cs_mod.asyncio, "wait_for", _raise_timeout)

    # Case 1: only shared clauses → total failure → LLMError.
    shared_only_chunks = {
        "lease_1": [_chunk("l1::0", "Rent is $1000/month.", "rental_term", "lease_1")],
        "lease_2": [_chunk("l2::0", "Rent is $2000/month.", "rental_term", "lease_2")],
    }
    service = ComparisonService(vector_store=FakeVectorStore(shared_only_chunks))
    service._llm_client = fake_groq
    with pytest.raises(LLMError):
        await service.compare(["lease_1", "lease_2"])

    # Case 2: with a one-sided clause, the response surfaces it + a timeout
    # note instead of raising.
    mixed_chunks = {
        "lease_1": [
            _chunk("l1::0", "Rent is $1000/month.", "rental_term", "lease_1"),
            _chunk("l1::1", "Maintenance handled by landlord.", "maintenance", "lease_1"),
        ],
        "lease_2": [_chunk("l2::0", "Rent is $2000/month.", "rental_term", "lease_2")],
    }
    service2 = ComparisonService(vector_store=FakeVectorStore(mixed_chunks))
    service2._llm_client = fake_groq
    result = await service2.compare(["lease_1", "lease_2"])

    # The one-sided "maintenance" clause still produces its deterministic diff.
    types = {d.clause_type for d in result.differences}
    assert "maintenance" in types
    # And the outer-timeout failure shows up in the insights.
    assert any("all shared clause types" in i for i in result.key_insights)
