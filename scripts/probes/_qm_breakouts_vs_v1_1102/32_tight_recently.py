#!/usr/bin/env python3
"""His labels on the 29 loose QM buys (31_tight3_labels.tsv): ok-or-better reach a 6.1-range spread (MSTR), several are 'buy
point a few days earlier' — QM bought after the breakout began, so the night before his buy already holds the breakout bars.
Variants, bars <= the night: c10 = spread of the last 10 closes (daily ranges); c10min5 = the tightest c10 on any of the last 6
nights (D-5..D); c10x2 = the 10 closes ending 2 sessions before D. Scored on all his labels; QM coverage + era-A names a night."""
import os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/23_move126_rule.py", run_name="lib")
F, Q, CUR, qrows, qbig = g["F"], g["Q"], g["CUR"], g["qrows"], g["qbig"]
from _chartlib import D as DD, runner  # noqa
OUT = "/Users/alvinfung/apollo_data/qm_breakouts_1102/tight_recent_eraA.parquet"
if not os.path.exists(OUT):
    parts = []
    for tk, grp in F[F.scan_date <= "2022-03-31"].groupby("ticker"):
        b, _ = runner.bars_for(DD, DD.tid[tk])
        h, l, c = (pd.Series(np.asarray(x, float)) for x in (b.h, b.l, b.c))
        adr = ((h - l) / c).rolling(20).mean()
        c10 = (c.rolling(10).max() / c.rolling(10).min() - 1) / adr
        pos = {d.isoformat(): i for i, d in enumerate(b.dates)}; ii = [pos[d] for d in grp.scan_date]
        parts.append(pd.DataFrame({"idx": grp.index, "c10": c10.values[ii], "c10min5": c10.rolling(6, min_periods=1).min().values[ii],
                                   "c10x2": ((c.shift(2).rolling(10).max() / c.shift(2).rolling(10).min() - 1) / adr).values[ii]}))
    pd.concat(parts).to_parquet(OUT, index=False)
Tt = pd.read_parquet(OUT).set_index("idx")
key = {(t, d): i for i, t, d in zip(F.index, F.ticker, F.scan_date)}
symtk = dict(zip(Q.sym, Q.ticker))
L1 = pd.read_csv(f"{HERE}/27_loose_wide_labels.tsv", sep="\t")[["who", "sym", "D", "label", "yes"]]
L2 = pd.read_csv(f"{HERE}/31_tight3_labels.tsv", sep="\t")
L2 = pd.DataFrame({"who": "QM buy", "sym": L2.sym, "D": L2.D, "label": L2.his,
                   "yes": L2.his.str.startswith(("ok", "good")) | L2.his.str.contains("earlier") & ~L2.his.str.startswith("no")})
L2.loc[L2.label.str.startswith("no") | L2.label.str.contains("EP"), "yes"] = False
L = pd.concat([L1[~L1.set_index(["sym", "D"]).index.isin(L2.set_index(["sym", "D"]).index)], L2])   # the newer label wins (SE 2020-09-14)
L["i"] = [key.get((symtk.get(s, s) if w == "QM buy" else s, d)) for s, d, w in zip(L.sym, L.D, L.who)]
L = L[L.i.notna()]; L["i"] = L.i.astype(int)
y, n = L[L.yes], L[~L.yes]
eraA = F.scan_date <= "2022-03-31"; nights = F.scan_date[eraA].unique()
size = lambda m: m[eraA].groupby(F.scan_date[eraA]).sum().reindex(nights, fill_value=0).median()
out = [f"labels: {len(y)} yes, {len(n)} no (SE 2020-09-14 was 'no' on the EMA21 sheet and 'ok' here — the newer label kept)"]
for col in Tt.columns:
    a, b = Tt[col].reindex(y.i).dropna().values, Tt[col].reindex(n.i).dropna().values
    auc = np.mean([[1.0 if u < v else (0.5 if u == v else 0.0) for v in b] for u in a])
    out.append(f"\n{col}: chance a yes is tighter than a no {auc:.2f}")
    v = Tt[col].reindex(F.index)
    for th in (3, 4, 5, 6):
        keep = v <= th
        out.append(f"  within {th}: yes kept {int((v[y.i] <= th).sum())}/{len(y)} | no removed {int((v[n.i] > th).sum())}/{len(n)} | "
                   f"QM buys kept {int(keep[qrows].sum())}/{len(qrows)} | big {int(keep[qbig].sum())}/{len(qbig)} | era-A names a night median {size(CUR & keep):.0f}")
    out.append("  loosest yes: " + ", ".join(f"{r.sym} {r.D} {v[r.i]:.1f}" for r in y.assign(t=v[y.i].values).sort_values('t', ascending=False).head(4).itertuples()))
print("\n".join(out)); open(f"{HERE}/32_tight_recently.txt", "w").write("\n".join(out) + "\n")
