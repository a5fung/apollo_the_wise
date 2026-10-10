"""#655 scope Q-B: would a co-movement test at Pass 1.5 (the ruling-(a) rule ported: keep the small theme when >= 2
of its members are judged against the absorbing theme and none passes 0.35; otherwise absorb as today) have kept
the Pass-1.5 exits of the 14 nights? Rosters = each theme's row on the previous engine night (the merge input is not
stored; t_size in the row is checked against it). $0."""
import re, sys
from collections import defaultdict
from datetime import date
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from load import load
from agents.market_intelligence import market_adjusted_correlation as mac
b = load()
on = defaultdict(dict)
for r in b["themes"]:
    if r["stage"] != "Retired" and r["tickers"]:
        on[r["d"]][r["name"]] = r
nights = sorted(on)
flipnames = set()
for ln in open("b1_churn.out"):
    m = re.match(r"  (.*?) \| (\d{4}-\d\d-\d\d) \| Pass-1.5", ln)
    if m: flipnames.add((m.group(1), m.group(2)))
cl = b["closes"]
def excess_for(d):
    s = mac.session_index(cl["SPY"], d); mk = mac.log_returns(cl["SPY"], s)
    return mac.excess_returns(cl, s, mk)
EX = {}
kept = absorbed = unk = 0
for e in b["events"]:
    if e["event_type"] != "theme_pass1_5_absorption": continue
    d = date.fromisoformat(e["et"][:10])
    if d < date(2026, 9, 22): continue
    det = e["detail"]
    t = re.search(r"t='(.*?)' t_score", det).group(1); tg = re.search(r"target='(.*?)' target_score", det).group(1)
    tsz = int(re.search(r"t_size=(\d+)", det).group(1))
    prev = [x for x in nights if x < d][-1]
    src = on[prev].get(t) or on[d].get(t); tgt = on[d].get(tg) or on[prev].get(tg)
    if not src or not tgt:
        print(f"{d} | {t[:50]} -> {tg[:45]} | roster not found (newborn that night) | t_size {tsz}"); unk += 1; continue
    ex = EX.setdefault(d, excess_for(d))
    others = [m for m in src["tickers"] if m not in tgt["tickers"]]
    bs = mac.build_baskets([{"name": "x", "stage": "x", "tickers": tgt["tickers"]}], ex, stages=("x",))
    res = {}
    for m in others:
        if m in ex and bs:
            c, n, _ = mac.correlate(ex[m], bs[0]); res[m] = None if c is None else round(c, 2)
        else: res[m] = None
    judged = [v for v in res.values() if v is not None]
    keep = len(judged) >= 2 and all(v < 0.35 for v in judged)
    kept += keep; absorbed += not keep
    fl = "FLIPPED" if (t[:70], str(d)) in {(a[:70], b_) for a, b_ in flipnames} else ""
    print(f"{d} | {t[:50]} ({len(src['tickers'])}, roster-row t_size {tsz}) -> {tg[:45]} | not already in target {res} | {'KEEP' if keep else 'absorb'} {fl}")
print(f"Pass-1.5 rows in window: kept {kept}, absorbed {absorbed}, roster unknown {unk}")
