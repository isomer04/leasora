#!/usr/bin/env python
"""Enforce architectural import contracts for the FastAPI backend.

Reads the contracts declared in ``grimp.yml`` and verifies that no module in a
forbidden ``source`` layer imports a module in the corresponding ``target``
layer. Dependencies must point inward: http -> services -> core.

Usage (from repo root):
    uv run --with grimp --with pyyaml python scripts/check_imports.py

Exit code 0 = all contracts satisfied, 1 = one or more violations found.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import grimp
    import yaml
except ImportError as exc:  # pragma: no cover - dependency guard
    sys.stderr.write(
        f"Missing dependency: {exc.name}. Run with:\n"
        "    uv run --with grimp --with pyyaml python scripts/check_imports.py\n"
    )
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "grimp.yml"


def _modules_in(graph: Any, package: str) -> set[str]:
    """Return the package itself plus all of its descendant modules."""
    descendants: set[str] = set(graph.find_descendants(package))
    return {package} | descendants


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    root_package: str = config.get("package", "leasora_api")
    forbidden = config.get("forbidden_imports", [])

    graph = grimp.build_graph(root_package)

    violations: list[str] = []
    for rule in forbidden:
        source = f"{root_package}.{rule['source']}"
        target = f"{root_package}.{rule['target']}"
        message = rule.get("error", f"{source} must not import {target}")

        for importer in _modules_in(graph, source):
            for imported in graph.find_modules_directly_imported_by(importer):
                if imported == target or imported.startswith(f"{target}."):
                    violations.append(
                        f"  {importer}  ->  {imported}\n"
                        f"      {message}"
                    )

    if violations:
        sys.stderr.write("Import contract violations found:\n")
        sys.stderr.write("\n".join(violations) + "\n")
        return 1

    print(f"Import contracts satisfied for '{root_package}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
