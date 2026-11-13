#!/usr/bin/env python3
"""#717 pick model — bridge check, FIT (2017-2020), one TEST (2021-01 .. 2022-04-01). Registration:
docs/analysis/cb_pick_model_2026-11-13.md (committed 730db6c7 BEFORE this file ran). Offline, $0, read-only; reads only
the 01 capture (era A list rows at the 4% floor), the Qullamaggie scorecard fixture and his positions panel. No rule
is changed; returns are not read.

    python3 scripts/probes/_717_pick_model_1113/02_fit_test.py bridge > .../02_bridge.out
    python3 scripts/probes/_717_pick_model_1113/02_fit_test.py fit    > .../02_fit.out      (writes coef.json)
    python3 scripts/probes/_717_pick_model_1113/02_fit_test.py test   > .../02_test.out     (reads coef.json; ONCE)
"""
import importlib.util, json, os, sys
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("p02", os.path.join(HERE, "..", "_717_precision_1112", "02_picks.py"))
P2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(P2)
P = P2.P
CAPTURE = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
COEF = os.path.join(HERE, "coef.json")
WIN, SLOTS, SEED, LAM, LABEL_FWD = P.WIN, P.SLOTS, 717, 1.0, 2
FIT_LAST, TEST_FIRST = "2020-12-31", "2021-01-01"
PCT = ["rs_1m", "rs_3m", "rs_6m", "prior_move", "runup6m", "depth_adr", "base_len", "spread10_adr", "adr20", "dollar_vol20",
       "dist_52w", "dist_level", "vs_ema21_adr", "since_low", "group_strength"]          # percentile within the night's list
PRIMARY = PCT[:14] + ["first_base", "group_strength"]                                     # features 1-16, registration order
SECONDARY = PRIMARY + ["gap_adr", "open_above"]
PLAIN = {"rs_1m": "1-month strength rank", "rs_3m": "3-month strength rank", "rs_6m": "6-month strength rank",
         "prior_move": "run-up into the base", "runup6m": "6-month move", "depth_adr": "base depth (in daily ranges)",
         "base_len": "base length", "spread10_adr": "last-10-close spread (high = loose)", "adr20": "daily range (ADR)",
         "dollar_vol20": "dollar volume", "dist_52w": "closeness to the 52-week high", "dist_level": "distance below the buy level",
         "vs_ema21_adr": "close above the 21-day average", "since_low": "sessions since the major low",
         "first_base": "first base since the major low (0/1)", "group_strength": "industry group strength",
         "gap_adr": "opening gap (in daily ranges)", "open_above": "opens above the level (0/1)"}


def load():
    df = pd.read_parquet(CAPTURE)
    cal = [date.fromisoformat(s) for s in open(CAPTURE + ".cal.txt").read().split()]
    assert cal[-1] < date(2025, 1, 1)
    df["E"] = [cal[c + 1].isoformat() for c in df.ci]
    df["score_order"] = P2.order_score(df)                    # `rank_rows` inside the night's 4% list
    df["dist_level"] = (df.level / df.close - 1) / df.adr20
    df["gap_adr_raw"] = (df.oE / df.close - 1) / df.adr20
    g = df.groupby("ci")
    for c in PCT:
        df["f_" + c] = g[c].rank(pct=True).fillna(0.5)
    df["f_gap_adr"] = g.gap_adr_raw.rank(pct=True).fillna(0.5)
    df["f_first_base"] = (df.bases_before == 0).astype(float)
    df["f_open_above"] = (df.oE > df.level).astype(float)
    # ── Qullamaggie: the panel's bought +-5 and covered days, and the scorecard ids — the 02_picks.py code path
    e = pd.read_csv(f"{P.HOLD}/entries.tsv", sep="\t", dtype=str, keep_default_na=False)
    snaps = pd.read_csv(f"{P.HOLD}/snapshots.tsv", sep="\t", dtype=str, keep_default_na=False)
    snap_ci = np.array(sorted({np.searchsorted(cal, date.fromisoformat(x)) for x in snaps.date if x and date.fromisoformat(x) <= cal[-1]}))
    def ci_at(s, side):
        d = date.fromisoformat(s); i = int(np.searchsorted(cal, d, "left"))
        return i if (i < len(cal) and cal[i] == d) or side == "lo" else i - 1
    bought = {}
    for r in e.itertuples():
        if r.initial == "True":
            continue
        if r.E:
            if date.fromisoformat(r.E) > cal[-1]:
                continue
            b0 = b1 = ci_at(r.E, "lo")
        elif r.lo and r.hi and int(r.window_len or 99) <= 10 and date.fromisoformat(r.lo) <= cal[-1]:
            b0, b1 = ci_at(r.lo, "lo"), ci_at(r.hi, "hi")
        else:
            continue
        bought.setdefault(r.sym_a or r.sym, []).append((b0 - WIN, b1 + WIN))
    eci = df.ci.to_numpy() + 1
    df["bought"] = [any(a <= c <= b for a, b in bought.get(t, ())) for t, c in zip(df.ticker, eci)]
    pos = np.searchsorted(snap_ci, eci)
    df["covered"] = np.minimum(np.abs(snap_ci[np.clip(pos, 0, len(snap_ci) - 1)] - eci), np.abs(snap_ci[np.clip(pos - 1, 0, len(snap_ci) - 1)] - eci)) <= WIN
    last_e = cal[int(df.ci.max()) + 1].isoformat()
    by_t, big_ids, win_ci = {}, set(), {}
    b = pd.read_csv(f"{P2.FX}/buys.tsv", sep="\t", dtype=str, keep_default_na=False)
    w = pd.read_csv(f"{P2.FX}/buys_undated_widened.tsv", sep="\t", dtype=str, keep_default_na=False)
    for bid, t, lo, hi, big in [("d" + r.eid, r.ticker, r.E, r.E, r.big_winner == "1") for r in b.itertuples()] + [("w" + r.eid, r.ticker, r.lo, r.hi, False) for r in w.itertuples()]:
        if hi <= last_e:
            by_t.setdefault(t, []).append((bid, lo, hi))
            win_ci.setdefault(t, []).append((ci_at(lo, "lo"), ci_at(hi, "hi")))
            if big:
                big_ids.add(bid)
    df["qm"] = [[bid for bid, lo, hi in by_t.get(t, ()) if lo <= E <= hi] for t, E in zip(df.ticker, df.E)]
    df["is_qm"] = df.qm.map(bool)
    # the FIT label: a scorecard buy of the ticker inside E .. E+2 sessions
    df["y"] = [any(a <= c + LABEL_FWD and b_ >= c for a, b_ in win_ci.get(t, ())) for t, c in zip(df.ticker, eci)]
    return df, cal, big_ids


