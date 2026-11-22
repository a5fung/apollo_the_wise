"""r2_verify_a: INDEPENDENT recount of run 2 from raw inputs (Alpaca ETF psv + FRED csv), own code route.
Legs -> trend votes -> E1-E3 -> redundancy -> selection -> composite -> W0 -> W1 -> W2 -> W3 (non-breadth baselines).
Breadth is rebuilt in r2_verify_b.py from the raw cb702 files. Writes only to the scratchpad (OUT) and prints.
Never imports or runs any r2_*.py. Compares to build_r2/ frames at the end (read-only)."""
import pandas as pd, numpy as np, os, sys, itertools, json
CUT = pd.Timestamp("2024-12-31"); HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
RAW = os.path.expanduser("~/apollo_data/liquidity_1122/etf_daily_all.psv")
def P(*a): print(*a)

# ---------------- raw ETF (adjusted) ----------------
e = pd.read_csv(RAW, sep="|", dtype={"ticker": str})
e["date"] = pd.to_datetime(e["date"]); e = e[e["date"] <= CUT]; assert e["date"].max() <= CUT
adj = e.pivot(index="date", columns="ticker", values="c").sort_index()
grid = pd.DatetimeIndex(sorted(e.loc[e.ticker == "SPY", "date"])); assert len(grid) == 2264
adj = adj.reindex(grid)
ng = len(grid)

def etf_fresh(cols):
    ok = np.ones(ng, bool)
    for t in cols:
        have = adj[t].notna().values; last = -10**9; o = np.zeros(ng, bool)
        for i in range(ng):
            if have[i]: last = i
            o[i] = (i - last) <= 3
        ok &= o
    return ok
ff = adj.ffill()

# ---------------- FRED with explicit lag join (own loop) ----------------
def fred(sid):
    d = pd.read_csv(f"{HERE}/fred/{sid}.csv"); d.columns = ["od", "v"]
    d["od"] = pd.to_datetime(d["od"]); d["v"] = pd.to_numeric(d["v"], errors="coerce")
    d = d[d.od <= CUT].dropna(); assert d.od.max() <= CUT
    return d.sort_values("od").reset_index(drop=True)
def usable(sid, rule, fresh_days):
    """rule(od) -> first calendar date the value may be used. For each session take the newest obs with usable_date <= session."""
    d = fred(sid); ud = d.od.map(rule).values.astype("datetime64[ns]")
    order = np.argsort(ud, kind="stable"); ud_s = ud[order]; od_s = d.od.values[order]; v_s = d.v.values[order]
    val = np.full(ng, np.nan); fr = np.zeros(ng, bool); used_od = np.full(ng, np.datetime64("NaT"), "datetime64[ns]")
    j = -1; best = -1
    for i, g in enumerate(grid.values):
        while j + 1 < len(ud_s) and ud_s[j + 1] <= g:
            j += 1
            if best < 0 or od_s[j] >= od_s[best]: best = j
        if best >= 0:
            val[i] = v_s[best]; used_od[i] = od_s[best]
            fr[i] = (g - od_s[best]) / np.timedelta64(1, "D") <= fresh_days
    return val, fr, used_od
nextsess = lambda od: od + pd.Timedelta(days=1)       # usable strictly after obs date  (od < session)
sameday = lambda od: od
plus2 = lambda od: od + pd.Timedelta(days=2)          # Wed level usable Friday
plus7 = lambda od: od + pd.Timedelta(days=7)
L = {}
baa, f_baa, u_baa = usable("BAA10Y", nextsess, 7)
dff, f_dff, u_dff = usable("DFF", nextsess, 7)
dgs2, f_dgs2, u_dgs2 = usable("DGS2", nextsess, 7)
dfii, f_dfii, u_dfii = usable("DFII10", nextsess, 7)
wal, f_wal, u_wal = usable("WALCL", plus2, 14)
tga, f_tga, u_tga = usable("WTREGEN", plus2, 14)
rrp, f_rrp, u_rrp = usable("RRPONTSYD", sameday, 7)
dtw, f_dtw, u_dtw = usable("DTWEXBGS", plus7, 7)
# lag evidence
lagrep = []
for nm, u in (("BAA10Y", u_baa), ("DFF", u_dff), ("DGS2", u_dgs2), ("DFII10", u_dfii), ("WALCL", u_wal), ("WTREGEN", u_tga), ("RRPONTSYD", u_rrp), ("DTWEXBGS", u_dtw)):
    lagd = (grid.values - u) / np.timedelta64(1, "D")
    lagrep.append(f"  {nm}: min calendar days from obs date to session {np.nanmin(lagd):.0f}, median {np.nanmedian(lagd):.0f}")
