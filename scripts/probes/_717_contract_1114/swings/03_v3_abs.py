"""#717 swings V3 (2026-11-14, after his side-by-side of the V2 blockers VIR 2020-06-19 / NXH 2021-01-22 / NUE 2022-01-05):
V2 divides the re-widening swing by the base's biggest leg B, so a quiet base after a big pole (tiny wiggles) scores high.
V3 = the same re-widening swing (smaller leg of a pair that is bigger than an earlier post-B leg) measured against the
CHART HEIGHT (189-session log high-low), i.e. how big the erratic two-way swings are on the chart he reads. Pre-stated
before running: same threshold rule as V2 (T = max over the must-pass set; flagged when > T). One run."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE); import sw
WLD = os.path.join(REPO, "scripts/probes/_717_wideloose_1114")
DEFNO = ["TDOC", "MELI", "RRC", "TWTR", "SWAV", "CDE", "DVAX", "FLGT"]
SIX = ["d1255", "d468", "d400", "w448", "w458", "d460"]

def v3(W):
    W = np.asarray(W, np.float64); out = np.full(len(W), np.nan)
    for r in range(len(W)):
        h, l = np.log(W[r, 1]), np.log(W[r, 2]); ok = np.isfinite(h) & np.isfinite(l)
        if ok.sum() < sw.LOOK: continue
        hh, ll = h[ok], l[ok]; chart = hh[-sw.CHART:].max() - ll[-sw.CHART:].min()
        a, p = sw.legs(hh[-sw.LOOK:], ll[-sw.LOOK:])
        if len(a) < 2: out[r] = 0.0; continue
        b = int(np.argmax(a[:-1])); s = 0.0
        for j in range(b + 2, len(a) - 1):
            m = min(a[j], a[j + 1])
            if m > a[b + 1:j].min(): s = max(s, m)
        out[r] = s / chart
    return out

gr = pd.read_csv(os.path.join(WLD, "graded_rows.tsv"), sep="\t")
gr["S3"] = v3(np.load(os.path.join(WLD, "graded_windows200.npy"))[gr.wid.to_numpy()])
qm = pd.read_csv(os.path.join(WLD, "qm_rows.tsv"), sep="\t", dtype={"eid": str}, keep_default_na=False, na_values=[""])
qm["S3"] = v3(np.load(os.path.join(WLD, "qm_windows200.npy"))[qm.wid.to_numpy()])
qm["key"] = qm.set.str[0] + qm.eid
hi = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_context_1114/high_rows.tsv"), sep="\t", dtype={"eid": str})
qm["listed56"] = qm.key.isin(set((hi.set.str[0] + hi.eid)[hi.ok == 1])).astype(int)
qm["six"] = qm.key.isin(SIX).astype(int)
qm["protect"] = ((qm.tier == "High") | (qm.listed56 == 1) | (qm.big == 1) | (qm.six == 1)).astype(int)
okg = gr[gr.grade.isin(["ok", "good"])]
mp = pd.concat([okg.assign(src="ok " + okg.ticker + " " + okg.D)[["src", "S3"]],
                qm[(qm.protect == 1) & qm.S3.notna()].assign(src=lambda x: "qm " + x.ticker + " " + x.E + " " + x.tier + np.where(x.big == 1, " BIG", "") + np.where(x.six == 1, " SIX", ""))[["src", "S3"]]])
T = float(mp.S3.max())
print(f"T = {T:.4f}; must-pass top 10:"); print(mp.sort_values("S3", ascending=False).head(10).to_string(index=False))
print("\nGRADED, S3 descending:"); print(gr.sort_values("S3", ascending=False)[["ticker", "D", "grade", "S3"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
dn = gr[gr.ticker.isin(DEFNO)]
print(f"\nDEF-NO flagged {int((dn.S3 > T).sum())}/8: {list(dn[dn.S3 > T].ticker)}; ok/good flagged {list(okg[okg.S3 > T].ticker)}")
sc = qm[qm.S3.notna()]
b = sc[sc.S3 > T]
print(f"QM scoreable rows {len(sc)} ({sc.key.nunique()} buys); flagged buys {b.key.nunique()}: tiers {b.drop_duplicates('key').tier.value_counts().to_dict()}")
print(b.drop_duplicates('key').sort_values("S3", ascending=False)[["ticker", "E", "tier", "big", "S3"]].head(30).to_string(index=False, float_format=lambda v: f"{v:.3f}"))

# post-hoc line just above the next protected row once FIRY (Medium, big winner) is set aside — shown to him, not adopted
T2 = float(mp[~mp.src.str.contains("FIRY")].S3.max())
print(f"\nPOST-HOC: line without FIRY = {T2:.4f}")
print(f"graded flagged: {gr[gr.S3 > T2][['ticker','grade']].values.tolist()}")
b2 = sc[sc.S3 > T2].drop_duplicates("key")
print(f"QM buys flagged {len(b2)} of {sc.key.nunique()}: tiers {b2.tier.value_counts().to_dict()}, big {int(b2.big.sum())}")
print(qm[qm.ticker == "FIRY"][["ticker", "E", "tier", "big", "nbars", "S3"]].to_string(index=False))
