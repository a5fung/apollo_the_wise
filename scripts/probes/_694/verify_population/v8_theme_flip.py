"""verify #694: flip the 3 rebuilt theme flags that disagree with the logged alert flag (BW 05-11, POET 05-14,
GFS 05-21) and redo every ordering's cut list on the crowded days among them. Local only."""
import csv, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; B = HERE.parent
sys.path.insert(0, str(B.parents[2]))
from agents.market_intelligence.ep_rubric import shortlist_prescore, shortlist_sort_key
ds = [r for r in csv.DictReader(open(B / "dataset.csv")) if r["pool"] == "1"]
flip = {("2026-05-11", "BW"), ("2026-05-14", "POET"), ("2026-05-21", "GFS")}
KEYS = {"adv$": ("k1_adv_dollar", 1), "pm$": ("k2_pm_dollar", 1), "pm_rvol": ("k3_pm_rvol", 1),
        "rs_comp": ("k4_rs_composite", 1), "zones": ("k5_zones", 1), "gap": ("k6_gap", 1)}
def f(x): return float(x) if x not in ("", None) else None
def orders(rs):
    out = {}
    for r in rs:
        adv = f(r["k1_adv_dollar"])
        r["cB"] = shortlist_prescore(adv_dollar=adv, gap_pct=f(r["gap_pct"]), in_active_theme=r["th"])["composite"]
        r["cA"] = shortlist_prescore(adv_dollar=None, gap_pct=f(r["gap_pct"]), in_active_theme=r["th"])["composite"]
    out["A"] = [r["ticker"] for r in sorted(rs, key=lambda r: shortlist_sort_key(r["ticker"], r["cA"], None))[20:]]
    out["B"] = [r["ticker"] for r in sorted(rs, key=lambda r: shortlist_sort_key(r["ticker"], r["cB"], f(r["k1_adv_dollar"])))[20:]]
    for k, (col, s) in KEYS.items():
        def key(r, col=col, s=s):
            v = f(r[col]); return (-r["cB"],) + ((1, 0.0) if v is None else (0, -s * v)) + (r["ticker"],)
        out["T:" + k] = sorted([r["ticker"] for r in sorted(rs, key=key)[20:]])
    return out
for day in sorted({d for d, _ in flip}):
    rs = [dict(r) for r in ds if r["scan_date"] == day]
    print(day, "pool", len(rs))
    if len(rs) <= 20: continue
    for r in rs: r["th"] = r["in_theme"] == "1"
    old = orders(rs)
    for r in rs:
        if (day, r["ticker"]) in flip: r["th"] = not r["th"]
    new = orders(rs)
    for k in old:
        print(f"  {k:9}", "SAME" if sorted(old[k]) == sorted(new[k]) else f"CHANGED as built {sorted(old[k])} -> flipped {sorted(new[k])}")
