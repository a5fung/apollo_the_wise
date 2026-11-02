#!/usr/bin/env python3
"""BLIND VERIFIER of the backward step (BACKWARD_DESIGN.md) that rebuilds the breakout list from Qullamaggie's 269 dated
breakout buys. Written WITHOUT reading backward/12_backward.py; it reads only the builder's OUTPUTS (12_backward.txt,
12_final_rules.json, 12_dropped_buys.tsv) as the claims to check.

Detection only: the two scores are (a) how many of Qullamaggie's buys a list keeps and (b) how many names it holds a night.
No R / P&L / win rate anywhere; trades.tsv.gz is read ONLY for eid/arm/in_window/entry_status/realized_r to name the 26
big winners, exactly as 11_starting_point.py does. Nothing dated 2025+ is read except _mtw_1102/mtw_bars.csv and q1.out."""
import json, math, os, re, sys, datetime as dt
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
BW = f"{BASE}/backward"
DATA = "/Users/alvinfung/apollo_data/qm_breakouts_1102"
REPO = "/Users/alvinfung/apollo_the_wise"
LOG, DISC = [], []
def say(s=""): print(s, flush=True); LOG.append(str(s))
def disc(s): DISC.append(s); say(f"  !! DISCREPANCY: {s}")

COLS = ["scan_date", "E", "ticker", "rs_best", "adr20", "close", "prior_move", "e10", "e21", "hi252", "e21_rise_base",
        "pass_history", "pass_universe", "pass_prior_move", "prior_move.prior_move", "prior_move.base_len",
        "prior_move.pole_high", "prior_move.pole_low", "higher_lows.base_low", "higher_lows.recent_low",
        "surf.run10", "surf.run20", "surf.run50", "surf.best", "tightening.ratio", "tightening.range_recent5",
        "tightening.range_early5", "universe.dollar_vol20", "universe.raw_close"]
F = pd.concat([pd.read_parquet(f"{DATA}/features_era{e}.parquet", columns=COLS) for e in "AB"], ignore_index=True)
codes, nights = pd.factorize(F.scan_date, sort=True)
NN = len(nights)
say("== VERIFY — blind re-derivation of the backward step from Qullamaggie's 269 dated breakout buys")
say(f"table rows {len(F):,} over {NN} nights ({nights[0]} .. {nights[-1]}); no gate_error column in either parquet")
assert nights[-1] < "2025-01-01"
pm_same = np.allclose(F["prior_move"].values, F["prior_move.prior_move"].values, equal_nan=True)
say(f"column prior_move == prior_move.prior_move on every row: {pm_same}")

# ---------------- his buys + big winners (11_starting_point's join, literally) ----------------
Q = pd.read_csv(f"{BASE}/qm_breakouts_v1_gates.tsv.gz", sep="\t", usecols=["eid", "sym", "ticker", "E", "D"])
key = dict(zip(zip(F.ticker, F.scan_date), F.index))
Q["row"] = [key.get((t, d)) for t, d in zip(Q.ticker, Q.D)]
assert Q.row.notna().all() and len(Q) == 269, "join"
Q["row"] = Q.row.astype(int)
dup = F.duplicated(["ticker", "scan_date"]).sum()
say(f"his buys joined {int(Q.row.notna().sum())}/{len(Q)}; duplicate (ticker, night) keys in the table: {dup}")
e_ok = (F.loc[Q.row, "E"].values == Q.E.values).all()
say(f"table E (next session) == his buy date E for all 269: {e_ok}")
T = pd.read_csv("/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/replay/trades.tsv.gz", sep="\t",
                usecols=["eid", "arm", "in_window", "entry_status", "realized_r"])
assert T.in_window.dtype == bool, "in_window must parse as bool"
w = T[(T.arm == "d3_p33_tspd") & (T.in_window == True) & (T.entry_status == "filled")]
big_eids = set(w[w.realized_r >= 5].eid)
Q["big"] = Q.eid.isin(big_eids)
Q["fit"] = Q.E.str[:4].astype(int).between(2017, 2020)
Q["chk"] = Q.E.str[:4].astype(int).between(2021, 2023)
assert (Q.fit ^ Q.chk).all()
say(f"big-winner eids in the replay: {len(big_eids)}; among the 269 buys: {int(Q.big.sum())} | FIT {int(Q.fit.sum())} CHECK {int(Q.chk.sum())}")
NFIT, NCHK, NBIG = int(Q.fit.sum()), int(Q.chk.sum()), int(Q.big.sum())


def names(mask_full_or_sub, cods):
    return np.bincount(cods[mask_full_or_sub], minlength=NN)


def stats(n):
    return float(np.median(n)), float(np.mean(n)), float(np.quantile(n, 0.9))


# ---------------- CHECK 1: S0 ----------------
say("\n== CHECK 1 — S0 (history + universe + strength >= 35 + range >= 2.1% + prior move kept)")
S0 = (F.pass_history.astype(bool) & F.pass_universe.astype(bool) & (F.rs_best >= 35) & (F.adr20 >= 0.021)
      & F.pass_prior_move.astype(bool)).values
