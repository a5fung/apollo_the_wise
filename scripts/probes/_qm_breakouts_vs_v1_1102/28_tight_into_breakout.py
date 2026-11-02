#!/usr/bin/env python3
"""His 11-02 ruling: 'the chart should tighten leading to the breakout, not the full base'. Tightness over the last N sessions
before the buy (N = 5, 7, 10, 15): the spread of the closes (max/min - 1) and of the full bars (highest high / lowest low - 1),
each in daily ranges (ADR20 at D). Scored on his 72 labels; then on QM's buys and the list (era A, current rules). No returns."""
import json, os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/23_move126_rule.py", run_name="lib")
F, Q, CUR, qrows, qbig = g["F"], g["Q"], g["CUR"], g["qrows"], g["qbig"]
from _chartlib import D as DD, runner  # noqa
OUT = "/Users/alvinfung/apollo_data/qm_breakouts_1102/tight_eraA.parquet"
A = F[CUR]
NS = (5, 7, 10, 15)
if not os.path.exists(OUT):
    parts = []
    for tk, grp in F[F.scan_date <= "2022-03-31"].groupby("ticker"):
        b, _ = runner.bars_for(DD, DD.tid[tk])
        h, l, c = (pd.Series(np.asarray(x, float)) for x in (b.h, b.l, b.c))
        adr = ((h - l) / c).rolling(20).mean()
        cols = {}
        for n in NS:
            cols[f"close{n}"] = (c.rolling(n).max() / c.rolling(n).min() - 1) / adr
            cols[f"bar{n}"] = (h.rolling(n).max() / l.rolling(n).min() - 1) / adr
        pos = {d.isoformat(): i for i, d in enumerate(b.dates)}
        ii = [pos[d] for d in grp.scan_date]
        parts.append(pd.DataFrame({"idx": grp.index, **{k: v.values[ii] for k, v in cols.items()}}))
    pd.concat(parts).to_parquet(OUT, index=False)
Tt = pd.read_parquet(OUT).set_index("idx")
L = pd.read_csv(f"{HERE}/27_loose_wide_labels.tsv", sep="\t")
key = {(t, d): i for i, t, d in zip(F.index, F.ticker, F.scan_date)}
symtk = dict(zip(Q.sym, Q.ticker))
L["i"] = [key.get((symtk.get(s, s) if w == "QM buy" else s, d)) for s, d, w in zip(L.sym, L.D, L.who)]
L = L[L.i.notna()]; L["i"] = L.i.astype(int)
y, n = L[L.yes], L[~L.yes]
out = [f"labels joined: {len(y)} yes, {len(n)} no"]
best = []
for col in Tt.columns:
    a, b = Tt[col].reindex(y.i).dropna().values, Tt[col].reindex(n.i).dropna().values
    auc = np.mean([[1.0 if u < v else (0.5 if u == v else 0.0) for v in b] for u in a])
    best.append((auc, col))
for auc, col in sorted(best, reverse=True):
    out.append(f"  {col:8s} chance a yes is tighter than a no: {auc:.2f}")
col = sorted(best, reverse=True)[0][1]
out.append(f"\nbest: {col} (spread of the last {col[-2:].strip('rl')} {'closes' if col.startswith('close') else 'bars'}, in daily ranges)")
v = Tt[col]
for th in (2, 2.5, 3, 3.5, 4, 5):
    keep = v <= th
    nn = (CUR & keep.reindex(F.index, fill_value=False)).groupby(F.scan_date).sum()
    out.append(f"  within {th}: his yes kept {int((v.reindex(y.i) <= th).sum())}/{len(y)} | his no removed {int((v.reindex(n.i) > th).sum())}/{len(n)} | "
               f"QM buys kept {int(keep.reindex(qrows, fill_value=False).sum())}/{len(qrows)} | big {int(keep.reindex(qbig, fill_value=False).sum())}/{len(qbig)} | names a night median {nn[nn.index <= '2022-03-31'].median():.0f}")
out.append("loosest yes on it: " + ", ".join(f"{r.sym} {r.D} {v[r.i]:.1f}" for r in y.assign(t=v.reindex(y.i).values).sort_values('t', ascending=False).head(5).itertuples()))
print("\n".join(out)); open(f"{HERE}/28_tight_into_breakout.txt", "w").write("\n".join(out) + "\n")
