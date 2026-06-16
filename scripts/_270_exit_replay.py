#!/usr/bin/env python3
"""#270 Layer-3 EXIT/harvest design (gate-free). Entry is held CONSTANT (FIRST5-BREAK,
the tuned primary) to isolate the exit variable; we walk forward bars and measure
REALIZED R (not MFE) under a SPEED SPECTRUM of harvest rules. The one question:
**does banking FASTER lift the realized R of the TYPICAL (median) name** — the cohort's
fat-MFE / weak-close profile says the edge is the excursion, not buy-and-hold.

Advisor-mandated methodology (6/14):
  1. Report median / mean / ex-top-2 for every rule — mean is dominated by HCAI+ASTI and
     structurally rewards "hold"; the thesis is about the median name.
  2. Intrabar path-dependency: a single DAILY bar can span both a target and the stop and
     we can't know which hit first -> compute BOTH bounds (optimistic=target-first,
     pessimistic=stop-first); HEADLINE = pessimistic. If the ranking flips between bounds
     the result is resolution-driven, not an edge.
  3. Day 0 = MINUTE resolution (derisk-fast lives on the trigger day), day 1+ = daily.
  4. Stop fills at min(stop, bar_open) — tiny-caps gap THROUGH stops; honest loss tail.
  + Perfect-foresight sell-at-MFE rule as a correctness anchor; cohort-MFE cross-check
    validates the daily bar-walk reproduces _270_cohort_run's known figures.

N ~= 15 (FIRST5 fills 15/18), one ~3.5-month window, in-sample => ILLUSTRATIVE DIRECTION
(does fast-harvest beat hold on the median name), NOT a magnitude verdict. ASCII output.
"""
import importlib.util
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Reuse the entry-replay machinery (GDL map, minute-bar loader, RTH constants).
_spec = importlib.util.spec_from_file_location("e270", HERE / "_270_entry_replay.py")
_e270 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_e270)
GDL, load_rth, RTH_OPEN = _e270.GDL, _e270.load_rth, _e270.RTH_OPEN
# Shared harvest evaluator (RULES + simulate) — single impl, also used by the anticipation replay.
_hspec = importlib.util.spec_from_file_location("h270", HERE / "_270_harvest.py")
_h270 = importlib.util.module_from_spec(_hspec)
_hspec.loader.exec_module(_h270)
RULES, simulate = _h270.RULES, _h270.simulate
FWD_DAYS = 10

# ---- daily bars (day 1+) -------------------------------------------------------
DAILY = defaultdict(list)
for _line in (HERE / "_270_cohort_bars.tsv").read_text(encoding="utf-8").splitlines():
    _p = _line.rstrip("\r").split("\t")
    if len(_p) != 7:
        continue
    _t, _d, _o, _h, _l, _c, _v = _p
    DAILY[_t].append({"date": _d, "o": float(_o), "h": float(_h),
                      "l": float(_l), "c": float(_c)})
for _t in DAILY:
    DAILY[_t].sort(key=lambda b: b["date"])


def entry_first5(bars, gdl):
    """FIRST5-BREAK entry; return (entry, stop, post_entry_minute_bars) or None.
    entry = first-5-min high, stop = first-5-min low; fill on the break bar."""
    or5 = [b for b in bars if RTH_OPEN <= b["m"] < RTH_OPEN + 5]
    if not or5:
        return None
    hi, lo = max(b["h"] for b in or5), min(b["l"] for b in or5)
    for i, b in enumerate(bars):
        if b["m"] < RTH_OPEN + 5:
            continue
        if b["h"] > hi:
            if hi <= lo or hi <= gdl * 0.98:
                return None
            return hi, lo, bars[i:]           # entry, stop, post-entry day-0 path
    return None


