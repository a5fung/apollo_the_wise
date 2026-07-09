"""#290 — LATE-ENTRY window backtest (realized-R, not precision).

The dead-zone re-eval (docs/analysis/dead_zone_reeval_2026-07-09.md) showed late-detected HIGHs
have ~precision parity with entered trades (and the 11:00 window beats it). Operator reopened the
entry-path question. Precision was never the R question: a late entry has NO fresh ORB, so it is
FORCED onto a stale-ORB stop (day_low / ATR) — exactly the models #276 W2 study-2 showed collapse
realized-R (orb_low +1.40R → day_low +0.14R). This measures realized-R for the late cohort.

FIRST-CUT = an explicit UPPER BOUND (advisor 7/9):
  - entry fill = the NEXT minute bar's OPEN after the detection minute + 10bps adverse slippage
    (immediate, no missed-breakout penalty — the most favorable honest entry).
  - same-day (day-0) stop checked against the POST-ENTRY intraday low (no lookahead on pre-entry
    dip); if hit → -1R that day.
  - survivors replay forward DAILY bars (mi_daily_closes real lows/closes) through the SAME
    MAGNA53 exit ladder (apply_daily_exit_step) — same management, only the entry timing + stop differ.
  If R doesn't clear the bar even here, late entries definitively don't pay. If it does, this is only
  the optimistic case (the real stop-buy mechanic at a late entry is the required next step).

Caveats (state in the writeup): shares=100 notional (R is size-independent); entered-HIGH control is
a DIFFERENT population (selection bias) — benchmark against #276's R numbers, don't over-read the
control; small N per cell (report N, don't over-read thin cells — the "17% WR" small-N burn).

Run on prod (Polygon + DB):  docker cp then
  docker exec -w /app apollo-market python /tmp/_290_late_entry_backtest.py --csv /tmp/dead_zone_v2.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app")

from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step
from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import get_pool

_ET = ZoneInfo("America/New_York")
SLIPPAGE = 0.001                      # 10bps adverse on the entry fill
SHARES = 100.0                        # notional; realized-R is size-independent
WINDOW_LO = 9 * 60 + 45              # late-detection window starts at 9:45 (the ORB cutoff)
CUTOFFS = [(9*60+55, "9:55"), (10*60, "10:00"), (10*60+30, "10:30"), (11*60, "11:00")]
# Stops honestly available at a LATE entry (no lookahead): low_so_far = the intraday range low
# from the open UP TO the entry minute (the tight structure stop, the late analog of orb_low —
# NOT the full-day low, which isn't known until EOD); plus ATR-based stops off prior-day ranges.
STOP_MODELS = ["low_so_far", "atr_1.0", "atr_1.5"]
# #276 W2 study-2 benchmarks (retained judge-HIGH ENTERED cohort, realized-R by stop model):
BENCH_276 = {"low_so_far": None, "atr_1.0": 0.48, "atr_1.5": 0.27}  # low_so_far ≈ orb_low's +1.40R analog


def _et_minute(epoch_ms: int) -> int:
    t = datetime.fromtimestamp(epoch_ms / 1000, _ET)
    return t.hour * 60 + t.minute


def _entry_and_lows(minute_bars: list, et_min: int):
    """entry = OPEN of the first bar strictly AFTER the detection minute (+slippage).
    low_so_far = lowest low from the open UP TO the entry (the tight structure stop KNOWN at entry).
    day_low_post = lowest low from entry to the close (the day-0 stop-CHECK reference; no pre-entry
    lookahead). Returns (entry, day_low_post, low_so_far)."""
    rth = [b for b in minute_bars if _et_minute(b["t"]) >= 9 * 60 + 30 and b.get("l") is not None]
    pre = [b for b in rth if _et_minute(b["t"]) <= et_min]
    post = [b for b in rth if _et_minute(b["t"]) >= et_min + 1 and b.get("o")]
    if not post or not pre:
        return None, None, None
    entry = post[0]["o"] * (1 + SLIPPAGE)
    day_low_post = min(float(b["l"]) for b in post)
    low_so_far = min(float(b["l"]) for b in pre)
    return entry, day_low_post, low_so_far


async def _atr14(conn, ticker: str, d0: date):
    rows = await conn.fetch(
        """SELECT high_price, low_price, close FROM mi_daily_closes
           WHERE ticker=$1 AND trade_date < $2 AND high_price IS NOT NULL AND low_price IS NOT NULL
           ORDER BY trade_date DESC LIMIT 15""", ticker, d0)
    if len(rows) < 6:
        return None
    rows = list(reversed(rows))
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = float(rows[i]["high_price"]), float(rows[i]["low_price"]), float(rows[i-1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return statistics.mean(trs) if trs else None


async def _fwd_daily(conn, ticker: str, d0: date, ndays: int = 10):
    rows = await conn.fetch(
        """SELECT trade_date, low_price, close FROM mi_daily_closes
           WHERE ticker=$1 AND trade_date > $2 AND low_price IS NOT NULL
           ORDER BY trade_date LIMIT $3""", ticker, d0, ndays)
    return [{"l": float(r["low_price"]), "c": float(r["close"])} for r in rows]


async def prep_row(conn, ticker: str, alert_date: date, et_min: int):
    """Fetch the stop-model-INDEPENDENT inputs ONCE per (ticker,date): entry price, post-entry
    day low, ATR, and the forward daily path. (Avoids re-fetching minute bars per stop model.)"""
    mb = await get_minute_bars(ticker, alert_date.isoformat(), alert_date.isoformat())
    if not mb:
        return None
    entry, day_low_post, low_so_far = _entry_and_lows(mb, et_min)
    if not entry or entry <= 0 or day_low_post is None or low_so_far is None:
        return None
    fwd = await _fwd_daily(conn, ticker, alert_date)
    if not fwd:
        return None
    return {"entry": entry, "day_low_post": day_low_post, "low_so_far": low_so_far,
            "atr": await _atr14(conn, ticker, alert_date), "fwd": fwd, "alert_date": alert_date}


def r_for_stop(p: dict, stop_model: str):
    """Realized-R for one prepped row under one stop model (pure). None if the model can't stop."""
    entry, day_low_post = p["entry"], p["day_low_post"]
    if stop_model == "low_so_far":
        stop = p["low_so_far"]
    else:  # atr_k
        if not p["atr"]:
            return None
        stop = entry - float(stop_model.split("_")[1]) * p["atr"]
    if stop >= entry or stop <= 0:
        return None
    risk = SHARES * (entry - stop)

    if day_low_post <= stop:          # day-0 same-day stop (post-entry low) → -1R
        return -1.0

    alert_date = p["alert_date"]
    state = {"alert_date": alert_date, "remaining_shares": SHARES, "entry_price": entry,
             "hard_stop": stop, "partial_taken": False, "breakeven_active": False,
             "exits": [], "running_closes": []}
    total = None
    for i, b in enumerate(p["fwd"]):   # forward daily bars through the MAGNA53 exit ladder
        step = apply_daily_exit_step(state, {"l": b["l"], "c": b["c"]},
                                     alert_date + timedelta(days=i + 1), integer_partial_shares=True)
        state.update(remaining_shares=step.new_remaining, partial_taken=step.new_partial_taken,
                     breakeven_active=step.new_breakeven_active, exits=step.new_exits,
                     running_closes=step.new_running_closes)
        if step.closed:
            total = step.new_total_pnl
            break
    if total is None:
        total = sum(e.get("pnl", 0) for e in state["exits"]) + (p["fwd"][-1]["c"] - entry) * state["remaining_shares"]
    return total / risk


