"""r2_05: P2 momentum check (EP events, breakout trades, Amihud stand-alone). Run once after W2/W3. Readings: build_r2/READINGS_before_outcomes.txt. Computes, saves, prints last."""
import pandas as pd, numpy as np, os
O = "build_r2"; CUT = pd.Timestamp("2024-12-31"); SEED = 20261122; HOME = os.path.expanduser("~/apollo_data")
comp = pd.read_csv(f"{O}/composite.csv", index_col=0, parse_dates=True); A = pd.read_csv("build/etf_adj.csv", index_col=0, parse_dates=True); BR = pd.read_csv(f"{O}/breadth.csv", index_col=0, parse_dates=True)
for f in (comp, A, BR): assert f.index.max() <= CUT
grid = A.index; gi = pd.Series(np.arange(len(grid)), grid); ST = comp["state"].reindex(grid)
spy = A["SPY"]; ma50 = spy.rolling(50, min_periods=50).mean(); gap = spy / ma50 - 1; above = spy >= ma50
rv = np.log(spy).diff().rolling(126, min_periods=126).std()
am = BR["amihud20"].reindex(grid); a20, a50 = am.rolling(20, min_periods=20).mean(), am.rolling(50, min_periods=50).mean()
AMI = {"combined rule": (am > a20) & (a20 > a50), "trend rule": (a20 > a50)}; am_ok = a50.notna()
cs = set(l.split("|")[0] for l in open(f"{HOME}/cb702/cb702_sic.psv") if l.rstrip("\n").split("|")[-1] == "CS")
log = []
# ---- EP
ev = pd.read_csv("../_ep_winner_study_1121/build/stage6_minutes/02b_events.tsv.gz", sep="\t", parse_dates=["E"]); n0 = len(ev)
ev = ev[ev.E <= CUT]; assert ev.E.max() <= CUT; log.append(f"EP events read {n0}; after the 2024-12-31 cut {len(ev)}; E {ev.E.min().date()} -> {ev.E.max().date()}")
n1 = len(ev); ev = ev[ev.ticker.isin(cs)]; log.append(f"EP: non-common-stock dropped {n1 - len(ev)} -> {len(ev)}")
pos = np.searchsorted(grid.values, ev.E.values, side="left") - 1   # grid session before E
ev = ev.assign(sp=pos); ev = ev[ev.sp >= 0]; ev["sd"] = grid[ev.sp.values]; ev["state"] = ST.reindex(ev.sd).values
n2 = len(ev); ev = ev[ev.state.notna()]; log.append(f"EP: events with no state at the close before E dropped {n2 - len(ev)} -> {len(ev)}; big winners {int(ev.big_winner.sum())} ({ev.big_winner.mean()*100:.1f}%, n={len(ev)})")
ev["win"] = ev.big_winner.astype(int); ev["blk"] = ev.E.dt.to_period("M").astype(str); ev["erak"] = ev.era
# ---- breakout
fr = []
for nm, p in (("pre", f"{HOME}/cb702_pre/out/trades_pre_exitpb.tsv.gz"), ("disc", f"{HOME}/cb702/out/trades_discovery_exitpb.tsv.gz")):
    t = pd.read_csv(p, sep="\t", usecols=["ticker", "D", "E", "K", "entry", "arm", "C0", "mature", "realized_r", "sessions_held", "exit_session"], parse_dates=["D", "E"], low_memory=False)
    m0 = len(t); t = t[t.D <= CUT]; assert t.D.max() <= CUT; log.append(f"breakout {nm}: rows read {m0}; after the D <= 2024-12-31 cut {len(t)}")
    t = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1) & (t.mature == 1)]; log.append(f"breakout {nm}: filter pp / orh5 / tl / C0=1 / mature=1 -> {len(t)}")
    t["erak"] = nm; fr.append(t)
