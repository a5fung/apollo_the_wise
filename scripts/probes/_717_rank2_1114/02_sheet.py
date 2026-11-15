#!/usr/bin/env python3
"""#717 ranking comparison sheets (2026-11-14; offline, $0, ERA A ONLY, nothing changed).
3 test-era list nights drawn at random (seed 717) from nights with >= 20 names in the gated pool. One sheet per night:
row 1 = live order score top 5, row 2 = pick model top 5, row 3 = dollar volume top 5. Each chart: 189 daily bars ending on
the list night, EMA10 blue / EMA21 red / SMA50 green, log scale, buy level dashed. Qullamaggie's buys NOT marked on the
image (key file = do-not-show). Drawing as 04_sheet_model_picks.py.
"""
import importlib.util, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PR = os.path.join(HERE, "..")
spec = importlib.util.spec_from_file_location("m", os.path.join(PR, "_717_pick_model_1113/02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
P = M.P
sys.path.insert(0, os.path.join(PR, "_717_qm_confidence_1111")); import sheet as SH  # noqa
plt = SH.plt
pool = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_rank2_1114/pool3_ranked.parquet")
_, cal, _ = M.load()
pool = pool[pool.E >= M.TEST_FIRST]
n = pool.groupby("ci").size(); nights = np.sort(n[n >= 20].index.values)
pick = np.random.default_rng(717).choice(nights, 3, replace=False)
S, _ = P.setup(); D = S.D
tid = {}
for k, t in enumerate(D.tickers): tid.setdefault(t, []).append(k)
ROWS = [("rk_L0", "LIVE ranking"), ("rk_PM", "PICK MODEL"), ("rk_R0", "DOLLAR VOLUME")]
key = []
for si, ci in enumerate(sorted(pick)):
    day = pool[pool.ci == ci]
    fig = plt.figure(figsize=(26, 16)); gs = fig.add_gridspec(6, 5, height_ratios=[3, 1] * 3, hspace=0.5, wspace=0.12)
    for ri, (col, name) in enumerate(ROWS):
        top = day.sort_values(col).head(5)
        for j, r in enumerate(top.itertuples()):
            bars = Di = None
            for k in tid[r.ticker]:
                bb, cidx = P.runner.bars_for(D, k); hit = np.flatnonzero(np.asarray(cidx) == ci)
                if len(hit) and abs(float(bb.c[hit[0]]) - r.close) < 1e-6 * max(1.0, r.close): bars, Di = bb, int(hit[0]); break
            assert bars is not None, r.ticker
            o, h, l, cf, v = (np.asarray(x[:Di + 1], float) for x in (bars.o, bars.h, bars.l, bars.c, bars.v))
            off = max(0, len(cf) - 189); o, h, l, c, v = o[off:], h[off:], l[off:], cf[off:], v[off:]
            ax = fig.add_subplot(gs[2 * ri, j]); axv = fig.add_subplot(gs[2 * ri + 1, j], sharex=ax)
            for k in range(len(c)):
                cl = "#26a69a" if c[k] >= o[k] else "#ef5350"
                ax.vlines(k, l[k], h[k], color=cl, lw=0.7)
                ax.add_patch(plt.Rectangle((k - 0.3, min(o[k], c[k])), 0.6, max(abs(c[k] - o[k]), 1e-9), color=cl)); axv.bar(k, v[k], color=cl, width=0.7)
            for arr, cl in ((SH.ema(cf, 10), "#1f77b4"), (SH.ema(cf, 21), "#d62728"), (SH.sma(cf, 50), "#2ca02c")): ax.plot(range(len(c)), arr[off:], color=cl, lw=0.9)
            ax.hlines(r.level, max(0, len(c) - 46), len(c) + 1, colors="black", linestyles="dashed", lw=1.0)
            ax.set_yscale("log"); ax.yaxis.set_major_formatter(SH.ScalarFormatter()); ax.yaxis.set_minor_formatter(SH.NullFormatter())
            ax.set_title(f"{name} #{j+1}: {r.ticker}", fontsize=12, loc="left"); ax.tick_params(labelsize=6); ax.set_xticks([]); axv.set_xticks([])
            key.append(f"sheet{si+1} {cal[ci]} | {name} #{j+1} {r.ticker} | Qullamaggie bought: {'YES' if r.is_qm else 'no'}")
    fig.suptitle(f"Sheet {si+1} — list night {cal[ci]} ({len(day)} names). Rows: live ranking / pick model / dollar volume, top 5 each. Dashed = buy level", fontsize=13)
    out = os.path.join(HERE, f"sheet_rank_{si+1}.png"); fig.savefig(out, dpi=80, bbox_inches="tight"); plt.close(fig); print(out)
open(os.path.join(HERE, "sheet_rank.key_do_not_show.txt"), "w").write("\n".join(key) + "\n")
