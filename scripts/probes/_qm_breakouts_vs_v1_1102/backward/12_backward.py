#!/usr/bin/env python3
"""THE BACKWARD STEP (BACKWARD_DESIGN.md, fixed before this run): start from S0 (all 269 of Qullamaggie's dated breakout
buys on the list the night before) and add rules greedily, each admitted only if it (1) drops <= 2% of his FIT buys
(<= 3 of the original 162), (2) drops none of his 26 big winners, (3) cuts the median names a night by >= 5% vs the list
before it, (4) drops <= 4% of his CHECK buys (<= 4 of the original 107). Stop when none qualifies or when the total
dropped reaches 10% of his 269 buys. NO returns anywhere: the only scores are how many of his buys the list keeps and
how many names it holds a night. Read-only research; writes only into this folder.

Definitions fixed here (printed in 12_backward.txt):
  * threshold = "the value 98% of his FIT buys pass" (the design's wording): with n = 162 FIT buys, k = ceil(0.98 n) = 159
    must pass -> lower bound = the (n-k+1)th smallest FIT value (x >= t, inclusive), upper bound = the kth smallest
    (x <= t, inclusive). Band [1st, 99th pct]: k1 = ceil(0.99 n) = 161 per side. NaN never passes. Thresholds are set
    ONCE on all 162 FIT buys at the start and never re-fit on the shrinking list.
  * drops are MARGINAL (buys still on the current list that the rule removes); denominators never shrink.
  * greedy tie-break: largest median cut -> largest mean cut -> fewest of his buys dropped -> rule name.
  * stop: add-then-check; stop once the cumulative drop >= 10% of 269 (26.9, i.e. >= 27).
"""
import gzip, json, math, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
OUTDIR = "/Users/alvinfung/apollo_data/qm_breakouts_1102"
LOG = []
def say(s=""): print(s, flush=True); LOG.append(str(s))

# ───────────────────────────── load (only the columns needed) ─────────────────────────────
COLS = ["scan_date", "E", "ticker", "rs_best", "adr20", "close", "raw_close", "prior_move", "e10", "e21", "hi252",
        "e21_rise_base", "pass_history", "pass_universe", "pass_prior_move", "pass_breakdown",
        "prior_move.pole_high", "prior_move.base_len", "higher_lows.base_low", "higher_lows.recent_low",
        "surf.run10", "surf.run20", "surf.run50", "surf.best", "tightening.ratio", "universe.dollar_vol20",
        "universe.raw_close"]
F = pd.concat([pd.read_parquet(f"{OUTDIR}/features_era{e}.parquet", columns=COLS) for e in "AB"], ignore_index=True)
codes, night_ids = pd.factorize(F.scan_date)
NIGHTS = len(night_ids)
say("== 12_backward — the backward step from Qullamaggie's 269 dated breakout buys (BACKWARD_DESIGN.md)")
say(f"feature rows {len(F):,} over {NIGHTS} nights; gate_error column not loaded — 10_feature_table_run.txt shows 0 gate "
    f"errors in both eras, so no row is filtered (same as 11_starting_point)")
assert NIGHTS == 2012, NIGHTS
assert int(F.pass_history.sum()) == len(F), "pass_history is not 1 on every row"
assert F.scan_date.max() < "2025-01-01" and F.E.max() < "2025-01-01"

# his buys (join exactly as 11_starting_point)
Q = pd.read_csv(f"{PARENT}/qm_breakouts_v1_gates.tsv.gz", sep="\t")
key = dict(zip(zip(F.ticker, F.scan_date), F.index))
Q["row"] = [key.get((t, d)) for t, d in zip(Q.ticker, Q.D)]
assert len(Q) == 269 and Q.row.notna().all(), "not all 269 buys join"
Q["row"] = Q.row.astype(int)
yr = pd.to_datetime(Q.E).dt.year
assert yr.between(2017, 2023).all()
Q["split"] = np.where(yr <= 2020, "FIT", "CHECK")
# big winners: trades.tsv.gz is read ONLY to name them (eid + the four filter columns; nothing else)
t = pd.read_csv("/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/replay/trades.tsv.gz", sep="\t",
                usecols=["eid", "arm", "in_window", "entry_status", "realized_r"])
