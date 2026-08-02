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
# #490: MAGNA53's OWN gap criterion, imported here so the opt-in at the call site names the
# strategy whose rule it is. Deliberately NOT imported inside entry_pipeline — that file is the
# SHARED funnel for MAGNA53 and 9M Day 2, and baking one strategy's constant into it is exactly
# how the 10%-floor-applied-to-a-3%-strategy defect happened.
from agents.market_intelligence.ep_detector import MIN_GAP_PCT as _MAGNA53_MIN_GAP_PCT
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
    finalize_stop_fill,
    update_stop,
)
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_CIRCUIT_BREAKER,
    BLOCK_DAILY_LOSS,
    BLOCK_MAX_POSITIONS,
    BLOCK_TRADING_PAUSED,
    cap_block_reason,
    strategy_cap_block_reason,
    INFRA_HALT_STATE_UNREADABLE,
    SETUP_ACCOUNT_FETCH_FAILED,
    WINDOW_DUPLICATE,
    humanize,
)
from agents.market_intelligence.backtester.filters import check_filters, compute_atr_14
from agents.market_intelligence.collector import et_today, get_index_history
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.db import get_pool, get_manual_halt_state, _coerce_date, OPEN_POSITION_STATUSES
from agents.market_intelligence.constants import (
    LIVE_TRADING_ENABLED,
    MAX_CONCURRENT_LIVE_POSITIONS,
    DAILY_LOSS_LIMIT_PCT,
    CIRCUIT_BREAKER_CONSEC_LOSSES,
    CIRCUIT_BREAKER_COOLDOWN_DAYS,
    current_account_mode,
    mode_prefix,
    resolve_strategy_mode_nonfatal,
)

logger = logging.getLogger(__name__)


# ── Safeguards ───────────────────────────────────────────────────────────────


async def count_open_positions(
    conn, account_mode: str, signal_type: str | None = None,
) -> int:
    """Open-position count for the cap gates — the single SQL source of truth.

    Shared by `_check_safeguards` (the STEP-2 cheap early gate) AND
    `entry_pipeline.submit_trade_entry` STEP 6 (the authoritative insert-time
    recount under the per-mode advisory cap lock, #461) so the two reads can
    never drift. Counting vocabulary = `db.OPEN_POSITION_STATUSES` (inert
    `pending_confirmation` proposals excluded, #436 fork B). Per-mode isolated
    (#66); pass `signal_type` for the per-strategy (#65) variant.
    """
    if signal_type is None:
        return await conn.fetchval("""
            SELECT COUNT(*) FROM mi_live_trades
            WHERE status = ANY($2) AND account_mode = $1
        """, account_mode, list(OPEN_POSITION_STATUSES))
    return await conn.fetchval("""
        SELECT COUNT(*) FROM mi_live_trades
        WHERE status = ANY($3) AND account_mode = $1 AND signal_type = $2
    """, account_mode, signal_type, list(OPEN_POSITION_STATUSES))


