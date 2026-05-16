"""EP Selectivity Phase 1 — master cohort CSV exporter.

Materializes two CSVs for `docs/decisions/0003-ep-selectivity-overhaul.md`:

  analysis/2026-05-16/ep_cohort_alerts_60d.csv
    One row per (ticker, alert_date) — collapses multiple intraday ticks
    to the top-conviction alert (DISTINCT ON ordered by ep_score DESC
    NULLS LAST, detected_at DESC). LEFT JOINs satellite tables.

  analysis/2026-05-16/ep_cohort_skipped_60d.csv
    Filter-rejected candidates from mi_ep_missed_outcomes
    (source='scan_filter') — pre-scored alerts that the system threw
    away, with forward returns for shed-winner analysis.

  analysis/2026-05-16/catalyst_labels.csv
    Labeling sheet for the user: last 30d HIGH alerts only
    (~200-260 rows), filtered down to (ticker, alert_date, catalyst,
    catalyst_quality, gap_pct, ep_score, label).

Cartesian-explosion guard (user catch 2026-05-16):
  mi_ep_alerts emits multiple ticks per (ticker, alert_date) when the
  same stock crosses the threshold repeatedly intraday. A naive LEFT
  JOIN on (ticker, scan_date) duplicates forward-return rows and
  corrupts crosstabs. We collapse to one row per (ticker, alert_date)
  BEFORE joining downstream tables.

Run on prod after market close:
    docker exec apollo-market python -m scripts.ep_selectivity_cohort
    docker exec apollo-market python -m scripts.ep_selectivity_cohort --window-days 90
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
from pathlib import Path

from agents.market_intelligence.db import get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT_DIR = Path("analysis/2026-05-16")

# Top-conviction collapse: pick the highest ep_score per (ticker, alert_date);
# tiebreak on most-recent detected_at. NULLS LAST so legitimate scores beat
# NULL rows that predate the detected_at backfill.
COHORT_ALERTS_SQL = """
WITH top_alerts AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
           a.id, a.ticker, a.alert_date, a.gap_pct, a.rel_volume,
           a.ep_score, a.score_tier, a.catalyst, a.catalyst_quality,
           a.pm_rvol, a.pm_rvol_baseline_n, a.detected_at, a.vol_percentile,
           a.confidence_multiplier
    FROM mi_ep_alerts a
    WHERE a.alert_date >= CURRENT_DATE - $1::int
    ORDER BY a.ticker, a.alert_date,
             a.ep_score DESC NULLS LAST,
             a.detected_at DESC NULLS LAST,
             a.id DESC
),
last_scan_tick AS (
    SELECT DISTINCT ON (sl.ticker, sl.scan_date)
           sl.ticker, sl.scan_date,
           sl.scan_time_et AS last_scan_time_et,
           sl.rank_by_gap, sl.projected_vol_multiple,
           sl.pm_rvol AS scan_pm_rvol,
           sl.adv, sl.adv_source, sl.minutes_since_open,
           sl.filter_reason AS final_filter_reason
    FROM mi_ep_scan_log sl
    WHERE sl.scan_date >= CURRENT_DATE - $1::int
    ORDER BY sl.ticker, sl.scan_date, sl.scan_time_et DESC NULLS LAST, sl.id DESC
)
SELECT
    a.ticker, a.alert_date, a.gap_pct, a.rel_volume,
    a.ep_score, a.score_tier, a.catalyst, a.catalyst_quality,
    a.pm_rvol, a.pm_rvol_baseline_n,
    a.detected_at, a.vol_percentile, a.confidence_multiplier,
    -- last scan tick context (filter that finally let it through, or held it)
    ls.last_scan_time_et, ls.rank_by_gap, ls.projected_vol_multiple,
    ls.scan_pm_rvol, ls.adv, ls.adv_source, ls.minutes_since_open,
    ls.final_filter_reason,
    -- forward returns from scan_outcomes (every alert gets a row computed nightly)
    so.fwd_5d_pct, so.fwd_10d_pct, so.baseline_close,
    so.n_sessions_5d, so.n_sessions_10d,
    -- traded vs not (paper, methodology only)
    lt.id AS trade_id, lt.status AS trade_status, lt.skip_reason AS trade_skip_reason,
    lt.entry_price, lt.entry_shares, lt.stop_price, lt.atr_14 AS trade_atr_14,
    lt.orb_high, lt.orb_low, lt.total_pnl, lt.partial_taken, lt.breakeven_active,
    lt.hold_days, lt.entry_attempt,
    -- 5-min ORB shadow (C1 dimension)
    os.status AS shadow_5m_status, os.entry_price AS shadow_5m_entry,
    os.total_pnl AS shadow_5m_pnl, os.skip_reason AS shadow_5m_skip,
    -- missed-outcomes mirror for unentered alerts (high_unentered / moderate_alert)
    mo.source AS missed_source, mo.skip_category AS missed_category,
    mo.ret_1d, mo.ret_5d, mo.ret_20d, mo.max_high_5d, mo.max_high_20d,
    -- theme membership (most recent snapshot ≤ alert_date)
    th.theme_name, th.theme_stage,
    -- continuation flag stage (COILED / TRIGGERED) on alert_date
    fc.stage AS flag_stage, fc.base_age AS flag_base_age,
    fc.runup_pct AS flag_runup_pct, fc.atr14_pct AS flag_atr14_pct,
    fc.sma_10, fc.sma_20, fc.rs_rank,
    -- gap-day OHLC + prior-day close for MA distance
    d0.open_price AS d0_open, d0.high_price AS d0_high,
    d0.low_price AS d0_low, d0.close AS d0_close,
    d_prev.close AS prev_close,
    -- MA distance (252d lookback, best-effort; nullable when history thin)
    ma.sma_10_calc, ma.sma_20_calc, ma.sma_50_calc, ma.sma_200_calc,
    ma.hi_252d,
    -- bookkeeping
    a.alert_date AS join_date
