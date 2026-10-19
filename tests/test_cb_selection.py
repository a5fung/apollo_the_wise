"""#702 selection test - `scripts/probes/_cb_backtest/selection_pre.py` (the build: picks, controls, population) and `selection_read.py` (the read).

SYNTHETIC data only: the read has never been run on the real picks (the build card must not compute an outcome), so what is pinned here is its
arithmetic on numbers worked out by hand, plus the build's pick / control logic on a toy tape. No file of /Users/alvinfung/apollo_data is read.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from scripts.probes._cb_backtest import selection_pre as sp
from scripts.probes._cb_backtest import selection_read as sr

NAN = float("nan")


# ═══ selection_read: one breakout's forward numbers ═══════════════════════════════════════════════
class TestItemMetrics:
    def _ramp(self, n=40):
        ci = np.arange(n)
        close = 10.0 + 0.1 * ci
        return ci, close + 0.5, close                                    # high = close + 0.5

    def test_the_numbers_are_the_registered_formulas(self):
        ci, h, c = self._ramp()
        m = sr.item_metrics(ci, h, c, e_ci=5, level=10.0, adr20=0.05, cal_last_ci=100)       # unit = level x ADR20 = 0.5
        assert m["fwd20"] == pytest.approx((c[25] - 10.0) / 0.5) == pytest.approx(5.0)          # close of E+20
        assert m["mfe10"] == pytest.approx((h[15] - 10.0) / 0.5) == pytest.approx(4.0)          # highest high of E..E+10 (a ramp: the last)
        assert m["mfe20"] == pytest.approx((h[25] - 10.0) / 0.5) == pytest.approx(6.0)
        assert m["reach5"] == 1.0 and (m["st10"], m["st20"]) == ("ok", "ok")

    def test_the_window_includes_the_breakout_day_itself(self):
        ci, h, c = self._ramp()
        h = h.copy()
        h[5] = 99.0                                                      # the breakout day's own high is the best excursion
        m = sr.item_metrics(ci, h, c, 5, 10.0, 0.05, 100)
        assert m["mfe10"] == pytest.approx((99.0 - 10.0) / 0.5) and m["mfe20"] == m["mfe10"]

    def test_reach5_is_the_share_flag_at_exactly_five_adr(self):
        ci = np.arange(30)
        c = np.full(30, 9.0)
        for best, want in ((18.0, 1.0), (17.99, 0.0)):                   # level 8, ADR20 0.25 -> unit 2: a high of 18 is exactly +5 ADR
            h = np.full(30, 9.0)
            h[15] = best
            m = sr.item_metrics(ci, h, c, 5, 8.0, 0.25, 100)
            assert m["reach5"] == want
        assert m["mfe20"] == pytest.approx((17.99 - 8.0) / 2.0)

    def test_a_window_is_never_filled_in(self):
        ci, h, c = self._ramp()
        hole = np.delete(np.arange(40), 18)                              # session 18 missing: inside E+20 but not inside E+10
        m = sr.item_metrics(hole, h[hole], c[hole], 5, 10.0, 0.05, 100)
        assert (m["st10"], m["st20"]) == ("ok", "hole") and np.isfinite(m["mfe10"])
        assert all(np.isnan(m[k]) for k in ("fwd20", "mfe20", "reach5"))
        short = np.arange(20)                                            # the ticker's last bar: a delisting / data end before E+20
        m = sr.item_metrics(short, h[:20], c[:20], 5, 10.0, 0.05, 100)
        assert (m["st10"], m["st20"]) == ("ok", "ended") and np.isnan(m["fwd20"])
        m = sr.item_metrics(ci, h, c, 5, 10.0, 0.05, cal_last_ci=20)     # E+20 is past the last session of the data
        assert (m["st10"], m["st20"]) == ("ok", "immature")
        assert sr.item_metrics(ci, h, c, 5, 0.0, 0.05, 100)["st20"] == "bad_level"
        assert sr.item_metrics(ci, h, c, 999, 10.0, 0.05, 1000)["st20"] == "no_E_bar"


# ═══ selection_read: the difference, its interval, the verdict ════════════════════════════════════
class TestMatchedDiff:
    def test_a_constant_gap_in_every_month_has_a_degenerate_interval(self):
        months = np.repeat(["2020-01", "2020-02", "2020-03", "2020-04"], 10)
        eff = np.repeat([0.0, 2.0, -1.0, 5.0], 10)
        d = sr.matched_diff(1.0 + eff, months, eff, key="k")
        assert (d["n"], d["n_excluded"]) == (40, 0)
        assert d["diff"] == pytest.approx(1.0) and d["lo"] == pytest.approx(1.0) and d["hi"] == pytest.approx(1.0)
        assert d["pick_mean"] - d["ctrl_mean"] == pytest.approx(1.0)

    def test_resampling_the_controls_widens_the_interval_and_keeps_the_estimate(self):
        months = np.array(["A"] * 6)                                     # ONE month: the pick-side-only draws are all the same draw
        x = np.ones(6)
        cv, cg = np.array([0.0, 2.0, 4.0, 6.0, 8.0, 10.0]), np.array(["A"] * 6)
        m = sr.matched_means(cv, cg, months)                             # 5.0 for every pick
        fixed = sr.matched_diff(x, months, m, key="k")
        both = sr.matched_diff(x, months, m, key="k", ctrl=(cv, cg, months))
        assert fixed["lo"] == fixed["hi"] == pytest.approx(-4.0)         # control mean treated as known: no spread at all
        assert both["diff"] == pytest.approx(fixed["diff"]) and both["n"] == fixed["n"]
        assert both["lo"] < -4.0 < both["hi"]                            # the controls' own sampling noise is now inside the interval
        flat = sr.matched_diff(x, months, m * 0 + 1.0, key="k", ctrl=(np.ones(6), cg, months))
        assert flat["lo"] == flat["hi"] == pytest.approx(0.0)            # identical controls cannot add spread

    def test_the_controls_are_redrawn_inside_their_own_group_only(self):
        picks_t = np.array(["T1", "T1", "T2", "T2"])
        months = np.array(["A", "A", "B", "B"])
        cv, cg = np.array([10.0, 10.0, 20.0, 20.0]), np.array(["T1", "T1", "T2", "T2"])      # constant inside each ticker, different across
        m = sr.matched_means(cv, cg, picks_t)
        d = sr.matched_diff(np.array([11.0, 11.0, 19.0, 19.0]), months, m, key="k", ctrl=(cv, cg, picks_t))
        assert d["diff"] == pytest.approx(0.0) and (d["lo"], d["hi"]) == (-1.0, 1.0)     # T1's controls never stand in for T2's: A -> +1, B -> -1

    def test_the_bootstrap_resamples_whole_months(self):
        months = np.array(["A"] * 5 + ["B"] * 5)
        x = np.array([1.0] * 5 + [-1.0] * 5)
        d = sr.matched_diff(x, months, np.zeros(10), key="k")
        assert d["diff"] == pytest.approx(0.0)
        assert (d["lo"], d["hi"]) == (-1.0, 1.0)                         # draws are AA / AB / BB: means +1 / 0 / -1, a quarter of the draws each end

    def test_an_unscored_pick_or_control_is_excluded_and_counted(self):
        x = np.array([1.0, 2.0, NAN, 4.0])
        m = np.array([0.0, NAN, 0.0, 1.0])
        d = sr.matched_diff(x, np.array(["A", "A", "B", "B"]), m, key="k")
        assert (d["n"], d["n_excluded"]) == (2, 2) and d["diff"] == pytest.approx((1.0 + 3.0) / 2)
        assert sr.matched_diff([NAN], ["A"], [1.0], key="k")["n"] == 0

    def test_each_comparison_has_its_own_fixed_stream(self):
        rng = np.random.default_rng(3)
        months = np.repeat(np.arange(12), 5).astype(str)
        x, m = rng.normal(0.3, 1.0, 60), rng.normal(0.0, 1.0, 60)
        a1, a2 = sr.matched_diff(x, months, m, key="tl|fwd20|a"), sr.matched_diff(x, months, m, key="tl|fwd20|a")
        b = sr.matched_diff(x, months, m, key="tl|fwd20|b")
        assert a1 == a2 and a1["diff"] == b["diff"] and (a1["lo"], a1["hi"]) != (b["lo"], b["hi"])

    def test_matched_means_follow_the_group_and_skip_unscored_controls(self):
        got = sr.matched_means([1.0, 3.0, NAN, 10.0], ["A", "A", "A", "B"], ["A", "B", "C"])
        assert got[0] == 2.0 and got[1] == 10.0 and np.isnan(got[2])     # the NaN control does not count; a group with no control is NaN


def test_the_verdict_is_the_registered_reading():
    assert sr.verdict(30, 0.01, 0.9) == "HIS SELECTION ADDS EDGE"
    assert sr.verdict(30, -0.9, -0.01) == "HIS PICKS DID WORSE"
    assert sr.verdict(30, -0.1, 0.2) == "CAN'T TELL"
    assert sr.verdict(29, 0.5, 0.9) == "CAN'T TELL"                       # fewer than 30 picks: whatever the interval says
    assert sr.verdict(200, NAN, NAN) == "CAN'T TELL"
    assert sr.verdict(30, 0.0, 0.5) == "CAN'T TELL" and sr.verdict(30, -0.5, 0.0) == "CAN'T TELL"      # the bar is strict


# ═══ selection_read: the whole comparison on synthetic tapes ═════════════════════════════════════
def _tape(slope, base=10.0, n=200):
    ci = np.arange(n)
    c = base + slope * ci
    return ci, c, c


def _frames(n_per_month=5, months=8, pick_slope=0.30, ctrl_slope=0.05):
    bars, picks, ca, cb = {}, [], [], []
    for mo in range(months):
        for j in range(n_per_month):
            e_ci = 20 + 12 * mo + j
            t = f"P{mo}_{j}"
            bars[t] = _tape(pick_slope)
            picks.append(dict(ticker=t, E_ci=e_ci, month=f"2020-{mo + 1:02d}", pivot=10.0 + pick_slope * e_ci, adr20=0.05, frame_verified=int(j == 0)))
            for q in range(2):
                tc = f"C{mo}_{j}_{q}"
                bars[tc] = _tape(ctrl_slope)
                ca.append(dict(ticker=tc, E_ci=e_ci + q, month=f"2020-{mo + 1:02d}", pivot=10.0 + ctrl_slope * (e_ci + q), adr20=0.05))
            cb.append(dict(ticker=t, E_ci=e_ci + 3, month=f"2020-{mo + 1:02d}", pivot=10.0 + pick_slope * (e_ci + 3), adr20=0.05))
    return bars, pd.DataFrame(picks), pd.DataFrame(ca), pd.DataFrame(cb)


class TestCompareLevel:
    def test_better_picks_read_as_edge_and_the_frame_subset_is_too_small_to_say(self):
        bars, picks, ca, cb = _frames()
        # control (b) rows are other bases of the pick's own ticker: their tape is the pick ticker's (slope 0.30), so (b) must read ~0
        get = lambda t: bars.get(t)                                       # noqa: E731
        r = sr.compare_level(picks, ca, cb, "tl", get, cal_last_ci=500)
        by = {(x["metric"], x["comparison"]): x for x in r["rows"]}
        a = by[("fwd20", "picks_vs_a")]
        assert a["n"] == 40 and a["diff"] > 0 and a["lo"] > 0 and a["verdict"] == "HIS SELECTION ADDS EDGE"
        assert a["pick_mean"] == pytest.approx(np.mean([0.30 * 20 / (0.05 * lv) for lv in picks["pivot"]]))
        f = by[("fwd20", "frame_vs_a")]
        assert f["n"] == 8 and f["verdict"] == "CAN'T TELL"                # the frame-verified subset: 8 picks < 30
        b = by[("fwd20", "picks_vs_b")]
        assert b["n"] == 40 and abs(b["diff"]) < abs(a["diff"])            # the pick's own ticker is the better comparison here
        assert 0 < by[("reach5", "picks_vs_a")]["diff"] <= 1.0           # share points: more of the picks reach +5 ADR
        assert r["status"]["picks"] == {"ok": 40}

    def test_unreachable_windows_are_excluded_not_filled(self):
        bars, picks, ca, cb = _frames(months=2)
        late = ca.iloc[:2].copy()
        late["E_ci"] = 190                                                # E+20 = 210 is past the last session
        ca2 = pd.concat([ca, late], ignore_index=True)
        r = sr.compare_level(picks, ca2, cb, "tl", lambda t: bars.get(t), cal_last_ci=200)
        assert r["status"]["control_a"].get("immature") == 2
        row = next(x for x in r["rows"] if x["metric"] == "fwd20" and x["comparison"] == "picks_vs_a")
        assert row["n_ctrl"] == len(ca2) and row["n_ctrl_scored"] == len(ca2) - 2

    def test_make_bars_serves_the_runners_export_by_calendar_index(self, tmp_path):
        import gzip
        days = [dt.date(2020, 1, 6) + dt.timedelta(days=k) for k in range(8)]
        days = [d for d in days if d.weekday() < 5]
        rows = [f"{t},{d.isoformat()},{p},{p + 1},{p - 1},{p},1000" for t, base in (("SPY", 100.0), ("XYZ", 20.0))
                for d, p in zip(days, [base + k for k in range(len(days))]) if not (t == "XYZ" and d == days[2])]
        with gzip.open(tmp_path / "daily_closes_all.csv.gz", "wt") as f:
            f.write("\n".join(rows) + "\n")
        bars, last = sr.make_bars(tmp_path)
        ci, h, c = bars("XYZ")
        assert last == len(days) - 1 and ci.tolist() == [0, 1, 3, 4, 5] and h[0] == 21.0 and c[2] == 23.0     # the missing session stays a hole
        assert bars("NOPE") is None

    def test_run_read_writes_the_result_files(self, tmp_path):
        bars, picks, ca, cb = _frames(months=3)
        out = tmp_path / "out"
        out.mkdir()
        for name, d in (("selection_picks", picks.assign(symbol=picks["ticker"], level="tl")),
                        ("selection_controls_a", ca.assign(level="tl")), ("selection_controls_b", cb.assign(level="tl"))):
            d.to_csv(out / f"{name}.tsv", sep="\t", index=False)
        res = sr.run_read(tmp_path, bars=lambda t: bars.get(t), cal_last_ci=500, levels=("tl",))
        txt = (out / "selection_result.txt").read_text()
        assert "VERDICT" in txt and "LEVEL tl" in txt and txt == res["text"]
        tsv = pd.read_csv(out / "selection_result.tsv", sep="\t", keep_default_na=False)
        assert set(tsv["metric"]) == set(sr.METRICS) and set(tsv["comparison"]) == {"picks_vs_a", "picks_vs_b", "frame_vs_a"}
        # 3 months x 5 picks = 15 scored picks < 30: whatever the interval says, the verdict is CAN'T TELL
        assert tsv[(tsv.metric == "fwd20") & (tsv.comparison == "picks_vs_a")].iloc[0]["verdict"] == "CAN'T TELL"


# ═══ selection_pre: picks, controls, loss reasons on a toy tape ═══════════════════════════════════
def _sessions(n=60):
    out, d = [], dt.date(2020, 1, 6)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


S = _sessions()
ISO = [d.isoformat() for d in S]
WIN = (S[10], S[50])


def _base(sym, pole_cis, watch_cis, e_ci=None, levels=("tl", "com"), no_tl=False, extra_first=None):
    """Watch rows for each (pole, night) and, if `e_ci`, the first-C0 breakout row of the chain base at every level."""
    watch, cands = [], []
    for pc in pole_cis:
        for ci in watch_cis:
            watch.append(dict(ticker=sym, watch_date=ISO[ci], ci=ci, pole_date=ISO[pc], pole_ci=pc,
                              pivot_tl=NAN if no_tl else 10.0, pivot_com=9.5))
    if e_ci is not None:
        for k in levels:
            if k == "tl" and no_tl:
                continue
            cands.append(dict(ticker=sym, D=ISO[e_ci - 1], E=ISO[e_ci], K=k, pole_date=ISO[pole_cis[0]], pole_ci=pole_cis[0],
                              base_id=f"{sym}|{ISO[pole_cis[0]]}", retrigger_chain=0, first_chain_C0=1, pivot=10.0, adr20=0.05))
            cands.append(dict(ticker=sym, D=ISO[e_ci + 4], E=ISO[e_ci + 5], K=k, pole_date=ISO[pole_cis[0]], pole_ci=pole_cis[0],
                              base_id=f"{sym}|{ISO[pole_cis[0]]}", retrigger_chain=1, first_chain_C0=0, pivot=10.0, adr20=0.05))
    return watch, cands


def _toy():
    watch, cands = [], []

    def add(*args, **kw):
        w, c = _base(*args, **kw)
        watch.extend(w)
        cands.extend(c)

    add("AAA", [20, 22], [24, 25, 26], e_ci=33)                           # two poles 2 sessions apart = ONE base; breaks out on session 33
    add("BBB", [20], [24, 25], e_ci=29)                                   # breaks out BEFORE the talk (session 31)
    add("CCC", [20], [24, 25])                                            # watched, lapsed, never broke out
    add("DDD", [20], [24, 50])                                            # still in place on the last scanned night (session 50)
    add("EEE", [20], [24, 25], e_ci=30, no_tl=True)                       # no night with a trendline; the com level breaks out
    add("GGG", [15], [20, 21], e_ci=25)                                   # an unrelated base, same month as AAA's break  -> control (a)
    add("HHH", [30], [34, 35], e_ci=45)                                   # an unrelated base in a later month          -> not in (a)
    add("AAA", [40], [42, 43], e_ci=52)                                   # ANOTHER base of AAA (later)               -> control (b)
    add("FFF", [], [])
    watch_df = pd.DataFrame(watch)
    cands_df = pd.DataFrame(cands)
    picks = pd.DataFrame([
        dict(symbol="AAA", pole_date=ISO[21], talk_date=ISO[31], ref_date_max=ISO[40], n_talks=2, spoken="AAA", ext_first_E="", ext_last_watch=ISO[26], bars_source="x"),
        dict(symbol="BBB", pole_date=ISO[20], talk_date=ISO[31], ref_date_max=ISO[31], n_talks=1, spoken="BBB", ext_first_E="", ext_last_watch=ISO[25], bars_source="x"),
        dict(symbol="CCC", pole_date=ISO[20], talk_date=ISO[31], ref_date_max=ISO[31], n_talks=1, spoken="CCC", ext_first_E="", ext_last_watch=ISO[25], bars_source="x"),
        dict(symbol="DDD", pole_date=ISO[20], talk_date=ISO[31], ref_date_max=ISO[31], n_talks=1, spoken="DDD", ext_first_E="", ext_last_watch=ISO[25], bars_source="x"),
        dict(symbol="EEE", pole_date=ISO[20], talk_date=ISO[27], ref_date_max=ISO[27], n_talks=1, spoken="EEE", ext_first_E="", ext_last_watch=ISO[25], bars_source="x"),
        dict(symbol="FFF", pole_date=ISO[20], talk_date=ISO[31], ref_date_max=ISO[31], n_talks=1, spoken="FFF", ext_first_E="", ext_last_watch=ISO[25], bars_source="x"),
        dict(symbol="AAA", pole_date=ISO[55], talk_date=ISO[55], ref_date_max=ISO[55], n_talks=1, spoken="AAA", ext_first_E="", ext_last_watch=ISO[55], bars_source="x"),
        dict(symbol="ZZZ", pole_date=ISO[20], talk_date=ISO[31], ref_date_max=ISO[31], n_talks=1, spoken="ZZZ", ext_first_E="", ext_last_watch=ISO[25], bars_source="x"),
    ])
    return watch_df, cands_df, picks


class TestBuildPopulation:
    def _run(self):
        watch, cands, picks = _toy()
        return sp.build_population(cands, watch, picks, S, frames={"AAA|" + ISO[21]}, symbols={"AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"},
                                   win=WIN)

    def test_every_pick_lands_in_exactly_one_outcome_per_level(self):
        pop = self._run()
        r = pop["rows"]
        why = {(x.symbol, x.pole_date, x.level): x.reason for x in r.itertuples()}
        assert why[("AAA", ISO[21], "tl")] == why[("AAA", ISO[21], "com")] == "matched"
        assert why[("BBB", ISO[20], "tl")] == "break_before_talk"
        assert why[("CCC", ISO[20], "tl")] == "never_broke_out"
        assert why[("DDD", ISO[20], "tl")] == "open_at_window_end"
        assert why[("EEE", ISO[20], "tl")] == "no_level_in_base" and why[("EEE", ISO[20], "com")] == "matched"      # com can match where tl cannot
        assert why[("FFF", ISO[20], "tl")] == "no_base_in_pre_run"
        assert why[("AAA", ISO[55], "tl")] == "talk_outside_window"
        assert why[("ZZZ", ISO[20], "tl")] == "symbol_not_in_export"
        assert len(r) == 2 * 8 and set(r["reason"]) <= set(sp.REASONS)

    def test_the_pick_takes_the_first_c0_break_of_the_chain_base_strictly_after_the_talk(self):
        r = self._run()["rows"]
        a = r[(r.symbol == "AAA") & (r.pole_date == ISO[21]) & (r.level == "tl")].iloc[0]
        assert a.base_id == f"AAA|{ISO[20]}" and a.E == ISO[33] and a.D == ISO[32] and int(a.E_ci) == 33     # not the retrigger on session 38
        assert a.E_after_last_talk == 0                                                                       # ... but it is on/before the LAST talk (session 40)
        assert a.n_candidate_bases == 1 and a.frame_verified == 1
        b = r[(r.symbol == "BBB") & (r.level == "tl")].iloc[0]
        assert b.E == ISO[29] and b.frame_verified == 0

    def test_controls_exclude_every_talked_base_and_follow_the_months_and_tickers(self):
        pop = self._run()
        ca, cb = pop["controls_a"]["tl"], pop["controls_b"]["tl"]
        # AAA's break is in February (session 33): the February first breaks that are not talked bases - GGG (25); BBB (29) and EEE are talked
        assert set(ca["base_id"]) == {f"GGG|{ISO[15]}"} and set(ca["month"]) == {"2020-02"}
        assert f"HHH|{ISO[30]}" not in set(ca["base_id"])                 # March: no pick breaks out in March
        assert set(cb["base_id"]) == {f"AAA|{ISO[40]}"}                   # the pick ticker's OTHER base; the picked base itself is not its own control
        assert pop["talked_bases"] >= {f"AAA|{ISO[20]}", f"BBB|{ISO[20]}", f"CCC|{ISO[20]}"}

    def test_the_candidate_table_is_read_through_a_column_whitelist(self, tmp_path):
        _, cands, _ = _toy()
        poisoned = cands.assign(high_E="BOOM", close_E="BOOM", open_E="BOOM", gap_open_pct="BOOM")
        p = tmp_path / "c.tsv"
        poisoned.to_csv(p, sep="\t", index=False)
        got = sp.load_candidates(p)
        assert list(got.columns) == sp.CAND_COLS                           # no price of the breakout day is ever parsed
        assert not [c for c in got.columns if c.endswith("_E") and c != "E"]
        w = pd.DataFrame(_toy()[0]).assign(close=1.0, high_tl="BOOM")
        wp = tmp_path / "w.tsv.gz"
        w.to_csv(wp, sep="\t", index=False)
        assert list(sp.load_watch(wp).columns) == sp.WATCH_COLS


def test_the_break_before_talk_bases_are_split_by_sessions_and_by_what_the_label_run_saw():
    lost = pd.DataFrame([
        dict(E_ci=30, talk_date=ISO[33], ext_first_E=""),                # 3 sessions before the talk, the label run saw no break
        dict(E_ci=30, talk_date=ISO[35], ext_first_E=ISO[40]),           # 5 sessions: still "<= 5", the label run saw a later break
        dict(E_ci=30, talk_date=ISO[40], ext_first_E=ISO[45]),           # 10 sessions
        dict(E_ci=10, talk_date=ISO[40], ext_first_E=""),                # 30 sessions
    ])
    rows = {ln.rsplit(None, 3)[0].strip(): ln.rsplit(None, 3)[1:] for ln in sp.break_gap_table(lost, S).splitlines()[1:]}
    assert rows == {"<= 5 sessions": ["1", "1", "2"], "6-20 sessions": ["0", "1", "1"], "> 20 sessions": ["1", "0", "1"]}


class TestCrosscheck:
    def test_the_label_runs_first_e_is_reproduced_or_explained(self):
        picks = pd.DataFrame([
            dict(symbol="A", pole_date="p", ext_first_E="2020-02-05", ext_last_watch="2020-01-20"),      # agree (earliest of two levels)
            dict(symbol="B", pole_date="p", ext_first_E="", ext_last_watch="2020-01-20"),                # both none
            dict(symbol="C", pole_date="p", ext_first_E="2022-02-01", ext_last_watch="2021-12-20"),      # past the window end: unseen
            dict(symbol="D", pole_date="p", ext_first_E="2020-03-01", ext_last_watch="2020-01-20"),      # a real disagreement
            dict(symbol="E", pole_date="p", ext_first_E="2017-02-01", ext_last_watch="2017-01-25"),      # before the window start
        ])
        x = pd.DataFrame([
            dict(ticker="A", pole_date="p", D="2020-02-04", E="2020-02-05"), dict(ticker="A", pole_date="p", D="2020-02-10", E="2020-02-11"),
            dict(ticker="A", pole_date="p", D="2020-01-10", E="2020-01-11"),                              # before the last watch night: ignored
            dict(ticker="D", pole_date="p", D="2020-02-20", E="2020-02-21"),
        ])
        got = sp.crosscheck_ext(picks, x, "2021-12-31")
        assert got["counts"] == {"agree": 1, "both_none": 1, "ext_break_past_window_end": 1, "differ": 1, "ext_break_before_window_start": 1}
        assert got["bad"] == [("D", "p", "2020-03-01", "2020-02-21")]

    def test_matched_picks_are_described_against_the_label_runs_first_e(self):
        res = pd.DataFrame([
            dict(level="tl", reason="matched", E="2020-02-05", ext_first_E="2020-02-05"),
            dict(level="tl", reason="matched", E="2020-02-05", ext_first_E=""),
            dict(level="tl", reason="matched", E="2020-02-05", ext_first_E="2020-02-03"),
            dict(level="tl", reason="matched", E="2020-02-05", ext_first_E="2020-02-09"),
            dict(level="tl", reason="break_before_talk", E="2020-02-05", ext_first_E="2020-02-05"),
            dict(level="com", reason="matched", E="2020-02-05", ext_first_E="2020-02-05"),
        ])
        assert sp.matched_vs_ext(res) == {"same": 1, "ext_blank": 1, "ext_earlier": 1, "ext_later": 1}
