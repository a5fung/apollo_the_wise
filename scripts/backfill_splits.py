"""One-shot split-history reconciliation.

The nightly splits_ingest pipeline catches splits going forward, but cached
`mi_daily_closes` rows that predate the pipeline retain pre-split prices and
volumes. This script forces a re-fetch + overwrite for every Polygon split
in the last N days, including rows already marked applied (use --reset).

Designed to be safe to re-run — the underlying upsert is idempotent and
adjusted=true returns identical bars on each fetch.

Usage (prod):
    docker exec apollo-market python -m scripts.backfill_splits
    docker exec apollo-market python -m scripts.backfill_splits --days 180 --reset
    docker exec apollo-market python -m scripts.backfill_splits --ticker TOUR --reset

Verification (positive control):
    -- Before:
    SELECT trade_date, close, volume FROM mi_daily_closes
     WHERE ticker = 'TOUR' AND trade_date BETWEEN '2026-04-15' AND '2026-04-25'
     ORDER BY trade_date;
    -- Run: docker exec apollo-market python -m scripts.backfill_splits --ticker TOUR --reset
    -- Expect: pre-split closes ~$0.65 → ~$6.50 (×10), volumes 235k → 23.5k (÷10).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, timedelta

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import get_pool, reset_split_applied
from agents.market_intelligence.splits_ingest import run_splits_ingest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _reset_window(since: date, ticker: str | None = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if ticker:
            rows = await conn.fetch(
                """
                SELECT ticker, execution_date FROM mi_splits
                WHERE ticker = $1 AND execution_date >= $2
                """,
                ticker, since,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT ticker, execution_date FROM mi_splits
                WHERE execution_date >= $1
                """,
                since,
            )
    for r in rows:
        await reset_split_applied(r["ticker"], r["execution_date"])
    return len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60, help="Lookback window")
    parser.add_argument("--reset", action="store_true",
                        help="Reset adjustment_applied for already-applied rows in window")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Restrict --reset to one ticker (used with --reset)")
    args = parser.parse_args()

    since = et_today() - timedelta(days=args.days)
    logger.info(f"Backfill splits since {since} (reset={args.reset}, ticker={args.ticker})")

    if args.reset:
        n_reset = await _reset_window(since, ticker=args.ticker)
        logger.info(f"Reset adjustment_applied on {n_reset} rows")

    summary = await run_splits_ingest(since=since)
    logger.info(f"Done: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