FROM top_alerts a
LEFT JOIN last_scan_tick ls
  ON ls.ticker = a.ticker AND ls.scan_date = a.alert_date
LEFT JOIN mi_ep_scan_outcomes so
  ON so.ticker = a.ticker AND so.scan_date = a.alert_date
LEFT JOIN mi_live_trades lt
  ON lt.ticker = a.ticker AND lt.alert_date = a.alert_date
 AND lt.account_mode = 'paper'
 AND lt.pnl_attribution IS NULL  -- methodology rows only
LEFT JOIN LATERAL (
    -- mi_orb_shadow_trades is NOT unique on (ticker, alert_date) — a
    -- ticker can have both magna53 and 9m_day2 5-min shadow rows the
    -- same day. Pick the higher-conviction one (status='closed' >
    -- 'cancelled' > 'no_entry') then any.
    SELECT status, entry_price, total_pnl, skip_reason
    FROM mi_orb_shadow_trades
    WHERE ticker = a.ticker AND alert_date = a.alert_date
      AND bar_size_minutes = 5
    ORDER BY
        CASE status WHEN 'closed' THEN 0 WHEN 'cancelled' THEN 1 ELSE 2 END,
        id DESC
    LIMIT 1
) os ON TRUE
LEFT JOIN LATERAL (
    -- mi_ep_missed_outcomes UNIQUE (ticker, alert_date, source). A
    -- ticker firing both MODERATE and HIGH that didn't trade produces
    -- TWO rows. Prefer 'high_unentered' (matches top-conviction alert).
    SELECT source, skip_category, ret_1d, ret_5d, ret_20d,
           max_high_5d, max_high_20d
    FROM mi_ep_missed_outcomes
    WHERE ticker = a.ticker AND alert_date = a.alert_date
      AND source IN ('high_unentered', 'moderate_alert')
    ORDER BY CASE source WHEN 'high_unentered' THEN 0 ELSE 1 END
    LIMIT 1
) mo ON TRUE
LEFT JOIN LATERAL (
    SELECT t.name AS theme_name, t.stage AS theme_stage
    FROM mi_themes t
    WHERE a.ticker = ANY(t.tickers) AND t.theme_date <= a.alert_date
    ORDER BY t.theme_date DESC
    LIMIT 1
) th ON TRUE
LEFT JOIN mi_flag_candidates fc
  ON fc.ticker = a.ticker AND fc.scan_date = a.alert_date
LEFT JOIN mi_daily_closes d0
  ON d0.ticker = a.ticker AND d0.trade_date = a.alert_date
