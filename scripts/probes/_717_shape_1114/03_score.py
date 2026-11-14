#!/usr/bin/env python3
"""#717 shape checks: the SCORE (2026-11-14; post-processing of 01_capture.py's bar windows; research, no rule changed).

PREREG — written BEFORE the first scoring run (02_study / 02b_study were exploration: they printed the bars and candidate
measures of the 36 graded charts and of Qullamaggie's 56, so his-eye is IN-SAMPLE for the choice of measures; no
threshold is taken from a grade). All measures at the watch night D from bars <= D; u = ADR20(D) x the buy level = one
daily range in price. NaN passes. One definition per reason (A) and at most one variant (B):

 (i)  choppy / wide bars, no tightness      A  hl10 = (highest high - lowest low of the last 10 sessions) / u  -> OUT when > T
                                            B  hl15 = the same over the last 15 sessions
 (ii) downtrend, a lower high               swings = zigzag of the last 60 sessions with a 2-daily-range reversal; the still
                                            running leg's extreme counts as the latest swing
                                            A  lh = (latest swing high - the one before) / u  -> OUT when < -T (a lower high by more than T)
                                            B  FIXED, no threshold: OUT when the latest swing high AND the latest swing low are both lower (lh < 0 and ll < 0)
 (iii) no higher lows in the base           A  ll = (latest swing low - the one before) / u, same swings  -> OUT when < -T
                                            B  the same with a 3-daily-range reversal
 (iv) "where's the breakout"                A  off60 = (60-session high - the buy level) / u  -> OUT when > T
      (and "needs more sideways tight days") B  near10 = how many of the last 10 closes sit within 2 daily ranges under the level -> OUT when < T
 (C)  the four together                     flags = the four A measures, each flagged beyond the 90th percentile (10th for a
                                            lower bound) of Qullamaggie's 56 listed High-tier buys; OUT when flags >= K,
                                            K = (the most flags any of the 56 carries) + 1. Cv = the same on the four B measures
                                            ((ii)B's flag = its fixed rule).

 SIZING (the previous card's rule, unchanged): a sized check's T is the EXTREME value among the 56 listed High-tier buys
 (keeps 56 of 56 by construction: in-sample on the 56; the out-of-sample read is the rest of the scorecard, incl. the 26 big
 winners). PLATEAU (ADR 0023; 3 points, nothing else is swept): sized checks at the 1st / 2nd / 3rd most extreme of the 56
 (the 2nd / 3rd drop 1 / 2 of his buys by construction — labelled); the swing reversal at 1.5 / 2 / 3 daily ranges; (C) at the
 85th / 90th / 95th percentile.
 STACK RULE (the previous card's): a check enters when it drops 0 of the 56, keeps 26 of 26 big winners firing, removes at
 least one graded "no" and no graded ok / good. Everything is shown ALONE (on the plain list) and ON TOP OF 1d (out when
 the close is more than 3% under a FALLING 50-day), whose baseline is 466 / 380 / 26 and 59 fires a day.
 HIS EYE is in-sample (36 grades over three sheets; 5 of the 'no' are already out at 1d).

 (03_score_first_run.out = the first run, kept. Edits after it, NO definition or threshold changed: two print labels, and a
 LOADER FIX — the first run matched 4 third-sheet grades (ADMS, RIOT, WDC, W) to the NEXT night's row because the
 11-14 fixture rows store the fire day where the earlier sheets store the list night; grades are now matched on both
 dates of the sheet key files. Only the his-eye columns could move.)
 ADR 0023's plateau guardrail (docs/decisions/0023-exit-stop-mechanics.md: "reject a best-cell whose neighbors collapse";
 "the pick must be mechanism-justified against its named cases") is judged in the report from the PLATEAU and ATTRIBUTION
 sections; the STACK section below applies only the previous card's numeric rule.

    python3 scripts/probes/_717_shape_1114/03_score.py > scripts/probes/_717_shape_1114/03_score.out
"""
import os, sys
import numpy as np, pandas as pd
import lib
pd.set_option("display.width", 320)
HERE = lib.HERE
f, sc, hi, hi_all, gr, nights, cal, WF, WX = lib.load()
mf = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_shape_1114/fires_shape_measures.parquet")
assert (mf.index == f.index).all()
f = f.join(mf)
def add(d, W):
    m = lib.measures(W[d.w.to_numpy()], d.adr20.to_numpy(), d.level.to_numpy()); m.index = d.index
    return d.join(m)
