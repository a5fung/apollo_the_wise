"""r2_01: run 2 (prereg §12). Rebuild the leg votes as the TREND vote (MA20 vs MA50 of X, two-state; 0 only on an exact tie or missing/stale data).
Reads ONLY run-1 build/legs_X.csv, legs_fresh.csv, etf_adj.csv, etf_raw.csv (ETF legs' price-only check). No outcome, breadth, EP or breakout file.
Run-1 conventions kept: window means by direct summation, tie = within 1e-9 relative, stale/unwarmed session = missing vote."""
import pandas as pd, numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv
CUT = pd.Timestamp("2024-12-31"); B, O = "build", "build_r2"
X = pd.read_csv(f"{B}/legs_X.csv", index_col=0, parse_dates=True); FR = pd.read_csv(f"{B}/legs_fresh.csv", index_col=0, parse_dates=True)
A = pd.read_csv(f"{B}/etf_adj.csv", index_col=0, parse_dates=True); R = pd.read_csv(f"{B}/etf_raw.csv", index_col=0, parse_dates=True)
for d in (X, FR, A, R): assert d.index.max() <= CUT
grid = X.index; assert len(grid) == 2264
def ma(x, n):
    a = x.values.astype(float); o = np.full(len(a), np.nan); o[n-1:] = swv(a, n).mean(axis=1); return pd.Series(o, x.index)
def gt(p, q): return (p - q) > 1e-9 * np.maximum(1.0, np.maximum(p.abs(), q.abs()))
def trend_vote(x, fresh):
    m20, m50 = ma(x, 20), ma(x, 50)
    v = pd.Series(0.0, x.index); v[gt(m20, m50)] = 1; v[gt(m50, m20)] = -1
    v[m50.isna() | ~fresh] = np.nan
    return v
def fast_dot(x, fresh):  # display only: X vs MA20
    m20 = ma(x, 20); v = pd.Series(0.0, x.index); v[gt(x, m20)] = 1; v[gt(m20, x)] = -1; v[m20.isna() | ~fresh] = np.nan; return v
V = pd.DataFrame({k: trend_vote(X[k], FR[k].astype(bool)) for k in X.columns})
F = pd.DataFrame({k: fast_dot(X[k], FR[k].astype(bool)) for k in X.columns})
fs = V.dropna(how="all").index[0]
print("grid", len(grid), grid[0].date(), grid[-1].date(), "| first state session", fs.date(), "| sessions from it", int((grid >= fs).sum()))
print("\nleg: tight / easy / exact-tie(0) / missing sessions from the first state session")
for k in V.columns:
    v = V.loc[fs:, k]; print(f"  {k}: tight {int((v==1).sum())} easy {int((v==-1).sum())} tie {int((v==0).sum())} missing {int(v.isna().sum())}")
V1 = pd.read_csv(f"{B}/legs_votes.csv", index_col=0, parse_dates=True)
print("\nvs run-1 combined vote (share of sessions where the run-1 vote was non-zero and the trend vote has the SAME sign; n = run-1 non-zero sessions)")
for k in V.columns:
    m = V1[k].notna() & (V1[k] != 0) & V[k].notna(); print(f"  {k}: {(V1[k][m]==V[k][m]).mean()*100:5.1f}% (n={int(m.sum())})")
# price-only vs adjusted trend vote (§6.5), on the new vote
Af, Rf = A.ffill(), R.ffill(); T = pd.Series(True, grid)
po = {"C1": -Rf["HYG"], "C2": -(Rf["HYG"]/Rf["IEI"]), "D1": Rf["UUP"], "D3": Rf["FXY"], "M1": Rf["GLD"]/Rf["SLV"], "M2": -(Rf["CPER"]/Rf["GLD"]),
      "K1": -(Rf["IWM"]/Rf["SPY"]), "K2": -(Rf["SPHB"]/Rf["SPLV"]), "K3": -(Rf["KRE"]/Rf["SPY"]), "K5": -(Rf["ARKK"]/Rf["QQQ"])}
print("\nprice-only (Alpaca raw close) vs adjusted TREND vote, share of sessions differing (n = sessions where both exist)")
for k, xr in po.items():
    vr = trend_vote(xr, T); m = V[k].notna() & vr.notna(); d = (V[k][m] != vr[m]).mean()
    print(f"  {k:3s} differ {d*100:5.2f}% (n={int(m.sum())}) -> {'price-only acceptable live' if d <= 0.02 else 'adjusted closes required live'}")
vj_a = trend_vote(-Af["JNK"], Af["JNK"].notna()); vj_r = trend_vote(-Rf["JNK"], Rf["JNK"].notna()); m = vj_a.notna() & vj_r.notna()
print(f"  C1(JNK tile) differ {(vj_a[m]!=vj_r[m]).mean()*100:5.2f}% (n={int(m.sum())})   [JNK NaN-window sessions have no vote]")
V.to_csv(f"{O}/legs_votes.csv"); F.to_csv(f"{O}/legs_fastdot.csv")
print("\nsaved build_r2/legs_votes.csv, legs_fastdot.csv")
