# @leasora/shared-schemas

Reserved Python package for **internal, Python-only** shared Pydantic models.

## Contract source of truth

The **API contract is owned by the FastAPI backend and exposed via OpenAPI.**
TypeScript types for the frontend are generated from that OpenAPI schema into
[`packages/shared-types`](../shared-types) (`pnpm gen:types`). Do **not**
hand-maintain a parallel copy of request/response models here — that would
create two competing sources of truth and inevitable drift.

Use this package only for domain models that are:

- shared across **multiple Python packages** (not just `apps/api`), and
- **not** part of the HTTP API contract (which already flows through OpenAPI).

At present there are no such models, so this package intentionally ships no
modules. Add code here only when a genuine cross-package Python need appears.

See [ADR 004 — No tRPC, why OpenAPI codegen](../../docs/adr/004-no-trpc-why-openapi-codegen.md).
