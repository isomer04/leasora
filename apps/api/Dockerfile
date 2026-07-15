# Multi-stage Dockerfile for Leasora FastAPI backend.
#
# Build context: this Dockerfile is referenced by services/compose/*.yml as
# ``dockerfile: apps/api/Dockerfile`` with ``context: ../..`` (the monorepo
# root). All ``COPY`` paths are therefore relative to the monorepo root,
# not to ``apps/api``.
#
# Concurrency contract: we run with ``--workers 1`` to match the
# single-process JSON stores (``LeaseStore``, ``ComparisonStore``) until
# the SQLite WAL migration lands. Multi-worker rolling restarts would race
# on the non-WAL JSON files; single-worker is the safe minimal fix.

# Stage 1: Base - Install uv package manager
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
RUN pip install --no-cache-dir uv


# Stage 2: Dependencies - Build virtual environment
FROM base AS deps
WORKDIR /app

# Copy dependency + workspace files from the monorepo root (build context).
# The root pyproject.toml declares the uv workspace; apps/api/pyproject.toml
# declares the package itself; packages/shared-schemas is the cross-language
# shared types package the API depends on at build time (hatchling reads
# its presence in the workspace).
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY packages/shared-schemas ./packages/shared-schemas
COPY apps/api/src ./apps/api/src

# Install dependencies (frozen, no dev). ``--package leasora-api`` keeps the
# install scoped to the API even with a workspace pyproject.toml at root.
RUN uv sync --package leasora-api --frozen --no-dev


# Stage 3: Runtime - Production image
FROM base AS runtime
WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 leasora && \
    chown -R leasora:leasora /app

# Copy virtual environment from deps stage
COPY --from=deps --chown=leasora:leasora /app/.venv /app/.venv

# Copy application code
COPY --chown=leasora:leasora apps/api/src ./apps/api/src

# Switch to non-root user
USER leasora

# Set PATH to use venv
ENV PATH="/app/.venv/bin:$PATH"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

# Expose port
EXPOSE 8000

# Run production server (NOT fastapi dev).
# Uses single-worker concurrency for the JSON store strategy.
CMD ["uvicorn", "leasora_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]