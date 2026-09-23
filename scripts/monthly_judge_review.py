"""#337 v1 — MONTHLY judge-judgment review CLI (thin wrapper over agents/judge_review.py, which is
the importable home so the monthly_backward_check_sweep can run the same logic).

READ-ONLY, no spend. Run (on the server):
  docker exec apollo-market python /app/scripts/monthly_judge_review.py --days 30
"""
import argparse
import asyncio

# Re-export the pure logic (lives in agents/ so the scheduler can import it without reaching into
# scripts/). Tests import these names from here OR from the agents module — both resolve.
from agents.market_intelligence.judge_review import (  # noqa: F401
    aggregate_judge_review, format_judge_review, recompute_has_direct_source, run,
)


async def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--send", action="store_true", help="also push to Telegram")
    args = ap.parse_args()
    print(await run(args.days, send=args.send))


if __name__ == "__main__":
    asyncio.run(_main())
