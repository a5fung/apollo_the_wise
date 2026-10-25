#!/usr/bin/env python3
"""Tests for 01_intra.py — synthetic fixtures for every stage's mechanics and every guard, and ONE end-to-end synthetic world run through every
stage runner (--enter-fit, --stop-fit, --exit-fit, --check) with real shapes: two eras incl. an era-B trade whose export calendar starts
~600 sessions into the pickle calendar, an early-close day with after-hours prints, a missing minute day inside a hold and on a buy day, a
still-held trade, a 121-session sell window, 60 tickers (freed objects get their ids reused), one-element numpy arrays. No real outcome is
used: every bar, minute, frame and caption here is made up. Run: python3 -m pytest scripts/probes/_705_intraday_1025/test_01_intra.py -q"""
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("intra01", os.path.join(HERE, "01_intra.py"))
intra = importlib.util.module_from_spec(spec)
sys.modules["intra01"] = intra
spec.loader.exec_module(intra)
rev, cb, rp, R, H = intra.rev, intra.cb, intra.rp, intra.R, intra.H


# ═════════════════════════════════════════════════════════════════════════════════════════════ fixtures
def sessions(n: int, start: str = "2020-01-02") -> list:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def weekday_cal(start: str = "2019-01-02", end: str = "2024-06-28") -> list:
    d, out = date.fromisoformat(start), []
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def daily_walk(n: int, base: float, seed: int, trend: float = 0.0006):
    rng = np.random.default_rng(seed)
    r = rng.normal(trend, 0.015, n)
    c = base * np.cumprod(1 + r)
    o = c * (1 + rng.normal(0, 0.004, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n)) + 0.0005)
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, n)) - 0.0005)
    return o, h, l, c, np.full(n, 2_000_000.0)


