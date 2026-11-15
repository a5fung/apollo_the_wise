#!/usr/bin/env python3
"""#717 grades sample sheet: 6 random A+ vs 6 random C breakouts from the TEST years (2026-11-15; offline, $0, ERA A ONLY).
RULE (stated before drawing): test rows (2021-01-01 <= E <= 2022-03-31) of the three-check pool, graded by
cutoffs.json; rows sorted by (ci, ticker); rng = numpy default_rng(1115); A+ rows permuted and walked, taking the first
6 with distinct tickers; then (same rng) the C rows the same way, tickers also distinct from the A+ six. No look at
is_qm or any outcome when sampling. Row 1 = A+, row 2 = C. Each chart: 189 daily bars ending on the list night, EMA10
blue / EMA21 red / SMA50 green, log scale, buy level dashed (drawing as _717_rank2_1114/02_sheet.py). Title = ticker +
grade only; dates and whether Qullamaggie bought go to the separate key file (do-not-show).
"""
import importlib.util, json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PR = os.path.join(HERE, "..")
spec = importlib.util.spec_from_file_location("g", os.path.join(HERE, "01_grades.py")); G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
spec = importlib.util.spec_from_file_location("m", os.path.join(PR, "_717_pick_model_1113/02_fit_test.py")); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
P = M.P
sys.path.insert(0, os.path.join(PR, "_717_qm_confidence_1111")); import sheet as SH  # noqa
plt = SH.plt
cuts = list(json.load(open(os.path.join(HERE, "cutoffs.json")))["cutoffs_log_odds"].items())
pool = G.load_pool(); pool["grade"] = G.grade_of(pool.PM, cuts)
test = pool[pool.E >= G.TEST_FIRST].sort_values(["ci", "ticker"]).reset_index(drop=True)
cal = [s for s in open(M.CAPTURE + ".cal.txt").read().split()]; assert cal[-1] < "2025-01-01"
rng = np.random.default_rng(G.SEED); picks, used = [], set()
for g in ("A+", "C"):
    x = test[test.grade == g]; n = 0
    for i in rng.permutation(len(x)):
        r = x.iloc[int(i)]
        if r.ticker in used: continue
        used.add(r.ticker); picks.append(r); n += 1
        if n == 6: break
    assert n == 6, (g, n)
S, _ = P.setup(); D = S.D
tid = {}
for k, t in enumerate(D.tickers): tid.setdefault(t, []).append(k)
fig = plt.figure(figsize=(31, 11)); gs = fig.add_gridspec(4, 6, height_ratios=[3, 1] * 2, hspace=0.5, wspace=0.12)
key = []
for n, r in enumerate(picks):
    ri, j = divmod(n, 6); ci = int(r.ci); bars = Di = None
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
    ax.set_title(f"{r.ticker} — {r.grade}", fontsize=14, loc="left"); ax.tick_params(labelsize=6); ax.set_xticks([]); axv.set_xticks([])
    key.append(f"{r.grade} | {r.ticker} | list night {cal[ci]} | breakout day {r.E} | score {r.PM:.3f} | pick-model rank that night {int(r.rk_PM)} | Qullamaggie bought: {'YES' if r.is_qm else 'no'}")
fig.suptitle("Breakout grades sample — top row: 6 random A+, bottom row: 6 random C (2021-01..2022-03). EMA10 blue / EMA21 red / SMA50 green, log; dashed = buy level", fontsize=14)
out = os.path.join(HERE, "sheet_grades.png"); fig.savefig(out, dpi=80, bbox_inches="tight"); plt.close(fig); print(out)
open(out + ".key_do_not_show.txt", "w").write("\n".join(key) + "\n")
