"""#275 — on-demand kill/scale band evaluation (READ-ONLY).

The SSoT's interim "evaluate the bands on request" surface until the Sunday-digest line +
trade-close transition alert are wired. Pre-launch (no live closed trades) this HOLDs below
the 20-trade sample floor — that's the build-ahead-of-data baseline.

    docker exec apollo-market python scripts/evaluate_kill_scale_bands.py        # live (default)
    docker exec apollo-market python scripts/evaluate_kill_scale_bands.py paper  # paper cohort dry-run
"""
import asyncio
import sys

from agents.market_intelligence.kill_scale_bands import (
    assemble_band_inputs, evaluate_kill_scale_bands, get_active_override, format_band_line,
)


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"
    inputs = await assemble_band_inputs(mode)
    verdict = evaluate_kill_scale_bands(
        inputs["realized_rs"], equity_above_start=inputs["equity_above_start"],
        drawdown_tier=inputs["drawdown_tier"])
    override = await get_active_override(mode)
    print(f"\n{'='*70}\n#275 KILL/SCALE BANDS — account_mode={mode}\n{'='*70}")
    print(f"  drawdown tier (persisted): {inputs['drawdown_tier']} · "
          f"equity_above_start={inputs['equity_above_start']}")
    print(format_band_line(verdict, override).replace("*", ""))
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
