#!/usr/bin/env python3
"""#717 reasons -> checks: the CAPTURE (2026-11-14; offline, $0, read-only, ERA A ONLY; research, no rule changed).

ONE measures function (`reason_measures`, bars <= the watch night D only — never the breakout day's bar), run on:
  fixtures : every listed session of Qullamaggie's 757 scorecard buys (`rating.load()`, the any-session-in-window logic of
             `_717_qm_confidence_1111/13_head_to_head.py`) and the 84 High-tier buys (as tests/test_breakout_v1_range_break.py)
             -> scorecard_rows.tsv, high_rows.tsv (in this folder)
  eraA     : every FIRE row of the 11-13 capture (`list_eraA_4pct.parquet`, the 4% floor; bars = cb702_pre_v2 via
             `P.setup()`, which asserts the calendar ends before 2025; `cb702/` is NOT opened) -> fires_measures.parquet
Raw continuous values are stored; every threshold is post-processing (`02_score.py`).

    python3 scripts/probes/_717_reasons_1114/01_measure.py fixtures > .../01_fixtures.out
    python3 scripts/probes/_717_reasons_1114/01_measure.py eraA     > .../01_eraA.out
"""
import csv, gzip, importlib.util, json, math, os, sys, time
from collections import defaultdict
from datetime import date
from multiprocessing import get_context

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
os.chdir(REPO); sys.path.insert(0, REPO)
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402

TPL = json.load(open(os.path.join(REPO, "scripts/probes/_717_pick_model_1113/template.json")))
TPL_MEAN, TPL_W, TPL_MIN_N = np.array(TPL["mean"]), int(TPL["W"]), 40
OUT_FIRES = "/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"     # outside git
GAP_LOOK, PIV_LOOK, PIV_HALF, HH_LOOK = 30, 60, 2, 126
MEAS = ["u50", "s50_chg5", "s50_chg10", "s50_chg20", "hh_age", "off_high_adr", "runup6m_adr", "prior_move_adr", "pole_low_age",
        "piv_ll_adr", "n_piv", "gap_dn_adr", "gap_dn_age", "gap_any_adr", "rng5_over_adr", "rng10_over_adr", "rng5_med", "rng3_max_over_adr",
        "spread10_adr", "tpl_dist", "higher_lows", "no_lower_low", "low_not_today", "ema21_not_falling", "base_len"]


def reason_measures(bars, D, P, adr, level):
    """Every measure at the watch night D from bars <= D. `P` = v1's pole top, `adr` = ADR20(D) (a fraction), `level` = the buy level."""
    o, h, l, c = (np.asarray(x[:D + 1], float) for x in (bars.o, bars.h, bars.l, bars.c))
    m = {}
    # 1 — the 50-day
    def sma(i):
        return float(c[i - 49:i + 1].mean()) if i >= 49 else float("nan")
    s50 = sma(D)
    m["u50"] = c[D] / s50 - 1.0                                   # < 0 = the close is under the 50-day
    for k in (5, 10, 20):
        m[f"s50_chg{k}"] = (s50 / sma(D - k) - 1.0) / adr         # the 50-day's change over k sessions, in daily ranges (< 0 = falling)
    # 2 — the run-up: how old the 6-month high is, how far under it the buy level sits, how big the run was
    a = max(0, D - HH_LOOK + 1)
    k = a + int(np.flatnonzero(h[a:D + 1] == h[a:D + 1].max())[-1])
    m["hh_age"] = D - k
    m["off_high_adr"] = (h[k] - level) / h[k] / adr
    ru = bv.runup6m_at(bars, D)
    m["runup6m_adr"] = ru / adr if ru is not None else float("nan")
    pl = P - bv.POLE_LOOKBACK + int(np.argmin(l[P - bv.POLE_LOOKBACK:P + 1]))
    m["prior_move_adr"] = (h[P] / l[pl] - 1.0) / adr
    m["pole_low_age"] = D - pl
    m["base_len"] = D - P
    # 3 — lower lows: the last two swing lows (5-bar pivots) of the 60 sessions to D
    piv = [i for i in range(max(PIV_HALF, D - PIV_LOOK + 1), D - PIV_HALF + 1) if l[i] <= l[i - PIV_HALF:i + PIV_HALF + 1].min()]
    piv = [i for n, i in enumerate(piv) if n == 0 or i - piv[n - 1] > PIV_HALF]
    m["n_piv"] = len(piv)
    m["piv_ll_adr"] = (l[piv[-1]] / l[piv[-2]] - 1.0) / adr if len(piv) >= 2 else float("nan")   # < 0 = the latest swing low is lower
    # 4 — a gap down the buy level has not reclaimed (level <= the close before the gap), the last 30 sessions
    best, age, anyg = 0.0, -1, 0.0
    for i in range(max(1, D - GAP_LOOK + 1), D + 1):
        g = (c[i - 1] - o[i]) / c[i - 1] / adr
        anyg = max(anyg, g)
        if level <= c[i - 1] and g > best:
            best, age = g, D - i
    m["gap_dn_adr"], m["gap_dn_age"], m["gap_any_adr"] = best, age, anyg
    # 5 — frozen tight: the last sessions' ranges against the name's own 20-day daily range
    rng = (h - l) / c
    m["rng5_over_adr"] = float(rng[D - 4:D + 1].mean()) / adr
    m["rng10_over_adr"] = float(rng[D - 9:D + 1].mean()) / adr
    m["rng5_med"] = float(np.median(rng[D - 4:D + 1]))
    m["rng3_max_over_adr"] = float(rng[D - 2:D + 1].max()) / adr
    cw = c[D - 9:D + 1]
    m["spread10_adr"] = (cw.max() / cw.min() - 1.0) / adr
    # 6 — likeness to the template (06_template.py: RMS gap in daily ranges from the buy level, the last 90 closes to D)
    cc = c[max(0, D - TPL_W + 1):D + 1]
    p = np.full(TPL_W, np.nan); p[TPL_W - len(cc):] = (cc - level) / (adr * level)
    ok = ~np.isnan(p)
    m["tpl_dist"] = float(np.sqrt(np.nansum((p - TPL_MEAN) ** 2) / ok.sum())) if ok.sum() >= TPL_MIN_N else float("nan")
    # 3 as-is — the existing shape helpers
    sg = bv.shape_gates(bars, D, P=int(P), adr20=adr)
    for kk in ("higher_lows", "no_lower_low", "low_not_today", "ema21_not_falling"):
        m[kk] = bool(sg[kk]["pass"])
    return m


