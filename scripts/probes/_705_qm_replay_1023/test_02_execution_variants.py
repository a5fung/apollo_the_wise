"""Synthetic tests for 02_execution_variants.py (#705, the execution-gap variants). No real data file is opened by any test: every
world is hand-built in tmp_path (the end-to-end test runs the FROZEN first read's `run_replay` on the same world first, so the
baseline-parity gate is exercised against outputs that exist).

Run:  python3 -m pytest scripts/probes/_705_qm_replay_1023/test_02_execution_variants.py -q
"""
from __future__ import annotations

import gzip
import importlib.util
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("exec02", os.path.join(HERE, "02_execution_variants.py"))
ex = importlib.util.module_from_spec(_spec)
sys.modules["exec02"] = ex
_spec.loader.exec_module(ex)
rp, R, cb = ex.rp, ex.R, ex.cb


# ═════════════════════════════════════════════════════════════════════════════════════════════
# a hand-built world
# ═════════════════════════════════════════════════════════════════════════════════════════════
def bdays(start: str, n: int) -> list:
    return [d.date() for d in pd.bdate_range(start, periods=n)]


CAL = bdays("2019-06-03", 260)
E_IDX = 150                                   # E = CAL[150]; D = CAL[149]
E, D_ = CAL[E_IDX].isoformat(), CAL[E_IDX - 1].isoformat()
E2, D2 = CAL[E_IDX + 2].isoformat(), CAL[E_IDX + 1].isoformat()
E_FAR = CAL[E_IDX + 25].isoformat()           # a later row of AAA's base OUTSIDE the 20-session window
FWD = [  # HHH after E (the first read's hand-computed trade: the third at session 3's close, the rest at session 8's open)
    (10.20, 10.50, 10.10, 10.40), (10.40, 10.80, 10.30, 10.70), (10.70, 11.00, 10.60, 10.90), (10.90, 11.20, 10.80, 11.10),
    (11.10, 11.40, 11.00, 11.30), (11.30, 11.60, 11.20, 11.50), (11.00, 11.10, 10.55, 10.60), (10.50, 10.60, 10.40, 10.45)]
FWD2 = [  # SSS after E2 (the re-entry): the third at session 3's close 21.1, then the breakeven stop on session 5
    (20.5, 20.8, 20.4, 20.7), (20.7, 21.0, 20.6, 20.9), (20.9, 21.2, 20.8, 21.1), (21.1, 21.3, 21.0, 21.2), (21.2, 21.3, 20.0, 20.1),
    (20.1, 20.2, 20.0, 20.1)]


def hhh_rows():
    rows = []
    for i, d in enumerate(CAL):
        if i < E_IDX:
            rows.append(("HHH", d, 10.0, 10.25, 9.75, 10.0, 1e6))          # ADR20 (H - L) / C = 0.05 exactly
        elif i == E_IDX:
            rows.append(("HHH", d, 10.0, 10.20, 9.95, 10.15, 2e6))
        elif i - E_IDX <= len(FWD):
            o, h, l, c = FWD[i - E_IDX - 1]
            rows.append(("HHH", d, o, h, l, c, 1e6))
        else:
            rows.append(("HHH", d, 10.45, 10.50, 10.40, 10.45, 1e6))
    return rows


def sss_rows():
    rows = []
    for i, d in enumerate(CAL):
        if i < E_IDX:
            bar = (20.0, 20.5, 19.5, 20.0)
        elif i == E_IDX:
            bar = (20.0, 20.4, 19.7, 19.8)
        elif i == E_IDX + 1:
            bar = (19.8, 19.95, 19.6, 19.9)
        elif i == E_IDX + 2:
            bar = (19.9, 20.6, 19.85, 20.5)
        elif i - E_IDX - 2 <= len(FWD2):
            bar = FWD2[i - E_IDX - 3]
        else:
            bar = (20.1, 20.15, 20.05, 20.1)
        rows.append(("SSS", d) + bar + (1e6,))
    return rows


def ggg_rows():
    rows = []
    for i, d in enumerate(CAL):
        bar = (30.0, 30.75, 29.25, 30.0) if i < E_IDX else ((30.6, 30.9, 30.2, 30.3) if i == E_IDX else (30.3, 30.4, 30.2, 30.3))
        rows.append(("GGG", d) + bar + (1e6,))
    return rows


def filler_rows(tk: str, base: float):
    return [(tk, d, base, base * 1.01, base * 0.99, base, 1e6) for d in CAL]


def write_export(path: Path, rows: list) -> None:
    with gzip.open(path, "wt") as fh:
        for t, d, o, h, l, c, v in rows:
            fh.write(f"{t},{d.isoformat()},{o},{h},{l},{c},{v}\n")


def hhh_minutes():
    m = []
    for k in range(5):
        m.append((k, 10.0, 10.05, 9.95 if k == 2 else 9.99, 10.0))
    m.append((5, 10.04, 10.10, 10.02, 10.08))
    for k in range(6, 390):
        m.append((k, 10.10, 10.20 if k == 200 else 10.15, 10.05, 10.12))
    return m


def sss_minutes_E():
    """ORH5 = 20.05, filled at minute 5 (20.05 x 1.001), stop 19.95 (minute 2); minute 100 touches 19.70 -> a day-0 stop at 19.95.
    The level entry (pivot 20.0) fills at minute 0 at 20.0 x 1.001, stop 19.99, and is stopped on day 0 at minute 2."""
    m = [(k, 20.0, 20.05, 19.95 if k == 2 else 19.99, 20.0) for k in range(5)]
    m.append((5, 20.04, 20.10, 20.02, 20.08))
    m.append((6, 20.10, 20.40, 20.05, 20.30))
    m += [(k, 20.2, 20.25, 20.15, 20.2) for k in range(7, 100)]
    m.append((100, 20.0, 20.0, 19.70, 19.75))
    m += [(k, 19.8, 19.85, 19.75, 19.8) for k in range(101, 390)]
    return m


def sss_minutes_E2():
    """The re-break: ORH5 = max(19.95, pivot 20.0) = 20.0, filled at minute 5 at 20.0 x 1.001, stop 19.85; no day-0 stop."""
    m = [(k, 19.9, 19.95, 19.85, 19.9) for k in range(5)]
    m.append((5, 19.95, 20.10, 19.90, 20.05))
    m += [(k, 20.3, 20.6, 20.25, 20.5) for k in range(6, 390)]
    return m


def ggg_minutes():
    """Opens ABOVE the level (30.6 > pivot 30.0) and fades: ORH5 = 30.9 never trades again (the first read's no-trigger class);
    the level entry fills at minute 0's OPEN 30.6 x 1.001 with the stop at minute 0's low 30.5."""
    m = [(0, 30.6, 30.9, 30.5, 30.7)] + [(k, 30.7, 30.8, 30.4, 30.5) for k in range(1, 5)]
    m += [(k, 30.4, 30.5, 30.2, 30.3) for k in range(5, 390)]
    return m


def aaa_minutes():
    m = [(k, 20.0, 20.05, 19.95, 20.0) for k in range(5)]
    m += [(k, 20.1, 20.2, 20.05, 20.15) for k in range(5, 390)]
    return m


def flat_minutes(px: float):
    return [(k, px, px * 1.01, px * 0.99, px) for k in range(390)]


def minute_bars(rows):
    return cb.minute_bars_from_lists([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows],
                                     [r[4] for r in rows], [100.0] * len(rows))


