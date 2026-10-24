"""Synthetic tests for 03_round3.py (#705 round 3: the structural stop, holding winners longer, market-strength sizing). No real data
file is opened by any test: every world is hand-built in tmp_path (the end-to-end test runs the FROZEN first read's `run_replay` on
the same world first, so the baseline-parity gate is exercised against outputs that exist).

Run:  python3 -m pytest scripts/probes/_705_qm_replay_1023/test_03_round3.py -q
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import os
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("round3", os.path.join(HERE, "03_round3.py"))
m = importlib.util.module_from_spec(_spec)
sys.modules["round3"] = m
_spec.loader.exec_module(m)
ex, rp, R, cb = m.ex, m.rp, m.R, m.cb


# ═════════════════════════════════════════════════════════════════════════════════════════════
# a hand-built world (the second read's, with poles and a rising QQQ)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def bdays(start: str, n: int) -> list:
    return [d.date() for d in pd.bdate_range(start, periods=n)]


CAL = bdays("2019-06-03", 260)
E_IDX = 150
E, D_ = CAL[E_IDX].isoformat(), CAL[E_IDX - 1].isoformat()
E2, D2 = CAL[E_IDX + 2].isoformat(), CAL[E_IDX + 1].isoformat()
POLE = CAL[E_IDX - 30].isoformat()
FWD = [(10.20, 10.50, 10.10, 10.40), (10.40, 10.80, 10.30, 10.70), (10.70, 11.00, 10.60, 10.90), (10.90, 11.20, 10.80, 11.10),
       (11.10, 11.40, 11.00, 11.30), (11.30, 11.60, 11.20, 11.50), (11.00, 11.10, 10.55, 10.60), (10.50, 10.60, 10.40, 10.45)]
FWD2 = [(20.5, 20.8, 20.4, 20.7), (20.7, 21.0, 20.6, 20.9), (20.9, 21.2, 20.8, 21.1), (21.1, 21.3, 21.0, 21.2), (21.2, 21.3, 20.0, 20.1),
        (20.1, 20.2, 20.0, 20.1)]
FILL_HHH = 10.05 * 1.001


def hhh_rows():
    rows = []
    for i, d in enumerate(CAL):
        if i < E_IDX:
            rows.append(("HHH", d, 10.0, 10.25, 9.75, 10.0, 1e6))
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


def qqq_rows():
    """Rising every session: the close is above both its 10- and 20-day averages on every D ("up")."""
    return [("QQQ", d, 200.0 + 0.1 * i, 200.1 + 0.1 * i, 199.9 + 0.1 * i, 200.0 + 0.1 * i, 1e6) for i, d in enumerate(CAL)]


def write_export(path: Path, rows: list) -> None:
    with gzip.open(path, "wt") as fh:
        for t, d, o, h, l, c, v in rows:
            fh.write(f"{t},{d.isoformat()},{o},{h},{l},{c},{v}\n")


def hhh_minutes():
    m_ = [(k, 10.0, 10.05, 9.95 if k == 2 else 9.99, 10.0) for k in range(5)]
    m_.append((5, 10.04, 10.10, 10.02, 10.08))
    m_ += [(k, 10.10, 10.20 if k == 200 else 10.15, 10.05, 10.12) for k in range(6, 390)]
    return m_


def sss_minutes_E():
    """ORH5 = 20.05, filled at minute 5 (20.05 x 1.001), day-low stop 19.95; minute 100 touches 19.70 -> a day-0 stop under the day low,
    NOT under the base low 19.5."""
    m_ = [(k, 20.0, 20.05, 19.95 if k == 2 else 19.99, 20.0) for k in range(5)]
    m_.append((5, 20.04, 20.10, 20.02, 20.08))
    m_.append((6, 20.10, 20.40, 20.05, 20.30))
    m_ += [(k, 20.2, 20.25, 20.15, 20.2) for k in range(7, 100)]
    m_.append((100, 20.0, 20.0, 19.70, 19.75))
    m_ += [(k, 19.8, 19.85, 19.75, 19.8) for k in range(101, 390)]
    return m_


def sss_minutes_E2():
    m_ = [(k, 19.9, 19.95, 19.85, 19.9) for k in range(5)]
    m_.append((5, 19.95, 20.10, 19.90, 20.05))
    m_ += [(k, 20.3, 20.6, 20.25, 20.5) for k in range(6, 390)]
    return m_


def ggg_minutes():
    m_ = [(0, 30.6, 30.9, 30.5, 30.7)] + [(k, 30.7, 30.8, 30.4, 30.5) for k in range(1, 5)]
    m_ += [(k, 30.4, 30.5, 30.2, 30.3) for k in range(5, 390)]
    return m_


def aaa_minutes():
    m_ = [(k, 20.0, 20.05, 19.95, 20.0) for k in range(5)]
    m_ += [(k, 20.1, 20.2, 20.05, 20.15) for k in range(5, 390)]
    return m_


def flat_minutes(px: float):
    return [(k, px, px * 1.01, px * 0.99, px) for k in range(390)]


def minute_bars(rows):
    return cb.minute_bars_from_lists([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows],
                                     [r[4] for r in rows], [100.0] * len(rows))


def write_minutes(path: Path, blocks: dict) -> None:
    lines = []
    for tk, rows in blocks.items():
        lines += [f"{tk}|{mn}|{o}|{h}|{l}|{c}|100" for mn, o, h, l, c in rows]
    with gzip.open(path, "wt") as fh:
        fh.write("\n".join(lines) + "\n")


def ev(ticker, **kw) -> "rp.Event":
    base = dict(era="A", ticker=ticker, D=D_, E=E, base_id=f"{ticker}|b", retrigger=0, pivot=10.0, adr20=0.05, year=CAL[E_IDX].year,
                month=E[:7], minutes_state="ok", qqq="up")
    base.update(kw)
    return rp.Event(**base)


@pytest.fixture()
def world(tmp_path):
    p = tmp_path / "export.csv.gz"
    rows = (filler_rows("SPY", 300.0) + qqq_rows() + hhh_rows() + sss_rows() + ggg_rows() + filler_rows("AAA", 20.0)
            + filler_rows("BBB", 30.0))
    rows.sort(key=lambda r: (r[1], r[0]), reverse=True)
    write_export(p, rows)
    D, _info = rp.load_daily_subset(str(p))
    return SimpleNamespace(path=p, D=D)


def bars_of(D, tk, e_iso=E):
    bars, cidx = R.bars_for(D, D.tid[tk])
    return bars, cidx, R.locate_breakout_index(D.cal, cidx, e_iso)


BASE_LOWS = {"HHH": (9.75, 10.25), "SSS": (19.5, 20.5), "GGG": (29.25, 30.75), "AAA": (19.8, 20.2), "BBB": (29.7, 30.3)}   # (low, high(P))


def poles_for(keys) -> dict:
    return {k: (POLE, 1.0 - BASE_LOWS[k[1]][0] / BASE_LOWS[k[1]][1]) for k in keys}


def hhh_r(stop: float) -> float:
    """The first read's hand-computed HHH trade: a third at session 3's close 10.90, the rest at session 8's open 10.50; R against `stop`."""
    return ((10.90 - FILL_HHH) / 3.0 + (10.50 - FILL_HHH) * (2.0 / 3.0)) / (FILL_HHH - stop)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the variant table is the registration's
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_variant_table_is_the_registration():
    assert [v.name for v in m.VARIANTS] == ["B0", "W1", "W1b", "W2", "W2_t20", "W2b", "W3", "W3b", "COMBINED", "W4m_B0", "W4m_C", "W4a_C",
                                             "W4ma_C"]
    assert {v.name for v in m.VARIANTS if v.beside} == {"W1b", "W2_t20", "W2b", "W3b", "W4m_B0", "W4m_C", "W4a_C", "W4ma_C"}
    b0, c = m.VMAP["B0"], m.VMAP["COMBINED"]
    assert (b0.stop, b0.arm, b0.sizing, b0.gross_max, b0.adds) == ("lod", "p33_s3_t10", "flat", 1.0, False)
    assert (c.stop, c.arm, c.sizing, c.gross_max, c.adds) == ("base_low", "d3_p33_tspd", "qqq", 1.0, False)
    assert m.VMAP["W1"].stop == "base_low" and m.VMAP["W1b"].stop == "lod_floor1" and m.VMAP["W2"].arm == "d3_p33_tspd"
    assert m.VMAP["W2b"].arm == "trail10_only" and m.VMAP["W3b"].sizing == "qqq_drop_down" and m.VMAP["W4ma_C"].gross_max == 2.0
    assert all(not v.adds or v.beside for v in m.VARIANTS) and all(v.gross_max == 1.0 or v.beside for v in m.VARIANTS)   # W4 beside only
    assert m.CAP30 == rp.Config("cap_30", cap=0.30) and m.CAP30 is ex.CAP30                       # the first read's cap_30 row
    assert m.SPEED_CUT == cb.TRAIL_SPEED_ADR_CUT == 0.0479 and (m.RISK_UP, m.RISK_OTHER) == (0.01, 0.005)
    assert m.BAND_KEY == "qm_replay|band|A|same-day (registered)" and m.FIRST_DIFF_KEY == "qm_replay|A|orh5|p33_s3_t10|mean R"
    assert m.ARMS["d3_p33_tspd"] is cb.HIS_EXIT_ARMS["d3_p33_tspd"] and m.ARMS["p33_s3_t10"] is cb.ARMS["p33_s3_t10"]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the base low at D (outcome-free) and its cross-check
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_base_low_facts_and_depth_cross_check(world):
    D = world.D
    bars, cidx, e = bars_of(D, "HHH")
    bl, P, implied, i = m.base_low_facts(bars, cidx, D.cal, ev("HHH"), POLE, 1.0 - 9.75 / 10.25)
    assert bl == 9.75 and i == e - 1 and bars.dates[P].isoformat() == POLE
    assert implied == pytest.approx(9.75, rel=1e-12)
    assert bl == R.base_low_at(bars, P, i)                                                    # the runner's own formula
    with pytest.raises(ValueError, match="pole_date"):
        m.base_low_facts(bars, cidx, D.cal, ev("HHH"), CAL[E_IDX - 1].isoformat(), 0.05)       # a pole on D is not before D
    with pytest.raises(ValueError, match="not the bar before E"):
        m.base_low_facts(bars, cidx, D.cal, ev("HHH", D=CAL[E_IDX - 2].isoformat()), POLE, 0.05)
    assert bl == float(bars.l[P + 1:i + 1].min())                                              # bars up to D only


