"""
Order lifecycle management for live EP trading.

Handles: order preparation, submission, fill checking, stop updates,
partial exits, full exits, EOD cleanup, and position sync.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime

from agents.market_intelligence.backtester.filters import validate_orb_entry
from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)


# ── Order Preparation ────────────────────────────────────────────────────────


async def prepare_orb_order(
    alert: dict,
    orb_bar: dict,
    atr_14: float,
    regime_record: dict | None,
) -> dict | None:
    """
    Compute entry/stop/shares/risk from ORB bar and account equity.
    Returns order spec dict or None if the trade fails validation.
    """
    orb_high = orb_bar["high"]
    orb_low = orb_bar["low"]

    # Single shared entry validation rule (same as EOD sim via validate_orb_entry)
    valid, skip_reason = validate_orb_entry(orb_high, orb_low, atr_14)
    if not valid:
        logger.info(f"{alert['ticker']}: ORB entry rejected — {skip_reason}")
        return None

    # Get actual account equity from Alpaca
    try:
        account = await alpaca.get_account()
        equity = account["equity"]
    except Exception as e:
        logger.error(f"Cannot get account equity for {alert['ticker']}, aborting order prep: {e}")
        return None

    # Position sizing: 1% risk, halved if QQQ EMA bearish
    risk_pct = 0.01
    if regime_record and regime_record.get("qqq_ema_bullish") is False:
        risk_pct *= 0.5

    risk_dollars = equity * risk_pct
    risk_per_share = orb_high - orb_low
    shares = math.floor(risk_dollars / risk_per_share)

    if shares <= 0:
        logger.warning(f"{alert['ticker']}: computed 0 shares, skipping")
        return None

    # Max 20% of account in one position
    max_position = equity * 0.20
    if shares * orb_high > max_position:
        shares = math.floor(max_position / orb_high)

    if shares <= 0:
        logger.warning(f"{alert['ticker']}: 0 shares after max-position cap (max=${max_position:.0f}, price=${orb_high:.2f})")
        return None

    position_size = shares * orb_high
    # Limit price: ORB high + 0.1% slippage buffer
    limit_price = round(orb_high * 1.001, 2)

    spec = {
        "ticker": alert["ticker"],
        "entry_price": orb_high,
        "limit_price": limit_price,
        "stop_loss_price": orb_low,
        "shares": shares,
        "risk_dollars": round(risk_dollars, 2),
        "risk_per_share": round(risk_per_share, 2),
        "position_size": round(position_size, 2),
        "equity": equity,
        "orb_high": orb_high,
        "orb_low": orb_low,
        "atr_14": atr_14,
        "ep_score": alert.get("ep_score"),
        "catalyst_quality": alert.get("catalyst_quality"),
        "gap_pct": alert.get("gap_pct"),
        "regime": regime_record.get("regime") if regime_record else None,
    }
    logger.info(
        f"Order spec: {alert['ticker']} entry=${orb_high:.2f} stop=${orb_low:.2f} "
        f"shares={shares} risk=${risk_dollars:.2f} position=${position_size:.2f} "
        f"risk_pct={risk_pct:.2%} equity=${equity:.0f}"
    )
    return spec


# ── Order Submission ─────────────────────────────────────────────────────────


async def submit_entry(trade_id: int) -> dict | None:
    """Place bracket order on Alpaca for a confirmed trade. Updates DB.

    Uses atomic status transition (confirmed → order_placed) to prevent
    duplicate orders from concurrent calls (e.g., double-click).
    """
    pool = await get_pool()

    # Atomic lock: only proceed if status is 'confirmed' and claim it
    async with pool.acquire() as conn:
        trade = await conn.fetchrow("""
            UPDATE mi_live_trades SET status = 'submitting'
            WHERE id = $1 AND status = 'confirmed'
            RETURNING *
        """, trade_id)

    if not trade:
        logger.warning(f"Trade {trade_id} not in 'confirmed' state — skipping (duplicate?)")
        return None

    ticker = trade["ticker"]
    # Deterministic client_order_id so both this call and the retry carry the
    # same ID.  Alpaca rejects a duplicate submission with the same ID, which
    # is exactly what we want: if the first call succeeded but timed out before
    # returning, the retry will get a rejection instead of creating a second position.
    client_order_id = f"apollo-{trade_id}-entry"
    try:
        order = await alpaca.place_bracket_order(
            ticker=ticker,
            qty=trade["entry_shares"],
            stop_price=trade["orb_high"],
            limit_price=round(trade["orb_high"] * 1.001, 2),
            stop_loss_price=trade["orb_low"],
            client_order_id=client_order_id,
        )
    except Exception as e:
        # 1 retry after 5s for transient errors.
        # Same client_order_id ensures Alpaca deduplicates if the first
        # submission went through but the network response was dropped.
        logger.warning(f"Entry order failed for {ticker}, retrying in 5s: {e}")
        await asyncio.sleep(5)
        try:
            order = await alpaca.place_bracket_order(
                ticker=ticker,
                qty=trade["entry_shares"],
                stop_price=trade["orb_high"],
                limit_price=round(trade["orb_high"] * 1.001, 2),
                stop_loss_price=trade["orb_low"],
                client_order_id=client_order_id,
            )
        except Exception as e2:
            logger.error(f"Entry order failed after retry for {ticker}: {e2}")
            await _update_trade_status(trade_id, "order_failed", skip_reason=str(e2))
            await send_telegram_message(f"⚠️ Order FAILED for {ticker}: {e2}")
            return None

    # Store order in DB
    entry_order_id = order["id"]
    stop_order_id = None
    if order.get("legs"):
        for leg in order["legs"]:
            if leg.get("type") == "stop":
                stop_order_id = leg["id"]
                break

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_live_trades SET
                status = 'order_placed',
                entry_order_id = $2,
                stop_order_id = $3
            WHERE id = $1
        """, trade_id, entry_order_id, stop_order_id)

        await conn.execute("""
            INSERT INTO mi_live_orders
                (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                 stop_price, limit_price, status, raw_response)
            VALUES ($1, $2, $3, 'buy', 'stop_limit', $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (alpaca_order_id) DO NOTHING
        """,
            trade_id, entry_order_id, ticker,
            float(trade["entry_shares"]),
            float(trade["orb_high"]),
            round(float(trade["orb_high"]) * 1.001, 2),
            order["status"],
            json.dumps(order),
        )

    logger.info(f"Entry order submitted: {ticker} order_id={entry_order_id}")
    return order


