"""#702 P1 — tests for agents/market_intelligence/consolidation_breakout.py (the pure core of the
Consolidation Breakout backtest + shadow).

Every expected number is derived here from the bars it came from, never from the function under
test: the MRNA canary hard-codes the fixture's own prices with the arithmetic beside them, and the
synthetic cases are built so each gate fails ALONE (a control that passes sits next to every
mutation that does not).
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence.constants import ENTRY_SLIPPAGE_PCT

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "htf_labelled_bars.psv"
REPO = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _weekdays(n: int, start: dt.date = dt.date(2025, 1, 6)) -> list:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _closes_only(closes) -> cb.DailyBars:
    c = list(closes)
    return cb.daily_bars_from_arrays(_weekdays(len(c)), c, c, c, c, [1.0] * len(c))


def _fwd(rows) -> cb.DailyBars:
    """rows = [(open, high, low, close), ...] -> DailyBars for E+1.."""
    o, h, l, c = zip(*rows)
    return cb.daily_bars_from_arrays(_weekdays(len(rows)), o, h, l, c, [1.0] * len(rows))


def _mrna():
    rows = [ln.rstrip("\n").split("|") for ln in FIXTURE.read_text().splitlines()
            if ln.startswith("MRNA|")]
    cols = [[float(r[k]) for r in rows] for k in (2, 3, 4, 5, 6)]
    bars = cb.daily_bars_from_arrays([dt.date.fromisoformat(r[1]) for r in rows], *cols)
    return bars, {r[1]: k for k, r in enumerate(rows)}


class Synth:
    """A clean C0 pass at i = n-1: a flat $10 pad, a 21-session ramp to a pole high `top` at
    P = i - base_n, then a base_n-session base — 8% daily ranges for the first 5 sessions, 5% in
    the middle, 2% for the last 5 (so tightening = 0.25) with lows that step UP. Mutate the lists,
    then call .bars()."""

    def __init__(self, n: int = 140, base_n: int = 20, top: float = 16.0):
        self.n, self.i, self.base_n, self.top = n, n - 1, base_n, top
        self.P = self.i - base_n
        self.o, self.h, self.l, self.c = ([0.0] * n for _ in range(4))
        for k in range(0, self.P - 20):                       # pad
            self.o[k] = self.c[k] = 10.0
            self.h[k], self.l[k] = 10.1, 9.9
        top_close = 0.987 * top
        for k in range(self.P - 20, self.P + 1):              # ramp, ending on the pole day
            t = (k - (self.P - 21)) / 21.0
            c = 10.0 + (top_close - 10.0) * t
            self.c[k], self.o[k] = c, c * 0.995
            self.h[k], self.l[k] = c * 1.01, c * 0.99
        self.o[self.P], self.h[self.P], self.l[self.P], self.c[self.P] = (
            0.98 * top, top, 0.97 * top, top_close)
        level = 0.94 * top
        tail_eps = [-0.003, 0.0, -0.002, 0.003, 0.0]
        for b in range(base_n):
            k = self.P + 1 + b
            if b < 5:
                c, hi, lo = level * 0.97, 1.04, 0.96
            elif b >= base_n - 5:
                c, hi, lo = level * (1 + tail_eps[b - (base_n - 5)]), 1.01, 0.99
            else:
                c, hi, lo = level, 1.025, 0.975
            self.c[k], self.o[k] = c, c
            self.h[k], self.l[k] = c * hi, c * lo

    def bars(self) -> cb.DailyBars:
        return cb.daily_bars_from_arrays(_weekdays(self.n), self.o, self.h, self.l, self.c,
                                         [2e6] * self.n)

    def watch(self):
        return cb.evaluate_watch(self.bars(), self.i)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. MRNA canary — expected numbers read off tests/fixtures/htf_labelled_bars.psv by hand
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestMrnaCanary:
    def setup_method(self):
        self.bars, self.idx = _mrna()
        self.i = self.idx["2026-09-16"]
        self.f = cb.evaluate_watch(self.bars, self.i)

    def test_passes_c0_on_the_watch_night(self):
        assert self.f is not None
        assert self.f["watch_date"] == "2026-09-16"
        assert self.i >= 129

    def test_pole_is_the_08_19_ep_day(self):
        # high 176.66 on 08-19 is the max high in [i-45, i-10]; 19 sessions before 09-16
        assert self.f["pole_date"] == "2026-08-19"
        assert self.f["pole_high"] == 176.66
        assert self.f["base_len"] == 19
        assert self.f["pole_idx"] == self.i - 19
        # pole low: the lowest low in the 41 sessions up to 08-19 is 52.6601 on 08-03
        assert self.f["pole_low"] == 52.6601
        assert self.f["pole_low_date"] == "2026-08-03"
        assert self.f["prior_move"] == pytest.approx(176.66 / 52.6601 - 1.0)
        assert self.f["pole_sessions"] == 12          # 08-03 .. 08-19 is 12 sessions apart

    def test_pivots_k5_and_k10_differ_which_is_why_k_is_a_parameter(self):
        # last 5 sessions (09-10..09-16): highs 137.13 149.7344 147.3399 148.6999 148.93 -> 149.7344 (09-11)
        assert self.f["pivot_k5"] == 149.7344 and self.f["pivot_k5_date"] == "2026-09-11"
        # last 10 sessions start 09-02 (09-07 was Labor Day): 09-02 high 156.4151 beats 154.69 (09-04)
        assert self.f["pivot_k10"] == 156.4151 and self.f["pivot_k10_date"] == "2026-09-02"
        # whole base: 08-25's 161.37 is the highest high after the pole day
        assert self.f["pivot_full"] == 161.37 and self.f["pivot_full_date"] == "2026-08-25"

    def test_breakout_day_clears_the_k5_pivot(self):
        assert self.bars.h[self.idx["2026-09-17"]] == 161.9599
        assert 161.9599 > self.f["pivot_k5"]
        assert 161.9599 > self.f["pivot_k10"]
        assert 161.9599 > self.f["pivot_full"]            # 161.9599 > 161.37 (08-25)
        # and the previous-day pivots are all still under the pole high (the C0 clause)
        assert self.f["pivot_full"] <= self.f["pole_high"]

    def test_higher_lows_and_tightening(self):
        # last-5 lows 130.38 135.0101 139.02 141.16 142.3001 -> min 130.38 (09-10) > base low 128.61 (08-20)
        assert self.f["base_low"] == 128.61
        assert self.f["higher_lows"] is True
        # (high-low)/close, last 5 sessions 09-10..09-16
        recent = [(137.13 - 130.38) / 136.62, (149.7344 - 135.0101) / 143.97,
                  (147.3399 - 139.02) / 146.69, (148.6999 - 141.16) / 143.77,
                  (148.93 - 142.3001) / 145.62]
        # first 5 base sessions 08-20..08-26
        early = [(155 - 128.61) / 133.32, (159.47 - 132.42) / 145.13, (145.5 - 130) / 138.89,
                 (161.37 - 141.21) / 158.83, (156.13 - 145.1) / 149.66]
        expect = (sum(recent) / 5) / (sum(early) / 5)
        assert expect == pytest.approx(0.4398, abs=1e-3)
        assert self.f["tightening_ratio"] == pytest.approx(expect, rel=1e-9)
        assert self.f["tightening_ratio"] < 0.75 and self.f["tightening_ok"] is True

    def test_ma_flags(self):
        # SMA20 = 145.671 (the operator note's "145.67"); close 145.62 >= 0.98 x that
        assert self.f["sma20"] == pytest.approx(145.671, abs=1e-3)
        assert self.f["sma20_ok"] is True
        # SMA50 = mean of the 50 closes 2026-07-08..2026-09-16 =
        # 94.9316; ten sessions earlier it was the mean of the 50 closes 2026-06-23..2026-09-01
        # = 80.2148 (both summed straight off the fixture's close column, not via the module).
        assert self.f["sma50"] == pytest.approx(94.9316, abs=1e-3)
        sma50_ten_sessions_ago = 80.2148
        assert self.f["sma50"] > sma50_ten_sessions_ago and self.f["sma50_rising"] is True
        assert 145.62 >= 94.9316 and self.f["close"] == 145.62      # a long way above the 50-day

    def test_features_are_plain_json_types(self):
        json.dumps(self.f)
        for k, v in self.f.items():
            assert type(v) in (int, float, bool, str, type(None)), (k, type(v))

    def test_adr20_and_atr14_match_an_independent_computation(self):
        i, b = self.i, self.bars
        adr = np.mean((b.h[i - 19:i + 1] - b.l[i - 19:i + 1]) / b.c[i - 19:i + 1])
        assert self.f["adr20"] == pytest.approx(adr, rel=1e-12)
        trs = [max(b.h[j] - b.l[j], abs(b.h[j] - b.c[j - 1]), abs(b.l[j] - b.c[j - 1]))
               for j in range(i - 13, i + 1)]
        assert self.f["atr14"] == pytest.approx(np.mean(trs) / b.c[i], rel=1e-12)    # a FRACTION
        rng = (b.h[i] - b.l[i]) / b.c[i]
        assert self.f["trigger_bar_range_adr"] == pytest.approx(rng / adr, rel=1e-12)
        assert self.f["inside_day"] is False     # 09-16 high 148.93 > 09-15 high 148.6999

    def test_cells_on_the_canary(self):
        ctx = {"rs_best": 99.5, "rs_all": 99.0, "grp_pct": 90.0,
               "phase_qqq_10_20": True, "phase_spy_qqq_50": True}
        for k in cb.PIVOT_KEYS:
            flags = cb.cell_flags(self.f, ctx, k=k)
            assert all(flags[c] for c in cb.CELLS), (k, flags)

    def test_entry_on_the_breakout_day_is_above_the_k5_pivot(self):
        # 09-17: the open (152.50) gaps over the 149.7344 pivot, so the PIVOT entry fills at that
        # open, not at the level — the gap-through branch. ORH5 = max(153.0, 149.7344) = 153.0 sits
        # ABOVE the open, so ORH5 does not gap: minute 5 opens 152.9 <= 153.0 and fills AT its level.
        mins = _flat_day(price=152.5, overrides={
            0: (152.5, 153.0, 152.0, 152.8), 5: (152.9, 154.0, 152.8, 153.9)}, hi=0.5)
        res = cb.entry_variants(mins, pivot=self.f["pivot_k5"], adr20=self.f["adr20"],
                                day_high=float(mins.h.max()), day_low=float(mins.l.min()))
        assert res["pivot"]["status"] == "filled" and res["pivot"]["fill_minute"] == 0
        assert res["pivot"]["level"] == self.f["pivot_k5"]
        assert res["pivot"]["fill"] == pytest.approx(152.5 * (1 + ENTRY_SLIPPAGE_PCT))
        assert res["orh5"]["status"] == "filled" and res["orh5"]["fill_minute"] == 5
        assert res["orh5"]["level"] == 153.0
        assert res["orh5"]["fill"] == pytest.approx(153.0 * (1 + ENTRY_SLIPPAGE_PCT))


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1b. Synthetic: each C0 gate fails alone; each flag flips alone
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestC0Gates:
    def test_control_passes(self):
        s = Synth()
        f = s.watch()
        assert f is not None
        assert f["pole_idx"] == s.P and f["base_len"] == 20
        assert f["prior_move"] == pytest.approx(16.0 / 9.9 - 1.0)
        assert f["higher_lows"] and f["tightening_ok"] and f["sma20_ok"] and f["sma50_rising"]
        assert f["inside_day"] is False

    def test_history_gate(self):
        assert Synth(n=130).watch() is not None            # i = 129: allowed
        assert Synth(n=129).watch() is None                # i = 128: 129 sessions

    def test_out_of_range_index_is_a_caller_bug(self):
        b = Synth().bars()
        with pytest.raises(IndexError):
            cb.evaluate_watch(b, len(b))

    def test_prior_move_gate_boundary(self):
        # pole low is the pad's 9.9: 12.9/9.9 - 1 = 30.3% passes, 12.8/9.9 - 1 = 29.3% fails
        assert Synth(top=12.9).watch() is not None
        assert Synth(top=12.8).watch() is None

    def test_no_new_high_since_pole(self):
        s = Synth()
        assert s.watch() is not None
        s.h[s.i - 3] = s.top * 1.01                       # outside [i-45, i-10]: P stays, base broken
        assert s.watch() is None

    def test_a_later_higher_high_inside_the_window_re_anchors_the_pole(self):
        s = Synth()
        s.h[s.i - 12] = s.top * 1.01                      # inside the window -> this IS the new P
        f = s.watch()
        assert f is not None and f["pole_idx"] == s.i - 12 and f["base_len"] == 12

    def test_pole_high_ties_resolve_to_the_latest(self):
        s = Synth()
        s.h[s.P - 5] = s.top                              # an equal high 5 sessions earlier
        f = s.watch()
        assert f["pole_idx"] == s.P                       # not P-5

    def test_base_length_bounds_are_inclusive(self):
        for base_n in (10, 45):
            f = Synth(base_n=base_n).watch()
            assert f is not None and f["base_len"] == base_n, base_n

    def test_a_pole_46_sessions_back_is_outside_the_window(self):
        # the 16.0 high at i-46 cannot be P; the best high left is a mid-base bar whose own "prior
        # move" from the base lows is ~10% -> None. (A 46-session base is not a valid base.)
        assert Synth(base_n=46).watch() is None
        assert Synth(base_n=45).watch() is not None

    def test_pole_low_window_is_40_sessions_before_the_pole_day(self):
        s = Synth()
        s.l[s.P - 35] = 8.0                                # inside [P-40, P]
        s.l[s.P - 41] = 5.0                                # one session past it
        f = s.watch()
        assert f["pole_low"] == 8.0 and f["pole_low_idx"] == s.P - 35
        assert f["pole_sessions"] == 35
        s2 = Synth()
        s2.l[s2.P - 40] = 8.0                              # the window's first session
        assert s2.watch()["pole_low"] == 8.0

    def test_pole_nine_sessions_back_is_not_a_base_yet(self):
        # top at i-9 sits outside [i-45, i-10]; the window's best high is the ramp's 15.7, which
        # the 16.0 high AFTER it has already beaten -> no valid P -> None
        assert Synth(base_n=9).watch() is None

    def test_pivot_windows_include_exactly_the_last_5_and_10_sessions(self):
        s = Synth()
        base = s.watch()
        # a new highest high at i-4 is the last bar INSIDE the 5-session window
        s.h[s.i - 4] = 15.9
        f = s.watch()
        assert f["pivot_k5"] == 15.9 and f["pivot_k5_idx"] == s.i - 4
        assert base["pivot_k5"] < 15.9
        # at i-5 it is OUTSIDE the 5-session window but inside the 10-session one
        s = Synth()
        s.h[s.i - 5] = 15.9
        f = s.watch()
        assert f["pivot_k5"] < 15.9 and f["pivot_k10"] == 15.9 and f["pivot_k10_idx"] == s.i - 5
        # i-9 is the last bar inside the 10-session window; i-10 is outside it (but in the full base)
        s = Synth()
        s.h[s.i - 9] = 15.95
        assert s.watch()["pivot_k10"] == 15.95
        s = Synth()
        s.h[s.i - 10] = 15.95
        f = s.watch()
        assert f["pivot_k10"] < 15.95 and f["pivot_full"] == 15.95
        # the full pivot excludes the pole day itself (P+1..i)
        assert f["pivot_full"] < s.top

    def test_moving_averages_are_the_plain_means_ending_on_i(self):
        s = Synth()
        f = s.watch()
        c = np.array(s.c)
        assert f["sma10"] == pytest.approx(c[s.i - 9:s.i + 1].mean())
        assert f["sma20"] == pytest.approx(c[s.i - 19:s.i + 1].mean())
        assert f["sma50"] == pytest.approx(c[s.i - 49:s.i + 1].mean())

    def test_sma50_gate_includes_todays_close(self):
        # close >= SMA50 over [i-49, i]  <=>  close >= the mean of the 49 closes before it
        s = Synth()
        m49 = float(np.mean(s.c[s.i - 49:s.i]))
        s.c[s.i] = m49 - 0.01
        s.h[s.i], s.l[s.i], s.o[s.i] = s.c[s.i] * 1.01, s.c[s.i] * 0.99, s.c[s.i]
        assert s.watch() is None
        s2 = Synth()
        s2.c[s2.i] = m49 + 0.01
        s2.h[s2.i], s2.l[s2.i], s2.o[s2.i] = s2.c[s2.i] * 1.01, s2.c[s2.i] * 0.99, s2.c[s2.i]
        assert s2.watch() is not None

    def test_close_below_sma50(self):
        s = Synth()
        assert s.watch() is not None
        s.c[s.i], s.o[s.i], s.h[s.i], s.l[s.i] = 12.0, 12.0, 12.1, 11.9     # SMA50 is ~13.2
        assert s.watch() is None

    def test_deal_pin_guard_uses_the_median_of_the_last_five_ranges(self):
        s = Synth()
        for k in (s.i - 4, s.i - 3, s.i - 2):             # 3 of 5 pinned -> median 0.2% < 0.5%
            s.h[k], s.l[k] = s.c[k] * 1.001, s.c[k] * 0.999
        assert s.watch() is None
        s2 = Synth()
        for k in (s2.i - 4, s2.i - 3):                    # only 2 of 5 pinned -> median still 2%
            s2.h[k], s2.l[k] = s2.c[k] * 1.001, s2.c[k] * 0.999
        assert s2.watch() is not None

    def test_sma20_ok_flips(self):
        s = Synth()
        assert s.watch()["sma20_ok"] is True
        s.c[s.i] = 14.0                                   # >= SMA50 (~13.2) but < 0.98 x SMA20 (~14.5)
        s.h[s.i], s.l[s.i], s.o[s.i] = 14.14, 13.86, 14.0
        f = s.watch()
        assert f is not None and f["sma20_ok"] is False

    def test_sma50_rising_flips(self):
        s = Synth()
        assert s.watch()["sma50_rising"] is True
        for k in range(s.i - 59, s.i - 54):               # 5 bars that leave SMA50 between i-10 and i
            s.o[k] = s.c[k] = 30.0                         # (and are gone by i-5: the slope is over 10, not 5)
            s.h[k], s.l[k] = 30.3, 29.7
        f = s.watch()
        assert f is not None and f["sma50_rising"] is False

    def test_higher_lows_flips(self):
        s = Synth()
        assert s.watch()["higher_lows"] is True
        s.l[s.i - 2] = 13.0                               # under every base low
        f = s.watch()
        assert f["higher_lows"] is False and f["base_low"] == 13.0

    def test_tightening_flips(self):
        s = Synth()
        assert s.watch()["tightening_ok"] is True
        for k in range(s.i - 4, s.i + 1):                 # last 5 as wide as the first 5 (8%)
            s.h[k], s.l[k] = s.c[k] * 1.04, s.c[k] * 0.96
        f = s.watch()
        assert f is not None and f["tightening_ratio"] > 0.75 and f["tightening_ok"] is False

    def test_inside_day_flips(self):
        s = Synth()
        assert s.watch()["inside_day"] is False
        s.h[s.i] = s.h[s.i - 1] - 0.01
        s.l[s.i] = s.l[s.i - 1] + 0.01
        assert s.watch()["inside_day"] is True
        s.h[s.i], s.l[s.i] = s.h[s.i - 1], s.l[s.i - 1]    # equal high and low still count (<=, >=)
        assert s.watch()["inside_day"] is True
        s.h[s.i] = s.h[s.i - 1] + 0.01                      # one cent over yesterday's high
        assert s.watch()["inside_day"] is False

    def test_phase_cells_do_not_touch_c0(self):
        f = Synth().watch()
        flags = cb.cell_flags(f, {"rs_best": 99.9, "grp_pct": 99.0}, k="k5")
        assert flags["C0"] is True and flags["C1"] is False      # no phase in ctx -> False


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Cross-sectional features
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestCrossSection:
    def test_rs_returns(self):
        c = [100.0 + k for k in range(130)]               # close[k] = 100 + k
        b = _closes_only(c)
        r21, r63, r126 = cb.rs_returns(b, 129)
        assert r21 == pytest.approx(229.0 / 208.0 - 1)
        assert r63 == pytest.approx(229.0 / 166.0 - 1)
        assert r126 == pytest.approx(229.0 / 103.0 - 1)
        assert cb.rs_returns(b, 100) == (pytest.approx(200 / 179 - 1), pytest.approx(200 / 137 - 1), None)
        assert cb.rs_returns(b, 10) == (None, None, None)

    def test_percentile_ranks_hand_computed(self):
        # sorted ascending: 5 (pos0), 7 (pos1), 9 (pos2), 20 (pos3); n-1 = 3
        assert cb.percentile_ranks([9, 5, None, 20, 7]) == [66.7, 0.0, None, 100.0, 33.3]
        assert cb.percentile_ranks([None, None]) == [None, None]
        assert cb.percentile_ranks([3.0]) == [0.0]
        assert cb.percentile_ranks([]) == []

    def test_percentile_ranks_equals_rs_engines(self):
        from agents.market_intelligence import rs_engine
        rng = np.random.default_rng(7)
        sample = [None if k % 9 == 0 else float(x) for k, x in enumerate(rng.normal(size=400))]
        sample += [0.25, 0.25, 0.25]                       # ties rank in input order in both
        assert cb.percentile_ranks(sample) == rs_engine._percentile_ranks(sample)

    def test_universe_constants_mirror_rs_engine(self):
        from agents.market_intelligence import rs_engine
        assert cb.MIN_PRICE == rs_engine.MIN_PRICE == 5.0
        assert cb.MIN_DOLLAR_VOL == rs_engine.MIN_DOLLAR_VOL == 10_000_000.0

    def test_group_returns(self):
        twelve = [0.01 * k for k in range(12)]             # median of 12 = (0.05 + 0.06) / 2
        nine = [0.5] * 9
        ten = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        out = cb.group_returns({"28": twelve, "36": nine, "73": ten})
        assert out == {"28": pytest.approx(0.055), "73": pytest.approx(0.55)}
        assert "36" not in out                              # 9 members -> NULL
        with_none = [0.1] * 9 + [None]                      # a None is not a member
        assert cb.group_returns({"x": with_none}) == {}
        assert cb.group_returns({"x": [3.0, 1.0, 2.0]}, min_members=3) == {"x": 2.0}

    def test_sic2(self):
        assert cb.sic2("2834") == "28" and cb.sic2(2834) == "28" and cb.sic2(2834.0) == "28"
        assert cb.sic2(100) == "01"                         # an int lost its leading zero
        assert cb.sic2(" 7372 ") == "73"
        for bad in (None, "", "A", "7", float("nan"), True, "28x4"):
            assert cb.sic2(bad) is None, bad

    def test_phase_qqq_10_20_rising_falling_and_short_history(self):
        up = _closes_only([100.0 + k for k in range(60)])
        assert cb.phase_qqq_10_20(up, 59) and cb.phase_qqq_10_20(up, 59, slope=5)
        down = _closes_only([200.0 - k for k in range(60)])
        assert not cb.phase_qqq_10_20(down, 59)
        assert not cb.phase_qqq_10_20(up, 18)               # < 20 sessions
        assert not cb.phase_qqq_10_20(up, 20, slope=5)      # SMA20(j-5) does not exist
        assert cb.phase_qqq_10_20(up, 20, slope=1)          # exactly enough
        with pytest.raises(ValueError):
            cb.phase_qqq_10_20(up, 59, slope=0)

    def test_phase_rules_reject_an_index_past_the_last_bar(self):
        # a caller that mis-joins QQQ/SPY to the watch night must fail loudly, not average a
        # truncated window (a numpy slice past the end does not raise by itself)
        up = _closes_only([100.0 + k for k in range(60)])
        assert cb.phase_qqq_10_20(up, 59) is True                  # the last bar is fine
        for j in (60, 63):
            with pytest.raises(IndexError):
                cb.phase_qqq_10_20(up, j)
            with pytest.raises(IndexError):
                cb.phase_spy_qqq_50(up, up, j, 59)
            with pytest.raises(IndexError):
                cb.phase_spy_qqq_50(up, up, 59, j)

    def test_phase_slope_matters(self):
        # 100..149 then 146 142 138 141 145 148 (sessions 50..55). Hand-checked:
        #   j=55: SMA10 145.0 > SMA20 142.75; vs j-1: 144.7 / 142.1 (both up)  -> slope 1 True
        #         vs j-5: SMA10 was 145.1 (down)                                  -> slope 5 False
        #   j=52: SMA10 144.8 fell from 145.2 -> slope 1 False; vs j-5 (142.5 / 137.5) both up -> slope 5 True
        s = _closes_only([100.0 + k for k in range(50)] + [146, 142, 138, 141, 145, 148])
        assert cb.phase_qqq_10_20(s, 55, slope=1) is True
        assert cb.phase_qqq_10_20(s, 55, slope=5) is False
        assert cb.phase_qqq_10_20(s, 52, slope=1) is False
        assert cb.phase_qqq_10_20(s, 52, slope=5) is True

    def test_phase_spy_qqq_50(self):
        up = _closes_only([100.0 + k for k in range(60)])
        down = _closes_only([200.0 - k for k in range(60)])
        assert cb.phase_spy_qqq_50(up, up, 59, 59) is True
        assert cb.phase_spy_qqq_50(up, down, 59, 59) is False
        assert cb.phase_spy_qqq_50(down, up, 59, 59) is False
        assert cb.phase_spy_qqq_50(up, up, 48, 59) is False      # SPY has < 50 sessions
        assert cb.phase_spy_qqq_50(up, up, 49, 49) is True       # exactly 50, close above its SMA50


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Universe
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _uni_bars(close=20.0, vol=1e6, n=140):
    return cb.daily_bars_from_arrays(_weekdays(n), [close] * n, [close] * n, [close] * n,
                                     [close] * n, [vol] * n)


class TestUniverse:
    def test_raw_factor_forward_split_nvda_like(self):
        splits = [(dt.date(2024, 6, 10), 10.0)]            # 10:1
        assert cb.raw_factor_for(dt.date(2024, 6, 7), splits) == 10.0
        assert cb.raw_factor_for(dt.date(2024, 6, 10), splits) == 1.0   # execution date is post-split
        assert cb.raw_factor_for(dt.date(2024, 6, 11), splits) == 1.0

    def test_raw_factor_reverse_split_amc_like(self):
        splits = [(dt.date(2023, 8, 24), 0.1)]             # 1:10 reverse
        assert cb.raw_factor_for(dt.date(2023, 8, 23), splits) == pytest.approx(0.1)
        assert cb.raw_factor_for(dt.date(2023, 8, 24), splits) == 1.0

    def test_raw_factor_compounds_and_validates(self):
        splits = [(dt.date(2022, 1, 5), 4.0), (dt.date(2024, 1, 5), 0.5)]
        assert cb.raw_factor_for(dt.date(2021, 12, 1), splits) == pytest.approx(2.0)
        assert cb.raw_factor_for(dt.date(2023, 1, 1), splits) == pytest.approx(0.5)
        assert cb.raw_factor_for(dt.date(2025, 1, 1), splits) == 1.0
        assert cb.raw_factor_for(dt.date(2025, 1, 1), []) == 1.0
        with pytest.raises(ValueError):
            cb.raw_factor_for(dt.date(2020, 1, 1), [(dt.date(2021, 1, 1), 0.0)])

    def test_reverse_split_pump_adjusted_above_five_but_raw_below(self):
        # adjusted close 40 looks like a $40 stock; raw it traded at 40 x 0.1 = $4 -> excluded
        b = _uni_bars(close=40.0, vol=1e6)
        assert cb.universe_ok(b, 139, raw_factor=1.0, ticker="AMC", security_type="CS") is True
        assert cb.universe_ok(b, 139, raw_factor=0.1, ticker="AMC", security_type="CS") is False

    def test_forward_split_adjusted_below_five_but_raw_above(self):
        b = _uni_bars(close=0.8, vol=2e7)                  # 0.8 x 2e7 = $16M a day
        assert cb.universe_ok(b, 139, raw_factor=1.0, ticker="NVDA", security_type=None) is False
        assert cb.universe_ok(b, 139, raw_factor=10.0, ticker="NVDA", security_type=None) is True

    def test_price_floor_boundary(self):
        b = _uni_bars(close=5.0, vol=3e6)
        assert cb.universe_ok(b, 139, raw_factor=1.0, ticker="X", security_type="CS") is True
        b2 = _uni_bars(close=4.99, vol=3e6)
        assert cb.universe_ok(b2, 139, raw_factor=1.0, ticker="X", security_type="CS") is False

    def test_dollar_volume_median_threshold(self):
        assert cb.universe_ok(_uni_bars(20.0, 5e5), 139, raw_factor=1.0, ticker="AB", security_type="CS")   # exactly $10M
        assert not cb.universe_ok(_uni_bars(20.0, 4.9e5), 139, raw_factor=1.0, ticker="AB", security_type="CS")
        # one huge print does not rescue a thin name: the median is what counts
        b = _uni_bars(20.0, 2e5)
        v = b.v.copy()
        v[130] = 1e9
        spiky = cb.daily_bars_from_arrays(b.dates, b.o, b.h, b.l, b.c, v)
        assert not cb.universe_ok(spiky, 139, raw_factor=1.0, ticker="AB", security_type="CS")

    def test_ticker_shape(self):
        b = _uni_bars(20.0, 1e6)
        ok = lambda t: cb.universe_ok(b, 139, raw_factor=1.0, ticker=t, security_type="CS")
        assert ok("A") and ok("AAPL") and ok("GOOGL")
        for bad in ("BRK.B", "abc", "TOOLONG", "", "AB1", "AAPL\n", "AAPL ", None):
            assert not ok(bad), bad

    def test_security_type(self):
        b = _uni_bars(20.0, 1e6)
        f = lambda st: cb.universe_ok(b, 139, raw_factor=1.0, ticker="ABC", security_type=st)
        assert f("CS") and f("ADRC") and f(None) and f("")
        for bad in ("ETF", "WARRANT", "PFD", "FUND", "cs"):
            assert not f(bad), bad

    def test_history_floor_and_range(self):
        b = _uni_bars(20.0, 1e6)
        assert cb.universe_ok(b, 129, raw_factor=1.0, ticker="ABC", security_type="CS")
        assert not cb.universe_ok(b, 128, raw_factor=1.0, ticker="ABC", security_type="CS")
        assert not cb.universe_ok(b, 5000, raw_factor=1.0, ticker="ABC", security_type="CS")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Cells
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _good_features(**over):
    f = dict(Synth().watch())
    f.update(over)
    return f


def _ctx(rs=99.5, grp=90.0, qqq=True, spyqqq=False, rs_all=None):
    return {"rs_best": rs, "rs_all": rs_all, "grp_pct": grp,
            "phase_qqq_10_20": qqq, "phase_spy_qqq_50": spyqqq}


class TestCells:
    def test_table(self):
        f = _good_features()
        F, T = False, True
        cases = [   # ctx kwargs -> C0..C7
            (dict(),                          [T, T, T, T, T, T, T, F]),   # rs 99.5, grp 90, qqq phase, no spy/qqq
            (dict(rs=98.0, grp=79.9),         [T, T, F, T, T, T, F, F]),   # 98 is inclusive; grp just under 80
            (dict(rs=97.9),                   [T, F, F, F, T, T, F, F]),   # under 98: C1 out, C5 (>=95) and C4 (no RS) stay
            (dict(rs=94.9),                   [T, F, F, F, T, F, F, F]),
            (dict(rs=98.0, qqq=False, spyqqq=True), [T, F, F, T, F, F, F, T]),   # C3 no phase; C7 spy/qqq rule
            (dict(grp=None),                  [T, T, F, T, T, T, F, F]),   # no group -> C2, C6 False
            (dict(rs=None, spyqqq=True),      [T, F, F, F, T, F, F, F]),   # no RS -> every RS cell False
            (dict(rs=99.0),                   [T, T, T, T, T, T, T, F]),   # 99 is inclusive for C2
        ]
        for kw, want in cases:
            flags = cb.cell_flags(f, _ctx(**kw), k="k5")
            assert [flags[c] for c in cb.CELLS] == want, (kw, flags)

    def test_prior_move_term_in_c2(self):
        ctx = _ctx()
        assert cb.cell_flags(_good_features(prior_move=0.49), ctx, k="k5")["C2"] is False
        assert cb.cell_flags(_good_features(prior_move=0.49), ctx, k="k5")["C1"] is True
        assert cb.cell_flags(_good_features(prior_move=0.50), ctx, k="k5")["C2"] is True

    @pytest.mark.parametrize("flag", ["sma20_ok", "sma50_rising", "higher_lows", "tightening_ok"])
    def test_each_structure_flag_gates_c1_to_c7_but_not_c0(self, flag):
        flags = cb.cell_flags(_good_features(**{flag: False}), _ctx(spyqqq=True), k="k5")
        assert flags["C0"] is True
        assert not any(flags[c] for c in cb.CELLS[1:]), flags

    def test_c0_needs_the_chosen_pivot_under_the_pole_high(self):
        f = _good_features()
        assert cb.cell_flags(f, _ctx(), k="full")["C0"] is True
        bad = dict(f, pivot_full=f["pole_high"] + 0.01)
        assert cb.cell_flags(bad, _ctx(), k="full")["C0"] is False
        assert cb.cell_flags(bad, _ctx(), k="k5")["C0"] is True      # other pivot unaffected

    def test_k_has_no_default_and_is_validated(self):
        f = _good_features()
        with pytest.raises(TypeError):
            cb.cell_flags(f, _ctx())                                  # type: ignore[call-arg]
        with pytest.raises(ValueError):
            cb.cell_flags(f, _ctx(), k="k7")
        with pytest.raises(ValueError):
            cb.breakout_key("ABC", f, "5")

    def test_no_watch_row_means_no_cells(self):
        assert cb.cell_flags(None, _ctx(), k="k5") == {c: False for c in cb.CELLS}

    def test_breakout_key_is_ticker_and_pivot_date(self):
        b, idx = _mrna()
        f = cb.evaluate_watch(b, idx["2026-09-16"])
        assert cb.breakout_key("MRNA", f, "k5") == ("MRNA", "2026-09-11")
        assert cb.breakout_key("MRNA", f, "k10") == ("MRNA", "2026-09-02")
        assert cb.breakout_key("MRNA", f, "full") == ("MRNA", "2026-08-25")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Entries
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _flat_day(price=100.0, overrides=None, hi=0.1, post=None):
    """A 390-minute session at `price` (range +-hi). `overrides` = {minute: (o, h, l, c)}.
    `post` = (from_minute, price) re-levels every minute AFTER that one to a quiet price whose
    low sits well above the morning's, so a stop under the early lows is never touched."""
    n = 390
    o = [price] * n
    h = [price + hi] * n
    l = [price - hi] * n
    c = [price] * n
    if post is not None:
        start, pp = post
        for m in range(start + 1, n):
            o[m], h[m], l[m], c[m] = pp, pp + 0.1, pp - 0.1, pp
    for m, (oo, hh, ll, cc) in (overrides or {}).items():
        o[m], h[m], l[m], c[m] = oo, hh, ll, cc
    return cb.minute_bars_from_lists(list(range(n)), o, h, l, c, [1000] * n)


