"""t_verify: independent recount of the §13.1 turning-point run (t_02). Own code; reads only build_r2/, build/etf_adj.csv, fred/VIXCLS.csv.
Nothing from build_t/ is used for computing; build_t/t_02_numbers.json is read only at the end to compare."""
import pandas as pd, numpy as np, json, sys
B = "/Users/alvinfung/apollo_the_wise/scripts/probes/_liquidity_1122/"
CUT = pd.Timestamp("2024-12-31")
out = []
def P(*a): s = " ".join(str(x) for x in a); out.append(s); print(s)

V = pd.read_csv(B + "build_r2/legs_votes.csv", index_col=0, parse_dates=True)
C = pd.read_csv(B + "build_r2/composite.csv", index_col=0, parse_dates=True)
A = pd.read_csv(B + "build/etf_adj.csv", index_col=0, parse_dates=True)
BR = pd.read_csv(B + "build_r2/breadth.csv", index_col=0, parse_dates=True)
VX = pd.read_csv(B + "fred/VIXCLS.csv"); VX.columns = ["d", "v"]; VX.d = pd.to_datetime(VX.d)
EP = pd.read_csv(B + "build_r2/p2_ep_frame.csv", parse_dates=["E", "sd"]); BO = pd.read_csv(B + "build_r2/p2_breakout_frame.csv", parse_dates=["D", "E"])
mx = dict(votes=V.index.max(), comp=C.index.max(), etf=A.index.max(), breadth=BR.index.max(), vix_file=VX.d.max(), ep=EP.E.max(), ep_sd=EP.sd.max(), bo_D=BO.D.max(), bo_E=BO.E.max())
P("SEAL: max dates in every input file:", {k: str(v.date()) for k, v in mx.items()}, "->", "OK" if all(v <= CUT for v in mx.values()) else "SEALED ROW PRESENT")
grid = V.index; G = len(grid); assert (A.index == grid).all()
pos = {d: i for i, d in enumerate(grid)}
vs, ve = pos[pd.Timestamp("2017-01-18")], pos[pd.Timestamp("2024-09-27")]; n = ve - vs + 1
h1last = max(i for i, d in enumerate(grid) if d <= pd.Timestamp("2020-12-31"))
P(f"grid {G}, window pos {vs}..{ve} n={n}")

# ---------- own turn rule ----------
def mysign(x):
    x = np.round(np.asarray(x, float), 9); s = np.sign(x); s[np.isnan(x)] = 0; return s   # 0 = carry
def myturns(diff):
    s = mysign(diff); cur = 0; carried = []
    for v in s:
        if v != 0: cur = v
        carried.append(cur)
    conf = 0; runsign = 0; runlen = 0; T = []; first_sign = None
    for i, v in enumerate(carried):
        if v == 0: continue
        if first_sign is None: first_sign = i
        runlen = runlen + 1 if v == runsign else 1; runsign = v
        if runlen == 5:
            if conf == 0: conf = v
            elif v != conf: conf = v; T.append((i, int(v)))
    return T, first_sign
ma = lambda s, w: s.rolling(w, min_periods=w).mean()
S = C["S"].reindex(grid)
LISTS = {"PRIMARY": myturns(ma(S, 20) - ma(S, 50)), "ALTERNATE": myturns(S - ma(S, 20))}
vix = VX.set_index("d")["v"]; vix = pd.to_numeric(vix, errors="coerce").reindex(grid)
vix_ff = vix.ffill()
BASEL = {"SPY": myturns(ma(-A.SPY, 20) - ma(-A.SPY, 50)), "IWM": myturns(ma(-A.IWM, 20) - ma(-A.IWM, 50)),
         "VIX": myturns(ma(vix_ff, 20) - ma(vix_ff, 50)), "breadth": myturns(ma(-BR.B3.reindex(grid), 20) - ma(-BR.B3.reindex(grid), 50))}
vix_noff = myturns(ma(vix, 20) - ma(vix, 50))
win = lambda T: [(i, d) for i, d in T if vs <= i <= ve]
def cnt(T):
    w = win(T); e = [i for i, d in w if d < 0]; t = [i for i, d in w if d > 0]
    return len(e), sum(i <= h1last for i in e), len(t), sum(i <= h1last for i in t)
