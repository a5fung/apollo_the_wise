"""
WebSocket streaming for real-time Alpaca trade updates.

Replaces polling-based fill checking with instant event-driven detection.
Handles: entry fills, stop-loss triggers, Day 1 re-entry, order cancellations.

The SDK's TradingStream auto-reconnects on WebSocket errors. This module adds
an outer monitoring wrapper that restarts the stream if it dies unexpectedly,
and falls back to polling if the stream fails repeatedly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime

from alpaca.trading.stream import TradingStream

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

# ── Module state ────────────────────────────────────────────────────────────

_stream_task: asyncio.Task | None = None
_trading_stream: TradingStream | None = None
_stream_healthy: bool = False
_last_event_time: datetime | None = None
_reconnect_count: int = 0
_MAX_OUTER_RETRIES = 3


# ── Lifecycle ───────────────────────────────────────────────────────────────


async def start_trade_stream() -> None:
    """Start the WebSocket trade update stream. Called from agent.py startup."""
    global _stream_task, _trading_stream

    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        logger.info("Live trading disabled, trade stream not started")
        return

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        logger.warning("Alpaca credentials not set, trade stream not started")
        return

    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    _trading_stream = TradingStream(
        api_key=api_key,
        secret_key=secret_key,
        paper=paper,
        raw_data=False,
    )
    _trading_stream.subscribe_trade_updates(_handle_trade_update)

    # Guard against SDK changes — _run_forever is the coroutine we need
    if not hasattr(_trading_stream, "_run_forever") or not asyncio.iscoroutinefunction(
        _trading_stream._run_forever
    ):
        logger.error(
            "alpaca-py SDK changed: TradingStream._run_forever not found. "
            "Pin alpaca-py==0.43.2. Falling back to polling."
        )
        return

    _stream_task = asyncio.create_task(_run_stream_with_monitoring())
    mode = "PAPER" if paper else "LIVE"
    logger.info(f"Trade update stream started ({mode})")


async def _run_stream_with_monitoring() -> None:
    """Outer wrapper: restarts _run_forever if it exits unexpectedly."""
    global _stream_healthy, _reconnect_count

    while True:
        try:
            _stream_healthy = True
            _reconnect_count = 0
            logger.info("Trade stream connecting...")
            await _trading_stream._run_forever()
        except asyncio.CancelledError:
            logger.info("Trade stream cancelled (shutdown)")
            _stream_healthy = False
            return
        except Exception as e:
            _stream_healthy = False
            _reconnect_count += 1
            logger.error(
                f"Trade stream died unexpectedly: {e}, "
                f"reconnect attempt {_reconnect_count}/{_MAX_OUTER_RETRIES}"
            )
            if _reconnect_count >= _MAX_OUTER_RETRIES:
                await send_telegram_message(
                    f"🚨 *Trade stream failed {_MAX_OUTER_RETRIES} times*\n"
                    f"Last error: {e}\n"
                    f"Falling back to polling. Check logs."
                )
                _stream_healthy = False
                return
            backoff = min(5 * _reconnect_count, 30)
            logger.info(f"Retrying trade stream in {backoff}s...")
            await asyncio.sleep(backoff)


async def stop_trade_stream() -> None:
    """Stop the WebSocket stream. Called from agent.py shutdown."""
    global _stream_task, _trading_stream, _stream_healthy

    if _stream_task and not _stream_task.done():
        _stream_task.cancel()
        try:
            await _stream_task
        except asyncio.CancelledError:
            pass

    if _trading_stream:
        try:
            await _trading_stream.close()
        except Exception:
            pass

    _stream_healthy = False
    logger.info("Trade stream stopped")


def get_stream_status() -> dict:
    """Return stream health info for monitoring and fallback decisions."""
    return {
        "healthy": _stream_healthy,
        "last_event": _last_event_time.isoformat() if _last_event_time else None,
        "reconnect_count": _reconnect_count,
        "task_alive": _stream_task is not None and not _stream_task.done() if _stream_task else False,
    }


# ── Event Router ────────────────────────────────────────────────────────────


async def _handle_trade_update(data) -> None:
    """Central handler for all Alpaca trade update WebSocket events."""
    global _last_event_time
    _last_event_time = datetime.utcnow()

    event = str(data.event)
    order = data.order
    order_id = str(order.id)
    symbol = order.symbol

    logger.info(f"WS event: {event} | {symbol} | order={order_id} | status={order.status}")

    try:
        if event == "fill":
            await _handle_fill(data)
        elif event == "partial_fill":
            logger.info(f"Partial fill: {symbol} {data.qty} shares, order={order_id}")
        elif event in ("canceled", "cancelled", "expired", "rejected"):
            await _handle_cancel_or_reject(data, event)
        elif event in ("new", "accepted", "held"):
            logger.debug(f"Order {event}: {symbol} order_id={order_id}")
        else:
            logger.debug(f"Unhandled trade event: {event} for {symbol}")
    except Exception as e:
        logger.error(f"Error handling WS event {event} for {symbol}: {e}", exc_info=True)
        await send_telegram_message(
            f"⚠️ *Stream handler error*\n{event} for {symbol}: {e}"
        )


# ── Fill Handler ────────────────────────────────────────────────────────────


async def _handle_fill(data) -> None:
    """Route fill events to entry fill or stop-loss fill handlers."""
    order = data.order
    order_id = str(order.id)
    symbol = order.symbol
    filled_price = float(order.filled_avg_price) if order.filled_avg_price else (data.price or 0)
    filled_qty = float(order.filled_qty) if order.filled_qty else (data.qty or 0)

    pool = await get_pool()

    # 1. Check if this is an entry order fill (atomic claim)
    async with pool.acquire() as conn:
        entry_trade = await conn.fetchrow("""
            UPDATE mi_live_trades SET status = 'filling'
            WHERE entry_order_id = $1 AND status = 'order_placed'
            RETURNING *
        """, order_id)

    if entry_trade:
        await _process_entry_fill(dict(entry_trade), order, filled_price, filled_qty, pool)
        return

    # 2. Check if this is a stop-loss leg fill (atomic claim)
    async with pool.acquire() as conn:
        stop_trade = await conn.fetchrow("""
            UPDATE mi_live_trades SET status = 'stop_processing'
            WHERE stop_order_id = $1 AND status = 'filled'
            RETURNING *
        """, order_id)

    if stop_trade:
        await _process_stop_fill(dict(stop_trade), filled_price, pool)
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
        else:
            # NULL purpose = legacy mi_live_orders row submitted before this fix
            # shipped (entry/stop rows have NULL too). Already updated to
            # status='filled' above; nothing else to do here.
            logger.info(
                f"Managed fill (purpose={purpose}): {symbol} order={order_id} "
                f"{filled_qty}@${filled_price}"
            )
        return

    # 4. Truly untracked — surprise fill from a direct/manual Alpaca action.
    if filled_qty > 0:
        side = str(getattr(order, "side", "")).lower()
        side_label = "SELL" if "sell" in side else ("BUY" if "buy" in side else "FILL")
        await send_telegram_message(
            f"💱 *Untracked {side_label}:* {symbol} @${filled_price:.2f} x {filled_qty:.0f}\n"
            f"Order {order_id[:8]} not in our records — direct Alpaca action."
        )
        logger.warning(f"Untracked fill: {symbol} order={order_id} filled={filled_qty}@${filled_price}")


async def _process_entry_fill(trade: dict, order, filled_price: float, filled_qty: float, pool) -> None:
    """Handle entry order fill — update trade to 'filled' status."""
    ticker = trade["ticker"]

    # Partial fill too small (< $500)
    if filled_qty < (trade["entry_shares"] or 0) and filled_price and filled_qty * filled_price < 500:
        logger.info(f"Partial fill too small for {ticker}: {filled_qty} shares, closing")
        try:
            await alpaca.close_position(ticker)
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
            refetched = await alpaca.get_order(str(order.id))
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
                new_stop = await alpaca.place_stop_order(ticker_name, filled_qty, stop_target)
                stop_order_id = new_stop["id"]
                logger.warning(
                    f"Fill-path stop remediation: {ticker_name} qty={filled_qty} "
                    f"stop=${stop_target:.2f} order_id={stop_order_id}"
                )
                await send_telegram_message(
                    f"🛡 *Protective stop placed:* {ticker_name}\n"
                    f"Bracket leg missing — standalone stop at ${stop_target:.2f}"
                )
            except Exception as e:
                logger.error(f"Fill-path stop remediation FAILED for {ticker_name}: {e}")
                await send_telegram_message(
                    f"🚨 *UNPROTECTED POSITION:* {ticker_name}\n"
                    f"Entry filled but stop placement failed: {e}\n"
                    f"Manual intervention required."
                )
        else:
            logger.error(f"Fill-path stop remediation impossible for {ticker_name}: no orb_low")
            await send_telegram_message(
                f"🚨 *UNPROTECTED POSITION:* {ticker_name}\n"
                f"Entry filled, no stop order, no orb_low in DB. Manual intervention required."
            )

    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_live_trades SET
                status = 'filled',
                entry_price = $2, entry_shares = $3, remaining_shares = $3,
                hard_stop = $4, stop_price = $4, filled_at = NOW(),
                stop_order_id = COALESCE($5, stop_order_id)
            WHERE id = $1
        """, trade["id"], filled_price, filled_qty, float(trade["orb_low"]), stop_order_id)

        await conn.execute("""
            UPDATE mi_live_orders SET
                status = 'filled', filled_qty = $2, filled_avg_price = $3, filled_at = NOW()
            WHERE alpaca_order_id = $1
        """, str(order.id), filled_qty, filled_price)

    attempt = trade.get("entry_attempt", 1)
    await send_telegram_message(
        f"✅ *FILLED:* {ticker} (attempt {attempt})\n"
        f"Entry: ${filled_price:.2f} x {filled_qty:.0f} shares\n"
        f"Stop: ${trade['orb_low']:.2f}"
    )
    logger.info(f"WS fill: {ticker} @${filled_price:.2f} x{filled_qty:.0f}")


