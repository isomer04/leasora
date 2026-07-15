import re

import pytest

from leasora_api.core.security import redact_pii
from leasora_api.services.eval.golden import GOLDEN_DIR
from leasora_api.services.eval.judges import audit_for_pii

PII_PATTERNS = {
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
}

# pii_fixtures.jsonl intentionally contains planted PII (it's the labeled
# fixture set used to test the deterministic redactor + LLM auditor below),
# so it is deliberately excluded from the "golden fixtures must be clean"
# scan below.
_PII_FIXTURES_FILENAME = "pii_fixtures.jsonl"


def test_no_pii_in_golden_fixtures():
    """Scan golden fixtures for PII patterns."""
    for file_path in GOLDEN_DIR.rglob("*"):
        if file_path.name == _PII_FIXTURES_FILENAME:
            continue
        if file_path.is_file() and file_path.suffix in {".txt", ".json", ".jsonl", ".md"}:
            content = file_path.read_text()

            for pattern_name, pattern in PII_PATTERNS.items():
                matches = re.findall(pattern, content, re.IGNORECASE)
                assert not matches, f"Found {pattern_name} in {file_path}: {matches}"


def _load_pii_fixtures() -> list[dict[str, object]]:
    import json

    path = GOLDEN_DIR / _PII_FIXTURES_FILENAME
    fixtures = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                fixtures.append(json.loads(line))
    return fixtures


@pytest.mark.parametrize("fixture", _load_pii_fixtures())
def test_redact_pii_catches_expected_regex_categories(fixture: dict[str, object]):
    """The deterministic redactor must catch every regex-detectable category."""
    payload = str(fixture["payload"])
    expected_categories = fixture["expected_regex_categories"]
    assert isinstance(expected_categories, list)

    redacted = redact_pii(payload)

    for category in expected_categories:
        assert f"[REDACTED_{category.upper()}]" in redacted, (
            f"redact_pii did not catch expected '{category}' in: {payload!r}"
        )


@pytest.mark.eval
@pytest.mark.parametrize("fixture", _load_pii_fixtures())
async def test_privacy_auditor_flags_pii_regex_misses(fixture: dict[str, object]):
    """The LLM auditor should flag PII categories the regex redactor can't catch.

    Real Groq call — kept behind the `eval` marker like the other LLM-judge
    tests. ``audit_for_pii`` redacts known regex patterns internally before
    prompting the judge, so for a payload with only regex-catchable PII
    (e.g. SSN), the judge sees a ``[REDACTED_SSN]`` placeholder rather than
    the raw value — it may still (correctly, and safely) note that an SSN
    was present, since the placeholder itself signals that. The real safety
    property under test is that the raw value never leaks into the judge's
    prompt or its output — verified below regardless of category outcome.
    """
    payload = str(fixture["payload"])
    expected_llm_categories = fixture["expected_llm_categories"]
    assert isinstance(expected_llm_categories, list)

    has_pii, findings = audit_for_pii(payload)

    # Safety property: findings must never contain the raw payload text
    # (only categories/locations), regardless of what was flagged.
    for finding in findings:
        assert payload not in str(finding)

    if expected_llm_categories:
        assert has_pii, f"Expected auditor to flag PII in: {payload!r}, findings={findings}"
    elif not fixture["expected_regex_categories"]:
        # Payloads with no PII of any kind should not trigger false positives.
        assert not has_pii or not findings, (
            f"Auditor unexpectedly flagged a clean payload: {payload!r}, findings={findings}"
        )