def _run(mins, pivot=100.5, adr20=0.05, **kw):
    return cb.entry_variants(mins, pivot=pivot, adr20=adr20, day_high=float(mins.h.max()),
                             day_low=float(mins.l.min()), **kw)


class TestEntries:
    def test_orh5_normal_trigger_and_the_other_variants_on_the_same_day(self):
        # ORH5 = 101.0 (minute 3). Minute 12 is the first minute >= 5 trading above it.
        mins = _flat_day(overrides={3: (100.0, 101.0, 99.9, 100.5),
                                    12: (100.8, 101.5, 100.7, 101.2)}, post=(12, 101.2))
        r = _run(mins, pivot=100.5)
        o5 = r["orh5"]
        assert o5["status"] == "filled" and o5["reason"] is None
        assert o5["level"] == 101.0 and o5["fill_minute"] == 12
        assert o5["fill"] == pytest.approx(101.0 * 1.001)           # open 100.8 <= level -> fills AT the level
        assert o5["stop"] == 99.9                                    # low of the day up to the fill
        assert o5["width_pct"] == pytest.approx((101.101 - 99.9) / 101.101)
        assert o5["day0"] == {"stopped": False, "exit_price": None, "exit_minute": None}
        # PIVOT 100.5: the minute-3 spike (high 101.0) is the first to clear it
        assert r["pivot"]["fill_minute"] == 3 and r["pivot"]["level"] == 100.5
        assert r["pivot"]["fill"] == pytest.approx(100.5 * 1.001)
        # ORH1 (minute 0 only: high 100.1) -> level max(100.1, 100.5) = 100.5 -> the same minute 3
        assert r["orh1"]["fill_minute"] == 3 and r["orh1"]["level"] == 100.5
        # ORH60 spans minutes 0..59 -> 101.5 (minute 12 is inside it); nothing later clears 101.5
        assert r["orh60"]["status"] == "no_trigger" and r["orh60"]["fill"] is None

    def test_gap_through_the_level_fills_at_the_open(self):
        mins = _flat_day(overrides={3: (100.0, 101.0, 99.9, 100.5),
                                    12: (102.0, 102.5, 101.9, 102.3)}, post=(12, 102.3))
        o5 = _run(mins)["orh5"]
        assert o5["fill_minute"] == 12 and o5["level"] == 101.0
        assert o5["fill"] == pytest.approx(102.0 * 1.001)           # NOT 101.0 x 1.001
        assert o5["stop"] == 99.9
        assert o5["width_pct"] == pytest.approx((102.102 - 99.9) / 102.102)

    def test_pivot_above_the_opening_range_sets_the_level(self):
        mins = _flat_day(overrides={3: (100.0, 101.0, 99.9, 100.5),
                                    20: (102.9, 103.2, 102.8, 103.1)}, post=(20, 103.1))
        r = _run(mins, pivot=103.0)
        assert r["orh5"]["level"] == 103.0 and r["orh5"]["fill_minute"] == 20
        assert r["orh5"]["fill"] == pytest.approx(103.0 * 1.001)    # open 102.9 <= 103.0
        assert r["pivot"]["level"] == 103.0 and r["pivot"]["fill_minute"] == 20

    def test_variants_with_different_triggers(self):
        # Pivot 100.5 is cleared at minute 1 (high 101.0) and never again after minute 5.
        mins = _flat_day(overrides={1: (100.0, 101.0, 99.9, 100.4)}, post=(1, 100.6))
        r = _run(mins, pivot=100.5)
        assert r["orh5"]["status"] == "no_trigger" and r["orh5"]["reason"] == "no_minute_above_level"
        assert r["orh5"]["level"] == 101.0                           # max(ORH5, pivot)
        assert r["orh60"]["status"] == "no_trigger"
        assert r["orh1"]["status"] == "filled" and r["orh1"]["fill_minute"] == 1
        assert r["pivot"]["status"] == "filled" and r["pivot"]["fill_minute"] == 1

    def test_orh60_cannot_trigger_before_minute_60(self):
        mins = _flat_day(overrides={
            10: (100.0, 101.0, 99.9, 100.9),                         # clears ORH5 (100.1) early
            30: (101.2, 101.5, 101.1, 101.4),                        # the morning's high: ORH60 = 101.5
            70: (101.9, 102.5, 101.8, 102.4)}, post=(70, 102.4))
        mins = _with_quiet_morning(mins)
        r = _run(mins, pivot=100.0)
        assert r["orh5"]["fill_minute"] < 60
        assert r["orh60"]["status"] == "filled"
        assert r["orh60"]["fill_minute"] == 70 and r["orh60"]["level"] == 101.5
        assert r["orh60"]["fill"] == pytest.approx(101.9 * 1.001)    # gapped over 101.5 at the open
        # Nothing before minute 60 can be an ORH60 fill because the level IS the running high of
        # minutes 0..59: no earlier minute can exceed it, so the `minute >= k` mask in _entry_one is
        # defensive only and cannot be told apart from its absence. The pin is the level itself.
        assert r["orh60"]["level"] >= float(mins.h[mins.minute < 60].max())

    def test_day0_case_a_0937_fill_then_the_morning_low_breaks_at_1015(self):
        # ORH5 100.1, pivot 100.5 -> level 100.5. Fill at minute 7 (09:37). Stop = low of minutes 0..7
        # = 99.9. Minute 45 (10:15) trades 99.5 -> the stop is hit at 99.9 = exactly -1R.
        mins = _flat_day(overrides={
            7: (100.2, 101.0, 100.0, 100.9),
            45: (100.0, 100.1, 99.5, 99.8)}, post=(7, 100.8))
        mins = _relevel(mins, 45, (100.0, 100.1, 99.5, 99.8))
        e = _run(mins, pivot=100.5)["orh5"]
        assert e["status"] == "filled" and e["fill_minute"] == 7
        assert e["fill"] == pytest.approx(100.5 * 1.001) and e["stop"] == 99.9
        assert e["day0"] == {"stopped": True, "exit_price": 99.9, "exit_minute": 45}
        out = cb.day0_result_to_outcome(e, 0.05)
        assert out["status"] == "stopped_day0"
        assert out["realized_r"] == pytest.approx(-1.0, abs=1e-12)
        assert out["sessions_held"] == 0
        assert out["events"] == [(0, "day0_stop", 99.9, 1.0)]
        assert out["pnl_adr"] == pytest.approx((99.9 - e["fill"]) / (e["fill"] * 0.05))

    def test_day0_gap_below_the_stop_exits_at_the_open_worse_than_1r(self):
        mins = _flat_day(overrides={7: (100.2, 101.0, 100.0, 100.9)}, post=(7, 100.8))
        mins = _relevel(mins, 45, (99.0, 99.2, 98.8, 99.1))
        e = _run(mins, pivot=100.5)["orh5"]
        assert e["day0"] == {"stopped": True, "exit_price": 99.0, "exit_minute": 45}
        out = cb.day0_result_to_outcome(e, 0.05)
        assert out["realized_r"] == pytest.approx((99.0 - e["fill"]) / (e["fill"] - 99.9))
        assert out["realized_r"] < -1.0
        assert out["events"][0][1] == "day0_gap"

    def test_day0_survivor_is_not_stopped_and_cannot_be_booked_as_a_stop_out(self):
        mins = _flat_day(overrides={7: (100.2, 101.0, 100.0, 100.9)}, post=(7, 100.8))
        e = _run(mins, pivot=100.5)["orh5"]
        assert e["day0"]["stopped"] is False
        with pytest.raises(ValueError):
            cb.day0_result_to_outcome(e, 0.05)

    def test_day0_walk_is_public_for_the_cap_not_skip_sensitivity(self):
        mins = _flat_day(overrides={7: (100.2, 101.0, 100.0, 100.9)}, post=(7, 100.8))
        mins = _relevel(mins, 45, (100.6, 100.7, 100.4, 100.5))
        assert cb.day0_walk(mins, fill_minute=7, stop=99.9)["stopped"] is False
        # a capped (tighter) stop of 100.45 is first touched by minute 45's low of 100.4 (open 100.6 is above it)
        assert cb.day0_walk(mins, fill_minute=7, stop=100.45) == {
            "stopped": True, "exit_price": 100.45, "exit_minute": 45}
        # the walk only looks AFTER the fill minute: a stop under the fill bar's own low is not re-tested
        assert cb.day0_walk(mins, fill_minute=45, stop=100.45)["stopped"] is False

    # ── abstains ───────────────────────────────────────────────────────────────────────────────
    @pytest.mark.parametrize("minutes", [None, cb.minute_bars_from_lists([], [], [], [], [], [])])
    def test_abstain_no_minutes(self, minutes):
        r = cb.entry_variants(minutes, pivot=100.0, adr20=0.05, day_high=101.0, day_low=99.0)
        assert set(r) == set(cb.ENTRY_VARIANTS)
        assert all(v["status"] == "abstain" and v["reason"] == "no_minutes" for v in r.values())

    def test_abstain_minute_daily_mismatch(self):
        mins = _flat_day(overrides={7: (100.2, 101.0, 100.0, 100.9)})
        r = cb.entry_variants(mins, pivot=100.5, adr20=0.05, day_high=float(mins.h.max()) * 1.02,
                              day_low=float(mins.l.min()))
        assert all(v["reason"] == "minute_daily_mismatch" for v in r.values())
        # inside the 1% tolerance is fine; a bad low trips it too
        ok = cb.entry_variants(mins, pivot=100.5, adr20=0.05, day_high=float(mins.h.max()) * 1.009,
                               day_low=float(mins.l.min()))
        assert ok["pivot"]["reason"] != "minute_daily_mismatch"
        low = cb.entry_variants(mins, pivot=100.5, adr20=0.05, day_high=float(mins.h.max()),
                                day_low=float(mins.l.min()) * 0.98)
        assert all(v["reason"] == "minute_daily_mismatch" for v in low.values())

    def test_abstain_minute_high_below_pivot(self):
        mins = _flat_day()                                           # max high 100.1
        r = _run(mins, pivot=105.0)
        assert all(v["status"] == "abstain" and v["reason"] == "minute_high_below_pivot"
                   for v in r.values())

    def test_abstain_order_mismatch_beats_below_pivot_and_no_minutes_beats_all(self):
        mins = _flat_day()
        r = cb.entry_variants(mins, pivot=105.0, adr20=0.05, day_high=110.0, day_low=99.9)
        assert all(v["reason"] == "minute_daily_mismatch" for v in r.values())

    def test_abstain_stop_at_or_above_fill(self):
        # a single print at 103 with zero slippage: fill = open = 103 and the day's low so far is 103
        mins = _flat_day(price=103.0, hi=0.0, overrides={0: (103.0, 103.0, 103.0, 103.0)})
        r = _run(mins, pivot=102.0, slippage=0.0)
        e = r["pivot"]
        assert e["status"] == "abstain" and e["reason"] == "stop_at_or_above_fill"
        assert e["fill"] == 103.0 and e["stop"] == 103.0

    def test_abstain_too_wide_still_returns_the_numbers_for_the_cap_sensitivity(self):
        mins = _flat_day(overrides={3: (100.0, 101.0, 99.9, 100.5),
                                    12: (100.8, 101.5, 100.7, 101.2)}, post=(12, 101.2))
        e = _run(mins, pivot=100.5, adr20=0.005)["orh5"]             # 0.5% ADR vs a 1.19% stop
        assert e["status"] == "abstain" and e["reason"] == "too_wide"
        assert e["fill"] == pytest.approx(101.101) and e["stop"] == 99.9
        assert e["width_pct"] == pytest.approx((101.101 - 99.9) / 101.101)
        assert e["width_pct"] > 0.005 and e["fill_minute"] == 12

    def test_width_exactly_one_adr_is_not_too_wide(self):
        mins = _flat_day(overrides={3: (100.0, 101.0, 99.9, 100.5),
                                    12: (100.8, 101.5, 100.7, 101.2)}, post=(12, 101.2))
        width = (101.0 * 1.001 - 99.9) / (101.0 * 1.001)
        assert _run(mins, pivot=100.5, adr20=width)["orh5"]["status"] == "filled"

    def test_bad_adr20_is_a_contract_error(self):
        mins = _flat_day()
        for bad in (None, 0.0, -0.1):
            with pytest.raises(ValueError):
                cb.entry_variants(mins, pivot=100.0, adr20=bad, day_high=100.1, day_low=99.9)

    def test_opening_range_with_no_bars_abstains_that_variant_only(self):
        n = list(range(5, 390))
        mins = cb.minute_bars_from_lists(n, [100.0] * len(n), [100.1] * len(n), [99.9] * len(n),
                                         [100.0] * len(n), [1] * len(n))
        r = cb.entry_variants(mins, pivot=99.0, adr20=0.05, day_high=100.1, day_low=99.9)
        assert r["orh1"]["reason"] == "no_opening_range_minutes"
        assert r["orh5"]["reason"] == "no_opening_range_minutes"
        assert r["pivot"]["status"] == "filled" and r["pivot"]["fill_minute"] == 5

    def test_close_entry(self):
        e = cb.close_entry(101.0, 99.0, 100.0, 0.05)
        assert e["status"] == "filled" and e["fill_minute"] is None and e["level"] == 100.0
        assert e["fill"] == pytest.approx(101.0 * 1.001) and e["stop"] == 99.0
        assert e["width_pct"] == pytest.approx((101.101 - 99.0) / 101.101)
        assert e["day0"]["stopped"] is False
        assert cb.close_entry(100.0, 99.0, 100.0, 0.05)["status"] == "no_trigger"   # not strictly above
        assert cb.close_entry(101.0, 99.0, 100.0, 0.01)["reason"] == "too_wide"
        flat = cb.close_entry(101.0, 101.2, 100.0, 0.05, slippage=0.0)
        assert flat["reason"] == "stop_at_or_above_fill"

    def test_default_slippage_is_the_repo_constant(self):
        e = cb.close_entry(101.0, 99.0, 100.0, 0.05)
        assert e["fill"] == pytest.approx(101.0 * (1 + ENTRY_SLIPPAGE_PCT)) and ENTRY_SLIPPAGE_PCT == 0.001

    def test_minute_bars_validation(self):
        with pytest.raises(ValueError):
            cb.minute_bars_from_lists([0, 0], [1, 1], [1, 1], [1, 1], [1, 1], [1, 1])
        with pytest.raises(ValueError):
            cb.minute_bars_from_lists([0, 390], [1, 1], [1, 1], [1, 1], [1, 1], [1, 1])
        with pytest.raises(ValueError):
            cb.minute_bars_from_lists([0], [float("nan")], [1], [1], [1], [1])


