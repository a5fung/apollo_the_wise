"""Window-extension impact analysis.

Universe: rows that DID NOT enter under the current 10:00 ET ORB cutoff.
Two sub-buckets:
  (A) cancelled — order placed in 9:31–10:00 window but never crossed
      limit. (skip_reason ILIKE 'ORB window unfilled' or 'EOD unfilled')
  (B) out_of_orb — alert arrived 9:45–9:59 ET too late for current
      window. Order was never placed. (skip_reason ILIKE 'window:out_of_orb%')

For each candidate trade and each cutoff C in {10:00, 11:00, 12:00, 14:00,
16:00}, simulate:
  1. Find first 1-minute bar in [start_t, C] where high >= limit. start_t
     is proposed_at for (A), alert detected_at for (B).
  2. If no cross → P&L = 0 (still cancelled).
  3. If cross → enter at limit, stop preserved at trade.stop_price.
  4. Same-day re-entry (max 2 attempts, mirroring `attempt_day1_reentry`):
     if leg-1 stops out before C, look for next cross in [stop_t, C] →
     leg-2 with same stop. Up to 2 entry attempts per current
     MAX_ENTRY_ATTEMPTS.
  5. Open positions at C are NOT auto-closed — we hold to EOD with the
     same stop, then mark-to-market at the EOD close. (The cutoff is the
     entry deadline, not an exit deadline.)

Aggregate by cutoff: total realised + unrealised P&L delta vs the current
10:00 baseline. Show per-trade detail too so we can spot tail outcomes
that drive the average.
"""
from __future__ import annotations
import asyncio
import re as _re
import sys
from datetime import datetime as _dt, date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import get_pool

_ET = ZoneInfo("America/New_York")
MAX_ATTEMPTS = 2  # mirrors order_manager.MAX_ENTRY_ATTEMPTS
CUTOFFS = [(10, 0), (11, 0), (12, 0), (14, 0), (16, 0)]


def _hhmm(t: _dt) -> int:
    return t.hour * 100 + t.minute


