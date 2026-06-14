#!/usr/bin/env python3
"""#270 step 2b (gate-free) — intraday ENTRY tuning. For each cohort TRIGGER day, replay
two template-aligned intraday entries on minute bars and compare stop tightness + the
captured intraday move. The entry layer decides HOW you get in (the daily reclaim is too
late, EOD). "Entry is as important as exit" (memory user-sip-setup-is-one-e2e-tactic).

Tactics:
  A FIRST5-BREAK  ("first-minute high/low HELD", the MNTS confirmation): enter on a break
                  above the first-5-min high; stop = first-5-min low. Tightest stop.
  B GDL-RECLAIM   (intraday U&R): enter on the first reclaim of the gap-day-low; stop =
                  gap-day-low. The structural reference.

Per tactic: entry, stop, risk% = (entry-stop)/entry, intraday MFE% (max high after entry
/ entry), R = MFE/risk. Compares fill-rate + median risk + median R across the cohort.
Read-only (a pulled minute-bar snapshot); gate-free.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BARS = HERE / "_270_intraday_bars.tsv"

# (ticker, trigger_date) -> gap_day_low (the reclaim/stop reference), from the cohort run.
GDL = {
    ("ZD", "2026-03-20"): 41.11, ("CNTA", "2026-04-14"): 39.57, ("SILO", "2026-04-16"): 6.90,
    ("RLMD", "2026-04-17"): 5.80, ("CMPS", "2026-04-24"): 8.63, ("ROLR", "2026-04-27"): 7.20,
    ("MXL", "2026-04-29"): 53.70, ("HCAI", "2026-04-30"): 9.91, ("RLYB", "2026-05-04"): 9.35,
    ("CAMP", "2026-05-13"): 4.19, ("EVC", "2026-05-13"): 6.37, ("TRT", "2026-05-14"): 10.76,
    ("ASTI", "2026-05-22"): 4.00, ("STRL", "2026-05-28"): 704.10, ("BLZE", "2026-05-29"): 7.12,
    ("KFRC", "2026-05-29"): 39.24, ("HCAI", "2026-06-10"): 7.21, ("MNTS", "2026-06-11"): 11.86,
}
RTH_OPEN, RTH_CLOSE = 9 * 60 + 30, 16 * 60   # ET minutes


def load_rth():
    """Group RTH minute bars by (ticker, et_date). Polygon t is UTC ms; ET = UTC-4 (EDT)."""
    by = defaultdict(list)
    for line in BARS.read_text(encoding="utf-8").splitlines():
        p = line.rstrip("\r").split("\t")
        if len(p) != 7 or p[0].startswith("#"):
            continue
        tk, tms, o, h, l, c, v = p
        et = datetime.fromtimestamp(int(tms) / 1000, timezone.utc) - timedelta(hours=4)
        minute = et.hour * 60 + et.minute
        if not (RTH_OPEN <= minute < RTH_CLOSE):
            continue
        by[(tk, et.date().isoformat())].append(
            {"m": minute, "o": float(o), "h": float(h), "l": float(l), "c": float(c)})
    for k in by:
        by[k].sort(key=lambda b: b["m"])
    return by


def entry_first5(bars, gdl):
    """Break above first-5-min high; stop = first-5-min low."""
    or5 = [b for b in bars if RTH_OPEN <= b["m"] < RTH_OPEN + 5]
    if not or5:
        return None
    hi, lo = max(b["h"] for b in or5), min(b["l"] for b in or5)
    for i, b in enumerate(bars):
        if b["m"] < RTH_OPEN + 5:
            continue
        if b["h"] > hi:                      # the break
            entry, stop = hi, lo
            if entry <= stop or entry <= gdl * 0.98:   # must be a real reclaim
                return None
            mfe = max(x["h"] for x in bars[i:]) / entry - 1
            return entry, stop, mfe
    return None


def entry_gdl(bars, gdl):
    """First reclaim of the gap-day-low; stop = gap-day-low."""
    for i, b in enumerate(bars):
        if b["c"] > gdl:
            entry, stop = b["c"], gdl
            if entry <= stop:
                return None
            mfe = max(x["h"] for x in bars[i:]) / entry - 1
            return entry, stop, mfe
    return None


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2] if s else float("nan")


def main():
    by = load_rth()
    rows = []
    for (tk, d), gdl in sorted(GDL.items(), key=lambda kv: kv[0][1]):
        bars = by.get((tk, d))
        if not bars:
            rows.append((d, tk, None, None))
            continue
        rows.append((d, tk, entry_first5(bars, gdl), entry_gdl(bars, gdl)))

    print(f"intraday entry replay: {sum(1 for _,_,a,b in rows if a or b)} of {len(rows)} "
          f"trigger days with RTH bars\n")
    print(f"{'date':<11}{'tk':<6}  {'FIRST5-BREAK (entry/stop risk% -> MFE% = R)':<46}  GDL-RECLAIM")
    aggA, aggB = [], []
    for d, tk, a, b in rows:
        def fmt(x, agg):
            if not x:
                return "—"
            e, s, mfe = x
            risk = (e - s) / e
            r = mfe / risk if risk > 0 else 0
            agg.append((risk, mfe, r))
            return f"{e:.2f}/{s:.2f} {risk*100:.0f}% -> {mfe*100:+.0f}% = {r:.1f}R"
        print(f"{d:<11}{tk:<6}  {fmt(a, aggA):<46}  {fmt(b, aggB)}")

    for name, agg in (("FIRST5-BREAK", aggA), ("GDL-RECLAIM", aggB)):
        if agg:
            risks = [x[0] for x in agg]; mfes = [x[1] for x in agg]; rs = [x[2] for x in agg]
            wins = sum(1 for m in mfes if m >= 0.05)
            print(f"\n{name}: fills {len(agg)}/{len(rows)} | median risk {median(risks)*100:.0f}% | "
                  f"median MFE {median(mfes)*100:+.0f}% | median {median(rs):.1f}R | "
                  f">=+5% MFE {wins}/{len(agg)} ({wins/len(agg)*100:.0f}%)")
    print("\n(MFE = intraday max-favorable-excursion after entry; risk = stop distance. "
          "Tighter stop -> more R on the same move — the U&R-paradox edge.)")


if __name__ == "__main__":
    main()
