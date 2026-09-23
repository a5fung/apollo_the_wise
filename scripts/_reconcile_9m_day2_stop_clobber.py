"""Reconcile 9M Day 2 trades where entry-fill UPDATE clobbered stop_price
with orb_low (2026-05-15 KLAR-class bug).

Bug: trade_stream._process_entry_fill UPDATE was using trade["orb_low"]
for the $4 parameter that wrote both hard_stop=$4 and stop_price=$4.
For MAGNA53 stop_price == orb_low (invisible). For 9M Day 2,
stop_price = prior_day_low ≠ orb_low → corruption.

Affected rows: stop_price overwritten to orb_low on fill. Broker had
the correct stop; only DB display + risk-basis is wrong.

Reconciliation: read the audit `orb_order_placed` for the original
intended stop and write that back to stop_price + hard_stop.

Code fix shipped in same commit prevents future occurrences.
"""
import asyncio
import re

from agents.market_intelligence.db import get_pool, log_audit_event


# (trade_id, ticker, audit_date) — derived from prod query 2026-05-15
AFFECTED = [
    (107, "ARM",  "2026-05-07"),
    (149, "KLAR", "2026-05-15"),
]


async def main() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        for trade_id, ticker, audit_date in AFFECTED:
            # Look up the original orb_order_placed audit for this trade.
            row = await conn.fetchrow(
                """
                SELECT summary FROM mi_audit_log
                WHERE event_type='orb_order_placed'
                  AND summary LIKE $1
                  AND created_at::date = $2::date
                ORDER BY created_at LIMIT 1
                """,
                f"%{ticker}%trade_id={trade_id}%",
                audit_date,
            )
            if not row:
                print(f"  {ticker} #{trade_id}: no orb_order_placed audit found, skipping")
                continue
            # Parse "stop=$NNN.NN" from the summary.
            m = re.search(r"stop=\$([0-9]+\.[0-9]+)", row["summary"])
            if not m:
                print(f"  {ticker} #{trade_id}: couldn't parse stop from audit, skipping")
                continue
            true_stop = float(m.group(1))

            current = await conn.fetchrow(
                "SELECT stop_price, hard_stop, orb_low FROM mi_live_trades WHERE id=$1",
                trade_id,
            )
            print(f"  {ticker} #{trade_id}: audit stop=${true_stop}, "
                  f"DB stop_price=${current['stop_price']}, orb_low=${current['orb_low']}")
            if abs(float(current["stop_price"]) - true_stop) < 0.01:
                print(f"    → already correct, skipping")
                continue

            await conn.execute(
                """
                UPDATE mi_live_trades SET
                    stop_price = $2,
                    hard_stop = $2
                WHERE id = $1
                """,
                trade_id,
                true_stop,
            )
            await log_audit_event(
                "manual_reconcile_9m_day2_stop_clobber",
                f"{ticker} #{trade_id}: stop_price/hard_stop reverted "
                f"from ${current['stop_price']:.2f} (orb_low clobber) "
                f"to ${true_stop:.2f} (audit-confirmed prior_day_low)",
            )
            print(f"    → reconciled to ${true_stop}")


if __name__ == "__main__":
    asyncio.run(main())
