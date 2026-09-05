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
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from typing import NamedTuple
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
    MAX_POSITION_PCT,
)
from agents.market_intelligence.db import (
    get_pool,
    log_audit_event,
    get_manual_halt_state,
    get_runtime_toggle,
    _jsonb_param,
)
from agents.market_intelligence.audit_events import (
    SIZING_REGIME_FALLBACK,
    SIZING_NOTIONAL_CAP_TRUNCATED,
    STOP_UPDATE_RETRY_TRIGGERED,
    STOP_UPDATE_FAILED,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# ── DB timeout for the re-protect-floor chain (#621, found 2026-09-05) ──────
# Nothing in this chain — `_trade_advisory_try_lock`, `get_pending_exit_qty`,
# `_current_stop_pointer`, `_read_preserved_dead_stop` — carried a time limit,
# and it runs directly in front of `place_stop_order`. A hung Postgres or a
# saturated 5-connection pool (`db.py::get_pool`, max_size=5) blocked one of
# these forever with no code-level escape, ahead of an unprotected position.
#
# SCOPE: a per-call bound on this chain only, not a pool-wide asyncpg
# `command_timeout` in `db.py::get_pool`. A pool-wide default is the smaller
# diff and would cover every query, but `db.py` runs ~25 `executemany` batch
# writers (nightly universe/theme/RS inserts, some thousands of rows) that a
# blanket timeout would need auditing to exempt one by one — undone here to
# avoid discovering the exempt list in production, and a separate card is
# already changing `db.py`'s query plumbing concurrently. This constant
# touches only the calls listed above, all in this file.
#
# MECHANISM: asyncpg's own `timeout=` kwarg on `pool.acquire()` and on the
# query itself (fetchval/fetchrow) — not an external `asyncio.wait_for(...)`
# wrapped around a call on a pooled connection. asyncpg cancels the in-flight
# command and marks the connection correctly when its own `timeout=` fires;
# wrapping externally can abandon the coroutine while the command is still
# running on the connection and hand a poisoned connection back to the pool
# for the next borrower. `pool.acquire(timeout=...)` covers the saturation
# case (blocked waiting for a free connection); the query's own `timeout=`
# covers a hung command once a connection is in hand.
#
# VALUE: these are single-row primary-key reads / an already-non-blocking
# `pg_try_advisory_lock` — a local round trip normally takes low single-digit
# milliseconds. 5s is roughly 1000x that: generous headroom against real but
# transient contention on the EXECUTION_OWNED_JOB_IDS role's shared 5-connection
# pool (its only concurrent users during market hours are `position_coverage_check`
# every 15 min and `stop_coverage_repair_retry` every 5 min — scheduler.py), while
# still ending a true hang in a small fraction of either job's cadence. It is
# also far tighter than the 30s/45s broker bounds in `alpaca_client.py`
# (`_SDK_TIMEOUT_DEFAULT`/`_SDK_TIMEOUT_WRITE`) on purpose: a local DB round
# trip has no business taking anywhere near as long as a network call to
# Alpaca.
#
# FAIL DIRECTION: every caller below already fails open on ANY exception
# (`_current_stop_pointer`, `_read_preserved_dead_stop`) or already lets a
# raise propagate to an existing per-trade handler (`get_pending_exit_qty`,
# `_trade_advisory_try_lock`) — a TimeoutError joins whichever path already
# exists, unchanged. Nothing here is given a NEW except clause or a NEW
# fail-open default; see each function's docstring/comment for why.
_REPROTECT_DB_TIMEOUT = 5.0


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


async def _breakeven_at_broker_enabled(account_mode: str) -> bool:
    """Runtime toggle for the REAL-TIME breakeven stop (#548, 2026-08-08). DEFAULT OFF.

    Operator signed off on the fix; this ships DARK anyway, because #508's own history is the
    argument for it: that change was deployed INERT, confirmed in prod, and only then flipped —
    "so the path was proven before it was allowed to act on money". Same idiom as
    `entry_ask_aware`: one `mi_safeguard_state` row, no redeploy, reversible the same way.

    Fails CLOSED. An unreadable flag must leave exit behaviour exactly as it is.
    """
    try:
        from agents.market_intelligence import db
        row = await db.get_safeguard_state("breakeven_at_broker", account_mode)
        return bool(row) and str(row.get("state", "")).lower() == "on"
    except Exception as e:
        logger.warning(f"breakeven_at_broker flag unreadable, staying OFF: {e}")
        return False


async def _profit_take_resting_limit_enabled(account_mode: str) -> bool:
    """Runtime toggle for the +2R RESTING-LIMIT partial (#548 final design, built
    2026-08-10). DEFAULT OFF — ships dark, exactly like `breakeven_at_broker`:
    one `mi_safeguard_state` row per account_mode, no redeploy to flip, reversible
    the same way. While OFF, the profit trigger keeps today's behaviour
    byte-for-byte (market sell + breakeven folded into the stop re-creation).

    Fails CLOSED. An unreadable flag must leave exit behaviour exactly as it is.
    """
    try:
        from agents.market_intelligence import db
        row = await db.get_safeguard_state("profit_take_resting_limit", account_mode)
        return bool(row) and str(row.get("state", "")).lower() == "on"
    except Exception as e:
        logger.warning(f"profit_take_resting_limit flag unreadable, staying OFF: {e}")
        return False


async def _profit_take_oco_enabled(account_mode: str) -> bool:
    """Runtime toggle for the +2R carve-out OCO (#566, built 2026-08-15). DEFAULT
    OFF — ships dark, same idiom as `profit_take_resting_limit` / `breakeven_at_broker`:
    one `mi_safeguard_state` row per account_mode, no redeploy to flip, reversible
    the same way.

    When ON (and resting mode is on), the freed 1/3 is sold with ONE OCO —
    GTC limit at the +2R target, sibling GTC stop at breakeven — instead of a
    bare resting limit, closing the ETON 2026-08-14 hole (a limit above the
    market protects nothing on a decline; the third had NO stop). Only
    MEANINGFUL when `profit_take_resting_limit` is also on: with resting mode
    off the partial is a market sell and there is no resting third to protect.

    Fails CLOSED. An unreadable flag must leave exit behaviour exactly as it is.
    """
    try:
        from agents.market_intelligence import db
        row = await db.get_safeguard_state("profit_take_oco", account_mode)
        return bool(row) and str(row.get("state", "")).lower() == "on"
    except Exception as e:
        logger.warning(f"profit_take_oco flag unreadable, staying OFF: {e}")
        return False


async def _ask_aware_entry_enabled(account_mode: str) -> bool:
    """Runtime toggle for the ask-aware entry fallback (2026-08-07). DEFAULT OFF.

    Entry discipline is THE LINE, so this ships dark: the operator flips it with a
    `mi_safeguard_state` row — no redeploy, reversible the same way, same idiom as
    the other runtime safeguards.

    Fails CLOSED (returns False) on any read error. An unreadable flag must leave
    entry behaviour exactly as it was; the one thing it must never do is silently
    enable a money-path change because a query hiccupped.
    """
    try:
        from agents.market_intelligence import db
        row = await db.get_safeguard_state("entry_ask_aware", account_mode)
        return bool(row) and str(row.get("state", "")).lower() == "on"
    except Exception as e:
        logger.warning(f"entry_ask_aware flag unreadable, staying OFF: {e}")
        return False


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


async def _log_notional_cap_truncation(
    *,
    ticker: str,
    alert_date: date,
    account_mode: str,
    equity: float,
    max_position: float,
    entry_price: float,
    shares_before_cap: int,
    shares_after_cap: int,
    risk_dollars_actual: float,
    risk_dollars_intended: float,
) -> None:
    """#571 (2026-08-23): the 20%-of-equity notional cap (`MAX_POSITION_PCT`)
    truncates shares SILENTLY today — the trade still fires, just smaller, and
    nothing records it except the shares==0 reject a few lines below. Measured
    over the 22 closed live trades (docs/analysis/position_sizing_571_2026-08-23.md):
    bound 11 of 22, cutting intended risk from ~$48 to as little as $15.

    Telemetry only — mirrors #570 (silent D-1 universe floors made visible).
    The cap VALUE, `MAX_POSITION_PCT`, the floor/rounding, and the zero-share
    reject are ALL untouched by this call; it only makes an already-happening
    truncation observable. OPERATOR RULING 2026-08-23 (docs/setups/safeguards.md):
    the cap stays as-is — "this will be solved with a large account eventually."

    `risk_dollars_intended` is the pre-cap sizing BUDGET (`equity * risk_pct`,
    read BEFORE the cap ever touches `shares` — see the caller). `risk_dollars_actual`
    is the realized dollar risk at the moment the cap bites (`shares_after_cap *
    risk_per_share`) — computed ONCE by the caller (it also persists to
    `mi_live_trades.risk_dollars_actual`) and passed in here rather than
    re-derived, so the one formula lives in one place.
    """
    fraction = (
        risk_dollars_actual / risk_dollars_intended
        if risk_dollars_intended else None
    )
    frac_str = f"{fraction:.0%}" if fraction is not None else "n/a"
    date_str = alert_date.isoformat() if alert_date else "unknown"
    summary = (
        f"{ticker} {date_str} account_mode={account_mode}: 20% notional "
        f"cap truncated {shares_before_cap}->{shares_after_cap} shares (entry=${entry_price:.2f} "
        f"equity=${equity:.0f} max_position=${max_position:.0f}) — risk "
        f"${risk_dollars_intended:.2f} intended -> ${risk_dollars_actual:.2f} actual "
        f"({frac_str} of intended)"
    )
    await log_audit_event(SIZING_NOTIONAL_CAP_TRUNCATED, summary)


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
    emit_cap_telemetry: bool = True,
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

    `emit_cap_telemetry` (#571, default True): whether a 20%-notional-cap
    truncation writes the `SIZING_NOTIONAL_CAP_TRUNCATED` audit event. The
    real caller (`live_tracker.py`, real money) leaves this at the default.
    The #482 shadow lane (`shadow_orb_tracker.py`) calls this same function
    with `account_mode=None` (its equity read is a display convenience, not a
    real order) and passes `emit_cap_telemetry=False` — without it, shadow
    candidates would silently pollute a signal meant to measure only real
    truncated trades.
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

    # ── 2026-08-16 (OPERATOR-SIGNED, THE LINE): protective stop = entry − 2R ──
    # R is DEFINED by the ORB and does not move: R = orb_high − orb_low. The ORB
    # low still defines R but is no longer the exit — the placed stop sits one
    # further R below it:
    #     stop = entry − 2R = 2·orb_low − orb_high
    # ⚠ Sizing is NOT separately halved. `shares = risk_dollars / risk_per_share`
    # below already divides by the stop DISTANCE, so doubling that distance
    # halves the share count by itself — dollar risk per trade is unchanged.
    # Adding an explicit halving here would QUARTER the position.
    # 🔴 The +2R profit target does NOT move with the stop: `scan_profit_triggers`
    # frames its target off entry − orb_low (the ORB R, via
    # `profit_target_r_per_share`), never off entry − stop — otherwise the target
    # silently drifts to +4R, which was never tested or approved.
    # Evidence (docs/roadmap/ep_profitability_program.md §0c-pre, matched 43
    # reconstructed HIGH trades at equal dollar risk): live ORB-low stop
    # SUM −6.0R median −1.00 vs 2R stop at half size SUM +11.4R median +0.33.
    # SSoT: docs/setups/magna53_ep.md + docs/setups/exit_discipline.md 2026-08-16.
    stop_loss_price = 2 * orb_low - orb_high
    if stop_loss_price <= 0:
        # Defensive: a 2R stop at/below $0 cannot be placed (needs ORB range
        # ≥ orb_low, i.e. a ~100% opening range — stop_too_wide (>1.5×ATR)
        # rejects long before this in practice).
        logger.warning(
            f"{ticker}: 2R stop ${stop_loss_price:.2f} <= 0 "
            f"(ORB H=${orb_high:.2f} L=${orb_low:.2f}) — skipping"
        )
        return None, (
            f"{SETUP_STOP_TOO_WIDE}: 2R stop ${stop_loss_price:.2f} <= $0 "
            f"(ORB H=${orb_high:.2f} L=${orb_low:.2f})"
        )
    risk_per_share = orb_high - stop_loss_price
    shares = math.floor(risk_dollars / risk_per_share)

    if shares <= 0:
        logger.warning(f"{ticker}: computed 0 shares, skipping")
        return None, (
            f"{SETUP_SIZE_TOO_SMALL}: ${risk_dollars:.0f} risk / "
            f"${risk_per_share:.2f} per-share < 1 share"
        )

    # Max 20% of account in one position. #571 (2026-08-23): this silently
    # truncates shares — the trade still fires, just smaller — with nothing
    # recording it besides the shares==0 reject below. `shares_before_cap` +
    # the telemetry call a few lines down make that visible; the cap VALUE
    # (MAX_POSITION_PCT), this formula, and the zero-share reject are all
    # UNCHANGED (THE LINE) — see _log_notional_cap_truncation's docstring and
    # the operator ruling in docs/setups/safeguards.md.
    max_position = equity * MAX_POSITION_PCT
    shares_before_cap = shares
    if shares * orb_high > max_position:
        shares = math.floor(max_position / orb_high)

    if shares <= 0:
        logger.warning(f"{ticker}: 0 shares after max-position cap (max=${max_position:.0f}, price=${orb_high:.2f})")
        return None, (
            f"{SETUP_PRICE_EXCEEDS_CAP}: ${orb_high:.2f}/share > "
            f"${max_position:.0f} (20% of ${equity:.0f})"
        )

    # #571: the dollar risk ACTUALLY placed, using the FINAL (possibly
    # cap-truncated) share count — distinct from `risk_dollars` above, which
    # is the pre-cap BUDGET (`equity * risk_pct`) and is never reassigned by
    # the cap. Equal to `risk_dollars` when the cap doesn't bind (modulo the
    # floor() in `shares = math.floor(risk_dollars / risk_per_share)`). `shares`
    # is final at this point (past both floor()s above) — computed ONCE here and
    # reused below for both the truncation-audit message and the persisted
    # `mi_live_trades.risk_dollars_actual` column, rather than re-derived twice.
    risk_dollars_actual = round(shares * risk_per_share, 2)

    if shares != shares_before_cap and emit_cap_telemetry:
        await _log_notional_cap_truncation(
            ticker=ticker,
            alert_date=today,
            account_mode=account_mode or current_account_mode(),
            equity=equity,
            max_position=max_position,
            entry_price=orb_high,
            shares_before_cap=shares_before_cap,
            shares_after_cap=shares,
            risk_dollars_actual=risk_dollars_actual,
            risk_dollars_intended=risk_dollars,
        )

    position_size = shares * orb_high
    limit_price = stop_limit_buy_price(orb_high)

    spec = {
        "ticker": ticker,
        "entry_price": orb_high,
        "limit_price": limit_price,
        "stop_loss_price": stop_loss_price,
        "shares": shares,
        "risk_dollars": round(risk_dollars, 2),
        "risk_dollars_actual": risk_dollars_actual,
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
        f"Order spec: {ticker} entry=${orb_high:.2f} stop=${stop_loss_price:.2f} "
        f"(2R below; ORB L=${orb_low:.2f}) "
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
        """('stop_limit', None) = the normal bracket; ('limit', px) = fallback.

        #500 asks ONE question — "has price already run past the ORB high, so a
        stop-limit trigger would be in-the-money and get cancelled?" — and until
        2026-08-07 it answered using the last TRADE only. The venue answers it using
        the OFFER, and on a thin first-minute gapper the two disagree:

            QNST 08-07  trigger 19.80   last 19.50    ASK 19.83  -> venue cancelled
            INSM 08-06  trigger 129.41  last 128.67   ASK 129.48 -> venue cancelled

        Both read "not through" on trades and "already through" on the ask; both were
        killed in single-digit milliseconds ("Unsolicited: Bad Stop 19.8" / "[6098]
        Stop Price Already Triggered"). Two high-quality setups lost in two days —
        INSM ran +33%, QNST posted record revenue +43% YoY.

        So the ASK becomes a second trigger for the SAME already-signed fallback. This
        is not a new entry rule: #500's intent covers this case exactly, it simply
        could not see it. The existing chase cap still bounds the result — on both
        names above the fallback lands at ~1.1x planned risk, well inside
        CHASE_RISK_INFLATION_CAP.

        ⚖ Gated on `entry_ask_aware` (mi_safeguard_state, default OFF) so the deploy
        changes nothing until the operator flips it — entry discipline is THE LINE.
        Fails CLOSED to the pre-existing behaviour on any error or missing quote: a
        quote we could not read must never be treated as a cheap offer.
        """
        latest = await alpaca.get_latest_trade(ticker)
        if latest and latest.get("price") and float(latest["price"]) > orb_high_f:
            return "limit", round(float(latest["price"]) * 1.002, 2)

        if await _ask_aware_entry_enabled(account_mode):
            try:
                quote = await alpaca.get_latest_quote(ticker)
                ask = float((quote or {}).get("ask") or 0)
                if ask > orb_high_f:
                    await log_audit_event(
                        "entry_ask_above_trigger",
                        f"{ticker} [{account_mode}]: ask ${ask:.2f} > ORB high "
                        f"${orb_high_f:.2f} — limit fallback (a stop there is cancelled "
                        f"by the venue)",
                        json.dumps({
                            "ticker": ticker, "orb_high": orb_high_f, "ask": ask,
                            "last_trade": (latest or {}).get("price"),
                            "account_mode": account_mode,
                        }),
                    )
                    return "limit", round(ask * 1.002, 2)
            except Exception as e:
                logger.warning(f"{ticker}: ask-aware entry check failed, using stop-limit: {e}")

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
            _jsonb_param(order),  # #216: codec single-encodes; do NOT pre-dumps
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
                _jsonb_param({"parent_entry_order": entry_order_id}),  # #216: codec single-encodes; do NOT pre-dumps
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
    filled_qty: float | None = None,
) -> dict:
    """
    Attempt re-entry for a Day 1 trade that was stopped out.
    Shared by both WebSocket handler and polling fallback.

    Uses price-aware logic: if current price > ORB high, places a limit buy
    instead of a stop-limit (which would never trigger).

    `filled_qty` (#588, 2026-08-24): the stop order's ACTUAL filled quantity,
    used ONLY to record the exit leg. RECORDING, not control flow — it never
    touches the R3 gate, the re-entry decision, remaining_shares or status.

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
    orb_high = trade["orb_high"]
    orb_low = trade["orb_low"]
    stop_loss_price = trade["stop_price"]

    # #588 (2026-08-24) — the stop leg must record the shares that ACTUALLY sold.
    # This booked `remaining_shares` blind. ETON 2026-08-14: the +2R carve-out had
    # placed a RESTING limit for 5 of 17 at 09:35 and it did not fill until 15:58,
    # so at 09:45 `remaining_shares` was still 17 (the deferred-commit pattern —
    # remaining only drops when the partial COMMITS). The 12-share stop fill was
    # therefore written as 17, and when the limit finally filled its 5 were counted
    # a second time: sum(exits.shares) = 22 on a 17-share trade, the booked P&L
    # $0.76 light on a winner, and every downstream `mi_sell_discipline_records`
    # figure inheriting it. PLTR escaped on both counts — day 14 (a different write
    # path) AND its partial had committed two weeks earlier.
    # Netting `get_pending_exit_qty` is the SAME subtraction `update_stop` already
    # applies for exactly this reason. `shares` feeds the exit leg, its P&L and the
    # Telegram text. With no resting exit order this is byte-identical to the old
    # behaviour. (#591 then made the SAME subtraction decide whether the row closes
    # at all — see the stay-open guard below.)
    tracked_remaining = int(trade["remaining_shares"] or 0)
    held = await get_pending_exit_qty(trade_id)
    # A 0 / missing quantity is UNKNOWN, not "sold nothing" — the WS payload falls
    # back to 0 when the broker sends no filled_qty, and recording a 0-share stop
    # leg would lose the trade's whole loss.
    if filled_qty is not None and int(filled_qty) > 0:
        shares = int(filled_qty)
    else:
        shares = max(tracked_remaining - held, 0)
    if shares != tracked_remaining:
        await log_audit_event(
            "stop_leg_shares_netted",
            f"{ticker}: stop leg recorded {shares} sh, not the tracked "
            f"{tracked_remaining} ({held} sh held by a resting exit order)",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "account_mode": account_mode,
                "tracked_remaining": tracked_remaining,
                "pending_exit_qty": held,
                "filled_qty": None if filled_qty is None else int(filled_qty),
                "recorded_shares": shares,
                "source": source,
            }),
        )

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

    # ── #591 (operator ruling 2026-08-24) — do NOT close a row while shares remain ──
    # ETON 2026-08-14 (live money): the 12-share stop filled at 09:45 and this
    # function closed the row at `remaining_shares = 0` while a +2R carve-out limit
    # for the other 5 was still RESTING at the broker. It did not fill until 15:58,
    # so for six hours the books said flat while five real shares sat live; they
    # filled for +$21.89 and the accounting only re-converged by luck. Put to the
    # operator as a fork (keep it open vs cancel the resting order) he answered
    # "if profit take is pending then why close it?" — it is a BUG, not a design
    # choice. His ruling is the authority for this branch and nothing wider.
    #
    # The row now stays OPEN at the shares still outstanding; whatever exit resolves
    # them closes it on the real final state (`_finalize_partial_exit_locked` closes
    # at zero, #566). Deliberately the SAME trigger `_process_stop_fill` has used
    # since #566 — `new_remaining > 0`, not `held > 0`. Path divergence between the
    # websocket and polling stop-fill handlers is the root cause of this whole bug
    # family (#566 fixed the WS path; #588 found polling still broken), so the two
    # must branch identically. That makes this a SUPERSET of the literal ruling: it
    # also holds the row open when shares remain and no exit order is working, which
    # is the state #566 already produces on the WS path.
    #
    # `held > 0` while `new_remaining == 0` means the broker's stop consumed shares
    # our `mi_live_orders` mirror still has reserved — the mirror is stale, and per
    # ADR 0008 a confirmed broker event beats the mirror. Close, and say so loudly
    # rather than inflating remaining_shares to paper over it.
    #
    # This branch returns BEFORE the re-entry logic on purpose: re-entry is a
    # full-stop-out concept, and buying on top of shares still held would double the
    # position — the identical gate `_process_stop_fill` applies via `full_stop_out`.
    new_remaining = max(tracked_remaining - shares, 0)
    if held > 0 and new_remaining == 0:
        await log_audit_event(
            "pending_exit_mirror_stale",
            f"{ticker}: stop fill of {shares} sh consumed the whole tracked "
            f"{tracked_remaining} while {held} sh were still reserved by a pending "
            f"exit order — closing on the broker event (ADR 0008), mirror is stale",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "account_mode": account_mode,
                "tracked_remaining": tracked_remaining,
                "pending_exit_qty": held, "recorded_shares": shares,
                "source": source,
            }),
        )
    if new_remaining > 0:
        total_pnl_so_far = sum(ex.get("pnl", 0) for ex in exits)
        async with pool.acquire() as conn:
            # broker-confirmed: the stop_order_id NULL records a stop the CALLER
            # already confirmed filled at the broker (_check_day1_reentry proceeds
            # only on get_order status=='filled'; the WS path IS the fill event) —
            # that leg is consumed and its pointer is dead. status stays 'filled':
            # this is the opposite of a demotion, the row stays OPEN.
            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'filled', exits = $2::jsonb,
                    remaining_shares = $3, total_pnl = $4,
                    stop_order_id = NULL
                WHERE id = $1
            """, trade["id"], exits, new_remaining, total_pnl_so_far)
        await log_audit_event(
            "stop_fill_position_stays_open",
            f"{ticker}: stop sold {shares} of {tracked_remaining} sh — trade stays "
            f"OPEN at {new_remaining} sh ({held} sh held by a working exit order); "
            f"no close, no re-entry",
            json.dumps({
                "trade_id": trade["id"], "ticker": ticker,
                "account_mode": account_mode,
                "stop_fill_price": float(stop_fill_price),
                "recorded_shares": shares,
                "tracked_remaining": tracked_remaining,
                "new_remaining": new_remaining,
                "pending_exit_qty": held,
                "att1_pnl": float(pnl),
                "source": source,
            }),
        )
        await send_telegram_message(
            f"{mode_prefix(account_mode)}❌ *Stopped out:* {ticker} @${stop_fill_price:.2f}\n"
            f"P&L: ${pnl:+,.2f} | stop hit — {shares} of {tracked_remaining} sh\n"
            f"{new_remaining} sh remain — position stays open (resting exit still working)"
        )
        logger.info(
            f"Day 1 stop-out ({source}): {ticker} @${stop_fill_price:.2f}, "
            f"{shares} of {tracked_remaining} sold — trade stays OPEN at {new_remaining} sh"
        )
        return {
            "ticker": ticker, "action": "stays_open",
            "remaining_shares": new_remaining, "pending_exit_qty": held,
        }

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
            _jsonb_param(new_order),  # #216: codec single-encodes; do NOT pre-dumps
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
        # #588: the fetched order already carries the filled quantity — dropping it
        # was the live hole that let the ETON shape recur on this path.
        result = await attempt_day1_reentry(
            trade["id"], stop_fill_price, source="polling",
            filled_qty=stop_order.get("filled_qty") or None,
        )
        results.append(result)

    return results


# ── Stop Management ──────────────────────────────────────────────────────────


# ── #591 pending-exit vocabulary — SSoT, do not hand-copy (money-path) ──────
# Alpaca's raw SDK enum value for a cancelled order is 'canceled' (single-L —
# confirmed via alpaca.trading.enums.OrderStatus.CANCELED.value). Two writers
# put status into mi_live_orders and they disagree on spelling:
# `reconcile_order_states` (below) writes `_canonical_order_status(alpaca_order
# ["status"])` straight through — that helper only lowercases, it never
# respells — so it CAN write the raw single-L 'canceled'. `_handle_cancel_or_reject`
# (trade_stream.py) normalizes its own writes to the double-L 'cancelled' first.
# Both spellings can therefore be sitting in the same column depending which
# path wrote a row last, so every "is this exit order still holding shares"
# check must exclude both — miss one and a single-l cancelled exit order
# counts as pending FOREVER, and every future partial/full exit on that trade
# silently no-ops (`partial_exit_aborted`, `stage=dedup_pending_exit`) with no
# operator-visible alarm.
#
# The first fix (`get_pending_exit_qty`) shipped 2026-08-24 as one of three
# hand-copies of this exact tuple; `execute_partial_exit`'s and
# `execute_full_exit`'s dedup checks were still single-l-blind. Query through
# this constant — never hand-copy the literal tuple again; enforcement is
# `tests/test_pending_exit_terminal_statuses_ssot.py`.
PENDING_EXIT_TERMINAL_STATUSES = frozenset({
    "filled", "cancelled", "canceled", "rejected", "expired",
})


async def get_pending_exit_qty(trade_id: int) -> int:
    """Sum of qty across non-terminal partial/full-exit orders for `trade_id`.

    Single source of truth for "shares Alpaca is currently holding for a
    pending sell." Callers that size a stop against `mi_live_trades.remaining_shares`
    must subtract this — without it, the deferred-commit pattern (CLAUDE.md
    2026-05-05) leaves remaining_shares at the pre-partial value and the
    stop-placement request collides with held_for_orders. FTRE 2026-05-09
    was the trigger; sync_positions Path C orphan remediation has the same
    structural exposure.

    Terminal-status set is `PENDING_EXIT_TERMINAL_STATUSES` (see its comment,
    directly above, for why both cancel spellings matter — money-path, not a
    typo). Enumerated against the live and paper book before the 2026-08-24
    fix shipped: it moved the pending quantity on ZERO trades
    (`scripts/probes/_591_state_capture.sql` Q2: every purpose-labelled exit
    order in the book is `filled`).
    """
    # #621: timeout only — a raise here (including a new TimeoutError) is left
    # to propagate exactly as any other DB error already does. Do NOT catch it
    # and fail open to 0: that would UNDER-count pending exits, oversize the
    # stop request, and reproduce the FTRE 5/9 class of bug (Alpaca rejects on
    # insufficient qty → naked), which is worse than the existing raise.
    pool = await get_pool()
    async with pool.acquire(timeout=_REPROTECT_DB_TIMEOUT) as conn:
        held = await conn.fetchval("""
            SELECT COALESCE(SUM(qty)::int, 0) FROM mi_live_orders
            WHERE trade_id = $1
              AND purpose IN ('partial_exit', 'full_exit')
              AND status != ALL($2::text[])
        """, trade_id, list(PENDING_EXIT_TERMINAL_STATUSES), timeout=_REPROTECT_DB_TIMEOUT)
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


def _infer_stop_source(entry_price, old_stop_price, new_stop_price, eps: float) -> str:
    """Shared inference used when the caller (trade_stream's decoupled WS handler)
    has no exit_logic.ExitStep.stop_source to hand us. ORDER MATTERS (#560 review):
    an UNCHANGED price must be checked FIRST — a morning re-issue at the same price
    (documented in CLAUDE.md: SMCI 07-22..07-24, 9:35 ET, $28.50 -> $28.50) can sit
    ABOVE entry from an earlier breakeven/trail move, and checking entry-relative
    position first would misreport that stale-but-unchanged stop as "the trail just
    rose" — a move that did not happen this call."""
    if new_stop_price is None:
        return "unknown"
    if old_stop_price is not None and abs(new_stop_price - old_stop_price) <= eps:
        return "refresh"
    if entry_price is not None and abs(new_stop_price - entry_price) <= eps:
        return "breakeven"
    if entry_price is not None and new_stop_price > entry_price + eps:
        return "trail"
    return "hard_stop"


_SOURCE_LABEL = {
    "trail": "The 10/20-day moving-average trail",
    "breakeven": "The breakeven stop",
    "giveback_floor": "The profit-lock floor",
    "refresh": "The overnight stop",
    "hard_stop": "The original stop",
    "unknown": "The stop",
}


def describe_stop_move(
    *,
    entry_price: float | None,
    hard_stop: float | None,
    old_stop_price: float | None,
    new_stop_price: float | None,
    stop_source: str | None = None,
    brief: bool = False,
) -> str:
    """Plain-English, operator-facing explanation of WHY a stop moved (#560, 2026-08-12).

    Two call sites need this and see different amounts of context:
      - live_tracker knows `stop_source` exactly (exit_logic.ExitStep.stop_source —
        the ladder input that actually set the price). Calls with `brief=False`
        (default) — it is the FIRST/authoritative message for a given move.
      - trade_stream reacts to a broker WebSocket event with no ladder context at
        all, so `stop_source` is None there and gets INFERRED from price comparison
        (`_infer_stop_source`). The inference is safe: on every live caller (both in
        live_tracker.py) the ladder never passes ema/pivot/character trail modes or
        the giveback hook (exit_logic.py docstrings — those are opt-in/shadow-only,
        no live caller passes them), so a raised stop can only be the moving-average
        trail or the breakeven floor. Calls with `brief=True` — it is a SAFETY-NET
        confirmation that may fire alongside live_tracker's own message for the same
        move; the full sentence would just repeat what the first message already
        said, so `brief=True` returns one short line instead (#560 review: the two
        messages were duplicating a whole paragraph verbatim).

    Ties every "can this still lose" claim to the STOP PRICE, never to certainty —
    "if this stop fills" — because a gap can defeat any stop (the #507 class: text
    promising something the system cannot structurally guarantee is worse than no
    text). Never raises: missing prices degrade to a generic but still-true line
    rather than an exception (this only decorates a Telegram message; it must never
    block the stop mutation it is describing).
    """
    try:
        eps = 0.01
        if stop_source is None:
            stop_source = _infer_stop_source(entry_price, old_stop_price, new_stop_price, eps)

        label = _SOURCE_LABEL.get(stop_source, _SOURCE_LABEL["unknown"])
        above_entry = (
            entry_price is not None and new_stop_price is not None
            and new_stop_price > entry_price + eps
        )
        at_entry = (
            entry_price is not None and new_stop_price is not None
            and abs(new_stop_price - entry_price) <= eps
        )

        if brief:
            if above_entry:
                return f"{label} — stop is above your ${entry_price:.2f} entry — a fill here banks a gain."
            if at_entry:
                return f"{label} — stop is at your ${entry_price:.2f} entry — a fill here is a scratch."
            return f"{label} confirmed live at the broker."

        if stop_source == "trail":
            why = "the 10/20-day moving-average trail rose"
            if above_entry:
                why += f" above your ${entry_price:.2f} entry"
        elif stop_source == "breakeven":
            why = "the trade ran far enough to arm the breakeven stop"
        elif stop_source == "giveback_floor":
            why = "the run-up armed the profit-lock floor"
        elif stop_source == "refresh":
            why = "the overnight stop expired and was reissued at the same price"
        elif stop_source == "hard_stop":
            why = "the original stop was (re)placed"
        else:
            why = "the stop changed"
        why = why[0].upper() + why[1:]

        if above_entry:
            gain = new_stop_price - entry_price
            tail = f" — a fill here banks ${gain:.2f}/share"
            if hard_stop is not None and entry_price > hard_stop:
                r = gain / (entry_price - hard_stop)
                tail += f", {r:.1f}R beyond breakeven"
        elif at_entry:
            tail = " — if this stop fills, it's a scratch"
        else:
            tail = ""

        return why + tail + "."
    except Exception as e:
        # Never let a presentation-text bug block the Telegram for a stop
        # mutation that has ALREADY happened at the broker — degrade to a
        # generic-but-true line and log loud so the formatting bug still surfaces.
        logger.warning(f"describe_stop_move: formatting failed ({e}) — generic text used")
        return "Position protected."


# ── #600: raise-only floor for RE-PROTECT placements (no live stop to refuse against)
# `update_stop`'s 2026-08-10 floor compares a requested move against the LIVE
# broker stop and REFUSES a non-raise. A re-protect (coverage place branch, sync
# orphan remediation, the WS cancel-restore paths, `_stop_refresh` after a stop
# died) has no live stop to refuse against — it is placing precisely because the
# stop is GONE. The same signed rule (a protective long stop is raise-only) has
# to be applied the other way round there: the price we place is never BELOW
# the last level the broker actually held, read off the DB's own stop pointer
# (`get_order` returns terminal orders with their `stop_price`), and with no
# broker truth at all we place at the DB price exactly as before.
#
# NEVER A REFUSAL. An unprotected position is strictly worse than a stop that
# sits ~1R low, so every "cannot read" path (NULL pointer, get_order → None,
# no stop_price on the order, a raising DB read) returns the DB price and the
# placement goes ahead. The floor only ever RAISES the price it is handed.
#
# Why the DB price can be low at all: execute_partial_exit's breakeven replace
# deliberately keeps the successor stop POINTER while WITHHOLDING stop_price
# when the replace's outcome was unconfirmed (the DB understating protection is
# the safe direction — pinned in test_resting_mode_breakeven_548.py), and the
# market-mode fold-in never writes stop_price at all. So `stop_price` can sit
# at the ORIGINAL stop while the broker rested at breakeven; a re-protect that
# trusted it re-armed the position ~1R below where it was (FIGS 2026-08-07 was
# the real-money analog of this pathology via a different trigger).
#
# Statuses the floor honours: anything the broker ever ACCEPTED (live or
# terminal — a cancelled/expired/replaced/filled stop's price WAS protection).
# `rejected` never rested, so its price was never protection and is ignored.
_REPROTECT_FLOOR_IGNORED_STATUSES = frozenset({"rejected"})
_REPROTECT_FLOOR_EVENT = "stop_reprotect_floor_applied"


def _floor_reprotect_price(base_price: float, broker_order: dict | None) -> tuple[float, dict]:
    """PURE (#600). The price a re-protect should place: `base_price` (what the
    caller would have placed — the DB stop_price, or the requested price) raised
    to the broker order's `stop_price` when that is readable and higher.

    Returns (price, info). `info["raised"]` is True only when the floor moved
    the price; `info["floor_source"]` says why it did or did not. Never raises,
    never returns a price below `base_price`.
    """
    base = float(base_price)
    info: dict = {
        "base_price": base, "broker_stop_price": None, "broker_status": None,
        "broker_order_id": None, "raised": False, "floor_source": None,
    }
    if not broker_order:
        info["floor_source"] = "no_broker_order"
        return base, info
    status = _canonical_order_status(broker_order.get("status"))
    info["broker_status"] = status
    info["broker_order_id"] = broker_order.get("id")
    if status in _REPROTECT_FLOOR_IGNORED_STATUSES:
        info["floor_source"] = f"ignored_status:{status}"
        return base, info
    raw = broker_order.get("stop_price")
    if raw is None:
        info["floor_source"] = "no_stop_price"
        return base, info
    try:
        broker_price = float(raw)
    except (TypeError, ValueError):
        info["floor_source"] = "unparseable_stop_price"
        return base, info
    info["broker_stop_price"] = broker_price
    if broker_price > base + 1e-9:
        info["raised"] = True
        info["floor_source"] = "broker_pointer"
        return broker_price, info
    info["floor_source"] = "base_not_below_broker"
    return base, info


async def _current_stop_pointer(trade_id: int) -> str | None:
    """The trade's CURRENT `stop_order_id`, read fresh (#600). A re-protect runs
    after the broker said there is no live stop, so an in-memory copy of the
    pointer may be stale; the row is the source of truth. FAIL-OPEN: a raising
    read returns None (→ no floor → the DB price is placed, exactly as before
    #600) — the position must still get its stop.

    #621: `pool.acquire()` and the query are timeout-bounded — this read used
    to be able to block forever (a hung Postgres, a saturated pool) directly in
    front of `place_stop_order`. A TimeoutError is just another exception this
    `except` already catches, so the fail-open path is unchanged.
    """
    try:
        pool = await get_pool()
        async with pool.acquire(timeout=_REPROTECT_DB_TIMEOUT) as conn:
            return await conn.fetchval(
                "SELECT stop_order_id FROM mi_live_trades WHERE id = $1",
                trade_id, timeout=_REPROTECT_DB_TIMEOUT)
    except Exception as e:  # loud-ok: fail-open by design — the placement still happens
        logger.warning(
            f"_current_stop_pointer: read failed for trade {trade_id} ({e}) — "
            f"re-protect floor unavailable, placing at the DB price"
        )
        return None


async def _preserve_dead_stop_price(
    trade_id: int,
    order_id: str,
    stop_price: float | None,
    status: str | None,
    account_mode: str,
) -> None:
    """#600 fork 2 (2026-09-04). Runs at the ONE place T1.5a's
    `cancel_or_reject_null` fail-safe discards the `stop_order_id` pointer
    (`trade_stream._handle_cancel_or_reject` section 2, UNCHANGED by this) —
    captures the DEAD order's own broker-held price so a later re-protect with
    no live pointer (`_apply_reprotect_floor`'s `consult_dead_stop` path) still
    has something to floor against, instead of going dark exactly when the
    pointer disappears — the common intraday path #600 could not reach.

    A PRICE plus the STATUS it died in — never an order id treated as live.
    `_read_preserved_dead_stop` hands both straight back to
    `_floor_reprotect_price`, so a preserved 'rejected' stop (never rested) is
    ignored by the SAME rule as a live one — one place to keep that rule, not
    two.

    RATCHETED, strictly-higher-only, and ATOMIC: the UPDATE's WHERE clause only
    matches when the new price is strictly above the currently preserved one
    (or none is preserved yet), so price/order_id/status/timestamp always move
    together — no window where the price reflects one dead order and the
    status reflects another. A live protective stop only ever rises during a
    trade's life (the 08-10 signed rule), so the highest dead stop this trade
    ever held is always the correct floor; an out-of-order WS delivery can
    only fail to raise it, never walk it down. A tie (new price == preserved
    price) intentionally does NOT overwrite — the first-recorded status for a
    given price level stays authoritative rather than flip-flopping.

    Scoped by trade_id (one row per position): a new trade starts at NULL, so
    nothing leaks across positions or across a flat-then-re-enter on the same
    ticker. Never explicitly cleared on a later live placement — whenever a
    live pointer exists, `_apply_reprotect_floor` never even reads this
    column, so a stale-but-lower preserved value can never wrongly floor a
    placement that already has real broker truth.

    Fails open silently on any write error — a later re-protect just finds
    nothing preserved and places at the DB price, exactly as before this
    change.
    """
    if stop_price is None:
        return
    try:
        price = float(stop_price)
    except (TypeError, ValueError):
        return
    try:
        pool = await get_pool()
        async with pool.acquire(timeout=_REPROTECT_DB_TIMEOUT) as conn:
            written = await conn.fetchval("""
                UPDATE mi_live_trades SET
                    dead_stop_price = $2,
                    dead_stop_order_id = $3,
                    dead_stop_status = $4,
                    dead_stop_recorded_at = NOW()
                WHERE id = $1
                  AND (dead_stop_price IS NULL OR $2 > dead_stop_price)
                RETURNING id
            """, trade_id, price, order_id, status,
                timeout=_REPROTECT_DB_TIMEOUT) is not None
    except Exception as e:  # loud-ok: fail-open — the #600 floor just finds nothing later
        logger.warning(
            f"_preserve_dead_stop_price: write failed for trade {trade_id} ({e}) — "
            f"a later re-protect will have nothing to floor against for this cancellation"
        )
        return
    if written:
        await log_audit_event(
            "dead_stop_price_preserved",
            f"trade #{trade_id} [{account_mode}]: dead stop {order_id[:8]} "
            f"(status={status}) preserved at ${price:.2f} for the #600 floor",
            json.dumps({
                "trade_id": trade_id, "account_mode": account_mode,
                "order_id": order_id, "status": status, "price": price,
            }),
        )


async def _read_preserved_dead_stop(trade_id: int) -> dict | None:
    """#600 fork 2 (2026-09-04). The dead-stop price + status
    `_preserve_dead_stop_price` preserved at the moment the pointer was
    nulled — the only broker truth left on the common intraday path, where
    `stop_order_id` is already NULL by the time a re-protect runs. Returned in
    the same shape `_floor_reprotect_price` already expects (`id`/`status`/
    `stop_price`), so a preserved 'rejected' stop is ignored by the exact same
    rule as a live one. FAIL-OPEN: any read error, or nothing preserved,
    returns None — the caller's existing no-truth path (place at base,
    unchanged) is exactly what runs.
    """
    try:
        pool = await get_pool()
        async with pool.acquire(timeout=_REPROTECT_DB_TIMEOUT) as conn:
            row = await conn.fetchrow(
                "SELECT dead_stop_price, dead_stop_status, dead_stop_order_id "
                "FROM mi_live_trades WHERE id = $1", trade_id,
                timeout=_REPROTECT_DB_TIMEOUT,
            )
    except Exception as e:  # loud-ok: fail-open — the caller places at base, unchanged
        logger.warning(
            f"_read_preserved_dead_stop: read failed for trade {trade_id} ({e}) — "
            f"no dead-stop fallback, placing at the caller's base price"
        )
        return None
    if not row or row["dead_stop_price"] is None:
        return None
    return {
        "id": row["dead_stop_order_id"],
        "status": row["dead_stop_status"],
        "stop_price": row["dead_stop_price"],
    }


async def _apply_reprotect_floor(
    trade_id: int,
    ticker: str,
    base_price: float,
    stop_order_id: str | None,
    account_mode: str,
    *,
    site: str,
    broker_order: dict | None = None,
    fetch: bool = True,
    consult_dead_stop: bool = False,
) -> float:
    """#600 — the price a re-protect should place, floored to the last level the
    broker held. Reads `get_order(stop_order_id)` unless the caller already has
    the order dict (`fetch=False` + `broker_order`). Audits + warns ONLY when the
    floor actually raised the price; every no-truth path is a quiet info line
    and the unchanged `base_price` — the placement always goes ahead.

    `consult_dead_stop` (#600 fork 2, 2026-09-04): when the live broker read
    above still leaves `order` as None (no pointer, unreadable, or the caller
    had none to hand), fall back to the price `_handle_cancel_or_reject`
    preserved at the moment it nulled the pointer — the ONLY source of broker
    truth left on the common intraday cancel/reject path. Opt-in and additive:
    default False reproduces #600's exact original behaviour (every existing
    caller and test), and even when True this can only raise `base_price` —
    routed through the SAME `_floor_reprotect_price` rules, so a preserved
    'rejected' stop is still ignored, and no data ever refuses the placement.
    """
    base = float(base_price)
    order = broker_order
    if fetch and order is None and stop_order_id:
        try:
            order = await alpaca.get_order(stop_order_id, account_mode=account_mode)
        except Exception as e:  # loud-ok: fail-open — floor unavailable, place at base
            logger.warning(
                f"{site}: {ticker} broker read of stop {stop_order_id} raised ({e}) — "
                f"re-protect floor unavailable, placing at ${base:.2f}"
            )
            order = None
    price, info = _floor_reprotect_price(base, order)
    if not info["raised"] and order is None and consult_dead_stop:
        try:
            dead_stop = await _read_preserved_dead_stop(trade_id)
        except Exception as e:  # loud-ok: redundant fail-open — _read_preserved_dead_stop
            # already fails open internally; this belt-and-suspenders guard means a future
            # bug there still cannot block a placement here.
            logger.warning(
                f"{site}: {ticker} dead-stop fallback read raised ({e}) — "
                f"placing at ${base:.2f}"
            )
            dead_stop = None
        if dead_stop:
            price, info = _floor_reprotect_price(base, dead_stop)
            if info["raised"]:
                info["floor_source"] = f"preserved_{info['floor_source']}"
    if not info["raised"]:
        logger.info(
            f"{site}: {ticker} re-protect at ${price:.2f} "
            f"(floor {info['floor_source']}, pointer={stop_order_id})"
        )
        return price
    _src_id = info["broker_order_id"] or stop_order_id
    logger.warning(
        f"{site}: {ticker} DB stop ${base:.2f} is BELOW the last broker stop "
        f"${price:.2f} ({_src_id}, status={info['broker_status']}, "
        f"source={info['floor_source']}) — re-protecting at ${price:.2f}, "
        f"never lower (raise-only)"
    )
    await log_audit_event(
        _REPROTECT_FLOOR_EVENT,
        f"{ticker}: re-protect price raised ${base:.2f} → ${price:.2f} to the last "
        f"broker stop ({_src_id[:8] if _src_id else '?'}, "
        f"status={info['broker_status']}) — DB stop_price was stale-low",
        json.dumps({
            "trade_id": trade_id, "ticker": ticker, "account_mode": account_mode,
            "site": site, "db_price": base, "placed_price": price,
            "broker_stop_price": info["broker_stop_price"],
            "broker_order_id": info["broker_order_id"],
            "broker_status": info["broker_status"],
            "floor_source": info["floor_source"],
        }),
    )
    return price


async def update_stop(
    trade_id: int, new_stop_price: float, stop_source: str | None = None,
) -> bool:
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

    `stop_source` (#560, 2026-08-12): optional label from exit_logic.ExitStep
    ('trail' / 'breakeven' / 'hard_stop' / 'giveback_floor') naming WHICH ladder
    input actually set `new_stop_price`. PRESENTATION ONLY — feeds the
    operator-facing "Stop confirmed" Telegram (via describe_stop_move) on the
    retry-recovered path below; never affects sizing, price, or control flow.
    None (the morning stop-refresh call site) makes describe_stop_move infer a
    label from the prices themselves.
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

    # ── Raise-only floor against the CURRENT BROKER stop (bug fix 2026-08-10) ──
    # A protective long stop is raise-only — signed intent; see the breakeven
    # branch comment at the `_be_outcome == "live"` write in
    # execute_partial_exit ("a stale (lower) value would let a later trail
    # pass cancel this stop and re-place LOWER — loosening protection"). The
    # DB is NOT authoritative for the live stop price: the #548 resting-mode
    # "uncertain" branch deliberately persists the successor stop POINTER
    # while WITHHOLDING stop_price (the DB understating protection is the safe
    # direction — pinned in test_resting_mode_breakeven_548.py; do not "fix"
    # that branch), so trade["stop_price"] can sit BELOW the stop actually
    # resting at the broker. Callers decide "should I move?" against the DB;
    # THIS function is the one that talks to the broker, so the floor lives
    # here — every current and future caller inherits it.
    #
    # FAIL DIRECTION — DELIBERATE: if the broker stop cannot be read
    # (get_order → None, or a non-terminal order carrying no stop_price), we
    # cannot prove the requested move is a raise, so we DO NOT act. Leaving
    # the existing stop untouched keeps protection exactly what it was — the
    # safe direction; proceeding blind is precisely how this defect loosens
    # protection. Never a silent swallow: logger.warning + a
    # stop_update_aborted audit row every time. A TERMINAL old stop
    # (cancelled/expired/rejected/replaced/done_for_day/filled) means there is
    # nothing live to floor against — that is the re-protect path
    # (_stop_refresh re-placing at the DB price after a stop died) and the
    # floor deliberately does not apply there. No pointer at all
    # (stop_order_id NULL, the post-remediation naked case) skips the floor
    # the same way.
    if old_stop_id:
        broker_order = await alpaca.get_order(old_stop_id, account_mode=account_mode)
        broker_status = _canonical_order_status(
            broker_order.get("status") if broker_order else None)
        old_stop_terminal = broker_order is not None and (
            broker_status in _STOP_DEAD_STATUSES or broker_status == "filled")
        if old_stop_terminal:
            # #600: the re-protect shape — nothing LIVE to refuse against, but the
            # dead stop's own price is the last level the broker held. Never place
            # BELOW it (raise-only, the same signed rule the refuse-floor below
            # enforces for live stops); never refuse (an unprotected position is
            # worse than a stop that is ~1R low). Unchanged whenever the requested
            # price already meets it — `_stop_refresh` re-placing at the DB price
            # after a DAY leg expired is exactly that case.
            new_stop_price = await _apply_reprotect_floor(
                trade_id, ticker, new_stop_price, old_stop_id, account_mode,
                site="update_stop.reprotect_after_dead_stop",
                broker_order=broker_order, fetch=False,
            )
        if not old_stop_terminal:
            broker_stop_raw = broker_order.get("stop_price") if broker_order else None
            if broker_stop_raw is None:
                logger.warning(
                    f"update_stop: {ticker} broker stop {old_stop_id} unreadable — "
                    f"cannot prove ${new_stop_price:.2f} is a raise; existing stop "
                    f"left untouched"
                )
                await log_audit_event(
                    "stop_update_aborted",
                    f"{ticker}: broker stop {old_stop_id} unreadable — cannot prove "
                    f"${new_stop_price:.2f} is a raise; existing stop left untouched",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker,
                        "reason": "broker_stop_unreadable",
                        "old_stop_id": old_stop_id,
                        "broker_status": broker_status,
                        "db_stop_price": old_stop_price,
                        "new_stop_price": new_stop_price,
                    }),
                )
                return False
            broker_stop_price = float(broker_stop_raw)
            if new_stop_price <= broker_stop_price + 1e-9:
                logger.warning(
                    f"update_stop: {ticker} refused — requested ${new_stop_price:.2f} "
                    f"is not above the live broker stop ${broker_stop_price:.2f} "
                    f"({old_stop_id}); raise-only, existing stop left untouched"
                )
                await log_audit_event(
                    "stop_update_aborted",
                    f"{ticker}: requested ${new_stop_price:.2f} is not above the live "
                    f"broker stop ${broker_stop_price:.2f} — raise-only floor; "
                    f"existing stop left untouched",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker,
                        "reason": "raise_only_floor",
                        "old_stop_id": old_stop_id,
                        "broker_stop_price": broker_stop_price,
                        "db_stop_price": old_stop_price,
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
        # #607 (2026-09-04): this is the TRANSIENT half of the old overloaded
        # `stop_update_failed` type — attempt 1 only, about to retry in 3s and
        # usually wins (see the #433 note below). Split out so no consumer has
        # to re-derive "was this the transient one?" from `attempt` in detail —
        # `stop_update_failed` itself is now reserved for the terminal case
        # (both attempts failed) a few lines down.
        await log_audit_event(
            STOP_UPDATE_RETRY_TRIGGERED,
            f"{ticker}: place_stop_order raised on first attempt — {type(e).__name__} — retrying in 3s",
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
            # #560 (2026-08-12): name WHY the stop moved (trail/breakeven/refresh)
            # instead of just the new price — the operator asked why every time.
            _reason_text = describe_stop_move(
                entry_price=float(trade["entry_price"]) if trade.get("entry_price") is not None else None,
                hard_stop=float(trade["hard_stop"]) if trade.get("hard_stop") is not None else None,
                old_stop_price=old_stop_price,
                new_stop_price=new_stop_price,
                stop_source=stop_source,
            )
            _was_line = (
                f" (was ${old_stop_price:.2f})"
                if old_stop_price is not None and abs(old_stop_price - new_stop_price) > 0.01
                else ""
            )
            await send_telegram_message(
                f"{mode_prefix(account_mode)}✅ *Stop confirmed:* {ticker} now ${new_stop_price:.2f}{_was_line}\n"
                f"{_reason_text}\n"
                f"_Recovered from a brief broker hiccup on the first attempt — protection never lapsed._"
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
            # #607 (2026-09-04): the TERMINAL half of the old overloaded type —
            # both attempts raised, nothing live to point at. `stop_update_failed`
            # is reserved for exactly this case now (see STOP_UPDATE_RETRY_TRIGGERED
            # above for the transient attempt-1-only case); every reader can treat
            # this type name alone as "genuinely naked," no `attempt` lookup needed.
            await log_audit_event(
                STOP_UPDATE_FAILED,
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
            _jsonb_param(new_order),  # #216: codec single-encodes; do NOT pre-dumps
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


async def _consecutive_partial_exit_failures(
    account_mode: str,
    floor_days: int = _PARTIAL_EXIT_BREAKER_WINDOW_DAYS,
) -> int:
    """Count GENUINE partial-exit failures SINCE THE LAST SUCCESSFUL partial exit, IN `account_mode`.

    ⚠ **PER-MODE SINCE 2026-08-08 (#525, operator-signed).** This query carried NO account_mode
    filter, so **a PAPER success closed the LIVE breaker**. Measured at the time of the fix:
    **12 of the 14 `partial_exit_committed` rows that had ever reset this breaker were PAPER**
    (only 2 live), and **all 5 recorded genuine failures were PAPER**. A simulated success was
    switching off a real safety stop.

    It violates invariant 3 of the dual-account safety backbone — *"account_mode filter on every
    trade query"* (`docs/architecture/dual_account.md`) — so this is a BUG FIX against a rule
    already signed, not a new criterion.

    **Attribution:** `mi_audit_log` has no `account_mode` column and these rows never wrote one
    into `detail`, so the mode is resolved two ways: the `account_mode` key written into `detail`
    from this commit onward, falling back to a join on `trade_id` → `mi_live_trades.account_mode`
    for every historical row. Both use regex extraction rather than `detail::json` because some
    rows carry malformed/truncated detail and a JSON cast would raise on them.

    **A row whose mode cannot be resolved COUNTS** — a breaker is a safety device, so an
    unattributable failure is treated as belonging to the mode being asked about. Over-counting
    delays trading; under-counting removes a stop.

    `partial_exit_breaker_reset` stays MODE-AGNOSTIC: it is a deliberate, audited operator action
    that clears the fault it names, and it should clear it everywhere.

    Success-aware breaker semantics (advisor 2026-05-29): a clean
    `partial_exit_committed` closes the breaker — only failures accrued *after*
    the most recent success count. This is the standard open→half-open→close
    model; a rolling fixed-window (the prior implementation) would stay open on
    stale already-remediated failures even after clean cycles resumed. `floor_days`
    bounds the lookback when there is NO recorded success yet (fresh system / never
    succeeded), so ancient history can't trip it.

    A `partial_exit_breaker_reset` row closes it the same way a success does
    (2026-08-04). Without one there was NO way out: the breaker only closed on a
    successful partial, and after the bracket-leg defect every partial failed — so
    the fix could not prove itself because the breaker opened by the bug it fixed
    still blocked the automatic path. The reset is a deliberate, audited row naming
    the fault it clears; it is not a silent bypass, and it clears nothing about WHY
    the failures happened — they stay in the log.

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
            r"""
            WITH tagged AS (
                SELECT a.created_at, a.event_type, a.detail,
                       COALESCE(
                         substring(a.detail from '"account_mode":\s*"([a-z]+)"'),
                         t.account_mode
                       ) AS mode
                  FROM mi_audit_log a
                  LEFT JOIN mi_live_trades t
                    ON t.id = NULLIF(substring(a.detail from '"trade_id":\s*(\d+)'), '')::int
                 WHERE a.event_type LIKE 'partial_exit%'
            )
            SELECT COUNT(*) AS n FROM tagged
            WHERE created_at > COALESCE(
                    (SELECT MAX(created_at) FROM tagged
                      -- a SUCCESS only closes the breaker for ITS OWN mode; a RESET is an
                      -- operator action and closes it for every mode.
                      WHERE (event_type = 'partial_exit_committed' AND mode = $2)
                         OR event_type = 'partial_exit_breaker_reset'),
                    NOW() - ($1 || ' days')::interval
                  )
              AND (mode = $2 OR mode IS NULL)   -- unattributable counts (fail safe)
              AND (
                event_type IN ('partial_exit_sell_failed', 'partial_exit_rollback_failed')
                OR (
                  event_type = 'partial_exit_aborted'
                  AND (detail LIKE '%"stage": "place_new_stop"%'
                       OR detail LIKE '%"stage": "verify_stop_live"%')
                )
              )
            """,
            str(floor_days), account_mode,
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


# ── #508 leg-safe stop reduction (2026-08-04) ─────────────────────────────────
# Alpaca REJECTS any qty change on an advanced-order leg (42210000, "qty cannot
# be changed for advanced orders") — and every MAGNA53 entry's stop IS an OTO
# bracket leg (place_bracket_order / place_limit_buy_with_stop). So the atomic
# replace that execute_partial_exit relies on can structurally NEVER reduce a
# bracket-leg stop. PLTR trade 307, 2026-08-04 — the first live +2R
# profit-trigger fire — failed exactly here (fail-safe: the rejected replace
# left the original leg live; nothing was harvested).
#
# Empirical basis — scripts/probes/_508_oto_leg_probe.py, paper, 2026-08-04:
#   T1  replace(leg, qty)                → REJECTED 42210000 (the PLTR bug)
#   T1b leg after the failed replace     → STILL LIVE (rejection is atomic)
#   T2  replace(leg, stop_price only)    → OK — price moves on legs still work
#   T2b the replacement order            → STILL order_class=oto (no detach)
#   T3  replace(replacement, qty)        → REJECTED 42210000 (once a leg,
#       always a leg — "detach via replace" is dead)
#   T4  2nd stop while the leg holds     → REJECTED 40310000 insufficient qty
#       (no over-cover transition; equally, a duplicate stop can never be
#       accepted while another one lives — the broker's share-reservation
#       system is itself the no-duplicate guard)
#   T5  market sell while the leg holds  → REJECTED 40310000 (can't sell first)
#   T6  cancel → cancel CONFIRMED +15ms → reservation released +78ms (the
#       release LAGS the confirm by ~60ms — the IBM 2026-05-27 race, measured)
#       → reduced stop accepted FIRST TRY at +87ms → partial sell accepted.
#
# CONCLUSION: for a bracket-leg stop, cancel-then-new is the ONLY mechanism
# Alpaca permits (T1/T3/T4/T5 close every alternative). What made IBM 5/27 a
# race was submitting the new stop BEFORE the share reservation cleared; this
# path GATES the submit on the broker's own release signal (qty_available),
# retries the reservation-lag rejection, and funnels every failure into the
# caller's existing abort machinery (post-lock _ensure_stop_coverage
# re-protect to broker truth). The position is unprotected only from
# cancel-confirm to new-stop-accept — measured ~72ms on paper — and that
# exposure is structural: no Alpaca ordering avoids it for a bracket leg.
_ADVANCED_ORDER_CLASSES = frozenset({"oto", "oco", "otoco", "bracket"})
_LEG_SAFE_CANCEL_CONFIRM_BUDGET_S = 3.0
# ── Share-release handshake before the partial SELL (2026-08-05, PLTR 307) ───
# Alpaca frees the shares a reduced stop no longer needs ASYNCHRONOUSLY, so the sell must
# wait on the broker's own `qty_available` signal. The budget was 3s (12 x 0.25s) and that
# was too tight at the open: PLTR's shares had not freed, the gate ABORTED, and — worse —
# aborting skipped the sell's own reservation-lag retry that exists for this exact case.
# Widened, and the gate now falls through to the sell instead of vetoing it.
_AVAIL_POLL_ATTEMPTS = 40          # 40 x 0.25s = 10s (was 12 = 3s)
_AVAIL_POLL_INTERVAL_S = 0.25
_SELL_RETRY_ATTEMPTS = 4           # was 2 — the lag outlived 2 attempts at the open
_SELL_RETRY_BACKOFF_S = 0.75       # was 0.5

_LEG_SAFE_RELEASE_BUDGET_S = 5.0
_LEG_SAFE_POLL_S = 0.1
_LEG_SAFE_STOP_ATTEMPTS = 4


def _is_stop_already_at_target(err: Exception) -> bool:
    """Alpaca 42210000 "order parameters are not changed" — the stop ALREADY has the qty and
    price we are asking for, so the reduction is a no-op, not a failure.

    ⚠ WHY THIS EXISTS — PLTR 307, 2026-08-05, a DEADLOCK on live money. The 09:30 attempt
    reduced the stop 6 → 4 successfully, then aborted before selling because the freed shares
    had not been released yet. Every retry from 09:35 onward then tried to reduce a stop that
    was ALREADY 4 @ $143.28, which Alpaca correctly rejects as a no-op — so the partial could
    never progress past a step it had already completed, and each attempt logged a
    `place_new_stop` abort, which the circuit breaker COUNTS. Three of those and the breaker
    would have closed the door on it permanently.

    Treating this as success is not a leniency: the broker is stating that the order already
    holds the parameters we requested, which is precisely the post-condition the replace exists
    to establish. Deliberately NARROW — it matches only the not-changed message, never a
    generic 42210000 (the advanced-order-leg rejection carries a different message and is
    matched separately by `_is_advanced_qty_rejection`).
    """
    msg = str(err).lower()
    return "parameters are not changed" in msg or "order parameters are not changed" in msg


def _is_advanced_qty_rejection(err: Exception) -> bool:
    """Alpaca 42210000 'qty cannot be changed for advanced orders' — the exact
    PLTR 2026-08-04 rejection. Deterministic + structural (the stop is a
    bracket leg), so retrying the replace is pointless; route to leg-safe."""
    msg = str(err).lower()
    return ("qty cannot be changed" in msg) or (
        "42210000" in msg and "advanced" in msg
    )


async def _replace_stop_leg_via_cancel_new(
    trade_id: int,
    ticker: str,
    old_stop_id: str,
    new_qty: int,
    stop_price: float,
    signal_type: str,
    account_mode: str,
) -> tuple[dict | None, dict]:
    """#508 / #523 — resize a BRACKET-LEG stop to `new_qty` shares via
    verified-cancel → reservation-release gate → new stop. See the
    "#508 leg-safe stop reduction" block comment further above (the
    `_ADVANCED_ORDER_CLASSES` / probe-table one) for why replace cannot work
    on a leg and why gating on qty_available closes the IBM 2026-05-27
    cancel+new race.

    THE SHARED MECHANISM behind two thin, direction-named callers:
      * `_reduce_stop_via_cancel_new` (#508, partial-exit) — new_qty is
        always <= the leg's current qty (shares are being sold off), so the
        release gate can only ever find MORE than enough available.
      * `_widen_stop_via_cancel_new` (#523, coverage repair) — new_qty is
        LARGER than the leg's current qty by construction (the leg is
        under-covering). The release gate is therefore NOT guaranteed to
        clear on qty alone — the widen caller must verify broker truth has
        enough headroom BEFORE calling this (cancelling is irreversible;
        this function does not re-check availability against any qty except
        what the broker's own release signal reports).
    Neither direction is special-cased below — cancel/confirm/release/place
    do not know or care which way the qty moved.

    Returns (new_stop_order, outcome); outcome["kind"] ∈:
      "ok"          — resized stop accepted; timings_ms attached.
      "protected"   — the cancel REQUEST failed and the old leg verified still
                      live: the position never stopped being protected.
      "stop_filled" — the old stop FILLED (full qty) during the cancel: the
                      position is exiting via the stop; nothing to protect,
                      nothing to resize — CALLER MUST NOT place a new stop off
                      a pre-fill qty snapshot (it is now stale).
      "naked"       — the old stop is (or may be) gone and no resized stop
                      could be placed: broker_qty snapshots taken before this
                      call may now be stale (a partial fill can precede this
                      outcome) — callers must re-protect off FRESH broker
                      truth, never off the qty they came in with.
    Never raises — every failure is an outcome. Broker-only: no DB writes here
    (the caller owns persistence + audit under the advisory lock).
    """
    t0 = time.monotonic()
    timings: dict = {}

    def _ms() -> float:
        return round((time.monotonic() - t0) * 1000, 1)

    # 1) Request the cancel. cancel_order returns False on ANY API error
    #    (including "already canceled/filled") — classification happens below
    #    against the order's actual status, not the request's return value.
    cancel_ok = await alpaca.cancel_order(old_stop_id, account_mode=account_mode)
    timings["cancel_req_ms"] = _ms()

    # 2) Confirm the leg reached a terminal state. `filled` → the stop beat us.
    cancel_confirmed = False
    last_status: str | None = None
    filled_qty = 0.0
    deadline = t0 + _LEG_SAFE_CANCEL_CONFIRM_BUDGET_S
    while True:
        chk = await alpaca.get_order(old_stop_id, account_mode=account_mode)
        last_status = _canonical_order_status(chk.get("status") if chk else None)
        if chk:
            try:
                filled_qty = float(chk.get("filled_qty") or 0)
            except (TypeError, ValueError):
                filled_qty = 0.0
        if last_status == "filled":
            return None, {
                "kind": "stop_filled", "timings": timings,
                "cancel_confirmed": False,
                "detail": (f"stop {old_stop_id} FILLED during cancel — "
                           f"position is exiting via the stop"),
            }
        if last_status in _CANCEL_LIKE_ORDER_STATUSES or last_status == "replaced":
            cancel_confirmed = True
            timings["cancel_confirm_ms"] = _ms()
            break
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(_LEG_SAFE_POLL_S)

    if not cancel_confirmed:
        if not cancel_ok and last_status in _STOP_CONFIRMED_LIVE_STATUSES:
            # Cancel request failed AND the leg is verifiably still resting —
            # the position never stopped being protected. Clean abort.
            return None, {
                "kind": "protected", "timings": timings,
                "cancel_confirmed": False,
                "detail": (f"cancel failed; old stop {old_stop_id} still live "
                           f"(status={last_status}) — position protected"),
            }
        # Cancel accepted but not yet terminal (pending_cancel limbo), or the
        # order state is unreadable. The stop MAY die at any moment with no
        # replacement coming — that is a naked hazard, not a safe walk-away.
        # Route to the re-protect machinery, which resolves against broker
        # truth (still-live stop → coverage met; dead → full stop placed).
        return None, {
            "kind": "naked", "timings": timings,
            "cancel_confirmed": False,
            "detail": (f"cancel not confirmed within "
                       f"{_LEG_SAFE_CANCEL_CONFIRM_BUDGET_S:g}s "
                       f"(last status={last_status})"),
        }

    if filled_qty > 0:
        # A partial stop-fill raced in before the cancel — DB new_remaining is
        # stale vs the broker. Do NOT place a possibly-wrong-size stop; route
        # to the re-protect machinery, which sizes off live broker qty.
        return None, {
            "kind": "naked", "timings": timings,
            "cancel_confirmed": True,
            "detail": (f"old stop partially filled ({filled_qty:g} sh) before "
                       f"cancel — re-protect to broker truth"),
        }

    # 3) Release gate — THE fix for the IBM 2026-05-27 race. The reservation
    #    (held_for_orders) clears ~60ms AFTER the cancel confirms (probe T6);
    #    submitting before it clears is exactly what produced the May
    #    "insufficient qty available" naked. Wait for the broker's own release
    #    signal. On timeout we still attempt placement — the submit itself is
    #    ground truth, and its retry loop absorbs stragglers.
    release_deadline = time.monotonic() + _LEG_SAFE_RELEASE_BUDGET_S
    while time.monotonic() < release_deadline:
        pos = await alpaca.get_position(ticker, account_mode=account_mode)
        avail = pos.get("qty_available") if pos else None
        if avail is not None and float(avail) >= new_qty:
            timings["avail_release_ms"] = _ms()
            break
        await asyncio.sleep(_LEG_SAFE_POLL_S)

    # 4) Place the resized stop. Probe T4: a stop can NEVER be accepted while
    #    another stop still holds the shares (40310000), so an accept here is
    #    broker-side proof there is no surviving duplicate.
    last_err: Exception | None = None
    for attempt in range(1, _LEG_SAFE_STOP_ATTEMPTS + 1):
        try:
            coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
            new_stop = await alpaca.place_stop_order(
                ticker, new_qty, float(stop_price),
                account_mode=account_mode, client_order_id=coid,
            )
            timings["stop_accept_ms"] = _ms()
            timings["stop_attempts"] = attempt
            return new_stop, {"kind": "ok", "timings": timings,
                              "cancel_confirmed": True, "detail": None}
        except Exception as e:
            last_err = e
            if _is_share_reservation_lag(e) and attempt < _LEG_SAFE_STOP_ATTEMPTS:
                logger.warning(
                    f"leg-safe resize {ticker}: resized-stop attempt {attempt}"
                    f"/{_LEG_SAFE_STOP_ATTEMPTS} hit reservation lag: {e} — retrying"
                )
                await asyncio.sleep(0.3)
                continue
            break
    return None, {
        "kind": "naked", "timings": timings, "cancel_confirmed": True,
        "detail": (f"resized stop placement failed after cancel "
                   f"({type(last_err).__name__ if last_err else 'unknown'}: "
                   f"{last_err})"),
    }


async def _reduce_stop_via_cancel_new(
    trade_id: int,
    ticker: str,
    old_stop_id: str,
    new_remaining: int,
    stop_price: float,
    signal_type: str,
    account_mode: str,
) -> tuple[dict | None, dict]:
    """#508 — thin direction-named wrapper over `_replace_stop_leg_via_cancel_new`
    for the partial-exit REDUCE case (new_remaining < the leg's current qty).
    Kept as its own name/signature — `execute_partial_exit` (and its tests)
    call it by this name — but it now delegates 100% of the mechanism to the
    shared helper; no logic lives here. See `_widen_stop_via_cancel_new` for
    the #523 opposite-direction sibling."""
    return await _replace_stop_leg_via_cancel_new(
        trade_id, ticker, old_stop_id, new_remaining, stop_price,
        signal_type, account_mode,
    )


async def _widen_stop_via_cancel_new(
    trade_id: int,
    ticker: str,
    old_stop_id: str,
    target_qty: int,
    stop_price: float,
    signal_type: str,
    account_mode: str,
) -> tuple[dict | None, dict]:
    """#523 — thin direction-named wrapper over `_replace_stop_leg_via_cancel_new`
    for the coverage-repair WIDEN case (target_qty > the leg's current qty).

    `stop_price` MUST be the leg's own already-accepted broker price (never a
    newly-computed one) — this can only ever change quantity, never the stop
    level (THE LINE). The caller owns verifying, BEFORE calling this, that the
    broker will actually have `target_qty` shares available once the leg is
    cancelled (see `_ensure_stop_coverage`'s pre-flight gate) — unlike the
    reduce direction, a widen's new qty is not bounded above by what the
    cancel itself frees, so that check cannot be deferred to this helper."""
    return await _replace_stop_leg_via_cancel_new(
        trade_id, ticker, old_stop_id, target_qty, stop_price,
        signal_type, account_mode,
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

    #621: deliberately NOT given the reprotect-floor timeout. The blocking wait
    for this lock is a safeguard behaviour by design (a partial-exit waits its
    turn rather than racing the reconciler) — bounding it would change WHEN a
    partial exit gives up, which is THE LINE, not a hang fix. It also is not on
    the stop-placement chain #621 addresses (`_ensure_stop_coverage` uses the
    non-blocking `_trade_advisory_try_lock` above, which IS bounded).
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

    #621: `pool.acquire()` and both `pg_try_advisory_lock`/`pg_advisory_unlock`
    calls are timeout-bounded (a saturated pool or a hung Postgres used to
    block here forever). `pg_try_advisory_lock` is already non-blocking at the
    Postgres level (it returns immediately either way) — the bound only
    protects against the DB itself being unresponsive. No new except clause:
    a raise (including TimeoutError) propagates exactly as any other DB error
    already does, to the caller's existing handling.
    """
    pool = await get_pool()
    conn = await pool.acquire(timeout=_REPROTECT_DB_TIMEOUT)
    acquired = False
    try:
        acquired = bool(await conn.fetchval(
            "SELECT pg_try_advisory_lock($1, $2)",
            _TRADE_LOCK_NAMESPACE, int(trade_id),
            timeout=_REPROTECT_DB_TIMEOUT,
        ))
        yield acquired
    finally:
        try:
            if acquired:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock($1, $2)",
                    _TRADE_LOCK_NAMESPACE, int(trade_id),
                    timeout=_REPROTECT_DB_TIMEOUT,
                )
        finally:
            await pool.release(conn)


async def _breaker_already_alerted(trade_id: int) -> bool:
    """Has the breaker-open Telegram already gone out for this trade?

    The audit row is the state — same idiom as the budget-alarm re-fire fix (7/17) and the
    new-lane detector. Fails OPEN (returns False, i.e. alert) on any error: a duplicate message is
    a nuisance, a missed one on a live money path is not."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM mi_audit_log WHERE event_type = 'partial_exit_circuit_open' "
                "AND detail::jsonb ->> 'trade_id' = $1::text", str(trade_id))
        return bool(n and int(n) > 1)   # >1: this cycle's row is already written above
    except Exception as e:  # loud-ok: logged; failing open only risks a duplicate alert, never a missed one
        logger.warning(f"breaker-alert dedupe check failed (will alert): {e}")
        return False


async def _profit_trigger_already_announced(trade_id: int) -> bool:
    """Has the 💰 profit-target-hit Telegram already gone out for this trade?

    ⚠ THE OTHER HALF OF THE 2026-08-04 BOMBARDMENT. The operator's words were "I've been
    bombarded with these msg non stop" and the volume was a PAIR of messages every 5 minutes:
    the breaker-open alert (deduped earlier today by `_breaker_already_alerted`) AND this
    announcement, which fired unconditionally at the top of every `scan_profit_triggers` pass.

    It re-fires because BOTH of its conditions are sticky. `partial_taken` only flips TRUE on a
    SUCCESSFUL partial, so a trade whose partial keeps failing is re-selected every cycle; and the
    trigger tests `MAX(high) >= target` over the whole in-hold window, which having once been true
    is true forever. So a position that can't be harvested announces its target hit every 5 minutes
    for as long as it stays open — which for PLTR 307 was hours, and would have resumed at 9:30
    tomorrow with nothing but this changed.

    Same idiom as the breaker dedupe: the audit row IS the state (no new table), the
    `profit_trigger_fired` / `profit_trigger_failed` rows still land EVERY cycle so the durable
    record stays complete, and only the Telegram is deduped. Fails OPEN (returns False, i.e.
    announce) — a duplicate message is a nuisance; a missed one on a live money path is not.

    Note the ordering difference from `_breaker_already_alerted`: that one runs AFTER its own audit
    row is written, so it tests > 1. This one runs BEFORE the cycle's row, so ANY prior row means
    already announced — hence > 0."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM mi_audit_log "
                "WHERE event_type IN ('profit_trigger_fired', 'profit_trigger_failed') "
                "AND detail::jsonb ->> 'trade_id' = $1::text", str(trade_id))
        return bool(n and int(n) > 0)
    except Exception as e:  # loud-ok: logged; failing open only risks a duplicate alert
        logger.warning(f"profit-trigger announce dedupe check failed (will announce): {e}")
        return False


async def execute_partial_exit(
    trade_id: int, shares: int, *, force: bool = False,
    limit_price: float | None = None,
    trigger: dict | None = None,
) -> bool:
    """
    Partial exit (1/3 sell). Replaces stop for remaining 2/3 first so the
    position is always protected. On sell failure, rolls the stop back to
    the full original qty.

    force=True bypasses the outcome-history circuit breaker (#151 c) — used by
    the operator-confirmed /partialnow command (an attended action). The
    scheduled cron path passes force=False so a string of recent failures pauses
    automatic retries instead of re-failing into the same fault daily.

    limit_price (#548 final design, 2026-08-10): when supplied AND the
    `profit_take_resting_limit` runtime toggle is ON for the trade's
    account_mode, the 1/3 is sold with a resting GTC LIMIT at this price
    (the +2R target) instead of a market order, and breakeven is applied to
    the reduced stop AFTERWARDS via an atomic price-only replace. Sequence and
    the reasoning for each step are at the resting-mode branches below. When
    the toggle is OFF (or limit_price is None — the day-3/5 ladder and
    /partialnow paths), behaviour is unchanged: market sell, breakeven folded
    into the stop re-creation.

    trigger (operator 2026-08-18, message-merge only — no order/sell-logic
    effect): optional {"delivered": bool, "high", "target", "entry",
    "r_multiple"} from scan_profit_triggers' own detection. When given, Step 3
    below folds these facts into ITS OWN Telegram (making that one message the
    whole story: trigger + sale + protection) and sets trigger["delivered"] =
    True right before sending — the caller uses that flag to decide whether
    IT still needs to speak. None (agent.py /partialnow, live_tracker.py) —
    every text branch below renders byte-identical to before this change.
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
    #
    # ⚠ The breaker runs BEFORE the trade row is loaded (deliberately — it short-circuits
    # without touching trade state), but #525 made it PER-MODE, and the mode lives on the
    # trade. So resolve just that one field here. Cheap, and it keeps the early-refusal
    # ordering intact rather than moving the breaker after the fetch.
    #
    # Falls back to the process's own mode if the row is missing — a trade we cannot read is
    # about to fail the fetch below anyway, and the breaker must not crash on the way there.
    try:
        _pool = await get_pool()
        async with _pool.acquire() as _c:
            _bm = await _c.fetchval(
                "SELECT account_mode FROM mi_live_trades WHERE id = $1", trade_id)
        breaker_mode = _bm or current_account_mode()
    except Exception as e:  # loud-ok: the breaker must still run, on the safest mode we know
        logger.warning(f"execute_partial_exit: account_mode lookup failed for trade "
                       f"{trade_id} ({e}) — breaker falls back to the process mode")
        breaker_mode = current_account_mode()
    fail_count = await _consecutive_partial_exit_failures(breaker_mode)
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
            # ⚠ ALERT ONCE PER TRADE, not once per cycle (2026-08-04). The breaker exists to stop
            # RETRIES into a fault; it was still letting the 5-minute job re-alert on every pass.
            # PLTR today: the same pair of messages every 5 minutes for hours, about a condition
            # already reported and already actioned — the operator's words were "I've been
            # bombarded with these msg non stop, this is a really really bad bug".
            #
            # A breaker that is OPEN is by definition a KNOWN state. Re-announcing it is not
            # information; it buries the ONE message that mattered. The audit row above still fires
            # every cycle — the durable record stays complete, only the Telegram is deduped.
            already_alerted = await _breaker_already_alerted(trade_id)
            if not already_alerted:
                await send_telegram_message(
                    f"🛑 *Partial-exit circuit breaker OPEN*\n"
                    f"{fail_count} partial-exit failures since the last clean exit — "
                    f"automatic partial exits are PAUSED to stop retries into the same "
                    f"fault.\n\n"
                    f"Trade {trade_id} was skipped. Investigate (`show errors 7d`), then "
                    f"`/partialnow TICKER CONFIRM` to act manually (bypasses the breaker "
                    f"+ a clean run closes it).\n\n"
                    f"_This alert fires ONCE per trade while the breaker stays open._"
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
    # #548 resting mode: breakeven-replace verification failed AFTER the limit was
    # placed — the partial STANDS (limit resting) but the reduced stop needs
    # re-protecting to broker truth. Distinct from abort_reprotect, whose post-lock
    # block reports "No shares sold" (false here) and returns False (also false —
    # the sell leg succeeded).
    be_reprotect = False
    be_ctx: dict = {}
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
        # Terminal-status set: PENDING_EXIT_TERMINAL_STATUSES — same SSoT
        # get_pending_exit_qty uses; do not hand-copy the tuple (#591 review).
        async with pool.acquire() as conn:
            pending = await conn.fetchrow("""
                SELECT alpaca_order_id, qty, purpose FROM mi_live_orders
                WHERE trade_id = $1
                  AND purpose IN ('partial_exit', 'full_exit')
                  AND status != ALL($2::text[])
                LIMIT 1
            """, trade_id, list(PENDING_EXIT_TERMINAL_STATUSES))
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

        # ── #548 RESTING-LIMIT MODE (final design, operator-approved shape) ──────
        # ON only when the caller supplied the +2R target AND the runtime toggle is
        # on for this account_mode. The sequence it selects:
        #   1. reduce the stop to 2/3 at its CURRENT price (cancel-then-new — the
        #      broker permits nothing else for a bracket leg);
        #   2. rest a GTC LIMIT for the freed 1/3 at the target;
        #   3. move the reduced stop to breakeven via atomic PRICE-ONLY replace.
        # Why breakeven is NOT folded into step 1 here (it is in market mode): the
        # only structurally-unprotected window in the whole sequence is
        # cancel-confirm → new-stop-accept (~72-90ms measured). Re-creating the
        # stop at the price it was JUST resting at cannot be price-rejected, so
        # that window closes with near-certainty; a breakeven price could sit
        # at/above market if price collapsed since the trigger bar (the trigger is
        # bar-based and up to 5 minutes stale) and a rejection there would EXTEND
        # the naked window. Step 3 is atomic: a rejected replace leaves the old
        # stop live and untouched (probe T1b/T2 + `_548_final_sequence_probe` P4),
        # so applying breakeven there carries zero naked risk.
        resting_mode = bool(limit_price) and await _profit_take_resting_limit_enabled(
            account_mode)

        # ── #566 OCO CARVE-OUT (operator-signed 2026-08-14) ──────────────────
        # In resting mode the freed 1/3's exit becomes ONE OCO: GTC limit at the
        # +2R target + sibling GTC stop at BREAKEVEN — whichever side fills
        # cancels the other. Closes the ETON hole (a bare resting limit above
        # the market left the third with NO stop for hours). The limit STAYS
        # RESTING (operator constraint — no cancel/re-place-on-price shapes).
        # The 1/3's stop sits at breakeven — max(current stop, entry) — never
        # below the stop the shares already had; if neither anchor exists the
        # OCO cannot be priced and we FALL BACK to the plain resting limit
        # (today's behaviour, no worse) with a loud audit row.
        oco_mode = False
        oco_stop_price = None
        if resting_mode and await _profit_take_oco_enabled(account_mode):
            _oco_anchors = [float(v) for v in (stop_price, trade.get("entry_price"))
                            if v is not None]
            if _oco_anchors:
                oco_mode = True
                oco_stop_price = max(_oco_anchors)
            else:
                await log_audit_event(
                    "partial_exit_oco_fallback",
                    f"{ticker}: OCO toggle on but no stop/entry anchor to price the "
                    f"sibling stop — falling back to plain resting limit",
                    json.dumps({"trade_id": trade_id, "ticker": ticker,
                                "limit_price": float(limit_price)}),
                )

        logger.info(
            f"Partial exit: {ticker} selling {shares} of {full_remaining} shares "
            f"(new_remaining={new_remaining}, trade_id={trade_id}, "
            f"mode={'resting_oco' if oco_mode else ('resting_limit' if resting_mode else 'market')})"
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

        # Step 1: reduce the stop to new_remaining BEFORE selling anything.
        # Two mechanisms, routed by what the stop IS (#508, 2026-08-04):
        #   * SIMPLE stop → atomic REPLACE, race-free vs cancel+new (IBM
        #     2026-05-27 false-naked: 43ms between cancel + new submit;
        #     Alpaca's share-reservation hadn't cleared so the new stop was
        #     rejected "insufficient qty available" — held_for_orders = 26).
        #   * OTO/BRACKET LEG → Alpaca REJECTS any qty replace (42210000, the
        #     PLTR 2026-08-04 failure) and every MAGNA53 entry's stop is a
        #     leg, so the profit-trigger could never harvest. Leg-safe path:
        #     verified cancel → reservation-release gate → new reduced stop
        #     (_reduce_stop_via_cancel_new; empirical basis in its block
        #     comment). Gated by runtime toggle `partial_exit_leg_safe`
        #     (mi_safeguard_state / PARTIAL_EXIT_LEG_SAFE, default OFF): when
        #     OFF, legs keep failing exactly as PLTR did — replace rejected,
        #     original stop intact, clean abort (fail-safe, but no harvest).
        new_stop_id = None
        # ── REAL-TIME BREAKEVEN (#548, 2026-08-08) ────────────────────────────────────────
        # The Telegram says "stop moves to breakeven" and, until now, nothing did: it set
        # `breakeven_active = TRUE` in the DB, and ONLY `exit_logic`'s DAILY pass consumed that
        # flag. FIGS 08-07 stopped out at 09:51 the same morning — about six hours before any
        # daily pass could act — so the remaining 41 shares still sat behind the ORIGINAL stop
        # and lost $13.74 on a trade that had already banked a profit.
        #
        # ⚠ THE CHEAP PART, and why this needs no new broker machinery: the stop is ALREADY
        # being re-created here to reduce its quantity (a bracket leg's qty cannot be replaced —
        # 42210000 — so it is cancel-then-new either way). Breakeven is therefore a PRICE
        # ARGUMENT to an operation that already happens: zero extra orders, zero extra legs,
        # zero new failure modes. That is what makes it shippable under the operator's
        # broker-simplicity constraint while the 2R-limit half is still being designed.
        #
        # max() — it can only ever RAISE the stop. If the original stop is already above entry
        # (a trailed or gapped-up position) it stays put; breakeven never loosens protection.
        #
        # ⚠ In RESTING-LIMIT mode (#548 final design) this fold-in is SKIPPED: breakeven is
        # applied AFTER the limit rests, by an atomic price-only replace — see the
        # resting-mode block comment above for why the re-created stop keeps its current
        # price through the one genuinely-unprotected window.
        _entry = trade.get("entry_price")
        if (not resting_mode and stop_price and _entry
                and await _breakeven_at_broker_enabled(account_mode)):
            _be = max(float(stop_price), float(_entry))
            if _be > float(stop_price):
                await log_audit_event(
                    "partial_exit_breakeven_armed",
                    f"{ticker}: stop moves to breakeven ${_be:.2f} (was ${float(stop_price):.2f}, "
                    f"entry ${float(_entry):.2f}) on the reduced {new_remaining}-share stop",
                )
                stop_price = _be

        if old_stop_id and stop_price and new_remaining > 0:
            leg_safe_on = await get_runtime_toggle(
                "partial_exit_leg_safe", "PARTIAL_EXIT_LEG_SAFE", default=False)
            stop_is_leg = False
            if leg_safe_on:
                try:
                    _cur_stop = await alpaca.get_order(
                        old_stop_id, account_mode=account_mode)
                    stop_is_leg = (
                        str((_cur_stop or {}).get("order_class") or "").lower()
                        in _ADVANCED_ORDER_CLASSES
                    )
                except Exception as _clserr:
                    # Unreadable → try the replace first; the 42210000 net in
                    # the retry loop still routes a real leg to leg-safe.
                    logger.warning(
                        f"execute_partial_exit: could not read order_class for "
                        f"{old_stop_id} ({_clserr}) — trying replace first")
                    stop_is_leg = False
            # Same-window retry (#136 follow-through). replace_order is atomic
            # so the original cancel-new race shouldn't recur, but other
            # transient broker failures (5xx, network blip) still warrant
            # a single same-tick retry before aborting. Skipping methodology
            # window costs an extra trading day at next-open price — too
            # expensive vs a 1s wait + retry.
            new_stop_order = None
            last_err: Exception | None = None
            reduce_outcome: dict | None = None
            if not stop_is_leg:
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
                        if _is_stop_already_at_target(e):
                            # The stop ALREADY holds the qty+price we asked for — a prior
                            # attempt reduced it and then aborted before selling (PLTR 307,
                            # 2026-08-05). Adopt the live stop and continue to the sell rather
                            # than re-failing a step that is already done; without this the
                            # partial deadlocks forever and each retry feeds the breaker.
                            try:
                                _oo = await alpaca.get_open_orders(account_mode=account_mode)
                                _cur = _live_sell_stops(
                                    [o for o in _oo if o.get("symbol") == ticker])
                            except Exception as _rerr:  # loud-ok: logged; falls to normal abort
                                logger.warning(
                                    f"execute_partial_exit: {ticker} stop reported already at "
                                    f"target but open orders unreadable ({_rerr}) — aborting")
                                break
                            if len(_cur) == 1 and abs(
                                    float(_cur[0].get("qty") or 0) - new_remaining) <= 0.5:
                                logger.info(
                                    f"execute_partial_exit: {ticker} stop already at target "
                                    f"({new_remaining} sh) — adopting {_cur[0]['id'][:8]} and "
                                    f"proceeding to sell")
                                new_stop_order = _cur[0]
                                last_err = None
                                break
                            logger.error(
                                f"execute_partial_exit: {ticker} broker says parameters "
                                f"unchanged but live stops do not match target "
                                f"{new_remaining}: {[(o.get('id','')[:8], o.get('qty')) for o in _cur]}"
                                f" — aborting rather than guessing")
                            break
                        if leg_safe_on and _is_advanced_qty_rejection(e):
                            # The broker says the stop IS an advanced-order
                            # leg — deterministic, retrying is pointless.
                            logger.warning(
                                f"execute_partial_exit: {ticker} stop "
                                f"{old_stop_id} is an advanced-order leg "
                                f"(42210000) — routing to leg-safe cancel+new")
                            stop_is_leg = True
                            break
                        logger.warning(
                            f"execute_partial_exit: replace attempt {attempt} failed "
                            f"for {ticker}: {e}"
                        )
                        if attempt < 2:
                            await asyncio.sleep(1.5)
            if leg_safe_on and stop_is_leg and new_stop_order is None:
                new_stop_order, reduce_outcome = await _reduce_stop_via_cancel_new(
                    trade_id, ticker, old_stop_id, new_remaining,
                    float(stop_price), signal_type, account_mode,
                )
                _kind = reduce_outcome["kind"]
                if _kind == "stop_filled":
                    # The stop FILLED while we tried to cancel it — the
                    # position is exiting AT the stop; nothing left to partial,
                    # nothing left to protect. The stop-fill WS flow owns
                    # finalization.
                    await log_audit_event(
                        "partial_exit_aborted",
                        f"{ticker}: old stop filled during leg-safe cancel — "
                        f"position exiting via stop, no partial taken",
                        json.dumps({
                            "trade_id": trade_id, "ticker": ticker,
                            "old_stop_id": old_stop_id,
                            "stage": "leg_safe_cancel_new",
                            "detail": reduce_outcome["detail"],
                            "timings_ms": reduce_outcome["timings"],
                        }),
                    )
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}⚠️ Partial exit for {ticker} "
                        f"aborted: the stop FILLED first — position is exiting "
                        f"via the stop. No partial taken."
                    )
                    return False
                if _kind != "ok":
                    # "protected" / "naked" — hand to the EXISTING abort
                    # machinery below (the persist-try raises): it probes the
                    # old stop on the broker and routes live → clean protected
                    # abort, dead → null pointer + post-lock
                    # _ensure_stop_coverage re-protect to broker truth.
                    last_err = RuntimeError(
                        f"#508 leg-safe reduce: {reduce_outcome['detail']}")
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
                        float(stop_price), new_stop_order["status"],
                        _jsonb_param(new_stop_order))  # #216: codec single-encodes; do NOT pre-dumps
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
                        # #508: which mechanism reduced the stop + measured
                        # leg-safe timings (cancel/release/accept ms) — the
                        # verify-live evidence for the naked-window size.
                        "mechanism": ("leg_safe_cancel_new" if reduce_outcome
                                      else "replace"),
                        **({"timings_ms": reduce_outcome["timings"]}
                           if reduce_outcome else {}),
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
            for _ in range(_AVAIL_POLL_ATTEMPTS):
                _pos = await alpaca.get_position(ticker, account_mode=account_mode)
                last_avail = _pos.get("qty_available") if _pos else None
                if last_avail is not None and last_avail >= shares:
                    avail_ok = True
                    break
                await asyncio.sleep(_AVAIL_POLL_INTERVAL_S)
            # `new_stop_id` is set only after the reduced stop was placed AND verified
            # live, so it is the confirmation this fall-through depends on. Without it
            # (no prior stop to reduce) we keep the strict abort — selling without a
            # confirmed stop behind it is the one case worth vetoing.
            if not avail_ok and new_stop_id:
                # ⚠ THE GATE IS AN OPTIMISATION, NOT A VETO (2026-08-05, PLTR 307).
                # The old 3s budget ABORTED here — and in doing so short-circuited the
                # sell's OWN retry loop below, which exists for exactly this rejection.
                # A stricter pre-check standing in front of looser recovery turned a
                # transient open-of-session lag into a 15-minute, three-scan recovery.
                #
                # Attempting the sell anyway is SAFE and is the broker's own contract:
                # `_is_share_reservation_lag` matches only a CLEAN rejection — no order is
                # placed — so a retry cannot oversell. The reduction is confirmed live, so
                # falling through cannot sell against a failed stop either.
                logger.warning(
                    f"execute_partial_exit: {ticker} qty_available={last_avail} < {shares} "
                    f"after {_AVAIL_POLL_ATTEMPTS * _AVAIL_POLL_INTERVAL_S:g}s, but the stop "
                    f"reduction is CONFIRMED — attempting the sell anyway; a clean "
                    f"reservation rejection is retryable and cannot oversell"
                )
                avail_ok = True
            if not avail_ok:
                # ⚠ 2026-08-05, PLTR 307 — this branch ASSUMED the wrong world and told the
                # operator the position was protected while 2 of 6 shares had no stop behind
                # them. Its premise was "shares are still held ⇒ the OLD full-size stop is
                # still resting ⇒ over-covered ⇒ safe to walk away". That is ONE of two worlds
                # with the identical symptom. On PLTR the NEW reduced stop was already
                # confirmed live (`partial_exit_stop_replaced`, 4 sh of a 6-sh position) and
                # the hold was something else — so the same `qty_available` reading meant
                # UNDER-covered, the exact opposite, and the abort left a real gap that
                # nothing repairs until the 16:05 sync.
                #
                # So: ASK THE BROKER instead of inferring. Coverage is a fact on the broker,
                # never a deduction from a share count.
                covered = None
                _pos_qty = None
                try:
                    _oo = await alpaca.get_open_orders(account_mode=account_mode)
                    covered = sum(
                        float(o.get("qty") or 0)
                        for o in _live_sell_stops(
                            [o for o in _oo if o.get("symbol") == ticker])
                    )
                    _p = await alpaca.get_position(ticker, account_mode=account_mode)
                    _pos_qty = float(_p.get("qty")) if _p and _p.get("qty") is not None else None
                except Exception as _cerr:  # loud-ok: logged; unreadable ⇒ assume under-covered
                    logger.warning(
                        f"execute_partial_exit: could not read broker coverage for {ticker} "
                        f"after the availability budget ({_cerr}) — assuming UNDER-covered")

                # Unreadable broker ⇒ NOT provably covered ⇒ re-protect. Never the reverse:
                # this branch's whole failure was assuming safety it had not established.
                fully_covered = (
                    covered is not None and _pos_qty is not None
                    and covered >= _pos_qty - 0.5
                )
                logger.error(
                    f"execute_partial_exit: {ticker} qty_available={last_avail} < {shares} "
                    f"after budget; broker stop coverage={covered} vs position={_pos_qty} — "
                    f"{'over-covered, safe to abort' if fully_covered else 'UNDER-COVERED, re-protecting'}"
                )
                await log_audit_event(
                    "partial_exit_aborted",
                    f"{ticker}: shares not free (qty_available={last_avail} < {shares}) — sell "
                    f"skipped; stop coverage {covered} vs position {_pos_qty} "
                    f"({'over-covered, safe' if fully_covered else 'UNDER-COVERED → re-protect'})",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker, "shares": shares,
                        "qty_available": last_avail, "new_remaining": new_remaining,
                        "new_stop_id": new_stop_id, "old_stop_id": old_stop_id,
                        "stage": "verify_shares_free",
                        "stop_coverage": None if covered is _BROKER_UNREADABLE else covered,
                        "position_qty": _pos_qty,
                        "fully_covered": fully_covered,
                    }),
                )
                if fully_covered:
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}⚠️ Partial exit SKIPPED for {ticker}: "
                        f"shares not free to sell (available {last_avail} < {shares}).\n"
                        f"_Stop still covers the full {_pos_qty:.0f} sh — position protected, "
                        f"no shares sold. Cron will retry next window._"
                    )
                    return False
                # UNDER-covered: the stop was already reduced but the sell never happened, so
                # the position is short of cover. Do NOT claim protection. Hand to the same
                # post-lock machinery every other abort path uses — it re-protects to BROKER
                # truth once the advisory lock releases, which is the only correct sizing
                # source here (DB `remaining_shares` is still the pre-partial number).
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}⚠️ Partial exit SKIPPED for {ticker}: "
                    f"shares not free to sell (available {last_avail} < {shares}).\n"
                    f"_No shares sold, but the stop had already been reduced to "
                    f"{covered if covered is not None else '?'} sh on a "
                    f"{_pos_qty if _pos_qty is not None else '?'} sh position — "
                    f"RE-PROTECTING to full size now._"
                )
                # ⚠ SET THE FLAG AND FALL THROUGH — do NOT return here. `abort_reprotect` is
                # consumed AFTER the advisory lock releases (the post-lock block below);
                # returning inside the lock would skip the re-protect entirely and make this
                # whole fix inert, which is exactly the shape of the bug it repairs.
                abort_reprotect = True

            # Step 2: Sell the partial (shares are now free from the stop).
            # Market mode: market sell, fills in seconds. Resting mode (#548): a
            # GTC LIMIT at the +2R target — fills AT the price instead of at
            # whatever the tape shows when the poll notices (FIGS 2026-08-07:
            # market fill +1.13R against a +2R target, two seconds after the high).
            try:
                coid_sell = alpaca.make_client_order_id(account_mode, signal_type, ticker)
                # #150: the atomic replace frees the shares, but Alpaca's share-hold
                # (held_for_orders) can lag the replace ack by ~ms, so an immediate
                # sell transiently rejects with "insufficient qty available" (confirmed
                # 2026-05-29; measured 12.8ms first-try clean after a VERIFIED-clear
                # cancel on 2026-08-10 — the retry loop stays as belt-and-braces).
                # Retry that SPECIFIC clean rejection a few times with
                # backoff before the outer except rolls the partial back. Fresh COID
                # per attempt avoids dup-COID rejection. Non-lag errors re-raise
                # immediately (no retry) so genuine failures still roll back fast.
                order = None
                for _attempt in range(3):
                    try:
                        if oco_mode:
                            # #566: ONE OCO — limit at the target + sibling stop at
                            # breakeven. The sibling rides as a HELD leg; the third
                            # is never limit-only (probe 2026-08-14: every share
                            # reserved, 40310000 on any further sell).
                            order = await alpaca.place_oco_sell(
                                ticker, shares, float(limit_price),
                                float(oco_stop_price),
                                account_mode=account_mode, client_order_id=coid_sell,
                            )
                        elif resting_mode:
                            order = await alpaca.place_limit_sell(
                                ticker, shares, float(limit_price),
                                account_mode=account_mode, client_order_id=coid_sell,
                            )
                        else:
                            order = await alpaca.place_market_sell(
                                ticker, shares,
                                account_mode=account_mode, client_order_id=coid_sell,
                            )
                        break
                    except Exception as _se:
                        if _is_share_reservation_lag(_se) and _attempt < _SELL_RETRY_ATTEMPTS:
                            logger.warning(
                                f"execute_partial_exit: {ticker} sell hit share-reservation "
                                f"lag (attempt {_attempt + 1}/3): {_se} — retry in 0.5s"
                            )
                            await asyncio.sleep(_SELL_RETRY_BACKOFF_S)
                            coid_sell = alpaca.make_client_order_id(
                                account_mode, signal_type, ticker,
                            )
                            continue
                        raise
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO mi_live_orders
                            (trade_id, alpaca_order_id, ticker, side, order_type, qty, status,
                             limit_price, purpose, exit_reason, raw_response)
                        VALUES ($1, $2, $3, 'sell', $7, $4, $5, $8,
                                'partial_exit', 'partial_profit', $6::jsonb)
                        ON CONFLICT (alpaca_order_id) DO NOTHING
                    """, trade_id, order["id"], ticker, float(shares),
                        order.get("status", "new"),
                        _jsonb_param(order),  # #216: codec single-encodes; do NOT pre-dumps
                        "limit" if resting_mode else "market",
                        float(limit_price) if resting_mode else None)
                # #566: record the OCO's sibling STOP leg under purpose='stop_loss'
                # so its fill routes to finalize_stop_fill (the WS router keys on
                # mi_live_orders — the leg is NOT stop_order_id, which stays the
                # 2/3's stop) and _verify_event_account_mode can place its events.
                # The leg is HIDDEN from get_open_orders while held (probe
                # 2026-08-14) — this row is the mirror's only record of it.
                if oco_mode:
                    _oco_leg_id = alpaca.extract_stop_leg_id(order)
                    _oco_leg = next(
                        (l for l in (order.get("legs") or [])
                         if str(l.get("id")) == str(_oco_leg_id)), None)
                    if _oco_leg_id:
                        async with pool.acquire() as conn:
                            await conn.execute("""
                                INSERT INTO mi_live_orders
                                    (trade_id, alpaca_order_id, ticker, side, order_type,
                                     qty, stop_price, status, raw_response, purpose,
                                     exit_reason)
                                VALUES ($1, $2, $3, 'sell', 'stop', $4, $5, $6, $7::jsonb,
                                        'stop_loss', 'stop_hit')
                                ON CONFLICT (alpaca_order_id) DO NOTHING
                            """, trade_id, _oco_leg_id, ticker, float(shares),
                                float(oco_stop_price),
                                (_oco_leg or {}).get("status", "held"),
                                _jsonb_param(_oco_leg or {}))  # #216: codec single-encodes; do NOT pre-dumps
                if oco_mode:
                    _sell_desc = (f"OCO resting for {shares}: limit "
                                  f"@ ${float(limit_price):.2f} / stop "
                                  f"@ ${float(oco_stop_price):.2f}")
                elif resting_mode:
                    _sell_desc = f"limit sell {shares} @ ${float(limit_price):.2f} resting"
                else:
                    _sell_desc = f"market sell {shares} placed"
                await log_audit_event(
                    "partial_exit_sell_placed",
                    f"{ticker}: {_sell_desc} ({order.get('id')}, status={order.get('status', 'new')})",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker,
                        "shares": shares, "order_id": order.get("id"),
                        "order_status": order.get("status"),
                        "order_type": "limit" if resting_mode else "market",
                        "order_class": "oco" if oco_mode else "simple",
                        "limit_price": float(limit_price) if resting_mode else None,
                        "oco_stop_price": (float(oco_stop_price) if oco_mode else None),
                        "oco_stop_leg_id": (_oco_leg_id if oco_mode else None),
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
                        "account_mode": account_mode,   # #525 — breaker attribution
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

        # ── Step 2b (#548 resting mode ONLY): move the reduced stop to BREAKEVEN
        # via an atomic PRICE-ONLY replace, now that the limit rests.
        #
        # Ordering is deliberate, twice over:
        #   * AFTER the limit: a replace transiently pairs old+new orders
        #     (pending_replace), and the FPS 2026-06-04 incident showed the old
        #     order can keep reserving its shares while the pair settles — doing
        #     this first could block the 1/3 limit's acceptance. Once the limit
        #     rests, its reservation is established and a price-only replace on
        #     the OTHER 2/3 cannot collide with it (verified on paper 2026-08-10:
        #     replace accepted, successor live, qty preserved, limit untouched —
        #     `_548_final_sequence_probe.py` P3).
        #   * PRICE-ONLY: quantity never changes, so this can never race the
        #     share-reservation system at all, and a REJECTED replace is atomic —
        #     the reduced stop stays live at its original price (probe T1b + P4).
        #     Protection is therefore never worse than it was before this step.
        #
        # max() — breakeven can only ever RAISE the stop (same guard as the
        # market-mode fold-in above). Gated on the same `breakeven_at_broker`
        # toggle so the operator's one switch governs breakeven in both modes.
        #
        # (be_stop_id, breakeven_price) once the broker POSITIVELY confirms the
        # remaining shares' breakeven stop is live — None on every other path
        # (not attempted, rejected, or unconfirmed). Step 3 below only claims
        # "your remaining shares' stop is now at breakeven" when this is set;
        # a rejected/uncertain outcome already sends its OWN dedicated message
        # above and Step 3 must not also assert a fact that isn't true yet.
        _be_confirmed_live: tuple | None = None
        if (resting_mode and not abort_reprotect and new_stop_id and stop_price
                and _entry and await _breakeven_at_broker_enabled(account_mode)):
            _be = max(float(stop_price), float(_entry))
            if _be > float(stop_price) + 1e-9:
                be_stop_id = None
                try:
                    coid_be = alpaca.make_client_order_id(account_mode, signal_type, ticker)
                    be_order = await alpaca.replace_order(
                        new_stop_id, stop_price=_be,
                        account_mode=account_mode, client_order_id=coid_be,
                    )
                    be_stop_id = be_order["id"]
                except Exception as _bee:
                    # Rejected replace = atomic no-op broker-side — but VERIFY that,
                    # never assume it (the one lesson every incident here repeats).
                    #
                    # The verify read has THREE outcomes, not two, and ADR 0008 rule 1
                    # ("write-side — never infer") forces them apart:
                    #   live    — confirmed broker read, stop resting → defer, done.
                    #   dead    — confirmed broker read, terminal status → the
                    #             demotion below is broker-evidenced.
                    #   unknown — the read RAISED, returned None (alpaca.get_order
                    #             swallows errors and returns None, so a None read IS
                    #             a failed read, not a status), or never left a
                    #             transitional pending_* inside the budget. NOTHING
                    #             was confirmed; demoting here would be inference
                    #             from a failed op — the exact 2026-06-04 FPS
                    #             false-naked shape ADR 0008 outlaws.
                    # Bounded retry first: a transient read failure / settling
                    # pending_replace usually resolves within the Step-1b-sized
                    # budget, turning "unknown" into a confirmed live/dead.
                    _red_outcome = "unknown"
                    _red_status = None
                    for _ in range(12):  # ~3s at 0.25s/retry — mirrors Step 1b
                        try:
                            _chk = await alpaca.get_order(
                                new_stop_id, account_mode=account_mode)
                        except Exception as _verr:
                            _chk = None
                            logger.warning(
                                f"execute_partial_exit: {ticker} breakeven replace "
                                f"failed AND reduced-stop read raised ({_verr}) — "
                                f"retrying read")
                        _red_status = _canonical_order_status(
                            _chk.get("status") if _chk else None)
                        if _red_status in _STOP_CONFIRMED_LIVE_STATUSES:
                            _red_outcome = "live"
                            break
                        if _red_status in _STOP_DEAD_STATUSES or _red_status == "filled":
                            _red_outcome = "dead"
                            break
                        await asyncio.sleep(0.25)
                    if _red_outcome == "live":
                        # Stop still resting at its original price: protection is
                        # exactly what it was pre-partial. Converges — the limit's
                        # fill sets breakeven_active, and the EOD pass raises the
                        # stop to entry via update_stop.
                        await log_audit_event(
                            "partial_exit_breakeven_deferred",
                            f"{ticker}: breakeven replace rejected "
                            f"({type(_bee).__name__}); reduced stop {new_stop_id} still "
                            f"live @${float(stop_price):.2f} — protection unchanged, "
                            f"EOD pass will raise it after the limit fills",
                            json.dumps({
                                "trade_id": trade_id, "ticker": ticker,
                                "stop_id": new_stop_id,
                                "stop_price": float(stop_price),
                                "breakeven_target": _be,
                                "error": str(_bee)[:500],
                            }),
                        )
                        await send_telegram_message(
                            f"{mode_prefix(account_mode)}⚠️ {ticker}: breakeven move "
                            f"rejected ({type(_bee).__name__}) — stop stays at "
                            f"${float(stop_price):.2f} for {new_remaining} sh (still "
                            f"protected). Limit for {shares} sh rests at "
                            f"${float(limit_price):.2f}."
                        )
                    elif _red_outcome == "dead":
                        # The reduced stop read back a TERMINAL status — the 2/3 is
                        # unprotected. Null the stale pointer (it points at a dead
                        # order) and re-protect to broker truth post-lock (nets the
                        # resting limit, so target = 2/3).
                        # broker-confirmed: reached ONLY when alpaca.get_order(
                        # new_stop_id) returned an actual status in
                        # _STOP_DEAD_STATUSES/'filled'. A raised or None read
                        # canonicalizes to None, matches neither status set, and
                        # lands in the "unknown" branch below — which never demotes.
                        await set_stop_order_id(
                            trade_id, None,
                            reason="breakeven_replace_failed",
                            account_mode=account_mode,
                        )
                        be_reprotect = True
                        be_ctx = {"error": str(_bee),
                                  "reason": f"breakeven replace failed and reduced "
                                            f"stop confirmed dead "
                                            f"(status={_red_status})"}
                    else:
                        # UNKNOWN: replace raised AND the reduced stop could not be
                        # confirmed either way (read failed/None, or still pending_*
                        # after the retry budget). The trade-off, stated plainly:
                        #   * DEMOTING here (the pre-2026-08-10 behavior) asserts
                        #     "naked" on zero broker evidence. That is the 2026-06-04
                        #     FPS incident verbatim — the broker actually HAD stops,
                        #     the DB lied "naked", and machinery acting on the lie
                        #     made it worse. ADR 0008 rule 1: only a confirmed broker
                        #     read/event may demote trade state.
                        #   * KEEPING the pointer risks it being stale — the stop may
                        #     really be dead while the DB claims protection it cannot
                        #     prove. That risk is bounded because protection never
                        #     depended on this DB write: be_reprotect still arms, and
                        #     the post-lock _ensure_stop_coverage discovers live
                        #     stops from BROKER TRUTH (get_open_orders
                        #     raise_on_error=True), not from this pointer — stop
                        #     really dead → it re-places in-process; stop alive →
                        #     no-op; broker unreadable → it defers LOUDLY and the
                        #     15-min reconcile + coverage-drift detector +
                        #     broker-gated naked alarm own the divergence (ADR 0008
                        #     rule 2: the reconciler owns divergence, guarded so it
                        #     never acts on a degraded read).
                        # Nulling adds NO protection either way — placing a stop
                        # needs the same broker the read could not reach; the null
                        # only changes what the DB *claims*, and an unconfirmed
                        # claim is rule 1's exact ban. So: the ADR's side — do NOT
                        # demote. (Same keep-on-unconfirmed call Step 1b's verify
                        # already makes: "keep the best-guess stop … rather than
                        # null it and trigger a false-naked".) No operator fork
                        # hides here: with the broker unreadable no policy can ADD
                        # protection, so the only choice is what the DB asserts —
                        # and the ADR (operator-directed 2026-06-04) already ruled
                        # that.
                        await log_audit_event(
                            "partial_exit_breakeven_unverifiable",
                            f"{ticker}: breakeven replace failed AND reduced stop "
                            f"{new_stop_id} unverifiable "
                            f"(last_status={_red_status}) — pointer KEPT (ADR 0008: "
                            f"no demotion without a confirmed broker read); "
                            f"re-protect + reconciler own it",
                            json.dumps({
                                "trade_id": trade_id, "ticker": ticker,
                                "stop_id": new_stop_id,
                                "last_status": _red_status,
                                "stop_price": float(stop_price),
                                "breakeven_target": _be,
                                "error": str(_bee)[:500],
                            }),
                        )
                        be_reprotect = True
                        be_ctx = {"error": str(_bee),
                                  "reason": "breakeven replace failed and reduced "
                                            "stop UNREADABLE/unsettled — pointer "
                                            "kept (ADR 0008), coverage re-checked "
                                            "from broker truth"}
                if be_stop_id:
                    # VERIFY the successor is actually live before persisting price
                    # — a replace can return an id the broker then rejects (the
                    # "looked successful, actually dead" class Step 1b guards).
                    _be_status = None
                    _be_outcome = "uncertain"
                    for _ in range(12):  # ~3s at 0.25s/poll — mirrors Step 1b
                        _chk = await alpaca.get_order(be_stop_id, account_mode=account_mode)
                        _be_status = _canonical_order_status(_chk.get("status") if _chk else None)
                        if _be_status in _STOP_CONFIRMED_LIVE_STATUSES:
                            _be_outcome = "live"
                            break
                        if _be_status in _STOP_DEAD_STATUSES or _be_status == "filled":
                            _be_outcome = "dead"
                            break
                        await asyncio.sleep(0.25)
                    if _be_outcome == "live":
                        await set_stop_order_id(
                            trade_id, be_stop_id,
                            reason="breakeven_replacement",
                            account_mode=account_mode,
                        )
                        async with pool.acquire() as conn:
                            # stop_price MUST follow the broker here: the EOD trail
                            # only fires when effective_stop > DB stop_price, so a
                            # stale (lower) value would let a later trail pass
                            # cancel this stop and re-place LOWER — loosening
                            # protection. Keeping the DB at breakeven makes the
                            # trail raise-only relative to the real stop.
                            await conn.execute(
                                "UPDATE mi_live_trades SET stop_price = $2 WHERE id = $1",
                                trade_id, _be)
                            await conn.execute("""
                                INSERT INTO mi_live_orders
                                    (trade_id, alpaca_order_id, ticker, side, order_type,
                                     qty, stop_price, status, raw_response, purpose,
                                     exit_reason)
                                VALUES ($1, $2, $3, 'sell', 'stop', $4, $5, $6, $7::jsonb,
                                        'stop_loss', 'stop_hit')
                                ON CONFLICT (alpaca_order_id) DO NOTHING
                            """, trade_id, be_stop_id, ticker, float(new_remaining),
                                _be, be_order.get("status", "new"),
                                _jsonb_param(be_order))  # #216: codec single-encodes; do NOT pre-dumps
                        await log_audit_event(
                            "partial_exit_breakeven_armed",
                            f"{ticker}: stop moves to breakeven ${_be:.2f} (was "
                            f"${float(stop_price):.2f}, entry ${float(_entry):.2f}) via "
                            f"price-only replace on the reduced {new_remaining}-share "
                            f"stop ({new_stop_id[:8]}→{be_stop_id[:8]})",
                            json.dumps({
                                "trade_id": trade_id, "ticker": ticker,
                                "old_stop_id": new_stop_id, "new_stop_id": be_stop_id,
                                "stop_price": _be, "qty": new_remaining,
                                "mechanism": "price_only_replace",
                            }),
                        )
                        _be_confirmed_live = (be_stop_id, _be)
                        if trigger is not None:
                            # Operator 2026-08-18 merge: Step 3 below is ABOUT to
                            # describe this exact breakeven stop in the same
                            # Telegram as the trigger + the sale. Write the proof
                            # BEFORE that send (same convention as d2a8eb6's
                            # `stop_update_retry_succeeded`: "already went out or
                            # is about to, same code path, no gap between the
                            # two") so the WS safety-net handler in trade_stream.py
                            # can recognize this replacement as already covered
                            # and suppress its own "Stop replaced" — extending the
                            # #561 idiom to execute_partial_exit's breakeven move,
                            # not competing with it. Gated on `trigger is not
                            # None` on purpose: agent.py's /partialnow and
                            # live_tracker.py's partials do NOT get this line in
                            # Step 3 (see the docstring), so they must NOT write
                            # this evidence either — the WS safety net stays the
                            # ONLY notice for their breakeven moves, exactly as
                            # today.
                            await log_audit_event(
                                "partial_exit_stop_telegram_pending",
                                f"{ticker}: breakeven stop {be_stop_id[:8]} will be "
                                f"described in the upcoming merged partial-exit "
                                f"Telegram — WS safety-net dup-suppression evidence",
                                json.dumps({
                                    "trade_id": trade_id,
                                    "new_stop_id": be_stop_id,
                                    "new_stop_price": _be,
                                }),
                            )
                    elif _be_outcome == "dead":
                        # The replace consumed the old stop and its successor died —
                        # the 2/3 is unprotected. NULL the pointer, re-protect
                        # post-lock to broker truth (limit is netted → target 2/3,
                        # placed at the DB stop_price, still the original — valid).
                        # broker-confirmed: "dead" is set ONLY when the bounded poll's
                        # get_order(be_stop_id) returned an ACTUAL terminal status
                        # (_STOP_DEAD_STATUSES/'filled'). A raised read propagates out
                        # (no demotion runs) and a None/failed read canonicalizes to
                        # None, which matches neither status set and leaves the poll
                        # on "uncertain" — a branch that persists the pointer, never
                        # demotes. Verified 2026-08-10 (ADR 0008 fence review).
                        await set_stop_order_id(
                            trade_id, None,
                            reason="breakeven_replace_failed",
                            account_mode=account_mode,
                        )
                        be_reprotect = True
                        be_ctx = {"error": f"breakeven successor dead (status={_be_status})",
                                  "reason": "breakeven successor stop died after replace"}
                    else:
                        # Uncertain (still settling after budget). The successor
                        # LIKELY lives — persist the pointer (best broker truth; the
                        # old id is auto-cancelled by the replace) but do NOT record
                        # the breakeven price as fact. Ask the operator to eyeball;
                        # the coverage detector + sync remain the mechanical net.
                        await set_stop_order_id(
                            trade_id, be_stop_id,
                            reason="breakeven_replacement",
                            account_mode=account_mode,
                        )
                        await log_audit_event(
                            "partial_exit_breakeven_unverified",
                            f"{ticker}: breakeven replace accepted "
                            f"({new_stop_id[:8]}→{be_stop_id[:8]}) but successor not "
                            f"confirmed live within budget (status={_be_status})",
                            json.dumps({
                                "trade_id": trade_id, "ticker": ticker,
                                "old_stop_id": new_stop_id, "new_stop_id": be_stop_id,
                                "last_status": _be_status,
                            }),
                        )
                        await send_telegram_message(
                            f"{mode_prefix(account_mode)}⚠️ {ticker}: breakeven stop "
                            f"replace accepted but not confirmed live "
                            f"(status={_be_status}). Verify the stop on Alpaca — "
                            f"limit for {shares} sh rests at ${float(limit_price):.2f}."
                        )

        # Step 3: Pending fill — DO NOT commit P&L / remaining_shares / partial_taken
        # at submit time. The order may be queued (after-hours) and fill at next open
        # at an unknown price; using the placement-time response here meant fill_price
        # fell back to entry_price → printed P&L $0.00 on a sale that hadn't happened.
        # finalize_partial_exit() runs from the WS fill handler with the real fill price.
        # Skipped on the abort path (no sell placed) — that path re-protects + alerts
        # AFTER the advisory lock releases, below.
        if not abort_reprotect:
            # Operator 2026-08-18 ("these 3 msgs can be merged into one?"): when
            # `trigger` is set, THIS message becomes the one and only story of
            # the event — trigger fact, sale fact, protection fact, and (when
            # confirmed) the remaining shares' breakeven-stop fact — instead of
            # a separate trigger message racing this one. `trigger is None`
            # (agent.py /partialnow, live_tracker.py) renders every branch
            # below byte-identical to before this change.
            _remaining_stop_line = ""
            if trigger is not None:
                trigger["delivered"] = True
                if _be_confirmed_live is not None:
                    _, _be_price = _be_confirmed_live
                    _be_reason = describe_stop_move(
                        entry_price=float(_entry) if _entry is not None else None,
                        hard_stop=(float(trade["hard_stop"])
                                   if trade.get("hard_stop") is not None else None),
                        old_stop_price=float(stop_price) if stop_price else None,
                        new_stop_price=float(_be_price),
                        stop_source="breakeven",
                        brief=True,
                    )
                    _remaining_stop_line = f"\nRemaining {new_remaining} sh: {_be_reason}"
            if oco_mode:
                if trigger is not None:
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}\U0001F4B0 *Profit target hit: {ticker}*\n"
                        f"traded ${trigger['high']:.2f} >= ${trigger['target']:.2f} "
                        f"({trigger['r_multiple']:g}R above ${trigger['entry']:.2f})\n"
                        f"Limit sell {shares} of {full_remaining} sh @ "
                        f"${float(limit_price):.2f} resting at the target, with a "
                        f"stop @ ${float(oco_stop_price):.2f} on the same shares "
                        f"(Order {order['id'][:8]})\n"
                        f"Whichever side fills cancels the other — the {shares} sh "
                        f"are never without a stop."
                        f"{_remaining_stop_line}\n"
                        f"_Confirms with real P&L on fill._"
                    )
                else:
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}📋 *Profit-take resting (OCO):* {ticker}\n"
                        f"Limit sell {shares} sh @ ${float(limit_price):.2f} resting at the "
                        f"target, with a stop @ ${float(oco_stop_price):.2f} on the same "
                        f"shares (Order {order['id'][:8]})\n"
                        f"_Whichever side fills cancels the other — the {shares} sh are "
                        f"never without a stop. Confirms with real P&L on fill._"
                    )
            elif resting_mode:
                if trigger is not None:
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}\U0001F4B0 *Profit target hit: {ticker}*\n"
                        f"traded ${trigger['high']:.2f} >= ${trigger['target']:.2f} "
                        f"({trigger['r_multiple']:g}R above ${trigger['entry']:.2f})\n"
                        f"Limit sell {shares} of {full_remaining} sh @ "
                        f"${float(limit_price):.2f} — resting at the target "
                        f"(Order {order['id'][:8]})"
                        f"{_remaining_stop_line}\n"
                        f"_Fills at the price or better; confirms with real P&L on fill._"
                    )
                else:
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}📋 *Profit-take resting:* {ticker}\n"
                        f"Limit sell {shares} sh @ ${float(limit_price):.2f} — resting at "
                        f"the target (Order {order['id'][:8]})\n"
                        f"_Fills at the price or better; confirms with real P&L on fill._"
                    )
            else:
                if trigger is not None:
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}\U0001F4B0 *Profit target hit: {ticker}*\n"
                        f"traded ${trigger['high']:.2f} >= ${trigger['target']:.2f} "
                        f"({trigger['r_multiple']:g}R above ${trigger['entry']:.2f})\n"
                        f"Market sell {shares} of {full_remaining} sh — pending fill "
                        f"(Order {order['id'][:8]})\n"
                        f"_Confirms with real P&L on fill._"
                    )
                else:
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

    # ── #548 resting mode: breakeven-replace verification failed AFTER the limit
    # was placed. The PARTIAL stands (limit resting = the pending exit for the
    # 1/3) — only the 2/3's stop needs re-establishing. Same post-lock idiom as
    # the abort block above (the try-lock inside _ensure_stop_coverage is why it
    # must run after the advisory lock releases); _ensure_stop_coverage nets the
    # resting limit via get_pending_exit_qty, so its target resolves to the 2/3
    # and it re-places at the DB stop_price — still the ORIGINAL stop (the price
    # update is written only on a VERIFIED breakeven), so the price is valid.
    if be_reprotect:
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
        except Exception as _re:
            logger.error(
                f"execute_partial_exit: breakeven re-protect via _ensure_stop_coverage "
                f"raised for {ticker}: {_re}"
            )
            await log_audit_event(
                "partial_exit_reprotect_failed",
                f"{ticker}: re-protect after breakeven-replace failure raised "
                f"({type(_re).__name__}) — next sync cron will remediate",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "error": str(_re)[:500],
                }),
            )
            coverage_msg = f"⚠️ re-protect call raised: {_re}"
        _cov_line = coverage_msg or (
            "_Re-protect deferred (coverage already met, or broker read failed) — "
            "verify the stop covers the remaining shares on Alpaca; sync cron will "
            "reconcile._"
        )
        await send_telegram_message(
            f"{mode_prefix(account_mode)}⚠️ {ticker}: breakeven move FAILED "
            f"({be_ctx.get('reason', be_ctx.get('error', 'unknown'))}).\n"
            f"Limit for {shares} sh still rests at ${float(limit_price):.2f}.\n"
            f"{_cov_line}"
        )
        # The partial itself SUCCEEDED (limit resting); only breakeven degraded.
        return True

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
    prior_remaining = int(trade["remaining_shares"])
    raw_remaining = prior_remaining - shares
    # #566 ACCOUNTING INVARIANT: remaining_shares must NEVER go negative. The
    # ETON 2026-08-14 shape: the 2/3 stop fill had already zeroed the row
    # (defect: _finalize_stop_fill_locked closed unconditionally), so when the
    # resting limit later filled its 5 shares this subtraction wrote -5. Clamp
    # at 0 and record LOUDLY — a clamp firing means some earlier write already
    # lied about the position and must be investigated, not papered over.
    new_remaining = max(raw_remaining, 0)
    if raw_remaining < 0:
        logger.error(
            f"finalize_partial_exit: {ticker} fill of {shares} exceeds recorded "
            f"remaining {prior_remaining} (would be {raw_remaining}) — clamping "
            f"remaining_shares at 0; books already disagreed with the broker"
        )
        await log_audit_event(
            "remaining_shares_clamped",
            f"{ticker}: partial-exit fill {shares} > recorded remaining "
            f"{prior_remaining} — remaining_shares clamped at 0 (was heading to "
            f"{raw_remaining}); an earlier close wrote the books wrong",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker, "account_mode": account_mode,
                "filled_qty": shares, "prior_remaining": prior_remaining,
                "raw_remaining": raw_remaining, "order_id": order_id,
            }),
        )
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

    # #566: a partial fill that exhausts the position CLOSES the trade — e.g.
    # the 2/3 stopped at breakeven first (which now leaves the row OPEN at 1/3)
    # and the OCO limit then fills the rest. Leaving remaining=0 on an open row
    # is the mirror image of the ETON defect (closed-with-shares); both lie.
    # An already-closed row (late fill — should be unreachable once the
    # stop-fill fix is live) just absorbs the exit without re-closing.
    close_now = new_remaining == 0 and trade.get("status") != "closed"
    async with pool.acquire() as conn:
        if close_now:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    exits = $2::jsonb,
                    remaining_shares = $3,
                    total_pnl = $4,
                    partial_taken = TRUE,
                    breakeven_active = TRUE,
                    status = 'closed',
                    stop_order_id = NULL,
                    closed_at = NOW()
                WHERE id = $1
            """, trade_id, exits, new_remaining, total_pnl)
        else:
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
        f"{ticker}: DB committed on WS fill — sold {shares} @${filled_price:.2f}, pnl ${pnl:+,.2f}, remaining {new_remaining}"
        + (" — position CLOSED" if close_now else ""),
        json.dumps({
            "trade_id": trade_id, "ticker": ticker,
            # #525: the row that CLOSES the breaker must say which book it closed. Until
            # 2026-08-08 it did not, and a PAPER success closed the LIVE breaker — 12 of the
            # 14 successes that had ever reset it were paper. The breaker query still
            # back-derives mode via trade_id for historical rows, but a row that carries its
            # own mode cannot be misattributed by a later schema or join change.
            "account_mode": account_mode,
            "shares": shares, "fill_price": float(filled_price),
            "pnl": float(pnl), "total_pnl": float(total_pnl),
            "new_remaining": new_remaining,
            "closed": close_now,
            "order_id": order_id,
        }),
    )
    await send_telegram_message(
        f"{mode_prefix(account_mode)}📤 *Partial exit FILLED:* {ticker}\n"
        f"Sold {shares} shares @${filled_price:.2f}\n"
        f"P&L: ${pnl:+,.2f} | Remaining: {new_remaining}"
        + (f"\nPosition closed — total P&L ${total_pnl:+,.2f}" if close_now else "")
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
    # Terminal-status set: PENDING_EXIT_TERMINAL_STATUSES (SSoT, #591 review).
    async with pool.acquire() as conn:
        pending = await conn.fetchrow("""
            SELECT alpaca_order_id, purpose FROM mi_live_orders
            WHERE trade_id = $1
              AND purpose IN ('partial_exit', 'full_exit')
              AND status != ALL($2::text[])
            LIMIT 1
        """, trade_id, list(PENDING_EXIT_TERMINAL_STATUSES))
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
            order.get("status", "new"), reason,
            _jsonb_param(order))  # #216: codec single-encodes; do NOT pre-dumps

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

    # #566 ACCOUNTING FIX (the ETON 2026-08-14 defect 2). This function closed
    # the trade UNCONDITIONALLY — status='closed', remaining_shares=0 — even
    # when the filled stop covered only PART of the position. ETON: the 2/3
    # breakeven stop (12 sh) filled, the row was zeroed while the broker still
    # held 5 sh behind the resting limit — no stop, no trail, invisible to
    # every surface reading the row; the later limit fill then wrote -5.
    # A partial-qty stop fill now DECREMENTS and the row stays OPEN; only a
    # fill that exhausts the position closes it.
    prior_remaining = int(trade.get("remaining_shares") or 0)
    raw_remaining = prior_remaining - int(filled_qty)
    new_remaining = max(raw_remaining, 0)
    if raw_remaining < 0:
        logger.error(
            f"finalize_stop_fill: {ticker} stop fill {int(filled_qty)} exceeds "
            f"recorded remaining {prior_remaining} — clamping remaining_shares at 0"
        )
        await log_audit_event(
            "remaining_shares_clamped",
            f"{ticker}: stop fill {int(filled_qty)} > recorded remaining "
            f"{prior_remaining} — remaining_shares clamped at 0 (was heading to "
            f"{raw_remaining}); books already disagreed with the broker",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker, "account_mode": account_mode,
                "filled_qty": int(filled_qty), "prior_remaining": prior_remaining,
                "raw_remaining": raw_remaining, "order_id": order_id,
            }),
        )

    async with pool.acquire() as conn:
        if new_remaining > 0:
            # Shares remain at the broker (e.g. the OCO third behind its own
            # held stop leg). NEVER mark closed while shares remain. The stop
            # pointer is nulled ONLY if the filled order IS the tracked stop
            # (the OCO leg is deliberately not stop_order_id — the pointer
            # keeps tracking the 2/3's stop).
            await conn.execute("""
                UPDATE mi_live_trades SET
                    exits = $2::jsonb,
                    remaining_shares = $3,
                    total_pnl = $4,
                    stop_order_id = CASE WHEN stop_order_id = $5
                                         THEN NULL ELSE stop_order_id END
                WHERE id = $1
            """, trade_id, exits, new_remaining, total_pnl, order_id)
        else:
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
        f"pnl ${pnl:+,.2f}, total ${total_pnl:+,.2f}"
        + (f" — {new_remaining} sh remain, trade stays OPEN" if new_remaining > 0 else ""),
        json.dumps({
            "trade_id": trade_id, "ticker": ticker,
            "shares": int(filled_qty), "fill_price": float(filled_price),
            "pnl": float(pnl), "total_pnl": float(total_pnl),
            "new_remaining": new_remaining,
            "attempt": attempt, "order_id": order_id,
        }),
    )

    await send_telegram_message(
        f"{mode_prefix(account_mode)}❌ *Stopped out:* {ticker} @${filled_price:.2f}\n"
        f"P&L: ${pnl:+,.2f} | shares: {filled_qty}"
        + (f"\n{new_remaining} sh remain — position stays open (resting exit still working)"
           if new_remaining > 0 else "")
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


def _cleanup_cancel_label(explicit_mode: str | None, touched_modes: set[str]) -> str:
    """Telegram-prefix label for a cancel-digest that may span BOTH books.

    `explicit_mode` is `cancel_unfilled_entries`'s OWN `account_mode` param.
    When the CALLER scoped the run to one book (operator /pause passes
    account_mode="live"), the SQL WHERE already filtered to that mode, so
    every row IS it by construction — render via `mode_prefix(explicit_mode)`
    exactly as before (unchanged path, do not touch).

    When `explicit_mode` is None (the 10:00 ET / 4:05 PM batch cleanup paths
    — cancellations genuinely span both books), do NOT call bare
    `mode_prefix(None)`: it silently falls back to `current_account_mode()`,
    which reads the `ALPACA_PAPER` env var — NOT which book the cancelled
    rows actually belonged to. That mismatch is the 2026-08-11 RIOT bug: a
    LIVE order's cancel-cleanup was labelled 📄 PAPER because the container's
    global default is paper. `mode_prefix`'s None-guessing default is a known
    fragile hazard elsewhere too — do not lean on it here; derive the label
    from the rows actually touched instead:
      - every touched row the same mode -> label that mode
      - a mix of live+paper (or nothing touched — should be unreachable, since
        callers only send a message when `cancelled`/`failed_tickers` is
        non-empty, but never fall back to a guess even here) -> say so
        explicitly, don't guess.
    """
    if explicit_mode is not None:
        return mode_prefix(explicit_mode)
    if len(touched_modes) == 1:
        return mode_prefix(next(iter(touched_modes)))
    return "⚠️ MIXED live+paper "


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
    cancelled_modes: set[str] = set()
    failed_modes: set[str] = set()
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
            cancelled_modes.add(trade_mode)
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
            failed_modes.add(trade_mode)
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
        # #444 threaded this function's OWN account_mode param (the filter used
        # in the query above): set (operator /pause passes account_mode="live")
        # -> every cancelled row IS that one mode, digest labels correctly.
        #
        # 2026-08-11 fix (RIOT mislabel): the None case — the batch cleanup
        # paths, where cancellations genuinely span both books — must NOT fall
        # through to bare mode_prefix(None). That silently guesses via
        # current_account_mode() (the env default), not which book was
        # actually touched, which is exactly how a LIVE cancel got labelled
        # 📄 PAPER. `_cleanup_cancel_label` derives the label from the modes
        # of the rows actually cancelled instead of guessing.
        await send_telegram_message(
            f"{_cleanup_cancel_label(account_mode, cancelled_modes)}🕓 {reason}: cancelled {cancelled} unfilled order(s) — {', '.join(cancelled_tickers)}"
        )
    if failed_tickers:
        # Same derivation for the cancel-FAILED digest — an operator dismissing
        # a "PAPER" cancel-failure that was really live is the dangerous version
        # of the mislabel above (a resting real-money order stays live and
        # unflagged).
        await send_telegram_message(
            f"{_cleanup_cancel_label(account_mode, failed_modes)}⚠️ {reason}: cancel FAILED for {len(failed_tickers)} order(s) — {', '.join(failed_tickers)} — investigate broker side"
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


def _leg_unfilled_qty(order: dict, order_qty: float) -> float | None:
    """#596 — the shares cancelling this order would actually RELEASE: its
    order quantity MINUS what it has already filled.

    `partially_filled` is a live-stop status, so a stop that has already sold
    part of itself still reads as protection. Its ORDER qty is then a lie about
    what it holds: the filled shares are gone from the position and from the
    broker's reservation. Any decision about what a cancel frees must use this,
    never `qty` (the #596 naked hazard: a partly-filled leg passed the widen
    pre-flight on its order qty, got cancelled, and could not be replaced).

    Returns None when `filled_qty` is missing or unparseable — the CALLER must
    treat that as "refuse", never as zero. A real broker dict always carries
    the field (`alpaca_client._order_to_dict` defaults it to 0), so None means
    a malformed row, and defaulting it to 0 would silently restore the exact
    over-statement this exists to remove. PURE: no broker or DB access.
    """
    raw = order.get("filled_qty")
    if raw is None:
        return None
    try:
        filled = float(raw)
    except (TypeError, ValueError):
        return None
    if filled < 0:
        return None
    return max(float(order_qty) - filled, 0.0)


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


# ── #599: THREE outcomes, not one nullable string ───────────────────────────
# `_ensure_stop_coverage` returned `str | None`, and `None` meant THREE
# different things: (a) coverage was CHECKED and meets target, (b) a partial
# held the per-trade advisory lock so NOTHING was checked, (c) the broker
# orders-read failed so NOTHING was checked. `retry_failed_coverage_repairs`
# (#596) read that `None` as "healed", audited it as "coverage now meets
# target", and SPENT one of its six attempts on a pass that verified nothing —
# so recurring lock contention or broker flakiness could burn the whole budget
# on non-checks, drop the trade out of the retry set, and the exhaustion 🚨
# would never fire because every attempt looked healthy.
#
# The STATUS below is the control signal. `message` is unchanged — it is the
# operator-facing Telegram text, emoji prefix and all; the bug was never the
# emoji, it was using the emoji as a control signal.
COVERAGE_COVERED = "covered"        # CHECKED — coverage meets target, nothing to do
COVERAGE_UNVERIFIED = "unverified"  # NOT CHECKED — lock held / broker unreadable → defer
COVERAGE_REPAIRED = "repaired"      # CHECKED — acted, coverage now meets target
COVERAGE_FLAGGED = "flagged"        # CHECKED — could not (or must not) fix; operator told

# The two statuses that mean "this pass verified the position's coverage".
_COVERAGE_VERIFIED_OK = (COVERAGE_COVERED, COVERAGE_REPAIRED)


class CoverageOutcome(NamedTuple):
    """One `_ensure_stop_coverage` pass, told apart at the SOURCE (#599).

    `message` is EXACTLY the human string the function has always returned
    (None when it had nothing to say). `_ensure_stop_coverage` is a thin
    wrapper handing back this field, so every pre-#599 caller is byte-identical.
    `status` is what a caller must branch on; `reason` is the machine tag that
    rides along into the audit row.
    """
    status: str
    message: str | None
    reason: str


async def _ensure_stop_coverage_outcome(
    trade_id: int,
    ticker: str,
    broker_qty: float,
    db_stop_price: float | None,
    signal_type: str,
    account_mode: str,
) -> CoverageOutcome:
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
      * under-covered, exactly ONE live stop, SIMPLE order   → atomic qty-only
            `replace_order` to `target` (keeps the accepted stop_price → can't
            breach); SINGLE stop, never an additive 2nd order.
      * under-covered, exactly ONE live stop, ADVANCED-ORDER  → #523: `replace_order`
            LEG (toggle `partial_exit_leg_safe` ON)            would be rejected
            (42210000, same as #508) — widen via the SAME verified-cancel →
            release-gate → new-stop mechanism instead (`_widen_stop_via_cancel_new`),
            after a pre-flight broker read confirms enough shares will be available
            post-cancel — sized on the leg's UNFILLED REMAINDER (#596), never its
            order qty, since a partly-filled leg releases only what it still
            holds. Toggle OFF → falls through to the atomic replace above,
            which fails exactly as it does today (safe: old leg stays live).
      * under-covered, NO live stop                          → `place_stop_order`
            at `db_stop_price` (the place branch is the only one that can breach).

    Idempotent: a 2nd consecutive run sees coverage == target → no-op, no new
    orders. Every submit is MODE-SCOPED via `make_client_order_id(account_mode,
    ...)`. On a stop-above-market BREACH (place branch), emit ONE discrepancy
    line + audit and CONVERGE — no retry, no auto-market-exit, no stop_order_id
    write (the breach-exit is the operator's call).

    Returns a `CoverageOutcome` (#599). `.message` is the human discrepancy
    string when it acted/flagged (for the batched Telegram), else None — the
    exact pre-#599 return, which `_ensure_stop_coverage` still hands back
    unchanged. `.status` says WHICH kind of pass this was: a `COVERAGE_COVERED`
    no-op (checked, fine) is a completely different fact from a
    `COVERAGE_UNVERIFIED` no-op (lock held or broker unreadable — nothing was
    checked), and the two used to be the same `None`.
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
            # #599: NOT a coverage check. The partial owns coverage right now and
            # its own abort path re-protects; the CALLER must be able to tell this
            # from "checked and fine" so it can try again rather than bank it.
            return CoverageOutcome(COVERAGE_UNVERIFIED, None, "partial_in_flight")
        target = float(broker_qty) - float(await get_pending_exit_qty(trade_id))
        if target <= 0.5:
            # Pending exits account for the whole (or all-but-noise) position —
            # nothing to protect beyond what's already in flight. The orphan loop's
            # own "fully covered by pending exits" guard handles the no-stop variant;
            # here we just decline to place/replace.
            return CoverageOutcome(
                COVERAGE_COVERED, None, "pending_exits_cover_position")

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
            # #599: ambiguous (couldn't read the broker) — defer to the next run.
            # This is a NON-CHECK, not a clean bill of health. `get_open_orders`
            # has already fired the deduped alpaca API alert (#370) before
            # re-raising, so the operator hears about the read failure itself.
            return CoverageOutcome(
                COVERAGE_UNVERIFIED, None, "open_orders_read_failed")

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
            return CoverageOutcome(
                COVERAGE_FLAGGED,
                f"⚠️ {ticker}: {len(live_stops)} live stops (target {target:.0f}) "
                f"— ambiguous, left for review",
                "multiple_live_stops",
            )

        live_stop = live_stops[0] if live_stops else None
        live_qty = None
        if live_stop is not None:
            try:
                live_qty = float(live_stop.get("qty")) if live_stop.get("qty") is not None else None
            except (TypeError, ValueError):
                live_qty = None

        # Fully covered (within tolerance) or over-covered → no-op. THE one
        # `None` that genuinely means "checked, and coverage meets target" (#599).
        if live_qty is not None and live_qty >= target - 0.5:
            return CoverageOutcome(
                COVERAGE_COVERED, None, "live_stop_meets_target")

        # Under-covered (or no live stop): re-protect to `target` as a SINGLE stop.
        coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)

        if live_stop is not None:
            # #523: if the live stop is an advanced-order (OTO/bracket) LEG,
            # Alpaca rejects EVERY qty replace on it (42210000 — the same
            # rejection #508 hit on the partial-exit path; every MAGNA53 entry's
            # stop is a leg on its entry day). Route through the SAME
            # verified-cancel → reservation-release-gate → new-stop mechanism
            # `_reduce_stop_via_cancel_new` uses for partial-exit reductions —
            # widen instead of reduce — gated behind the SAME toggle so one
            # switch governs both sites. `order_class` is already on the
            # fetched order dict (unlike the partial-exit site, no extra
            # broker read is needed to learn it).
            leg_safe_on = await get_runtime_toggle(
                "partial_exit_leg_safe", "PARTIAL_EXIT_LEG_SAFE", default=False)
            # live_qty is None when the fetched order dict's qty is missing/
            # unparseable (pre-existing possibility — see its computation
            # above). The leg-safe branch below does arithmetic on live_qty
            # (the pre-flight headroom check); never route there without a
            # real number. Falls through to the atomic replace, exactly the
            # pre-#523 behavior for this edge case regardless of order_class.
            stop_is_leg = leg_safe_on and live_qty is not None and (
                str(live_stop.get("order_class") or "").lower()
                in _ADVANCED_ORDER_CLASSES
            )

            new_order = None
            last_err: Exception | None = None
            widen_outcome: dict | None = None

            if not stop_is_leg:
                # Atomic qty-only replace — keeps the already-accepted stop_price (so it
                # cannot breach) and never opens a share-release window. New order id
                # must be persisted. UNCHANGED from before #523 — this is the only
                # path reached when the toggle is off or the stop is a simple order.
                try:
                    new_order = await alpaca.replace_order(
                        live_stop["id"],
                        qty=int(target),
                        account_mode=account_mode,
                        client_order_id=coid,
                    )
                except Exception as e:  # loud-ok: not swallowed — the unified
                    # `if new_order is None:` block just below logs, audits
                    # (stop_coverage_repair_failed), and returns the operator
                    # message for BOTH this branch and the leg-safe one.
                    last_err = e
            else:
                # Leg-safe widen. stop_price MUST be the leg's OWN already-accepted
                # broker price (never db_stop_price, never recomputed) — the atomic
                # replace above changes qty only for the same reason; cancel+new must
                # be told a price explicitly, so it has to be told the price that is
                # already live. THE LINE: quantity only, never level.
                _widen_price = live_stop.get("stop_price")
                # #596: what a cancel actually RELEASES is the leg's UNFILLED
                # remainder, not its order quantity. `partially_filled` is a
                # live-stop status (`_STOP_CONFIRMED_LIVE_STATUSES`), so a leg
                # that has already sold part of itself reaches this branch with
                # `live_qty` = the ORDER qty — shares it no longer holds. Sizing
                # the pre-flight on that over-states headroom by exactly
                # `filled_qty`, so a cancel that cannot be replaced passes the
                # one gate built to make that unreachable. Unreadable → REFUSE
                # (same idiom as the missing stop_price above): if we cannot
                # compute what the cancel frees, we must not cancel. A real
                # broker dict always carries filled_qty (`_order_to_dict`
                # defaults it to 0), so this can only fire on a malformed row.
                _leg_unfilled = _leg_unfilled_qty(live_stop, live_qty)
                if _widen_price is None:
                    last_err = RuntimeError(
                        f"leg-safe widen: live stop {live_stop['id']} has no "
                        f"readable stop_price — cannot safely place a new one")
                elif _leg_unfilled is None:
                    last_err = RuntimeError(
                        f"leg-safe widen: live stop {live_stop['id']} has an "
                        f"unreadable filled_qty — cannot size what the cancel "
                        f"would release; refusing to cancel a leg we can't "
                        f"safely replace")
                else:
                    # Pre-flight, BEFORE cancelling anything: verify the broker will
                    # actually have `target` shares available once the leg is
                    # cancelled. Unlike the REDUCE direction (new qty is always <=
                    # what the cancel itself frees, so the release gate can only
                    # ever find enough), a WIDEN's new qty is LARGER than the leg's
                    # own qty by construction — if some other reservation this
                    # function doesn't account for is holding shares, the release
                    # gate would time out only AFTER the leg is already cancelled,
                    # turning today's guaranteed-safe failure (under-covered, old
                    # stop live) into a genuinely naked one. Checking first makes
                    # that failure mode unreachable instead of recovered from.
                    _pos = await alpaca.get_position(ticker, account_mode=account_mode)
                    _avail = (float(_pos["qty_available"])
                              if _pos and _pos.get("qty_available") is not None else None)
                    if _avail is None or (_avail + _leg_unfilled) < target - 0.5:
                        last_err = RuntimeError(
                            f"leg-safe widen: only {_avail if _avail is not None else '?'} "
                            f"available + {_leg_unfilled:.0f} still unfilled on the leg "
                            f"(order qty {live_qty:.0f}) — not enough to reach "
                            f"target {target:.0f} after cancel; refusing to cancel a leg "
                            f"we can't safely replace")
                    else:
                        new_order, widen_outcome = await _widen_stop_via_cancel_new(
                            trade_id, ticker, live_stop["id"], int(target),
                            float(_widen_price), signal_type, account_mode,
                        )
                        if widen_outcome["kind"] != "ok":
                            last_err = RuntimeError(widen_outcome["detail"])

            if new_order is None:
                e = last_err if last_err else RuntimeError("replace_order unreached")
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
                        **({"mechanism": "leg_safe_cancel_new",
                            "widen_outcome": widen_outcome["kind"],
                            "timings_ms": widen_outcome["timings"]}
                           if widen_outcome else {}),
                    }),
                )
                if widen_outcome and widen_outcome["kind"] in ("naked", "stop_filled"):
                    # The old (under-covering) leg is CONFIRMED gone (cancelled or
                    # filled) and no replacement was placed — this is NOT the safe
                    # "under-covered, old stop still live" state the toggle-off path
                    # guarantees; coverage may be ZERO. Say so plainly rather than
                    # reusing the "failed to widen X→Y" phrasing below, which would
                    # falsely imply the old stop is still there. Do NOT place a stop
                    # here: broker_qty may now be stale (a fill can precede this
                    # outcome) — sizing off it risks an oversized order. The next
                    # reconciler pass re-reads broker truth from scratch and repairs
                    # (place branch below, no live stop found).
                    return CoverageOutcome(
                        COVERAGE_FLAGGED,
                        f"🚨 {ticker}: leg-safe widen left the old stop "
                        f"{widen_outcome['kind']} with no confirmed replacement — "
                        f"coverage may be ZERO, not just under {live_qty}→{target:.0f}. "
                        f"Next reconciler pass re-protects.",
                        f"widen_left_stop_{widen_outcome['kind']}",
                    )
                return CoverageOutcome(
                    COVERAGE_FLAGGED,
                    f"⚠️ {ticker}: failed to widen stop coverage "
                    f"{live_qty}→{target:.0f}: {e}",
                    "replace_under_covering_stop_failed",
                )
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
                    **({"mechanism": "leg_safe_cancel_new",
                        "timings_ms": widen_outcome["timings"]}
                       if widen_outcome else {}),
                }),
            )
            # Pre-existing latent bug, surfaced by #523's live_qty=None test: `:.0f` on a
            # None crashes. live_qty prints plain elsewhere in this function for exactly
            # this reason (e.g. the audit summary two lines up) — match that here too.
            _live_qty_disp = f"{live_qty:.0f}" if live_qty is not None else str(live_qty)
            return CoverageOutcome(
                COVERAGE_REPAIRED,
                f"🛡 Coverage repaired {ticker}: stop {_live_qty_disp}→{target:.0f} "
                f"(under-covering after partial-exit failure)",
                "replaced_under_covering_stop",
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
            return CoverageOutcome(
                COVERAGE_FLAGGED,
                f"⚠️ {ticker}: no stop & no stop_price (target {target:.0f}) "
                f"— manual intervention needed",
                "no_stop_and_no_stop_price",
            )
        # #600: never re-arm BELOW the last level the broker held. `db_stop_price`
        # can be stale-low (the breakeven replace withholds it on an unconfirmed
        # outcome — see _floor_reprotect_price); the DB's own stop pointer, read
        # fresh, names the broker order whose price WAS the protection, even when
        # that order is now terminal. No broker truth → the DB price, exactly as
        # before #600 — a re-protect NEVER refuses to place.
        # #600 fork 2 (2026-09-04): the pointer is commonly ALREADY NULL here —
        # `_handle_cancel_or_reject` nulls it on the WS cancel/expiry before this
        # retry/sync ever runs — so consult the price it preserved at that moment.
        _db_stop_price_f = float(db_stop_price)
        place_price = await _apply_reprotect_floor(
            trade_id, ticker, _db_stop_price_f,
            await _current_stop_pointer(trade_id), account_mode,
            site="ensure_stop_coverage.place",
            consult_dead_stop=True,
        )
        try:
            new_order = await alpaca.place_stop_order(
                ticker, int(target), place_price,
                account_mode=account_mode, client_order_id=coid,
            )
        except Exception as e:
            if _is_stop_above_market(e):
                # BREACH: the protective trigger is at/above current price. NOT
                # retryable. ONE alert, converge, leave for operator. Do NOT
                # auto-market-exit and do NOT write stop_order_id.
                await log_audit_event(
                    "stop_coverage_breach",
                    f"{ticker}: stop ${place_price:.2f} would sit above market — "
                    f"position through the stop. Operator action required (no auto-exit).",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker,
                        "account_mode": account_mode,
                        "intended_stop_price": place_price,
                        "db_stop_price": _db_stop_price_f,
                        "target_qty": target, "error": str(e),
                    }),
                )
                logger.error(
                    f"_ensure_stop_coverage: BREACH for {ticker} — stop "
                    f"${place_price:.2f} above market; converging (no retry, no auto-exit)"
                )
                return CoverageOutcome(
                    COVERAGE_FLAGGED,
                    f"🚨 {ticker}: stop ${place_price:.2f} is ABOVE market — "
                    f"position breached the stop. Operator decision needed "
                    f"(no auto-exit).",
                    "stop_above_market_breach",
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
            return CoverageOutcome(
                COVERAGE_FLAGGED,
                f"⚠️ {ticker}: failed to place coverage stop (target {target:.0f}): {e}",
                "place_coverage_stop_failed",
            )
        await set_stop_order_id(
            trade_id, new_order["id"],
            reason="sync_coverage_repair",
            account_mode=account_mode,
        )
        await log_audit_event(
            "stop_coverage_repaired",
            f"{ticker}: placed coverage stop {int(target)} @ ${place_price:.2f} "
            f"(was no live stop)",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "account_mode": account_mode,
                "new_stop_id": new_order["id"], "target_qty": target,
                "stop_price": place_price,
                "db_stop_price": _db_stop_price_f,
            }),
        )
        return CoverageOutcome(
            COVERAGE_REPAIRED,
            f"🛡 Coverage placed {ticker}: stop {target:.0f} @ ${place_price:.2f} "
            f"(no live stop, under-covered)",
            "placed_coverage_stop",
        )