def test_prepare_counts_a_depth_mismatch_instead_of_passing_it(world):
    D = world.D
    evs = [ev("HHH", his=True), ev("SSS", pivot=20.0, his=True)]
    S = {"evs": evs, "Ds": {"A": D}}
    poles = poles_for([("A", "HHH", E), ("A", "SSS", E)])
    X = m.prepare(S, poles)
    assert X["facts"]["depth_mismatch"] == 0 and X["base_low"][("A", "HHH", E)] == 9.75 and X["base_low"][("A", "SSS", E)] == 19.5
    poles[("A", "SSS", E)] = (POLE, 0.10)                                                     # a wrong stored depth
    X = m.prepare(S, poles)
    assert X["facts"]["depth_mismatch"] == 1 and X["depth_bad"][0][0] == ("A", "SSS", E)
    with pytest.raises(KeyError):
        m.prepare({"evs": [ev("GGG", pivot=30.0, his=True)], "Ds": {"A": D}}, {})


def test_width_at_level_is_outcome_free_and_signed():
    x = ev("HHH", pivot=10.0, adr20=0.05)
    assert m.width_adr_at_level(x, 9.75) == pytest.approx(0.25 / 0.5, rel=1e-12)              # 2.5% of the level = 0.5 ADR
    assert m.width_adr_at_level(x, 10.2) < 0
    assert m.WIDTH_FLOOR_ADR == ex.WIDTH_FLOOR_ADR == 0.25


def test_near_zero_w1_stop_fills_and_is_floored_beside():
    """A base low between the level and the fill FILLS under W1 with a stop under 0.1% wide (the second read's unit artifact); the
    floored re-read drops it from the per-trade rows and the interval; a base low at or above the fill abstains."""
    mb = minute_bars(hhh_minutes())
    en = cb.entry_variants(mb, pivot=10.0, adr20=0.05, day_high=10.20, day_low=9.95)["orh5"]   # level 10.05, fill 10.06005
    tiny = m.stop_set_entries(en, mb, base_low=10.055, adr20=0.05)["base_low"]
    assert tiny["status"] == "filled" and tiny["width_pct"] < 0.001
    at_fill = m.stop_set_entries(en, mb, base_low=10.06005, adr20=0.05)["base_low"]
    assert at_fill["status"] == "abstain" and at_fill["reason"] == "stop_at_or_above_fill"
    walk = {("A", "X", "d"): SimpleNamespace(adr20=0.05)}
    assert not ex.floor_ok(SimpleNamespace(width=tiny["width_pct"], key=("A", "X", "d")), walk)
    assert ex.floor_ok(SimpleNamespace(width=0.0125, key=("A", "X", "d")), walk)
    # the `keep` filter of the date-matched line removes the narrow trade from the arm it sits in
    t_ok = _trade("H", 5, 0.03, [(6, rp.ORDER_OPEN, 1.0, 110.0, "trail", 1)], [100.0, 110.0])
    t_tiny = _trade("C", 5, 0.0005, [(6, rp.ORDER_OPEN, 1.0, 110.0, "trail", 1)], [100.0, 110.0])
    T = {t_ok.key: t_ok, t_tiny.key: t_tiny}
    his = [SimpleNamespace(era="A", ticker="H", E=t_ok.key[2])]
    ctl = [SimpleNamespace(era="A", ticker="C", E=t_tiny.key[2])]
    d_all = m.date_matched3(his, ctl, T, "k|mean R")
    d_fl = m.date_matched3(his, ctl, T, "k|floor|mean R", keep=lambda t: t.width >= 0.0125)
    assert d_all["_n"] == (1, 1) and d_fl["_n"] == (1, 0)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# W1 — the base-low stop; W1b — the lower of lod_prior and one ADR below the fill
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_w1_restops_a_fill_and_reruns_day0():
    mb = minute_bars(hhh_minutes())
    en = cb.entry_variants(mb, pivot=10.0, adr20=0.05, day_high=10.20, day_low=9.95)["orh5"]
    assert en["status"] == "filled" and en["stop"] == 9.95 and en["fill_minute"] == 5
    sets = m.stop_set_entries(en, mb, base_low=9.75, adr20=0.05)
    assert sets["lod"] is en
    w1 = sets["base_low"]
    assert w1["status"] == "filled" and w1["stop"] == 9.75 and w1["fill"] == en["fill"] and w1["fill_minute"] == 5
    assert w1["width_pct"] == pytest.approx((FILL_HHH - 9.75) / FILL_HHH, rel=1e-12)
    assert w1["day0"] == cb.day0_walk(mb, fill_minute=5, stop=9.75) and not w1["day0"]["stopped"]
    # W1b: lod_prior = the lows of minutes 0..4 (9.95 at minute 2), one ADR below the fill = 10.06005 x 0.95 = 9.557: the LOWER wins
    w1b = sets["lod_floor1"]
    assert w1b["stop"] == pytest.approx(FILL_HHH * 0.95, rel=1e-12) and w1b["status"] == "filled"


