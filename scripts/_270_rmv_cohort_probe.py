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
from agents.market_intelligence.flag_detector import _compute_rmv, _atr_14   # the SAME impl prod persists

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


def outcome_under_stop(bars, ai, trig_idx, end_idx, stop):
    """Single-shot (no re-enter) outcome of an anticipation entry at coiled day `ai` under a
    GIVEN stop. Isolates the STOP-placement effect (operator 6/16: is RMV-low 'bad' really just
    a too-tight coiled-low stop on a deeply-contracted day?). Returns (outcome, R) where R is the
    MFE-to-window-high / risk ceiling (win/open) or -1.0 (stop). MFE-ceiling, not harvested."""
    entry = bars[ai]["c"]
    if stop is None or stop >= entry:
        return None
    risk = (entry - stop) / entry
    for i in range(ai + 1, end_idx + 1):
        if trig_idx is not None and i >= trig_idx:           # reached the breakout, never stopped
            run_high = max(b["h"] for b in bars[ai + 1: end_idx + 1])
            return "win", (run_high / entry - 1) / risk
        if bars[i]["l"] <= stop:                              # shaken first
            return "stop", -1.0
    run_high = max((b["h"] for b in bars[ai + 1: end_idx + 1]), default=entry)
    return "open", (run_high / entry - 1) / risk


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

    # ── 5. STOP SENSITIVITY (operator 6/16: is RMV-low 'ineffective' really a too-tight STOP?) ──
    # For EVERY coiled day, single-shot outcome under 4 stops tight->wide, split by rmv_5d bucket.
    # If low-RMV win% RISES sharply as the stop widens, the shake was a STOP artifact, not setup
    # quality -> the stop is the lever to tune, and RMV-low setups may be fine with a wider stop.
    STOPS = ["coiled_low", "coiled_low-0.5ATR", "gap_day_low", "fixed_-8%"]
    cd_rows = []   # {rmv5, stop_name -> (outcome,R)}
    for x in names:
        bars = bars_by[x["t"]]
        rrows = to_rmv_rows(bars)
        ctx = x["ctx"]
        for i in anti.find_coiled_days(bars, ctx, min_base=1):
            atr = _atr_14(rrows, i)
            entry = bars[i]["c"]
            stopvals = {
                "coiled_low": bars[i]["l"],
                "coiled_low-0.5ATR": (bars[i]["l"] - 0.5 * atr) if atr else None,
                "gap_day_low": ctx["gap_day_low"],
                "fixed_-8%": entry * 0.92,
            }
            rec = {"rmv5": rmv_at(rrows, i, 5)}
            for sn in STOPS:
                rec[sn] = outcome_under_stop(bars, i, ctx["trig_idx"], x["end_idx"], stopvals[sn])
            cd_rows.append(rec)

    print("5. STOP SENSITIVITY - single-shot win% (+ med R, MFE-ceiling) by stop x rmv_5d bucket "
          f"(all coiled days, N={len(cd_rows)}):")
    print(f"   {'stop':<20}{'med risk%':>10}   " + "".join(f"{b[0]:>14}" for b in buckets) + f"{'ALL':>14}")
    for sn in STOPS:
        # median risk% for this stop across coiled days
        risks = []
        for x in names:
            bars, rrows, ctx = bars_by[x["t"]], None, x["ctx"]
            for i in anti.find_coiled_days(bars, ctx, min_base=1):
                e = bars[i]["c"]
                sv = {"coiled_low": bars[i]["l"], "gap_day_low": ctx["gap_day_low"],
                      "fixed_-8%": e * 0.92}.get(sn)
                if sn == "coiled_low-0.5ATR":
                    a = _atr_14(to_rmv_rows(bars), i)
                    sv = (bars[i]["l"] - 0.5 * a) if a else None
                if sv is not None and sv < e:
                    risks.append((e - sv) / e)
        cells = []
        for label, pred in buckets + [("ALL", lambda v: True)]:
            sub = [r[sn] for r in cd_rows if pred(r["rmv5"]) and r[sn] is not None]
            if not sub:
                cells.append(f"{'-':>14}")
                continue
            w = sum(1 for o, _ in sub if o == "win")
            medr = median([R for _, R in sub])
            cells.append(f"{w}/{len(sub)} {medr:+.1f}R".rjust(14))
        print(f"   {sn:<20}{median(risks)*100:>9.0f}%   " + "".join(cells))
    print("   -> if low-rmv (<=10) win% climbs sharply from coiled_low -> wider stops, the RMV-low")
    print("      shakes were a STOP artifact (tiny coiled range = stop right under entry), NOT setup")
    print("      quality. Then the STOP is the lever (operator 6/16); RMV-low setups may be viable")
    print("      with a structural (gap_day_low) or ATR-buffered stop. R is MFE-ceiling -> direction only.\n")

    print("VERDICT (DIRECTION ONLY, N small - nothing 100% yet, all params up for scrutiny): sections 1-4 "
          "show RMV-low does NOT improve the coiled-low-stop entry (it inverts). Section 5 tests whether "
          "that is a STOP artifact. RMV is RECORDED telemetry either way; the coil gate + the STOP are both "
          "tuning candidates at N>=10 + sign-off (CHANGE_PROCESS). Durable writeup: docs/analysis/delayed_ep_rmv_step0_270.md")


if __name__ == "__main__":
    main()
