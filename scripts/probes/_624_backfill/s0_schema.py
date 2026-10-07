"""#624 backfill — Stage 0a: schema + split-application state. READ-ONLY. No outcome table read
(mi_lowcap_lane_replays: column NAMES only, from information_schema)."""
import asyncio
from agents.market_intelligence.db import get_pool

TABLES = ("mi_daily_closes", "mi_lowcap_lane_signals", "mi_lowcap_lane_replays", "mi_universe_floor_shadow",
          "mi_ep_scan_log", "mi_splits", "mi_security_types", "mi_audit_log")

async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for t in TABLES:
            cols = await c.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name=$1 ORDER BY ordinal_position", t)
            print(f"=== {t}: " + ", ".join(f"{r['column_name']}:{r['data_type']}" for r in cols))
        print("=== mi_splits applied state by execution vs today")
        for r in await c.fetch("""SELECT (execution_date <= DATE '2026-10-06') executed, adjustment_applied, count(*) n,
                                         min(execution_date) lo, max(execution_date) hi FROM mi_splits GROUP BY 1,2 ORDER BY 1,2"""):
            print(dict(r))
        print("=== executed-but-unapplied splits")
        for r in await c.fetch("""SELECT * FROM mi_splits WHERE execution_date <= DATE '2026-10-06' AND NOT adjustment_applied ORDER BY execution_date"""):
            print(dict(r))
        print("=== mi_daily_closes extent + null volumes")
        print(dict(await c.fetchrow("""SELECT max(trade_date) hi, count(*) FILTER (WHERE volume IS NULL) nullvol,
                                              count(*) FILTER (WHERE close IS NULL) nullclose
                                       FROM mi_daily_closes WHERE trade_date >= '2023-08-01'""")))
        for r in await c.fetch("""SELECT trade_date, count(*) n FROM mi_daily_closes WHERE trade_date >= '2026-09-28' GROUP BY 1 ORDER BY 1"""):
            print(dict(r))

asyncio.run(main())
