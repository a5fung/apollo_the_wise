#!/usr/bin/env python3
"""His 11-02 read: 'One key reason for no I see was wide and loose bases or run ups'. On every label he has given (era A, bars
<= D): the run-up = the low -> high stretch that makes the 6-month move; the base = after that high up to D. Width and looseness
measures for both; for each, the line that keeps ALL his ok-or-better and how many of his no's it removes. No returns."""
import os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/26_runup_in_ranges.py", run_name="lib")
F, Q, T0 = g["F"], g["Q"], g["T"]
from _chartlib import D as DD, runner  # noqa

def measures(tk, d):
    b, _ = runner.bars_for(DD, DD.tid[tk]); dates = [x.isoformat() for x in b.dates]; i = dates.index(d)
    h, l, c = (np.asarray(x, float) for x in (b.h, b.l, b.c))
    best, jl, jh = -1, None, None
    for j in range(max(1, i - 125), i + 1):                 # the 6-month move's low -> high (same definition as move126)
        k = max(0, j - 63) + int(np.argmin(l[max(0, j - 63):j + 1]))
        m = h[j] / l[k] - 1
        if m > best: best, jl, jh = m, k, j
    rng = (h - l) / c
    adr = rng[i - 19:i + 1].mean()
    ru = slice(jl, jh + 1); bs = slice(jh + 1, i + 1)
    lc = np.log(c[ru]); x = np.arange(len(lc))
    r2 = np.corrcoef(x, lc)[0, 1] ** 2 if len(lc) > 2 else np.nan
    runmax = np.maximum.accumulate(c[ru]); dd = (1 - c[ru] / runmax).max()
    ret_ru = np.diff(np.log(c[ru])); ret_bs = np.diff(np.log(c[jh:i + 1]))
    out = {"runup sessions": jh - jl, "runup smoothness (R2)": r2, "runup deepest pullback %": dd,
           "runup deepest pullback (ranges)": dd / adr, "runup avg daily range %": rng[ru].mean(),
           "runup day-to-day swing %": ret_ru.std() if len(ret_ru) > 1 else np.nan,
           "runup swing / trend": (ret_ru.std() / ret_ru.mean()) if len(ret_ru) > 1 and ret_ru.mean() > 0 else np.nan,
           "base sessions": i - jh}
    if i - jh >= 3:
        out.update({"base depth %": 1 - l[bs].min() / h[jh], "base depth (ranges)": (1 - l[bs].min() / h[jh]) / adr,
                    "base avg daily range %": rng[bs].mean(), "base range vs runup range": rng[bs].mean() / rng[ru].mean(),
                    "base day-to-day swing %": ret_bs.std(), "base close spread %": c[bs].max() / c[bs].min() - 1,
                    "last 10 closes spread %": c[i - 9:i + 1].max() / c[i - 9:i + 1].min() - 1,
                    "last 10 closes spread (ranges)": (c[i - 9:i + 1].max() / c[i - 9:i + 1].min() - 1) / adr,
                    "last 10 avg range vs base": rng[i - 9:i + 1].mean() / rng[bs].mean()})
    return out

rows = []
for r in T0.itertuples():
    d = Q.D[Q.row == r.i].iloc[0] if r.who == "QM buy" else r.date
    rows.append({"who": r.who, "sym": r.sym, "D": d, "label": r.label, "yes": r.yes, **measures(F.ticker[r.i], d)})
T = pd.DataFrame(rows)
T.to_csv(f"{HERE}/27_loose_wide_labels.tsv", sep="\t", index=False)
yes, no = T[T.yes], T[~T.yes]
res = []
for m in [c for c in T.columns if c not in ("who", "sym", "D", "label", "yes")]:
    for dirn in ("<=", ">="):                                 # '<=' = wide/loose is cut (the line sits at the loosest yes)
        y = yes[m].dropna()
        if not len(y): continue
        th = y.max() if dirn == "<=" else y.min()
        nv = no[m]
        removed = int(((nv > th) if dirn == "<=" else (nv < th)).sum())
        res.append((m, dirn, th, removed, int(nv.notna().sum()), int(y.size), round(float(y.median()), 3), round(float(nv.median()), 3)))
R = pd.DataFrame(res, columns=["measure", "keep if", "line (keeps every yes)", "no's removed", "no's measured", "yes measured", "yes median", "no median"])
R = R.sort_values("no's removed", ascending=False)
out = f"labels: {len(yes)} ok-or-better, {len(no)} no\n" + R.head(16).to_string(index=False, float_format=lambda x: f"{x:.3g}")
print(out); open(f"{HERE}/27_loose_wide.txt", "w").write(out + "\n")
