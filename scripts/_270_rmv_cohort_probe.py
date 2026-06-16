#!/usr/bin/env python3
"""#270 STEP 0 — RMV on the cohort: does our BUILT tightness metric (flag_detector._compute_rmv,
the DeepVue/TraderLion 0-100 contraction index) separate the WINNING coiled entries from the
shaken ones — and how often does Pradeep's |close %change| <= 0.4% even fire on these volatile
tiny-caps (the "too tight for our universe" caveat)?

Reuses the anticipation replay's lifecycle + find_coiled_days + stop-and-reenter machinery
(NO reinvention) and the REAL `_compute_rmv` via a key-adapter ({h,l,c}->{high_price,low_price,
close}). Gate-free, read-only. N is small (one window) => ILLUSTRATIVE DIRECTION, not a verdict;
the COILED gate stays on the <=7%-range + base_run until N>=10 + sign-off (CHANGE_PROCESS).
ASCII output. Usage: python scripts/_270_rmv_cohort_probe.py
"""
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), HERE / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


anti = _load("_270_anticipation_replay.py")        # lifecycle, find_coiled_days, build_names, median
from agents.market_intelligence.flag_detector import _compute_rmv   # the SAME impl prod persists

median, mean = anti.median, anti.mean


def to_rmv_rows(bars):
    """Key-adapter: the cohort bars use {date,o,h,l,c,v}; _compute_rmv/_wilder_tr read
    {high_price,low_price,close}. (open/volume/date are unused by RMV.)"""
    return [{"high_price": b["h"], "low_price": b["l"], "close": b["c"]} for b in bars]


def rmv_at(rmv_rows, i, lookback):
    return _compute_rmv(rmv_rows, i, lookback=lookback)


def pct_change(bars, i):
    if i < 1 or not bars[i - 1]["c"]:
        return None
    return abs(bars[i]["c"] / bars[i - 1]["c"] - 1)


def rng_pct(bars, i):
    return (bars[i]["h"] - bars[i]["l"]) / bars[i]["c"] if bars[i]["c"] else None


def load_cohort():
    bars_by = defaultdict(list)
    for line in (HERE / "_270_cohort_bars.tsv").read_text(encoding="utf-8").splitlines():
        p = line.rstrip("\r").split("\t")
        if len(p) != 7:
            continue
        t, d, o, h, l, c, v = p
        bars_by[t].append({"date": d, "o": float(o), "h": float(h), "l": float(l),
                           "c": float(c), "v": float(v)})
    for t in bars_by:
        bars_by[t].sort(key=lambda b: b["date"])
    return bars_by