def test_w1_fills_a_too_wide_call_and_abstains_when_the_base_low_is_above_the_fill():
    mb = minute_bars(hhh_minutes())
    tw = cb.entry_variants(mb, pivot=10.0, adr20=0.005, day_high=10.20, day_low=9.95)["orh5"]   # 1.09% stop, 0.5% ADR: too wide
    assert tw["status"] == "abstain" and tw["reason"] == "too_wide"
    sets = m.stop_set_entries(tw, mb, base_low=9.75, adr20=0.005)
    assert sets["lod"]["status"] == "abstain"                                                 # the registered rule keeps the skip
    assert sets["base_low"]["status"] == "filled" and sets["base_low"]["stop"] == 9.75           # W1: no one-ADR skip
    assert sets["lod_floor1"]["status"] == "filled" and sets["lod_floor1"]["stop"] == 9.95   # the day low is the LOWER at a 0.5% ADR
    ab = m.stop_set_entries(tw, mb, base_low=10.5, adr20=0.005)["base_low"]
    assert ab["status"] == "abstain" and ab["reason"] == "stop_at_or_above_fill" and ab["day0"] is None
    nt = cb.entry_variants(minute_bars(ggg_minutes()), pivot=30.0, adr20=0.05, day_high=30.9, day_low=30.2)["orh5"]
    assert nt["status"] == "no_trigger"
    assert all(s is nt for s in m.stop_set_entries(nt, None, 29.25, 0.05).values())           # nothing to re-stop


def test_w1_day0_walk_differs_from_the_day_low_walk():
    """SSS: minute 100 touches 19.70 — a day-0 stop under the day low (19.95), none under the base low (19.5)."""
    mb = minute_bars(sss_minutes_E())
    en = cb.entry_variants(mb, pivot=20.0, adr20=0.05, day_high=20.4, day_low=19.7)["orh5"]
    assert en["day0"]["stopped"] and en["day0"]["exit_price"] == 19.95
    w1 = m.stop_set_entries(en, mb, base_low=19.5, adr20=0.05)["base_low"]
    assert not w1["day0"]["stopped"] and w1["stop"] == 19.5


def test_lod_prior_never_reads_the_fill_minutes_own_low():
    rows = [(k, 9.85, 9.90, 9.80, 9.85) for k in range(5)] + [(5, 9.95, 10.06, 9.60, 10.04)]   # the fill minute makes a new low 9.60
    rows += [(k, 10.05, 10.10, 10.00, 10.06) for k in range(6, 390)]
    mb = minute_bars(rows)
    en = cb.entry_variants(mb, pivot=10.0, adr20=0.10, day_high=10.10, day_low=9.60)["orh5"]
    assert en["status"] == "filled" and en["fill_minute"] == 5 and en["stop"] == 9.60             # the module's stop IS its own low
    assert ex.own_low_flag(mb, en) == (True, False)
    assert m.lod_prior(mb, 5) == 9.80                                                        # minutes 0..4 only
    w1b = m.stop_set_entries(en, mb, base_low=9.0, adr20=0.10)["lod_floor1"]
    assert w1b["stop"] == pytest.approx(min(9.80, en["fill"] * 0.90), rel=1e-12) and w1b["stop"] != 9.60
    with pytest.raises(AssertionError):
        m.lod_prior(minute_bars([(0, 10.0, 10.1, 9.9, 10.0)] + [(k, 10.0, 10.1, 9.9, 10.0) for k in range(1, 10)]), 0)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# W2 — the speed arm equals the 10-day above the cut and the 20-day below it; trail10_only has no partial
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_walk_event3_speed_arm_and_trail10_known_answers(world):
    D = world.D
    bars, cidx, e = bars_of(D, "HHH")
    mb = minute_bars(hhh_minutes())
    w = m.walk_event3(ev("HHH", adr20=0.05), bars, cidx, e, mb, breaks=None, base_low=9.75)   # 5% ADR > the 4.79% cut: the 10-day
    arms = w["sets"]["lod"]["arms"]
    assert set(arms) == set(m.ARMS) and set(w["sets"]) == set(m.STOPS)
    assert arms["p33_s3_t10"]["realized_r"] == pytest.approx(hhh_r(9.95), rel=1e-12)
    assert arms["d3_p33_tspd"]["realized_r"] == pytest.approx(arms["p33_s3_t10"]["realized_r"], rel=1e-12)
    assert arms["d3_p33_tspd"]["events"][0] == (0, "trail_n", 10.0, 0.0)
    assert arms["p33_s3_t20"]["realized_r"] != pytest.approx(arms["p33_s3_t10"]["realized_r"])   # the two trails differ on HHH
    slow = m.walk_event3(ev("HHH", adr20=0.045), bars, cidx, e, mb, breaks=None, base_low=9.75)["sets"]["lod"]["arms"]
    assert slow["d3_p33_tspd"]["realized_r"] == pytest.approx(slow["p33_s3_t20"]["realized_r"], rel=1e-12)
    assert slow["d3_p33_tspd"]["events"][0] == (0, "trail_n", 20.0, 0.0)
    # trail10_only: no partial, trails from session 1 -> the whole position out at session 8's open
    t10 = arms["trail10_only"]
    assert not any(k == "partial" for _j, k, _p, _f in t10["events"])
    assert t10["realized_r"] == pytest.approx((10.50 - FILL_HHH) / (FILL_HHH - 9.95), rel=1e-12) and t10["sessions_held"] == 8
    # W1 on HHH: the same exits, R in the wider unit
    assert w["sets"]["base_low"]["arms"]["p33_s3_t10"]["realized_r"] == pytest.approx(hhh_r(9.75), rel=1e-12)
    assert w["own_low"] == (False, False)


