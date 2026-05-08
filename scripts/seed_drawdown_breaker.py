"""Day-1 baseline seed for the drawdown circuit breaker (#39).

One-shot — run once after deploying the drawdown_breaker code so the snapshot
table has a baseline row + the safeguard state row exists. After day 1, the
16:12 ET cron takes over and there's no need to run this again.

Idempotent (UNIQUE on snapshot_date+account_mode), safe to re-run.

Usage:
    docker exec apollo-market python -m scripts.seed_drawdown_breaker
"""
from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    from agents.market_intelligence.broker.drawdown_breaker import (
        snapshot_account_equity,
        recompute_drawdown_state,
    )
    from agents.market_intelligence.constants import current_account_mode

    mode = current_account_mode()
    logger.info(f"Seeding drawdown breaker baseline for account_mode={mode}")

    snap = await snapshot_account_equity(source="baseline")
    if snap is None:
        logger.error("Baseline snapshot failed (Alpaca API issue?). State row not created.")
        return
    logger.info(
        f"Baseline snapshot inserted: equity=${float(snap['equity']):,.2f} "
        f"date={snap['snapshot_date']} source={snap['source']}"
    )

    prev, new, details = await recompute_drawdown_state(mode)
    logger.info(
        f"Drawdown state recompute: {prev} → {new}  "
        f"(dd={details.get('drawdown_pct', 0)*100:.2f}%, "
        f"peak=${details.get('peak', 0):,.2f}, "
        f"sufficient_history={details.get('sufficient_history', False)})"
    )
    logger.info("Seed complete. The 16:12 ET cron will take over from here.")


if __name__ == "__main__":
    asyncio.run(main())
