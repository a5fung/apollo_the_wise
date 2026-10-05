"""#482 verify (2026-10-05, read-only): which arms each recent trade has, and the trade's state."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for tid in (382, 396, 400, 401, 404):
            t = await c.fetchrow("SELECT id, ticker, status, account_mode, filled_at::date AS f, "
                                 "closed_at::date AS c FROM mi_live_trades WHERE id = $1", tid)
            a = await c.fetch("SELECT arm, outcome FROM mi_live_fill_counterfactuals WHERE trade_id = $1 "
                              "ORDER BY arm", tid)
            print(dict(t) if t else tid, [(x["arm"], x["outcome"]) for x in a])
        errs = await c.fetch("SELECT created_at::date d, left(summary, 180) s FROM mi_audit_log "
                             "WHERE event_type ILIKE '%counterfactual%' AND created_at >= NOW() - INTERVAL '14 days' "
                             "ORDER BY created_at DESC LIMIT 8")
        for e in errs:
            print(" ", e["d"], e["s"])


asyncio.run(main())