def test_make_trade_drops_the_trail_n_event(world):
    D = world.D
    bars, cidx, e = bars_of(D, "HHH")
    w = m.walk_event3(ev("HHH"), bars, cidx, e, minute_bars(hhh_minutes()), breaks=None, base_low=9.75)
    X = {"walk": {("A", "HHH", E): ev("HHH")}}
    w["bars"], w["cidx"], w["e"] = bars, cidx, e
    T = m.trades_for_combo(X, {("A", "HHH", E): w}, "base_low", "d3_p33_tspd")
    t = T[("A", "HHH", E)]
    assert [lg[4] for lg in t.legs] == ["partial", "trail"] and sum(lg[2] for lg in t.legs) == pytest.approx(1.0)
    assert t.realized_r == pytest.approx(hhh_r(9.75), rel=1e-12) and t.stop == 9.75


# ═════════════════════════════════════════════════════════════════════════════════════════════
# W3 / W4 — simulate3: the first read's simulate with two switches
# ═════════════════════════════════════════════════════════════════════════════════════════════
CC = bdays("2020-01-01", 80)


def _trade(tk, e_ci, width, legs, path_c, fill=100.0, key_tag=""):
    return rp.Trade(key=("A", tk, CC[e_ci].isoformat() + key_tag), ticker=tk, era="A", e_ci=e_ci, fill_minute=5, fill=fill,
                    stop=fill * (1 - width), width=width, status="stopped", mature=True, realized_r=0.0, r_slip=(0.0, 0.0, 0.0),
                    sessions_held=max(lg[5] for lg in legs), legs=legs, path_c=np.asarray(path_c, dtype=float), year=2020,
                    month=CC[e_ci].isoformat()[:7])


def random_trades(rng, n: int) -> list:
    out = []
    for i in range(n):
        e_ci = int(rng.integers(5, 50))
        held = int(rng.integers(1, 8))
        fill = 100.0
        px = float(fill * rng.uniform(0.85, 1.4))
        path = [fill] + [float(fill * rng.uniform(0.9, 1.3)) for _ in range(held - 1)] + [px]
        if rng.uniform() < 0.5:
            legs = [(e_ci + held, rp.ORDER_OPEN, 1.0, px, "trail", held)]
        else:
            legs = [(e_ci + 2, rp.ORDER_CLOSE, 1 / 3, path[2] if len(path) > 2 else path[-1], "partial", 2),
                    (e_ci + held, rp.ORDER_INTRADAY, 2 / 3, px, "stop", held)] if held > 2 else \
                   [(e_ci + held, rp.ORDER_INTRADAY, 1.0, px, "stop", held)]
        out.append(_trade(f"T{i % 7}", e_ci, float(rng.uniform(0.005, 0.12)), legs, path, key_tag=f"|{i}"))
    return out


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_simulate3_at_defaults_equals_the_first_reads_simulate(seed):
    rng = np.random.default_rng(seed)
    tr = random_trades(rng, 40)
    for cfg in (m.CAP30, rp.PRIMARY_CONFIG, rp.Config("trim", room="trim"), rp.Config("skip_same", same_ticker="skip")):
        a = rp.simulate(tr, cfg, CC, 4)
        b = m.simulate3(tr, cfg, CC, 4)
        assert m.curves_equal(a, b), (cfg, dict(a["counts"]), dict(b["counts"]))
        assert b["counts"][f"risk_{cfg.risk:g}"] == a["counts"]["entered"]
        assert m.curves_equal(a, m.simulate3(tr, cfg, CC, 4, risk_of=lambda t, r=cfg.risk: r, gross_max=1.0))
    assert not m.curves_equal(rp.simulate(tr, m.CAP30, CC, 4), rp.simulate(tr, rp.PRIMARY_CONFIG, CC, 4))   # the helper discriminates


def test_w3_sizing_by_qqq_state_known_answer():
    """Two trades, width 10%, each +20% on the position. Up: 1% risk -> a 10% position -> +2%. Down (or mixed / unknown): 0.5% -> 5% -> +1%."""
    a = _trade("UP", 5, 0.10, [(6, rp.ORDER_OPEN, 1.0, 120.0, "trail", 1)], [100.0, 120.0])
    b = _trade("DN", 10, 0.10, [(11, rp.ORDER_OPEN, 1.0, 120.0, "trail", 1)], [100.0, 120.0])
    c = _trade("UNK", 15, 0.10, [(16, rp.ORDER_OPEN, 1.0, 120.0, "trail", 1)], [100.0, 120.0])
    qqq_of = {a.key: "up", b.key: "down"}
    risk = m.risk_qqq(qqq_of)
    assert (risk(a), risk(b), risk(c)) == (0.01, 0.005, 0.005)
    sim = m.simulate3([a, b, c], m.CAP30, CC, 4, risk_of=risk)
    assert sim["final"] == pytest.approx(1.02 * 1.01 * 1.01, rel=1e-12)
    assert sim["counts"]["risk_0.01"] == 1 and sim["counts"]["risk_0.005"] == 2
    kept, n = m.drop_down([a, b, c], qqq_of)
    assert [t.key for t in kept] == [a.key, c.key] and n == 1
    v3b = m.VMAP["W3b"]
    tr, dr = m.variant_trades(v3b, [a.key, b.key, c.key], {a.key: a, b.key: b, c.key: c}, {}, qqq_of)
    assert [t.key for t in tr] == [a.key, c.key] and dr == 1
    assert m.risk_fn(m.VMAP["B0"], qqq_of) is None and m.risk_fn(v3b, qqq_of)(b) == 0.005


def test_w4_margin_enters_what_no_margin_skips():
    """Width 2%: 1% risk wants 50%, capped at 30% each. Four trades on the same day = 120% of equity: no margin takes three and skips the
    fourth for no room; at 2x gross all four enter and cash goes negative."""
    trs = [_trade(f"S{i}", 5, 0.02, [(7, rp.ORDER_CLOSE, 1.0, 110.0, "partial", 2)], [100.0, 105.0, 110.0]) for i in range(4)]
    cfg = m.CAP30
    a = m.simulate3(trs, cfg, CC, 4)
    assert a["counts"]["entered"] == 3 and a["counts"]["skipped_no_room"] == 1 and a["min_cash"] >= -1e-12
    assert a["final"] == pytest.approx(1 + 3 * 0.30 * 0.10, rel=1e-12)
    b = m.simulate3(trs, cfg, CC, 4, gross_max=2.0)
    assert b["counts"]["entered"] == 4 and b["counts"]["skipped_no_room"] == 0
    assert b["final"] == pytest.approx(1 + 4 * 0.30 * 0.10, rel=1e-12) and b["min_cash"] == pytest.approx(-0.20, rel=1e-12)
    assert b["max_gross"] > 1.0 and a["max_gross"] <= 1.0 + 1e-12
    assert m.curves_equal(rp.simulate(trs, cfg, CC, 4), a)
    # the per-stock limit still binds under margin: two positions in one ticker take 30% at cost together
    same = [_trade("S0", 5, 0.02, [(7, rp.ORDER_CLOSE, 1.0, 110.0, "partial", 2)], [100.0, 105.0, 110.0], key_tag=f"|{i}") for i in range(2)]
    s = m.simulate3(same, cfg, CC, 4, gross_max=2.0)
    assert s["counts"]["entered"] == 1 and s["counts"]["skipped_stock_limit"] == 1


