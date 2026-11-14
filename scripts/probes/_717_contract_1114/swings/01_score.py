#!/usr/bin/env python3
"""#717 swing structure: does the base's swing size SHRINK into the buy? (2026-11-14; offline, $0, ERA A; research only.)

PREREG — written BEFORE any labelled chart, Qullamaggie buy or fire was scored (sw.py was only run on synthetic series).
 V1 DEFINITION (sw.py): last 60 sessions to the night before (log prices). Swing points = fractal pivots (the highest high /
  lowest low of the 3 bars either side), made alternating (two highs in a row keep the higher, two lows the lower). Legs =
  sizes between consecutive swing points; the final leg = from the last confirmed swing point to the extreme of the bars
  since it (a tight right side is a small final swing, not a missing one). late = mean of the last 2 legs, early = mean of
  the 2 legs before them. S = late / early (>= 1 = the swings are NOT shrinking). S = 0 (not flagged) when the late swings
  are under 10% of the chart's height (189-session high-low; too small to be wide chop) or the base has < 4 legs.
  Pivot scale = the bars themselves (3 bars either side), no daily-range sizing at the last night (it shrinks with the
  tightening being measured). Lows-holding is a REPORTED column (lowchg = last swing low - the one before, / chart), not in S.
 THRESHOLD RULE: T = the highest S among the MUST-PASS set = every ok/good graded chart (14), the six buys he called
  tightening (d1255 AMC, d468 W, d400 APT, w448 PENN, w458 MRNA, d460 NVAX), and every scoreable Qullamaggie row (>= 60 bars)
  that is tier High OR in the listed 56 OR a big winner — fixed-day rows and EVERY candidate night of multi-session windows.
  Flag = S > T. "None exists" if no def-no chart is above T. Margin = min(TDOC, MELI, RRC) / T.
 SCOREBOARD: def-no flagged of 8 (TDOC, MELI, RRC first); ok/good flagged; six flagged; Qullamaggie fixed-day full-chart
  headline (573) flagged by tier + big; multi-session any-night apart; era-A fires per day removed, all fires (118.5/day)
  and the pool after 1d (103.1/day), the population named.
 Fires: S from the 80-bar fire windows with the 189-session chart height taken from the wide-loose card's captured
  box20_chart (chart = box20 / box20_chart); bridge-asserted on TDOC / MELI / RRC against the graded windows.
 ONE REVISION allowed; both versions recorded (01_score_v1.out, 01_score_v2.out).

PREREG V2 — the one revision, written AFTER V1's results (0 of 8 flagged; T set by PENN 6.71, BLDP 3.91 / LRN 3.83 block
 too: a one-way pole read as "not shrinking") and AFTER the leg diagnostic 02_legs_diag.out, i.e. FITTED ON THOSE PRINTED
 CHARTS (in-sample; the ~100 protected Qullamaggie rows not printed there are the out-of-sample part). sw.score_rows_v2:
 same pivots / legs / 60 sessions. B = the biggest CONFIRMED leg. After B, a pair of consecutive legs (the running final leg
 may be the 2nd member) whose smaller leg is bigger than some leg already seen since B = the swings shrank then widened
 again, both ways. S = the largest such smaller-of-pair / B (0 = the swings only decay after the big move). No size gate.
 Same threshold rule, same scoreboard. Run ONCE; if a protected row tops the lowest of TDOC / MELI / RRC, the answer is
 "no threshold exists" and the blockers are named — no further iteration.
    python3 scripts/probes/_717_contract_1114/swings/01_score.py > scripts/probes/_717_contract_1114/swings/01_score.out
"""
import importlib.util, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
import sw
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
WLD = os.path.join(REPO, "scripts/probes/_717_wideloose_1114")
VER = os.environ.get("VER", "v1")
FS = os.path.join(HERE, "fires_swing_" + VER + ".parquet")
DEFNO = ["TDOC", "MELI", "RRC", "TWTR", "SWAV", "CDE", "DVAX", "FLGT"]
SIX = ["d1255", "d468", "d400", "w448", "w458", "d460"]
print(f"VERSION {VER}: LOOK {sw.LOOK} K {sw.K} GATE {sw.GATE}")

