#!/usr/bin/env python3
"""#717 'the range does not contract' check, time-slice (thirds) angle (2026-11-14; offline, $0, ERA A; research, no rule changed).

PREREG — written BEFORE any result below was computed. Nothing here is tuned after the run except the one allowed revision,
which (if used) is recorded as REVISION 1 below with the first version's result kept in 01_thirds_v0.out.

 His rule (operator_shared_notes 2026-11-14): wide is NOT the defect; the defect is a range that does NOT CONTRACT into the
 buy (stays wide / widens, erratic two-way swings). So the defect = LOOSE  AND  NOT CONTRACTING (a conjunction: a tight flat
 base has a late/early ratio ~1 and must not be flagged for it).

 LOOSE gate (frozen, not refit here): wl.py's wide measure box20_chart = high-low box of the last 20 sessions / height of the
   189-session chart (log), >= WIDE_MIN = the least of TDOC / MELI / RRC (= TDOC). Needs >= 60 bars (wl.MIN_BARS).
   Known cost: TWTR / CDE / DVAX / SWAV / FLGT may sit under this gate and be unflaggable — acceptable, the bar is the three.
 NOT-CONTRACTING ratio R (log prices, bars to the night before the buy / the list night; index -1 = that night):
   split the last 3k sessions into thirds (oldest, middle, latest), each k sessions;
   R = metric(latest third) / max(metric(oldest third), metric(middle third)). R < 1 = the latest slice is smaller (contracting).
   Family (exactly four, no others):
     V1 box21 : k=7,  metric = max(high) - min(low) of the slice
     V2 box30 : k=10, same
     V3 tr21  : k=7,  metric = mean true range of the slice
     V4 tr30  : k=10, same
   A slice with any missing bar -> not scored (NaN), never a silent pass; such rows are counted.
 SELECTION (graded 48 charts ONLY, before any Qullamaggie buy or fire is scored): for each variant, t_g = max R over gated
   ok/good graded charts (0 if none gated); count of the 8 chop rejects (TDOC MELI RRC TWTR SWAV CDE DVAX FLGT) gated with
   R > t_g, all of TDOC/MELI/RRC required; tie-break larger min(R of the 3) / t_g; then V1..V4 order.
 THRESHOLD (set by the must-pass set only, never fitted to the def-no charts): t = max R over every GATED must-pass row:
   ok/good graded charts; the six tightening buys (ticker + buy day: AMC 2021-02-22, W 2020-04-07, APT 2020-02-21,
   PENN 2020-03-26, MRNA 2020-04-02, NVAX 2020-04-03); every candidate row of the 56 listed High and the 26 big winners.
   Flagged iff gated AND R > t (strict). passes_bar = TDOC, MELI, RRC all flagged. Margin = min R(3 def-no) / t reported.
 POPULATIONS: Qullamaggie buys = all 972 rows of qm_rows.tsv (all eras in that capture; era-A subset also printed);
   a multi-session buy is flagged if ANY candidate night is flagged; scoreable = gate + R defined; unscoreable High / big
   are counted (an unscored row is not a pass). Conditional grades, VIR, LAC: reported, constrain nothing.
 FIRES: era-A fires as 03_score.py loads them; R from fires_windows.npy (80 bars, float32; alignment asserted on the last
   close), gate from fires_wl.parquet (the 189-bar box20_chart). Bridge: TDOC/MELI/RRC fire rows reproduce graded R (1e-4)
   and gate. Removed per day reported against ALL fires and against the pool after the 1d check.

    python3 scripts/probes/_717_contract_1114/thirds/01_thirds.py > scripts/probes/_717_contract_1114/thirds/01_thirds_v0.out
    python3 scripts/probes/_717_contract_1114/thirds/01_thirds.py --rev1 > scripts/probes/_717_contract_1114/thirds/01_thirds_rev1.out

 VERSION 0 RESULT (01_thirds_v0.out): selected V3_tr21; threshold set by PENN 2020-03-26 (R 1.93: its latest third IS the
   rebound, the widest slice) -> 0 of 3 def-no flagged; MELI's latest third is NARROWER than its earlier thirds on all four
   variants (box21 0.38). FAIL.
 REVISION 1 (the one allowed; written before its result but AFTER the v0 result and a per-bar TR/close printout of
   MELI TDOC RRC CAR ATYR PENN W AMC — disclosed; run with --rev1 > 01_thirds_rev1.out): his PENN words are
   "rebound, not wide loose range up and down" -> the slice metric becomes TWO-WAY travel, so a one-way rebound is small:
     V5 churn21 : k=7, metric = min(sum of up close-to-close moves, sum of down moves) inside the slice
   R = churn(latest) / max(churn(oldest), churn(middle)). Same gate, same must-pass threshold rule, same scoreboard; V5 only
   (no selection step: the single registered variant).
 RESULT REV 1: line 3.7933 set by PENN; 0 of 3 def-no. FAIL. Caveat: churn ratio explodes on near-zero earlier slices
   (LAZR 41, OPTT 12), so its flagged buys / fires are partly a small-denominator artifact. Removal rates are VOID (the
   line flags no def-no chart). Not a PENN knife-edge: flagging RRC/MELI also needs W (six) and TLRY 2021-02-02 (High) flagged.
"""
import importlib.util, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
WLD = os.path.join(REPO, "scripts/probes/_717_wideloose_1114"); sys.path.insert(0, WLD)
import wl  # noqa: E402
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
ff = lambda x: f"{x:.3f}"

