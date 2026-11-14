#!/usr/bin/env python3
"""#717 context checks: long decline under a falling 50-day (A) and bars not contracting (B) — PAIR VALIDATION + SCORE
(2026-11-14; post-processing of earlier era-A captures + 01_capture.py; research, no rule or constant changed).

PREREG v1 — written BEFORE any measure of this card was computed on any row (inputs: his words on the side-by-side,
docs/methodology/operator_shared_notes.md 2026-11-14, and the picture _717_pairs_1114/pairs.png). All measures at the watch
night D from bars <= D. NaN passes.

 A  DOWNTREND = a long decline sitting under a FALLING 50-day (not price vs the 50-day on one day; not a lower high)
    A1  OUT when the 50-day is lower than 20 sessions ago (s50_chg20 < 0) AND the close is under it (u50 < 0)
        AND the 126-session return < T
    A2  OUT when the 50-day is lower than 20 sessions ago AND the 126-session return < T        (no price-vs-50 leg)
 B  CHOP = wide loose bars that are NOT contracting into the buy (not the 10-day box; no ADR denominator)
    B1  tr5_base = mean true range of the last 5 sessions / mean true range of the base's earlier bars (pole top+1 .. D-5;
        a base with fewer than 5 earlier bars uses the 15 sessions before the last 5)  -> OUT when > T
    B2  wide10 = how many of the last 10 sessions have a true range > 1.5 x the mean true range of the 20 sessions BEFORE
        those 10  -> OUT when > T

 SIZING (the shape card's extreme-of-the-must-keeps line, extended to the big winners as the brief asks): T = the cut
 that removes the most while keeping ALL 56 listed High-tier buys AND all 26 big winners firing (a big winner is kept when
 any of its fired sessions passes -> its constraint is its best fired session). For A the constraint set is only the
 must-keeps that meet the fixed legs, and T is capped at 0 (a decline): no must-keep meets the fixed legs -> T = 0.
 No threshold is taken from a grade or from the pairs.
 PAIR VALIDATION (before scoring; fire rows of the era-A capture): A must flag THC 2017-05-10 and REN 2017-07-28 and not
 APT 2020-06-17 / BE 2020-08-13; B must flag TWTR 2018-02-08 and not JMIA 2020-11-18. A definition that fails is revised
 ONCE (v2 below, both recorded); the raw components of the six rows are printed for that purpose (nothing else is looked at).
 PLATEAU (3 points, nothing else swept): A — the 50-day's fall measured over 5 / 10 / 20 sessions, T re-sized each time;
 B — T at the 1st / 2nd / 3rd most extreme constraint (the 2nd / 3rd lose 1 / 2 must-keeps BY CONSTRUCTION — labelled).
 TABLE (the shape card's harness verbatim): High kept /56 (drops listed), scorecard listed / fired / big, his eye on the 36
 graded (IN-SAMPLE; THC, REN, TWTR are the design pairs), fires a day — each definition ALONE and ON TOP OF 1d (out when
 the close is more than 3% under a falling 50-day; baseline 466 / 380 / 26, 59 a day).
 STACK / SHEET RULE: a definition enters the stack when, on top of 1d, it keeps 56/56 and 26/26 and removes >= 1 more
 graded "no" and no ok / good. A sheet is drawn only if the stack removes >= 4 more "no" than 1d alone (>= 9 of 20).

REVISION (the ONE allowed; made after 02_pairs_v1.out, which is kept): A1 v1 FAILED the pairs — REN closed 0.6% ABOVE its
 50-day on the list night, so "close under the 50-day" is exactly the one-day reading the operator said is not the point.
    A1 v2  OUT when the 50-day is lower than 20 sessions ago AND the close is under the 200-DAY average AND the
           126-session return < T          (the long decline is read off the 200-day, not the 50-day on one day)
 A2, B1, B2 separated their pairs in v1 and are UNCHANGED. Sizing, plateau, table and stack rules unchanged.
 Disclosed: the v1 pair printout showed the six rows' raw components, including the 200-day ratio (THC 0.89, REN 0.92,
 APT 1.75, BE 1.56) — the new leg was chosen seeing those six rows and nothing else.

    python3 scripts/probes/_717_context_1114/02_score.py pairs > .../02_pairs_v1.out      (v1, before any revision)
    python3 scripts/probes/_717_context_1114/02_score.py       > .../02_score.out            (v2: pairs again, then the score)
"""
import os, sys
import numpy as np, pandas as pd
import ctx
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 60)
HERE = ctx.HERE
MODE = sys.argv[1] if len(sys.argv) > 1 else "score"
f, sc, hi, hi_all, gr, nights, cal, WF, WX = ctx.load()
MF = "/Users/alvinfung/apollo_data/bv1_context_1114/fires_ctx_measures.parquet"
if not os.path.exists(MF):
    os.makedirs(os.path.dirname(MF), exist_ok=True)
    parts = [ctx.measures(WF[a:a + 20000], f.base_len.to_numpy()[a:a + 20000]) for a in range(0, len(f), 20000)]
    m = pd.concat(parts, ignore_index=True); m.index = f.index; m.to_parquet(MF)
