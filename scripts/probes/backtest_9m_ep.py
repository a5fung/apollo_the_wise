"""
9M EP Backtest — historical forward returns for stocks that traded >= 9M shares on a single day.

Queries mi_daily_closes for confirmed 9M days (using open_price/close_price/high_price/low_price),
then computes D1 (next close), D5, D10, D21 forward returns. Sugar Baby filter optional.

Usage:
    python scripts/backtest_9m_ep.py [--days 180] [--sugar-only] [--min-price 3.0]

Outputs:
    - Overall hit rate and avg return at each horizon
    - Breakdown by close_in_range_pct bucket (0-50%, 50-75%, 75-100%)
    - Breakdown by volume bucket (<20M, 20-50M, 50M+)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.market_intelligence.db import get_pool


async def run_backtest(days: int, sugar_only: bool, min_price: float) -> None:
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Fetch all 9M days with complete OHLCV
        rows = await conn.fetch("""
            SELECT ticker, trade_date, open_price, high_price, low_price, close AS close_price,
                   volume
            FROM mi_daily_closes
            WHERE volume >= 9000000
              AND close >= $1
              AND open_price IS NOT NULL
              AND high_price IS NOT NULL
              AND low_price IS NOT NULL
              AND trade_date >= CURRENT_DATE - ($2 || ' days')::interval
              AND trade_date <= CURRENT_DATE - INTERVAL '1 day'
            ORDER BY trade_date DESC, volume DESC
        """, min_price, str(days))

        if not rows:
            print("No 9M days found in the lookback window. "
                  "Run nightly ingest first to populate open_price/high_price/low_price.")
            return

        print(f"Found {len(rows)} 9M days across {len(set(r['trade_date'] for r in rows))} dates\n")

        results: list[dict] = []

        for row in rows:
            ticker = row["ticker"]
            signal_date = row["trade_date"]
            o, h, l, c = row["open_price"], row["high_price"], row["low_price"], row["close_price"]
            vol = row["volume"]

            # Sugar Baby criteria
            is_green = c > o
            close_in_range = (c - l) / (h - l) if (h - l) > 0 else 0
            is_sugar_baby = is_green and close_in_range >= 0.75

            if sugar_only and not is_sugar_baby:
                continue

            # Fetch forward closes at D1, D5, D10, D21
            fwd = {}
            for horizon, label in [(1, "d1"), (5, "d5"), (10, "d10"), (21, "d21")]:
                close_row = await conn.fetchrow("""
                    SELECT close FROM mi_daily_closes
                    WHERE ticker = $1
                      AND trade_date > $2
                      AND trade_date <= $2 + ($3 || ' days')::interval
                      AND close > 0
                    ORDER BY trade_date ASC
                    OFFSET $4 LIMIT 1
                """, ticker, signal_date, str(horizon + 5), horizon - 1)
                if close_row:
                    fwd[label] = round((close_row["close"] - c) / c * 100, 2)

            if not fwd:
                continue

            results.append({
                "ticker": ticker,
                "date": signal_date,
                "volume_m": round(vol / 1_000_000, 1),
                "close_in_range": round(close_in_range, 3),
                "is_sugar_baby": is_sugar_baby,
                **fwd,
            })

    if not results:
        print("No results after filtering.")
        return

    _print_report(results, sugar_only)


def _print_report(results: list[dict], sugar_only: bool) -> None:
    label = "Sugar Babies Only" if sugar_only else "All 9M Days"
    print(f"=== 9M EP Backtest — {label} (n={len(results)}) ===\n")

    for horizon in ["d1", "d5", "d10", "d21"]:
        vals = [r[horizon] for r in results if horizon in r]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        hit_rate = sum(1 for v in vals if v > 0) / len(vals) * 100
        print(f"  {horizon.upper()}: avg={avg:+.2f}%  hit_rate={hit_rate:.0f}%  n={len(vals)}")

    print()

    # Breakdown by close_in_range bucket
    print("--- By Close-In-Range ---")
    for lo, hi, bucket in [(0, 0.5, "0-50%"), (0.5, 0.75, "50-75%"), (0.75, 1.01, "75-100% (Sugar)")]:
        sub = [r for r in results if lo <= r["close_in_range"] < hi]
        if not sub:
            continue
        vals = [r["d5"] for r in sub if "d5" in r]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        hit_rate = sum(1 for v in vals if v > 0) / len(vals) * 100
        print(f"  {bucket:<20} n={len(sub):<4} D5 avg={avg:+.2f}%  hit={hit_rate:.0f}%")

    print()

    # Breakdown by volume bucket
    print("--- By Volume ---")
    for lo, hi, bucket in [(9, 20, "9-20M"), (20, 50, "20-50M"), (50, 9999, "50M+")]:
        sub = [r for r in results if lo <= r["volume_m"] < hi]
        if not sub:
            continue
        vals = [r["d5"] for r in sub if "d5" in r]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        hit_rate = sum(1 for v in vals if v > 0) / len(vals) * 100
        print(f"  {bucket:<20} n={len(sub):<4} D5 avg={avg:+.2f}%  hit={hit_rate:.0f}%")

    print()

    # Top 10 by D5 return
    sorted_r = sorted([r for r in results if "d5" in r], key=lambda x: x["d5"], reverse=True)
    print("--- Top 10 by D5 Return ---")
    for r in sorted_r[:10]:
        sb = "🍬" if r["is_sugar_baby"] else "  "
        print(
            f"  {sb} {r['ticker']:<6} {r['date']} "
            f"Vol:{r['volume_m']:.0f}M  D5:{r['d5']:+.1f}%  D10:{r.get('d10', 'N/A'):+.1f}%  "
            f"Range:{int(r['close_in_range']*100)}%"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="9M EP backtest")
    parser.add_argument("--days", type=int, default=180, help="Lookback window in days")
    parser.add_argument("--sugar-only", action="store_true", help="Only sugar babies (top 25% range + green)")
    parser.add_argument("--min-price", type=float, default=3.0, help="Minimum close price")
    args = parser.parse_args()

    asyncio.run(run_backtest(args.days, args.sugar_only, args.min_price))


if __name__ == "__main__":
    main()
