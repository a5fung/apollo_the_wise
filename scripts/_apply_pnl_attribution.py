"""Apply pnl_attribution schema migration + tag CRMD #137 as bug-attributed.

Idempotent — safe to re-run.
"""
import asyncio
from agents.market_intelligence.db import get_pool


async def main() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "ALTER TABLE mi_live_trades ADD COLUMN IF NOT EXISTS pnl_attribution TEXT"
        )
        result = await conn.fetchrow(
            """
            UPDATE mi_live_trades
            SET pnl_attribution = 'incident_2026_05_14_naked_position'
            WHERE id = 137 AND pnl_attribution IS DISTINCT FROM 'incident_2026_05_14_naked_position'
            RETURNING id, ticker, total_pnl, pnl_attribution
            """
        )
        if result is None:
            print("CRMD #137 already tagged (or row missing).")
            row = await conn.fetchrow(
                "SELECT id, ticker, total_pnl, pnl_attribution FROM mi_live_trades WHERE id=137"
            )
            print(f"Current state: {dict(row) if row else None}")
        else:
            print(f"Tagged: {dict(result)}")


if __name__ == "__main__":
    asyncio.run(main())
