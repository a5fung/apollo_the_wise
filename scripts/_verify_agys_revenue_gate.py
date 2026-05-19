"""Live verification: run revenue-growth gate logic against AGYS, see if it
would downgrade today. One-shot diagnostic.

Run: docker exec apollo-market python -m scripts._verify_agys_revenue_gate
"""
import asyncio
from datetime import date

from agents.market_intelligence.fundamentals import compute_fundamental_flags
from agents.market_intelligence.constants import EARNINGS_REVENUE_GATE_MIN_YOY


async def main():
    ticker = "AGYS"
    flags = await compute_fundamental_flags([ticker], date.today())
    if not flags:
        print(f"{ticker}: no fundamentals returned")
        return

    f = flags[0]
    sales_yoy = f.get("sales_yoy_latest")
    eps_yoy = f.get("eps_yoy_latest")
    eps_accel = f.get("eps_accelerating")
    eps_streak = f.get("eps_streak_25pct")

    print(f"=== {ticker} fundamentals ===")
    print(f"  sales_yoy_latest:  {sales_yoy}")
    print(f"  eps_yoy_latest:    {eps_yoy}")
    print(f"  eps_accelerating:  {eps_accel}")
    print(f"  eps_streak_25pct:  {eps_streak}")
    print()
    print(f"=== Gate decision ===")
    print(f"  Threshold (EARNINGS_REVENUE_GATE_MIN_YOY): {EARNINGS_REVENUE_GATE_MIN_YOY*100:.1f}%")

    if sales_yoy is None:
        print(f"  VERDICT: DOWNGRADE — fundamentals unavailable (fail-closed)")
    elif sales_yoy < EARNINGS_REVENUE_GATE_MIN_YOY:
        print(f"  VERDICT: DOWNGRADE — sales_yoy {sales_yoy*100:.2f}% < {EARNINGS_REVENUE_GATE_MIN_YOY*100:.1f}%")
    else:
        print(f"  VERDICT: PASS — sales_yoy {sales_yoy*100:.2f}% >= {EARNINGS_REVENUE_GATE_MIN_YOY*100:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
