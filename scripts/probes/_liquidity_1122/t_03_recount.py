"""t_03: independent recount of the t_02 headline numbers by a second route (pandas rolling + plain per-event loops, from build_t/turns_*.csv written by the
outcome-blind t_01, the ETF closes and the run-2 setup frames). No new rule, window or statistic; also prints the one reading (R7) whose other form touches a turn."""
import pandas as pd, numpy as np, json
CUT = pd.Timestamp("2024-12-31"); VS, VE = pd.Timestamp("2017-01-18"), pd.Timestamp("2024-09-27")
A = pd.read_csv("build/etf_adj.csv", index_col=0, parse_dates=True); assert A.index.max() <= CUT; g = list(A.index); pos = {d: i for i, d in enumerate(g)}
EP = pd.read_csv("build_r2/p2_ep_frame.csv", parse_dates=["E"]); BO = pd.read_csv("build_r2/p2_breakout_frame.csv", parse_dates=["D"]); assert EP.E.max() <= CUT and BO.D.max() <= CUT
J = json.load(open("build_t/t_02_numbers.json"))["RES"]; ok_all = True
def chk(lab, mine, theirs, tol=1e-9):
    global ok_all; m = (mine == theirs) if isinstance(mine, (int, str)) else abs(mine - theirs) <= tol; ok_all &= bool(m); print(f"  {lab}: recount {mine:.6g} vs t_02 {theirs:.6g} -> {'MATCH' if m else 'MISMATCH'}")
def ext(t, low):
    s = A[t]; r = s.rolling(127, center=True, min_periods=127); m = r.min() if low else r.max(); c = s[s == m].index; out = []
    for d in c:                                  # earliest of equal closes inside its own window
        i = pos[d]; w = s.iloc[i - 63:i + 64]; first = w[w == s.iloc[i]].index[0]
        if first == d: out.append(d)
    return out
for rule in ("PRIMARY", "ALTERNATE"):
    print(rule); T = pd.read_csv(f"build_t/turns_{rule}.csv", parse_dates=["date"]); T = T[(T.date >= VS) & (T.date <= VE)]
    for q, d, low in (("Q1", "easing", True), ("Q2", "tightening", False)):
        X = [pos[x] for x in ext("IWM", low)]; tp = [pos[x] for x in T.date[T.dir == d]]; tp = [p for p in tp if p + 21 <= len(g) - 64]
        lags = []
        for p in tp:
            best = min(X, key=lambda x: (abs(p - x), x)); lags.append(p - best)
        hits = [l for l in lags if abs(l) <= 21]; r = J[rule][q]["IWM"]
        chk(f"{q} turns n", len(tp), r["n"]); chk(f"{q} hits", len(hits), r["hits"]); chk(f"{q} median |lag|", float(np.median(np.abs(hits))), r["med_abs_lag"])
        sess = [i for i in range(pos[VS], pos[VE] + 1) if i + 21 <= len(g) - 64]; b = np.mean([min(abs(i - x) for x in X) <= 21 for i in sess]); chk(f"{q} base", float(b), r["base"])
        el = [x for x in X if x - 21 >= pos[VS] and x + 21 <= pos[VE]]; rc = np.mean([any(abs(p - x) <= 21 for p in tp) for x in el]); chk(f"{q} recall", float(rc), r["recall"]); chk(f"{q} recall-eligible n", len(el), r["n_lows"])
        iw = A["IWM"]; f = [iw.iloc[p + 21] / iw.iloc[p] - 1 for p in tp]; chk(f"{q} forward-21 median", float(np.median(f)), r["fwd21"]["med"])
        fb = (iw.shift(-21) / iw - 1).iloc[sess]; chk(f"{q} forward-21 base median", float(fb.median()), r["fwd21"]["base_med"])
    allp = sorted(pos[x] for x in T.date); dirs = {pos[x]: y for x, y in zip(T.date, T.dir)}
    for q, ev, col, covf in (("Q3", EP, "E", lambda d: d <= pd.Timestamp("2024-09-30")), ("Q4", BO, "D", lambda d: (pd.Timestamp("2017-03-01") <= d <= pd.Timestamp("2021-12-31")) or (pd.Timestamp("2022-03-31") <= d <= pd.Timestamp("2024-09-30")))):
        okt = {p: all(covf(g[j]) for j in range(p + 1, p + 21)) for p in allp}; cnt = {"easing": [0, 0], "tightening": [0, 0]}
        for e, w in zip(ev[col].map(pos).values, ev.win.values):
            prev = [p for p in allp if p < e]
            if not prev or e in dirs: continue
            p = prev[-1]
            if 1 <= e - p <= 20 and okt[p]: cnt[dirs[p]][0] += 1; cnt[dirs[p]][1] += int(w)
        r = J[rule][q]
        for d, k in (("easing", "E"), ("tightening", "T")): chk(f"{q} {d} events", cnt[d][0], r[k][2]); chk(f"{q} {d} winners", cnt[d][1], r[k][1])
        chk(f"{q} easing minus tightening", cnt["easing"][1] / cnt["easing"][0] - cnt["tightening"][1] / cnt["tightening"][0], r["diff"])
print("\nALL MATCH" if ok_all else "\nMISMATCH PRESENT")
# R7 other reading: breadth common span from the first CONFIRMED direction (2017-04-03) instead of the first sign (2017-03-28): touches the primary 2017-03-29 tightening turn only
f = pd.read_csv("build_t/frame_PRIMARY_Q2_tightening_IWM_highs.csv", parse_dates=["date"]); x = f[f.date >= pd.Timestamp("2017-04-03")]
print(f"R7 other reading, primary Q2 (e) vs breadth: composite precision {x.hit.mean()*100:.1f}% ({int(x.hit.sum())} of n={len(x)}) vs breadth 32.0% (8 of n=25); as run: 33.3% (8 of n=24). The 2017-03-29 turn: hit={bool(f.hit[f.date == pd.Timestamp('2017-03-29')].iloc[0])}")