async def _fetch_rth(ticker: str, d: _date) -> list[tuple]:
    bars = await get_minute_bars(ticker, d.isoformat(), d.isoformat())
    out = []
    for b in bars:
        t = _dt.fromtimestamp(b["t"] / 1000, tz=_ET)
        if 931 <= _hhmm(t) <= 1600:
            out.append((t, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
    return sorted(out)


def _parse_detected_time(skip_reason: str, alert_date: _date) -> _dt | None:
    """Extract 'detected HH:MM ET' from a window:out_of_orb skip_reason."""
    m = _re.search(r"detected\s+(\d{1,2}):(\d{2})\s+ET", skip_reason or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return _dt.combine(alert_date, _dt.min.time(), tzinfo=_ET).replace(hour=h, minute=mi)


def simulate_trade(
    rth: list[tuple],
    start_t: _dt,
    cutoff_t: _dt,
    limit: float,
    stop: float,
    shares: int,
) -> tuple[float, str]:
    """Returns (pnl, outcome_label). pnl is total $ across all legs."""
    eod_close = rth[-1][4]
    pnl = 0.0
    cur_t = start_t
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Find next cross of limit in [cur_t, cutoff_t]
        cross = next(((t, h) for t, _o, h, _l, _c in rth
                      if cur_t <= t <= cutoff_t and h >= limit), None)
        if not cross:
            break
        fill_t = cross[0]
        # Find stop hit after fill_t (no cutoff — exits run to EOD)
        stop_hit = next(((t, l) for t, _o, _h, l, _c in rth
                         if t > fill_t and l <= stop), None)
        if stop_hit:
            pnl += (stop - limit) * shares
            cur_t = stop_hit[0]
            if attempt == MAX_ATTEMPTS:
                return pnl, f"{attempt}× stop"
            continue
        # Open to EOD
        pnl += (eod_close - limit) * shares
        return pnl, f"attempt {attempt} → EOD ${eod_close:.2f}"
    return pnl, f"{MAX_ATTEMPTS}× stop, no further re-entry"


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, alert_date, entry_price, stop_price, entry_shares,
                   skip_reason, proposed_at
            FROM mi_live_trades
            WHERE skip_reason ILIKE '%ORB window unfilled%'
               OR skip_reason ILIKE '%EOD unfilled%'
               OR skip_reason ILIKE 'window:out_of_orb%'
            ORDER BY alert_date ASC
        """)
    print(f"\nUniverse: {len(rows)} candidate trades "
          f"(cancelled or window-out-of-orb)\n")

    # For window:out_of_orb rows entry_price/stop_price/entry_shares may be
    # NULL because the order was never built. We need to derive them — pull
    # ORB high/low for that ticker/day from the minute bars, then synthesize
    # a conservative shares estimate. Skip if can't derive.
    per_cutoff = {(c[0], c[1]): {"trades": [], "total": 0.0} for c in CUTOFFS}

    for r in rows:
        ticker = r["ticker"]
        d = r["alert_date"]
        rth = await _fetch_rth(ticker, d)
        if not rth:
            continue

        # Derive limit/stop/shares — for cancelled rows they're already set.
        limit = float(r["entry_price"]) if r["entry_price"] else None
        stop = float(r["stop_price"]) if r["stop_price"] else None
        shares = int(r["entry_shares"] or 0)

        is_out_of_orb = (r["skip_reason"] or "").startswith("window:out_of_orb")
        if is_out_of_orb and (limit is None or stop is None or shares == 0):
            # Synthesize from 9:31–9:45 ORB bars (15-min ORB is the system
            # default for late detections — same as ep_detector behaviour).
            orb_bars = [b for b in rth if 931 <= _hhmm(b[0]) <= 945]
            if not orb_bars:
                continue
            orb_h = max(b[2] for b in orb_bars)
            orb_l = min(b[3] for b in orb_bars)
            limit = orb_h
            stop = orb_l
            # Synthesize shares from $1k risk budget, the system's typical
            # paper-trade unit (real sizing is regime-dependent — this is
            # intentionally conservative for impact analysis).
            risk_per = limit - stop
            if risk_per <= 0:
                continue
            shares = max(1, int(1000 / risk_per))

        if limit is None or stop is None or shares == 0:
            continue

        # Determine start_t (when an order would be live)
        if is_out_of_orb:
            start_t = _parse_detected_time(r["skip_reason"], d)
            if start_t is None:
                continue
        else:
            # Cancelled — proposed_at is when we placed the order
            if r["proposed_at"]:
                start_t = r["proposed_at"].astimezone(_ET)
            else:
                start_t = _dt.combine(d, _dt.min.time(), tzinfo=_ET).replace(hour=9, minute=31)

        for ch, cm in CUTOFFS:
            cutoff_t = _dt.combine(d, _dt.min.time(), tzinfo=_ET).replace(hour=ch, minute=cm)
            if cutoff_t < start_t:
                # Cutoff is before order would even exist — no impact
                pnl, label = 0.0, "cutoff < start"
            else:
                pnl, label = simulate_trade(rth, start_t, cutoff_t, limit, stop, shares)
            per_cutoff[(ch, cm)]["trades"].append({
                "ticker": ticker, "date": d, "pnl": pnl, "label": label,
                "bucket": "out_of_orb" if is_out_of_orb else "cancelled",
            })
            per_cutoff[(ch, cm)]["total"] += pnl

    # ----- summary by cutoff -----
    print(f"{'cutoff':<8} {'trades':>7} {'fills':>6} {'wins':>5} {'losses':>7} "
          f"{'total $':>10} {'avg/trade':>10}")
    print("-" * 60)
    for ch, cm in CUTOFFS:
        bucket = per_cutoff[(ch, cm)]
        ts = bucket["trades"]
        fills = sum(1 for t in ts if t["pnl"] != 0)
        wins = sum(1 for t in ts if t["pnl"] > 0)
        losses = sum(1 for t in ts if t["pnl"] < 0)
        avg = bucket["total"] / len(ts) if ts else 0.0
        print(f"{ch:02d}:{cm:02d}    {len(ts):>7} {fills:>6} {wins:>5} {losses:>7} "
              f"{bucket['total']:>+10.2f} {avg:>+10.2f}")

    # Per-trade matrix
    print("\nPer-trade P&L by cutoff:")
    print(f"{'ticker':<7}{'date':<12}{'bucket':<13}", end="")
    for ch, cm in CUTOFFS:
        print(f"{ch:02d}:{cm:02d}".rjust(11), end="")
    print()
    print("-" * (32 + 11 * len(CUTOFFS)))

    # Build per-(ticker,date) row across cutoffs
    seen = set()
    base = per_cutoff[CUTOFFS[0]]["trades"]
    for ref in base:
        key = (ref["ticker"], ref["date"])
        if key in seen:
            continue
        seen.add(key)
        print(f"{ref['ticker']:<7}{str(ref['date']):<12}{ref['bucket']:<13}", end="")
        for ch, cm in CUTOFFS:
            tr = next((t for t in per_cutoff[(ch, cm)]["trades"]
                       if (t["ticker"], t["date"]) == key), None)
            cell = f"{tr['pnl']:+.0f}" if tr else "—"
            print(cell.rjust(11), end="")
        print()

    print("\nNotes:")
    print("- 'fills' = trades that crossed limit by cutoff. 'trades' = total candidates.")
    print("- Stops preserved at trade.stop_price; max 2 entry attempts per day "
          "(mirrors current re-entry).")
    print("- Open positions at cutoff are HELD to EOD with same stop; cutoff "
          "is the entry deadline, not exit.")
    print("- Out-of-orb rows synthesise shares from a $1k risk-per-trade budget.")


if __name__ == "__main__":
    asyncio.run(main())
