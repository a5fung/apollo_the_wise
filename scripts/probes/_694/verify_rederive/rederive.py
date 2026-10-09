"""Independent re-derivation of the #694 tie-breaker test (verifier, 2026-10-08).
Reads ONLY the captured raw pulls (q03/q07/q08/q09) + the label fixtures. Does not import
build_dataset.py / score.py / dataset.csv. Production formulas copied by reading:
  ep_rubric.shortlist_prescore / shortlist_sort_key, ep_shortlist_shadow.compute_shortlist_ranking,
  db.get_adv_map (adv_20 where truthy), db._pick_latest_complete_score_date, db.get_active_themes.
"""
import sys, csv, statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS
from tests.fixtures.must_not_trade_charts import CHART_RULINGS

def rd(p):
    lines = [l.rstrip("\n") for l in open(p) if l.strip() and not l.startswith("(")]
    hdr = lines[0].split("|")
    return [dict(zip(hdr, l.split("|"))) for l in lines[1:]]

def f(x):
    return None if x in ("", None) else float(x)

pool = rd(HERE / "q03_pool.out")
counts = [(date.fromisoformat(r["score_date"]), int(r["n"])) for r in rd(HERE / "q07_score_counts.out")]
scores = {}
for r in rd(HERE / "q08_scores.out"):
    scores[(r["ticker"], r["score_date"])] = r
themes = rd(HERE / "q09_themes.out")

# labels
lab = {}
for m in MUST_NOT_MISS:
    if m.alert_date >= "2026-04-13":
        lab[(m.ticker, m.alert_date)] = "REAL_EP"
for c in CHART_RULINGS:
    if c.verdict in ("GOOD_CHART", "OKISH_CHART", "BAD_CHART"):
        lab.setdefault((c.ticker, c.alert_date), c.verdict)
alllab = {(c.ticker, c.alert_date) for c in CHART_RULINGS} | {(m.ticker, m.alert_date) for m in MUST_NOT_MISS}

def prior_complete(d):
    c = sorted([x for x in counts if x[0] < d], reverse=True)
    rec = sorted(n for _, n in c[:10]); mid = len(rec)//2
    med = rec[mid] if len(rec) % 2 else (rec[mid-1]+rec[mid])/2
    for dd, n in c:
        if n >= 0.5*med:
            return dd

def theme_set(d, include_d=False):
    lo = d - timedelta(days=7)
    latest = {}
    for r in themes:
        td = date.fromisoformat(r["theme_date"])
        if lo <= td and (td <= d if include_d else td < d):
            if r["name"] not in latest or td > latest[r["name"]][0]:
                latest[r["name"]] = (td, r["stage"], r["tickers"])
    out = set()
    for td, st, tk in latest.values():
        if st in ("Accelerating", "Mainstream"):
            out |= set(t for t in tk.split(",") if t)
    return out

TIERS = [(500e6, 15), (250e6, 12), (100e6, 10), (50e6, 7)]
def prescore(adv_dollar, in_theme):
    raw = {"liq": None if adv_dollar is None else next((p for t, p in TIERS if adv_dollar >= t), 0),
           "gap": 10, "th": 10 if in_theme else 0}
    W = {"liq": (15, 3), "gap": (10, 1), "th": (10, 1)}
    av = [k for k, v in raw.items() if v is not None]
    w = sum(raw[k]*W[k][1] for k in av); mx = sum(W[k][0]*W[k][1] for k in av)
    return round(w*65/mx, 2)

days = defaultdict(list)
theme_chk = [0, 0, 0, 0]
for r in pool:
    d = date.fromisoformat(r["scan_date"])
    P = prior_complete(d)
    s = scores.get((r["ticker"], P.isoformat()))
    adv20 = f(s["adv_20"]) if s else None
    pc = f(r["prev_close"])
    adv_dollar = adv20*pc if (adv20 and pc) else None
    ts = theme_set(d)
    if r["in_active_theme"] in ("t", "f"):
        th = r["in_active_theme"] == "t"
        theme_chk[0] += (th == (r["ticker"] in ts)); theme_chk[1] += 1
        theme_chk[2] += (th == (r["ticker"] in theme_set(d, True))); theme_chk[3] += 1
    else:
        th = r["ticker"] in ts
    row = dict(t=r["ticker"], d=r["scan_date"], tick=r["tick_et"], P=P, adv=adv_dollar,
               pm_rvol=f(r["pm_rvol"]), gap=f(r["gap_pct"]), theme=th,
               logged_pre=r["rank_by_prescore"], comp=prescore(adv_dollar, th),
               compA=prescore(None, th), label=lab.get((r["ticker"], r["scan_date"])),
               anylab=(r["ticker"], r["scan_date"]) in alllab)
    days[r["scan_date"]].append(row)