for k, (T, f) in {**LISTS, **BASEL}.items(): P(f"turns {k}: easing/H1, tightening/H1 = {cnt(T)}; first sign {grid[f].date()}")
P(f"VIX baseline without forward-fill of missing VIX days: {cnt(vix_noff[0])}")
# compare turn dates with t_01 output files (dates only)
for k in ("PRIMARY", "ALTERNATE"):
    f = pd.read_csv(B + f"build_t/turns_{k}.csv"); mine = [str(grid[i].date()) for i, d in LISTS[k][0]]
    P(f"turn dates {k} vs build_t file: {'MATCH' if mine == list(f.date) else 'MISMATCH'} ({len(mine)} turns all-grid)")
for k in BASEL:
    f = pd.read_csv(B + f"build_t/turns_baseline_{k}.csv"); mine = [str(grid[i].date()) for i, d in BASEL[k][0]]
    P(f"turn dates baseline {k} vs build_t file: {'MATCH' if mine == list(f.date) else 'MISMATCH'}")
# look-ahead: MA20/MA50 at t use only S<=t; verify by truncation for a sample of primary turns
la_ok = True
for i, d in LISTS["PRIMARY"][0][::5]:
    St = S.iloc[: i + 1]; T2, _ = myturns(ma(St, 20) - ma(St, 50))
    la_ok &= bool(T2) and T2[-1] == (i, d)
P("look-ahead check (turn recomputed from S truncated at the turn close is identical):", "OK" if la_ok else "FAIL")

# ---------- extrema ----------
def extrema(px, low):
    x = px.values.astype(float); r = []
    for i in range(63, G - 63):
        w = x[i - 63:i + 64]
        if low and w[63] == w.min() and (w[:63] > w[63]).all(): r.append(i)
        if not low and w[63] == w.max() and (w[:63] < w[63]).all(): r.append(i)
    return np.array(r)
EXT = {(t, k): extrema(A[t], k == "low") for t in ("IWM", "SPY") for k in ("low", "high")}
LASTX = G - 1 - 63
for (t, k), e in EXT.items(): P(f"{t} {k}s: in window {((e>=vs)&(e<=ve)).sum()}, recall-eligible {((e-21>=vs)&(e+21<=ve)).sum()}")
IWM = A.IWM.values.astype(float)

def q12(T, d, kind, span=None, tk="IWM"):
    ex = EXT[(tk, kind)]; px = A[tk].values.astype(float)
    own = np.array([i for i, x in win(T) if x == d], int); oth = np.array([i for i, x in win(T) if x == -d], int)
    if span is not None: own = own[own >= span]; oth = oth[oth >= span]
    own = own[own + 21 <= LASTX]; oth = oth[oth + 21 <= LASTX]
    def near(p):
        dd = p - ex; a = np.abs(dd); j = np.where(a == a.min())[0][0]; return dd[j]
    lag = np.array([near(p) for p in own]); hit = np.abs(lag) <= 21
    base = np.arange(vs, ve + 1); base = base[base + 21 <= LASTX]; bh = np.array([np.abs(p - ex).min() <= 21 for p in base])
    el = ex[(ex - 21 >= vs) & (ex + 21 <= ve)]; rec = np.mean([len(own) and np.abs(own - l).min() <= 21 for l in el])
    halves = {}
    for h, m, mb in (("H1", own <= h1last, base <= h1last), ("H2", own > h1last, base > h1last)):
        halves[h] = (hit[m].sum(), m.sum(), hit[m].mean(), bh[mb].mean())
    f = np.median(px[own + 21] / px[own] - 1); fb = np.median(px[base + 21] / px[base] - 1)
    ho = np.array([np.abs(p - ex).min() <= 21 for p in oth])
    return dict(n=len(own), hits=int(hit.sum()), prec=hit.mean(), base=bh.mean(), recall=rec, n_el=len(el), halves=halves,
                lag=np.median(np.abs(lag[hit])) if hit.any() else np.nan, fwd=f, fwdb=fb, oth=ho.mean() if len(ho) else np.nan, own=own)