def write_minutes(path: Path, blocks: dict) -> None:
    lines = []
    for tk, rows in blocks.items():
        lines += [f"{tk}|{m}|{o}|{h}|{l}|{c}|100" for m, o, h, l, c in rows]
    with gzip.open(path, "wt") as fh:
        fh.write("\n".join(lines) + "\n")


def ev(ticker, **kw) -> "rp.Event":
    base = dict(era="A", ticker=ticker, D=D_, E=E, base_id=f"{ticker}|b", retrigger=0, pivot=10.0, adr20=0.05,
                year=CAL[E_IDX].year, month=E[:7], minutes_state="ok")
    base.update(kw)
    return rp.Event(**base)


@pytest.fixture()
def world(tmp_path):
    p = tmp_path / "export.csv.gz"
    rows = (filler_rows("SPY", 300.0) + filler_rows("QQQ", 200.0) + hhh_rows() + sss_rows() + ggg_rows() + filler_rows("AAA", 20.0)
            + filler_rows("BBB", 30.0))
    rows.sort(key=lambda r: (r[1], r[0]), reverse=True)
    write_export(p, rows)
    D, _info = rp.load_daily_subset(str(p))
    return SimpleNamespace(path=p, D=D)


def bars_of(D, tk, e_iso=E):
    bars, cidx = R.bars_for(D, D.tid[tk])
    return bars, cidx, R.locate_breakout_index(D.cal, cidx, e_iso)


def expected_hhh_r() -> float:
    fill = 10.05 * 1.001
    return ((10.90 - fill) / 3.0 + (10.50 - fill) * (2.0 / 3.0)) / (fill - 9.95)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# V1 — buy as it breaks out (the module's own `pivot` row): a gap fill vs a level fill
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_v1_reads_the_modules_pivot_row():
    assert ex.ENTRY_SETS["level"].variant == "pivot" and ex.ENTRY_SETS["level_tc"].variant == "pivot"
    assert ex.ENTRY_SETS["orh5"] == ex.EntrySet("orh5", "orh5", "ours", "skip")


def test_v1_gap_fill_at_the_open():
    mb = minute_bars(ggg_minutes())
    ent = cb.entry_variants(mb, pivot=30.0, adr20=0.05, day_high=30.9, day_low=30.2)
    lv = ent["pivot"]
    assert lv["status"] == "filled" and lv["fill_minute"] == 0
    assert lv["fill"] == pytest.approx(30.6 * 1.001, rel=1e-12)          # it opened above the level: the open, plus 0.1%
    assert lv["stop"] == 30.5     # the lowest low from 09:30 through the fill minute, its OWN low included: minute 0's low (§1.4b)
    assert ent["orh5"]["status"] == "no_trigger" and ent["orh5"]["reason"] == "no_minute_above_level"   # the 42-call class
    assert lv["day0"]["stopped"] and lv["day0"]["exit_price"] == 30.5     # minute 1's low 30.4 takes the stop


def test_v1_level_fill_on_the_first_minute_through_it():
    rows = [(k, 9.80, 9.90, 9.70 if k == 1 else 9.75, 9.85) for k in range(3)] + [(3, 9.92, 10.06, 9.90, 10.04)]
    rows += [(k, 10.05, 10.10, 10.00, 10.06) for k in range(4, 390)]
    mb = minute_bars(rows)
    lv = cb.entry_variants(mb, pivot=10.0, adr20=0.05, day_high=10.10, day_low=9.70)["pivot"]
    assert lv["status"] == "filled" and lv["fill_minute"] == 3
    assert lv["fill"] == pytest.approx(10.0 * 1.001, rel=1e-12)           # opened under the level: the level, plus 0.1%
    assert lv["stop"] == 9.70                                             # min low of minutes 0..3
    assert lv["width_pct"] == pytest.approx((10.01 - 9.70) / 10.01, rel=1e-12)


def test_v1_own_low_flag_cases():
    """§1.4b, print-only: (own_low, first_bar) for a fill or a too_wide abstain; None for anything else."""
    gg = minute_bars(ggg_minutes())
    ent = cb.entry_variants(gg, pivot=30.0, adr20=0.05, day_high=30.9, day_low=30.2)
    assert ex.own_low_flag(gg, ent["pivot"]) == (True, True)                 # a fill in minute 0: its stop IS minute 0's low
    assert ex.own_low_flag(gg, ent["orh5"]) is None                          # no_trigger
    rows = [(k, 9.80, 9.90, 9.70 if k == 1 else 9.75, 9.85) for k in range(3)] + [(3, 9.92, 10.06, 9.90, 10.04)]
    rows += [(k, 10.05, 10.10, 10.00, 10.06) for k in range(4, 390)]
    mb = minute_bars(rows)
    lv = cb.entry_variants(mb, pivot=10.0, adr20=0.05, day_high=10.10, day_low=9.70)["pivot"]
    assert lv["fill_minute"] == 3 and ex.own_low_flag(mb, lv) == (False, False)   # stop = minute 1's low, below minute 3's
    rows = [(k, 9.85, 9.90, 9.80, 9.85) for k in range(3)] + [(3, 9.85, 10.06, 9.60, 10.04)]   # the fill minute makes a new low
    rows += [(k, 10.05, 10.10, 10.00, 10.06) for k in range(4, 390)]
    mb = minute_bars(rows)
    kw = dict(pivot=10.0, day_high=10.10, day_low=9.60)
    lv = cb.entry_variants(mb, adr20=0.05, **kw)["pivot"]
    assert lv["status"] == "filled" and lv["stop"] == 9.60 and ex.own_low_flag(mb, lv) == (True, False)
    tw = cb.entry_variants(mb, adr20=0.01, **kw)["pivot"]                     # the same entry, too wide on a 1% ADR: flagged too
    assert tw["status"] == "abstain" and tw["reason"] == "too_wide" and ex.own_low_flag(mb, tw) == (True, False)
    # minute gaps: the day's first BAR is minute 2 (nothing traded at 09:30-09:31); a fill on it is first_bar by index
    rows = [(2, 10.2, 10.3, 10.1, 10.25), (4, 10.25, 10.3, 10.0, 10.1)] + [(k, 10.1, 10.2, 10.05, 10.1) for k in range(6, 390)]
    mb = minute_bars(rows)
    lv = cb.entry_variants(mb, pivot=10.0, adr20=0.05, day_high=10.3, day_low=10.0)["pivot"]
    assert lv["fill_minute"] == 2 and lv["stop"] == 10.1 and ex.own_low_flag(mb, lv) == (True, True)


def test_walk_event2_sets_own_low_on_the_level_sets_only(world):
    D = world.D
    bars, cidx, e = bars_of(D, "HHH")
    w = ex.walk_event2(ev("HHH"), bars, cidx, e, minute_bars(hhh_minutes()), breaks=None, adr_tc=0.06)
    assert w["sets"]["level"]["own_low"] == (True, True) and w["sets"]["level_tc"]["own_low"] == (True, True)
    assert all(w["sets"][s]["own_low"] is None for s in ("orh5", "orh5_tc", "orh5_cap"))


def test_without_first_bar_drops_minute_0_fills_only():
    res = {"a": {"sets": {"level_tc": {"own_low": (True, True)}}}, "b": {"sets": {"level_tc": {"own_low": (True, False)}}},
           "c": {"sets": {"level_tc": {"own_low": (False, False)}}}}
    T = {"a": 1, "b": 2, "c": 3}
    assert ex.without_first_bar(T, res, "level_tc") == {"b": 2, "c": 3}
    with pytest.raises(AssertionError):
        ex.without_first_bar({"a": 1}, {"a": {"sets": {"level_tc": {"own_low": None}}}}, "level_tc")


