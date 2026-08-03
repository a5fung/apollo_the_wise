"""#329 — backfill the co-movement axis for rows written before the check went live.

WHY. `refresh_co_movement_for_date` runs FORWARD-ONLY (the 17:xx job calls it with `et_today()`),
so it has only ever populated rows from 2026-07-27 on. Everything earlier sits dark on that axis:
~437 of 496 `mi_theme_axis_shadow` rows at the time of writing.

That matters now because #368's labelling session is about to read this cohort. A dataset that is
90% blank on one axis is exactly the shape that produces a confident wrong answer — twice today a
partly-blank or wrongly-scaled dataset nearly did (a fraction/percent mix-up read as 0%, and a
sweep that returned identical results for 91 days read as "already optimal").

SAFE TO BACKFILL, and that is a property of the function, not an assumption:
  * It is IDEMPOTENT — recomputes unconditionally from the same inputs, so a re-run converges.
  * It is POINT-IN-TIME by construction — the cohort is re-derived via `get_theme_heat_asof` at
    `trade_date - 1 day`, STRICTLY-PRIOR theme state. That reproduces exactly what the scan-time
    writer saw at 9:35 AM, and it stops a theme BORN FROM the day's own move from grading its own
    co-movement. So running it over history introduces no lookahead.

Shadow table, no money path. Read-only until `--execute` is passed.

    python scripts/_329_backfill_co_movement.py            # dry run: what is dark, per date
    python scripts/_329_backfill_co_movement.py --execute  # backfill
"""
import argparse
import asyncio
import sys


async def main(execute: bool) -> int:
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.theme_axis_shadow import refresh_co_movement_for_date

    pool = await get_pool()
    async with pool.acquire() as conn:
        # ⚠ GROUP BY alert_date, NEVER created_at. The first draft of this script used
        # created_at::date and would have been WRONG for most of the table: 452 rows were WRITTEN
        # on 2026-06-24 in one seeding pass but carry 60 distinct alert_dates spanning
        # 2026-03-24 .. 2026-06-24. Passing the write-date as `trade_date` would have graded each
        # row's co-movement against the wrong day's cohort and the wrong day's closes — fabricating
        # 406 rows of plausible-looking nonsense. `alert_date` is the day the move actually happened
        # and the only key `refresh_co_movement_for_date` can be correct against.
        dark = await conn.fetch("""
            SELECT alert_date AS d,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE co_moving IS NULL) AS dark
            FROM mi_theme_axis_shadow
            GROUP BY 1 HAVING COUNT(*) FILTER (WHERE co_moving IS NULL) > 0
            ORDER BY 1
        """)

    if not dark:
        print("Nothing dark — every row already carries the co-movement axis.")
        return 0

    total_dark = sum(r["dark"] for r in dark)
    print(f"{len(dark)} date(s) with dark rows · {total_dark} rows total")
    for r in dark[:5]:
        print(f"   {r['d']}  {r['dark']}/{r['total']} dark")
    if len(dark) > 5:
        print(f"   … and {len(dark) - 5} more dates")

    if not execute:
        print("\nDRY RUN — nothing written. Re-run with --execute to backfill.")
        return 0

    refreshed = skipped = failed = 0
    async with pool.acquire() as conn:
        for r in dark:
            try:
                out = await refresh_co_movement_for_date(conn, r["d"])
                refreshed += int(out.get("refreshed", 0))
                skipped += int(out.get("skipped", 0))
            except Exception as e:      # per-date isolation: one bad day must not stop the rest
                failed += 1
                print(f"   ! {r['d']}: {type(e).__name__}: {e}")

    print(f"\nbackfilled {refreshed} row(s) · {skipped} skipped (cohort not re-derivable) · "
          f"{failed} date(s) errored")

    async with pool.acquire() as conn:
        left = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_theme_axis_shadow WHERE co_moving IS NULL")
    print(f"still dark after backfill: {left}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="write; omit for a dry run")
    sys.exit(asyncio.run(main(ap.parse_args().execute)))