def shift(p, off): return vs + (np.asarray(p) - vs + off) % n
OFFS = range(126, n - 126 + 1)
def null12(T, d, kind, pct):
    ex = EXT[("IWM", kind)]; own = np.array([i for i, x in win(T) if x == d], int); el = ex[(ex - 21 >= vs) & (ex + 21 <= ve)]
    ps, rs = [], []
    for o in OFFS:
        q = shift(own, o); q = q[q + 21 <= LASTX]
        ps.append(np.mean([np.abs(p - ex).min() <= 21 for p in q])); rs.append(np.mean([np.abs(q - l).min() <= 21 for l in el]))
    return np.percentile(ps, pct), np.percentile(rs, pct)

EVT = {"EP": (np.array([pos[d] for d in EP.E]), EP.win.values), "BO": (np.array([pos[d] for d in BO.D]), BO.win.values)}
def cov(setup):
    if setup == "EP": return np.array(grid <= pd.Timestamp("2024-09-30"))
    return np.array(((grid >= pd.Timestamp("2017-03-01")) & (grid <= pd.Timestamp("2021-12-31"))) | ((grid >= pd.Timestamp("2022-03-31")) & (grid <= pd.Timestamp("2024-09-30"))))
COV = {s: cov(s) for s in EVT}
def q34core(tp, td, setup):
    o = np.argsort(tp, kind="stable"); tp = np.asarray(tp)[o]; td = np.asarray(td)[o]
    ep, w = EVT[setup]; cv = COV[setup]
    ok = np.array([p + 20 < G and cv[p + 1:p + 21].all() for p in tp])
    j = np.searchsorted(tp, ep, side="right") - 1; lagv = ep - tp[np.clip(j, 0, None)]; m = (j >= 0) & (lagv >= 1) & (lagv <= 20)
    nn = np.bincount(j[m], minlength=len(tp)); ww = np.bincount(j[m], weights=w[m], minlength=len(tp)).astype(int)
    per = {i: [nn[i], ww[i]] for i in range(len(tp))}
    rows = [(tp[j], td[j], ok[j], per[j][0], per[j][1]) for j in range(len(tp))]
    return rows
def shr(rows, d, cond=lambda p: True):
    nn = sum(r[3] for r in rows if r[1] == d and r[2] and cond(r[0])); ww = sum(r[4] for r in rows if r[1] == d and r[2] and cond(r[0]))
    return (ww / nn if nn else np.nan), ww, nn
def q34(T, setup, span=None):
    w = win(T); tp = [i for i, d in w if span is None or i >= span]; td = [d for i, d in w if span is None or i >= span]
    rows = q34core(tp, td, setup); E = shr(rows, -1); Tt = shr(rows, 1)
    return rows, E, Tt
def full34(T, setup, pct, need):
    rows, E, Tt = q34(T, setup); diff = E[0] - Tt[0]
    ep, wv = EVT[setup]; inw = (ep >= vs) & (ep <= ve); allsh = wv[inw].mean()
    bad = np.zeros(G, bool)
    for r in rows:
        if not r[2]: bad[r[0] + 1:r[0] + 21] = True
    allB = wv[inw & ~bad[ep]].mean()
    hv = {h: (shr(rows, -1, c)[0], shr(rows, 1, c)[0]) for h, c in (("H1", lambda p: p <= h1last), ("H2", lambda p: p > h1last))}
    rng = np.random.default_rng(20261122)
    e = np.array([(r[3], r[4]) for r in rows if r[1] == -1 and r[2]]); t = np.array([(r[3], r[4]) for r in rows if r[1] == 1 and r[2]])
    ie = rng.integers(0, len(e), (10000, len(e))); it = rng.integers(0, len(t), (10000, len(t)))
    se = e[ie].sum(1); st = t[it].sum(1); k = (se[:, 0] > 0) & (st[:, 0] > 0); dv = se[k, 1] / se[k, 0] - st[k, 1] / st[k, 0]
    lo, hi = np.percentile(dv, [2.5, 97.5])
    tp0 = np.array([i for i, d in win(T)]); td0 = np.array([d for i, d in win(T)]); sh = []
    for o in OFFS:
        rr = q34core(shift(tp0, o), td0, setup); sh.append(shr(rr, -1)[0] - shr(rr, 1)[0])
    nullp = np.nanpercentile(sh, pct)
    bas = {}
    for bn, (bT, bf) in BASEL.items():
        _, be, bt = q34(bT, setup); _, ce, ct = q34(T, setup, span=bf); bas[bn] = (ce[0] - ct[0], be[0] - bt[0])
    floor = E[1] >= 40 and Tt[1] >= 40
    parts = {"a >=1.25x all": E[0] >= 1.25 * max(allsh, allB), "b gap": diff >= need, "c boot": lo > 0,
             "d halves": all(a > b for a, b in hv.values()), "e null": diff > nullp, "f baselines": all(c >= b for c, b in bas.values())}
    return dict(E=E, T=Tt, diff=diff, all=allsh, allB=allB, halves=hv, boot=(lo, hi), null=nullp, bas=bas, floor=floor, parts=parts,
                dropped=[(str(grid[r[0]].date()), r[1]) for r in rows if not r[2]])