def taken_set(x):
    return {i for l in x.qm for i in l}


def X_of(d, feats):
    return np.c_[np.ones(len(d)), d[["f_" + f for f in feats]].to_numpy(float)]


def fit_logit(X, y, lam):
    """L2 logistic by Newton steps; the intercept (column 0) is not penalised. -> (beta, standard errors)."""
    b = np.zeros(X.shape[1]); pen = np.r_[0.0, np.full(X.shape[1] - 1, lam)]
    for it in range(100):
        p = 1 / (1 + np.exp(-X @ b))
        grad = X.T @ (y - p) - pen * b
        H = (X * (p * (1 - p))[:, None]).T @ X + np.diag(pen)
        step = np.linalg.solve(H, grad); b = b + step
        if np.abs(step).max() < 1e-10:
            break
    return b, np.sqrt(np.diag(np.linalg.inv(H))), it + 1


def stage_bridge():
    df, cal, big = load()
    nights = sorted(df.ci.unique())
    f = df[df.fire]
    per = f.groupby("ci").size().reindex(nights).fillna(0)
    s = taken_set(f); t5 = taken_set(P2.top_k(f, f.score_order))
    lst = df.groupby("ci").size().reindex(nights).fillna(0)
    print(f"BRIDGE to 03_adr_floor.out, the 4.00% row (expect: listed median 190, fires median 68, fired buys 375 / 26 big, order-score top 5 takes 50 / 5 big)")
    print(f"this capture: {len(nights)} nights {cal[nights[0]]} .. {cal[nights[-1]]}; listed median {lst.median():.0f}; fires median {per.median():.0f}; "
          f"fired buys {len(s)} / {len(s & big)} big; order-score top 5 takes {len(t5)} / {len(t5 & big)} big")
    ok = (lst.median(), per.median(), len(s), len(s & big), len(t5), len(t5 & big)) == (190, 68, 375, 26, 50, 5)
    print("BRIDGE", "OK" if ok else "MISMATCH — STOP")
    print(f"\nfeature coverage on the {len(df):,} list rows (share missing before the 0.5 fill): " +
          ", ".join(f"{c} {df[c].isna().mean():.2%}" for c in PCT if df[c].isna().any()) or "none missing")
    print(f"industry code present: list rows {df.has_sic.mean():.1%}, fires {f.has_sic.mean():.1%}; group strength present (a group of 10+): list {df.group_strength.notna().mean():.1%}")
    print(f"first base (no earlier base since the major low): list rows {(df.bases_before == 0).mean():.1%}; sessions of history at D under 252: {(df.bars_to_d < 252).mean():.1%} of rows")
    sys.exit(0 if ok else 1)


