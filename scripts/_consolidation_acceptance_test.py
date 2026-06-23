"""Acceptance test for the consolidation-detector fix — operator-labeled, LIVE data.

Gate (operator 2026-06-22): ADMIT {STM,FPS,QTTB,DELL} (real runup -> base setups),
REJECT {BTU,UFO,DRUG,PTGX} (declines / no contraction — they fired entries = the bug).

Runs the PURE detector (anticipation.py) against the committed live-bar fixture, as-of
each ticker's latest bar. Structural, not name-hardcoded: a ticker passes on the
detector's own runup/anchor/entry behavior, not a lookup table.

  GOOD  pass  := admitted to the universe (evaluate_consolidation not None, real runup)
  GARBAGE pass := NO entry fires (anticipate or confirm)

Run:  PYTHONIOENCODING=utf-8 python scripts/_consolidation_acceptance_test.py
"""
import sys
from collections import defaultdict
from agents.market_intelligence import anticipation as de

GOOD = {"STM", "FPS", "QTTB", "DELL"}
GARBAGE = {"BTU", "UFO", "DRUG", "PTGX"}
FIXTURE = "tests/fixtures/consolidation_acceptance_bars.psv"


def load_bars():
    by = defaultdict(list)
    with open(FIXTURE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            tk, d, o, h, lo, c, v = line.split("|")
            by[tk].append({"trade_date": d, "open_price": float(o), "high_price": float(h),
                           "low_price": float(lo), "close": float(c), "volume": float(v)})
    return {tk: de.db_rows_to_bars(rows) for tk, rows in by.items()}


def current_anchor(bars):
    """BROKEN (live): anchor = EARLIEST date of MAX close in last 15 sessions
    (db.get_anticipation_universe `pk` CTE) — re-pins to recent highs / inside the base."""
    last15 = bars[-15:]
    mx = max(b["c"] for b in last15)
    for b in last15:
        if b["c"] == mx:
            return b["date"]
    return bars[-1]["date"]


def stable_anchor(bars, *, lookback=60, min_base=3):
    """FIX guard 1 — the runup PEAK with a base AFTER it: the MAX-close date over the
    lookback window EXCLUDING the most recent `min_base` bars. Forces the anchor to be
    >= min_base sessions old (so a base exists after it) and stops it re-pinning to
    today's marginal new high. min_base = MATURE_DAYS."""
    n = len(bars)
    end = n - min_base
    start = max(0, n - lookback)
    if end <= start:
        return bars[-1]["date"]
    window = bars[start:end]
    mx = max(b["c"] for b in window)
    for b in window:
        if b["c"] == mx:
            return b["date"]
    return bars[-1]["date"]


def verdict(bars, anchor_fn):
    anchor_date = anchor_fn(bars)
    anchor_idx = next((j for j, b in enumerate(bars) if b["date"] == anchor_date), None)
    cons = de.evaluate_consolidation(bars, anchor_date)
    idx = len(bars) - 1
    fired = None
    # Mirror the live job: entries only fire when the runup canary admits the name
    # (scheduler._consolidation_readiness_job: `if cons is None: continue`).
    if cons is not None and anchor_idx is not None:
        if de.entry_signal_at(bars, idx, anchor_idx):
            fired = "anticipate"
        elif de.confirm_signal_at(bars, idx, anchor_idx):
            fired = "confirm"
    return {
        "anchor": anchor_date,
        "admitted": cons is not None,
        "runup": round(cons["runup_ratio"], 3) if cons else None,
        "state": cons["state"] if cons else None,
        "fired": fired,
    }


def run(bars, anchor_fn, label):
    print(f"\n=== {label} ===")
    print(f"{'ticker':6} {'label':8} {'admit':6} {'runup':7} {'state':11} {'fired':11} result")
    print("-" * 64)
    npass = ntot = 0
    for tk in sorted(GOOD | GARBAGE):
        if tk not in bars:
            print(f"{tk:6} NO BARS")
            continue
        v = verdict(bars[tk], anchor_fn)
        ntot += 1
        ok = v["admitted"] if tk in GOOD else (v["fired"] is None)
        npass += ok
        print(f"{tk:6} {('GOOD' if tk in GOOD else 'GARBAGE'):8} "
              f"{str(v['admitted']):6} {str(v['runup']):7} {str(v['state']):11} "
              f"{str(v['fired']):11} {'PASS' if ok else 'FAIL'}")
    print("-" * 64)
    print(f"{npass}/{ntot} pass")
    return npass, ntot


def main():
    bars = load_bars()
    run(bars, current_anchor, "BASELINE — broken anchor (max close, last 15)")
    npass, ntot = run(bars, stable_anchor, "FIX guard 1 — stable anchor (peak with a base after it)")
    return 0 if npass == ntot else 1


if __name__ == "__main__":
    sys.exit(main())
