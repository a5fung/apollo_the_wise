"""#717 LOWER LINE (2026-11-14, from his markups: Qullamaggie's bases have RISING lows / converging lines; MELI = flat
wide box, TDOC = falling lows). Stated before running: over the last N sessions (N = 30 and 40, both reported) take the
confirmed swing lows (sw.pivots, 3 bars either side) plus the lowest low of the bars after the last confirmed pivot; fit a
line through them in log price; slope = change per 10 sessions as a fraction of the 189-session chart height.
flag = slope <= 0 (lower line flat or falling) AND V3 (the re-widening swing vs chart height) > W, W = the loosest line
that flags no must-pass row. Graded + Qullamaggie windows from _717_wideloose_1114. One run."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE); import sw, v3m
WLD = os.path.join(REPO, "scripts/probes/_717_wideloose_1114")
DEFNO = ["TDOC", "MELI", "RRC", "TWTR", "SWAV", "CDE", "DVAX", "FLGT"]
SIX = ["d1255", "d468", "d400", "w448", "w458", "d460"]

def lowslope(W, N):
    W = np.asarray(W, np.float64); out = np.full(len(W), np.nan)
    for r in range(len(W)):
        h, l = np.log(W[r, 1]), np.log(W[r, 2]); ok = np.isfinite(h) & np.isfinite(l)
        if ok.sum() < max(N, 60): continue
        hh, ll = h[ok], l[ok]; chart = hh[-sw.CHART:].max() - ll[-sw.CHART:].min()
        H, L = hh[-N:], ll[-N:]
        p = sw.pivots(H, L)
        pts = [(i, v) for i, v, t in p if t == -1]
        last = p[-1][0] if p else -1
        if last + 1 < N:
            j = last + 1 + int(np.argmin(L[last + 1:])); pts.append((j, L[j]))
        if len(pts) < 2: out[r] = 0.0; continue
        x = np.array([q[0] for q in pts], float); y = np.array([q[1] for q in pts])
        out[r] = np.polyfit(x, y, 1)[0] * 10 / chart
    return out

gr = pd.read_csv(os.path.join(WLD, "graded_rows.tsv"), sep="\t"); WG = np.load(os.path.join(WLD, "graded_windows200.npy"))[gr.wid.to_numpy()]
qm = pd.read_csv(os.path.join(WLD, "qm_rows.tsv"), sep="\t", dtype={"eid": str}, keep_default_na=False, na_values=[""]); WQ = np.load(os.path.join(WLD, "qm_windows200.npy"))[qm.wid.to_numpy()]
gr["V3"] = v3m.v3(WG); qm["V3"] = v3m.v3(WQ)
qm["key"] = qm.set.str[0] + qm.eid
hi = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_context_1114/high_rows.tsv"), sep="\t", dtype={"eid": str})
qm["listed56"] = qm.key.isin(set((hi.set.str[0] + hi.eid)[hi.ok == 1])).astype(int)
qm["six"] = qm.key.isin(SIX).astype(int)
qm["protect"] = ((qm.tier == "High") | (qm.listed56 == 1) | (qm.big == 1) | (qm.six == 1)).astype(int)
for N in (30, 40):
    gr["LS"] = lowslope(WG, N); qm["LS"] = lowslope(WQ, N)
    print(f"\n===== N = {N}")
    print(gr.sort_values("V3", ascending=False)[["ticker", "D", "grade", "V3", "LS"]].head(26).to_string(index=False, float_format=lambda v: f"{v:+.3f}"))
    for nm in ["FIRY", "BLDP", "VIR", "NXH", "NUE"]:
        print(qm[(qm.ticker == nm) & (qm.protect == 1)][["ticker", "E", "tier", "big", "V3", "LS"]].to_string(index=False, header=False, float_format=lambda v: f"{v:+.3f}"))
    okg = gr[gr.grade.isin(["ok", "good"])]
    mp = pd.concat([okg[["V3", "LS"]], qm[(qm.protect == 1) & qm.V3.notna()][["V3", "LS"]]])
    W = float(mp[mp.LS <= 0].V3.max())
    flag_g = gr[(gr.LS <= 0) & (gr.V3 > W)]
    sc = qm[qm.V3.notna()]; fq = sc[(sc.LS <= 0) & (sc.V3 > W)].drop_duplicates("key")
    print(f"W (loosest line flagging no must-pass with a flat/falling lower line) = {W:.3f}")
    print(f"graded flagged: {flag_g[['ticker','grade']].values.tolist()}")
    print(f"QM buys flagged {len(fq)} of {sc.key.nunique()}: tiers {fq.tier.value_counts().to_dict()}, big {int(fq.big.sum())}")
    print(fq.sort_values("V3", ascending=False)[["ticker", "E", "tier", "V3", "LS"]].head(15).to_string(index=False, float_format=lambda v: f"{v:+.3f}"))
