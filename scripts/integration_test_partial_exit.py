"""#151 (a.2) — durable end-to-end integration test for execute_partial_exit.

The repeatable test the `feedback_no_trade_state_fix_without_integration`
memory rule actually demands. The IBM /partialnow canary (2026-05-29) was a
ONE-TIME manual fire against a real position; this is the callable harness
that catches the NEXT regression in the partial-exit path.

**Run this BEFORE merging any change to execute_partial_exit / replace_order /
the partial-exit broker flow.** It is NOT a deploy gate (unlike G6): it needs
market hours + real fills + the live WS stream + mutates prod trade-state
tables, so it can't run on every off-hours deploy. Manual, deliberate, watched.

What it does (during market hours, paper account only):
  1. Sweep any orphan sentinel rows/positions from a prior crashed run.
  2. Market-BUY 6 shares of a cheap liquid ticker (F) → wait for fill.
  3. Place a far-below stop for all 6 shares.
  4. INSERT a synthetic mi_live_trades row (signal_type='integration_test')
     so execute_partial_exit can operate on it. Capture id via RETURNING.
  5. Call execute_partial_exit(trade_id, 2, force=True) — exercises the full
     flow: atomic stop replace → verify-stop-live → market sell → (WS finalize).
  6. ASSERT ON BROKER GROUND TRUTH (hard fail): the partial sell order shows
     filled AND the stop order is now qty=4 and live. Queryable directly, no
     DB/WS dependency (advisor 2026-05-29: asserting on the WS-populated DB row
     would test the WS handler + inherit stream health as a failure mode →
     false reds when the stream lags, the #123 class).
  7. Poll the DB row for WS-finalize (partial_taken/remaining) as a SOFT,
     diagnostic check — a lag here is reported as "WS-finalize lagged", a
     DISTINCT diagnosis, NOT an execute_partial_exit failure.
  8. Teardown in finally (survives partial failure, loudly prints residue):
     flatten the remaining position, cancel the stop, DELETE the sentinel row
     WHERE id=$captured AND signal_type='integration_test' (both conditions —
     never by ticker/sentinel alone; this DELETE is the 2026-05-27 cascade
     surface).

Exit 0 = execute_partial_exit + broker confirmed correct. Exit 1 = real
failure. Exit 2 = couldn't run (market closed / setup error) — inconclusive,
not a failure of the code under test.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("partial_exit_integration")

_ET = ZoneInfo("America/New_York")
_SENTINEL_SIGNAL_TYPE = "integration_test"
_TEST_TICKER = "F"          # cheap, liquid; never an active strategy position
_TEST_QTY = 6               # 6 // 3 = 2 partial, 4 remaining
_PARTIAL_QTY = _TEST_QTY // 3
_REMAINING_QTY = _TEST_QTY - _PARTIAL_QTY
_ACCOUNT_MODE = "paper"     # NEVER touch live


def _market_open_now() -> bool:
    et = datetime.now(_ET)
    mins = et.hour * 60 + et.minute
    return et.weekday() < 5 and (9 * 60 + 30) <= mins < (16 * 60)


async def _poll_order_status(order_id, account_mode, want, *, budget_s=8.0, interval=0.4):
    """Poll get_order until its normalized status is in `want`. Returns the
    last seen status (normalized) whether or not it matched."""
    from agents.market_intelligence.broker import alpaca_client
    from agents.market_intelligence.broker.order_manager import _canonical_order_status
    deadline = time.monotonic() + budget_s
    last = None
    while time.monotonic() < deadline:
        o = await alpaca_client.get_order(order_id, account_mode=account_mode)
        last = _canonical_order_status(o.get("status") if o else None)
        if last in want:
            return last
        await asyncio.sleep(interval)
    return last


async def _flatten_test_position(account_mode):
    """Close any open position in the test ticker (idempotent)."""
    from agents.market_intelligence.broker import alpaca_client
    pos = await alpaca_client.get_position(_TEST_TICKER, account_mode=account_mode)
    if pos:
        qty = abs(int(float(pos.get("qty", 0))))
        if qty > 0:
            try:
                await alpaca_client.close_position(_TEST_TICKER, account_mode=account_mode)
                logger.info(f"sweep/teardown: closed {qty} {_TEST_TICKER} position")
            except Exception as e:
                logger.warning(f"sweep/teardown: close_position {_TEST_TICKER} failed: {e}")


async def _cancel_test_ticker_orders(account_mode):
    """Cancel any open orders on the test ticker (idempotent)."""
    from agents.market_intelligence.broker import alpaca_client
    orders = await alpaca_client.get_open_orders(account_mode=account_mode)
    for o in orders:
        if (o.get("symbol") or o.get("ticker")) == _TEST_TICKER:
            oid = o.get("id")
            if oid:
                try:
                    await alpaca_client.cancel_order(oid, account_mode=account_mode)
                    logger.info(f"sweep/teardown: cancelled {_TEST_TICKER} order {oid}")
                except Exception as e:
                    logger.warning(f"sweep/teardown: cancel {oid} failed: {e}")


async def _delete_sentinel_rows(trade_id=None):
    """Delete sentinel mi_live_trades rows (+ their mi_live_orders). When
    trade_id is given, delete that id guarded by signal_type (defense in depth).
    When None (sweep), delete ALL rows with signal_type=sentinel.

    The mi_live_trades DELETE is the 2026-05-27 cascade surface — both
    conditions always required; never by ticker alone.
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        if trade_id is not None:
            ids = [r["id"] for r in await conn.fetch(
                "SELECT id FROM mi_live_trades WHERE id = $1 AND signal_type = $2",
                trade_id, _SENTINEL_SIGNAL_TYPE)]
        else:
            ids = [r["id"] for r in await conn.fetch(
                "SELECT id FROM mi_live_trades WHERE signal_type = $1",
                _SENTINEL_SIGNAL_TYPE)]
        for tid in ids:
            await conn.execute("DELETE FROM mi_live_orders WHERE trade_id = $1", tid)
            await conn.execute(
                "DELETE FROM mi_live_trades WHERE id = $1 AND signal_type = $2",
                tid, _SENTINEL_SIGNAL_TYPE)
            logger.info(f"teardown: deleted sentinel trade row {tid} (+ its orders)")
    return len(ids)