VARIANTS = {"V1_box21": (7, "box"), "V2_box30": (10, "box"), "V3_tr21": (7, "tr"), "V4_tr30": (10, "tr")}
if "--rev1" in sys.argv:   # was env REV=1 (the one revision; #681 bans hand-rolled env booleans)
    VARIANTS = {"V5_churn21": (7, "churn")}
REJ3 = ["TDOC", "MELI", "RRC"]; REJ8 = REJ3 + ["TWTR", "SWAV", "CDE", "DVAX", "FLGT"]
SIX = [("AMC", "2021-02-22"), ("W", "2020-04-07"), ("APT", "2020-02-21"), ("PENN", "2020-03-26"), ("MRNA", "2020-04-02"), ("NVAX", "2020-04-03")]


def ratios(W):
    """W: (n, >=4, T) o/h/l/c -> DataFrame of R for each variant (NaN if any bar in the 3k+1 tail is missing)."""
    W = np.asarray(W, np.float64)
    h, l, c = np.log(W[:, 1]), np.log(W[:, 2]), np.log(W[:, 3])
    tr = np.fmax(h[:, 1:], c[:, :-1]) - np.fmin(l[:, 1:], c[:, :-1])       # tr[:, j] is the true range of bar j+1
    out = {}
    for name, (k, kind) in VARIANTS.items():
        n = 3 * k
        ok = np.isfinite(c[:, -(n + 1):]).all(1) & np.isfinite(h[:, -n:]).all(1) & np.isfinite(l[:, -n:]).all(1)
        m = []
        for s in range(3):
            a, b = -n + s * k, -n + (s + 1) * k
            sl = slice(a, b if b < 0 else None)
            if kind == "box":
                m.append(h[:, sl].max(1) - l[:, sl].min(1))
            elif kind == "tr":
                m.append(tr[:, sl].mean(1))
            else:
                d = np.diff(c[:, -(n + 1):], axis=1)[:, s * k:(s + 1) * k]       # the k close-to-close moves ending inside the slice
                m.append(np.fmin(np.clip(d, 0, None).sum(1), np.clip(-d, 0, None).sum(1)))
        r = m[2] / np.fmax(m[0], m[1])
        out[name] = np.where(ok, r, np.nan)
    return pd.DataFrame(out)


def gate_of(box20_chart, nbars, wide_min):
    return (box20_chart >= wide_min) & (nbars >= wl.MIN_BARS)


# ── graded 48
gr = pd.read_csv(os.path.join(WLD, "graded_rows.tsv"), sep="\t")
WG = np.load(os.path.join(WLD, "graded_windows200.npy"))[gr.wid.to_numpy()]
cg = wl.core(WG)
d3 = gr.ticker.isin(REJ3).to_numpy()
WIDE_MIN = float(cg.box20_chart[d3].min())
gr = pd.concat([gr, cg.reset_index(drop=True), ratios(WG)], axis=1)
gr["gate"] = gate_of(gr.box20_chart, gr.nbars, WIDE_MIN)
gr["okgood"] = gr.grade.isin(["ok", "good"])
gr["rej8"] = gr.ticker.isin(REJ8) & (gr.grade == "no")
print(f"LOOSE gate: box20_chart >= {WIDE_MIN:.4f} (least of TDOC/MELI/RRC, wl.py frozen line)")
print(f"graded gated: {int(gr.gate.sum())} of 48 (ok/good gated {int((gr.gate & gr.okgood).sum())} of {int(gr.okgood.sum())}); chop rejects gated: "
      + ", ".join(t for t in REJ8 if gr[(gr.ticker == t) & (gr.grade == 'no')].gate.any()))
