#!/usr/bin/env python3
"""#717 breakout GRADES A+ / A / B / C from the pick-model score (2026-11-15; offline, $0, ERA A ONLY — rows with a
breakout day E <= 2022-03-31; research, no rule changed, nothing deployed, nothing committed).

His idea 2026-11-14 (docs/methodology/operator_shared_notes.md): record a grade per listed breakout so the ranking can
be reviewed and A+ charts compared with the rest. Agreed: grade by the pick-model SCORE, cutoffs from Qullamaggie buy
rates per score band, shown to him before live.

PREREG — written BEFORE any number of this probe was computed. ALREADY SEEN (disclosed): _717_rank2_1114/01_rank2.out
(top-5 counts by ranking), coef.json. NOT seen: any score distribution, any buy rate by score.

POOL   /Users/alvinfung/apollo_data/bv1_rank2_1114/pool3_ranked.parquet = each night's names that BROKE OUT next day
       (fires) and pass the three live list checks, PM = the pick model's log-odds as fitted (coef.json primary).
       Every rate here is therefore "per name that broke out"; the live grade is stamped on list rows the night before.
ERAS   FIT  = E <= 2020-12-31 (also the pick model's own fit years -> in-sample for the score);
       TEST = 2021-01-01 <= E <= 2022-03-31. Cutoffs use FIT rows only; TEST is read once, after the cutoffs print.
LABEL  is_qm (the row is a Qullamaggie scorecard buy on that day).
RULE   1. base = the buy rate of ALL fit pool rows (sensitivity, one line: `covered` rows only).
       2. Calibration: an unpenalised 2-parameter logistic of is_qm on PM over the fit rows -> rate(PM).
       3. Cutoffs = the scores where the calibrated rate equals 4x, 2x and 1x base:
            A+ : rate(PM) >= 4x base     A : >= 2x     B : >= 1x     C : below 1x.
          A grade is a fixed score threshold -> the same score gets the same grade on any night; a night can have no A+.
       4. DEGENERATE (decided now): if the 4x cutoff lies above the fit rows' maximum score, or the A+ band holds fewer
          than 15 fit buy rows, A+ is dropped and three grades remain (A >= 2x, B >= 1x, C); the same test then on A
          (-> two grades). No other adjustment of the multiples after seeing data.
       5. CHECK printed beside the cutoffs (not used to move them): the EMPIRICAL fit buy rate per grade and per
          20 equal-count score bins.
"ABSOLUTE" DIAGNOSTICS (the score is built from within-night ranks, so this premise is tested, fit rows only): buy
       rate per grade by YEAR and by tercile of the night's pool size; on test: share of nights with no A+ name.
       If nearly every night has an A+ the grade means "top of tonight's list" and the report says so.
OUT-OF-SAMPLE TABLE (test): per grade — rows, median names a night (nights with none count as 0; a second column
       from the WHOLE list before the context checks, PM recomputed by 02_fit_test.load), distinct Qullamaggie buys,
       row buy rate, lift vs the TEST base rate, big winners, High-tier (scorecard_rows.tsv).
PASS BAR (test): grades SEPARATE his buys if the row buy rate falls in order A+ > A > B > C AND the day-resampled
       (1,000 draws of days, seed 1115) 90% interval of [A+ rate / C rate] lies above 1. The 4x/2x multiples are
       expected to shrink out of sample (in-sample score) — reaching them is NOT the bar.
ALSO   one line: how much A+ is just dollar volume (share of A+ rows in the night's dollar-volume top 5).

    python3 scripts/probes/_717_grades_1115/01_grades.py > scripts/probes/_717_grades_1115/01_grades.out
"""
import importlib.util, json, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
POOL = "/Users/alvinfung/apollo_data/bv1_rank2_1114/pool3_ranked.parquet"
FIT_LAST, TEST_FIRST, ERA_LAST = "2020-12-31", "2021-01-01", "2022-03-31"
MULT, MIN_BUYS, SEED = (("A+", 4.0), ("A", 2.0), ("B", 1.0)), 15, 1115
pd.set_option("display.width", 250)


def load_pool():
    p = pd.read_parquet(POOL, filters=[("E", "<=", ERA_LAST)])          # era A only, filtered at read
    assert p.E.max() <= ERA_LAST and p.E.min() >= "2017-01-01"
    p["qm"] = p.qm.map(lambda s: [x for x in s.split(",") if x])
    return p


def taken(x):
    return {i for l in x.qm for i in l}


def grade_of(pm, cuts):
    g = np.full(len(pm), "C", dtype=object)
    for name, c in reversed(cuts):                                       # lowest threshold first, higher overwrite
        g[np.asarray(pm) >= c] = name
    return g