LEFT JOIN LATERAL (
    SELECT close
    FROM mi_daily_closes
    WHERE ticker = a.ticker AND trade_date < a.alert_date
    ORDER BY trade_date DESC LIMIT 1
) d_prev ON TRUE
LEFT JOIN LATERAL (
    SELECT
        AVG(close) FILTER (WHERE trade_date >= a.alert_date - INTERVAL '10 days')  AS sma_10_calc,
        AVG(close) FILTER (WHERE trade_date >= a.alert_date - INTERVAL '20 days')  AS sma_20_calc,
        AVG(close) FILTER (WHERE trade_date >= a.alert_date - INTERVAL '50 days')  AS sma_50_calc,
        AVG(close) FILTER (WHERE trade_date >= a.alert_date - INTERVAL '200 days') AS sma_200_calc,
        MAX(high_price)                                                            AS hi_252d
    FROM mi_daily_closes
    WHERE ticker = a.ticker
      AND trade_date >= a.alert_date - INTERVAL '252 days'
      AND trade_date < a.alert_date
) ma ON TRUE
ORDER BY a.alert_date DESC, a.ticker;
"""

COHORT_SKIPPED_SQL = """
SELECT
    mo.ticker, mo.alert_date,
    mo.source, mo.skip_reason, mo.skip_category,
    mo.ep_score, mo.gap_pct, mo.rel_volume, mo.catalyst_quality,
    mo.open_d0, mo.close_d0,
    mo.ret_1d, mo.ret_5d, mo.ret_20d,
    mo.max_high_5d, mo.max_high_20d,
    -- scan_log context for the candidate that got filtered
    sl.scan_time_et, sl.rank_by_gap, sl.projected_vol_multiple,
    sl.pm_rvol, sl.adv, sl.adv_source, sl.minutes_since_open,
    sl.filter_reason
FROM mi_ep_missed_outcomes mo
LEFT JOIN LATERAL (
    SELECT scan_time_et, rank_by_gap, projected_vol_multiple,
           pm_rvol, adv, adv_source, minutes_since_open, filter_reason
    FROM mi_ep_scan_log
    WHERE ticker = mo.ticker AND scan_date = mo.alert_date
    ORDER BY scan_time_et DESC NULLS LAST, id DESC
    LIMIT 1
) sl ON TRUE
WHERE mo.alert_date >= CURRENT_DATE - $1::int
  AND mo.source = 'scan_filter'
ORDER BY mo.alert_date DESC, mo.ticker;
"""

CATALYST_LABELS_SQL = """
SELECT DISTINCT ON (a.ticker, a.alert_date)
       a.ticker, a.alert_date, a.gap_pct, a.ep_score,
       a.catalyst_quality, a.catalyst,
       a.claude_analysis,
       ''::text AS user_label,
       ''::text AS user_notes
FROM mi_ep_alerts a
WHERE a.alert_date >= CURRENT_DATE - 30
  AND a.score_tier = 'HIGH'
ORDER BY a.ticker, a.alert_date,
         a.ep_score DESC NULLS LAST,
         a.detected_at DESC NULLS LAST,
         a.id DESC;
"""


async def export_alerts_cohort(window_days: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(COHORT_ALERTS_SQL, window_days)
        distinct_count = await conn.fetchval(
            "SELECT COUNT(DISTINCT (ticker, alert_date)) FROM mi_ep_alerts "
            "WHERE alert_date >= CURRENT_DATE - $1::int",
            window_days,
        )

    n_rows = len(rows)
    logger.info(
        "alerts cohort: fetched=%d, expected_distinct=%d", n_rows, distinct_count
    )
    if n_rows != distinct_count:
        logger.error(
            "ROW MISMATCH — cohort fan-out detected. fetched=%d distinct=%d",
            n_rows, distinct_count,
        )
        raise SystemExit(
            "Cartesian fan in alerts cohort. Inspect the LEFT JOIN that fanned "
            "(likely scan_outcomes/missed_outcomes/orb_shadow). Aborting CSV export."
        )

    out = OUT_DIR / f"ep_cohort_alerts_{window_days}d.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        logger.warning("alerts cohort empty — writing header only.")
        out.write_text("ticker,alert_date,no_data\n")
        return 0

    cols = list(rows[0].keys())
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([_cell(r[c]) for c in cols])
    logger.info("wrote %s (%d rows)", out, n_rows)
    return n_rows


async def export_skipped_cohort(window_days: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(COHORT_SKIPPED_SQL, window_days)
    out = OUT_DIR / f"ep_cohort_skipped_{window_days}d.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        logger.warning("skipped cohort empty — writing header only.")
        out.write_text("ticker,alert_date,no_data\n")
        return 0
    cols = list(rows[0].keys())
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([_cell(r[c]) for c in cols])
    logger.info("wrote %s (%d rows)", out, len(rows))
    return len(rows)


async def export_catalyst_labels() -> int:
    """Last 30d HIGH catalyst-labeling sheet for operator review."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(CATALYST_LABELS_SQL)
    out = OUT_DIR / "catalyst_labels.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        logger.warning("catalyst_labels empty — writing header only.")
        out.write_text("ticker,alert_date,no_data\n")
        return 0
    cols = list(rows[0].keys())
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([_cell(r[c]) for c in cols])
    logger.info("wrote %s (%d rows)", out, len(rows))
    return len(rows)


