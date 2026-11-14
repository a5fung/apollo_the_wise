#!/usr/bin/env python3
"""#717 reasons -> checks: the SCORE (2026-11-14; post-processing of 01_measure.py's captures only; research, no rule changed).

DECLARED BEFORE THE SCORE (this docstring was written before the first run):
 * A threshold is never picked off the operator's 24 grades. Fixed-definition checks (1a-1d, 3a-3d) have no threshold.
   A SIZED check takes the EXTREME value among the 56 listed High-tier Qullamaggie buys (so it keeps 56 of 56 by
   construction — its High-tier recall is in-sample; the out-of-sample recall is the rest of the 757 scorecard, incl. the
   26 big winners). The grades and the era-A fires are then read ONCE at that threshold.
   A "SWEEP" row (the 2nd / 3rd / 4th most extreme High buy as the line: drops 1 / 2 / 3 of his buys) is labelled a sweep.
 * "falling 50-day" = the 50-day SMA at D is lower than 10 sessions earlier (s50_chg10 < 0).
 * STACK RULE: a check enters the stack when it (i) drops 0 of the 56 listed High-tier buys, (ii) keeps 26 of 26 big
   winners firing, (iii) removes at least one graded "no" and (iv) removes no graded ok / good. Every scorecard buy a
   check stops from firing is listed by tier in 02_drops.tsv — the PLAN DoD's literal "never below 479 / 386 / 26" is
   failed by ANY gate that drops one Low / Not-tier sighting; that reading is the operator's call, shown per row.
 * NaN (a measure that cannot be computed) PASSES a check.
The checks (all at the watch night D, bars <= D):
 1a close >= SMA50 (the gate dropped 11-11) | 1b close >= 0.97 x SMA50 | 1c OUT when close < SMA50 AND the SMA50 is falling
 1d OUT when close < 0.97 x SMA50 AND falling
 2a the 6-month (126-session) high is no older than T | 2b the buy level no further under that high than T daily ranges
 2c the 6-month run (runup6m / ADR) at least T | 2 = 2a AND 2b AND 2c
 3a higher_lows 3b no_lower_low 3c low_not_today 3d ema21_not_falling (breakout_v1.shape_gates, as-is)
 3e the latest 5-bar swing low of the last 60 sessions no lower than T daily ranges under the one before it (the ONE new definition)
 4  the biggest gap down (prior close -> open) of the last 30 sessions that the buy level has NOT reclaimed (level <= the
    close before the gap) no bigger than T daily ranges
 4b POST-HOC (added after the first run showed check 4 removes none of LCID / F / DVAX — LCID's gap is ABOVE-reclaimed, the
    level sits over the pre-gap close): the biggest gap down of the last 30 sessions, reclaimed or not, no bigger than T.
    Same sizing rule; flagged post-hoc wherever it appears.
 5a mean range of the last 5 sessions / ADR20 at least T | 5b last 10 | 5c the last-10-close spread at least T daily ranges
 6  template distance (06_template.py's RMS gap, W = 90) no more than T; also read as era-A percentile cuts (sweep)

    python3 scripts/probes/_717_reasons_1114/02_score.py > scripts/probes/_717_reasons_1114/02_score.out
"""
import importlib.util, os, sys
from datetime import date
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
os.chdir(REPO); sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "tests/fixtures"))
from breakout_list_grades import MODEL_PICK_GRADES  # noqa: E402
CAP = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
MEASF = "/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"
pd.set_option("display.width", 250)

# ── load
df = pd.read_parquet(CAP)
cal = [date.fromisoformat(s) for s in open(CAP + ".cal.txt").read().split()]
assert cal[-1] < date(2025, 1, 1)
nights = sorted(df.ci.unique())
f = df[df.fire].join(pd.read_parquet(MEASF), rsuffix="_m")
assert (f.base_len == f.base_len_m).all()
f["Dd"] = [cal[c].isoformat() for c in f.ci]
sc = pd.read_csv(os.path.join(HERE, "scorecard_rows.tsv"), sep="\t", dtype={"eid": str})
sc["key"] = sc.set + sc.eid
hi_all = pd.read_csv(os.path.join(HERE, "high_rows.tsv"), sep="\t", dtype={"eid": str})
hi = hi_all[hi_all.ok == 1].copy()
gr = []
for g in MODEL_PICK_GRADES:
    x = f[(f.ticker == g.ticker) & (f.Dd == g.list_date)]
    assert len(x) == 1, g
    gr.append(dict(x.iloc[0].to_dict(), grade=g.grade, card=g.sheet_card, words=g.operator_words))
