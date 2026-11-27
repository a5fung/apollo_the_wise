"""R4 stage 3 extras for the carried features: ex-2020/2020-only counts, B4-strata ratio, monster / clean / ADR-tail, per-year; compared to stage 3's text lines."""
import re, json
import numpy as np, pandas as pd
import r4_common as C
import r4_stats as S
D = pd.read_parquet(C.OUTD / f"r4_disc_frame{C.SUF}.parquet")
O = pd.read_parquet(C.BIG / f"r4_outcomes_disc{C.SUF}.parquet")
D = D.merge(O[["era", "ticker", "D", "monster", "clean", "adr_tail", "fail"]], on=["era", "ticker", "D"], suffixes=("", "_o"))
D = D.sort_values(["era", "E", "ticker"]).reset_index(drop=True)
sc = pd.factorize(D.era + "|" + D.month)[0]
yr = np.array([int(x[:4]) for x in D.E]); y = D.win.to_numpy(float)
q = np.array([f"{x[:4]}Q{(int(x[5:7]) - 1) // 3 + 1}" for x in D.E])
txt = open("/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage3/3_discovery.txt").read()
def block(k): return re.search(rf"\n{k} - .*?(?=\n\n[fB]\d\d? - |\n\n=)", txt, re.S).group(0)
def tcounts(a, lab, mask=None):
    m = np.ones(len(a), bool) if mask is None else mask
    t, b = (a == 2) & m, (a == 0) & m
    return int(lab[t].sum()), int(t.sum()), int(lab[b].sum()), int(b.sum())
res = {}
for f, tk in (("f1", "f01"), ("f2", "f02"), ("f4", "f04"), ("f9", "f09")):
    v = D[f].to_numpy(float); a = S.thirds_assign(v, sc)
    wt, nt, wb, nb = tcounts(a, y)
    ex = tcounts(a, y, yr <= 2019); y20 = tcounts(a, y, yr == 2020)
    # B4 strata: (era, quarter, B4 third within era-quarter) holding >= 9 events (all discovery events), thirds of the feature within the stratum
    b4 = D.B4.to_numpy(float); scq = pd.factorize(D.era + "|" + q)[0]
    b4t = S.thirds_assign(b4, scq, min_n=1)
    sB = pd.factorize(pd.Series(scq).astype(str) + "|" + pd.Series(b4t).astype(str))[0]
    sizes = pd.Series(sB).map(pd.Series(sB).value_counts()).to_numpy()
    vv = np.where(sizes >= 9, v, np.nan)
    aB = S.thirds_assign(vv, sB, min_n=9)
    bs = tcounts(aB, y)
    mo = tcounts(a, D.monster.to_numpy(float)); cl = tcounts(a, D.clean.to_numpy(float)); ad = tcounts(a, D.adr_tail.to_numpy(float))
    py = {int(yy): tcounts(a, y, yr == yy) for yy in (2017, 2018, 2019, 2020)}
    ratio = lambda c: ((c[0] / c[1]) / (c[2] / c[3])) if c[1] and c[3] and c[2] else float("nan")
    res[f] = dict(all=(wt, nt, wb, nb), ex2020=ex, only2020=y20, b4=bs, b4_ratio=ratio(bs), monster=(mo[0], mo[2], ratio(mo)), clean=(cl[0], cl[2], ratio(cl)), adr=(ad[0], ad[2], ratio(ad)),
                  per_year={k: (round(ratio(c), 3), f"{c[0]}:{c[2]}") for k, c in py.items()})
    b = block(tk)
    print(f"--- {f} / {tk}")
    print("  mine :", {k: (v_ if not isinstance(v_, dict) else v_) for k, v_ in res[f].items() if k in ("ex2020", "only2020", "b4", "b4_ratio", "monster", "clean", "adr")})
    print("  mine per-year:", res[f]["per_year"])
    for line in b.splitlines():
        if any(s in line for s in ("without 2020", "within B4", "monster", "per year")): print("  stage3:", line.strip()[:300])
json.dump(res, open(C.OUTD / f"r4_carried_extras{C.SUF}.json", "w"), indent=1, default=str)
