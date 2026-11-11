"""Breakout v1 — the INITIAL RULE SET of 2026-11-11 (PENDING HIS SIGN-OFF BEFORE PAPER): keep Qullamaggie's buys.

Spec: `docs/analysis/cb_initial_rules_2026-11-11.md`; owner `docs/setups/consolidation_breakout.md` (change log
2026-11-11). His words: "we are trying to buy like qullamaggie ... buy his setups period". THE TARGET is Qullamaggie's
buys; the 84 high-confidence ones (`docs/analysis/cb_qm_buy_confidence_2026-11-11.md`, `high_tier.tsv`) shaped it:
  * the 79 the unchanged safety floors allow are LISTED the night before (63 under the 2026-11-02 rules) and 76 fire on
    their break day — pinned by name; the 3 that do not are short of his 1.2x 10-day volume bar, named;
  * the 5 the floors cost are pinned by name and by the floor that stops each (his call, never silently fixed);
  * the range high is MEASURED on every name (the rated buy point) and the level is the LOWER of it and the 5-day high —
    a missing range never takes a name off the list, and no buy the 5-day level made is lost.
"""
from __future__ import annotations

import csv
import gzip
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence.broker import breakout_v1_entry as be

FX = Path(__file__).parent / "fixtures" / "qm_breakout_scorecard"
# The five High-tier Qullamaggie buys the UNCHANGED floors keep off the list (his call whether to move a floor).
FLOOR_LOSSES = {("BNGO", "2019-12-30"): ["universe"],      # 20-session median dollar volume $1.5M (floor $5M)
                ("INO", "2020-01-21"): ["universe"],       # $3.6M
                ("HEXO", "2020-08-13"): ["universe"],      # $4.4M
                ("FCEL", "2020-02-10"): ["universe"],      # raw close $1.72 at D, under the $2 floor (dollar volume $42.6M)
                ("PLTR", "2021-01-22"): ["history"]}       # under 86 sessions since listing
# Unranked nights (not in the 2026-11-02 cross-section): the strength rank cannot be measured from the fixtures, so the
# rank is passed. A raw close is derived for FCEL and SLV from a neighbouring ranked night (12_build_high_fixture.py).
RANK_NOT_MEASURED = {("BNGO", "2019-12-30"), ("INO", "2020-01-21"), ("FCEL", "2020-02-10"), ("HEXO", "2020-08-13"),
                     ("PLTR", "2021-01-22"), ("SLV", "2021-01-28")}


@pytest.fixture(scope="module")
def high_tier():
    """[(row, DailyBars, D, v1_gates at D)] for the 84 high-confidence Qullamaggie buys."""
    by = defaultdict(list)
    for name in ("bars.psv.gz", "bars_undated_widened.psv.gz"):
        with gzip.open(FX / name, "rt") as f:
            for r in csv.DictReader(f, delimiter="|"):
                by[(name == "bars.psv.gz", r["eid"])].append(r)
    out = []
    for r in csv.DictReader(open(FX / "high_tier.tsv"), delimiter="\t"):
        rr = sorted(by[(r["set"] == "dated", r["eid"])], key=lambda x: x["date"])
        ds = [date.fromisoformat(x["date"]) for x in rr]
        b = cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"])
        D = ds.index(date.fromisoformat(r["D"]))
        assert ds[D + 1] == date.fromisoformat(r["E"])
        g = bv.v1_gates(b, D, rs_best=float(r["rs_best"]) if r["rs_best"] else 99.0,
                        raw_close=float(r["raw_close_D"]) if r["raw_close_D"] else None)
        out.append((r, b, D, g))
    return out


def _key(r):
    return (r["ticker"], r["E"])


# High-tier buys the list holds whose break day is under his 2026-11-02 volume bar (1.2x the last 10 sessions).
VOLUME_MISSES = {("AMD", "2020-01-17"), ("AVLR", "2020-01-02"), ("LVGO", "2020-09-25")}


def test_the_79_listable_high_confidence_qullamaggie_buys_are_listed_the_night_before_and_76_fire_on_the_break_day(high_tier):
    """'Fire' = the DAILY bar of the break day takes out the level on volume at or above the bar — a proxy of the buy,
    not the live intraday entry (opening range, volume pace, the stop-width rule)."""
    assert len(high_tier) == 84 and sum(r["set"] == "dated" for r, *_ in high_tier) == 53
    assert {_key(r) for r, *_ in high_tier if not r["rs_best"]} == RANK_NOT_MEASURED
    listed, fired, missed = [], [], set()
    for r, b, D, g in high_tier:
        if _key(r) in FLOOR_LOSSES:
            continue
        assert g["ok"] is True and g["failed"] == [], (_key(r), g["failed"])
        # the range high is the rated buy point (ratings.tsv keeps 4 significant figures); the level is never above it
        assert g["range"]["value"]["level"] == pytest.approx(float(r["buy_point"]), rel=5e-4), _key(r)
        assert g["range"]["value"]["len"] == int(r["range_len"]) >= bv.RANGE_MIN_LEN, _key(r)
        assert g["level"] == min(g["level5"], g["range"]["value"]["level"]), _key(r)
        listed.append(_key(r))
        t = bv.breakout_triggered({"h": float(b.h[D + 1]), "v": float(b.v[D + 1])}, g)
        assert t["level_pass"] is True, _key(r)                        # every one takes its level out on the break day
        (fired.append(_key(r)) if t["fired"] else missed.add(_key(r)))
    assert len(listed) == 79 and len(fired) == 76 and missed == VOLUME_MISSES
    for name in (("ALB", "2021-05-27"), ("ALB", "2021-07-09"), ("NUE", "2022-01-05"), ("ABNB", "2021-11-05"),     # prior move 22-30%
                 ("DKNG", "2020-08-18"), ("FSLY", "2020-09-21"), ("AMD", "2021-10-13"), ("LCID", "2022-01-07"),    # under the 50-day
                 ("NVAX", "2021-04-13"), ("WKHS", "2020-08-03"), ("NET", "2020-06-15"), ("DVN", "2021-11-24")):
        assert name in fired, name


