"""t_02: §13.1 turning-point test — the ONE outcome run. Computes everything, saves frames to build_t/, prints last.

READINGS FIXED BEFORE ANY OUTCOME WAS OPENED (t_01 / t_01b are outcome-blind; this header was written before the first run):
 R1  Turn rule, composite / leg / baseline: t_00_lib.turns (every frozen count and chance share reproduced in t_01 / t_01b).
 R2  Fed-and-money channel turn = sign(MA20 - MA50 of the channel score) (the reading that reproduces the doc's 25 / 24; sign-of-score gives 16 / 16).
 R3  Low: close == min(closes t-63..t+63), full window inside the grid, earliest of equal closes. High mirrors. Nearest low: smallest |lag|, earlier on ties. Hit: |lag| <= 21.
 R4  Edge censoring (literal, "dropped from Q1/Q2"): a turn or base session at pos p with p+21 > 2200 (2024-10-01, last pos that can hold a low) is dropped from EVERY Q1/Q2 part
     incl. the forward-return part; the uncensored return base is printed beside it. Recall counts lows with l-21 >= window start and l+21 <= window end.
 R5  Floor "at least 6 lows in the window": counted on recall-eligible lows (harder), plain in-window count printed too.
 R6  "Beats the shift null" = strictly above the percentile (numpy linear interpolation) of the shifted values; primary 95th, alternate 97.5th. Offsets 126..n-126 inclusive.
     Shift = window position + offset, modulo n; every turn (both directions) is shifted together; all drops and the event assignment are redone per offset.
 R7  Baseline common span: starts at the first session the baseline's trend sign exists (literal). Composite turns before it are dropped for that comparison only.
     The first-confirmed-direction date is printed; composite turns between the two are counted.
 R8  Baseline comparison: precision >= baseline precision (0 if it has no turn/hit); median |lag| among hits <= baseline's (a baseline with zero hits is beaten on lag).
 R9  Setup events: build_r2/p2_ep_frame.csv and p2_breakout_frame.csv (run-2 §5.5 frames, already cut, filtered and dropped; no raw file is reopened). Event date EP E, breakout D.
     An event belongs to the last turn strictly before it, if 1..20 grid sessions after it. An event dated ON a turn date belongs to no turn (literal).
 R10 Coverage drop: a turn is dropped from a setup when any of sessions t+1..t+20 is outside that setup's covered dates.
     EP covered: <= 2024-09-30. Breakout covered: 2017-03-01 -> 2021-12-31 and 2022-03-31 -> 2024-09-30. The front edge (before 2017-03-01) is not named in the doc's
     parenthesis but falls under its rule "not fully covered by a setup file"; it touches no primary turn and one alternate turn (2017-02-01): both readings are printed for the alternate.
 R11 "All events" base: reading A = every frame event dated inside the validation window; reading B = reading A minus events dated inside a dropped turn's 20-session window
     and (breakout) nothing else. Both printed; the bar is judged on the HARDER (larger) base.
 R12 Halves: a turn belongs to the half holding its date (H1 <= 2020-12-31); its events go with it. "Same direction in both halves" = easing share > tightening share in each.
 R13 Turn-cluster bootstrap: easing turns and tightening turns resampled separately with replacement (each with its events, zero-event turns included), pooled over halves,
     10,000 draws, numpy default_rng(20261122); a draw with no event in either class is dropped and counted; interval = 2.5th..97.5th percentile of easing minus tightening share.
 R14 Baseline setup statistic = easing-window share minus tightening-window share, on the common span (R7).
 R15 60/63-session figures, +/-63 proximity, SPY, legs, Fed channel, paired lags: reported only, never judged.
 R16 Floors: >= 8 turns per direction per half and 16 pooled (after edge / coverage drops); >= 40 big winners in each of the easing- and tightening-window classes.
"""
import pandas as pd, numpy as np, json, os
from t_00_lib import *
SEED = 20261122
comp = pd.read_csv(f"{O}/composite.csv", index_col=0, parse_dates=True); V = pd.read_csv(f"{O}/legs_votes.csv", index_col=0, parse_dates=True)
A = pd.read_csv("build/etf_adj.csv", index_col=0, parse_dates=True); BR = pd.read_csv(f"{O}/breadth.csv", index_col=0, parse_dates=True)
vx = pd.read_csv("fred/VIXCLS.csv"); vx.columns = ["d", "v"]; vx["d"] = pd.to_datetime(vx.d); vx["v"] = pd.to_numeric(vx.v, errors="coerce"); vx = vx[vx.d <= CUT]
EP = pd.read_csv(f"{O}/p2_ep_frame.csv", parse_dates=["E", "sd"]); BO = pd.read_csv(f"{O}/p2_breakout_frame.csv", parse_dates=["D", "E"])
EP = EP[EP.E <= CUT]; BO = BO[(BO.D <= CUT) & (BO.E <= CUT)]
for f in (comp, V, A, BR): assert f.index.max() <= CUT
assert vx.d.max() <= CUT and EP.E.max() <= CUT and EP.sd.max() <= CUT and BO.D.max() <= CUT and BO.E.max() <= CUT
grid = A.index; assert len(grid) == 2264 and (grid == V.index).all()
vs, ve = grid.get_loc(VS), grid.get_loc(VE); n = ve - vs + 1; assert n == 1937
G = len(grid); LASTLOW = G - 1 - 63; H1POS = int(np.searchsorted(grid.values, np.datetime64(H1END), side="right")) - 1   # last H1 position
gi = pd.Series(np.arange(G), grid)
assert EP.E.isin(grid).all() and BO.D.isin(grid).all()
S = comp["S"].reindex(grid); VIX = vx.dropna().set_index("d")["v"].reindex(grid).ffill(); B3 = BR["B3"].reindex(grid)
PX = {t: A[t].values.astype(float) for t in ("IWM", "SPY")}

