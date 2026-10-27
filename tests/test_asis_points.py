"""Tests for the #705 as-is read, step 5 (scripts/probes/_705_asis_1026/asis_common.py + 01_points.py; the plan's §10 step-5 list).
Synthetic fixtures only: no apollo_data, no machine path. CI collects tests/ only, so the file lives here rather than beside the modules.

Covers: synthetic minute days with known opens / k-minute highs / prior-day levels / swings / closes -> exactly the hand-listed points;
every bracket type narrows the reachable set correctly (incl. the 2-5 / 6+ boundary, the clock-before-open and after-close flags); the
daily-only fallback; the export fallback (only when the primary has no bar in the window); read_windows on a fixture whose last sighting
is blip-filled, and hold_sessions; no swing on equal neighbours, no VWAP cross on equality, the strict cross; the raw factor (exact /
carried through a split / partial / missing, the seal on the raw file and the split list, a split inside the window, F10 and dist_round in
raw price); merged rows (the mean of the levels, our_length per tag); no F9 rows; the run gates (dry run complete with 0 MISMATCH, pins
below the marker, outputs absent); the alias extension; the seal and the forbidden-folder guard raise; the identifier scan fails on a
planted forbidden name and passes on `average`; the fresh-interpreter import test (fails on a planted import of a rule-folder file);
every copied helper matches its source byte for byte (after the one declared parameter rename).
"""
from __future__ import annotations

import ast
import gzip
import importlib.util
import io
import os
import subprocess
import sys
import tokenize
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
ASIS = REPO / "scripts" / "probes" / "_705_asis_1026"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load("asis_common", ASIS / "asis_common.py")
P = _load("asis_points01", ASIS / "01_points.py")


# ═════════════════════════════════════════════════════════════════════════════════════════════ fixtures
def weekday_cal(start: str = "2019-10-01", end: str = "2020-12-31") -> list:
    d, out = date.fromisoformat(start), []
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


CAL = weekday_cal()
S = C.Sessions(CAL)


def synthetic_day(anchors: list, n: int = 390):
    """Closes interpolated between (minute, close) anchors and rounded to cents; open = the previous close; no wicks (high / low = max / min of
    open and close), so every cross is a hand-computable close path. Constant volume."""
    m = np.arange(n)
    xs, ys = [a for a, _ in anchors], [b for _, b in anchors]
    c = np.round(np.interp(m, xs, ys), 4)
    o = np.concatenate([[c[0]], c[:-1]])
    h, l = np.maximum(o, c), np.minimum(o, c)
    return C.minute_bars_from_lists(m, o, h, l, c, np.full(n, 1000.0))


ANCHORS = [(0, 10.00), (4, 10.20), (8, 10.00), (20, 9.90), (40, 10.30), (100, 10.40), (389, 10.10)]


def day_ctx(**over) -> dict:
    ctx = {"o": 10.00, "h": 10.40, "l": 9.90, "c": 10.10, "v": 390_000.0, "prev_h": 10.50, "prev_l": 9.92, "prev_c": 10.05,
           "short_history": False, "bar_holes": 0, "avgrange20": 0.40, "vol20": 400_000.0}
    for n in (3, 5, 10, 20, 40, 60):
        ctx[f"hi_{n}"], ctx[f"lo_{n}"], ctx[f"since_hi_{n}"], ctx[f"ret_{n}"] = 10.35, 9.50, 2, 1.0
    for n in C.SMA_SWEEP:
        ctx[f"ma_{n}"] = 10.33
    ctx.update(over)
    return ctx


def frame(idx: int, d: str, ctx: str, clock: str, full: bool = True, symbols=(), blip=()) -> "C.Frame":
    return C.Frame(idx=idx, frame_id=f"f{idx}", vid=f"v{idx}", date=d, ctx=ctx, clock=clock, full=full, symbols=list(symbols), blip_filled=list(blip))


def window(earlier, later, lo, hi, side="buy", inverted=False) -> "P.Window":
    w = P.Window(1, "XYZ", "XYZ", side, lo, hi, earlier, later, inverted, False)
    w.bracket = P.type_bracket(w, S)
    P.reachable(w, S)
    return w


def pts_by(pts, fam, which=None, direction=None, k=None):
    return [p for p in pts if p.family == fam and (which is None or p.which == which) and (direction is None or p.direction == direction)
            and (k is None or p.k == str(k))]


# ═════════════════════════════════════════════════════════════════════════════════════════════ the candidate generator
def test_hand_listed_points_full_day():
    mb = synthetic_day(ANCHORS)
    ctx = day_ctx()
    pts, nr, info = P.minute_points("2020-06-01", mb, None, None, ctx, 390, (9.90, 10.40))
    # F1 the open at minute 0
    (f1,) = pts_by(pts, "F1")
    assert (f1.minute, f1.price, f1.direction) == (0, 10.00, "level")
    # F2: the 5-minute high 10.20 is traded through from below at minute 35 (9.90 at 20 rising 0.02/min); its low 10.00 from above at 8
    (orh5_up,) = pts_by(pts, "F2", "high", "up", 5)
    assert (orh5_up.minute, orh5_up.price, orh5_up.our_length) == (35, 10.20, True)
    (orl5_dn,) = pts_by(pts, "F2", "low", "down", 5)
    assert (orl5_dn.minute, orl5_dn.price) == (8, 10.00)
    assert pts_by(pts, "F2", "high", "down", 1)[0].minute == 8       # the 1-minute high 10.00: fallen through at 8 (10.05 -> 10.00)...
    assert pts_by(pts, "F2", "high", "up", 1)[0].minute == 25        # ...and risen back through at 25 (9.98 -> 10.00)
    assert pts_by(pts, "F2", "high", "up", 15)[0].our_length is False
    # F3: the prior high 10.50 is never reached; the prior low 9.92 is crossed down at 18; the prior close 10.05 down at 7 and up at 28
    assert not pts_by(pts, "F3", "high") and nr["F3:high"] == 2
    assert pts_by(pts, "F3", "low", "down")[0].minute == 18
    assert pts_by(pts, "F3", "close", "down")[0].minute == 7
    assert pts_by(pts, "F3", "close", "up")[0].minute == 1          # 10.00 -> 10.05 at minute 1, before the drop
    # F4: the day's high 10.40 first printed at 100, the low 9.90 at 20
    assert (pts_by(pts, "F4", "high")[0].minute, pts_by(pts, "F4", "high")[0].price) == (100, 10.40)
    assert (pts_by(pts, "F4", "low")[0].minute, pts_by(pts, "F4", "low")[0].price) == (20, 9.90)
    # F5: the 5-minute bucket 20-24 is a swing low (9.90, strictly below the three buckets either side); its print at 20; never traded through
    (sw,) = pts_by(pts, "F5", "swing_low")
    assert (sw.minute, sw.price) == (20, 9.90)
    assert not pts_by(pts, "F5", "cross_low")
    (sh,) = pts_by(pts, "F5", "swing_high")                            # the bucket 100-104 holds the day's high 10.40: a swing high, printed at 100
    assert (sh.minute, sh.price) == (100, 10.40) and not pts_by(pts, "F5", "cross_high")   # never traded through after its confirmation
    # F6: the close at 389 and the market-on-close print at 385
    assert (pts_by(pts, "F6", "close")[0].minute, pts_by(pts, "F6", "close")[0].price) == (389, 10.10)
    assert pts_by(pts, "F6", "moc")[0].minute == 385
    # F7: the prior 5-session high 10.35 crossed up at 70 (10.30 at 40 rising 0.1 over 60 minutes); 20 and 60 carry our_length
    assert pts_by(pts, "F7", "high", "up", 5)[0].minute == 70
    assert pts_by(pts, "F7", "high", "up", 20)[0].our_length is True and pts_by(pts, "F7", "high", "up", 5)[0].our_length is False
    assert not pts_by(pts, "F7", "low")                               # 9.50 never reached
    # F8: the averages at 10.33 crossed up at 58; 10 and 20 flagged, 13 not
    assert pts_by(pts, "F8", "ma", "up", 10)[0].minute == 58 and pts_by(pts, "F8", "ma", "up", 10)[0].our_length is True
    assert pts_by(pts, "F8", "ma", "up", 13)[0].our_length is False
    # F9 (the band ends) is NOT a candidate row (R33): the ends live in `info` / ranges.tsv
    assert not pts_by(pts, "F9") and "F9" not in P.FAMILY_ORDER
    assert (info["range_lo"], info["range_hi"], info["range_lo_minute"], info["range_hi_minute"]) == (9.90, 10.40, 20, 100)
    # F10: the one round number inside 9.90..10.40 is 10.00 (a $10 multiple): down at 8, up at 25; price_raw = the level (factor 1)
    assert [(p.k, p.direction, p.minute, p.price_raw) for p in pts_by(pts, "F10")] == [("10", "up", 25, 10.0), ("10", "down", 8, 10.0)]
    # F11: the average traded price (equal volume = the mean of closes so far): the first down-touch is at minute 2 (hand: 10.05 > 10.025,
    # the bar's low 10.05 <= the average 10.05)
    assert pts_by(pts, "F11", "vwap", "down")[0].minute == 2
    assert info["avg_traded_price"] == pytest.approx(float(np.round(np.interp(np.arange(390), [a for a, _ in ANCHORS], [b for _, b in ANCHORS]), 4).mean()))


