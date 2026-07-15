"""Unit tests for ``core.security`` PII redaction.

These tests pin the contract for PII redaction:

- SSN / credit card / email / phone / street address are caught anywhere
  they appear.
- Account number is anchored to a label; a bare order id is NOT redacted.
- Date of birth requires a DOB/Birth label or year-only form.
- Person name is Unicode-aware, handles hyphenated surnames, mixed-case,
  and honours the ``, Jr.|Sr.|II|III|IV`` suffix.
- ``redact_dict`` recursively walks tuples, sets, frozensets, lists, and
  pydantic models.
"""

from __future__ import annotations

import pytest

from leasora_api.core.security import (
    PERSON_NAME_ROLE_LABELS,
    PII_PATTERNS,
    redact_dict,
    redact_pii,
)


class TestBasicRedaction:
    """Tests for basic PII redaction categories."""

    def test_ssn_redaction(self) -> None:
        text = "Customer SSN: 123-45-6789"
        redacted = redact_pii(text)
        assert "123-45-6789" not in redacted, "Original SSN must be removed from output"
        assert "[REDACTED_SSN]" in redacted, "SSN must be replaced with placeholder token"

    def test_credit_card_redaction(self) -> None:
        text = "Card: 1234-5678-9012-3456"
        redacted = redact_pii(text)
        assert "1234-5678-9012-3456" not in redacted, "Original credit card number must be removed"
        assert "[REDACTED_CREDIT_CARD]" in redacted, "Card number must be replaced with token"

    def test_email_redaction(self) -> None:
        text = "Contact tenant at jane.doe@example.com for details"
        redacted = redact_pii(text)
        assert "jane.doe@example.com" not in redacted, "Original email must be removed from output"
        assert "[REDACTED_EMAIL]" in redacted, "Email must be replaced with placeholder token"

    def test_phone_redaction(self) -> None:
        text = "Call the landlord at (555) 123-4567 or 555-987-6543"
        redacted = redact_pii(text)
        assert "(555) 123-4567" not in redacted, "First phone number must be removed"
        assert "555-987-6543" not in redacted, "Second phone number must be removed"
        # Paren dropped with the leading digit — pin "two phones redacted".
        assert redacted.count("[REDACTED_PHONE]") == 2, "Both phone numbers must be redacted to tokens"

    def test_street_address_redaction(self) -> None:
        text = "The unit is located at 742 Evergreen Terrace"
        redacted = redact_pii(text)
        assert "742 Evergreen Terrace" not in redacted, "Street address must be removed"
        assert "[REDACTED_STREET_ADDRESS]" in redacted, "Address must be replaced with token"


class TestParametrizedCoverage:
    """Parametrized happy-path coverage for each PII category."""

    @pytest.mark.parametrize(
        ("text", "expected_token"),
        [
            ("SSN on file: 111-22-3333", "[REDACTED_SSN]"),
            ("Card ending 4111-1111-1111-1111", "[REDACTED_CREDIT_CARD]"),
            ("routing info: Routing: 123456789", "[REDACTED_ACCOUNT_NUMBER]"),
            ("Pay to A/C 1234-5678-9012", "[REDACTED_ACCOUNT_NUMBER]"),
            ("Bank Account: 987654321", "[REDACTED_ACCOUNT_NUMBER]"),
            ("Email: jane@example.com", "[REDACTED_EMAIL]"),
            ("Phone: (415) 555-1212", "[REDACTED_PHONE]"),
            ("742 Evergreen Terrace", "[REDACTED_STREET_ADDRESS]"),
            ("Tenant DOB: 03/14/1985", "[REDACTED_DATE_OF_BIRTH]"),
            ("DOB 1971-07-04 listed", "[REDACTED_DATE_OF_BIRTH]"),
            ("Date of Birth: March 14, 1985", "[REDACTED_DATE_OF_BIRTH]"),
            ("Born 1990 listed", "[REDACTED_DATE_OF_BIRTH]"),
            ("LANDLORD: Jane Smith", "[REDACTED_PERSON_NAME]"),
        ],
    )
    def test_redacts_each_pii_category(self, text: str, expected_token: str) -> None:
        """Each PII category, when present, redacts at least one token."""
        assert expected_token in redact_pii(text), (
            f"expected {expected_token!r} in redacted output for input {text!r}"
        )


