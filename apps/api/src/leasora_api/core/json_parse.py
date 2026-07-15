"""Shared JSON-parsing helpers for LLM responses.

LLMs asked to return JSON sometimes still wrap their output in a
triple-backtick + ``json`` code fence (especially under "respond with ONLY"
prompts that some models hedge on). This module centralizes the
"try-parse-literal, fall back to stripping fences" pattern so every
call site stops re-implementing slightly-incompatible versions of it.

Extracted from three near-duplicated call sites: GroqClient.complete_structured, 
judges._parse_json_with_fallback, and the eval runner's privacy-audit path.
"""

from __future__ import annotations

import json
import re
from typing import cast


# Fence we expect to strip: starts with ```json or plain ``` and ends with
# the matching closing triple-backtick. The regex is case-insensitive and
# lets a leading/trailing whitespace pass through unmodified.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)


def strip_code_fence(s: str) -> str:
    r"""Strip a surrounding ``json ... ``` (or plain ``` ... ```) fence.

    Lowercases the opening tag for matching so ``JSON`` is treated
    identically to ``json``. Leaves the body untouched otherwise.

    Args:
        s: Raw LLM response text that may or may not be fence-wrapped.

    Returns:
        The (possibly) stripped string. If ``s`` doesn't look fence-wrapped,
        it is returned verbatim (modulo an outer ``.strip()`` for trailing
        newlines).
    """
    match = _FENCE_RE.match(s.strip())
    if match:
        return match.group(1).strip()
    return s.strip()


def parse_json_lenient(s: str) -> object | None:
    r"""Parse a JSON value with code-fence fallback.

    Tries ``json.loads(s)`` first; on ``JSONDecodeError`` strips a single
    surrounding ```json / ``` fence and retries. Returns ``None`` on a
    second failure so the caller can decide how to log/handle.

    Args:
        s: Raw LLM response text (potentially fence-wrapped).

    Returns:
        The parsed object (list, dict, scalar) on success, else ``None``.
        Use ``isinstance(parsed, dict)`` at the call site if a dict is
        required — non-dict top-level values are valid JSON but mean the
        LLM didn't honor the prompt's "JSON object" instruction.
    """
    try:
        return cast(object, json.loads(s))
    except json.JSONDecodeError:
        pass
    stripped = strip_code_fence(s)
    try:
        return cast(object, json.loads(stripped))
    except json.JSONDecodeError:
        return None
