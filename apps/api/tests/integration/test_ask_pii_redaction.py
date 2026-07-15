"""Integration tests for PII redaction at the AskResponse boundary.

The PII redaction contract has two halves:
1. Inputs to the LLM (Langfuse spans, log lines, judge prompts) must NOT
   carry unredacted PII. That half is exercised by
   ``test_ask.py::test_langfuse_spans_never_receive_raw_pii``.
2. The API response (``AskResponse.answer``, ``AskResponse.quote``,
   ``sources[*].excerpt``) must NOT carry unredacted PII either — even
   when the LLM echoes a verbatim clause.

This file exercises the second half.
"""

from unittest.mock import patch

import pytest

from leasora_api.services.rag.query_service import RAGQueryService
from leasora_api.services.retrieval.embedder import Embedder
from leasora_api.services.retrieval.query_cache import QueryCache
from leasora_api.services.retrieval.semantic_cache import SemanticCache
from leasora_api.services.retrieval.vector_store import ChromaStore

LEASE_ID = "lease-pii-test"


@pytest.fixture(autouse=True)
def _fresh_module_level_caches(monkeypatch):
    import leasora_api.services.rag.query_service as query_service_module

    monkeypatch.setattr(query_service_module, "query_cache", QueryCache())
    monkeypatch.setattr(query_service_module, "semantic_cache", SemanticCache())


@pytest.fixture
async def seeded_store_with_pii(tmp_path):
    """ChromaStore seeded with PII chunks whose text is semantically close to
    the questions in this file.

    The seeded chunks are written so each test's question is a near-embedding
    match — without that, the retrieval layer's refusal guard (min_distance
    over ``settings.refusal_threshold``) would short-circuit the test before
    the LLM is ever called, and we'd be testing the refusal path rather than
    the redaction boundary.
    """
    store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="pii-test")
    embedder = Embedder()

    # Each chunk's text is intentionally verbose and topical so a
    # semantically-related question lands inside the refusal threshold.
    ssn_chunk = (
        "Background check disclosure: the tenant's social security number "
        "123-45-6789 must be on file for credit and identity verification "
        "purposes prior to lease execution."
    )
    deposit_chunk = (
        "Deposit payment terms: the security deposit was paid with credit "
        "card 4111 1111 1111 1111 on the first of the month at lease "
        "signing, and is held in escrow per state landlord-tenant law."
    )
    contact_chunk = (
        "Tenant inquiries: please direct any questions about rent, "
        "deposits, or maintenance requests to leases@example.com during "
        "normal business hours, or call the leasing office number listed "
        "below."
    )
    clean_chunk = "The landlord is responsible for structural repairs and roof maintenance."
    texts = [ssn_chunk, deposit_chunk, contact_chunk, clean_chunk]
    embeddings = await embedder.aembed_documents(texts)
    await store.add(
        ids=["chunk-0", "chunk-1", "chunk-2", "chunk-3"],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {"source": "lease.pdf", "page": 1, "clause_type": "rental_term", "lease_id": LEASE_ID},
            {"source": "lease.pdf", "page": 2, "clause_type": "deposit", "lease_id": LEASE_ID},
            {"source": "lease.pdf", "page": 3, "clause_type": "contact", "lease_id": LEASE_ID},
            {"source": "lease.pdf", "page": 4, "clause_type": "maintenance", "lease_id": LEASE_ID},
        ],
    )
    return store, embedder


