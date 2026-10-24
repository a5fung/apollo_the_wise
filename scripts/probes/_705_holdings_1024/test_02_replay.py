"""Synthetic tests for 02_replay.py: the entries -> events reader, the same-day re-buy (F4), the panel clock vs the fill (F5), the
output guard, the calendar unification and the QQQ / SPY stitch, the market statistics (04_vs_market.py's formulas) on a curve of
known beta and alpha, his bar, the window curve, the undated open fill, the panel-exit trade, the era-B index shift, one
hand-computed account through the frozen `simulate`, and the freeze marker line.
No real data file is opened except the registration doc (its marker line)."""
import importlib.util
import os
import sys
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_705_holdings02", os.path.join(HERE, "02_replay.py"))
M = importlib.util.module_from_spec(spec)
sys.modules["_705_holdings02"] = M
spec.loader.exec_module(M)
rp, cb = M.rp, M.cb


def bars(n=200, start="2019-06-03", o=None, h=None, l=None, c=None):
    dates = [d.date() for d in pd.bdate_range(start, periods=n)]
    c = np.asarray(c if c is not None else 10.0 + 0.01 * np.arange(n), dtype=float)
    o = np.asarray(o if o is not None else c, dtype=float)
    h = np.asarray(h if h is not None else c * 1.01, dtype=float)
    l = np.asarray(l if l is not None else c * 0.99, dtype=float)
    return cb.daily_bars_from_arrays(dates, o, h, l, c, np.ones(n) * 1e6), np.arange(n, dtype=np.int64)


# ---- entries -> events -----------------------------------------------------------------------------------------------------------------
def entries_df():
    base = dict(sym="ABC", sym_a="ABC", has_bars="True", ever_candidate="True", era="A", pivot="", adr20="", base_id="", retrigger="0",
                ep_prev_close="", ep_gap_pct="", lo="2020-03-02", hi="2020-03-03", window_len="2", inverted="False", initial="False",
                flicker="False", exit_lo="2020-03-10", exit_hi="2020-03-10", still_held="False", decides="True", D="2020-03-02", E="2020-03-03")
    rows = [dict(base, eid="0", setup="breakout", pivot="10.5", adr20="0.04", base_id="ABC|x"),
            dict(base, eid="1", sym="XYZ", sym_a="XYZ", setup="EP", ep_prev_close="20", ep_gap_pct="12"),
            dict(base, eid="2", sym="UND", sym_a="UND", setup="undated", E="", D="", decides="False"),
            dict(base, eid="3", sym="INI", sym_a="INI", setup="initial", E="", D="", lo="", window_len="", initial="True", decides="False"),
            dict(base, eid="4", sym="GBTC", sym_a="GBTC", setup="undated", E="", D="", has_bars="False", decides="False"),
            dict(base, eid="5", sym="FB", sym_a="META", setup="breakout", pivot="200", adr20="0.03", E="2020-05-05", D="2020-05-04",
                 lo="2020-05-05", hi="2020-05-05", window_len="1", flicker="True"),
            dict(base, eid="6", sym="LATE", sym_a="LATE", setup="breakout", pivot="5", adr20="0.05", era="B", E="2022-09-01", D="2022-08-31",
                 lo="2022-09-01", hi="2022-09-01", window_len="1")]
    return pd.DataFrame(rows)


def test_load_events(tmp_path):
    p = tmp_path / "entries.tsv"
    entries_df().to_csv(p, sep="\t", index=False)
    evs, c = M.load_events(str(p))
    by = {e.eid: e for e in evs}
    assert c["entries"] == 7 and c["initial"] == 1 and c["non_initial"] == 6 and c["dated"] == 4 and c["undated"] == 2
    assert c["deciding"] == 4 and c["skipped_no_bars"] == 1 and c["in_window"] == 3 and c["in_window_breakout"] == 2 and c["in_window_EP"] == 1
    assert 3 not in by and 4 not in by
    assert by[0].pivot == 10.5 and by[0].adr20 == 0.04 and by[0].in_window and by[0].ticker == "ABC"
    assert by[1].pivot == 20.0 and by[1].adr20 is None and by[1].setup == "EP"
    assert by[2].setup == "undated" and by[2].E == "2020-03-02" and by[2].D == "" and not by[2].decides and not by[2].in_window
    assert by[5].ticker == "META" and by[5].flicker and by[5].in_window
    assert by[6].era == "B" and by[6].ticker == "LATE" and not by[6].in_window       # decides, but after the window's end


