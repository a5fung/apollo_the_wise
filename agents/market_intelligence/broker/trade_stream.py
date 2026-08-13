"""
WebSocket streaming for real-time Alpaca trade updates.

Replaces polling-based fill checking with instant event-driven detection.
Handles: entry fills, stop-loss triggers, Day 1 re-entry, order cancellations.

Dual-account architecture (#66, 2026-05-10): one TradingStream instance
per Alpaca account_mode (paper, live). Each stream's handler is closure-
bound to its account_mode. The central dispatcher
(`_dispatch_trade_event`) validates `mi_live_trades.account_mode ==
stream_account_mode` before any state mutation — prevents a paper-stream
event from racing into a live trade row (and vice versa). Cross-account
mismatches drop the event and emit `cross_account_event_rejected` audit.

The SDK's TradingStream auto-reconnects on WebSocket errors. This module adds
an outer monitoring wrapper that restarts the stream if it dies unexpectedly,
and falls back to polling if the stream fails repeatedly. Per-stream
backoff state means paper-stream reconnect doesn't reset the live-stream
counter and vice versa.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from alpaca.trading.stream import TradingStream

from agents.market_intelligence.audit_events import ENTRY_ORDER_REJECTED
from agents.market_intelligence.broker.stream_models import (
    ReasonPreservingTradingStream,
)
from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.skip_reasons import humanize
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.constants import mode_prefix
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

# ── Per-mode module state (#66) ──────────────────────────────────────────────

_stream_tasks: dict[str, asyncio.Task] = {}
_trading_streams: dict[str, TradingStream] = {}
_stream_healthy: dict[str, bool] = {}
_last_event_time: dict[str, datetime | None] = {}
_reconnect_count: dict[str, int] = {}
_MAX_OUTER_RETRIES = 3


def _resolve_modes() -> list[str]:
    """Return the list of account_modes to subscribe streams for.

    ENABLE_LIVE_MODE=true → ['paper', 'live'] (production default).
    ENABLE_LIVE_MODE=false → ['paper'] (dev / single-account).
    """
    from agents.market_intelligence.constants import active_account_modes
    return active_account_modes()


# ── Lifecycle ───────────────────────────────────────────────────────────────


async def start_trade_stream() -> None:
    """Start one WebSocket trade-update stream per account_mode."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        logger.info("Live trading disabled, trade stream not started")
        return

    for mode in _resolve_modes():
        await _start_one_stream(mode)


async def _start_one_stream(account_mode: str) -> None:
    """Spawn one TradingStream subscribed for a specific account_mode."""
    env_prefix = f"ALPACA_{account_mode.upper()}_"
    api_key = os.environ.get(f"{env_prefix}API_KEY")
    secret_key = os.environ.get(f"{env_prefix}SECRET_KEY")
    if not api_key or not secret_key:
        logger.warning(
            f"Alpaca {account_mode} credentials not set, "
            f"trade stream NOT started for mode={account_mode}"
        )
        return

    # #540: the reason-preserving subclass, NOT the bare SDK stream — the bare
    # one drops the broker's rejection reason at parse time (see stream_models.py).
    stream = ReasonPreservingTradingStream(
        api_key=api_key,
        secret_key=secret_key,
        paper=(account_mode == "paper"),
        raw_data=False,
    )

    # Closure binding: every event from this stream knows which mode it
    # came from. The dispatcher validates account_mode against the trade
    # row before any state mutation (cross-account contamination guard).
    async def _handler(data, _mode=account_mode):
        await _dispatch_trade_event(data, _mode)

    stream.subscribe_trade_updates(_handler)

    # Guard against SDK changes — _run_forever is the coroutine we need
    if not hasattr(stream, "_run_forever") or not asyncio.iscoroutinefunction(
        stream._run_forever
    ):
        logger.error(
            "alpaca-py SDK changed: TradingStream._run_forever not found. "
            "Pin alpaca-py==0.43.2. Falling back to polling for "
            f"mode={account_mode}."
        )
        return

    _trading_streams[account_mode] = stream
    _stream_healthy[account_mode] = False
    _last_event_time[account_mode] = None
    _reconnect_count[account_mode] = 0
    _stream_tasks[account_mode] = asyncio.create_task(
        _run_stream_with_monitoring(account_mode)
    )
    logger.info(f"Trade update stream started for mode={account_mode}")


async def _run_stream_with_monitoring(account_mode: str) -> None:
    """Outer wrapper: restarts _run_forever for a specific mode if it dies."""
    stream = _trading_streams.get(account_mode)
    if stream is None:
        return

    while True:
        try:
            _stream_healthy[account_mode] = True
            _reconnect_count[account_mode] = 0
            logger.info(f"Trade stream connecting (mode={account_mode})...")
            await stream._run_forever()
        except asyncio.CancelledError:
            logger.info(f"Trade stream cancelled for mode={account_mode} (shutdown)")
            _stream_healthy[account_mode] = False
            return
        except Exception as e:
            _stream_healthy[account_mode] = False
            _reconnect_count[account_mode] += 1
            n = _reconnect_count[account_mode]
            logger.error(
                f"Trade stream (mode={account_mode}) died unexpectedly: {e}, "
                f"reconnect attempt {n}/{_MAX_OUTER_RETRIES}"
            )
            if n >= _MAX_OUTER_RETRIES:
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🚨 *Trade stream "
                    f"failed {_MAX_OUTER_RETRIES} times* (mode={account_mode})\n"
                    f"Last error: {e}\n"
                    f"Falling back to polling. Check logs."
                )
                _stream_healthy[account_mode] = False
                return
            backoff = min(5 * n, 30)
            logger.info(f"Retrying trade stream (mode={account_mode}) in {backoff}s...")
            await asyncio.sleep(backoff)


async def stop_trade_stream() -> None:
    """Stop all per-mode WebSocket streams. Called from agent.py shutdown."""
    for mode, task in list(_stream_tasks.items()):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    for mode, stream in list(_trading_streams.items()):
        try:
            await stream.close()
        except Exception as e:
            logger.debug(f"trade stream close failed for mode={mode} during shutdown: {e}")

    _stream_healthy.clear()
    logger.info("All trade streams stopped")


def get_stream_status() -> dict:
    """Return per-mode stream health info for monitoring + fallback decisions.

    Shape: per-mode nested dict PLUS legacy top-level aggregate keys for
    callers that pre-date the dual-account refactor.

      {
        "paper": {"healthy": bool, "last_event": str|None,
                  "reconnect_count": int, "task_alive": bool},
        "live":  {... (only if dual-mode active)},
        # Legacy aggregate — true only if EVERY mode is healthy/alive.
        # Watchdog uses these to detect "all streams down → restart".
        "healthy": bool,
        "task_alive": bool,
        "modes": [list of mode names],
      }
    """
    out: dict = {"modes": []}
    all_healthy = True
    all_alive = True
    for mode in list(_stream_tasks.keys()):
        task = _stream_tasks.get(mode)
        mode_alive = task is not None and not task.done() if task else False
        mode_healthy = bool(_stream_healthy.get(mode, False))
        out[mode] = {
            "healthy": mode_healthy,
            "last_event": (
                _last_event_time[mode].isoformat()
                if _last_event_time.get(mode) else None
            ),
            "reconnect_count": _reconnect_count.get(mode, 0),
            "task_alive": mode_alive,
        }
        out["modes"].append(mode)
        all_healthy = all_healthy and mode_healthy
        all_alive = all_alive and mode_alive
    # Aggregate fallback: when no streams exist yet, report not-healthy /
    # not-alive so the watchdog kicks a restart attempt.
    if not out["modes"]:
        all_healthy = False
        all_alive = False
    out["healthy"] = all_healthy
    out["task_alive"] = all_alive
    return out


# ── Cross-account event validation (reviewer correctness invariant) ─────────