# ---------- turn lists ----------
def tl(s):
    t, c, first = turns(s); cv = c.values; fc = None; run = 0
    for i in range(G):
        if np.isnan(cv[i]): continue
        run = run + 1 if (i > 0 and cv[i] == cv[i - 1]) else 1
        if run == 5: fc = i; break
    return dict(all=t, win=[(i, d) for i, d in t if vs <= i <= ve], first_sign=first, first_conf=fc)
T = {"PRIMARY": tl(sign_series(ma(S, 20) - ma(S, 50))), "ALTERNATE": tl(sign_series(S - ma(S, 20)))}
BASE = {"SPY": tl(sign_series(ma(-A["SPY"], 20) - ma(-A["SPY"], 50))), "IWM": tl(sign_series(ma(-A["IWM"], 20) - ma(-A["IWM"], 50))),
        "VIX": tl(sign_series(ma(VIX, 20) - ma(VIX, 50))), "breadth": tl(sign_series(ma(-B3, 20) - ma(-B3, 50)))}
LEG = {k: tl(sign_series(V[k])) for k in KEPT}; Fc = comp["Fed and money"].reindex(grid); LEG["Fed channel"] = tl(sign_series(ma(Fc, 20) - ma(Fc, 50)))
assert (len([1 for i, d in T["PRIMARY"]["win"] if d < 0]), len([1 for i, d in T["PRIMARY"]["win"] if d > 0])) == (24, 24)
assert (len([1 for i, d in T["ALTERNATE"]["win"] if d < 0]), len([1 for i, d in T["ALTERNATE"]["win"] if d > 0])) == (38, 37)

# ---------- index outcomes ----------
def extrema(a, low=True):
    x = a if low else -a; out = []
    for i in range(63, G - 63):
        w = x[i - 63:i + 64]
        if int(np.argmin(w)) == 63: out.append(i)     # argmin returns the earliest of equal closes
    return np.array(out)
EXT = {(t, k): extrema(PX[t], k == "low") for t in PX for k in ("low", "high")}
def nearest(p, ex):
    d = np.abs(ex - p); j = int(np.argmin(d)); return int(ex[j]), int(p - ex[j])     # argmin -> earlier extremum on equal distance
def fwd(a, p, h): return a[p + h] / a[p] - 1 if p + h < G else np.nan
def dd63(a, p): return a[p + 1:p + 64].min() / a[p] - 1 if p + 63 < G else np.nan
BASEPOS = np.arange(vs, ve + 1); BASEC = BASEPOS[BASEPOS + 21 <= LASTLOW]          # edge-censored base sessions
def half(p): return "H1" if p <= H1POS else "H2"
def prox(pos, ex):
    """pos: turn positions (already censored). returns hits flags, signed lags, nearest extremum."""
    if len(pos) == 0: return np.array([], bool), np.array([], int), np.array([], int)
    r = [nearest(p, ex) for p in pos]; lag = np.array([x[1] for x in r]); return np.abs(lag) <= 21, lag, np.array([x[0] for x in r])
def base_share(ex, sess):
    return np.array([np.abs(ex - p).min() <= 21 for p in sess])
def recall(pos, ex):
    el = ex[(ex - 21 >= vs) & (ex + 21 <= ve)]
    if len(el) == 0: return np.nan, 0, 0
    hit = np.array([len(pos) > 0 and np.abs(np.asarray(pos) - l).min() <= 21 for l in el]); return hit.mean(), int(hit.sum()), len(el)