def test_reachable_minutes_narrow_the_points():
    mb = synthetic_day(ANCHORS)
    pts, nr, info = P.minute_points("2020-06-01", mb, 5, 120, day_ctx(), 390, (9.90, 10.40))
    assert not pts_by(pts, "F1") and nr["F1:open"] == 1                # minute 0 is outside the bracket
    assert not pts_by(pts, "F6")                                        # the close too
    assert pts_by(pts, "F4", "high")[0].minute == 100 and pts_by(pts, "F4", "low")[0].minute == 20
    assert pts_by(pts, "F2", "high", "up", 5)[0].minute == 35
    assert pts_by(pts, "F2", "low", "down", 5)[0].minute == 8           # minute 8 is inside [5, 120]
    assert pts_by(pts, "F3", "close", "down")[0].minute == 7 and pts_by(pts, "F3", "close", "up")[0].minute == 28   # the up-cross at 1 is before 5
    assert (info["range_lo"], info["range_hi"]) == (9.90, 10.40) and info["n_minutes"] == 116
    assert all(5 <= p.minute <= 120 for p in pts)
    # a bracket that starts after the swing low's print: the print is gone, the day's low too, the range begins where the bracket does
    pts2, nr2, info2 = P.minute_points("2020-06-01", mb, 30, 200, day_ctx(), 390, (9.90, 10.40))
    assert not pts_by(pts2, "F5", "swing_low") and nr2["F5:swing_low"] == 1 and not pts_by(pts2, "F4", "low")
    assert info2["range_lo"] == float(mb.l[30]) and info2["range_lo_minute"] == 30 and not pts_by(pts2, "F9")


def test_early_close_drops_after_hours_prints():
    mb = synthetic_day(ANCHORS, n=215)                                  # 210 regular minutes + 5 after-hours prints
    pts, nr, info = P.minute_points("2020-11-27", mb, None, None, day_ctx(), C.session_end_minute("2020-11-27"), (9.90, 10.40))
    assert C.session_end_minute("2020-11-27") == 210 and C.session_end_minute("2020-11-30") == 390
    assert pts_by(pts, "F6", "close")[0].minute == 209 and pts_by(pts, "F6", "moc")[0].minute == 205
    assert max(p.minute for p in pts) <= 209


def test_merge_same_minute_rows_and_round_levels():
    mb = synthetic_day(ANCHORS)
    pts, _, _ = P.minute_points("2020-06-01", mb, None, None, day_ctx(), 390, (9.90, 10.40))
    groups = P.merge_points(pts)
    assert all(len({(p.date, p.minute) for p in g}) == 1 for g in groups)
    at8 = [g for g in groups if g[0].minute == 8][0]
    assert {p.family for p in at8} >= {"F2", "F10"}                     # the 5-minute low 10.00 and the round $10 meet at minute 8
    assert sum(len(g) for g in groups) == len(pts)
    assert P.round_levels(9.9, 10.4) == [(10.0, "10")]
    assert P.round_levels(12.3, 15.6) == [(12.5, "0.5"), (13.0, "1"), (13.5, "0.5"), (14.0, "1"), (14.5, "0.5"), (15.0, "5"), (15.5, "0.5")]
    assert P.round_levels(10.0, 9.0) == []
    many = P.round_levels(100000.0, 101000.0)                           # 2,001 half-dollar levels: coarsened to $10 (101 levels)
    assert len(many) == 101 and P.round_levels.last_step == 10.0 and many[0] == (100000.0, "1000") and many[1] == (100010.0, "10")
    assert P.round_levels(9.9, 10.4) == [(10.0, "10")] and P.round_levels.last_step == 0.5


def test_density_hand_computed():
    # [10, 20]; a level at 11 (tolerance 0.11) and at 19 (0.19): 0.22 + 0.38 = 0.60 of 10
    assert P.density([(11.0, 1.0), (19.0, 1.0)], 10.0, 20.0) == pytest.approx(0.06)
    # the 10%-of-range arm: a $1 range -> 0.10; overlapping bands union once
    assert P.density([(11.0, 1.0), (11.05, 1.0)], 10.0, 20.0) == pytest.approx((11.1605 - 10.89) / 10)   # [10.89, 11.11] u [10.9395, 11.1605]
    assert P.density([], 10.0, 20.0) == 0.0
    assert P.density([(10.0, 0.0)], 10.0, 10.0) == 1.0
    assert P.tolerance(100.0, 0.5) == 1.0 and P.tolerance(1.0, 0.1) == 0.05 and P.tolerance(2.0, 3.0) == pytest.approx(0.3)


def test_daily_points_families():
    ctx = day_ctx(o=10.00, h=10.40, l=9.90, c=10.10, prev_h=10.50, prev_l=9.92, prev_c=10.05)
    pts, nr = P.daily_points("2020-06-01", ctx, ("F1", "F3", "F4", "F6", "F7", "F8", "F10"), (9.90, 10.40))
    assert all(p.minute is None and p.source == "daily_only" for p in pts)
    assert pts_by(pts, "F1")[0].price == 10.00 and pts_by(pts, "F6")[0].price == 10.10
    assert not pts_by(pts, "F3", "high") and nr["F3:high"] == 1
    assert pts_by(pts, "F3", "low")[0].direction == "down" and pts_by(pts, "F3", "close")[0].direction == "up"
    assert pts_by(pts, "F10")[0].price == 10.0 and pts_by(pts, "F10")[0].direction == "level"
    close_only, _ = P.daily_points("2020-06-01", ctx, ("F6",), (9.90, 10.40))
    assert [p.family for p in close_only] == ["F6"]


# ═════════════════════════════════════════════════════════════════════════════════════════════ brackets and reachable sets
def test_every_bracket_type_narrows_the_reachable_set():
    d1, d2, d3, d4 = "2020-06-01", "2020-06-02", "2020-06-03", "2020-06-09"
    # same day, in-session -> in-session: the later day's minutes from the earlier clock to the later clock
    w = window(frame(1, d1, "in", "10:00"), frame(2, d1, "in", "10:45"), d1, d1)
    assert w.bracket == "same_in_in" and w.reach == [(d1, 30, 75)] and not w.flags
    # same day, pre-market -> in-session: 09:30 to the later clock, pre_market_possible
    w = window(frame(1, d1, "pre", "09:05"), frame(2, d1, "in", "10:45"), d1, d1)
    assert w.bracket == "same_pre_in" and w.reach == [(d1, None, 75)] and w.flags == {"pre_market_possible"}
    # next session, in-session -> pre-market: the earlier day from its clock to the close, extended_hours_possible
    w = window(frame(1, d1, "in", "10:00"), frame(2, d2, "pre", "09:10"), d1, d1)
    assert w.bracket == "next_in_pre" and w.reach == [(d1, 30, None)] and w.flags == {"extended_hours_possible"}
    # R35: an earlier frame after the close, or a later one, also flags extended hours; a later in-session frame clocked before 09:30 is a
    # misread -> the full session, flagged (never "minute 0 only")
    w = window(frame(1, d1, "closed", "17:00"), frame(2, d2, "in", "10:15"), d2, d2)      # closed -> in is an `other` pair: the full session (§3.2)
    assert w.bracket == "next_other" and w.reach == [(d2, None, None)] and w.flags == {"extended_hours_possible", "bracket_other"}
    w = window(frame(1, d1, "in", "10:00"), frame(2, d2, "closed", "16:30"), d1, d2)
    assert "extended_hours_possible" in w.flags
    w = window(frame(1, d1, "pre", "09:05"), frame(2, d1, "in", "09:20"), d1, d1)
    assert w.bracket == "same_pre_in" and w.reach == [(d1, None, None)] and w.flags == {"pre_market_possible", "clock_before_open"}
    w = window(frame(1, d1, "in", "09:20"), frame(2, d1, "in", "10:45"), d1, d1)       # the EARLIER frame: the clip was minute 0 anyway, flag only
    assert w.reach == [(d1, None, 75)] and w.flags == {"clock_before_open_earlier"}
    # next session, in-session -> in-session: the earlier day from its clock, the later day to its clock
    w = window(frame(1, d1, "in", "10:00"), frame(2, d2, "in", "10:15"), d1, d2)
    assert w.bracket == "next_in_in" and w.reach == [(d1, 30, None), (d2, None, 45)]
    # 2-5 sessions apart: the earlier day from its clock, every full session between, the later day to its clock
    w = window(frame(1, d1, "in", "11:00"), frame(2, d3, "in", "09:50"), d1, d3)
    assert w.bracket == "sessions_2_5" and w.reach == [(d1, 90, None), (d2, None, None), (d3, None, 20)]
    # 2-5 sessions apart with a closed earlier frame and a pre-market later frame: the window already excludes both frame days
    w = window(frame(1, d1, "closed", "18:00"), frame(2, "2020-06-08", "pre", "09:00"), d2, "2020-06-05")
    assert w.bracket == "sessions_2_5" and [r[0] for r in w.reach] == [d2, d3, "2020-06-04", "2020-06-05"]
    assert all(r[1] is None and r[2] is None for r in w.reach) and w.flags == {"extended_hours_possible"}
    # the 2-5 / 6+ boundary: a gap of exactly 5 sessions (06-01 -> 06-08) is 2-5; a gap of 6 (-> 06-09) is 6+, daily resolution only
    w = window(frame(1, d1, "in", "10:00"), frame(2, "2020-06-08", "in", "10:00"), d1, "2020-06-08")
    assert w.bracket == "sessions_2_5" and not w.wide and len(w.reach) == 6 and w.reach[0] == (d1, 30, None) and w.reach[-1] == ("2020-06-08", None, 30)
    w = window(frame(1, d1, "in", "10:00"), frame(2, d4, "in", "10:00"), d1, d4)
    assert w.bracket == "sessions_6plus" and w.wide and "wide_window" in w.flags and len(w.reach) == 7
    w = window(frame(1, d1, "in", "10:00"), frame(2, "2020-06-10", "in", "10:00"), d1, "2020-06-10")
    assert w.bracket == "sessions_6plus" and w.wide and "wide_window" in w.flags and len(w.reach) == 8
    # other clock pairs (pre -> pre on the same day): the full sessions, bracket_other, no clipping
    w = window(frame(1, d1, "pre", "09:00"), frame(2, d1, "pre", "09:20"), d1, d1)
    assert w.bracket == "same_other" and w.reach == [(d1, None, None)] and "bracket_other" in w.flags
    w = window(frame(1, d1, "in", "10:00"), frame(2, d2, "closed", "17:00"), d1, d2)
    assert w.bracket == "next_other" and w.reach == [(d1, None, None), (d2, None, None)]
    # inverted: none
    w = window(frame(1, d1, "closed", "17:00"), frame(2, d1, "closed", "18:00"), d1, d1, inverted=True)
    assert w.bracket == "inverted" and w.reach == [] and w.flags == {"inverted"}
    # the clock misreads (R13): order broken -> the full session, flagged; zero width keeps its one minute; no clock -> full, flagged
    w = window(frame(1, d1, "in", "10:45"), frame(2, d1, "in", "10:00"), d1, d1)
    assert w.reach == [(d1, None, None)] and "clock_order_broken" in w.flags
    w = window(frame(1, d1, "in", "10:00"), frame(2, d1, "in", "10:00"), d1, d1)
    assert w.reach == [(d1, 30, 30)] and "width_zero" in w.flags
    w = window(frame(1, d1, "in", ""), frame(2, d1, "in", "10:00"), d1, d1)
    assert w.reach == [(d1, None, 30)] and "clock_unknown" in w.flags
    # a clock past the close clips to the last regular minute (R14); an early-close day to 209
    w = window(frame(1, "2020-11-27", "in", "09:40"), frame(2, "2020-11-27", "in", "15:30"), "2020-11-27", "2020-11-27")
    assert w.reach == [("2020-11-27", 10, 209)]
    assert P.clock_minute("09:30") == 0 and P.clock_minute("15:59") == 389 and P.clock_minute("") is None