# ───────────────────────────── fixtures: the 757 scorecard buys + the 84 High tier ─────────────────────────────
def stage_fixtures():
    sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
    import rating as R
    F = pd.read_parquet("/Users/alvinfung/apollo_data/qm_breakouts_1102/features_eraA.parquet", columns=["scan_date", "ticker", "rs_best", "raw_close"])
    assert str(F.scan_date.max())[:10] <= "2022-03-31"
    RS = {(t, str(d)[:10]): (r, rc) for t, d, r, rc in zip(F.ticker, F.scan_date, F.rs_best, F.raw_close)}
    TIER = {(r["set"], r["eid"]): r["tier"] for r in csv.DictReader(open("scripts/probes/_717_qm_confidence_1111/ratings.tsv"), delimiter="\t")}
    rows = []
    for b in R.load():
        assert b["dates"][-1] < date(2025, 1, 1)
        bars = cb.daily_bars_from_arrays(b["dates"], b["o"], b["h"], b["l"], b["c"], b["v"])
        for t in b["win"]:
            D = t - 1
            if b["set"] == "dated":
                rs, raw = float(b["row"]["rs_best"]), float(b["row"]["raw_close_D"])
            else:
                rs, raw = RS.get((b["ticker"], b["dates"][D].isoformat()), (None, None))
            try:
                g = bv.v1_gates(bars, D, rs_best=rs, raw_close=raw)
            except Exception:
                continue
            if not g["ok"]:
                continue
            fired = bool(bv.breakout_triggered({"h": float(b["h"][t]), "v": float(b["v"][t])}, g)["fired"])
            m = reason_measures(bars, D, g["pole_idx"], g["adr20"], g["level"])
            rows.append(dict(set=b["set"], eid=b["eid"], ticker=b["ticker"], E=b["dates"][t].isoformat(), tier=TIER[(b["set"], b["eid"])],
                             big=int(b["row"].get("big_winner") == "1"), fired=int(fired), adr20=g["adr20"], level=g["level"], **m))
    sc = pd.DataFrame(rows); sc.to_csv(os.path.join(HERE, "scorecard_rows.tsv"), sep="\t", index=False)
    key = sc.set + sc.eid
    print(f"scorecard (current constants, ADR floor {bv.ADR_MIN}): listed sessions {len(sc)}; buys LISTED {key.nunique()} of 757; FIRED {key[sc.fired == 1].nunique()}; "
          f"big winners fired {key[(sc.fired == 1) & (sc.big == 1)].nunique()} of 26   (expect 479 / 386 / 26)")
    # the 84 High tier, as the test
    FX = "tests/fixtures/qm_breakout_scorecard"
    by = defaultdict(list)
    for name in ("bars.psv.gz", "bars_undated_widened.psv.gz"):
        with gzip.open(f"{FX}/{name}", "rt") as f:
            for r in csv.DictReader(f, delimiter="|"):
                by[(name == "bars.psv.gz", r["eid"])].append(r)
    big = {r["eid"] for r in csv.DictReader(open(f"{FX}/buys.tsv"), delimiter="\t") if r["big_winner"] == "1"}
    hr = []
    for r in csv.DictReader(open(f"{FX}/high_tier.tsv"), delimiter="\t"):
        rr = sorted(by[(r["set"] == "dated", r["eid"])], key=lambda x: x["date"])
        ds = [date.fromisoformat(x["date"]) for x in rr]
        bars = cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"])
        D = ds.index(date.fromisoformat(r["D"]))
        g = bv.v1_gates(bars, D, rs_best=float(r["rs_best"]) if r["rs_best"] else 99.0, raw_close=float(r["raw_close_D"]) if r["raw_close_D"] else None)
        base = dict(set=r["set"], eid=r["eid"], ticker=r["ticker"], E=r["E"], ok=int(g["ok"]), failed=",".join(g["failed"]),
                    big=int(r["set"] == "dated" and r["eid"] in big), adr20=g["adr20"], level=g["level"])
        if g["gates"]["history"]["pass"]:
            base.update(reason_measures(bars, D, g["pole_idx"], g["adr20"], g["level"]))
        hr.append(base)
    hi = pd.DataFrame(hr); hi.to_csv(os.path.join(HERE, "high_rows.tsv"), sep="\t", index=False)
    print(f"High tier: {len(hi)} buys; listed {int(hi.ok.sum())} (expect 56); stopped by the 4% floor alone {int((hi.failed == 'adr').sum())} (expect 22); "
          f"other floors {int(((hi.ok == 0) & (hi.failed != 'adr')).sum())} (expect 5); 84 - 22 = {len(hi) - int((hi.failed == 'adr').sum())}")
    print("not listed, not the 4% floor:", ", ".join(f"{r.ticker} {r.E} [{r.failed}]" for r in hi[(hi.ok == 0) & (hi.failed != 'adr')].itertuples()))


