"""Verifier recount (independent code). Reads ONLY the raw inputs: ~/apollo_data/liquidity_1122/etf_daily_{all,raw}.psv and fred/*.csv.
Opens build/legs_votes.csv / kept_legs.csv only to diff. No outcome, breadth, EP or breakout file is opened; no forward value is computed."""
import os, csv, itertools, statistics, math
from datetime import date, timedelta
CUT = date(2024, 12, 31); HERE = os.path.dirname(os.path.abspath(__file__))
def d(s): return date.fromisoformat(s)

# ---- ETF closes (adjusted + raw), cut on load
def load_psv(name):
    out = {}
    with open(os.path.expanduser(f"~/apollo_data/liquidity_1122/etf_daily_{name}.psv")) as f:
        r = csv.DictReader(f, delimiter="|")
        for row in r:
            dt = d(row["date"])
            if dt > CUT: continue
            out.setdefault(row["ticker"], {})[dt] = float(row["c"])
    assert max(max(v) for v in out.values()) <= CUT
    return out
ADJ, RAW = load_psv("all"), load_psv("raw")
grid = sorted(ADJ["SPY"]); N = len(grid); gi = {g: i for i, g in enumerate(grid)}
print("grid", N, grid[0], grid[-1])

def etf_series(px, t):
    """carry last close at most 3 sessions; returns (value list, fresh list)"""
    vals, fresh, last, lasti = [], [], None, None
    for i, g in enumerate(grid):
        if g in px[t]: last, lasti = px[t][g], i
        vals.append(last); fresh.append(last is not None and i - lasti <= 3)
    return vals, fresh

# ---- FRED with own lag code
def load_fred(i, scale):
    obs = []
    with open(os.path.join(HERE, "fred", f"{i}.csv")) as f:
        r = csv.reader(f); next(r)
        for od, v in r:
            od = d(od)
            if od > CUT or v in ("", "."): continue
            obs.append((od, int(round(float(v) * scale))))
    obs.sort(); assert obs[-1][0] <= CUT
    return obs
def fred_on_grid(obs, usable, maxage):
    """usable(od, g) -> bool; value at g = newest obs usable by g; fresh when g - od <= maxage days"""
    vals, fresh, j, cur = [], [], 0, None
    # obs sorted by od; usable is monotone in od for fixed lag rules
    for g in grid:
        while j < len(obs) and usable(obs[j][0], g): cur = obs[j]; j += 1
        vals.append(None if cur is None else cur[1]); fresh.append(cur is not None and (g - cur[0]).days <= maxage)
    return vals, fresh
nxt = lambda od, g: od < g                      # "next session"
same = lambda od, g: od <= g                    # same day
fri = lambda od, g: od + timedelta(days=2) <= g  # Wednesday level usable Friday
wk7 = lambda od, g: od + timedelta(days=7) <= g  # obs date + 7 calendar days
BAA = fred_on_grid(load_fred("BAA10Y", 100), nxt, 7)
DFF = fred_on_grid(load_fred("DFF", 100), nxt, 7)
DGS2 = fred_on_grid(load_fred("DGS2", 100), nxt, 7)
DFII = fred_on_grid(load_fred("DFII10", 100), nxt, 7)
WAL = fred_on_grid(load_fred("WALCL", 1), fri, 14)
TGA = fred_on_grid(load_fred("WTREGEN", 1), fri, 14)
RRP = fred_on_grid(load_fred("RRPONTSYD", 1000), same, 7)   # $bn*1000 = $mn, exact int
DTW = fred_on_grid(load_fred("DTWEXBGS", 10000), wk7, 7)
def comb(f, *ss):
    v = [None if any(s[0][i] is None for s in ss) else f(*[s[0][i] for s in ss]) for i in range(N)]
    fr = [all(s[1][i] for s in ss) for i in range(N)]
    return v, fr