def build_path(tk, trig_date, post_min_bars):
    """Day-0 post-entry MINUTE bars + day 1..FWD_DAYS DAILY bars. Daily bars carry
    `prior_low` (the previous completed daily bar's low) for the trail."""
    path = [{"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
             "kind": "min", "prior_low": None, "day_idx": 0} for b in post_min_bars]
    dbars = DAILY.get(tk, [])
    idx = next((i for i, b in enumerate(dbars) if b["date"] == trig_date), None)
    if idx is None:
        return path, None
    fwd = dbars[idx + 1: idx + 1 + FWD_DAYS]
    prior_low = dbars[idx]["l"]               # day-0 daily low seeds the trail
    for di, b in enumerate(fwd, start=1):
        path.append({"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                     "kind": "day", "prior_low": prior_low, "day_idx": di})
        prior_low = b["l"]
    # MFE over the whole post-entry path (day0 minute + daily) for capture %.
    mfe = max(b["h"] for b in path) / 1.0     # filled in by caller vs entry
    return path, mfe


# RULES (the harvest speed spectrum) + simulate() live in _270_harvest.py — the SINGLE
# evaluator shared with the anticipation replay (extracted 2026-06-14 to kill the hand-synced
# copy). SPEED_ORDER is just this script's display ordering of those rules.
SPEED_ORDER = ["all_out_+1R", "time_stop_2d", "half_1R_trail", "bank_1R_3R",
               "bank2_1R_run", "twophase_g50", "twophase_g33", "hold_10d", "MFE_ceiling"]


def agg(xs):
    s = sorted(xs)
    n = len(s)
    med = s[n // 2] if n else float("nan")
    mean = statistics.fmean(s) if s else float("nan")
    ex2 = statistics.fmean(s[:-2]) if n > 2 else float("nan")  # drop the 2 best names
    wr = sum(1 for x in s if x > 0) / n if n else float("nan")
    return med, mean, ex2, wr


def main():
    by = load_rth()
    setups = []      # (tk, date, entry, stop, path)
    for (tk, d), gdl in sorted(GDL.items(), key=lambda kv: kv[0][1]):
        bars = by.get((tk, d))
        if not bars:
            continue
        e = entry_first5(bars, gdl)
        if not e:
            continue
        entry, stop, post = e
        path, _ = build_path(tk, d, post)
        if len(path) < 2:
            continue
        setups.append((tk, d, entry, stop, path))

    print(f"#270 EXIT/harvest replay — FIRST5 entry held constant, N={len(setups)} filled "
          f"triggers (one window, in-sample => illustrative DIRECTION).\n")

    # Cross-check: reproduce _270_cohort_run MFE (trigger CLOSE -> 10d daily high) to
    # validate the daily bar-walk alignment (advisor anchor).
    print("daily-alignment cross-check (trigger close -> next-10d high, vs cohort_run):")
    for tk, d, *_ in setups:
        dbars = DAILY.get(tk, [])
        idx = next((i for i, b in enumerate(dbars) if b["date"] == d), None)
        if idx is None:
            continue
        fwd = dbars[idx + 1: idx + 1 + FWD_DAYS]
        if fwd:
            mfe = max(b["h"] for b in fwd) / dbars[idx]["c"] - 1
            if mfe >= 0.30:
                print(f"  {tk:<6} {d}  close-base MFE {mfe*100:+.0f}%")
    print()

    print(f"{'rule':<16} {'bound':<5} {'medR':>6} {'meanR':>7} {'exTop2R':>8} "
          f"{'win%':>5} {'medCap%':>8}")
    results = {}
    fill_days = defaultdict(lambda: defaultdict(float))   # rule -> day_idx -> sum(fraction)
    for name in SPEED_ORDER:
        rule = RULES[name]
        for bound in ("pess", "opt"):
            rs, caps = [], []
            for tk, d, entry, stop, path in setups:
                out = simulate(entry, stop, path, rule, bound)
                if out:
                    rs.append(out[0])
                    if out[1] == out[1]:     # not nan
                        caps.append(out[1])
                    if bound == "pess":      # tally fills once, on the headline bound
                        for day_idx, frac in out[2]:
                            fill_days[name][day_idx] += frac
            med, mean, ex2, wr = agg(rs)
            medcap = sorted(caps)[len(caps)//2] if caps else float("nan")
            results[(name, bound)] = (med, mean, ex2, wr)
            print(f"{name:<16} {bound:<5} {med:>6.2f} {mean:>7.2f} {ex2:>8.2f} "
                  f"{wr*100:>4.0f}% {medcap*100:>7.0f}%")
        if name != "MFE_ceiling":
            print()

    # FILL-DAY DISTRIBUTION (advisor 6/14): the "same-day harvest" claim was inferred
    # from opt==pess, never measured. This MEASURES it — what fraction of every rule's
    # position is exited on the TRIGGER day (day_idx 0) vs day 1+. [pess bound]
    print("fill-day distribution [pess] — share of total exited position by day_idx:")
    print(f"  {'rule':<16} {'day0':>6} {'day1':>6} {'day2':>6} {'day3+':>6}  (sumfrac of "
          f"N={len(setups)} positions)")
    for name in SPEED_ORDER:
        if name == "MFE_ceiling":
            continue
        dd = fill_days[name]
        total = sum(dd.values()) or 1.0
        d0 = dd.get(0, 0.0) / total
        d1 = dd.get(1, 0.0) / total
        d2 = dd.get(2, 0.0) / total
        d3 = sum(v for k, v in dd.items() if k >= 3) / total
        print(f"  {name:<16} {d0*100:>5.0f}% {d1*100:>5.0f}% {d2*100:>5.0f}% {d3*100:>5.0f}%")
    print("  -> 'same-day harvest' is CONFIRMED only if the fast rules bank the bulk on "
          "day0; otherwise restate the SSoT claim to the measured split.")
    print()

    # The thesis test, on the HEADLINE (pessimistic) bound, median + ex-top-2.
    print("THESIS (does faster banking lift the TYPICAL name's realized R?):")
    fast = results[("all_out_+1R", "pess")]
    hold = results[("hold_10d", "pess")]
    hyb = results[("half_1R_trail", "pess")]
    print(f"  [pess] median R: all_out_+1R {fast[0]:+.2f} | half_1R_trail {hyb[0]:+.2f} | "
          f"hold_10d {hold[0]:+.2f}")
    print(f"  [pess] ex-top2 R: all_out_+1R {fast[2]:+.2f} | half_1R_trail {hyb[2]:+.2f} | "
          f"hold_10d {hold[2]:+.2f}")
    print("  -> if fast/hybrid > hold on BOTH median and ex-top2 (and the ranking holds "
          "under the opt bound), the derisk-fast thesis is confirmed for the median name.")

    # PRADEEP TWO-PHASE test: does CONDITIONAL hold (day-0 aggressive trail → hold survivors)
    # protect the median AND capture the tail the fixed-target scale CAPS at +3R?
    print("\nPRADEEP TWO-PHASE (day-0 giveback trail -> survivors held to day-5; [pess]):")
    scale = results[("bank_1R_3R", "pess")]
    tp50, tp33 = results[("twophase_g50", "pess")], results[("twophase_g33", "pess")]
    print(f"  {'rule':<14}{'medR':>7}{'meanR':>8}{'exTop2R':>9}{'win%':>6}")
    for nm, r in (("bank_1R_3R", scale), ("twophase_g50", tp50), ("twophase_g33", tp33),
                  ("hold_10d", hold)):
        print(f"  {nm:<14}{r[0]:>+7.2f}{r[1]:>+8.2f}{r[2]:>+9.2f}{r[3]*100:>5.0f}%")
    print("  -> two-phase WINS if it holds the median ~level with the fast rules (>=0) AND lifts "
          "the MEAN\n     above the +3R-capped scale (= it kept a runner the cap threw away). If "
          "the mean doesn't\n     beat scale, the day-0 trail is stopping out the would-be runners "
          "too -- tune day0_giveback / the day-5 cap.")


if __name__ == "__main__":
    main()