def stage_fit():
    df, cal, big = load()
    tr = df[df.fire & df.covered & (df.E <= FIT_LAST)]
    y = tr.y.to_numpy(float)
    print(f"FIT rows: fires on covered days, E {tr.E.min()} .. {tr.E.max()}: {len(tr):,} rows on {tr.ci.nunique()} days; label (a Qullamaggie buy in E..E+{LABEL_FWD} sessions) = 1 on {int(y.sum())} rows ({y.mean():.2%}); "
          f"by year {tr[tr.y].E.str[:4].value_counts().sort_index().to_dict()}")
    print(f"industry code on the label rows: {tr[tr.y].has_sic.mean():.1%} (all fit rows {tr.has_sic.mean():.1%})")
    out = {"registration": "docs/analysis/cb_pick_model_2026-11-13.md", "lambda": LAM, "fit_rows": len(tr), "fit_positives": int(y.sum()), "models": {}}
    for name, feats in (("primary", PRIMARY), ("secondary", SECONDARY)):
        bta, se, it = fit_logit(X_of(tr, feats), y, LAM)
        out["models"][name] = {"features": feats, "intercept": float(bta[0]), "coef": [float(v) for v in bta[1:]], "se": [float(v) for v in se[1:]]}
        print(f"\n== {name.upper()} — logistic, L2 {LAM}, {it} Newton steps; intercept {bta[0]:+.3f} ==")
        print("  each feature is its 0..1 rank inside the night's list, so a coefficient = the log-odds change from the bottom to the top of the list; odds x = exp(coef)")
        print(f"  {'feature':46s} {'coef':>7s} {'se':>6s} {'z':>6s} {'odds x':>7s}")
        for k in np.argsort(-np.abs(bta[1:])):
            print(f"  {PLAIN[feats[k]]:46s} {bta[k + 1]:+7.2f} {se[k + 1]:6.2f} {bta[k + 1] / se[k + 1]:+6.1f} {np.exp(bta[k + 1]):7.2f}")
        # in-sample, informational: the bar's reading on the FIT years
        ftr = df[df.fire & (df.E <= FIT_LAST)]
        sc = pd.Series(X_of(ftr, feats) @ bta, index=ftr.index)
        a, o, dv = (taken_set(P2.top_k(ftr, s_)) for s_ in (sc, ftr.score_order, ftr.dollar_vol20))
        print(f"  in-sample (FIT years, all days, top 5 fires a day): model {len(a)} ({len(a & big)} big) | order score {len(o)} ({len(o & big)}) | dollar volume {len(dv)} ({len(dv & big)}) | fired {len(taken_set(ftr))}")
    json.dump(out, open(COEF, "w"), indent=1)
    print(f"\ncoefficients written to {COEF}")