def test_v1_strict_cross_and_no_cross():
    rows = [(k, 9.9, 10.0, 9.8, 9.95) for k in range(390)]               # the high only TOUCHES the level
    ent = cb.entry_variants(minute_bars(rows), pivot=10.0, adr20=0.05, day_high=10.0, day_low=9.8)
    assert ent["pivot"]["status"] == "abstain" and ent["pivot"]["reason"] == "minute_high_below_pivot"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# V2 — his screen's ADR (TC2000) vs ours
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _bars(h, l, c):
    n = len(c)
    return cb.daily_bars_from_arrays(bdays("2020-01-01", n), np.asarray(c, float), np.asarray(h, float), np.asarray(l, float),
                                     np.asarray(c, float), np.ones(n))


def test_v2_adr_pair_known_answer():
    b = _bars([11.0] * 25, [10.0] * 25, [10.5] * 25)
    ours, tc = ex.adr_pair(b, 24)
    assert ours == pytest.approx(1.0 / 10.5, rel=1e-12) and tc == pytest.approx(0.1, rel=1e-12)
    # a window of two kinds of bars, ending at D = index 21 (bars 2..21): 10 of each
    h = [100.0, 100.0] + [12.0, 22.0] * 10 + [999.0] * 3
    l = [1.0, 1.0] + [10.0, 20.0] * 10 + [1.0] * 3
    c = [50.0, 50.0] + [11.0, 21.0] * 10 + [500.0] * 3
    ours, tc = ex.adr_pair(_bars(h, l, c), 21)
    assert ours == pytest.approx((2 / 11 + 2 / 21) / 2, rel=1e-12)
    assert tc == pytest.approx((12 / 10 + 22 / 20) / 2 - 1.0, rel=1e-12)
    with pytest.raises(ValueError):
        ex.adr_pair(_bars(h, l, c), 18)                                  # fewer than 20 bars ending D


def test_v2_tc2000_never_below_ours():
    rng = np.random.default_rng(1)
    for _ in range(50):
        c = rng.uniform(5, 50, 20)
        o = c * rng.uniform(0.95, 1.05, 20)
        h = np.maximum(o, c) * rng.uniform(1.0, 1.1, 20)
        l = np.minimum(o, c) * rng.uniform(0.9, 1.0, 20)
        ours, tc = ex.adr_pair(_bars(h, l, c), 19)
        assert tc >= ours - 1e-15


def test_v2_too_wide_on_ours_fills_on_tc2000_same_fill():
    """ORH5 width 1.09%: too wide on our ADR 1.0%, inside TC2000's 1.2% -> the same fill / stop / day-0 walk, only the gate differs."""
    mb = minute_bars(hhh_minutes())
    kw = dict(pivot=10.0, day_high=10.20, day_low=9.95)
    ours = cb.entry_variants(mb, adr20=0.010, **kw)["orh5"]
    tc = cb.entry_variants(mb, adr20=0.012, **kw)["orh5"]
    assert ours["status"] == "abstain" and ours["reason"] == "too_wide"
    assert tc["status"] == "filled"
    assert (tc["fill"], tc["stop"], tc["fill_minute"]) == (ours["fill"], ours["stop"], ours["fill_minute"])
    assert tc["day0"] == cb.day0_walk(mb, fill_minute=tc["fill_minute"], stop=tc["stop"])
    wide = cb.entry_variants(mb, adr20=0.05, **kw)["orh5"]                # a fill under ours is the same fill under any wider ADR
    assert wide["status"] == "filled" and (wide["fill"], wide["stop"]) == (tc["fill"], tc["stop"])


def test_v2_walk_event2_uses_tc_only_for_the_gate(world):
    D = world.D
    bars, cidx, e = bars_of(D, "HHH")
    mb = minute_bars(hhh_minutes())
    x = ev("HHH", adr20=0.010)
    w = ex.walk_event2(x, bars, cidx, e, mb, breaks=None, adr_tc=0.012)
    assert w["sets"]["orh5"]["raw"] is None and w["sets"]["orh5"]["entry"]["reason"] == "too_wide"
    assert w["sets"]["orh5_tc"]["raw"] is not None
    assert w["sets"]["orh5_tc"]["raw"]["realized_r"] == pytest.approx(expected_hhh_r(), rel=1e-12)


def test_v2b_cap_not_skip_equals_the_runners(world):
    D = world.D
    bars, cidx, e = bars_of(D, "HHH")
    mb = minute_bars(hhh_minutes())
    adr = 0.005
    ent = cb.entry_variants(mb, pivot=10.0, adr20=adr, day_high=10.20, day_low=9.95)["orh5"]
    assert ent["reason"] == "too_wide"
    fwd, _cut = cb.forward_window(bars, cidx, e, ex.HORIZON)
    ref = R.cap_sensitivity(ent, mb, closes_before=bars.c[:e + 1], fwd=fwd, adr20=adr, horizon=ex.HORIZON)
    capped = ex.cap_not_skip(ent, mb, adr)
    assert capped["stop"] == pytest.approx(ent["fill"] * (1 - adr), rel=1e-15) == ref["stop"]
    mine = cb.walk_arms(capped, closes_before=bars.c[:e + 1], fwd=fwd, adr20=adr, horizon=ex.HORIZON,
                        arms={ex.PRIMARY_ARM: cb.ARMS[ex.PRIMARY_ARM]})[ex.PRIMARY_ARM]
    assert mine["status"] == ref["status"] and mine["realized_r"] == pytest.approx(ref["realized_r"], rel=1e-12)
    w = ex.walk_event2(ev("HHH", adr20=adr), bars, cidx, e, mb, breaks=None, adr_tc=adr * 1.01)
    assert w["sets"]["orh5_cap"]["capped"] and w["sets"]["orh5_cap"]["raw"]["realized_r"] == pytest.approx(ref["realized_r"], rel=1e-12)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# V0 — the walk is the first read's
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_walk_event2_v0_equals_the_first_reads_walk_event(world):
    D = world.D
    for tk, mins, piv in (("HHH", hhh_minutes(), 10.0), ("SSS", sss_minutes_E(), 20.0), ("GGG", ggg_minutes(), 30.0)):
        bars, cidx, e = bars_of(D, tk)
        mb = minute_bars(mins)
        x = ev(tk, pivot=piv)
        ref = rp.walk_event(x, bars, cidx, e, mb)
        mine = ex.walk_event2(x, bars, cidx, e, mb, breaks=None, adr_tc=0.06)
        assert mine["sets"]["orh5"]["entry"] == ref["orh5"]["entry"]
        a, b = mine["sets"]["orh5"]["raw"], ref["orh5"]["arms"].get(ex.PRIMARY_ARM)
        assert (a is None) == (b is None)
        if a is not None:
            assert a == b
        assert mine["n_fwd"] == ref["n_fwd"] and mine["break_cut"] == ref["break_cut"]
    bars, cidx, e = bars_of(D, "HHH")
    w = ex.walk_event2(ev("HHH"), bars, cidx, e, minute_bars(hhh_minutes()), breaks=None, adr_tc=0.06)
    assert w["sets"]["orh5"]["raw"]["realized_r"] == pytest.approx(expected_hhh_r(), rel=1e-12)
    lv = w["sets"]["level"]["entry"]                                      # HHH under V1: minute 0 at the level, then a day-0 stop
    assert lv["fill_minute"] == 0 and lv["fill"] == pytest.approx(10.01, rel=1e-12) and lv["stop"] == 9.99
    assert w["sets"]["level"]["raw"]["status"] == "stopped_day0"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# V3 — the re-entry chain
