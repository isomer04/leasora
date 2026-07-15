"""Process liveness + dependency-readiness endpoints.

- ``/healthz`` — process up. Always 200 while the event loop is
  responsive. Use as a Kubernetes ``livenessProbe`` target.
- ``/readyz``  — process can serve real traffic. Returns 200 when the
  vector store is reachable and the embeddings model is loaded; 503
  otherwise. Use as a ``readinessProbe`` target so a fresh pod doesn't
  get traffic before its dependencies are warm.
- ``/health``  — legacy route. Kept for the existing CI smoke test and
  for clients on the old contract; behaves identically to ``/healthz``.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field, ConfigDict

from leasora_api.core.constants import APP_VERSION

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "version": "0.2.0",
            }
        }
    )

    status: str = Field(..., description="Service status")
    version: str = Field(default="0.2.0", description="API version")


def _base_response() -> HealthResponse:
    return HealthResponse(status="ok", version=APP_VERSION)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check (legacy)",
    description="Legacy health check. Prefer /healthz + /readyz for probes.",
    tags=["health"],
    responses={200: {"description": "Service is healthy"}},
)
async def health_check() -> HealthResponse:
    """Legacy health check (kept for backwards compatibility with existing tests)."""
    return _base_response()


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness probe",
    description=(
        "Liveness probe — returns 200 whenever the process is up and the "
        "event loop is responsive. Use as a Kubernetes ``livenessProbe`` "
        "target. Does NOT check downstream dependencies (use ``/readyz`` "
        "for that)."
    ),
    tags=["health"],
    responses={200: {"description": "Process is alive"}},
)
async def healthz() -> HealthResponse:
    """Liveness probe — checks the process, not the dependencies."""
    return _base_response()


@router.get(
    "/readyz",
    summary="Readiness probe",
    description=(
        "Readiness probe — returns 200 only when downstream dependencies "
        "(ChromaDB collection reachable, embeddings model loaded) are "
        "available. Returns 503 with an explanatory error code otherwise."
    ),
    tags=["health"],
    responses={
        200: {"description": "Service is ready to serve traffic"},
        503: {"description": "Dependencies unavailable"},
    },
)
async def readyz(response: Response) -> dict[str, str | list[str]]:
    """Readiness probe — checks the dependencies too.

    Failure modes surfaced here:
    - ``chromadb_unreachable`` — Chroma persistent client failed to list.
    - ``embedder_not_loaded`` — sentence-transformers model not warmed
      up yet (cold start); the readiness probe should be retried.
    - ``reason`` — human-readable summary.
    """
    failures: list[str] = []

    # 1. Chroma reachable. Bound the wait so a slow disk doesn't block
    #    the probe past the orchestrator's timeout.
    try:
        from leasora_api.services.retrieval.vector_store import chroma

        def _probe_chroma() -> None:
            # ``count()`` is the cheapest call that exercises both the
            # client construction and the persistent storage path.
            chroma._ensure_collection().count()

        await asyncio.wait_for(asyncio.to_thread(_probe_chroma), timeout=2.0)
    except Exception as error:  # pragma: no cover - exercised at runtime
        logger.warning("readyz: ChromaDB probe failed: %s", error)
        failures.append("chromadb_unreachable")

    # 2. Embedder loaded. The model is loaded lazily; ``_ensure_loaded``
    #    is idempotent and cheap once the weights are in memory.
    try:
        from leasora_api.services.retrieval.embedder import embedder

        await asyncio.wait_for(asyncio.to_thread(embedder._ensure_loaded), timeout=5.0)
    except Exception as error:  # pragma: no cover - exercised at runtime
        logger.warning("readyz: embedder probe failed: %s", error)
        failures.append("embedder_not_loaded")

    if failures:
        response.status_code = 503
        return {
            "status": "not_ready",
            "reason": ", ".join(failures),
            "failures": failures,
        }
    return {"status": "ready", "reason": "", "failures": []}
