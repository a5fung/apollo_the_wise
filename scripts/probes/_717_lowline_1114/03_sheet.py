#!/usr/bin/env python3
"""#717 lower-line check: ONE fresh outcome-blind grading sheet (2026-11-14; offline, $0, ERA A ONLY, no rule changed).
_717_context_1114/05_sheet.py with the stack 1d + A2(10) + the lower-line check (ll.py: OUT when V3 > 0.212 AND the
30-session lower line is flat or falling, >= 189 bars). 12 names at random (seed 717), one chart per ticker, from the day's
passing fires' top 5 by plain 20-day dollar volume; drawing unchanged (189 bars ending on the list night, the breakout day
not drawn, no ticker / date / score on the image; key separate). Excluded: every ticker and every date on EVERY earlier
*.key_do_not_show.txt under scripts/probes/_717_* (globbed) and every MODEL_PICK_GRADES ticker. Bars: cb702_pre_v2 only.

    python3 scripts/probes/_717_lowline_1114/03_sheet.py > scripts/probes/_717_lowline_1114/03_sheet.out
"""
import glob, importlib.util, os, re, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PM = os.path.join(REPO, "scripts/probes/_717_pick_model_1113")
spec = importlib.util.spec_from_file_location("m", os.path.join(PM, "02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
P2, P = M.P2, M.P
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_qm_confidence_1111")); sys.path.insert(0, os.path.join(REPO, "tests/fixtures")); sys.path.insert(0, HERE)
import sheet as SH  # noqa: E402
import ll  # noqa: E402
from breakout_list_grades import MODEL_PICK_GRADES  # noqa: E402
plt = SH.plt
OUT = os.path.join(HERE, "sheet_lowline_picks.png")
N, SHOWN, SEED = 12, 189, 717
assert int(open(os.path.join(HERE, "02_big_lost.txt")).read()) == 0, "a big winner is lost — no sheet"

df, cal, big = M.load()
f = df[df.fire].join(pd.read_parquet("/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"), rsuffix="_m")
tr = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_rank_1114/fires_trend.parquet")
lw = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_lowline_1114/fires_lowline.parquet")
assert (tr.index == f.index).all() and (lw.index == f.index).all()
f = f.join(tr[["ret126"]]).join(lw)
n0 = len(f)
f1 = f[~((f.u50 < -0.03) & (f.s50_chg10 < 0))]
f2 = f1[~((f1.s50_chg10 < 0) & (f1.ret126 < 0))]
f = f2[~ll.flag(f2.V3, f2.LS30, f2.nbars)].copy()
assert (n0, len(f1), len(f2)) == (156695, 136305, 120872)
f["rank"] = f.groupby("ci").dollar_vol20.rank(ascending=False, method="first").astype(int)
picks = P2.top_k(f, f.dollar_vol20).sort_values(["ci", "ticker"]).reset_index(drop=True)
base_picks = P2.top_k(f2, f2.dollar_vol20)
same = len(set(zip(picks.ci, picks.ticker)) & set(zip(base_picks.ci, base_picks.ticker)))
seen = {g.ticker for g in MODEL_PICK_GRADES}
assert len(seen) == 48, len(seen)
used_D, DATE = set(), re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
for k in sorted(glob.glob(os.path.join(REPO, "scripts/probes/_717_*/**/*.key_do_not_show.txt"), recursive=True)):
    if os.path.abspath(k).startswith(HERE):
        continue
    cols, nt, nd = None, 0, 0
    for line in open(k).read().splitlines():
        p = line.split("|")
        if p[0] == "letter":
            cols = [i for i, c in enumerate(p) if c in ("ticker", "sym")]; continue
        if cols is None or len(p) < 2 or line.startswith("#"):
            continue
        for i in cols:
            if i < len(p) and p[i]:
                seen.add(p[i]); nt += 1
        for d in DATE.findall(line):
            used_D.add(d); nd += 1
    print(f"exclusions from {os.path.relpath(k, REPO)}: {nt} ticker fields, {nd} dates" + ("" if cols else "  (NO letter| header — nothing parsed)"))
print(f"excluded tickers {len(seen)}, excluded dates {len(used_D)}")
chosen = []
for i in np.random.default_rng(SEED).permutation(len(picks)):
    r = picks.iloc[int(i)]
    if r.ticker not in seen and r.E not in used_D and cal[r.ci].isoformat() not in used_D:
        seen.add(r.ticker); used_D.add(r.E); chosen.append(r)
    if len(chosen) == N:
        break
assert len(chosen) == N and all(r.E <= "2022-04-01" for r in chosen)
assert not any(bool(ll.flag(r.V3, r.LS30, r.nbars)) for r in chosen)
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
key = ["stack = 1d (more than 3% under a FALLING 50-day -> out) + A2 (50-day lower than 10 sessions ago AND a negative 126-session return -> out) + lower line (V3 > 0.212 AND the 30-session lower line flat or falling -> out); ranking = 20-day dollar volume",
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
print(f"{OUT}: {len(chosen)} charts from {len(picks):,} picks on {picks.ci.nunique()} era-A days (fires {n0:,} -> {len(f1):,} after 1d -> {len(f2):,} after A2(10) -> {len(f):,} after the lower line); "
      f"{1 - same / len(base_picks):.1%} of the 1d + A2(10) dollar-volume picks replaced; "
      f"Qullamaggie buys the daily top 5 by dollar volume takes: 1d + A2(10) {len(tk0)} ({len(tk0 & big)} big), + lower line {len(tk1)} ({len(tk1 & big)} big); "
      f"Qullamaggie buys on the sheet (scorecard): {sum(bool(r.is_qm) for r in chosen)}; bought within +-5 (panel): {sum(bool(r.bought) for r in chosen)}; years on the sheet {sorted(r.E[:4] for r in chosen)}")
