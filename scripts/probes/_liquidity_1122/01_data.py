"""01: ETF + FRED load (cut+assert), HYG adjustment check, JNK rule, leg series X (up=tighter) on the grid, votes,
price-only vs adjusted vote difference. NO outcome, breadth, EP or breakout file is opened here."""
import pandas as pd, numpy as np, os, subprocess, io
CUT = pd.Timestamp("2024-12-31"); B = "build"; D = os.path.expanduser("~/apollo_data")
def etf(name):
    d = pd.read_csv(f"{D}/liquidity_1122/etf_daily_{name}.psv", sep="|", parse_dates=["date"])
    d = d[d.date <= CUT]; assert d.date.max() <= CUT
    assert not d.duplicated(["ticker", "date"]).any()
    return d.pivot(index="date", columns="ticker", values="c").sort_index()
A, R = etf("all"), etf("raw")
grid = A["SPY"].dropna().index
print("grid sessions", len(grid), grid[0].date(), grid[-1].date()); assert len(grid) == 2264 and grid[0] == pd.Timestamp("2016-01-04")
A, R = A.reindex(grid), R.reindex(grid)
print("missing adjusted bars per ticker on grid:", {t: int(A[t].isna().sum()) for t in A.columns if A[t].isna().any()})

# ---- HYG adjustment check (tolerance fixed before looking: 1e-3 relative = above 2-decimal rounding noise ~3e-4, below a monthly distribution ~3e-3+)
TOL = 1e-3
f = (A["HYG"] / R["HYG"]); st = f / f.shift(1) - 1
steps = st[st.abs() > TOL]
print(f"\nHYG adjustment check: adj/raw factor first {f.iloc[0]:.5f} last {f.iloc[-1]:.5f}; step days (|change|>{TOL}) n={len(steps)}")
print("  steps per year:", steps.groupby(steps.index.year).size().to_dict())
print("  negative steps:", int((steps < 0).sum()), " step size min/median/max: %.4f %.4f %.4f" % (steps.min(), steps.median(), steps.max()))
print("  step day-of-month counts:", steps.groupby(steps.index.day).size().to_dict())
print("  months with >1 step:", {str(k): int(v) for k, v in steps.groupby(steps.index.to_period('M')).size().items() if v > 1})
print("  non-step days max |factor change|: %.6f (n=%d)" % (st[st.abs() <= TOL].abs().max(), (st.abs() <= TOL).sum()))
ye = f.groupby(f.index.year).agg(["first", "last"]); prev_last = ye["last"].shift(1).fillna(f.iloc[0])
drift = ye["last"] / prev_last - 1
print("  factor drift per calendar year:", {int(y): round(float(v), 4) for y, v in drift.items()})
ok_drift = bool(((drift >= 0.03) & (drift <= 0.08)).all()); ok_steps = bool((steps > 0).all() and steps.groupby(steps.index.to_period('M')).size().max() <= 2)
print("  drift 3-8% every year:", ok_drift, "| steps all upward, <=2 per month:", ok_steps)
print("  step dates:", " ".join(d.strftime("%Y-%m-%d") for d in steps.index))
# splits: raw vs adjusted daily return gap > 5%
for t in A.columns:
    g = (A[t].pct_change() - R[t].pct_change()).abs()
    if (g > 0.05).any(): print("  SPLIT-like day", t, [(d.strftime('%Y-%m-%d'), round(float(v), 3)) for d, v in g[g > 0.05].items()])

# ---- local closes cross-check (ETF tickers only, awk cut <= 2024-12-31 before python sees a row)
T = list(A.columns); pat = "|".join(T); loc = f"{B}/local_etf_closes.csv"
if not os.path.exists(loc):
    with open(loc, "w") as fh:
        for src in ("cb702_pre_v2", "cb702"):
            cmd = f"gzcat {D}/{src}/daily_closes_all.csv.gz | awk -F, -v s={src} '$2<=\"2024-12-31\" && $1 ~ /^({pat})$/ {{print s\",\"$1\",\"$2\",\"$6}}'"
            fh.write(subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout)
L = pd.read_csv(loc, names=["src", "ticker", "date", "c"], parse_dates=["date"]); assert L.date.max() <= CUT
print("\nlocal cross-check (Alpaca raw vs local split-adjusted close): ticker src n max|rel diff| n>0.5%")
for (s, t), g in L.groupby(["src", "ticker"]):
    j = g.set_index("date")["c"].reindex(grid).dropna(); r = (R[t].reindex(j.index) / j - 1).abs()
    print(f"  {t:5s} {s:13s} n={len(j):4d} max={r.max():.4f} n_gt_0.5%={(r > 0.005).sum()}")