async def _ensure_stop_coverage(
    trade_id: int,
    ticker: str,
    broker_qty: float,
    db_stop_price: float | None,
    signal_type: str,
    account_mode: str,
) -> str | None:
    """The pre-#599 face of the coverage invariant: the human discrepancy string
    when it acted/flagged, else None.

    UNCHANGED CONTRACT, deliberately. `_sync_positions_for_mode`,
    `execute_partial_exit`'s abort and breakeven re-protect paths, and
    `trade_stream`'s OCO-cancel re-protect all batch this string into a Telegram
    and treat None as "nothing to say" — which is correct for them, because the
    next reconciler pass covers them either way. Only
    `retry_failed_coverage_repairs` needs to tell a checked no-op from an
    unchecked one (it BUDGETS attempts), so only it calls
    `_ensure_stop_coverage_outcome` directly.
    """
    outcome = await _ensure_stop_coverage_outcome(
        trade_id, ticker, broker_qty, db_stop_price, signal_type, account_mode,
    )
    return outcome.message


# #596 — how many times one trade's failed coverage repair may be re-driven in
# a single ET session. A repair that has failed six times in a row is not a
# transient broker hiccup; it is something only the operator can resolve, and
# an unbounded retry would hammer the broker and the breaker's failure counter.
_COVERAGE_RETRY_MAX_ATTEMPTS = 6