async def _sweep_orphans(account_mode):
    """Idempotent pre-test cleanup of any residue from a prior crashed run:
    sentinel DB rows first (so nothing references the position), then flatten
    the broker position + cancel orders."""
    await _delete_sentinel_rows(trade_id=None)
    await _cancel_test_ticker_orders(account_mode)
    await _flatten_test_position(account_mode)


async def run() -> int:
    try:
        from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
        _bootstrap_alpaca_credentials()
    except Exception as e:
        logger.error(f"bootstrap failed: {e}")
        return 2

    if not _market_open_now():
        logger.error(
            "market is closed — this test needs real fills + the live WS stream. "
            "Run during 9:30-16:00 ET Mon-Fri. (inconclusive, not a failure)"
        )
        return 2

    from agents.market_intelligence.broker import alpaca_client
    from agents.market_intelligence.broker.order_manager import (
        execute_partial_exit, _canonical_order_status,
    )
    from agents.market_intelligence.db import get_pool
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    # 0. Sweep any orphan residue first (teardown-path proven before we create
    #    anything that needs cleaning).
    await _sweep_orphans(_ACCOUNT_MODE)

    trade_id = None
    stop_id = None
    try:
        # 1. Market BUY the test shares.
        client = alpaca_client.get_trading_client(_ACCOUNT_MODE)
        buy = client.submit_order(MarketOrderRequest(
            symbol=_TEST_TICKER, qty=_TEST_QTY, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        ))
        buy_id = str(buy.id)
        buy_status = await _poll_order_status(buy_id, _ACCOUNT_MODE, {"filled"})
        if buy_status != "filled":
            logger.error(f"SETUP FAIL: test buy not filled (status={buy_status})")
            return 2
        bo = await alpaca_client.get_order(buy_id, account_mode=_ACCOUNT_MODE)
        fill_price = float(bo.get("filled_avg_price") or bo.get("limit_price") or 0) or 11.0
        logger.info(f"test buy filled: {_TEST_QTY} {_TEST_TICKER} @ ${fill_price:.2f}")

        # 2. Place a far-below stop for all shares (won't trigger; F ~$11).
        stop_price = round(fill_price * 0.90, 2)
        stop = await alpaca_client.place_stop_order(
            _TEST_TICKER, _TEST_QTY, stop_price,
            account_mode=_ACCOUNT_MODE,
        )
        stop_id = stop["id"]
        logger.info(f"test stop placed: {_TEST_QTY} sh @ ${stop_price} id={stop_id}")

        # 3. INSERT the synthetic trade row. RETURNING id is the teardown anchor.
        pool = await get_pool()
        async with pool.acquire() as conn:
            trade_id = await conn.fetchval("""
                INSERT INTO mi_live_trades
                    (ticker, alert_date, status, account_mode, signal_type,
                     remaining_shares, entry_price, stop_price, stop_order_id,
                     hold_days, partial_taken, filled_at)
                VALUES ($1, CURRENT_DATE, 'filled', $2, $3,
                        $4, $5, $6, $7, 3, FALSE, NOW())
                RETURNING id
            """, _TEST_TICKER, _ACCOUNT_MODE, _SENTINEL_SIGNAL_TYPE,
                _TEST_QTY, fill_price, stop_price, stop_id)
        logger.info(f"synthetic trade row id={trade_id} inserted")

        # 4. THE FUNCTION UNDER TEST. force=True (operator-attended path; also
        #    bypasses the breaker, which may be open from prior real failures).
        ok = await execute_partial_exit(trade_id, _PARTIAL_QTY, force=True)
        if not ok:
            logger.error("FAIL: execute_partial_exit returned False")
            return 1

        # 5. HARD ASSERT on broker ground truth (no DB/WS dependency).
        #    a) the partial sell order filled
        #    b) the stop order is now qty=_REMAINING_QTY and live
        async with pool.acquire() as conn:
            sell_oid = await conn.fetchval("""
                SELECT alpaca_order_id FROM mi_live_orders
                WHERE trade_id = $1 AND purpose = 'partial_exit'
                ORDER BY id DESC LIMIT 1
            """, trade_id)
            new_stop_oid = await conn.fetchval("""
                SELECT alpaca_order_id FROM mi_live_orders
                WHERE trade_id = $1 AND purpose = 'stop_loss'
                ORDER BY id DESC LIMIT 1
            """, trade_id)

        if not sell_oid:
            logger.error("FAIL: no partial_exit order row written")
            return 1
        sell_status = await _poll_order_status(sell_oid, _ACCOUNT_MODE, {"filled"})
        if sell_status != "filled":
            logger.error(f"FAIL: partial sell not filled on broker (status={sell_status})")
            return 1

        new_stop = await alpaca_client.get_order(new_stop_oid, account_mode=_ACCOUNT_MODE)
        new_stop_status = _canonical_order_status(new_stop.get("status") if new_stop else None)
        new_stop_qty = int(float(new_stop.get("qty", 0))) if new_stop else 0
        # Track the actual live stop id for teardown (replace issued a new id).
        if new_stop_oid:
            stop_id = new_stop_oid
        if new_stop_status not in {"new", "accepted", "held", "partially_filled"}:
            logger.error(
                f"FAIL: replacement stop not live (status={new_stop_status})"
            )
            return 1
        if new_stop_qty != _REMAINING_QTY:
            logger.error(
                f"FAIL: replacement stop qty={new_stop_qty}, expected {_REMAINING_QTY}"
            )
            return 1
        logger.info(
            f"BROKER OK: partial sell {sell_oid[:8]} filled; "
            f"stop {new_stop_oid[:8]} live qty={new_stop_qty} status={new_stop_status}"
        )

        # 6. SOFT/diagnostic: WS-finalize of the DB row (not a pass/fail of the
        #    function under test — a lag here is a WS/#123 diagnosis).
        finalized = False
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT partial_taken, remaining_shares FROM mi_live_trades WHERE id = $1",
                    trade_id)
            if row and row["partial_taken"] and int(row["remaining_shares"]) == _REMAINING_QTY:
                finalized = True
                break
            await asyncio.sleep(0.5)
        if finalized:
            logger.info("WS-FINALIZE OK: DB row partial_taken=TRUE, remaining updated")
        else:
            logger.warning(
                "WS-finalize LAGGED: broker is correct but DB row not yet "
                "committed by the WS handler — WS/#123 diagnosis, NOT an "
                "execute_partial_exit failure."
            )

        logger.info("PASS — execute_partial_exit validated end-to-end against real broker")
        return 0

    except Exception as e:
        logger.error(f"FAIL (exception): {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        return 1
    finally:
        # Teardown — survives partial failure; loudly reports residue.
        residue = []
        try:
            await _flatten_test_position(_ACCOUNT_MODE)
        except Exception as e:
            residue.append(f"position flatten failed: {e}")
        try:
            await _cancel_test_ticker_orders(_ACCOUNT_MODE)
        except Exception as e:
            residue.append(f"order cancel failed: {e}")
        try:
            if trade_id is not None:
                await _delete_sentinel_rows(trade_id=trade_id)
        except Exception as e:
            residue.append(f"sentinel row delete failed (id={trade_id}): {e}")
        if residue:
            logger.error(
                "TEARDOWN INCOMPLETE — manual cleanup needed:\n  "
                + "\n  ".join(residue)
                + f"\n  (test ticker={_TEST_TICKER}, trade_id={trade_id}, "
                f"stop_id={stop_id}, account={_ACCOUNT_MODE})"
            )


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