mf = pd.read_parquet(MF); assert (mf.index == f.index).all()
f = f.join(mf)
def add(d):
    m = ctx.measures(WX[d.w.to_numpy()], d.base_len.to_numpy()); m.index = d.index
    return d.join(m)
sc, hi = add(sc), add(hi)
gr = gr.join(mf.loc[[f.index[w] for w in gr.w]].reset_index(drop=True))
gr["sheet"] = gr.sheet.map(lambda p: {"sheet_model_picks.png": "1 (11-13)", "sheet_template_picks.png": "2 (11-13)", "sheet_stack_dollar_volume_picks.png": "3 (11-14)"}[os.path.basename(p)])
NO, OKG, COND = gr[gr.grade == "no"], gr[gr.grade.isin(["ok", "good"])], gr[gr.grade == "conditional"]
ONE_D = lambda d: ~((d.u50 < -0.03) & (d.s50_chg10 < 0))
TRUE = lambda d: pd.Series(True, index=d.index)
BIGF = sc[(sc.fired == 1) & (sc.big == 1)]

# ── sizing: the cut that removes the most while keeping the 56 and every big winner (its best fired session)
def constraints(col, side, fixed):
    """-> sorted list of (value, who): one per listed High buy meeting `fixed`, one per big winner whose EVERY fired session meets `fixed`."""
    out = [(float(v), f"{t} {e}") for v, t, e in zip(hi[col], hi.ticker, hi.E) if v == v] if fixed is None else \
          [(float(v), f"{t} {e}") for v, t, e, k in zip(hi[col], hi.ticker, hi.E, fixed(hi)) if k and v == v]
    for key, g in BIGF.groupby("key"):
        fx = np.ones(len(g), bool) if fixed is None else fixed(g).to_numpy()
        if fx.all() and g[col].notna().all():
            v = g[col].max() if side == "min" else g[col].min()
            out.append((float(v), f"{g.ticker.iloc[0]} {g.E.iloc[0]} (big)"))
    return sorted(set(out), reverse=(side == "max"))
def sized(col, side, fixed=None, cap=None, k=1):
    cs = constraints(col, side, fixed)
    T = cs[k - 1][0] if len(cs) >= k else cap
    if cap is not None and T is not None:
        T = min(T, cap) if side == "min" else max(T, cap)
    if T is None:
        return TRUE, None, cs
    beyond = (lambda d: d[col] < T) if side == "min" else (lambda d: d[col] > T)
    return (lambda d: ~(beyond(d) & (TRUE(d) if fixed is None else fixed(d)))), T, cs

FALL = lambda n: (lambda d: d[f"s50_chg{n}"] < 0)
DEFS_V1 = {
    "A1 falling 50d + under it + 126d return": dict(col="ret126", side="min", fixed=lambda d: FALL(20)(d) & (d.u50 < 0), cap=0.0),
    "A2 falling 50d + 126d return":            dict(col="ret126", side="min", fixed=FALL(20), cap=0.0),
    "B1 last-5 bars vs the base's earlier":    dict(col="tr5_base", side="max"),
    "B2 wide bars in the last 10":             dict(col="wide10", side="max"),
}
DEFS = DEFS_V1
DEFS_V2 = dict(DEFS_V1)
del DEFS_V2["A1 falling 50d + under it + 126d return"]
A1F = lambda n: (lambda d: FALL(n)(d) & (d.sma200_ratio < 1))
DEFS_V2 = {"A1 falling 50d + under 200d + 126d return": dict(col="ret126", side="min", fixed=A1F(20), cap=0.0), **DEFS_V2}
for _n, _mk in (("A1 falling 50d + under 200d + 126d return", A1F), ("A2 falling 50d + 126d return", FALL)):
    DEFS_V2[_n] = dict(DEFS_V2[_n], plateau=[(f"50-day fall over {k}", dict(col="ret126", side="min", fixed=_mk(k), cap=0.0)) for k in (5, 10, 20)])
if MODE != "pairs":
    DEFS = DEFS_V2