# ───────────────────────────── era A: every fire row of the 11-13 capture ─────────────────────────────
G = {}


def _work(tickers):
    P, D, tid, f = G["P"], G["D"], G["tid"], G["f"]
    out = []
    for t in tickers:
        g = f[f.ticker == t] if False else G["groups"][t]
        cands = [P.runner.bars_for(D, k) for k in tid[t]]
        for i, ci, close, level, adr, bl in zip(g.index, g.ci, g.close, g.level, g.adr20, g.base_len):
            for bars, cidx in cands:
                hit = np.flatnonzero(np.asarray(cidx) == ci)
                if len(hit) and abs(float(bars.c[hit[0]]) - close) < 1e-6 * max(1.0, close):
                    Di = int(hit[0])
                    Pp = Di - int(bl)
                    m = reason_measures(bars, Di, Pp, float(adr), float(level))
                    out.append((i, *[m[k] for k in MEAS]))
                    break
            else:
                out.append((i, *[np.nan] * len(MEAS)))
    return out


def stage_eraA():
    assert not os.path.exists(OUT_FIRES), "captured once — delete by hand to rebuild"
    spec = importlib.util.spec_from_file_location("b", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/01_build.py"))
    B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
    P = B.P
    df = pd.read_parquet(B.CAPTURE)
    f = df[df.fire]
    S, _ = P.setup(); D = S.D
    assert D.cal[-1] < date(2025, 1, 1), D.cal[-1]
    tid = {}
    for k, t in enumerate(D.tickers):
        tid.setdefault(t, []).append(k)
    G.update(P=P, D=D, tid=tid, f=f, groups={t: g for t, g in f.groupby("ticker")})
    ts = sorted(G["groups"]); t0 = time.time()
    chunks = [ts[i::32] for i in range(32)]
    with get_context("fork").Pool(8) as pool:
        parts = pool.map(_work, chunks)
    out = pd.DataFrame([r for p in parts for r in p], columns=["idx"] + MEAS).set_index("idx").sort_index()
    assert len(out) == len(f)
    out.to_parquet(OUT_FIRES)
    print(f"era A fires: {len(out):,} rows measured in {time.time() - t0:.0f}s; unmatched {int(out.u50.isna().sum())} (incl. names with under 50 sessions); "
          f"calendar {D.cal[0]} .. {D.cal[-1]} -> {OUT_FIRES}")
    print(out.describe().T.to_string())


if __name__ == "__main__":
    {"fixtures": stage_fixtures, "eraA": stage_eraA}[sys.argv[1]]()
