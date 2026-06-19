"""READ-ONLY: dig the cooldowns_per_day L2 anomaly (16 vs median 3) — which themes/tickers
got revalidated OUT today, with the reason/qualifier, to judge false-removal (#213/#214)."""
import asyncio

from agents.market_intelligence import db


async def main():
    pool = await db.get_pool()
    async with pool.acquire() as c:
        # what columns exist
        cols = await c.fetch("""SELECT column_name FROM information_schema.columns
                                WHERE table_name='mi_validation_cooldowns' ORDER BY ordinal_position""")
        print("cols:", [r["column_name"] for r in cols], "\n")

        print("══ Drill-down: themes with tickers revalidated-out today (UTC) ══")
        rows = await c.fetch("""
            SELECT theme_name, COUNT(*) n
            FROM mi_validation_cooldowns
            WHERE removed_at::date = CURRENT_DATE
            GROUP BY theme_name ORDER BY n DESC LIMIT 20
        """)
        for r in rows:
            print(f"   {r['theme_name']:<40} {r['n']}")

        print("\n══ The actual (theme, ticker, reason) removed today ══")
        rows = await c.fetch("""
            SELECT * FROM mi_validation_cooldowns
            WHERE removed_at::date = CURRENT_DATE
            ORDER BY theme_name, ticker
        """)
        for r in rows:
            d = dict(r)
            reason = d.get("reason") or d.get("removal_reason") or d.get("notes") or ""
            print(f"   {str(d.get('theme_name'))[:34]:<34} {str(d.get('ticker')):<7} {str(reason)[:90]}")

        # Did SNDK / SIMO (the #213 canaries) survive?
        print("\n══ #213 canaries — were SNDK/SIMO removed today? ══")
        rows = await c.fetch("""
            SELECT ticker, theme_name FROM mi_validation_cooldowns
            WHERE removed_at::date = CURRENT_DATE AND ticker IN ('SNDK','SIMO','TSEM')
        """)
        if not rows:
            print("   ✅ none of SNDK/SIMO/TSEM removed today (shield holding)")
        for r in rows:
            print(f"   🔴 {r['ticker']} removed from {r['theme_name']}")


asyncio.run(main())