sc, hi = add(sc, WX), add(hi, WX)
gr = gr.join(mf.loc[[f.index[w] for w in gr.w]].reset_index(drop=True))
gr["sheet"] = gr.sheet.map(lambda p: {"sheet_model_picks.png": "1 (11-13)", "sheet_template_picks.png": "2 (11-13)", "sheet_stack_dollar_volume_picks.png": "3 (11-14)"}[os.path.basename(p)])
NO, OKG, COND = gr[gr.grade == "no"], gr[gr.grade.isin(["ok", "good"])], gr[gr.grade == "conditional"]
ONE_D = lambda d: ~((d.u50 < -0.03) & (d.s50_chg10 < 0))
TRUE = lambda d: pd.Series(True, index=d.index)

# ── bridge (the previous card's numbers must reproduce before anything new)
per0 = f.groupby("ci").size().reindex(nights).fillna(0)
L0, F0, B0 = sc.key.nunique(), sc.key[sc.fired == 1].nunique(), sc.key[(sc.fired == 1) & (sc.big == 1)].nunique()
print(f"BRIDGE: scorecard listed / fired / big winners = {L0} / {F0} / {B0} (expect 479 / 386 / 26); listed High-tier buys {len(hi)} (expect 56); era-A fires a day median {per0.median():.0f} (expect 68) over {len(nights)} nights; "
      f"grades {len(NO)} no / {len(OKG)} ok-good / {len(COND)} maybe (36 = the three sheets)")
assert (L0, F0, B0, len(hi), per0.median(), len(gr)) == (479, 386, 26, 56, 68, 36)
TOP0 = set(map(tuple, f.sort_values("dollar_vol20", ascending=False).groupby("ci").head(5)[["ci", "ticker"]].to_numpy()))

DROPS = []
def score(name, fn):
    hk = fn(hi); hd = hi[~hk]
    s = sc[fn(sc)]
    L, F, B = s.key.nunique(), s.key[s.fired == 1].nunique(), s.key[(s.fired == 1) & (s.big == 1)].nunique()
    lostf = sc[(sc.fired == 1) & ~sc.key.isin(s.key[s.fired == 1])].drop_duplicates("key")
    for r in lostf.itertuples():
        DROPS.append((name, r.set, r.eid, r.ticker, r.E, r.tier, r.big))
    tier = lostf.tier.value_counts().reindex(["High", "Medium", "Low", "Not"]).fillna(0).astype(int)
    bigl = lostf[lostf.big == 1]
    rn, ro, rc = NO[~fn(NO)], OKG[~fn(OKG)], COND[~fn(COND)]
    ff = f[fn(f)]
    per = ff.groupby("ci").size().reindex(nights).fillna(0)
    top = set(map(tuple, ff.sort_values("dollar_vol20", ascending=False).groupby("ci").head(5)[["ci", "ticker"]].to_numpy()))
    repl = 1 - len(top & TOP0) / len(TOP0)
    print(f"{name:34s} | {int(hk.sum()):2d}/56 | {L:3d} / {F:3d} / {B:2d} | lost H{tier['High']} M{tier['Medium']} L{tier['Low']} N{tier['Not']} | no {len(rn):2d}/{len(NO)} ok-good {len(ro)}/{len(OKG)} maybe {len(rc)}/{len(COND)} | {per.median():4.0f} {per.mean():6.1f} | {repl:5.1%} | "
          f"High dropped: {', '.join(f'{r.ticker} {r.E}' for r in hd.itertuples()) or '-'}"
          f"{' | BIG WINNERS LOST: ' + ', '.join(f'{r.ticker} {r.E}' for r in bigl.itertuples()) if len(bigl) else ''}"
          f" | no removed: {' '.join(rn.ticker) or '-'}{' | OK/GOOD REMOVED: ' + ' '.join(ro.ticker) if len(ro) else ''}{' | maybe removed: ' + ' '.join(rc.ticker) if len(rc) else ''}")
    return dict(high=int(hk.sum()), L=L, F=F, B=B, no=len(rn), ok=len(ro), fires=per.median())
HDR = (f"{'check':34s} | High  | scorecard listed/fired/big | fired buys lost by tier | his eye (IN-SAMPLE): removed of {len(NO)} no / {len(OKG)} ok-good / {len(COND)} maybe | fires a day median mean | "
       "top-5 dollar-volume picks replaced | names")

# ── definitions
def ext(col, side, k=1):
    v = np.sort(hi[col].dropna().to_numpy())
    return float(v[-k]) if side == "max" else float(v[k - 1])
def sized(col, side, k=1):
    T = ext(col, side, k)
    return (lambda d: d[col].isna() | (d[col] <= T)) if side == "max" else (lambda d: d[col].isna() | (d[col] >= T)), T
SIZED = {"(i)A hl10 box": ("hl10", "max"), "(i)B hl15 box": ("hl15", "max"), "(ii)A lower high": ("lh_2.0", "min"),
         "(iii)A swing low not lower": ("ll_2.0", "min"), "(iii)B same, 3-range swings": ("ll_3.0", "min"),
         "(iv)A level under 60d high": ("off60", "max"), "(iv)B closes near the level": ("near10", "min")}
