"""Replay ORB-unfilled cancellations under an extended entry window.

For each cancelled trade with skip_reason ILIKE 'ORB window unfilled' or
'EOD unfilled', fetch the full-day minute bars, find the first post-9:31
ET print where high >= limit (= original ORB-high stop-limit trigger),
and simulate:
  - entry at `limit` at fill_time
  - exit = first bar after entry where low <= stop_price (stop hit)
           or EOD close if stop never hit
  - synthetic P&L vs the cancelled outcome ($0)

Read-only. Pure analysis — does not write to any DB.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime as _dt, timedelta as _td
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import get_pool

_ET = ZoneInfo("America/New_York")

ORB_WINDOW_END_HHMM = (10, 0)  # current cutoff


async def replay_one(row: dict) -> dict:
    ticker = row["ticker"]
    d = row["alert_date"]
    limit = float(row["entry_price"])
    stop = float(row["stop_price"])
    shares = int(row["entry_shares"] or 0)
    bars = await get_minute_bars(ticker, d.isoformat(), d.isoformat())
    if not bars:
        return {"ticker": ticker, "date": d, "error": "no bars"}

    parsed = []
    for b in bars:
        t = _dt.fromtimestamp(b["t"] / 1000, tz=_ET)
        parsed.append((t, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
    parsed.sort()

    # Original ORB window: 09:31:00 -> 10:00:00 ET. Anything in this range
    # would have filled under current logic (and we know it didn't, hence
    # the cancel).
    open_t = _dt.combine(d, _dt.min.time(), tzinfo=_ET).replace(hour=9, minute=31)
    cur_cutoff = open_t.replace(hour=ORB_WINDOW_END_HHMM[0], minute=ORB_WINDOW_END_HHMM[1])
    eod = open_t.replace(hour=16, minute=0)

    fill_t = None
    fill_px = None
    for t, _o, h, _l, _c in parsed:
        if t < open_t or t > eod:
            continue
        if h >= limit:
            fill_t = t
            fill_px = limit  # stop-limit BUY fills at limit (best case)
            break

    if fill_t is None:
        return {
            "ticker": ticker, "date": d, "limit": limit, "stop": stop,
            "would_fill": False, "max_high_eod": max(b[2] for b in parsed),
        }

    # Simulate exit: stop hit at first bar after entry with low <= stop;
    # otherwise close at EOD close (last bar at/before 16:00).
    exit_t = None
    exit_px = None
    exit_reason = None
    for t, _o, _h, l, _c in parsed:
        if t <= fill_t or t > eod:
            continue
        if l <= stop:
            exit_t = t
            exit_px = stop  # stop-limit SELL fills at stop (or worse, but assume at stop)
            exit_reason = "stop"
            break

    if exit_t is None:
        # EOD close
        eod_bars = [b for b in parsed if b[0] <= eod]
        if eod_bars:
            last = eod_bars[-1]
            exit_t = last[0]
            exit_px = last[4]
            exit_reason = "eod"

    pnl = (exit_px - fill_px) * shares if (fill_px and exit_px) else None
    return {
        "ticker": ticker,
        "date": d,
        "limit": limit,
        "stop": stop,
        "shares": shares,
        "would_fill": True,
        "fill_t": fill_t.strftime("%H:%M"),
        "fill_px": fill_px,
        "exit_t": exit_t.strftime("%H:%M") if exit_t else None,
        "exit_px": exit_px,
        "exit_reason": exit_reason,
        "pnl": pnl,
        "in_orig_window": fill_t <= cur_cutoff,
    }


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, alert_date, orb_high, orb_low, entry_price,
                   stop_price, entry_shares
            FROM mi_live_trades
            WHERE skip_reason ILIKE '%ORB window unfilled%'
               OR skip_reason ILIKE '%EOD unfilled%'
            ORDER BY alert_date DESC
        """)

    print(f"\nReplaying {len(rows)} cancelled rows under extended ORB window:\n")
    print(f"{'ticker':<7} {'date':<12} {'limit':>8} {'stop':>8} "
          f"{'fill@':>7} {'fill$':>8} {'exit@':>7} {'exit$':>8} "
          f"{'reason':<6} {'pnl':>10} {'orig?':<5}")
    print("-" * 100)

    total_pnl = 0.0
    fill_in_orig = 0
    fill_extended = 0
    no_fill = 0
    for r in rows:
        out = await replay_one(dict(r))
        if "error" in out:
            print(f"{out['ticker']:<7} {str(out['date']):<12}  ERROR {out['error']}")
            continue
        if not out["would_fill"]:
            no_fill += 1
            print(f"{out['ticker']:<7} {str(out['date']):<12} "
                  f"{out['limit']:>8.2f} {out['stop']:>8.2f}  "
                  f"NO FILL all day (max high {out['max_high_eod']:.2f})")
            continue
        if out["in_orig_window"]:
            fill_in_orig += 1
        else:
            fill_extended += 1
        total_pnl += out["pnl"] or 0
        print(
            f"{out['ticker']:<7} {str(out['date']):<12} "
            f"{out['limit']:>8.2f} {out['stop']:>8.2f} "
            f"{out['fill_t']:>7} {out['fill_px']:>8.2f} "
            f"{out['exit_t'] or '—':>7} {(out['exit_px'] or 0):>8.2f} "
            f"{out['exit_reason'] or '—':<6} "
            f"{out['pnl'] or 0:>+10.2f} "
            f"{'yes' if out['in_orig_window'] else 'no':<5}"
        )

    print()
    print(f"Summary: {fill_in_orig} would have filled in original 9:31-10:00 window "
          f"(suggests current cancel logic / cron timing slip), "
          f"{fill_extended} would have filled later, {no_fill} never filled.")
    print(f"Synthetic P&L of extended-window fills: ${total_pnl:+,.2f}")


if __name__ == "__main__":
    asyncio.run(main())
