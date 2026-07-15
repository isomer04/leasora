# Leasora

**A source-grounded California lease explainer for renters.**

[▶ Watch the Leasora demo](https://kommodo.ai/recordings/izaQ8XKbnajfkSQoYuLT?onlyRecording=1)

Leasora turns lease PDFs into answers you can verify. Upload a lease, ask a
plain-language question, and receive an answer with page citations, verbatim
quotes, and clause signals such as `tenant_friendly`, `unusual`, or `red_flag`.

> [!IMPORTANT]
> Leasora is an educational summarization tool, not legal advice. Verify
> important decisions with a qualified attorney or local housing authority.

## Highlights

- **Evidence-first answers:** every supported answer links back to retrieved
  lease text and page numbers.
- **Deterministic refusal:** weak retrieval results are rejected before an LLM
  is called instead of being turned into a guess.
- **Lease workspace:** upload, list, inspect, compare, refresh metadata for,
  and delete leases and their derived artifacts.
- **Measured quality:** a reproducible golden dataset tracks MRR, recall,
  refusal accuracy, faithfulness, correctness, and relevance.
- **Privacy controls:** deterministic PII redaction, local persistence,
  cascade deletion, prompt-injection defenses, and opt-in observability.
- **Typed full stack:** FastAPI OpenAPI schemas generate the TypeScript types
  consumed by the Next.js client.

## Quick start

### Prerequisites

- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js 18+ and pnpm 9.x (`package.json` pins pnpm 9.15.0)
- A Groq API key only for live answers, comparisons, and LLM-based evaluation

### Run from source

```bash
pnpm install
cd apps/api
uv venv
uv pip install -e ".[dev]"
cd ../..
```
Create the API environment file, then start both applications:

```bash
# POSIX
cp .env.example apps/api/.env

# PowerShell
Copy-Item .env.example apps/api/.env

pnpm dev
```

Open the web app at <http://localhost:3000>. API documentation is available at
<http://localhost:8000/docs> and <http://localhost:8000/redoc>.

For a containerized alternative, run:

```bash
docker compose -f services/compose/docker-compose.yml up --build
```

The Compose command starts the web app and API. Chroma runs embedded in the
API process and persists under the shared `data/` mount. Compose is an
alternative to `pnpm dev`, not a prerequisite. See the [complete setup guide](docs/setup.md)
for platform notes, optional Langfuse services, and troubleshooting.

## How it works

1. `pdfplumber` extracts text page by page; scanned PDFs are rejected because
   OCR is not implemented.
2. A clause-aware splitter creates chunks, and sentence-transformers produces
   local embeddings stored per lease in Chroma.
3. Dense retrieval finds candidate clauses. Optional BM25 fusion and a
   cross-encoder can refine ranking.
4. A distance gate refuses weak evidence before generation.
5. Groq produces a structured answer from the selected clauses; Pydantic
   validates it and an optional groundedness judge can reject unsupported text.
6. Exact and semantic caches are lease-scoped and invalidated on re-ingestion.

See the [architecture diagrams](docs/ARCHITECTURE.md) and
[layer dependency rules](docs/architecture/layers.md).

## Evaluation

Results on the current 23-question synthetic golden set:

| Retrieval configuration | MRR | Refusal accuracy |
|---|---:|---:|
| Dense baseline | 0.674 | 0.913 |
| Cross-encoder reranked | **0.804** | **1.000** |
| Hybrid without reranking | 0.707 | 0.826 |
| Hybrid with reranking | **0.804** | **1.000** |

The reranked configuration also measured faithfulness **1.000**, correctness
**0.947**, and relevance **0.968** using real Groq calls. These figures are a
small baseline, not a production guarantee. See the
[full evaluation report](docs/EVALUATION_REPORT.md) for methodology, category
results, limitations, and reproduction commands.

## Privacy and security

- Uploaded PDFs, chunks, metadata, and caches are stored locally by default.
- Supported PII patterns are redacted before Chroma metadata, answer-cache,
  and Langfuse trace persistence. The LLM privacy auditor is an additional
  detector, not the guarantee.
- **Live answers and comparisons send the question and selected, redacted
  context to Groq.** Do not treat LLM-backed operations as fully offline.
- Langfuse is disabled unless its enable flag, host, public key, and secret key
  are all configured. The self-hosted stack is an optional Compose profile.
- Leasora has no user authentication or tenant isolation. Do not expose this
  version directly to the public internet.

See [ADR 005](docs/adr/005-langfuse-self-host-default.md) and
[ADR 006](docs/adr/006-no-user-auth-single-tenant-v1.md).

## Technology

| Area | Main components |
|---|---|
| API | FastAPI, Pydantic v2, pdfplumber, sentence-transformers, ChromaDB, Groq |
| Web | Next.js 16, React 19, strict TypeScript, Tailwind CSS, Radix UI |
| Quality | pytest, Vitest, Ruff, mypy, ESLint, Prettier, Grimp |
| Platform | pnpm workspaces, Turborepo, uv, Docker Compose, OpenAPI |

## Known limitations

- Scanned and image-only PDFs are unsupported because there is no OCR.
- Live-generated answers require Groq and transmit selected context externally.
- The current evaluation uses one synthetic lease and 23 questions.
- The shipped reranker was trained on web-search data, not legal text, and is
  disabled by default.
- The application is single-process, local-first, unauthenticated, and not
  ready for public multi-tenant deployment.
## Documentation

- [Setup](docs/setup.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Documentation index](docs/INDEX.md)
- [Evaluation report](docs/EVALUATION_REPORT.md)
- [Architecture decisions](docs/adr/)
- [Release notes](RELEASE_NOTES.md)

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. It covers
branch conventions, verification, architecture boundaries, generated types,
and privacy expectations.

## License

This repository currently does **not** include an open-source license file.
Unless and until one is added, no permission to copy, modify, or distribute the
code is granted by default. The legal-advice disclaimer above describes product
scope; it is not a software license.
