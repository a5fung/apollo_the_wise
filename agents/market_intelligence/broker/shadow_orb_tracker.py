"""Shadow ORB tracker — telemetry-only 5-minute ORB simulation.

Records would-be 5-min ORB entries and outcomes alongside the live 1-min
trades so we can answer: "is there a class of EPs better entered at 5m
than at 1m?" Same alert universe, same gates, same exit rules — only the
ORB bar size differs (apples-to-apples).

No Alpaca submits. No new Telegram alerts. Pure telemetry surfaced via
`/audit shadow_orb` and the Sunday weekly review.

Two cron entry points:
    run_shadow_pass(today)        — 10:00 ET, ORB window closed
    update_shadow_positions(today) — 16:30 ET, daily exit step
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
from agents.market_intelligence.broker.order_manager import (
    prepare_prior_day_low_orb_order,
    prepare_orb_order,
)
from agents.market_intelligence.broker.skip_reasons import (
    INFRA_NO_BAR,
)
from agents.market_intelligence.collector import get_index_history, prev_trading_days
from agents.market_intelligence.db import (
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


# ── Daily exit pass (16:30 ET) ──────────────────────────────────────────────


async def update_shadow_positions(today: date) -> dict[str, int]:
    """Apply one daily exit step to every open shadow row.

    Uses the same exit_logic as backtester + live tracker (SSOT). Shadow
    is pure telemetry — no Alpaca calls, no Telegram. Fractional partial
    sizing (integer_partial_shares=False) matches backtester semantics.
    """
    open_rows = await get_open_shadow_trades(bar_size_minutes=BAR_SIZE_MINUTES)
    if not open_rows:
        logger.info("Shadow ORB exit pass: no open rows")
        return {"closed": 0, "updated": 0, "no_data": 0, "error": 0}

    counts = {"closed": 0, "updated": 0, "no_data": 0, "error": 0}
    today_str = today.isoformat()

    for row in open_rows:
        try:
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