# (sign, form, P series, fresh)
def S(x): return pd.Series(np.asarray(x, float), grid)
legs = {
 "C1": (-1, "ratio", ff["HYG"], etf_fresh(["HYG"])),
 "C2": (-1, "ratio", ff["HYG"] / ff["IEI"], etf_fresh(["HYG", "IEI"])),
 "C3": (+1, "diff", S(baa), f_baa),
 "F1": (-1, "ratio", S(wal - tga - rrp * 1000), f_wal & f_tga & f_rrp),
 "F2": (+1, "diff", S(dff), f_dff),
 "F3": (+1, "diff", S(dgs2 - dff), f_dgs2 & f_dff),
 "R1": (+1, "diff", S(dfii), f_dfii),
 "R2": (+1, "diff", S(dgs2), f_dgs2),
 "D1": (+1, "ratio", ff["UUP"], etf_fresh(["UUP"])),
 "D2": (+1, "ratio", S(dtw), f_dtw),
 "D3": (+1, "ratio", ff["FXY"], etf_fresh(["FXY"])),
 "M1": (+1, "ratio", ff["GLD"] / ff["SLV"], etf_fresh(["GLD", "SLV"])),
 "M2": (-1, "ratio", ff["CPER"] / ff["GLD"], etf_fresh(["CPER", "GLD"])),
 "K1": (-1, "ratio", ff["IWM"] / ff["SPY"], etf_fresh(["IWM", "SPY"])),
 "K2": (-1, "ratio", ff["SPHB"] / ff["SPLV"], etf_fresh(["SPHB", "SPLV"])),
 "K3": (-1, "ratio", ff["KRE"] / ff["SPY"], etf_fresh(["KRE", "SPY"])),
 "K5": (-1, "ratio", ff["ARKK"] / ff["QQQ"], etf_fresh(["ARKK", "QQQ"])),
}
LEGS = list(legs)
def vote(x, fresh, tol):
    m20 = x.rolling(20).mean(); m50 = x.rolling(50).mean(); d = (m20 - m50).values
    scale = np.maximum(1.0, np.maximum(np.abs(m20.values), np.abs(m50.values)))
    v = np.where(d > tol * scale, 1.0, np.where(d < -tol * scale, -1.0, 0.0))
    v[np.isnan(m50.values) | ~np.asarray(fresh)] = np.nan
    return pd.Series(v, grid)
Xd = {k: s * p for k, (s, f, p, fr) in legs.items()}
V = pd.DataFrame({k: vote(Xd[k], legs[k][3], 1e-9) for k in LEGS})
fs = V.dropna(how="all").index[0]

# ---------------- compare with builder's legs ----------------
bX = pd.read_csv(f"{HERE}/build/legs_X.csv", index_col=0, parse_dates=True); bF = pd.read_csv(f"{HERE}/build/legs_fresh.csv", index_col=0, parse_dates=True)
bV = pd.read_csv(f"{HERE}/build_r2/legs_votes.csv", index_col=0, parse_dates=True)
P("== LEGS FROM RAW vs builder")
P("grid", ng, grid[0].date(), grid[-1].date(), "first state session", fs.date(), "n", int((grid >= fs).sum()))
mism_tot = 0
for k in LEGS:
    x = pd.Series(Xd[k].values, grid); bx = bX[k].reindex(grid)
    rel = ((x - bx).abs() / np.maximum(1e-12, bx.abs())).max()
    frd = int((np.asarray(legs[k][3]) != bF[k].reindex(grid).astype(bool).values).sum())
    a, b = V[k].loc[fs:], bV[k].loc[fs:]; dv = int(((a != b) & ~(a.isna() & b.isna())).sum()); mism_tot += dv
    P(f"  {k}: X max rel diff {rel:.2e} | fresh-flag diffs {frd} | vote diffs {dv} of {len(a)}")