n0 = names(S0, codes)
med0, mean0, p90_0 = stats(n0)
hit0 = S0[Q.row.values]
# 11_starting_point's own computation (pandas groupby) as a second route
n0b = pd.Series(S0).groupby(F.scan_date.values).sum()
say(f"S0: his buys {int(hit0.sum())}/269 | big winners {int(hit0[Q.big.values].sum())}/{NBIG} | names a night median {med0:.0f}, "
    f"mean {mean0:.0f}, 90th pct {p90_0:.0f} | rows {int(S0.sum()):,} | groupby route median {n0b.median():.0f} p90 {n0b.quantile(.9):.0f}")
c1 = (hit0.sum() == 269 and hit0[Q.big.values].sum() == 26 and round(med0) == 543 and round(mean0) == 625 and round(p90_0) == 1023)
say(f"CHECK 1 {'PASS' if c1 else 'FAIL'}")
RES = {"c1": (c1, f"S0 {int(hit0.sum())}/269 buys, {int(hit0[Q.big.values].sum())}/26 big, median {med0:.0f} mean {mean0:.0f} p90 {p90_0:.0f}")}

# ---------------- restrict to S0 rows ----------------
G = F.loc[S0].reset_index()          # 'index' = original row
gc = codes[S0]
pos = np.searchsorted(G["index"].values, Q.row.values)
assert (G["index"].values[pos] == Q.row.values).all()
FITp, CHKp, BIGp = pos[Q.fit.values], pos[Q.chk.values], pos[Q.big.values]


