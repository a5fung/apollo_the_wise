"""#180 — Unified would-have-filled EOD replay (read-only, no DB writes).

Supersedes the two fragmented sims:
  - `broker/gap_through_telemetry.py` (LIVE classifier) — runs intraday over the
    narrow [proposed_at, cancelled_at] window → UNDER-COUNTS would_have_filled
    (misses fills that occur after an early 10:00 cleanup-cancel; the live final
    bar can also still be forming).
  - `scripts/replay_extended_orb_window.py` (scratch SIM v1) — replays over the
    FULL day [9:31, 16:00] → LATE-CUTOFF BIAS (a 3 PM fill is counted as if it
    were a valid ORB entry, which it is not).

This pass fixes BOTH biases by replaying every cancelled ORB candidate on
COMPLETE (settled, EOD) minute bars over the CANONICAL ORB window
[09:31, 10:00] ET — the real fill window (submission 9:31–9:45, 10:00 cleanup
cancels unfilled). The post-10:00 extension is reported as a SEPARATE
sensitivity line, never summed into the headline edge.

Data source: `get_minute_bars` → Polygon consolidated tape = SIP-equivalent
(full-market, all exchanges/TRF — not Alpaca's IEX-only data feed). This IS the
SIP-reconstructed cohort the 6/22 cutover gate requires
(memory: paper_iex_vs_live_sip_gate_adjustment; review:
data_gated_reviews.yaml::alpaca_stop_trigger_reliability).

Classification matches gap_through_telemetry.py exactly so the EOD pass is
CONSISTENT with the live classifier:
  - clean_miss       : trigger (orb_high) never hit in the window
  - would_have_filled: trigger hit AND a later print came back <= limit (fillable)
  - gap_through      : trigger hit but price ran past limit and never returned
  - data_unavailable : no bars

CAVEATS (printed with the result):
  - Minute-bar fill is an APPROXIMATION — a bar low <= limit is a TRADE PRINT,
    not a guaranteed marketable ASK at limit. Fine for a cohort-level edge
    estimate; not a per-trade fill guarantee.
  - Synthetic P&L assumes entry at limit, exit at stop (first bar low<=stop) or
    EOD close. No partials/trailing — a floor-level edge proxy.

Usage (read-only; safe to run via docker exec — no trade-state mutation):
  docker exec apollo-market python scripts/replay_would_have_filled.py [--days N]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from datetime import datetime as _dt
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import get_pool

_ET = ZoneInfo("America/New_York")

CANONICAL_OPEN_HHMM = (9, 31)   # ORB entry window start
CANONICAL_CUTOFF_HHMM = (10, 0)  # 10:00 ET unfilled-entry cleanup
EOD_HHMM = (16, 0)


def _classify(bars_in_window, trigger, limit):
    """Return (classification, fill_t, fill_px) over a complete-bar window.

    Mirrors gap_through_telemetry.classify_orb_cancellation:
      trigger never hit -> clean_miss
      trigger hit, a later LOW <= limit -> would_have_filled (fill at limit)
      trigger hit, price ran past limit (never returned) -> gap_through
    """
    above = [(t, h, l) for t, h, l in bars_in_window if h >= trigger]
    if not above:
        return "clean_miss", None, None
    trigger_first_t = above[0][0]
    after = [(t, h, l) for t, h, l in bars_in_window if t >= trigger_first_t]
    min_low_after = min(l for _, _, l in after)
    if min_low_after <= limit:
        return "would_have_filled", trigger_first_t, limit
    return "gap_through", trigger_first_t, None


def _sim_exit(parsed, fill_t, stop, eod_t):
    """First bar after fill with low<=stop -> stop; else EOD close."""
    for t, _o, _h, l, _c in parsed:
        if t <= fill_t or t > eod_t:
            continue
        if l <= stop:
            return t, stop, "stop"
    eod_bars = [b for b in parsed if b[0] <= eod_t]
    if eod_bars:
        last = eod_bars[-1]
        return last[0], last[4], "eod"
    return None, None, None


async def replay_one(row: dict) -> dict:
    ticker = row["ticker"]
    d = row["alert_date"]
    trigger = float(row["orb_high"] or row["entry_price"] or 0)
    limit = float(row["entry_price"] or row["orb_high"] or 0)
    stop = float(row["stop_price"] or row["orb_low"] or 0)
    shares = int(row["entry_shares"] or 0)
    if not trigger or not limit:
        return {"ticker": ticker, "date": d, "error": "no trigger/limit"}

    bars = await get_minute_bars(ticker, d.isoformat(), d.isoformat())
    if not bars:
        return {"ticker": ticker, "date": d, "classification": "data_unavailable"}

    parsed = sorted(
        (_dt.fromtimestamp(b["t"] / 1000, tz=_ET),
         float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"]))
        for b in bars
    )
    base = _dt.combine(d, _dt.min.time(), tzinfo=_ET)
    open_t = base.replace(hour=CANONICAL_OPEN_HHMM[0], minute=CANONICAL_OPEN_HHMM[1])
    cutoff_t = base.replace(hour=CANONICAL_CUTOFF_HHMM[0], minute=CANONICAL_CUTOFF_HHMM[1])
    eod_t = base.replace(hour=EOD_HHMM[0], minute=EOD_HHMM[1])

    canon = [(t, h, l) for t, _o, h, l, _c in parsed if open_t <= t <= cutoff_t]
    ext = [(t, h, l) for t, _o, h, l, _c in parsed if cutoff_t < t <= eod_t]

    cls, fill_t, fill_px = _classify(canon, trigger, limit)

    out = {
        "ticker": ticker, "date": d, "trigger": trigger, "limit": limit,
        "stop": stop, "shares": shares, "classification": cls,
        "fill_t": fill_t.strftime("%H:%M") if fill_t else None,
        "pnl": None, "exit_reason": None, "extended_only_fill": False,
    }

    if cls == "would_have_filled" and fill_t is not None:
        exit_t, exit_px, reason = _sim_exit(parsed, fill_t, stop, eod_t)
        out["exit_reason"] = reason
        if exit_px is not None:
            out["pnl"] = (exit_px - fill_px) * shares
    else:
        # SENSITIVITY ONLY: would it have filled in the post-10:00 extension?
        ecls, efill_t, efill_px = _classify(ext, trigger, limit)
        if ecls == "would_have_filled" and efill_t is not None:
            out["extended_only_fill"] = True
            exit_t, exit_px, reason = _sim_exit(parsed, efill_t, stop, eod_t)
            if exit_px is not None:
                out["ext_pnl"] = (exit_px - efill_px) * shares
                out["ext_fill_t"] = efill_t.strftime("%H:%M")
    return out


async def main(days: int | None):
    pool = await get_pool()
    where_days = f"AND alert_date >= CURRENT_DATE - INTERVAL '{int(days)} days'" if days else ""
    async with pool.acquire() as conn:
        # Cohort = ORB entry that was PLACED then CANCELLED unfilled. Keyed on
        # status='cancelled' + entry_order_id set (NOT skip_reason text — the
        # cancellation skip_reason is often literally "cancelled", e.g. AVAV/MRVL,
        # which a skip_reason ILIKE on "ORB window unfilled" silently dropped).
        rows = await conn.fetch(f"""
            SELECT ticker, alert_date, orb_high, orb_low, entry_price,
                   stop_price, entry_shares, skip_reason
            FROM mi_live_trades
            WHERE status = 'cancelled'
              AND entry_order_id IS NOT NULL
              AND orb_high IS NOT NULL
              {where_days}
            ORDER BY alert_date DESC
        """)

    print(f"\n#180 unified would-have-filled replay — {len(rows)} cancelled ORB candidates"
          f"{f' (last {days}d)' if days else ' (all)'}\n")
    print("Skip-reason distribution:")
    for sr, n in Counter((r["skip_reason"] or "?")[:48] for r in rows).most_common():
        print(f"  {n:>3}  {sr}")
    print()

    hdr = (f"{'ticker':<7}{'date':<12}{'trig':>8}{'limit':>8}{'stop':>8}"
           f"  {'class':<17}{'fill@':>6}{'exit':>6}{'pnl':>11}{'ext?':>5}")
    print(hdr)
    print("-" * len(hdr))

    counts = Counter()
    canon_pnl = 0.0
    canon_fills = 0
    ext_only_pnl = 0.0
    ext_only_fills = 0
    for r in rows:
        out = await replay_one(dict(r))
        if "error" in out:
            counts["error"] += 1
            continue
        cls = out["classification"]
        counts[cls] += 1
        if cls == "would_have_filled":
            canon_fills += 1
            canon_pnl += out["pnl"] or 0
        if out.get("extended_only_fill"):
            ext_only_fills += 1
            ext_only_pnl += out.get("ext_pnl") or 0
        print(
            f"{out['ticker']:<7}{str(out['date']):<12}{out['trigger']:>8.2f}"
            f"{out['limit']:>8.2f}{out['stop']:>8.2f}  {cls:<17}"
            f"{out['fill_t'] or '—':>6}{out['exit_reason'] or '—':>6}"
            f"{(out['pnl'] if out['pnl'] is not None else 0):>+11.2f}"
            f"{'yes' if out.get('extended_only_fill') else '—':>5}"
        )

    n = len(rows)
    print("\n" + "=" * 60)
    print(f"Cohort N={n}.  Classifications: {dict(counts)}")
    print(f"\nHEADLINE (canonical 9:31–10:00 window, complete bars — cutover-relevant):")
    print(f"  would_have_filled: {canon_fills}")
    print(f"  synthetic settled edge: ${canon_pnl:+,.2f}")
    print(f"\nSENSITIVITY (post-10:00 extension — NOT in headline; late-cutoff bias):")
    print(f"  extended-only fills: {ext_only_fills}")
    print(f"  their synthetic edge: ${ext_only_pnl:+,.2f}")
    print(f"\nCAVEAT: minute-bar fill is an approximation (bar low<=limit is a trade")
    print(f"  print, not a guaranteed ask); P&L assumes entry@limit, exit@stop/EOD,")
    print(f"  no partials. Floor-level edge proxy. N small → directional, not a verdict.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None, help="lookback window (default: all)")
    args = ap.parse_args()
    asyncio.run(main(args.days))