# ---- legs: X oriented up = tighter. FRED legs are exact integers; ETF legs floats
L = {}
L["C3"] = BAA; L["F2"] = DFF; L["R1"] = DFII; L["R2"] = DGS2
L["F3"] = comb(lambda a, b: a - b, DGS2, DFF)
L["F1"] = comb(lambda w, t, r: -(w - t - r), WAL, TGA, RRP)
L["D2"] = DTW
def etfleg(sign, num, den=None):
    a = etf_series(ADJ, num)
    if den is None: return [None if x is None else sign * x for x in a[0]], a[1]
    b = etf_series(ADJ, den)
    return [None if (x is None or y is None) else sign * x / y for x, y in zip(a[0], b[0])], [p and q for p, q in zip(a[1], b[1])]
L["C1"] = etfleg(-1, "HYG"); L["C2"] = etfleg(-1, "HYG", "IEI"); L["D1"] = etfleg(+1, "UUP"); L["D3"] = etfleg(+1, "FXY")
L["M1"] = etfleg(+1, "GLD", "SLV"); L["M2"] = etfleg(-1, "CPER", "GLD"); L["K1"] = etfleg(-1, "IWM", "SPY")
L["K2"] = etfleg(-1, "SPHB", "SPLV"); L["K3"] = etfleg(-1, "KRE", "SPY"); L["K5"] = etfleg(-1, "ARKK", "QQQ")
INTLEG = {"C3", "F2", "R1", "R2", "F3", "F1", "D2"}
PRIO = "C1 M1 F1 F2 R1 D1 K1 C2 C3 R2 F3 K5 D3 M2 K2 K3 D2".split(); assert sorted(PRIO) == sorted(L)

def votes(x, fresh, exact):
    out = [None] * N
    for i in range(49, N):
        w = x[i - 49:i + 1]
        if any(v is None for v in w): continue
        if exact: s20, s50, xi = sum(w[-20:]), sum(w), w[-1]
        else: s20, s50, xi = math.fsum(w[-20:]), math.fsum(w), w[-1]
        a, b = 20 * xi, s20          # X vs MA20 (scaled by 20)
        c, e = 50 * s20, 20 * s50    # MA20 vs MA50 (scaled by 1000)
        if not exact:  # float: treat |diff| within 1e-12 relative as a tie (ratios of adjusted closes)
            if abs(a - b) <= 1e-12 * max(abs(a), abs(b)): a = b
            if abs(c - e) <= 1e-12 * max(abs(c), abs(e)): c = e
        v = 1 if (a > b and c > e) else (-1 if (a < b and c < e) else 0)
        out[i] = v if fresh[i] else None
    return out
V = {k: votes(L[k][0], L[k][1], k in INTLEG) for k in PRIO}

# ---- diff vs builder votes
with open(os.path.join(HERE, "build", "legs_votes.csv")) as f:
    r = csv.reader(f); hdr = next(r); BV = {k: [None] * N for k in hdr[1:]}
    for row in r:
        i = gi[d(row[0][:10])]
        for k, v in zip(hdr[1:], row[1:]): BV[k][i] = None if v == "" else int(float(v))
tot = 0
print("\nVOTE RECOUNT vs builder legs_votes.csv (differences = sessions where vote or missingness differs)")
for k in PRIO:
    diff = [grid[i] for i in range(N) if V[k][i] != BV[k][i]]; tot += len(diff)
    print(f"  {k}: {len(diff)} differ" + (f"  first: {diff[:5]}" if diff else ""))
print("  TOTAL differing:", tot)

# ---- E1/E2/E3 under several readings
fs = next(i for i in range(N) if any(V[k][i] is not None for k in PRIO))
H = {"H1": (fs, gi[date(2020, 12, 31)]), "H2": (gi[date(2021, 1, 4)], N - 1)}
print("\nfirst state session", grid[fs], "| H1 n", H["H1"][1] - H["H1"][0] + 1, "| H2 n", H["H2"][1] - H["H2"][0] + 1)
def runs_from(seq, skip_missing):
    if skip_missing: seq = [v for v in seq if v is not None]
    return [len(list(g)) for key, g in itertools.groupby(seq) if key is not None]
def whole_runs(k):
    """runs over the full history (missing breaks), each tagged by index of first session"""
    out, i = [], fs
    while i < N:
        if V[k][i] is None: i += 1; continue
        j = i
        while j + 1 < N and V[k][j + 1] == V[k][i]: j += 1
        out.append((i, j - i + 1)); i = j + 1
    return out