# ---- calendars and the stitch ----------------------------------------------------------------------------------------------------------
def test_unify_calendars():
    a = [d.date() for d in pd.bdate_range("2021-01-04", "2021-03-31")]
    b = [d.date() for d in pd.bdate_range("2021-03-01", "2021-06-30")]
    cal_u, map_b = M.unify_calendars(a, b)
    assert cal_u[:len(a)] == a and cal_u[-1] == b[-1] and len(cal_u) == len(set(cal_u))
    assert cal_u[map_b[0]] == b[0] and cal_u[map_b[-1]] == b[-1] and all(cal_u[map_b[i]] == b[i] for i in range(len(b)))
    with pytest.raises(M.GuardStop):
        M.unify_calendars(a, [d for d in b if d != date(2021, 3, 15)])      # a missing session on the overlap


def daily(cal, closes_by_ticker):
    """A minimal `Daily` for `R.bars_for`: flat arrays, one bar per session per ticker."""
    tickers = sorted(closes_by_ticker)
    n = len(cal)
    start = np.arange(len(tickers)) * n
    stop = start + n
    ci = np.tile(np.arange(n), len(tickers))
    c = np.concatenate([np.asarray(closes_by_ticker[t], dtype=float) for t in tickers])
    return SimpleNamespace(tickers=tickers, start=start, stop=stop, ci=ci, o=c, h=c * 1.01, l=c * 0.99, c=c, v=np.ones_like(c), cal=list(cal),
                           tid={t: k for k, t in enumerate(tickers)})


def test_stitched_closes_and_overlap_check():
    a = [d.date() for d in pd.bdate_range("2021-01-04", "2021-03-31")]
    b = [d.date() for d in pd.bdate_range("2021-03-01", "2021-06-30")]
    cal_u, map_b = M.unify_calendars(a, b)
    qa = 100.0 + np.arange(len(a))
    qb = 100.0 + np.arange(len(b)) + (len(a) - len([d for d in b if d <= a[-1]]))    # continues A's series exactly on the overlap
    DA = daily(a, {"QQQ": qa, "SPY": qa * 2})
    DB = daily(b, {"QQQ": qb, "SPY": qb * 2})
    px = M.stitched_closes(DA, DB, cal_u, map_b)
    assert len(px["QQQ"]) == len(cal_u) and px["QQQ"][0] == 100.0 and px["QQQ"][-1] == qb[-1] and not np.isnan(px["SPY"]).any()
    DB2 = daily(b, {"QQQ": qb * 1.02, "SPY": qb * 2})
    with pytest.raises(M.GuardStop):
        M.stitched_closes(DA, DB2, cal_u, map_b)


