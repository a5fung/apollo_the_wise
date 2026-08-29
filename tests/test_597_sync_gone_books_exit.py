"""#597 — sync_positions "position gone from Alpaca" must not book a wrong P&L.

The pre-#597 branch closed the row blind: status='closed', remaining_shares=0,
closed_at=NOW(), stop_order_id=NULL — and NEVER wrote an exit leg or total_pnl.
The trade booked whatever P&L it already had (usually $0 on a real loss), and
mi_live_trades.total_pnl feeds mi_sell_discipline_records, which every
exit-rule replay reads.

Fix under test (`_resolve_position_gone`, called from the gone branch of
`_sync_positions_for_mode`):
  1. GRACE  — stop confirmed filled at the broker but recently → leave the row
              to the websocket finaliser (no DB write).
  2. RECORD — stop fill older than the grace window → book the exit from
              BROKER TRUTH (the stop order's filled_avg_price/filled_qty) by
              delegating the commit to _finalize_stop_fill_locked, the
              canonical writer (deploy gate audit_column_writes) — exits +
              total_pnl in one statement, idempotent on exits[].order_id.
  3. REFUSE — no broker-confirmed fill → leave the row OPEN and loud (audit +
              Telegram + discrepancy), never invent a price.

Every test here FAILS against the pre-#597 blind-close (verified by mutation:
see the task report — reverting the branch, dropping the exit-leg write, and
no-op'ing the idempotency guard each turn specific tests red).
"""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool


def _gone_trade(trade_id=42, ticker="XYZ", remaining=10, stop_order_id="stop-1"):
    """Row shape returned by the sweep query."""
    return {
        "id": trade_id, "ticker": ticker,
        "remaining_shares": remaining, "entry_price": 100.0,
        "status": "filled", "stop_order_id": stop_order_id,
        "stop_price": 95.0, "orb_low": 95.0,
        "signal_type": "magna53",
    }


def _present_trade(trade_id=41, ticker="AAA", remaining=5):
    """A second DB trade that IS at Alpaca — keeps the 2026-05-27 mass-close
    guard (0 Alpaca positions + DB-active → abort) out of these tests' way.
    Carries an ACTIVE stop ("aaa-stop", status new) so the later orphaned-stop
    sweep leaves it alone and never reaches remediation paths."""
    return _gone_trade(trade_id=trade_id, ticker=ticker, remaining=remaining,
                       stop_order_id="aaa-stop")


def _full_row(trade, exits=None, account_mode="paper"):
    """Row shape for the under-lock re-read (SELECT * WHERE id=...)."""
    row = dict(trade)
    row["exits"] = exits if exits is not None else []
    row["account_mode"] = account_mode
    return row


def _alpaca_positions():
    return [{"symbol": "AAA", "qty": 5.0}]


def _filled_stop(order_id="stop-1", price=95.0, qty=10, age_s=7200):
    filled_at = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return {
        "id": order_id, "status": "filled",
        "filled_avg_price": price, "filled_qty": float(qty),
        "filled_at": filled_at.isoformat(),
    }


def _fake_try_lock(acquired=True):
    @asynccontextmanager
    async def _lock(_trade_id):
        yield acquired
    return _lock


def _run_patches(pool, get_order_result=None, try_lock=None, audit_calls=None,
                 telegram_calls=None):
    """Common patch stack for _sync_positions_for_mode runs."""
    audit_calls = audit_calls if audit_calls is not None else []
    telegram_calls = telegram_calls if telegram_calls is not None else []

    async def _audit(event_type, summary=None, detail=None):
        audit_calls.append((event_type, summary, detail))

    async def _telegram(msg, *a, **k):
        telegram_calls.append(msg)
        return True

    async def _get_order(order_id, account_mode=None):
        if order_id == "aaa-stop":  # the present trade's healthy, active stop
            return {"id": "aaa-stop", "status": "new"}
        return get_order_result

    import agents.market_intelligence.broker.order_manager as om
    return patch.object(
        om.alpaca, "get_all_positions",
        new=AsyncMock(return_value=_alpaca_positions()),
    ), patch.object(
        om.alpaca, "get_order", new=AsyncMock(side_effect=_get_order),
    ), patch.object(
        om, "get_pool", new=AsyncMock(return_value=pool),
    ), patch.object(
        om, "_trade_advisory_try_lock", new=try_lock or _fake_try_lock(True),
    ), patch.object(
        om, "log_audit_event", new=_audit,
    ), patch.object(
        om, "send_telegram_message", new=_telegram,
    )


def _make_pool(db_trades, full_row):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=db_trades)
    conn.fetchrow = AsyncMock(return_value=full_row)
    conn.execute = AsyncMock()
    return pool, conn


