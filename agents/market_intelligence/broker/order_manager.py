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
from contextlib import asynccontextmanager
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from zoneinfo import ZoneInfo

from agents.market_intelligence.backtester.filters import validate_orb_entry
from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_REENTRY_GAP_THROUGH,
    BROKER_ENTRY_CANCELLED,
    BROKER_ENTRY_EXPIRED,
    BROKER_ENTRY_REJECTED,
    INFRA_ORDER_SUBMIT_FAILED,
    SETUP_ACCOUNT_FETCH_FAILED,
    SETUP_CHASE_CAP_EXCEEDED,
    SETUP_PRICE_EXCEEDS_CAP,
    SETUP_SIZE_TOO_SMALL,
    SETUP_STOP_TOO_WIDE,
    SETUP_ZERO_RANGE,
    humanize,
)
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.constants import (
    current_account_mode,
    mode_prefix,
    active_account_modes,
    LIVE_TRADING_ENABLED,
    RISK_PCT,
    REGIME_SIZING_FALLBACK_MULTIPLIER,
)
from agents.market_intelligence.db import get_pool, log_audit_event, get_manual_halt_state
from agents.market_intelligence.audit_events import SIZING_REGIME_FALLBACK

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


# #500 (2026-07-23): bound the price-aware fallback's chase. Entry shares are
# sized on PLANNED risk (orb_high - stop); a fallback limit-buy fill at
# `limit` carries ACTUAL risk (limit - stop). Cap actual/planned so a runaway
# gapper can't silently multiply per-trade risk (CADL 2026-04-20 would have
# been 11.3x planned; ARWR 2026-07-22 was 1.37x → admitted). 1.5x = worst-case
# 1.5% equity on a full stop-out at the standard 1%-risk sizing. Evidence +
# operator sign-off: docs/analysis/500_orb_entry_price_aware_proposal_2026-07-23.md
CHASE_RISK_INFLATION_CAP = float(os.getenv("CHASE_RISK_INFLATION_CAP", "1.5"))


async def broker_terminal_reason(event_norm: str, ticker: str, trigger_price) -> str:
    """#500 reason capture: build a `broker:*` skip_reason for an entry order
    the BROKER killed (cancel/reject/expire).

    Alpaca sends no textual reason anywhere (order object, WS payload,
    dashboard — confirmed in the ARWR 2026-07-22 incident), so synthesize the
    diagnosis Alpaca won't: last trade vs the entry trigger at event time.
    `last > trigger` at a cancel = the in-the-money-stop class this fix exists
    for. Degrades to the bare prefix on any data problem — never raises, never
    blocks the status update.
    """
    prefix = {
        "cancelled": BROKER_ENTRY_CANCELLED,
        "canceled": BROKER_ENTRY_CANCELLED,
        "rejected": BROKER_ENTRY_REJECTED,
        "expired": BROKER_ENTRY_EXPIRED,
    }.get(event_norm, BROKER_ENTRY_CANCELLED)
    if trigger_price is None:
        return prefix  # no trigger to compare against — skip the price fetch
    try:
        latest = await alpaca.get_latest_trade(ticker)
        if latest and latest.get("price") and trigger_price is not None:
            px = float(latest["price"])
            trig = float(trigger_price)
            rel = "above" if px > trig else "at/below"
            diagnosis = f"last ${px:.2f} {rel} trigger ${trig:.2f} at event"
            if px > trig:
                diagnosis += " — in-the-money stop (#500 class)"
            return f"{prefix}: {diagnosis}"
    except Exception as e:
        logger.debug(f"broker-cancel diagnosis failed for {ticker}: {e}")
    return prefix


# ── Order Preparation ────────────────────────────────────────────────────────


def _regime_sizing_freshness_threshold(today: date) -> date:
    """The oldest `regime_date` that still counts as FRESH when read at an ORB
    entry on `today` (#456).

    The regime nightly runs at 17:00 ET and stamps `regime_date` = the day it
    ran, so an ORB entry the FOLLOWING trading morning is EXPECTED to read
    yesterday's row — not today's (today's nightly hasn't run yet). The naive
    predicate `regime_date < last_trading_day(today)` is wrong: on any
    ordinary trading day `last_trading_day(today) == today`, so it would floor
    + fail-loud EVERY morning. The correct threshold is the last completed
    trading day strictly BEFORE today.

    Known limitation (documented, not fixed — see safeguards.md): weekend-only,
    no market-holiday calendar (matches `last_trading_day`'s own docstring).
    The trading day after a market holiday reads one day tighter than
    necessary and floors+alerts as a false positive (~9x/yr). Safe-direction
    (floors size, doesn't oversize) — accepted rather than building a holiday
    calendar for this.
    """
    from agents.market_intelligence.collector import last_trading_day
    return last_trading_day(today - timedelta(days=1))


async def _alert_regime_sizing_fallback_once(
    *, account_mode: str, regime_date: date | None, label: str | None,
    today: date, reason: str,
) -> None:
    """Ruling 5 (#456, operator 2026-07-26): "it should fail loud so we can
    fix." Missing / stale / unrecognized regime sizes at the fail-safe floor
    AND pages — Telegram + audit, deduped ONCE per ET day per account_mode so
    a broken nightly can't spam one alert per candidate. Audit-log-as-state
    dedup, same idiom as `intraday_drawdown._already_alerted_today`: the
    day's first occurrence writes ONE audit row (the durable record AND the
    dedup marker); later occurrences the same day/mode are silent no-ops
    (mirrors the drawdown-crossing precedent — a duplicate doesn't re-log).

    Known race (accepted, documented — matches the #461-class precedent): the
    ORB monitor processes up to 5 candidates concurrently (`Semaphore(5)` +
    `gather`), so on the FIRST fallback morning multiple candidates can all
    read "not yet alerted" before any commits — bounded to at most a handful
    of duplicate Telegrams that morning, never more. The audit row remains the
    single source of truth surviving restarts; this is a Telegram-count
    nicety, not a sizing-correctness concern (the floor multiplier applies
    correctly regardless of the race).
    """
    marker = f"account_mode={account_mode}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT summary FROM mi_audit_log
            WHERE event_type = $1
              AND (created_at AT TIME ZONE 'America/New_York')::date = $2
            """,
            SIZING_REGIME_FALLBACK, today,
        )
    if any(marker in (r["summary"] or "") for r in rows):
        return  # already alerted this ET day for this account_mode

    detail_date = regime_date.isoformat() if regime_date else "none"
    summary = (
        f"{marker} regime sizing fallback ({reason}): last regime_date seen="
        f"{detail_date} label={label!r} -> floor "
        f"{REGIME_SIZING_FALLBACK_MULTIPLIER:.2f}x"
    )
    await log_audit_event(SIZING_REGIME_FALLBACK, summary)
    await send_telegram_message(
        f"{mode_prefix(account_mode)}🚨 Regime sizing FALLBACK ({reason}): "
        f"last regime_date seen {detail_date}, label={label or 'none'} — "
        f"sizing floored to {REGIME_SIZING_FALLBACK_MULTIPLIER:.0%}. Regime "
        f"feed may be broken — check the nightly regime job."
    )


async def _resolve_regime_risk_pct(
    regime_record: dict | None,
    today: date,
    account_mode: str | None,
    base_pct: float = RISK_PCT,
) -> float:
    """#456 — the SINGLE regime-keyed risk_pct resolver. Both real-money
    sizing sites (`prepare_orb_order` / MAGNA53, `prepare_prior_day_low_orb_order` /
    9M Day2) call this — no scattered copies of the fold, per this repo's
    documented history of hand-synced duplicates drifting apart.

    `REGIME_SIZING_ENABLED=false` (default): reproduces today's exact
    behavior — `vix_scaled_risk_pct(vix)` with the separate `qqq_ema_bullish`
    binary halve. Byte-identical to pre-#456 code; this is the untouched
    behavior the feature flag protects.

    `REGIME_SIZING_ENABLED=true`: `risk_pct = base_pct *
    regime_risk_multiplier(label)`. The `qqq_ema_bullish` halve is FOLDED
    (operator ruling 2 — "VIX is not the only gate"; the regime classifier
    already scores the bearish tape, the halve double-counted it) and VIX no
    longer scales sizing directly — it only feeds the regime classifier.
    Missing / stale (`regime_date` older than the last completed trading day
    before `today`) / unrecognized-label regime floors to
    `REGIME_SIZING_FALLBACK_MULTIPLIER` (0.25x) AND fires the fail-loud alert
    (ruling 5).
    """
    from agents.market_intelligence.constants import (
        REGIME_SIZING_ENABLED,
        REGIME_RISK_MULTIPLIER,
        regime_risk_multiplier,
        vix_scaled_risk_pct,
    )

    if not REGIME_SIZING_ENABLED:
        vix_value = regime_record.get("vix") if regime_record else None
        risk_pct = vix_scaled_risk_pct(vix_value, base_pct=base_pct)
        if regime_record and regime_record.get("qqq_ema_bullish") is False:
            risk_pct *= 0.5
        return risk_pct

    from agents.market_intelligence.db import _coerce_date

    label = regime_record.get("regime") if regime_record else None
    regime_date = (
        _coerce_date(regime_record.get("regime_date")) if regime_record else None
    )
    threshold = _regime_sizing_freshness_threshold(today)
    is_stale = regime_date is None or regime_date < threshold
    is_unrecognized = (not is_stale) and label not in REGIME_RISK_MULTIPLIER

    if is_stale or is_unrecognized:
        # PAGING MUST NEVER BLOCK THE FLOOR (advisor review, 2026-07-26). The alert
        # does get_pool() -> conn.fetch -> log_audit_event -> Telegram; any of those
        # can raise, and this branch runs ONLY when the regime feed is already
        # broken — precisely the moment not to introduce a second failure mode. An
        # unguarded await here would propagate out of prepare_orb_order instead of
        # returning the floored size, i.e. the fail-LOUD mechanism would defeat the
        # fail-SAFE one it exists to announce. Ruling 5 asked for both: floor AND
        # page. The floor is the safety property, so it wins on conflict.
        # loud-ok: the failure is reported (logger.exception) and the sizing
        # decision is unaffected — swallowing here is the fail-safe direction.
        try:
            await _alert_regime_sizing_fallback_once(
                account_mode=account_mode or current_account_mode(),
                regime_date=regime_date,
                label=label,
                today=today,
                reason="missing_or_stale" if is_stale else "unrecognized_label",
            )
        except Exception:
            logger.exception(
                "regime sizing fallback alert FAILED — sizing still floored to "
                f"{REGIME_SIZING_FALLBACK_MULTIPLIER:.2f}x (label={label!r} "
                f"regime_date={regime_date})"
            )
        return base_pct * REGIME_SIZING_FALLBACK_MULTIPLIER

    return base_pct * regime_risk_multiplier(label)


async def prepare_orb_order(
    alert: dict,
    orb_bar: dict,
    atr_14: float,
    regime_record: dict | None,
    account_mode: str | None = None,
    today: date | None = None,
) -> tuple[dict | None, str | None]:
    """
    Compute entry/stop/shares/risk from ORB bar and account equity.
    Returns (spec, None) on success or (None, reason) on any rejection.

    `today` (#456): pass the SAME `today` the caller already resolved for the
    regime fetch / alerts query / `submit_trade_entry` (e.g.
    `process_new_alerts_live`'s `today` param) — the regime-sizing staleness
    gate must compare against that value, not a fresh `et_today()` call made
    independently inside this function. A second, unpinned clock read here
    could silently diverge from the caller's `today` under
    `EXECUTION_MODE=http` (cross-container) or a slow bar-fetch retry
    spanning a midnight ET boundary. Defaults to `et_today()` only for
    callers that don't have one on hand (e.g. tests, or the HTF path).
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

    # Position sizing (#456): regime-keyed risk_pct when REGIME_SIZING_ENABLED,
    # else byte-identical to the pre-#456 P19 VIX-scaled + qqq_ema_bullish-halve
    # formula. Single resolver — see _resolve_regime_risk_pct's docstring.
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()
    risk_pct = await _resolve_regime_risk_pct(
        regime_record, today, account_mode, base_pct=RISK_PCT,
    )

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

    # #345 manual halt — defense-in-depth so the `/pause` panic button covers EVERY
    # real-money submit path, not just the auto-submit funnel (_check_safeguards).
    # The telegram_confirm proposal-confirm path reaches submit_entry directly,
    # bypassing _check_safeguards. Peek account_mode BEFORE the atomic claim so a
    # halted/unreadable LIVE submit aborts WITHOUT leaving the row stuck in
    # 'submitting' (status stays 'confirmed' → re-submittable after /resume).
    # Fail-SAFE (unreadable blocks); paper/shadow unaffected.
    async with pool.acquire() as conn:
        _peek = await conn.fetchrow(
            "SELECT account_mode FROM mi_live_trades WHERE id = $1", trade_id)
    if _peek and (_peek["account_mode"] or current_account_mode()) == "live":
        _halt = await get_manual_halt_state()
        if _halt in ("on", "unreadable"):
            logger.warning(f"submit_entry {trade_id}: blocked by manual trading halt ({_halt})")
            await log_audit_event(
                "trade_submit_blocked_by_halt",
                f"trade {trade_id} blocked at submit_entry — manual trading halt ({_halt})",
                json.dumps({"trade_id": trade_id, "halt_state": _halt}),
            )
            return None

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

    # #500 price-aware entry (2026-07-23, operator-signed): a stop-limit BUY
    # whose trigger is already below the market is invalid at the broker —
    # Alpaca kills it instead of filling (ARWR 2026-07-22: pending_new →
    # cancelled within ~1 min on a +19.6% gapper). Mirror the re-entry branch
    # (attempt_day1_reentry): when the latest trade is above the ORB high,
    # place a bounded limit buy instead. Fail-open: any data problem selects
    # the bracket (pre-#500 behavior, byte-identical).
    orb_high_f = float(trade["orb_high"])
    _stop_raw = trade["stop_price"] if trade["stop_price"] is not None else trade["orb_low"]
    stop_loss_f = float(_stop_raw)

    async def _pick_entry() -> tuple[str, float | None]:
        """('stop_limit', None) = the normal bracket; ('limit', px) = fallback."""
        latest = await alpaca.get_latest_trade(ticker)
        if latest and latest.get("price") and float(latest["price"]) > orb_high_f:
            return "limit", round(float(latest["price"]) * 1.002, 2)
        return "stop_limit", None

    def _chase_cap_reason(fallback_limit: float) -> str | None:
        """Skip-reason when the fallback chases too far; None = within cap."""
        planned = orb_high_f - stop_loss_f
        actual = fallback_limit - stop_loss_f
        if planned > 0 and actual <= CHASE_RISK_INFLATION_CAP * planned:
            return None
        return (
            f"{SETUP_CHASE_CAP_EXCEEDED}: limit ${fallback_limit:.2f} risk "
            f"${actual:.2f}/sh vs planned ${planned:.2f}/sh "
            f"(cap {CHASE_RISK_INFLATION_CAP:.2f}x, ORB high ${orb_high_f:.2f})"
        )

    async def _skip_chase_capped(reason: str, status: str) -> None:
        await _update_trade_status(trade_id, status, skip_reason=reason)
        await log_audit_event(
            "entry_chase_cap_skipped",
            f"{ticker} [{account_mode}]: {reason}",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "orb_high": orb_high_f, "stop": stop_loss_f,
            }),
        )
        await send_telegram_message(
            f"{mode_prefix(account_mode)}⚠️ No entry for {ticker}: {humanize(reason)}"
        )

    async def _submit(entry_type: str, fallback_limit: float | None, submit_coid: str) -> dict:
        if entry_type == "limit":
            logger.info(
                f"{ticker}: price above ORB high ${orb_high_f:.2f} — "
                f"limit-buy fallback at ${fallback_limit:.2f} (#500)"
            )
            return await alpaca.place_limit_buy_with_stop(
                ticker=ticker,
                qty=trade["entry_shares"],
                limit_price=fallback_limit,
                stop_loss_price=trade["stop_price"],
                account_mode=account_mode,
                client_order_id=submit_coid,
            )
        return await alpaca.place_bracket_order(
            ticker=ticker,
            qty=trade["entry_shares"],
            stop_price=trade["orb_high"],
            limit_price=stop_limit_buy_price(trade["orb_high"]),
            stop_loss_price=trade["stop_price"],
            account_mode=account_mode,
            client_order_id=submit_coid,
        )

    entry_type, fallback_limit = await _pick_entry()
    if entry_type == "limit":
        _cap_reason = _chase_cap_reason(fallback_limit)
        if _cap_reason:
            await _skip_chase_capped(_cap_reason, "cancelled")
            return None

    coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
    try:
        order = await _submit(entry_type, fallback_limit, coid)
    except Exception as e:
        # 1 retry after 5s for transient errors
        logger.warning(f"Entry order failed for {ticker}, retrying: {e}")
        await asyncio.sleep(5)
        try:
            # Re-decide the order type: 5s is long at 9:31 — price may have
            # crossed the ORB high either way since the first attempt (#500).
            entry_type, fallback_limit = await _pick_entry()
            if entry_type == "limit":
                _cap_reason = _chase_cap_reason(fallback_limit)
                if _cap_reason:
                    await _skip_chase_capped(_cap_reason, "order_failed")
                    return None
            # New COID for retry so client_order_id stays unique
            coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
            order = await _submit(entry_type, fallback_limit, coid)
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

        # #500: record the ACTUAL order placed. A limit fallback has no
        # trigger price and its limit is the latest-based fallback limit —
        # never write the bracket's legacy columns for it.
        await conn.execute("""
            INSERT INTO mi_live_orders
                (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                 stop_price, limit_price, status, raw_response)
            VALUES ($1, $2, $3, 'buy', $9, $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (alpaca_order_id) DO NOTHING
        """,
            trade_id, entry_order_id, ticker,
            float(trade["entry_shares"]),
            None if entry_type == "limit" else float(trade["orb_high"]),
            fallback_limit if entry_type == "limit"
            else stop_limit_buy_price(float(trade["orb_high"])),
            order["status"],
            json.dumps(order),
            entry_type,
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
            SELECT id, ticker, entry_order_id, entry_shares, orb_low, orb_high,
                   stop_price, entry_attempt, account_mode
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

            # Find the stop-loss order leg. REST-refetch fallback (money-path audit
            # 2026-07-12 R6): the polling payload can omit legs exactly like the
            # submit response — submit_entry and _process_entry_fill both refetch on
            # a miss; this path previously wrote COALESCE(NULL, …) = a no-op and
            # left the pointer NULL until the reconcile repaired it.
            stop_order_id = alpaca.extract_stop_leg_id(order)
            if not stop_order_id:
                _refetched = await alpaca.get_order(trade["entry_order_id"], account_mode=account_mode)
                if _refetched:
                    stop_order_id = alpaca.extract_stop_leg_id(_refetched)

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
                # AND status='order_placed' + rowcount check (audit R1 sibling):
                # if the WS handler already claimed/processed this fill, the
                # polling backup must NOT re-write the row (was: unconditional
                # overwrite + a DUPLICATE fill Telegram).
                _res = await conn.execute("""
                    UPDATE mi_live_trades SET
                        status = 'filled',
                        entry_price = $2,
                        entry_shares = $3,
                        remaining_shares = $3,
                        stop_price = $4,
                        filled_at = NOW(),
                        stop_order_id = COALESCE($5, stop_order_id)
                    WHERE id = $1 AND status = 'order_placed'
                """, trade["id"], filled_price, filled_qty, float(trade["stop_price"]), stop_order_id)
                if _res == "UPDATE 0":
                    logger.info(f"check_fills: {ticker} already processed (WS won) — skipping")
                    continue

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
                f"{mode_prefix(account_mode)}✅ *FILLED:* {ticker} (attempt {trade.get('entry_attempt', 1)})\n"
                f"Entry: ${filled_price:.2f} × {filled_qty:.0f} shares\n"
                f"Stop: ${trade['stop_price']:.2f}"
            )
            logger.info(f"Fill: {ticker} @${filled_price:.2f} x{filled_qty:.0f}")
            results.append({"ticker": ticker, "action": "filled", "price": filled_price})

        elif status in _CANCEL_LIKE_ORDER_STATUSES:
            # #500 reason capture (polling backup path): never write the bare
            # broker status — synthesize the price-vs-trigger diagnosis.
            skip_reason = await broker_terminal_reason(
                status, ticker, trade.get("orb_high"),
            )
            await _update_trade_status(trade["id"], "cancelled", skip_reason=skip_reason)
            logger.info(f"Order {status}: {ticker} ({skip_reason})")
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

    # Kill-switch + manual-halt gates (money-path audit 2026-07-12, R2). Re-entry
    # SUBMITS a real order and previously bypassed BOTH switches (submit_entry has
    # them; this path did not). Latent while R3_DAY1_REENTRY_ENABLED stays false —
    # these gates are the precondition for ever enabling it. Same pattern as
    # submit_entry: LIVE_TRADING_ENABLED kills all submits; /pause halts live only
    # ('unreadable' fails SAFE — capital protection, distinct reason in the audit).
    if not LIVE_TRADING_ENABLED:
        logger.warning(f"attempt_day1_reentry {trade_id}: blocked — LIVE_TRADING_ENABLED=false")
        await log_audit_event(
            "reentry_blocked_by_kill_switch",
            f"{ticker} trade {trade_id}: day-1 re-entry blocked — LIVE_TRADING_ENABLED=false",
            json.dumps({"trade_id": trade_id, "account_mode": account_mode}),
        )
        return {"ticker": ticker, "action": "reentry_blocked_kill_switch"}
    if account_mode == "live":
        _halt = await get_manual_halt_state()
        if _halt in ("on", "unreadable"):
            logger.warning(f"attempt_day1_reentry {trade_id}: blocked by manual trading halt ({_halt})")
            await log_audit_event(
                "reentry_blocked_by_halt",
                f"{ticker} trade {trade_id}: day-1 re-entry blocked — manual trading halt ({_halt})",
                json.dumps({"trade_id": trade_id, "halt_state": _halt}),
            )
            return {"ticker": ticker, "action": "reentry_blocked_halt"}

    entry_price = trade["entry_price"]
    shares = trade["remaining_shares"]
    orb_high = trade["orb_high"]
    orb_low = trade["orb_low"]
    stop_loss_price = trade["stop_price"]

    # Record the stop-out exit
    pnl = (stop_fill_price - entry_price) * shares if entry_price else 0
    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")
    exits.append({
        "time": datetime.now(timezone.utc).isoformat(),
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
            """, trade["id"], exits, total_pnl_so_far)
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
            """, trade["id"], exits, total_pnl_so_far)
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
            """, trade["id"], exits, total_pnl_so_far,
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
        # broker-confirmed: the closed/NULL demotion records the Day-1 stop FILL the
        # CALLER already confirmed at the broker (_check_day1_reentry only proceeds on
        # get_order status=='filled'; the WS path IS the fill event) — position flat,
        # stop leg consumed. This except only aborts the re-entry attempt; it demotes
        # nothing inferred from the failure itself. Residual: an ambiguous-accept
        # re-entry order (raised after broker acceptance) is untracked → #184(b)
        # broker-order ingest / 15-min reconcile is the catcher.
        total_pnl = sum(ex.get("pnl", 0) for ex in exits)
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'closed', exits = $2::jsonb,
                    remaining_shares = 0, total_pnl = $3,
                    stop_order_id = NULL, closed_at = NOW(),
                    entry_attempt = $4
                WHERE id = $1
            """, trade["id"], exits, total_pnl, attempt)
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
            attempt, exits, total_pnl_after_stop)

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