class TestPIIRedaction:
    """Tests for PII redaction in standard cases."""

    async def test_answer_is_redacted_for_planted_ssn(self, seeded_store_with_pii):
        """An LLM answer that verbatim echoes a planted SSN must be redacted."""
        store, embedder = seeded_store_with_pii
        service = RAGQueryService(
            embedder_=embedder,
            vector_store=store,
        )

        # Have the LLM echo the planted PII as the "answer" — the worst case
        # for the boundary.
        raw_answer_with_pii = {
            "answer": "The tenant's SSN is 123-45-6789 per the disclosure.",
            "quote": (
                "the tenant's social security number 123-45-6789 must be on file "
                "for credit and identity verification"
            ),
            "signal": "standard",
        }

        with patch.object(
            service._llm_client,
            "complete_structured",
            return_value=(raw_answer_with_pii, {"total_tokens": 42}),
        ):
            response = await service.answer_question(
                LEASE_ID, "What social security number is on file for the tenant?"
            )

        # SSN must be redacted in the API response.
        assert "123-45-6789" not in response.answer, "SSN must be redacted in answer"
        assert "[REDACTED_SSN]" in response.answer, "SSN redaction token must be in answer"
        assert "123-45-6789" not in response.quote, "SSN must be redacted in quote"
        assert "[REDACTED_SSN]" in response.quote, "SSN redaction token must be in quote"
        # Sources[*].excerpt also redacted.
        for source in response.sources:
            assert "123-45-6789" not in source.excerpt, "SSN must be redacted in source excerpts"

    async def test_credit_card_is_redacted_in_answer(self, seeded_store_with_pii):
        """A 16-digit CC number must be replaced with [REDACTED_CREDIT_CARD]."""
        store, embedder = seeded_store_with_pii
        service = RAGQueryService(
            embedder_=embedder,
            vector_store=store,
        )

        raw_answer_with_cc = {
            "answer": "The security deposit was paid with credit card 4111 1111 1111 1111.",
            "quote": (
                "the security deposit was paid with credit card 4111 1111 1111 "
                "1111 on the first of the month at lease signing"
            ),
            "signal": "standard",
        }

        # Use a question semantically near the deposit chunk so retrieval succeeds
        # and the answer is generated (rather than refused).
        with patch.object(
            service._llm_client,
            "complete_structured",
            return_value=(raw_answer_with_cc, {}),
        ):
            response = await service.answer_question(
                LEASE_ID, "How was the security deposit paid?"
            )

        assert response.answer != "I don't have enough information in the lease to answer that.", "Should retrieve relevant CC info"
        assert "4111 1111 1111 1111" not in response.answer, "CC number must be redacted in answer"
        assert "[REDACTED_CREDIT_CARD]" in response.answer, "CC redaction token must be in answer"


class TestPIIRedactionEdgeCases:
    """Tests for PII redaction edge cases and special scenarios."""

    async def test_email_is_redacted_in_excerpt(self, seeded_store_with_pii):
        """An email in source excerpts must be redacted before being sent to the client."""
        store, embedder = seeded_store_with_pii
        service = RAGQueryService(
            embedder_=embedder,
            vector_store=store,
        )

        raw_answer_no_pii = {
            "answer": "Reach out using the email listed in the contact section.",
            "quote": (
                "please direct any questions about rent, deposits, or maintenance "
                "requests to the leasing office during normal business hours"
            ),
            "signal": "standard",
        }

        with patch.object(
            service._llm_client,
            "complete_structured",
            return_value=(raw_answer_no_pii, {}),
        ):
            response = await service.answer_question(
                LEASE_ID, "Where can I send questions about rent or deposits?"
            )

        assert response.answer != "I don't have enough information in the lease to answer that.", "Should retrieve email info"
        for source in response.sources:
            assert "leases@example.com" not in source.excerpt, "Email must be redacted in source excerpts"

    async def test_clean_answer_passes_through_unchanged(self):
        """When there's no PII in the response or sources, the answer is returned verbatim."""
        import tempfile

        # ignore_cleanup_errors mirrors the eval runner's pattern — Chroma's
        # persistent client can keep file handles open on Windows past the
        # `with` block, which would otherwise raise PermissionError during
        # teardown.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
            store = ChromaStore(
                persist_dir=f"{tmp_dir}/chroma", collection_name="clean-test"
            )
            embedder = Embedder()
            text = "The landlord is responsible for structural repairs and roof maintenance."
            embeddings = await embedder.aembed_documents([text])
            await store.add(
                ids=["chunk-0"],
                embeddings=embeddings,
                documents=[text],
                metadatas=[
                    {"source": "lease.pdf", "page": 1, "clause_type": "maintenance", "lease_id": LEASE_ID}
                ],
            )

            service = RAGQueryService(
                embedder_=embedder,
                vector_store=store,
            )

            clean_answer = {
                "answer": "The landlord handles structural repairs.",
                "quote": "The landlord is responsible for structural repairs and roof maintenance.",
                "signal": "standard",
            }

            with patch.object(
                service._llm_client,
                "complete_structured",
                return_value=(clean_answer, {}),
            ):
                response = await service.answer_question(LEASE_ID, "Who handles repairs?")

            assert response.answer == clean_answer["answer"], "Clean answer must pass through unchanged"
            assert response.quote == clean_answer["quote"], "Clean quote must pass through unchanged"
