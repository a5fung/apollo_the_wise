"""#559 era-D re-cut — step 1: POPULATION COMPOSITION from capture 1 (c1_scope.out). $0, no network.
Prints the deduped ticker-day classes, their tick windows, minute-bar coverage, and the pair list
capture 2 must fetch. Nothing here is a result; it is the population check that comes first."""
from __future__ import annotations

from collections import Counter, defaultdict

from readcap import read_sections

S = read_sections("c1_scope.out")
ev = S["EVENTS"]
CLS = ["ep_rt_universe_catch", "ep_rt_floor_flip_up", "ep_rt_admit", "ep_rt_live_miss"]


def win(t: str) -> str:
    if "09:31" <= t <= "09:44":
        return "inwin"
    if t < "09:30":
        return "preopen"
    return "0930" if t == "09:30" else "late"


first: dict[tuple, dict] = {}
for r in ev:
    if r["event_type"] not in CLS:
        continue
    k = (r["d"], r["ticker"], r["event_type"])
    if k not in first or r["tick_et"] < first[k]["tick_et"]:
        first[k] = r

print("event rows", len(ev), "| deduped (day,ticker,class)", len(first))
c = Counter()
for (d, t, e), r in first.items():
    c[(e, win(r["tick_et"]), r["authoritative"])] += 1
for k in sorted(c):
    print("  ", k, c[k])

union: dict[tuple, dict] = {}
for (d, t, e), r in first.items():
    k = (d, t)
    if k not in union or r["tick_et"] < union[k]["tick_et"]:
        union[k] = r
cu = Counter(win(r["tick_et"]) for r in union.values())
days = sorted({d for d, _ in union})
print("UNION ticker-days", len(union), dict(cu), "| days", len(days), days[0], days[-1])

cov = {(r["ticker"], r["d"]): r for r in S["COVERAGE"]}
print("coverage pairs", len(cov))
for lab, keys in [("union-inwin", [k for k, r in union.items() if win(r["tick_et"]) == "inwin"]),
                  ("union-preopen", [k for k, r in union.items() if win(r["tick_et"]) == "preopen"]),
                  ("union-all", list(union))]:
    n = len(keys)
    has930 = sum(1 for d, t in keys if cov.get((t, d), {}).get("has_930") == "t")
    orb = sum(1 for d, t in keys if int(cov.get((t, d), {}).get("orb_bars", 0) or 0) >= 10)
    rth = sum(1 for d, t in keys if int(cov.get((t, d), {}).get("rth_bars", 0) or 0) >= 300)
    print(f"  {lab}: n={n} has_0930={has930} orb_bars>=10: {orb} rth_bars>=300: {rth}")

al = S["ALERTS"]
alk = {(r["alert_date"], r["ticker"]) for r in al}
print("alerts", len(al), "HIGH", sum(1 for r in al if r["score_tier"] == "HIGH"),
      "pre-open HIGH", sum(1 for r in al if r["score_tier"] == "HIGH" and r["detected_et"] < "09:30:00"),
      "alert days", len({r["alert_date"] for r in al}))
print("alert pair minute coverage (rth bars):",
      [(r["ticker"], r["alert_date"], cov.get((r["ticker"], r["alert_date"]), {}).get("rth_bars")) for r in al])
print("alerts inside the event union:", sum(1 for k in alk if k in union), "of", len(alk))
print("in-window crossers that alerted:",
      [(d, t, union[(d, t)]["event_type"], union[(d, t)]["tick_et"]) for (d, t) in union
       if win(union[(d, t)]["tick_et"]) == "inwin" and (d, t) in alk])

sl = S["SCANLOG"]
slk = defaultdict(list)
for r in sl:
    slk[(r["scan_date"], r["ticker"])].append(r)
print("scanlog pairs", len(slk), "| union pairs with scan-log rows", sum(1 for k in union if k in slk))
inwin_nolog = [k for k, r in union.items() if win(r["tick_et"]) == "inwin" and k not in slk]
print("in-window crossers with NO scan-log row:", len(inwin_nolog), inwin_nolog[:12])

# the pair list capture 2 must cover: event union ∪ alerts ∪ trades
tr = S["TRADES"]
pairs = set(union) | alk | {(r["alert_date"], r["ticker"]) for r in tr}
print("capture-2 pairs:", len(pairs), "tickers:", len({t for _, t in pairs}))