out = []
p = out.append
p(f"pool rows {len(pool)} days {len(days)}  ticks: { {k:sum(1 for d in days.values() if d[0]['tick']==k) for k in set(d[0]['tick'] for d in days.values())} }")
p(f"P<scan_date on all days: {all(r['P'] < date.fromisoformat(r['d']) for d in days.values() for r in d)}")
p(f"theme rebuild [d-7,d-1] agrees with logged {theme_chk[0]}/{theme_chk[1]};  [d-7,d] agrees {theme_chk[2]}/{theme_chk[3]}")
p(f"adv present {sum(r['adv'] is not None for d in days.values() for r in d)}; pm_rvol present {sum(r['pm_rvol'] is not None for d in days.values() for r in d)}")

def kv(r, key):
    return r[key]

def order(rows, key, tie_only=True, compkey="comp"):
    def k(r):
        v = r[key]
        miss = v is None
        prim = (-r[compkey],) if tie_only else ()
        return prim + (miss, -(v if v is not None else 0), r["t"])
    return sorted(rows, key=k)

def orderB(rows):  # exact shortlist_sort_key: missing adv -> 0.0
    return sorted(rows, key=lambda r: (-r["comp"], -(r["adv"] or 0.0), r["t"]))

def orderA(rows):
    return sorted(rows, key=lambda r: (-r["compA"], r["t"]))

# check A reproduces logged prescore rank
okA = tot = 0
for d, rows in days.items():
    for i, r in enumerate(orderA(rows), 1):
        if r["logged_pre"]:
            tot += 1; okA += (int(r["logged_pre"]) == i)
p(f"baseline A reproduces logged rank_by_prescore {okA}/{tot}")

p("\n== crowded days (pool > 20) ==")
crowd = sorted(d for d, rows in days.items() if len(rows) > 20)
p(" ".join(crowd))
for d in ["2026-09-17", "2026-10-05"]:
    rows = days.get(d, [])
    p(f"\n{d}: pool {len(rows)} at {rows[0]['tick'] if rows else '-'}")
    if len(rows) > 20:
        for nm, o in [("A", orderA(rows)), ("B", orderB(rows)), ("T:pm_rvol", order(rows, "pm_rvol")),
                      ("T:adv", order(rows, "adv")), ("T:gap", order(rows, "gap"))]:
            p(f"  {nm:10s} cut: {' '.join(r['t'] for r in o[20:])}")
        p("  B detail: " + "; ".join(f"{i}:{r['t']} c={r['comp']} adv={'-' if r['adv'] is None else round(r['adv']/1e6,1)} pmr={r['pm_rvol']}" for i, r in enumerate(orderB(rows), 1)))
# labelled names cut on any crowded day under B / A / T:pm_rvol
p("\nlabelled names on crowded days (rank under A, B, T:adv, T:pm_rvol, T:gap):")
for d in crowd:
    rows = days[d]
    for r in rows:
        if r["label"]:
            rk = lambda o: [x["t"] for x in o].index(r["t"]) + 1
            p(f"  {d} {r['t']} {r['label']} pool {len(rows)}: A={rk(orderA(rows))} B={rk(orderB(rows))} T:adv={rk(order(rows,'adv'))} T:pmr={rk(order(rows,'pm_rvol'))} T:gap={rk(order(rows,'gap'))}")

def auc(key, target="REAL_EP", present_only=False, sign=1, negs="unlab"):
    num = n = 0; pos = set(); per = []
    for d, rows in days.items():
        P = [r for r in rows if r["label"] == target]
        U = [r for r in rows if (not r["anylab"] if negs == "unlab" else not r["label"])]
        for a in P:
            pn = pc = 0
            for b in U:
                va, vb = a[key], b[key]
                if present_only and (va is None or vb is None):
                    continue
                if va is None and vb is None: s = .5
                elif va is None: s = 0
                elif vb is None: s = 1
                else: s = 1 if va > vb else (.5 if va == vb else 0)
                if sign < 0 and not (va is None or vb is None): s = 1 - s
                pn += s; pc += 1
            if pc:
                num += pn; n += pc; pos.add((a["t"], d)); per.append(pn/pc)
    return (round(num/n, 3) if n else None, len(pos), n, round(statistics.mean(per), 3) if per else None)

p("\n== within-day pairwise separation (positive vs unlabelled pool-mate; missing ranks last; ties .5) ==")
for key in ["adv", "pm_rvol", "gap"]:
    for negs in ["unlab", "nolean"]:
        a = auc(key, negs=negs); b = auc(key, present_only=True, negs=negs)
        g = auc(key, "GOOD_CHART", negs=negs); o = auc(key, "OKISH_CHART", negs=negs)
        bad = auc(key, "BAD_CHART", negs=negs)
        p(f"{key:8s} negs={negs:7s} REAL all: auc={a[0]} eps={a[1]} pairs={a[2]} per-EP={a[3]} | present-only: {b[0]} eps={b[1]} pairs={b[2]} | GOOD {g[:3]} OKISH {o[:3]} BAD(higher=ranked first) {bad[:3]}")
