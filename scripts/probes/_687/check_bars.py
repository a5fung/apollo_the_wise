"""#687 INDEPENDENT CHECK (6a) — held-day minute-bar integrity (never checked by the study) and the RTH-vs-daily low
convention, on captured files only. Writes check_bars.txt."""
import collections, csv
from datetime import date, time
from pathlib import Path
import check_walk as CW
HERE = Path(__file__).resolve().parent
O = open(HERE / "check_bars.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); O.write(s + "\n")
daily = CW.load_daily()
held = CW.load_min(["minutes_held.tsv.gz"])
ent = CW.load_min(["minutes_entry.tsv.gz", "minutes_entry2.tsv.gz"])
lt = list(csv.DictReader(open(HERE / "line_tests.tsv"), delimiter="|"))
def cmp(sets, label):
    c = collections.Counter(); worst = []
    for (t, d), bars in sets:
        db = daily.get(t, {}).get(d)
        if not db or not bars:
            c["no_daily_or_bars"] += 1; continue
        o, h, l, cl, v = db
        mo = bars[0][1][0] if bars[0][0] == time(9, 30) else None
        mh = max(b[1] for _, b in bars); ml = min(b[2] for _, b in bars); mc = bars[-1][1][3]
        c["days"] += 1
        c["low_equal_(1c)"] += abs(ml - l) <= 0.011
        c["low_within_1%"] += abs(ml - l) / l <= 0.01
        c["daily_low_BELOW_rth_low_>1c"] += (l < ml - 0.011)
        c["high_within_1%"] += abs(mh - h) / h <= 0.01
        c["close_within_1%"] += abs(mc - cl) / cl <= 0.01
        if mo is not None:
            c["open_within_0.5%"] += abs(mo - o) / o <= 0.005
        dev = max(abs(ml - l) / l, abs(mh - h) / h)
        if dev > 0.02:
            worst.append((t, str(d), round(ml, 4), l, round(mh, 4), h, round(dev * 100, 1)))
    P(f"   {label}: {dict(c)}; days with RTH high/low > 2% off the daily bar {len(worst)}: {sorted(worst, key=lambda x: -x[6])[:12]}")
    return worst
P("# #687 CHECK (6a) BAR INTEGRITY — Polygon RTH minute bars vs mi_daily_closes on the SAME day")
w_h = cmp([((r["ticker"], date.fromisoformat(r["day"])), held.get((r["ticker"], date.fromisoformat(r["day"])))) for r in lt], "656 HELD line-test days")
# for a line-test day, what matters is whether the RTH low reaches the line exactly as the daily low does
flip = []
for r in lt:
    k = (r["ticker"], date.fromisoformat(r["day"])); bars = held.get(k)
    if not bars:
        continue
    ml = min(b[2] for _, b in bars); line = float(r["line"])
    if ml > line + 1e-9:
        flip.append((k[0], str(k[1]), line, float(r["low"]), ml, r["cls"], r["A0_action"]))
P(f"   line-test days whose daily low reached the line but the RTH minute low did NOT (a touch that exists only outside RTH or in the daily feed): "
  f"{len(flip)}: {flip[:15]}")
P(f"   of those, days where A0 is recorded as stopped on that day: {sum(1 for x in flip if x[6] == 'stop_hit')}")
cmp([(k, v) for k, v in ent.items() if k[0] in daily], "entry days (all fetched)")
O.close()