# ---- JNK rule
print("\nJNK rule (needs every calendar year 2016-2024: daily-return corr with HYG >= 0.90 and no day differing > 3 points)")
rj, rh = A["JNK"].pct_change(), A["HYG"].pct_change(); jnk_ok = True
for y in range(2016, 2025):
    m = (grid.year == y); a, b = rj[m], rh[m]; k = a.notna() & b.notna()
    if k.sum() < 200: print(f"  {y}: JNK sessions with a return n={k.sum()} of {m.sum()} -> year not covered -> FAIL"); jnk_ok = False; continue
    c = np.corrcoef(a[k], b[k])[0, 1]; mx = (a[k] - b[k]).abs().max(); ok = c >= 0.90 and mx <= 0.03; jnk_ok &= ok
    print(f"  {y}: n={k.sum()} corr={c:.3f} max day gap={mx*100:.2f} pts -> {'ok' if ok else 'FAIL'}")
print("  RESULT: C1 uses", "JNK" if jnk_ok else "HYG for the whole history (no splice); JNK only on the seed tile")
C1T = "JNK" if jnk_ok else "HYG"

# ---- FRED
def fred(i):
    d = pd.read_csv(f"fred/{i}.csv"); d.columns = ["date", "v"]; d["date"] = pd.to_datetime(d.date); d["v"] = pd.to_numeric(d.v, errors="coerce")
    d = d[d.date <= CUT]; assert d.date.max() <= CUT
    return d.dropna().set_index("date")["v"]
def on_grid(s, lag_days, strict_before, fresh_days):
    """value usable at session g = newest obs with obs_date + lag_days <= g (or < g when strict_before). returns (ffilled value, fresh flag)."""
    obs = pd.DataFrame({"od": s.index, "v": s.values}); obs["avail"] = obs.od + pd.Timedelta(days=lag_days)
    g = pd.DataFrame({"g": grid})
    m = pd.merge_asof(g, obs.sort_values("avail"), left_on="g", right_on="avail", allow_exact_matches=not strict_before)
    age = (m.g - m.od).dt.days
    return pd.Series(m.v.values, grid), pd.Series((age <= fresh_days).values & m.v.notna().values, grid)
P, FR, SIGN, FORM = {}, {}, {}, {}
def add(k, p, fresh, sign, form): P[k], FR[k], SIGN[k], FORM[k] = p, fresh, sign, form
def etffresh(*ts):  # carry at most 3 sessions
    ok = pd.Series(True, grid)
    for t in ts:
        last = pd.Series(np.where(A[t].notna(), np.arange(len(grid)), np.nan), grid).ffill()
        ok &= (np.arange(len(grid)) - last) <= 3
    return ok
Af = A.ffill()
add("C1", Af[C1T], etffresh(C1T), -1, "ratio")
add("C2", Af["HYG"] / Af["IEI"], etffresh("HYG", "IEI"), -1, "ratio")
v, fr = on_grid(fred("BAA10Y"), 0, True, 7); add("C3", v, fr, +1, "diff")
wal, f1 = on_grid(fred("WALCL"), 2, False, 14); tga, f2 = on_grid(fred("WTREGEN"), 2, False, 14); rrp, f3 = on_grid(fred("RRPONTSYD"), 0, False, 7)
add("F1", wal - tga - rrp * 1000, f1 & f2 & f3, -1, "ratio")
dff, frd = on_grid(fred("DFF"), 0, True, 7); add("F2", dff, frd, +1, "diff")
dg2, fr2 = on_grid(fred("DGS2"), 0, True, 7); add("F3", dg2 - dff, fr2 & frd, +1, "diff")
v, fr = on_grid(fred("DFII10"), 0, True, 7); add("R1", v, fr, +1, "diff")
add("R2", dg2, fr2, +1, "diff")
add("D1", Af["UUP"], etffresh("UUP"), +1, "ratio")
v, fr = on_grid(fred("DTWEXBGS"), 7, False, 7); add("D2", v, fr, +1, "ratio")
add("D3", Af["FXY"], etffresh("FXY"), +1, "ratio")
add("M1", Af["GLD"] / Af["SLV"], etffresh("GLD", "SLV"), +1, "ratio")
add("M2", Af["CPER"] / Af["GLD"], etffresh("CPER", "GLD"), -1, "ratio")
add("K1", Af["IWM"] / Af["SPY"], etffresh("IWM", "SPY"), -1, "ratio")
add("K2", Af["SPHB"] / Af["SPLV"], etffresh("SPHB", "SPLV"), -1, "ratio")
add("K3", Af["KRE"] / Af["SPY"], etffresh("KRE", "SPY"), -1, "ratio")
add("K5", Af["ARKK"] / Af["QQQ"], etffresh("ARKK", "QQQ"), -1, "ratio")
LEGS = list(P)
def vote_of(x, fresh):
    # rerun 2 (disclosed): exact-tie fix. Window means by direct summation (no running-sum drift); a difference within 1e-9 relative is a TIE -> 0 (prereg 4.1)
    from numpy.lib.stride_tricks import sliding_window_view as swv
    a = x.values.astype(float)
    def ma(n):
        o = np.full(len(a), np.nan); o[n-1:] = swv(a, n).mean(axis=1); return pd.Series(o, x.index)
    m20, m50 = ma(20), ma(50)
    def gt(p, q): return (p - q) > 1e-9 * np.maximum(1.0, np.maximum(p.abs(), q.abs()))
    v = pd.Series(0.0, x.index); v[gt(x, m20) & gt(m20, m50)] = 1; v[gt(m20, x) & gt(m50, m20)] = -1
    v[m50.isna() | ~fresh] = np.nan
    return v