# ═════════════════════════════════════════════════════════════════════════════════════════════
# W4a — one add per trade on a new high after the day-3 partial
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_add_for_known_answer_on_hhh(world):
    """HHH (base-low stop): the day-3 partial, then session 4's high 11.20 exceeds the prior high 11.00 (sessions 0-3) -> the add fills at
    11.00 x 1.001 (the open 10.90 did not gap above it), stop = the breakeven fill, and exits with the remainder at session 8's open 10.50."""
    D = world.D
    bars, cidx, e = bars_of(D, "HHH")
    w = m.walk_event3(ev("HHH"), bars, cidx, e, minute_bars(hhh_minutes()), breaks=None, base_low=9.75)
    w["bars"], w["cidx"], w["e"] = bars, cidx, e
    X = {"walk": {("A", "HHH", E): ev("HHH")}}
    T = m.trades_for_combo(X, {("A", "HHH", E): w}, "base_low", "d3_p33_tspd")
    t = T[("A", "HHH", E)]
    qqq = R.bars_for(D, D.tid["QQQ"])
    a, why = m.add_for(t, bars, e, cidx, D.cal, qqq)
    assert why == ("ok", "up") and a is not None
    assert a.key == ("A", "HHH", f"{E}|add4") and a.fill == pytest.approx(11.00 * 1.001, rel=1e-12) and a.stop == t.fill
    assert a.e_ci == int(cidx[e + 4]) and a.fill_minute == 389 and a.sessions_held == 4 and a.mature
    assert a.legs == [(int(cidx[e + 8]), rp.ORDER_OPEN, 1.0, 10.50, "trail", 4)]
    assert a.realized_r == pytest.approx((10.50 - a.fill) / (a.fill - t.fill), rel=1e-12)
    assert list(a.path_c) == [float(x) for x in bars.c[e + 4:e + 9]]
    # the account books the add after its origin; both exit at session 8's open
    S = {"Ds": {"A": D}, "qqq": {"A": qqq}}
    adds, states, reasons = m.adds_for_combo(T, {("A", "HHH", E): w}, S)
    assert set(adds) == {("A", "HHH", E)} and states[a.key] == "up" and reasons == Counter({"ok": 1})
    tr, _d = m.variant_trades(m.VMAP["W4a_C"], [("A", "HHH", E)], T, adds, {("A", "HHH", E): "up", a.key: "up"})
    assert [x.key for x in tr] == [t.key, a.key]
    sim = m.simulate3(tr, m.CAP30, D.cal, e - 1, risk_of=m.risk_qqq({t.key: "up", a.key: "up"}))
    assert sim["counts"]["entered"] == 2 and sim["counts"]["same_ticker_concurrent"] == 1


def test_add_rules_no_partial_no_room_stop_day_and_one_add_only():
    cal = CC
    dates = cal[:30]
    h = np.array([10.0] * 30)
    o = np.array([10.0] * 30)
    l = np.array([9.5] * 30)
    c = np.array([10.0] * 30)
    e = 5
    # a stopped-out trade (no partial) never adds
    t = _trade("X", 5, 0.05, [(6, rp.ORDER_INTRADAY, 1.0, 95.0, "stop", 1)], [100.0, 95.0])
    bars = cb.daily_bars_from_arrays(dates, o, h, l, c, np.ones(30))
    assert m.add_for(t, bars, e, np.arange(30), cal, (bars, np.arange(30)))[1] == "no_partial"
    # a partial at session 3 then the breakeven stop on session 4: no room (j must be < s_exit and >= 4)
    t = _trade("X", 5, 0.05, [(8, rp.ORDER_CLOSE, 1 / 3, 101.0, "partial", 3), (9, rp.ORDER_INTRADAY, 2 / 3, 100.0, "stop", 4)], [100.0] * 5)
    assert m.add_for(t, bars, e, np.arange(30), cal, (bars, np.arange(30)))[1] == "no_room"
    # the remainder exits on session 6; the only new high is ON the stop day (session 6): no add
    h2 = h.copy()
    h2[e + 6] = 12.0
    bars2 = cb.daily_bars_from_arrays(dates, o, h2, l, c, np.ones(30))
    t = _trade("X", 5, 0.05, [(8, rp.ORDER_CLOSE, 1 / 3, 101.0, "partial", 3), (11, rp.ORDER_INTRADAY, 2 / 3, 100.0, "stop", 6)], [100.0] * 7)
    assert m.add_for(t, bars2, e, np.arange(30), cal, (bars2, np.arange(30)))[1] == "no_new_high"
    # a new high on session 4 AND on session 5: ONE add, on session 4; a gap open above the prior high fills at the open
    h3 = h.copy()
    h3[e + 4], h3[e + 5] = 10.5, 11.0
    o3 = o.copy()
    o3[e + 4] = 10.3
    bars3 = cb.daily_bars_from_arrays(dates, o3, h3, l, c, np.ones(30))
    # the origin's fill (100, the breakeven stop) sits ABOVE the add's fill on these ~10 bars: skipped and counted
    assert m.add_for(t, bars3, e, np.arange(30), cal, (bars3, np.arange(30)))[1] == "stop_at_or_above_fill"
    t2 = _trade("X", 5, 0.05, [(8, rp.ORDER_CLOSE, 1 / 3, 101.0, "partial", 3), (11, rp.ORDER_INTRADAY, 2 / 3, 9.9, "stop", 6)], [10.0] * 7,
                fill=10.0)
    a2, why2 = m.add_for(t2, bars3, e, np.arange(30), cal, (bars3, np.arange(30)))
    assert why2[0] == "ok" and a2.key[2].endswith("|add4") and a2.fill == pytest.approx(10.3 * 1.001, rel=1e-12) and a2.fill_minute == 0
    assert a2.stop == 10.0 and a2.sessions_held == 2 and a2.legs[0][3] == 9.9
    assert a2.realized_r == pytest.approx((9.9 - a2.fill) / (a2.fill - 10.0), rel=1e-12)
    t3 = _trade("X", 5, 0.05, [(8, rp.ORDER_CLOSE, 1 / 3, 101.0, "partial", 3), (11, rp.ORDER_INTRADAY, 2 / 3, 9.9, "stop", 6)], [10.0] * 7,
                fill=11.0)
    assert m.add_for(t3, bars3, e, np.arange(30), cal, (bars3, np.arange(30)))[1] == "stop_at_or_above_fill"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the fork and its text
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_fork_is_the_second_reads_function_with_this_reads_text():
    assert ex.fork_exec({2020: 0.80, 2021: 0.50}, 0.05)[0] == "EXPLAINED"
    assert ex.fork_exec({2020: 0.80, 2021: 0.499}, 0.0)[0] == "NEXT GAPS"
    assert ex.fork_exec({2020: 0.80, 2021: 0.60}, 0.055)[0] == "NEXT GAPS"
    assert m.NEXT_GAPS in m.FORK_TEXT["NEXT GAPS"] and "does not work" in m.FORK_TEXT["NEXT GAPS"]
    assert "the EPs and parabolic shorts in his record" in m.NEXT_GAPS and "never mentioned on stream" in m.NEXT_GAPS
    assert "adds / margin if still beside" in m.NEXT_GAPS


