"""
Wick-fill (P22) replay verification.

Self-contained ground-truth check on the wick-fill selection + forward-return
logic against historical data. yfinance OHLCV — no DB dependency, runs locally.

Default case: POET 2026-04-21 (9M wick day) → 2026-04-22 (fill test). The 4/21
session must qualify as a wick candidate (close in [0.50, 0.75) of range +
green body). The 4/22 session must clear the 4/21 high (the wick-fill event).

If POET fails the gate, stop — wick rule needs re-tuning before promoting to
paper. See plan in `~/.claude/plans/shiny-mapping-locket.md`.

Usage:
    python scripts/backfill_wick_replay.py
    python scripts/backfill_wick_replay.py --ticker NVDA --date 2026-03-15
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta


async def _fetch_yf(ticker: str, end_date: str, lookback_days: int = 30) -> list[dict]:
    import yfinance as yf

    def _fetch():
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        # Pad +12 calendar days past end_date so we can measure forward returns.
        far_end = end_dt + timedelta(days=20)
        start_dt = end_dt - timedelta(days=int(lookback_days * 1.6) + 60)
        df = yf.Ticker(ticker).history(
            start=start_dt.isoformat(),
            end=(far_end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
        return df

    df = await asyncio.to_thread(_fetch)
    if df is None or df.empty:
        return []
    out: list[dict] = []
    for ts, row in df.iterrows():
        out.append({
            "trade_date": ts.date(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })
    return out


def _evaluate_wick(bar: dict, prev_close: float, adv20: float) -> dict:
    """Apply the same gates as `get_eod_9m_wick_candidates`.

    Wick candidate := green body + close in [0.50, 0.75) of range + 3× ADV +
    net up vs prev_close >= 3% (matches sugar baby cohort, just lower CIRP).
    """
    rng = bar["high"] - bar["low"]
    cirp = (bar["close"] - bar["low"]) / rng if rng > 0 else 0.0
    green = bar["close"] > bar["open"]
    net_pct = (bar["close"] - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
    vol_ratio = bar["volume"] / adv20 if adv20 > 0 else 0.0
    dollar_vol_m = bar["volume"] * bar["close"] / 1_000_000

    passed = (
        green
        and 0.50 <= cirp < 0.75
        and net_pct >= 3.0
        and vol_ratio >= 3.0
        and dollar_vol_m >= 50.0
        and bar["close"] >= 5.0
    )
    return {
        "close_in_range_pct": cirp,
        "green": green,
        "net_pct_vs_prev_close": net_pct,
        "vol_ratio_vs_adv20": vol_ratio,
        "dollar_vol_m": dollar_vol_m,
        "passed": passed,
    }


def _replay_fill(prior_high: float, anchor_close: float,
                 forward_bars: list[dict]) -> dict:
    """Simulate `wick_tracker.update_forward_returns` over the next 10 sessions."""
    if len(forward_bars) < 10:
        return {"settled": False, "reason": f"only {len(forward_bars)} fwd sessions"}

    sessions = forward_bars[:10]
    filled, fill_date = False, None
    for s in sessions:
        if s["high"] >= prior_high:
            filled = True
            fill_date = s["trade_date"]
            break

    out = {"settled": True, "filled": filled, "fill_date": fill_date}
    for n in (1, 3, 10):
        close_n = sessions[n - 1]["close"]
        out[f"fwd_{n}d_from_close_pct"] = (close_n - anchor_close) / anchor_close * 100
        window_filled = any(s["high"] >= prior_high for s in sessions[:n])
        out[f"fwd_{n}d_from_high_pct"] = (
            (close_n - prior_high) / prior_high * 100 if window_filled and prior_high > 0
            else None
        )
    return out


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", default="POET")
    p.add_argument("--date", default="2026-04-21",
                   help="Wick-day candidate date (YYYY-MM-DD)")
    args = p.parse_args()

    bars = await _fetch_yf(args.ticker, args.date, lookback_days=30)
    if not bars:
        print(f"❌ No data for {args.ticker}")
        return 1

    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    idx = next((i for i, b in enumerate(bars) if b["trade_date"] == target), None)
    if idx is None:
        print(f"❌ {args.ticker} has no bar for {args.date}")
        return 1
    if idx < 21:
        print(f"❌ Need >=20 prior sessions, only {idx} available")
        return 1

    prior_20 = bars[idx - 20:idx]
    adv20 = sum(b["volume"] for b in prior_20) / 20
    prev_close = bars[idx - 1]["close"]
    bar = bars[idx]

    verdict = _evaluate_wick(bar, prev_close, adv20)

    print(f"\n{'='*70}")
    print(f"Wick-day evaluation: {args.ticker} {args.date}")
    print(f"{'='*70}")
    print(f"  open={bar['open']:.2f}  high={bar['high']:.2f}  "
          f"low={bar['low']:.2f}  close={bar['close']:.2f}")
    print(f"  volume={bar['volume']:,}  adv20={adv20:,.0f}")
    print(f"  close_in_range_pct={verdict['close_in_range_pct']:.3f} "
          f"(need [0.50, 0.75))")
    print(f"  green={verdict['green']}")
    print(f"  net_vs_prev_close={verdict['net_pct_vs_prev_close']:+.2f}% (need >=3%)")
    print(f"  vol_ratio={verdict['vol_ratio_vs_adv20']:.2f}x (need >=3x)")
    print(f"  dollar_vol=${verdict['dollar_vol_m']:.1f}M (need >=$50M)")
    print(f"  GATE: {'PASSED' if verdict['passed'] else 'REJECTED'}")

    if not verdict["passed"]:
        print("\nWick rule rejected this candidate. No fill replay.")
        return 1 if args.ticker == "POET" else 0

    forward = bars[idx + 1: idx + 11]
    print(f"\n{'='*70}")
    print(f"Forward sessions ({len(forward)} available, prior high={bar['high']:.2f})")
    print(f"{'='*70}")
    for s in forward:
        broke = "<- BROKE PRIOR HIGH" if s["high"] >= bar["high"] else ""
        print(f"  {s['trade_date']}  high={s['high']:.2f}  close={s['close']:.2f}  {broke}")

    fill = _replay_fill(bar["high"], bar["close"], forward)
    print(f"\n{'='*70}")
    print(f"Forward-return replay (10 sessions from {args.date})")
    print(f"{'='*70}")
    if not fill["settled"]:
        print(f"  PENDING: {fill['reason']}")
        return 0
    print(f"  filled_wick={fill['filled']}  fill_date={fill['fill_date']}")
    for n in (1, 3, 10):
        from_h = fill[f"fwd_{n}d_from_high_pct"]
        from_c = fill[f"fwd_{n}d_from_close_pct"]
        from_h_str = f"{from_h:+.2f}%" if from_h is not None else "n/a"
        print(f"  fwd_{n}d:  from_high={from_h_str:>8}   "
              f"from_close={from_c:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