ref = json.load(open(B + "build_t/t_02_numbers.json"))["RES"]
mism = []
def cmp(label, mine, theirs, tol=1e-9):
    ok = (mine is None and theirs is None) or (theirs is not None and mine is not None and abs(float(mine) - float(theirs)) <= tol)
    if not ok: mism.append((label, mine, theirs))
    return "=" if ok else f"!= t_02 {theirs}"
VERD = {}
for rule, pct in (("PRIMARY", 95), ("ALTERNATE", 97.5)):
    T = LISTS[rule][0]
    for q, d, kind in (("Q1", -1, "low"), ("Q2", 1, "high")):
        r = q12(T, d, kind); np_, nr = null12(T, d, kind, pct); R = ref[rule][q]["IWM"]
        P(f"\n{rule} {q}: n={r['n']} hits={r['hits']} prec={r['prec']:.4f} [{cmp(rule+q+'prec', r['prec'], R['precision'])}] base={r['base']:.4f} [{cmp(rule+q+'base', r['base'], R['base'])}] recall={r['recall']:.4f} of {r['n_el']} [{cmp(rule+q+'rec', r['recall'], R['recall'])}]")
        P(f"  null{pct}: prec {np_:.4f} [{cmp(rule+q+'np', np_, R['null']['prec_p'])}] recall {nr:.4f} [{cmp(rule+q+'nr', nr, R['null']['rec_p'])}]")
        P(f"  halves: " + "; ".join(f"{h} {a}/{b} {c:.4f} base {e:.4f} [{cmp(rule+q+h, c, R['half'][h]['precision'])}|{cmp(rule+q+h+'b', e, R['half'][h]['base'])}]" for h, (a, b, c, e) in r["halves"].items()))
        P(f"  fwd21 med {r['fwd']:+.5f} [{cmp(rule+q+'f', r['fwd'], R['fwd21']['med'])}] base {r['fwdb']:+.5f} [{cmp(rule+q+'fb', r['fwdb'], R['fwd21']['base_med'])}]; lag med {r['lag']} [{cmp(rule+q+'lag', r['lag'], R['med_abs_lag'])}]; other-dir {r['oth']:.4f} [{cmp(rule+q+'oth', r['oth'], R['other_dir']['precision'])}]")
        bp, bl = True, True
        for bn, (bT, bf) in BASEL.items():
            b = q12(bT, d, kind); c = q12(T, d, kind, span=bf); Rb = ref[rule][q]["base"][bn]
            bprec = 0 if np.isnan(b["prec"]) else b["prec"]; po = c["prec"] >= bprec; lo = True if b["hits"] == 0 else c["lag"] <= b["lag"]; bp &= po; bl &= lo
            P(f"  vs {bn}: comp {c['prec']:.4f} [{cmp(rule+q+bn+'c', c['prec'], Rb['c']['precision'])}] base-rule {b['prec']:.4f} ({b['hits']}/{b['n']}) [{cmp(rule+q+bn+'b', b['prec'], Rb['b']['precision'])}] lag {c['lag']} vs {b['lag']} [{cmp(rule+q+bn+'lb', b['lag'], Rb['b']['med_abs_lag'])}] -> prec {'ok' if po else 'NO'} lag {'ok' if lo else 'NO'}")
        parts = {"a 1.5x": r["prec"] >= 1.5 * r["base"], "b prec null": r["prec"] > np_, "b recall null": r["recall"] > nr,
                 "c halves": all(c >= 1.25 * e for a, b, c, e in r["halves"].values()), "d fwd": (r["fwd"] > r["fwdb"]) if q == "Q1" else (r["fwd"] < r["fwdb"]),
                 "e prec base": bp, "e lag base": bl, "f direction": r["prec"] > r["oth"]}
        fl = all(b >= 8 for a, b, c, e in r["halves"].values()) and r["n"] >= 16 and r["n_el"] >= 6
        v = "CANNOT TELL" if not fl else ("PASS" if all(parts.values()) else "FAIL"); VERD[(rule, q)] = (v, [k for k, x in parts.items() if not x])
        P(f"  -> {v}; failing parts: {VERD[(rule, q)][1]}")
    for q, setup, need in (("Q3", "EP", 0.03), ("Q4", "BO", 0.005)):
        r = full34(T, setup, pct, need); R = ref[rule][q]
        P(f"\n{rule} {q}: dropped {r['dropped']}; easing {r['E'][1]}/{r['E'][2]} {r['E'][0]:.5f} [{cmp(rule+q+'E', r['E'][0], R['E'][0])}] tightening {r['T'][1]}/{r['T'][2]} {r['T'][0]:.5f} [{cmp(rule+q+'T', r['T'][0], R['T'][0])}] all {r['all']:.5f} [{cmp(rule+q+'all', r['all'], R['allA'][0])}] allB {r['allB']:.5f} [{cmp(rule+q+'allB', r['allB'], R['allB'][0])}]")
        P(f"  halves {[(h, round(a, 5), round(b, 5)) for h, (a, b) in r['halves'].items()]}; boot {r['boot'][0]:+.5f}..{r['boot'][1]:+.5f} [{cmp(rule+q+'lo', r['boot'][0], R['boot']['lo'])}|{cmp(rule+q+'hi', r['boot'][1], R['boot']['hi'])}]; null{pct} {r['null']:+.5f} [{cmp(rule+q+'null', r['null'], R['null']['p'])}]")
        P("  baselines (comp on span, baseline): " + "; ".join(f"{bn} {c:+.5f} [{cmp(rule+q+bn+'c', c, R['base'][bn]['c']['diff'])}] vs {b:+.5f} [{cmp(rule+q+bn+'b', b, R['base'][bn]['b']['diff'])}]" for bn, (c, b) in r["bas"].items()))
        v = "CANNOT TELL" if not r["floor"] else ("PASS" if all(r["parts"].values()) else "FAIL"); VERD[(rule, q)] = (v, [k for k, x in r["parts"].items() if not x])
        P(f"  floor {'met' if r['floor'] else 'NOT MET'} -> {v}; failing parts: {VERD[(rule, q)][1]}")
