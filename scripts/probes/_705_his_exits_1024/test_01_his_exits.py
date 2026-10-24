"""Synthetic tests for 01_his_exits.py: walk_x's parity with cb.walk_exit on the plain trail, its leg kinds and statuses (so the frozen
`make_trade` / `simulate` accept them), each custom shape (gap-down at the open, big up day / extension at the close, the below-fill cut,
the time stop, the breakeven move), the registered rules all build, the marker / CHOSEN parsing, and the description's `rel` / `bucket`.
No real data file is opened except the registration doc (its marker line) when it exists."""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_705_his_exits01", os.path.join(HERE, "01_his_exits.py"))
M = importlib.util.module_from_spec(spec)
sys.modules["_705_his_exits01"] = M
spec.loader.exec_module(M)
rp, cb = M.rp, M.cb


def bars(n, start="2020-01-02", o=None, h=None, l=None, c=None):
    dates = [d.date() for d in pd.bdate_range(start, periods=n)]
    c = np.asarray(c if c is not None else 10.0 + 0.01 * np.arange(n), dtype=float)
    o = np.asarray(o if o is not None else c, dtype=float)
    h = np.asarray(h if h is not None else np.maximum(o, c) * 1.01, dtype=float)
    l = np.asarray(l if l is not None else np.minimum(o, c) * 0.99, dtype=float)
    return cb.daily_bars_from_arrays(dates, o, h, l, c, np.ones(n) * 1e6)


def entry(fill=10.0, stop=9.5, stopped=False):
    return {"status": "filled", "fill": fill, "stop": stop, "fill_minute": 7, "day0": {"stopped": stopped, "exit_price": (9.4 if stopped else None), "exit_minute": (30 if stopped else None)}}


def random_world(seed, n=140):
    rng = np.random.default_rng(seed)
    c = 10.0 * np.exp(np.cumsum(rng.normal(0.002, 0.03, n)))
    o = c * np.exp(rng.normal(0, 0.01, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.01, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.01, n)))
    return bars(n, o=o, h=h, l=l, c=c)


@pytest.mark.parametrize("seed", range(40))
def test_walk_x_plain_trail_equals_cb_walk_exit(seed):
    b = random_world(seed)
    e = 25
    fill = float(b.c[e]) * 1.001
    stop = float(b.l[e])
    en = entry(fill, stop)
    fwd = b.slice(e + 1, e + 2 + M.HORIZON)
    for k in (10, 20):
        arm = cb.Arm(f"t{k}", "qm", 0.0, None, k)
        a = cb.walk_exit(fill=fill, stop=stop, closes_before=b.c[:e + 1], fwd=fwd, arm=arm, adr20=0.05, horizon=M.HORIZON)
        x = M.walk_x(en, closes_before=b.c[:e + 1], fwd=fwd, adr20=0.05, rule=M.XRule("x", trail_n=k), horizon=M.HORIZON)
        assert a["status"] == x["status"]
        assert abs(a["realized_r"] - x["realized_r"]) < 1e-9
        assert a["sessions_held"] == x["sessions_held"]
        la = [(s, kd, px, f) for s, kd, px, f in a["events"] if kd in rp.SELL_KINDS]
        lx = [(s, kd, px, f) for s, kd, px, f in x["events"] if kd in rp.SELL_KINDS]
        assert la == lx


def test_walk_x_legs_are_sell_kinds_and_statuses_mature():
    b = random_world(7, n=60)
    e = 25
    fill, stop = float(b.c[e]) * 1.001, float(b.l[e])
    fwd = b.slice(e + 1, e + 2 + M.HORIZON)
    for rule in M.X_RULES.values():
        x = M.walk_x(entry(fill, stop), closes_before=b.c[:e + 1], fwd=fwd, adr20=0.05, rule=rule)
        sell = [ev for ev in x["events"] if ev[3] > 0]
        assert sell and all(ev[1] in rp.SELL_KINDS for ev in sell)
        assert abs(sum(ev[3] for ev in sell) - 1.0) < 1e-9
        assert x["status"] in cb.TERMINAL_STATUSES or x["status"] in ("censored", "degraded")
        tags = [ev for ev in x["events"] if str(ev[1]).startswith("x_")]
        assert all(ev[3] == 0.0 for ev in tags)


def test_day0_stop_is_the_entrys_own():
    b = random_world(3, n=60)
    e = 25
    x = M.walk_x(entry(10.0, 9.5, stopped=True), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, e + 50), adr20=0.05, rule=M.XRule("x", trail_n=20))
    assert x["status"] == "stopped_day0" and x["events"][0][1] in ("day0_stop", "day0_gap") and x["sessions_held"] == 0