def shifted(pos, off): return vs + (np.asarray(pos, int) - vs + off) % n
OFFS = np.arange(126, n - 126 + 1)
def q12(lst, d, tkr, kind, pct, span_from=None):
    """Q1 (d=-1 easing, kind=low) or Q2 (d=+1, kind=high) for one turn list. Returns dict."""
    ex = EXT[(tkr, kind)]; a = PX[tkr]
    own = np.array([i for i, x in lst if x == d], int); oth = np.array([i for i, x in lst if x == -d], int)
    if span_from is not None: own = own[own >= span_from]; oth = oth[oth >= span_from]
    n_raw = len(own); keep = own + 21 <= LASTLOW; own_c = own[keep]; oth_c = oth[oth + 21 <= LASTLOW]
    hit, lag, nx = prox(own_c, ex); bs = base_share(ex, BASEC); R = dict(n_turns=n_raw, n_censored=int((~keep).sum()), n=len(own_c), hits=int(hit.sum()))
    R["precision"] = hit.mean() if len(hit) else np.nan; R["base"] = bs.mean(); R["n_base"] = len(BASEC)
    R["recall"], R["recall_hits"], R["n_lows"] = recall(own_c, ex); R["n_lows_in_window"] = int(((ex >= vs) & (ex <= ve)).sum())
    R["distinct_hit"] = int(len(set(nx[hit]))) if len(hit) else 0
    R["med_abs_lag"] = float(np.median(np.abs(lag[hit]))) if hit.any() else np.nan; R["med_signed_lag"] = float(np.median(lag[hit])) if hit.any() else np.nan
    R["lags_hits"] = [int(x) for x in lag[hit]] if len(hit) else []
    R["half"] = {}
    for h in ("H1", "H2"):
        m = np.array([half(p) == h for p in own_c], bool); mb = np.array([half(p) == h for p in BASEC])
        R["half"][h] = dict(n=int(m.sum()), hits=int(hit[m].sum()) if len(hit) else 0, precision=(hit[m].mean() if m.sum() else np.nan), base=bs[mb].mean(), n_base=int(mb.sum()))
    f21 = np.array([fwd(a, p, 21) for p in own_c]); b21 = np.array([fwd(a, p, 21) for p in BASEC]); b21u = np.array([fwd(a, p, 21) for p in BASEPOS])
    R["fwd21"] = dict(med=float(np.median(f21)) if len(f21) else np.nan, mean=float(np.mean(f21)) if len(f21) else np.nan, base_med=float(np.median(b21)), base_mean=float(np.mean(b21)), base_med_uncensored=float(np.median(b21u)))
    f63 = np.array([fwd(a, p, 63) for p in own_c]); b63 = np.array([fwd(a, p, 63) for p in BASEPOS])
    R["fwd63"] = dict(med=float(np.median(f63)) if len(f63) else np.nan, base_med=float(np.median(b63)))
    ddv = np.array([dd63(a, p) for p in own_c]) <= -0.10; ddb = np.array([dd63(a, p) for p in BASEPOS]) <= -0.10
    R["dd63"] = dict(share=float(ddv.mean()) if len(ddv) else np.nan, n=len(ddv), base=float(ddb.mean()), n_base=len(ddb))
    ho, _, _ = prox(oth_c, ex); R["other_dir"] = dict(precision=(ho.mean() if len(ho) else np.nan), hits=int(ho.sum()), n=len(ho))
    # +/-63 proximity, reported only
    R["within63"] = float((np.abs(lag) <= 63).mean()) if len(lag) else np.nan
    # shift null (precision and recall of the own-direction turns)
    sp, sr = [], []
    for off in OFFS:
        q = shifted(own, off); q = q[q + 21 <= LASTLOW]; h2, _, _ = prox(q, ex); sp.append(h2.mean() if len(h2) else np.nan); sr.append(recall(q, ex)[0])
    sp, sr = np.array(sp), np.array(sr)
    R["null"] = dict(n=len(OFFS), pct=pct, prec_p=float(np.nanpercentile(sp, pct)), prec_med=float(np.nanmedian(sp)), prec_share_ge=float((sp >= R["precision"]).mean()),
                     rec_p=float(np.nanpercentile(sr, pct)), rec_med=float(np.nanmedian(sr)), rec_share_ge=float((sr >= R["recall"]).mean()))
    R["_frame"] = pd.DataFrame({"pos": own_c, "date": grid[own_c], "half": [half(p) for p in own_c], "nearest": grid[nx] if len(nx) else [], "lag": lag, "hit": hit, "fwd21": f21, "fwd63": f63, "dd63_10pct": ddv})
    R["_hitmap"] = {int(x): int(l) for x, l in sorted(zip(nx[hit], lag[hit]), key=lambda z: -abs(z[1]))} if len(hit) else {}   # extremum -> lag of its nearest hitting turn
    return R

# ---------- setup outcomes ----------
EV = {"EP": (gi.reindex(EP.E).values.astype(int), EP.win.values.astype(int)), "breakout": (gi.reindex(BO.D).values.astype(int), BO.win.values.astype(int))}
def covered(setup):
    d = grid
    if setup == "EP": c = np.asarray(d <= pd.Timestamp("2024-09-30"))
    else: c = np.asarray(((d >= pd.Timestamp("2017-03-01")) & (d <= pd.Timestamp("2021-12-31"))) | ((d >= pd.Timestamp("2022-03-31")) & (d <= pd.Timestamp("2024-09-30"))))
    return c
COV = {s: covered(s) for s in EV}; COVNF = {"breakout": np.asarray(((grid <= pd.Timestamp("2021-12-31"))) | ((grid >= pd.Timestamp("2022-03-31")) & (grid <= pd.Timestamp("2024-09-30")))), "EP": COV["EP"]}  # no-front-edge reading
def turn_ok(p, cov, h):
    return (p + h <= G - 1) and bool(cov[p + 1:p + h + 1].all())