# ── Fill Checking ────────────────────────────────────────────────────────────


async def check_fills() -> list[dict]:
    """Poll Alpaca for fills on pending entry orders + Day 1 stop-outs for re-entry."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        pending = await conn.fetch("""
            SELECT id, ticker, entry_order_id, entry_shares, orb_low, entry_attempt
            FROM mi_live_trades
            WHERE status = 'order_placed' AND entry_order_id IS NOT NULL
        """)

    results = []
    for trade in pending:
        order = await alpaca.get_order(trade["entry_order_id"])
        if not order:
            continue

        status = order["status"]
        ticker = trade["ticker"]

        if status == "filled":
            filled_price = order["filled_avg_price"]
            filled_qty = order["filled_qty"]

            # Check for partial fill with tiny position
            if filled_qty < trade["entry_shares"] and filled_price and filled_qty * filled_price < 500:
                logger.info(f"Partial fill too small for {ticker}: {filled_qty} shares, closing")
                try:
                    await alpaca.close_position(ticker)
                except Exception as e:
                    logger.error(f"Failed to close partial fill for {ticker}: {e}")
                await _update_trade_status(trade["id"], "closed", skip_reason="partial_fill_too_small")
                results.append({"ticker": ticker, "action": "partial_cancelled"})
                continue

            # Find the stop-loss order leg
            stop_order_id = None
            for leg in order.get("legs", []):
                if leg.get("type") == "stop" or leg.get("stop_price"):
                    stop_order_id = leg["id"]
                    break

            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_trades SET
                        status = 'filled',
                        entry_price = $2,
                        entry_shares = $3,
                        remaining_shares = $3,
                        hard_stop = $4,
                        stop_price = $4,
                        filled_at = NOW(),
                        stop_order_id = COALESCE($5, stop_order_id)
                    WHERE id = $1
                """, trade["id"], filled_price, filled_qty, float(trade["orb_low"]), stop_order_id)

                # Update order audit trail
                await conn.execute("""
                    UPDATE mi_live_orders SET
                        status = 'filled',
                        filled_qty = $2,
                        filled_avg_price = $3,
                        filled_at = NOW()
                    WHERE alpaca_order_id = $1
                """, trade["entry_order_id"], filled_qty, filled_price)

            await send_telegram_message(
                f"✅ *FILLED:* {ticker} (attempt {trade.get('entry_attempt', 1)})\n"
                f"Entry: ${filled_price:.2f} × {filled_qty:.0f} shares\n"
                f"Stop: ${trade['orb_low']:.2f}"
            )
            logger.info(f"Fill: {ticker} @${filled_price:.2f} x{filled_qty:.0f}")
            results.append({"ticker": ticker, "action": "filled", "price": filled_price})

        elif status in ("cancelled", "expired", "rejected"):
            await _update_trade_status(trade["id"], "cancelled", skip_reason=status)
            logger.info(f"Order {status}: {ticker}")
            results.append({"ticker": ticker, "action": status})

    # Check Day 1 stop-outs for re-entry (max 2 attempts per Qullamaggie)
    reentry_results = await _check_day1_reentry()
    results.extend(reentry_results)

    return results


