"""PII detection and redaction utilities.

The single source of truth for regex-catchable PII patterns used by:

- ``redact_pii`` — regex-driven redaction of free-form text.
- ``redact_dict`` — structural walk over mappings/lists/tuples/sets/pydantic
  models that recursively scrubs string values.

Coverage:

- SSN, credit card, email, phone, street address — caught anywhere they
  appear.
- Account number — anchored on an explicit label
  (``Account #`` / ``A/C`` / ``Routing`` / ``ABA:`` / ``ACH:`` / ``Bank
  account:``). The previous version's ``[A-Z]{2}\\d{8,12}`` prefix missed
  hyphenated US bank-account formats (e.g. ``A/C 1234-5678-9012``) and
  false-positived on orders like ``AB12345678``.
- Date of birth — requires an explicit DOB/Birth label OR a year-only
  ``Born \\d{4}`` form. Bare dates (e.g. an effective-date ``03/14/2025``
  on a lease) are NOT redacted.
- Person name — Unicode-aware, allows ``[\\p{L}\\p{M}'-]``, honours
  ``, Jr.|Sr.|II|III|IV`` suffixes without consuming trailing sentence
  punctuation. Anchored to a landlord/tenant/lessor/lessee role label so
  a bare ``Jane Smith`` in prose is NOT redacted (callers that need that
  should route through ``services.eval.judges.audit_for_pii`` as a
  detection layer, not rely on this regex alone).

Patterns are compiled with ``re.IGNORECASE | re.UNICODE`` so they work
correctly on accented / mixed-case text. Where a portion of a pattern
needs strict ASCII digit matching (account-number digits, SSN, credit
card), the pattern includes its own character class rather than relying
on case toggling.

Fail-closed contract: ``redact_pii`` is best-effort. A residual
may-contain-PII risk remains (see the detector + UI-badge path in
``services.rag.query_service`` that surfaces unredacted residue rather
than shipping it silently to the LLM).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import regex as _re
from regex import Pattern


# Pattern catalog.

# Each pattern is a Python regex string. ``redact_pii`` compiles and applies
# them in catalog order with re.IGNORECASE | re.UNICODE. Patterns are largely
# disjoint on realistic lease text; catalog order is therefore not significant.

PII_PATTERNS: dict[str, str] = {
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    # Account number
    "account_number": (
        r"(?:Account\s*#|\bA/?C\b|Routing(?:\s+Number)?:|ABA(?:\s+Routing)?:"
        r"|ACH(?:\s+Account)?:|Bank\s+Account:)"
        r"(?:\s+No\.?)?"
        r"[\s\-]*"
        r"[0-9](?:[0-9\-\s]{6,18}[0-9])"
        # IBAN/SWIFT/BIC — letter-bearing, so a separate alternative with
        # an alphanumeric body (the numeric-only branch above can never
        # match these).
        r"|\b(?:IBAN|SWIFT|BIC)\b:?\s*[A-Za-z0-9]{4,34}\b"
    ),
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "street_address": (
        r"\b\d{1,6}\s+[A-Za-z0-9]"
        r"(?:[A-Za-z0-9.\s]{0,30})?\s"
        r"(?:Street|St\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Drive|Dr\.?|"
        r"Lane|Ln\.?|Road|Rd\.?|Court|Ct\.?|Place|Pl\.?|Way|Circle|Cir\.?|"
        r"Terrace|Ter\.?)\b"
    ),
    # Date of birth
    "date_of_birth": (
        r"(?:DOB|D\.O\.B\.?|Date\s+of\s+Birth|Birthday)"
        r"\s*(?:[:\-]|is)?\s*"
        r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
        r"|\d{4}-\d{1,2}-\d{1,2}"
        r"|(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"\s+\d{1,2},?\s+\d{2,4}"
        r"|\d{1,2}\s+(?:January|February|March|April|May|June|July|"
        r"August|September|October|November|December)\s+\d{2,4})"
        # OR year-only "Born YYYY".
        r"|Born\s+\d{4}\b"
    ),
    # Person name
    "person_name": (
        # Role label (case-insensitive).
        r"(?i:(?:landlord|tenant|lessor|lessee|owner|renter|landlady|"
        r"landlord's? representative|tenant's? representative|co-tenant|"
        r"co-landlord|agent))"
        r"\s*[:\-]\s*"
        # First letter must be Unicode-letter (any script, no leading digit).
        r"[\p{L}][\p{L}\p{M}'\-]+"
        r"(?:\s+[\p{L}][\p{L}\p{M}'\-]+){0,3}"
        # Optional suffix: accepts both ", Jr./Sr./II/III/IV" with comma
        # (formal style) and bare "Jr./Sr./II/III/IV" (colloquial) — the
        # trailing lookahead ensures we don't eat sentence-ending
        # punctuation outside the suffix itself.
        r"(?:,\s*(?:Jr|Sr)\.?|\s(?:Jr|Sr)\.?|,\s*(?:II|III|IV)|\s(?:II|III|IV))?"
        r"(?=[\s,;.!?:\"'()\[\]]|$)"
    ),
}


def _compile_patterns() -> dict[str, Pattern[str]]:
    """Compile the pattern catalog once at import time.

    ``regex`` is a declared runtime dependency and supports the
    ``\\p{L}`` / ``\\p{M}`` Unicode-property escapes used for
    accent-insensitive name matching.
    """
    return {
        name: _re.compile(pattern, _re.IGNORECASE | _re.UNICODE)
        for name, pattern in PII_PATTERNS.items()
    }


# Compiled-pattern cache so redaction is fast on hot paths.
_COMPILED_PATTERNS: dict[str, Pattern[str]] = _compile_patterns()


# A small set of role labels duplicated for callers that want to label-anchor
# their own detection logic on the same vocabulary (e.g. ``audit_for_pii``
# in ``services.eval.judges``). Kept in sync with the ``person_name`` role
# alternation above.
PERSON_NAME_ROLE_LABELS: tuple[str, ...] = (
    "landlord",
    "tenant",
    "lessor",
    "lessee",
    "owner",
    "renter",
    "landlady",
    "landlord's representative",
    "tenant's representative",
    "co-tenant",
    "co-landlord",
    "agent",
)


# Redaction pipeline.


def redact_pii(text: str) -> str:
    """Redact regex-catchable PII patterns from text.

    Covers SSN, credit card, account number, email, phone, street address,
    date of birth, and personal names that appear in a lease's parties
    block (e.g. ``Landlord: Jane Smith``). Does NOT catch bare names elsewhere
    in prose — see the ``person_name`` pattern note for the rationale. Callers
    that need full name coverage should also route the payload through
    ``services.eval.judges.audit_for_pii`` as a detection layer, not rely
    on this function alone.

    Patterns are compiled with ``re.IGNORECASE | re.UNICODE`` so accented
    letters, mixed-case surnames, and hyphenated names are matched correctly.
    """
    for pattern_name, compiled in _COMPILED_PATTERNS.items():
        text = compiled.sub(f"[REDACTED_{pattern_name.upper()}]", text)
    return text


# Structural walk (replaces the previous isinstance ladder that silently
# bypassed tuples / sets / pydantic models).


def _redact_string(value: str) -> str:
    return redact_pii(value)


def _redact_mapping(value: Mapping[Any, Any]) -> dict[Any, Any]:
    return {key: _redact_value(item) for key, item in value.items()}


def _redact_iterable(value: Iterable[Any]) -> list[Any]:
    return [_redact_value(item) for item in value]


def _redact_value(value: Any) -> Any:
    """Recursively redact PII from any value type.

    Replaces the prior isinstance ladder that silently bypassed tuples,
    sets, frozensets, and pydantic models (``redact_dict({"a":
    ("SSN 123-45-6789",)}`` previously returned the tuple unchanged).

    Order:
    1. ``None`` → returned as-is.
    2. ``str`` → ``redact_pii``.
    3. ``Mapping`` → structural walk over items.
    4. ``list`` / ``tuple`` / ``set`` / ``frozenset`` → converted to a
       ``list`` of redacted children (order preserved for ``list``/
       ``tuple``; ``set``/``frozenset`` order is implementation-defined).
    5. Pydantic v2 ``BaseModel`` (if available) → ``model_dump()`` round-trip.
    6. Anything else → string-cast and redacted, so a custom object that
       happens to override ``__str__`` with a PII-rich representation still
       gets scrubbed instead of being silently dropped.
    """
    if value is None:
        return value
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return _redact_iterable(value)
    # Pydantic v2: `model_dump()` produces a plain Python structure we can
    # then redact. Avoid hard dependency — try/except is fine here.
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _redact_value(model_dump())
        except Exception:
            # Pydantic model in a bad state — fall through to string cast.
            pass
    # Final fallback: stringify then redact. This does NOT preserve type —
    # e.g. ``5`` becomes ``"5"`` and ``True`` becomes ``"True"`` — but cheap
    # scalars (``int``, ``float``, ``bool``) contain no PII, so the string
    # form is a faithful (if now-``str``) representation of the value.
    return _redact_string(str(value))


def redact_dict(data: Mapping[Any, Any]) -> dict[Any, Any]:
    """Recursively redact PII from a Mapping's values.

    Replaces the previous ``isinstance(value, dict)`` recursion that
    silently dropped tuples/sets/custom objects. See ``_redact_value`` for
    the full type-coverage contract.
    """
    return _redact_mapping(data)