"""
One-shot historical backfill of mi_minute_volume_curves for an expanded universe.

The nightly `_minute_volume_curves_refresh_job` only covers the top-500 by
20d dollar volume. EP candidates routinely come from outside that universe
(small/mid-caps having an unusual day), so the 9:30-9:44 RVOL@T gate has
~9% coverage on real cohort tickers (verified 2026-04-30 via
scripts/backfill_dead_zone.py).

This script extends coverage by computing baselines for an expanded
universe: top-1500 by 20d dollar volume UNION any ticker that appeared as
a HIGH/MODERATE EP alert OR a post-open dead-zoned candidate in the last
90 days. Polygon's minute-bar history goes back years; we don't need to
wait for the nightly cron to accumulate samples.

Reuses `minute_volume._refresh_one_ticker` — same window, same anchor
math, same MIN_SAMPLE_N filter — so the rows produced are identical to
what the nightly cron would produce for these tickers, just sooner.

Run once on Hetzner after-hours:

    docker exec apollo-market python -m scripts.backfill_minute_curves
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents.market_intelligence.db import get_pool, upsert_minute_volume_curves
from agents.market_intelligence.minute_volume import (
    _refresh_one_ticker,
    LOOKBACK_DAYS,
    _REFRESH_CONCURRENCY,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


async def fetch_expanded_universe(top_n: int, ep_cohort_days: int) -> list[str]:
    """Top-N by adv_20 * close UNION 90d EP cohort (alerts + dead-zoned)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        latest = await conn.fetchval("SELECT MAX(score_date) FROM mi_stock_scores")
        if latest is None:
            return []
        rows = await conn.fetch(
            f"""WITH top_dv AS (
                  SELECT ticker
                    FROM mi_stock_scores
                   WHERE score_date = $1
                     AND adv_20 IS NOT NULL
                     AND close IS NOT NULL
                ORDER BY (adv_20 * close) DESC NULLS LAST
                   LIMIT $2
                ),
                ep_alerts AS (
                  SELECT DISTINCT ticker
                    FROM mi_ep_alerts
                   WHERE alert_date > CURRENT_DATE - {ep_cohort_days}
                ),
                dead_zone AS (
                  SELECT DISTINCT ticker
                    FROM mi_ep_scan_log
                   WHERE scan_date > CURRENT_DATE - {ep_cohort_days}
                     AND filter_reason LIKE '%post-open%'
                )
                SELECT ticker FROM top_dv
                UNION
                SELECT ticker FROM ep_alerts
                UNION
                SELECT ticker FROM dead_zone""",
            latest, top_n,
        )
    return sorted({r["ticker"] for r in rows})


async def main(top_n: int, ep_cohort_days: int, lookback_days: int) -> None:
    et_today = datetime.now(_ET).date()
    to_d = et_today - timedelta(days=1)
    from_d = to_d - timedelta(days=lookback_days)
    from_str, to_str = from_d.strftime("%Y-%m-%d"), to_d.strftime("%Y-%m-%d")

    universe = await fetch_expanded_universe(top_n, ep_cohort_days)
    logger.info(f"Expanded universe: {len(universe)} tickers (top {top_n} + {ep_cohort_days}d EP cohort)")
    logger.info(f"Window: {from_str} → {to_str}")

    sem = asyncio.Semaphore(_REFRESH_CONCURRENCY)
    succeeded = 0
    rows_written = 0
    failed = 0

    async def _do_one(ticker: str):
        nonlocal succeeded, rows_written, failed
        async with sem:
            try:
                recs = await _refresh_one_ticker(ticker, from_str, to_str)
                if recs:
                    written = await upsert_minute_volume_curves(recs)
                    succeeded += 1
                    rows_written += written
            except Exception as e:
                failed += 1
                logger.warning(f"Curve refresh failed for {ticker}: {e}")

    # Progress logging
    total = len(universe)
    progress_every = max(50, total // 20)

    async def _do_with_progress(ticker: str, idx: int):
        await _do_one(ticker)
        if (idx + 1) % progress_every == 0:
            logger.info(
                f"Progress: {idx + 1}/{total} ({succeeded} succeeded, "
                f"{rows_written} rows, {failed} failed)"
            )

    await asyncio.gather(*[_do_with_progress(t, i) for i, t in enumerate(universe)])

    logger.info(
        f"Done. attempted={total} succeeded={succeeded} "
        f"rows_written={rows_written} failed={failed}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=1500)
    parser.add_argument("--ep-cohort-days", type=int, default=90)
    parser.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS)
    args = parser.parse_args()
    asyncio.run(main(
        top_n=args.top_n,
        ep_cohort_days=args.ep_cohort_days,
        lookback_days=args.lookback_days,
    ))
