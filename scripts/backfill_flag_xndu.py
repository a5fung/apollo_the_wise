"""
XNDU backfill verification for the continuation-flag detector.

Per `~/.claude/plans/shiny-mapping-locket.md`, this script is the gate that
must pass before any infra (scheduler / persistence / Telegram) gets wired
up. Pulls XNDU's last ~120 sessions of OHLCV from yfinance, runs
`compute_flag_metrics()` for each scan_date in the verification window
(2026-04-15 → 2026-05-01), threads `yesterday_stage` + `recent_stages`
through the loop so hysteresis and TRIGGERED-needs-recent-COILED gates
fire correctly, and prints a day-by-day stage trajectory.

Expected XNDU progression:
  4/16          : pivot_high day (high-vol bar)
  4/17–4/22     : WATCH      (base age 1–4)
  4/23–4/26     : TIGHTENING (range contracting)
  4/29–4/30     : COILED     (range AND vol contracted, small bodies)
  5/1           : TRIGGERED  (close > base_high on volume)

If the trajectory matches, the detector is calibrated. Pure compute is
unit-testable without DB.

Usage:
    python scripts/backfill_flag_xndu.py
    python scripts/backfill_flag_xndu.py --ticker XNDU --start 2026-04-15 --end 2026-05-01
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime as _dt, timedelta as _td
from typing import Optional

# Allow running from project root: `python scripts/backfill_flag_xndu.py`
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from agents.market_intelligence.flag_detector import compute_flag_metrics


async def _fetch_yf_history(ticker: str, end_date: str, lookback_days: int = 130) -> list[dict]:
    """Pull OHLCV from yfinance ending on `end_date` (YYYY-MM-DD inclusive)."""
    import yfinance as yf

    def _fetch():
        end_dt = _dt.strptime(end_date, "%Y-%m-%d").date()
        calendar_span = max(int(lookback_days * 1.6) + 30, 200)
        start_dt = end_dt - _td(days=calendar_span)
        df = yf.Ticker(ticker).history(
            start=start_dt.isoformat(),
            end=(end_dt + _td(days=1)).isoformat(),
            auto_adjust=False,
        )
        out = []
        for ts, row in df.iterrows():
            out.append({
                "trade_date":  ts.date(),
                "open_price":  float(row["Open"]),
                "high_price":  float(row["High"]),
                "low_price":   float(row["Low"]),
                "close":       float(row["Close"]),
                "volume":      int(row["Volume"]) if row["Volume"] else 0,
            })
        return out

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch)


GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def _fmt_stage(stage: str) -> str:
    color = {
        "TRIGGERED":   f"{BOLD}{RED}",
        "COILED":      f"{BOLD}{CYAN}",
        "TIGHTENING":  YELLOW,
        "WATCH":       GREEN,
        "INVALIDATED": RED,
        "unqualified": DIM,
    }.get(stage, "")
    return f"{color}{stage:<11}{RESET}"


def _fmt_num(v: Optional[float], width: int = 6, fmt: str = ".2f") -> str:
    if v is None:
        return f"{DIM}{'—':>{width}}{RESET}"
    return f"{v:>{width}{fmt}}"


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", default="XNDU")
    p.add_argument("--start",  default="2026-04-15", help="First scan_date (YYYY-MM-DD)")
    p.add_argument("--end",    default="2026-05-01", help="Last scan_date (YYYY-MM-DD)")
    args = p.parse_args()

    full = await _fetch_yf_history(args.ticker, end_date=args.end, lookback_days=130)
    if not full:
        print(f"{RED}No yfinance data for {args.ticker}{RESET}")
        return 1

    start_dt = _dt.strptime(args.start, "%Y-%m-%d").date()
    end_dt   = _dt.strptime(args.end,   "%Y-%m-%d").date()

    scan_dates = [r["trade_date"] for r in full
                  if start_dt <= r["trade_date"] <= end_dt]
    if not scan_dates:
        print(f"{RED}No trading days in window {args.start}…{args.end}{RESET}")
        return 1

    print(f"\n{BOLD}{args.ticker}{RESET} flag-detector replay  "
          f"{DIM}({len(full)} sessions of yfinance OHLCV; "
          f"{len(scan_dates)} scan dates){RESET}")
    print(f"  first bar: {full[0]['trade_date']}  last bar: {full[-1]['trade_date']}\n")

    header = (
        f"{'date':<12}{'stage':<11}  "
        f"{'pivot':<11}{'age':>4}  "
        f"{'runup':>7}  "
        f"{'rng':>5}  {'vol':>5}  "
        f"{'body':>5}/{'prev':<5}  "
        f"{'close':>7}  {'baseH':>7}  {'bovx':>5}  "
        f"{'reason':<55}"
    )
    print(header)
    print("-" * 150)

    yesterday_stage: Optional[str] = None
    recent_stages: list[str] = []
    prior_pivot_date: Optional[date] = None
    prior_pivot_high: Optional[float] = None

    for sd in scan_dates:
        end_idx = next((i for i, r in enumerate(full) if r["trade_date"] == sd), None)
        if end_idx is None:
            continue
        rows = full[: end_idx + 1]   # ascending, last row = sd
        m = compute_flag_metrics(
            rows,
            ticker=args.ticker,
            yesterday_stage=yesterday_stage,
            recent_stages=recent_stages.copy(),
            prior_pivot_date=prior_pivot_date,
            prior_pivot_high=prior_pivot_high,
        )

        pivot_str = m["pivot_high_date"].strftime("%m-%d") if m["pivot_high_date"] else "—"
        age_str   = str(m["base_age"]) if m["base_age"] is not None else "—"
        runup_pct = f"{m['runup_pct']*100:+.0f}%" if m["runup_pct"] is not None else "—"

        # Diagnostic: would-be breakout volume ratio (today vs 20d trailing).
        vol_today = float(rows[-1]["volume"] or 0)
        win_start = max(0, end_idx - 20)
        v20 = [float(rows[i]["volume"] or 0) for i in range(win_start, end_idx)]
        bovx = (vol_today / (sum(v20) / len(v20))) if v20 and sum(v20) > 0 else None

        print(
            f"{sd.isoformat():<12}{_fmt_stage(m['stage'])}  "
            f"{pivot_str:<11}{age_str:>4}  "
            f"{runup_pct:>7}  "
            f"{_fmt_num(m['range_contraction_ratio'], 5)}  "
            f"{_fmt_num(m['vol_contraction_ratio'],   5)}  "
            f"{_fmt_num(m['last_body_pct'], 5)}/"
            f"{_fmt_num(m['prev_body_pct'], 5)}  "
            f"{_fmt_num(rows[-1]['close'], 7)}  "
            f"{_fmt_num(m['base_high'], 7)}  "
            f"{_fmt_num(bovx, 5)}  "
            f"{(m['reason'] or '')[:53]:<55}"
        )

        # Carry forward stage info for hysteresis + TRIGGERED-recent-COILED gate
        yesterday_stage = m["stage"]
        recent_stages.append(m["stage"])
        if len(recent_stages) > 10:
            recent_stages.pop(0)
        # Stable-anchor: thread today's pivot forward (prod loads from
        # mi_flag_candidates via get_yesterday_flag_pivots; in replay we
        # carry it inline). Skip rows with no pivot (unqualified path).
        if m.get("pivot_high_date") and m.get("pivot_high_price"):
            prior_pivot_date = m["pivot_high_date"]
            prior_pivot_high = float(m["pivot_high_price"])

    print()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
