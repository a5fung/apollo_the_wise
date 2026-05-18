"""E2E synthetic test — Gate 5 A naked-position remediation.

Verifies `_process_entry_fill`'s exception handler:
- Catches DB UPDATE failures
- Submits fallback stop-market at trade["orb_low"]
- Emits `naked_position_remediation_fired` audit event
- Re-raises original error

Method:
1. Creates a test trade row in mi_live_trades (rolled back after test)
2. Monkey-patches the entry-fill UPDATE to raise AmbiguousParameterError
   (simulating the CRMD class bug)
3. Monkey-patches alpaca.place_stop_order to return a fake order
4. Calls _process_entry_fill
5. Asserts:
   - Exception was raised (re-raise after remediation)
   - naked_position_remediation_fired audit event written to mi_audit_log
   - Audit event detail names "GATE5A_E2E_TEST" marker

Audit event persists (log_audit_event uses its own pool connection,
outside the test's transaction); test trade row rolls back.

Closes the data-gated review predicate for crmd_naked_position_postmortem_2026_05_14.

Run via: docker exec apollo-market python -m scripts._e2e_gate5a_naked_remediation_test
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import asyncpg

from agents.market_intelligence.db import get_pool


async def synth_gate5a_test():
    pool = await get_pool()

    # 1. Get baseline audit count
    async with pool.acquire() as conn:
        baseline = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_audit_log "
            "WHERE event_type = 'naked_position_remediation_fired'"
        )
    print(f"baseline_naked_remediation_count={baseline}")

    # 2. Create test trade row (will be rolled back; audit row persists in separate conn)
    async with pool.acquire() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            test_id = await conn.fetchval("""
                INSERT INTO mi_live_trades
                  (ticker, alert_date, signal_type, account_mode, status,
                   entry_price, orb_high, orb_low, stop_price, hard_stop,
                   atr_14, position_size, risk_dollars, proposed_at,
                   regime, catalyst_quality, ep_score, gap_pct, entry_shares,
                   entry_order_id)
                VALUES
                  ('GATE5ATEST', CURRENT_DATE, 'magna53', 'paper', 'order_placed',
                   100.0, 100.0, 95.0, 95.0, 95.0,
                   2.0, 10, 50.0, NOW(),
                   'Bull', 'strong', 70, 5.0, 10,
                   'gate5a_test_entry_order_id')
                RETURNING id
            """)
            print(f"test_trade_id={test_id}")

            # 3. Set up the synthetic test:
            #    - Patch conn.execute to raise AmbiguousParameterError when
            #      the entry-fill UPDATE runs.
            #    - Patch alpaca.place_stop_order to return a fake order.

            from agents.market_intelligence.broker import trade_stream

            # Build a mock order object matching what TradingStream gives us
            class MockOrder:
                def __init__(self):
                    self.id = "gate5a_test_order_id"
                    self.symbol = "GATE5ATEST"
                    self.filled_qty = "10"
                    self.filled_avg_price = "100.5"
                    self.legs = None

            # Fake stop placement — returns dict with `id` key
            async def fake_place_stop_order(ticker, qty, stop_price, account_mode=None):
                print(f"fake_place_stop_order: {ticker} qty={qty} stop=${stop_price}")
                return {"id": f"gate5a_test_fallback_stop_{ticker}", "status": "accepted"}

            # Patch alpaca module + send_telegram to no-op
            async def noop_telegram(*args, **kwargs):
                print(f"(telegram suppressed for test)")
                return True

            # Build the trade dict that _process_entry_fill expects
            trade_dict = {
                "id": test_id,
                "ticker": "GATE5ATEST",
                "entry_shares": 10,
                "orb_low": 95.0,
                "stop_price": 95.0,
                "entry_attempt": 1,
                "account_mode": "paper",
            }

            # Patch the alpaca module + telegram
            with patch.object(trade_stream.alpaca, "place_stop_order", new=fake_place_stop_order), \
                 patch.object(trade_stream, "send_telegram_message", new=noop_telegram):

                # Force the entry-fill UPDATE to raise AmbiguousParameterError.
                # Pool.acquire() returns a connection; we monkey-patch its
                # execute method for THIS test only.
                original_acquire = pool.acquire

                class FailingConnWrapper:
                    """Wraps a real pool connection but raises on execute()
                    for the entry-fill UPDATE shape."""
                    def __init__(self, real_conn):
                        self._real_conn = real_conn
                        self._update_call_count = 0
                    async def execute(self, query, *args):
                        # Raise on the first UPDATE matching the entry-fill shape
                        if "UPDATE mi_live_trades" in query and "entry_price" in query:
                            self._update_call_count += 1
                            if self._update_call_count == 1:
                                raise asyncpg.exceptions.AmbiguousParameterError(
                                    "GATE5A_E2E_TEST: synthetic injection — verifying "
                                    "naked-position remediation path fires"
                                )
                        return await self._real_conn.execute(query, *args)
                    def __getattr__(self, name):
                        return getattr(self._real_conn, name)

                class FailingPoolWrapper:
                    """Returns FailingConnWrapper for context manager."""
                    def __init__(self, real_pool):
                        self._real_pool = real_pool
                    def acquire(self):
                        return _FailingAcquireCtx(self._real_pool.acquire())

                class _FailingAcquireCtx:
                    def __init__(self, ctx):
                        self._ctx = ctx
                    async def __aenter__(self):
                        real_conn = await self._ctx.__aenter__()
                        return FailingConnWrapper(real_conn)
                    async def __aexit__(self, exc_type, exc, tb):
                        return await self._ctx.__aexit__(exc_type, exc, tb)

                wrapped_pool = FailingPoolWrapper(pool)

                # Call _process_entry_fill — expecting it to:
                # 1. UPDATE raises AmbiguousParameterError
                # 2. except branch submits fake fallback stop
                # 3. log_audit_event writes naked_position_remediation_fired
                # 4. Re-raises original error
                raised = False
                try:
                    await trade_stream._process_entry_fill(
                        trade_dict, MockOrder(), wrapped_pool, "paper",
                    )
                except asyncpg.exceptions.AmbiguousParameterError as e:
                    raised = True
                    print(f"original error re-raised as expected: {type(e).__name__}")
                except Exception as e:
                    print(f"UNEXPECTED exception type: {type(e).__name__}: {e}")
                    raise

                assert raised, "Expected AmbiguousParameterError to be re-raised after remediation"

        finally:
            await tx.rollback()
            print("test trade row rolled back")

    # 4. Verify audit event was written (in a separate connection)
    async with pool.acquire() as conn:
        new_count = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_audit_log "
            "WHERE event_type = 'naked_position_remediation_fired'"
        )
        latest = await conn.fetchrow(
            "SELECT created_at, summary, detail FROM mi_audit_log "
            "WHERE event_type = 'naked_position_remediation_fired' "
            "ORDER BY created_at DESC LIMIT 1"
        )

    print(f"post_test_naked_remediation_count={new_count}")
    print(f"delta={new_count - baseline}")

    assert new_count == baseline + 1, (
        f"Expected audit_log count to increment by 1; got delta={new_count - baseline}"
    )
    assert latest is not None, "No audit_log row found"
    detail = json.loads(latest["detail"]) if latest["detail"] else {}
    assert "GATE5A_E2E_TEST" in (detail.get("db_error", "") + str(latest["summary"])), (
        f"Audit event detail doesn't reference GATE5A_E2E_TEST marker: {latest}"
    )

    print(f"audit_event_summary={latest['summary']}")
    print(f"audit_event_detail_db_error={detail.get('db_error', '<missing>')}")
    print("GATE5A_E2E_TEST_PASSED")


if __name__ == "__main__":
    asyncio.run(synth_gate5a_test())
