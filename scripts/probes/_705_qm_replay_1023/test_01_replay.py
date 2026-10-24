"""Synthetic tests for 01_replay.py (#705 QM replay). No real data file is opened by any test (the module's import hashes nothing;
the end-to-end test runs `run_replay` on a hand-built world in tmp_path).

Run:  python3 -m pytest scripts/probes/_705_qm_replay_1023/test_01_replay.py -q
"""
from __future__ import annotations

import gzip
import importlib.util
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("replay01", os.path.join(HERE, "01_replay.py"))
rp = importlib.util.module_from_spec(_spec)
sys.modules["replay01"] = rp
_spec.loader.exec_module(rp)
R, cb = rp.R, rp.cb


# ═════════════════════════════════════════════════════════════════════════════════════════════
# a hand-built world: one stock HHH whose ORH5 trade has a known answer, plus filler stocks
# ═════════════════════════════════════════════════════════════════════════════════════════════
def bdays(start: str, n: int) -> list:
    return [d.date() for d in pd.bdate_range(start, periods=n)]


CAL = bdays("2019-06-03", 260)
E_IDX = 150                                   # E = CAL[150]; D = CAL[149]
FWD = [  # (o, h, l, c) of sessions 1..8 after E (session 3's close takes the third; session 7 closes under the 10-day; 8's open sells)
    (10.20, 10.50, 10.10, 10.40), (10.40, 10.80, 10.30, 10.70), (10.70, 11.00, 10.60, 10.90), (10.90, 11.20, 10.80, 11.10),
    (11.10, 11.40, 11.00, 11.30), (11.30, 11.60, 11.20, 11.50), (11.00, 11.10, 10.55, 10.60), (10.50, 10.60, 10.40, 10.45)]


def hhh_rows():
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


def hhh_minutes():
    """E's minutes: 0..4 range 9.95..10.05 (ORH5 = 10.05); minute 5 opens 10.04 and trades 10.10 -> fill 10.05 x 1.001; the rest of the
    day stays above 10.0 with one minute at the day high 10.20 (the minute day matches the daily bar)."""
    m = []
    for k in range(5):
        m.append((k, 10.0, 10.05, 9.95 if k == 2 else 9.99, 10.0))
    m.append((5, 10.04, 10.10, 10.02, 10.08))
    for k in range(6, 390):
        hi = 10.20 if k == 200 else 10.15
        m.append((k, 10.10, hi, 10.05, 10.12))
    return m


def expected_hhh_r() -> float:
    fill = 10.05 * 1.001
    stop = 9.95
    return ((10.90 - fill) / 3.0 + (10.50 - fill) * (2.0 / 3.0)) / (fill - stop)


def filler_rows(tk: str, base: float):
    return [(tk, d, base, base * 1.01, base * 0.99, base, 1e6) for d in CAL]


def write_export(path: Path, rows: list) -> None:
    with gzip.open(path, "wt") as fh:
        for t, d, o, h, l, c, v in rows:
            fh.write(f"{t},{d.isoformat()},{o},{h},{l},{c},{v}\n")


def world_export(path: Path) -> None:
    rows = filler_rows("SPY", 300.0) + filler_rows("QQQ", 200.0) + hhh_rows() + filler_rows("AAA", 20.0) + filler_rows("BBB", 30.0)
    rows.sort(key=lambda r: (r[1], r[0]), reverse=True)          # unsorted on purpose: the loader sorts
    write_export(path, rows)


def minute_bars(rows):
    return cb.minute_bars_from_lists([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows],
                                     [r[4] for r in rows], [100.0] * len(rows))


def hhh_event(**kw) -> "rp.Event":
    base = dict(era="A", ticker="HHH", D=CAL[E_IDX - 1].isoformat(), E=CAL[E_IDX].isoformat(), base_id="HHH|2019-12-01", retrigger=0,
                pivot=10.0, adr20=0.05, his=True, year=CAL[E_IDX].year, month=CAL[E_IDX].isoformat()[:7], minutes_state="ok")
    base.update(kw)
    return rp.Event(**base)


@pytest.fixture()
def world(tmp_path):
    p = tmp_path / "export.csv.gz"
    world_export(p)
    D, info = rp.load_daily_subset(str(p))
    return SimpleNamespace(path=p, D=D, info=info)


def hhh_bars(D):
    bars, cidx = R.bars_for(D, D.tid["HHH"])
    e = R.locate_breakout_index(D.cal, cidx, CAL[E_IDX].isoformat())
    return bars, cidx, e


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the loader: parity with runner.load_daily, the era-B cut at read, the ticker subset
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_loader_equals_runner_load_daily(world):
    ref = R.load_daily(world.path)
    got = world.D
    assert got.tickers == ref.tickers and got.cal == ref.cal and got.tid == ref.tid
    for k in ("start", "stop", "ci", "o", "h", "l", "c", "v"):
        assert np.array_equal(getattr(got, k), getattr(ref, k)), k
    assert (got.n_holes, got.n_hole_tickers) == (ref.n_holes, ref.n_hole_tickers)


def test_era_b_cut_drops_rows_at_read_and_asserts(world):
    cut = CAL[100].isoformat()
    D, info = rp.load_daily_subset(str(world.path), keep={"HHH"}, cut=cut)
    assert D.cal[-1].isoformat() == cut and max(D.cal).isoformat() <= cut
    assert info["dated_after_cut"] == 5 * (len(CAL) - 101)          # five tickers x the sessions after the cut
    assert set(D.tickers) == {"SPY", "HHH"}                          # SPY is always kept (the calendar)
    a, b = int(D.start[D.tid["HHH"]]), int(D.stop[D.tid["HHH"]])
    assert b - a == 101


