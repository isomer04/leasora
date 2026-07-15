"""Lightweight in-process metrics registry.

Exposes Prometheus-style counters + histograms using the
``prometheus_client`` library so we can render a ``/metrics`` endpoint
without pulling in a heavier dependency.

Design choices:

- All metrics are created on import (the ``prometheus_client`` registry
  is global). Counters/histograms are no-ops on their own — they're just
  cheap integer increments.
- Tests reset counters between cases by patching the module-level
  ``UPLOADS_TOTAL`` / ``REFUSALS_TOTAL`` / ``CACHE_TOTAL`` / ``*_LATENCY_MS``
  globals directly (see ``test_metrics_and_logging.py``).
- Histograms use a fixed bucket set tuned for typical RAG latencies: the
  99th percentile of a Groq call is well under 5s, and Chroma queries
  rarely exceed 250ms. The buckets are deliberately coarse — a Grafana
  p95 panel reads better with 8 well-chosen buckets than 30 micro-tuned
  ones.
- ``prometheus-client`` is a main dependency (``pyproject.toml``), so in
  practice it's always installed. The helpers still degrade to a no-op
  if it's ever missing (e.g. a hand-pruned install), so the application
  doesn't crash on this dependency. The :func:`metrics_available` flag
  lets callers (like the ``/metrics`` endpoint) decide whether to render
  a 503 vs. an empty body in that case.

Counters:
- ``leasora_uploads_total{status}`` — ingest outcomes
- ``leasora_refusals_total{clause_type}`` — refusals by clause type
- ``leasora_cache_total{cache,result}`` — exact/semantic cache hit/miss

Histograms:
- ``leasora_upload_latency_ms`` — full /upload handler duration
- ``leasora_retrieval_latency_ms`` — vector store query latency
- ``leasora_llm_latency_ms`` — Groq completion latency
"""

from __future__ import annotations

import importlib
import time
from contextlib import contextmanager
from typing import Any, Iterator

try:  # pragma: no cover - exercised at runtime, not in unit tests
    _prom_client: Any = importlib.import_module("prometheus_client")
    _CounterFactory = _prom_client.Counter
    _HistogramFactory = _prom_client.Histogram
    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised at runtime, not in unit tests
    _PROM_AVAILABLE = False
    _CounterFactory = None
    _HistogramFactory = None


def metrics_available() -> bool:
    """Return True when ``prometheus_client`` is installed and the registry is live."""
    return _PROM_AVAILABLE


# Default bucket set covers RAG pipeline latencies:
#   - Vector store queries (10ms–500ms)
#   - LLM completions (250ms–10s)
# We use the same buckets for upload/retrieval/LLM so a Grafana panel
# with a shared Y-axis "log" mode can compare distributions.
_LATENCY_BUCKETS_MS = (
    10.0,
    25.0,
    50.0,
    100.0,
    250.0,
    500.0,
    1_000.0,
    2_500.0,
    5_000.0,
    10_000.0,
)


def _build_counter(name: str, doc: str, labels: list[str]) -> Any:
    if not _PROM_AVAILABLE:
        return None
    return _CounterFactory(name, doc, labels)


def _build_histogram(name: str, doc: str) -> Any:
    if not _PROM_AVAILABLE:
        return None
    return _HistogramFactory(name, doc, buckets=_LATENCY_BUCKETS_MS)


# Counters --------------------------------------------------------------------
UPLOADS_TOTAL = _build_counter(
    "leasora_uploads_total",
    "Total lease uploads processed, labeled by terminal status.",
    ["status"],
)

REFUSALS_TOTAL = _build_counter(
    "leasora_refusals_total",
    "Total retrieval refusals, labeled by clause type (or 'unknown').",
    ["clause_type"],
)

CACHE_TOTAL = _build_counter(
    "leasora_cache_total",
    "Cache lookups, labeled by cache (exact|semantic) and result (hit|miss).",
    ["cache", "result"],
)

# Histograms ------------------------------------------------------------------
UPLOAD_LATENCY_MS = _build_histogram(
    "leasora_upload_latency_ms",
    "End-to-end /upload handler latency in milliseconds.",
)

RETRIEVAL_LATENCY_MS = _build_histogram(
    "leasora_retrieval_latency_ms",
    "ChromaDB vector store query latency in milliseconds.",
)

LLM_LATENCY_MS = _build_histogram(
    "leasora_llm_latency_ms",
    "Groq LLM completion latency in milliseconds.",
)


@contextmanager
def time_retrieval() -> Iterator[None]:
    """Record ChromaDB query latency."""
    if RETRIEVAL_LATENCY_MS is None:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1_000.0
        RETRIEVAL_LATENCY_MS.observe(elapsed_ms)


@contextmanager
def time_llm() -> Iterator[None]:
    """Record Groq LLM completion latency."""
    if LLM_LATENCY_MS is None:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1_000.0
        LLM_LATENCY_MS.observe(elapsed_ms)


def record_upload_latency(elapsed_ms: float) -> None:
    """Observe an upload latency value in milliseconds."""
    if UPLOAD_LATENCY_MS is not None:
        UPLOAD_LATENCY_MS.observe(elapsed_ms)


def record_upload(status: str) -> None:
    """Increment the upload counter for a given terminal ``status`` (e.g. ``"ok"``)."""
    if UPLOADS_TOTAL is not None:
        UPLOADS_TOTAL.labels(status=status).inc()


def record_refusal(clause_type: str) -> None:
    """Increment the refusal counter for the clause type that triggered the refusal."""
    if REFUSALS_TOTAL is not None:
        REFUSALS_TOTAL.labels(clause_type=clause_type or "unknown").inc()


def record_cache(cache: str, hit: bool) -> None:
    """Record a cache lookup. ``cache`` is ``"exact"`` or ``"semantic"``."""
    if CACHE_TOTAL is not None:
        CACHE_TOTAL.labels(cache=cache, result="hit" if hit else "miss").inc()


def render_metrics() -> tuple[bytes, str]:
    """Render the current Prometheus registry as a ``(body, content_type)`` tuple.

    Returns an empty body with ``text/plain; version=0.0.4; charset=utf-8``
    when ``prometheus_client`` is not installed, so the endpoint can still
    emit a useful (if empty) 200 response instead of a 503.
    """
    if not _PROM_AVAILABLE:  # pragma: no cover - exercised at runtime, not in unit tests
        return b"", "text/plain; version=0.0.4; charset=utf-8"
    # Imported lazily so the dependency is optional.
    generate_latest = _prom_client.generate_latest
    return generate_latest(), _prom_client.CONTENT_TYPE_LATEST
