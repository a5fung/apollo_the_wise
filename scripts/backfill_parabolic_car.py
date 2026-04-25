"""
CAR backfill verification for the parabolic-short detector (Stage 1).

Per `~/.claude/plans/shiny-mapping-locket.md`, this script is the gate that
must pass before any infra (scheduler / persistence / Telegram) gets wired
up. Pulls CAR's last 60 sessions of OHLCV from `mi_daily_closes`, runs
`compute_parabolic_metrics()` over a sliding window for each day in the
trailing 30 days, and prints a day-by-day table of stage + every metric.

Verification gates (eyeball after running):
  * Mario's Tuesday-night tweet day (2026-04-21) → stage `anticipation` or `climax`
  * The actual climax day before CAR's first big drop → stage `climax`
  * Days well before the move (e.g. 30+ trading days prior) → stage `unqualified`

If the detector misfires (5+ days early or late), STOP and return to rule
synthesis with the user — don't paper over with infrastructure.

Usage:
    python scripts/backfill_parabolic_car.py
    python scripts/backfill_parabolic_car.py --ticker NVDA --days 45
    python scripts/backfill_parabolic_car.py --market-cap 4000000000
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Optional

from agents.market_intelligence.db import get_recent_daily_history
from agents.market_intelligence.parabolic_detector import (
    _get_or_fetch_market_cap,
    compute_parabolic_metrics,
)


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def _fmt_stage(stage: str) -> str:
    if stage == "climax":
        return f"{RED}climax      {RESET}"
    if stage == "anticipation":
        return f"{YELLOW}anticipation{RESET}"
    return f"{DIM}unqualified {RESET}"


def _fmt_num(v, width: int = 6, fmt: str = ".2f") -> str:
    if v is None:
        return f"{'-':>{width}}"
    return f"{v:>{width}{fmt}}"


def _fmt_int(v, width: int = 3) -> str:
    if v is None:
        return f"{'-':>{width}}"
    return f"{int(v):>{width}d}"


def _fmt_bool(v) -> str:
    if v is None:
        return "-"
    return "Y" if v else "n"


async def _run(ticker: str, history_days: int, scan_days: int, override_cap: Optional[int]) -> int:
    rows = await get_recent_daily_history(ticker, history_days)
    if not rows:
        print(f"{RED}No rows in mi_daily_closes for {ticker}.{RESET}")
        return 1
    print(f"Pulled {len(rows)} sessions for {ticker} "
          f"({rows[0]['trade_date']} → {rows[-1]['trade_date']}).")

    if override_cap is not None:
        market_cap = override_cap
        print(f"Using override market cap: ${market_cap/1e9:.2f}B")
    else:
        market_cap = await _get_or_fetch_market_cap(ticker)
        if market_cap is None:
            print(f"{YELLOW}No market cap available — defaulting to mid-cap thresholds.{RESET}")
        else:
            print(f"Market cap (yfinance, current — note: post-crash): ${market_cap/1e9:.2f}B")
    print()

    header = (
        f"{'date':<11}  {'stage':<12}  "
        f"{'close':>7}  {'prior%':>7}  "
        f"{'sma20×':>6}  {'sma50×':>6}  {'slope':>7}  {'pull20':>6}  "
        f"{'streak':>6}  {'gap3d':>5}  {'rng3d':>5}  {'vol3d':>5}  "
        f"{'gap?':>4}  {'climaxV?':>8}  {'score':>5}  reason"
    )
    print(header)
    print("─" * len(header))

    # Sliding window: for each day in trailing scan_days, run with rows[:i+1]
    # and need at least 50+ sessions of history to compute SMA-50.
    start_idx = max(50, len(rows) - scan_days)
    last_n_per_stage = {"climax": 0, "anticipation": 0, "unqualified": 0}
    for i in range(start_idx, len(rows)):
        window = rows[: i + 1]
        m = compute_parabolic_metrics(window, market_cap=market_cap)
        last_n_per_stage[m["stage"]] = last_n_per_stage.get(m["stage"], 0) + 1
        d = window[-1]
        prior_pct = (m["prior_move_pct"] * 100) if m["prior_move_pct"] is not None else None
        slope = (m["slope_accel"] * 100) if m["slope_accel"] is not None else None
        print(
            f"{str(d['trade_date']):<11}  {_fmt_stage(m['stage'])}  "
            f"{_fmt_num(float(d['close']), 7, '.2f')}  "
            f"{_fmt_num(prior_pct, 6, '.0f') + '%' if prior_pct is not None else _fmt_num(None, 7)}  "
            f"{_fmt_num(m['ext_vs_sma20'], 6, '.2f')}  "
            f"{_fmt_num(m['ext_vs_sma50'], 6, '.2f')}  "
            f"{_fmt_num(slope, 6, '.1f') + '%' if slope is not None else _fmt_num(None, 7)}  "
            f"{_fmt_int(m['pullback_count_20d'], 6)}  "
            f"{_fmt_int(m['days_up_streak'], 6)}  "
            f"{_fmt_int(m['gap_count_3d'], 5)}  "
            f"{_fmt_int(m['range_expansion_count_3d'], 5)}  "
            f"{_fmt_int(m['vol_expansion_count_3d'], 5)}  "
            f"{_fmt_bool(m['gapped_today']):>4}  "
            f"{_fmt_bool(m['climax_volume_flag']):>8}  "
            f"{_fmt_int(m['score'], 5)}  "
            f"{m.get('reason') or ''}"
        )

    print()
    print(f"Stage counts over {len(rows) - start_idx} scanned days:")
    for stage in ("climax", "anticipation", "unqualified"):
        print(f"  {stage:<12}  {last_n_per_stage.get(stage, 0)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--ticker", default="CAR")
    p.add_argument("--days", type=int, default=120,
                   help="History to pull from mi_daily_closes (default 120 — needed for SMA-50 + 30d scan window)")
    p.add_argument("--scan-days", type=int, default=30,
                   help="Trailing days to score with the sliding window (default 30)")
    p.add_argument("--market-cap", type=int, default=None,
                   help="Override market cap in dollars (e.g. 4000000000)")
    args = p.parse_args()
    return asyncio.run(_run(args.ticker, args.days, args.scan_days, args.market_cap))


if __name__ == "__main__":
    sys.exit(main())