def test_load_done_cut(tmp_path):
    p = tmp_path / "_done.psv"
    p.write_text("2024-12-30|AAA|390|ok\n2024-12-31|BBB|0|empty\n2025-01-02|CCC|390|ok\n")
    done, dropped = rp.load_done(str(p), cut="2024-12-31")
    assert dropped == 1 and done == {("2024-12-30", "AAA"): "ok", ("2024-12-31", "BBB"): "empty"}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the walk: the hand-computed trade, parity with the runner, the legs
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_hhh_fill_stop_partial_trail_known_answer(world):
    bars, cidx, e = hhh_bars(world.D)
    w = rp.walk_event(hhh_event(), bars, cidx, e, minute_bars(hhh_minutes()))
    en = w["orh5"]["entry"]
    assert en["status"] == "filled" and en["fill_minute"] == 5
    assert en["fill"] == pytest.approx(10.05 * 1.001, abs=1e-12) and en["stop"] == pytest.approx(9.95)
    raw = w["orh5"]["arms"]["p33_s3_t10"]
    assert raw["status"] == "trailed" and raw["sessions_held"] == 8
    assert raw["realized_r"] == pytest.approx(expected_hhh_r(), abs=1e-12)
    kinds = [(ev[0], ev[1]) for ev in raw["events"]]
    assert (3, "partial") in kinds and (8, "trail") in kinds
    t = rp.make_trade(hhh_event(), en, raw, bars, cidx, e, w["n_fwd"])
    assert [(lg[0] - int(cidx[e]), lg[1], round(lg[2], 9), lg[3]) for lg in t.legs] == [
        (3, rp.ORDER_CLOSE, round(1 / 3, 9), 10.90), (8, rp.ORDER_OPEN, round(2 / 3, 9), 10.50)]
    assert t.r_slip[0] == pytest.approx(raw["realized_r"], abs=1e-12)
    fill = 10.05 * 1.001
    want01 = ((10.90 * 0.999 - fill) / 3 + (10.50 * 0.999 - fill) * 2 / 3) / (fill - 9.95)
    assert t.r_slip[1] == pytest.approx(want01, abs=1e-12)
    assert len(t.path_c) == 9 and t.path_c[0] == pytest.approx(10.15) and t.path_c[-1] == pytest.approx(10.45)


def test_too_wide_stop_is_skipped(world):
    bars, cidx, e = hhh_bars(world.D)
    w = rp.walk_event(hhh_event(adr20=0.005), bars, cidx, e, minute_bars(hhh_minutes()))     # width 1.09% > ADR 0.5%
    assert w["orh5"]["entry"]["status"] == "abstain" and w["orh5"]["entry"]["reason"] == "too_wide" and not w["orh5"]["arms"]


def test_grid_dispatch_equals_runner_walk_arms(world):
    bars, cidx, e = hhh_bars(world.D)
    mb = minute_bars(hhh_minutes())
    w = rp.walk_event(hhh_event(), bars, cidx, e, mb)
    en = w["orh5"]["entry"]
    fwd, _ = cb.forward_window(bars, cidx, e, rp.HORIZON)
    ref = R.walk_arms(en, closes_before=bars.c[:e + 1], fwd=fwd, adr20=0.05, horizon=rp.HORIZON,
                      arms={a: cb.ARMS[a] for a in rp.GRID_ARMS})
    mine = {a: R.arm_result(w["orh5"]["arms"][a], width=en["width_pct"], n_fwd=len(fwd)) for a in rp.GRID_ARMS}
    assert mine == ref
    pp_ref = R.exitpb_walk_arms(en, closes_before=bars.c[:e + 1], fwd=fwd, adr20=0.05, minutes=mb, horizon=rp.HORIZON,
                                arms={"pp": R.EXITPB_ARMS["pp"]})["pp"]
    assert w["orh5"]["arms"]["pp"]["realized_r"] == pp_ref["realized_r"] and w["orh5"]["arms"]["pp"]["events"] == pp_ref["events"]


def test_primary_equals_runner_evaluate_candidate(world):
    """The runner's own per-candidate engine on the same synthetic candidate: every minute variant's p33_s3_t10 row is ours."""
    bars, cidx, e = hhh_bars(world.D)
    mb = minute_bars(hhh_minutes())
    c = {"ticker": "HHH", "E": CAL[E_IDX].isoformat(), "pivot": 10.0, "adr20": 0.05}
    ref = R.evaluate_candidate(c, bars, cidx, e, mb, world.D.cal, len(world.D.cal) - 1, apollo=False)
    w = rp.walk_event(hhh_event(), bars, cidx, e, mb)
    for vr in ref:
        if vr["variant"] not in ("orh5", "orh1", "orh60"):
            continue
        mine = w[vr["variant"]]
        assert mine["entry"]["status"] == vr["entry"]["status"]
        if vr["entry"]["status"] == "filled":
            assert mine["arms"]["p33_s3_t10"]["realized_r"] == vr["arms"]["p33_s3_t10"]["realized_r"]
            assert mine["arms"]["p33_s3_t10"]["status"] == vr["arms"]["p33_s3_t10"]["status"]


def brk(i: int) -> np.ndarray:
    return np.array([CAL[E_IDX + i].toordinal()], dtype=np.int64)


def test_break_after_the_exit_leaves_the_walk_unchanged_and_mature(world):
    """HHH sells its last two thirds at the open of session 8: a break dated on session 9 cuts the window to sessions 1..8."""
    bars, cidx, e = hhh_bars(world.D)
    mb = minute_bars(hhh_minutes())
    ref = rp.walk_event(hhh_event(), bars, cidx, e, mb)
    w = rp.walk_event(hhh_event(), bars, cidx, e, mb, breaks=brk(9))
    assert w["break_cut"] == CAL[E_IDX + 9].isoformat() and w["n_fwd"] == 8 and ref["break_cut"] == ""
    raw, raw0 = w["orh5"]["arms"]["p33_s3_t10"], ref["orh5"]["arms"]["p33_s3_t10"]
    assert raw["status"] == raw0["status"] == "trailed" and raw["realized_r"] == raw0["realized_r"] and raw["events"] == raw0["events"]
    t = rp.make_trade(hhh_event(), w["orh5"]["entry"], raw, bars, cidx, e, w["n_fwd"])
    assert t.mature and t.realized_r == pytest.approx(expected_hhh_r(), abs=1e-12)
    # a break dated after the window's last bar, or on / before E, cuts nothing
    late = rp.walk_event(hhh_event(), bars, cidx, e, mb, breaks=np.array([CAL[-1].toordinal() + 10]))
    early = rp.walk_event(hhh_event(), bars, cidx, e, mb, breaks=np.array([CAL[E_IDX].toordinal()]))
    assert late["break_cut"] == early["break_cut"] == "" and late["n_fwd"] == early["n_fwd"] == ref["n_fwd"]