w = t[(t.arm == "d3_p33_tspd") & (t.in_window == True) & (t.entry_status == "filled")]
big_eids = set(w[w.realized_r >= 5].eid)
Q["big"] = Q.eid.isin(big_eids)
NFIT, NCHK, NBIG = int((Q.split == "FIT").sum()), int((Q.split == "CHECK").sum()), int(Q.big.sum())
say(f"his buys joined {int(Q.row.notna().sum())}/269 | FIT (E 2017-2020) {NFIT} | CHECK (E 2021-2023) {NCHK} | "
    f"big winners {NBIG} of the 269 ({len(big_eids)} big-winner eids in the replay; {len(big_eids - set(Q.eid))} are not "
    f"among the 269 breakout buys)")
assert NBIG == 26 and NFIT + NCHK == 269

# ───────────────────────────── derived features ─────────────────────────────
DERIVED = {
    "base_depth_adr": "(`prior_move.pole_high` - `higher_lows.base_low`) / `prior_move.pole_high` / `adr20`",
    "close_vs_e10_adr": "(`close` / `e10` - 1) / `adr20`",
    "close_vs_e21_adr": "(`close` / `e21` - 1) / `adr20`",
    "below_52w_high": "1 - `close` / `hi252`",
    "below_52w_high_adr": "(1 - `close` / `hi252`) / `adr20`",
    "recent_low_vs_base_low_adr": "(`higher_lows.recent_low` / `higher_lows.base_low` - 1) / `adr20`",
}
for name, expr in DERIVED.items():
    v = F.eval(expr).astype(float)
    F[name] = v.where(np.isfinite(v))         # +-inf -> NaN (never passes)

# candidates: (feature column, plain-words meaning, band?)
CANDS = [
    ("rs_best", "strength rank (best of 1/3/6-month percentile)", False),
    ("adr20", "daily range (ADR20, fraction of close)", False),
    ("prior_move", "prior move size (pole high / pole low - 1)", False),
    ("prior_move.base_len", "base length in sessions (pole top to D)", True),
    ("base_depth_adr", "base depth from the pole top in daily ranges", True),
    ("e21_rise_base", "EMA21 rise across the base (EMA21(D)/EMA21(pole top) - 1)", False),
    ("close_vs_e10_adr", "close vs EMA10 in daily ranges", False),
    ("close_vs_e21_adr", "close vs EMA21 in daily ranges", False),
    ("below_52w_high", "distance below the 52-week high (fraction)", False),
    ("below_52w_high_adr", "distance below the 52-week high in daily ranges", False),
    ("recent_low_vs_base_low_adr", "recent 5-session low vs base low in daily ranges (higher-lows value)", False),
    ("surf.run10", "surf value: sessions in a row riding the 10-day", False),
    ("surf.run20", "surf value: sessions in a row riding the 20-day", False),
    ("surf.run50", "surf value: sessions in a row riding the 50-day", False),
    ("surf.best", "surf value: best of the three runs", False),
    ("tightening.ratio", "tightening value: range of last 5 / range of the 5 before", False),
    ("universe.dollar_vol20", "dollar volume (20-session median close x volume)", False),
    ("universe.raw_close", "price (the real, unadjusted close at D)", False),
]

# ───────────────────────────── S0 ─────────────────────────────
BASE = [("pass_history", "==", 1), ("pass_universe", "==", 1), ("rs_best", ">=", 35.0), ("adr20", ">=", 0.021),
        ("pass_prior_move", "==", 1)]
def apply(col, op, thr, frame=F):
    x = frame[col].values
    with np.errstate(invalid="ignore"):
        if op == ">=": return x >= thr
        if op == "<=": return x <= thr
        if op == "==": return x == thr
    raise ValueError(op)

S0 = np.ones(len(F), bool)
for c, op, thr in BASE:
    S0 &= apply(c, op, thr)

def nights_stats(mask):
    n = np.bincount(codes[mask], minlength=NIGHTS)
    return n, float(np.median(n)), float(np.mean(n)), float(np.percentile(n, 90))

ROWS = Q.row.values
FITm, CHKm, BIGm = (Q.split == "FIT").values, (Q.split == "CHECK").values, Q.big.values
def buy_counts(kept):
    return int(kept[FITm].sum()), int(kept[CHKm].sum()), int(kept.sum()), int(kept[BIGm].sum())

