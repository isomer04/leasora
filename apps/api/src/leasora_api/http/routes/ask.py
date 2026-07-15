"""Ask question about lease endpoint.

Clean code design:
- Route handler focuses only on HTTP contract (request → response)
- Validation delegated to RequestValidator (SRP)
- Exception handling delegated to middleware (DRY)
- Uses Retrieval-Augmented Generation grounded in real ChromaDB retrieval,
  with a distance-based refusal gate (see RAGQueryService.answer_question)
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from leasora_api.core.config import get_settings
from leasora_api.core.exceptions import LLMError
from leasora_api.core.logging import (
    hash_query,
    internal_correlation_id_var,
    lease_id_var,
    stash_request_metadata,
    user_query_hash_var,
)
from leasora_api.core.validators import validate_lease_id, validate_question
from leasora_api.http.deps import enforce_rate_limit
from leasora_api.schemas.request import AskRequest
from leasora_api.schemas.response import AskResponse
from leasora_api.services.rag.query_service import RAGQueryService, rag_service

logger = logging.getLogger(__name__)

router = APIRouter()


def get_rag_service() -> RAGQueryService:
    """Dependency provider for RAGQueryService.

    Returns the module-level singleton by default. Override in tests via
    ``app.dependency_overrides[get_rag_service] = lambda: mock_service``
    to inject a fake or differently-configured service without patching
    module-level imports.
    """
    return rag_service


def validate_ask_request(request: AskRequest) -> AskRequest:
    """Validate ask request fields.

    Delegates to focused validator functions (SRP principle).
    Each validator has a single responsibility and clear error messages.

    Also populates the per-request observability contextvars so the
    access-log middleware can stamp every log line with the lease
    identifier and a salted HMAC of the user question.

    Args:
        request: The incoming request

    Returns:
        Validated request (unchanged, just validated)

    Raises:
        ValidationError: If any field fails validation
    """
    validate_lease_id(request.lease_id)
    validate_question(request.question)
    # Stash metadata for the access-log middleware. We stash under the
    # server-generated internal correlation id (NOT the client-influenceable
    # X-Request-ID) because FastAPI's dependency
    # resolver runs the dependency under a separate anyio task whose
    # contextvar mutations don't propagate back to the ASGI middleware,
    # and two concurrent requests sending the same X-Request-ID would
    # otherwise overwrite each other's stashed entry. The middleware pops
    # this entry at response-finally time.
    stash_key = internal_correlation_id_var.get() or ""
    if stash_key:
        stash_request_metadata(
            stash_key,
            lease_id=request.lease_id,
            user_query_hash=hash_query(request.question),
        )
    # Mirror into the contextvars for log-line correlation within this
    # request; the access log falls back to the stash if those don't
    # propagate.
    lease_id_var.set(request.lease_id)
    user_query_hash_var.set(hash_query(request.question))
    return request


@router.post(
    "",
    response_model=AskResponse,
    summary="Ask a question about a lease",
    description="Use RAG to answer questions grounded in lease content",
    dependencies=[Depends(enforce_rate_limit)],
    responses={
        200: {"description": "Answer with sources"},
        400: {"description": "Invalid lease ID or question"},
        404: {"description": "Lease not found"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "LLM unreachable or timed out"},
    },
)
async def ask(
    request: Annotated[AskRequest, Depends(validate_ask_request)],
    service: Annotated[RAGQueryService, Depends(get_rag_service)],
) -> AskResponse:
    """Ask a natural language question about a specific lease.

    The system uses Retrieval-Augmented Generation (RAG) to:
    1. Search for relevant clauses in the lease
    2. Generate an answer grounded in the lease content
    3. Provide source references

    Args:
        request: Question and lease ID (validated by dependency)

    Returns:
        Answer with confidence score and source references

    Raises:
        LeasoraError: Domain errors (validation, not found, LLM errors)
                     These are caught by middleware and translated to HTTP

    Note:
        The full RAG flow is bounded by ``settings.llm_timeout_seconds``
        so a hung Groq call cannot hold a worker indefinitely. On timeout,
        the client gets a 503 with a static "Answer generation timed out"
        message — the underlying httpexception is not echoed.

        The Groq call itself runs in a worker thread (``asyncio.to_thread``
        inside ``RAGQueryService``); cancelling this coroutine on timeout
        does not stop that thread. ``GroqClient._call_groq`` bounds its own
        retries to the same overall deadline (instead of each retry getting
        a fresh budget), so the thread converges on this timeout rather
        than a multiple of it, but the in-flight attempt still runs to its
        own completion in the background after the 503 is returned.
    """
    timeout = float(get_settings().llm_timeout_seconds)
    try:
        return await asyncio.wait_for(
            service.answer_question(request.lease_id, request.question),
            timeout=timeout,
        )
    except asyncio.TimeoutError as error:
        logger.exception("Ask timed out for lease %s after %.1fs", request.lease_id, timeout)
        raise LLMError("Answer generation timed out") from error