def test_break_before_the_exit_degrades_the_walk(world):
    """A break dated on session 6: the walk reads sessions 1..5 — the third sold at session 3, the rest marked at session 5's close
    (11.30) — and ends `degraded`: not mature (in no per-trade number), booked in the account."""
    bars, cidx, e = hhh_bars(world.D)
    w = rp.walk_event(hhh_event(), bars, cidx, e, minute_bars(hhh_minutes()), breaks=brk(6))
    assert w["break_cut"] == CAL[E_IDX + 6].isoformat() and w["n_fwd"] == 5
    raw = w["orh5"]["arms"]["p33_s3_t10"]
    assert raw["status"] == "degraded"
    t = rp.make_trade(hhh_event(), w["orh5"]["entry"], raw, bars, cidx, e, w["n_fwd"])
    fill = 10.05 * 1.001
    assert not t.mature and t.realized_r == pytest.approx(((10.90 - fill) / 3 + (11.30 - fill) * 2 / 3) / (fill - 9.95), abs=1e-12)
    assert [(lg[5], lg[4]) for lg in t.legs] == [(3, "partial"), (5, "mark")] and sum(lg[2] for lg in t.legs) == pytest.approx(1.0)
    assert w["orh5"]["arms"]["pp"]["status"] == "degraded"             # `pp` (20-day trail) is still open at the break too


def test_break_on_the_session_after_e_leaves_an_empty_window(world):
    bars, cidx, e = hhh_bars(world.D)
    w = rp.walk_event(hhh_event(), bars, cidx, e, minute_bars(hhh_minutes()), breaks=brk(1))
    assert w["n_fwd"] == 0
    raw = w["orh5"]["arms"]["p33_s3_t10"]
    assert raw["status"] == "degraded"                                # marked at E's close
    t = rp.make_trade(hhh_event(), w["orh5"]["entry"], raw, bars, cidx, e, w["n_fwd"])
    assert not t.mature and t.legs[-1][4] == "mark" and t.legs[-1][3] == pytest.approx(10.15)
    assert w["orh5"]["arms"]["pp"]["status"] == "degraded"


def test_walk_all_empty_event_without_a_date_file_abstains_no_minutes(world):
    """An `empty`-logged event is kept; its date file may not exist — the entry abstains `no_minutes` instead of a KeyError."""
    E = CAL[E_IDX].isoformat()
    ev = hhh_event(minutes_state="empty")
    DB, _ = rp.load_daily_subset(str(world.path), keep={"QQQ"})
    S = {"evs": [ev], "Ds": {"A": world.D, "B": DB}, "files": {"A": {}, "B": {}}, "guards": {"A": {}, "B": {}}}
    res, tally = rp.walk_all(S, rp.Say())
    en = res[("A", "HHH", E)]["orh5"]["entry"]
    assert en["status"] == "abstain" and en["reason"] == "no_minutes" and not res[("A", "HHH", E)]["orh5"]["arms"]
    assert tally["A_minute_date_file_absent"] == 1 and tally["A_minutes_no_rows"] == 1


def test_walk_all_cuts_at_a_break_and_keeps_the_event(world, tmp_path):
    E = CAL[E_IDX].isoformat()
    mdir = tmp_path / "m"
    mdir.mkdir()
    with gzip.open(mdir / f"{E}.psv.gz", "wt") as fh:
        fh.write("\n".join(f"HHH|{m}|{o}|{h}|{l}|{c}|100" for m, o, h, l, c in hhh_minutes()) + "\n")
    ev = hhh_event()
    DB, _ = rp.load_daily_subset(str(world.path), keep={"QQQ"})
    S = {"evs": [ev], "Ds": {"A": world.D, "B": DB}, "files": {"A": {E: mdir / f"{E}.psv.gz"}, "B": {}},
         "guards": {"A": {"HHH": brk(6)}, "B": {}}}
    res, tally = rp.walk_all(S, rp.Say())
    assert ev.keep and ev.break_cut == CAL[E_IDX + 6].isoformat() and tally["A_forward_window_cut_at_a_break"] == 1
    assert res[("A", "HHH", E)]["orh5"]["arms"]["p33_s3_t10"]["status"] == "degraded"


def test_day0_stop_leg_is_intraday_on_e(world):
    bars, cidx, e = hhh_bars(world.D)
    mins = hhh_minutes()
    mins[300] = (300, 10.0, 10.0, 9.90, 9.92)                       # a day-0 stop-out at 9.95 after the fill
    D = rp.walk_event(hhh_event(), bars, cidx, e, minute_bars(mins))
    raw = D["orh5"]["arms"]["p33_s3_t10"]
    assert raw["status"] == "stopped_day0"
    t = rp.make_trade(hhh_event(), D["orh5"]["entry"], raw, bars, cidx, e, D["n_fwd"])
    assert t.legs == [(int(cidx[e]), rp.ORDER_INTRADAY, 1.0, 9.95, "day0_stop", 0)]
    assert t.realized_r == pytest.approx(-1.0)


def test_legs_order_open_close_intraday():
    bars = SimpleNamespace(o=np.array([10.0, 10.0, 9.0, 10.0, 11.0]))
    cidx = np.array([100, 101, 102, 103, 104])
    ev = [(1, "partial", 10.5, 1 / 3), (1, "be_above_close", 10.0, 0.0), (2, "stop_gap", 9.0, 2 / 3)]
    legs = rp.legs_of(ev, bars, cidx, 0)
    assert [(l[0], l[1]) for l in legs] == [(101, rp.ORDER_CLOSE), (102, rp.ORDER_OPEN)]
    ev2 = [(3, "stop", 9.5, 1.0)]                                     # touched intraday (open 10.0 above the stop)
    assert rp.legs_of(ev2, bars, cidx, 0)[0][1] == rp.ORDER_INTRADAY
    ev3 = [(4, "trail", 11.0, 1.0)]
    assert rp.legs_of(ev3, bars, cidx, 0)[0][1] == rp.ORDER_OPEN


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the account simulation
# ═════════════════════════════════════════════════════════════════════════════════════════════
SIMCAL = bdays("2020-01-01", 40)