def assign(tpos, tdir, setup, h=20, cov=None):
    """per-turn event and winner counts. tpos sorted. returns DataFrame pos, dir, ok, n, w."""
    cov = COV[setup] if cov is None else cov; ep, w = EV[setup]
    j = np.searchsorted(tpos, ep, side="left") - 1; on_turn = np.isin(ep, tpos); valid = (j >= 0) & ~on_turn
    lagv = np.where(valid, ep - tpos[np.clip(j, 0, None)], -1); m = valid & (lagv >= 1) & (lagv <= h)
    nn = np.bincount(j[m], minlength=len(tpos)); ww = np.bincount(j[m], weights=w[m], minlength=len(tpos))
    ok = np.array([turn_ok(p, cov, h) for p in tpos], bool)
    return pd.DataFrame({"pos": tpos, "dir": tdir, "ok": ok, "n": nn, "w": ww.astype(int)}), m, j
def share(df, d):
    x = df[(df.dir == d) & df.ok]; return (x.w.sum() / x.n.sum() if x.n.sum() else np.nan), int(x.w.sum()), int(x.n.sum()), len(x)
def diff_stat(tpos, tdir, setup, h=20, cov=None):
    df, _, _ = assign(tpos, tdir, setup, h, cov); return share(df, -1)[0] - share(df, 1)[0]
def q34(lst, setup, pct, span_from=None, h=20, cov=None, null=True):
    tp = np.array([i for i, d in lst], int); td = np.array([d for i, d in lst], int)
    if span_from is not None: k = tp >= span_from; tp, td = tp[k], td[k]
    df, m, j = assign(tp, td, setup, h, cov); df["date"] = grid[df.pos.values]; df["half"] = [half(p) for p in df.pos]
    R = dict(dropped=[(str(d.date()), "easing" if x < 0 else "tightening") for d, x, o in zip(df.date, df.dir, df.ok) if not o])
    R["E"] = share(df, -1); R["T"] = share(df, 1); R["diff"] = R["E"][0] - R["T"][0]
    ep, w = EV[setup]; inw = (ep >= vs) & (ep <= ve); R["allA"] = (w[inw].mean(), int(w[inw].sum()), int(inw.sum()))
    bad = np.zeros(G, bool)
    for p, o in zip(df.pos, df.ok):
        if not o: bad[p + 1:min(G, p + h + 1)] = True
    inb = inw & ~bad[ep]; R["allB"] = (w[inb].mean(), int(w[inb].sum()), int(inb.sum()))
    R["half"] = {hh: (share(df[df.half == hh], -1), share(df[df.half == hh], 1)) for hh in ("H1", "H2")}
    R["turns_half"] = {hh: (int(((df.half == hh) & (df.dir == -1) & df.ok).sum()), int(((df.half == hh) & (df.dir == 1) & df.ok).sum())) for hh in ("H1", "H2")}
    if null:
        rng = np.random.default_rng(SEED); e = df[(df.dir == -1) & df.ok][["n", "w"]].values; t = df[(df.dir == 1) & df.ok][["n", "w"]].values
        ie = rng.integers(0, len(e), (10000, len(e))); it = rng.integers(0, len(t), (10000, len(t))); se = e[ie].sum(axis=1); st = t[it].sum(axis=1)
        okb = (se[:, 0] > 0) & (st[:, 0] > 0); dv = se[okb, 1] / se[okb, 0] - st[okb, 1] / st[okb, 0]
        R["boot"] = dict(lo=float(np.percentile(dv, 2.5)), hi=float(np.percentile(dv, 97.5)), dropped=int((~okb).sum()))
        sh = []
        for off in OFFS:
            q = shifted(tp, off); o = np.argsort(q, kind="mergesort"); sh.append(diff_stat(q[o], td[o], setup, h, cov))
        sh = np.array(sh); R["null"] = dict(n=len(OFFS), nan=int(np.isnan(sh).sum()), pct=pct, p=float(np.nanpercentile(sh, pct)), med=float(np.nanmedian(sh)), share_ge=float(np.nanmean(sh >= R["diff"])))
    R["_frame"] = df
    return R

# ---------- run everything ----------
RES = {}
for rule, pct in (("PRIMARY", 95), ("ALTERNATE", 97.5)):
    lst = T[rule]["win"]; r = RES[rule] = {}
    for q, d, kind in (("Q1", -1, "low"), ("Q2", 1, "high")):
        r[q] = {tk: q12(lst, d, tk, kind, pct) for tk in ("IWM", "SPY")}
        r[q]["base"] = {}
        for bn, b in BASE.items():
            sf = b["first_sign"]; br = q12(b["win"], d, "IWM", kind, pct); cr = q12(lst, d, "IWM", kind, pct, span_from=sf)
            both = sorted(set(cr["_hitmap"]) & set(br["_hitmap"])); pl = [cr["_hitmap"][x] - br["_hitmap"][x] for x in both]
            r[q]["base"][bn] = dict(b=br, c=cr, span_from=sf, first_conf=b["first_conf"], comp_before_sign=int(sum(1 for i, x in lst if i < sf)), comp_between=int(sum(1 for i, x in lst if sf <= i < (b["first_conf"] or sf))), paired=pl)
    for q, setup in (("Q3", "EP"), ("Q4", "breakout")):
        r[q] = q34(lst, setup, pct); r[q]["h60"] = q34(lst, setup, pct, h=60, null=False)
        r[q]["nofront"] = q34(lst, setup, pct, cov=COVNF[setup]) if setup == "breakout" else None
        r[q]["base"] = {}
        for bn, b in BASE.items():
            sf = b["first_sign"]; r[q]["base"][bn] = dict(b=q34(b["win"], setup, pct, null=False), c=q34(lst, setup, pct, span_from=sf, null=False))
