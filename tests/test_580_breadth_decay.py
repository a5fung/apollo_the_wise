"""#580 (2026-10-03) — the breadth-decay rule reads a stored 0% as 0%, not as "healthy".

`_rescore_existing_theme` forces a theme to Fading when its breadth (share of members above their
20-day average) is below `_BREADTH_DECAY_THRESHOLD` (0.40) two nights running. The prior night's
reading was read as `(prev or 1.0) < 0.40`: a stored 0.0 — every member broken down, the worst
possible reading — is falsy, so it became 1.0 and the theme could never fade. On 2026-09-29, 9
Mainstream themes sat at exactly 0% and their members still collected the EP +10.

Contract pinned here:
  * prev 0.0 + today below the bar  -> forced Fading       (RED on the pre-fix code)
  * prev None (never measured)      -> NOT forced (today's behaviour, unchanged)
  * prev at/above the bar           -> NOT forced (unchanged)
  * prev below the bar, non-zero    -> forced (unchanged — the case that always worked)

No DB, no network: every I/O seam `_rescore_existing_theme` touches on its plain Tuesday path is
replaced (the pattern from test_theme_parent_link_persistence.py).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from agents.market_intelligence import theme_engine as te

TUESDAY = date(2026, 9, 29)   # not Mon/Wed/Fri: no validation or description refresh
NAME = "Precious Metals Miners Velocity Breakout"
TICKERS = ["AEM", "KGC", "NEM"]
STOCKS = {
    "AEM": {"ticker": "AEM", "rs_composite": 90.0, "sector": "Basic Materials"},
    "KGC": {"ticker": "KGC", "rs_composite": 88.0, "sector": "Basic Materials"},
    "NEM": {"ticker": "NEM", "rs_composite": 86.0, "sector": "Basic Materials"},
}
# Names members, so the description-quality cap (#125) never interferes with the stage.
DESC = "Gold miners AEM, KGC and NEM breaking out on bullion strength."


def _wire(monkeypatch, today_breadth):
    """Replace the rescore's I/O. Five prior rows at the theme's own score, so the RS rule
    alone yields Mainstream (age >= 5, score >= 50, smoothed delta ~0) — the breadth override
    is then the ONLY thing that can move the stage."""
    events: list[tuple] = []

    async def fake_history(name, days=7, tickers=None):
        return [{"name": name, "score": 74.0, "theme_date": TUESDAY - timedelta(days=i + 1)}
                for i in range(5)]

    async def fake_news(name, tickers=None):
        return 30, DESC, False

    async def fake_breadth(tickers, today):
        return today_breadth

    async def fake_rs_batch(tickers, today, days=3):
        return {}

    async def fake_audit(event_type, summary="", detail=None, *a, **k):
        events.append((event_type, summary))

    monkeypatch.setattr(te, "_get_theme_history", fake_history)
    monkeypatch.setattr(te, "_news_check", fake_news)
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20", fake_breadth)
    monkeypatch.setattr(te, "get_recent_rs_batch", fake_rs_batch)
    monkeypatch.setattr(te, "log_audit_event", fake_audit)
    return events


def _yesterday(prev_breadth):
    return {"name": NAME, "tickers": list(TICKERS), "score": 74.0, "stage": "Mainstream",
            "description": DESC, "pct_above_20sma": prev_breadth}


async def _rescore(monkeypatch, *, prev, today):
    events = _wire(monkeypatch, today)
    result, changelog = await te._rescore_existing_theme(
        _yesterday(prev), STOCKS, TUESDAY, protected=set())
    assert result is not None
    return result, changelog, events


@pytest.mark.asyncio
async def test_580_zero_breadth_two_nights_fades_the_theme(monkeypatch):
    """THE BUG: 0% last night and 0% tonight is two nights below 0.40. Pre-fix this stayed
    Mainstream (0.0 read as 1.0) and kept paying the EP +10."""
    result, changelog, events = await _rescore(monkeypatch, prev=0.0, today=0.0)
    assert result["stage"] == "Fading"
    assert result["pct_above_20sma"] == 0.0
    assert any(e[0] == "theme_breadth_fade" for e in events)
    assert any(c.get("type") == "stage_change" and c["new_stage"] == "Fading" for c in changelog)


@pytest.mark.asyncio
async def test_580_zero_last_night_and_low_tonight_fades(monkeypatch):
    """0% last night, 33% tonight (one of three back above its average) — still two nights
    below 0.40, the shape 'Cloud Data Storage' had on 09-29."""
    result, _, _ = await _rescore(monkeypatch, prev=0.0, today=0.333)
    assert result["stage"] == "Fading"


@pytest.mark.asyncio
async def test_580_none_prior_breadth_keeps_todays_behaviour(monkeypatch):
    """None = never measured (a newborn row before the birth fill, or a lookup that found no
    scored member). It does not count as a night below the bar — exactly as before the fix."""
    result, _, events = await _rescore(monkeypatch, prev=None, today=0.0)
    assert result["stage"] == "Mainstream"
    assert not any(e[0] == "theme_breadth_fade" for e in events)


@pytest.mark.asyncio
async def test_580_missing_prior_key_keeps_todays_behaviour(monkeypatch):
    """A prior row dict with no breadth key at all is the same as None."""
    events = _wire(monkeypatch, 0.0)
    theme = _yesterday(None)
    del theme["pct_above_20sma"]
    result, _ = await te._rescore_existing_theme(theme, STOCKS, TUESDAY, protected=set())
    assert result["stage"] == "Mainstream"
    assert not any(e[0] == "theme_breadth_fade" for e in events)


@pytest.mark.asyncio
async def test_580_healthy_prior_does_not_fade(monkeypatch):
    """One bad night is not two: prior at the bar (0.40 is NOT below it) or above."""
    for prev in (0.40, 0.9):
        result, _, _ = await _rescore(monkeypatch, prev=prev, today=0.0)
        assert result["stage"] == "Mainstream", prev


@pytest.mark.asyncio
async def test_580_nonzero_low_prior_still_fades(monkeypatch):
    """The case that always worked (0 < prev < 0.40) is unchanged."""
    result, _, _ = await _rescore(monkeypatch, prev=0.2, today=0.25)
    assert result["stage"] == "Fading"


@pytest.mark.asyncio
async def test_580_tonight_unknown_never_fades(monkeypatch):
    """Tonight's breadth None (no member scored on the date) never forces anything,
    whatever last night said."""
    result, _, _ = await _rescore(monkeypatch, prev=0.0, today=None)
    assert result["stage"] == "Mainstream"