print("\n== GRADED 48 (sorted by grade, box20_chart) ==")
print(gr[["ticker", "D", "grade", "box20_chart", "gate"] + list(VARIANTS)].sort_values(["grade", "box20_chart"], ascending=[True, False]).to_string(index=False, float_format=ff))

# ── selection on the graded charts only
sel = []
for v in VARIANTS:
    tg = float(gr.loc[gr.gate & gr.okgood, v].max()) if (gr.gate & gr.okgood).any() else 0.0
    tg = 0.0 if np.isnan(tg) else tg
    fl = gr.gate & (gr[v] > tg)
    n8 = int((fl & gr.rej8).sum()); all3 = all(fl[(gr.ticker == t) & (gr.grade == "no")].any() for t in REJ3)
    m3 = float(gr.loc[d3, v].min())
    sel.append(dict(variant=v, t_graded=tg, rej8_flagged=n8, all3=all3, min_R_3=m3, margin=m3 / tg if tg > 0 else np.inf,
                    flagged=",".join(gr.ticker[fl & gr.rej8])))
sel = pd.DataFrame(sel)
print("\n== SELECTION (graded only) ==\n" + sel.to_string(index=False, float_format=ff))
cand = sel[sel.all3] if sel.all3.any() else sel
cand = cand.sort_values(["rej8_flagged", "margin"], ascending=[False, False], kind="stable")
V = cand.variant.iloc[0]
print(f"SELECTED: {V}")

# ── Qullamaggie buys
qm = pd.read_csv(os.path.join(WLD, "qm_rows.tsv"), sep="\t", dtype={"eid": str}, keep_default_na=False, na_values=[""])
WQ = np.load(os.path.join(WLD, "qm_windows200.npy"))[qm.wid.to_numpy()]
qm = pd.concat([qm.drop(columns=["nbars"]), wl.core(WQ).reset_index(drop=True), ratios(WQ)], axis=1)
qm["key"] = qm.set + qm.eid
qm["gate"] = gate_of(qm.box20_chart, qm.nbars, WIDE_MIN)
hi = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_context_1114/high_rows.tsv"), sep="\t", dtype={"eid": str})
HIK = set((hi.set + hi.eid)[hi.ok == 1]); BIGK = set(qm.key[qm.big == 1])
assert len(HIK) == 56 and len(BIGK) == 26, (len(HIK), len(BIGK))
qm["high"] = qm.key.isin(HIK); qm["bigk"] = qm.key.isin(BIGK)
qm["six"] = [(t, e) in SIX for t, e in zip(qm.ticker, qm.E)]
assert qm.six.sum() == 6, qm[qm.six]
qm["scoreable"] = qm.nbars >= wl.MIN_BARS
for v in VARIANTS:
    qm["scoreable_" + v] = qm.scoreable & qm[v].notna()

# ── threshold from the must-pass set only
mp_g = gr[gr.gate & gr.okgood]; mp_q = qm[qm.gate & (qm.six | qm.high | qm.bigk)]
cands = pd.concat([mp_g.assign(src="graded ok/good", key=mp_g.ticker)[["src", "ticker", "D", "box20_chart", V]],
                   mp_q.assign(src=np.where(mp_q.six, "six", np.where(mp_q.high, "High", "big")))[["src", "ticker", "E", "box20_chart", V]].rename(columns={"E": "D"})])
print(f"\n== MUST-PASS rows inside the LOOSE gate ({len(cands)}), by {V} ==")
print(cands.sort_values(V, ascending=False).to_string(index=False, float_format=ff))
T = float(np.nanmax(cands[V])) if len(cands) else 0.0
print(f"THRESHOLD t = {T:.4f} (flag iff gated AND {V} > t); unscored must-pass inside gate: {int(cands[V].isna().sum())}")

gr["flag"] = gr.gate & (gr[V] > T); qm["flag"] = qm.gate & (qm[V] > T)
m3 = gr.loc[d3, V]
print(f"\n== SCOREBOARD ({V}, t = {T:.4f}) ==")
print("def-no 3: " + ", ".join(f"{t} {'FLAGGED' if gr.flag[(gr.ticker == t)].any() else 'not'} (R {float(gr.loc[gr.ticker == t, V].iloc[0]):.3f}, gate {bool(gr.gate[gr.ticker == t].iloc[0])})" for t in REJ3)
      + f"; margin min(R 3)/t = {float(m3.min()) / T if T > 0 else np.inf:.3f}")
