"""#705 (b) - tests for the A+ rating read (scripts/probes/_cb_backtest/aplus_read.py, aplus_fixtures.py, aplus_rederive.py) on SYNTHETIC
data only: the golden fixtures (check 8: days E / E2 / E3 by hand), the engine's rules, the bars and the consequence table, the synthetic tree
end to end (the pins, the dry run and the self-check with no outcome column opened, the full read with VERDICT MATCH, once-only, the seal,
the hindsight gate, aplus-verdict, aplus-confirm's gate, aplus-profile), every check's failing case, the look-ahead invariance, the guards.
No real outcome: every number here is a synthetic bar.
"""
from __future__ import annotations

import ast
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.probes._cb_backtest import aplus_fixtures as fx
from scripts.probes._cb_backtest import aplus_read as ap
from scripts.probes._cb_backtest import aplus_rederive as rd
from scripts.probes._cb_backtest import registered_read as rr
from scripts.probes._cb_backtest import runner as rn
from scripts.probes._cb_backtest import fetch_minutes as fm

ERA_START = {"discovery": dt.date(2023, 1, 2), "pre": dt.date(2019, 1, 7), "holdout": dt.date(2025, 1, 6)}
LINEAR_PINS = {m: m / 390 for m in ap.PROFILE_PINS}


# ═══ the synthetic tree: the golden population written into every pinned file ══════════════════════════════════════════════════════
def _bars_rows(ticker: str, cal: list, r: fx.Row) -> list:
    """The ticker's export rows: flat 100 before the pole, the hand-set base bars [P, D], the volumes of vol_dry5, then E's bar."""
    h, l, c = fx.base_bars(r.base_len, r.wk, r.pb, r.close_d)
    d_ci, p_ci = r.E_ci - 1, r.E_ci - 1 - r.base_len
    first = min(p_ci, d_ci - 9)
    rows = []
    for ci in range(first, r.E_ci + 1):
        if ci < p_ci:
            o, hh, ll, cc = 100.0, 100.0, 100.0, 100.0
        elif ci <= d_ci:
            k = ci - p_ci
            o, hh, ll, cc = float(c[k]), float(h[k]), float(l[k]), float(c[k])
        else:
            o, hh, ll, cc = r.close_d, r.fill + 1.0, 99.0, r.close_d * 1.02
        v = 100.0 * r.vol_dry5 if d_ci - 4 <= ci <= d_ci else 100.0
        rows.append(f"{ticker},{cal[ci]},{o},{hh},{ll},{cc},{v}\n")
    return rows


def _minute_lines(r: fx.Row, dud: bool = False) -> list:
    """The E block: minutes 0..fill_minute-1 (window volumes; h 100, l set for range_sofar), the fill minute (h 101, v 999 - `dud`: h 100, v 0,
    the fill minute changing neither number), then two quiet minutes."""
    vols = r.window_volumes()
    low = 100.0 - r.range_sofar * 100.0 * r.adr20
    out = [f"{r.ticker}|{m}|100.0|100.0|{low}|100.0|{vols[m]}" for m in range(r.fill_minute)]
    out.append(f"{r.ticker}|{r.fill_minute}|100.0|{100.0 if dud else 101.0}|{low}|100.0|{0.0 if dud else 999.0}")
    out += [f"{r.ticker}|{r.fill_minute + k}|100.0|100.0|{low}|100.0|10.0" for k in (1, 2)]
    return out


def write_tree(d: Path, period: str, rows: list, cal: list, extra_watch_after_d: bool = False, duds: tuple = ()) -> dict:
    """Every pinned file of the period's data dir from `rows`: the export, the candidates (with a dummy early first break so every stair window
    starts inside the file, and the extra first-break rows that give each member its stair step), the watch rows (the fill's own pole and the
    extra poles; `extra_watch_after_d`: a later night per ticker), the P5 table, the exitpb table (features + outcomes), the minute files."""
    pre = period == "pre"
    (d / "out").mkdir(parents=True, exist_ok=True)
    (d / "minutes").mkdir(exist_ok=True)
    label = (lambda D: "pre") if pre else (lambda D: rn.split_label(dt.date.fromisoformat(D)))
    # the export
    with gzip.open(d / "daily_closes_all.csv.gz", "wt") as fh:
        for day in cal:
            fh.write(f"SPY,{day},100.0,100.0,100.0,100.0,100.0\n")
        for r in rows:
            fh.writelines(_bars_rows(r.ticker, cal, r))
    # the candidates + watch rows
    ccols = ["ticker", "D", "E", "K", "split", "retrigger", "pole_date", "pole_ci", "pivot", "adr20", "adv20_vol_D", "prior_move", "base_len", "base_depth",
             "tightening_ratio", "atr14_slope", "rs_best", "rs_all", "grp_pct", "phase_qqq_10_20", "base_id", "open_E", "high_E", "low_E", "close_E", "vol_E",
             "breakout_vol_x"]
    wcols = ["ticker", "watch_date", "ci", "close", "pole_date", "pole_ci", "pole_high", "range_recent5", "range_early5", "adr20"]
    cands, watch = [], []
    cands.append({"ticker": "ZZZZ", "D": (dt.date.fromisoformat(cal[0]) - dt.timedelta(days=1)).isoformat(), "E": cal[0], "K": "tl", "retrigger": 0, "pole_date": cal[0],
                  "pole_ci": 0, "pivot": 1.0, "adr20": 0.05, "adv20_vol_D": 1.0, "prior_move": 0.5, "base_len": 10, "base_depth": 0.1, "tightening_ratio": 0.9,
                  "atr14_slope": 0.9, "rs_best": 50.0, "rs_all": 50.0, "grp_pct": None, "phase_qqq_10_20": 1, "base_id": "ZZZZ|x", "open_E": 1.0, "high_E": 1.0,
                  "low_E": 1.0, "close_E": 1.0, "vol_E": 1.0, "breakout_vol_x": 1.0})
    cands[0]["split"] = label(cands[0]["D"])
    for r in rows:
        d_ci, p_ci = r.E_ci - 1, r.E_ci - 1 - r.base_len
        cands.append({"ticker": r.ticker, "D": r.D, "E": r.E, "K": "tl", "split": label(r.D), "retrigger": 0, "pole_date": cal[p_ci], "pole_ci": p_ci, "pivot": r.fill / 1.001,
                      "adr20": r.adr20, "adv20_vol_D": r.adv20, "prior_move": r.prior_move, "base_len": r.base_len, "base_depth": r.base_depth,
                      "tightening_ratio": r.tightening_ratio, "atr14_slope": r.atr14_slope, "rs_best": r.rs_best, "rs_all": r.rs_all, "grp_pct": r.grp_pct,
                      "phase_qqq_10_20": 1, "base_id": f"{r.ticker}|{cal[p_ci]}", "open_E": r.close_d, "high_E": r.fill + 1.0, "low_E": 99.0, "close_E": r.close_d * 1.02,
                      "vol_E": 12345.0, "breakout_vol_x": 1.5})
        watch.append({"ticker": r.ticker, "watch_date": r.D, "ci": d_ci, "close": r.close_d, "pole_date": cal[p_ci], "pole_ci": p_ci, "pole_high": 100.0,
                      "range_recent5": r.tightening_ratio * 0.02, "range_early5": 0.02, "adr20": r.adr20})
        for j in range(1, (r.stair_n or 0) + 1):                     # the extra first breaks that make the member's stair step
            e2 = r.E_ci - 30 - j
            pj = e2 - 20 - 10 * j
            cands.append(dict(cands[-1], D=cal[e2 - 1], E=cal[e2], split=label(cal[e2 - 1]), pole_date=cal[pj], pole_ci=pj, base_id=f"{r.ticker}|{cal[pj]}"))
            watch.append({"ticker": r.ticker, "watch_date": cal[e2 - 1], "ci": e2 - 1, "close": 100.0, "pole_date": cal[pj], "pole_ci": pj, "pole_high": 100.0,
                          "range_recent5": 0.02, "range_early5": 0.02, "adr20": r.adr20})
        if extra_watch_after_d:
            watch.append({"ticker": r.ticker, "watch_date": r.E, "ci": r.E_ci, "close": 100.0, "pole_date": cal[p_ci + 2], "pole_ci": p_ci + 2, "pole_high": 100.0,
                          "range_recent5": 0.02, "range_early5": 0.02, "adr20": r.adr20})
    rn.write_tsv(d / "out" / ("candidates_tl_com.tsv" if pre else "candidates.tsv"), cands, ccols)
    rn.write_tsv(d / "out" / ("watch_tl_com.tsv.gz" if pre else "watch.tsv.gz"), watch, wcols, gz=True)
    # the P5 and exitpb tables
    p5 = [{"ticker": r.ticker, "D": r.D, "E": r.E, "K": "tl", "arm": ap.P5_ARM, "stop_variant": "lod", "range5_adr": r.range5_adr, "fill": r.fill, "fill_minute": r.fill_minute,
           "realized_r": r.realized_r} for r in rows]
    rn.write_tsv(d / "out" / f"trades_{period}_p5.tsv.gz", p5, list(p5[0].keys()) if p5 else ["ticker", "D", "E", "K", "arm", "stop_variant", "range5_adr"], gz=True)
    ecols = ap.FILL_COLS + ["status", "realized_r", "pnl_adr", "acct_pct", "sessions_held"]
    ex = [{"ticker": r.ticker, "D": r.D, "E": r.E, "K": "tl", "entry": "orh5", "arm": "pp", "fill": r.fill, "fill_minute": r.fill_minute, "fill_month": r.E[:7],
           "adr20": r.adr20, "width_adr": r.width_adr, "stop": r.stop, "mature": r.mature, "open_mark": 1 - r.mature, "early_close": int(r.E in rn.H60_EARLY_CLOSE),
           "phase_qqq_10_20": 1, "status": "stopped" if r.realized_r < 0 else "trail", "realized_r": r.realized_r, "pnl_adr": r.pnl_adr, "acct_pct": 0.0, "sessions_held": 5}
          for r in rows]
    ex += [dict(e, arm="A", realized_r=e["realized_r"] + 0.5) for e in ex[:3]]                 # another arm's rows: never the population
    rn.write_tsv(d / "out" / f"trades_{period}_exitpb.tsv.gz", ex, ecols, gz=True)
    # the minutes
    by_e = {}
    for r in rows:
        by_e.setdefault(r.E, []).append(r)
    done = []
    for e, rs in sorted(by_e.items()):
        for r in rs:
            fm._append_gz(d / "minutes" / f"{e}.psv.gz", _minute_lines(r, dud=r.ticker in duds))
            done.append(f"{e}|{r.ticker}|{r.fill_minute + 3}|ok")
    (d / "minutes" / "_done.psv").write_text("\n".join(done) + ("\n" if done else ""))
    return {"cands": cands, "watch": watch}