LEGRES = {}
for k, b in LEG.items():
    LEGRES[k] = dict(Q1=q12(b["win"], -1, "IWM", "low", 95), Q2=q12(b["win"], 1, "IWM", "high", 95), EP=q34(b["win"], "EP", 95, null=False), BO=q34(b["win"], "breakout", 95, null=False))

# ---------- save ----------
os.makedirs("build_t", exist_ok=True)
def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)): return [clean(x) for x in o]
    if isinstance(o, (np.floating, float)): return None if o != o else float(o)
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.bool_,)): return bool(o)
    return o
json.dump(clean(dict(RES=RES, LEG=LEGRES)), open("build_t/t_02_numbers.json", "w"), indent=1)
for rule in RES:
    RES[rule]["Q1"]["IWM"]["_frame"].to_csv(f"build_t/frame_{rule}_Q1_easing_IWM_lows.csv", index=False); RES[rule]["Q2"]["IWM"]["_frame"].to_csv(f"build_t/frame_{rule}_Q2_tightening_IWM_highs.csv", index=False)
    RES[rule]["Q3"]["_frame"].to_csv(f"build_t/frame_{rule}_Q3_EP.csv", index=False); RES[rule]["Q4"]["_frame"].to_csv(f"build_t/frame_{rule}_Q4_breakout.csv", index=False)
for (t, k), ex in EXT.items(): pd.DataFrame({"date": grid[ex], "pos": ex, "close": PX[t][ex]}).to_csv(f"build_t/extrema_{t}_{k}.csv", index=False)
for bn, b in BASE.items(): pd.DataFrame({"date": [grid[i] for i, d in b["all"]], "pos": [i for i, d in b["all"]], "dir": ["tightening" if d > 0 else "easing" for i, d in b["all"]]}).to_csv(f"build_t/turns_baseline_{bn}.csv", index=False)

# ---------- print ----------
P = print; pc = lambda x: "n/a" if x is None or x != x else f"{x*100:.1f}%"; pc2 = lambda x: "n/a" if x is None or x != x else f"{x*100:.2f}%"
P(f"grid n={G}; window {VS.date()} -> {VE.date()} n={n}; max dates: ETF {A.index.max().date()}, composite {comp.index.max().date()}, VIX {vx.d.max().date()}, breadth {BR.index.max().date()}, EP E {EP.E.max().date()} (n={len(EP)}), breakout D {BO.D.max().date()} / E {BO.E.max().date()} (n={len(BO)}) -- all asserted <= 2024-12-31")
P(f"base sessions after edge censoring (pos+21 <= {LASTLOW} = {grid[LASTLOW].date()}): {len(BASEC)} of {n}; H1 ends {grid[H1POS].date()}")
for t in ("IWM", "SPY"):
    for k in ("low", "high"):
        ex = EXT[(t, k)]; P(f"{t} 63-session {k}s on the whole grid: {len(ex)} ({grid[ex[0]].date()} -> {grid[ex[-1]].date()}); inside the window {int(((ex>=vs)&(ex<=ve)).sum())}; with +/-21 inside the window (recall-eligible) {int(((ex-21>=vs)&(ex+21<=ve)).sum())}")
P("IWM lows in window: " + ", ".join(str(grid[x].date()) for x in EXT[("IWM", "low")] if vs <= x <= ve))
P("IWM highs in window: " + ", ".join(str(grid[x].date()) for x in EXT[("IWM", "high")] if vs <= x <= ve))
P("\nBASELINE TURNS in the window (same rule; easing = price trend turning up / VIX trend turning down / breadth trend turning up)")
for bn, b in BASE.items():
    e = [i for i, d in b["win"] if d < 0]; g = [i for i, d in b["win"] if d > 0]
    P(f"  {bn}: easing {len(e)} (H1 {sum(half(i)=='H1' for i in e)}, H2 {sum(half(i)=='H2' for i in e)}), tightening {len(g)} (H1 {sum(half(i)=='H1' for i in g)}, H2 {sum(half(i)=='H2' for i in g)}); trend sign exists from {grid[b['first_sign']].date()}, first confirmed direction {grid[b['first_conf']].date()}, first turn {grid[b['all'][0][0]].date()}")
