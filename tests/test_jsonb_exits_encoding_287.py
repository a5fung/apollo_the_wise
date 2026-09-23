"""#287 — jsonb double-encoding fix for mi_live_trades.exits / .running_closes writers.

Same bug class as #177/#179/#412: the DB pool registers a jsonb codec whose encoder
is plain json.dumps, applied AUTOMATICALLY to every jsonb param (see db.py's
`_jsonb_param` docstring). A caller that ALSO does json.dumps(x) before passing it
into a `$N::jsonb` param double-encodes — the value lands as jsonb_typeof='string'
instead of a proper jsonb array. Confirmed live: 26 corrupted rows incl. a live trade.

Fix: pass the PLAIN list into the ::jsonb param so the codec encodes it exactly once.
`_jsonb_param` is NOT used here — it does `value or {}`, which would coerce an empty
list `[]` into a dict `{}` (wrong shape for an array column).

These tests pin the param TYPE at the conn.execute() call site for one representative
order_manager `exits` writer (finalize_full_exit) and one representative live_tracker
`running_closes` writer (update_open_positions_live's still-open tail write) — two of
the 12 sites migrated by #287 (order_manager x8, trade_stream x1, live_tracker x3). A
future regression that reintroduces json.dumps(exits) / json.dumps(new_running_closes)
would fail these by producing a str param instead of a list.
"""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker.exit_logic import ExitStep

from tests.conftest import make_mock_pool


# ─── order_manager.finalize_full_exit — exits writer (~line 2033) ──────────


@pytest.mark.asyncio
async def test_finalize_full_exit_exits_param_is_list(monkeypatch):
    pool, conn = make_mock_pool()
    trade_row = {
        "id": 1,
        "ticker": "TEST",
        "exits": [],  # already a list — no prior exits on this trade
        "entry_price": 100.0,
    }
    conn.fetchrow = AsyncMock(return_value=trade_row)
    conn.execute = AsyncMock()
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    # R1 (2026-07-12): the public finalizer now wraps the body in the per-trade
    # advisory lock; stub it (the real impl needs a raw awaitable pool.acquire).
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def _noop_lock(_tid):
        yield
    monkeypatch.setattr(om, "_trade_advisory_lock", _noop_lock)

    await om.finalize_full_exit(
        trade_id=1, filled_qty=100, filled_price=110.0,
        order_id="order-abc", reason="sma_trail_stop",
    )

    assert conn.execute.await_count == 1
    args = conn.execute.await_args[0]
    assert "exits = $2::jsonb" in args[0], "the ::jsonb cast must stay in the SQL"
    exits_param = args[2]
    assert isinstance(exits_param, list), (
        f"exits param must be a plain list (codec encodes exactly once) — got "
        f"{type(exits_param)}. A json.dumps() pre-encode here double-encodes into "
        "jsonb_typeof='string' (#287)."
    )
    assert not isinstance(exits_param, str)
    assert exits_param[0]["order_id"] == "order-abc"


# ─── live_tracker.update_open_positions_live — running_closes writer (~line 619) ──


def _trade_row_still_open():
    return {
        "id": 7,
        "ticker": "TEST",
        "alert_date": date(2026, 6, 18),
        "remaining_shares": 60,
        "entry_price": 100.0,
        "hard_stop": 95.0,
        "stop_price": 95.0,
        "partial_taken": True,
        "breakeven_active": False,
        "exits": [],
        "running_closes": [101.0] * 10,
    }


def _still_open_step():
    # action not in {"stopped_out", "sma_stopped"} -> falls through to the tail
    # "still open" UPDATE (the running_closes write under test). effective_stop
    # is kept <= current_stop (95.0) so the update_stop() branch is skipped too.
    return ExitStep(
        action="updated", closed=False,
        close_reason=None, close_price=None, close_shares=None, close_pnl=None,
        partial_fired=False, partial_shares=0,
        partial_price=None, partial_pnl=None,
        effective_stop=90.0, active_sma=101.0,
        bar_low=108.0, bar_close=110.0, hold_days=6,
        new_remaining=60, new_partial_taken=True, new_breakeven_active=True,
        new_running_closes=[101.0] * 10 + [110.0], new_exits=[], new_total_pnl=300.0,
    )


@pytest.mark.asyncio
async def test_eod_still_open_running_closes_param_is_list(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[_trade_row_still_open()])
    conn.execute = AsyncMock()

    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "get_index_history",
                        AsyncMock(return_value=[{"l": 108.0, "c": 110.0, "h": 111.0, "o": 109.0}]))
    monkeypatch.setattr(lt, "apply_daily_exit_step", lambda *a, **k: _still_open_step())
    monkeypatch.setattr(lt, "update_stop", AsyncMock(return_value=True))

    await lt.update_open_positions_live(today=date(2026, 6, 24))

    assert conn.execute.await_count == 1
    args = conn.execute.await_args[0]
    assert "running_closes = $4::jsonb" in args[0], "the ::jsonb cast must stay in the SQL"
    running_closes_param = args[4]
    assert isinstance(running_closes_param, list), (
        f"running_closes param must be a plain list (codec encodes exactly once) — got "
        f"{type(running_closes_param)}. A json.dumps() pre-encode here double-encodes "
        "into jsonb_typeof='string' (#287)."
    )
    assert not isinstance(running_closes_param, str)