MAX_ENTRY_ATTEMPTS = 2


async def attempt_day1_reentry(
    trade_id: int,
    stop_fill_price: float,
    source: str = "polling",
) -> dict:
    """
    Attempt re-entry for a Day 1 trade that was stopped out.
    Shared by both WebSocket handler and polling fallback.

    Uses price-aware logic: if current price > ORB high, places a limit buy
    instead of a stop-limit (which would never trigger).

    Returns {"ticker": ..., "action": "reentry"|"reentry_failed"|"closed", ...}
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow("""
            SELECT id, ticker, entry_price, entry_shares, remaining_shares,
                   orb_high, orb_low, atr_14, stop_order_id, entry_attempt,
                   exits, ep_score, catalyst_quality, gap_pct, regime, alert_date
            FROM mi_live_trades WHERE id = $1
        """, trade_id)

    if not trade:
        return {"ticker": "?", "action": "not_found"}

    trade = dict(trade)
    ticker = trade["ticker"]
    entry_price = trade["entry_price"]
    shares = trade["remaining_shares"]
    orb_high = trade["orb_high"]
    orb_low = trade["orb_low"]

    # Record the stop-out exit
    pnl = (stop_fill_price - entry_price) * shares if entry_price else 0
    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")
    exits.append({
        "time": datetime.utcnow().isoformat(),
        "price": stop_fill_price,
        "reason": "stop_hit",
        "shares": shares,
        "pnl": pnl,
        "attempt": trade["entry_attempt"],
        "source": source,
    })

    attempt = trade["entry_attempt"] + 1

    # Re-entry only valid in the morning session — no late-day chasing
    from agents.market_intelligence.collector import _ET
    now_et = datetime.now(_ET)
    if now_et.hour >= 11:
        total_pnl_so_far = sum(ex.get("pnl", 0) for ex in exits)
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'closed', exits = $2::jsonb,
                    remaining_shares = 0, total_pnl = $3,
                    stop_order_id = NULL, closed_at = NOW()
                WHERE id = $1
            """, trade["id"], json.dumps(exits), total_pnl_so_far)
        await send_telegram_message(
            f"❌ *Stopped out:* {ticker} @${stop_fill_price:.2f}\n"
            f"P&L: ${pnl:+,.2f} | No re-entry after 11 AM"
        )
        logger.info(f"Day 1 stop-out ({source}): {ticker} @${stop_fill_price:.2f}, no re-entry after 11 AM")
        return {"ticker": ticker, "action": "closed", "reason": "after_11am"}

    logger.info(f"Day 1 stop-out ({source}): {ticker} @${stop_fill_price:.2f}, attempting re-entry #{attempt}")

    # Price-aware re-entry: check if price already above ORB high
    try:
        latest = await alpaca.get_latest_trade(ticker)
        if latest and latest["price"] > orb_high:
            # Price already past breakout — stop-limit would never trigger
            limit_price = round(latest["price"] * 1.002, 2)
            logger.info(
                f"Price ${latest['price']:.2f} > ORB high ${orb_high:.2f}, "
                f"using limit buy at ${limit_price:.2f}"
            )
            new_order = await alpaca.place_limit_buy_with_stop(
                ticker=ticker,
                qty=trade["entry_shares"],
                limit_price=limit_price,
                stop_loss_price=orb_low,
            )
            order_type = "limit"
        else:
            # Normal: price below ORB high, use stop-limit as usual
            new_order = await alpaca.place_bracket_order(
                ticker=ticker,
                qty=trade["entry_shares"],
                stop_price=orb_high,
                limit_price=round(orb_high * 1.001, 2),
                stop_loss_price=orb_low,
            )
            order_type = "stop_limit"
    except Exception as e:
        logger.error(f"Re-entry order failed for {ticker}: {e}")
        total_pnl = sum(ex.get("pnl", 0) for ex in exits)
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'closed', exits = $2::jsonb,
                    remaining_shares = 0, total_pnl = $3,
                    stop_order_id = NULL, closed_at = NOW(),
                    entry_attempt = $4
                WHERE id = $1
            """, trade["id"], json.dumps(exits), total_pnl, attempt)
        await send_telegram_message(
            f"❌ *Stopped out:* {ticker} @${stop_fill_price:.2f}\n"
            f"P&L: ${pnl:+,.2f} | Re-entry failed: {e}"
        )
        return {"ticker": ticker, "action": "reentry_failed"}

    # Update trade for re-entry
    new_entry_order_id = new_order["id"]
    new_stop_order_id = None
    for leg in new_order.get("legs", []):
        if leg.get("type") == "stop" or leg.get("stop_price"):
            new_stop_order_id = leg["id"]
            break

    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_live_trades SET
                status = 'order_placed',
                entry_order_id = $2,
                stop_order_id = $3,
                remaining_shares = 0,
                entry_attempt = $4,
                exits = $5::jsonb,
                filled_at = NULL
            WHERE id = $1
        """, trade["id"], new_entry_order_id, new_stop_order_id,
            attempt, json.dumps(exits))

        await conn.execute("""
            INSERT INTO mi_live_orders
                (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                 stop_price, limit_price, status, raw_response)
            VALUES ($1, $2, $3, 'buy', $4, $5, $6, $7, $8, $9::jsonb)
            ON CONFLICT (alpaca_order_id) DO NOTHING
        """,
            trade["id"], new_entry_order_id, ticker, order_type,
            float(trade["entry_shares"]),
            float(orb_high),
            round(float(orb_high) * 1.001, 2),
            new_order["status"],
            json.dumps(new_order),
        )

    entry_desc = (
        f"limit buy @${latest['price']:.2f}" if order_type == "limit"
        else f"buy >${orb_high:.2f}"
    )
    await send_telegram_message(
        f"🔄 *Re-entry:* {ticker} (attempt {attempt}/{MAX_ENTRY_ATTEMPTS})\n"
        f"Stopped @${stop_fill_price:.2f} (${pnl:+,.2f})\n"
        f"New order: {entry_desc} stop ${orb_low:.2f}\n"
        f"_[{source}]_"
    )
    logger.info(f"Re-entry order placed: {ticker} attempt={attempt} type={order_type} order_id={new_entry_order_id}")
    return {"ticker": ticker, "action": "reentry", "attempt": attempt, "order_type": order_type}