def test_the_five_buys_the_unchanged_floors_cost_are_named_with_the_floor_that_stops_each(high_tier):
    got = {_key(r): g["failed"] for r, _, _, g in high_tier if not g["ok"]}
    assert got == FLOOR_LOSSES
    assert (bv.MIN_PRICE, bv.MIN_DOLLAR_VOL, bv.MIN_BARS, bv.ADR_MIN) == (2.0, 5_000_000.0, 86, 0.021)   # not moved


def _base(n=160, top=20.0):
    """A run from 10 to `top`, then a flat 15-session range under it (high `top`, low 0.95 x top)."""
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    c = np.concatenate([np.linspace(10.0, top * 0.99, n - 15), np.full(15, top * 0.97)])
    h, lo = c * 1.01, c * 0.99
    h[n - 15:] = top
    lo[n - 15:] = top * 0.95
    return cb.DailyBars(dates=days, o=c.copy(), h=h, l=lo, c=c, v=np.full(n, 1_000_000.0))


def test_a_range_is_measured_and_the_level_is_the_lower_of_the_range_high_and_the_5_day_high():
    b = _base()
    g = bv.v1_gates(b, len(b) - 1, rs_best=99.0)
    rng = g["range"]
    assert "range" not in g["gates"] and "range" not in bv.GATES              # measured, never a gate
    assert rng["pass"] is True and rng["value"]["level"] == 20.0 and rng["value"]["len"] >= 10
    assert g["level"] == min(g["level5"], 20.0) == 20.0
    ok = dict(g, ok=True)
    big = 10 * g["vol_bar"]
    assert bv.breakout_triggered({"h": 20.01, "v": big}, ok)["fired"] is True
    assert bv.breakout_triggered({"h": 20.00, "v": big}, ok)["fired"] is False                 # touched, not taken out
    assert bv.breakout_triggered({"h": 20.50, "v": 0.99 * g["vol_bar"]}, ok)["fired"] is False   # under 1.2x the last 10
    assert bv.breakout_triggered({"h": 19.99, "v": big}, ok)["fired"] is False                 # volume alone never buys


def test_no_range_keeps_the_name_on_the_list_at_its_5_day_high():
    n = 160                                                  # a straight run, new highs to the last bar: no range
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    c = np.linspace(10.0, 30.0, n)
    b = cb.DailyBars(dates=days, o=c.copy(), h=c * 1.01, l=c * 0.99, c=c, v=np.full(n, 1_000_000.0))
    g = bv.v1_gates(b, n - 1, rs_best=99.0)
    assert g["range"]["pass"] is False and "range" not in g["failed"]
    assert g["level"] == g["level5"] == pytest.approx(30.0 * 1.01) and g["level_source"] == "five_day"
    assert bv.range_levels(np.asarray(b.h), np.asarray(b.l), n - 1) == []


def test_range_levels_reads_only_bars_up_to_d():
    b = _base()
    D = len(b) - 6
    want = bv.range_levels(np.asarray(b.h), np.asarray(b.l), D)
    junk_h = np.concatenate([np.asarray(b.h)[:D + 1], np.full(5, 1e6)])
    junk_l = np.concatenate([np.asarray(b.l)[:D + 1], np.full(5, 1e-6)])
    assert bv.range_levels(junk_h, junk_l, D) == want and want


_ET = ZoneInfo("America/New_York")
TODAY = date(2026, 11, 2)


def _bar(m, o, h, lo, c, v):
    return {"t_et": datetime(TODAY.year, TODAY.month, TODAY.day, 9, 30, tzinfo=_ET) + timedelta(minutes=m),
            "open": o, "high": h, "low": lo, "close": c, "volume": v}


def test_the_live_entry_rests_its_buy_at_the_list_level_never_under_it():
    """`breakout_v1_entry.evaluate` (unchanged) buys through max(the 5-minute opening-range high, the list row's level):
    an opening range UNDER the level rests the buy at the level, one above it at the opening-range high."""
    bars = [_bar(m, 9.9, 10.00, 9.85, 9.9, 5e4) for m in range(6)]
    mins = be.bars_by_minute(bars, TODAY, 5)
    st = be.evaluate(mins, list_level=10.40, adr20=0.08, vol_bar=1e5, last_completed=5)
    assert st["orh5"] == 10.00 and st["level"] == 10.40                       # the range high, above the opening range
    st2 = be.evaluate(mins, list_level=9.95, adr20=0.08, vol_bar=1e5, last_completed=5)
    assert st2["level"] == 10.00 >= 9.95                                      # never under the range high
    assert be.first_break(mins, level=st["level"], vol_bar=1e5, from_minute=5) is None    # 10.00 never reached 10.40
