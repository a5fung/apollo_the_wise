"""
One-shot backfill for mi_ep_missed_outcomes.

Usage (inside container):
    docker exec apollo-market python -m scripts.refresh_missed_outcomes 90

Runs the same refresh function the nightly data pull does, but with a longer
default window so the table populates immediately for /missed and the weekly
review on first-deploy day.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from agents.market_intelligence.missed_outcomes import (
    ensure_missed_outcomes_schema, refresh_missed_outcomes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main(window_days: int) -> None:
    await ensure_missed_outcomes_schema()
    summary = await refresh_missed_outcomes(window_days=window_days)
    logger.info(f"refresh_missed_outcomes complete: {summary}")


if __name__ == "__main__":
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    asyncio.run(main(window))