gr = pd.DataFrame(gr)
NO, OKG, COND = gr[gr.grade == "no"], gr[gr.grade.isin(["ok", "good"])], gr[gr.grade == "conditional"]

# ── bridge
per0 = f.groupby("ci").size().reindex(nights).fillna(0)
L0, F0, B0 = sc.key.nunique(), sc.key[sc.fired == 1].nunique(), sc.key[(sc.fired == 1) & (sc.big == 1)].nunique()
print(f"BRIDGE: scorecard listed / fired / big winners = {L0} / {F0} / {B0} (expect 479 / 386 / 26); listed High-tier buys {len(hi)} (expect 56; 84 = 56 + {int((hi_all.failed == 'adr').sum())} stopped by the 4% floor alone + 5 other floors); "
      f"era-A fires a day median {per0.median():.0f} mean {per0.mean():.1f} over {len(nights)} nights (expect median 68); grades {len(NO)} no / {len(OKG)} ok-good / {len(COND)} conditional")
assert (L0, F0, B0, len(hi), per0.median()) == (479, 386, 26, 56, 68)

# ── check 1 evidence: every High-tier buy under its 50-day
print("\n== CHECK 1 EVIDENCE — the High-tier buys whose close sat under the 50-day the night before (all 84; 'listed' = on today's 4% list) ==")
u = hi_all[hi_all.u50 < 0].sort_values("u50")
print(f"{'ticker':6s} {'E':10s} {'set':8s} {'listed':6s} {'big':3s} {'% under':>8s} {'50d chg 10 sess (ADR)':>22s} {'falling':>8s} {'1b keeps':>8s} {'1c keeps':>8s} {'1d keeps':>8s}")
for r in u.itertuples():
    print(f"{r.ticker:6s} {r.E:10s} {r.set:8s} {('yes' if r.ok else r.failed):6s} {r.big:3d} {r.u50:8.1%} {r.s50_chg10:22.2f} {str(r.s50_chg10 < 0):>8s} {str(r.u50 >= -0.03):>8s} {str(not r.s50_chg10 < 0):>8s} {str(not (r.u50 < -0.03 and r.s50_chg10 < 0)):>8s}")
print(f"under the 50-day: {len(u)} of 84 ({int(u.ok.sum())} of the 56 listed); within 3% under: {int((u.u50 >= -0.03).sum())}; more than 3% under: {int((u.u50 < -0.03).sum())}; under a FALLING 50-day: {int((u.s50_chg10 < 0).sum())}; more than 3% under AND falling: {int(((u.u50 < -0.03) & (u.s50_chg10 < 0)).sum())}")

# ── thresholds from the 56 listed High-tier buys
def ext(col, side, k=1):
    v = np.sort(hi[col].dropna().to_numpy())
    return float(v[-k]) if side == "max" else float(v[k - 1])
SIZED = {"2a": ("hh_age", "max"), "2b": ("off_high_adr", "max"), "2c": ("runup6m_adr", "min"), "3e": ("piv_ll_adr", "min"),
         "4": ("gap_dn_adr", "max"), "4b": ("gap_any_adr", "max"), "5a": ("rng5_over_adr", "min"), "5b": ("rng10_over_adr", "min"), "5c": ("spread10_adr", "min"), "6": ("tpl_dist", "max")}
def sized(cid, k=1):
    col, side = SIZED[cid]; T = ext(col, side, k)
    return (lambda d, c=col, T=T, s=side: (d[c].isna() | (d[c] <= T)) if s == "max" else (d[c].isna() | (d[c] >= T))), T
CHECKS = {
    "1a close>=SMA50": lambda d: d.u50 >= 0,
    "1b close>=0.97xSMA50": lambda d: d.u50 >= -0.03,
    "1c under AND falling 50d": lambda d: ~((d.u50 < 0) & (d.s50_chg10 < 0)),
    "1d >3% under AND falling": lambda d: ~((d.u50 < -0.03) & (d.s50_chg10 < 0)),
}
THR = {}
for cid, nm in (("2a", "6m high age"), ("2b", "level under 6m high"), ("2c", "6m run size")):
    CHECKS[f"{cid} {nm}"], THR[cid] = sized(cid)
CHECKS["2  run-up (2a+2b+2c)"] = lambda d: CHECKS["2a 6m high age"](d) & CHECKS["2b level under 6m high"](d) & CHECKS["2c 6m run size"](d)
for cid, col in (("3a", "higher_lows"), ("3b", "no_lower_low"), ("3c", "low_not_today"), ("3d", "ema21_not_falling")):
    CHECKS[f"{cid} {col} (as-is)"] = lambda d, c=col: d[c].astype(bool)