def mk(k, e_ci, width, legs_rel, path, ticker=None, fm=5):
    """A synthetic Trade: fill 100, stop 100 (1 - width); legs (session offset, order, frac, px); path = closes from E."""
    fill = 100.0
    legs = [(e_ci + s, o, f, px, "x", s) for s, o, f, px in legs_rel]
    return rp.Trade(key=("A", ticker or f"T{k}", str(k)), ticker=ticker or f"T{k}", era="A", e_ci=e_ci, fill_minute=fm, fill=fill,
                    stop=fill * (1 - width), width=width, status="trailed", mature=True, realized_r=0.0, r_slip=(0.0, 0.0, 0.0),
                    sessions_held=max(s for s, *_ in legs_rel), legs=legs, path_c=np.asarray(path, dtype=float))


def test_primary_config_is_his_sizing():
    """operator_shared_notes.md (risk 0.25-1%, positions 10-20%, at most 30% in one stock) + the SSoT's min(20%, 1% / stop width)."""
    c = rp.PRIMARY_CONFIG
    assert (c.risk, c.cap, c.stock_limit, c.room, c.same_ticker, c.exit_slip) == (0.01, 0.20, 0.30, "skip", "allow", 0.0)
    beside = {x.name: x for x in rp.CONFIGS}
    assert beside["risk_0.25"].risk == 0.0025 and beside["risk_0.5"].risk == 0.005
    assert beside["cap_10"].cap == 0.10 and beside["cap_30"].cap == 0.30 and "cap_33" not in beside and "risk_1.0" not in beside
    assert all(x.stock_limit == 0.30 for x in rp.CONFIGS)


def test_sim_cap_binds_and_compounds():
    t1 = mk(1, 2, 0.01, [(3, rp.ORDER_CLOSE, 1.0, 110.0)], [100, 101, 105, 110])   # risk 1% / width 1% = 100% -> capped at 20%
    t2 = mk(2, 8, 0.10, [(2, rp.ORDER_CLOSE, 1.0, 120.0)], [100, 110, 120])        # 1% / 10% = 10% of the equity at the prior close
    sim = rp.simulate([t1, t2], rp.PRIMARY_CONFIG, SIMCAL, 0)
    assert sim["counts"]["cap_bound"] == 1 and sim["counts"]["entered"] == 2
    e1 = 1.0 + 0.20 * 0.10
    assert sim["final"] == pytest.approx(e1 + 0.10 * e1 * 0.20, abs=1e-12)
    assert sim["max_dd"] == pytest.approx(0.0, abs=1e-12)
    assert sim["yearly"][2020] == pytest.approx(sim["final"] - 1.0)


def test_sim_skips_when_the_full_position_does_not_fit():
    ts = [mk(k, 3, 0.01, [(2, rp.ORDER_CLOSE, 1.0, 100.0)], [100, 100, 100], fm=k) for k in range(6)]
    sim = rp.simulate(ts, rp.PRIMARY_CONFIG, SIMCAL, 0)                 # five 20% positions fill the account; the sixth is skipped
    assert sim["counts"]["entered"] == 5 and sim["counts"]["skipped_no_room"] == 1 and sim["max_open"] == 5
    assert sim["max_gross"] == pytest.approx(1.0)
    # a 40% cap is above the 30% stock limit: no limit here, so the test reads the trim rule alone
    trim = rp.simulate([mk(k, 3, 0.01, [(2, rp.ORDER_CLOSE, 1.0, 100.0)], [100, 100, 100], fm=k) for k in range(3)],
                       rp.Config("t", cap=0.40, stock_limit=None, room="trim"), SIMCAL, 0)
    assert trim["counts"]["entered"] == 3 and trim["counts"]["trimmed"] == 1


def test_sim_partial_returns_cash_and_open_exit_frees_room_same_day():
    # five 20% positions fill the account on day 3; one sells everything AT THE OPEN of day 6 -> a day-6 entry fits;
    # the others sell AT THE CLOSE of day 6 -> they do NOT free room for a day-6 entry
    a = [mk(k, 3, 0.01, [(3, rp.ORDER_OPEN, 1.0, 100.0)], [100] * 4, fm=k) for k in range(1)]
    b = [mk(k, 3, 0.01, [(3, rp.ORDER_CLOSE, 1.0, 100.0)], [100] * 4, fm=k) for k in range(1, 5)]
    new1 = mk(10, 6, 0.01, [(1, rp.ORDER_CLOSE, 1.0, 100.0)], [100, 100], fm=1)
    new2 = mk(11, 6, 0.01, [(1, rp.ORDER_CLOSE, 1.0, 100.0)], [100, 100], fm=2)
    sim = rp.simulate(a + b + [new1, new2], rp.PRIMARY_CONFIG, SIMCAL, 0)
    assert sim["counts"]["entered"] == 6 and sim["counts"]["skipped_no_room"] == 1
    # a one-third partial at the close returns a third of the cost
    p = mk(20, 2, 0.02, [(1, rp.ORDER_CLOSE, 1 / 3, 130.0), (2, rp.ORDER_CLOSE, 2 / 3, 100.0)], [100, 130, 100])
    s2 = rp.simulate([p], rp.PRIMARY_CONFIG, SIMCAL, 0)
    assert s2["final"] == pytest.approx(1.0 + 0.20 * 0.30 / 3, abs=1e-12)


def test_sim_same_ticker_allow_and_skip():
    t1 = mk(1, 2, 0.10, [(5, rp.ORDER_CLOSE, 1.0, 100.0)], [100] * 6, ticker="ZZZ")    # 1% / 10% = 10%
    t2 = mk(2, 4, 0.10, [(2, rp.ORDER_CLOSE, 1.0, 100.0)], [100] * 3, ticker="ZZZ")    # 10% more: 20% in ZZZ, inside the 30% limit
    allow = rp.simulate([t1, t2], rp.PRIMARY_CONFIG, SIMCAL, 0)
    assert allow["counts"]["entered"] == 2 and allow["counts"]["same_ticker_concurrent"] == 1
    assert allow["counts"]["stock_limit_trimmed"] == 0 and allow["counts"]["skipped_stock_limit"] == 0
    skip = rp.simulate([t1, t2], rp.Config("s", same_ticker="skip"), SIMCAL, 0)
    assert skip["counts"]["entered"] == 1 and skip["counts"]["skipped_same_ticker"] == 1