async def _check_safeguards(
    account_mode: str | None = None,
    signal_type: str | None = None,
) -> tuple[bool, str | None, float]:
    """
    Check all safety gates before proposing a new trade.
    Returns (ok, reason, sizing_multiplier).
      - ok=True, reason=None, multiplier in [0.0, 1.0]: allow with possibly-reduced sizing
      - ok=False, reason=<block:*>, multiplier=0.0: blocked

    Dual-account aware (#66, 2026-05-10): when account_mode is passed,
    all mi_live_trades queries filter by AND account_mode = $1, and
    alpaca.get_account routes to the per-mode TradingClient. Per-mode
    isolated safeguards: paper at-cap doesn't constrain live and vice
    versa. None falls back to current_account_mode() for legacy callers.

    Per-strategy cap (#65): when signal_type is passed AND the strategy
    row has max_concurrent_positions set, enforces a per-strategy slot
    budget within the per-mode global envelope. NULL on the strategy row
    means "share the global cap" — no per-strategy gate.

    Tiered drawdown breaker (2026-05-18): active phase returns the tier's
    sizing multiplier (1.0 for OK/WATCH, 0.5 for REDUCE, 0.0 for BLOCK).
    Shadow phase always returns 1.0. Composes with mi_strategies
    .position_size_multiplier in entry_pipeline.
    """
    if not LIVE_TRADING_ENABLED:
        logger.debug("Safeguard: live trading disabled")
        return False, "live_trading_disabled", 0.0

    if account_mode is None:
        account_mode = current_account_mode()

    # Manual real-money halt (#345) — the operator's one-command `/pause` kill switch.
    # Highest-priority gate: a manual halt overrides every other safeguard. LIVE path
    # only (paper/shadow telemetry keeps running). DB-backed (mi_safeguard_state), read
    # per-entry so `/pause` takes effect on the NEXT entry with no redeploy. Fail-SAFE:
    # an unreadable halt state blocks the live path (capital protection) under a DISTINCT
    # reason so the operator is never told "you paused" when a DB error caused it.
    if account_mode == "live":
        halt = await get_manual_halt_state()
        if halt == "on":
            logger.info(f"Safeguard [{account_mode}] blocked: manual trading halt (/pause)")
            return False, BLOCK_TRADING_PAUSED, 0.0
        if halt == "unreadable":
            logger.error(
                f"Safeguard [{account_mode}] blocked: halt-state unreadable → failing safe"
            )
            return False, INFRA_HALT_STATE_UNREADABLE, 0.0

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Max concurrent positions — per mode (paper noise doesn't
        # constrain live; live noise doesn't constrain paper). This read is
        # the CHEAP EARLY gate; the authoritative recount happens at insert
        # time inside entry_pipeline's per-mode-locked transaction (#461),
        # via the SAME count_open_positions helper.
        open_count = await count_open_positions(conn, account_mode)
        if open_count >= MAX_CONCURRENT_LIVE_POSITIONS:
            logger.info(
                f"Safeguard [{account_mode}] blocked: max positions "
                f"({open_count}/{MAX_CONCURRENT_LIVE_POSITIONS})"
            )
            # #484: built by the SHARED helper — this string is string-MATCHED by
            # the #197 CAP+1 alert, and it used to be hand-copied into
            # entry_pipeline's STEP-6 recount too.
            return False, cap_block_reason(
                open_count, MAX_CONCURRENT_LIVE_POSITIONS, account_mode,
            ), 0.0

        # Per-strategy concurrent-position cap (#65). Enforced WITHIN the
        # per-mode global envelope above. NULL on mi_strategies = share
        # global cap, no per-strategy gate.
        if signal_type:
            strat_cap = await conn.fetchval(
                "SELECT max_concurrent_positions FROM mi_strategies WHERE strategy_id = $1",
                signal_type,
            )
            if strat_cap is not None:
                strat_open = await count_open_positions(
                    conn, account_mode, signal_type,
                )
                if strat_open >= int(strat_cap):
                    logger.info(
                        f"Safeguard [{account_mode}/{signal_type}] blocked: "
                        f"per-strategy cap ({strat_open}/{strat_cap})"
                    )
                    return False, strategy_cap_block_reason(
                        signal_type, strat_open, strat_cap, account_mode,
                    ), 0.0

        # Daily loss limit (per-mode)
        try:
            account = await alpaca.get_account(account_mode=account_mode)
            equity = account["equity"]
        except Exception as e:
            logger.error(f"Safeguard [{account_mode}]: cannot get account equity: {e}")
            return False, f"{SETUP_ACCOUNT_FETCH_FAILED}: {e}", 0.0

        # PDT guard RETIRED 2026-06-04 (#181). FINRA Rule 4210 + Alpaca's new
        # intraday-margin framework eliminated the PDT designation and the $25K
        # floor (4x intraday BP now from $2K). Alpaca returns pattern_day_trader=
        # false / daytrade_count=0 (fields removed by 2026-07-06) and enforces
        # intraday-margin pre-trade checks broker-side (orders into a margin
        # deficit are rejected). No Apollo-side day-trade-count gate is needed.
        # See docs/setups/safeguards.md change log 2026-06-04.

        today = et_today()
        # FL-2 daily-loss COVERAGE fix (operator-signed 2026-07-24, CHANGE_PROCESS in
        # safeguards.md): attribute each realized loss to its CLOSE day (ET), NOT alert_date.
        # A multi-day position (Day 2-5: SMA trail / partials / time-stop) that stops out
        # today was INVISIBLE to this backstop under `alert_date = today` — its loss got
        # mis-attributed to the (prior) alert day. Each realized loss now counts ONCE, on the
        # day it is realized: this CLOSES the multi-day under-count hole (the safety win) AND
        # removes the old alert-day OVER-attribution — net MORE-CORRECT, not uniformly tighter
        # (some days it counts less: old 5/21 -$1505 -> new -$643, the position wasn't lost yet
        # on its alert day). Cannot false-trip (every trip still maps to real realized losses
        # >= 2%). Backtest: old vs new disagreed on 12/28 loss-days ($0-under-old days had real
        # losses: 6/24 -$1483, 5/26 -$862). closed_at 100% populated on closed trades (0/40
        # NULL); ET conversion per the TIMESTAMPTZ->ET-date rule (CLAUDE.md time-handling).
        today_losses = await conn.fetchval("""
            SELECT COALESCE(SUM(total_pnl), 0)
            FROM mi_live_trades
            WHERE (closed_at AT TIME ZONE 'America/New_York')::date = $1
              AND status = 'closed' AND total_pnl < 0
              AND account_mode = $2
        """, today, account_mode)
        daily_limit = equity * DAILY_LOSS_LIMIT_PCT
        if abs(today_losses) >= daily_limit:
            logger.info(
                f"Safeguard [{account_mode}] blocked: daily loss limit "
                f"(${today_losses:+,.0f} >= ${daily_limit:.0f})"
            )
            return False, (
                f"{BLOCK_DAILY_LOSS}: ${today_losses:+,.0f} >= ${daily_limit:.0f} "
                f"(mode={account_mode})"
            ), 0.0

        # Circuit breaker: N consecutive losses, per mode (so a paper losing
        # streak doesn't gate live entries). Time-based escape valve mirrors
        # backtester semantics — without it, once N losses close, no new
        # entries can ever fire (the trailing-N window is permanently
        # all-losses until a winner ages into it).
        recent_closed = await conn.fetch("""
            SELECT total_pnl, closed_at FROM mi_live_trades
            WHERE status = 'closed' AND total_pnl IS NOT NULL
              AND account_mode = $2
            ORDER BY closed_at DESC LIMIT $1
        """, CIRCUIT_BREAKER_CONSEC_LOSSES, account_mode)

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
                    ), 0.0

    # Drawdown breaker — active phase only (env DRAWDOWN_BREAKER_PHASE='active').
    # Tiered (2026-05-18): BLOCK state hard-blocks new entries; REDUCE state
    # returns ok=True with 0.5× multiplier (entry_pipeline halves shares);
    # WATCH/OK return 1.0×. Shadow phase always returns 1.0× (informational
    # only). SSoT: docs/setups/safeguards.md.
    drawdown_multiplier = 1.0
    from agents.market_intelligence.constants import DRAWDOWN_BREAKER_PHASE
    if DRAWDOWN_BREAKER_PHASE == "active":
        from agents.market_intelligence.broker.drawdown_breaker import (
            read_breaker_state, get_tier_multiplier,
        )
        from agents.market_intelligence.broker.skip_reasons import BLOCK_DRAWDOWN_BREAKER
        dd_state = await read_breaker_state(account_mode)
        drawdown_multiplier = get_tier_multiplier(dd_state)
        if drawdown_multiplier == 0.0:
            # BLOCK tier — hard block
            logger.info(f"Safeguard [{account_mode}] blocked: drawdown {dd_state}")
            return False, (
                f"{BLOCK_DRAWDOWN_BREAKER}: {dd_state} (mode={account_mode}, "
                f"see mi_safeguard_state)"
            ), 0.0
        if drawdown_multiplier < 1.0:
            logger.info(
                f"Safeguard [{account_mode}]: drawdown {dd_state} → "
                f"sizing multiplier {drawdown_multiplier}×"
            )

    return True, None, drawdown_multiplier


