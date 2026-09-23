#!/usr/bin/env python3
"""
Coverage + bias check for the EP backtest population (see backfill_orb_bars.py
for the WHY). Read-only — no writes. Run BEFORE and AFTER the backfill with
identical logic so the two numbers are comparable.

Population = every (trade_date, ticker) meeting the 9% gap floor since
2026-04-13 (max(gap_pct_open, scanlog_max_gap) >= 9.0), NOT just the subset
that needed backfill — the bias question is about the full population.

Usage (inside apollo-execution, DB-reachable):
    python /tmp/backfill_orb_bars_coverage_check.py /tmp/_bt_population_capture.psv before
    python /tmp/backfill_orb_bars_coverage_check.py /tmp/_bt_population_capture.psv after
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app")

from agents.market_intelligence.db import get_pool  # noqa: E402

ET = ZoneInfo("America/New_York")
GAP_FLOOR = 9.0


def load_full_population(path: str) -> list[dict]:
    """Every row meeting the gap floor, regardless of has_orb_bar — the
    denominator for the bias question, not just the backfill target set."""
    pop = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("|")
            if len(parts) != 13:
                continue
            (trade_date, ticker, _open, prev_close, prev_volume, gap_pct_open,
             scanlog_max_gap, _in_open_seed, _in_scanlog_seed, _has_orb_bar,
             _has_any_bar, _prev_trade_date, _gap_days) = parts

            def to_f(s):
                try:
                    return float(s)
                except ValueError:
                    return None

            g1, g2 = to_f(gap_pct_open), to_f(scanlog_max_gap)
            vals = [v for v in (g1, g2) if v is not None]
            if not vals:
                continue
            gap = max(vals)
            if gap < GAP_FLOOR:
                continue
            d = datetime.strptime(trade_date, "%Y-%m-%d").date()
            pv = to_f(prev_volume)
            pc = to_f(prev_close)
            dollar_vol = (pv * pc) if (pv is not None and pc is not None) else None
            pop.append({"date": d, "ticker": ticker, "gap": gap, "dollar_vol": dollar_vol})
    return pop


async def covered_09_30(conn, pop: list[dict]) -> set:
    tickers, bar_times, lookup = [], [], {}
    for row in pop:
        bt = datetime.combine(row["date"], datetime.min.time().replace(hour=9, minute=30), tzinfo=ET)
        tickers.append(row["ticker"])
        bar_times.append(bt)
        lookup[(row["ticker"], bt)] = (row["date"], row["ticker"])
    rows = await conn.fetch(
        """
        SELECT b.ticker, b.bar_time
        FROM mi_intraday_bars b
        JOIN unnest($1::text[], $2::timestamptz[]) AS q(ticker, bar_time)
          ON b.ticker = q.ticker AND b.bar_time = q.bar_time
        """,
        tickers, bar_times,
    )
    covered = set()
    for r in rows:
        key = (r["ticker"], r["bar_time"])
        if key in lookup:
            covered.add(lookup[key])
    return covered


def quartile_bins(values_with_rows, key):
    """4 equal-count bins by `key`, ascending. Rows with key=None excluded."""
    scored = sorted([r for r in values_with_rows if r.get(key) is not None], key=lambda r: r[key])
    n = len(scored)
    if n == 0:
        return []
    q = n // 4
    bins = []
    for i in range(4):
        lo = i * q
        hi = (i + 1) * q if i < 3 else n
        bins.append(scored[lo:hi])
    return bins


async def main():
    pop_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/_bt_population_capture.psv"
    label = sys.argv[2] if len(sys.argv) > 2 else "check"

    pop = load_full_population(pop_path)
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_rows = await conn.fetchval("SELECT COUNT(*) FROM mi_intraday_bars")
        covered = await covered_09_30(conn, pop)

    n = len(pop)
    n_covered = len(covered)
    print(f"=== {label.upper()} ===")
    print(f"mi_intraday_bars total row count: {total_rows}")
    print(f"population (gap>=9%): {n} ticker-days")
    print(f"covered at 09:30 ET: {n_covered} ({100*n_covered/n:.1f}%)")

    # Liquidity quartiles (dollar volume = prev_volume * prev_close)
    liq_bins = quartile_bins(pop, "dollar_vol")
    print("-- liquidity quartiles (dollar volume, Q1=thinnest..Q4=most liquid) --")
    for i, b in enumerate(liq_bins, 1):
        if not b:
            continue
        cov = sum(1 for r in b if (r["date"], r["ticker"]) in covered)
        lo, hi = b[0]["dollar_vol"], b[-1]["dollar_vol"]
        print(f"  Q{i} n={len(b)} range=${lo:,.0f}..${hi:,.0f} covered={cov} ({100*cov/len(b):.1f}%)")

    # Gap-size quartiles
    gap_bins = quartile_bins(pop, "gap")
    print("-- gap-size quartiles (Q1=smallest gap..Q4=largest) --")
    for i, b in enumerate(gap_bins, 1):
        if not b:
            continue
        cov = sum(1 for r in b if (r["date"], r["ticker"]) in covered)
        lo, hi = b[0]["gap"], b[-1]["gap"]
        print(f"  Q{i} n={len(b)} range={lo:.1f}%..{hi:.1f}% covered={cov} ({100*cov/len(b):.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
