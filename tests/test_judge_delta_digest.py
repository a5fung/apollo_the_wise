"""Regression tests for the EP Judge delta digest formatter (#240 / W3, 2026-06-09).

The PUSH complement to the pull-only judge_delta_review.py — once a day the names
the holistic judge moved up/down vs the floor go to Telegram. These pin the message
formatting (arrows, floor→judge tier, materiality, the shadow-vs-load-bearing subtitle).
The job's DB-query + Telegram-send shell is exercised by the prod scan; the pure
formatter is what bugs (markdown/escaping, count, cap) live in.
"""
# Alpaca SDK + backtester.filters stubbing handled by tests/conftest.py.
from agents.market_intelligence.scheduler import _build_judge_delta_message


def _row(ticker, direction, floor="MODERATE", judge="HIGH", mat="material", gap=12.0,
         rationale="reason"):
    return {"ticker": ticker, "judge_direction": direction, "baseline_floor_tier": floor,
            "judge_tier": judge, "judge_materiality_tier": mat, "gap_pct": gap,
            "judge_rationale": rationale}


def test_header_counts_promotes_and_demotes():
    rows = [_row("AAA", "promote"), _row("BBB", "demote", floor="HIGH", judge="none"),
            _row("CCC", "demote", floor="HIGH", judge="none")]
    msg = _build_judge_delta_message(rows, authority_on=False, date_str="Jun 09")
    assert "▲1 ▼2" in msg.splitlines()[0]
    assert "Jun 09" in msg


def test_shadow_vs_loadbearing_subtitle():
    rows = [_row("AAA", "promote")]
    shadow = _build_judge_delta_message(rows, authority_on=False, date_str="Jun 09")
    live = _build_judge_delta_message(rows, authority_on=True, date_str="Jun 09")
    assert "drives nothing" in shadow
    assert "DROVE the paper grade" in live


def test_row_shows_arrow_tiers_and_materiality():
    msg = _build_judge_delta_message([_row("NRIX", "promote", floor="MODERATE",
                                           judge="HIGH", mat="transformative", gap=18.5)],
                                     authority_on=False, date_str="Jun 09")
    assert "▲ `NRIX` MODERATE→HIGH" in msg
    assert "mat=transformative" in msg
    assert "+18.5%" in msg


def test_demote_uses_down_arrow():
    msg = _build_judge_delta_message([_row("BIGCO", "demote", floor="HIGH", judge="none",
                                           mat="immaterial")],
                                     authority_on=False, date_str="Jun 09")
    assert "▼ `BIGCO` HIGH→none" in msg


def test_null_materiality_and_gap_are_safe():
    msg = _build_judge_delta_message([_row("X", "promote", mat=None, gap=None)],
                                     authority_on=False, date_str="Jun 09")
    assert "mat=n/a" in msg and "+0.0%" in msg


def test_caps_at_15_with_overflow_note():
    rows = [_row(f"T{i:02d}", "promote") for i in range(20)]
    msg = _build_judge_delta_message(rows, authority_on=False, date_str="Jun 09")
    # 15 rendered ticker lines + overflow note
    assert "…+5 more" in msg
    assert sum(1 for ln in msg.splitlines() if ln.startswith("▲ `T")) == 15


def test_rationale_truncated_to_140():
    long = "z" * 300
    msg = _build_judge_delta_message([_row("X", "promote", rationale=long)],
                                     authority_on=False, date_str="Jun 09")
    rline = [ln for ln in msg.splitlines() if ln.strip().startswith("_z")][0]
    assert len(rline.strip().strip("_")) == 140