for cid, nm in (("3e", "swing low not lower"), ("4", "unreclaimed gap down"), ("4b", "any gap down (POST-HOC)"), ("5a", "frozen: range5/ADR"), ("5b", "frozen: range10/ADR"), ("5c", "frozen: spread10"), ("6", "template distance")):
    CHECKS[f"{cid} {nm}"], THR[cid] = sized(cid)
print("\n== THRESHOLDS (the extreme of the 56 listed High-tier buys; who sets each) ==")
for cid, (col, side) in SIZED.items():
    v = hi.sort_values(col, ascending=(side == "min")).dropna(subset=[col]).head(4)
    q = f[col].dropna()
    share = (q > THR[cid]).mean() if side == "max" else (q < THR[cid]).mean()
    print(f"  {cid:3s} {col:16s} {side} = {THR[cid]:8.3f}  set by {', '.join(f'{r.ticker} {r.E} ({getattr(r, col):.2f})' for r in v.itertuples())} | High median {hi[col].median():.2f}; era-A fires median {q.median():.2f}; fires beyond the line {share:.1%}")
tpl_in, tpl_out = hi[hi.E <= "2020-12-31"], hi[hi.E > "2020-12-31"]
print(f"  check 6 is IN-SAMPLE on the buys to 2020 (the template was fitted on them): High to 2020 n={len(tpl_in)} distance median {tpl_in.tpl_dist.median():.2f} max {tpl_in.tpl_dist.max():.2f}; 2021+ n={len(tpl_out)} median {tpl_out.tpl_dist.median():.2f} max {tpl_out.tpl_dist.max():.2f}")

# ── the yardstick
DROPS = []
def score(name, fn, quiet=False):
    hk = fn(hi); hd = hi[~hk]
    s = sc[fn(sc)]
    L, F, B = s.key.nunique(), s.key[s.fired == 1].nunique(), s.key[(s.fired == 1) & (s.big == 1)].nunique()
    lostf = sc[(sc.fired == 1) & ~sc.key.isin(s.key[s.fired == 1])].drop_duplicates("key")
    for r in lostf.itertuples():
        DROPS.append((name, r.set, r.eid, r.ticker, r.E, r.tier, r.big))
    tier = lostf.tier.value_counts().reindex(["High", "Medium", "Low", "Not"]).fillna(0).astype(int)
    bigl = lostf[lostf.big == 1]
    rn, ro, rc = NO[~fn(NO)], OKG[~fn(OKG)], COND[~fn(COND)]
    per = f[fn(f)].groupby("ci").size().reindex(nights).fillna(0)
    if not quiet:
        print(f"{name:28s} | {int(hk.sum()):2d}/56 | {L:3d} / {F:3d} / {B:2d} | fired lost H{tier['High']} M{tier['Medium']} L{tier['Low']} N{tier['Not']} | no {len(rn):2d}/{len(NO)}  ok-good {len(ro)}/{len(OKG)}  cond {len(rc)}/{len(COND)} | {per.median():4.0f} {per.mean():6.1f} | "
              f"High dropped: {', '.join(f'{r.ticker} {r.E}' for r in hd.itertuples()) or '-'}"
              f"{' | BIG WINNERS LOST: ' + ', '.join(f'{r.ticker} {r.E}' for r in bigl.itertuples()) if len(bigl) else ''}"
              f" | no removed: {' '.join(rn.ticker) or '-'}{' | OK/GOOD REMOVED: ' + ' '.join(ro.ticker) if len(ro) else ''}{' | cond removed: ' + ' '.join(rc.ticker) if len(rc) else ''}")
    return dict(high=int(hk.sum()), L=L, F=F, B=B, no=len(rn), ok=len(ro), fires=per.median(), high_lost_fired=int(tier["High"]))
HDR = f"{'check':28s} | High  | scorecard listed/fired/big | fired buys lost by tier (High Medium Low Not) | his eye: removed of 15 no / 7 ok-good / 2 cond | fires a day median mean | names"
print("\n== EACH CHECK ALONE (baseline first) ==\n" + HDR)
RES = {"baseline": score("baseline (no check)", lambda d: pd.Series(True, index=d.index))}
for name, fn in CHECKS.items():
    RES[name] = score(name, fn)

print("\n== SWEEPS (labelled: the line at the 2nd / 3rd / 4th most extreme High buy -> drops 1 / 2 / 3 of his 56) ==\n" + HDR)
for cid in SIZED:
    for k in (2, 3, 4):
        fn, T = sized(cid, k)
        score(f"SWEEP {cid} k={k} T={T:.2f}", fn)
