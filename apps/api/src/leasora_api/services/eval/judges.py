"""LLM-as-judge guardrails: runtime answer-groundedness check + data-privacy audit.

Builds on ``services/eval/judge.py``'s offline faithfulness/correctness/
relevance scorer with a runtime-usable groundedness check
(``check_answer_grounded``), and adds a separate privacy auditor
(``audit_for_pii``) that flags PII a deterministic regex might miss.

Design boundary: an LLM judge can *detect* problems but does not
*guarantee* them away. The guarantee comes from deterministic code.
(``core.security.redact_pii``, applied before anything is written to
ChromaDB metadata, the answer cache, or Langfuse traces). The privacy judge
here is an audit/detection layer on top of that enforcement — it must never
be the only line of defense, and it must never echo raw PII in its own
output, rationale, or logs (only categories/locations).
"""

import logging

from leasora_api.core.json_parse import parse_json_lenient
from leasora_api.core.security import redact_pii
from leasora_api.services.llm.groq_client import LLMClient, groq_client

logger = logging.getLogger(__name__)

_GROUNDEDNESS_PROMPT_TEMPLATE = """You are checking whether an AI-generated answer about a lease \
agreement is grounded in the retrieved context, or whether it contains unsupported/hallucinated \
claims.

Retrieved lease context:
{context}

Generated answer:
{answer}

Is every factual claim in the generated answer directly supported by the retrieved context above? \
Answer conservatively: if a claim is not clearly supported, treat it as unsupported.

Respond with ONLY a JSON object in this exact form:
{{"grounded": <true or false>, "unsupported_claims": [<list of unsupported claim strings, empty if none>]}}"""

_PRIVACY_AUDIT_PROMPT_TEMPLATE = """You are auditing a payload that is about to be persisted \
(stored in a database, cache, or observability trace) for personally-identifying information \
(PII) that automated regex redaction may have missed — for example, full names, street \
addresses, email addresses, phone numbers, or other free-text identifiers not caught by \
SSN/credit-card/account-number regex patterns.

Payload to audit:
{payload}

Identify PII categories present, WITHOUT repeating the actual PII values in your response — \
report only the category and a short generic location description (e.g. "tenant full name in \
the 'excerpt' field"), never the value itself.

Respond with ONLY a JSON object in this exact form:
{{"has_pii": <true or false>, "findings": [{{"category": "<category>", "location": "<short generic location>"}}]}}"""


def check_answer_grounded(
    context: str,
    answer: str,
    llm_client: LLMClient | None = None,
) -> tuple[bool, list[str]]:
    """Runtime groundedness check: is the answer supported by the context?

    Intended as an optional guardrail called from ``RAGQueryService`` after
    generation (gated by ``settings.answer_guard_enabled``, off by default
    since it adds an extra LLM call + latency).

    Args:
        context: The retrieved lease context used to generate the answer.
        answer: The generated answer to check.
        llm_client: Optional client override (defaults to the shared Groq client).

    Returns:
        Tuple of ``(grounded, unsupported_claims)``. Fails safe: if the judge
        call itself fails or returns malformed output, returns
        ``(False, ["judge_unavailable"])`` so a broken judge degrades to a
        refusal rather than silently waving through an unverified answer.
    """
    client = llm_client or groq_client
    # Redact regex-catchable PII (email, phone, SSN, etc.) from both context
    # and answer before they reach the judge prompt/logs. Redacting both
    # sides consistently preserves groundedness semantics: an email that
    # appears in both context and answer still redacts to the same
    # placeholder on each side, so the "is this claim supported" comparison
    # still holds.
    safe_context = redact_pii(context)
    safe_answer = redact_pii(answer)
    prompt = _GROUNDEDNESS_PROMPT_TEMPLATE.format(context=safe_context, answer=safe_answer)

    try:
        raw = client.complete(prompt, temperature=0.0)
    except Exception:
        logger.exception("Groundedness judge LLM call failed")
        return False, ["judge_unavailable"]

    parsed = _parse_json_with_fallback(raw)
    if parsed is None:
        # raw is the LLM's verbatim echo; redact before logging.
        logger.warning("Groundedness judge response was not valid JSON: %s", redact_pii(raw[:200]))
        return False, ["judge_unavailable"]

    grounded = bool(parsed.get("grounded", False))
    unsupported = parsed.get("unsupported_claims", [])
    if not isinstance(unsupported, list):
        unsupported = []
    return grounded, [str(claim) for claim in unsupported]


def audit_for_pii(
    payload: str,
    llm_client: LLMClient | None = None,
) -> tuple[bool, list[dict[str, str]]]:
    """Audit a payload bound for persistence for PII a regex might miss.

    Detection only — does not redact or block persistence itself. Callers
    that need enforcement must still run ``core.security.redact_pii`` before
    writing the payload anywhere; this function is a verifier on top of that.

    Args:
        payload: The text payload about to be persisted (already passed
            through ``redact_pii`` by the caller, ideally — this audits for
            what regex redaction missed).
        llm_client: Optional client override (defaults to the shared Groq client).

    Returns:
        Tuple of ``(has_pii, findings)`` where each finding is
        ``{"category": ..., "location": ...}`` — never the raw PII value.
        Fails safe: if the judge call fails, returns
        ``(True, [{"category": "audit_unavailable", "location": "unknown"}])``
        so a broken auditor is treated as a potential finding, not a clean
        bill of health.
    """
    client = llm_client or groq_client
    # Redact known patterns before even sending to the judge, so the judge's
    # own prompt/logs never contain PII that the deterministic layer already
    # knows how to catch.
    safe_payload = redact_pii(payload)
    prompt = _PRIVACY_AUDIT_PROMPT_TEMPLATE.format(payload=safe_payload)

    try:
        raw = client.complete(prompt, temperature=0.0)
    except Exception:
        logger.exception("Privacy audit judge LLM call failed")
        return True, [{"category": "audit_unavailable", "location": "unknown"}]

    parsed = _parse_json_with_fallback(raw)
    if parsed is None:
        # raw is the LLM's verbatim echo; redact before logging.
        logger.warning("Privacy audit judge response was not valid JSON: %s", redact_pii(raw[:200]))
        return True, [{"category": "audit_unavailable", "location": "unknown"}]

    has_pii = bool(parsed.get("has_pii", False))
    raw_findings = parsed.get("findings", [])
    findings: list[dict[str, str]] = []
    if isinstance(raw_findings, list):
        for item in raw_findings:
            if isinstance(item, dict):
                findings.append(
                    {
                        "category": str(item.get("category", "unknown")),
                        "location": str(item.get("location", "unknown")),
                    }
                )
    return has_pii, findings


def _parse_json_with_fallback(raw: str) -> dict[str, object] | None:
    """Parse JSON, stripping common code-fence wrapping as a fallback.

    Thin wrapper around :func:`core.json_parse.parse_json_lenient` that
    also narrows the result to ``dict`` (the prompt shape we ask the
    LLM for). Kept locally as a private name because the two callsites
    in this module both want the dict-narrowed behavior in one line.
    """
    parsed = parse_json_lenient(raw)
    return parsed if isinstance(parsed, dict) else None
