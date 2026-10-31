"""POST-HOC diagnostic of why C3b failed (prereg §11 C3: bar-derived +10-session close-to-close return vs mi_ep_scan_outcomes.fwd_10d_pct).
Reads only the stored outcome columns and bars to find out WHAT the stored column measures. Does NOT touch any float/neglect feature or any verdict statistic."""
import sys, numpy as np, pandas as pd
sys.argv = [sys.argv[0]]
import importlib.util, os
spec = importlib.util.spec_from_file_location("s2", os.path.join(os.path.dirname(os.path.abspath(__file__)), "s2_read.py"))
s2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(s2)
S = s2.load_all(); B = s2.Bars(S)
tb = s2.tab(S["tail"]["POP_B"]); tb = tb[tb.is_scored == "t"].copy()
tb = s2.to_num(tb, ["outcome_baseline_close", "fwd_5d_pct", "fwd_10d_pct", "n_sessions_5d", "n_sessions_10d"])
rows = []
for r in tb.itertuples():
    ti = B.tix[r.ticker]; iD = B.ix[r.scan_date]
    c0 = B.c[ti, iD]
    if not np.isfinite(r.fwd_10d_pct) or not np.isfinite(c0):
        continue
    d = dict(ticker=r.ticker, date=r.scan_date, base=r.outcome_baseline_close, c0=c0, f5=r.fwd_5d_pct, f10=r.fwd_10d_pct, n5=r.n_sessions_5d, n10=r.n_sessions_10d)
    for k in (1, 5, 8, 9, 10, 11):
        ck = B.c[ti, iD + k]
        d[f"cc{k}"] = (ck / c0 - 1) * 100
    d["hi10"] = (np.nanmax(B.h[ti, iD + 1:iD + 11]) / c0 - 1) * 100
    d["o1"] = (B.o[ti, iD + 1] / c0 - 1) * 100
    d["cc10_vs_o1"] = (B.c[ti, iD + 10] / B.o[ti, iD + 1] - 1) * 100
    d["cc9_vs_o1"] = (B.c[ti, iD + 9] / B.o[ti, iD + 1] - 1) * 100
    d["cc10_vs_oD"] = (B.c[ti, iD + 10] / B.o[ti, iD] - 1) * 100
    rows.append(d)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df.head(12).round(2).to_string())
for col in ["cc8", "cc9", "cc10", "cc11", "hi10", "cc10_vs_o1", "cc9_vs_o1", "cc10_vs_oD"]:
    print(f"{col:12s} within 0.5pp of stored fwd_10d_pct: {((df[col]-df.f10).abs()<=0.5).mean()*100:5.1f}%   median abs diff {np.nanmedian((df[col]-df.f10).abs()):.2f}")
for k, n in ((5, "cc5"),):
    print(f"cc5 vs fwd_5d within 0.5pp: {((df[n]-df.f5).abs()<=0.5).mean()*100:.1f}%")
print("corr(cc10, f10) =", np.corrcoef(df.cc10, df.f10)[0, 1].round(3), " corr(cc9, f10) =", np.corrcoef(df.cc9, df.f10)[0, 1].round(3))
# offset implied by n_sessions_10d
for n in (10, 9, 8):
    m = df[df.n10 == n]
    kk = f"cc{n}" if f"cc{n}" in df else None
    if kk:
        print(f"rows with n_sessions_10d={n}: {len(m)}; bar close at +{n} within 0.5pp: {((m[kk]-m.f10).abs()<=0.5).mean()*100:.1f}%")
# is stored fwd_10d perhaps measured from a different anchor? regress
print("f10 - cc10 summary:", (df.f10 - df.cc10).describe().round(2).to_dict())
print("ratio f10/cc10 median:", np.nanmedian(df.f10 / df.cc10))