_STOP_ID_UNSET = object()  # sentinel: expected_prior not supplied (distinct from a real None prior)


async def set_stop_order_id(
    trade_id: int,
    new_id: str | None,
    *,
    reason: str,
    account_mode: str,
    expected_prior=_STOP_ID_UNSET,
) -> bool:
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
      - 'ingest_r1_repair'         #184b broker-order ingest repaired a NULL/dead stop pointer

    `expected_prior` (optional): a NO-OVERWRITE compare-and-set. When supplied, the update applies
    ONLY if the current stop_order_id IS NOT DISTINCT FROM it — race-safe, never clobber a pointer a
    concurrent write just moved (the #184b ingest R1 guard). Returns True if the row was updated,
    False if the guard blocked it. Without it: unconditional set, always returns True (existing
    callers ignore the return). Emits `stop_order_id_changed` only when it actually wrote.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if expected_prior is _STOP_ID_UNSET:
            await conn.execute(
                "UPDATE mi_live_trades SET stop_order_id = $1 WHERE id = $2", new_id, trade_id)
            applied = True
        else:
            applied = await conn.fetchval(
                "UPDATE mi_live_trades SET stop_order_id = $1 "
                "WHERE id = $2 AND stop_order_id IS NOT DISTINCT FROM $3 RETURNING id",
                new_id, trade_id, expected_prior) is not None
    if applied:
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
    return applied


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
        # #433 (2026-07-06, WULF): do NOT cry "NO stop protection" on the FIRST
        # attempt — a retry fires in 3s and usually succeeds (the OTO-leg-vs-
        # refresh conflict class: the old stop often still holds the shares this
        # instant, so attempt-1 gets insufficient-qty then attempt-2 wins). A
        # loud naked alarm here is a FALSE positive the operator cannot tell
        # apart from a real one. The loud alarm now fires ONLY if the retry ALSO
        # fails (the genuinely-naked case below). Attempt-1 failure = log + audit.
        logger.warning(
            f"{ticker}: first stop-place attempt failed ({type(e).__name__}) — retrying in 3s"
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
            # #433: CONFIRM to the operator — the position IS protected. Without
            # this, a prior transient concern (or the WS stop-cancel alert) is
            # never retracted and the operator believes the position is naked.
            await send_telegram_message(
                f"{mode_prefix(account_mode)}✅ *Stop confirmed:* {ticker} @ ${new_stop_price:.2f}\n"
                f"_Placed on retry after a transient conflict — position protected._"
            )
        except Exception as e2:
            logger.error(f"Stop re-placement also failed for {ticker}: {e2}")
            # Null stop_order_id so sync_positions Path C (4:05 PM + 9:00 PM)
            # can detect the orphan and remediate. Leaving the stale ID in place
            # silently masks the naked state and blocks Path C's orphan check.
            # broker-confirmed: the old-stop cancel was a real broker call (cancel_ok
            # recorded in the audit payload) and BOTH placements raised — no live stop
            # we can point at. When cancel_ok=False the old stop's state is ambiguous;
            # NULL is the DELIBERATE FAIL-SAFE direction (assume naked → Path C
            # remediates to broker truth) per ADR 0008's escape clause — the stale
            # pointer alternative masks possible nakedness.
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
            # #433: THIS is the genuinely-naked case (BOTH attempts failed) — it
            # was audit-only before, so the real emergency was quieter than the
            # false attempt-1 alarm. Alarm LOUD here: this is the one that means it.
            await send_telegram_message(
                f"{mode_prefix(account_mode)}🚨 *STOP FAILED — position NAKED:* {ticker}\n"
                f"Both attempts to place @ ${new_stop_price:.2f} failed ({type(e2).__name__}).\n"
                f"{float(trade['remaining_shares']):.0f} sh unprotected — remediation runs at 4:05 PM ET."
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


# Outcome-history circuit breaker (#151 c). If recent partial-exit attempts have
# failed at the broker-interaction stages, refuse further unattended attempts and
# alert the operator rather than let a scheduled cron retry into the same fault
# every day (the IBM 2026-05-27/28 shape: two days of silent same-trade failures).
_PARTIAL_EXIT_BREAKER_THRESHOLD = 3
_PARTIAL_EXIT_BREAKER_WINDOW_DAYS = 7
# UN-PAUSED 2026-06-23 (operator sign-off): the #151 durable fix is shipped + verified.
# The pending_replace-race that forced the 2026-06-22 pause is fixed at the ROOT:
#  (1) a Postgres advisory lock on trade_id serializes the (CROSS-PROCESS) partial vs
#      the never-naked reconciler — proven on the real prod DB (an asyncio.Lock was a
#      no-op given the EXECUTION_MODE=http service split);
#  (2) the rollback/cancel block is GONE — never cancel a pending_replace (uncancelable
#      while pending, G6-confirmed);
#  (3) ALL 3 abort paths re-protect IMMEDIATELY in-process via _ensure_stop_coverage
#      (no naked window — does NOT wait for the EOD-cadence sync net).
# Validated end-to-end on the REAL paper broker (scripts/_partial_exit_paper_validation.py:
# clean partial 6→4 + forced-abort re-protect 4→6, zero naked / zero sold / zero cancel).
# Tests monkeypatch this. (Pause history: QURE 6/22, FPS 6/04, IBM 5/27 — #151 / ADR 0009.)
_PARTIAL_EXIT_PAUSED = False


async def _consecutive_partial_exit_failures(floor_days: int = _PARTIAL_EXIT_BREAKER_WINDOW_DAYS) -> int:
    """Count GENUINE partial-exit failures SINCE THE LAST SUCCESSFUL partial exit.

    Success-aware breaker semantics (advisor 2026-05-29): a clean
    `partial_exit_committed` closes the breaker — only failures accrued *after*
    the most recent success count. This is the standard open→half-open→close
    model; a rolling fixed-window (the prior implementation) would stay open on
    stale already-remediated failures even after clean cycles resumed. `floor_days`
    bounds the lookback when there is NO recorded success yet (fresh system / never
    succeeded), so ancient history can't trip it.

    Counts only broker-interaction failures — NOT benign aborts (dedup against a
    pending exit, trade-not-found), which share the `partial_exit_aborted`
    event_type but carry a non-failure `stage`. Genuine signals:
      - partial_exit_sell_failed       (market sell raised)
      - partial_exit_rollback_failed   (sell failed AND stop rollback failed)
      - partial_exit_aborted with stage in {place_new_stop, verify_stop_live}
        (replacement stop failed / confirmed dead before sell)
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n FROM mi_audit_log
            WHERE created_at > COALESCE(
                    (SELECT MAX(created_at) FROM mi_audit_log
                     WHERE event_type = 'partial_exit_committed'),
                    NOW() - ($1 || ' days')::interval
                  )
              AND (
                event_type IN ('partial_exit_sell_failed', 'partial_exit_rollback_failed')
                OR (
                  event_type = 'partial_exit_aborted'
                  AND (detail LIKE '%"stage": "place_new_stop"%'
                       OR detail LIKE '%"stage": "verify_stop_live"%')
                )
              )
            """,
            str(floor_days),
        )
    return int(row["n"]) if row else 0


def _is_share_reservation_lag(err: Exception) -> bool:
    """#150: after an atomic stop-replace frees shares, Alpaca's
    held_for_orders can lag the replace ack by ~ms, so an immediate market
    sell transiently rejects with "insufficient qty available" (confirmed
    2026-05-29). True = that retryable race. Deliberately narrow: it matches
    only a clean REJECTION (no order was placed → retry can't oversell), NOT a
    network timeout/ambiguous error (which must fall through to rollback)."""
    msg = str(err).lower()
    return (
        "insufficient" in msg
        or "held_for_orders" in msg
        or "qty available" in msg
    )


# ── #151 cross-PROCESS trade-state lock (advisory, DB-global) ─────────────────
# execute_partial_exit and _ensure_stop_coverage run in DIFFERENT PROCESSES in
# production (service split, EXECUTION_MODE=http — the partial is HTTP-triggerable
# cross-container). An asyncio.Lock is a no-op across processes. A Postgres
# *advisory* lock IS process-global: it serializes the partial (which reduces the
# stop) against the reconciler's coverage repair (_ensure_stop_coverage), so the
# reconciler can never "repair" a stop the partial is mid-flight reducing — the
# race that produced the under-covering/naked window (FPS/QURE/IBM).
#
# Two-int form pg_advisory_lock(classid, objid): a fixed namespace constant +
# trade_id. Session-level (NOT xact) so it's held across our own commits and
# auto-released the instant the dedicated connection closes — the backstop if a
# process dies mid-hold. We take a DEDICATED pooled connection and hold it for
# the lock's lifetime, releasing the lock + the connection in finally.
#
# Non-re-entrant by design: each call site acquires the lock for `trade_id`
# exactly ONCE and releases before doing anything that could acquire it again
# (the abort re-protect calls _ensure_stop_coverage only AFTER releasing). So
# there is no self-deadlock; the DB-global lock only ever serializes the
# cross-process partial-vs-reconciler pair.
_TRADE_LOCK_NAMESPACE = 0x504152  # "PAR" — fits int4; arbitrary fixed namespace


@asynccontextmanager
async def _trade_advisory_lock(trade_id: int):
    """BLOCKING session-level advisory lock on (namespace, trade_id).

    Acquires a dedicated connection from the pool, blocks until the lock is held
    (`pg_advisory_lock`), yields, then unlocks + releases the connection in
    `finally`. Session-level → if this process dies the lock auto-releases when
    the connection closes (backstop). Used by execute_partial_exit at the TOP.
    """
    pool = await get_pool()
    conn = await pool.acquire()
    locked = False
    try:
        await conn.fetchval(
            "SELECT pg_advisory_lock($1, $2)",
            _TRADE_LOCK_NAMESPACE, int(trade_id),
        )
        locked = True
        yield
    finally:
        try:
            if locked:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock($1, $2)",
                    _TRADE_LOCK_NAMESPACE, int(trade_id),
                )
        finally:
            await pool.release(conn)


@asynccontextmanager
async def _trade_advisory_try_lock(trade_id: int):
    """NON-BLOCKING session-level advisory lock on (namespace, trade_id).

    Yields True if the lock was acquired (caller proceeds), False if another
    holder has it (caller SKIPS). Unlocks + releases the connection in `finally`.
    Used by _ensure_stop_coverage so the reconciler defers to an in-flight
    partial rather than repairing a stop mid-reduction.
    """
    pool = await get_pool()
    conn = await pool.acquire()
    acquired = False
    try:
        acquired = bool(await conn.fetchval(
            "SELECT pg_try_advisory_lock($1, $2)",
            _TRADE_LOCK_NAMESPACE, int(trade_id),
        ))
        yield acquired
    finally:
        try:
            if acquired:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock($1, $2)",
                    _TRADE_LOCK_NAMESPACE, int(trade_id),
                )
        finally:
            await pool.release(conn)


