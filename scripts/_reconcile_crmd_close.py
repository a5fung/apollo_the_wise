"""Reconcile CRMD trade row after emergency manual close.

CRMD entered 2026-05-14 09:34:40 ET, entry-fill UPDATE failed
(AmbiguousParameterError). Position became naked. Manual SELL submitted
~11:00 ET, filled 2214 @ $8.01.

This script:
  1. Pulls the manual SELL order details from Alpaca.
  2. Sets CRMD row: status='closed', filled_at=<entry fill time>,
     entry_price=8.36 (broker avg), entry_shares=2214,
     remaining_shares=0, exits=[stop_hit @8.01], total_pnl computed,
     closed_at=NOW().
"""
import asyncio

from agents.market_intelligence.broker.alpaca_client import get_trading_client
from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
from agents.market_intelligence.db import get_pool


MANUAL_SELL_ORDER_ID = "9c1b57d2-7690-459b-8295-613a0b58f3a6"
TRADE_ID = 137


async def main() -> None:
    _bootstrap_alpaca_credentials()
    tc = get_trading_client("paper")

    sell = tc.get_order_by_id(MANUAL_SELL_ORDER_ID)
    print(f"Manual SELL: filled_qty={sell.filled_qty} filled_avg={sell.filled_avg_price} filled_at={sell.filled_at}")

    entry = tc.get_order_by_id("23de8472-2315-44c8-b522-8416e18c3c1a")
    print(f"Entry: filled_qty={entry.filled_qty} filled_avg={entry.filled_avg_price} filled_at={entry.filled_at}")

    entry_price = float(entry.filled_avg_price)
    entry_shares = int(entry.filled_qty)
    exit_price = float(sell.filled_avg_price)
    exit_shares = int(sell.filled_qty)
    pnl = (exit_price - entry_price) * exit_shares

    exit_record = [{
        "time": sell.filled_at.isoformat(),
        "price": exit_price,
        "reason": "manual_emergency_close",
        "shares": exit_shares,
        "pnl": pnl,
        "attempt": 1,
        "order_id": MANUAL_SELL_ORDER_ID,
        "source": "manual_reconcile",
        "note": "Emergency close after WS entry-fill UPDATE failed (AmbiguousParameterError $2 numeric vs double precision). Stop leg auto-canceled by OTO bracket teardown.",
    }]

    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE mi_live_trades SET
                status = 'closed',
                entry_price = $2,
                entry_shares = $3,
                remaining_shares = 0,
                hard_stop = $4,
                stop_price = $4,
                filled_at = $5,
                closed_at = $6,
                exits = $7::jsonb,
                total_pnl = $8,
                lowest_price_seen = $9::numeric,
                highest_price_seen = $10::numeric
            WHERE id = $1
            """,
            TRADE_ID,
            entry_price,
            entry_shares,
            8.45,  # original orb_low
            entry.filled_at,
            sell.filled_at,
            json.dumps(exit_record),
            pnl,
            min(entry_price, exit_price),
            max(entry_price, exit_price),
        )
        row = await conn.fetchrow(
            "SELECT id, ticker, status, entry_price, total_pnl, filled_at, closed_at FROM mi_live_trades WHERE id=$1",
            TRADE_ID,
        )
        print(f"Reconciled: {dict(row)}")


if __name__ == "__main__":
    asyncio.run(main())
