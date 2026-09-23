"""One-shot manual partial-exit trigger for IBM trade #167 (2026-05-27).

Today's 4:45 PM ET scheduled job failed at the cancel-new race; partial
methodology window (hold_days=5 forced) was missed. With the
replace_order fix + same-window retry now deployed, retrying now (after
hours) queues the partial market sell for tomorrow's open — the same
outcome as tomorrow's 4:45 PM job would have produced, but with the
methodology intent honored at the next available window instead of the
day after.

CRITICAL: must call _bootstrap_alpaca_credentials BEFORE any
alpaca_client import or use, otherwise the spawned subprocess sees
only the legacy ALPACA_API_KEY env var and Alpaca client fails. This
was the same mistake that caused the 2026-05-27 23:01 ET DB
mass-close incident; the safety guard (#137) prevents the destructive
outcome but the bootstrap is still required for any operation.

Run: docker exec apollo-market python -m scripts._manual_partial_ibm_167
"""
import asyncio
import sys


async def main():
    # Bootstrap creds FIRST (matches agent.py startup ordering).
    from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
    status, fallback = _bootstrap_alpaca_credentials()
    print(f"creds: {status} (fallback={fallback})")

    # Now safe to import + use alpaca_client.
    from agents.market_intelligence.broker.order_manager import execute_partial_exit

    trade_id = 167
    shares = 8

    print(f"Triggering execute_partial_exit({trade_id=}, {shares=}) ...")
    result = await execute_partial_exit(trade_id, shares)
    print(f"Result: {result}")
    if not result:
        print("WARNING: partial returned False; check audit log for partial_exit_aborted")
        sys.exit(1)
    print("OK: partial executed successfully")


if __name__ == "__main__":
    asyncio.run(main())
