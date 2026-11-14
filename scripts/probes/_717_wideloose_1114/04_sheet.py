#!/usr/bin/env python3
"""#717 wide-and-loose: the sheet he asked for — Qullamaggie's real buys that score as wide and loose as his def-no charts
(2026-11-14). NOT outcome-blind by his ask: ticker, buy day, tier, big-winner flag and the measure are on every chart.
Row 1 = his three def-no charts. Then the 16 most extreme HEADLINE buys (fixed buy day, full chart) at score >= 1, most
extreme first; a second buy of the same ticker within 10 sessions of one already shown is skipped (the same chart).
Drawing as _717_pairs_1114/pairs.py: 189 bars to the night before the buy, EMA10 / EMA21 / SMA50, dashed buy level, last 10 days shaded.
    python3 scripts/probes/_717_wideloose_1114/04_sheet.py > scripts/probes/_717_wideloose_1114/04_sheet.out
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..")); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_qm_confidence_1111")); import sheet as SH  # noqa
import wl
plt = SH.plt
WHY = {"weak_pivot": "weak pivot", "ep_gap": "gap-up day, not a breakout", "downtrend": "in a downtrend", "no_level": "no level cleared", "gives_back": "gave back over half its run",
       "close_break": "cleared on closes", "short_pivot": "short pivot", "fund": "fund", "range_break": "range break", "range_break_partial": "partial range break", "broke_before": "broke out earlier",
       "bounce": "bounce off a low", "ipo": "new listing", "inside_range": "pivot inside a range"}
gr = pd.read_csv(os.path.join(HERE, "graded_rows.tsv"), sep="\t")
WG = np.load(os.path.join(HERE, "graded_windows200.npy"))
mg = wl.measures(WG[gr.wid.to_numpy()])
d3 = gr.ticker.isin(["TDOC", "MELI", "RRC"]).to_numpy()
WIDE_MIN, CHOP_MIN = float(mg.box20_chart[d3].min()), float(mg.churn20_chart[d3].min())
gr["wide"], gr["chop"], gr["legs15"] = mg.box20_chart, mg.churn20_chart, mg["swn20_0.15"]; gr["score"] = wl.score(mg, WIDE_MIN, CHOP_MIN)
qm = pd.read_csv(os.path.join(HERE, "03_qm_scored.tsv"), sep="\t", dtype={"eid": str}, keep_default_na=False, na_values=[""])
WQ = np.load(os.path.join(HERE, "qm_windows200.npy"))
H = qm[(qm.fixed_day == 1) & (qm.nbars >= 189) & (qm.score >= 1.0)].sort_values("score", ascending=False)
picks, skipped = [], []
for r in H.itertuples():
    if any(p.ticker == r.ticker and abs((pd.Timestamp(p.E) - pd.Timestamp(r.E)).days) <= 14 for p in picks):
        skipped.append(f"{r.ticker} {r.E}"); continue
    if len(picks) < 16:
        picks.append(r)
items = [("you", r) for r in gr[d3].set_index("ticker").loc[["TDOC", "MELI", "RRC"]].reset_index().itertuples()] + [None] + [("qm", r) for r in picks]
ncol = 4; nrow = (len(items) + ncol - 1) // ncol
fig = plt.figure(figsize=(26, 6.6 * nrow))
gs = fig.add_gridspec(2 * nrow, ncol, height_ratios=[3, 1] * nrow, hspace=0.62, wspace=0.12)
out = []
for n, it in enumerate(items):
    rr, cc = divmod(n, ncol)
    if it is None:
        ax = fig.add_subplot(gs[2 * rr, cc]); ax.axis("off")
        ax.text(0.0, 1.0, "HOW TO READ THE NUMBERS\n\n"
                "range = how much of the chart's height the last\n20 sessions span (high to low)\n\n"
                "up-and-down = how far price travelled BOTH ways\nin those 20 sessions (the smaller of all up closes\nand all down closes), against the chart's height\n\n"
                f"The line = your least extreme def-no chart (TDOC):\nrange {WIDE_MIN:.0%} and up-and-down {CHOP_MIN:.0%}.\n"
                "Every Qullamaggie buy below is at or past BOTH.\n\n"
                "big swings = moves of 15%+ of the chart's height\ninside the 20 sessions (1-2 = one V, 3+ = repeated chop)",
                fontsize=13, va="top", family="monospace")
        continue
    kind, r = it
    W = (WG if kind == "you" else WQ)[r.wid]
    ok = ~np.isnan(W[3]); o, h, l, cf, v = (W[j][ok] for j in range(5))
    off = max(0, len(cf) - 189)
    o2, h2, l2, c2, v2 = o[off:], h[off:], l[off:], cf[off:], v[off:]
    ax = fig.add_subplot(gs[2 * rr, cc]); axv = fig.add_subplot(gs[2 * rr + 1, cc], sharex=ax)
    for k in range(len(c2)):
        cl = "#26a69a" if c2[k] >= o2[k] else "#ef5350"
        ax.vlines(k, l2[k], h2[k], color=cl, lw=0.7)
        ax.add_patch(plt.Rectangle((k - 0.3, min(o2[k], c2[k])), 0.6, max(abs(c2[k] - o2[k]), 1e-9), color=cl))
        axv.bar(k, v2[k], color=cl, width=0.7)
    for arr, cl in ((SH.ema(cf, 10), "#1f77b4"), (SH.ema(cf, 21), "#d62728"), (SH.sma(cf, 50), "#2ca02c")):
        ax.plot(range(len(c2)), arr[off:], color=cl, lw=0.9)
    lvl = r.level if r.level == r.level and r.level / cf[-1] <= 1.15 else None
    if lvl:
        ax.hlines(lvl, max(0, len(c2) - 46), len(c2) + 1, colors="black", linestyles="dashed", lw=1.0)
    ax.axvspan(len(c2) - 10.5, len(c2) - 0.5, color="#ffd54f", alpha=0.18)
    ax.set_yscale("log"); ax.yaxis.set_major_formatter(SH.ScalarFormatter()); ax.yaxis.set_minor_formatter(SH.NullFormatter())
    ax.set_xticks([]); axv.set_xticks([]); ax.tick_params(labelsize=7); axv.tick_params(labelsize=5)
    nums = f"range {r.wide:.0%} · up-and-down {r.chop:.0%} · big swings {int(r.legs15)} · {r.score:.2f}x the line"
    if kind == "you":
        t = f"YOU: def no — {r.ticker} · buy day {r.E}\n{nums}"
        col = "#b71c1c"
    else:
        t = (f"QULLAMAGGIE BUY — {r.ticker} · buy day {r.E}\ntier {r.tier} ({WHY.get(r.reason, r.reason)}) · big winner: {'YES' if r.big else 'no'}\n{nums}"
             + ("" if lvl else "\n(no buy level drawn)"))
        col = "#1b5e20" if r.tier in ("High", "Medium") else "#37474f"
    ax.set_title(t, fontsize=11.5, loc="left", color=col)
    out.append(f"{kind}\t{r.ticker}\t{r.E}\t{getattr(r, 'tier', '-')}\t{getattr(r, 'reason', '-')}\tbig={getattr(r, 'big', '-')}\twide={r.wide:.3f}\tchop={r.chop:.3f}\tlegs15={int(r.legs15)}\tscore={r.score:.3f}\tlevel={'drawn' if lvl else 'none'}")
fig.suptitle("Top row: your three def-no charts. Below: the Qullamaggie buys that measure as wide and loose as them or more, most extreme first.\n"
             "Each chart ends the night before the buy day · dashed = buy level · blue EMA10, red EMA21, green SMA50 · last 10 days shaded", fontsize=15, y=0.905)
fig.savefig(os.path.join(HERE, "sheet_qm_wide_loose.png"), dpi=80, bbox_inches="tight")
print(f"line: range >= {WIDE_MIN:.4f} and up-and-down >= {CHOP_MIN:.4f}; headline buys at or past it: {len(H)}; shown {len(picks)}; skipped as the same chart: {skipped}")
print("\n".join(out))
