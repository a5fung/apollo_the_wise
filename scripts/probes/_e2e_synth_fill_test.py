"""E2E synthetic fill test — confirms refactored T1.1 entry-fill UPDATE
works end-to-end against real DB with a TEST row, then rolls back.

Verifies:
- Refactored 5-param UPDATE executes cleanly
- status = 'filled' written
- entry_price / entry_shares / remaining_shares / filled_at set correctly
- stop_price / hard_stop UNCHANGED from INSERT value (no KLAR-class clobber)
- stop_order_id set via COALESCE
- lowest/highest_price_seen seeded with filled_price

Run via: docker exec apollo-market python -m scripts._e2e_synth_fill_test
"""
import asyncio
import sys
from agents.market_intelligence.db import get_pool


async def synth_fill_test():
    pool = await get_pool()
    async with pool.acquire() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            test_id = await conn.fetchval("""
                INSERT INTO mi_live_trades
                  (ticker, alert_date, signal_type, account_mode, status,
                   entry_price, orb_high, orb_low, stop_price, hard_stop,
                   atr_14, position_size, risk_dollars, proposed_at,
                   regime, catalyst_quality, ep_score, gap_pct, entry_shares)
                VALUES
                  ('TEST_E2E', CURRENT_DATE, 'magna53', 'paper', 'order_placed',
                   100.0, 100.0, 95.0, 95.0, 95.0,
                   2.0, 10, 50.0, NOW(),
                   'Bull', 'strong', 70, 5.0, 10)
                RETURNING id
            """)
            print(f"test_trade_id={test_id}")

            filled_price = 100.5
            filled_qty = 10
            stop_order_id = "test_stop_id_abc"

            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'filled',
                    entry_price = $2, entry_shares = $3, remaining_shares = $3,
                    filled_at = NOW(),
                    stop_order_id = COALESCE($4, stop_order_id),
                    lowest_price_seen = COALESCE(lowest_price_seen, $5),
                    highest_price_seen = COALESCE(highest_price_seen, $5)
                WHERE id = $1
            """, test_id, filled_price, filled_qty, stop_order_id, filled_price)

            r = await conn.fetchrow(
                "SELECT * FROM mi_live_trades WHERE id = $1", test_id,
            )
            print(f"status={r['status']}")
            print(f"entry_price={r['entry_price']} (expected 100.5)")
            print(f"entry_shares={r['entry_shares']} (expected 10)")
            print(f"remaining_shares={r['remaining_shares']} (expected 10)")
            print(f"stop_price={r['stop_price']} (expected 95.0 — UNCHANGED from INSERT)")
            print(f"hard_stop={r['hard_stop']} (expected 95.0 — UNCHANGED from INSERT)")
            print(f"stop_order_id={r['stop_order_id']}")
            print(f"lowest_price_seen={r['lowest_price_seen']}")
            print(f"highest_price_seen={r['highest_price_seen']}")
            print(f"filled_at_set={r['filled_at'] is not None}")

            assert r["status"] == "filled"
            assert float(r["entry_price"]) == 100.5
            assert r["entry_shares"] == 10
            assert r["remaining_shares"] == 10
            assert float(r["stop_price"]) == 95.0, "KLAR-class regression: stop_price clobbered"
            assert float(r["hard_stop"]) == 95.0, "KLAR-class regression: hard_stop clobbered"
            assert r["stop_order_id"] == "test_stop_id_abc"
            assert float(r["lowest_price_seen"]) == 100.5
            assert float(r["highest_price_seen"]) == 100.5
            print("ASSERTIONS_PASSED")
        finally:
            await tx.rollback()
            print("transaction rolled back cleanly")


if __name__ == "__main__":
    asyncio.run(synth_fill_test())
    print("SYNTH_FILL_E2E_TEST_PASSED")
