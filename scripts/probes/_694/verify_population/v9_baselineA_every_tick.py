"""verify #694: baseline A (today's live pre-open order: theme first, then A->Z, top 20 graded) applied at EVERY
pre-open tick on the crowded real-EP days. A real EP inside the top 20 at ANY pre-open tick gets graded that morning
(later ticks then log it 'already scored earlier today'). Theme set rebuilt with build_dataset.py's rule (re-implemented
here, not imported, so the build's files are not rewritten). Local only."""
import csv, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
HERE = Path(__file__).resolve().parent; B = HERE.parent
sys.path.insert(0, str(B.parents[2]))
from agents.market_intelligence.ep_rubric import shortlist_prescore, shortlist_sort_key
by_name = defaultdict(list)
for r in csv.DictReader(open(B / "q09_themes.out"), delimiter="|"):
    if not r.get("theme_date") or r["name"].startswith("("): continue
    by_name[r["name"]].append((r["theme_date"], r["stage"], set(filter(None, (r["tickers"] or "").split(",")))))
for v in by_name.values(): v.sort(key=lambda x: x[0])
def theme_set(d):
    dd = date.fromisoformat(d); lo, hi = (dd - timedelta(days=7)).isoformat(), (dd - timedelta(days=1)).isoformat()
    out = set()
    for snaps in by_name.values():
        latest = None
        for td, st, tk in snaps:
            if lo <= td <= hi: latest = (td, st, tk)
        if latest and latest[1] in ("Accelerating", "Mainstream"): out |= latest[2]
    return out
ticks = defaultdict(list)
for r in csv.DictReader(open(HERE / "v9_ticks_positive_days.out"), delimiter="|"):
    if not r.get("tick") or r["scan_date"].startswith("("): continue
    ticks[(r["scan_date"], r["tick"])].append(r["ticker"])
POS = {"2026-05-06": ["UMC", "ARM"], "2026-05-07": ["SNOW"], "2026-08-04": ["PLTR"], "2026-08-07": ["TEAM"]}
for d, names in POS.items():
    ts = theme_set(d)
    for p in names:
        hits = []
        for (dd, t), tk in sorted(ticks.items()):
            if dd != d or p not in tk: continue
            order = sorted(tk, key=lambda x: shortlist_sort_key(x, shortlist_prescore(adv_dollar=None, gap_pct=10.0, in_active_theme=x in ts)["composite"], None))
            rk = order.index(p) + 1
            hits.append((t[:8], rk, len(tk)))
        inside = [h for h in hits if h[1] <= 20]
        print(f"{d} {p}: present at {len(hits)} pre-open ticks; inside top 20 under live order at {len(inside)}"
              + (f"; first {inside[0][0]} rank {inside[0][1]} of {inside[0][2]}" if inside else "")
              + f"; last tick {hits[-1][0]} rank {hits[-1][1]} of {hits[-1][2]}")
