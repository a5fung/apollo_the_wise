"""Synthetic tests for 02_fit_filter.py (#705 Track A, the fit module). No real file is opened by any test.

Run:  python3 -m pytest scripts/probes/_705_track_a_1023/test_02_fit_filter.py -q
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fit02", os.path.join(HERE, "02_fit_filter.py"))
fit = importlib.util.module_from_spec(_spec)
sys.modules["fit02"] = fit
_spec.loader.exec_module(fit)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# synthetic bars + a watch row
# ═════════════════════════════════════════════════════════════════════════════════════════════
def bdays(start: str, n: int) -> list:
    return [str(d.date()) for d in pd.bdate_range(start, periods=n)]


CAL = bdays("2019-01-01", 320)
P_IDX = 200                      # the pole top
BASE_LEN = 15
D_IDX = P_IDX + BASE_LEN         # the watch night


def base_bars():
    """The base P..D (16 rows): swing highs at 0 (P), 5 and 10; volumes 1000 on D-9..D-5 and 400 on D-4..D."""
    h = np.array([120, 110, 105, 103, 108, 115, 111, 109, 110, 111, 112, 110, 109, 108, 107, 106], dtype=float)
    l = np.array([112, 100, 101, 99, 102, 110, 108, 107, 106, 108, 109, 105, 104, 103, 102, 101], dtype=float)
    c = (h + l) / 2.0
    c[-1] = 103.0
    return h, l, c


def make_export(extra_after: bool = True):
    """SPY on every session + TST: flat 50s before the pole, the base P..D, then 100 more rows after D."""
    rows = []
    for i, d in enumerate(CAL):
        rows.append(("SPY", d, 300.0, 299.0, 299.5, 1e6))
    h, l, c = base_bars()
    for i, d in enumerate(CAL):
        if i < P_IDX:
            hh, ll, cc = 50.0 + 0.1 * (i % 7), 49.0, 49.5 + 0.05 * (i % 5)
        elif i <= D_IDX:
            k = i - P_IDX
            hh, ll, cc = h[k], l[k], c[k]
        else:
            if not extra_after:
                break
            hh, ll, cc = 99.0, 97.0, 98.0
        v = 1000.0 if D_IDX - 9 <= i <= D_IDX - 5 else (400.0 if D_IDX - 4 <= i <= D_IDX else 777.0)
        rows.append(("TST", d, hh, ll, cc, v))
    df = pd.DataFrame(rows, columns=["ticker", "date", "h", "l", "c", "v"])
    return fit.export_from_frame(df.sample(frac=1.0, random_state=3))      # unsorted on purpose: the loader sorts


def watch_row(**kw):
    w = dict(ticker="TST", watch_date=CAL[D_IDX], split="pre", pole_date=CAL[P_IDX], base_len=float(BASE_LEN), adr20=0.05, close=100.0,
             pivot_tl=110.0, pole_high=120.0, pole_low_date=CAL[P_IDX - 30], tightening_ratio=0.7, base_depth=0.175, retrace=0.4,
             prior_move=1.5, pole_day_vol_ratio=3.0, rs_best=91.0, grp_pct=75.0, trigger_bar_range_adr=0.6)
    w.update(kw)
    return w


class Acc:
    """A minimal watch accessor: {(ticker, date): row}."""

    def __init__(self, rows):
        self.rows = {(r["ticker"], r["watch_date"]): r for r in rows}

    def get(self, t, d):
        return self.rows.get((t, d))


def expected_wk(h, l, c):
    env1 = (h[11:16].max() - l[11:16].min()) / c[15]
    env3 = (h[1:6].max() - l[1:6].min()) / c[5]
    return env1 / env3


def test_export_loader_sorts_and_keys_the_calendar():
    ex = make_export()
    assert ex.cal == CAL
    ci, h, l, c, v = ex.rows("TST")
    assert (np.diff(ci) > 0).all() and h[P_IDX] == 120.0


def test_each_feature_on_hand_built_bars():
    ex = make_export()
    w = watch_row()
    x, fl = fit.features_for("TST", CAL[D_IDX], Acc([w]), ex, None)
    v = dict(zip(fit.FEATURE_KEYS, x))
    h, l, c = base_bars()
    assert v["wk_ratio"] == pytest.approx(expected_wk(h, l, c), rel=1e-12)
    assert v["pb_ratio"] == pytest.approx(((115 - 106) / 115) / ((120 - 99) / 120), rel=1e-12)
    assert v["vol_dry5"] == pytest.approx(400.0 / 1000.0)
    assert v["dist_level_adr"] == pytest.approx((110 - 100) / (100 * 0.05))
    for k in ("tightening_ratio", "base_depth", "retrace", "prior_move", "pole_day_vol_ratio", "rs_best", "grp_pct", "trigger_bar_range_adr"):
        assert v[k] == w[k], k
    assert not any(fl.values())


def test_short_base_has_no_weekly_reading_and_no_line_no_distance():
    ex = make_export()
    # base_len 14 -> k = 2 < 3: weekly missing (the base rows are then 15, so the base check uses base_len 14 on rows [P+1, D])
    w = watch_row(pole_date=CAL[P_IDX + 1], base_len=14.0, pole_high=110.0, pivot_tl=float("nan"))
    x, fl = fit.features_for("TST", CAL[D_IDX], Acc([w]), ex, None)
    v = dict(zip(fit.FEATURE_KEYS, x))
    assert math.isnan(v["wk_ratio"]) and math.isnan(v["dist_level_adr"]) and not fl["base_mismatch"]


def test_base_mismatch_leaves_both_scales_missing_and_counts():
    ex = make_export()
    x, fl = fit.features_for("TST", CAL[D_IDX], Acc([watch_row(pole_high=121.0)]), ex, None)
    v = dict(zip(fit.FEATURE_KEYS, x))
    assert fl["base_mismatch"] and math.isnan(v["wk_ratio"]) and math.isnan(v["pb_ratio"])


@pytest.mark.parametrize("offset,rs_missing,grp_missing", [(-126, False, False), (-125, True, False), (-63, True, False), (-62, True, True),
                                                            (0, True, True), (1, False, False)])
def test_discontinuous_windows_rs_and_grp(offset, rs_missing, grp_missing):
    ex = make_export()
    disc = np.array([D_IDX + offset], dtype=np.int64)
    x, fl = fit.features_for("TST", CAL[D_IDX], Acc([watch_row()]), ex, disc)
    v = dict(zip(fit.FEATURE_KEYS, x))
    assert math.isnan(v["rs_best"]) == rs_missing and fl["disc_rs_best"] == rs_missing
    assert math.isnan(v["grp_pct"]) == grp_missing


def test_discontinuous_window_prior_move():
    ex = make_export()
    lo = P_IDX - 30
    for d, miss in ((lo, False), (lo + 1, True), (P_IDX, True), (P_IDX + 1, False)):
        x, _ = fit.features_for("TST", CAL[D_IDX], Acc([watch_row(pole_low_date=CAL[lo])]), ex, np.array([d], dtype=np.int64))
        assert math.isnan(dict(zip(fit.FEATURE_KEYS, x))["prior_move"]) == miss, d


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the within-day AUC
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_within_day_auc_hand_example_ties_half_excluded_out():
    #            day 1: negatives 1 2 2 3, an EXCLUDED row 10, the positive 2 -> (1 + 0.5 x 2) / 4 = 0.5
    #            day 2: negatives 5 NaN, the positive 7 -> 1.0; a positive with NaN skipped
    x = np.array([1, 2, 2, 3, 10, 2, 5, np.nan, 7, np.nan], dtype=float)
    day = np.array([1, 1, 1, 1, 1, 1, 2, 2, 2, 2])
    pos = np.array([0, 0, 0, 0, 0, 1, 0, 0, 1, 1], dtype=bool)
    neg = np.array([1, 1, 1, 1, 0, 0, 1, 1, 0, 0], dtype=bool)
    r = fit.within_day_auc(x, day, pos, neg)[0]
    assert r["auc"] == pytest.approx(0.75) and r["n_pos"] == 2 and r["skip_missing"] == 1


def test_within_day_auc_matches_brute_force():
    rng = np.random.default_rng(1)
    n = 600
    day = rng.integers(0, 15, n)
    x = rng.integers(0, 8, n).astype(float)
    x[rng.random(n) < 0.15] = np.nan
    kind = rng.choice(3, n, p=[0.05, 0.85, 0.10])      # 0 pos, 1 neg, 2 excluded
    pos, neg = kind == 0, kind == 1
    tot, cnt = 0.0, 0
    for d in np.unique(day[pos]):
        nv = x[(day == d) & neg]
        nv = nv[~np.isnan(nv)]
        for pv in x[(day == d) & pos]:
            if np.isnan(pv) or len(nv) == 0:
                continue
            tot += ((nv < pv).sum() + 0.5 * (nv == pv).sum()) / len(nv)
            cnt += 1
    assert fit.within_day_auc(x, day, pos, neg)[0]["auc"] == pytest.approx(tot / cnt, rel=1e-12)


def test_direction_is_applied_before_the_auc():
    # lower is better for tightening_ratio: a positive with the SMALLEST raw value must read AUC 1 once oriented
    X = np.full((5, len(fit.FEATURE_KEYS)), np.nan)
    j = fit.FIDX["tightening_ratio"]
    X[:, j] = [0.1, 0.5, 0.6, 0.7, 0.8]
    Xo = X * fit.DIRECTION
    pos = np.array([1, 0, 0, 0, 0], dtype=bool)
    r = fit.within_day_auc(Xo, np.zeros(5, dtype=int), pos, ~pos)[j]
    assert r["auc"] == 1.0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the subset rule
# ═════════════════════════════════════════════════════════════════════════════════════════════
def aucs_of(**kw):
    a = {k: 0.52 for k in fit.FEATURE_KEYS}
    a.update(kw)
    return a


def test_subset_rule_top_five_descending_and_against_reported():
    a = aucs_of(rs_best=0.70, wk_ratio=0.65, retrace=0.60, vol_dry5=0.59, grp_pct=0.585, prior_move=0.58, base_depth=0.45)
    sub, against = fit.subset_rule(a)
    assert sub == ["rs_best", "wk_ratio", "retrace", "vol_dry5", "grp_pct"]          # prior_move (0.58) is the sixth: cut by the cap of 5
    assert against == ["base_depth"]


def test_subset_rule_empty_is_fail_and_below_half_never_chosen():
    a = aucs_of(rs_best=0.579, base_depth=0.30)
    sub, against = fit.subset_rule(a)
    assert sub == [] and against == ["base_depth"]
    assert fit.bar_verdict(True, 0, "n/a", 0)[0] == "FAIL"
    sub56, _ = fit.subset_rule(a, 0.56)                                               # a threshold neighbour may still find one
    assert sub56 == ["rs_best"]


def test_subset_rule_ties_break_by_table_order():
    a = aucs_of(grp_pct=0.6, tightening_ratio=0.6)
    assert fit.subset_rule(a)[0] == ["tightening_ratio", "grp_pct"]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the score, the pool, the cap
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_subset_score_counts_missing_as_half():
    P = np.array([[0.9, np.nan], [np.nan, np.nan], [0.2, 0.4]])
    assert list(fit.subset_score(P, [0, 1])) == pytest.approx([0.7, 0.5, 0.3])


def stream_one_feature(pool_vals, day_vals, pool_day=5, day=10, F=1):
    """Pool rows on E_ci = `pool_day` (inside [day-20, day-1]) and the day's rows on E_ci = `day`; one feature column (oriented)."""
    n0, n1 = len(pool_vals), len(day_vals)
    X = np.full((n0 + n1, F), np.nan)
    X[:n0, 0] = pool_vals
    X[n0:, 0] = day_vals
    E = np.array([pool_day] * n0 + [day] * n1)
    tk = np.array([f"P{i:03d}" for i in range(n0)] + [f"D{i:03d}" for i in range(n1)])
    order = np.lexsort((tk, E))
    return X[order], E[order], tk[order]