async def _check_day1_reentry() -> list[dict]:
    """
    Polling fallback: check filled Day 1 trades for stop-out.
    If stopped out and attempt < 2, calls attempt_day1_reentry().
    """
    from agents.market_intelligence.collector import et_today
    today = et_today()

    pool = await get_pool()
    async with pool.acquire() as conn:
        trades = await conn.fetch("""
            SELECT id, ticker, stop_order_id, orb_low
            FROM mi_live_trades
            WHERE alert_date = $1
              AND status = 'filled'
              AND remaining_shares > 0
              AND entry_attempt < $2
              AND stop_order_id IS NOT NULL
        """, today, MAX_ENTRY_ATTEMPTS)

    results = []
    for trade in trades:
        trade = dict(trade)
        stop_order = await alpaca.get_order(trade["stop_order_id"])
        if not stop_order or stop_order["status"] != "filled":
            continue

        stop_fill_price = stop_order.get("filled_avg_price") or trade["orb_low"]
        result = await attempt_day1_reentry(trade["id"], stop_fill_price, source="polling")
        results.append(result)

    return results


# ── Stop Management ──────────────────────────────────────────────────────────


async def update_stop(trade_id: int, new_stop_price: float) -> bool:
    """Cancel old stop order and place new one at updated price."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT * FROM mi_live_trades WHERE id = $1", trade_id,
        )
    if not trade or not trade["remaining_shares"]:
        logger.warning(f"update_stop: trade {trade_id} not found or no remaining shares")
        return False

    ticker = trade["ticker"]
    old_stop_id = trade.get("stop_order_id")

    # Cancel existing stop
    if old_stop_id:
        cancelled = await alpaca.cancel_order(old_stop_id)
        if not cancelled:
            logger.warning(f"Could not cancel old stop {old_stop_id} for {ticker} — may already be filled/cancelled")

    # Place new stop
    try:
        new_order = await alpaca.place_stop_order(
            ticker=ticker,
            qty=trade["remaining_shares"],
            stop_price=new_stop_price,
        )
    except Exception as e:
        logger.error(f"Failed to place new stop for {ticker}: {e}")
        # Urgent: stop not in place!
        await send_telegram_message(
            f"🚨 *STOP ORDER FAILED* for {ticker}!\n"
            f"Attempted stop @${new_stop_price:.2f}\n"
            f"Error: {e}\n"
            f"Position has NO stop protection!"
        )
        # Try once more
        await asyncio.sleep(3)
        try:
            new_order = await alpaca.place_stop_order(
                ticker=ticker, qty=trade["remaining_shares"], stop_price=new_stop_price,
            )
        except Exception as e2:
            logger.error(f"Stop re-placement also failed for {ticker}: {e2}")
            return False

    new_stop_id = new_order["id"]
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_live_trades SET
                stop_order_id = $2,
                stop_price = $3
            WHERE id = $1
        """, trade_id, new_stop_id, new_stop_price)

        await conn.execute("""
            INSERT INTO mi_live_orders
                (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                 stop_price, status, raw_response)
            VALUES ($1, $2, $3, 'sell', 'stop', $4, $5, $6, $7::jsonb)
            ON CONFLICT (alpaca_order_id) DO NOTHING
        """,
            trade_id, new_stop_id, ticker,
            float(trade["remaining_shares"]),
            new_stop_price, new_order["status"],
            json.dumps(new_order),
        )

    logger.info(f"Stop updated: {ticker} → ${new_stop_price:.2f}")
    return True


