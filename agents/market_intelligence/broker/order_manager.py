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
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from agents.market_intelligence.backtester.filters import validate_orb_entry
from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_REENTRY_GAP_THROUGH,
    INFRA_ORDER_SUBMIT_FAILED,
    SETUP_ACCOUNT_FETCH_FAILED,
    SETUP_PRICE_EXCEEDS_CAP,
    SETUP_SIZE_TOO_SMALL,
    SETUP_STOP_TOO_WIDE,
    SETUP_ZERO_RANGE,
)
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.constants import (
    current_account_mode,
    mode_prefix,
    ENABLE_LIVE_MODE,
)
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def stop_limit_buy_price(stop_price: float) -> float:
    """Compute the LIMIT price for a stop-limit BUY parent order.

    Stop-limit semantics: once `last >= stop_price`, the order becomes a limit
    BUY at this price; it fills only if the ask is at or below the limit. A
    too-tight buffer rejects fills the instant the spread widens past stop.

    Two-floor buffer:
      - 0.5% above stop covers normal-priced names where the spread is a few
        bps wide; gives the limit room to absorb 1-2 ticks of slippage.
      - $0.02 absolute floor protects penny tickers — at $5.49 the 0.5%
        buffer is $0.027, enough to clear the spread; at $1.00 a 0.5% buffer
        rounds to a single penny and a 0.5%-only formula would be no-op.
    Doesn't address true gap-through (price runs past stop+buffer before
    order arrives) — that requires latency reduction, not wider buffer.
    """
    return round(max(stop_price * 1.005, stop_price + 0.02), 2)


# ── Order Preparation ────────────────────────────────────────────────────────


async def prepare_orb_order(
    alert: dict,
    orb_bar: dict,
    atr_14: float,
    regime_record: dict | None,
    account_mode: str | None = None,
) -> tuple[dict | None, str | None]:
    """
    Compute entry/stop/shares/risk from ORB bar and account equity.
    Returns (spec, None) on success or (None, reason) on any rejection.
    """
    orb_high = orb_bar["high"]
    orb_low = orb_bar["low"]
    ticker = alert["ticker"]

    # Single shared entry validation rule (same as EOD sim via validate_orb_entry)
    valid, skip_reason = validate_orb_entry(orb_high, orb_low, atr_14)
    if not valid:
        logger.info(f"{ticker}: ORB entry rejected — {skip_reason}")
        orb_range = orb_high - orb_low
        if skip_reason and SETUP_STOP_TOO_WIDE in skip_reason:
            orb_pct = (orb_range / orb_low * 100) if orb_low > 0 else 0
            return None, (
                f"{SETUP_STOP_TOO_WIDE}: ORB range ${orb_range:.2f} ({orb_pct:.1f}%) "
                f"> 1.5x ATR ${atr_14 * 1.5:.2f}"
            )
        return None, f"{SETUP_ZERO_RANGE}: open=high=low=${orb_high:.2f}"

    # Get actual account equity from Alpaca (per-mode for dual-account)
    try:
        account = await alpaca.get_account(account_mode=account_mode)
        equity = account["equity"]
    except Exception as e:
        logger.error(f"Cannot get account equity for {ticker}, aborting order prep: {e}")
        return None, f"{SETUP_ACCOUNT_FETCH_FAILED}: {e}"

    # Position sizing: P19 — VIX-scaled continuous risk pct (2026-05-14).
    # Reads regime_record["vix"] when available; falls back to binary
    # bearish-halve if VIX isn't ingested yet. Continuous formula
    # (in constants.vix_scaled_risk_pct):
    #   VIX ≤ 15  → 1.0× base    VIX 20 → 0.75×    VIX 25 → 0.50×
    #   VIX 30+   → 0.25× floor
    # Bearish regime additionally halves (preserves existing safety).
    from agents.market_intelligence.constants import vix_scaled_risk_pct, RISK_PCT
    vix_value = regime_record.get("vix") if regime_record else None
    risk_pct = vix_scaled_risk_pct(vix_value, base_pct=RISK_PCT)
    if regime_record and regime_record.get("qqq_ema_bullish") is False:
        risk_pct *= 0.5

    risk_dollars = equity * risk_pct
    risk_per_share = orb_high - orb_low
    shares = math.floor(risk_dollars / risk_per_share)

    if shares <= 0:
        logger.warning(f"{ticker}: computed 0 shares, skipping")
        return None, (
            f"{SETUP_SIZE_TOO_SMALL}: ${risk_dollars:.0f} risk / "
            f"${risk_per_share:.2f} per-share < 1 share"
        )

    # Max 20% of account in one position
    max_position = equity * 0.20
    if shares * orb_high > max_position:
        shares = math.floor(max_position / orb_high)

    if shares <= 0:
        logger.warning(f"{ticker}: 0 shares after max-position cap (max=${max_position:.0f}, price=${orb_high:.2f})")
        return None, (
            f"{SETUP_PRICE_EXCEEDS_CAP}: ${orb_high:.2f}/share > "
            f"${max_position:.0f} (20% of ${equity:.0f})"
        )

    position_size = shares * orb_high
    limit_price = stop_limit_buy_price(orb_high)

    spec = {
        "ticker": ticker,
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
        f"Order spec: {ticker} entry=${orb_high:.2f} stop=${orb_low:.2f} "
        f"shares={shares} risk=${risk_dollars:.2f} position=${position_size:.2f} "
        f"risk_pct={risk_pct:.2%} equity=${equity:.0f}"
    )
    return spec, None


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
    account_mode = trade.get("account_mode") or current_account_mode()
    signal_type = trade.get("signal_type") or "unknown"
    coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
    try:
        order = await alpaca.place_bracket_order(
            ticker=ticker,
            qty=trade["entry_shares"],
            stop_price=trade["orb_high"],
            limit_price=stop_limit_buy_price(trade["orb_high"]),
            stop_loss_price=trade["stop_price"],
            account_mode=account_mode,
            client_order_id=coid,
        )
    except Exception as e:
        # 1 retry after 5s for transient errors
        logger.warning(f"Entry order failed for {ticker}, retrying: {e}")
        await asyncio.sleep(5)
        try:
            # New COID for retry so client_order_id stays unique
            coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
            order = await alpaca.place_bracket_order(
                ticker=ticker,
                qty=trade["entry_shares"],
                stop_price=trade["orb_high"],
                limit_price=stop_limit_buy_price(trade["orb_high"]),
                stop_loss_price=trade["stop_price"],
                account_mode=account_mode,
                client_order_id=coid,
            )
        except Exception as e2:
            logger.error(f"Entry order failed after retry for {ticker}: {e2}")
            await _update_trade_status(
                trade_id, "order_failed",
                skip_reason=f"{INFRA_ORDER_SUBMIT_FAILED}: {e2}",
            )
            await send_telegram_message(
                f"{mode_prefix(account_mode)}⚠️ Order FAILED for {ticker}: {e2}"
            )
            return None

    # Store order in DB
    entry_order_id = order["id"]
    stop_order_id = alpaca.extract_stop_leg_id(order)

    # Submission response occasionally omits `legs` for OTO parents even when
    # the child stop was placed. A REST refetch always returns populated legs,
    # so one extra call here closes the gap that triggers the fill-path
    # remediation false alarm.
    if not stop_order_id:
        refetched = await alpaca.get_order(entry_order_id, account_mode=account_mode)
        stop_order_id = alpaca.extract_stop_leg_id(refetched)
        if not stop_order_id:
            logger.warning(
                f"{ticker} bracket {entry_order_id}: no stop leg after REST refetch — "
                f"fill handler will remediate"
            )

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
            stop_limit_buy_price(float(trade["orb_high"])),
            order["status"],
            json.dumps(order),
        )

        # OTO bracket child stop-loss leg — tag with purpose='stop_loss' so
        # WS fill handler can route reliably even when stop_order_id on
        # mi_live_trades goes stale (TEAM 5/06 + ARM 5/07 incident class).
        if stop_order_id:
            await conn.execute("""
                INSERT INTO mi_live_orders
                    (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                     stop_price, status, raw_response, purpose, exit_reason)
                VALUES ($1, $2, $3, 'sell', 'stop', $4, $5, 'new', $6::jsonb,
                        'stop_loss', 'stop_hit')
                ON CONFLICT (alpaca_order_id) DO NOTHING
            """,
                trade_id, stop_order_id, ticker,
                float(trade["entry_shares"]),
                float(trade["orb_low"]),
                json.dumps({"parent_entry_order": entry_order_id}),
            )

    logger.info(f"Entry order submitted: {ticker} order_id={entry_order_id}")
    return order


# ── Fill Checking ────────────────────────────────────────────────────────────


