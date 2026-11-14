#!/usr/bin/env python3
"""#717 lower-line sheet (2026-11-14): Qullamaggie buys flagged by V3 > 0.212 AND lowslope(30) <= 0 (04_lowline.py, N=30).
Row 1 = his def-no MELI + TDOC; then up to 14 flagged buys, highest V3 first. Blue = fitted lower line through the
swing lows of the last 30 sessions (+ lowest low after the last pivot). Era A only. Drawing as _717_pairs_1114/pairs_v3.py."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SW_DIR = os.path.join(REPO, "scripts/probes/_717_contract_1114/swings"); WLD = os.path.join(REPO, "scripts/probes/_717_wideloose_1114")
sys.path.insert(0, SW_DIR); import sw, v3m
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_qm_confidence_1111")); import sheet as SH  # noqa
plt = SH.plt
N, WTHR = 30, 0.212

def fit(W):
    h, l = np.log(W[1]), np.log(W[2]); ok = np.isfinite(h) & np.isfinite(l); hh, ll = h[ok], l[ok]
    chart = hh[-sw.CHART:].max() - ll[-sw.CHART:].min(); H, L = hh[-N:], ll[-N:]
    p = sw.pivots(H, L); pts = [(i, v) for i, v, t in p if t == -1]; last = p[-1][0] if p else -1
    if last + 1 < N:
        j = last + 1 + int(np.argmin(L[last + 1:])); pts.append((j, L[j]))
    if len(pts) < 2: return 0.0, None, pts
    x = np.array([q[0] for q in pts], float); y = np.array([q[1] for q in pts]); b = np.polyfit(x, y, 1)
    return b[0] * 10 / chart, b, pts

gr = pd.read_csv(os.path.join(WLD, "graded_rows.tsv"), sep="\t"); WG = np.load(os.path.join(WLD, "graded_windows200.npy"))
qm = pd.read_csv(os.path.join(WLD, "qm_rows.tsv"), sep="\t", dtype={"eid": str}, keep_default_na=False, na_values=[""]); WQ = np.load(os.path.join(WLD, "qm_windows200.npy"))
qm["V3"] = v3m.v3(WQ[qm.wid.to_numpy()]); qm["LS"] = [fit(WQ[w])[0] if np.isfinite(v) else np.nan for w, v in zip(qm.wid, qm.V3)]
qm["key"] = qm.set.str[0] + qm.eid
sc = qm[qm.V3.notna()]
WTHR = float(sc[(sc.ticker == "MU") & (sc.E == "2021-12-21")].V3.iloc[0])  # exact W of 04_lowline.py = this must-pass (High-tier) row; strict > excludes it
fq = sc[(sc.LS <= 0) & (sc.V3 > WTHR)].drop_duplicates("key").sort_values("V3", ascending=False)
print(f"flagged {len(fq)} of {sc.key.nunique()} (V3>{WTHR}, lowslope{N}<=0)")
for r in fq.itertuples(): print(f"FLAG\t{r.ticker}\t{r.E}\t{r.tier}\tbig={r.big}\tV3={r.V3:.3f}\tLS={r.LS:+.3f}")
you = []
for t, E in (("MELI", "2018-09-18"), ("TDOC", "2020-03-20")):
    g = gr[(gr.ticker == t) & (gr.E == E)]; assert len(g) == 1, (t, E); you.append(g.iloc[0])
items = [("you", r) for r in you] + [("qm", r) for r in fq.head(14).itertuples()]
ncol = 4; nrow = (len(items) + ncol - 1) // ncol
fig = plt.figure(figsize=(26, 6.6 * nrow)); gs = fig.add_gridspec(2 * nrow, ncol, height_ratios=[3, 1] * nrow, hspace=0.75, wspace=0.12)
for n, (kind, r) in enumerate(items):
    rr, cc = divmod(n, ncol); W = (WG if kind == "you" else WQ)[int(r.wid)]
    v3 = float(v3m.v3(W[None])[0]); ls, b, pts = fit(W)
    ok = ~np.isnan(W[3]); o, h, l, cf, v = (W[j][ok] for j in range(5)); off = max(0, len(cf) - 189)
    o2, h2, l2, c2, v2 = o[off:], h[off:], l[off:], cf[off:], v[off:]
    ax = fig.add_subplot(gs[2 * rr, cc]); axv = fig.add_subplot(gs[2 * rr + 1, cc], sharex=ax)
    for k in range(len(c2)):
        cl = "#26a69a" if c2[k] >= o2[k] else "#ef5350"
        ax.vlines(k, l2[k], h2[k], color=cl, lw=0.7)
        ax.add_patch(plt.Rectangle((k - 0.3, min(o2[k], c2[k])), 0.6, max(abs(c2[k] - o2[k]), 1e-9), color=cl)); axv.bar(k, v2[k], color=cl, width=0.7)
    for arr, cl in ((SH.ema(cf, 10), "#1f77b4"), (SH.ema(cf, 21), "#d62728"), (SH.sma(cf, 50), "#2ca02c")): ax.plot(range(len(c2)), arr[off:], color=cl, lw=0.9)
    if b is not None:
        x0 = len(c2) - N; xs = np.arange(N); ax.plot(x0 + xs, np.exp(np.polyval(b, xs)), color="#0d47a1", lw=2.4)
        ax.scatter([x0 + i for i, _ in pts], [np.exp(y) for _, y in pts], color="#0d47a1", s=22, zorder=5)
    lvl = r.level if r.level == r.level and r.level / cf[-1] <= 1.15 else None
    if lvl: ax.hlines(lvl, max(0, len(c2) - 46), len(c2) + 1, colors="black", linestyles="dashed", lw=1.0)
    ax.axvspan(len(c2) - 10.5, len(c2) - 0.5, color="#ffd54f", alpha=0.18)
    ax.set_yscale("log"); ax.yaxis.set_major_formatter(SH.ScalarFormatter()); ax.yaxis.set_minor_formatter(SH.NullFormatter())
    ax.set_xticks([]); axv.set_xticks([]); ax.tick_params(labelsize=7); axv.tick_params(labelsize=5)
    kindw = "falling" if ls < -0.02 else ("flat" if ls <= 0.02 else "rising")
    nums = f"re-widening swing {v3*100:.0f}% of chart height\nlower line {kindw} ({ls:+.2f}/10 sessions)"
    if kind == "you": t, col = f"YOU: def no — {r.ticker} · buy day {r.E}\n{nums}", "#b71c1c"
    else:
        t = f"QULLAMAGGIE BUY — {r.ticker} · buy day {r.E}\ntier {r.tier} · big winner: {'YES' if r.big else 'no'}\n{nums}" + ("" if lvl else "\n(no buy level drawn)")
        col = "#1b5e20" if r.tier in ("High", "Medium") else "#37474f"
    ax.set_title(t, fontsize=11.5, loc="left", color=col)
fig.suptitle("Top row: your def-no charts. Below: Qullamaggie buys with a re-widening swing past 21% of chart height AND a flat/falling lower line, biggest first.\n"
             "Ends the night before the buy · dashed = buy level · BLUE THICK LINE = lower line fitted through the swing lows (dots) of the last 30 sessions · EMA10 blue, EMA21 red, SMA50 green", fontsize=14, y=0.955)
fig.savefig(os.path.join(HERE, "sheet_qm_flagged.png"), dpi=80, bbox_inches="tight")