READ = {}
def elig(k, reading):
    res = []
    for h, (a, b) in H.items():
        seq = V[k][a:b + 1]; n = len(seq); nn = [v for v in seq if v is not None]
        cov = len(nn) / n; t = nn.count(1) / len(nn); e = nn.count(-1) / len(nn)
        if reading == "per_run_missing_breaks": rl = runs_from(seq, False); mr = statistics.median(rl)
        elif reading == "per_run_missing_skipped": rl = runs_from(seq, True); mr = statistics.median(rl)
        elif reading == "uncut_runs_by_start_half": rl = [L_ for s, L_ in whole_runs(k) if a <= s <= b]; mr = statistics.median(rl)
        elif reading == "per_session_median":   # run length of the run each session sits in (sessions-weighted)
            rl = runs_from(seq, False); mr = statistics.median([x for x in rl for _ in range(x)])
        res.append((h, n, cov, t, e, mr, cov >= 0.95, 0.10 <= t <= 0.70 and 0.10 <= e <= 0.70, mr >= 5))
    return res
READINGS = ["per_run_missing_breaks", "per_run_missing_skipped", "uncut_runs_by_start_half", "per_session_median"]
ELIG = {}
for rd in READINGS:
    ELIG[rd] = [k for k in PRIO if all(x[6] and x[7] and x[8] for x in elig(k, rd))]
print("\nE1/E2/E3 table, builder's reading (per-run median, a missing vote breaks a run), and the median run under the other readings")
print("leg half     n   cov%  tight%  easy%  med_run | skip-missing  uncut  per-session")
for k in PRIO:
    base = elig(k, READINGS[0]); others = [elig(k, rd) for rd in READINGS[1:]]
    for idx, x in enumerate(base):
        h, n, cov, t, e, mr = x[:6]
        print(f"{k}  {h}  {n:5d}  {cov*100:5.1f}  {t*100:5.1f}  {e*100:5.1f}  {mr:6.1f}  | {others[0][idx][5]:6.1f}  {others[1][idx][5]:6.1f}  {others[2][idx][5]:6.1f}"
              f"   E1{'Y' if x[6] else 'N'} E2{'Y' if x[7] else 'N'} E3{'Y' if x[8] else 'N'}")

# ---- redundancy walk per reading
def ma(x, n, i): return sum(x[i - n + 1:i + 1]) / n
SIGN = {k: (+1 if k in ("C3", "F2", "F3", "R1", "R2", "D1", "D2", "D3", "M1") else -1) for k in PRIO}
RATIO = {k for k in PRIO if k not in ("C3", "F2", "F3", "R1", "R2")}
def rawP(k):  # un-negated P
    x = L[k][0]; s = SIGN[k] if k not in ("F1",) else -1
    return [None if v is None else v * s for v in x]  # X = sign*P  -> P = sign*X (sign is +-1)
G = {}
for k in PRIO:
    P = rawP(k); g = [None] * N
    for i in range(49, N):
        w = P[i - 49:i + 1]
        if any(v is None for v in w): continue
        m20, m50 = sum(w[-20:]) / 20, sum(w) / 50
        g[i] = SIGN[k] * ((m20 / m50 - 1) if k in RATIO else (m20 - m50))
    G[k] = g
def corr(a, b):
    n = len(a); ma_, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma_) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma_) * (y - mb) for x, y in zip(a, b)) / (sa * sb)
def redundant(a, b):
    thr = 0.80 if a[0] == b[0] else 0.85; t1 = t2 = True
    for h, (s, e) in H.items():
        idx = [i for i in range(s, e + 1) if G[a][i] is not None and G[b][i] is not None]
        t1 &= corr([G[a][i] for i in idx], [G[b][i] for i in idx]) >= thr
        nz = [i for i in range(s, e + 1) if V[a][i] not in (None, 0) and V[b][i] not in (None, 0)]
        t2 &= (sum(V[a][i] == V[b][i] for i in nz) / len(nz) if nz else 0) >= 0.85
    return t1 or t2