VERD = {}
def show12(rule, q):
    r = RES[rule][q]; x = r["IWM"]; pct = x["null"]["pct"]; own = "easing" if q == "Q1" else "tightening"; oth = "tightening" if q == "Q1" else "easing"; kind = "low" if q == "Q1" else "high"
    P(f"\n{rule} {q}: a{'n' if q=='Q1' else ''} {own} turn marks an IWM {kind} (judged on IWM, +/-21 sessions)")
    P(f"  turns {x['n_turns']} (edge-censored {x['n_censored']}) -> n={x['n']}; per half: H1 {x['half']['H1']['n']}, H2 {x['half']['H2']['n']}; {kind}s inside the window {x['n_lows_in_window']}, recall-eligible {x['n_lows']}")
    fl = x['half']['H1']['n'] >= 8 and x['half']['H2']['n'] >= 8 and x['n'] >= 16 and x['n_lows'] >= 6
    P(f"  floor (>= 8 turns per half, 16 pooled, >= 6 {kind}s): {'met' if fl else 'NOT MET -> cannot tell'}")
    c = {}
    ct_base = x["base"] > 2 / 3
    c["a precision >= 1.5x base"] = x["precision"] >= 1.5 * x["base"]
    P(f"  (a) precision {pc(x['precision'])} ({x['hits']} of n={x['n']}) vs base {pc(x['base'])} (n={x['n_base']} sessions) = {x['precision']/x['base']:.2f}x; bar >= 1.5x -> {'CANNOT TELL (base above 66.7%)' if ct_base else ('PASS' if c['a precision >= 1.5x base'] else 'FAIL')}")
    nl = x["null"]; c["b precision beats shift null"] = x["precision"] > nl["prec_p"]; c["b recall beats shift null"] = x["recall"] > nl["rec_p"]
    P(f"  (b) shift null ({nl['n']} offsets, {pct}th percentile): precision {pc(x['precision'])} vs null {pc(nl['prec_p'])} (null median {pc(nl['prec_med'])}; {pc(nl['prec_share_ge'])} of shifts reach it) -> {'PASS' if c['b precision beats shift null'] else 'FAIL'}")
    P(f"      recall {pc(x['recall'])} ({x['recall_hits']} of n={x['n_lows']} {kind}s; distinct {kind}s hit by a turn {x['distinct_hit']}) vs null {pc(nl['rec_p'])} (null median {pc(nl['rec_med'])}; {pc(nl['rec_share_ge'])} of shifts reach it) -> {'PASS' if c['b recall beats shift null'] else 'FAIL'}")
    hh = x["half"]; c["c precision >= 1.25x base in each half"] = all(hh[h]["n"] > 0 and hh[h]["precision"] >= 1.25 * hh[h]["base"] for h in hh)
    P("  (c) per half: " + " | ".join(f"{h} {pc(hh[h]['precision'])} ({hh[h]['hits']} of n={hh[h]['n']}) vs base {pc(hh[h]['base'])} (n={hh[h]['n_base']}) = {hh[h]['precision']/hh[h]['base']:.2f}x" for h in hh) + f"; bar >= 1.25x in each -> {'PASS' if c['c precision >= 1.25x base in each half'] else 'FAIL'}")
    f = x["fwd21"]; c["d forward 21-session return"] = (f["med"] > f["base_med"]) if q == "Q1" else (f["med"] < f["base_med"])
    P(f"  (d) forward 21-session IWM return after {own} turns: median {f['med']*100:+.2f}% mean {f['mean']*100:+.2f}% (n={x['n']}) vs base median {f['base_med']*100:+.2f}% mean {f['base_mean']*100:+.2f}% (n={x['n_base']}; uncensored base median {f['base_med_uncensored']*100:+.2f}%, n={n}); bar median {'above' if q=='Q1' else 'below'} base -> {'PASS' if c['d forward 21-session return'] else 'FAIL'}")
    okp, okl = True, True
    for bn, y in r["base"].items():
        b, cc = y["b"], y["c"]; bp = 0.0 if b["precision"] != b["precision"] else b["precision"]; p_ok = cc["precision"] >= bp
        l_ok = True if b["hits"] == 0 else (cc["hits"] > 0 and cc["med_abs_lag"] <= b["med_abs_lag"]); okp &= p_ok; okl &= l_ok
        P(f"  (e) vs {bn} same-rule {own} turns [common span from {grid[y['span_from']].date()}; composite turns dropped {x['n_turns'] - cc['n_turns']}]: composite precision {pc(cc['precision'])} ({cc['hits']} of n={cc['n']}) vs {bn} {pc(b['precision'])} ({b['hits']} of n={b['n']}) -> {'ok' if p_ok else 'NO'}; median |lag| among hits {cc['med_abs_lag']:g} vs {b['med_abs_lag']:g} sessions -> {'ok' if l_ok else 'NO'}"
          + f"  [reported: signed median lag {cc['med_signed_lag']:+g} vs {b['med_signed_lag']:+g}; {bn} recall {pc(b['recall'])} of n={b['n_lows']}; {kind}s hit by both n={len(y['paired'])}, median paired lag difference (composite minus {bn}) {np.median(y['paired']) if y['paired'] else float('nan'):+g}; composite turns between first sign and first confirmed direction {y['comp_between']}]")
    c["e precision >= each baseline"] = okp; c["e median |lag| <= each baseline"] = okl
    P(f"      precision >= all four -> {'PASS' if okp else 'FAIL'}; median |lag| <= all four -> {'PASS' if okl else 'FAIL'}")
    o = x["other_dir"]; c["f direction matters"] = x["precision"] > o["precision"]
    P(f"  (f) direction: {own}-turn precision on {kind}s {pc(x['precision'])} (n={x['n']}) vs {oth}-turn precision on {kind}s {pc(o['precision'])} ({o['hits']} of n={o['n']}); bar {own} above {oth} -> {'PASS' if c['f direction matters'] else 'FAIL'}")
    failed = [k for k, v in c.items() if not v]
    v = "CANNOT TELL" if (not fl or ct_base) else ("PASS" if not failed else "FAIL"); VERD[(rule, q)] = (v, failed)
    P(f"  {rule} {q}: {v}" + (f"; parts not met: {failed}" if failed else ""))
    P(f"  reported, not judged: signed lag among hits median {x['med_signed_lag']:+g} sessions (positive = turn after the {kind}), all hit lags {sorted(x['lags_hits'])}; share of {own} turns within +/-63 of a {kind} {pc(x['within63'])} (n={x['n']})")
    P(f"     10% IWM drawdown within 63 sessions after {own} turns: {pc(x['dd63']['share'])} (n={x['dd63']['n']}) vs all window sessions {pc(x['dd63']['base'])} (n={x['dd63']['n_base']}); forward 63-session IWM return median {x['fwd63']['med']*100:+.2f}% vs base {x['fwd63']['base_med']*100:+.2f}% (63-session windows mostly shared with the next turn)")
    s = r["SPY"]; P(f"     SPY: precision {pc(s['precision'])} ({s['hits']} of n={s['n']}) vs base {pc(s['base'])} = {s['precision']/s['base']:.2f}x (null {pct}th pct {pc(s['null']['prec_p'])}); recall {pc(s['recall'])} ({s['recall_hits']} of n={s['n_lows']}; null {pc(s['null']['rec_p'])}); median |lag| {s['med_abs_lag']:g}, signed {s['med_signed_lag']:+g}; forward 21 median {s['fwd21']['med']*100:+.2f}% vs base {s['fwd21']['base_med']*100:+.2f}%; 10% SPY drawdown in 63: {pc(s['dd63']['share'])} (n={s['dd63']['n']}) vs {pc(s['dd63']['base'])}; other-direction precision {pc(s['other_dir']['precision'])} (n={s['other_dir']['n']})")
