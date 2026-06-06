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


def test_excluded_categories_are_all_structural():
    # The gaps query excludes _UNTRADEABLE_CATEGORIES; every one must be the
    # 'structural' kind, else a real gap could be silently dropped.
    for cat in _UNTRADEABLE_CATEGORIES:
        assert _CATEGORY_KIND.get(cat) == "structural", cat


def test_safeguard_blocks_are_not_excluded():
    # The FTNT/INOD class (#199 entry-pipeline blocks) must NOT be in the
    # structural exclusion — they are the headline gaps.
    for cat in ("cap_blocked", "breaker_blocked", "window_missed",
                "stop_too_wide", "high_unentered"):
        assert cat not in _UNTRADEABLE_CATEGORIES


def test_missed_section_prepends_gaps():
    missed = {"window_days": 7, "top_winners": [], "by_category": [],
              "gaps": [_gap("INOD", "breaker_blocked", 0.25, 0.20)]}
    out = format_missed_section_for_weekly(missed)
    assert out.startswith("🚨")        # gaps section leads the digest
    assert "INOD" in out
    assert "Circuit breaker" in out


def test_missed_section_blank_when_nothing():
    assert format_missed_section_for_weekly({"window_days": 7}) == ""
