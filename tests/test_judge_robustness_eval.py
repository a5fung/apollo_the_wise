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

    # log_caller became REQUIRED on grade_holistic 2026-08-02 and run_eval now threads it, so the
    # fake must accept it or this stops exercising the real call shape.
    async def fake_grade(client, payload, *, semaphore=None, timeout=None,
                         include_axis_reads=False, log_caller=None):
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


# ── #167 gate 2 — differential mode (fake-client, proved BEFORE any paid run) ───────────────
def test_classify_movement_up_down_unchanged():
    high = {"tier": "HIGH", "grade": "strong"}
    mod_routine = {"tier": "MODERATE", "grade": "routine"}
    mod_strong = {"tier": "MODERATE", "grade": "strong"}

    up = harness.classify_movement(mod_routine, high)
    assert up["direction"] == "UP"
    assert up["crossed_into_high"] is True

    down = harness.classify_movement(high, mod_routine)
    assert down["direction"] == "DOWN"
    assert down["crossed_into_high"] is False   # dropping OUT of HIGH is not a crossing INTO it

    unchanged = harness.classify_movement(mod_routine, mod_routine)
    assert unchanged["direction"] == "UNCHANGED"
    assert unchanged["crossed_into_high"] is False

    # same tier, grade improves within it → still UP (inflation-but-inert, no boundary crossed)
    grade_only_up = harness.classify_movement(mod_routine, mod_strong)
    assert grade_only_up["direction"] == "UP"
    assert grade_only_up["crossed_into_high"] is False


def test_classify_movement_mna_excluded_from_grade_ladder():
    """mna is the M&A path, not a rung on the game_changer/strong/routine ladder — grade_delta
    must not be computed for it (would misclassify an M&A read as an up/down move)."""
    base = {"tier": "MODERATE", "grade": "routine"}
    forced = {"tier": "MODERATE", "grade": "mna"}
    m = harness.classify_movement(base, forced)
    assert m["grade_delta"] is None
    assert m["direction"] == "UNCHANGED"   # tier held, grade_delta not comparable → no move claimed
    assert "mna" in m["note"]


def test_classify_movement_no_verdict_handled():
    m = harness.classify_movement(None, {"tier": "HIGH", "grade": "strong"})
    assert m["direction"] == "NO_VERDICT"
    assert m["crossed_into_high"] is False


def test_summarize_differential_counts_and_crossings():
    results = [
        {"case_id": "A", "direction": "UP", "crossed_into_high": True},
        {"case_id": "B", "direction": "UP", "crossed_into_high": False},
        {"case_id": "C", "direction": "UNCHANGED", "crossed_into_high": False},
        {"case_id": "D", "direction": "DOWN", "crossed_into_high": False},
    ]
    s = harness.summarize_differential(results)
    assert s == {
        "n": 4, "up": 2, "unchanged": 1, "down": 1, "no_verdict": 0,
        "up_ids": ["A", "B"], "down_ids": ["D"], "unchanged_ids": ["C"], "no_verdict_ids": [],
        "crossed_into_high": ["A"],
    }


def test_run_differential_skips_already_true_and_pairs_calls():
    """Fake grade_fn: promotes tier from MODERATE to HIGH ONLY when in_narrative_cohort is
    True in the payload it actually received — the exact mechanism #167 gate 2 is testing
    (the judge reads the flag verbatim). Proves: (1) already-true corpus cases are skipped
    entirely (zero calls), (2) each flippable case gets exactly 2 calls (base + forced), and
    (3) the forced call's payload really does carry in_narrative_cohort=True."""
    calls = []

    async def fake_grade(client, payload, *, semaphore=None, timeout=None,
                         include_axis_reads=False, log_caller=None):
        calls.append((payload["ticker"], payload["in_narrative_cohort"], log_caller))
        if payload["in_narrative_cohort"]:
            return {"grade": "strong", "tier": "HIGH", "direction_vs_floor": "promote",
                    "rationale": "narrative joined", "fire_axes": ["narrative"], "confidence": 0.8}
        return {"grade": "routine", "tier": "MODERATE", "direction_vs_floor": "hold",
                "rationale": "no own catalyst", "fire_axes": [], "confidence": 0.6}

    cases = [
        {"id": "F1", "class": "sympathy_no_own_catalyst",
         "payload": {"ticker": "FLIP1", "in_narrative_cohort": False}},
        {"id": "F2", "class": "sympathy_no_own_catalyst",
         "payload": {"ticker": "FLIP2", "in_narrative_cohort": False}},
        {"id": "T1", "class": "structural_upgrade",
         "payload": {"ticker": "ALREADYTRUE", "in_narrative_cohort": True}},
    ]
    diff = asyncio.run(harness.run_differential(cases, fake_grade, client=None))

    assert diff["skipped_already_true"] == ["T1"]
    assert len(calls) == 4                         # 2 calls each for F1/F2, none for T1
    assert all(c[2] == "judge_narrative_diff_eval" for c in calls)   # its own spend bucket
    forced_calls = [c for c in calls if c[1] is True]
    assert {c[0] for c in forced_calls} == {"FLIP1", "FLIP2"}

    by_id = {r["case_id"]: r for r in diff["results"]}
    assert set(by_id) == {"F1", "F2"}              # T1 never scored — nothing to differentiate
    assert by_id["F1"]["direction"] == "UP"
    assert by_id["F1"]["crossed_into_high"] is True
    assert by_id["F1"]["base_tier"] == "MODERATE" and by_id["F1"]["forced_tier"] == "HIGH"
    s = diff["summary"]
    assert s["up"] == 2 and s["crossed_into_high"] == ["F1", "F2"]


def test_run_differential_retries_once_on_none():
    calls = {"n": 0}

    async def flaky_grade(client, payload, *, semaphore=None, timeout=None,
                          include_axis_reads=False, log_caller=None):
        calls["n"] += 1
        if payload["in_narrative_cohort"] and calls["n"] < 3:
            return None   # forced-arm call: None once, then succeeds on retry
        return {"grade": "routine", "tier": "MODERATE", "direction_vs_floor": "hold",
                "rationale": "r", "fire_axes": [], "confidence": 0.5}

    cases = [{"id": "R1", "class": "sympathy_no_own_catalyst",
              "payload": {"ticker": "RETRY", "in_narrative_cohort": False}}]
    diff = asyncio.run(harness.run_differential(cases, flaky_grade, client=None))
    assert diff["results"][0]["direction"] == "UNCHANGED"   # retry recovered a real verdict
    assert calls["n"] == 3   # base call (1) + forced call None (1) + forced retry (1)