async def execute_partial_exit(trade_id: int, shares: float) -> bool:
    """Market sell for partial exit (1/3 position)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT * FROM mi_live_trades WHERE id = $1", trade_id,
        )
    if not trade:
        logger.warning(f"execute_partial_exit: trade {trade_id} not found")
        return False

    ticker = trade["ticker"]
    logger.info(f"Partial exit: {ticker} selling {shares:.0f} shares (trade_id={trade_id})")
    try:
        order = await alpaca.place_market_sell(ticker, shares)
    except Exception as e:
        logger.error(f"Partial exit failed for {ticker}: {e}")
        await send_telegram_message(f"⚠️ Partial exit FAILED for {ticker}: {e}")
        return False

    # Update DB
    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")
    fill_price = order.get("filled_avg_price") or trade["entry_price"]
    pnl = (fill_price - trade["entry_price"]) * shares if trade["entry_price"] else 0

    exits.append({
        "time": datetime.utcnow().isoformat(),
        "price": fill_price,
        "reason": "partial_profit",
        "shares": shares,
        "pnl": pnl,
        "order_id": order["id"],
    })

    remaining = trade["remaining_shares"] - shares
    total_pnl = sum(e.get("pnl", 0) for e in exits)

    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_live_trades SET
                exits = $2::jsonb,
                remaining_shares = $3,
                total_pnl = $4,
                partial_taken = TRUE,
                breakeven_active = TRUE
            WHERE id = $1
        """, trade_id, json.dumps(exits), remaining, total_pnl)

    # Update stop order quantity to match remaining shares
    if trade.get("stop_order_id") and remaining > 0:
        await update_stop(trade_id, trade["stop_price"])

    await send_telegram_message(
        f"📤 *Partial exit:* {ticker}\n"
        f"Sold {shares:.0f} shares @${fill_price:.2f}\n"
        f"P&L: ${pnl:+,.2f} | Remaining: {remaining:.0f}"
    )
    return True


