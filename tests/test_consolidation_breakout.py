"""#702 P1 — tests for agents/market_intelligence/consolidation_breakout.py (the pure core of the
Consolidation Breakout backtest + shadow).

Every expected number is derived here from the bars it came from, never from the function under
test: the MRNA canary hard-codes the fixture's own prices with the arithmetic beside them, and the
synthetic cases are built so each gate fails ALONE (a control that passes sits next to every
mutation that does not).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
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
        self.v = [2e6] * n                                    # flat volume; tests raise single bars
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
        return cb.daily_bars_from_arrays(_weekdays(self.n), self.o, self.h, self.l, self.c, self.v)

    def watch(self):
        return cb.evaluate_watch(self.bars(), self.i)

    def explain(self):
        return cb.explain_watch(self.bars(), self.i)


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
        # and (a fact about MRNA, no longer a gate) the previous-day pivots all sit under the pole high
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

    def test_a_wick_over_the_pole_high_does_not_end_the_base_only_a_close_does(self):
        # #702 P1b change 1 (was: "no new high since P"). The shipped HTF `_flag_resolved_by` rule:
        # price has LEFT the base only once some bar CLOSES above high(P); a wick over it is not an exit.
        s = Synth()
        assert s.watch() is not None
        s.h[s.i - 3] = s.top * 1.01                       # a wick: close stays ~15, P stays, base stands
        f = s.watch()
        assert f is not None and f["pole_idx"] == s.P
        assert f["pivot_k5"] == s.top * 1.01              # and the wick IS the resistance level
        s2 = Synth()
        s2.c[s2.i - 3], s2.o[s2.i - 3] = s2.top * 1.001, s2.top * 1.001
        s2.h[s2.i - 3] = s2.top * 1.01                    # now it CLOSED over the top
        assert s2.explain() == (None, "close_above_pole_high")
        s3 = Synth()
        s3.c[s3.i - 3], s3.o[s3.i - 3] = s3.top, s3.top   # a close EXACTLY at the pole high: strict `>`
        s3.h[s3.i - 3] = s3.top * 1.01
        assert s3.watch() is not None

    def test_a_later_wick_over_an_unresolved_top_does_not_become_the_pole(self):
        # #592 (mirrored in `_pole_top`): a higher HIGH 12 sessions back, with no CLOSE above the
        # top since the top, is a wick over the base, not a new top - P stays.
        s = Synth()
        s.h[s.i - 12] = s.top * 1.01
        f = s.watch()
        assert f is not None and f["pole_idx"] == s.P

    def test_a_close_above_the_top_lets_a_later_high_re_anchor_the_pole(self):
        s = Synth()
        s.h[s.i - 12] = s.top * 1.02
        s.c[s.i - 12] = s.top * 1.01                      # the close resolves the old top
        f, gate = cb.explain_watch(s.bars(), s.i)
        assert gate != "close_above_pole_high"            # the new top is P, so it is not "after P"
        assert f is not None and f["pole_idx"] == s.i - 12 and f["base_len"] == 12

    def test_pole_top_walk_matches_the_592_rule(self):
        h = np.array([10.0, 12.0, 12.5, 12.4, 12.3, 12.2, 12.6, 12.1])   # 12.6 at t=6: a wick
        c = np.array([10.0, 11.9, 12.4, 12.2, 12.1, 12.0, 12.3, 12.0])   # no close > 12.5
        assert cb._pole_top(h, c, 0, 7) == 2              # t=6 is 3 bars after t=2: the base formed
        c2 = c.copy(); c2[4] = 12.55                      # a close above 12.5 resolves the top
        assert cb._pole_top(h, c2, 0, 7) == 6
        h3 = h.copy(); h3[4] = 12.7                       # 1 bar after the t=2 top (4-2-1 = 1 < 3):
        assert cb._pole_top(h3, c, 0, 7) == 4             # the pole is still extending -> it walks

    def test_pole_high_ties_resolve_to_the_latest_only_while_the_pole_extends(self):
        s = Synth()
        s.h[s.P - 2] = s.top                              # an equal high 2 sessions earlier: extending
        assert s.watch()["pole_idx"] == s.P
        s = Synth()
        s.h[s.P - 5] = s.top                              # 5 sessions earlier (P-(P-5)-1 = 4 >= 3) and the
        f = s.watch()                                     # ramp closes P-4..P (14.7..15.8) never exceed 16:
        assert f["pole_idx"] == s.P - 5 and f["base_len"] == 25   # the later equal high is a re-test

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
        s.v[s.i - 59] = 2e7        # 10 -> 30 is a 3x jump INSIDE the pole window: only on real volume is it a pole
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

    @pytest.mark.parametrize("flag", ["sma20_ok", "sma50_rising", "higher_lows", "tightening_ok", "retrace_ok"])
    def test_each_structure_flag_gates_c1_to_c7_but_not_c0(self, flag):
        flags = cb.cell_flags(_good_features(**{flag: False}), _ctx(spyqqq=True), k="k5")
        assert flags["C0"] is True
        assert not any(flags[c] for c in cb.CELLS[1:]), flags

    def test_c0_needs_the_chosen_pivot_to_exist_and_may_sit_over_the_pole_high(self):
        # #702 P1b change 1: the old `pivot <= pole_high` clause is gone — a wick over the pole top is a
        # real resistance level and the base survives it. Only a missing / non-positive pivot fails C0.
        f = _good_features()
        assert cb.cell_flags(f, _ctx(), k="full")["C0"] is True
        wick = dict(f, pivot_full=f["pole_high"] + 0.01)
        assert cb.cell_flags(wick, _ctx(), k="full")["C0"] is True
        for bad_pivot in (None, 0.0, -1.0):
            bad = dict(f, pivot_full=bad_pivot)
            flags = cb.cell_flags(bad, _ctx(), k="full")
            assert flags["C0"] is False and not any(flags[c] for c in cb.CELLS[1:]), bad_pivot
            assert cb.cell_flags(bad, _ctx(), k="k5")["C0"] is True      # other pivot unaffected

    def test_tl_c0_needs_a_down_sloping_line_that_night(self):
        f = _good_features()
        assert f["pivot_tl"] is not None and cb.cell_flags(f, _ctx(), k="tl")["C0"] is True
        none = dict(f, pivot_tl=None)
        flags = cb.cell_flags(none, _ctx(), k="tl")
        assert flags["C0"] is False and not any(flags[c] for c in cb.CELLS[1:])
        assert cb.cell_flags(none, _ctx(), k="k10")["C0"] is True             # the horizontal levels are unaffected

    def test_k_has_no_default_and_is_validated(self):
        f = _good_features()
        with pytest.raises(TypeError):
            cb.cell_flags(f, _ctx())                                  # type: ignore[call-arg]
        with pytest.raises(ValueError):
            cb.cell_flags(f, _ctx(), k="k7")
        with pytest.raises(ValueError):
            cb.breakout_key("ABC", f, "5")

    def test_no_watch_row_means_no_cells(self):
        assert cb.cell_flags(None, _ctx(), k="k5") == {c: False for c in cb.CELLS + cb.REPORT_CELLS}

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
    """`arm` is an ARMS name or an Arm instance."""
    a = arm if isinstance(arm, cb.Arm) else cb.ARMS[arm]
    return cb.walk_exit(fill=fill, stop=stop, closes_before=before, fwd=_fwd(rows), arm=a, adr20=ADR, **kw)


def _close(name):
    """The named arm with its trail filled at the SIGNAL CLOSE (the pre-#702-P1b behaviour): keeps
    every hand-derived trail signal in this file checkable on a single row, while the arms table
    itself now fills at the next open."""
    return dataclasses.replace(cb.ARMS[name], trail_fill="close")


def _drift_rows(n, step=0.5, start=100.0):
    """A steady climber: close = start + step*j, lows far above the stop, never trails."""
    return [(start + step * j - 0.2, start + step * j + 0.3, start + step * j - 0.4, start + step * j)
            for j in range(1, n + 1)]


class TestArms:
    def test_the_fifteen_arms(self):
        assert len(cb.ARMS) == 15
        assert cb.ARMS["p33_s3_t10_early"].trail_before_partial
        grid = [n for n in cb.ARMS if re.fullmatch(r"p\d+_s\d+_t\d+", n)]
        assert sorted(grid) == sorted(
            f"p{p}_s{s}_t{t}" for p in (33, 50) for s in (3, 5) for t in (10, 20))
        assert sorted(set(cb.ARMS) - set(grid)) == sorted([
            "p33_s3_t10_early", "p33_s3_t10_close", "p33_s3_t10_nobe", "p33_s3_t10_ifprofit",
            "trail10_only", "stop_only", "fixed_3r_12"])
        # EVERY arm fills a trail at the NEXT OPEN (his 09-29 execution ruling) except the one
        # sensitivity arm that fills at the signal close
        assert {n for n, a in cb.ARMS.items() if a.trail_fill == "close"} == {"p33_s3_t10_close"}
        assert all(a.trail_fill == "next_open" for n, a in cb.ARMS.items() if n != "p33_s3_t10_close")
        # only the nobe control drops the breakeven; only the ifprofit arm conditions the partial
        assert {n for n, a in cb.ARMS.items() if not a.breakeven} == {"p33_s3_t10_nobe"}
        assert {n for n, a in cb.ARMS.items() if a.partial_if_profit} == {"p33_s3_t10_ifprofit"}
        assert "trail10_only" in cb.ARMS and "fixed_3r_12" in cb.ARMS
        so = cb.ARMS["stop_only"]
        assert (so.kind, so.partial_frac, so.partial_session, so.trail_sma) == ("qm", 0.0, None, None)
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
        out = _walk([(101, 103, 99, 101)], fill=100.0, stop=90.0, before=before, arm=_close("trail10_only"))
        assert out["status"] == "trailed" and out["sessions_held"] == 1
        assert out["events"] == [(1, "trail", 101.0, 1.0)]
        assert out["realized_r"] == pytest.approx((101 - 100) / 10.0)
        # the arms table fills that same signal at the NEXT open: session 2 opens 100.5
        nxt = _walk([(101, 103, 99, 101), (100.5, 102, 100, 101.5)], fill=100.0, stop=90.0,
                    before=before, arm="trail10_only")
        assert nxt["status"] == "trailed" and nxt["sessions_held"] == 2
        assert nxt["events"] == [(2, "trail", 100.5, 1.0)]
        assert nxt["realized_r"] == pytest.approx((100.5 - 100) / 10.0)
        # without the pre-entry closes there is no SMA10 until session 10 (the #548 defect)
        blind = _walk([(101, 103, 99, 101)], fill=100.0, stop=90.0, before=[], arm="trail10_only")
        assert blind["status"] == "degraded" and blind["events"][-1][:2] == (1, "mark")

    def test_trail_needs_a_close_strictly_below_the_sma(self):
        # (a no-partial arm: on partial arms the trail waits for the partial, see below)
        # SMA10 at j=1 = (9 x 100 + 100) / 10 = 100.0; a close of exactly 100.0 does not trail
        out = _walk([(100, 101, 99, 100.0)], fill=100.0, stop=90.0, arm=_close("trail10_only"))
        assert out["status"] == "degraded"
        out2 = _walk([(100, 101, 99, 99.99)], fill=100.0, stop=90.0, arm=_close("trail10_only"))
        assert out2["status"] == "trailed"
        # the same two closes on the next-open arm (a second session exists): 100.0 never signals,
        # 99.99 signals on session 1 and sells session 2's open
        nxt_rows = [(100.0, 101, 99, 99.99), (99.8, 100, 99, 99.9)]
        assert _walk([(100, 101, 99, 100.0), (100.1, 101, 99, 100.1)], fill=100.0, stop=90.0,
                     arm="trail10_only")["status"] == "degraded"
        assert _walk(nxt_rows, fill=100.0, stop=90.0, arm="trail10_only")["events"] == [(2, "trail", 99.8, 1.0)]

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
        right = _walk(row, fill=100.0, stop=90.0, before=[100.0] * 9 + [110.0], arm=_close("trail10_only"))
        assert right["status"] == "trailed" and right["events"] == [(1, "trail", 101.0, 1.0)]
        wrong = _walk(row, fill=100.0, stop=90.0, before=[100.0] * 9, arm=_close("trail10_only"))
        assert wrong["status"] == "degraded" and wrong["events"] == [(1, "mark", 101.0, 1.0)]
        # and on the next-open arm the right series sells session 2's open, the wrong one never signals
        row2 = row + [(100.7, 101.0, 100.4, 100.9)]
        right2 = _walk(row2, fill=100.0, stop=90.0, before=[100.0] * 9 + [110.0], arm="trail10_only")
        assert right2["events"] == [(2, "trail", 100.7, 1.0)]
        wrong2 = _walk(row2, fill=100.0, stop=90.0, before=[100.0] * 9, arm="trail10_only")
        assert wrong2["status"] == "degraded"

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
        # the partial sold at 106, UNDER the 108 fill: the breakeven stop (108) sits above that close, so
        # the event is appended and session 4 (open 106) is taken out at the open by the resting stop
        assert out["events"][1] == (3, "be_above_close", 106.0, 0.0)
        assert out["events"][2][:3] == (4, "stop_gap", 106.0)
        early_close = _walk(rows[:1], arm=_close("p33_s3_t10_early"), fill=108.0, stop=103.0, before=before)
        assert early_close["status"] == "trailed" and early_close["events"] == [(1, "trail", 104.0, 1.0)]
        assert early_close["realized_r"] == pytest.approx((104.0 - 108.0) / 5.0)       # -0.8R, no partial
        early = _walk(rows[:2], arm="p33_s3_t10_early", fill=108.0, stop=103.0, before=before)
        assert early["events"] == [(2, "trail", 104.5, 1.0)]                            # session 2 opens 104.5
        assert early["realized_r"] == pytest.approx((104.5 - 108.0) / 5.0)

    def test_no_partial_arm_trails_from_session_one(self):
        before = [float(x) for x in range(100, 109)] + [110.0]
        out = _walk([(109.0, 109.5, 103.5, 104.0)], arm=_close("trail10_only"), fill=108.0, stop=103.0,
                    before=before)
        assert out["status"] == "trailed" and out["events"] == [(1, "trail", 104.0, 1.0)]
        nxt = _walk([(109.0, 109.5, 103.5, 104.0), (104.2, 105.0, 104.0, 104.5)], arm="trail10_only",
                    fill=108.0, stop=103.0, before=before)
        assert nxt["status"] == "trailed" and nxt["events"] == [(2, "trail", 104.2, 1.0)]

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
        out2 = _walk(rows2, arm=_close("p50_s5_t20"), before=before)
        assert out2["events"][-1] == (6, "trail", 100.7, 0.5)
        assert out2["status"] == "trailed"
        # next-open arm: the same signal sells the remaining half at session 7's open (100.9)
        out3 = _walk(rows2 + [(100.9, 101.5, 100.6, 101.0)], arm="p50_s5_t20", before=before)
        assert out3["events"][-1] == (7, "trail", 100.9, 0.5) and out3["status"] == "trailed"
        assert out3["sessions_held"] == 7
        assert out3["realized_r"] == pytest.approx((0.5 * 5 + 0.5 * 0.9) / 5.0)

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


class TestNextOpenTrail:
    """Change 7 — a trail signal on the CLOSE of session j sells the remainder at the OPEN of j+1."""

    BEFORE120 = [120.0] * 30                     # SMA10 ~ 118+: any close near 100 signals

    def _walk(self, rows, arm="trail10_only", fill=100.0, stop=90.0, **kw):
        return _walk(rows, arm=arm, fill=fill, stop=stop, before=self.BEFORE120, **kw)

    def test_the_pending_exit_fills_at_the_open_and_the_next_stop_check_never_books_twice(self):
        # session 1 closes 101 (< SMA10 118.1): signal. Session 2 opens 95, ABOVE the 90 stop, and trades
        # down to 80 through it. The remainder was already sold at the 95 open, so it books ONCE, at 95 —
        # not at the 90 stop (an order that ran the stop check first would book -1R here).
        out = self._walk([(101, 103, 99, 101), (95, 96, 80, 85)])
        assert out["events"] == [(2, "trail", 95.0, 1.0)]
        assert out["status"] == "trailed" and out["sessions_held"] == 2
        assert out["realized_r"] == pytest.approx((95.0 - 100.0) / 10.0)
        assert out["pnl_adr"] == pytest.approx(-5.0 / (100.0 * ADR))

    def test_a_gap_below_the_stop_still_books_once_at_the_open(self):
        out = self._walk([(101, 103, 99, 101), (85, 86, 80, 82)])
        assert out["events"] == [(2, "trail", 85.0, 1.0)]            # one event, at the open (-1.5R), kind "trail"
        assert out["realized_r"] == pytest.approx(-1.5)

    def test_a_signal_on_the_last_forward_bar_cannot_fill_and_stays_degraded(self):
        out = self._walk([(101, 103, 99, 101)])
        assert out["status"] == "degraded" and out["events"] == [(1, "mark", 101.0, 1.0)]
        assert out["sessions_held"] == 1

    def test_a_signal_the_session_before_the_stop_session_still_exits_at_the_trail_open(self):
        # the close-fill arm on the same rows exits on session 1 at the close; the stop on session 2 is moot
        rows = [(101, 103, 99, 101), (100.5, 101, 88, 95)]
        assert self._walk(rows, arm=_close("trail10_only"))["events"] == [(1, "trail", 101.0, 1.0)]
        assert self._walk(rows)["events"] == [(2, "trail", 100.5, 1.0)]

    def test_horizon_signal_is_censored_filled_at_the_next_open_when_there_is_one(self):
        # closes 101..104 stay above the rising SMA10, session 5 (the horizon) closes 99.5 under it
        before = [100.0] * 30
        rows = [(100.5, 101.5, 100.2, 101.0), (101.0, 102.5, 100.8, 102.0), (102.0, 103.5, 101.8, 103.0),
                (103.0, 104.5, 102.8, 104.0), (103.5, 104.0, 99.0, 99.5)]
        mark = _walk(rows, arm="trail10_only", stop=90.0, before=before, horizon=5)
        assert mark["status"] == "censored" and mark["events"] == [(5, "mark", 99.5, 1.0)]    # no session 6
        out = _walk(rows + [(98.8, 99.5, 98.0, 99.0)], arm="trail10_only", stop=90.0, before=before, horizon=5)
        assert out["status"] == "censored"
        assert out["events"] == [(6, "trail", 98.8, 1.0)] and out["sessions_held"] == 6
        assert out["realized_r"] == pytest.approx((98.8 - 100.0) / 10.0)
        # one session earlier (horizon 6 on the same 6 rows) the signal at 5 is an ordinary trail
        ordinary = _walk(rows + [(98.8, 99.5, 98.0, 99.0)], arm="trail10_only", stop=90.0, before=before, horizon=6)
        assert ordinary["status"] == "trailed" and ordinary["events"] == [(6, "trail", 98.8, 1.0)]

    def test_the_documented_forward_slice_is_long_enough_for_a_horizon_signal_to_fill(self):
        # `DailyBars.slice`'s docstring gives the forward-walk input as `bars.slice(<lo>, <hi>)` in E / horizon.
        # Evaluate THAT expression and walk it: a trail signal on the horizon session must fill at the next
        # open, which only exists if the documented slice carries horizon + 1 sessions. With exactly `horizon`
        # rows the branch is unreachable and the signal is marked at the close instead.
        import re as _re
        m = _re.search(r"bars\.slice\(([^)]*)\)", cb.DailyBars.slice.__doc__)
        assert m, "DailyBars.slice's docstring no longer shows the forward-walk slice"
        lo_src, hi_src = (x.strip() for x in m.group(1).split(","))
        E, horizon = 29, 5
        fwd_rows = [(100.5, 101.5, 100.2, 101.0), (101.0, 102.5, 100.8, 102.0), (102.0, 103.5, 101.8, 103.0),
                    (103.0, 104.5, 102.8, 104.0), (103.5, 104.0, 99.0, 99.5),      # session 5 = the horizon: trail signal
                    (98.8, 99.5, 98.0, 99.0), (98.0, 98.5, 97.0, 97.5)]            # the next open, then one spare row
        rows = [(100.0, 100.0, 100.0, 100.0)] * (E + 1) + fwd_rows
        o, h, l, c = zip(*rows)
        bars = cb.daily_bars_from_arrays(_weekdays(len(rows)), o, h, l, c, [1.0] * len(rows))
        env = {"__builtins__": {}}
        lo, hi = eval(lo_src, env, {"E": E, "horizon": horizon}), eval(hi_src, env, {"E": E, "horizon": horizon})
        assert (lo, hi) == (E + 1, E + 2 + horizon)
        fwd = bars.slice(lo, hi)
        assert len(fwd) == horizon + 1
        walk = dict(fill=100.0, stop=90.0, closes_before=bars.c[:E + 1], arm=cb.ARMS["trail10_only"],
                    adr20=ADR, horizon=horizon)
        out = cb.walk_exit(fwd=fwd, **walk)
        assert out["status"] == "censored" and out["events"] == [(6, "trail", 98.8, 1.0)]
        assert out["sessions_held"] == 6
        short = cb.walk_exit(fwd=bars.slice(E + 1, E + 1 + horizon), **walk)       # the OLD documented slice
        assert short["status"] == "censored" and short["events"] == [(5, "mark", 99.5, 1.0)]

    def test_partials_stay_at_the_session_close_whatever_the_trail_fill(self):
        # partial at the j=3 close (106); the j=4 trail signal sells the rest at j=5's open, the partial
        # price is untouched: 1/3 x (106 - 100) + 2/3 x (100.8 - 100) = 2 + 0.5333
        before = [100.0] * 30
        rows = [(101, 104.5, 100.5, 104.0), (104, 105.5, 103.5, 105.0), (105, 107, 104.5, 106.0),
                (105.5, 106, 100.5, 101.0), (100.8, 101.5, 100.2, 101.2)]
        out = _walk(rows, before=before)
        assert out["events"] == [(3, "partial", 106.0, pytest.approx(1 / 3)),
                                 (5, "trail", 100.8, pytest.approx(2 / 3))]
        assert out["realized_r"] == pytest.approx((6 / 3 + 0.8 * 2 / 3) / 5.0)
        assert out["sessions_held"] == 5 and out["status"] == "trailed"
        close = _walk(rows, arm="p33_s3_t10_close", before=before)
        assert close["events"] == [(3, "partial", 106.0, pytest.approx(1 / 3)),
                                   (4, "trail", 101.0, pytest.approx(2 / 3))]
        assert close["realized_r"] == pytest.approx((6 / 3 + 1.0 * 2 / 3) / 5.0)
        assert close["sessions_held"] == 4

    def test_arm_validates_its_trail_fill(self):
        with pytest.raises(ValueError):
            cb.Arm("x", "qm", 0.0, None, 10, trail_fill="tomorrow")
        with pytest.raises(ValueError):
            cb.Arm("x", "qm", 0.0, None, 10, partial_if_profit=True)      # needs a partial


class TestNewExitArms:
    """Change 7 — the four new arms."""

    BEFORE = [100.0] * 30

    def test_nobe_keeps_the_entry_stop_after_the_partial(self):
        # partial 1/3 at the j=3 close (106). Session 4 trades down to 98: under the BREAKEVEN stop (100) but
        # above the entry stop (95). Primary: stopped at 100. nobe: carries on; session 5 breaks the 95 stop.
        rows = [(101, 104.5, 100.5, 104.0), (104, 105.5, 103.5, 105.0), (105, 107, 104.5, 106.0),
                (104.0, 105.0, 98.0, 103.0), (103.0, 104.0, 94.0, 95.0)]
        prim = _walk(rows, before=self.BEFORE)
        assert prim["events"] == [(3, "partial", 106.0, pytest.approx(1 / 3)), (4, "stop", 100.0, pytest.approx(2 / 3))]
        assert prim["realized_r"] == pytest.approx((6 / 3 + 0.0) / 5.0)
        nobe = _walk(rows, arm="p33_s3_t10_nobe", before=self.BEFORE)
        assert nobe["events"] == [(3, "partial", 106.0, pytest.approx(1 / 3)), (5, "stop", 95.0, pytest.approx(2 / 3))]
        assert nobe["realized_r"] == pytest.approx((6 / 3 + (95 - 100) * 2 / 3) / 5.0)         # -0.2667R
        assert nobe["sessions_held"] == 5

    def test_nobe_never_emits_be_above_close(self):
        rows = [(99, 100, 98, 99), (99, 100, 97, 98), (98, 99, 96, 97), (97.5, 98.5, 96.5, 98.0)]
        out = _walk(rows, arm="p33_s3_t10_nobe", before=[90.0] * 30)
        assert [e[1] for e in out["events"]] == ["partial", "mark"]

    def test_be_above_close_marks_the_hidden_day4_time_stop(self):
        # the partial sells at 97, UNDER the 100 fill: the breakeven stop (100) sits above the close, so the
        # next session's open (97.5 <= 100) takes the rest out. The event lets the runner count those.
        rows = [(99, 100, 98, 99), (99, 100, 97, 98), (98, 99, 96, 97), (97.5, 98.5, 96.5, 98.0)]
        out = _walk(rows, before=[90.0] * 30)
        assert out["events"] == [(3, "partial", 97.0, pytest.approx(1 / 3)), (3, "be_above_close", 97.0, 0.0),
                                 (4, "stop_gap", 97.5, pytest.approx(2 / 3))]
        assert out["realized_r"] == pytest.approx(((97 - 100) / 3 + (97.5 - 100) * 2 / 3) / 5.0)
        # a partial AT a profit never emits it
        up = _walk([(101, 104.5, 100.5, 104.0), (104, 105.5, 103.5, 105.0), (105, 107, 104.5, 106.0)],
                   before=[90.0] * 30)
        assert all(e[1] != "be_above_close" for e in up["events"])
        # the breakeven stop equal to the close is NOT above it
        flat = _walk([(99, 101, 98, 100), (100, 101, 99, 100), (100, 101, 99, 100.0)], before=[90.0] * 30)
        assert all(e[1] != "be_above_close" for e in flat["events"])

    def test_ifprofit_takes_the_partial_only_on_a_profit_and_arms_the_trail_a_session_later(self):
        before = [120.0] * 30                     # SMA10 ~118: every close near 100 is under it
        # (a) the j=3 close (102) is ABOVE the fill: partial + breakeven. The PRIMARY trails on that same
        #     close (signal j=3 -> sells session 4's open 102); ifprofit holds the trail until session 4's
        #     close, then sells session 5's open.
        rows = [(100.5, 101.5, 99.5, 101.0), (101.0, 102.0, 100.5, 101.5), (101.5, 103.0, 101.0, 102.0),
                (102.0, 103.0, 100.5, 101.0), (100.8, 101.5, 100.2, 101.2)]
        prim = _walk(rows, before=before)
        assert prim["events"] == [(3, "partial", 102.0, pytest.approx(1 / 3)), (4, "trail", 102.0, pytest.approx(2 / 3))]
        ifp = _walk(rows, arm="p33_s3_t10_ifprofit", before=before)
        assert ifp["events"] == [(3, "partial", 102.0, pytest.approx(1 / 3)), (5, "trail", 100.8, pytest.approx(2 / 3))]
        assert ifp["realized_r"] == pytest.approx((2 / 3 + 0.8 * 2 / 3) / 5.0)
        # (b) the j=3 close (99) is under the fill: NO partial, NO breakeven (the entry stop 95 stays), the
        #     whole position rides on; the trail arms from session 4 and sells session 5's open
        rows_b = [(100.0, 101.0, 98.0, 99.5), (99.5, 100.0, 97.0, 98.0), (98.0, 99.5, 96.0, 99.0),
                  (98.5, 99.0, 96.5, 97.5), (97.0, 98.0, 96.0, 97.0)]
        ifp_b = _walk(rows_b, arm="p33_s3_t10_ifprofit", before=BEFORE)
        assert ifp_b["events"] == [(5, "trail", 97.0, 1.0)]
        assert ifp_b["realized_r"] == pytest.approx((97.0 - 100.0) / 5.0)
        prim_b = _walk(rows_b, before=BEFORE)                          # the primary DOES partial at 99 (a loss)
        assert prim_b["events"][0] == (3, "partial", 99.0, pytest.approx(1 / 3))
        assert prim_b["events"][1] == (3, "be_above_close", 99.0, 0.0)
        # exactly at the fill is not a profit
        rows_c = [(100.0, 101.0, 98.0, 99.5), (99.5, 100.0, 97.0, 98.0), (98.0, 100.5, 96.0, 100.0)]
        assert all(e[1] != "partial" for e in _walk(rows_c, arm="p33_s3_t10_ifprofit", before=[90.0] * 30)["events"])

    def test_stop_only_holds_the_entry_stop_to_the_horizon_and_marks(self):
        before = [120.0] * 30                      # the trail arms would all fire immediately
        rows = [(101, 102, 100, 101 - 0.1 * j) for j in range(1, 11)]
        out = _walk(rows, arm="stop_only", before=before, horizon=8)
        assert out["status"] == "censored" and out["sessions_held"] == 8
        assert out["events"] == [(8, "mark", pytest.approx(101 - 0.8), 1.0)]
        assert out["realized_r"] == pytest.approx((101 - 0.8 - 100.0) / 5.0)
        short = _walk(rows[:5], arm="stop_only", before=before, horizon=8)
        assert short["status"] == "degraded" and short["events"] == [(5, "mark", pytest.approx(100.5), 1.0)]
        # the entry stop still works: session 5 breaks 95
        hit = _walk(rows[:4] + [(100, 101, 94.5, 95.0)], arm="stop_only", before=before)
        assert hit["status"] == "stopped" and hit["events"] == [(5, "stop", 95.0, 1.0)]
        assert hit["realized_r"] == pytest.approx(-1.0)

    def test_close_arm_is_the_primary_with_the_signal_close_fill(self):
        a, p = cb.ARMS["p33_s3_t10_close"], cb.ARMS["p33_s3_t10"]
        assert dataclasses.replace(a, name=p.name, trail_fill=p.trail_fill) == p
        assert cb.PRIMARY_ARM == "p33_s3_t10" and p.trail_fill == "next_open"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6b. #702 P1b — base anchor, fresh pin, retrace, artifact guard, explain_watch, telemetry
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _fixture(ticker: str):
    """(bars, {iso date: index}) for one ticker of tests/fixtures/htf_labelled_bars.psv."""
    rows = [ln.rstrip("\n").split("|") for ln in FIXTURE.read_text().splitlines()
            if ln.startswith(ticker + "|")]
    cols = [[float(r[k]) for r in rows] for k in (2, 3, 4, 5, 6)]
    bars = cb.daily_bars_from_arrays([dt.date.fromisoformat(r[1]) for r in rows], *cols)
    return bars, {r[1]: k for k, r in enumerate(rows)}


def _welded_tail(s: Synth, n: int = 5) -> None:
    """The last `n` sessions as 1% daily ranges: the 5-session median range (1%) clears the mature
    deal-pin arm (0.5%) while the 5-session band (~1.6%) stays under the fresh-pin 2.5% ceiling —
    so a fresh-pin verdict can only come from the VOLUME axis. (`n=10` also welds the sessions the
    sticky carry re-reads as-of 1..5 sessions ago.)"""
    for k in range(s.i - n + 1, s.i + 1):
        s.h[k], s.l[k] = s.c[k] * 1.005, s.c[k] * 0.995


class TestBaseAnchor:
    """Change 1 — the base survives a wick over the pole high; only a CLOSE ends it."""

    def test_base_resolved_equals_flag_detectors_flag_resolved_by(self):
        from agents.market_intelligence.flag_detector import _flag_resolved_by
        cases = {
            "all closes under": [99.0, 98.0, 99.5, 97.0, 96.0, 98.0, 99.0, 99.9, 98.5, 97.5, 99.0, 98.0],
            "a close EXACTLY at the pole high": [99.0, 98.0, 100.0, 97.0, 96.0, 98.0, 99.0, 99.9, 98.5, 97.5, 99.0, 98.0],
            "first base close over": [100.01, 98.0, 99.5, 97.0, 96.0, 98.0, 99.0, 99.9, 98.5, 97.5, 99.0, 98.0],
            "a middle close over": [99.0, 98.0, 99.5, 97.0, 96.0, 101.0, 99.0, 99.9, 98.5, 97.5, 99.0, 98.0],
            "last close over": [99.0, 98.0, 99.5, 97.0, 96.0, 98.0, 99.0, 99.9, 98.5, 97.5, 99.0, 100.01],
        }
        for name, base_closes in cases.items():
            c = np.array([100.0] + base_closes)              # P = 0, i = 12 (11+ base sessions)
            rows = [{"close": float(x)} for x in c]
            real = _flag_resolved_by(rows, 0, 100.0, len(c) - 1)
            assert cb._base_resolved(c, 0, len(c) - 1, 100.0) is real, name
        # strictness, spelled out: equal does not resolve, a cent over does
        assert cb._base_resolved(np.array([100.0, 100.0] + [90.0] * 11), 0, 12, 100.0) is False
        assert cb._base_resolved(np.array([100.0, 100.01] + [90.0] * 11), 0, 12, 100.0) is True

    def test_gh_2026_06_15_hand_check_two_wicks_over_the_pole_high_leave_the_base_standing(self):
        # HAND-DERIVED from tests/fixtures/htf_labelled_bars.psv (GH rows). P = 2026-05-29, high 133.9699.
        # Closes 06-01..06-15, read straight off the rows:
        closes = [129.14, 130.17, 127.03, 133.06, 125.61, 124.89, 130.12, 130.7, 130.9, 131.62, 129.82]
        # Highs over the same eleven sessions; TWO of them are wicks over 133.9699 (06-04 and 06-15):
        highs = [130.44, 131.88, 129.87, 134.28, 133.335, 132.0, 130.36, 133.31, 133.37, 133.66, 134.998]
        bars, idx = _fixture("GH")
        P, i = idx["2026-05-29"], idx["2026-06-15"]
        assert i - P == 11 and bars.h[P] == 133.9699
        assert list(bars.c[P + 1:i + 1]) == closes and list(bars.h[P + 1:i + 1]) == highs
        assert max(closes) == 133.06 < 133.9699                  # no close ever got over the top
        assert max(highs) == 134.998 > 133.9699                  # but the OLD gate (max high > high(P)) would reject
        assert [h for h in highs if h > 133.9699] == [134.28, 134.998]
        # P really is the highest high of [i-45, i-10] (independent argmax, latest tie)
        win = bars.h[i - 45:i - 10 + 1]
        assert win.max() == 133.9699 and i - 45 + int(np.flatnonzero(win == win.max())[-1]) == P
        f, gate = cb.explain_watch(bars, i)
        assert gate is None, gate
        assert f["pole_date"] == "2026-05-29" and f["pole_high"] == 133.9699 and f["base_len"] == 11
        assert f["pole_low"] == 74.55 and f["pole_low_date"] == "2026-04-10"
        assert f["prior_move"] == pytest.approx(133.9699 / 74.55 - 1.0)
        assert f["pivot_k5"] == 134.998 and f["pivot_k5_date"] == "2026-06-15"   # the wick IS the resistance
        # The night a CLOSE finally clears the top (06-24 closes 136.96) ends the base
        j = idx["2026-06-24"]
        assert bars.c[j] == 136.96 > 133.9699
        assert cb.explain_watch(bars, j) == (None, "close_above_pole_high")

    def test_gh_passes_c0_on_the_june_nights_it_failed_before(self):
        # the same nights through the committed P1 gate (a wick over the pole high rejected) were all
        # None; they are now C0 nights (06-11..06-23, eight sessions)
        bars, idx = _fixture("GH")
        for d in ("2026-06-11", "2026-06-12", "2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18",
                  "2026-06-22", "2026-06-23"):
            assert cb.evaluate_watch(bars, idx[d]) is not None, d
            P = cb.evaluate_watch(bars, idx[d])["pole_idx"]
            assert bars.h[P + 1:idx[d] + 1].max() > bars.h[P], d       # the old gate would have said None


class TestFreshPinGate:
    """Change 2 — `flag_detector._evaluate_fresh_pin` (#502) inside C0."""

    def test_the_rows_fed_are_the_40_prod_rows_newest_first(self):
        s = Synth()
        b = s.bars()
        rows = cb._fresh_pin_rows(b, s.i)
        assert len(rows) == 40
        assert rows[0] == {"high_price": b.h[s.i], "low_price": b.l[s.i], "close": b.c[s.i], "volume": b.v[s.i]}
        assert rows[39]["close"] == b.c[s.i - 39] and rows[1]["close"] == b.c[s.i - 1]

    def test_control_welded_tail_flat_volume_passes_and_records_the_numbers(self):
        s = Synth()
        _welded_tail(s)
        f = s.watch()
        assert f is not None and f["fresh_pin"] is False
        assert f["fresh_pin_spike_x"] == pytest.approx(1.0)       # flat 2e6 volume: max event / mean baseline
        c5 = np.array(s.c[s.i - 4:s.i + 1])
        band = (max(s.h[s.i - 4:s.i + 1]) - min(s.l[s.i - 4:s.i + 1])) / c5.mean()
        assert f["fresh_pin_band_pct"] == pytest.approx(band) and band < 0.025

    def test_welded_band_plus_a_10x_volume_event_in_the_last_10_sessions_rejects(self):
        s = Synth()
        _welded_tail(s)
        s.v[s.i - 5] = 2e7                                    # 10x the 2e6 baseline, inside the event window
        assert s.explain() == (None, "fresh_pin")

    def test_spike_threshold_is_5x_inclusive(self):
        for vol, want in ((8e6, None), (1e7, "fresh_pin")):    # 4x passes, 5.0x fires (>=)
            s = Synth()
            _welded_tail(s)
            s.v[s.i - 5] = vol
            assert s.explain()[1] == want, vol

    def test_either_axis_alone_does_not_reject(self):
        s = Synth()                                           # default tail: 2% ranges, band ~2.6% > 2.5%
        s.v[s.i - 5] = 2e7
        assert s.watch() is not None                           # volume spike but not welded
        s2 = Synth()
        _welded_tail(s2)
        assert s2.watch() is not None                          # welded but no volume event

    def test_event_window_is_the_last_10_sessions_then_the_sticky_carry_holds_it_to_14_back(self):
        # i-9 is the oldest session in today's event window; the spike at i-10 only counts through the
        # STICKY carry (re-run as-of 1..5 sessions ago while today's band is still <= 2.5%): i-14 is the
        # farthest back that is still carried, i-15 is not.
        for back, want in ((9, "fresh_pin"), (10, "fresh_pin"), (14, "fresh_pin"), (15, None)):
            s = Synth()
            _welded_tail(s, 10)
            s.v[s.i - back] = 2e7
            assert s.explain()[1] == want, back
        # the carry needs today's band to still be welded: a wide tail releases it
        s = Synth()
        s.v[s.i - 10] = 2e7
        assert s.watch() is not None

    def test_a_mature_pin_is_reported_before_the_fresh_one(self):
        s = Synth()
        for k in range(s.i - 4, s.i + 1):                      # 0.2% ranges: the mature MEDIAN arm fires
            s.h[k], s.l[k] = s.c[k] * 1.001, s.c[k] * 0.999
        s.v[s.i - 5] = 2e7                                     # ... and so would the fresh one
        assert s.explain() == (None, "deal_pin_median")

    def test_atai_0903_0904_hand_check_the_fresh_layer_does_NOT_reject_it(self):
        # RECORDED GAP, hand-derived from tests/fixtures/htf_labelled_bars.psv (ATAI rows). The cash deal
        # day is 2026-07-16 (165.6M shares), 35 sessions before 2026-09-03: far outside the 10-session event
        # window, and INSIDE the 30-session baseline window (i-39 .. i-10), where it inflates the mean.
        # 09-03's own print (17.48M) is therefore only ~1.1x that baseline (1.65x with the deal day removed;
        # a longer event window alone would not fire either). So the layer that caught ATAI on 07-23 .. 08-05
        # (the `fired` list below) does not fire here and ATAI is still a C0 night.
        # (What stands between ATAI and a C1 trade: higher_lows is False on both nights, asserted below,
        # and P2's STEP 0 deal check on every C1 trade >= 5R.)
        bars, idx = _fixture("ATAI")
        i = idx["2026-09-03"]
        hi5, lo5 = [7.37, 7.38, 7.385, 7.36, 7.43], [7.29, 7.29, 7.34, 7.32, 7.32]   # 08-28 .. 09-03
        close5 = [7.29, 7.34, 7.34, 7.35, 7.34]
        assert bars.v[i] == 17475711
        assert list(bars.h[i - 4:i + 1]) == hi5 and list(bars.l[i - 4:i + 1]) == lo5
        assert list(bars.c[i - 4:i + 1]) == close5
        band = (max(hi5) - min(lo5)) / (sum(close5) / 5)                # 0.14 / 7.332 = 1.91% <= 2.5%: welded
        assert band == pytest.approx(0.019094, abs=1e-6)
        baseline = bars.v[i - 39:i - 9]                                  # the 30 sessions i-39 .. i-10
        event_max = bars.v[i - 9:i + 1].max()                            # the last 10 sessions i-9 .. i
        assert event_max == 17475711
        spike = event_max / baseline.mean()                              # independent of the module
        assert spike == pytest.approx(1.1102, abs=1e-3) and spike < 5.0  # the volume axis fails
        deal = idx["2026-07-16"]                                         # the deal day sits in the baseline window
        assert (i - deal, bars.v[deal]) == (35, 165634412)
        assert i - 39 <= deal <= i - 10
        without = np.delete(baseline, deal - (i - 39))                   # baseline with the deal day removed
        assert len(without) == 29 and event_max / without.mean() == pytest.approx(1.6529, abs=1e-3)
        f, gate = cb.explain_watch(bars, i)
        assert gate is None and f["fresh_pin"] is False
        assert f["fresh_pin_band_pct"] == pytest.approx(band) and f["fresh_pin_spike_x"] == pytest.approx(spike)
        assert f["higher_lows"] is False and f["retrace_ok"] is True
        # 09-04: the same story one session later
        j = idx["2026-09-04"]
        assert cb.explain_watch(bars, j)[1] is None
        assert cb.evaluate_watch(bars, j)["higher_lows"] is False
        # and on the nights the layer DID fire (07-23 .. 08-05) another gate reports first, so the
        # first-failing-gate name never reads "fresh_pin" for ATAI in the corpus
        from agents.market_intelligence.flag_detector import _evaluate_fresh_pin
        fired = [d for d, k in idx.items()
                 if k >= 129 and _evaluate_fresh_pin(cb._fresh_pin_rows(bars, k))["is_fresh_pin"]]
        assert fired == ["2026-07-23", "2026-07-24", "2026-07-27", "2026-07-28", "2026-07-29",
                         "2026-07-30", "2026-07-31", "2026-08-03", "2026-08-04", "2026-08-05"]
        assert all(cb.explain_watch(bars, idx[d])[1] in ("close_above_pole_high", "deal_pin_median") for d in fired)


class TestRetrace:
    """Change 3 — the pole retrace as a C1 term, with two REPORTED-only cells."""

    def test_retrace_formula_on_the_synth_base(self):
        s = Synth()
        f = s.watch()
        base_low = min(s.l[s.P + 1:s.i + 1])                   # 14.0052: the first base sessions' lows
        assert f["base_low"] == pytest.approx(base_low) and base_low == pytest.approx(0.94 * 16 * 0.97 * 0.96)
        assert f["retrace"] == pytest.approx((16.0 - base_low) / (16.0 - 9.9))
        assert f["retrace_ok"] is True and f["retrace"] < 0.5

    def test_the_hold_limit_is_the_signed_family_a_constant(self):
        from agents.market_intelligence.anticipation import COIL_HOLD_LIMIT
        assert COIL_HOLD_LIMIT == 0.50 and cb.COIL_HOLD_LIMIT is COIL_HOLD_LIMIT

    def test_retrace_ok_boundary_at_one_half_of_the_pole(self):
        # pole 9.9 -> 16.0 is 6.1; giving back half is a base low of 12.95
        for low, ok in ((12.96, True), (12.94, False)):        # 49.8% / 50.2%
            s = Synth()
            s.l[s.P + 10] = low
            f = s.watch()
            assert f is not None and f["retrace_ok"] is ok, low
            assert f["retrace"] == pytest.approx((16.0 - low) / 6.1)

    def test_retrace_of_exactly_one_half_is_ok_the_limit_is_inclusive(self):
        # pole low 10 -> pole high 20 -> base low 15: (20 - 15) / (20 - 10) = 0.5 EXACTLY in floating point
        # (every term is a small integer), so this sits ON the line. `anticipation.evaluate_coil_consolidation`
        # rejects only on `retrace > hold_limit`, so "ok" means `<=`: a `<` here would drop the exact-half base.
        s = Synth(top=20.0)
        for k in range(s.P - 20):
            s.l[k] = 10.0                                      # pad lows 9.9 -> 10.0: the pole low is exactly 10
        s.l[s.P + 10] = 15.0
        f = s.watch()
        assert f is not None
        assert (f["pole_high"], f["pole_low"], f["base_low"]) == (20.0, 10.0, 15.0)
        assert f["retrace"] == 0.5 and f["retrace_ok"] is True
        s.l[s.P + 10] = 14.99                                  # one cent deeper: 50.1%, over the line
        g = s.watch()
        assert g is not None and g["retrace"] > 0.5 and g["retrace_ok"] is False

    def test_oust_hand_check_the_august_base_gave_back_82_percent_the_june_base_46(self):
        # HAND-DERIVED from tests/fixtures/htf_labelled_bars.psv (OUST rows).
        # AUGUST base: pole top 63.79 (2026-06-30), pole low 23.60 (2026-05-11), base low 30.822 (07-28):
        #   (63.79 - 30.822) / (63.79 - 23.60) = 32.968 / 40.19 = 0.8203 -> over the 50% cap.
        # JUNE base: pole top 49.39 (06-02), pole low 18.4601 (04-07), base low 35.30 (06-09):
        #   (49.39 - 35.30) / (49.39 - 18.4601) = 14.09 / 30.9299 = 0.4555 -> under it.
        bars, idx = _fixture("OUST")
        assert (bars.h[idx["2026-06-30"]], bars.l[idx["2026-05-11"]]) == (63.79, 23.6)
        assert bars.l[idx["2026-07-28"]] == 30.822 and bars.l[idx["2026-07-01"]:idx["2026-08-05"] + 1].min() == 30.822
        assert (bars.h[idx["2026-06-02"]], bars.l[idx["2026-04-07"]], bars.l[idx["2026-06-09"]]) == (49.39, 18.4601, 35.3)
        aug_expect = (63.79 - 30.822) / (63.79 - 23.6)
        jun_expect = (49.39 - 35.3) / (49.39 - 18.4601)
        assert aug_expect == pytest.approx(0.8203, abs=1e-4) and jun_expect == pytest.approx(0.4555, abs=1e-4)
        # the nights OUST passes the four C1 STRUCTURE flags (sma20, rising sma50, higher lows, tightening)
        struct = []
        for d, k in idx.items():
            f = cb.evaluate_watch(bars, k) if k >= 129 else None
            if f and f["sma20_ok"] and f["sma50_rising"] and f["higher_lows"] and f["tightening_ok"]:
                struct.append((d, f))
        assert [d for d, _ in struct] == ["2026-06-16", "2026-06-17", "2026-08-05", "2026-08-06",
                                          "2026-08-14", "2026-08-17", "2026-08-18"]
        for d, f in struct:
            if d.startswith("2026-08"):
                assert f["pole_date"] == "2026-06-30" and f["retrace"] == pytest.approx(aug_expect)
                assert f["retrace_ok"] is False
            else:
                assert f["pole_date"] == "2026-06-02" and f["retrace"] == pytest.approx(jun_expect)
                assert f["retrace_ok"] is True
        # so C1 loses the five August nights and keeps the two June ones; the reported cell keeps all seven
        ctx = _ctx(spyqqq=True)
        for d, f in struct:
            flags = cb.cell_flags(f, ctx, k="k5")
            assert flags["C1"] is f["retrace_ok"] and flags["C1_no_retrace"] is True, d

    def test_report_cells_drop_exactly_one_term(self):
        ctx = _ctx(spyqqq=True)
        ok = cb.cell_flags(_good_features(), ctx, k="k5")
        assert ok["C1"] and ok["C1_no_retrace"] and ok["C1_no_tightening"]
        r = cb.cell_flags(_good_features(retrace_ok=False), ctx, k="k5")
        assert (r["C1"], r["C1_no_retrace"], r["C1_no_tightening"]) == (False, True, False)
        t = cb.cell_flags(_good_features(tightening_ok=False), ctx, k="k5")
        assert (t["C1"], t["C1_no_retrace"], t["C1_no_tightening"]) == (False, False, True)
        both = cb.cell_flags(_good_features(retrace_ok=False, tightening_ok=False), ctx, k="k5")
        assert not both["C1_no_retrace"] and not both["C1_no_tightening"]
        # the other C1 terms still gate both reported cells
        for kw in (dict(rs=97.9), dict(qqq=False)):
            fl = cb.cell_flags(_good_features(), _ctx(**kw), k="k5")
            assert not fl["C1"] and not fl["C1_no_retrace"] and not fl["C1_no_tightening"], kw
        for flag in ("sma20_ok", "sma50_rising", "higher_lows"):
            fl = cb.cell_flags(_good_features(**{flag: False}), ctx, k="k5")
            assert not fl["C1_no_retrace"] and not fl["C1_no_tightening"], flag
        # reported cells never join the deciding set
        assert cb.CELLS == ("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7")
        assert cb.REPORT_CELLS == ("C1_no_retrace", "C1_no_tightening", "HTF")
        assert set(cb.CELLS).isdisjoint(cb.REPORT_CELLS)


class TestPoleArtifact:
    """Change 4 — a > 50% one-session close jump on < 2x volume inside the pole window rejects."""

    @staticmethod
    def _inject(s: Synth, back: int, close: float, vol: float = 2e6) -> None:
        k = s.P - back                                         # inside the pad, outside P's search window
        s.c[k] = s.o[k] = close
        s.h[k], s.l[k] = close * 1.01, close * 0.99
        s.v[k] = vol

    def test_a_1_6x_jump_on_ordinary_volume_rejects(self):
        s = Synth()
        assert s.watch() is not None
        self._inject(s, 30, 16.0)                              # 10.0 -> 16.0 = 1.6x on 1x volume
        assert s.explain() == (None, "pole_artifact")

    def test_real_volume_on_the_same_jump_is_a_pole_not_an_artifact(self):
        s = Synth()
        self._inject(s, 30, 16.0, vol=5e6)                     # window mean = (40 x 2e6 + 5e6) / 41 = 2.073e6
        assert 5e6 >= 2.0 * (40 * 2e6 + 5e6) / 41              # >= 2x the window's own mean (spike day included)
        assert s.watch() is not None
        s2 = Synth()
        self._inject(s2, 30, 16.0, vol=3e6)                    # 3e6 < 2 x 2.049e6 = 4.10e6 -> still an artifact
        assert s2.explain() == (None, "pole_artifact")

    def test_a_jump_day_at_exactly_2x_the_window_mean_volume_is_not_an_artifact(self):
        # 40 sessions at 975 + the jump day at 2000 -> window mean = 41000 / 41 = 1000.0 EXACTLY (integer sums),
        # so the jump day is exactly 2.0x the mean: the guard is a strict `<`, so it does NOT reject. 1999 is
        # 1.9990x of its own mean (999.976) and does; 2001 is above and does not. A `<=` would flip the 2000 case.
        def artifact(jump_vol: float) -> bool:
            n, P, jump = 60, 50, 20                            # window [P-40, P] = [10, 50]; jump inside it
            c = [10.0] * n
            c[jump] = 16.0                                     # 10 -> 16 = 1.6x (> 1.5); the next day falls back
            v = [975.0] * n
            v[jump] = jump_vol
            bars = cb.daily_bars_from_arrays(_weekdays(n), c, c, c, c, v)
            assert P - cb.POLE_LOOKBACK < jump <= P
            return cb._pole_data_artifact(bars, P)

        assert (40 * 975.0 + 2000.0) / 41 == 1000.0 and 2000.0 == cb.POLE_ARTIFACT_VOL_MULT * 1000.0
        assert artifact(2000.0) is False
        assert artifact(1999.0) is True
        assert artifact(2001.0) is False

    def test_exactly_1_5x_is_not_over_the_line(self):
        s = Synth()
        self._inject(s, 30, 15.0)                              # 15.0 / 10.0 = 1.5 exactly: strict `>`
        assert s.watch() is not None
        s2 = Synth()
        self._inject(s2, 30, 15.01)
        assert s2.explain() == (None, "pole_artifact")

    def test_the_pole_window_is_41_sessions_a_jump_on_its_first_or_older_session(self):
        # window [P-40, P]; a jump is read on sessions P-39..P (prev close inside the window). A jump
        # landing on P-40 (prev = P-41, outside) is not a pole-window event; one on P-39 is.
        s = Synth()
        self._inject(s, 40, 16.0)
        assert s.watch() is not None
        s2 = Synth()
        self._inject(s2, 39, 16.0)
        assert s2.explain() == (None, "pole_artifact")

    def test_agrees_with_the_shipped_detector_guard_on_the_same_bars(self):
        # The guard is an inline literal in flag_detector.compute_flag_metrics, so it is MIRRORED, not
        # imported. Same Synth bars (top 21 so the detector's 90% runup gate lets them through) through
        # BOTH: where the module says pole_artifact the real detector says flagpole_data_artifact_*.
        from agents.market_intelligence import flag_detector as fd

        def detector_reason(s: Synth) -> str:
            ds = _weekdays(s.n)
            rows = [{"trade_date": ds[k], "open_price": s.o[k], "high_price": s.h[k], "low_price": s.l[k],
                     "close": s.c[k], "volume": s.v[k]} for k in range(s.n)]
            return fd.compute_flag_metrics(rows, ticker="X").get("reason") or ""

        scenarios = [("control", None, None), ("1.6x low vol", 16.0, 2e6), ("1.6x high vol", 16.0, 5e6),
                     ("exactly 1.5x", 15.0, 2e6), ("1.51x low vol", 15.1, 2e6)]
        for name, close, vol in scenarios:
            s = Synth(top=21.0)
            if close is not None:
                self._inject(s, 30, close, vol)
            real = detector_reason(s).startswith("flagpole_data_artifact")
            ours = s.explain()[1] == "pole_artifact"
            assert real == ours, (name, detector_reason(s), s.explain())
        # the one deliberate difference: our window is the module's 41-session pole window [P-40, P],
        # the detector's is 40 [P-39, P] -> a jump landing on P-39 is ours alone. Pinned both ways so a
        # drift in EITHER window fails loudly.
        s = Synth(top=21.0)
        self._inject(s, 39, 16.0, 2e6)
        assert s.explain()[1] == "pole_artifact"
        assert not detector_reason(s).startswith("flagpole_data_artifact")

    def test_mrna_08_19_is_a_195m_share_ep_not_an_artifact(self):
        # 62.96 -> 174.38 is a 2.77x one-session close jump, so the volume leg MUST clear or the canary
        # is rejected as a bad tick: 191.7M shares against 2 x the 41-session window mean. The 40
        # sessions before it each traded under 15M (max 14.57M, 07-06), so that mean is under
        # (40 x 15M + 191.7M) / 41 = 19.3M and 2x it under 38.6M (actual mean 10.86M) -> 191.7M clears it.
        bars, idx = _mrna()
        P = idx["2026-08-19"]
        assert bars.c[P] / bars.c[P - 1] == pytest.approx(174.38 / 62.96) and 174.38 / 62.96 > 1.5
        window_mean = bars.v[P - 40:P + 1].mean()
        assert bars.v[P] >= 2.0 * window_mean and bars.v[P] == 191705760
        assert cb.explain_watch(bars, idx["2026-09-16"])[1] is None


class TestExplainWatch:
    """Change 5 — which gate failed, FIRST in evaluation order."""

    def test_the_gate_vocabulary_and_order(self):
        assert cb.WATCH_GATES == ("history", "prior_move", "close_above_pole_high", "close_nonpositive",
                                  "sma50", "deal_pin_median", "fresh_pin", "pole_artifact", "adr_unusable")

    def test_control_passes_and_every_gate_fails_alone_under_its_own_name(self):
        assert Synth().explain()[1] is None

        def variants():
            yield "history", Synth(n=129)
            yield "prior_move", Synth(top=12.8)
            s = Synth(); s.c[s.i - 3] = s.top * 1.001; s.o[s.i - 3] = s.c[s.i - 3]; s.h[s.i - 3] = s.top * 1.01
            yield "close_above_pole_high", s
            s = Synth(); s.c[s.i], s.o[s.i], s.h[s.i], s.l[s.i] = 12.0, 12.0, 12.1, 11.9
            yield "sma50", s
            s = Synth()
            for k in (s.i - 4, s.i - 3, s.i - 2):
                s.h[k], s.l[k] = s.c[k] * 1.001, s.c[k] * 0.999
            yield "deal_pin_median", s
            s = Synth(); _welded_tail(s); s.v[s.i - 5] = 2e7
            yield "fresh_pin", s
            s = Synth(); TestPoleArtifact._inject(s, 30, 16.0)
            yield "pole_artifact", s
            s = Synth()
            for k in range(s.i - 19, s.i - 8):                 # 11 of the last 20 closes unreadable (0)
                s.c[k] = 0.0
            yield "adr_unusable", s

        seen = []
        for gate, s in variants():
            feats, got = s.explain()
            assert feats is None and got == gate, (gate, got)
            seen.append(gate)
        assert seen == [g for g in cb.WATCH_GATES if g != "close_nonpositive"]

    def test_close_nonpositive_is_bad_data(self):
        s = Synth()
        s.c[s.i] = 0.0
        assert s.explain() == (None, "close_nonpositive")

    def test_when_two_gates_fail_the_earlier_one_in_the_order_is_named(self):
        # prior_move + close_above_pole_high
        s = Synth(top=12.8); s.c[s.i - 3] = 13.0; s.h[s.i - 3] = 13.1
        assert s.explain()[1] == "prior_move"
        # close_above_pole_high + sma50
        s = Synth(); s.c[s.i - 3] = s.top * 1.001; s.h[s.i - 3] = s.top * 1.01
        s.c[s.i], s.o[s.i], s.h[s.i], s.l[s.i] = 12.0, 12.0, 12.1, 11.9
        assert s.explain()[1] == "close_above_pole_high"
        # sma50 + deal_pin_median
        s = Synth(); s.c[s.i], s.o[s.i] = 12.0, 12.0
        for k in range(s.i - 4, s.i + 1):
            s.h[k], s.l[k] = s.c[k] * 1.001, s.c[k] * 0.999
        assert s.explain()[1] == "sma50"
        # deal_pin_median + fresh_pin
        s = Synth()
        for k in range(s.i - 4, s.i + 1):
            s.h[k], s.l[k] = s.c[k] * 1.001, s.c[k] * 0.999
        s.v[s.i - 5] = 2e7
        assert s.explain()[1] == "deal_pin_median"
        # fresh_pin + pole_artifact
        s = Synth(); _welded_tail(s); s.v[s.i - 5] = 2e7; TestPoleArtifact._inject(s, 30, 16.0)
        assert s.explain()[1] == "fresh_pin"
        # pole_artifact + adr_unusable
        s = Synth(); TestPoleArtifact._inject(s, 30, 16.0)
        for k in range(s.i - 19, s.i - 8):
            s.c[k] = 0.0
        assert s.explain()[1] == "pole_artifact"

    def test_evaluate_watch_is_the_thin_wrapper(self):
        for s in (Synth(), Synth(n=129), Synth(top=12.8)):
            b = s.bars()
            assert cb.evaluate_watch(b, s.i) == cb.explain_watch(b, s.i)[0]
        b, idx = _mrna()
        assert cb.evaluate_watch(b, idx["2026-09-16"]) == cb.explain_watch(b, idx["2026-09-16"])[0]

    def test_out_of_range_index_is_still_a_caller_bug(self):
        b = Synth().bars()
        with pytest.raises(IndexError):
            cb.explain_watch(b, len(b))
        with pytest.raises(IndexError):
            cb.explain_watch(b, -1)


class TestTelemetry:
    """Change 6 — features that never gate."""

    def setup_method(self):
        self.bars, self.idx = _mrna()
        self.i = self.idx["2026-09-16"]
        self.f = cb.evaluate_watch(self.bars, self.i)

    def test_mrna_retrace_by_hand(self):
        # pole top 176.66, pole low 52.6601, base low 128.61 -> (176.66 - 128.61) / (176.66 - 52.6601)
        assert (self.f["pole_high"], self.f["pole_low"], self.f["base_low"]) == (176.66, 52.6601, 128.61)
        assert self.f["retrace"] == pytest.approx(48.05 / 124.0, rel=1e-6) and self.f["retrace"] == pytest.approx(0.3875, abs=1e-4)
        assert self.f["retrace_ok"] is True

    def test_mrna_pole_telemetry_by_hand(self):
        # the biggest single-session close gain inside (08-03, 08-19] is the EP day itself:
        # 174.38 / 62.96 - 1; its gap is the 08-19 open 116.02 over the 08-18 close 62.96
        assert self.f["pole_max_gain_day"] == "2026-08-19"
        assert self.f["pole_max_gain"] == pytest.approx(174.38 / 62.96 - 1.0)
        assert self.f["pole_max_gap"] == pytest.approx(116.02 / 62.96 - 1.0)
        # volume that day 191,705,760 over the mean of the 20 sessions ENDING THE DAY BEFORE the pole low
        # (08-03): 07-06 .. 07-31, whose twenty volumes sum to 117,820,466 -> mean 5,891,023.3
        v20 = [14571593, 6932312, 6545770, 4343874, 9142812, 8514671, 5474033, 3418829, 5579167, 4543225,
               4943704, 4116413, 3764801, 4454400, 4398086, 5036752, 5523004, 4338643, 4424240, 7754137]
        assert list(self.bars.v[self.idx["2026-08-03"] - 20:self.idx["2026-08-03"]]) == v20
        assert sum(v20) == 117_820_466
        assert self.f["pole_day_vol_ratio"] == pytest.approx(191_705_760 / (117_820_466 / 20))
        assert self.f["pole_day_vol_ratio"] == pytest.approx(32.542, abs=1e-3)

    def test_mrna_dollar_volume_and_atr_slope_match_independent_computations(self):
        b, i = self.bars, self.i
        assert self.f["median_dollar_vol20"] == pytest.approx(float(np.median(b.c[i - 19:i + 1] * b.v[i - 19:i + 1])))

        def atr_pct(j):                                        # mean of the 14 true ranges ending j, over close j
            trs = [max(b.h[k] - b.l[k], abs(b.h[k] - b.c[k - 1]), abs(b.l[k] - b.c[k - 1])) for k in range(j - 13, j + 1)]
            return float(np.mean(trs) / b.c[j])

        P = self.f["pole_idx"]
        assert self.f["atr14_slope"] == pytest.approx(atr_pct(i) / atr_pct(P + 1), rel=1e-12)
        assert self.f["atr14"] == pytest.approx(atr_pct(i), rel=1e-12)

    def test_a_pole_low_on_the_pole_day_leaves_the_pole_telemetry_empty(self):
        s = Synth()
        s.l[s.P] = 5.0                                          # the lowest low of the window IS the pole day
        f = s.watch()
        assert f is not None and f["pole_sessions"] == 0
        assert f["pole_max_gain_day"] is None and f["pole_max_gain"] is None
        assert f["pole_max_gap"] is None and f["pole_day_vol_ratio"] is None

    def test_telemetry_never_gates(self):
        s = Synth()
        s.v = [10.0] * s.n                                     # $20 of dollar volume a day: telemetry, not a gate
        f = s.watch()
        assert f is not None and f["median_dollar_vol20"] < 1_000.0
        s2 = Synth()
        s2.o[s2.P - 3] = s2.c[s2.P - 4] * 1.4                  # a 40% overnight gap inside the pole
        f2 = s2.watch()
        assert f2 is not None and f2["pole_max_gap"] == pytest.approx(0.4)

    def test_synth_pole_gain_day_and_volume_ratio(self):
        s = Synth()
        k = s.P - 7                                             # one big up session inside the pole
        s.c[k] = s.c[k - 1] * 1.06
        s.o[k], s.h[k], s.l[k] = s.c[k - 1], s.c[k] * 1.01, s.c[k - 1] * 0.99
        s.v[k] = 8e6
        f = s.watch()
        low_idx = f["pole_low_idx"]
        assert f["pole_max_gain_day"] == _weekdays(s.n)[k].isoformat()
        assert f["pole_max_gain"] == pytest.approx(0.06)
        assert f["pole_day_vol_ratio"] == pytest.approx(8e6 / 2e6)             # flat 2e6 before the pole low
        assert low_idx < k


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6b. The down-sloping TRENDLINE breakout level `tl` (#702 P1c — his note 2026-10-17)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _tl_synth(highs: dict) -> Synth:
    """A Synth C0 pass (pole high 16.0 at P, i = P + 20) whose base highs for sessions P+j are overridden from
    `highs` {j: high}. Every override sits at or above the Synth closes/opens (<= 15.09), so the bars stay
    internally consistent, and the first three base sessions stay under the pole high (else the pole walk moves)."""
    s = Synth()
    for j, hi in highs.items():
        s.h[s.P + j] = hi
    return s


def _line16(j: int) -> float:
    """The dyadic test line through (P, 16.0) with slope -1/32 per session: exact in binary, so every expected
    number below is exact rather than approximately equal."""
    return 16.0 - j / 32.0


class TestTrendline:
    """The line is anchored at the pole top (P, high[P]) with slope m = max over j in (P, i] of
    (high[j] - high[P]) / (j - P); pivot_tl = high[P] + m x (i + 1 - P), the level a break on E = i + 1 must clear."""

    def setup_method(self):
        self.bars, self.idx = _mrna()
        self.i = self.idx["2026-09-16"]
        self.f = cb.evaluate_watch(self.bars, self.i)

    def test_pivot_keys_gain_tl(self):
        assert cb.PIVOT_KEYS == ("k5", "k10", "full", "tl")

    # ── MRNA canary, derived by hand from tests/fixtures/htf_labelled_bars.psv ───────────────────
    def test_mrna_slope_touch_and_the_projected_level_by_hand(self):
        # P = 2026-08-19, high 176.66. Sessions after P and each base high's slope (high - 176.66) / sessions:
        #   08-25  161.37  4 sessions  -15.29 / 4  = -3.8225        09-02  156.4151 10 sessions -2.0245
        #   09-04  154.69  12 sessions -22.0 / 12  = -1.8308        09-11  149.7344 16 sessions -1.6828
        #   09-14  147.3399 17 sessions            = -1.7247        09-15  148.6999 18 sessions -1.5533
        #   09-16  148.93  19 sessions -27.73 / 19 = -1.4595  <- the flattest: the touch is the watch night itself
        m = (148.93 - 176.66) / 19
        assert m == pytest.approx(-1.4595, abs=5e-5)
        assert self.f["tl_touch_date"] == "2026-09-16" and self.f["tl_touch_idx"] == self.i
        assert self.f["tl_touch_is_today"] is True
        assert self.f["tl_slope_pct"] == pytest.approx(m / 176.66, rel=1e-12)
        # the level for 09-17 is the line 20 sessions after the pole: 176.66 - 20 x 1.45947... = 147.4705,
        # which is the touch high plus ONE more session of slope (148.93 + m), NOT the line's value at 09-16
        assert self.f["pivot_tl"] == pytest.approx(176.66 + 20 * m, rel=1e-12)
        assert self.f["pivot_tl"] == pytest.approx(147.4705, abs=5e-5)
        assert self.f["pivot_tl"] == pytest.approx(148.93 + m, rel=1e-12)       # kills "projected at i, not i + 1"
        assert self.f["pivot_tl"] != pytest.approx(148.93, abs=0.5)
        # every other base high lies UNDER the line (the definition's own invariant)
        P = self.f["pole_idx"]
        for j in range(P + 1, self.i + 1):
            assert self.bars.h[j] <= 176.66 + m * (j - P) + 1e-9, self.bars.dates[j]

    def test_mrna_the_line_sits_below_the_horizontal_breakouts_and_the_next_session_clears_it(self):
        assert self.f["pivot_tl"] < self.f["pivot_k5"] == 149.7344
        assert self.f["pivot_tl"] < self.f["pivot_k10"] < self.f["pivot_full"]
        assert self.bars.h[self.idx["2026-09-17"]] == 161.9599 > self.f["pivot_tl"]
        # 09-17's open 152.50 gaps over the line, so a buy-the-line entry fills at the open
        assert 152.5 > self.f["pivot_tl"]

    def test_mrna_interior_touches_by_hand(self):
        # the line at 09-15 is 148.93 + 1.4595 = 150.39; the 09-15 high 148.6999 is 1.1% under it, more than the 0.5%
        # tolerance, and no other interior base high is closer in percentage terms -> none touch
        m = (148.93 - 176.66) / 19
        P = self.f["pole_idx"]
        gaps = [(176.66 + m * (j - P) - self.bars.h[j]) / (176.66 + m * (j - P)) for j in range(P + 1, self.i)]
        assert min(gaps) > cb.TL_TOUCH_TOL
        assert self.f["tl_interior_touches"] == 0

    def test_mrna_aliases_and_cells_and_the_breakout_key(self):
        assert self.f["pivot_tl_date"] == self.f["tl_touch_date"] and self.f["pivot_tl_idx"] == self.f["tl_touch_idx"]
        ctx = {"rs_best": 99.5, "rs_all": 99.0, "grp_pct": 90.0, "phase_qqq_10_20": True, "phase_spy_qqq_50": True}
        flags = cb.cell_flags(self.f, ctx, k="tl")
        assert all(flags[c] for c in cb.CELLS)
        assert cb.breakout_key("MRNA", self.f, "tl") == ("MRNA", "2026-09-16")

    # ── synthetic: each case isolates one property of the definition ─────────────────────────────
    def test_a_falling_flag_the_line_is_below_the_base_high_and_breaks_first(self):
        # highs on the exact line 16 - j/32 at j = 10 and 1/8 UNDER it everywhere else (j = 5 and 7 excepted below):
        # slope at j = 10 is -0.3125 / 10 = -1/32 exactly; every other session is steeper (-1/32 - 1/(8 j)).
        highs = {j: _line16(j) - 0.125 for j in range(1, 21)}
        highs[10] = _line16(10)                                       # 15.6875 — the touch
        s = _tl_synth(highs)
        f = s.watch()
        assert f is not None
        assert f["tl_touch_idx"] == s.P + 10 and f["tl_touch_is_today"] is False
        assert f["tl_touch_date"] == _weekdays(s.n)[s.P + 10].isoformat() == f["pivot_tl_date"]
        assert f["tl_slope_pct"] == -1 / 32 / 16.0
        # next-session level: 16 - 21/32 = 15.34375 — the line 20 + 1 sessions after the pole
        assert f["pivot_tl"] == 15.34375
        # the base high is the first session's 16 - 1/32 - 1/8 = 15.84375: the line is 0.5 BELOW it
        assert f["pivot_full"] == 15.84375 and f["pivot_tl"] < f["pivot_full"]
        # a break of the line before any break of the base high: a day topping at 15.5 clears one, not the other
        mins = _flat_day(price=15.4, overrides={0: (15.4, 15.5, 15.3, 15.45)}, hi=0.1)
        at_line = _run(mins, pivot=f["pivot_tl"])
        at_base = _run(mins, pivot=f["pivot_full"])
        assert at_line["pivot"]["status"] == "filled" and at_line["pivot"]["level"] == f["pivot_tl"]
        assert at_base["pivot"]["status"] != "filled"

    def test_the_touch_is_the_flattest_line_not_the_highest_high(self):
        # the base high (j = 1, 15.84375) is NOT the touch: j = 1 has slope -0.15625, far steeper than -1/32
        highs = {j: _line16(j) - 0.125 for j in range(1, 21)}
        highs[10] = _line16(10)
        f = _tl_synth(highs).watch()
        assert f["pivot_full_idx"] != f["tl_touch_idx"]

    def test_ties_resolve_to_the_latest_touch(self):
        # three exactly collinear highs on the -1/32 line at j = 6, 12, 18 (slope -1/32 each); np.argmax would take 6
        highs = {j: _line16(j) - 0.125 for j in range(1, 21)}
        for j in (6, 12, 18):
            highs[j] = _line16(j)
        s = _tl_synth(highs)
        f = s.watch()
        assert f["tl_touch_idx"] == s.P + 18
        assert f["pivot_tl"] == 16.0 - 21 / 32
        assert f["tl_interior_touches"] == 3                    # 6, 12 and 18 are all interior (< i = P + 20)

    def test_a_flat_top_is_a_valid_line_and_ties_to_the_latest_equal_high(self):
        # two base highs EQUAL to the pole high (j = 12 and 15, past the pole walk's window): m == 0
        highs = {j: 15.5 for j in range(1, 21)}
        highs[12] = highs[15] = 16.0
        s = _tl_synth(highs)
        f = s.watch()
        assert f is not None
        assert f["pivot_tl"] == 16.0 and f["tl_slope_pct"] == 0.0
        assert f["tl_touch_idx"] == s.P + 15                    # the LATEST of the two ties
        assert f["tl_interior_touches"] == 2
        assert cb.cell_flags(f, _ctx(), k="tl")["C0"] is True

    def test_a_wick_above_the_pole_high_moves_the_line_s_anchor_to_the_wick(self):
        # a base high at 16.4 > the pole high 16.0 (a wick; only a CLOSE above ends the base). The line is drawn
        # from the base's highest high: A = P+15 (16.4); the flattest line to the later highs (all 15.5) touches
        # tonight, i = P+20: slope (15.5 - 16.4) / 5 = -0.18 per session; projected to i+1: 16.4 - 0.18 x 6 = 15.32.
        highs = {j: 15.5 for j in range(1, 21)}
        highs[15] = 16.4
        s = _tl_synth(highs)
        f = s.watch()
        assert f is not None, "a wick does not end the base"
        assert f["tl_anchor_idx"] == s.P + 15
        assert f["pivot_tl"] == pytest.approx(16.4 - 0.18 * 6)
        assert f["tl_slope_pct"] == pytest.approx(-0.18 / 16.4)
        assert f["tl_touch_idx"] == s.i and f["tl_touch_is_today"] is True
        assert f["pivot_full"] == 16.4                                        # the horizontal levels are untouched
        assert cb.cell_flags(f, _ctx(), k="tl")["C0"] is True
        json.dumps(f)

    def test_no_line_while_the_highest_high_is_under_three_sessions_old(self):
        highs = {j: 15.5 for j in range(1, 21)}
        highs[18] = 16.4                                                      # i - A = 2 < 3
        f = _tl_synth(highs).watch()
        assert f is not None and f["pivot_tl"] is None and f["tl_slope_pct"] is None
        assert cb.cell_flags(f, _ctx(), k="tl")["C0"] is False
        with pytest.raises(ValueError):
            cb.breakout_key("ABC", f, "tl")

    def test_interior_touches_count_within_half_a_percent_and_exclude_the_watch_night_and_the_pole(self):
        highs = {j: _line16(j) - 0.125 for j in range(1, 21)}
        highs[10] = _line16(10)                                 # the touch (interior)
        highs[5] = _line16(5) - 0.05                            # 0.05 / 15.84 = 0.32% under the line  -> a touch
        highs[7] = _line16(7) - 0.10                            # 0.10 / 15.78 = 0.63% under the line  -> not
        highs[20] = _line16(20) - 0.05                          # within tolerance but it IS the watch night -> excluded
        f = _tl_synth(highs).watch()
        assert f["tl_interior_touches"] == 2                    # j = 10 and j = 5
        assert f["tl_touch_is_today"] is False
        # the 0.5% edge is relative to the line at the high's OWN session: 0.005 x 15.84375 = 0.0792 at j = 5
        for gap, want in ((0.0790, 2), (0.0795, 1)):
            h2 = dict(highs)
            h2[5] = _line16(5) - gap
            assert _tl_synth(h2).watch()["tl_interior_touches"] == want, gap

    def test_a_non_positive_projected_level_is_no_level(self):
        # a line that has fallen through zero: pole high 100, the watch night's high 5 ten sessions later
        n = 12
        h = np.array([100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0, 5.0, 4.0][:n])
        bars = cb.daily_bars_from_arrays(_weekdays(n), h, h, h, h, [1.0] * n)
        out = cb._down_trendline(bars, 0, 10)                   # P = 0, i = 10: m = max((h[j]-100)/j) = -9.5 at j = 10
        assert out["tl_slope_pct"] == pytest.approx(-9.5 / 100.0)
        assert out["pivot_tl"] is None and out["tl_touch_idx"] is None      # 100 - 9.5 x 11 = -4.5

    def test_every_tl_key_is_present_on_every_row_with_plain_json_types(self):
        keys = {"pivot_tl", "pivot_tl_idx", "pivot_tl_date", "tl_slope_pct", "tl_touch_idx", "tl_touch_date",
                "tl_touch_is_today", "tl_interior_touches"}
        wick = _tl_synth({**{j: 15.5 for j in range(1, 21)}, 15: 16.4}).watch()
        for f in (self.f, wick, Synth().watch()):
            assert keys <= set(f)
            for k in keys:
                assert type(f[k]) in (int, float, bool, str, type(None)), (k, type(f[k]))
            json.dumps(f)

    def test_the_line_uses_bars_up_to_the_watch_night_only(self):
        # bars after i never enter: three huge later sessions change nothing about the line at i
        s = Synth()
        base = s.watch()
        bars = s.bars()
        longer = cb.daily_bars_from_arrays(
            list(bars.dates) + _weekdays(s.n + 3)[s.n:], list(bars.o) + [20.0] * 3, list(bars.h) + [99.0] * 3,
            list(bars.l) + [19.0] * 3, list(bars.c) + [20.0] * 3, list(bars.v) + [2e6] * 3)
        again = cb.evaluate_watch(longer, s.i)
        assert {k: again[k] for k in base if k.startswith(("tl_", "pivot_tl"))} == \
            {k: base[k] for k in base if k.startswith(("tl_", "pivot_tl"))}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6c. The labelled corpus (change 8)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# (ticker, label_date) -> runs of (first night, last night, verdict) over the member's window: the 10 bar
# sessions strictly before `label_date` plus its `assert_dates`. verdict = "C0" (every structural gate
# passed) or the name of the FIRST failing gate. Generated by running `explain_watch` over the fixture
# bars on 2026-10-17 — a REGRESSION PIN of what the module does, NOT evidence that it is right.
CORPUS_PIN = {
    ("CDNA", "2026-08-19"): [("2026-08-05", "2026-08-14", "close_above_pole_high"), ("2026-08-17", "2026-08-19", "C0")],
    ("HNGE", "2026-08-24"): [("2026-08-10", "2026-08-21", "close_above_pole_high"), ("2026-08-24", "2026-08-24", "C0")],
    ("MRNA", "2026-09-17"): [("2026-09-02", "2026-09-16", "C0")],
    ("NCI", "2026-06-27"): [("2026-06-12", "2026-06-15", "close_above_pole_high"), ("2026-06-16", "2026-06-18", "C0"),
                            ("2026-06-22", "2026-06-26", "close_above_pole_high")],
    ("ATAI", "2026-07-24"): [("2026-07-10", "2026-07-24", "close_above_pole_high")],
    ("OUST", "2026-09-04"): [("2026-06-29", "2026-06-29", "close_above_pole_high"), ("2026-08-21", "2026-09-03", "sma50")],
    ("SHAZ", "2026-09-04"): [("2026-06-29", "2026-08-21", "history"), ("2026-08-24", "2026-09-03", "sma50")],
    ("REPL", "2026-09-04"): [("2026-08-10", "2026-09-03", "close_above_pole_high")],
    ("GH", "2026-06-27"): [("2026-06-12", "2026-06-23", "C0"), ("2026-06-24", "2026-06-26", "close_above_pole_high")],
    ("HNGE", "2026-06-27"): [("2026-06-12", "2026-06-26", "close_above_pole_high")],
    ("HPE", "2026-06-02"): [("2026-05-18", "2026-06-02", "close_above_pole_high")],
}


class TestLabelledCorpus:
    """REGRESSION PIN over every member of tests/fixtures/htf_labelled.py that has bars in the fixture
    psv. It pins BEHAVIOUR — which nights of each labelled window pass C0, else the first failing gate —
    so a later change to any gate shows up as a diff here; it does not prove any verdict is right. The
    hand-derived assertions live beside it: MRNA (TestMrnaCanary), GH (TestBaseAnchor), ATAI
    (TestFreshPinGate), OUST (TestRetrace)."""

    @staticmethod
    def _runs(member) -> list:
        bars, _ = _fixture(member.ticker)
        d = bars.dates
        before = [k for k, x in enumerate(d) if x < member.label_date][-10:]
        extra = [d.index(x) for x in member.assert_dates if x in d]
        out: list = []
        for k in sorted(set(before) | set(extra)):
            f, g = cb.explain_watch(bars, k)
            verdict, night = ("C0" if f else g), d[k].isoformat()
            if out and out[-1][2] == verdict:
                out[-1] = (out[-1][0], night, verdict)
            else:
                out.append((night, night, verdict))
        return out

    @staticmethod
    def _members_with_bars() -> dict:
        from tests.fixtures.htf_labelled import HTF_LABELLED
        tickers = {ln.split("|", 1)[0] for ln in FIXTURE.read_text().splitlines() if ln}
        return {(m.ticker, m.label_date.isoformat()): m for m in HTF_LABELLED if m.ticker in tickers}

    def test_the_pinned_set_is_every_labelled_member_that_has_bars(self):
        assert set(self._members_with_bars()) == set(CORPUS_PIN)

    def test_every_window_verdict_is_pinned(self):
        for key, member in self._members_with_bars().items():
            assert self._runs(member) == CORPUS_PIN[key], key

    def test_every_verdict_is_a_known_gate_or_c0(self):
        known = set(cb.WATCH_GATES) | {"C0"}
        assert {v for runs in CORPUS_PIN.values() for *_, v in runs} <= known

    def test_the_hand_derived_canaries_agree_with_the_pin(self):
        # MRNA's 09-16 watch night and GH's 06-23 (a pass the committed P1 gate could not give) are pass nights
        assert ("2026-09-02", "2026-09-16", "C0") in CORPUS_PIN[("MRNA", "2026-09-17")]
        assert ("2026-06-12", "2026-06-23", "C0") in CORPUS_PIN[("GH", "2026-06-27")]


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


def test_adr20_is_the_broker_function_itself_not_a_mirror():
    # imported under the `# exec-boundary-ok:` marker (exit_logic is pure ladder math); the old mirror and its
    # equality test are gone, so this pins that a second copy cannot come back unnoticed
    from agents.market_intelligence.broker import exit_logic
    assert cb.adr20_pct_from_bars is exit_logic.adr20_pct_from_bars
    assert cb.adr20_pct_from_bars([{"h": 11.0, "l": 10.0, "c": 10.0}] * 10) == pytest.approx(0.1)
    assert cb.adr20_pct_from_bars([{"h": 11.0, "l": 10.0, "c": 10.5}] * 9) is None            # fewer than 10 usable


def test_the_pole_artifact_literals_are_flag_detectors_named_constants():
    from agents.market_intelligence import flag_detector as fd
    assert cb.POLE_ARTIFACT_JUMP is fd._POLE_ARTIFACT_JUMP and cb.POLE_ARTIFACT_VOL_MULT is fd._POLE_ARTIFACT_VOL_MULT
    assert (cb.POLE_ARTIFACT_JUMP, cb.POLE_ARTIFACT_VOL_MULT) == (1.50, 2.0)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 7. the plumbing the runner and the nightly shadow share (one definition, here)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestSharedPlumbing:
    def test_exchange_test_symbols(self):
        for t in ("ZVZZT", "ZWZZT", "ZXZZT", "ZBZX", "NTEST", "ZTEST", "ZAZZC"):
            assert cb.is_test_symbol(t) is True, t
        for t in ("AAPL", "ZZZZ", "TSLA", "ZVZZTX", ""):
            assert cb.is_test_symbol(t) is False, t

    def test_security_type_falls_back_mi_then_sic_then_unknown(self):
        assert cb.resolve_sectype("X", {"X": "CS"}, {"X": "ADRC"}) == "CS"
        assert cb.resolve_sectype("X", {}, {"X": "ADRC"}) == "ADRC"
        assert cb.resolve_sectype("X", {"X": ""}, {}) == ""

    def test_contiguity_mask_and_tail(self):
        import random
        rng = random.Random(1)
        for _ in range(100):
            n = rng.randint(100, 200)
            gaps = [1 if rng.random() > 0.01 else rng.randint(2, 4) for _ in range(n - 1)]
            cidx = np.cumsum([0] + gaps).astype(np.int64)
            mask = cb.contiguous_window_mask(cidx, 130)
            want = [i >= 129 and int(cidx[i]) - int(cidx[i - 129]) == 129 for i in range(n)]       # the definition
            assert mask.tolist() == want
            assert cb.contiguous_tail(cidx, 130) == want[-1]
        assert cb.contiguous_tail(np.arange(129), 130) is False                  # one bar short of the window
        assert cb.contiguous_tail(np.arange(130), 130) is True
        assert cb.contiguous_tail(np.array([], dtype=np.int64), 130) is False

    def test_the_forward_walk_stops_before_the_first_bar_after_a_hole(self):
        import random
        rng = random.Random(2)
        for _ in range(200):
            n = rng.randint(5, 200)
            gaps = [1 if rng.random() > 0.05 else rng.randint(2, 3) for _ in range(n - 1)]
            cidx = np.cumsum([0] + gaps).astype(np.int64)
            e = rng.randint(0, n - 1)
            hi = e + rng.randint(1, 130)
            end = min(hi, n)
            want = (end, False)
            for j in range(e + 1, end):                                           # the definition, bar by bar
                if int(cidx[j]) - int(cidx[j - 1]) != 1:
                    want = (j, True)
                    break
            assert cb.fwd_end(cidx, e, hi) == want

    def test_forward_window_is_horizon_plus_one_bars_cut_at_a_hole(self):
        bars = _closes_only([10.0 + k for k in range(200)])
        cidx = np.arange(200, dtype=np.int64)
        fwd, cut = cb.forward_window(bars, cidx, 10, 120)
        assert (len(fwd), cut) == (121, False) and fwd.dates[0] == bars.dates[11]
        holed = cidx.copy()
        holed[50:] += 1                                                           # a missing session before bar 50
        fwd, cut = cb.forward_window(bars, holed, 10, 120)
        assert (len(fwd), cut) == (39, True) and fwd.dates[-1] == bars.dates[49]
        fwd, cut = cb.forward_window(bars, None, 10, 120)                         # no hole information: bars only
        assert (len(fwd), cut) == (121, False)
        fwd, cut = cb.forward_window(bars, None, 190, 120)
        assert (len(fwd), cut) == (9, False)

    def test_breakout_gap_and_maturity_helpers(self):
        assert cb.breaks_out(10.0, 9.9) is True and cb.breaks_out(9.9, 9.9) is False
        assert cb.breaks_out(9.0, 9.9) is False and cb.breaks_out(10.0, None) is False
        gap, over = cb.gap_fields(11.0, 10.0, 0.05)
        assert gap == pytest.approx(0.10) and over is True
        gap, over = cb.gap_fields(10.2, 10.0, 0.05)
        assert gap == pytest.approx(0.02) and over is False
        for st in ("stopped", "stopped_day0", "trailed", "target", "time_exit"):
            assert cb.is_mature(st, 0) is True
        assert cb.is_mature("censored", 121) is True and cb.is_mature("censored", 120) is False
        assert cb.is_mature("censored", 61, horizon=60) is True
        assert cb.is_mature("degraded", 500) is False and cb.is_mature("unbookable", 500) is False
        assert cb.TERMINAL_STATUSES == {"stopped", "stopped_day0", "trailed", "target", "time_exit"}

    def test_one_definition_of_the_names_both_callers_use(self):
        assert cb.KS == cb.PIVOT_KEYS and cb.CELL_NAMES == cb.CELLS + cb.REPORT_CELLS
        assert (cb.POLE_DRIFT_MAX, cb.POLE_BAD_HIGH_X) == (3, 1.25)
        from agents.market_intelligence import consolidation_breakout_shadow as sh
        from scripts.probes._cb_backtest import runner as rn
        for name in ("is_test_symbol", "resolve_sectype", "breaks_out", "gap_fields", "is_mature", "forward_window",
                     "fwd_end", "cross_section_one_date", "stamp_retrigger", "chain_bases", "stamp_base_chain",
                     "contiguous_window_mask", "KS", "CELL_NAMES", "POLE_DRIFT_MAX", "POLE_BAD_HIGH_X"):
            assert getattr(rn, name) is getattr(cb, name), name
        for name in ("is_test_symbol", "resolve_sectype", "breaks_out", "gap_fields", "is_mature", "forward_window",
                     "cross_section_one_date", "stamp_retrigger", "chain_bases", "stamp_base_chain",
                     "contiguous_tail", "KS", "CELL_NAMES"):
            assert getattr(sh, name) is getattr(cb, name), name
        for name in ("TEST_SYMBOLS", "_TEST_FAMILY", "TERMINAL_STATUSES", "POLE_BAD_HIGH_X", "contiguous_tail"):
            assert not hasattr(rn, name) or getattr(rn, name) is getattr(cb, name), name     # no second copy in the runner
            assert not hasattr(sh, name) or getattr(sh, name) is getattr(cb, name), name     # none in the shadow

    def test_cross_section_hand_worked(self):
        # five members, the first three in group "28", the next two in a group of 2 (< 10 members: it drops out)
        r21 = [0.10, 0.20, 0.30, None, 0.05]
        r63 = [0.10, 0.20, 0.30, 0.40, 0.50]
        r126 = [0.30, 0.20, 0.10, 0.50, None]
        groups = ["28", "28", "28", "35", "35"]
        rs_best, rs_all, grp, n_groups = cb.cross_section_one_date(r21, r63, r126, groups)
        p21, p63, p126 = (cb.percentile_ranks(r) for r in (r21, r63, r126))
        for k in range(5):
            vals = [x for x in (p21[k], p63[k], p126[k]) if x is not None]
            assert rs_best[k] == (max(vals) if vals else None)
            assert rs_all[k] == (min(vals) if len(vals) == 3 else None)
        assert rs_all[3] is None and rs_all[4] is None and rs_all[0] is not None            # one None percentile -> None
        assert n_groups == 0 and grp == [None] * 5                                           # no group reaches 10 members

    def test_stamping_first_break_and_the_chain_key(self):
        def cand(ticker, pole_ci, e, **cells):
            c = {"ticker": ticker, "pole_ci": pole_ci, "pole_date": f"2026-01-{pole_ci:02d}", "K": "k5", "E": e}
            c.update({n: False for n in cb.CELL_NAMES})
            c.update(cells)
            return c
        a, b, d = cand("AAA", 10, "2026-03-02"), cand("AAA", 10, "2026-03-05", C1=True), cand("AAA", 13, "2026-03-09", C1=True)
        cs = [d, a, b]
        cb.stamp_retrigger(cs)
        assert (a["retrigger"], b["retrigger"], d["retrigger"]) == (0, 1, 0)               # d: another pole = another spec base
        assert (a["first_C1"], b["first_C1"], d["first_C1"]) == (0, 1, 1)                   # b: the first break with C1 held
        cb.stamp_base_chain(cs, cb.chain_bases([("AAA", 10, a["pole_date"]), ("AAA", 13, d["pole_date"])]))
        assert {c["base_id"] for c in cs} == {"AAA|" + a["pole_date"]}                      # poles 3 apart = ONE base
        assert (a["retrigger_chain"], b["retrigger_chain"], d["retrigger_chain"]) == (0, 1, 1)
        far = cand("AAA", 14, "2026-03-12")
        assert cb.chain_bases([("AAA", 10, "p10"), ("AAA", 14, "p14")]) == {("AAA", 10): "AAA|p10", ("AAA", 14): "AAA|p14"}
        assert far["pole_ci"] - 10 > cb.POLE_DRIFT_MAX                                       # 4 apart: two bases

    def test_walk_arms_books_a_day0_stop_once_and_walks_the_rest_per_arm(self):
        entry = {"status": "filled", "fill": 100.0, "stop": 95.0, "width_pct": 0.05,
                 "day0": {"stopped": False, "exit_price": None, "exit_minute": None}}
        rows = _drift_rows(40) + [(50.0, 50.0, 50.0, 50.0)] * 5                    # a late gap-down: stops every arm
        fwd = _fwd(rows)
        out = cb.walk_arms(entry, closes_before=BEFORE, fwd=fwd, adr20=ADR)
        assert list(out) == list(cb.ARMS)
        for name, arm in cb.ARMS.items():
            want = cb.walk_exit(fill=100.0, stop=95.0, closes_before=BEFORE, fwd=fwd, arm=arm, adr20=ADR)
            assert out[name] == want, name
        only = cb.walk_arms(entry, closes_before=BEFORE, fwd=fwd, adr20=ADR, arms={"stop_only": cb.ARMS["stop_only"]})
        assert list(only) == ["stop_only"] and only["stop_only"] == out["stop_only"]            # `arms` filters
        stopped = dict(entry, day0={"stopped": True, "exit_price": 94.0, "exit_minute": 12})
        d0 = cb.walk_arms(stopped, closes_before=BEFORE, fwd=fwd, adr20=ADR)
        one = cb.day0_result_to_outcome(stopped, ADR)
        assert list(d0) == list(cb.ARMS) and all(v == one and v["status"] == "stopped_day0" for v in d0.values())
        assert len({id(v) for v in d0.values()}) == len(cb.ARMS)                                 # separate dicts per arm


def test_the_htf_report_cell_uses_flag_detectors_own_geometry():
    from agents.market_intelligence.flag_detector import _FLAG_DEPTH_MIN, _RUNUP_MIN_RATIO
    assert "HTF" in cb.REPORT_CELLS and "HTF" not in cb.CELLS
    base = {"pivot_k5": 10.0, "sma20_ok": True, "sma50_rising": True, "higher_lows": True, "tightening_ok": True,
            "retrace_ok": True, "prior_move": 1.0}
    # a 100% pole (20 / 10) holding 80% of its top: an HTF base
    f = dict(base, pole_high=20.0, pole_low=10.0, base_low=16.0)
    assert cb.cell_flags(f, {}, k="k5")["HTF"] is True
    # an 80% pole (18 / 10): not HTF; a 26% pullback (14.8 / 20): not HTF
    assert cb.cell_flags(dict(f, pole_high=18.0), {}, k="k5")["HTF"] is False
    assert cb.cell_flags(dict(f, base_low=14.8), {}, k="k5")["HTF"] is False
    # the boundaries are flag_detector's (>= on both)
    edge = dict(f, pole_high=10.0 * _RUNUP_MIN_RATIO, base_low=_FLAG_DEPTH_MIN * 10.0 * _RUNUP_MIN_RATIO)
    assert cb.cell_flags(edge, {}, k="k5")["HTF"] is True
    assert cb.cell_flags(dict(f, pivot_k5=None), {}, k="k5")["HTF"] is False      # C0 first
