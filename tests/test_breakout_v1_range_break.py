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
# The 22 more High-tier buys the 4% daily-range floor (operator 2026-11-12, was 2.1%) now stops at the `adr` gate alone
# (ADR20 in the comment) — every other gate still passes for each. He holds them as buys; the floor is the ruling.
ADR_DROPS = {("SEDG", "2017-09-27"): "adr", ("AMD", "2019-12-12"): "adr", ("AMD", "2020-06-09"): "adr",    # 3.2 / 2.8 / 3.96%
             ("JD", "2020-08-17"): "adr", ("TWTR", "2020-09-22"): "adr", ("TTD", "2021-02-19"): "adr",     # 3.1 / 3.4 / 3.88%
             ("DVN", "2021-11-24"): "adr", ("MU", "2021-12-21"): "adr", ("FCX", "2023-01-06"): "adr",      # 3.7 / 3.3 / 3.1%
             ("LI", "2023-04-17"): "adr", ("PBR", "2019-10-22"): "adr", ("DHT", "2019-12-19"): "adr",      # 3.3 / 2.1 / 3.0%
             ("AVLR", "2020-01-02"): "adr", ("DT", "2020-01-06"): "adr", ("AMD", "2020-01-17"): "adr",     # 3.1 / 3.5 / 2.6%
             ("SLV", "2021-01-28"): "adr", ("ALB", "2021-05-27"): "adr", ("ALB", "2021-07-09"): "adr",     # 2.2 / 3.6 / 2.4%
             ("NET", "2021-09-16"): "adr", ("AMD", "2021-10-13"): "adr", ("ABNB", "2021-11-05"): "adr",    # 3.3 / 2.7 / 2.5%
             ("NUE", "2022-01-05"): "adr"}                                                                  # 3.8%
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


# High-tier buys the list holds whose break day is under the 2026-11-02 volume bar (1.2x the last 10 sessions) — they
# FIRE since his 2026-11-11 "drop it" (volume is recorded, not required).
VOLUME_MISSES = {("LVGO", "2020-09-25")}      # (AMD 01-17 and AVLR 01-02 are now dropped by the 4% daily-range floor)


def test_the_56_listable_high_confidence_qullamaggie_buys_are_listed_the_night_before_and_all_56_fire_on_the_break_day(high_tier):
    """'Fire' = the DAILY bar of the break day takes out the level — a proxy of the buy, not the live intraday entry
    (opening range, the stop-width rule). Volume is recorded, not required (his 2026-11-11 "drop it")."""
    assert len(high_tier) == 84 and sum(r["set"] == "dated" for r, *_ in high_tier) == 53
    assert {_key(r) for r, *_ in high_tier if not r["rs_best"]} == RANK_NOT_MEASURED
    listed, fired, missed = [], [], set()
    for r, b, D, g in high_tier:
        if _key(r) in FLOOR_LOSSES:
            continue
        if _key(r) in ADR_DROPS:
            assert g["failed"] == ["adr"], (_key(r), g["failed"])          # only the 4% floor stops it
            continue
        assert g["ok"] is True and g["failed"] == [], (_key(r), g["failed"])
        # the range high is the rated buy point (ratings.tsv keeps 4 significant figures); the level is never above it
        assert g["range"]["value"]["level"] == pytest.approx(float(r["buy_point"]), rel=5e-4), _key(r)
        assert g["range"]["value"]["len"] == int(r["range_len"]) >= bv.RANGE_MIN_LEN, _key(r)
        assert g["level"] == min(bv.settled_level(b.h, b.l, b.c, D)[0], g["range"]["value"]["level"]) <= g["level5"], _key(r)
        listed.append(_key(r))
        t = bv.breakout_triggered({"h": float(b.h[D + 1]), "v": float(b.v[D + 1])}, g)
        assert t["level_pass"] is True, _key(r)                        # every one takes its level out on the break day
        assert t["fired"] is True, _key(r)
        fired.append(_key(r))
        if not t["volume_pass"]:
            missed.add(_key(r))
    assert len(listed) == 56 and len(fired) == 56 and missed == VOLUME_MISSES
    for name in (("ALB", "2021-05-27"), ("ALB", "2021-07-09"), ("NUE", "2022-01-05"), ("ABNB", "2021-11-05"),     # prior move 22-30%
                 ("DKNG", "2020-08-18"), ("FSLY", "2020-09-21"), ("AMD", "2021-10-13"), ("LCID", "2022-01-07"),    # under the 50-day
                 ("NVAX", "2021-04-13"), ("WKHS", "2020-08-03"), ("NET", "2020-06-15"), ("DVN", "2021-11-24")):
        assert name in fired or name in ADR_DROPS, name       # the six now under 4% ADR20 are in ADR_DROPS


def test_the_five_buys_the_unchanged_floors_cost_are_named_with_the_floor_that_stops_each(high_tier):
    got = {_key(r): g["failed"] for r, _, _, g in high_tier if not g["ok"]}
    assert {k: v for k, v in got.items() if v != ["adr"]} == FLOOR_LOSSES
    assert {k for k, v in got.items() if v == ["adr"]} == set(ADR_DROPS)
    assert (bv.MIN_PRICE, bv.MIN_DOLLAR_VOL, bv.MIN_BARS, bv.ADR_MIN) == (2.0, 5_000_000.0, 86, 0.04)   # not moved


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
    t = bv.breakout_triggered({"h": 20.50, "v": 0.5 * g["vol_bar"]}, ok)                       # a below-volume break
    assert t["fired"] is True and t["volume_pass"] is False                                    # still buys (2026-11-11)
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