def _relevel(mins: cb.MinuteBars, minute: int, ohlc) -> cb.MinuteBars:
    """Copy of `mins` with ONE minute replaced (so a scenario can place a late-morning break)."""
    o, h, l, c = (a.copy() for a in (mins.o, mins.h, mins.l, mins.c))
    k = int(np.flatnonzero(mins.minute == minute)[0])
    o[k], h[k], l[k], c[k] = ohlc
    return cb.minute_bars_from_lists(mins.minute, o, h, l, c, mins.v)


def _with_quiet_morning(mins: cb.MinuteBars) -> cb.MinuteBars:
    """Minutes 31..69 sit at 101.3 so nothing there beats the 101.5 morning high."""
    o, h, l, c = (a.copy() for a in (mins.o, mins.h, mins.l, mins.c))
    for k in range(31, 70):
        o[k], h[k], l[k], c[k] = 101.3, 101.4, 101.2, 101.3
    return cb.minute_bars_from_lists(mins.minute, o, h, l, c, mins.v)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Exits
# ═══════════════════════════════════════════════════════════════════════════════════════════════
BEFORE = [100.0] * 30            # pre-entry closes: SMA10/SMA20 are defined from E+1
ADR = 0.05


def _walk(rows, arm="p33_s3_t10", fill=100.0, stop=95.0, before=BEFORE, **kw):
    return cb.walk_exit(fill=fill, stop=stop, closes_before=before, fwd=_fwd(rows),
                        arm=cb.ARMS[arm], adr20=ADR, **kw)


