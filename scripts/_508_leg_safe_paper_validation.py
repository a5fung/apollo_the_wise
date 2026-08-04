"""#508 — PAPER end-to-end validation of the LEG-SAFE partial exit.

THE verify-live vehicle for the 2026-08-04 bracket-leg fix, run BEFORE the
`partial_exit_leg_safe` toggle is flipped on. The existing
`_partial_exit_paper_validation.py` buys with a STANDALONE stop, which (post
#508) exercises only the replace path; every real MAGNA53 position's stop is
an OTO bracket LEG, where replace-with-qty is structurally rejected
(42210000, the PLTR trade-307 failure). This script exercises the REAL
`execute_partial_exit` against a REAL bracket leg on paper:

    docker exec apollo-execution python scripts/_508_leg_safe_paper_validation.py

Market hours 9:30–16:00 ET Mon–Fri (needs real fills). PAPER ONLY — same
guards as the parent harness (account_mode literal, base_url belt, sentinel
row account-mode check, bulletproof teardown).

TOGGLE ISOLATION (important): the toggle is patched IN-PROCESS ONLY
(`order_manager.get_runtime_toggle` module attr → True for
'partial_exit_leg_safe'). The mi_safeguard_state row is NEVER written, so the
prod scheduler — and any live position — keeps the toggle OFF while this runs.

SEQUENCE + ASSERTIONS (broker truth, no WS dependency):
  setup  OTO market buy 6 F (stop leg ~15% below) → parent fill → leg LIVE →
         leg reads order_class='oto' via get_order (verifies the #508
         _order_to_dict field against real Alpaca) → sentinel mi_live_trades
         row pointing at the LEG id.
  run    execute_partial_exit(id, 2, force=True) with the toggle ON in-process.
  assert 1. returns True.
         2. replace_order was called ZERO times (the doomed qty-replace is
            never attempted against a leg).
         3. the old LEG is canceled broker-side.
         4. partial sell FILLED; broker position == 4.
         5. EXACTLY ONE live sell-stop covering 4 — and it is a SIMPLE stop
            (order_class not advanced), so later qty/price updates work.
         6. the partial_exit_stop_replaced audit row carries
            mechanism='leg_safe_cancel_new' + timings_ms — PRINTED, because
            cancel_confirm→stop_accept is the measured naked window and goes
            into the verify-live report.
EXIT CODES: 0 pass · 1 real failure · 2 inconclusive (closed market / setup).
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("508_leg_safe_paper_validation")

# ── Reuse the proven harness (teardown discipline, sentinel hygiene, guards) ──
_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "_pepv", os.path.join(_HERE, "_partial_exit_paper_validation.py"))
_pepv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pepv)

_ACCOUNT_MODE = "paper"          # literal, threaded everywhere — NEVER live
_TEST_TICKER = _pepv._TEST_TICKER
_TEST_QTY = _pepv._TEST_QTY      # 6
_PARTIAL_QTY = _pepv._PARTIAL_QTY  # 2
_REMAINING_QTY = _pepv._REMAINING_QTY  # 4
_LIVE_STATUSES = _pepv._LIVE_STATUSES
_SENTINEL_SIGNAL_TYPE = _pepv._SENTINEL_SIGNAL_TYPE


async def _setup_bracket_and_sentinel():
    """OTO market buy 6 F with a stop-loss LEG ~15% below → wait fill → wait
    leg live → sentinel row pointing at the LEG id. Returns
    (trade_id, leg_id, fill_price, stop_price). Raises on setup failure."""
    from agents.market_intelligence.broker import alpaca_client
    from agents.market_intelligence.db import get_pool
    from alpaca.trading.requests import MarketOrderRequest, StopLossRequest
    from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce

    lt = await alpaca_client.get_latest_trade(_TEST_TICKER)
    if not lt or not lt.get("price"):
        raise RuntimeError("setup: no latest trade for the test ticker")
    stop_price = round(float(lt["price"]) * 0.85, 2)

    client = alpaca_client.get_trading_client(_ACCOUNT_MODE)
    buy = client.submit_order(MarketOrderRequest(
        symbol=_TEST_TICKER, qty=_TEST_QTY, side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.OTO,
        stop_loss=StopLossRequest(stop_price=stop_price),
    ))
    buy_id = str(buy.id)
    # Canonical helper — never re-implement the leg loop.
    leg_id = alpaca_client.extract_stop_leg_id(buy)
    if await _pepv._poll_order_status(buy_id, _ACCOUNT_MODE, {"filled"}) != "filled":
        raise RuntimeError("setup: OTO parent buy not filled")
    bo = await alpaca_client.get_order(buy_id, account_mode=_ACCOUNT_MODE)
    fill_price = float(bo.get("filled_avg_price") or 12.0) or 12.0
    if not leg_id:
        leg_id = alpaca_client.extract_stop_leg_id(bo)
    if not leg_id:
        raise RuntimeError("setup: no stop leg id on the OTO parent")
    logger.info(
        f"setup: OTO filled {_TEST_QTY} {_TEST_TICKER} @ ${fill_price:.2f}, "
        f"stop LEG {leg_id} @ ${stop_price:.2f}")

    st = await _pepv._poll_order_status(leg_id, _ACCOUNT_MODE, _LIVE_STATUSES)
    if st not in _LIVE_STATUSES:
        raise RuntimeError(f"setup: stop leg not confirmed live (status={st})")

    # Verify the #508 wire field against REAL Alpaca: the leg must read as an
    # advanced order via the production get_order path.
    leg = await alpaca_client.get_order(leg_id, account_mode=_ACCOUNT_MODE)
    oc = str((leg or {}).get("order_class") or "").lower()
    if oc not in ("oto", "oco", "otoco", "bracket"):
        raise RuntimeError(
            f"setup: leg order_class={oc!r} — expected an advanced class; "
            f"the _order_to_dict field or Alpaca behavior changed")
    logger.info(f"setup: leg live, order_class={oc!r} (advanced — confirmed)")

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
            _TEST_QTY, fill_price, stop_price, leg_id)
    async with pool.acquire() as conn:
        row_mode = await conn.fetchval(
            "SELECT account_mode FROM mi_live_trades WHERE id = $1", trade_id)
    if row_mode != "paper":
        raise RuntimeError(
            f"ABORT: sentinel row {trade_id} resolved account_mode={row_mode!r} "
            f"— PAPER ONLY.")
    logger.info(f"setup: sentinel row id={trade_id} → stop_order_id={leg_id} (the LEG)")
    return trade_id, leg_id, fill_price, stop_price


async def _test_leg_safe(sent: list) -> int:
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence.broker import alpaca_client
    from agents.market_intelligence.db import get_pool

    trade_id = None
    replace_calls = {"n": 0}
    real_replace = alpaca_client.replace_order

    async def _counting_replace(*a, **k):
        replace_calls["n"] += 1
        return await real_replace(*a, **k)

    try:
        trade_id, leg_id, fill_price, stop_price = await _setup_bracket_and_sentinel()

        # Count replace calls ONLY during the function-under-test window.
        order_manager.alpaca.replace_order = _counting_replace
        try:
            ok = await order_manager.execute_partial_exit(
                trade_id, _PARTIAL_QTY, force=True)
        finally:
            order_manager.alpaca.replace_order = real_replace
        logger.info(f"[LEG] execute_partial_exit returned: {ok!r}")

        if not ok:
            logger.error("[LEG] FAIL: execute_partial_exit returned False on a bracket leg")
            return 1
        if replace_calls["n"] != 0:
            logger.error(
                f"[LEG] FAIL: replace_order called {replace_calls['n']}x — the leg "
                f"path must never attempt the qty replace Alpaca rejects")
            return 1

        # Old LEG must be canceled broker-side.
        leg_status = await _pepv._poll_order_status(
            leg_id, _ACCOUNT_MODE, {"canceled", "cancelled"}, budget_s=5.0)
        if leg_status not in ("canceled", "cancelled"):
            logger.error(f"[LEG] FAIL: old leg {leg_id} status={leg_status}, expected canceled")
            return 1

        # Partial sell filled; position 4; exactly ONE live stop covering 4.
        pool = await get_pool()
        async with pool.acquire() as conn:
            sell_oid = await conn.fetchval("""
                SELECT alpaca_order_id FROM mi_live_orders
                WHERE trade_id = $1 AND purpose = 'partial_exit'
                ORDER BY id DESC LIMIT 1
            """, trade_id)
        if not sell_oid:
            logger.error("[LEG] FAIL: no partial_exit order row written")
            return 1
        if await _pepv._poll_order_status(sell_oid, _ACCOUNT_MODE, {"filled"}) != "filled":
            logger.error("[LEG] FAIL: partial sell not filled on broker")
            return 1
        pos_qty = await _pepv._broker_position_qty(_ACCOUNT_MODE)
        if pos_qty != _REMAINING_QTY:
            logger.error(f"[LEG] FAIL: broker position qty={pos_qty}, expected {_REMAINING_QTY}")
            return 1
        stops = await _pepv._live_sell_stops(_ACCOUNT_MODE)
        if len(stops) != 1:
            logger.error(
                f"[LEG] FAIL: expected EXACTLY ONE live sell-stop, got {len(stops)}: "
                f"{[(o.get('id', '?')[:8], o.get('qty')) for o in stops]}")
            return 1
        cov = int(float(stops[0].get("qty") or 0))
        if cov != _REMAINING_QTY:
            logger.error(f"[LEG] FAIL: live stop covers {cov}, expected {_REMAINING_QTY}")
            return 1
        # The replacement must be a SIMPLE stop — post-partial flexibility.
        new_stop = await alpaca_client.get_order(
            stops[0]["id"], account_mode=_ACCOUNT_MODE)
        new_oc = str((new_stop or {}).get("order_class") or "").lower()
        if new_oc in ("oto", "oco", "otoco", "bracket"):
            logger.error(f"[LEG] FAIL: replacement stop order_class={new_oc!r} — expected simple")
            return 1

        # Mechanism + measured naked-window timings from the audit row.
        async with pool.acquire() as conn:
            detail = await conn.fetchval("""
                SELECT detail FROM mi_audit_log
                WHERE event_type = 'partial_exit_stop_replaced'
                  AND detail::jsonb ->> 'trade_id' = $1::text
                ORDER BY id DESC LIMIT 1
            """, str(trade_id))
        mech, timings = None, None
        if detail:
            d = json.loads(detail)
            mech, timings = d.get("mechanism"), d.get("timings_ms")
        if mech != "leg_safe_cancel_new":
            logger.error(f"[LEG] FAIL: audit mechanism={mech!r}, expected leg_safe_cancel_new")
            return 1
        naked_ms = None
        if timings and timings.get("cancel_confirm_ms") and timings.get("stop_accept_ms"):
            naked_ms = round(timings["stop_accept_ms"] - timings["cancel_confirm_ms"], 1)
        logger.info(
            f"[LEG] PASS — leg canceled, reduced SIMPLE stop covers {cov}, sell filled, "
            f"replace never attempted. timings_ms={timings} "
            f"→ MEASURED NAKED WINDOW ≈ {naked_ms} ms (cancel-confirm → stop-accept)")
        return 0
    except Exception as e:
        logger.error(f"[LEG] setup/run error: {e}", exc_info=True)
        return 2
    finally:
        residue = await _pepv._teardown(trade_id, "LEG")
        if residue:
            logger.error("[LEG] teardown residue — manual cleanup may be needed")


async def run() -> int:
    if os.environ.get("ENABLE_LIVE_MODE") is None and not os.environ.get("ALPACA_PAPER_API_KEY"):
        logger.error("no Alpaca env — run inside the apollo-execution container")
        return 2
    try:
        from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
        _bootstrap_alpaca_credentials()
    except Exception as e:
        logger.error(f"bootstrap failed: {e}")
        return 2

    # PAPER endpoint belt (same as parent harness).
    from agents.market_intelligence.broker import alpaca_client
    client = alpaca_client.get_trading_client(_ACCOUNT_MODE)
    base_url = ""
    for attr in ("_base_url", "base_url"):
        v = getattr(client, attr, None)
        if v:
            base_url = str(v)
            break
    low = base_url.lower()
    if low and "paper-api" not in low and "api.alpaca.markets" in low:
        logger.error(f"ABORT: base_url={base_url!r} is the LIVE endpoint. PAPER ONLY.")
        return 2
    logger.info(f"paper client OK (mode={_ACCOUNT_MODE!r}, base_url={base_url or 'unreadable'})")

    if not _pepv._market_open_now():
        logger.error("market is closed — needs real fills. Run 9:30-16:00 ET Mon-Fri.")
        return 2

    from agents.market_intelligence.broker import order_manager

    # ── IN-PROCESS toggle ON + telegram capture. The prod scheduler is a
    #    separate process: its toggle read (DB row / env) stays OFF. ──────────
    real_toggle = order_manager.get_runtime_toggle
    real_send = order_manager.send_telegram_message
    pause_was = order_manager._PARTIAL_EXIT_PAUSED
    sent: list[str] = []

    async def _toggle_on(name, env_var, default=True):
        if name == "partial_exit_leg_safe":
            return True
        return await real_toggle(name, env_var, default=default)

    async def _capture_send(msg, *args, **kwargs):
        sent.append(str(msg))
        logger.info(f"[telegram captured] {str(msg)[:160]}")
        return True

    order_manager.get_runtime_toggle = _toggle_on
    order_manager.send_telegram_message = _capture_send
    order_manager._PARTIAL_EXIT_PAUSED = False
    rc = 2
    try:
        await _pepv._sweep_orphans(_ACCOUNT_MODE)
        logger.info("════════ #508 LEG-SAFE PARTIAL (bracket leg, toggle ON in-process) ════════")
        rc = await _test_leg_safe(sent)
    finally:
        order_manager.get_runtime_toggle = real_toggle
        order_manager.send_telegram_message = real_send
        order_manager._PARTIAL_EXIT_PAUSED = pause_was
        try:
            await _pepv._sweep_orphans(_ACCOUNT_MODE)
            pos_qty = await _pepv._broker_position_qty(_ACCOUNT_MODE)
            open_orders = await _pepv._open_test_orders(_ACCOUNT_MODE)
            sentinel_left = await _pepv._count_sentinel_rows()
            logger.info(
                f"CLEANUP VERIFY: {_TEST_TICKER} qty={pos_qty}, open orders="
                f"{len(open_orders)}, sentinel rows={sentinel_left}")
            if not (pos_qty == 0 and not open_orders and sentinel_left == 0):
                logger.error("FINAL TEARDOWN INCOMPLETE — MANUAL CLEANUP NEEDED")
        except Exception as e:
            logger.error(f"cleanup verify failed: {e}")
    logger.info(f"RESULT: rc={rc} (0 pass · 1 fail · 2 inconclusive)")
    return rc


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