# graded
gr = pd.read_csv(os.path.join(WLD, "graded_rows.tsv"), sep="\t")
WG = np.load(os.path.join(WLD, "graded_windows200.npy"))[gr.wid.to_numpy()]
SCORE = sw.score_rows_v2 if VER == "v2" else sw.score_rows
for k, v in SCORE(WG).items():
    gr[k] = v
# Qullamaggie
qm = pd.read_csv(os.path.join(WLD, "qm_rows.tsv"), sep="\t", dtype={"eid": str}, keep_default_na=False, na_values=[""])
WQ = np.load(os.path.join(WLD, "qm_windows200.npy"))[qm.wid.to_numpy()]
for k, v in SCORE(WQ).items():
    qm[k] = v
qm["key"] = qm.set.str[0] + qm.eid
hi = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_context_1114/high_rows.tsv"), sep="\t", dtype={"eid": str})
qm["listed56"] = qm.key.isin(set((hi.set.str[0] + hi.eid)[hi.ok == 1])).astype(int)
qm["fixed"] = qm.how.isin(["dated", "one_session_window"]).astype(int)
qm["six"] = qm.key.isin(SIX).astype(int)
assert qm[qm.six == 1].key.nunique() == 6 and (qm[qm.six == 1].fixed == 1).all()
qm["protect"] = ((qm.tier == "High") | (qm.listed56 == 1) | (qm.big == 1)).astype(int)
okg = gr[gr.grade.isin(["ok", "good"])]
sc_q = qm[qm.S.notna()]
print(f"graded: {len(gr)} (ok/good {len(okg)}, def-no {gr.ticker.isin(DEFNO).sum()}); qm rows {len(qm)}, scoreable (>= {sw.LOOK} bars) {len(sc_q)}")
print(f"protected keys: High tier {qm[qm.tier == 'High'].key.nunique()} (scoreable {sc_q[sc_q.tier == 'High'].key.nunique()}), listed56 {qm[qm.listed56 == 1].key.nunique()} (scoreable {sc_q[sc_q.listed56 == 1].key.nunique()}), big {qm[qm.big == 1].key.nunique()} (scoreable {sc_q[sc_q.big == 1].key.nunique()})")
mp = pd.concat([okg.assign(src="ok/good " + okg.ticker + " " + okg.D)[["src", "S"]],
                sc_q[(sc_q.six == 1) | (sc_q.protect == 1)].assign(src=lambda x: "qm " + x.key + " " + x.ticker + " " + x.E + " " + x.tier + np.where(x.big == 1, " BIG", "") + np.where(x.six == 1, " SIX", ""))[["src", "S"]]])
