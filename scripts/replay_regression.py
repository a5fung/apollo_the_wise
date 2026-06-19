"""#302 — on-demand P6 replay-regression report (READ-ONLY).

Surfaces the accruing LIVE R-distribution next to the #268b calibration card — the same
section that rides the Sunday weekly review. SURFACES only (no divergence verdict; the
statistic isn't valid at low N — see the module docstring). Pre-launch (no live closed
trades) it reads "comparison begins at cutover" — the build-ahead-of-data baseline.

    docker exec apollo-market python scripts/replay_regression.py        # live (default)
    docker exec apollo-market python scripts/replay_regression.py paper  # paper cohort (informational)
"""
import asyncio
import sys

from agents.market_intelligence.replay_regression import regression_digest_section


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"
    lines = await regression_digest_section(mode)
    print(f"\n{'='*70}\n#302 REPLAY-REGRESSION — account_mode={mode}\n{'='*70}")
    for ln in lines:
        print(ln.replace("*", ""))
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