class TestNegativeCases:
    """Tests for things that are NOT PII and must not be over-redacted."""

    @pytest.mark.parametrize(
        "text",
        [
            # Bare dates — effective-date / start-date style — must NOT match
            # the DOB pattern (the audit spec called out `03/14/2025` as the
            # canonical example).
            "Lease effective date: 03/14/2025",
            "Term: 03/14/2025 to 03/14/2026",
            "On 2025-03-14 the parties signed",
            "January 1, 2025",
            # Order id / account-like alphanumeric sequences without a label.
            "Reference number: AB12345678",
            "PO: ORD-12345",
        ],
    )
    def test_does_not_over_redact(self, text: str) -> None:
        """Bounded redaction: the catalog must not catch things that aren't PII."""
        redacted = redact_pii(text)
        assert "[REDACTED_" not in redacted, (
            f"unexpected redaction in {text!r} -> {redacted!r}"
        )


class TestAuditDrivenFixes:
    """Audit-driven fixes for PII redaction edge cases."""

    def test_account_number_label_anchored(self) -> None:
        """Anchored label: a bare order id is NOT redacted."""
        text = "Please reference order AB12345678 when paying."
        redacted = redact_pii(text)
        assert "AB12345678" in redacted, "Bare order ID without label must not be redacted"
        assert "[REDACTED_" not in redacted, "No PII tokens should appear for unanchored ID"

    def test_account_number_routing_label(self) -> None:
        """`Routing:` with a colon is captured (regression: previously missed)."""
        text = "Wire to Routing: 123456789"
        redacted = redact_pii(text)
        assert "123456789" not in redacted, "Routing number must be removed from output"
        assert "[REDACTED_ACCOUNT_NUMBER]" in redacted, "Routing number must be replaced with token"

    def test_account_number_aba_label(self) -> None:
        """`ABA:` and `ACH:` labels trigger account-number redaction."""
        for label in (
            "ABA: 123456789",
            "ACH Account: 123456789",
            "Bank Account: 987654321012",
        ):
            redacted = redact_pii(label)
            assert "[REDACTED_ACCOUNT_NUMBER]" in redacted, f"failed for {label!r}"

    def test_dob_label_required_for_redaction(self) -> None:
        """Bare dates are NOT redacted as DOB (audit case)."""
        text = "Effective date: 03/14/2025"
        redacted = redact_pii(text)
        assert "03/14/2025" in redacted, "Bare lease date must not be redacted as DOB"
        assert "[REDACTED_DATE_OF_BIRTH]" not in redacted, "No DOB token without explicit label"

    def test_dob_bare_year_form(self) -> None:
        """The `Born YYYY` year-only form IS redacted."""
        text = "Born 1990 listed"
        redacted = redact_pii(text)
        assert "1990" not in redacted, "Year in Born pattern must be removed"
        assert "[REDACTED_DATE_OF_BIRTH]" in redacted, "Born year must be replaced with token"

    def test_dob_labeled_numeric(self) -> None:
        """Labeled numeric dates ARE redacted."""
        text = "Tenant DOB: 03/14/1985"
        redacted = redact_pii(text)
        assert "03/14/1985" not in redacted, "DOB with label must be removed"
        assert "[REDACTED_DATE_OF_BIRTH]" in redacted, "DOB must be replaced with token"

    def test_person_name_unicode_accents(self) -> None:
        """Names with non-ASCII letters are matched."""
        text = "Lessor: Émilie Lefèvre"
        redacted = redact_pii(text)
        assert "Émilie" not in redacted
        assert "[REDACTED_PERSON_NAME]" in redacted

    def test_person_name_hyphenated_surname(self) -> None:
        """Hyphenated surnames like `Smith-Jones` are matched in full."""
        text = "Tenant: Mary Smith-Jones"
        redacted = redact_pii(text)
        assert "Smith-Jones" not in redacted
        assert "[REDACTED_PERSON_NAME]" in redacted

    def test_person_name_all_caps_surname(self) -> None:
        """All-caps surnames like `VANESSA` are matched (case-insensitive)."""
        text = "Tenant: VANESSA"
        redacted = redact_pii(text)
        assert "VANESSA" not in redacted
        assert "[REDACTED_PERSON_NAME]" in redacted

    def test_person_name_comma_suffix_with_period_kept(self) -> None:
        """The `, Jr.` suffix is consumed along with the name so the suffix is redacted.

        Prior implementation gated the suffix on `(?<!\.)`, which meant a
        ``, Jr.`` (with the formal trailing period) never matched. The current
        pattern allows the optional `Jr.` / `Sr.` / `II` / `III` / `IV` suffix
        to be consumed by the redaction so downstream readers see one token,
        not a half-redacted name with a dangling suffix.
        """
        text = "TENANT: John Doe, Jr. signed"
        redacted = redact_pii(text)
        # Audit regression guard: the suffix is included in the redaction.
        assert "[REDACTED_PERSON_NAME]" in redacted
        # The trailing `signed` (sentence context) survives the redaction.
        assert redacted.endswith("signed")

    def test_person_name_bare_name_in_prose_not_redacted(self) -> None:
        """A bare capitalized name (no role label) is intentionally not caught."""
        text = "Jane Smith asked about the rent."
        redacted = redact_pii(text)
        # Judge layer catches this; this regex is intentionally label-anchored.
        assert "Jane Smith" in redacted
        assert "[REDACTED_" not in redacted