# ═════════════════════════════════════════════════════════════════════════════════════════════
CC = bdays("2020-01-01", 60)


def _t(e_ci, status, held):
    return SimpleNamespace(e_ci=e_ci, status=status, sessions_held=held)


def _k(i):
    return ("A", "XXX", CC[i].isoformat())


def test_v3_chain_known_answer_max_two_each_its_own_trade():
    T = {_k(10): _t(10, "stopped", 2),             # the call: stopped out on session 2 -> exit day CC[12]; window to CC[30]
         _k(11): _t(11, "trailed", 5),             # a break BEFORE the exit day: never a re-entry (and not counted)
         _k(15): _t(15, "stopped", 1),             # re-entry 1 (CC[13] refused, CC[14] not filled); exit day CC[16]
         _k(16): _t(16, "trailed", 5),             # ON that exit day: not strictly after it
         _k(17): _t(17, "stopped_day0", 0),        # re-entry 2 (stopped again)
         _k(19): _t(19, "trailed", 9),             # a third eligible re-entry: NOT taken (at most 2)
         _k(40): _t(40, "trailed", 9)}             # outside the window
    rows = [(CC[i].isoformat(), _k(i)) for i in (11, 12, 13, 14, 15, 16, 17, 19, 40)]
    refuse = lambda k: "data_excluded" if k == _k(13) else None           # noqa: E731
    counts = Counter()
    ch = ex.chain_of(_k(10), T, rows, CC, refuse, counts)
    assert ch == [_k(10), _k(15), _k(17)]
    assert counts == Counter({"passed_data_excluded": 1, "passed_not_filled": 1, "reentry_1": 1, "reentry_2": 1})


def test_v3_chain_ends_on_a_non_stop_exit_and_needs_a_fill():
    T = {_k(10): _t(10, "trailed", 4), _k(15): _t(15, "stopped", 1)}
    rows = [(CC[15].isoformat(), _k(15))]
    assert ex.chain_of(_k(10), T, rows, CC, lambda k: None, Counter()) == [_k(10)]     # a trail exit earns no retry
    assert ex.chain_of(_k(9), T, rows, CC, lambda k: None, Counter()) == []            # an unfilled call has no campaign
    T2 = {_k(10): _t(10, "stopped", 0), _k(15): _t(15, "trailed", 3), _k(31): _t(31, "trailed", 3)}
    rows2 = [(CC[31].isoformat(), _k(31)), (CC[30].isoformat(), _k(30))]
    assert ex.chain_of(_k(10), T2, sorted(rows2), CC, lambda k: None, Counter()) == [_k(10)]   # CC[31] is past E + 20; CC[30] unfilled
    T3 = {_k(10): _t(10, "stopped", 0), _k(30): _t(30, "trailed", 3)}
    assert ex.chain_of(_k(10), T3, [(CC[30].isoformat(), _k(30))], CC, lambda k: None, Counter()) == [_k(10), _k(30)]  # E + 20 is in


def test_v3_control_rule_and_data_refusals():
    X = {"walk": {_k(1): object(), _k(2): object()}, "lab": {"A": {_k(1): True, _k(2): False}}}
    rf_c = ex.make_refuse(X, "A", control_rule=True)
    rf_h = ex.make_refuse(X, "A", control_rule=False)
    assert rf_c(_k(1)) == "control_rule" and rf_c(_k(2)) is None and rf_c(_k(3)) == "data_excluded"
    assert rf_h(_k(1)) is None and rf_h(_k(3)) == "data_excluded"


def _trade(tk, e_ci, width, legs, path_c):
    fill = 100.0
    return rp.Trade(key=("A", tk, CC[e_ci].isoformat()), ticker=tk, era="A", e_ci=e_ci, fill_minute=5, fill=fill,
                    stop=fill * (1 - width), width=width, status="stopped", mature=True, realized_r=0.0, r_slip=(0.0, 0.0, 0.0),
                    sessions_held=max(lg[5] for lg in legs), legs=legs, path_c=np.asarray(path_c, dtype=float), year=2020,
                    month=CC[e_ci].isoformat()[:7])


def test_v3_union_dedupes_and_each_reentry_enters_the_account():
    """A's campaign re-enters at B, which is ALSO one of the group's own calls: B enters the account once. C re-enters after B.
    Each trade risks 1% (width 10% -> a 10% position, under the 20% cap): -1% -1% then C +20% x 10% = +2%."""
    A = _trade("XXX", 5, 0.10, [(6, rp.ORDER_INTRADAY, 1.0, 90.0, "stop", 1)], [100.0, 90.0])
    B = _trade("XXX", 8, 0.10, [(9, rp.ORDER_INTRADAY, 1.0, 90.0, "stop", 1)], [100.0, 90.0])
    C = _trade("XXX", 11, 0.10, [(12, rp.ORDER_OPEN, 1.0, 120.0, "trail", 1)], [100.0, 120.0])
    T = {A.key: A, B.key: B, C.key: C}
    camps = {A.key: [A.key, B.key, C.key], B.key: [B.key, C.key]}
    tr = ex.union_trades(camps, [A.key, B.key], T)
    assert [t.key for t in tr] == [A.key, B.key, C.key]
    sim = rp.simulate(tr, rp.PRIMARY_CONFIG, CC, 4)
    assert sim["counts"]["entered"] == 3
    assert sim["final"] == pytest.approx(0.99 * 0.99 * (1 + 0.10 * 0.20), rel=1e-12)


def test_v3_campaign_r_is_the_sum_of_its_trades():
    t1 = SimpleNamespace(mature=True, r_slip=(-1.0, -1.1, -1.2))
    t2 = SimpleNamespace(mature=True, r_slip=(6.0, 5.9, 5.8))
    t3 = SimpleNamespace(mature=False, r_slip=(2.0, 2.0, 2.0))
    T = {"a": t1, "b": t2, "c": t3}
    evs = [SimpleNamespace(era="A", ticker="X", E="1"), SimpleNamespace(era="A", ticker="Y", E="2"),
           SimpleNamespace(era="A", ticker="Z", E="3")]
    camps = {("A", "X", "1"): ["a", "b"], ("A", "Y", "2"): ["a", "c"], ("A", "Z", "3"): []}
    vals, used, nf, nm = ex.campaign_values(evs, camps, T)
    assert vals == [5.0] and nf == 2 and nm == 1 and used == [evs[0]]     # a campaign holding an open mark is in no number
    assert ex.campaign_values(evs, camps, T, slip_i=1)[0] == [pytest.approx(4.8)]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# V4 — the 30% cap
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_v4_cap30_known_answer():
    """Width 2%: 1% risk wants a 50% position; the cap makes it 20% (primary), 30% (V4); 0.5% risk wants 25% (V4b). +10% on the
    position -> equity +2% / +3% / +2.5%."""
    t = _trade("XXX", 5, 0.02, [(7, rp.ORDER_CLOSE, 1.0, 110.0, "partial", 2)], [100.0, 105.0, 110.0])
    out = {cfg.name: rp.simulate([t], cfg, CC, 4)["final"] for cfg in (rp.PRIMARY_CONFIG, ex.CAP30, ex.CAP30_R05)}
    assert out == pytest.approx({"primary": 1.02, "cap_30": 1.03, "cap_30_risk_0.5": 1.025}, rel=1e-12)
    assert ex.VMAP["V4"].cfg == rp.CONFIGS[4] and rp.CONFIGS[4].name == "cap_30"         # V4 = the first read's cap_30 row
    assert ex.VMAP["COMBINED"].cfg is ex.CAP30 and ex.VMAP["COMBINED"].entry == "level_tc" and ex.VMAP["COMBINED"].chain


