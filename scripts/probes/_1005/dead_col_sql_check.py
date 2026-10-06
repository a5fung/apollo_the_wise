"""2026-10-05 read-only: run the #543 fix's two new SQL statements (timestamp-column lookup + written-since
EXISTS) against prod on the three currently-dead columns' tables, before the branch ships."""
import asyncio
from datetime import datetime, timedelta, timezone
from agents.market_intelligence.db import get_pool

TS = ("updated_at", "created_at", "computed_at", "logged_at")


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        since = datetime.now(timezone.utc) - timedelta(days=1)
        for table in ("mi_anticipation_consolidation", "mi_stock_scores", "mi_live_fill_counterfactuals", "mi_live_trades", "crypto_btc_dominance"):
            present = {r["column_name"] for r in await c.fetch(
                """SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = $1
                      AND column_name::text = ANY($2::text[])
                      AND data_type IN ('timestamp with time zone', 'timestamp without time zone')""", table, list(TS))}
            cols = [x for x in TS if x in present]
            if not cols:
                print(f"{table}: no write-ts column -> next-ET-day rule"); continue
            where = " OR ".join(f'"{x}" > $1::timestamptz' for x in cols)
            ex = await c.fetchval(f'SELECT EXISTS (SELECT 1 FROM "{table}" WHERE {where})', since)
            print(f"{table}: ts={cols} written_in_last_24h={ex}")
        n = await c.fetchval("SELECT count(*) FROM mi_audit_log WHERE event_type='dead_column_suspect'")
        print("existing dead_column_suspect rows:", n)


asyncio.run(main())