# Audit event types the retry state machine reads. `stop_coverage_breach` is
# read only to STOP retrying: a stop that would sit above market is structurally
# un-retryable (`_is_stop_above_market`), `_ensure_stop_coverage` converges on it
# by design — ONE alert, operator's call — and the breach-exit decision is the
# operator's, not the reconciler's. A breach never STARTS a retry, and a breach
# recorded after a failure ENDS it, so this can never resurrect the loop that
# convergence exists to prevent.
_COVERAGE_RETRY_FAIL_EVENT = "stop_coverage_repair_failed"
_COVERAGE_RETRY_OK_EVENT = "stop_coverage_repaired"
_COVERAGE_RETRY_ATTEMPT_EVENT = "stop_coverage_retry_attempted"
_COVERAGE_RETRY_BREACH_EVENT = "stop_coverage_breach"
# #599 — a pass that could NOT CHECK coverage (a partial held the per-trade
# advisory lock, or the broker orders-read failed). Durable record, deliberately
# a DIFFERENT event type from `_COVERAGE_RETRY_ATTEMPT_EVENT`: only attempt rows
# spend the budget, so a non-check leaves the trade in the retry set for the next
# 5-minute cycle instead of banking it as healed. Before #599 both were the same
# `None` return and a non-check both audited as healed AND spent an attempt.
_COVERAGE_RETRY_DEFER_EVENT = "stop_coverage_retry_deferred"