async def check_fills() -> list[dict]:
    """Poll Alpaca for fills on pending entry orders + Day 1 stop-outs for re-entry."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        pending = await conn.fetch("""
            SELECT id, ticker, entry_order_id, entry_shares, orb_low, stop_price,
                   entry_attempt, account_mode
            FROM mi_live_trades
            WHERE status = 'order_placed' AND entry_order_id IS NOT NULL
        """)

    results = []
    for trade in pending:
        account_mode = trade["account_mode"] or current_account_mode()
        order = await alpaca.get_order(trade["entry_order_id"], account_mode=account_mode)
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
                    await alpaca.close_position(ticker, account_mode=account_mode)
                except Exception as e:
                    logger.error(f"Failed to close partial fill for {ticker}: {e}")
                await _update_trade_status(trade["id"], "closed", skip_reason="partial_fill_too_small")
                results.append({"ticker": ticker, "action": "partial_cancelled"})
                continue

            # Find the stop-loss order leg
            stop_order_id = alpaca.extract_stop_leg_id(order)

            async with pool.acquire() as conn:
                # Gate 3 initial-stop modeling (2026-05-18): hard_stop is the
                # IMMUTABLE initial-risk basis for R-expectancy calc — set
                # ONCE at INSERT in entry_pipeline._skip from
                # order_spec["stop_loss_price"], never updated thereafter.
                # check_fills is the polling backup for entry fills; it
                # MUST NOT write hard_stop or it can corrupt the initial
                # risk basis if it runs after a same-tick trail update.
                # stop_price (current/trailed) is still written here for
                # consistency with INSERT value at the time of fill.
                await conn.execute("""
                    UPDATE mi_live_trades SET
                        status = 'filled',
                        entry_price = $2,
                        entry_shares = $3,
                        remaining_shares = $3,
                        stop_price = $4,
                        filled_at = NOW(),
                        stop_order_id = COALESCE($5, stop_order_id)
                    WHERE id = $1
                """, trade["id"], filled_price, filled_qty, float(trade["stop_price"]), stop_order_id)

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
                f"{mode_prefix()}✅ *FILLED:* {ticker} (attempt {trade.get('entry_attempt', 1)})\n"
                f"Entry: ${filled_price:.2f} × {filled_qty:.0f} shares\n"
                f"Stop: ${trade['stop_price']:.2f}"
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
                   orb_high, orb_low, stop_price, atr_14, stop_order_id, entry_attempt,
                   exits, ep_score, catalyst_quality, gap_pct, regime, alert_date,
                   account_mode, signal_type
            FROM mi_live_trades WHERE id = $1
        """, trade_id)

    if not trade:
        return {"ticker": "?", "action": "not_found"}

    trade = dict(trade)
    ticker = trade["ticker"]
    account_mode = trade.get("account_mode") or current_account_mode()
    signal_type = trade.get("signal_type") or "unknown"
    entry_price = trade["entry_price"]
    shares = trade["remaining_shares"]
    orb_high = trade["orb_high"]
    orb_low = trade["orb_low"]
    stop_loss_price = trade["stop_price"]

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

    # R3 ship 2026-05-17: drop Day-1 same-day re-entry from MAGNA53 ORB
    # path. Evidence: 0/6 re-entry win rate over 60d cohort.
    # Methodology: a failed first breakout invalidates the setup; same-day
    # re-entry chases the failure rather than respecting it.
    # Alpha-slip risk known and accepted: 65% of failed-Day-1 alpha names
    # made +5% within 21d, only 34% caught by downstream detectors.
    # Phase 7 paired work (sugar baby filter audit + MAGNA53→flag
    # carryforward) close the gap quickly post-ship. Target: 2026-05-24.
    # Env flag for fast rollback if Phase 7 slips materially.
    _R3_ENABLED = os.environ.get("R3_DAY1_REENTRY_ENABLED", "false").lower() == "true"
    if not _R3_ENABLED:
        total_pnl_so_far = sum(ex.get("pnl", 0) for ex in exits)
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'closed', exits = $2::jsonb,
                    remaining_shares = 0, total_pnl = $3,
                    stop_order_id = NULL, closed_at = NOW(),
                    skip_reason = 'block:r3_reentry_disabled'
                WHERE id = $1
            """, trade["id"], json.dumps(exits), total_pnl_so_far)
        await log_audit_event(
            "r3_day1_reentry_blocked",
            f"{ticker}: Day-1 re-entry disabled by R3 ship",
            json.dumps({
                "trade_id": trade["id"], "ticker": ticker,
                "stop_fill_price": stop_fill_price,
                "att1_pnl": pnl,
                "source": source,
            }),
        )
        await send_telegram_message(
            f"{mode_prefix(account_mode)}❌ *Stopped out:* {ticker} @${stop_fill_price:.2f}\n"
            f"P&L: ${pnl:+,.2f} | Re-entry disabled (R3 2026-05-17)"
        )
        logger.info(
            f"Day 1 stop-out ({source}): {ticker} @${stop_fill_price:.2f}, "
            f"R3 ship — re-entry disabled"
        )
        return {"ticker": ticker, "action": "closed", "reason": "r3_disabled"}

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
            f"{mode_prefix(account_mode)}❌ *Stopped out:* {ticker} @${stop_fill_price:.2f}\n"
            f"P&L: ${pnl:+,.2f} | No re-entry after 11 AM"
        )
        logger.info(f"Day 1 stop-out ({source}): {ticker} @${stop_fill_price:.2f}, no re-entry after 11 AM")
        return {"ticker": ticker, "action": "closed", "reason": "after_11am"}

    # Gap-through quality gate (#73, 2026-05-11). 90-day backtest: 5 of 6
    # multi-attempt trades had gap-through att1 stops (fill price < stop_price
    # - $0.05). Zero winning re-entries in the whole cohort; ~$1900 in
    # cumulative att2 losses. Gap-through indicates the level broke
    # decisively, not a shake-out — the setup quality is compromised.
    # Skip re-entry, close the trade with att1's loss preserved.
    stop_level = trade.get("stop_price")
    if stop_level is not None and stop_fill_price < float(stop_level) - 0.05:
        gap_through = float(stop_level) - stop_fill_price
        total_pnl_so_far = sum(ex.get("pnl", 0) for ex in exits)
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'closed', exits = $2::jsonb,
                    remaining_shares = 0, total_pnl = $3,
                    stop_order_id = NULL, closed_at = NOW(),
                    skip_reason = $4
                WHERE id = $1
            """, trade["id"], json.dumps(exits), total_pnl_so_far,
                BLOCK_REENTRY_GAP_THROUGH)
        await log_audit_event(
            "reentry_blocked_gap_through",
            f"{ticker}: att1 stop {stop_level:.2f} → fill {stop_fill_price:.2f} "
            f"(gap-through ${gap_through:.2f}); re-entry skipped",
            json.dumps({
                "trade_id": trade["id"], "ticker": ticker,
                "stop_price": float(stop_level),
                "stop_fill_price": float(stop_fill_price),
                "gap_through_dollars": float(gap_through),
                "att1_pnl": float(pnl),
            }),
        )
        await send_telegram_message(
            f"{mode_prefix(account_mode)}❌ *Stopped out:* {ticker} @${stop_fill_price:.2f}\n"
            f"P&L: ${pnl:+,.2f} | Re-entry SKIPPED — gap-through "
            f"${gap_through:.2f} past stop signals broken level"
        )
        logger.info(
            f"Day 1 stop-out ({source}): {ticker} @${stop_fill_price:.2f}, "
            f"re-entry blocked (gap-through ${gap_through:.2f})"
        )
        return {"ticker": ticker, "action": "closed", "reason": "gap_through"}

    logger.info(f"Day 1 stop-out ({source}): {ticker} @${stop_fill_price:.2f}, attempting re-entry #{attempt}")

    # Price-aware re-entry: check if price already above ORB high
    try:
        latest = await alpaca.get_latest_trade(ticker)
        coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
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
                stop_loss_price=stop_loss_price,
                account_mode=account_mode,
                client_order_id=coid,
            )
            order_type = "limit"
        else:
            # Normal: price below ORB high, use stop-limit as usual
            new_order = await alpaca.place_bracket_order(
                ticker=ticker,
                qty=trade["entry_shares"],
                stop_price=orb_high,
                limit_price=stop_limit_buy_price(orb_high),
                stop_loss_price=stop_loss_price,
                account_mode=account_mode,
                client_order_id=coid,
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
            f"{mode_prefix(account_mode)}❌ *Stopped out:* {ticker} @${stop_fill_price:.2f}\n"
            f"P&L: ${pnl:+,.2f} | Re-entry failed: {e}"
        )
        return {"ticker": ticker, "action": "reentry_failed"}

    # Update trade for re-entry
    new_entry_order_id = new_order["id"]
    new_stop_order_id = alpaca.extract_stop_leg_id(new_order)
    if not new_stop_order_id:
        refetched = await alpaca.get_order(new_entry_order_id, account_mode=account_mode)
        new_stop_order_id = alpaca.extract_stop_leg_id(refetched)

    # Invariant: total_pnl = sum(exits[].pnl). MUST update both columns
    # together. MNDY 2026-05-11 bug class — attempt 1 stopped out, attempt 2
    # placed bracket but never filled, 10:00 ET cleanup marked status='closed'
    # but total_pnl was never updated from its zero default → /trades displayed
    # $0 P/L on a >$1000 loss. Fix: update total_pnl alongside exits in every
    # path that mutates exits.
    total_pnl_after_stop = sum(ex.get("pnl", 0) for ex in exits)
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_live_trades SET
                status = 'order_placed',
                entry_order_id = $2,
                stop_order_id = $3,
                remaining_shares = 0,
                entry_attempt = $4,
                exits = $5::jsonb,
                total_pnl = $6,
                filled_at = NULL
            WHERE id = $1
        """, trade["id"], new_entry_order_id, new_stop_order_id,
            attempt, json.dumps(exits), total_pnl_after_stop)

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
            stop_limit_buy_price(float(orb_high)),
            new_order["status"],
            json.dumps(new_order),
        )

    entry_desc = (
        f"limit buy @${latest['price']:.2f}" if order_type == "limit"
        else f"buy >${orb_high:.2f}"
    )
    await send_telegram_message(
        f"{mode_prefix(account_mode)}🔄 *Re-entry:* {ticker} (attempt {attempt}/{MAX_ENTRY_ATTEMPTS})\n"
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
            SELECT id, ticker, stop_order_id, stop_price, account_mode
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
        account_mode = trade.get("account_mode") or current_account_mode()
        stop_order = await alpaca.get_order(trade["stop_order_id"], account_mode=account_mode)
        if not stop_order or stop_order["status"] != "filled":
            continue

        stop_fill_price = stop_order.get("filled_avg_price") or trade["stop_price"]
        result = await attempt_day1_reentry(trade["id"], stop_fill_price, source="polling")
        results.append(result)

    return results


# ── Stop Management ──────────────────────────────────────────────────────────


async def get_pending_exit_qty(trade_id: int) -> int:
    """Sum of qty across non-terminal partial/full-exit orders for `trade_id`.

    Single source of truth for "shares Alpaca is currently holding for a
    pending sell." Callers that size a stop against `mi_live_trades.remaining_shares`
    must subtract this — without it, the deferred-commit pattern (CLAUDE.md
    2026-05-05) leaves remaining_shares at the pre-partial value and the
    stop-placement request collides with held_for_orders. FTRE 2026-05-09
    was the trigger; sync_positions Path C orphan remediation has the same
    structural exposure.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        held = await conn.fetchval("""
            SELECT COALESCE(SUM(qty)::int, 0) FROM mi_live_orders
            WHERE trade_id = $1
              AND purpose IN ('partial_exit', 'full_exit')
              AND status NOT IN ('filled', 'cancelled', 'rejected', 'expired')
        """, trade_id)
    return int(held or 0)