async def execute_partial_exit(
    trade_id: int, shares: int, *, force: bool = False,
) -> bool:
    """
    Partial exit (1/3 sell). Replaces stop for remaining 2/3 first so the
    position is always protected. On sell failure, rolls the stop back to
    the full original qty.

    force=True bypasses the outcome-history circuit breaker (#151 c) — used by
    the operator-confirmed /partialnow command (an attended action). The
    scheduled cron path passes force=False so a string of recent failures pauses
    automatic retries instead of re-failing into the same fault daily.
    """
    # ── HARD PAUSE (#151, 2026-06-22) — disabled until the pending_replace-race
    # fix is verified-live. Take NO partial (no stop touch): the position keeps its
    # full stop + size, strictly safer than the looping/under-covering broken path.
    if _PARTIAL_EXIT_PAUSED:
        logger.warning(
            f"execute_partial_exit: PAUSED (#151 race fix pending) — trade {trade_id} "
            f"keeps full stop+size, no partial taken (force={force})"
        )
        await log_audit_event(
            "partial_exit_paused",
            f"partial-exit PAUSED (#151 pending_replace-race fix pending) — trade "
            f"{trade_id} keeps full stop + full size, no partial taken",
            json.dumps({"trade_id": trade_id, "shares": int(shares), "force": force}),
        )
        return False

    # Circuit breaker (#151 c): if partial-exit attempts have failed at the
    # broker-interaction stages SINCE THE LAST SUCCESSFUL partial, refuse this
    # UNATTENDED attempt and alert. Success-aware (advisor 2026-05-29): a clean
    # partial_exit_committed resets the count, so resumed clean cycles close the
    # breaker rather than staying open on stale already-remediated failures.
    # Skipped when force=True (operator chose to act); the override is recorded.
    fail_count = await _consecutive_partial_exit_failures()
    if fail_count >= _PARTIAL_EXIT_BREAKER_THRESHOLD:
        if not force:
            logger.error(
                f"execute_partial_exit: circuit breaker OPEN "
                f"({fail_count} consecutive failures since last success) "
                f"— refusing trade {trade_id}"
            )
            await log_audit_event(
                "partial_exit_circuit_open",
                f"breaker OPEN: {fail_count} partial-exit failures since last "
                f"success — trade {trade_id} skipped",
                json.dumps({
                    "trade_id": trade_id, "shares": int(shares),
                    "consecutive_failures": fail_count,
                    "threshold": _PARTIAL_EXIT_BREAKER_THRESHOLD,
                }),
            )
            await send_telegram_message(
                f"🛑 *Partial-exit circuit breaker OPEN*\n"
                f"{fail_count} partial-exit failures since the last clean exit — "
                f"automatic partial exits are PAUSED to stop retries into the same "
                f"fault.\n\n"
                f"Trade {trade_id} was skipped. Investigate (`show errors 7d`), then "
                f"`/partialnow TICKER CONFIRM` to act manually (bypasses the breaker "
                f"+ a clean run closes it)."
            )
            return False
        # force=True: operator override — record it but proceed.
        logger.warning(
            f"execute_partial_exit: circuit breaker OPEN ({fail_count} consecutive "
            f"failures) — OVERRIDDEN (force=True) for trade {trade_id}"
        )
        await log_audit_event(
            "partial_exit_circuit_overridden",
            f"breaker open ({fail_count} failures since last success) but "
            f"force=True — trade {trade_id} proceeding",
            json.dumps({
                "trade_id": trade_id, "shares": int(shares),
                "consecutive_failures": fail_count,
            }),
        )

    # ── #151 cross-PROCESS serialization (advisory lock on trade_id) ─────────
    # Hold a DB-global advisory lock for this trade_id across the entire stop-
    # reduce → verify → sell sequence so the reconciler's _ensure_stop_coverage
    # (which runs in a DIFFERENT process under EXECUTION_MODE=http) cannot repair
    # a stop we are mid-reducing. An asyncio.Lock would be a no-op cross-process;
    # this is process-global. Released on CM exit (below), BEFORE the abort
    # re-protect (which itself takes the try-lock on this trade_id).
    abort_reprotect = False
    abort_ctx: dict = {}
    async with _trade_advisory_lock(trade_id):
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

        # Step 1: Atomically REPLACE stop with reduced qty. Replace is race-free
        # vs cancel+new (IBM 2026-05-27 false-naked: 43ms between cancel + new
        # submit; Alpaca's share-reservation system hadn't cleared so the new
        # stop was rejected with "insufficient qty available" — held_for_orders
        # = 26). Alpaca's replace_order_by_id is atomic broker-side: no share
        # release window.
        new_stop_id = None
        if old_stop_id and stop_price and new_remaining > 0:
            # Same-window retry (#136 follow-through). replace_order is atomic
            # so the original cancel-new race shouldn't recur, but other
            # transient broker failures (5xx, network blip) still warrant
            # a single same-tick retry before aborting. Skipping methodology
            # window costs an extra trading day at next-open price — too
            # expensive vs a 1s wait + retry.
            new_stop_order = None
            last_err: Exception | None = None
            for attempt in (1, 2):
                try:
                    coid_stop = alpaca.make_client_order_id(
                        account_mode, signal_type, ticker,
                    )
                    new_stop_order = await alpaca.replace_order(
                        old_stop_id,
                        qty=new_remaining,
                        stop_price=float(stop_price),
                        account_mode=account_mode,
                        client_order_id=coid_stop,
                    )
                    break
                except Exception as e:
                    last_err = e
                    logger.warning(
                        f"execute_partial_exit: replace attempt {attempt} failed "
                        f"for {ticker}: {e}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(1.5)
            try:
                if new_stop_order is None:
                    raise last_err if last_err else RuntimeError("replace_order unreached")
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
                # Replacement stop failed. CRITICAL: replace_order_by_id is ATOMIC —
                # a REJECTED replace (validation error like sub-penny stop, or a
                # pre-HTTP Pydantic failure) leaves the ORIGINAL stop (old_stop_id)
                # LIVE and unchanged broker-side. The old handler assumed
                # "old cancelled → naked" and fired a 🚨 manual-stop alert; that is a
                # FALSE naked (RCAT 2026-06-01: sub-penny 11.955 rejected, original
                # 11.96 stop intact the whole time — exact shape this fn's L445-451
                # comment already documented for the str(qty) trigger). Verify the
                # old stop on the broker BEFORE alarming. No sell has happened yet.
                logger.error(f"execute_partial_exit: replacement stop failed for {ticker}: {e}")
                old_stop_live = False
                if old_stop_id:
                    try:
                        _chk = await alpaca.get_order(old_stop_id, account_mode=account_mode)
                        _old_status = _canonical_order_status(_chk.get("status") if _chk else None)
                        old_stop_live = _old_status in _STOP_CONFIRMED_LIVE_STATUSES
                    except Exception as _verr:
                        logger.warning(
                            f"execute_partial_exit: could not verify old stop {old_stop_id} "
                            f"for {ticker} after replace failure: {_verr}"
                        )
                if old_stop_live:
                    # Atomic replace was rejected → original stop still protects the
                    # full position. NOT naked. Keep stop_order_id, abort cleanly,
                    # retry next window. Calm message (no manual-stop call to action,
                    # which would create a duplicate-stop oversell).
                    await log_audit_event(
                        "partial_exit_aborted",
                        f"{ticker}: replacement stop rejected ({type(e).__name__}); "
                        f"original stop {old_stop_id} still LIVE — position protected, no action",
                        json.dumps({
                            "trade_id": trade_id, "ticker": ticker,
                            "old_stop_id": old_stop_id, "new_remaining": new_remaining,
                            "stop_price": float(stop_price), "stage": "place_new_stop",
                            "old_stop_intact": True, "error": str(e)[:500],
                        }),
                    )
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}⚠️ Partial exit skipped for {ticker}: "
                        f"replacement stop rejected ({type(e).__name__}).\n"
                        f"_Original stop still live — position protected, no shares sold. "
                        f"Cron will retry next window._"
                    )
                    return False
                # Old stop NOT confirmed live → genuine naked risk.
                # broker-confirmed: reached only after the alpaca.get_order(old_stop_id)
                # read above set old_stop_live=False — i.e. the broker itself confirmed
                # the old stop is not in a live status. This is the #151 verify-stop-live
                # fix; the null is broker-evidenced, not inferred.
                #
                # #151 (2026-06-23) IMMEDIATE in-process re-protect (mirrors the
                # sell-failure path below): no sell has happened, but the position is
                # now under-covered (dead stop). NULL the stale DB pointer (it points
                # at a dead order — the invariant is "stop_order_id never points at a
                # dead order", which makes nulling correct HERE even though the
                # sell-fail path must NOT null its still-live reduced stop), then set
                # abort_reprotect so the post-lock block (AFTER the advisory lock
                # releases) re-protects to BROKER TRUTH via _ensure_stop_coverage —
                # closing the naked window in sub-second instead of waiting for the
                # next sync cron. Do NOT null+return-inside-the-lock (the old behavior
                # leaned on the slow net) and do NOT send the inline 🚨 alert / the
                # "sync_positions will remediate" audit — the post-lock block owns the
                # single Telegram, and in-process re-protect is now the remediator.
                await set_stop_order_id(
                    trade_id, None,
                    reason="partial_naked",
                    account_mode=account_mode,
                )
                await log_audit_event(
                    "partial_exit_aborted",
                    f"{ticker}: replacement stop failed AND old stop not live — "
                    f"under-covered, re-protecting in-process ({type(e).__name__})",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker,
                        "old_stop_id": old_stop_id, "new_remaining": new_remaining,
                        "stop_price": float(stop_price), "stage": "place_new_stop",
                        "stale_stop_id_cleared": old_stop_id,
                        "error": str(e)[:500],
                    }),
                )
                abort_reprotect = True
                abort_ctx = {
                    "error": str(e),
                    "reason": (
                        f"replacement stop rejected ({type(e).__name__}), "
                        f"old stop confirmed dead"
                    ),
                }

        # Step 1b: VERIFY the replacement stop is actually live on the broker
        # BEFORE freeing shares via the market sell. A replace can return a new
        # order_id that the broker then rejects/cancels — "looked successful,
        # actually dead". G6 guards that shape at deploy time; this is its runtime
        # analog on the production path. Selling against a dead stop = naked.
        #
        # Tolerate the pending_replace → new settling window (≤~1s observed) so we
        # don't manufacture a false-naked on a stop that's merely still settling
        # (the lesson the paper-Alpaca harness taught us 2026-05-29). Poll a short
        # budget, then classify: live → sell; dead → abort+null+remediate; still
        # pending after budget → abort WITHOUT nulling (keep the best-guess stop,
        # ask operator to verify) since we have NOT sold and the stop likely lives.
        #
        # `not abort_reprotect` guard: if the replace-failed path above already
        # flagged an abort while leaving a non-None new_stop_id (replace succeeded
        # but the subsequent persist/INSERT raised), don't re-verify here — the
        # post-lock block already owns the re-protect.
        if new_stop_id and not abort_reprotect:
            verify_status = None
            verify_outcome = "uncertain"  # live | dead | uncertain
            for _ in range(12):  # ~3s budget at 0.25s/poll
                chk = await alpaca.get_order(new_stop_id, account_mode=account_mode)
                verify_status = _canonical_order_status(chk.get("status") if chk else None)
                if verify_status in _STOP_CONFIRMED_LIVE_STATUSES:
                    verify_outcome = "live"
                    break
                if verify_status in _STOP_DEAD_STATUSES or verify_status == "filled":
                    verify_outcome = "dead"
                    break
                await asyncio.sleep(0.25)

            if verify_outcome != "live":
                logger.error(
                    f"execute_partial_exit: replacement stop {new_stop_id} for {ticker} "
                    f"not confirmed live before sell (outcome={verify_outcome}, "
                    f"last_status={verify_status}) — aborting sell"
                )
                if verify_outcome == "dead":
                    # Stop is gone broker-side → position under-covered. NULL the stale
                    # DB pointer (it points at a dead order) then re-protect IN-PROCESS
                    # via the post-lock block (#151, 2026-06-23) — same shape as the
                    # replacement-rejected path above and the sell-failure path below.
                    # Previously this nulled + returned inside the lock and leaned on
                    # the next sync cron; now we route to the immediate re-protect
                    # (closes the naked window sub-second). Drop the inline 🚨 alert +
                    # the "sync_positions will remediate" audit — the post-lock block
                    # owns the single Telegram and is itself the remediator.
                    await set_stop_order_id(
                        trade_id, None,
                        reason="partial_verify_stop_dead",
                        account_mode=account_mode,
                    )
                    await log_audit_event(
                        "partial_exit_aborted",
                        f"{ticker}: replacement stop confirmed DEAD before sell "
                        f"(status={verify_status}) — re-protecting in-process",
                        json.dumps({
                            "trade_id": trade_id, "ticker": ticker,
                            "new_stop_id": new_stop_id, "new_remaining": new_remaining,
                            "stop_price": float(stop_price) if stop_price else None,
                            "stage": "verify_stop_live", "verify_outcome": verify_outcome,
                            "last_status": verify_status,
                            "stale_stop_id_cleared": new_stop_id,
                        }),
                    )
                    abort_reprotect = True
                    abort_ctx = {
                        "error": f"replacement stop dead before sell (status={verify_status})",
                        "reason": "replacement stop dead before sell",
                    }
                    # Fall through to the post-lock re-protect (NO return inside the
                    # lock — _ensure_stop_coverage takes the try-lock on this trade_id).
                else:
                    # Uncertain (still pending after budget). We did NOT sell, so the
                    # full position is intact. Keep new_stop_id persisted (it likely
                    # IS live, just slow to settle) rather than null it and trigger a
                    # false-naked that could cancel a good stop. Ask operator to eyeball.
                    # This branch keeps returning False inside the lock — the stop is
                    # kept (safe / over-covered), nothing to re-protect.
                    await log_audit_event(
                        "partial_exit_aborted",
                        f"{ticker}: replacement stop not confirmed live within budget "
                        f"(status={verify_status}) — sell skipped, stop kept",
                        json.dumps({
                            "trade_id": trade_id, "ticker": ticker,
                            "new_stop_id": new_stop_id, "new_remaining": new_remaining,
                            "stop_price": float(stop_price) if stop_price else None,
                            "stage": "verify_stop_live", "verify_outcome": verify_outcome,
                            "last_status": verify_status,
                        }),
                    )
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}⚠️ Partial exit SKIPPED for {ticker}: "
                        f"replacement stop not confirmed live (status={verify_status}).\n"
                        f"No shares sold; stop {new_stop_id[:8]} kept for {new_remaining} sh. "
                        f"_Verify on Alpaca; cron will retry next window._"
                    )
                    return False

            if not abort_reprotect:
                logger.info(
                    f"execute_partial_exit: replacement stop {new_stop_id} for {ticker} "
                    f"confirmed live (status={verify_status}) — proceeding to sell"
                )

        # Step 1c (#151 Phase 1, docs/decisions/0009): VERIFY the shares are
        # actually FREE before selling. A live new stop (Step 1b) is NOT enough —
        # the OLD stop can stay stuck in `pending_replace` and keep reserving the
        # whole position even after replace_order returns a live new order (FPS
        # 2026-06-04/05: new 109 stop live, old 163 stop stuck pending_replace →
        # qty_available=0 → sell rejected "insufficient qty" → false-naked +
        # starved rollback). "New stop is live" passed both days and it still
        # broke. Poll the broker's qty_available until it covers the partial; if
        # it never frees within budget, ABORT BEFORE SELLING — the position is
        # OVER-covered (safe), not naked. Keep the stop, retry next window.
        # ── #151 (2026-06-23): SKIP all broker-acting steps when an abort
        # was flagged above (paths #1 replacement-rejected-old-dead / #2
        # verify-stop-dead). Without this guard, control would fall through
        # into the qty-available poll + the MARKET SELL below — placing a real
        # sell AFTER a stop failure (strictly worse than aborting). The
        # post-lock block re-protects to broker truth once the lock releases.
        if not abort_reprotect:
            avail_ok = False
            last_avail = None
            for _ in range(12):  # ~3s budget at 0.25s/poll
                _pos = await alpaca.get_position(ticker, account_mode=account_mode)
                last_avail = _pos.get("qty_available") if _pos else None
                if last_avail is not None and last_avail >= shares:
                    avail_ok = True
                    break
                await asyncio.sleep(0.25)
            if not avail_ok:
                logger.error(
                    f"execute_partial_exit: {ticker} qty_available={last_avail} < {shares} "
                    f"after budget — old stop likely still reserving shares "
                    f"(pending_replace limbo); aborting BEFORE sell (over-covered, safe)"
                )
                await log_audit_event(
                    "partial_exit_aborted",
                    f"{ticker}: shares not free (qty_available={last_avail} < {shares}) — "
                    f"sell skipped, position over-covered (safe), retry next window",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker, "shares": shares,
                        "qty_available": last_avail, "new_remaining": new_remaining,
                        "new_stop_id": new_stop_id, "old_stop_id": old_stop_id,
                        "stage": "verify_shares_free",
                    }),
                )
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}⚠️ Partial exit SKIPPED for {ticker}: "
                    f"shares not free to sell (available {last_avail} < {shares}).\n"
                    f"_Old stop likely still settling (pending_replace) — position "
                    f"protected, no shares sold. Cron will retry next window._"
                )
                return False

            # Step 2: Market sell the partial (shares are now free from the stop).
            try:
                coid_sell = alpaca.make_client_order_id(account_mode, signal_type, ticker)
                # #150: the atomic replace frees the shares, but Alpaca's share-hold
                # (held_for_orders) can lag the replace ack by ~ms, so an immediate
                # sell transiently rejects with "insufficient qty available" (confirmed
                # 2026-05-29). Retry that SPECIFIC clean rejection a few times with
                # backoff before the outer except rolls the partial back. Fresh COID
                # per attempt avoids dup-COID rejection. Non-lag errors re-raise
                # immediately (no retry) so genuine failures still roll back fast.
                order = None
                for _attempt in range(3):
                    try:
                        order = await alpaca.place_market_sell(
                            ticker, shares,
                            account_mode=account_mode, client_order_id=coid_sell,
                        )
                        break
                    except Exception as _se:
                        if _is_share_reservation_lag(_se) and _attempt < 2:
                            logger.warning(
                                f"execute_partial_exit: {ticker} sell hit share-reservation "
                                f"lag (attempt {_attempt + 1}/3): {_se} — retry in 0.5s"
                            )
                            await asyncio.sleep(0.5)
                            coid_sell = alpaca.make_client_order_id(
                                account_mode, signal_type, ticker,
                            )
                            continue
                        raise
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
                # CONVERGE, don't loop (#151 durable fix, 2026-06-23). The market sell
                # raised AFTER we reduced the stop to `new_remaining` but BEFORE any
                # shares sold — so the broker now has a reduced stop (`new_remaining`,
                # e.g. 134) resting under a STILL-FULL position (`full_remaining`, e.g.
                # 200). That is UNDER-covered: the un-sold shares (200−134=66) are
                # NAKED until we re-protect. The OLD rollback block here (cancel the
                # reduced stop → place a full-qty stop → null on failure) is GONE: it
                # re-replaced into the SAME pending_replace race that broke this path
                # repeatedly (QURE 6/22, FPS 6/04, IBM 5/27), and cancelling a
                # `pending_replace` stop is exactly the move that widened the naked
                # window. Instead: abort cleanly, leave the reduced stop UNTOUCHED
                # (never cancel a pending_replace, never null stop_order_id), set a
                # flag, and the instant the advisory lock releases (CM exit below)
                # re-protect to broker truth via _ensure_stop_coverage IN-PROCESS —
                # closing the naked window in sub-second, not at the next sync cron.
                logger.error(f"Partial exit sell failed for {ticker} after stop reduced: {e}")
                await log_audit_event(
                    "partial_exit_sell_failed",
                    f"{ticker}: market sell raised — {type(e).__name__}; aborting, "
                    f"re-protecting to broker truth (no rollback, no cancel)",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker,
                        "shares": shares, "new_stop_id": new_stop_id,
                        "full_remaining": full_remaining,
                        "stop_price": float(stop_price) if stop_price else None,
                        "error": str(e)[:500],
                    }),
                )
                # Defer the SINGLE Telegram + the in-process re-protect to AFTER the
                # advisory lock releases (the lock CM exits below) — _ensure_stop_coverage
                # takes the try-lock on the same trade_id and would SKIP if we still held
                # it. abort_ctx carries everything the post-lock re-protect needs.
                abort_reprotect = True
                abort_ctx = {"error": str(e)}

        # Step 3: Pending fill — DO NOT commit P&L / remaining_shares / partial_taken
        # at submit time. The order may be queued (after-hours) and fill at next open
        # at an unknown price; using the placement-time response here meant fill_price
        # fell back to entry_price → printed P&L $0.00 on a sale that hadn't happened.
        # finalize_partial_exit() runs from the WS fill handler with the real fill price.
        # Skipped on the abort path (no sell placed) — that path re-protects + alerts
        # AFTER the advisory lock releases, below.
        if not abort_reprotect:
            await send_telegram_message(
                f"{mode_prefix(account_mode)}📋 *Partial exit order placed:* {ticker}\n"
                f"Market sell {shares} sh — pending fill (Order {order['id'][:8]})\n"
                f"_Confirms with real P&L on fill._"
            )
        # F14 (7/2 review): the former _*_out relay copies were a pure renaming
        # layer — Python `with` blocks don't create a scope, so the originals
        # (ticker/account_mode/signal_type/stop_price/abort_*) remain bound on
        # every path past the lock. The relays invited an in-lock edit that
        # forgets the relay line (a real post-lock/in-lock mismatch); post-lock
        # code now uses the original names directly.

    # ── Advisory lock RELEASED here (the `async with _trade_advisory_lock` CM
    # exits as control leaves the wrapped body above). Now — and ONLY now — is it
    # safe to call _ensure_stop_coverage, which takes the try-lock on this same
    # trade_id; calling it while we still held the lock would SKIP and leave the
    # position under-covered. The brief release→re-protect gap is benign:
    # _ensure_stop_coverage is idempotent, so if the sync cron also fires in that
    # window, whichever runs second sees coverage already == target and no-ops.
    if abort_reprotect:
        # IMMEDIATE re-protect to BROKER TRUTH (kills the latency gap vs the next
        # sync cron). Fetch the live total position qty — NOT DB full_remaining
        # (stale-DB → wrong-size order, the 109-vs-28 class) and NOT qty_available
        # (already nets held-for-orders → double-subtract). _ensure_stop_coverage
        # nets pending exits internally; the failed sell placed none, so target
        # resolves to the full position.
        coverage_msg = None
        try:
            _pos = await alpaca.get_position(ticker, account_mode=account_mode)
            _broker_qty = float(_pos.get("qty")) if _pos and _pos.get("qty") is not None else None
            if _broker_qty and _broker_qty > 0:
                coverage_msg = await _ensure_stop_coverage(
                    trade_id, ticker, _broker_qty,
                    float(stop_price) if stop_price else None,
                    signal_type or "unknown",
                    account_mode,
                )
            else:
                logger.warning(
                    f"execute_partial_exit: abort re-protect — no live broker position "
                    f"for {ticker} (qty={_broker_qty}); nothing to re-protect"
                )
        except Exception as _re:
            logger.error(
                f"execute_partial_exit: abort re-protect via _ensure_stop_coverage "
                f"raised for {ticker}: {_re}"
            )
            await log_audit_event(
                "partial_exit_reprotect_failed",
                f"{ticker}: in-process re-protect after sell-failure raised "
                f"({type(_re).__name__}) — next sync cron will remediate",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "error": str(_re)[:500],
                }),
            )
            coverage_msg = f"⚠️ re-protect call raised: {_re}"
        # ONE Telegram for the whole abort: the sell failure + the re-protect
        # outcome folded together (no separate alert from the except block above).
        # coverage_msg is None ONLY when _ensure_stop_coverage returned None — i.e.
        # it found coverage already == target (a partial already re-protected, or
        # the reconciler raced the try-lock) OR it couldn't read the broker
        # (get_open_orders failed) and deferred. The first is fine; the second
        # leaves the position UNDER-covered and unfixed, so the fallback must NOT
        # claim "safe" — it tells the operator to verify and that the sync cron is
        # the backstop.
        _cov_line = coverage_msg or (
            "_Re-protect deferred (coverage already met, or broker read failed) — "
            "verify the stop covers the full position on Alpaca; sync cron will "
            "reconcile._"
        )
        # Path-specific cause line. The sell-failure path sets only `error` (no sell
        # ran on the two stop-failure paths, so "sell failed" would lie there); those
        # set a `reason`. Prefer `reason`, else fall back to "sell failed (<error>)".
        _abort_reason = abort_ctx.get("reason")
        _cause_line = _abort_reason or f"sell failed ({abort_ctx.get('error', 'unknown')})"
        await send_telegram_message(
            f"{mode_prefix(account_mode)}⚠️ Partial exit ABORTED for {ticker}: "
            f"{_cause_line}.\n"
            f"No shares sold.\n{_cov_line}"
        )
        return False

    return True