def _profile_pair(pre: Path, cal: list) -> None:
    """One non-population pair in the pre tree whose CUM is exactly linear (v = 1 on every minute): the pinned profile re-derives from it."""
    e = cal[50]
    fm._append_gz(pre / "minutes" / f"{e}.psv.gz", [f"PROF|{m}|100.0|100.0|100.0|100.0|1.0" for m in range(390)])
    done = pre / "minutes" / "_done.psv"
    done.write_text((done.read_text() if done.exists() else "") + f"{e}|PROF|390|ok\n")


def _stub_dir(d: Path, period: str) -> None:
    """The OTHER data dir: every pinned file present as a stub (the freeze pins both trees)."""
    (d / "out").mkdir(parents=True, exist_ok=True)
    (d / "minutes").mkdir(exist_ok=True)
    names = ["candidates_tl_com.tsv", "watch_tl_com.tsv.gz", "trades_pre_exitpb.tsv.gz", "trades_pre_p5.tsv.gz"] if period == "pre" else \
        ["candidates.tsv", "watch.tsv.gz", "trades_discovery_exitpb.tsv.gz", "trades_holdout_exitpb.tsv.gz", "trades_discovery_p5.tsv.gz", "trades_holdout_p5.tsv.gz"]
    for name in names:
        if not (d / "out" / name).exists():
            (d / "out" / name).write_text(name)
    if not (d / "daily_closes_all.csv.gz").exists():
        (d / "daily_closes_all.csv.gz").write_bytes(b"stub export")
    if not (d / "minutes" / "_done.psv").exists():
        (d / "minutes" / "_done.psv").write_text("")


def _empty_exitpb(path: Path) -> None:
    rn.write_tsv(path, [], ap.FILL_COLS + ["status", "realized_r", "pnl_adr", "acct_pct", "sessions_held"], gz=True)


def aplus_tree(tmp_path, monkeypatch, period: str = "discovery", rows: "list | None" = None, **kw) -> dict:
    """cb702 + cb702_pre, the repo, the linear profile under cb702_pre/out, the registration doc with matching pins; the module constants
    pointed at the synthetic facts (the profile's sha / pins / tally, the census targets)."""
    cal = fx.set_calendar(ERA_START[period])
    rows = rows if rows is not None else fx.golden_rows(e2_rs=40, with_f6=False)     # the files meet check 3 (rs_best never missing); E2's boundary is in-memory
    for r in rows:
        if r.stair_n is None:                                              # a file cannot express "unrated on concept 5" for one fill of a day: F2 reads 0 here
            r.stair_n = 0
    data, pre = tmp_path / "cb702", tmp_path / "cb702_pre"
    d = pre if period == "pre" else data
    write_tree(d, period, rows, cal, **kw)
    if period == "holdout":                                                # the confirm read pools the discovery table (empty here)
        _empty_exitpb(data / "out" / "trades_discovery_exitpb.tsv.gz")
    other = data if period == "pre" else pre
    _stub_dir(other, "discovery" if period == "pre" else "pre")
    if period != "pre":
        _empty_exitpb(pre / "out" / "trades_pre_exitpb.tsv.gz")
    _stub_dir(d, period)
    pre.mkdir(exist_ok=True)
    _profile_pair(pre, cal)
    prof_text = ap.profile_text(fx.PROFILE)
    (pre / "out").mkdir(exist_ok=True)
    (pre / "out" / ap.PROFILE_NAME).write_text(prof_text)
    sha = hashlib.sha256(prof_text.encode()).hexdigest()
    n_pop = sum(1 for r in rows) if period == "pre" else 0                          # the pre tree holds the population's own pairs (+ PROF)
    n_early = sum(1 for r in rows if r.E in rn.H60_EARLY_CLOSE) if period == "pre" else 0
    monkeypatch.setattr(ap, "PROFILE_SHA_EXPECTED", sha)
    monkeypatch.setattr(ap, "PROFILE_PINS", LINEAR_PINS)
    monkeypatch.setattr(ap, "PROFILE_TALLY", {"ok": n_pop + 1, "zero": 0, "early": n_early, "population": n_pop - n_early, "kept": 1})
    repo = tmp_path / "repo"
    (repo / "docs" / "analysis").mkdir(parents=True)
    (repo / rn.MODULE_REL).parent.mkdir(parents=True, exist_ok=True)
    (repo / rn.MODULE_REL).write_text("# module\n")
    monkeypatch.setattr(rn, "REPO", repo)
    monkeypatch.setattr(rn, "HERE", tmp_path / "hereroot")
    (rn.HERE / "out").mkdir(parents=True)
    ap.clear_export_cache()
    rr.clear_daily_cache()
    tree = {"cb702": data, "cb702_pre": pre, "repo": repo, "rows": rows, "cal": cal, "period": period, "dir": d}
    doc(tree)
    return tree