async def _verify_event_account_mode(order_id: str, stream_account_mode: str) -> bool:
    """Validate that an order event arrived on the correct account's stream.

    Looks up the trade row's account_mode by order_id (covers entry, stop,
    and tagged exit orders). Returns:
      - True if account_mode matches stream_account_mode → safe to process
      - True if no row found → likely untracked direct Alpaca action;
        downstream handler emits the untracked-fill alert
      - False if mismatch → drops the event, emits cross_account_event_rejected
        audit, prevents cross-account state mutation

    Required because a single Apollo container subscribes to BOTH paper and
    live trade streams. Without this guard, a paper-stream event for an
    untagged order_id could mutate a live trade row (or vice versa) if the
    order_id happened to match — extremely unlikely with mode-bound
    client_order_id (apollo_paper_… vs apollo_live_…) but still load-bearing
    defense in depth.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Try mi_live_trades first (entry / stop order matches)
        row_mode = await conn.fetchval(
            """
            SELECT account_mode FROM mi_live_trades
            WHERE entry_order_id = $1 OR stop_order_id = $1
            LIMIT 1
            """,
            order_id,
        )
        # Then mi_live_orders (tagged exits: partial_exit, full_exit, stop_loss)
        if row_mode is None:
            row_mode = await conn.fetchval(
                """
                SELECT lt.account_mode FROM mi_live_orders lo
                JOIN mi_live_trades lt ON lt.id = lo.trade_id
                WHERE lo.alpaca_order_id = $1
                LIMIT 1
                """,
                order_id,
            )

    if row_mode is None:
        # Untracked — let downstream handler emit the untracked-fill alert.
        return True

    if row_mode != stream_account_mode:
        logger.error(
            f"CROSS_ACCOUNT_EVENT_REJECTED: order_id={order_id} arrived on "
            f"stream={stream_account_mode} but trade row carries "
            f"account_mode={row_mode}"
        )
        try:
            await log_audit_event(
                event_type="cross_account_event_rejected",
                summary=(
                    f"Stream {stream_account_mode} got event for "
                    f"{row_mode} trade (order={order_id})"
                ),
                detail=json.dumps({
                    "order_id": order_id,
                    "stream_account_mode": stream_account_mode,
                    "trade_account_mode": row_mode,
                }),
            )
        except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py). This only wraps the cross_account_event_rejected audit write: logger.error(CROSS_ACCOUNT_EVENT_REJECTED...) fires unconditionally one line above, and the caller's return False (event dropped) does not depend on this write succeeding — the cross-account guard is enforced regardless.
            pass
        return False

    return True


def _find_replacement_stop(open_orders, symbol: str, canceled_order_id: str, remaining_shares):
    """#433 (2026-07-06): given the broker's open orders, return a live SELL stop
    for `symbol` (not the just-canceled order) that COVERS the position — i.e.
    proof it is still protected (a stop REPLACEMENT, not a naked position).
    Returns the stop order dict or None.

    Mirrors #128's `_covered_by_broker` exactly: filter to SELL orders first,
    require sell-side coverage ≥ remaining_shares, THEN find the stop among them.
    The sell-side filter is LOAD-BEARING (advisor/review 7/6): a stop-limit BUY
    (the entry order, or a Day-1 re-entry in flight) also carries a `stop_price`,
    so matching any-side "stop" would let a BUY stop falsely read as protection
    for a LONG and suppress a real naked alarm. A long is protected only by a
    SELL stop. INVARIANT: positive match only; None on any doubt (partial
    coverage, wrong side, unknown qty) → the caller alarms."""
    sell_orders = [
        o for o in (open_orders or [])
        if o.get("symbol") == symbol
        and o.get("id") != canceled_order_id
        and str(o.get("side", "")).lower().endswith("sell")
    ]
    if remaining_shares is None:
        return None
    covered = sum(
        max(float(o.get("qty") or 0) - float(o.get("filled_qty") or 0), 0.0)
        for o in sell_orders
    )
    if covered < float(remaining_shares):
        return None
    return next(
        (o for o in sell_orders
         if "stop" in str(o.get("type", "")).lower() or o.get("stop_price") is not None),
        None,
    )


# #475: settle window before the ONE bounded re-check on a stop-cancel with no
# replacement found — long enough for an in-flight stop RE-PLACE to land at the
# broker (observed ~seconds on MANE 2026-07-15), short enough that a genuinely
# naked position still alarms promptly.
_STOP_CANCEL_RECHECK_DELAY_S = 3


async def _broker_confirm_replacement_stop(
    symbol: str, canceled_order_id: str, remaining_shares, account_mode: str,
):
    """One bounded, fail-safe broker read: does a DIFFERENT live SELL stop cover
    `symbol`? Returns the replacement order dict, or None.

    FAIL-SAFE CONTRACT (#433 — do not weaken): only a POSITIVE broker
    confirmation returns an order. A read error, a timeout, or genuinely-no-stop
    all return None → the caller ALARMS. The 8s `asyncio.wait_for` bound exists
    because `get_open_orders` is a SYNC alpaca-py REST call under an async def —
    it blocks the WS event loop for the round-trip; a slow/hung broker must not
    wedge the trade stream at exactly the moment stop-cancels cluster.
    """
    from agents.market_intelligence.broker import alpaca_client as _alp
    try:
        open_orders = await asyncio.wait_for(
            _alp.get_open_orders(account_mode=account_mode, raise_on_error=True),
            timeout=8,
        )
        return _find_replacement_stop(
            open_orders, symbol, canceled_order_id, remaining_shares
        )
    except Exception as _e:
        logger.warning(
            f"WS [{account_mode}]: broker-confirm on stop-cancel failed for "
            f"{symbol} ({_e}) — treating as no replacement (fail-safe: caller alarms)"
        )
        return None


# ── Event Router ────────────────────────────────────────────────────────────


async def _dispatch_trade_event(data, stream_account_mode: str) -> None:
    """Central handler for all Alpaca trade update WebSocket events.

    Validates cross-account invariant before routing to the per-event
    handler. All downstream handlers receive the validated account_mode
    and use it to (a) filter mi_live_trades queries, (b) route alpaca
    calls to the correct client, (c) emit Telegram with the right prefix.
    """
    _last_event_time[stream_account_mode] = datetime.now(timezone.utc)

    event = str(data.event)
    order = data.order
    order_id = str(order.id)
    symbol = order.symbol

    logger.info(
        f"WS [{stream_account_mode}] event: {event} | {symbol} | "
        f"order={order_id} | status={order.status}"
    )

    # Cross-account guard — runs BEFORE any DB mutation. Lifecycle events
    # (new, accepted, held) bypass since they don't mutate state.
    if event in ("fill", "partial_fill", "canceled", "cancelled", "expired", "rejected"):
        if not await _verify_event_account_mode(order_id, stream_account_mode):
            return

    try:
        if event == "fill":
            await _handle_fill(data, stream_account_mode)
        elif event == "partial_fill":
            await _handle_partial_fill(data, stream_account_mode)
        elif event in ("canceled", "cancelled", "expired", "rejected"):
            await _handle_cancel_or_reject(data, event, stream_account_mode)
        elif event in ("new", "accepted", "held"):
            logger.debug(
                f"Order {event} [{stream_account_mode}]: "
                f"{symbol} order_id={order_id}"
            )
        else:
            logger.debug(f"Unhandled trade event: {event} for {symbol}")
    except Exception as e:
        logger.error(
            f"Error handling WS event {event} [{stream_account_mode}] "
            f"for {symbol}: {e}",
            exc_info=True,
        )
        # Escalate fill / partial_fill errors specifically — the consequence
        # is a naked or partially-managed position at broker. The auto-
        # remediation inside _process_entry_fill should have submitted a
        # fallback stop, but the outer alert is the operator's hard ping.
        if event in ("fill", "partial_fill"):
            await send_telegram_message(
                f"{mode_prefix(stream_account_mode)}🚨 *POSITION MAY BE NAKED — INTERVENTION REQUIRED*\n"
                f"{event} handler threw for {symbol}; stop-leg may have been canceled.\n"
                f"Check Alpaca dashboard NOW and confirm a protective stop is active.\n"
                f"Error: {e}"
            )
        else:
            await send_telegram_message(
                f"{mode_prefix(stream_account_mode)}⚠️ *Stream handler error*\n"
                f"{event} for {symbol}: {e}"
            )


# Backward-compat alias (some older imports may still call _handle_trade_update
# directly). New code should use _dispatch_trade_event with explicit mode.
async def _handle_trade_update(data, account_mode: str | None = None) -> None:
    from agents.market_intelligence.constants import current_account_mode
    await _dispatch_trade_event(data, account_mode or current_account_mode())


# ── Partial Fill Handler (visibility-only) ──────────────────────────────────
#
# Paper Alpaca atomic-fills, so this code path has zero production exercise on
# paper. Real-$ tick-fills routinely (bid-side liquidity, large size, news bars).
# When the first real partial lands, we want the operator paged so they can
# manually verify DB state vs broker state — the full deferred-commit handler
# will be designed against that production data.


async def _handle_partial_fill(data, account_mode: str) -> None:
    order = data.order
    order_id = str(order.id)
    symbol = order.symbol
    event_qty = float(data.qty) if getattr(data, "qty", None) else 0.0
    cum_filled = float(order.filled_qty) if order.filled_qty else 0.0
    total_qty = float(order.qty) if order.qty else 0.0
    avg_price = float(order.filled_avg_price) if order.filled_avg_price else 0.0
    side = str(getattr(order, "side", "")).split(".")[-1].lower()

    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT id, ticker FROM mi_live_trades "
            "WHERE (entry_order_id = $1 OR stop_order_id = $1) "
            "  AND account_mode = $2 "
            "ORDER BY id DESC LIMIT 1",
            order_id,
            account_mode,
        )
    trade_id = trade["id"] if trade else None
    ticker = trade["ticker"] if trade else symbol

    summary = (
        f"[{account_mode}] {symbol} partial_fill {event_qty:g}/{total_qty:g} "
        f"(cum {cum_filled:g}) @ ${avg_price:.2f} side={side}"
    )
    detail = json.dumps({
        "trade_id": trade_id,
        "order_id": order_id,
        "ticker": ticker,
        "side": side,
        "event_qty": event_qty,
        "cum_filled": cum_filled,
        "total_qty": total_qty,
        "avg_price": avg_price,
        "account_mode": account_mode,
    })
    await log_audit_event("entry_partial_fill", summary, detail)

    # Route sell-side partial fills on tagged exit legs to their finalizers,
    # but ONLY when cumulative qty has reached total qty (i.e., the order is
    # terminal — the broker just reported it through partial_fill events
    # instead of a final `fill` event). ARM 5/07 incident: stop sold 87/89
    # @$219.50 then odd-lot leftover never filled; cum_filled=total_qty=87
    # at terminal would have routed correctly.
    #
    # General-case multi-print partials (cum_filled < total_qty) STAY
    # visibility-only per Wave 3 P0.2 advisor scope: the finalizer's
    # idempotency check is keyed on order_id, so committing on the first
    # partial would no-op subsequent partials and drop their shares' P&L
    # silently. Wait for the terminal event before committing state.
    is_terminal_partial = (
        "sell" in side and trade_id and total_qty > 0 and cum_filled >= total_qty
    )
    if is_terminal_partial:
        async with pool.acquire() as conn:
            exit_order = await conn.fetchrow("""
                UPDATE mi_live_orders SET
                    status = 'partially_filled',
                    filled_qty = $2, filled_avg_price = $3
                WHERE alpaca_order_id = $1
                  AND purpose IS NOT NULL
                  AND status NOT IN ('filled', 'cancelled')
                RETURNING trade_id, purpose, exit_reason, qty
            """, order_id, cum_filled, avg_price)
        if exit_order:
            purpose = exit_order["purpose"]
            if purpose == "stop_loss":
                from agents.market_intelligence.broker.order_manager import finalize_stop_fill
                await finalize_stop_fill(
                    exit_order["trade_id"], int(cum_filled), avg_price, order_id,
                )
            elif purpose == "partial_exit":
                from agents.market_intelligence.broker.order_manager import finalize_partial_exit
                await finalize_partial_exit(
                    exit_order["trade_id"], int(cum_filled), avg_price, order_id,
                )
            elif purpose == "full_exit":
                from agents.market_intelligence.broker.order_manager import finalize_full_exit
                await finalize_full_exit(
                    exit_order["trade_id"], int(cum_filled), avg_price, order_id,
                    exit_order["exit_reason"] or "exit",
                )
            return  # finalizer already sent its own Telegram

    # Paper-mode noise reduction (2026-05-11): paper Alpaca synthesizes
    # partial fills on liquid mid-caps even though no real liquidity
    # constraint exists. One trade can produce 6+ partial-fill messages
    # (e.g. MNDY 5/11: 228 sh entry filled in 3 partials, then exited in
    # another 4 partials = 7 messages for one trade). The audit-log entry
    # above is preserved for telemetry; only the Telegram blast is
    # suppressed on paper.
    #
    # Live mode keeps the alert per the 2026-05-05 contract — first real
    # partials need operator eyes on DB state vs broker state. When a
    # large-size live trade starts tick-filling, this is load-bearing
    # visibility.
    if account_mode != "live":
        logger.info(
            f"Partial fill suppressed (paper): {symbol} {event_qty:g}/{total_qty:g} "
            f"@${avg_price:.2f} order={order_id}"
        )
        return

    await send_telegram_message(
        f"{mode_prefix(account_mode)}📊 *Partial fill: {symbol}*\n"
        f"This event: {event_qty:g} sh | Cumulative: {cum_filled:g}/{total_qty:g}\n"
        f"Avg price: ${avg_price:.2f} | side: {side}\n"
        f"order={order_id}\n"
        f"_Visibility-only — handler defers commit to terminal fill event._"
    )


# ── Fill Handler ────────────────────────────────────────────────────────────


async def _handle_fill(data, account_mode: str) -> None:
    """Route fill events to entry fill or stop-loss fill handlers."""
    order = data.order
    order_id = str(order.id)
    symbol = order.symbol
    filled_price = float(order.filled_avg_price) if order.filled_avg_price else (data.price or 0)
    filled_qty = float(order.filled_qty) if order.filled_qty else (data.qty or 0)

    pool = await get_pool()

    # 1. Check if this is an entry order fill (atomic claim, mode-scoped)
    async with pool.acquire() as conn:
        entry_trade = await conn.fetchrow("""
            UPDATE mi_live_trades SET status = 'filling'
            WHERE entry_order_id = $1 AND status = 'order_placed'
              AND account_mode = $2
            RETURNING *
        """, order_id, account_mode)

    if entry_trade:
        await _process_entry_fill(
            dict(entry_trade), order, filled_price, filled_qty, pool, account_mode
        )
        return

    # 2. Check if this is a stop-loss leg fill (atomic claim, mode-scoped)
    async with pool.acquire() as conn:
        stop_trade = await conn.fetchrow("""
            UPDATE mi_live_trades SET status = 'stop_processing'
            WHERE stop_order_id = $1 AND status = 'filled'
              AND account_mode = $2
            RETURNING *
        """, order_id, account_mode)

    if stop_trade:
        await _process_stop_fill(dict(stop_trade), filled_price, pool, account_mode)
        return

    # 3. Managed exit fill (partial_exit / full_exit). Atomically claim the
    # mi_live_orders row by status transition; the RETURNING row's purpose
    # routes to the right finalizer. Submit-time path no longer commits to
    # mi_live_trades (after-hours queued sells were printing fake P&L=$0
    # against entry_price); fill-time finalize uses the real Alpaca fill price.
    async with pool.acquire() as conn:
        exit_order = await conn.fetchrow("""
            UPDATE mi_live_orders SET
                status = 'filled', filled_qty = $2, filled_avg_price = $3, filled_at = NOW()
            WHERE alpaca_order_id = $1 AND status NOT IN ('filled', 'cancelled')
            RETURNING trade_id, purpose, exit_reason, qty
        """, order_id, filled_qty, filled_price)

    if exit_order:
        purpose = exit_order["purpose"]
        if purpose == "partial_exit":
            from agents.market_intelligence.broker.order_manager import finalize_partial_exit
            await finalize_partial_exit(
                exit_order["trade_id"], int(filled_qty), filled_price, order_id,
            )
        elif purpose == "full_exit":
            from agents.market_intelligence.broker.order_manager import finalize_full_exit
            await finalize_full_exit(
                exit_order["trade_id"], int(filled_qty), filled_price, order_id,
                exit_order["exit_reason"] or "exit",
            )
        elif purpose == "stop_loss":
            # Stop-loss leg fill — primary routing path now (replaces step 2's
            # stop_order_id-match which can go stale, ref. TEAM 5/06 BE-stop +
            # ARM 5/07 entry-stop classes). Step 2 still runs first for
            # backwards compat with un-tagged historical stops.
            from agents.market_intelligence.broker.order_manager import finalize_stop_fill
            await finalize_stop_fill(
                exit_order["trade_id"], int(filled_qty), filled_price, order_id,
            )
        else:
            # NULL purpose = legacy mi_live_orders row submitted before this fix
            # shipped (entry/stop rows have NULL too). Already updated to
            # status='filled' above; nothing else to do here.
            logger.info(
                f"Managed fill [{account_mode}] (purpose={purpose}): "
                f"{symbol} order={order_id} {filled_qty}@${filled_price}"
            )
        return

    # 4. Truly untracked — surprise fill from a direct/manual Alpaca action.
    if filled_qty > 0:
        side = str(getattr(order, "side", "")).lower()
        side_label = "SELL" if "sell" in side else ("BUY" if "buy" in side else "FILL")
        await send_telegram_message(
            f"{mode_prefix(account_mode)}💱 *Untracked {side_label}:* "
            f"{symbol} @${filled_price:.2f} x {filled_qty:.0f}\n"
            f"Order {order_id[:8]} not in our records — direct Alpaca action."
        )
        logger.warning(
            f"Untracked fill [{account_mode}]: {symbol} order={order_id} "
            f"filled={filled_qty}@${filled_price}"
        )


async def _process_entry_fill(
    trade: dict,
    order,
    filled_price: float,
    filled_qty: float,
    pool,
    account_mode: str,
) -> None:
    """Handle entry order fill — update trade to 'filled' status."""
    ticker = trade["ticker"]

    # Partial fill too small (< $500)
    if filled_qty < (trade["entry_shares"] or 0) and filled_price and filled_qty * filled_price < 500:
        logger.info(f"Partial fill too small for {ticker}: {filled_qty} shares, closing")
        try:
            await alpaca.close_position(ticker, account_mode=account_mode)
        except Exception as e:
            logger.error(f"Failed to close partial fill for {ticker}: {e}")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE mi_live_trades SET status = 'closed', skip_reason = 'Partial fill too small' WHERE id = $1",
                trade["id"],
            )
        return

    # Extract stop-loss leg ID. Multiple sources in priority order so one
    # failure mode can't silently produce an untracked stop:
    #   1. The WS fill-event payload (often populated, sometimes empty for OTO parents).
    #   2. The DB value submit_entry already wrote at order-placement time.
    #   3. A REST refetch of the parent order — legs are always populated there.
    # Without #2/#3 we previously attempted a standalone remediation stop that
    # Alpaca rejected with `heldForOrders` — false-alarming UNPROTECTED while
    # the OTO child was actually live (see 2026-04-24 INTC incident).
    stop_order_id = alpaca.extract_stop_leg_id(order)

    if not stop_order_id:
        async with pool.acquire() as conn:
            stop_order_id = await conn.fetchval(
                "SELECT stop_order_id FROM mi_live_trades WHERE id = $1", trade["id"]
            )

    if not stop_order_id:
        try:
            refetched = await alpaca.get_order(str(order.id), account_mode=account_mode)
            stop_order_id = alpaca.extract_stop_leg_id(refetched)
        except Exception as e:
            logger.warning(f"Could not refetch order {order.id} for leg extraction: {e}")

    # Fill-path stop remediation — fire immediately instead of waiting for 4:05 PM sync
    # if no stop leg came back (bracket order_class validation in alpaca_client should
    # prevent this, but defensive).
    if not stop_order_id:
        stop_target = float(trade["orb_low"]) if trade.get("orb_low") else None
        ticker_name = trade["ticker"]
        if stop_target:
            try:
                new_stop = await alpaca.place_stop_order(
                    ticker_name, filled_qty, stop_target, account_mode=account_mode,
                )
                stop_order_id = new_stop["id"]
                # Tag remediation stop with purpose='stop_loss' so WS fill handler
                # routes via mi_live_orders even if stop_order_id goes stale later.
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO mi_live_orders
                            (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                             stop_price, status, raw_response, purpose, exit_reason)
                        VALUES ($1, $2, $3, 'sell', 'stop', $4, $5,
                                $6, $7::jsonb, 'stop_loss', 'stop_hit')
                        ON CONFLICT (alpaca_order_id) DO NOTHING
                    """, trade["id"], stop_order_id, ticker_name,
                        float(filled_qty), stop_target,
                        new_stop.get("status", "new"), json.dumps(new_stop))
                logger.warning(
                    f"Fill-path stop remediation [{account_mode}]: {ticker_name} "
                    f"qty={filled_qty} stop=${stop_target:.2f} order_id={stop_order_id}"
                )
                # Explicit audit event for the
                # trade_stream_stop_placement_without_orders_row review's
                # specific predicate (was using naked_position_detected proxy).
                await log_audit_event(
                    "entry_fill_stop_remediated",
                    f"{ticker_name}: bracket leg missing, standalone stop placed at ${stop_target:.2f}",
                    json.dumps({
                        "trade_id": trade["id"],
                        "ticker": ticker_name,
                        "account_mode": account_mode,
                        "stop_price": stop_target,
                        "stop_order_id": stop_order_id,
                        "site": "trade_stream.py:367_entry_fill_remediation",
                    }),
                )
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🛡 *Protective stop placed:* {ticker_name}\n"
                    f"Bracket leg missing — standalone stop at ${stop_target:.2f}"
                )
            except Exception as e:
                logger.error(f"Fill-path stop remediation FAILED for {ticker_name}: {e}")
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🚨 *UNPROTECTED POSITION:* {ticker_name}\n"
                    f"Entry filled but stop placement failed: {e}\n"
                    f"Manual intervention required."
                )
        else:
            logger.error(f"Fill-path stop remediation impossible for {ticker_name}: no orb_low")
            await send_telegram_message(
                f"{mode_prefix(account_mode)}🚨 *UNPROTECTED POSITION:* {ticker_name}\n"
                f"Entry filled, no stop order, no orb_low in DB. Manual intervention required."
            )

    # CRMD-class naked-position remediation (Gate 5 deliverable A, 2026-05-14):
    # if the UPDATE raises (asyncpg AmbiguousParameter, transient DB error,
    # serialization fail, anything), the OTO bracket's stop leg gets
    # canceled by Alpaca and the position is naked. Submit a fallback
    # stop-market BEFORE re-raising so the position is protected even if
    # the DB-level reconciliation is broken.
    try:
        async with pool.acquire() as conn:
            # T1.1 refactor (2026-05-17): removed stop_price + hard_stop from
            # this UPDATE per docs/architecture/trade-state-ownership.md.
            #
            # ORIGIN: 2026-05-15 KLAR incident — 9M Day 2 trade #149 had
            # broker stop=$14.96 (prior_day_low) but DB stop_price=$15.74
            # (orb_low) because this UPDATE clobbered it. Today's fix
            # writes `trade["stop_price"]` instead of `trade["orb_low"]`
            # (correct for both strategies), but the SECOND-WRITE pattern
            # remained — entry-fill is not the authorized writer for
            # stop_price/hard_stop. INSERT at entry_pipeline._skip is the
            # initial setter; update_stop() is the authorized trail updater.
            # check_fills polling writes the existing value (no-op safe).
            #
            # Removing from here cuts stop_price writers 7→5 and eliminates
            # the second-write race entirely.
            #
            # NUMERIC type bookkeeping: lowest_price_seen / highest_price_seen
            # are NUMERIC; entry_price is DOUBLE PRECISION. asyncpg's type
            # deduction requires a SEPARATE placeholder for the numeric
            # columns even though the value is the same — using $2 for both
            # produces AmbiguousParameter (CRMD class). $4 carries
            # filled_price typed for the numeric columns; $2 carries it
            # typed for entry_price.
            # AND status='filling': never resurrect a row something else terminalized
            # between our atomic claim and this write (money-path audit 2026-07-12 R1
            # sibling of SM6). A no-op here strands 'filling' LOUDLY — the stuck-fill
            # watchdog alerts on it — which beats silently overwriting a terminal state.
            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'filled',
                    entry_price = $2, entry_shares = $3, remaining_shares = $3,
                    filled_at = NOW(),
                    stop_order_id = COALESCE($4, stop_order_id),
                    lowest_price_seen = COALESCE(lowest_price_seen, $5),
                    highest_price_seen = COALESCE(highest_price_seen, $5)
                WHERE id = $1 AND status = 'filling'
            """, trade["id"], filled_price, filled_qty,
                 stop_order_id, filled_price)
    except Exception as db_err:
        # Submit fallback stop IMMEDIATELY at intended orb_low — do not
        # depend on later sync_positions, do not re-raise yet. Cover the
        # naked position first; surface the underlying error after.
        ticker = trade["ticker"]
        stop_target = float(trade["orb_low"]) if trade.get("orb_low") else None
        if stop_target:
            try:
                fallback = await alpaca.place_stop_order(
                    ticker, filled_qty, stop_target, account_mode=account_mode,
                )
                await log_audit_event(
                    "naked_position_remediation_fired",
                    f"{ticker}: entry-fill UPDATE failed ({type(db_err).__name__}); "
                    f"fallback stop placed at ${stop_target:.2f} order={fallback['id']}",
                    detail=json.dumps({
                        "trade_id": trade["id"],
                        "ticker": ticker,
                        "account_mode": account_mode,
                        "db_error": f"{type(db_err).__name__}: {str(db_err)[:200]}",
                        "filled_qty": float(filled_qty),
                        "fallback_stop_price": stop_target,
                        "fallback_order_id": fallback["id"],
                    }),
                )
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🛡 *NAKED POSITION REMEDIATED:* {ticker}\n"
                    f"Entry-fill UPDATE failed ({type(db_err).__name__}); "
                    f"fallback stop placed at ${stop_target:.2f}.\n"
                    f"DB row remains in inconsistent state — operator should reconcile."
                )
            except Exception as stop_err:
                await log_audit_event(
                    "naked_position_remediation_failed",
                    f"{ticker}: BOTH UPDATE and fallback stop failed",
                    detail=json.dumps({
                        "trade_id": trade["id"],
                        "ticker": ticker,
                        "db_error": f"{type(db_err).__name__}: {str(db_err)[:200]}",
                        "stop_error": f"{type(stop_err).__name__}: {str(stop_err)[:200]}",
                    }),
                )
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🚨🚨 *CRITICAL: POSITION NAKED AND UNRECOVERABLE* {ticker}\n"
                    f"UPDATE failed: {db_err}\n"
                    f"Fallback stop also failed: {stop_err}\n"
                    f"MANUAL INTERVENTION REQUIRED on Alpaca dashboard NOW."
                )
        else:
            await log_audit_event(
                "naked_position_remediation_failed",
                f"{ticker}: UPDATE failed and no orb_low for fallback stop",
                detail=json.dumps({
                    "trade_id": trade["id"],
                    "ticker": ticker,
                    "db_error": f"{type(db_err).__name__}: {str(db_err)[:200]}",
                }),
            )
            await send_telegram_message(
                f"{mode_prefix(account_mode)}🚨🚨 *CRITICAL: NAKED + NO STOP ANCHOR* {ticker}\n"
                f"UPDATE failed: {db_err}\nNo orb_low. MANUAL INTERVENTION REQUIRED."
            )
        # Re-raise so the outer handler logs / Telegram-escalates the original
        # error class. Remediation is best-effort; the failure is still loud.
        raise

        await conn.execute("""
            UPDATE mi_live_orders SET
                status = 'filled', filled_qty = $2, filled_avg_price = $3, filled_at = NOW()
            WHERE alpaca_order_id = $1
        """, str(order.id), filled_qty, filled_price)

    attempt = trade.get("entry_attempt", 1)
    # #475: this FILLED alert is now the SOLE per-trade Telegram (the placement
    # message was dropped), so it must be self-contained: entry, shares, stop.
    # Show the ACTUAL stop (mi_live_trades.stop_price = the spec's stop) — for
    # 9M Day 2 the stop is the PRIOR day's low, not orb_low; the two only
    # coincide for MAGNA53. orb_low kept as fallback for legacy NULL rows.
    _stop_val = trade.get("stop_price") or trade.get("orb_low")
    _stop_line = f"\nStop: ${float(_stop_val):.2f}" if _stop_val else ""
    msg = (
        f"{mode_prefix(account_mode)}✅ *FILLED:* {ticker} (attempt {attempt})\n"
        f"Entry: ${filled_price:.2f} x {filled_qty:.0f} shares"
        f"{_stop_line}"
    )
    try:
        await log_audit_event(
            "trade_lifecycle_telegram_attempted",
            f"fill {ticker} @${filled_price:.2f} x{filled_qty:.0f}",
            f"trade_id={trade['id']} account={account_mode} attempt={attempt} "
            f"message_len={len(msg)}",
        )
    except Exception as e:
        logger.debug(f"trade-lifecycle audit failed (non-critical): {e}")
    await send_telegram_message(msg)
    logger.info(f"WS fill [{account_mode}]: {ticker} @${filled_price:.2f} x{filled_qty:.0f}")


async def _process_stop_fill(
    trade: dict, stop_fill_price: float, pool, account_mode: str,
) -> None:
    """Handle stop-loss fill — close trade or attempt Day 1 re-entry."""
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.broker.order_manager import attempt_day1_reentry, MAX_ENTRY_ATTEMPTS

    ticker = trade["ticker"]
    today = et_today()
    is_day1 = trade["alert_date"] == today
    attempt = trade.get("entry_attempt", 1)

    if is_day1 and attempt < MAX_ENTRY_ATTEMPTS:
        # Restore status to 'filled' so attempt_day1_reentry can process it
        # (we set it to 'stop_processing' for the atomic claim)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE mi_live_trades SET status = 'filled' WHERE id = $1",
                trade["id"],
            )
        result = await attempt_day1_reentry(trade["id"], stop_fill_price, source="websocket")
        logger.info(f"WS re-entry result [{account_mode}] for {ticker}: {result}")
    else:
        # Close trade — Day 2+ or max attempts reached.
        # Money-path audit 2026-07-12 R1: the whole read-modify-write runs under the
        # per-trade #151 advisory lock with a FRESH row read (the claim-time snapshot
        # could be stale vs a concurrent job-side writer holding the same lock), and
        # the close is guarded on the claim status so it can never clobber a state
        # some other path terminalized — a no-op strands 'stop_processing' LOUDLY
        # (the transitional-state watchdog alerts) instead of corrupting silently.
        from agents.market_intelligence.broker.order_manager import _trade_advisory_lock

        entry_price = trade["entry_price"]
        async with _trade_advisory_lock(trade["id"]):
            async with pool.acquire() as conn:
                fresh = await conn.fetchrow(
                    "SELECT remaining_shares, exits, status FROM mi_live_trades WHERE id = $1",
                    trade["id"],
                )
            # explicit None-check (NOT `or`): a fresh remaining_shares of 0 is a real
            # value and must not fall back to the stale claim-time snapshot.
            shares = fresh["remaining_shares"] if fresh is not None else trade["remaining_shares"]
            pnl = (stop_fill_price - entry_price) * shares if entry_price else 0

            _raw_exits = fresh["exits"] if fresh else trade["exits"]
            exits = _raw_exits if isinstance(_raw_exits, list) else json.loads(_raw_exits or "[]")
            exits.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "price": stop_fill_price,
                "reason": "stop_hit",
                "shares": shares,
                "pnl": pnl,
                "attempt": attempt,
                "source": "websocket",
            })
            total_pnl = sum(e.get("pnl", 0) for e in exits)

            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_trades SET
                        status = 'closed', exits = $2::jsonb,
                        remaining_shares = 0, total_pnl = $3,
                        stop_order_id = NULL, closed_at = NOW()
                    WHERE id = $1 AND status = 'stop_processing'
                """, trade["id"], exits, total_pnl)

        reason = "max attempts" if is_day1 else f"stop hit ({trade.get('hold_days', 0)}d)"
        msg = (
            f"{mode_prefix(account_mode)}❌ *Stopped out:* {ticker} @${stop_fill_price:.2f}\n"
            f"P&L: ${pnl:+,.2f} | {reason}"
        )
        # Audit row BEFORE the send, with the message text — gives operator a
        # ground-truth record that the stop-out handler reached the Telegram
        # step. The actual Telegram delivery is a separate question (mi_audit_log
        # 'telegram_send_failed' / 'telegram_markdown_fallback' track failures;
        # silent success was previously invisible). Caught 2026-05-26 ROIV:
        # WS stop fired, DB closed, but operator couldn't tell if Telegram
        # delivered — there was no audit trail on success path.
        try:
            await log_audit_event(
                "trade_lifecycle_telegram_attempted",
                f"stop_out {ticker} @${stop_fill_price:.2f} pnl=${pnl:+,.2f}",
                f"trade_id={trade['id']} account={account_mode} reason={reason} "
                f"message_len={len(msg)}",
            )
        except Exception as e:
            logger.debug(f"trade-lifecycle audit failed (non-critical): {e}")
        await send_telegram_message(msg)
        logger.info(
            f"WS stop-out [{account_mode}]: {ticker} @${stop_fill_price:.2f} "
            f"pnl=${pnl:+,.2f}"
        )


