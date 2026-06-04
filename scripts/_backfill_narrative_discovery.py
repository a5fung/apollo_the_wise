"""#167 narrative-discovery BACKFILL (advisory) — run discover_narrative_themes
over the last ~35 days of actual EP alerts to (a) measure the real clustering
RATE (proposals/day) and (b) front-load the inspection set so the 6/23 promote-
gate can be judged now instead of waiting weeks of slow forward accrual.

Writes narrative_cogap proposals to mi_theme_candidates_shadow (advisory shadow
table — NOT mi_themes, NOT trade state). Idempotent-ish: discover_narrative_themes
dedups per date. LOOKAHEAD CAVEAT: backfilled narrative labels carry present-day
hindsight on "was this a hot theme" — so the precision read runs optimistic; the
COUNT/rate (what we're after) + price-based actionability are robust. Backfilled
rows are distinguishable from forward ones by created_at >> run_date.

Run: docker exec apollo-market python scripts/_backfill_narrative_discovery.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.market_intelligence.theme_engine import discover_narrative_themes
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT alert_date FROM mi_ep_alerts "
            "WHERE alert_date > CURRENT_DATE - 35 ORDER BY alert_date"
        )
    dates = [r["alert_date"] for r in rows]
    print(f"\n#167 narrative-discovery backfill — {len(dates)} alert-days\n")
    print(f"{'date':<12}{'alerts':>7}{'themes':>7}  names")
    print("-" * 70)

    total = 0
    days_with = 0
    for d in dates:
        out = await discover_narrative_themes(d)
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
    asyncio.run(main())