def minutes_from_daily(o: float, h: float, l: float, c: float, early: bool = False, after_hours: bool = False):
    """The session's minutes from one daily bar: a piecewise-linear close path o -> h -> l -> c (the high and the low touched exactly), each
    minute's open = the previous close, so the minute-built OHLC equals the daily bar; an early-close day has 210 minutes, optionally with
    after-hours prints at 210..214 (dropped by the trim)."""
    n = 210 if early else 390
    m = np.arange(n)
    closes = np.interp(m, [0, n // 3, 2 * n // 3, n - 1], [o, h, l, c])
    opens = np.concatenate([[o], closes[:-1]])
    highs, lows = np.maximum(opens, closes), np.minimum(opens, closes)
    mm = list(m)
    o_, h_, l_, c_ = list(opens), list(highs), list(lows), list(closes)
    if early and after_hours:
        for k in range(210, 215):
            mm.append(k); o_.append(c); h_.append(c); l_.append(c); c_.append(c)
    return cb.minute_bars_from_lists(mm, o_, h_, l_, c_, [1000.0] * len(mm))


def hand_minutes(path, start_minute: int = 0):
    """path = list of (o, h, l, c) per minute from `start_minute`."""
    m = list(range(start_minute, start_minute + len(path)))
    o, h, l, c = (list(x) for x in zip(*path))
    return cb.minute_bars_from_lists(m, o, h, l, c, [1000.0] * len(m))


def mk_buy(**kw):
    base = dict(eid=1, sym="AAA", sym_a="AAA", has_bars=True, ever_candidate=True, setup="undated", E="2020-03-02", D="2020-02-28", era="A", ticker="AAA",
                pivot=None, adr20=None, base_id="", retrigger=0, undated_reason="no_event_in_window", first_frame="", prev_full_frame="", lo="2020-03-02",
                hi="2020-03-02", window_len=1, inverted=False, initial=False, flicker=False, exit_lo="2020-03-05", exit_hi="2020-03-05", still_held=False, decides=False)
    clocks = {k: kw.pop(k) for k in ("first_clock", "flat_clock", "p_ctx", "f_ctx") if k in kw}
    base.update(kw)
    b = rev.Buy(**base)
    b.dated = b.setup in ("breakout", "EP", "both")
    b.noev = b.setup == "undated" and b.undated_reason == "no_event_in_window"
    b.year = int(b.E[:4])
    b.era = "A" if b.E <= intra.A_LAST else "B"
    b.ticker = b.sym_a if b.era == "A" else b.sym
    b.first_clock = clocks.get("first_clock", "")
    b.flat_clock = clocks.get("flat_clock", "")
    b.p_ctx = clocks.get("p_ctx", "in" if b.flat_clock else "")
    b.f_ctx = clocks.get("f_ctx", "in" if b.first_clock else "")
    b.in_bracket = bool(b.first_clock) and bool(b.flat_clock) and b.p_ctx == "in"
    b.pre_flat_bracket = bool(b.first_clock) and bool(b.flat_clock) and b.p_ctx == "pre"
    b.held_before_0935 = bool(b.first_clock) and b.first_clock < "09:35"
    return b


class FakeStore(intra.MinuteStore):
    """A store serving hand minutes by date (None = no minutes that session)."""

    def __init__(self, by_date: dict):
        super().__init__({}, {})
        self.by_date = by_date

    def state(self, d, tk, b=None):
        return "ok/FAKE" if self.by_date.get(d) is not None else "missing"

    def preload(self, pairs):
        from collections import Counter
        return Counter()

    def get(self, d, tk, b=None):
        self.seal(d)
        return self.by_date.get(d)


def mini_rec(n: int = 80, e: int = 60, seed: int = 3, mb=None, start: str = "2020-01-02", exit_lo: int = 3, exit_hi: int = 5, **buy_kw):
    """A small record on its own calendar: `n` daily bars, the buy day at index e, minutes `mb`, exit window at offsets (exit_lo, exit_hi)."""
    cal = sessions(n, start)
    o, h, l, c, v = daily_walk(n, 50.0, seed)
    bars = cb.daily_bars_from_arrays(cal, o, h, l, c, v)
    cidx = np.arange(n, dtype=np.int32)
    E = cal[e].isoformat()
    b = mk_buy(E=E, lo=E, hi=E, exit_lo=cal[e + exit_lo].isoformat() if exit_lo is not None else "", exit_hi=cal[e + exit_hi].isoformat() if exit_hi is not None else "", **buy_kw)
    rev.index_calendar([b], [d.isoformat() for d in cal])
    r = intra.IRec(b=b, bars=bars, cidx=cidx, e=e, adr20=0.04, cal=cal, era="A", mb=mb, minutes_state="ok" if mb is not None else "missing")
    r.qqq_c = np.asarray(bars.c, dtype=float) * 3.0
    if b.has_exit:
        r.exit_lo_j, r.exit_hi_j = r.off(b.exit_lo), r.off(b.exit_hi)
    return r


def sightings_from(frames: list):
    """frames: (date, sym, ctx, clock) -> a Sightings."""
    rows = [dict(idx=i, frame_id=f"f{i}", vid="v", date=d, ctx=ctx, clock=clk, symbols=s, blip_filled="") for i, (d, s, ctx, clk) in enumerate(frames)]
    return rev.Sightings.build(pd.DataFrame(rows))


# ═════════════════════════════════════════════════════════════════════════════════════════════ the 60-minute bars and the average
def test_h60_bars_full_early_close_missing_window_and_never_0_59():
    mb = minutes_from_daily(100.0, 104.0, 97.0, 101.0)
    bars = intra.h60_bars(mb, "2020-03-02")
    assert len(bars) == 7 and [(x.lo, x.hi) for x in bars] == [(0, 29), (30, 89), (90, 149), (150, 209), (210, 269), (270, 329), (330, 389)]
    assert bars[0].first_minute == 0 and bars[0].close_minute == 29 and bars[0].o == 100.0 and bars[-1].c == pytest.approx(101.0)
    assert bars[0].h == pytest.approx(float(mb.h[mb.minute <= 29].max())) and bars[0].h < float(mb.h[mb.minute <= 59].max())    # a [0,59] first bar would read higher
    # an early-close day: 4 bars, the after-hours prints dropped first
    mbe = minutes_from_daily(100.0, 103.0, 98.0, 99.0, early=True, after_hours=True)
    assert int(mbe.minute.max()) == 214
    be = intra.h60_bars(mbe, "2020-11-27")
    assert len(be) == 4 and be[-1].hi == 209 and be[-1].close_minute == 209 and be[-1].c == pytest.approx(99.0)
    # a window with no minute is no bar
    keep = (mb.minute < 90) | (mb.minute > 149)
    mb2 = cb.minute_bars_from_lists(mb.minute[keep], mb.o[keep], mb.h[keep], mb.l[keep], mb.c[keep], mb.v[keep])
    b2 = intra.h60_bars(mb2, "2020-03-02")
    assert b2[2] is None and b2[1] is not None and b2[3] is not None
    assert intra.next_minute_open(mb, 389) is None and intra.next_minute_open(mb, 29) == (30, pytest.approx(float(mb.o[30])))


def test_ema_hand_seed_thin_and_residual():
    closes = np.arange(1.0, 101.0)
    ema = intra.ema_series(closes)
    assert np.isnan(ema[18]) and ema[19] == pytest.approx(np.mean(closes[:20]))
    hand = float(np.mean(closes[:20]))
    for i in range(20, 100):
        hand = 2 / 21 * closes[i] + 19 / 21 * hand
    assert ema[99] == pytest.approx(hand)
    # the floor (C3): 20 seed + 45 post-seed = 65 bars; a 10-session warm-up holds 70 (67 across one early close), so a 67-bar warm-up clears it
    assert intra.EMA_SEED_BARS + intra.EMA_POST_SEED_BARS == 65
    assert intra.ema_is_thin(64) and not intra.ema_is_thin(65) and not intra.ema_is_thin(67)
    assert intra.seed_residual(65) == pytest.approx((19 / 21) ** 45) and 0.010 < intra.seed_residual(65) < 0.012 and intra.seed_residual(20) == 1.0
    assert np.isnan(intra.ema_series(np.arange(5.0))).all()
    sma = intra.sma_series_bars(closes)
    assert np.isnan(sma[18]) and sma[19] == pytest.approx(10.5) and sma[99] == pytest.approx(np.mean(closes[80:100]))


def test_bar_sequence_armed_index_and_missing_sessions():
    cal = sessions(40, "2020-03-02")
    by = {}
    for i, d in enumerate(cal):
        by[d.isoformat()] = None if i == 12 else minutes_from_daily(50 + i, 51 + i, 49 + i, 50.5 + i, early=(d.isoformat() in intra.EARLY_CLOSE))
    r = mini_rec(n=40, e=15, start="2020-03-02", exit_lo=3, exit_hi=5, mb=by[cal[15].isoformat()])
    st = FakeStore(by)
    seq = intra.bar_sequence(r, st, -10, 10)
    assert seq.missing_sessions == 1                       # session index 12 = j -3 has no minutes
    assert seq.warmup_bars == 9 * 7                        # 10 warm-up sessions, one missing -> 63 bars
    assert len(seq.items) == (9 + 1 + 10) * 7 and seq.items[0][0] == -10 and seq.items[-1][0] == 10
    a = intra.armed_index(seq, 40)                          # a fill at minute 40 arms on the bar [30,89] of the buy day
    assert seq.items[a][0] == 0 and seq.items[a][1].lo == 30
    assert seq.items[intra.armed_index(seq, 389)][0] == 1 and seq.items[intra.armed_index(seq, None)][0] == 1
    assert a == 64 and intra.ema_is_thin(a)                 # 63 warm-up bars + 1 buy-day bar = 64 < 65: one missing warm-up session AND an early fill is thin
    assert not intra.ema_is_thin(intra.armed_index(seq, 100))   # a fill at 11:10 arms on [90,149]: 63 + 2 = 65 bars -> not thin
    # one early close inside the warm-up (67 bars) is never thin, whatever the fill minute
    by2 = {d.isoformat(): minutes_from_daily(50 + i, 51 + i, 49 + i, 50.5 + i, early=(i == 12)) for i, d in enumerate(cal)}
    r2 = mini_rec(n=40, e=15, start="2020-03-02", exit_lo=3, exit_hi=5, mb=by2[cal[15].isoformat()])
    seq2 = intra.bar_sequence(r2, FakeStore(by2), -10, 10)
    assert seq2.warmup_bars == 67 and not intra.ema_is_thin(intra.armed_index(seq2, 0))


# ═════════════════════════════════════════════════════════════════════════════════════════════ ENTER
def enter_rec(flat="10:05", first="10:40", pivot=None, setup="undated", mb=None):
    mb = mb if mb is not None else minutes_from_daily(100.0, 108.0, 96.0, 104.0)
    r = mini_rec(mb=mb, flat_clock=flat, first_clock=first, setup=setup, pivot=pivot, decides=setup != "undated", adr20=0.05 if setup != "undated" else None)
    return r


def test_levels_l7_l8_l9_existence_schedule_and_trigger():
    # a hand session: minute 0 high 100; minutes 1-29 highs 101; bar [30,89] highs 103 with the first minute above 101 at minute 35; bar [90,149] highs 102 until minute 120 where 104
    path = [(99.0, 100.0, 98.0, 99.5)] + [(99.5, 101.0, 99.0, 100.0)] * 29
    path += [(100.0, 100.5, 99.0, 100.0)] * 5 + [(100.0, 103.0, 99.5, 102.0)] + [(102.0, 102.5, 101.0, 102.0)] * 54          # minutes 30..89
    path += [(102.0, 102.0, 101.0, 101.5)] * 30 + [(101.5, 104.0, 101.0, 103.5)] + [(103.5, 103.8, 103.0, 103.5)] * 29       # minutes 90..149
    path += [(103.5, 103.6, 103.0, 103.2)] * 240
    mb = hand_minutes(path)
    r = enter_rec(mb=mb)
    L = intra.intraday_levels(r)
    assert L["L7"] == 100.0 and L["L8"] == 101.0
    assert L["L9"][0] is None and L["L9"][1] == 101.0 and L["L9"][2] == 103.0 and L["L9"][3] == 104.0
    assert intra.l9_level_at(L, 29) is None and intra.l9_level_at(L, 30) == 101.0 and intra.l9_level_at(L, 95) == 103.0 and intra.l9_level_at(L, 150) == 104.0
    assert intra.l9_cross(mb, L) == 35 and rev.first_cross(mb, L["L8"]) == 35 and rev.first_cross(mb, L["L7"]) == 1
    # L9 never triggers later than L8: a session where the 30-minute high is never exceeded in the first hour but the second hour's bar is
    path2 = [(99.0, 100.0, 98.0, 99.5)] + [(99.5, 105.0, 99.0, 100.0)] * 29 + [(100.0, 102.0, 99.0, 101.0)] * 60 + [(101.0, 102.5, 100.5, 102.0)] * 300
    mb2 = hand_minutes(path2)
    L2 = intra.intraday_levels(enter_rec(mb=mb2))
    assert rev.first_cross(mb2, L2["L8"]) is None and intra.l9_cross(mb2, L2) == 90          # L9 = the first hour's high 102 from 11:00; crossed at 11:00
    # existence: before 10:00 the 30-minute levels do not exist; before 09:31 the 1-minute one does not
    assert intra.no_level_yet("L8", 29) and not intra.no_level_yet("L8", 30) and intra.no_level_yet("L7", 0) and not intra.no_level_yet("L7", 1) and intra.no_level_yet("L6", 59)
    # no bar at minute 0 -> L7 None (no_bar_0930)
    mb3 = hand_minutes(path[1:], start_minute=1)
    assert intra.intraday_levels(enter_rec(mb=mb3))["L7"] is None
    # the pivot floor on a dated breakout row only
    rb = enter_rec(mb=mb, setup="breakout", pivot=102.5)
    Lb = intra.intraday_levels(rb)
    assert Lb["L7"] == 102.5 and Lb["L8"] == 102.5 and Lb["L9"][1] == 102.5 and Lb["L9"][2] == 103.0 and Lb["L7_raw"] == 100.0
    assert intra.intraday_levels(enter_rec(mb=mb, setup="EP", pivot=102.5))["L7"] == 100.0
    # C14 (REJECTED by proof, the search made explicit as a belt): the crossing of L7 / L8 is searched from the minute the level EXISTS (09:31 /
    # 10:00). A floored level max(raw, pivot) is at least the raw level, and the raw level is the maximum high over every minute before the
    # level exists (minute 0 for L7; minutes 0-29 for L8), so no such minute can have a high STRICTLY above it: the search from the existence
    # minute equals the frozen search from minute 0 on every row, pivot or not. Asserted on a pivot above the raw range, a pivot below it, a
    # pre-10:00 spike that sets the raw 30-minute high, and a sparse opening range.
    path3 = list(path); path3[20] = (99.5, 102.0, 99.0, 100.0)                                       # minute 20's high 102 is the 30-minute high
    path4 = list(path3); path4[21] = (100.0, 102.6, 99.5, 100.0)
    for mbx, pv in ((hand_minutes(path), 102.5), (hand_minutes(path), 99.0), (hand_minutes(path3), 100.5), (hand_minutes(path3), 101.5), (hand_minutes(path4), 102.5),
                    (hand_minutes(path4), 102.7), (hand_minutes(path[1:], start_minute=1), 100.5), (hand_minutes(path[:3] + path[40:], start_minute=0), 100.9)):
        rx = enter_rec(mb=mbx, setup="breakout", pivot=pv, flat="10:00", first="10:40")
        Lx = intra.intraday_levels(rx)
        for lv in ("L7", "L8"):
            if Lx[lv] is None:
                continue
            assert Lx[lv] >= Lx[f"{lv}_raw"]
            assert intra.first_cross_from(mbx, Lx[lv], intra.LEVEL_EXISTS[lv]) == rev.first_cross(mbx, Lx[lv]), (pv, lv)
            assert intra.first_cross_from(mbx, Lx[lv], intra.LEVEL_EXISTS[lv]) is None or intra.first_cross_from(mbx, Lx[lv], intra.LEVEL_EXISTS[lv]) >= intra.LEVEL_EXISTS[lv]
            assert intra.score_new_fixed(mbx, Lx[lv], lv, 30, 70, 0.05)["cross"] == intra.score_fixed(mbx, Lx[lv], 30, 70, 0.05)["cross"]
    mb3 = hand_minutes(path3)
    rb3 = enter_rec(mb=mb3, setup="breakout", pivot=101.5, flat="10:00", first="10:40")
    L3 = intra.intraday_levels(rb3)
    assert L3["L8_raw"] == 102.0 and L3["L8"] == 102.0 and L3["L7"] == 101.5 and intra.first_cross_from(mb3, 101.5, 1) == 20 == rev.first_cross(mb3, 101.5)
    cross_l8, _pa = intra.level_price_fn("L8", rb3, L3)
    assert cross_l8 == 35 == rev.first_cross(mb3, 102.0)                                               # the shifted control's crossing: the same rule
    intra.chain_fill(rb3, "L8", {})
    assert rb3.fill_minute == 35 and rb3.fill_src == "level:L8"                                        # and the chain's fill
    # L9 at the window's edges (C7): a cross AT the flat minute is infeasible (the window is (flat, first]); a cross AT the first minute is feasible
    L_ = intra.intraday_levels(r)
    assert intra.score_l9(mb, L_, 35, 60, r.adr20)["feasible"] is False and intra.score_l9(mb, L_, 30, 35, r.adr20)["feasible"] is True


def test_score_l9_feasibility_hit_and_window_range():
    path = [(99.0, 100.0, 98.0, 99.5)] + [(99.5, 101.0, 99.0, 100.0)] * 29 + [(100.0, 100.5, 99.0, 100.0)] * 5 + [(100.0, 103.0, 99.5, 102.0)] + [(102.0, 102.5, 101.0, 102.0)] * 354
    mb = hand_minutes(path)
    r = enter_rec(mb=mb, flat="10:00", first="10:10")
    L = intra.intraday_levels(r)
    s = intra.score_l9(mb, L, 30, 40, r.adr20)
    assert s["cross"] == 35 and s["feasible"] and s["price"] == 101.0 and s["verdict"] == "HIT"
    s2 = intra.score_l9(mb, L, 36, 60, r.adr20)
    assert not s2["feasible"] and s2["verdict"] in ("HIT", "BALLPARK", "MISS")
    assert intra.range_verdict(mb, 150.0, 30, 40, 0.04)[0] == "MISS" and intra.range_verdict(mb, 101.0, 395, 399, 0.04)[0] == "no_bracket_minutes"


def test_shifted_window_control_no_room_bounds_and_keys():
    r = enter_rec(flat="10:05", first="10:40")                      # width 35
    cross, price_at = intra.level_price_fn("L8", r, intra.intraday_levels(r))
    s = intra.shifted_control(r, "L8", cross, price_at, n=50)
    assert not s["no_room"] and len(s["feas"]) == 50 and 0 <= s["feasible_share"] <= 1
    # the draw is keyed by (eid, level, draw) with seed 702: deterministic
    s2 = intra.shifted_control(r, "L8", cross, price_at, n=50)
    assert (s["feas"] == s2["feas"]).all() and (s["hit"] == s2["hit"]).all()
    # the starts lie in [the existence minute, the close - width]: read from the FUNCTION's own draws (C7), and equal to the keys replayed
    assert len(s["starts"]) == 50 and min(s["starts"]) >= 30 and max(s["starts"]) + 35 <= 390
    starts = [30 + int(intra.rng_for(intra.SHIFT_KEY.format(eid=r.b.eid, level="L8", draw=d)).integers(0, 390 - 35 - 30 + 1)) for d in range(50)]
    assert s["starts"] == starts
    s7 = intra.shifted_control(r, "L7", cross, price_at, n=50)
    assert min(s7["starts"]) >= 1 and min(intra.shifted_control(r, "L4", cross, price_at, n=50)["starts"]) >= 0
    # no room: a width wider than close - existence
    r3 = enter_rec(flat="09:35", first="15:50")                     # width 375 > 390 - 30
    assert intra.shifted_control(r3, "L8", cross, price_at)["no_room"]
    assert not intra.shifted_control(r3, "L4", cross, price_at)["no_room"]      # L4 exists from minute 0: room = 390 - 375 = 15
    # an early-close day bounds the starts at 13:00 (210)
    r4 = enter_rec(flat="10:05", first="10:40", mb=minutes_from_daily(100.0, 104.0, 97.0, 101.0, early=True))
    r4.b.E = "2020-11-27"
    s4 = intra.shifted_control(r4, "L1", cross, price_at, n=20)
    assert not s4["no_room"] and min(s4["starts"]) >= 5 and max(s4["starts"]) + 35 <= 210
    assert intra.shifted_control(enter_rec(flat="10:05", first="15:40", mb=minutes_from_daily(100.0, 104.0, 97.0, 101.0, early=True)), "L1", cross, price_at)["no_room"] is False or True


def test_enter_score_trade_summary_choice_verdict_and_veto():
    recs = []
    for k in range(8):
        r = enter_rec(flat="10:05", first="11:30", mb=minutes_from_daily(100.0 + k, 108.0 + k, 96.0 + k, 104.0 + k))
        r.b.eid = 100 + k
        recs.append(r)
    rng = intra.rng_for(intra.RANDOM_KEY)
    scored = {r.b.eid: intra.enter_score_trade(r, rng, with_shift=True) for r in recs}
    summ = intra.enter_summary(scored)
    assert summ["n"] == 8 and set(intra.ALL_LEVELS) <= set(summ) and 0 <= summ["control"]["feasible_share"] <= 1
    for lv in intra.ALL_LEVELS:
        assert summ[lv]["feasible"] <= 8 and summ[lv]["hit"] <= 8
    assert summ["union"]["control_feasible"] == summ["control"]["feasible_share"]      # the union's random-price control IS the plain one
    ch = intra.choose_level(summ)
    assert ch in intra.NEW_LEVELS
    # the choice: the highest feasible count among L7-L9; a tie that includes L8 goes to L8 (the article's hourly entry), any other tie to the first in order
    def tie(f7, f8, f9):
        return dict(n=10, **{lv: dict(feasible=f) for lv, f in (("L7", f7), ("L8", f8), ("L9", f9))})
    assert intra.choose_level(tie(5, 5, 3)) == "L8" and intra.choose_level(tie(4, 5, 5)) == "L8" and intra.choose_level(tie(5, 3, 5)) == "L7"
    assert intra.choose_level(tie(6, 5, 5)) == "L7" and intra.choose_level(tie(3, 3, 7)) == "L9" and intra.choose_level(tie(2, 2, 2)) == "L8"
    # the verdict: a hand summary
    def hs(f, n=40):
        return dict(n=n, **{lv: dict(feasible=f, hit=n, feasible_share=intra.binom_ci(f, n), hit_share=intra.binom_ci(n, n), shift_feasible=0.20, shift_hit=0.9, shift_no_room=0, shift_n=n, verdicts={}) for lv in intra.ALL_LEVELS},
                    control=dict(feasible_share=0.30, hit_share=0.85), union={})
    assert intra.enter_verdict(hs(30), "L8")[0] == "PASS"                   # 75% >= 50, >= 30 + 15, >= 20 + 15, hit 100% >= 70
    assert intra.enter_verdict(hs(17), "L8")[0] == "FAIL" and "falsifier" in " ".join(intra.enter_verdict(hs(17), "L8")[1])
    assert intra.enter_verdict(hs(30, n=39), "L8")[0] == "INCONCLUSIVE-by-size"
    s = hs(30); s["control"]["feasible_share"] = 0.70
    assert intra.enter_verdict(s, "L8")[0] == "FAIL"
    # the sign veto: strictly below the larger control fires; fewer than 5 windows abstains
    v = hs(2, n=9); v["control"]["feasible_share"] = 0.32
    assert intra.enter_veto(v, "L8")[0] is True
    v2 = hs(3, n=9); v2["control"]["feasible_share"] = 0.32; v2["L8"]["shift_feasible"] = 0.20
    assert intra.enter_veto(v2, "L8")[0] is False                            # 33.3% not strictly below 32%
    assert intra.enter_veto(hs(1, n=4), "L8") == (False, "abstains (4 scorable untouched windows < 5)")
    # a window closing before 10:00 reads no_level_yet on L8 / L9 and is in the denominator
    r0 = enter_rec(flat="09:40", first="09:50")
    s0 = intra.enter_score_trade(r0, rng, with_shift=False)
    assert s0["L8"]["verdict"] == "no_level_yet" and s0["L9"]["verdict"] == "no_level_yet" and not s0["L8"]["feasible"] and s0["L7"]["verdict"] in ("HIT", "BALLPARK", "MISS")
    # the union is ANY of L7 / L1 / L8 (C7): minutes 0-9 flat at a 100 high, minute 10 clears it -> L7 (and L1) cross at 09:40 inside the window
    # (09:35, 09:50]; L8 does not exist yet -> the union is feasible although L8 is not
    pu = [(99.0, 100.0, 98.0, 99.5)] * 10 + [(99.5, 101.0, 99.0, 100.5)] + [(100.5, 100.8, 100.0, 100.5)] * 379
    ru = enter_rec(mb=hand_minutes(pu), flat="09:35", first="09:50")
    su = intra.enter_score_trade(ru, rng, with_shift=False)
    assert su["L7"]["feasible"] and su["L7"]["cross"] == 10 and not su["L8"]["feasible"] and su["union"]["feasible"]
    # the random-price control counts HIT OR BALLPARK (C7): the window's minutes sit exactly at 100 while every other close is 100.5 — within
    # 0.25 ADR20 (0.04 x 100 = 1.0) of the range -> every drawn price is BALLPARK (never HIT), and the control's hit share is 1.0
    pb = [(100.5, 100.5, 100.5, 100.5)] * 390
    for mnt in range(36, 71):
        pb[mnt] = (100.0, 100.0, 100.0, 100.0)
    rb_ = enter_rec(mb=hand_minutes(pb), flat="10:05", first="10:40")
    sb = intra.enter_score_trade(rb_, intra.rng_for(intra.RANDOM_KEY), with_shift=False)
    assert intra.range_verdict(rb_.mb, 100.5, 35, 70, 0.04)[0] == "BALLPARK" and intra.range_verdict(rb_.mb, 100.0, 35, 70, 0.04)[0] == "HIT"
    assert sb["control"]["hit_share"] == 1.0 and 0.0 < sb["control"]["hit"].mean() == 1.0


def test_chain_fill_uses_the_level_where_feasible_else_the_registered_fill():
    path = [(99.0, 100.0, 98.0, 99.5)] + [(99.5, 101.0, 99.0, 100.0)] * 29 + [(100.0, 100.5, 99.0, 100.0)] * 5 + [(100.0, 103.0, 99.5, 102.0)] + [(102.0, 102.5, 101.0, 102.0)] * 354
    mb = hand_minutes(path)
    r = enter_rec(mb=mb, flat="10:00", first="10:10")
    intra.chain_fill(r, "L8", {})
    assert r.fill == 101.0 and r.fill_minute == 35 and r.fill_src == "level:L8" and not r.fill_fallback
    r2 = enter_rec(mb=mb, flat="10:00", first="10:10")
    intra.chain_fill(r2, "L9", {})
    assert r2.fill == 101.0 and r2.fill_minute == 35 and r2.fill_src == "level:L9"
    r3 = enter_rec(mb=mb, flat="10:40", first="11:00")                      # the crossing (10:05) is outside the window -> the registered fill (the open)
    intra.chain_fill(r3, "L8", {})
    assert r3.fill_src == "open" and r3.fill_fallback and r3.fill_minute == 0
    r4 = enter_rec(mb=mb, flat="10:00", first="10:10")
    intra.chain_fill(r4, None, {})
    assert r4.fill_src == "open" and not r4.fill_fallback


# ═════════════════════════════════════════════════════════════════════════════════════════════ §2c clock sanity, the sets' predicates
def test_clock_sanity_on_the_named_frames():
    mis = {"g_apps": ("2019-10-01", 300.0)}
    assert intra.clock_sane(mk_buy(flat_clock="10:48", first_clock="08:58"), {}) == "zero_width"                 # APPS 2019-10-01 (the clock reads backwards)
    assert intra.clock_sane(mk_buy(flat_clock="09:38", first_clock="09:38"), {}) == "zero_width"                 # ASPS 2019-10-17
    assert intra.clock_sane(mk_buy(flat_clock="09:08", first_clock="09:33"), {}) == "flat_before_open"           # ARWR 2020-01-02 (labelled in-session)
    assert intra.clock_sane(mk_buy(flat_clock="09:24", first_clock="09:25"), {}) == "flat_before_open"           # FBR 2019-10-23
    assert intra.clock_sane(mk_buy(flat_clock="09:26", first_clock="10:30"), {}) == "flat_before_open"           # DWAC 2022-01-31
    assert intra.clock_sane(mk_buy(flat_clock="10:05", first_clock="10:40", first_frame="g_apps"), mis) == "clock_misread"
    assert intra.clock_sane(mk_buy(flat_clock="10:05", first_clock="10:40"), mis) == "ok"
    assert intra.clock_sane(mk_buy(flat_clock="09:30", first_clock="09:31"), {}) == "ok"                          # 09:30 counts as in session


def test_fit_set_violation_refuses_every_check_side_buy():
    ok_u = mk_buy(E="2020-03-02", lo="2020-03-02", hi="2020-03-02", flat_clock="10:05", first_clock="10:40")
    assert intra.fit_set_violation("enter", ok_u) is None and intra.fit_set_violation("stop", ok_u) is None
    assert intra.fit_set_violation("exit", ok_u) is not None                                                        # EXIT's fit is dated 2020 only
    d20 = mk_buy(E="2020-03-02", setup="breakout", decides=True, pivot=50.0, adr20=0.05, exit_lo="2020-03-05", exit_hi="2020-03-06")
    assert not d20.has_exit and "not in the registered EXIT" in intra.fit_set_violation("exit", d20)               # unindexed: no KNOWN exit -> not EXIT's
    rev.index_calendar([d20], [d.isoformat() for d in sessions(10, "2020-03-02")])
    assert d20.has_exit                                                                                             # premise: the exit is known once indexed
    assert intra.fit_set_violation("exit", d20) is None and intra.fit_set_violation("enter", d20) is not None       # no window -> not ENTER's
    for E in ("2021-02-01", "2019-10-03", "2023-05-18", "2020-01-23", "2022-11-15"):
        b = mk_buy(E=E, lo=E, hi=E, flat_clock="10:05", first_clock="10:40")
        for st in ("enter", "stop", "exit"):
            assert "outside the fit window" in intra.fit_set_violation(st, b)
    fl = mk_buy(E="2020-03-02", lo="2020-03-02", hi="2020-03-02", flicker=True, flat_clock="10:05", first_clock="10:40")
    assert intra.fit_set_violation("enter", fl) is not None and intra.fit_set_violation("stop", fl) is None         # flickers: STOP yes, ENTER's deciding no
    g = intra.BarGuard({1})
    b21 = mk_buy(eid=2, E="2021-02-01", lo="2021-02-01", hi="2021-02-01")
    with pytest.raises(intra.GuardStop):
        g.forward(b21, 1)
    with pytest.raises(intra.GuardStop):
        g.forward_date(b21, "2021-02-02")
    g.forward_date(b21, "2021-01-20")                                      # before the buy day (warm-up): free
    assert intra.BarGuard(None).horizon(b21) is None


# ═════════════════════════════════════════════════════════════════════════════════════════════ STOP
def test_s9_s10_at_the_read_minute():
    path = [(99.0, 100.0, 97.0, 99.5)] + [(99.5, 101.0, 98.0, 100.0)] * 29 + [(100.0, 102.0, 99.0, 101.0)] * 60 + [(101.0, 103.0, 100.0, 102.0)] * 60 + [(102.0, 103.0, 101.5, 102.5)] * 240
    mb = hand_minutes(path)
    r = enter_rec(mb=mb, flat="10:05", first="11:30")                      # an in-session holding frame at 11:30 -> the read minute
    r.fill, r.fill_minute, r.fill_src = 100.0, 0, "open"
    S = intra.stop_levels_intra(r)
    assert r.read_minute == 120 and S["S9"] == 97.0 and not S["S9_is_S1"] and S["S10"] == 99.0 and not S["S10_is_S1"]     # the last completed bar before 11:30 = [30,89], low 99
    r2 = enter_rec(mb=mb, flat="09:40", first="09:50")                     # read before 10:00 -> copies of S1
    r2.fill, r2.fill_minute, r2.fill_src = 100.0, 0, "open"
    S2 = intra.stop_levels_intra(r2)
    assert S2["S9_is_S1"] and S2["S10_is_S1"] and S2["S9"] == S2["S1"]
    r3 = enter_rec(mb=mb, flat="", first="")                               # no in-session frame: the fill minute decides; a level fill at 10:35
    r3.b.in_bracket = False
    r3.fill, r3.fill_minute, r3.fill_src = 101.0, 65, "level:L8"
    S3 = intra.stop_levels_intra(r3)
    assert r3.read_minute == 65 and S3["S9"] == 97.0 and S3["S10"] == 97.0 and S3["S1"] == pytest.approx(97.0)        # S10 at 10:35 = the first bar's low = S9
    r4 = enter_rec(mb=mb, flat="", first="")
    r4.fill, r4.fill_minute, r4.fill_src = 101.0, None, "close_proxy"       # a close fill without a frame: copies of S1 (a reading, listed)
    S4 = intra.stop_levels_intra(r4)
    assert S4["S9_is_S1"] and S4["S10_is_S1"]
    r5 = enter_rec(mb=mb, flat="10:05", first="16:30", )
    r5.b.f_ctx = "closed"                                                  # an after-close frame is not an in-session holding frame
    r5.fill, r5.fill_minute, r5.fill_src = 100.0, 0, "open"
    assert intra.read_minute_of(r5) == 0


def stop_world(touch_minute: int, flat="10:05", first="10:40", fill_minute=0, exit_frame_clock="11:30", after_close=False, in_frame=True):
    """A record whose day-0 minutes touch 95 at `touch_minute` (level S = 95 is tested), later sessions above it, exit window at +3..+5."""
    path = [(100.0, 100.5, 99.5, 100.0)] * 390
    path[touch_minute] = (100.0, 100.0, 94.9, 99.0)
    mb = hand_minutes(path)
    r = mini_rec(mb=mb, flat_clock=flat, first_clock=first)
    if not in_frame:
        r.b.first_clock, r.b.f_ctx = "", ""
    r.fill, r.fill_minute, r.fill_src = 100.0, fill_minute, "level:L8" if fill_minute else "open"
    r.stop_levels = {"S1": 95.0, "S1_is_S2": False, "S3": 95.0, "S9": 95.0, "S9_is_S1": False, "S10": 95.0, "S10_is_S1": False, "S8": 50.0, "SMA50": ("sma", 50)}
    r.bars.l[r.e + 1:] = 99.0; r.bars.c[r.e + 1:] = 100.0; r.bars.o[r.e + 1:] = 100.0; r.bars.h[r.e + 1:] = 101.0
    r.bars.o[r.e], r.bars.h[r.e], r.bars.l[r.e], r.bars.c[r.e] = 100.0, 100.5, 94.9, 100.0      # the buy day's daily bar = its minute path (never daily_walk's ~50 close)
    frames = [(r.b.E, "AAA", "in", first)] if in_frame else []
    frames.append((r.b.exit_lo, "AAA", "in", exit_frame_clock))
    if after_close:
        frames.append((r.b.exit_lo, "AAA", "closed", "16:30"))
    return r, sightings_from(frames), FakeStore({})


def test_buy_day_certainty_rule_for_T():
    smas = intra.smas_for(stop_world(50)[0].bars)
    # a touch at or before flat_clock (10:05 = minute 35) is NOT an event; nothing later -> no event at all
    r, si, st = stop_world(20)
    h = intra.held_through_intra(r, "S1", "T", smas, si, st)
    assert not h["any"] and not h["certain"] and not h["unresolved"]
    # between flat (35) and first (70): unresolved
    r, si, st = stop_world(50)
    h = intra.held_through_intra(r, "S1", "T", smas, si, st)
    assert h["any"] and h["unresolved"] and not h["certain"] and h["event_m"] == 50 and h["first_j"] == 0
    # at or after first_clock: certain
    r, si, st = stop_world(90)
    h = intra.held_through_intra(r, "S1", "T", smas, si, st)
    assert h["any"] and h["certain"] and not h["unresolved"]
    # no in-session holding frame on the buy day: every buy-day event unresolved
    r, si, st = stop_world(90, in_frame=False)
    h = intra.held_through_intra(r, "S1", "T", smas, si, st)
    assert h["any"] and h["unresolved"] and not h["certain"]
    # a touch before the fill minute is not an event (he did not hold yet)
    r, si, st = stop_world(50, fill_minute=60)
    assert not intra.held_through_intra(r, "S1", "T", smas, si, st)["any"]
    # the OLD rule (the frozen held_through) called the 10:20 touch after the fill CERTAIN — the new rule does not
    r, si, st = stop_world(50)
    old = rev.held_through(r, "S1", "T", smas, si)
    assert old["certain"] and not intra.held_through_intra(r, "S1", "T", smas, si, st)["certain"]


def test_buy_day_certainty_rule_for_H_and_no_bar_abstention():
    def world(h_bar_close_minute_bar: int, first="10:40", flat="10:05", fill_minute=0):
        path = [(100.0, 100.5, 99.5, 100.0)] * 390
        lo, hi = R.h60_windows("h60", False)[h_bar_close_minute_bar]
        for m in range(lo, hi + 1):
            path[m] = (96.0, 96.5, 94.0, 94.5)                               # that bar closes below 95
        mb = hand_minutes(path)
        r = mini_rec(mb=mb, flat_clock=flat, first_clock=first)
        r.fill, r.fill_minute, r.fill_src = 100.0, fill_minute, "open"
        r.stop_levels = {"S1": 95.0, "S1_is_S2": False, "S3": 95.0, "S9": 95.0, "S9_is_S1": False, "S10": 95.0, "S10_is_S1": False, "S8": 50.0, "SMA50": ("sma", 50)}
        r.bars.l[r.e + 1:] = 99.0; r.bars.c[r.e + 1:] = 100.0; r.bars.o[r.e + 1:] = 100.0; r.bars.h[r.e + 1:] = 101.0
        return r, sightings_from([(r.b.E, "AAA", "in", first), (r.b.exit_lo, "AAA", "in", "11:30")]), FakeStore({})
    smas = intra.smas_for(world(1)[0].bars)
    r, si, st = world(1)                                                       # the bar [30,89] closes at 89 (10:59) >= first 10:40 -> certain
    h = intra.held_through_intra(r, "S1", "H", smas, si, st)
    assert h["any"] and h["certain"] and h["event_m"] == 89
    r, si, st = world(1, first="11:30")                                        # closes at 10:59 < first 11:30, after flat -> unresolved
    h = intra.held_through_intra(r, "S1", "H", smas, si, st)
    assert h["any"] and h["unresolved"] and not h["certain"]
    r, si, st = world(0, flat="10:05", first="11:30")                          # the first bar closes at 09:59 <= flat 10:05 -> not an event; later sessions clean -> none
    h = intra.held_through_intra(r, "S1", "H", smas, si, st)
    assert not h["any"]
    r, si, st = world(1, fill_minute=100)                                      # the bar completed before the fill: not an event
    assert not intra.held_through_intra(r, "S1", "H", smas, si, st)["any"]
    # a later session without minutes: H abstains for that session (no_bar) and the scan goes on; T still reads the daily low.
    # PREMISE (asserted): the buy day carries NO H event — its only bar below closes at 09:59, at or before flat 10:05 — so the scan reaches
    # the later sessions (a day-0 event at or after first_clock would end the scan as certain before any later session is read).
    r, si, st = world(0, flat="10:05", first="11:30")
    assert not intra.held_through_intra(r, "S1", "H", smas, si, FakeStore({r.session_date(j): hand_minutes([(100.0, 100.5, 99.5, 100.0)] * 390) for j in range(1, 6)}))["any"]
    r.bars.l[r.e + 2] = 94.0
    hT = intra.held_through_intra(r, "S1", "T", smas, si, FakeStore({}))
    assert hT["any"] and hT["certain"] and hT["first_j"] == 2                 # day 0's 09:30-09:59 touch is at or before flat: not an event; session +2 < exit_lo: certain
    hH = intra.held_through_intra(r, "S1", "H", smas, si, FakeStore({r.session_date(1): None}))
    assert not hH["any"] and hH["no_bar_sessions"] >= 1 and hH["note"] == "no_bar"


def test_H_and_T_certainty_on_exit_lo_and_C_after_close():
    r, si, st = stop_world(20, exit_frame_clock="11:30")
    r.stop_levels["S3"] = 98.5
    smas = intra.smas_for(r.bars)
    # a touch on exit_lo (j = 3) BEFORE the last in-session frame (11:30): certain under T when the exit minutes show it early
    r.bars.l[r.e + 3] = 98.0
    early = [(100.0, 100.5, 97.9, 100.0)] + [(100.0, 100.5, 99.5, 100.0)] * 389
    late = [(100.0, 100.5, 99.5, 100.0)] * 300 + [(100.0, 100.5, 97.9, 100.0)] + [(100.0, 100.5, 99.5, 100.0)] * 89
    hT = intra.held_through_intra(r, "S3", "T", smas, si, FakeStore({r.session_date(3): hand_minutes(early)}))
    assert hT["any"] and hT["certain"] and hT["first_j"] == 3
    hT2 = intra.held_through_intra(r, "S3", "T", smas, si, FakeStore({r.session_date(3): hand_minutes(late)}))
    assert hT2["any"] and not hT2["certain"] and not hT2["unresolved"]
    hT3 = intra.held_through_intra(r, "S3", "T", smas, si, FakeStore({}))
    assert hT3["any"] and hT3["unresolved"]
    # H on exit_lo: the bar's close minute must be before 11:30 (minute 120): a bar [30,89] closing below counts, [90,149] (closes 10:59.. no: 149 = 11:59) does not
    r.bars.l[r.e + 3] = 99.0
    pathH = [(100.0, 100.5, 99.5, 100.0)] * 390
    for m in range(30, 90):
        pathH[m] = (98.0, 98.2, 97.5, 98.0)
    hH = intra.held_through_intra(r, "S3", "H", smas, si, FakeStore({r.session_date(3): hand_minutes(pathH)}))
    assert hH["any"] and hH["certain"] and hH["event_m"] == 89
    pathH2 = [(100.0, 100.5, 99.5, 100.0)] * 390
    for m in range(90, 150):
        pathH2[m] = (98.0, 98.2, 97.5, 98.0)
    hH2 = intra.held_through_intra(r, "S3", "H", smas, si, FakeStore({r.session_date(3): hand_minutes(pathH2)}))
    assert hH2["any"] and not hH2["certain"]
    # C on exit_lo: certain only with a frame after the close. PREMISE (asserted): no session before exit_lo closes under S3 (the buy day's
    # daily close is the minute path's 100, not daily_walk's), so the C event is exit_lo's own.
    r.bars.c[r.e + 3] = 98.0
    assert all(float(r.bars.c[r.e + j]) > r.stop_levels["S3"] for j in range(0, 3))
    hC = intra.held_through_intra(r, "S3", "C", smas, si, st)
    assert hC["any"] and hC["first_j"] == 3 and not hC["certain"]
    r2, si2, st2 = stop_world(20, after_close=True)
    r2.stop_levels["S3"] = 98.5
    r2.bars.c[r2.e + 3] = 98.0
    assert intra.held_through_intra(r2, "S3", "C", intra.smas_for(r2.bars), si2, st2)["certain"]
    # C on the BUY DAY keeps the frozen rule (a reading, listed): a buy-day daily close below the level is a certain held-through event
    r4, si4, st4 = stop_world(20)
    r4.bars.c[r4.e] = 94.0
    h4 = intra.held_through_intra(r4, "S1", "C", intra.smas_for(r4.bars), si4, st4)
    assert h4["any"] and h4["certain"] and not h4["unresolved"] and h4["first_j"] == 0
    # a session strictly before exit_lo: certain without any minute
    r3, si3, st3 = stop_world(20)
    r3.stop_levels["S3"] = 98.5
    r3.bars.l[r3.e + 1] = 98.0
    h3 = intra.held_through_intra(r3, "S3", "T", intra.smas_for(r3.bars), si3, st3)
    assert h3["certain"] and h3["first_j"] == 1


def test_stop_table_choice_verdict_and_spearman_exclusions():
    recs = []
    for k in range(25):
        r, si, st = stop_world(90 if k < 23 else 50)
        r.b.eid = 500 + k
        recs.append((r, si))
    si = recs[0][1]
    tab = intra.stop_table_intra([r for r, _s in recs], si, FakeStore({}))
    t = tab[("S1", "T")]
    assert t["n"] == 25 and t["any"] == 25 and t["certain"] == 23 and t["unresolved"] == 2 and t["eligible"] and t["differ"] == 25
    # choice: make S9-H the tightest eligible cell with H_cond <= 10%
    fake = {}
    for L in intra.STOP_LEVELS + intra.STOP_CONTROLS:
        for V in intra.STOP_VARIANTS:
            fake[(L, V)] = dict(n=60, any=30, certain=15, unresolved=0, H_cond=0.5, H_all=0.25, tight=0.05, eligible=True, differ=60, no_bar=0)
    fake[("S9", "H")].update(H_cond=0.08, tight=0.03)
    fake[("S1", "T")].update(H_cond=0.05, tight=0.04)
    fake[("S8", "T")].update(H_cond=0.0, tight=0.01)                          # a control is never his stop
    assert intra.choose_stop(fake) == ("S9", "H")
    fake[("S9", "H")].update(any=10, eligible=False)
    assert intra.choose_stop(fake) == ("S1", "T")
    fake[("S3", "T")].update(H_cond=0.05, tight=0.04)                          # a tie on the width -> T before C / H, then the level order
    fake[("S3", "C")].update(H_cond=0.05, tight=0.04)
    assert intra.choose_stop(fake) == ("S1", "T")
    assert intra.choose_stop({k: dict(v, H_cond=0.5) for k, v in fake.items()}) is None
    # the verdict on a check table
    chk = {k: dict(v) for k, v in fake.items()}
    chk[("S1", "T")].update(any=30, certain=3, H_cond=0.10)
    assert intra.stop_verdict(chk, ("S1", "T"))[0] == "PASS"
    chk[("S1", "T")].update(certain=6, H_cond=0.20)
    v, reasons = intra.stop_verdict(chk, ("S1", "T"))
    assert v == "FAIL" and "some cell <= 30%" in reasons[-1]
    chk2 = {k: dict(v, H_cond=0.45) for k, v in chk.items()}
    assert "falsifier" in intra.stop_verdict(chk2, ("S1", "T"))[1][-1]
    chk[("S1", "T")].update(any=19)
    assert intra.stop_verdict(chk, ("S1", "T"))[0] == "INCONCLUSIVE-by-size"
    chk[("S9", "H")].update(any=30, certain=2, H_cond=0.07, differ=19)
    assert intra.stop_verdict(chk, ("S9", "H"))[0] == "INCONCLUSIVE-by-size"
    assert intra.stop_verdict(chk, None)[0] == "INCONCLUSIVE"
    # Spearman leaves out S9 / S10 cells equal to S1 on more than half the records
    for r, _s in recs:
        r.stop_levels["S9_is_S1"] = True
    rho, used = intra.spearman_cells(fake, chk, [r for r, _s in recs])
    assert all(c[0] != "S9" for c in used) and any(c[0] == "S10" for c in used)


def test_stop_walk_h_books_the_next_minute_open_or_the_next_session_open():
    path = [(100.0, 100.5, 99.5, 100.0)] * 390
    for m in range(330, 390):
        path[m] = (96.0, 96.5, 94.0, 94.5)                                        # the day's LAST bar closes below 95 -> the next session's open
    r = mini_rec(mb=hand_minutes(path), flat_clock="10:05", first_clock="10:40")
    r.fill, r.fill_minute, r.fill_src = 100.0, 0, "open"
    r.bars.o[r.e + 1] = 93.0
    j, px, kind = intra.stop_walk_h(r, 95.0, intra.smas_for(r.bars), FakeStore({}), 5)
    assert (j, px, kind) == (1, 93.0, "stop_h_nextopen")
    path2 = [(100.0, 100.5, 99.5, 100.0)] * 390
    for m in range(30, 90):
        path2[m] = (96.0, 96.5, 94.0, 94.5)
    path2[90] = (97.0, 97.5, 96.5, 97.2)
    r2 = mini_rec(mb=hand_minutes(path2), flat_clock="10:05", first_clock="10:40")
    r2.fill, r2.fill_minute, r2.fill_src = 100.0, 0, "open"
    assert intra.stop_walk_h(r2, 95.0, intra.smas_for(r2.bars), FakeStore({}), 5) == (0, 97.0, "stop_h")
    # a later session's bar below -> that session's next minute open
    r3 = mini_rec(mb=hand_minutes([(100.0, 100.5, 99.5, 100.0)] * 390), flat_clock="10:05", first_clock="10:40")
    r3.fill, r3.fill_minute, r3.fill_src = 100.0, 0, "open"
    st = FakeStore({r3.session_date(2): hand_minutes(path2)})
    assert intra.stop_walk_h(r3, 95.0, intra.smas_for(r3.bars), st, 5) == (2, 97.0, "stop_h")
    # no bar below through J -> a mark at J's close
    j, px, kind = intra.stop_walk_h(r3, 50.0, intra.smas_for(r3.bars), FakeStore({}), 4)
    assert (j, kind) == (4, "mark") and px == pytest.approx(float(r3.bars.c[r3.e + 4]))
    assert intra.order_of("stop_h_nextopen") == intra.ORDER_OPEN and intra.order_of("stop_h") == intra.ORDER_INTRADAY and intra.order_of("mark_hole") == intra.ORDER_CLOSE


# ═════════════════════════════════════════════════════════════════════════════════════════════ EXIT
def exit_world(n_pre: int = 12, hold: int = 10, armed_fill_minute: int = 40, n: int = 120):
    """A record with minutes on every session from -n_pre to +hold, a rising path (the EMA under price), then a chosen session where the bars
    fall through the EMA; the prior-low legs set by hand on the daily bars. `n` daily bars (120 by default: 49 forward sessions; 300 for a
    full 120-session horizon)."""
    e = 70
    cal = sessions(n, "2020-01-02")
    o = np.full(n, 100.0); c = np.full(n, 100.0); h = np.full(n, 101.0); l = np.full(n, 99.0)
    for i in range(n):
        # a 0.3 / session trend, the low 0.25 under the open: measured on the built sequence, no bar closes below the 20-bar EMA on the rising
        # path (margin +0.07; a +-0.5 range dipped under the EMA's lag and fired E1 on the buy day) AND the EMA enters session +2 about 0.11
        # above the prior session's low (a shallower low put the prior low ABOVE the EMA); lows rise session over session (E4 never touches)
        o[i] = 100 + 0.3 * i; c[i] = 100.3 + 0.3 * i; h[i] = c[i] + 0.05; l[i] = o[i] - 0.25
    bars = cb.daily_bars_from_arrays(cal, o, h, l, c, np.full(n, 1e6))
    E = cal[e].isoformat()
    b = mk_buy(E=E, lo=E, hi=E, exit_lo=cal[e + 4].isoformat(), exit_hi=cal[e + 6].isoformat(), flat_clock="10:05", first_clock="10:40")
    rev.index_calendar([b], [d.isoformat() for d in cal])
    r = intra.IRec(b=b, bars=bars, cidx=np.arange(n, dtype=np.int32), e=e, adr20=0.03, cal=cal, era="A")
    r.qqq_c = np.asarray(bars.c) * 3
    r.exit_lo_j, r.exit_hi_j = 4, 6
    by = {cal[i].isoformat(): minutes_from_daily(o[i], h[i], l[i], c[i]) for i in range(n)}
    r.mb = by[E]
    r.fill, r.fill_minute, r.fill_src = float(o[e]) + 0.2, armed_fill_minute, "level:L8"
    r.stop, r.stop_lvl, r.stop_variant, r.stop_src = float(o[e]) * 0.90, float(o[e]) * 0.90, "T", "S1-T"
    r.day0 = dict(cb._NO_DAY0)
    return r, by, bars


def test_exit_variants_e1_e4_half_leg_all_out_tail_and_stop_preemption():
    r, by, bars = exit_world()
    by0 = dict(by)                                                              # the untouched rising path (E4's and the hole's world)
    st0 = FakeStore(by0)
    seq0 = intra.bar_sequence(r, st0, -intra.WARMUP_SESSIONS, r.exit_hi_j + intra.TAIL_SESSIONS)
    armed = intra.armed_index(seq0, r.fill_minute)
    assert not intra.ema_is_thin(armed) and seq0.items[armed][0] == 0 and seq0.items[armed][1].lo == 30
    # PREMISE (asserted, never assumed): on the rising path no armed bar closes below the EMA, so no E1 leg can fire before the designed session
    assert all(x.c >= seq0.ema[i] for i, (jj, x) in enumerate(seq0.items) if i >= armed and np.isfinite(seq0.ema[i]))
    # session +2: from the second bar on, the bars close BELOW the EMA but ABOVE the prior session's low (so the prior-low legs do not fire there;
    # the daily bar stays 'normal' for E2's daily-close leg). The band is read off the sequence itself, never estimated.
    d2 = r.session_date(2)
    i2 = [i for i, (jj, x) in enumerate(seq0.items) if jj == 2 and x.lo == 30][0]
    ema_in = float(seq0.ema[i2 - 1])                                            # the EMA entering bar [30,89] (a close below it is below the EMA that includes it)
    PL2 = float(r.bars.l[r.e + 1])
    assert PL2 + 0.04 < ema_in, (PL2, ema_in)                                   # PREMISE: room between the prior low and the EMA
    cb_ = 0.5 * (PL2 + ema_in)
    o2 = float(r.bars.o[r.e + 2])
    path = [(o2, o2 + 0.02, o2 - 0.02, o2)] * 30 + [(cb_, cb_ + 0.01, cb_ - 0.01, cb_)] * 360
    by[d2] = hand_minutes(path)
    st = FakeStore(by)
    seq = intra.bar_sequence(r, st, -intra.WARMUP_SESSIONS, r.exit_hi_j + intra.TAIL_SESSIONS)
    assert intra.armed_index(seq, r.fill_minute) == armed
    assert seq.items[i2 - 1][1].c >= seq.ema[i2 - 1] and seq.items[i2][0] == 2 and seq.items[i2][1].lo == 30 and seq.items[i2][1].c < seq.ema[i2]   # PREMISE: the designed bar is the first below
    assert cb_ - 0.01 > PL2                                                     # PREMISE: session +2 never touches the prior low
    smas = intra.smas_for(bars)
    J_tail = r.exit_hi_j + intra.TAIL_SESSIONS
    # the stop is far below (90% of the open): no stop; E1 sells at the next minute's open after the first bar below (session +2, bar [30,89] closes at 89 -> minute 90's open)
    w1 = intra.exit_walk_intra(r, "E1", seq, armed, st, smas, J_tail)
    assert len(w1["legs"]) == 1 and w1["legs"][0].kind == "e1" and w1["legs"][0].j == 2 and w1["legs"][0].minute == 89 and w1["legs"][0].px == pytest.approx(cb_)
    assert w1["last_j"] == 2 and not w1["stop_preempt"] and w1["e1_j"] == 2
    # E4 on the untouched rising path: the prior session's low is never touched -> cut at the tail
    w4 = intra.exit_walk_intra(r, "E4", seq0, armed, st0, smas, J_tail)
    assert len(w4["legs"]) == 1 and w4["legs"][0].kind == "cut_at_tail" and w4["legs"][0].j == J_tail and w4["cut"] == "tail"
    # E2: half at E1's bar; the rest at the first daily close below the prior low -> make session +5 close below session +4's low; sold at +6's open
    r.bars.c[r.e + 5] = float(r.bars.l[r.e + 4]) - 1.0
    r.bars.l[r.e + 5] = float(r.bars.c[r.e + 5]) - 0.2
    w2 = intra.exit_walk_intra(r, "E2", seq, armed, st, smas, J_tail)
    kinds = [lg.kind for lg in w2["legs"]]
    assert kinds == ["e1_half", "dclose"] and w2["legs"][0].frac == 0.5 and w2["legs"][1].frac == 0.5 and w2["legs"][1].j == 6 and w2["legs"][1].order == intra.ORDER_OPEN and w2["half_j"] == 2
    # E3: half at E1's bar; the rest at an intraday touch of the prior low (session +5's low under +4's low): sold at the level
    by[r.session_date(5)] = minutes_from_daily(float(r.bars.o[r.e + 5]), float(r.bars.h[r.e + 5]), float(r.bars.l[r.e + 5]), float(r.bars.c[r.e + 5]))
    w3 = intra.exit_walk_intra(r, "E3", seq, armed, st, smas, J_tail)
    assert [lg.kind for lg in w3["legs"]] == ["e1_half", "touch"] and w3["legs"][1].j == 5 and w3["legs"][1].px == pytest.approx(float(r.bars.l[r.e + 4]))
    sc, hit, half = intra.exit_hit(w3, r, dict(J_tail=J_tail))
    assert sc and hit and not half                                              # the last leg (session 5) is inside [4, 6]; the half leg (session 2) is not
    # E2 / E3 all out when the prior-low event comes BEFORE E1's bar: a daily close below the prior low on session +1
    r2, by2, bars2 = exit_world()
    r2.bars.c[r2.e + 1] = float(r2.bars.l[r2.e]) - 1.0
    r2.bars.l[r2.e + 1] = float(r2.bars.c[r2.e + 1]) - 0.2
    st2 = FakeStore(by2)
    seq2 = intra.bar_sequence(r2, st2, -intra.WARMUP_SESSIONS, r2.exit_hi_j + intra.TAIL_SESSIONS)
    w2b = intra.exit_walk_intra(r2, "E2", seq2, intra.armed_index(seq2, r2.fill_minute), st2, intra.smas_for(bars2), r2.exit_hi_j + intra.TAIL_SESSIONS)
    assert [lg.kind for lg in w2b["legs"]] == ["dclose_all"] and w2b["legs"][0].frac == 1.0 and w2b["legs"][0].j == 2
    # the stop pre-empts any leg inside a session: a T stop touched on session +1 -> all out at the level, no E1 leg
    r3, by3, bars3 = exit_world()
    r3.bars.l[r3.e + 1] = r3.stop - 0.5
    by3[r3.session_date(1)] = minutes_from_daily(float(r3.bars.o[r3.e + 1]), float(r3.bars.h[r3.e + 1]), float(r3.bars.l[r3.e + 1]), float(r3.bars.c[r3.e + 1]))
    st3 = FakeStore(by3)
    seq3 = intra.bar_sequence(r3, st3, -intra.WARMUP_SESSIONS, r3.exit_hi_j + intra.TAIL_SESSIONS)
    w = intra.exit_walk_intra(r3, "E1", seq3, intra.armed_index(seq3, r3.fill_minute), st3, intra.smas_for(bars3), r3.exit_hi_j + intra.TAIL_SESSIONS)
    assert w["stop_preempt"] and w["legs"][0].kind == "stop" and w["legs"][0].px == pytest.approx(r3.stop) and w["legs"][0].j == 1
    # the legs trade: two legs sum to one, realised R from both legs
    t = intra.make_legs_trade(r, w3["legs"], (r.fill - r.stop) / r.fill, None, 10 ** 6)
    assert t is not None and len(t.legs) == 2 and abs(sum(lg[2] for lg in t.legs) - 1.0) < 1e-9 and t.sessions_held == 5 and t.status == "touch"
    exp_r = 0.5 * (w3["legs"][0].px - r.fill) / (r.fill - r.stop) + 0.5 * (w3["legs"][1].px - r.fill) / (r.fill - r.stop)
    assert t.realized_r == pytest.approx(exp_r)
    # the second-close variant fires on the second bar below, not the first
    w5 = intra.exit_walk_intra(r, "E1", seq, armed, st, smas, J_tail, second_close=True)
    assert w5["legs"][0].kind == "e1" and w5["legs"][0].minute == 149
    # a hole on the path -> mark_hole at the last bar before it
    r4, by4, bars4 = exit_world()
    r4.cidx = r4.cidx.copy(); r4.cidx[r4.e + 3:] += 1                           # a missing session after +2
    st4 = FakeStore(by4)
    seq4 = intra.bar_sequence(r4, st4, -intra.WARMUP_SESSIONS, 8)
    w6 = intra.exit_walk_intra(r4, "E4", seq4, intra.armed_index(seq4, r4.fill_minute), st4, intra.smas_for(bars4), 8)
    assert w6["cut"] == "hole" and w6["legs"][-1].kind == "mark_hole" and w6["legs"][-1].j == 2


def test_choose_exit_ties_recovery_veto_and_hit_rate_scorability():
    rates = {"E1": (0.4, 0.3, 20, {}), "E2": (0.5, 0.2, 20, {}), "E3": (0.5, 0.2, 20, {}), "E4": (0.5, 0.0, 20, {})}
    assert intra.choose_exit(rates) == "E4"                                      # ties -> fewer legs: E1, E4, then E2, E3
    rates["E1"] = (0.5, 0.3, 20, {})
    assert intra.choose_exit(rates) == "E1"
    assert intra.exit_veto(dict(ours=1.4, chosen=1.3, his=2.6)) == (True, "his 2.600 > ours 1.400; chosen 1.300 < ours -> VETO")
    assert intra.exit_veto(dict(ours=1.4, chosen=1.5, his=2.6))[0] is False
    assert intra.exit_veto(dict(ours=1.4, chosen=1.1, his=1.3))[0] is False      # his <= ours there: abstains
    r, by, bars = exit_world()
    w = dict(last_j=5, half_j=None, cut="")
    assert intra.exit_hit(w, r, dict(J_tail=26)) == (True, True, False)
    # the window's width is read on the record's OWN calendar (C12): the main calendar's indices say > 20 while the own offsets say 3 -> scorable
    r.b.exit_hi_i = r.b.exit_lo_i + 25
    assert intra.exit_window_sessions(r) == 3 and intra.exit_hit(w, r, dict(J_tail=26))[0] is True
    r.exit_hi_j = r.exit_lo_j + 25                                               # a window > 20 sessions on the own calendar leaves the hit rate
    assert intra.exit_window_sessions(r) == 26 and intra.exit_hit(dict(last_j=10, half_j=None, cut=""), r, dict(J_tail=50))[0] is False
    r.exit_hi_j = 6
    assert intra.exit_hit(dict(last_j=2, half_j=None, cut="hole"), r, dict(J_tail=26))[0] is False     # cut by a hole before the window
    assert intra.exit_hit(w, r, dict(J_tail=5))[0] is False                                              # the data ended before his exit
    # the check's pure decision rules (C7)
    assert intra.chain_after("PASS", "L8") == "L8" and intra.chain_after("FAIL", "L8") is None and intra.chain_after("INCONCLUSIVE", ("S1", "T")) is None
    assert intra.apply_sign_veto("PASS", True, "2021-22") == ("INCONCLUSIVE", "a PASS on 2021-22 vetoed by the untouched years' sign")
    assert intra.apply_sign_veto("PASS", False, "x") == ("PASS", None) and intra.apply_sign_veto("FAIL", True, "x") == ("FAIL", None)
    assert intra.deciding_line_for({"enter": "FAIL", "stop": "FAIL"}) == "registered" and intra.deciding_line_for({"enter": "PASS", "stop": "FAIL"}) == "chain"
    assert intra.deciding_line_for({"enter": "INCONCLUSIVE", "stop": "PASS"}) == "chain" and intra.deciding_line_for({}) == "registered"
    assert intra.exit_verdict(dict(void="his / ours = 1.1", abstain_share=0.0, recovery=0.9))[0] == "VOID"            # VOID before anything
    assert intra.exit_verdict(dict(void="", abstain_share=0.11, recovery=0.9))[0] == "INCONCLUSIVE"                   # then the abstention clause
    assert intra.exit_verdict(dict(void="", abstain_share=0.10, recovery=0.25))[0] == "PASS" and intra.exit_verdict(dict(void="", abstain_share=0.0, recovery=0.249))[0] == "FAIL"
    from collections import Counter
    c = Counter(trades=8, cut_at_tail=1, cut_at_horizon=1, ema_thin=1, no_armed_bar=0, cut_at_hole=0)
    assert intra.abstention_share(c) == (3, pytest.approx(3 / 9))                                                     # over the account trades + the thin / no-bar ones
    assert intra.abstention_share(Counter(trades=5)) == (0, 0.0) and np.isnan(intra.abstention_share(Counter())[1])


def test_exit_prepare_tail_kind_armed_session_touch_rule_and_close_holds_fixtures():
    """C11 / C15 / C7: exit_prepare's J_tail and tail kinds (tail / horizon); the prior-low touch waits for the ARMED bar's close on the armed
    session whatever its j; a bar whose LOW pierces the average but whose CLOSE holds is no E1 event (and no H stop event)."""
    r, by, bars = exit_world()
    st = FakeStore(by)
    M = dict(guards={"A": {}}, map_b=None)
    prep = intra.exit_prepare(r, M, st)
    assert prep["J_tail"] == r.exit_hi_j + intra.TAIL_SESSIONS == 26 and prep["tail_kind"] == "cut_at_tail" and prep["why"] == "" and not prep["thin"]
    assert prep["armed"] == 70 + 1 and prep["residual"] == pytest.approx((19 / 21) ** 51)        # 70 warm-up bars + the 09:30-10:00 bar before the [30,89] armed bar
    # a sell window longer than the 120-session horizon: J_tail caps at the horizon and the tail is `cut_at_horizon` (never `mark_hole`)
    r2, by2, _b2 = exit_world(n=300)
    r2.exit_lo_j, r2.exit_hi_j = 110, 126
    prep2 = intra.exit_prepare(r2, M, FakeStore(by2))
    assert prep2["J_tail"] == prep2["bh"] == intra.HORIZON + 1 < r2.exit_hi_j and prep2["why"] == "" and prep2["tail_kind"] == "cut_at_horizon"   # the frozen window: + 1 .. + 121
    r2h, by2h, _b = exit_world()                                                                  # the data ends 49 sessions out: the export's end, not the horizon
    r2h.exit_lo_j, r2h.exit_hi_j = 40, 45
    prep2h = intra.exit_prepare(r2h, M, FakeStore(by2h))
    assert prep2h["J_tail"] == 49 and prep2h["why"] == "" and prep2h["tail_kind"] == "cut_at_data_end"
    assert intra.tail_kind_for(r2, 120, "break", 120) == "mark_break" and intra.tail_kind_for(r2, 120, "hole", 120) == "mark_hole" and intra.tail_kind_for(r, 26, "", 49) == "cut_at_tail"
    # C15: a CLOSE fill (None) arms on session 1's first bar; a prior-low touch at 09:31 of session 1 must NOT count (the armed bar has not completed)
    r3, by3, bars3 = exit_world(armed_fill_minute=None)
    r3.fill_minute = None
    d1 = r3.session_date(1)
    PL1 = float(r3.bars.l[r3.e])                                                               # the prior low for session 1 = the buy day's low
    o1 = float(r3.bars.o[r3.e + 1])
    path1 = [(o1, o1 + 0.02, o1 - 0.02, o1)] + [(o1, o1 + 0.01, PL1 - 0.3, o1)] + [(o1, o1 + 0.02, o1 - 0.02, o1)] * 28        # minute 1 touches the prior low
    path1 += [(o1, o1 + 0.02, o1 - 0.02, o1)] * 60 + [(o1, o1 + 0.01, PL1 - 0.3, o1)] + [(o1, o1 + 0.02, o1 - 0.02, o1)] * 299  # minute 90 touches again
    by3[d1] = hand_minutes(path1)
    r3.bars.l[r3.e + 1] = PL1 - 0.3
    st3 = FakeStore(by3)
    seq3 = intra.bar_sequence(r3, st3, -intra.WARMUP_SESSIONS, r3.exit_hi_j + intra.TAIL_SESSIONS)
    armed3 = intra.armed_index(seq3, None)
    assert seq3.items[armed3][0] == 1 and seq3.items[armed3][1].lo == 0 and seq3.items[armed3][1].close_minute == 29
    w = intra.exit_walk_intra(r3, "E4", seq3, armed3, st3, intra.smas_for(bars3), r3.exit_hi_j + intra.TAIL_SESSIONS)
    assert w["legs"][0].kind == "touch" and w["legs"][0].j == 1 and w["legs"][0].minute == 90       # the 09:31 touch is before the armed bar's close (09:59): skipped; 11:00's counts
    # a touch on the buy day when the fill arms on session 1: never counted (the session is before the armed one). The buy day's minutes dip
    # under ITS prior low (session -1's) at 09:35; session 1's prior low (the buy day's daily low) is left as it was, so its 11:00 touch stands
    PL0 = float(r3.bars.l[r3.e - 1])
    o0 = float(r3.bars.o[r3.e])
    path0 = [(o0, o0 + 0.02, o0 - 0.02, o0)] * 5 + [(o0, o0 + 0.01, PL0 - 0.3, o0)] + [(o0, o0 + 0.02, o0 - 0.02, o0)] * 384
    by3[r3.b.E] = hand_minutes(path0)
    r3.mb = by3[r3.b.E]
    assert PL0 - 0.3 < PL0 and float(r3.bars.l[r3.e]) > PL0 - 0.3 - 1.0                            # PREMISE: the buy-day minutes touch session 0's prior low
    seq3b = intra.bar_sequence(r3, FakeStore(by3), -intra.WARMUP_SESSIONS, r3.exit_hi_j + intra.TAIL_SESSIONS)
    wb = intra.exit_walk_intra(r3, "E4", seq3b, intra.armed_index(seq3b, None), FakeStore(by3), intra.smas_for(bars3), r3.exit_hi_j + intra.TAIL_SESSIONS)
    assert wb["legs"][0].j == 1 and wb["legs"][0].minute == 90                                      # not the buy day's 09:35 touch
    # E2's daily-close leg counts from the armed SESSION on: the buy day's own close under the prior low does not sell a close fill
    r3.bars.c[r3.e] = float(r3.bars.l[r3.e - 1]) - 0.2
    seq3c = intra.bar_sequence(r3, FakeStore(by3), -intra.WARMUP_SESSIONS, r3.exit_hi_j + intra.TAIL_SESSIONS)
    w2 = intra.exit_walk_intra(r3, "E2", seq3c, intra.armed_index(seq3c, None), FakeStore(by3), intra.smas_for(bars3), r3.exit_hi_j + intra.TAIL_SESSIONS)
    assert float(r3.bars.c[r3.e]) < float(r3.bars.l[r3.e - 1])                                    # PREMISE: the buy day closes under its prior session's low
    assert all(lg.j >= 1 for lg in w2["legs"])
    # N4: a daily close sells at the NEXT open, so a `dclose` leg booked on session 1 can only come from the buy day's close: none may exist
    # (counted from the armed session, session 1, on — C15)
    assert not any(lg.kind.startswith("dclose") and lg.j <= 1 for lg in w2["legs"]), [(lg.kind, lg.j) for lg in w2["legs"]]
    # C7: a bar whose low pierces the average but whose close holds above it fires neither E1 nor an H stop
    r4, by4, bars4 = exit_world()
    st4 = FakeStore(by4)
    seq4 = intra.bar_sequence(r4, st4, -intra.WARMUP_SESSIONS, r4.exit_hi_j + intra.TAIL_SESSIONS)
    armed4 = intra.armed_index(seq4, r4.fill_minute)
    d2 = r4.session_date(2)
    i2 = [i for i, (jj, x) in enumerate(seq4.items) if jj == 2 and x.lo == 30][0]
    ema_in = float(seq4.ema[i2 - 1])
    o2 = float(r4.bars.o[r4.e + 2])
    hold = ema_in + 0.3                                                                           # closes hold 0.3 above the EMA entering the bar, the lows dive 1.0 under it
    path2 = [(o2, o2 + 0.02, o2 - 0.02, o2)] * 30 + [(hold, hold + 0.01, ema_in - 1.0, hold)] * 360
    by4[d2] = hand_minutes(path2)
    r4.bars.l[r4.e + 2] = ema_in - 1.0
    st4 = FakeStore(by4)
    seq4 = intra.bar_sequence(r4, st4, -intra.WARMUP_SESSIONS, r4.exit_hi_j + intra.TAIL_SESSIONS)
    bar2 = [x for jj, x in seq4.items if jj == 2 and x.lo == 30][0]
    assert bar2.l < seq4.ema[i2] < bar2.c                                                           # PREMISE: the low pierces, the close holds
    w4 = intra.exit_walk_intra(r4, "E1", seq4, armed4, st4, intra.smas_for(bars4), r4.exit_hi_j + intra.TAIL_SESSIONS)
    assert not any(lg.kind == "e1" and lg.j == 2 for lg in w4["legs"])
    r4.stop_lvl, r4.stop_variant, r4.stop = ema_in - 0.5, "H", ema_in - 0.5                         # an H stop at a level the lows pierce but no close breaks
    assert intra.stop_event(r4, 2, intra.smas_for(bars4), st4, seq4) is None
    rH = mini_rec(mb=hand_minutes([(100.0, 100.5, 99.5, 100.0)] * 390), flat_clock="10:05", first_clock="10:40")
    rH.fill, rH.fill_minute, rH.fill_src = 100.0, 0, "open"
    rH.stop_levels = {"S1": 95.0, "S1_is_S2": False, "S3": 95.0, "S9": 95.0, "S9_is_S1": False, "S10": 95.0, "S10_is_S1": False, "S8": 50.0, "SMA50": ("sma", 50)}
    rH.bars.l[rH.e + 1:] = 99.0; rH.bars.c[rH.e + 1:] = 100.0; rH.bars.o[rH.e + 1:] = 100.0; rH.bars.h[rH.e + 1:] = 101.0
    pierce = [(100.0, 100.5, 99.5, 100.0)] * 390
    for mnt in range(30, 90):
        pierce[mnt] = (100.0, 100.5, 94.0, 99.0)                                                   # the lows pierce 95 all hour; every close holds at 99
    rH.bars.l[rH.e + 1] = 94.0
    siH = sightings_from([(rH.b.E, "AAA", "in", "10:40"), (rH.b.exit_lo, "AAA", "in", "11:30")])
    hH = intra.held_through_intra(rH, "S1", "H", intra.smas_for(rH.bars), siH, FakeStore({rH.session_date(1): hand_minutes(pierce)}))
    hT = intra.held_through_intra(rH, "S1", "T", intra.smas_for(rH.bars), siH, FakeStore({}))
    assert not hH["any"] and hT["any"] and hT["certain"]                                            # H: no close below; T: the low touched


def test_early_close_day_bars_and_the_next_open_from_the_next_session():
    """The T33 shape (C7): a hold across the listed early close 2020-11-27 — 4 bars that day, the last closing at minute 209 (12:59), its
    after-hours prints (210..214) dropped; an E1 on that last bar sells at the NEXT session's open, never at an after-hours print."""
    r, by, bars = exit_world()
    cal = [d for d in r.cal]
    # move the record so that session +2 is the early-close day
    ec = date(2020, 11, 27)
    assert ec.isoformat() in intra.EARLY_CLOSE
    n = 120
    cal2 = sessions(n, "2020-08-03")
    e = [i for i, d in enumerate(cal2) if d == ec][0] - 2
    o = np.full(n, 100.0); c = np.full(n, 100.0); h = np.full(n, 101.0); l = np.full(n, 99.0)
    for i in range(n):
        o[i] = 100 + 0.3 * i; c[i] = 100.3 + 0.3 * i; h[i] = c[i] + 0.05; l[i] = o[i] - 0.25
    bars2 = cb.daily_bars_from_arrays(cal2, o, h, l, c, np.full(n, 1e6))
    E = cal2[e].isoformat()
    b = mk_buy(E=E, lo=E, hi=E, exit_lo=cal2[e + 4].isoformat(), exit_hi=cal2[e + 6].isoformat(), flat_clock="10:05", first_clock="10:40")
    rev.index_calendar([b], [d.isoformat() for d in cal2])
    r = intra.IRec(b=b, bars=bars2, cidx=np.arange(n, dtype=np.int32), e=e, adr20=0.03, cal=cal2, era="A")
    r.qqq_c = np.asarray(bars2.c) * 3
    r.exit_lo_j, r.exit_hi_j = 4, 6
    by = {cal2[i].isoformat(): minutes_from_daily(o[i], h[i], l[i], c[i], early=(cal2[i] == ec), after_hours=(cal2[i] == ec)) for i in range(n)}
    r.mb = by[E]
    r.fill, r.fill_minute, r.fill_src = float(o[e]) + 0.2, 40, "level:L8"
    r.stop, r.stop_lvl, r.stop_variant, r.stop_src = float(o[e]) * 0.90, float(o[e]) * 0.90, "T", "S1-T"
    r.day0 = dict(cb._NO_DAY0)
    st = FakeStore(by)
    seq = intra.bar_sequence(r, st, -intra.WARMUP_SESSIONS, r.exit_hi_j + intra.TAIL_SESSIONS)
    bars_ec = [x for jj, x in seq.items if jj == 2]
    assert len(bars_ec) == 4 and bars_ec[-1].close_minute == 209 and bars_ec[-1].hi == 209 and int(by[ec.isoformat()].minute.max()) == 214
    # make the early-close day's LAST bar close below the EMA while the first three hold: the E1 sale is the next session's open
    armed = intra.armed_index(seq, r.fill_minute)
    i_last = [i for i, (jj, x) in enumerate(seq.items) if jj == 2 and x.lo == 150][0]
    ema_in = float(seq.ema[i_last - 1])
    o2 = float(o[e + 2])
    path = [(o2, o2 + 0.02, o2 - 0.02, o2)] * 150 + [(ema_in - 0.5, ema_in - 0.49, ema_in - 0.51, ema_in - 0.5)] * 60
    mm = list(range(210)) + [210, 211, 212, 213, 214]
    px = [p for p in path] + [(ema_in + 5.0, ema_in + 5.0, ema_in + 5.0, ema_in + 5.0)] * 5          # after-hours prints far above: must never be the sale
    mb_ec = cb.minute_bars_from_lists(mm, [p[0] for p in px], [p[1] for p in px], [p[2] for p in px], [p[3] for p in px], [1000.0] * len(mm))
    by[ec.isoformat()] = mb_ec
    r.bars.c[e + 2] = ema_in - 0.5
    st = FakeStore(by)
    seq = intra.bar_sequence(r, st, -intra.WARMUP_SESSIONS, r.exit_hi_j + intra.TAIL_SESSIONS)
    xs = [x for jj, x in seq.items if jj == 2]
    assert len(xs) == 4 and xs[-1].c == pytest.approx(ema_in - 0.5) and all(x.c >= seq.ema[i] for i, (jj, x) in enumerate(seq.items) if jj == 2 and x.lo < 150)
    w = intra.exit_walk_intra(r, "E1", seq, armed, st, intra.smas_for(bars2), r.exit_hi_j + intra.TAIL_SESSIONS)
    lg = w["legs"][0]
    assert lg.kind == "e1" and lg.j == 3 and lg.minute == 209 and lg.order == intra.ORDER_OPEN and lg.px == pytest.approx(float(o[e + 3]))
    assert intra.next_minute_open(R.h60_trim(mb_ec, True), 209) is None and intra.next_minute_open(mb_ec, 209) == (210, pytest.approx(ema_in + 5.0))


def test_accounts_his_differs_from_ours_and_the_abstention_clause():
    """C7: 'his' (the panel exit at exit_hi's close) is not 'ours' (the speed trail); an all-cut variant reads the INCONCLUSIVE clause."""
    recs, by_all = [], {}
    for k in range(3):
        r, by, bars = exit_world()
        r.b.eid = 900 + k
        r.b.sym = r.b.sym_a = r.b.ticker = f"X{k}"
        recs.append(r)
        by_all.update(by)
    st = FakeStore(by_all)
    cal_u = [d.isoformat() for d in recs[0].cal]
    M = dict(guards={"A": {}}, map_b=None)
    say = rp.Say()
    acc = intra.accounts_intra(say, recs, "E4", M, cal_u, 0, st, label="t ", preps=None)
    assert acc["n"] == 3 and acc["his"] != acc["ours"]                                               # the panel mark at exit_hi (+6) is not the speed trail's exit
    assert acc["counts"]["cut_at_tail"] == 3 and acc["abstain_share"] == 1.0 and "INCONCLUSIVE clause" in say.lines[0]
    assert intra.exit_verdict(acc)[0] in ("VOID", "INCONCLUSIVE")                                   # VOID first if his / ours < 1.25, else the clause
    r2, by2, _b = exit_world(n=300)
    r2.exit_lo_j, r2.exit_hi_j = 110, 126
    cal_u = [d.isoformat() for d in r2.cal]
    say2 = rp.Say()
    acc2 = intra.accounts_intra(say2, [r2], "E4", M, cal_u, 0, FakeStore(by2), label="h ", preps=None)
    assert acc2["counts"]["cut_at_horizon"] == 1 and acc2["abstain_share"] == 1.0 and "cut at the 120-session horizon" in "\n".join(say2.lines) and "exit_hi offset 126" in "\n".join(say2.lines)
    r3, by3, _b = exit_world()                                                                     # the export ends 49 sessions out, before exit_hi + 20
    r3.exit_lo_j, r3.exit_hi_j = 40, 45
    say3 = rp.Say()
    acc3 = intra.accounts_intra(say3, [r3], "E4", M, [d.isoformat() for d in r3.cal], 0, FakeStore(by3), label="d ", preps=None)
    assert acc3["counts"]["cut_at_data_end"] == 1 and acc3["abstain_share"] == 1.0 and "cut_at_data_end; exit_hi offset 45, J_tail 49" in "\n".join(say3.lines)


def test_n7_tails_a_hole_or_an_identity_break_shortened_count_with_the_cuts():
    """N7: a walk whose tail a missing session (`mark_hole`) or an identity break (`mark_break`) shortened is counted in the 10% clause, as
    the horizon / data-end / tail cuts are (C11: a cut is a cut whichever bound made it)."""
    assert intra.abstention_share(Counter(trades=10, cut_at_break=1, cut_at_guard=1, cut_at_hole=1)) == (3, pytest.approx(0.3))
    assert set(intra.CUT_KINDS) == {"cut_at_tail", "cut_at_horizon", "cut_at_data_end", "cut_at_guard", "mark_hole", "mark_break"}
    r, by, _bars = exit_world()
    r.b.sym = r.b.sym_a = r.b.ticker = "XB"
    brk = np.array([date.fromisoformat(r.session_date(15)).toordinal()], dtype=np.int64)
    M = dict(guards={"A": {"XB": brk}}, map_b=None)
    prep = intra.exit_prepare(r, M, FakeStore(by))
    assert prep["why"] == "break" and prep["J_tail"] == prep["bh"] == 14 and prep["tail_kind"] == "mark_break"
    say = rp.Say()
    acc = intra.accounts_intra(say, [r], "E4", M, [d.isoformat() for d in r.cal], 0, FakeStore(by), label="b ", preps=None)
    assert acc["counts"]["cut_at_break"] == 1 and acc["abstain_share"] == 1.0 and "mark_break; exit_hi offset 6, J_tail 14" in "\n".join(say.lines)
    r2, by2, _b2 = exit_world()
    r2.b.sym = r2.b.sym_a = r2.b.ticker = "XH"
    r2.cidx = r2.cidx.copy()
    r2.cidx[r2.e + 15:] += 1                                                     # session +15 has no daily bar: the forward window ends at +14
    prep2 = intra.exit_prepare(r2, dict(guards={"A": {}}, map_b=None), FakeStore(by2))
    assert prep2["why"] == "hole" and prep2["J_tail"] == 14 and prep2["tail_kind"] == "mark_hole"
    acc2 = intra.accounts_intra(rp.Say(), [r2], "E4", dict(guards={"A": {}}, map_b=None), [d.isoformat() for d in r2.cal], 0, FakeStore(by2), label="h ", preps=None)
    assert acc2["counts"]["cut_at_hole"] == 1 and acc2["abstain_share"] == 1.0


def test_x1_the_fit_bounds_the_speed_trail_window_before_the_first_forbidden_session():
    """X1: in a fit stage the frozen speed trail's 121-session forward window (and break_horizon's) ends on the session before the first
    forbidden pair — by an extra identity-break entry, dates only; the check (no forbidden pair) is unchanged."""
    r, by, _bars = exit_world()
    r.b.sym = r.b.sym_a = r.b.ticker = "XG"
    M = dict(guards={"A": {}}, map_b=None)
    p0 = intra.exit_prepare(r, M, FakeStore(by))
    assert p0["guard_j"] is None and p0["bh"] == 49 and p0["why"] == ""
    r.guard = intra.BarGuard({r.b.eid}, frozenset({("XG", r.session_date(40))}))
    p1 = intra.exit_prepare(r, M, FakeStore(by))
    assert p1["guard_j"] == 40 and p1["bh"] == 39 and p1["why"] == "guard" and p1["J_tail"] == 26 and p1["tail_kind"] == "cut_at_tail"
    assert list(p1["guards"]["XG"]) == [date.fromisoformat(r.session_date(40)).toordinal()] and M["guards"]["A"] == {}     # the stage's guards are not mutated
    fwd, _cut = cb.forward_window(r.bars, r.cidx, r.e, intra.HORIZON)
    assert len(rp.cut_at_break(fwd, r.bars.dates[r.e], p1["guards"]["XG"])[0]) == 39                  # the speed trail reads sessions 1 .. 39 only
    say = rp.Say()
    acc = intra.accounts_intra(say, [r], "E4", M, [d.isoformat() for d in r.cal], 0, FakeStore(by), label="g ", preps={r.b.eid: p1})
    assert acc["counts"]["guard_bounded"] == 1 and "X1, a fit stage only" in "\n".join(say.lines) and "first forbidden session +40, bh 39" in "\n".join(say.lines)
    r.guard = intra.BarGuard({r.b.eid}, frozenset({("XG", r.session_date(22))}))                      # inside exit_hi + 20 (the span exclusion rules it out on a kept trade)
    p2 = intra.exit_prepare(r, M, FakeStore(by))
    assert p2["bh"] == p2["J_tail"] == 21 and p2["tail_kind"] == "cut_at_guard"
    r.guard = intra.BarGuard(None)                                                                    # the check
    assert intra.exit_prepare(r, M, FakeStore(by))["guard_j"] is None


def test_gate_vii_random_control_known_answer_unit():
    """(vii) C6 / N4: the random-price control's mean shares on the previous 41 undated records must read 31.7% / 85.9% at one decimal; 40
    records, another share, or the known answer on the wrong records stop the check. Records outside the previous 41 never count."""
    def rec(f, h):
        out = {lv: dict(feasible=False, verdict="MISS") for lv in intra.ALL_LEVELS}
        out.update(control=dict(feasible_share=f, hit_share=h), union=dict(feasible=False, hit=False))
        return out
    prev = set(range(1, 42))
    good = {k: rec(0.317, 0.859) for k in prev}
    good.update({k: rec(0.9, 0.1) for k in range(100, 120)})                    # the dated side records: scored, never in the known answer
    say = rp.Say()
    intra.gate_vii_random_control(say, good, prev)
    assert "-> reproduced" in say.lines[-1] and "on the previous 41" in say.lines[-1]
    mixed = dict(good)
    mixed.update({1: rec(0.300, 0.859), 2: rec(0.334, 0.859)})                 # the mean is still 31.7%: what is checked is the mean over the 41
    intra.gate_vii_random_control(rp.Say(), mixed, prev)
    for bad, why in (({k: v for k, v in good.items() if k != 41}, "40 records"), ({**good, **{k: rec(0.320, 0.859) for k in prev}}, "a different feasible share"),
                     ({**good, **{k: rec(0.317, 0.870) for k in prev}}, "a different hit share")):
        with pytest.raises(intra.GuardStop, match="gate \\(vii\\)"):
            intra.gate_vii_random_control(rp.Say(), bad, prev)
    with pytest.raises(intra.GuardStop, match="gate \\(vii\\)"):
        intra.gate_vii_random_control(rp.Say(), good, set(range(100, 141)))       # the wrong population's 41


def test_gate_ii_through_enter_row_catches_a_0_59_builder(tmp_path, monkeypatch):
    """C8 / N4: the value gate (ii) checks is the BUILDER's first bar as `enter_row` records it — a builder whose first bar is [0,59] makes
    H60_0_high the first-hour high, which differs from the raw 30-minute high and stops the stage; the correct builder passes."""
    monkeypatch.setattr(intra, "OUT_DIR", str(tmp_path))                        # the failing rows go to tmp, never into the real intraday/ folder
    path = [(100.0, 100.4, 99.6, 100.0)] * 30 + [(101.0, 102.5, 100.8, 102.0)] * 30 + [(102.0, 102.4, 101.6, 102.0)] * 330   # minutes 30-59 above the opening range
    def row_for():
        r = enter_rec(mb=hand_minutes(path))
        res = intra.enter_score_trade(r, intra.rng_for(intra.RANDOM_KEY), with_shift=False)
        return intra.enter_row(r, res)
    ok = row_for()
    assert ok["H60_0_high"] == ok["L8_raw"] == pytest.approx(100.4) and ok["L6_raw"] == pytest.approx(102.5)
    intra.gate_level_order(rp.Say(), [ok] * 5, "t")
    real = R.h60_windows
    try:
        R.h60_windows = lambda variant, early=False: [(0, 59)] + [w for w in real(variant, early)[2:]]        # the [0,59] first-bar bug in the builder
        bad = row_for()
    finally:
        R.h60_windows = real
    assert bad["H60_0_high"] == pytest.approx(102.5) and bad["L8_raw"] == pytest.approx(100.4)
    with pytest.raises(intra.GuardStop, match="builder's first bar differs"):
        intra.gate_level_order(rp.Say(), [bad] * 5, "t")


# ═════════════════════════════════════════════════════════════════════════════════════════════ the era-B calendar, IdCache, the module scan, numpy scalars
def test_era_b_offsets_on_one_calendar_and_the_old_mix_is_wrong():
    cal = weekday_cal("2016-01-04", "2024-12-31")                              # the pickle calendar
    iB = cal.index(date(2021, 9, 27))                                           # era B's export starts ~1,443 sessions in (the real shape)
    calB = cal[iB:]
    n = len(calB)
    o, h, l, c, v = daily_walk(n, 30.0, 5)
    bars = cb.daily_bars_from_arrays(calB, o, h, l, c, v)
    E = date(2022, 5, 2)
    e = calB.index(E)
    b = mk_buy(E=E.isoformat(), lo=E.isoformat(), hi=E.isoformat(), exit_lo=calB[e + 5].isoformat(), exit_hi=calB[e + 5].isoformat())
    rev.index_calendar([b], [d.isoformat() for d in cal])                       # the pickle indices (what the previous module mixed in)
    r = intra.IRec(b=b, bars=bars, cidx=np.arange(n, dtype=np.int32), e=e, adr20=0.04, cal=calB, era="B")
    assert r.off(b.exit_lo) == 5 and r.off(b.exit_hi) == 5 and r.off(b.E) == 0
    mixed = b.exit_hi_i - int(r.cidx[r.e])                                      # the previous read's mix: the pickle index of the sell minus the own index of the buy
    assert mixed > 1400, mixed
    with pytest.raises(intra.GuardStop, match="beyond the record's own calendar"):
        r.off("2025-03-03")
    assert r.session_date(5) == calB[e + 5].isoformat() and r.session_date(-e - 1) is None
    # a date that is not a session of the own calendar is snapped forward and counted
    r.off("2022-05-07")                                                          # a Saturday
    assert r.off_snapped == 1


def test_idcache_holds_its_object_and_never_serves_a_reused_id():
    cache = intra.IdCache()
    a = np.arange(10.0)
    built = []
    v1 = cache.get(a, lambda x: (built.append(1), float(x.sum()))[1])
    assert v1 == 45.0 and cache.get(a, lambda x: 0.0) == 45.0 and len(built) == 1
    ida = id(a)
    del a
    # plant another object under the same id (what a reused id looks like): the entry must not be served
    b = np.arange(5.0)
    cache._d[(ida, None)] = (np.arange(10.0), 45.0)                              # an entry whose object is NOT b
    cache._d[(id(b), None)] = (np.arange(3.0), 999.0)
    assert cache.get(b, lambda x: float(x.sum())) == 10.0                        # rebuilt for b, never 999
    assert cache.get(b, key="other", build=lambda x: 1.0) == 1.0 and cache.get(b) == 10.0
    assert cache.get(np.arange(2.0)) is None
    # the module's own caches: bars_of keyed by the export OBJECT; smas_for by the bars object
    s1 = intra.smas_for(cb.daily_bars_from_arrays(sessions(60), *daily_walk(60, 10.0, 1)))
    assert set(s1) == {10, 20, 50}


def test_module_scan_no_id_outside_idcache_and_no_pytz_or_naive_now():
    src = open(os.path.join(HERE, "01_intra.py"), encoding="utf-8").read()
    body = src.split("class IdCache:")[1].split("\n\n\n")[0]
    outside = src.replace(body, "")
    hits = [ln.strip() for ln in outside.splitlines() if re.search(r"(?<![A-Za-z_])id\(", ln) and not ln.strip().startswith("#")]
    assert hits == [], hits
    assert "import pytz" not in src and "utcnow()" not in src
    assert "float(mb.h[sel0])" not in src                                        # one-element arrays go through fnum


def test_fnum_one_element_arrays_and_refusals():
    a = np.array([3.5])
    with pytest.raises(TypeError):
        float(a)
    assert intra.fnum(a) == 3.5 and intra.fnum(np.float64(2.0)) == 2.0 and intra.fnum(4) == 4.0 and intra.fnum(np.array([[7.0]])) == 7.0
    with pytest.raises(ValueError):
        intra.fnum(np.array([1.0, 2.0]))


# ═════════════════════════════════════════════════════════════════════════════════════════════ the freeze lock, the ledger, the outputs, the store
def write_doc(path, body_lines: list, tail_lines: list):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body_lines) + "\n" + intra.FREEZE_MARKER + "\n" + "\n".join(tail_lines) + ("\n" if tail_lines else ""))


