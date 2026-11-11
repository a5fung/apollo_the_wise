"""Breakout v1's SHAPE gates (#717, 2026-11-11) — pre-registered and scored in
`docs/analysis/cb_shape_gates_2026-11-11.md`; owner `docs/setups/consolidation_breakout.md`.

The score FAILED its bar, so NO shape gate is enforced on the list (`bv.ENFORCED_SHAPE_GATES == ()`). These tests pin:
  - the pre-registered constants and the calibration on the three charts the operator read on 2026-11-02;
  - that the list is unchanged while nothing is enforced;
  - the MEASURED result of the revised set (not_extended + tight10) on his 29 graded list names
    (`tests/fixtures/breakout_list_grades.py` + `_bars.psv.gz`) and on Qullamaggie's 269 buys
    (`tests/fixtures/qm_breakout_scorecard/`), each survivor and each dropped good chart NAMED;
  - the DoD's own test — every chart he graded `no` is rejected — as a strict xfail: red today, and it must be
    turned into a plain test by whichever definition finally passes it.
These are DETECTION checks against his grades and Qullamaggie's setups, never a returns verdict.
"""
from __future__ import annotations

import csv
import gzip
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import consolidation_breakout as cb
from tests.fixtures.breakout_list_grades import BREAKOUT_LIST_GRADES

FX = Path(__file__).parent / "fixtures"
QM = FX / "qm_breakout_scorecard"
REVISED = ("not_extended", "tight10")          # the 2026-11-11 amendment's set


def _bars(rows, keys="ohlcv", dkey="date"):
    ds = [date.fromisoformat(x[dkey]) for x in rows]
    return cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rows] for k in keys])


