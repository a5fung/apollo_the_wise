#!/usr/bin/env python3
"""#717 'range does not contract' — VOLATILITY-TREND angle (2026-11-14; offline, $0, ERA A fires; research, no rule changed).

PREREG — written BEFORE any score below was computed.
 His rule (operator_shared_notes 2026-11-14): wide is NOT the defect; the defect is a range that does NOT CONTRACT into the buy
 with erratic up-and-down ("wide lose bars, large up and large down, it's not tightening"). PENN's pass reason is one-way legs
 ("gap down over days then rebound, not wide loose range up and down"), so the erratic part counts ALTERNATIONS of large daily
 moves, not two-way travel (a V scores high on two-way travel). Defect = NOT CONTRACTING **AND** ERRATIC.
 One function, bars <= the list night D (index -1), log prices, last 80 bars only (fires have 80):
   TR   = true range (log)
   CR   = mean TR of the last 10 sessions / mean TR of the 15 sessions before them (sessions -25..-11)   [>= 1 = flat/rising]
   ALT  = over the last 15 sessions, sum of min(|d_i|, |d_{i-1}|) for every close-to-close move d_i whose sign flips from
          d_{i-1}, divided by the 80-bar chart height (max high - min low)                                 [erratic alternation]
   score = min(CR / CR_line, ALT / ALT_line); CR_line, ALT_line = the least of TDOC 2020-03-19 / MELI 2018-09-17 / RRC 2018-11-12
          (so each of the three scores >= 1 by construction).
 Scoreable = >= 80 finite bars to D (shorter listed apart, unscored).
 THRESHOLD RULE: t = the max score over the PROTECTED set (14 ok/good graded charts; the six tightening buys AMC 2021-02-22,
   W 2020-04-07, APT 2020-02-21, PENN 2020-03-26, MRNA 2020-04-02, NVAX 2020-04-03; the 56 listed High; the 26 big winners —
   every candidate night of a multi-session window counts, i.e. a protected buy is flagged if ANY of its nights is);
   flag = score > t. If any of TDOC / MELI / RRC is not > t -> "none exists".
 Conditional grades and non-chop 'no' grades are reported apart (neither must-flag nor must-pass).
 One revision allowed; both versions recorded in this file and the .out.
 REVISION v2 (written after v1, before v2 was computed): v1 found NONE EXISTS — MELI's last 10 sessions are QUIET (daily ranges
   3-5%, its 10-session box half the prior one), so MELI scores as contracting on a 10-vs-15 horizon and sits below ok charts
   (ADMS, TTD, ZS, CRWD, TELL). His MELI read ("super choppy, huge wide ranges") must be the whole base, not the last weeks.
   v2 = same structure, base-length horizon: CR = mean TR last 20 / mean TR sessions -60..-21; ALT over the last 40 sessions.
   Same lines (least of the three), same threshold rule. Post-hoc after seeing v1: disclosed as such.
   python3 .../01_vol.py > .../01_vol.out 2> .../01_vol.err
"""
import os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
WL = os.path.join(REPO, "scripts/probes/_717_wideloose_1114")
CAP = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
MEASF = "/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"
WINF = "/Users/alvinfung/apollo_data/bv1_shape_1114/fires_windows.npy"
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
VERSION = sys.argv[1] if len(sys.argv) > 1 else "v1"
# v1 = PREREG above. v2 (the one revision) is defined in VERSIONS and recorded with its reason in the .out header.
VERSIONS = {"v1": dict(rec=10, prior=15, alt=15), "v2": dict(rec=20, prior=40, alt=40)}
P = VERSIONS[VERSION]
CHART = 80
ANCH = [("TDOC", "2020-03-19"), ("MELI", "2018-09-17"), ("RRC", "2018-11-12")]
CHOP = ANCH + [("TWTR", "2018-02-07"), ("SWAV", "2021-08-17"), ("CDE", "2019-11-05"), ("DVAX", "2021-11-17"), ("FLGT", "2021-12-10")]
SIX = [("AMC", "2021-02-22"), ("W", "2020-04-07"), ("APT", "2020-02-21"), ("PENN", "2020-03-26"), ("MRNA", "2020-04-02"), ("NVAX", "2020-04-03")]