async def retry_failed_coverage_repairs() -> dict:
    """#596 — re-drive `_ensure_stop_coverage` for trades whose repair FAILED.

    THE HOLE THIS FILLS. When a coverage repair fails, the position can be left
    genuinely unprotected (the leg-safe widen's `naked`/`stop_filled` outcomes
    confirm the old stop is gone with no replacement). Until now that produced
    ONE 🚨 Telegram and nothing else: the 15-minute `check_position_coverage`
    job only DETECTS, and the next scheduled REPAIR is `sync_positions` inside
    `eod_cleanup` at 16:05 ET. A failure at 09:31 therefore sat unrepaired for
    the whole session unless an event-driven caller happened to fire.

    NOT A NEW MECHANISM — the same signed repair (#523/#151), driven again.
    This function decides only WHEN to re-run it; every order decision stays
    inside `_ensure_stop_coverage`, which re-reads BROKER TRUTH from scratch
    (position qty + open orders) rather than trusting anything captured here.
    It changes no stop price, no target, no size: quantity coverage only.

    Selection (audit log IS the state, same idiom as
    `_coverage_gap_already_alerted_today`): a trade is retried when, within
    TODAY's ET day, its most recent `stop_coverage_repair_failed` is not
    followed by a `stop_coverage_repaired`, and it has had fewer than
    `_COVERAGE_RETRY_MAX_ATTEMPTS` retries. On the last permitted attempt the
    operator is told retries are exhausted — the alert stops being once-only
    without becoming a bombardment.

    #599 — ONLY A VERIFIED PASS SPENDS THE BUDGET. `_ensure_stop_coverage`
    returns `COVERAGE_UNVERIFIED` when it could not check at all (a partial holds
    the per-trade advisory lock, or the broker orders-read failed). Such a pass
    records `stop_coverage_retry_deferred`, does NOT count as an attempt and does
    NOT report healed, so the trade stays in the retry set for the next 5-minute
    cycle — which is the entire point of having a retry. Previously both cases
    came back as a bare `None`, were audited "coverage now meets target", and each
    burned one of the six attempts: on recurring contention or broker flakiness a
    trade could exhaust the budget on passes that verified nothing and drop out
    silently, with the exhaustion 🚨 never firing because every attempt looked
    healthy.

    Both account modes (`active_account_modes()`), deliberately: this drives the
    SAME function `sync_positions` drives, and sync_positions runs per-mode. The
    live-only scoping of `check_position_coverage` is a DETECTOR choice (no
    dollars at risk on paper) and does not apply to a repairer whose paper-side
    no-op is free.

    Idempotent and safe to run on a healthy book: a trade with no failure row
    is never touched, and `_ensure_stop_coverage` no-ops when coverage already
    meets target. Returns {"examined", "retried", "resolved", "exhausted"}.
    """
    from agents.market_intelligence.collector import et_today

    today = et_today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_type, detail, created_at
            FROM mi_audit_log
            WHERE event_type = ANY($1::text[])
              AND (created_at AT TIME ZONE 'America/New_York')::date = $2
            ORDER BY created_at ASC
            """,
            [_COVERAGE_RETRY_FAIL_EVENT, _COVERAGE_RETRY_OK_EVENT,
             _COVERAGE_RETRY_ATTEMPT_EVENT, _COVERAGE_RETRY_BREACH_EVENT,
             _COVERAGE_RETRY_DEFER_EVENT],
            today,
        )

    # Fold the day's rows into per-trade state. Python, not SQL: `detail` is
    # TEXT (not jsonb) so a malformed row must be SKIPPED rather than fail the
    # whole scan — the same reason trade_stream parses its evidence rows here.
    state: dict[int, dict] = {}
    for r in rows:
        try:
            d = json.loads(r["detail"]) if r["detail"] else None
        except (TypeError, ValueError):  # loud-ok below: one bad row must not blind the scan
            logger.warning(
                f"retry_failed_coverage_repairs: unparseable detail on a "
                f"{r['event_type']} row — skipped"
            )
            continue
        if not isinstance(d, dict) or d.get("trade_id") is None:
            continue
        try:
            tid = int(d["trade_id"])
        except (TypeError, ValueError):
            continue
        s = state.setdefault(
            tid, {"failed_at": None, "repaired_at": None, "breached_at": None,
                  "attempts": 0, "deferrals": 0, "ticker": None,
                  "account_mode": None},
        )
        s["ticker"] = d.get("ticker") or s["ticker"]
        s["account_mode"] = d.get("account_mode") or s["account_mode"]
        if r["event_type"] == _COVERAGE_RETRY_FAIL_EVENT:
            s["failed_at"] = r["created_at"]
        elif r["event_type"] == _COVERAGE_RETRY_OK_EVENT:
            s["repaired_at"] = r["created_at"]
        elif r["event_type"] == _COVERAGE_RETRY_BREACH_EVENT:
            s["breached_at"] = r["created_at"]
        elif r["event_type"] == _COVERAGE_RETRY_ATTEMPT_EVENT:
            s["attempts"] += 1
        elif r["event_type"] == _COVERAGE_RETRY_DEFER_EVENT:
            # #599: a pass that could not CHECK. Counted for telemetry only —
            # never against the attempt budget. ⚠ This used to be an `else:
            # s["attempts"] += 1` catch-all; folding a new event type into it
            # would silently re-create the exact bug #599 fixes, so every event
            # type this scan fetches now has its OWN branch and the final else
            # does nothing.
            s["deferrals"] += 1

    modes = set(active_account_modes())
    examined = 0
    retried = 0
    resolved = 0
    exhausted = 0
    deferred = 0

    for trade_id, s in state.items():
        if s["failed_at"] is None:
            continue
        if s["repaired_at"] is not None and s["repaired_at"] > s["failed_at"]:
            continue  # a later repair already succeeded — nothing outstanding
        if s["breached_at"] is not None and s["breached_at"] >= s["failed_at"]:
            # The position is THROUGH its stop. `_ensure_stop_coverage` already
            # converged and told the operator; re-driving would re-submit a
            # structurally invalid stop and re-decide a call that is his.
            continue
        examined += 1
        if s["attempts"] >= _COVERAGE_RETRY_MAX_ATTEMPTS:
            exhausted += 1
            continue

        async with pool.acquire() as conn:
            trade = await conn.fetchrow(
                """
                SELECT id, ticker, remaining_shares, stop_price, orb_low,
                       signal_type, account_mode
                FROM mi_live_trades
                WHERE id = $1 AND status = 'filled' AND remaining_shares > 0
                """,
                trade_id,
            )
        if trade is None:
            continue  # closed / flat since the failure — nothing left to protect
        account_mode = trade["account_mode"] or s["account_mode"]
        if account_mode not in modes:
            continue
        ticker = trade["ticker"]

        # BROKER TRUTH for sizing, re-read now — never the qty the failed
        # attempt came in with (a fill can have landed since; that staleness is
        # exactly why the widen's `naked` outcome refuses to place a stop
        # itself and defers to a fresh pass like this one).
        try:
            pos = await alpaca.get_position(ticker, account_mode=account_mode)
        except Exception as e:
            logger.warning(
                f"retry_failed_coverage_repairs: get_position failed for "
                f"{ticker} [{account_mode}]: {e} — deferring to next run"
            )
            continue
        broker_qty = float(pos["qty"]) if pos and pos.get("qty") is not None else 0.0
        if broker_qty <= 0:
            continue  # flat at the broker — nothing to cover

        attempt_no = s["attempts"] + 1
        # #599: the STRUCTURED result. The retry is the one caller that must tell
        # "checked, and covered" from "could not check" — it budgets attempts, and
        # banking a non-check as an attempt is what silenced the exhaustion alert.
        try:
            outcome = await _ensure_stop_coverage_outcome(
                trade_id, ticker, broker_qty,
                trade["stop_price"] or trade["orb_low"],
                trade["signal_type"] or "unknown",
                account_mode,
            )
        except Exception as e:
            logger.error(
                f"retry_failed_coverage_repairs: _ensure_stop_coverage raised "
                f"for {ticker}: {e}", exc_info=True,
            )
            # Deliberately FLAGGED, not UNVERIFIED (#599): an exception out of the
            # invariant is arguably "couldn't check" too, but it already counts and
            # already reaches the exhaustion alert today. Relabelling it unverified
            # would create a NEW silent-forever path — the opposite of this fix.
            outcome = CoverageOutcome(
                COVERAGE_FLAGGED,
                f"⚠️ {ticker}: coverage retry errored: {e}",
                "invariant_raised",
            )
        msg = outcome.message

        if outcome.status == COVERAGE_UNVERIFIED:
            # NOTHING WAS CHECKED — a partial holds the advisory lock, or the
            # broker orders-read failed (which fires its own deduped alpaca alert
            # before re-raising). Leave the trade in the retry set: no attempt row,
            # so no budget spent and the next 5-minute cycle tries again. Durable
            # record only; no Telegram, because the position's true state is
            # unknown rather than newly bad, and the original repair failure has
            # already alerted.
            deferred += 1
            logger.info(
                f"retry_failed_coverage_repairs: coverage NOT VERIFIED for "
                f"{ticker} [{account_mode}] ({outcome.reason}) — deferring to the "
                f"next cycle; attempt budget untouched "
                f"({s['attempts']}/{_COVERAGE_RETRY_MAX_ATTEMPTS} used)"
            )
            await log_audit_event(
                _COVERAGE_RETRY_DEFER_EVENT,
                f"{ticker}: coverage retry could NOT check coverage "
                f"({outcome.reason}) — not counted against the "
                f"{_COVERAGE_RETRY_MAX_ATTEMPTS}-attempt budget; retrying next cycle",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "account_mode": account_mode,
                    "attempts_used": s["attempts"],
                    "deferrals_today": s["deferrals"] + 1,
                    "broker_qty": broker_qty,
                    "status": outcome.status,
                    "reason": outcome.reason,
                }),
            )
            continue

        retried += 1
        # A pass that actually CHECKED: covered (nothing to do) or repaired (acted)
        # both mean the position is protected to target right now. Byte-equivalent
        # to the pre-#599 `msg is None or msg.startswith("🛡")` for every VERIFIED
        # case — the difference is only that a non-check no longer reaches here.
        healed = outcome.status in _COVERAGE_VERIFIED_OK
        if healed:
            resolved += 1
        await log_audit_event(
            _COVERAGE_RETRY_ATTEMPT_EVENT,
            f"{ticker}: coverage repair retry {attempt_no}/"
            f"{_COVERAGE_RETRY_MAX_ATTEMPTS} — "
            f"{'coverage now meets target' if healed else 'still not covered'}",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "account_mode": account_mode,
                "attempt": attempt_no,
                "broker_qty": broker_qty,
                "outcome": msg,
                "healed": healed,
                "status": outcome.status,
                "reason": outcome.reason,
            }),
        )

        if outcome.status == COVERAGE_REPAIRED:
            # Only the ACTED-ON case speaks; a silent no-op needs no Telegram
            # (a guard that always fires is not a guard). The original failure
            # already alerted, so the operator is owed the resolution.
            await send_telegram_message(
                f"{mode_prefix(account_mode)}🛡 *Coverage retry succeeded: {ticker}*\n"
                f"{msg}\n"
                f"_Attempt {attempt_no} after the earlier repair failure._"
            )
        elif not healed and attempt_no >= _COVERAGE_RETRY_MAX_ATTEMPTS:
            await send_telegram_message(
                f"{mode_prefix(account_mode)}🚨 *Coverage still broken: {ticker}*\n"
                f"{msg}\n"
                f"Retried {attempt_no} times this session — giving up until the "
                f"16:05 ET position sync. Check the broker."
            )

    return {"examined": examined, "retried": retried,
            "resolved": resolved, "exhausted": exhausted,
            "deferred": deferred}


async def _coverage_gap_already_alerted_today(trade_id: int, today) -> bool:
    """Has the `position_unprotected` Telegram already gone out for this trade
    TODAY (ET)?

    Same idiom as `_profit_trigger_already_announced` (#508, the 5-minute
    bombardment fix): the audit row IS the state, checked BEFORE this cycle's
    own row lands — hence `> 0`, matching that function's ordering (not
    `_breaker_already_alerted`'s post-write `> 1`). The audit row itself still
    lands EVERY cycle a gap persists (durable record, same as
    `stop_coverage_repaired` / `stop_coverage_repair_failed` above); only the
    Telegram is deduped.

    Scoped to the ET SESSION (today), not "ever": a gap that was open
    yesterday and is STILL open today is a fresh fact worth a fresh alert, not
    permanent silence — "per trade per session", not "per trade for life".

    Fails OPEN (returns False, i.e. alert) on any error — a duplicate message
    is a nuisance; a missed one on a live money path is not.

    ⚠ Guards `detail <> ''` BEFORE the `::jsonb` cast. `log_audit_event`'s `detail`
    defaults to `""` for callers that omit it, and Postgres does not guarantee
    AND-clause evaluation order — an empty-string row (of ANY event_type, not just
    this one) sailing through to the cast would raise `invalid input syntax for
    type json` and trip the fail-open path on every call, which would silently
    defeat the dedupe (advisor review, #527).
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM mi_audit_log "
                "WHERE event_type = 'position_unprotected' "
                "AND detail IS NOT NULL AND detail <> '' "
                "AND detail::jsonb ->> 'trade_id' = $1::text "
                "AND (created_at AT TIME ZONE 'America/New_York')::date = $2",
                str(trade_id), today,
            )
        return bool(n and int(n) > 0)
    except Exception as e:  # loud-ok: logged; failing open only risks a duplicate alert, never a missed one
        logger.warning(f"coverage-gap dedupe check failed (will alert): {e}")
        return False