P("\nVERDICTS (own):"); [P(f"  {k}: {v}") for k, v in VERD.items()]
P(f"\nnumeric mismatches vs t_02_numbers.json: {len(mism)}"); [P("  ", m) for m in mism]
open(B + "t_verify_raw.txt", "w").write("\n".join(out) + "\n")

# ---------- sensitivity: events dated ON a turn date ----------
P("\nSENSITIVITY")
for rule in ("PRIMARY", "ALTERNATE"):
    tp = np.array([i for i, d in win(LISTS[rule][0])]); td = np.array([d for i, d in win(LISTS[rule][0])])
    assert all(td[k] != td[k + 1] for k in range(len(td) - 1))
    for setup in ("EP", "BO"):
        ep, w = EVT[setup]; on = np.isin(ep, tp)
        # alternative reading: an on-turn event goes to the PREVIOUS turn if 1..20 sessions after it
        j = np.searchsorted(tp, ep, side="left") - 1; lagv = ep - tp[np.clip(j, 0, None)]; m = (j >= 0) & (lagv >= 1) & (lagv <= 20)
        cv = COV[setup]; ok = np.array([p + 20 < G and cv[p + 1:p + 21].all() for p in tp])
        nn = np.bincount(j[m], minlength=len(tp)); ww = np.bincount(j[m], weights=w[m], minlength=len(tp))
        sE = ww[(td < 0) & ok].sum() / nn[(td < 0) & ok].sum(); sT = ww[(td > 0) & ok].sum() / nn[(td > 0) & ok].sum()
        P(f"  {rule} {setup}: events dated on a turn date {on.sum()} (winners {w[on].sum()}); if they joined the previous turn: easing {sE:.5f} tightening {sT:.5f} diff {(sE-sT)*100:+.2f} pts")