@pytest.fixture(scope="module")
def graded():
    """[(BreakoutGrade, DailyBars ending on its list night)] — the 29 names he graded."""
    by = defaultdict(list)
    with gzip.open(FX / "breakout_list_grades_bars.psv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by[(r["ticker"], r["list_date"])].append(r)
    out = []
    for g in BREAKOUT_LIST_GRADES:
        b = _bars(by[(g.ticker, g.list_date)])
        assert b.dates[-1].isoformat() == g.list_date        # no bar after the list night
        out.append((g, b))
    return out


@pytest.fixture(scope="module")
def qm_series():
    """{eid: rows} and the buys — Qullamaggie's 269, bars cut at the night D before each buy."""
    buys = list(csv.DictReader(open(QM / "buys.tsv"), delimiter="\t"))
    by = defaultdict(list)
    with gzip.open(QM / "bars.psv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by[r["eid"]].append(r)
    out = []
    for r in buys:
        rr = sorted(by[r["eid"]], key=lambda x: x["date"])
        D = [x["date"] for x in rr].index(r["D"])
        out.append((r, _bars(rr[:D + 1]), rr))
    return out


def _shape(b, D=None):
    D = len(b) - 1 if D is None else D
    g = bv.v1_gates(b, D, rs_best=99.0)
    return bv.shape_gates(b, D, P=g["pole_idx"], adr20=g["adr20"]), g


def test_the_constants_are_the_pre_registered_ones_and_nothing_is_enforced():
    assert bv.SHAPE_GATES == ("higher_lows", "no_lower_low", "rising_avg", "not_extended", "tight10")
    assert (bv.SHAPE_HL_RECENT, bv.SHAPE_SWING_HALF, bv.SHAPE_LOWER_LOW_ADR, bv.SHAPE_RISING_SESSIONS,
            bv.SHAPE_EMA_FAST, bv.SHAPE_EXTENDED_ADR_MAX, bv.SHAPE_TIGHT_ADR_MAX) == (5, 2, 1.0, 5, 10, 1.0, 4.0)
    assert bv.ENFORCED_SHAPE_GATES == ()          # the score failed its bar: a hard gate ships only on his sign-off
    assert not set(bv.SHAPE_GATES) & set(bv.GATES)


def test_calibration_codx_and_penn_pass_all_five_and_mtw_fails_on_its_lower_low(qm_series):
    """His 2026-11-02 reads: CODX-1 (D 2020-04-15) and PENN-2 (D 2020-06-22) "fit perfectly"; MTW 10-30 is "not a
    breakout ... not really making higher lows" (a swing low at 21.09, then 21.05)."""
    rows = {r["eid"]: rr for r, _, rr in qm_series}
    for eid, d in (("731", "2020-04-15"), ("1265", "2020-06-22")):
        rr = rows[eid]
        b = _bars(rr[:[x["date"] for x in rr].index(d) + 1])
        sg, _ = _shape(b)
        assert all(sg[k]["pass"] for k in bv.SHAPE_GATES), (eid, {k: sg[k]["pass"] for k in bv.SHAPE_GATES})
    m = list(csv.DictReader(open(QM / "mtw_bars.csv")))
    b = _bars(m, keys=("open_price", "high_price", "low_price", "close", "volume"), dkey="trade_date")
    sg, _ = _shape(b, b.dates.index(date(2026, 10, 30)))
    assert [k for k in bv.SHAPE_GATES if not sg[k]["pass"]] == ["no_lower_low"]
    assert sg["no_lower_low"]["value"]["undercut_swing_lows"] == [["2026-10-09", 21.09]]


def test_the_list_is_unchanged_while_no_shape_gate_is_enforced(graded):
    for g, b in graded:
        v = bv.v1_gates(b, len(b) - 1, rs_best=99.0)
        assert v["ok"] and set(v["gates"]) == set(bv.GATES), g.ticker      # every graded name WAS on the list


def test_shape_gates_read_only_bars_up_to_d(graded):
    g, b = graded[0]
    D = len(b) - 6
    want, _ = _shape(b, D)
    junk = cb.daily_bars_from_arrays(b.dates, *[np.concatenate([np.asarray(x[:D + 1], float), np.full(5, 1e6)])
                                                for x in (b.o, b.h, b.l, b.c, b.v)])
    got, _ = _shape(junk, D)
    assert got == want


def test_ema_series_ends_on_ema_at(graded):
    _, b = graded[0]
    D = len(b) - 1
    assert bv.ema_series(b.c, D, 21)[D] == pytest.approx(bv.ema_at(b.c, D, 21), rel=1e-12)


def test_the_revised_set_on_his_grades_10_of_17_no_rejected_9_of_11_good_ok_kept(graded, monkeypatch):
    """The MEASURED result on his 2026-11-11 REGRADE (17 no / 11 good-ok; `03_score_regraded.out`), every name pinned."""
    monkeypatch.setattr(bv, "ENFORCED_SHAPE_GATES", REVISED)
    kept = {(g.ticker, g.grade) for g, b in graded if bv.v1_gates(b, len(b) - 1, rs_best=99.0)["ok"]}
    no_kept = sorted(t for t, gr in kept if gr == "no")
    assert no_kept == ["ABCL", "CVLT", "FNKO", "MANE", "NVAX", "RSKD", "SIG"]   # the `no` charts it does NOT reject
    good_ok = {g.ticker for g, _ in graded if g.grade in ("good", "ok")}
    dropped = sorted(good_ok - {t for t, _ in kept})
    assert dropped == ["BHC", "PAR"] and len(good_ok) == 11         # 9 of 11 kept
    failed = {g.ticker: bv.v1_gates(b, len(b) - 1, rs_best=99.0)["failed"] for g, b in graded if g.grade == "no"}
    assert failed["MRNA"] == ["not_extended"] and failed["SPCE"] == ["not_extended"]
    assert all(failed[t] == ["not_extended", "tight10"] for t in ("VFC", "ONT", "CHTR", "DUOL", "PLNT", "ASO", "OUST"))


def test_amendment_2_on_his_grades_13_of_17_no_rejected_and_249_of_qullamaggies_263(graded, qm_series, monkeypatch):
    """Round 2 (`07_score_amendment2.out`): the four gates sized against Qullamaggie's buys. SIG, DUOL, CVLT, OUST pass
    — so DoD (1) is still red and NOTHING is enforced."""
    assert bv.SHAPE_GATES_V2 == ("in_base", "ema21_not_falling", "ema21_vs_sma50", "low_not_today")
    assert (bv.SHAPE_BASE_ABOVE_ADR_MAX, bv.SHAPE_E21_S50_ADR_MIN, bv.SHAPE_FALLING_WINDOWS) == (0.0, -1.0, (5, 10, 20))
    monkeypatch.setattr(bv, "ENFORCED_SHAPE_GATES", bv.SHAPE_GATES_V2)
    kept = {(g.ticker, g.grade) for g, b in graded if bv.v1_gates(b, len(b) - 1, rs_best=99.0)["ok"]}
    assert sorted(t for t, gr in kept if gr == "no") == ["CVLT", "DUOL", "OUST", "SIG"]
    good_ok = {g.ticker for g, _ in graded if g.grade in ("good", "ok")}
    assert sorted(good_ok - {t for t, _ in kept}) == ["BHC", "PAR"]
    failed = {g.ticker: bv.v1_gates(b, len(b) - 1, rs_best=99.0)["failed"] for g, b in graded}
    assert failed["ABCL"] == ["ema21_not_falling"] and failed["NVAX"] == ["ema21_not_falling"]
    assert failed["RSKD"] == failed["FNKO"] == failed["MANE"] == ["low_not_today"]
    on = [r for r, b, _ in qm_series
          if bv.v1_gates(b, len(b) - 1, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))["ok"]]
    assert (len(on), sum(r["big_winner"] == "1" for r in on)) == (249, 25)
    assert ("SI", "2021-01-22") not in {(r["sym"], r["E"]) for r in on}          # the one big winner it drops


def test_the_first_set_keeps_only_6_of_his_11_good_ok_and_108_of_qullamaggies_buys(graded, monkeypatch):
    monkeypatch.setattr(bv, "ENFORCED_SHAPE_GATES", bv.SHAPE_GATES)
    kept = {(g.ticker, g.grade) for g, b in graded if bv.v1_gates(b, len(b) - 1, rs_best=99.0)["ok"]}
    assert sorted(t for t, gr in kept if gr == "no") == ["SIG"]
    assert sorted(t for t, gr in kept if gr in ("good", "ok")) == ["BILL", "BLKB", "HAE", "OSCR", "PAYS", "PLSE"]


def test_recall_on_qullamaggies_buys_263_unenforced_225_under_the_revised_set_108_under_all_five(qm_series, monkeypatch):
    def count():
        on = [r for r, b, _ in qm_series
              if bv.v1_gates(b, len(b) - 1, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))["ok"]]
        return len(on), sum(r["big_winner"] == "1" for r in on), {(r["sym"], r["E"]) for r in on}
    assert count()[:2] == (263, 26)                                # the signed-off scorecard, untouched
    monkeypatch.setattr(bv, "ENFORCED_SHAPE_GATES", REVISED)
    n, big, on = count()
    assert (n, big) == (225, 24)
    assert ("APT", "2020-06-17") not in on and ("JMIA", "2020-11-18") not in on   # the two big winners it drops
    monkeypatch.setattr(bv, "ENFORCED_SHAPE_GATES", bv.SHAPE_GATES)
    assert count()[:2] == (108, 11)


@pytest.mark.xfail(strict=True, reason="DoD (1) of #717: RED on 2026-11-11 — SIG, DUOL, CVLT and OUST pass amendment 2 "
                                       "(the best set that keeps Qullamaggie's buys near 263); rejecting them costs "
                                       "16-17 of his buys each (docs/analysis/cb_shape_gates_2026-11-11.md, round 2)")
def test_dod_1_the_list_rejects_every_chart_he_graded_no(graded, monkeypatch):
    monkeypatch.setattr(bv, "ENFORCED_SHAPE_GATES", bv.SHAPE_GATES_V2)
    survivors = [g.ticker for g, b in graded if g.grade == "no" and bv.v1_gates(b, len(b) - 1, rs_best=99.0)["ok"]]
    assert survivors == []
