"""Current liquidity read (display only — his 11-22 ruling: the display may use 2025-26 prices; no outcome is read or judged).
Rules: docs/analysis/liquidity_composite_prereg_2026-11-22.md §12 (trend vote 20d vs 50d), §4.3 composite, run-2 kept legs."""
import pandas as pd, numpy as np
from pathlib import Path
D = Path.home() / "apollo_data/liquidity_current"
adj = pd.read_csv(D / "etf_daily_all.psv", sep="|", parse_dates=["date"]).pivot(index="date", columns="ticker", values="c")
raw = pd.read_csv(D / "etf_daily_raw.psv", sep="|", parse_dates=["date"]).pivot(index="date", columns="ticker", values="c")
idx = adj.index
def fred(i):
    s = pd.read_csv(D / f"{i}.csv", parse_dates=["observation_date"]).set_index("observation_date").iloc[:, 0]
    return pd.to_numeric(s, errors="coerce").reindex(idx.union(s.index)).ffill().reindex(idx)
X = pd.DataFrame(index=idx)
X["C3 Baa spread"] = fred("BAA10Y")
X["F1 net liquidity"] = -(fred("WALCL") - fred("WTREGEN") - fred("RRPONTSYD") * 1000)
X["F2 funds rate"] = fred("DFF")
X["R1 10y real yield"] = fred("DFII10")
X["R2 2y yield"] = fred("DGS2")
X["D1 dollar (UUP)"] = adj["UUP"]
X["M1 gold/silver"] = adj["GLD"] / adj["SLV"]
X["M2 copper/gold"] = -(adj["CPER"] / adj["GLD"])
X["K1 small/large"] = -(adj["IWM"] / adj["SPY"])
X["K5 spec growth"] = -(adj["ARKK"] / adj["QQQ"])
CH = {"credit": ["C3 Baa spread"], "fed": ["F1 net liquidity", "F2 funds rate"], "rates": ["R1 10y real yield", "R2 2y yield"],
      "dollar": ["D1 dollar (UUP)"], "metals": ["M1 gold/silver", "M2 copper/gold"], "risk": ["K1 small/large", "K5 spec growth"]}
m20, m50 = X.rolling(20).mean(), X.rolling(50).mean()
V = np.sign(m20 - m50).where(m50.notna())
fast = np.sign(X - m20)
S = sum(V[c].mean(axis=1) for c in CH.values())
K = len(CH); state = []; cur = "Neutral"; up = dn = 0
for v in S:
    if np.isnan(v): state.append(None); continue
    up = up + 1 if v >= K / 3 else 0; dn = dn + 1 if v <= -K / 3 else 0
    if cur == "Draining" and v <= K / 6: cur = "Neutral"
    if cur == "Easing" and v >= -K / 6: cur = "Neutral"
    if up >= 3: cur = "Draining"
    if dn >= 3: cur = "Easing"
    state.append(cur)
st = pd.Series(state, index=idx)
last = idx[-1]
def since(s):
    s = s.dropna(); ch = s[s != s.shift()]; d = ch.index[-1]; return d.date(), int((s.index > d).sum())
print(f"AS OF {last.date()}  (context, not validated)\n")
print("LEG                 trend(20d vs 50d)  since (sessions)   fast dot (vs 20d)")
for c in X.columns:
    d, n = since(V[c]); t = {1: "TIGHT", -1: "easy", 0: "flat"}[int(V[c].iloc[-1])]
    f = {1: "tight", -1: "easy", 0: "flat"}.get(int(fast[c].iloc[-1]) if not np.isnan(fast[c].iloc[-1]) else 0)
    print(f"{c:22s} {t:6s}  since {d} ({n:3d})   {f}")
gt = sum(int((V[c].iloc[-1] > 0).mean() > 0.5 or (V[c].iloc[-1].mean() > 0)) for c in CH.values())
print(f"\nGROUPS TIGHT (channel score > 0): {sum(int(V[c].iloc[-1].mean() > 0) for c in CH.values())} of {K}; score S = {S.iloc[-1]:+.1f} (range -6..+6)")
print("composite state (no word ships; shown for his read):", st.iloc[-1], "since", since(st)[0])
s20, s50 = S.rolling(20).mean(), S.rolling(50).mean(); sg = np.sign(s20 - s50)
print("composite trend (20d vs 50d of S):", {1: "tightening", -1: "easing", 0: "flat"}[int(sg.iloc[-1])], "since", since(sg)[0])
print("\nMONTH-END S / state:")
for d in pd.date_range("2025-08-31", last, freq="ME"):
    j = idx[idx <= d][-1]; print(f"  {j.date()}  S {S[j]:+.1f}  {st[j]}  groups tight {sum(int(V[c].loc[j].mean() > 0) for c in CH.values())}")
print(f"  {last.date()}  S {S.iloc[-1]:+.1f}  {st.iloc[-1]}")
j = raw["JNK"]; print(f"\nSEED JNK (price, Caruso's chart): {j.iloc[-1]:.2f}  vs 20d {j.rolling(20).mean().iloc[-1]:.2f}  vs 50d {j.rolling(50).mean().iloc[-1]:.2f}  20d slope {j.rolling(20).mean().diff(5).iloc[-1]:+.3f}/wk  1-month change {100*(j.iloc[-1]/j.iloc[-22]-1):+.1f}%")
g = raw["GLD"] / raw["SLV"]; print(f"SEED gold/silver (GLD/SLV): {g.iloc[-1]:.2f}  vs 20d {g.rolling(20).mean().iloc[-1]:.2f}  vs 50d {g.rolling(50).mean().iloc[-1]:.2f}  1-month change {100*(g.iloc[-1]/g.iloc[-22]-1):+.1f}%")
hy = fred("BAMLH0A0HYM2"); print(f"HY spread: {hy.iloc[-1]:.2f}%  1 month ago {hy.iloc[-22]:.2f}%  3 months ago {hy.iloc[-64]:.2f}%")
nl = -X["F1 net liquidity"]; print(f"Net liquidity: ${nl.iloc[-1]/1e6:.2f}T  3 months ago ${nl.iloc[-64]/1e6:.2f}T")
