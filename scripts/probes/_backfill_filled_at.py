"""Backfill filled_at + extreme prices for trades whose entry-fill UPDATE
was silently failing due to the AmbiguousParameterError bug (fixed in
commit 96fd7ee, 2026-05-14).

Affected rows since the bug-introducing commit 35c1f6c (2026-05-10):
  - MRAM #120 (5/11)  → already has filled_at (Day-1 reentry path wrote it)
  - KLAR #136 (5/14)  → filled_at NULL
  - CSCO #138 (5/14)  → filled_at NULL
  - CRMD #137 (5/14)  → reconciled separately

This script:
  - For each affected row, queries Alpaca for the entry order's filled_at
    and writes it to mi_live_trades.filled_at.
  - Sets lowest_price_seen / highest_price_seen to entry_price (the value
    they SHOULD have been seeded with at fill time).
"""
import asyncio

from agents.market_intelligence.broker.alpaca_client import get_trading_client
from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
from agents.market_intelligence.db import get_pool


TARGETS = [
    # (trade_id, ticker)
    (136, "KLAR"),
    (138, "CSCO"),
]


async def main() -> None:
    _bootstrap_alpaca_credentials()
    tc = get_trading_client("paper")

    pool = await get_pool()
    async with pool.acquire() as conn:
        for trade_id, ticker in TARGETS:
            row = await conn.fetchrow(
                "SELECT entry_order_id, entry_price FROM mi_live_trades WHERE id=$1",
                trade_id,
            )
            entry_order_id = row["entry_order_id"]
            entry_price = float(row["entry_price"])
            if not entry_order_id:
                print(f"  {ticker} #{trade_id}: no entry_order_id, skipping")
                continue
            order = tc.get_order_by_id(entry_order_id)
            print(f"  {ticker} #{trade_id}: entry filled_at={order.filled_at} avg=${order.filled_avg_price}")
            await conn.execute(
                """
                UPDATE mi_live_trades SET
                    filled_at = COALESCE(filled_at, $2),
                    lowest_price_seen = COALESCE(lowest_price_seen, $3::numeric),
                    highest_price_seen = COALESCE(highest_price_seen, $3::numeric)
                WHERE id = $1
                """,
                trade_id,
                order.filled_at,
                entry_price,
            )
            updated = await conn.fetchrow(
                "SELECT filled_at, lowest_price_seen, highest_price_seen FROM mi_live_trades WHERE id=$1",
                trade_id,
            )
            print(f"    → {dict(updated)}")


if __name__ == "__main__":
    asyncio.run(main())
