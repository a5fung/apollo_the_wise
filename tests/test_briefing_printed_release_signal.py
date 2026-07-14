"""Fix-2b (2026-07-14) — already-printed scheduled-release signal in the brief.

The 2026-07 CPI miss: CPI printed 8:30 AM ET and moved the market, but a
Perplexity timeout blanked the overnight summary → the brief said "no clear
catalyst" while its own CALENDAR section showed "8:30 AM ET — CPI". The fix
derives a deterministic "this release ALREADY printed" driver signal from the
calendar the brief already fetched — (a) threaded into the overnight-news
prompt, (b) appended to the OVERNIGHT section as a determined-from-data line
that survives full Perplexity degradation. Happy path (no printed high-impact
release): everything is byte-identical to before.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import agents.market_intelligence.briefing as briefing

_ET = ZoneInfo("America/New_York")
# Brief send time: 9:00 AM ET — after the 8:30 print, before the 10:00/2:00 ones.
_NOW = datetime(2026, 7, 14, 9, 0, tzinfo=_ET)

_CAL = "\n".join([
    "• 8:30 AM ET — CPI (Consumer Price Index, June)",
    "• 10:00 AM ET — Consumer Sentiment (Michigan, prelim)",
    "• 2:00 PM ET — FOMC Minutes",
])


# ── _already_printed_releases: the deterministic parser ──────────────────────

def test_printed_high_impact_release_detected():
    out = briefing._already_printed_releases(_CAL, now_et=_NOW)
    assert len(out) == 1
    assert "CPI" in out[0]
    assert "8:30 AM ET" in out[0]


def test_future_releases_not_flagged():
    # 10:00 AM and 2:00 PM haven't printed at 9:00 AM — must not be flagged
    # (they haven't moved the market yet).
    out = briefing._already_printed_releases(_CAL, now_et=_NOW)
    assert not any("FOMC" in l or "Sentiment" in l for l in out)


def test_pm_release_flagged_after_it_prints():
    # AM/PM math: at 2:30 PM ET the FOMC minutes HAVE printed.
    later = datetime(2026, 7, 14, 14, 30, tzinfo=_ET)
    out = briefing._already_printed_releases(_CAL, now_et=later)
    assert any("FOMC" in l for l in out)


def test_non_high_impact_printed_release_skipped():
    # Printed but not tape-moving → no driver line (keeps the signal curated).
    out = briefing._already_printed_releases(
        "• 8:00 AM ET — Wholesale Inventories", now_et=_NOW)
    assert out == []


def test_no_calendar_or_bare_time_lines_yield_no_signal():
    assert briefing._already_printed_releases(None, now_et=_NOW) == []
    assert briefing._already_printed_releases("", now_et=_NOW) == []
    # time with no parseable high-impact event → skipped (conservative)
    assert briefing._already_printed_releases("• 8:30 AM ET —", now_et=_NOW) == []
    # event with no parseable ET time → skipped (can't tell if it printed)
    assert briefing._already_printed_releases("• CPI sometime today", now_et=_NOW) == []


# ── _append_printed_release_line: the Perplexity-independent brief line ──────

def test_append_creates_section_when_perplexity_fully_degraded():
    # news=None AND snapshot empty → section would be absent; the printed-
    # release signal must still reach the operator.
    out = briefing._append_printed_release_line(None, ["8:30 AM ET — CPI (June)"])
    assert out is not None and out.startswith("*OVERNIGHT*")
    assert "Data printed" in out and "CPI" in out


def test_append_preserves_existing_section():
    section = "*OVERNIGHT*\n  SPY *-1.0%*  |  QQQ *-1.4%*"
    out = briefing._append_printed_release_line(section, ["8:30 AM ET — CPI"])
    assert out.startswith(section)          # existing content untouched
    assert "Data printed" in out


def test_no_printed_releases_is_a_noop():
    # Happy-path preservation: nothing printed → section returned unchanged.
    section = "*OVERNIGHT*\n  SPY *-1.0%*"
    assert briefing._append_printed_release_line(section, []) == section
    assert briefing._append_printed_release_line(None, []) is None


# ── _get_overnight_news: the prompt-input thread ─────────────────────────────

@pytest.mark.asyncio
async def test_overnight_news_query_carries_printed_release(monkeypatch):
    captured: dict = {}

    async def _fake_search(query, recency="day", system_prompt=None):
        captured["query"] = query
        return "CPI came in hot; indexes sold off."

    monkeypatch.setattr(briefing, "search_news_perplexity", _fake_search)

    out = await briefing._get_overnight_news(
        None, printed_releases=["8:30 AM ET — CPI (June)"])

    assert "ALREADY" in captured["query"] and "CPI" in captured["query"]
    assert out and "CPI" in out


@pytest.mark.asyncio
async def test_triggered_movers_query_also_carries_printed_release(monkeypatch):
    captured: dict = {}

    async def _fake_search(query, recency="day", system_prompt=None):
        captured["query"] = query
        return "CPI came in hot; indexes sold off."

    monkeypatch.setattr(briefing, "search_news_perplexity", _fake_search)

    snapshot = [{"name": "SPY", "pct_change": -1.5, "triggered": True}]
    await briefing._get_overnight_news(
        snapshot, printed_releases=["8:30 AM ET — CPI (June)"])

    assert "SPY down 1.5%" in captured["query"]      # movers branch intact
    assert "CPI" in captured["query"]                # release signal threaded


@pytest.mark.asyncio
async def test_overnight_news_query_unchanged_without_releases(monkeypatch):
    # Happy-path preservation: no printed releases → the query carries no
    # release note (byte-identical prompt to the pre-fix behavior).
    captured: dict = {}

    async def _fake_search(query, recency="day", system_prompt=None):
        captured["query"] = query
        return "Bounce after Friday's selloff; no fresh catalyst."

    monkeypatch.setattr(briefing, "search_news_perplexity", _fake_search)

    await briefing._get_overnight_news(None)

    assert "ALREADY" not in captured["query"]
    assert "economic releases" not in captured["query"]