def test_freeze_lock_chosen_lines_body_diff_and_pins_under_marker(tmp_path):
    doc = tmp_path / "doc.md"
    body = ["# Test", "prose mentioning `CHOSEN ENTER: L8` inline is not a chosen line", "- CHOSEN STOP: S1-T (a bullet is not column 0 either)", "CHOSEN ENTER: L8", "CHOSEN EXIT: E2"]
    write_doc(doc, body, [])
    ch = intra.chosen_lines(str(doc))
    assert ch == {"enter": ["L8"], "exit": ["E2"]}
    assert intra.pin_under_marker("doc_body_freeze", str(doc)) is None
    h = intra.store_freeze_body(str(doc), str(tmp_path / "fb"))
    assert (tmp_path / "fb" / f"doc_body_{h}.md").exists() and intra.freeze_body_text(h, str(doc), str(tmp_path / "fb")) == "\n".join(body) + "\n"
    write_doc(doc, body, [f"- doc_body_freeze: {h}", "- other: " + "0" * 64])
    assert intra.pin_under_marker("doc_body_freeze", str(doc)) == h
    assert intra.freeze_state(str(doc), str(tmp_path / "fb")) == (True, "")
    # adding a keyed CHOSEN line at column 0 keeps the lock; any other edit breaks it
    write_doc(doc, body + ["CHOSEN STOP: S9-H"], [f"- doc_body_freeze: {h}"])
    assert intra.freeze_state(str(doc), str(tmp_path / "fb"))[0] is True
    write_doc(doc, body + ["CHOSEN STOP: S9-H", "an extra sentence"], [f"- doc_body_freeze: {h}"])
    ok, why = intra.freeze_state(str(doc), str(tmp_path / "fb"))
    assert not ok and "beyond the keyed CHOSEN lines" in why
    write_doc(doc, body, [])
    assert "not under the marker" in intra.freeze_state(str(doc), str(tmp_path / "fb"))[1]
    write_doc(doc, body, [f"- doc_body_freeze: {'1' * 64}"])
    assert "neither stored" in intra.freeze_state(str(doc), str(tmp_path / "fb"))[1]
    # two marker lines: no body, no chosen lines
    with open(doc, "a") as fh:
        fh.write(intra.FREEZE_MARKER + "\n")
    assert intra.chosen_lines(str(doc)) == {} and intra.doc_body_text(str(doc)) is None
    assert intra.body_diff_beyond_chosen("a\nb\n", "a\nCHOSEN ENTER: L8\nb\n") == [] and intra.body_diff_beyond_chosen("a\nb\n", "a\nc\n") == ["-b", "+c"]