async def check_position_coverage() -> dict:
    """#527 market-hours coverage DETECTOR — every ~15 min, 09:31-15:55 ET.

    Answers the only question that matters: does every LIVE open position have a
    resting stop RIGHT NOW? Reads BROKER TRUTH per position, never DB state —
    `stop_order_id` being non-NULL only means a stop was placed at SOME point, not
    that one is resting now (the 2026-08-04 PLTR hole: the coverage machinery that
    should have caught a dead DAY-tif leg simply hadn't been built yet — see PLAN.md
    #527 for the corrected timeline).

    ⚠ DETECTOR ONLY. Never places, cancels, or repairs an order — `_ensure_stop_coverage`
    (above) already owns repair, called from `sync_positions` and the partial-exit
    abort paths. This function must never become a second order-emission site; that
    would be a strategy/safeguard-shaped change reserved for the operator (THE LINE).

    Scope: `mi_live_trades` rows with status='filled' AND remaining_shares > 0 AND
    account_mode='live' — paper is deliberately excluded (no real dollars at risk).

    Coverage test: sum the qty of every live sell-stop on the ticker via
    `_live_sell_stops` — the SAME filter `_ensure_stop_coverage` uses, so "covered"
    can't drift between the detector and the repairer — and compare to
    `remaining_shares` with the SAME 0.5-share tolerance used throughout this module
    (`_ensure_stop_coverage`'s own decision tree, the 2523 qty-sync, the 2415 adopt).

    Fail OPEN AND LOUD on a broker-read error (F16 idiom: `raise_on_error=True`). A
    read failure is NEVER treated as "covered" — it writes `position_unprotected_check_failed`
    for that ticker and moves on; one ticker's broker error must not blind the scan to
    the rest of the book (and must not silently read as "all clear" for the ticker that
    failed either).

    Dedup (#508 bombardment idiom): the `position_unprotected` audit row lands EVERY
    cycle a gap persists (durable record); the Telegram fires once per trade per ET
    session via `_coverage_gap_already_alerted_today`. Silent on a normally-covered
    book — no row, no message, nothing (CLAUDE.md 2026-08-03: a guard that always
    fires is not a guard).

    DEFERS to an in-flight partial exit (advisor review, #527) — takes the SAME
    non-blocking `_trade_advisory_try_lock` `_ensure_stop_coverage` uses, for the
    SAME reason: `execute_partial_exit`'s cancel-then-new-stop sequence has a
    measured ~72ms (longer under retry) window with genuinely ZERO live stops
    while it re-protects itself mid-flight. Reading that window as a GAP would be
    a false positive on a position that IS actively being protected right now —
    it just isn't finished yet. The partial's own abort path re-protects via
    `_ensure_stop_coverage` if it fails, so skipping here is a defer, not a blind
    spot. Deferred tickers land in the `deferred` bucket, not `gaps`.

    Returns `{"examined", "covered", "gaps", "check_failed", "deferred"}` for
    callers/tests.
    """
    from agents.market_intelligence.collector import et_today

    today = et_today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        trades = await conn.fetch("""
            SELECT id, ticker, remaining_shares, account_mode
            FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0 AND account_mode = 'live'  -- mode-ok: real dollars only by design (see docstring)
        """)

    examined = 0
    covered = 0
    gaps: list[dict] = []
    check_failed: list[dict] = []
    deferred: list[str] = []

    for trade in trades:
        trade = dict(trade)
        examined += 1
        trade_id = trade["id"]
        ticker = trade["ticker"]
        account_mode = trade["account_mode"]
        target = float(trade["remaining_shares"])

        async with _trade_advisory_try_lock(trade_id) as have_lock:
            if not have_lock:
                deferred.append(ticker)
                continue

            try:
                open_orders = await alpaca.get_open_orders(
                    ticker, account_mode=account_mode, raise_on_error=True,
                )
            except Exception as e:
                logger.error(f"check_position_coverage: broker read failed for {ticker}: {e}")
                check_failed.append({"ticker": ticker, "trade_id": trade_id, "error": str(e)})
                await log_audit_event(
                    "position_unprotected_check_failed",
                    f"{ticker}: could not read broker open orders — coverage UNKNOWN, "
                    f"NOT claimed covered: {e}",
                    json.dumps({
                        "trade_id": trade_id, "ticker": ticker, "account_mode": account_mode,
                        "remaining_shares": target, "error": str(e),
                    }),
                )
                continue

            live_stops = _live_sell_stops(open_orders)
            live_qty = sum(float(o.get("qty") or 0) for o in live_stops)

            # #566: the OCO carve-out's sibling stop rides HELD at the broker and
            # `get_open_orders` HIDES a held leg (probe 2026-08-14, the exact
            # wrong-reading class that produced the ETON incident) — so summing
            # visible sell-stops alone would read the OCO third as NAKED and
            # false-alarm every cycle. The OCO PARENT (sell limit,
            # order_class=oco) IS visible, and an OPEN parent is broker-proof
            # the sibling stop still holds those shares: the pair lives and
            # dies as a unit (one cancel kills both; either side's fill cancels
            # the other), and the probe's extra sell was rejected 40310000
            # naming the parent. Count the parent's UNFILLED qty as stop
            # coverage. Plain (non-OCO) sell limits are deliberately NOT
            # counted — a bare limit above the market protects nothing on a
            # decline; that IS the defect this detector exists to catch.
            oco_stop_qty = sum(
                max(float(o.get("qty") or 0) - float(o.get("filled_qty") or 0), 0.0)
                for o in open_orders
                if str(o.get("order_class") or "").lower() == "oco"
                and "sell" in str(o.get("side") or "").lower()
                and _canonical_order_status(o.get("status")) in _STOP_CONFIRMED_LIVE_STATUSES
            )

            if live_qty + oco_stop_qty >= target - 0.5:
                covered += 1
                continue

            # Gap. Audit row lands every cycle; Telegram is deduped per trade per session.
            gaps.append({"ticker": ticker, "trade_id": trade_id,
                         "target": target, "live_qty": live_qty + oco_stop_qty})
            await log_audit_event(
                "position_unprotected",
                f"{ticker}: live stop qty {live_qty + oco_stop_qty:.0f} < {target:.0f} shares held — GAP",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker, "account_mode": account_mode,
                    "expected_qty": target, "found_qty": live_qty + oco_stop_qty,
                    "plain_stop_qty": live_qty, "oco_reserved_qty": oco_stop_qty,
                }),
            )
            if not await _coverage_gap_already_alerted_today(trade_id, today):
                try:
                    await send_telegram_message(
                        f"{mode_prefix(account_mode)}🚨 *Position unprotected: {ticker}*\n"
                        f"Expected a stop covering {target:.0f} sh, found "
                        f"{live_qty + oco_stop_qty:.0f} sh live.\n"
                        f"Detector only — no repair fired. Check the broker now."
                    )
                except Exception:  # loud-ok: the durable audit row above already landed; notify must never raise past this point
                    logger.warning(f"position_unprotected Telegram failed for {ticker}", exc_info=True)

    return {"examined": examined, "covered": covered, "gaps": gaps,
            "check_failed": check_failed, "deferred": deferred}