P("  TOTAL vote cells differing:", mism_tot)
P("lag evidence (calendar days between the observation used and the session):"); P("\n".join(lagrep))
# WALCL Wednesday -> Friday sample
smp = [d for d in grid if d.weekday() in (3, 4)][100:104]
for d in smp:
    i = grid.get_loc(d); P(f"  session {d.date()} ({d.day_name()[:3]}): WALCL obs used {pd.Timestamp(u_wal[i]).date()}  DTWEXBGS obs used {pd.Timestamp(u_dtw[i]).date()}  BAA10Y obs used {pd.Timestamp(u_baa[i]).date()}")
# tie sensitivity
P("tie-tolerance sensitivity (vote cells changed vs 1e-9, from first state session):")
for tol in (0.0, 1e-12, 1e-6):
    Vt = pd.DataFrame({k: vote(Xd[k], legs[k][3], tol) for k in LEGS}).loc[fs:]
    ch = {k: int(((Vt[k] != V[k].loc[fs:]) & ~(Vt[k].isna() & V[k].loc[fs:].isna())).sum()) for k in LEGS}
    P(f"  tol {tol:g}: total {sum(ch.values())}; nonzero legs {({k: v for k, v in ch.items() if v})}")

# ---------------- selection ----------------
PRIO = "C1 M1 F1 F2 R1 D1 K1 C2 C3 R2 F3 K5 D3 M2 K2 K3 D2".split()
H = {"H1": (fs, pd.Timestamp("2020-12-31")), "H2": (pd.Timestamp("2021-01-04"), CUT)}
def runs(v):
    out = []; cur = None; n = 0
    for x in v:
        if x != x:
            if cur is not None: out.append(n)
            cur = None; n = 0; continue
        if cur is None or x != cur:
            if cur is not None: out.append(n)
            cur = x; n = 1
        else: n += 1
    if cur is not None: out.append(n)
    return out
P("\n== SELECTION (own code)")
elig, elig12 = {}, {}; etab = []
for k in PRIO:
    ok = ok12 = True; row = [k]
    for h, (a, b) in H.items():
        v = V.loc[a:b, k]; cov = v.notna().mean(); vv = v.dropna(); t = (vv == 1).mean(); ea = (vv == -1).mean(); mr = float(np.median(runs(v.values)))
        e1, e2, e2a, e3 = cov >= .95, (.1 <= t <= .7) and (.1 <= ea <= .7), .1 <= t <= .7, mr >= 5
        ok &= e1 and e2 and e3; ok12 &= e1 and e2a and e3
        row.append(f"{h} n={len(v)} cov {cov*100:.1f} tight {t*100:.1f} easy {ea*100:.1f} medrun {mr:g}")
    elig[k], elig12[k] = ok, ok12; etab.append("  " + " | ".join(row) + f" | elig(4.2)={'Y' if ok else 'N'} elig(12-shorthand)={'Y' if ok12 else 'N'}")
P("\n".join(etab))
G = {}
for k in PRIO:
    s, f, p, fr = legs[k]; m20, m50 = p.rolling(20).mean(), p.rolling(50).mean()
    G[k] = s * ((m20 / m50 - 1) if f == "ratio" else (m20 - m50))
G = pd.DataFrame(G)
def red(a, b):
    thr = .80 if a[0] == b[0] else .85; c_all = ag_all = True; det = []
    for h, (s, e_) in H.items():
        x = G.loc[s:e_, [a, b]].dropna(); c = x[a].corr(x[b])
        v = V.loc[s:e_, [a, b]].dropna(); nz = v[(v[a] != 0) & (v[b] != 0)]; ag = (nz[a] == nz[b]).mean()
        c_all &= c >= thr; ag_all &= ag >= .85; det.append(f"{h} corr {c:+.2f} agree {ag*100:.1f}%")
    return (c_all or ag_all), "; ".join(det)
