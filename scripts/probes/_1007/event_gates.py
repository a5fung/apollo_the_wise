"""2026-10-07 read-only: have #597's vanish event or #540's broker rejection/cancel fired yet; #505 queue state."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for ev in ("sync_position_gone_unresolved", "entry_order_rejected", "entry_order_canceled_by_broker", "broker_reject",
                   "order_rejected", "theme_parent_pass_ran", "theme_parent_linked"):
            r = await c.fetchrow("""SELECT count(*) n, max(created_at AT TIME ZONE 'America/New_York') last FROM mi_audit_log
                                    WHERE event_type=$1 AND created_at > now() - interval '30 days'""", ev)
            print(ev, dict(r))



asyncio.run(main())