def _load_cohort(csv_path: str):
    """late_detection HIGH_missed rows, deduped by (ticker,date) keeping the EARLIEST minute
    (mirrors analyze_late_detection_v3), restricted to the 9:45+ late window."""
    keyed = {}
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            if r["cohort"] != "HIGH_missed" or r["mechanism"] != "late_detection":
                continue
            if not r["et_alert_minute"] or date.fromisoformat(r["alert_date"]) < date(2026, 3, 20):
                continue
            em = int(r["et_alert_minute"])
            if em < WINDOW_LO:
                continue
            key = (r["ticker"], r["alert_date"])
            if key not in keyed or em < keyed[key][1]:
                keyed[key] = (r["ticker"], em, date.fromisoformat(r["alert_date"]))
    return list(keyed.values())


def _fmt_cell(rs: list) -> str:
    if not rs:
        return f"{'-':>26}"
    n = len(rs)
    mean = statistics.mean(rs)
    med = statistics.median(rs)
    winp = 100 * sum(1 for r in rs if r > 0) / n
    return f"n={n:>3} mean={mean:+5.2f}R med={med:+5.2f}R win={winp:>4.0f}%"


async def main(csv_path: str):
    cohort = _load_cohort(csv_path)
    print(f"Late-detection HIGH_missed cohort (deduped, 9:45+, post-3/20): {len(cohort)}\n")
    pool = await get_pool()
    # results[stop_model][cutoff_label] = list of R
    results = defaultdict(lambda: defaultdict(list))
    prepped = 0
    async with pool.acquire() as conn:
        for ticker, et_min, alert_date in cohort:
            p = await prep_row(conn, ticker, alert_date, et_min)
            if p is None:
                continue
            prepped += 1
            for stop_model in STOP_MODELS:
                r = r_for_stop(p, stop_model)
                if r is None:
                    continue
                for cutoff_min, label in CUTOFFS:
                    if WINDOW_LO <= et_min < cutoff_min:
                        results[stop_model][label].append(r)
    print(f"Prepped (had bars + forward path): {prepped}/{len(cohort)}\n")

    print("=== LATE-ENTRY realized-R by stop model × ORB-extension cutoff (UPPER BOUND) ===")
    print("(cutoff = late HIGHs detected 9:45 ≤ t < cutoff; would-be entries if the window extended)\n")
    for stop_model in STOP_MODELS:
        bench = BENCH_276.get(stop_model)
        if stop_model == "low_so_far":
            bench_s = "   [tight structure stop — the late analog of #276 orb_low +1.40R]"
        else:
            bench_s = f"   [#276 same-stop bench: {bench:+.2f}R]" if bench else ""
        print(f"  stop={stop_model}{bench_s}")
        for _, label in CUTOFFS:
            print(f"    extend→{label:<6} {_fmt_cell(results[stop_model][label])}")
        print()
    print("#276 W2 study-2 reference (entered cohort): orb_low +1.40R (NOT available to a late "
          "entry — no fresh ORB), day_low +0.14R, atr_1.0 +0.48R, atr_1.5 +0.27R.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="/tmp/dead_zone_v2.csv")
    args = ap.parse_args()
    asyncio.run(main(args.csv))
