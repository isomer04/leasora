"""Integration tests for the real RAG query flow (retrieve -> refuse -> ground -> answer).

Uses a real embedder + a temp ChromaDB store seeded with a couple of chunks,
and mocks only the LLM call so these tests stay fast and deterministic while
still exercising the true retrieval + refusal-gate logic.
"""

from unittest.mock import patch

import pytest

from leasora_api.core.config import get_settings
from leasora_api.core.constants import REFUSAL_MESSAGE
from leasora_api.services.rag.query_service import (
    STRUCTURED_OUTPUT_FALLBACK_MESSAGE,
    RAGQueryService,
)
from leasora_api.services.retrieval.embedder import Embedder
from leasora_api.services.retrieval.query_cache import QueryCache
from leasora_api.services.retrieval.semantic_cache import SemanticCache
from leasora_api.services.retrieval.vector_store import ChromaStore

LEASE_ID = "lease-ask-test"


@pytest.fixture(autouse=True)
def _fresh_module_level_caches(monkeypatch):
    """Prevent the module-level QueryCache/SemanticCache singletons from
    leaking cached answers between tests (they're shared process-wide, and
    each test otherwise reuses the same LEASE_ID + question strings).
    """
    import leasora_api.services.rag.query_service as query_service_module

    monkeypatch.setattr(query_service_module, "query_cache", QueryCache())
    monkeypatch.setattr(query_service_module, "semantic_cache", SemanticCache())

STRUCTURED_ANSWER = {
    "answer": "Rent is due on the 1st of each month.",
    "quote": "Rent is due on the first day of each month.",
    "signal": "standard",
}


@pytest.fixture
async def seeded_store(tmp_path):
    """A ChromaStore seeded with a couple of real-embedded lease chunks."""
    store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="ask-test")
    embedder = Embedder()  # real model, already cached locally

    texts = [
        "Rent is due on the first day of each month. Late payments incur a 5% penalty.",
        "The landlord is responsible for structural repairs and roof maintenance.",
    ]
    embeddings = await embedder.aembed_documents(texts)
    await store.add(
        ids=["chunk-0", "chunk-1"],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {"source": "lease.pdf", "page": 1, "clause_type": "rental_term", "lease_id": LEASE_ID},
            {"source": "lease.pdf", "page": 2, "clause_type": "maintenance", "lease_id": LEASE_ID},
        ],
    )
    return store, embedder


async def test_supported_question_returns_grounded_answer_with_sources(seeded_store):
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    with patch.object(
        service._llm_client,
        "complete_structured",
        return_value=(STRUCTURED_ANSWER, {"total_tokens": 42}),
    ) as mock_complete:
        response = await service.answer_question(LEASE_ID, "When is rent due?")

    mock_complete.assert_called_once()
    assert response.answer != REFUSAL_MESSAGE
    assert response.answer == STRUCTURED_ANSWER["answer"]
    assert response.quote == STRUCTURED_ANSWER["quote"]
    assert response.signal == "standard"
    assert response.sources, "Expected real sources from retrieval"
    assert response.sources[0].source == "lease.pdf"
    assert response.sources[0].page in (1, 2)
    assert 0.0 <= response.confidence <= 1.0


async def test_malformed_structured_output_degrades_gracefully(seeded_store):
    """If the LLM's JSON output fails schema validation, fall back instead of 500ing."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    malformed = {"answer": "ok", "quote": "ok"}  # missing required "signal"

    with patch.object(
        service._llm_client, "complete_structured", return_value=(malformed, {})
    ):
        response = await service.answer_question(LEASE_ID, "When is rent due?")

    assert response.answer == STRUCTURED_OUTPUT_FALLBACK_MESSAGE
    assert response.sources, "Sources should still be returned even on fallback"
    assert response.quote is None
    assert response.signal is None


async def test_unsupported_question_refuses_without_calling_llm(seeded_store):
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    with patch.object(service._llm_client, "complete_structured") as mock_complete:
        response = await service.answer_question(
            LEASE_ID, "What internet speed is included in the unit?"
        )

    mock_complete.assert_not_called()
    assert response.answer == REFUSAL_MESSAGE
    assert response.sources == []
    assert response.confidence == 0.0


async def test_refusal_threshold_is_config_driven(seeded_store, monkeypatch):
    """Tightening the refusal threshold should force a refusal for a previously answered question."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    # Force refusal_threshold to ~0 so even a decent semantic match is refused.
    settings = get_settings()
    monkeypatch.setattr(settings, "refusal_threshold", 0.0)

    with patch.object(service._llm_client, "complete_structured") as mock_complete:
        response = await service.answer_question(LEASE_ID, "When is rent due?")

    mock_complete.assert_not_called()
    assert response.answer == REFUSAL_MESSAGE