# ---- the market statistics and his bar -------------------------------------------------------------------------------------------------
def test_market_stats_recovers_beta_and_alpha():
    rng = np.random.default_rng(7)
    n = 600
    q = rng.normal(0.0005, 0.012, n)
    alpha_d, beta = 0.0008, 0.6
    r = alpha_d + beta * q                                  # no noise: exact recovery, t -> inf
    qqq = 100 * np.cumprod(1 + np.concatenate(([0.0], q)))
    eq = np.cumprod(1 + np.concatenate(([0.0], r)))
    spy = qqq * 0.5
    st = M.market_stats(eq, qqq, spy)
    assert abs(st["beta"] - beta) < 1e-9 and abs(st["alpha_ann"] - alpha_d * 252) < 1e-9
    assert st["alpha_t"] > 1e6 or not np.isfinite(st["alpha_t"])
    assert abs(st["total"] - (eq[-1] / eq[0] - 1)) < 1e-12 and abs(st["qqq"] - (qqq[-1] / qqq[0] - 1)) < 1e-12 and st["days"] == n + 1
    assert st["spy"] == st["qqq"]
    # noise: t finite, beta near
    r2 = r + rng.normal(0, 0.01, n)
    st2 = M.market_stats(np.cumprod(1 + np.concatenate(([0.0], r2))), qqq, spy)
    assert abs(st2["beta"] - beta) < 0.1 and np.isfinite(st2["alpha_t"])
    # sharpe: the pandas convention (sample std, x sqrt 252)
    rr = eq[1:] / eq[:-1] - 1
    assert abs(st["sharpe"] - rr.mean() / rr.std(ddof=1) * np.sqrt(252)) < 1e-12
    # a flat account: no Sharpe, no t -> the bar fails without raising
    st3 = M.market_stats(np.ones(n + 1), qqq, spy)
    ok, failed = M.bar_verdict(st3)
    assert not ok and len(failed) >= 1


def test_bar_verdict():
    good = dict(alpha_t=2.5, total=1.0, qqq=0.8, spy=0.4, sharpe=1.3, qqq_sharpe=1.1)
    assert M.bar_verdict(good) == (True, [])
    for k, v in (("alpha_t", 1.9), ("total", 0.7), ("sharpe", 1.0)):
        ok, failed = M.bar_verdict({**good, k: v})
        assert not ok and len(failed) == 1
    ok, failed = M.bar_verdict({**good, "total": 0.3})            # below both QQQ and SPY
    assert not ok and len(failed) == 2


def test_curve_on_window():
    sim = {"curve": ([10, 11, 12], [1.0, 1.1, 1.2])}
    assert list(M.curve_on_window(sim, 8, 14)) == [1.0, 1.0, 1.0, 1.1, 1.2, 1.2, 1.2]
    assert list(M.curve_on_window({"curve": ([], [])}, 0, 2)) == [1.0, 1.0, 1.0]


# ---- the undated open fill and the panel exit ------------------------------------------------------------------------------------------
def test_undated_entry():
    b, _ = bars(5, o=[10, 10, 10, 10, 10], l=[9.9, 9.0, 9.9, 9.9, 9.9], c=[10] * 5, h=[10.1] * 5)
    en = M.undated_entry(b, 0, 0.05)
    assert abs(en["fill"] - 10.01) < 1e-9 and abs(en["stop"] - 10.01 * 0.95) < 1e-9 and not en["day0"]["stopped"] and en["fill_minute"] == 0
    en2 = M.undated_entry(b, 1, 0.05)
    assert en2["day0"]["stopped"] and en2["day0"]["exit_price"] == en2["stop"]
    out = cb.day0_result_to_outcome(en2, 0.05)
    assert out["status"] == "stopped_day0" and abs(out["realized_r"] + 1.0) < 1e-9 and out["events"] == [(0, "day0_stop", en2["stop"], 1.0)]


def hevent(**kw):
    base = dict(eid=0, sym="ABC", ticker="ABC", era="A", setup="breakout", E="2019-06-03", D="2019-05-31", pivot=10.0, adr20=0.05, base_id="",
                retrigger=0, window_len=1, flicker=False, decides=True, in_window=True, exit_hi="", still_held=False, year=2019, month="2019-06")
    base.update(kw)
    return M.HEvent(**base)