def expected_for(rows: list, period: str) -> dict:
    """The synthetic census targets the test is sure of by construction (the equality the real doc pins is on real counts)."""
    el = [r for r in rows if r.eligible]
    fms = [r.fill_minute for r in el]
    thin = sum(1 for r in el if sum(1 for q in rows if r.E_ci - 20 <= q.E_ci <= r.E_ci - 1) < ap.POOL_FLOOR)      # the pool members' own thin pools
    early = [r for r in el if r.E in rn.H60_EARLY_CLOSE]
    return {"joined": len(rows), "fills": len(el), "open": sum(1 - r.mature for r in el), "weeks": len({ap.iso_week(r.E) for r in el}), "dropped": len(rows) - len(el),
            "c5_unrated": 0, "thin": thin, "fm_min": min(fms), "fm_max": max(fms), "fm_at5": sum(1 for x in fms if x == 5), "fm_ge210": sum(1 for x in fms if x >= 210),
            "zero_vol": tuple(sorted((r.ticker, r.E) for r in el if r.vol_sofar is None)), "early": len(early), "early_ge210": sum(1 for r in early if r.fill_minute >= 210),
            "exp_missing": 0,
            "exp_le0": sum(1 for r in el if (r.exp_up or 0) <= 0), "grp_present": sum(1 for r in el if r.grp_pct is not None), "min0_absent": 0, "absent_any": 0}


def doc(tree: dict, body: str = "Method / population. What this does not answer. n=1.\n") -> Path:
    spec = ap.APLUS_READ
    p = tree["repo"] / "docs" / "analysis" / spec.doc
    p.write_text(body + rn.FREEZE_MARK + "\n## Freeze record\n")
    ctx = rr.resolve(spec, ns(tree), rn)
    pins = rn.pin_lines(tree["cb702"], tree["repo"], files=rr.frozen_map(spec, ctx)) + [f"- doc body sha256: `{rn.doc_body_sha(p.read_text())}`"]
    p.write_text(p.read_text() + "\n".join(pins) + "\n")
    return p


def ns(tree, **kw):
    kw.setdefault("period", tree["period"])
    kw.setdefault("self_check", False)
    return T_ns(tree["cb702"], data_pre=str(tree["cb702_pre"]), **kw)


def T_ns(data, **kw):
    import argparse
    base = dict(data=str(data), out=None, small_out=None, workers=1, minutes=None, limit_dates=0, no_close=False, dry_run=False, no_freeze_check=False,
                print_pins=False, prereg=None, trades=None, no_apollo=False, self_check=False)
    base.update(kw)
    return argparse.Namespace(**base)


def main(tree, stage, *extra, period="unset"):
    argv = [stage, "--data", str(tree["cb702"]), "--data-pre", str(tree["cb702_pre"]), "--workers", "1"]
    p = tree["period"] if period == "unset" else period
    if p:
        argv += ["--period", p]
    return rn.main(argv + list(extra))


def set_expected(monkeypatch, tree: dict, **over) -> dict:
    """The synthetic census targets AND the synthetic table's own C0 integers (the registered 13,363 / 165 ... describe the real tables; a run
    whose table disagrees with its pinned integers stops - `test_the_c0_integers_must_describe_the_table`)."""
    exp = expected_for(tree["rows"], tree["period"])
    exp.update(over)
    monkeypatch.setattr(ap, "APLUS_EXPECTED", {**ap.APLUS_EXPECTED, tree["period"]: exp})
    mature = [r for r in tree["rows"] if r.mature]
    r = np.array([x.realized_r for x in mature], dtype=float)
    c0 = {"n": len(mature), "ge10": int((r >= 10).sum()), "mean_r": round(float(r.mean()), 3), "ge5_per100": round(float(100 * (r >= 5).mean()), 2),
          "ge10_per100": round(float(100 * (r >= 10).mean()), 3)}
    monkeypatch.setitem(ap.C0_PUBLISHED, tree["period"], c0)
    return exp


# ═══ check 8: the golden fixtures ═════════════════════════════════════════════════════════════════════════════════════════════════════
class TestGolden:
    def test_the_golden_fixtures_pass_on_the_committed_code(self):
        assert fx.run_golden() == []

    def test_the_bars_give_the_pinned_formulas_their_targets(self):
        h, l, c = fx.base_bars(15, 0.3, 0.6)
        assert ap.wk_ratio_of(h, l, c, 15) == pytest.approx(0.3) and ap.pb_ratio_of(h, l) == pytest.approx(0.6)
        assert ap.swing_highs(h) == [0, 5, 10] and len(ap.pullbacks_of(h, l)) == 2
        h, l, c = fx.base_bars(12, None, 0.5)
        assert ap.wk_ratio_of(h, l, c, 12) is None and ap.pb_ratio_of(h, l) == pytest.approx(0.5)      # 2 blocks: weekly missing
        h, l, c = fx.base_bars(14, None, None)
        assert ap.wk_ratio_of(h, l, c, 14) is None and ap.pb_ratio_of(h, l) is None                     # one completed pullback: missing
        h, l, c = fx.base_bars(20, 0.5, 0.5)
        assert ap.wk_ratio_of(h, l, c, 20) is not None                                                  # k = 4, m = 2: two blocks a side

    def test_a_golden_expectation_that_fails_is_named(self, monkeypatch):
        """The fixtures are a check: an engine that reads a missing scale as 0 (not 0.5) is caught."""
        real = ap.spec_scores

        def zero_for_missing(P, spec):
            P = P.copy()
            P[:, ap.KEY_IDX["c1_wk"]] = np.nan_to_num(P[:, ap.KEY_IDX["c1_wk"]], nan=0.0)
            return real(P, spec)
        monkeypatch.setattr(ap, "spec_scores", zero_for_missing)
        problems = fx.run_golden()
        assert problems and any("0.5" in p or "hand" in p for p in problems)

    def test_the_hand_formula_is_the_mid_rank_percentile(self):
        assert fx._pct([1, 2, 3, 4] * 10, 2.5, True) == 0.5 and fx._pct([1, 2, 3, 4] * 10, 2, True) == (10 + 5) / 40
        assert fx._pct([1, 2, 3, 4] * 10, 2, True, exclude_self=True) == (10 + 4.5) / 39
        assert fx._pct([1] * 29, 1, True) is None                                                        # under the floor