# ── #597: "position gone from Alpaca" resolution ─────────────────────────────
# Seconds a broker-confirmed exit fill is left to the websocket finaliser
# before sync_positions books it itself. WS commits land in seconds; the gap
# this bridges is only the poll-between-fill-and-finaliser race.
_SYNC_GONE_GRACE_S = 600


async def _resolve_position_gone(trade: dict, account_mode: str) -> str | None:
    """#597 — the DB holds a filled row with shares but Alpaca shows no position.

    SHAPE: record the exit the broker actually reports; refuse to close on
    anything less. A hybrid of the two candidate fixes, because each alone
    re-creates a known failure:

      * The pre-#597 branch closed the row blind (status='closed',
        remaining=0, no exit leg, no total_pnl update) — the trade booked
        whatever P&L it already had, usually $0 on a real loss, and
        mi_sell_discipline_records then fed that number to every exit-rule
        replay (MNDY 2026-05-11 class: total_pnl must move WITH exits).
      * "Always refuse and wait for the finaliser" leaves permanently wrong
        books when the WS event was genuinely LOST (stream restart, missed
        delivery) — the awaited finaliser never runs and the row lingers as a
        phantom open position.

    So, under the per-trade #151 advisory try-lock (defer if a finaliser or
    partial is mid-flight — never fight a live writer):

      1. GRACE — tracked stop confirmed FILLED at the broker but recently
         (< _SYNC_GONE_GRACE_S): do nothing; the WS finaliser is presumably
         in flight and owns the commit. This is the race in the bug report;
         deferring one sweep costs nothing.
      2. RECORD — stop fill older than the grace window: the finaliser missed
         it. Book the exit from BROKER TRUTH only (the stop order's own
         filled_avg_price / filled_qty — never a synthesised price) by
         DELEGATING the commit to _finalize_stop_fill_locked, the CANONICAL
         writer for exits/total_pnl/remaining_shares/status/closed_at
         (deploy gate audit_column_writes; T1.3 2026-05-18 removed the last
         duplicate close writer for exactly this reason). It keeps the
         exits+total_pnl-in-one-statement invariant, is idempotent on
         exits[].order_id (ONE guard — none duplicated here), nulls
         stop_order_id on a full close, and only closes when the fill
         exhausts remaining_shares. Both writers serialize on the same
         per-trade advisory lock, so a double leg cannot be written even if
         the WS event arrives later.
      3. REFUSE — anything else (no stop_order_id, order unreadable, order
         not filled: e.g. an OCO limit took the shares, or a manual
         liquidation): no real exit price can be established. Leave the row
         OPEN and LOUD (audit event + Telegram + a discrepancy line every
         sweep) for the operator. A wrong-but-confident P&L is the exact
         failure being fixed, and the 2026-05-27 mass-close guard already
         established open+loud as this file's safe direction for
         DB-says-shares / broker-says-none with an unconfirmed cause.

    CLOSE-TIMING CHANGE, explicit (THE LINE audit): the old branch closed the
    row on the same sweep unconditionally. Now: same-sweep close only when the
    broker confirms the fill (2); a fresh fill waits one sweep for its
    finaliser (1); an unconfirmable close stays open indefinitely (3). No
    order is placed, cancelled, or altered here — recording only — and the
    revert is deleting this helper and restoring the blind UPDATE at the call
    site.

    An orders-list/activities lookup (to auto-resolve case 3 too) was
    considered and deliberately NOT added: it widens the broker surface on the
    money path for a doubly-rare case, and open+loud is the correct terminal
    state for "we do not know the real price".

    Returns the discrepancy line for the sweep report, or None when there is
    nothing to say (a finaliser already committed the truth). The caller wraps
    this in its own degrade-loudly guard, so the sweep never breaks.
    """
    trade_id = int(trade["id"])
    ticker = trade["ticker"]
    prefix = f"[{account_mode}]"

    async with _trade_advisory_try_lock(trade_id) as acquired:
        if not acquired:
            # A finaliser/partial is writing this trade right now — it owns
            # the truth. Next sweep re-checks.
            return (f"{prefix} Position gone from Alpaca: {ticker} — trade lock "
                    f"held by an in-flight writer; deferring to it")

        # Re-read under the lock: the sweep's snapshot may predate a finaliser
        # commit. account_mode filter is load-bearing (dual-account #66).
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM mi_live_trades WHERE id = $1 AND account_mode = $2",
                trade_id, account_mode,
            )
        if not row or row["status"] == "closed" or (row["remaining_shares"] or 0) <= 0:
            return None  # finaliser won the race — books already true

        stop_order_id = row["stop_order_id"]
        order = None
        if stop_order_id:
            order = await alpaca.get_order(stop_order_id, account_mode=account_mode)
        order_status = (
            str(order.get("status", "")).split(".")[-1].lower() if order else ""
        )
        filled_price = order.get("filled_avg_price") if order else None
        filled_qty = float(order.get("filled_qty") or 0) if order else 0.0

        if order_status == "filled" and filled_price is not None and filled_qty > 0:
            # ── Case 1/2: broker-confirmed stop fill ─────────────────────────
            filled_at_raw = order.get("filled_at")
            fill_age_s = None
            if filled_at_raw:
                try:
                    filled_at = datetime.fromisoformat(str(filled_at_raw))
                    if filled_at.tzinfo is None:
                        filled_at = filled_at.replace(tzinfo=timezone.utc)
                    fill_age_s = (datetime.now(timezone.utc) - filled_at).total_seconds()
                except ValueError:
                    fill_age_s = None  # unparseable → record now (idempotent + locked)
            if fill_age_s is not None and fill_age_s < _SYNC_GONE_GRACE_S:
                return (f"{prefix} Position gone from Alpaca: {ticker} — stop "
                        f"filled {fill_age_s:.0f}s ago; leaving the row to the "
                        f"fill finaliser (grace {_SYNC_GONE_GRACE_S}s)")

            # Commit via the CANONICAL writer (deploy gate audit_column_writes:
            # _finalize_stop_fill_locked owns this close shape — adding a sixth
            # writer would undo the T1.3 2026-05-18 consolidation). It re-reads
            # the row itself, is idempotent on exits[].order_id (so no second
            # guard here), books pnl off the REAL fill, closes + nulls
            # stop_order_id only when the fill exhausts remaining_shares, and
            # emits its own audit row + "Closed" Telegram.
            #
            # LOCK CONTRACT: we HOLD the #151 per-trade try-lock, so we must
            # call the _locked variant, NOT the public finalize_stop_fill —
            # the public wrapper acquires pg_advisory_lock on a DIFFERENT
            # pooled connection, and advisory locks are per-connection, so it
            # would block forever against our own held lock (live-money hang).
            await _finalize_stop_fill_locked(
                trade_id, int(filled_qty), float(filled_price), stop_order_id,
            )
            entry_price = float(row["entry_price"] or 0)
            shares = int(filled_qty)
            pnl = (float(filled_price) - entry_price) * shares if entry_price else 0
            # Our own audit row records that SYNC (not the websocket) drove the
            # commit — the canonical writer's leg says source=websocket.
            await log_audit_event(
                "sync_gone_stop_fill_recorded",
                f"{ticker}: position gone from Alpaca; missed stop fill booked "
                f"via finalize_stop_fill from broker truth — {shares} sh "
                f"@${float(filled_price):.2f}, pnl ${pnl:+,.2f}",
                json.dumps({
                    "trade_id": trade_id, "ticker": ticker,
                    "account_mode": account_mode,
                    "stop_order_id": stop_order_id,
                    "filled_qty": shares,
                    "filled_avg_price": float(filled_price),
                    "db_remaining_before": float(row["remaining_shares"] or 0),
                    "pnl": float(pnl),
                    "fill_age_s": fill_age_s,
                }),
            )
            return (f"{prefix} Position gone from Alpaca: {ticker} — missed stop "
                    f"fill booked from broker truth ({shares} sh "
                    f"@${float(filled_price):.2f})")

        # ── Case 3: no broker-confirmed exit fill — leave open + loud ────────
        await log_audit_event(
            "sync_position_gone_unresolved",
            f"{ticker}: position gone from Alpaca but no broker-confirmed exit "
            f"fill (stop_order_id={stop_order_id or 'none'}, "
            f"status={order_status or 'unreadable'}) — row left OPEN; refusing "
            f"to book a P&L without a real fill price",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "account_mode": account_mode,
                "stop_order_id": stop_order_id,
                "stop_order_status": order_status or None,
                "db_remaining": float(row["remaining_shares"] or 0),
            }),
        )
        await send_telegram_message(
            f"{mode_prefix(account_mode)}🚨 *Books vs broker:* {ticker} position "
            f"is gone at Alpaca but DB trade {trade_id} still shows "
            f"{float(row['remaining_shares'] or 0):.0f} shares and no confirmed "
            f"exit fill was found (tracked stop: {order_status or 'unreadable'}).\n"
            f"Row left OPEN — needs manual reconcile."
        )
        return (f"{prefix} Position gone from Alpaca: {ticker} — UNRESOLVED, row "
                f"left open (no broker-confirmed exit fill)")


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
                # #597: do NOT blind-close — the old UPDATE here set
                # status='closed'/remaining=0 with no exit leg and no total_pnl,
                # booking a wrong (usually $0) P&L that then fed
                # mi_sell_discipline_records. Resolve from broker truth, defer
                # to an in-flight finaliser, or leave the row open + loud —
                # see _resolve_position_gone for the full rationale.
                try:
                    gone_msg = await _resolve_position_gone(dict(trade), account_mode)
                except Exception as e:
                    # Degrade loudly, never break the sweep (scheduled reconcile).
                    logger.error(
                        f"sync_positions [{account_mode}]: position-gone "
                        f"resolution failed for {ticker}: {e}", exc_info=True,
                    )
                    await log_audit_event(
                        "sync_gone_resolution_error",
                        f"{ticker}: position gone from Alpaca and resolution "
                        f"errored ({type(e).__name__}: {e}) — row left untouched",
                        json.dumps({
                            "trade_id": trade["id"], "ticker": ticker,
                            "account_mode": account_mode,
                        }),
                    )
                    gone_msg = (f"[{account_mode}] Position gone from Alpaca: "
                                f"{ticker} — resolution errored, row left open")
                if gone_msg:
                    discrepancies.append(gone_msg)

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
        # #600: the dead pointer's own broker order, kept for the re-protect
        # floor below (its stop_price is the last level the broker held). Reset
        # per trade so one row's read can never leak into the next.
        dead_stop_order: dict | None = None
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
            dead_stop_order = order
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
        # #600: never re-arm BELOW the last level the broker held. The dead
        # pointer's order (read above, no second broker call) carries the price
        # that WAS the protection; the DB stop_price can be stale-low (breakeven
        # withheld). NULL pointer → nothing to floor against → the DB anchor,
        # exactly as before — this path NEVER refuses to place.
        # #600 fork 2 (2026-09-04): `existing_stop_id` is commonly ALREADY NULL by
        # the time this runs (the WS cancel/expire beat this sync) — fall back to
        # the price `_handle_cancel_or_reject` preserved at that moment.
        stop = await _apply_reprotect_floor(
            trade["id"], ticker, float(stop), existing_stop_id, account_mode,
            site="sync_positions.orphan_remediation",
            broker_order=dead_stop_order, fetch=False,
            consult_dead_stop=True,
        )
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

    # #571 (2026-08-23): points at the shared constant instead of a second
    # hardcoded 0.20 literal (values verified identical; see
    # test_571_notional_cap_visibility.py's no-op pin). No #571 audit
    # telemetry here — this path has had NO live caller since #515 removed
    # `submit_9m_day2_trade`; it now serves ONLY the #482 shadow lane
    # (`shadow_orb_tracker.py`, no Alpaca submits), so a truncation here is
    # not a real-money event.
    max_position = equity * MAX_POSITION_PCT
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
# #605 (2026-08-29): minute bars are kept for the EP CANDIDATE population, not the alerted
# subset (persist_alert_day_paths' scan_log UNION arm). 8.0 = the acting 9% admission floor
# (ep_detector.MIN_GAP_PCT) minus one point of counterfactual headroom, so a modest floor cut
# can be replayed on stored bars — deliberately NOT the row-capture floor (5.0): bars at 571
# B/row are ~50x the cost of a scan_log row and the 5-8% band has no admission question open.
# Deliberately a LOCAL constant, not an ep_detector import (this module runs on the execution
# service); tests/test_605_decision_vector_capture.py pins it <= MIN_GAP_PCT so a floor change
# below 8% cannot silently re-open the coverage hole.
_PATH_CAPTURE_MIN_GAP = 8.0


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