def test_panel_exit_trade_filled_and_close_fill_and_truncation():
    c = np.array([10.0, 10.5, 11.0, 12.0, 11.5, 13.0])
    b, cidx = bars(6, c=c)
    en = {"status": "filled", "fill": 10.2, "stop": 9.8, "fill_minute": 7}
    t = M.panel_exit_trade(hevent(), en, b, cidx, 0, exit_ci=3)
    assert t.fill == 10.2 and abs(t.width - 0.4 / 10.2) < 1e-12 and t.legs == [(3, M.ORDER_CLOSE, 1.0, 12.0, "mark", 3)]
    assert abs(t.realized_r - (12.0 - 10.2) / 0.4) < 1e-9 and t.status == "panel_exit" and t.mature and len(t.path_c) == 4 and t.fill_minute == 7
    # not filled: bought at the buy day's close + slippage, width = ADR20
    t2 = M.panel_exit_trade(hevent(adr20=0.05), None, b, cidx, 0, exit_ci=2)
    assert abs(t2.fill - 10.0 * 1.001) < 1e-12 and abs(t2.width - 0.05) < 1e-12 and t2.status == "panel_exit_close_fill" and t2.legs[0][0] == 2
    # same-day exit: the leg sits on the buy day at the close
    t3 = M.panel_exit_trade(hevent(), en, b, cidx, 0, exit_ci=0)
    assert t3.legs == [(0, M.ORDER_CLOSE, 1.0, 10.0, "mark", 0)] and t3.sessions_held == 0
    # the exit session beyond the bars -> truncated at the last bar
    t4 = M.panel_exit_trade(hevent(), en, b, cidx, 0, exit_ci=40)
    assert t4.status == "panel_exit_truncated" and t4.legs[0][0] == 5 and t4.legs[0][3] == 13.0
    # a hole in the sessions stops the walk before it
    cidx2 = np.array([0, 1, 2, 4, 5, 6])
    t5 = M.panel_exit_trade(hevent(), en, b, cidx2, 0, exit_ci=5)
    assert t5.legs[0][0] == 2 and t5.status == "panel_exit_truncated"


def test_to_unified_shifts_era_b_only():
    en = {"status": "filled", "fill": 10.2, "stop": 9.8, "fill_minute": 7}
    b, cidx = bars(6, c=np.array([10.0, 10.5, 11.0, 12.0, 11.5, 13.0]))
    t = M.panel_exit_trade(hevent(era="B"), en, b, cidx, 0, exit_ci=3)
    map_b = np.arange(100, 200)
    M.to_unified(t, map_b)
    assert t.e_ci == 100 and t.legs[0][0] == 103
    ta = M.panel_exit_trade(hevent(era="A"), en, b, cidx, 0, exit_ci=3)
    M.to_unified(ta, map_b)
    assert ta.e_ci == 0 and ta.legs[0][0] == 3


def test_simulate_hand_computed_through_the_frozen_account():
    """One trade at the 30% cap: width 5% -> position min(1% / 5%, 30%) = 20% of equity; sold at +20% -> equity 1.04."""
    c = np.array([10.0, 10.5, 11.0, 12.0, 11.5, 13.0])
    b, cidx = bars(6, c=c)
    en = {"status": "filled", "fill": 10.0, "stop": 9.5, "fill_minute": 7}
    t = M.panel_exit_trade(hevent(), en, b, cidx, 0, exit_ci=3)
    cal = list(b.dates)
    sim = rp.simulate([t], M.CAP30, cal, 0)
    assert abs(sim["final"] - 1.04) < 1e-12 and sim["counts"]["entered"] == 1 and sim["counts"]["cap_bound"] == 0
    assert list(sim["curve"][0]) == [0, 1, 2, 3]
    eq = M.curve_on_window(sim, 0, 5)
    assert abs(eq[1] - (0.8 + 0.2 * 1.05)) < 1e-12 and abs(eq[-1] - 1.04) < 1e-12