T = float(mp.S.max())
print(f"\nMUST-PASS set {len(mp)} rows; T = max S = {T:.4f}; the 8 highest:"); print(mp.sort_values("S", ascending=False).head(15).to_string(index=False))
cols = [c for c in ["ticker", "D", "grade", "S", "B", "late", "early", "late_chart", "nlegs", "lowchg"] if c in gr]
print("\nGRADED charts, S descending:"); print(gr.sort_values("S", ascending=False)[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
dn = gr[gr.ticker.isin(DEFNO)].set_index("ticker").loc[DEFNO]
fl = dn[dn.S > T]
print(f"\nDEF-NO flagged {len(fl)}/8: {', '.join(fl.index)}; margin min(TDOC,MELI,RRC)/T = {dn.loc[['TDOC','MELI','RRC']].S.min() / T:.3f}")
print(f"ok/good flagged: {list(okg[okg.S > T].ticker)} | all 'no' flagged: {list(gr[(gr.grade == 'no') & (gr.S > T)].ticker)} | conditional flagged: {list(gr[(gr.grade == 'conditional') & (gr.S > T)].ticker)}")
print("six:"); print(qm[qm.six == 1][[c for c in ["key", "ticker", "E", "S", "B", "late", "early", "late_chart", "nlegs", "lowchg"] if c in qm]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
H = qm[(qm.fixed == 1) & (qm.nbars >= 189)]
b = H[H.S > T]
print(f"\nQM headline (fixed day, full chart) {len(H)}: flagged {len(b)}; tier {b.tier.value_counts().to_dict()}; High {int((b.tier == 'High').sum())}, listed56 {int(b.listed56.sum())}, big {int(b.big.sum())}")
qc = [c for c in ["key", "ticker", "E", "tier", "big", "listed56", "S", "B", "late", "early", "late_chart", "nlegs"] if c in qm]
print(b.sort_values("S", ascending=False)[qc].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
mid = qm[(qm.fixed == 1) & (qm.nbars < 189) & qm.S.notna()]; print(f"short history fixed-day (60-188 bars) flagged {int((mid.S > T).sum())} of {len(mid)}")
mw = sc_q[sc_q.fixed == 0].groupby("key").S.agg(["min", "max"])
print(f"multi-session windows {len(mw)}: any night flagged {int((mw['max'] > T).sum())}, every night flagged {int((mw['min'] > T).sum())}")
print(f"all scoreable Qullamaggie buys (any row flagged): {sc_q[sc_q.S > T].key.nunique()} of {sc_q.key.nunique()}")

# fires
spec = importlib.util.spec_from_file_location("m", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
df, cal, big = M.load()
f = df[df.fire].join(pd.read_parquet("/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"), rsuffix="_m")
wlp = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_wideloose_1114/fires_wl.parquet"); assert (wlp.index == f.index).all()
f["Dd"] = [cal[c].isoformat() for c in f.ci]
assert f.Dd.max() <= "2022-03-31"
if not os.path.exists(FS):
    WF = np.load("/Users/alvinfung/apollo_data/bv1_shape_1114/fires_windows.npy", mmap_mode="r"); assert len(WF) == len(f)
    box20 = np.log(np.nanmax(WF[:, 1, -20:], 1).astype(float)) - np.log(np.nanmin(WF[:, 2, -20:], 1).astype(float))
    chart = box20 / wlp.box20_chart.to_numpy()
    o = pd.DataFrame(SCORE(WF, chart=chart), index=f.index); o.to_parquet(FS)
o = pd.read_parquet(FS); assert (o.index == f.index).all()
f = f.join(o[["S", "nlegs"]])
for t_ in ("TDOC", "MELI", "RRC"):
    d_ = gr[gr.ticker == t_].D.iloc[0]
    x = f[(f.ticker == t_) & (f.Dd == d_)].S.iloc[0]; y = gr[gr.ticker == t_].S.iloc[0]
    print(f"bridge {t_} {d_}: fires {x:.4f} graded {y:.4f}"); assert abs(x - y) < 1e-3 * max(1, abs(y)), (t_, x, y)
nights = df.ci.nunique()
pool = f[~((f.u50 < -0.03) & (f.s50_chg10 < 0))]
print(f"\nfires {len(f):,} / {nights} nights = {len(f) / nights:.1f} a day; pool after 1d {len(pool):,} = {len(pool) / nights:.1f} a day; S NaN (under {sw.LOOK} bars) {int(f.S.isna().sum())}")
tier = dict(zip(qm.key, qm.tier)); bigk = set(qm.key[qm.big == 1])
for nm, x in (("all fires", f), ("pool after 1d", pool)):
    bb = x[x.S > T]; ids = {i for l_ in bb.qm for i in l_}
    print(f"{nm}: removed {len(bb):,} = {len(bb) / nights:.2f} a day of {len(x) / nights:.1f} ({len(bb) / len(x):.1%}); Qullamaggie fired buys removed {len(ids)} (High {sum(tier.get(i) == 'High' for i in ids)}, big {len(ids & bigk)}): {','.join(sorted(ids))[:200]}")
