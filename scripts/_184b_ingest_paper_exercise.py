"""#184(b) #151 PAPER exercise — prove R1 stop-pointer repair end-to-end against REAL paper Alpaca.

Recreates the a41e7c6a false-naked state on the PAPER account and proves order_ingest.R1 heals it:
  1. Place a REAL paper SELL stop for F (stop $1 / limit $0.50 — far below market, never triggers,
     never fills; market-closed-safe). COID via make_client_order_id (mode-bound, registry strategy).
  2. Insert a test 'filled' mi_live_trades row for F with stop_order_id = NULL (DB thinks NAKED).
  3. run_ingest(mode='live_r1') over the REAL broker open_orders + the test row → R1 must repoint
     stop_order_id to the real broker stop. ASSERT the pointer is repaired.
  4. Reset to NULL, run_ingest(mode='dry_run') → ASSERT zero mutation (still NULL).
  5. Cleanup (finally): cancel the paper order + delete the test row.

PAPER only, one share, self-cleaning. Sends 1-2 real 'Ingest R1' Telegrams (the test — ignore them).
Run:  docker exec -w /app apollo-execution python scripts/_184b_ingest_paper_exercise.py
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import StopLimitOrderRequest

from agents.market_intelligence.broker import alpaca_client
from agents.market_intelligence.broker.order_ingest import run_ingest
from agents.market_intelligence.db import get_pool

TICKER = "F"
STRATEGY = "magna53"   # a real registry strategy for the COID only (validate_coid checks EXISTENCE)
SENTINEL_SIGNAL_TYPE = "integration_test"  # the test DB row's signal_type — a DEDICATED sentinel so
                                           # setup/teardown can NEVER clobber/delete a real magna53
                                           # trade (R1 keys on ticker, never the row's signal_type)
MODE = "paper"


async def main() -> int:
    pool = await get_pool()
    coid = alpaca_client.make_client_order_id(MODE, STRATEGY, TICKER)
    client = alpaca_client.get_trading_client(MODE)
    placed_id = None
    trade_id = None
    ok = False
    try:
        # 1. real paper SELL stop, far below market (never triggers, never fills)
        req = StopLimitOrderRequest(symbol=TICKER, qty=1, side=OrderSide.SELL,
                                    time_in_force=TimeInForce.DAY,
                                    stop_price=1.00, limit_price=0.50, client_order_id=coid)
        placed = client.submit_order(req)
        placed_id = str(placed.id)
        print(f"1. placed paper SELL stop id={placed_id} coid={coid}")

        # 2. test 'filled' DB row with stop_order_id = NULL (the false-naked state)
        async with pool.acquire() as conn:
            trade_id = await conn.fetchval(
                """INSERT INTO mi_live_trades (ticker, alert_date, account_mode, signal_type, status,
                       entry_price, entry_shares, remaining_shares, stop_order_id)
                   VALUES ($1, (NOW() AT TIME ZONE 'America/New_York')::date, $2, $3, 'filled',
                           10.0, 1, 1, NULL)
                   ON CONFLICT (ticker, alert_date, account_mode)  -- 3-col since #465
                   DO UPDATE SET stop_order_id = NULL, status = 'filled', account_mode = $2,
                                 signal_type = $3
                   RETURNING id""", TICKER, MODE, SENTINEL_SIGNAL_TYPE)
        print(f"2. test DB row id={trade_id} (stop_order_id=NULL)")

        # 3. R1 live repair over the REAL broker book
        positions = await alpaca_client.get_all_positions(account_mode=MODE)
        open_orders = await alpaca_client.get_open_orders(account_mode=MODE)
        db_row = {"id": trade_id, "ticker": TICKER, "stop_order_id": None}
        n = await run_ingest(MODE, positions, open_orders, [db_row], mode="live_r1")
        async with pool.acquire() as conn:
            repaired = await conn.fetchval(
                "SELECT stop_order_id FROM mi_live_trades WHERE id = $1", trade_id)
        assert repaired == placed_id, f"R1 FAILED: expected {placed_id}, got {repaired!r} (acted={n})"
        print(f"3. ✅ R1 repaired: stop_order_id → {repaired}")

        # 4. dry_run must NOT mutate
        async with pool.acquire() as conn:
            await conn.execute("UPDATE mi_live_trades SET stop_order_id = NULL WHERE id = $1", trade_id)
        await run_ingest(MODE, positions, open_orders,
                         [{"id": trade_id, "ticker": TICKER, "stop_order_id": None}], mode="dry_run")
        async with pool.acquire() as conn:
            after = await conn.fetchval(
                "SELECT stop_order_id FROM mi_live_trades WHERE id = $1", trade_id)
        assert after is None, f"dry_run MUTATED (expected NULL, got {after!r})"
        print("4. ✅ dry_run: zero mutation")
        ok = True
        print("\nPASS — #184b R1 paper exercise (repair-when-live + dry-run-writes-nothing)")
    finally:
        if placed_id:
            try:
                await alpaca_client.cancel_order(placed_id, account_mode=MODE)
                print(f"cleanup: cancelled paper order {placed_id}")
            except Exception as e:
                print(f"cleanup: order cancel non-fatal: {e}")
        if trade_id:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # both mi_live_orders + mi_live_trades DELETEs are guarded (trade-state safety) —
                    # opt in; drop the R1-upserted order row FIRST (FK child), then the trade row.
                    await conn.execute("SET LOCAL mi.allow_trade_delete = 'yes'")
                    await conn.execute("DELETE FROM mi_live_orders WHERE trade_id = $1", trade_id)
                    await conn.execute(
                        "DELETE FROM mi_live_trades WHERE id = $1 AND signal_type = $2 "
                        "AND account_mode = 'paper'", trade_id, SENTINEL_SIGNAL_TYPE)
            print(f"cleanup: deleted test row {trade_id} (+ its ingest-upserted order row)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