print("SWEEP check 6 as an era-A percentile cut (drop the fires least like the template):")
for pct in (10, 25, 50):
    T = float(np.nanpercentile(f.tpl_dist, 100 - pct))
    score(f"SWEEP 6 drop worst {pct}% T={T:.2f}", lambda d, T=T: d.tpl_dist.isna() | (d.tpl_dist <= T))

# ── attribution: does each check remove the picks whose stated reason it mechanises?
TARGETS = {"1 (50-day above, curling down)": (["CLR"], ["1a close>=SMA50", "1b close>=0.97xSMA50", "1c under AND falling 50d", "1d >3% under AND falling"]),
           "2 (no run-up / large old range)": (["FLGT", "FUTU", "ZIM", "MVIS", "DVAX"], ["2a 6m high age", "2b level under 6m high", "2c 6m run size"]),
           "3 (lower lows / downtrend / no higher lows)": (["DOCN", "F", "MVIS", "ATOS"], ["3a higher_lows (as-is)", "3b no_lower_low (as-is)", "3c low_not_today (as-is)", "3d ema21_not_falling (as-is)", "3e swing low not lower"]),
           "4 (gap down into the range)": (["LCID", "F", "DVAX"], ["4 unreclaimed gap down", "4b any gap down (POST-HOC)"]),
           "5 (suspiciously tight)": (["OCGN"], ["5a frozen: range5/ADR", "5b frozen: range10/ADR", "5c frozen: spread10"])}
print("\n== ATTRIBUTION — the picks whose STATED reason each check mechanises (x = removed) ==")
for lab, (tk, cs) in TARGETS.items():
    for c in cs:
        print(f"  {lab:46s} {c:28s} " + "  ".join(f"{t}:{'x' if not bool(CHECKS[c](gr[gr.ticker == t]).iloc[0]) else '.'}" for t in tk))

print("\n== THE 24 GRADED PICKS — every measure ==")
cols = ["card", "ticker", "Dd", "grade", "u50", "s50_chg10", "hh_age", "off_high_adr", "runup6m_adr", "piv_ll_adr", "gap_dn_adr", "gap_any_adr", "rng5_over_adr", "rng10_over_adr", "spread10_adr", "tpl_dist",
        "higher_lows", "no_lower_low", "low_not_today", "ema21_not_falling"]
print(gr.sort_values(["grade", "ticker"])[cols].round(2).to_string(index=False))
print("\nthe 56 listed High-tier buys — the same measures (quartiles):")
print(hi[cols[4:16]].describe().loc[["min", "25%", "50%", "75%", "max"]].round(2).to_string())
print("as-is shape helpers on the 56 (share passing): " + ", ".join(f"{c} {hi[c].astype(bool).mean():.0%}" for c in cols[16:]))

# ── the stack
print("\n== STACK (rule in the docstring: 0 of 56 High dropped, 26/26 big winners, >= 1 'no' removed, 0 ok/good removed), cumulative in the task's order ==")
enter = [n for n in CHECKS if not n.startswith("2  ") and RES[n]["high"] == 56 and RES[n]["B"] == 26 and RES[n]["no"] >= 1 and RES[n]["ok"] == 0]
print("checks that pass the rule alone:", "; ".join(enter) or "NONE")
print(HDR)
cum = []
for n in enter:
    cum.append(n)
    score("+ " + n[:26], lambda d, cc=tuple(cum): np.logical_and.reduce([CHECKS[c](d) for c in cc]))
STACK = tuple(cum)
open(os.path.join(HERE, "stack.txt"), "w").write("\n".join(f"{c}\t{THR.get(c.split()[0], '')}" for c in STACK) + "\n")
dd = pd.DataFrame(DROPS, columns=["check", "set", "eid", "ticker", "E", "tier", "big"]).drop_duplicates()
dd.to_csv(os.path.join(HERE, "02_drops.tsv"), sep="\t", index=False)
if STACK:
    last = "+ " + STACK[-1][:26]
    x = dd[dd.check == last]
    print(f"\nthe full stack stops {len(x)} scorecard buys from firing (all in 02_drops.tsv): by tier {x.tier.value_counts().to_dict()}; big winners {int(x.big.sum())}")
    print("  High / Medium among them: " + (", ".join(f"{r.ticker} {r.E} ({r.tier})" for r in x[x.tier.isin(['High', 'Medium'])].itertuples()) or "-"))
