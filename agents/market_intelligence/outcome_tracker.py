"""
Signal outcome tracker — measures forward returns for RS leaders, EP alerts, and theme transitions.

Runs nightly after fundamental flags. Computes forward returns at various horizons:
- 1D, 1W (5 trading days), 1M (21 trading days), 3M (63 trading days)
- Compares to SPY for alpha calculation

First RS leader outcomes appear ~21 trading days after deployment.
EP 1D outcomes appear next day.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import (
    get_pool,
    upsert_signal_outcome,
    get_signal_outcomes,
)

logger = logging.getLogger(__name__)

# Trading day offsets (approximate calendar days)
_1D_OFFSET = 1
_1W_OFFSET = 7      # ~5 trading days
_1M_OFFSET = 30     # ~21 trading days
_3M_OFFSET = 90     # ~63 trading days


async def run_outcome_tracker(trade_date: date | None = None) -> dict:
    """Main entry. Runs all outcome computations. Returns summary."""
    today = trade_date or et_today()
    total = 0

    try:
        n = await _compute_rs_leader_outcomes(today)
        total += n
        if n:
            logger.info(f"Outcome tracker: {n} RS leader outcomes computed")
    except Exception as e:
        logger.error(f"RS leader outcomes failed: {e}")

    try:
        n = await _compute_ep_outcomes(today)
        total += n
        if n:
            logger.info(f"Outcome tracker: {n} EP outcomes computed")
    except Exception as e:
        logger.error(f"EP outcomes failed: {e}")

    try:
        n = await _compute_theme_outcomes(today)
        total += n
        if n:
            logger.info(f"Outcome tracker: {n} theme outcomes computed")
    except Exception as e:
        logger.error(f"Theme outcomes failed: {e}")

    try:
        n = await _compute_9m_ep_outcomes(today)
        total += n
        if n:
            logger.info(f"Outcome tracker: {n} 9M EP outcomes computed")
    except Exception as e:
        logger.error(f"9M EP outcomes failed: {e}")

    return {"total": total, "trade_date": today.isoformat()}


async def _compute_rs_leader_outcomes(today: date) -> int:
    """
    For RS leaders from ~21 trading days ago (1M), compute forward 1M returns.
    Also compute 3M returns for signals ~63 trading days old.
    Compare to SPY for alpha.
    """
    pool = await get_pool()
    count = 0

    async with pool.acquire() as conn:
        for offset_days, fwd_field in [(_1M_OFFSET, "fwd_1m_pct"), (_3M_OFFSET, "fwd_3m_pct")]:
            signal_date_approx = today - timedelta(days=offset_days)

            # Find actual score_date closest to the target
            signal_date_row = await conn.fetchrow("""
                SELECT DISTINCT score_date FROM mi_stock_scores
                WHERE score_date <= $1 AND score_date >= $1 - INTERVAL '5 days'
                ORDER BY score_date DESC LIMIT 1
            """, signal_date_approx)
            if not signal_date_row:
                continue
            signal_date = signal_date_row["score_date"]

            # Already computed?
            existing = await conn.fetchval("""
                SELECT COUNT(*) FROM mi_signal_outcomes
                WHERE signal_type = 'rs_leader' AND signal_date = $1 AND {fwd} IS NOT NULL
            """.format(fwd=fwd_field), signal_date)
            if existing and existing >= 15:
                continue

            # Get top 20 RS leaders on signal_date
            leaders = await conn.fetch("""
                SELECT ticker, rs_composite FROM mi_stock_scores
                WHERE score_date = $1
                ORDER BY rs_composite DESC NULLS LAST
                LIMIT 20
            """, signal_date)
            if not leaders:
                continue

            tickers = [r["ticker"] for r in leaders]

            # Get closes on signal_date and today
            signal_closes = await conn.fetch("""
                SELECT ticker, close FROM mi_daily_closes
                WHERE trade_date = $1 AND ticker = ANY($2) AND close > 0
            """, signal_date, tickers)
            signal_close_map = {r["ticker"]: r["close"] for r in signal_closes}

            # Find most recent trade date for today closes
            today_date_row = await conn.fetchrow("""
                SELECT DISTINCT trade_date FROM mi_daily_closes
                WHERE trade_date <= $1 AND trade_date >= $1 - INTERVAL '3 days'
                ORDER BY trade_date DESC LIMIT 1
            """, today)
            if not today_date_row:
                continue
            today_close_date = today_date_row["trade_date"]

            today_closes = await conn.fetch("""
                SELECT ticker, close FROM mi_daily_closes
                WHERE trade_date = $1 AND ticker = ANY($2) AND close > 0
            """, today_close_date, tickers)
            today_close_map = {r["ticker"]: r["close"] for r in today_closes}

            # SPY forward return
            spy_signal = await conn.fetchval(
                "SELECT close FROM mi_daily_closes WHERE trade_date = $1 AND ticker = 'SPY'",
                signal_date,
            )
            spy_today = await conn.fetchval(
                "SELECT close FROM mi_daily_closes WHERE trade_date = $1 AND ticker = 'SPY'",
                today_close_date,
            )
            spy_fwd = None
            if spy_signal and spy_today:
                spy_fwd = round((spy_today - spy_signal) / spy_signal * 100, 2)

            spy_fwd_field = "spy_fwd_1m_pct" if offset_days == _1M_OFFSET else "spy_fwd_3m_pct"

            for r in leaders:
                ticker = r["ticker"]
                if ticker not in signal_close_map or ticker not in today_close_map:
                    continue
                fwd_pct = round(
                    (today_close_map[ticker] - signal_close_map[ticker])
                    / signal_close_map[ticker] * 100, 2
                )
                record = {
                    "signal_type": "rs_leader",
                    "signal_date": signal_date,
                    "identifier": ticker,
                    "detail": {"rs_composite": r["rs_composite"]},
                    fwd_field: fwd_pct,
                    spy_fwd_field: spy_fwd,
                }
                await upsert_signal_outcome(record)
                count += 1

    return count


async def _compute_ep_outcomes(today: date) -> int:
    """
    For EP alerts at various ages, compute forward returns.
    1D: alerts from yesterday. 1W: alerts from 5 trading days ago. 1M: 21 trading days ago.
    """
    pool = await get_pool()
    count = 0

    async with pool.acquire() as conn:
        for offset_days, fwd_field in [
            (_1D_OFFSET, "fwd_1d_pct"),
            (_1W_OFFSET, "fwd_1w_pct"),
            (_1M_OFFSET, "fwd_1m_pct"),
        ]:
            alert_date_approx = today - timedelta(days=offset_days)

            # Find EP alerts around that date
            alerts = await conn.fetch("""
                SELECT ticker, alert_date, ep_score, catalyst_quality
                FROM mi_ep_alerts
                WHERE alert_date <= $1 AND alert_date >= $1 - INTERVAL '3 days'
            """, alert_date_approx)
            if not alerts:
                continue

            for alert in alerts:
                ticker = alert["ticker"]
                alert_date = alert["alert_date"]

                # Already computed for this field?
                existing = await conn.fetchrow("""
                    SELECT {fwd} FROM mi_signal_outcomes
                    WHERE signal_type = 'ep_alert' AND signal_date = $1
                      AND identifier = $2 AND {fwd} IS NOT NULL
                """.format(fwd=fwd_field), alert_date, ticker)
                if existing:
                    continue

                # Get close on alert_date and today
                alert_close = await conn.fetchval("""
                    SELECT close FROM mi_daily_closes
                    WHERE trade_date = $1 AND ticker = $2 AND close > 0
                """, alert_date, ticker)
                if not alert_close:
                    continue

                today_close_row = await conn.fetchrow("""
                    SELECT close FROM mi_daily_closes
                    WHERE ticker = $1 AND trade_date <= $2
                      AND trade_date >= $2 - INTERVAL '3 days'
                      AND close > 0
                    ORDER BY trade_date DESC LIMIT 1
                """, ticker, today)
                if not today_close_row:
                    continue

                fwd_pct = round(
                    (today_close_row["close"] - alert_close) / alert_close * 100, 2
                )

                record = {
                    "signal_type": "ep_alert",
                    "signal_date": alert_date,
                    "identifier": ticker,
                    "detail": {
                        "ep_score": alert["ep_score"],
                        "catalyst_quality": alert["catalyst_quality"],
                    },
                    fwd_field: fwd_pct,
                }
                await upsert_signal_outcome(record)
                count += 1

    return count


async def _compute_theme_outcomes(today: date) -> int:
    """
    Detect stage transitions by comparing themes on consecutive dates.
    For transitions 1M+ old, compute avg constituent forward returns.
    """
    pool = await get_pool()
    count = 0

    async with pool.acquire() as conn:
        transition_date = today - timedelta(days=_1M_OFFSET)

        # Find theme dates around 1M ago
        date_rows = await conn.fetch("""
            SELECT DISTINCT theme_date FROM mi_themes
            WHERE theme_date <= $1 AND theme_date >= $1 - INTERVAL '5 days'
            ORDER BY theme_date DESC LIMIT 2
        """, transition_date)
        if len(date_rows) < 2:
            return 0

        curr_date = date_rows[0]["theme_date"]
        prev_date = date_rows[1]["theme_date"]

        # Get themes on both dates
        curr_themes = await conn.fetch(
            "SELECT name, stage, tickers FROM mi_themes WHERE theme_date = $1", curr_date
        )
        prev_themes = await conn.fetch(
            "SELECT name, stage, tickers FROM mi_themes WHERE theme_date = $1", prev_date
        )

        prev_map = {r["name"]: r for r in prev_themes}

        for ct in curr_themes:
            name = ct["name"]
            if name not in prev_map:
                continue
            prev_stage = prev_map[name]["stage"]
            curr_stage = ct["stage"]
            if prev_stage == curr_stage:
                continue

            # Stage transition detected
            tickers = ct["tickers"] or []
            if not tickers:
                continue

            # Already computed?
            existing = await conn.fetchval("""
                SELECT COUNT(*) FROM mi_signal_outcomes
                WHERE signal_type = 'theme_stage' AND signal_date = $1 AND identifier = $2
            """, curr_date, name)
            if existing:
                continue

            # Compute avg forward returns for constituents
            fwd_returns = []
            for ticker in tickers[:20]:
                signal_close = await conn.fetchval("""
                    SELECT close FROM mi_daily_closes
                    WHERE trade_date = $1 AND ticker = $2 AND close > 0
                """, curr_date, ticker)
                today_close = await conn.fetchval("""
                    SELECT close FROM mi_daily_closes
                    WHERE ticker = $1 AND trade_date <= $2
                      AND trade_date >= $2 - INTERVAL '3 days'
                      AND close > 0
                    ORDER BY trade_date DESC LIMIT 1
                """, ticker, today)
                if signal_close and today_close:
                    fwd_returns.append(
                        (today_close - signal_close) / signal_close * 100
                    )

            avg_fwd = round(sum(fwd_returns) / len(fwd_returns), 2) if fwd_returns else None

            record = {
                "signal_type": "theme_stage",
                "signal_date": curr_date,
                "identifier": name,
                "detail": {
                    "from_stage": prev_stage,
                    "to_stage": curr_stage,
                    "tickers": tickers[:20],
                },
                "fwd_1m_pct": avg_fwd,
            }
            await upsert_signal_outcome(record)
            count += 1

    return count


async def _compute_9m_ep_outcomes(today: date) -> int:
    """
    For confirmed 9M sugar babies at various ages, compute forward returns.
    1D: babies from yesterday. 1W: ~7 days ago. 1M: ~30 days ago.
    Writes to mi_signal_outcomes with signal_type='9m_ep'.
    """
    pool = await get_pool()
    count = 0

    async with pool.acquire() as conn:
        for offset_days, fwd_field in [
            (_1D_OFFSET, "fwd_1d_pct"),
            (_1W_OFFSET, "fwd_1w_pct"),
            (_1M_OFFSET, "fwd_1m_pct"),
        ]:
            baby_date_approx = today - timedelta(days=offset_days)

            babies = await conn.fetch("""
                SELECT ticker, alert_date, volume, close_in_range_pct, gap_pct
                FROM mi_9m_sugar_babies
                WHERE alert_date <= $1 AND alert_date >= $1 - INTERVAL '3 days'
            """, baby_date_approx)
            if not babies:
                continue

            for baby in babies:
                ticker = baby["ticker"]
                alert_date = baby["alert_date"]

                existing = await conn.fetchrow("""
                    SELECT {fwd} FROM mi_signal_outcomes
                    WHERE signal_type = '9m_ep' AND signal_date = $1
                      AND identifier = $2 AND {fwd} IS NOT NULL
                """.format(fwd=fwd_field), alert_date, ticker)
                if existing:
                    continue

                alert_close = await conn.fetchval("""
                    SELECT close FROM mi_daily_closes
                    WHERE trade_date = $1 AND ticker = $2 AND close > 0
                """, alert_date, ticker)
                if not alert_close:
                    continue

                today_close_row = await conn.fetchrow("""
                    SELECT close FROM mi_daily_closes
                    WHERE ticker = $1 AND trade_date <= $2
                      AND trade_date >= $2 - INTERVAL '3 days'
                      AND close > 0
                    ORDER BY trade_date DESC LIMIT 1
                """, ticker, today)
                if not today_close_row:
                    continue

                fwd_pct = round(
                    (today_close_row["close"] - alert_close) / alert_close * 100, 2
                )

                record = {
                    "signal_type": "9m_ep",
                    "signal_date": alert_date,
                    "identifier": ticker,
                    "detail": {
                        "volume": baby["volume"],
                        "close_in_range_pct": baby["close_in_range_pct"],
                        "gap_pct": baby.get("gap_pct"),
                    },
                    fwd_field: fwd_pct,
                }
                await upsert_signal_outcome(record)
                count += 1

    return count


async def get_weekly_signal_summary(lookback_days: int = 30) -> dict:
    """
    Aggregate outcomes for weekly report:
    - RS Top 20 avg fwd return vs SPY (alpha)
    - EP alert hit rate (% profitable at 1M)
    - Theme stage transition avg returns
    """
    today = et_today()
    from_date = today - timedelta(days=lookback_days)

    rs_outcomes = await get_signal_outcomes("rs_leader", from_date=from_date)
    ep_outcomes = await get_signal_outcomes("ep_alert", from_date=from_date)

    # RS leader alpha
    rs_1m = [r["fwd_1m_pct"] for r in rs_outcomes if r.get("fwd_1m_pct") is not None]
    spy_1m = [r["spy_fwd_1m_pct"] for r in rs_outcomes if r.get("spy_fwd_1m_pct") is not None]
    rs_avg = round(sum(rs_1m) / len(rs_1m), 2) if rs_1m else None
    spy_avg = round(sum(spy_1m) / len(spy_1m), 2) if spy_1m else None
    rs_alpha = round(rs_avg - spy_avg, 2) if rs_avg is not None and spy_avg is not None else None

    # EP hit rate at 1M
    ep_1m = [r["fwd_1m_pct"] for r in ep_outcomes if r.get("fwd_1m_pct") is not None]
    ep_profitable = sum(1 for x in ep_1m if x > 0)
    ep_total = len(ep_1m)
    ep_hit_rate = round(ep_profitable / ep_total * 100, 0) if ep_total > 0 else None

    return {
        "rs_avg_1m": rs_avg,
        "spy_avg_1m": spy_avg,
        "rs_alpha": rs_alpha,
        "rs_count": len(rs_1m),
        "ep_profitable": ep_profitable,
        "ep_total": ep_total,
        "ep_hit_rate": ep_hit_rate,
    }
