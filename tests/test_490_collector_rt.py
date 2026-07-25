"""#490 RT-1 — collector fetcher extensions (design §2.1/§3/§5).

`get_alpaca_snapshots_batch` gains: the date-keyed cross-check inputs (both daily bars +
timestamps), latest_quote fields (Q1 NBBO band), minute_ts (Q3 bar age), an optional
`concurrency` (default 1 = today's proven serial behavior) and a `stats` out-param (the
§5.3 rung-2 degrade evidence). All backward-compatible — existing callers pass nothing new
and read the same keys. Plus the §6.1 minute-volume batcher and the §2.2 splits reference.
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch
from zoneinfo import ZoneInfo

from agents.market_intelligence import collector

_ET = ZoneInfo("America/New_York")
_NOW = datetime(2026, 7, 24, 9, 40, 0, tzinfo=_ET)


def _fake_snapshot():
    ts = _NOW - timedelta(seconds=5)
    return NS(
        latest_trade=NS(price=12.0, timestamp=ts),
        minute_bar=NS(close=11.9, volume=40_000, timestamp=ts),
        daily_bar=NS(close=11.5, volume=1_000_000, timestamp=_NOW.replace(hour=0, minute=0)),
        previous_daily_bar=NS(close=10.0, volume=900_000,
                              timestamp=_NOW.replace(hour=0, minute=0) - timedelta(days=1)),
        latest_quote=NS(bid_price=11.95, ask_price=12.05, bid_size=3, ask_size=2, timestamp=ts),
    )


class _FakeSnapReq:
    """conftest stubs the alpaca modules with MagicMocks, so the real StockSnapshotRequest
    isn't constructible in tests — this stand-in records symbol_or_symbols like the real one."""

    def __init__(self, symbol_or_symbols=None, feed=None):
        self.symbol_or_symbols = symbol_or_symbols


class _FakeClient:
    calls = 0
    fail = False

    def __init__(self, api_key=None, secret_key=None):
        pass

    def get_stock_snapshot(self, req):
        _FakeClient.calls += 1
        if _FakeClient.fail:
            raise RuntimeError("boom")
        return {sym: _fake_snapshot() for sym in req.symbol_or_symbols}


def _env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_SECRET_KEY", raising=False)


def test_snapshot_batch_new_fields_and_stats(monkeypatch):
    _env(monkeypatch)
    _FakeClient.calls, _FakeClient.fail = 0, False
    stats: dict = {}
    with patch("alpaca.data.historical.StockHistoricalDataClient", _FakeClient), \
         patch("alpaca.data.requests.StockSnapshotRequest", _FakeSnapReq):
        out = asyncio.run(collector.get_alpaca_snapshots_batch(["AAA"], stats=stats))
    sn = out["AAA"]
    # pre-#490 keys unchanged
    assert sn["price"] == 12.0 and sn["prev_close"] == 10.0 and sn["minute_close"] == 11.9
    # #490 additions
    assert sn["daily_bar_close"] == 11.5 and sn["daily_bar_ts"] is not None
    assert sn["prev_daily_bar_ts"] is not None and sn["minute_ts"] is not None
    assert sn["bid"] == 11.95 and sn["ask"] == 12.05 and sn["quote_ts"] is not None
    assert stats == {"batches_total": 1, "batches_failed": 0}


def test_snapshot_batch_chunks_at_100_and_merges(monkeypatch):
    _env(monkeypatch)
    _FakeClient.calls, _FakeClient.fail = 0, False
    tickers = [f"T{i}" for i in range(250)]
    stats: dict = {}
    with patch("alpaca.data.historical.StockHistoricalDataClient", _FakeClient), \
         patch("alpaca.data.requests.StockSnapshotRequest", _FakeSnapReq):
        out = asyncio.run(collector.get_alpaca_snapshots_batch(
            tickers, stats=stats, concurrency=5))
    assert len(out) == 250
    assert stats == {"batches_total": 3, "batches_failed": 0}   # 100/100/50 — batch 100 (fork 5)
    assert _FakeClient.calls == 3


def test_snapshot_batch_total_failure_is_soft_and_counted(monkeypatch):
    _env(monkeypatch)
    _FakeClient.calls, _FakeClient.fail = 0, True
    stats: dict = {}
    with patch("alpaca.data.historical.StockHistoricalDataClient", _FakeClient), \
         patch("alpaca.data.requests.StockSnapshotRequest", _FakeSnapReq):
        out = asyncio.run(collector.get_alpaca_snapshots_batch(["AAA"], stats=stats))
    assert out == {}
    assert stats == {"batches_total": 1, "batches_failed": 1}


class _FakeBarsClient:
    def __init__(self, api_key=None, secret_key=None):
        pass

    def get_stock_bars(self, req):
        pm = NS(timestamp=_NOW.replace(hour=9, minute=15), volume=1_000)
        s1 = NS(timestamp=_NOW.replace(hour=9, minute=31), volume=2_000)
        s2 = NS(timestamp=_NOW.replace(hour=9, minute=35), volume=3_000)
        return NS(data={"AAA": [pm, s1, s2]})


def test_minute_cum_volumes_split_at_930(monkeypatch):
    _env(monkeypatch)
    with patch("alpaca.data.historical.StockHistoricalDataClient", _FakeBarsClient):
        out = asyncio.run(collector.get_alpaca_minute_cum_volumes(["AAA"], _NOW))
    assert out == {"AAA": {"pm_vol": 1_000, "session_vol": 5_000}}


def test_minute_cum_volumes_failure_is_empty(monkeypatch):
    _env(monkeypatch)

    class _Boom:
        def __init__(self, **kw):
            pass

        def get_stock_bars(self, req):
            raise RuntimeError("down")
    with patch("alpaca.data.historical.StockHistoricalDataClient", _Boom):
        out = asyncio.run(collector.get_alpaca_minute_cum_volumes(["AAA"], _NOW))
    assert out == {}


def test_splits_today_set_and_failure_none(monkeypatch):
    async def _get(path, params=None):
        assert path == "/v3/reference/splits" and params["execution_date"] == "2026-07-24"
        return {"results": [{"ticker": "XYZ"}, {"ticker": "ABC"}, {}]}
    monkeypatch.setattr(collector, "_polygon_get", _get)
    assert asyncio.run(collector.get_splits_today("2026-07-24")) == {"XYZ", "ABC"}

    async def _boom(path, params=None):
        raise RuntimeError("403")
    monkeypatch.setattr(collector, "_polygon_get", _boom)
    assert asyncio.run(collector.get_splits_today("2026-07-24")) is None
