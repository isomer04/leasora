# ADR 007: Retrieval Quality, Evaluation Harness, and LLM-as-Judge Guardrails

**Date:** 2026-07-10
**Deciders:** Development Team

## Status: IN-FORCE (verified 2026-07-13)

Verified against the working tree:

- The 0.55 refusal gate, the cross-encoder reranker choice
  (`cross-encoder/ms-marco-MiniLM-L-6-v2`), and the BM25 + dense fusion
  (`hybrid_alpha=0.5`) match the code in `services/retrieval/`.
- `services/eval/judges.py` exposes `check_answer_grounded` (gated on
  `answer_guard_enabled`) and `audit_for_pii` (offline auditor) with
  fail-safe behavior on judge errors.
- `core/security.py::redact_pii` is the deterministic privacy guarantee;
  judges are layered on top as verifiers, not as the guarantee.
- `core/langfuse_client.py` is a graceful no-op when
  `langfuse_enabled` / `langfuse_public_key` / `langfuse_secret_key` /
  `langfuse_host` are not all set. PII redaction runs before any span
  input/output.
- Both `QueryCache` and `SemanticCache` are `lease_id`-scoped, config-keyed,
  and evicted by `IngestPipeline` on every successful ingest.
- Rate limiting in `services/rag/query_service.py` is an in-memory,
  per-process, per-client-IP rolling-60-second token bucket — for LLM cost
  control, not abuse protection.
- The CI `evals` job runs `pytest -m eval` against the golden dataset and
  fails the build if any documented floor (e.g. `MIN_REFUSAL_ACCURACY`)
  regresses.

The two implementation bugs recorded under "Two real implementation bugs" are
fixed in the working tree:
- `IngestPipeline.__init__` uses explicit `is None` checks for the two
  cache dependencies (comment in code explains why `or` fails for empty
  containers with `__len__`).
- An autouse pytest fixture (`apps/api/tests/conftest.py`) monkeypatches
  fresh cache instances into `query_service` before each test to prevent
  cross-test cache leakage.

## Context

The RAG core described in the README (PDF ingest, ChromaDB retrieval, a 0.55
refusal gate, grounded answers) lived only in a legacy flat-file prototype
(`app.py`, `ingest.py`, `retrieve.py`, `query.py`). During the monorepo
restructure, that logic was removed from `main` and not ported into the new
`apps/api` package — the new package was clean-architecture scaffolding with
the RAG core stubbed (`NotImplementedError` placeholders, mock data, hardcoded
eval literals).

This ADR records the resulting decisions and tradeoffs for the retrieval-quality features.

## Decisions

### 1. Recover and adapt, don't rewrite from scratch

The legacy prototype's clause-splitting, recursive chunking, and refusal-gate
logic were recovered from git history into `.legacy-reference/` and adapted
into the new service layer (`services/ingest/chunker.py`,
`services/rag/query_service.py`) rather than reinvented. This preserved
already-validated thresholds (1000-char oversized-clause boundary, 350-char
recursive chunk size, 50-char overlap, 80-char runt merge) instead of
re-deriving them from scratch.

### 2. Cross-encoder reranking is a net win, measured

A `cross-encoder/ms-marco-MiniLM-L-6-v2` second-pass reranker improved MRR
from 0.674 to 0.804 (+0.13) and refusal accuracy from 0.913 to 1.000 on the
23-question golden set. See
[docs/EVALUATION_REPORT.md](../EVALUATION_REPORT.md) for the full comparison
table. Kept config-gated (`rerank_enabled`, default off) so the cost of an
extra model call is opt-in.

### 3. Hybrid (BM25 + dense) retrieval requires reranking to be safe

Hybrid retrieval alone improved MRR (+0.033) but **regressed refusal accuracy**
from 0.913 to 0.826, because BM25's lexical overlap scoring has no semantic
understanding and can push an out-of-scope question's fused distance below
the refusal threshold. Combined with reranking, the regression fully
disappears (refusal accuracy back to 1.000). Decision: document this as a
required pairing, not just a suggestion — `hybrid_enabled` without
`rerank_enabled` is not treated as a safe default configuration.

### 4. Structured output uses JSON Object Mode, not strict `json_schema` mode

Groq's strict `json_schema` mode (constrained decoding, guaranteed schema
compliance) is currently limited to a small set of GPT-OSS models and does
not cover `llama-3.3-70b-versatile`, the model this project uses. JSON Object
Mode (`response_format={"type": "json_object"}`) is broadly supported and
guarantees syntactically valid JSON but not schema compliance, so the
response is validated against a Pydantic model (`StructuredAnswer`) after
parsing, with a code-fence-stripping fallback and a graceful degrade (a
distinct fallback message, not a 500) on validation failure.

### 5. LLM-as-judge guardrails detect; deterministic code guarantees

Two judge functions were added (`services/eval/judges.py`):
- `check_answer_grounded`: an optional runtime guard (`answer_guard_enabled`,
  off by default) that downgrades an answer to the canonical refusal if the
  judge finds unsupported claims against the retrieved context.
