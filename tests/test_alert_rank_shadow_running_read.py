"""2026-08-18 — the alert_rank_shadow_out_of_sample RUNNING-READ conversion + the five
PARKED threads (docs/roadmap/ep_profitability_program.md GOAL section, BIAS FOR ACTION
+ SELECTION rules, operator-approved recommendations 1 & 2 of the six-item list).

Covers, per the task's mandate:
  - a parked entry surfaces with its re-open trigger stated
  - a running read reports at n=1 with confidence stated
  - it does NOT present a thin read as decision-grade
  - both-directions reporting (winners admitted AND losers excluded) — the load-bearing
    test: a candidate holding the SAME winners while admitting FEWER losers than
    baseline must score as a GAIN, never a wash. A numerator-only ("winners only")
    scorer is the exact regression this test exists to catch — confirmed to fail this
    test when `score_both_directions` was temporarily mutated to ignore the losers side
    during authoring (mutation reverted; not left in the tree).

THE LINE: everything here is registry/reporting/measurement plumbing. No test touches
or asserts on any grading/entry/sizing/ordering behavior.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from scripts.alert_rank_shadow_running_read import (
    CohortRead,
    confidence_label,
    render_running_read,
    score_both_directions,
)

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data_gated_reviews.yaml"


def _load_registry() -> dict:
    return {
        r["review_id"]: r
        for r in yaml.safe_load(REGISTRY_PATH.read_text())["reviews"]
    }


PARKED_IDS = [
    "bracket_geometry_variants_parked",
    "floor_timing_never_alerted_crossers_parked",
    "rt_cutover_ep_capture_argument_parked",
    "regime_conditional_exit_grid_parked",
    "minute_pull_620_trigger_parked",
]


# ── PART 1 — parked entries surface with a re-open trigger, collection continues ──────


@pytest.mark.parametrize("review_id", PARKED_IDS)
def test_each_parked_entry_exists_and_is_pending(review_id):
    reg = _load_registry()
    assert review_id in reg, f"{review_id} missing from data_gated_reviews.yaml"
    entry = reg[review_id]
    assert entry["status"] == "pending", (
        f"{review_id} must stay status=pending — parking is not closing, and 'pending' "
        f"is the only documented status that still surfaces on the Sunday digest"
    )


@pytest.mark.parametrize("review_id", PARKED_IDS)
def test_each_parked_entry_states_its_reopen_trigger(review_id):
    """A parked entry that does not say WHEN it reopens is a delete wearing a disguise.
    Pinned to the actual trigger PHRASE ("re-opens when"), not incidental prose
    elsewhere in the entry that happens to contain "re-open" — a looser substring
    check passed on two entries before their explicit trigger line existed."""
    reg = _load_registry()
    entry = reg[review_id]
    combined = " ".join([
        entry.get("question", ""), entry.get("action_when_ready", ""),
        entry.get("notes", ""),
    ]).lower().replace("re-opens when", "reopens when")
    assert "reopens when" in combined, (
        f"{review_id} does not state an explicit 'RE-OPENS WHEN:' trigger"
    )


@pytest.mark.parametrize("review_id", PARKED_IDS)
def test_each_parked_entry_says_collection_continues(review_id):
    """'Parked' must never read as 'stopped collecting' — the operator's explicit
    instruction. Every entry must say plainly that the underlying data keeps writing."""
    reg = _load_registry()
    entry = reg[review_id]
    combined = " ".join([
        entry.get("question", ""), entry.get("notes", ""),
    ]).lower()
    assert "collection continues" in combined or "keeps writing" in combined or "keeps persisting" in combined, (
        f"{review_id} does not state that collection continues while parked"
    )


def test_four_of_five_parked_entries_carry_a_real_evidence_predicate():
    """Per the operator's instruction: prefer real evidence predicates over dates.
    Shipping five new date-fires would be self-defeating — only ONE of the five is a
    genuine date-fire (the 620/minute-pull thread, where the true trigger is a scoping
    decision, not a data threshold)."""
    from agents.market_intelligence.data_gated_reviews import is_date_fire_predicate

    reg = _load_registry()
    date_fires = [
        rid for rid in PARKED_IDS
        if is_date_fire_predicate(reg[rid].get("predicate_sql")) or reg[rid].get("predicate_sql") is None
    ]
    assert date_fires == ["minute_pull_620_trigger_parked"], (
        f"expected exactly the 620/minute-pull thread to be the honest date-fire, got {date_fires}"
    )


def test_the_one_date_fire_thread_is_labelled_honestly_not_dressed_up():
    """`predicate_sql: null` is the documented HONEST form (data_gated_reviews.py
    module docstring) — never fake SQL with no FROM clause pretending to be evidence."""
    reg = _load_registry()
    entry = reg["minute_pull_620_trigger_parked"]
    assert entry["predicate_sql"] is None
    assert isinstance(entry["earliest_review_date"], date)


def test_regime_grid_predicate_reads_the_current_thin_cells():
    """Sanity: the regime-conditional-exit-grid parked entry's predicate is a real,
    non-date-fire SQL read (not vacuously true/false)."""
    from agents.market_intelligence.data_gated_reviews import is_date_fire_predicate

    reg = _load_registry()
    entry = reg["regime_conditional_exit_grid_parked"]
    assert not is_date_fire_predicate(entry["predicate_sql"])
    assert entry["threshold"] == 10


# ── PART 1b — nothing was deleted or silently reclassified ────────────────────────────


def test_no_existing_review_ids_were_removed():
    """Parking must never delete. Spot-check a handful of pre-existing IDs this task
    touches or sits near are still present."""
    reg = _load_registry()
    for rid in (
        "alert_rank_shadow_out_of_sample", "stop_2r_running_comparison",
        "exit_path_shadow_first_read", "exit_regime_separability",
        "regime_sizing_vs_tail_recheck", "exit_tune_bull_regime_read",
        "rt_admission_recut_post_2r_exits",
    ):
        assert rid in reg, f"{rid} disappeared from the registry"


# ── PART 2 — the running-read conversion itself is wired correctly ────────────────────


def test_alert_rank_shadow_out_of_sample_is_no_longer_date_locked():
    """The 2026-10-15 gate was the whole problem (BIAS FOR ACTION) — it must be gone,
    or every part of this conversion is inert until October regardless of what the
    scorer below can do."""
    reg = _load_registry()
    entry = reg["alert_rank_shadow_out_of_sample"]
    assert entry.get("earliest_review_date") is None, (
        "a future earliest_review_date re-locks the running read behind a date gate"
    )
    assert entry["threshold"] == 1, "threshold must fire from the FIRST out-of-sample session"


def test_alert_rank_shadow_out_of_sample_predicate_is_real_evidence_not_a_date_fire():
    from agents.market_intelligence.data_gated_reviews import is_date_fire_predicate

    reg = _load_registry()
    entry = reg["alert_rank_shadow_out_of_sample"]
    assert not is_date_fire_predicate(entry["predicate_sql"])
    assert "mi_alert_rank_shadow" in entry["predicate_sql"]


def test_stop_2r_running_comparison_untouched_in_shape():
    """The model entry this conversion copies — its predicate/status must not have
    been touched by this task (only a caveat note was added to it)."""
    reg = _load_registry()
    entry = reg["stop_2r_running_comparison"]
    assert entry["status"] == "pending"
    assert entry.get("earliest_review_date") is None
    assert "mi_exit_path_shadow" in entry["evidence_predicate"]


# ── PART 3 — the running-read scorer/renderer (pure, DB-free) ─────────────────────────


def test_confidence_label_states_n_and_marks_a_thin_read_at_n1():
    label = confidence_label(1)
    assert "n=1" in label
    assert "THIN" in label
    assert "DECISION-GRADE" not in label


def test_confidence_label_no_data_state_is_distinct_from_a_thin_read():
    assert confidence_label(0) == "NO DATA YET"


def test_confidence_label_flips_to_decision_grade_exactly_at_the_mark():
    assert "DECISION-GRADE" in confidence_label(25)
    assert "THIN" in confidence_label(24)
    assert "DECISION-GRADE" not in confidence_label(24)


def test_render_running_read_never_claims_decision_grade_on_a_thin_n():
    """The hard requirement: it must NOT present a thin read as decision-grade."""
    out = render_running_read(
        n_sessions=1,
        top_quartile=CohortRead(n=2, winners_admitted=0, losers_admitted=1),
        rest_of_pool=CohortRead(n=6, winners_admitted=0, losers_admitted=4),
    )
    assert "n=1" in out
    assert "THIN" in out
    assert "DECISION-GRADE" not in out


def test_render_running_read_at_decision_grade_n_says_so():
    out = render_running_read(
        n_sessions=25,
        top_quartile=CohortRead(n=20, winners_admitted=2, losers_admitted=8),
        rest_of_pool=CohortRead(n=60, winners_admitted=2, losers_admitted=30),
    )
    assert "DECISION-GRADE" in out


# ── PART 3b — both-directions scoring (the SELECTION rule, mechanised) ────────────────


def test_same_winners_fewer_losers_scores_as_a_gain():
    """THE LOAD-BEARING TEST. Candidate holds the SAME winner count as baseline but
    admits losers at a LOWER rate -- per the GOAL section this MUST score as a gain.
    A numerator-only ('how many winners') scorer would call this a wash; confirmed to
    fail this exact assertion when score_both_directions was mutated during authoring
    to compare winners_delta alone (see module history / this file's docstring)."""
    candidate = CohortRead(n=100, winners_admitted=4, losers_admitted=20)   # 20% loser rate
    baseline = CohortRead(n=100, winners_admitted=4, losers_admitted=40)    # 40% loser rate
    verdict = score_both_directions(candidate, baseline)
    assert verdict.startswith("GAIN"), verdict
    # Wording changed 2026-08-18 (simplify): the cascade became an explicit 3x3 so
    # the both-unchanged cell stopped being mislabelled "moved in opposite
    # directions". Assert on the BEHAVIOUR this test exists for — same winners
    # plus fewer losers must score as a GAIN — not on the old phrasing.
    assert "FEWER losers" in verdict
    assert "wash" in verdict  # the SELECTION rule this cell exists to enforce


def test_fewer_winners_and_more_losers_scores_as_a_loss():
    candidate = CohortRead(n=100, winners_admitted=1, losers_admitted=50)
    baseline = CohortRead(n=100, winners_admitted=4, losers_admitted=20)
    verdict = score_both_directions(candidate, baseline)
    assert verdict.startswith("LOSS"), verdict


def test_more_winners_but_also_more_losers_is_reported_mixed_not_netted():
    """Winners up, losers up too -- must not be silently netted into a single GAIN/LOSS
    that hides one side of the trade-off."""
    candidate = CohortRead(n=100, winners_admitted=6, losers_admitted=50)
    baseline = CohortRead(n=100, winners_admitted=4, losers_admitted=20)
    verdict = score_both_directions(candidate, baseline)
    assert verdict.startswith("MIXED"), verdict


def test_zero_n_on_either_side_refuses_to_score_rather_than_divide_by_zero():
    candidate = CohortRead(n=0, winners_admitted=0, losers_admitted=0)
    baseline = CohortRead(n=10, winners_admitted=1, losers_admitted=5)
    verdict = score_both_directions(candidate, baseline)
    assert "INSUFFICIENT N" in verdict


def test_render_running_read_reports_both_directions_never_a_winner_count_alone():
    out = render_running_read(
        n_sessions=1,
        top_quartile=CohortRead(n=2, winners_admitted=0, losers_admitted=1),
        rest_of_pool=CohortRead(n=6, winners_admitted=0, losers_admitted=4),
    )
    assert "winners=" in out
    assert "losers-admitted=" in out
    # both cohorts' loser figures present, not just the top quartile's
    assert out.count("losers-admitted=") == 2
