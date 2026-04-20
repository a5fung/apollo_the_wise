"""
Live trade tracker — the real-time analog of backtester/tracker.py.

Reuses the same trading logic (ORB entry, SMA trail, partials) but executes
via Alpaca broker instead of simulating retroactively.

Schedule:
- 9:32 AM ET: process_new_alerts_live() — ORB monitor, send proposals
- 4:45 PM ET: update_open_positions_live() — SMA trail, partials, stop updates
- 9:35 AM ET: morning_stop_refresh() — refresh stops for Day 2+ positions
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta, time

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.order_manager import (
    prepare_orb_order,
    execute_partial_exit,
    execute_full_exit,
    update_stop,
)
from agents.market_intelligence.broker.telegram_confirm import send_trade_proposal
from agents.market_intelligence.backtester.filters import check_filters, compute_atr_14
from agents.market_intelligence.collector import et_today, get_index_history
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.constants import (
    LIVE_TRADING_ENABLED,
    MAX_CONCURRENT_LIVE_POSITIONS,
    DAILY_LOSS_LIMIT_PCT,
    CIRCUIT_BREAKER_CONSEC_LOSSES,
)

logger = logging.getLogger(__name__)


# ── Safeguards ───────────────────────────────────────────────────────────────


async def _check_safeguards() -> tuple[bool, str | None]:
    """
    Check all safety gates before proposing a new trade.
    Returns (ok, reason) — reason is None if ok.
    """
    if not LIVE_TRADING_ENABLED:
        logger.debug("Safeguard: live trading disabled")
        return False, "live_trading_disabled"

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Max concurrent positions
        open_count = await conn.fetchval("""
            SELECT COUNT(*) FROM mi_live_trades
            WHERE status IN ('filled', 'order_placed', 'pending_confirmation', 'confirmed')
        """)
        if open_count >= MAX_CONCURRENT_LIVE_POSITIONS:
            logger.info(f"Safeguard blocked: max positions ({open_count}/{MAX_CONCURRENT_LIVE_POSITIONS})")
            return False, f"max_positions ({open_count}/{MAX_CONCURRENT_LIVE_POSITIONS})"

        # Daily loss limit
        try:
            account = await alpaca.get_account()
            equity = account["equity"]
        except Exception as e:
            logger.error(f"Safeguard: cannot get account equity: {e}")
            return False, "cannot_get_account"

        today = et_today()
        today_losses = await conn.fetchval("""
            SELECT COALESCE(SUM(total_pnl), 0)
            FROM mi_live_trades
            WHERE alert_date = $1 AND status = 'closed' AND total_pnl < 0
        """, today)
        daily_limit = equity * DAILY_LOSS_LIMIT_PCT
        if abs(today_losses) >= daily_limit:
            logger.info(f"Safeguard blocked: daily loss limit (${today_losses:+,.0f} >= ${daily_limit:.0f})")
            return False, f"daily_loss_limit (${today_losses:+,.0f} >= ${daily_limit:.0f})"

        # Circuit breaker: N consecutive losses
        recent_closed = await conn.fetch("""
            SELECT total_pnl FROM mi_live_trades
            WHERE status = 'closed' AND total_pnl IS NOT NULL
            ORDER BY closed_at DESC LIMIT $1
        """, CIRCUIT_BREAKER_CONSEC_LOSSES)

        if len(recent_closed) >= CIRCUIT_BREAKER_CONSEC_LOSSES:
            all_losses = all(r["total_pnl"] <= 0 for r in recent_closed)
            if all_losses:
                logger.info(f"Safeguard blocked: circuit breaker ({CIRCUIT_BREAKER_CONSEC_LOSSES} consecutive losses)")
                return False, f"circuit_breaker ({CIRCUIT_BREAKER_CONSEC_LOSSES} consecutive losses)"

    return True, None


# ── New Alerts (Day 1) ───────────────────────────────────────────────────────


async def _submit_orb_trade(
    alert: dict,
    orb_bar: dict,
    atr_14: float | None,
    today: date,
    regime_record: dict | None,
    pool,
) -> dict:
    """Build order spec, check safeguards, and submit trade for a single alert."""
    ticker = alert["ticker"]

    order_spec, spec_reason = await prepare_orb_order(alert, orb_bar, atr_14 or 0, regime_record)
    if not order_spec:
        skip_msg = spec_reason or "order spec failed"
        await _insert_skipped_trade(ticker, today, alert, regime_record, skip_msg)
        await send_telegram_message(f"⏭️ *{ticker}* ORB skipped: {skip_msg}")
        try:
            from agents.market_intelligence.db import log_audit_event
            atr_str = f"{atr_14:.2f}" if atr_14 else "n/a"
            await log_audit_event(
                "orb_skipped",
                f"{ticker} — {skip_msg} | ORB H={orb_bar['high']:.2f} L={orb_bar['low']:.2f} ATR={atr_str}",
            )
        except Exception:
            pass
        return {"ticker": ticker, "action": "skipped", "reason": skip_msg}

    ok, sg_reason = await _check_safeguards()
    if not ok:
        await _insert_skipped_trade(ticker, today, alert, regime_record, sg_reason)
        await send_telegram_message(f"🚫 *{ticker}* blocked by safeguard: {sg_reason}")
        return {"ticker": ticker, "action": "blocked", "reason": sg_reason}

    async with pool.acquire() as conn:
        trade_id = await conn.fetchval("""
            INSERT INTO mi_live_trades
                (ticker, alert_date, ep_score, catalyst_quality, gap_pct, regime,
                 status, orb_high, orb_low, atr_14,
                 entry_price, entry_shares, stop_price, hard_stop,
                 position_size, risk_dollars, proposed_at)
            VALUES ($1,$2,$3,$4,$5,$6,'pending_confirmation',$7,$8,$9,
                    $10,$11,$12,$13,$14,$15,NOW())
            ON CONFLICT (ticker, alert_date) DO NOTHING
            RETURNING id
        """,
            ticker, today, alert["ep_score"],
            alert.get("catalyst_quality"), alert.get("gap_pct"),
            order_spec.get("regime"),
            order_spec["orb_high"], order_spec["orb_low"], atr_14,
            order_spec["entry_price"], float(order_spec["shares"]),
            order_spec["stop_loss_price"], order_spec["stop_loss_price"],
            order_spec["position_size"], order_spec["risk_dollars"],
        )

    if not trade_id:
        logger.debug(f"Trade already exists for {ticker}, skipping proposal")
        return {"ticker": ticker, "action": "skipped", "reason": "already_exists"}

    is_paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    if is_paper:
        logger.info(f"Paper auto-confirm: {ticker} (trade_id={trade_id})")
        from agents.market_intelligence.broker.order_manager import submit_entry
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET status = 'confirmed', confirmed_at = NOW()
                WHERE id = $1
            """, trade_id)
        order = await submit_entry(trade_id)
        if order:
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event(
                    "orb_order_placed",
                    f"{ticker} entry=${order_spec['entry_price']:.2f} stop=${order_spec['stop_loss_price']:.2f} shares={order_spec['shares']} risk=${order_spec['risk_dollars']:.0f} trade_id={trade_id}",
                )
            except Exception:
                pass
            await send_telegram_message(
                f"📊 *Paper trade auto-entered:* {ticker}\n"
                f"Entry: ${order_spec['entry_price']:.2f} | Stop: ${order_spec['stop_loss_price']:.2f}\n"
                f"Shares: {order_spec['shares']} | Risk: ${order_spec['risk_dollars']:.0f}"
            )
            return {"ticker": ticker, "action": "auto_entered", "trade_id": trade_id}
        else:
            logger.error(f"submit_entry returned None for {ticker} (trade_id={trade_id}) — order placement failed, check order_failed status in DB")
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event("orb_order_failed", f"{ticker} — submit_entry returned None (trade_id={trade_id}), check mi_live_trades.skip_reason")
            except Exception:
                pass
            await send_telegram_message(f"⚠️ *Paper auto-enter failed:* {ticker} — check logs (trade_id={trade_id})")
            return {"ticker": ticker, "action": "auto_enter_failed"}
    else:
        sent = await send_trade_proposal(alert, order_spec, trade_id)
        if sent:
            logger.info(f"Trade proposal sent: {ticker} (id={trade_id})")
            return {"ticker": ticker, "action": "proposed", "trade_id": trade_id}
        else:
            return {"ticker": ticker, "action": "proposal_send_failed"}