# recall with edge-censored turns kept
for rule in ("PRIMARY", "ALTERNATE"):
    for d, kind in ((-1, "low"), (1, "high")):
        ex = EXT[("IWM", kind)]; el = ex[(ex - 21 >= vs) & (ex + 21 <= ve)]; own = np.array([i for i, x in win(LISTS[rule][0]) if x == d])
        P(f"  {rule} {kind} recall with edge-censored turns kept: {np.mean([np.abs(own - l).min() <= 21 for l in el]):.4f}")
open(B + "t_verify_raw.txt", "w").write("\n".join(out) + "\n")

# ---------- leg and Fed-channel rows (reported, not judged) ----------
L = json.load(open(B + "build_t/t_02_numbers.json"))["LEG"]; lm = 0
Fc = C["Fed and money"].reindex(grid)
LEGT = {k: myturns(V[k]) for k in "M1 F1 F2 R1 D1 K1 C3 R2 K5 M2".split()}; LEGT["Fed channel"] = myturns(ma(Fc, 20) - ma(Fc, 50))
for k, (T, f) in LEGT.items():
    a = q12(T, -1, "low"); b = q12(T, 1, "high"); _, eE, eT = q34(T, "EP"); _, oE, oT = q34(T, "BO"); R = L[k]
    vals = [(a["prec"], R["Q1"]["precision"]), (b["prec"], R["Q2"]["precision"]), (eE[0], R["EP"]["E"][0]), (eT[0], R["EP"]["T"][0]), (oE[0], R["BO"]["E"][0]), (oT[0], R["BO"]["T"][0])]
    bad = [x for x in vals if abs(x[0] - x[1]) > 1e-9]; lm += len(bad)
    P(f"  leg {k}: E->low {a['hits']}/{a['n']} T->high {b['hits']}/{b['n']} EP {eE[0]:.4f} (n={eE[2]}) vs {eT[0]:.4f} (n={eT[2]}) BO {oE[0]:.4f} vs {oT[0]:.4f} -> {'MATCH' if not bad else bad}")
P(f"leg rows mismatches: {lm}")
open(B + "t_verify_raw.txt", "w").write("\n".join(out) + "\n")

# ---------- extra checks (advisor) ----------
P("\nEXTRA")
W = pd.read_csv(B + "build_r2/w2_w3_frame.csv", index_col=0, parse_dates=True)
ig = (ma(A.IWM, 20) / ma(A.IWM, 50) - 1).reindex(W.index); sg = (ma(A.SPY, 20) / ma(A.SPY, 50) - 1).reindex(W.index)
dd = pd.Series([IWM[pos[d] + 1:pos[d] + 64].min() / IWM[pos[d]] - 1 for d in W.index], W.index)
P(f"price bridge vs run-2 w2_w3_frame ({len(W)} rows): max|iwm_gap diff| {np.nanmax(np.abs(ig - W.iwm_gap)):.2e}, max|spy_gap diff| {np.nanmax(np.abs(sg - W.spy_gap)):.2e}, max|vix diff| {np.nanmax(np.abs(vix_ff.reindex(W.index) - W.vix)):.2e}, max|iwm_dd63 diff| {np.nanmax(np.abs(dd - W.iwm_dd63)):.2e}")
DOC = dict(M1=(20, 21), F1=(24, 24), F2=(14, 13), R1=(21, 20), D1=(19, 18), K1=(20, 21), C3=(17, 18), R2=(15, 14), K5=(19, 18), M2=(20, 21))
for k, exp in DOC.items():
    c = cnt(LEGT[k][0]); f = pd.read_csv(B + f"build_t/turns_leg_{k}.csv"); same = [str(grid[i].date()) for i, d in LEGT[k][0]] == list(f.date)
    P(f"  leg {k} window turns E/T {c[0]}/{c[2]} doc {exp} -> {'MATCH' if (c[0], c[2]) == exp else 'MISMATCH'}; dates vs build_t {'MATCH' if same else 'MISMATCH'}")
