"""2026-10-06 read-only: #688 — was CEG (trade 409, the first live entry since the 2% switch) sized at
equity x 2% x the regime multiplier?"""
import asyncio, json
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        t = await c.fetchrow("SELECT * FROM mi_live_trades WHERE id = 409")
        keep = {k: v for k, v in dict(t).items() if any(s in k for s in
                ("risk", "share", "entry", "stop", "orb", "size", "regime", "equity", "notional", "status", "created", "filled"))}
        print("trade 409:", keep)
        for r in await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary, 300) s, LEFT(detail, 600) d
                                  FROM mi_audit_log WHERE created_at > now() - interval '12 hours'
                                  AND (summary ILIKE '%CEG%' OR detail ILIKE '%"CEG"%') ORDER BY created_at LIMIT 15"""):
            print(f"{r['t']:%H:%M:%S} {r['event_type']:<30} {r['s']} || {r['d']}")
        print("live trades since 10-03:", [dict(r) for r in await c.fetch(
            "SELECT id, ticker, risk_dollars, entry_shares, created_at FROM mi_live_trades WHERE account_mode='live' AND created_at > '2026-10-03' ORDER BY id")])


asyncio.run(main())
