"""Backfill mi_daily_closes with multi-year daily bars (operator-approved 2026-09-06).

WHY: our history began 2025-08-04 — thirteen months. He judges multi-year structure: RNG's
"long base since 2022" is the reason he called it the only outright-good chart we have ever
shown him, and none of it is in our data. A weekly or monthly chart over thirteen months is
the same window drawn coarser, so the fix is depth, not interval.

REUSES the live path rather than re-implementing it — `collector.get_grouped_daily` to fetch
and `db.ingest_daily_closes` to write, so the backfilled rows are byte-identical in shape to
the ones the nightly job writes (same ticker filter, same conflict target, same COALESCE
semantics that never overwrite a good OHLC with a null).

SAFE BY CONSTRUCTION:
  - Only touches dates we do NOT already have. Existing rows are never revisited.
  - The writer is an idempotent upsert, so a re-run after an interruption is harmless.
  - Skips weekends before spending a call; a market holiday returns an empty payload and is
    recorded as such rather than retried.
  - --dry-run prints the plan and fetches nothing.

USAGE:  python3 scripts/probes/_backfill_daily_history.py --years 5 [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence.collector import get_grouped_daily  # noqa: E402
from agents.market_intelligence.db import get_pool, ingest_daily_closes  # noqa: E402

# Polite pacing. Polygon's documented limit is far higher, but a one-shot backfill has no
# deadline and there is nothing to gain by crowding a provider we depend on every morning.
PACE_SECONDS = 0.35
PROGRESS_EVERY = 50


async def _existing_dates() -> set[date]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT trade_date FROM mi_daily_closes")
    return {r["trade_date"] for r in rows}


async def main(years: int, dry_run: bool) -> None:
    have = await _existing_dates()
    earliest_have = min(have) if have else date.today()
    start = date.today() - timedelta(days=365 * years)
    # Only the gap BELOW what we hold — never re-fetch a session we already have.
    wanted = []
    d = start
    while d < earliest_have:
        if d.weekday() < 5 and d not in have:
            wanted.append(d)
        d += timedelta(days=1)

    print(f"history held : {len(have)} sessions, earliest {earliest_have}")
    print(f"target start : {start}  ({years} years)")
    print(f"to fetch     : {len(wanted)} weekday sessions (holidays return empty and are skipped)")
    if dry_run:
        print("\n--dry-run: fetched nothing.")
        return
    if not wanted:
        print("nothing to do.")
        return

    ok = rows = empty = failed = 0
    for i, d in enumerate(wanted, 1):
        try:
            bars = await get_grouped_daily(d.isoformat())
            if bars:
                n = await ingest_daily_closes(d, bars)
                rows += n
                ok += 1
            else:
                empty += 1          # market holiday, or a date the provider has no data for
        except Exception as e:      # never abort the run for one bad session
            failed += 1
            print(f"  ! {d}: {type(e).__name__}: {str(e)[:90]}")
        if i % PROGRESS_EVERY == 0 or i == len(wanted):
            print(f"  {i}/{len(wanted)}  sessions_ok={ok} rows={rows:,} empty={empty} failed={failed}")
        await asyncio.sleep(PACE_SECONDS)

    print(f"\nDONE  sessions_ok={ok}  empty={empty}  failed={failed}  rows_written={rows:,}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.years, a.dry_run))
