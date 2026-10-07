"""2026-10-06 read-only: #658's 15-trading-day read — P1a (admitted_over_sector >= 1 per trading week),
P1b (rejected_over_sector <= admitted_over_sector over the window), and the boosted share of EP alerts
(+10 theme bonus) vs the baseline 25 of 346 and the backtest's 36 of 346."""
import asyncio, json
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::date d, detail FROM mi_audit_log
                                WHERE event_type='assignment_comove_summary' AND created_at >= '2026-09-15' ORDER BY created_at""")
        adm = rej = 0
        weeks = {}
        for r in rows:
            try:
                j = json.loads(r["detail"] or "{}")
            except Exception:
                continue
            a, b = int(j.get("admitted_over_sector") or 0), int(j.get("rejected_over_sector") or 0)
            adm += a; rej += b
            wk = r["d"].isocalendar()[1]
            weeks[wk] = weeks.get(wk, 0) + a
            print(r["d"], "admitted_over_sector", a, "rejected_over_sector", b)
        print("TOTAL admitted_over_sector", adm, "rejected_over_sector", rej, "| per ISO week admitted:", weeks)
        n_days = await c.fetchval("SELECT count(DISTINCT trade_date) FROM mi_daily_closes WHERE trade_date >= '2026-09-15' AND trade_date <= '2026-10-06'")
        print("trading days 09-15..10-06:", n_days)
        cols = [x["column_name"] for x in await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_alerts'")]
        tcol = next((x for x in ("theme_bonus_applied", "in_active_theme", "theme_bonus", "theme_boost") if x in cols), None)
        print("alert theme column:", tcol)
        if tcol:
            r = await c.fetchrow(f"""SELECT count(*) n, count(*) FILTER (WHERE {tcol}::text IN ('true','t','10','10.0')) boosted
                                     FROM mi_ep_alerts WHERE alert_date >= '2026-09-15'""")
            print("alerts since 09-15:", dict(r))
        for r in await c.fetch("""SELECT event_type, count(*) n FROM mi_audit_log WHERE created_at >= '2026-09-15'
                                  AND event_type ILIKE 'ep_theme_%' GROUP BY 1 ORDER BY 2 DESC LIMIT 8"""):
            print("  ", dict(r))


asyncio.run(main())
