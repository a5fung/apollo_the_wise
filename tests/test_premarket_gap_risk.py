"""ADR 0023 Card 5 — 9:00 ET pre-market gap-risk heads-up (read-only telemetry).
Pins: the Polygon price extraction, and that the scan alerts ONLY when an open
position's pre-market price is below its stop, per-account, labeled, no order action.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.conftest import make_mock_pool
import agents.market_intelligence.collector as collector
import agents.market_intelligence.briefing as briefing
import agents.market_intelligence.constants as constants


# ── collector.get_premarket_prices — extraction precedence + graceful failure ──
@pytest.mark.asyncio
async def test_get_premarket_prices_precedence(monkeypatch):
    snap = {"tickers": [
        {"ticker": "AAA", "min": {"c": 10.5}, "lastTrade": {"p": 9.0}},  # min.c wins
        {"ticker": "BBB", "lastTrade": {"p": 20.0}},                     # falls to lastTrade
        {"ticker": "CCC", "day": {"o": 30.0}},                          # falls to day.o
        {"ticker": "DDD"},                                             # no price → dropped
    ]}
    monkeypatch.setattr(collector, "_polygon_get", AsyncMock(return_value=snap))
    out = await collector.get_premarket_prices(["AAA", "BBB", "CCC", "DDD"])
    assert out == {"AAA": 10.5, "BBB": 20.0, "CCC": 30.0}


@pytest.mark.asyncio
async def test_get_premarket_prices_empty_and_graceful(monkeypatch):
    pg = AsyncMock(side_effect=RuntimeError("polygon down"))
    monkeypatch.setattr(collector, "_polygon_get", pg)
    assert await collector.get_premarket_prices([]) == {}   # no tickers → no call
    pg.assert_not_awaited()
    assert await collector.get_premarket_prices(["X"]) == {}  # error → graceful empty


# ── briefing.premarket_gap_risk_scan ──
def _wire_scan(monkeypatch, *, opens_by_mode, prices):
    pool, conn = make_mock_pool()
    # for mode in ['paper','live'] → conn.fetch(opens) per mode
    conn.fetch = AsyncMock(side_effect=[opens_by_mode["paper"], opens_by_mode["live"]])
    monkeypatch.setattr(briefing, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(briefing, "log_audit_event", AsyncMock())
    monkeypatch.setattr(constants, "active_account_modes", lambda: ["paper", "live"])
    monkeypatch.setattr(collector, "get_premarket_prices", AsyncMock(return_value=prices))
    sent = []
    monkeypatch.setattr(briefing, "send_telegram_message",
                        AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))
    return sent


def _pos(ticker, entry, stop, hold=2):
    return {"ticker": ticker, "entry_price": entry, "stop_price": stop,
            "remaining_shares": 100, "hold_days": hold}


@pytest.mark.asyncio
async def test_scan_alerts_when_premarket_below_stop(monkeypatch):
    # Live holds SYRE (stop 95); pre-market 83 → gap-through risk. Paper dormant.
    sent = _wire_scan(monkeypatch,
                      opens_by_mode={"paper": [], "live": [_pos("SYRE", 98.49, 95.0)]},
                      prices={"SYRE": 83.0})
    n = await briefing.premarket_gap_risk_scan()
    assert n == 1 and len(sent) == 1
    msg = sent[0]
    assert "💰 LIVE-$" in msg and "Gap-risk" in msg and "SYRE" in msg
    assert "83.00" in msg and "95.00" in msg and "BELOW stop" in msg


@pytest.mark.asyncio
async def test_scan_silent_when_premarket_above_stop(monkeypatch):
    sent = _wire_scan(monkeypatch,
                      opens_by_mode={"paper": [], "live": [_pos("AVAV", 100.0, 95.0)]},
                      prices={"AVAV": 101.0})  # holding above the stop
    n = await briefing.premarket_gap_risk_scan()
    assert n == 0 and sent == []


@pytest.mark.asyncio
async def test_scan_skips_when_no_premarket_quote(monkeypatch):
    sent = _wire_scan(monkeypatch,
                      opens_by_mode={"paper": [], "live": [_pos("WULF", 24.0, 23.0)]},
                      prices={})  # Polygon returned nothing for the ticker
    n = await briefing.premarket_gap_risk_scan()
    assert n == 0 and sent == []
