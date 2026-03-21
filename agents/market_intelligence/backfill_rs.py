"""
Backfill RS scores from historical daily closes.

Replays run_rs_engine() for weekly dates going back as far as daily close
data allows (needs 6M lookback, so earliest scorable date ≈ closes_start + 6M).

Usage:
    python -m agents.market_intelligence.backfill_rs [--weeks 16] [--dry-run]

Safe to re-run — uses upsert (ON CONFLICT DO UPDATE) so existing scores
for already-computed dates are refreshed, not duplicated.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, timedelta

from agents.market_intelligence.rs_engine import run_rs_engine
from agents.market_intelligence.db import get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def get_scorable_range() -> tuple[date, date]:
    """Return (earliest_scorable_date, latest_date) based on available daily closes."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT MIN(trade_date), MAX(trade_date) FROM mi_daily_closes"
        )
    if not row or not row[0]:
        raise RuntimeError("No daily closes in DB — run bootstrap first")
    earliest_close = row[0]
    latest_close = row[1]
    # Need 6 months of lookback for rs_6m
    earliest_scorable = earliest_close + timedelta(days=190)  # ~6M + buffer
    return earliest_scorable, latest_close


def generate_weekly_dates(start: date, end: date) -> list[date]:
    """Generate Friday dates (trading week end) from start to end."""
    dates = []
    # Start from the first Friday on or after start
    d = start
    while d.weekday() != 4:  # 4 = Friday
        d += timedelta(days=1)
    while d <= end:
        dates.append(d)
        d += timedelta(days=7)
    return dates


async def backfill(weeks: int | None = None, dry_run: bool = False) -> None:
    """Run RS engine for historical weekly dates."""
    earliest, latest = await get_scorable_range()
    logger.info(f"Scorable range: {earliest} to {latest}")

    all_dates = generate_weekly_dates(earliest, latest)

    if weeks:
        all_dates = all_dates[-weeks:]

    # Check which dates already have scores
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetch(
            "SELECT DISTINCT score_date FROM mi_stock_scores WHERE score_date = ANY($1)",
            all_dates,
        )
    existing_dates = {r["score_date"] for r in existing}
    to_compute = [d for d in all_dates if d not in existing_dates]

    logger.info(
        f"Backfill plan: {len(all_dates)} weekly dates, "
        f"{len(existing_dates)} already computed, "
        f"{len(to_compute)} to compute"
    )

    if dry_run:
        for d in to_compute:
            logger.info(f"  [DRY RUN] Would compute: {d}")
        return

    for i, d in enumerate(to_compute):
        logger.info(f"[{i+1}/{len(to_compute)}] Computing RS for {d}...")
        try:
            result = await run_rs_engine(trade_date=d)
            scored = result.get("stocks_scored", 0)
            logger.info(f"  Scored {scored} stocks for {d}")
        except Exception as e:
            logger.error(f"  Failed for {d}: {e}")

    logger.info("Backfill complete")


def main():
    parser = argparse.ArgumentParser(description="Backfill RS scores from daily closes")
    parser.add_argument("--weeks", type=int, default=None, help="Only backfill last N weeks (default: all available)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be computed without running")
    args = parser.parse_args()
    asyncio.run(backfill(weeks=args.weeks, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
