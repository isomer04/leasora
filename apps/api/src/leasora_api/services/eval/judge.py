"""LLM-as-judge scorer for answer quality (offline half of the eval harness).

Compares a generated answer against a reference answer and the retrieved
context, and returns a structured verdict covering faithfulness/groundedness
(every claim supported by the retrieved clauses), correctness (matches the
reference answer), and relevance/completeness.

This is intentionally lightweight — a single JSON-mode LLM call with a pinned 
low temperature. More sophisticated versions (with runtime guardrail hooks and 
a data-privacy auditor) can be built on top of this same pattern.
"""

import json
import logging

from leasora_api.core.exceptions import LLMError
from leasora_api.core.security import redact_pii
from leasora_api.services.llm.groq_client import LLMClient, groq_client

logger = logging.getLogger(__name__)

_JUDGE_PROMPT_TEMPLATE = """You are evaluating the quality of an AI-generated answer to a question \
about a lease agreement.

Question: {question}

Retrieved lease context (the answer should be grounded in this):
{context}

Reference answer (ground truth):
{reference_answer}

Generated answer (to evaluate):
{generated_answer}

Score the generated answer on three dimensions, each from 0.0 to 1.0:
- faithfulness: Is every claim in the generated answer supported by the retrieved context? \
(1.0 = fully grounded, 0.0 = contains unsupported/hallucinated claims)
- correctness: Does the generated answer match the reference answer's meaning? \
(1.0 = fully matches, 0.0 = contradicts or misses the point)
- relevance: Does the generated answer directly address the question without irrelevant content? \
(1.0 = fully relevant and complete, 0.0 = off-topic or incomplete)

Respond with ONLY a JSON object in this exact form:
{{"faithfulness": <float>, "correctness": <float>, "relevance": <float>}}"""


def _default_verdict() -> dict[str, object]:
    """Fallback verdict used when the judge call fails or returns bad output.

    The ``_judge_unavailable`` flag is set so the runner can distinguish a
    broken judge (returned by Groq timeout / JSON parse error) from a
    uniformly-bad model. It is NOT included in the answer-quality mean.
    """
    return {
        "faithfulness": 0.0,
        "correctness": 0.0,
        "relevance": 0.0,
        "_judge_unavailable": True,
    }


def judge_answer(
    question: str,
    context: str,
    generated_answer: str,
    reference_answer: str,
    llm_client: LLMClient | None = None,
) -> dict[str, object]:
    """Score a generated answer against a reference answer using an LLM judge.

    Redacts regex-catchable PII from all payload fields before they reach the
    judge prompt, ensuring comparison consistency (redacted tokens match on both
    sides). Returns all-zero scores on failure rather than raising, so a single
    bad judge call doesn't abort a full eval run.

    Args:
        question: The original question.
        context: The retrieved lease context used to generate the answer.
        generated_answer: The answer produced by the RAG pipeline.
        reference_answer: The ground-truth reference answer.
        llm_client: Optional client override (defaults to the shared Groq client).

    Returns:
        Dict with ``faithfulness``, ``correctness``, ``relevance`` scores
        in ``[0.0, 1.0]`` plus an optional ``_judge_unavailable`` boolean
        (set ``True`` when the judge call failed, so the runner can count
        failures and not silently treat a broken judge as a uniformly-bad
        model). Returns all-zero scores on failure, rather than raising,
        so a single bad judge call doesn't abort a full eval run.
    """
    client = llm_client or groq_client
    prompt = _JUDGE_PROMPT_TEMPLATE.format(
        question=redact_pii(question),
        context=redact_pii(context),
        reference_answer=redact_pii(reference_answer),
        generated_answer=redact_pii(generated_answer),
    )

    try:
        raw = client.complete(prompt, temperature=0.0)
    except LLMError:
        logger.exception("Judge LLM call failed")
        return _default_verdict()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Strip common code-fence wrapping and retry once.
        stripped = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            # raw is the LLM's verbatim echo; redact before logging.
            logger.warning("Judge response was not valid JSON: %s", redact_pii(raw[:200]))
            return _default_verdict()

    verdict: dict[str, object] = {
        "faithfulness": 0.0,
        "correctness": 0.0,
        "relevance": 0.0,
        "_judge_unavailable": False,
    }
    for key in ("faithfulness", "correctness", "relevance"):
        value = parsed.get(key)
        if isinstance(value, (int, float)) and 0.0 <= value <= 1.0:
            verdict[key] = float(value)
    return verdict


def answer_quality_score(verdict: dict[str, object]) -> float:
    """Combine a judge verdict into a single answer-quality score.

    Args:
        verdict: Dict with ``faithfulness``, ``correctness``, and ``relevance``.

    Returns:
        Unweighted mean of the three dimensions. The ``_judge_unavailable``
        flag (when present) is intentionally not included in the mean — it
        is reported separately by the runner so a broken judge is
        distinguishable from a uniformly-bad model.
    """
    dimensions = ("faithfulness", "correctness", "relevance")
    # Cast each value to float defensively — verdicts are typed as
    # ``dict[str, object]`` but at runtime every dimension is a 0.0–1.0
    # number. ``Default to 0.0`` if the key is missing so a stripped
    # verdict degrades gracefully rather than raising.
    values: list[float] = []
    for dim in dimensions:
        raw = verdict.get(dim, 0.0)
        values.append(float(raw) if isinstance(raw, (int, float)) else 0.0)
    return sum(values) / len(values)
