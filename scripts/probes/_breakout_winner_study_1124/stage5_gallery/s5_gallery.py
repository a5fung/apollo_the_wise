#!/usr/bin/env python3
"""STAGE 5 - WINNER GALLERY A (prereg 7.A; A1, A3 in force). Read-only on bars; writes PNGs + a key file under this directory only.

READINGS (fixed here, before rendering):
 R1 pool = seed-1124 KEPT discovery events with E <= 2020-10-06 (the embargo); winners = big==1 (>=1.5x), monsters = monster==1 (>=2.0x, subset).
    Winner count <= 600, so ALL are rendered (no 600-sample). Order: monsters first, then other winners; seeded Random(1124) shuffle inside each tier;
    sheets of 12 in that order. Never hand-picked.
 R2 failures = kept discovery events E <= 2020-10-06 with failed==1 (<1.10x), not window-truncated. Each winner sheet gets 12 failures:
    one per winner, same E month (nearest earlier-then-later month with a failure left, when the month is used up), never the identity of a winner
    on the paired sheet, never reused. Draw order seeded Random(1124).
 R3 chart: calendar slots ci(D)-250 .. ci(D)+61 (312 slots, every chart the same width; a missing bar leaves a gap); E = slot 251; level(D) dashed
    across; EMA10, EMA21, SMA50, SMA200 computed on the name's own adjusted bars (all bars <= the window end); log price axis, no price labels.
    NO ticker, NO date on any chart (A3: show no ticker; the prereg lists no date). File names carry only pair number.
 R4 text under each chart: chart id, outcome, pick grade (live cut-offs on B1 = pick_score) and all 24 feature values.
 R5 SEAL: bars read only with date <= 2020-12-31; window end cal[ci+61] <= 2020-12-31 asserted per chart. Nothing after 2024-12-31 is touched.
"""
import gzip, hashlib, json, random, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
S1 = HERE.parent
REPO = HERE.parents[3]
DATA = Path("/Users/alvinfung/apollo_data")
PRE = {"docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md": "3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a",
       "docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md": "4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10",
       "docs/analysis/breakout_winner_study_prereg_amendment_A3_2026-11-26.md": "a0c11a3685bc83369a9fba29766368e82734432ea9a3a464fd363787e6d34268"}
for p, h in PRE.items():
    assert hashlib.sha256((REPO / p).read_bytes()).hexdigest() == h, f"{p} sha differs - STOP"
TABLE = S1 / "stage1f/feature_table.tsv.gz"
assert hashlib.sha256(TABLE.read_bytes()).hexdigest() == "d629ef0af85f0ed3404d0e9cffcc6545627fa3dec6230eb4da94cb3ed95bf53c"
EMB, SEAL = "2020-10-06", "2020-12-31"
CUTS = (("A+", -3.4942), ("A", -4.1845), ("B", -4.8715))
OUTD = HERE / "pairs"
KEYD = HERE / "_key"
OUTD.mkdir(exist_ok=True); KEYD.mkdir(exist_ok=True)
LOG = []
def P(s=""):
    print(s, flush=True); LOG.append(s)
t0 = time.time()

def grade(s):
    if s is None or pd.isna(s): return "-"
    for g, c in CUTS:
        if s >= c: return g
    return "C"

O = pd.read_csv(S1 / "stage3/discovery_outcomes.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str})
T = pd.read_csv(TABLE, sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str}, low_memory=False)
T = T[(T.kept == True) & (T.set == "DISC")]
assert T.E.max() <= SEAL
O = O[(O.kept == True) & (O.E <= EMB)]
assert (O.era == "A").all() and O.E.max() <= EMB
import pyarrow.parquet as pq
EV = pq.read_table(DATA / "cb702/bws1124_events_postdrop.parquet", columns=["era", "ci", "ticker", "level", "D", "E"], filters=[("E", "<=", EMB)]).to_pandas()
Tk = T.set_index(["ticker", "D", "E"])
X = O.merge(EV[["ticker", "D", "E", "level"]], on=["ticker", "D", "E"], how="left", validate="1:1")
assert X.level.notna().all()
X = X.merge(T.drop(columns=["era", "ci", "kept", "kept2411", "Ey", "month", "set", "failed"]), on=["ticker", "D", "E"], how="left", validate="1:1")
assert X.f01.notna().all() and len(X) == len(O)
X["winner"] = X.big == 1
X["mult"] = X.maxc / X.proxy if "maxc" in X else np.nan
W = X[X.winner].copy(); Fp = X[(X.failed == 1) & (X.truncated.isna() | (X.truncated == ""))].copy()
P(f"pool: {len(X)} kept discovery events E<={EMB}; winners {len(W)} (monsters {int((W.monster == 1).sum())}); failure pool {len(Fp)}; truncated winners {int(W.truncated.notna().sum() - (W.truncated == '').sum())}")
assert len(W) <= 600
rng = random.Random(1124)
def shuf(df):
    idx = list(df.index); rng.shuffle(idx); return df.loc[idx]
