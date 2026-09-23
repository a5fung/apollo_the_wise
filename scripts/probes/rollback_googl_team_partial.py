"""Roll back today's bogus partial-exit DB state on GOOGL #56 + TEAM #57.

GOOGL: only had today's bogus partial in exits → reset to empty.
TEAM: keep the legitimate 5/01 stop_hit row (re-entry artifact per #181),
      drop today's bogus partial_profit row by order_id.
"""
import asyncio
import json
import os

import asyncpg

BOGUS_GOOGL_ORDER_ID = "82ebdc29-5783-4455-9012-25f99f79b5c2"
BOGUS_TEAM_ORDER_ID = "ce35d7a8-3ff7-486a-b72f-2c2d3d12ca95"


async def main():
    dsn = os.environ.get("DATABASE_URL") or (
        f"postgresql://{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@"
        f"{os.environ.get('POSTGRES_HOST', 'postgres')}:"
        f"{os.environ.get('POSTGRES_PORT', 5432)}/"
        f"{os.environ['POSTGRES_DB']}"
    )
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            # Read current state
            for trade_id in (56, 57):
                row = await conn.fetchrow(
                    "SELECT id, ticker, exits FROM mi_live_trades WHERE id=$1", trade_id
                )
                raw = row["exits"]
                exits = raw
                while isinstance(exits, str):
                    exits = json.loads(exits or "[]")
                if exits is None:
                    exits = []
                print(f"BEFORE #{trade_id} {row['ticker']}: {len(exits)} exits row(s)")

                if trade_id == 56:
                    new_exits = [e for e in exits if e.get("order_id") != BOGUS_GOOGL_ORDER_ID]
                else:
                    new_exits = [e for e in exits if e.get("order_id") != BOGUS_TEAM_ORDER_ID]

                new_total_pnl = sum(float(e.get("pnl") or 0) for e in new_exits)

                await conn.execute(
                    """
                    UPDATE mi_live_trades SET
                      partial_taken=FALSE,
                      breakeven_active=FALSE,
                      exits=$2::jsonb,
                      total_pnl=$3
                    WHERE id=$1
                    """,
                    trade_id, json.dumps(new_exits), new_total_pnl,
                )
                print(f"AFTER  #{trade_id} {row['ticker']}: {len(new_exits)} exits row(s), total_pnl={new_total_pnl:.2f}")

        print("\nVerify:")
        rows = await conn.fetch(
            "SELECT id, ticker, partial_taken, breakeven_active, total_pnl, remaining_shares, exits FROM mi_live_trades WHERE id IN (56, 57) ORDER BY id"
        )
        for r in rows:
            raw = r["exits"]
            exits = raw
            while isinstance(exits, str):
                exits = json.loads(exits or "[]")
            if exits is None:
                exits = []
            print(f"  #{r['id']} {r['ticker']}: partial_taken={r['partial_taken']} breakeven={r['breakeven_active']} pnl={r['total_pnl']:.2f} remaining={r['remaining_shares']} n_exits={len(exits)}")
    finally:
        await conn.close()


asyncio.run(main())