def test_pool_percentile_reference_scores_cutoff_and_take():
    X, E, tk = stream_one_feature(np.arange(1, 41, dtype=float), [30.0])
    eng = fit.PoolEngine(X, E, tk, np.array(["W"] * len(E)))
    i = int(np.flatnonzero(tk == "D000")[0])
    assert eng.own[i, 0] == pytest.approx((29 + 0.5) / 40)                           # the fill against the pool (it is not in S)
    r = eng.rate([0], 6)
    # members vs the pool minus themselves: (y - 1) / 39; the 24th-highest y is 17 -> 16 / 39
    assert r["cutoff"][i] == pytest.approx(16 / 39)
    assert r["flag"][i] == fit.FLAG_TAKE


def test_pool_floor_below_thirty_counts_half():
    X, E, tk = stream_one_feature(np.r_[np.arange(1, 30, dtype=float), [np.nan] * 11], [100.0])   # 29 non-missing of 40 members
    eng = fit.PoolEngine(X, E, tk, np.array(["W"] * len(E)))
    i = int(np.flatnonzero(tk == "D000")[0])
    assert math.isnan(eng.own[i, 0])
    r = eng.rate([0], 6)
    assert r["score"][i] == 0.5
    # every member reads 0.5 (pool minus itself < 30), so all 40 are rated (R-a) and the cutoff is 0.5: the fill (0.5) is TAKE
    assert r["cutoff"][i] == 0.5 and r["flag"][i] == fit.FLAG_TAKE
    assert r["strict_unrated"][i]                                                    # the strict reading would leave it UNRATED


def test_unrated_with_fewer_than_4n_members():
    X, E, tk = stream_one_feature(np.arange(1, 24, dtype=float), [30.0])            # 23 members < 24
    eng = fit.PoolEngine(X, E, tk, np.array(["W"] * len(E)), floor=5)
    i = int(np.flatnonzero(tk == "D000")[0])
    assert eng.rate([0], 6)["flag"][i] == fit.FLAG_UNRATED
    assert eng.rate([0], 4)["flag"][i] != fit.FLAG_UNRATED                           # 16 suffice at N = 4


def test_weekly_cap_take_then_capped_in_ticker_order_and_reset():
    score = np.array([0.9] * 8 + [0.9, 0.1, np.nan])
    cutoff = np.array([0.5] * 10 + [np.nan])
    week = np.array(["W1"] * 8 + ["W2", "W2", "W2"])
    f = fit.apply_cap(score, cutoff, week, 6)
    assert list(f[:8]) == ["TAKE"] * 6 + ["CAPPED"] * 2
    assert list(f[8:]) == ["TAKE", "PASS", "UNRATED"]