Pdf = pd.DataFrame(P); FRdf = pd.DataFrame(FR)
X = pd.DataFrame({k: SIGN[k] * Pdf[k] for k in LEGS})
V = pd.DataFrame({k: vote_of(X[k], FRdf[k]) for k in LEGS})
print("\nfirst session with a 50-session average:", V.dropna(how="all").index[0].date(), "(grid session #%d)" % (list(grid).index(V.dropna(how='all').index[0]) + 1))
print("\nleg: stale sessions (no fresh value) from first state session, of n; D2 freshness is the literal rule (observation exactly 7 days old)")
fs = V.dropna(how="all").index[0]; n = (grid >= fs).sum()
for k in LEGS: print(f"  {k}: stale {int((~FRdf.loc[fs:, k]).sum())} of {n}")
# D2 alternative MA reading: an average window that holds any stale session has no value
x = X["D2"].where(FRdf["D2"]); m20, m50 = x.rolling(20).mean(), x.rolling(50).mean()
print("  D2 alternative reading (average undefined when its window holds a stale session): sessions with a vote", int((x.notna() & m50.notna()).loc[fs:].sum()), "of", n)

# ---- price-only vs adjusted vote
print("\nprice-only (Alpaca raw close) vs adjusted vote, share of sessions differing (n = sessions where both votes exist)")
Rf = R.ffill()
po = {"C1": -Rf[C1T], "C1(JNK tile)": -Rf["JNK"], "C2": -(Rf["HYG"] / Rf["IEI"]), "D1": Rf["UUP"], "D3": Rf["FXY"], "M1": Rf["GLD"] / Rf["SLV"], "M2": -(Rf["CPER"] / Rf["GLD"]),
      "K1": -(Rf["IWM"] / Rf["SPY"]), "K2": -(Rf["SPHB"] / Rf["SPLV"]), "K3": -(Rf["KRE"] / Rf["SPY"]), "K5": -(Rf["ARKK"] / Rf["QQQ"])}
for k, xr in po.items():
    va = V[k] if k in V else vote_of(-Af["JNK"], etffresh("JNK") & Af["JNK"].notna()); vr = vote_of(xr, pd.Series(True, grid))
    m = va.notna() & vr.notna(); d = (va[m] != vr[m]).mean()
    print(f"  {k:13s} differ {d*100:5.2f}% (n={m.sum()}) -> {'price-only acceptable live' if d <= 0.02 else 'adjusted closes required live'}")
Pdf.to_csv(f"{B}/legs_P.csv"); X.to_csv(f"{B}/legs_X.csv"); V.to_csv(f"{B}/legs_votes.csv"); FRdf.to_csv(f"{B}/legs_fresh.csv")
pd.Series(SIGN).to_csv(f"{B}/legs_sign.csv"); pd.Series(FORM).to_csv(f"{B}/legs_form.csv")
A.to_csv(f"{B}/etf_adj.csv"); R.to_csv(f"{B}/etf_raw.csv")
print("\nsaved build/legs_*.csv, etf_adj.csv, etf_raw.csv")
