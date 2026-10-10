"""#559 era-D re-cut — step 1b: what the LIVE scan did with each in-window crosser (scan-log fate).
Prints the distinct filter_reason prefixes and the furthest stage per in-window ticker-day, so the
'gate-passing subset' is defined from recorded fates, not re-derived gates. $0, reads capture 1."""
from __future__ import annotations

from collections import Counter, defaultdict

from readcap import read_sections

S = read_sections("c1_scope.out")
CLS = ["ep_rt_universe_catch", "ep_rt_floor_flip_up", "ep_rt_admit", "ep_rt_live_miss"]


def win(t):
    if "09:31" <= t <= "09:44":
        return "inwin"
    return "preopen" if t < "09:30" else ("0930" if t == "09:30" else "late")


first = {}
for r in S["EVENTS"]:
    if r["event_type"] not in CLS:
        continue
    k = (r["d"], r["ticker"])
    if k not in first or r["tick_et"] < first[k]["tick_et"]:
        first[k] = r
inwin = {k: r for k, r in first.items() if win(r["tick_et"]) == "inwin"}
sl = defaultdict(list)
for r in S["SCANLOG"]:
    sl[(r["scan_date"], r["ticker"])].append(r)
alerts = {(r["alert_date"], r["ticker"]): r for r in S["ALERTS"]}

reasons = Counter()
for k in inwin:
    for r in sl[k]:
        fr = (r["filter_reason"] or "").strip()
        reasons[fr.split(":")[0][:50] if fr else "(none)"] += 1
print("filter_reason prefixes over in-window crossers' scan-log rows:")
for k, v in reasons.most_common():
    print(f"  {v:4d}  {k}")

print("\nper in-window crosser: class, tick, scan rows, last reason, max score, tier, alerted?")
for k in sorted(inwin, key=lambda x: (x[0], x[1])):
    rows = sorted(sl[k], key=lambda r: r["scan_et"])
    last = rows[-1] if rows else {}
    scores = [float(r["ep_score"]) for r in rows if r["ep_score"]]
    tiers = {r["score_tier"] for r in rows if r["score_tier"]}
    rs = {(r["filter_reason"] or "").split(":")[0][:40] for r in rows}
    print(f"  {k[0]} {k[1]:6s} {inwin[k]['event_type'][6:]:18s} @{inwin[k]['tick_et']} rows={len(rows):2d} "
          f"reasons={sorted(rs)} maxscore={max(scores) if scores else None} tiers={sorted(tiers)} "
          f"alert={'YES ' + alerts[k]['score_tier'] if k in alerts else '-'}")
