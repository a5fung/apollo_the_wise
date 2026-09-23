"""Re-run compute_parabolic_metrics on ERNA with the now-properly-adjusted data.

Verifies that Wave C #3 was incidentally closed by the splits_ingest fix.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from agents.market_intelligence.db import get_pool, get_recent_daily_history
from agents.market_intelligence.parabolic_detector import compute_parabolic_metrics


async def main():
    pool = await get_pool()
    rows = await get_recent_daily_history("ERNA", days=120)
    if not rows:
        print("NO ROWS")
        return
    market_cap = None  # cap-tier defaults to small in compute_parabolic_metrics
    result = compute_parabolic_metrics(rows, market_cap=market_cap)
    print(f"=== ERNA parabolic re-classification (post split-fix) ===")
    for k in (
        "stage", "reason", "score", "prior_move_pct", "base_date",
        "ext_vs_sma20", "ext_vs_sma50", "roc_5d", "roc_20d",
        "days_up_streak", "gap_count_3d", "range_expansion_count_3d",
        "vol_expansion_count_3d", "gapped_today", "climax_volume_flag",
        "pullback_count_20d", "cap_tier",
    ):
        v = result.get(k)
        if isinstance(v, float):
            print(f"  {k:30} = {v:.4f}")
        else:
            print(f"  {k:30} = {v}")


if __name__ == "__main__":
    asyncio.run(main())
