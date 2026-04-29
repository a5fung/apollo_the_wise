"""Wick-fill (P22) tracker — telemetry-only.

Daily flow:
  1. EOD sweep (called from ninem_detector at ~5pm ET) inserts new
     mi_wick_candidates rows for today's 9M days closing in [0.50, 0.75)
     of intraday range with green body and ≥3× ADV.
  2. Forward-returns job (~17:45 ET) walks unsettled rows whose 10-trading-
     session horizon has elapsed and writes filled_wick + fwd_Nd_from_high
     and fwd_Nd_from_close.

No entries, no orders. Promotion to paper gated by telemetry_review:
n_candidates ≥ 30 AND fill_rate ≥ 0.50. Disabling the strategy halts the
EOD sweep entirely; a manual backfill is needed to recover the missed days.
"""
from __future__ import annotations

import logging
from datetime import date

from agents.market_intelligence import db
from agents.market_intelligence.strategies.registry import should_run

logger = logging.getLogger(__name__)

_HORIZON_DAYS = 10
_OFFSETS = (1, 3, 10)


async def run_wick_sweep(today: "date | str") -> int:
    """Persist today's wick candidates. Returns rows written. Gated by
    `should_run('wick_fill')`."""
    if not await should_run("wick_fill"):
        await db.log_audit_event(
            "strategy_disabled_skip",
            "wick_fill disabled — skipping EOD sweep",
        )
        return 0
    if isinstance(today, str):
        today = date.fromisoformat(today)
    candidates = await db.get_eod_9m_wick_candidates(today)
    if not candidates:
        return 0
    for c in candidates:
        await db.insert_wick_candidate({
            "ticker": c["ticker"],
            "alert_date": today,
            "open_price": float(c["open_price"]),
            "close_price": float(c["close_price"]),
            "high_price": float(c["high_price"]),
            "low_price": float(c["low_price"]),
            "volume": int(c["volume"]),
            "close_in_range_pct": float(c["close_in_range_pct"]),
            "prior_high": float(c["high_price"]),
            "prev_5d_pct": c.get("prev_5d_pct"),
            "prev_20d_pct": c.get("prev_20d_pct"),
            "prev_vs_sma10": c.get("prev_vs_sma10"),
            "prev_vs_sma50": c.get("prev_vs_sma50"),
            "sma50_slope_pct": c.get("sma50_slope_pct"),
            "prior_sessions": c.get("prior_sessions"),
        })
    logger.info(f"wick_sweep {today}: persisted {len(candidates)} candidates")
    return len(candidates)


async def update_forward_returns(today: "date | str") -> int:
    """Walk unsettled rows and write fwd returns once ≥10 trading sessions
    have elapsed since alert_date. Rows without enough forward data yet are
    left untouched and retried next day.

    Intentionally NOT gated by `should_run('wick_fill')`: disabling the
    strategy mid-cycle should still settle pending rows so accumulated
    telemetry isn't lost. The sweep gate halts new candidate creation;
    this gate would only orphan in-flight measurements."""
    if isinstance(today, str):
        today = date.fromisoformat(today)
    pending = await db.get_unsettled_wick_candidates(today)
    if not pending:
        return 0
    pool = await db.get_pool()
    settled = 0
    for row in pending:
        ticker = row["ticker"]
        alert_date = row["alert_date"]
        prior_high = float(row["prior_high"])
        anchor_close = float(row["close_price"])
        async with pool.acquire() as conn:
            session_rows = await conn.fetch(
                """
                SELECT trade_date, close, high_price
                FROM mi_daily_closes
                WHERE ticker = $1
                  AND trade_date > $2
                ORDER BY trade_date ASC
                LIMIT $3
                """,
                ticker, alert_date, _HORIZON_DAYS,
            )
        if len(session_rows) < _HORIZON_DAYS:
            continue
        sessions = [dict(s) for s in session_rows]

        filled_wick = False
        fill_date: "date | None" = None
        for s in sessions:
            if s["high_price"] is not None and float(s["high_price"]) >= prior_high:
                filled_wick = True
                fill_date = s["trade_date"]
                break

        from_high: dict[int, float | None] = {n: None for n in _OFFSETS}
        from_close: dict[int, float | None] = {n: None for n in _OFFSETS}
        for n in _OFFSETS:
            session_n = sessions[n - 1]
            close_n = float(session_n["close"])
            if anchor_close > 0:
                from_close[n] = (close_n - anchor_close) / anchor_close * 100.0
            window_filled = any(
                s["high_price"] is not None and float(s["high_price"]) >= prior_high
                for s in sessions[:n]
            )
            if window_filled and prior_high > 0:
                from_high[n] = (close_n - prior_high) / prior_high * 100.0

        await db.update_wick_forward_returns(
            row["id"],
            filled_wick=filled_wick,
            fill_date=fill_date,
            fwd_1d_from_high_pct=from_high[1],
            fwd_3d_from_high_pct=from_high[3],
            fwd_10d_from_high_pct=from_high[10],
            fwd_1d_from_close_pct=from_close[1],
            fwd_3d_from_close_pct=from_close[3],
            fwd_10d_from_close_pct=from_close[10],
        )
        settled += 1
    logger.info(f"wick_forward_returns {today}: settled {settled} rows")
    return settled
