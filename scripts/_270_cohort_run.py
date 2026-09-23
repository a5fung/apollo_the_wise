#!/usr/bin/env python3
"""#270 step 2 (gate-free cohort calibration) — run the composition replay over the
huge-gap cohort and tally the WATCHED->ARMED->TRIGGERED funnel. The TRIGGER rate is
the calibration signal: a rare setup (one-pays-for-ten-losers) should fire SELECTIVELY,
not on every gap. Reuses replay() from _270_delayed_ep_replay (no duplicated logic).

Usage: python scripts/_270_cohort_run.py [cohort_bars.tsv]
       (TSV cols: ticker<TAB>date<TAB>open<TAB>high<TAB>low<TAB>close<TAB>volume)
"""
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r270", HERE / "_270_delayed_ep_replay.py")
r270 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r270)
replay = r270.replay

TSV = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "_270_cohort_bars.tsv"

bars_by = defaultdict(list)
for line in TSV.read_text(encoding="utf-8").splitlines():
    p = line.rstrip("\r").split("\t")
    if len(p) != 7:
        continue
    t, d, o, h, l, c, v = p
    bars_by[t].append({"date": d, "o": float(o), "h": float(h), "l": float(l),
                       "c": float(c), "v": float(v)})

def fwd_outcome(bars, trig_date, n=10):
    """MFE + close-return over the next n bars after the trigger date (does it RUN?)."""
    idx = next((i for i, b in enumerate(bars) if b["date"] == trig_date), None)
    if idx is None or idx + 1 >= len(bars):
        return None
    entry = bars[idx]["c"]
    fwd = bars[idx + 1: idx + 1 + n]
    if not fwd:
        return None
    mfe = max(b["h"] for b in fwd) / entry - 1
    ret = fwd[-1]["c"] / entry - 1
    return mfe, ret, len(fwd)


reached = {"WATCHED": set(), "ARMED": set(), "TRIGGERED": set()}
counts = {"WATCHED": 0, "ARMED": 0, "TRIGGERED": 0}
triggers = []
for t, bars in bars_by.items():
    bars.sort(key=lambda b: b["date"])
    for date, state, detail in replay(bars):
        if state in counts:
            counts[state] += 1
            reached[state].add(t)
        if state == "TRIGGERED":
            triggers.append((date, t, detail, fwd_outcome(bars, date)))

w, a, tr = (len(reached[s]) for s in ("WATCHED", "ARMED", "TRIGGERED"))
n_bars = sum(len(b) for b in bars_by.values())
print(f"cohort: {len(bars_by)} huge-gap tickers, {n_bars} bars (full history per ticker)")
print(f"thresholds: GAP>={r270.GAP:.0%} VOLX>={r270.VOLX}x ARM_WINDOW={r270.ARM_WINDOW}d "
      f"EXPANSION>{r270.EXPANSION}x\n")
print(f"WATCHED   {w:3d} tickers / {counts['WATCHED']} events")
print(f"ARMED     {a:3d} tickers / {counts['ARMED']} events  (undercut of gap-day low in window)")
print(f"TRIGGERED {tr:3d} tickers / {counts['TRIGGERED']} events  (reclaim + volume expansion)")
print(f"\nfunnel: WATCHED {w} -> ARMED {a} ({a/w*100:.0f}% of watched) -> "
      f"TRIGGERED {tr} ({tr/w*100:.0f}% of watched, {tr/a*100 if a else 0:.0f}% of armed)")
print(f"=> composition fires the full lifecycle on {tr}/{w} = {tr/w*100:.0f}% of huge-gap names "
      f"({counts['TRIGGERED']} trigger events)\n")
# forward-outcome distribution (does the lifecycle, once TRIGGERED, actually run?)
scored = [(d, t, o) for d, t, _, o in triggers if o is not None]
mfes = sorted(o[0] for _, _, o in scored)
if mfes:
    n = len(mfes)
    med = mfes[n // 2]
    big = sum(1 for m in mfes if m >= 0.20)
    print(f"FORWARD OUTCOME (next 10 trading days post-trigger, N={n} with fwd data):")
    print(f"  MFE median {med*100:+.0f}%  |  >=+20% MFE: {big}/{n} ({big/n*100:.0f}%)  |  "
          f"best {mfes[-1]*100:+.0f}%  worst {mfes[0]*100:+.0f}%")
    print("  (MFE = max favorable excursion: did it RUN like MNTS's +43% after the reclaim?)\n")
print("=== TRIGGERED events (date | ticker | fwd MFE / 10d-ret) ===")
for date, t, detail, o in sorted(triggers):
    fwd = f"MFE {o[0]*100:+.0f}% / ret {o[1]*100:+.0f}% (n={o[2]})" if o else "in-flight (no fwd data)"
    print(f"  {date}  {t:<6} {fwd:<32} {detail.split(';')[0]}")