def _drift_rows(n, step=0.5, start=100.0):
    """A steady climber: close = start + step*j, lows far above the stop, never trails."""
    return [(start + step * j - 0.2, start + step * j + 0.3, start + step * j - 0.4, start + step * j)
            for j in range(1, n + 1)]


class TestArms:
    def test_the_eleven_arms(self):
        assert len(cb.ARMS) == 11
        assert cb.ARMS["p33_s3_t10_early"].trail_before_partial
        grid = [n for n in cb.ARMS if n.startswith("p") and not n.endswith("_early")]
        assert sorted(grid) == sorted(
            f"p{p}_s{s}_t{t}" for p in (33, 50) for s in (3, 5) for t in (10, 20))
        assert "trail10_only" in cb.ARMS and "fixed_3r_12" in cb.ARMS
        assert cb.PRIMARY_ARM == "p33_s3_t10" and cb.PRIMARY_ARM in cb.ARMS
        a = cb.ARMS["p33_s3_t10"]
        assert (a.partial_frac, a.partial_session, a.trail_sma, a.kind) == (1 / 3, 3, 10, "qm")
        b = cb.ARMS["p50_s5_t20"]
        assert (b.partial_frac, b.partial_session, b.trail_sma) == (0.5, 5, 20)
        t = cb.ARMS["trail10_only"]
        assert (t.partial_frac, t.partial_session, t.trail_sma) == (0.0, None, 10)
        x = cb.ARMS["fixed_3r_12"]
        assert (x.kind, x.target_r, x.max_sessions) == ("fixed", 3.0, 12)


