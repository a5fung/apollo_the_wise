"""
One-time OHLC backfill for `mi_daily_closes`.

Older rows in `mi_daily_closes` are close+volume only — `open_price`,
`high_price`, `low_price` were added later and never backfilled. The
parabolic-short detector (and any future detector that needs intraday
shape) requires 60+ sessions of full OHLC per ticker. Without this
backfill the 17:15 ET parabolic scan returns zero usable candidates
for ~55 trading days.

Strategy: pull Polygon grouped-daily for every trading day in the
trailing N days that has any NULL `open_price` rows, and re-upsert
through `ingest_daily_closes()`. The existing ON CONFLICT clause
COALESCE's OHLC columns, so close/volume are untouched and only the
NULL OHLC fields get filled.

Usage (run on prod where Polygon key + DB pool live):
    docker exec apollo-market python -m scripts.backfill_ohlc
    docker exec apollo-market python -m scripts.backfill_ohlc --days 90 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, timedelta

from agents.market_intelligence.collector import get_grouped_daily
from agents.market_intelligence.db import get_pool, ingest_daily_closes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _dates_needing_backfill(days: int) -> list[date]:
    """Trading dates within trailing `days` that have any NULL open_price rows."""
    pool = await get_pool()
    cutoff = date.today() - timedelta(days=days)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT trade_date
            FROM mi_daily_closes
            WHERE trade_date >= $1
            GROUP BY trade_date
            HAVING COUNT(*) FILTER (WHERE open_price IS NULL) > 0
            ORDER BY trade_date
            """,
            cutoff,
        )
    return [r["trade_date"] for r in rows]


async def _backfill(days: int, dry_run: bool) -> None:
    targets = await _dates_needing_backfill(days)
    if not targets:
        logger.info(f"No dates with NULL OHLC in trailing {days}d. Nothing to do.")
        return

    logger.info(f"Backfilling OHLC for {len(targets)} trading dates "
                f"({targets[0]} → {targets[-1]})")
    if dry_run:
        for d in targets:
            logger.info(f"  [DRY RUN] would fetch grouped-daily for {d}")
        return

    total_rows = 0
    failed: list[date] = []
    for i, d in enumerate(targets, 1):
        try:
            bars = await get_grouped_daily(d.isoformat())
            if not bars:
                logger.warning(f"[{i}/{len(targets)}] {d}: empty grouped-daily payload")
                failed.append(d)
                continue
            n = await ingest_daily_closes(d, bars)
            total_rows += n
            logger.info(f"[{i}/{len(targets)}] {d}: upserted {n} rows ({len(bars)} bars)")
        except Exception as e:
            logger.error(f"[{i}/{len(targets)}] {d}: failed — {e}")
            failed.append(d)

    logger.info(f"Done. Upserted {total_rows} rows across {len(targets) - len(failed)} dates.")
    if failed:
        logger.warning(f"{len(failed)} dates failed: {failed}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--days", type=int, default=90,
                   help="Calendar days to scan for NULL OHLC (default 90 — covers 60 trading days + buffer)")
    p.add_argument("--dry-run", action="store_true",
                   help="List dates that would be backfilled, don't fetch")
    args = p.parse_args()
    asyncio.run(_backfill(args.days, args.dry_run))


if __name__ == "__main__":
    main()