# ── New Alerts (Day 1) ───────────────────────────────────────────────────────


def _is_window_duplicate_reason(reason) -> bool:
    """True when a skip reason is the WINDOW_DUPLICATE constant (bare, or with
    the vocabulary's optional ':detail' suffix). Matches on the constant from
    skip_reasons.py, never on the humanized display string (#475)."""
    if not isinstance(reason, str):
        return False
    return reason == WINDOW_DUPLICATE or reason.startswith(WINDOW_DUPLICATE + ":")


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

    # #444: this whole function is MAGNA53-only (signal_type="magna53" below) —
    # every alert in this batch shares ONE account_mode, so resolve it once for
    # the two digest surfaces (crash + skip-digest) instead of falling back to
    # the legacy global per message. Fail-open, never raises (mirrors the
    # ep_detector downgrade-ping precedent) — a resolve miss degrades to the
    # exact prior behavior (mode_prefix(None) == mode_prefix()), never blocks entry.
    _magna53_mode = await resolve_strategy_mode_nonfatal("magna53")

    logger.info(f"ORB monitor [{trigger}]: {len(alerts)} HIGH EP alerts: {[a['ticker'] for a in alerts]}")
    try:
        await log_audit_event("orb_triggered", f"[{trigger}] {len(alerts)} alerts: {[a['ticker'] for a in alerts]}")
    except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); logger.info already fired immediately above
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
                except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); logger.info already fired above, and the skip itself is already durable via _insert_skipped_trade() (uncaught) a few lines earlier
                    pass
                # Per-ticker Telegram suppressed — grouped digest fires post-gather.
                return {"ticker": ticker, "action": "filtered", "reason": skip_reason}

            atr_14, _atr_pct = await compute_atr_14(ticker, today)

            async def _magna_spec_builder(
                alert_ctx: dict,
                orb_bar: dict,
                regime: dict | None,
                account_mode: str,
                _atr=atr_14,
                _today=today,
            ) -> tuple[dict | None, str | None]:
                # #456: thread the SAME `today` this function already resolved
                # (used above for the regime fetch + alerts query + the
                # submit_trade_entry(today=...) call below) into the regime-
                # sizing staleness gate — not a second, independent et_today()
                # clock read inside order_manager.py.
                return await prepare_orb_order(
                    alert_ctx, orb_bar, _atr or 0, regime,
                    account_mode=account_mode, today=_today,
                )

            return await submit_trade_entry(
                alert_context=alert,
                spec_builder=_magna_spec_builder,
                regime_record=regime_record,
                strategy_label="ORB",
                signal_type="magna53",
                today=today,
                atr_14=atr_14,
                success_title="EP order placed",
                # MAGNA53 HIGH: Sonnet+Perplexity validation + ATR stop
                # width + 10:00 ET cleanup already cover dead-cat fills.
                # Midpoint check was over-strict; drop it.
                fade_midpoint_ratio=None,
                # #490: MAGNA53 opts IN to the submission-time gap re-check at its OWN 10% floor.
                # 9M Day 2 (line ~1248) deliberately does NOT — its bar is 3%, not 10%.
                rt_gap_floor_pct=_MAGNA53_MIN_GAP_PCT,
                aggregate_skips=True,
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
                    f"{mode_prefix(_magna53_mode)}🚨 *{tkr}* ORB pipeline crashed — {type(r).__name__}: {r}"
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
    skipped_results = [r for r in results if r.get("action") in ("filtered", ACTION_SKIPPED, ACTION_BLOCKED)]
    logger.info(f"ORB monitor: {entered} entered, {len(skipped_results)} skipped out of {len(alerts)} alerts")

    # Grouped skip digest — one Telegram per cron-run instead of per-ticker.
    # #475 (2026-07-15): WINDOW_DUPLICATE skips are excluded from the digest —
    # they are dedup noise from the dual bar_stream/cron ORB trigger (the same
    # alert legitimately arrives twice; one path wins, the other reports
    # "duplicate"). All GENUINE skips (filter:/setup:/block:/infra:/other
    # window:) still surface; if only duplicates remain, no Telegram is sent.
    # Duplicates stay observable: results list, log line above, orb_duplicate audit.
    digest_results = [
        r for r in skipped_results
        if not _is_window_duplicate_reason(r.get("reason"))
    ]
    if digest_results:
        bullets = "\n".join(
            f"• `{r['ticker']}` — {humanize(r.get('reason'))}"
            for r in digest_results
        )
        try:
            await send_telegram_message(
                f"{mode_prefix(_magna53_mode)}⏭️ *ORB skips ({today}, {len(digest_results)})*\n{bullets}"
            )
        except Exception as e:
            logger.error(f"ORB grouped-skip Telegram failed — {e}")

    return results


# ── Day 2+ Position Management ──────────────────────────────────────────────


async def update_open_positions_live(today: date | None = None) -> list[dict]:
    """
    Update open live positions: SMA10/20 trail + stop updates (EOD, on the close).
    Same logic as backtester/tracker.py update_open_positions(), but executes
    real orders via Alpaca.

    #361 (2026-06-23): the Day 3-5 PARTIAL-PROFIT decision has been SPLIT OUT
    of this EOD (4:45 PM) job into `run_partial_exits()`, which runs DURING
    market hours (3:45 PM). Root cause: this job fires after the 16:00 ET close,
    so a partial's stop-replace parks in `pending_replace` until the next
    session open — both old+new orders reserve the shares, qty_available=0, and
    the partial aborts. Running the partial mid-session (stop-replaces settle in
    ~0.2s, the sell fills) fixes it. This job therefore passes
    `skip_partial_decision=True` to `apply_daily_exit_step` so the partial branch
    is bypassed here — the partial fires EXACTLY ONCE, at 3:45, NOT also at 4:45.
    The SMA-trail / stop-update / running_closes advance / daily summary stay
    here at 4:45 (EOD, on the settled close). When a 3:45 partial has already
    filled, `finalize_partial_exit` has persisted partial_taken / breakeven_active /
    reduced remaining_shares to the DB, so this job (which reads fresh from
    mi_live_trades) computes the effective stop floored at entry correctly.
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

        # #361: partials moved to run_partial_exits() (3:45 PM, market-hours).
        # This 4:45 EOD job bypasses the partial branch so it never double-fires
        # the partial — it owns ONLY the SMA-trail + stop-update + summary here.
        step = apply_daily_exit_step(state, daily_bars[0], today,
                                     integer_partial_shares=True,
                                     skip_partial_decision=True)

        logger.info(
            f"Processing {ticker}: day={step.hold_days} close=${step.bar_close:.2f} "
            f"low=${step.bar_low:.2f} stop=${hard_stop:.2f} "
            f"shares={trade['remaining_shares']:.0f} partial={state['partial_taken']}"
        )

        # 1. Hard-stop verification: re-call without hard_stop if Alpaca says
        # position is still open (stop didn't actually trigger yet).
        #
        # ⚠ account_mode is LOAD-BEARING (#444, fixed 2026-07-27) — same defect
        # class as morning_stop_refresh's get_order, but with a worse failure
        # mode. Without it this read defaults to current_account_mode() =
        # "paper" inside apollo-execution, so a LIVE position is looked up in the
        # PAPER book and comes back None → `not pos` → the branch below feeds
        # finalize_stop_fill a SYNTHETIC close, marking a still-open real
        # position as closed and dropping it out of stop management entirely.
        # That is state corruption, not just churn. It had not fired yet (no
        # `inferred_close` rows exist in prod) because the SMA-trail stopped_out
        # branch had not been reached for a live position — loaded, not
        # triggered. Fixed before it could.
        if step.action == "stopped_out":
            pos = await alpaca.get_position(
                ticker, account_mode=trade["account_mode"],
            )
            if not pos or pos["qty"] <= 0:
                # T1.3 refactor 2026-05-18: delegate close commit to
                # finalize_stop_fill (the canonical authorized writer for
                # close-path columns: exits, status, remaining_shares,
                # total_pnl, closed_at, stop_order_id). This path is the
                # FALLBACK when WS missed the stop fill — synthetic
                # deterministic order_id prevents collision with real
                # Alpaca IDs + makes the idempotent check work if
                # update_open_positions_live runs twice.
                #
                # Per docs/architecture/trade-state-ownership.md:
                # live_tracker is no longer a writer to those columns;
                # hold_days + running_closes are live_tracker-domain
                # (state machine outputs) and get their own UPDATE.
                synthetic_order_id = f"inferred_close_{trade['id']}_{today.isoformat()}"
                await finalize_stop_fill(
                    trade_id=trade["id"],
                    filled_qty=int(trade["remaining_shares"]),
                    filled_price=float(step.close_price),
                    order_id=synthetic_order_id,
                )
                # Live_tracker-domain follow-up: hold_days + running_closes
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE mi_live_trades SET
                            hold_days = $2,
                            running_closes = $3::jsonb
                        WHERE id = $1
                    """, trade["id"], step.hold_days,
                        step.new_running_closes)
                # finalize_stop_fill already sends the close Telegram +
                # logs stop_exit_committed audit event. No duplicate ping.
                results.append({"ticker": ticker, "action": "stopped_out", "pnl": step.new_total_pnl})
                continue
            # Alpaca still holds — re-run skipping the close branch.
            # hard_stop stays in state so effective_stop still floors at it.
            # #361: partial branch is owned by run_partial_exits (3:45) — keep
            # skip_partial_decision=True here so this EOD job never partials.
            step = apply_daily_exit_step(state, daily_bars[0], today,
                                         integer_partial_shares=True,
                                         skip_hard_stop_close=True,
                                         skip_partial_decision=True)

        # 2. Partial profit branch — MOVED to run_partial_exits() (3:45 PM ET,
        # #361). With skip_partial_decision=True above, step.partial_fired is
        # always False here, so this job runs ONLY the SMA-trail + stop ladder.

        # 3. SMA trail close
        if step.action == "sma_stopped":
            await execute_full_exit(trade["id"], "sma_trail_stop")
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_trades SET
                        hold_days = $2, running_closes = $3::jsonb
                    WHERE id = $1
                """, trade["id"], step.hold_days,
                    step.new_running_closes)
            results.append({"ticker": ticker, "action": "sma_stopped", "hold_days": step.hold_days})
            continue

        # 4. Still open — update Alpaca stop if effective_stop rose
        current_stop = trade["stop_price"] or 0
        if step.effective_stop > current_stop + 0.01 and step.new_remaining > 0:
            await update_stop(trade["id"], round(step.effective_stop, 2))

        # #361 (2026-06-23): the partial branch moved to run_partial_exits()
        # (3:45 PM), and this job now passes skip_partial_decision=True, so
        # step.partial_fired is always False here — the former `if
        # step.partial_fired` UPDATE (which deliberately omitted
        # breakeven_active to avoid the BW 5/14 optimistic-write incident) is
        # dead code and has been removed. This job persists ONLY the
        # state-machine / live_tracker-domain columns below.
        #
        # T1.4 refactor 2026-05-17: dropped stop_price + total_pnl +
        # partial_taken + remaining_shares from this UPDATE.
        #
        # - stop_price: update_stop() above owns trail writes. Writing here is
        #   redundant when update_stop succeeded and FALSELY OPTIMISTIC when it
        #   failed (KLAR-class bug).
        # - total_pnl / partial_taken / remaining_shares: step.new_X == state[X]
        #   (no change, partial decision skipped). The "no-op idempotent write"
        #   is actually a LOST UPDATE hazard if a WS fill arrived concurrently
        #   between state-load and this UPDATE — the stale read would clobber the
        #   WS write. Authorized writers: finalize_partial_exit,
        #   finalize_full_exit, finalize_stop_fill, _sync_positions_for_mode.
        #
        # Keeps: hold_days, breakeven_active (monotonic — see below),
        # running_closes (live_tracker domain; appended exactly once here).
        #
        # F22 (7/2 review — #361 regression): breakeven_active is written as
        # `old OR step`, MONOTONIC, never TRUE→FALSE. step.new_breakeven_active
        # is a passthrough of this job's OPENING read (partial branch skipped),
        # and the read→UPDATE window spans the whole job (network calls per
        # ticker). If finalize_partial_exit (the only TRUE-writer, on the WS
        # fill) lands inside that window — a delayed 3:45-partial fill, or an
        # operator /partialnow — a plain `= $3` clobbers TRUE back to FALSE
        # with NO self-heal (partial_taken stays TRUE so the partial never
        # re-fires; the stop then floors below entry for the trade's life).
        # OR-ing preserves it; safe because no writer legitimately resets the
        # flag on an open row (order_manager:1858 is TRUE-only).
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    hold_days = $2,
                    breakeven_active = (breakeven_active OR $3),
                    running_closes = $4::jsonb
                WHERE id = $1
            """, trade["id"], step.hold_days,
                step.new_breakeven_active,
                step.new_running_closes)

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


