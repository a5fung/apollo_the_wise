#!/usr/bin/env python3
"""#548 — what would a CORRECTLY-SEEDED MA trail have done? (EVIDENCE ONLY, read-only.)

THE LINE: replay only. Ships nothing, changes nothing.

The trail was averaging our HOLDING PERIOD instead of the stock's price history, so it could not
exist until ~10 held days. Fixed 2026-08-08 on the operator's ruling ("fix it, it's a bug"). This
answers the question that fix leaves open, and it is the operator's own concern from the same
morning: **does a trail that is live from day one cut the runners short?**

METHOD, deliberately conservative and mirroring `exit_logic` exactly:
  * trail = max(SMA10, SMA20) over the stock's real closes (mi_daily_closes), per EP_TRADING_RULES
    §B4 ("10-SMA when 10 > 20, else 20-SMA" — max() picks that).
  * effective stop = max(hard_stop, trail). The trail can only ever RAISE the stop, so it can
    never exit earlier than the hard stop already would — that is the property that makes the fix
    safe, and modelling it any other way would overstate the trail's bite.
  * exit on the first daily CLOSE below the effective stop (close-only; the exit path sees no
    intraday price).
  * compares against what the trade ACTUALLY did.

Usage: python scripts/probes/_548_seeded_ma_trail_replay.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


TRADES_SQL = """
SELECT t.id, t.ticker, t.alert_date, t.account_mode, t.entry_price, t.hard_stop,
       t.stop_price, t.hold_days, t.total_pnl, t.entry_shares, t.closed_at,
       t.exits
  FROM mi_live_trades t
 WHERE t.status = 'closed' AND t.entry_price IS NOT NULL
 ORDER BY t.alert_date
"""

CLOSES_SQL = """
SELECT trade_date, close
  FROM mi_daily_closes
 WHERE ticker = $1 AND trade_date <= $2
 ORDER BY trade_date
"""


def sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


def trail_of(closes):
    """max(SMA10, SMA20) — exit_logic's `trail_mode='sma'`, faithful to §B4."""
    s10, s20 = sma(closes, 10), sma(closes, 20)
    if s20 is not None:
        return s10 if (s10 is not None and s10 > s20) else s20
    return s10


async def main() -> None:
    from agents.market_intelligence.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        trades = await conn.fetch(TRADES_SQL)
        rows = []
        for t in trades:
            entry = float(t["entry_price"])
            stop = float(t["hard_stop"] or t["stop_price"] or 0)
            if not stop or stop >= entry:
                continue
            risk = entry - stop
            end = t["closed_at"].date() if t["closed_at"] else t["alert_date"]
            hist = await conn.fetch(CLOSES_SQL, t["ticker"], end)
            if not hist:
                continue

            closes, exit_day, exit_px = [], None, None
            for h in hist:
                c = float(h["close"])
                closes.append(c)
                if h["trade_date"] <= t["alert_date"]:
                    continue                      # pre-entry: build history only
                tr = trail_of(closes)
                eff = max(stop, tr) if tr is not None else stop
                if c < eff:                        # close-below-effective-stop
                    exit_day, exit_px = h["trade_date"], eff
                    break

            actual_r = (float(t["total_pnl"] or 0) / (risk * float(t["entry_shares"] or 1)))
            trail_r = ((exit_px - entry) / risk) if exit_px is not None else None
            rows.append({
                "tk": t["ticker"], "mode": t["account_mode"], "hold": t["hold_days"],
                "actual_r": actual_r, "trail_r": trail_r,
                "trail_day": (exit_day - t["alert_date"]).days if exit_day else None,
            })

    print(f"\n{'tkr':<7}{'mode':<7}{'held':>5}{'actual_R':>10}{'seeded-trail_R':>16}"
          f"{'trail fired d+':>16}")
    print("-" * 62)
    for r in rows:
        tr = f"{r['trail_r']:+.2f}" if r["trail_r"] is not None else "  (never)"
        td = str(r["trail_day"]) if r["trail_day"] is not None else "-"
        print(f"{r['tk']:<7}{r['mode']:<7}{r['hold']:>5}{r['actual_r']:>10.2f}{tr:>16}{td:>16}")

    for mode in ("live", "paper"):
        sub = [r for r in rows if r["mode"] == mode]
        if not sub:
            continue
        fired = [r for r in sub if r["trail_r"] is not None]
        print(f"\n{mode}: n={len(sub)}  trail would have fired on {len(fired)}")
        if fired:
            print(f"  mean actual {sum(r['actual_r'] for r in fired)/len(fired):+.2f}R"
                  f"  -> mean seeded-trail {sum(r['trail_r'] for r in fired)/len(fired):+.2f}R")
            better = [r for r in fired if r["trail_r"] > r["actual_r"]]
            worse = [r for r in fired if r["trail_r"] < r["actual_r"]]
            print(f"  better on {len(better)}, worse on {len(worse)}")
            for r in sorted(worse, key=lambda x: x["trail_r"] - x["actual_r"])[:5]:
                print(f"    WORSE  {r['tk']:<6} actual {r['actual_r']:+.2f}R "
                      f"-> trail {r['trail_r']:+.2f}R (fired d+{r['trail_day']})")
    print()


if __name__ == "__main__":
    asyncio.run(main())