def test_sim_his_30pct_per_stock_limit_at_cost():
    """A second position in a held stock takes only the room left under 30% (at cost, of the prior close's equity); none left -> skipped
    and counted. A partial sale gives back the sold shares' COST, not their sale value."""
    t1 = mk(1, 2, 0.05, [(10, rp.ORDER_CLOSE, 1.0, 100.0)], [100] * 11, ticker="ZZZ")   # 20% (cap-bound)
    t2 = mk(2, 3, 0.05, [(8, rp.ORDER_CLOSE, 1.0, 100.0)], [100] * 9, ticker="ZZZ", fm=1)  # wants 20%, takes the 10% left
    t3 = mk(3, 4, 0.05, [(6, rp.ORDER_CLOSE, 1.0, 100.0)], [100] * 7, ticker="ZZZ", fm=1)  # no room left -> skipped
    sim = rp.simulate([t1, t2, t3], rp.PRIMARY_CONFIG, SIMCAL, 0)
    assert sim["counts"]["entered"] == 2 and sim["counts"]["stock_limit_trimmed"] == 1 and sim["counts"]["skipped_stock_limit"] == 1
    assert sim["max_gross"] == pytest.approx(0.30)
    # the room is measured at COST: a held position marked up 50% does not shrink the room; selling half of it frees half its cost
    u1 = mk(1, 2, 0.05, [(2, rp.ORDER_CLOSE, 0.5, 150.0), (6, rp.ORDER_CLOSE, 0.5, 150.0)], [100, 150, 150, 150, 150, 150, 150], ticker="ZZZ")
    u2 = mk(2, 5, 0.05, [(2, rp.ORDER_CLOSE, 1.0, 100.0)], [100, 100, 100], ticker="ZZZ")   # cost held 10% -> room 30% x eq_prev - 10%
    s2 = rp.simulate([u1, u2], rp.PRIMARY_CONFIG, SIMCAL, 0)
    eq_prev = 1.0 + 0.20 * 0.5                                                             # u1 marked at 150 from day 3
    assert s2["counts"]["entered"] == 2 and s2["counts"]["stock_limit_trimmed"] == 0       # wants 20% x 1.1 = 0.22 <= 0.33 - 0.10
    assert s2["final"] == pytest.approx(eq_prev, abs=1e-12)
    s3 = rp.simulate([u1, u2], rp.Config("tight", stock_limit=0.25), SIMCAL, 0)            # room 0.25 x 1.1 - 0.10 = 0.175 < 0.22
    assert s3["counts"]["stock_limit_trimmed"] == 1


def test_sim_marks_to_market_and_sizes_on_the_prior_close():
    t1 = mk(1, 2, 0.01, [(4, rp.ORDER_CLOSE, 1.0, 100.0)], [100, 80, 80, 90, 100])     # 25% position: -20% marked on days 3-4
    t2 = mk(2, 3, 0.05, [(1, rp.ORDER_CLOSE, 1.0, 100.0)], [100, 100])                 # sized on day 2's close (1.0), not day 3's
    sim = rp.simulate([t1, t2], rp.PRIMARY_CONFIG, SIMCAL, 0)
    assert sim["max_dd"] == pytest.approx(0.04, abs=1e-12)                              # 0.20 x 20% of 1.0
    curve = dict(zip(*sim["curve"]))
    assert curve[3] == pytest.approx(0.96)
    t3 = mk(3, 4, 0.10, [(1, rp.ORDER_CLOSE, 1.0, 110.0)], [100, 110])                 # 1% / 10% = 10%, sized on day 3's close 0.96
    sim3 = rp.simulate([t1, t3], rp.PRIMARY_CONFIG, SIMCAL, 0)
    assert sim3["final"] == pytest.approx(1.0 + 0.96 * 0.10 * 0.10, abs=1e-12)


def test_sim_exit_slippage():
    t1 = mk(1, 2, 0.02, [(1, rp.ORDER_CLOSE, 1.0, 110.0)], [100, 110])
    sim = rp.simulate([t1], rp.Config("s", exit_slip=0.001), SIMCAL, 0)
    assert sim["final"] == pytest.approx(1.0 - 0.20 + 0.20 / 100.0 * 110.0 * 0.999, abs=1e-12)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the control draw, the paired bootstrap, the fork, the per-event facts, G8
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_control_draw_same_count_per_day_and_short_day():
    his = {"2020-01-02": 2, "2020-01-03": 3}
    ctl = {"2020-01-02": [f"a{i}" for i in range(10)], "2020-01-03": ["b0", "b1"]}
    ids, c = rp.sample_control(his, ctl, np.random.default_rng(702))
    assert sum(1 for x in ids if x.startswith("a")) == 2 and sorted(x for x in ids if x.startswith("b")) == ["b0", "b1"]
    assert c["dates_short"] == 1 and len(set(ids)) == len(ids)
    ids2, _ = rp.sample_control(his, ctl, np.random.default_rng(702))
    assert ids == ids2                                                # the draw depends only on the seed


def test_control_draw_mix_matched():
    his = {"d": 3}
    ctl = {"d": [("f0", 0), ("f1", 0), ("r0", 1), ("r1", 1), ("r2", 1)]}
    ids, c = rp.sample_control(his, ctl, np.random.default_rng(1), mix={"d": (2, 1)})
    assert sum(1 for x in ids if x.startswith("f")) == 2 and sum(1 for x in ids if x.startswith("r")) == 1
    ids, c = rp.sample_control(his, ctl, np.random.default_rng(1), mix={"d": (3, 0)})     # one first break short -> topped up
    assert len(ids) == 3 and c["mix_topped_up"] == 1


def test_paired_bootstrap_shift_and_identity():
    rng = np.random.default_rng(5)
    a = rng.normal(0, 1, 300)
    months = [f"2020-{1 + i % 12:02d}" for i in range(300)]
    dates = [f"{m}-{1 + (i // 12) % 28:02d}" for i, m in enumerate(months)]
    strat = [i % 2 for i in range(300)]
    d = rp.paired_block_diff(a + 1.0, months, strat, a, months, strat, {0: 0.5, 1: 0.5}, a_date=dates, b_date=dates, draws=300, key="t")
    assert d["weighted"] == pytest.approx(1.0) and d["w_lo"] == pytest.approx(1.0) and d["w_hi"] == pytest.approx(1.0)
    assert d["raw"] == pytest.approx(1.0) and d["dropped_w"] == 0
    assert d["matched"] == pytest.approx(1.0) and d["m_lo"] == pytest.approx(1.0) and d["m_hi"] == pytest.approx(1.0)
    assert d["dropped_m"] == 0 and d["cells_uncovered"] == 0 and d["his_matched"] == 300
    z = rp.paired_block_diff(a, months, strat, a, months, strat, {0: 0.5, 1: 0.5}, a_date=dates, b_date=dates, draws=300, key="t")
    assert z["w_lo"] == pytest.approx(0.0) and z["w_hi"] == pytest.approx(0.0)
    assert z["m_lo"] == pytest.approx(0.0) and z["m_hi"] == pytest.approx(0.0)