async def execute_full_exit(trade_id: int, reason: str) -> bool:
    """Close entire remaining position."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT * FROM mi_live_trades WHERE id = $1", trade_id,
        )
    if not trade or trade["remaining_shares"] <= 0:
        logger.warning(f"execute_full_exit: trade {trade_id} not found or no remaining shares")
        return False

    ticker = trade["ticker"]
    logger.info(f"Full exit: {ticker} reason={reason} shares={trade['remaining_shares']:.0f} (trade_id={trade_id})")

    # Cancel stop order first
    if trade.get("stop_order_id"):
        cancelled = await alpaca.cancel_order(trade["stop_order_id"])
        logger.info(f"Full exit: cancelled stop {trade['stop_order_id']} for {ticker} (success={cancelled})")

    try:
        order = await alpaca.close_position(ticker)
    except Exception as e:
        logger.error(f"Full exit failed for {ticker}: {e}")
        await send_telegram_message(f"⚠️ Full exit FAILED for {ticker}: {e}")
        return False

    fill_price = order.get("filled_avg_price") or trade.get("entry_price", 0)
    remaining = trade["remaining_shares"]
    pnl = (fill_price - trade["entry_price"]) * remaining if trade["entry_price"] else 0

    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")
    exits.append({
        "time": datetime.utcnow().isoformat(),
        "price": fill_price,
        "reason": reason,
        "shares": remaining,
        "pnl": pnl,
        "order_id": order["id"],
    })
    total_pnl = sum(e.get("pnl", 0) for e in exits)

    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_live_trades SET
                status = 'closed',
                exits = $2::jsonb,
                remaining_shares = 0,
                total_pnl = $3,
                stop_order_id = NULL,
                closed_at = NOW()
            WHERE id = $1
        """, trade_id, json.dumps(exits), total_pnl)

    emoji = "✅" if total_pnl > 0 else "❌"
    await send_telegram_message(
        f"{emoji} *Closed:* {ticker} — {reason}\n"
        f"Exit @${fill_price:.2f} × {remaining:.0f} shares\n"
        f"Total P&L: ${total_pnl:+,.2f}"
    )
    return True


# ── EOD Cleanup ──────────────────────────────────────────────────────────────