def test_variant_table_is_the_registration():
    assert [v.name for v in ex.VARIANTS] == ["V0", "V1", "V2", "V2b", "V3", "V4", "V4b", "COMBINED", "COMBINED_r05"]
    assert {v.name for v in ex.VARIANTS if v.beside} == {"V2b", "V4b", "COMBINED_r05"}
    assert ex.VMAP["V0"].cfg is rp.PRIMARY_CONFIG and not ex.VMAP["V0"].chain and ex.VMAP["V0"].entry == "orh5"
    assert ex.VMAP["V3"].chain and ex.VMAP["V3"].entry == "orh5"
    assert (ex.REENTRY_WINDOW, ex.MAX_REENTRIES, ex.STOP_OUT) == (20, 2, frozenset({"stopped", "stopped_day0"}))
    assert ex.BAND_KEY == "qm_replay|band|A|same-day (registered)" and ex.FIRST_DIFF_KEY == "qm_replay|A|orh5|p33_s3_t10|mean R"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the fork
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_fork_exec():
    assert ex.fork_exec({2020: 0.80, 2021: 0.50}, 0.05)[0] == "EXPLAINED"
    assert ex.fork_exec({2020: 0.80, 2021: 0.499}, 0.0)[:3] == ("NEXT GAPS", False, True)
    assert ex.fork_exec({2020: 0.80, 2021: 0.60}, 0.055)[:3] == ("NEXT GAPS", True, False)
    assert ex.fork_exec({2020: 0.80}, 0.0)[0] == "NEXT GAPS"                            # a year with no return is not met
    assert ex.fork_exec({2019: 2.0, 2020: 2.0, 2021: 0.1}, 0.0)[0] == "NEXT GAPS"        # BOTH 2020 and 2021, not 2 of 5
    with pytest.raises(ValueError):
        ex.fork_exec({2020: 1.0, 2021: 1.0}, float("nan"))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the outcome-free facts
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_history_reason(world):
    D = world.D
    bars, cidx, _e = bars_of(D, "HHH")
    assert ex.history_reason(ev("HHH"), bars, cidx, D.cal) is None
    assert ex.history_reason(ev("HHH", D=CAL[E_IDX - 2].isoformat()), bars, cidx, D.cal) == "D_not_the_bar_before_E"
    assert ex.history_reason(ev("HHH", E=CAL[100].isoformat(), D=CAL[99].isoformat()), bars, cidx, D.cal) == "history_not_contiguous"
    hole = cidx[:-5].copy()                                                          # room at the end of the calendar
    hole[E_IDX - 10:] += 1                                                              # a missing session inside the 130
    b2 = SimpleNamespace(dates=[D.cal[k] for k in hole])
    assert ex.history_reason(ev("HHH", E=D.cal[int(hole[E_IDX])].isoformat(), D=D.cal[int(hole[E_IDX - 1])].isoformat()),
                             b2, hole, D.cal) == "history_not_contiguous"
    assert ex.history_reason(ev("HHH", E=D.cal[int(hole[E_IDX - 10]) - 1].isoformat()), b2, hole, D.cal) == "no_bar_on_E"


def test_event_facts(world):
    D = world.D
    qqq = R.bars_for(D, D.tid["QQQ"])
    files = {E: "x"}
    x = ev("HHH")
    ex.event_facts(x, D, qqq, {}, {(E, "HHH"): "ok"}, files)
    assert x.keep and x.minutes_state == "ok" and not x.break_pre and x.qqq == "mixed"   # QQQ flat: neither above nor below both
    y = ev("HHH")
    brk = {"HHH": np.array([CAL[E_IDX - 5].toordinal()])}
    ex.event_facts(y, D, qqq, brk, {(E, "HHH"): "ok"}, files)
    assert y.break_pre and not y.keep
    z = ev("HHH")
    ex.event_facts(z, D, qqq, {}, {}, files)
    assert z.minutes_state == "missing" and not z.keep
    w = ev("HHH")
    ex.event_facts(w, D, qqq, {}, {(E, "HHH"): "empty"}, {})
    assert w.minutes_state == "empty" and w.keep


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock — line-anchored, exactly once
# ═════════════════════════════════════════════════════════════════════════════════════════════
M = ex.FREEZE_MARKER