async def run_partial_exits(today: date | None = None) -> list[dict]:
    """Run the Day 3-5 partial-profit decision DURING market hours (3:45 PM ET).

    #361 (2026-06-23): SPLIT OUT of the 4:45 PM `update_open_positions_live`
    EOD job. The partial-profit decision LOGIC is UNCHANGED — it is still the
    single source of truth in `apply_daily_exit_step` (we reuse it; we do not
    duplicate the decision). Only WHEN it fires moved: from after the close
    (4:45) to mid-session (3:45).

    WHY 3:45 / market-hours: when the partial fired at 4:45 (after the 16:00 ET
    close), its stop-replace parked in `pending_replace` until the next session
    open. Both the old and the new stop reserved the shares → qty_available=0 →
    the partial sell aborted. Mid-session, the stop-replace settles in ~0.2s and
    the sell fills cleanly.

    Acts ONLY on the partial branch (`step.partial_fired`) → `execute_partial_exit`.
    Persists NOTHING here:
      - The reduced remaining / partial_taken / breakeven_active / exits are
        committed by `finalize_partial_exit` on the actual WS fill (the only
        authorized writer — BW 5/14 optimistic-write protocol).
      - running_closes / hold_days / SMA-trail stop stay OWNED by the 4:45 job.
        Writing running_closes here would DOUBLE-APPEND today's close (the
        append at exit_logic.py line ~98 runs every call), corrupting the SMA
        basis — so this function deliberately discards the rest of `step`.

    No double-fire: the 4:45 job passes `skip_partial_decision=True`, so the
    partial can fire only here, exactly once per day.

    Note: at 3:45 `get_index_history` returns today's FORMING daily bar (live
    Polygon aggregate), so `bar_close` is the intraday last trade, not the
    settled close. For the Day 3-4 branch (`bar_close > entry_price`) this is an
    intraday evaluation — implicit in the operator's choice of a market-hours
    trigger. Day 5+ is unconditional and unaffected.
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
        logger.info("run_partial_exits: no open live positions")
        return []

    logger.info(
        f"run_partial_exits: scanning {len(open_trades)} open positions for "
        f"Day 3-5 partials: {[dict(t)['ticker'] for t in open_trades]}"
    )
    results: list[dict] = []

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
            logger.debug(f"run_partial_exits: no daily bar for {ticker} on {today}")
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

        # Single-source-of-truth partial decision. We discard everything in
        # `step` EXCEPT partial_fired / partial_shares — the SMA-trail, stop,
        # and running_closes advance are the 4:45 job's domain (see docstring).
        #
        # skip_hard_stop_close=True is REQUIRED here (matches the 4:45 job's
        # post-verify re-run): at 3:45 the forming bar's `bar_low` is the
        # intraday low, so a position that WICKED to/through its hard_stop
        # intraday but recovered (still open, still green) would short-circuit
        # `apply_daily_exit_step` at its step-1 hard-stop close — returning
        # partial_fired=False BEFORE the partial branch — and we'd silently DROP
        # that day's partial. The real Alpaca resting stop is the actual stop
        # mechanism (the backtest-pure bar_low<=hard_stop close is a no-op once
        # the position is confirmed held); these positions ARE held (the query
        # filters status='filled' AND remaining_shares>0). Skipping the close
        # branch keeps the partial decision alive — faithful to the validated
        # live behavior. We still act ONLY on partial_fired; the close path is
        # never executed from this partial-only job.
        # #508 — when the intraday profit trigger is ON it OWNS the partial, so the
        # 3:45 time-gate must stand down or both could act on the same position.
        # Done at the CALLER, not by editing exit_logic: that module is pure decision
        # logic with no config dependency, and it already exposes exactly this seam
        # (`update_open_positions_live` at 4:45 has passed skip_partial_decision=True
        # since #361 for the same reason — one owner per decision).
        # PROFIT_TRIGGER_R = None restores the day-3/day-5 rule with no code change.
        from agents.market_intelligence.constants import PROFIT_TRIGGER_R
        step = apply_daily_exit_step(state, daily_bars[0], today,
                                     integer_partial_shares=True,
                                     skip_hard_stop_close=True,
                                     skip_partial_decision=bool(PROFIT_TRIGGER_R))

        if not step.partial_fired:
            results.append({"ticker": ticker, "action": "no_partial"})
            continue

        logger.info(
            f"run_partial_exits: {ticker} day={step.hold_days} "
            f"close=${step.bar_close:.2f} partial_shares={step.partial_shares:.0f}"
        )

        # ── Announce the DECISION, not just the downstream fill (operator 2026-08-01:
        # "is telegram hooked up to notify me of profit takes"). It was not: this job
        # had ZERO Telegram calls, so a partial the system CHOSE to take reached him
        # only as a broker fill event with no statement of why or at what level. On a
        # rule whose whole purpose is "take profit at X", the reasoning is the message.
        # Self-catching: a notification failure must never abort a money action that
        # is about to run on the next line.
        try:
            _entry = trade.get("entry_price")
            _risk = (_entry - hard_stop) if (_entry and hard_stop) else None
            _rem = trade.get("remaining_shares")
            r_now = ((step.bar_close - _entry) / _risk) if (_risk and _entry) else None
            await send_telegram_message(
                f"{mode_prefix(trade.get('account_mode'))}💰 *Profit-take firing: {ticker}*\n"
                f"day {step.hold_days} · close ${step.bar_close:.2f}"
                + (f" · {r_now:+.2f}R" if r_now is not None else "")
                + f"\nSelling {int(step.partial_shares)} of {int(_rem)} sh, "
                f"stop moves to breakeven (${_entry:.2f})."
            )
        except Exception:  # loud-ok: send_telegram_message self-catches and returns False; this guards the f-string/format path only. The partial below MUST run regardless.
            logger.warning(f"partial-decision notify failed for {ticker}", exc_info=True)

        partial_ok = await execute_partial_exit(trade["id"], int(step.partial_shares))
        # finalize_partial_exit commits the DB state on the actual WS fill; if
        # the helper aborts/fails it has already audit-logged + (where relevant)
        # re-protected the stop. Nothing to persist here either way — the 4:45
        # job and the WS fill own all state writes.
        results.append({
            "ticker": ticker,
            "action": "partial_submitted" if partial_ok else "partial_failed",
            "shares": int(step.partial_shares),
        })

    return results


# ── Morning Stop Refresh ─────────────────────────────────────────────────────


async def morning_stop_refresh() -> int:
    """
    At 9:35 AM, ensure stop orders are active for all Day 2+ positions.
    Alpaca DAY stops expire overnight — re-place them as GTC.
    Returns count of stops refreshed.

    SAME-DAY EXCLUSION (ADR 0029 D1, signed 2026-07-12, shipped 2026-07-26). The
    docstring above always said "Day 2+", but the query did not enforce it — it
    selected every filled position including ones that filled THIS MORNING, whose
    stop is an OTO child placed atomically with the entry. Refreshing those raced
    the broker's own child order and produced the WULF `insufficient qty
    available` self-conflict. Entry day = the OTO child owns the stop BY
    CONSTRUCTION; the refresh exists solely to replace overnight-expired DAY
    stops, which by definition cannot apply to a same-morning fill. Excluding
    them removes the 9:35 collision at the root — the #433 retry machinery stays
    as belt-and-suspenders and is expected to go quiet.

    Day-1 RE-ENTRY is covered by the same exclusion and deliberately so (advisor
    carve-in, ADR 0029): `attempt_day1_reentry` places a FRESH OTO bracket on the
    same alert_date after a stop-out, so its protection is likewise its own
    atomically-placed child.

    This job NEVER discovers stops — a NULL/stale `stop_order_id` is a MIRROR
    defect, healed by the remediation stack (3-source capture at fill,
    `sync_positions` Path-C naked remediation, #184b R1 ingest repointing), never
    by this refresh. So a genuinely-naked same-day trade is still caught; it is
    not silently skipped forever. Risk framing: this NARROWS a live job — it does
    strictly less, on a cohort whose protection already exists.
    """
    today = et_today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        trades = await conn.fetch("""
            SELECT id, ticker, remaining_shares, stop_price, stop_order_id,
                   account_mode
            FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0
              AND alert_date <> $1
        """, today)

    refreshed = 0
    refreshed_tickers: list[str] = []
    for trade in trades:
        ticker = trade["ticker"]
        stop_price = trade["stop_price"]

        if not stop_price or not trade["remaining_shares"]:
            continue

        # Check if existing stop order is still active.
        #
        # ⚠ account_mode is LOAD-BEARING here (#444, fixed 2026-07-27). Without
        # it this read defaulted to current_account_mode(), which resolves to
        # "paper" inside apollo-execution — so a LIVE stop_order_id was looked up
        # in the PAPER book, always returned None, and this "still active → skip"
        # branch was unreachable dead code. The job then cancelled and re-placed
        # every live Day-2+ stop EVERY morning at an identical price, each cycle
        # leaving a window with no resting stop on a real position. Confirmed in
        # prod on SMCI: 9:35 ET replacements on 07-22, 07-23 and 07-24, all
        # $28.5 → $28.50, one of which raised an APIError and needed the #433
        # retry. Passing the trade's OWN mode makes the skip branch reachable, so
        # an already-active stop is left alone.
        if trade["stop_order_id"]:
            order = await alpaca.get_order(
                trade["stop_order_id"], account_mode=trade["account_mode"],
            )
            if order and str(order.get("status", "")).split(".")[-1].lower() in ("new", "accepted", "held"):
                logger.debug(f"Stop still active for {ticker}")
                continue

        # Re-place stop
        success = await update_stop(trade["id"], stop_price)
        if success:
            refreshed += 1
            refreshed_tickers.append(ticker)
            logger.info(f"Morning stop refreshed: {ticker} @${stop_price:.2f}")

    if refreshed:
        # #475 (2026-07-15): routine housekeeping — expected every morning for
        # every Day 2+ position (DAY stops expire overnight). Log only; failures
        # in update_stop() keep their own loud paths.
        logger.info(
            f"Morning: refreshed {refreshed} stop order(s) — {', '.join(refreshed_tickers)}"
        )
    return refreshed


# ── Daily Summary ────────────────────────────────────────────────────────────


async def _gather_mode_summary(conn, mode: str, today) -> dict:
    """Per-account-mode slice of the daily book. Every query is filtered by
    account_mode so paper and live never bleed together (the pre-dual-account
    version queried the whole table and mislabeled everything paper — operator 7/8)."""
    stats = await conn.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE status NOT IN ('skipped','cancelled','order_failed')) as total,
            COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0) as winners,
            COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl <= 0) as losers,
            COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) as realized_pnl
        FROM mi_live_trades WHERE account_mode = $1
    """, mode)
    open_trades = await conn.fetch("""
        SELECT ticker, entry_price, remaining_shares, stop_price, hold_days,
               partial_taken, total_pnl
        FROM mi_live_trades
        WHERE status = 'filled' AND remaining_shares > 0 AND account_mode = $1
        ORDER BY alert_date ASC
    """, mode)
    todays_closes = await conn.fetch("""
        SELECT ticker, total_pnl, hold_days FROM mi_live_trades
        WHERE status = 'closed' AND account_mode = $2
          AND (closed_at AT TIME ZONE 'America/New_York')::date = $1
    """, today, mode)
    todays_entries = await conn.fetch("""
        SELECT ticker, entry_price, entry_shares FROM mi_live_trades
        WHERE alert_date = $1 AND account_mode = $2 AND status IN ('filled', 'order_placed')
    """, today, mode)
    todays_skipped = await conn.fetch("""
        SELECT ticker, skip_reason FROM mi_live_trades
        WHERE alert_date = $1 AND account_mode = $2
          AND status IN ('skipped', 'cancelled', 'order_failed')
    """, today, mode)
    return {"stats": stats, "open": open_trades, "closes": todays_closes,
            "entries": todays_entries, "skipped": todays_skipped}


def _mode_has_activity(d: dict) -> bool:
    return bool(d["entries"] or d["closes"] or d["skipped"] or d["open"]
                or (d["stats"]["total"] and d["stats"]["total"] > 0))


async def send_live_trade_summary() -> None:
    """Daily summary of trading activity, PER ACCOUNT (dual-account #66).
    #479: routed into the 16:55 Market Close Digest (BOOK section) instead of
    a standalone Telegram — render text unchanged.

    Live-money account is the PRIMARY block (full detail); paper is FOLDED into a
    compact secondary line (operator 7/8: only the paper book was reported, so the
    real-money EOD state was invisible). Paper-only deployments (ENABLE_LIVE_MODE
    off) render exactly as before. Called after the position update."""
    from agents.market_intelligence.constants import active_account_modes
    pool = await get_pool()
    today = et_today()
    modes = active_account_modes()
    async with pool.acquire() as conn:
        data = {m: await _gather_mode_summary(conn, m, today) for m in modes}

    primary = "live" if "live" in modes else "paper"
    prim = data[primary]
    prim_label = "Live" if primary == "live" else "Paper"
    lines = [f"{mode_prefix(primary)}📊 *Live Trade Update (Alpaca — {prim_label})*\n"]

    # ── PRIMARY block (full detail) ──
    if prim["entries"]:
        lines.append("*Entered today:*")
        for t in prim["entries"]:
            lines.append(f"  ▶ {t['ticker']} @${t['entry_price']:.2f} × {t['entry_shares']:.0f}")
        lines.append("")
    if prim["skipped"]:
        lines.append("*Filtered today:*")
        for t in prim["skipped"]:
            lines.append(f"  ⊘ {t['ticker']}: {humanize(t['skip_reason'])}")
        lines.append("")
    if prim["closes"]:
        lines.append("*Closed today:*")
        for t in prim["closes"]:
            emoji = "✅" if t["total_pnl"] > 0 else "❌"
            lines.append(f"  {emoji} {t['ticker']} ${t['total_pnl']:+,.2f} ({t['hold_days']}d)")
        lines.append("")
    if prim["open"]:
        lines.append(f"*Open positions ({len(prim['open'])}):*")
        for t in prim["open"]:
            ticker = t["ticker"]
            try:
                pos = await alpaca.get_position(ticker, primary)
                current = pos["current_price"] if pos else None
                unrealized = pos["unrealized_pl"] if pos else 0
            except Exception as e:
                logger.warning(f"Could not get position for {ticker} ({primary}) in summary: {e}")
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

    ps = prim["stats"]
    prim_closed = (ps["winners"] or 0) + (ps["losers"] or 0)
    try:
        account = await alpaca.get_account(primary)
        lines.append(f"*Account:* ${account['equity']:,.0f}")
    except Exception as e:
        logger.warning(f"Could not get {primary} account equity for summary: {e}")
    if prim_closed > 0:
        wr = ps["winners"] / prim_closed * 100
        lines.append(f"*Record:* {ps['winners']}W/{ps['losers']}L ({wr:.0f}%) · "
                     f"${float(ps['realized_pnl']):+,.2f}")
    elif ps["total"]:
        lines.append(f"*Trades:* {ps['total']} (no closes yet)")

    # ── FOLDED paper block (compact secondary) ──
    # Only when paper is ACTIVELY trading that day (today-activity or open positions) —
    # NOT for the dormant historical cumulative. Nothing is phase='paper' today, so this
    # stays silent until a setup is promoted to paper (operator 7/8); it then auto-reappears.
    pap = data.get("paper")
    _paper_active = pap and (pap["entries"] or pap["closes"] or pap["skipped"] or pap["open"])
    if primary == "live" and _paper_active:
        pst = pap["stats"]
        pap_closed = (pst["winners"] or 0) + (pst["losers"] or 0)
        seg = []
        try:
            pa = await alpaca.get_account("paper")
            seg.append(f"${pa['equity']:,.0f}")
        except Exception as e:
            logger.warning(f"Could not get paper account equity for summary: {e}")
        if pap_closed > 0:
            wr = pst["winners"] / pap_closed * 100
            seg.append(f"{pst['winners']}W/{pst['losers']}L ({wr:.0f}%) · "
                       f"${float(pst['realized_pnl']):+,.2f}")
        act = []
        if pap["entries"]:
            act.append(f"{len(pap['entries'])} entered")
        if pap["skipped"]:
            act.append(f"{len(pap['skipped'])} filtered")
        if pap["closes"]:
            act.append(f"{len(pap['closes'])} closed")
        if pap["open"]:
            act.append(f"{len(pap['open'])} open")
        lines.append("\n— 📄 *Paper (shadow book):* " + (" · ".join(seg) or "—")
                     + (f"  ·  today: {', '.join(act)}" if act else ""))

    # Surface if any account had activity today or holds open positions.
    # #479: the routine daily summary no longer Telegrams directly — the same
    # render text goes to close_digest.contribute("BOOK", ...) and lands in
    # the 16:55 Market Close Digest (this function is job-exclusive to the
    # 16:45 live_position_update job).
    if any(_mode_has_activity(data[m]) for m in modes):
        from agents.market_intelligence.close_digest import contribute
        contribute("BOOK", "\n".join(lines))


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _insert_skipped_trade(
    ticker: str,
    today: date,
    alert: dict | None,
    regime_record: dict | None,
    skip_reason: str,
    signal_type: str | None = None,
    account_mode: str | None = None,
) -> None:
    """Insert a skipped live trade record.

    alert / regime_record may be None — the bar-stream timeout path cannot
    hydrate them without a DB join during a stuck lock. The invariant is that
    (ticker, alert_date, status='skipped', skip_reason) lands in mi_live_trades;
    score/catalyst/gap/regime can be LEFT-JOINed from mi_ep_alerts by /why.

    account_mode: the Alpaca account the skipped signal belongs to. Pass it for
    strategy-bound skips (a live-strategy signal → 'live') so the EOD summary
    attributes the filtered trade to the right account. Defaults to
    current_account_mode() for legacy callers (pre-dual-account behavior).
    """
    pool = await get_pool()
    # `today` (the alert_date) arrives as an ISO STRING when this is dispatched
    # over the intelligence→execution HTTP wire (_wire_default serializes dates);
    # coerce back so asyncpg's date_encode doesn't raise. This is the DB-write
    # boundary — routed through the shared db._coerce_date helper (LZB
    # 2026-06-13: this site missed the coercion → a HIGH alert sat with no terminal row).
    today = _coerce_date(today)
    ep_score = alert.get("ep_score") if alert else None
    catalyst_quality = alert.get("catalyst_quality") if alert else None
    gap_pct = alert.get("gap_pct") if alert else None
    regime = regime_record.get("regime") if regime_record else None
    from agents.market_intelligence.constants import current_account_mode
    account_mode = account_mode or current_account_mode()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_live_trades
                (ticker, alert_date, ep_score, catalyst_quality, gap_pct,
                 regime, status, skip_reason, signal_type, account_mode)
            VALUES ($1, $2, $3, $4, $5, $6, 'skipped', $7, $8, $9)
            ON CONFLICT (ticker, alert_date) DO NOTHING
        """,
            ticker, today, ep_score, catalyst_quality, gap_pct, regime,
            skip_reason, signal_type, account_mode,
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

    # Pipeline spec_builder signature is (alert_ctx, orb_bar, regime,
    # account_mode) — the sugar_baby row IS the alert_context, so we just
    # pass it through. account_mode threaded for dual-account #66 routing.
    async def _ninem_spec_builder(
        alert_ctx: dict, orb_bar: dict, regime: dict | None, account_mode: str,
    ) -> tuple[dict | None, str | None]:
        # #456: thread this function's own `today` (already used above for the
        # submit_trade_entry(today=...) call) into the regime-sizing
        # staleness gate, not a second independent et_today() clock read.
        return await prepare_9m_day2_orb_order(
            alert_ctx, orb_bar, regime, account_mode=account_mode, today=today,
        )

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
        success_title="9M Day2 order placed",
        stop_label="Stop (prev day low)",
        on_skip=_on_skip,
        # 9M is pure quant (no LLM validation); keep some fade protection
        # but loose — only skip on real weakness (lower 25% of ORB).
        fade_midpoint_ratio=0.25,
        aggregate_skips=True,
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
