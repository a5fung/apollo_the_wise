"""re-verify #694: on each crowded morning, for every ordering, does the rank-20/21 boundary fall inside a group
whose sort values are IDENTICAL up to the final A->Z (i.e. the cut is decided alphabetically, not by the key)?
Pre-market $ (k2) before 08-29 is DERIVED from rel_volume rounded to 2 decimals, so many rows derive to exactly 0.
Local only, reads dataset.csv; reimplements score.py's ordering (does not import it, it prints on import)."""
import csv, sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent; B = HERE.parent
sys.path.insert(0, str(B.parents[2]))
from agents.market_intelligence.ep_rubric import shortlist_prescore, shortlist_sort_key
F = lambda x: float(x) if x not in ("", None) else None
KEYS = {"adv$": ("k1_adv_dollar", 1), "pm$": ("k2_pm_dollar", 1), "pm_rvol": ("k3_pm_rvol", 1),
        "rs_comp": ("k4_rs_composite", 1), "zones": ("k5_zones", 1), "gap": ("k6_gap", 1)}
rows = [r for r in csv.DictReader(open(B / "dataset.csv")) if r["pool"] == "1"]
days = defaultdict(list)
for r in rows:
    for c, _ in KEYS.values(): r[c] = F(r[c])
    r["compB"] = shortlist_prescore(adv_dollar=r["k1_adv_dollar"], gap_pct=F(r["gap_pct"]), in_active_theme=r["in_theme"] == "1")["composite"]
    days[r["scan_date"]].append(r)
def key_wo_alpha(r, kind, kid):
    col, s = KEYS[kid]; v = r[col]
    miss = (1, 0.0) if v is None else (0, -s * v)
    return ((-r["compB"],) if kind == "T" else ()) + miss
n_alpha = 0
for d, rs in sorted(days.items()):
    if len(rs) <= 20: continue
    for kind in ("T", "S"):
        for kid in KEYS:
            o = sorted(rs, key=lambda r: key_wo_alpha(r, kind, kid) + (r["ticker"],))
            k20, k21 = key_wo_alpha(o[19], kind, kid), key_wo_alpha(o[20], kind, kid)
            if k20 == k21:
                grp = [r["ticker"] for r in o if key_wo_alpha(r, kind, kid) == k20]
                kept = [t for t in grp if o.index(next(x for x in o if x["ticker"] == t)) < 20]
                lab = [(r["ticker"], r["label"]) for r in o if r["label"] and key_wo_alpha(r, kind, kid) == k20]
                n_alpha += 1
                val = "missing" if k20[-2] == 1 else f"value {-k20[-1]:.0f}"
                print(f"{d} {kind}:{kid:8} cut decided A->Z inside a {len(grp)}-name group ({val}): kept {kept} cut {[t for t in grp if t not in kept]}"
                      + (f"  LABELLED in group: {lab}" if lab else ""))
print(f"total crowded-morning orderings whose 20-cut is decided alphabetically: {n_alpha}")