Wm = shuf(W[W.monster == 1]); Wo = shuf(W[W.monster != 1])
W = pd.concat([Wm, Wo]).reset_index(drop=True)
nsheet = (len(W) + 11) // 12
months = sorted(X.month.unique())
used = set(); pairs = []
for s in range(nsheet):
    w = W.iloc[s * 12:(s + 1) * 12]
    ids = set(w.ticker)
    picks = []
    quota = list(w.month)
    # one failure per winner month; pad to 12 when the last sheet is short (reuse the sheet's months in order)
    q = (quota * 3)[:12]
    for m in q:
        order = sorted(months, key=lambda mm: (abs(months.index(mm) - months.index(m)), months.index(mm) > months.index(m)))
        got = None
        for mm in order:
            cand = Fp[(Fp.month == mm) & (~Fp.ticker.isin(ids)) & (~Fp.index.isin(used))]
            if len(cand):
                got = cand.loc[rng.choice(list(cand.index))]; break
        assert got is not None, "failure pool exhausted"
        used.add(got.name); picks.append(got); ids = ids  # identity of failures may repeat across sheets; not within a sheet below
        ids = ids | {got.ticker}
    pairs.append((w, pd.DataFrame(picks)))
P(f"sheets: {nsheet} pairs; failures used {len(used)}; same-month exact {sum(1 for w,f in pairs for a,b in zip((list(w.month)*3)[:12], f.month) if a==b)} of {nsheet*12}")

# ---- bars (adjusted OHLCV), only needed tickers, only dates <= SEAL
need = set(W.ticker) | set(pd.concat([f for _, f in pairs]).ticker)
cal = [l.strip() for l in open(DATA / "cb702/bws1124_eraA_list_ctx.cal.txt")]
cix = {d: i for i, d in enumerate(cal)}
rows = {t: [] for t in need}
mx = ""
with gzip.open(DATA / "cb702_pre_v2/daily_closes_all.csv.gz", "rt") as fh:
    for ln in fh:
        t, rest = ln.split(",", 1)
        if t not in need: continue
        d = rest[:10]
        if d > SEAL: continue
        mx = max(mx, d)
        rows[t].append(rest)
assert mx <= SEAL
P(f"bars: {sum(len(v) for v in rows.values())} rows for {len(need)} tickers; max date {mx} (ASSERT <= {SEAL}) | {time.time()-t0:.0f}s")
S = {}
for t, r in rows.items():
    a = pd.DataFrame([x.strip().split(",") for x in r], columns=["d", "o", "h", "l", "c", "v"])
    a[["o", "h", "l", "c", "v"]] = a[["o", "h", "l", "c", "v"]].astype(float)
    a = a.drop_duplicates("d").sort_values("d")
    a = a[a.d.isin(cix)]
    a["ci"] = a.d.map(cix)
    a["e10"] = a.c.ewm(span=10, adjust=False).mean(); a["e21"] = a.c.ewm(span=21, adjust=False).mean()
    a["s50"] = a.c.rolling(50).mean(); a["s200"] = a.c.rolling(200).mean()
    S[t] = a.set_index("ci")

FN = {"f01": "ADR%", "f02": "px", "f03": "$vol", "f04": "RSb", "f05": "RS1m", "f06": "RS6m", "f07": "prior", "f08": "run20", "f09": "6m", "f10": "/52wH",
      "f11": "isHi", "f12": "base", "f13": "depth", "f14": "range", "f15": "sprd", "f16": "contr", "f17": "dry", "f18": "u/d", "f19": "ext",
      "f20": "shape", "f21": "v200", "f22": "sinceLo", "f23": "1stBase", "f24": "gap"}
def fv(k, v):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "-"
    if k == "f03": return f"{v/1e6:.0f}M"
    if k in ("f11", "f14", "f23"): return "Y" if float(v) else "N"
    if k in ("f12", "f20", "f22"): return f"{float(v):.0f}"
    if k == "f02": return f"{v:.2f}"
    return f"{float(v):.3g}"

