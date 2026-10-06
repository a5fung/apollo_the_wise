"""#327 G12: classify EP-day (day 0) minute coverage from minute.tsv.gz (RTH bars, 09:30<=t<16:00 ET).
full >= 300 RTH bars (reproduces the 09-27 doc: 212 full of 261 ERA A) ; partial 100-299 ; one-bar < 100 ; none 0.
Writes sat_day0_targets.tsv = every campaign whose EP day is not full."""
import csv, gzip, collections, datetime as dt
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
al = [r for r in csv.DictReader(open("alerts.tsv"), delimiter="|") if r["alert_date"]]
rth = collections.Counter(); first = {}; last = {}
for r in csv.DictReader(gzip.open("minute.tsv.gz", "rt"), delimiter="|"):
    if not r["t_ms"]: continue
    k = (r["ticker"], r["d"])
    t = int(r["t_ms"]) / 1000
    m = dt.datetime.fromtimestamp(t, dt.timezone.utc).astimezone(ET)
    mm = m.hour * 60 + m.minute
    if 570 <= mm < 960:
        rth[k] += 1
        first[k] = min(first.get(k, 9999), mm); last[k] = max(last.get(k, -1), mm)
out = []; cls = collections.Counter(); span_odd = []
for a in al:
    k = (a["ticker"], a["alert_date"]); n = rth.get(k, 0)
    c = "none" if n == 0 else "one_bar" if n < 100 else "partial" if n < 300 else "full"
    cls[(a["era"], c)] += 1
    if c == "full" and (first[k] > 575 or last[k] < 955): span_odd.append((a["ticker"], a["alert_date"], n, first[k], last[k]))
    if c != "full": out.append((a["era"], a["ticker"], a["alert_date"], c, n))
print(dict(cls)); print("full-but-not-spanning-session:", span_odd)
with open("sat_day0_targets.tsv", "w") as f:
    f.write("era|ticker|alert_date|class|rth_bars\n")
    for x in out: f.write("|".join(map(str, x)) + "\n")
print(len(out), "targets")