def show34(rule, q):
    r = RES[rule][q]; setup = "EP" if q == "Q3" else "breakout"; need = 0.03 if q == "Q3" else 0.005; pct = r["null"]["pct"]
    E, Tt = r["E"], r["T"]; P(f"\n{rule} {q}: {setup} big-winner share in the 20 sessions after easing vs tightening turns")
    P(f"  turns dropped for coverage: {r['dropped'] if r['dropped'] else 'none'}; turns left easing {E[3]} (H1 {r['turns_half']['H1'][0]}, H2 {r['turns_half']['H2'][0]}), tightening {Tt[3]} (H1 {r['turns_half']['H1'][1]}, H2 {r['turns_half']['H2'][1]})")
    fl_t = min(r['turns_half']['H1'] + r['turns_half']['H2']) >= 8 and E[3] >= 16 and Tt[3] >= 16; fl_w = E[1] >= 40 and Tt[1] >= 40
    P(f"  floor: turns {'met' if fl_t else 'NOT MET'}; big winners easing-window {E[1]}, tightening-window {Tt[1]} (bar 40 each) -> {'met' if fl_w else 'NOT MET'}{'' if (fl_t and fl_w) else ' -> cannot tell'}")
    aA, aB = r["allA"], r["allB"]; hard = max(aA[0], aB[0]); c = {}
    c["a easing >= 1.25x all"] = E[0] >= 1.25 * hard
    P(f"  (a) easing-window {pc2(E[0])} ({E[1]} of n={E[2]}) vs all window events {pc2(aA[0])} ({aA[1]} of n={aA[2]}) = {E[0]/aA[0]:.2f}x [reading B, events inside dropped-turn windows removed: {pc2(aB[0])} ({aB[1]} of n={aB[2]}) = {E[0]/aB[0]:.2f}x]; bar >= 1.25x -> {'PASS' if c['a easing >= 1.25x all'] else 'FAIL'}" + ("" if (E[0] >= 1.25 * aA[0]) == (E[0] >= 1.25 * aB[0]) else "  ** the two readings DISAGREE **"))
    c["b easing minus tightening gap"] = r["diff"] >= need
    P(f"  (b) tightening-window {pc2(Tt[0])} ({Tt[1]} of n={Tt[2]}); easing minus tightening {r['diff']*100:+.2f} points; bar >= {need*100:g} -> {'PASS' if c['b easing minus tightening gap'] else 'FAIL'}")
    b = r["boot"]; c["c bootstrap excludes 0"] = b["lo"] > 0
    P(f"  (c) turn-cluster bootstrap (10,000 draws, {b['dropped']} dropped): 95% interval {b['lo']*100:+.2f} to {b['hi']*100:+.2f} points; bar excludes 0 (above) -> {'PASS' if c['c bootstrap excludes 0'] else 'FAIL'}")
    hh = r["half"]; c["d same direction both halves"] = all(hh[h][0][0] > hh[h][1][0] for h in hh)
    P("  (d) per half: " + " | ".join(f"{h} easing {pc2(hh[h][0][0])} ({hh[h][0][1]} of n={hh[h][0][2]}) vs tightening {pc2(hh[h][1][0])} ({hh[h][1][1]} of n={hh[h][1][2]})" for h in hh) + f"; bar easing above in each -> {'PASS' if c['d same direction both halves'] else 'FAIL'}")
    nl = r["null"]; c["e beats shift null"] = r["diff"] > nl["p"]
    P(f"  (e) shift null ({nl['n']} offsets, {nl['nan']} not computable, {pct}th percentile): observed {r['diff']*100:+.2f} vs null {nl['p']*100:+.2f} points (null median {nl['med']*100:+.2f}; {pc(nl['share_ge'])} of shifts reach it) -> {'PASS' if c['e beats shift null'] else 'FAIL'}")
    ok = True
    for bn, y in r["base"].items():
        bb, cc = y["b"], y["c"]; g = (cc["diff"] >= bb["diff"]) if bb["diff"] == bb["diff"] else True; ok &= g
        P(f"  (f) vs {bn} same-rule turns: composite (common span) {cc['diff']*100:+.2f} points [easing {pc2(cc['E'][0])} n={cc['E'][2]}, tightening {pc2(cc['T'][0])} n={cc['T'][2]}] vs {bn} {bb['diff']*100:+.2f} points [easing {pc2(bb['E'][0])} ({bb['E'][1]} of n={bb['E'][2]}, {bb['E'][3]} turns), tightening {pc2(bb['T'][0])} ({bb['T'][1]} of n={bb['T'][2]}, {bb['T'][3]} turns)] -> {'ok' if g else 'NO'}")
    c["f >= each baseline"] = ok; P(f"      >= all four -> {'PASS' if ok else 'FAIL'}")
    failed = [k for k, v in c.items() if not v]; v = "CANNOT TELL" if not (fl_t and fl_w) else ("PASS" if not failed else "FAIL"); VERD[(rule, q)] = (v, failed)
    P(f"  {rule} {q}: {v}" + (f"; parts not met: {failed}" if failed else ""))
    h6 = r["h60"]; P(f"  reported, not judged: 60-session window (turns whose 60-session window is not covered dropped: {len(h6['dropped'])}): easing {pc2(h6['E'][0])} ({h6['E'][1]} of n={h6['E'][2]}) vs tightening {pc2(h6['T'][0])} ({h6['T'][1]} of n={h6['T'][2]})")
    if r.get("nofront") is not None:
        nf = r["nofront"]; P(f"  other reading of the breakout front edge (turns before 2017-03-01 kept): dropped {nf['dropped']}; easing {pc2(nf['E'][0])} ({nf['E'][1]} of n={nf['E'][2]}) vs tightening {pc2(nf['T'][0])} ({nf['T'][1]} of n={nf['T'][2]}), diff {nf['diff']*100:+.2f} points, bootstrap {nf['boot']['lo']*100:+.2f} to {nf['boot']['hi']*100:+.2f}, null {nf['null']['p']*100:+.2f}")