def main():
    spec = importlib.util.spec_from_file_location("m", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/02_fit_test.py"))
    M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
    pool = load_pool()
    fit, test = pool[pool.E <= FIT_LAST], pool[pool.E >= TEST_FIRST]
    b = (len(pool), len(taken(fit[fit.rk_PM <= 5])), len(taken(test[test.rk_PM <= 5])))
    print("== BRIDGE rows / pick-model top-5 buys fit / test:", b, "(expect 114698, 71, 41; the saved pool has 114,847 rows — 149 break out on 2022-04-01, outside this probe's 2022-03-31 line, found at the bridge and disclosed)"); assert b == (114698, 71, 41)

    # ── cutoffs, FIT ONLY
    base = fit.is_qm.mean()
    print(f"\n== FIT 2017-01..2020-12: {len(fit):,} breakout rows, {int(fit.is_qm.sum())} buy rows, base rate {base:.5f} (1 in {1/base:.0f})")
    print(f"   sensitivity, covered rows only: {fit[fit.covered].is_qm.mean():.5f} on {int(fit.covered.sum()):,} rows")
    X = np.c_[np.ones(len(fit)), fit.PM.to_numpy(float)]
    beta, se, it = M.fit_logit(X, fit.is_qm.to_numpy(float), 0.0)
    print(f"   calibration: logit(rate) = {beta[0]:.4f} + {beta[1]:.4f} * score  (se {se[0]:.3f}, {se[1]:.3f}; {it} steps)")
    cuts = [(n, (np.log(m * base / (1 - m * base)) - beta[0]) / beta[1]) for n, m in MULT]
    print(f"   score range in fit: {fit.PM.min():.3f} .. {fit.PM.max():.3f}; raw cutoffs " + ", ".join(f"{n} {c:.4f}" for n, c in cuts))
    while cuts:
        n, c = cuts[0]; k = int(fit[fit.PM >= c].is_qm.sum())
        if c > fit.PM.max() or k < MIN_BUYS:
            print(f"   DEGENERATE: {n} band has {k} fit buy rows (minimum {MIN_BUYS}) -> dropped"); cuts = cuts[1:]
        else:
            break
    names = [n for n, _ in cuts] + ["C"]
    json.dump({"rule": "calibrated buy rate >= 4x / 2x / 1x the fit base rate", "fit_base_rate": base, "calibration": list(beta),
               "cutoffs_log_odds": dict(cuts)}, open(os.path.join(HERE, "cutoffs.json"), "w"), indent=1)
    pool["grade"] = grade_of(pool.PM, cuts); fit, test = pool[pool.E <= FIT_LAST], pool[pool.E >= TEST_FIRST]
    print("\n== CUTOFFS (score = the pick model's log-odds, `pick_score`) ==")
    for (n, c), (_, m) in zip(cuts, [x for x in MULT if x[0] in names]):
        r = m * base
        print(f"   {n:2s}: score >= {c:8.4f}   calibrated rate at the cutoff {r:.4f} = 1 in {1/r:.0f} breakouts is his buy ({m:g}x base); plain sigmoid(score) {1/(1+np.exp(-c)):.5f}")
    print(f"   C : below {cuts[-1][1]:.4f}")
    def band(x, bs):
        g = x.groupby("grade").agg(rows=("is_qm", "size"), buy_rows=("is_qm", "sum")).reindex(names).fillna(0)
        g["rate"] = g.buy_rows / g.rows; g["lift_vs_base"] = g.rate / bs; g["one_in"] = 1 / g.rate; g["share_rows"] = g.rows / len(x)
        return g
    print("\n== CHECK, FIT, empirical per grade (in-sample) =="); print(band(fit, base).round(4).to_string())
    q = pd.qcut(fit.PM, 20, labels=False)
    v = fit.groupby(q).agg(lo=("PM", "min"), hi=("PM", "max"), rows=("is_qm", "size"), buys=("is_qm", "sum")); v["lift"] = v.buys / v.rows / base
    print("\n== CHECK, FIT, 20 equal-count score bins =="); print(v.round(3).to_string())

    print("\n== ABSOLUTE? FIT buy rate per grade by year (rows / rate) ==")
    y = fit.assign(year=fit.E.str[:4])
    print((y.pivot_table(index="year", columns="grade", values="is_qm", aggfunc="mean")[names] * 100).round(2).to_string(), "  (percent)")
    print(y.pivot_table(index="year", columns="grade", values="is_qm", aggfunc="size")[names].to_string(), "  (rows)")
    nday = fit.groupby("ci").ticker.transform("size"); ter = pd.qcut(nday.groupby(fit.ci).first(), 3, labels=["small", "mid", "large"])
    z = fit.assign(night=fit.ci.map(ter))
    print("\n== ABSOLUTE? FIT buy rate per grade by tercile of the night's pool size (percent, then rows) ==")
    print((z.pivot_table(index="night", columns="grade", values="is_qm", aggfunc="mean", observed=True)[names] * 100).round(2).to_string())
    print(z.pivot_table(index="night", columns="grade", values="is_qm", aggfunc="size", observed=True)[names].to_string())

    # ── TEST (once)
    df, cal, big = M.load()
    assert max(cal[c] for c in df.ci.unique()).isoformat() <= ERA_LAST and cal[-1].isoformat() < '2025-01-01'
    co = json.load(open(M.COEF))["models"]["primary"]
    df["PM"] = M.X_of(df, co["features"]) @ np.r_[co["intercept"], co["coef"]]; df["grade"] = grade_of(df.PM, cuts)
    df = df[df.E <= ERA_LAST]; lst = df[df.E >= TEST_FIRST]; nights = np.sort(lst.ci.unique())
    sc = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_reasons_1114/scorecard_rows.tsv"), sep="\t", dtype={"eid": str})
    tier = {("d" if s == "dated" else "w") + e: t_ for s, e, t_ in zip(sc.set, sc.eid, sc.tier)}
    tb = test.is_qm.mean(); rows = []
    for g in names + ["ALL"]:
        x = test if g == "ALL" else test[test.grade == g]; xl = lst if g == "ALL" else lst[lst.grade == g]; ids = taken(x)
        rows.append(dict(grade=g, rows=len(x), names_a_night_median=x.groupby("ci").size().reindex(nights).fillna(0).median(),
                         whole_list_names_a_night_median=xl.groupby("ci").size().reindex(nights).fillna(0).median(),
                         qm_buys=len(ids), buy_rows=int(x.is_qm.sum()), buy_rate_pct=round(100 * x.is_qm.mean(), 3), one_in=round(1 / x.is_qm.mean()) if x.is_qm.sum() else None,
                         lift_vs_test_base=round(x.is_qm.mean() / tb, 2), big_winners=len(ids & big), high_tier=sum(tier.get(i) == "High" for i in ids),
                         share_of_buys_pct=round(100 * len(ids) / max(1, len(taken(test))), 1)))
    res = pd.DataFrame(rows); res.to_csv(os.path.join(HERE, "01_oos_table.tsv"), sep="\t", index=False)
    print(f"\n== OUT OF SAMPLE 2021-01..2022-03: {len(test):,} breakout rows on {len(nights)} nights, test base rate {tb:.5f} (1 in {1/tb:.0f}); fit base was {base:.5f} ==")
    print("   names_a_night_median = names that broke out and pass the checks; whole_list = every listed name (before the context checks)")
    print(res.to_string(index=False))
    top = names[0]; has = test[test.grade == top].groupby("ci").size().reindex(nights).fillna(0)
    hl = lst[lst.grade == top].groupby("ci").size().reindex(nights).fillna(0)
    print(f"\n   nights with NO {top}: among breakouts {int((has == 0).sum())} of {len(nights)} ({100*(has == 0).mean():.0f}%); on the whole list {int((hl == 0).sum())} of {len(nights)} ({100*(hl == 0).mean():.0f}%)")
    print(f"   whole list, {top} names a night: min {hl.min():.0f}, 10th pct {hl.quantile(.1):.0f}, median {hl.median():.0f}, 90th pct {hl.quantile(.9):.0f}, max {hl.max():.0f}")
    rate = [r["buy_rate_pct"] for r in rows[:-1]]; mono = all(a > b_ for a, b_ in zip(rate, rate[1:]))
    per = {g: (test[test.grade == g].groupby("ci").is_qm.sum().reindex(nights).fillna(0).to_numpy(), test[test.grade == g].groupby("ci").size().reindex(nights).fillna(0).to_numpy()) for g in (top, "C")}
    dr = np.random.default_rng(SEED).integers(0, len(nights), size=(1000, len(nights)))
    ra = per[top][0][dr].sum(1) / per[top][1][dr].sum(1); rc = per["C"][0][dr].sum(1) / per["C"][1][dr].sum(1)
    ok = rc > 0; lo, hi = np.percentile(ra[ok] / rc[ok], [5, 95])
    print(f"\n== PASS BAR: rates in order {' > '.join(names)}: {rate} -> {'YES' if mono else 'NO'}; {top} rate / C rate = {rate[0]/rate[-1]:.1f}x, day-resampled 90% {lo:.1f}x .. {hi:.1f}x ({int((~ok).sum())} draws with no C buy dropped) -> {'above 1' if lo > 1 else 'NOT above 1'}")
    print(f"   VERDICT: grades {'SEPARATE' if mono and lo > 1 else 'DO NOT SEPARATE'} his buys out of sample")
    ty = test.assign(q=test.E.str[:4] + "Q" + ((test.E.str[5:7].astype(int) + 2) // 3).astype(str))
    print("\n== TEST by quarter: buy rate percent, then rows ==")
    print((ty.pivot_table(index="q", columns="grade", values="is_qm", aggfunc="mean")[names] * 100).round(2).to_string())
    print(ty.pivot_table(index="q", columns="grade", values="is_qm", aggfunc="size")[names].to_string())
    a = test[test.grade == top]
    print(f"\n== DOLLAR VOLUME: {top} rows in the night's dollar-volume top 5: {100*(a.rk_R0 <= 5).mean():.0f}%; median dollar-volume percentile in the night's list by grade: "
          + ", ".join(f"{g} {test[test.grade == g].f_dollar_vol20.median():.2f}" for g in names))
    print("   A+ buys out of sample:", ", ".join(sorted(f"{t} {E}" for t, E in zip(a[a.is_qm].ticker, a[a.is_qm].E))))


if __name__ == "__main__":
    main()