print("\nKEPT LIST per E3 reading (channel cap during the walk)")
for rd in READINGS:
    kept = []
    for k in [k for k in PRIO if k in ELIG[rd]]:
        if sum(1 for j in kept if j[0] == k[0]) >= 2: continue
        if any(redundant(j, k) for j in kept): continue
        kept.append(k)
    Kc = len({k[0] for k in kept})
    print(f"  {rd:26s} eligible {ELIG[rd]} -> kept {kept}, K = {Kc} -> {'composite' if Kc >= 4 else 'NO composite (fewer than 4 groups)'}")
with open(os.path.join(HERE, "build", "kept_legs.csv")) as f: bk = [l.strip() for l in f if l.strip()]
print("  builder kept_legs.csv:", bk)

# ---- E3 relaxation scan (information only, outcome-blind): how many groups have a leg passing E1+E2 and median run >= m, builder reading
print("\nINFO: groups with at least one leg passing E1, E2 and median run >= m in both halves (builder reading), m = 5,4,3")
for m in (5, 4, 3):
    ok = [k for k in PRIO if all(x[6] and x[7] and x[5] >= m for x in elig(k, READINGS[0]))]
    print(f"  m={m}: legs {ok} -> groups {len({k[0] for k in ok})}")

# ---- sign audit shares
print("\nSIGN AUDIT: share EASY in 2018-12-03..12-21 and 2020-03-09..03-20")
def share(k, a, b, val):
    idx = [i for i in range(N) if a <= grid[i] <= b]; return sum(V[k][i] == val for i in idx) / len(idx)
for k in PRIO:
    s1, s2 = share(k, date(2018, 12, 3), date(2018, 12, 21), -1), share(k, date(2020, 3, 9), date(2020, 3, 20), -1)
    print(f"  {k}: {s1*100:5.1f}% {s2*100:5.1f}%" + ("  AUDIT" if s1 > 0.5 and s2 > 0.5 else ""))
i0, i1 = gi[date(2020, 3, 9)], gi[date(2020, 3, 20)]
print("  F3 X (2y minus funds, bp) 2020-03-09..03-20:", [L["F3"][0][i] for i in range(i0, i1 + 1)])
print("  F3 MA20, MA50 (bp) on 2020-03-20: %.1f %.1f" % (ma(L["F3"][0], 20, i1), ma(L["F3"][0], 50, i1)))

# ---- lag spot checks
print("\nLAG SPOT CHECKS (value used at the session close -> observation it came from)")
for g in (date(2018, 12, 3), date(2020, 3, 16), date(2022, 6, 17), date(2024, 12, 31)):
    i = gi[g]; print(f"  {g} ({g.strftime('%a')}): WALCL {WAL[0][i]} fresh {WAL[1][i]} | DTWEXBGS {DTW[0][i]} fresh {DTW[1][i]} | DGS2 {DGS2[0][i]}")

# ---- price-only vs adjusted (independent)
print("\nPRICE-ONLY vs ADJUSTED vote differ share (n)")
def etfleg_px(px, sign, num, den=None):
    a = etf_series(px, num)
    if den is None: return [None if x is None else sign * x for x in a[0]], [True] * N
    b = etf_series(px, den); return [None if (x is None or y is None) else sign * x / y for x, y in zip(a[0], b[0])], [True] * N
SPEC = {"C1": (-1, "HYG", None), "C2": (-1, "HYG", "IEI"), "D1": (1, "UUP", None), "D3": (1, "FXY", None), "M1": (1, "GLD", "SLV"), "M2": (-1, "CPER", "GLD"),
        "K1": (-1, "IWM", "SPY"), "K2": (-1, "SPHB", "SPLV"), "K3": (-1, "KRE", "SPY"), "K5": (-1, "ARKK", "QQQ")}
for k, (s, a, b) in SPEC.items():
    va = votes(*etfleg_px(ADJ, s, a, b), False); vr = votes(*etfleg_px(RAW, s, a, b), False)
    m = [i for i in range(N) if va[i] is not None and vr[i] is not None]
    print(f"  {k}: {sum(va[i] != vr[i] for i in m) / len(m) * 100:5.2f}% (n={len(m)})")
