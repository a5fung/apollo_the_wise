"""re-verify #694: pre-market $ (k2) before 08-29 is DERIVED as rel_volume x adv x prev_close x (1+gap/100), and
rel_volume is logged rounded to 2 decimals (ep_detector._snap_candidate / ADV backfill: round(today_volume/adv, 2)).
So each derived value is only known to lie in [(rel-0.005), (rel+0.005)] x adv x price (floored at 0). This bounds the
real-EP pair-weighted separation for k2 (best case / worst case over those intervals) and counts exact-zero rows.
Local only (dataset.csv + q03_pool.out for rel_volume/adv)."""
import csv
from collections import defaultdict
from pathlib import Path
B = Path(__file__).resolve().parent.parent
F = lambda x: float(x) if x not in ("", None) else None
raw = {}
for r in csv.DictReader(open(B / "q03_pool.out"), delimiter="|"):
    if r.get("ticker") and not r["scan_date"].startswith("("):
        raw[(r["scan_date"], r["ticker"])] = r
rows = [r for r in csv.DictReader(open(B / "dataset.csv")) if r["pool"] == "1"]
days = defaultdict(list)
for r in rows:
    v = F(r["k2_pm_dollar"])
    if r["k2_src"] == "derived":
        q = raw[(r["scan_date"], r["ticker"])]
        rel, adv, pc, gap = F(q["rel_volume"]), F(q["adv"]), F(q["prev_close"]), F(q["gap_pct"])
        px = pc * (1 + gap / 100)
        lo, hi = max(0.0, (rel - 0.005)) * adv * px, (rel + 0.005) * adv * px
    else:
        lo = hi = v
    r["v"], r["lo"], r["hi"] = v, lo, hi
    days[r["scan_date"]].append(r)
zero = [r for r in rows if r["k2_src"] == "derived" and r["v"] == 0]
print(f"derived rows {sum(r['k2_src']=='derived' for r in rows)}; derived to exactly 0: {len(zero)}; labelled among them: {[(r['ticker'], r['scan_date'], r['label']) for r in zero if r['label']]}")
def auc(group, mode):
    win = n = 0
    for d, rs in days.items():
        for p in rs:
            if p["label"] not in group: continue
            for m in rs:
                if m["label"]: continue
                n += 1
                if mode == "point":
                    a, b = p["v"], m["v"]
                elif mode == "best":    # labelled name at its top, mate at its bottom
                    a, b = p["hi"], m["lo"]
                else:                   # worst: labelled at bottom, mate at top
                    a, b = p["lo"], m["hi"]
                win += 1 if a > b else (0.5 if a == b else 0)
    return win / n, n
for g, name in ((("REAL_EP",), "real EPs"), (("GOOD_CHART", "OKISH_CHART"), "GOOD/OKISH"), (("BAD_CHART",), "BAD (lower better => 1-x)")):
    pt, n = auc(g, "point"); be, _ = auc(g, "best"); wo, _ = auc(g, "worst")
    print(f"{name:28} pairs {n:4}  as built {pt:.3f}   bounds from rounding: worst {wo:.3f} .. best {be:.3f}")