async def finalize_partial_exit(
    trade_id: int,
    filled_qty: int,
    filled_price: float,
    order_id: str,
) -> None:
    """Public entry — serializes the whole read-modify-write under the per-trade
    #151 advisory lock (money-path audit 2026-07-12 R1: finalizers were the only
    trade-state writers OUTSIDE the lock; job-side writers already hold it)."""
    async with _trade_advisory_lock(trade_id):
        return await _finalize_partial_exit_locked(trade_id, filled_qty, filled_price, order_id)


async def _finalize_partial_exit_locked(
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
    account_mode = trade.get("account_mode") or current_account_mode()
    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")

    # Idempotency: a duplicate WS fill for the same order_id no-ops.
    if any(e.get("order_id") == order_id for e in exits):
        logger.info(f"finalize_partial_exit: {ticker} order {order_id[:8]} already committed")
        return

    shares = int(filled_qty)
    new_remaining = int(trade["remaining_shares"]) - shares
    pnl = (filled_price - trade["entry_price"]) * shares if trade["entry_price"] else 0

    exits.append({
        "time": datetime.now(timezone.utc).isoformat(),
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
        """, trade_id, exits, new_remaining, total_pnl)

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
        f"{mode_prefix(account_mode)}📤 *Partial exit FILLED:* {ticker}\n"
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
    """Public entry — serializes the whole read-modify-write under the per-trade
    #151 advisory lock (money-path audit 2026-07-12 R1: finalizers were the only
    trade-state writers OUTSIDE the lock; job-side writers already hold it)."""
    async with _trade_advisory_lock(trade_id):
        return await _finalize_full_exit_locked(trade_id, filled_qty, filled_price, order_id, reason)


async def _finalize_full_exit_locked(
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
    account_mode = trade.get("account_mode") or current_account_mode()
    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")

    if any(e.get("order_id") == order_id for e in exits):
        logger.info(f"finalize_full_exit: {ticker} order {order_id[:8]} already committed")
        return

    pnl = (filled_price - trade["entry_price"]) * filled_qty if trade["entry_price"] else 0

    exits.append({
        "time": datetime.now(timezone.utc).isoformat(),
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
        """, trade_id, exits, total_pnl)

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
        f"{mode_prefix(account_mode)}{emoji} *Closed:* {ticker} — {reason}\n"
        f"Exit @${filled_price:.2f} × {filled_qty:.0f} shares\n"
        f"Total P&L: ${total_pnl:+,.2f}"
    )