FIXED = {"(ii)B lower high AND lower low": lambda d: ~((d["lh_2.0"] < 0) & (d["ll_2.0"] < 0))}
A4 = [("hl10", "max"), ("lh_2.0", "min"), ("ll_2.0", "min"), ("off60", "max")]
B4 = [("hl15", "max"), None, ("ll_3.0", "min"), ("near10", "min")]
def flags(d, spec, pct):
    n = pd.Series(0, index=d.index)
    for s in spec:
        if s is None:
            n += ((d["lh_2.0"] < 0) & (d["ll_2.0"] < 0)).astype(int); continue
        col, side = s
        p = np.nanpercentile(hi[col], pct if side == "max" else 100 - pct)
        n += ((d[col] > p) if side == "max" else (d[col] < p)).astype(int)
    return n
def composite(spec, pct):
    K = int(flags(hi, spec, pct).max()) + 1
    return (lambda d: flags(d, spec, pct) < K), K
CHECKS, THR = {}, {}
for nm, (col, side) in SIZED.items():
    CHECKS[nm], THR[nm] = sized(col, side)
CHECKS.update(FIXED)
CHECKS["(C) flags of the four A"], THR["(C) flags of the four A"] = composite(A4, 90)
CHECKS["(Cv) flags of the four B"], THR["(Cv) flags of the four B"] = composite(B4, 90)

print("\n== THRESHOLDS (the extreme of the 56; who sets each; how the 56 and the era-A fires sit) ==")
for nm, (col, side) in SIZED.items():
    v = hi.sort_values(col, ascending=(side == "min")).dropna(subset=[col]).head(4)
    q = f[col].dropna(); T = THR[nm]
    share = (q > T).mean() if side == "max" else (q < T).mean()
    print(f"  {nm:30s} {col:7s} {side} = {T:7.2f}  set by {', '.join(f'{r.ticker} {r.E} ({hi.loc[r.Index, col]:.2f})' for r in v.itertuples())} | the 56 median {hi[col].median():.2f}; fires median {q.median():.2f}; fires beyond the line {share:.1%}")
for nm, spec in (("(C) flags of the four A", A4), ("(Cv) flags of the four B", B4)):
    fh, ff = flags(hi, spec, 90), flags(f, spec, 90)
    print(f"  {nm:30s} OUT at {THR[nm]} flags or more; flags among the 56: {fh.value_counts().sort_index().to_dict()}; among fires: {(ff.value_counts(normalize=True).sort_index() * 100).round(1).to_dict()} %; "
          f"lines: " + ", ".join("fixed rule" if s is None else f"{s[0]} {'>' if s[1] == 'max' else '<'} {np.nanpercentile(hi[s[0]], 90 if s[1] == 'max' else 10):.2f}" for s in spec))
print("  tier medians (scorecard sessions) — does Qullamaggie's own confidence line up with the measure?")
print(sc.groupby("tier")[["hl10", "hl15", "lh_2.0", "ll_2.0", "ll_3.0", "off60", "near10"]].median().reindex(["High", "Medium", "Low", "Not"]).round(2).to_string())
print("  era-A fires median:        " + "  ".join(f"{c} {f[c].median():.2f}" for c in ["hl10", "hl15", "lh_2.0", "ll_2.0", "ll_3.0", "off60", "near10"]))

RES = {}
print("\n== EACH CHECK ALONE on the plain list (baseline first) ==\n" + HDR)
RES["baseline"] = score("baseline (no check)", TRUE)
RES["1d"] = score("1d (>3% under a falling 50-day)", ONE_D)
for nm, fn in CHECKS.items():
    RES[nm] = score(nm, fn)
print("\n== EACH CHECK ON TOP OF 1d (the 1d baseline: 56/56, 466 / 380 / 26, 59 a day) ==\n" + HDR)
RES1 = {}
for nm, fn in CHECKS.items():
    RES1[nm] = score("1d + " + nm, lambda d, fn=fn: ONE_D(d) & fn(d))

print("\n== PLATEAU, on top of 1d (3 points each; the 2nd / 3rd most extreme of the 56 drop 1 / 2 of his buys BY CONSTRUCTION) ==\n" + HDR)
for nm, (col, side) in SIZED.items():
    for k in (1, 2, 3):
        fn, T = sized(col, side, k)
        score(f"1d + {nm[:20]} k={k} T={T:.2f}", lambda d, fn=fn: ONE_D(d) & fn(d))
