# Pre-Commit Hooks

Leasora uses [pre-commit](https://pre-commit.com/) for fast local checks before
a commit is created. CI remains the source of truth; hooks provide earlier
feedback but do not replace the full test and build commands.

## Install

`pre-commit` is not included in `apps/api`'s development dependencies. Install
it as an isolated tool, then register the repository hook:

```bash
uv tool install pre-commit
pre-commit install
```

Alternatively, install it with your preferred Python package manager.

## Run manually

```bash
pre-commit run --all-files
```

The first run downloads pinned hook environments and may take longer.

## Configured checks

The root [`.pre-commit-config.yaml`](.pre-commit-config.yaml) currently runs:

- Ruff linting and formatting for Python
- mypy for applicable Python files
- Python AST, YAML, JSON, and TOML validation
- private-key, trailing-whitespace, and end-of-file checks
- Grimp architecture import contracts
- the repository's PII pattern scanner
- Prettier and ESLint for supported web/documentation files

## Normal workflow

1. Stage only the files intended for the commit.
2. Run `pre-commit run --all-files` when making broad changes.
3. Commit normally and let hooks inspect the staged content.
4. Review and restage any automatic fixes before retrying the commit.

```bash
git add README.md docs/ARCHITECTURE.md
pre-commit run --all-files
git commit -m "docs: improve project documentation"
```
## Troubleshooting

### Command not found

Confirm that the tool's install directory is on `PATH`, then run:

```bash
pre-commit --version
```

### A hook modifies files

Inspect the diff, stage the intentional fixes, and rerun the hooks. Do not use
`git add .` when unrelated work is present.

### A hook reports a false positive

Do not weaken repository configuration or skip verification silently. Capture
the exact output, confirm that no secret or real PII is present, and fix the
scanner or configuration in a reviewable change when appropriate.

Bypassing hooks with `--no-verify` removes a safety layer and should be reserved
for an explicitly reviewed emergency; CI checks still apply.