def _close_executes(conn):
    return [c for c in conn.execute.call_args_list
            if c.args and "status = 'closed'" in (c.args[0] or "")]


@pytest.mark.asyncio
async def test_gone_with_old_filled_stop_records_exit_and_closes():
    """The core #597 case: WS finaliser missed a 2h-old stop fill. Sync must
    book the REAL fill (exit leg + total_pnl together) — not close at $0."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    gone = _gone_trade()
    pool, conn = _make_pool([_present_trade(), gone], _full_row(gone))
    audit_calls = []

    p1, p2, p3, p4, p5, p6 = _run_patches(
        pool, get_order_result=_filled_stop(age_s=7200), audit_calls=audit_calls,
    )
    with p1, p2, p3, p4, p5, p6:
        result = await _sync_positions_for_mode("paper")

    closes = _close_executes(conn)
    assert len(closes) == 1, "must close the row exactly once"
    sql = closes[0].args[0]
    # The MNDY 2026-05-11 invariant: exits and total_pnl move together, in the
    # same statement, in the same close.
    assert "exits" in sql and "total_pnl" in sql, (
        "close must write exits + total_pnl in the SAME statement — the "
        "pre-#597 blind close wrote neither"
    )
    _, exits_arg, total_pnl_arg = closes[0].args[1], closes[0].args[2], closes[0].args[3]
    assert isinstance(exits_arg, list) and len(exits_arg) == 1
    leg = exits_arg[0]
    assert leg["order_id"] == "stop-1"
    assert leg["price"] == 95.0
    assert leg["shares"] == 10
    assert leg["pnl"] == pytest.approx((95.0 - 100.0) * 10)  # -50, the real loss
    assert total_pnl_arg == pytest.approx(-50.0), (
        "total_pnl must equal sum(exits[].pnl) — booking $0 here is the bug"
    )
    assert any(c[0] == "sync_gone_stop_fill_recorded" for c in audit_calls)
    assert any("XYZ" in m for m in result)


@pytest.mark.asyncio
async def test_gone_unresolved_leaves_row_open_and_loud():
    """No broker-confirmed fill (stop canceled — e.g. OCO limit took the
    shares, or manual liquidation): NEVER close, never invent a price."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    gone = _gone_trade()
    pool, conn = _make_pool([_present_trade(), gone], _full_row(gone))
    audit_calls, telegram_calls = [], []

    canceled = {"id": "stop-1", "status": "canceled",
                "filled_avg_price": None, "filled_qty": 0, "filled_at": None}
    p1, p2, p3, p4, p5, p6 = _run_patches(
        pool, get_order_result=canceled,
        audit_calls=audit_calls, telegram_calls=telegram_calls,
    )
    with p1, p2, p3, p4, p5, p6:
        result = await _sync_positions_for_mode("paper")

    assert _close_executes(conn) == [], (
        "must NOT close a row whose real exit price is unknown — the pre-#597 "
        "branch closed it blind and booked $0"
    )
    assert conn.execute.call_args_list == [], "no DB mutation at all when unresolved"
    assert any(c[0] == "sync_position_gone_unresolved" for c in audit_calls)
    assert any("XYZ" in m for m in telegram_calls), "unresolved must Telegram the operator"
    assert any("UNRESOLVED" in m for m in result)


@pytest.mark.asyncio
async def test_gone_no_stop_order_id_leaves_row_open():
    """Row has no stop pointer at all — nothing to fetch, so refuse to close."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    gone = _gone_trade(stop_order_id=None)
    pool, conn = _make_pool([_present_trade(), gone], _full_row(gone))
    audit_calls = []

    p1, p2, p3, p4, p5, p6 = _run_patches(pool, get_order_result=None,
                                          audit_calls=audit_calls)
    with p1, p2, p3, p4, p5, p6:
        await _sync_positions_for_mode("paper")

    assert conn.execute.call_args_list == []
    assert any(c[0] == "sync_position_gone_unresolved" for c in audit_calls)


@pytest.mark.asyncio
async def test_gone_recent_fill_defers_to_finaliser():
    """The race in the bug report: exit filled seconds ago, finaliser hasn't
    run yet. Sync must leave the row alone (grace window), not close it."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    gone = _gone_trade()
    pool, conn = _make_pool([_present_trade(), gone], _full_row(gone))

    p1, p2, p3, p4, p5, p6 = _run_patches(
        pool, get_order_result=_filled_stop(age_s=30),
    )
    with p1, p2, p3, p4, p5, p6:
        result = await _sync_positions_for_mode("paper")

    assert conn.execute.call_args_list == [], (
        "a fresh broker fill belongs to the WS finaliser — sync closing here "
        "is the exact race that produced wrong books"
    )
    assert any("finaliser" in m for m in result)


