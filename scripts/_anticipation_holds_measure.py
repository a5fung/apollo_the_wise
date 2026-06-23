"""Measure the HOLDS dimension (Pradeep One-Strike + Depth/retrace) for the GOOD Anticipation
cohort (the 6/15 canonical names, as-of 6/15) vs the GARBAGE that fired (as-of 6/22).

Grounds the gate in the known-good set instead of inventing a threshold (ADR 0013 discipline:
"gate only on what holds. No invented thresholds."). Anchor = the stable runup peak (the proven
guard-1). Reports, per name: # of >=4% close-to-close breakdowns in the base, and max retrace
from the peak. We are LOOKING FOR a clean separator, not asserting one.
"""
import sys
from collections import defaultdict
sys.path.insert(0, ".")
from agents.market_intelligence import anticipation as de

GOOD = {"COO", "HYLN", "ALHC", "APPS", "NTAP", "MNTS"}   # Pradeep 6/15 canonical (as-of 6/15)
GARBAGE = {"BTU", "UFO", "DRUG", "PTGX"}                  # fired-on-decline/uptrend (as-of 6/22)


def load(path):
    by = defaultdict(list)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            tk, d, o, h, lo, c, v = line.split("|")
            by[tk].append({"trade_date": d, "open_price": float(o), "high_price": float(h),
                           "low_price": float(lo), "close": float(c), "volume": float(v)})
    return {tk: de.db_rows_to_bars(r) for tk, r in by.items()}


def stable_anchor_idx(bars, min_base=3, max_base=20):
    # Pradeep base = 3-20 days -> the recent runup-leg peak sits in [today-max_base, today-min_base].
    # (Not the global 60d max, which finds an earlier leg and manufactures a months-long "base".)
    n = len(bars)
    end, start = n - min_base, max(0, n - max_base)
    if end <= start:
        return n - 1
    mx = max(bars[j]["c"] for j in range(start, end))
    for j in range(start, end):
        if bars[j]["c"] == mx:
            return j
    return n - 1


def measure(bars):
    ai = stable_anchor_idx(bars)
    peak = bars[ai]["c"]
    base = bars[ai + 1:]
    if not base:
        return None
    bd4 = sum(1 for j in range(ai + 1, len(bars))
              if bars[j - 1]["c"] and (bars[j]["c"] / bars[j - 1]["c"] - 1) <= -0.04)
    max_retrace = (peak - min(b["c"] for b in base)) / peak * 100
    return {"anchor": bars[ai]["date"], "peak": round(peak, 2),
            "base_days": len(base), "breakdowns_4pct": bd4, "max_retrace_pct": round(max_retrace, 1)}


def main():
    bars = {}
    bars.update(load("tests/fixtures/anticipation_pradeep_cohort_bars.psv"))
    bars.update(load("tests/fixtures/consolidation_acceptance_bars.psv"))
    print(f"{'ticker':6} {'label':8} {'anchor':11} {'baseD':6} {'#4%-breakdowns':15} {'maxRetrace%':11}")
    print("-" * 64)
    for grp, names in (("GOOD (Pradeep)", sorted(GOOD)), ("GARBAGE", sorted(GARBAGE))):
        for tk in names:
            if tk not in bars:
                print(f"{tk:6} NO BARS")
                continue
            m = measure(bars[tk])
            if not m:
                print(f"{tk:6} no base")
                continue
            print(f"{tk:6} {('GOOD' if tk in GOOD else 'GARBAGE'):8} {m['anchor']:11} "
                  f"{m['base_days']:<6} {m['breakdowns_4pct']:<15} {m['max_retrace_pct']:<11}")
        print()


if __name__ == "__main__":
    main()