def measures(W):
    W = np.asarray(W, np.float64)[:, :, -CHART:]
    h, l, c = np.log(W[:, 1]), np.log(W[:, 2]), np.log(W[:, 3])
    tr = np.fmax(h[:, 1:], c[:, :-1]) - np.fmin(l[:, 1:], c[:, :-1])
    rec, pri, alt = P["rec"], P["prior"], P["alt"]
    cr = np.nanmean(tr[:, -rec:], 1) / np.nanmean(tr[:, -rec - pri:-rec], 1)
    d = np.diff(c, axis=1)[:, -(alt + 1):]
    flip = np.sign(d[:, 1:]) * np.sign(d[:, :-1]) < 0
    altv = np.nansum(np.where(flip, np.fmin(np.abs(d[:, 1:]), np.abs(d[:, :-1])), 0.0), 1)
    ch = np.nanmax(h, 1) - np.nanmin(l, 1)
    nb = np.isfinite(c).sum(1)
    return pd.DataFrame({"CR": cr, "ALT": altv / ch, "nb": nb})


# ── graded (48) and Qullamaggie buys
gr = pd.read_csv(os.path.join(WL, "graded_rows.tsv"), sep="\t")
mg = measures(np.load(os.path.join(WL, "graded_windows200.npy"))[gr.wid.to_numpy()]); gr = pd.concat([gr, mg], axis=1)
qm = pd.read_csv(os.path.join(WL, "03_qm_scored.tsv"), sep="\t", dtype={"eid": str}, keep_default_na=False, na_values=[""])
mq = measures(np.load(os.path.join(WL, "qm_windows200.npy"))[qm.wid.to_numpy()]); qm = pd.concat([qm.drop(columns=["score"]), mq], axis=1)
key = lambda df, t, d, col: df[(df.ticker == t) & (df[col] == d)]
ia = [key(gr, t, d, "D").index[0] for t, d in ANCH]
CRL, ALTL = gr.loc[ia, "CR"].min(), gr.loc[ia, "ALT"].min()
sc = lambda x: np.minimum(x.CR / CRL, x.ALT / ALTL).where(x.nb >= CHART)
gr["score"], qm["score"] = sc(gr), sc(qm)
print(f"VERSION {VERSION} {P}; lines: CR >= {CRL:.3f}, ALT >= {ALTL:.4f} (least of TDOC/MELI/RRC)")

# ── fires (lib.load()'s frame, rebuilt here) + bridge
df = pd.read_parquet(CAP); cal = open(CAP + ".cal.txt").read().split(); assert cal[-1] < "2025-01-01"
nights = df.ci.nunique()
f = df[df.fire].join(pd.read_parquet(MEASF), rsuffix="_m"); assert (f.base_len == f.base_len_m).all()
WF = np.load(WINF, mmap_mode="r"); assert len(WF) == len(f)
f["Dd"] = [cal[c] for c in f.ci]; assert f.Dd.max() <= "2022-03-31"
parts = [measures(WF[i:i + 20000]) for i in range(0, len(f), 20000)]
mf = pd.concat(parts, ignore_index=True); mf.index = f.index; f = f.join(mf); f["score"] = sc(f)
for t, d in ANCH + [("OKTA", "2018-03-26"), ("CRWD", "2020-10-16")]:
    x = key(f, t, d, "Dd"); y = key(gr, t, d, "D")
    assert len(x) == 1 and abs(x.CR.iloc[0] - y.CR.iloc[0]) < 1e-3 and abs(x.ALT.iloc[0] - y.ALT.iloc[0]) < 1e-3, (t, x[["CR", "ALT"]], y[["CR", "ALT"]])
print("bridge: fire windows reproduce the graded CR/ALT for TDOC MELI RRC OKTA CRWD (float32 tol 1e-3): ok")

# ── protected set + threshold
okg = gr[gr.grade.isin(["ok", "good"])]
six = pd.concat([key(qm, t, e, "E") for t, e in SIX]); assert len(six) == 6, six
hi = qm[qm.high_listed == 1]; bw = qm[qm.big == 1]
print(f"protected scored: ok/good {okg.score.notna().sum()}/{len(okg)}; six {six.score.notna().sum()}/6; listed High {hi[hi.score.notna()].key.nunique()}/{hi.key.nunique()} (rows {len(hi)}); big {bw[bw.score.notna()].key.nunique()}/{bw.key.nunique()}")
prot = pd.concat([okg.assign(src="ok/good", key=okg.ticker + " " + okg.D)[["src", "key", "ticker", "score", "CR", "ALT"]],
                  six.assign(src="six")[["src", "key", "ticker", "E", "score", "CR", "ALT"]],
                  hi.assign(src="High")[["src", "key", "ticker", "E", "score", "CR", "ALT"]],
                  bw.assign(src="big")[["src", "key", "ticker", "E", "score", "CR", "ALT"]]])