def main():
    bars_by = load_cohort()
    armed, names = anti.build_names(bars_by, min_base=1)   # loose = all coiled days

    # ── per ENTERED coiled day (stop-and-reenter attempt), tagged by what it did ──
    rows = []      # {t, i, outcome, rmv5, rmv15, rng, pc}
    for x in names:
        rrows = to_rmv_rows(bars_by[x["t"]])
        for a in x["attempts"]:
            i = a["ai"]
            rows.append({
                "t": x["t"], "i": i, "outcome": a["outcome"],
                "rmv5": rmv_at(rrows, i, 5), "rmv15": rmv_at(rrows, i, 15),
                "rng": rng_pct(bars_by[x["t"]], i), "pc": pct_change(bars_by[x["t"]], i),
            })

    print("#270 STEP 0 - RMV on the cohort: does our built tightness metric separate the winning coils?")
    print("(reuses anticipation lifecycle + find_coiled_days; _compute_rmv via key-adapter; "
          "gate-free, N small = DIRECTION)\n")
    coiled_names = len(names)
    print(f"cohort: {len(bars_by)} tickers; {armed} ARMED; {coiled_names} presented >=1 coiled day; "
          f"{len(rows)} entered coiled-entries (stop-and-reenter attempts).\n")

    # ── 1. RMV at the coiled-entry day, split by outcome ──
    print("1. RMV AT THE COILED-ENTRY DAY, split by what that entry DID:")
    print(f"   {'outcome':<8}{'n':>4}{'med rmv_5d':>12}{'med rmv_15d':>13}{'med range%':>12}{'med |close%|':>14}")
    for oc in ("win", "stop", "open"):
        sub = [r for r in rows if r["outcome"] == oc]
        if not sub:
            continue
        m5 = median([r["rmv5"] for r in sub])
        m15 = median([r["rmv15"] for r in sub])
        mr = median([r["rng"] for r in sub])
        mp = median([r["pc"] for r in sub])
        print(f"   {oc:<8}{len(sub):>4}{m5:>12.0f}{m15:>13.0f}{mr*100:>11.1f}%{mp*100:>13.2f}%")
    print("   -> if WINNING coils sit at LOWER rmv than SHAKEN (stop) coils, RMV-low is a useful "
          "coil-quality filter.\n")

    # ── 2. win-rate by RMV bucket (per coiled entry) ──
    print("2. ENTRY OUTCOME by rmv_5d bucket (per coiled-entry; win = held into the breakout):")
    print(f"   {'rmv_5d':<10}{'n':>4}{'win':>5}{'stop':>6}{'open':>6}{'win%':>7}")
    buckets = [("<=10", lambda v: v is not None and v <= 10),
               ("10-30", lambda v: v is not None and 10 < v <= 30),
               (">30", lambda v: v is not None and v > 30)]
    for label, pred in buckets:
        sub = [r for r in rows if pred(r["rmv5"])]
        if not sub:
            print(f"   {label:<10}{0:>4}")
            continue
        w = sum(1 for r in sub if r["outcome"] == "win")
        s = sum(1 for r in sub if r["outcome"] == "stop")
        o = sum(1 for r in sub if r["outcome"] == "open")
        print(f"   {label:<10}{len(sub):>4}{w:>5}{s:>6}{o:>6}{w/len(sub)*100:>6.0f}%")
    print()

    # ── 3. Pradeep 0.4% close-% on these tiny-caps (validate the caveat) ──
    # Use ALL coiled days (find_coiled_days), not just entered ones, for the fire-rate.
    all_coiled = []   # (t, i)
    for x in names:
        ctx = x["ctx"]
        for i in anti.find_coiled_days(bars_by[x["t"]], ctx, min_base=1):
            all_coiled.append((x["t"], i))
    pcs = [pct_change(bars_by[t], i) for t, i in all_coiled]
    pcs = [p for p in pcs if p is not None]
    fire_04 = sum(1 for p in pcs if p <= 0.004)
    print(f"3. PRADEEP |close %change| <= 0.4% on the cohort's coiled days (N={len(pcs)}):")
    print(f"   fires on {fire_04}/{len(pcs)} ({fire_04/len(pcs)*100:.0f}%)  | "
          f"median |close%| at a coiled day = {median(pcs)*100:.2f}%")
    # the threshold that would fire on ~half the coiled days = our-universe-calibrated value
    half = sorted(pcs)[len(pcs) // 2] if pcs else float("nan")
    print(f"   -> 0.4% is Pradeep's value for calmer names; on these tiny-caps the median coiled-day "
          f"close-move is {median(pcs)*100:.2f}%,\n      so a calibrated tight-close threshold for OUR "
          f"universe is ~{half*100:.1f}% (fires on ~half). Telemetry-first; do not hard-gate on 0.4%.\n")

    # ── 4. RMV adds resolution WITHIN the existing <=7%-range gate? ──
    in_gate = [r for r in rows if r["rng"] is not None and r["rng"] <= 0.07]
    print(f"4. RMV resolution WITHIN the current <=7%-range coiled gate (entered coils in-gate N={len(in_gate)}):")
    for label, pred in buckets:
        sub = [r for r in in_gate if pred(r["rmv5"])]
        if not sub:
            continue
        w = sum(1 for r in sub if r["outcome"] == "win")
        print(f"   range<=7% AND rmv_5d {label:<6}: {len(sub):>2} entries, win {w}/{len(sub)} ({w/len(sub)*100:.0f}%)")
    print("   -> if winners concentrate at low rmv even WITHIN the range gate, RMV is an additive "
          "coil-quality axis (the #54 'RMV catches what range misses' result, re-tested on #270).\n")

    print("VERDICT (direction only, N small): see whether row 1 shows win-rmv < stop-rmv and row 2 "
          "shows win% falling as rmv rises.\n   If yes -> RMV is the right coil metric to RECORD now + "
          "graduate to load-bearing at N>=10 + sign-off. If flat -> keep it as telemetry, range-gate stays primary.")


if __name__ == "__main__":
    main()