# Every Qullamaggie buy the wick rule turns from not-fired to fired (14_wick_rule.out, X = 0.5): (ticker, D, E, level, 5-day high).
WICK_GAINS_DATED = {("APT", "2020-02-21"): (5.40, 5.98, "2020-02-13"), ("CRWD", "2020-09-18"): (32.31, 33.46, "2020-09-16"),
                    ("NVAX", "2020-12-17"): (130.9, 135.5, "2020-12-14"), ("DKNG", "2021-02-26"): (61.63, 63.25, "2021-02-22"),
                    ("LAC", "2021-09-30"): (22.46, 22.8, "2021-09-23")}


def test_the_wick_rule_apt_0221_is_bought_through_the_settled_range_not_the_spike():
    """His 2026-10-18 note, "big upper wick then settling lower -> ignore part of the wick". APT 2020-02-13 opened 5.90,
    made 5.98 and closed 5.18; the days after topped at 5.40. Qullamaggie bought through ~5.40 on 02-21 (high 5.77) —
    a big winner the 5-day high (5.98) never fired on. The four other dated buys the rule adds are pinned with it."""
    assert bv.LEVEL_WICK_MIN == 0.5
    by = defaultdict(list)
    with gzip.open(FX / "bars.psv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by[r["eid"]].append(r)
    seen = {}
    for r in csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"):
        k = (r["ticker"], r["E"])
        if k not in WICK_GAINS_DATED:
            continue
        rr = sorted(by[r["eid"]], key=lambda x: x["date"])
        ds = [date.fromisoformat(x["date"]) for x in rr]
        b = cb.daily_bars_from_arrays(ds, *[[float(x[c]) for x in rr] for c in "ohlcv"])
        D = ds.index(date.fromisoformat(r["D"]))
        g = bv.v1_gates(b, D, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))
        lvl, l5, wick = WICK_GAINS_DATED[k]
        assert g["ok"] and g["level_source"] == "settled_after_wick" and g["wick_date"] == wick, k
        assert g["level"] == pytest.approx(lvl, rel=1e-3) and g["level5"] == pytest.approx(l5, rel=1e-3), k
        bar = {"h": float(b.h[D + 1]), "v": float(b.v[D + 1])}
        assert bv.breakout_triggered(bar, g)["fired"] is True, k
        assert bv.breakout_triggered(bar, dict(g, level=g["level5"]))["level_pass"] is False, k     # the spike high was never taken out
        seen[k] = r["big_winner"]
    assert set(seen) == set(WICK_GAINS_DATED) and seen[("APT", "2020-02-21")] == "1"


# The four big winners the day's volume kept out (0.89x / 1.04x / 0.80x / 0.96x the 10-day average); at the minute they
# crossed the level the live pace was 0.38 / 0.60 / 1.00 / 0.86 against the 1.2 it needed (15_pace_at_cross.out).
VOLUME_MISSED_BIG_WINNERS = {("DOYU", "2020-08-24"), ("MDB", "2020-09-21"), ("NVDA", "2020-09-25"), ("JMIA", "2021-01-12")}


def test_the_four_big_winners_the_volume_bar_kept_out_fire_on_the_price_break():
    """His ruling 2026-11-11: "drop it" — buy on the price break alone."""
    by = defaultdict(list)
    with gzip.open(FX / "bars.psv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by[r["eid"]].append(r)
    seen = set()
    for r in csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"):
        k = (r["ticker"], r["E"])
        if k not in VOLUME_MISSED_BIG_WINNERS:
            continue
        assert r["big_winner"] == "1", k
        rr = sorted(by[r["eid"]], key=lambda x: x["date"])
        ds = [date.fromisoformat(x["date"]) for x in rr]
        b = cb.daily_bars_from_arrays(ds, *[[float(x[c]) for x in rr] for c in "ohlcv"])
        D = ds.index(date.fromisoformat(r["D"]))
        g = bv.v1_gates(b, D, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))
        t = bv.breakout_triggered({"h": float(b.h[D + 1]), "v": float(b.v[D + 1])}, g)
        assert g["ok"] and t["level_pass"] and t["volume_pass"] is False and t["fired"] is True, k
        seen.add(k)
    assert seen == VOLUME_MISSED_BIG_WINNERS


def test_the_wick_rule_only_acts_on_a_day_that_closed_in_the_lower_half_and_is_not_the_last_day():
    h = np.array([10.0, 10.2, 12.0, 10.5, 10.4, 10.6])
    lo = np.array([9.8, 9.9, 10.0, 10.1, 10.0, 10.2])
    c = np.array([9.9, 10.1, 10.2, 10.3, 10.2, 10.5])              # day 2: high 12.0, close 10.2 -> wick 1.8 of a 2.0 range
    assert bv.settled_level(h, lo, c, 5) == (10.6, 12.0, 2)        # the high of the sessions after the spike
    c2 = c.copy()
    c2[2] = 11.5                                                   # closed in the upper half: a real high, kept
    assert bv.settled_level(h, lo, c2, 5) == (12.0, 12.0, None)
    h3 = np.array([10.0, 10.2, 10.3, 10.5, 10.4, 12.0])            # the spike is the last day: nothing after it to settle
    c3 = np.array([9.9, 10.1, 10.2, 10.3, 10.2, 10.3])
    assert bv.settled_level(h3, lo, c3, 5) == (12.0, 12.0, None)


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