r8 = gr[gr.rej8]
print(f"chop rejects flagged {int(r8.flag.sum())}/8: " + ", ".join(f"{r.ticker}{'*' if r.flag else ''}(R {r[V]:.2f}, gate {r.gate})" for _, r in r8.iterrows()))
print(f"other 'no' flagged: {list(gr.ticker[gr.flag & (gr.grade == 'no') & ~gr.rej8])}; conditional flagged: {list(gr.ticker[gr.flag & (gr.grade == 'conditional')])}")
print(f"ok/good flagged: {list(gr.ticker[gr.flag & gr.okgood])}")
print(f"six tightening buys flagged: {list(qm.ticker[qm.flag & qm.six])}; their R: " + ", ".join(f"{r.ticker} {r[V]:.2f}(gate {r.gate})" for _, r in qm[qm.six].iterrows()))
for lab, sub in (("ALL rows in capture", qm), ("era A (E <= 2022-03-31)", qm[qm.E <= "2022-03-31"])):
    ks = sub[sub["scoreable_" + V]].key.unique()
    fk = sub[sub.flag].key.unique()
    print(f"Qullamaggie buys [{lab}]: flagged {len(fk)} of {len(ks)} scoreable buys ({sub.key.nunique()} buys); "
          f"High flagged {len(set(fk) & HIK)} (scoreable {len(set(ks) & HIK)} of 56); big flagged {len(set(fk) & BIGK)} (scoreable {len(set(ks) & BIGK)} of 26)")
fl = qm[qm.flag].drop_duplicates("key")
print("flagged Qullamaggie buys:\n" + fl[["set", "eid", "ticker", "E", "tier", "reason", "big", "high", "how", "nbars", "box20_chart", V]].to_string(index=False, float_format=ff))
print("VIR / LAC rows: " + "; ".join(f"{r.ticker} {r.E} R {r[V]:.2f} gate {r.gate} flag {r.flag}" for _, r in qm[qm.ticker.isin(["VIR", "LAC"])].iterrows() if r.gate))
print("\nall-variant view at each variant's own must-pass line (descriptive):")
for v in VARIANTS:
    tv = float(np.nanmax(pd.concat([mp_g[v], mp_q[v]])))
    print(f"  {v}: t {tv:.3f}; def-no3 R " + ", ".join(f"{t} {float(gr.loc[gr.ticker == t, v].iloc[0]):.3f}" for t in REJ3)
          + f"; max-must-pass row: " + ", ".join(f"{r.ticker} {r.D}" for _, r in cands.assign(_v=pd.concat([mp_g[v], mp_q[v]]).values).nlargest(2, "_v").iterrows()))

# ── era-A fires
spec = importlib.util.spec_from_file_location("m", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
df, cal, big = M.load()
f = df[df.fire].join(pd.read_parquet("/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"), rsuffix="_m")
o = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_wideloose_1114/fires_wl.parquet"); assert (o.index == f.index).all()
f = f.join(o)
WF = np.load("/Users/alvinfung/apollo_data/bv1_shape_1114/fires_windows.npy", mmap_mode="r"); assert len(WF) == len(f)
last = np.asarray(WF[:, 3, -1], np.float64)
assert np.allclose(last, f.close.to_numpy(), rtol=1e-5), "window / fire misalignment"
RF = pd.concat([ratios(WF[i:i + 20000]) for i in range(0, len(WF), 20000)], ignore_index=True); RF.index = f.index
f = f.join(RF)
f["Dd"] = [cal[c].isoformat() for c in f.ci]; assert f.Dd.max() <= "2022-03-31"
f["gate"] = gate_of(f.box20_chart, f.nbars, WIDE_MIN); f["flag"] = f.gate & (f[V] > T)
for t_, d_ in (("TDOC", "2020-03-19"), ("MELI", "2018-09-17"), ("RRC", "2018-11-12")):
    x = f[(f.ticker == t_) & (f.Dd == d_)].iloc[0]; y = gr[gr.ticker == t_].iloc[0]
    assert abs(x[V] - y[V]) < 1e-4 and x.gate == y.gate and abs(x.box20_chart - y.box20_chart) < 1e-9, (t_, x[V], y[V])
print("\nbridge: fire path reproduces graded R + gate for TDOC/MELI/RRC: ok")
nights = df.ci.nunique()
pool = f[~((f.u50 < -0.03) & (f.s50_chg10 < 0))]
print(f"== ERA-A FIRES ({nights} list nights) ==  R unscored (missing bars): {int(f[V].isna().sum()):,}")
for nm, x in (("all fires", f), ("pool after 1d", pool)):
    b = x[x.flag]
    print(f"  {nm}: {len(x):,} = {len(x) / nights:.1f}/day; flagged {len(b):,} = {len(b) / nights:.2f}/day removed ({len(b) / len(x):.1%}); gated {int(x.gate.sum()):,}")