async def finalize_stop_fill(
    trade_id: int,
    filled_qty: int,
    filled_price: float,
    order_id: str,
) -> None:
    """Public entry — serializes the whole read-modify-write under the per-trade
    #151 advisory lock (money-path audit 2026-07-12 R1: finalizers were the only
    trade-state writers OUTSIDE the lock; job-side writers already hold it)."""
    async with _trade_advisory_lock(trade_id):
        return await _finalize_stop_fill_locked(trade_id, filled_qty, filled_price, order_id)


async def _finalize_stop_fill_locked(
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
    account_mode = trade.get("account_mode") or current_account_mode()
    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")

    if any(e.get("order_id") == order_id for e in exits):
        logger.info(f"finalize_stop_fill: {ticker} order {order_id[:8]} already committed")
        return

    pnl = (filled_price - trade["entry_price"]) * filled_qty if trade["entry_price"] else 0
    attempt = trade.get("entry_attempt", 1)

    exits.append({
        "time": datetime.now(timezone.utc).isoformat(),
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
        """, trade_id, exits, total_pnl)

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
        f"{mode_prefix(account_mode)}❌ *Stopped out:* {ticker} @${filled_price:.2f}\n"
        f"P&L: ${pnl:+,.2f} | shares: {filled_qty}"
    )


# ── EOD Cleanup ──────────────────────────────────────────────────────────────


async def expire_stale_proposals() -> int:
    """#436 self-heal — expire staged-paper trade PROPOSALS that outlived their
    ORB window. The staged path (phase=live + live_real_enabled=False) inserts a
    `pending_confirmation` row with NO broker order and waits for the operator's
    manual confirm; nothing ever expired the unconfirmed ones (the ABSI/FCEL/
    SNX/ACAD class sat 10-12 days until a hand cleanup on 7/06 — no standing
    reaper existed). A proposal for a PRIOR day's ORB is meaningless AND unsafe:
    a late manual confirm would submit an entry priced off a dead window.

    Expires pending_confirmation rows with proposed_at before TODAY (ET) —
    same-day proposals stay confirmable through the session. No broker calls
    (these rows have no orders); status → 'expired' + one audit row each.
    Called from both cleanup jobs (10:00 ET ORB-window + 4:05 PM EOD).

    Per-mode (review 7/17): iterates only the modes THIS container is
    authoritative for (the sync_positions idiom) — the dual-account backbone
    requires an account_mode filter on every trade query, and a paper-only dev
    container (ENABLE_LIVE_MODE=false) must never expire live-account rows.
    RAISES on failure — both callers wrap with notify_job_failure (an internal
    swallow made reaper breakage permanently invisible, the exact #436 class)."""
    from agents.market_intelligence.constants import ENABLE_LIVE_MODE
    modes = ["paper", "live"] if ENABLE_LIVE_MODE else ["paper"]
    pool = await get_pool()
    total = 0
    for mode in modes:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                UPDATE mi_live_trades
                   SET status = 'expired',
                       skip_reason = COALESCE(skip_reason, 'window:proposal_expired')  -- WINDOW_PROPOSAL_EXPIRED
                 WHERE account_mode = $1
                   AND status = 'pending_confirmation'
                   AND entry_order_id IS NULL
                   AND (proposed_at AT TIME ZONE 'America/New_York')::date
                       < (NOW() AT TIME ZONE 'America/New_York')::date
                RETURNING id, ticker, account_mode, proposed_at
            """, mode)
        for r in rows:
            await log_audit_event(
                "stale_proposal_expired",
                f"{r['ticker']} (id={r['id']}, {r['account_mode']}) — unconfirmed "
                f"staged proposal from {r['proposed_at']:%Y-%m-%d} expired (#436)",
            )
        total += len(rows)
    if total:
        logger.info(f"expired {total} stale trade proposal(s)")
    return total


async def cancel_unfilled_entries(reason: str = "EOD unfilled", account_mode: str | None = None) -> int:
    """Cancel all unfilled entry orders. Returns count cancelled.

    Called from cleanup paths AND the operator panic button — passing the right
    reason keeps skip_reason and Telegram copy honest:
    - 10:00 ET ORB-window cleanup → reason="ORB window unfilled"
    - 4:05 PM EOD cleanup         → reason="EOD unfilled" (default)
    - operator /pause (#345)       → reason="manual /pause", account_mode="live"

    account_mode (#345): when set, cancel ONLY that mode's resting entries — so
    /pause cancels resting REAL-MONEY brackets without touching paper. None (the
    cleanup paths) = all modes.
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
              AND ($1::text IS NULL OR t.account_mode = $1)
        """, account_mode)

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
                #
                # Bug fix 2026-05-28 (AVAV investigation): previously this
                # passed `entry_price` as the `limit_price` arg, which is the
                # TRIGGER (= orb_high), not the LIMIT (= stop_limit_buy_price
                # of orb_high). Effect: classifier couldn't tell `would_have_
                # filled` from `gap_through` since both args were identical,
                # so any cross-trigger case was mis-labelled `clean_miss`.
                # AVAV 2026-05-28 was the surfacing case: SIP showed high
                # $207.20 at 09:48 ET vs trigger $204.86 — should have been
                # `would_have_filled` or `gap_through`, was logged as
                # `clean_miss` due to this bug. Fire-and-forget; bar fetch
                # failure logs and continues.
                if trade.get("orb_high") and trade.get("entry_price"):
                    asyncio.create_task(classify_orb_cancellation(
                        trade_id=int(trade["id"]),
                        ticker=trade["ticker"],
                        alert_date=trade["alert_date"],
                        proposed_at=trade["proposed_at"],
                        trigger_price=float(trade["orb_high"]),
                        limit_price=stop_limit_buy_price(float(trade["orb_high"])),
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
        # #444: thread this function's OWN account_mode param (already in scope —
        # it's the filter used in the query above). When None (the batch cleanup
        # paths), mode_prefix(None) == mode_prefix() — byte-identical to before,
        # since cancellations genuinely span both modes and per-trade mode is
        # captured in the per-line audit events. When set (operator /pause passes
        # account_mode="live"), every cancelled row IS that one mode — the digest
        # now labels correctly instead of falling back to the legacy global.
        await send_telegram_message(
            f"{mode_prefix(account_mode)}🕓 {reason}: cancelled {cancelled} unfilled order(s) — {', '.join(cancelled_tickers)}"
        )
    if failed_tickers:
        await send_telegram_message(
            f"{mode_prefix(account_mode)}⚠️ {reason}: cancel FAILED for {len(failed_tickers)} order(s) — {', '.join(failed_tickers)} — investigate broker side"
        )
    return cancelled


def _canonical_order_status(raw: str | None) -> str | None:
    """Normalize order status to lowercase canonical form. Handles both Python
    SDK enum repr ('OrderStatus.PENDING_NEW') and bare lowercase ('new').

    Returns None for empty input. Examples:
      'OrderStatus.PENDING_NEW' -> 'pending_new'
      'new' -> 'new'
      'OrderStatus.FILLED' -> 'filled'
    """
    if not raw:
        return None
    return raw.split(".")[-1].lower()


# Statuses that are terminal — order is done, no further state changes expected.
_TERMINAL_ORDER_STATUSES = frozenset({
    "filled", "canceled", "cancelled", "expired", "rejected", "replaced", "done_for_day",
})

# Subset that means "order ended without filling" — used to derive cancelled_at.
_CANCEL_LIKE_ORDER_STATUSES = frozenset({"canceled", "cancelled", "expired", "rejected"})

# Statuses that confirm a replacement stop is LIVE and protecting the position.
# Used by execute_partial_exit's pre-sell verify-check: we only free shares via
# the market sell once the reduced-qty stop is confirmed resting on the broker.
_STOP_CONFIRMED_LIVE_STATUSES = frozenset({
    "new", "accepted", "held", "partially_filled", "accepted_for_bidding",
})
# Statuses that confirm the stop is DEAD (rejected/cancelled-away) — selling now
# would leave the position naked, so we abort + null the stop for remediation.
_STOP_DEAD_STATUSES = frozenset({
    "canceled", "cancelled", "expired", "rejected", "replaced", "done_for_day",
})

# Stuck-pending_new watchdog (#142, 2026-05-28). RDW ORB entry 2026-05-26
# stayed in Alpaca pending_new the entire session despite cleanup cron firing
# 10:00 ET — scheduler misfired on the 10:00:00 tick that day. Defensive
# layer here catches the gap regardless of why cleanup missed.
#
# Threshold: 15 min. Alpaca paper routing typically <1s; >5 min is anomalous;
# >15 min during market hours means routing is dead. 15 min also matches the
# reconcile cron cadence (so first reconcile after the failed-routing window
# catches it). No auto-cancel — operator decides per post-mortem discipline
# (STOP and CONSULT, not ATTEMPT and RECOVER).
_STUCK_PENDING_NEW_THRESHOLD_MINUTES = 15


async def _maybe_alert_stuck_pending_new(
    conn, row, account_mode: str, *, submitted_at
) -> None:
    """Telegram + audit when an order has been Alpaca-confirmed pending_new
    for >_STUCK_PENDING_NEW_THRESHOLD_MINUTES during market hours. Once
    per (ticker, day) dedup against `stuck_pending_new_detected` audit rows.
    """
    from zoneinfo import ZoneInfo
    from agents.market_intelligence.audit_events import STUCK_PENDING_NEW_DETECTED
    from agents.market_intelligence.trading_calendar import is_market_hours_now_et

    if submitted_at is None or not is_market_hours_now_et():
        return

    ET = ZoneInfo("America/New_York")
    now_et = datetime.now(ET)
    age_minutes = (now_et - submitted_at.astimezone(ET)).total_seconds() / 60.0
    if age_minutes < _STUCK_PENDING_NEW_THRESHOLD_MINUTES:
        return

    # Surrounding try-block guards only the DB+Telegram interactions —
    # the parent reconcile loop must keep iterating other orders even if
    # alerting infrastructure throws.
    try:
        existing = await conn.fetchval(
            """
            SELECT 1 FROM mi_audit_log
            WHERE event_type = $1
              AND summary LIKE $2
              AND (created_at AT TIME ZONE 'America/New_York')::date = $3
            LIMIT 1
            """,
            STUCK_PENDING_NEW_DETECTED,
            f"{row['ticker']}%",
            now_et.date(),
        )
        if existing:
            return

        order_id = row["alpaca_order_id"]
        ticker = row["ticker"]
        purpose = row["purpose"]

        await log_audit_event(
            STUCK_PENDING_NEW_DETECTED,
            f"{ticker} order={order_id[:8]} stuck {age_minutes:.0f}min "
            f"({account_mode}, purpose={purpose})",
            f"order_id={order_id} trade_id={row['trade_id']} "
            f"submitted_at={submitted_at.isoformat()} "
            f"age_minutes={age_minutes:.1f}",
        )
        await send_telegram_message(
            f"⚠️ *Order stuck pending_new — {ticker}*\n"
            f"Alpaca {account_mode} hasn't routed the order in "
            f"{age_minutes:.0f} min. Apollo's submission was clean; "
            f"broker-side routing stalled.\n\n"
            f"Order ID: `{order_id[:12]}…`\n"
            f"Purpose: `{purpose}`\n"
            f"Submitted: `{submitted_at.astimezone(ET).strftime('%Y-%m-%d %H:%M:%S ET')}`\n\n"
            f"_Operator decision: cancel via Alpaca web UI if "
            f"setup is no longer valid. Reconcile job will keep checking._"
        )
    except Exception as e:
        logger.error(f"_maybe_alert_stuck_pending_new failed: {e}", exc_info=True)


async def reconcile_order_states(account_mode: str, lookback_days: int = 90) -> dict:
    """Reconcile mi_live_orders.status against Alpaca for orders in transitional
    states. Updates DB rows where Alpaca's authoritative status differs.

    Smallest-viable version (#123, 2026-05-26): order-status only — does not
    derive trade close-out from Alpaca position state. If drift in 'filled'
    trades persists after 1wk of this running, expand scope to include
    trade-state derive-close (ROIV class). Per advisor 2026-05-26.

    Bounded to last `lookback_days` to avoid scanning the entire order history;
    49 stuck orders dating back to April surfaced today are well within 90d.

    Returns: {'examined': N, 'updated': M, 'errors': E}. Audit row per
    divergence ('order_status_reconciled') + 'order_status_reconcile_failed'
    on per-order fetch errors.

    Skip Telegram per advisor — retroactive 'stop fired hours ago' alerts
    are operationally confusing. Operator can drill via /audit or /trades.
    """
    pool = await get_pool()
    examined = 0
    updated = 0
    errors = 0

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT lo.alpaca_order_id, lo.ticker, lo.status, lo.trade_id, lo.purpose,
                   lo.submitted_at
            FROM mi_live_orders lo
            JOIN mi_live_trades lt ON lt.id = lo.trade_id
            WHERE lo.alpaca_order_id IS NOT NULL
              AND lt.account_mode = $1
              AND lo.submitted_at > NOW() - INTERVAL '{lookback_days} days'
              AND lo.filled_at IS NULL
              AND lo.cancelled_at IS NULL
            ORDER BY lo.submitted_at DESC
            """,
            account_mode,
        )

        if not rows:
            return {"examined": 0, "updated": 0, "errors": 0}

        for r in rows:
            order_id = r["alpaca_order_id"]
            db_status_norm = _canonical_order_status(r["status"])
            if db_status_norm in _TERMINAL_ORDER_STATUSES:
                continue
            examined += 1

            try:
                alpaca_order = await alpaca.get_order(order_id, account_mode=account_mode)
            except Exception as e:
                errors += 1
                await log_audit_event(
                    "order_status_reconcile_failed",
                    f"{r['ticker']} order={order_id[:8]}: {type(e).__name__}",
                    f"order_id={order_id} db_status={r['status']!r} error={e}",
                )
                continue

            if alpaca_order is None:
                # alpaca.get_order swallows all errors → None. Could be 404
                # or transient 5xx. Audit + retry next cycle.
                await log_audit_event(
                    "order_status_reconcile_failed",
                    f"{r['ticker']} order={order_id[:8]} alpaca_returned_none",
                    f"order_id={order_id} db_status={r['status']!r}",
                )
                errors += 1
                continue

            alpaca_status_norm = _canonical_order_status(alpaca_order.get("status"))

            # Stuck-pending_new watchdog (#142). If Alpaca confirms the order
            # is still pending_new and it's been stuck for >threshold during
            # market hours, alert operator. Fires once per (ticker, day) via
            # audit dedup. No auto-cancel — operator decides.
            if alpaca_status_norm == "pending_new":
                await _maybe_alert_stuck_pending_new(
                    conn, r, account_mode, submitted_at=r["submitted_at"]
                )

            if alpaca_status_norm == db_status_norm:
                continue

            mark_filled = alpaca_status_norm == "filled"
            mark_cancelled = alpaca_status_norm in _CANCEL_LIKE_ORDER_STATUSES
            await conn.execute(
                """
                UPDATE mi_live_orders
                SET status = $1,
                    filled_qty = COALESCE($2, filled_qty),
                    filled_avg_price = COALESCE($3, filled_avg_price),
                    filled_at = CASE WHEN $5 THEN COALESCE(filled_at, NOW()) ELSE filled_at END,
                    cancelled_at = CASE WHEN $6 THEN COALESCE(cancelled_at, NOW()) ELSE cancelled_at END
                WHERE alpaca_order_id = $4
                """,
                alpaca_status_norm,
                alpaca_order.get("filled_qty"),
                alpaca_order.get("filled_avg_price"),
                order_id,
                mark_filled,
                mark_cancelled,
            )
            updated += 1
            await log_audit_event(
                "order_status_reconciled",
                f"{r['ticker']} order={order_id[:8]}: {db_status_norm} -> {alpaca_status_norm} "
                f"({account_mode})",
                f"order_id={order_id} trade_id={r['trade_id']} purpose={r['purpose']} "
                f"db_was={r['status']!r} alpaca_now={alpaca_status_norm} "
                f"filled_qty={alpaca_order.get('filled_qty')} "
                f"filled_avg_price={alpaca_order.get('filled_avg_price')}",
            )

    return {"examined": examined, "updated": updated, "errors": errors}


async def reconcile_all_modes(lookback_days: int = 90) -> dict:
    """Run reconcile_order_states for paper + live (or paper only if
    ENABLE_LIVE_MODE=false). Aggregate counts across modes."""
    modes = active_account_modes()
    totals = {"examined": 0, "updated": 0, "errors": 0}
    for mode in modes:
        try:
            result = await reconcile_order_states(mode, lookback_days=lookback_days)
            for k in totals:
                totals[k] += result.get(k, 0)
        except Exception as e:
            logger.error(f"reconcile_order_states[{mode}] failed: {e}", exc_info=True)
            totals["errors"] += 1
    return totals


def _live_sell_stops(open_orders: list) -> list:
    """The SINGLE shared definition of "what counts as a live sell-stop" — a
    sell-side, stop-type order whose canonical status is in
    `_STOP_CONFIRMED_LIVE_STATUSES`. Both the adopt site (`_try_adopt_existing_stop`)
    and the coverage site (`_ensure_stop_coverage`) filter through this so they
    can't drift on the definition (a divergence would risk a naked position).

    PURE: takes the already-fetched open orders and returns the matching subset.
    The CALLER owns the `get_open_orders` fetch and its error handling — the fetch
    is deliberately NOT folded in here (each site has its own warning message).
    """
    live_stops = []
    for o in open_orders:
        side = str(o.get("side", "")).lower()
        otype = str(o.get("type", "")).lower()
        status = _canonical_order_status(o.get("status"))
        if "sell" not in side or "stop" not in otype:
            continue
        if status not in _STOP_CONFIRMED_LIVE_STATUSES:
            continue
        live_stops.append(o)
    return live_stops


# Distinct "couldn't read the broker" outcome for the adopt/place decision —
# must never be conflated with "no adoptable stop" (F16-sibling, 7/3).
_BROKER_UNREADABLE = object()


async def _try_adopt_existing_stop(
    trade_id: int,
    ticker: str,
    remaining_qty: float,
    account_mode: str,
) -> "str | None | object":
    """#151 Phase 2 / #184 part-a (adopt-only): if the broker ALREADY has a
    live sell-stop covering this position, adopt it into the DB stop_order_id
    pointer (a PURE DB WRITE — no broker order placed or cancelled) rather than
    placing a duplicate. Returns the adopted order id, or None when there is no
    single positively-confirmed covering stop (caller falls through to the
    existing place-new remediation — today's behavior).

    Conservative by design (advisor 2026-06-05): adopts ONLY when EXACTLY ONE
    open order is a confirmed-live sell-stop with qty >= remaining. Zero
    candidates (nothing to adopt) or >1 (ambiguous) → None; never guess. No
    cancel/dedup here — that broker-mutating capability is deferred (Phase 2b).

    F16-sibling (7/3 review, altitude pass): a broker-READ failure returns the
    distinct _BROKER_UNREADABLE sentinel, NOT None — with None, "couldn't read"
    was indistinguishable from "nothing to adopt" and the caller fell through
    to place_stop_order while a real stop may exist (the same duplicate-stop
    hazard F16 closed in _ensure_stop_coverage). The caller DEFERS on the
    sentinel (next sync run re-checks).
    """
    try:
        open_orders = await alpaca.get_open_orders(
            ticker, account_mode=account_mode, raise_on_error=True)
    except Exception as e:
        logger.warning(f"_try_adopt_existing_stop: get_open_orders failed for {ticker}: {e}")
        return _BROKER_UNREADABLE
    candidates = []
    for o in _live_sell_stops(open_orders):
        oqty = o.get("qty")
        try:
            if oqty is not None and float(oqty) >= float(remaining_qty) - 0.5:
                candidates.append(o)
        except (TypeError, ValueError):
            continue
    if len(candidates) != 1:
        return None  # 0 = nothing to adopt; >1 = ambiguous → don't guess
    adopt_id = candidates[0].get("id")
    if not adopt_id:
        return None
    await set_stop_order_id(
        trade_id, adopt_id, reason="sync_adopt_existing", account_mode=account_mode,
    )
    await log_audit_event(
        "stop_coverage_adopted",
        f"{ticker}: adopted existing live broker stop {adopt_id[:8]} into DB "
        f"pointer (no duplicate placed)",
        json.dumps({
            "trade_id": trade_id, "ticker": ticker, "adopted_stop_id": adopt_id,
            "remaining_qty": float(remaining_qty),
        }),
    )
    return adopt_id


# Substring signatures of Alpaca's "stop trigger is above current price" rejection.
# A protective sell-stop must sit BELOW the market; when the stop_price we want is
# above the last trade, Alpaca refuses it. This is NOT a transient error — retrying
# can't fix a price that's structurally invalid — so the never-naked invariant
# converges (ONE alert, leave for operator) instead of looping. The breach-exit
# decision (market out vs hold) is the operator's/strategy's call, not the
# reconciler's. Real incident 2026-06-23. Matched case-insensitively on str(exc).
_STOP_ABOVE_MARKET_SIGNATURES = (
    "must be less than current price",
    "must be less than the current price",
    "stop price must be less",
)


def _is_stop_above_market(exc: Exception) -> bool:
    """True iff the broker rejected a sell-stop because its trigger is at/above
    the current market price (structural breach — the position is already through
    where the stop would sit). Distinguished from transient/qty errors so the
    invariant converges instead of retrying an un-retryable price."""
    msg = str(exc).lower()
    return any(sig in msg for sig in _STOP_ABOVE_MARKET_SIGNATURES)


async def _ensure_stop_coverage(
    trade_id: int,
    ticker: str,
    broker_qty: float,
    db_stop_price: float | None,
    signal_type: str,
    account_mode: str,
) -> str | None:
    """#151 never-naked coverage invariant.

    Guarantee EXACTLY ONE live sell-stop covering `target = broker_qty −
    pending_exit_qty(trade_id)` for a filled position. Closes the gap the
    orphan-remediation loop structurally cannot: that loop only acts when the
    stop is NULL/just-cleared or DEAD (it `continue`s past a LIVE stop at the
    `order_status not in DEAD_STATES` gate). A LIVE-but-UNDER-COVERING stop
    (e.g. a 134-share stop left behind by a failed/aborted partial on a
    163-share position) sails through untouched → the un-trimmed shares are
    NAKED. This brings coverage back to `target` so any partial-exit failure
    leaves the position "no profit trimmed", never "naked".

    BROKER TRUTH ONLY for sizing:
      * `broker_qty` is the Alpaca position qty (caller passes `qty`, the TOTAL
        position — NOT `qty_available`, which already nets out held-for-orders
        and would double-subtract).
      * The live stop is discovered via `get_open_orders` (like
        `_try_adopt_existing_stop`), NEVER the stale in-memory `remaining_shares`
        / `stop_order_id` (the qty-sync + orphan loop write the DB but do not
        mutate the already-fetched `db_trades` rows; 109-vs-28 incident
        2026-06-23).

    Decision tree (0.5-share tolerance, matching the 2523 qty-sync / 2415 adopt):
      * target <= 0 (pending exits cover everything)        → no-op (None)
      * |live_stop_qty − target| <= 0.5                     → no-op (None)
      * over-covered (live_stop_qty > target + 0.5)         → no-op (Phase 2b
            dedup/down-size deferred — never our job to shrink coverage here)
      * >1 live sell-stop                                    → ambiguous, no-op
            (a duplicate has no cleanup path; Phase 2b dedup deferred)
      * under-covered, exactly ONE live stop                → atomic qty-only
            `replace_order` to `target` (keeps the accepted stop_price → can't
            breach); SINGLE stop, never an additive 2nd order.
      * under-covered, NO live stop                          → `place_stop_order`
            at `db_stop_price` (the place branch is the only one that can breach).

    Idempotent: a 2nd consecutive run sees coverage == target → no-op, no new
    orders. Every submit is MODE-SCOPED via `make_client_order_id(account_mode,
    ...)`. On a stop-above-market BREACH (place branch), emit ONE discrepancy
    line + audit and CONVERGE — no retry, no auto-market-exit, no stop_order_id
    write (the breach-exit is the operator's call).

    Returns a human discrepancy string when it acted/flagged (for the batched
    Telegram), else None.
    """
    # ── #151 cross-PROCESS lock: defer to an IN-FLIGHT partial. ──────────────
    # execute_partial_exit holds the BLOCKING advisory lock on this trade_id
    # while it reduces the stop. If we (the reconciler, possibly a different
    # process under EXECUTION_MODE=http) tried to 'repair' coverage mid-reduce
    # we'd fight the partial. Take the NON-BLOCKING try-lock: if a partial holds
    # it, SKIP this trade entirely (return None) — the partial owns coverage and
    # its own abort path re-protects. If we get the lock, do the coverage check
    # under it (auto-unlocked on CM exit).
    async with _trade_advisory_try_lock(trade_id) as _have_lock:
        if not _have_lock:
            logger.info(
                f"_ensure_stop_coverage: coverage skipped — partial in-flight "
                f"(advisory lock held) for trade {trade_id} {ticker}"
            )
            return None
        target = float(broker_qty) - float(await get_pending_exit_qty(trade_id))
        if target <= 0.5:
            # Pending exits account for the whole (or all-but-noise) position —
            # nothing to protect beyond what's already in flight. The orphan loop's
            # own "fully covered by pending exits" guard handles the no-stop variant;
            # here we just decline to place/replace.
            return None

        # Discover the live sell-stop(s) from broker truth. raise_on_error=True
        # (F16, 7/3): get_open_orders' default [] fallback made this except
        # UNREACHABLE — a transient read failure looked like "no live stop" and
        # drove the place branch on a false premise (duplicate-stop hazard).
        # Exceptions-out here makes the defer-on-ambiguity below work as designed.
        try:
            open_orders = await alpaca.get_open_orders(
                ticker, account_mode=account_mode, raise_on_error=True)
        except Exception as e:
            logger.warning(
                f"_ensure_stop_coverage: get_open_orders failed for {ticker}: {e}"
            )
            return None  # ambiguous (couldn't read broker) — defer to next run

        live_stops = _live_sell_stops(open_orders)

        if len(live_stops) > 1:
            # Ambiguous: more than one live sell-stop. Adding/replacing here could
            # leave a dangling duplicate with no cleanup path. Flag only; Phase 2b
            # dedup-cancel is the place that owns this.
            await log_audit_event(
                "stop_coverage_ambiguous",
                f"{ticker}: {len(live_stops)} live sell-stops vs target {target:.0f} "
                f"— skipping coverage repair (Phase 2b dedup deferred)",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "account_mode": account_mode,
                    "live_stop_count": len(live_stops),
                    "target_qty": target,
                }),
            )
            return (
                f"⚠️ {ticker}: {len(live_stops)} live stops (target {target:.0f}) "
                f"— ambiguous, left for review"
            )

        live_stop = live_stops[0] if live_stops else None
        live_qty = None
        if live_stop is not None:
            try:
                live_qty = float(live_stop.get("qty")) if live_stop.get("qty") is not None else None
            except (TypeError, ValueError):
                live_qty = None

        # Fully covered (within tolerance) or over-covered → no-op.
        if live_qty is not None and live_qty >= target - 0.5:
            return None

        # Under-covered (or no live stop): re-protect to `target` as a SINGLE stop.
        coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)

        if live_stop is not None:
            # Atomic qty-only replace — keeps the already-accepted stop_price (so it
            # cannot breach) and never opens a share-release window. New order id
            # must be persisted.
            try:
                new_order = await alpaca.replace_order(
                    live_stop["id"],
                    qty=int(target),
                    account_mode=account_mode,
                    client_order_id=coid,
                )
            except Exception as e:
                logger.error(
                    f"_ensure_stop_coverage: replace under-covering stop failed for "
                    f"{ticker} ({live_qty}→{target:.0f}): {e}"
                )
                await log_audit_event(
                    "stop_coverage_repair_failed",
                    f"{ticker}: replace under-covering stop {live_qty}→{int(target)} failed: {e}",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker,
                        "account_mode": account_mode,
                        "live_stop_qty": live_qty, "target_qty": target,
                        "error": str(e),
                    }),
                )
                return f"⚠️ {ticker}: failed to widen stop coverage {live_qty}→{target:.0f}: {e}"
            await set_stop_order_id(
                trade_id, new_order["id"],
                reason="sync_coverage_repair",
                account_mode=account_mode,
            )
            await log_audit_event(
                "stop_coverage_repaired",
                f"{ticker}: under-covering stop {live_qty}→{int(target)} "
                f"(replaced {live_stop['id'][:8]}→{new_order['id'][:8]})",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "account_mode": account_mode,
                    "old_stop_id": live_stop["id"], "new_stop_id": new_order["id"],
                    "live_stop_qty": live_qty, "target_qty": target,
                }),
            )
            return (
                f"🛡 Coverage repaired {ticker}: stop {live_qty:.0f}→{target:.0f} "
                f"(under-covering after partial-exit failure)"
            )

        # No live stop at all → place one at the DB stop price. This is the ONLY
        # branch that can breach (the price we choose may now be above market).
        if not db_stop_price:
            await log_audit_event(
                "stop_coverage_no_price",
                f"{ticker}: under-covered (target {target:.0f}) with no live stop and "
                f"no DB stop_price — manual intervention",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "account_mode": account_mode, "target_qty": target,
                }),
            )
            return (
                f"⚠️ {ticker}: no stop & no stop_price (target {target:.0f}) "
                f"— manual intervention needed"
            )
        try:
            new_order = await alpaca.place_stop_order(
                ticker, int(target), float(db_stop_price),
                account_mode=account_mode, client_order_id=coid,
            )
        except Exception as e:
            if _is_stop_above_market(e):
                # BREACH: the protective trigger is at/above current price. NOT
                # retryable. ONE alert, converge, leave for operator. Do NOT
                # auto-market-exit and do NOT write stop_order_id.
                await log_audit_event(
                    "stop_coverage_breach",
                    f"{ticker}: stop ${db_stop_price:.2f} would sit above market — "
                    f"position through the stop. Operator action required (no auto-exit).",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker,
                        "account_mode": account_mode,
                        "intended_stop_price": float(db_stop_price),
                        "target_qty": target, "error": str(e),
                    }),
                )
                logger.error(
                    f"_ensure_stop_coverage: BREACH for {ticker} — stop "
                    f"${db_stop_price:.2f} above market; converging (no retry, no auto-exit)"
                )
                return (
                    f"🚨 {ticker}: stop ${db_stop_price:.2f} is ABOVE market — "
                    f"position breached the stop. Operator decision needed (no auto-exit)."
                )
            # Any other placement error: surface it, no retry inside the invariant
            # (the reconciler runs again on its cadence).
            logger.error(
                f"_ensure_stop_coverage: place coverage stop failed for {ticker}: {e}"
            )
            await log_audit_event(
                "stop_coverage_repair_failed",
                f"{ticker}: place coverage stop (target {int(target)}) failed: {e}",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "account_mode": account_mode, "target_qty": target,
                    "error": str(e),
                }),
            )
            return f"⚠️ {ticker}: failed to place coverage stop (target {target:.0f}): {e}"
        await set_stop_order_id(
            trade_id, new_order["id"],
            reason="sync_coverage_repair",
            account_mode=account_mode,
        )
        await log_audit_event(
            "stop_coverage_repaired",
            f"{ticker}: placed coverage stop {int(target)} @ ${db_stop_price:.2f} "
            f"(was no live stop)",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "account_mode": account_mode,
                "new_stop_id": new_order["id"], "target_qty": target,
                "stop_price": float(db_stop_price),
            }),
        )
        return (
            f"🛡 Coverage placed {ticker}: stop {target:.0f} @ ${db_stop_price:.2f} "
            f"(no live stop, under-covered)"
        )


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
    modes = active_account_modes()
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

    # Safety: if Alpaca returned zero positions but DB has N>0 active
    # filled trades, that's almost certainly a broker-side failure
    # (creds bootstrap failed, 5xx, network hiccup) — NOT a real "user
    # liquidated everything" event. Mass-closing the DB on this signal
    # destroys state (2026-05-27 23:01 ET incident: docker exec python
    # one-shot ran sync without _bootstrap_alpaca_credentials → 0
    # positions returned → 3 active trades wrongly closed in DB; manual
    # SQL restore required). Audit + abort.
    active_db_trades = [
        t for t in db_trades
        if t["status"] == "filled" and (t["remaining_shares"] or 0) > 0
    ]
    if not alpaca_positions and active_db_trades:
        await log_audit_event(
            "sync_positions_aborted_alpaca_empty",
            f"[{account_mode}] Alpaca returned 0 positions but DB has "
            f"{len(active_db_trades)} active filled trades — refusing to "
            f"mass-close (likely creds/API failure). Investigate manually.",
            detail=json.dumps({
                "account_mode": account_mode,
                "db_active_count": len(active_db_trades),
                "db_active_tickers": [t["ticker"] for t in active_db_trades],
            }),
        )
        logger.error(
            f"sync_positions [{account_mode}]: 0 Alpaca / "
            f"{len(active_db_trades)} DB-active → ABORT (refusing mass-close)"
        )
        return [
            f"[{account_mode}] ABORTED: 0 Alpaca positions vs "
            f"{len(active_db_trades)} DB-active — likely broker-side failure"
        ]

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
            # #401 (advisor 6/28): a naked LIVE position gets its OWN loud alarm —
            # real money must not be one bullet buried in the generic sync digest.
            # The digest + auto-remediation below still run; this only escalates.
            if account_mode == "live":
                if not await send_telegram_message(
                    f"🚨 NAKED LIVE POSITION — {ticker}: stop "
                    f"{existing_stop_id[:8]} is {order_status}. "
                    f"Auto-remediation (re-place/adopt) running now; verify in /trades."
                ):
                    logger.error(
                        f"#401 naked-live escalation Telegram FAILED for {ticker} "
                        f"(alert lost; digest + audit row still carry it)"
                    )
        # #151 Phase 2 / #184 part-a (sync-first, adopt-only): BEFORE placing a
        # new stop, check whether the broker ALREADY has a live stop covering
        # this position that the DB merely lost track of (null / just-cleared
        # pointer). If so, ADOPT it (pure DB write) instead of placing a
        # duplicate — the FPS 2026-06-05 false-remediation loop (sync kept
        # trying to add a 2nd stop while df9ff732 already covered the 109).
        # Conservative: adopts only a single positively-confirmed covering stop;
        # ambiguity falls through to place. Dedup-cancel deferred (Phase 2b).
        adopted_id = await _try_adopt_existing_stop(
            trade["id"], ticker,
            float(trade["remaining_shares"] or 0), account_mode,
        )
        if adopted_id is _BROKER_UNREADABLE:
            # F16-sibling: couldn't READ the broker's open orders — placing now
            # could duplicate a live stop we simply failed to see. Defer this
            # trade to the next sync run (same ambiguity semantics as
            # _ensure_stop_coverage's defer).
            msg = f"⏸ {ticker}: broker orders unreadable — stop remediation deferred to next sync"
            discrepancies.append(msg)
            logger.warning(f"sync_positions: {msg}")
            continue
        if adopted_id:
            msg = f"🛡 Adopted existing broker stop for {ticker} ({adopted_id[:8]}) — no duplicate placed"
            discrepancies.append(msg)
            logger.info(f"sync_positions: {msg}")
            continue

        # Position is live in Alpaca but has no stop order — remediate
        stop = trade["stop_price"] or trade["orb_low"]
        if not stop:
            msg = f"⚠️ Orphaned position {ticker}: filled with no stop & no stop_price in DB — manual intervention needed"
            discrepancies.append(msg)
            logger.error(f"sync_positions: orphaned {ticker} trade_id={trade['id']} — no stop_price to remediate")
            # RED-2 observability (2026-07-12): durable terminal-naked marker.
            # This shape was digest/log only — the FL-1 soak (and any monitor)
            # could not see a hands-fixed orphan. TERMINAL: adopt found no
            # broker stop and there is NO stop anchor in DB, so no automated
            # pass (this sync, evening backstop, next-day watchdog) can ever
            # protect it. Additive audit row only — no control-flow change.
            # NOTE: summary must NOT start with "{ticker} #{trade_id}" — the
            # stop-ack watchdog dedups its remediation on that prefix and must
            # still run its own attempt next market-hours window.
            await log_audit_event(
                "stop_ack_remediation_failed",
                f"{ticker}: sync orphan unremediable — no live/adoptable stop "
                f"and no stop_price/orb_low anchor in DB (trade {trade['id']})",
                json.dumps({
                    "trade_id": trade["id"],
                    "ticker": ticker,
                    "account_mode": account_mode,
                    "remaining_shares": float(trade["remaining_shares"] or 0),
                    "reason": "no_stop_anchor",
                    "site": "order_manager.py::sync_positions_orphan_no_anchor",
                }),
            )
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
            # RED-2 observability (2026-07-12): durable terminal-naked marker
            # (digest/log only before). TERMINAL for this remediation layer:
            # 3 backoff attempts exhausted, loop gives up, position stays
            # naked until hands or a much-later pass. Additive audit row only.
            # Summary deliberately avoids the watchdog's "{ticker} #{id}%"
            # dedup prefix (see no-anchor site above).
            await log_audit_event(
                "stop_ack_remediation_failed",
                f"{ticker}: sync orphan stop remediation failed after 3 attempts "
                f"— {type(last_err).__name__ if last_err else 'unknown'} "
                f"(trade {trade['id']})",
                json.dumps({
                    "trade_id": trade["id"],
                    "ticker": ticker,
                    "account_mode": account_mode,
                    "qty": qty,
                    "stop_price": float(stop),
                    "reason": "place_stop_failed_3_attempts",
                    "error": (
                        f"{type(last_err).__name__}: {str(last_err)[:200]}"
                        if last_err else None
                    ),
                    "site": "order_manager.py::sync_positions_orphan_remediation_failed",
                }),
            )

    # #151 NEVER-NAKED COVERAGE INVARIANT — runs AFTER the orphan/adopt loop.
    # The orphan loop only acts on a NULL/just-cleared or DEAD stop; a LIVE-but-
    # UNDER-COVERING stop sails past its `order_status not in DEAD_STATES: continue`
    # gate (e.g. a 134-share stop left by a failed/aborted partial on a 163-share
    # position) → the un-trimmed shares are NAKED. This pass guarantees exactly
    # one live stop at `broker_qty − pending_exit` for every filled position, so
    # any partial-exit failure leaves it "no profit trimmed", never naked.
    #
    # Broker truth for sizing: `alpaca_map` was mutated (`del`) by the qty-sync
    # loop above, so rebuild a fresh map from the intact `alpaca_positions` list.
    # Use `qty` (TOTAL position) NOT `qty_available` (already nets held-for-orders
    # → would double-subtract). The helper rediscovers the live stop via
    # get_open_orders rather than trusting the stale in-memory trade row.
    broker_qty_map = {p["symbol"]: p["qty"] for p in alpaca_positions}
    for trade in db_trades:
        ticker = trade["ticker"]
        if trade["status"] != "filled":
            continue
        broker_qty = broker_qty_map.get(ticker)
        if broker_qty is None or broker_qty <= 0:
            continue  # not (or no longer) a live broker position — nothing to cover
        try:
            coverage_msg = await _ensure_stop_coverage(
                trade["id"], ticker, float(broker_qty),
                trade.get("stop_price") or trade.get("orb_low"),
                trade.get("signal_type") or "unknown",
                account_mode,
            )
        except Exception as e:
            logger.error(
                f"sync_positions: _ensure_stop_coverage raised for {ticker}: {e}",
                exc_info=True,
            )
            coverage_msg = f"⚠️ {ticker}: coverage-invariant check errored: {e}"
        if coverage_msg:
            discrepancies.append(coverage_msg)

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


