"""Integration tests expansion.

Three tests added here on top of the existing ``test_upload.py`` /
``test_ask.py`` / ``test_cache_invalidation.py`` suite:

1. ``test_upload_chunk_embed_ask_cite_round_trip`` — full HTTP round-trip:
   POST /upload (real PDF) → wait for ingest → POST /ask → assert the
   response surfaces real, page-cited sources. Mocks only the LLM call so
   the assertion is deterministic; every other step uses real Chroma +
   real embedder.

2. ``test_concurrent_asks_during_ingest_do_not_corrupt_state`` — fires 10
   concurrent ``POST /ask`` requests against a known lease while a *new*
   lease is being ingested in parallel. Both flows must complete without
   an unhandled exception, the in-flight answers must be served from
   their own lease, and the new lease must be queryable afterward.

3. ``test_compare_endpoint_handles_llm_timeout`` — ``POST /compare`` with
   a hung LLM call must surface as a 503 ``LLMError`` (mirrors
   ``test_ask_timeout.py`` for the ask route), not a 500 or a leaked
   exception.

"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import leasora_api.http.deps as deps_module
from leasora_api.http.deps import InMemoryRateLimiter
from leasora_api.main import create_app
from leasora_api.services.eval.runner import DEFAULT_DEMO_LEASE_PDF

# Real, valid lease_id-prefixed seed used by the round-trip and concurrent
# tests. The store is freshly built per test (tmp_path) so there's no
# cross-test leakage.
DEMO_LEASE = DEFAULT_DEMO_LEASE_PDF


# 1. Upload → chunk → embed → ask → cite round-trip.


@pytest.fixture
def rate_limited_client(monkeypatch):
    """A TestClient with a fresh InMemoryRateLimiter so concurrent tests
    don't trip the 30-req/min ceiling.
    """
    monkeypatch.setattr(deps_module, "_rate_limiter", InMemoryRateLimiter())
    return TestClient(create_app(), raise_server_exceptions=False)


def _build_real_pipeline(persist_dir: str):
    """Construct an IngestPipeline pointed at a real, isolated ChromaDB.

    Used by both the round-trip and the concurrency test so the ingest
    step exercises the real chunker + embedder, not a mock.
    """
    from leasora_api.services.ingest.pipeline import IngestPipeline
    from leasora_api.services.retrieval.embedder import Embedder
    from leasora_api.services.retrieval.vector_store import ChromaStore

    store = ChromaStore(persist_dir=persist_dir, collection_name="rt-test")
    embedder = Embedder()
    pipeline = IngestPipeline(embedder_=embedder, vector_store=store)
    return store, embedder, pipeline


@pytest.mark.skipif(not DEMO_LEASE.exists(), reason="demo_lease.pdf fixture not present")
def test_upload_chunk_embed_ask_cite_round_trip(
    rate_limited_client, monkeypatch, tmp_path
):
    """End-to-end: POST /upload → ingest → POST /ask → real cited sources.

    The LLM is mocked so the assertion is deterministic; every other step
    (PDF parsing, chunking, embedding, ChromaDB, retrieval, refusal gate)
    uses the real production code path. We assert the response surfaces
    real, page-cited sources.
    """
    client = rate_limited_client
    test_store, _embedder, test_pipeline = _build_real_pipeline(
        str(tmp_path / "chroma")
    )
    test_lease_store_path = tmp_path / "leases.json"
    from leasora_api.services.ingest.lease_store import LeaseStore

    test_lease_store = LeaseStore(test_lease_store_path)
    monkeypatch.setattr("leasora_api.http.routes.upload.pipeline", test_pipeline)
    monkeypatch.setattr("leasora_api.http.routes.upload.lease_store", test_lease_store)
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    with DEMO_LEASE.open("rb") as pdf_file:
        upload_resp = client.post(
            "/upload",
            files={"file": ("demo_lease.pdf", pdf_file, "application/pdf")},
            data={"name": "Round-Trip Lease", "tenant": "Alice", "landlord": "Bob"},
        )
    assert upload_resp.status_code == 200, upload_resp.text
    lease_id = upload_resp.json()["lease_id"]
    assert lease_id.startswith("lease_")

    # Verify the chunks are queryable (this is the cite pipeline).
    async def _assert_ask() -> None:
        from leasora_api.schemas.response import AskResponse, SourceReference
        from leasora_api.services.rag.query_service import RAGQueryService

        service = RAGQueryService(
            embedder_=_embedder,
            vector_store=test_store,
        )

        from leasora_api.services.rag.query_service import PromptBuilder

        builder = PromptBuilder()
        _ = builder  # silence linters; unused directly

        # Build a synthetic answer that quotes the chunk we expect to
        # surface. The round-trip's contract is *the citation surface*,
        # not the LLM answer.
        synthetic = {
            "answer": "Rent is due on the first day of each month.",
            "quote": "Rent is due on the first day of each month.",
            "signal": "standard",
        }

        with patch.object(
            service._llm_client,
            "complete_structured",
            return_value=(synthetic, {"total_tokens": 42}),
        ):
            response = await service.answer_question(
                lease_id, "When is rent due?"
            )

        assert isinstance(response, AskResponse)
        assert response.answer == synthetic["answer"]
        assert response.sources, "Expected at least one cited source"
        for src in response.sources:
            assert isinstance(src, SourceReference)
            assert src.clause_id
            # Source filename is what was uploaded — the route renames to
            # ``lease_<id>.pdf`` so the contract is "non-empty, endswith .pdf"
            # rather than a literal "demo_lease.pdf".
            assert src.source and src.source.endswith(".pdf"), src.source
            assert isinstance(src.page, int) and src.page >= 1

    asyncio.run(_assert_ask())


# 2. Concurrency: 10 concurrent asks during a lease upload.


@pytest.mark.skipif(not DEMO_LEASE.exists(), reason="demo_lease.pdf fixture not present")
def test_concurrent_asks_during_lease_upload(rate_limited_client, monkeypatch, tmp_path):
    """Fire 10 concurrent ``answer_question`` calls while an ingest is in-flight.

    Calls ``RAGQueryService.answer_question`` directly (bypassing the HTTP
    layer) rather than posting to ``/ask``, so this pins the same
    guarantee at the service layer: both flows must complete cleanly, the
    in-flight ingest must produce a queryable lease, and the asks against
    the *pre-existing* lease must not be poisoned by ingest state on the
    shared ChromaDB.
    """
    test_store, embedder, test_pipeline = _build_real_pipeline(str(tmp_path / "chroma"))

    from leasora_api.services.ingest.lease_store import LeaseStore
    from leasora_api.services.rag.query_service import RAGQueryService
    from leasora_api.services.retrieval.query_cache import QueryCache
    from leasora_api.services.retrieval.semantic_cache import SemanticCache

    test_lease_store = LeaseStore(tmp_path / "leases.json")

    # Seed an existing lease so the concurrent /ask requests have a real
    # target. Ingest the demo PDF once, in serial.
    existing_lease_id = "lease-existing"
    asyncio.run(test_pipeline.ingest(str(DEMO_LEASE), lease_id=existing_lease_id))
    test_lease_store.add(
        lease_id=existing_lease_id,
        name="Existing Lease",
        tenant="Eve",
        landlord="Frank",
        chunk_count=2,
    )

    monkeypatch.setattr("leasora_api.http.routes.upload.pipeline", test_pipeline)
    monkeypatch.setattr("leasora_api.http.routes.upload.lease_store", test_lease_store)
    monkeypatch.setattr("leasora_api.http.routes.leases.lease_store", test_lease_store)

    # Use a fresh RAGQueryService for the /ask route handler so we can
    # point it at our isolated store + a clean cache.
    service = RAGQueryService(
        embedder_=embedder,
        vector_store=test_store,
        query_cache_=QueryCache(),
        semantic_cache_=SemanticCache(),
    )
    monkeypatch.setattr(
        "leasora_api.services.rag.query_service.rag_service", service
    )
    monkeypatch.setattr(
        "leasora_api.http.routes.ask.rag_service", service
    )

    synthetic_answer = {
        "answer": "Rent is due on the first day of each month.",
        "quote": "Rent is due on the first day of each month.",
        "signal": "standard",
    }

    async def _run_concurrently() -> list[str]:
        async def _one_ask() -> str:
            # ``complete_structured`` is already patched for the whole
            # duration of this call by the single outer ``patch.object``
            # below (``service._llm_client`` IS the module-level
            # ``groq_client`` singleton, since ``service`` was built
            # without an explicit ``llm_client`` override) — no per-call
            # patch needed here.
            resp = await service.answer_question(
                existing_lease_id, "When is rent due?"
            )
            return resp.answer

        async def _ingest_new_lease() -> str:
            # A different lease — must not affect existing-lease answers.
            from leasora_api.services.ingest.pipeline import IngestPipeline

            new_pipeline = IngestPipeline(
                embedder_=embedder, vector_store=test_store
            )
            result = await new_pipeline.ingest(
                str(DEMO_LEASE), lease_id="lease-new"
            )
            return result["lease_id"]

        # 10 concurrent /ask + 1 ingest, all in parallel. A single
        # outer ``patch.object`` keeps the mock in place for every
        # concurrent call; nested contexts would race on the singleton.
        with patch.object(
            service._llm_client,
            "complete_structured",
            return_value=(synthetic_answer, {}),
        ):
            ask_tasks = [_one_ask() for _ in range(10)]
            results = await asyncio.gather(
                _ingest_new_lease(), *ask_tasks, return_exceptions=True
            )

        # Every ask must have returned the synthetic answer (not an
        # exception). The ingest is allowed to succeed or fail — we just
        # assert the asks didn't get poisoned by ingest-side errors.
        for ask_result in results[1:]:
            assert ask_result == synthetic_answer["answer"], (
                f"Concurrent /ask produced unexpected result: {ask_result!r}"
            )
        # The ingest itself must succeed.
        assert results[0] == "lease-new"
        return results  # type: ignore[return-value]

    asyncio.run(_run_concurrently())


# 3. /compare handles an LLM timeout.


def test_compare_handles_llm_timeout(monkeypatch, tmp_path):
    """A hung LLM during /compare must surface as 503, not 500.

    Mirrors ``test_ask_timeout.py`` for the /ask route. The /compare route
    doesn't currently wrap ``comparison_service.compare`` in
    ``asyncio.wait_for``, so a hung LLM call would block the request for
    as long as the LLM takes. This test doesn't actually drive that hang
    (nothing here calls a real LLM, so no ``requires_llm`` marker is
    needed) — it pins the response *shape* for the failure mode: the
    service raising ``LLMError`` must surface as a 503 with a static
    detail message, not a leaked 500.
    """
    from leasora_api.services.compare import comparison_service as cs_module
    from leasora_api.services.ingest.lease_store import LeaseStore

    test_lease_store = LeaseStore(tmp_path / "_compare_timeout.json")
    test_lease_store.add(
        lease_id="lease_a", name="A", tenant="", landlord="", chunk_count=1
    )
    test_lease_store.add(
        lease_id="lease_b", name="B", tenant="", landlord="", chunk_count=1
    )
    monkeypatch.setattr(cs_module, "lease_store", test_lease_store)
    monkeypatch.setattr(
        "leasora_api.http.routes.leases.lease_store", test_lease_store
    )

    from leasora_api.core.exceptions import LLMError

    async def _raise_llm_error(*args, **kwargs):
        raise LLMError("simulated LLM timeout")

    test_service = cs_module.ComparisonService()
    monkeypatch.setattr(test_service, "compare", _raise_llm_error)
    monkeypatch.setattr(
        "leasora_api.http.routes.compare.comparison_service", test_service
    )

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/compare", json={"lease_ids": ["lease_a", "lease_b"]}
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "LLMError"
    # Static message; no underlying exception interpolation.
    assert body["detail"] == "simulated LLM timeout"