# ---- F4: a same-day re-buy never reuses the first entry's fill --------------------------------------------------------------------------
def test_same_day_rebuy_is_out_of_every_account(tmp_path):
    df = entries_df()
    extra = [dict(df.iloc[0].to_dict(), eid="7", lo="2020-03-03", flat_clock_on_E="10:55"),                  # ABC again, same E
             dict(df.iloc[2].to_dict(), eid="8"),                                                              # UND again, same lo
             dict(df.iloc[0].to_dict(), eid="9", E="2020-03-04", D="2020-03-03", lo="2020-03-04", hi="2020-03-04")]   # ABC, a later E: kept
    pd.concat([df, pd.DataFrame(extra)]).to_csv(tmp_path / "e.tsv", sep="\t", index=False)
    evs, c = M.load_events(str(tmp_path / "e.tsv"))
    by = {e.eid: e for e in evs}
    assert by[7].same_day_rebuy and by[7].rebuy_of == 0 and not by[7].decides and not by[7].in_window and by[7].flat_clock_on_E == "10:55"
    assert by[8].same_day_rebuy and by[8].rebuy_of == 2 and not by[9].same_day_rebuy and by[9].in_window and not by[0].same_day_rebuy
    assert c["same_day_rebuy"] == 2 and c["same_day_rebuy_deciding"] == 1 and c["same_day_rebuy_in_window"] == 1 and c["same_day_rebuy_undated"] == 1
    assert c["deciding"] == 6 and c["in_window"] == 4 and c["in_window_breakout"] == 3        # the timeline's deciding count; the account loses #7
    # none -> every key still present (a missing key reads NOT MEASURED)
    evs, c = M.load_events(str(_write(tmp_path, entries_df())))
    assert c["same_day_rebuy"] == 0 and "same_day_rebuy_in_window" in c and "in_window_both" in c


def _write(tmp_path, df):
    p = tmp_path / "e0.tsv"
    df.to_csv(p, sep="\t", index=False)
    return p


# ---- F5: the panel's clock on E against our fill -----------------------------------------------------------------------------------------
def test_panel_vs_fill():
    assert M.minute_clock(0) == "09:30" and M.minute_clock(5) == "09:35" and M.minute_clock(65) == "10:35"
    en = {"status": "filled", "fill_minute": 10, "day0": {"stopped": False, "exit_price": None, "exit_minute": None}}       # 09:40
    c = M.panel_vs_fill(hevent(flat_clock_on_E="10:36", first_clock_on_E="11:00"), en)
    assert c["before_flat"] and not c["after_held"] and c["contradicts"] and c["fill_clock"] == "09:40"
    c = M.panel_vs_fill(hevent(flat_clock_on_E="09:24", first_clock_on_E="09:32", orh5_infeasible=True), {**en, "fill_minute": 5})
    assert c["after_held"] and not c["before_flat"] and c["contradicts"]
    c = M.panel_vs_fill(hevent(flat_clock_on_E="09:40", first_clock_on_E="09:40"), en)          # the same minute both ways: ambiguous
    assert not c["contradicts"]
    stop = {**en, "day0": {"stopped": True, "exit_price": 9.0, "exit_minute": 40}}             # stopped 10:10
    assert M.panel_vs_fill(hevent(first_clock_on_E="10:20"), stop)["day0_out_while_held"]
    assert not M.panel_vs_fill(hevent(first_clock_on_E="10:05"), stop)["day0_out_while_held"]
    c = M.panel_vs_fill(hevent(), stop)                                                        # first seen after E
    assert c["day0_out_before_later_sighting"] and not c["contradicts"]
    assert M.panel_vs_fill(hevent(), {"status": "no_trigger"})["fill_clock"] == ""


# ---- guard (2): any file under the output folder refuses the run ------------------------------------------------------------------------
def test_existing_outputs_any_file_under_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "OUT_DIR", str(tmp_path / "replay"))
    monkeypatch.setattr(M, "PRINTOUT", str(tmp_path / "02_replay.txt"))
    monkeypatch.setattr(M, "STOPPED", str(tmp_path / "02_replay.STOPPED.txt"))
    assert M.existing_outputs() == []
    (tmp_path / "replay").mkdir()
    assert M.existing_outputs() == []
    (tmp_path / "replay" / "anything_else.tsv").write_text("x")
    assert M.existing_outputs() == [str(tmp_path / "replay" / "anything_else.tsv")]


