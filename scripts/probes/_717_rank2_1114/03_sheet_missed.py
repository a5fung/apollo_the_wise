#!/usr/bin/env python3
"""#717 (2026-11-14; offline, ERA A ONLY): 12 Qullamaggie buys (fire rows in the gated pool) the PICK MODEL ranks top 5
but the LIVE order score ranks 20th or lower that night; one per ticker, drawn at random (seed 717). Same drawing as
02_sheet.py; title = ticker, buy day, live rank / pick-model rank / dollar-volume rank, names that night."""
import importlib.util, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PR = os.path.join(HERE, "..")
spec = importlib.util.spec_from_file_location("m", os.path.join(PR, "_717_pick_model_1113/02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M); P = M.P
sys.path.insert(0, os.path.join(PR, "_717_qm_confidence_1111")); import sheet as SH  # noqa
plt = SH.plt
pool = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_rank2_1114/pool3_ranked.parquet")
pool["n_night"] = pool.groupby("ci").ticker.transform("size")
q = pool[pool.is_qm.astype(bool) & (pool.rk_PM <= 5) & (pool.rk_L0 >= 20)]
chosen, seen = [], set()
for i in np.random.default_rng(717).permutation(len(q)):
    r = q.iloc[int(i)]
    if r.ticker not in seen: seen.add(r.ticker); chosen.append(r)
    if len(chosen) == 12: break
chosen.sort(key=lambda r: r.E)
S, _ = P.setup(); D = S.D
tid = {}
for k, t in enumerate(D.tickers): tid.setdefault(t, []).append(k)
fig = plt.figure(figsize=(26, 18)); gs = fig.add_gridspec(6, 4, height_ratios=[3, 1] * 3, hspace=0.5, wspace=0.12)
for n, r in enumerate(chosen):
    ci = r.ci; bars = Di = None
    for k in tid[r.ticker]:
        bb, cidx = P.runner.bars_for(D, k); hit = np.flatnonzero(np.asarray(cidx) == ci)
        if len(hit) and abs(float(bb.c[hit[0]]) - r.close) < 1e-6 * max(1.0, r.close): bars, Di = bb, int(hit[0]); break
    assert bars is not None, r.ticker
    o, h, l, cf, v = (np.asarray(x[:Di + 1], float) for x in (bars.o, bars.h, bars.l, bars.c, bars.v))
    off = max(0, len(cf) - 189); o, h, l, c, v = o[off:], h[off:], l[off:], cf[off:], v[off:]
    rr, cc = divmod(n, 4); ax = fig.add_subplot(gs[2 * rr, cc]); axv = fig.add_subplot(gs[2 * rr + 1, cc], sharex=ax)
    for k in range(len(c)):
        cl = "#26a69a" if c[k] >= o[k] else "#ef5350"
        ax.vlines(k, l[k], h[k], color=cl, lw=0.7)
        ax.add_patch(plt.Rectangle((k - 0.3, min(o[k], c[k])), 0.6, max(abs(c[k] - o[k]), 1e-9), color=cl)); axv.bar(k, v[k], color=cl, width=0.7)
    for arr, cl in ((SH.ema(cf, 10), "#1f77b4"), (SH.ema(cf, 21), "#d62728"), (SH.sma(cf, 50), "#2ca02c")): ax.plot(range(len(c)), arr[off:], color=cl, lw=0.9)
    ax.hlines(r.level, max(0, len(c) - 46), len(c) + 1, colors="black", linestyles="dashed", lw=1.0)
    ax.set_yscale("log"); ax.yaxis.set_major_formatter(SH.ScalarFormatter()); ax.yaxis.set_minor_formatter(SH.NullFormatter())
    ax.set_title(f"{r.ticker} bought {r.E}\nlive #{int(r.rk_L0)} | pick model #{int(r.rk_PM)} | dollar vol #{int(r.rk_R0)}  (of {int(r.n_night)})", fontsize=11, loc="left")
    ax.tick_params(labelsize=6); ax.set_xticks([]); axv.set_xticks([])
fig.suptitle("Qullamaggie buys the pick model puts in the top 5 and the live ranking puts 20th or lower. Chart ends the night before his buy; dashed = buy level", fontsize=13)
out = os.path.join(HERE, "sheet_missed_by_live.png"); fig.savefig(out, dpi=80, bbox_inches="tight"); print(out, len(q))
