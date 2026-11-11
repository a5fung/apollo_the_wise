"""Breakout v1 — the INITIAL RULE SET of 2026-11-11 (PENDING HIS SIGN-OFF BEFORE PAPER): buy Qullamaggie's range breaks.

Spec: `docs/analysis/cb_initial_rules_2026-11-11.md`; owner `docs/setups/consolidation_breakout.md` (change log
2026-11-11). His words: "we are trying to buy like qullamaggie ... buy his setups period". THE TARGET is the 84
high-confidence Qullamaggie buys (`docs/analysis/cb_qm_buy_confidence_2026-11-11.md`, `high_tier.tsv`):
  * the 80 the unchanged safety floors allow are LISTED the night before and BOUGHT on their break day, at the rated
    buy point (the range high) — pinned by name;
  * the 4 the floors cost are pinned by name and by the floor that stops each (his call, never silently fixed);
  * the trigger never fires without the range high being taken out.
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
# The four High-tier Qullamaggie buys the UNCHANGED floors keep off the list (his call whether to move a floor).
FLOOR_LOSSES = {("BNGO", "2019-12-30"): ["universe"],      # 20-session median dollar volume $1.5M (floor $5M)
                ("INO", "2020-01-21"): ["universe"],       # $3.6M
                ("HEXO", "2020-08-13"): ["universe"],      # $4.4M
                ("PLTR", "2021-01-22"): ["history"]}       # under 86 sessions since listing
# Unranked nights (not in the 2026-11-02 cross-section): the strength rank cannot be measured from the fixtures, so the
# rank is passed; FCEL's raw price that night was ~$1.95 (the $2 floor would stop it live) — stated, not asserted.
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


def test_the_80_listable_high_confidence_qullamaggie_buys_are_listed_the_night_before_and_bought_on_the_break_day(high_tier):
    assert len(high_tier) == 84 and sum(r["set"] == "dated" for r, *_ in high_tier) == 53
    assert {_key(r) for r, *_ in high_tier if not r["rs_best"]} == RANK_NOT_MEASURED
    listed, bought = [], []
    for r, b, D, g in high_tier:
        if _key(r) in FLOOR_LOSSES:
            continue
        assert g["ok"] is True and g["failed"] == [], (_key(r), g["failed"])
        # the range high IS the rated buy point (ratings.tsv keeps 4 significant figures)
        assert g["level"] == pytest.approx(float(r["buy_point"]), rel=5e-4), _key(r)
        assert g["gates"]["range"]["value"]["len"] == int(r["range_len"]) >= bv.RANGE_MIN_LEN, _key(r)
        listed.append(_key(r))
        t = bv.breakout_triggered({"h": float(b.h[D + 1]), "c": float(b.c[D + 1]), "v": float(b.v[D + 1])}, g)
        assert t["fired"] is True and t["level_pass"] and t["volume_pass"], _key(r)
        bought.append(_key(r))
    assert len(listed) == len(bought) == 80
    for name in (("ALB", "2021-05-27"), ("ALB", "2021-07-09"), ("NUE", "2022-01-05"), ("ABNB", "2021-11-05"),     # prior move 22-30%
                 ("DKNG", "2020-08-18"), ("FSLY", "2020-09-21"), ("AMD", "2021-10-13"), ("LCID", "2022-01-07"),    # under the 50-day
                 ("NVAX", "2021-04-13"), ("WKHS", "2020-08-03"), ("NET", "2020-06-15"), ("DVN", "2021-11-24")):
        assert name in bought, name


def test_the_four_buys_the_unchanged_floors_cost_are_named_with_the_floor_that_stops_each(high_tier):
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


def test_the_level_is_the_range_high_and_nothing_fires_without_taking_it_out():
    b = _base()
    g = bv.v1_gates(b, len(b) - 1, rs_best=99.0)
    rng = g["gates"]["range"]
    assert rng["pass"] is True and g["level"] == rng["value"]["level"] == 20.0 and rng["value"]["len"] >= 10
    ok = dict(g, ok=True)
    big = 10 * g["vol_bar"]
    assert bv.breakout_triggered({"h": 20.01, "c": 20.005, "v": big}, ok)["fired"] is True
    assert bv.breakout_triggered({"h": 20.00, "c": 19.9, "v": big}, ok)["fired"] is False      # touched, not taken out
    assert bv.breakout_triggered({"h": 20.50, "c": 19.9, "v": big}, ok)["fired"] is False      # a daily bar must close above it
    assert bv.breakout_triggered({"h": 20.50, "c": 20.4, "v": 0.99 * g["vol_bar"]}, ok)["fired"] is False   # under the 20-session mean
    assert bv.breakout_triggered({"h": 19.99, "v": big}, ok)["fired"] is False                 # high volume alone never buys


def test_no_range_means_no_level_and_no_buy():
    n = 160                                                  # a straight run, new highs to the last bar: no range
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    c = np.linspace(10.0, 30.0, n)
    b = cb.DailyBars(dates=days, o=c.copy(), h=c * 1.01, l=c * 0.99, c=c, v=np.full(n, 1_000_000.0))
    g = bv.v1_gates(b, n - 1, rs_best=99.0)
    assert "range" in g["failed"] and g["ok"] is False and g["level"] is None and g["level5"] > 0
    assert bv.range_levels(np.asarray(b.h), np.asarray(b.l), n - 1) == []
    assert bv.breakout_triggered({"h": 1e9, "c": 1e9, "v": 1e12}, dict(g, ok=True))["fired"] is False


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


def test_the_live_entry_rests_its_buy_at_the_range_high_never_under_it():
    """`breakout_v1_entry.evaluate` buys through max(the 5-minute opening-range high, the list row's level). The list
    row's level is now the range high, so an opening range UNDER it rests the buy at the range high (no buy on an
    opening-range break alone), and one above it rests at the opening-range high (still above the range high)."""
    bars = [_bar(m, 9.9, 10.00, 9.85, 9.9, 5e4) for m in range(6)]
    mins = be.bars_by_minute(bars, TODAY, 5)
    st = be.evaluate(mins, list_level=10.40, adr20=0.08, vol_bar=1e5, last_completed=5)
    assert st["orh5"] == 10.00 and st["level"] == 10.40                       # the range high, above the opening range
    st2 = be.evaluate(mins, list_level=9.95, adr20=0.08, vol_bar=1e5, last_completed=5)
    assert st2["level"] == 10.00 >= 9.95                                      # never under the range high
    assert be.first_break(mins, level=st["level"], vol_bar=1e5, from_minute=5) is None    # 10.00 never reached 10.40
