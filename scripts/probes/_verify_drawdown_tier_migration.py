"""One-shot: trigger recompute_drawdown_state('paper') to migrate legacy
TRIPPED state to tiered enum + verify today's -6.06% lands in WATCH.

Run: docker exec apollo-market python -m scripts._verify_drawdown_tier_migration
"""
import asyncio

from agents.market_intelligence.broker.drawdown_breaker import (
    recompute_drawdown_state, read_breaker_state, get_tier_multiplier,
)


async def main():
    print("Before recompute:")
    before = await read_breaker_state("paper")
    print(f"  state={before}  multiplier={get_tier_multiplier(before)}")

    print("\nTriggering recompute...")
    prev, new, details = await recompute_drawdown_state("paper")
    print(f"  recompute: prev={prev}  new={new}")
    print(f"  drawdown_pct={details['drawdown_pct']*100:.2f}%")
    print(f"  peak=${details['peak']:,.2f}  current=${details['current']:,.2f}")
    print(f"  sufficient_history={details['sufficient_history']}")

    print("\nAfter recompute:")
    after = await read_breaker_state("paper")
    print(f"  state={after}  multiplier={get_tier_multiplier(after)}")


if __name__ == "__main__":
    asyncio.run(main())
