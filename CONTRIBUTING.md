# Contributing to Leasora

Thank you for improving Leasora. Keep changes focused, explain user-visible
tradeoffs, and treat lease content as sensitive data.

## Development setup

Follow [docs/setup.md](docs/setup.md) and choose one runtime workflow:

- **Host development:** install pnpm and Python dependencies, create
  `apps/api/.env`, then run `pnpm dev`.
- **Containers:** run the Compose stack instead of `pnpm dev` to avoid port
  conflicts.

Install Git hooks separately because `pre-commit` is not part of the API's
Python development extra:

```bash
uv tool install pre-commit
pre-commit install
```

See [PRE_COMMIT_SETUP.md](PRE_COMMIT_SETUP.md) for hook details.

## Workflow

```bash
git switch -c feature/short-description
# Make and verify a focused change.
git add path/to/changed-file
git commit -m "feat(scope): describe the outcome"
```

Use `feature/`, `fix/`, `docs/`, `chore/`, or `refactor/` branch prefixes.
Commit messages follow Conventional Commits: `feat`, `fix`, `refactor`,
`test`, `docs`, `chore`, or `perf`.

## Verification

Run checks relevant to your change. From the repository root:

```bash
pnpm lint
pnpm type-check
pnpm test
pnpm build
```

For a non-watching frontend test run, use:

```bash
pnpm --filter @leasora/web test:run
```
Backend-specific checks:

```bash
uv run --project apps/api pytest apps/api/tests
uv run --project apps/api ruff check apps/api
uv run --project apps/api mypy apps/api/src
uv run --with grimp --with pyyaml python scripts/check_imports.py
```

Tests marked `eval` can call Groq and may incur cost. Run them only when the
change affects evaluation or LLM behavior and credentials are configured.

## Architecture and API contracts

- Preserve the dependency rules in
  [docs/architecture/layers.md](docs/architecture/layers.md).
- Record significant, durable design changes in an ADR.
- After changing a FastAPI route or schema, run `pnpm gen:types`, inspect
  `packages/shared-types/src/api.ts`, and include the generated update.
- Do not hand-edit generated API types.

## Security and privacy

Never commit real lease documents, credentials, or personally identifying
information. New persistence or external-service flows must redact supported
PII before storage or transmission and must remain opt-in when they cross a new
external boundary.

## Pull requests

Use the repository template. Summarize the outcome, link any issue or ADR,
list verification commands and results, and call out privacy, schema, or
architecture impact. Keep the branch free of process-only commits before merge.