async def _persist_minute_bars_for_ticker_day(
    pool, ticker: str, day: date, day_start: datetime, day_end: datetime,
    out: dict, gap_note: str, log_prefix: str,
) -> None:
    """Shared per-ticker body of `persist_alert_day_paths` and
    `persist_forward_alert_paths` (#574 extraction, 2026-08-31 — refactor only,
    no behaviour change; the two inline copies were verified byte-identical
    except for the two label strings now passed in). Coverage-checks
    `mi_intraday_bars` over [day_start, day_end], fetches + persists when thin,
    and mutates `out`'s already_covered / fetched / thin / errors counters
    exactly as both callers did inline. `gap_note` = the caller-specific
    parenthetical inside the `path_coverage_gap` audit summary; `log_prefix` =
    the caller-specific warning prefix. Fail-soft: one bad name must not kill
    the day's capture. A change to retry policy, the thin-log threshold or
    rate limiting now lands HERE once, for both jobs — the divergence the
    2026-08-18 simplify review flagged before it could happen.
    """
    try:
        async with pool.acquire() as conn:
            n_have = await conn.fetchval(
                """
                SELECT count(*) FROM mi_intraday_bars
                WHERE ticker = $1 AND bar_time >= $2 AND bar_time <= $3
                """,
                ticker, day_start, day_end,
            )
        if (n_have or 0) >= _PATH_MIN_DAY_BARS:
            out["already_covered"] += 1
            return
        bars = await alpaca.get_minute_bars_range(ticker, day_start, day_end)
        if bars:
            await alpaca.persist_intraday_bars(ticker, bars)
            out["fetched"] += 1
        if len(bars) < _PATH_MIN_DAY_BARS:
            out["thin"] += 1
            await log_audit_event(
                "path_coverage_gap",
                f"{ticker} {day}: {len(bars)}/390 bars ({gap_note})",
            )
    except Exception as e:  # one bad name must not kill the day's capture
        logger.warning(f"{log_prefix}: {ticker} {day} failed: {e}")
        out["errors"] += 1


