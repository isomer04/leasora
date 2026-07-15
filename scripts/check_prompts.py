#!/usr/bin/env python3
r"""CI check: no fenced JSON examples in prompt templates.

Walks ``apps/api/src/leasora_api/services/llm/prompts/*.md`` and fails with
a non-zero exit code if any of them wraps a JSON example in a markdown
code fence (```json ... ```). The convention is bare inline JSON,
because fenced examples have historically caused the model to *echo the
fence* and then fail structured-output validators.

Run from repo root:
    python scripts/check_prompts.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "apps" / "api" / "src" / "leasora_api" / "services" / "llm" / "prompts"

# Any markdown code fence whose opening is ``` or ```json (with optional
# language tag). Captures: ```<lang?> ... ```
_FENCE_PATTERN = re.compile(r"^\s*```(?:json)?\s*$", re.MULTILINE)


def _check_file(path: Path) -> list[str]:
    """Return a list of human-readable violations for ``path``."""
    text = path.read_text(encoding="utf-8")
    if not _FENCE_PATTERN.search(text):
        return []
    return [
        f"{path.relative_to(REPO_ROOT)}: contains a fenced JSON example. "
        "Use bare inline JSON per apps/api/src/leasora_api/services/llm/prompts/README.md"
    ]


def main() -> int:
    if not PROMPTS_DIR.is_dir():
        print(f"WARN: prompts dir not found at {PROMPTS_DIR}", file=sys.stderr)
        return 0

    violations: list[str] = []
    files = sorted(PROMPTS_DIR.glob("*.md"))
    for path in files:
        violations.extend(_check_file(path))

    if violations:
        print("Prompt convention check FAILED:", file=sys.stderr)
        for line in violations:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"OK: no fenced JSON examples in {len(files)} prompt template(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