def test_date_matched_differs_from_pooled_when_the_control_is_heavy_on_bad_days():
    """His trades equal the control's on EACH day, but the control holds 10 trades on his good day and 100 on his bad day: the pooled
    (and the stratum-only) difference reads a large edge that is only the date mix; the date-matched difference reads zero."""
    a = np.array([2.0, -1.0])
    a_d, b_d = ["2020-01-15", "2020-02-14"], ["2020-01-15"] * 10 + ["2020-02-14"] * 100
    b = np.r_[np.full(10, 2.0), np.full(100, -1.0)]
    d = rp.paired_block_diff(a, [x[:7] for x in a_d], [0, 0], b, [x[:7] for x in b_d], [0] * 110, {0: 1.0, 1: 0.0},
                             a_date=a_d, b_date=b_d, draws=200, key="bad-days")
    pooled = 0.5 - (20.0 - 100.0) / 110.0
    assert d["raw"] == pytest.approx(pooled) and d["weighted"] == pytest.approx(pooled)
    assert d["matched"] == pytest.approx(0.0, abs=1e-12) and d["m_lo"] == pytest.approx(0.0, abs=1e-12)
    assert d["m_hi"] == pytest.approx(0.0, abs=1e-12) and d["w_lo"] < d["w_hi"]          # the pooled one moves with the month draw
    assert abs(d["matched"] - d["raw"]) > 1.0


def test_date_matched_weights_his_counts_and_drops_an_uncovered_cell():
    # cell 1: his [3, 1] (mean 2) vs control [0] -> +2 x 2 trades; cell 2: his [1] vs control [2] -> -1 x 1; cell 3: his [9], NO control
    # (a retrigger cell on a date whose control holds only first breaks) -> dropped and counted
    a = np.array([3.0, 1.0, 1.0, 9.0])
    a_d = ["2020-01-15", "2020-01-15", "2020-02-14", "2020-02-14"]
    a_s = [0, 0, 0, 1]
    b = np.array([0.0, 2.0])
    b_d = ["2020-01-15", "2020-02-14"]
    d = rp.paired_block_diff(a, [x[:7] for x in a_d], a_s, b, [x[:7] for x in b_d], [0, 0], {0: 0.75, 1: 0.25},
                             a_date=a_d, b_date=b_d, draws=200, key="cells")
    assert d["matched"] == pytest.approx((2 * 2.0 + 1 * -1.0) / 3)
    assert d["cells_his"] == 3 and d["cells_uncovered"] == 1 and d["his_uncovered"] == 1 and d["his_matched"] == 3
    # a resample drawing only month 2 holds one covered cell (-1); only month 1, +2: the interval spans both
    assert d["m_lo"] == pytest.approx(-1.0) and d["m_hi"] == pytest.approx(2.0)


def test_paired_bootstrap_reweights_the_control_to_his_mix():
    # his: all first breaks at 1.0; control: first breaks 1.0, retriggers 0.0, mostly retriggers -> raw diff > 0, weighted diff = 0
    a = np.ones(50)
    b = np.r_[np.ones(10), np.zeros(90)]
    ma, mb = ["2020-01"] * 50, ["2020-01"] * 100
    d = rp.paired_block_diff(a, ma, [0] * 50, b, mb, [0] * 10 + [1] * 90, {0: 1.0, 1: 0.0}, draws=50, key="m")
    assert d["weighted"] == pytest.approx(0.0) and d["raw"] == pytest.approx(0.9)


def test_fork_verdict():
    # the curve arm needs >= +50% in 2 of 2017-21 AND at most 5% of the band's draws at or above his final equity
    assert rp.fork_verdict({2020: 0.6, 2021: 0.55}, -0.1, 0.01)[0] == "SELECTION"
    assert rp.fork_verdict({2020: 0.6, 2021: 0.55}, -0.1, 0.05)[0] == "SELECTION"                # at most 5%: 5% still meets it
    v = rp.fork_verdict({2020: 0.6, 2021: 0.55}, -0.1, 0.30)                                    # strong curve, the band at or above it
    assert v[0] == "DATES / market" and v[2] is True and v[3] is False and v[4] is False
    assert rp.fork_verdict({2020: 0.6, 2021: 0.55}, 0.02, 0.30)[0] == "SELECTION"               # ... unless the interval arm is met
    assert rp.fork_verdict({2020: 0.6, 2021: 0.2}, -0.1, 0.0)[0] == "EXECUTION / data"
    assert rp.fork_verdict({2020: 0.1}, 0.05, 1.0)[0] == "SELECTION"
    assert rp.fork_verdict({2020: 0.1}, float("nan"), 0.0)[0] == "EXECUTION / data"
    assert rp.fork_verdict({2022: 0.9, 2023: 0.9}, -1.0, 0.0)[0] == "EXECUTION / data"          # only 2017-21 years count
    with pytest.raises(ValueError):
        rp.fork_verdict({2020: 0.6, 2021: 0.55}, -0.1, float("nan"))                            # an unreadable band is a refusal


def test_qqq_state():
    c = np.r_[np.full(20, 100.0), 105.0]
    assert rp.qqq_state_at(c, 20) == "up"
    assert rp.qqq_state_at(np.r_[np.full(20, 100.0), 95.0], 20) == "down"
    mixed = np.r_[np.full(10, 90.0), np.full(10, 110.0), 101.0]          # above SMA20 (100.05), below SMA10 (109.1)
    assert rp.qqq_state_at(mixed, 20) == "mixed"
    assert rp.qqq_state_at(c, 10) == ""


def test_break_in_rule():
    b = np.array([date(2020, 1, 10).toordinal()])
    lo, hi = date(2020, 1, 10).toordinal(), date(2020, 2, 1).toordinal()
    assert not rp.break_in(b, lo, hi)                                 # dated on the window's first bar: outside
    assert rp.break_in(b, lo - 1, hi) and not rp.break_in(None, lo, hi)


