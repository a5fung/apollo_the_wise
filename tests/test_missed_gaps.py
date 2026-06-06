"""Tests for the #219 'should've-entered gaps' weekly section (2026-06-06).

The verified-first cohort = NON-structural misses. The DB query excludes
_UNTRADEABLE_CATEGORIES, so those MUST all be the 'structural' kind for
"non-structural == a gap" to hold. The formatter surfaces facts only.
"""
from __future__ import annotations

from datetime import date

from agents.market_intelligence.missed_outcomes import (
    format_gaps_section_for_weekly,
    format_missed_section_for_weekly,
    _UNTRADEABLE_CATEGORIES,
    _SHOULDVE_ENTERED_CATEGORIES,
    _CATEGORY_KIND,
)


def _gap(tk, cat, peak, ret5=None, d=date(2026, 5, 7)):
    return {"ticker": tk, "alert_date": d, "skip_category": cat,
            "max_high_5d": peak, "ret_5d": ret5}


def test_gaps_section_renders_reason_and_peak():
    out = format_gaps_section_for_weekly([_gap("FTNT", "cap_blocked", 0.18, 0.12)])
    assert "Should've-entered gaps" in out
    assert "FTNT" in out
    assert "Max positions" in out      # humanized verified reason
    assert "+18%" in out               # peak missed upside


def test_gaps_section_empty_returns_blank():
    assert format_gaps_section_for_weekly([]) == ""


def test_untradeable_equals_structural_kinds():
    # Bidirectional: _UNTRADEABLE_CATEGORIES must be EXACTLY the 'structural'
    # kinds in _CATEGORY_KIND. One-directional ("each untradeable is structural")
    # misses the drift that bites — a NEW structural category added to the kind
    # map but forgotten in _UNTRADEABLE would silently surface as a tradeable
    # miss. Lock both directions. (Altitude /simplify finding 2026-06-06.)
    structural = {c for c, k in _CATEGORY_KIND.items() if k == "structural"}
    assert set(_UNTRADEABLE_CATEGORIES) == structural


def test_safeguard_blocks_are_the_cohort():
    # The FTNT/INOD class (#199 entry-pipeline blocks) IS the should've-entered
    # cohort (the query filters skip_category IN _SHOULDVE_ENTERED_CATEGORIES).
    for cat in ("cap_blocked", "breaker_blocked", "window_missed",
                "stop_too_wide", "high_unentered"):
        assert cat in _SHOULDVE_ENTERED_CATEGORIES
        assert cat not in _UNTRADEABLE_CATEGORIES


def test_filter_rejections_excluded_from_cohort():
    # The micro-cap-rocket noise (filter said no on a name we don't trade) must
    # NOT be in the cohort — flat-ranking those by peak buried FTNT/INOD (the
    # 6/6 probe caught this). They live in the by-category roll-up instead.
    for cat in ("pm_rvol_low", "session_rvol_low", "outside_top20",
                "score_below_50", "catalyst_downgrade", "mcap_low", "adv_low"):
        assert cat not in _SHOULDVE_ENTERED_CATEGORIES


def test_missed_section_prepends_gaps():
    missed = {"window_days": 7, "top_winners": [], "by_category": [],
              "gaps": [_gap("INOD", "breaker_blocked", 0.25, 0.20)]}
    out = format_missed_section_for_weekly(missed)
    assert out.startswith("🚨")        # gaps section leads the digest
    assert "INOD" in out
    assert "Circuit breaker" in out


def test_missed_section_blank_when_nothing():
    assert format_missed_section_for_weekly({"window_days": 7}) == ""
