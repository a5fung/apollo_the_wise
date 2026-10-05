"""2026-10-05 read-only: how energy themes group today — ecosystem (mi_theme_ecosystems) and parent theme
(mi_themes.parent_theme) for every live board theme in E-ENER, plus the three cycling cohorts."""
import asyncio
from agents.market_intelligence.db import get_pool, get_active_themes


async def main():
    pool = await get_pool()
    board = await get_active_themes(stale_after_days=7)
    async with pool.acquire() as c:
        eco = {r["theme_name"]: (r["e_code"], r["method"]) for r in await c.fetch(
            "SELECT theme_name, e_code, method FROM mi_theme_ecosystems")}
    names = {"Appalachian Natural Gas Producers", "Offshore Drilling Rig Contractors",
             "Regulated Natural Gas Distribution Utilities", "Appalachian & Natural Gas-Weighted E&P Laggards"}
    print("== live board themes in E-ENER (name | stage | members | parent | ecosystem method)")
    for t in board:
        e = eco.get(t["name"])
        if e and e[0] == "E-ENER":
            print(f"  {t['name']} | {t['stage']} | {len(t['tickers'] or [])} | parent={t.get('parent_theme')} | {e[1]}")
    print("== the three cycling cohorts' ecosystem rows")
    for n in sorted(names):
        print(f"  {n}: {eco.get(n)}")


asyncio.run(main())