# ── pair validation (fire rows of the era-A capture; D = the night before the buy day)
PAIRS = [("A", "THC", "2017-05-10", True), ("A", "REN", "2017-07-28", True), ("A", "APT", "2020-06-17", False), ("A", "BE", "2020-08-13", False),
         ("B", "TWTR", "2018-02-08", True), ("B", "JMIA", "2020-11-18", False)]
pr = pd.concat([f[(f.ticker == t) & (f.Ed == E)] for _, t, E, _ in PAIRS]); assert len(pr) == 6
RAW = ["u50", "s50_chg5", "s50_chg10", "s50_chg20", "ret126", "sma200_ratio", "runup6m_adr", "off_high_adr", "hh_age", "base_len",
       "tr5_base", "cc5_base", "wide10", "wide5", "tr5_prev15", "tr10_prev20", "tr3_prev10", "trmax5_med20", "cc10_prev20"]
print("== PAIR VALIDATION — raw components of the six rows (fire rows) ==")
print(pr[["ticker", "Ed"] + RAW].round(3).to_string(index=False))
print("bridge — the same measures on the scorecard rows of the three Qullamaggie buys (other bar path):")
print(sc[sc.ticker.isin(["APT", "BE", "JMIA"]) & sc.E.isin(["2020-06-17", "2020-08-13", "2020-11-18"])][["ticker", "E", "fired", "big"] + [c for c in RAW if c in sc.columns]].round(3).to_string(index=False))
CHECKS, THR, CONS = {}, {}, {}
for nm, d in DEFS.items():
    CHECKS[nm], THR[nm], CONS[nm] = sized(d["col"], d["side"], d.get("fixed"), d.get("cap"))
print("\nthresholds (from the 56 + the 26 big winners only) and the pair verdicts:")
ALLOK = True
for nm in DEFS:
    fam = nm[0]
    v = []
    for fm, t, E, want in PAIRS:
        if fm == fam:
            out = not bool(CHECKS[nm](pr[(pr.ticker == t)]).iloc[0])
            v.append(f"{t} {'OUT' if out else 'kept'} ({'ok' if out == want else 'WRONG'})"); ALLOK &= (out == want)
    print(f"  {nm:42s} T = {THR[nm]}  set by {CONS[nm][:3]}  ->  " + "; ".join(v))
print("ALL PAIRS SEPARATED AS HE SAYS:", ALLOK)
if MODE == "pairs":
    sys.exit()