def test_engine_requires_e_ticker_order():
    X = np.zeros((2, 1))
    with pytest.raises(AssertionError):
        fit.PoolEngine(X, np.array([2, 1]), np.array(["A", "B"]), np.array(["W", "W"]))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the plateau, the bar
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_plateau_need_is_one_sided_max4_ceil075():
    a = aucs_of(rs_best=0.70, wk_ratio=0.65)
    counts = {("rs_best", "wk_ratio"): 8, ("rs_best",): 6, ("wk_ratio",): 7}
    pl = fit.plateau(a, ["rs_best", "wk_ratio"], lambda s: counts[tuple(s)], 8)
    assert pl["need"] == 6 and pl["verdict"] == "HOLDS"
    counts[("rs_best",)] = 5
    assert fit.plateau(a, ["rs_best", "wk_ratio"], lambda s: counts[tuple(s)], 8)["verdict"] == "FAILS"
    counts[("rs_best",)] = 30                                                        # flagging MORE never fails
    assert fit.plateau(a, ["rs_best", "wk_ratio"], lambda s: counts[tuple(s)], 8)["verdict"] == "HOLDS"
    assert fit.plateau(a, ["rs_best", "wk_ratio"], lambda s: 4, 3)["need"] == 4


def test_plateau_leave_one_out_re_derives_and_admits_a_sixth():
    a = aucs_of(rs_best=0.70, wk_ratio=0.68, retrace=0.66, vol_dry5=0.64, grp_pct=0.62, prior_move=0.60)
    seen = []
    fit.plateau(a, fit.subset_rule(a)[0], lambda s: seen.append(tuple(s)) or 9, 9)
    assert ("wk_ratio", "retrace", "vol_dry5", "grp_pct", "prior_move") in seen     # rs_best left out -> prior_move enters


def test_plateau_threshold_neighbour_empty_flags_zero():
    a = aucs_of(rs_best=0.59)                                                        # at 0.60 the subset is empty
    pl = fit.plateau(a, ["rs_best"], lambda s: 9, 9)
    row = [r for r in pl["neighbours"] if r["name"] == "screen 0.60"][0]
    assert row["subset"] == [] and row["count"] == 0 and pl["verdict"] == "FAILS"


def test_plateau_one_feature_swaps_in_the_next_ranked_or_cant_tell():
    a = aucs_of(rs_best=0.65, wk_ratio=0.55)
    pl = fit.plateau(a, ["rs_best"], lambda s: 9, 9)
    assert [r["name"] for r in pl["neighbours"]][-1] == "wk_ratio swapped in for rs_best" and pl["verdict"] == "HOLDS"
    a2 = {k: 0.40 for k in fit.FEATURE_KEYS}
    a2["rs_best"] = 0.65
    pl2 = fit.plateau(a2, ["rs_best"], lambda s: 9, 9)
    assert pl2["verdict"] == "CAN'T TELL"


@pytest.mark.parametrize("c,plat,eb,want", [(1, "HOLDS", 1, "FAIL"), (0, "HOLDS", 1, "FAIL"), (2, "HOLDS", 1, "CAN'T TELL"),
                                            (4, "HOLDS", 1, "CAN'T TELL"), (5, "HOLDS", 1, "PASS"), (5, "HOLDS", 0, "CAN'T TELL"),
                                            (5, "FAILS", 1, "CAN'T TELL"), (9, "CAN'T TELL", 3, "CAN'T TELL"), (66, "HOLDS", 9, "PASS")])
def test_bar_verdict_edges(c, plat, eb, want):
    assert fit.bar_verdict(False, c, plat, eb)[0] == want


def test_poisson_tail_matches_the_registered_chance():
    assert fit.poisson_tail(5, 0.87) == pytest.approx(0.0021, abs=2e-4)               # "chance alone reaches 5 with probability 0.2%"
    assert 1 - fit.poisson_tail(2, 0.87) == pytest.approx(0.78, abs=0.01)            # "<= 1 ... what chance gives 78% of the time"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# GUARD 4 — the look-ahead test catches a leaking feature
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_lookahead_passes_the_real_features():
    ex = make_export()
    acc = Acc([watch_row(), watch_row(watch_date=CAL[D_IDX + 1], rs_best=5.0)])
    n, diffs = fit.lookahead_test([("TST", CAL[D_IDX])], acc, ex, {"TST": np.array([D_IDX - 300], dtype=np.int64)})
    assert n == 1 and diffs == []


def test_lookahead_catches_a_feature_reading_the_next_bar():
    ex = make_export()
    acc = Acc([watch_row()])

    def leaky(t, D, wacc, ex_, disc):
        x, fl = fit.features_for(t, D, wacc, ex_, disc)
        ci, h, l, c, v = ex_.rows(t)
        b = int(np.searchsorted(ci, ex_.cal_ci[D], "right"))
        x = x.copy()
        x[fit.FIDX["vol_dry5"]] = v[b - 4:b + 1].mean() / v[b - 9:b - 4].mean()        # D-3..D+1: one bar after D
        return x, fl
    _, diffs = fit.lookahead_test([("TST", CAL[D_IDX])], acc, ex, {}, feat_fn=leaky)
    assert diffs and "vol_dry5" in diffs[0][2]


def test_lookahead_catches_a_feature_reading_a_later_watch_row():
    ex = make_export()
    acc = Acc([watch_row(), watch_row(watch_date=CAL[D_IDX + 1])])

    def leaky(t, D, wacc, ex_, disc):
        x, fl = fit.features_for(t, D, wacc, ex_, disc)
        nxt = wacc.get(t, ex_.cal[ex_.cal_ci[D] + 1])
        x = x.copy()
        x[fit.FIDX["rs_best"]] = nxt["rs_best"]
        return x, fl
    _, diffs = fit.lookahead_test([("TST", CAL[D_IDX])], acc, ex, {}, feat_fn=leaky)
    assert diffs and "rs_best" in diffs[0][2]


def test_lookahead_catches_a_disc_window_reaching_past_d():
    ex = make_export()
    acc = Acc([watch_row()])

    def leaky(t, D, wacc, ex_, disc):
        x, fl = fit.features_for(t, D, wacc, ex_, disc)
        iD = ex_.cal_ci[D]
        if disc is not None and ((disc > iD) & (disc <= iD + 60)).any():                  # a window that wrongly reaches forward
            x = x.copy()
            x[fit.FIDX["grp_pct"]] = np.nan
        return x, fl
    _, diffs = fit.lookahead_test([("TST", CAL[D_IDX])], acc, ex, {}, feat_fn=leaky)
    assert diffs and "grp_pct" in diffs[0][2]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# GUARD 1 — the whitelist
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_whitelist_refuses_an_extra_column_before_opening():
    with pytest.raises(fit.WhitelistError):
        fit.wl_check("cand_A", list(fit.WHITELIST["cand_A"]) + ["close_E"])
    with pytest.raises(fit.WhitelistError):
        fit.wl_check("cand_A", ["ticker", "D", "C2"])
    with pytest.raises(fit.WhitelistError):
        fit.wl_check("trades", ["ticker"])
    with pytest.raises(fit.WhitelistError):                                           # raised before the (missing) file is opened
        fit.wl_read_tsv("labels_joined", ["vid", "r1_status"], (), path="/nonexistent/x.tsv")


def test_whitelist_reads_exactly_the_listed_columns(tmp_path):
    p = tmp_path / "lj.tsv"
    cols = list(fit.WHITELIST["matched_events"])
    pd.DataFrame([dict(zip(cols, ["A", "X", "2020-01-02", "1", "0", "0", "X|2019-12-01"]))]).assign(r1_status="R1", r2="1").to_csv(p, sep="\t", index=False)
    df, _ = fit.wl_read_tsv("matched_events", cols, cols, path=str(p))
    assert list(df.columns) == cols and "r1_status" not in df.columns