def stage_test():
    df, cal, big = load()
    co = json.load(open(COEF))
    for name, m in co["models"].items():
        df["score_" + name] = X_of(df, m["features"]) @ np.r_[m["intercept"], m["coef"]]
    te = df[df.E >= TEST_FIRST].copy()
    f = te[te.fire]
    days = sorted(te.ci.unique()); nD = len(days)
    fired = taken_set(f)
    rng = np.random.default_rng(SEED)
    f = f.assign(score_random=rng.random(len(f)))
    print(f"TEST — scored once. Days E {te.E.min()} .. {te.E.max()}: {nD} days ({te[te.covered].ci.nunique()} with a positions snapshot within +-5 sessions); "
          f"list rows {len(te):,}, fires {len(f):,} (median {f.groupby('ci').size().reindex(days).fillna(0).median():.0f} a day)")
    print(f"Qullamaggie's scorecard buys that FIRE on the test days: {len(fired)} ({len(fired & big)} big winners); fire rows landing on one: {int(f.is_qm.sum())}")
    cap = f[f.is_qm].groupby("ci").size()
    print(f"ceiling with 5 slots a day: {int(cap.clip(upper=SLOTS).sum())} of {int(cap.sum())} name-days (most on one day {int(cap.max())})")

    def per_day_sets(x):
        d = {c: set() for c in days}
        for c, l in zip(x.ci, x.qm):
            d[c].update(l)
        return d

    def row(name, x):
        s = taken_set(x); c = x[x.covered]
        print(f"  {name:44s} buys taken {len(s):>3d}  big {len(s & big):>2d} | picks {len(x):>5,d}  on a Qullamaggie buy {int(x.is_qm.sum()):>3d} = {x.is_qm.mean():6.2%} of picks, {x.is_qm.sum() / nD:.3f} a day | bought +-5 (covered days) {c.bought.mean():6.2%} (n={len(c):,})")
        return per_day_sets(x)

    print("\n== THE BAR: the day's top 5 fires by each ranking (all 5 slots free daily) ==")
    S = {}
    for name, col in (("MODEL (primary: night-before features)", "score_primary"), ("ORDER SCORE (live)", "score_order"), ("DOLLAR VOLUME (high first)", "dollar_vol20"),
                      ("model, secondary (+ the opening gap)", "score_secondary"), ("5 at random (seed 717)", "score_random")):
        S[col] = row(name, P2.top_k(f, f[col]))
    rs = []
    for k in range(200):
        r_ = np.random.default_rng(1000 + k)
        rs.append(len(taken_set(P2.top_k(f, pd.Series(r_.random(len(f)), index=f.index)))))
    print(f"  5 at random, mean of 200 draws: buys taken {np.mean(rs):.1f} (5th-95th {np.percentile(rs, 5):.0f}-{np.percentile(rs, 95):.0f})")
    print(f"  all fires (no ranking, {len(f) / nD:.0f} a day): buys taken {len(fired)}  big {len(fired & big)}")

    print("\n== THE REGISTERED COMPARISON (1,000 resamples of test DAYS, seed 717; 90% interval of the difference in distinct buys taken) ==")
    brng = np.random.default_rng(SEED)
    draws = brng.integers(0, nD, size=(1000, nD))
    def boot(col):
        sets = [S[col][c] for c in days]
        return np.array([len(set().union(*(sets[i] for i in d))) for d in draws])
    bm = boot("score_primary")
    verdicts = {}
    for other, lab in (("score_order", "order score"), ("dollar_vol20", "dollar volume")):
        d = bm - boot(other)
        lo, hi = np.percentile(d, [5, 95])
        point = len(set().union(*S["score_primary"].values())) - len(set().union(*S[other].values()))
        verdicts[lab] = point > 0 and lo > 0
        print(f"  model minus {lab}: {point:+d} buys (90% interval {lo:+.0f} .. {hi:+.0f}) -> {'beats it' if verdicts[lab] else 'NOT SHOWN'}")
    print("  VERDICT: " + ("PASS — the model beats the order score" + ("" if verdicts["dollar volume"] else "; dollar volume alone does as well") if verdicts["order score"] else "NOT SHOWN"))
    for y_ in sorted(set(f.E.str[:4])):
        fy = f[f.E.str[:4] == y_]
        print(f"  {y_}: fired {len(taken_set(fy))} | model {len(taken_set(P2.top_k(fy, fy.score_primary)))} | order score {len(taken_set(P2.top_k(fy, fy.score_order)))} | dollar volume {len(taken_set(P2.top_k(fy, fy.dollar_vol20)))}")

    print("\n== SLOT MECHANICS PROXY (test days; daily bars cannot see WHICH name breaks first — a bracket, not a measurement) ==")
    def line(name, x, extra=""):
        s = taken_set(x)
        print(f"  {name:66s} buys/day {len(x) / nD:5.2f} | buys taken {len(s):>3d}  big {len(s & big):>2d} | on a Qullamaggie buy {x.is_qm.mean() if len(x) else 0:6.2%} of buys{extra}")
    for lab, col in (("MODEL", "score_primary"), ("ORDER SCORE", "score_order")):
        print(f" ranking = {lab}")
        xa, seats = P2.live_like(te, te[col], "fire", 0)
        line("R as wired: top 5 of the LIST rest at 09:35, buy only if it breaks", xa, f" | {len(xa) / max(1, seats):.0%} of resting seats broke out")
        line("K break-only, best case: the day's top 5 FIRES by the ranking", P2.top_k(f, f[col]))
        pr = f.groupby("ci")[col].rank(pct=True)
        line("G break-only, open-first: above the level at the open first, then by rank", P2.top_k(f, pr + f.f_open_above))
        lr = te.groupby("ci")[col].rank(ascending=False, method="first")
        for n in (10, 20, 40):
            sub = f[lr.reindex(f.index) <= n]
            vals = []
            for k in range(200):
                r_ = np.random.default_rng(2000 + k)
                vals.append(len(taken_set(P2.top_k(sub, pd.Series(r_.random(len(sub)), index=sub.index)))))
            x = P2.top_k(sub, pd.Series(np.random.default_rng(SEED).random(len(sub)), index=sub.index))
            line(f"N break-only, order-blind: only the top {n} of the list may buy", x, f" | mean of 200 draws {np.mean(vals):.1f}; eligible fires a day {len(sub) / nD:.1f}")
    line("Z break-only, no ranking: 5 fires at random (seed 717)", P2.top_k(f, f.score_random))
    print(f"  share of fires already above the level at the open: {f.f_open_above.mean():.1%}; of Qullamaggie-buy fire rows: {f[f.is_qm].f_open_above.mean():.1%}")
    print("  cannot see: the minute of each break (so who takes a seat first), the too-wide cancel minute (the daily low is used), slots still held from earlier days (all 5 free each morning here).")


if __name__ == "__main__":
    {"bridge": stage_bridge, "fit": stage_fit, "test": stage_test}[sys.argv[1]]()
