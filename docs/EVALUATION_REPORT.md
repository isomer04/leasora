# Evaluation Report

This report records measured results from `leasora eval` against
[`questions.jsonl`](../apps/api/tests/evals/golden/questions.jsonl): 23 labeled
questions across `factual`, `statute`, `red_flag`, and `out_of_scope`.
Fixture provenance and regeneration instructions are documented in the
[golden dataset guide](../apps/api/tests/evals/golden/README.md).

> [!CAUTION]
> This is one synthetic lease and a small sample. The results are regression
> baselines, not estimates of production performance or legal accuracy.

## Reproduce

```bash
cd apps/api
leasora eval --compare-hybrid --out hybrid_comparison.json
leasora eval --full
```

The full run uses Groq for answer-quality and privacy judges and may incur cost.
Model versions, provider behavior, and quotas can affect repeatability.

## Retrieval results

| Configuration | MRR | Recall@k | Precision@k | Refusal accuracy |
|---|---:|---:|---:|---:|
| Dense baseline | 0.674 | 0.783 | 0.157 | 0.913 |
| Cross-encoder reranked | **0.804** | 0.826 | 0.165 | **1.000** |
| Hybrid, no reranking | 0.707 | 0.826 | 0.165 | 0.826 |
| Hybrid with reranking | **0.804** | 0.826 | 0.165 | **1.000** |

Settings: `retrieval_top_k=5`, `rerank_top_n=20`, and
`hybrid_alpha=0.5`.

### Category MRR: dense vs. reranked

| Category | Dense | Reranked | Change |
|---|---:|---:|---:|
| Factual | 0.85 | 1.00 | +0.15 |
| Statute | 0.80 | 0.90 | +0.10 |
| Red flag | 0.75 | 1.00 | +0.25 |
| Out of scope | 0.00 | 0.00 | Not applicable; no relevant IDs |

### Category MRR: dense vs. hybrid without reranking

| Category | Dense | Hybrid | Change |
|---|---:|---:|---:|
| Factual | 0.85 | 0.90 | +0.05 |
| Statute | 0.80 | 0.80 | 0.00 |
| Red flag | 0.75 | 0.8125 | +0.0625 |
| Out of scope | 0.00 | 0.00 | Not applicable |

## Negative result: hybrid retrieval needs reranking

Hybrid retrieval improved MRR by 0.033 and recall@k by 0.043 but reduced
refusal accuracy from 0.913 to 0.826. The regression came from out-of-scope
queries: lexical overlap promoted irrelevant utility text for a question about
internet speed, pushing its fused score through the refusal gate.

Cross-encoder reranking recovered refusal accuracy to 1.000. The application
therefore rejects `hybrid_enabled=true` unless reranking is also enabled.

## Party-identity retrieval

Evaluation exposed that text before the first numbered heading could be lost,
which affected questions such as “Who is the landlord?” The chunker now
captures party tables and all-caps recital preambles. Regression coverage lives
in `test_chunker.py`.

## Answer quality

The following scores cover 19 answerable questions. Groq
`llama-3.3-70b-versatile` was used for generation and judging, with judge
temperature set to zero.

| Dimension | Score |
|---|---:|
| Faithfulness | 1.000 |
| Correctness | 0.947 |
| Relevance | 0.968 |
| **Overall** | **0.972** |

The same provider acting as generator and judge can introduce correlated bias;
these figures should be supplemented with human review before broader claims.
## Privacy audit

Five labeled fixtures cover regex-detectable values, free-text PII categories,
and a clean payload.

- Deterministic `redact_pii` caught all expected SSN and credit-card categories
  in this fixture set.
- The LLM auditor identified expected free-text categories such as names,
  addresses, email addresses, and phone numbers without echoing raw values in
  its prompt result.
- A real Groq quota failure exercised the fail-safe path: the auditor returned
  `has_pii=true` with `audit_unavailable` rather than reporting a false clean
  result.

The auditor is a detection layer. `core.security.redact_pii` is a
deterministic, best-effort safeguard applied before supported content enters
Chroma metadata, answer caches, or Langfuse traces. It covers configured
patterns, but residual PII may remain and the auditor does not redact or block
persistence itself.

## Configuration decisions

The default reranker is `cross-encoder/ms-marco-MiniLM-L-6-v2`. It improved
this baseline but was trained on web-search data rather than lease law, so
reranking remains disabled by default. The results are a baseline for future
legal-domain models—not an upper bound on their possible performance.

Out-of-scope behavior remains visible as a separate category because ranking
metrics alone cannot measure correct refusal. A future dedicated classifier
would require a larger labeled in-scope/out-of-scope dataset and a new
comparative evaluation.

## Result history

| Change | Observed impact |
|---|---|
| Golden dataset and metrics harness | Dense baseline: MRR 0.674, recall@k 0.783, refusal 0.913 |
| Cross-encoder reranking | MRR +0.130; refusal +0.087 |
| BM25 hybrid without reranking | MRR +0.033; refusal -0.087 |
| Hybrid with reranking | Refusal recovered to 1.000 |
| Structured output | Answer-shape change; no retrieval-metric effect |
| Runtime groundedness guard | Optional and off by default; when enabled, unsupported or unavailable judge results downgrade the answer to a refusal |
| Offline privacy audit | `audit_for_pii` runs in the evaluation harness, not the request path; it detects residual PII but does not redact or block persistence |