async def test_no_chunks_for_lease_refuses(seeded_store):
    """A lease_id with no ingested chunks must refuse rather than answer from another lease."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    with patch.object(service._llm_client, "complete_structured") as mock_complete:
        response = await service.answer_question("some-other-lease", "When is rent due?")

    mock_complete.assert_not_called()
    assert response.answer == REFUSAL_MESSAGE


async def test_reranking_applied_when_enabled(seeded_store, monkeypatch):
    """When rerank_enabled is True, the reranker must be invoked and its output used."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    settings = get_settings()
    monkeypatch.setattr(settings, "rerank_enabled", True)

    with (
        patch.object(
            service._llm_client, "complete_structured", return_value=(STRUCTURED_ANSWER, {})
        ),
        patch.object(
            service._reranker, "arerank", wraps=service._reranker.arerank
        ) as mock_rerank,
    ):
        await service.answer_question(LEASE_ID, "When is rent due?")

    mock_rerank.assert_called_once()


async def test_reranking_skipped_when_disabled(seeded_store):
    """When rerank_enabled is False (default), the reranker must not be invoked."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    with (
        patch.object(
            service._llm_client, "complete_structured", return_value=(STRUCTURED_ANSWER, {})
        ),
        patch.object(service._reranker, "arerank") as mock_rerank,
    ):
        await service.answer_question(LEASE_ID, "When is rent due?")

    mock_rerank.assert_not_called()


async def test_hybrid_fusion_applied_when_enabled(seeded_store, monkeypatch):
    """When hybrid_enabled is True, BM25 fusion must run and still surface real sources."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    settings = get_settings()
    monkeypatch.setattr(settings, "hybrid_enabled", True)

    with patch.object(
        service._llm_client, "complete_structured", return_value=(STRUCTURED_ANSWER, {})
    ):
        response = await service.answer_question(LEASE_ID, "When is rent due?")

    assert response.answer != REFUSAL_MESSAGE
    assert response.sources


async def test_hybrid_fusion_skipped_when_disabled(seeded_store):
    """When hybrid_enabled is False (default), _hybrid_fuse must not be invoked."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    with (
        patch.object(
            service._llm_client, "complete_structured", return_value=(STRUCTURED_ANSWER, {})
        ),
        patch.object(service, "_hybrid_fuse") as mock_fuse,
    ):
        await service.answer_question(LEASE_ID, "When is rent due?")

    mock_fuse.assert_not_called()


async def test_answer_is_cached_and_skips_llm_on_second_call(seeded_store):
    """Repeated identical questions on the same lease must skip the LLM call."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    with patch.object(
        service._llm_client,
        "complete_structured",
        return_value=(STRUCTURED_ANSWER, {}),
    ) as mock_complete:
        first = await service.answer_question(LEASE_ID, "When is rent due?")
        second = await service.answer_question(LEASE_ID, "When is rent due?")

    mock_complete.assert_called_once()
    assert first.answer == second.answer


async def test_cache_scoped_by_lease_does_not_leak_across_leases(seeded_store):
    """A cached answer for one lease must not be served for a different lease_id."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    with patch.object(
        service._llm_client,
        "complete_structured",
        return_value=(STRUCTURED_ANSWER, {}),
    ):
        await service.answer_question(LEASE_ID, "When is rent due?")

    # A different lease with no ingested chunks must refuse, not return the
    # other lease's cached answer.
    with patch.object(service._llm_client, "complete_structured") as mock_complete:
        response = await service.answer_question("different-lease-id", "When is rent due?")

    mock_complete.assert_not_called()
    assert response.answer == REFUSAL_MESSAGE


async def test_cache_disabled_calls_llm_every_time(seeded_store, monkeypatch):
    """With cache_enabled=False, repeated identical questions must call the LLM each time."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    settings = get_settings()
    monkeypatch.setattr(settings, "cache_enabled", False)

    with patch.object(
        service._llm_client,
        "complete_structured",
        return_value=(STRUCTURED_ANSWER, {}),
    ) as mock_complete:
        await service.answer_question(LEASE_ID, "When is rent due?")
        await service.answer_question(LEASE_ID, "When is rent due?")

    assert mock_complete.call_count == 2


