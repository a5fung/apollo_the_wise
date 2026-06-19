"""6/16 CLOSE reconciliation — verify the items owed-for-today (read-only)."""
import asyncio
from datetime import date
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        # ---- audit-log event counts, last 30h (schema-safe) ----
        print("=== mi_audit_log — last 30h, owed-item events ===")
        rows = await c.fetch("""
            SELECT event_type, count(*) n, max(created_at) AS last
            FROM mi_audit_log
            WHERE created_at >= now() - INTERVAL '30 hours'
              AND (event_type = 'mna_acquirer_title_skipped'
                   OR event_type ILIKE '%error%'
                   OR event_type ILIKE '%anomaly%'
                   OR event_type ILIKE '%l2%'
                   OR event_type ILIKE '%drift%'
                   OR event_type ILIKE '%anticipation%'
                   OR event_type ILIKE '%ep_high%'
                   OR event_type ILIKE '%invariant%')
            GROUP BY event_type ORDER BY n DESC
        """)
        if not rows:
            print("  (none)")
        for r in rows:
            print(f"  {r['event_type']:<42} {r['n']:>4}   last={r['last']}")

        # ---- #286 RS leaderboard liquidity ----
        print("\n=== #286 RS leaderboard — latest score_date, top 15 ===")
        cols = {r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_stock_scores'")}
        comp = next((x for x in ("composite", "composite_rank", "composite_score", "comp") if x in cols), None)
        sd = await c.fetchval("SELECT MAX(score_date) FROM mi_stock_scores")
        print(f"  latest score_date={sd}  composite_col={comp}  has_adv20={'adv_20' in cols}")
        if comp and sd:
            adv = ", adv_20" if "adv_20" in cols else ""
            lead = await c.fetch(f"""
                SELECT ticker, {comp} AS comp{adv}
                FROM mi_stock_scores WHERE score_date=$1
                ORDER BY {comp} DESC NULLS LAST LIMIT 15""", sd)
            for r in lead:
                a = r.get("adv_20")
                # latest close for a $-vol estimate
                px = await c.fetchval(
                    "SELECT close FROM mi_daily_closes WHERE ticker=$1 ORDER BY trade_date DESC LIMIT 1",
                    r["ticker"])
                dvol = (px or 0) * (a or 0) if a else None
                dtag = f"${dvol/1e6:7.1f}M" if dvol else "adv?=pass"
                print(f"  {r['ticker']:<6} comp={float(r['comp']):6.1f}  px={px or 0:8.2f}  ~$vol/d={dtag}")

        # ---- EP HIGH alerts today (#1 ORB handoff trigger) ----
        print("\n=== EP HIGH alerts today (drives #1 ORB-handoff verify) ===")
        for tbl, datecol in (("mi_ep_alerts", "alert_date"), ("mi_ep_outcomes", "alert_date")):
            try:
                n = await c.fetchval(
                    f"SELECT count(*) FROM {tbl} WHERE {datecol}=$1 AND score_tier='HIGH'", date(2026, 6, 16))
                print(f"  {tbl}: {n} HIGH today")
            except Exception as e:
                print(f"  {tbl}: n/a ({str(e)[:60]})")


if __name__ == "__main__":
    asyncio.run(main())
