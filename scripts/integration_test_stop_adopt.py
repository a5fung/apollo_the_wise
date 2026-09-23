"""#151 Phase 2 (sync-first) — integration test for the stop-coverage ADOPT path.

Reproduces the FPS 2026-06-05 false-remediation shape: a LIVE broker stop covers
the position, but the DB stop_order_id pointer is NULL (lost during a partial-exit
false-naked). Pre-fix, sync_positions kept trying to PLACE a duplicate stop and
failed forever (qty_available=0). Post-fix, _try_adopt_existing_stop ADOPTS the
existing broker stop into the DB pointer — a pure DB write, ZERO new broker orders.

ASSERTS (hard fail):
  1. _try_adopt_existing_stop returns the existing stop's id (adopted).
  2. DB mi_live_trades.stop_order_id is now that id.
  3. ZERO new orders placed — open orders on the test ticker still = the ONE
     original stop (same id), proving no duplicate.

Market hours + paper only; mutates prod trade-state tables (sentinel row, guarded
teardown). Exit 0 = pass, 1 = real failure, 2 = couldn't run (market closed/setup).
Mirrors scripts/integration_test_partial_exit.py harness discipline.
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
logger = logging.getLogger("stop_adopt_integration")

_ET = ZoneInfo("America/New_York")
_SENTINEL_SIGNAL_TYPE = "integration_test"
_TEST_TICKER = "F"
_TEST_QTY = 5
_ACCOUNT_MODE = "paper"


def _market_open_now() -> bool:
    et = datetime.now(_ET)
    mins = et.hour * 60 + et.minute
    return et.weekday() < 5 and (9 * 60 + 30) <= mins < (16 * 60)


async def _poll_order_status(order_id, account_mode, want, *, budget_s=8.0, interval=0.4):
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


async def _open_test_orders(account_mode):
    from agents.market_intelligence.broker import alpaca_client
    orders = await alpaca_client.get_open_orders(_TEST_TICKER, account_mode=account_mode)
    return [o for o in orders if (o.get("symbol") or o.get("ticker")) == _TEST_TICKER]


async def _flatten_test_position(account_mode):
    from agents.market_intelligence.broker import alpaca_client
    pos = await alpaca_client.get_position(_TEST_TICKER, account_mode=account_mode)
    if not pos:
        return
    qty = abs(int(float(pos.get("qty", 0))))
    if qty <= 0:
        return
    await alpaca_client.close_position(_TEST_TICKER, account_mode=account_mode)
    logger.info(f"teardown: close {qty} {_TEST_TICKER} submitted — waiting for flat")
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        p = await alpaca_client.get_position(_TEST_TICKER, account_mode=account_mode)
        if not p or abs(int(float(p.get("qty", 0)))) == 0:
            return
        await asyncio.sleep(0.4)


async def _cancel_test_ticker_orders(account_mode):
    from agents.market_intelligence.broker import alpaca_client
    for o in await _open_test_orders(account_mode):
        oid = o.get("id")
        if oid:
            try:
                await alpaca_client.cancel_order(oid, account_mode=account_mode)
            except Exception as e:
                logger.warning(f"teardown: cancel {oid} failed: {e}")
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        if not await _open_test_orders(account_mode):
            return
        await asyncio.sleep(0.3)


async def _delete_sentinel_rows(trade_id=None):
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
            async with conn.transaction():
                await conn.execute("SET LOCAL mi.allow_trade_delete = 'yes'")
                await conn.execute("DELETE FROM mi_live_orders WHERE trade_id = $1", tid)
                await conn.execute(
                    "DELETE FROM mi_live_trades WHERE id = $1 AND signal_type = $2",
                    tid, _SENTINEL_SIGNAL_TYPE)
            logger.info(f"teardown: deleted sentinel trade row {tid}")
    return len(ids)


async def _sweep_orphans(account_mode):
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
        logger.error("market closed — needs real fills. Run 9:30-16:00 ET. (inconclusive)")
        return 2

    from agents.market_intelligence.broker import alpaca_client
    from agents.market_intelligence.broker.order_manager import _try_adopt_existing_stop
    from agents.market_intelligence.db import get_pool
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    await _sweep_orphans(_ACCOUNT_MODE)

    trade_id = None
    stop_id = None
    try:
        # 1. BUY test shares.
        client = alpaca_client.get_trading_client(_ACCOUNT_MODE)
        buy = client.submit_order(MarketOrderRequest(
            symbol=_TEST_TICKER, qty=_TEST_QTY, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        ))
        if await _poll_order_status(str(buy.id), _ACCOUNT_MODE, {"filled"}) != "filled":
            logger.error("SETUP FAIL: test buy not filled")
            return 2
        bo = await alpaca_client.get_order(str(buy.id), account_mode=_ACCOUNT_MODE)
        fill_price = float(bo.get("filled_avg_price") or 11.0) or 11.0
        logger.info(f"test buy filled: {_TEST_QTY} {_TEST_TICKER} @ ${fill_price:.2f}")

        # 2. Place the LIVE broker stop for all shares (the stop the DB will "lose").
        stop_price = round(fill_price * 0.90, 2)
        stop = await alpaca_client.place_stop_order(
            _TEST_TICKER, _TEST_QTY, stop_price, account_mode=_ACCOUNT_MODE,
        )
        stop_id = stop["id"]
        logger.info(f"live broker stop placed: {_TEST_QTY} sh @ ${stop_price} id={stop_id}")
        # Wait until the stop is CONFIRMED-LIVE before adopting — the real FPS
        # shape is an ESTABLISHED stop, not a 12ms-old pending_new one. The
        # adopt guard correctly declines unconfirmed orders, so the test must
        # mirror reality (otherwise it fails on its own setup race).
        _live = {"new", "accepted", "held", "partially_filled", "accepted_for_bidding"}
        st = await _poll_order_status(stop_id, _ACCOUNT_MODE, _live)
        if st not in _live:
            logger.error(f"SETUP FAIL: stop not confirmed live (status={st})")
            return 2
        logger.info(f"stop confirmed live (status={st}) — FPS shape established")

        # 3. Synthetic trade row with stop_order_id = NULL — the FPS shape:
        #    broker HAS a covering stop, DB pointer is null.
        pool = await get_pool()
        async with pool.acquire() as conn:
            trade_id = await conn.fetchval("""
                INSERT INTO mi_live_trades
                    (ticker, alert_date, status, account_mode, signal_type,
                     remaining_shares, entry_price, stop_price, stop_order_id,
                     hold_days, partial_taken, filled_at)
                VALUES ($1, CURRENT_DATE, 'filled', $2, $3,
                        $4, $5, $6, NULL, 3, FALSE, NOW())
                RETURNING id
            """, _TEST_TICKER, _ACCOUNT_MODE, _SENTINEL_SIGNAL_TYPE,
                _TEST_QTY, fill_price, stop_price)
        logger.info(f"synthetic trade row id={trade_id} inserted (stop_order_id=NULL)")

        # 4. THE FUNCTION UNDER TEST.
        adopted = await _try_adopt_existing_stop(
            trade_id, _TEST_TICKER, float(_TEST_QTY), _ACCOUNT_MODE,
        )

        # 5a. ASSERT: adopted the existing stop id.
        if adopted != stop_id:
            logger.error(f"FAIL: adopted={adopted}, expected existing stop {stop_id}")
            return 1
        # 5b. ASSERT: DB pointer now set to it.
        async with pool.acquire() as conn:
            db_stop = await conn.fetchval(
                "SELECT stop_order_id FROM mi_live_trades WHERE id = $1", trade_id)
        if db_stop != stop_id:
            logger.error(f"FAIL: DB stop_order_id={db_stop}, expected {stop_id}")
            return 1
        # 5c. ASSERT: ZERO new orders — open stops on the ticker still = the one original.
        open_now = await _open_test_orders(_ACCOUNT_MODE)
        stop_ids = [o.get("id") for o in open_now
                    if "stop" in str(o.get("type", "")).lower()]
        if stop_ids != [stop_id]:
            logger.error(
                f"FAIL: expected exactly the original stop [{stop_id}] open, "
                f"got {stop_ids} — a duplicate was placed (the bug)"
            )
            return 1

        logger.info(
            f"BROKER OK: adopted existing stop {stop_id[:8]} into DB pointer; "
            f"ZERO duplicate orders placed (open stops = {[s[:8] for s in stop_ids]})"
        )
        logger.info("PASS — stop-coverage ADOPT path validated against real broker")
        return 0

    except Exception as e:
        logger.error(f"FAIL (exception): {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        return 1
    finally:
        residue = []
        try:
            await _cancel_test_ticker_orders(_ACCOUNT_MODE)
        except Exception as e:
            residue.append(f"order cancel failed: {e}")
        try:
            await _flatten_test_position(_ACCOUNT_MODE)
        except Exception as e:
            residue.append(f"position flatten failed: {e}")
        try:
            if trade_id is not None:
                await _delete_sentinel_rows(trade_id=trade_id)
        except Exception as e:
            residue.append(f"sentinel row delete failed (id={trade_id}): {e}")
        if residue:
            logger.error(
                "TEARDOWN INCOMPLETE — manual cleanup needed:\n  "
                + "\n  ".join(residue)
                + f"\n  (ticker={_TEST_TICKER}, trade_id={trade_id}, "
                f"stop_id={stop_id}, account={_ACCOUNT_MODE})"
            )


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
