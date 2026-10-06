"""Local validation of sat_day0_raw.tsv (no network): per-target bar counts vs the stored minute.tsv.gz bars and vs daily.tsv / sat_daily_long.tsv."""
import csv, gzip, collections, datetime as dt
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
def mm(t): e = dt.datetime.fromtimestamp(t/1000, dt.timezone.utc).astimezone(ET); return e.hour*60+e.minute
new = collections.defaultdict(dict)
for r in csv.DictReader(gzip.open("sat_day0_minutes.tsv.gz","rt"), delimiter="|"):
    if r["t_ms"]: new[(r["ticker"], r["d"])][int(r["t_ms"])] = (float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]))
tg = [r for r in csv.DictReader(open("sat_day0_targets.tsv"), delimiter="|") if r["alert_date"]]
keys = {(r["ticker"], r["alert_date"]) for r in tg}
old = collections.defaultdict(dict)
for r in csv.DictReader(gzip.open("minute.tsv.gz", "rt"), delimiter="|"):
    k = (r["ticker"], r["d"])
    if k in keys and r["t_ms"] and 570 <= mm(int(r["t_ms"])) < 960:
        old[k][int(r["t_ms"])] = (float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]))
daily = {}
for r in csv.DictReader(open("sat_daily_long.tsv"), delimiter="|"):
    if (r["ticker"], r["trade_date"]) in keys: daily[(r["ticker"], r["trade_date"])] = tuple(float(r[c]) for c in ("open_price","high_price","low_price","close","volume"))
print("ticker|d|class_before|old_n|new_n|old_subset_of_new|old_vals_match|o_dev%|h_dev%|l_dev%|c_dev%|vol_ratio|gaps>15min")
res = []
for r in tg:
    k = (r["ticker"], r["alert_date"]); n = new.get(k, {}); o = old.get(k, {})
    ts = sorted(n)
    sub = all(t in n for t in o); match = sum(1 for t in o if t in n and all(abs(a-b) < 1e-6 for a, b in zip(o[t], n[t])))
    d = daily.get(k)
    if n and d:
        bars = [n[t] for t in ts]
        dev = lambda a, b: round(100*(a-b)/b, 2)
        no, nh, nl, nc = bars[0][0], max(b[1] for b in bars), min(b[2] for b in bars), bars[-1][3]
        vr = round(sum(b[4] for b in bars)/d[4], 3)
        ds = (dev(no, d[0]), dev(nh, d[1]), dev(nl, d[2]), dev(nc, d[3]), vr)
    else: ds = ("", "", "", "", "")
    mins = [mm(t) for t in ts]; gap = max([b-a for a, b in zip(mins, mins[1:])] or [0])
    print("|".join(map(str, (k[0], k[1], r["class"], len(o), len(n), sub, f"{match}/{len(o)}") + ds + (gap,))))