class TestQmExit:
    def test_partial_at_the_close_of_session_3_then_breakeven_stop_hit(self):
        rows = [(101, 103, 99, 102), (102, 104, 100, 103), (103, 106, 101, 105),
                (104, 105, 99.5, 101), (101, 102, 100, 101)]
        out = _walk(rows)
        # sell 1/3 at 105 (j=3): +5 per share x 1/3; the rest stops at breakeven 100 on j=4 (open 104 > 100)
        assert out["events"] == [(3, "partial", 105, pytest.approx(1 / 3)),
                                 (4, "stop", 100.0, pytest.approx(2 / 3))]
        pnl = (105 - 100) / 3 + 0.0
        assert out["status"] == "stopped" and out["sessions_held"] == 4
        assert out["realized_r"] == pytest.approx(pnl / 5.0)            # = 1/3 R
        assert out["realized_r"] == pytest.approx(1 / 3)
        assert out["pnl_adr"] == pytest.approx(pnl / (100.0 * ADR))

    def test_breakeven_stop_rests_from_the_next_session_not_the_partial_session(self):
        rows = [(101, 103, 99, 102), (102, 104, 100, 103),
                (103, 106, 99, 105),             # j=3 low 99 < breakeven 100, but the stop was still 95
                (104, 105, 99.5, 101)]
        out = _walk(rows)
        assert [e[:2] for e in out["events"]] == [(3, "partial"), (4, "stop")]

    def test_stop_before_partial_in_the_same_session(self):
        rows = [(101, 103, 99, 102), (102, 104, 100, 103), (103, 106, 94, 105)]   # j=3 trades 94 < 95
        out = _walk(rows)
        assert out["events"] == [(3, "stop", 95.0, 1.0)]
        assert out["realized_r"] == pytest.approx(-1.0) and out["status"] == "stopped"

    def test_trail_uses_pre_entry_closes_so_it_can_fire_on_session_1(self):
        # (a no-partial arm: on partial arms the trail waits for the partial, see below)
        before = [120.0] * 30                    # SMA10 on E+1 = (9 x 120 + 101) / 10 = 118.1
        out = _walk([(101, 103, 99, 101)], fill=100.0, stop=90.0, before=before, arm="trail10_only")
        assert out["status"] == "trailed" and out["sessions_held"] == 1
        assert out["events"] == [(1, "trail", 101.0, 1.0)]
        assert out["realized_r"] == pytest.approx((101 - 100) / 10.0)
        # without the pre-entry closes there is no SMA10 until session 10 (the #548 defect)
        blind = _walk([(101, 103, 99, 101)], fill=100.0, stop=90.0, before=[], arm="trail10_only")
        assert blind["status"] == "degraded" and blind["events"][-1][:2] == (1, "mark")

    def test_trail_needs_a_close_strictly_below_the_sma(self):
        # (a no-partial arm: on partial arms the trail waits for the partial, see below)
        # SMA10 at j=1 = (9 x 100 + 100) / 10 = 100.0; a close of exactly 100.0 does not trail
        out = _walk([(100, 101, 99, 100.0)], fill=100.0, stop=90.0, arm="trail10_only")
        assert out["status"] == "degraded"
        out2 = _walk([(100, 101, 99, 99.99)], fill=100.0, stop=90.0, arm="trail10_only")
        assert out2["status"] == "trailed"

    def test_the_stop_is_checked_before_the_trail_in_a_session(self):
        before = [120.0] * 30
        out = _walk([(101, 103, 89, 101)], fill=100.0, stop=90.0, before=before)
        assert out["status"] == "stopped" and out["events"] == [(1, "stop", 90.0, 1.0)]

    def test_gap_down_through_the_stop_exits_at_the_open_worse_than_minus_1r(self):
        rows = [(101, 102, 100, 101), (90, 92, 88, 91)]
        out = _walk(rows)
        assert out["status"] == "stopped" and out["sessions_held"] == 2
        assert out["events"] == [(2, "stop_gap", 90.0, 1.0)]
        assert out["realized_r"] == pytest.approx((90 - 100) / 5.0)       # -2R
        assert out["pnl_adr"] == pytest.approx((90 - 100) / (100 * ADR))

    def test_open_equal_to_the_stop_exits_at_the_open_price(self):
        out = _walk([(101, 102, 100, 101), (95, 96, 94, 95)])
        assert out["events"] == [(2, "stop", 95.0, 1.0)] and out["realized_r"] == pytest.approx(-1.0)

    def test_gap_down_through_the_breakeven_stop_after_the_partial(self):
        rows = [(101, 103, 99, 102), (102, 104, 100, 103), (103, 106, 101, 105),
                (98, 99, 96, 97)]                 # j=4 opens under breakeven 100
        out = _walk(rows)
        assert out["events"][-1] == (4, "stop_gap", 98.0, pytest.approx(2 / 3))
        assert out["realized_r"] == pytest.approx(((105 - 100) / 3 + (98 - 100) * 2 / 3) / 5.0)

    def test_censored_at_the_horizon_and_degraded_when_fwd_ends(self):
        # trail10_only on a steady climber: close_j = 100 + 0.5 j, never below its SMA10
        for n_fwd, status in ((25, "censored"), (20, "censored"), (19, "degraded")):
            out = _walk(_drift_rows(n_fwd), arm="trail10_only", horizon=20)
            assert out["status"] == status, (n_fwd, out["status"])
            held = 20 if status == "censored" else 19
            assert out["sessions_held"] == held
            mark = 100.0 + 0.5 * held
            assert out["events"] == [(held, "mark", mark, 1.0)]
            assert out["realized_r"] == pytest.approx((mark - 100.0) / 5.0)

    def test_default_horizon_is_120_sessions(self):
        out = _walk(_drift_rows(130), arm="trail10_only")
        assert out["status"] == "censored" and out["sessions_held"] == 120 == cb.EXIT_HORIZON
        assert out["events"][-1][2] == pytest.approx(100.0 + 0.5 * 120)

    def test_a_stop_on_the_horizon_session_is_a_stop_not_censored(self):
        rows = _drift_rows(19) + [(100, 100.5, 94, 99)]                # session 20 breaks the stop
        out = _walk(rows, arm="trail10_only", horizon=20)
        assert out["status"] == "stopped" and out["sessions_held"] == 20

    def test_no_forward_bars_marks_the_remainder_at_es_close_and_stays_degraded(self):
        # the night an entry fills: no E+1 yet. E closed at 102.0 -> +2 on a 5-point risk = 0.4R,
        # NOT a phantom 0R. Still "degraded" (sessions_held 0) so the runner can exclude it.
        empty = _fwd([(1, 1, 1, 1)]).slice(0, 0)
        for arm in ("p33_s3_t10", "trail10_only", "fixed_3r_12"):
            out = cb.walk_exit(fill=100.0, stop=95.0, closes_before=[99.0, 100.0, 102.0], fwd=empty,
                               arm=cb.ARMS[arm], adr20=0.04)
            assert out["status"] == "degraded" and out["sessions_held"] == 0, arm
            assert out["events"] == [(0, "mark", 102.0, 1.0)], arm
            assert out["realized_r"] == pytest.approx(0.4), arm
            assert out["pnl_adr"] == pytest.approx(2.0 / (100.0 * 0.04)), arm

    def test_no_forward_bars_and_no_closes_books_nothing(self):
        # with no close anywhere there is nothing to mark against; the status still says so
        out = cb.walk_exit(fill=100.0, stop=95.0, closes_before=[], fwd=_fwd([(1, 1, 1, 1)]).slice(0, 0),
                           arm=cb.ARMS["p33_s3_t10"], adr20=ADR)
        assert out["status"] == "degraded" and out["events"] == [] and out["realized_r"] == 0.0
        assert out["sessions_held"] == 0

    def test_closes_before_must_end_at_E_an_off_by_one_series_flips_the_trail(self):
        # (a no-partial arm: on partial arms the trail waits for the partial, see below)
        # The contract the module cannot check: closes_before[-1] is E's close. True series ends
        # [100 x 9, 110(E)]; SMA10 on E+1 (close 101) = (8 x 100 + 110 + 101) / 10 = 101.1 -> 101 trails.
        # Hand the walker the series ending E-1 and SMA10 = (9 x 100 + 101) / 10 = 100.1 -> no trail.
        # The P2 runner therefore asserts closes_before[-1] == bars.c[E] before every call.
        row = [(101.0, 102.0, 100.5, 101.0)]
        right = _walk(row, fill=100.0, stop=90.0, before=[100.0] * 9 + [110.0], arm="trail10_only")
        assert right["status"] == "trailed" and right["events"] == [(1, "trail", 101.0, 1.0)]
        wrong = _walk(row, fill=100.0, stop=90.0, before=[100.0] * 9, arm="trail10_only")
        assert wrong["status"] == "degraded" and wrong["events"] == [(1, "mark", 101.0, 1.0)]

    def test_trail_waits_for_the_partial_on_partial_arms(self):
        # The article's sequence: sell 1/3 after 3-5 days, THEN trail the rest. Day-1 close 104 is
        # under SMA10 = (101..108 + 110 + 104) / 10 = 1050 / 10 = 105.0, but the primary arm holds
        # (low 103.5 > stop 103) and reaches the j=3 partial; the "_early" sensitivity arm trails
        # out at 104 = -0.8R.
        before = [float(x) for x in range(100, 109)] + [110.0]
        rows = [(109.0, 109.5, 103.5, 104.0), (104.5, 106.0, 104.0, 105.5),
                (105.5, 107.0, 105.0, 106.0), (106.0, 107.5, 105.5, 107.0)]
        out = _walk(rows, fill=108.0, stop=103.0, before=before)
        assert out["events"][0][:3] == (3, "partial", 106.0)
        assert out["events"][0][3] == pytest.approx(1 / 3)
        early = _walk(rows[:1], arm="p33_s3_t10_early", fill=108.0, stop=103.0, before=before)
        assert early["status"] == "trailed" and early["events"] == [(1, "trail", 104.0, 1.0)]
        assert early["realized_r"] == pytest.approx((104.0 - 108.0) / 5.0)       # -0.8R, no partial

    def test_no_partial_arm_trails_from_session_one(self):
        before = [float(x) for x in range(100, 109)] + [110.0]
        out = _walk([(109.0, 109.5, 103.5, 104.0)], arm="trail10_only", fill=108.0, stop=103.0,
                    before=before)
        assert out["status"] == "trailed" and out["events"] == [(1, "trail", 104.0, 1.0)]

    def test_p50_s5_t20_partial_and_mark(self):
        # close_j = 100 + j, lows 0.5 under: never near the 95 stop nor the 100 breakeven after j=5
        rows = [(100 + j - 0.3, 100 + j + 0.4, 100 + j - 0.5, 100.0 + j) for j in range(1, 11)]
        out = _walk(rows, arm="p50_s5_t20", horizon=8)
        assert out["status"] == "censored" and out["sessions_held"] == 8
        assert out["events"] == [(5, "partial", 105.0, 0.5), (8, "mark", 108.0, 0.5)]
        assert out["realized_r"] == pytest.approx((0.5 * 5 + 0.5 * 8) / 5.0)       # 1.3

    def test_trail_after_the_partial_exits_only_the_remainder(self):
        # partial 1/2 at the close of j=5 (105); j=6 closes at 96, under SMA20 (~101) but above the
        # breakeven-rested stop's reach? low 96 < 100 -> the stop fires first (stop before trail)
        rows = [(100 + j - 0.3, 100 + j + 0.4, 100 + j - 0.5, 100.0 + j) for j in range(1, 6)]
        rows += [(104, 104.5, 96, 96)]
        out = _walk(rows, arm="p50_s5_t20")
        assert out["events"][-1] == (6, "stop", 100.0, 0.5)
        # a close under the SMA with the low still above breakeven trails the remainder at the close
        before = [100.0] * 30
        rows2 = [(100 + j - 0.3, 100 + j + 0.4, 100 + j - 0.5, 100.0 + j) for j in range(1, 6)]
        rows2 += [(102, 103, 100.6, 100.7)]       # close 100.7 < SMA20(6) = (14 x 100 + 101..105 + 100.7)/20 = 100.8
        out2 = _walk(rows2, arm="p50_s5_t20", before=before)
        assert out2["events"][-1] == (6, "trail", 100.7, 0.5)
        assert out2["status"] == "trailed"

    def test_bad_inputs(self):
        with pytest.raises(ValueError):
            _walk([(101, 102, 100, 101)], fill=100.0, stop=100.0)
        with pytest.raises(ValueError):
            cb.walk_exit(fill=100.0, stop=95.0, closes_before=BEFORE, fwd=_fwd([(1, 1, 1, 1)]),
                         arm=cb.ARMS["trail10_only"], adr20=0.0)


