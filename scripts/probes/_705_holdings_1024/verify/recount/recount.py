#!/usr/bin/env python3
"""Independent recount of the #705 HOLDINGS replay (02_replay.py) from the TABLES IT WROTE ONLY:
   trades.tsv.gz, account_his.tsv, market.tsv, account_band.tsv  (+ the timeline's entries.tsv for the F5 clocks, + the two daily exports
   for opens / closes / QQQ / SPY). No import of 02_replay.py / 01_replay.py, no walk, no minute file, no re-run.
   (1) deciding account d3_p33_tspd / cap_30   (2) the readout vs QQQ / SPY and his bar   (3) the beside row without the contradicting fills
   (4) per-trade n / mean R / win   (5) the band (his breakout-only final vs the 200 stored draw finals)   (6) sensitivity: drop best 1 / best 3
"""
import collections, gzip, math, os, re, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPLAY = "/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/replay/"
ENTRIES = "/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/entries.tsv"
EXPORT_A = "/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz"
EXPORT_B = "/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz"
SESS_A = "/Users/alvinfung/apollo_data/cb702_pre_v2/sessions.txt"
PRINTOUT = os.path.join(HERE, "..", "..", "02_replay.txt")
CUT_B = "2024-12-31"                      # era B rows after this are sealed: dropped at read
W0D, W1D = "2020-01-27", "2022-06-14"
DECIDING_ARM, PRIMARY_ARM = "d3_p33_tspd", "p33_s3_t10"

ROWS = []
def rec(claim, printed, mine, ok):
    ROWS.append((claim, printed, mine, "OK" if ok else "MISMATCH"))

# ------------------------------------------------------------------ the printout, parsed
txt = open(PRINTOUT).read().split("\n")
def line(prefix):
    return next(l for l in txt if l.startswith(prefix))