# ---- the freeze marker -----------------------------------------------------------------------------------------------------------------
def test_doc_has_exactly_one_marker_line():
    with open(M.DOC, "rb") as fh:
        raw = fh.read()
    assert len(M.marker_spans(raw)) == 1
    body = raw[:M.marker_spans(raw)[0][0]]
    assert M.FREEZE_MARKER.encode() not in body          # the marker string appears nowhere above its line (prose says "the freeze marker")


def test_constants_are_the_registration():
    assert M.WINDOW == ("2020-01-27", "2022-06-14") and M.WINDOW_CAP == 10 and M.BAR_ALPHA_T == 2.0
    assert M.DECIDING[1] == "d3_p33_tspd" and M.DECIDING[2].cap == 0.30 and M.DECIDING[2].risk == 0.01
    assert M.EXPECT["deciding"] == 294 and M.EXPECT["in_window"] == 262 and M.EXPECT["in_window_breakout"] + M.EXPECT["in_window_EP"] + M.EXPECT["in_window_both"] == 262
    assert M.EXPECT["same_day_rebuy_in_window"] == 2 and M.EXPECT["same_day_rebuy_deciding"] == 2
    assert "panel_reader" in M.CODE and "panel_read_printout" in M.FILES                  # F7: the reader and its printout are pinned


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ---- END TO END on a synthetic world: the real-run path, every function wired to real minute / daily files ---------------------------------
import gzip  # noqa: E402

CAL = [d.date() for d in pd.bdate_range("2019-06-03", periods=260)]
E_IDX = 150
E_ISO = CAL[E_IDX].isoformat()
FWD = [(10.20, 10.50, 10.10, 10.40), (10.40, 10.80, 10.30, 10.70), (10.70, 11.00, 10.60, 10.90), (10.90, 11.20, 10.80, 11.10),
       (11.10, 11.40, 11.00, 11.30), (11.30, 11.60, 11.20, 11.50), (11.00, 11.10, 10.55, 10.60), (10.50, 10.60, 10.40, 10.45)]


def _hhh_rows():
    rows = []
    for i, d in enumerate(CAL):
        if i < E_IDX:
            rows.append(("HHH", d, 10.0, 10.04, 9.96, 10.0, 1e6))
        elif i == E_IDX:
            rows.append(("HHH", d, 10.0, 10.20, 9.95, 10.15, 2e6))
        elif i - E_IDX <= len(FWD):
            o, h, l, c = FWD[i - E_IDX - 1]
            rows.append(("HHH", d, o, h, l, c, 1e6))
        else:
            rows.append(("HHH", d, 10.45, 10.50, 10.40, 10.45, 1e6))
    return rows


def _flat(tk, base, spread=0.01):
    return [(tk, d, base, base * (1 + spread), base * (1 - spread), base, 1e6) for d in CAL]


def _hhh_minutes():
    m = [(k, 10.0, 10.05, 9.95 if k == 2 else 9.99, 10.0) for k in range(5)]
    m.append((5, 10.04, 10.10, 10.02, 10.08))
    m += [(k, 10.10, 10.20 if k == 200 else 10.15, 10.05, 10.12) for k in range(6, 390)]
    return m


def _expected_hhh_r():
    fill, stop = 10.05 * 1.001, 9.95
    return ((10.90 - fill) / 3.0 + (10.50 - fill) * (2.0 / 3.0)) / (fill - stop)