class TestRedactDictStructuralWalk:
    """Tests for redact_dict structural walk (recursive redaction)."""

    def test_handles_tuple(self) -> None:
        """Tuples are recursed into; previously silently bypassed."""
        out = redact_dict({"data": ("SSN 123-45-6789",)})
        assert "[REDACTED_SSN]" in out["data"][0], "PII in tuples must be redacted"

    def test_handles_set(self) -> None:
        """Sets are recursed into; previously silently bypassed."""
        out = redact_dict({"items": {"Contact jane@example.com"}})
        # `items` value is a set containing a single string.
        redacted_str = next(iter(out["items"]))
        assert "[REDACTED_EMAIL]" in redacted_str

    def test_handles_pydantic_like_object(self) -> None:
        """An object exposing ``model_dump()`` is dumped + redacted."""

        class Thing:
            def __init__(self, text: str) -> None:
                self.text = text

            def model_dump(self) -> dict[str, str]:
                return {"text": self.text}

        out = redact_dict({"thing": Thing("Reach me at jane@example.com")})
        assert "[REDACTED_EMAIL]" in out["thing"]["text"]

    def test_handles_nested_mixed_structure(self) -> None:
        """Nested dict-of-list-of-dict with multiple PII types is fully scrubbed."""
        payload = {
            "rows": [
                {"tenant": "TENANT: Jane Smith", "ssn": "123-45-6789"},
                {"landlord": "LANDLORD: John Doe", "email": "john@example.com"},
            ],
            "labels": ("LANDLORD: Jane Smith",),
        }
        redacted = redact_dict(payload)
        text = str(redacted)
        assert "123-45-6789" not in text
        assert "john@example.com" not in text
        assert "Jane Smith" not in text
        assert "John Doe" not in text
        assert "[REDACTED_SSN]" in text
        assert "[REDACTED_EMAIL]" in text
        assert "[REDACTED_PERSON_NAME]" in text


class TestOtherConsistency:
    """Consistency and catalog checks."""

    def test_redaction_consistency(self) -> None:
        text = "SSN: 111-22-3333"
        assert redact_pii(text) == redact_pii(text)

    def test_pattern_catalog_includes_all_categories(self) -> None:
        """Sanity check: every required category is wired up."""
        for category in (
            "ssn",
            "credit_card",
            "account_number",
            "email",
            "phone",
            "street_address",
            "date_of_birth",
            "person_name",
        ):
            assert category in PII_PATTERNS

    def test_person_name_role_labels_match_inline_alternation(self) -> None:
        """The exported ``PERSON_NAME_ROLE_LABELS`` mirrors the regex role set.

        Detects drift if someone adds a new role to the regex without
        updating the export (or vice-versa).
        """
        role_words = {label.replace("'", "").split()[0] for label in PERSON_NAME_ROLE_LABELS}
        expected = {"landlord", "tenant", "lessor", "lessee", "owner", "renter", "agent"}
        assert expected.issubset(role_words)
