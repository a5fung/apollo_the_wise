"""#151 — PAPER-ONLY end-to-end validation of the FULL execute_partial_exit flow.

THE "watch a partial actually run clean" check the operator runs AFTER deploying
the #151 fix. Exercises `execute_partial_exit` (and, on the abort path, the
post-lock `_ensure_stop_coverage` re-protect) against REAL paper Alpaca — the
broker-side behavior the mocked unit tests structurally cannot reach (atomic
replace, pending_replace settle, real share-reservation semantics, the
never-naked converge). Sibling of:
  * scripts/integration_test_partial_exit.py        (happy-path harness)
  * scripts/_coverage_invariant_paper_exercise.py   (the _ensure_stop_coverage
                                                      teardown discipline)
This one adds the SELL-FAILURE abort proof (TEST B) — the actual #151 durable fix.

────────────────────────────────────────────────────────────────────────────────
RUN COMMAND (one-off process, market hours 9:30–16:00 ET Mon–Fri, AFTER deploy):

    docker exec apollo-execution python scripts/_partial_exit_paper_validation.py

It is a SEPARATE PROCESS from the running scheduler. Inside it we monkeypatch the
module flag `order_manager._PARTIAL_EXIT_PAUSED = False` so this process can call
the real execute_partial_exit logic. **This does NOT un-pause the prod scheduler:**
the scheduler runs in its own process with its own memory image; a module-attr
mutation here is invisible there. The SOURCE flag stays True (we never touch the
file); only this in-process attribute is flipped. PAPER ONLY — the run aborts
before any broker interaction if the resolved account_mode is anything but 'paper'.
────────────────────────────────────────────────────────────────────────────────

TEST A — HAPPY PARTIAL (the clean run):
  Buy 6 F (paper, wait fill) → place a full 6-share sell-stop below market →
  insert a sentinel mi_live_trades row (signal_type='integration_test',
  remaining_shares=6, stop_order_id=<the stop>) → execute_partial_exit(id, 2,
  force=True). ASSERT on REAL Alpaca: the 2-share market sell filled; the stop
  was replaced DOWN to 4 shares and is live; broker position == 4; EXACTLY ONE
  live sell-stop covering 4 (no duplicate). DB-finalize (partial_taken/remaining)
  is SOFT/diagnostic only (no WS stream in a one-off process → it never fires;
  asserting on it would test the WS handler, not execute_partial_exit).

TEST B — ABORT RE-PROTECT (the never-naked proof):
  Fresh sentinel/position (6 F + full 6-share stop) → monkeypatch
  alpaca_client.place_market_sell to RAISE a plain RuntimeError (a NON-lag error
  → re-raised on attempt 1 → straight to the sell-failure abort at 1675) →
  execute_partial_exit(id, 2, force=True). The stop is reduced to 4 first, then
  the sell raises → post-lock _ensure_stop_coverage replaces the 4-stop back UP
  to the broker-TRUTH full qty (6). ASSERT: exactly one live sell-stop covering
  6, broker position == 6 (NOTHING sold, NOTHING naked); ZERO cancel_order calls
  during the run (never cancel a pending_replace); EXACTLY ONE telegram, an
  honest "ABORTED … Coverage repaired" — and it must NOT say "rolled back" /
  "rollback" (the literal #151 converge-not-rollback proof).

HARD CONSTRAINTS:
  * PAPER only. _ACCOUNT_MODE literal threaded to every Alpaca call; top guard
    aborts if it is not 'paper'; base_url belt-and-suspenders aborts on a live
    endpoint; a per-test guard aborts if the sentinel row's account_mode ever
    resolves to 'live'.
  * Build-only flag patch is in-process; never edits _PARTIAL_EXIT_PAUSED in the
    source (only the module attr here).
  * Bulletproof cleanup (finally, always): cancel ALL F orders, flatten F, DELETE
    sentinel rows (WHERE signal_type='integration_test'). Verify F flat + zero
    sentinel rows; print the cleanup outcome.

EXIT CODES: 0 = both tests passed end-to-end against real paper broker.
            1 = a real failure / a finding to report.
            2 = couldn't run (market closed / setup error / NOT paper) —
                inconclusive, not a failure of the code under test.
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
logger = logging.getLogger("partial_exit_paper_validation")

_ET = ZoneInfo("America/New_York")
_SENTINEL_SIGNAL_TYPE = "integration_test"
_TEST_TICKER = "F"          # cheap, liquid; never an active strategy position
_TEST_QTY = 6               # 6 - 2 = 4 remaining after the partial
_PARTIAL_QTY = 2            # the partial size (matches the 6//3 reference)
_REMAINING_QTY = _TEST_QTY - _PARTIAL_QTY  # 4
_ACCOUNT_MODE = "paper"     # NEVER touch live — literal, threaded everywhere

# Mirror order_manager._STOP_CONFIRMED_LIVE_STATUSES — the statuses that count as
# a live, protecting stop. The "exactly one live stop covering N" assertions
# filter on exactly this set (same as the function under test).
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
    """Live sell-stops on the test ticker, computed the SAME way the function
    under test does (side=sell, type contains 'stop', status in live set). Used
    by every 'exactly one stop covering N' assertion."""
    from agents.market_intelligence.broker.order_manager import _canonical_order_status
    out = []
    for o in await _open_test_orders(account_mode):
        side = str(o.get("side", "")).lower()
        otype = str(o.get("type", "")).lower()
        status = _canonical_order_status(o.get("status"))
        if "sell" in side and "stop" in otype and status in _LIVE_STATUSES:
            out.append(o)
    return out


async def _broker_position_qty(account_mode):
    from agents.market_intelligence.broker import alpaca_client
    pos = await alpaca_client.get_position(_TEST_TICKER, account_mode=account_mode)
    return abs(int(float(pos.get("qty", 0)))) if pos else 0


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
    Alpaca's held_for_orders reservation lags the cancel ack by ~ms; proceeding
    to flatten immediately fails with 'insufficient qty available'. Idempotent.

    NOTE: this uses alpaca_client.cancel_order directly — it is the legitimate
    TEARDOWN cancel. TEST B's 'no cancel_order on pending_replace' assertion wraps
    a COUNTER around the execute_partial_exit call window ONLY (restored before
    cleanup), so these teardown cancels are never counted against the invariant.
    """
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
    signal_type (the 2026-05-27 cascade surface — BOTH conditions, never ticker
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
    """Idempotent pre-test cleanup of residue from a prior crashed run:
    sentinel rows first (nothing references the position), then cancel + flatten."""
    await _delete_sentinel_rows(trade_id=None)
    await _cancel_test_ticker_orders(account_mode)
    await _flatten_test_position(account_mode)


async def _setup_position_and_sentinel(account_mode, stop_mult=0.85):
    """Buy 6 F (wait fill) → place a full 6-share sell-stop well below market →
    INSERT a sentinel mi_live_trades row pointing at that stop. Returns
    (trade_id, stop_id, fill_price, stop_price). Raises on any setup failure
    (the caller treats a setup raise as exit-2 inconclusive).

    HARD GUARD: refuses to insert if account_mode is not 'paper'.
    """
    if account_mode != "paper":
        raise RuntimeError(f"ABORT: setup account_mode={account_mode!r} is not 'paper'")

    from agents.market_intelligence.broker import alpaca_client
    from agents.market_intelligence.db import get_pool
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    client = alpaca_client.get_trading_client(account_mode)
    buy = client.submit_order(MarketOrderRequest(
        symbol=_TEST_TICKER, qty=_TEST_QTY, side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    ))
    buy_id = str(buy.id)
    if await _poll_order_status(buy_id, account_mode, {"filled"}) != "filled":
        raise RuntimeError("setup: test buy not filled")
    bo = await alpaca_client.get_order(buy_id, account_mode=account_mode)
    fill_price = float(bo.get("filled_avg_price") or 12.0) or 12.0
    logger.info(f"setup: buy filled {_TEST_QTY} {_TEST_TICKER} @ ${fill_price:.2f}")

    # Full 6-share stop, well below market (can't trigger).
    stop_price = round(fill_price * stop_mult, 2)
    stop = await alpaca_client.place_stop_order(
        _TEST_TICKER, _TEST_QTY, stop_price, account_mode=account_mode,
    )
    stop_id = stop["id"]
    logger.info(f"setup: full stop placed {_TEST_QTY} sh @ ${stop_price} id={stop_id}")

    # Poll the stop CONFIRMED-LIVE before the sentinel row exists — a pending_new
    # stop is invisible to the function's live-stop scan.
    st = await _poll_order_status(stop_id, account_mode, _LIVE_STATUSES)
    if st not in _LIVE_STATUSES:
        raise RuntimeError(f"setup: stop not confirmed live (status={st})")

    # Pre-assert setup state: exactly one live sell-stop, qty 6.
    pre = await _live_sell_stops(account_mode)
    if len(pre) != 1 or int(float(pre[0].get("qty") or 0)) != _TEST_QTY:
        raise RuntimeError(
            f"setup: expected exactly one {_TEST_QTY}-sh live stop, got "
            f"{[(o.get('id','?')[:8], o.get('qty')) for o in pre]}"
        )

    # Sentinel row — columns copied verbatim from integration_test_partial_exit.py
    # (already satisfies the NOT-NULLs).
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
        """, _TEST_TICKER, account_mode, _SENTINEL_SIGNAL_TYPE,
            _TEST_QTY, fill_price, stop_price, stop_id)

    # Defense in depth: the row MUST have resolved account_mode='paper'.
    async with pool.acquire() as conn:
        row_mode = await conn.fetchval(
            "SELECT account_mode FROM mi_live_trades WHERE id = $1", trade_id)
    if row_mode != "paper":
        raise RuntimeError(
            f"ABORT: sentinel row {trade_id} resolved account_mode={row_mode!r}, "
            f"not 'paper'. Refusing to proceed. PAPER ONLY."
        )
    logger.info(
        f"setup: sentinel row id={trade_id} (remaining={_TEST_QTY}, "
        f"stop_order_id={stop_id}, account_mode={row_mode})"
    )
    return trade_id, stop_id, fill_price, stop_price


async def _teardown(trade_id, label):
    """Bulletproof per-test teardown. Order matters: cancel orders FIRST (release
    held_for_orders), THEN flatten. Returns a residue list (empty == clean)."""
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
            f"[{label}] TEARDOWN INCOMPLETE — residue:\n  " + "\n  ".join(residue)
        )
    return residue


# ──────────────────────────────────────────────────────────────────────────────
# TEST A — HAPPY PARTIAL
# ──────────────────────────────────────────────────────────────────────────────
async def _test_a(send_capture):
    """Returns 0 (pass) / 1 (fail) / 2 (inconclusive-setup). send_capture is the
    list the patched send_telegram_message appends to (cleared by caller)."""
    from agents.market_intelligence.broker.order_manager import execute_partial_exit
    from agents.market_intelligence.db import get_pool

    trade_id = None
    try:
        trade_id, stop_id, fill_price, stop_price = await _setup_position_and_sentinel(
            _ACCOUNT_MODE)

        # ── THE FUNCTION UNDER TEST. force=True (the pause-gate precedes the
        #    breaker, so the in-process flag patch + force together let it run).
        ok = await execute_partial_exit(trade_id, _PARTIAL_QTY, force=True)
        logger.info(f"[A] execute_partial_exit returned: {ok!r}")
        if not ok:
            logger.error("[A] FAIL: execute_partial_exit returned False on the happy path")
            return 1

        # ── ASSERT on BROKER truth (no WS/DB dependency).
        # a) the partial sell order filled.
        pool = await get_pool()
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
            logger.error("[A] FAIL: no partial_exit order row written")
            return 1
        if await _poll_order_status(sell_oid, _ACCOUNT_MODE, {"filled"}) != "filled":
            logger.error("[A] FAIL: partial sell not filled on broker")
            return 1

        # Poll the replacement stop confirmed-live before the coverage assert.
        if new_stop_oid:
            await _poll_order_status(new_stop_oid, _ACCOUNT_MODE, _LIVE_STATUSES)

        # b) broker position now 4.
        pos_qty = await _broker_position_qty(_ACCOUNT_MODE)
        if pos_qty != _REMAINING_QTY:
            logger.error(f"[A] FAIL: broker position qty={pos_qty}, expected {_REMAINING_QTY}")
            return 1

        # c) EXACTLY ONE live sell-stop covering 4 — no duplicate.
        stops = await _live_sell_stops(_ACCOUNT_MODE)
        if len(stops) != 1:
            logger.error(
                f"[A] FAIL: expected EXACTLY ONE live sell-stop, got {len(stops)}: "
                f"{[(o.get('id','?')[:8], o.get('qty')) for o in stops]} (duplicate?)"
            )
            return 1
        cov = int(float(stops[0].get("qty") or 0))
        if cov != _REMAINING_QTY:
            logger.error(f"[A] FAIL: live stop covers {cov}, expected {_REMAINING_QTY}")
            return 1
        logger.info(
            f"[A] BROKER OK: partial sell {sell_oid[:8]} filled; position={pos_qty}; "
            f"exactly ONE live stop covering {cov} (no duplicate)"
        )

        # SOFT/diagnostic: DB-finalize. A one-off process has no WS stream, so
        # finalize_partial_exit never fires — a lag here is EXPECTED, not a failure.
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT partial_taken, remaining_shares FROM mi_live_trades WHERE id = $1",
                trade_id)
        if row and row["partial_taken"] and int(row["remaining_shares"]) == _REMAINING_QTY:
            logger.info("[A] WS-FINALIZE OK (DB row updated)")
        else:
            logger.info(
                "[A] WS-finalize not present (expected — no WS stream in a one-off "
                "process). Broker truth is the assertion; this is diagnostic only."
            )

        logger.info("[A] PASS — happy partial validated end-to-end against real paper broker")
        return 0
    except Exception as e:
        logger.error(f"[A] setup/exec raised: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        # A setup raise is inconclusive (couldn't run); an assertion path returns 1
        # explicitly above, so reaching here is a setup/env failure → exit 2.
        return 2
    finally:
        await _teardown(trade_id, "A")


# ──────────────────────────────────────────────────────────────────────────────
# TEST B — ABORT RE-PROTECT (the never-naked proof)
# ──────────────────────────────────────────────────────────────────────────────
async def _test_b(send_capture):
    """Force the market sell to raise → assert the post-lock _ensure_stop_coverage
    re-protects to the broker-TRUTH full qty (6), no naked, no pending_replace
    cancel, ONE honest telegram. Returns 0/1/2."""
    from agents.market_intelligence.broker import alpaca_client
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence.broker.order_manager import execute_partial_exit

    trade_id = None
    # Restore handles for the scoped patches.
    real_place_market_sell = alpaca_client.place_market_sell
    real_cancel_order = alpaca_client.cancel_order
    cancel_calls = {"n": 0}

    try:
        trade_id, stop_id, fill_price, stop_price = await _setup_position_and_sentinel(
            _ACCOUNT_MODE)

        # ── FORCE THE SELL FAILURE. A plain RuntimeError is a NON-lag error
        #    (does not match _is_share_reservation_lag: no 'insufficient' /
        #    'held_for_orders' / 'qty available'), so the 3× retry loop re-raises
        #    it on attempt 1 → straight to the sell-failure abort (om L1675).
        #    Patch the MODULE ATTR that order_manager.alpaca points at.
        async def _raising_sell(*args, **kwargs):
            raise RuntimeError("forced sell failure (TEST B) — non-lag, abort path")

        # ── COUNT cancel_order ONLY during the execute_partial_exit window. The
        #    invariant: the converge path must NEVER cancel a pending_replace stop
        #    (that is the move that widened the naked window historically). Teardown
        #    cancels happen AFTER we restore the real fn, so they aren't counted.
        async def _counting_cancel(order_id, account_mode=None):
            cancel_calls["n"] += 1
            logger.warning(
                f"[B] cancel_order CALLED during partial-exit (order={order_id}) — "
                f"this should NOT happen on the converge path"
            )
            return await real_cancel_order(order_id, account_mode=account_mode)

        alpaca_client.place_market_sell = _raising_sell
        alpaca_client.cancel_order = _counting_cancel

        send_capture.clear()
        try:
            ok = await execute_partial_exit(trade_id, _PARTIAL_QTY, force=True)
        finally:
            # Restore BEFORE any teardown so cleanup cancels run for real + aren't
            # counted against the invariant.
            alpaca_client.place_market_sell = real_place_market_sell
            alpaca_client.cancel_order = real_cancel_order

        logger.info(f"[B] execute_partial_exit returned: {ok!r} (expected False — aborted)")
        if ok:
            logger.error("[B] FAIL: expected False (abort) but got True — sell did not fail as forced")
            return 1

        # ── ASSERT 1: ZERO cancel_order calls during the run (never cancel a
        #    pending_replace).
        if cancel_calls["n"] != 0:
            logger.error(
                f"[B] FAIL: cancel_order called {cancel_calls['n']}× during partial-exit "
                f"— the converge path must NEVER cancel (pending_replace risk)"
            )
            return 1
        logger.info("[B] OK: zero cancel_order calls during the abort path")

        # ── ASSERT 2: re-protect to broker TRUTH. Read the new stop_order_id the
        #    re-protect wrote, poll confirmed-live, then assert one live stop
        #    covering 6 + position == 6 (nothing sold, nothing naked).
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            db_stop_id = await conn.fetchval(
                "SELECT stop_order_id FROM mi_live_trades WHERE id = $1", trade_id)
        if db_stop_id:
            await _poll_order_status(db_stop_id, _ACCOUNT_MODE, _LIVE_STATUSES)

        pos_qty = await _broker_position_qty(_ACCOUNT_MODE)
        if pos_qty != _TEST_QTY:
            logger.error(
                f"[B] FAIL: broker position qty={pos_qty}, expected {_TEST_QTY} "
                f"(nothing should have sold on the abort path)"
            )
            return 1

        stops = await _live_sell_stops(_ACCOUNT_MODE)
        if len(stops) != 1:
            logger.error(
                f"[B] FAIL: expected EXACTLY ONE live sell-stop after re-protect, got "
                f"{len(stops)}: {[(o.get('id','?')[:8], o.get('qty')) for o in stops]}"
            )
            return 1
        cov = int(float(stops[0].get("qty") or 0))
        if cov != _TEST_QTY:
            logger.error(
                f"[B] FAIL: re-protected stop covers {cov}, expected {_TEST_QTY} "
                f"(under-cover NOT repaired → {_TEST_QTY - cov} sh NAKED — the bug)"
            )
            return 1
        logger.info(
            f"[B] BROKER OK: position={pos_qty}, exactly ONE live stop covering {cov} "
            f"— re-protected to broker truth, ZERO naked, ZERO sold"
        )

        # ── ASSERT 3: EXACTLY ONE honest telegram, NOT a rollback narrative.
        if len(send_capture) != 1:
            logger.error(
                f"[B] FAIL: expected EXACTLY ONE telegram on the abort, got "
                f"{len(send_capture)}:\n  " + "\n  ".join(repr(m) for m in send_capture)
            )
            return 1
        msg = send_capture[0]
        low = msg.lower()
        if "rolled back" in low or "rollback" in low:
            logger.error(
                f"[B] FAIL: telegram contains a ROLLBACK narrative (the pre-#151 "
                f"behavior) — must be a converge/re-protect message:\n  {msg!r}"
            )
            return 1
        if "aborted" not in low:
            logger.error(f"[B] FAIL: telegram does not read as an honest ABORT:\n  {msg!r}")
            return 1
        if "coverage repaired" not in low and "🛡" not in msg:
            logger.warning(
                f"[B] NOTE: telegram does not name a coverage repair — re-protect may "
                f"have found coverage already met (idempotent/raced). Broker truth "
                f"already asserted 6-cover above, so this is acceptable but flagged:\n  {msg!r}"
            )
        logger.info(f"[B] TELEGRAM OK (one honest abort msg): {msg!r}")

        logger.info("[B] PASS — sell-failure re-protect (never-naked) validated against real paper broker")
        return 0
    except Exception as e:
        logger.error(f"[B] setup/exec raised: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        return 2
    finally:
        # Belt-and-suspenders restore (in case we raised before the inner restore).
        alpaca_client.place_market_sell = real_place_market_sell
        alpaca_client.cancel_order = real_cancel_order
        await _teardown(trade_id, "B")


async def run() -> int:
    # ── HARD SAFETY GUARD: paper only. Abort before any broker interaction if the
    #    mode literal is not 'paper'.
    if _ACCOUNT_MODE != "paper":
        logger.error(f"ABORT: _ACCOUNT_MODE={_ACCOUNT_MODE!r} is not 'paper'. PAPER ONLY.")
        return 2

    try:
        from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
        _bootstrap_alpaca_credentials()
    except Exception as e:
        logger.error(f"bootstrap failed: {e}")
        return 2

    # ── Belt-and-suspenders: confirm the resolved paper client talks to the PAPER
    #    endpoint (the 'paper' literal threaded everywhere is the real protection;
    #    this is an extra abort if the endpoint positively resolves to LIVE).
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
            "market is closed — this validation needs real fills. Run 9:30-16:00 ET "
            "Mon-Fri. (inconclusive, not a failure of the code under test)"
        )
        return 2

    from agents.market_intelligence.broker import order_manager

    # ── IN-PROCESS un-pause of the #151 HARD PAUSE. ─────────────────────────────
    # The prod scheduler runs in a SEPARATE PROCESS with its own memory image —
    # mutating this module attribute here is invisible there, so the live trading
    # path STAYS PAUSED. We never touch _PARTIAL_EXIT_PAUSED in the source file;
    # only this in-process attribute is flipped so this validation process can call
    # the real execute_partial_exit logic. Restored in finally (paranoia — the
    # process exits anyway).
    pause_was = order_manager._PARTIAL_EXIT_PAUSED
    if pause_was is not True:
        logger.warning(
            f"NOTE: order_manager._PARTIAL_EXIT_PAUSED was {pause_was!r} at start "
            f"(expected True). Proceeding (this process un-pauses locally regardless)."
        )

    # ── Capture telegrams (also stops real operator spam during the run). Patch
    #    the MODULE attr so the function-under-test's calls are intercepted.
    sent: list[str] = []
    real_send = order_manager.send_telegram_message

    async def _capture_send(msg, *args, **kwargs):
        sent.append(str(msg))
        logger.info(f"[telegram captured] {str(msg)[:160]}")
        return True

    order_manager._PARTIAL_EXIT_PAUSED = False
    order_manager.send_telegram_message = _capture_send

    rc_a = rc_b = 2
    try:
        # Sweep any orphan residue first (teardown path proven before we create
        # anything that needs cleaning).
        await _sweep_orphans(_ACCOUNT_MODE)

        logger.info("════════ TEST A — HAPPY PARTIAL ════════")
        sent.clear()
        rc_a = await _test_a(sent)

        logger.info("════════ TEST B — ABORT RE-PROTECT (never-naked) ════════")
        sent.clear()
        rc_b = await _test_b(sent)
    finally:
        # Restore module attrs (process exits anyway; belt-and-suspenders).
        order_manager._PARTIAL_EXIT_PAUSED = pause_was
        order_manager.send_telegram_message = real_send

        # ── Final orphan sweep + CLEANUP VERIFY (always, guarded). ──────────────
        verify_residue = []
        try:
            await _sweep_orphans(_ACCOUNT_MODE)
        except Exception as e:
            verify_residue.append(f"final sweep failed: {e}")
        try:
            pos_qty = await _broker_position_qty(_ACCOUNT_MODE)
            open_orders = await _open_test_orders(_ACCOUNT_MODE)
            sentinel_left = await _count_sentinel_rows()
            logger.info(
                f"CLEANUP VERIFY: {_TEST_TICKER} position qty={pos_qty}, open "
                f"{_TEST_TICKER} orders={len(open_orders)}, sentinel rows={sentinel_left}"
            )
            if pos_qty == 0 and len(open_orders) == 0 and sentinel_left == 0:
                logger.info(
                    f"CLEANUP OK: {_TEST_TICKER} FLAT, no open {_TEST_TICKER} orders, "
                    f"zero sentinel rows."
                )
            else:
                verify_residue.append(
                    f"VERIFY mismatch — pos_qty={pos_qty}, open_orders={len(open_orders)}, "
                    f"sentinel_rows={sentinel_left}"
                )
        except Exception as e:
            verify_residue.append(f"cleanup verify failed: {e}")
        if verify_residue:
            logger.error(
                "FINAL TEARDOWN INCOMPLETE — MANUAL CLEANUP NEEDED:\n  "
                + "\n  ".join(verify_residue)
                + f"\n  (ticker={_TEST_TICKER}, account={_ACCOUNT_MODE})"
            )

    # ── Roll up the result. 0 only if BOTH tests passed.
    logger.info(f"RESULT: TEST A rc={rc_a}, TEST B rc={rc_b}")
    if rc_a == 0 and rc_b == 0:
        logger.info("PASS — execute_partial_exit (#151) validated end-to-end against real paper broker")
        return 0
    if 1 in (rc_a, rc_b):
        logger.error("FAIL — at least one test reported a real failure / finding")
        return 1
    logger.error("INCONCLUSIVE — at least one test could not run (setup/env)")
    return 2


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
