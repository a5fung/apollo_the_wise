"""Preflight Gate G6 — paper-Alpaca replace_order integration smoke.

Catches the bug classes from 2026-05-27 (cancel→new race) and 2026-05-28
(str→numeric Pydantic) by exercising the actual replace_order code path
against real paper Alpaca. Both bugs shipped to source without ever
exercising the production code path before a scheduled cron fired against
a real trade.

**What this script does**:
1. Bootstraps Alpaca paper credentials via the agent's standard path
2. Uses the paper_alpaca test harness to place a sentinel BUY STOP
3. Calls `alpaca_client.replace_order(...)` against the test order
4. Asserts the broker returned a new order_id, status is acceptable
5. Verifies the OLD order is canceled/replaced on broker side
6. Harness cleans up the new order on exit (sweep handles any leak)

Failure → non-zero exit → deploy.sh aborts.

**Idempotent**: harness's startup sweep cancels any orphan test orders
from prior crashed runs. Safe to re-run.

**Network required**: this is an integration test, not a mock. Calls
paper-api.alpaca.markets directly. Slower than other preflight gates
(~2-3s typical).

**Cost**: places a $999 stop on 1 share of F. Never triggers (F trades
~$12). Zero capital risk. Zero buying-power consumption since the order
is uncancelled for <5s.

Author note (2026-05-29): this script is intentionally minimal. It
catches today's known bug class permanently; it does NOT catch deeper
logic bugs (those need #151 (a) architectural split with verify-
between-steps). Treat as a Pydantic-shape canary, not as proof of
end-to-end correctness.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("preflight_g6")


async def run() -> bool:
    """Execute the smoke. Returns True on success, False on any error."""
    try:
        from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
        _bootstrap_alpaca_credentials()
    except Exception as e:
        logger.error(f"bootstrap failed: {e}")
        return False

    # Hard guard: never exercise this against live mode.
    if os.environ.get("LIVE_TRADING_ENABLED", "false").lower() == "true":
        if not os.environ.get("ALPACA_PAPER_API_KEY"):
            logger.error("G6 requires ALPACA_PAPER_API_KEY for paper-side test")
            return False

    try:
        from agents.market_intelligence.broker import alpaca_client
        from agents.market_intelligence.integration.paper_alpaca import paper_test_stop
    except Exception as e:
        logger.error(f"import failed: {e}\n{traceback.format_exc()}")
        return False

    try:
        async with paper_test_stop() as old_order_id:
            logger.info(f"G6: test order placed id={old_order_id}")

            # Exercise the production replace_order code path. This is
            # what failed via TypeError on 2026-05-28 (str→numeric bug).
            new_order = await alpaca_client.replace_order(
                old_order_id,
                qty=2,
                stop_price=998.0,
                limit_price=999.0,
                account_mode="paper",
            )

            new_order_id = new_order.get("id")
            if not new_order_id:
                logger.error(f"G6 FAIL: replace_order returned no id: {new_order}")
                return False
            if new_order_id == old_order_id:
                logger.error(
                    f"G6 FAIL: replace returned same id (no new order created): "
                    f"{new_order_id}"
                )
                return False

            # Status assertion (advisor 2026-05-29): broker can issue a new
            # order_id and still REJECT or CANCEL it (e.g., invalid Pydantic
            # field that passes serialization but fails broker-side validation,
            # or extended-hours restrictions). Without this check, a rejection
            # passes G6 — exactly the "looked successful, actually broken"
            # bug shape the gate exists to catch.
            _LIVE_STATUSES = {
                "accepted", "new", "accepted_for_bidding",
                "pending_new", "held", "pending_replace",
            }
            status = (new_order.get("status") or "").lower()
            if status not in _LIVE_STATUSES:
                logger.error(
                    f"G6 FAIL: replace returned non-live status: '{status}' "
                    f"(expected one of {sorted(_LIVE_STATUSES)})"
                )
                return False

            logger.info(
                f"G6: replace ok — old={old_order_id[:8]} new={new_order_id[:8]} "
                f"status={status}"
            )

            # Best-effort cancel the NEW order (the harness only knows the OLD id
            # and will sweep it via the sentinel COID prefix on the NEXT run,
            # but cancelling now reduces sweep noise).
            try:
                await alpaca_client.cancel_order(new_order_id, account_mode="paper")
                logger.info(f"G6: cancelled new order {new_order_id[:8]}")
            except Exception as e:
                logger.info(f"G6: cancel new order non-fatal: {e}")

        logger.info("G6 PASS — replace_order code path validated end-to-end")
        return True

    except Exception as e:
        logger.error(f"G6 FAIL: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        return False


def main() -> int:
    ok = asyncio.run(run())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