def test_gapdown_sells_at_the_open_as_an_open_leg():
    n = 40
    c = np.full(n, 10.0)
    o = c.copy()
    c[31] = 10.5                                   # session 1 (e = 30) closes 10.5
    o[32] = 10.5 * (1 - 0.5 * 0.06) - 0.01         # session 2 opens more than half an ADR20 (6%) under the prior close
    c[32] = 10.3
    b = bars(n, o=o, c=c, h=np.maximum(o, c) + 0.2, l=np.minimum(o, c) - 0.05)
    e = 30
    fill, stop = 10.05, 9.0
    x = M.walk_x(entry(fill, stop), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, n), adr20=0.06, rule=M.XRule("x", trail_n=20, gap_x=0.5))
    assert x["status"] == "time_exit" and x["sessions_held"] == 2
    tag = [ev for ev in x["events"] if ev[1] == "x_gapdown"]
    leg = [ev for ev in x["events"] if ev[1] == "stop_gap"]
    assert tag and leg and abs(leg[0][2] - o[32]) < 1e-12
    assert abs(x["realized_r"] - (o[32] - fill) / (fill - stop)) < 1e-12
    # legs_of books it at the OPEN (order 0) because the price equals the session's open
    cidx = np.arange(n, dtype=np.int64)
    legs = rp.legs_of(x["events"], b, cidx, e)
    assert len(legs) == 1 and legs[0][1] == rp.ORDER_OPEN and legs[0][4] == "stop_gap"


def test_upday_extension_belowfill_time_and_breakeven():
    n = 60
    e = 30
    c = np.full(n, 10.0)
    c[31] = 10.0 * (1 + 1.5 * 0.05) + 0.01         # a big up day on session 1
    b = bars(n, c=c)
    x = M.walk_x(entry(10.05, 9.5), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, n), adr20=0.05, rule=M.XRule("x", trail_n=10, up_x=1.5))
    assert x["status"] == "time_exit" and x["sessions_held"] == 1 and any(ev[1] == "x_upday" for ev in x["events"])
    # extension: a close 2 ADR over its 10-day
    c = np.full(n, 10.0)
    c[33] = 10.0 * (1 + 2 * 0.05) * 1.02
    b = bars(n, c=c)
    x = M.walk_x(entry(10.05, 9.5), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, n), adr20=0.05, rule=M.XRule("x", trail_n=20, ext_x=2.0))
    assert x["status"] == "time_exit" and x["sessions_held"] == 3 and any(ev[1] == "x_extension" for ev in x["events"])
    # below fill within 3 sessions: session 2 closes under the fill
    c = np.full(n, 10.2)
    c[32] = 10.0
    b = bars(n, c=c, l=c - 0.05, h=c + 0.05)
    x = M.walk_x(entry(10.05, 9.5), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, n), adr20=0.05, rule=M.XRule("x", trail_n=10, below_fill_n=3))
    assert x["status"] == "time_exit" and x["sessions_held"] == 2 and any(ev[1] == "x_belowfill" for ev in x["events"])
    # the same close on session 4 is NOT cut (n = 3)
    c = np.full(n, 10.2)
    c[34] = 10.0
    b = bars(n, c=c, l=c - 0.05, h=c + 0.05)
    x = M.walk_x(entry(10.05, 9.5), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, n), adr20=0.05, rule=M.XRule("x", trail_n=10, below_fill_n=3))
    assert not any(ev[1] == "x_belowfill" for ev in x["events"])
    # time stop at session 5, flat prices
    b = bars(n, c=np.full(n, 10.2), l=np.full(n, 10.1), h=np.full(n, 10.3))
    x = M.walk_x(entry(10.05, 9.5), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, n), adr20=0.05, rule=M.XRule("x", time_n=5))
    assert x["status"] == "time_exit" and x["sessions_held"] == 5 and x["events"][-1][1] == "cut"
    # breakeven after +1R: a high at fill + R on session 1, then a dip to the fill - 0.01 on session 3 stops at the fill
    fill, stop = 10.0, 9.5
    c = 10.3 + 0.001 * np.arange(n)                # rising, so the 20-day trail never fires
    h = c + 0.05
    l = c - 0.05
    h[31] = 10.6                                   # +1R = 10.5 reached on session 1
    l[33] = 9.99                                   # session 3 dips under the fill (not under the original stop)
    b = bars(n, c=c, h=h, l=l)
    x = M.walk_x(entry(fill, stop), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, n), adr20=0.05, rule=M.XRule("x", trail_n=20, be_after_r=1.0))
    assert x["status"] == "stopped" and x["sessions_held"] == 3 and abs(x["realized_r"]) < 1e-12