print("swing reversal 1.5 / 2 / 3 daily ranges (sized at the 56's extreme each time):")
for base, nm in (("lh", "(ii)A lower high"), ("ll", "(iii)A swing low")):
    for k in ("1.5", "2.0", "3.0"):
        fn, T = sized(f"{base}_{k}", "min")
        score(f"1d + {nm} zz={k} T={T:.2f}", lambda d, fn=fn: ONE_D(d) & fn(d))
    for k in ("1.5", "2.0", "3.0"):
        if base == "lh":
            score(f"1d + (ii)B both lower zz={k}", lambda d, k=k: ONE_D(d) & ~((d[f"lh_{k}"] < 0) & (d[f"ll_{k}"] < 0)))
print("(C) / (Cv) at the 85th / 90th / 95th percentile of the 56:")
for nm, spec in (("(C)", A4), ("(Cv)", B4)):
    for pct in (85, 90, 95):
        fn, K = composite(spec, pct)
        score(f"1d + {nm} p{pct} out at {K}+ flags", lambda d, fn=fn: ONE_D(d) & fn(d))

# ── attribution: the charts whose STATED reason each check mechanises (x = removed by the check alone)
TARGETS = {"(i) choppy / large bars / no tightness": (["SWAV", "DVAX", "F", "FLGT", "THC", "CDE", "TWTR", "FUTU", "AZUL"], ["(i)A hl10 box", "(i)B hl15 box"]),
           "(ii) downtrend / lower high": (["F", "DOCN", "THC", "REN"], ["(ii)A lower high", "(ii)B lower high AND lower low"]),
           "(iii) no higher lows": (["MVIS", "CDE", "DOCN"], ["(iii)A swing low not lower", "(iii)B same, 3-range swings"]),
           "(iv) no breakout / needs more tight days": (["LCID", "REN", "AZUL"], ["(iv)A level under 60d high", "(iv)B closes near the level"]),
           "all the above": (sorted(set("SWAV DVAX F FLGT THC CDE TWTR FUTU AZUL DOCN REN MVIS LCID".split())), ["(C) flags of the four A", "(Cv) flags of the four B"])}
print("\n== ATTRIBUTION — the charts whose STATED reason each check mechanises (x = removed) ==")
for lab, (tk, cs) in TARGETS.items():
    for c in cs:
        print(f"  {lab:42s} {c:30s} " + "  ".join(f"{t}:{'x' if not bool(CHECKS[c](gr[gr.ticker == t]).iloc[0]) else '.'}" for t in tk))

print("\n== THE 36 GRADED PICKS — the measures, the A-flag count (p90 lines) and whether 1d already removed it ==")
g2 = gr.assign(flagsA=flags(gr, A4, 90), flagsB=flags(gr, B4, 90), out_1d=~ONE_D(gr))
cols = ["sheet", "card", "ticker", "Dd", "grade", "out_1d", "base_len", "hl10", "hl15", "lh_2.0", "ll_2.0", "ll_3.0", "off60", "near10", "flagsA", "flagsB"]
print(g2.sort_values(["grade", "out_1d", "ticker"])[[c for c in cols if c in g2.columns]].round(2).to_string(index=False))
print("\nthe 56 listed High-tier buys — the same measures (quantiles):")
print(hi[cols[7:14]].describe(percentiles=[.1, .25, .5, .75, .9]).loc[["min", "10%", "25%", "50%", "75%", "90%", "max"]].round(2).to_string())

# ── the stack
print("\n== STACK (rule in PREREG), cumulative on top of 1d ==")
enter = [n for n in CHECKS if RES1[n]["high"] == 56 and RES1[n]["B"] == 26 and RES1[n]["no"] > RES["1d"]["no"] and RES1[n]["ok"] == 0]
print("checks that pass the rule on top of 1d:", "; ".join(enter) or "NONE")
print(HDR)
cum = []
score("1d", ONE_D)
for n in enter:
    cum.append(n)
    score("+ " + n, lambda d, cc=tuple(cum): ONE_D(d) & np.logical_and.reduce([CHECKS[c](d) for c in cc]))
dd = pd.DataFrame(DROPS, columns=["check", "set", "eid", "ticker", "E", "tier", "big"]).drop_duplicates()
dd.to_csv(os.path.join(HERE, "03_drops.tsv"), sep="\t", index=False)
open(os.path.join(HERE, "stack.txt"), "w").write("1d\n" + "\n".join(f"{c}\t{THR.get(c, '')}" for c in cum) + "\n")
if cum:
    x = dd[dd.check == "+ " + cum[-1]]
    print(f"\nthe full stack stops {len(x)} scorecard buys from firing (03_drops.tsv): by tier {x.tier.value_counts().to_dict()}; big winners {int(x.big.sum())}")
    print("  " + ", ".join(f"{r.ticker} {r.E} ({r.tier})" for r in x.itertuples()))