async def test_answer_guard_disabled_by_default_skips_judge_call(seeded_store):
    """With answer_guard_enabled False (default), the groundedness judge must not run."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    with (
        patch.object(
            service._llm_client, "complete_structured", return_value=(STRUCTURED_ANSWER, {})
        ),
        patch(
            "leasora_api.services.rag.query_service.check_answer_grounded"
        ) as mock_guard,
    ):
        response = await service.answer_question(LEASE_ID, "When is rent due?")

    mock_guard.assert_not_called()
    assert response.answer == STRUCTURED_ANSWER["answer"]


async def test_answer_guard_downgrades_ungrounded_answer_to_refusal(seeded_store, monkeypatch):
    """When enabled and the judge says not grounded, the answer must be downgraded.

    The answer becomes REFUSAL_MESSAGE but sources are preserved so the user 
    can verify which clauses the model consulted. Previously this test asserted 
    sources == [] — that behavior masked the user's ability to audit a downgrade. 
    Confidence is also retained.
    """
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    settings = get_settings()
    monkeypatch.setattr(settings, "answer_guard_enabled", True)

    with (
        patch.object(
            service._llm_client, "complete_structured", return_value=(STRUCTURED_ANSWER, {})
        ),
        patch(
            "leasora_api.services.rag.query_service.check_answer_grounded",
            return_value=(False, ["hallucinated claim"]),
        ),
    ):
        response = await service.answer_question(LEASE_ID, "When is rent due?")

    assert response.answer == REFUSAL_MESSAGE, "Ungrounded answer must be downgraded to refusal"
    # Sources and confidence are no longer zeroed out on a downgrade
    # so the user can audit which clauses were consulted.
    assert response.sources != [], "Sources must be retained for user audit"
    assert response.confidence is not None and response.confidence > 0, "Confidence must be retained"


async def test_answer_guard_passes_through_grounded_answer(seeded_store, monkeypatch):
    """When enabled and the judge says grounded, the real answer must be returned unchanged."""
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    settings = get_settings()
    monkeypatch.setattr(settings, "answer_guard_enabled", True)

    with (
        patch.object(
            service._llm_client, "complete_structured", return_value=(STRUCTURED_ANSWER, {})
        ),
        patch(
            "leasora_api.services.rag.query_service.check_answer_grounded",
            return_value=(True, []),
        ),
    ):
        response = await service.answer_question(LEASE_ID, "When is rent due?")

    assert response.answer == STRUCTURED_ANSWER["answer"]
    assert response.sources


async def test_langfuse_spans_never_receive_raw_pii(seeded_store):
    """PII in the question/answer must be redacted before reaching Langfuse spans.

    ADR-003 guarantee: no raw PII in traces. Since Langfuse isn't configured
    in tests, spans are no-ops, but this test asserts on the *inputs* passed
    to the langfuse_client wrapper's start_span/start_generation, which is
    where the redaction must happen regardless of whether tracing is enabled.
    """
    store, embedder = seeded_store
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=store,
    )

    question_with_pii = "My SSN is 123-45-6789, when is rent due?"

    captured_span_inputs = []
    captured_gen_inputs = []

    original_start_span = service._langfuse.start_span
    original_start_generation = service._langfuse.start_generation

    def _capture_start_span(name, input=None, metadata=None):  # noqa: A002
        captured_span_inputs.append(input)
        return original_start_span(name, input=input, metadata=metadata)

    def _capture_start_generation(name, model, input=None, metadata=None):  # noqa: A002
        captured_gen_inputs.append(input)
        return original_start_generation(name, model=model, input=input, metadata=metadata)

    with (
        patch.object(
            service._llm_client, "complete_structured", return_value=(STRUCTURED_ANSWER, {})
        ),
        patch.object(service._langfuse, "start_span", side_effect=_capture_start_span),
        patch.object(
            service._langfuse, "start_generation", side_effect=_capture_start_generation
        ),
    ):
        await service.answer_question(LEASE_ID, question_with_pii)

    for span_input in captured_span_inputs:
        assert "123-45-6789" not in str(span_input)
    for gen_input in captured_gen_inputs:
        assert "123-45-6789" not in str(gen_input)
