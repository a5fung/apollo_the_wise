"""#564 — `score_single_ticker` must not persist a `mi_stock_scores` row dated a day
the market never traded.

THE BUG: `score_single_ticker` (rs_engine.py) defaulted `today = trade_date or et_today()`
and then wrote `db_record["score_date"] = today` unconditionally. A one-off ad-hoc lookup
(`/setup TICKER`, a natural-language ticker mention, etc.) run on a weekend therefore
PERSISTED a real row dated that Saturday/Sunday. Measured on prod: OKTA 2026-05-30, RACE
2026-07-05, CRCL 2026-07-12, FIGS 2026-08-08 — every one a weekend, every one exactly 1 row.
The FIGS row made 2026-08-08 look like a trading session to a downstream date-window query
in the evening brief and silently blanked a signal line.

THE FIX: compute the score and return it either way (so `/setup TICKER` etc. keep working),
but only call `upsert_stock_score` / `upsert_tracked_stock` when `today == last_trading_day
(today)`. Anchoring the write to the last real session instead was considered and rejected:
`upsert_stock_score`'s ON CONFLICT clause overwrites EVERY column (including sector/adv_20/
market_cap) from `EXCLUDED`, and this on-demand path always sets those three to None — writing
onto the real session's existing row would silently blank fields a legitimate nightly run
populated. Not persisting is strictly safer.

These tests pin: a weekend lookup computes a score but writes nothing; a normal weekday lookup
(a real trading day) persists exactly as before.
"""
from datetime import date

import pytest

import agents.market_intelligence.db as db_mod
import agents.market_intelligence.rs_engine as rs_engine_mod
from agents.market_intelligence import rs_engine

# 2026-08-08 is the real Saturday from the FIGS incident (PLAN.md #564).
_SATURDAY = date(2026, 8, 8)
_FRIDAY = date(2026, 8, 7)  # the last real trading day before it


class _FakeConn:
    """Serves the two direct `conn.fetch` calls inside score_single_ticker — the
    per-ticker raw-return distribution and the composite-rank distribution."""

    def __init__(self, existing_rows, composite_rows):
        self._existing_rows = existing_rows
        self._composite_rows = composite_rows

    async def fetch(self, query, *args):
        if "raw_1m" in query:
            return self._existing_rows
        if "rs_composite" in query:
            return self._composite_rows
        return []


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


def _setup(monkeypatch):
    """Wire score_single_ticker's deps so it reaches the persist decision without a
    real DB or API call, and record every persist-call it attempts."""
    closes = {
        "ABCD": {
            "2026-08-07": 105.0,  # Friday close — the real session, found via lookback
            "2026-08-06": 104.0,
            "2026-08-05": 103.0,
            "2026-08-04": 102.0,
        }
    }

    async def _fake_closes(start, end):
        return closes

    monkeypatch.setattr(db_mod, "get_daily_closes_all", _fake_closes)

    existing_rows = [{"ticker": "ABCD", "raw_1m": 5.0, "raw_3m": 8.0, "raw_6m": 12.0}]
    composite_rows = [{"rs_composite": 60.0}]
    fake_conn = _FakeConn(existing_rows, composite_rows)

    async def _fake_get_pool():
        return _FakePool(fake_conn)

    monkeypatch.setattr(rs_engine_mod, "get_pool", _fake_get_pool)

    async def _fake_latest_complete(conn, on_or_before=None, on_or_after=None):
        return _FRIDAY  # the last real (complete) trading day either way

    monkeypatch.setattr(rs_engine_mod, "latest_complete_score_date", _fake_latest_complete)

    persisted: dict[str, list] = {"scores": [], "tracked": []}

    async def _fake_upsert_stock_score(record):
        persisted["scores"].append(record)

    async def _fake_upsert_tracked_stock(ticker, today, rs_score):
        persisted["tracked"].append((ticker, today, rs_score))

    monkeypatch.setattr(rs_engine_mod, "upsert_stock_score", _fake_upsert_stock_score)
    monkeypatch.setattr(rs_engine_mod, "upsert_tracked_stock", _fake_upsert_tracked_stock)
    return persisted


@pytest.mark.asyncio
async def test_weekend_lookup_computes_score_but_does_not_persist(monkeypatch):
    persisted = _setup(monkeypatch)

    result = await rs_engine.score_single_ticker("ABCD", trade_date=_SATURDAY)

    assert "error" not in result
    assert result["rs_composite"] is not None  # the lookup itself still works
    # THE FIX: no row written for the day the market never traded.
    assert persisted["scores"] == []
    assert persisted["tracked"] == []


@pytest.mark.asyncio
async def test_weekday_lookup_on_a_real_session_persists_unchanged(monkeypatch):
    persisted = _setup(monkeypatch)

    result = await rs_engine.score_single_ticker("ABCD", trade_date=_FRIDAY)

    assert "error" not in result
    # A normal ad-hoc lookup on a real trading day is UNCHANGED by this fix.
    assert len(persisted["scores"]) == 1
    assert persisted["scores"][0]["score_date"] == _FRIDAY
    assert persisted["scores"][0]["ticker"] == "ABCD"
    assert len(persisted["tracked"]) == 1
    assert persisted["tracked"][0][0] == "ABCD"
    assert persisted["tracked"][0][1] == _FRIDAY