def test_run_replay_end_to_end_on_a_synthetic_world(tmp_path, monkeypatch):
    # the daily export: SPY / QQQ flat, HHH the breakout (fills, sells a third on session 3, trails out at session 8's open), BBB a breakout
    # whose level the day never clears (no trigger -> the panel-exit account buys it at the close), AAA a control name, UUU an undated holding
    qqq_c = [200.0 + 0.05 * i + 0.8 * np.sin(i / 7.0) for i in range(len(CAL))]          # a market with variance (the regression needs one)
    rows = _flat("SPY", 300.0) + [("QQQ", d, c, c * 1.005, c * 0.995, c, 1e6) for d, c in zip(CAL, qqq_c)] + _hhh_rows() + _flat("AAA", 20.0) \
        + _flat("BBB", 30.0) + _flat("UUU", 50.0, 0.01)
    exp = tmp_path / "export.csv.gz"
    with gzip.open(exp, "wt") as fh:
        for t, d, o, h, l, c, v in rows:
            fh.write(f"{t},{d.isoformat()},{o},{h},{l},{c},{v}\n")
    DA, _ = rp.load_daily_subset(str(exp))
    DB, _ = rp.load_daily_subset(str(exp), keep={"QQQ"})
    cal_u, map_b = M.unify_calendars(DA.cal, DB.cal)
    px = M.stitched_closes(DA, DB, cal_u, map_b)
    # the minute file of E (one tree, "A") and its fetch log
    mdir = tmp_path / "minutes"
    mdir.mkdir()
    lines = [f"HHH|{m}|{o}|{h}|{l}|{c}|100" for m, o, h, l, c in _hhh_minutes()]
    for tk, p in (("AAA", 20.0), ("BBB", 30.0)):
        lines += [f"{tk}|{m}|{p}|{p * 1.01}|{p * 0.99}|{p}|100" for m in range(390)]
    with gzip.open(mdir / f"{E_ISO}.psv.gz", "wt") as fh:
        fh.write("\n".join(lines) + "\n")
    done = {"A": {(E_ISO, t): "ok" for t in ("HHH", "AAA", "BBB")}, "B": {}, "EP": {}}
    files = {"A": {E_ISO: mdir / f"{E_ISO}.psv.gz"}, "B": {}, "EP": {}}
    # the panel's entries and snapshots (what run_replay reads from the timeline's outputs)
    exit_h, exit_b, exit_u = CAL[E_IDX + 4].isoformat(), CAL[E_IDX + 2].isoformat(), CAL[E_IDX + 3].isoformat()
    pd.DataFrame([dict(initial="False", lo=E_ISO, exit_hi=exit_h, sym_a="HHH"), dict(initial="False", lo=E_ISO, exit_hi=exit_b, sym_a="BBB"),
                  dict(initial="False", lo=E_ISO, exit_hi=exit_u, sym_a="UUU"), dict(initial="True", lo="", exit_hi="", sym_a="OLD")]
                 ).to_csv(tmp_path / "entries.tsv", sep="\t", index=False)
    pd.DataFrame([dict(asof=CAL[E_IDX + 10].isoformat())]).to_csv(tmp_path / "snapshots.tsv", sep="\t", index=False)
    monkeypatch.setitem(M.FILES, "entries", str(tmp_path / "entries.tsv"))
    monkeypatch.setitem(M.FILES, "snapshots", str(tmp_path / "snapshots.tsv"))
    monkeypatch.setattr(M, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(M, "BAND_DRAWS", 3)
    monkeypatch.setattr(M, "write_g8", lambda era, trades, cal: (0, 0))
    D_ISO = CAL[E_IDX - 1].isoformat()
    evs = [hevent(eid=0, sym="HHH", ticker="HHH", E=E_ISO, D=D_ISO, pivot=10.0, adr20=0.05, exit_hi=exit_h, year=CAL[E_IDX].year, month=E_ISO[:7]),
           hevent(eid=1, sym="BBB", ticker="BBB", E=E_ISO, D=D_ISO, pivot=29.0, adr20=0.05, retrigger=1, exit_hi=exit_b, year=CAL[E_IDX].year, month=E_ISO[:7]),
           hevent(eid=2, sym="UUU", ticker="UUU", setup="undated", E=E_ISO, D="", pivot=None, adr20=None, decides=False, in_window=False,
                  exit_hi=exit_u, year=CAL[E_IDX].year, month=E_ISO[:7])]
    qqq = M.R.bars_for(DA, DA.tid["QQQ"])
    for ev in evs:
        M.event_facts(ev, DA, qqq, {}, done, files, DA.cal)
    assert all(ev.keep for ev in evs) and evs[2].D == D_ISO and evs[2].adr20 == pytest.approx(0.02, rel=1e-9) and evs[2].minutes_state == "n/a"
    assert evs[0].minutes_tree == "A" and evs[0].minutes_state == "ok"
    pool = pd.DataFrame([dict(ticker="AAA", D=D_ISO, E=E_ISO, base_id="AAA|1", retrigger="0", pivot="20.1", adr20="0.05"),
                         dict(ticker="BBB", D=D_ISO, E=E_ISO, base_id="BBB|1", retrigger="1", pivot="29.0", adr20="0.05")])
    w0, w1 = E_IDX - 5, E_IDX + 30
    S = dict(evs=evs, Ds={"A": DA, "B": DB}, cal_u=cal_u, map_b=map_b, px=px, w0=w0, w1=w1, done=done, files=files, guards={"A": {}, "B": {}},
             pool_rows=pool)
    say = rp.Say()
    M.run_replay(S, say)
    text = "\n".join(say.lines)
    for needle in ("THE WALK", "G8", "ACCOUNTS", "THE DECIDING READOUT", "HIS BAR", "PER TRADE", "BESIDE", "SAME-DAY BAND", "Outputs written"):
        assert needle in text, needle
    # the trade table: HHH's primary arm equals the hand-computed R; the speed arm trails the 10-day too (ADR20 5% > the 4.79% cut) -> equal
    t = pd.read_csv(tmp_path / "out" / "trades.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
    h = t[(t.ticker == "HHH") & (t.arm == "p33_s3_t10")]
    assert len(h) == 1 and float(h.realized_r.iloc[0]) == pytest.approx(_expected_hhh_r(), rel=1e-9)
    hs = t[(t.ticker == "HHH") & (t.arm == "d3_p33_tspd")]
    assert len(hs) == 1 and float(hs.realized_r.iloc[0]) == pytest.approx(_expected_hhh_r(), rel=1e-9)
    assert set(t[t.ticker == "BBB"].entry_status) == {"no_trigger"}
    assert set(t[t.ticker == "UUU"].arm) == {"p33_s3_t10", "d3_p33_tspd"}          # the undated open fill walked both arms
    # the accounts: deciding = HHH alone at the 30% cap (1% / 1.1% width -> cap-bound)
    acc = pd.read_csv(tmp_path / "out" / "account_his.tsv", sep="\t")
    fill = 10.05 * 1.001
    width = (fill - 9.95) / fill
    pos = min(0.01 / width, 0.30)
    want = 1.0 + pos * ((10.90 / fill - 1) / 3 + (10.50 / fill - 1) * 2 / 3)
    dec = acc[acc.config == "deciding"]
    assert dec.equity.iloc[-1] == pytest.approx(want, rel=1e-9) and dec.date.iloc[0] == cal_u[w0].isoformat()
    # the panel-exit account: HHH sold at session 4's close (11.10), BBB bought at E's close + slippage and sold at session 2's close (30.0)
    pan = acc[acc.config == "panel_exit"]
    want_p = 1.0 + pos * (11.10 / fill - 1) + min(0.01 / 0.05, 0.30) * (30.0 / (30.0 * 1.001) - 1)
    assert pan.equity.iloc[-1] == pytest.approx(want_p, rel=1e-9)
    # the market table carries the deciding row with a verdict and the beside rows without
    mk = pd.read_csv(tmp_path / "out" / "market.tsv", sep="\t")
    assert set(mk.variant) >= {"deciding", "panel_exit", "primary_exit_cap30"} and mk[mk.variant == "deciding"].verdict.iloc[0] in ("PASS", "FAIL")
    assert mk[mk.variant == "deciding"].days.iloc[0] == w1 - w0 + 1
    band = pd.read_csv(tmp_path / "out" / "account_band.tsv", sep="\t")
    assert len(band) == 3 and (band.final == 1.0).all()               # the control pool (AAA) never triggers; BBB is excluded as his name that day
    assert "days short of events 3" in text                            # AAA alone cannot match his 2 breakout entries on E
