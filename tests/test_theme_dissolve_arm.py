"""ADR 0025 Arm A (#274) — dissolve-on-flagged-pair + retro-sweep, behind THEME_MERGE_ARM.

Covers the C1 card's test list:
  dissolve-on-removal-at-2 · survivor-released-no-cooldown · retro-sweep dissolves ·
  ≥3-member removal does NOT dissolve · cooldown rows written · toggle-OFF byte-identical
(the composes-with-merge case lives in test_theme_thesis_merge_pass.py).
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from agents.market_intelligence import theme_engine

MONDAY = date(2026, 7, 13)  # validation runs Mon/Wed/Fri


def _capture(monkeypatch):
    """Capture audit events + cooldown writes; silence external I/O."""
    events: list[tuple[str, str]] = []
    cooldowns: list[tuple[str, str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        events.append((event_type, summary))

    async def fake_cooldown(ticker, theme_name, reason=""):
        cooldowns.append((ticker, theme_name, reason))
        return 1

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    monkeypatch.setattr(theme_engine, "add_validation_cooldown", fake_cooldown)
    return events, cooldowns


def _fake_client(remove_list):
    class _Block:
        # `type` is REQUIRED on every fake block (#544): the real API always sets it, and
        # our reader now selects BY type instead of by position. A fake without it is a
        # shape production never produces — the exact "fabricated input proves nothing"
        # trap that let the 08-06 thinking-block outage through every existing test.
        type = "text"
        text = json.dumps({"remove": remove_list})

    class _Resp:
        content = [_Block()]
        stop_reason = "end_turn"

    class _Messages:
        async def create(self, *a, **kw):
            return _Resp()

    class _Client:
        messages = _Messages()

    return _Client()


STOCKS = {
    "NVDA": {"ticker": "NVDA", "rs_composite": 85.0, "sector": "Technology"},
    "CAR": {"ticker": "CAR", "rs_composite": 82.0, "sector": "Industrials"},
    "AMD": {"ticker": "AMD", "rs_composite": 80.0, "sector": "Technology"},
}


# ── in-run dissolve (validation path) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_dissolve_on_removal_at_2_real_validator(monkeypatch):
    """Arm ON: validation flags a member of a 2-member theme → the theme dissolves
    (rescore returns None), the FLAGGED member gets the 14d cooldown, the audit fires."""
    monkeypatch.setenv("THEME_MERGE_ARM", "1")
    events, cooldowns = _capture(monkeypatch)
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(["CAR"]))

    theme = {"name": "Semiconductors", "tickers": ["NVDA", "CAR"], "score": 60,
             "stage": "Nascent", "description": "chips"}
    result, changelog = await theme_engine._rescore_existing_theme(
        theme, STOCKS, MONDAY, protected=set())

    assert result is None                                     # dissolved
    assert ("CAR", "Semiconductors") in [(c[0], c[1]) for c in cooldowns]  # flagged cooled
    assert any(e[0] == "theme_dissolved_flagged_pair" for e in events)
    assert any(e[0] == "ticker_revalidated_out" for e in events)
    dissolve = [c for c in changelog if c["type"] == "theme_dissolved_flagged_pair"]
    assert dissolve and dissolve[0]["flagged"] == ["CAR"]
    assert dissolve[0]["survivors"] == ["NVDA"]


@pytest.mark.asyncio
async def test_survivor_released_without_cooldown(monkeypatch):
    """The survivor did nothing wrong: NO cooldown row for it (ADR 0025 Arm A)."""
    monkeypatch.setenv("THEME_MERGE_ARM", "1")
    _events, cooldowns = _capture(monkeypatch)
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(["CAR"]))

    theme = {"name": "Semiconductors", "tickers": ["NVDA", "CAR"], "score": 60,
             "stage": "Nascent", "description": "chips"}
    await theme_engine._rescore_existing_theme(theme, STOCKS, MONDAY, protected=set())

    cooled = {c[0] for c in cooldowns}
    assert cooled == {"CAR"}          # flagged only — never the survivor


@pytest.mark.asyncio
async def test_three_member_removal_does_not_dissolve(monkeypatch):
    """Narrow by design: the arm never dissolves a ≥3-member theme — a removal that
    would leave <2 still hits the min-survivor guard (removals skipped, all kept)."""
    monkeypatch.setenv("THEME_MERGE_ARM", "1")
    events, cooldowns = _capture(monkeypatch)
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(["CAR", "AMD"]))

    kept = await theme_engine._validate_theme_membership(
        "Semiconductors", ["NVDA", "CAR", "AMD"], [], protected=set(),
        dissolve_flagged_pair=True)

    assert kept == ["NVDA", "CAR", "AMD"]   # min-guard held
    assert cooldowns == []
    assert not any(e[0] == "ticker_revalidated_out" for e in events)


@pytest.mark.asyncio
async def test_toggle_off_two_member_kept_byte_identical(monkeypatch):
    """Toggle OFF = legacy behavior exactly: the flagged 2-member pair is KEPT by the
    min-survivor guard (no removal, no cooldown, no dissolve audit)."""
    monkeypatch.delenv("THEME_MERGE_ARM", raising=False)
    events, cooldowns = _capture(monkeypatch)
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(["CAR"]))

    async def fake_history(name, days=7, tickers=None):
        return []

    async def fake_news(name, tickers=None):
        return 30, "desc", False

    async def fake_breadth(tickers, today):
        return 0.9

    monkeypatch.setattr(theme_engine, "_get_theme_history", fake_history)
    monkeypatch.setattr(theme_engine, "_news_check", fake_news)
    monkeypatch.setattr(theme_engine, "get_ticker_breadth_above_sma20", fake_breadth)

    theme = {"name": "Semiconductors", "tickers": ["NVDA", "CAR"], "score": 60,
             "stage": "Nascent", "description": "chips"}
    result, _changelog = await theme_engine._rescore_existing_theme(
        theme, STOCKS, MONDAY, protected=set())

    assert result is not None                       # NOT dissolved
    assert sorted(result["tickers"]) == ["CAR", "NVDA"]   # pair intact (legacy guard)
    assert cooldowns == []
    assert not any(e[0] == "theme_dissolved_flagged_pair" for e in events)


# ── retro-sweep ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retro_sweep_dissolves_flagged_pair(monkeypatch):
    """A live (ticker, theme) validation cooldown on a member of an active 2-member
    theme = prior validation evidence → the sweep dissolves the theme, refreshes the
    flagged member's cooldown, leaves the survivor untouched."""
    monkeypatch.setenv("THEME_MERGE_ARM", "1")
    events, cooldowns = _capture(monkeypatch)

    async def fake_cooldown_set():
        return {("CAR", "Semiconductors")}

    monkeypatch.setattr(theme_engine, "get_cooldown_set", fake_cooldown_set)

    themes = [
        {"name": "Semiconductors", "tickers": ["NVDA", "CAR"], "stage": "Nascent"},
        {"name": "Healthy Theme", "tickers": ["A", "B", "C"], "stage": "Mainstream"},
    ]
    changelog: list[dict] = []
    swept = await theme_engine._retro_sweep_flagged_pairs(themes, changelog)

    assert [t["name"] for t in swept] == ["Healthy Theme"]   # dissolved from emission
    assert [(c[0], c[1]) for c in cooldowns] == [("CAR", "Semiconductors")]  # refreshed
    assert any(e[0] == "theme_dissolved_flagged_pair" for e in events)
    assert changelog and changelog[0]["via"] == "retro_sweep"
    assert changelog[0]["survivors"] == ["NVDA"]


