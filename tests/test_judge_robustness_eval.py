"""ADR 0030 C1 — pins for the judge-robustness eval harness (pure scorer + fake-client e2e)."""
import asyncio
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "run_judge_robustness_eval",
    Path(__file__).parent.parent / "scripts" / "evals" / "run_judge_robustness_eval.py",
)
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)


# ── predicate scorer truth table ────────────────────────────────────────────
V = {"grade": "strong", "tier": "HIGH", "direction_vs_floor": "hold"}


@pytest.mark.parametrize("must,expect_pass", [
    ({"tier_is": "HIGH"}, True),
    ({"tier_is": "MODERATE"}, False),
    ({"tier_not": "HIGH"}, False),
    ({"tier_not": "MODERATE"}, True),
    ({"tier_in": ["HIGH", "MODERATE"]}, True),
    ({"tier_in": ["none"]}, False),
    ({"grade_is": "strong"}, True),
    ({"grade_is": "mna"}, False),
    ({"grade_in": ["strong", "routine"]}, True),
    ({"grade_in": ["mna"]}, False),
    ({"direction_in": ["hold", "demote"]}, True),
    ({"direction_in": ["promote"]}, False),
    ({"tier_not": "HIGH", "direction_in": ["hold"]}, False),  # conjunction: one fail fails
    ({"tier_is": "HIGH", "grade_is": "strong"}, True),
    ({"bogus_predicate": "x"}, False),  # unknown predicate = loud fail, never silent pass
])
def test_check_predicates_truth_table(must, expect_pass):
    passed, fails = harness.check_predicates(must, V)
    assert passed is expect_pass
    assert (fails == []) is expect_pass


# ── summarize: the gate bars ────────────────────────────────────────────────
def _r(cid, cls, passed):
    return {"case_id": cid, "class": cls, "passed": passed}


def test_summarize_hard_failure_fails_gate_regardless_of_overall():
    results = [_r("S01", "stale_news_repackaged", False)] + [
        _r(f"P{i}", "clean_print_control", True) for i in range(20)
    ]
    s = harness.summarize(results)
    assert s["hard_failures"] == ["S01"]
    assert s["overall"] > 0.85
    assert s["pass"] is False


def test_summarize_positive_bar_and_pass():
    results = ([_r(f"H{i}", "mna_as_catalyst", True) for i in range(3)]
               + [_r(f"P{i}", "structural_upgrade", True) for i in range(4)]
               + [_r("P4", "clean_print_control", False)])  # 4/5 positives = 0.8 → at bar
    s = harness.summarize(results)
    assert s["positive_control_rate"] == 0.8
    assert s["hard_failures"] == []
    # overall 7/8 = 0.875 ≥ 0.85 and no soft classes → PASS
    assert s["pass"] is True


def test_summarize_soft_class_below_bar_fails():
    results = ([_r("A", "sympathy_no_own_catalyst", False),
                _r("B", "sympathy_no_own_catalyst", True)]   # 0.5 < 0.8 soft bar
               + [_r(f"P{i}", "clean_print_control", True) for i in range(20)])
    s = harness.summarize(results)
    assert s["soft_classes_below_bar"] == ["sympathy_no_own_catalyst"]
    assert s["pass"] is False


# ── run_eval end-to-end with a fake grade_fn (retry-on-None pinned) ─────────
def test_run_eval_fake_client_scores_and_retries():
    calls = {"n": 0}

    async def fake_grade(client, payload, *, semaphore=None, timeout=None, include_axis_reads=False):
        calls["n"] += 1
        if payload["ticker"] == "FLKY" and calls.setdefault("flky", 0) == 0:
            calls["flky"] = 1
            return None  # first attempt: transport-style None → must retry once
        if payload["ticker"] == "DEAD":
            return None  # always None → NO_VERDICT after 2 attempts
        return {"grade": "routine", "tier": "MODERATE", "direction_vs_floor": "demote",
                "rationale": "r", "fire_axes": [], "confidence": 0.7}

    cases = [
        {"id": "C1", "class": "stale_news_repackaged",
         "golden": {"must": {"tier_not": "HIGH"}}, "payload": {"ticker": "OKAY"}},
        {"id": "C2", "class": "stale_news_repackaged",
         "golden": {"must": {"tier_not": "HIGH"}}, "payload": {"ticker": "FLKY"}},
        {"id": "C3", "class": "clean_print_control",
         "golden": {"must": {"tier_is": "HIGH"}}, "payload": {"ticker": "MISS"}},
        {"id": "C4", "class": "mna_as_catalyst",
         "golden": {"must": {"grade_is": "mna"}}, "payload": {"ticker": "DEAD"}},
    ]
    results = asyncio.run(harness.run_eval(cases, fake_grade, client=None))
    by_id = {r["case_id"]: r for r in results}
    assert by_id["C1"]["passed"] is True
    assert by_id["C2"]["passed"] is True          # retry recovered the None
    assert by_id["C3"]["passed"] is False         # MODERATE fails tier_is HIGH (over-skepticism visible)
    assert by_id["C4"]["passed"] is False
    assert by_id["C4"]["failed_predicates"] == ["NO_VERDICT (2x None)"]
    s = harness.summarize(results)
    assert s["hard_failures"] == ["C4"]           # a dead hard-class case fails the gate
    assert s["pass"] is False