def test_the_doc_carries_the_fork_row_and_the_marker_once():
    if not os.path.exists(m.DOC):
        pytest.skip("registration not written yet")
    raw = Path(m.DOC).read_bytes()
    sp = m.marker_spans(raw)
    assert len(sp) == 1 and raw[:sp[0][0]].count(m.FREEZE_MARKER.encode()) == 0
    body = raw[:sp[0][0]].decode()
    s7 = body.split("## 7.")[1].split("\n## 8.")[0]
    row = [ln for ln in s7.splitlines() if "**NEXT GAPS**" in ln]
    assert len(row) == 1 and m.NEXT_GAPS in row[0]
    assert "chosen AFTER seeing the first two reads" in body
    for word in ("**W1**", "W1b (beside)", "**W2**", "W2_t20 (beside", "W2b (beside)", "**W3**", "W3b (beside)", "**COMBINED**",
                 "W4 (BESIDE ONLY"):
        assert word in body, word
    assert "4.79%" in body and "2.044" in body and "d3_p33_tspd" in body and "trail10_only" in body


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock, the pins, the refusals
# ═════════════════════════════════════════════════════════════════════════════════════════════
M = m.FREEZE_MARKER


def test_freeze_lock_is_the_second_reads_line_anchored_lock(tmp_path):
    assert m.doc_body_sha is ex.doc_body_sha and m.freeze_missing is ex.freeze_missing and m.marker_spans is ex.marker_spans
    doc = tmp_path / "d.md"
    doc.write_text(f"# body\nthe lock pastes pins under the freeze marker `{M}` below\n\n{M}\n")
    body = doc.read_bytes().split(b"\n" + M.encode() + b"\n")[0] + b"\n"
    assert m.doc_body_sha(str(doc)) == hashlib.sha256(body).hexdigest()
    assert m.freeze_missing(str(doc), {"a": "aaa"}) == ["a"]
    doc.write_text(f"# body\n\n{M}\n- a: aaa\n\n{M}\n- a: aaa\n")
    assert m.freeze_missing(str(doc), {"a": "aaa"}) == ["a"]                                    # two marker lines: refused


def test_pins_cover_both_frozen_reads_and_this_module():
    assert set(m.SECOND) == {"second_trades", "second_chains", "second_account_his", "second_account_band", "second_printout"}
    assert set(m.FIRST) == set(ex.FIRST) and set(ex.FILES) <= set(m.FILES) and set(m.SECOND) <= set(m.FILES)
    assert {"round3_module", "round3_tests", "exec_module", "exec_tests", "replay_module", "replay_tests", "runner", "cb_module",
            "constants"} <= set(m.CODE)
    assert m.PINNED["exec_module"] == m.SECOND_MODULE_SHA and m.PINNED["exec_tests"] == m.SECOND_TESTS_SHA
    assert m.PINNED["replay_module"] == ex.FIRST_MODULE_SHA
    assert rp.sha(ex.CODE["exec_module"]) == m.SECOND_MODULE_SHA                                  # the imported second read IS the frozen one
    assert rp.sha(rp.CODE["replay_module"]) == ex.FIRST_MODULE_SHA
    assert m.FIRST_MINUTES["A"].startswith("b6a99cdf") and m.FIRST_MINUTES["B"].startswith("d548f856")


