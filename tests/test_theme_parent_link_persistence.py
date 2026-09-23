"""#471 — sub-theme `parent_theme` must survive daily saves for as long as the
parent still exists (and must still clear on a genuine orphan).

Root cause (verified against prod, 2026-07-24): `_rescore_existing_theme`
rebuilds each theme dict from scratch every night and never copied
`parent_theme` forward from the loaded `existing` row — so a child's link to
its parent survived exactly one day (the birth-day write) and went NULL on
every save after that, even though nothing about the relationship changed
(evidence: "Cyber Exposure Management & Vulnerability Assessment" born
2026-07-17 under "Network Security & Zero-Trust Edge", parent_theme NULL on
every row from 2026-07-20 onward).

Two fix points, both covered here:
  1. `_rescore_existing_theme` (both return branches) now carries
     `theme.get("parent_theme")` forward.
  2. `_restore_sub_theme_links` (new) is the final reconciliation step run in
     `run_theme_engine` right before `_save_themes` — it (re)sets the link
     when the parent is still present in today's final snapshot, and clears
     it when the parent is genuinely gone (preserving the pre-existing
     orphan-clearing contract from `_emit_pipeline_diagnostic`).

Run: pytest tests/test_theme_parent_link_persistence.py -v
"""
from __future__ import annotations

from datetime import date

import pytest

from agents.market_intelligence import theme_engine

# Tuesday — outside the Mon/Wed/Fri validation/refresh cadence, so rescore
# takes the plain re-score path with no LLM validation call needed.
TUESDAY = date(2026, 7, 21)

PARENT_NAME = "Network Security & Zero-Trust Edge"
CHILD_NAME = "Cyber Exposure Management & Vulnerability Assessment"

STRONG_STOCKS = {
    "TENB": {"ticker": "TENB", "rs_composite": 85.0, "sector": "Technology"},
    "RPD": {"ticker": "RPD", "rs_composite": 82.0, "sector": "Technology"},
    "QLYS": {"ticker": "QLYS", "rs_composite": 80.0, "sector": "Technology"},
}

WEAK_STOCKS = {
    "TENB": {"ticker": "TENB", "rs_composite": 10.0, "sector": "Technology"},
    "RPD": {"ticker": "RPD", "rs_composite": 8.0, "sector": "Technology"},
    "QLYS": {"ticker": "QLYS", "rs_composite": 5.0, "sector": "Technology"},
}


def _quiet_rescore_io(monkeypatch):
    """Silence the DB/network calls `_rescore_existing_theme` makes on its
    plain (non-validation) path — mirrors the pattern in
    test_theme_dissolve_arm.py::test_toggle_off_two_member_kept_byte_identical."""

    async def fake_history(name, days=7, tickers=None):
        return []

    async def fake_news(name, tickers=None):
        return 30, "existing description", False

    async def fake_breadth(tickers, today):
        return 0.9

    async def fake_rs_batch(tickers, today, days=3):
        # #368: the prune paths now fetch trajectory history for sub-floor
        # members; empty history = fail-conservative (prune exactly as before).
        return {}

    monkeypatch.setattr(theme_engine, "_get_theme_history", fake_history)
    monkeypatch.setattr(theme_engine, "_news_check", fake_news)
    monkeypatch.setattr(theme_engine, "get_ticker_breadth_above_sma20", fake_breadth)
    monkeypatch.setattr(theme_engine, "get_recent_rs_batch", fake_rs_batch)


# ── Fix point 1: _rescore_existing_theme carries parent_theme forward ────────

