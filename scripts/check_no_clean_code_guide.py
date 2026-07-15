#!/usr/bin/env python3
"""CI lint: fail if ``docs/CLEAN_CODE_GUIDE.md`` reappears.

This file was deleted because its contents were stale (the stale sub-config 
example was already cleaned up) and the file no longer carried its weight. 
This guard prevents the file from sneaking back in via a copy-paste or 
external contribution.

Exit codes:
    0 — file does not exist (good)
    1 — file exists (bad; CI fails)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = REPO_ROOT / "docs" / "CLEAN_CODE_GUIDE.md"


def main() -> int:
    if FORBIDDEN.exists():
        print(
            f"[check_no_clean_code_guide] FAIL: {FORBIDDEN} exists. "
            "This file was explicitly deleted. If you believe it should "
            "be restored, open an ADR explaining the rationale.",
            file=sys.stderr,
        )
        return 1
    print("[check_no_clean_code_guide] OK: docs/CLEAN_CODE_GUIDE.md absent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())