async def _process_stop_fill(trade: dict, stop_fill_price: float, pool) -> None:
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
        logger.info(f"WS re-entry result for {ticker}: {result}")
    else:
        # Close trade — Day 2+ or max attempts reached
        entry_price = trade["entry_price"]
        shares = trade["remaining_shares"]
        pnl = (stop_fill_price - entry_price) * shares if entry_price else 0

        exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")
        exits.append({
            "time": datetime.utcnow().isoformat(),
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
                WHERE id = $1
            """, trade["id"], json.dumps(exits), total_pnl)

        reason = "max attempts" if is_day1 else f"stop hit ({trade.get('hold_days', 0)}d)"
        await send_telegram_message(
            f"❌ *Stopped out:* {ticker} @${stop_fill_price:.2f}\n"
            f"P&L: ${pnl:+,.2f} | {reason}"
        )
        logger.info(f"WS stop-out: {ticker} @${stop_fill_price:.2f} pnl=${pnl:+,.2f}")


# ── Cancel/Reject Handler ──────────────────────────────────────────────────


async def _handle_cancel_or_reject(data, event: str) -> None:
    """Handle order cancellation, expiry, or rejection."""
    order = data.order
    order_id = str(order.id)
    symbol = order.symbol
    event_norm = "cancelled" if event in ("canceled", "cancelled") else event

    pool = await get_pool()

    # 1. Entry order?
    async with pool.acquire() as conn:
        entry_trade = await conn.fetchrow("""
            SELECT id, ticker FROM mi_live_trades
            WHERE entry_order_id = $1 AND status IN ('order_placed', 'submitting', 'pending_confirmation', 'confirmed')
        """, order_id)

    if entry_trade:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE mi_live_trades SET status = 'cancelled', skip_reason = $2 WHERE id = $1",
                entry_trade["id"], event_norm,
            )
        icon = "🚫" if event_norm == "rejected" else "🗑"
        await send_telegram_message(
            f"{icon} *Entry {event_norm.upper()}:* {symbol}\nOrder {order_id[:8]} — no position opened."
        )
        logger.info(f"WS: entry order {event_norm}: {symbol}")
        return

    # 2. Stop-loss leg cancellation — signals open position is now unprotected
    async with pool.acquire() as conn:
        stop_trade = await conn.fetchrow("""
            SELECT id, ticker, remaining_shares, stop_price FROM mi_live_trades
            WHERE stop_order_id = $1 AND status = 'filled'
        """, order_id)

    if stop_trade:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE mi_live_trades SET stop_order_id = NULL WHERE id = $1",
                stop_trade["id"],
            )
        if event_norm == "expired":
            await send_telegram_message(
                f"ℹ️ *EOD stop expired (expected):* {symbol}\n"
                f"{stop_trade['remaining_shares']:.0f} sh — GTC re-issue at 4:05 PM ET."
            )
            logger.info(f"WS: EOD stop expired (expected): {symbol} trade_id={stop_trade['id']}")
        else:
            await send_telegram_message(
                f"⚠️ *Stop order {event_norm.upper()}:* {symbol}\n"
                f"Position unprotected ({stop_trade['remaining_shares']:.0f} sh). "
                f"Remediation runs at 4:05 PM ET — monitor."
            )
            logger.warning(f"WS: stop-loss {event_norm}: {symbol} trade_id={stop_trade['id']}")
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
                await alpaca.cancel_order(trade_row["stop_order_id"])
            try:
                restored = await alpaca.place_stop_order(
                    trade_row["ticker"],
                    int(trade_row["remaining_shares"]),
                    float(trade_row["stop_price"]),
                )
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE mi_live_trades SET stop_order_id = $2 WHERE id = $1",
                        trade_row["id"], restored["id"],
                    )
                await send_telegram_message(
                    f"⚠️ *Partial exit {event_norm.upper()}:* {symbol}\n"
                    f"Sell did not fill. Stop restored to full {int(trade_row['remaining_shares'])} sh "
                    f"@${float(trade_row['stop_price']):.2f}."
                )
                logger.warning(
                    f"WS: partial exit {event_norm} for {symbol}, stop restored "
                    f"to {trade_row['remaining_shares']} sh"
                )
            except Exception as e:
                await send_telegram_message(
                    f"🚨 *PARTIAL EXIT {event_norm.upper()} + STOP RESTORE FAILED* for {symbol}!\n"
                    f"{e}\n*Position may be unprotected — manual intervention required.*"
                )
                logger.error(f"WS: partial exit {event_norm} stop-restore failed for {symbol}: {e}")
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
                )
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE mi_live_trades SET stop_order_id = $2 WHERE id = $1",
                        trade_row["id"], restored["id"],
                    )
                await send_telegram_message(
                    f"⚠️ *Close order {event_norm.upper()}:* {symbol}\n"
                    f"Position still open ({int(trade_row['remaining_shares'])} sh). "
                    f"Stop re-placed @${float(trade_row['stop_price']):.2f}."
                )
                logger.warning(f"WS: full exit {event_norm} for {symbol}, stop re-placed")
            except Exception as e:
                await send_telegram_message(
                    f"🚨 *CLOSE {event_norm.upper()} + STOP RESTORE FAILED* for {symbol}!\n"
                    f"{e}\n*Position may be unprotected — manual intervention required.*"
                )
                logger.error(f"WS: full exit {event_norm} stop-restore failed for {symbol}: {e}")
        return

    # 4. Untracked cancellation (direct/manual Alpaca action) — still alert on rejection
    # to surface account-level issues (margin/PDT/etc.); stay quieter on expiry.
    if event_norm == "rejected":
        await send_telegram_message(f"⚠️ *Order REJECTED:* {symbol}\nOrder {order_id[:8]} — check logs.")
        logger.warning(f"WS: untracked rejection: {symbol} order={order_id}")
    else:
        logger.info(f"WS: untracked {event_norm}: {symbol} order={order_id}")
