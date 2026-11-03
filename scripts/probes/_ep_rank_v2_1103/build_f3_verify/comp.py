#!/usr/bin/env python3
"""BLIND VERIFIER part 2 — the v2 composite bars (i)-(iii), recomputed from the pre-registration's
R7/R8/R9 text, the shadow's _pct_rank rule, and the encoder's preopen n_cleared (feature 1, reused as the
pre-registration requires). My own F3 (v_f3.py's f3) supplies 'held'. Offline, $0."""
from __future__ import annotations

import csv
import importlib.util
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = (HERE / "v_f3.py").read_text()
exec(src.split("# ---------------------------------------------------------------- population checks")[0])
OUT.clear()

spec = importlib.util.spec_from_file_location("nbis", REPO / "scripts/probes/_533_nbis_structure_encoder.py")
nbis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nbis)
sys.path.insert(0, str(REPO))
from scripts.alert_rank_shadow_running_read import CohortRead, score_both_directions  # noqa: E402

alerts = defaultdict(set)
for r in csv.DictReader(open(DATA / "ep_alerts.csv")):
    alerts[r["alert_date"]].add(r["ticker"])
shd = {}
for r in csv.DictReader(open(DATA / "shadow_rows.csv")):
    shd.setdefault((r["ticker"], r["alert_date"]), r)

_z = {}


def zones(t, d):
    if (t, d) not in _z:
        sl, ia = slice_to(t, d)
        if sl is None:
            _z[(t, d)] = None
        else:
            e = nbis.encode(t, d, {t: sl}, {}, preopen=True)
            _z[(t, d)] = None if e.get("error") else e["n_cleared"]
    return _z[(t, d)]


def pct_rank(vals, v):
    lo = sum(1 for x in vals if x < v)
    eq = sum(1 for x in vals if x == v)
    return (lo + eq / 2) / len(vals)


def composite(t, d, feats, f3prm):
    """feats: list of feature names, each 'higher=yes'. Returns (composite, featured pool size) or (None, n)."""
    pool = set(alerts.get(d, set())) | {t}
    pool = {x for x in pool if x in bars}

    def fv(x):
        out = []
        for f in feats:
            if f == "zones":
                v = zones(x, d)
            else:
                v = f3(x, d, f3prm)["held"]
            if v is None:
                return None
            out.append(v)
        return out

    vals = {x: fv(x) for x in pool}
    feat = {x: v for x, v in vals.items() if v is not None}
    if t not in feat:
        return None, len(feat)
    if len(feat) < 2:
        return 0.5, len(feat)
    rs = []
    for j in range(len(feats)):
        col = [v[j] for v in feat.values()]
        rs.append(1 - pct_rank(col, feat[t][j]))
    return sum(rs) / len(rs), len(feat)


pa = {(p["ticker"], p["date"]): p["label"] for p in pairs if p["source"] == "A"}
yesA = [k for k, v in pa.items() if v in YES]
noA = [k for k, v in pa.items() if v in NO]
Bop = [(p["ticker"], p["date"]) for p in pairs if p["source"] == "B" and p["label"] == "operator"]
Cks = [(p["ticker"], p["date"]) for p in pairs if p["source"] == "C"]

# C outcomes from bars (verified equal to rows.psv in v_f3.txt)
crow = {}
for (t, d) in Cks:
    rows = bars[t]
    i0 = [i for i, x in enumerate(rows) if x[0] == d][0]
    fw = rows[i0:]
    o0, l0 = fw[0][1], fw[0][3]
    adrf = float(shd[(t, d)]["adr20_frac"])
    crow[(t, d)] = dict(sess=len(fw), x5=(max(x[2] for x in fw[:6]) - o0) / o0 / adrf,
                        x20=(max(x[2] for x in fw[:21]) - o0) / o0 / adrf,
                        loser=min(x[3] for x in fw[1:6]) < l0,
                        c_eod=float(shd[(t, d)]["composite_rank_eod"]),
                        c_945=float(shd[(t, d)]["composite_rank_asof0945"]))