@pytest.mark.asyncio
async def test_retro_sweep_ignores_unflagged_and_larger_themes(monkeypatch):
    """No evidence (no live cooldown from THAT theme) or ≥3 members → untouched."""
    monkeypatch.setenv("THEME_MERGE_ARM", "1")
    _events, cooldowns = _capture(monkeypatch)

    async def fake_cooldown_set():
        # AMD is cooled from a DIFFERENT theme; the 3-member theme has a flagged member
        return {("AMD", "Some Other Theme"), ("C", "Big Theme")}

    monkeypatch.setattr(theme_engine, "get_cooldown_set", fake_cooldown_set)

    themes = [
        {"name": "Clean Pair", "tickers": ["NVDA", "AMD"], "stage": "Nascent"},
        {"name": "Big Theme", "tickers": ["A", "B", "C"], "stage": "Mainstream"},
    ]
    swept = await theme_engine._retro_sweep_flagged_pairs(themes, [])

    assert [t["name"] for t in swept] == ["Clean Pair", "Big Theme"]
    assert cooldowns == []


@pytest.mark.asyncio
async def test_retro_sweep_noop_when_toggle_off(monkeypatch):
    """Toggle OFF → the sweep neither reads cooldowns nor touches the list."""
    monkeypatch.delenv("THEME_MERGE_ARM", raising=False)
    called = {"n": 0}

    async def fake_cooldown_set():
        called["n"] += 1
        return set()

    monkeypatch.setattr(theme_engine, "get_cooldown_set", fake_cooldown_set)
    themes = [{"name": "Semiconductors", "tickers": ["NVDA", "CAR"], "stage": "Nascent"}]
    swept = await theme_engine._retro_sweep_flagged_pairs(themes, [])

    assert swept is themes         # identical object — untouched
    assert called["n"] == 0        # no DB read when off