CHN = {"C": "Credit", "F": "Fed and money", "R": "Rates", "D": "Dollar", "M": "Metals", "K": "Risk appetite"}
def walk(el):
    kept = []; lg = []
    for k in [x for x in PRIO if el[x]]:
        if sum(j[0] == k[0] for j in kept) >= 2: lg.append(f"{k} skipped (channel full)"); continue
        hits = [j for j in kept if red(j, k)[0]]
        if hits: lg.append(f"{k} pruned by {hits} [{red(hits[0], k)[1]}]")
        else: kept.append(k); lg.append(f"{k} KEPT")
    return kept, lg
kept, lg = walk(elig); P("pruning walk (4.2 E2):"); P("  " + " | ".join(lg))
kept12, lg12 = walk(elig12); P("pruning walk (12-shorthand E2):"); P("  " + " | ".join(lg12))
bk = [l.strip() for l in open(f"{HERE}/build_r2/kept_legs.csv") if l.strip()]
P("kept (mine):", kept, "| builder:", bk, "->", "MATCH" if kept == bk else "MISMATCH")
P("alt E2 kept (mine):", kept12)
# D2 vs D1 detail; C1/C2/D3 E2 detail
P("D1-D2 redundancy:", red("D1", "D2"))
P("seed C1 (HYG) tight/easy per half:", [((V.loc[a:b, 'C1'] == 1).mean().round(3), (V.loc[a:b, 'C1'] == -1).mean().round(3)) for a, b in H.values()])

# ---------------- composite ----------------
def composite(Vv, kept, exit_le=True, start=None):
    Vk = Vv.loc[fs:, kept].fillna(0.0)
    ch = {}
    for k in kept: ch.setdefault(k[0], []).append(k)
    C = pd.DataFrame({c: Vk[ks].mean(axis=1) for c, ks in ch.items()}); K = C.shape[1]; T, X_ = K / 3, K / 6
    Sv = C.sum(axis=1).values; st = []; cur = "N"
    for i in range(len(Sv)):
        if i >= 2:
            w = Sv[i-2:i+1]
            dr, ea = (w >= T - 1e-12).all(), (w <= -T + 1e-12).all()
            if exit_le: xd, xe = (w <= X_ + 1e-12).all(), (w >= -X_ - 1e-12).all()
            else: xd, xe = (w < X_ - 1e-12).all(), (w > -X_ + 1e-12).all()
            if cur == "D": cur = "E" if ea else ("N" if xd else "D")
            elif cur == "E": cur = "D" if dr else ("N" if xe else "E")
            else: cur = "D" if dr else ("E" if ea else "N")
        st.append(cur)
    return pd.Series(st, C.index), pd.Series(Sv, C.index), C
