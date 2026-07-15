"""RAG safety utilities: prompt-injection sanitization for retrieved chunks.

The regex patterns below catch *common* injection phrases observed in the
wild (e.g. "ignore the above", "forget everything"). They are NOT a
comprehensive defense against all prompt-injection techniques — adversaries
can bypass them via encoding tricks, unicode substitution, non-English
instructions, or novel phrasings.

The primary injection defense is the LLM prompt itself: the system prompt
instructs the model to answer from context only and ignore instructions
embedded in document text. This sanitizer is a defense-in-depth layer that
cheaply strips the most common patterns before the chunk ever reaches the
prompt. It should never be treated as the sole injection barrier.

The behavior is gated on ``settings.prompt_injection_defense_enabled`` so
operators can opt out (e.g. for a known-clean internal corpus), but the
default is ON. Calling :func:`sanitize_chunk` honors that flag and is a
no-op (modulo truncation) when the flag is False — callers don't need to
check the flag themselves, so a forgotten ``if`` check can't accidentally
ship un-sanitized chunks to the LLM.
"""

from __future__ import annotations

import logging
import re

from leasora_api.core.config import get_settings

logger = logging.getLogger(__name__)


INJECTION_PATTERNS = [
    r"ignore\s+the\s+above",
    r"ignore\s+all\s+previous",
    r"system\s*:",
    r"user\s*:",
    r"forget\s+everything",
    r"disregard\s+all",
]


def sanitize_chunk(chunk: str, max_length: int = 2000) -> str:
    """Remove injection patterns and truncate.

    Honors ``settings.prompt_injection_defense_enabled``. When that flag is
    False, ``sanitize_chunk`` does NOT scrub the patterns (it only enforces
    the ``max_length`` truncation cap, which is a separate concern). When
    the flag is True (the default), the chunk is scrubbed of the regex
    patterns in ``INJECTION_PATTERNS`` and then truncated.

    Args:
        chunk: The text to sanitize (a single retrieved chunk or LLM
            prompt fragment).
        max_length: Soft cap on the returned string length. Truncation
            happens AFTER injection scrubbing so the scrubber has full
            context to operate on.

    Returns:
        The (possibly) scrubbed, truncated string.
    """
    try:
        enabled = get_settings().prompt_injection_defense_enabled
    except Exception:
        # Settings may be uninitialized in early test contexts — fail
        # closed (defense on) so a misconfigured runtime can't accidentally
        # ship raw chunks.
        enabled = True

    if enabled:
        for pattern in INJECTION_PATTERNS:
            chunk = re.sub(pattern, "", chunk, flags=re.IGNORECASE | re.MULTILINE)
    else:
        # Defensive logging when defense is disabled but the chunk LOOKS
        # like an injection — operator can decide whether to re-enable.
        if any(
            re.search(p, chunk, flags=re.IGNORECASE | re.MULTILINE)
            for p in INJECTION_PATTERNS
        ):
            logger.warning(
                "prompt_injection_defense_enabled=False but chunk appears to "
                "contain an injection pattern; passing through unmodified."
            )

    # Truncation always applies so callers can rely on the size cap even
    # when defense is off.
    if len(chunk) > max_length:
        chunk = chunk[:max_length]

    return chunk.strip()