async def persist_alert_day_paths(target_date=None) -> dict:
    """EOD: persist day-of minute bars for EVERY EP alert ticker-day, not just
    traded names (2026-08-15 capture audit item 3; telemetry only, THE LINE
    untouched — nothing here reads back into any detection/entry/exit path).

    WHY. `mi_intraday_bars` was only written by the #306 position recorder, so
    minute paths existed for names we took a position in — 43 of 98 alert
    ticker-days since 07-28 (44%). Skips, cancels and moderates — the plan's own
    outcome unit — had NO stored intraday path, so the HOLD test, 620 timing and
    the #559 reclaim split all leaned on a vendor refetch.

    POPULATION (the audit's, verbatim: "skips, cancels, moderates, rt catches
    included"): DISTINCT tickers from `mi_ep_alerts` on `target_date` (HIGH and
    MODERATE alike) UNION tickers from that day's `ep_rt_universe_catch` audit
    rows (detected-in-rt-never-admitted — joined to the review universe by the
    08-12 ruling). ~10-25 names x 390 bars/day ≈ 1-1.3 GB/yr all-in at the
    measured 571 B/row — priced into the 5y `mi_intraday_bars` retention.

    #605 (2026-08-29) — POPULATION-DRIVEN, not alert-driven: also every
    `mi_ep_scan_log` ticker whose day-max gap ≥ `_PATH_CAPTURE_MIN_GAP`. The
    08-29 backtest needed ORB bars for the CANDIDATE population and found 14%
    coverage — a 1.1M-row vendor backfill closed it once, but alert-gated
    ongoing capture re-opens the hole from the very next session. This arm
    keeps it closed. Priced: ~45-65 candidate names/day (46/day measured at
    the ≥9% floor over 97 sessions + the 8-9% headroom band), less the
    already-covered alert/traded overlap → ~+10 MB/day ≈ +2.5-3 GB/yr at the
    measured 571 B/row (vs ~1-1.3 GB/yr before) — accepted, sits inside the
    5y retention pricing above.

    Reuses the #306 pieces unchanged: `get_minute_bars_range` (Alpaca, same feed
    as the recorder so provenance stays uniform) + `persist_intraday_bars`
    (ON CONFLICT DO NOTHING — idempotent, so overlap with recorder-covered
    traded names is harmless). Names already holding >= `_PATH_MIN_DAY_BARS`
    bars are skipped without an API call. A thin day (halted/illiquid name)
    logs `path_coverage_gap`, same as the multi-day sweep — audit-only, never
    Telegram (a guard that always fires is not a guard).

    Runs in the EXECUTION service (the only one with Alpaca creds). NOT gated
    on LIVE_TRADING_ENABLED: alert capture must keep recording while trading
    is paused. Returns {"population": n, "fetched": n, "already_covered": n,
    "thin": n, "errors": n} for the job log.
    """
    day = target_date or datetime.now(_ET).date()
    out = {"population": 0, "fetched": 0, "already_covered": 0, "thin": 0, "errors": 0}
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ticker FROM mi_ep_alerts WHERE alert_date = $1
                UNION
                -- detail holds the JSON payload (log_audit_event's 3rd arg). The
                -- LIKE guard is load-bearing: ONE row with empty/non-JSON detail
                -- would abort the WHOLE query on the cast and zero the day's
                -- capture. ep_detector's reader guards per-row for the same reason.
                SELECT detail::json->>'ticker' AS ticker
                FROM mi_audit_log
                WHERE event_type = 'ep_rt_universe_catch'
                  AND (created_at AT TIME ZONE 'America/New_York')::date = $1
                  AND detail LIKE '{%'
                UNION
                -- 2026-08-16: consolidation (Family A) entry days. Audited that day:
                -- `mi_consolidation_entry_shadow` is well instrumented for DAILY eval
                -- (realized_r, fwd_mfe_r, rmv, regime) but **0 of 294 entry dates had
                -- minute bars**, so no stop-placement / intraday-shakeout / entry-timing
                -- study could run on it — the three analyses that produced the most
                -- useful EP results. The tactics transfer between the two setups, so the
                -- capture has to as well. Same additive path, no new job.
                SELECT ticker FROM mi_consolidation_entry_shadow WHERE entry_date = $1
                UNION
                -- #605 (2026-08-29): the CANDIDATE population — every scan_log ticker whose
                -- day-max gap cleared _PATH_CAPTURE_MIN_GAP, whether it alerted, got gate-
                -- killed, or fell outside the shortlist. Alert-gated capture is why the
                -- 08-29 backtest found 14% ORB coverage on its own population. Day-MAX gap
                -- (GROUP BY, not per-row) so an intraday fade below the floor can't drop a
                -- name that WAS a candidate at any tick.
                SELECT ticker FROM mi_ep_scan_log
                WHERE scan_date = $1
                GROUP BY ticker
                HAVING MAX(gap_pct) >= $2
                """,
                day, _PATH_CAPTURE_MIN_GAP,
            )
    except Exception as e:
        logger.error(f"alert-day path persist: population query failed: {e}")
        out["errors"] += 1
        return out

    tickers = sorted({r["ticker"] for r in rows if r["ticker"]})
    out["population"] = len(tickers)
    if not tickers:
        return out

    day_start = datetime.combine(day, datetime_time(9, 30), tzinfo=_ET)
    day_end = datetime.combine(day, datetime_time(16, 0), tzinfo=_ET)
    for ticker in tickers:
        await _persist_minute_bars_for_ticker_day(
            pool, ticker, day, day_start, day_end, out,
            gap_note="alert-day persist",
            log_prefix="alert-day path persist",
        )
    return out


# ── Forward alert-day path capture (2026-08-18, ep_profitability_program.md §0g) ──
#
# WHY. The conversion rehearsal (§0g) found the winners we already surface are
# real, but their run does not start on the EP day — peaks land 7-21 sessions
# out, and in 3 of 5 cases the base the run started from formed DAYS LATER and
# BELOW the EP-day low (HLIT bottomed session +4 at 11.97 vs an EP-day low of
# 12.68; NRIX bottomed +1, peaked +21). No stop width survives that; it is a
# TIMING problem, and delayed re-entry is the only surface aimed at it. We only
# persist minute bars for the ALERT DAY itself (`persist_alert_day_paths`
# above), so a delayed-entry read on a name we were actually stopped out of
# needs a fresh vendor pull every single time we want to look — exactly why the
# 620 trigger could not be tested and why any delayed-entry read today needs a
# 574-ticker-day backfill. This closes that gap GOING FORWARD (no backfill —
# see the module docstring above): capture only, so evidence accrues on its own
# from here on instead of waiting until we next have the capacity to look.
#
# THE LINE: capture only. No detection, no signal, no entry logic, nothing on
# this path is read by any grading/entry/sizing/ordering code — mirrors
# `persist_alert_day_paths`'s own contract exactly, just extended in TIME.

FORWARD_CAPTURE_WINDOW_SESSIONS = 25
"""Trading sessions AFTER the alert day (day 0) to keep persisting minute bars
for a stopped-out EP name. The rehearsal's 5 measured peaks landed at sessions
+7, +10, +11, +17 and +21 — 25 sessions (~5 weeks) covers that full observed
range with margin. Also matches the 25-session "decision-grade" maturity mark a
sibling running-read review elsewhere in this codebase uses for the same kind
of forward-looking window — reusing an established number, not inventing a new
one. A named constant, not a magic number, because it is the one knob that
bounds this job's growth (see `window_closed` below)."""


def trading_sessions_elapsed(alert_date: date, as_of: date) -> int:
    """Approximate count of trading SESSIONS from `alert_date` (session 0)
    through `as_of`, inclusive of `as_of`, skipping weekends only. Delegates to
    `collector.prev_trading_days` — the codebase's ONE weekends-only
    approximation — instead of re-implementing its loop (#574; the first
    version of this function hand-mirrored it, leaving two independent
    approximations of "a trading day" free to drift apart). Returns 0 when
    `as_of <= alert_date` (day 0 itself, or malformed input — never negative).
    Pure, no DB/network — the bound check `persist_forward_alert_paths` uses to
    decide whether a ticker-day is still inside its capture window.

    ⚠ Weekends-only is a DOCUMENTED approximation: a market holiday counts as
    an elapsed session here, exactly as it did before #574 and as it does at
    every `prev_trading_days` call site. Switching to the calendar-aware
    `get_market_status().is_trading_day` would CHANGE behaviour (each holiday
    inside a window would extend forward capture by one calendar day) — out of
    scope for the #574 refactor, recorded there as a separate finding.
    """
    if as_of <= alert_date:
        return 0
    from agents.market_intelligence.collector import prev_trading_days

    # The calendar-day span bounds the number of sessions in (alert_date,
    # as_of]. prev_trading_days walks BACK from (and excluding) its from_date,
    # so start one day past as_of to include as_of itself, then keep only the
    # sessions after alert_date.
    span = (as_of - alert_date).days
    return sum(
        1 for d in prev_trading_days(span, from_date=as_of + timedelta(days=1))
        if d > alert_date
    )


async def persist_forward_alert_paths(target_date=None) -> dict:
    """EOD: for an EP name that was alerted and then STOPPED OUT of a live
    position, keep persisting minute bars for `FORWARD_CAPTURE_WINDOW_SESSIONS`
    trading sessions AFTER the alert day — not just day 0 (`persist_alert_day_
    paths` already owns day 0; this job explicitly skips it, see
    `sessions_elapsed == 0` below).

    POPULATION: (ticker, alert_date) pairs from `mi_exit_path_shadow` where the
    LIVE trade's exit was a stop (`is_exit_day=true AND exit_reason='stop_hit'`)
    — the exact class §0g's finding is about ("names we surfaced, entered, and
    were stopped out of"). Deliberately scoped to this population, not every EP
    alert: the broader population (~17.5 alert ticker-days/trading day, per the
    2026-08-18 cost read) would run ~25x the storage/API cost of the stopped-out
    class alone (~0.63 stop-outs/trading day) for evidence the §0g finding did
    not ask for — narrow now, widen later if the narrow read earns it.

    Runs once per weekday; each run fetches ONLY *today's* bars for every
    ticker-day still inside its window — the window fills in incrementally
    across subsequent daily runs, exactly like `persist_alert_day_paths` fills
    in day 0. `window_closed` counts ticker-days whose window has already
    elapsed as of `target_date` (skipped without an API call) — the mechanism
    that BOUNDS this job so it does not grow forever. ⚠ A trade only ENTERS
    this population on its exit day (the population query reads `is_exit_day`),
    so a multi-day hold that stops out on session 4 gets sessions 5+ captured
    forward from here but NOT sessions 1-3 (already gone by the time this job
    first sees the trade) — fine for §0g's question (the base forms AFTER the
    stop), a gap for anyone who later wants the full pre-stop path too.

    Idempotent (`alpaca.persist_intraday_bars`'s `ON CONFLICT DO NOTHING`) and
    fail-soft (one bad ticker/day is logged and skipped, never raised) — same
    contract as `persist_alert_day_paths`, same fetch/write path reused
    unchanged (`alpaca.get_minute_bars_range` + `alpaca.persist_intraday_bars`;
    no second capture path built).

    Runs in the EXECUTION service (Alpaca data creds). NOT gated on
    LIVE_TRADING_ENABLED — telemetry capture must keep recording while trading
    is paused.

    Returns {"population": n, "fetched": n, "already_covered": n, "thin": n,
    "errors": n, "window_closed": n} for the job log.
    """
    day = target_date or datetime.now(_ET).date()
    out = {"population": 0, "fetched": 0, "already_covered": 0, "thin": 0,
           "errors": 0, "window_closed": 0}
    pool = await get_pool()
    # Generous calendar-day floor (2x the session window covers weekends +
    # margin for holidays) — the precise per-row session check below is what
    # actually enforces the bound; this floor only keeps the population query
    # from scanning the entire table's history every run.
    lookback_floor = day - timedelta(days=FORWARD_CAPTURE_WINDOW_SESSIONS * 2)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ticker, alert_date FROM mi_exit_path_shadow
                WHERE is_exit_day = true AND exit_reason = 'stop_hit'
                  AND alert_date >= $1 AND alert_date <= $2
                """,
                lookback_floor, day,
            )
    except Exception as e:
        logger.error(f"forward alert path persist: population query failed: {e}")
        out["errors"] += 1
        return out

    candidates = sorted(
        {(r["ticker"], r["alert_date"]) for r in rows if r["ticker"] and r["alert_date"]}
    )
    day_start = datetime.combine(day, datetime_time(9, 30), tzinfo=_ET)
    day_end = datetime.combine(day, datetime_time(16, 0), tzinfo=_ET)
    for ticker, alert_date in candidates:
        sessions_elapsed = trading_sessions_elapsed(alert_date, day)
        if sessions_elapsed == 0:
            continue  # day 0 is persist_alert_day_paths' job, not this one's
        if sessions_elapsed > FORWARD_CAPTURE_WINDOW_SESSIONS:
            out["window_closed"] += 1
            continue
        out["population"] += 1
        await _persist_minute_bars_for_ticker_day(
            pool, ticker, day, day_start, day_end, out,
            gap_note=(f"forward alert-day persist, session {sessions_elapsed} "
                      f"of {FORWARD_CAPTURE_WINDOW_SESSIONS}"),
            log_prefix="forward alert-day path persist",
        )
    return out


# ── Profit-target R frame (2026-08-16, operator-signed 2R-stop change) ──────
# Signal types whose R frame is DEFINED by the ORB (R = entry − orb_low),
# independent of where the protective stop sits. MAGNA53's stop moved to
# entry − 2R at half size on 2026-08-16, but its +2R partial still comes off at
# the ORIGINAL entry + 2·(entry − orb_low) price — framing the target off the
# placed stop would silently drift it to +4R, which was never tested or
# approved. Strategies NOT listed here (9M Day 2: stop = prior day low) keep
# entry − stop, which IS their R — listing them would rewrite THEIR target
# (the #490 latent-defect class: one strategy's rule leaking into shared code).
_ORB_R_FRAME_SIGNAL_TYPES = frozenset({"magna53"})


def profit_target_r_per_share(
    signal_type: str | None,
    entry: float | None,
    stop: float | None,
    orb_low: float | None,
) -> float | None:
    """Per-share R used to price the +N·R profit target. Returns None when no
    valid frame exists — the caller must SKIP that trade, never fabricate a
    number (the ADR 0014 no-valid-R-frame rule).

    ORB-framed strategies (`_ORB_R_FRAME_SIGNAL_TYPES`): R = entry − orb_low.
    Everything else: R = entry − stop (their stop distance IS their R).
    """
    if entry is None or entry <= 0:
        return None
    if (signal_type or "") in _ORB_R_FRAME_SIGNAL_TYPES:
        if orb_low is None or orb_low >= entry:
            return None
        return entry - orb_low
    if stop is None or stop >= entry:
        return None
    return entry - stop


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
            SELECT id, ticker, entry_price, hard_stop, stop_price, orb_low,
                   signal_type, remaining_shares,
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
        # 🔴 2026-08-16 (operator-signed 2R-stop change): the target's R frame is
        # the ORB-based R (entry − orb_low) for MAGNA53 — NOT the placed stop
        # distance, which is now 2R wide. `entry + N·(entry − stop)` on a 2R stop
        # would silently move the target to +4R. profit_target_r_per_share owns
        # the frame per strategy; None = unframeable → skip loudly, never guess.
        r_per_share = profit_target_r_per_share(
            t["signal_type"], entry, stop, _num(t["orb_low"]))
        if r_per_share is None:
            logger.warning(
                f"profit trigger: {t['ticker']} trade {t['id']} has no valid R "
                f"frame (signal_type={t['signal_type']} entry={entry} "
                f"orb_low={t['orb_low']} stop={stop}) — trigger skipped"
            )
            continue
        target = entry + PROFIT_TRIGGER_R * r_per_share
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
        # #548 final design: in resting mode the 1/3 is sold with a GTC limit AT
        # the target (fills at the price, not at whatever the tape shows when the
        # poll notices — the FIGS 0.87R gap). The toggle is read here only for the
        # announcement text; execute_partial_exit re-reads it as the gate.
        _resting = await _profit_take_resting_limit_enabled(t["account_mode"])
        # Operator 2026-08-18 ("these 3 msgs can be merged into one?"): AMLX got
        # three separate Telegrams for one partial exit — this trigger notice,
        # execute_partial_exit's own "Profit-take resting" line, and the WS
        # safety-net "Stop replaced" confirming the remaining shares' breakeven
        # stop. Rather than send this trigger message here and race a SECOND
        # message out of execute_partial_exit, hand the trigger facts DOWN as
        # `trigger` — execute_partial_exit's Step 3 folds them into its own
        # (later, richer) message and flips `trigger["delivered"]` right before
        # it sends. AUTHOR = execute_partial_exit's Step 3 (it alone knows the
        # order actually went out); this call site only SPEAKS on its own when
        # `delivered` is still False afterward — paused/circuit-broken/aborted
        # calls that never reach Step 3, or the announce-gate below is already
        # satisfied. Never silently drops the trigger fact.
        #
        # ⚠ ANNOUNCE ONCE PER TRADE, not once per 5-minute cycle (2026-08-04). Both selection
        # conditions are sticky while the partial keeps failing, so this re-fired every pass
        # for hours — half of the "bombarded with these msg non stop" pair. See
        # `_profit_trigger_already_announced`. The audit rows below still fire every cycle.
        _trigger_ctx: dict | None = None
        try:
            if not await _profit_trigger_already_announced(t["id"]):
                _trigger_ctx = {
                    "delivered": False,
                    "high": float(hi), "target": float(target), "entry": float(entry),
                    "r_multiple": PROFIT_TRIGGER_R,
                }
        except Exception:  # loud-ok: notification must never abort the money action below
            logger.warning(f"profit-trigger context build failed for {t['ticker']}", exc_info=True)
            _trigger_ctx = None
        ok = await execute_partial_exit(
            t["id"], shares, limit_price=round(target, 2), trigger=_trigger_ctx,
        )
        if _trigger_ctx is not None and not _trigger_ctx.get("delivered"):
            # Speak when in doubt: execute_partial_exit never reached the point
            # where it could carry this fact (paused / circuit-breaker-open /
            # an early abort before Step 3) — tell the operator the target was
            # hit on its own, same text as before this merge shipped.
            try:
                _action_line = (
                    f"Resting a limit to sell {shares} of "
                    f"{int(float(t['remaining_shares']))} sh at ${target:.2f}; "
                    f"stop moves to breakeven."
                    if _resting else
                    f"Taking {shares} of {int(float(t['remaining_shares']))} sh, "
                    f"stop moves to breakeven."
                )
                await send_telegram_message(
                    f"{mode_prefix(t['account_mode'])}\U0001F4B0 *Profit target hit: {t['ticker']}*\n"
                    f"traded ${float(hi):.2f} >= ${target:.2f} "
                    f"({PROFIT_TRIGGER_R:g}R above ${entry:.2f})\n"
                    f"{_action_line}"
                )
            except Exception:  # loud-ok: notification must never abort the money action below
                logger.warning(f"profit-trigger notify failed for {t['ticker']}", exc_info=True)
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
