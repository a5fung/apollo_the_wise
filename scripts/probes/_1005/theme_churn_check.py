"""2026-10-05 read-only: the weekly digest's churn anomaly — 20 high-churn pairs three weeks running, this
week all 2 adds / 2 removes in the Offshore Drilling and Appalachian Gas themes. Membership by night and the
audit rows that added/removed each name."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        names = await c.fetch("SELECT DISTINCT name FROM mi_themes WHERE theme_date >= '2026-09-21' AND "
                              "(name ILIKE '%offshore%' OR name ILIKE '%appalach%' OR name ILIKE '%natural gas%')")
        for n in names:
            print("=====", n["name"])
            rows = await c.fetch("SELECT theme_date, stage, tickers FROM mi_themes WHERE name=$1 AND theme_date >= '2026-09-21' "
                                 "ORDER BY theme_date", n["name"])
            prev = None
            for r in rows:
                cur = set(r["tickers"] or [])
                d = "" if prev is None else f"  +{sorted(cur-prev)} -{sorted(prev-cur)}"
                print(f"  {r['theme_date']} {r['stage']:<12} {len(cur)} {sorted(cur)}{d}")
                prev = cur
        ev = await c.fetch("SELECT created_at AT TIME ZONE 'America/New_York' AS t, event_type, left(summary, 170) s "
                           "FROM mi_audit_log WHERE created_at >= '2026-09-28' AND (summary ILIKE '%offshore%' OR "
                           "summary ILIKE '%appalach%') ORDER BY created_at")
        print("== audit rows naming them:")
        for e in ev[-30:]:
            print(f"  {e['t']:%m-%d %H:%M} {e['event_type']:<32} {e['s']}")


asyncio.run(main())
