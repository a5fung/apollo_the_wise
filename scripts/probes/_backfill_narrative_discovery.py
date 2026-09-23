"""#167 narrative-discovery BACKFILL (advisory) — run discover_narrative_themes
over the last ~35 days of actual EP alerts to (a) measure the real clustering
RATE (proposals/day) and (b) front-load the inspection set so the 6/23 promote-
gate can be judged now instead of waiting weeks of slow forward accrual.

Writes narrative_cogap proposals to mi_theme_candidates_shadow (advisory shadow
table — NOT mi_themes, NOT trade state). Idempotent-ish: discover_narrative_themes
dedups per date. LOOKAHEAD CAVEAT: backfilled narrative labels carry present-day
hindsight on "was this a hot theme" — so the precision read runs optimistic; the
COUNT/rate (what we're after) + run_date-anchored forward returns are robust;
the HINDSIGHT-exposed signal is `live_unified` (recall, scored vs TODAY's themes).
Backfilled rows are SEGREGATED by source='narrative_cogap_backfill' (#167, 2026-06-06)
so the promote-gate splits them from the forward population by construction.

Run: docker exec apollo-market python scripts/_backfill_narrative_discovery.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.market_intelligence.theme_engine import discover_narrative_themes
from agents.market_intelligence.db import get_pool


async def main(persist: bool):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT alert_date FROM mi_ep_alerts "
            "WHERE alert_date > CURRENT_DATE - 35 ORDER BY alert_date"
        )
    dates = [r["alert_date"] for r in rows]
    print(f"\n#167 narrative-discovery backfill — {len(dates)} alert-days "
          f"({'WRITE' if persist else 'DRY (read-only A/B)'})\n")
    print(f"{'date':<12}{'alerts':>7}{'themes':>7}  names")
    print("-" * 70)

    total = 0
    days_with = 0
    for d in dates:
        # backfilled=True → source='narrative_cogap_backfill' so these hindsight
        # rows stay SEGREGATED from the forward population at the promote-gate (#167).
        out = await discover_narrative_themes(d, persist=persist, backfilled=True)
        n = out.get("themes", 0) or 0
        total += n
        if n > 0:
            days_with += 1
        names = ", ".join(out.get("names") or [])
        err = out.get("error")
        print(f"{str(d):<12}{out.get('alerts', 0):>7}{n:>7}  {names}{(' ERR:' + str(err)[:40]) if err else ''}")

    nd = len(dates) or 1
    print("\n" + "=" * 60)
    print(f"SUMMARY: {len(dates)} alert-days, {days_with} produced >=1 proposal, {total} proposals total.")
    print(f"RATE: {total/nd:.2f} proposals/day · {days_with/nd*100:.0f}% of days clustered.")
    print(f"At this rate, N=5 (rolling-30d) accrues in ~{(5/ (total/nd)) if total else float('inf'):.0f} alert-days "
          f"(but the rolling window also ages rows out — see if steady-state >=5).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="read-only A/B: do NOT persist to shadow table")
    args = ap.parse_args()
    asyncio.run(main(persist=not args.dry))