async def side_checks(window_days: int) -> None:
    """Block 1 sanity checks: alert count + mi_daily_closes depth for fixtures."""
    pool = await get_pool()
    fixtures = ("NBIS", "CSCO", "KLAR", "TRT", "ONDS", "CPA", "CRMD")
    async with pool.acquire() as conn:
        n_alerts = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_ep_alerts WHERE alert_date >= CURRENT_DATE - $1::int",
            window_days,
        )
        n_distinct = await conn.fetchval(
            "SELECT COUNT(DISTINCT (ticker, alert_date)) FROM mi_ep_alerts "
            "WHERE alert_date >= CURRENT_DATE - $1::int",
            window_days,
        )
        n_high = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_ep_alerts WHERE alert_date >= CURRENT_DATE - $1::int "
            "AND score_tier = 'HIGH'",
            window_days,
        )
        n_scan_log = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_ep_scan_log WHERE scan_date >= CURRENT_DATE - $1::int",
            window_days,
        )
        n_missed = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_ep_missed_outcomes "
            "WHERE alert_date >= CURRENT_DATE - $1::int",
            window_days,
        )
        n_outcomes = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_ep_scan_outcomes "
            "WHERE scan_date >= CURRENT_DATE - $1::int",
            window_days,
        )
        n_shadow = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_orb_shadow_trades "
            "WHERE alert_date >= CURRENT_DATE - $1::int AND bar_size_minutes = 5",
            window_days,
        )
        fixture_history = await conn.fetch(
            "SELECT ticker, COUNT(*) AS n_days, MIN(trade_date) AS earliest, "
            "MAX(trade_date) AS latest FROM mi_daily_closes "
            "WHERE ticker = ANY($1::text[]) GROUP BY ticker ORDER BY ticker",
            list(fixtures),
        )

    logger.info("─" * 60)
    logger.info("SIDE CHECKS — window=%dd", window_days)
    logger.info("  mi_ep_alerts rows:             %d", n_alerts)
    logger.info("  mi_ep_alerts distinct (t,d):   %d", n_distinct)
    logger.info("  mi_ep_alerts HIGH:             %d", n_high)
    logger.info("  mi_ep_scan_log rows:           %d", n_scan_log)
    logger.info("  mi_ep_missed_outcomes rows:    %d", n_missed)
    logger.info("  mi_ep_scan_outcomes rows:      %d", n_outcomes)
    logger.info("  mi_orb_shadow_trades (5m):     %d", n_shadow)
    logger.info("  Alert-multiplicity ratio:      %.2f", n_alerts / max(1, n_distinct))
    logger.info("─" * 60)
    logger.info("FIXTURE history (mi_daily_closes coverage):")
    seen = {r["ticker"] for r in fixture_history}
    for r in fixture_history:
        logger.info(
            "  %-6s n=%4d  %s → %s",
            r["ticker"], r["n_days"], r["earliest"], r["latest"]
        )
    for tk in fixtures:
        if tk not in seen:
            logger.warning("  %s — NO daily_closes rows", tk)
    logger.info("─" * 60)


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "|".join(str(x) for x in v)
    return v


async def main(window_days: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    await side_checks(window_days)
    n_alerts = await export_alerts_cohort(window_days)
    n_skipped = await export_skipped_cohort(window_days)
    n_labels = await export_catalyst_labels()
    logger.info("DONE — alerts=%d skipped=%d labels=%d", n_alerts, n_skipped, n_labels)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=60)
    args = ap.parse_args()
    asyncio.run(main(args.window_days))