# ═════════════════════════════════════════════════════════════════════════════════════════════ loaders, the daily-only fallback, the seal
def write_export(path: Path, tickers: dict, cal: list) -> None:
    """A header-less export (ticker,date,o,h,l,c,v) with SPY (the calendar) and the given tickers' bars."""
    with gzip.open(path, "wt") as fh:
        for d in cal:
            fh.write(f"SPY,{d},300,301,299,300,1000000\n")
        for tk, rows in tickers.items():
            for d, (o, h, l, c, v) in rows.items():
                fh.write(f"{tk},{d},{o},{h},{l},{c},{v}\n")


def write_minute_tree(root: Path, d: str, blocks: dict, statuses: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "_done.psv", "a") as fh:
        for tk, st in statuses.items():
            fh.write(f"{d}|{tk}|{len(blocks.get(tk, []))}|{st}\n")
    with open(root / f"{d}.psv.gz", "ab") as fh:
        for tk, mb in blocks.items():
            text = "".join(f"{tk}|{int(mb.minute[i])}|{mb.o[i]}|{mb.h[i]}|{mb.l[i]}|{mb.c[i]}|{mb.v[i]}\n" for i in range(len(mb)))
            fh.write(gzip.compress(text.encode()))


@pytest.fixture
def world(tmp_path):
    cal = weekday_cal("2020-01-02", "2020-07-31")
    S2 = C.Sessions(cal)
    rows = {}
    rng = np.random.default_rng(7)
    px = 10.0
    for d in cal[:cal.index("2020-06-02") + 1]:
        px = round(px * (1 + rng.normal(0, 0.01)), 2)
        rows[d] = (px, round(px * 1.02, 2), round(px * 0.98, 2), round(px * 1.005, 2), 500000.0)
    rows["2020-06-01"] = (10.00, 10.40, 9.90, 10.10, 390000.0)         # the synthetic day's bar
    export = tmp_path / "daily.csv.gz"
    write_export(export, {"XYZ": rows}, cal)
    daily, info = C.load_daily_subset(str(export), keep={"XYZ"}, cut=C.CUT_B)
    tree = tmp_path / "minutes"
    write_minute_tree(tree, "2020-06-01", {"XYZ": synthetic_day(ANCHORS)}, {"XYZ": "ok", "EMPTYCO": "empty"})
    done = {"A": C.load_done(str(tree / "_done.psv"), cut=C.CUT_B)[0]}
    files = {"A": C.minute_date_files(tree)}
    store = C.MinuteStore(done, files)
    bars = P.Bars({"A": daily, "B": daily}, store, S2)
    return {"S": S2, "bars": bars, "store": store, "daily": daily, "tree": tree}


def test_loaders_and_minute_store(world):
    st = world["store"]
    assert st.state("2020-06-01", "XYZ") == "ok/A" and st.state("2020-06-01", "EMPTYCO") == "empty/A" and st.state("2020-06-01", "NOPE") == "missing"
    mb = st.get("2020-06-01", "XYZ")
    assert len(mb) == 390 and mb.c[389] == 10.10 and st.get("2020-06-01", "NOPE") is None
    assert st.reads["A"] == 1
    b, ix = world["bars"].daily("A", "XYZ")
    assert ix["2020-06-01"] == len(b) - 2 and world["bars"].has_daily("A", "XYZ", "2020-06-01") and not world["bars"].has_daily("A", "ZZZ", "2020-06-01")
    ctx = P.day_context(b, ix, "2020-06-01")
    assert ctx["o"] == 10.00 and ctx["prev_c"] == b.c[-3] and ctx["hi_5"] == float(b.h[-7:-2].max()) and ctx["short_history"] is False
    assert ctx["ma_10"] == pytest.approx(float(b.c[-12:-2].mean()))


def test_side_rows_minute_then_daily_only_fallback(world):
    S2, bars = world["S"], world["bars"]
    d = "2020-06-01"
    w = P.Window(1, "XYZ", "XYZ", "buy", d, d, frame(1, d, "in", "10:00"), frame(2, d, "in", "11:00", symbols=["XYZ"]), False, False)
    w.bracket, w.year, w.in_span, w.bar_sym, w.export = P.type_bracket(w, S2), 2020, True, "XYZ", "A"
    P.reachable(w, S2)
    tally, nr = __import__("collections").Counter(), __import__("collections").Counter()
    panel = {"f2": {"XYZ": (1.0, "ok")}}                                 # +1% on the prior close at the first sighting
    rng, cov, cands = P.side_rows(w, bars, panel, S2, tally, nr)
    assert cov["resolution"] == "minute" and rng["resolution"] == "minute" and rng["reach_minutes"] == 61
    b, ix = bars.daily("A", "XYZ")
    mb = synthetic_day(ANCHORS)
    assert rng["range_lo"] == pytest.approx(float(mb.l[30:91].min()), abs=1e-4) and rng["range_hi"] == pytest.approx(float(mb.h[30:91].max()), abs=1e-4)
    assert rng["range_lo"] == 10.08 and rng["range_lo_minute"] == f"{d}:30"       # the bracket's first minute opens at the prior close 10.08
    assert rng["panel_price"] == pytest.approx(round(float(b.c[ix[d] - 1]) * 1.01, 4))     # the prior session's close, +1%
    assert rng["panel_outside_range"] in (True, False) and rng["range_lo_with_panel"] <= rng["range_lo"]
    assert rng["n_candidates"] == len(cands) > 0 and all(c["source"] == "minute" for c in cands)
    assert all(c["date"] == d and 30 <= c["minute"] <= 90 for c in cands)
    assert set(P.CAND_COLS) >= set(cands[0])
    assert rng["density_all"] != "" and 0 <= rng["density_core"] <= rng["density_all"] <= 1
    # the same side on a day with no minute file: daily-only, the whole day's range, minute blank
    d2 = "2020-05-29"
    w2 = P.Window(2, "XYZ", "XYZ", "sale", d2, d2, frame(3, d2, "in", "10:00", symbols=["XYZ"]), frame(4, d2, "in", "11:00"), False, False)
    w2.bracket, w2.year, w2.in_span, w2.bar_sym, w2.export, w2.hold_min, w2.hold_max = P.type_bracket(w2, S2), 2020, True, "XYZ", "A", 1, 3
    P.reachable(w2, S2)
    rng2, cov2, cands2 = P.side_rows(w2, bars, {}, S2, tally, nr)
    assert cov2["resolution"] == "daily_only" and cov2["daily_only_reason"] == "no_minute_file"
    assert rng2["range_lo"] == float(b.l[ix[d2]]) and rng2["range_hi"] == float(b.h[ix[d2]])
    assert "bracket_clipped_lost_daily_only" in rng2["flags"] and "panel_no_pct" in rng2["flags"]
    assert cands2 and all(c["minute"] == "" and "daily_only" in c["flags"] for c in cands2)
    assert all(c["hold_sessions_min"] == 1 and c["hold_sessions_max"] == 3 for c in cands2)
    # no daily bar at all: resolution none, no candidates
    w3 = P.Window(3, "ZZZ", "ZZZ", "buy", d, d, frame(1, d, "in", "10:00"), frame(2, d, "in", "11:00"), False, False)
    w3.bracket, w3.bar_sym, w3.export = P.type_bracket(w3, S2), "ZZZ", "A"
    P.reachable(w3, S2)
    rng3, cov3, cands3 = P.side_rows(w3, bars, {}, S2, tally, nr)
    assert cov3["resolution"] == "none" and cands3 == [] and "no_daily_bar" in rng3["flags"]