async def cancel_unfilled_entries() -> int:
    """Cancel all unfilled entry orders at EOD. Returns count cancelled."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        pending = await conn.fetch("""
            SELECT id, ticker, entry_order_id
            FROM mi_live_trades
            WHERE status = 'order_placed' AND entry_order_id IS NOT NULL
        """)

    cancelled = 0
    logger.info(f"EOD cleanup: {len(pending)} unfilled entries to cancel")
    for trade in pending:
        success = await alpaca.cancel_order(trade["entry_order_id"])
        if success:
            await _update_trade_status(trade["id"], "cancelled", skip_reason="EOD unfilled")
            cancelled += 1
            logger.info(f"EOD cancel: {trade['ticker']} order_id={trade['entry_order_id']}")
        else:
            logger.warning(f"EOD cancel failed: {trade['ticker']} order_id={trade['entry_order_id']}")

    if cancelled:
        await send_telegram_message(f"🕓 EOD: cancelled {cancelled} unfilled order(s)")
    return cancelled


async def sync_positions() -> list[str]:
    """
    Reconcile DB vs Alpaca positions. Alpaca is source of truth.
    Returns list of discrepancy messages.
    """
    logger.info("Position sync starting...")
    alpaca_positions = await alpaca.get_all_positions()
    alpaca_map = {p["symbol"]: p for p in alpaca_positions}
    logger.info(f"Position sync: {len(alpaca_positions)} Alpaca positions")

    pool = await get_pool()
    async with pool.acquire() as conn:
        db_trades = await conn.fetch("""
            SELECT id, ticker, remaining_shares, entry_price, status
            FROM mi_live_trades
            WHERE status IN ('filled', 'order_placed')
        """)

    discrepancies = []

    # Check each DB trade against Alpaca
    for trade in db_trades:
        ticker = trade["ticker"]
        if ticker in alpaca_map:
            alpaca_qty = alpaca_map[ticker]["qty"]
            db_qty = trade["remaining_shares"] or 0
            if abs(alpaca_qty - db_qty) > 0.5:
                msg = f"Qty mismatch {ticker}: DB={db_qty:.0f} Alpaca={alpaca_qty:.0f}"
                discrepancies.append(msg)
                # Update DB to match Alpaca
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE mi_live_trades SET remaining_shares = $2 WHERE id = $1",
                        trade["id"], alpaca_qty,
                    )
            del alpaca_map[ticker]
        else:
            # DB says we have a position but Alpaca doesn't
            if trade["status"] == "filled" and (trade["remaining_shares"] or 0) > 0:
                msg = f"Position gone from Alpaca: {ticker} (DB says {trade['remaining_shares']:.0f} shares)"
                discrepancies.append(msg)
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE mi_live_trades SET
                            status = 'closed', remaining_shares = 0,
                            closed_at = NOW(), stop_order_id = NULL
                        WHERE id = $1
                    """, trade["id"])

    # Alpaca has positions not in DB
    for ticker, pos in alpaca_map.items():
        msg = f"Unknown Alpaca position: {ticker} ({pos['qty']:.0f} shares) — not in mi_live_trades"
        discrepancies.append(msg)

    if discrepancies:
        msg = "⚠️ *Position Sync Discrepancies:*\n" + "\n".join(f"  • {d}" for d in discrepancies)
        await send_telegram_message(msg)
        logger.warning(f"Position sync: {len(discrepancies)} discrepancies")
    else:
        logger.info("Position sync: all clear")

    return discrepancies


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _update_trade_status(trade_id: int, status: str, skip_reason: str | None = None) -> None:
    logger.info(f"Trade {trade_id} → status={status}" + (f" reason={skip_reason}" if skip_reason else ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        if skip_reason:
            await conn.execute(
                "UPDATE mi_live_trades SET status = $2, skip_reason = $3 WHERE id = $1",
                trade_id, status, skip_reason,
            )
        else:
            await conn.execute(
                "UPDATE mi_live_trades SET status = $2 WHERE id = $1",
                trade_id, status,
            )