@pytest.mark.asyncio
async def test_gone_idempotent_no_double_leg():
    """Leg for this stop order already in exits[]: the canonical writer's
    idempotency guard (delegated to, not duplicated) must make the whole
    resolution a no-op — no second leg, no double-counted P&L, no write."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    existing_leg = {"time": "2026-08-28T15:00:00+00:00", "price": 95.0,
                    "reason": "stop_hit", "shares": 10, "pnl": -50.0,
                    "order_id": "stop-1", "source": "websocket"}
    gone = _gone_trade()
    pool, conn = _make_pool(
        [_present_trade(), gone], _full_row(gone, exits=[existing_leg]),
    )

    p1, p2, p3, p4, p5, p6 = _run_patches(
        pool, get_order_result=_filled_stop(age_s=7200),
    )
    with p1, p2, p3, p4, p5, p6:
        await _sync_positions_for_mode("paper")

    assert conn.execute.call_args_list == [], (
        "an already-recorded fill must be a complete no-op — any write here "
        "means a duplicate leg or double-counted P&L"
    )


@pytest.mark.asyncio
async def test_gone_lock_held_defers():
    """Advisory try-lock not acquired → a finaliser/partial is mid-write.
    Sync must not touch the row this sweep."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    gone = _gone_trade()
    pool, conn = _make_pool([_present_trade(), gone], _full_row(gone))

    p1, p2, p3, p4, p5, p6 = _run_patches(
        pool, get_order_result=_filled_stop(age_s=7200),
        try_lock=_fake_try_lock(acquired=False),
    )
    with p1, p2, p3, p4, p5, p6:
        result = await _sync_positions_for_mode("paper")

    assert conn.execute.call_args_list == []
    assert conn.fetchrow.call_args_list == [], "no re-read without the lock"
    assert any("deferring" in m for m in result)


@pytest.mark.asyncio
async def test_gone_finaliser_already_closed_row_noop():
    """Under-lock re-read shows the row closed (finaliser won the race after
    the sweep snapshot): nothing to do, nothing to report."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    gone = _gone_trade()
    closed_row = _full_row(gone)
    closed_row["status"] = "closed"
    closed_row["remaining_shares"] = 0
    pool, conn = _make_pool([_present_trade(), gone], closed_row)

    p1, p2, p3, p4, p5, p6 = _run_patches(
        pool, get_order_result=_filled_stop(age_s=7200),
    )
    with p1, p2, p3, p4, p5, p6:
        result = await _sync_positions_for_mode("paper")

    assert conn.execute.call_args_list == []
    assert not any("XYZ" in m for m in result)


@pytest.mark.asyncio
async def test_gone_resolution_error_degrades_loudly_and_sweep_survives():
    """Constraint 5: a failure inside the resolution must audit + report, not
    raise into the scheduled sweep or silently drop the discrepancy."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    gone = _gone_trade()
    pool, conn = _make_pool([_present_trade(), gone], _full_row(gone))
    conn.fetchrow = AsyncMock(side_effect=RuntimeError("db exploded"))
    audit_calls = []

    p1, p2, p3, p4, p5, p6 = _run_patches(
        pool, get_order_result=_filled_stop(age_s=7200), audit_calls=audit_calls,
    )
    with p1, p2, p3, p4, p5, p6:
        result = await _sync_positions_for_mode("paper")  # must not raise

    assert conn.execute.call_args_list == [], "no writes after a failed re-read"
    assert any(c[0] == "sync_gone_resolution_error" for c in audit_calls)
    assert any("resolution errored" in m for m in result)


@pytest.mark.asyncio
async def test_gone_account_mode_threaded_to_broker_and_query():
    """Account-mode safety: the under-lock re-read filters on account_mode and
    the stop-order fetch routes to the trade's own mode."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )
    import agents.market_intelligence.broker.order_manager as om

    gone = _gone_trade()
    pool, conn = _make_pool([_present_trade(), gone],
                            _full_row(gone, account_mode="live"))

    p1, p2, p3, p4, p5, p6 = _run_patches(
        pool, get_order_result=_filled_stop(age_s=7200),
    )
    with p1, p2, p3, p4, p5, p6:
        await _sync_positions_for_mode("live")
        get_order_mock = om.alpaca.get_order

    fetchrow_call = conn.fetchrow.call_args_list[0]
    assert "account_mode" in fetchrow_call.args[0]
    assert "live" in fetchrow_call.args
    stop_calls = [c for c in get_order_mock.call_args_list if "stop-1" in c.args]
    assert stop_calls, "resolution must fetch the tracked stop order"
    assert all(c.kwargs.get("account_mode") == "live" for c in stop_calls)