n0, med0, mean0, p900 = nights_stats(S0)
k0 = S0[ROWS]
f0, c0, a0, b0 = buy_counts(k0)
say("\n== STEP 0 — reproduce S0 (history + universe + strength >= 35 + range >= 2.1% + prior move kept; no shape rule)")
say(f"S0: his buys {a0}/269 (FIT {f0}/{NFIT}, CHECK {c0}/{NCHK}) | big winners {b0}/{NBIG} | names a night: median "
    f"{med0:.0f}, mean {mean0:.0f}, 90th pct {p900:.0f}")
S0_OK = (a0 == 269 and b0 == 26 and f"{med0:.0f}" == "543" and f"{mean0:.0f}" == "625" and f"{p900:.0f}" == "1023")
say(f"S0 reproduces 11_starting_point.txt (269/269, 26/26, median 543, mean 625, 90th pct 1023): {'YES' if S0_OK else 'NO'}")
if not S0_OK:
    open(f"{HERE}/12_backward.txt", "w").write("\n".join(LOG) + "\n")
    sys.exit("S0 does not reproduce — stopping")

# ───────────────────────────── thresholds (FIT only, once) ─────────────────────────────
say("\n== DEFINITIONS")
say("derived features (pandas DataFrame.eval expressions on the table's columns; +-inf -> NaN):")
for name, expr in DERIVED.items():
    say(f"  {name:28s} = {expr}")