bt = pd.concat(fr); bt = bt[bt.D <= pd.Timestamp("2024-09-30")]; log.append(f"breakout: D <= 2024-09-30 -> {len(bt)}")
ei = gi.reindex(bt.E).values; hold = np.fmax(pd.to_numeric(bt.exit_session, errors="coerce").values, pd.to_numeric(bt.sessions_held, errors="coerce").values)
xi = ei + hold + 1; bad = ~(xi <= len(grid) - 1)   # NaN (E off grid / after cut, or no hold count) or past the grid end
log.append(f"breakout: exit session after 2024-12-31 or not computable, dropped {int(bad.sum())} (E not on the cut grid {int(np.isnan(ei).sum())}, no hold count {int(np.isnan(hold).sum())}) -> {int((~bad).sum())}")
bt = bt[~bad].copy(); bt["sd"] = bt.D; bt["state"] = ST.reindex(bt.D).values; m1 = len(bt); bt = bt[bt.state.notna()]; log.append(f"breakout: no state on D dropped {m1 - len(bt)} -> {len(bt)}; D {bt.D.min().date()} -> {bt.D.max().date()}")
bt["win"] = (bt.realized_r >= 10).astype(int); bt["blk"] = bt.D.dt.to_period("M").astype(str)
log.append(f"breakout: realized_r >= 10: {int(bt.win.sum())} ({bt.win.mean()*100:.2f}%, n={len(bt)})")
def shares(d, flag):
    a, b = d.win[flag], d.win[~flag]; pa = a.mean() if len(a) else np.nan; pb = b.mean() if len(b) else np.nan
    return pa, pb, len(a), len(b), int(a.sum()), int(b.sum())
def boot(d, flag):
    g = pd.DataFrame({"b": d.blk.values, "dn": flag.astype(int), "dw": flag * d.win.values, "on": (~flag).astype(int), "ow": (~flag) * d.win.values}).groupby("b").sum().values
    rng = np.random.default_rng(SEED); idx = rng.integers(0, len(g), (10000, len(g))); s = g[idx].sum(axis=1); ok = (s[:, 0] > 0) & (s[:, 2] > 0)
    df = s[ok, 1] / s[ok, 0] - s[ok, 3] / s[ok, 2]; return np.percentile(df, 2.5), np.percentile(df, 97.5), int((~ok).sum()), len(g)
def strat(d, flag, mask, pooled_gap):
    res = []; okall = True
    for lab, m in (("in", mask), ("out", ~mask)):
        pa, pb, na, nb, wa, wb = shares(d[m], flag[m])
        ct = (na == 0 or nb == 0); good = (not ct) and (pa < pb) and ((pb - pa) >= 0.5 * pooled_gap) and pooled_gap > 0
        res.append((lab, pa, pb, na, nb, ct, good)); okall &= good
    return res, okall
def run(d, name):
    R = {"name": name}; flag = (d.state == "D").values
    pa, pb, na, nb, wa, wb = shares(d, flag); R["main"] = (pa, pb, na, nb, wa, wb); pg = pb - pa
    R["boot"] = boot(d, flag)
    R["era"] = {e: shares(d[d.erak == e], flag[(d.erak == e).values]) for e in sorted(d.erak.unique())}
    ab = above.reindex(d.sd).values.astype(bool); R["spy"] = strat(d, flag, ab, pg)
    s0, s1 = d.sd.min(), d.sd.max(); span = grid[(grid >= max(s0, ST.first_valid_index())) & (grid <= s1)]
    k = int((ST.loc[span] == "D").sum()); b1days = gap.loc[span].sort_values(kind="mergesort").index[:k]; b1 = d.sd.isin(b1days).values
    R["b1"] = (shares(d, b1), k, len(span))
    v = rv.loc[span]; thr = v.quantile(2 / 3); top = (rv.reindex(d.sd).values > thr); R["vol"] = strat(d, flag, top, pg); R["volthr"] = (float(thr), int(top.sum()))
    R["ami"] = {}
    for lab, f in AMI.items():
        okm = am_ok.reindex(d.sd).values.astype(bool); tf = f.reindex(d.sd).values.astype(bool); R["ami"][lab] = shares(d[okm], tf[okm])
    return R