class TestFixedExit:
    def test_bar_touching_both_target_and_stop_books_the_stop(self):
        out = _walk([(100, 101, 99, 100), (100, 116, 94, 100)], arm="fixed_3r_12")
        assert out["status"] == "stopped" and out["events"] == [(2, "stop", 95.0, 1.0)]
        assert out["realized_r"] == pytest.approx(-1.0)

    def test_target_is_fill_plus_3r(self):
        out = _walk([(100, 101, 99, 100), (101, 103, 99, 102), (104, 116, 101, 110)], arm="fixed_3r_12")
        assert out["status"] == "target" and out["sessions_held"] == 3
        assert out["events"] == [(3, "target", 115.0, 1.0)]
        assert out["realized_r"] == pytest.approx(3.0)
        assert out["pnl_adr"] == pytest.approx(15.0 / (100.0 * ADR))

    def test_gap_over_the_target_fills_at_the_target_not_the_open(self):
        out = _walk([(120, 121, 119, 120)], arm="fixed_3r_12")
        assert out["realized_r"] == pytest.approx(3.0) and out["events"][0][2] == 115.0

    def test_gap_down_through_the_stop_exits_at_the_open(self):
        out = _walk([(90, 91, 88, 89)], arm="fixed_3r_12")
        assert out["status"] == "stopped" and out["events"] == [(1, "stop_gap", 90.0, 1.0)]
        assert out["realized_r"] == pytest.approx(-2.0)

    def test_time_exit_at_12_and_degraded_before(self):
        rows = [(100, 102, 99, 100 + 0.4 * j) for j in range(1, 13)]
        out = _walk(rows, arm="fixed_3r_12")
        assert out["status"] == "time_exit" and out["sessions_held"] == 12
        assert out["events"] == [(12, "mark", pytest.approx(104.8), 1.0)]
        assert out["realized_r"] == pytest.approx(4.8 / 5.0)
        short = _walk(rows[:11], arm="fixed_3r_12")
        assert short["status"] == "degraded" and short["sessions_held"] == 11
        assert short["events"] == [(11, "mark", pytest.approx(104.4), 1.0)]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Data shapes and purity
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestShapesAndPurity:
    def test_daily_bars_from_rows_takes_db_rows_to_bars_output(self):
        from agents.market_intelligence.anticipation import db_rows_to_bars
        db = [{"trade_date": "2026-09-14", "open_price": 10, "high_price": 11, "low_price": 9.5,
               "close": 10.5, "volume": 1000},
              {"trade_date": dt.date(2026, 9, 15), "open_price": None, "high_price": 11.5,
               "low_price": 10.0, "close": 11.0, "volume": None}]
        b = cb.daily_bars_from_rows(db_rows_to_bars(db))
        assert b.dates == [dt.date(2026, 9, 14), dt.date(2026, 9, 15)]
        assert list(b.c) == [10.5, 11.0] and list(b.o) == [10.0, 11.0] and list(b.v) == [1000.0, 0.0]

    def test_daily_bars_validation(self):
        d = _weekdays(3)
        with pytest.raises(ValueError):
            cb.daily_bars_from_arrays(d, [1, 2], [1, 2, 3], [1, 2, 3], [1, 2, 3], [1, 2, 3])
        with pytest.raises(ValueError):
            cb.daily_bars_from_arrays([d[1], d[0], d[2]], [1] * 3, [1] * 3, [1] * 3, [1] * 3, [1] * 3)
        with pytest.raises(ValueError):
            cb.daily_bars_from_arrays(d, [1, float("nan"), 1], [1] * 3, [1] * 3, [1] * 3, [1] * 3)

    def test_slice(self):
        b = Synth().bars()
        s = b.slice(5, 9)
        assert len(s) == 4 and s.dates == b.dates[5:9] and list(s.c) == list(b.c[5:9])

    def test_importing_the_module_loads_no_database_or_http_client(self):
        code = ("import sys; import agents.market_intelligence.consolidation_breakout as m; "
                "bad=[x for x in ('asyncpg','httpx','requests','aiohttp','pandas','pytz','alpaca') "
                "if x in sys.modules]; print(bad); sys.exit(1 if bad else 0)")
        p = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
        assert p.returncode == 0, p.stdout + p.stderr