async def prepare_prior_day_low_orb_order(
    sugar_baby: dict,
    orb_bar: dict,
    regime_record: dict | None = None,
    account_mode: str | None = None,
    today: date | None = None,
) -> tuple[dict | None, str | None]:
    """
    ORB entry with a PRIOR-DAY-LOW stop — a geometry, not a strategy.

    ⚠ RENAMED 2026-08-02 from `prepare_9m_day2_orb_order`. Nothing here is 9M-specific;
    it was named after its first caller, which is why retiring the (dead) 9M Day 2
    strategy appeared to be blocked on it. The 5-min ORB shadow lane runs this geometry
    as a #482 bracket variant (105 acted rows) and must keep doing so.

    ⚠ It is NOT `prepare_orb_order` with one argument changed — a line-by-line diff on
    2026-08-02 found EIGHT divergences, not the one the old docstring claimed:
      1. stop source          — prior-day low vs today's ORB low
      2. stop-width policy    — stop distance > 15% vs ORB range > 1.5x ATR
      3. risk floor           — 2% minimum risk_per_share here; none there
      4. validity check       — rejects prior_day_low >= orb_high (impossible for ORB)
      5. atr_14               — not taken here; required there
      6. risk_dollars         — the ACTUAL (shares x risk) here; the BUDGET there
      7. skip reason          — size_too_small here; price_exceeds_cap there
      8. spec payload         — trade_type/sugar_baby_date vs score/catalyst/atr
    These are two different RISK POLICIES. A merge would need five strategy hooks on
    the money path, which is worse than two clearly-named functions. Do not merge them.

    Stop = prior day's low anchors risk to the institutional "wall" rather than to the
    opening range.

    sugar_baby: dict from get_pending_9m_sugar_babies() — must have ticker, low_price.
    orb_bar: dict with 'high' and 'low' from alpaca.get_first_bar().
    regime_record: used by the #456 regime-keyed sizing resolver (falls back to
      the pre-#456 VIX+EMA-halve formula when REGIME_SIZING_ENABLED is off).
    today: pass the SAME `today` the caller already resolved (e.g.
      the caller's `today = et_today()`) — see prepare_orb_order's
      docstring for why a second independent `et_today()` call here would be
      an unpinned second clock source in the money path. Defaults to a fresh
      `et_today()` for callers that don't have one on hand.

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

    # Position sizing (#456): same single resolver as MAGNA53 prepare_orb_order
    # — see _resolve_regime_risk_pct's docstring.
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()
    risk_pct = await _resolve_regime_risk_pct(
        regime_record, today, account_mode, base_pct=RISK_PCT,
    )

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


_PATH_MIN_DAY_BARS = 300  # #306 sweep gap-heal threshold — a full RTH day is ~390
                          # 1-min bars; < 300 flags a restart-day hole worth a refetch.
_PATH_SWEEP_LOOKBACK_DAYS = 30  # matches scripts/backfill_position_extremes.py's
                                # Polygon-request cap — bounds the EOD sweep's per-day
                                # coverage backfill so it can't runaway-request history.


async def _sweep_multi_day_coverage(pool, open_trades, today_open_et: datetime) -> None:
    """16:10 ET EOD sweep helper (#306; `sweep=True` only). For every position in
    this poll's population that filled on a PRIOR day (still open, or closed
    today after a multi-day hold), counts recorded `mi_intraday_bars` rows per
    prior trading day since `filled_at` and refetches any day whose count
    suggests a restart-day hole (a mid-day container restart during that day's
    5-min polling window). Bounded to the last `_PATH_SWEEP_LOOKBACK_DAYS` days.

    Audit-only on a persistent gap (`log_audit_event`, never `send_telegram_
    message`) — this is a shadow coverage heal, not an alertable condition.
    """
    thirty_days_ago = today_open_et - timedelta(days=_PATH_SWEEP_LOOKBACK_DAYS)
    for trade in open_trades:
        filled_at = trade["filled_at"]
        if not filled_at or filled_at >= today_open_et:
            continue  # filled today — already covered by the day-so-far fetch above
        ticker = trade["ticker"]
        lookback_start = max(filled_at, thirty_days_ago)
        try:
            async with pool.acquire() as conn:
                day_rows = await conn.fetch(
                    """
                    SELECT (bar_time AT TIME ZONE 'America/New_York')::date AS d,
                           count(*) AS n
                    FROM mi_intraday_bars
                    WHERE ticker = $1 AND bar_time >= $2
                    GROUP BY 1
                    """,
                    ticker, lookback_start,
                )
        except Exception as e:
            logger.warning(f"path sweep: {ticker} day-coverage query failed: {e}")
            continue

        for row in day_rows:
            day, n = row["d"], row["n"]
            if n >= _PATH_MIN_DAY_BARS:
                continue
            day_start = datetime.combine(day, datetime_time(9, 30), tzinfo=_ET)
            day_end = datetime.combine(day, datetime_time(16, 0), tzinfo=_ET)
            try:
                refetched = await alpaca.get_minute_bars_range(ticker, day_start, day_end)
            except Exception as e:
                logger.warning(f"path sweep: {ticker} {day} refetch failed: {e}")
                continue
            if refetched:
                await alpaca.persist_intraday_bars(ticker, refetched)
            if len(refetched) < _PATH_MIN_DAY_BARS:
                await log_audit_event(
                    "path_coverage_gap",
                    f"{ticker} {day}: {len(refetched)}/390 bars",
                )


async def scan_profit_triggers() -> list[dict]:
    """#508 — take 1/3 when the position first trades at entry + PROFIT_TRIGGER_R x risk.

    Runs on the 5-minute cadence, immediately AFTER track_open_position_extremes has
    persisted this poll's minute bars, and reads those bars back from mi_intraday_bars.

    WHY A SEPARATE FUNCTION, not a branch inside the recorder: that recorder is
    name-registered in the column-write authority gate
    (`audit_column_writes.ALLOWED_WRITERS` owns highest/lowest_price_seen for
    `order_manager.track_open_position_extremes`, and preflight_db_updates.py lists it).
    Folding a partial-exit — which writes exits/remaining_shares/stop_order_id via
    execute_partial_exit — into that name would both trip Gate 5 G and blur a pure
    recorder into a money action. #500 already cost us a deploy on exactly that class.

    MECHANISM (operator's, 2026-08-01): no resting order. This detects, then calls the
    proven `execute_partial_exit`, which reduces the stop FIRST under a per-trade advisory
    lock, verifies, and only then sells — so the position is never unprotected and there is
    no window where the stop over-covers the position.

    DETECTION IS BAR-BASED, not spot: a spike between polls is still seen, because the
    trigger tests the in-hold minute HIGH. Only the fill moment moves (measured cost vs an
    idealised limit fill: <=0.04R, nil at +2R — build step 1).

    OFF unless constants.PROFIT_TRIGGER_R is set. Returns per-trade outcome dicts.
    """
    from agents.market_intelligence.constants import PROFIT_TRIGGER_R
    if not PROFIT_TRIGGER_R:
        return []

    pool = await get_pool()
    now_et = datetime.now(_ET)
    today_open_et = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    if now_et <= today_open_et:
        return []

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ticker, entry_price, hard_stop, stop_price, remaining_shares,
                   partial_taken, filled_at, account_mode
            FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0
              AND filled_at IS NOT NULL
              AND COALESCE(partial_taken, FALSE) = FALSE
            """
        )
    results: list[dict] = []
    for t in rows:
        def _num(v):
            return float(v) if v is not None else None
        entry = _num(t["entry_price"])
        stop = _num(t["hard_stop"]) or _num(t["stop_price"])
        if not entry or not stop or stop >= entry:
            continue
        target = entry + PROFIT_TRIGGER_R * (entry - stop)
        async with pool.acquire() as conn:
            hi = await conn.fetchval(
                """
                SELECT MAX(high) FROM mi_intraday_bars
                 WHERE ticker = $1 AND bar_time >= $2
                """,
                t["ticker"], t["filled_at"],
            )
        if hi is None or float(hi) < target:
            continue
        shares = int(float(t["remaining_shares"]) // 3)
        if shares < 1:
            results.append({"ticker": t["ticker"], "action": "too_small_to_split"})
            continue
        try:
            await send_telegram_message(
                f"{mode_prefix(t['account_mode'])}\U0001F4B0 *Profit target hit: {t['ticker']}*\n"
                f"traded ${float(hi):.2f} >= ${target:.2f} "
                f"({PROFIT_TRIGGER_R:g}R above ${entry:.2f})\n"
                f"Taking {shares} of {int(float(t['remaining_shares']))} sh, "
                f"stop moves to breakeven."
            )
        except Exception:  # loud-ok: notification must never abort the money action below
            logger.warning(f"profit-trigger notify failed for {t['ticker']}", exc_info=True)
        ok = await execute_partial_exit(t["id"], shares)
        await log_audit_event(
            "profit_trigger_fired" if ok else "profit_trigger_failed",
            f"{t['ticker']}: high ${float(hi):.2f} >= {PROFIT_TRIGGER_R:g}R target ${target:.2f}",
            json.dumps({"trade_id": t["id"], "shares": shares, "entry": entry,
                        "target": target, "high": float(hi)}),
        )
        results.append({"ticker": t["ticker"],
                        "action": "partial_submitted" if ok else "partial_failed",
                        "shares": shares})
    return results


async def track_open_position_extremes(sweep: bool = False) -> int:
    """Alpaca-sourced intraday path recorder + extremes maintainer (#306, 2026-07-25).

    Runs every 5 min during market hours (job id `track_position_extremes`,
    unchanged cron slot) plus one 16:10 ET EOD completion sweep (`sweep=True`,
    job id `position_path_eod_sweep`). This SUBSUMES the prior Polygon-only
    extremes job — same function name, same job id, same registry entries
    (`scripts/audit_column_writes.py` / `scripts/preflight_db_updates.py`
    authorize `order_manager.track_open_position_extremes` by name) — a body
    rewrite, not a repoint. Full design:
    docs/design/306_intraday_path_recorder_2026-07-25.md

    Two defects fixed together (the card's framing was only the first):
    (1) Polygon `get_minute_bars` on our Starter plan is ~15-17 min delayed, so
        a fast trade's path was invisible while it was still open. Alpaca
        (`get_minute_bars_range`, feed = `get_data_feed()`) is real-time.
    (2) The selection predicate below is open-OR-closed-today, not open-only —
        a trade that fills 09:36 and stops 09:39 is picked up via `closed_at`
        by the very next poll, so every trade's final minutes get captured.
        This is the #310 bug class (`pivot_stop_shadow`'s `closed_at::date =
        today` exact match silently dropped 7 of 9 same-day round trips) —
        the predicate is a tz-aware TIMESTAMPTZ `>=` comparison, NEVER a
        `::date` cast, so it is immune to the UTC-rollover failure mode.

    Two correctness clamps (load-bearing — state them, don't just imply them):
    (A) RECORDING window != EXTREMES window, AND both are capped at 16:00 ET.
        Bars are persisted for the whole fetch window (today-so-far, capped at
        16:00 — NEVER `now_et` directly, which at the 16:10 sweep would pull in
        after-hours prints) — including post-exit same-day bars up to that cap,
        which is wanted for offline review context (§2b: "through 16:00 ...
        never further"). Extremes are computed ONLY over bars with `filled_at
        <= t` AND (`t <= closed_at` if closed, else unbounded up to the SAME
        16:00-capped fetch window if still open) — a post-stop-out pop must
        never contaminate `highest_price_seen` (the HUT post-stop re-cross
        class the parent analysis relied on excluding), and an OPEN position's
        "unbounded" upper bound must never silently mean "post-close" just
        because the sweep runs after 16:00.
    (B) The in-hold lower bound stays `t >= filled_at` exactly as before #306
        (was `t >= filled_ms` against epoch-ms Polygon bars — same semantic,
        now compared as tz-aware datetimes) — so extremes stay comparable with
        every historical value and with the sim contract's SC-1 boundary
        (design doc §2a).

    `highest_price_seen` IS read by a decision-adjacent path: the time-stop
    scan (scheduler.py, JOB_TIME_STOP_SCAN) uses an excursion-from-high
    discriminator to surface 9M Day 2 meanderer candidates for the operator's
    `/timestop` command — an operator-CONFIRMED sell, not an automated one.
    That population is holds >= 5 trading days, for which a source that used
    to be ~15 min delayed is immaterial — every bar has long since been
    polled by the time it's read, and both vendors serve the same
    consolidated tape. The sub-15-minute trades whose values actually change
    under this repoint are already closed and can never re-enter the
    time-stop population. Net behavior change to time-stop: none — only the
    PROVENANCE of an already-settled number moved (THE-LINE hygiene note, not
    a code gate).

    Lifetime extremes (across the whole trade, including any Day-1 re-entry
    attempts) — not per-attempt. Initialized to entry_price by
    trade_stream._process_entry_fill; this job tightens (lows down, highs
    up) over the trade's life.

    Returns count of trade rows updated (extremes UPDATEs only — path-recording
    upserts are not counted, matching the pre-#306 return-value contract).
    """
    pool = await get_pool()
    now_et = datetime.now(_ET)
    today_open_et = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    # Fetch window end is capped at 16:00 ET, never raw `now_et` (verify-against-
    # design catch, 2026-07-25): at the 16:10 EOD sweep now_et=16:10, and for an
    # OPEN position closed_at is None, so the extremes upper bound below is
    # unbounded — whatever the fetch window's end is. Without this cap, a
    # 16:00-16:10 print would (a) leak into highest/lowest_price_seen for every
    # still-open position, contradicting clamp A's "now if open" (now means
    # trading-day now, not post-close), and (b) violate §2b's recording
    # boundary ("through 16:00 of its fill/exit days only, never further").
    # During the regular */5 poll this is a no-op (now_et is always < 16:00).
    window_end_et = min(now_et, today_open_et.replace(hour=16, minute=0, second=0, microsecond=0))
    if window_end_et <= today_open_et:
        # Pre-open cron fires (the `*/5` slot starts at hour=9, i.e. 9:00-9:25,
        # before the 9:30 open) would otherwise request an INVERTED
        # [today_open_et, window_end_et] window from Alpaca for any already-open
        # multi-day position — fails safe (get_minute_bars_range catches the
        # exception and returns []), but every such fire logs a spurious error.
        # Nothing to fetch before the open; skip outright.
        return 0

    async with pool.acquire() as conn:
        # Open OR closed-today — NOT open-only (defect #2) — and a tz-aware
        # TIMESTAMPTZ `>=` comparison, NEVER `closed_at::date = <today>` (the
        # #310 bug class). Status vocabulary deliberately not enumerated on the
        # closed side: `closed_at >= $1` is immune to vocabulary drift (prod
        # today uses 'closed').
        open_trades = await conn.fetch(
            """
            SELECT id, ticker, filled_at, closed_at
            FROM mi_live_trades
            WHERE filled_at IS NOT NULL
              AND (
                (status = 'filled' AND remaining_shares > 0)
                OR closed_at >= $1
              )
            """,
            today_open_et,
        )
    if not open_trades:
        return 0

    from collections import defaultdict
    by_ticker: dict[str, list] = defaultdict(list)
    for t in open_trades:
        by_ticker[t["ticker"]].append(t)

    update_rows: list[tuple[int, float, float]] = []
    for ticker, trades in by_ticker.items():
        try:
            bars = await alpaca.get_minute_bars_range(ticker, today_open_et, window_end_et)
        except Exception as e:
            logger.warning(f"track_extremes: {ticker} minute bars fetch failed: {e}")
            continue
        if not bars:
            continue

        # PATH write — every fetched bar, including post-exit same-day bars
        # (clamp A). Fire-and-forget-safe (persist_intraday_bars never raises).
        await alpaca.persist_intraday_bars(ticker, bars)

        for trade in trades:
            filled_at = trade["filled_at"]
            if not filled_at:
                continue
            closed_at = trade["closed_at"]
            # Clamp B: in-hold lower bound unchanged. Clamp A: upper bound is
            # closed_at when the trade has closed, else unbounded (still open)
            # — never the fetch window's post-exit tail.
            in_hold = [
                b for b in bars
                if b.get("t_et") is not None
                and filled_at <= b["t_et"]
                and (closed_at is None or b["t_et"] <= closed_at)
            ]
            if not in_hold:
                continue
            period_low = min(b["low"] for b in in_hold)
            period_high = max(b["high"] for b in in_hold)
            if period_low <= 0 or period_high <= 0:
                continue
            update_rows.append((trade["id"], period_low, period_high))

    if update_rows:
        async with pool.acquire() as conn:
            await conn.executemany("""
                UPDATE mi_live_trades SET
                    lowest_price_seen = LEAST(COALESCE(lowest_price_seen, $2), $2),
                    highest_price_seen = GREATEST(COALESCE(highest_price_seen, $3), $3)
                WHERE id = $1
            """, update_rows)

    if sweep:
        await _sweep_multi_day_coverage(pool, open_trades, today_open_et)

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
