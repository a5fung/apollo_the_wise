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


# ---- harvest rules (the speed spectrum) ----------------------------------------
# Each rule: partials [(R_multiple, fraction)], breakeven_after_first, trail_prior_low,
# time_stop_days (force-exit remaining at that daily bar's close), hold (exit at end),
# perfect_mfe (ceiling anchor).
RULES = {
    "MFE_ceiling":   dict(perfect_mfe=True),
    "all_out_+1R":   dict(partials=[(1.0, 1.0)]),
    "time_stop_2d":  dict(time_stop_days=2),
    "half_1R_trail": dict(partials=[(1.0, 0.5)], breakeven_after_first=True,
                          trail_prior_low=True),
    # tail-capture variants — bank the bulk fast (protect the median) but keep a
    # runner tranche for the fat tail (the setup's reason-for-being).
    "bank_1R_3R":    dict(partials=[(1.0, 0.5), (3.0, 0.5)]),                 # 1/2@+1R, 1/2@+3R
    "bank2_1R_run":  dict(partials=[(1.0, 0.667)], breakeven_after_first=True,
                          trail_prior_low=True),                              # 2/3@+1R, 1/3 trail
    "hold_10d":      dict(hold=True),
}
SPEED_ORDER = ["all_out_+1R", "time_stop_2d", "half_1R_trail", "bank_1R_3R",
               "bank2_1R_run", "hold_10d", "MFE_ceiling"]


def simulate(entry, init_stop, path, rule, bound):
    """Realized R under one intrabar `bound` ('opt' target-first / 'pess' stop-first).
    risk = entry - init_stop. Returns (realized_R, captured_pct_of_mfe, fills) where
    `fills` is a list of (day_idx, fraction) for every exit slice — the raw material
    for the fill-day distribution that VALIDATES (vs assumes) the 'same-day harvest'
    claim (day_idx 0 == trigger day)."""
    risk = entry - init_stop
    if risk <= 0:
        return None
    if rule.get("perfect_mfe"):
        mfe_px = max(b["h"] for b in path)
        return (mfe_px - entry) / risk, 1.0, []          # ceiling anchor: no real fills

    partials = list(rule.get("partials", []))           # (R_mult, frac) queue
    stop = init_stop
    pos = 1.0
    realized = 0.0                                       # in R units
    day_count = 0
    mfe_px = entry
    fills = []                                           # (day_idx, fraction) per slice

    for b in path:
        mfe_px = max(mfe_px, b["h"])
        if b["kind"] == "day":
            day_count += 1
            if rule.get("trail_prior_low") and b["prior_low"] is not None:
                stop = max(stop, b["prior_low"])
        # next partial target price (if any)
        tgt_px = entry + partials[0][0] * risk if partials else None
        hit_tgt = tgt_px is not None and b["h"] >= tgt_px
        hit_stop = b["l"] <= stop

        def take_partial():
            nonlocal pos, realized, partials
            r_mult, frac = partials.pop(0)
            f = min(frac, pos)
            realized += f * r_mult                       # target fills AT target price
            pos -= f
            fills.append((b["day_idx"], f))
            if rule.get("breakeven_after_first"):
                nonlocal_stop_breakeven()

        def nonlocal_stop_breakeven():
            nonlocal stop
            stop = max(stop, entry)

        def take_stop():
            nonlocal pos, realized
            fill = min(stop, b["o"])                     # gap-through honesty
            realized += pos * (fill - entry) / risk
            fills.append((b["day_idx"], pos))
            pos = 0.0

        if hit_tgt and hit_stop:
            if bound == "opt":
                take_partial()
                if pos > 0 and b["l"] <= stop:           # stop may still hit after
                    take_stop()
            else:                                        # pessimistic: stop first
                take_stop()
        elif hit_tgt:
            take_partial()
        elif hit_stop:
            take_stop()

        if pos <= 0:
            break
        if rule.get("time_stop_days") and b["kind"] == "day" and day_count >= rule["time_stop_days"]:
            realized += pos * (b["c"] - entry) / risk    # force-exit at close
            fills.append((b["day_idx"], pos))
            pos = 0.0
            break

    if pos > 0:                                          # survived: exit at last close
        realized += pos * (path[-1]["c"] - entry) / risk
        fills.append((path[-1]["day_idx"], pos))
    captured = realized / ((mfe_px - entry) / risk) if mfe_px > entry else float("nan")
    return realized, captured, fills


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


if __name__ == "__main__":
    main()