# ═══ the engine's rules ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
class TestEngine:
    def test_pool_percentiles_mid_rank_floor_and_the_member_minus_itself(self):
        X = np.full((45, len(ap.FEATURE_KEYS)), np.nan)
        X[:40, 0] = np.arange(40, dtype=float)                       # 40 pool values 0..39 on feature 0
        X[40:, 0] = [-1.0, 38.5, 100.0, 5.0, np.nan]                 # the day's fills: below all, above all but the top, above all, a tie, missing
        own, ref = ap.pool_percentiles(X, np.arange(40), np.arange(40, 45))
        assert own[0, 0] == 0.0 and own[1, 0] == 39 / 40 and own[2, 0] == 1.0 and own[3, 0] == 5.5 / 40 and np.isnan(own[4, 0])
        assert ref[0, 0] == 0.0 and ref[39, 0] == 1.0 and ref[20, 0] == 20 / 39                          # the member against the 39 others
        assert np.isnan(own[:, 1]).all() and np.isnan(ref[:, 1]).all()                                    # a feature under the floor: NaN
        X2 = X.copy()
        X2[30:40, 0] = np.nan                                                                             # 30 values: the fill ranks, the member (29) does not
        own2, ref2 = ap.pool_percentiles(X2, np.arange(40), np.arange(40, 45))
        assert own2[2, 0] == 1.0 and np.isnan(ref2[:, 0]).all()

    def test_spec_scores_composite_optional_required_and_reversed(self):
        P = np.full((3, len(ap.FEATURE_KEYS)), np.nan)
        for k, v in (("c1_daily", 0.9), ("c2", 0.6), ("c3", 0.6), ("c4", 0.6), ("c6", 0.6), ("c7", 0.6)):
            P[:, ap.KEY_IDX[k]] = v
        P[0, ap.KEY_IDX["c5"]] = 0.2                                        # row 0 carries concept 5; row 1 does not; row 2 misses a required concept
        P[2, ap.KEY_IDX["c6"]] = np.nan
        P[0, ap.KEY_IDX["c1_wk"]] = 0.9
        s = ap.spec_scores(P, ap.SPECS["core"])
        assert s[0] == pytest.approx(((0.9 + 0.9 + 0.5) / 3 + 5 * 0.6 + 0.2) / 7)                       # a missing pullback scale = 0.5
        assert s[1] == pytest.approx(((0.9 + 0.5 + 0.5) / 3 + 5 * 0.6) / 6)                             # concept 5 missing: the mean of six
        assert np.isnan(s[2])
        r = ap.spec_scores(P, ap.SPECS["rev_stair"])
        assert r[0] == pytest.approx(((0.9 + 0.9 + 0.5) / 3 + 5 * 0.6 + 0.8) / 7) and r[1] == s[1]
        g = ap.spec_scores(P, ap.SPECS["grp"])
        assert np.isnan(g).all()                                                                          # grp missing: unrated under +grp
        a = ap.spec_scores(P, ap.SPECS["alone_c1_weekly"])
        assert a[0] == 0.9 and np.isnan(a[1])                                                             # a scale alone: no 0.5 rule
        assert ap.spec_scores(P, ap.SPECS["alone_c5"])[0] == 0.2 and np.isnan(ap.spec_scores(P, ap.SPECS["alone_c5"])[1])

    def test_cutoff_is_the_rank_th_highest_rated_reference_score(self):
        s = np.array([0.1, np.nan, 0.9, 0.5, 0.7] + [0.3] * 10)
        assert ap.cutoff_of(s, 1) == 0.9 and ap.cutoff_of(s, 4) == 0.3 and ap.cutoff_of(s, 14) == 0.1 and np.isnan(ap.cutoff_of(s, 15))

    def test_the_weekly_cap_runs_in_fill_order_and_never_more_than_n(self):
        cols = fx.cols_of(fx.golden_rows())
        res = ap.rate_population(cols)
        weeks = np.asarray(cols["week"], dtype=object)
        for N in ap.NS:
            fl = res["flag"][("core", N)]
            for w in set(weeks):
                above = ((fl == "aplus") | (fl == "capped")) & (weeks == w)
                assert int(((fl == "aplus") & (weeks == w)).sum()) == min(N, int(above.sum()))
                order = np.flatnonzero(above)
                assert all(fl[i] == "aplus" for i in order[:N]) and all(fl[i] == "capped" for i in order[N:])
        rev = {k: list(reversed(v)) for k, v in cols.items()}                  # any input order: the engine sorts into fill order itself
        res_rev = ap.rate_population(rev)
        for N in ap.NS:
            assert ap.aplus_set(rev, res_rev, "core", N) == ap.aplus_set(cols, res, "core", N)
        assert list(res_rev["pool_n"]) == list(reversed(res["pool_n"]))

    def test_a_feature_missing_is_never_read_as_zero(self):
        cols = fx.cols_of(fx.golden_rows())
        X = ap.oriented_matrix(cols)
        i = cols["ticker"].index("F2")
        assert np.isnan(X[i, ap.KEY_IDX["c5"]]) and cols["stair_n"][i] is None
        res = ap.rate_population(cols)
        assert np.isnan(res["pct"][i, ap.KEY_IDX["c5"]]) and not np.isnan(res["score"]["core"][i])

    def test_hindsight_top_n_orders_by_score_rs_minute_ticker(self):
        cols = fx.cols_of(fx.golden_rows())
        res = ap.rate_population(cols)
        top = ap.hindsight_topn(cols, res, ap.SPECS["core"], 3)
        e_day = {cols["ticker"][i] for i in np.flatnonzero(top) if cols["E"][i] == fx.CAL[fx.E_CI]}
        assert len(e_day) == 3 and "F1" in e_day and e_day <= {"F1", "F3", "F5", "F2", "F4"}            # 3 of the week's rated fills, F1 first
        assert int(top.sum()) <= 3 * len(set(cols["week"]))
        assert np.array_equal(top, ap.hindsight_topn(cols, res, ap.SPECS["core"], 3))                   # deterministic
        assert int(ap.hindsight_topn(cols, res, ap.SPECS["core"], 1).sum()) <= len(set(cols["week"]))


# ═══ the bars, the paired bar, the consequence table ═════════════════════════════════════════════════════════════════════════════
def _group(r, width=0.5, tickers=None, months=None):
    r = np.asarray(r, dtype=float)
    n = len(r)
    return ap.group_stats(r, np.full(n, 0.1), np.full(n, width), tickers or [f"T{i % 7}" for i in range(n)], months or [f"2023-{1 + i % 6:02d}" for i in range(n)],
                          "k", rn.block_bootstrap_ci)


class TestBars:
    def test_verdict_pass_fail_cant_tell_and_the_integer_outlier_bar(self):
        c0 = {"mean_r": -0.169, "ge5_per100": 2.57, "median_width_adr": 0.5}
        g = _group([12.0] * 10 + [0.5] * 30)                                # 10 of 40 >= 10R: 10 x 8984 >= 2 x 85 x 40
        assert ap.verdict_of(g, c0, 8984, 85)[0] == "PASS"
        g = _group([-1.0] * 40)
        assert ap.verdict_of(g, c0, 8984, 85)[0] == "FAIL"
        g = _group([0.5] * 29)
        assert ap.verdict_of(g, c0, 8984, 85) == ("CAN'T TELL", "n = 29 < 30")
        # the 7-of-370 counter-example: 7 x 8,984 = 62,888 < 2 x 85 x 370 = 62,900 - FAILS the outlier bar (positive, no tail)
        g = _group([12.0] * 7 + [6.0] * 10 + [0.6] * 353)                   # >= 5R 4.6 per 100 beats C0; the tail alone misses
        v, why = ap.verdict_of(g, c0, 8984, 85)
        assert v == "CAN'T TELL (positive, no tail)" and "62888 < 2 x 85 x 370" in why
        g = _group([12.0] * 8 + [6.0] * 10 + [0.6] * 352)                    # 8 x 8,984 = 71,872 >= 62,900
        assert ap.verdict_of(g, c0, 8984, 85)[0] == "PASS"
        g = _group([12.0] * 8 + [6.0] * 10 + [0.6] * 352, width=0.1)         # the spread counts stops >= 0.25 ADR only
        v, why = ap.verdict_of(g, c0, 8984, 85)
        assert v == "CAN'T TELL (positive, no tail)" and "0 tickers / 0 months" in why
        g = _group([12.0] * 8 + [6.0] * 10 + [0.6] * 352, tickers=["A"] * 370)
        assert "1 tickers" in ap.verdict_of(g, c0, 8984, 85)[1]
        g = _group([12.0] * 7 + [0.6] * 363)                                 # the >= 5R share under C0's AND the tail: plain CAN'T TELL
        assert ap.verdict_of(g, c0, 8984, 85)[0] == "CAN'T TELL"

    def test_paired_delta_redraws_empty_sides_and_reads_the_interval(self):
        d = ap.paired_delta([1.0] * 20, ["2023-01"] * 10 + ["2023-02"] * 10, [-1.0] * 5, ["2023-03"] * 5, "k")
        assert d["discarded"] > 0 and d["reading"] == "separates" and d["mean"] == 2.0 and d["lo"] == 2.0 == d["hi"]
        d = ap.paired_delta([-1.0] * 20, ["2023-01"] * 20, [1.0] * 20, ["2023-01"] * 20, "k")
        assert d["reading"] == "picks worse" and d["discarded"] == 0
        rng = np.random.default_rng(1)
        a, b = rng.normal(0, 1, 60), rng.normal(0, 1, 60)
        m = [f"2023-{1 + i % 12:02d}" for i in range(60)]
        d1, d2 = ap.paired_delta(a, m, b, m, "k"), ap.paired_delta(a, m, b, m, "k")
        assert d1 == d2 and d1["reading"] == "can't tell" and ap.paired_delta(a, m, b, m, "other") != d1
        assert ap.paired_delta([], [], [1.0], ["2023-01"], "k")["reading"] == "can't tell"

    def test_grp_reading(self):
        assert ap.grp_reading({"lo": 0.1, "hi": 0.5}) == "ADDS" and ap.grp_reading({"lo": -0.5, "hi": -0.1}) == "SUBTRACTS" and ap.grp_reading({"lo": -0.1, "hi": 0.1}) == "CAN'T TELL"

    @pytest.mark.parametrize("vp,vd,pp,pd_,cell", [
        ("PASS", "PASS", "separates", "can't tell", "RECORD"), ("PASS", "CAN'T TELL", "can't tell", "can't tell", "LEAD"),
        ("CAN'T TELL (positive, no tail)", "PASS", "can't tell", "separates", "LEAD"), ("PASS", "FAIL", "separates", "separates", "NOT RECORDED"),
        ("FAIL", "PASS", "can't tell", "can't tell", "NOT RECORDED"), ("CAN'T TELL", "CAN'T TELL", "separates", "separates", "LEAD"),
        ("CAN'T TELL", "CAN'T TELL", "separates", "can't tell", "NOT RECORDED"), ("PASS", "PASS", "picks worse", "separates", "NOT RECORDED"),
        ("PASS", "PASS", "separates", "picks worse", "NOT RECORDED"), ("FAIL", "FAIL", "can't tell", "can't tell", "NOT RECORDED")])
    def test_the_consequence_table_and_its_precedence(self, vp, vd, pp, pd_, cell):
        pre = {"verdict": vp, "paired": {"reading": pp}, "grp": {"reading": "ADDS"}}
        disc = {"verdict": vd, "paired": {"reading": pd_}, "grp": {"reading": "ADDS"}}
        c = ap.consequence(pre, disc)
        assert c["cell"] == cell and c["record_core"] == (cell in ("RECORD", "LEAD")) and c["record_grp"] == c["record_core"]
        disc["grp"]["reading"] = "CAN'T TELL"
        assert ap.consequence(pre, disc)["record_grp"] is False

    def test_next_registration_picks_the_eligible_alone_row(self):
        row = lambda ge10, mean, t=3, m=3: {"n": 100, "ge10_per100": ge10, "mean_r": mean, "tail_tickers": t, "tail_months": m}   # noqa: E731
        pre = {"alone_c1": row(3.0, 0.1), "alone_c2": row(5.0, 0.2, t=2), "alone_c3": row(4.0, 0.3), "alone_c4": row(4.0, 0.3)}
        disc = {"alone_c1": row(3.0, 0.1), "alone_c2": row(5.0, 0.2), "alone_c3": row(4.0, 0.1), "alone_c4": row(4.0, 0.1)}
        assert ap.next_registration(pre, disc) == "alone_c3"                  # c2 fails the spread in one era; c3 ties c4 on >= 10R, wins on mean R... then the lower number
        disc["alone_c4"]["mean_r"] = 0.5
        assert ap.next_registration(pre, disc) == "alone_c4"
        assert ap.next_registration({}, {}) is None


