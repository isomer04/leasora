from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from leasora_api.core.config import Settings, get_settings
from leasora_api.core.constants import APP_VERSION
from leasora_api.core.exceptions import LeasoraError
from leasora_api.core.langfuse_client import langfuse_client
from leasora_api.core.logging import reconfigure_from_settings
from leasora_api.core.metrics import metrics_available, render_metrics
from leasora_api.http import routes
from leasora_api.http.middleware import (
    MaxBodySizeMiddleware,
    RequestIDMiddleware,
    leasora_error_handler,
    unhandled_exception_handler,
)
from leasora_api.services.ingest.retention import purge_expired_leases
from leasora_api.services.llm.registry import registry

logger = logging.getLogger(__name__)
_RETENTION_SWEEP_INTERVAL_SECONDS = 24 * 60 * 60


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App startup and shutdown events."""
    settings = get_settings()
    # Reconfigure structured-logging globals from the loaded settings.
    # The HMAC salt only matters for observability, so a load failure here
    # is logged + ignored rather than crashing startup.
    try:
        reconfigure_from_settings(settings.log_hash_salt)
    except Exception:  # pragma: no cover - defensive only
        logger.exception("Failed to apply log configuration from settings (non-fatal).")

    if not settings.log_hash_salt:
        logger.warning(
            "LEASORA_LOG_HASH_SALT is not set; falling back to the hard-coded "
            "dev salt. user_query_hash values in access logs are dictionary-"
            "attackable (guessable) by anyone with log read access. Set "
            "LEASORA_LOG_HASH_SALT in production."
        )

    if settings.rate_limit_enabled is False:
        logger.warning(
            "rate_limit_enabled=False; LLM-tier cost control is disabled. "
            "Set LEASORA_RATE_LIMIT_ENABLED=true unless this is intentional."
        )

    retention_task = asyncio.create_task(
        _run_retention_worker(settings.upload_retention_days),
        name="lease-retention-worker",
    )
    try:
        # Sync prompts to Langfuse (no-op when Langfuse keys aren't configured)
        await registry.sync_prompts_to_langfuse()
        # Warmup retrieval models so the first user request doesn't pay download +
        # load latency. Only runs when the feature is enabled (no wasted startup
        # time if reranking is off).
        await _warmup_models(settings)
        yield
    finally:
        retention_task.cancel()
        with suppress(asyncio.CancelledError):
            await retention_task
        # Flush pending Langfuse SDK spans (no-op when disabled).
        langfuse_client.flush()


async def _run_retention_worker(retention_days: int) -> None:
    """Sweep immediately and then daily until application shutdown."""
    while True:
        try:
            await purge_expired_leases(retention_days)
        except Exception:
            logger.exception("Unexpected failure during retention sweep")
        await asyncio.sleep(_RETENTION_SWEEP_INTERVAL_SECONDS)


async def _warmup_models(settings: Settings) -> None:
    """Pre-load heavy ML models to avoid cold-start latency on first request.

    Offloaded to a thread so the event loop isn't blocked during download/load.
    Failures are logged and swallowed — a failed warmup just means the first
    request will be slower, not that the app can't start.
    """

    logger = logging.getLogger(__name__)

    try:
        from leasora_api.services.retrieval.embedder import embedder
        logger.info("Warming up embedding model: %s", embedder.model_name)
        await asyncio.to_thread(embedder._ensure_loaded)
    except Exception:
        logger.warning("Embedder warmup failed (will retry on first request)", exc_info=True)

    if settings.rerank_enabled:
        try:
            from leasora_api.services.retrieval.reranker import reranker
            logger.info("Warming up reranker model: %s", reranker.model_name)
            await asyncio.to_thread(reranker._ensure_loaded)
        except Exception:
            logger.warning("Reranker warmup failed (will retry on first request)", exc_info=True)


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Sets up:
    - RequestIDMiddleware (X-Request-ID propagation + log correlation +
      access-log emission)
    - MaxBodySizeMiddleware (request body cap at the ASGI layer)
    - Exception handling middleware (centralized domain → HTTP translation)
    - CORS middleware (frontend communication)
    - Observability (tracing, Prometheus metrics endpoint)
    - Route registration (organized by feature)
    """
    settings = get_settings()
    app = FastAPI(
        title="Leasora API",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    # Registered via add_exception_handler (not ASGI middleware) so error
    # responses are still processed by CORSMiddleware below.
    app.add_exception_handler(LeasoraError, leasora_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Pure ASGI middlewares (run inside CORS so error responses get headers)
    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # CORS middleware for frontend communication
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Feature-organized route registration
    app.include_router(routes.health.router, prefix="", tags=["health"])
    app.include_router(routes.ask.router, prefix="/ask", tags=["rag"])
    app.include_router(routes.leases.router, prefix="/leases", tags=["leases"])
    app.include_router(routes.compare.router, prefix="/compare", tags=["rag"])
    app.include_router(routes.upload.router, prefix="/upload", tags=["ingest"])
    app.include_router(routes.eval.router, prefix="/eval", tags=["eval"])

    @app.get(
        "/metrics",
        summary="Prometheus metrics",
        description="Prometheus exposition endpoint for monitoring.",
        tags=["ops"],
        responses={200: {"description": "Prometheus text exposition"}},
        include_in_schema=False,
    )
    async def metrics() -> Response:
        """Render the Prometheus registry.

        The endpoint is mounted here (vs. as a route module) because it
        is operational plumbing: not part of the public API surface,
        intentionally not included in the generated OpenAPI schema, and
        cheap to inline next to ``create_app``.
        """
        body, content_type = render_metrics()
        headers = {"Cache-Control": "no-store"}
        # If ``prometheus_client`` isn't installed we still return 200 +
        # an empty body so operational probes remain healthy during a
        # hand-pruned deployment.
        if not metrics_available():
            headers["X-Leasora-Metrics-Stub"] = "prometheus_client not installed"
        return Response(content=body, media_type=content_type, headers=headers)

    return app


app = create_app()
