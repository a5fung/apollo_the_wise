#!/usr/bin/env python3
"""#717 shape checks: STUDY part 2 (still exploration, before PREREG): the candidate measures on all three populations
(cached), Qullamaggie's 56 vs the era-A fires, and the 36 grades. Nothing is scored here.
    python3 scripts/probes/_717_shape_1114/02b_study.py > scripts/probes/_717_shape_1114/02b_study.out"""
import os, numpy as np, pandas as pd
import lib
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 200)
f, sc, hi, hi_all, gr, nights, cal, WF, WX = lib.load()
CF = "/Users/alvinfung/apollo_data/bv1_shape_1114/fires_shape_measures.parquet"
if not os.path.exists(CF):
    mf = lib.measures(WF, f.adr20.to_numpy(), f.level.to_numpy()); mf.index = f.index; mf.to_parquet(CF)
mf = pd.read_parquet(CF)
mh = lib.measures(WX[hi.w.to_numpy()], hi.adr20.to_numpy(), hi.level.to_numpy()); mh.index = hi.index
mg = mf.loc[[f.index[w] for w in gr.w]].reset_index(drop=True)
cols = list(mf.columns)
q = [.05, .1, .25, .5, .75, .9, .95]
print("== the 56 listed High-tier buys =="); print(pd.concat([mh.describe(percentiles=q).T, hi[["base_len"]].describe(percentiles=q).T]).round(2).to_string())
print("\n== era-A fires (all) =="); print(pd.concat([mf.describe(percentiles=q).T, f[["base_len"]].describe(percentiles=q).T]).round(2).to_string())
print("\n== share of era-A fires beyond the 56's 90th / 10th percentile and beyond the 56's extreme ==")
for c in cols:
    for side in ("hi", "lo"):
        p = np.nanpercentile(mh[c], 90 if side == "hi" else 10); e = mh[c].max() if side == "hi" else mh[c].min()
        sh = (mf[c] > p).mean() if side == "hi" else (mf[c] < p).mean(); se = (mf[c] > e).mean() if side == "hi" else (mf[c] < e).mean()
        print(f"  {c:8s} {side}: p = {p:6.2f} fires beyond {sh:5.1%} (the 56: {((mh[c] > p) if side == 'hi' else (mh[c] < p)).mean():4.0%}) | extreme {e:6.2f} fires beyond {se:5.1%}")
G = pd.concat([gr[["card", "ticker", "Dd", "grade", "base_len", "u50", "s50_chg10", "off_high_adr", "hh_age", "runup6m_adr"]], mg], axis=1)
G["after1d"] = ~((G.u50 < -0.03) & (G.s50_chg10 < 0))
print("\n== the 36 grades =="); print(G.sort_values(["grade", "after1d", "ticker"]).round(2).to_string(index=False))
print("\n== the 56 =="); print(pd.concat([hi[["ticker", "E", "big", "base_len", "u50", "s50_chg10"]], mh], axis=1).round(2).to_string(index=False))
