# Local Development Setup

This guide offers two independent ways to run Leasora. Use the **host workflow**
for active development or the **Compose workflow** for a containerized stack.
Do not run both at once because each binds ports 3000 and 8000.

## Prerequisites

| Tool | Supported version | Purpose |
|---|---|---|
| Python | 3.12+ | API runtime |
| [`uv`](https://docs.astral.sh/uv/getting-started/installation/) | Current | Python environments and packages |
| Node.js | 18+ | Web runtime |
| [`pnpm`](https://pnpm.io/installation) | 9.x | Workspace package manager |
| Docker | Current | Compose workflow and optional observability |

## Option A: run from source

### 1. Install dependencies

From the repository root:

```bash
pnpm install
cd apps/api
uv venv
uv pip install -e ".[dev]"
cd ../..
```

Activating the Python environment is optional when commands use `uv run`.
If needed, run `source apps/api/.venv/bin/activate` on POSIX or
`apps\api\.venv\Scripts\Activate.ps1` in PowerShell.

### 2. Configure the API

The API reads `apps/api/.env` by default:

```bash
# POSIX
cp .env.example apps/api/.env

# PowerShell
Copy-Item .env.example apps/api/.env
```
`LEASORA_GROQ_API_KEY` may remain empty for ingestion and retrieval-only
operations. Set it before using live answers, comparisons, metadata extraction,
or LLM-based evaluation. Uploaded leases default to a 30-day retention period;
the API sweeps at startup and every 24 hours. Review `.env.example` for
retrieval, retention, security, and observability settings.

### 3. Start the applications

```bash
pnpm dev
```

Turborepo starts FastAPI and Next.js. Open:

| Service | URL |
|---|---|
| Web app | <http://localhost:3000> |
| Swagger UI | <http://localhost:8000/docs> |
| ReDoc | <http://localhost:8000/redoc> |
| Health check | <http://localhost:8000/health> |

The embedding model may be downloaded on first use. Live generation sends the
question and selected lease context to Groq; ingestion and retrieval remain
local.

## Option B: run with Docker Compose

From the repository root:

```bash
docker compose -f services/compose/docker-compose.yml up --build
```

The default profile starts:

- Next.js at <http://localhost:3000>
- FastAPI at <http://localhost:8000>

Chroma runs as an embedded persistent client inside the API container and
stores its files under the shared `data/` mount; it does not expose a separate
HTTP port.

Stop it with:

```bash
docker compose -f services/compose/docker-compose.yml down
```

Do not also run `pnpm dev`; the host and container workflows use the same web
and API ports.
## Optional self-hosted observability

Langfuse v3 is not part of the default profile. Before starting the
`observability` profile, define:

- `LANGFUSE_SALT`
- `LANGFUSE_ENCRYPTION_KEY` (64 hexadecimal characters)
- `LANGFUSE_NEXTAUTH_SECRET`

Then run:

```bash
docker compose -f services/compose/docker-compose.yml \
  --profile observability up --build
```

Open <http://localhost:3001>, create a project, and copy its public and secret
keys into the API configuration. Starting the containers alone does not enable
application tracing; set all `LEASORA_LANGFUSE_*` values described in
[ADR 005](adr/005-langfuse-self-host-default.md).

## Common commands

```bash
pnpm lint
pnpm type-check
pnpm build
pnpm --filter @leasora/web test:run
uv run --project apps/api pytest apps/api/tests
uv run --project apps/api ruff check apps/api
uv run --project apps/api mypy apps/api/src
pnpm gen:types
```

Tests marked `eval` can make billed Groq calls. Run them deliberately.

## Troubleshooting

### Port 3000 or 8000 is already in use

Stop the other host or Compose workflow. Check active containers with
`docker compose -f services/compose/docker-compose.yml ps`.

### The API cannot import `leasora_api`

Reinstall the editable package with `uv pip install -e ".[dev]"` from
`apps/api`, or run Python commands with `uv run --project apps/api`.