def ordn(k): return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"
k98 = -(-98 * NFIT // 100)      # ceil(0.98 n) = buys that must pass a one-sided threshold
k99 = -(-99 * NFIT // 100)      # ceil(0.99 n) = buys that must pass each side of a band
say(f"threshold = 'the value 98% of his FIT buys pass' (design wording): n = {NFIT} FIT buys, k = ceil(0.98 n) = {k98} must "
    f"pass -> lower bound t = the {ordn(NFIT - k98 + 1)} smallest FIT value, rule x >= t; upper bound t = the {ordn(k98)} smallest, "
    f"rule x <= t (both inclusive; drops <= {NFIT - k98} FIT buys by construction, fewer on ties). "
    f"Band [1st, 99th pct]: k1 = ceil(0.99 n) = {k99} per side -> [{ordn(NFIT - k99 + 1)} smallest, {ordn(k99)} smallest]. "
    f"(numpy's default linear 2nd percentile would sit between two buys and drop {NFIT - k98 + 1}, failing condition 1 "
    f"by construction — not used.) NaN never passes. Thresholds fixed once on all {NFIT} FIT buys; never re-fit.")
CAP_FIT = math.floor(0.02 * NFIT)          # 3
CAP_CHK = math.floor(0.04 * NCHK)          # 4
CAP_TOTAL = 0.10 * 269                     # 26.9
say(f"admission (marginal drops, original denominators): (1) FIT drop <= {CAP_FIT} (2% of {NFIT} = {0.02 * NFIT:.2f}); "
    f"(2) big-winner drop = 0; (3) new median <= 0.95 x current median; (4) CHECK drop <= {CAP_CHK} (4% of {NCHK} = "
    f"{0.04 * NCHK:.2f}) else 'did not hold on the later years' and NOT added.")
say(f"greedy: largest median cut -> largest mean cut -> fewest of his buys dropped -> rule name; stop when none qualifies "
    f"or once the cumulative drop >= 10% of 269 = {CAP_TOTAL:.1f} (add-then-check). An added rule leaves the pool; its "
    f"opposite side and bands stay in, evaluated on top of the current list.")
say("names a night = count of list rows per scan_date over all 2012 nights (np.bincount; identical to 11_starting_point's "
    "mask.groupby(scan_date).sum()); median / mean / 90th pct = numpy defaults (= pandas defaults).")

H = F.loc[ROWS].reset_index(drop=True)
RULES = []       # dict(name, feature, op, thr | lo/hi, meaning)
say("\ncandidate thresholds (FIT values) and NaN counts:")
say(f"  {'feature':28s} {'NaN his buys':>12s} {'NaN S0 rows':>11s}  thresholds")
for col, meaning, band in CANDS:
    if col not in F.columns:
        say(f"  {col:28s} SKIPPED — column missing"); continue
    nan_buys = int(H[col].isna().sum())
    nan_rows = int(np.isnan(F[col].values[S0].astype(float)).sum())
    share = nan_rows / int(S0.sum())
    if share > 0.5 or nan_buys > NFIT - k98:
        say(f"  {col:28s} {nan_buys:12d} {nan_rows:11d}  SKIPPED — mostly NaN"); continue
    v = np.sort(H.loc[FITm, col].dropna().astype(float).values)
    m = len(v)
    lo = float(v[m - k98]); hi = float(v[k98 - 1])
    RULES.append(dict(name=f"{col} >= {lo:.6g}", feature=col, op=">=", thr=lo, meaning=meaning))
    RULES.append(dict(name=f"{col} <= {hi:.6g}", feature=col, op="<=", thr=hi, meaning=meaning))
    txt = f"lower {lo:.6g} | upper {hi:.6g}"
    if band:
        blo = float(v[m - k99]); bhi = float(v[k99 - 1])
        RULES.append(dict(name=f"{blo:.6g} <= {col} <= {bhi:.6g}", feature=col, op="band", lo=blo, hi=bhi, meaning=meaning))
        txt += f" | band [{blo:.6g}, {bhi:.6g}]"
    say(f"  {col:28s} {nan_buys:12d} {nan_rows:11d}  {txt}")

def rule_pass(r, frame=F):
    if r["op"] == "band":
        return apply(r["feature"], ">=", r["lo"], frame) & apply(r["feature"], "<=", r["hi"], frame)
    return apply(r["feature"], r["op"], r["thr"], frame)

for r in RULES:
    r["mask"] = rule_pass(r)
    r["buy_pass"] = r["mask"][ROWS]

say("\nconstruction check — each candidate ALONE on S0: FIT buys it drops (<= 3 by construction; band <= 2):")
for r in RULES:
    say(f"  {r['name']:52s} FIT dropped {int((~r['buy_pass'])[FITm].sum())}  CHECK dropped "
        f"{int((~r['buy_pass'])[CHKm].sum())}  big dropped {int((~r['buy_pass'])[BIGm].sum())}")

# ───────────────────────────── greedy loop ─────────────────────────────
cur, kept = S0.copy(), k0.copy()
cur_med, cur_mean = med0, mean0
added, steps, dropped_by = [], [], {}
pool = list(range(len(RULES)))
step = 0
stop_reason = None
def bl(idx):
    return ", ".join(f"{Q.ticker[i]} {Q.D[i]}" + (" [BIG]" if Q.big[i] else "") + f" ({Q.split[i]})" for i in idx)

while True:
    step += 1
    say(f"\n== STEP {step} — candidates on top of the current list (median {cur_med:.0f} names a night, his buys kept "
        f"{int(kept.sum())}/269)")
    say(f"  {'rule':52s} {'FITdrop':>7s} {'CHKdrop':>7s} {'BIGdrop':>7s} {'median':>7s} {'cut':>7s} {'mean':>6s}  verdict")
    evals = []
    for j in pool:
        r = RULES[j]
        drop = kept & ~r["buy_pass"]
        fd, cd, bd = int(drop[FITm].sum()), int(drop[CHKm].sum()), int(drop[BIGm].sum())
        nm = cur & r["mask"]
        _, med, mean, p90 = nights_stats(nm)
        cut = 1 - med / cur_med
        why = []
        if fd > CAP_FIT: why.append(f"FIT drop {fd} > {CAP_FIT}")
        if bd > 0: why.append(f"drops {bd} big winner(s)")
        if not (med <= 0.95 * cur_med): why.append(f"median cut {cut:.1%} < 5%")
        if cd > CAP_CHK and not why: why.append(f"did not hold on the later years (CHECK drop {cd} > {CAP_CHK})")
        elif cd > CAP_CHK: why.append(f"CHECK drop {cd} > {CAP_CHK}")
        ok = not why
        evals.append(dict(j=j, fd=fd, cd=cd, bd=bd, med=med, mean=mean, p90=p90, cut=cut, ok=ok, drop=drop))
        say(f"  {r['name']:52s} {fd:7d} {cd:7d} {bd:7d} {med:7.0f} {cut:7.1%} {mean:6.0f}  "
            f"{'QUALIFIES' if ok else 'no: ' + '; '.join(why)}")
    q = [e for e in evals if e["ok"]]
    if not q:
        stop_reason = "no candidate qualifies"
        say(f"  -> none qualifies: STOP")
        break
    q.sort(key=lambda e: (-(cur_med - e["med"]), -(cur_mean - e["mean"]), e["fd"] + e["cd"], RULES[e["j"]]["name"]))
    e = q[0]; r = RULES[e["j"]]
    di = np.where(e["drop"])[0]
    for i in di: dropped_by[i] = len(added)
    cur = cur & r["mask"]; kept = kept & r["buy_pass"]
    _, cur_med, cur_mean, cur_p90 = nights_stats(cur)
    fk, ck, ak, bk = buy_counts(kept)
    added.append(r); pool.remove(e["j"])
    rec = dict(step=step, rule=r["name"], threshold=(r["thr"] if r["op"] != "band" else [r["lo"], r["hi"]]),
               kept_fit=fk, kept_check=ck, kept_all=ak, big_kept=bk, med=cur_med, mean=cur_mean, p90=cur_p90,
               dropped=[f"{Q.ticker[i]} {Q.D[i]}" for i in di], total_dropped=269 - ak)
    steps.append(rec)
    say(f"  -> ADD {r['name']}  ({r['meaning']})")
    say(f"     his buys kept FIT {fk}/{NFIT} | CHECK {ck}/{NCHK} | all {ak}/269 | big winners {bk}/{NBIG} | names a "
        f"night: median {cur_med:.0f}, mean {cur_mean:.0f}, 90th pct {cur_p90:.0f} | cumulative dropped {269 - ak}")
    say(f"     dropped this step ({len(di)}): {bl(di) if len(di) else 'none'}")
    if 269 - ak >= CAP_TOTAL:
        stop_reason = f"total dropped {269 - ak} reached 10% of 269 ({CAP_TOTAL:.1f})"
        say(f"  -> {stop_reason}: STOP"); break
    if not pool:
        stop_reason = "candidate pool exhausted"; break

# ───────────────────────────── step table ─────────────────────────────
say("\n== STEP TABLE (his buys kept FIT / CHECK / all; big winners kept; names a night median / mean / 90th pct)")
say(f"  {'step':>4s}  {'rule':52s} {'FIT':>7s} {'CHECK':>7s} {'all':>7s} {'big':>5s} {'med':>5s} {'mean':>5s} {'p90':>5s}  dropped")
say(f"  {0:4d}  {'S0 (starting point)':52s} {f0:3d}/{NFIT} {c0:3d}/{NCHK} {a0:3d}/269 {b0:2d}/{NBIG} {med0:5.0f} {mean0:5.0f} {p900:5.0f}  -")
for s in steps:
    say(f"  {s['step']:4d}  {s['rule']:52s} {s['kept_fit']:3d}/{NFIT} {s['kept_check']:3d}/{NCHK} {s['kept_all']:3d}/269 "
        f"{s['big_kept']:2d}/{NBIG} {s['med']:5.0f} {s['mean']:5.0f} {s['p90']:5.0f}  {', '.join(s['dropped']) or 'none'}")
say(f"stop reason: {stop_reason}")

# ───────────────────────────── final list ─────────────────────────────
nF, medF, meanF, p90F = nights_stats(cur)
fk, ck, ak, bk = buy_counts(kept)
say("\n== FINAL LIST")
say("rules: S0 base (" + " & ".join(f"{c} {op} {thr}" for c, op, thr in BASE) + ")" +
    "".join(f" & {r['name']}" for r in added))
say(f"his buys kept {ak}/269 (FIT {fk}/{NFIT}, CHECK {ck}/{NCHK}) | big winners {bk}/{NBIG} | names a night: median "
    f"{medF:.0f}, mean {meanF:.0f}, 90th pct {p90F:.0f}, min {nF.min()}, max {nF.max()}")
say(f"nights over 50 names: {int((nF > 50).sum())}/{NIGHTS} ({(nF > 50).mean():.1%}); over 100 names: "
    f"{int((nF > 100).sum())}/{NIGHTS} ({(nF > 100).mean():.1%})")

# dropped buys file
rows = []
for i in sorted(dropped_by, key=lambda i: (dropped_by[i], Q.D[i])):
    r = added[dropped_by[i]]
    val = float(H.loc[i, r["feature"]])
    also = [f"{a['name']} (value {float(H.loc[i, a['feature']]):.6g})" for k, a in enumerate(added)
            if k != dropped_by[i] and not a["buy_pass"][i]]
    rows.append({"eid": Q.eid[i], "ticker": Q.ticker[i], "sym": Q.sym[i], "D": Q.D[i], "E": Q.E[i], "era": Q.split[i],
                 "big_winner": "yes" if Q.big[i] else "no", "rule": r["name"], "feature": r["feature"],
                 "value": val, "threshold": (r["thr"] if r["op"] != "band" else f"[{r['lo']}, {r['hi']}]"),
                 "op": r["op"], "also_fails": "; ".join(also)})
DF = pd.DataFrame(rows, columns=["eid", "ticker", "sym", "D", "E", "era", "big_winner", "rule", "feature", "value",
                                 "threshold", "op", "also_fails"])
DF.to_csv(f"{HERE}/12_dropped_buys.tsv", sep="\t", index=False)
say(f"\ndropped buys under the final set: {len(DF)} (FIT {int((DF.era == 'FIT').sum())}, CHECK {int((DF.era == 'CHECK').sum())}, "
    f"big winners {int((DF.big_winner == 'yes').sum())}) -> backward/12_dropped_buys.tsv (these charts go to him)")
for _, d in DF.iterrows():
    say(f"  {d.ticker:6s} D {d.D}  E {d.E}  {d.era:5s} big={d.big_winner:3s}  {d.rule}  value {d.value:.6g}"
        + (f"  also fails: {d.also_fails}" if d.also_fails else ""))

# final rules json + self-check by re-applying it with DataFrame.eval
FEXPR = {c: f"`{c}`" for c, _, _ in CANDS}
FEXPR.update(DERIVED)
J = {"description": "Breakout list rebuilt backward from Qullamaggie's 269 dated breakout buys (12_backward.py). Apply "
                    "to features_eraA/B.parquet (one row per name-night); a row is on the list when EVERY rule passes. "
                    "NaN never passes. Feature expressions are pandas DataFrame.eval strings (backticks quote dotted "
                    "column names); +-inf -> NaN.",
     "tables": [f"{OUTDIR}/features_era{e}.parquet" for e in "AB"],
     "base_rules_S0": [{"feature": c, "expr": f"`{c}`", "op": op, "threshold": thr} for c, op, thr in BASE],
     "added_rules": [{"step": k + 1, "name": r["name"], "feature": r["feature"], "expr": FEXPR[r["feature"]],
                      "meaning": r["meaning"], "op": r["op"],
                      **({"threshold": r["thr"]} if r["op"] != "band" else {"lo": r["lo"], "hi": r["hi"]})}
                     for k, r in enumerate(added)],
     "threshold_definition": f"lower = the {ordn(NFIT - k98 + 1)} smallest of the {NFIT} FIT buys' values (x >= t); upper = "
                             f"the {ordn(k98)} smallest (x <= t); band = [{ordn(NFIT - k99 + 1)}, {ordn(k99)} smallest]; inclusive",
     "result": {"his_buys_kept": ak, "fit_kept": fk, "check_kept": ck, "big_winners_kept": bk,
                "names_a_night_median": medF, "names_a_night_mean": meanF, "names_a_night_p90": p90F},
     "stop_reason": stop_reason}
json.dump(J, open(f"{HERE}/12_final_rules.json", "w"), indent=1)
chk = np.ones(len(F), bool)
for rr in J["base_rules_S0"] + J["added_rules"]:
    x = F.eval(rr["expr"]).astype(float).values
    x = np.where(np.isfinite(x), x, np.nan)
    with np.errstate(invalid="ignore"):
        if rr["op"] == "band": chk &= (x >= rr["lo"]) & (x <= rr["hi"])
        elif rr["op"] == ">=": chk &= x >= rr["threshold"]
        elif rr["op"] == "<=": chk &= x <= rr["threshold"]
        else: chk &= x == rr["threshold"]
say(f"12_final_rules.json re-applied with DataFrame.eval reproduces the final list: "
    f"{'YES' if np.array_equal(chk, cur) else 'NO'} ({int(chk.sum()):,} rows)")
assert np.array_equal(chk, cur)

# ───────────────────────────── secondary checks (stated, never deciding) ─────────────────────────────
def verdict(rowd, base_only=False):
    fails = []
    for c, op, thr in BASE:
        v = rowd.get(c)
        okv = v is not None and not (isinstance(v, float) and math.isnan(v)) and (
            (op == ">=" and v >= thr) or (op == "<=" and v <= thr) or (op == "==" and v == thr))
        if not okv: fails.append(f"S0 {c} {op} {thr} (value {v})")
    for r in ([] if base_only else added):
        v = rowd.get(r["feature"])
        if v is None or (isinstance(v, float) and math.isnan(v)): okv = False
        elif r["op"] == "band": okv = r["lo"] <= v <= r["hi"]
        elif r["op"] == ">=": okv = v >= r["thr"]
        else: okv = v <= r["thr"]
        if not okv: fails.append(f"{r['name']} (value {v:.6g})" if v is not None else f"{r['name']} (value NaN)")
    return fails

SHOW = ["rs_best", "adr20", "prior_move", "prior_move.base_len", "base_depth_adr", "e21_rise_base", "close_vs_e10_adr",
        "close_vs_e21_adr", "below_52w_high", "below_52w_high_adr", "recent_low_vs_base_low_adr", "surf.run10",
        "surf.run20", "surf.run50", "surf.best", "tightening.ratio", "universe.dollar_vol20", "universe.raw_close",
        "pass_universe", "pass_prior_move", "pass_breakdown"]
say("\n== SECONDARY CHECKS (stated, never deciding)")
say("(b) Qullamaggie's 2020-08-10 stream calls: MRNA / INO 'breaking down' (list night 2020-08-07); CDE 'no good setup' "
    "(2020-08-05, 2020-08-06)")
sec = {}
for tk, d in [("MRNA", "2020-08-07"), ("INO", "2020-08-07"), ("CDE", "2020-08-05"), ("CDE", "2020-08-06")]:
    i = key.get((tk, d))
    if i is None:
        say(f"  {tk} {d}: NOT IN TABLE (strength < 30 or not listable that night) -> not on any list"); sec[f"{tk} {d}"] = "not in table"; continue
    rowd = {c: (float(F.at[i, c]) if F.at[i, c] is not None else None) for c in SHOW + [c for c, _, _ in BASE]}
    fails = verdict(rowd)
    say(f"  {tk} {d}: " + ", ".join(f"{c}={rowd[c]:.4g}" for c in SHOW))
    v = "PASS (on the final list)" if not fails else "FAIL: " + "; ".join(fails)
    say(f"     under the final set: {v} | on S0: {'yes' if S0[i] else 'no'}")
    sec[f"{tk} {d}"] = v

say("\n(a) MTW on 2026-10-30 (Qullamaggie's read: no setup) — live breakout_v1.v1_gates on scripts/probes/_mtw_1102/mtw_bars.csv")
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import breakout_v1 as bv  # noqa
from agents.market_intelligence import consolidation_breakout as cb  # noqa
import datetime as _dt
M = pd.read_csv("/Users/alvinfung/apollo_the_wise/scripts/probes/_mtw_1102/mtw_bars.csv")
bars = cb.daily_bars_from_arrays([_dt.date.fromisoformat(x) for x in M.trade_date], M.open_price, M.high_price,
                                 M.low_price, M.close, M.volume)
D = len(bars) - 1
assert str(bars.dates[D]) == "2026-10-30"
g = bv.v1_gates(bars, D, rs_best=98.6, raw_close=float(bars.c[D]), cidx=None)
gg = g["gates"]
def ema(x, n):
    a, out = 2 / (n + 1), np.empty(len(x)); out[0] = x[0]
    for i in range(1, len(x)): out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out
cc = np.asarray(bars.c, float)
e10, e21 = ema(cc, 10)[D], ema(cc, 21)
hi252 = float(np.max(bars.h[:D + 1]))
bl_ = int(gg["prior_move"]["value"]["base_len"]); P = D - bl_
mt = {"pass_history": int(bool(gg["history"]["pass"])), "pass_universe": int(bool(gg["universe"]["pass"])),
      "pass_prior_move": int(bool(gg["prior_move"]["pass"])), "pass_breakdown": int(bool(gg["breakdown"]["pass"])),
      "rs_best": 98.6, "adr20": g["adr20"], "close": float(cc[D]), "prior_move": g["prior_move"],
      "prior_move.base_len": bl_, "prior_move.pole_high": gg["prior_move"]["value"]["pole_high"],
      "higher_lows.base_low": gg["higher_lows"]["value"]["base_low"],
      "higher_lows.recent_low": gg["higher_lows"]["value"]["recent_low"],
      "e10": float(e10), "e21": float(e21[D]), "hi252": hi252, "e21_rise_base": float(e21[D] / e21[P] - 1),
      "surf.run10": gg["surf"]["value"]["run10"], "surf.run20": gg["surf"]["value"]["run20"],
      "surf.run50": gg["surf"]["value"]["run50"], "surf.best": gg["surf"]["value"]["best"],
      "tightening.ratio": gg["tightening"]["value"]["ratio"],
      "universe.dollar_vol20": gg["universe"]["value"]["dollar_vol20"], "universe.raw_close": float(cc[D])}
MD = pd.DataFrame([mt])
for name, expr in DERIVED.items():
    mt[name] = float(MD.eval(expr).iloc[0])
# parity with the prod row in q1.out
q1 = open("/Users/alvinfung/apollo_the_wise/scripts/probes/_mtw_1102/q1.out").read().splitlines()
prod = json.loads([l for l in q1 if l.startswith("2026-10-30|MTW|")][0].split("|", 6)[6])
pg = prod["gates"]
par = [("adr20", prod["adr20"], g["adr20"]), ("base_len", pg["prior_move"]["value"]["base_len"], bl_),
       ("pole_high", pg["prior_move"]["value"]["pole_high"], gg["prior_move"]["value"]["pole_high"]),
       ("pole_low", pg["prior_move"]["value"]["pole_low"], gg["prior_move"]["value"]["pole_low"]),
       ("prior_move", pg["prior_move"]["value"]["prior_move"], gg["prior_move"]["value"]["prior_move"]),
       ("base_low", pg["higher_lows"]["value"]["base_low"], gg["higher_lows"]["value"]["base_low"]),
       ("recent_low", pg["higher_lows"]["value"]["recent_low"], gg["higher_lows"]["value"]["recent_low"]),
       ("tightening.ratio", pg["tightening"]["value"]["ratio"], gg["tightening"]["value"]["ratio"]),
       ("surf.run10", pg["surf"]["value"]["run10"], gg["surf"]["value"]["run10"]),
       ("surf.run20", pg["surf"]["value"]["run20"], gg["surf"]["value"]["run20"]),
       ("surf.run50", pg["surf"]["value"]["run50"], gg["surf"]["value"]["run50"]),
       ("dollar_vol20", pg["universe"]["value"]["dollar_vol20"], gg["universe"]["value"]["dollar_vol20"]),
       ("level", prod["level"], g["level"])]
mism = [n for n, a, b in par if not (a == b or (isinstance(a, float) and isinstance(b, float) and abs(a - b) <= 1e-9 * max(1, abs(a))))]
say(f"  parity vs the prod list row (q1.out): {len(par) - len(mism)}/{len(par)} values match"
    + (f"; differ: {', '.join(f'{n} prod {a} vs here {b}' for n, a, b in par if n in mism)}" if mism else " exactly"))
say(f"  v1 verdict: prod row ok={prod['ok']} (its gates {sorted(pg)} carry no pinned/adr gate — the row predates the "
    f"11-02 floors); live v1_gates here ok={g['ok']}, failed {g['failed']} (ADR20 {g['adr20']:.4f} < the 4.26% floor)")
say(f"  note: {len(bars)} bars in the file (prod saw {pg['history']['value']['bars_to_d']}); EMA10/21 seeded at the file's first bar "
    f"(2026-06-15) and hi252 = max high in the file, so those three differ from a longer-history computation")
say("  MTW 2026-10-30: " + ", ".join(f"{c}={mt[c]:.4g}" for c in SHOW))
mf = verdict(mt)
mtw_v = "PASS (on the final list)" if not mf else "FAIL: " + "; ".join(mf)
say(f"     under the final set: {mtw_v} | on S0: {'yes' if not verdict(mt, base_only=True) else 'no: ' + '; '.join(verdict(mt, base_only=True))}")

J["secondary"] = {"MTW 2026-10-30": mtw_v, **sec}
json.dump(J, open(f"{HERE}/12_final_rules.json", "w"), indent=1)
open(f"{HERE}/12_backward.txt", "w").write("\n".join(LOG) + "\n")
