#!/usr/bin/env python3
"""#486 unblock (2026-09-07) — one-time prod run of the bounded-read backfill for
mi_theme_axis_shadow. SHADOW table only; touches no grade/alert/entry/exit/size column.

Usage (run inside apollo-market, which has the modules + DB — same pattern as
scripts/probes/_306_latency_check.py):
  python -m scripts.probes._486_backfill_bounded --fidelity-only   # read-only, no writes
  python -m scripts.probes._486_backfill_bounded --commit          # fidelity check + backfill

Always runs the fidelity check first (against the rows already captured live —
bounded_matches_unbounded IS NOT NULL) and prints it before touching anything else.
"""
from __future__ import annotations

import asyncio
import sys

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.theme_axis_shadow import (
    backfill_bounded_theme_reads,
    compute_bounded_backfill_read,
)


async def _fidelity_check(conn) -> bool:
    """Read-only: recompute the bounded read for every row the live writer has already
    captured (bounded_matches_unbounded IS NOT NULL) via the EXACT backfill code path
    (compute_bounded_backfill_read), and diff against the stored values. Never writes.
    Returns True iff every row reproduces exactly."""
    rows = await conn.fetch("""
        SELECT id, ticker, alert_date, theme_name, theme_name_7d, theme_stage_7d,
               bounded_matches_unbounded,
               ((created_at AT TIME ZONE 'America/New_York')::date = alert_date) AS same_day_write
        FROM mi_theme_axis_shadow
        WHERE bounded_matches_unbounded IS NOT NULL
        ORDER BY id
    """)
    print(f"\n=== FIDELITY CHECK: {len(rows)} live-captured row(s) ===")
    all_ok = True
    for r in rows:
        name_7d, stage_7d, matches = await compute_bounded_backfill_read(
            conn, r["ticker"], r["alert_date"], r["same_day_write"], r["theme_name"])
        ok = (name_7d == r["theme_name_7d"] and stage_7d == r["theme_stage_7d"]
              and matches == r["bounded_matches_unbounded"])
        all_ok = all_ok and ok
        status = "OK" if ok else "MISMATCH"
        print(f"  [{status}] id={r['id']} {r['ticker']} {r['alert_date']} "
              f"same_day_write={r['same_day_write']}")
        print(f"      stored:    name_7d={r['theme_name_7d']!r} stage_7d={r['theme_stage_7d']!r} "
              f"matches={r['bounded_matches_unbounded']!r}")
        print(f"      recomputed: name_7d={name_7d!r} stage_7d={stage_7d!r} matches={matches!r}")
    print(f"=== FIDELITY CHECK: {'ALL MATCH' if all_ok else 'MISMATCH FOUND'} "
          f"({len(rows)} row(s)) ===\n")
    return all_ok


async def _population_snapshot(conn, label: str) -> None:
    row = await conn.fetchrow("""
        SELECT
            count(*) AS n_total,
            count(*) FILTER (WHERE bounded_matches_unbounded IS NULL) AS n_null,
            count(*) FILTER (WHERE bounded_matches_unbounded IS NOT NULL) AS n_captured,
            count(*) FILTER (WHERE theme_name IS NOT NULL) AS n_themed,
            count(*) FILTER (WHERE theme_name IS NOT NULL
                              AND bounded_matches_unbounded IS TRUE) AS n_themed_agree,
            count(*) FILTER (WHERE theme_name IS NOT NULL
                              AND bounded_matches_unbounded IS FALSE) AS n_themed_disagree,
            count(*) FILTER (WHERE bounded_backfilled_at IS NOT NULL) AS n_backfilled_marker
        FROM mi_theme_axis_shadow
    """)
    print(f"--- population snapshot ({label}) ---")
    for k, v in dict(row).items():
        print(f"  {k}: {v}")
    print()


async def main() -> None:
    commit = "--commit" in sys.argv[1:]
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _population_snapshot(conn, "before")
        fidelity_ok = await _fidelity_check(conn)
        if not fidelity_ok:
            print("FIDELITY CHECK FAILED — refusing to run the backfill. Investigate before "
                  "re-running with --commit.")
            sys.exit(1)
        if not commit:
            print("--fidelity-only (or no flag): fidelity check passed, no writes made. "
                  "Re-run with --commit to perform the backfill.")
            return
        result = await backfill_bounded_theme_reads(conn)
        print(f"=== BACKFILL RESULT === {result}")
        await _population_snapshot(conn, "after")


if __name__ == "__main__":
    asyncio.run(main())