RES = [run(ev, "EP (big_winner share)"), run(bt, "Breakout (share with realized R >= 10)")]
ev[["era", "ticker", "E", "sd", "state", "win"]].to_csv(f"{O}/p2_ep_frame.csv", index=False); bt[["erak", "ticker", "D", "E", "state", "win", "realized_r"]].to_csv(f"{O}/p2_breakout_frame.csv", index=False)
# secondary R (never judged)
rows = pd.read_csv("../_ep_winner_study_1121/build/stage6_minutes/02b_rows.tsv.gz", sep="\t", parse_dates=["E"], low_memory=False); rows = rows[rows.E <= CUT]; assert rows.E.max() <= CUT
rows = rows[(rows["mode"] == "PRIMARY") & (rows.entered.astype(str).isin(["1", "True", "1.0"]))].merge(ev[["ticker", "E", "state"]], on=["ticker", "E"]); rows["R"] = pd.to_numeric(rows.R, errors="coerce")
SEC = rows.dropna(subset=["R"]).assign(dr=lambda x: np.where(x.state == "D", "Draining", "rest")).groupby(["arm", "dr"])["R"].agg(["mean", "median", "size"])
# ---------------- print ----------------
P = print; pc = lambda x: "n/a" if x != x else f"{x*100:.2f}%"
P("\n".join(log))
def line(s): pa, pb, na, nb, wa, wb = s; return f"{pc(pa)} ({wa} of n={na}) vs {pc(pb)} ({wb} of n={nb})" + (f", ratio {pa/pb:.2f}" if pb and pb == pb and pb > 0 and pa == pa else "")
for R in RES:
    P(f"\nP2 {R['name']}: Draining vs rest")
    pa, pb, na, nb, wa, wb = R["main"]; ratio = pa / pb
    ct = wa < 40; c2 = pa <= (2 / 3) * pb; lo, hi, dr, nbk = R["boot"]; c3 = hi < 0
    P(f"  main: {line(R['main'])}")
    P(f"  (1) big winners in Draining: {wa} (floor 40) -> {'ok' if not ct else 'CANNOT TELL'}")
    P(f"  (2) Draining share at most two-thirds of the rest: ratio {ratio:.2f} vs <= 0.67 -> {'PASS' if c2 else 'FAIL'}")
    P(f"  (3) month-block bootstrap ({nbk} months, 10,000 resamples, {dr} dropped): 95% interval of the difference {lo*100:+.2f} to {hi*100:+.2f} points; must exclude 0 on the low side -> {'PASS' if c3 else 'FAIL'}")
    c4 = True
    for e, s in R["era"].items(): good = s[2] > 0 and s[3] > 0 and s[0] < s[1]; c4 &= good; P(f"  (4) era {e}: {line(s)} -> {'lower in Draining' if good else 'NOT lower'}")
    res, c5 = R["spy"]
    for lab, a, b, na_, nb_, ctt, good in res: P(f"  (5) SPY {'at or above' if lab == 'in' else 'below'} its 50-day: {pc(a)} (n={na_}) vs {pc(b)} (n={nb_}); needs lower and gap >= {0.5*(pb-pa)*100:.2f} points -> {'ok' if good else ('cannot tell' if ctt else 'no')}")
    s, k, sp = R["b1"]; b1r = s[0] / s[1] if s[1] > 0 else np.nan; c6 = ratio < b1r
    P(f"  (6) k-matched SPY-trend flag (k={k} of {sp} sessions): {line(s)} -> composite ratio {ratio:.2f} {'<' if c6 else '>='} baseline {b1r:.2f}: {'PASS' if c6 else 'FAIL'}")
    res, c7 = R["vol"]
    for lab, a, b, na_, nb_, ctt, good in res: P(f"  (7) SPY 126-session volatility {'top third' if lab == 'in' else 'lower two-thirds'}: {pc(a)} (n={na_}) vs {pc(b)} (n={nb_}) -> {'ok' if good else ('cannot tell' if ctt else 'no')}")
    verdict = "CANNOT TELL" if ct else ("PASS" if (c2 and c3 and c4 and c5 and c6 and c7) else "FAIL")
    P(f"  P2 {R['name'].split()[0]}: {verdict}" + ("" if not ct else f" (and parts failing regardless: {[n for n, c in (('2',c2),('3',c3),('4',c4),('5',c5),('6',c6),('7',c7)) if not c]})"))
    for lab, s in R["ami"].items(): P(f"  Amihud stand-alone [{lab}], tight vs not (reported, not judged): {line(s)}")
P("\nsecondary, never judged: EP replay R, mode PRIMARY, entered rows, by opening-range arm (minutes)"); P(SEC.round(3).to_string())