P(f"  Fed channel MA20/MA50: {cnt(LEGT['Fed channel'][0])[::2]} (doc 25/24); sign of score: {cnt(myturns(Fc)[0])[::2]}")
for rule in ("PRIMARY", "ALTERNATE"):
    w = win(LISTS[rule][0]); g = np.diff([i for i, d in w])
    for d, nm in ((-1, "easing"), (1, "tightening")):
        p = np.array([i for i, x in w if x == d]); near = np.array([np.abs(p - s).min() <= 21 for s in range(vs, ve + 1)]).mean()
        P(f"  {rule} {nm}: chance share {near*100:.1f}%")
    P(f"  {rule} gaps: min {g.min()} median {np.median(g):g} <=20 {(g<=20).sum()} <=60 {(g<=60).sum()} of {len(g)}")
# per-half n and turn floor for Q3/Q4
for rule in ("PRIMARY", "ALTERNATE"):
    for setup in ("EP", "BO"):
        rows, E, Tt = q34(LISTS[rule][0], setup)
        hh = {h: (shr(rows, -1, c)[2], shr(rows, 1, c)[2], sum(1 for r in rows if r[1] == -1 and r[2] and c(r[0])), sum(1 for r in rows if r[1] == 1 and r[2] and c(r[0]))) for h, c in (("H1", lambda p: p <= h1last), ("H2", lambda p: p > h1last))}
        P(f"  {rule} {setup}: per-half events (easing n, tightening n, easing turns, tightening turns) {hh}; turn floor (>=8 per half, >=16 pooled) {'met' if min(min(v[2:]) for v in hh.values()) >= 8 and sum(v[2] for v in hh.values()) >= 16 and sum(v[3] for v in hh.values()) >= 16 else 'NOT MET'}")
# alternate recall null: share of shifts at 100%
for rule, pct in (("PRIMARY", 95), ("ALTERNATE", 97.5)):
    for d, kind in ((-1, "low"), (1, "high")):
        ex = EXT[("IWM", kind)]; el = ex[(ex - 21 >= vs) & (ex + 21 <= ve)]; own = np.array([i for i, x in win(LISTS[rule][0]) if x == d])
        rs = []
        for o in OFFS:
            q = shift(own, o); q = q[q + 21 <= LASTX]; rs.append(np.mean([np.abs(q - l).min() <= 21 for l in el]))
        rs = np.array(rs); P(f"  {rule} recall null on {kind}s: share of shifts at 100% = {(rs == 1).mean()*100:.1f}%; {pct}th pct {np.percentile(rs, pct)*100:.1f}%")
# open readings
cv0 = COV["BO"].copy(); COV["BO"] = np.array(((grid <= pd.Timestamp("2021-12-31"))) | ((grid >= pd.Timestamp("2022-03-31")) & (grid <= pd.Timestamp("2024-09-30"))))
_, E2, T2 = q34(LISTS["ALTERNATE"][0], "BO"); P(f"  breakout front edge not dropped (alternate): diff {(E2[0]-T2[0])*100:+.2f} pts (null 97.5th {0.500:.2f}) "); COV["BO"] = cv0
bfirstconf = None; s_ = mysign(ma(-BR.B3.reindex(grid), 20) - ma(-BR.B3.reindex(grid), 50)); run = 0; prev = 0
for i, v in enumerate(s_):
    if v == 0: continue
    run = run + 1 if v == prev else 1; prev = v
    if run == 5: bfirstconf = i; break
c2 = q12(LISTS["PRIMARY"][0], 1, "high", span=bfirstconf); P(f"  breadth span from first confirmed direction {grid[bfirstconf].date()}: primary Q2 comp precision {c2['prec']*100:.1f}% vs breadth 32.0%")
base = np.arange(vs, ve + 1); P(f"  uncensored base median fwd21 {np.median(IWM[base + 21] / IWM[base] - 1)*100:+.2f}%")
open(B + "t_verify_raw.txt", "w").write("\n".join(out) + "\n")
