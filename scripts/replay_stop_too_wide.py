"""Replay last 30d setup:stop_too_wide skips with the new Wilder TR ATR.

For each orb_skipped event with reason setup:stop_too_wide, recompute ATR-14
using the SSoT Wilder TR helper (just shipped). Determine whether the new
1.5x gate would have passed the recorded ORB range. For passers, fetch 5d
max-high % from the baseline close as forward-return proxy.

Skips 9M Day2 rows — different gate (stop distance % vs ORB-vs-ATR).
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta

from agents.market_intelligence.backtester.filters import compute_atr_14
from agents.market_intelligence.db import get_pool


SUMMARY_RE = re.compile(
    r"^ORB\s+(?P<ticker>[A-Z][A-Z0-9.\-]*)\s+—\s+setup:stop_too_wide:\s+ORB range \$(?P<orb_range>[\d.]+)"
)


async def fetch_skip_rows():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT created_at, summary
            FROM mi_audit_log
            WHERE event_type = 'orb_skipped'
              AND summary LIKE 'ORB %setup:stop_too_wide%'
              AND created_at >= NOW() - INTERVAL '30 days'
            ORDER BY created_at ASC
            """
        )


async def fetch_fwd_returns(ticker: str, alert_date: date):
    """Return (baseline_close, max_high_5d, ret_pct_5d, max_high_10d, ret_pct_10d).

    baseline_close = close on alert_date (entry-day close as denominator —
    we're asking "what would 5d max-high have been from here").
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT trade_date, high_price, close
            FROM mi_daily_closes
            WHERE ticker = $1
              AND trade_date >= $2
              AND trade_date <= $2 + INTERVAL '20 days'
              AND high_price IS NOT NULL
            ORDER BY trade_date ASC
            LIMIT 11
            """,
            ticker,
            alert_date,
        )
    if not rows or len(rows) < 2:
        return None, None, None, None, None
    baseline = float(rows[0]["close"])
    if baseline <= 0:
        return None, None, None, None, None
    fwd = rows[1:]  # exclude alert_date itself
    max_5d = max((float(r["high_price"]) for r in fwd[:5]), default=None)
    max_10d = max((float(r["high_price"]) for r in fwd[:10]), default=None)
    ret_5d = (max_5d / baseline - 1) * 100 if max_5d else None
    ret_10d = (max_10d / baseline - 1) * 100 if max_10d else None
    return baseline, max_5d, ret_5d, max_10d, ret_10d


async def main():
    rows = await fetch_skip_rows()
    print(f"Found {len(rows)} stop_too_wide skips in last 30d\n")

    parsed = []
    for r in rows:
        m = SUMMARY_RE.match(r["summary"])
        if not m:
            continue
        parsed.append((r["created_at"].date(), m.group("ticker"), float(m.group("orb_range"))))

    print(f"{'Date':<12} {'Tkr':<7} {'ORB$':>7} {'oldATR':>7} {'newATR':>7} {'pass?':<7} {'5dMax':>7} {'10dMax':>7}")
    print("-" * 80)

    pass_count = 0
    pass_rows = []
    for alert_dt, tkr, orb_range in parsed:
        new_atr, _ = await compute_atr_14(tkr, alert_dt)
        if new_atr is None:
            print(f"{alert_dt}   {tkr:<7} {orb_range:>7.2f}   None    None   N/A     -       -")
            continue

        passes = orb_range <= 1.5 * new_atr
        marker = "PASS" if passes else "skip"

        baseline, max_5d, ret_5d, max_10d, ret_10d = await fetch_fwd_returns(tkr, alert_dt)
        ret_5d_str = f"{ret_5d:+.1f}%" if ret_5d is not None else "—"
        ret_10d_str = f"{ret_10d:+.1f}%" if ret_10d is not None else "—"

        print(
            f"{alert_dt}   {tkr:<7} {orb_range:>7.2f}        — {new_atr:>7.2f} {marker:<7} "
            f"{ret_5d_str:>7} {ret_10d_str:>7}"
        )

        if passes:
            pass_count += 1
            pass_rows.append((alert_dt, tkr, orb_range, new_atr, ret_5d, ret_10d))

    print("\n" + "=" * 80)
    print(f"SUMMARY: {pass_count}/{len(parsed)} would pass under new ATR\n")

    if pass_rows:
        rets_5d = [r[4] for r in pass_rows if r[4] is not None]
        rets_10d = [r[5] for r in pass_rows if r[5] is not None]
        if rets_5d:
            print(f"5d max-high %:  mean {sum(rets_5d)/len(rets_5d):+.1f}%, median {sorted(rets_5d)[len(rets_5d)//2]:+.1f}%")
            print(f"  positive: {sum(1 for r in rets_5d if r > 0)}/{len(rets_5d)}, ≥10%: {sum(1 for r in rets_5d if r >= 10)}/{len(rets_5d)}")
        if rets_10d:
            print(f"10d max-high %: mean {sum(rets_10d)/len(rets_10d):+.1f}%, median {sorted(rets_10d)[len(rets_10d)//2]:+.1f}%")


asyncio.run(main())
