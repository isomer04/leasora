#!/usr/bin/env python3
"""
Pre-commit hook for PII detection in files.

Scans files for sensitive patterns (SSN, credit card, account numbers, signatures).
Exits with 0 if no PII is detected, 1 if any is found.

Usage: pre-commit-pii-scan.py [file1] [file2] ...
"""

import re
import sys
from pathlib import Path

# PII and secret patterns for pre-commit scanning.
# Includes:
# - PII: SSN, credit card, account numbers, signatures
# - Secrets: Groq API key (gsk_*), Langfuse keys (pk-lf-*, sk-lf-*), Langfuse
#   self-hosted stack secrets (NEXTAUTH_SECRET, CLICKHOUSE_PASSWORD, etc.)
# - Generic: Authorization Bearer tokens, PASSWORD/SECRET/API_KEY assignments
PII_PATTERNS = {
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    "account_number": r"\b(?:Account|Acct\.?|A/C)[:\s#]*[A-Z]{2}\d{8,12}\b",
    "signature": r"(?:^|\n)\s*(?:/s/|/Signature/|Signed:?|By:)\s*[A-Z][a-zA-Z\.\- ]{2,60}",
    "groq_api_key": r"\bgsk_[A-Za-z0-9]{16,}\b",
    "langfuse_public_key": r"\bpk-lf-[A-Fa-f0-9]{8}-[A-Za-z0-9_\-]{4,}\b",
    "langfuse_secret_key": r"\bsk-lf-[A-Fa-f0-9]{8}-[A-Za-z0-9_\-]{4,}\b",
    "langfuse_nextauth_secret": r"^LANGFUSE_NEXTAUTH_SECRET\s*=\s*([A-Fa-f0-9]{16,})\b",
    "langfuse_clickhouse_password": r"^LANGFUSE_CLICKHOUSE_PASSWORD\s*=\s*(\S{4,})\b",
    "langfuse_minio_root_password": r"^LANGFUSE_MINIO_ROOT_PASSWORD\s*=\s*(\S{4,})\b",
    "langfuse_redis_auth": r"^LANGFUSE_REDIS_AUTH\s*=\s*(\S{4,})\b",
    "bearer_token": r"(?i)\bAuthorization\s*[:=]\s*Bearer\s+[A-Za-z0-9._\-]{16,}\b",
    "password_assignment": (
        r"(?im)^[A-Z_][A-Z0-9_]*(?:PASSWORD|SECRET|API_KEY)\s*=\s*(\S{8,})\b"
    ),
}

# Files to skip
SKIP_PATTERNS = {
    r"\.git/",
    r"node_modules/",
    r"\.pytest_cache/",
    r"__pycache__/",
    r"\.venv/",
    r"\.mypy_cache/",
}


def should_skip_file(filepath: str) -> bool:
    """Check if file should be skipped from PII scanning."""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, filepath):
            return True
    return False


def scan_file_for_pii(filepath: str) -> list[tuple[int, str, str]]:
    """
    Scan a file for PII patterns.

    Returns list of (line_number, pattern_name, matched_text) tuples.
    """
    findings = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except (IOError, OSError) as e:
        print(f"Warning: Could not read {filepath}: {e}")
        return findings

    for line_num, line in enumerate(lines, start=1):
        for pattern_name, pattern_regex in PII_PATTERNS.items():
            if re.search(pattern_regex, line, re.IGNORECASE):
                matched_text = line.strip()[:80]  # Truncate for display
                findings.append((line_num, pattern_name, matched_text))

    return findings


def main(argv: list[str] | None = None) -> int:
    """Scan files for PII and return exit code (0=clean, 1=found PII)."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("No files to scan.")
        return 0

    total_findings = 0

    for filepath in argv:
        # Skip certain directories/files
        if should_skip_file(filepath):
            continue

        # Skip certain file types (binaries, etc.)
        if Path(filepath).suffix in {".pdf", ".png", ".jpg", ".bin", ".lock"}:
            continue

        findings = scan_file_for_pii(filepath)
        if findings:
            print(f"\n{filepath}:")
            for line_num, pattern_name, matched_text in findings:
                print(f"  Line {line_num}: {pattern_name}")
                print(f"    {matched_text}")
            total_findings += len(findings)

    if total_findings > 0:
        print(f"\n[FAIL] PII Detection failed: {total_findings} pattern(s) found.")
        print(
            "Please remove or redact any sensitive data before committing.\n"
            "Valid patterns to redact:\n"
        )
        for name, pattern in PII_PATTERNS.items():
            print(f"  - {name}: {pattern}")
        return 1

    print("[OK] PII scan passed: no sensitive patterns detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
