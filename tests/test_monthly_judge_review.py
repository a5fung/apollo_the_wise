"""#337 v1 — monthly judge-review aggregation. Pins the pure aggregator + formatter (no DB):
the direction/agreement counts, the fwd-outcome buckets, and the Unjustified-Demotion sweep
(ADR 0011's winner-killing guard) — the parts that decide what the operator sees.
"""
from scripts.monthly_judge_review import aggregate_judge_review, format_judge_review

_ROWS = [
    # promote, judge HIGH over floor MODERATE, ran +8% → promote bucket, NOT agree
    {"ticker": "AAA", "alert_date": "2026-06-10", "judge_tier": "HIGH",
     "baseline_floor_tier": "MODERATE", "judge_direction": "promote", "fwd_5d_pct": 8.0},
    # hold, judge HIGH == floor HIGH → agree; +3%
    {"ticker": "BBB", "alert_date": "2026-06-11", "judge_tier": "HIGH",
     "baseline_floor_tier": "HIGH", "judge_direction": "hold", "fwd_5d_pct": 3.0},
    # demote to none, but ran +9% → UNJUSTIFIED demote (the guard)
    {"ticker": "CCC", "alert_date": "2026-06-12", "judge_tier": "none",
     "baseline_floor_tier": "HIGH", "judge_direction": "demote", "fwd_5d_pct": 9.0},
    # demote, correctly avoided (-4%)
    {"ticker": "DDD", "alert_date": "2026-06-13", "judge_tier": "none",
     "baseline_floor_tier": "MODERATE", "judge_direction": "demote", "fwd_5d_pct": -4.0},
    # promote but outcome not settled → counted in n, excluded from settled stats
    {"ticker": "EEE", "alert_date": "2026-06-17", "judge_tier": "HIGH",
     "baseline_floor_tier": "MODERATE", "judge_direction": "promote", "fwd_5d_pct": None},
]


def test_counts_and_agreement():
    a = aggregate_judge_review(_ROWS)
    assert a["n"] == 5 and a["settled"] == 4
    assert a["dir_counts"] == {"promote": 2, "hold": 1, "demote": 2, "none": 0}
    assert round(a["agreement_rate"]) == 20      # only BBB has judge==floor


def test_buckets_exclude_unsettled():
    a = aggregate_judge_review(_ROWS)
    assert a["by_dir"]["promote"] == [8.0]       # EEE (None) excluded
    assert a["by_dir"]["hold"] == [3.0]
    assert sorted(a["by_dir"]["demote"]) == [-4.0, 9.0]
    assert sorted(a["by_tier"]["HIGH"]) == [3.0, 8.0]
    assert sorted(a["by_tier"]["none"]) == [-4.0, 9.0]


def test_unjustified_demotion_sweep():
    a = aggregate_judge_review(_ROWS)
    ud = a["unjustified_demotes"]
    assert len(ud) == 1 and ud[0]["ticker"] == "CCC"   # +9% demote caught; -4% demote is fine


def test_formatter_surfaces_not_prescribes():
    text = format_judge_review(aggregate_judge_review(_ROWS), 30)
    assert "MONTHLY JUDGE REVIEW" in text
    assert "UNJUSTIFIED-DEMOTION" in text and "CCC" in text
    assert "OPERATOR labeling" in text
    # SURFACES facts, never prescribes code (feedback_weekly_review_surface_not_prescribe).
    assert "proposed change" not in text.lower() and "should " not in text.lower()


def test_empty_rows_safe():
    a = aggregate_judge_review([])
    assert a["n"] == 0 and a["agreement_rate"] == 0.0
    assert "n=0" in format_judge_review(a, 30)