def feat_table(df, depth_alt=False):
    """My own feature definitions, from BACKWARD_DESIGN.md's candidate list (dimensionless; inf -> NaN)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        ph, bl, adr, c = df["prior_move.pole_high"].values, df["higher_lows.base_low"].values, df.adr20.values, df.close.values
        depth = (ph - bl) / (adr * c) if depth_alt else (ph - bl) / ph / adr
        X = {"rs_best": df.rs_best.values, "adr20": df.adr20.values, "prior_move": df.prior_move.values,
             "prior_move.base_len": df["prior_move.base_len"].values.astype(float),
             "base_depth_adr": depth,
             "e21_rise_base": df.e21_rise_base.values,
             "close_vs_e10_adr": (c / df.e10.values - 1) / adr,
             "close_vs_e21_adr": (c / df.e21.values - 1) / adr,
             "below_52w_high": 1 - c / df.hi252.values,
             "below_52w_high_adr": (1 - c / df.hi252.values) / adr,
             "recent_low_vs_base_low_adr": (df["higher_lows.recent_low"].values / bl - 1) / adr,
             "surf.run10": df["surf.run10"].values.astype(float), "surf.run20": df["surf.run20"].values.astype(float),
             "surf.run50": df["surf.run50"].values.astype(float), "surf.best": df["surf.best"].values.astype(float),
             "tightening.ratio": df["tightening.ratio"].values,
             "universe.dollar_vol20": df["universe.dollar_vol20"].values,
             "universe.raw_close": df["universe.raw_close"].values,
             # values of v1's tightening gate the builder did not use (design: "tightening ... VALUES")
             "tightening.range_recent5": df["tightening.range_recent5"].values,
             "tightening.range_early5": df["tightening.range_early5"].values}
    return {k: np.where(np.isfinite(v.astype(float)), v.astype(float), np.nan) for k, v in X.items()}


BANDED = {"prior_move.base_len", "base_depth_adr"}
BUILDER_SET = ["rs_best", "adr20", "prior_move", "prior_move.base_len", "base_depth_adr", "e21_rise_base", "close_vs_e10_adr",
               "close_vs_e21_adr", "below_52w_high", "below_52w_high_adr", "recent_low_vs_base_low_adr", "surf.run10",
               "surf.run20", "surf.run50", "surf.best", "tightening.ratio", "universe.dollar_vol20", "universe.raw_close"]
EXTRA = ["tightening.range_recent5", "tightening.range_early5"]


def thresholds(x_fit):
    s = np.sort(x_fit[np.isfinite(x_fit)]); n = len(s)
    k = math.ceil(0.98 * n); k1 = math.ceil(0.99 * n)
    return {"lower": s[n - k], "upper": s[k - 1], "band": (s[n - k1], s[k1 - 1]), "n": n,
            "np_p2": float(np.percentile(s, 2)), "np_p98": float(np.percentile(s, 98))}


def candidates(X, feats):
    out = []
    for f in feats:
        th = thresholds(X[f][FITp])
        x = X[f]
        with np.errstate(invalid="ignore"):
            out.append((f"{f} >= {th['lower']:g}", f, ">=", th["lower"], x >= th["lower"]))
            out.append((f"{f} <= {th['upper']:g}", f, "<=", th["upper"], x <= th["upper"]))
            if f in BANDED:
                lo, hi = th["band"]
                out.append((f"{lo:g} <= {f} <= {hi:g}", f, "band", (lo, hi), (x >= lo) & (x <= hi)))
    return out


def greedy(cands, marginal=True, verbose=False, label=""):
    cur = np.ones(len(G), bool)
    pool = list(cands)
    steps, tables, cum = [], [], 0
    while True:
        n = np.bincount(gc[cur], minlength=NN); cmed, cmean, _ = stats(n)
        rows = []
        for name, f, op, t, m in pool:
            new = cur & m
            ref = cur if marginal else np.ones(len(G), bool)
            mm = new if marginal else m
            fd = int((ref[FITp] & ~mm[FITp]).sum()); cd = int((ref[CHKp] & ~mm[CHKp]).sum()); bd = int((ref[BIGp] & ~mm[BIGp]).sum())
            nn = np.bincount(gc[new], minlength=NN); med, mean, p90 = stats(nn)
            why = []
            if bd > 0: why.append(f"drops {bd} big winner(s)")
            if fd > 3: why.append(f"FIT drop {fd} > 3")
            if med > 0.95 * cmed: why.append(f"median cut {100 * (1 - med / cmed):.1f}% < 5%")
            if cd > 4: why.append(f"CHECK drop {cd} > 4")
            q = not why
            rows.append(dict(name=name, f=f, op=op, t=t, fd=fd, cd=cd, bd=bd, med=med, mean=mean, p90=p90,
                             cut=1 - med / cmed, q=q, why="QUALIFIES" if q else "no: " + "; ".join(why), mask=m))
        tables.append((cmed, cmean, rows))
        ok = [r for r in rows if r["q"]]
        if not ok:
            break
        ok.sort(key=lambda r: (-(cmed - r["med"]), -(cmean - r["mean"]), r["fd"] + r["cd"], r["name"]))
        best = ok[0]
        newcur = cur & best["mask"]
        dropped_pos = [p for p in pos if cur[p] and not newcur[p]]
        cur = newcur; cum += len(dropped_pos)
        pool = [c for c in pool if c[0] != best["name"]]
        steps.append(dict(best, dropped=dropped_pos, cur=cur.copy()))
        if cum >= 0.10 * 269:
            break
    return steps, tables, cur


def buy_name(p):
    i = int(np.where(pos == p)[0][0]); return f"{Q.ticker.iat[i]} {Q.D.iat[i]}"


# ---------------- CHECK 2: thresholds ----------------
X = feat_table(G)
say("\n== CHECK 2 — thresholds = order statistics of the 162 FIT buys (lower = 4th smallest, upper = 159th, band = 2nd/161st)")
say("   my derivation: 'the value 98% of his FIT buys pass' -> ceil(0.98*162) = 159 must pass -> x >= s[3] or x <= s[158]; "
    "band split 1%/1% -> ceil(0.99*162) = 161 per side -> [s[1], s[160]]")
nan_his = {f: int(np.isnan(X[f][pos]).sum()) for f in BUILDER_SET + EXTRA}
nan_s0 = {f: int(np.isnan(X[f]).sum()) for f in BUILDER_SET + EXTRA}
say(f"   NaN on his buys: {sum(nan_his.values())} total; NaN on S0 rows: {sum(nan_s0.values())} total ({ {k: v for k, v in nan_s0.items() if v} })")
J = json.load(open(f"{BW}/12_final_rules.json"))
txt = open(f"{BW}/12_backward.txt").read()
# builder's printed candidate thresholds
bth = {}
for line in txt.split("candidate thresholds (FIT values) and NaN counts:")[1].split("construction check")[0].splitlines():
    m = re.match(r"^\s{2}(\S+)\s+(\d+)\s+(\d+)\s+lower (\S+) \| upper (\S+)(?: \| band \[(\S+), (\S+)\])?", line)
    if m:
        bth[m.group(1)] = m.groups()[1:]
say(f"   {'feature':28s} {'mine lower':>12s} {'mine upper':>12s} {'band':>24s}   builder-printed match | numpy-default p2 / p98")
c2 = True
for f in BUILDER_SET + EXTRA:
    th = thresholds(X[f][FITp])
    band = f"[{th['band'][0]:g}, {th['band'][1]:g}]" if f in BANDED else ""
    if f in bth:
        b = bth[f]
        mt = (f"{th['lower']:g}" == b[2] and f"{th['upper']:g}" == b[3] and (f not in BANDED or (f"{th['band'][0]:g}" == b[4] and f"{th['band'][1]:g}" == b[5])))
        mt_s = "YES" if mt else "NO"
        if not mt: c2 = False; disc(f"threshold for {f}: mine {th['lower']:g}/{th['upper']:g}{band} vs builder {b[2:]}")
    else:
        mt_s = "(not a builder candidate)"
    say(f"   {f:28s} {th['lower']:12g} {th['upper']:12g} {band:>24s}   {mt_s:5s} | {th['np_p2']:.6g} / {th['np_p98']:.6g}")
# exact float equality against the JSON's added rules
say("   JSON added rules, exact float check:")
for r in J["added_rules"]:
    th = thresholds(X[r["feature"]][FITp])
    if r["op"] == ">=":
        mine, theirs = th["lower"], r["threshold"]; eq = mine == theirs
    elif r["op"] == "<=":
        mine, theirs = th["upper"], r["threshold"]; eq = mine == theirs
    else:
        mine, theirs = th["band"], (r["lo"], r["hi"]); eq = abs(mine[0] - theirs[0]) <= 1e-12 * abs(theirs[0]) and abs(mine[1] - theirs[1]) <= 1e-12 * abs(theirs[1])
    say(f"     step {r['step']} {r['name']:42s} mine {mine} | json {theirs} | equal {eq}")
    if not eq: c2 = False; disc(f"JSON threshold step {r['step']} {r['name']} differs from my order statistic: {mine} vs {theirs}")
for r in J["base_rules_S0"]:
    pass
say("   definitions vs the design's wording:")
say("     base_depth_adr = (pole_high - base_low)/pole_high/adr20 [builder] — design 'base depth from the pole top in daily ranges'; "
    "matches; the design does not pin the normaliser (alt: /(adr20*close)) -> sensitivity run below")
say("     close_vs_e10/e21_adr = (close/EMA - 1)/adr20 — design 'close vs EMA10 and vs EMA21 in daily ranges': matches")
say("     below_52w_high = 1 - close/hi252 — design 'distance below the 52-week high': matches. below_52w_high_adr is an EXTRA "
    "variant the design does not list (not added). hi252 = trailing max with min_periods=1 (a <252-bar name gets the max of what exists)")
say("     recent_low_vs_base_low_adr = (recent_low/base_low - 1)/adr20 — a normalisation chosen for v1's higher-lows values: reasonable, not in the design text")
say("     e21_rise_base = e21[D]/e21[pole]-1 from the table (G4) — matches")
say("     NOT used by the builder: tightening.range_recent5 / range_early5 (also v1 tightening VALUES) -> run as extra candidates below")
say("     band percentiles: the design marks bands but gives no percentile; builder 1%/1% (2nd/161st) — consistent with 98% passing")
say(f"CHECK 2 {'PASS' if c2 else 'FAIL'}")
th_adr = thresholds(X['adr20'][FITp])
RES["c2"] = (c2, f"all {len(bth)} builder candidate thresholds (mismatches: {sum(1 for d in DISC if d.startswith('threshold'))}) vs my order statistics (s[3], s[158], band s[1]/s[160] of n=162 FIT); "
                 f"JSON adr20 {J['added_rules'][0]['threshold']!r} == mine; numpy default p2 would be {th_adr['np_p2']:.7g}")

# ---------------- my greedy (builder candidate set) ----------------
C = candidates(X, BUILDER_SET)
steps, tables, final = greedy(C)
say("\n== MY GREEDY (builder's 18-feature candidate set; marginal drops on top of the current list; original denominators)")
for si, (cmed, cmean, rows) in enumerate(tables, 1):
    say(f"-- step {si}: current median {cmed:.0f}, mean {cmean:.0f}")
    say(f"   {'rule':52s} FITdrop CHKdrop BIGdrop  median    cut   mean  verdict")
    for r in rows:
        say(f"   {r['name']:52s} {r['fd']:7d} {r['cd']:7d} {r['bd']:7d} {r['med']:7.0f} {100 * r['cut']:5.1f}% {r['mean']:6.0f}  {r['why']}")
    if si <= len(steps):
        s = steps[si - 1]
        say(f"   -> ADD {s['name']} | dropped {', '.join(buy_name(p) for p in s['dropped'])}")
    else:
        say("   -> none qualifies: STOP")

# compare every candidate row of every step against the builder's printed tables
say("\n== builder's per-step candidate tables vs mine (every row: FIT/CHECK/BIG drops, median, mean, verdict)")
blocks = re.split(r"== STEP (\d) — candidates", txt)
bt = {}
for i in range(1, len(blocks), 2):
    st = int(blocks[i]); rows = {}
    for line in blocks[i + 1].splitlines():
        m = re.match(r"^\s{2}(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)%\s+(\d+)\s+(QUALIFIES|no:.*)$", line)
        if m:
            rows[m.group(1).strip()] = m.groups()[1:]
    bt[st] = rows
mism = 0; nrow = 0
for si, (cmed, cmean, rows) in enumerate(tables, 1):
    for r in rows:
        b = bt.get(si, {}).get(r["name"])
        nrow += 1
        if b is None:
            mism += 1; disc(f"step {si}: my candidate '{r['name']}' not in the builder's table"); continue
        mine = (str(r["fd"]), str(r["cd"]), str(r["bd"]), f"{r['med']:.0f}", f"{100 * r['cut']:.1f}", f"{r['mean']:.0f}", r["q"])
        theirs = (b[0], b[1], b[2], b[3], b[4], b[5], b[6] == "QUALIFIES")
        if mine != theirs:
            mism += 1; disc(f"step {si} '{r['name']}': mine {mine} vs builder {theirs}")
    extra_b = set(bt.get(si, {})) - {r["name"] for r in rows}
    for e in extra_b:
        mism += 1; disc(f"step {si}: builder row '{e}' not among my candidates")
say(f"   rows compared {nrow}, mismatches {mism}; builder printed {len(bt)} step tables, I have {len(tables)}")

# ---------------- CHECK 3: re-apply the final rule set from the JSON ----------------
say("\n== CHECK 3 — re-apply 12_final_rules.json (my own feature code + JSON thresholds) on the S0 rows")
m = np.ones(len(G), bool)
for r in J["added_rules"]:
    x = X[r["feature"]]
    with np.errstate(invalid="ignore"):
        m &= (x >= r["threshold"]) if r["op"] == ">=" else (x <= r["threshold"]) if r["op"] == "<=" else ((x >= r["lo"]) & (x <= r["hi"]))
nf = np.bincount(gc[m], minlength=NN); fmed, fmean, fp90 = stats(nf)
kf, kc, kb = int(m[FITp].sum()), int(m[CHKp].sum()), int(m[BIGp].sum())
same_as_greedy = bool((m == final).all())
say(f"final list: his buys {kf + kc}/269 (FIT {kf}/{NFIT}, CHECK {kc}/{NCHK}) | big winners {kb}/{NBIG} | names a night median {fmed:.0f}, "
    f"mean {fmean!r}, 90th pct {fp90:.0f}, min {nf.min()}, max {nf.max()} | rows {int(m.sum()):,} | nights >50 {int((nf > 50).sum())}, >100 {int((nf > 100).sum())}")
say(f"JSON result block: {J['result']}")
say(f"identical to my greedy's final list: {same_as_greedy}")
res = J["result"]
c3 = (kf + kc == res["his_buys_kept"] and kf == res["fit_kept"] and kc == res["check_kept"] and kb == res["big_winners_kept"]
      and fmed == res["names_a_night_median"] and abs(fmean - res["names_a_night_mean"]) < 1e-9 and fp90 == res["names_a_night_p90"]
      and int(m.sum()) == 905047 and same_as_greedy)
if not c3: disc("final re-application does not match the builder's claims")
say(f"CHECK 3 {'PASS' if c3 else 'FAIL'}")
RES["c3"] = (c3, f"{kf + kc}/269 (FIT {kf}/162, CHECK {kc}/107), big {kb}/26, median {fmed:.0f}, mean {fmean:.6f}, p90 {fp90:.0f}, "
                 f"min {nf.min()} max {nf.max()}, {int(m.sum()):,} rows; identical to my own greedy final list: {same_as_greedy}")

# ---------------- CHECK 4: admission conditions at each step ----------------
say("\n== CHECK 4 — every added rule met all 4 conditions at its step (builder's order recomputed)")
order_b = [r["name"] for r in J["added_rules"]]
order_m = [s["name"] for s in steps]
say(f"builder order: {order_b}\nmy order:      {order_m}")
c4 = order_b == order_m
cur = np.ones(len(G), bool); cmed = stats(np.bincount(gc, minlength=NN))[0]
C4D = []
for r in J["added_rules"]:
    x = X[r["feature"]]
    with np.errstate(invalid="ignore"):
        rm = (x >= r["threshold"]) if r["op"] == ">=" else (x <= r["threshold"]) if r["op"] == "<=" else ((x >= r["lo"]) & (x <= r["hi"]))
    new = cur & rm
    fd = int((cur[FITp] & ~new[FITp]).sum()); cd = int((cur[CHKp] & ~new[CHKp]).sum()); bd = int((cur[BIGp] & ~new[BIGp]).sum())
    nmed = stats(np.bincount(gc[new], minlength=NN))[0]
    ok = fd <= 3 and bd == 0 and nmed <= 0.95 * cmed and cd <= 4
    say(f"  step {r['step']} {r['name']:40s} (1) FIT drop {fd} <= 3 {fd <= 3} | (2) big drop {bd} == 0 {bd == 0} | "
        f"(3) median {cmed:.0f} -> {nmed:.0f} cut {100 * (1 - nmed / cmed):.1f}% >= 5% {nmed <= 0.95 * cmed} | (4) CHECK drop {cd} <= 4 {cd <= 4} -> {'MET' if ok else 'NOT MET'}")
    c4 = c4 and ok
    C4D.append(f"step {r['step']} {r['name']}: FIT {fd}/CHK {cd}/big {bd}, median {cmed:.0f}->{nmed:.0f} ({100 * (1 - nmed / cmed):.1f}%)")
    cur, cmed = new, nmed
tot = sum(len(s["dropped"]) for s in steps)
say(f"  cumulative dropped {tot} of 269 ({100 * tot / 269:.1f}%) < 10% stop (26.9): the stop was 'no candidate qualifies' at step {len(steps) + 1}")
# the load-bearing rejections at step 4, named
say("  the two rules rejected only on CHECK (step 4, on the final list): the CHECK buys they would drop")
for nm in ("close_vs_e21_adr >= -0.269583", "below_52w_high_adr >= 0.682311"):
    row = [r for r in tables[-1][2] if r["name"] == nm]
    if not row:
        disc(f"rejected candidate {nm} not found in my step-{len(tables)} table"); continue
    row = row[0]
    dropped = [buy_name(p) for p in CHKp if final[p] and not (final & row["mask"])[p]]
    say(f"    {nm}: CHECK drops {len(dropped)} ({', '.join(dropped)}) | FIT drops {row['fd']} | big {row['bd']} | median {row['med']:.0f} ({100 * row['cut']:.1f}% cut)")
    if len(dropped) <= 4: c4 = False; disc(f"{nm} drops only {len(dropped)} CHECK buys — it should have been eligible")
say(f"CHECK 4 {'PASS' if c4 else 'FAIL'}")
RES["c4"] = (c4, f"order {order_m} = builder; " + " ; ".join(C4D) + f"; total dropped {tot} < 26.9")

# ---------------- CHECK 5: step 1 spot check ----------------
say("\n== CHECK 5 — step 1: the qualifying candidate with the largest median cut")
q1 = sorted([r for r in tables[0][2] if r["q"]], key=lambda r: r["med"])
for r in q1:
    say(f"   qualifies: {r['name']:42s} median {r['med']:.0f} cut {100 * r['cut']:.1f}%  mean {r['mean']:.0f}")
big_cuts = sorted(tables[0][2], key=lambda r: r["med"])[:6]
say("   the six biggest cuts overall at step 1 (any verdict):")
for r in big_cuts:
    say(f"     {r['name']:42s} median {r['med']:.0f} cut {100 * r['cut']:.1f}%  {r['why']}")
c5 = q1[0]["name"] == J["added_rules"][0]["name"] and q1[0]["med"] < q1[1]["med"]
say(f"CHECK 5 {'PASS' if c5 else 'FAIL'} — first added {J['added_rules'][0]['name']}; mine {q1[0]['name']} (next best {q1[1]['name']} at {q1[1]['med']:.0f})")
RES["c5"] = (c5, f"{len(q1)} qualify at step 1: " + ", ".join(f"{r['name']} {r['med']:.0f} ({100 * r['cut']:.1f}%)" for r in q1) + "; bigger cuts that fail: " + ", ".join(f"{r['name']} ({100 * r['cut']:.1f}%: {r['why']})" for r in big_cuts if not r["q"] and r["med"] < q1[0]["med"]))

# ---------------- sensitivity runs ----------------
say("\n== SENSITIVITY (not part of the fixed procedure; does any reasonable reading change the result?)")
C_ext = candidates(X, BUILDER_SET + EXTRA)
st_ext, tb_ext, fin_ext = greedy(C_ext)
say(f"(a) + tightening.range_recent5 / range_early5 as candidates: order {[s['name'] for s in st_ext]} | final == builder's: {bool((fin_ext == final).all())}")
for si, (cmed, cmean, rows) in enumerate(tb_ext, 1):
    for r in rows:
        if r["f"] in EXTRA:
            say(f"     step {si} {r['name']:44s} FIT {r['fd']} CHK {r['cd']} big {r['bd']} median {r['med']:.0f} cut {100 * r['cut']:.1f}%  {r['why']}")
if not (fin_ext == final).all():
    disc("adding v1's other tightening values as candidates changes the greedy result")
Xa = feat_table(G, depth_alt=True)
st_a, tb_a, fin_a = greedy(candidates(Xa, BUILDER_SET))
say(f"(b) base depth normalised by close instead of pole_high, (pole_high-base_low)/(adr20*close): order {[s['name'] for s in st_a]} | "
    f"final == builder's: {bool((fin_a == final).all())} | kept {int(fin_a[pos].sum())}/269, big {int(fin_a[BIGp].sum())}, median {stats(np.bincount(gc[fin_a], minlength=NN))[0]:.0f}")
for s in st_a:
    say(f"     {s['name']}: dropped {', '.join(buy_name(p) for p in s['dropped'])}")
st_s, tb_s, fin_s = greedy(C, marginal=False)
say(f"(c) conditions 1/2/4 counted standalone on S0 instead of on top of the current list: order {[s['name'] for s in st_s]} | final == builder's: {bool((fin_s == final).all())}")

# ---------------- CHECK 6: look-ahead (code reading, recorded) ----------------
say("\n== CHECK 6 — look-ahead (read from 10_feature_table.py, breakout_v1.v1_gates, consolidation_breakout helpers, v1_replay)")
for s in ["EMA10/EMA21: recursive from the ticker's first bar, value taken at index D (bars <= D) — causal",
          "hi252: pandas rolling(252, min_periods=1).max() of highs, value at D (includes D's own high) — causal; <252 bars -> max of what exists",
          "e21_rise_base: e21[D]/e21[D-base_len]-1, the pole index from v1_gates at D — causal",
          "v1_gates(bars, D): adr20 = mean (h-l)/c over the 20 sessions ending D; pole top P in [D-45, D-10] via _pole_top (closes up to t <= D-10); "
          "pole_low over [P-40, P]; base_low = min low (P, D]; recent_low = last 5 sessions to D; surf/sma/tightening/breakdown windows end at D; "
          "dollar_vol = median close x volume ending D — all bars <= D",
          "rs_best: cross-section of r21/r63/r126 = c[D]/c[D-h]-1 on the night's pool — causal",
          "listable/universe: raw close at D and trailing dollar volume; the fund/security type list is the 2026-10-28 classification (a present-day label, not price data)",
          "split-adjusted bars: adjustment factors include splits after D (<= 2024-12-31); every feature used is a ratio within one series, so scale-invariant",
          "nothing in the table depends on E's bar (E is only a label); no column reads bars after D"]:
    say("   " + s)
c6 = True
say("CHECK 6 PASS (no feature reads a bar after D)")
RES["c6"] = (c6, "all features from bars <= D: EMA recursive to D, hi252 trailing (min_periods=1, mis-named for <252-bar names), pole in [D-45,D-10], "
                 "base/ADR/surf/tightening/dollar-vol windows end at D, RS from returns at D; security types are a 2026-10-28 label (not price data)")

# ---------------- CHECK 7: dropped-buys file ----------------
say("\n== CHECK 7 — 12_dropped_buys.tsv vs the buys my re-application drops")
DT = pd.read_csv(f"{BW}/12_dropped_buys.tsv", sep="\t", keep_default_na=False)
mine_drop = {}
for si, s in enumerate(steps, 1):
    for p in s["dropped"]:
        mine_drop[buy_name(p)] = s["name"]
theirs_drop = {f"{t} {d}": r for t, d, r in zip(DT.ticker, DT.D, DT.rule)}
say(f"mine {len(mine_drop)}, file {len(theirs_drop)}, both {len(set(mine_drop) & set(theirs_drop))}, only-mine {sorted(set(mine_drop) - set(theirs_drop))}, only-file {sorted(set(theirs_drop) - set(mine_drop))}")
c7 = set(mine_drop) == set(theirs_drop)
ALSO = []
for k in sorted(mine_drop):
    i = int(Q.index[(Q.ticker + " " + Q.D) == k][0]); p = pos[i]
    rr = [r for r in J["added_rules"] if r["name"] == mine_drop[k]][0]
    val = X[rr["feature"]][p]
    also = []
    for r2 in J["added_rules"]:
        if r2["name"] == mine_drop[k]: continue
        x2 = X[r2["feature"]][p]
        ok2 = (x2 >= r2["threshold"]) if r2["op"] == ">=" else (x2 <= r2["threshold"]) if r2["op"] == "<=" else (r2["lo"] <= x2 <= r2["hi"])
        if not ok2: also.append(f"{r2['name']} (value {x2:g})")
    frow = DT[(DT.ticker + " " + DT.D) == k]
    fv = float(frow.value.iat[0]) if len(frow) else float("nan")
    fa = frow.also_fails.iat[0] if len(frow) else ""
    big = "big" if Q.big.iat[i] else "no"
    era = "FIT" if Q.fit.iat[i] else "CHECK"
    match = len(frow) and frow.rule.iat[0] == mine_drop[k] and abs(fv - val) < 1e-12 * max(1, abs(val)) and fa == "; ".join(also) \
        and frow.era.iat[0] == era and frow.big_winner.iat[0] == big and str(frow.eid.iat[0]) == str(Q.eid.iat[i]) and frow.E.iat[0] == Q.E.iat[i]
    say(f"   {k:18s} eid {Q.eid.iat[i]:5d} {era:5s} big={big:3s} {mine_drop[k]:40s} value {val:.6g} | also fails: {'; '.join(also) or '-'} | file row matches: {bool(match)}")
    if also: ALSO.append(k + ' -> ' + '; '.join(also))
    if not match: c7 = False; disc(f"dropped-buys row for {k} differs (rule/value/also_fails/era/big/eid/E)")
say(f"CHECK 7 {'PASS' if c7 else 'FAIL'}")
RES["c7"] = (c7, f"mine {len(mine_drop)} vs file {len(theirs_drop)}, same set {set(mine_drop) == set(theirs_drop)}; per-row rule/value/era/big/eid/E/also_fails matched: {c7}; also-fails: " + "; ".join(ALSO))

# ---------------- CHECK 8: secondary checks ----------------
say("\n== CHECK 8 — secondary checks (stated, never deciding)")
Xf = None
def final_verdict_row(ticker, d):
    idx = key.get((ticker, d))
    if idx is None:
        return f"{ticker} {d}: not in the table (strength < 30 or not listable)", None
    on_s0 = bool(S0[idx])
    row = F.loc[[idx]]
    Xr = feat_table(row)
    fails = []
    for r in J["added_rules"]:
        x = Xr[r["feature"]][0]
        ok = (x >= r["threshold"]) if r["op"] == ">=" else (x <= r["threshold"]) if r["op"] == "<=" else (r["lo"] <= x <= r["hi"])
        if not ok: fails.append(f"{r['name']} (value {x:.6g})")
    v = "PASS" if on_s0 and not fails else "FAIL"
    detail = (f"{ticker} {d}: {v} | on S0 {on_s0} | fails {fails or '-'} | adr20 {Xr['adr20'][0]:.5f} prior_move {Xr['prior_move'][0]:.4f} "
              f"base_depth_adr {Xr['base_depth_adr'][0]:.5f} close_vs_e10_adr {Xr['close_vs_e10_adr'][0]:.3f} close_vs_e21_adr {Xr['close_vs_e21_adr'][0]:.3f}")
    return detail, (v, on_s0, fails)
sec = {}
for t, d in [("MRNA", "2020-08-07"), ("INO", "2020-08-07"), ("CDE", "2020-08-05"), ("CDE", "2020-08-06")]:
    s, v = final_verdict_row(t, d); say("   " + s); sec[f"{t} {d}"] = v
exp = {"MRNA 2020-08-07": "PASS", "INO 2020-08-07": "PASS", "CDE 2020-08-05": "FAIL", "CDE 2020-08-06": "FAIL"}
c8 = all(sec[k] and sec[k][0] == exp[k] for k in exp)
c8 = c8 and "1.69996" in sec["CDE 2020-08-05"][2][0] and "1.69996" in sec["CDE 2020-08-06"][2][0]

# MTW 2026-10-30 — first from the prod row values in q1.out, then live v1_gates on mtw_bars.csv
q1txt = open(f"{REPO}/scripts/probes/_mtw_1102/q1.out").read()
js = json.loads(re.search(r"\|(\{\"ok\".*\})\s*$", [l for l in q1txt.splitlines() if l.startswith("2026-10-30|MTW")][0]).group(1))
gg = js["gates"]
pm, ph, bl, adr = gg["prior_move"]["value"]["prior_move"], gg["prior_move"]["value"]["pole_high"], gg["higher_lows"]["value"]["base_low"], js["adr20"]
depth = (ph - bl) / ph / adr
on_s0 = (gg["history"]["pass"] and gg["universe"]["pass"] and gg["rs"]["value"]["rs_best"] >= 35 and adr >= 0.021 and gg["prior_move"]["pass"])
fails = []
r1, r2, r3 = J["added_rules"]
if not adr >= r1["threshold"]: fails.append("adr20")
if not (r2["lo"] <= depth <= r2["hi"]): fails.append("base_depth")
if not pm >= r3["threshold"]: fails.append(f"prior_move >= {r3['threshold']:g} (value {pm:.6f})")
say(f"   MTW 2026-10-30 from the prod row (q1.out): on S0 {on_s0} (history {gg['history']['value']['bars_to_d']} bars pass, universe pass, rs {gg['rs']['value']['rs_best']}, "
    f"adr20 {adr:.5f}, prior_move pass) | base_depth_adr {depth:.4f} (band [{r2['lo']:.5f}, {r2['hi']:.5f}]) | adr20 >= {r1['threshold']:.6f} {adr >= r1['threshold']} | "
    f"final: {'PASS' if not fails else 'FAIL: ' + '; '.join(fails)}")
mtw_fail = bool(on_s0 and fails == [f"prior_move >= {r3['threshold']:g} (value {pm:.6f})"])
# live v1_gates parity on the 97-bar file
sys.path.insert(0, REPO)
from agents.market_intelligence import breakout_v1 as bv  # noqa
from agents.market_intelligence import consolidation_breakout as cb  # noqa
B = pd.read_csv(f"{REPO}/scripts/probes/_mtw_1102/mtw_bars.csv")
dates = [dt.date.fromisoformat(x) for x in B.trade_date]
bars = cb.daily_bars_from_arrays(dates, B.open_price.values.astype(float), B.high_price.values.astype(float), B.low_price.values.astype(float),
                                 B.close.values.astype(float), B.volume.values.astype(float))
Di = dates.index(dt.date(2026, 10, 30))
g = bv.v1_gates(bars, Di, rs_best=98.6, raw_close=float(B.close.values[Di]), cidx=None)
pairs = [("prior_move", g["gates"]["prior_move"]["value"]["prior_move"], pm), ("pole_high", g["gates"]["prior_move"]["value"]["pole_high"], ph),
         ("pole_low", g["gates"]["prior_move"]["value"]["pole_low"], gg["prior_move"]["value"]["pole_low"]),
         ("base_len", g["gates"]["prior_move"]["value"]["base_len"], gg["prior_move"]["value"]["base_len"]),
         ("base_low", g["gates"]["higher_lows"]["value"]["base_low"], bl), ("recent_low", g["gates"]["higher_lows"]["value"]["recent_low"], gg["higher_lows"]["value"]["recent_low"]),
         ("adr20", g["adr20"], adr), ("ratio", g["gates"]["tightening"]["value"]["ratio"], gg["tightening"]["value"]["ratio"]),
         ("surf.best", g["gates"]["surf"]["value"]["best"], gg["surf"]["value"]["best"]),
         ("dollar_vol20", g["gates"]["universe"]["value"]["dollar_vol20"], gg["universe"]["value"]["dollar_vol20"]),
         ("level", g["level"], js["level"])]
pm_ok = sum(1 for _, a, b in pairs if (a == b) or (isinstance(a, float) and abs(a - b) <= 1e-9 * max(1, abs(b))))
say(f"   MTW live v1_gates on mtw_bars.csv ({len(B)} bars, D = {dates[Di]}): {pm_ok}/{len(pairs)} spot values equal the prod row "
    f"({', '.join(f'{n} {a:.6g}/{b:.6g}' for n, a, b in pairs if not ((a == b) or (isinstance(a, float) and abs(a - b) <= 1e-9 * max(1, abs(b)))))}) | live ok={g['ok']} failed={g['failed']}")
c8 = c8 and mtw_fail
say(f"CHECK 8 {'PASS' if c8 else 'FAIL'}")
RES["c8"] = (c8, f"MTW 10-30 FAIL only on prior_move 0.307895 < 0.321354 (on S0; depth {depth:.3f} in band; adr20 {adr:.4f}); "
                 f"MRNA/INO 2020-08-07 PASS; CDE 08-05 FAIL band ({sec['CDE 2020-08-05'][2][0]}), 08-06 FAIL band ({sec['CDE 2020-08-06'][2][0]}); "
                 f"live v1_gates on the MTW file {pm_ok}/{len(pairs)} spot values = prod row")

say("\n== SUMMARY")
for k in sorted(RES):
    say(f"  {k}: {'PASS' if RES[k][0] else 'FAIL'} — {RES[k][1]}")
FLAGS = [f"base depth is the one definition the design does not pin: the builder's (pole_high-base_low)/pole_high/adr20 follows its wording; normalising by close instead, (pole_high-base_low)/(adr20*close), changes step 2 to {st_a[1]['name'] if len(st_a) > 1 else '-'} dropping {', '.join(buy_name(p) for p in st_a[1]['dropped']) if len(st_a) > 1 else '-'} (instead of LRN 2020-08-04, MRNA 2021-11-26), final {int(fin_a[pos].sum())}/269, median {stats(np.bincount(gc[fin_a], minlength=NN))[0]:.0f}",
         "extra candidates the design does not name were run (below_52w_high_adr, recent_low_vs_base_low_adr normalisation); none was added. v1's tightening.range_recent5/range_early5 values were NOT run by the builder; adding them changes nothing",
         "hi252 uses min_periods=1: for a name with <252 bars it is the max of the bars that exist (causal; no 52-week rule was added)"]
say("  flags (not discrepancies):")
for f_ in FLAGS: say(f"   * {f_}")
say(f"  discrepancies: {len(DISC)}")
for d in DISC:
    say(f"   - {d}")
open(f"{HERE}/verify.txt", "w").write("\n".join(LOG) + "\n")
json.dump({k: [bool(v[0]), v[1]] for k, v in RES.items()} | {"discrepancies": DISC, "flags": FLAGS}, open(f"{HERE}/verify_summary.json", "w"), indent=1)