# GOOD+OKISH pooled lean
def auc_set(key, targets, negs="unlab"):
    num = n = 0
    for d, rows in days.items():
        P = [r for r in rows if r["label"] in targets]
        U = [r for r in rows if not r["anylab"]]
        for a in P:
            for b in U:
                va, vb = a[key], b[key]
                if va is None and vb is None: s = .5
                elif va is None: s = 0
                elif vb is None: s = 1
                else: s = 1 if va > vb else (.5 if va == vb else 0)
                num += s; n += 1
    return round(num/n, 3) if n else None, n
for key in ["adv", "pm_rvol", "gap"]:
    go = auc_set(key, {"GOOD_CHART", "OKISH_CHART"}); bd = auc_set(key, {"BAD_CHART"})
    p(f"{key:8s} GOOD/OKISH pooled {go}  BAD pooled share-ranked-above {bd} -> 'lower better' = {round(1-bd[0],3)}")
# baseline orderings as full rank AUC (positive above unlabelled)
def auc_order(fn):
    num = n = 0
    for d, rows in days.items():
        o = [x["t"] for x in fn(rows)]
        for a in rows:
            if a["label"] != "REAL_EP": continue
            for b in rows:
                if b["anylab"]: continue
                num += o.index(a["t"]) < o.index(b["t"]); n += 1
    return round(num/n, 3), n
p(f"\nfull-order separation: A {auc_order(orderA)}  B {auc_order(orderB)}  T:pm_rvol {auc_order(lambda r: order(r,'pm_rvol'))}  T:gap {auc_order(lambda r: order(r,'gap'))}")
p("\nper real EP (rank in day's pool under standalone adv / pm_rvol / gap; pool size):")
for d in sorted(days):
    rows = days[d]
    for r in rows:
        if r["label"] == "REAL_EP":
            rk = lambda o: [x["t"] for x in o].index(r["t"]) + 1
            p(f"  {d} {r['t']}: adv={rk(order(rows,'adv',False))} pmr={rk(order(rows,'pm_rvol',False))} gap={rk(order(rows,'gap',False))} B={rk(orderB(rows))} A={rk(orderA(rows))} / {len(rows)}  adv$={None if r['adv'] is None else round(r['adv']/1e6,1)}M pm_rvol={r['pm_rvol']} theme={r['theme']} comp={r['comp']}")
open(HERE / "verify_rederive" / "rederive.out", "w").write("\n".join(out) + "\n")
print("\n".join(out))

# --- slots decided by the tie-breaker on crowded days (tie group straddling rank 20/21 under B) ---
extra = []
tot = 0
for d in crowd:
    o = orderB(days[d]); c20, c21 = o[19]["comp"], o[20]["comp"]
    above = sum(1 for r in o if r["comp"] > c20)
    slots = (20 - above) if c20 == c21 else 0
    nomiss = sum(1 for r in days[d] if r["adv"] is None)
    tot += slots
    extra.append(f"  {d} pool {len(o)} rank20 comp {c20} rank21 comp {c21} above {above} slots {slots} no-ADV names {nomiss}")
extra.append(f"total slots decided by tie-breaker: {tot}")
r = days["2026-08-04"]
for t in ("BLZE", "INSP"):
    x = next(z for z in r if z["t"] == t)
    extra.append(f"  08-04 {t}: comp {x['comp']} adv {x['adv']} pm_rvol {x['pm_rvol']} gap {x['gap']}")
open(HERE / "verify_rederive" / "rederive.out", "a").write("\n".join(extra) + "\n")
print("\n".join(extra))

def auc_order_set(fn, targets):
    num = n = 0
    for d, rows in days.items():
        o = [x["t"] for x in fn(rows)]
        for a in rows:
            if a["label"] not in targets: continue
            for b in rows:
                if b["anylab"]: continue
                num += o.index(a["t"]) < o.index(b["t"]); n += 1
    return round(num/n, 3), n
ex = [f"full-order lean: B GOOD/OKISH {auc_order_set(orderB, {'GOOD_CHART','OKISH_CHART'})} B BAD(share above) {auc_order_set(orderB, {'BAD_CHART'})} A GOOD/OKISH {auc_order_set(orderA, {'GOOD_CHART','OKISH_CHART'})} A BAD {auc_order_set(orderA, {'BAD_CHART'})}"]
open(HERE / "verify_rederive" / "rederive.out", "a").write("\n".join(ex) + "\n"); print("\n".join(ex))