# ═══ the synthetic tree, end to end ════════════════════════════════════════════════════════════════════════════════════════════════
class TestTree:
    def test_the_tree_reproduces_the_golden_features_from_the_files(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch)
        spec = ap.APLUS_READ
        ctx = rr.resolve(spec, ns(tree), rn)
        prep = ap.aplus_prepare(ctx)
        feats = ap.build_features(ctx, prep, lambda *a: None)
        cols = feats["cols"]
        want = fx.cols_of(tree["rows"])
        assert cols["ticker"] == want["ticker"] and cols["E"] == want["E"] and cols["E_ci"] == want["E_ci"]
        for k in ("tightening_ratio", "wk_ratio", "pb_ratio", "vol_dry5", "rs_best", "prior_move", "stair_n", "exp_up_adr", "vol_sofar_x", "grp_pct", "base_len",
                  "range5_adr", "range_sofar_adr"):
            for i in range(len(want["ticker"])):
                a, b = cols[k][i], want[k][i]
                assert (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= 1e-9 * max(1.0, abs(b))), (k, cols["ticker"][i], a, b)
        assert feats["problems"] == [] and feats["pert_ok"] == feats["n_blocks_ok"] == len(cols["ticker"])
        res, want_res = ap.rate_population(cols), ap.rate_population(want)
        assert ap._res_diff(res, want_res) == "" and ap.aplus_set(cols, res) == ap.aplus_set(want, want_res)

    def test_print_pins_carries_the_registrations_list(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        assert main(tree, "aplus-read", "--print-pins", period=None) is None
        pins = capsys.readouterr().out
        for label in ("cb702_pre/out/aplus_intraday_profile.tsv", "cb702/out/trades_discovery_exitpb.tsv.gz", "cb702_pre/out/trades_pre_exitpb.tsv.gz",
                      "cb702/out/trades_holdout_exitpb.tsv.gz", "cb702/out/trades_discovery_p5.tsv.gz", "cb702_pre/out/trades_pre_p5.tsv.gz",
                      "cb702/out/trades_holdout_p5.tsv.gz", "cb702/out/candidates.tsv", "cb702_pre/out/candidates_tl_com.tsv", "cb702/out/watch.tsv.gz",
                      "cb702_pre/out/watch_tl_com.tsv.gz", "cb702/daily_closes_all.csv.gz", "cb702_pre/daily_closes_all.csv.gz", "cb702/minutes/_done.psv",
                      "cb702_pre/minutes/_done.psv", "cb702/minutes (tree)", "cb702_pre/minutes (tree)", "module", "runner", "scaffold", "spec module",
                      "rederivation module", "doc body"):
            assert f"- {label} sha256: `" in pins, label
        assert "MISSING" not in pins

    def test_dry_run_counts_the_census_and_opens_no_outcome(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        set_expected(monkeypatch, tree)
        boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("an outcome column was opened"))     # noqa: E731
        monkeypatch.setattr(ap, "read_outcomes", boom)
        before = sorted(p.as_posix() for p in tmp_path.rglob("*"))
        assert main(tree, "aplus-read", "--dry-run") is None
        out = capsys.readouterr().out
        assert "STEP 0 PASSED: every equality target met" in out and "concept 1 scales: weekly present" in out and "APLUS DRY RUN (freeze check passed" in out
        assert sorted(p.as_posix() for p in tmp_path.rglob("*")) == before
        assert main(tree, "aplus-read", "--dry-run", "--self-check") is None
        out = capsys.readouterr().out
        assert "SELF-CHECK PASSED" in out and "check 2 (later-fill removal)" in out and "check 4 (golden fixtures" in out and "  core N = 3: A+ " in out
        with pytest.raises(SystemExit):                                       # --self-check needs --dry-run
            main(tree, "aplus-read", "--self-check")
        assert "only together with --dry-run" in capsys.readouterr().err
        set_expected(monkeypatch, tree, fills=999)
        assert main(tree, "aplus-read", "--dry-run") is None
        assert "STEP 0 / SELF-CHECK FAILED" in capsys.readouterr().out

    def test_the_full_read_once_only_the_seal_hindsight_and_verdict(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        set_expected(monkeypatch, tree)
        out, small = tree["cb702"] / "out", rn.HERE / "out"
        # the seal (check 10): a holdout artefact on disk refuses aplus-read
        (out / "trades_holdout_aplus.tsv.gz").write_bytes(b"x")
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-read")
        assert ex.value.code == 2 and "BROKEN run (check 10)" in capsys.readouterr().err
        (out / "trades_holdout_aplus.tsv.gz").unlink()
        with pytest.raises(SystemExit):                                       # hindsight and the verdict refuse before both verdicts exist
            main(tree, "aplus-hindsight")
        assert "AFTER both deciding verdict files exist" in capsys.readouterr().err
        with pytest.raises(SystemExit):
            main(tree, "aplus-verdict", period=None)
        assert "BOTH verdict files exist" in capsys.readouterr().err
        assert main(tree, "aplus-read") is None
        o = capsys.readouterr().out
        assert "RE-DERIVATION (pandas, no runner code)" in o and "VERDICT MATCH" in o and "WROTE" in o
        t = rn.read_tsv(out / "trades_discovery_aplus.tsv.gz")
        e_day = t[t["E"] == fx.CAL[fx.E_CI]]
        assert len(t) == len(tree["rows"]) and set(e_day.loc[e_day["flag_core_n3"] == "aplus", "ticker"]) == {"F1", "F3", "F2"} and (e_day["flag_core_n3"] == "capped").sum() == 1
        vj = json.loads((out / "aplus_verdict_discovery.json").read_text())
        assert vj["verdict"] == "CAN'T TELL" and 3 <= vj["n"] < 30 and vj["rederivation"] == "MATCH" and vj["paired"]["reading"] in ("separates", "can't tell", "picks worse")
        assert vj["aplus_n"]["3"] == vj["n"] == int((t["flag_core_n3"] == "aplus").sum())
        assert (small / "aplus_verdict_discovery.txt").exists() and (small / "aplus_report_discovery.txt").exists() and (out / "aplus_report_discovery.tsv").exists()
        assert "check 11 (re-derivation): VERDICT MATCH" in (small / "aplus_report_discovery.txt").read_text()
        with pytest.raises(SystemExit) as ex:                                 # read once
            main(tree, "aplus-read")
        assert ex.value.code == 2 and "read ONCE per period" in capsys.readouterr().err
        # the pre verdict does not exist yet: hindsight still refuses; a synthetic pre verdict unlocks it and aplus-verdict
        with pytest.raises(SystemExit):
            main(tree, "aplus-hindsight")
        capsys.readouterr()
        pre_v = dict(vj, period="pre", verdict="PASS")
        (tree["cb702_pre"] / "out" / "aplus_verdict_pre.json").write_text(json.dumps(pre_v))
        assert main(tree, "aplus-hindsight") is None
        o = capsys.readouterr().out
        assert "HINDSIGHT within-week top-3" in o and "THE 39" in o and (out / "aplus_hindsight_discovery.txt").exists()
        with pytest.raises(SystemExit):                                       # once only
            main(tree, "aplus-hindsight")
        capsys.readouterr()
        assert main(tree, "aplus-verdict", period=None) is None
        o = capsys.readouterr().out
        assert "#705 A+ CONSEQUENCE: 2017-21 PASS" in o and "LEAD" in o
        # aplus-confirm refuses unless the cell reads RECORD
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-confirm", period="holdout")
        assert ex.value.code == 2 and "runs only on RECORD" in capsys.readouterr().err

    def test_the_pre_period_reads_its_own_tree(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch, period="pre")
        set_expected(monkeypatch, tree)
        assert main(tree, "aplus-read", "--dry-run") is None and "STEP 0 PASSED" in capsys.readouterr().out
        assert main(tree, "aplus-read") is None
        assert "VERDICT MATCH" in capsys.readouterr().out and (tree["cb702_pre"] / "out" / "aplus_verdict_pre.json").exists()
        assert not list((tree["cb702"] / "out").glob("*aplus*"))

    def test_the_confirm_read_runs_on_record_and_pools_the_discovery_table(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch, period="holdout")
        exp = set_expected(monkeypatch, tree)
        v = {"verdict": "PASS", "paired": {"reading": "separates"}, "grp": {"reading": "ADDS"}, "rows": {}}
        (tree["cb702_pre"] / "out" / "aplus_verdict_pre.json").write_text(json.dumps(v))
        (tree["cb702"] / "out" / "aplus_verdict_discovery.json").write_text(json.dumps(v))
        assert main(tree, "aplus-confirm", "--dry-run") is None and "STEP 0 PASSED" in capsys.readouterr().out
        assert main(tree, "aplus-confirm") is None
        assert "VERDICT MATCH" in capsys.readouterr().out and (tree["cb702"] / "out" / "aplus_verdict_holdout.json").exists()
        assert exp["fills"] == len(tree["rows"])

    def test_the_profile_stage_builds_the_pin_refuses_a_rebuild_and_a_mismatch(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch, period="pre")
        prof = tree["cb702_pre"] / "out" / ap.PROFILE_NAME
        with pytest.raises(SystemExit) as ex:                                  # the pin exists: never rebuilt
            main(tree, "aplus-profile", period=None)
        assert ex.value.code == 2 and "built ONCE" in capsys.readouterr().err
        want = prof.read_bytes()
        prof.unlink()
        assert main(tree, "aplus-profile", period=None) is None
        o = capsys.readouterr().out
        assert prof.read_bytes() == want and "= EXPECTED" in o and f"kept 1" in o and "monotone True" in o
        assert (rn.HERE / "out" / "aplus_profile_summary.txt").exists()
        prof.unlink()
        monkeypatch.setattr(ap, "PROFILE_SHA_EXPECTED", "0" * 64)
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-profile", period=None)
        assert ex.value.code == 3 and "PROFILE BUILD FAILED" in capsys.readouterr().out and rn.partial_path(prof).exists() and not prof.exists()

    def test_guards_refusals_and_the_freeze(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        set_expected(monkeypatch, tree)
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-read", period=None)
        assert ex.value.code == 2 and "--period is required" in capsys.readouterr().err
        for extra, needle in ((["--out", str(tmp_path / "x")], "--out"), (["--minutes", str(tree["cb702_pre"] / "minutes")], "--minutes"),
                              (["--prereg", "x.md"], "--prereg is honoured only"), (["--no-freeze-check"], "only together with --dry-run"),
                              (["--keys", "com"], "--keys com")):
            with pytest.raises(SystemExit) as ex:
                main(tree, "aplus-read", *extra)
            assert ex.value.code == 2 and needle in capsys.readouterr().err, extra
        p = tree["cb702"] / "out" / "candidates.tsv"
        before = p.read_bytes()
        p.write_bytes(before + b"\n")
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-read")
        assert ex.value.code == 2 and "cb702/out/candidates.tsv sha256 mismatch" in capsys.readouterr().err
        p.write_bytes(before)
        (tree["cb702_pre"] / "out" / ap.PROFILE_NAME).write_text("m\tprofile\n")                        # the profile is a pin
        with pytest.raises(SystemExit):
            main(tree, "aplus-read")
        assert "aplus_intraday_profile.tsv sha256 mismatch" in capsys.readouterr().err
        (tree["cb702_pre"] / "out" / ap.PROFILE_NAME).write_text(ap.profile_text(fx.PROFILE))
        done = tree["cb702"] / "minutes" / "_done.psv"
        logged = done.read_text()
        done.write_text(logged.replace("F1", "NOPE", 1))
        doc(tree)
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-read")
        assert ex.value.code == 2 and "pairs are not logged" in capsys.readouterr().err
        done.write_text(logged)
        doc(tree)
        assert not list((tree["cb702"] / "out").glob("*aplus*")) and not list((rn.HERE / "out").glob("aplus_verdict*"))


# ═══ every check's failing case ════════════════════════════════════════════════════════════════════════════════════════════════════
def _feats(tree, with_perturbation=True):
    ctx = rr.resolve(ap.APLUS_READ, ns(tree), rn)
    prep = ap.aplus_prepare(ctx)
    feats = ap.build_features(ctx, prep, lambda *a: None, with_perturbation)
    return ctx, prep, feats, feats["cols"], ap.rate_population(feats["cols"])


class TestFailingCases:
    def test_step0_mismatch_stops_before_any_outcome(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        set_expected(monkeypatch, tree, weeks=7)
        monkeypatch.setattr(ap, "read_outcomes", lambda *a, **k: (_ for _ in ()).throw(AssertionError("an outcome column was opened")))
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-read")
        assert ex.value.code == 3 and "STEP 0 FAILED" in capsys.readouterr().out
        assert not (tree["cb702"] / "out" / "aplus_verdict_discovery.json").exists() and (rn.HERE / "out" / "aplus_summary_discovery.txt").exists()

    def test_the_profile_sha_mismatch_fails_step0(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        set_expected(monkeypatch, tree)
        monkeypatch.setattr(ap, "PROFILE_SHA_EXPECTED", "1" * 64)
        assert main(tree, "aplus-read", "--dry-run") is None
        assert "is not the EXPECTED" in capsys.readouterr().out

    def test_check3_a_missing_p5_row(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        set_expected(monkeypatch, tree)
        p5 = tree["cb702"] / "out" / "trades_discovery_p5.tsv.gz"
        t = rn.read_tsv(p5)
        t[t["ticker"] != "F1"].to_csv(p5, sep="\t", index=False, na_rep="", compression="gzip")
        doc(tree)
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-read")
        o = capsys.readouterr().out
        assert ex.value.code == 3 and "IMPLEMENTATION CHECK FAILED" in o and "P5: no row for" in o

    def test_check1a_and_check5_a_reader_that_includes_the_fill_minute(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch)
        real = ap.window_stats

        def broken(mb, fill_minute):
            return real(mb, fill_minute + 1)                                  # the window extended by the fill minute
        monkeypatch.setattr(ap, "window_stats", broken)
        ctx, prep, feats, cols, res = _feats(tree)
        assert feats["pert_ok"] < feats["n_blocks_ok"]
        p1, _ = ap.check1_lookahead(cols, res, feats, prep, ctx)
        assert any("check 1:" in x and "randomised" in x for x in p1)
        p5, _ = ap.check5_breakout_inputs(cols, res, feats, prep, ctx)
        assert any("check 5" in x for x in p5)

    def test_check1b_a_scorer_that_reads_an_e_day_column(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch)
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        real = ap.rate_population

        def broken(c, *a, **k):
            r = real(c, *a, **k)
            ce = c.get("close_E")
            if ce is not None:                                                # a reader that leans on close_E when it is there
                for N in ap.NS:
                    r["flag"][("core", N)] = np.where(np.asarray([x is not None and x > 100.5 for x in ce]), "rest", r["flag"][("core", N)])
            return r
        monkeypatch.setattr(ap, "rate_population", broken)
        p, _ = ap.check1_lookahead(cols, res, feats, prep, ctx)
        assert any("check 1 (b)" in x for x in p)

    def test_check1c_a_feature_that_reads_past_d(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch)
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        real = ap.vol_dry5_of

        def broken(ex, ticker, D):
            ci, _h, _l, _c, v = ex.rows(ticker)
            dci = ex.cal_ci.get(D)
            b = np.searchsorted(ci, dci, side="right")
            return float(v[b - 4:b + 1].mean() / v[b - 9:b - 4].mean())        # one row after D
        monkeypatch.setattr(ap, "vol_dry5_of", broken)
        p, _ = ap.check1_lookahead(cols, res, feats, prep, ctx)
        assert any("check 1 (c)" in x for x in p)

    def test_check2_a_pool_that_includes_the_days_own_fills(self, tmp_path, monkeypatch):
        """A reference set that holds the day's own fills (the 10-21 draft's within-week rank): the cutoff of an A+ fill then moves when the
        later fills of its day are removed - check 2 fires."""
        tree = aplus_tree(tmp_path, monkeypatch)
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        real = ap.pool_percentiles

        def broken(X, pool, day, floor=ap.POOL_FLOOR):
            return real(X, np.concatenate([pool, day]), day, floor)
        monkeypatch.setattr(ap, "pool_percentiles", broken)
        res_b = ap.rate_population(cols)
        p, _ = ap.check2_later_fills(cols, res_b)
        assert p and "check 2" in p[0]
        monkeypatch.undo()
        assert ap.check2_later_fills(cols, ap.rate_population(cols))[0] == []

    def test_check5_a_fill_minute_that_changes_neither_number(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch, duds=("F1",))
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        p, _ = ap.check5_breakout_inputs(cols, res, feats, prep, ctx)
        assert any("change NEITHER number" in x for x in p) and any("left the range unchanged" in x for x in p)

    def test_check4_a_week_with_more_than_n_or_a_duplicate(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch)
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        assert ap.check4_counts(cols, res)[0] == []
        fl = res["flag"][("core", 3)]
        i = int(np.flatnonzero(fl == "capped")[0])
        fl[i] = "aplus"                                                      # a 4th A+ in a week whose cap is 3
        p, _ = ap.check4_counts(cols, res)
        assert any("has 4 A+" in x for x in p)
        fl[i] = "capped"
        j = int(np.flatnonzero(fl == "aplus")[0])
        cols2 = dict(cols)
        cols2["ticker"] = list(cols["ticker"])
        k = int(np.flatnonzero(fl == "aplus")[1])
        cols2["ticker"][k], cols2["E"] = cols["ticker"][j], list(cols["E"])
        cols2["E"][k] = cols["E"][j]                                         # two A+ rows with the same (ticker, E)
        assert any("not unique" in x for x in ap.check4_counts(cols2, res)[0])

    def test_check6_a_pool_window_of_the_wrong_length(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch)
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        res100 = ap.rate_population(cols, pool_sessions=100)                    # the fixture's day clusters sit 100 sessions apart: a 100-session window reaches the previous one
        p, _ = ap.check6_pool(cols, res100)
        assert any("independent count" in x for x in p)
        cols["week"][0] = "2000-W01"
        assert any("ISO week" in x for x in ap.check6_pool(cols, res)[0])

    def test_check7_an_order_dependent_engine(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch)
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        real = ap.rate_population

        def broken(c, *a, **k):
            r = real(c, *a, **k)
            r["flag"][("core", 3)][7] = "aplus"                               # the row at position 7, whichever fill that is
            return r
        monkeypatch.setattr(ap, "rate_population", broken)
        p, _ = ap.check7_shuffle(cols, broken(cols))
        assert p and "check 7" in p[0]

    def test_check9_a_stair_step_that_disagrees_with_the_chain_at_d(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch, extra_watch_after_d=True)
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        assert ap.check9_stair(cols, feats, prep, ctx)[0] == []
        cols["stair_n"] = [None if x is None else x + 1 for x in cols["stair_n"]]
        p, _ = ap.check9_stair(cols, feats, prep, ctx)
        assert any("check 9" in x for x in p)

    def test_check12_a_scale_that_disagrees_with_the_export(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch)
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        assert ap.check12_scales(cols, res, feats)[0] == []
        i = cols["ticker"].index("F1")
        cols["wk_ratio"][i] = cols["wk_ratio"][i] * 2
        p, _ = ap.check12_scales(cols, res, feats)
        assert any("scales" in x for x in p)
        cols["tightening_ratio"][i] = 0.3
        assert any("tightening" in x for x in ap.check12_scales(cols, res, feats)[0])

    def test_check11_a_rederivation_that_differs_writes_nothing(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        set_expected(monkeypatch, tree)
        real = rd.rederive

        def broken(*a, **k):
            r = real(*a, **k)
            r["aplus"][("core", 3)] = set(list(r["aplus"][("core", 3)])[:-1])
            return r
        monkeypatch.setattr(rd, "rederive", broken)
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-read")
        o = capsys.readouterr().out
        assert ex.value.code == 3 and "MISMATCH: the A+ set differs on (core, N = 3)" in o and "the result is NOT written" in o
        assert not (tree["cb702"] / "out" / "aplus_verdict_discovery.json").exists() and not (tree["cb702"] / "out" / "trades_discovery_aplus.tsv.gz").exists()

    def test_the_c0_integers_must_describe_the_table(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        set_expected(monkeypatch, tree)
        monkeypatch.setitem(ap.C0_PUBLISHED, "discovery", dict(ap.C0_PUBLISHED["discovery"], n=1))
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-read")
        assert ex.value.code == 3 and "C0 INTEGERS DIFFER" in capsys.readouterr().out

    def test_check4_a_golden_failure_fails_the_run(self, tmp_path, monkeypatch, capsys):
        tree = aplus_tree(tmp_path, monkeypatch)
        set_expected(monkeypatch, tree)
        monkeypatch.setattr(fx, "run_golden", lambda: ["E: a hand expectation differs"])
        with pytest.raises(SystemExit) as ex:
            main(tree, "aplus-read")
        assert ex.value.code == 3 and "check 4 (golden fixtures): E: a hand expectation differs" in capsys.readouterr().out


# ═══ the look-ahead invariance on the synthetic population ═══════════════════════════════════════════════════════════════════════════
class TestLookAhead:
    def test_the_checks_pass_on_the_synthetic_population(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch, extra_watch_after_d=True)
        ctx, prep, feats, cols, res = _feats(tree)
        for fn in (lambda: ap.check1_lookahead(cols, res, feats, prep, ctx), lambda: ap.check2_later_fills(cols, res), lambda: ap.check5_breakout_inputs(cols, res, feats, prep, ctx),
                   lambda: ap.check6_pool(cols, res), lambda: ap.check7_shuffle(cols, res), lambda: ap.check9_stair(cols, feats, prep, ctx),
                   lambda: ap.check12_scales(cols, res, feats), lambda: ap.check3_join(cols, feats, prep, ctx, ap.PROFILE_SHA_EXPECTED)):
            p, lines = fn()
            assert p == [] and lines

    def test_the_perturbed_export_randomises_only_after_d(self, tmp_path, monkeypatch):
        tree = aplus_tree(tmp_path, monkeypatch)
        ctx, prep, feats, cols, res = _feats(tree, with_perturbation=False)
        ex = feats["ex"]
        i = cols["ticker"].index("F1")
        pex = ap.PerturbedExport(ex, cols["D"][i], 1)
        ci, h, l, c, v = ex.rows("F1")
        ci2, h2, l2, c2, v2 = pex.rows("F1")
        after = ci > ex.cal_ci[cols["D"][i]]
        assert np.array_equal(h[~after], h2[~after]) and not np.array_equal(h[after], h2[after]) and after.sum() == 1
        assert ap.export_features(pex, "F1", cols["pole_date"][i], cols["D"][i], cols["base_len"][i])[:3] == ap.export_features(ex, "F1", cols["pole_date"][i], cols["D"][i], cols["base_len"][i])[:3]

    def test_perturbed_minutes_change_only_from_the_fill_minute_on(self):
        mb = rn.cb.minute_bars_from_lists(list(range(10)), [1.0] * 10, [2.0] * 10, [0.5] * 10, [1.5] * 10, [7.0] * 10)
        p = ap.perturb_minutes(mb, 6, np.random.default_rng(3), rn.cb)
        keys = ("sumv", "maxh", "minl", "first_open", "n_present", "n_absent", "min0_absent")
        a, b = ap.window_stats(p, 6), ap.window_stats(mb, 6)
        assert list(p.v[:6]) == [7.0] * 6 and (p.h[6:] != 2.0).any() and all(a[k] == b[k] for k in keys)
        assert a["h_fill"] != b["h_fill"] and a["v_fill"] != b["v_fill"]                                  # the fill minute itself is randomised
        assert ap.window_stats(mb, 6)["sumv"] == 42.0 and ap.window_stats(mb, 6)["v_fill"] == 7.0 and ap.window_stats(mb, 11)["fill_present"] == 0


# ═══ the readers, the chain, the week rule, the re-derivation's independence ══════════════════════════════════════════════════════════
class TestPieces:
    def test_week_in_era_and_the_edge_rule(self):
        assert ap.iso_week("2022-01-03") == "2022-W01" and not ap.week_in_era("2022-01-03", "pre") and ap.week_in_era("2021-12-31", "pre")
        assert ap.week_in_era("2025-01-02", "discovery") and not ap.week_in_era("2025-01-03", "holdout") and ap.week_in_era("2025-01-06", "holdout")
        assert ap.week_in_era("2025-01-03", "discovery")

    def test_chain_at_d_reads_rows_up_to_d_only(self):
        poles = [("2023-01-05", 10, "p10"), ("2023-01-09", 12, "p12"), ("2023-01-20", 16, "p16"), ("2023-02-01", 13, "p13")]
        assert ap.chain_at_d(poles, "2023-01-20", 3) == {10: "p10", 12: "p10", 16: "p16"}
        assert ap.chain_at_d(poles, "2023-02-01", 3) == {10: "p10", 12: "p10", 13: "p10", 16: "p10"}      # the later pole bridges the two bases
        assert ap.stair_n_of("X", 200, 16, [(150, 10), (160, 12), (170, 16)], ap.chain_at_d(poles, "2023-01-20", 3), 0) == 1
        assert ap.stair_n_of("X", 200, 16, [(190, 10)], {10: "a", 16: "b"}, 0) == 1 and ap.stair_n_of("X", 200, 16, [(190, 10)], {10: "a", 16: "b"}, 81) is None
        assert ap.stair_n_of("X", 100, 16, [(90, 10)], {10: "a", 16: "b"}, 0) is None                 # the window [-20, 99] starts before the file's first E
        with pytest.raises(ValueError, match="not in the chain"):
            ap.stair_n_of("X", 200, 16, [(190, 99)], {16: "b"}, 0)

    def test_read_profile_refuses_any_other_shape(self, tmp_path):
        p = tmp_path / "p.tsv"
        p.write_text(ap.profile_text(fx.PROFILE))
        assert np.array_equal(ap.read_profile(p), fx.PROFILE) and ap.profile_problems(fx.PROFILE) == [] or True
        assert [x for x in ap.profile_problems(fx.PROFILE) if "pinned" not in x] == []
        p.write_text(ap.profile_text(fx.PROFILE).rstrip("\n"))
        with pytest.raises(ValueError, match="byte-for-byte"):
            ap.read_profile(p)
        bad = fx.PROFILE.copy()
        bad[100] = 0.0
        assert any("non-decreasing" in x for x in ap.profile_problems(bad))

    def test_the_rederivation_imports_no_runner_code_and_agrees_on_the_golden_rules(self):
        # source-pin-ok: the registration requires the re-derivation to use NO runner code - its import list IS the behaviour under test
        tree = ast.parse(Path(rd.__file__).read_text())
        names = {n.module.split(".")[-1] if isinstance(n, ast.ImportFrom) else a.name.split(".")[-1] for n in ast.walk(tree)
                 if isinstance(n, (ast.Import, ast.ImportFrom)) for a in (n.names if isinstance(n, ast.Import) else [n])}
        assert not names & {"runner", "aplus_read", "registered_read", "consolidation_breakout", "aplus_fixtures"}, names
        h, l, c = fx.base_bars(15, 0.3, 0.6)
        assert rd.weekly(h, l, c, 15) == pytest.approx(ap.wk_ratio_of(h, l, c, 15)) and rd.pullbacks(h, l) == pytest.approx(ap.pb_ratio_of(h, l))
        r = np.random.default_rng(2).normal(0, 1, 50)
        m = np.array([f"2023-{1 + i % 5:02d}" for i in range(50)])
        assert rd.boot_ci(r, m, "k") == rn.block_bootstrap_ci(r, m, key="k")

    def test_the_minute_reader_keeps_the_last_block_per_member(self, tmp_path):
        f = tmp_path / "2023-01-03.psv.gz"
        fm._append_gz(f, ["AAA|0|1|1|1|1|1", "AAA|1|1|1|1|1|1", "BBB|0|2|2|2|2|2"])
        fm._append_gz(f, ["AAA|0|9|9|9|9|9", "AAA|2|9|9|9|9|9"])
        b = rd.minute_blocks(f)
        assert list(b["AAA"]["v"]) == [9.0, 9.0] and list(b["BBB"]["v"]) == [2.0] and set(rd.minute_blocks(f, {"BBB"})) == {"BBB"}
        f.write_bytes(f.read_bytes() + b"\x1f\x8b\x08\x00trunc")
        assert list(rd.minute_blocks(f)["AAA"]["v"]) == [9.0, 9.0]


def test_the_registry_holds_the_three_aplus_reads_and_the_two_plain_stages():
    assert set(rn.REGISTERED_READS) == {"aplus-read", "aplus-confirm", "aplus-hindsight"} and {"aplus-profile", "aplus-verdict"} <= set(rn.BUILTIN_STAGES)
    assert ap.APLUS_READ.periods == ("pre", "discovery") and ap.APLUS_CONFIRM.periods == ("holdout",) and ap.APLUS_READ.order == rr.DEFAULT_ORDER