def test_no_forward_column_on_any_whitelist_entry():
    for name, cols in fit.WHITELIST.items():
        assert not set(cols) & fit.FORBIDDEN, name
        assert not any(c.startswith("first_") for c in cols), name


# ═════════════════════════════════════════════════════════════════════════════════════════════
# GUARDS 2 and 3 — shuffle tests, planted signal vs none vs a bug
# ═════════════════════════════════════════════════════════════════════════════════════════════
def within_day_data(signal: float, seed: int = 5, days: int = 60, per: int = 50, k: int = 2, discrete: bool = False):
    rng = np.random.default_rng(seed)
    n = days * per
    day = np.repeat(np.arange(days), per)
    pos = np.zeros(n, dtype=bool)
    for d in range(days):
        pos[d * per + rng.choice(per, k, replace=False)] = True
    neg = ~pos
    neg[rng.random(n) < 0.05] = False                                                  # some excluded rows
    neg &= ~pos
    base = rng.integers(0, 4, n).astype(float) if discrete else rng.normal(size=n)
    X = np.column_stack([base + signal * pos, rng.normal(size=n)])
    return X, day, pos, neg


def test_guard2_no_signal_passes():
    X, day, pos, neg = within_day_data(0.0)
    ok, means = fit.guard2_shuffle(X, day, pos, neg, perms=60)
    assert ok and np.all(np.abs(means - 0.5) < 0.02)


def test_guard2_planted_signal_still_passes_the_shuffle():
    X, day, pos, neg = within_day_data(3.0)
    assert fit.within_day_auc(X, day, pos, neg)[0]["auc"] > 0.9
    ok, means = fit.guard2_shuffle(X, day, pos, neg, perms=60)
    assert ok, means


def test_guard2_catches_a_biased_auc():
    X, day, pos, neg = within_day_data(0.0, discrete=True)

    def buggy(Xo, d, p, n, groups=None):                                               # ties counted as WORSE (a bug)
        out = []
        for f in range(Xo.shape[1]):
            tot, cnt = 0.0, 0
            for dd in np.unique(d[p]):
                nv = Xo[(d == dd) & n, f]
                for pv in Xo[(d == dd) & p, f]:
                    tot += (nv <= pv).sum() / len(nv)
                    cnt += 1
            out.append(dict(auc=tot / cnt))
        return out
    ok, means = fit.guard2_shuffle(X, day, pos, neg, perms=20, auc_fn=buggy)
    assert not ok and means[0] > 0.52


