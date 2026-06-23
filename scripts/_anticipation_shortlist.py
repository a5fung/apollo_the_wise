"""Generate the Anticipation shortlist for operator labeling (data-grounded gates, NOT calibrated).

Applies the rebuild gates to the live post-runup universe and writes a labelable table so the
operator can mark each good/garbage -> that becomes the calibration set for the volatility-relative
thresholds. NOTHING is gated/deployed by this; it's a worksheet.

Gates applied: stable anchor (recent runup-leg peak, 3-20d base) -> runup >= 1.15 (the §2 floor) ->
show holds (>=4% breakdowns + max retrace) + tightness (rmv_5d) + today move. Ordered so the
tight/holding names sit on top and the declines are visible lower down.
"""
import sys
from collections import defaultdict
sys.path.insert(0, ".")
from agents.market_intelligence import anticipation as de

OUT = "docs/analysis/anticipation_shortlist_to_label_2026-06-22.md"


def load(path):
    by = defaultdict(list)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            p = line.split("|")
            if len(p) != 7:
                continue
            tk, d, o, h, lo, c, v = p
            try:
                by[tk].append({"trade_date": d, "open_price": float(o), "high_price": float(h),
                               "low_price": float(lo), "close": float(c), "volume": float(v)})
            except ValueError:
                continue
    return {tk: de.db_rows_to_bars(r) for tk, r in by.items()}


def stable_anchor_idx(bars, min_base=3, max_base=20):
    n = len(bars)
    end, start = n - min_base, max(0, n - max_base)
    if end <= start:
        return None
    mx = max(bars[j]["c"] for j in range(start, end))
    for j in range(start, end):
        if bars[j]["c"] == mx:
            return j
    return None


def row(bars):
    if len(bars) < 15:
        return None
    ai = stable_anchor_idx(bars)
    if ai is None or ai < 10:
        return None
    peak = bars[ai]["c"]
    runup = peak / min(bars[j]["c"] for j in range(ai - 10, ai + 1))
    if runup < 1.15:
        return None
    base = bars[ai + 1:]
    bd4 = sum(1 for j in range(ai + 1, len(bars))
              if bars[j - 1]["c"] and (bars[j]["c"] / bars[j - 1]["c"] - 1) <= -0.04)
    retrace = (peak - min(b["c"] for b in base)) / peak * 100
    rmv = de.compute_rmv(bars, len(bars) - 1, lookback=5)
    prev = bars[-2]["c"]
    today = abs(bars[-1]["c"] / prev - 1) * 100 if prev else None
    return {"runup": round(runup, 2), "baseD": len(base), "bd4": bd4,
            "retrace": round(retrace, 1), "rmv": round(rmv) if rmv is not None else None,
            "today": round(today, 1) if today is not None else None}


def main():
    bars = load("tests/fixtures/anticipation_universe_bars.psv")
    rows = []
    for tk, b in bars.items():
        r = row(b)
        if r:
            rows.append((tk, r))
    # tight + holding first: fewest breakdowns, then tightest rmv, then smallest retrace
    rows.sort(key=lambda x: (x[1]["bd4"], x[1]["rmv"] if x[1]["rmv"] is not None else 99, x[1]["retrace"]))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# Anticipation shortlist — TO LABEL (operator)\n\n")
        f.write("Mark each **G** (real Pradeep Anticipation setup) or **X** (garbage) in the LABEL column.\n")
        f.write("This calibrates the volatility-relative holds/tightness thresholds — do NOT treat the\n")
        f.write("current ordering as the gate. Gates so far: stable anchor (3-20d base) + runup>=15%.\n")
        f.write("`bd4`=#>=4% daily breakdowns in the base · `retr%`=max retrace from peak · `rmv`=tightness (0-100, low=tight) · `today%`=today's move.\n\n")
        f.write(f"{len(rows)} post-runup candidates (live universe of {len(bars)}). Tight+holding first.\n\n")
        f.write("| LABEL | ticker | runup | baseD | bd4 | retr% | rmv | today% |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for tk, r in rows:
            f.write(f"|   | {tk} | {r['runup']} | {r['baseD']} | {r['bd4']} | {r['retrace']} | {r['rmv']} | {r['today']} |\n")
    print(f"wrote {len(rows)} candidates to {OUT}")
    print("\nTop 20 (tightest + holding):")
    print(f"{'ticker':7} {'runup':6} {'baseD':6} {'bd4':4} {'retr%':6} {'rmv':4} {'today%':6}")
    for tk, r in rows[:20]:
        print(f"{tk:7} {r['runup']:<6} {r['baseD']:<6} {r['bd4']:<4} {r['retrace']:<6} {str(r['rmv']):<4} {str(r['today']):<6}")


if __name__ == "__main__":
    main()
