#!/usr/bin/env python3
"""#717 side-by-side (2026-11-14, his ask): a chart he rejected next to a Qullamaggie big-winner buy that the
matching check would also have thrown out. Era A only; drawing as _717_reasons_1114/03_sheet.py."""
import importlib.util, os, sys
from datetime import date
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PM = os.path.join(REPO, "scripts/probes/_717_pick_model_1113")
spec = importlib.util.spec_from_file_location("m", os.path.join(PM, "02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M); P = M.P
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_qm_confidence_1111")); import sheet as SH  # noqa
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_shape_1114")); import lib as LB  # noqa
plt = SH.plt
CAP = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
df = pd.read_parquet(CAP); cal = [date.fromisoformat(s) for s in open(CAP + ".cal.txt").read().split()]
ix = {d.isoformat(): i for i, d in enumerate(cal)}
PAIRS = [
    (("TWTR", "2018-02-08", "YOU: no — \"no tightness, just chop\""),
     ("JMIA", "2020-11-18", "QULLAMAGGIE BUY — big winner")),
    (("THC", "2017-05-10", "YOU: no — \"downtrend, recent up move made lower high\""),
     ("APT", "2020-06-17", "QULLAMAGGIE BUY — big winner")),
    (("REN", "2017-07-28", "YOU: no — \"just downtrend, where's breakout?\""),
     ("BE", "2020-08-13", "QULLAMAGGIE BUY — big winner")),
]
S, _ = P.setup(); D = S.D
tid = {}
for k, t in enumerate(D.tickers):
    tid.setdefault(t, []).append(k)
fig = plt.figure(figsize=(18, 20))
gs = fig.add_gridspec(6, 2, height_ratios=[3, 1] * 3, hspace=0.42, wspace=0.08)
out = []
for row, pair in enumerate(PAIRS):
    for col, (t, E, label) in enumerate(pair):
        ci = ix[E] - 1
        r = df[(df.ticker == t) & (df.ci == ci)].iloc[0]
        bars = None
        for k in tid[t]:
            bb, cidx = P.runner.bars_for(D, k)
            hit = np.flatnonzero(np.asarray(cidx) == ci)
            if len(hit) and abs(float(bb.c[hit[0]]) - r.close) < 1e-6 * max(1.0, r.close):
                bars, Di = bb, int(hit[0]); break
        assert bars is not None, t
        o, h, l, cf, v = (np.asarray(x[:Di + 1], float) for x in (bars.o, bars.h, bars.l, bars.c, bars.v))
        W = np.stack([o[-80:], h[-80:], l[-80:], cf[-80:]])[None]
        m = LB.measures(W, [r.adr20], [r.level]).iloc[0]
        off = max(0, len(cf) - 189)
        o2, h2, l2, c2, v2 = o[off:], h[off:], l[off:], cf[off:], v[off:]
        ax = fig.add_subplot(gs[2 * row, col]); axv = fig.add_subplot(gs[2 * row + 1, col], sharex=ax)
        for k in range(len(c2)):
            cl = "#26a69a" if c2[k] >= o2[k] else "#ef5350"
            ax.vlines(k, l2[k], h2[k], color=cl, lw=0.7)
            ax.add_patch(plt.Rectangle((k - 0.3, min(o2[k], c2[k])), 0.6, max(abs(c2[k] - o2[k]), 1e-9), color=cl))
            axv.bar(k, v2[k], color=cl, width=0.7)
        for arr, cl in ((SH.ema(cf, 10), "#1f77b4"), (SH.ema(cf, 21), "#d62728"), (SH.sma(cf, 50), "#2ca02c")):
            ax.plot(range(len(c2)), arr[off:], color=cl, lw=0.9)
        ax.hlines(r.level, max(0, len(c2) - 46), len(c2) + 1, colors="black", linestyles="dashed", lw=1.0)
        ax.axvspan(len(c2) - 10.5, len(c2) - 0.5, color="#ffd54f", alpha=0.18)
        ax.set_yscale("log"); ax.yaxis.set_major_formatter(SH.ScalarFormatter()); ax.yaxis.set_minor_formatter(SH.NullFormatter())
        ax.set_xticks([]); axv.set_xticks([]); ax.tick_params(labelsize=7); axv.tick_params(labelsize=5)
        ax.set_title(f"{t} · buy day {E}\n{label}\nlast 10 days (shaded) span {m.hl10:.1f} daily ranges", fontsize=11, loc="left",
                     color="#b71c1c" if col == 0 else "#1b5e20")
        out.append(f"{t}\t{E}\thl10={m.hl10:.2f}")
fig.suptitle("Left: charts you rejected. Right: Qullamaggie big-winner buys that the matching check would also throw out.\n"
             "Each ends the night before the buy day · dashed = buy level · blue EMA10, red EMA21, green SMA50", fontsize=12)
fig.savefig(os.path.join(HERE, "pairs.png"), dpi=90, bbox_inches="tight")
print("\n".join(out))
