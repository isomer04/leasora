"""Pure retrieval evaluation metrics.

Each function takes ranked retrieved IDs and a ground-truth relevant set (or
per-question inputs for the aggregate/refusal metrics) and returns a score in
``[0, 1]``. No I/O, no LLM calls — deterministic and unit-testable.
"""

from collections.abc import Sequence


def reciprocal_rank(retrieved_ids: Sequence[str], relevant_ids: set[str]) -> float:
    """Reciprocal rank of the first relevant hit in a single ranked list.

    Args:
        retrieved_ids: Ranked list of retrieved IDs (most relevant first).
        relevant_ids: Set of ground-truth relevant IDs.

    Returns:
        ``1 / rank`` of the first relevant hit (1-indexed), or ``0.0`` if no
        relevant ID appears in ``retrieved_ids``. Returns ``0.0`` if
        ``relevant_ids`` is empty (nothing to find).
    """
    if not relevant_ids:
        return 0.0
    for rank, retrieved_id in enumerate(retrieved_ids, start=1):
        if retrieved_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def mrr(rankings: Sequence[tuple[Sequence[str], set[str]]]) -> float:
    """Mean Reciprocal Rank across multiple queries.

    Args:
        rankings: Sequence of ``(retrieved_ids, relevant_ids)`` pairs, one per
            query.

    Returns:
        Mean of :func:`reciprocal_rank` across all queries, or ``0.0`` if
        ``rankings`` is empty.
    """
    if not rankings:
        return 0.0
    scores = [reciprocal_rank(retrieved, relevant) for retrieved, relevant in rankings]
    return sum(scores) / len(scores)


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of relevant IDs found within the top-``k`` retrieved IDs.

    Args:
        retrieved_ids: Ranked list of retrieved IDs.
        relevant_ids: Set of ground-truth relevant IDs.
        k: Cutoff rank.

    Returns:
        ``|top_k ∩ relevant| / |relevant|``, or ``0.0`` if ``relevant_ids`` is
        empty.
    """
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)


def precision_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of the top-``k`` retrieved IDs that are relevant.

    Args:
        retrieved_ids: Ranked list of retrieved IDs.
        relevant_ids: Set of ground-truth relevant IDs.
        k: Cutoff rank.

    Returns:
        ``|top_k ∩ relevant| / min(k, len(top_k))``, or ``0.0`` if no IDs were
        retrieved within the cutoff.
    """
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = len(set(top_k) & relevant_ids)
    return hits / len(top_k)


def mean_recall_at_k(
    rankings: Sequence[tuple[Sequence[str], set[str]]], k: int
) -> float:
    """Mean recall@k across multiple queries."""
    if not rankings:
        return 0.0
    scores = [recall_at_k(retrieved, relevant, k) for retrieved, relevant in rankings]
    return sum(scores) / len(scores)


def mean_precision_at_k(
    rankings: Sequence[tuple[Sequence[str], set[str]]], k: int
) -> float:
    """Mean precision@k across multiple queries."""
    if not rankings:
        return 0.0
    scores = [precision_at_k(retrieved, relevant, k) for retrieved, relevant in rankings]
    return sum(scores) / len(scores)


def refusal_accuracy(predictions: Sequence[tuple[bool, bool]]) -> float:
    """Accuracy of the refusal gate across multiple questions.

    Args:
        predictions: Sequence of ``(should_refuse, did_refuse)`` pairs, one
            per question.

    Returns:
        Fraction of questions where ``did_refuse == should_refuse``, or
        ``0.0`` if ``predictions`` is empty.
    """
    if not predictions:
        return 0.0
    correct = sum(1 for should, did in predictions if should == did)
    return correct / len(predictions)