for rule in ("PRIMARY", "ALTERNATE"):
    P("\n" + "=" * 30 + f" {rule} " + ("(judged at the 95th percentile)" if rule == "PRIMARY" else "(fast composite turn; shift-null parts judged at the 97.5th percentile)") + " " + "=" * 30)
    g = np.diff([i for i, d in T[rule]["win"]]); P(f"turns in window {len(T[rule]['win'])}; gaps <= 20 sessions {int((g<=20).sum())} of {len(g)}, <= 60 sessions {int((g<=60).sum())} of {len(g)} (the overlap share for every 60/63-session figure)")
    show12(rule, "Q1"); show12(rule, "Q2"); show34(rule, "Q3"); show34(rule, "Q4")
P("\n" + "=" * 30 + " VERDICTS " + "=" * 30)
for k, (v, f) in VERD.items(): P(f"  {k[0]} {k[1]}: {v}" + (f"  (parts not met: {'; '.join(f)})" if f else ""))
P("\n" + "=" * 30 + " LEG AND FED-CHANNEL TURNS (reported, NOT judged; 22 rows = about one 'pass' at 5% by chance) " + "=" * 30)
P("  row: easing turns -> IWM lows: precision (hits of n) / median |lag| / forward-21 median | tightening turns -> IWM highs: same | EP share after easing vs tightening | breakout share after easing vs tightening")
b1, b2 = RES["PRIMARY"]["Q1"]["IWM"], RES["PRIMARY"]["Q2"]["IWM"]
P(f"  base: low within +/-21 {pc(b1['base'])}, high within +/-21 {pc(b2['base'])}, forward-21 median {b1['fwd21']['base_med']*100:+.2f}% (n={b1['n_base']})")
for k, r in LEGRES.items():
    a, b, e, o = r["Q1"], r["Q2"], r["EP"], r["BO"]
    P(f"  {k + ' ' + NAME.get(k, ''):28s} E->low {pc(a['precision'])} ({a['hits']} of n={a['n']}) lag {a['med_abs_lag']:g} fwd {a['fwd21']['med']*100:+.2f}% recall {pc(a['recall'])} | T->high {pc(b['precision'])} ({b['hits']} of n={b['n']}) lag {b['med_abs_lag']:g} fwd {b['fwd21']['med']*100:+.2f}% recall {pc(b['recall'])} | EP {pc2(e['E'][0])} (n={e['E'][2]}) vs {pc2(e['T'][0])} (n={e['T'][2]}) | BO {pc2(o['E'][0])} (n={o['E'][2]}) vs {pc2(o['T'][0])} (n={o['T'][2]})")
