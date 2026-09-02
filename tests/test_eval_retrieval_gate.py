"""Scoring maths for the retrieval gate — no network, no keys.

The metrics are the gate's whole point, so they get asserted rather than eyeballed:
a silently wrong nDCG would make a regression look like an improvement.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("gate", ROOT / "scripts" / "eval_retrieval_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_perfect_ranking_scores_one():
    m = gate.score(["a", "b", "c"], {"a", "b", "c"})
    assert m["recall@5"] == 1.0
    assert m["mrr"] == 1.0
    assert m["ndcg@5"] == pytest.approx(1.0)


def test_nothing_relevant_scores_zero():
    m = gate.score(["x", "y"], {"a"})
    assert m["recall@5"] == 0.0
    assert m["mrr"] == 0.0
    assert m["ndcg@5"] == 0.0


def test_mrr_uses_the_first_hit_not_the_count():
    assert gate.score(["x", "a"], {"a"})["mrr"] == pytest.approx(0.5)
    assert gate.score(["x", "y", "a"], {"a"})["mrr"] == pytest.approx(1 / 3)


def test_recall_is_over_labelled_not_over_returned():
    # one of two relevant events found: recall 0.5, precision 1/5
    m = gate.score(["a"], {"a", "b"})
    assert m["recall@5"] == pytest.approx(0.5)
    assert m["precision@5"] == pytest.approx(0.2)


def test_ndcg_rewards_rank_order():
    early = gate.score(["a", "x", "y"], {"a"})["ndcg@5"]
    late = gate.score(["x", "y", "a"], {"a"})["ndcg@5"]
    assert early > late


def test_results_past_k_are_ignored_for_recall():
    # relevant event sits 6th; beyond K=5, so recall is 0 but MRR still sees it
    ranked = ["x1", "x2", "x3", "x4", "x5", "a"]
    m = gate.score(ranked, {"a"})
    assert m["recall@5"] == 0.0
    assert m["mrr"] == pytest.approx(1 / 6)


def test_floors_are_below_the_recorded_baseline():
    """A floor above the baseline would fail every run from day one."""
    baseline = {"recall@5": 0.232, "mrr": 0.432, "ndcg@5": 0.278}
    for metric, floor in gate.FLOORS.items():
        assert floor <= baseline[metric], f"{metric} floor {floor} exceeds baseline"