def test_wide_window_is_daily_only_even_with_minutes(world):
    S2, bars = world["S"], world["bars"]
    w = P.Window(1, "XYZ", "XYZ", "buy", "2020-05-19", "2020-06-01", frame(1, "2020-05-19", "in", "10:00"), frame(2, "2020-06-01", "in", "11:00"), False, False)
    w.bracket, w.bar_sym, w.export = P.type_bracket(w, S2), "XYZ", "A"
    P.reachable(w, S2)
    assert w.bracket == "sessions_6plus" and w.wide
    rng, cov, cands = P.side_rows(w, bars, {}, S2, __import__("collections").Counter(), __import__("collections").Counter())
    assert cov["resolution"] == "daily_only" and cov["daily_only_reason"] == "wide_window" and cov["n_sessions"] == 10
    assert all(c["minute"] == "" for c in cands)
    # the middle sessions carry the close only (§3.5): the window has 10 sessions, the first and last 5 are full, so no middle here;
    # a 12-session window has two middle sessions with F6 only
    w = P.Window(1, "XYZ", "XYZ", "buy", "2020-05-15", "2020-06-02", frame(1, "2020-05-15", "in", "10:00"), frame(2, "2020-06-02", "in", "11:00"), False, False)
    w.bracket, w.bar_sym, w.export = P.type_bracket(w, S2), "XYZ", "A"
    P.reachable(w, S2)
    rng, cov, cands = P.side_rows(w, bars, {}, S2, __import__("collections").Counter(), __import__("collections").Counter())
    mids = [c for c in cands if c["date"] in ("2020-05-22", "2020-05-26")]
    assert mids and all(c["families"].startswith("F6") for c in mids)


def test_seal_raises(world, tmp_path):
    st = world["store"]
    with pytest.raises(C.GuardStop):
        st.seal("2025-01-02")
    with pytest.raises(C.GuardStop):
        st.get("2025-01-02", "XYZ")
    with pytest.raises(C.GuardStop):
        C.seal_date("2025-06-30", "(a test)")
    C.seal_date("2024-12-31")
    done_path = tmp_path / "late" / "_done.psv"
    done_path.parent.mkdir()
    done_path.write_text("2024-12-31|A|390|ok\n2025-01-02|A|390|ok\n")
    done, dropped = C.load_done(str(done_path), cut=C.CUT_B)
    assert dropped == 1 and ("2025-01-02", "A") not in done and ("2024-12-31", "A") in done
    export = tmp_path / "late.csv.gz"
    write_export(export, {"XYZ": {"2025-01-02": (1, 1, 1, 1, 1), "2024-12-30": (1, 1, 1, 1, 1)}}, weekday_cal("2024-12-02", "2025-01-10"))
    daily, info = C.load_daily_subset(str(export), keep={"XYZ"}, cut=C.CUT_B)
    assert info["dated_after_cut"] > 0 and daily.cal[-1].isoformat() <= C.CUT_B


def test_forbidden_folder_guard_raises():
    names = {"replay", "his_exits", "intraday", "reverse", "rule_mix", "reverse_fit_events", "reverse_recount_cache"}
    assert {os.path.basename(d) for d in C.FORBIDDEN_DIRS} == names and len(C.FORBIDDEN_DIRS) == 7
    for d in C.FORBIDDEN_DIRS:
        with pytest.raises(C.GuardStop):
            C.checked(os.path.join(d, "anything.tsv"))
        with pytest.raises(C.GuardStop):
            C.checked(d)
    assert C.checked(C.FILES["entries"]) == C.FILES["entries"]
    assert C.checked(os.path.join(C.H_DIR, "replay_missing_minutes.tsv"))     # a sibling FILE, not the folder


def test_alias_extension_recovers_renamed_symbols():
    lex = {"GOTU": ("2019-06-06", "2022-06-30", "2021-09-27", "2026-10-16"), "GSX": ("", "", "2025-09-16", "2026-02-19"),
           "CHPT": ("2019-09-16", "2022-06-30", "2021-09-27", "2026-10-16")}
    tally = __import__("collections").Counter()
    out = C.extend_alias_renames({"FB": "META"}, lex, tally)
    assert out == {"FB": "META", "GSX": "GOTU", "SBE": "CHPT"} and tally["alias_rename_table"] == 2
    # a panel symbol that HAS era-A rows of its own is never re-pointed; a target with no era-A rows recovers nothing
    lex2 = dict(lex, GSX=("2019-06-06", "2022-06-30", "", ""), CHPT=("", "", "2021-09-27", "2026-10-16"))
    tally2 = __import__("collections").Counter()
    out2 = C.extend_alias_renames({}, lex2, tally2)
    assert out2 == {} and tally2["rename_skipped_has_era_a"] == 1 and tally2["rename_skipped_target_absent"] == 1
    assert C.RENAMES == {"GSX": "GOTU", "SBE": "CHPT"}


# ═════════════════════════════════════════════════════════════════════════════════════════════ guards on the code itself
def test_identifier_scan_fails_on_planted_name_and_passes_on_average(tmp_path):
    forb = C.load_forbidden_names()
    assert "average" not in forb and "operator" not in forb and "setup_paths" not in forb and len(forb) >= 30
    clean = tmp_path / "clean.py"
    clean.write_text("average = 1\noperator = 'x'\nsetup_paths = {'the setup is': 2}\nrange_vs_avgrange20 = 3\nmsg = f'{average}'\n")
    assert C.scan_identifiers([str(clean)], forb) == []
    planted = tmp_path / "planted.py"
    planted.write_text("average = 1\nx = row.setup\ny = 'pivot'\nz = thing.decides(1)\n")
    hits = C.scan_identifiers([str(planted)], forb)
    assert [(ln, t) for _p, ln, t in hits] == [(2, "setup"), (3, "'pivot'"), (4, "decides")]
    planted2 = tmp_path / "planted2.py"
    planted2.write_text("def f(E):\n    return E\n")
    assert len(C.scan_identifiers([str(planted2)], forb)) == 2


def test_step5_modules_scan_clean():
    # source-pin-ok: the plan's guard (3) IS a scan of the step-5 source text; the modules must hold none of the excluded names
    assert C.scan_identifiers([str(ASIS / "asis_common.py"), str(ASIS / "01_points.py")]) == []