# ------------------------------------------------------------------ the stored tables
T = pd.read_csv(REPLAY + "trades.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
W = T[(T.in_window == "True") & (T.entry_status == "filled")].copy()
for c in ("fill", "stop", "fill_minute", "realized_r", "sessions_held", "eid"):
    W[c] = pd.to_numeric(W[c])
assert not W.duplicated(["eid", "arm"]).any()
need = {"A": set(W[W.era == "A"].ticker) | {"QQQ", "SPY"}, "B": set(W[W.era == "B"].ticker) | {"QQQ", "SPY"}}

# ------------------------------------------------------------------ bars (opens, closes) from the two exports
def load_export(path, keep, cut=None):
    out = []
    for ch in pd.read_csv(path, header=None, names=["tk", "d", "o", "c"], usecols=[0, 1, 2, 5], dtype={"tk": str, "d": str}, chunksize=2_000_000):
        ch = ch[ch.tk.isin(keep)]
        if cut:
            ch = ch[ch.d <= cut]                     # sealed rows leave at read
        out.append(ch)
    return pd.concat(out, ignore_index=True)
bA = load_export(EXPORT_A, need["A"])
bB = load_export(EXPORT_B, need["B"], cut=CUT_B)
sessA = [l.strip() for l in open(SESS_A) if l.strip()]
calB = sorted(set(bB[bB.tk == "SPY"].d))
cal = sorted(set(sessA) | set(calB))
ci = {d: i for i, d in enumerate(cal)}
NC = len(cal)
assert sorted(set(bA[bA.tk == "SPY"].d)) == sessA, "era A sessions != era A SPY dates"
overlapA = [d for d in sessA if d >= calB[0]]; overlapB = [d for d in calB if d <= sessA[-1]]
assert overlapA == overlapB, "the exports' calendars differ on the overlap"
OPEN, CLOSE = {}, {}
for era, b in (("A", bA), ("B", bB)):
    for tk, g in b.groupby("tk"):
        o = np.full(NC, np.nan); c = np.full(NC, np.nan)
        idx = g.d.map(ci).to_numpy()
        o[idx] = g.o.to_numpy(); c[idx] = g.c.to_numpy()
        OPEN[(era, tk)] = o; CLOSE[(era, tk)] = c
w0, w1 = ci[W0D], ci[W1D]
print(f"calendar {cal[0]}..{cal[-1]} ({NC} sessions); window {W0D}..{W1D} = {w1 - w0 + 1} sessions")

# QQQ / SPY: era A through its last session (stitch), era B after; compare the overlap
px = {}
for tk in ("QQQ", "SPY"):
    a, b = CLOSE[("A", tk)].copy(), CLOSE[("B", tk)]
    both = ~np.isnan(a) & ~np.isnan(b)
    dev = float(np.max(np.abs(b[both] / a[both] - 1))) if both.any() else float("nan")
    print(f"{tk}: era A vs era B closes on {both.sum()} overlapping sessions, max rel dev {dev:.5f}")
    a[np.isnan(a)] = b[np.isnan(a)]
    assert not np.isnan(a[w0:w1 + 1]).any()
    px[tk] = a

# ------------------------------------------------------------------ trades -> sim records
def to_records(df):
    recs = []
    for r in df.itertuples():
        e = ci[r.E]
        legs = []
        for lg in r.legs.split(";"):
            s, kind, p, f = lg.split(":"); s = int(s); p = float(p); f = float(f)
            if s == 0:
                order = 3 if kind == "mark" else 2
            elif kind == "trail":
                order = 0
            elif kind in ("partial", "cut", "mark"):
                order = 3
            else:                                         # stop / stop_gap / partial_r: at the open if it IS the open, else inside the day
                o = OPEN[(r.era, r.ticker)][e + s]
                order = 0 if abs(p - o) < 6e-5 else 2
            legs.append((e + s, order, f, p))
        assert abs(sum(l[2] for l in legs) - 1) < 1e-9, (r.ticker, r.E)
        recs.append(dict(eid=int(r.eid), era=r.era, tk=r.ticker, E=r.E, e=e, fm=int(r.fill_minute), fill=r.fill, stop=r.stop, R=r.realized_r,
                         legs=legs, setup=r.setup, status=r.status))
    return recs

def simulate(trs, risk=0.01, cap=0.30, lim=0.30, start=w0):
    byE = collections.defaultdict(list)
    for x in trs:
        byE[x["e"]].append(x)
    last = max([l[0] for x in trs for l in x["legs"]] + [start])
    sched = collections.defaultdict(lambda: ([], [], [], []))
    cash, eq_prev = 1.0, 1.0
    pos, cnt = [], collections.Counter()
    curve, pnl = {}, {}
    peak, dd = 1.0, 0.0
    for i in range(start, last + 1):
        def run(order):
            nonlocal cash
            S = sched.get(i)
            if S is None:
                return
            for p, frac, pxx in S[order]:
                cash += p["sh"] * frac * pxx
                p["rem"] -= frac
                p["proceeds"] += p["sh"] * frac * pxx
        run(0)
        held = collections.defaultdict(float)
        for p in pos:
            held[p["tk"]] += p["sh"] * p["rem"] * p["fill"]
        for x in sorted(byE.get(i, []), key=lambda z: (z["fm"], z["tk"])):
            width = (x["fill"] - x["stop"]) / x["fill"]
            val = eq_prev * min(risk / width, cap)
            room = lim * eq_prev - held[x["tk"]]
            if room <= 1e-12:
                cnt["skipped_stock_limit"] += 1; continue
            if val > room + 1e-12:
                val = room; cnt["trimmed_stock_limit"] += 1
            if val > cash + 1e-12:
                cnt["skipped_no_room"] += 1; continue
            if risk / width >= cap:
                cnt["cap_bound"] += 1
            cash -= val
            p = dict(tk=x["tk"], era=x["era"], sh=val / x["fill"], fill=x["fill"], rem=1.0, lastc=x["fill"], cost=val, proceeds=0.0, eid=x["eid"], R=x["R"])
            held[x["tk"]] += val
            pos.append(p); cnt["entered"] += 1
            for (li, order, frac, pxx) in x["legs"]:
                sched[li][order].append((p, frac, pxx))
        run(2); run(3)
        for p in [p for p in pos if p["rem"] <= 1e-9]:
            pnl[p["eid"]] = (p["proceeds"] - p["cost"], p["R"], p["tk"])
        pos = [p for p in pos if p["rem"] > 1e-9]
        mtm = cash
        for p in pos:
            c = CLOSE[(p["era"], p["tk"])][i]
            if not math.isnan(c):
                p["lastc"] = c
            mtm += p["sh"] * p["rem"] * p["lastc"]
        eq_prev = mtm
        curve[i] = mtm
        peak = max(peak, mtm); dd = max(dd, 1 - mtm / peak)
        sched.pop(i, None)
    assert not pos, "positions left open"
    ye = {}
    for i, v in curve.items():
        ye[cal[i][:4]] = v
    prev, yr = 1.0, {}
    for y in sorted(ye):
        yr[y] = ye[y] / prev - 1; prev = ye[y]
    return dict(final=eq_prev, yearly=yr, dd=dd, cnt=cnt, curve=curve, pnl=pnl, last=last)

# ------------------------------------------------------------------ market stats (own OLS; sample std; rf 0; sqrt 252)
def stats(sim, a=w0, b=w1):
    eq = np.array([sim["curve"].get(i, sim["final"] if i > sim["last"] else 1.0) for i in range(a, b + 1)], dtype=float)
    q, s = px["QQQ"][a:b + 1], px["SPY"][a:b + 1]
    r, qr = eq[1:] / eq[:-1] - 1, q[1:] / q[:-1] - 1
    n = len(r)
    sh = r.mean() / r.std(ddof=1) * math.sqrt(252); qsh = qr.mean() / qr.std(ddof=1) * math.sqrt(252)
    xb, yb = qr.mean(), r.mean()
    sxx = ((qr - xb) ** 2).sum()
    b1 = ((qr - xb) * (r - yb)).sum() / sxx
    b0 = yb - b1 * xb
    sse = ((r - b0 - b1 * qr) ** 2).sum()
    se0 = math.sqrt(sse / (n - 2) * (1 / n + xb ** 2 / sxx))
    d = dict(total=eq[-1] / eq[0] - 1, qqq=q[-1] / q[0] - 1, spy=s[-1] / s[0] - 1, dd=float((eq / np.maximum.accumulate(eq) - 1).min()),
             qdd=float((q / np.maximum.accumulate(q) - 1).min()), sharpe=sh, qsharpe=qsh, beta=b1, alpha=b0 * 252, t=b0 / se0, days=len(eq))
    d["cagr"] = (1 + d["total"]) ** (252 / len(eq)) - 1
    d["pass"] = d["t"] >= 2.0 and d["total"] > d["qqq"] and d["total"] > d["spy"] and sh > qsh
    return d

def fmt(d):
    return (f"total {100*d['total']:+.1f}% (QQQ {100*d['qqq']:+.1f}%, SPY {100*d['spy']:+.1f}%) | CAGR {100*d['cagr']:.1f}% | max DD "
            f"{100*d['dd']:.1f}% (QQQ {100*d['qdd']:.1f}%) | Sharpe {d['sharpe']:.2f} (QQQ {d['qsharpe']:.2f}) | beta {d['beta']:.2f} | "
            f"alpha {100*d['alpha']:+.1f}%/yr, t {d['t']:.2f} | {d['days']} sessions")

# ------------------------------------------------------------------ (1) the deciding account
dec_df = W[W.arm == DECIDING_ARM]
DEC = to_records(dec_df)
sim = simulate(DEC, cap=0.30)
yrs = ", ".join(f"{y} {100*v:.1f}%" for y, v in sorted(sim["yearly"].items()))
mine = f"final {sim['final']:.3f} | {yrs} | max DD {100*sim['dd']:.1f}% | entered {sim['cnt']['entered']}, skipped no room {sim['cnt']['skipped_no_room']}, per-stock limit {sim['cnt']['skipped_stock_limit']} (trimmed {sim['cnt']['trimmed_stock_limit']}), cap-bound {sim['cnt']['cap_bound']}"
pl = line("- deciding (d3_p33_tspd, cap_30) <- DECIDING")
pr = pl.split(": final", 1)[1].rsplit(" | max open", 1)[0].replace("concurrent same stock 2", "").strip(" |")
pr = "final" + pr
pr = re.sub(r"\s*,\s*$", "", pr)
ok = (f"final {sim['final']:.3f}" in pl and yrs in pl and f"max DD {100*sim['dd']:.1f}%" in pl and f"entered {sim['cnt']['entered']}," in pl
      and f"skipped no room {sim['cnt']['skipped_no_room']}," in pl and f"per-stock limit {sim['cnt']['skipped_stock_limit']} (trimmed {sim['cnt']['trimmed_stock_limit']})" in pl
      and f"cap-bound {sim['cnt']['cap_bound']}" in pl)
rec("(1) deciding account d3_p33_tspd cap_30: final / years / maxDD / entered / skipped / cap-bound", pr, mine, ok)
# stored daily curve vs mine
ah = pd.read_csv(REPLAY + "account_his.tsv", sep="\t")
a = ah[ah.config == "deciding"].reset_index(drop=True)
mc = np.array([sim["curve"][i] for i in range(w0, sim["last"] + 1)])
dates_mine = [cal[i] for i in range(w0, sim["last"] + 1)]
same_dates = list(a.date) == dates_mine
dmax = float(np.max(np.abs(a.equity.to_numpy() - mc))) if same_dates else float("nan")
rec("(1b) stored daily curve account_his.tsv 'deciding' vs mine (same dates, max abs equity diff)", f"{len(a)} rows, last {a.equity.iloc[-1]:.6f}",
    f"{len(mc)} rows, last {mc[-1]:.6f}; same dates {same_dates}; max |diff| {dmax:.2e}", same_dates and dmax < 5e-4)
print("deciding account:", mine, "| last leg", cal[sim["last"]], "| max curve diff", dmax)

# ------------------------------------------------------------------ (2) the readout
st = stats(sim)
rl = line("- DECIDING (d3_p33_tspd, cap_30): total")
bl = line("- HIS BAR")
ok = fmt(st) in rl and (("**PASS**" in bl) == st["pass"])
rec("(2) readout total / Sharpe / beta / alpha / t vs QQQ, SPY (own OLS)", rl.split("): ", 1)[1], fmt(st), fmt(st) in rl)
rec("(2b) bar verdict (alpha t>=2, total>QQQ, total>SPY, Sharpe>QQQ's)", "PASS" if "**PASS**" in bl else "FAIL",
    f"{'PASS' if st['pass'] else 'FAIL'} (t {st['t']:.3f}, total {st['total']:.4f} vs {st['qqq']:.4f}/{st['spy']:.4f}, Sharpe {st['sharpe']:.3f} vs {st['qsharpe']:.3f})",
    ("**PASS**" in bl) == st["pass"])
mk = pd.read_csv(REPLAY + "market.tsv", sep="\t")
m = mk[mk.variant == "deciding"].iloc[0]
dm = max(abs(m.total - st["total"]), abs(m.sharpe - st["sharpe"]), abs(m.beta - st["beta"]), abs(m.alpha_ann - st["alpha"]), abs(m.alpha_t - st["t"]))
rec("(2c) stored market.tsv 'deciding' row vs mine (total, Sharpe, beta, alpha, t; max abs diff)", f"total {m.total:.6f} t {m.alpha_t:.6f}",
    f"total {st['total']:.6f} t {st['t']:.6f}; max |diff| {dm:.1e}", dm < 5e-4 and m.verdict == "PASS")
print("readout:", fmt(st))


# ------------------------------------------------------------------ market-series check: QQQ / SPY from era B wherever B has the session (2021-09-27 on)
px_keep = {k: v.copy() for k, v in px.items()}
for tk in ("QQQ", "SPY"):
    b_ = CLOSE[("B", tk)]
    px[tk] = np.where(np.isnan(b_), px_keep[tk], b_)
stB = stats(sim)
print("\nreadout with era B's QQQ / SPY closes preferred in the overlap:", fmt(stB))
rec("(2d) same readout with QQQ / SPY taken from the era-B export for 2021-09-27 on", "(A-first stitch as run)", f"total {100*stB['total']:+.1f}%, QQQ {100*stB['qqq']:+.1f}%, SPY {100*stB['spy']:+.1f}%, Sharpe {stB['sharpe']:.2f}, t {stB['t']:.2f}, bar {'PASS' if stB['pass'] else 'FAIL'}",
    abs(stB["t"] - st["t"]) < 0.02 and stB["pass"] == st["pass"])
px = px_keep

# ------------------------------------------------------------------ (3) without the contradicting fills (F5), rebuilt from entries.tsv clocks
E = pd.read_csv(ENTRIES, sep="\t", dtype=str, keep_default_na=False)[["eid", "first_clock_on_E", "flat_clock_on_E"]]
E["eid"] = E.eid.astype(int)
dm_ = dec_df.copy(); dm_["eid"] = dm_.eid.astype(int)
dm_ = dm_.merge(E, on="eid", how="left")
def clock(mn):
    t = 9 * 60 + 30 + int(mn)
    return f"{t // 60:02d}:{t % 60:02d}"
fc = dm_.fill_minute.map(clock)
before_flat = (dm_.flat_clock_on_E != "") & (fc < dm_.flat_clock_on_E)
after_held = (dm_.first_clock_on_E != "") & (fc > dm_.first_clock_on_E)
bad = set(dm_[before_flat | after_held].eid)
sim2 = simulate([r for r in DEC if r["eid"] not in bad], cap=0.30)
st2 = stats(sim2)
l47 = next(l for l in txt if l.startswith("- deciding config WITHOUT the"))
l47b = txt[txt.index(l47) + 1]
rec("(3a) contradicting fills (fill before a flat full snapshot, or after the first holding snapshot, on E)", "47", f"{len(bad)} (before flat {int(before_flat.sum())}, after held {int(after_held.sum())})", len(bad) == 47)
rec("(3b) deciding config WITHOUT them: total / t / Sharpe", l47b.strip().split(" -> ")[0], fmt(st2),
    fmt(st2) in l47b and f"final {sim2['final']:.3f}" in l47 and f"entered {sim2['cnt']['entered']}," in l47)
print("without 47:", f"final {sim2['final']:.3f}", fmt(st2))

# ------------------------------------------------------------------ (4) per trade
R = dec_df.realized_r.to_numpy()
mine = f"n {len(R)}, mean R {R.mean():+.3f}, win {100*(R>0).mean():.1f}%, median {np.median(R):+.3f}, max {R.max():+.2f}, worst {R.min():+.2f}, sum {R.sum():+.1f}"
pl = next(l for l in txt if re.match(r"\s*all\s+\|\s+205", l))
c = [x.strip() for x in pl.split("|")]
pr = f"n {c[1]}, mean R {c[8]}, win {c[7]}, median {c[9]}, max {c[5]}, worst {c[6]}, sum {c[10]}"
ok = (c[1] == str(len(R)) and c[8] == f"{R.mean():+.3f}" and c[7] == f"{100*(R>0).mean():.1f}%" and c[5] == f"{R.max():+.2f}" and c[6] == f"{R.min():+.2f}")
rec("(4) per-trade, deciding arm, in window, filled (all mature: statuses stopped/stopped_day0/trailed)", pr, mine, ok)
print(mine)

# ------------------------------------------------------------------ (5) the band: his breakout-dated entries alone vs the stored 200 draw finals
bk = [r for r in DEC if r["era"] == "A" and r["setup"] in ("breakout", "both")]
sim_bk = simulate(bk, cap=0.30)
bd = pd.read_csv(REPLAY + "account_band.tsv", sep="\t")
fin = bd.final.to_numpy()
pc = {q: float(np.percentile(fin, q)) for q in (5, 25, 50, 75, 95)}
share = float((fin >= sim_bk["final"]).mean())
bl = line("- his breakout-dated entries alone")
mine = (f"his final {sim_bk['final']:.3f} ({len(bk)} filled); band n {len(fin)} p5 {pc[5]:.3f} / p25 {pc[25]:.3f} / p50 {pc[50]:.3f} / p75 {pc[75]:.3f} / p95 {pc[95]:.3f}; "
        f"draws >= his {100*share:.1f}% (max draw {fin.max():.3f})")
ok = (f"final {sim_bk['final']:.3f}" in bl and f"p5 {pc[5]:.3f} / p25 {pc[25]:.3f} / p50 {pc[50]:.3f} / p75 {pc[75]:.3f} / p95 {pc[95]:.3f}" in bl
      and f"draws at or above his {100*share:.1f}%" in bl)
rec("(5) band: his breakout-only final vs 200 stored draws (control trades are not stored: draws not re-derivable)", bl.split("alone (n = 212): ")[1][:150], mine, ok)
print(mine)

# ------------------------------------------------------------------ beside parity: the other three stored account curves (a cheap extra)
PRI = to_records(W[W.arm == PRIMARY_ARM])
for name, recs, cap in (("primary_exit_cap30", PRI, 0.30), ("speed_cap20", DEC, 0.20), ("primary_exit_cap20", PRI, 0.20)):
    s_ = simulate(recs, cap=cap)
    a_ = ah[ah.config == name].reset_index(drop=True)
    mc_ = np.array([s_["curve"][i] for i in range(w0, s_["last"] + 1)])
    same = list(a_.date) == [cal[i] for i in range(w0, s_["last"] + 1)]
    d_ = float(np.max(np.abs(a_.equity.to_numpy() - mc_))) if same else float("nan")
    st_ = stats(s_)
    mrow = mk[mk.variant == name].iloc[0]
    rec(f"(extra) beside {name}: final / t vs stored curve + market.tsv", f"last {a_.equity.iloc[-1]:.4f}, t {mrow.alpha_t:.3f}",
        f"final {s_['final']:.4f}, t {st_['t']:.3f}; curve max|diff| {d_:.1e}", same and d_ < 5e-4 and abs(mrow.alpha_t - st_["t"]) < 5e-4)

# ------------------------------------------------------------------ (6) sensitivity
print("\nSENSITIVITY (account re-run without the trades; every later size / room / skip re-decided)")
def row(label, sm):
    s_ = stats(sm)
    return f"{label:<46} final {sm['final']:.3f} | total {100*s_['total']:+6.1f}% | Sharpe {s_['sharpe']:.2f} | alpha {100*s_['alpha']:+5.1f}%/yr | t {s_['t']:.2f} | bar {'PASS' if s_['pass'] else 'FAIL'}", s_
SENS = []
base_line, _ = row("baseline (all 166 entered)", sim)
SENS.append(base_line)
by_pnl = sorted(sim["pnl"].items(), key=lambda kv: -kv[1][0])
by_r = sorted(sim["pnl"].items(), key=lambda kv: -kv[1][1])
id2 = {r["eid"]: r for r in DEC}
def drop(ids, label):
    sm = simulate([r for r in DEC if r["eid"] not in ids], cap=0.30)
    l, s_ = row(label, sm)
    SENS.append(l)
    return s_
print("top 3 by account $ pnl:", [(id2[k]["tk"], id2[k]["E"], f"R {v[1]:+.2f}", f"pnl {100*v[0]:+.1f}% of start") for k, v in by_pnl[:3]])
print("top 3 by realized R (entered):", [(id2[k]["tk"], id2[k]["E"], f"R {v[1]:+.2f}", f"pnl {100*v[0]:+.1f}%") for k, v in by_r[:3]])
allR = sorted(DEC, key=lambda r: -r["R"])[:3]
print("top 3 by realized R (all 205 filled):", [(r["tk"], r["E"], f"R {r['R']:+.2f}", "entered" if r["eid"] in sim["pnl"] else "SKIPPED (no room)") for r in allR])
drop({by_pnl[0][0]}, "drop best 1 (by account $ pnl)")
drop({k for k, _ in by_pnl[:3]}, "drop best 3 (by account $ pnl)")
if by_r[0][0] != by_pnl[0][0]:
    drop({by_r[0][0]}, "drop best 1 (by realized R, entered)")
if {k for k, _ in by_r[:3]} != {k for k, _ in by_pnl[:3]}:
    drop({k for k, _ in by_r[:3]}, "drop best 3 (by realized R, entered)")
for l in SENS:
    print(l)

# ------------------------------------------------------------------ table
print("\n\nclaim | printout | yours | match")
for c_, p_, m_, ok_ in ROWS:
    print(f"{c_} | {p_} | {m_} | {ok_}")
print("\nMISMATCHES:", sum(1 for r in ROWS if r[3] != "OK"), "of", len(ROWS))