print("\ntop protected scores:"); print(prot.sort_values("score", ascending=False).head(10).to_string(index=False, float_format="%.3f"))
t = float(prot.score.max())
print("\nall graded (score desc):"); print(gr.sort_values("score", ascending=False)[["ticker", "D", "grade", "CR", "ALT", "score"]].to_string(index=False, float_format="%.3f"))
anch_s = gr.loc[ia, "score"]
exists = bool((anch_s > t).all())
print(f"\nTHRESHOLD t = max protected score = {t:.4f}; flag = score > t; anchors {dict(zip([a[0] for a in ANCH], anch_s.round(3)))} -> {'EXISTS' if exists else 'NONE EXISTS (an anchor is not above t)'}")
for t_use, lab in ((t, "rule threshold"),) + (((1.0, "the anchor line 1.0 (for reference, breaks a must-pass)"),) if not exists else ()):
    fl = lambda x: x.score > t_use
    print(f"\n==== SCOREBOARD @ {lab}: t = {t_use:.4f} ====")
    cg = gr.set_index(gr.ticker + " " + gr.D)
    chopk = [a + " " + b for a, b in CHOP]
    print(f"def-no (chop) flagged {int(fl(cg.loc[chopk]).sum())}/{len(chopk)}: " + ", ".join(f"{k}{'*' if fl(cg.loc[[k]]).iloc[0] else ''} ({cg.loc[k, 'score']:.2f})" for k in chopk) + "  (* = flagged)")
    print(f"ok/good flagged: {cg[cg.grade.isin(['ok','good']) & fl(cg)].index.tolist()}")
    print(f"conditional flagged: {cg[(cg.grade == 'conditional') & fl(cg)].index.tolist()}; other 'no' flagged: {cg[(cg.grade == 'no') & fl(cg) & ~cg.index.isin(chopk)].index.tolist()}")
    print(f"six tightening flagged: {six[fl(six)].ticker.tolist()}  scores {dict(zip(six.ticker, six.score.round(2)))}")
    S = qm[qm.score.notna()]
    any_flag = S.groupby("key").apply(lambda g: bool(fl(g).any()))
    meta = S.groupby("key").agg(ticker=("ticker", "first"), E=("E", "first"), tier=("tier", "first"), big=("big", "max"), hl=("high_listed", "max"), fixed=("fixed_day", "max"))
    meta["flag"] = any_flag
    eA = meta[meta.E <= "2022-03-31"]
    print(f"Qullamaggie buys flagged (any night): {int(meta.flag.sum())} of {len(meta)} scoreable (>= {CHART} bars; all dates to 2023-12); era-A {int(eA.flag.sum())} of {len(eA)}; fixed-day only {int(meta[meta.fixed == 1].flag.sum())} of {int((meta.fixed == 1).sum())}")
    print(f"  tier-High flagged {int(meta[(meta.tier == 'High')].flag.sum())} of {int((meta.tier == 'High').sum())}; listed High {int(meta[meta.hl == 1].flag.sum())}/56; big {int(meta[meta.big == 1].flag.sum())}/26")
    print("  flagged High/big:", meta[meta.flag & ((meta.tier == "High") | (meta.big == 1) | (meta.hl == 1))].to_dict("records"))
    print("  flagged buys:", ", ".join(f"{r.ticker} {r.E} ({r.tier})" for r in meta[meta.flag].sort_values("E").itertuples()))
    pool = f[~((f.u50 < -0.03) & (f.s50_chg10 < 0))]
    for nm, x in (("all fires", f), ("pool after 1d", pool)):
        b = x[fl(x)]
        print(f"  {nm}: {len(x) / nights:.1f} a day -> removes {len(b) / nights:.2f} a day ({len(b):,} of {len(x):,} = {len(b) / len(x):.1%}); unscored (<{CHART} bars) {int(x.score.isna().sum()):,}")