async def process_new_alerts_live(today: date | None = None, trigger: str = "cron") -> list[dict]:
    """
    For each HIGH EP alert today:
    1. Pre-trade filters (ADV, ATR)
    2. Fetch first 1-min bar from Alpaca
    3. ATR validation
    4. Build order spec
    5. Check safeguards
    6. Send Telegram proposal with inline keyboard
    7. Store pending proposal in DB

    trigger: "bar_stream" | "cron_9_31" | "cron_fallback" | "cron" — logged for debugging
    """
    if today is None:
        today = et_today()

    if not LIVE_TRADING_ENABLED:
        logger.info("Live trading disabled, skipping")
        return []

    # Get today's HIGH EP alerts
    pool = await get_pool()
    async with pool.acquire() as conn:
        alerts = await conn.fetch("""
            SELECT DISTINCT ON (ticker)
                   ticker, alert_date, gap_pct, rel_volume, ep_score,
                   score_tier, catalyst, catalyst_quality, vol_percentile
            FROM mi_ep_alerts
            WHERE alert_date = $1 AND score_tier = 'HIGH'
            ORDER BY ticker, ep_score DESC
        """, today)
    alerts = [dict(a) for a in alerts]

    if not alerts:
        logger.info("No HIGH EP alerts today for live trading")
        return []

    logger.info(f"ORB monitor [{trigger}]: {len(alerts)} HIGH EP alerts to process: {[a['ticker'] for a in alerts]}")
    try:
        from agents.market_intelligence.db import log_audit_event
        await log_audit_event("orb_triggered", f"[{trigger}] {len(alerts)} alerts: {[a['ticker'] for a in alerts]}")
    except Exception:
        pass

    # Get regime
    async with pool.acquire() as conn:
        regime_record = await conn.fetchrow(
            "SELECT * FROM mi_market_regime WHERE regime_date <= $1 ORDER BY regime_date DESC LIMIT 1",
            today,
        )
    regime_record = dict(regime_record) if regime_record else None

    results = []
    pending_orb: list[tuple[dict, float | None]] = []  # (alert, atr_14) awaiting ORB bar

    for alert in alerts:
        ticker = alert["ticker"]

        # Skip if already processed today
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM mi_live_trades WHERE ticker = $1 AND alert_date = $2)",
                ticker, today,
            )
        if exists:
            logger.debug(f"Live trade already exists for {ticker} on {today}")
            continue

        # Pre-trade filters (ADV, ATR% — skip mcap for small account)
        passed, skip_reason = await check_filters(ticker, today)
        if not passed:
            await _insert_skipped_trade(ticker, today, alert, regime_record, skip_reason)
            logger.info(f"ORB filter [{trigger}]: {ticker} skipped — {skip_reason}")
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event("orb_filtered", f"{ticker} [{trigger}] — {skip_reason}")
            except Exception:
                pass
            await send_telegram_message(f"⏭️ *{ticker}* ORB skipped: {skip_reason}")
            results.append({"ticker": ticker, "action": "filtered", "reason": skip_reason})
            continue

        # Compute ATR
        atr_14, _atr_pct = await compute_atr_14(ticker, today)

        # Fetch first 1-min bar from Alpaca — retry every 60s until 9:35 ET
        orb_bar = await alpaca.get_first_bar(ticker, today)
        if not orb_bar:
            logger.warning(f"ORB bar not available yet for {ticker} [{trigger}] — queuing for retry")
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event("orb_bar_miss", f"{ticker} [{trigger}] attempt 1 — bar not available, queuing retry")
            except Exception:
                pass
            pending_orb.append((alert, atr_14))
            results.append({"ticker": ticker, "action": "pending_orb"})
            continue

        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event("orb_bar_fetched", f"{ticker} [{trigger}] O={orb_bar['open']:.2f} H={orb_bar['high']:.2f} L={orb_bar['low']:.2f} range={orb_bar['high']-orb_bar['low']:.2f}")
        except Exception:
            pass
        result = await _submit_orb_trade(alert, orb_bar, atr_14, today, regime_record, pool)
        results.append(result)

    # Retry pending ORB bars every 60s until 9:35 ET (max 3 retries)
    MAX_ORB_RETRIES = 3
    retry = 0
    while pending_orb and retry < MAX_ORB_RETRIES:
        retry += 1
        logger.info(f"ORB retry {retry}/{MAX_ORB_RETRIES}: waiting 60s for {[a['ticker'] for a, _ in pending_orb]}")
        await asyncio.sleep(60)
        still_pending = []
        for alert, atr_14 in pending_orb:
            ticker = alert["ticker"]
            orb_bar = await alpaca.get_first_bar(ticker, today)
            if not orb_bar:
                logger.warning(f"ORB bar still unavailable for {ticker} [{trigger}] (retry {retry}/{MAX_ORB_RETRIES})")
                try:
                    from agents.market_intelligence.db import log_audit_event
                    await log_audit_event("orb_bar_miss", f"{ticker} [{trigger}] retry {retry}/{MAX_ORB_RETRIES} — still no bar")
                except Exception:
                    pass
                still_pending.append((alert, atr_14))
                continue
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event("orb_bar_fetched", f"{ticker} [{trigger}] retry {retry} O={orb_bar['open']:.2f} H={orb_bar['high']:.2f} L={orb_bar['low']:.2f} range={orb_bar['high']-orb_bar['low']:.2f}")
            except Exception:
                pass
            result = await _submit_orb_trade(alert, orb_bar, atr_14, today, regime_record, pool)
            # Remove the pending_orb placeholder from results
            results = [r for r in results if not (r.get("ticker") == ticker and r.get("action") == "pending_orb")]
            results.append(result)
        pending_orb = still_pending

    # Any tickers still without an ORB bar after retries — mark as skipped
    for alert, atr_14 in pending_orb:
        ticker = alert["ticker"]
        await _insert_skipped_trade(ticker, today, alert, regime_record, "No ORB bar")
        results = [r for r in results if not (r.get("ticker") == ticker and r.get("action") == "pending_orb")]
        results.append({"ticker": ticker, "action": "skipped", "reason": "No ORB bar"})
        logger.warning(f"No ORB bar for {ticker} after {MAX_ORB_RETRIES} retries")
        await send_telegram_message(f"⏭️ *{ticker}* ORB skipped: no first bar after {MAX_ORB_RETRIES} retries")
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event("orb_no_bar", f"{ticker} — bar never available after {MAX_ORB_RETRIES} retries, trade skipped")
        except Exception:
            pass

    if results:
        entered = sum(1 for r in results if r.get("action") in ("auto_entered", "proposed"))
        skipped = sum(1 for r in results if r.get("action") in ("filtered", "skipped", "blocked"))
        logger.info(f"ORB monitor: {entered} entered, {skipped} skipped out of {len(alerts)} alerts")

    return results