GCOL = {"win": "#1f7a3d", "fail": "#a33"}
def chart(ax, axv, r, role, cid):
    ci = int(r.ci) if "ci" in r else cix[r.D]
    lo, hi = ci - 250, ci + 61
    assert cal[hi] <= SEAL, "window end past the seal"
    a = S[r.ticker]
    nb = int(r.nbars)
    end = hi
    if r.truncated not in ("", None) and not pd.isna(r.truncated): end = min(hi, ci + nb)
    b = a.loc[(a.index >= lo - 0) & (a.index <= end)]
    x = b.index.values - lo
    up = b.c >= b.o
    col = np.where(up, "#2a8a4a", "#c0392b")
    ax.vlines(x, b.l, b.h, colors=col, linewidth=0.6)
    ax.bar(x, (b.c - b.o).abs().clip(lower=1e-9), bottom=np.minimum(b.o, b.c), width=0.75, color=col, linewidth=0)
    for k, c_, lw in (("e10", "#e0a000", .7), ("e21", "#1f77b4", .7), ("s50", "#8e44ad", .8), ("s200", "#555", .9)):
        ax.plot(x, b[k].values, color=c_, lw=lw)
    ax.axhline(r.level, color="k", ls="--", lw=.6)
    ax.axvline(251, color="#d4a000", lw=.8, alpha=.8)
    ax.set_xlim(-2, 313); ax.set_yscale("log")
    ymin, ymax = float(b.l.min()), float(b.h.max())
    ax.set_ylim(ymin * .96, ymax * 1.04)
    ax.set_xticks([]); ax.set_yticks([]); ax.minorticks_off()
    ax.tick_params(left=False, bottom=False)
    for s_ in ax.spines.values(): s_.set_color(GCOL[role]); s_.set_linewidth(1.4)
    axv.bar(x, b.v.values, width=.75, color=col, linewidth=0)
    axv.axvline(251, color="#d4a000", lw=.8, alpha=.8)
    axv.set_xlim(-2, 313); axv.set_xticks([]); axv.set_yticks([])
    for s_ in axv.spines.values(): s_.set_color("#bbb")
    mult = float(r.maxc)
    g = grade(r.B1)
    l1 = f"{cid}  {'WINNER' if role=='win' else 'FAILED'}  peak x{mult:.2f}  grade {g} (pick {r.B1:.2f})"
    items = [f"{FN[k]} {fv(k, r[k])}" for k in FN]
    l2 = "  ".join(items[0:8]); l3 = "  ".join(items[8:16]); l4 = "  ".join(items[16:24])
    axv.set_xlabel(l1 + "\n" + l2 + "\n" + l3 + "\n" + l4, fontsize=6.4, loc="left", labelpad=3, family="monospace")

key = []
for si, (w, f) in enumerate(pairs, 1):
    for role, df, nm in (("win", w, "winners"), ("fail", f, "failures")):
        fig = plt.figure(figsize=(26, 19.5), dpi=80)
        gs = fig.add_gridspec(3, 4, left=.01, right=.99, top=.955, bottom=.07, wspace=.06, hspace=.30)
        tier = "monsters (>=2.0x) first" if si == 1 else ""
        ttl = f"Pair {si:02d} - {'WINNERS (outcome known, discovery, E <= 2020-10-06)' if role=='win' else 'FAILURES from the same months (peak under 1.10x)'}    candles + volume, D-250 .. E+60; dashed = level; gold line = E; EMA10 orange, EMA21 blue, SMA50 purple, SMA200 grey"
        fig.suptitle(ttl, fontsize=10, y=.985)
        for j in range(len(df)):
            r = df.iloc[j]
            sub = gs[j // 4, j % 4].subgridspec(2, 1, height_ratios=[4, 1], hspace=.02)
            ax = fig.add_subplot(sub[0]); axv = fig.add_subplot(sub[1])
            cid = f"{si:02d}{'W' if role=='win' else 'F'}-{j+1:02d}"
            chart(ax, axv, r, role, cid)
            key.append(dict(chart=cid, pair=si, role=role, identity=r.ticker, D=r.D, E=r.E, month=r.month, monster=int(r.monster), peak_mult=round(float(r.maxc), 4), grade=grade(r.B1)))
        fn = OUTD / f"pair_{si:02d}_{nm}.png"
        fig.savefig(fn); plt.close(fig)
    if si % 8 == 0: P(f"  rendered {si}/{nsheet} pairs | {time.time()-t0:.0f}s")
pd.DataFrame(key).to_csv(KEYD / "gallery_A_key.tsv", sep="\t", index=False)
ids = sorted({k["identity"] for k in key})
(KEYD / "gallery_A_identities.txt").write_text("\n".join(ids) + "\n")
P(f"charts {len(key)}; identities shown {len(ids)}; pairs {nsheet}; script sha256 {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]} | {time.time()-t0:.0f}s")
(HERE / "5_gallery.txt").write_text("\n".join(LOG) + "\n")
