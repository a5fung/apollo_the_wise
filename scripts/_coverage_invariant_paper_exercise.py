"""#151 never-naked COVERAGE-INVARIANT — paper-only integration exercise.

Validates `_ensure_stop_coverage` (agents/market_intelligence/broker/order_manager.py)
against REAL paper Alpaca. This exercises the broker-side path the mocked unit
tests (tests/test_never_naked_invariant.py) cannot: actual replace_order behavior,
real order-status transitions (pending_new → accepted, pending_replace → replaced),
and Alpaca's share-reservation semantics. Per feedback_no_trade_state_fix_without_integration:
no trade-state fix ships on mocked tests alone.

This is the under-covering repair sibling of scripts/integration_test_stop_adopt.py
(which validates the ADOPT path) and scripts/integration_test_partial_exit.py
(the full partial flow). Same harness discipline; PAPER ONLY.

THE SHAPE under test (the gap the orphan-remediation loop structurally cannot close):
  A filled 6-share position whose live broker stop covers only 4 shares — the
  residue of a failed/aborted partial-exit. The stop is LIVE, so the orphan loop
  `continue`s past it; the 2 un-trimmed shares are NAKED. `_ensure_stop_coverage`
  must atomically replace the 4-share stop UP to 6 (one stop, no duplicate), and a
  second call must be a no-op (idempotent).

EXERCISE (everything account_mode='paper'; setup+assert in try, cleanup in finally):
  1. Read F price (~$12, liquid).
  2. Market-BUY 6 F (paper) → poll to filled.
  3. Place a sell-stop for ONLY 4 shares, well below market (price*0.85, can't
     trigger) = the UNDER-COVERING stop. Poll it to CONFIRMED-LIVE before
     proceeding (else the invariant sees zero live stops → wrong branch).
  4. INSERT a sentinel mi_live_trades row (signal_type='integration_test',
     remaining_shares=6, stop_order_id=<4-sh stop>, stop_price=<stop>).
  5. await _ensure_stop_coverage(trade_id, 'F', 6.0, <stop>, 'integration_test', 'paper').
  6. ASSERT on REAL Alpaca:
     a) return string indicates a coverage REPAIR (🛡 / "repaired"), not a ⚠️ failure;
     b) EXACTLY ONE live sell-stop on F, covering 6 (the 4 was replaced to 6) — no dup;
     c) IDEMPOTENT: read the new stop_order_id from the DB row, poll it confirmed-live,
        call _ensure_stop_coverage again → returns None, stop_order_id UNCHANGED,
        still exactly one 6-share stop, no new order.
  7. CLEANUP (finally, guarded): cancel ALL F orders, flatten the 6 F shares,
     DELETE the sentinel row (WHERE id=<trade_id> AND signal_type='integration_test').
     Verify F flat + zero sentinel rows; print the outcome.

HARD CONSTRAINTS:
  * PAPER only. _ACCOUNT_MODE literal threaded to every Alpaca call. Top-of-run
    guard aborts if it is not 'paper'.
  * Bulletproof cleanup — never leave a naked test position or a sentinel row.
  * A ⚠️ "failed to widen" return (e.g. Alpaca rejecting replace-UP as insufficient
    qty) is a REAL FINDING — reported, never retried-around.

Exit 0 = invariant validated end-to-end against real broker. Exit 1 = real
failure / a finding to report. Exit 2 = couldn't run (market closed / setup error /
NOT paper) — inconclusive, not a failure of the code under test.
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
logger = logging.getLogger("coverage_invariant_exercise")

_ET = ZoneInfo("America/New_York")
_SENTINEL_SIGNAL_TYPE = "integration_test"
_TEST_TICKER = "F"            # cheap, liquid; never an active strategy position
_TEST_QTY = 6                 # full position
_UNDER_QTY = 4                # the under-covering stop (2 shares left naked)
_ACCOUNT_MODE = "paper"       # NEVER touch live — literal, threaded everywhere

# Mirrors order_manager._STOP_CONFIRMED_LIVE_STATUSES — the statuses that count
# as a live, protecting stop. The invariant filters on exactly this set, so the
# exercise must wait for the stop to reach it before calling (a pending_new stop
# is invisible to the invariant → it would take the wrong branch).
_LIVE_STATUSES = {"new", "accepted", "held", "partially_filled", "accepted_for_bidding"}


def _market_open_now() -> bool:
    et = datetime.now(_ET)
    mins = et.hour * 60 + et.minute
    return et.weekday() < 5 and (9 * 60 + 30) <= mins < (16 * 60)


async def _poll_order_status(order_id, account_mode, want, *, budget_s=10.0, interval=0.4):
    """Poll get_order until normalized status is in `want`. Returns last seen."""
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


async def _live_sell_stops(account_mode):
    """The live sell-stops on the test ticker, computed the SAME way the invariant
    does (side=sell, type contains 'stop', status in _LIVE_STATUSES). Used by the
    'exactly one stop covering N' assertions."""
    from agents.market_intelligence.broker.order_manager import _canonical_order_status
    out = []
    for o in await _open_test_orders(account_mode):
        side = str(o.get("side", "")).lower()
        otype = str(o.get("type", "")).lower()
        status = _canonical_order_status(o.get("status"))
        if "sell" in side and "stop" in otype and status in _LIVE_STATUSES:
            out.append(o)
    return out


async def _flatten_test_position(account_mode):
    """Close any open position in the test ticker, then WAIT until flat.
    close_position places a market sell that doesn't fill instantly; proceeding
    before flat triggers the wash-trade guard on the next buy. Idempotent."""
    from agents.market_intelligence.broker import alpaca_client
    pos = await alpaca_client.get_position(_TEST_TICKER, account_mode=account_mode)
    if not pos:
        return
    qty = abs(int(float(pos.get("qty", 0))))
    if qty <= 0:
        return
    await alpaca_client.close_position(_TEST_TICKER, account_mode=account_mode)
    logger.info(f"teardown: close {qty} {_TEST_TICKER} submitted — waiting for flat")
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        p = await alpaca_client.get_position(_TEST_TICKER, account_mode=account_mode)
        if not p or abs(int(float(p.get("qty", 0)))) == 0:
            logger.info(f"teardown: {_TEST_TICKER} position flat")
            return
        await asyncio.sleep(0.4)
    logger.warning(f"teardown: {_TEST_TICKER} position NOT confirmed flat within budget")


async def _cancel_test_ticker_orders(account_mode):
    """Cancel any open orders on the test ticker, then WAIT until they clear.
    Alpaca's held_for_orders share reservation lags the cancel ack by ~ms;
    proceeding to flatten immediately fails with 'insufficient qty available'.
    Idempotent."""
    from agents.market_intelligence.broker import alpaca_client
    for o in await _open_test_orders(account_mode):
        oid = o.get("id")
        if oid:
            try:
                await alpaca_client.cancel_order(oid, account_mode=account_mode)
                logger.info(f"teardown: cancelled {_TEST_TICKER} order {oid}")
            except Exception as e:
                logger.warning(f"teardown: cancel {oid} failed: {e}")
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if not await _open_test_orders(account_mode):
            return
        await asyncio.sleep(0.3)
    logger.warning(f"teardown: {_TEST_TICKER} open orders did not clear within budget")


async def _delete_sentinel_rows(trade_id=None):
    """Delete sentinel mi_live_trades rows (+ their mi_live_orders), guarded by
    signal_type (the 2026-05-27 cascade surface — both conditions, never ticker
    alone). trade_id given → that id; None (sweep) → all sentinel rows."""
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
            # protect_trade_tables BEFORE-DELETE trigger blocks DELETE unless the
            # transaction-scoped session var is set (auto-resets at COMMIT).
            async with conn.transaction():
                await conn.execute("SET LOCAL mi.allow_trade_delete = 'yes'")
                await conn.execute("DELETE FROM mi_live_orders WHERE trade_id = $1", tid)
                await conn.execute(
                    "DELETE FROM mi_live_trades WHERE id = $1 AND signal_type = $2",
                    tid, _SENTINEL_SIGNAL_TYPE)
            logger.info(f"teardown: deleted sentinel trade row {tid} (+ its orders)")
    return len(ids)


async def _count_sentinel_rows():
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM mi_live_trades WHERE signal_type = $1",
            _SENTINEL_SIGNAL_TYPE)


async def _sweep_orphans(account_mode):
    """Idempotent pre-test cleanup of any residue from a prior crashed run:
    sentinel rows first (nothing references the position), then cancel + flatten."""
    await _delete_sentinel_rows(trade_id=None)
    await _cancel_test_ticker_orders(account_mode)
    await _flatten_test_position(account_mode)


def _is_repair_string(s) -> bool:
    return bool(s) and ("🛡" in s or "repaired" in s.lower() or "coverage placed" in s.lower())


def _is_failure_string(s) -> bool:
    return bool(s) and ("⚠️" in s or "🚨" in s or "fail" in s.lower())


async def run() -> int:
    # HARD SAFETY GUARD: paper only. Abort before any broker interaction if the
    # mode literal is not 'paper'.
    if _ACCOUNT_MODE != "paper":
        logger.error(f"ABORT: _ACCOUNT_MODE={_ACCOUNT_MODE!r} is not 'paper'. PAPER ONLY.")
        return 2

    try:
        from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
        _bootstrap_alpaca_credentials()
    except Exception as e:
        logger.error(f"bootstrap failed: {e}")
        return 2

    # Defense in depth: confirm the resolved paper client is talking to the PAPER
    # API endpoint. The deterministic _ACCOUNT_MODE='paper' literal threaded to
    # every call is the real protection (alpaca-py routes paper→paper-api when the
    # client was built with paper=True). This is a belt-and-suspenders check on
    # top of that: if we can read the endpoint and it positively resolves to LIVE
    # (api.alpaca.markets without the 'paper-' prefix), ABORT. If the attribute
    # name differs across alpaca-py versions and we can't read it, we DON'T block —
    # the 'paper' literal already guarantees the routing — but we log loudly.
    from agents.market_intelligence.broker import alpaca_client
    try:
        client = alpaca_client.get_trading_client(_ACCOUNT_MODE)
        base_url = ""
        for attr in ("_base_url", "base_url"):
            v = getattr(client, attr, None)
            if v:
                base_url = str(v)
                break
        low = base_url.lower()
        if low and "paper-api" not in low and "api.alpaca.markets" in low:
            logger.error(
                f"ABORT: resolved client base_url={base_url!r} resolves to the LIVE "
                f"endpoint. Refusing to place orders. PAPER ONLY."
            )
            return 2
        logger.info(f"paper client OK (mode={_ACCOUNT_MODE!r}, base_url={base_url or 'unreadable'})")
    except Exception as e:
        logger.error(f"ABORT: could not build/verify paper client: {e}")
        return 2

    if not _market_open_now():
        logger.error(
            "market is closed — this exercise needs real fills. Run 9:30-16:00 ET "
            "Mon-Fri. (inconclusive, not a failure of the code under test)"
        )
        return 2

    from agents.market_intelligence.broker.order_manager import _ensure_stop_coverage
    from agents.market_intelligence.db import get_pool
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    # 0. Sweep any orphan residue first (teardown path proven before we create
    #    anything that needs cleaning).
    await _sweep_orphans(_ACCOUNT_MODE)

    trade_id = None
    stop_id = None
    try:
        # 1. Market BUY the full test position.
        buy = client.submit_order(MarketOrderRequest(
            symbol=_TEST_TICKER, qty=_TEST_QTY, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        ))
        buy_id = str(buy.id)
        if await _poll_order_status(buy_id, _ACCOUNT_MODE, {"filled"}) != "filled":
            logger.error("SETUP FAIL: test buy not filled")
            return 2
        bo = await alpaca_client.get_order(buy_id, account_mode=_ACCOUNT_MODE)
        fill_price = float(bo.get("filled_avg_price") or 12.0) or 12.0
        logger.info(f"test buy filled: {_TEST_QTY} {_TEST_TICKER} @ ${fill_price:.2f}")

        # 2. Place the UNDER-COVERING stop: only 4 shares, well below market
        #    (price*0.85 → can't trigger). The 2 un-trimmed shares are the naked gap.
        stop_price = round(fill_price * 0.85, 2)
        stop = await alpaca_client.place_stop_order(
            _TEST_TICKER, _UNDER_QTY, stop_price, account_mode=_ACCOUNT_MODE,
        )
        stop_id = stop["id"]
        logger.info(
            f"UNDER-covering stop placed: {_UNDER_QTY} sh @ ${stop_price} id={stop_id} "
            f"(position is {_TEST_QTY} — {_TEST_QTY - _UNDER_QTY} sh naked)"
        )

        # Poll the stop to CONFIRMED-LIVE before calling the invariant. A
        # pending_new stop is invisible to _ensure_stop_coverage's live-stop scan
        # → it would take the PLACE branch and create a 2nd stop.
        st = await _poll_order_status(stop_id, _ACCOUNT_MODE, _LIVE_STATUSES)
        if st not in _LIVE_STATUSES:
            logger.error(f"SETUP FAIL: under-covering stop not confirmed live (status={st})")
            return 2
        logger.info(f"under-covering stop confirmed live (status={st})")

        # Pre-assert the setup state: exactly one live sell-stop, qty 4.
        pre = await _live_sell_stops(_ACCOUNT_MODE)
        if len(pre) != 1 or int(float(pre[0].get("qty") or 0)) != _UNDER_QTY:
            logger.error(
                f"SETUP FAIL: expected exactly one {_UNDER_QTY}-sh live stop, got "
                f"{[(o.get('id','?')[:8], o.get('qty')) for o in pre]}"
            )
            return 2

        # 3. Sentinel trade row: remaining_shares=6, stop_order_id=<4-sh stop>.
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
        logger.info(
            f"sentinel trade row id={trade_id} inserted "
            f"(remaining={_TEST_QTY}, stop_order_id={stop_id})"
        )

        # 4. THE FUNCTION UNDER TEST — first call. Should REPLACE 4→6.
        ret1 = await _ensure_stop_coverage(
            trade_id, _TEST_TICKER, float(_TEST_QTY), float(stop_price),
            _SENTINEL_SIGNAL_TYPE, _ACCOUNT_MODE,
        )
        logger.info(f"_ensure_stop_coverage (call 1) returned: {ret1!r}")

        # 5a. ASSERT: return indicates a coverage REPAIR (not a ⚠️ failure string).
        if _is_failure_string(ret1) and not _is_repair_string(ret1):
            logger.error(
                f"FINDING: _ensure_stop_coverage returned a FAILURE string, not a "
                f"repair: {ret1!r}. This is real Alpaca behavior the mocks miss "
                f"(e.g. replace-UP 4→6 rejected). Reported, NOT retried."
            )
            return 1
        if not _is_repair_string(ret1):
            logger.error(
                f"FAIL: expected a coverage-repair return string, got {ret1!r} "
                f"(None would mean it thought coverage was already adequate)."
            )
            return 1

        # 5b. ASSERT: read the new stop_order_id the function wrote to the DB
        #     (synchronous via set_stop_order_id, NOT WS-dependent → reliable now).
        async with pool.acquire() as conn:
            new_stop_id = await conn.fetchval(
                "SELECT stop_order_id FROM mi_live_trades WHERE id = $1", trade_id)
        if not new_stop_id:
            logger.error("FAIL: DB stop_order_id is NULL after repair")
            return 1
        if new_stop_id != stop_id:
            logger.info(f"DB stop_order_id advanced {stop_id[:8]} → {new_stop_id[:8]} (replace issued new id)")
        # Track the live id for teardown.
        stop_id = new_stop_id

        # Poll the NEW stop to confirmed-live before asserting (the replace passes
        # the old id through pending_replace/replaced; the new id transits
        # pending_new → accepted). Asserting/recalling before it settles would
        # see zero live stops and mislead.
        st2 = await _poll_order_status(new_stop_id, _ACCOUNT_MODE, _LIVE_STATUSES)
        if st2 not in _LIVE_STATUSES:
            logger.error(f"FAIL: replacement stop {new_stop_id[:8]} not confirmed live (status={st2})")
            return 1

        # 5c. ASSERT: EXACTLY ONE live sell-stop on F, covering 6 — no duplicate.
        after1 = await _live_sell_stops(_ACCOUNT_MODE)
        if len(after1) != 1:
            logger.error(
                f"FAIL: expected EXACTLY ONE live sell-stop after repair, got "
                f"{len(after1)}: {[(o.get('id','?')[:8], o.get('qty')) for o in after1]} "
                f"— a duplicate was created (the never-naked bug shape)."
            )
            return 1
        cov_qty = int(float(after1[0].get("qty") or 0))
        if cov_qty != _TEST_QTY:
            logger.error(f"FAIL: live stop covers {cov_qty}, expected {_TEST_QTY}")
            return 1
        logger.info(
            f"BROKER OK (call 1): exactly ONE live sell-stop {after1[0].get('id','?')[:8]} "
            f"covering {cov_qty} sh (was {_UNDER_QTY}) — under-cover repaired, no duplicate"
        )

        # 6. IDEMPOTENCY — second call should be a strict no-op.
        ret2 = await _ensure_stop_coverage(
            trade_id, _TEST_TICKER, float(_TEST_QTY), float(stop_price),
            _SENTINEL_SIGNAL_TYPE, _ACCOUNT_MODE,
        )
        logger.info(f"_ensure_stop_coverage (call 2) returned: {ret2!r}")
        if ret2 is not None:
            logger.error(f"FAIL: idempotent 2nd call returned {ret2!r}, expected None (no-op)")
            return 1
        # stop_order_id unchanged (no new order issued) — the strongest no-op proof.
        async with pool.acquire() as conn:
            id_after2 = await conn.fetchval(
                "SELECT stop_order_id FROM mi_live_trades WHERE id = $1", trade_id)
        if id_after2 != new_stop_id:
            logger.error(
                f"FAIL: idempotent 2nd call changed stop_order_id {new_stop_id[:8]} → "
                f"{(id_after2 or 'NULL')[:8]} — a new order was issued (not a no-op)"
            )
            return 1
        after2 = await _live_sell_stops(_ACCOUNT_MODE)
        if len(after2) != 1 or int(float(after2[0].get("qty") or 0)) != _TEST_QTY:
            logger.error(
                f"FAIL: after idempotent call, expected exactly one {_TEST_QTY}-sh stop, "
                f"got {[(o.get('id','?')[:8], o.get('qty')) for o in after2]}"
            )
            return 1
        logger.info(
            f"IDEMPOTENT OK (call 2): returned None, stop_order_id unchanged "
            f"({new_stop_id[:8]}), still exactly one {_TEST_QTY}-sh stop — no new order"
        )

        logger.info("PASS — never-naked coverage invariant validated end-to-end against real paper broker")
        return 0

    except Exception as e:
        logger.error(f"FAIL (exception): {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        return 1
    finally:
        # Teardown — survives partial failure; loudly reports residue. Order
        # matters: cancel orders FIRST (release held_for_orders), THEN flatten.
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

        # Verify F flat + zero sentinel rows, and print the cleanup outcome.
        try:
            pos = await alpaca_client.get_position(_TEST_TICKER, account_mode=_ACCOUNT_MODE)
            pos_qty = abs(int(float(pos.get("qty", 0)))) if pos else 0
            open_orders = await _open_test_orders(_ACCOUNT_MODE)
            sentinel_left = await _count_sentinel_rows()
            logger.info(
                f"CLEANUP VERIFY: {_TEST_TICKER} position qty={pos_qty}, "
                f"open {_TEST_TICKER} orders={len(open_orders)}, sentinel rows={sentinel_left}"
            )
            if pos_qty == 0 and len(open_orders) == 0 and sentinel_left == 0:
                logger.info(
                    f"CLEANUP OK: {_TEST_TICKER} is FLAT, no open {_TEST_TICKER} orders, "
                    f"zero sentinel rows."
                )
            else:
                residue.append(
                    f"VERIFY mismatch — pos_qty={pos_qty}, open_orders={len(open_orders)}, "
                    f"sentinel_rows={sentinel_left}"
                )
        except Exception as e:
            residue.append(f"cleanup verify failed: {e}")

        if residue:
            logger.error(
                "TEARDOWN INCOMPLETE — MANUAL CLEANUP NEEDED:\n  "
                + "\n  ".join(residue)
                + f"\n  (ticker={_TEST_TICKER}, trade_id={trade_id}, "
                f"stop_id={stop_id}, account={_ACCOUNT_MODE})"
            )


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