# ── Cancel/Reject Handler ──────────────────────────────────────────────────


def _terminal_order_snapshot(order) -> dict:
    """#500: the broker-side evidence for a killed order — Alpaca's lifecycle
    timestamps + final order fields. Alpaca provides no textual reason, so
    these timestamps (canceled_at / failed_at / expired_at) plus the
    synthesized price diagnosis are the whole record. Defensive getattr
    everywhere — WS payload shapes vary; this must never raise."""
    def _iso(x):
        return x.isoformat() if x is not None and hasattr(x, "isoformat") else None

    def _s(x):
        return None if x is None else str(x)

    return {
        "status": _s(getattr(order, "status", None)),
        "canceled_at": _iso(getattr(order, "canceled_at", None)),
        "failed_at": _iso(getattr(order, "failed_at", None)),
        "expired_at": _iso(getattr(order, "expired_at", None)),
        "updated_at": _iso(getattr(order, "updated_at", None)),
        "filled_qty": _s(getattr(order, "filled_qty", None)),
        "order_type": _s(getattr(order, "type", None) or getattr(order, "order_type", None)),
        "limit_price": _s(getattr(order, "limit_price", None)),
        "stop_price": _s(getattr(order, "stop_price", None)),
    }


async def _handle_cancel_or_reject(data, event: str, account_mode: str) -> None:
    """Handle order cancellation, expiry, or rejection."""
    order = data.order
    order_id = str(order.id)
    symbol = order.symbol
    event_norm = "cancelled" if event in ("canceled", "cancelled") else event

    pool = await get_pool()

    # 1. Entry order? (mode-scoped). Context columns ride along for the #475
    # entry_order_rejected telemetry below.
    async with pool.acquire() as conn:
        entry_trade = await conn.fetchrow("""
            SELECT id, ticker, gap_pct, ep_score, entry_price, stop_price,
                   regime, signal_type
            FROM mi_live_trades
            WHERE entry_order_id = $1 AND account_mode = $2
              AND status IN ('order_placed', 'submitting', 'pending_confirmation', 'confirmed')
        """, order_id, account_mode)

    if entry_trade:
        # #500 reason capture (2026-07-23): Alpaca sends NO textual reason on a
        # cancel/reject, so never write the bare event word (the ARWR 7/22
        # "entry cancelled, no reason"). Synthesize last-vs-trigger diagnosis
        # (broker:* skip_reason) + persist the terminal order snapshot.
        from agents.market_intelligence.broker.order_manager import broker_terminal_reason
        skip_reason = await broker_terminal_reason(
            event_norm, symbol, entry_trade["entry_price"],
        )
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE mi_live_trades SET status = 'cancelled', skip_reason = $2 WHERE id = $1",
                entry_trade["id"], skip_reason,
            )
            try:
                await conn.execute("""
                    UPDATE mi_live_orders SET
                        status = $2,
                        cancelled_at = COALESCE(cancelled_at, NOW()),
                        raw_response = COALESCE(raw_response, '{}'::jsonb)
                            || jsonb_build_object('terminal', $3::jsonb)
                    WHERE alpaca_order_id = $1
                """, order_id, event_norm, json.dumps(_terminal_order_snapshot(order)))
            except Exception as snap_err:
                # Observability only — never block the status update / Telegram.
                logger.warning(
                    f"terminal-snapshot persist failed for {symbol} {order_id[:8]}: {snap_err}"
                )
        # #475 telemetry (observability only — the status update above is
        # unchanged): entry orders dying at the BROKER. e.g. AEHR 2026-07-15,
        # an exchange-level LULD rejection on a +29.5% gapper. Routine 10:00 ET
        # cleanup cancels mark their rows 'cancelled' BEFORE the WS event lands,
        # so they don't reach this branch — what arrives here is the unexpected
        # class. Rows accumulate in mi_audit_log and feed the
        # `entry_order_rejections_systematic` data-gated review: observe whether
        # the pattern is systematic before designing any retry mechanism.
        broker_reason = None
        broker_reason_source = None
        # ⚠ PRIMARY SOURCE (#540, 2026-08-10): the WS event ITSELF carries Alpaca's
        # reason — the stream parses with TradeUpdateWithBrokerFields, so it is on
        # `data` right now, race-free. The REST events-history lookup below is only
        # the FALLBACK: it races Alpaca's indexing (QNST 8/07 — NULL 76ms after the
        # cancel while the reason sat on the stream).
        if event_norm in ("rejected", "cancelled", "canceled", "expired"):
            _evt_reason = getattr(data, "reason", None)
            if _evt_reason:
                broker_reason = str(_evt_reason)[:300]
                broker_reason_source = "event"
            _evt_at = datetime.now(timezone.utc)
            if not broker_reason:
                broker_reason = await alpaca.fetch_broker_reject_reason(
                    order_id, _evt_at, account_mode=account_mode)
                if broker_reason:
                    broker_reason_source = "lookup"
            if not broker_reason:
                # ⚠ 2026-08-07: the inline lookup runs ~76ms after the event and Alpaca's
                # events history has NOT indexed it yet — measured on QNST, where the reason
                # ("Unsolicited: Bad Stop 19.8") was retrievable by hand minutes later but
                # came back NULL here. Re-ask in the BACKGROUND so the reason still lands,
                # without sleeping in this handler (every other order event queues behind it).
                # Late is fine for a post-mortem on an order that is already dead; blocking
                # the money path is not.
                async def _late_reason(_oid=order_id, _at=_evt_at, _mode=account_mode,
                                       _tid=entry_trade["id"], _tkr=entry_trade["ticker"]):
                    try:
                        late = await alpaca.fetch_broker_reject_reason_later(
                            _oid, _at, account_mode=_mode)
                        if not late:
                            return
                        await log_audit_event(
                            "entry_order_reject_reason_late",
                            f"{_tkr} [{_mode}] order {_oid[:8]} — broker reason (late): {late}",
                            json.dumps({"trade_id": _tid, "ticker": _tkr, "order_id": _oid,
                                        "account_mode": _mode, "broker_reason": late}),
                        )
                    except Exception as _e:   # loud-ok: a diagnostic must never surface here
                        logger.warning(f"late reject-reason lookup failed for {_oid}: {_e}")
                asyncio.create_task(_late_reason())
        try:
            await log_audit_event(
                ENTRY_ORDER_REJECTED,
                f"{event_norm}: {entry_trade['ticker']} [{account_mode}] "
                f"order {order_id[:8]}",
                json.dumps({
                    "trade_id": entry_trade["id"],
                    "ticker": entry_trade["ticker"],
                    "account_mode": account_mode,
                    "event_norm": event_norm,
                    "order_id": order_id,
                    "skip_reason": skip_reason,  # #500 — carries the diagnosis
                    # ⚠ ALPACA'S OWN WORDS (2026-08-06, INSM). Everything above this line
                    # is a diagnosis we SYNTHESISE; this is the broker stating the cause.
                    # It lives on the trade-updates EVENT, not the order — the order object
                    # has no reason field, and the SDK's TradeUpdate model has none either,
                    # so raw_data=False parses it away before this handler runs. Recovered
                    # by a targeted lookup instead of flipping the stream to raw dicts,
                    # which would rewrite every handler on the FILL path to recover a field
                    # needed only on a terminal failure. INSM would have read:
                    #   "[6098] Stop Price Already Triggered/Exceeds $ Threshold"
                    # instead of hours of inference.
                    # Since 2026-08-10 the PRIMARY source is the WS event itself
                    # (source="event", race-free); the REST lookup is the fallback
                    # (source="lookup") — the source key is the live proof of which
                    # path fired.
                    "broker_reason": broker_reason,
                    "broker_reason_source": broker_reason_source,
                    "gap_pct": float(entry_trade["gap_pct"]) if entry_trade["gap_pct"] is not None else None,
                    "ep_score": float(entry_trade["ep_score"]) if entry_trade["ep_score"] is not None else None,
                    "entry_price": float(entry_trade["entry_price"]) if entry_trade["entry_price"] is not None else None,
                    "stop_price": float(entry_trade["stop_price"]) if entry_trade["stop_price"] is not None else None,
                    "regime": entry_trade["regime"],
                    "signal_type": entry_trade["signal_type"],
                }),
            )
        except Exception as _e:
            # log_audit_event never raises; this guards the json.dumps/context
            # assembly so a telemetry bug can't block the REJECTED Telegram below.
            logger.warning(
                f"entry_order_rejected telemetry emit failed for {symbol}: {_e}"
            )
        icon = "🚫" if event_norm == "rejected" else "🗑"
        # The broker's own reason goes to the OPERATOR, not just the audit row. INSM sat
        # unexplained for hours with the answer already in Alpaca's payload.
        reason_line = f"\n_Broker: {broker_reason}_" if broker_reason else ""
        await send_telegram_message(
            f"{mode_prefix(account_mode)}{icon} *Entry {event_norm.upper()}:* {symbol}\n"
            f"Order {order_id[:8]} — no position opened.\n"
            f"{humanize(skip_reason)}{reason_line}"
        )
        logger.info(
            f"WS [{account_mode}]: entry order {event_norm}: {symbol} ({skip_reason})"
        )
        return

    # 2. Stop-loss leg cancellation — signals open position is now unprotected
    async with pool.acquire() as conn:
        stop_trade = await conn.fetchrow("""
            SELECT id, ticker, remaining_shares, stop_price, entry_price, hard_stop
            FROM mi_live_trades
            WHERE stop_order_id = $1 AND status = 'filled' AND account_mode = $2
        """, order_id, account_mode)

    if stop_trade:
        from agents.market_intelligence.broker.order_manager import (
            describe_stop_move,
            set_stop_order_id,
        )
        await set_stop_order_id(
            stop_trade["id"], None,
            reason="cancel_or_reject_null",
            account_mode=account_mode,
        )
        if event_norm == "expired":
            # #507 (2026-07-28): the old text promised "GTC re-issue at 4:05 PM ET"
            # — a time that had ALWAYS ALREADY PASSED, because this handler only
            # runs once the stop has expired (~16:15) while eod_cleanup runs at
            # 16:05. It was structurally incapable of being true, and a false
            # all-clear is worse than silence: it is exactly what stops an
            # operator acting on a correct alarm.
            #
            # What ACTUALLY happens, traced: eod_cleanup (16:05) cancels unfilled
            # orders + syncs positions — it never re-issues stops. NOTHING
            # re-issues after hours. The stop-ack watchdog (cron hour="9-15") is
            # the only re-placer, so it restores the stop at 09:00 ET — half an
            # hour BEFORE the open. The bare window is 16:15 → 09:00, entirely
            # outside market hours, and a stop would not execute then anyway.
            # So the position is protected again before it can be hit.
            await send_telegram_message(
                f"{mode_prefix(account_mode)}ℹ️ *EOD stop expired (expected):* {symbol}\n"
                f"{stop_trade['remaining_shares']:.0f} sh — bare overnight; "
                f"the 4:20 PM refresh puts a GTC stop back on tonight, so it is "
                f"protected from the open. No action needed."
            )
            logger.info(
                f"WS [{account_mode}]: EOD stop expired (expected): {symbol} "
                f"trade_id={stop_trade['id']}"
            )
        else:
            # #433 (2026-07-06, WULF): a stop-leg cancel is NOT proof of a naked
            # position — a stop REPLACEMENT (old leg canceled, new stop placed)
            # produces this exact event. Before crying "unprotected", ask the
            # broker whether a DIFFERENT live stop for this symbol exists.
            # INVARIANT: only downgrade the alarm when the broker POSITIVELY
            # confirms a live stop; a read failure or no-stop-found still alarms
            # (fail-safe — never suppress a genuinely-naked alert).
            replacement = await _broker_confirm_replacement_stop(
                symbol, order_id, stop_trade["remaining_shares"], account_mode
            )
            rechecked = False
            if not replacement:
                # #475 (2026-07-15, MANE): a stop RE-PLACE can still be IN FLIGHT
                # when the cancel WS event arrives — the first broker look finds
                # nothing yet, the new stop lands seconds later, and the premature
                # "unprotected" alarm was FALSE. Do ONE bounded re-check after a
                # short settle window. The #433 fail-safe is UNCHANGED: if the
                # re-check also errors / times out / finds no stop, we still
                # alarm — a real naked stop is never suppressed.
                rechecked = True
                await asyncio.sleep(_STOP_CANCEL_RECHECK_DELAY_S)
                replacement = await _broker_confirm_replacement_stop(
                    symbol, order_id, stop_trade["remaining_shares"], account_mode
                )
            if replacement:
                _settle_note = " (settled on re-check)" if rechecked else ""
                # #560 (2026-08-12): this handler is a SAFETY-NET check, decoupled
                # from whatever code path actually moved the stop — it exists
                # because a stop-leg cancel is ambiguous (naked vs. replaced) until
                # the broker positively confirms a replacement. It carries no
                # exit-ladder context (no stop_source), so describe_stop_move
                # INFERS the reason from prices alone — safe on live trades since
                # only the trail and breakeven ever raise a stop (see its
                # docstring).
                _new_stop = replacement.get("stop_price")
                _entry = stop_trade.get("entry_price")
                _hard = stop_trade.get("hard_stop")
                _old_stop = stop_trade.get("stop_price")

                # Operator (2026-08-12): "can we combine these two msg? I get two
                # Everytime stop moves." — this WS safety-net and order_manager's
                # own retry-recovered "Stop confirmed" fire independently for the
                # SAME move (retry path: order_manager cancels the old leg, that
                # cancel is what wakes THIS handler, and by the time order_manager's
                # retry lands + it tells the operator, this recheck usually lands
                # too). Do NOT merge the text — SUPPRESS this one when it is pure
                # confirmation of a fact the operator already has.
                #
                # AGREEMENT TEST is TWO-PART, and both parts are load-bearing:
                #   1. DB match — mi_live_trades' CURRENT stop_order_id/stop_price
                #      (re-read fresh, NOT `stop_trade` captured before the recheck)
                #      is this exact broker order.
                #   2. DUPLICATE EVIDENCE — a `stop_update_retry_succeeded` audit
                #      row exists for this exact trade_id + this exact new_stop_id.
                #      That event type is written ONLY on order_manager's
                #      retry-recovered branch, immediately before it sends "Stop
                #      confirmed" — so its presence is direct proof a Telegram for
                #      THIS order already went out (or is about to, same code path,
                #      no gap between the two).
                # Part 1 ALONE is not enough: on the ORDINARY happy path (attempt-1
                # succeeds — the common case, no "brief broker hiccup") order_manager
                # commits the SAME DB write but sends NO Telegram at all. If this WS
                # event beats that commit (the clean-race timing), this handler is
                # the operator's ONLY message for the move — matching DB state alone
                # would silence it and the operator would hear NOTHING (caught in
                # review: a version of this fix that checked only DB agreement did
                # exactly that). Requiring part 2 means we only suppress when a
                # second message would otherwise be genuinely redundant.
                # POSITIVE-ONLY, mirrors the #433 fail-safe above: DB not caught up,
                # a different price/order id, no matching retry-succeeded row, or
                # the re-read itself failing — ALL count as disagreement and still
                # speak. Silence is never the default.
                _agrees = False
                try:
                    async with pool.acquire() as _conn2:
                        _current = await _conn2.fetchrow(
                            "SELECT stop_order_id, stop_price FROM mi_live_trades WHERE id = $1",
                            stop_trade["id"],
                        )
                    _db_matches = bool(
                        _current
                        and _current["stop_order_id"] is not None
                        and replacement.get("id") is not None
                        and str(_current["stop_order_id"]) == str(replacement["id"])
                        and _current["stop_price"] is not None
                        and _new_stop is not None
                        and abs(float(_current["stop_price"]) - float(_new_stop)) < 0.01
                    )
                    if _db_matches:
                        # Match in PYTHON, not SQL: `mi_audit_log.detail` is a bare
                        # TEXT column (`DEFAULT ''`) and ~130 call sites across the
                        # codebase write it via log_audit_event's 2-arg form, which
                        # leaves '' — casting `detail::jsonb` in the WHERE clause
                        # risks Postgres evaluating that cast on an unrelated ''
                        # row before the event_type filter narrows the scan (SQL
                        # AND has no guaranteed evaluation order), raising and
                        # falling into the except below on ANY unrelated row from
                        # the same 5-minute window — the suppression would then
                        # never fire in production while looking green in tests.
                        # Filter to event_type + a bounded window in SQL (both
                        # plain, non-throwing comparisons), pull the handful of
                        # candidate `detail` strings, and json.loads + match each
                        # in Python where a bad row can just be skipped.
                        async with pool.acquire() as _conn3:
                            _candidates = await _conn3.fetch(
                                """
                                SELECT detail FROM mi_audit_log
                                WHERE event_type = 'stop_update_retry_succeeded'
                                  AND created_at > NOW() - INTERVAL '5 minutes'
                                ORDER BY created_at DESC
                                """
                            )
                        _dup_evidence = False
                        for _cand in (_candidates or []):
                            try:
                                _cand_detail = json.loads(_cand["detail"])
                            except Exception:  # loud-ok: a candidate row is skipped, not the check — real stop_update_retry_succeeded rows are always written with json.dumps() detail (order_manager.py:1591-1599), so this only guards a theoretical malformed row; the outer try/except around the whole agreement test still fail-safes to "speak" on any genuine read failure.
                                continue
                            if (str(_cand_detail.get("trade_id")) == str(stop_trade["id"])
                                    and str(_cand_detail.get("new_stop_id")) == str(replacement["id"])):
                                _dup_evidence = True
                                break
                        _agrees = _dup_evidence
                except Exception as _e:
                    logger.warning(
                        f"WS [{account_mode}]: post-replacement agreement re-check "
                        f"failed for {symbol} ({_e}) — treating as disagreement "
                        f"(fail-safe: still notify)"
                    )
                    _agrees = False

                if _agrees:
                    await log_audit_event(
                        "stop_replacement_confirmed_silent",
                        f"{symbol}: WS safety-net matches the trade's recorded stop "
                        f"(${float(_new_stop):.2f}, {replacement['id']}) — Telegram "
                        f"suppressed, operator already notified via order_manager",
                        json.dumps({
                            "trade_id": stop_trade["id"],
                            "ticker": symbol,
                            "account_mode": account_mode,
                            "replacement_order_id": replacement.get("id"),
                            "replacement_stop_price": float(_new_stop),
                            "event_norm": event_norm,
                            "rechecked": rechecked,
                        }),
                    )
                    logger.info(
                        f"WS [{account_mode}]: stop-leg {event_norm} but replacement live"
                        f"{_settle_note} ({replacement['id']}): {symbol} "
                        f"trade_id={stop_trade['id']} — matches DB + confirmed retry-"
                        f"succeeded audit row, Telegram suppressed"
                    )
                else:
                    # brief=True: when this DOES fire alongside live_tracker's own
                    # "Stop confirmed" for the same move (agreement check inconclusive
                    # either way), a full repeated paragraph reads as an unexplained
                    # duplicate (2026-08-12 review) — one short line plus the footer
                    # below (which says why THIS check exists) is enough; it still
                    # stands alone in the clean-race case where this is the
                    # operator's only message for the move.
                    _reason_text = describe_stop_move(
                        entry_price=float(_entry) if _entry is not None else None,
                        hard_stop=float(_hard) if _hard is not None else None,
                        old_stop_price=float(_old_stop) if _old_stop is not None else None,
                        new_stop_price=float(_new_stop) if _new_stop is not None else None,
                        brief=True,
                    )
                    _price_line = f" now ${float(_new_stop):.2f}" if _new_stop is not None else ""
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}ℹ️ *Stop replaced:* {symbol}{_price_line}\n"
                        f"{_reason_text}\n"
                        f"_Broker-side safety check after the prior stop {event_norm} — "
                        f"confirms the position stayed protected throughout._"
                    )
                    logger.info(
                        f"WS [{account_mode}]: stop-leg {event_norm} but replacement live"
                        f"{_settle_note} ({replacement['id']}): {symbol} "
                        f"trade_id={stop_trade['id']}"
                    )
            else:
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}⚠️ *Stop order {event_norm.upper()}:* {symbol}\n"
                    f"Position unprotected ({stop_trade['remaining_shares']:.0f} sh). "
                    f"Remediation runs at 4:05 PM ET — monitor."
                )
                logger.warning(
                    f"WS [{account_mode}]: stop-loss {event_norm}: {symbol} "
                    f"trade_id={stop_trade['id']}"
                )
        return

    # 3. Pending managed exit (partial/full) cancelled or rejected before fill.
    # With deferred-fill commits, the position state in mi_live_trades was
    # untouched at submit time, but for a partial exit we already cancelled
    # the original stop and placed a smaller one sized for new_remaining.
    # If the partial sell never fills, those leftover shares end up unprotected
    # — restore the stop to full remaining_shares to close the gap.
    async with pool.acquire() as conn:
        pending_exit = await conn.fetchrow("""
            UPDATE mi_live_orders SET
                status = $2, cancelled_at = NOW()
            WHERE alpaca_order_id = $1 AND status NOT IN ('filled', 'cancelled')
            RETURNING trade_id, purpose
        """, order_id, event_norm)

    if pending_exit and pending_exit["purpose"] == "partial_exit":
        async with pool.acquire() as conn:
            trade_row = await conn.fetchrow("""
                SELECT id, ticker, remaining_shares, stop_price, stop_order_id
                FROM mi_live_trades WHERE id = $1
            """, pending_exit["trade_id"])
        if trade_row and trade_row["remaining_shares"] > 0 and trade_row["stop_price"]:
            # Cancel the smaller stop and place one sized for the full remaining.
            if trade_row["stop_order_id"]:
                await alpaca.cancel_order(trade_row["stop_order_id"], account_mode=account_mode)
            try:
                restored = await alpaca.place_stop_order(
                    trade_row["ticker"],
                    int(trade_row["remaining_shares"]),
                    float(trade_row["stop_price"]),
                    account_mode=account_mode,
                )
                from agents.market_intelligence.broker.order_manager import set_stop_order_id
                await set_stop_order_id(
                    trade_row["id"], restored["id"],
                    reason="cancel_or_reject_restored",
                    account_mode=account_mode,
                )
                async with pool.acquire() as conn:
                    # Tag restored stop with purpose='stop_loss' so WS fill handler
                    # routes correctly even if stop_order_id later goes stale.
                    await conn.execute("""
                        INSERT INTO mi_live_orders
                            (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                             stop_price, status, raw_response, purpose, exit_reason)
                        VALUES ($1, $2, $3, 'sell', 'stop', $4, $5,
                                $6, $7::jsonb, 'stop_loss', 'stop_hit')
                        ON CONFLICT (alpaca_order_id) DO NOTHING
                    """, trade_row["id"], restored["id"], trade_row["ticker"],
                        float(trade_row["remaining_shares"]),
                        float(trade_row["stop_price"]),
                        restored.get("status", "new"), json.dumps(restored))
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}⚠️ *Partial exit {event_norm.upper()}:* {symbol}\n"
                    f"Sell did not fill. Stop restored to full {int(trade_row['remaining_shares'])} sh "
                    f"@${float(trade_row['stop_price']):.2f}."
                )
                logger.warning(
                    f"WS [{account_mode}]: partial exit {event_norm} for {symbol}, "
                    f"stop restored to {trade_row['remaining_shares']} sh"
                )
            except Exception as e:
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🚨 *PARTIAL EXIT {event_norm.upper()} + "
                    f"STOP RESTORE FAILED* for {symbol}!\n{e}\n"
                    f"*Position may be unprotected — manual intervention required.*"
                )
                logger.error(
                    f"WS [{account_mode}]: partial exit {event_norm} stop-restore "
                    f"failed for {symbol}: {e}"
                )
        return

    if pending_exit and pending_exit["purpose"] == "full_exit":
        # Original stop was already cancelled in execute_full_exit. Restoring
        # the stop here requires the original stop_price; mi_live_trades still
        # has it (we didn't null it out — DB commit was deferred). Surface and
        # re-place.
        async with pool.acquire() as conn:
            trade_row = await conn.fetchrow("""
                SELECT id, ticker, remaining_shares, stop_price
                FROM mi_live_trades WHERE id = $1
            """, pending_exit["trade_id"])
        if trade_row and trade_row["remaining_shares"] > 0 and trade_row["stop_price"]:
            try:
                restored = await alpaca.place_stop_order(
                    trade_row["ticker"],
                    int(trade_row["remaining_shares"]),
                    float(trade_row["stop_price"]),
                    account_mode=account_mode,
                )
                from agents.market_intelligence.broker.order_manager import set_stop_order_id
                await set_stop_order_id(
                    trade_row["id"], restored["id"],
                    reason="cancel_or_reject_restored",
                    account_mode=account_mode,
                )
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}⚠️ *Close order {event_norm.upper()}:* {symbol}\n"
                    f"Position still open ({int(trade_row['remaining_shares'])} sh). "
                    f"Stop re-placed @${float(trade_row['stop_price']):.2f}."
                )
                logger.warning(f"WS [{account_mode}]: full exit {event_norm} for {symbol}, stop re-placed")
            except Exception as e:
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🚨 *CLOSE {event_norm.upper()} + "
                    f"STOP RESTORE FAILED* for {symbol}!\n{e}\n"
                    f"*Position may be unprotected — manual intervention required.*"
                )
                logger.error(
                    f"WS [{account_mode}]: full exit {event_norm} stop-restore "
                    f"failed for {symbol}: {e}"
                )
        return

    # 4. Untracked cancellation (direct/manual Alpaca action) — still alert on rejection
    # to surface account-level issues (margin/PDT/etc.); stay quieter on expiry.
    if event_norm == "rejected":
        # #540: the event carries the broker's reason when the stream kept it —
        # an untracked rejection (margin/PDT/manual) should say why, not "check logs".
        _untracked_reason = getattr(data, "reason", None)
        _untracked_line = (
            f"\n_Broker: {str(_untracked_reason)[:300]}_" if _untracked_reason else ""
        )
        await send_telegram_message(
            f"{mode_prefix(account_mode)}⚠️ *Order REJECTED:* {symbol}\n"
            f"Order {order_id[:8]} — check logs.{_untracked_line}"
        )
        logger.warning(
            f"WS [{account_mode}]: untracked rejection: {symbol} order={order_id} "
            f"reason={_untracked_reason}"
        )
    else:
        logger.info(f"WS [{account_mode}]: untracked {event_norm}: {symbol} order={order_id}")