async def set_stop_order_id(
    trade_id: int,
    new_id: str | None,
    *,
    reason: str,
    account_mode: str,
) -> None:
    """Single authorized writer for mi_live_trades.stop_order_id (T1.5a).

    Used for SOLO stop_order_id mutations: cycling stop orders
    (cancel old + place new), nulling on failure (orphan remediation
    triggers), recovery from cancel/reject events, and watchdog
    fallback placements.

    Multi-column atomic closes (e.g. status='closed', stop_order_id=NULL,
    closed_at=NOW()) stay inline at their respective call sites — splitting
    them via this helper would lose atomicity.

    `reason` taxonomy (used in audit event for tracing):
      - 'stop_update_succeeded'    update_stop trail succeeded
      - 'stop_update_failed'       update_stop retry failed → null
      - 'partial_replacement'      execute_partial_exit replaced stop
      - 'partial_naked'            execute_partial_exit failed → null
      - 'partial_rollback'         execute_partial_exit rollback stop
      - 'partial_rollback_failed'  execute_partial_exit both failed → null
      - 'sync_stale_stop'          sync_positions found stale broker ID
      - 'sync_remediation'         sync_positions placed remediation stop
      - 'cancel_or_reject_null'    trade_stream cleared on cancel/reject
      - 'cancel_or_reject_restored' trade_stream restored stop after cancel
      - 'stop_ack_timeout'         scheduler watchdog fallback

    Emits `stop_order_id_changed` audit event with full context.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE mi_live_trades SET stop_order_id = $1 WHERE id = $2",
            new_id, trade_id,
        )
    await log_audit_event(
        "stop_order_id_changed",
        f"trade #{trade_id} [{account_mode}]: stop_order_id={new_id or 'NULL'} (reason={reason})",
        json.dumps({
            "trade_id": trade_id,
            "account_mode": account_mode,
            "new_id": new_id,
            "reason": reason,
        }),
    )


async def update_stop(trade_id: int, new_stop_price: float) -> bool:
    """Cancel old stop order and place new one at updated price.

    Sizes the stop against `remaining_shares` MINUS any pending partial/full
    exit orders. Without that subtraction, the deferred-commit pattern
    (see CLAUDE.md 2026-05-05) leaves `remaining_shares` at the pre-partial
    value until the WS fill arrives — so a same-job-call sequence of
    `execute_partial_exit` then `update_stop` (e.g. partial fires + SMA
    trail bumps stop in the same `_live_position_update` pass) requests a
    stop for the original qty against an Alpaca position that already has
    those shares held_for_orders by the partial sell. Alpaca rejects with
    `insufficient qty` and the position goes naked. FTRE 2026-05-09 was
    the trigger — partial sell 461 of 1384, stop attempt rejected because
    of the 461 held.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT * FROM mi_live_trades WHERE id = $1", trade_id,
        )
    if not trade or not trade["remaining_shares"]:
        logger.warning(f"update_stop: trade {trade_id} not found or no remaining shares")
        await log_audit_event(
            "stop_update_aborted",
            f"trade_id={trade_id}: not found or no remaining shares",
            json.dumps({"trade_id": trade_id, "new_stop_price": new_stop_price}),
        )
        return False

    ticker = trade["ticker"]
    account_mode = trade.get("account_mode") or current_account_mode()
    signal_type = trade.get("signal_type") or "unknown"
    old_stop_id = trade.get("stop_order_id")
    old_stop_price = float(trade["stop_price"]) if trade.get("stop_price") else None

    # Subtract pending-exit qty from remaining so the stop sizes correctly
    # ahead of the deferred WS commit. See get_pending_exit_qty docstring.
    held = await get_pending_exit_qty(trade_id)
    effective_qty = int(trade["remaining_shares"]) - held
    if effective_qty <= 0:
        logger.info(
            f"update_stop: {ticker} remaining {trade['remaining_shares']} fully covered "
            f"by pending exits ({held}) — skip"
        )
        await log_audit_event(
            "stop_update_aborted",
            f"{ticker}: pending exits ({held}) cover full remaining "
            f"({trade['remaining_shares']}) — no stop sizing left",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "remaining_shares": float(trade["remaining_shares"]),
                "pending_exit_qty": held,
                "effective_qty": effective_qty,
                "new_stop_price": new_stop_price,
            }),
        )
        return False

    await log_audit_event(
        "stop_update_started",
        f"{ticker}: ${old_stop_price} → ${new_stop_price:.2f} "
        f"({effective_qty} of {int(trade['remaining_shares'])} after {held} held)",
        json.dumps({
            "trade_id": trade_id, "ticker": ticker,
            "old_stop_id": old_stop_id, "old_stop_price": old_stop_price,
            "new_stop_price": new_stop_price,
            "remaining_shares": float(trade["remaining_shares"]),
            "pending_exit_qty": held,
            "effective_qty": effective_qty,
        }),
    )

    # Cancel existing stop
    cancel_ok = True
    if old_stop_id:
        cancelled = await alpaca.cancel_order(old_stop_id, account_mode=account_mode)
        if not cancelled:
            cancel_ok = False
            logger.warning(f"Could not cancel old stop {old_stop_id} for {ticker} — may already be filled/cancelled")
            await log_audit_event(
                "stop_update_cancel_failed",
                f"{ticker}: could not cancel old stop {old_stop_id}",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "old_stop_id": old_stop_id,
                }),
            )

    # Place new stop
    try:
        coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
        new_order = await alpaca.place_stop_order(
            ticker=ticker,
            qty=effective_qty,
            stop_price=new_stop_price,
            account_mode=account_mode,
            client_order_id=coid,
        )
    except Exception as e:
        logger.error(f"Failed to place new stop for {ticker}: {e}")
        await log_audit_event(
            "stop_update_failed",
            f"{ticker}: place_stop_order raised on first attempt — {type(e).__name__}",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "new_stop_price": new_stop_price, "attempt": 1,
                "old_cancel_ok": cancel_ok,
                "error": str(e)[:500],
            }),
        )
        # Urgent: stop not in place!
        await send_telegram_message(
            f"{mode_prefix(account_mode)}🚨 *STOP ORDER FAILED* for {ticker}!\n"
            f"Attempted stop @${new_stop_price:.2f}\n"
            f"Error: {e}\n"
            f"Position has NO stop protection!"
        )
        # Try once more
        await asyncio.sleep(3)
        try:
            coid_retry = alpaca.make_client_order_id(account_mode, signal_type, ticker)
            new_order = await alpaca.place_stop_order(
                ticker=ticker, qty=effective_qty, stop_price=new_stop_price,
                account_mode=account_mode, client_order_id=coid_retry,
            )
            await log_audit_event(
                "stop_update_retry_succeeded",
                f"{ticker}: retry placed stop @${new_stop_price:.2f}",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "new_stop_price": new_stop_price,
                    "new_stop_id": new_order.get("id"),
                }),
            )
        except Exception as e2:
            logger.error(f"Stop re-placement also failed for {ticker}: {e2}")
            # Null stop_order_id so sync_positions Path C (4:05 PM + 9:00 PM)
            # can detect the orphan and remediate. Leaving the stale ID in place
            # silently masks the naked state and blocks Path C's orphan check.
            await set_stop_order_id(
                trade_id, None,
                reason="stop_update_failed",
                account_mode=account_mode,
            )
            await log_audit_event(
                "stop_update_failed",
                f"{ticker}: retry also failed — position naked, {type(e2).__name__}",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "new_stop_price": new_stop_price, "attempt": 2,
                    "old_cancel_ok": cancel_ok,
                    "stale_stop_id_cleared": old_stop_id,
                    "error_first": str(e)[:500],
                    "error_retry": str(e2)[:500],
                }),
            )
            await log_audit_event(
                "naked_position_detected",
                f"{ticker}: stop_order_id cleared; sync_positions will remediate",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "stop_price": new_stop_price,
                    "remaining_shares": float(trade["remaining_shares"]),
                    "source": "update_stop",
                }),
            )
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
                 stop_price, status, raw_response, purpose, exit_reason)
            VALUES ($1, $2, $3, 'sell', 'stop', $4, $5, $6, $7::jsonb,
                    'stop_loss', 'stop_hit')
            ON CONFLICT (alpaca_order_id) DO NOTHING
        """,
            trade_id, new_stop_id, ticker,
            float(effective_qty),
            new_stop_price, new_order["status"],
            json.dumps(new_order),
        )

    logger.info(
        f"Stop updated: {ticker} → ${new_stop_price:.2f} "
        f"({effective_qty} sh, {held} held by pending exit)"
    )
    await log_audit_event(
        "stop_updated",
        f"{ticker}: stop now ${new_stop_price:.2f} ({new_stop_id}) for {effective_qty} sh",
        json.dumps({
            "trade_id": trade_id, "ticker": ticker,
            "old_stop_id": old_stop_id, "old_stop_price": old_stop_price,
            "new_stop_id": new_stop_id, "new_stop_price": new_stop_price,
            "remaining_shares": float(trade["remaining_shares"]),
            "pending_exit_qty": held,
            "effective_qty": effective_qty,
            "old_cancel_ok": cancel_ok,
        }),
    )
    return True


async def execute_partial_exit(trade_id: int, shares: int) -> bool:
    """
    Partial exit (1/3 sell). Replaces stop for remaining 2/3 first so the
    position is always protected. On sell failure, rolls the stop back to
    the full original qty.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT * FROM mi_live_trades WHERE id = $1", trade_id,
        )
    if not trade:
        logger.warning(f"execute_partial_exit: trade {trade_id} not found")
        await log_audit_event(
            "partial_exit_aborted",
            f"trade_id={trade_id}: not found",
            json.dumps({"trade_id": trade_id, "shares": int(shares)}),
        )
        return False

    # Dedup against an already-pending exit order for this trade — without this,
    # if a sell placed by yesterday's cron is still queued (e.g. after-hours
    # market sell awaiting next open), today's cron would stack a duplicate.
    async with pool.acquire() as conn:
        pending = await conn.fetchrow("""
            SELECT alpaca_order_id, qty, purpose FROM mi_live_orders
            WHERE trade_id = $1
              AND purpose IN ('partial_exit', 'full_exit')
              AND status NOT IN ('filled', 'cancelled', 'rejected', 'expired')
            LIMIT 1
        """, trade_id)
    if pending:
        logger.info(
            f"execute_partial_exit: trade {trade_id} {trade['ticker']} already has "
            f"pending {pending['purpose']} order {pending['alpaca_order_id']} — skip"
        )
        await log_audit_event(
            "partial_exit_aborted",
            f"{trade['ticker']}: pending {pending['purpose']} order already open ({pending['alpaca_order_id']})",
            json.dumps({
                "trade_id": trade_id, "ticker": trade["ticker"],
                "pending_order_id": pending["alpaca_order_id"],
                "pending_purpose": pending["purpose"],
                "stage": "dedup_pending_exit",
            }),
        )
        return False

    ticker = trade["ticker"]
    account_mode = trade.get("account_mode") or current_account_mode()
    signal_type = trade.get("signal_type") or "unknown"
    shares = int(shares)
    full_remaining = int(trade["remaining_shares"])
    new_remaining = full_remaining - shares
    stop_price = trade["stop_price"] or trade.get("hard_stop")
    old_stop_id = trade.get("stop_order_id")

    logger.info(
        f"Partial exit: {ticker} selling {shares} of {full_remaining} shares "
        f"(new_remaining={new_remaining}, trade_id={trade_id})"
    )
    await log_audit_event(
        "partial_exit_started",
        f"{ticker}: sell {shares} of {full_remaining} (new_remaining={new_remaining})",
        json.dumps({
            "trade_id": trade_id, "ticker": ticker,
            "shares": shares, "full_remaining": full_remaining,
            "new_remaining": new_remaining,
            "stop_price": float(stop_price) if stop_price else None,
            "old_stop_id": old_stop_id,
        }),
    )

    # Step 1: Replace stop order for new_remaining before unlocking shares.
    # Cancelling the full-qty stop frees shares held-for-orders; the new
    # smaller stop immediately re-establishes protection for what we keep.
    new_stop_id = None
    if old_stop_id and stop_price and new_remaining > 0:
        cancelled = await alpaca.cancel_order(old_stop_id, account_mode=account_mode)
        if not cancelled:
            # Old stop still live — all shares held-for-orders, sell will fail.
            # Abort cleanly; morning_stop_refresh will retry tomorrow.
            logger.error(
                f"execute_partial_exit: cancel failed for stop {old_stop_id} on {ticker} — aborting"
            )
            await log_audit_event(
                "partial_exit_aborted",
                f"{ticker}: cancel failed for stop {old_stop_id}",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "old_stop_id": old_stop_id, "shares": shares,
                    "stage": "cancel_old_stop",
                }),
            )
            await send_telegram_message(
                f"{mode_prefix(account_mode)}⚠️ Partial exit ABORTED for {ticker}: "
                f"could not cancel existing stop (order {old_stop_id}). "
                f"Will retry next position update."
            )
            return False

        try:
            coid_stop = alpaca.make_client_order_id(account_mode, signal_type, ticker)
            new_stop_order = await alpaca.place_stop_order(
                ticker, new_remaining, float(stop_price),
                account_mode=account_mode, client_order_id=coid_stop,
            )
            new_stop_id = new_stop_order["id"]
            # Persist immediately — if we crash after this, sync_positions sees correct qty.
            await set_stop_order_id(
                trade_id, new_stop_id,
                reason="partial_replacement",
                account_mode=account_mode,
            )
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO mi_live_orders
                        (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                         stop_price, status, raw_response, purpose, exit_reason)
                    VALUES ($1, $2, $3, 'sell', 'stop', $4, $5, $6, $7::jsonb,
                            'stop_loss', 'stop_hit')
                    ON CONFLICT (alpaca_order_id) DO NOTHING
                """, trade_id, new_stop_id, ticker, float(new_remaining),
                    float(stop_price), new_stop_order["status"], json.dumps(new_stop_order))
            logger.info(
                f"Partial exit {ticker}: replacement stop placed for {new_remaining} shares "
                f"@${stop_price:.2f} (order {new_stop_id})"
            )
            await log_audit_event(
                "partial_exit_stop_replaced",
                f"{ticker}: stop reissued for {new_remaining} sh @${float(stop_price):.2f} ({new_stop_id})",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "new_stop_id": new_stop_id, "new_remaining": new_remaining,
                    "stop_price": float(stop_price),
                }),
            )
        except Exception as e:
            # Old stop cancelled but new one failed — position momentarily unprotected.
            logger.error(f"execute_partial_exit: replacement stop failed for {ticker}: {e}")
            # Null stop_order_id (still pointing to the now-cancelled old_stop_id)
            # so sync_positions Path C can detect the orphan and remediate.
            await set_stop_order_id(
                trade_id, None,
                reason="partial_naked",
                account_mode=account_mode,
            )
            await log_audit_event(
                "partial_exit_aborted",
                f"{ticker}: replacement stop failed — position naked, {type(e).__name__}",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "old_stop_id": old_stop_id, "new_remaining": new_remaining,
                    "stop_price": float(stop_price), "stage": "place_new_stop",
                    "stale_stop_id_cleared": old_stop_id,
                    "error": str(e)[:500],
                }),
            )
            await log_audit_event(
                "naked_position_detected",
                f"{ticker}: stop_order_id cleared; sync_positions will remediate",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "stop_price": float(stop_price),
                    "remaining_shares": float(new_remaining),
                    "source": "execute_partial_exit",
                }),
            )
            await send_telegram_message(
                f"{mode_prefix(account_mode)}🚨 *PARTIAL EXIT ABORTED* for {ticker}!\n"
                f"Old stop cancelled but new stop failed: {e}\n"
                f"*Position unprotected — place a manual stop immediately!*"
            )
            return False

    # Step 2: Market sell the partial (shares are now free from the stop).
    try:
        coid_sell = alpaca.make_client_order_id(account_mode, signal_type, ticker)
        order = await alpaca.place_market_sell(
            ticker, shares,
            account_mode=account_mode, client_order_id=coid_sell,
        )
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO mi_live_orders
                    (trade_id, alpaca_order_id, ticker, side, order_type, qty, status,
                     purpose, exit_reason, raw_response)
                VALUES ($1, $2, $3, 'sell', 'market', $4, $5,
                        'partial_exit', 'partial_profit', $6::jsonb)
                ON CONFLICT (alpaca_order_id) DO NOTHING
            """, trade_id, order["id"], ticker, float(shares),
                order.get("status", "new"), json.dumps(order))
        await log_audit_event(
            "partial_exit_sell_placed",
            f"{ticker}: market sell {shares} placed ({order.get('id')}, status={order.get('status', 'new')})",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "shares": shares, "order_id": order.get("id"),
                "order_status": order.get("status"),
            }),
        )
    except Exception as e:
        logger.error(f"Partial exit sell failed for {ticker} after stop replaced: {e}")
        await log_audit_event(
            "partial_exit_sell_failed",
            f"{ticker}: market sell raised — {type(e).__name__}, attempting rollback",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "shares": shares, "new_stop_id": new_stop_id,
                "full_remaining": full_remaining,
                "stop_price": float(stop_price) if stop_price else None,
                "error": str(e)[:500],
            }),
        )
        # Rollback: restore stop for full original qty so nothing sits unprotected.
        if new_stop_id:
            await alpaca.cancel_order(new_stop_id, account_mode=account_mode)
        try:
            coid_rollback = alpaca.make_client_order_id(account_mode, signal_type, ticker)
            rollback = await alpaca.place_stop_order(
                ticker, full_remaining, float(stop_price),
                account_mode=account_mode, client_order_id=coid_rollback,
            )
            await set_stop_order_id(
                trade_id, rollback["id"],
                reason="partial_rollback",
                account_mode=account_mode,
            )
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO mi_live_orders
                        (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                         stop_price, status, raw_response, purpose, exit_reason)
                    VALUES ($1, $2, $3, 'sell', 'stop', $4, $5, $6, $7::jsonb,
                            'stop_loss', 'stop_hit')
                    ON CONFLICT (alpaca_order_id) DO NOTHING
                """, trade_id, rollback["id"], ticker, float(full_remaining),
                    float(stop_price), rollback.get("status", "new"), json.dumps(rollback))
            await log_audit_event(
                "partial_exit_rolled_back",
                f"{ticker}: stop restored to full {full_remaining} sh @${float(stop_price):.2f} ({rollback['id']})",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "rollback_stop_id": rollback["id"],
                    "full_remaining": full_remaining,
                    "stop_price": float(stop_price),
                }),
            )
            await send_telegram_message(
                f"{mode_prefix(account_mode)}⚠️ Partial exit FAILED for {ticker}: {e}\n"
                f"Stop restored for full {full_remaining} shares @${stop_price:.2f}"
            )
            logger.warning(
                f"Partial exit {ticker}: sell failed, stop rolled back to {full_remaining} shares"
            )
        except Exception as e2:
            logger.error(f"Partial exit rollback ALSO failed for {ticker}: {e2}")
            # new_stop_id was just cancelled; rollback didn't place anything.
            # Null stop_order_id so sync_positions Path C remediates.
            await set_stop_order_id(
                trade_id, None,
                reason="partial_rollback_failed",
                account_mode=account_mode,
            )
            await log_audit_event(
                "partial_exit_rollback_failed",
                f"{ticker}: CRITICAL — sell failed AND rollback failed, position naked",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "full_remaining": full_remaining,
                    "stop_price": float(stop_price) if stop_price else None,
                    "stale_stop_id_cleared": new_stop_id,
                    "sell_error": str(e)[:500],
                    "rollback_error": str(e2)[:500],
                }),
            )
            await log_audit_event(
                "naked_position_detected",
                f"{ticker}: stop_order_id cleared; sync_positions will remediate",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "stop_price": float(stop_price) if stop_price else None,
                    "remaining_shares": float(full_remaining),
                    "source": "execute_partial_exit_rollback",
                }),
            )
            await send_telegram_message(
                f"{mode_prefix(account_mode)}🚨 *CRITICAL* {ticker}: partial sell failed AND stop rollback failed!\n"
                f"Sell error: {e}\nRollback error: {e2}\n"
                f"*Position may have NO stop — sync_positions will retry; verify on Alpaca.*"
            )
        return False

    # Step 3: Pending fill — DO NOT commit P&L / remaining_shares / partial_taken
    # at submit time. The order may be queued (after-hours) and fill at next open
    # at an unknown price; using the placement-time response here meant fill_price
    # fell back to entry_price → printed P&L $0.00 on a sale that hadn't happened.
    # finalize_partial_exit() runs from the WS fill handler with the real fill price.
    await send_telegram_message(
        f"{mode_prefix(account_mode)}📋 *Partial exit order placed:* {ticker}\n"
        f"Market sell {shares} sh — pending fill (Order {order['id'][:8]})\n"
        f"_Confirms with real P&L on fill._"
    )
    return True


async def finalize_partial_exit(
    trade_id: int,
    filled_qty: int,
    filled_price: float,
    order_id: str,
) -> None:
    """Commit a partial exit on actual fill (called from WS fill handler).

    Splits the original execute_partial_exit "Step 3" out so commit happens
    against the real Alpaca fill price, not the response at submit time.
    Idempotent: silently no-ops if the same order_id is already in exits[].
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT * FROM mi_live_trades WHERE id = $1", trade_id,
        )
    if not trade:
        logger.warning(f"finalize_partial_exit: trade {trade_id} not found")
        return

    ticker = trade["ticker"]
    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")

    # Idempotency: a duplicate WS fill for the same order_id no-ops.
    if any(e.get("order_id") == order_id for e in exits):
        logger.info(f"finalize_partial_exit: {ticker} order {order_id[:8]} already committed")
        return

    shares = int(filled_qty)
    new_remaining = int(trade["remaining_shares"]) - shares
    pnl = (filled_price - trade["entry_price"]) * shares if trade["entry_price"] else 0

    exits.append({
        "time": datetime.utcnow().isoformat(),
        "price": filled_price,
        "reason": "partial_profit",
        "shares": shares,
        "pnl": pnl,
        "order_id": order_id,
    })
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
        """, trade_id, json.dumps(exits), new_remaining, total_pnl)

    await log_audit_event(
        "partial_exit_committed",
        f"{ticker}: DB committed on WS fill — sold {shares} @${filled_price:.2f}, pnl ${pnl:+,.2f}, remaining {new_remaining}",
        json.dumps({
            "trade_id": trade_id, "ticker": ticker,
            "shares": shares, "fill_price": float(filled_price),
            "pnl": float(pnl), "total_pnl": float(total_pnl),
            "new_remaining": new_remaining,
            "order_id": order_id,
        }),
    )
    await send_telegram_message(
        f"{mode_prefix()}📤 *Partial exit FILLED:* {ticker}\n"
        f"Sold {shares} shares @${filled_price:.2f}\n"
        f"P&L: ${pnl:+,.2f} | Remaining: {new_remaining}"
    )


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

    # Dedup against pending exit orders — see execute_partial_exit comment.
    async with pool.acquire() as conn:
        pending = await conn.fetchrow("""
            SELECT alpaca_order_id, purpose FROM mi_live_orders
            WHERE trade_id = $1
              AND purpose IN ('partial_exit', 'full_exit')
              AND status NOT IN ('filled', 'cancelled', 'rejected', 'expired')
            LIMIT 1
        """, trade_id)
    if pending:
        logger.info(
            f"execute_full_exit: trade {trade_id} {trade['ticker']} already has "
            f"pending {pending['purpose']} order {pending['alpaca_order_id']} — skip"
        )
        return False

    ticker = trade["ticker"]
    account_mode = trade.get("account_mode") or current_account_mode()
    logger.info(f"Full exit: {ticker} reason={reason} shares={trade['remaining_shares']:.0f} (trade_id={trade_id})")

    # Cancel stop order first
    if trade.get("stop_order_id"):
        cancelled = await alpaca.cancel_order(trade["stop_order_id"], account_mode=account_mode)
        logger.info(f"Full exit: cancelled stop {trade['stop_order_id']} for {ticker} (success={cancelled})")

    try:
        order = await alpaca.close_position(ticker, account_mode=account_mode)
    except Exception as e:
        logger.error(f"Full exit failed for {ticker}: {e}")
        await send_telegram_message(
            f"{mode_prefix(account_mode)}⚠️ Full exit FAILED for {ticker}: {e}"
        )
        return False

    remaining = trade["remaining_shares"]
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_live_orders
                (trade_id, alpaca_order_id, ticker, side, order_type, qty, status,
                 purpose, exit_reason, raw_response)
            VALUES ($1, $2, $3, 'sell', 'market', $4, $5,
                    'full_exit', $6, $7::jsonb)
            ON CONFLICT (alpaca_order_id) DO NOTHING
        """, trade_id, order["id"], ticker, float(remaining),
            order.get("status", "new"), reason, json.dumps(order))

    # Pending fill — finalize_full_exit() runs from the WS fill handler with
    # the real fill price. Submitting close_position after-hours queues a
    # market order for next open; fill_price was None at submit time, which
    # made P&L print as 0 on a close that hadn't happened yet.
    await send_telegram_message(
        f"{mode_prefix(account_mode)}📋 *Closing order placed:* {ticker} — {reason}\n"
        f"Market sell {remaining:.0f} sh — pending fill (Order {order['id'][:8]})\n"
        f"_Confirms with real P&L on fill._"
    )
    return True