def _fresh_import_report(module_path: Path, extra_prelude: str = "") -> list:
    code = (
        "import importlib.util, sys, json\n"
        f"{extra_prelude}\n"
        f"spec = importlib.util.spec_from_file_location('asis_points01', {str(module_path)!r})\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['asis_points01'] = m; spec.loader.exec_module(m)\n"
        "print(json.dumps(m.C.rule_modules_loaded()))\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    import json
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_fresh_interpreter_import_holds_no_rule_module(tmp_path):
    assert _fresh_import_report(ASIS / "01_points.py") == []
    # a planted import of a file inside one of the rule folders (a stub; the real module is never executed) must be reported
    stub_dir = tmp_path / "_705_intraday_1025"
    stub_dir.mkdir()
    (stub_dir / "01_intra.py").write_text("PLANTED = True\n")
    prelude = (f"spec2 = importlib.util.spec_from_file_location('intra01_planted', {str(stub_dir / '01_intra.py')!r})\n"
               "m2 = importlib.util.module_from_spec(spec2); sys.modules['intra01_planted'] = m2; spec2.loader.exec_module(m2)")
    assert _fresh_import_report(ASIS / "01_points.py", prelude) == ["intra01_planted"]
    # the checker on a fake module table: the four folders and the four named modules
    fake = {"a": type("M", (), {"__file__": "/x/scripts/probes/_cb_backtest/runner.py"})(),
            "b": type("M", (), {"__file__": "/x/agents/market_intelligence/consolidation_breakout.py"})(),
            "c": type("M", (), {"__file__": "/x/scripts/probes/_705_asis_1026/asis_common.py"})(), "d": type("M", (), {})()}
    assert C.rule_modules_loaded(fake) == ["a", "b"]


def _segment(src: str, name: str, cls: str = None) -> str:
    """The source text of a top-level def / class / assignment (or a method of `cls`), decorators included; text only, nothing imported."""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    body = tree.body
    if cls is not None:
        body = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    for node in body:
        nm = None
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            nm = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            nm = t.id if isinstance(t, ast.Name) else (",".join(e.id for e in t.elts) if isinstance(t, ast.Tuple) else None)
        if nm == name:
            start = node.lineno - 1
            if getattr(node, "decorator_list", None):
                start = node.decorator_list[0].lineno - 1
            return "".join(lines[start:node.end_lineno])
    raise KeyError(name)


def _rename(text: str, mapping: dict) -> str:
    toks = tokenize.generate_tokens(io.StringIO(text).readline)
    return tokenize.untokenize([(t.type, mapping.get(t.string, t.string) if t.type == tokenize.NAME else t.string, t.start, t.end, t.line) for t in toks])


def test_every_copied_helper_matches_its_source():
    # source-pin-ok: the plan (§10) requires every copied rule-free helper to be byte-identical to its source, never imported; this compares text
    copy_src = (ASIS / "asis_common.py").read_text(encoding="utf-8")
    assert len(C.COPIED) >= 40
    seen = set()
    for src_rel, name, kind, ren in C.COPIED:
        src_text = (REPO / src_rel).read_text(encoding="utf-8")
        if kind == "method":
            cls, meth = name.split(".")
            theirs, ours = _segment(src_text, meth, cls), _segment(copy_src, meth, cls)
        else:
            theirs, ours = _segment(src_text, name), _segment(copy_src, name)
        if ren:
            fn = ast.parse(theirs).body[0]
            src_param = fn.args.args[ren["param_index"]].arg
            theirs = _rename(theirs, {src_param: ren["to"]})
        assert theirs == ours, f"{src_rel}:{name} drifted from its copy"
        seen.add(name)
    for must in ("Sessions", "load_alias", "read_minute_file", "load_daily_subset", "fnum", "rng_for", "session_end_minute", "smas_for",
                 "MinuteStore.seal", "MinuteStore.preload", "EARLY_CLOSE", "bar_sym", "covered_tree", "minute_state", "subs_list_sha"):
        assert must in seen


def test_copied_helpers_behave():
    assert C.fnum(np.array([2.5])) == 2.5 and C.fnum(np.float64(1.0)) == 1.0 and C.fnum(3) == 3.0
    with pytest.raises(ValueError):
        C.fnum(np.array([1.0, 2.0]))
    a, b = C.rng_for("x").random(), C.rng_for("x").random()
    assert a == b and C.rng_for("y").random() != a
    assert C.bar_sym("2022-03-31", "A", "B") == "A" and C.bar_sym("2022-04-01", "A", "B") == "B"
    assert C.et_seconds("2020-05-20T10:40-04:00") == 38400 and C.hhmm(38400) == "10:40" and C.et_seconds("") is None
    cal = weekday_cal("2020-06-01", "2020-06-12")
    S3 = C.Sessions(cal)
    assert C.asof(frame(1, "2020-06-02", "pre", "09:00"), S3) == 0 and C.asof(frame(1, "2020-06-02", "in", "10:00"), S3) == 1
    assert C.lo_after(frame(1, "2020-06-02", "closed", "17:00"), S3) == 2 and C.lo_after(frame(1, "2020-06-02", "in", "10:00"), S3) == 1
    assert C.asof(frame(1, "2020-06-06", "in", "10:00"), S3) == 4 and C.lo_after(frame(1, "2020-06-06", "in", "10:00"), S3) == 5   # a Saturday
    cache = C.IdCache()
    o1 = object()
    assert cache.get(o1, lambda _o: "v1") == "v1" and cache.get(o1) == "v1" and cache.get(object()) is None
    bars = C.daily_bars_from_arrays([date(2020, 1, k) for k in range(2, 12)], np.arange(10.0), np.arange(10.0) + 1, np.arange(10.0) - 1, np.arange(10.0), np.ones(10))
    sw = C.smas_sweep(bars)
    assert set(sw) == set(C.SMA_SWEEP) and np.isnan(sw[5][3]) and sw[5][4] == 2.0 and C.smas_for(bars)[10][9] == 4.5
    # (the rule-module check runs in a fresh interpreter in test_fresh_interpreter_import_holds_no_rule_module: this process is shared
    # with every other test file CI collects, several of which load the cb module)
    assert C.raw_factor_for(date(2020, 10, 21), [(date(2021, 7, 20), 4.0), (date(2024, 6, 10), 10.0)]) == 40.0
    assert C.raw_factor_for(date(2021, 7, 20), [(date(2021, 7, 20), 4.0), (date(2024, 6, 10), 10.0)]) == 10.0     # on the execution date: post-split
    fb = C.factor_by_bar([date(2021, 7, 19), date(2021, 7, 20), date(2024, 6, 11)], [(date(2021, 7, 20), 4.0), (date(2024, 6, 10), 10.0)])
    assert list(fb) == [40.0, 10.0, 1.0]


def test_no_absolute_machine_path_in_this_test_file():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "/Users" + "/" not in text


# ═════════════════════════════════════════════════════════════════════════════════════════════ the review's F5: the window / loader layer
def test_assign_export_falls_back_only_when_the_primary_has_no_bar_in_the_window(tmp_path):
    cal = weekday_cal("2020-01-02", "2020-07-31")
    S2 = C.Sessions(cal)
    bar = (10.0, 10.4, 9.9, 10.1, 1000.0)
    a_rows = {d: bar for d in cal if d < "2020-06-01"}                   # export A: XYZ to the end of May only
    b_rows = {d: bar for d in cal}                                       # export B: XYZ everywhere
    ex_a, ex_b = tmp_path / "a.csv.gz", tmp_path / "b.csv.gz"
    write_export(ex_a, {"XYZ": a_rows, "ONLYA": {"2020-06-02": bar}}, cal)
    write_export(ex_b, {"XYZ": b_rows, "ONLYB_MAY": {"2020-05-29": bar}}, cal)
    dA, _ = C.load_daily_subset(str(ex_a), keep={"XYZ", "ONLYA", "ONLYB_MAY"}, cut=C.CUT_B)
    dB, _ = C.load_daily_subset(str(ex_b), keep={"XYZ", "ONLYA", "ONLYB_MAY"}, cut=C.CUT_B)
    bars = P.Bars({"A": dA, "B": dB}, C.MinuteStore({}, {}), S2)
    tally = __import__("collections").Counter()

    def mk(sym, lo, hi):
        w = P.Window(1, sym, sym, "buy", lo, hi, frame(1, lo, "in", "10:00"), frame(2, hi, "in", "11:00"), False, False)
        w.bracket = P.type_bracket(w, S2)
        P.reachable(w, S2)
        P.assign_export(w, bars, tally)
        return w
    w = mk("XYZ", "2020-05-29", "2020-05-29")                            # the primary (A, window end <= 2022-03-31) has the bar: no fallback
    assert (w.export, w.bar_sym, w.export_fallback) == ("A", "XYZ", False)
    w = mk("XYZ", "2020-06-02", "2020-06-02")                            # A carries XYZ but has NO bar in the window; B has: fallback
    assert (w.export, w.bar_sym, w.export_fallback) == ("B", "XYZ", True) and tally["export_fallback"] == 1
    w = mk("ONLYB_MAY", "2020-06-02", "2020-06-02")                      # the other export merely has the ticker (May), no bar in the window: no fallback
    assert (w.export, w.export_fallback) == ("A", False) and tally["export_fallback"] == 1
    w = mk("XYZ", "2020-05-29", "2020-06-02")                            # A has one of the two sessions: the primary stands (no fallback)
    assert (w.export, w.export_fallback) == ("A", False)


def _tsv(path: Path, cols: list, rows: list) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")
    return str(path)


def test_read_windows_last_sighting_includes_blip_filled_and_hold_sessions(tmp_path):
    cal = weekday_cal("2020-06-01", "2020-06-12")
    S2 = C.Sessions(cal)
    d1, d2, d3 = "2020-06-01", "2020-06-02", "2020-06-03"
    snaps = [{"idx": 1, "frame_id": "f1", "vid": "v1", "date": d1, "ctx": "in", "clock": "10:00", "full": "True", "symbols": "", "blip_filled": ""},
             {"idx": 2, "frame_id": "f2", "vid": "v1", "date": d1, "ctx": "in", "clock": "10:30", "full": "True", "symbols": "XYZ", "blip_filled": ""},
             {"idx": 3, "frame_id": "f3", "vid": "v2", "date": d2, "ctx": "in", "clock": "10:00", "full": "True", "symbols": "", "blip_filled": "XYZ"},
             {"idx": 4, "frame_id": "f4", "vid": "v3", "date": d3, "ctx": "in", "clock": "10:00", "full": "True", "symbols": "", "blip_filled": ""}]
    snap_path = _tsv(tmp_path / "snapshots.tsv", P.SNAP_COLS, snaps)
    ent = [{"eid": 1, "sym": "XYZ", "sym_a": "XYZ", "has_bars": "True", "first_frame": "f2", "first_vid": "v1", "first_date": d1, "first_ctx": "in",
            "prev_full_frame": "f1", "prev_full_date": d1, "lo": d1, "hi": d1, "window_len": 1, "inverted": "False", "initial": "False",
            "flicker": "True", "n_sightings": 2, "n_streams": 2, "exit_lo": d2, "exit_hi": d3, "exit_frame": "f4", "still_held": "False",
            "first_resolution": "1920x1080"}]
    exi = [{"eid": 1, "sym": "XYZ", "sym_a": "XYZ", "exit_lo": d2, "exit_hi": d3, "exit_frame": "f4", "flicker": "True", "initial": "False"}]
    frames = P.read_frames(snap_path)
    tally = __import__("collections").Counter()
    buys, sales, ent_df = P.read_windows(frames, S2, tally, _tsv(tmp_path / "entries.tsv", P.ENTRY_COLS, ent), _tsv(tmp_path / "exits.tsv", P.EXIT_COLS, exi))
    assert len(buys) == len(sales) == 1 and len(ent_df) == 1
    # the last sighting is the BLIP-FILLED frame f3 (ignoring blip_filled would start the sale window on d1 at f2)
    assert sales[0].earlier.frame_id == "f3" and (sales[0].lo, sales[0].hi) == (d2, d3) and not sales[0].inverted
    assert tally["exit_windows_reproduced"] == 1 and tally["flicker"] == 1 and tally["sale_inverted"] == 0
    assert (buys[0].lo, buys[0].hi, buys[0].earlier.frame_id, buys[0].later.frame_id) == (d1, d1, "f1", "f2")
    # §3.4 hold_sessions_min / max from the two windows: at least d2 - d1 = 1 session, at most d3 - d1 = 2
    assert P.hold_sessions(buys[0], sales[0], S2) == (1, 2)
    wide_sale = P.Window(1, "XYZ", "XYZ", "sale", d1, d3, None, None, False, False)
    assert P.hold_sessions(buys[0], wide_sale, S2) == (0, 2)              # a same-session round trip floors at 0


def test_no_swing_on_equal_neighbours_and_no_vwap_cross_on_equality():
    # a plateau: the 5-minute buckets 20-24 and 25-29 both top at 10.50 -> neither is STRICTLY above its three neighbours: no swing high
    mb = synthetic_day([(0, 10.00), (20, 10.50), (29, 10.50), (60, 10.00), (389, 10.00)])
    pts, nr, _ = P.minute_points("2020-06-01", mb, None, None, day_ctx(h=10.50, l=10.00, c=10.00), 390, (10.00, 10.50))
    assert not pts_by(pts, "F5", "swing_high")
    # a flat day: the previous close always EQUALS the previous average -> no F11 cross in either direction (strict inequality)
    flat = synthetic_day([(0, 10.00), (389, 10.00)])
    pts, nr, _ = P.minute_points("2020-06-01", flat, None, None, day_ctx(h=10.00, l=10.00, c=10.00, o=10.00), 390, (10.00, 10.00))
    assert not pts_by(pts, "F11") and nr["F11:up"] == 1 and nr["F11:down"] == 1
    # the cross is strict on the previous bar's close: a bar whose previous close sits ON the level is not a cross
    m, o, h, l, c = np.arange(3), np.array([10.0, 10.0, 10.0]), np.array([10.0, 10.0, 10.5]), np.array([10.0, 10.0, 10.0]), np.array([10.0, 10.0, 10.5])
    assert P.first_cross(10.0, m, o, h, l, c, 0, 2, "up") is None and P.first_cross(10.2, m, o, h, l, c, 0, 2, "up") == 2


# ═════════════════════════════════════════════════════════════════════════════════════════════ the raw factor (R12 / R31) and merged rows (R20)
@pytest.fixture
def raw_world(tmp_path):
    """Adjusted bars constant; XYZ split 10:1 on 06-01 and 2:1 on 07-01 (so the true raw factor is 20 before 06-01, 2 in June, 1 from July);
    the raw file ends 06-15 (July is CARRIED through the split list); NORAW has splits but no raw rows (PARTIAL); NONE has neither (MISSING)."""
    cal = weekday_cal("2020-01-02", "2020-07-31")
    S2 = C.Sessions(cal)
    bar = (10.0, 10.4, 9.9, 10.1, 1000.0)
    rows = {d: bar for d in cal}
    export = tmp_path / "daily.csv.gz"
    write_export(export, {"XYZ": rows, "NORAW": rows, "NONE": rows}, cal)
    daily, _ = C.load_daily_subset(str(export), keep={"XYZ", "NORAW", "NONE"}, cut=C.CUT_B)
    with gzip.open(tmp_path / "raw.csv.gz", "wt") as fh:
        for d in cal:
            if d <= "2020-06-15":
                fh.write(f"XYZ,{d},{10.1 * (20 if d < '2020-06-01' else 2)}\n")
        fh.write("XYZ,2025-01-03,1.0\n")                                  # after the seal: dropped at read
    (tmp_path / "splits.psv").write_text("XYZ|2020-06-01|1|10\nXYZ|2020-07-01|1|2\nNORAW|2020-06-01|1|10\nXYZ|2025-03-02|1|5\nXYZ|2020-06-01|1|10\n")
    rawmap, info = C.load_raw_close_subset(str(tmp_path / "raw.csv.gz"), keep={"XYZ", "NORAW", "NONE"}, cut=C.CUT_B)
    splits, n_dropped = C.load_splits_sealed(str(tmp_path / "splits.psv"))
    bars = P.Bars({"A": daily, "B": daily}, C.MinuteStore({}, {}), S2)
    return {"S": S2, "bars": bars, "rawmap": rawmap, "splits": splits, "info": info, "n_dropped": n_dropped}


def test_raw_factor_sources_and_seal(raw_world):
    S2, bars, rawmap, splits = raw_world["S"], raw_world["bars"], raw_world["rawmap"], raw_world["splits"]
    assert raw_world["info"]["dated_after_cut"] == 1 and raw_world["n_dropped"] == 1 and set(rawmap) == {"XYZ"}
    assert splits["XYZ"] == [(date(2020, 6, 1), 10.0), (date(2020, 7, 1), 2.0)] and splits["NORAW"] == [(date(2020, 6, 1), 10.0)]   # deduplicated, sealed
    tally = __import__("collections").Counter()

    def mk(sym, lo, hi):
        w = P.Window(1, sym, sym, "buy", lo, hi, frame(1, lo, "in", "10:00"), frame(2, hi, "in", "11:00"), False, False)
        w.bracket, w.bar_sym, w.export = P.type_bracket(w, S2), sym, "A"
        P.reachable(w, S2)
        P.raw_factors(w, bars, rawmap, splits, tally)
        return w
    w = mk("XYZ", "2020-05-29", "2020-06-02")                            # exact on every session; the split falls inside the window
    assert w.raw == {"2020-05-29": (20.0, "exact"), "2020-06-01": (2.0, "exact"), "2020-06-02": (2.0, "exact")} and "split_inside_window" in w.flags
    w = mk("XYZ", "2020-06-16", "2020-06-16")                            # after the raw file's last row, before the July split: carried, still 2
    assert w.raw == {"2020-06-16": (2.0, "carried")} and "split_inside_window" not in w.flags
    w = mk("XYZ", "2020-07-02", "2020-07-02")                            # carried THROUGH the 2:1 of 07-01: 2 / 2 = 1
    assert w.raw["2020-07-02"] == (pytest.approx(1.0), "carried")
    w = mk("NORAW", "2020-05-29", "2020-06-02")                          # no raw row: the listed splits after the session only
    assert w.raw == {"2020-05-29": (10.0, "partial"), "2020-06-01": (1.0, "partial"), "2020-06-02": (1.0, "partial")}
    w = mk("NONE", "2020-05-29", "2020-05-29")
    assert w.raw == {"2020-05-29": (1.0, "missing")}
    assert tally[("raw_source", "buy", "exact")] == 3 and tally[("raw_source", "buy", "carried")] == 2 and tally[("raw_source", "buy", "partial")] == 3
    assert tally[("raw_source", "buy", "missing")] == 1


def test_side_rows_carry_raw_price_and_f10_in_raw(raw_world):
    S2, bars, rawmap, splits = raw_world["S"], raw_world["bars"], raw_world["rawmap"], raw_world["splits"]
    tally, nr = __import__("collections").Counter(), __import__("collections").Counter()
    w = P.Window(1, "XYZ", "XYZ", "sale", "2020-05-29", "2020-06-02", frame(1, "2020-05-29", "in", "10:00"), frame(2, "2020-06-02", "in", "11:00"), False, False)
    w.bracket, w.bar_sym, w.export, w.year, w.in_span = P.type_bracket(w, S2), "XYZ", "A", 2020, True
    P.reachable(w, S2)
    P.raw_factors(w, bars, rawmap, splits, tally)
    rng, cov, cands = P.side_rows(w, bars, {}, S2, tally, nr)
    assert cov["resolution"] == "daily_only" and (rng["range_lo"], rng["range_hi"]) == (9.9, 10.4)
    # the raw range is the min / max over the SESSIONS' raw ranges (20x before the split, 2x after), never one factor x the bar range
    assert (rng["range_lo_raw"], rng["range_hi_raw"]) == (pytest.approx(19.8), pytest.approx(208.0))
    assert (rng["raw_factor"], rng["raw_source"]) == (20.0, "exact") and "split_inside_window" in rng["flags"]
    by_day = {}
    for c in cands:
        by_day.setdefault(c["date"], []).append(c)
    f10_may = [c for c in by_day["2020-05-29"] if "F10" in c["families"]]
    assert f10_may and all(c["price_raw"] == pytest.approx(c["price"] * 20) and float(c["price_raw"]).is_integer() or c["price_raw"] % 0.5 == 0 for c in f10_may)
    assert {c["price_raw"] for c in f10_may} == {198.0 + 0.5 * k for k in range(21)}       # every $0.50 inside 198..208 (= 9.9..10.4 x 20)
    assert all(c["dist_round"] == 0 for c in f10_may)
    f10_june = [c for c in by_day["2020-06-01"] if "F10" in c["families"]]
    assert {c["price_raw"] for c in f10_june} == {20.0, 20.5} and {c["price"] for c in f10_june} == {10.0, 10.25}
    f1 = [c for c in by_day["2020-05-29"] if c["family"].startswith("F1")]     # the open 10.0 x 20 = $200 is itself a round number: merged with F10
    assert f1 and f1[0]["family"] == "F1+F10" and f1[0]["price_raw"] == 200.0 and f1[0]["raw_factor"] == 20.0 and f1[0]["dist_round"] == 0
    assert all("split_inside_window" in c["flags"] for c in cands)
    assert set(P.CAND_COLS) >= set(cands[0]) and set(P.RANGE_COLS) >= set(k for k in rng if not k.startswith("density_"))


def test_merged_row_price_is_the_mean_and_tags_carry_our_length(world):
    S2, bars = world["S"], world["bars"]
    d = "2020-06-01"
    w = P.Window(1, "XYZ", "XYZ", "buy", d, d, frame(1, d, "in", "09:30"), frame(2, d, "in", "11:00", symbols=["XYZ"]), False, False)
    w.bracket, w.year, w.in_span, w.bar_sym, w.export = P.type_bracket(w, S2), 2020, True, "XYZ", "A"
    P.reachable(w, S2)
    rng, cov, cands = P.side_rows(w, bars, {}, S2, __import__("collections").Counter(), __import__("collections").Counter())
    at8 = [c for c in cands if c["minute"] == 8]
    assert len(at8) == 1 and at8[0]["n_families"] >= 2
    row = at8[0]
    levels = [float(x.split(":")[1]) for x in row["levels"].split("|")]
    assert row["price"] == pytest.approx(sum(levels) / len(levels), abs=1e-4) and "+" in row["family"] and row["family"].startswith("F2")
    tags = row["families"].split("+")
    assert any(t.startswith("F2(5)") and t.endswith("*") for t in tags) and any(t.startswith("F10") and not t.endswith("*") for t in tags)
    assert row["our_length"] is True and row["k"] == "" and row["direction"] == "down"
    assert not any("F9" in c["families"] for c in cands) and all(c["bar_holes"] == 0 and c["short_history"] is False for c in cands)
    single = [c for c in cands if c["n_families"] == 1]
    assert single and all("+" not in c["family"] and c["price"] == float(c["levels"].split(":")[1]) for c in single)


# ═════════════════════════════════════════════════════════════════════════════════════════════ the run gates (R34)
def test_run_gate_refuses_until_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "P_DRY", str(tmp_path / "dry.txt"))
    monkeypatch.setattr(C, "P_RUN", str(tmp_path / "run.txt"))
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    monkeypatch.setattr(C, "OUTPUTS", {k: str(tmp_path / f"{k}.tsv") for k in ("candidates", "ranges", "coverage")})
    doc = tmp_path / "doc.md"
    doc.write_text("# body\n\n<!-- FREEZE -->\n")
    # R46 (review F6): the windows-v2 gate is threaded through (its own reading is tested in test_asis_windows_v2; here it never reads real data)
    monkeypatch.setattr(C, "windows_v2_gate", lambda: ["the windows-v2 dry run has not completed (synthetic)"])
    assert any("windows-v2 dry run" in x for x in P.run_gate(str(doc)))
    monkeypatch.setattr(C, "windows_v2_gate", lambda: [])
    problems = P.run_gate(str(doc))
    assert any("not completed" in x for x in problems) and any("pins not below" in x for x in problems)
    (tmp_path / "dry.txt").write_text("stuff\nRESULT: 3 claims, 2 OK, 1 MISMATCH\nDRY RUN COMPLETE\n")
    assert P.dry_run_mismatches(str(tmp_path / "dry.txt")) == 1
    assert any("1 MISMATCH" in x for x in P.run_gate(str(doc)))
    (tmp_path / "dry.txt").write_text("stuff\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert P.dry_run_mismatches(str(tmp_path / "dry.txt")) == 0
    assert any("other code than the modules" in x for x in P.run_gate(str(doc)))          # no module line: the dry run predates the code
    (tmp_path / "dry.txt").write_text(f"stuff\n- modules: {P.module_shas_line()}x\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert any("other code than the modules" in x for x in P.run_gate(str(doc)))          # a different sha
    (tmp_path / "dry.txt").write_text(f"stuff\n- modules: {P.module_shas_line()}\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert P.dry_run_modules_line(str(tmp_path / "dry.txt")) == P.module_shas_line()
    # paste every pin (inputs, modules, doc body, the dry-run printout) below the marker: the gate opens
    pins = C.pins(str(doc), include_outputs=False)
    pins["dryrun_printout"] = C.sha(str(tmp_path / "dry.txt"))
    with open(doc, "a") as fh:
        fh.write("\n".join(f"- {k}: `{v}`" for k, v in pins.items()) + "\n")
    assert P.run_gate(str(doc)) == []
    # an output already present, or an edit ABOVE the marker, refuses again
    (tmp_path / "ranges.tsv").write_text("x\n")
    assert any("outputs exist" in x for x in P.run_gate(str(doc)))
    (tmp_path / "ranges.tsv").unlink()
    doc.write_text(doc.read_text().replace("# body", "# body edited"))
    assert any("doc_body" in x for x in P.run_gate(str(doc)))
    assert P.dry_run_mismatches(str(tmp_path / "absent.txt")) is None


# ═════════════════════════════════════════════════════════════════════════════════════════════ re-run 1: the pull's tree, the archive (R37-R39)
def test_pull_tree_is_last_and_pre_pull_trees_are_the_original_six():
    assert C.PRE_PULL_TREES == ("A", "B", "EP", "EP2", "REV", "INTRA")
    assert C.TREE_ORDER == C.PRE_PULL_TREES + ("ASIS",)                        # last: no pair already covered changes tree
    assert "done_ASIS" in C.FILES and "ASIS" in C.MINUTES
    assert C.FILES["done_ASIS"] == C.MINUTES["ASIS"] + "/_done.psv"
    for tr in C.TREE_ORDER:                                                    # one fetch log and one folder per tree, nothing orphaned
        assert C.FILES[f"done_{tr}"].endswith("/_done.psv") and tr in C.MINUTES
    assert {k for k in C.FILES if k.startswith("done_")} == {f"done_{t}" for t in C.TREE_ORDER}


def test_coverage_claims_read_pre_pull_trees_and_the_pull_is_measured_beside(world, tmp_path):
    S2, bars = world["S"], world["bars"]
    d_pre, d_new, d_both = "2020-06-01", "2020-06-02", "2020-06-03"             # pre-pull tree A holds d_pre and d_both; the pull's tree d_new, d_both
    pull = tmp_path / "pull"
    write_minute_tree(pull, d_new, {"XYZ": synthetic_day(ANCHORS)}, {"XYZ": "ok"})
    write_minute_tree(pull, d_both, {"XYZ": synthetic_day(ANCHORS, n=200)}, {"XYZ": "ok"})
    write_minute_tree(world["tree"], d_both, {"XYZ": synthetic_day(ANCHORS)}, {"XYZ": "ok"})
    st = bars.store
    st.done["A"], _ = C.load_done(str(world["tree"] / "_done.psv"), cut=C.CUT_B)
    st.files["A"] = C.minute_date_files(world["tree"])
    st.done["ASIS"], _ = C.load_done(str(pull / "_done.psv"), cut=C.CUT_B)
    st.files["ASIS"] = C.minute_date_files(pull)
    assert st.state(d_both, "XYZ") == "ok/A"                                   # a pair already covered keeps its tree (ASIS is last)
    assert st.get(d_both, "XYZ") is not None and len(st.get(d_both, "XYZ")) == 390
    assert st.state(d_new, "XYZ") == "ok/ASIS"

    def win(lo, hi):
        w = P.Window(1, "XYZ", "XYZ", "buy", lo, hi, None, None, False, False)
        w.sym_a_orig = "XYZ"
        return w
    for lo, hi, pre, post in ((d_pre, d_pre, True, True),                        # covered before: stays covered
                              (d_new, d_new, False, True),                       # only the pull covers it: the claims do not see it, the after does
                              (d_pre, d_new, False, True),                       # a window needs EVERY session: one pull session completes it
                              (d_both, d_both, True, True),                      # held by both trees: counted in the pre-pull claims (tree A)
                              (d_pre, d_both, False, True)):                     # spans d_new, which only the pull holds
        w = win(lo, hi)
        assert P.inventory_coverage(w, bars, S2)[2] is pre                                          # the default is the PRE-pull trees
        assert P.inventory_coverage(w, bars, S2, trees=C.PRE_PULL_TREES)[2] is pre
        assert P.inventory_coverage(w, bars, S2, trees=C.TREE_ORDER)[2] is post
    assert P.inventory_coverage(win("2020-06-04", "2020-06-04"), bars, S2, trees=C.TREE_ORDER)[2] is False     # nobody holds it: still uncovered
    # an empty log in the pull counts as no minute bars (the 355 empties of the real pull)
    write_minute_tree(pull, "2020-06-04", {}, {"XYZ": "empty"})
    st.done["ASIS"], _ = C.load_done(str(pull / "_done.psv"), cut=C.CUT_B)
    st.files["ASIS"] = C.minute_date_files(pull)
    assert P.inventory_coverage(win("2020-06-04", "2020-06-04"), bars, S2, trees=C.TREE_ORDER)[2] is False


def test_ledger_verify_accepts_the_run1_archive_and_nothing_else(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    assert C.ledger_verify() == ["ledger missing"]
    assert C.archive_path("/x/01_points.txt") == "/x/01_points_run1.txt" and C.archive_path("/x/candidates.tsv") == "/x/candidates_run1.tsv"
    a, b = tmp_path / "01_points.txt", tmp_path / "candidates.tsv"
    a.write_text("run 1 printout\n")
    b.write_text("run 1 table\n")
    C.ledger_append("step5_points", str(a))
    C.ledger_append("step5_candidates", str(b))
    assert C.ledger_verify() == []
    # a deleted file with no archive is a problem; so is an edit
    b2 = b.read_text()
    b.unlink()
    assert C.ledger_verify() == [f"{b}: missing"]
    # the rename alone is not enough: the archive must be a ledger fact
    (tmp_path / "candidates_run1.tsv").write_text(b2)
    assert C.ledger_verify() == [f"{b}: missing"]
    C.ledger_append(C.ARCHIVE_STAGE + "candidates", str(tmp_path / "candidates_run1.tsv"))
    assert C.ledger_verify() == []
    # run 2 writes a fresh file at the original path and appends its own row: both rows verify
    b.write_text("run 2 table\n")
    C.ledger_append("step5_rerun1_candidates", str(b))
    assert C.ledger_verify() == []
    # a regenerated printout (the dry run is rewritten) needs its archived copy too
    a_old = a.read_text()
    a.write_text("a regenerated printout\n")
    assert C.ledger_verify() == [f"{a}: changed since the ledger recorded it"]
    (tmp_path / "01_points_run1.txt").write_text(a_old)
    C.ledger_append(C.ARCHIVE_STAGE + "points", str(tmp_path / "01_points_run1.txt"))
    assert C.ledger_verify() == []
    # the archive is itself checked: edit it and the run-1 rows fail with it
    (tmp_path / "candidates_run1.tsv").write_text("tampered\n")
    bad = C.ledger_verify()
    assert f"{tmp_path}/candidates_run1.tsv: changed since the ledger recorded it" in bad and f"{b}: changed since the ledger recorded it" in bad


def test_run_gate_passes_the_outputs_check_once_run1_is_archived(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "P_DRY", str(tmp_path / "dry.txt"))
    monkeypatch.setattr(C, "P_RUN", str(tmp_path / "run.txt"))
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    monkeypatch.setattr(C, "OUTPUTS", {k: str(tmp_path / f"{k}.tsv") for k in ("candidates", "ranges", "coverage")})
    doc = tmp_path / "doc.md"
    doc.write_text("# body\n\n<!-- FREEZE -->\n")
    for k, p in C.OUTPUTS.items():
        open(p, "w").write(f"{k} run 1\n")
    open(C.P_RUN, "w").write("run 1\n")
    assert any("outputs exist" in x for x in P.run_gate(str(doc)))
    for k, p in list(C.OUTPUTS.items()) + [("points", C.P_RUN)]:
        C.ledger_append("step5_" + k, p)
        os.replace(p, C.archive_path(p))
        C.ledger_append(C.ARCHIVE_STAGE + k, C.archive_path(p))
    problems = P.run_gate(str(doc))
    assert not any("outputs exist" in x or "ledger" in x for x in problems)


# ═════════════════════════════════════════════════════════════════════════════════════════════ re-run 1 review fixes (F4, F12)
def test_pull_row_counts_gains_only_where_the_pull_adds_minutes(world, tmp_path):
    """Review F4: the before / after table's row is a module function; a mutation pointing 'after' at the pre-pull trees must fail here."""
    S2, bars = world["S"], world["bars"]
    d_pre, d_new = "2020-06-01", "2020-06-02"                                   # tree A holds d_pre; only the pull holds d_new
    pull = tmp_path / "pull"
    write_minute_tree(pull, d_new, {"XYZ": synthetic_day(ANCHORS)}, {"XYZ": "ok"})
    st = bars.store
    st.done["ASIS"], _ = C.load_done(str(pull / "_done.psv"), cut=C.CUT_B)
    st.files["ASIS"] = C.minute_date_files(pull)

    def win(lo, hi):
        w = P.Window(1, "XYZ", "XYZ", "buy", lo, hi, None, None, False, False)
        w.sym_a_orig = "XYZ"
        return w
    ws = [win(d_pre, d_pre), win(d_new, d_new), win("2020-06-04", "2020-06-04")]
    row = P.pull_row("BUY", "span", ws, bars, S2)
    # [side, group, n, minute % before, after, gained, width-1 n, width-1 before, after, width-1 gained]
    assert row[:3] == ["BUY", "span", 3] and row[5] == 1 and row[6] == 3 and row[9] == 1       # exactly ONE window gained, the pull-only one
    assert row[3] == P.pct(1, 3) and row[4] == P.pct(2, 3)                                    # 1/3 covered before, 2/3 after
    # a window covered before the pull stays covered: nothing gained when the pull adds nothing
    row0 = P.pull_row("SALE", "2020", [win(d_pre, d_pre)], bars, S2)
    assert row0[5] == 0 and row0[3] == row0[4] == P.pct(1, 1)


def test_fetch_list_reads_the_pre_pull_state_so_it_stays_reproducible(world, tmp_path):
    """Review F12: a pair the pull has since fetched STAYS in the list (reading the post-pull state would silently rewrite it to empty)."""
    fetch = _load("asis_fetch00", ASIS / "00_fetch_list.py")
    st = world["store"]
    d_pre, d_pulled, d_nobody = "2020-06-01", "2020-06-02", "2020-06-04"
    pull = tmp_path / "pull"
    write_minute_tree(pull, d_pulled, {"XYZ": synthetic_day(ANCHORS)}, {"XYZ": "ok"})
    st.done["ASIS"], _ = C.load_done(str(pull / "_done.psv"), cut=C.CUT_B)
    st.files["ASIS"] = C.minute_date_files(pull)
    pairs = {(d_pre, "XYZ"), (d_pulled, "XYZ"), (d_nobody, "XYZ")}
    state, missing = fetch.missing_pairs(pairs, st)
    assert sorted(missing) == [("XYZ", d_pulled), ("XYZ", d_nobody)] and state["ok/A"] == 1 and state["missing"] == 2    # the pulled pair is still listed
    _, after = fetch.missing_pairs(pairs, st, trees=C.TREE_ORDER)                # the post-pull state would have dropped it: that is the mutation
    assert after == [("XYZ", d_nobody)]


def test_ledger_archive_rows_are_the_only_excuse_and_the_rerun_has_its_own_stage_names(tmp_path, monkeypatch):
    """Review F12: a NON-archive row that happens to record a *_run1 path does not excuse a missing file; the re-run's stage prefix is not run 1's."""
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    b = tmp_path / "candidates.tsv"
    b.write_text("run 1 table\n")
    C.ledger_append("step5_candidates", str(b))
    arc = tmp_path / "candidates_run1.tsv"
    arc.write_text("run 1 table\n")
    C.ledger_append("step5_something_else", str(arc))                          # same sha, same _run1 path, but NOT an archive_run1_ row
    b.unlink()
    assert any("missing" in x for x in C.ledger_verify())
    assert P.RERUN_STAGE.startswith("step5_rerun") and not "step5_candidates".startswith(P.RERUN_STAGE) and P.RERUN_STAGE != "step5_"
