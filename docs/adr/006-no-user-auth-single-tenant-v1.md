# ADR 006: No User Authentication in v1 (Single-Tenant)

**Date:** 2026-07-09
**Deciders:** Development Team

## Status: IN-FORCE (verified 2026-07-13)

Verified: no `(auth)` route group, no `login`/`signup`/`reset-password` pages,
no `PasswordInput` component, no `lib/auth.ts` token helper, no bearer-token
header in API requests. The partial UI scaffolding was removed, and the API is
unauthenticated.

Rate limiting in v1 is scoped to LLM cost control (per ADR-007 §8) — not
abuse protection. The future path described in this ADR (managed auth
provider → Postgres scoping → user-scoped ChromaDB → access control on
routes) is still the correct migration path when multi-tenancy is added.

## Context

Early scaffolding for Leasora's web app included the beginnings of a
username/password authentication system:

- `(auth)` route group with `login`, `signup`, and `reset-password` pages
- A `PasswordInput` UI component and password validation constants
- A localStorage-backed token helper (`lib/auth.ts`) and a `UserMenu` with a
  "Sign out" action
- A bearer-token header injected into API requests

None of it was wired to a real identity provider or backend — there was no
`users` table, no session issuance, and no token verification on the API. It
was UI shell only.

At the same time, a question came up about where to store user credentials.
The vector store (ChromaDB) is the wrong place for that: it has no row-level
access control, no uniqueness constraints, and its access pattern is
approximate nearest-neighbor search, not exact-match auth lookups. Credentials
also must never sit in the same store as lease chunks that flow into LLM
context and traces.

That left three real options:

1. **Build full password auth** ourselves (hashing, sessions, reset flow).
2. **Delegate auth** to a managed provider (Clerk, Auth0, Supabase Auth, Cognito).
3. **Ship v1 with no auth** as a single-tenant tool and defer multi-tenancy.

## Decision

**Ship v1 as a single-tenant application with no user authentication.** Remove
the partial auth scaffolding rather than leave a half-built system in the tree.

Rationale:

- **Leasora is an AI/RAG project first.** Its value and its hard problems live
  in ingestion, retrieval, the refusal gate, grounding, evaluation, and
  observability — not in login plumbing that every web app already has.
- **A half-built auth system is a liability**, not a feature. It invites
  security questions it can't answer (reset flows, session fixation, rate
  limiting) and distracts from the parts of the system that matter.
- **Rolling our own credential storage is easy to get subtly wrong**, and it
  adds a sensitive-data surface (password hashes, PII) with no offsetting
  product benefit at this stage.
- **The relational layer (Postgres) is not justified by auth alone.** If a
  relational store is added later, it should earn its place through documents,
  query/answer history, feedback, and eval runs — not a `users` table for a
  single-tenant demo. (See "Related Decisions".)

### What this means concretely

- No login/signup/reset UI. The marketing site's calls-to-action open the app
  directly (`/dashboard`).
- The API is unauthenticated in v1. It is intended for local/demo use and must
  not be exposed to the public internet as-is.
- No credentials are stored anywhere — not in ChromaDB, not in Postgres.

## Consequences

### Positive

- Smaller surface area; no auth code to secure, test, or explain.
- Focus stays on the AI pipeline and observability.
- No credential or PII storage risk introduced.

### Negative

- **No data isolation.** All uploaded leases share one space; the app is not
  safe for multiple untrusted users as-is.
- **Not production-exposable** without adding auth and access control first.
- The marketing pricing page describes tiers that don't map to any real
  account system yet (it is illustrative product framing only).

### Mitigation / Guardrails

- Treat v1 as **local/single-tenant**. Do not deploy the API to a public,
  unauthenticated endpoint.
- When multi-user support is needed, prefer **Option 2 (delegate to a managed
  provider)** so Leasora stores a user ID for scoping data — never passwords.
- If credentials are ever stored, they must be **salted hashes** produced by a
  slow password hashing algorithm (argon2id / bcrypt / scrypt), kept in a
  relational store, and excluded from anything that flows into LLM context or
  traces.

## Future Path (when auth is needed)

1. Add a managed auth provider and obtain a stable `user_id` per request.
2. Introduce a Postgres relational layer for documents, history, and feedback
   (the use cases that actually justify it), scoping rows by `user_id`.
3. Scope ChromaDB collections/metadata by `user_id` to enforce isolation.
4. Add access control to API routes and require a verified token.

## Related Decisions

- **ADR 003:** Prompt Versioning & LLM Observability (Langfuse) — retained;
  credentials must never enter traces.
- **ADR 005:** Self-Hosted Langfuse — Langfuse's own backing Postgres is
  unrelated to application-level storage and is unaffected by this decision.
