#!/usr/bin/env python3
"""Meta-rubric STEP-0.5 backfill (#369): backfill mi_theme_axis_shadow over historical EP HIGHs.

SHADOW telemetry ONLY — read-only on mi_ep_alerts, writes ONLY mi_theme_axis_shadow (idempotent
upsert). Reuses the live STEP-0 writer `log_theme_axis_shadow` (identical heat / structural-
attribution / upsert), so a backfilled row is byte-identical to what the live hook would have
logged for that alert. Never touches trade-state or the live grade.

Grounding-era is DERIVABLE from alert_date (< 2026-06-23 = pre-#360, less-grounded catalyst text
from the Perplexity-discoverer era → noisier structural attribution). STEP-2 segments on it; no
new column needed.

Usage (run inside apollo-market, which has the modules + DB):
  python scripts/backfill_theme_axis_shadow.py [--since-days N]            # DRY-RUN (count + sample)
  python scripts/backfill_theme_axis_shadow.py [--since-days N] --commit   # perform the upsert
"""
from __future__ import annotations

import asyncio
import sys

from agents.market_intelligence.db import get_pool, get_theme_heat_asof
from agents.market_intelligence.theme_axis_shadow import (
    compute_structural_attribution,
    log_theme_axis_shadow,
)


async def main() -> None:
    args = sys.argv[1:]
    since_days = 120
    if "--since-days" in args:
        since_days = int(args[args.index("--since-days") + 1])
    commit = "--commit" in args

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, alert_date, score_tier, grounded_text
            FROM mi_ep_alerts
            WHERE score_tier = 'HIGH' AND alert_date >= CURRENT_DATE - $1::int
            ORDER BY alert_date
            """,
            since_days,
        )
        pre = sum(1 for r in rows if str(r["alert_date"]) < "2026-06-23")
        with_text = sum(1 for r in rows if r["grounded_text"])
        print(
            f"{len(rows)} historical EP HIGHs (last {since_days}d) — "
            f"{pre} pre-#360 / {len(rows) - pre} grounded-era · {with_text} have grounded_text"
        )

        if not commit:
            print("\n--- DRY-RUN sample (first 5 with grounded_text; NO writes) ---")
            shown = 0
            for r in rows:
                if shown >= 5:
                    break
                if not r["grounded_text"]:
                    continue
                heat = await get_theme_heat_asof(conn, r["ticker"], r["alert_date"])
                if heat is None:
                    print(f"  {r['alert_date']} {r['ticker']:6} THEMELESS")
                else:
                    score, attr, matched = compute_structural_attribution(
                        r["grounded_text"], r["ticker"], heat["tickers"],
                        heat["name"], heat["description"],
                    )
                    print(
                        f"  {r['alert_date']} {r['ticker']:6} "
                        f"theme={(heat['name'] or '')[:22]:22} {(heat['stage'] or ''):12} "
                        f"score={heat['score']} struct={score} matched={matched[:6]}"
                    )
                shown += 1
            print("\nRe-run with --commit to backfill.")
            return

        n = 0
        for r in rows:
            await log_theme_axis_shadow(conn, dict(r))
            n += 1
        print(f"\nbackfilled {n} rows into mi_theme_axis_shadow (idempotent upsert)")


if __name__ == "__main__":
    asyncio.run(main())
