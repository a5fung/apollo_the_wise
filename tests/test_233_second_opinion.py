"""#233 (operator-signed 2026-08-27) — the Perplexity comparison changes hands.

The agreement half is RETIRED and the disagreement half goes to the judge.

  before: Perplexity agrees with the grader's label -> confidence_multiplier = 1.2, which
          multiplied straight into the EP score. Measured over 419 alerts
          (docs/analysis/pplx_agreement_boost_233_2026-08-27.md): boosted names ran a SMALLER
          5-day max move (9.17% vs 11.20%) and, once score band is held constant, the effect
          is a null. What it actually did shows in the gap column — boosted names gap 15.5%
          against 18.8%, i.e. it lifted smaller movers over the bar.
  after:  agreement changes nothing. A DISAGREEMENT is rendered to the judge as a labelled
          re-read prompt (rubric rule 7) — that half has evidence: it roughly doubles the odds
          the judge also disagrees (33% vs an 18% base) and the two point the same way 25
          times in 29.

⚠ The reason rule 7 says "not independent corroboration": the judge ALREADY reads Perplexity's
[Web summary] text, so counting its grade as a separate vote counts one source twice. That is
the operator's named concern and the monthly review measures it across the ship boundary.
"""
import io
import re

from agents.market_intelligence.ep_grade_judge import (
    _RUBRIC, _build_judge_prompt, assemble_judge_inputs,
)
from agents.market_intelligence.judge_review import (
    _SECOND_OPINION_LIVE_FROM, aggregate_judge_review, format_judge_review,
)

_EP_SRC = io.open("agents/market_intelligence/ep_detector.py", encoding="utf-8").read()

# The rendered block's own marker. Rule 7 also puts "SECOND OPINION" in _RUBRIC, which rides
# every prompt — so presence of the phrase proves nothing about the block.
_BLOCK = "--- SECOND OPINION (a different model graded the same catalyst) ---"


def _payload(second, label):
    p = assemble_judge_inputs(
        {"ticker": "T", "gap_pct": 10.0, "catalyst": "c", "catalyst_quality": label,
         "score_tier": "HIGH", "ep_score": 80},
        second_opinion=second)
    p["floor_catalyst_quality"] = label
    return p


# ── the boost is gone, and cannot come back by accident ──────────────────────────────────
def test_the_agreement_boost_is_retired():
    assert "confidence_multiplier = 1.2" not in _EP_SRC, \
        "the 1.2x agreement boost is retired (#233, operator-signed 2026-08-27)"
    # …and the comparison itself survives, as the judge-facing disagreement flag.
    assert "_pplx_disagreed" in _EP_SRC
    assert "second_opinion=r.get(\"gemini_validation\")" in _EP_SRC


def test_the_hedge_downgrade_recomputes_the_flag_against_the_new_label():
    """The hedge branch CHANGES catalyst_quality, so a flag computed before it would record a
    stale answer for the telemetry cohort."""
    hedge = _EP_SRC.split("Perplexity hedge detected")[1][:1400]
    assert "_pplx_disagreed = bool(pplx_quality and pplx_quality != catalyst_quality)" in hedge


# ── the prompt block: disagreement only, and never as a vote ─────────────────────────────
def test_agreement_renders_nothing_at_all():
    """Agreement carries no measured information, so it must not reach the prompt — the
    ~half of alerts where the two concur stay byte-identical to the pre-change form."""
    agree = _build_judge_prompt(_payload("strong", "strong"))
    none_given = _build_judge_prompt(_payload(None, "strong"))
    # NB: rule 7 puts the words "SECOND OPINION" in the rubric itself, which is always in the
    # prompt — assert on the BLOCK marker, not the phrase.
    assert _BLOCK not in agree
    assert agree == none_given


def test_disagreement_is_rendered_as_a_re_read_prompt_never_a_vote():
    out = _build_judge_prompt(_payload("routine", "game_changer"))
    assert _BLOCK in out
    assert "It graded this catalyst routine" in out
    assert "the grader's label is game_changer" in out
    # the anti-double-count instruction is the point of the block
    assert "NOT independent corroboration" in out
    assert "count one source twice" in out
    assert "keep your own read" in out


def test_the_rubric_itself_carries_the_anti_double_count_rule():
    """The eval gate hashes _RUBRIC only. An instruction living solely in _build_judge_prompt
    would ship past the grade-surface gate unseen — the ADR 0030 blind spot."""
    assert "SECOND OPINION" in _RUBRIC
    assert "never as a vote" in _RUBRIC
    assert "count one source twice" in _RUBRIC


# ── the double-count telemetry ───────────────────────────────────────────────────────────
def _row(date, label, pplx, jg):
    return {"alert_date": date, "catalyst_quality": label, "gemini_validation": pplx,
            "judge_grade": jg, "judge_tier": "HIGH", "baseline_floor_tier": "HIGH",
            "judge_direction": "hold", "grounded_text": ""}


def test_only_disagreements_enter_the_double_count_cohort():
    """Agreement renders nothing, so it cannot double-count and must not dilute the rate."""
    agg = aggregate_judge_review([
        _row("2026-08-28", "strong", "strong", "strong"),      # agreed — out of scope
        _row("2026-08-28", "strong", "routine", "routine"),    # disagreed, judge sided
    ])
    assert agg["second_opinion"]["after"] == {"n": 1, "sided": 1}


def test_rows_without_a_judge_grade_are_unmeasurable_not_negative():
    """judge_grade is NULL before it was persisted. Those rows are not evidence the judge
    declined to side with the second model — they are simply not measurable."""
    agg = aggregate_judge_review([_row("2026-05-01", "strong", "routine", None)])
    assert agg["second_opinion"]["before"]["n"] == 0


def test_the_cohorts_split_on_the_day_the_block_went_live():
    before = str(int(_SECOND_OPINION_LIVE_FROM[:4])) + _SECOND_OPINION_LIVE_FROM[4:8] + "26"
    agg = aggregate_judge_review([
        _row(before, "strong", "routine", "routine"),
        _row(_SECOND_OPINION_LIVE_FROM, "strong", "routine", "routine"),
    ])
    assert agg["second_opinion"]["before"]["n"] == 1
    assert agg["second_opinion"]["after"]["n"] == 1


def test_the_digest_states_which_way_reads_as_double_counting():
    rows = [_row("2026-08-28", "strong", "routine", "routine") for _ in range(25)]
    rows += [_row("2026-08-01", "strong", "routine", "strong") for _ in range(25)]
    out = format_judge_review(aggregate_judge_review(rows), 30)
    assert "SECOND OPINION" in out
    assert "before it was told" in out and "after  it was told" in out
    assert "counts one source twice" in out
    assert "25/25 = 100%" in out and "0/25 = 0%" in out


def test_a_thin_cohort_is_labelled_unreadable():
    out = format_judge_review(aggregate_judge_review(
        [_row("2026-08-28", "strong", "routine", "routine")]), 30)
    assert "not yet readable" in out


def test_no_second_opinion_data_prints_no_section():
    out = format_judge_review(aggregate_judge_review(
        [_row("2026-08-28", "strong", "strong", "strong")]), 30)
    assert "SECOND OPINION" not in out