# ── Day 2+ Position Management ──────────────────────────────────────────────


async def update_open_positions_live(today: date | None = None) -> list[dict]:
    """
    Update open live positions: SMA trail + Day 3-5 partial profit.
    Same logic as backtester/tracker.py update_open_positions(), but executes
    real orders via Alpaca.
    """
    if today is None:
        today = et_today()

    pool = await get_pool()
    async with pool.acquire() as conn:
        open_trades = await conn.fetch("""
            SELECT * FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0
            ORDER BY alert_date ASC
        """)

    if not open_trades:
        logger.info("No open live positions to update")
        return []

    logger.info(f"Updating {len(open_trades)} open live positions: {[dict(t)['ticker'] for t in open_trades]}")
    results = []

    for trade in open_trades:
        trade = dict(trade)
        ticker = trade["ticker"]
        alert_date = trade["alert_date"]
        remaining = trade["remaining_shares"]
        entry_price = trade["entry_price"]
        hard_stop = trade.get("hard_stop") or trade["stop_price"]
        partial_taken = trade.get("partial_taken", False)
        breakeven_active = trade.get("breakeven_active", False)
        exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")
        running_closes = trade.get("running_closes", [])
        if isinstance(running_closes, str):
            running_closes = json.loads(running_closes or "[]")

        if remaining <= 0 or today <= alert_date:
            continue

        # Fetch today's daily bar
        today_str = today.strftime("%Y-%m-%d")
        daily_bars = await get_index_history(ticker, today_str, today_str)

        if not daily_bars:
            logger.debug(f"No daily bar for {ticker} on {today}")
            results.append({"ticker": ticker, "action": "no_data"})
            continue

        bar = daily_bars[0]
        bar_low = bar.get("l", 0)
        bar_close = bar.get("c", 0)
        hold_days = (today - alert_date).days

        # Append today's close
        running_closes.append(float(bar_close))

        logger.info(
            f"Processing {ticker}: day={hold_days} close=${bar_close:.2f} low=${bar_low:.2f} "
            f"stop=${hard_stop:.2f} shares={remaining:.0f} partial={partial_taken}"
        )

        # 1. Hard stop check — Alpaca's stop order should catch this,
        #    but verify and update DB if it triggered
        if hard_stop and bar_low <= hard_stop:
            # Check if Alpaca already closed the position
            pos = await alpaca.get_position(ticker)
            if not pos or pos["qty"] <= 0:
                # Stop already triggered on Alpaca
                pnl = (hard_stop - entry_price) * remaining if entry_price else 0
                exits.append({
                    "time": datetime.combine(today, time(16, 0)).isoformat(),
                    "price": hard_stop,
                    "reason": "stop_hit",
                    "shares": remaining,
                    "pnl": pnl,
                })
                total_pnl = sum(e.get("pnl", 0) for e in exits)
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE mi_live_trades SET
                            status = 'closed', exits = $2::jsonb,
                            remaining_shares = 0, stop_price = NULL,
                            total_pnl = $3, hold_days = $4, closed_at = NOW(),
                            stop_order_id = NULL,
                            running_closes = $5::jsonb
                        WHERE id = $1
                    """, trade["id"], json.dumps(exits), total_pnl, hold_days,
                        json.dumps(running_closes))
                await send_telegram_message(
                    f"❌ *Stop hit:* {ticker} @${hard_stop:.2f}\n"
                    f"P&L: ${total_pnl:+,.2f} ({hold_days}d)"
                )
                results.append({"ticker": ticker, "action": "stopped_out", "pnl": total_pnl})
                continue
            # If Alpaca still has position, stop didn't trigger yet — let it ride

        # 2. Compute SMAs
        active_sma = None
        if len(running_closes) >= 20:
            sma_10 = sum(running_closes[-10:]) / 10
            sma_20 = sum(running_closes[-20:]) / 20
            active_sma = sma_10 if sma_10 > sma_20 else sma_20
        elif len(running_closes) >= 10:
            active_sma = sum(running_closes[-10:]) / 10

        # 3. Partial profit on Day 3-5
        if hold_days >= 3 and not partial_taken and entry_price:
            take_partial = False
            if hold_days <= 4 and bar_close > entry_price:
                take_partial = True
            elif hold_days >= 5:
                take_partial = True

            if take_partial:
                partial_shares = int(remaining) // 3
                await execute_partial_exit(trade["id"], partial_shares)
                partial_taken = True
                breakeven_active = True
                remaining -= partial_shares

        # 4. Effective stop = max(hard_stop, active_sma, breakeven)
        effective_stop = hard_stop or 0
        if active_sma and active_sma > effective_stop:
            effective_stop = active_sma
        if breakeven_active and entry_price and entry_price > effective_stop:
            effective_stop = entry_price

        logger.info(
            f"{ticker}: effective_stop=${effective_stop:.2f} "
            f"(hard=${hard_stop or 0:.2f} sma={active_sma or 0:.2f} be={'yes' if breakeven_active else 'no'})"
        )

        # 5. SMA trail check (close-based)
        if bar_close < effective_stop and remaining > 0:
            await execute_full_exit(trade["id"], "sma_trail_stop")
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_trades SET
                        hold_days = $2, running_closes = $3::jsonb
                    WHERE id = $1
                """, trade["id"], hold_days, json.dumps(running_closes))
            results.append({"ticker": ticker, "action": "sma_stopped", "hold_days": hold_days})
            continue

        # 6. Still open — update stop on Alpaca if it changed
        current_stop = trade["stop_price"] or 0
        if effective_stop > current_stop + 0.01 and remaining > 0:
            await update_stop(trade["id"], round(effective_stop, 2))

        # Update DB state
        total_pnl = sum(e.get("pnl", 0) for e in exits)
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    stop_price = $2, hold_days = $3, total_pnl = $4,
                    partial_taken = $5, breakeven_active = $6,
                    running_closes = $7::jsonb,
                    remaining_shares = $8
                WHERE id = $1
            """, trade["id"], effective_stop, hold_days, total_pnl,
                partial_taken, breakeven_active,
                json.dumps(running_closes), remaining)

        results.append({
            "ticker": ticker, "action": "updated",
            "effective_stop": effective_stop, "hold_days": hold_days,
        })

    return results


# ── Morning Stop Refresh ─────────────────────────────────────────────────────


async def morning_stop_refresh() -> int:
    """
    At 9:35 AM, ensure stop orders are active for all Day 2+ positions.
    Alpaca DAY stops expire overnight — re-place them as GTC.
    Returns count of stops refreshed.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        trades = await conn.fetch("""
            SELECT id, ticker, remaining_shares, stop_price, stop_order_id
            FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0
        """)

    refreshed = 0
    for trade in trades:
        ticker = trade["ticker"]
        stop_price = trade["stop_price"]

        if not stop_price or not trade["remaining_shares"]:
            continue

        # Check if existing stop order is still active
        if trade["stop_order_id"]:
            order = await alpaca.get_order(trade["stop_order_id"])
            if order and order["status"] in ("new", "accepted", "held"):
                logger.debug(f"Stop still active for {ticker}")
                continue

        # Re-place stop
        success = await update_stop(trade["id"], stop_price)
        if success:
            refreshed += 1
            logger.info(f"Morning stop refreshed: {ticker} @${stop_price:.2f}")

    if refreshed:
        await send_telegram_message(f"🔄 Morning: refreshed {refreshed} stop order(s)")
    return refreshed


