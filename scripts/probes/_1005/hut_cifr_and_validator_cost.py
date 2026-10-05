"""2026-10-05 read-only: (1) where HUT/CIFR live now after rule B retired their home; (2) which of tonight's
20 rule-B retirements were small BEFORE tonight vs made small by tonight's removals; (3) price a validator replay."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        d1 = await c.fetchval("SELECT max(theme_date) FROM mi_themes")
        d0 = await c.fetchval("SELECT max(theme_date) FROM mi_themes WHERE theme_date < $1", d1)
        print("tonight", d1, "prior", d0)
        for tk in ("HUT", "CIFR"):
            rows = await c.fetch("SELECT name, stage FROM mi_themes WHERE theme_date=$1 AND $2 = ANY(tickers) AND stage <> 'Retired'", d1, tk)
            prev = await c.fetch("SELECT name, stage FROM mi_themes WHERE theme_date=$1 AND $2 = ANY(tickers)", d0, tk)
            print(f"== {tk} tonight: {[dict(r) for r in rows]} | prior night: {[dict(r) for r in prev]}")
        names = [r["detail"] for r in await c.fetch("""SELECT detail::json->>'theme' detail FROM mi_audit_log WHERE event_type='theme_retired_small_fading'
                 AND (created_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date""")]
        print("== rule B retirements: prior-night stage / members -> tonight's removals")
        made_small = 0
        for n in names:
            p = await c.fetchrow("SELECT stage, tickers FROM mi_themes WHERE theme_date=$1 AND name=$2", d0, n)
            cd = await c.fetch("""SELECT ticker, LEFT(removal_reason, 40) r FROM mi_validation_cooldowns WHERE theme_name=$1
                                  AND (removed_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date""", n)
            pn = len(p["tickers"] or []) if p else None
            if pn is not None and pn >= 3:
                made_small += 1
            print(f"  {n[:60]:60s} prior={p['stage'] if p else None}/{pn} removed_tonight={[(r['ticker'], r['r']) for r in cd]}")
        print("made small tonight (had >=3 members last night):", made_small, "of", len(names))
        print("== validator spend per night (theme_validation)")
        for r in await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::date d, model, count(*) n, round(sum(cost_usd)::numeric, 3) usd
                                  FROM api_usage WHERE caller='theme_validation' AND created_at > now() - interval '10 days' GROUP BY 1,2 ORDER BY 1"""):
            print("  ", dict(r))


asyncio.run(main())