ST, SS, CC = composite(V, kept)
bc = pd.read_csv(f"{HERE}/build_r2/composite.csv", index_col=0, parse_dates=True)
P("\n== COMPOSITE: state days differing from builder:", int((ST != bc["state"].reindex(ST.index)).sum()), "of", len(ST), "| S max abs diff", float((SS - bc["S"].reindex(SS.index)).abs().max()))
VS, VE = pd.Timestamp("2017-01-18"), pd.Timestamp("2024-09-27")
def w0w1(ST, VS=VS, VE=VE, label=""):
    val = ST.loc[VS:VE]; out = {}
    chg = (ST != ST.shift()) & ST.shift().notna(); cy = chg.groupby(chg.index.year).sum()
    g = (val != val.shift()).cumsum(); sizes = val.groupby(g).size()
    out["n"] = len(val); out["share"] = {k: (int((val == k).sum()), round((val == k).mean() * 100, 1)) for k in "DNE"}
    out["chg_by_year"] = {int(a): int(b) for a, b in cy.items()}; out["chg_med_17_23"] = float(cy.loc[2017:2023].median())
    out["dwell_med"] = float(sizes.median()); out["spells"] = len(sizes)
    out["W0"] = out["chg_med_17_23"] <= 8 and out["dwell_med"] >= 10 and .10 <= (val == "D").mean() <= .35
    rows = {}
    def sh(a, b, k): x = ST.loc[a:b]; return (x == k).mean(), int((x == k).sum()), len(x)
    for r, a, b, bar in (("S1", "2018-10-10", "2018-12-24", .5), ("S2", "2020-02-28", "2020-04-03", .5), ("S3", "2022-01-18", "2022-10-14", .5), ("S4", "2023-08-15", "2023-10-27", .4)):
        p, c, n = sh(a, b, "D"); rows[r] = (p >= bar, f"D {c}/{n}")
    for r, a, b, leg, lb, dm in (("L1", "2023-03-10", "2023-03-24", "K3", .8, 10), ("L2", "2024-08-01", "2024-08-09", "D3", .8, 5), ("L3", "2018-02-05", "2018-02-16", "R1", .6, 5), ("L4", "2021-02-16", "2021-03-19", "R1", .7, 10)):
        v = V.loc[a:b, leg]; lt = (v == 1).mean(); p, c, n = sh(a, b, "D"); rows[r] = (lt >= lb and c <= dm, f"{leg} tight {int((v==1).sum())}/{len(v)}, D {c}")
    for r, a, b, em, dm in (("Q1", "2017-01-18", "2017-12-29", None, .10), ("Q2", "2019-01-07", "2019-04-30", None, .15), ("Q3", "2019-07-01", "2020-01-31", None, .15), ("Q4", "2020-06-01", "2021-01-29", .5, .10), ("Q5", "2023-11-01", "2024-03-28", .4, .10)):
        p, c, n = sh(a, b, "D"); ee, ec, _ = sh(a, b, "E"); rows[r] = (p <= dm and (em is None or ee >= em), f"D {c}/{n} E {ec}/{n}")
    cnt = {t: sum(rows[r][0] for r in rows if r[0] == t) for t in "SLQ"}
    out["W1rows"] = {r: ("hit" if v[0] else "MISS") + " " + v[1] for r, v in rows.items()}; out["W1cnt"] = cnt
    out["W1"] = cnt["S"] >= 3 and cnt["L"] >= 3 and cnt["Q"] >= 4
    return out
R0 = w0w1(ST)
P("W0/W1 (mine):", json.dumps(R0, default=str))
# sensitivities
P("\n== SENSITIVITY (W0 Draining share / W1 calm)")
for lab, st_ in (("exit '<' (strict below K/6) instead of '<='", composite(V, kept, exit_le=False)[0]),):
    r = w0w1(st_); P(f"  {lab}: Draining {r['share']['D']} of {r['n']}; changes med {r['chg_med_17_23']}; dwell {r['dwell_med']}; W0 {r['W0']}; W1 cnt {r['W1cnt']} Q1 {r['W1rows']['Q1']} Q5 {r['W1rows']['Q5']}")
for tol in (0.0, 1e-6):
    Vt = pd.DataFrame({k: vote(Xd[k], legs[k][3], tol) for k in LEGS}); st_ = composite(Vt, kept)[0]; r = w0w1(st_)
    P(f"  tie tol {tol:g}: state diffs {int((st_ != ST).sum())}; Draining {r['share']['D']}; W0 {r['W0']}; W1 {r['W1cnt']}")
for lab, a, b in (("window from 2017-01-17", "2017-01-17", "2024-09-27"), ("window to 2024-09-30", "2017-01-18", "2024-09-30"), ("both extra sessions", "2017-01-17", "2024-09-30")):
    r = w0w1(ST, pd.Timestamp(a), pd.Timestamp(b)); P(f"  {lab}: n {r['n']} Draining {r['share']['D']}")
# Draining share of window needed to pass: how many sessions over 35%
val = ST.loc[VS:VE]; P(f"  Draining sessions over the 35% line: {int((val=='D').sum()) - int(np.floor(.35*len(val)))} (line = {int(np.floor(.35*len(val)))} of {len(val)})")
ST.to_frame("state").assign(S=SS).to_csv(f"{OUT}/my_composite.csv")
V.to_csv(f"{OUT}/my_votes.csv")
adj.to_csv(f"{OUT}/my_adj.csv")
pd.Series(kept).to_csv(f"{OUT}/my_kept.csv", index=False, header=False)