- `audit_for_pii`: an offline/detection-only auditor that flags PII a regex
  redactor might miss (full names, addresses, emails, phone numbers).

Neither judge is the actual privacy or correctness guarantee. The privacy
guarantee is `core.security.redact_pii`, applied deterministically before
anything is persisted to ChromaDB metadata, the answer cache, or Langfuse
traces. The judge is a verifier layered on top, and both judge functions fail
safe: a broken judge call or malformed judge output is treated as "not
grounded" / "has PII", never as a clean bill of health. This fail-safe path
was exercised for real (not just unit-tested with a mock) when a Groq daily
rate limit was hit mid-evaluation during this work.

### 6. LLM observability (Langfuse) is gracefully optional

`langfuse` (v4, OpenTelemetry-native SDK) was added as a main dependency.
`core/langfuse_client.py` wraps it so every span-creation call becomes a
no-op when `langfuse_public_key`/`langfuse_secret_key` are not configured —
verified by running the full test suite and booting the app with zero
Langfuse keys set. Question/prompt/answer text is passed through
`redact_pii` before entering any span input/output, preserving the ADR-003
no-PII-in-traces guarantee. The unused generic OpenTelemetry exporter was
subsequently removed; Langfuse is the only trace backend.

### 7. Answer caching is scoped per lease and invalidated on re-ingest

Exact-match (`QueryCache`) and near-duplicate (`SemanticCache`) answer
caches are both scoped strictly by `lease_id`, with the cache key including
retrieval config flags (rerank/hybrid enabled, thresholds) so toggling
config never serves a stale cross-configuration answer. `IngestPipeline`
evicts both caches for a `lease_id` after every successful ingest
(first-time or re-ingest), so a newly uploaded lease is never blocked by a
previously-cached refusal or stale answer.

### 8. Rate limiting targets LLM cost control, not abuse protection

Per ADR-006 (single-tenant, local v1, no user auth), the rate limiter added
in this work is intentionally minimal: an in-memory, per-process,
per-client-IP rolling-60-second token bucket. It is not distributed and does
not persist across restarts. This is a deliberate scope decision, not an
oversight — the goal is capping accidental LLM overspend during local/demo
use, not defending against coordinated abuse from many clients.

## Two real implementation bugs caught during this work (worth recording)

These are included because they're genuine engineering signal from measuring
and testing thoroughly, not because every implementation detail belongs in
an ADR:

1. **Falsy-empty-collection bug**: `IngestPipeline.__init__` used the
   `x or default` idiom for constructor-injected dependencies (matching the
   existing style for `pdf_parser_`/`chunker_`/etc.). Because `QueryCache`
   and `SemanticCache` both define `__len__`, a freshly constructed *empty*
   cache is falsy in Python, so `query_cache_ or query_cache` silently
   discarded a test's injected empty cache and fell back to the real
   module-level singleton. Fixed with explicit `is None` checks for those
   two specific dependencies, with a comment explaining why the otherwise-
   idiomatic `or` pattern doesn't work for them.
2. **Cross-test cache leakage**: `RAGQueryService` reads the module-level
   `query_cache`/`semantic_cache` singletons directly (unlike the vector
   store/embedder, which are constructor-injected), so answers cached by one
   test in `test_ask.py` were leaking into later tests reusing the same
   `LEASE_ID` + question string, causing nondeterministic test failures.
   Fixed with an autouse pytest fixture that monkeypatches fresh cache
   instances into the module before each test.

Both were caught by implementing features and then verifying them with real
integration tests before moving on, rather than by code review alone.

## Consequences

### Positive
- Every retrieval-quality claim in the README and evaluation report is a
  measured number from a real, reproducible eval harness, not an assertion.
- The documented hybrid-without-rerank refusal regression demonstrates that
  measurement discipline was applied even when the result was unfavorable.
- The landlord-identity chunking gap found during evaluation is now covered by
  a shipped fix and regression tests.
- The privacy/correctness guarantee boundary (judge detects, code
  guarantees) is enforced in code, not just described in prose.

### Negative
- More moving parts (reranker, BM25 index, two caches, two judges, Langfuse
  client) increase the surface area of `query_service.answer_question`,
  which is now a shared, frequently-touched file.
- The golden dataset (23 questions) is intentionally small; per-category
  metric deltas have wide confidence intervals and should not be
  over-interpreted (documented in the evaluation report).

## Related Decisions

- **ADR 003:** Prompt Versioning and LLM Observability — extended with a
  real Langfuse integration in this work.
- **ADR 005:** Self-Host Langfuse by Default — the client wrapper added here
  is agnostic to self-hosted vs. cloud Langfuse.
- **ADR 006:** No User Authentication in v1 — the rate-limiting scope
  decision here follows directly from that single-tenant framing.
- **docs/EVALUATION_REPORT.md:** the full measured numbers referenced above.