def test_build_events_flags_and_first_of_base():
    ns = SimpleNamespace(name="A", ticker=np.array(["X", "X", "Y", "Z"]), E=np.array(["2020-01-03", "2020-01-08", "2020-01-03", "2020-01-03"]),
                         D=np.array(["2020-01-02", "2020-01-07", "2020-01-02", "2020-01-02"]), base_id=np.array(["X|1", "X|1", "Y|1", "Z|1"]),
                         retrigger=np.array([0, 1, 0, 0]), pivot=np.ones(4), adr20=np.full(4, 0.05),
                         cls={"pos": np.array([1, 1, 0, 0], bool), "neg": np.array([0, 0, 1, 1], bool), "post": np.array([0, 0, 0, 1], bool),
                              "strict": np.array([0, 1, 0, 0], bool)})
    evs = rp.build_events({"A": ns})
    by = {(e.ticker, e.E): e for e in evs}
    assert by[("X", "2020-01-03")].first_of_base and not by[("X", "2020-01-08")].first_of_base
    assert by[("X", "2020-01-08")].strict and by[("Z", "2020-01-03")].post and by[("Z", "2020-01-03")].ctl


def test_tail_stats_rates_and_event_denominator():
    st = rp.tail_stats([12.0, 6.0, -1.0, -1.0], n_events=8)
    assert st["ge5"] == 50.0 and st["ge10"] == 25.0 and st["ge20"] == 0.0 and st["ge10_ev"] == 12.5
    assert st["max"] == 12.0 and st["worst"] == -1.0 and st["win"] == 0.5 and st["mean_ev"] == pytest.approx(16.0 / 8)