def bars_for(feats, f3prm, tag):
    P(f"\n=== composite [{tag}] features {feats} · F3 params {f3prm}")
    cy = [composite(t, d, feats, f3prm) for (t, d) in yesA]
    cn = [composite(t, d, feats, f3prm) for (t, d) in noA]
    ly = [c for c, n in cy if c is not None]
    ln = [c for c, n in cn if c is not None]
    a_lit = auc([-x for x in ly], [-x for x in ln])
    ry = [c for c, n in cy if c is not None and n >= 2]
    rn = [c for c, n in cn if c is not None and n >= 2]
    a_rk = auc([-x for x in ry], [-x for x in rn])
    P(f"  (i) literal {a_lit:.3f} (n {len(ly)}/{len(ln)}) · rankable-only {a_rk:.3f} (n {len(ry)}/{len(rn)}) -> {'PASS' if a_lit >= 0.70 else 'FAIL'}")
    cb = [composite(t, d, feats, f3prm) for (t, d) in Bop]
    rk = [(c, n) for c, n in cb if c is not None and n >= 2]
    top = sum(1 for c, n in rk if c < 0.5)
    P(f"  (ii) rankable {len(rk)} of {len(Bop)} · top half {top} -> {'PASS' if rk and top / len(rk) >= 0.8 else 'FAIL'}")
    v2 = {k: composite(k[0], k[1], feats, f3prm)[0] for k in Cks}
    nnull = sum(1 for v in v2.values() if v is None)
    res3 = []
    for h, mm, xk in (("5d", 6, "x5"), ("20d", 21, "x20")):
        mat = [k for k in Cks if crow[k]["sess"] >= mm]
        top_v2 = [k for k in mat if v2[k] is not None and v2[k] <= 0.25 + 1e-9]
        for ob in ("c_eod", "c_945"):
            top_o = [k for k in mat if crow[k][ob] <= 0.25 + 1e-9]
            w1 = sum(1 for k in top_v2 if crow[k][xk] >= 8); l1 = sum(1 for k in top_v2 if crow[k]["loser"])
            w0 = sum(1 for k in top_o if crow[k][xk] >= 8); l0 = sum(1 for k in top_o if crow[k]["loser"])
            v = score_both_directions(CohortRead(len(top_v2), w1, l1), CohortRead(len(top_o), w0, l0))
            ok = (w1 > w0) and (l1 / len(top_v2) <= l0 / len(top_o)) if top_v2 and top_o else False
            res3.append(ok)
            P(f"  (iii) {h} vs {ob}: matured {len(mat)} | v2 top n={len(top_v2)} w {w1} L {l1} | old top n={len(top_o)} w {w0} L {l0} "
              f"-> {v.split(' --')[0]} · bar {'PASS' if ok else 'FAIL'}")
    P(f"  v2 NULL composite on {nnull} of {len(Cks)} C rows")
    verdict = "PASS" if (a_lit >= 0.70 and rk and top / len(rk) >= 0.8 and all(res3)) else "FAIL"
    P(f"  -> verdict {verdict}")


LIT = {}                                          # my literal reading: run P-59..P, shelf S-44..S
BLD = {"run_incl": False, "shelf_incl": False}    # the builder's convention found by the diff
bars_for(["zones"], LIT, "stated: zones cleared alone (held < 0.65 does not enter)")
bars_for(["zones", "held"], LIT, "FORCED zones+held, literal windows")
bars_for(["zones", "held"], BLD, "FORCED zones+held, builder windows")
bars_for(["zones", "held"], {**LIT, "shelf_win": 22}, "plateau shelf_win=22, literal windows (held 0.701 qualifies)")
bars_for(["zones", "held"], {**BLD, "shelf_win": 22, "couple": True}, "plateau shelf_win=22, builder windows (held 0.670 qualifies)")

(HERE / "comp.txt").write_text("\n".join(OUT) + "\n")
