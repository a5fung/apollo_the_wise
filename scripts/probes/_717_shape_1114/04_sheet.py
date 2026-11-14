#!/usr/bin/env python3
"""#717 shape checks: ONE outcome-blind grading sheet (2026-11-14; offline, $0, ERA A ONLY, no rule changed).
Exactly `_717_reasons_1114/03_sheet.py` (12 names at random, seed 717, one chart per ticker, from what the 5 slots would
take in era A: the day's passing fires, top 5 by PLAIN 20-day dollar volume; 189 daily bars ending on the list night D;
the breakout day is not drawn; no ticker / date / score on the image; the key is a separate do-not-show file) with the
stack of 03_score.py (stack.txt): 1d + (iv)B (at least T of the last 10 closes within 2 daily ranges under the level).
((iii)B was in the first-run stack; the grade-matching fix showed it removes one of his ok charts, WDC -> out of the stack.)
NOTE: (iv)B changes about 1% of the picks against 1d alone — this sheet is in effect a fresh draw of the 1d list. Excluded: every graded ticker (36)
and every fire day on the THREE earlier sheets. Bars: cb702_pre_v2 only.

    python3 scripts/probes/_717_shape_1114/04_sheet.py > scripts/probes/_717_shape_1114/04_sheet.out
"""
import importlib.util, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PM = os.path.join(REPO, "scripts/probes/_717_pick_model_1113")
PREV = os.path.join(REPO, "scripts/probes/_717_reasons_1114")
spec = importlib.util.spec_from_file_location("m", os.path.join(PM, "02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
P2, P = M.P2, M.P
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_qm_confidence_1111")); sys.path.insert(0, os.path.join(REPO, "tests/fixtures"))
import sheet as SH  # noqa: E402
from breakout_list_grades import MODEL_PICK_GRADES  # noqa: E402
plt = SH.plt
OUT = os.path.join(HERE, "sheet_shape_stack_dollar_volume_picks.png")
N, SHOWN, SEED = 12, 189, 717
st = dict(l.split("\t") for l in open(os.path.join(HERE, "stack.txt")).read().splitlines() if "\t" in l)
assert list(st) == ["(iv)B closes near the level"], st
T_NEAR = float(st["(iv)B closes near the level"])

df, cal, big = M.load()
f = df[df.fire].join(pd.read_parquet("/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"), rsuffix="_m")
sm = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_shape_1114/fires_shape_measures.parquet")
assert (sm.index == f.index).all()
f = f.join(sm[["ll_3.0", "near10"]])
n0 = len(f)
f1 = f[~((f.u50 < -0.03) & (f.s50_chg10 < 0))]
f = f1[f1.near10 >= T_NEAR].copy()
f["rank"] = f.groupby("ci").dollar_vol20.rank(ascending=False, method="first").astype(int)
picks = P2.top_k(f, f.dollar_vol20).sort_values(["ci", "ticker"]).reset_index(drop=True)
base_picks = P2.top_k(df[df.fire], df[df.fire].dollar_vol20)
d1_picks = P2.top_k(f1, f1.dollar_vol20)
same = len(set(zip(picks.ci, picks.ticker)) & set(zip(base_picks.ci, base_picks.ticker)))
same1 = len(set(zip(picks.ci, picks.ticker)) & set(zip(d1_picks.ci, d1_picks.ticker)))
used_E = set()
for k in (os.path.join(PM, "sheet_model_picks.png.key_do_not_show.txt"), os.path.join(PM, "sheet_template_picks.png.key_do_not_show.txt"),
          os.path.join(PREV, "sheet_stack_dollar_volume_picks.png.key_do_not_show.txt")):
    for line in open(k).read().splitlines():
        p = line.split("|")
        if len(p) > 2 and p[2][:2] == "20":
            used_E.add(p[2][:10])
assert len(used_E) >= 30, used_E
seen = {g.ticker for g in MODEL_PICK_GRADES}
assert len(seen) == 36
chosen = []
for i in np.random.default_rng(SEED).permutation(len(picks)):
    r = picks.iloc[int(i)]
    if r.ticker not in seen and r.E not in used_E:
        seen.add(r.ticker); chosen.append(r)
    if len(chosen) == N:
        break
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
key = [f"stack = 1d (more than 3% under a FALLING 50-day -> out) + fewer than {T_NEAR:.0f} of the last 10 closes within 2 daily ranges of the level -> out; ranking = 20-day dollar volume",
       "letter|ticker|fire day E (list night D)|dollar-volume rank among that day's passing fires|Qullamaggie bought? (scorecard, on E)|his-buy window|bought within +-5 sessions (panel)"]
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
tk0, tk1 = M.taken_set(base_picks), M.taken_set(picks)
print(f"{OUT}: {len(chosen)} charts from {len(picks):,} picks on {picks.ci.nunique()} era-A days (fires {n0:,} -> {len(f1):,} after 1d -> {len(f):,} after the stack); "
      f"{same:,} of the {len(base_picks):,} no-stack dollar-volume picks are unchanged ({1 - same / len(base_picks):.1%} replaced); vs the 1d-only picks {1 - same1 / len(d1_picks):.1%} replaced; "
      f"Qullamaggie buys the daily top 5 by dollar volume takes: no stack {len(tk0)} ({len(tk0 & big)} big), after the stack {len(tk1)} ({len(tk1 & big)} big); "
      f"Qullamaggie buys on the sheet (scorecard): {sum(bool(r.is_qm) for r in chosen)}; bought within +-5 (panel): {sum(bool(r.bought) for r in chosen)}; years on the sheet {sorted(r.E[:4] for r in chosen)}")