def test_time_unless_r_spares_a_trade_that_reached_the_level():
    n = 60
    e = 30
    fill, stop = 10.0, 9.5
    c = 10.3 + 0.001 * np.arange(n)
    h = c + 0.05
    l = c - 0.05
    b = bars(n, c=c, h=h, l=l)
    rule = M.XRule("x", trail_n=10, time_n=5, time_unless_r=2.0)
    # never reaches +2R (11.0): sold at the close of session 5
    x = M.walk_x(entry(fill, stop), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, n), adr20=0.05, rule=rule)
    assert x["status"] == "time_exit" and x["sessions_held"] == 5 and any(ev[1] == "x_time" for ev in x["events"])
    # a session-2 high at +2R: kept, and the rising closes never break the 10-day -> censored at the horizon / degraded at the data's end
    h2 = h.copy()
    h2[32] = 11.0
    b2 = bars(n, c=c, h=h2, l=l)
    x = M.walk_x(entry(fill, stop), closes_before=b2.c[:e + 1], fwd=b2.slice(e + 1, n), adr20=0.05, rule=rule)
    assert x["status"] == "degraded" and x["sessions_held"] == n - e - 1 and not any(ev[1] == "x_time" for ev in x["events"])
    # the day-0 peak counts as reached
    x = M.walk_x(entry(fill, stop), closes_before=b.c[:e + 1], fwd=b.slice(e + 1, n), adr20=0.05, rule=rule, day0_peak=11.0)
    assert not any(ev[1] == "x_time" for ev in x["events"])


def test_registered_rules_build_and_tags():
    assert set(M.RULES) == set(M.S_RULES) | set(M.B_RULES)
    assert all(M.RULE_TAG[k] == "S" for k in M.S_RULES) and all(M.RULE_TAG[k] == "B" for k in M.B_RULES)
    assert 3 <= len(M.RULES) <= 6
    assert M.ALL_ARMS[M.SPEED_ARM].trail_mode == "speed" and M.ALL_ARMS[M.SPEED_ARM].partial_session == 3
    s3 = M.RULES["S3_c3_p33_tspd_cut3"]
    assert s3.stall_cut_session == 3 and s3.stall_cut_r == 1.0 and s3.partial_trigger == "combo" and s3.trail_mode == "speed"
    assert M.RULES["S1_r2_p33_tspd"].partial_trigger == "r_target" and M.RULES["S1_r2_p33_tspd"].partial_r == 2.0
    assert M.RULES["S2_hold_t20"].partial_frac == 0.0 and M.RULES["S2_hold_t20"].trail_sma == 20
    assert M.RULES["S4_d3profit_p33_tspd"].partial_if_profit and M.RULES["S4_d3profit_p33_tspd"].trail_mode == "speed"


def test_fixed_time_stop_arm_marks_at_the_session_close():
    b = bars(60, c=np.full(60, 10.2), l=np.full(60, 10.1), h=np.full(60, 10.3))
    e = 30
    arm = cb.Arm("t5", "fixed", target_r=1e9, max_sessions=5)
    r = cb.walk_exit(fill=10.05, stop=9.5, closes_before=b.c[:e + 1], fwd=b.slice(e + 1, 60), arm=arm, adr20=0.05, horizon=M.HORIZON)
    assert r["status"] == "time_exit" and r["sessions_held"] == 5 and cb.is_mature(r["status"], 29, M.HORIZON)


def test_rel_and_bucket():
    assert M.rel(None, 2, 4) == "never" and M.rel(1, 2, 4) == "before" and M.rel(2, 2, 4) == "within" and M.rel(4, 2, 4) == "within" and M.rel(5, 2, 4) == "after"
    assert M.bucket(0) == "0 (E itself)" and M.bucket(2) == "1-2" and M.bucket(5) == "3-5" and M.bucket(10) == "6-10" and M.bucket(20) == "11-20" and M.bucket(21) == ">20"
    assert M.bucket(None) == "still held"


def test_marker_and_chosen_parsing(tmp_path, monkeypatch):
    doc = tmp_path / "doc.md"
    doc.write_text("# x\n\nCHOSEN: S2_hold_t20 (recovery +0.4)\n\n" + M.FREEZE_MARKER + "\n\n- a: 1\n")
    monkeypatch.setattr(M, "DOC", str(doc))
    assert M.marker_ok(doc.read_text())
    assert M.chosen_from_doc() == "S2_hold_t20"
    doc.write_text("# x\n\n" + M.FREEZE_MARKER + "\n\nCHOSEN: S2_hold_t20\n")      # below the marker does not count
    assert M.chosen_from_doc() is None
    doc.write_text("# x\n\nCHOSEN: none\n\nthe marker `" + M.FREEZE_MARKER + "` in prose\n" + M.FREEZE_MARKER + "\n")
    assert not M.marker_ok(doc.read_text())


def test_doc_has_exactly_one_marker_line():
    if not os.path.exists(M.DOC):
        pytest.skip("registration not written yet")
    assert M.marker_ok(open(M.DOC).read())