@pytest.fixture()
def lock_sandbox(tmp_path, monkeypatch):
    f = tmp_path / "input.txt"
    f.write_text("x")
    doc = tmp_path / "doc.md"
    first_doc = tmp_path / "first.md"
    first_doc.write_text("first body\n" + M + "\n")
    second_doc = tmp_path / "second.md"
    second_doc.write_text("second body\n" + M + "\n")
    monkeypatch.setattr(m, "FILES", {"inp": str(f)})
    monkeypatch.setattr(m, "FIRST", {"first_printout": str(f)})
    monkeypatch.setattr(m, "SECOND", {"second_printout": str(f)})
    monkeypatch.setattr(m, "CODE", {})
    monkeypatch.setattr(m, "PINNED", {"inp": rp.sha(str(f))})
    monkeypatch.setattr(rp, "DOC", str(first_doc))
    monkeypatch.setattr(ex, "DOC", str(second_doc))
    monkeypatch.setattr(m, "FIRST_DOC_BODY", rp.doc_body_sha(str(first_doc)))
    monkeypatch.setattr(m, "SECOND_DOC_BODY", ex.doc_body_sha(str(second_doc)))
    monkeypatch.setattr(m, "DOC", str(doc))
    monkeypatch.setattr(m, "PRINTOUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(m, "DRY_PRINTOUT", str(tmp_path / "dry.txt"))
    monkeypatch.setattr(m, "STOPPED", str(tmp_path / "stopped.txt"))
    monkeypatch.setattr(m, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(m, "FIRST_MINUTES", {"A": rp.tree_sha([]), "B": rp.tree_sha([])})
    monkeypatch.setattr(rp, "load_all", lambda say, dry: {"evs": []})
    monkeypatch.setattr(rp, "describe_population", lambda say, S: None)
    monkeypatch.setattr(m, "load_poles", lambda: {})
    monkeypatch.setattr(m, "prepare", lambda S, poles: {"walk": {}, "facts": Counter(), "depth_bad": []})
    monkeypatch.setattr(m, "describe_round3", lambda *a: None)
    ran = []
    monkeypatch.setattr(m, "run_round3", lambda S, X, say: ran.append(1))
    return SimpleNamespace(doc=doc, f=f, first_doc=first_doc, second_doc=second_doc, ran=ran, tmp=tmp_path)


def test_real_run_refuses_until_frozen_then_runs(lock_sandbox):
    sb = lock_sandbox
    sb.doc.write_text(f"# registration\n\n{M}\n")
    assert m.main([]) == 2 and not sb.ran
    p = m.pins({"A": [], "B": []})
    assert {"first_doc_body", "second_doc_body", "doc_body", "minutes_A_used", "minutes_B_used", "inp"} <= set(p)
    sb.doc.write_text(f"# registration\n\n{M}\n" + "".join(f"- {k}: {v}\n" for k, v in p.items()))
    assert m.main(["--dry-run"]) == 0 and not sb.ran
    assert "DRY RUN ends here" in Path(m.DRY_PRINTOUT).read_text()
    assert m.main([]) == 0 and sb.ran == [1]
    os.remove(m.PRINTOUT)


def test_real_run_refuses_a_doc_edited_after_the_pin_or_an_output_or_drift(lock_sandbox):
    sb = lock_sandbox
    sb.doc.write_text(f"# registration\n\n{M}\n")
    p = m.pins({"A": [], "B": []})
    sb.doc.write_text(f"# registration, EDITED after the pin\n\n{M}\n" + "".join(f"- {k}: {v}\n" for k, v in p.items()))
    assert m.main([]) == 2 and not sb.ran
    sb.doc.write_text(f"# registration\n\n{M}\n" + "".join(f"- {k}: {v}\n" for k, v in p.items()))
    Path(m.PRINTOUT).write_text("already ran")
    assert m.main([]) == 2 and not sb.ran
    os.remove(m.PRINTOUT)
    os.makedirs(m.OUT_DIR, exist_ok=True)
    Path(m.OUT_DIR, "adds.tsv").write_text("x")
    assert m.main([]) == 2 and not sb.ran
    os.remove(Path(m.OUT_DIR, "adds.tsv"))
    sb.second_doc.write_text("second body EDITED\n" + M + "\n")                                    # the frozen second doc drifted
    assert m.main(["--dry-run"]) == 2 and not sb.ran
    sb.second_doc.write_text("second body\n" + M + "\n")
    sb.first_doc.write_text("first body EDITED\n" + M + "\n")
    assert m.main(["--dry-run"]) == 2 and not sb.ran
    sb.first_doc.write_text("first body\n" + M + "\n")
    sb.f.write_text("changed")
    assert m.main(["--dry-run"]) == 2 and not sb.ran


def test_dry_run_refuses_when_the_walk_set_is_not_the_first_reads(lock_sandbox, monkeypatch):
    sb = lock_sandbox
    monkeypatch.setattr(m, "FIRST_MINUTES", {"A": "0" * 64, "B": "0" * 64})
    sb.doc.write_text(f"# registration\n\n{M}\n")
    assert m.main(["--dry-run"]) == 2 and not sb.ran
    assert "walk set is not the first read's" in Path(m.DRY_PRINTOUT).read_text()


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the parity readers
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_parity_trades3_checks_both_arms_and_detects_a_changed_trade(tmp_path):
    cols = ["era", "ticker", "E", "variant", "entry_status", "entry_reason", "fill", "stop", "fill_minute", "arm", "status", "mature",
            "sessions_held", "realized_r"]
    rows = [["A", "HHH", E, "orh5", "filled", "", "10.06005", "9.95", "5", "p33_s3_t10", "trailed", "1", "8", "4.123456789"],
            ["A", "HHH", E, "orh5", "filled", "", "10.06005", "9.95", "5", "p33_s3_t20", "trailed", "1", "12", "5.5"],
            ["A", "HHH", E, "orh5", "filled", "", "10.06005", "9.95", "5", "pp", "trailed", "1", "8", "9.9"],
            ["A", "GGG", E, "orh5", "no_trigger", "no_minute_above_level", "", "", "", "", "", "", "", ""]]
    p = tmp_path / "t.tsv.gz"
    with gzip.open(p, "wt") as fh:
        fh.write("\t".join(cols) + "\n" + "".join("\t".join(r) + "\n" for r in rows))
    keys = {("A", "HHH", E), ("A", "GGG", E)}
    res = {("A", "HHH", E): {"sets": {"lod": {"entry": {"status": "filled", "reason": None}}}},
           ("A", "GGG", E): {"sets": {"lod": {"entry": {"status": "no_trigger", "reason": "no_minute_above_level"}}}}}
    t10 = SimpleNamespace(fill=10.06005, stop=9.95, realized_r=4.1234567891, fill_minute=5, status="trailed", mature=True, sessions_held=8)
    t20 = SimpleNamespace(fill=10.06005, stop=9.95, realized_r=5.5, fill_minute=5, status="trailed", mature=True, sessions_held=12)
    TT = {("lod", "p33_s3_t10"): {("A", "HHH", E): t10}, ("lod", "p33_s3_t20"): {("A", "HHH", E): t20}}
    assert m.parity_trades3(str(p), keys, res, TT) == []
    t20.realized_r = 5.6                                                                         # the SECOND arm is checked too
    assert len(m.parity_trades3(str(p), keys, res, TT)) == 1
    t20.realized_r = 5.5
    TT[("lod", "p33_s3_t20")] = {}
    assert any("no B0 trade" in b for b in m.parity_trades3(str(p), keys, res, TT))
    assert m.parity_trades3(str(p), keys | {("A", "ZZZ", E)}, res, TT)[0].startswith("event set differs")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# end to end: the frozen first read's run_replay on a world, then this read's run_round3 on the SAME world through the parity gate
# ═════════════════════════════════════════════════════════════════════════════════════════════
def e2e_world(world, tmp_path):
    D = world.D
    mdir = tmp_path / "minutes"
    mdir.mkdir()
    write_minutes(mdir / f"{E}.psv.gz", {"HHH": hhh_minutes(), "SSS": sss_minutes_E(), "GGG": ggg_minutes(), "AAA": aaa_minutes(),
                                        "BBB": flat_minutes(30.0)})
    write_minutes(mdir / f"{E2}.psv.gz", {"SSS": sss_minutes_E2()})
    evs = [ev("HHH", strict=True, first_of_base=True, his=True), ev("SSS", pivot=20.0, his=True, first_of_base=True),
           ev("GGG", pivot=30.0, his=True, first_of_base=True),
           ev("AAA", pivot=20.1, adr20=0.02, ctl=True, base_id="AAA|1"),
           ev("BBB", pivot=29.0, adr20=0.02, ctl=True, base_id="BBB|1", retrigger=1)]
    rows = [("HHH", E, D_, "HHH|b", 0, 10.0, 0.05, True), ("SSS", E, D_, "SSS|b", 0, 20.0, 0.05, True),
            ("SSS", E2, D2, "SSS|b", 1, 20.0, 0.05, True), ("GGG", E, D_, "GGG|b", 0, 30.0, 0.05, True),
            ("AAA", E, D_, "AAA|1", 0, 20.1, 0.02, False), ("BBB", E, D_, "BBB|1", 1, 29.0, 0.02, False)]
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
    poles = poles_for([("A", x.ticker, x.E) for x in evs])
    return S, poles


def first_read_on(S, tmp_path, monkeypatch):
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
    a1 = pd.read_csv(tmp_path / "out1" / "account_his.tsv", sep="\t")
    c30 = a1[a1.config == "cap_30"]
    ye = c30.groupby(c30.date.str[:4]).equity.last()
    yearly = {int(y): ye[y] / (ye.get(str(int(y) - 1), 1.0)) - 1.0 for y in ye.index}
    monkeypatch.setattr(m, "OUT_DIR", str(tmp_path / "out2"))
    monkeypatch.setattr(m, "BAND_DRAWS", 3)
    monkeypatch.setattr(m, "FIRST", {"first_trades": str(tmp_path / "out1" / "trades.tsv.gz"),
                                     "first_account_his": str(tmp_path / "out1" / "account_his.tsv"),
                                     "first_account_band": str(tmp_path / "out1" / "account_band.tsv"),
                                     "first_printout": str(first_txt)})
    monkeypatch.setattr(m, "BASELINE_FINAL_TXT", f"{c30.equity.iloc[-1]:.3f}")
    monkeypatch.setattr(m, "BASELINE_YEARS_TXT", {y: rp.pct(v) for y, v in yearly.items() if y in (CAL[E_IDX].year,)})
    return first_txt


def test_run_round3_end_to_end_with_the_parity_gate(world, tmp_path, monkeypatch):
    S, poles = e2e_world(world, tmp_path)
    first_txt = first_read_on(S, tmp_path, monkeypatch)
    assert "of 1 his-call trades stopped out, 1 have a later break" in first_txt.read_text()
    X = m.prepare(S, poles)
    assert X["facts"]["depth_mismatch"] == 0 and len(X["walk"]) == 5
    say2 = rp.Say()
    m.run_round3(S, X, say2)
    text = "\n".join(say2.lines)
    for s in ("BASELINE PARITY", "Entry facts per stop set", "HEADLINE", "By year of E", "DATE-MATCHED", "ACCOUNT CURVE", "every stop x every exit",
              "CONTROL BAND", "THE FORK", "VERDICT", "strictly-before", "Era B"):
        assert s in text, s
    # B0 = the first read's cap_30 row, day by day
    acc = pd.read_csv(tmp_path / "out2" / "account_his.tsv", sep="\t")
    a1 = pd.read_csv(tmp_path / "out1" / "account_his.tsv", sep="\t")
    b0, c30 = acc[acc.variant == "B0"], a1[a1.config == "cap_30"]
    assert len(b0) == len(c30) and np.allclose(b0.equity.to_numpy(), c30.equity.to_numpy(), atol=1e-12)
    assert set(acc.variant) == {v.name for v in m.VARIANTS}
    # W3 = B0 on this world: QQQ is "up" on every D, so every trade risks 1%
    assert np.allclose(acc[acc.variant == "W3"].equity.to_numpy(), b0.equity.to_numpy(), atol=1e-12)
    assert np.allclose(acc[acc.variant == "W3b"].equity.to_numpy(), b0.equity.to_numpy(), atol=1e-12)
    # the trade table: 3 stop sets x 4 arms for a filled event; W1's HHH R in the wider unit; SSS day-0 stopped under the day low only
    t = pd.read_csv(tmp_path / "out2" / "trades.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
    hhh = t[t.ticker == "HHH"]
    assert len(hhh) == 12 and set(hhh.stop_set) == set(m.STOPS) and set(hhh.arm) == set(m.ARMS)
    r_w1 = float(hhh[(hhh.stop_set == "base_low") & (hhh.arm == "p33_s3_t10")].realized_r.iloc[0])
    assert r_w1 == pytest.approx(hhh_r(9.75), rel=1e-9)
    assert float(hhh[(hhh.stop_set == "lod") & (hhh.arm == "p33_s3_t10")].realized_r.iloc[0]) == pytest.approx(hhh_r(9.95), rel=1e-9)
    sss = t[t.ticker == "SSS"]
    assert set(sss[sss.stop_set == "lod"].status) == {"stopped_day0"} and "stopped_day0" not in set(sss[sss.stop_set == "base_low"].status)
    assert (hhh.own_low == "0").all() and (t[t.ticker == "GGG"].entry_status == "no_trigger").all()
    # adds: HHH (base_low x speed) adds on session 4 at 11.00 x 1.001; SSS adds on session 4 and exits at its breakeven stop (-1R)
    ad = pd.read_csv(tmp_path / "out2" / "adds.tsv", sep="\t", dtype=str)
    assert set(ad.ticker) >= {"HHH", "SSS"} and (ad.qqq_at_add_D == "up").all()
    h_add = ad[(ad.ticker == "HHH") & (ad.stop_set == "base_low")].iloc[0]
    assert float(h_add.fill) == pytest.approx(11.00 * 1.001, rel=1e-9) and int(h_add.session_j) == 4 and float(h_add.exit_px) == 10.5
    s_add = ad[(ad.ticker == "SSS") & (ad.stop_set == "base_low")].iloc[0]
    assert float(s_add.realized_r) == pytest.approx(-1.0, rel=1e-9)
    assert "W4a adds on the base_low x d3_p33_tspd trades" in text
    bnd = pd.read_csv(tmp_path / "out2" / "account_band.tsv", sep="\t")
    assert set(bnd.variant) == {v.name for v in m.VARIANTS} and set(bnd.measure.astype(str)) == {"2020", "2021", "final", "max_dd"}
    assert "VERDICT: **NEXT GAPS**" in text or "VERDICT: **EXPLAINED**" in text


def test_run_round3_stops_when_b0_is_not_the_first_read_on_the_second_arm(world, tmp_path, monkeypatch):
    """Tamper with one stored first-read R on the p33_s3_t20 arm: the gate STOPS before any variant number (both arms are checked)."""
    S, poles = e2e_world(world, tmp_path)
    first_read_on(S, tmp_path, monkeypatch)
    p = tmp_path / "out1" / "trades.tsv.gz"
    t = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
    mask = (t.ticker == "HHH") & (t.variant == "orh5") & (t.arm == "p33_s3_t20")
    assert mask.sum() == 1
    t.loc[mask, "realized_r"] = "9.999"
    with gzip.open(p, "wt") as fh:
        t.to_csv(fh, sep="\t", index=False)
    X = m.prepare(S, poles)
    say2 = rp.Say()
    with pytest.raises(m.GuardStop, match="BASELINE PARITY FAILED"):
        m.run_round3(S, X, say2)
    assert not any("HEADLINE" in ln for ln in say2.lines)


def test_run_round3_stops_when_the_registered_baseline_string_differs(world, tmp_path, monkeypatch):
    S, poles = e2e_world(world, tmp_path)
    first_read_on(S, tmp_path, monkeypatch)
    monkeypatch.setattr(m, "BASELINE_FINAL_TXT", "2.044")                                        # the real registration's number, not this world's
    X = m.prepare(S, poles)
    with pytest.raises(m.GuardStop, match="not the registered 2.044"):
        m.run_round3(S, X, rp.Say())