def test_guard3_chance_ok_planted_ok_broken_cap_stops():
    rng = np.random.default_rng(9)
    n, days = 4000, 80
    day = np.repeat(np.arange(days), n // days)
    pos = np.zeros(n, dtype=bool)
    pos[rng.choice(n, 40, replace=False)] = True
    neg = ~pos
    take = rng.random(n) < 0.01
    ok, m = fit.guard3_shuffle(take, day, pos, neg, perms=100)
    assert ok and m < 1.5
    planted = take | pos                                                               # every positive flagged: real recall 40 of 40
    assert int((planted & pos).sum()) == 40
    ok2, m2 = fit.guard3_shuffle(planted, day, pos, neg, perms=100)
    assert ok2 and m2 < 1.5
    ok3, m3 = fit.guard3_shuffle(np.ones(n, dtype=bool), day, pos, neg, perms=20)        # a cap that never binds
    assert not ok3 and m3 == 40


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the labels -> the populations
# ═════════════════════════════════════════════════════════════════════════════════════════════
def lab(vid, ts, tk, s0, grade, E, delta, base, era="A", watch="0", tl="0", cov="full"):
    return dict(vid=vid, ts=ts, screen_ticker=tk, sym=tk, s0=s0, era=era, coverage=cov, grade=grade, is_bought=str(int("bought" in grade)),
                is_not_yet=str(int("not_yet" in grade)), is_best=str(int("best" in grade)), watch_at_s0=watch, c0_tl_at_s0=tl,
                delta_tl=str(delta) if E else "", E_tl=E, base_id_tl=base)


GRADE_RX = {"best": r"\bbest setup\b", "bought": r"\bi bought\b", "not_yet": r"\bnot ready\b"}


def toy_labels():
    J = pd.DataFrame([
        lab("v1", "0:01", "AAA", "2020-03-02", "bought", "2020-03-04", 2, "AAA|b1"),        # strictly before -> positive
        lab("v1", "0:02", "BBB", "2020-03-04", "bought", "2020-03-04", 0, "BBB|b1"),        # on E -> positive, at0
        lab("v2", "0:03", "CCC", "2020-03-09", "bought", "2020-03-04", -3, "CCC|b1"),       # after E only -> post
        lab("v2", "0:04", "DDD", "2020-03-01", "not_yet", "2020-03-05", 3, "DDD|b1", watch="1", tl="1"),
        lab("v3", "0:05", "EEE", "2020-03-03", "not_yet", "2020-03-04", 1, "EEE|b1", watch="1", tl="1"),
        lab("v3", "0:06", "EEE", "2020-03-03", "bought", "2020-03-04", 1, "EEE|b1", watch="1", tl="1"),  # EEE's event carries both
        lab("v4", "0:07", "FFF", "2021-02-01", "best", "2021-02-01", 0, "FFF|b1"),         # a 2021 positive (hold-out)
    ])
    ME = pd.DataFrame([
        dict(era="A", sym=s, E_tl=E, bought=b, not_yet=n, best=bb, base_id=f"{s}|b1")
        for s, E, b, n, bb in (("AAA", "2020-03-04", "1", "0", "0"), ("BBB", "2020-03-04", "1", "0", "0"), ("CCC", "2020-03-04", "1", "0", "0"),
                               ("DDD", "2020-03-05", "0", "1", "0"), ("EEE", "2020-03-04", "1", "1", "0"), ("FFF", "2021-02-01", "0", "0", "1"))])
    MO = pd.DataFrame([dict(video="v1", ts="0:01", ticker="AAA", quote="I bought it"), dict(video="v1", ts="0:02", ticker="BBB", quote="nothing"),
                       dict(video="v4", ts="0:07", ticker="FFF", quote="best setup")])
    return J, ME, MO


def test_label_sets_classes_and_readiness_exclusion():
    J, ME, MO = toy_labels()
    ls = fit.label_sets(J, ME, MO, GRADE_RX)
    K = ls["keys"]["A"]
    assert K["pos"] == {("AAA", "2020-03-04"), ("BBB", "2020-03-04"), ("EEE", "2020-03-04"), ("FFF", "2021-02-01")}
    assert K["post"] == {("CCC", "2020-03-04")}
    assert K["strict"] == {("AAA", "2020-03-04"), ("EEE", "2020-03-04")}
    assert K["at0"] == {("BBB", "2020-03-04"), ("FFF", "2021-02-01")}
    assert K["own"] == {("AAA", "2020-03-04"), ("FFF", "2021-02-01")}
    assert ls["own_counts"]["bought"] == 1 and ls["own_counts"]["best"] == 1
    assert ls["posny_ev"]["A"] == {("EEE", "2020-03-04")}
    assert len(ls["ready"]["ny_s0_all"]) == 2 and len(ls["ready"]["ny_s0"]) == 1          # EEE's not-yet label leaves the not-yet side
    assert len(ls["ready"]["b_s0"]) == 1


def test_negatives_round3_rule_later_label_does_not_exclude():
    J, ME, MO = toy_labels()
    ls = fit.label_sets(J, ME, MO, GRADE_RX)
    # the stream on 2020-03-04: the positives, CCC (post-E-only: its label 03-09 comes after its E -> stays a NEGATIVE), GGG (unlabelled),
    # HHH on DDD's base? no - DDD|b1 row on 03-04 whose base was labelled 03-01 (on or before 03-04) -> EXCLUDED
    tick = np.array(["AAA", "BBB", "CCC", "DDD", "EEE", "GGG", "DDD", "FFF", "ZZZ"])
    E = np.array(["2020-03-04"] * 6 + ["2020-03-05", "2021-02-01", "2021-02-01"])
    base = np.array([f"{t}|b1" for t in tick])
    era = fit.Era(name="A", cal=[], ticker=tick, D=E, E=E, E_ci=np.arange(len(E)), week=E, year=np.array([int(x[:4]) for x in E]),
                  retrigger=np.zeros(len(E), dtype=int), C1=np.zeros(len(E), dtype=int), base_id=base, phase={}, X=np.zeros((len(E), 12)))
    ls["ny_ev"]["A"] = {("DDD", "2020-03-05"), ("EEE", "2020-03-04")}
    fit.assign_classes(era, ls)
    c = era.cls
    assert list(tick[c["pos"]]) == ["AAA", "BBB", "EEE", "FFF"]
    assert list(tick[c["neg"]]) == ["CCC", "GGG", "ZZZ"]
    assert list(tick[c["excl"]]) == ["DDD"]
    assert list(tick[c["post"]]) == ["CCC"]
    assert list(c["fit"]) == [True] * 7 + [False, False]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# end to end on fabricated eras: run_fit in the registered order
# ═════════════════════════════════════════════════════════════════════════════════════════════
def fake_era(name: str, start: str, ndays: int, per: int, pos_days: list, seed: int, planted=("rs_best", "vol_dry5")):
    rng = np.random.default_rng(seed)
    cal = bdays(start, ndays)
    rows = []
    for di, d in enumerate(cal):
        if di < 25:
            continue
        for t in range(per):
            rows.append((di, d, f"T{t:03d}"))
        if di in pos_days:
            rows.append((di, d, "AAA"))
    rows.sort(key=lambda r: (r[0], r[2]))
    n = len(rows)
    E_ci = np.array([r[0] for r in rows])
    E = np.array([r[1] for r in rows])
    tk = np.array([r[2] for r in rows])
    X = rng.normal(size=(n, len(fit.FEATURE_KEYS)))
    X[rng.random(n) < 0.3, fit.FIDX["wk_ratio"]] = np.nan
    pos = tk == "AAA"
    X[np.ix_(pos, [j for j, k in enumerate(fit.FEATURE_KEYS) if k not in planted])] = 0.0   # the median: no signal off the planted features
    for k in planted:                                    # the planted positives sit at the better end of the planted features
        X[pos, fit.FIDX[k]] = fit.FEATURES[k][0] * (5.0 + rng.random(int(pos.sum())))
    neg = np.zeros(n, dtype=bool)
    pdates = set(E[pos])
    neg[np.array([x in pdates for x in E])] = True
    neg &= ~pos
    era = fit.Era(name=name, cal=cal, ticker=tk, D=E, E=E, E_ci=E_ci, week=np.array([fit.ap.iso_week(x) for x in E]),
                  year=np.array([int(x[:4]) for x in E]), retrigger=(rng.random(n) < 0.7).astype(int), C1=(rng.random(n) < 0.02).astype(int),
                  base_id=np.array([f"{t}|{e}" for t, e in zip(tk, E)]), phase={"phase_qqq_10_20": np.where(rng.random(n) < 0.6, "1", "0"),
                  "phase_qqq_10_20_s5": np.full(n, "1"), "phase_spy_qqq_50": np.full(n, "1"), "apollo_regime": np.full(n, "")}, X=X)
    fitm = (E <= fit.FIT_LAST_E) if name == "A" else np.zeros(n, dtype=bool)
    z = np.zeros(n, dtype=bool)
    era.cls = dict(pos=pos, neg=neg, excl=z, post=z, strict=pos & (rng.random(n) < 0.5), at0=pos & (rng.random(n) < 0.5), own=pos, bpos=pos, bneg=neg,
                   ny=z, ny_only=z, fit=fitm, hold=(~fitm) if name == "A" else z, lab_by_E=pos, n_gdates=np.array([len(pdates)]))
    return era


def test_run_fit_end_to_end_on_planted_signal(tmp_path):
    calA = bdays("2019-01-01", 760)
    mondays = [i for i, d in enumerate(calA) if pd.Timestamp(d).weekday() == 0 and i >= 30]
    hold_m = [i for i in mondays if calA[i] > fit.FIT_LAST_E][:10]
    fit_m = [i for i in mondays if calA[i] <= fit.FIT_LAST_E]               # ~95 fit positives: random features stay well under 0.58
    A = fake_era("A", "2019-01-01", 760, 30, fit_m + hold_m, seed=11)
    calB = bdays("2022-01-03", 200)
    B = fake_era("B", "2022-01-03", 200, 30, [i for i, d in enumerate(calB) if pd.Timestamp(d).weekday() == 0 and i >= 40][:3], seed=12)
    rng = np.random.default_rng(3)
    nyX = rng.normal(size=(6, 12)) * 0.1
    bX = rng.normal(size=(8, 12)) * 0.1
    for k in ("rs_best", "vol_dry5"):
        bX[:, fit.FIDX[k]] = fit.FEATURES[k][0] * 4.0
        nyX[:, fit.FIDX[k]] = -fit.FEATURES[k][0] * 4.0
    rows_pos = np.flatnonzero(A.cls["pos"])
    A.ready = dict(ny_s0_all=dict(X=nyX, d_ci=np.full(6, 400), tl=np.ones(6, dtype=bool)), b_s0=dict(X=bX, d_ci=np.full(8, 400), tl=np.ones(8, dtype=bool)),
                   ny_s0_in43=np.array([True] * 5 + [False]), ny_ev_all=dict(row=rows_pos[:3]), ny_ev=dict(row=rows_pos[:2]), b_ev=dict(row=rows_pos[3:8]))
    out = []
    take = tmp_path / "take.tsv"
    res = fit.run_fit({"A": A, "B": B}, out.append, take_path=str(take), expect=None)
    assert res["guard2"][0] and res["guard3"][0]
    assert set(res["subset"]) >= {"rs_best", "vol_dry5"}
    assert res["c"] >= 5 and res["era_b"] >= 1
    assert res["verdict"] == "PASS", (res["verdict"], res["why"], res["plateau"])
    t = pd.read_csv(take, sep="\t", dtype=str, keep_default_na=False)
    assert len(t) == len(A.E) + len(B.E)
    wk = t[t.flag == "TAKE"].assign(w=lambda d: [fit.ap.iso_week(x) for x in d.E]).groupby(["era", "w"]).size()
    assert wk.max() <= 6
    text = "\n".join(out)
    assert "READINESS CONTRAST" in text and "BAR VERDICT" in text


def test_run_fit_empty_subset_is_fail_without_a_take_table(tmp_path):
    A = fake_era("A", "2019-01-01", 600, 20, list(range(40, 560, 9)), seed=21, planted=())
    B = fake_era("B", "2022-01-03", 150, 20, [60, 90], seed=22, planted=())
    take = tmp_path / "take.tsv"
    res = fit.run_fit({"A": A, "B": B}, lambda m: None, take_path=str(take), expect=None)
    if res["subset"]:
        pytest.skip("a random feature crossed 0.58 on this seed")
    assert res["verdict"] == "FAIL" and not take.exists()


def test_freeze_check_lists_the_pins_not_under_the_marker(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("body aaaa\n<!-- FREEZE -->\n- module: bbbb\n")
    assert fit.freeze_missing(str(doc), {"m": "bbbb", "x": "aaaa"}) == ["x"]          # a pin ABOVE the marker does not count
    doc.write_text("no marker bbbb")
    assert fit.freeze_missing(str(doc), {"m": "bbbb"}) == ["m"]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the review's hardening (2026-10-23): the registered constants, the edges, the era-B cut, the doc-body pin, the EXPECT assert
# ═════════════════════════════════════════════════════════════════════════════════════════════
# the §5 table, written out HERE (not derived from the module): a flipped sign in FEATURES must fail
SECTION5_DIRECTIONS = [("tightening_ratio", -1), ("wk_ratio", -1), ("pb_ratio", -1), ("base_depth", -1), ("retrace", -1),
                       ("prior_move", +1), ("pole_day_vol_ratio", +1), ("rs_best", +1), ("grp_pct", +1),
                       ("vol_dry5", -1), ("dist_level_adr", -1), ("trigger_bar_range_adr", -1)]


def test_the_twelve_directions_are_the_registered_ones_in_table_order():
    assert list(fit.FEATURE_KEYS) == [k for k, _ in SECTION5_DIRECTIONS]                 # #1..#12, the tie-break order
    assert {k: v[0] for k, v in fit.FEATURES.items()} == dict(SECTION5_DIRECTIONS)
    assert list(fit.DIRECTION) == [d for _, d in SECTION5_DIRECTIONS] and len(fit.FEATURE_KEYS) == 12
    assert fit.FIDX == {k: j for j, (k, _) in enumerate(SECTION5_DIRECTIONS)}


def test_oriented_matrix_applies_the_fixed_direction_per_column():
    era = fake_era("A", "2019-01-01", 40, 3, [30], seed=1)
    raw = np.arange(1, 13, dtype=float)
    era.X = np.tile(raw, (len(era.E), 1))
    assert list(era.Xo[0]) == [raw[j] * d for j, (_, d) in enumerate(SECTION5_DIRECTIONS)]


def test_the_registered_constants():
    assert fit.SCREEN == 0.58 and fit.AGAINST == 0.50 and fit.MAX_SUBSET == 5
    assert fit.PLATEAU_THRESHOLDS == (0.56, 0.60)
    assert fit.N_DECIDES == 6 and fit.NS == (4, 6, 8)
    assert fit.cutoff_rank(6) == 24 and fit.cutoff_rank(4) == 16 and fit.cutoff_rank(8) == 32          # the (4 x N)-th highest reference score
    assert fit.POOL_SESSIONS == 20 and fit.POOL_FLOOR == 30 and fit.MISSING_PCT == 0.5
    assert fit.BAR_PASS == 5 and fit.BAR_FAIL == 1 and fit.HOLDOUT_N == 66
    assert fit.PERMS == 200 and fit.SEED == 702 and fit.GUARD2_BAND == (0.48, 0.52) and fit.GUARD3_MAX == 1.5
    assert fit.LOOKAHEAD_N == 500 and fit.CUT_B == "2024-12-31" and fit.FIT_LAST_E == "2020-12-31"


def test_the_engine_defaults_are_the_registered_pool_and_floor():
    import inspect
    sig = inspect.signature(fit.PoolEngine.__init__).parameters
    assert sig["pool_sessions"].default == 20 and sig["floor"].default == 30
    assert inspect.signature(fit.score_at_nights).parameters["floor"].default == 30


@pytest.mark.parametrize("c,need", [(1, 4), (3, 4), (4, 4), (5, 4), (6, 5), (8, 6), (12, 9), (16, 12), (20, 15), (66, 50)])
def test_plateau_need_is_max4_ceil_075c(c, need):
    a = aucs_of(rs_best=0.70, wk_ratio=0.65)
    assert fit.plateau(a, ["rs_best", "wk_ratio"], lambda s: 0, c)["need"] == need
    # one-sided and inclusive: a neighbour at exactly `need` holds, at need - 1 fails, above never fails
    assert fit.plateau(a, ["rs_best", "wk_ratio"], lambda s: need, c)["verdict"] == "HOLDS"
    assert fit.plateau(a, ["rs_best", "wk_ratio"], lambda s: need - 1, c)["verdict"] == "FAILS"


def test_screen_is_inclusive_at_exactly_0_58():
    assert fit.subset_rule(aucs_of(rs_best=0.58))[0] == ["rs_best"]
    assert fit.subset_rule(aucs_of(rs_best=0.5799999999))[0] == []
    # an AUC the module itself computes to exactly 0.58 (29 of 50 same-day negatives below the positive) counts too
    x = np.r_[np.arange(50, dtype=float), [28.5]]
    pos = np.r_[np.zeros(50, dtype=bool), [True]]
    r = fit.within_day_auc(x, np.zeros(51, dtype=int), pos, ~pos)[0]
    assert r["auc"] == 0.58
    assert fit.subset_rule({k: (r["auc"] if k == "rs_best" else 0.52) for k in fit.FEATURE_KEYS})[0] == ["rs_best"]


def test_plateau_thresholds_are_inclusive_at_0_56_and_0_60():
    a = aucs_of(rs_best=0.60, wk_ratio=0.58, retrace=0.56, vol_dry5=0.5599999)
    pl = fit.plateau(a, ["rs_best", "wk_ratio"], lambda s: 99, 10)
    by = {r["name"]: r["subset"] for r in pl["neighbours"]}
    assert by["screen 0.56"] == ["rs_best", "wk_ratio", "retrace"]                      # 0.56 in, 0.5599999 out
    assert by["screen 0.60"] == ["rs_best"]                                              # 0.60 in, 0.58 out


def test_the_bar_is_pass_at_5_and_fail_at_1():
    assert fit.bar_verdict(False, 5, "HOLDS", 1)[0] == "PASS" and fit.bar_verdict(False, 4, "HOLDS", 1)[0] == "CAN'T TELL"
    assert fit.bar_verdict(False, 1, "HOLDS", 1)[0] == "FAIL" and fit.bar_verdict(False, 2, "HOLDS", 1)[0] == "CAN'T TELL"


def test_pool_of_exactly_thirty_counts_and_twenty_nine_does_not():
    X, E, tk = stream_one_feature(np.r_[np.arange(1, 31, dtype=float), [np.nan] * 10], [100.0])        # 30 non-missing of 40 members
    eng = fit.PoolEngine(X, E, tk, np.array(["W"] * len(E)))
    i = int(np.flatnonzero(tk == "D000")[0])
    assert eng.own[i, 0] == 1.0                                                          # |S| = 30 >= 30: the fill is rated (all 30 below it)
    X29, E29, tk29 = stream_one_feature(np.r_[np.arange(1, 30, dtype=float), [np.nan] * 11], [100.0])   # 29 non-missing
    eng29 = fit.PoolEngine(X29, E29, tk29, np.array(["W"] * len(E29)))
    assert math.isnan(eng29.own[int(np.flatnonzero(tk29 == "D000")[0]), 0])


def test_members_need_thirty_values_in_the_pool_minus_themselves():
    # 30 non-missing: a member sees 29 -> unrated reference (NaN); 31 non-missing: a member sees 30 -> rated
    for n_ok, rated in ((30, False), (31, True)):
        X, E, tk = stream_one_feature(np.r_[np.arange(1, n_ok + 1, dtype=float), [np.nan] * (40 - n_ok)], [100.0])
        eng = fit.PoolEngine(X, E, tk, np.array(["W"] * len(E)))
        a, b, ref = eng.days[-1]
        assert ref.shape[0] == 40 and bool((~np.isnan(ref[:, 0])).any()) == rated, n_ok
        ok = ~np.isnan(X[:40, 0])                                                         # the 40 pool rows come first (E 5 < 10)
        assert bool((~np.isnan(ref[ok, 0])).all()) == rated and np.isnan(ref[~ok, 0]).all()


@pytest.mark.parametrize("pool_day,pool_n", [(9, 0), (10, 40), (29, 40), (30, 0), (31, 0)])
def test_pool_window_is_e_minus_20_to_e_minus_1(pool_day, pool_n):
    # the day is E = 30: E-21 = 9 is OUT, E-20 = 10 and E-1 = 29 are IN, the same day (30) and the next (31) are OUT
    X, E, tk = stream_one_feature(np.arange(1, 41, dtype=float), [50.0], pool_day=pool_day, day=30)
    eng = fit.PoolEngine(X, E, tk, np.array(["W"] * len(E)), floor=1)
    i = int(np.flatnonzero(tk == "D000")[0])
    assert int(eng.pool_n[i]) == pool_n


def test_pool_window_members_set_the_percentile_not_the_rows_outside_it():
    # in-window members 1..40 on E-20 and E-1; rows at E-21 and the same day carry a huge value and must not change the fill's percentile
    n = 20
    vals = [(9, 1e9, "O"), (10, 1.0, "P"), (29, 2.0, "Q"), (30, 1e9, "S")]
    rows = [(e, f"{tag}{i:03d}", v) for e, v, tag in vals for i in range(n)]
    rows.append((30, "ZFILL", 1.5))
    rows.sort(key=lambda r: (r[0], r[1]))
    E = np.array([r[0] for r in rows])
    tk = np.array([r[1] for r in rows])
    X = np.array([[r[2]] for r in rows])
    eng = fit.PoolEngine(X, E, tk, np.array(["W"] * len(E)), floor=1)
    i = int(np.flatnonzero(tk == "ZFILL")[0])
    assert eng.pool_n[i] == 2 * n and eng.own[i, 0] == pytest.approx(0.5)                # 20 below (the 1.0s), 20 above (the 2.0s)


def test_readiness_pool_is_d_minus_19_to_d():
    d = 50
    # stream rows at d-20 (OUT, huge), d-19 (IN, 1), d (IN, 2), d+1 (OUT, huge); the night's value 5 beats both members -> percentile 1.0
    E = np.array([d - 20] * 3 + [d - 19] * 2 + [d] * 2 + [d + 1] * 3, dtype=np.int64)
    X = np.array([[1000.0]] * 3 + [[1.0]] * 2 + [[2.0]] * 2 + [[3000.0]] * 3)
    sc, pn = fit.score_at_nights(X, E, np.array([[5.0]]), np.array([d]), [0], floor=1)
    assert int(pn[0]) == 4 and sc[0] == pytest.approx(1.0)
    sc2, pn2 = fit.score_at_nights(X, E, np.array([[5.0]]), np.array([d - 1]), [0], floor=1)           # d-1: window [d-20, d-1] = the 3 + 2 rows
    assert int(pn2[0]) == 5


def test_cap_week_is_the_iso_week_sunday_belongs_to_the_week_before():
    iso = fit.ap.iso_week
    assert iso("2021-01-03") == "2020-W53" and iso("2021-01-04") == "2021-W01"           # Sunday vs Monday across a year edge
    assert iso("2021-03-07") == iso("2021-03-01") != iso("2021-03-08")                    # Mon..Sun is one week
    dates = ["2020-12-31"] * 3 + ["2021-01-01"] * 2 + ["2021-01-03"] * 2 + ["2021-01-04"]
    week = np.array([iso(x) for x in dates])
    f = fit.apply_cap(np.full(8, 0.9), np.full(8, 0.5), week, 6)
    assert list(f) == ["TAKE"] * 6 + ["CAPPED"] + ["TAKE"]                               # 7 in the week -> the 7th CAPPED; Monday resets


def _csv(path, rows):
    path.write_text("\n".join(",".join(str(x) for x in r) for r in rows) + "\n")


def test_era_b_export_row_dated_2025_is_dropped_at_read_and_counted(tmp_path):
    rows = []
    for d in ("2024-12-30", "2024-12-31", "2025-01-02"):
        rows += [("SPY", d, 300, 301, 299, 300.5, 1e6), ("TST", d, 50, 51, 49, 50.5, 1e5)]
    p = tmp_path / "export_B.csv"
    _csv(p, rows)
    ex, n_after = fit.wl_read_export("export_B", {"TST", "SPY"}, fit.CUT_B, path=str(p))
    assert n_after == 2 and ex.cal == ["2024-12-30", "2024-12-31"]                         # the SPY and the TST row of 2025-01-02
    assert len(ex.rows("TST")[0]) == 2 and max(ex.cal) <= fit.CUT_B
    ex_a, n_a = fit.wl_read_export("export_A", {"TST", "SPY"}, None, path=str(p))          # era A has no cut: the same rows stay
    assert n_a == 0 and ex_a.cal[-1] == "2025-01-02"


def test_a_row_dated_after_the_cut_that_slipped_through_trips_the_assert(tmp_path, monkeypatch):
    df = pd.DataFrame({"date": ["2024-12-31", "2025-01-02"]})
    with pytest.raises(AssertionError, match="survived the read"):
        fit.assert_none_after(df, "date", fit.CUT_B, "x")
    fit.assert_none_after(df.iloc[:1], "date", fit.CUT_B, "x")
    fit.assert_none_after(df.iloc[:0], "date", fit.CUT_B, "x")
    # and the export path: if the filter let a 2025 row through, the read itself raises
    p = tmp_path / "export_B.csv"
    _csv(p, [("SPY", "2024-12-31", 300, 301, 299, 300.5, 1e6)])
    real_concat = pd.concat
    extra = pd.DataFrame({"ticker": ["SPY"], "date": ["2025-01-02"], "h": [1.0], "l": [1.0], "c": [1.0], "v": [1.0]})
    monkeypatch.setattr(fit.pd, "concat", lambda parts, **kw: real_concat(list(parts) + [extra], **kw))
    with pytest.raises(AssertionError, match="survived the read"):
        fit.wl_read_export("export_B", {"SPY"}, fit.CUT_B, path=str(p))


def test_era_b_flags_dated_2025_are_dropped_and_counted(tmp_path):
    p = tmp_path / "B_flags.tsv"
    pd.DataFrame([dict(klass=fit.DISC_KLASS, ticker="AAA", date="2024-12-31"), dict(klass=fit.DISC_KLASS, ticker="BBB", date="2025-01-02"),
                  dict(klass="other_klass", ticker="CCC", date="2023-05-05")]).to_csv(p, sep="\t", index=False)
    df, dropped = fit.read_flags("flags_B", fit.CUT_B, path=str(p))
    assert list(df["ticker"]) == ["AAA"] and dropped["dated_after_cut"] == 1
    df_a, d_a = fit.read_flags("flags_A", None, path=str(p))                               # no cut: both DISCONTINUOUS rows stay
    assert list(df_a["ticker"]) == ["AAA", "BBB"] and d_a["dated_after_cut"] == 0


def test_era_b_candidates_and_watch_rows_after_the_cut_are_dropped_and_counted(tmp_path):
    cols = list(fit.WHITELIST["cand_B"])
    base = {c: "" for c in cols}
    base.update(K="tl", split="discovery", base_len=10.0, adr20=0.05, pivot=10.0, C1="0", retrigger="0", retrigger_chain="0")

    def row(**kw):
        r = dict(base)
        r.update(kw)
        return r
    rows = [row(ticker="OK1", D="2024-12-30", E="2024-12-31"),
            row(ticker="LATE", D="2024-12-31", E="2025-01-02"),                              # E after the cut
            row(ticker="HOLD", D="2024-06-03", E="2024-06-04", split="holdout"),             # not the discovery split
            row(ticker="COM", D="2024-06-03", E="2024-06-04", K="com")]                      # discovery but not a tl row
    p = tmp_path / "candidates.tsv"
    pd.DataFrame(rows, columns=cols).to_csv(p, sep="\t", index=False)
    df, dropped = fit.wl_read_tsv("cand_B", cols, fit.CAND_STR, path=str(p), keep=fit.era_b_cand_keep)
    assert list(df["ticker"]) == ["OK1"] and dropped["dated_after_cut"] == 1 and dropped["not_discovery"] == 1
    wcols = list(fit.WHITELIST["watch_B"])
    wrows = [dict({c: "" for c in wcols}, ticker=t, watch_date=d, split=sp) for t, d, sp in
             (("OK", "2024-12-31", "discovery"), ("LATE", "2025-01-02", "discovery"), ("HOLD", "2024-05-01", "holdout"))]
    wp = tmp_path / "watch.tsv"
    pd.DataFrame(wrows, columns=wcols).to_csv(wp, sep="\t", index=False)
    wdf, wd = fit.wl_read_tsv("watch_B", wcols, fit.WATCH_STR, path=str(wp), keep=fit.era_b_watch_keep)
    assert list(wdf["ticker"]) == ["OK"] and wd["dropped_after_cut_or_holdout"] == 2


# ── the population assert: every EXPECT key must be measured ─────────────────────────────────
def test_check_expect_fails_on_a_missing_key_and_on_a_wrong_value():
    out = []
    assert fit.check_expect({"a": 1, "b": 0}, {"a": 1, "b": 0}, out.append) == [] and out == []
    bad = fit.check_expect({"a": 1}, {"a": 1, "b": 0}, out.append)                          # b registered but never measured
    assert bad and "b: NOT MEASURED" in bad[0] and "POPULATION ASSERT FAILED" in out[-1]
    assert fit.check_expect({"a": 2, "b": 0}, {"a": 1, "b": 0}, out.append) == ["a: 2 (registered 1)"]
    assert fit.check_expect({"a": 1, "b": 0, "extra": 7}, {"a": 1, "b": 0}, out.append) == []   # an unregistered extra measurement is only printed


def test_the_2022_01_03_rows_are_asserted_not_only_printed():
    assert fit.EXPECT["pos_hold_2022"] == 0 and fit.EXPECT["neg_hold_2022"] == 0
    got = dict(fit.EXPECT)
    assert fit.check_expect(got, fit.EXPECT, lambda m: None) == []
    got["pos_hold_2022"] = 1
    assert fit.check_expect(got, fit.EXPECT, lambda m: None) == ["pos_hold_2022: 1 (registered 0)"]
    del got["pos_hold_2022"]
    assert any("pos_hold_2022: NOT MEASURED" in b for b in fit.check_expect(got, fit.EXPECT, lambda m: None))


# ── the doc-body pin: an edit to the doc after the freeze makes the real run exit 2 ──────────────
def test_doc_body_sha_is_the_bytes_above_the_marker(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_bytes(b"body one\r\nbody two\n<!-- FREEZE -->\n- tail\n")
    assert fit.doc_body_sha(str(doc)) == hashlib.sha256(b"body one\r\nbody two\n").hexdigest()
    doc.write_bytes(b"body one\r\nbody two\n<!-- FREEZE -->\n- a different tail\n")          # the record below the marker is not part of the hash
    assert fit.doc_body_sha(str(doc)) == hashlib.sha256(b"body one\r\nbody two\n").hexdigest()


def test_freeze_check_refuses_a_doc_edited_after_the_pin(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("registration body\n<!-- FREEZE -->\n")
    pinned = fit.doc_body_sha(str(doc))
    doc.write_text(f"registration body\n<!-- FREEZE -->\n- doc_body: {pinned}\n")
    assert fit.freeze_missing(str(doc), {"doc_body": fit.doc_body_sha(str(doc))}) == []
    doc.write_text(f"registration body, edited\n<!-- FREEZE -->\n- doc_body: {pinned}\n")        # one word changed above the marker
    assert fit.freeze_missing(str(doc), {"doc_body": fit.doc_body_sha(str(doc))}) == ["doc_body"]


class _Reached(Exception):
    pass


@pytest.fixture
def main_sandbox(tmp_path, monkeypatch):
    """`main` with every output path in tmp, the file hashes faked to the pinned values, and the first label read replaced by a sentinel."""
    doc = tmp_path / "doc.md"
    monkeypatch.setattr(fit, "DOC", str(doc))
    for nm in ("PRINTOUT", "DRY_PRINTOUT", "STOPPED", "TAKE_TSV"):
        monkeypatch.setattr(fit, nm, str(tmp_path / f"out_{nm}"))
    by_path = {fit.FILES[n]: v for n, v in fit.PINNED.items() if n in fit.FILES}
    by_path[fit.JOIN_SCRIPT] = fit.PINNED["join_script"]
    monkeypatch.setattr(fit, "sha", lambda path: by_path.get(path, hashlib.sha256(path.encode()).hexdigest()))

    def reached(*a, **kw):
        raise _Reached()
    monkeypatch.setattr(fit, "wl_read_tsv", reached)
    return doc


def _write_doc_with_every_pin(doc, body: str) -> None:
    doc.write_text(body + "<!-- FREEZE -->\n")
    tail = "".join(f"- {k}: {v}\n" for k, v in fit.pins().items())
    doc.write_text(body + "<!-- FREEZE -->\n## Freeze record\n" + tail)


def test_real_run_exits_2_when_the_doc_body_was_edited_after_the_freeze(main_sandbox, capsys):
    doc = main_sandbox
    _write_doc_with_every_pin(doc, "registration body\n")
    with pytest.raises(_Reached):                                                           # every pin under the marker -> past the refusal
        fit.main([])
    capsys.readouterr()
    doc.write_text(doc.read_text().replace("registration body", "registration body, edited", 1))   # the body above the marker changes
    assert fit.main([]) == 2                                                               # refused BEFORE any label file is read
    out = capsys.readouterr()
    assert "NOT YET under the FREEZE marker: doc_body" in out.out and "REFUSED" in out.err


def test_dry_run_prints_the_live_doc_body_hash_as_the_value_to_pin(main_sandbox, capsys):
    doc = main_sandbox
    doc.write_text("registration body\n<!-- FREEZE -->\n")
    with pytest.raises(_Reached):
        fit.main(["--dry-run"])
    out = capsys.readouterr().out
    assert f"- doc_body: {fit.doc_body_sha(str(doc))}" in out and "the value the freeze commit must pin" in out
    assert "NOT YET under the FREEZE marker" in out and "doc_body" in out.split("NOT YET under the FREEZE marker", 1)[1].splitlines()[0]