def test_g8_file_runs_through_trade_impact(tmp_path):
    """The real trade_impact.py on a synthetic export / flags / trade list in the `--kind r1` shape this module writes."""
    exp = tmp_path / "x.csv.gz"
    write_export(exp, filler_rows("SPY", 300.0) + hhh_rows())
    flags = tmp_path / "f.tsv"
    flags.write_text("check\tklass\tticker\tdate\tliquid\tgapn\tprev_close\topen\tclose\tgo\trc\tc1_over_pc\tc5_over_pc\tv_ratio_20\tdv20_prior\textra\n"
                     f"gap\tpersistent\tHHH\t{CAL[E_IDX + 2]}\t1\t1\t1\t1\t1\t0\t0.1\t1\t1\t1\t1\t\n")
    tr = tmp_path / "g8.tsv"
    rp.write_g8_file(str(tr), [("p33_s3_t10", "HHH", CAL[E_IDX].isoformat(), 8, 5.2), ("p33_s3_t10", "HHH", CAL[-3].isoformat(), 8, -1.0),
                               ("pp", "HHH", CAL[E_IDX].isoformat(), 8, 1.0)])
    res = subprocess.run([sys.executable, rp.TRADE_IMPACT, "--flags", str(flags), "--export", str(exp), "--trades", str(tr), "--label", "T",
                          "--kind", "r1", "--cell", "p33_s3_t10", "--cutoff", "2024-12-31"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert rp.parse_g8(res.stdout) == (0, 1)                          # the second trade's hold runs past the last bar
    with pytest.raises(ValueError):
        rp.parse_g8("nothing here")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_freeze_missing_and_doc_body_hash(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text("# body\n\n<!-- FREEZE -->\n- a: aaa\n")
    p = {"a": "aaa", "b": "bbb", "doc_body": rp.doc_body_sha(str(doc))}
    assert rp.freeze_missing(str(doc), p) == ["b", "doc_body"]
    doc.write_text(f"# body\n\n<!-- FREEZE -->\n- a: aaa\n- b: bbb\n- doc_body: {p['doc_body']}\n")
    assert rp.freeze_missing(str(doc), {**p, "doc_body": rp.doc_body_sha(str(doc))}) == []
    doc.write_text(f"# body EDITED\n\n<!-- FREEZE -->\n- a: aaa\n- b: bbb\n- doc_body: {p['doc_body']}\n")
    assert rp.freeze_missing(str(doc), {**p, "doc_body": rp.doc_body_sha(str(doc))}) == ["doc_body"]
    nomark = tmp_path / "n.md"
    nomark.write_text("no marker")
    assert rp.freeze_missing(str(nomark), {"a": "aaa"}) == ["a"]


@pytest.fixture()
def lock_sandbox(tmp_path, monkeypatch):
    f = tmp_path / "input.txt"
    f.write_text("x")
    doc = tmp_path / "doc.md"
    monkeypatch.setattr(rp, "FILES", {"inp": str(f)})
    monkeypatch.setattr(rp, "CODE", {})
    monkeypatch.setattr(rp, "PINNED", {"inp": rp.sha(str(f))})
    monkeypatch.setattr(rp, "DOC", str(doc))
    monkeypatch.setattr(rp, "PRINTOUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(rp, "DRY_PRINTOUT", str(tmp_path / "dry.txt"))
    monkeypatch.setattr(rp, "STOPPED", str(tmp_path / "stopped.txt"))
    monkeypatch.setattr(rp, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(rp, "load_all", lambda say, dry: {"evs": [], "dB": {"not_discovery": 0, "dated_after_cut": 0}, "doneB_dropped": 0,
                                                          "guards": {"A": {}, "B": {}}, "guard_A_equal": True})
    monkeypatch.setattr(rp, "describe_population", lambda say, S: None)
    monkeypatch.setitem(rp.FILES, "verdict_A", str(f))
    ran = []
    monkeypatch.setattr(rp, "run_replay", lambda S, say: ran.append(1))
    return SimpleNamespace(doc=doc, f=f, ran=ran, tmp=tmp_path)


def test_real_run_refuses_until_frozen_then_runs(lock_sandbox):
    sb = lock_sandbox
    sb.doc.write_text("# registration\n\n<!-- FREEZE -->\n")
    assert rp.main([]) == 2 and not sb.ran                           # nothing under the marker
    p = rp.pins({"A": [], "B": []})
    sb.doc.write_text("# registration\n\n<!-- FREEZE -->\n" + "".join(f"- {k}: {v}\n" for k, v in p.items()))
    assert rp.main(["--dry-run"]) == 0 and not sb.ran
    assert rp.main([]) == 0 and sb.ran == [1]
    os.remove(rp.PRINTOUT)


def test_real_run_refuses_a_doc_edited_after_the_pin(lock_sandbox):
    sb = lock_sandbox
    sb.doc.write_text("# registration\n\n<!-- FREEZE -->\n")
    p = rp.pins({"A": [], "B": []})
    sb.doc.write_text("# registration, EDITED after the pin\n\n<!-- FREEZE -->\n" + "".join(f"- {k}: {v}\n" for k, v in p.items()))
    assert rp.main([]) == 2 and not sb.ran


def test_real_run_refuses_when_an_output_exists(lock_sandbox):
    sb = lock_sandbox
    Path(rp.PRINTOUT).write_text("already ran")
    assert rp.main([]) == 2 and not sb.ran
    os.remove(rp.PRINTOUT)
    os.makedirs(rp.OUT_DIR, exist_ok=True)
    Path(rp.OUT_DIR, "trades.tsv.gz").write_text("x")
    assert rp.main([]) == 2 and not sb.ran


def test_real_run_refuses_on_pinned_input_drift(lock_sandbox):
    sb = lock_sandbox
    sb.f.write_text("changed")
    assert rp.main(["--dry-run"]) == 2 and not sb.ran


def test_entry_slippage_is_pinned_and_asserted(monkeypatch, tmp_path):
    """constants.py (ENTRY_SLIPPAGE_PCT, the default every fill pays) is in the freeze lock, and the 0.1% is asserted at import."""
    assert rp.CODE["constants"].endswith(os.path.join("agents", "market_intelligence", "constants.py"))
    assert os.path.exists(rp.CODE["constants"])
    assert cb.ENTRY_SLIPPAGE_PCT == 0.001
    import inspect
    assert inspect.signature(cb.entry_variants).parameters["slippage"].default == 0.001
    doc = tmp_path / "d.md"
    doc.write_text("x\n<!-- FREEZE -->\n")
    monkeypatch.setattr(rp, "FILES", {})
    monkeypatch.setattr(rp, "CODE", {"constants": rp.CODE["constants"]})
    assert rp.pins({}, doc=str(doc))["constants"] == rp.sha(rp.CODE["constants"])


def test_no_forward_column_on_any_read_list():
    assert not (rp.FORBIDDEN & (set(rp.LJ_COLS) | set(rp.ME_COLS) | set(rp.CAND_COLS)))
    assert "r1_status" not in rp.ME_COLS and "r2" not in rp.ME_COLS


# ═════════════════════════════════════════════════════════════════════════════════════════════
# end to end: the real-run path on the hand-built world (the run that happens once must not crash)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_run_replay_end_to_end_on_synthetic_world(world, tmp_path, monkeypatch):
    D = world.D
    E = CAL[E_IDX].isoformat()
    mdir = tmp_path / "minutes"
    mdir.mkdir()
    lines = [f"HHH|{m}|{o}|{h}|{l}|{c}|100" for m, o, h, l, c in hhh_minutes()]
    for tk, px in (("AAA", 20.0), ("BBB", 30.0)):                    # control: flat stocks whose ORH5 never triggers or abstains
        lines += [f"{tk}|{m}|{px}|{px * 1.01}|{px * 0.99}|{px}|100" for m in range(390)]
    with gzip.open(mdir / f"{E}.psv.gz", "wt") as fh:
        fh.write("\n".join(lines) + "\n")
    flags = tmp_path / "flags.tsv"
    flags.write_text("check\tklass\tticker\tdate\n")
    monkeypatch.setitem(rp.FILES, "flags_A", str(flags))
    monkeypatch.setattr(rp, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(rp, "BAND_DRAWS", 3)
    monkeypatch.setattr(rp, "run_g8", lambda era, path, out: (0, 0))
    evs = [hhh_event(), rp.Event(era="A", ticker="AAA", D=CAL[E_IDX - 1].isoformat(), E=E, base_id="AAA|1", retrigger=0, pivot=20.1,
                                 adr20=0.05, ctl=True, year=CAL[E_IDX].year, month=E[:7], minutes_state="ok"),
           rp.Event(era="A", ticker="BBB", D=CAL[E_IDX - 1].isoformat(), E=E, base_id="BBB|1", retrigger=1, pivot=29.0, adr20=0.05,
                    ctl=True, year=CAL[E_IDX].year, month=E[:7], minutes_state="ok")]
    evs[0].first_of_base = True
    evs[0].strict = True                                              # the strictly-before beside path runs too
    DB, _ = rp.load_daily_subset(str(world.path), keep={"QQQ"})
    S = {"evs": evs, "Ds": {"A": D, "B": DB}, "files": {"A": {E: mdir / f"{E}.psv.gz"}, "B": {}}, "guards": {"A": {}, "B": {}},
         "eras": {"A": SimpleNamespace(ticker=np.array(["HHH", "AAA", "BBB"]), base_id=np.array(["HHH|2019-12-01", "AAA|1", "BBB|1"]),
                                       E=np.array([E, E, E]))}}
    say = rp.Say()
    rp.run_replay(S, say)
    text = "\n".join(say.lines)
    assert "THE FORK" in text and "ACCOUNT CURVE" in text and "CONTROL BAND" in text
    assert "DATE-MATCHED" in text and "BESIDE (decides nothing): both arms on the 1 strictly-before calls" in text
    assert "max drawdown (higher = WORSE)" in text and "filled walks NOT mature" in text
    t = pd.read_csv(tmp_path / "out" / "trades.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
    row = t[(t.ticker == "HHH") & (t.variant == "orh5") & (t.arm == "p33_s3_t10")]
    assert len(row) == 1 and float(row.realized_r.iloc[0]) == pytest.approx(expected_hhh_r(), rel=1e-9)
    assert set(t[t.ticker == "BBB"].entry_status) <= {"no_trigger", "abstain"}
    acc = pd.read_csv(tmp_path / "out" / "account_his.tsv", sep="\t")
    prim = acc[acc.config == "primary"]
    fill = 10.05 * 1.001
    width = (fill - 9.95) / fill
    pos = min(0.01 / width, 0.20)                                     # his sizing: 1% risk, 20% cap (cap-bound here)
    want = 1.0 + pos * ((10.90 / fill - 1) / 3 + (10.50 / fill - 1) * 2 / 3)
    assert prim.equity.iloc[-1] == pytest.approx(want, rel=1e-9)
