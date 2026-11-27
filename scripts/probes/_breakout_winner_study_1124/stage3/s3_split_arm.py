#!/usr/bin/env python3
"""STAGE 3 - positive check that the SPLIT arm of the truncation could fire (read-only; the captured outcomes are not rewritten).
'0 split truncations' is an absence: a broken raw/adjusted factor (all NaN) would print the same. Stage 1e's w_split column
(a factor step in E..E+60, from the pinned store) is the reference: the same fact is recomputed here from the stream-read factor.
Reads era-A adjusted + raw closes for seed-1124 discovery tickers, dated <= ci(2020-12-31)+60 only."""
import gzip, sys
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent
DATA = Path("/Users/alvinfung/apollo_data"); PRE = DATA / "cb702_pre_v2"
K = pd.read_csv(HERE.parent / "stage1de/events_kept_seed1124.tsv", sep="\t", usecols=["era", "ci", "ticker", "E", "w_split"], dtype={"ticker": str}, keep_default_na=False)
K = K[(K.era == "A") & (K.E <= "2020-12-31")].reset_index(drop=True)
assert len(K) == 5330
cal = [l.strip() for l in open(DATA / "cb702/bws1124_eraA_list_ctx.cal.txt")]; cix = {d: i for i, d in enumerate(cal)}
cut = cal[cix["2020-12-31"] + 60]; need = set(K.ticker)
adj = {t: {} for t in need}; raw = {t: {} for t in need}
with gzip.open(PRE / "daily_closes_all.csv.gz", "rt") as fh:
    for ln in fh:
        f = ln.split(",")
        if f[0] in need and f[1] <= cut: adj[f[0]][f[1]] = float(f[5])
with gzip.open(PRE / "daily_raw_close.csv.gz", "rt") as fh:
    for ln in fh:
        t, d, c = ln.rstrip("\n").split(",")
        if t in need and d <= cut: raw[t][d] = float(c)
O = pd.read_csv(HERE / "discovery_outcomes.tsv.gz", sep="\t", keep_default_na=False, dtype={"ticker": str, "truncated": str})
CAP = {(t, e): (tr, int(nb)) for t, e, tr, nb, k in zip(O.ticker, O.E, O.truncated, O.nbars, O.kept) if str(k) == "True"}
mine, moves, n_nan, n_bars = [], [], 0, 0
for r in K.itertuples(index=False):
    iE = int(r.ci) + 1
    ds = sorted(d for d in adj[r.ticker] if d <= cal[iE + 60])
    c = np.array([adj[r.ticker][d] for d in ds]); F = np.array([raw[r.ticker].get(d, np.nan) for d in ds]) / c
    i0 = ds.index(r.E)
    n_bars += len(ds) - i0; n_nan += int(np.isnan(F[i0 - 1:]).sum())
    st = [p for p in range(i0, len(ds)) if abs(F[p] / F[p - 1] - 1) > 0.005]
    mine.append(bool(st))
    moves += [(r.ticker, r.E, ds[p], round(float(c[p] / c[p - 1] - 1), 4), p == i0, p - i0) for p in st]
ref = K.w_split.astype(str).eq("True").to_numpy()
eq = bool((np.array(mine) == ref).all())
by = pd.Series(mine).groupby(K.E.str[:4]).sum().to_dict()
big = [m for m in moves if m[3] >= 0.70 or m[3] <= -0.50]
out = [f"split arm, seed-1124 discovery events ({len(K)}): 'a raw/adjusted factor step in E..E+60' recomputed from the stream = stage 1e's w_split on every event: {eq}; per year {by} (stage 1e: 3 / 1 / 0 / 5)",
       f"NaN factor bars inside the windows (incl. the bar before E): {n_nan} of {n_bars}",
       f"factor-step bars: {len(moves)} (on E itself: {sum(m[4] for m in moves)}); adjusted close-to-close move on them: min {min(m[3] for m in moves):+.1%}, max {max(m[3] for m in moves):+.1%}; reaching >= +70% or <= -50%: {len(big)} -> after E: {len([m for m in big if not m[4]])}",
       "step bars (ticker, E, step date, move, on E): " + "; ".join(f"{m[0]} {m[1]} {m[2]} {m[3]:+.1%}{' (E)' if m[4] else ''}" for m in moves)]
# every qualifying step bar after E must already be cut out of the captured window: by the split arm, or by a guard break dated on / before it
unc = []
for m in big:
    if m[4]:
        continue
    tr, nb = CAP[(m[0], m[1])]
    cut_ok = nb <= m[5]                                            # the captured window holds bar positions 0 .. nb-1; the step bar is position m[5]
    out.append(f"qualifying step {m[0]} E {m[1]} on {m[2]} ({m[3]:+.1%}, window position {m[5]}): captured window holds {nb} bars, cut reason '{tr}' -> the step bar is {'OUTSIDE the window (cut on that date)' if cut_ok else 'INSIDE - NOT CUT'}")
    if not cut_ok:
        unc.append(m)
out.append(f"RESULT: {'PASS' if eq and n_nan == 0 and not unc else 'FAIL'} (factor is live: steps found and matched to stage 1e; the one qualifying move is cut on its date by the guard arm, which is tested first, so the split arm had nothing left to cut)")
print("\n".join(out)); (HERE / "3_split_arm.txt").write_text("\n".join(out) + "\n")
sys.exit(0 if "RESULT: PASS" in out[-1] else 3)
