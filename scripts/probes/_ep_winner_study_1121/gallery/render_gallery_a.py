#!/usr/bin/env python3
"""EP winner study step 5 — WINNER GALLERY A (prereg §7A), DISCOVERY ONLY, seed 1121. First 3 winner sheets + 3 paired failure sheets.
Bars: era-A discovery tickers only, cut at ci(2020-12-31)+60 (asserted); every era-B series dropped unread; every event E <= 2020-12-31 (asserted).
Never opens events_scored.tsv.gz / run.txt. No network/DB."""
import sys, pickle
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter, NullFormatter
HERE = Path(__file__).resolve().parent
S1 = HERE.parent / "build/stage1"; S3 = HERE.parent / "build/stage3"
sys.path.insert(0, str(S1))
import common as C, features as F
NSHEETS = 3; PRE, POST = 250, 60; W = PRE + POST + 1
cal = C.calendars()["A"]
ci_last = int(np.searchsorted(cal, C.DISC_LAST)); assert cal[ci_last] == C.DISC_LAST
CI_MAX = ci_last + POST
ft = pd.read_csv(S1 / "feature_table.tsv.gz", sep="\t", keep_default_na=False, dtype={"ticker": str, "E": str})
ft = ft[ft.set == "DISC"].reset_index(drop=True)
out = pd.read_csv(S3 / "discovery_outcomes.tsv.gz", sep="\t", keep_default_na=False, dtype={"ticker": str, "E": str})
pop = pd.read_csv(S1 / "population.tsv", sep="\t", keep_default_na=False, dtype={"ticker": str, "E": str})
pop = pop[pop.set == "DISC"].reset_index(drop=True)
assert len(ft) == len(out) == len(pop) == 2414
assert (ft.ticker.values == out.ticker.values).all() and (ft.E.values == out.E.values).all() and (pop.E.values == ft.E.values).all()
assert (ft.E <= C.DISC_LAST).all() and (ft.era == "A").all()
ev = ft.copy()
for c in ["maxc_ratio", "big_winner", "monster", "fail_pool"]: ev[c] = pd.to_numeric(out[c])
ev["iE"] = pop.iE.astype(int).values; ev["open"] = pd.to_numeric(pop.open).values
ev["adr20"] = pd.to_numeric(ev.adr20_raw, errors="coerce"); ev["dmin"] = pd.to_numeric(ev.B1, errors="coerce")
assert ev.big_winner.sum() == 302 and ev.monster.sum() == 102 and ev.fail_pool.sum() == 955
# bars (era A discovery tickers only)
allb = pickle.load(open(S1 / "cache/bars_event_tickers.pkl", "rb")); need = set(ev.ticker); bars = {}
for (era, t), b in allb.items():
    if era != "A" or t not in need: continue
    d, ci, o, h, l, c, v = b; k = int(np.searchsorted(ci, CI_MAX, side="right"))
    bars[t] = (d[:k], np.asarray(ci[:k]), np.asarray(o[:k], float), np.asarray(h[:k], float), np.asarray(l[:k], float), np.asarray(c[:k], float), np.asarray(v[:k], float))
del allb
assert max(b[0][-1] for b in bars.values()) <= cal[CI_MAX]
# seeded draw
rng = np.random.default_rng(C.SEED)
mon = ev[ev.monster == 1].index.to_numpy(); rest = ev[(ev.big_winner == 1) & (ev.monster == 0)].index.to_numpy()
order = list(rng.permutation(mon)) + list(rng.permutation(rest))
pair_used = set(); sheets = []
failidx = ev[ev.fail_pool == 1].index.to_numpy()
for s in range(NSHEETS):
    wins = order[12 * s:12 * s + 12]; fails = []; notes = []
    months = sorted(ev.month.values[wins]); allm = sorted(ev.month.unique())
    for w in wins:  # one failure per winner, same (era, month), random; nearest month if none left
        m = ev.month.iat[w]; cand = [f for f in failidx if ev.month.iat[f] == m and f not in pair_used]
        note = ""
        if not cand:
            j = allm.index(m)
            for dd in range(1, len(allm)):
                for mm in (allm[max(j - dd, 0)], allm[min(j + dd, len(allm) - 1)]):
                    cand = [f for f in failidx if ev.month.iat[f] == mm and f not in pair_used]
                    if cand: note = f"month fallback {m}->{mm}"; break
                if cand: break
        f = int(rng.choice(cand)); pair_used.add(f); fails.append(f); notes.append(note)
    sheets.append((wins, fails, notes))
def ident(t):  # status-suffix symbol shown by its identity symbol (5 letters ending in Q)
    return t[:-1] if len(t) == 5 and t.endswith("Q") else t
def ema(x, n):
    a = 2 / (n + 1); o = np.empty(len(x)); o[0] = x[0]
    for i in range(1, len(x)): o[i] = a * x[i] + (1 - a) * o[i - 1]
    return o