# ── bridge (the shape card's numbers must reproduce before anything new)
per0 = f.groupby("ci").size().reindex(nights).fillna(0)
L0, F0, B0 = sc.key.nunique(), sc.key[sc.fired == 1].nunique(), sc.key[(sc.fired == 1) & (sc.big == 1)].nunique()
print(f"\nBRIDGE: scorecard listed / fired / big winners = {L0} / {F0} / {B0} (expect 479 / 386 / 26); listed High-tier buys {len(hi)} (expect 56); era-A fires a day median {per0.median():.0f} (expect 68) over {len(nights)} nights; "
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
    print(f"{name:46s} | {int(hk.sum()):2d}/56 | {L:3d} / {F:3d} / {B:2d} | lost H{tier['High']} M{tier['Medium']} L{tier['Low']} N{tier['Not']} | no {len(rn):2d}/{len(NO)} ok-good {len(ro)}/{len(OKG)} maybe {len(rc)}/{len(COND)} | {per.median():4.0f} {per.mean():6.1f} | {repl:5.1%} | "
          f"High dropped: {', '.join(f'{r.ticker} {r.E}' for r in hd.itertuples()) or '-'}"
          f"{' | BIG WINNERS LOST: ' + ', '.join(f'{r.ticker} {r.E}' for r in bigl.itertuples()) if len(bigl) else ''}"
          f" | no removed: {' '.join(rn.ticker) or '-'}{' | OK/GOOD REMOVED: ' + ' '.join(ro.ticker) if len(ro) else ''}{' | maybe removed: ' + ' '.join(rc.ticker) if len(rc) else ''}")
    return dict(high=int(hk.sum()), L=L, F=F, B=B, no=len(rn), ok=len(ro), fires=per.median(), nos=set(rn.ticker))
HDR = (f"{'check':46s} | High  | scorecard listed/fired/big | fired buys lost by tier | his eye (IN-SAMPLE): removed of {len(NO)} no / {len(OKG)} ok-good / {len(COND)} maybe | fires a day median mean | "
       "top-5 dollar-volume picks replaced | names")

print("\n== THRESHOLDS (who sets each; how the 56 and the era-A fires sit) ==")
for nm, d in DEFS.items():
    col, side = d["col"], d["side"]
    out = ~CHECKS[nm](f)
    print(f"  {nm:42s} {col} {'<' if side == 'min' else '>'} {THR[nm]}  constraints (most binding first): {CONS[nm][:4]} | the 56 median {hi[col].median():.2f}; fires median {f[col].median():.2f}; fires OUT {out.mean():.1%}")

RES, RES1 = {}, {}
print("\n== EACH DEFINITION ALONE on the plain list (baseline first) ==\n" + HDR)
RES["baseline"] = score("baseline (no check)", TRUE)
RES["1d"] = score("1d (>3% under a falling 50-day)", ONE_D)
for nm, fn in CHECKS.items():
    RES[nm] = score(nm, fn)
print("\n== EACH DEFINITION ON TOP OF 1d (the 1d baseline: 56/56, 466 / 380 / 26, 59 a day) ==\n" + HDR)
for nm, fn in CHECKS.items():
    RES1[nm] = score("1d + " + nm, lambda d, fn=fn: ONE_D(d) & fn(d))

print("\n== PLATEAU, on top of 1d (3 points each) ==\n" + HDR)
for nm, d in DEFS.items():
    if "plateau" in d:
        for lab, dd in d["plateau"]:
            fn, T, _ = sized(dd["col"], dd["side"], dd.get("fixed"), dd.get("cap"))
            score(f"1d + {nm[:2]} {lab} T={T if T is None else round(T, 3)}", lambda x, fn=fn: ONE_D(x) & fn(x))
    else:
        for k in (1, 2, 3):
            fn, T, _ = sized(d["col"], d["side"], d.get("fixed"), d.get("cap"), k=k)
            score(f"1d + {nm[:2]} k={k} T={T if T is None else round(T, 3)}" + (" (loses must-keeps by construction)" if k > 1 else ""), lambda x, fn=fn: ONE_D(x) & fn(x))

print("\n== THE 36 GRADED PICKS — the measures and which definition removes each (x) ==")
g2 = gr.assign(out_1d=~ONE_D(gr), **{nm[:2]: np.where(CHECKS[nm](gr), ".", "x") for nm in DEFS})
cols = ["sheet", "card", "ticker", "Dd", "grade", "out_1d"] + [nm[:2] for nm in DEFS] + ["u50", "s50_chg20", "ret126", "runup6m_adr", "base_len", "tr5_base", "wide10", "tr5_prev15", "cc5_base"]
print(g2.sort_values(["grade", "out_1d", "ticker"])[cols].round(2).to_string(index=False))
print("\nthe 56 listed High-tier buys (quantiles):")
print(hi[["u50", "s50_chg20", "ret126", "tr5_base", "wide10", "tr5_prev15"]].describe(percentiles=[.1, .25, .5, .75, .9]).loc[["min", "10%", "25%", "50%", "75%", "90%", "max"]].round(2).to_string())
print("tier medians (scorecard sessions):")
print(sc.groupby("tier")[["ret126", "tr5_base", "wide10", "tr5_prev15"]].median().reindex(["High", "Medium", "Low", "Not"]).round(2).to_string())
print("era-A fires median:  " + "  ".join(f"{c} {f[c].median():.2f}" for c in ["ret126", "tr5_base", "wide10", "tr5_prev15"]))

print("\n== STACK (rule in PREREG), cumulative on top of 1d ==")
enter = [n for n in CHECKS if RES1[n]["high"] == 56 and RES1[n]["B"] == 26 and RES1[n]["no"] > RES["1d"]["no"] and RES1[n]["ok"] == 0]
print("definitions that pass the rule on top of 1d:", "; ".join(enter) or "NONE")
print(HDR)
cum, last = [], score("1d", ONE_D)
for n in enter:
    cum.append(n)
    last = score("+ " + n, lambda d, cc=tuple(cum): ONE_D(d) & np.logical_and.reduce([CHECKS[c](d) for c in cc]))
extra = last["no"] - RES["1d"]["no"]
sheet = bool(cum) and last["high"] == 56 and last["B"] == 26 and last["ok"] == 0 and extra >= 4
print(f"\nthe stack removes {extra} more 'no' than 1d alone ({last['no']} of {len(NO)}); SHEET RULE (>= 4 more, 56/56, 26/26, no ok/good): {'MET' if sheet else 'NOT MET'}")
dd = pd.DataFrame(DROPS, columns=["check", "set", "eid", "ticker", "E", "tier", "big"]).drop_duplicates()
dd.to_csv(os.path.join(HERE, "02_drops.tsv"), sep="\t", index=False)
open(os.path.join(HERE, "stack.txt"), "w").write("1d\n" + "\n".join(f"{c}\t{THR.get(c, '')}" for c in cum) + f"\nsheet\t{int(sheet)}\n")
