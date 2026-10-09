"""verify #694 (f): 4 zones rows whose daily history is on a later split-adjusted scale. Rescale the history
to the scan row's prev_close, recompute zones with the UNCHANGED encoder, and redo the zones cut lists."""
import csv, sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent; B = HERE.parent
sys.path.insert(0, str(B.parents[2])); sys.path.insert(0, str(B.parent))
import _533_nbis_structure_encoder as nbis
from agents.market_intelligence.ep_rubric import shortlist_prescore
daily = defaultdict(list)
for ln in open(B / "q10_daily.out"):
    p = ln.rstrip("\n").split("|")
    if len(p) != 7 or p[1] < "2025-07-07": continue
    try: o, h, l, c, v = (float(x) if x else None for x in p[2:7])
    except ValueError: continue
    if None in (o, h, l, c) or c <= 0 or h <= 0: continue
    daily[p[0]].append((p[1], o, h, l, c, v or 0.0))
for t in daily: daily[t].sort()
ds = [r for r in csv.DictReader(open(B / "dataset.csv")) if r["pool"] == "1"]
fix = {("2026-05-06", "ELPW"), ("2026-05-08", "AXTU"), ("2026-05-11", "AIXI"), ("2026-05-29", "VWAV")}
newz = {}
for r in ds:
    if (r["scan_date"], r["ticker"]) not in fix: continue
    d, t, px, pc = r["scan_date"], r["ticker"], float(r["tick_price"]), float(r["prev_close"])
    hist = [x for x in daily[t] if x[0] < d]
    k = pc / hist[-1][4]
    hist = [(x[0], x[1]*k, x[2]*k, x[3]*k, x[4]*k, x[5]) for x in hist]
    res = nbis.encode(t, d, {t: hist + [(d, px, px, px, px, 0.0)]}, {}, preopen=True)
    newz[(d, t)] = None if res.get("error") else int(res["n_cleared"])
    print(d, t, "scale", round(k, 4), "zones as built", r["k5_zones"] or "-", "rescaled", newz[(d, t)], res.get("cls"), res.get("error"))
def cuts(rs, kind):
    def key(r):
        v = r["z"]
        miss = (1, 0.0) if v is None else (0, -v)
        return ((-r["c"],) if kind == "T" else ()) + miss + (r["ticker"],)
    return [r["ticker"] for r in sorted(rs, key=key)[20:]]
for day in sorted({d for d, _ in fix}):
    rs = [dict(r) for r in ds if r["scan_date"] == day]
    if len(rs) <= 20: print(day, "pool", len(rs), "not crowded"); continue
    for r in rs:
        adv = float(r["k1_adv_dollar"]) if r["k1_adv_dollar"] else None
        r["c"] = shortlist_prescore(adv_dollar=adv, gap_pct=float(r["gap_pct"]), in_active_theme=r["in_theme"] == "1")["composite"]
        r["z"] = float(r["k5_zones"]) if r["k5_zones"] else None
    old = {k: cuts(rs, k) for k in "TS"}
    for r in rs:
        if (day, r["ticker"]) in newz: r["z"] = newz[(day, r["ticker"])]
    new = {k: cuts(rs, k) for k in "TS"}
    for k in "TS":
        print(day, f"{k}:zones cut as built", old[k], "| rescaled", new[k], "| SAME" if old[k] == new[k] else "| CHANGED")