async def finalize_full_exit(
    trade_id: int,
    filled_qty: int,
    filled_price: float,
    order_id: str,
    reason: str,
) -> None:
    """Commit a full exit on actual fill (called from WS fill handler).

    Splits the post-submit DB commit out of execute_full_exit so it runs
    against the real Alpaca fill price, not the response at submit time.
    Idempotent: no-ops if the same order_id is already in exits[].
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT * FROM mi_live_trades WHERE id = $1", trade_id,
        )
    if not trade:
        logger.warning(f"finalize_full_exit: trade {trade_id} not found")
        return

    ticker = trade["ticker"]
    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")

    if any(e.get("order_id") == order_id for e in exits):
        logger.info(f"finalize_full_exit: {ticker} order {order_id[:8]} already committed")
        return

    pnl = (filled_price - trade["entry_price"]) * filled_qty if trade["entry_price"] else 0

    exits.append({
        "time": datetime.utcnow().isoformat(),
        "price": filled_price,
        "reason": reason,
        "shares": filled_qty,
        "pnl": pnl,
        "order_id": order_id,
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

    await log_audit_event(
        "full_exit_committed",
        f"{ticker}: DB committed on WS fill — closed {filled_qty} @${filled_price:.2f}, "
        f"reason={reason}, total_pnl ${total_pnl:+,.2f}",
        json.dumps({
            "trade_id": trade_id, "ticker": ticker,
            "shares": int(filled_qty), "fill_price": float(filled_price),
            "pnl": float(pnl), "total_pnl": float(total_pnl),
            "reason": reason, "order_id": order_id,
        }),
    )

    emoji = "✅" if total_pnl > 0 else "❌"
    await send_telegram_message(
        f"{mode_prefix()}{emoji} *Closed:* {ticker} — {reason}\n"
        f"Exit @${filled_price:.2f} × {filled_qty:.0f} shares\n"
        f"Total P&L: ${total_pnl:+,.2f}"
    )


async def finalize_stop_fill(
    trade_id: int,
    filled_qty: int,
    filled_price: float,
    order_id: str,
) -> None:
    """Commit a stop-loss fill on actual fill (called from WS handler).

    Mirrors finalize_full_exit but with reason='stop_hit'. Routed via
    mi_live_orders.purpose='stop_loss' instead of mi_live_trades.stop_order_id
    matching, which can go stale (TEAM 5/06 BE-stop, ARM 5/07 entry-stop classes).

    Idempotent: no-ops if the same order_id is already in exits[].
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT * FROM mi_live_trades WHERE id = $1", trade_id,
        )
    if not trade:
        logger.warning(f"finalize_stop_fill: trade {trade_id} not found")
        return

    ticker = trade["ticker"]
    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")

    if any(e.get("order_id") == order_id for e in exits):
        logger.info(f"finalize_stop_fill: {ticker} order {order_id[:8]} already committed")
        return

    pnl = (filled_price - trade["entry_price"]) * filled_qty if trade["entry_price"] else 0
    attempt = trade.get("entry_attempt", 1)

    exits.append({
        "time": datetime.utcnow().isoformat(),
        "price": filled_price,
        "reason": "stop_hit",
        "shares": filled_qty,
        "pnl": pnl,
        "attempt": attempt,
        "order_id": order_id,
        "source": "websocket",
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

    await log_audit_event(
        "stop_exit_committed",
        f"{ticker}: stopped out {filled_qty} @${filled_price:.2f}, "
        f"pnl ${pnl:+,.2f}, total ${total_pnl:+,.2f}",
        json.dumps({
            "trade_id": trade_id, "ticker": ticker,
            "shares": int(filled_qty), "fill_price": float(filled_price),
            "pnl": float(pnl), "total_pnl": float(total_pnl),
            "attempt": attempt, "order_id": order_id,
        }),
    )

    await send_telegram_message(
        f"{mode_prefix()}❌ *Stopped out:* {ticker} @${filled_price:.2f}\n"
        f"P&L: ${pnl:+,.2f} | shares: {filled_qty}"
    )


# ── EOD Cleanup ──────────────────────────────────────────────────────────────


async def cancel_unfilled_entries(reason: str = "EOD unfilled") -> int:
    """Cancel all unfilled entry orders. Returns count cancelled.

    Called from two distinct cleanup paths — passing the right reason keeps
    skip_reason and Telegram copy honest:
    - 10:00 ET ORB-window cleanup → reason="ORB window unfilled"
    - 4:05 PM EOD cleanup         → reason="EOD unfilled" (default)
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # orb_high included for gap-through telemetry (task #22) — trigger
        # price reference. pm_rvol joined from mi_ep_alerts for stratification
        # (LEFT JOIN; null-safe if alert isn't in mi_ep_alerts e.g. 9M Day 2).
        pending = await conn.fetch("""
            SELECT t.id, t.ticker, t.entry_order_id, t.alert_date, t.proposed_at,
                   t.entry_price, t.stop_price, t.entry_shares, t.orb_high,
                   t.account_mode, a.pm_rvol
            FROM mi_live_trades t
            LEFT JOIN mi_ep_alerts a
              ON a.ticker = t.ticker AND a.alert_date = t.alert_date
            WHERE t.status = 'order_placed' AND t.entry_order_id IS NOT NULL
        """)

    cancelled = 0
    cancelled_tickers: list[str] = []
    failed_tickers: list[str] = []
    logger.info(f"{reason}: {len(pending)} unfilled entries to cancel")
    event_type = "orb_unfilled_cancelled" if "ORB" in reason else "eod_unfilled_cancelled"
    if event_type == "orb_unfilled_cancelled":
        from agents.market_intelligence.broker.orb_extension_shadow import (
            record_shadow_for_cancellation,
        )
        from agents.market_intelligence.broker.gap_through_telemetry import (
            classify_orb_cancellation,
        )
    for trade in pending:
        trade_mode = trade["account_mode"] or current_account_mode()
        success = await alpaca.cancel_order(
            trade["entry_order_id"], account_mode=trade_mode,
        )
        if success:
            # If this trade has prior fills (Day-1 re-entry pattern: prior
            # attempt stopped out, re-entry never filled), don't overwrite the
            # whole trade as 'cancelled' — that masks the prior loss/profit.
            # Mark as 'closed' instead and preserve exits[]. ARM 5/07 incident:
            # entry filled $224, stop fired $219.50 (-$391.50), Day-1 re-entry
            # attempt unfilled at 10:00, cleanup wrongly marked trade
            # 'cancelled' with empty exits[].
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT exits, total_pnl FROM mi_live_trades WHERE id = $1",
                    trade["id"],
                )
            exits_raw = row["exits"] if row else None
            exits_list = (
                exits_raw if isinstance(exits_raw, list)
                else (json.loads(exits_raw) if exits_raw else [])
            )
            if exits_list:
                # Has prior history → preserve it; trade is closed not cancelled.
                # Also recompute total_pnl from exits (defense in depth — every
                # path that mutates exits SHOULD also update total_pnl, but if
                # one drops the invariant the cleanup catches it). MNDY
                # 2026-05-11 bug: row had exits=[stop_out: -$1100] but
                # total_pnl=0 → /trades showed $0 P/L on a stopped trade.
                cleanup_total_pnl = sum(
                    float(e.get("pnl") or 0) for e in exits_list
                )
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE mi_live_trades SET
                            status = 'closed',
                            closed_at = COALESCE(closed_at, NOW()),
                            skip_reason = NULL,
                            entry_order_id = NULL,
                            total_pnl = $2
                        WHERE id = $1
                    """, trade["id"], cleanup_total_pnl)
            else:
                await _update_trade_status(trade["id"], "cancelled", skip_reason=reason)
            cancelled += 1
            cancelled_tickers.append(trade["ticker"])
            logger.info(f"{reason} cancel: {trade['ticker']} order_id={trade['entry_order_id']}")
            await log_audit_event(
                event_type,
                f"{trade['ticker']} entry cancelled: {reason}",
                json.dumps({
                    "trade_id": trade["id"],
                    "ticker": trade["ticker"],
                    "entry_order_id": trade["entry_order_id"],
                    "reason": reason,
                }),
            )
            # Shadow telemetry: only the 10:00 ET ORB-window path. Excluding
            # 4:05 PM EOD cancellations keeps the dataset homogeneous (the
            # decision we're trying to make is about extending the morning
            # cutoff, not the all-day deadline).
            if (
                event_type == "orb_unfilled_cancelled"
                and trade["entry_price"] is not None
                and trade["stop_price"] is not None
                and trade["entry_shares"]
                and trade["proposed_at"] is not None
            ):
                cancellation_time = datetime.now(_ET)
                asyncio.create_task(record_shadow_for_cancellation(
                    trade_id=int(trade["id"]),
                    ticker=trade["ticker"],
                    alert_date=trade["alert_date"],
                    proposed_at=trade["proposed_at"],
                    limit_price=float(trade["entry_price"]),
                    stop_price=float(trade["stop_price"]),
                    shares=int(trade["entry_shares"]),
                    cancelled_at=cancellation_time,
                ))
                # Gap-through telemetry (task #22): classify why the limit
                # didn't fill — clean_miss vs gap_through vs would_have_filled.
                # Trigger price = orb_high (per submit_entry, the buy-stop trigger
                # is set slightly below orb_high but orb_high is the reference);
                # limit_price = entry_price (set via stop_limit_buy_price helper).
                # Fire-and-forget; bar fetch failure logs and continues.
                if trade.get("orb_high") and trade.get("entry_price"):
                    asyncio.create_task(classify_orb_cancellation(
                        trade_id=int(trade["id"]),
                        ticker=trade["ticker"],
                        alert_date=trade["alert_date"],
                        proposed_at=trade["proposed_at"],
                        trigger_price=float(trade["orb_high"]),
                        limit_price=float(trade["entry_price"]),
                        cancelled_at=cancellation_time,
                        pm_rvol=trade.get("pm_rvol"),
                    ))
        else:
            failed_tickers.append(trade["ticker"])
            logger.warning(f"{reason} cancel failed: {trade['ticker']} order_id={trade['entry_order_id']}")
            await log_audit_event(
                "unfilled_cancel_failed",
                f"{trade['ticker']} cancel failed during {reason}",
                json.dumps({
                    "trade_id": trade["id"],
                    "ticker": trade["ticker"],
                    "entry_order_id": trade["entry_order_id"],
                    "reason": reason,
                }),
            )

    if cancelled:
        # Telegram digest uses global mode_prefix — cancellations span both modes
        # in dual-account; per-trade mode is captured in the per-line audit events.
        await send_telegram_message(
            f"{mode_prefix()}🕓 {reason}: cancelled {cancelled} unfilled order(s) — {', '.join(cancelled_tickers)}"
        )
    if failed_tickers:
        await send_telegram_message(
            f"{mode_prefix()}⚠️ {reason}: cancel FAILED for {len(failed_tickers)} order(s) — {', '.join(failed_tickers)} — investigate broker side"
        )
    return cancelled


async def sync_positions() -> list[str]:
    """
    Reconcile DB vs Alpaca positions per account_mode (dual-account #66).
    Alpaca is source of truth. Returns combined list of discrepancy messages
    across both modes.

    In dual-mode (ENABLE_LIVE_MODE=true): iterates ['paper', 'live'] and runs
    isolated reconciliation per mode — paper-side discrepancies don't touch
    live trades and vice versa. Each mode's mi_live_trades query carries its
    AND account_mode=$1 filter, and each Alpaca call routes to its mode's
    TradingClient via the per-mode singleton.
    """
    modes = ["paper", "live"] if ENABLE_LIVE_MODE else ["paper"]
    all_discrepancies: list[str] = []
    for mode in modes:
        try:
            mode_discrepancies = await _sync_positions_for_mode(mode)
            all_discrepancies.extend(mode_discrepancies)
        except Exception as e:
            logger.error(f"sync_positions for mode={mode} failed: {e}", exc_info=True)
            all_discrepancies.append(f"[{mode}] sync failed: {e}")
    return all_discrepancies


async def _sync_positions_for_mode(account_mode: str) -> list[str]:
    """Per-mode reconciliation. Called by sync_positions for each mode."""
    logger.info(f"Position sync starting (mode={account_mode})...")
    alpaca_positions = await alpaca.get_all_positions(account_mode=account_mode)
    alpaca_map = {p["symbol"]: p for p in alpaca_positions}
    logger.info(f"Position sync [{account_mode}]: {len(alpaca_positions)} Alpaca positions")

    alpaca_tickers = {p["symbol"] for p in alpaca_positions}

    pool = await get_pool()
    async with pool.acquire() as conn:
        db_trades = await conn.fetch("""
            SELECT id, ticker, remaining_shares, entry_price, status,
                   stop_order_id, stop_price, orb_low, signal_type
            FROM mi_live_trades
            WHERE status IN ('filled', 'order_placed')
              AND account_mode = $1
        """, account_mode)

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
                # Audit the overwrite (SMCI 5/11 #77 forensics: previously
                # this just wrote silently with logger.info, leaving no
                # trail for "when did DB qty drift?" investigations).
                # Common cause: paper Alpaca temporarily soft-reserves
                # shares for an after-hours queued sell, so
                # get_all_positions returns reduced qty until the order
                # finalizes at next open.
                await log_audit_event(
                    "sync_qty_overwrite",
                    f"{ticker}: DB {db_qty:.0f} → Alpaca {alpaca_qty:.0f} "
                    f"(trade_id={trade['id']}, mode={account_mode})",
                    detail=json.dumps({
                        "trade_id": trade["id"],
                        "ticker": ticker,
                        "account_mode": account_mode,
                        "db_qty_before": float(db_qty),
                        "alpaca_qty_after": float(alpaca_qty),
                    }),
                )
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
        msg = f"[{account_mode}] Unknown Alpaca position: {ticker} ({pos['qty']:.0f} shares) — not in mi_live_trades"
        discrepancies.append(msg)

    # Orphaned stop check — filled positions in Alpaca with no active stop.
    # Two shapes: stop_order_id IS NULL (e.g. update_stop / execute_partial_exit
    # nulled it on placement failure), or stop_order_id IS NOT NULL but the
    # referenced order is dead at the broker (cancelled/rejected/expired/missing).
    # The second shape happens when update_stop's cancel succeeded but new
    # placement failed in a path that didn't null — we still verify here as
    # defense in depth.
    for trade in db_trades:
        ticker = trade["ticker"]
        if trade["status"] != "filled":
            continue
        if not (trade["remaining_shares"] or 0) > 0:
            continue
        if ticker not in alpaca_tickers:
            continue

        existing_stop_id = trade["stop_order_id"]
        if existing_stop_id:
            try:
                order = await alpaca.get_order(existing_stop_id, account_mode=account_mode)
            except Exception as exc:
                logger.warning(
                    f"sync_positions: get_order({existing_stop_id}) raised for {ticker}: {exc}"
                )
                order = None
            order_status = (
                str(order.get("status", "")).split(".")[-1].lower()
                if order else ""
            )
            # Only act on explicitly dead states. Active gate alone is fragile
            # — Alpaca's enum includes pending_new / pending_replace / accepted
            # _for_bidding etc., and a freshly-placed stop in pending_new
            # would be misclassified as dead and double-stopped on remediation.
            # Inverting: leave alone unless we positively confirm the order is
            # in a terminal state. Network failure (order=None) is ambiguous,
            # not dead — defer to next sync_positions run.
            DEAD_STATES = (
                "canceled", "cancelled", "expired", "rejected",
                "replaced", "filled", "done_for_day", "stopped", "suspended",
            )
            if order_status not in DEAD_STATES:
                # Active, transient, unknown, or fetch-failed — leave alone.
                continue
            # Confirmed dead: clear stale ID so remediation records a clean
            # new stop_order_id and future runs see a single source of truth.
            await set_stop_order_id(
                trade["id"], None,
                reason="sync_stale_stop",
                account_mode=account_mode,
            )
            msg = (
                f"⚠️ Stale stop {ticker}: {existing_stop_id[:8]} status="
                f"{order_status} — clearing & remediating"
            )
            discrepancies.append(msg)
            logger.warning(f"sync_positions: stale stop for {ticker}: {msg}")
            await log_audit_event(
                "naked_position_detected",
                f"{ticker}: stale stop_order_id ({order_status}) cleared by sync_positions",
                json.dumps({
                    "trade_id": trade["id"], "ticker": ticker,
                    "stale_stop_id": existing_stop_id,
                    "broker_status": order_status,
                    "source": "sync_positions",
                }),
            )
        # Position is live in Alpaca but has no stop order — remediate
        stop = trade["stop_price"] or trade["orb_low"]
        if not stop:
            msg = f"⚠️ Orphaned position {ticker}: filled with no stop & no stop_price in DB — manual intervention needed"
            discrepancies.append(msg)
            logger.error(f"sync_positions: orphaned {ticker} trade_id={trade['id']} — no stop_price to remediate")
            continue
        # Subtract pending-exit qty so a partial-exit pending at sync time
        # doesn't cause Alpaca to reject the remediation stop on insufficient
        # qty. Same shape as update_stop's accounting (FTRE 5/9). If a partial
        # is in flight, remediate to the post-partial qty; the WS handler
        # will resize the stop again when the partial fills/cancels.
        held = await get_pending_exit_qty(trade["id"])
        qty = float(int(trade["remaining_shares"]) - held)
        if qty <= 0:
            logger.warning(
                f"sync_positions: {ticker} fully covered by pending exits "
                f"({held}/{trade['remaining_shares']}) — skipping remediation"
            )
            await log_audit_event(
                "stop_remediation_skipped_pending_exit",
                f"{ticker}: {held} pending exit covers full {int(trade['remaining_shares'])} remaining",
                json.dumps({
                    "trade_id": trade["id"], "ticker": ticker,
                    "remaining_shares": float(trade["remaining_shares"]),
                    "pending_exit_qty": held,
                }),
            )
            continue
        new_order = None
        last_err: Exception | None = None
        signal_type = trade.get("signal_type") or "unknown"
        for attempt in range(1, 4):
            try:
                coid_remediate = alpaca.make_client_order_id(account_mode, signal_type, ticker)
                new_order = await alpaca.place_stop_order(
                    ticker, qty, float(stop),
                    account_mode=account_mode, client_order_id=coid_remediate,
                )
                break
            except Exception as e:
                last_err = e
                logger.warning(f"sync_positions: stop remediation attempt {attempt}/3 failed for {ticker}: {e}")
                if attempt < 3:
                    await asyncio.sleep(2 ** attempt)  # 2s, 4s
        if new_order:
            await set_stop_order_id(
                trade["id"], new_order["id"],
                reason="sync_remediation",
                account_mode=account_mode,
            )
            msg = f"🛡 Orphaned stop remediated: {ticker} qty={qty:.0f} stop=${stop:.2f}"
            discrepancies.append(msg)
            logger.warning(f"sync_positions: placed remediation stop for {ticker} trade_id={trade['id']} stop={stop:.2f}")
        else:
            msg = f"⚠️ Failed to remediate orphaned stop for {ticker} after 3 attempts: {last_err}"
            discrepancies.append(msg)
            logger.error(f"sync_positions: stop remediation failed for {ticker}: {last_err}")

    if discrepancies:
        msg = (
            f"{mode_prefix(account_mode)}⚠️ *Position Sync Discrepancies "
            f"({account_mode}):*\n" + "\n".join(f"  • {d}" for d in discrepancies)
        )
        await send_telegram_message(msg)
        logger.warning(f"Position sync [{account_mode}]: {len(discrepancies)} discrepancies")
    else:
        logger.info(f"Position sync [{account_mode}]: all clear")

    return discrepancies


# ── Helpers ──────────────────────────────────────────────────────────────────


async def prepare_9m_day2_orb_order(
    sugar_baby: dict,
    orb_bar: dict,
    regime_record: dict | None = None,
    account_mode: str | None = None,
) -> tuple[dict | None, str | None]:
    """
    Compute entry/stop/shares for a 9M sugar baby Day 2 ORB entry.

    Key difference from prepare_orb_order(): stop = prior day's low (the 9M breakout
    day low), not today's ORB low. This anchors risk to the institutional "wall."

    sugar_baby: dict from get_pending_9m_sugar_babies() — must have ticker, low_price.
    orb_bar: dict with 'high' and 'low' from alpaca.get_first_bar().
    regime_record: optional, used to halve risk in bearish QQQ regime.

    Returns (spec, None) on success or (None, reason) on any rejection. Reasons
    use the bounded vocabulary from skip_reasons.py so callers can write to
    mi_live_trades.skip_reason without post-processing.
    """
    ticker = sugar_baby["ticker"]
    orb_high = orb_bar["high"]
    prior_day_low = sugar_baby["low_price"]

    if not orb_high or not prior_day_low:
        logger.warning(f"9M Day2 {ticker}: missing orb_high or prior_day_low")
        return None, f"{SETUP_ZERO_RANGE}: missing orb_high or prior_day_low"

    if prior_day_low >= orb_high:
        logger.warning(
            f"9M Day2 {ticker}: prior_day_low ${prior_day_low:.2f} >= orb_high ${orb_high:.2f} — invalid"
        )
        return None, (
            f"{SETUP_ZERO_RANGE}: prior_day_low ${prior_day_low:.2f} "
            f">= orb_high ${orb_high:.2f}"
        )

    risk_per_share = orb_high - prior_day_low

    # Opening auction can print an orb_high very close to prior_day_low, making
    # risk_per_share near-zero. Without a floor, shares = risk_dollars / ~0 → huge
    # number that silently hits the 20% equity cap — wrong size for a 0-risk stop.
    min_risk = orb_high * 0.02
    if risk_per_share < min_risk:
        logger.warning(
            f"9M Day2 {ticker}: risk_per_share ${risk_per_share:.2f} below 2% floor "
            f"(${min_risk:.2f}) — enforcing floor to prevent oversizing"
        )
        risk_per_share = min_risk

    if (risk_per_share / orb_high) > 0.15:
        logger.warning(
            f"9M Day2 {ticker}: stop distance {risk_per_share/orb_high:.1%} > 15% — too wide, skipping"
        )
        return None, (
            f"{SETUP_STOP_TOO_WIDE}: stop distance {risk_per_share/orb_high:.1%} > 15%"
        )

    try:
        account = await alpaca.get_account(account_mode=account_mode)
        equity = account["equity"]
    except Exception as e:
        logger.error(f"9M Day2 {ticker}: cannot get account equity — {e}")
        return None, f"{SETUP_ACCOUNT_FETCH_FAILED}: {e}"

    # P19 VIX-scaled sizing (same path as MAGNA53 prepare_orb_order).
    from agents.market_intelligence.constants import vix_scaled_risk_pct, RISK_PCT
    vix_value = regime_record.get("vix") if regime_record else None
    risk_pct = vix_scaled_risk_pct(vix_value, base_pct=RISK_PCT)
    if regime_record and regime_record.get("qqq_ema_bullish") is False:
        risk_pct *= 0.5

    risk_dollars = equity * risk_pct
    shares = math.floor(risk_dollars / risk_per_share)

    max_position = equity * 0.20
    if shares * orb_high > max_position:
        shares = math.floor(max_position / orb_high)

    if shares < 1:
        logger.warning(f"9M Day2 {ticker}: computed 0 shares — skipping")
        return None, (
            f"{SETUP_SIZE_TOO_SMALL}: ${risk_dollars:.0f} risk / "
            f"${risk_per_share:.2f} per-share < 1 share"
        )

    spec = {
        "ticker": ticker,
        "entry_price": orb_high,
        "limit_price": stop_limit_buy_price(orb_high),
        "stop_loss_price": round(prior_day_low, 2),
        "orb_high": orb_high,
        "orb_low": orb_bar["low"],
        "shares": shares,
        "risk_dollars": round(shares * risk_per_share, 2),
        "risk_per_share": round(risk_per_share, 2),
        "position_size": round(shares * orb_high, 2),
        "equity": equity,
        "trade_type": "9m_ep_day2",
        "sugar_baby_date": str(sugar_baby["alert_date"]),
    }
    return spec, None


async def track_open_position_extremes() -> int:
    """Update worst-price / best-price seen for every open position.

    Runs every 5 min during market hours. For each unique ticker with open
    trades, fetches today's minute bars from Polygon, takes the recent
    period's MIN(low) and MAX(high), and applies monotonic LEAST/GREATEST
    against the persisted values on every trade row for that ticker.

    Lifetime extremes (across the whole trade, including any Day-1 re-entry
    attempts) — not per-attempt. Initialized to entry_price by
    trade_stream._process_entry_fill; this job tightens (lows down, highs
    up) over the trade's life.

    Returns count of trade rows updated.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        open_trades = await conn.fetch("""
            SELECT id, ticker, filled_at
            FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0
        """)
    if not open_trades:
        return 0

    from collections import defaultdict
    by_ticker: dict[str, list] = defaultdict(list)
    for t in open_trades:
        by_ticker[t["ticker"]].append(t)

    from agents.market_intelligence.collector import get_minute_bars, et_today
    today_str = et_today().isoformat()

    # Per-trade filtering by filled_at (#74): Polygon get_minute_bars returns
    # extended-hours bars including pre-market, which captured BW's pre-open
    # dip at $14.51 below the $16.49 stop and stored it as lowest_price_seen
    # even though the trade only filled at 9:53 ET. Fix: only consider bars
    # whose timestamp >= trade's filled_at.
    update_rows: list[tuple[int, float, float]] = []
    for ticker, trades in by_ticker.items():
        try:
            bars = await get_minute_bars(ticker, today_str, today_str)
        except Exception as e:
            logger.warning(f"track_extremes: {ticker} minute bars fetch failed: {e}")
            continue
        if not bars:
            continue
        for trade in trades:
            filled_at = trade["filled_at"]
            if not filled_at:
                continue
            filled_ms = int(filled_at.timestamp() * 1000)
            in_hold = [
                b for b in bars
                if b.get("t") and int(b["t"]) >= filled_ms
                and b.get("l") and b.get("h")
            ]
            if not in_hold:
                continue
            period_low = min(float(b["l"]) for b in in_hold)
            period_high = max(float(b["h"]) for b in in_hold)
            if period_low <= 0 or period_high <= 0:
                continue
            update_rows.append((trade["id"], period_low, period_high))

    if not update_rows:
        return 0
    async with pool.acquire() as conn:
        await conn.executemany("""
            UPDATE mi_live_trades SET
                lowest_price_seen = LEAST(COALESCE(lowest_price_seen, $2), $2),
                highest_price_seen = GREATEST(COALESCE(highest_price_seen, $3), $3)
            WHERE id = $1
        """, update_rows)
    return len(update_rows)


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
