# Release Notes

This file summarizes notable user-facing changes. The package manifests remain
at version `0.2.0`; the `0.3.0` work below is therefore marked unreleased until
a coordinated version bump and tag are created.

## Unreleased — 0.3.0: Retrieval Quality and Evaluation

### Highlights

- Restored the complete PDF ingestion and grounded question-answering path.
- Added a 23-question golden dataset and reproducible retrieval and answer
  quality evaluation.
- Added optional BM25 hybrid retrieval and cross-encoder reranking.
- Added structured LLM output, exact and semantic caches, groundedness checks,
  privacy auditing, request rate limiting, and Prometheus metrics.
- Added lease listing, chunk inspection, metadata refresh, comparison history,
  and cascade deletion of lease artifacts.
- Expanded optional Langfuse and OpenTelemetry instrumentation while keeping
  external observability disabled by default.

Measured results and caveats are maintained in the
[evaluation report](docs/EVALUATION_REPORT.md). Design rationale is recorded in
[ADR 007](docs/adr/007-retrieval-quality-and-evaluation.md).

### Compatibility

No intentionally breaking HTTP API changes are included. Generated response
types gained additive fields for source, page, quote, and signal metadata.
Regenerate frontend contracts with `pnpm gen:types` after API schema changes.

### Configuration

New `LEASORA_` settings cover retrieval, reranking, hybrid fusion, caching,
answer guards, privacy audits, and rate limits. Defaults preserve the dense
retrieval path and keep optional LLM judging and observability off.

## 0.2.0 — Monorepo and Typed API Foundation

### Highlights

- Organized the project into `apps/`, `packages/`, `services/`, and `docs/`.
- Adopted pnpm workspaces and Turborepo for JavaScript orchestration.
- Moved the backend to a layered FastAPI package with Grimp import contracts.
- Added a Next.js App Router frontend and OpenAPI-generated TypeScript types.
- Added prompt versioning, centralized configuration, PII-aware logging, and
  optional tracing integrations.
### Migration notes

- Environment variables use the `LEASORA_` prefix.
- The API package lives under `apps/api/src/leasora_api/`.
- The web package lives under `apps/web/`.
- Frontend API definitions are generated with `pnpm gen:types`.
- The default Compose stack runs the web app, API, and Chroma. Optional
  Langfuse v3 services require `--profile observability` and service secrets;
  see [ADR 005](docs/adr/005-langfuse-self-host-default.md).

## Versioning policy

A release is considered published only when package manifests, release notes,
and the Git tag agree. Do not infer deployment readiness from this file:
Leasora remains an unauthenticated, local/single-tenant educational project as
documented in [ADR 006](docs/adr/006-no-user-auth-single-tenant-v1.md).
