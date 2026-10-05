"""2026-10-05 read-only: what production did to rehearsal trade #407 (KO, paper) — audit rows naming it."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT created_at AT TIME ZONE 'America/New_York' AS t, event_type, left(summary, 230) AS s "
            "FROM mi_audit_log WHERE created_at >= NOW() - INTERVAL '3 hours' AND "
            "(summary ILIKE '%KO %' OR summary ILIKE '%KO:%' OR summary ILIKE '%#407%' OR detail::text ILIKE '%\"trade_id\": 407%' "
            " OR detail::text ILIKE '%trade_id=407%') ORDER BY created_at")
        orders = await c.fetch(
            "SELECT alpaca_order_id, purpose, order_type, qty, "
            "status, stop_price, limit_price FROM mi_live_orders WHERE trade_id = 407")
        tr = await c.fetchrow("SELECT stop_order_id, stop_price, remaining_shares, partial_taken FROM mi_live_trades WHERE id=407")
    for r in rows:
        print(f"{r['t']:%H:%M:%S} {r['event_type']:<34} {r['s']}")
    print("-- orders rows for 407:")
    for o in orders:
        print(f"  {str(o['alpaca_order_id'])[:8]} {o['purpose']} {o['order_type']} {o['qty']} {o['status']} stop={o['stop_price']} lim={o['limit_price']}")
    print("-- trade row now:", dict(tr))


asyncio.run(main())