def test_freeze_lock_ignores_an_inline_mention_and_hashes_up_to_the_marker_line(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text(f"# body\nthe lock pastes pins under `{M}` below\nmore rules\n\n{M}\n")
    body = doc.read_bytes().split(b"\n" + M.encode() + b"\n")[0] + b"\n"
    import hashlib
    assert ex.doc_body_sha(str(doc)) == hashlib.sha256(body).hexdigest()
    p = {"a": "aaa", "doc_body": ex.doc_body_sha(str(doc))}
    assert ex.freeze_missing(str(doc), p) == ["a", "doc_body"]
    doc.write_text(f"# body\nthe lock pastes pins under `{M}` below\nmore rules\n\n{M}\n- a: aaa\n- doc_body: {p['doc_body']}\n")
    assert ex.freeze_missing(str(doc), {**p, "doc_body": ex.doc_body_sha(str(doc))}) == []
    # an edit BETWEEN the inline mention and the marker line changes the hash: refused
    doc.write_text(f"# body\nthe lock pastes pins under `{M}` below\nmore rules EDITED\n\n{M}\n- a: aaa\n- doc_body: {p['doc_body']}\n")
    assert ex.freeze_missing(str(doc), {**p, "doc_body": ex.doc_body_sha(str(doc))}) == ["doc_body"]


def test_freeze_lock_refuses_zero_or_two_marker_lines(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text(f"# body\n\n{M}\n- a: aaa\n\n{M}\n- a: aaa\n")
    assert ex.freeze_missing(str(doc), {"a": "aaa"}) == ["a"]
    doc.write_text(f"# body mentions `{M}` inline only\n- a: aaa\n")
    assert ex.freeze_missing(str(doc), {"a": "aaa"}) == ["a"]
    doc.write_text(f"# body\n{M}  \n- a: aaa\n")                                    # trailing blanks still a marker line
    assert ex.freeze_missing(str(doc), {"a": "aaa"}) == []


def test_the_registration_doc_mentions_the_marker_only_as_its_line():
    """The doc's body never carries the literal marker text: exactly one line-anchored marker, no other occurrence above it."""
    if not os.path.exists(ex.DOC):
        pytest.skip("registration not written yet")
    raw = Path(ex.DOC).read_bytes()
    sp = ex.marker_spans(raw)
    assert len(sp) == 1
    assert raw[:sp[0][0]].count(M.encode()) == 0


def test_next_gaps_list_is_the_registrations_word_for_word():
    """FORK_TEXT's NEXT GAPS list = the doc's §7 NEXT GAPS row, word for word; the stop lever left untested is in it and in §11."""
    assert ex.NEXT_GAPS in ex.FORK_TEXT["NEXT GAPS"]
    assert ex.NEXT_GAPS.startswith("stop placement beyond one ADR / the structural stop, ")
    if not os.path.exists(ex.DOC):
        pytest.skip("registration not written yet")
    raw = Path(ex.DOC).read_bytes()
    body = raw[:ex.marker_spans(raw)[0][0]].decode()
    s7 = body.split("## 7.")[1].split("\n## 8.")[0]
    row = [ln for ln in s7.splitlines() if "**NEXT GAPS**" in ln]
    assert len(row) == 1 and ex.NEXT_GAPS in row[0]
    s11 = body.split("## 11.")[1]
    assert "stop placement beyond one adr / the structural stop" in s11.lower()


def test_widest_bar_and_the_adr_gap_listing(world):
    h = [11.0] * 25
    l = [10.0] * 25
    l[20] = 1.0                                                                       # one bad low inside the window ending D = 24
    b = _bars(h, l, [10.5] * 25)
    d, w = ex.widest_bar(b, 24)
    assert d == b.dates[20].isoformat() and w == pytest.approx(10.0, rel=1e-12)
    ours, tc = ex.adr_pair(b, 24)
    assert 100 * (tc - ours) > 40                                                     # one bad low -> a gap of tens of points
    D = world.D
    k1, k2, k3 = ("A", "HHH", E), ("A", "SSS", E), ("A", "GGG", E)
    X = {"walk": {k1: ev("HHH", his=True), k2: ev("SSS", ctl=True), k3: ev("GGG")}}
    adr = {k1: (0.05, 0.08), k2: (0.05, 0.065), k3: (0.05, 0.051)}                     # 3, 1.5 and 0.1 points
    S = {"Ds": {"A": D}}
    got = ex.adr_gap_events(S, X, adr, "A")
    assert list(got) == ["his", "ctl", "post", "reentry rows"]
    assert [r[:3] for r in got["his"]] == [(pytest.approx(3.0), "HHH", E)]
    assert got["ctl"] == [] and got["post"] == [] and got["reentry rows"] == []          # 1.5 is under 2; GGG's 0.1 too
    assert got["his"][0][4] == pytest.approx(10.25 / 9.75 - 1, rel=1e-12)              # HHH's bars before E: H / L = 10.25 / 9.75


@pytest.fixture()
def lock_sandbox(tmp_path, monkeypatch):
    f = tmp_path / "input.txt"
    f.write_text("x")
    doc = tmp_path / "doc.md"
    first_doc = tmp_path / "first.md"
    first_doc.write_text("first body\n" + M + "\n")
    monkeypatch.setattr(ex, "FILES", {"inp": str(f)})
    monkeypatch.setattr(ex, "FIRST", {"first_printout": str(f)})
    monkeypatch.setattr(ex, "CODE", {})
    monkeypatch.setattr(ex, "PINNED", {"inp": rp.sha(str(f))})
    monkeypatch.setattr(rp, "DOC", str(first_doc))
    monkeypatch.setattr(ex, "FIRST_DOC_BODY", rp.doc_body_sha(str(first_doc)))
    monkeypatch.setattr(ex, "DOC", str(doc))
    monkeypatch.setattr(ex, "PRINTOUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(ex, "DRY_PRINTOUT", str(tmp_path / "dry.txt"))
    monkeypatch.setattr(ex, "STOPPED", str(tmp_path / "stopped.txt"))
    monkeypatch.setattr(ex, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setitem(rp.FILES, "done_A", str(f))
    monkeypatch.setitem(rp.FILES, "done_B", str(f))
    monkeypatch.setattr(rp, "load_all", lambda say, dry: {"evs": []})
    monkeypatch.setattr(rp, "describe_population", lambda say, S: None)
    monkeypatch.setattr(ex, "prepare", lambda S, done: {"walk": {}, "facts": Counter()})
    monkeypatch.setattr(ex, "adr_facts", lambda S, X: ({}, Counter()))
    monkeypatch.setattr(ex, "describe_superset", lambda *a: None)
    monkeypatch.setattr(ex, "EXPECT_SUPERSET", {})
    ran = []
    monkeypatch.setattr(ex, "run_exec", lambda S, X, adr, say: ran.append(1))
    return SimpleNamespace(doc=doc, f=f, first_doc=first_doc, ran=ran, tmp=tmp_path)


def test_real_run_refuses_until_frozen_then_runs(lock_sandbox):
    sb = lock_sandbox
    sb.doc.write_text(f"# registration\n\n{M}\n")
    assert ex.main([]) == 2 and not sb.ran
    p = ex.pins({"A": [], "B": []})
    sb.doc.write_text(f"# registration\n\n{M}\n" + "".join(f"- {k}: {v}\n" for k, v in p.items()))
    assert ex.main(["--dry-run"]) == 0 and not sb.ran
    assert ex.main([]) == 0 and sb.ran == [1]
    os.remove(ex.PRINTOUT)


def test_real_run_refuses_a_doc_edited_after_the_pin(lock_sandbox):
    sb = lock_sandbox
    sb.doc.write_text(f"# registration\n\n{M}\n")
    p = ex.pins({"A": [], "B": []})
    sb.doc.write_text(f"# registration, EDITED after the pin\n\n{M}\n" + "".join(f"- {k}: {v}\n" for k, v in p.items()))
    assert ex.main([]) == 2 and not sb.ran


def test_real_run_refuses_when_an_output_exists(lock_sandbox):
    sb = lock_sandbox
    Path(ex.PRINTOUT).write_text("already ran")
    assert ex.main([]) == 2 and not sb.ran
    os.remove(ex.PRINTOUT)
    os.makedirs(ex.OUT_DIR, exist_ok=True)
    Path(ex.OUT_DIR, "chains.tsv").write_text("x")
    assert ex.main([]) == 2 and not sb.ran


def test_real_run_refuses_on_drift_of_an_input_or_the_first_doc(lock_sandbox):
    sb = lock_sandbox
    sb.first_doc.write_text("first body EDITED\n" + M + "\n")
    assert ex.main(["--dry-run"]) == 2 and not sb.ran
    sb.first_doc.write_text("first body\n" + M + "\n")
    sb.f.write_text("changed")
    assert ex.main(["--dry-run"]) == 2 and not sb.ran


def test_pins_cover_the_first_read_and_this_module():
    assert set(ex.FIRST) == {"first_trades", "first_account_his", "first_account_band", "first_printout"}
    assert set(ex.FIRST) <= set(ex.FILES) and set(rp.FILES) <= set(ex.FILES)
    assert {"exec_module", "exec_tests", "replay_module", "replay_tests", "runner", "cb_module", "constants"} <= set(ex.CODE)
    assert ex.PINNED["replay_module"] == ex.FIRST_MODULE_SHA and ex.PINNED["replay_tests"] == ex.FIRST_TESTS_SHA
    assert rp.sha(rp.CODE["replay_module"]) == ex.FIRST_MODULE_SHA                     # the imported first read IS the frozen one


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the baseline-parity gate's readers
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_parse_first_printout_matches_the_first_reads_formats():
    txt = ("- RE-ENTRIES (counted, never walked): of 134 his-call trades stopped out, 91 have a later break of the same base after the "
           "exit day and within 20 sessions of E (358 such breaks; 33 of them are themselves his calls)\n"
           "- mean R: DATE-MATCHED +0.543 [-0.132, +1.424] | beside: stratum-only +0.1 [-0.2, +0.3]\n")
    got = ex.parse_first_printout(txt)
    assert got == {"reentry": (134, 91, 358, 33), "diff": ("+0.543", "-0.132", "+1.424")}
    with pytest.raises(ValueError):
        ex.parse_first_printout("nothing")
    src = Path(rp.__file__).read_text()                                                # the strings come from the frozen module
    assert "his-call trades stopped out, {n_with} have a later break of the same base after the" in src
    assert "- {meas}: DATE-MATCHED {d['matched']:+.3f} [{d['m_lo']:+.3f}, {d['m_hi']:+.3f}]" in src


def test_parity_trades_detects_a_changed_trade(tmp_path):
    cols = ["era", "ticker", "E", "variant", "entry_status", "entry_reason", "fill", "stop", "fill_minute", "arm", "status", "mature",
            "sessions_held", "realized_r"]
    rows = [["A", "HHH", E, "orh5", "filled", "", "10.06005", "9.95", "5", "p33_s3_t10", "trailed", "1", "8", "4.123456789"],
            ["A", "HHH", E, "orh5", "filled", "", "10.06005", "9.95", "5", "pp", "trailed", "1", "8", "9.9"],
            ["A", "GGG", E, "orh5", "no_trigger", "no_minute_above_level", "", "", "", "", "", "", "", ""]]
    p = tmp_path / "t.tsv.gz"
    with gzip.open(p, "wt") as fh:
        fh.write("\t".join(cols) + "\n" + "".join("\t".join(r) + "\n" for r in rows))
    keys = {("A", "HHH", E), ("A", "GGG", E)}
    res = {("A", "HHH", E): {"sets": {"orh5": {"entry": {"status": "filled", "reason": None}}}},
           ("A", "GGG", E): {"sets": {"orh5": {"entry": {"status": "no_trigger", "reason": "no_minute_above_level"}}}}}
    t = SimpleNamespace(fill=10.06005, stop=9.95, realized_r=4.1234567891, fill_minute=5, status="trailed", mature=True, sessions_held=8)
    assert ex.parity_trades(str(p), keys, res, {("A", "HHH", E): t}) == []
    t.realized_r = 4.1235
    assert len(ex.parity_trades(str(p), keys, res, {("A", "HHH", E): t})) == 1
    t.realized_r = 4.1234567891
    assert ex.parity_trades(str(p), keys | {("A", "ZZZ", E)}, res, {("A", "HHH", E): t})[0].startswith("event set differs")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# end to end: the first read's run_replay on a world, then this read's run_exec on the SAME world (the parity gate must pass)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def e2e_world(world, tmp_path):
    D = world.D
    mdir = tmp_path / "minutes"
    mdir.mkdir()
    write_minutes(mdir / f"{E}.psv.gz", {"HHH": hhh_minutes(), "SSS": sss_minutes_E(), "GGG": ggg_minutes(), "AAA": aaa_minutes(),
                                        "BBB": flat_minutes(30.0)})
    write_minutes(mdir / f"{E2}.psv.gz", {"SSS": sss_minutes_E2()})
    bars, _c, e2 = bars_of(D, "SSS", E2)
    adr2 = ex.adr_pair(bars, e2 - 1)[0]
    evs = [ev("HHH", strict=True, first_of_base=True, his=True), ev("SSS", pivot=20.0, his=True, first_of_base=True),
           ev("GGG", pivot=30.0, his=True, first_of_base=True),
           ev("AAA", pivot=20.1, adr20=0.02, ctl=True, base_id="AAA|1"),
           ev("BBB", pivot=29.0, adr20=0.02, ctl=True, base_id="BBB|1", retrigger=1)]
    rows = [("HHH", E, D_, "HHH|b", 0, 10.0, 0.05, True), ("SSS", E, D_, "SSS|b", 0, 20.0, 0.05, True),
            ("SSS", E2, D2, "SSS|b", 1, 20.0, adr2, True), ("GGG", E, D_, "GGG|b", 0, 30.0, 0.05, True),
            ("AAA", E, D_, "AAA|1", 0, 20.1, 0.02, False), ("AAA", E_FAR, CAL[E_IDX + 24].isoformat(), "AAA|1", 1, 20.1, 0.02, False),
            ("BBB", E, D_, "BBB|1", 1, 29.0, 0.02, False)]
    ns = SimpleNamespace(name="A", ticker=np.array([r[0] for r in rows]), E=np.array([r[1] for r in rows]),
                         D=np.array([r[2] for r in rows]), base_id=np.array([r[3] for r in rows]),
                         retrigger=np.array([r[4] for r in rows]), pivot=np.array([r[5] for r in rows]),
                         adr20=np.array([r[6] for r in rows]), cls={"lab_by_E": np.array([r[7] for r in rows])})
    empty = SimpleNamespace(name="B", ticker=np.array([], dtype=str), E=np.array([], dtype=str), D=np.array([], dtype=str),
                            base_id=np.array([], dtype=str), retrigger=np.array([], dtype=int), pivot=np.array([]), adr20=np.array([]),
                            cls={"lab_by_E": np.array([], dtype=bool)})
    DB, _ = rp.load_daily_subset(str(world.path), keep={"QQQ"})
    S = {"evs": evs, "Ds": {"A": D, "B": DB}, "files": {"A": {E: mdir / f"{E}.psv.gz", E2: mdir / f"{E2}.psv.gz"}, "B": {}},
         "guards": {"A": {}, "B": {}}, "eras": {"A": ns, "B": empty},
         "qqq": {"A": R.bars_for(D, D.tid["QQQ"]), "B": R.bars_for(DB, DB.tid["QQQ"])}}
    done = {"A": {(E, t): "ok" for t in ("HHH", "SSS", "GGG", "AAA", "BBB")} | {(E2, "SSS"): "ok"}, "B": {}}
    return S, done


def test_run_exec_end_to_end_with_the_parity_gate(world, tmp_path, monkeypatch):
    S, done = e2e_world(world, tmp_path)
    flags = tmp_path / "flags.tsv"
    flags.write_text("check\tklass\tticker\tdate\n")
    monkeypatch.setitem(rp.FILES, "flags_A", str(flags))
    monkeypatch.setattr(rp, "OUT_DIR", str(tmp_path / "out1"))
    monkeypatch.setattr(rp, "BAND_DRAWS", 3)
    monkeypatch.setattr(rp, "run_g8", lambda era, path, out: (0, 0))
    # 1) the FROZEN first read on this world -> its outputs (the parity gate's targets)
    say1 = rp.Say()
    rp.run_replay(S, say1)
    first_txt = tmp_path / "01_replay.txt"
    say1.write(str(first_txt))
    assert "of 1 his-call trades stopped out, 1 have a later break" in first_txt.read_text()   # SSS (ORH5 day-0 stop) re-breaks at E2
    # 2) this read on the same world
    monkeypatch.setattr(ex, "OUT_DIR", str(tmp_path / "out2"))
    monkeypatch.setattr(ex, "BAND_DRAWS", 3)
    monkeypatch.setattr(ex, "FIRST", {"first_trades": str(tmp_path / "out1" / "trades.tsv.gz"),
                                      "first_account_his": str(tmp_path / "out1" / "account_his.tsv"),
                                      "first_account_band": str(tmp_path / "out1" / "account_band.tsv"),
                                      "first_printout": str(first_txt)})
    X = ex.prepare(S, done)
    assert X["facts"]["A_reentry_rows"] == 1 and X["facts"]["A_new_rows_kept"] == 1     # SSS@E2 in; AAA@E+25 outside the window
    assert ("A", "SSS", E2) in X["walk"] and ("A", "AAA", E_FAR) not in X["walk"]
    adr, bad = ex.adr_facts(S, X)
    assert not bad and adr[("A", "HHH", E)][0] == pytest.approx(0.05, abs=1e-12)
    assert adr[("A", "HHH", E)][1] == pytest.approx(10.25 / 9.75 - 1, rel=1e-12)
    say2 = rp.Say()
    ex.run_exec(S, X, adr, say2)
    text = "\n".join(say2.lines)
    for s in ("BASELINE PARITY", "THE FORK", "VERDICT", "CONTROL BAND", "V3 re-entry chains", "per EVENT", "Era B"):
        assert s in text, s
    ch = pd.read_csv(tmp_path / "out2" / "chains.tsv", sep="\t", dtype=str)
    sss = ch[(ch.variant == "V3") & (ch.group == "his") & (ch.origin_ticker == "SSS")]
    assert len(sss) == 1 and sss.trade_Es.iloc[0] == f"{E},{E2}"                         # the stop-out, then the re-break: 2 trades
    assert "GGG " + E in text and "level filled" in text                                  # the unfilled ORH5 call, filled at the open
    # §1.4b beside lines: HHH, SSS, GGG fill in minute 0 under V1 (own low); the control's BBB does, AAA (minute 5) does not; SSS's
    # re-entry at E2 fills at minute 5. With minute-0 fills dropped his origins have no campaign, the control keeps AAA.
    ol = [ln for ln in say2.lines if ln.startswith("- beside (§1.4b")]
    assert len(ol) == 10 and len(set(ol[:9])) == 1                                       # beside every V1 / COMBINED table, era A x 9 + B
    assert ("level his: fills 3 of 3, too-wide skips 0 of 0; level ctl: fills 1 of 2" in ol[0]
            and "COMBINED trades his (re-entries included) 3 of 4; COMBINED trades ctl (re-entries included) 1 of 2" in ol[0])
    m0 = [ln for ln in say2.lines if "fill in minute 0 (the day's first minute bar) DROPPED" in ln]
    assert len(m0) == 1 and "his 3 of 4 and the control's 1 of 2 fill in minute 0" in m0[0] and "final 1.000" in m0[0]
    assert "VERDICT" in text.split("fill in minute 0 (the day's first minute bar) DROPPED")[0]   # printed after the fork, beside it
    acc = pd.read_csv(tmp_path / "out2" / "account_his.tsv", sep="\t")
    a1 = pd.read_csv(tmp_path / "out1" / "account_his.tsv", sep="\t")
    assert acc[acc.variant == "V0"].equity.iloc[-1] == pytest.approx(a1[a1.config == "primary"].equity.iloc[-1], abs=1e-9)
    t = pd.read_csv(tmp_path / "out2" / "trades.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
    row = t[(t.ticker == "HHH") & (t.entry_set == "orh5")]
    assert float(row.realized_r.iloc[0]) == pytest.approx(expected_hhh_r(), rel=1e-9)
    assert set(t.entry_set) == set(ex.ENTRY_SETS) and (t[t.ticker == "SSS"].reentry_row_only.astype(int).sum()) == len(ex.ENTRY_SETS)


def test_run_exec_stops_when_v0_is_not_the_first_read(world, tmp_path, monkeypatch):
    """Tamper with one stored first-read R: the gate STOPS before any variant number."""
    S, done = e2e_world(world, tmp_path)
    flags = tmp_path / "flags.tsv"
    flags.write_text("check\tklass\tticker\tdate\n")
    monkeypatch.setitem(rp.FILES, "flags_A", str(flags))
    monkeypatch.setattr(rp, "OUT_DIR", str(tmp_path / "out1"))
    monkeypatch.setattr(rp, "BAND_DRAWS", 3)
    monkeypatch.setattr(rp, "run_g8", lambda era, path, out: (0, 0))
    say1 = rp.Say()
    rp.run_replay(S, say1)
    first_txt = tmp_path / "01_replay.txt"
    say1.write(str(first_txt))
    p = tmp_path / "out1" / "trades.tsv.gz"
    t = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
    m = (t.ticker == "HHH") & (t.variant == "orh5") & (t.arm == "p33_s3_t10")
    t.loc[m, "realized_r"] = "9.999"
    with gzip.open(p, "wt") as fh:
        t.to_csv(fh, sep="\t", index=False)
    monkeypatch.setattr(ex, "OUT_DIR", str(tmp_path / "out2"))
    monkeypatch.setattr(ex, "BAND_DRAWS", 3)
    monkeypatch.setattr(ex, "FIRST", {"first_trades": str(p), "first_account_his": str(tmp_path / "out1" / "account_his.tsv"),
                                      "first_account_band": str(tmp_path / "out1" / "account_band.tsv"),
                                      "first_printout": str(first_txt)})
    X = ex.prepare(S, done)
    adr, _bad = ex.adr_facts(S, X)
    say2 = rp.Say()
    with pytest.raises(ex.GuardStop, match="BASELINE PARITY FAILED"):
        ex.run_exec(S, X, adr, say2)
    assert not any("HEADLINE" in ln for ln in say2.lines)


def test_prepare_reads_each_eras_own_bars(world, tmp_path):
    """The same ticker in both eras: the walk-wiring check of a re-entry row must read ITS era's bars (a ticker-keyed cache shared
    across eras marked 400 good era-B rows `no_bar_on_E` / `D_not_the_bar_before_E` in the first dry run)."""
    cal_b = bdays("2022-03-01", 200)
    pb = tmp_path / "export_b.csv.gz"
    rows = [(t, d, px, px * 1.01, px * 0.99, px, 1e6) for t, px in (("SPY", 400.0), ("QQQ", 300.0), ("SSS", 50.0)) for d in cal_b]
    write_export(pb, rows)
    DB, _ = rp.load_daily_subset(str(pb))
    S, done = e2e_world(world, tmp_path)
    eb, db_, eb2 = cal_b[150].isoformat(), cal_b[149].isoformat(), cal_b[151].isoformat()
    S["Ds"]["B"] = DB
    S["qqq"]["B"] = R.bars_for(DB, DB.tid["QQQ"])
    S["files"]["B"] = {eb: "x", eb2: "y"}
    S["evs"].append(ev("SSS", era="B", D=db_, E=eb, pivot=50.0, adr20=0.02, his=True, year=2022, month=eb[:7]))
    S["eras"]["B"] = SimpleNamespace(name="B", ticker=np.array(["SSS", "SSS"]), E=np.array([eb, eb2]), D=np.array([db_, eb]),
                                     base_id=np.array(["SSS|b", "SSS|b"]), retrigger=np.array([0, 1]), pivot=np.array([50.0, 50.0]),
                                     adr20=np.array([0.02, 0.02]), cls={"lab_by_E": np.array([True, True])})
    done["B"] = {(eb, "SSS"): "ok", (eb2, "SSS"): "ok"}
    X = ex.prepare(S, done)
    assert X["facts"]["B_new_rows"] == 1 and X["facts"]["B_new_rows_kept"] == 1, dict(X["facts"])
    assert X["facts"]["A_new_rows_kept"] == 1 and ("B", "SSS", eb2) in X["walk"]


def test_v1_near_zero_stop_is_pinned_and_flagged():
    """A gap open whose first minute never trades below its open: the level entry fills at open x 1.001 with the stop AT the open, a
    0.1% stop (the near-zero-stop distortion the beside table re-reads without)."""
    rows = [(0, 10.5, 10.6, 10.5, 10.55)] + [(k, 10.55, 10.6, 10.3, 10.4) for k in range(1, 390)]
    lv = cb.entry_variants(minute_bars(rows), pivot=10.0, adr20=0.05, day_high=10.6, day_low=10.3)["pivot"]
    assert lv["status"] == "filled" and lv["fill"] == pytest.approx(10.5 * 1.001, rel=1e-12) and lv["stop"] == 10.5
    assert lv["width_pct"] == pytest.approx(0.001 / 1.001, rel=1e-9) and lv["width_pct"] < ex.TINY_WIDTH
    t = SimpleNamespace(width=lv["width_pct"], key=("A", "X", "d"))
    walk = {("A", "X", "d"): SimpleNamespace(adr20=0.05)}
    assert not ex.floor_ok(t, walk)
    assert ex.floor_ok(SimpleNamespace(width=0.0125, key=("A", "X", "d")), walk)              # exactly 0.25 ADR is in