@pytest.mark.asyncio
async def test_rescore_carries_parent_theme_forward_main_path(monkeypatch):
    """Day-2 rescore of a healthy (non-Fading) child must keep parent_theme —
    this is the exact dict that flows into `_save_themes`. Fails on pre-fix
    code: the returned dict has no 'parent_theme' key at all, so .get() is None."""
    _quiet_rescore_io(monkeypatch)

    child_yesterday = {
        "name": CHILD_NAME,
        "tickers": list(STRONG_STOCKS.keys()),
        "score": 72.5,
        "stage": "Mainstream",
        "description": "existing description",
        "parent_theme": PARENT_NAME,
    }
    result, _changelog = await theme_engine._rescore_existing_theme(
        child_yesterday, STRONG_STOCKS, TUESDAY, protected=set())

    assert result is not None
    assert result.get("parent_theme") == PARENT_NAME


@pytest.mark.asyncio
async def test_rescore_carries_parent_theme_forward_fading_path(monkeypatch):
    """Same carry-forward on the early Fading-branch return (the theme's own
    stocks went weak, but it hasn't retired yet) — a separate return point in
    the same function, patched separately."""
    _quiet_rescore_io(monkeypatch)

    child_yesterday = {
        "name": CHILD_NAME,
        "tickers": list(WEAK_STOCKS.keys()),
        "score": 40.0,
        "stage": "Fading",
        "description": "existing description",
        "parent_theme": PARENT_NAME,
    }
    result, _changelog = await theme_engine._rescore_existing_theme(
        child_yesterday, WEAK_STOCKS, TUESDAY, protected=set())

    assert result is not None
    assert result["stage"] == "Fading"
    assert result.get("parent_theme") == PARENT_NAME


# ── Fix point 2: _restore_sub_theme_links (final reconciliation) ────────────

def test_restore_sub_theme_links_survives_when_parent_present():
    """A child's parent_theme (re)set when the parent made it into today's
    final snapshot — this is what actually reaches _save_themes."""
    themes = [
        {"name": CHILD_NAME, "stage": "Mainstream", "tickers": ["TENB"],
         "parent_theme": None},  # simulates the pre-fix rescore dropping it
        {"name": PARENT_NAME, "stage": "Mainstream", "tickers": ["CRWD", "OKTA"]},
    ]
    theme_engine._restore_sub_theme_links(themes, {CHILD_NAME: PARENT_NAME})

    child = next(t for t in themes if t["name"] == CHILD_NAME)
    assert child["parent_theme"] == PARENT_NAME


def test_restore_sub_theme_links_clears_genuine_orphan():
    """Preserve the genuine orphan-clearing behavior: if the parent really is
    gone from today's final snapshot (retired/merged away), the link clears —
    it must NOT be resurrected just because sub_theme_parents still mentions it."""
    themes = [
        {"name": CHILD_NAME, "stage": "Mainstream", "tickers": ["TENB"],
         "parent_theme": PARENT_NAME},
        # PARENT_NAME is absent — dropped this run (merge/cap/retirement).
    ]
    theme_engine._restore_sub_theme_links(themes, {CHILD_NAME: PARENT_NAME})

    child = next(t for t in themes if t["name"] == CHILD_NAME)
    assert child["parent_theme"] is None


def test_restore_sub_theme_links_ignores_retired_rows():
    """Retired rows carry a deliberate successor pointer in `parent_theme`
    (theme_auto_retired) — never a sub-theme link. Must not be clobbered even
    if the retired name happens to collide with a sub_theme_parents key."""
    themes = [
        {"name": CHILD_NAME, "stage": "Retired", "tickers": [],
         "parent_theme": "Some Successor Theme"},
    ]
    theme_engine._restore_sub_theme_links(themes, {CHILD_NAME: PARENT_NAME})

    child = themes[0]
    assert child["parent_theme"] == "Some Successor Theme"


def test_restore_sub_theme_links_noop_when_no_map():
    """Empty sub_theme_parents (no sub-theme relationships at all) touches
    nothing — cheap no-op on the common (no-sub-themes) day."""
    themes = [{"name": "Solo Theme", "stage": "Mainstream", "tickers": ["A"]}]
    theme_engine._restore_sub_theme_links(themes, {})
    assert "parent_theme" not in themes[0]