def fmt(k, v):
    if v == "" or (isinstance(v, float) and not np.isfinite(v)): return "n/a"
    if k in ("f15", "f16"): return "yes" if float(v) >= 0.5 else "no"
    x = float(v); a = abs(x)
    return f"{x:.0f}" if a >= 1000 else (f"{x:.1f}" if a >= 10 else f"{x:.2f}")
def featlines(i):
    vals = [f"{k} {fmt(k, ev[k].iat[i])}" for k in F.FEATS] + [f"dmin {fmt('B1', ev.dmin.iat[i])}", f"adr20 {fmt('x', ev.adr20.iat[i])}"]
    return ["  ".join(vals[j:j + 6]) for j in range(0, len(vals), 6)]
def draw(ax, axv, axt, i, letter, kind):
    t = ev.ticker.iat[i]; iE = int(ev.iE.iat[i]); oE = float(ev.open.iat[i])
    d, ci, o, h, l, c, v = bars[t]; lo = iE - PRE; hi = iE + POST
    sel = np.flatnonzero((ci >= lo) & (ci <= hi)); x = ci[sel] - lo
    for xi, k in zip(x, sel):
        col = "#26a69a" if c[k] >= o[k] else "#ef5350"
        ax.vlines(xi, l[k], h[k], color=col, lw=0.6); ax.add_patch(plt.Rectangle((xi - 0.3, min(o[k], c[k])), 0.6, max(abs(c[k] - o[k]), 1e-9), color=col))
        axv.bar(xi, v[k], color=col, width=0.7)
    cc = c; full_ci = ci
    for n, col in ((10, "#1f77b4"), (21, "#d62728"), (50, "#2ca02c"), (200, "#9467bd")):
        arr = ema(cc, n) if n in (10, 21) else pd.Series(cc).rolling(n).mean().values
        ax.plot(ci[sel] - lo, arr[sel], color=col, lw=0.8)
    ax.set_yscale("log"); ax.yaxis.set_major_formatter(ScalarFormatter()); ax.yaxis.set_minor_formatter(NullFormatter())
    ax.axvline(PRE, color="orange", lw=1.0, alpha=0.7)
    ax.axhline(oE * 1.5, color="gray", lw=0.6, ls=":"); ax.axhline(oE * 2.0, color="gray", lw=0.6, ls=":")
    ax.set_xlim(-2, W + 1); axv.set_xlim(-2, W + 1)
    tag = " | MONSTER >=2x" if ev.monster.iat[i] == 1 else ""
    unt = " | untyped (likely a fund)" if ev.sectype.iat[i] == "" else ""
    ax.set_title(f"{letter}  {ident(t)}  E {ev.E.iat[i]}  {kind}  max close {ev.maxc_ratio.iat[i]:.2f}x open" + ("\n" + (tag + unt).strip(" |") if (tag + unt) else ""), fontsize=9, loc="left")
    ax.tick_params(labelsize=6); axv.tick_params(labelsize=5); ax.set_xticks([]); axv.set_xticks([])
    axt.axis("off"); axt.text(0, 1, "\n".join(featlines(i)), va="top", ha="left", fontsize=6.3, family="monospace", transform=axt.transAxes)
keyrows = []
for s, (wins, fails, notes) in enumerate(sheets, 1):
    for kind, idxs, name in (("WINNER", wins, f"sheet_{s:02d}.png"), ("FAILURE", fails, f"fail_{s:02d}.png")):
        fig = plt.figure(figsize=(26, 22)); gs = fig.add_gridspec(9, 4, height_ratios=[4, 1.2, 1.1] * 3, hspace=0.35, wspace=0.12)
        for n, i in enumerate(idxs):
            r, cc_ = divmod(n, 4); L = "ABCDEFGHIJKL"[n]
            draw(fig.add_subplot(gs[3 * r, cc_]), fig.add_subplot(gs[3 * r + 1, cc_]), fig.add_subplot(gs[3 * r + 2, cc_]), i, L, kind)
            keyrows.append((name, L, kind, ident(ev.ticker.iat[i]), ev.E.iat[i], "monster" if ev.monster.iat[i] == 1 else ("winner" if ev.big_winner.iat[i] == 1 else "failure"),
                            f"{ev.maxc_ratio.iat[i]:.3f}", notes[n] if kind == "FAILURE" else "", " ".join(featlines(i))))
        fig.suptitle(f"EP winner study — Gallery A (discovery, outcome KNOWN) — {name} — {kind}S, daily E-250..E+60, orange = E, dotted = 1.5x / 2x open(E); under each: 20 features + dmin + ADR20", fontsize=12)
        fig.savefig(HERE / name, dpi=90, bbox_inches="tight"); plt.close(fig)
with open(HERE / "key_sheets_01-03.tsv", "w") as fh:
    fh.write("sheet\tletter\tkind\tticker(identity symbol)\tE\tclass\tmax_close_over_open\tpairing_note\tfeatures\n")
    for r in keyrows: fh.write("\t".join(r) + "\n")
print("seed", C.SEED, "winner order head (monsters first):", [ (ev.ticker.iat[i], ev.E.iat[i]) for i in order[:3]]); print(len(keyrows), "charts")