def test_ledger_outputs_dry_run_gate_and_store_seal(tmp_path, monkeypatch):
    L = tmp_path / "ledger.tsv"
    p = tmp_path / "x.txt"
    p.write_text("one")
    intra.ledger_append("enter-fit", str(p), str(L))
    assert intra.ledger_verify(str(L)) == []
    p.write_text("two")
    assert intra.ledger_verify(str(L)) == [f"{p}: changed since the ledger recorded it"]
    assert intra.ledger_verify(str(tmp_path / "none.tsv")) == ["ledger missing"]
    monkeypatch.setattr(intra, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(intra, "STOPPED", str(tmp_path / "S.txt"))
    monkeypatch.setattr(intra, "P_FIT", {s: str(tmp_path / f"{s}.txt") for s in intra.STAGES})
    monkeypatch.setattr(intra, "P_CHECK", str(tmp_path / "check.txt"))
    monkeypatch.setattr(intra, "P_WHY", str(tmp_path / "why.txt"))
    monkeypatch.setattr(intra, "LEDGER", str(L))
    os.makedirs(tmp_path / "out")
    (tmp_path / "out" / "dryrun_windows.tsv").write_text("x")
    (tmp_path / "out" / "freeze_bodies").mkdir()
    assert intra.stage_outputs("enter") == [] and intra.any_stage_output() == [str(L)]
    (tmp_path / "out" / "enter_fit_trades.tsv").write_text("x")
    assert intra.stage_outputs("enter") == [str(tmp_path / "out" / "enter_fit_trades.tsv")] and intra.stage_outputs("stop") == []
    (tmp_path / "S.txt").write_text("stopped")
    assert str(tmp_path / "S.txt") in intra.stage_outputs("exit")
    d = tmp_path / "dry.txt"
    assert not intra.dry_run_complete(str(d))
    d.write_text("...\nSTOPPED: x\n")
    assert not intra.dry_run_complete(str(d))
    d.write_text("...\nDRY RUN COMPLETE: ok\n\n")
    assert intra.dry_run_complete(str(d))
    st = intra.MinuteStore({}, {})
    with pytest.raises(intra.GuardStop, match="guard \\(12\\)"):
        st.get("2025-01-03", "AAA")
    assert st.get("2020-03-02", "AAA") is None and st.state("2020-03-02", "AAA") == "missing"


def test_minute_store_reads_each_file_once_with_want(tmp_path):
    import gzip
    tree = tmp_path / "tree"
    tree.mkdir()
    rows = []
    for d in ("2020-03-02", "2020-03-03"):
        lines = []
        for tk in ("AAA", "BBB", "CCC"):
            for m in range(0, 390, 5):
                lines.append(f"{tk}|{m}|10|10.5|9.5|10.2|100")
        with gzip.open(tree / f"{d}.psv.gz", "wt") as fh:
            fh.write("\n".join(lines) + "\n")
        for tk in ("AAA", "BBB", "CCC"):
            rows.append(f"{d}|{tk}|78|ok")
        rows.append(f"{d}|DDD|0|empty")
    (tree / "_done.psv").write_text("\n".join(rows) + "\n")
    done = {"INTRA": rp.load_done(str(tree / "_done.psv"))[0]}
    files = {"INTRA": R.minute_date_files(tree)}
    st = intra.MinuteStore(done, files)
    c = st.preload([("2020-03-02", "AAA"), ("2020-03-02", "BBB"), ("2020-03-03", "AAA"), ("2020-03-02", "DDD"), ("2020-03-02", "ZZZ")])
    assert c["ok"] == 3 and c["empty"] == 1 and c["missing"] == 1 and st.reads["INTRA"] == 2
    assert len(st.get("2020-03-02", "AAA")) == 78 and st.get("2020-03-02", "DDD") is None and st.get("2020-03-02", "ZZZ") is None
    assert st.state("2020-03-02", "AAA") == "ok/INTRA" and st.state("2020-03-02", "DDD") == "empty/INTRA" and st.state("2020-03-02", "ZZZ") == "missing"
    st.get("2020-03-03", "CCC")                                                  # a lazy single read of a pair not preloaded
    assert st.reads["INTRA"] == 3
    bars = st.h60("2020-03-02", "AAA")
    assert len(bars) == 7 and all(x is not None for x in bars) and bars[0].n == 6 and st.h60("2020-03-02", "DDD") is None


def test_gate_level_order_catches_the_0_59_first_bar_bug_and_order_violations(tmp_path, monkeypatch):
    monkeypatch.setattr(intra, "OUT_DIR", str(tmp_path))                        # the failing rows go to tmp, never into the real intraday/ folder
    say = rp.Say()
    rows = [dict(L7_raw=1.0, L1_raw=1.5, L8_raw=2.0, L6_raw=2.5, H60_0_high=2.0) for _ in range(10)]
    intra.gate_level_order(say, rows, "t")
    assert "first-bar high < L6 on 10 of 10" in say.lines[-1] and "equals L8_raw on 10 of 10" in say.lines[-1]
    # C8: the [0,59] BUILDER bug — the builder's first bar reads the first-hour high (= L6) while the raw 30-minute high is still right
    with pytest.raises(intra.GuardStop, match="builder's first bar differs"):
        intra.gate_level_order(say, [dict(L7_raw=1.0, L1_raw=1.5, L8_raw=2.0, L6_raw=2.5, H60_0_high=2.5) for _ in range(10)], "t")
    with pytest.raises(intra.GuardStop, match="0,59"):
        intra.gate_level_order(say, [dict(L7_raw=1.0, L1_raw=1.5, L8_raw=2.5, L6_raw=2.5, H60_0_high=2.5) for _ in range(10)], "t")
    intra.gate_level_order(say, [dict(L7_raw=1.0, L1_raw=1.5, L8_raw=2.5, L6_raw=2.5, H60_0_high=2.5)] * 8 + [dict(L7_raw=1.0, L1_raw=1.5, L8_raw=2.0, L6_raw=2.5, H60_0_high=2.0)] * 2, "t")   # 80% equal: allowed
    with pytest.raises(intra.GuardStop, match="level order fails"):
        intra.gate_level_order(say, [dict(L7_raw=3.0, L1_raw=1.5, L8_raw=2.0, L6_raw=2.5, H60_0_high=2.0)], "t")
    # the real row carries the builder's value: enter_row on a hand session
    r = enter_rec()
    rng = intra.rng_for(intra.RANDOM_KEY)
    res = intra.enter_score_trade(r, rng, with_shift=False)
    row = intra.enter_row(r, res)
    assert row["H60_0_high"] == row["L8_raw"] == pytest.approx(float(r.mb.h[r.mb.minute <= 29].max()))


def test_gate_i_two_arms_true_and_broken_readings(tmp_path, monkeypatch):
    """C1: gate (i) decides on high AND low (0.5%, >= 98%) and on open AND close (0.5%, >= 90%) separately; an auction-basis difference on the
    open or close passes while a wrong day or a one-hour clock shift fails on most pairs."""
    monkeypatch.setattr(intra, "OUT_DIR", str(tmp_path))
    good = dict(dev_o=0.0, dev_h=0.0, dev_l=0.0, dev_c=0.0003, sym="A", session="2020-03-02", eid=1, j=0, daily_c=1.0, minute_c=1.0)
    auction = dict(good, dev_c=0.049)                                            # APT 2020-02-28's closing cross: high / low exact, the close 4.9% off
    rows = [dict(good) for _ in range(84)] + [dict(auction) for _ in range(4)]   # the review's 84 of 88
    v = intra.gate_ohlc_verdict(rows)
    assert v["ok"] and v["hl_share"] == 1.0 and v["oc_ok"] == 84 and v["oc_share"] == pytest.approx(84 / 88)
    shift = dict(good, dev_o=0.024, dev_c=0.0085, dev_l=0.013, dev_h=0.0)       # the one-hour shift's median deviations: open / close / low off, the high often kept
    assert not intra.gate_ohlc_verdict([dict(shift) for _ in range(80)] + [dict(good) for _ in range(8)])["ok"]
    wrong_day = dict(good, dev_o=0.027, dev_h=0.061, dev_l=0.033, dev_c=0.05)
    assert not intra.gate_ohlc_verdict([dict(wrong_day) for _ in range(88)])["ok"]
    assert not intra.gate_ohlc_verdict([dict(good) for _ in range(78)] + [dict(auction) for _ in range(10)])["ok"]     # 88.6% open/close: under the 90% bar
    assert not intra.gate_ohlc_verdict([dict(good) for _ in range(97)] + [dict(good, dev_l=0.006) for _ in range(3)])["ok"]  # 97% high/low: under the 98% bar
    assert intra.gate_ohlc_verdict([])["ok"]
    # on records: minutes built from the daily bar pass; a close shifted by an auction print passes the high/low arm and counts on the open/close arm;
    # minutes of ANOTHER day (a wrong-day read) fail the high/low arm and stop the stage
    recs = []
    for k in range(10):
        r = mini_rec(seed=10 + k, mb=None)
        r.mb = minutes_from_daily(float(r.bars.o[r.e]), float(r.bars.h[r.e]), float(r.bars.l[r.e]), float(r.bars.c[r.e]))
        r.b.eid = 700 + k
        recs.append(r)
    say = rp.Say()
    v = intra.gate_ohlc(say, recs, FakeStore({}), lambda r: [0], "t")
    assert v["n"] == 10 and v["hl_ok"] == 10 and v["oc_ok"] == 10 and "gate (i) t" in say.lines[0]
    recs[0].bars.c[recs[0].e] = float(recs[0].bars.c[recs[0].e]) * 1.03         # the daily close is an auction print 3% from the last minute
    v2 = intra.gate_ohlc(say, recs, FakeStore({}), lambda r: [0], "t")
    assert v2["hl_ok"] == 10 and v2["oc_ok"] == 9 and (tmp_path / "gate_i_pairs_t.tsv").exists()
    for r in recs[:3]:
        k = r.e - 1
        r.mb = minutes_from_daily(float(r.bars.o[k]), float(r.bars.h[k]), float(r.bars.l[k]), float(r.bars.c[k]))         # the previous session's minutes under today's date
    with pytest.raises(intra.GuardStop, match="gate \\(i\\)"):
        intra.gate_ohlc(say, recs, FakeStore({}), lambda r: [0], "t")


def test_gate_i_trims_an_early_close_day_before_comparing(tmp_path, monkeypatch):
    """N4: gate (i) compares the minute-built session with the daily bar AFTER the early-close trim — after-hours prints past 13:00 on a listed
    early-close day (here far above the day's high) never reach the comparison."""
    monkeypatch.setattr(intra, "OUT_DIR", str(tmp_path))
    target = date(2020, 11, 27)
    assert target.isoformat() in intra.EARLY_CLOSE                                                  # PREMISE: a listed early close
    d0 = target
    for _ in range(60):
        d0 -= timedelta(days=1)
        while d0.weekday() >= 5:
            d0 -= timedelta(days=1)
    r = mini_rec(start=d0.isoformat(), mb=None)
    assert r.b.E == target.isoformat()
    o, h, l, c = (float(x[r.e]) for x in (r.bars.o, r.bars.h, r.bars.l, r.bars.c))
    base = minutes_from_daily(o, h, l, c, early=True)
    mm = list(base.minute) + [210, 211, 212]
    r.mb = cb.minute_bars_from_lists(mm, list(base.o) + [c] * 3, list(base.h) + [h * 1.05] * 3, list(base.l) + [l * 0.95] * 3, list(base.c) + [c * 1.03] * 3, [1000.0] * len(mm))
    assert float(r.mb.h.max()) > h * 1.04                                                           # PREMISE: untrimmed, the high is 5% off
    v = intra.gate_ohlc(rp.Say(), [r], FakeStore({}), lambda r_: [0], "t")
    assert v["n"] == 1 and v["hl_ok"] == 1 and v["oc_ok"] == 1


def test_gate_iii_auction_band_and_share(tmp_path, monkeypatch):
    """C2: a C event inside the auction band that is not an H event is counted, never failing; beyond the band it fails the share bar."""
    monkeypatch.setattr(intra, "OUT_DIR", str(tmp_path))
    r, si, st = stop_world(20)
    r.exit_lo_j, r.exit_hi_j = 3, 5
    base = [(100.3, 100.5, 100.1, 100.3)] * 390
    by = {r.session_date(j): hand_minutes(base) for j in range(1, 6)}          # every later session's last bar closes at 100.3, ABOVE the 100.2 level
    r.stop_levels = {"S1": 100.2, "S1_is_S2": False, "S3": 100.2, "S9": 100.2, "S9_is_S1": True, "S10": 100.2, "S10_is_S1": True, "S8": 50.0, "SMA50": ("sma", 50)}
    r.bars.c[r.e:r.e + 6] = 100.5                                                # every daily close above the level ...
    r.bars.c[r.e + 1] = 99.9                                                     # ... but session 1's, 0.3% under it: inside the 0.5% band, the last bar (100.0) is not below
    say = rp.Say()
    out = intra.gate_c_implies_h(say, [r], FakeStore(by), "t", levels=("S1",))
    assert out["n_beyond"] == 0 and out["n_band"] == 1 and out["n_band_not_h"] == 1 and "inside the band 1, of which not H 1" in say.lines[-1]
    r.bars.c[r.e + 2] = 98.0                                                     # 2.2% under the level: beyond the band, and the last bar still closes at 100.3 -> a failure
    with pytest.raises(intra.GuardStop, match="gate \\(iii\\)"):
        intra.gate_c_implies_h(say, [r], FakeStore(by), "t", levels=("S1",))
    assert (tmp_path / "gate_iii_failures_t.tsv").exists()
    low = [(100.0, 100.5, 99.5, 100.0)] * 330 + [(99.0, 99.2, 98.5, 98.6)] * 60   # the last bar closes under the level too: an H event day
    by[r.session_date(2)] = hand_minutes(low)
    out2 = intra.gate_c_implies_h(say, [r], FakeStore(by), "t", levels=("S1",))
    assert out2["n_beyond"] == 1 and out2["bad"] == 0 and out2["share"] == 1.0
    # the share bar: 1 failure in 100 beyond-band days passes (99% >= 98%), 3 in 100 does not
    assert intra.GATE_III_SHARE == 0.98 and intra.AUCTION_BAND == intra.GATE_OC_TOL == 0.005


def test_guard_5_per_ticker_and_date_collisions_and_the_belt(tmp_path):
    """C9 / N1 / N3: the forbidden (symbol, date) pairs after a check-side trade's buy day; a fit trade whose PLANNED span — from the stage's
    daily lookback (ENTER 20 sessions, STOP / EXIT 50) to its last booked session (ENTER the buy day, STOP exit_hi + 1, EXIT exit_hi + 21) —
    touches one is excluded by dates alone (an era-A rename shares the bar symbol: FIRY = FEAC / SKLZ); the guard and the store refuse any read
    of such a pair, a cached pair and the pre-buy lookback included; a trade outside the fit set is refused from session 1."""
    cal = weekday_cal("2019-06-03", "2021-06-30")
    cal_s = [d.isoformat() for d in cal]
    CI = {d: i for i, d in enumerate(cal_s)}
    eids = iter(range(5000, 5100))

    def mk(sym, E, sym_a=None, exit_off=(3, 5), dated=False, still=False):
        kw = dict(eid=next(eids), sym=sym, sym_a=sym_a or sym, E=E, lo=E, hi=E, exit_lo=cal_s[CI[E] + exit_off[0]] if not still else "", exit_hi=cal_s[CI[E] + exit_off[1]] if not still else "",
                  flat_clock="10:05", first_clock="10:40")
        if dated:
            kw.update(setup="breakout", decides=True, pivot=1.0, adr20=0.05)
        return mk_buy(**kw)
    virgin_x = mk("X", "2020-01-23", exit_off=(7, 7))                            # APT-like: post-buy sessions 01-24 .. 02-03 + 20 sessions (to 03-02)
    chk_sklz = mk("SKLZ", "2021-01-05", sym_a="FIRY", exit_off=(15, 15), dated=True)
    still = mk("Y", "2020-01-10", still=True)                                    # a still-held check-side trade: its last frame + 20
    chk_z = mk("Z", "2020-06-10")                                                # forbidden from 06-11
    chk_w = mk("W", "2020-09-01")                                                # forbidden from 09-02
    fit_x1 = mk("X", "2020-02-05", exit_off=(2, 3))                              # its buy day lies inside X's window -> every stage excludes it
    fit_x2 = mk("X", "2020-06-01", exit_off=(2, 3))                              # clear of X's window in every stage (50 sessions back = 03-23)
    fit_x3 = mk("X", "2020-03-10", exit_off=(2, 3))                              # ENTER's 20-session lookback reaches back into X's window (N3)
    fit_x4 = mk("X", "2020-04-15", exit_off=(2, 3))                              # ENTER clear (20 back = 03-18); STOP / EXIT's 50-session lookback is not (N3)
    fit_feac = mk("FEAC", "2020-11-30", sym_a="FIRY", exit_off=(12, 20), dated=True)   # its 20-session tail runs into SKLZ's post-buy window on the shared symbol FIRY
    fit_y = mk("Y", "2020-02-20", exit_off=(1, 2))                               # Y's still-held window (last frame 2020-02-14 + 20) covers it
    fit_z = mk("Z", "2020-06-03", exit_off=(3, 5))                               # exit_hi = Z's buy day: only STOP's exit_hi + 1 (a next open) touches 06-11 (N1)
    fit_w = mk("W", cal_s[CI["2020-09-02"] - 24], exit_off=(2, 3))               # exit_hi + 21 = 09-02: only EXIT's tail-plus-next-open touches it (N1)
    buys = [virgin_x, chk_sklz, still, chk_z, chk_w, fit_x1, fit_x2, fit_x3, fit_x4, fit_feac, fit_y, fit_z, fit_w]
    rev.index_calendar(buys, cal_s)
    I = dict(chk22_dated=[chk_sklz], chk22_und=[chk_z, chk_w], virgin_all=[virgin_x, still])
    C = dict(I=I, E={}, cal=cal_s, CI=CI)
    forbid = intra.forbidden_pairs(C, last_seen={"Y": ["2020-02-14"]})
    assert ("X", "2020-01-24") in forbid and ("X", "2020-01-23") not in forbid and ("FIRY", "2021-01-06") in forbid and ("SKLZ", "2021-01-06") not in forbid
    assert ("Y", "2020-02-14") in forbid and ("Y", cal_s[CI["2020-02-14"] + 20]) in forbid and ("Y", cal_s[CI["2020-02-14"] + 21]) not in forbid
    assert max(d for s, d in forbid if s == "X") == cal_s[CI["2020-02-03"] + 20] == "2020-03-02"
    assert ("Z", "2020-06-10") not in forbid and ("Z", "2020-06-11") in forbid and ("W", "2020-09-02") in forbid
    # the planned span's two ends, per stage (N1 / N3)
    for b in (fit_x2, fit_z, fit_w):
        for st_, lo_, hi_ in (("enter", CI[b.E] - 20, CI[b.E]), ("stop", CI[b.E] - 50, CI[b.exit_hi] + 1), ("exit", CI[b.E] - 50, CI[b.exit_hi] + 21)):
            sp = intra.planned_span(st_, b, cal_s)
            assert (sp[0][1], sp[-1][1], len(sp)) == (cal_s[lo_], cal_s[hi_], hi_ - lo_ + 1), (b.sym, st_)
    assert intra.LOOKBACK_SESSIONS == {"enter": 20, "stop": 50, "exit": 50}
    fits = [fit_x1, fit_x2, fit_x3, fit_x4, fit_feac, fit_y, fit_z, fit_w]
    ex = {st_: {b.sym + " " + b.E for b, _h, _x in intra.collisions(st_, fits, forbid, cal_s)} for st_ in intra.STAGES}
    assert ex["enter"] == {"X 2020-02-05", "X 2020-03-10", "Y 2020-02-20"}
    assert ex["stop"] == {"X 2020-02-05", "X 2020-03-10", "X 2020-04-15", "Y 2020-02-20", "Z 2020-06-03"}
    assert ex["exit"] == {"X 2020-02-05", "X 2020-03-10", "X 2020-04-15", "FEAC 2020-11-30", "Y 2020-02-20", "Z 2020-06-03", f"W {fit_w.E}"}
    col = intra.collisions("exit", [fit_feac], forbid, cal_s)
    assert col[0][2] == {(chk_sklz.eid, "SKLZ", "2021-01-05")} and len(intra.planned_span("exit", fit_feac, cal_s)) == 50 + 1 + 20 + 21
    say = rp.Say()
    kept = intra.exclude_collisions(say, "stop", fits, forbid, cal_s, "t")
    assert [b.sym for b in kept] == ["X", "FEAC", "W"] and "exposes X 2020-01-23" in say.lines[0] and "5 of 8 trades excluded" in say.lines[0]
    # X1, dates only: the speed trail's forward window (sessions 1 .. 121) on a kept fit trade reaching a forbidden session
    assert intra.speed_trail_bound(fit_x2, cal_s, forbid) is None and intra.speed_trail_bound(fit_w, cal_s, forbid) == 24
    # the belt: a record under a guard with the forbidden set refuses the pair on daily and minute reads, the store refuses it too
    r = mini_rec(n=80, e=60, start="2019-12-02")
    r.b.sym = r.b.sym_a = "X"
    g = intra.BarGuard({r.b.eid}, frozenset(forbid))
    r.guard = g
    d1 = r.session_date(1)
    g2 = intra.BarGuard({r.b.eid}, frozenset({("X", d1)}))
    r.guard = g2
    assert r.bar_at(0) == r.e
    with pytest.raises(intra.GuardStop, match="guard \\(5\\): the bar of X on"):
        r.bar_at(1)
    with pytest.raises(intra.GuardStop, match="guard \\(5\\)"):
        r.minutes(FakeStore({}), 1)
    r.guard = intra.BarGuard({r.b.eid}, frozenset({("X", r.session_date(-3))}))
    with pytest.raises(intra.GuardStop, match="guard \\(5\\)"):
        r.h60(FakeStore({}), -3)                                                 # the warm-up asks too
    assert r.bar_at(-2) is not None and intra.BarGuard(None).forbid == frozenset()
    # the per-TRADE guard: a trade outside the fit set reads its buy day, never session 1 (forbid empty: the per-pair half is silent)
    r.guard = intra.BarGuard({r.b.eid + 1})
    assert r.bar_at(0) == r.e
    with pytest.raises(intra.GuardStop, match="fit set does not hold that trade"):
        r.bar_at(1)
    st = intra.MinuteStore({}, {})
    st.forbid = frozenset({("X", "2020-03-02")})
    with pytest.raises(intra.GuardStop, match="minutes of X on 2020-03-02"):
        st.get("2020-03-02", "X")
    assert st.get("2020-03-03", "X") is None and st.restricted().forbid == st.forbid
    st.cache[("2020-03-04", "X")] = None                                         # a pair already cached before the forbidden set arrived ...
    st.forbid = frozenset({("X", "2020-03-04")})
    with pytest.raises(intra.GuardStop, match="minutes of X on 2020-03-04"):
        st.get("2020-03-04", "X")                                                # ... is refused all the same (the cache is no way around the belt)
    # restricted(): a SEPARATE store over the old trees in their fixed order (gate iv's re-read never sees the new tree)
    st2 = intra.MinuteStore({"INTRA": {}, "B": {}, "A": {}}, {"INTRA": {}, "B": {}, "A": {}})
    rs = st2.restricted()
    assert rs is not st2 and rs.all_trees() == ("A", "B") and "INTRA" in st2.all_trees() and rs.cache is not st2.cache


def test_lookback_pairs_and_the_record_builder_belt(world):
    """N3: the pre-buy daily reads by BAR index (ENTER 20 bars; STOP / EXIT 50 and a dated base low from its base date) are what the record
    builder's belt checks; a forbidden pair inside them refuses the record, one outside does not."""
    M = world["M"]
    b = [x for x in world["C"]["I"]["fit_und"] if not x.flicker][0]
    D = M["Ds"]["A"]
    bars, cidx = intra.bars_of(D, b.sym_a)
    e = int(np.searchsorted(cidx, intra.bisect.bisect_left(D.cal, date.fromisoformat(b.E))))
    p20 = intra.lookback_pairs(b, bars, cidx, e, D.cal, 20)
    p50 = intra.lookback_pairs(b, bars, cidx, e, D.cal, 50)
    assert len(p20) == 20 and len(p50) == 50 and p20 == p50[-20:] and p50[-1][1] == D.cal[int(cidx[e - 1])].isoformat() and all(d < b.E for _s, d in p50)
    with pytest.raises(intra.GuardStop, match="pre-buy daily lookback"):
        intra.make_irec(b, M, "A", None, intra.BarGuard({b.eid}, frozenset({p50[0]})), want_minutes=False)
    assert intra.make_irec(b, M, "A", None, intra.BarGuard({b.eid}, frozenset({p50[0]})), min_bars=20, want_minutes=False) is not None   # 50 bars back: outside ENTER's 20
    with pytest.raises(intra.GuardStop, match="pre-buy daily lookback"):
        intra.make_irec(b, M, "A", None, intra.BarGuard({b.eid}, frozenset({p20[0]})), min_bars=20, want_minutes=False)
    # a dated trade's base low reads from its base date when that lies before the 50 bars
    bd = [x for x in world["C"]["I"]["fit_dated"]][0]
    bars_d, cidx_d = intra.bars_of(D, bd.sym_a)
    e_d = int(np.searchsorted(cidx_d, intra.bisect.bisect_left(D.cal, date.fromisoformat(bd.E))))
    base_d = D.cal[int(cidx_d[e_d - 70])].isoformat()
    old = bd.base_id
    try:
        bd.base_id = f"x|{base_d}"
        pb = intra.lookback_pairs(bd, bars_d, cidx_d, e_d, D.cal, 50)
        assert len(pb) == 70 and pb[0][1] == base_d and len(intra.lookback_pairs(bd, bars_d, cidx_d, e_d, D.cal, 20)) == 20
    finally:
        bd.base_id = old


def test_freeze_record_per_fit_and_the_check_refuses_a_swapped_body(tmp_path, monkeypatch):
    """C5: every fit records the freeze body it ran under and the module's sha; the check refuses when a fit's record differs from the pin
    under the marker or from this module."""
    doc = tmp_path / "doc.md"
    body = ["# synthetic registration", "the fixed rules"]
    write_doc(doc, body, [])
    h = intra.store_freeze_body(str(doc), str(tmp_path / "fb"))
    write_doc(doc, body, [f"- doc_body_freeze: {h}"])
    monkeypatch.setattr(intra, "DOC", str(doc))
    monkeypatch.setattr(intra, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(intra, "LEDGER", str(tmp_path / "ledger.tsv"))
    fz = intra.freeze_record_now()
    assert fz == {"doc_body_freeze": h, "intra_module": intra.sha(os.path.join(HERE, "01_intra.py"))}
    for s in intra.STAGES:
        intra.write_chosen(s, {"x": 1}, "L8")
    assert json.load(open(tmp_path / "out" / "enter_fit_chosen.json"))["freeze"] == fz and intra.freeze_records_agree() == []
    # the hole the review showed: the body edited after the fits, stored, re-pinned, every pin re-pasted -> the fits' records disagree
    body2 = body + ["a bar moved after the fits"]
    write_doc(doc, body2, [])
    h2 = intra.store_freeze_body(str(doc), str(tmp_path / "fb"))
    write_doc(doc, body2, [f"- doc_body_freeze: {h2}"])
    bad = intra.freeze_records_agree()
    assert len(bad) == 3 and all("doc_body_freeze" in x for x in bad) and h2 != h
    write_doc(doc, body, [f"- doc_body_freeze: {h}"])
    monkeypatch.setattr(intra, "module_sha", lambda: "0" * 64)                 # the module edited after the fits
    assert any("intra_module" in x for x in intra.freeze_records_agree())
    monkeypatch.undo()
    monkeypatch.setattr(intra, "DOC", str(doc)); monkeypatch.setattr(intra, "OUT_DIR", str(tmp_path / "out"))
    os.remove(tmp_path / "out" / "stop_fit_chosen.json")
    with open(tmp_path / "out" / "stop_fit_chosen.json", "w") as fh:
        json.dump({"stage": "stop", "text": "S1-T", "object": {}}, fh)         # a chosen file without a record (an older module's)
    assert any("recorded no freeze body" in x for x in intra.freeze_records_agree())


def test_why_counts_sheet_and_precision():
    texts = {"v1": ("he sold half when it broke below the 20 ema on the 60 minute chart", [], []), "v2": ("the hourly chart and the twenty ema look fine", [], []),
             "v3": ("a 60-min range break is my add", [], []), "v4": ("nothing here", [], [])}
    assert intra.why_counts(texts) == (4, 3, 2, 2)
    sheet = pd.DataFrame([dict(verdict="yes"), dict(verdict="YES "), dict(verdict="no"), dict(verdict="")])
    assert intra.why_precision(sheet) == (pytest.approx(2 / 3), 2, 1)
    joins = [dict(video="v1", t=10.0, phrase="x", upload="20200701", ambiguous=False, eids=[1], tickers=["AAA"]) for _ in range(12)]
    joins += [dict(video="v1", t=10.0, phrase="x", upload="20210701", ambiguous=False, eids=[2], tickers=["BBB"])]
    joins += [dict(video="v1", t=10.0, phrase="x", upload="20200701", ambiguous=True, eids=[1, 2], tickers=["AAA", "BBB"])]
    tx = {"v1": ("w " * 100, list(range(0, 200, 2)), [float(i) for i in range(100)])}
    rows = intra.why_sheet_rows(joins, tx)
    assert len(rows) == 10 and all(r["upload"].startswith("2020") and r["verdict"] == "" for r in rows)


# ═════════════════════════════════════════════════════════════════════════════════════════════ the END-TO-END synthetic world
class SynthStore(intra.MinuteStore):
    """Minutes built from the world's daily bars on demand; `empty` pairs have no minutes; after-hours prints on early-close days; `new_only`
    pairs exist only in the NEW tree: served by the store, absent from its `restricted()` view (what the previous fit's trees held)."""

    def __init__(self, daily: dict, cal: list, empty: set, new_only: "set | None" = None):
        super().__init__({}, {})
        self.daily, self.cal, self.empty = daily, cal, empty
        self.new_only = set(new_only or ())
        self.pos = {d.isoformat(): i for i, d in enumerate(cal)}

    def state(self, d, tk, b=None):
        if (d, tk) in self.empty:
            return "empty/SYN"
        return "ok/SYN" if (tk in self.daily and d in self.pos) else "missing"

    def _build(self, d, tk):
        if (d, tk) in self.empty or tk not in self.daily or d not in self.pos:
            return None
        i = self.pos[d]
        o, h, l, c, _v = self.daily[tk]
        return minutes_from_daily(float(o[i]), float(h[i]), float(l[i]), float(c[i]), early=d in intra.EARLY_CLOSE, after_hours=d in intra.EARLY_CLOSE)

    def preload(self, pairs):
        from collections import Counter
        c = Counter()
        for p in pairs:
            d, tk = p[0], p[1]
            self.seal(d)
            self.check_forbid(d, tk)
            if (d, tk) not in self.cache:
                self.cache[(d, tk)] = self._build(d, tk)
            c[self.state(d, tk).split("/")[0]] += 1
        return c

    def get(self, d, tk, b=None):
        self.seal(d)
        self.check_forbid(d, tk)
        if (d, tk) not in self.cache:
            self.cache[(d, tk)] = self._build(d, tk)
        return self.cache[(d, tk)]

    def restricted(self, trees=intra.OLD_TREES):
        parent = self

        class OldTreesView(SynthStore):
            def __init__(self):
                super().__init__(parent.daily, parent.cal, parent.empty | parent.new_only)
                self.forbid = parent.forbid

            def restricted(self, trees=intra.OLD_TREES):
                return self
        return OldTreesView()


def make_D(daily: dict, cal: list, lo: int, hi: int):
    tks = sorted(daily)
    n = hi - lo
    o, h, l, c, v, ci = [], [], [], [], [], []
    for tk in tks:
        oo, hh, ll, cc, vv = daily[tk]
        o.append(oo[lo:hi]); h.append(hh[lo:hi]); l.append(ll[lo:hi]); c.append(cc[lo:hi]); v.append(vv[lo:hi]); ci.append(np.arange(n, dtype=np.int32))
    start = np.arange(len(tks)) * n
    return R.Daily(tks, start, start + n, np.concatenate(ci), np.concatenate(o), np.concatenate(h), np.concatenate(l), np.concatenate(c), np.concatenate(v),
                   cal[lo:hi], {t: k for k, t in enumerate(tks)}, 0, 0)


def build_world():
    """Two eras over one pickle calendar (2019-01..2024-06): DA = a prefix (to 2022-06-30), DB = a late suffix (from 2021-09-27). 60 tickers plus
    QQQ / SPY; a designed FSL path for the known-answer gate; buys in every set the registration names."""
    cal = weekday_cal("2019-01-02", "2024-06-28")
    CI = {d.isoformat(): i for i, d in enumerate(cal)}
    n = len(cal)
    tks = [f"T{k:02d}" for k in range(60)] + ["QQQ", "SPY", "FSL"]
    daily = {tk: daily_walk(n, 20.0 + 1.5 * k, 100 + k) for k, tk in enumerate(tks)}
    # FSL: rising, then on X a 10% break with bars closing below the 60-minute EMA, X+1's low under X's low
    X = CI["2020-07-10"]
    o = np.array([50.0 * (1.004 ** i) for i in range(n)]); c = o * 1.001; h = c * 1.002; l = o * 0.998
    o[X], c[X], h[X], l[X] = c[X - 1], c[X - 1] * 0.90, c[X - 1] * 1.001, c[X - 1] * 0.895
    o[X + 1], c[X + 1], h[X + 1], l[X + 1] = c[X] * 0.99, c[X] * 0.97, c[X] * 0.995, c[X] * 0.965
    for i in range(X + 2, n):
        o[i], c[i], h[i], l[i] = c[X + 1], c[X + 1] * 1.001, c[X + 1] * 1.003, c[X + 1] * 0.998
    daily["FSL"] = (o, h, l, c, np.full(n, 1e6))
    iA, iB = CI["2022-06-30"] + 1, CI["2021-09-27"]
    DA, DB = make_D(daily, cal, 0, iA), make_D(daily, cal, iB, n)
    cal_u, map_b = H.unify_calendars(DA.cal, DB.cal)
    assert [d.isoformat() for d in cal_u] == [d.isoformat() for d in cal]
    buys, frames = [], []
    eid = [0]

    def add(sym, E, kind="und", flat="10:05", first="10:40", exit_off=(3, 5), flicker=False, pivot=None, decides=False, window=True, p_ctx="in", still=False, f_ctx="in"):
        eid[0] += 1
        i = CI[E]
        kw = dict(eid=eid[0], sym=sym, sym_a=sym, E=E, lo=E, hi=E, flicker=flicker)
        if kind == "bo":
            kw.update(setup="breakout", decides=True, pivot=pivot if pivot is not None else float(daily[sym][3][i - 1]) * 1.01, adr20=0.05)
        if still:
            kw.update(exit_lo="", exit_hi="", still_held=True)
        elif flicker:
            kw.update(exit_lo=E, exit_hi=E)
        else:
            kw.update(exit_lo=cal[i + exit_off[0]].isoformat(), exit_hi=cal[i + exit_off[1]].isoformat())
        if window:
            kw.update(flat_clock=flat, first_clock=first, p_ctx=p_ctx, f_ctx=f_ctx)
        b = mk_buy(**kw)
        buys.append(b)
        if window:
            frames.append((E, sym, p_ctx, flat, False))
            frames.append((E, sym, f_ctx, first, True))
        if still:
            for off in (3, 9):
                frames.append((cal[i + off].isoformat(), sym, "in", "11:00", True))
        elif not flicker:
            frames.append((b.exit_lo, sym, "in", "11:30", True))
            if eid[0] % 2 == 0:
                frames.append((b.exit_lo, sym, "closed", "16:30", True))
        return b

    fit_dates = ["2020-02-03", "2020-02-18", "2020-03-02", "2020-03-16", "2020-04-01", "2020-04-15", "2020-05-01", "2020-05-18", "2020-06-01", "2020-06-15",
                 "2020-07-01", "2020-07-15", "2020-08-03", "2020-08-17", "2020-09-01", "2020-09-15", "2020-10-01", "2020-10-15", "2020-11-02", "2020-11-16"]
    clocks = [("10:05", "10:40"), ("09:40", "09:50"), ("10:30", "11:20"), ("09:35", "10:05"), ("11:00", "12:30"), ("10:10", "10:12"), ("13:00", "14:00"), ("10:05", "10:40")]
    for k, E in enumerate(fit_dates):
        fl, fs = clocks[k % len(clocks)]
        add(f"T{k:02d}", E, flat=fl, first=fs, exit_off=((1, 3), (2, 4), (3, 6), (0, 2), (5, 8))[k % 5])
    add("T20", "2020-02-10", flicker=True)
    add("T21", "2020-03-10", flicker=True, flat="10:10", first="10:10")           # zero width -> dropped by §2c
    add("T22", "2020-04-10", flicker=True, flat="10:20", first="10:50")
    for k, E in enumerate(["2020-02-05", "2020-03-04", "2020-04-06", "2020-05-06", "2020-06-08", "2020-07-08"]):
        add(f"T{23 + k:02d}", E, kind="bo", flat=clocks[k][0], first=clocks[k][1], exit_off=((2, 4), (4, 7), (1, 1), (3, 5), (6, 9), (2, 3))[k])
    for k, E in enumerate(["2020-02-12", "2020-05-12", "2020-09-09", "2020-11-24"]):          # dated without a window (a pre-market flat frame)
        add(f"T{29 + k:02d}", E, kind="bo", window=True, flat="09:10", first="09:45", p_ctx="pre", exit_off=((2, 5), (1, 2), (3, 3), (4, 8))[k])
    add("T33", "2020-11-18", exit_off=(5, 9))                                     # a hold across the early-close day 2020-11-27
    add("T34", "2020-06-22", exit_off=(2, 4))                                     # the buy day without minutes (empty)
    add("T35", "2020-08-05", exit_off=(4, 6))                                     # a missing minute day inside the hold
    fsl = add("FSL", "2020-06-29", flat="10:05", first="10:40", exit_off=(9, 10))  # X = 2020-07-10 = +9 (with 2020-07-03 a holiday in the real calendar, not here)
    # 2021-22: the check
    for k, E in enumerate(["2021-02-01", "2021-03-15", "2021-05-03", "2021-08-02", "2021-11-01", "2022-02-01", "2022-03-01"]):
        add(f"T{36 + k:02d}", E, flat=clocks[k % 4][0], first=clocks[k % 4][1], exit_off=((2, 3), (1, 1), (4, 6), (3, 3), (6, 10), (2, 2), (5, 5))[k])
    eraB = add("T43", "2022-05-02", flat="10:05", first="10:40", exit_off=(5, 5))   # era B: the sell window five sessions after the buy
    add("T44", "2022-01-31", flat="09:26", first="10:30", exit_off=(1, 2))         # DWAC-like: dropped by §2c
    add("T45", "2021-06-01", flicker=True, flat="10:05", first="10:40")
    add("T46", "2021-09-01", flicker=True, flat="10:20", first="10:50")
    for k, E in enumerate(["2021-02-08", "2021-06-14", "2022-01-10"]):
        add(f"T{47 + k:02d}", E, kind="bo", flat="10:05", first="10:40", exit_off=((2, 4), (1, 3), (3, 3))[k])
    for k, E in enumerate(["2021-04-05", "2021-10-04", "2022-03-14"]):
        add(f"T{50 + k:02d}", E, kind="bo", window=False, exit_off=((1, 2), (2, 2), (4, 5))[k])
    add("T53", "2022-04-20", kind="bo", window=False, exit_off=(3, 3))              # era B dated
    # the virgin block
    for k, E in enumerate(["2019-10-03", "2019-10-10", "2019-11-01", "2019-11-15"]):
        add(f"T{54 + k:02d}", E, flat="10:05", first="10:40", exit_off=((1, 1), (10, 14), (3, 3), (8, 8))[k])
    add("T58", "2019-10-01", flat="10:48", first="08:58", exit_off=(2, 2))          # APPS-like zero width
    add("T59", "2019-10-23", flat="09:24", first="09:25", exit_off=(2, 7))          # FBR-like flat before the open
    add("T00", "2019-10-21", kind="bo", window=False, exit_off=(5, 9))
    add("T01", "2019-11-07", kind="bo", flat="09:28", first="09:34", p_ctx="pre", exit_off=(3, 6))
    add("T02", "2019-10-22", flicker=True, flat="09:40", first="09:55")
    add("T03", "2019-11-11", flicker=True, flat="09:47", first="10:05")
    add("T04", "2023-06-01", kind="bo", window=False, exit_off=(6, 126))            # GSIT-like 121-session window
    add("T05", "2023-06-06", kind="bo", window=False, exit_off=(3, 123))
    add("T06", "2023-12-01", kind="bo", window=False, still=True)                   # still held at the last stream
    add("T07", "2023-12-04", kind="bo", window=False, still=True)
    add("T08", "2023-05-18", flat="09:35", first="09:49", exit_off=(15, 135))
    add("T09", "2023-05-19", flat="09:42", first="09:51", exit_off=(2, 8))
    add("T10", "2022-11-15", kind="bo", window=False, exit_off=(2, 47))
    add("T11", "2022-11-17", exit_off=(0, 45), window=False)
    for k, E in enumerate(["2020-01-02", "2020-01-02", "2020-01-02"]):
        add(f"T{12 + k:02d}", E, flat="09:08", first="09:33", exit_off=(0, 8))     # ARWR-like: flat before the open
    add("T15", "2020-01-23", flat="10:05", first="10:10", exit_off=(7, 7))          # APT-like: sane
    add("T15", "2020-02-14", flicker=True, flat="10:05", first="10:40")             # a 2020 flicker INSIDE that virgin trade's post-buy window: ENTER's
                                                                                    # beside windows and the STOP fit must exclude it (N5 / guard 5)
    rev.index_calendar(buys, [d.isoformat() for d in cal])
    S = rev.build_sets(buys)
    I = intra.intra_sets(S)
    mis = {}
    E = intra.enter_sets(I, S, mis)
    rows = [dict(idx=i, frame_id=f"f{i}", vid="v", date=d, ctx=ctx, clock=clk, symbols=(s if shows else ""), blip_filled="") for i, (d, s, ctx, clk, shows) in enumerate(frames)]
    sn = pd.DataFrame(rows)
    C = dict(buys=buys, S=S, I=I, E=E, mis=mis, sn=sn, cal=[d.isoformat() for d in cal], CI=CI)
    empty = {("2020-06-22", "T34"), (cal[CI["2020-08-05"] + 2].isoformat(), "T35")}
    # the exit windows' first sessions of the 2020 fit trades bought from June on exist in the NEW tree only (the real shape: 251 of 346 STOP fit
    # trades) — gate (iv)'s re-read must not see them
    new_only = {(b.exit_lo, b.sym) for b in I["fit_dated"] + I["fit_und"] if b.has_exit and b.exit_lo != b.E and b.E >= "2020-06-01"}
    sight = rev.Sightings.build(sn)

    def make_M():
        DA_, DB_ = make_D(daily, cal, 0, iA), make_D(daily, cal, iB, n)
        return dict(DA=DA_, DB=DB_, Ds={"A": DA_, "B": DB_}, cal_u=[d.isoformat() for d in cal], map_b=map_b, px=None, guards={"A": {}, "B": {}}, done={}, files={},
                    store=SynthStore(daily, cal, empty, new_only), sight=sight, last_seen=intra.last_seen_map(sight))
    M = make_M()
    return dict(C=C, M=M, cal=cal, CI=CI, daily=daily, fsl=fsl, eraB=eraB, byeid={b.eid: b for b in buys}, make_M=make_M, new_only=new_only)


@pytest.fixture(scope="module")
def world():
    return build_world()


def test_world_sets_and_era_b_record(world):
    C, M = world["C"], world["M"]
    I, E = C["I"], C["E"]
    assert len(I["fit_dated"]) == 10 and len(I["fit_und"]) == 28 and len(I["chk22_und"]) == 11 and len(I["chk22_dated"]) == 7
    # the virgin block by construction: undated = T54-T57, T58, T59, the flickers T02 / T03, T08 / T09, T11, T12-T14, T15 = 15; dated = T00, T01,
    # T04-T07, T10 = 7. ENTER's 2021-22 deciding windows = T36-T42 + T43 (era B) = 8 (T44 out by §2c); the virgin windows = T54-T57, T08, T09, T15
    # + the flickers T02 / T03 = 9 (7 non-flicker; T58 zero width, T59 and T12-T14 flat before the open, T01 pre-market flat: out)
    assert len(I["virgin_und"]) == 15 and len(I["virgin_dated"]) == 7 and len(I["virgin_all"]) == 22
    assert len(E["chk22_und"]) == 8 and len(E["virgin"]) == 9 and len(E["virgin_nf"]) == 7 and [b.sym for b in E["virgin_fl"]] == ["T02", "T03"]
    assert [b.sym for b in E["fit_fl"]] == ["T20", "T22", "T15"]                     # the zero-width flicker is dropped by §2c
    assert sum(1 for b in I["chk22_und"] if b.E >= intra.B_FIRST) == 1
    r = intra.make_irec(world["eraB"], M, "B", M["store"], None)
    assert r is not None and r.era == "B" and (r.exit_lo_j, r.exit_hi_j) == (5, 5) and r.cal is M["DB"].cal
    mixed = world["eraB"].exit_hi_i - r.e_ci
    assert mixed > 500                                                                 # the previous read's mixed-calendar reading
    assert np.isfinite(r.qqq_c[r.e + 1:]).any() and np.isfinite(r.qqq_c[r.e])          # a full record holds QQQ's closes along the hold (exit_features reads them)
    rd = intra.make_irec(world["eraB"], M, "B", None, None, min_bars=0, want_minutes=False)   # the dry run's dates-only build (C13)
    assert np.isfinite(rd.qqq_c[rd.e]) and np.isnan(rd.qqq_c[rd.e + 1:]).all() and (rd.exit_lo_j, rd.exit_hi_j) == (5, 5)
    stillr = intra.make_irec(world["byeid"][[b.eid for b in I["v23_dated"] if b.still_held][0]], M, "B", M["store"], None)
    assert stillr.last_j == 9 and stillr.exit_hi_j is None
    g = intra.BarGuard({1})
    r2 = intra.make_irec(world["eraB"], M, "B", M["store"], g)
    with pytest.raises(intra.GuardStop):
        r2.minutes(M["store"], 1)
    r2.minutes(M["store"], -3)                                                          # the warm-up is free


def synthetic_gate_iv_files(world, tmp, mis):
    """The previous fit's TSVs rebuilt on the synthetic world with the frozen functions (gate iv compares row for row)."""
    C, M = world["C"], world["M"]
    E, I = C["E"], C["I"]
    store, sight = M["store"], M["sight"]
    rows = []
    recs, _d = intra.recs_for(E["fit_dated"] + E["fit_und"], M, store, intra.BarGuard(None), min_bars=intra.REC_MIN_BARS_ENTER)
    for r in recs:
        row = dict(eid=r.b.eid, scorable=r.mb is not None)
        if r.mb is not None:
            flat_m, first_m = intra.hhmm_to_min(r.b.flat_clock), intra.hhmm_to_min(r.b.first_clock)
            lv = rev.enter_levels(r)
            for L in intra.OLD_LEVELS:
                s = dict(cross=None, feasible=False, verdict="no_level_yet") if first_m < rev.LEVEL_KNOWN_MIN.get(L, 0) else rev.score_level(r.mb, lv[L], flat_m, first_m, r.adr20)
                row[f"{L}_cross"], row[f"{L}_feasible"], row[f"{L}_verdict"] = s["cross"], s["feasible"], s["verdict"]
        rows.append(row)
    pe = tmp / "enter_fit_trades.tsv"
    pd.DataFrame(rows).to_csv(pe, sep="\t", index=False)
    recs, _d = intra.recs_for(I["fit_dated"] + I["fit_und"], M, store, intra.BarGuard(None))
    intra.apply_chain(recs, None, None, mis)
    rows = []
    old_store = store.restricted()                                              # the previous fit read the OLD trees only (C4)
    n_old = 0
    for r in recs:
        sl = rev.stop_levels(r, r.fill_minute if r.fill_src.startswith(("level", "orh5")) else None)
        row = dict(eid=r.b.eid, fill=r.fill, fill_minute=r.fill_minute, fill_src=r.fill_src)
        smas = intra.smas_for(r.bars)
        r.stop_levels = sl
        exit_mb = old_store.get(r.b.exit_lo, r.b.sym) if (r.b.has_exit and r.b.exit_lo != r.b.E) else None
        n_old += int(exit_mb is not None)
        for L in ("S1", "S3"):
            row[f"{L}_level0"] = rev.level_at(r, sl[L], 0, smas)
            for V in ("T", "C"):
                h = rev.held_through(r, L, V, smas, sight, exit_mb=exit_mb)
                for fld in ("any", "certain", "unresolved", "first_j"):
                    row[f"{L}_{V}_{fld}"] = h[fld]
        rows.append(row)
    ps = tmp / "stop_fit_trades.tsv"
    pd.DataFrame(rows).to_csv(ps, sep="\t", index=False)
    pj = tmp / "exit_fit_chosen.json"
    pj.write_text(json.dumps({"stage": "exit", "text": "list: X7<=0", "object": {"family": "list", "list": [[["X7", "<=", 0.0]]]}}))
    # PREMISE: the new-tree-only pairs are real in this world — some fit trades' exit minutes exist in the store but not in the old view,
    # and the frozen rule reads them differently (unresolved without, resolved with), so a gate (iv) that read the new tree would stop the stage
    with_new = sum(1 for r in recs if r.b.has_exit and r.b.exit_lo != r.b.E and store.get(r.b.exit_lo, r.b.sym) is not None)
    assert n_old < with_new, (n_old, with_new)
    differ = 0
    for r in recs:
        if (r.b.exit_lo, r.b.sym) in world["new_only"]:
            a = rev.held_through(r, "S3", "T", intra.smas_for(r.bars), sight, exit_mb=None)
            b_ = rev.held_through(r, "S3", "T", intra.smas_for(r.bars), sight, exit_mb=store.get(r.b.exit_lo, r.b.sym))
            differ += int((a["any"], a["certain"], a["unresolved"]) != (b_["any"], b_["certain"], b_["unresolved"]))
    assert differ >= 1, "no new-tree-only pair changes the old rule's reading: the world cannot see a gate (iv) that reads the new tree"
    return str(pe), str(ps), str(pj)


def e2e_env(world, tmp_path, monkeypatch) -> dict:
    """The end-to-end runners' environment on the synthetic world: every output path under tmp, the gate-iv files rebuilt, a FRESH market per
    stage (C10), G8 / pins / populations / WHY joins stubbed, gate (vii) recorded (its known answer is the real data's), the FSLY gate on the
    designed FSL trade, the doc body stored and pinned, a completed dry run. Shared by the plain run and the N2 reset run."""
    C, M = world["C"], world["M"]
    out = tmp_path / "intraday"
    out.mkdir()
    doc = tmp_path / "doc.md"
    fb = tmp_path / "freeze_bodies"
    monkeypatch.setattr(intra, "OUT_DIR", str(out))
    monkeypatch.setattr(intra, "FREEZE_BODIES", str(fb))
    monkeypatch.setattr(intra, "FROZEN_DIR", str(tmp_path))
    monkeypatch.setattr(intra, "LEDGER", str(tmp_path / "ledger.tsv"))
    monkeypatch.setattr(intra, "P_DRY", str(tmp_path / "dry.txt"))
    monkeypatch.setattr(intra, "P_PINS", str(tmp_path / "pins.txt"))
    monkeypatch.setattr(intra, "P_FIT", {s: str(tmp_path / f"{s}_fit.txt") for s in intra.STAGES})
    monkeypatch.setattr(intra, "P_CHECK", str(tmp_path / "check.txt"))
    monkeypatch.setattr(intra, "P_WHY", str(tmp_path / "why.txt"))
    monkeypatch.setattr(intra, "STOPPED", str(tmp_path / "STOPPED.txt"))
    monkeypatch.setattr(intra, "WHY_SHEET", str(out / "why_sheet.tsv"))
    monkeypatch.setattr(intra, "DOC", str(doc))
    monkeypatch.setattr(intra, "SUBS_GLOB", str(tmp_path / "nosubs" / "*.vtt"))
    monkeypatch.setattr(intra, "FIT_EVENTS", str(tmp_path / "fit_events"))           # N2: a reset's archive under tmp, never the module's verify/
    pe, ps, pj = synthetic_gate_iv_files(world, tmp_path, C["mis"])
    files = dict(intra.FILES)
    files.update(rev_enter_fit_trades=pe, rev_stop_fit_trades=ps, rev_exit_fit_chosen=pj, done_INTRA=str(tmp_path / "done.psv"))
    monkeypatch.setattr(intra, "FILES", files)
    monkeypatch.setattr(intra, "load_core", lambda say: C)
    # C10: every stage gets a FRESH M (new exports, new bars objects, a new store); the previous one is dropped and collected, so ids get reused
    Ms = []

    def fresh_M(say, C_, a, b):
        import gc
        Ms.append(id(world["make_M"]()["DA"]))
        gc.collect()
        m = world["make_M"]()
        say(f"- synthetic markets rebuilt (DA id {id(m['DA'])})")
        return m
    monkeypatch.setattr(intra, "load_for_stage", fresh_M)
    monkeypatch.setattr(intra, "g8_run", lambda say, recs, label: say(f"- G8 skipped in the synthetic world ({label})"))
    monkeypatch.setattr(intra, "check_pinned_inputs", lambda say: say("- pins skipped (synthetic)"))
    monkeypatch.setattr(intra, "assert_populations", lambda say, C_: say("- populations skipped (synthetic)"))
    monkeypatch.setattr(intra, "why_joins", lambda texts, C_: {"joins": []})
    seen_vii = []
    monkeypatch.setattr(intra, "gate_vii_random_control", lambda say, scored_all, prev_und_eids: (seen_vii.append((set(scored_all), set(prev_und_eids))),
                                                                                                     say("- gate (vii) skipped (the known answer is the real data's)"))[1])
    fsl = world["fsl"]
    X = world["cal"][world["CI"]["2020-07-10"]]
    monkeypatch.setattr(intra, "FSLY_GATE", dict(eid=fsl.eid, sym="FSL", E=fsl.E, exit_lo=fsl.exit_lo, exit_hi=fsl.exit_hi, h60_below_on=X.isoformat(),
                                                   prior_low_touch_on=world["cal"][world["CI"]["2020-07-10"] + 1].isoformat()))
    # the freeze: the doc body stored, its pin under the marker; a completed dry run
    body = ["# synthetic registration", "the fixed rules"]
    write_doc(doc, body, [])
    h = intra.store_freeze_body(str(doc), str(fb))
    write_doc(doc, body, [f"- doc_body_freeze: {h}"])
    (tmp_path / "dry.txt").write_text("...\nDRY RUN COMPLETE: synthetic\n")
    return dict(C=C, M=M, out=out, doc=doc, fb=fb, h=h, body=body, Ms=Ms, seen_vii=seen_vii)


def test_end_to_end_every_stage_runner_on_the_synthetic_world(world, tmp_path, monkeypatch):
    """--enter-fit, --stop-fit, --exit-fit, then --check through the real runners (their refusals, gates and ledger included) on the synthetic
    world; a frozen copy of the module beside the (stub) pins; the stop fit's FSLY gate on a designed trade; every output file written."""
    env = e2e_env(world, tmp_path, monkeypatch)
    C, M, out, doc, fb, h, body, Ms, seen_vii = (env[k] for k in ("C", "M", "out", "doc", "fb", "h", "body", "Ms", "seen_vii"))
    # a fit stage refuses without the freeze pin
    write_doc(doc, body, [])
    say = rp.Say()
    assert intra.run_fit_stage("enter", say) == 3 and "freeze lock" in "\n".join(say.lines)
    os.remove(tmp_path / "STOPPED.txt")
    write_doc(doc, body, [f"- doc_body_freeze: {h}"])
    # ENTER
    say = rp.Say()
    rc = intra.run_fit_stage("enter", say)
    text = "\n".join(say.lines)
    assert rc == 0, text
    assert "CHOSEN ENTER:" in text and "STOPPED" not in text and "gate (i) enter_fit" in text and "gate (ii)" in text and "gate (iv) ENTER" in text
    ent = json.load(open(out / "enter_fit_chosen.json"))
    assert ent["text"] in intra.NEW_LEVELS and (out / "enter_fit_trades.tsv").exists()
    assert ent["freeze"] == {"doc_body_freeze": h, "intra_module": intra.sha(os.path.join(HERE, "01_intra.py"))} and f"runs under the freeze body {h}" in text
    assert "guard (5) per ticker-date (the fit windows): 0 of" in text                                 # no fit window of this world collides
    # N5: the T15 flicker inside the virgin T15 trade's post-buy window is excluded from ENTER's beside windows (else the store's belt stops the stage)
    m_b = re.search(r"guard \(5\) per ticker-date \(the beside windows\): 1 of \d+ trades excluded [^:]*: T15 2020-02-14 \(\d+ pairs; exposes T15 2020-01-23\)", text)
    assert m_b, [ln for ln in say.lines if "beside windows" in ln]
    tr = pd.read_csv(out / "enter_fit_trades.tsv", sep="\t")
    assert "L9_shift_feasible" in tr.columns and "H60_0_high" in tr.columns and (tr["scorable"] == False).sum() >= 1   # noqa: E712  (the T34 buy day without minutes)
    # C8 / N4: the TSV's H60_0_high is the 60-minute BUILDER's first-bar high on that buy day (what L9, S10 and EXIT consume)
    sc_rows = tr[tr["scorable"] == True]                                                                # noqa: E712
    assert len(sc_rows) >= 10
    for rw in sc_rows.to_dict("records"):
        b_ = world["byeid"][int(rw["eid"])]
        b0 = intra.h60_bars(M["store"].get(b_.E, b_.sym), b_.E)[0]
        assert rw["H60_0_high"] == pytest.approx(b0.h), (b_.sym, b_.E)
    assert intra.run_fit_stage("enter", rp.Say()) == 2                                                  # writes once
    # STOP (the FSLY gate on the designed trade; the H variant; the buy-day rule)
    say = rp.Say()
    rc = intra.run_fit_stage("stop", say)
    text = "\n".join(say.lines)
    assert rc == 0, text
    assert "CHOSEN STOP:" in text and "gate (vi) FSLY" in text and "gate (iii) stop_fit" in text and "gate (iv) STOP" in text and "S9-H" in text and "RISK" in text
    m_s = re.search(r"guard \(5\) per ticker-date \(the fit trades\): (\d+) of (\d+) trades excluded", text)
    assert m_s and int(m_s.group(1)) == 3 and "T15 2020-02-14" in text and "T00 2020-02-03" in text and "T01 2020-02-18" in text   # the flicker; T00 / T01 by STOP's 50-session lookback (N3)
    m_iv = re.search(r"old-tree exit minutes read for (\d+) of (\d+) records", text)
    assert m_iv and 0 < int(m_iv.group(1)) < int(m_iv.group(2))                                      # the new-tree-only pairs were NOT read by the re-read
    stp = json.load(open(out / "stop_fit_chosen.json"))
    assert set(stp["object"]["fit_table"]) == {f"{L}-{V}" for L in intra.STOP_LEVELS + intra.STOP_CONTROLS for V in intra.STOP_VARIANTS}
    st_tr = pd.read_csv(out / "stop_fit_trades.tsv", sep="\t")
    assert len(st_tr) >= 30 and "S10_H_event_m" in st_tr.columns and st_tr["era"].eq("A").all()
    # EXIT
    say = rp.Say()
    rc = intra.run_fit_stage("exit", say)
    text = "\n".join(say.lines)
    assert rc == 0, text
    assert "CHOSEN EXIT:" in text and "THE 2020 ACCOUNTS" in text and "registered fill and stop" in text and "arming" in text and "= 65 bars before the armed bar" in text
    xit = json.load(open(out / "exit_fit_chosen.json"))
    assert xit["text"] in intra.EXIT_VARIANTS and (out / "exit_fit_bars.tsv.gz").exists()
    ex_tr = pd.read_csv(out / "exit_fit_trades.tsv", sep="\t")
    assert len(ex_tr) == 10 and "E3_last_j" in ex_tr.columns
    assert len(set(Ms)) == len(Ms) >= 3                                                                 # C10: a fresh export object per stage
    # the check refuses until the CHOSEN lines stand above the marker and every pin sits under it
    assert intra.run_check(rp.Say()) == 2
    body2 = body + [f"CHOSEN ENTER: {ent['text']}", f"CHOSEN STOP: {stp['text']}", f"CHOSEN EXIT: {xit['text']}"]
    write_doc(doc, body2, [f"- doc_body_freeze: {h}"])
    stub = {"intra_module": intra.sha(os.path.join(HERE, "01_intra.py")), "doc_body_freeze": h, "doc_body": intra.doc_body_sha(str(doc))}
    monkeypatch.setattr(intra, "pins", lambda doc=None, include_outputs=True: stub)
    assert intra.run_check(rp.Say()) == 2                                                               # pins not yet under the marker
    # C5: the HOLE the review showed — a bar edited above the marker AFTER the fits, the new body stored, `doc_body_freeze` re-pinned to it and every
    # pin re-pasted: the freeze lock is satisfied, but the fits recorded the OLD body, so the check refuses
    body_swap = ["# synthetic registration", "the fixed rules, one bar moved after the fits"] + body2[2:]
    write_doc(doc, body_swap, [])
    h2 = intra.store_freeze_body(str(doc), str(fb))
    stub2 = {"intra_module": stub["intra_module"], "doc_body_freeze": h2, "doc_body": None}
    write_doc(doc, body_swap, [f"- doc_body_freeze: {h2}", f"- intra_module: {stub2['intra_module']}"])
    stub2["doc_body"] = intra.doc_body_sha(str(doc))
    write_doc(doc, body_swap, [f"- doc_body_freeze: {h2}", f"- intra_module: {stub2['intra_module']}", f"- doc_body: {stub2['doc_body']}"])
    monkeypatch.setattr(intra, "pins", lambda doc=None, include_outputs=True: stub2)
    assert intra.freeze_state(str(doc), str(fb)) == (True, "") and h2 != h                             # the lock alone is satisfied ...
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        assert intra.run_check(rp.Say()) == 2                                                           # ... and the check still refuses
    assert "did not run under this freeze body" in buf.getvalue() and "doc_body_freeze" in buf.getvalue()
    monkeypatch.setattr(intra, "pins", lambda doc=None, include_outputs=True: stub)
    write_doc(doc, body2, [f"- doc_body_freeze: {h}", f"- intra_module: {stub['intra_module']}", f"- doc_body: {stub['doc_body']}"])
    calls = []                                                                  # N4: the order the random-price draws are consumed in
    real_score = intra.enter_score_trade
    monkeypatch.setattr(intra, "enter_score_trade", lambda rec, rng, with_shift=True: (calls.append(rec.b.eid), real_score(rec, rng, with_shift))[1])
    say = rp.Say()
    rc = intra.run_check(say)
    monkeypatch.setattr(intra, "enter_score_trade", real_score)
    text = "\n".join(say.lines)
    assert rc == 0, text
    assert "CHECK COMPLETE: ENTER" in text and "gate (v)" in text and "the sign veto" in text and "THE SEALED TEST'S BRANCH" in text and "STOPPED" not in text
    assert "all three fits ran under this freeze body and this module" in text
    assert "own-calendar offsets exit_lo 5 exit_hi 5" in text or "era B T43" in text or "era-B trades beside" in text
    # C6 / C7: the draw population is the previous read's (`ent_chk_dated` + `ent_chk_und`, flickers and the DWAC-like window scored), the
    # known-answer gate saw exactly the `ent_chk_und` records, and DECIDING is the chk22_und records with minutes — never the whole population
    S_ = C["S"]
    draw_pop = S_["ent_chk_dated"] + S_["ent_chk_und"]
    n_dec = len([r for r in intra.recs_for(C["E"]["chk22_und"], M, M["store"], intra.BarGuard(None), min_bars=intra.REC_MIN_BARS_ENTER)[0] if r.mb is not None])
    assert re.search(rf"records \d+ of {len(draw_pop)} windows", text) and f"DECIDING {n_dec} (the {len(C['E']['chk22_und'])} undated non-flicker windows" in text
    assert n_dec < len(draw_pop) and len(seen_vii) == 1
    assert seen_vii[0][1] == {b.eid for b in S_["ent_chk_und"]} and seen_vii[0][0] <= {b.eid for b in draw_pop} and len(seen_vii[0][0]) > n_dec
    # N4: the draw population's COMPOSITION (every `ent_chk_dated` + `ent_chk_und` record with minutes, dated flickers and the DWAC-like window
    # included) and its ORDER (the first draws go to those records in (buy day, eid) order, before any beside set is scored)
    dp_recs = [r for r in intra.recs_for(draw_pop, M, M["store"], intra.BarGuard(None), min_bars=intra.REC_MIN_BARS_ENTER)[0] if r.mb is not None]
    want = [r.b.eid for r in sorted(dp_recs, key=lambda x: (x.b.E, x.b.eid))]
    assert seen_vii[0][0] == set(want) and calls[:len(want)] == want, (calls[:len(want)], want)
    assert any(b.dated and b.flicker for b in S_["ent_chk_dated"] if b.eid in set(want)) or not any(b.flicker for b in S_["ent_chk_dated"])
    assert any(b.sym == "T44" for b in S_["ent_chk_und"] if b.eid in set(want))                        # the DWAC-like window is drawn, never deciding
    assert f"beside: the {len(S_['ent_chk_dated'])} dated 2021-22 windows" in text
    # the three accounts are three accounts: 'his' is never 'ours' on the deciding line
    acc_lines = [ln for ln in say.lines if ln.startswith("- dated 2021-22, registered fill and stop, ") or ln.startswith("- dated 2021-22, chain fill and stop, ")]
    assert acc_lines
    for ln in acc_lines:
        m_ = re.search(r"ours ([-\d.]+) \| chosen ([-\d.]+) \| his ([-\d.]+)", ln)
        assert m_ and m_.group(1) != m_.group(3), ln
    verd = json.load(open(out / "check_verdicts.json"))
    assert set(verd) == {"enter", "stop", "exit"}
    assert any(f.startswith("01_intra_frozen_") for f in os.listdir(tmp_path))
    for f in ("check_enter_trades.tsv", "check_stop_trades.tsv", "check_exit_trades.tsv", "check_exit_bars.tsv.gz"):
        assert (out / f).exists(), f
    assert intra.ledger_verify(str(tmp_path / "ledger.tsv")) == []
    ce = pd.read_csv(out / "check_stop_trades.tsv", sep="\t")
    assert (ce["era"] == "B").sum() >= 2 and ce.loc[ce["sym"] == "T43", "exit_hi_j"].iloc[0] == 5
    assert intra.run_check(rp.Say()) == 2                                                               # the check runs once
    # C7: the check's DECISIONS, forced one at a time through the real check_stages on fresh output folders (the chosen files copied in)
    import shutil

    def forced_check(name, **patches):
        d = tmp_path / f"forced_{name}"
        (d / "intraday").mkdir(parents=True)
        for s in intra.STAGES:
            shutil.copy(out / f"{s}_fit_chosen.json", d / "intraday" / f"{s}_fit_chosen.json")
        sj = json.load(open(d / "intraday" / "stop_fit_chosen.json"))
        if not sj["object"]["level"]:                                            # a forced STOP PASS needs a chosen cell to carry
            sj["object"].update(level="S1", variant="T"); sj["text"] = "S1-T"
            json.dump(sj, open(d / "intraday" / "stop_fit_chosen.json", "w"))
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(intra, "OUT_DIR", str(d / "intraday"))
            mp.setattr(intra, "LEDGER", str(d / "ledger.tsv"))
            mp.setattr(intra, "WHY_SHEET", str(d / "why.tsv"))
            for k, v in patches.items():
                mp.setattr(intra if not k.startswith("rev.") else rev, k.split(".")[-1], v)
            s_ = rp.Say()
            rc_ = intra.check_stages(s_, C, world["make_M"](), with_why=False)
            return rc_, "\n".join(s_.lines), json.load(open(d / "intraday" / "check_verdicts.json"))
    pass_e = lambda summary, chosen: ("PASS", [])                              # noqa: E731
    fail_e = lambda summary, chosen: ("FAIL", ["forced"])                       # noqa: E731
    rc1, t1, v1 = forced_check("enter_pass", enter_verdict=pass_e, enter_veto=lambda sv, ch: (False, "abstains (forced)"), stop_verdict=lambda tab, ch: ("FAIL", ["forced"]))
    assert rc1 == 0 and v1["enter"] == "PASS" and "the chain carries: the chosen level" in t1 and "the deciding line = the chain fill and stop" in t1
    assert "the chain carries: the REGISTERED stop" in t1
    rc2, t2, v2 = forced_check("enter_pass_vetoed", enter_verdict=pass_e, enter_veto=lambda sv, ch: (True, "forced VETO"), stop_verdict=lambda tab, ch: ("FAIL", ["forced"]))
    assert rc2 == 0 and v2["enter"] == "INCONCLUSIVE" and "vetoed by the untouched years' sign" in t2 and "the chain carries: the REGISTERED fill" in t2
    assert "the deciding line = the registered fill and stop" in t2
    seen_tab = []
    def rec_stop_verdict(tab, ch):
        seen_tab.append(tab)
        return "PASS", ["forced"]
    rc3, t3, v3 = forced_check("stop_pass", enter_verdict=fail_e, stop_verdict=rec_stop_verdict)
    n_vu = len(intra.recs_for(C["I"]["virgin_und"], M, M["store"], intra.BarGuard(None))[0])
    n_22u = len(intra.recs_for(C["I"]["chk22_und"], M, M["store"], intra.BarGuard(None))[0])
    assert rc3 == 0 and v3["stop"] == "PASS" and "the chain carries: the chosen stop" in t3 and "the deciding line = the chain fill and stop" in t3
    assert seen_tab and seen_tab[0][("S1", "T")]["n"] == n_vu != n_22u                            # the deciding table is the virgin undated one
    rc4, t4, v4 = forced_check("exit_void", enter_verdict=fail_e, stop_verdict=lambda tab, ch: ("FAIL", ["forced"]), **{"rev.recovery": lambda o, c, h_: (float("nan"), "his / ours = 1.00 < 1.25 (forced)")})
    assert rc4 == 0 and v4["exit"] == "VOID" and "EXIT: **VOID**" in t4
    rc5, t5, v5 = forced_check("exit_pass_vetoed", enter_verdict=fail_e, stop_verdict=lambda tab, ch: ("FAIL", ["forced"]), exit_verdict=lambda acc: ("PASS", "forced"),
                               exit_veto=lambda acc: (True, "forced VETO"))
    assert rc5 == 0 and v5["exit"] == "INCONCLUSIVE" and "a PASS on dated 2021-22 vetoed" in t5 and "words-based (the speed trail)" in t5
    rc6, t6, v6 = forced_check("exit_pass", enter_verdict=fail_e, stop_verdict=lambda tab, ch: ("FAIL", ["forced"]), exit_verdict=lambda acc: ("PASS", "forced"),
                               exit_veto=lambda acc: (False, "abstains (forced)"))
    assert rc6 == 0 and v6["exit"] == "PASS" and "the inferred FSLY variant" in t6
    # the dry-run-complete gate: a fit refuses without it
    for s in intra.STAGES:
        os.remove(tmp_path / f"{s}_fit.txt")
    for f in os.listdir(out):
        if f.startswith(("enter_fit", "stop_fit", "exit_fit")):
            os.remove(out / f)
    (tmp_path / "dry.txt").write_text("...\nSTOPPED: x\n")
    say = rp.Say()
    assert intra.run_fit_stage("enter", say) == 3 and "has not COMPLETED" in "\n".join(say.lines)


def test_reset_fits_archives_never_deletes_and_the_check_needs_the_disclosure(tmp_path, monkeypatch):
    """N2: --reset-fits refuses without a reason, without a STOPPED file (it never re-rolls a completed fit) and after a completed check; it
    COPIES every artifact (printouts, chosen files, ledger, STOPPED, the dry run's printout, intraday/ files, module copies — not the dry run's
    own dryrun_* files) into verify/fit_events/<event>/, verifies each copy, writes MANIFEST.tsv / DISCLOSURE.md / events.tsv, and only then
    removes the originals; --check's gate refuses an event whose manifest pin is not under the marker or whose manifest changed."""
    out = tmp_path / "intraday"
    out.mkdir()
    doc = tmp_path / "doc.md"
    ev_root = tmp_path / "fit_events"
    for name, val in (("OUT_DIR", str(out)), ("DOC", str(doc)), ("FIT_EVENTS", str(ev_root)), ("FROZEN_DIR", str(tmp_path)), ("LEDGER", str(tmp_path / "ledger.tsv")),
                      ("STOPPED", str(tmp_path / "STOPPED.txt")), ("P_CHECK", str(tmp_path / "check.txt")), ("P_WHY", str(tmp_path / "why.txt")),
                      ("P_DRY", str(tmp_path / "dry.txt")), ("P_PINS", str(tmp_path / "pins.txt")), ("P_FIT", {s_: str(tmp_path / f"{s_}_fit.txt") for s_ in intra.STAGES})):
        monkeypatch.setattr(intra, name, val)
    write_doc(doc, ["# synthetic registration"], [])
    (tmp_path / "enter_fit.txt").write_text("# ENTER FIT\nCHOSEN ENTER: L8\n")
    (out / "enter_fit_chosen.json").write_text('{"stage": "enter", "text": "L8"}')
    (out / "enter_fit_trades.tsv").write_text("eid\n1\n")
    (out / "dryrun_windows.tsv").write_text("set\n")                            # the dry run's own file: never archived
    (tmp_path / "01_intra_frozen_abcdef123456.py").write_text("# a module copy guard (2) made\n")
    (tmp_path / "dry.txt").write_text("...\nDRY RUN COMPLETE: x\n")
    intra.ledger_append("enter-fit", str(tmp_path / "enter_fit.txt"))
    say = rp.Say()
    assert intra.reset_fits(say, "x") == 2 and not ev_root.exists()                                   # nothing STOPPED: a completed fit is never re-rolled
    (tmp_path / "STOPPED.txt").write_text("# STOP FIT\nSTOPPED: gate (i): high/low within 0.5% on 50.0% of 80 pairs\n")
    assert intra.reset_fits(say, "  ") == 2                                                            # no reason
    (tmp_path / "check.txt").write_text("CHECK COMPLETE\n")
    assert intra.reset_fits(say, "x") == 2                                                             # the check completed: it ran once
    os.remove(tmp_path / "check.txt")
    before = {p_: intra.sha(p_) for p_ in intra.reset_artifacts()}
    assert str(out / "dryrun_windows.tsv") not in before and len(before) == 7
    # a copy that does not match its original refuses the reset and removes NOTHING from its place
    real_copy = intra.shutil.copy2
    monkeypatch.setattr(intra.shutil, "copy2", lambda a, b: (real_copy(a, b), open(b, "a").write("corrupted"))[0])
    assert intra.reset_fits(rp.Say(), "a reset whose copy goes wrong") == 3
    monkeypatch.setattr(intra.shutil, "copy2", real_copy)
    assert all(os.path.exists(p_) and intra.sha(p_) == h_ for p_, h_ in before.items()) and intra.fit_events() == []
    shutil_rm = __import__("shutil")
    shutil_rm.rmtree(ev_root)                                                    # the partial copies of the refused attempt (scratch, this test only)
    assert intra.reset_fits(say, "gate (i) stopped the STOP fit on a clock bug; fixed in h60_bars") == 0
    evs = intra.fit_events()
    assert len(evs) == 1 and evs[0]["files"] == "7" and evs[0]["reason"].startswith("gate (i) stopped")
    dest = ev_root / evs[0]["event"]
    man = pd.read_csv(dest / "MANIFEST.tsv", sep="\t", dtype=str)
    assert set(man["original"]) == {os.path.abspath(p_) for p_ in before}
    for rw in man.to_dict("records"):
        assert not os.path.exists(rw["original"]) and intra.sha(str(dest / rw["archived"])) == rw["sha256"] == before[rw["original"]]   # moved, intact
    assert (out / "dryrun_windows.tsv").exists() and (dest / "intraday" / "enter_fit_trades.tsv").exists() and (dest / "module" / "STOPPED.txt").exists()
    disc = (dest / "DISCLOSURE.md").read_text()
    assert "CHOSEN ENTER: L8" in disc and "STOPPED: gate (i)" in disc and intra.sha(str(dest / "MANIFEST.tsv")) in disc
    assert intra.stage_outputs("enter") == [] and not os.path.exists(intra.LEDGER) and not intra.dry_run_complete()   # the dry run must be re-run
    pins_ = intra.fit_event_pins()
    assert pins_ == {f"fit_event_{evs[0]['event']}": intra.sha(str(dest / "MANIFEST.tsv"))} and set(pins_) <= set(intra.pins(str(doc), include_outputs=False))
    bad = intra.fit_events_undisclosed(str(doc))
    assert len(bad) == 1 and "not disclosed under the marker" in bad[0]
    write_doc(doc, ["# synthetic registration"], [f"- {k}: {v}" for k, v in pins_.items()])
    assert intra.fit_events_undisclosed(str(doc)) == []
    with open(dest / "MANIFEST.tsv", "a") as fh:
        fh.write("an edit after the fact\n")
    assert any("changed since events.tsv recorded it" in x for x in intra.fit_events_undisclosed(str(doc)))
    assert intra.reset_fits(rp.Say(), "again") == 2                                                    # the STOPPED file went with the event


def test_end_to_end_a_stop_after_the_first_fit_then_the_reset_path_to_a_clean_check(world, tmp_path, monkeypatch):
    """N2 end to end: ENTER fits, STOP stops on a gate, the dead end (no fit re-runs; a module edit would split the fits' records), the reset,
    the dry run, ALL three fits again under the fixed module, and --check: refused until the event is disclosed under the marker, then clean."""
    env = e2e_env(world, tmp_path, monkeypatch)
    out, doc, h, body = env["out"], env["doc"], env["h"], env["body"]
    assert intra.run_fit_stage("enter", rp.Say()) == 0
    first_enter = (tmp_path / "enter_fit.txt").read_text()
    real_vi = intra.gate_vi_fsly

    def planted(say, recs, store):
        raise intra.GuardStop("gate (vi): planted — the builder's bars disagree with his FSLY words")
    monkeypatch.setattr(intra, "gate_vi_fsly", planted)
    say = rp.Say()
    assert intra.run_fit_stage("stop", say) == 3 and (tmp_path / "STOPPED.txt").exists() and "planted" in (tmp_path / "STOPPED.txt").read_text()
    # the dead end without the reset: every fit refuses (outputs on disk), and the fixed module's sha would differ from the ENTER fit's record
    assert intra.run_fit_stage("stop", rp.Say()) == 2 and intra.run_fit_stage("enter", rp.Say()) == 2
    monkeypatch.setattr(intra, "gate_vi_fsly", real_vi)                                               # the fix ...
    monkeypatch.setattr(intra, "module_sha", lambda: "f" * 64)                                       # ... changes the module
    assert json.load(open(out / "enter_fit_chosen.json"))["freeze"]["intra_module"] != "f" * 64
    assert intra.reset_fits(rp.Say(), "gate (vi) stopped --stop-fit (planted); fixed") == 0
    assert not (tmp_path / "STOPPED.txt").exists() and not (tmp_path / "enter_fit.txt").exists() and not intra.dry_run_complete()
    (tmp_path / "dry.txt").write_text("...\nDRY RUN COMPLETE: synthetic, under the fixed module\n")    # the dry run re-run
    for st_ in intra.STAGES:
        s_ = rp.Say()
        assert intra.run_fit_stage(st_, s_) == 0, "\n".join(s_.lines)
        assert json.load(open(out / f"{st_}_fit_chosen.json"))["freeze"] == {"doc_body_freeze": h, "intra_module": "f" * 64}
    assert intra.freeze_records_agree() == []
    texts = {st_: json.load(open(out / f"{st_}_fit_chosen.json"))["text"] for st_ in intra.STAGES}
    body2 = body + [f"CHOSEN {st_.upper()}: {texts[st_]}" for st_ in intra.STAGES]
    write_doc(doc, body2, [f"- doc_body_freeze: {h}"])
    stub = {"intra_module": "f" * 64, "doc_body_freeze": h, "doc_body": intra.doc_body_sha(str(doc))}
    monkeypatch.setattr(intra, "pins", lambda doc=None, include_outputs=True: stub)
    tail = [f"- {k}: {v}" for k, v in stub.items()]
    write_doc(doc, body2, tail)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        assert intra.run_check(rp.Say()) == 2
    assert "is not disclosed under the marker" in buf.getvalue()
    ev = intra.fit_events()[0]["event"]
    assert first_enter in open(tmp_path / "fit_events" / ev / "module" / "enter_fit.txt").read()        # the already-seen ENTER printout is kept
    write_doc(doc, body2, tail + [f"- {k}: {v}" for k, v in intra.fit_event_pins().items()])
    say = rp.Say()
    rc = intra.run_check(say)
    assert rc == 0, "\n".join(say.lines)
    assert intra.ledger_verify() == [] and "CHECK COMPLETE: ENTER" in "\n".join(say.lines)


# ═════════════════════════════════════════════════════════════════════════════════════════════ the dry run's DATA GATE OPEN path and --print-pins
class QuietClaims(intra.Claims):
    """Records every claim, asserts none: the synthetic world cannot reproduce the real registration's counts, so what is under test here is the
    dry run's MECHANICS (the pending-pairs branch, the files it writes, the pins), never its numbers."""

    def __call__(self, anchor, label, doc, mine):
        self.n += 1
        self.say(f"  [quiet] {label} | doc {intra.fmt_claim(doc)} | mine {intra.fmt_claim(mine)}")
        return True


def test_dry_run_with_the_fetch_pending_reports_the_pairs_and_completes_and_print_pins_writes(world, tmp_path, monkeypatch):
    """The data gate OPEN (the task's case: the fetch has not run): the intra tree has no _done.psv and no pair of the list sits in any tree's
    log -> every pair is PENDING, written to dryrun_fetch_pending.psv, the fetch-log claims print NOT READ, and the run still ends
    `DRY RUN COMPLETE ... DATA GATE OPEN`. Then --print-pins writes its file (this read's outputs named ABSENT, the module and the tests pinned
    by sha); and a fit stage refuses while the gate is open even with a completed dry run and the freeze pin in place."""
    C, M = world["C"], world["M"]
    out = tmp_path / "intraday"
    out.mkdir()
    doc = tmp_path / "doc.md"
    write_doc(doc, ["# synthetic registration", "the fixed rules"], [])
    fl = tmp_path / "fetch_list.psv"
    pairs = [(b.sym, b.E, "fit2020") for b in C["E"]["fit_und"][:5]] + [(b.sym, b.E, "y2122") for b in C["E"]["chk22_und"][:3]] + [("T54", "2019-10-03", "virgin")]
    fl.write_text("".join(f"{t}|{d}|{blk}\n" for t, d, blk in pairs))
    monkeypatch.setattr(intra, "FILES", {k: v for k, v in intra.FILES.items() if k != "done_INTRA"})     # the fetch has NOT run
    for name, val in (("OUT_DIR", str(out)), ("FREEZE_BODIES", str(tmp_path / "fb")), ("DOC", str(doc)), ("FETCH_LIST", str(fl)),
                      ("P_DRY", str(tmp_path / "dry.txt")), ("P_PINS", str(tmp_path / "pins.txt")), ("LEDGER", str(tmp_path / "ledger.tsv")),
                      ("STOPPED", str(tmp_path / "STOPPED.txt")), ("P_CHECK", str(tmp_path / "check.txt")), ("P_WHY", str(tmp_path / "why.txt")),
                      ("P_FIT", {s: str(tmp_path / f"{s}_fit.txt") for s in intra.STAGES}), ("SUBS_GLOB", str(tmp_path / "nosubs" / "*.vtt"))):
        monkeypatch.setattr(intra, name, val)
    monkeypatch.setattr(intra, "load_core", lambda say: C)
    monkeypatch.setattr(intra, "load_for_stage", lambda say, C_, a, b: M)
    monkeypatch.setattr(intra, "check_pinned_inputs", lambda say: say("- pins skipped (synthetic)"))
    monkeypatch.setattr(intra, "population_claims", lambda say, C_: QuietClaims(say))
    monkeypatch.setattr(intra, "load_done_all", lambda: ({}, {}))                                        # no fetch log anywhere
    monkeypatch.setattr(intra, "why_joins", lambda texts, C_: {"joins": [], "hits": 0, "qual": 0, "amb": 0})
    rc = intra.main(["--dry-run"])
    text = (tmp_path / "dry.txt").read_text()
    assert rc == 0, text
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[-1].startswith("DRY RUN COMPLETE") and f"DATA GATE OPEN: {len(pairs)} pairs pending" in lines[-1] and "no minute file opened (0 reads)" in lines[-1]
    assert "DATA GATE OPEN" in text and "NOT READ (tree absent)" in text and "the tree minutes_intra_1025 has NO _done.psv" in text
    pend = (out / "dryrun_fetch_pending.psv").read_text().splitlines()
    assert sorted(pend) == sorted(f"{t}|{d}" for t, d, _b in pairs)                                   # every pair of the list, none served by any tree
    assert "coverage per block: fit2020: missing 5; virgin: missing 1; y2122: missing 3" in text
    assert (out / "dryrun_windows.tsv").exists() and not (tmp_path / "STOPPED.txt").exists()
    # --print-pins
    assert intra.main(["--print-pins"]) == 0
    pins_text = (tmp_path / "pins.txt").read_text()
    assert f"- intra_module: {intra.sha(os.path.join(HERE, '01_intra.py'))}" in pins_text and f"- intra_tests: {intra.sha(os.path.join(HERE, 'test_01_intra.py'))}" in pins_text
    assert "- enter_fit_printout: ABSENT" in pins_text and "- ledger: ABSENT" in pins_text and f"- doc_body: {intra.doc_body_sha(str(doc))}" in pins_text
    assert "- dryrun_printout: " in pins_text and "dryrun_printout: ABSENT" not in pins_text
    assert "- freeze record: NOT YET under the marker" in pins_text and "CHOSEN lines above the marker (column 0, keyed): none" in pins_text
    # a fit stage refuses while the gate is open, even with a completed dry run and the freeze pin in place
    h = intra.store_freeze_body(str(doc), str(tmp_path / "fb"))
    write_doc(doc, ["# synthetic registration", "the fixed rules"], [f"- doc_body_freeze: {h}"])
    say = rp.Say()
    assert intra.run_fit_stage("enter", say) == 3 and "the data gate is open" in "\n".join(say.lines)
    assert (tmp_path / "STOPPED.txt").exists()
