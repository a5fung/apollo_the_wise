"""Read-only probe (#149): does yfinance actually return a usable quarterly
revenue YoY for the 8 distinct names that hit `q_rev_yoy_missing`?

Premise-check #2 (advisor 2026-06-05): before building shadow sourcing, measure
the ACTUAL recoverable coverage. If half the names still come back empty, the
fix recovers far less than the headline 8 events.

Read-only external fetch (yfinance) — no DB mutation, no trade-state. Safe via
docker exec. Run: docker exec apollo-market python scripts/_probe_q_rev_yoy_coverage.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.market_intelligence.fundamentals import get_fundamentals

# The 8 distinct (ticker, alert_date) events from q_rev_yoy_missing
TICKERS = ["HSAI", "SNOW", "BBWI", "QFIN", "ESLT", "JOYY", "LION", "RL"]


async def main():
    print(f"\n#149 q_rev_yoy coverage probe — {len(TICKERS)} distinct affected names\n")
    hdr = f"{'ticker':<8}{'latest_q':<12}{'rev_m':>10}{'yoy_pct':>10}  {'usable?':<8}"
    print(hdr)
    print("-" * len(hdr))

    usable = 0
    for t in TICKERS:
        try:
            f = await get_fundamentals(t)
        except Exception as e:
            print(f"{t:<8}{'ERROR':<12}{'—':>10}{'—':>10}  no   ({type(e).__name__}: {e})")
            continue
        qr = f.get("quarterly_revenue") or []
        if not qr:
            print(f"{t:<8}{'—(none)':<12}{'—':>10}{'—':>10}  no")
            continue
        latest = qr[-1]
        yoy = latest.get("yoy_pct")
        rev = latest.get("revenue_m")
        ok = yoy is not None
        if ok:
            usable += 1
        print(f"{t:<8}{str(latest.get('period')):<12}"
              f"{(rev if rev is not None else 0):>10.1f}"
              f"{(yoy if yoy is not None else 0):>10.1f}  {'YES' if ok else 'no':<8}")

    print("\n" + "=" * 50)
    print(f"Usable YoY recovered: {usable}/{len(TICKERS)} "
          f"({100*usable/len(TICKERS):.0f}%)")
    print("(usable = latest quarter has a non-null yoy_pct = prior-year quarter present)")


if __name__ == "__main__":
    asyncio.run(main())
