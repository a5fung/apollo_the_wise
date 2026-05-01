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
from datetime import date, datetime, time, timedelta, timezone

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.entry_pipeline import (
    ACTION_AUTO_ENTERED,
    ACTION_AUTO_ENTER_FAILED,
    ACTION_BLOCKED,
    ACTION_PROPOSAL_SEND_FAILED,
    ACTION_PROPOSED,
    ACTION_SKIPPED,
    submit_trade_entry,
)
from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step
from agents.market_intelligence.broker.order_manager import (
    prepare_orb_order,
    execute_partial_exit,
    execute_full_exit,
    update_stop,
)
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_CIRCUIT_BREAKER,
    BLOCK_DAILY_LOSS,
    BLOCK_MAX_POSITIONS,
    SETUP_ACCOUNT_FETCH_FAILED,
    humanize,
)
from agents.market_intelligence.backtester.filters import check_filters, compute_atr_14
from agents.market_intelligence.collector import et_today, get_index_history
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.constants import (
    LIVE_TRADING_ENABLED,
    MAX_CONCURRENT_LIVE_POSITIONS,
    DAILY_LOSS_LIMIT_PCT,
    CIRCUIT_BREAKER_CONSEC_LOSSES,
    CIRCUIT_BREAKER_COOLDOWN_DAYS,
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
            return False, f"{BLOCK_MAX_POSITIONS}: {open_count}/{MAX_CONCURRENT_LIVE_POSITIONS}"

        # Daily loss limit
        try:
            account = await alpaca.get_account()
            equity = account["equity"]
        except Exception as e:
            logger.error(f"Safeguard: cannot get account equity: {e}")
            return False, f"{SETUP_ACCOUNT_FETCH_FAILED}: {e}"

        today = et_today()
        today_losses = await conn.fetchval("""
            SELECT COALESCE(SUM(total_pnl), 0)
            FROM mi_live_trades
            WHERE alert_date = $1 AND status = 'closed' AND total_pnl < 0
        """, today)
        daily_limit = equity * DAILY_LOSS_LIMIT_PCT
        if abs(today_losses) >= daily_limit:
            logger.info(f"Safeguard blocked: daily loss limit (${today_losses:+,.0f} >= ${daily_limit:.0f})")
            return False, f"{BLOCK_DAILY_LOSS}: ${today_losses:+,.0f} >= ${daily_limit:.0f}"

        # Circuit breaker: N consecutive losses, then auto-release after cooldown.
        # Time-based escape valve mirrors backtester semantics — without it, once N
        # losses close, no new entries can ever fire (the trailing-N window is
        # permanently all-losses until a winner ages into it, which can't happen
        # if entries are blocked).
        recent_closed = await conn.fetch("""
            SELECT total_pnl, closed_at FROM mi_live_trades
            WHERE status = 'closed' AND total_pnl IS NOT NULL
            ORDER BY closed_at DESC LIMIT $1
        """, CIRCUIT_BREAKER_CONSEC_LOSSES)

        if len(recent_closed) >= CIRCUIT_BREAKER_CONSEC_LOSSES:
            all_losses = all(r["total_pnl"] <= 0 for r in recent_closed)
            if all_losses:
                latest_loss_at = recent_closed[0]["closed_at"]
                cooldown_until = latest_loss_at + timedelta(days=CIRCUIT_BREAKER_COOLDOWN_DAYS)
                now = datetime.now(timezone.utc)
                if now < cooldown_until:
                    logger.info(
                        f"Safeguard blocked: circuit breaker "
                        f"({CIRCUIT_BREAKER_CONSEC_LOSSES} consecutive losses, "
                        f"cooldown until {cooldown_until.isoformat()})"
                    )
                    return False, (
                        f"{BLOCK_CIRCUIT_BREAKER}: cooldown until "
                        f"{cooldown_until.isoformat()}"
                    )

    return True, None


# ── New Alerts (Day 1) ───────────────────────────────────────────────────────


async def process_new_alerts_live(today: date | None = None, trigger: str = "cron") -> list[dict]:
    """
    For each HIGH EP alert today, run the unified entry pipeline.

    Pre-pipeline work (MAGNA53-specific): check_filters (ADV/ATR%) and
    compute ATR14. Pipeline then handles: duplicate check, safeguards,
    bar fetch with retry, fade guard, spec build, DB insert, Alpaca submit
    (paper auto-confirm or live proposal), and terminal-state Telegram on
    every failure branch.

    trigger: "bar_stream" | "cron_9_31" | "cron_fallback" | "cron"
    """
    if today is None:
        today = et_today()

    if not LIVE_TRADING_ENABLED:
        logger.info("Live trading disabled, skipping")
        return []

    from agents.market_intelligence.db import log_audit_event

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

    logger.info(f"ORB monitor [{trigger}]: {len(alerts)} HIGH EP alerts: {[a['ticker'] for a in alerts]}")
    try:
        await log_audit_event("orb_triggered", f"[{trigger}] {len(alerts)} alerts: {[a['ticker'] for a in alerts]}")
    except Exception:
        pass

    async with pool.acquire() as conn:
        regime_record = await conn.fetchrow(
            "SELECT * FROM mi_market_regime WHERE regime_date <= $1 ORDER BY regime_date DESC LIMIT 1",
            today,
        )
    regime_record = dict(regime_record) if regime_record else None

    # Per-alert concurrency. Bar-fetch retry can block up to 3 × 60s on a
    # single ticker; serial would stack past the 5-min cron interval on
    # any morning where multiple alerts miss the first bar. Semaphore
    # caps Alpaca-bound work to keep us under per-account rate limits.
    sem = asyncio.Semaphore(5)

    async def _process_alert(alert: dict) -> dict | None:
        ticker = alert["ticker"]
        async with sem:
            async with pool.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM mi_live_trades WHERE ticker = $1 AND alert_date = $2)",
                    ticker, today,
                )
            if exists:
                logger.debug(f"Live trade already exists for {ticker} on {today}")
                return None

            passed, skip_reason = await check_filters(ticker, today)
            if not passed:
                await _insert_skipped_trade(
                    ticker, today, alert, regime_record, skip_reason,
                    signal_type="magna53",
                )
                logger.info(f"ORB filter [{trigger}]: {ticker} skipped — {skip_reason}")
                try:
                    await log_audit_event("orb_filtered", f"{ticker} [{trigger}] — {skip_reason}")
                except Exception:
                    pass
                await send_telegram_message(f"⏭️ *{ticker}* ORB skipped — {humanize(skip_reason)}")
                return {"ticker": ticker, "action": "filtered", "reason": skip_reason}

            atr_14, _atr_pct = await compute_atr_14(ticker, today)

            async def _magna_spec_builder(
                alert_ctx: dict,
                orb_bar: dict,
                regime: dict | None,
                _atr=atr_14,
            ) -> tuple[dict | None, str | None]:
                return await prepare_orb_order(alert_ctx, orb_bar, _atr or 0, regime)

            return await submit_trade_entry(
                alert_context=alert,
                spec_builder=_magna_spec_builder,
                regime_record=regime_record,
                strategy_label="ORB",
                signal_type="magna53",
                today=today,
                atr_14=atr_14,
                success_title="EP entered",
                # MAGNA53 HIGH: Sonnet+Perplexity validation + ATR stop
                # width + 10:00 ET cleanup already cover dead-cat fills.
                # Midpoint check was over-strict; drop it.
                fade_midpoint_ratio=None,
            )

    raw = await asyncio.gather(
        *(_process_alert(a) for a in alerts), return_exceptions=True,
    )
    results: list[dict] = []
    for alert, r in zip(alerts, raw):
        if r is None:
            continue
        if isinstance(r, BaseException):
            tkr = alert["ticker"]
            logger.exception(
                f"ORB monitor [{trigger}] {tkr}: per-alert task raised — {r}"
            )
            # Always write the crash to the audit log first — this is the
            # durable record. If Telegram is also down we'd otherwise lose all
            # trace of the failure.
            try:
                await log_audit_event(
                    "orb_pipeline_crash",
                    f"{tkr} [{trigger}] — {type(r).__name__}: {r}",
                )
            except Exception:
                logger.exception(f"ORB crash audit_log write also failed for {tkr}")
            try:
                await send_telegram_message(
                    f"🚨 *{tkr}* ORB pipeline crashed — {type(r).__name__}: {r}"
                )
            except Exception:
                logger.exception(
                    f"ORB crash Telegram alert ALSO failed for {tkr} — "
                    f"check audit log event 'orb_pipeline_crash'"
                )
            results.append({"ticker": tkr, "action": "crashed", "reason": str(r)})
            continue
        results.append(r)

    entered = sum(1 for r in results if r.get("action") in (ACTION_AUTO_ENTERED, ACTION_PROPOSED))
    skipped = sum(1 for r in results if r.get("action") in ("filtered", ACTION_SKIPPED, ACTION_BLOCKED))
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
        running_closes_in = trade.get("running_closes", [])
        if isinstance(running_closes_in, str):
            running_closes_in = json.loads(running_closes_in or "[]")
        exits_in = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")
        hard_stop = trade.get("hard_stop") or trade["stop_price"]

        if trade["remaining_shares"] <= 0 or today <= alert_date:
            continue

        today_str = today.strftime("%Y-%m-%d")
        daily_bars = await get_index_history(ticker, today_str, today_str)
        if not daily_bars:
            logger.debug(f"No daily bar for {ticker} on {today}")
            results.append({"ticker": ticker, "action": "no_data"})
            continue

        state = {
            "alert_date": alert_date,
            "remaining_shares": trade["remaining_shares"],
            "entry_price": trade["entry_price"],
            "hard_stop": hard_stop,
            "partial_taken": trade.get("partial_taken", False),
            "breakeven_active": trade.get("breakeven_active", False),
            "exits": exits_in,
            "running_closes": running_closes_in,
        }

        step = apply_daily_exit_step(state, daily_bars[0], today,
                                     integer_partial_shares=True)

        logger.info(
            f"Processing {ticker}: day={step.hold_days} close=${step.bar_close:.2f} "
            f"low=${step.bar_low:.2f} stop=${hard_stop:.2f} "
            f"shares={trade['remaining_shares']:.0f} partial={state['partial_taken']}"
        )

        # 1. Hard-stop verification: re-call without hard_stop if Alpaca says
        # position is still open (stop didn't actually trigger yet).
        if step.action == "stopped_out":
            pos = await alpaca.get_position(ticker)
            if not pos or pos["qty"] <= 0:
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE mi_live_trades SET
                            status = 'closed', exits = $2::jsonb,
                            remaining_shares = 0, stop_price = NULL,
                            total_pnl = $3, hold_days = $4, closed_at = NOW(),
                            stop_order_id = NULL,
                            running_closes = $5::jsonb
                        WHERE id = $1
                    """, trade["id"], json.dumps(step.new_exits),
                        step.new_total_pnl, step.hold_days,
                        json.dumps(step.new_running_closes))
                await send_telegram_message(
                    f"❌ *Stop hit:* {ticker} @${step.close_price:.2f}\n"
                    f"P&L: ${step.new_total_pnl:+,.2f} ({step.hold_days}d)"
                )
                results.append({"ticker": ticker, "action": "stopped_out", "pnl": step.new_total_pnl})
                continue
            # Alpaca still holds — re-run skipping the close branch.
            # hard_stop stays in state so effective_stop still floors at it.
            step = apply_daily_exit_step(state, daily_bars[0], today,
                                         integer_partial_shares=True,
                                         skip_hard_stop_close=True)

        # 2. Partial profit branch — execute via helper, fall through on failure
        if step.partial_fired:
            partial_ok = await execute_partial_exit(trade["id"], int(step.partial_shares))
            if not partial_ok:
                # Helper failed (e.g. cancel-stop blocked). Re-run skipping
                # partial decision so the rest of the ladder runs against
                # original remaining; partial_taken/breakeven_active stay
                # at their pre-step values. Next day retries.
                step = apply_daily_exit_step(
                    state, daily_bars[0], today,
                    integer_partial_shares=True,
                    skip_partial_decision=True,
                )

        # 3. SMA trail close
        if step.action == "sma_stopped":
            await execute_full_exit(trade["id"], "sma_trail_stop")
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_trades SET
                        hold_days = $2, running_closes = $3::jsonb
                    WHERE id = $1
                """, trade["id"], step.hold_days,
                    json.dumps(step.new_running_closes))
            results.append({"ticker": ticker, "action": "sma_stopped", "hold_days": step.hold_days})
            continue

        # 4. Still open — update Alpaca stop if effective_stop rose
        current_stop = trade["stop_price"] or 0
        if step.effective_stop > current_stop + 0.01 and step.new_remaining > 0:
            await update_stop(trade["id"], round(step.effective_stop, 2))

        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    stop_price = $2, hold_days = $3, total_pnl = $4,
                    partial_taken = $5, breakeven_active = $6,
                    running_closes = $7::jsonb,
                    remaining_shares = $8
                WHERE id = $1
            """, trade["id"], step.effective_stop, step.hold_days,
                step.new_total_pnl, step.new_partial_taken,
                step.new_breakeven_active,
                json.dumps(step.new_running_closes), step.new_remaining)

        logger.info(
            f"{ticker}: effective_stop=${step.effective_stop:.2f} "
            f"(hard=${hard_stop or 0:.2f} sma={step.active_sma or 0:.2f} "
            f"be={'yes' if step.new_breakeven_active else 'no'})"
        )

        results.append({
            "ticker": ticker, "action": "updated",
            "effective_stop": step.effective_stop, "hold_days": step.hold_days,
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
    refreshed_tickers: list[str] = []
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
            refreshed_tickers.append(ticker)
            logger.info(f"Morning stop refreshed: {ticker} @${stop_price:.2f}")

    if refreshed:
        await send_telegram_message(
            f"🔄 Morning: refreshed {refreshed} stop order(s) — {', '.join(refreshed_tickers)}"
        )
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
            WHERE status = 'closed'
              AND (closed_at AT TIME ZONE 'America/New_York')::date = $1
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
            lines.append(f"  ⊘ {t['ticker']}: {humanize(t['skip_reason'])}")
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
    alert: dict | None,
    regime_record: dict | None,
    skip_reason: str,
    signal_type: str | None = None,
) -> None:
    """Insert a skipped live trade record.

    alert / regime_record may be None — the bar-stream timeout path cannot
    hydrate them without a DB join during a stuck lock. The invariant is that
    (ticker, alert_date, status='skipped', skip_reason) lands in mi_live_trades;
    score/catalyst/gap/regime can be LEFT-JOINed from mi_ep_alerts by /why.
    """
    pool = await get_pool()
    ep_score = alert.get("ep_score") if alert else None
    catalyst_quality = alert.get("catalyst_quality") if alert else None
    gap_pct = alert.get("gap_pct") if alert else None
    regime = regime_record.get("regime") if regime_record else None
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_live_trades
                (ticker, alert_date, ep_score, catalyst_quality, gap_pct,
                 regime, status, skip_reason, signal_type)
            VALUES ($1, $2, $3, $4, $5, $6, 'skipped', $7, $8)
            ON CONFLICT (ticker, alert_date) DO NOTHING
        """,
            ticker, today, ep_score, catalyst_quality, gap_pct, regime,
            skip_reason, signal_type,
        )


