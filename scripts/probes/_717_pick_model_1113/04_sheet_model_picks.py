#!/usr/bin/env python3
"""#717 pick model — ONE outcome-blind chart sheet for the operator's eye (2026-11-13; offline, $0, ERA A ONLY, no rule
changed). 12 names drawn at random (seed 717, one chart per ticker, NOT stratified) from the MODEL's daily top-5 fires
on the test days (E 2021-01-04 .. 2022-04-01; coef.json, no refit). Each chart: 189 daily bars (~9 months) ENDING ON
THE LIST NIGHT D (the breakout day is not drawn), EMA10 blue / EMA21 red / SMA50 green, volume, log scale, the buy level
dashed. No ticker, date, score or label on the image; the key is a separate do-not-show file.
Drawing as `_717_qm_confidence_1111/sheet.py` (its buy-window shading and SMA200 left out). Bars: cb702_pre_v2 only.

    python3 scripts/probes/_717_pick_model_1113/04_sheet_model_picks.py
"""
import importlib.util, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("m", os.path.join(HERE, "02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
P2, P = M.P2, M.P
sys.path.insert(0, os.path.join(HERE, "..", "_717_qm_confidence_1111"))
import sheet as SH  # noqa: E402
plt = SH.plt
OUT = os.path.join(HERE, "sheet_model_picks.png")
N, SHOWN, SEED = 12, 189, 717

df, cal, big = M.load()
co = json.load(open(M.COEF))["models"]["primary"]
df["score_primary"] = M.X_of(df, co["features"]) @ np.r_[co["intercept"], co["coef"]]
f = df[(df.E >= M.TEST_FIRST) & df.fire].copy()
f["rank"] = f.groupby("ci").score_primary.rank(ascending=False, method="first").astype(int)
picks = P2.top_k(f, f.score_primary).sort_values(["ci", "ticker"]).reset_index(drop=True)
chosen, seen = [], set()
for i in np.random.default_rng(SEED).permutation(len(picks)):
    r = picks.iloc[int(i)]
    if r.ticker not in seen:
        seen.add(r.ticker); chosen.append(r)
    if len(chosen) == N:
        break
# his-buy windows by scorecard id
win = {}
b = pd.read_csv(f"{P2.FX}/buys.tsv", sep="\t", dtype=str, keep_default_na=False)
w = pd.read_csv(f"{P2.FX}/buys_undated_widened.tsv", sep="\t", dtype=str, keep_default_na=False)
win.update({"d" + r.eid: f"{r.E} (dated{', BIG WINNER' if r.big_winner == '1' else ''})" for r in b.itertuples()})
win.update({"w" + r.eid: f"{r.lo}..{r.hi} (undated sighting)" for r in w.itertuples()})

S, _ = P.setup()                       # era A store; asserts the calendar ends before 2025
D = S.D
tid = {}
for k, t in enumerate(D.tickers):
    tid.setdefault(t, []).append(k)
fig = plt.figure(figsize=(26, 18))
gs = fig.add_gridspec(6, 4, height_ratios=[3, 1] * 3, hspace=0.45, wspace=0.12)
key = ["letter|ticker|fire day E (list night D)|model rank among that day's fires|Qullamaggie bought? (scorecard, on E)|his-buy window|bought within +-5 sessions (panel)"]
for n, r in enumerate(chosen):
    bars = Di = None
    for k in tid[r.ticker]:
        bb, cidx = P.runner.bars_for(D, k)
        hit = np.flatnonzero(np.asarray(cidx) == r.ci)
        if len(hit) and abs(float(bb.c[hit[0]]) - r.close) < 1e-6 * max(1.0, r.close):
            bars, Di = bb, int(hit[0]); break
    assert bars is not None, r.ticker
    o, h, l, cf, v = (np.asarray(x[:Di + 1], float) for x in (bars.o, bars.h, bars.l, bars.c, bars.v))
    off = max(0, len(cf) - SHOWN)
    o, h, l, c, v = o[off:], h[off:], l[off:], cf[off:], v[off:]
    rr, cc = divmod(n, 4)
    ax = fig.add_subplot(gs[2 * rr, cc]); axv = fig.add_subplot(gs[2 * rr + 1, cc], sharex=ax)
    for k in range(len(c)):
        col = "#26a69a" if c[k] >= o[k] else "#ef5350"
        ax.vlines(k, l[k], h[k], color=col, lw=0.7)
        ax.add_patch(plt.Rectangle((k - 0.3, min(o[k], c[k])), 0.6, max(abs(c[k] - o[k]), 1e-9), color=col))
        axv.bar(k, v[k], color=col, width=0.7)
    for arr, col in ((SH.ema(cf, 10), "#1f77b4"), (SH.ema(cf, 21), "#d62728"), (SH.sma(cf, 50), "#2ca02c")):
        ax.plot(range(len(c)), arr[off:], color=col, lw=0.9)
    ax.hlines(r.level, max(0, len(c) - 46), len(c) + 1, colors="black", linestyles="dashed", lw=1.0)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(SH.ScalarFormatter()); ax.yaxis.set_minor_formatter(SH.NullFormatter())
    L = chr(ord("A") + n)
    ax.set_title(L, fontsize=13, loc="left"); ax.tick_params(labelsize=6); axv.tick_params(labelsize=5)
    ax.set_xticks([]); axv.set_xticks([])
    key.append(f"{L}|{r.ticker}|{r.E} ({cal[r.ci]})|{r['rank']}|{'YES' if r.is_qm else 'no'}|{'; '.join(win[i] for i in r.qm) or '-'}|{'yes' if r.bought else 'no'}{'' if r.covered else ' (no snapshot within 5 sessions)'}")
fig.suptitle("Breakout v1 — 12 names; each chart ends the night before the buy day; dashed = the buy level; blue EMA10, red EMA21, green SMA50", fontsize=12)
fig.savefig(OUT, dpi=100, bbox_inches="tight"); plt.close(fig)
open(OUT + ".key_do_not_show.txt", "w").write("\n".join(key) + "\n")
print(f"{OUT}: {len(chosen)} charts from {len(picks)} model picks on {picks.ci.nunique()} test days; Qullamaggie buys on the sheet (scorecard): {sum(bool(r.is_qm) for r in chosen)}; bought within +-5 (panel): {sum(bool(r.bought) for r in chosen)}")
