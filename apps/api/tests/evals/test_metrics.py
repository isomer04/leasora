from leasora_api.services.eval.metrics import (
    mean_precision_at_k,
    mean_recall_at_k,
    mrr,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    refusal_accuracy,
)


def test_reciprocal_rank_first_position_hit():
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0


def test_reciprocal_rank_third_position_hit():
    assert reciprocal_rank(["a", "b", "c"], {"c"}) == 1 / 3


def test_reciprocal_rank_no_hit_returns_zero():
    assert reciprocal_rank(["a", "b"], {"z"}) == 0.0


def test_reciprocal_rank_empty_relevant_returns_zero():
    assert reciprocal_rank(["a", "b"], set()) == 0.0


def test_mrr_averages_across_queries():
    rankings = [
        (["a", "b", "c"], {"a"}),  # RR = 1.0
        (["a", "b", "c"], {"b"}),  # RR = 0.5
    ]
    assert mrr(rankings) == 0.75


def test_mrr_empty_rankings_returns_zero():
    assert mrr([]) == 0.0


def test_recall_at_k_all_relevant_found():
    assert recall_at_k(["a", "b", "c"], {"a", "b"}, k=3) == 1.0


def test_recall_at_k_partial_match():
    assert recall_at_k(["a", "x", "y"], {"a", "b"}, k=3) == 0.5


def test_recall_at_k_respects_cutoff():
    assert recall_at_k(["x", "y", "a"], {"a"}, k=2) == 0.0


def test_recall_at_k_empty_relevant_returns_zero():
    assert recall_at_k(["a", "b"], set(), k=2) == 0.0


def test_precision_at_k_all_hits():
    assert precision_at_k(["a", "b"], {"a", "b", "c"}, k=2) == 1.0


def test_precision_at_k_partial_hits():
    assert precision_at_k(["a", "x"], {"a"}, k=2) == 0.5


def test_precision_at_k_no_retrieved_returns_zero():
    assert precision_at_k([], {"a"}, k=5) == 0.0


def test_mean_recall_at_k_averages():
    rankings = [
        (["a", "b"], {"a", "b"}),  # recall = 1.0
        (["x", "y"], {"a"}),  # recall = 0.0
    ]
    assert mean_recall_at_k(rankings, k=2) == 0.5


def test_mean_precision_at_k_averages():
    rankings = [
        (["a", "b"], {"a", "b"}),  # precision = 1.0
        (["a", "x"], {"a"}),  # precision = 0.5
    ]
    assert mean_precision_at_k(rankings, k=2) == 0.75


def test_refusal_accuracy_all_correct():
    predictions = [(True, True), (False, False)]
    assert refusal_accuracy(predictions) == 1.0


def test_refusal_accuracy_partial_correct():
    predictions = [(True, True), (False, True)]
    assert refusal_accuracy(predictions) == 0.5


def test_refusal_accuracy_empty_returns_zero():
    assert refusal_accuracy([]) == 0.0