# ── Daily Summary ────────────────────────────────────────────────────────────


async def send_live_trade_summary() -> None:
    """Send a daily Telegram summary of live trading activity. Called after position update."""
    pool = await get_pool()
    today = et_today()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status NOT IN ('skipped','cancelled','order_failed')) as total,
                COUNT(*) FILTER (WHERE status = 'filled' AND remaining_shares > 0) as open_count,
                COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0) as winners,
                COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl <= 0) as losers,
                COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) as realized_pnl
            FROM mi_live_trades
        """)
        open_trades = await conn.fetch("""
            SELECT ticker, entry_price, remaining_shares, stop_price, hold_days,
                   partial_taken, total_pnl
            FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0
            ORDER BY alert_date ASC
        """)
        todays_closes = await conn.fetch("""
            SELECT ticker, total_pnl, hold_days
            FROM mi_live_trades
            WHERE status = 'closed' AND closed_at::date = $1
        """, today)
        todays_entries = await conn.fetch("""
            SELECT ticker, entry_price, entry_shares
            FROM mi_live_trades
            WHERE alert_date = $1 AND status IN ('filled', 'order_placed')
        """, today)
        todays_skipped = await conn.fetch("""
            SELECT ticker, skip_reason
            FROM mi_live_trades
            WHERE alert_date = $1 AND status IN ('skipped', 'cancelled', 'order_failed')
        """, today)

    # Build message
    lines = ["📊 *Live Trade Update (Alpaca — Paper)*\n"]

    # Today's activity
    if todays_entries:
        lines.append("*Entered today:*")
        for t in todays_entries:
            lines.append(f"  ▶ {t['ticker']} @${t['entry_price']:.2f} × {t['entry_shares']:.0f}")
        lines.append("")

    if todays_skipped:
        lines.append("*Filtered today:*")
        for t in todays_skipped:
            lines.append(f"  ⊘ {t['ticker']}: {t['skip_reason']}")
        lines.append("")

    if todays_closes:
        lines.append("*Closed today:*")
        for t in todays_closes:
            emoji = "✅" if t["total_pnl"] > 0 else "❌"
            lines.append(f"  {emoji} {t['ticker']} ${t['total_pnl']:+,.2f} ({t['hold_days']}d)")
        lines.append("")

    # Open positions
    if open_trades:
        # Fetch current prices from Alpaca
        lines.append(f"*Open positions ({len(open_trades)}):*")
        for t in open_trades:
            ticker = t["ticker"]
            try:
                pos = await alpaca.get_position(ticker)
                current = pos["current_price"] if pos else None
                unrealized = pos["unrealized_pl"] if pos else 0
            except Exception as e:
                logger.warning(f"Could not get position for {ticker} in summary: {e}")
                current = None
                unrealized = 0

            entry_str = f"${t['entry_price']:.2f}" if t["entry_price"] else "?"
            current_str = f"${current:.2f}" if current else "?"
            pnl_emoji = "🟢" if unrealized > 0 else "🔴" if unrealized < 0 else "⚪"
            partial = " ½" if t["partial_taken"] else ""

            lines.append(
                f"  {pnl_emoji} {ticker} {entry_str}→{current_str} "
                f"${unrealized:+,.0f} · {t['hold_days']}d{partial}"
            )
        lines.append("")

    # Running totals
    closed_count = (stats["winners"] or 0) + (stats["losers"] or 0)
    win_rate = (stats["winners"] / closed_count * 100) if closed_count > 0 else 0

    try:
        account = await alpaca.get_account()
        equity = account["equity"]
        lines.append(f"*Account:* ${equity:,.0f}")
    except Exception as e:
        logger.warning(f"Could not get account equity for summary: {e}")

    if closed_count > 0:
        lines.append(
            f"*Record:* {stats['winners']}W/{stats['losers']}L "
            f"({win_rate:.0f}%) · ${float(stats['realized_pnl']):+,.2f}"
        )
    elif stats["total"]:
        lines.append(f"*Trades:* {stats['total']} (no closes yet)")

    # Send if there's any activity today or open positions
    has_activity = todays_entries or todays_closes or todays_skipped or open_trades
    if has_activity or (stats["total"] and stats["total"] > 0):
        await send_telegram_message("\n".join(lines))


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _insert_skipped_trade(
    ticker: str,
    today: date,
    alert: dict,
    regime_record: dict | None,
    skip_reason: str,
) -> None:
    """Insert a skipped live trade record."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_live_trades
                (ticker, alert_date, ep_score, catalyst_quality, gap_pct,
                 regime, status, skip_reason)
            VALUES ($1, $2, $3, $4, $5, $6, 'skipped', $7)
            ON CONFLICT (ticker, alert_date) DO NOTHING
        """,
            ticker, today, alert["ep_score"],
            alert.get("catalyst_quality"), alert.get("gap_pct"),
            regime_record.get("regime") if regime_record else None,
            skip_reason,
        )


# ── 9M EP Day 2 ORB ──────────────────────────────────────────────────────────


async def submit_9m_day2_trade(sugar_baby: dict) -> dict:
    """
    Place a Day 2 ORB entry for a confirmed 9M sugar baby.

    Called at 9:31 AM ET. Shares the same 4-position cap / daily-loss safeguards
    as MAGNA53 trades via _check_safeguards().

    sugar_baby: row from get_pending_9m_sugar_babies() — must have ticker, alert_date, low_price.
    Returns status dict for logging.
    """
    from agents.market_intelligence.broker.order_manager import (
        prepare_9m_day2_orb_order,
        submit_entry,
    )
    from agents.market_intelligence.db import (
        get_latest_regime,
        update_9m_sugar_baby_status,
    )

    ticker = sugar_baby["ticker"]
    alert_date = sugar_baby["alert_date"]
    today = et_today()

    ok, sg_reason = await _check_safeguards()
    if not ok:
        logger.info(f"9M Day2 {ticker}: blocked by safeguard — {sg_reason}")
        await update_9m_sugar_baby_status(ticker, alert_date, "skipped")
        return {"ticker": ticker, "action": "blocked", "reason": sg_reason}

    orb_bar = await alpaca.get_first_bar(ticker, today)
    if not orb_bar:
        logger.warning(f"9M Day2 {ticker}: no ORB bar available")
        await update_9m_sugar_baby_status(ticker, alert_date, "skipped")
        return {"ticker": ticker, "action": "skipped", "reason": "no_orb_bar"}

    regime_record = await get_latest_regime()
    order_spec = await prepare_9m_day2_orb_order(sugar_baby, orb_bar, regime_record)

    if not order_spec:
        logger.info(f"9M Day2 {ticker}: order spec failed (stop too wide or invalid)")
        await update_9m_sugar_baby_status(ticker, alert_date, "skipped")
        await send_telegram_message(
            f"⏭️ *9M Day2 {ticker}* skipped: stop distance invalid"
        )
        return {"ticker": ticker, "action": "skipped", "reason": "order_spec_failed"}

    pool = await get_pool()
    async with pool.acquire() as conn:
        trade_id = await conn.fetchval("""
            INSERT INTO mi_live_trades
                (ticker, alert_date, ep_score, catalyst_quality, gap_pct, regime,
                 status, orb_high, orb_low, atr_14,
                 entry_price, entry_shares, stop_price, hard_stop,
                 position_size, risk_dollars, proposed_at)
            VALUES ($1,$2,0,'9m_volume',$3,$4,'pending_confirmation',$5,$6,NULL,
                    $7,$8,$9,$9,$10,$11,NOW())
            ON CONFLICT (ticker, alert_date) DO NOTHING
            RETURNING id
        """,
            ticker, today,
            sugar_baby.get("gap_pct"),
            regime_record.get("regime") if regime_record else None,
            order_spec["orb_high"], order_spec["orb_low"],
            order_spec["entry_price"], float(order_spec["shares"]),
            order_spec["stop_loss_price"],
            order_spec["position_size"], order_spec["risk_dollars"],
        )

    if not trade_id:
        logger.debug(f"9M Day2 {ticker}: trade row already exists, skipping")
        await update_9m_sugar_baby_status(ticker, alert_date, "skipped")
        return {"ticker": ticker, "action": "skipped", "reason": "already_exists"}

    is_paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    if is_paper:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE mi_live_trades SET status = 'confirmed', confirmed_at = NOW() WHERE id = $1",
                trade_id,
            )
        order = await submit_entry(trade_id)
        if order:
            await update_9m_sugar_baby_status(ticker, alert_date, "traded")
            await send_telegram_message(
                f"🍬 *9M Day2 entered:* {ticker}\n"
                f"Entry: ${order_spec['entry_price']:.2f} | "
                f"Stop: ${order_spec['stop_loss_price']:.2f} (prev day low)\n"
                f"Shares: {order_spec['shares']} | Risk: ${order_spec['risk_dollars']:.0f}"
            )
            return {"ticker": ticker, "action": "auto_entered", "trade_id": trade_id}
        else:
            await update_9m_sugar_baby_status(ticker, alert_date, "skipped")
            await send_telegram_message(
                f"⚠️ *9M Day2 auto-enter failed:* {ticker} (trade_id={trade_id})"
            )
            return {"ticker": ticker, "action": "auto_enter_failed"}
    else:
        # Live mode: propose for manual confirmation (same flow as MAGNA53)
        alert_stub = {
            "ep_score": 0, "catalyst_quality": "9m_volume",
            "gap_pct": sugar_baby.get("gap_pct"), "ticker": ticker,
        }
        sent = await send_trade_proposal(alert_stub, order_spec, trade_id)
        if sent:
            await update_9m_sugar_baby_status(ticker, alert_date, "traded")
            return {"ticker": ticker, "action": "proposed", "trade_id": trade_id}
        else:
            return {"ticker": ticker, "action": "proposal_send_failed"}
