"""#727 — an operator-promoted theme is not dissolved by ADR 0025 Arm A inside its 3-night window
(validation path + retro sweep). Outside the window / with no exemption set: today's behaviour."""
from __future__ import annotations

import json
from datetime import date

import pytest

from agents.market_intelligence import theme_engine

MONDAY = date(2026, 7, 13)  # validation runs Mon/Wed/Fri
PROMO = "Bitcoin Miners & AI/HPC Data-Center Pivot"
STOCKS = {
    "RIOT": {"ticker": "RIOT", "rs_composite": 85.0, "sector": "Financials"},
    "FIGR": {"ticker": "FIGR", "rs_composite": 82.0, "sector": "Financials"},
}


def _theme():
    return {"name": PROMO, "tickers": ["RIOT", "FIGR"], "score": 60,
            "stage": "Nascent", "description": "miners"}


def _exempt(left=None):
    return theme_engine.OperatorExempt(nights_left={PROMO: left} if left else {})


def _fake_client(remove_list):
    class _Block:
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


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("THEME_MERGE_ARM", "1")
    events, cooldowns = [], []

    async def fake_audit(event_type, summary, detail=None):
        events.append((event_type, summary))

    async def fake_cooldown(ticker, theme_name, reason=""):
        cooldowns.append((ticker, theme_name))
        return 1

    async def fake_history(name, days=7, tickers=None):
        return []

    async def fake_news(name, tickers=None):
        return 30, "desc", False

    async def fake_breadth(tickers, today):
        return 0.9

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    monkeypatch.setattr(theme_engine, "add_validation_cooldown", fake_cooldown)
    monkeypatch.setattr(theme_engine, "_get_theme_history", fake_history)
    monkeypatch.setattr(theme_engine, "_news_check", fake_news)
    monkeypatch.setattr(theme_engine, "get_ticker_breadth_above_sma20", fake_breadth)
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(["FIGR"]))
    return events, cooldowns


@pytest.mark.asyncio
async def test_a_in_window_pair_kept_with_audit_row(env):
    events, cooldowns = env
    result, changelog = await theme_engine._rescore_existing_theme(
        _theme(), STOCKS, MONDAY, protected=set(), operator_exempt=_exempt(2))
    assert result is not None and sorted(result["tickers"]) == ["FIGR", "RIOT"]
    rows = [e for e in events if e[0] == "theme_dissolve_operator_exempt"]
    assert len(rows) == 1 and "night 2 of 3" in rows[0][1] and "FIGR" in rows[0][1]
    assert not any(e[0] == "theme_dissolved_flagged_pair" for e in events)
    assert not any(c["type"] == "theme_dissolved_flagged_pair" for c in changelog)
    assert cooldowns == []


@pytest.mark.asyncio
async def test_a2_in_window_nothing_flagged_writes_no_row(env, monkeypatch):
    events, _ = env
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client([]))
    result, _cl = await theme_engine._rescore_existing_theme(
        _theme(), STOCKS, MONDAY, protected=set(), operator_exempt=_exempt(3))
    assert result is not None
    assert not any(e[0] == "theme_dissolve_operator_exempt" for e in events)


@pytest.mark.asyncio
async def test_b_window_over_dissolves_as_before(env):
    events, cooldowns = env
    result, changelog = await theme_engine._rescore_existing_theme(
        _theme(), STOCKS, MONDAY, protected=set(), operator_exempt=_exempt(None))
    assert result is None
    assert any(e[0] == "theme_dissolved_flagged_pair" for e in events)
    assert not any(e[0] == "theme_dissolve_operator_exempt" for e in events)
    assert ("FIGR", PROMO) in cooldowns


@pytest.mark.asyncio
async def test_d_operator_exempt_none_is_today(env):
    events, _ = env
    result, _cl = await theme_engine._rescore_existing_theme(
        _theme(), STOCKS, MONDAY, protected=set(), operator_exempt=None)
    assert result is None
    assert any(e[0] == "theme_dissolved_flagged_pair" for e in events)


@pytest.mark.asyncio
async def test_c_retro_sweep_skips_promoted_still_dissolves_others(env, monkeypatch):
    events, cooldowns = env

    async def fake_cooldown_set():
        return {("FIGR", PROMO), ("CAR", "Plain Pair")}

    monkeypatch.setattr(theme_engine, "get_cooldown_set", fake_cooldown_set)
    themes = [
        {"name": PROMO, "tickers": ["RIOT", "FIGR"], "stage": "Nascent"},
        {"name": "Plain Pair", "tickers": ["NVDA", "CAR"], "stage": "Nascent"},
    ]
    changelog: list[dict] = []
    out = await theme_engine._retro_sweep_flagged_pairs(themes, changelog, _exempt(1))
    assert [t["name"] for t in out] == [PROMO]
    assert [c[:2] for c in cooldowns] == [("CAR", "Plain Pair")]   # no cooldown refresh for promo
    rows = [e for e in events if e[0] == "theme_dissolve_operator_exempt"]
    assert len(rows) == 1 and "night 3 of 3" in rows[0][1]
    assert [c["theme"] for c in changelog] == ["Plain Pair"]


@pytest.mark.asyncio
async def test_c2_retro_sweep_none_dissolves(env, monkeypatch):
    async def fake_cooldown_set():
        return {("FIGR", PROMO)}

    monkeypatch.setattr(theme_engine, "get_cooldown_set", fake_cooldown_set)
    themes = [{"name": PROMO, "tickers": ["RIOT", "FIGR"], "stage": "Nascent"}]
    out = await theme_engine._retro_sweep_flagged_pairs(themes, [], None)
    assert out == []