# ── 9M EP Day 2 ORB ──────────────────────────────────────────────────────────


async def submit_9m_day2_trade(sugar_baby: dict) -> dict:
    """
    Place a Day 2 ORB entry for a confirmed 9M sugar baby via the unified
    trade-entry pipeline.

    Called at 9:31 AM ET. Shares the same 4-position cap / daily-loss
    safeguards, bar-fetch retry, fade guard, and terminal-state Telegram
    contract as MAGNA53 trades (single code path — see entry_pipeline.py).

    sugar_baby: row from get_pending_9m_sugar_babies() — must have ticker,
    alert_date, low_price. Returns status dict for logging.
    """
    from agents.market_intelligence.broker.order_manager import prepare_9m_day2_orb_order
    from agents.market_intelligence.db import get_latest_regime, update_9m_sugar_baby_status

    ticker = sugar_baby["ticker"]
    alert_date = sugar_baby["alert_date"]
    today = et_today()

    regime_record = await get_latest_regime()

    # Pipeline spec_builder signature is (alert_ctx, orb_bar, regime) — the
    # sugar_baby row IS the alert_context, so we just pass it through.
    async def _ninem_spec_builder(
        alert_ctx: dict, orb_bar: dict, regime: dict | None,
    ) -> tuple[dict | None, str | None]:
        return await prepare_9m_day2_orb_order(alert_ctx, orb_bar, regime)

    # on_skip fires for every terminal skip (safeguard, no-bar, fade, spec fail).
    # Sugar baby row must mirror the skip so /9m doesn't show it as "pending" forever.
    async def _on_skip(_reason: str) -> None:
        await update_9m_sugar_baby_status(ticker, alert_date, "skipped")

    # alert_context must include the keys prepare_9m_day2_orb_order needs
    # (low_price etc.) plus the common EP fields the pipeline passes to DB insert.
    alert_context = {
        **sugar_baby,
        "ticker": ticker,
        "ep_score": 0,
        "catalyst_quality": "9m_volume",
        "gap_pct": sugar_baby.get("gap_pct"),
    }

    result = await submit_trade_entry(
        alert_context=alert_context,
        spec_builder=_ninem_spec_builder,
        regime_record=regime_record,
        strategy_label="9M Day2",
        signal_type="9m_day2",
        today=today,
        atr_14=None,
        success_icon="🍬",
        success_title="9M Day2 entered",
        stop_label="Stop (prev day low)",
        on_skip=_on_skip,
        # 9M is pure quant (no LLM validation); keep some fade protection
        # but loose — only skip on real weakness (lower 25% of ORB).
        fade_midpoint_ratio=0.25,
    )

    # Mirror pipeline outcome onto sugar baby row so /9m reflects reality.
    # Successful entry → traded. Post-insert submit/proposal failures bypass
    # _on_skip (they happen after DB insert) so mark skipped explicitly here.
    action = result.get("action")
    status_update: str | None = None
    if action in (ACTION_AUTO_ENTERED, ACTION_PROPOSED):
        status_update = "traded"
    elif action in (ACTION_AUTO_ENTER_FAILED, ACTION_PROPOSAL_SEND_FAILED):
        status_update = "skipped"

    if status_update:
        try:
            await update_9m_sugar_baby_status(ticker, alert_date, status_update)
        except Exception as e:
            logger.warning(
                f"9M Day2 {ticker}: sugar baby status update to '{status_update}' failed — {e}"
            )

    return result
