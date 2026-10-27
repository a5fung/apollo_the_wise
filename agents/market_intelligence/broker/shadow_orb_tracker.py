"""Shadow ORB tracker — telemetry-only 5-minute ORB simulation, plus the FIRST-HOUR lane.

Records would-be 5-min ORB entries and outcomes alongside the live 1-min
trades so we can answer: "is there a class of EPs better entered at 5m
than at 1m?" Same alert universe, same gates, same exit rules — only the
ORB bar size differs (apples-to-apples).

THE FIRST-HOUR LANE (#482 add-on, operator 2026-10-26 "Ok move to Tuesday"): a SECOND bar size
(60) in the same table, one row per 5-minute row — the full alert population, which is what the
book-arm recorder (`book_geometry_arms.py`, SELECTION EFFECT) could not see because it walks only
the fills we took. The entry is the book's: a stop-limit buy at the first 60-minute bar's high
(09:30-10:29 ET) submitted 10:30, day order to the session close (13:00 on a half day), with the
broker's limit buffer (`book_geometry_arms.entry_walk`); the stop is the live bracket rule restated
on that bar (2 × bar low − bar high, the formula `prepare_orb_order` uses); the exit ladder is the
same daily step the 5-minute rows walk. NO admission gate (the `stop_too_wide` ATR gate would refuse
most hour bars — the book-arm rule), NO account read: the row is sized ONE unit (`entry_shares` 1,
`risk_dollars` = entry − stop) so every reader's `total_pnl / risk_dollars` is R by construction.
The walk itself is `broker/hour_bar_walk.py`, the ONE copy the book-arm recorder also runs. The
day-0 gap rule: a walk whose post-10:30 minutes have holes and never crossed the hour high is
decided by the day's daily high (strictly below the hour high proves the no-entry); otherwise, on
a thin first hour (< 50 of 60 minutes), and on a LATE fill whose exit history cannot be walked, the
row is deferred and retried nightly, written `gate_blocked` with the gap named once the alert is
HOUR_GAP_RETRY_SESSIONS old. NOTHING is written for a candidate until every read it needs is in
hand (review F1: an `open` row inserted before its catch-up would be quarantined, not retried).

No Alpaca submits. No new Telegram alerts. Pure telemetry surfaced via
`/audit shadow_orb` and the Sunday weekly review (both 5-minute only; the hour lane is read by SQL —
docs/setups/magna53_ep.md 2026-10-27).

Cron entry points (all three run in apollo-execution — EXECUTION_OWNED_JOB_IDS):
    run_shadow_pass(today)         — 10:00 ET, ORB window closed (5-minute entries)
    run_shadow_hour_pass(today)    — 16:50 ET, inside the exit job, before the step (hour entries)
    update_shadow_positions(today) — 16:50 ET, daily exit step on BOTH bar sizes
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.entry_pipeline import check_fade_guard
from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step
from agents.market_intelligence.broker.hour_bar_walk import (
    NO_ENTRY_HOUR,
    classify_hour_entry,
    session_close_et,
)
from agents.market_intelligence.broker.order_manager import (
    prepare_prior_day_low_orb_order,
    prepare_orb_order,
)
from agents.market_intelligence.broker.skip_reasons import (
    INFRA_NO_BAR,
)
from agents.market_intelligence.collector import get_index_history, prev_trading_days
from agents.market_intelligence.db import (
    SHADOW_HOUR_LANE_CANDIDATES_SQL,
    get_all_9m_sugar_babies,
    get_open_shadow_trades,
    get_pool,
    insert_shadow_trade,
    update_shadow_trade,
)

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
BAR_SIZE_MINUTES = 5
ORB_WINDOW_MINUTES = 30  # 9:30 → 10:00 ET
TRIGGER_END_MINUTE = 30  # exclusive — last 1-min bar is 9:59
SHADOW_CONCURRENCY = 5

# ── the first-hour lane (#482 add-on) ──
HOUR_BAR_SIZE_MINUTES = 60
HOUR_LANE_LOOKBACK_DAYS = 14     # calendar days of 5-minute rows the nightly pass looks back over —
                                 # twice HOUR_GAP_RETRY_SESSIONS, so a gap row is still in the
                                 # population when it becomes recordable even after a missed night
HOUR_GAP_RETRY_SESSIONS = 5      # a data gap is retried nightly this many sessions, then recorded
HOUR_LANE_UNIT_SHARES = 1.0      # one unit: total_pnl / risk_dollars reads as R


# ── Entry pass (10:00 ET) ───────────────────────────────────────────────────


async def run_shadow_pass(today: date) -> dict[str, int]:
    """Compute 5-min ORB + apply gates for every live ORB candidate.

    Sources:
      * MAGNA53 HIGH alerts created today before 09:31 ET (alert-race
        correctness — HIGHs at 09:45–09:59 ET are tagged
        WINDOW_OUT_OF_ORB by live; including them flatters 5m).
      * 9M sugar babies confirmed yesterday (all statuses — by 10:00 ET
        the live 9:31 job has already flipped pending→traded/skipped, so
        filtering for 'pending' would yield the inverse of live's universe).

    Writes one mi_orb_shadow_trades row per candidate with status
    open / no_entry / gate_blocked / infra:no_bar.
    """
    from agents.market_intelligence.db import log_audit_event
    from agents.market_intelligence.strategies.registry import should_run
    if not await should_run("shadow_orb_5m"):
        await log_audit_event(
            "strategy_disabled_skip",
            "shadow_orb_5m disabled — skipping shadow pass",
        )
        return {"open": 0, "no_entry": 0, "gate_blocked": 0,
                "infra:no_bar": 0, "duplicate": 0, "error": 0,
                "strategy_disabled": 1}

    magna_alerts = await _fetch_magna53_high_pre_open(today)
    yesterday = prev_trading_days(1, from_date=today)[0]
    sugar_babies = await get_all_9m_sugar_babies(yesterday)

    logger.info(
        f"Shadow ORB pass: {len(magna_alerts)} MAGNA53 HIGH + "
        f"{len(sugar_babies)} 9M Day-2 candidates"
    )

    regime_record = await _fetch_latest_regime(today)
    sem = asyncio.Semaphore(SHADOW_CONCURRENCY)
    counts = {"open": 0, "no_entry": 0, "gate_blocked": 0, "infra:no_bar": 0,
              "duplicate": 0, "error": 0}

    async def _one(builder_kind: str, alert_ctx: dict) -> None:
        async with sem:
            try:
                status = await _process_candidate(
                    builder_kind, alert_ctx, today, regime_record,
                )
                counts[status] = counts.get(status, 0) + 1
            except Exception:
                logger.exception(
                    f"Shadow ORB {alert_ctx.get('ticker')}: per-candidate crash"
                )
                counts["error"] += 1

    tasks = [_one("magna53", a) for a in magna_alerts]
    tasks += [_one("9m_day2", s) for s in sugar_babies]
    await asyncio.gather(*tasks)

    logger.info(f"Shadow ORB pass complete: {counts}")
    return counts


async def _process_candidate(
    builder_kind: str,
    alert_ctx: dict,
    today: date,
    regime_record: dict | None,
) -> str:
    ticker = alert_ctx["ticker"]

    bars = await alpaca.get_minute_bars_window(
        ticker, today, 0, ORB_WINDOW_MINUTES,
    )
    if len(bars) < BAR_SIZE_MINUTES:
        await _insert_row(
            ticker, today, builder_kind, alert_ctx,
            status="gate_blocked",
            skip_reason=f"{INFRA_NO_BAR}: only {len(bars)} 1-min bars in 9:30-10:00",
        )
        return "infra:no_bar"

    orb_high = max(b["high"] for b in bars[:BAR_SIZE_MINUTES])
    orb_low = min(b["low"] for b in bars[:BAR_SIZE_MINUTES])

    trigger_minute_et: time | None = None
    for b in bars[BAR_SIZE_MINUTES:]:
        if b["high"] >= orb_high:
            ts = b["timestamp"]
            if ts is not None:
                trigger_minute_et = ts.astimezone(ET).time().replace(microsecond=0)
            break

    if trigger_minute_et is None:
        await _insert_row(
            ticker, today, builder_kind, alert_ctx,
            status="no_entry",
            orb_high=orb_high, orb_low=orb_low,
        )
        return "no_entry"

    synthetic_orb_bar = {
        "high": orb_high, "low": orb_low,
        "open": orb_low, "close": orb_high, "volume": 0,
    }

    fade_ratio = None if builder_kind == "magna53" else 0.25
    fade_ok, fade_reason = await check_fade_guard(
        ticker, synthetic_orb_bar, fade_ratio,
    )
    if not fade_ok:
        await _insert_row(
            ticker, today, builder_kind, alert_ctx,
            status="gate_blocked", skip_reason=fade_reason,
            orb_high=orb_high, orb_low=orb_low,
            trigger_minute_et=trigger_minute_et,
        )
        return "gate_blocked"

    if builder_kind == "magna53":
        from agents.market_intelligence.backtester.filters import compute_atr_14
        atr_14, _ = await compute_atr_14(ticker, today)
        spec, reject = await prepare_orb_order(
            alert_ctx, synthetic_orb_bar, atr_14 or 0, regime_record,
            # #571: this lane places no real order (module docstring: "No
            # Alpaca submits") — suppress the 20%-cap truncation audit event
            # so shadow candidates don't pollute a signal meant to measure
            # only real truncated trades.
            emit_cap_telemetry=False,
        )
    else:
        spec, reject = await prepare_prior_day_low_orb_order(
            alert_ctx, synthetic_orb_bar, regime_record,
        )

    if spec is None:
        await _insert_row(
            ticker, today, builder_kind, alert_ctx,
            status="gate_blocked", skip_reason=reject,
            orb_high=orb_high, orb_low=orb_low,
            trigger_minute_et=trigger_minute_et,
        )
        return "gate_blocked"

    inserted = await _insert_row(
        ticker, today, builder_kind, alert_ctx,
        status="open",
        orb_high=orb_high, orb_low=orb_low,
        trigger_minute_et=trigger_minute_et,
        entry_price=spec["entry_price"],
        stop_price=spec["stop_loss_price"],
        hard_stop=spec["stop_loss_price"],
        risk_dollars=spec.get("risk_dollars"),
        entry_shares=spec["shares"],
        atr_14=spec.get("atr_14"),
    )
    return "open" if inserted else "duplicate"


async def _insert_row(
    ticker: str,
    today: date,
    builder_kind: str,
    alert_ctx: dict,
    *,
    status: str,
    skip_reason: str | None = None,
    orb_high: float | None = None,
    orb_low: float | None = None,
    trigger_minute_et: time | None = None,
    entry_price: float | None = None,
    stop_price: float | None = None,
    hard_stop: float | None = None,
    risk_dollars: float | None = None,
    entry_shares: float | None = None,
    atr_14: float | None = None,
) -> bool:
    signal_type = "magna53" if builder_kind == "magna53" else "9m_day2"
    shape_tag = alert_ctx.get("shape_tag") if signal_type == "9m_day2" else None
    score_tier = alert_ctx.get("score_tier") if signal_type == "magna53" else None

    row = {
        "ticker": ticker,
        "alert_date": today,
        "bar_size_minutes": BAR_SIZE_MINUTES,
        "signal_type": signal_type,
        "shape_tag": shape_tag,
        "score_tier": score_tier,
        "orb_high": orb_high,
        "orb_low": orb_low,
        "atr_14": atr_14,
        "trigger_minute_et": trigger_minute_et,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "hard_stop": hard_stop,
        "risk_dollars": risk_dollars,
        "entry_shares": entry_shares,
        "status": status,
        "skip_reason": skip_reason,
        "remaining_shares": entry_shares if status == "open" else 0,
    }
    trade_id = await insert_shadow_trade(row)
    return trade_id is not None


# ── First-hour entry pass (16:50 ET, before the exit step) — #482 add-on ───


async def run_shadow_hour_pass(today: date) -> dict[str, int]:
    """Record the first-hour entry for every 5-minute shadow row that has no 60-minute sibling yet
    (alert dates within HOUR_LANE_LOOKBACK_DAYS of `today`). The population is DERIVED from the
    5-minute rows, so the two lanes cover exactly the same alerts by construction.

    Statuses written: open / no_entry / gate_blocked (a non-positive 2R stop, or a data gap that
    stayed open HOUR_GAP_RETRY_SESSIONS sessions). A gap younger than that writes nothing — the row
    is picked up again tomorrow. Same kill switch as the 5-minute lane (`shadow_orb_5m`).
    """
    from agents.market_intelligence.db import log_audit_event
    from agents.market_intelligence.strategies.registry import should_run
    counts = {"open": 0, "no_entry": 0, "gate_blocked": 0, "deferred": 0,
              "duplicate": 0, "error": 0}
    if not await should_run("shadow_orb_5m"):
        await log_audit_event(
            "strategy_disabled_skip",
            "shadow_orb_5m disabled — skipping the first-hour shadow pass",
        )
        return {**counts, "strategy_disabled": 1}

    candidates = await _fetch_hour_lane_candidates(today)
    logger.info(f"Shadow first-hour pass: {len(candidates)} 5-minute row(s) without an hour row")
    sem = asyncio.Semaphore(SHADOW_CONCURRENCY)

    async def _one(row: dict) -> None:
        async with sem:
            try:
                status = await _process_hour_candidate(row, today)
                counts[status] = counts.get(status, 0) + 1
            except Exception:
                logger.exception(
                    f"Shadow first-hour {row.get('ticker')} {row.get('alert_date')}: per-candidate crash"
                )
                counts["error"] += 1

    await asyncio.gather(*[_one(r) for r in candidates])
    logger.info(f"Shadow first-hour pass complete: {counts}")
    await log_audit_event(
        "shadow_orb_hour_pass",
        f"{len(candidates)} candidate(s): {counts['open']} open, {counts['no_entry']} no-entry, "
        f"{counts['gate_blocked']} gate-blocked, {counts['deferred']} deferred (gap retried), "
        f"{counts['error']} error(s)",
    )
    return counts


def _alpaca_bars_to_walk_shape(bars: list[dict]) -> list[dict]:
    """`alpaca.get_minute_bars_window` rows → the {m,o,h,l,c} shape the book-arm walks read."""
    out = []
    for b in bars:
        ts = b.get("timestamp")
        if ts is None:
            continue
        out.append({"m": ts.astimezone(ET), "o": b["open"], "h": b["high"], "l": b["low"], "c": b["close"]})
    return out


def _minutes_from_open(t: time) -> int:
    return (t.hour * 60 + t.minute) - (9 * 60 + 30)


def _sessions_old(alert_date: date, today: date) -> int:
    """Weekday sessions strictly after `alert_date` through `today` (the file's holiday-free rule)."""
    return _count_weekday_sessions(alert_date, today)


async def _process_hour_candidate(row: dict, today: date) -> str:
    """One 5-minute row → its 60-minute sibling. Returns the status written, 'deferred' when nothing
    was written (a data gap still inside its retry window), 'duplicate' on a UNIQUE conflict.

    Every read happens BEFORE the first write (review F1): the day's minutes, the day-0 daily high
    when the walk saw holes, and — for a LATE fill — the exit history of the sessions it missed. A
    candidate whose reads are incomplete is deferred as a whole; an `open` row is only ever inserted
    together with the catch-up that makes it steppable."""
    ticker = row["ticker"]
    alert_date = row["alert_date"]
    close_et = session_close_et(alert_date)
    raw = await alpaca.get_minute_bars_window(ticker, alert_date, 0, _minutes_from_open(close_et))
    bars = _alpaca_bars_to_walk_shape(raw)
    stale = _sessions_old(alert_date, today) >= HOUR_GAP_RETRY_SESSIONS

    verdict = classify_hour_entry(bars, close_et) if bars else {"kind": "pending", "reason": "no_minute_bars"}
    if verdict["kind"] == "needs_daily_high":
        daily = await get_index_history(ticker, alert_date.isoformat(), alert_date.isoformat())
        d0_high = float(daily[0]["h"]) if daily and daily[0].get("h") is not None else None
        if d0_high is None:
            verdict = {"kind": "pending", "high": verdict["high"], "low": verdict["low"],
                       "reason": f"{verdict['walk_reason']}:no_day0_daily_bar"}
        else:
            verdict = classify_hour_entry(bars, close_et, d0_high)

    hi, lo = verdict.get("high"), verdict.get("low")
    trigger: time | None = None
    entry = stop = None
    catch_up: dict[str, Any] | None = None
    if verdict["kind"] == "filled":
        # the live bracket rule restated on the hour bar
        trigger = verdict["minute"].astimezone(ET).time().replace(microsecond=0)
        entry = float(verdict["px"])
        stop = 2 * lo - hi
        if stop <= 0:
            inserted = await _insert_hour_row(
                row, status="gate_blocked",
                skip_reason=f"first_hour_2r_stop_nonpositive: 2R stop ${stop:.2f} <= $0",
                orb_high=hi, orb_low=lo, trigger_minute_et=trigger,
            )
            return "gate_blocked" if inserted else "duplicate"
        # A LATE fill (the lookback backfill, or a gap row resolved on a later night) is walked over
        # the sessions between the alert and yesterday BEFORE it is written — see _walk_missed_sessions.
        catch_up = await _walk_missed_sessions(ticker, alert_date, entry, stop, today)
        if catch_up is not None and "_unavailable" in catch_up:
            verdict = {"kind": "pending", "high": hi, "low": lo, "reason": catch_up["_unavailable"]}
            catch_up = None

    if verdict["kind"] == "pending":
        if not stale:
            return "deferred"
        inserted = await _insert_hour_row(
            row, status="gate_blocked",
            skip_reason=f"{INFRA_NO_BAR}: {verdict['reason']} (unresolved after {HOUR_GAP_RETRY_SESSIONS} sessions)",
            orb_high=hi, orb_low=lo, trigger_minute_et=trigger,
        )
        return "gate_blocked" if inserted else "duplicate"

    if verdict["kind"] == "no_entry":
        reason = verdict["reason"]
        inserted = await _insert_hour_row(
            row, status="no_entry",
            skip_reason=None if reason == NO_ENTRY_HOUR else reason,
            orb_high=hi, orb_low=lo,
        )
        return "no_entry" if inserted else "duplicate"

    trade_id = await _insert_hour_row(
        row, status="open",
        orb_high=hi, orb_low=lo,
        trigger_minute_et=trigger,
        entry_price=entry, stop_price=stop, hard_stop=stop,
        risk_dollars=HOUR_LANE_UNIT_SHARES * (entry - stop),
        entry_shares=HOUR_LANE_UNIT_SHARES,
        atr_14=row.get("atr_14"),
    )
    if trade_id is None:
        return "duplicate"
    if catch_up:
        await update_shadow_trade(trade_id, catch_up)
    return "open"


async def _walk_missed_sessions(ticker: str, alert_date: date, entry: float, stop: float,
                                today: date) -> dict[str, Any] | None:
    """The catch-up for a LATE fill, computed BEFORE anything is written: the daily ladder walked
    over the real sessions in (alert_date, yesterday] — the live path's own driver (`iter_exit_ladder`,
    `integer_partial_shares=False`, no prior closes, no opt-ins), exactly as `replay_stale_open_row`
    drives it. Tonight's own session is left to the exit step that runs right after this pass.

    Returns None when there is nothing to catch up (today is the first session after the alert, or
    the only sessions between were holidays the stale guard tolerates); the `update_shadow_trade`
    fields when sessions were walked; or `{"_unavailable": reason}` when the history is missing or
    short enough that the exit step's own guard (`detect_stale_for_step`) would quarantine the row —
    the caller then DEFERS the candidate (retried nightly, recorded `gate_blocked` once stale) instead
    of inserting an `open` row that could never be stepped (review F1). The guard is the same
    predicate the exit step applies, so a row this returns fields for is one the step will walk."""
    from agents.market_intelligence.broker.exit_logic import iter_exit_ladder, seed_exit_state
    if _count_weekday_sessions(alert_date, today) < 2:
        return None                       # today is the first session after the alert: nothing missed
    through = today - timedelta(days=1)
    bars = await get_index_history(ticker, (alert_date + timedelta(days=1)).isoformat(), through.isoformat())
    day_bars: list[tuple[date, dict]] = []
    for b in bars or []:
        ts = b.get("t")
        if ts is None:
            continue
        day = datetime.fromtimestamp(ts / 1000, tz=ET).date()
        if alert_date < day <= through:
            day_bars.append((day, b))
    day_bars.sort(key=lambda x: x[0])
    fields: dict[str, Any] | None = None
    if day_bars:
        state = seed_exit_state(alert_date=alert_date, entry_price=entry, hard_stop=stop,
                                remaining_shares=HOUR_LANE_UNIT_SHARES)
        last_step = None
        for _i, _day, step in iter_exit_ladder(state, day_bars, integer_partial_shares=False):
            last_step = step
        if last_step is not None:
            fields = {
                "running_closes": state["running_closes"],
                "exits": state["exits"],
                "remaining_shares": state["remaining_shares"],
                "partial_taken": state["partial_taken"],
                "breakeven_active": state["breakeven_active"],
                "total_pnl": sum(e.get("pnl", 0) for e in state["exits"]),
                "hold_days": last_step.hold_days,
                "stop_price": last_step.effective_stop,
            }
            if last_step.closed:
                fields["status"] = "closed"
                fields["closed_at"] = datetime.now(ET)
                return fields             # closed inside the missed sessions: nothing left to step
    is_stale, reason = detect_stale_for_step(alert_date, fields["hold_days"] if fields else None, today)
    if is_stale:
        return {"_unavailable": (
            f"exit_history:{(alert_date + timedelta(days=1)).isoformat()}..{through.isoformat()}:"
            f"{len(day_bars)}_session_bar(s) — {reason}")}
    return fields


async def _insert_hour_row(row: dict, *, status: str, skip_reason: str | None = None,
                           orb_high: float | None = None, orb_low: float | None = None,
                           trigger_minute_et: time | None = None,
                           entry_price: float | None = None, stop_price: float | None = None,
                           hard_stop: float | None = None, risk_dollars: float | None = None,
                           entry_shares: float | None = None, atr_14: float | None = None) -> int | None:
    """Returns the new row's id, None on the UNIQUE conflict."""
    return await insert_shadow_trade({
        "ticker": row["ticker"],
        "alert_date": row["alert_date"],
        "bar_size_minutes": HOUR_BAR_SIZE_MINUTES,
        "signal_type": row["signal_type"],
        "shape_tag": row.get("shape_tag"),
        "score_tier": row.get("score_tier"),
        "orb_high": orb_high,
        "orb_low": orb_low,
        "atr_14": atr_14,
        "trigger_minute_et": trigger_minute_et,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "hard_stop": hard_stop,
        "risk_dollars": risk_dollars,
        "entry_shares": entry_shares,
        "status": status,
        "skip_reason": skip_reason,
        "remaining_shares": entry_shares if status == "open" else 0,
    })


async def _fetch_hour_lane_candidates(today: date) -> list[dict]:
    """5-minute rows (any status — the whole alert population) within the lookback that have no
    60-minute sibling yet. `atr_14` rides along so the hour row can state its stop width offline.
    The statement lives in db.py (`SHADOW_HOUR_LANE_CANDIDATES_SQL`) so the deploy prepares it."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            SHADOW_HOUR_LANE_CANDIDATES_SQL,
            today, BAR_SIZE_MINUTES, HOUR_BAR_SIZE_MINUTES, HOUR_LANE_LOOKBACK_DAYS,
        )
    out = []
    for r in rows:
        d = dict(r)
        d["atr_14"] = float(d["atr_14"]) if d.get("atr_14") is not None else None
        out.append(d)
    return out


# ── #482 evidence-quarantine: resumed-from-freeze detection (2026-08-17) ───
# The #216 jsonb double-encoding bug froze `update_shadow_trade` writes for
# months; the day the fix landed, the exit pass resumed every frozen row
# with ONE step spanning the whole gap — fabricating an outcome (a ~100-day
# price jump evaluated as if it were the very next trading day). Two
# related but DIFFERENT checks:
#
#   `detect_path_gap`       — classifies rows that ALREADY took the bad
#                              step (offline, one-time #482 remediation).
#   `detect_stale_for_step` — the LIVE guard: fires BEFORE a step, inside
#                              `update_shadow_positions`, so the bad step
#                              can never happen again (any cause — #216 or
#                              a future bug of the same shape).
#
# Both count WEEKDAYS only (no holiday calendar) — matches the existing
# `collector.prev_trading_days` / `shared.dates.last_trading_day`
# convention; thresholds carry slack for the 1-2 NYSE holidays a
# multi-month span can contain. Validated against every prod row on
# 2026-08-17: genuinely continuous rows cluster at gap/missed 0-1; every
# freeze-affected row starts at gap>=3 (min observed 3, max 75).

PATH_GAP_THRESHOLD_DAYS = 3
STALE_MISSED_SESSIONS_THRESHOLD = 2


def _count_weekday_sessions(after: date, through: date) -> int:
    """Weekdays (Mon-Fri) strictly after `after`, up to and including
    `through`. Weekend-only approximation (no holiday calendar)."""
    n = 0
    d = after + timedelta(days=1)
    while d <= through:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def detect_path_gap(
    alert_date: date, hold_days: int | None, running_closes: list,
) -> tuple[bool, str | None]:
    """Classify whether a row's RECORDED PATH already shows the
    resumed-from-freeze signature: far fewer recorded closes than the
    weekday sessions between `alert_date` and the day of the last recorded
    step (`alert_date + hold_days` calendar days). For the one-time #482
    remediation pass over EXISTING rows — not called from the live loop.
    """
    if hold_days is None:
        return False, None
    n_closes = len(running_closes or [])
    last_step_day = alert_date + timedelta(days=int(hold_days))
    expected = _count_weekday_sessions(alert_date, last_step_day)
    gap = expected - n_closes
    if gap >= PATH_GAP_THRESHOLD_DAYS:
        return True, (
            f"resumed-from-freeze (#216/#482): {n_closes} recorded close(s) "
            f"over {hold_days} calendar days (~{expected} trading sessions "
            f"expected, gap={gap})"
        )
    return False, None


def detect_stale_for_step(
    alert_date: date, hold_days: int | None, as_of: date,
) -> tuple[bool, str | None]:
    """LIVE guard: would stepping this row on `as_of` jump over more than
    one genuinely-missed trading session since its last recorded step?
    `apply_daily_exit_step` has no memory of what happened on skipped days,
    so stepping across a real gap fabricates an outcome exactly like the
    #216 resume did — this is what stops that from happening again.

    `hold_days is None` (never stepped) treats `alert_date` as the last
    step day — a brand-new row's very first step is always safe.
    """
    last_step_day = (
        alert_date + timedelta(days=int(hold_days))
        if hold_days is not None else alert_date
    )
    missed = _count_weekday_sessions(last_step_day, as_of) - 1
    if missed >= STALE_MISSED_SESSIONS_THRESHOLD:
        return True, (
            f"stale resume guard (#216/#482): last recorded step "
            f"{last_step_day.isoformat()}, stepping {as_of.isoformat()} "
            f"would skip {missed} trading session(s) — quarantined instead "
            f"of stepped"
        )
    return False, None


# ── Daily exit pass (16:30 ET) ──────────────────────────────────────────────


async def update_shadow_positions(today: date) -> dict[str, int]:
    """Apply one daily exit step to every open shadow row.

    Uses the same exit_logic as backtester + live tracker (SSOT). Shadow
    is pure telemetry — no Alpaca calls, no Telegram. Fractional partial
    sizing (integer_partial_shares=False) matches backtester semantics.

    #482 (2026-08-17): before stepping, each row passes `detect_stale_for_step`
    — a row whose last recorded step is many sessions stale gets quarantined
    (marked, not stepped) instead of silently fabricating a jump. See the
    detection block above.

    #482 add-on (2026-10-27): the 60-minute rows are stepped by the same loop —
    the open-row read no longer filters on bar size (every lane in the table
    walks this one ladder; the 5-minute rows' steps are byte-identical, pinned
    by the golden in tests/test_482_shadow_hour_lane.py).
    """
    open_rows = await get_open_shadow_trades(bar_size_minutes=None)
    if not open_rows:
        logger.info("Shadow ORB exit pass: no open rows")
        return {"closed": 0, "updated": 0, "no_data": 0, "error": 0,
                "quarantined_stale": 0}

    from agents.market_intelligence.db import log_audit_event

    counts = {"closed": 0, "updated": 0, "no_data": 0, "error": 0,
              "quarantined_stale": 0}
    today_str = today.isoformat()

    for row in open_rows:
        try:
            is_stale, stale_reason = detect_stale_for_step(
                row["alert_date"], row.get("hold_days"), today,
            )
            if is_stale:
                await update_shadow_trade(row["id"], {
                    "quarantined": True,
                    "quarantine_reason": stale_reason,
                    "quarantined_at": datetime.now(ET),
                })
                await log_audit_event(
                    "shadow_orb_stale_quarantine",
                    f"{row['ticker']} {row['alert_date']}: {stale_reason}",
                )
                counts["quarantined_stale"] += 1
                continue

            bars = await get_index_history(row["ticker"], today_str, today_str)
            daily_bar = bars[0] if bars else None
            state = _row_to_state(row)
            step = apply_daily_exit_step(
                state, daily_bar, today,
                integer_partial_shares=False,
            )
            outcome = await _persist_step(row, step, today)
            counts[outcome] = counts.get(outcome, 0) + 1
        except Exception:
            logger.exception(
                f"Shadow ORB exit {row['ticker']}: per-row crash"
            )
            counts["error"] += 1

    logger.info(f"Shadow ORB exit pass complete: {counts}")
    return counts


def _coerce_jsonb_list(value: Any) -> list:
    """Normalize a jsonb array column value to a list.

    Defensive READ tolerance for the #216 double-encoding bug: a legacy row
    written before the write-path fix stores the array as a JSON STRING
    (e.g. '[101.0, 102.0]') instead of a native array — decode it instead of
    raising. Matches the established `trade["exits"] if isinstance(...,
    list) else json.loads(...)` read-tolerance idiom already used for this
    exact exits/running_closes bug class at 8+ call sites (order_manager.py
    x4, live_tracker.py, trade_stream.py, backtester/tracker.py,
    exit_path_shadow.py, giveback_shadow.py) — not a new convention.
    """
    return value if isinstance(value, list) else json.loads(value or "[]")


def _row_to_state(row: dict) -> dict[str, Any]:
    return {
        "alert_date": row["alert_date"],
        "remaining_shares": float(row.get("remaining_shares") or 0),
        "entry_price": float(row["entry_price"]) if row.get("entry_price") else None,
        "hard_stop": float(row["hard_stop"]) if row.get("hard_stop") else None,
        "partial_taken": bool(row.get("partial_taken", False)),
        "breakeven_active": bool(row.get("breakeven_active", False)),
        "exits": _coerce_jsonb_list(row.get("exits")),
        "running_closes": [float(x) for x in _coerce_jsonb_list(row.get("running_closes"))],
    }


async def _persist_step(row: dict, step: Any, today: date) -> str:
    if step.action in ("skip_pre_alert", "no_data"):
        return "no_data"

    fields: dict[str, Any] = {
        "running_closes": step.new_running_closes,
        "exits": step.new_exits,
        "remaining_shares": step.new_remaining,
        "partial_taken": step.new_partial_taken,
        "breakeven_active": step.new_breakeven_active,
        "total_pnl": step.new_total_pnl,
        "hold_days": step.hold_days,
        "stop_price": step.effective_stop,
    }
    if step.closed:
        fields["status"] = "closed"
        fields["closed_at"] = datetime.now(ET)

    await update_shadow_trade(row["id"], fields)
    return "closed" if step.closed else "updated"


# ── Source helpers ──────────────────────────────────────────────────────────


async def _fetch_magna53_high_pre_open(today: date) -> list[dict]:
    """HIGH MAGNA53 alerts whose created_at is before 09:31 ET on `today`.

    Live ORB submission window is 09:30 ≤ now < 09:45 ET; HIGHs that arrive
    at 09:45–09:59 are tagged WINDOW_OUT_OF_ORB and live never enters them.
    Including those alerts in the shadow universe would flatter 5m unfairly
    (free entries live couldn't take). The 09:31 cutoff matches the cron
    fire time for live ORB monitoring.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (ticker)
                   ticker, alert_date, gap_pct, rel_volume, ep_score,
                   score_tier, catalyst, catalyst_quality, vol_percentile
            FROM mi_ep_alerts
            WHERE alert_date = $1
              AND score_tier = 'HIGH'
              AND (created_at AT TIME ZONE 'America/New_York')::time
                  < TIME '09:31:00'
            ORDER BY ticker, ep_score DESC
            """,
            today,
        )
    return [dict(r) for r in rows]


async def _fetch_latest_regime(today: date) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mi_market_regime WHERE regime_date <= $1 "
            "ORDER BY regime_date DESC LIMIT 1",
            today,
        )
    return dict(row) if row else None


# ── #482 offline remediation: faithful re-replay for resumed-from-freeze
#    OPEN rows (2026-08-17) ───────────────────────────────────────────────
# NOT called from the live daily loop (`update_shadow_positions` — that path
# is fully covered by `detect_stale_for_step` above, which quarantines
# instead of stepping). This is the ONE-TIME #482 remediation path for the
# rows that already carry a `detect_path_gap` gap: instead of leaving them
# quarantined forever, replay every missed daily bar honestly.


async def replay_stale_open_row(row: dict[str, Any], as_of: date) -> dict[str, Any]:
    """Faithful day-by-day re-replay of a resumed-from-freeze OPEN row.

    Re-seeds the exit ladder from the row's ORIGINAL entry parameters
    (alert_date, entry_price, hard_stop, entry_shares — set once at INSERT
    by `_insert_row`, never touched by the #216 freeze bug) and replays
    every REAL trading session from alert_date+1 through `as_of` using
    `collector.get_index_history`'s actual daily OHLC — the same 'l'/'c'
    shape `apply_daily_exit_step` already reads for the live single-day
    call in `update_shadow_positions`. Drives the replay through the SAME
    canonical driver (`exit_logic.iter_exit_ladder`) with the SAME kwargs
    the live path uses — `integer_partial_shares=False`, no `prior_closes`,
    no trail_mode/scale_fraction/giveback opt-ins. This is a DATA REPAIR
    (THE LINE): it reproduces exactly what the daily cron would have
    written had it never frozen — nothing about the exit rule changes.

    Returns a dict of corrected `update_shadow_trade` fields, including
    `pre_replay_snapshot` (the row's CURRENT — corrupted — recorded values,
    preserved alongside per the no-erase constraint) and `replayed_at`.

    Returns `{"_replay_unavailable": "<reason>"}` (that key only) when no
    historical bars are available for the range — caller falls back to
    quarantining the row instead.
    """
    from agents.market_intelligence.broker.exit_logic import (
        iter_exit_ladder,
        seed_exit_state,
    )

    alert_date = row["alert_date"]
    entry_price = float(row["entry_price"]) if row.get("entry_price") else None
    hard_stop = float(row["hard_stop"]) if row.get("hard_stop") else None
    entry_shares = float(row.get("entry_shares") or 0)

    bars = await get_index_history(
        row["ticker"],
        (alert_date + timedelta(days=1)).isoformat(),
        as_of.isoformat(),
    )
    if not bars:
        return {"_replay_unavailable": (
            f"get_index_history returned 0 daily bars for {row['ticker']} "
            f"{alert_date.isoformat()}..{as_of.isoformat()}"
        )}

    day_bars: list[tuple[date, dict]] = []
    for b in bars:
        ts = b.get("t")
        if ts is None:
            continue
        day = datetime.fromtimestamp(ts / 1000, tz=ET).date()
        day_bars.append((day, b))
    day_bars.sort(key=lambda x: x[0])

    state = seed_exit_state(
        alert_date=alert_date,
        entry_price=entry_price,
        hard_stop=hard_stop,
        remaining_shares=entry_shares,
    )
    last_step = None
    for _i, _day, step in iter_exit_ladder(
        state, day_bars, integer_partial_shares=False,
    ):
        last_step = step

    if last_step is None:
        return {"_replay_unavailable": (
            f"no fetched bar produced an evaluable step for {row['ticker']} "
            f"({alert_date.isoformat()}..{as_of.isoformat()})"
        )}

    total_pnl = sum(e.get("pnl", 0) for e in state["exits"])
    pre_replay_snapshot = {
        "running_closes": row.get("running_closes"),
        "exits": row.get("exits"),
        "remaining_shares": row.get("remaining_shares"),
        "partial_taken": row.get("partial_taken"),
        "breakeven_active": row.get("breakeven_active"),
        "total_pnl": row.get("total_pnl"),
        "hold_days": row.get("hold_days"),
        "status": row.get("status"),
        "stop_price": row.get("stop_price"),
        "closed_at": row["closed_at"].isoformat() if row.get("closed_at") else None,
    }

    fields: dict[str, Any] = {
        "running_closes": state["running_closes"],
        "exits": state["exits"],
        "remaining_shares": state["remaining_shares"],
        "partial_taken": state["partial_taken"],
        "breakeven_active": state["breakeven_active"],
        "total_pnl": total_pnl,
        "hold_days": last_step.hold_days,
        "stop_price": last_step.effective_stop,
        "pre_replay_snapshot": pre_replay_snapshot,
        "replayed_at": datetime.now(ET),
    }
    if last_step.closed:
        fields["status"] = "closed"
        fields["closed_at"] = datetime.now(ET)
    return fields
