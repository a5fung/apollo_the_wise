"""Tests for scripts/probes/_705_rule_mix_1025/01_mix.py (#705 rule mix; docs/analysis/cb_rule_mix_prereg_2026-10-25.md).

Synthetic fixtures only — every bar, minute, frame and TSV row here is made up; no real outcome is read. Per-rule mechanics on hand-built
paths (the four buckets, the booked session, the buy-day frame rule, the missing-session rule), both window controls and the random-level
control, the ENTER k-price / shared-window controls and the replayed draw stream, every guard (the freeze lock, guard 1 against the intraday
dry run, the module scan for a bare reused-helper call / float( / id( / a frozen writer), and ONE end-to-end world (--dry-run -> --print-pins
-> --tag, then a planted TSV row that must STOP gate (viii) and the reset path) with real shapes: two eras incl. an era-B record on its own
calendar, an early-close day with after-hours prints, a missing minute day inside a hold and on a buy day, a still-held trade, windows over
20 sessions, a buy-day sell (control (a) no_room), a loser and a winner on one name, an undated trade with no buy-day frame, the fit chain's
`level:L8` rows, guard-5 trades that return, flickers, 60+ tickers with a fresh market per stage (the store's reads counted: 0 in the dry run, > 0 in the tag).
Run: python3 -m pytest tests/test_rule_mix.py -q -p no:cacheprovider
"""
from __future__ import annotations

import ast
import dataclasses
import gc
import math
import shutil
import importlib.util
import os
import re
import sys
from datetime import date, timedelta

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_PATH = os.path.join(REPO, "scripts", "probes", "_705_rule_mix_1025", "01_mix.py")
_spec = importlib.util.spec_from_file_location("mix01_under_test", MOD_PATH)
mix = importlib.util.module_from_spec(_spec)
sys.modules["mix01_under_test"] = mix
_spec.loader.exec_module(mix)
fz, rev, cb, rp, R, H = mix.fz, mix.rev, mix.cb, mix.rp, mix.R, mix.H
_REAL_CLAIMS = mix.MixClaims                       # the real claims class (the end-to-end env swaps in a quiet one)
EX, ME, UN, NE = mix.EX, mix.ME, mix.UN, mix.NE


def _lock_inputs_on_disk() -> bool:
    """The freeze lock (`tag_lock` -> `mix_pins`) hashes every input of the two frozen reads it carries (their FILES tables,
    all under the local apollo_data folder). CI's shallow clone has none of that data, so the tests that reach the lock
    can only run on a machine that holds it (they run in the pre-push worktree on the build machine)."""
    return all(os.path.exists(p) for table in (rev.FILES, fz.FILES) for p in table.values())


needs_lock_inputs = pytest.mark.skipif(
    not _lock_inputs_on_disk(), reason="the freeze lock hashes the frozen reads' real inputs; this machine does not hold them")


# ═════════════════════════════════════════════════════════════════════════════════════════════ fixtures
def sessions(n: int, start: str = "2020-01-02") -> list:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def weekday_cal(start: str, end: str) -> list:
    d, out = date.fromisoformat(start), []
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def mbars(minutes, closes):
    """Minute bars from a close path: each minute opens at the previous close; high / low = the larger / smaller of the two."""
    c = np.asarray(closes, dtype=float)
    o = np.concatenate([[c[0]], c[:-1]])
    return cb.minute_bars_from_lists(list(minutes), list(o), list(np.maximum(o, c)), list(np.minimum(o, c)), list(c), [1000.0] * len(c))


def path_minutes(points, n: int = 390):
    """A session's minutes through (minute, price) points, linear in between (the first point at minute 0)."""
    m = np.arange(n)
    xs, ys = zip(*points)
    return mbars(m, np.interp(m, xs, ys))


def quiet(p: float, n: int = 390):
    """The default session: o -> h (+0.2%) -> l (-0.2%) -> c (= o): no touch of the prior low, no 60-minute close under the EMA on a
    rising series, no red close."""
    return path_minutes([(0, p), (130, p * 1.002), (260, p * 0.998), (n - 1, p)], n)


def daily_walk(n: int, base: float, seed: int, trend: float = 0.0006):
    rng = np.random.default_rng(seed)
    r = rng.normal(trend, 0.015, n)
    c = base * np.cumprod(1 + r)
    o = c * (1 + rng.normal(0, 0.004, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n)) + 0.0005)
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, n)) - 0.0005)
    return o, h, l, c, np.full(n, 2_000_000.0)


def minutes_from_daily(o, h, l, c, early: bool = False, after_hours: bool = False):
    n = 210 if early else 390
    m = np.arange(n)
    closes = np.interp(m, [0, n // 3, 2 * n // 3, n - 1], [o, h, l, c])
    opens = np.concatenate([[o], closes[:-1]])
    mm, o_, h_, l_, c_ = list(m), list(opens), list(np.maximum(opens, closes)), list(np.minimum(opens, closes)), list(closes)
    if early and after_hours:
        for k in range(210, 215):
            mm.append(k); o_.append(c); h_.append(c); l_.append(c); c_.append(c)
    return cb.minute_bars_from_lists(mm, o_, h_, l_, c_, [1000.0] * len(mm))


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
    b.era = "A" if b.E <= fz.A_LAST else "B"
    b.ticker = b.sym_a if b.era == "A" else b.sym
    b.first_clock = clocks.get("first_clock", "")
    b.flat_clock = clocks.get("flat_clock", "")
    b.p_ctx = clocks.get("p_ctx", "in" if b.flat_clock else "")
    b.f_ctx = clocks.get("f_ctx", "in" if b.first_clock else "")
    b.in_bracket = bool(b.first_clock) and bool(b.flat_clock) and b.p_ctx == "in"
    b.pre_flat_bracket = bool(b.first_clock) and bool(b.flat_clock) and b.p_ctx == "pre"
    b.held_before_0935 = bool(b.first_clock) and b.first_clock < "09:35"
    return b


class FakeStore(fz.MinuteStore):
    """Hand minutes by date (None = no minutes that session)."""

    def __init__(self, by_date: dict):
        super().__init__({}, {})
        self.by_date = by_date

    def state(self, d, tk, b=None):
        return "ok/FAKE" if self.by_date.get(d) is not None else "empty/FAKE"

    def preload(self, pairs):
        from collections import Counter
        return Counter()

    def get(self, d, tk, b=None):
        self.seal(d)
        return self.by_date.get(d)


def sightings_from(frames: list):
    """frames: (date, sym, ctx, clock) -> a Sightings."""
    rows = [dict(idx=i, frame_id=f"f{i}", vid="v", date=d, ctx=ctx, clock=clk, symbols=s, blip_filled="") for i, (d, s, ctx, clk) in enumerate(frames)]
    return rev.Sightings.build(pd.DataFrame(rows, columns=["idx", "frame_id", "vid", "date", "ctx", "clock", "symbols", "blip_filled"]))


def unit_rec(n: int = 90, e: int = 70, exit_lo: int = 3, exit_hi: int = 5, sess=None, empty=(), flat="10:05", first="10:40", f_ctx="in", fill_minute=0,
             fill=None, stop=None, adr20=0.04, eid=1, sym="AAA", frames=(), setup="undated", rise: float = 0.005):
    """One record on its own calendar: `n` sessions, every one a quiet minute path on a series rising `rise` per session unless `sess[offset]`
    (offset from the buy day) gives (callable p -> MinuteBars); `empty` offsets have no minutes; the daily bars are the minutes' own OHLC.
    The registered fill: the buy day's open (minute 0) unless given; the stop one ADR20 under it unless given."""
    cal = sessions(n, "2020-01-02")
    sess = sess or {}
    by_date, o, h, l, c = {}, [], [], [], []
    p = 50.0
    for i in range(n):
        p = p * (1 + rise)
        off = i - e
        mb = sess[off](p) if off in sess else quiet(p)
        o.append(float(mb.o[0])); h.append(float(mb.h.max())); l.append(float(mb.l.min())); c.append(float(mb.c[-1]))
        if off in sess:
            p = float(mb.c[-1])
        by_date[cal[i].isoformat()] = None if off in empty else mb
    bars = cb.daily_bars_from_arrays(cal, np.array(o), np.array(h), np.array(l), np.array(c), np.full(n, 1e6))
    E = cal[e].isoformat()
    b = mk_buy(eid=eid, sym=sym, sym_a=sym, E=E, lo=E, hi=E, setup=setup, exit_lo=cal[e + exit_lo].isoformat() if exit_lo is not None else "",
               exit_hi=cal[e + exit_hi].isoformat() if exit_hi is not None else "", flat_clock=flat or "", first_clock=first or "", f_ctx=f_ctx if first else "",
               p_ctx="in" if flat else "")
    rev.index_calendar([b], [d.isoformat() for d in cal])
    store = FakeStore(by_date)
    r = fz.IRec(b=b, bars=bars, cidx=np.arange(n, dtype=np.int32), e=e, adr20=adr20, cal=cal, era="A", mb=store.get(E, sym), minutes_state="ok")
    r.qqq_c = np.asarray(bars.c, dtype=float) * 3.0
    if b.has_exit:
        r.exit_lo_j, r.exit_hi_j = r.off(b.exit_lo), r.off(b.exit_hi)
    r.fill = float(fill) if fill is not None else float(bars.o[e])
    r.fill_minute = fill_minute
    r.fill_src = "open" if fill_minute == 0 else ("orh5" if fill_minute is not None else "close_proxy")
    r.stop = float(stop) if stop is not None else r.fill * (1 - adr20)
    r.stop_lvl, r.stop_variant, r.stop_src = r.stop, "T", "ADR20-T"
    r.stop_levels = fz.stop_levels_intra(r)
    mix.add_s4(r)
    r.day0 = rev.day0_for(r, r.fill_minute, r.stop)
    sight = sightings_from([(d_, sym, ctx, clk) for d_, ctx, clk in frames])
    M = {"guards": {"A": {}, "B": {}}}
    return r, store, sight, M


def fires_of(r, store, M):
    prep = fz.exit_prepare(r, M, store)
    ctx = mix.make_ctx(r, prep, store)
    return mix.exit_fires(r, prep, store, ctx, fz.smas_for(r.bars)), prep, ctx


def drop_at(p: float, m_from: int, m_to: int, depth: float, n: int = 390):
    """A quiet session that falls `depth` between minutes m_from and m_to and stays there to the close."""
    return path_minutes([(0, p), (m_from, p), (m_to, p * (1 - depth)), (n - 1, p * (1 - depth))], n)


# ═════════════════════════════════════════════════════════════════════════════════════════════ the four buckets
def test_bucket_precedence_and_the_vector_twin_agree_everywhere():
    F = mix.Fire
    # first firing only: early then (again) inside -> MISS-EARLY; on exit_lo -> EXPLAINS; after exit_hi -> NEITHER
    assert mix.bucket(F(je=1, jb=1), 3, 5) == ME and mix.bucket(F(je=3, jb=3), 3, 5) == EX and mix.bucket(F(je=6, jb=6), 3, 5) == NE
    assert mix.bucket(F(), 3, 5) == NE and mix.bucket(F(abstain="ema_thin", je=3, jb=3), 3, 5) == NE
    # a buy-day firing between flat and first -> UNRESOLVED, also when the window holds the buy day
    assert mix.bucket(F(je=0, jb=0, bd_unres=True), 3, 5) == UN and mix.bucket(F(je=0, jb=0, bd_unres=True), 0, 2) == UN
    # a missing session before the firing never upgrades it: UNRESOLVED; one after the firing changes nothing; none by the window's end
    assert mix.bucket(F(je=4, jb=4, missing=(2,)), 3, 5) == UN and mix.bucket(F(je=1, jb=1, missing=(2,)), 3, 5) == ME
    assert mix.bucket(F(missing=(4,)), 3, 5) == UN and mix.bucket(F(missing=(9,)), 3, 5) == NE
    # a booked session (a last-bar close) after exit_hi reads NEITHER even when the event was inside
    assert mix.bucket(F(je=5, jb=6), 3, 5) == NE
    # R2: the alternatives agree -> their bucket; disagree -> UNRESOLVED
    assert mix.bucket(F(je=0, jb=0, alt=F(je=1, jb=1)), 3, 5) == ME
    assert mix.bucket(F(je=0, jb=0, alt=F(je=4, jb=4)), 3, 5) == UN
    assert mix.bucket(F(je=0, jb=0, alt=F()), 3, 5) == UN
    # R15: without frames a buy-day firing reads by the window alone (inside -> EXPLAINS, before -> MISS-EARLY); the missing rule stays
    assert mix.BUCKETS[int(mix.bucket_vec(F(je=0, jb=0, bd_unres=True), np.array([0]), 2, frames=False)[0])] == EX
    assert mix.BUCKETS[int(mix.bucket_vec(F(je=0, jb=1, bd_unres=True), np.array([2]), 2, frames=False)[0])] == ME
    assert mix.BUCKETS[int(mix.bucket_vec(F(je=4, jb=4, missing=(2,)), np.array([3]), 2, frames=False)[0])] == UN
    # the vector twin on every placement equals the scalar, over many random firings and windows
    rng = np.random.default_rng(7)
    for _ in range(3000):
        je = int(rng.integers(0, 12)) if rng.random() < 0.85 else None
        jb = None if je is None else je + int(rng.random() < 0.3)
        miss = tuple(sorted(set(int(x) for x in rng.integers(0, 14, size=int(rng.integers(0, 3))))))
        f = F(je=je, jb=jb, bd_unres=bool(je == 0 and rng.random() < 0.5), missing=miss, abstain="x" if rng.random() < 0.05 else "")
        if je is not None and rng.random() < 0.15:
            f = F(je=0, jb=0, alt=f)
        w = int(rng.integers(1, 5))
        starts = np.arange(0, 12)
        vec = mix.bucket_vec(f, starts, w)
        for s, code in zip(starts, vec):
            assert mix.BUCKETS[int(code)] == mix.bucket(f, int(s), int(s) + w - 1), (f, s, w)


def test_four_buckets_on_a_daily_rule_m3_and_the_buy_day_frame():
    """M-3 (the first close under the 10-day): fires at +2 (a drop) and again at +6 — an early firing then an inside one reads MISS-EARLY;
    the window on +2 EXPLAINS; a window before it NEITHER. A buy-day close under the average with no in-session buy-day frame -> UNRESOLVED."""
    sess = {2: lambda p: drop_at(p, 200, 260, 0.08), 3: lambda p: quiet(p * 1.09), 6: lambda p: drop_at(p, 200, 260, 0.08), 7: lambda p: quiet(p * 1.09)}
    r, store, sight, M = unit_rec(exit_lo=6, exit_hi=6, sess=sess)
    f, prep, ctx = fires_of(r, store, M)
    assert f["M-3"].je == 2 and f["M-3"].jb == 2 and f["M-3"].m == mix.CLOSE_M
    assert mix.bucket(f["M-3"], 6, 6) == ME and mix.bucket(f["M-3"], 2, 3) == EX and mix.bucket(f["M-3"], 0, 1) == NE
    # the buy-day close under the 10-day, no in-session buy-day frame -> UNRESOLVED; with the frame -> certain (MISS-EARLY before exit_lo)
    sess0 = {0: lambda p: drop_at(p, 300, 380, 0.10), 1: lambda p: quiet(p * 1.11)}
    r0, s0, _sg, M0 = unit_rec(exit_lo=3, exit_hi=4, sess=sess0, first=None, flat=None)
    f0, _p, ctx0 = fires_of(r0, s0, M0)
    assert ctx0.first_m is None and f0["M-3"].je == 0 and f0["M-3"].bd_unres and mix.bucket(f0["M-3"], 3, 4) == UN
    r1, s1, _sg, M1 = unit_rec(exit_lo=3, exit_hi=4, sess=sess0)
    f1, _p, _c = fires_of(r1, s1, M1)
    assert f1["M-3"].je == 0 and not f1["M-3"].bd_unres and mix.bucket(f1["M-3"], 3, 4) == ME


def test_m1_sixty_minute_close_the_last_bar_books_the_next_session_and_the_buy_day_rule():
    # a drop inside the 11:00-12:00 bar of +3 -> M-1 at that bar's close, booked on +3 (a next minute exists)
    r, store, sight, M = unit_rec(exit_lo=3, exit_hi=3, sess={3: lambda p: drop_at(p, 95, 140, 0.03)})
    f, prep, ctx = fires_of(r, store, M)
    assert not prep["thin"] and prep["armed"] is not None
    assert f["M-1"].je == 3 and f["M-1"].m == 149 and f["M-1"].jb == 3 and f["M-1"].sale_m == 150 and mix.bucket(f["M-1"], 3, 3) == EX
    # a drop in the LAST hour only -> the 15:00-16:00 bar closes under -> booked on the NEXT session (its open): NEITHER on a one-session window
    r2, s2, _sg, M2 = unit_rec(exit_lo=3, exit_hi=3, sess={3: lambda p: drop_at(p, 340, 385, 0.03)})
    f2, _p, _c = fires_of(r2, s2, M2)
    assert f2["M-1"].je == 3 and f2["M-1"].m == 389 and f2["M-1"].jb == 4 and f2["M-1"].sale_m == 0
    assert mix.bucket(f2["M-1"], 3, 3) == NE and mix.bucket(f2["M-1"], 4, 5) == EX
    # the buy day: a close under the EMA at or before flat_clock is not an event (the scan goes on); the frame-free firing stays for gate viii-b
    sess = {0: lambda p: path_minutes([(0, p), (10, p * 0.95), (28, p * 0.95), (40, p), (389, p)]), 4: lambda p: drop_at(p, 95, 140, 0.03)}
    r3, s3, _sg, M3 = unit_rec(exit_lo=4, exit_hi=4, sess=sess, flat="10:05", first="10:40")
    f3, _p, _c = fires_of(r3, s3, M3)
    assert f3["M-1"].raw_jb == 0 and f3["M-1"].je == 4 and mix.bucket(f3["M-1"], 4, 4) == EX
    # ... between flat and first -> UNRESOLVED
    sess_u = {0: lambda p: path_minutes([(0, p), (40, p), (55, p * 0.95), (80, p * 0.95), (100, p), (389, p)])}
    r4, s4, _sg, M4 = unit_rec(exit_lo=4, exit_hi=4, sess=sess_u, flat="10:05", first="11:40")
    f4, _p, _c = fires_of(r4, s4, M4)
    assert f4["M-1"].je == 0 and f4["M-1"].bd_unres and mix.bucket(f4["M-1"], 4, 4) == UN
    # a session without minutes between the armed point and an in-window firing -> UNRESOLVED (missing data never upgrades)
    r5, s5, _sg, M5 = unit_rec(exit_lo=4, exit_hi=4, sess={4: lambda p: drop_at(p, 95, 140, 0.03)}, empty={2})
    f5, _p, ctx5 = fires_of(r5, s5, M5)
    assert 2 in ctx5.nomin and f5["M-1"].je == 4 and mix.bucket(f5["M-1"], 4, 4) == UN and mix.bucket(f5["M-1"], 5, 6) == UN
    # ema_thin abstains M-1 and, through it, M-2s (R6); M-2 still reads its touch
    r6, s6, _sg, M6 = unit_rec(exit_lo=4, exit_hi=4, empty=set(range(-10, -2)))
    f6, p6, _c = fires_of(r6, s6, M6)
    assert p6["thin"] and f6["M-1"].abstain == "ema_thin" and f6["M-2s"].abstain == "m1_ema_thin" and not f6["M-2"].abstain


def test_m2_touch_and_m2s_the_fsly_sequence():
    """FSLY shape: the unconditional prior-low touch comes early (+1, MISS-EARLY), the 60-minute close under the EMA on +2 (before the window,
    staying above +1's low), the first touch AFTER that close on +3 (inside) -> M-2s EXPLAINS; a world whose first touch follows the close ->
    M-2 takes the tag. Every session's dip low sits above the previous session's low (a staircase), so no touch comes before the ones planted."""
    def dip(depth):
        return lambda p: path_minutes([(0, p), (40, p), (45, p * (1 - depth)), (50, p), (389, p)])
    slide = lambda p: path_minutes([(0, p), (95, p), (140, p * 0.985), (389, p * 0.985)])     # noqa: E731
    through = lambda p: path_minutes([(0, p), (60, p), (90, p * 0.97), (389, p * 0.97)])      # noqa: E731
    for with_dip in (True, False):
        sess = {-2: dip(0.10), -1: dip(0.07), 0: dip(0.04), 1: dip(0.05 if with_dip else 0.025), 2: slide, 3: through}
        r, store, sight, M = unit_rec(exit_lo=3, exit_hi=4, sess=sess, rise=0.0)
        f, prep, ctx = fires_of(r, store, M)
        assert f["M-1"].je == 2 and f["M-1"].m == 149 and mix.bucket(f["M-1"], 3, 4) == ME
        assert f["M-2s"].je == 3 and mix.bucket(f["M-2s"], 3, 4) == EX
        real = {c: mix.bucket(f[c], 3, 4) for c in mix.LIB_CODES["EXIT"]}
        if with_dip:
            assert f["M-2"].je == 1 and real["M-2"] == ME
            assert mix.greedy_tag({c: v for c, v in real.items() if c in ("M-1", "M-2", "M-2s")}, mix.LIB_CODES["EXIT"]) == "M-2s"
        else:
            assert f["M-2"].je == 3 and real["M-2"] == EX and mix.greedy_tag(real, mix.LIB_CODES["EXIT"]) == "M-2"


def test_m7_daily_close_under_the_prior_low_books_the_next_open_and_m8_from_session_two():
    sess = {3: lambda p: path_minutes([(0, p), (200, p * 0.97), (389, p * 0.97)]), 4: lambda p: quiet(p * 1.04)}
    r, store, sight, M = unit_rec(exit_lo=4, exit_hi=4, sess=sess)
    f, prep, ctx = fires_of(r, store, M)
    assert f["M-7"].je == 3 and f["M-7"].jb == 4 and f["M-7"].sale_m == 0 and mix.bucket(f["M-7"], 4, 4) == EX
    assert f["M-8"].je == 3 and mix.bucket(f["M-8"], 4, 4) == ME                 # the first red close, from session 2 on
    # the buy day's own red close is not M-8's (R17), it is M-3's / M-10's arming
    r2, s2, _sg, M2 = unit_rec(exit_lo=4, exit_hi=4, sess={0: lambda p: path_minutes([(0, p), (200, p * 0.97), (389, p * 0.97)])})
    f2, _p, _c = fires_of(r2, s2, M2)
    assert f2["M-8"].je is None or f2["M-8"].je >= 1


def test_m5_is_a_subset_of_m9_m6_on_the_registered_r_and_m10_thresholds():
    # a stalled trade: no high at fill + 1R by the close of offset 2 -> M-5 fires at offset 2 with M-9; M-5 sits first, so it takes the tag
    r, store, sight, M = unit_rec(exit_lo=2, exit_hi=2, adr20=0.05, rise=0.001)
    f, prep, ctx = fires_of(r, store, M)
    assert f["M-5"].je == 2 and f["M-9"].je == 2
    real = {c: mix.bucket(f[c], 2, 2) for c in mix.LIB_CODES["EXIT"]}
    assert real["M-5"] == EX and real["M-9"] == EX and mix.greedy_tag(real, mix.LIB_CODES["EXIT"]) in ("M-5", "M-3", "M-4", "M-1", "M-2")
    order_pos = mix.LIB_CODES["EXIT"].index
    assert order_pos("M-5") == order_pos("M-9") - 1                                       # the subset rule: M-5 directly before M-9
    # a trade that reached +1R on offset 1: M-5 silent, M-9 still fires (M-9's greedy share reads "session-3 sells after +1R")
    r2, s2, _sg, M2 = unit_rec(exit_lo=2, exit_hi=2, adr20=0.05, rise=0.001, sess={1: lambda p: path_minutes([(0, p), (100, p * 1.07), (389, p * 1.06)])})
    f2, _p, _c = fires_of(r2, s2, M2)
    assert f2["M-5"].je is None and f2["M-9"].je == 2
    # M-6: +2R on the registered stop's width (R = fill - stop): a high at fill + 2R on offset 3 (fill 100, stop 95 -> 110)
    hit = {3: lambda p: path_minutes([(0, p), (120, 111.0), (389, p)])}
    r3, s3, _sg, M3 = unit_rec(exit_lo=5, exit_hi=5, sess=hit, fill=100.0, stop=95.0, rise=0.0)
    f3, _p, _c = fires_of(r3, s3, M3)
    assert mix.r_unit(r3) == pytest.approx(5.0) and f3["M-6"].je == 3 and f3["M-6"].m == 119 and mix.bucket(f3["M-6"], 5, 5) == ME
    r3b, s3b, _sg, M3b = unit_rec(exit_lo=5, exit_hi=5, sess={3: lambda p: path_minutes([(0, p), (120, 109.0), (389, p)])}, fill=100.0, stop=95.0, rise=0.0)
    assert fires_of(r3b, s3b, M3b)[0]["M-6"].je is None
    # M-10: a big up day = close >= prior close x (1 + 1.5 ADR20); just over fires, just under does not (no extension on a flat series)
    for k, want in ((1.0011, 4), (0.9989, None)):
        up = {4: lambda p, k=k: path_minutes([(0, p), (389, p * (1 + 1.5 * 0.04) * k)])}
        r4, s4, _sg, M4 = unit_rec(exit_lo=6, exit_hi=6, sess=up, rise=0.0, adr20=0.04)
        assert fires_of(r4, s4, M4)[0]["M-10"].je == want, k
    # the extension: close >= the 10-day x (1 + 2 ADR20) on a slow climb that would not be a big up day
    ext = {j: (lambda p: path_minutes([(0, p), (389, p * 1.055)])) for j in range(1, 4)}
    r5, s5, _sg, M5 = unit_rec(exit_lo=6, exit_hi=6, sess=ext, rise=0.0, adr20=0.04)
    f5 = fires_of(r5, s5, M5)[0]
    c5, sma = r5.bars.c, fz.smas_for(r5.bars)[10]
    k5 = r5.bar_at(f5["M-10"].je)
    assert f5["M-10"].je is not None and c5[k5] >= sma[k5] * (1 + 2 * 0.04)


def test_stop_cells_through_the_frozen_function_close_fill_alternatives_exit_lo_and_h_booking():
    smas_of = lambda r: fz.smas_for(r.bars)                                         # noqa: E731
    # S3-T (the prior low): touched at +2 then again at +4 (inside) -> MISS-EARLY (first touch only)
    dip = lambda p: path_minutes([(0, p), (100, p), (105, p * 0.96), (110, p), (389, p)])      # noqa: E731
    r, store, sight, M = unit_rec(exit_lo=4, exit_hi=4, sess={2: dip, 4: dip}, frames=())
    nomin = mix.nomin_sessions(r, store, 10)
    f, h = mix.stop_fire(r, "S3-T", smas_of(r), sight, store, 10, nomin)
    assert h["first_j"] == 2 and mix.bucket(f, 4, 4) == ME
    # R3: a touch ON exit_lo with no frame that day -> the frozen 'unresolved' (exit_lo) -> EXPLAINS here
    r2, s2, sg2, M2 = unit_rec(exit_lo=4, exit_hi=4, sess={4: lambda p: path_minutes([(0, p), (100, p), (105, p * 0.9), (389, p * 0.9)])}, frames=())
    fS4, h2 = mix.stop_fire(r2, "S4-T", smas_of(r2), sg2, s2, 10, mix.nomin_sessions(r2, s2, 10))
    assert h2["first_j"] == 4 and h2["unresolved"] and not fS4.bd_unres and mix.bucket(fS4, 4, 4) == EX
    # ... a frame later that day showing the name contradicts the EXPLAINS (counted); none before the touch does not
    E4 = r2.session_date(4)
    sgc = sightings_from([(E4, "AAA", "in", "14:30")])
    fS4c, h2c = mix.stop_fire(r2, "S4-T", smas_of(r2), sgc, s2, 10, mix.nomin_sessions(r2, s2, 10))
    assert mix.bucket(fS4c, 4, 4) == EX and mix.contradicted(r2, fS4c, sgc) and h2c["certain"]
    assert not mix.contradicted(r2, fS4c, sightings_from([(E4, "AAA", "in", "09:40")]))
    # R2: a close fill (dated close proxy) whose buy-day low reached the level: the alternatives agree (a later touch before exit_lo) -> MISS-EARLY
    for later, want in ((2, ME), (4, UN), (None, UN)):
        sess = {0: lambda p: path_minutes([(0, p), (100, p * 0.90), (389, p * 1.0)])}
        if later is not None:
            sess[later] = lambda p: path_minutes([(0, p), (100, p * 0.85), (389, p * 0.98)])
        r3, s3, sg3, M3 = unit_rec(exit_lo=4, exit_hi=5, sess=sess, fill_minute=None, setup="breakout", adr20=0.04)
        r3.fill = float(r3.bars.c[r3.e]) * 1.001                        # the dated close-fill proxy (the buy day's close + 0.1%)
        r3.stop_levels = fz.stop_levels_intra(r3)
        mix.add_s4(r3)
        assert fnum_low(r3, 0) <= r3.stop_levels["S4"]                  # the precondition: the buy-day low reached the level
        f3, h3 = mix.stop_fire(r3, "S4-T", smas_of(r3), sg3, s3, 12, mix.nomin_sessions(r3, s3, 12))
        assert f3.alt is not None and h3["unresolved"] and f3.alt.je == later, (later, h3)
        assert mix.bucket(f3, 4, 5) == want, later
        # frame-free control mode (R15): the buy-day alternative alone
        assert mix.BUCKETS[int(mix.bucket_vec(f3, np.array([4]), 2, frames=False)[0])] == ME
    # H: a 60-minute close under S3 on the LAST bar of +3 -> books +4 (R4): EXPLAINS on a window starting +4, NEITHER on [3, 3]
    last = lambda p: path_minutes([(0, p), (340, p), (385, p * 0.97), (389, p * 0.97)])    # noqa: E731
    r4, s4, sg4, M4 = unit_rec(exit_lo=4, exit_hi=4, sess={3: last, 4: lambda p: quiet(p * 1.04)})
    f4, h4 = mix.stop_fire(r4, "S3-H", smas_of(r4), sg4, s4, 10, mix.nomin_sessions(r4, s4, 10))
    assert h4["first_j"] == 3 and f4.je == 3 and f4.jb == 4 and mix.bucket(f4, 4, 4) == EX and mix.bucket(f4, 3, 3) == NE
    # H: a session without minutes before the firing -> UNRESOLVED; a T cell on the same record is not touched by it
    r5, s5, sg5, M5 = unit_rec(exit_lo=4, exit_hi=4, sess={4: lambda p: path_minutes([(0, p), (100, p), (140, p * 0.9), (389, p * 0.9)])}, empty={2})
    nm5 = mix.nomin_sessions(r5, s5, 10)
    f5, h5 = mix.stop_fire(r5, "S4-H", smas_of(r5), sg5, s5, 10, nm5)
    f5t, _h = mix.stop_fire(r5, "S4-T", smas_of(r5), sg5, s5, 10, nm5)
    assert h5["no_bar_sessions"] >= 1 and mix.bucket(f5, 4, 4) == UN and mix.bucket(f5t, 4, 4) == EX
    # continued past exit_hi for control (b): a T touch at +8 (exit_hi +4) is found by the continuation
    r6, s6, sg6, M6 = unit_rec(exit_lo=3, exit_hi=4, sess={8: lambda p: path_minutes([(0, p), (100, p * 0.9), (389, p * 0.9)])})
    f6, h6 = mix.stop_fire(r6, "S4-T", smas_of(r6), sg6, s6, 12, mix.nomin_sessions(r6, s6, 12))
    assert h6["first_j"] is None and f6.je == 8 and mix.bucket(f6, 3, 4) == NE and mix.bucket(f6, 7, 8) == EX


def fnum_low(r, j):
    return float(r.bars.l[r.bar_at(j)])


def test_every_rule_and_cell_reads_the_four_buckets_by_its_booked_session():
    """All twelve EXIT rules and fifteen STOP cells on one designed path (a quiet climb, a breakdown on +2 through the day's open-range lows,
    the prior low, the 10- and 20-day averages and one ADR20 under the fill, a big up day on +6, a slow climb to +2R): each rule's first
    firing reads EXPLAINS on a window holding its booked session, MISS-EARLY on a window after it, NEITHER on one before it — the scalar and
    the vector twin alike; M-4 is the 20-day, M-9 / M-11 sit on offsets 2 / 4."""
    brk = lambda p: path_minutes([(0, p), (60, p * 1.004), (100, p * 0.93), (389, p * 0.90)])          # noqa: E731
    sess = {2: brk, 3: lambda p: quiet(p * 1.0), 6: lambda p: path_minutes([(0, p), (389, p * 1.08)])}
    r, store, sight, M = unit_rec(n=110, e=70, exit_lo=8, exit_hi=9, sess=sess, fill_minute=0, adr20=0.04, rise=0.006, first="10:40", flat="10:05")
    f, prep, ctx = fires_of(r, store, M)
    nomin = mix.nomin_sessions(r, store, int(prep["J_tail"]))
    sf = {c: mix.stop_fire(r, c, fz.smas_for(r.bars), sight, store, int(prep["J_tail"]), nomin)[0] for c in mix.LIB_CODES["STOP"]}
    assert f["M-9"].je == 2 and f["M-11"].je == 4 and f["M-3"].je == 2 and f["M-4"].je == 2 and f["M-1"].je == 2 and f["M-2"].je == 2
    assert f["M-7"].je == 2 and f["M-7"].jb == 3 and f["M-8"].je == 2 and f["M-10"].je == 6 and f["M-2s"].je == 2
    sma20 = fz.smas_for(r.bars)[20]
    k2 = r.bar_at(2)
    assert r.bars.c[k2] < sma20[k2] and r.bars.c[r.bar_at(1)] >= sma20[r.bar_at(1)]                   # M-4 reads the 20-day
    fired = 0
    for code, fire in list(f.items()) + list(sf.items()):
        if fire.abstain or fire.jb is None or fire.bd_unres or fire.alt is not None:
            continue
        fired += 1
        jb = fire.jb
        for lo, hi, want in ((jb, jb, EX), (max(0, jb - 1), jb + 1, EX), (jb + 1, jb + 2, ME), (max(0, jb - 3), jb - 1, NE)):
            if hi < 0 or lo > hi:
                continue
            got = mix.bucket(fire, lo, hi)
            assert got == want, (code, fire, lo, hi)
            assert mix.BUCKETS[int(mix.bucket_vec(fire, np.array([lo]), hi - lo + 1)[0])] == got, code
    assert fired >= 20, fired
    assert all(not sf[c].abstain for c in mix.LIB_CODES["STOP"]) and sum(1 for c in mix.LIB_CODES["STOP"] if sf[c].je == 2 or sf[c].jb == 3) >= 10


def test_random_windows_placements_width_no_room_and_the_cut_path():
    r, store, sight, M = unit_rec(exit_lo=3, exit_hi=5)
    a = mix.random_windows(r, 25, "a")
    b = mix.random_windows(r, 25, "b")
    assert list(a["starts"]) == [0, 1, 2, 3] and a["width"] == 3 and not a["no_room"]
    assert list(b["starts"]) == list(range(0, 5 + 20 - 3 + 2)) and not b["cut"]
    bc = mix.random_windows(r, 12, "b")                                         # a path bounded at J_tail 12 (a hole / the horizon / the data's end)
    assert bc["cut"] and bc["starts"][-1] == 12 - 3 + 1
    r0, *_ = unit_rec(exit_lo=0, exit_hi=0)                                      # a buy-day sell: control (a) has ONE placement -> no_room
    assert mix.random_windows(r0, 20, "a")["no_room"]
    # the width on the record's OWN calendar (an era-B record: the global calendar would read it differently)
    cal_glob = sessions(900, "2019-01-02")
    own = cal_glob[600:]
    b2 = mk_buy(eid=9, sym="BBB", sym_a="BBB", E=own[100].isoformat(), lo=own[100].isoformat(), hi=own[100].isoformat(), exit_lo=own[103].isoformat(), exit_hi=own[106].isoformat())
    rb = fz.IRec(b=b2, bars=None, cidx=np.arange(len(own), dtype=np.int32), e=100, adr20=0.04, cal=own, era="B")
    rb.exit_lo_j, rb.exit_hi_j = rb.off(b2.exit_lo), rb.off(b2.exit_hi)
    assert (rb.exit_lo_j, rb.exit_hi_j) == (3, 6) and fz.exit_window_sessions(rb) == 4
    # the window summary: the per-rule shares, greedy and union over the placements
    F = mix.Fire
    fires = {"X": F(je=1, jb=1), "Y": F(je=2, jb=2)}
    ws = mix.window_summary(fires, ("X", "Y"), np.arange(0, 4), 2)
    assert ws["n"] == 4 and ws["ex"]["X"] == 0.5 and ws["greedy"]["Y"] == 0.25 and ws["union"] == 0.75


def test_greedy_and_earliest_firing_orders():
    order = ("A", "B", "C")
    b = {"A": ME, "B": EX, "C": EX}
    assert mix.greedy_tag(b, order) == "B" and mix.greedy_tag({"A": NE}, order) == "discretion"
    times = {"A": (1, 10), "B": (3, 100), "C": (3, 50)}
    assert mix.earliest_tag(b, times, order) == "C"
    assert mix.earliest_tag({"B": EX, "C": EX}, {"B": (3, 50), "C": (3, 50)}, order) == "B"          # ties -> the library order


def test_random_level_vector_scan_equals_the_frozen_touch_on_every_fill_kind():
    """R9: the k-level union's vectorised touch scan reproduces, level for level, the frozen held_through_intra on a bare price (the per-rule
    floor) — on an intraday fill with minutes (the buy-day rule), an open fill without minutes, a close fill (R2), windows from 0 and later."""
    dip = lambda p: path_minutes([(0, p), (60, p * 0.97), (200, p * 0.95), (389, p * 0.99)])       # noqa: E731
    cases = [dict(fill_minute=0, exit_lo=3, exit_hi=4), dict(fill_minute=45, exit_lo=2, exit_hi=3, setup="breakout"), dict(fill_minute=0, exit_lo=0, exit_hi=1),
             dict(fill_minute=None, exit_lo=3, exit_hi=5, setup="breakout"), dict(fill_minute=0, exit_lo=2, exit_hi=2, first=None, flat=None)]
    for kw in cases:
        r, store, sight, M = unit_rec(sess={0: dip, 1: dip, 2: dip, 3: dip}, **kw)
        if kw.get("fill_minute") is None:
            r.fill = float(r.bars.c[r.e]) * 1.001
        if kw.get("first", "x") is None:
            r.mb = None                                                        # an open fill WITHOUT buy-day minutes
        smas = fz.smas_for(r.bars)
        r.rlevel_lowest = mix.hold_lowest_low(r, store)
        lv = np.linspace(r.rlevel_lowest, r.fill, 60)
        path = mix.touch_path(r, store)
        vec = mix.touch_buckets_vec(path, lv, r.exit_lo_j, r.exit_hi_j)
        sc = [mix.CODE_OF[mix.bucket(mix.stop_fire_bare(r, float(x), smas, sight, store), r.exit_lo_j, r.exit_hi_j)] for x in lv]
        assert list(vec) == sc, kw
    # the draws: keyed, reproducible, inside [lowest low, fill); no room when the hold never went under the fill
    r, store, sight, M = unit_rec(sess={1: dip})
    r.rlevel_lowest = mix.hold_lowest_low(r, store)
    d1, d2 = mix.random_level_draws(r, mix.RLEVEL_KEY), mix.random_level_draws(r, mix.RLEVEL_KEY)
    assert np.array_equal(d1, d2) and d1.min() >= r.rlevel_lowest and d1.max() < r.fill and d1.shape == (200,)
    assert mix.random_level_draws(r, mix.RLEVEL_K_KEY, 12).shape == (200, 12)
    r.rlevel_lowest = r.fill * 1.01
    assert mix.random_level_draws(r, mix.RLEVEL_KEY) is None


def enter_unit(flat="10:05", first="10:40"):
    """An ENTER window on a hand session: an opening range, then a climb through it inside the window."""
    pts = [(0, 50.0), (3, 50.4), (5, 50.1), (20, 50.6), (29, 50.2), (40, 51.5), (60, 52.0), (389, 52.5)]
    r, store, sight, M = unit_rec(sess={0: lambda p: path_minutes([(m, x * p / 50.0) for m, x in pts])}, flat=flat, first=first)
    r.levels = {}
    return r, store


def test_enter_one_controls_identity_and_the_playback_guard():
    r, store = enter_unit()
    u = fz.rng_for(fz.RANDOM_KEY).integers(0, 390, size=fz.RANDOM_LEVELS)
    e = mix.enter_one(r, u, "fit")
    order = mix.LIB_CODES["ENTER"]
    assert set(e["real"]) == set(order) and e["width"] == 35 and e["flat_m"] == 35
    # the playback draws ARE the frozen control's draws: the same res as the live generator in the same order
    r2, _s = enter_unit()
    res_live = fz.enter_score_trade(r2, fz.rng_for(fz.RANDOM_KEY), with_shift=True)
    assert np.array_equal(res_live["control"]["feas"], e["res"]["control"]["feas"]) and res_live["control"]["feasible_share"] == e["res"]["control"]["feasible_share"]
    # gate (x): the shared-window machinery placed at the real window reproduces every real feasible flag
    for lv in order:
        x, _m = mix.window_feasible(e["crosses"][lv], fz.LEVEL_EXISTS.get(lv, 0), np.array([e["flat_m"]]), e["width"])
        assert bool(x[0]) == (e["real"][lv] == EX) == bool(e["res"][lv]["feasible"]), lv
    # the k-price and shared-window controls: keyed, in range, reproducible
    e2 = mix.enter_one(enter_unit()[0], u, "fit")
    assert e2["kprice"]["union"] == e["kprice"]["union"] and np.array_equal(e2["kprice"]["prices"], e["kprice"]["prices"])
    assert np.array_equal(e2["shared"]["starts"], e["shared"]["starts"])
    st = e["shared"]["starts"]
    assert st.min() >= 1 and st.max() <= 390 - 35 and len(st) == mix.DRAWS
    assert 0.0 <= e["kprice"]["union"] <= 1.0 and abs(sum(e["kprice"]["greedy"].values()) - e["kprice"]["union"]) < 1e-12
    # the k-price keys are the registered i = 1..7 (price i stands for library rule i): every draw re-read from its own key
    eid = r.b.eid
    for d in (0, 1, 57, 199):
        for i in range(1, 8):
            want = fz.fnum(rev.random_levels(r.mb, 1, fz.rng_for(mix.K_KEY.format(eid=eid, d=d, i=i)))[0])
            assert e["kprice"]["prices"][d, i - 1] == want, (d, i)
    assert e["kprice"]["prices"][0, 0] != fz.fnum(rev.random_levels(r.mb, 1, fz.rng_for(mix.K_KEY.format(eid=eid, d=0, i=0)))[0])
    # the shared window's start: uniform over [09:31, the close - width] — each draw re-read from its key (the floor is minute 1, not 0)
    close = fz.session_end_minute(r.b.E)
    want = [1 + int(fz.rng_for(mix.SHARED_KEY.format(eid=eid, d=d)).integers(0, close - 35)) for d in range(mix.DRAWS)]
    assert list(st) == want
    # a window too wide for the session: the shared window and a late-existing level's shifted control have no room
    rw, _s = enter_unit(flat="09:31", first="15:45")
    ew = mix.enter_one(rw, u, "fit")
    assert ew["shift"]["room"]["L8"] is False and ew["shift"]["room"]["L1"] is True and not ew["shared"]["no_room"]
    rw2, _s = enter_unit(flat="09:30", first="16:00")
    assert mix.enter_one(rw2, u, "fit")["shared"]["no_room"] is True
    # a level that does not exist yet at the window's end is never feasible (L8 before 10:00)
    x, _m = mix.window_feasible(5, 30, np.array([0, 10]), 15)
    assert not x.any()
    # the playback refuses a second call or another shape
    pb = mix.Playback(u)
    pb.integers(0, 390, size=200)
    with pytest.raises(mix.GuardStop):
        pb.integers(0, 390, size=200)
    with pytest.raises(mix.GuardStop):
        mix.Playback(u).integers(0, 391, size=200)
    # the ENTER buckets: crossed at or before flat -> MISS-EARLY; inside -> EXPLAINS; after first / never / abstaining -> NEITHER
    assert mix.enter_bucket(dict(cross=30, feasible=False, verdict="HIT"), 35, 70) == ME
    assert mix.enter_bucket(dict(cross=50, feasible=True, verdict="HIT"), 35, 70) == EX
    assert mix.enter_bucket(dict(cross=80, feasible=False, verdict="MISS"), 35, 70) == NE
    assert mix.enter_bucket(dict(cross=None, feasible=False, verdict="no_level_yet"), 35, 70) == NE
    assert mix.enter_bucket(dict(cross=35, feasible=False, verdict="HIT"), 35, 70) == ME          # a cross exactly at flat_clock: MISS-EARLY


def test_replay_draws_walk_the_shared_stream_in_the_previous_order():
    orders = {"fit": [("", [5, 3, 9]), ("b", [2])], "check": [("", [7])]}
    d = mix.replay_draws(orders)
    g = fz.rng_for(fz.RANDOM_KEY)
    for eid in (5, 3, 9, 2):
        assert np.array_equal(d[("fit", eid)], g.integers(0, 390, size=fz.RANDOM_LEVELS))
    assert np.array_equal(d[("check", 7)], fz.rng_for(fz.RANDOM_KEY).integers(0, 390, size=fz.RANDOM_LEVELS))
    with pytest.raises(mix.GuardStop):
        mix.replay_draws({"fit": [("", [1, 1])]})


def test_viii_a_the_frozen_walk_with_a_stop_pre_empting_and_viii_b_without():
    """With the chain's stop touched at +2 the frozen E1 walk's last leg is the stop's session (stop_preempt) while the no-stop M-1 fires at +4
    (a NEW number, not gated); with the stop far away the walk's E1 leg = this module's frame-free M-1 booked session (gate viii-b)."""
    sess = {2: lambda p: path_minutes([(0, p), (40, p), (45, p * 0.95), (50, p), (389, p)]), 4: lambda p: drop_at(p, 95, 140, 0.03)}
    for stop_far, want_pre in ((False, True), (True, False)):
        r, store, sight, M = unit_rec(exit_lo=4, exit_hi=4, sess=sess, stop=(1.0 if stop_far else None))
        if not stop_far:
            r.stop = float(r.bars.o[r.bar_at(2)]) * 0.97            # under the buy day's and +1's lows; touched on +2 (its dip to -5%)
        r.stop_lvl = r.stop
        r.day0 = rev.day0_for(r, r.fill_minute, r.stop)
        prep = fz.exit_prepare(r, M, store)
        w = fz.exit_walk_intra(r, "E1", prep["seq"], prep["armed"], store, fz.smas_for(r.bars), prep["J_tail"])
        ctx = mix.make_ctx(r, prep, store)
        m1 = mix.fire_m1(r, prep, store, ctx)
        assert w["stop_preempt"] == want_pre and m1.raw_jb == 4
        if want_pre:
            assert w["last_j"] == 2
        else:
            assert mix._legs_j(";".join(f"{lg.kind}@{lg.j}" for lg in w["legs"]), ("e1",)) == m1.raw_jb


def test_fsly_shaped_buckets_and_gate_ix():
    """His FSLY words on a synthetic FSLY: the 60-minute close under the EMA one session before his window (MISS-EARLY, booked by X), the
    prior-low touch by X+1 for M-2 and M-2s; gate (ix) passes, and STOPS when the window is moved onto X (M-1 would EXPLAIN)."""
    crash = lambda p: path_minutes([(0, p), (130, p * 1.001), (260, p * 0.895), (389, p * 0.90)])   # noqa: E731
    r, store, sight, M = unit_rec(exit_lo=10, exit_hi=11, sess={9: crash, 10: lambda p: path_minutes([(0, p * 0.99), (200, p * 0.965), (389, p * 0.97)])})
    X, X1 = r.session_date(9), r.session_date(10)
    t = {"rec": r, "status": ""}
    prep = fz.exit_prepare(r, M, store)
    ctx = mix.make_ctx(r, prep, store)
    f = mix.exit_fires(r, prep, store, ctx, fz.smas_for(r.bars))
    t["exit_fires"], t["exit_real"] = f, {c: mix.bucket(f[c], 10, 11) for c in mix.LIB_CODES["EXIT"]}
    t["exit_tag"] = mix.greedy_tag(t["exit_real"], mix.LIB_CODES["EXIT"])
    assert t["exit_real"]["M-1"] == ME and f["M-1"].jb == 9 and t["exit_real"]["M-2"] != NE and t["exit_real"]["M-2s"] != NE
    old = dict(mix.FSLY)
    try:
        mix.FSLY.update(eid=r.b.eid, sym=r.b.sym, E=r.b.E, exit_lo=r.b.exit_lo, exit_hi=r.b.exit_hi, m1_by=X, touch_by=X1)
        say = rp.Say()
        mix.gate_ix(say, {r.b.eid: t}, store)
        assert "gate (ix) FSLY" in say.lines[-1]
        t2 = dict(t, exit_real=dict(t["exit_real"], **{"M-1": EX}))
        with pytest.raises(mix.GuardStop):
            mix.gate_ix(rp.Say(), {r.b.eid: t2}, store)
    finally:
        mix.FSLY.clear()
        mix.FSLY.update(old)


def test_library_constants_sources_and_order():
    for d in mix.DECISIONS:
        lib = mix.LIBRARY[d]
        assert [r.nid for r in lib] == [f"{d[0]}-{i}" for i in range(1, len(lib) + 1)] or d == "EXIT"
        for r in lib:
            assert re.search(r"his words|his yes|a READING of his words|our reading", r.source), r
            assert r.tier in (1, 2) and r.order_no
            if r.tier == 1 and "his" in r.source:
                assert re.search(r"l\.\d{4}|caption|FSLY", r.source), r
        tiers = [r.tier for r in lib]
        assert tiers == sorted(tiers), d                                                   # tier 1 before tier 2
    assert mix.LIB_CODES["ENTER"] == ("L1", "L8", "L2", "L7", "L3", "L9", "L4")
    assert mix.LIB_CODES["EXIT"] == ("M-1", "M-2", "M-3", "M-4", "M-5", "M-9", "M-6", "M-2s", "M-11", "M-7", "M-8", "M-10")
    assert mix.LIB_CODES["STOP"][:4] == ("S1-T", "S10-T", "S10-H", "S10-C") and mix.LIB_CODES["STOP"][-3:] == ("S4-T", "S4-H", "S4-C")
    assert len(mix.readings_lines()) == 16 and all(ln.strip().startswith(f"R{i}") for i, ln in enumerate(mix.readings_lines(), 1))


def test_mix_claims_stop_on_a_mismatch_or_a_lost_anchor_and_notes_never_stop():
    say = rp.Say()
    c = mix.MixClaims(say)
    a = mix.EXPECT_MIX["run_records"][0]
    assert c(a, "x", "88 / 431 / 149", "88 / 431 / 149") and not c.bad
    c(a, "y", "88", "87")
    c("an anchor that is not in the doc", "z", "1", "1")
    assert len(c.bad) == 2 and "anchor not found" in c.bad[1][1]
    c(a, "n", "199", "at --tag", note=True)
    assert len(c.bad) == 2 and len(c.notes) == 1 and "| NOTE" in say.lines[-1]
    # every anchor of EXPECT_MIX resolves to a line of the real registration
    assert all(fz.doc_line_of(an, mix.DOC) for an, _v in mix.EXPECT_MIX.values())


def test_labels_and_the_summary_mix_rule():
    assert mix.label_of(0.50, 0.30, 0.60) == "carries" and mix.label_of(0.50, 0.30, 0.40) == "weak"
    assert mix.label_of(0.33, 0.30, 0.9) == "chance" and mix.label_of(0.20, 0.30, 0.9) == "below chance" and mix.label_of(0.40, 0.30, 0.9) == "weak"
    # the edges, on the PRINTED one-decimal percentages (0.40 - 0.35 > 0.05 in float; the label must not contradict 40.0% vs 35.0%)
    assert 0.40 - 0.35 > 0.05 and mix.label_of(0.40, 0.35, 0.9) == "chance" and mix.label_of(0.30, 0.35, 0.9) == "chance"
    assert mix.label_of(0.50, 0.35, 0.50) == "carries"                    # exactly 15.0 points over AND precision exactly 50.0%
    assert mix.label_of(0.4994, 0.35, 0.9) == "weak" and mix.label_of(0.50, 0.35, 0.4994) == "weak"
    assert mix.label_of(0.2994, 0.35, 0.9) == "below chance" and mix.label_of(0.351, 0.30, 0.9) == "weak"
    assert mix.mix_label(0.65, 0.50) and mix.mix_label(0.45, 0.30) and not mix.mix_label(0.649, 0.50) and not mix.mix_label(math.nan, 0.5)
    say = rp.Say()
    per = {"2020": dict(labels={c: "carries" for c in mix.LIB_CODES["ENTER"]}, union=0.7, chance_union=0.5),
           "2021-22": dict(labels={c: ("carries" if c == "L1" else "weak") for c in mix.LIB_CODES["ENTER"]}, union=0.7, chance_union=0.56)}
    mix.summary_labels(say, "ENTER", per)
    text = "\n".join(say.lines)
    assert re.search(r"L1\s+\| carries\s+\| carries\s+\| -\s+\| carries", text) and re.search(r"L8\s+\| carries\s+\| weak", text) and "-> no mix" in text


# ═════════════════════════════════════════════════════════════════════════════════════════════ R16, the registered semantics, the edges
def test_r16_a_buy_day_close_without_an_in_session_frame_reads_unresolved_in_every_library():
    """F3 / R16: no in-session buy-day frame and a buy-day close under the prior low and one ADR20 under the fill (window +3..+4): the frozen
    held_through_intra reads the C close CERTAIN (no buy-day clock test for C); §4a reads every buy-day firing UNRESOLVED — the STOP C cells
    now read it so, like S3-T / S3-H and the exit daily rules on the SAME close. With the frame: MISS-EARLY. A flat frame after the close: not
    an event, the scan goes on."""
    sess0 = {0: lambda p: drop_at(p, 300, 380, 0.10), 1: lambda p: quiet(p * 1.11)}
    r, store, sight, M = unit_rec(exit_lo=3, exit_hi=4, sess=sess0, first=None, flat=None)
    smas, nomin = fz.smas_for(r.bars), mix.nomin_sessions(r, store, 24)
    for code in ("S3-C", "S4-C"):
        f, h = mix.stop_fire(r, code, smas, sight, store, 24, nomin)
        assert h["first_j"] == 0 and h["certain"] and not h["unresolved"], code             # the frozen reading (gate viii compares it)
        assert f.r16 == "unres" and f.bd_unres and mix.bucket(f, 3, 4) == UN, code
    for code in ("S3-T", "S3-H"):
        f, h = mix.stop_fire(r, code, smas, sight, store, 24, nomin)
        assert f.je == 0 and mix.bucket(f, 3, 4) == UN and not f.r16, code
    fx, _p, _c = fires_of(r, store, M)
    for code in ("M-3", "M-4", "M-7"):
        assert fx[code].je == 0 and mix.bucket(fx[code], 3, 4) == UN, code
    # the controls: frames-free placements read the same close EXPLAINS at s = 0, frames-on UNRESOLVED (R15: the chance line is the larger)
    t = mix.tag_se(r, M, store, sight)
    assert t["stop_r16"].get("S3-C") == "unres" and t["stop_real"]["S3-C"] == UN and t["exit_real"]["M-3"] == UN
    for dec, code in (("EXIT", "M-3"), ("STOP", "S3-C")):
        x = mix.summarize_se([t], dec)["rules"][code]
        assert x["a_ex_ff"] > x["a_ex_fa"] == 0.0 and x["a_ex"] == x["a_ex_ff"], (dec, code)
    # with an in-session buy-day frame: certain -> MISS-EARLY (the frozen reading and R16 agree)
    r1, s1, sg1, M1 = unit_rec(exit_lo=3, exit_hi=4, sess=sess0)
    f1, _h = mix.stop_fire(r1, "S3-C", fz.smas_for(r1.bars), sg1, s1, 24, mix.nomin_sessions(r1, s1, 24))
    assert not f1.r16 and mix.bucket(f1, 3, 4) == ME
    # a flat frame after the close: the buy-day close is not an event; the scan goes on (here: no later close under the level)
    r2, s2, sg2, M2 = unit_rec(exit_lo=3, exit_hi=4, sess=sess0, flat="16:30", first="10:40")
    f2, h2 = mix.stop_fire(r2, "S3-C", fz.smas_for(r2.bars), sg2, s2, 24, mix.nomin_sessions(r2, s2, 24))
    assert h2["first_j"] == 0 and f2.r16 == "skip" and f2.je != 0 and mix.bucket(f2, 3, 4) == NE
    fx2, _p, _c = fires_of(r2, s2, M2)
    assert fx2["M-3"].je != 0 and fx2["M-7"].je != 0


def test_m3_reads_the_10_day_and_m4_the_20_day():
    """A close between the 10-day and the 20-day average: M-3 fires, M-4 does not (m49)."""
    r, store, sight, M = unit_rec(exit_lo=6, exit_hi=6, sess={3: lambda p: path_minutes([(0, p), (200, p * 0.965), (389, p * 0.965)])}, rise=0.005)
    f, _p, _c = fires_of(r, store, M)
    sm = fz.smas_for(r.bars)
    k3 = r.bar_at(3)
    assert sm[10][k3] > r.bars.c[k3] >= sm[20][k3]
    assert f["M-3"].je == 3 and f["M-4"].je != 3


def test_m2_applies_the_buy_day_frame_rule_and_m6_skips_a_pre_flat_high():
    """M-2: a buy-day touch of the prior low after the armed bar but at or before flat_clock is not an event (the scan goes on to +2,
    MISS-EARLY); one between flat and first is UNRESOLVED; the frame-free firing (gate viii-b) keeps the buy day (m37). M-6: a +2R high
    before flat_clock is skipped, the next one after first_clock is the certain firing (m63)."""
    dip2 = lambda p: path_minutes([(0, p), (195, p), (200, p * 0.97), (205, p), (389, p)])      # noqa: E731
    for touch_m, want in ((100, "skip"), (140, "unres")):
        d0 = lambda p, t=touch_m: path_minutes([(0, p), (t - 5, p), (t, p * 0.99), (t + 5, p), (389, p)])     # noqa: E731
        r, store, sight, M = unit_rec(exit_lo=3, exit_hi=4, sess={0: d0, 2: dip2}, flat="11:30", first="12:10")
        f, prep, ctx = fires_of(r, store, M)
        assert ctx.armed_j == 0 and ctx.armed_close_m < touch_m - 5 and f["M-2"].raw_jb == 0, want
        if want == "skip":
            assert f["M-2"].je == 2 and not f["M-2"].bd_unres and mix.bucket(f["M-2"], 3, 4) == ME
        else:
            assert f["M-2"].je == 0 and f["M-2"].bd_unres and mix.bucket(f["M-2"], 3, 4) == UN
    two = lambda p: path_minutes([(0, 100.0), (20, 100.0), (30, 110.5), (40, 100.0), (190, 100.0), (200, 110.5), (210, 100.0), (389, 100.0)])  # noqa: E731
    r6, s6, _sg, M6 = unit_rec(exit_lo=3, exit_hi=3, sess={0: two}, fill=100.0, stop=95.0, rise=0.0, flat="10:30", first="11:00")
    f6 = fires_of(r6, s6, M6)[0]["M-6"]
    assert f6.je == 0 and f6.m >= 190 and not f6.bd_unres


def test_m10_fires_on_the_buy_day_and_the_hold_low_excludes_pre_fill_minutes():
    """M-10 arms at the fill: a big up day ON the buy day is its first firing (m64). The random-level control's lowest low reads the buy day
    from the fill minute on, never a pre-fill minute (m29)."""
    r, store, sight, M = unit_rec(exit_lo=3, exit_hi=3, sess={0: lambda p: path_minutes([(0, p), (389, p * 1.07)])}, rise=0.0, adr20=0.04)
    f = fires_of(r, store, M)[0]["M-10"]
    assert f.je == 0 and not f.bd_unres
    r2, s2, _sg, _M = unit_rec(exit_lo=2, exit_hi=3, fill_minute=100, sess={0: lambda p: path_minutes([(0, p), (50, p * 0.90), (80, p), (150, p * 0.99), (389, p)])})
    low = mix.hold_lowest_low(r2, s2)
    post = float(r2.mb.l[r2.mb.minute > 100].min())
    later = min(float(r2.bars.l[r2.bar_at(j)]) for j in range(1, 4))
    assert low == min(post, later) and low > float(r2.mb.l.min())


def test_the_exit_lo_contradicted_line_after_close_frames_the_booked_session_and_the_edges():
    r, store, sight, M = unit_rec(exit_lo=3, exit_hi=3)
    E3 = r.b.exit_lo
    F = mix.Fire
    assert mix.contradicted(r, F(sale_m=mix.CLOSE_M), sightings_from([(E3, "AAA", "closed", "16:30")]))     # an after-close frame (m50)
    assert not mix.contradicted(r, F(sale_m=mix.CLOSE_M), sightings_from([]))
    sg = sightings_from([(E3, "AAA", "in", "11:30")])                                                     # 11:30 = minute 120
    assert mix.contradicted(r, F(sale_m=119), sg) and not mix.contradicted(r, F(sale_m=120), sg)           # the edge (m16)
    assert not mix.contradicted(r, F(sale_m=mix.UNKNOWN_M), sg) and not mix.contradicted(r, F(), sg)       # a sale minute unknown
    # the count keys on the BOOKED session: a last-bar close on +3 books on +4 = exit_lo (sold at its open), a frame at 11:30 that day (m51)
    d4 = sessions(90)[74].isoformat()
    r2, s2, sg2, M2 = unit_rec(exit_lo=4, exit_hi=5, sess={3: lambda p: drop_at(p, 340, 385, 0.03)}, frames=[(d4, "in", "11:30")])
    t = mix.tag_se(r2, M2, s2, sg2)
    f1 = t["exit_fires"]["M-1"]
    assert f1.je == 3 and f1.jb == 4 and f1.sale_m == 0 and t["exit_real"]["M-1"] == EX and t["exit_contra"]["M-1"]


def test_tag_se_room_loser_and_the_random_level_union_of_k_levels():
    # control (a) has room from exit_lo_j = 1 (two placements: offsets 0 and 1) (m52)
    r, store, sight, M = unit_rec(exit_lo=1, exit_hi=2)
    t = mix.tag_se(r, M, store, sight)
    assert t["status"] == "" and t["room"] and t["stop_win_a"]["n"] == 2
    # a close exactly at the fill is not a loser (m34)
    r2, s2, sg2, M2 = unit_rec(exit_lo=2, exit_hi=3, rise=0.0)
    for bump, want in ((0.0, False), (1e-6, True)):
        r2.fill = float(r2.bars.c[r2.bar_at(3)]) + bump
        r2.stop_levels = fz.stop_levels_intra(r2)
        mix.add_s4(r2)
        assert mix.tag_se(r2, M2, s2, sg2)["loser"] is want, bump
    # the random-level UNION draws k independent levels (keys .../i, i = 1..k), never one level for all k rules (m62)
    def dip(depth):
        return lambda p: path_minutes([(0, p), (100, p * (1 - depth)), (389, p)])
    r3, s3, sg3, M3 = unit_rec(exit_lo=3, exit_hi=4, rise=0.0, sess={1: dip(0.02), 2: dip(0.03), 3: dip(0.05), 4: dip(0.07)})
    t3 = mix.tag_se(r3, M3, s3, sg3)
    rl = t3["rlevel"]
    assert not rl["no_room"] and 0.2 < rl["ex"] < 0.9
    path = mix.touch_path(r3, s3)
    for dec in ("STOP", "EXIT"):
        k = len(mix.LIB_CODES[dec])
        lk = mix.random_level_draws(r3, mix.RLEVEL_K_KEY, k)
        assert len(set(lk[0])) == k
        X = np.column_stack([mix.touch_buckets_vec(path, lk[:, i], 3, 4) == mix.CODE_OF[EX] for i in range(k)])
        assert rl[dec]["union"] == pytest.approx(X.any(axis=1).mean()) and rl[dec]["union"] > rl["ex"] + 0.05, dec


def test_the_boundaries_of_m5_m6_the_fixed_sessions_the_window_cap_and_the_buy_day_clock():
    # M-5: a peak EXACTLY at +1R is not a stall (fill 50, stop 47.5 -> 52.5); just under it is (m09)
    for top, stalls in ((52.5, False), (52.49, True)):
        r, store, sight, M = unit_rec(exit_lo=2, exit_hi=2, fill=50.0, stop=47.5, rise=0.0, sess={1: lambda p, t=top: path_minutes([(0, 50.0), (100, t), (389, 50.0)])})
        f = fires_of(r, store, M)[0]["M-5"]
        assert (f.je == 2) is stalls, top
    # M-6: a high EXACTLY at +2R fires (55.0); just under does not (m10)
    for top, je in ((55.0, 3), (54.99, None)):
        r, store, sight, M = unit_rec(exit_lo=5, exit_hi=5, fill=50.0, stop=47.5, rise=0.0, sess={3: lambda p, t=top: path_minutes([(0, 50.0), (120, t), (389, 50.0)])})
        assert fires_of(r, store, M)[0]["M-6"].je == je, top
    # M-9 / M-11: a session exactly at J_tail fires; one past it does not (m11)
    r, store, sight, M = unit_rec(exit_lo=3, exit_hi=3)
    ctx = fires_of(r, store, M)[2]
    assert mix._fixed_session(r, dataclasses.replace(ctx, J_tail=2), 2).je == 2 and mix._fixed_session(r, dataclasses.replace(ctx, J_tail=1), 2).je is None
    # a window of exactly 20 sessions is in the denominator; 21 is out (m12)
    for hi, want in ((22, ""), (23, "window_gt_20")):
        rr, *_x = unit_rec(n=130, e=70, exit_lo=3, exit_hi=hi)
        assert fz.exit_window_sessions(rr) == hi - 2 and mix.se_status(rr, {"J_tail": 60}) == want, hi
    # a buy-day firing exactly at first_clock is certain; exactly at the lower bound is not an event (m31)
    assert mix.day0_status(100, 35, 100) == "certain" and mix.day0_status(99, 35, 100) == "unres" and mix.day0_status(35, 35, 100) == "skip"
    assert mix.day0_status(36, 35, None) == "unres" and mix.day0_status(None, 35, 100) == "unres"
    # a 60-minute close on the record's LAST session's last bar books on that session's close (no next session) (l.573)
    r, store, sight, M = unit_rec(n=90, e=70, exit_lo=3, exit_hi=3)
    assert mix.h_booking(r, store, 19, 389) == (19, mix.CLOSE_M) and mix.h_booking(r, store, 18, 389) == (19, 0) and mix.h_booking(r, store, 18, 100) == (18, 101)


# ═════════════════════════════════════════════════════════════════════════════════════════════ guards
def write_doc(path, body_lines: list, tail_lines: list):
    path.write_text("\n".join(body_lines) + "\n<!-- FREEZE -->\n" + "\n".join(tail_lines) + "\n")


def test_module_scan_no_bare_helper_call_no_float_no_id_no_frozen_writer():
    # source-pin-ok: a lint over the module's own code — a bare reused-helper call (which would hash the intraday read's doc), a float() of an array, an id()-keyed cache and a frozen gate that writes files are properties of the source; the path that would expose each runs only on the one real --tag, so no behaviour test can show them absent beforehand
    src = open(MOD_PATH, encoding="utf-8").read()
    tree = ast.parse(src)
    need = {"doc_body_text": 1, "pin_under_marker": 2, "store_freeze_body": 2, "freeze_body_text": 3, "freeze_state": 2, "ledger_append": 3,
            "ledger_verify": 1, "dry_run_complete": 1, "pins": 1, "fit_events": 1, "fit_event_pins": 1, "fit_events_undisclosed": 2, "doc_line_of": 2,
            "chosen_lines": 1, "freeze_missing": 2}
    banned = {"stage_outputs", "any_stage_output", "reset_fits", "reset_artifacts", "print_pins", "run_check", "write_rows", "gate_ohlc", "gate_level_order",
              "gate_c_implies_h", "g8_run", "write_chosen", "read_chosen", "freeze_record_now", "freeze_records_agree", "run_fit_stage", "dry_run", "main"}
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "fz":
            name = node.func.attr
            if name in banned:
                bad.append(f"l.{node.lineno} fz.{name} (a frozen helper bound to the intraday read's files)")
            if name in need and len(node.args) + len(node.keywords) < need[name]:
                bad.append(f"l.{node.lineno} fz.{name} called without its path argument")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("float", "id"):
            bad.append(f"l.{node.lineno} bare {node.func.id}(")
        if isinstance(node, ast.Assign) or isinstance(node, ast.AugAssign):
            for tgt in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id in ("fz", "rev", "rp", "R", "cb", "H"):
                    bad.append(f"l.{node.lineno} assigns {tgt.value.id}.{tgt.attr} (a frozen module is never mutated)")
    for i, ln in enumerate(src.splitlines(), 1):
        if re.search(r"\bfz\.(P_DRY|LEDGER|OUT_DIR|STOPPED|DOC|FREEZE_BODIES|P_FIT|P_CHECK|P_PINS)\b", ln) and "intra-path-ok" not in ln:
            bad.append(f"l.{i} reads an intraday path constant outside the pinned list: {ln.strip()[:80]}")
        if re.search(r"(?<![\w.])id\(", ln) and not ln.lstrip().startswith("#"):
            bad.append(f"l.{i} id(")
    assert not bad, bad
    # the scan bites: a planted bare call and a planted float( are both caught
    planted = ast.parse("fz.ledger_append('tag', p)\nx = float('1')\nfz.dry_run_complete()\n")
    hits = [n for n in ast.walk(planted) if isinstance(n, ast.Call) and ((isinstance(n.func, ast.Attribute) and n.func.attr in need and len(n.args) < need[n.func.attr])
                                                                        or (isinstance(n.func, ast.Name) and n.func.id == "float"))]
    assert len(hits) == 3


@needs_lock_inputs
def test_guard_1_refuses_when_only_the_intraday_dry_run_exists_and_the_freeze_lock(tmp_path, monkeypatch):
    doc = tmp_path / "doc.md"
    body = ["# synthetic registration", "the fixed library"]
    write_doc(doc, body, [])
    for name, val in (("DOC", str(doc)), ("P_DRY", str(tmp_path / "mix_dry.txt")), ("P_TAG", str(tmp_path / "tag.txt")), ("LEDGER", str(tmp_path / "ledger.tsv")),
                      ("STOPPED", str(tmp_path / "STOPPED.txt")), ("FREEZE_BODIES", str(tmp_path / "fb")), ("OUT_DIR", str(tmp_path / "rule_mix")),
                      ("TAG_EVENTS", str(tmp_path / "ev"))):
        monkeypatch.setattr(mix, name, val)
    # the real registration carries exactly one line-anchored freeze marker; its body is what doc_body pins
    raw = open(os.path.join(REPO, "docs", "analysis", "cb_rule_mix_prereg_2026-10-25.md"), "rb").read()
    assert len(fz.marker_spans(raw)) == 1 and fz.doc_body_text(os.path.join(REPO, "docs", "analysis", "cb_rule_mix_prereg_2026-10-25.md")) is not None
    # the intraday dry run on disk ends DRY RUN COMPLETE — it must NOT satisfy this read's lock
    assert fz.dry_run_complete(os.path.join(mix.INTRA_DIR, "01_intra_dryrun.txt"))
    bad = mix.tag_lock()
    assert any("THIS read's dry run has not COMPLETED" in x for x in bad) and any("freeze lock" in x for x in bad) and any("pins not under the marker" in x for x in bad)
    dry_text = f"{mix.DRY_HEADER}: synthetic\n## RESULT: 3 claims, 3 OK, 0 MISMATCH; 0 notes\nDRY RUN COMPLETE: synthetic\n"
    (tmp_path / "mix_dry.txt").write_text("...\nDRY RUN COMPLETE: synthetic\n")              # the last line alone is not THIS read's dry run
    h = fz.store_freeze_body(str(doc), str(tmp_path / "fb"))
    write_doc(doc, body, [f"- {k}: {v}" for k, v in mix.mix_pins().items()])
    assert any("THIS read's dry run has not COMPLETED" in x for x in mix.tag_lock())
    (tmp_path / "mix_dry.txt").write_text(dry_text.replace("0 MISMATCH", "1 MISMATCH"))      # a dry run that STOPPED on a mismatch
    write_doc(doc, body, [f"- {k}: {v}" for k, v in mix.mix_pins().items()])
    assert any("THIS read's dry run has not COMPLETED" in x for x in mix.tag_lock())
    (tmp_path / "mix_dry.txt").write_text(dry_text)
    p = mix.mix_pins()
    assert p["doc_body"] == h and p["mix_module"] == mix.sha(MOD_PATH) and p["mix_tests"] == mix.sha(os.path.abspath(__file__)) and "intra_frozen_module" in p
    write_doc(doc, body, [f"- {k}: {v}" for k, v in p.items()])
    assert mix.tag_lock() == []
    # (F2a) the intraday read's dry run copied over THIS read's, the pins re-pasted: its sha is ALSO pinned (as intra_dryrun_printout), so the
    # value-anywhere test of the frozen freeze_missing passes — the lock must still refuse (its header is not this read's)
    shutil.copyfile(os.path.join(mix.INTRA_DIR, "01_intra_dryrun.txt"), tmp_path / "mix_dry.txt")
    p2 = mix.mix_pins()
    assert p2["mix_dryrun_printout"] == p2["intra_dryrun_printout"]
    write_doc(doc, body, [f"- {k}: {v}" for k, v in p2.items()])
    assert fz.freeze_missing(str(doc), p2) == [] and fz.dry_run_complete(str(tmp_path / "mix_dry.txt"))
    assert any("THIS read's dry run has not COMPLETED" in x for x in mix.tag_lock())
    (tmp_path / "mix_dry.txt").write_text(dry_text)
    write_doc(doc, body, [f"- {k}: {v}" for k, v in p.items()])
    assert mix.tag_lock() == []
    # (F2b) an input that turns ABSENT after the paste: `- mix_ledger: ABSENT` satisfies the value-anywhere test; the by-name test refuses
    monkeypatch.setitem(mix.CODE, "mix_tests", str(tmp_path / "gone.py"))
    p3 = mix.mix_pins()
    assert p3["mix_tests"] == "ABSENT" and "- mix_ledger: ABSENT" in doc.read_text() and fz.freeze_missing(str(doc), p3) == []
    assert any("checked by name" in x and "mix_tests" in x for x in mix.tag_lock())
    monkeypatch.setitem(mix.CODE, "mix_tests", os.path.abspath(__file__))
    # a value present only under ANOTHER pin's name: refused by name
    lines = [f"- {k}: {v}" for k, v in p.items()]
    lines = [ln if not ln.startswith("- intra_doc_body:") else f"- intra_doc_body: {'0' * 64}\n- note: {p['intra_doc_body']}" for ln in lines]
    write_doc(doc, body, lines)
    assert fz.freeze_missing(str(doc), p) == [] and any("checked by name" in x and "intra_doc_body" in x for x in mix.tag_lock())
    write_doc(doc, body, [f"- {k}: {v}" for k, v in p.items()])
    assert mix.tag_lock() == []
    # an edit above the marker after the freeze: the body pin breaks and the lock refuses
    write_doc(doc, body + ["a late edit"], [f"- {k}: {v}" for k, v in p.items()])
    assert any("freeze lock" in x or "pins not under" in x for x in mix.tag_lock())
    write_doc(doc, body, [f"- {k}: {v}" for k, v in p.items()])
    # a tag output on disk refuses; a STOPPED file refuses
    (tmp_path / "STOPPED.txt").write_text("STOPPED: x\n")
    assert any("already on disk" in x for x in mix.tag_lock())
    os.remove(tmp_path / "STOPPED.txt")
    # a changed ledger row refuses
    lp = tmp_path / "x.txt"
    lp.write_text("a\n")
    fz.ledger_append("tag", str(lp), str(tmp_path / "ledger.tsv"))
    lp.write_text("b\n")
    assert any("ledger" in x for x in mix.tag_lock())


# ═════════════════════════════════════════════════════════════════════════════════════════════ the synthetic world (end to end)
class SynthStore(fz.MinuteStore):
    """Minutes built from the world's daily bars on demand; `empty` pairs have none (empty at the source); `missing` pairs are in no tree's log
    (pending: no minutes either); after-hours prints on the early-close days. Every pair built counts as one file read (`reads`), so the dry run
    can be held to 0 reads and the tag shown to read."""

    def __init__(self, daily: dict, cal: list, empty: set, missing: set = frozenset()):
        super().__init__({}, {})
        self.daily, self.cal, self.empty, self.missing = daily, cal, set(empty), set(missing)
        self.pos = {d.isoformat(): i for i, d in enumerate(cal)}

    def state(self, d, tk, b=None):
        if (d, tk) in self.missing:
            return "missing"
        if (d, tk) in self.empty:
            return "empty/SYN"
        return "ok/SYN" if (tk in self.daily and d in self.pos) else "missing"

    def _build(self, d, tk):
        if (d, tk) in self.empty or (d, tk) in self.missing or tk not in self.daily or d not in self.pos:
            return None
        i = self.pos[d]
        o, h, l, c, _v = self.daily[tk]
        return minutes_from_daily(float(o[i]), float(h[i]), float(l[i]), float(c[i]), early=d in fz.EARLY_CLOSE, after_hours=d in fz.EARLY_CLOSE)

    def _get(self, d, tk):
        self.seal(d)
        if (d, tk) not in self.cache:
            self.cache[(d, tk)] = self._build(d, tk)
            self.reads["SYN"] += 1
        return self.cache[(d, tk)]

    def preload(self, pairs):
        from collections import Counter
        c = Counter()
        for p in pairs:
            d, tk = p[0], p[1]
            self._get(d, tk)
            c[self.state(d, tk).split("/")[0]] += 1
        return c

    def get(self, d, tk, b=None):
        return self._get(d, tk)


def make_D(daily: dict, cal: list, idx):
    """An export over the sessions `idx` of the world calendar (an era's own calendar: a slice, or a slice with a session dropped)."""
    idx = np.asarray(list(idx), dtype=np.int64)
    tks = sorted(daily)
    n = len(idx)
    o, h, l, c, v, ci = [], [], [], [], [], []
    for tk in tks:
        oo, hh, ll, cc, vv = daily[tk]
        o.append(oo[idx]); h.append(hh[idx]); l.append(ll[idx]); c.append(cc[idx]); v.append(vv[idx]); ci.append(np.arange(n, dtype=np.int32))
    start = np.arange(len(tks)) * n
    return R.Daily(tks, start, start + n, np.concatenate(ci), np.concatenate(o), np.concatenate(h), np.concatenate(l), np.concatenate(c), np.concatenate(v),
                   [cal[i] for i in idx], {t: k for k, t in enumerate(tks)}, 0, 0)


def build_world():
    """Two eras over one calendar (2019-01..2024-06): DA = a prefix to 2022-06-30, DB = a suffix from 2021-09-27 on its OWN calendar (one
    session after the overlap, 2022-08-03, missing from it: an era-B record's offsets differ from the panel calendar's; the overlap with DA must
    stay equal, the frozen unify_calendars asserts it). 60 tickers + QQQ / SPY + designed names:
    FSL (his FSLY shape), LW (a winner and a loser on one name), UP (a steady climb: no 60-minute close under the EMA, no prior-low touch —
    a dated 2020 trade the EXIT fit's guard bounds), GAP (a minute-less session that opens under the prior low); buys in every set the
    registration names, incl. 41 previous-draw-population undated 2021-22 windows (gate vii's base)."""
    cal = weekday_cal("2019-01-02", "2024-06-28")
    CI = {d.isoformat(): i for i, d in enumerate(cal)}
    n = len(cal)
    tks = [f"T{k:02d}" for k in range(60)] + ["QQQ", "SPY"]
    daily = {tk: daily_walk(n, 20.0 + 1.5 * k, 100 + k) for k, tk in enumerate(tks)}
    X = CI["2020-07-10"]
    o = np.array([50.0 * (1.004 ** i) for i in range(n)]); c = o * 1.001; h = c * 1.002; l = o * 0.998
    o[X], c[X], h[X], l[X] = c[X - 1], c[X - 1] * 0.90, c[X - 1] * 1.001, c[X - 1] * 0.895
    o[X + 1], c[X + 1], h[X + 1], l[X + 1] = c[X] * 0.99, c[X] * 0.97, c[X] * 0.995, c[X] * 0.965
    for i in range(X + 2, n):
        o[i], c[i], h[i], l[i] = c[X + 1], c[X + 1] * 1.001, c[X + 1] * 1.003, c[X + 1] * 0.998
    daily["FSL"] = (o, h, l, c, np.full(n, 1e6))
    W = CI["2020-08-20"]
    lo_ = np.array([30.0 * (1.006 ** min(i, W)) * (0.985 ** max(0, i - W)) for i in range(n)])
    daily["LW"] = (lo_ * 0.999, lo_ * 1.004, lo_ * 0.994, lo_, np.full(n, 1e6))
    # UP: flat, then a steady climb (0.8% a session) from 2020-03-02 to 2020-09-30, then flat
    u0, u1 = CI["2020-03-02"], CI["2020-09-30"]
    cu = np.array([40.0 * (1.008 ** (min(max(i, u0), u1) - u0)) for i in range(n)])
    ou = np.concatenate([[cu[0]], cu[:-1]]) * np.where((np.arange(n) > u0) & (np.arange(n) <= u1), 1.0005, 1.0)
    hu, lu = np.maximum(ou, cu) * 1.0002, np.minimum(ou, cu) * 0.9998
    daily["UP"] = (ou, hu, lu, cu, np.full(n, 1e6))
    # GAP: a slow climb with narrow ranges; on 2020-07-22 (+2 of its 2020-07-20 buy) it opens 5% under the prior low, and that session has no minutes
    G = CI["2020-07-22"]
    cg, og = np.zeros(n), np.zeros(n)
    for i in range(n):
        if i == 0:
            og[i] = cg[i] = 30.0
            continue
        og[i] = cg[i - 1] if i != G else min(og[i - 1], cg[i - 1]) * 0.999 * 0.95
        cg[i] = og[i] * 1.001
    daily["GAP"] = (og, np.maximum(og, cg) * 1.001, np.minimum(og, cg) * 0.999, cg, np.full(n, 1e6))
    iA, iB = CI["2022-06-30"] + 1, CI["2021-09-27"]
    drop_B = CI["2022-08-03"]
    buys, frames = [], []
    eid = [0]

    def add(sym, E, kind="und", flat="10:05", first="10:40", exit_off=(3, 5), flicker=False, decides=False, window=True, p_ctx="in", still=False, f_ctx="in"):
        eid[0] += 1
        i = CI[E]
        kw = dict(eid=eid[0], sym=sym, sym_a=sym, E=E, lo=E, hi=E, flicker=flicker)
        if kind == "bo":
            kw.update(setup="breakout", decides=True, pivot=float(daily[sym][3][i - 1]) * 1.01, adr20=0.05)
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
    add("T21", "2020-03-10", flicker=True, flat="10:10", first="10:10")
    add("T22", "2020-04-10", flicker=True, flat="10:20", first="10:50")
    for k, E in enumerate(["2020-02-05", "2020-03-04", "2020-04-06", "2020-05-06", "2020-06-08", "2020-07-08"]):
        add(f"T{23 + k:02d}", E, kind="bo", flat=clocks[k][0], first=clocks[k][1], exit_off=((2, 4), (4, 7), (1, 1), (3, 5), (6, 9), (2, 3))[k])
    for k, E in enumerate(["2020-02-12", "2020-05-12", "2020-09-09", "2020-11-24"]):
        add(f"T{29 + k:02d}", E, kind="bo", flat="09:10", first="09:45", p_ctx="pre", exit_off=((2, 5), (1, 2), (3, 3), (4, 8))[k])
    add("T33", "2020-11-18", exit_off=(5, 9))                                       # a hold across the early-close day 2020-11-27
    add("T34", "2020-06-22", exit_off=(2, 4))                                       # the buy day without minutes
    add("T35", "2020-08-05", exit_off=(4, 6))                                       # a missing minute day inside the hold
    fsl = add("FSL", "2020-06-29", flat="10:05", first="10:40", exit_off=(10, 11))  # X = 2020-07-10 = +9: one session before his window
    add("LW", "2020-08-03", exit_off=(2, 3))                                        # a winner ...
    add("LW", "2020-09-08", exit_off=(2, 3))                                        # ... and a loser on one name
    add("T16", "2020-10-05", exit_off=(0, 0))                                       # a buy-day sell: control (a) no_room
    add("T17", "2020-10-20", exit_off=(2, 4), window=False)                         # undated, no buy-day frame at all
    add("T18", "2020-03-23", exit_off=(3, 25))                                      # a window over 20 sessions
    up = add("UP", "2020-06-01", kind="bo", window=False, exit_off=(2, 3))          # the steady climb: M-1 never fires; the EXIT fit's guard bounds it
    gap = add("GAP", "2020-07-20", exit_off=(3, 4))                                 # a minute-less +2 that opens under the prior low
    for k, E in enumerate(["2021-02-01", "2021-03-15", "2021-05-03", "2021-08-02", "2021-11-01", "2022-02-01", "2022-03-01"]):
        add(f"T{36 + k:02d}", E, flat=clocks[k % 4][0], first=clocks[k % 4][1], exit_off=((2, 3), (1, 1), (4, 6), (3, 3), (6, 10), (2, 2), (5, 5))[k])
    eraB = add("T43", "2022-05-02", flat="10:05", first="10:40", exit_off=(5, 5))   # era B
    add("T44", "2022-01-31", flat="09:26", first="10:30", exit_off=(1, 2))
    # 32 more undated 2021-22 windows: the previous draw population's undated records become 41 (gate vii's base)
    sane = [("10:05", "10:40"), ("10:30", "11:20"), ("09:40", "09:50"), ("11:00", "12:30")]
    for k, E in enumerate([d.isoformat() for d in weekday_cal("2021-02-08", "2022-03-18")[::9][:32]]):
        add(f"T{k:02d}", E, flat=sane[k % 4][0], first=sane[k % 4][1], exit_off=((1, 2), (2, 3), (3, 3), (2, 5))[k % 4])
    add("T45", "2021-06-01", flicker=True, flat="10:05", first="10:40")
    add("T46", "2021-09-01", flicker=True, flat="10:20", first="10:50")
    for k, E in enumerate(["2021-02-08", "2021-06-14", "2022-01-10"]):
        add(f"T{47 + k:02d}", E, kind="bo", flat="10:05", first="10:40", exit_off=((2, 4), (1, 3), (3, 3))[k])
    for k, E in enumerate(["2021-04-05", "2021-10-04", "2022-03-14"]):
        add(f"T{50 + k:02d}", E, kind="bo", window=False, exit_off=((1, 2), (2, 2), (4, 5))[k])
    add("T53", "2022-04-20", kind="bo", window=False, exit_off=(3, 3))
    for k, E in enumerate(["2019-10-03", "2019-10-10", "2019-11-01", "2019-11-15"]):
        add(f"T{54 + k:02d}", E, flat="10:05", first="10:40", exit_off=((1, 1), (10, 14), (3, 3), (8, 8))[k])
    add("T58", "2019-10-01", flat="10:48", first="08:58", exit_off=(2, 2))
    add("T59", "2019-10-23", flat="09:24", first="09:25", exit_off=(2, 7))
    add("T00", "2019-10-21", kind="bo", window=False, exit_off=(5, 9))
    add("T01", "2019-11-07", kind="bo", flat="09:28", first="09:34", p_ctx="pre", exit_off=(3, 6))
    add("T02", "2019-10-22", flicker=True, flat="09:40", first="09:55")
    add("T03", "2019-11-11", flicker=True, flat="09:47", first="10:05")
    add("T04", "2023-06-01", kind="bo", window=False, exit_off=(6, 126))
    add("T05", "2023-06-06", kind="bo", window=False, exit_off=(3, 123))
    add("T06", "2023-12-01", kind="bo", window=False, still=True)
    add("T07", "2023-12-04", kind="bo", window=False, still=True)
    add("T08", "2023-05-18", flat="09:35", first="09:49", exit_off=(15, 135))
    add("T09", "2023-05-19", flat="09:42", first="09:51", exit_off=(2, 8))
    eraB2 = add("T19", "2022-08-01", exit_off=(3, 5))                               # era B: 2022-08-03 is not on its OWN calendar (+2 / +4, not +3 / +5)
    add("T10", "2022-11-15", kind="bo", window=False, exit_off=(2, 47))
    add("T11", "2022-11-17", exit_off=(0, 45), window=False)
    for k in range(3):
        add(f"T{12 + k:02d}", "2020-01-02", flat="09:08", first="09:33", exit_off=(0, 8))
    add("T15", "2020-01-23", flat="10:05", first="10:10", exit_off=(7, 7))
    add("T15", "2020-02-14", flicker=True, flat="10:05", first="10:40")             # inside the virgin T15's post-buy window: a guard-5 trade that RETURNS
    rev.index_calendar(buys, [d.isoformat() for d in cal])
    S = rev.build_sets(buys)
    I = fz.intra_sets(S)
    mis = {}
    E = fz.enter_sets(I, S, mis)
    rows = [dict(idx=i, frame_id=f"f{i}", vid="v", date=d, ctx=ctx, clock=clk, symbols=(s if shows else ""), blip_filled="") for i, (d, s, ctx, clk, shows) in enumerate(frames)]
    sn = pd.DataFrame(rows)
    C = dict(buys=buys, S=S, I=I, E=E, mis=mis, sn=sn, cal=[d.isoformat() for d in cal], CI=CI)
    empty = {("2020-06-22", "T34"), (cal[CI["2020-08-05"] + 2].isoformat(), "T35"), (cal[G].isoformat(), "GAP")}
    missing = {("2019-11-15", "T57"), (cal[CI["2023-05-19"] + 1].isoformat(), "T09")}       # in no tree's log: the dry run's pending pairs
    sight = rev.Sightings.build(sn)

    def make_M():
        DA_, DB_ = make_D(daily, cal, range(0, iA)), make_D(daily, cal, [i for i in range(iB, n) if i != drop_B])
        cal_u, map_b = H.unify_calendars(DA_.cal, DB_.cal)
        return dict(DA=DA_, DB=DB_, Ds={"A": DA_, "B": DB_}, cal_u=[d.isoformat() for d in cal_u], map_b=map_b, px=None, guards={"A": {}, "B": {}}, done={}, files={},
                    store=SynthStore(daily, cal, empty, missing), sight=sight, last_seen=fz.last_seen_map(sight))
    return dict(C=C, make_M=make_M, cal=cal, CI=CI, daily=daily, fsl=fsl, eraB=eraB, eraB2=eraB2, up=up, gap=gap, missing=missing, byeid={b.eid: b for b in buys}, X=X)


@pytest.fixture(scope="module")
def world():
    return build_world()


def test_the_synthetic_world_holds_the_real_shapes(world):
    """The shapes the gates and the end-to-end run rely on are really in the world (so the e2e assertions are not vacuous)."""
    C, cal, CI = world["C"], world["cal"], world["CI"]
    M = world["make_M"]()
    assert len(C["S"]["ent_chk_und"]) == 41                                           # gate (vii)'s base, the frozen gate's own count
    eb = world["eraB2"]
    rB = fz.make_irec(eb, M, "B", None, None, want_minutes=False)
    assert (rB.exit_lo_j, rB.exit_hi_j) == (2, 4) and (CI[eb.exit_lo] - CI[eb.E], CI[eb.exit_hi] - CI[eb.E]) == (3, 5)   # its own calendar lacks 2022-08-03
    assert eb.eid in {b.eid for b in C["I"]["virgin_und"]} and fz.make_irec(world["eraB"], M, "B", None, None, want_minutes=False) is not None
    assert world["up"].eid in {b.eid for b in C["I"]["fit_dated"]} and world["gap"].eid in {b.eid for b in C["I"]["fit_und"]}
    assert any(b.eid == world["up"].eid for b in fz.collision_summary(C, M["last_seen"])["exit"]["kept"])


def intraday_tsvs(world, out_dir) -> dict:
    """The six intraday TSVs the frozen stages would have written on this world, by the frozen functions in the frozen stages' orders (the fit
    under the fit chain: L8 where feasible; the guard-5 exclusions applied; the EXIT fit under a BarGuard whose forbid holds one session of UP's
    tail, so its row is bounded there: cut_why 'guard', J_tail < exit_hi + 20), plus the known answers their printouts would carry."""
    C, M = world["C"], world["make_M"]()
    S, I, E, mis = C["S"], C["I"], C["E"], C["mis"]
    store, sight, g = M["store"], M["sight"], fz.BarGuard(None)
    cs = fz.collision_summary(C, M["last_seen"])
    known = {}
    # ENTER fit
    recs, _d = fz.recs_for(cs["enter"]["kept"], M, store, g, min_bars=fz.REC_MIN_BARS_ENTER)
    rng = fz.rng_for(fz.RANDOM_KEY)
    rows, scored = [], {}
    for r in sorted(recs, key=lambda x: (x.b.E, x.b.eid)):
        if r.mb is None:
            rows.append(dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, minutes=r.minutes_state, scorable=False))
            continue
        res = fz.enter_score_trade(r, rng)
        scored[r.b.eid] = res
        rows.append(fz.enter_row(r, res))
    known["enter_fit"] = ({lv: (sum(1 for x in scored.values() if x[lv]["feasible"]) / len(scored)) for lv in fz.ALL_LEVELS}, len(scored))
    kept_b = {b.eid for b in cs["enter_beside"]["kept"]}
    for lab, key in (("flickers 2020 (in-session windows after §2c)", "fit_fl"), ("pre-market-flat windows, dated 2020", "pre_dated_fit"),
                     ("pre-market-flat windows, undated 2020", "pre_und_fit")):
        rr, _d = fz.recs_for([b for b in E[key] if b.eid in kept_b], M, store, g, min_bars=fz.REC_MIN_BARS_ENTER)
        rr = [r for r in rr if r.mb is not None and mix.clocks_ok(r.b)]
        sc = {r.b.eid: fz.enter_score_trade(r, rng) for r in sorted(rr, key=lambda x: (x.b.E, x.b.eid))}
        rows += [dict(fz.enter_row(r, sc[r.b.eid]), beside=lab) for r in rr]
    pd.DataFrame(rows).to_csv(out_dir / "enter_fit_trades.tsv", sep="\t", index=False)
    # ENTER check
    draw_pop = sorted(S["ent_chk_dated"] + S["ent_chk_und"], key=lambda b: (b.E, b.eid))
    recs_e, _d = fz.recs_for(draw_pop, M, store, g, min_bars=fz.REC_MIN_BARS_ENTER)
    rng = fz.rng_for(fz.RANDOM_KEY)
    rows, scored = [], {}
    for r in sorted(recs_e, key=lambda x: (x.b.E, x.b.eid)):
        if r.mb is None:
            rows.append(dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, minutes=r.minutes_state, scorable=False))
            continue
        res = fz.enter_score_trade(r, rng)
        scored[r.b.eid] = res
        rows.append(dict(fz.enter_row(r, res), sane=fz.clock_sane(r.b, mis)))
    dec = {b.eid for b in E["chk22_und"]}
    dd = [v for k, v in scored.items() if k in dec]
    known["enter_check"] = ({lv: sum(1 for x in dd if x[lv]["feasible"]) / len(dd) for lv in ("L7", "L8", "L9", "L1")}, len(dd))
    prev = {k: v for k, v in scored.items() if k in {b.eid for b in S["ent_chk_und"]}}
    assert len(prev) == 41
    ctl = fz.enter_summary(prev)["control"]
    known["vii"] = (ctl["feasible_share"], ctl["hit_share"])
    rr_fl, _d = fz.recs_for(E["chk22_fl"], M, store, g, min_bars=fz.REC_MIN_BARS_ENTER)
    sc_fl = {r.b.eid: fz.enter_score_trade(r, rng) for r in sorted(rr_fl, key=lambda x: (x.b.E, x.b.eid)) if r.mb is not None}
    rows += [dict(fz.enter_row(r, sc_fl[r.b.eid]), beside="flickers") for r in rr_fl if r.b.eid in sc_fl]
    rr_v, _d = fz.recs_for(E["virgin"], M, store, g, min_bars=fz.REC_MIN_BARS_ENTER)
    sc_v = {r.b.eid: fz.enter_score_trade(r, rng) for r in sorted(rr_v, key=lambda x: (x.b.flicker, x.b.E, x.b.eid)) if r.mb is not None}
    rows += [dict(fz.enter_row(r, sc_v[r.b.eid]), beside="virgin") for r in rr_v if r.b.eid in sc_v]
    pd.DataFrame(rows).to_csv(out_dir / "check_enter_trades.tsv", sep="\t", index=False)
    known["prev_und"] = {b.eid for b in S["ent_chk_und"]}
    # STOP fit (the fit chain) / check (registered)
    recs, _d = fz.recs_for(cs["stop"]["kept"], M, store, g)
    cc = fz.apply_chain(recs, "L8", None, mis)
    known["level_rows"] = cc.get("fill_level:L8", 0)
    pd.DataFrame(fz.stop_rows(recs, sight, store)).to_csv(out_dir / "stop_fit_trades.tsv", sep="\t", index=False)
    allr = []
    for k in ("virgin_und", "virgin_dated", "chk22_und", "chk22_dated"):
        allr += fz.recs_for(I[k], M, store, g)[0]
    fz.apply_chain(allr, None, None, mis)
    pd.DataFrame(fz.stop_rows(allr, sight, store)).to_csv(out_dir / "check_stop_trades.tsv", sep="\t", index=False)
    # EXIT fit (the fit chain, under the fit's guard: one forbidden session inside UP's tail) / check (registered)
    up, cal, CI = world["up"], world["cal"], world["CI"]
    up_hi = CI[up.exit_hi] - CI[up.E]
    known["up_forbid"] = (up.sym, cal[CI[up.E] + up_hi + 6].isoformat())
    fit_exit = [b for b in cs["exit"]["kept"]]
    g_fit = fz.BarGuard({b.eid for b in fit_exit}, frozenset([known["up_forbid"]]))
    for name, buys, level, guard in (("exit_fit", fit_exit, "L8", g_fit), ("check_exit", [b for b in I["chk22_dated"] if b.has_exit], None, g)):
        recs, _d = fz.recs_for(buys, M, store, guard)
        fz.apply_chain(recs, level, None, mis)
        preps = {r.b.eid: fz.exit_prepare(r, M, store) for r in recs}
        rates = fz.hit_rates_for(recs, M, store, preps)
        pd.DataFrame(fz.exit_rows(recs, preps, rates)).to_csv(out_dir / f"{name}_trades.tsv", sep="\t", index=False)
        tl = fz.trivial_and_list_hits(recs, preps, None)
        known[name] = ({v: rates[v][0] for v in fz.EXIT_VARIANTS}, rates["E1"][2])
        known[name + "_trivial"] = (tl["first_red_close"], tl["close_of_session_3"], tl["n"])
    und, _d = fz.recs_for(I["chk22_und"], M, store, g)
    fz.apply_chain(und, None, None, mis)
    und = [r for r in und if r.exit_hi_j is not None]
    tl = fz.trivial_and_list_hits(und, {r.b.eid: fz.exit_prepare(r, M, store) for r in und}, None)
    known["check_und_trivial"] = (tl["first_red_close"], tl["close_of_session_3"], tl["n"])
    return known


TSV_NAMES = ("enter_fit_trades", "check_enter_trades", "stop_fit_trades", "check_stop_trades", "exit_fit_trades", "check_exit_trades")


@pytest.fixture(scope="module")
def tsv_cache(world, tmp_path_factory):
    """The intraday TSVs built ONCE per module (the frozen functions are deterministic); each end-to-end env copies them."""
    d = tmp_path_factory.mktemp("intraday_cache")
    known = intraday_tsvs(world, d)
    return d, known


def restore_tsvs(tsv_cache, tsv_dir) -> None:
    for k in TSV_NAMES:
        shutil.copyfile(tsv_cache[0] / f"{k}.tsv", tsv_dir / f"{k}.tsv")


def test_the_exit_fit_tsv_holds_a_guard_bounded_tail_cut_row(tsv_cache, world):
    """F1's real shape: the fit's guard bounded UP's walk inside exit_hi + 20, so its row books `cut_at_guard@J` on every variant (the frozen
    `tail_kind_for` with why = 'guard')."""
    t = pd.read_csv(tsv_cache[0] / "exit_fit_trades.tsv", sep="\t", dtype=str, keep_default_na=False)
    row = t[t["eid"] == str(world["up"].eid)].iloc[0]
    assert row["cut_why"] == "guard" and int(float(row["J_tail"])) == int(float(row["exit_hi_j"])) + 5
    assert all(row[f"{v}_legs"].endswith(f"cut_at_guard@{int(float(row['J_tail']))}") for v in fz.EXIT_VARIANTS)


class QuietClaims(mix.MixClaims):
    """Records every claim, asserts none: the synthetic world cannot reproduce the real registration's counts — under test here are the dry
    run's MECHANICS (the files, the data gate, the pins), never its numbers."""

    def __call__(self, anchor, label, doc, mine, note=False):
        self.n += 1
        self.say(f"  [quiet] {label} | doc {doc} | mine {mine}")
        return True


class QuietPrev:
    n, bad = 0, []


G8_STUB = '''import sys
args = sys.argv[1:]
trades = args[args.index("--trades") + 1]
with open(trades) as fh:
    head = fh.readline()
    n = sum(1 for _ in fh)
if not head.startswith("cell\\tattempt\\tticker\\tentry_date\\texit_j\\trealized_r"):
    sys.exit(5)
print(f"synthetic trade_impact: {n} trades")
print("trades entered after the cutoff 2024-12-31 (their bars are sealed): 0")
print("trades whose hold runs past the last bar kept (truncated or no bars): 0")
'''


def e2e_env(world, tsv_cache, tmp_path, monkeypatch) -> dict:
    C = world["C"]
    tsv_dir = tmp_path / "intraday"
    tsv_dir.mkdir()
    restore_tsvs(tsv_cache, tsv_dir)
    known = tsv_cache[1]
    doc = tmp_path / "doc.md"
    body = ["# synthetic rule-mix registration", "the fixed library"]
    write_doc(doc, body, [])
    fl = tmp_path / "fetch_list.psv"
    fl.write_text("".join(f"{b.sym}|{b.E}|fit2020\n" for b in C["E"]["fit_und"][:4]) + "T54|2019-10-03|virgin\nT57|2019-11-15|virgin\n")
    paths = dict(DOC=str(doc), P_DRY=str(tmp_path / "mix_dry.txt"), P_TAG=str(tmp_path / "mix_tag.txt"), P_PINS=str(tmp_path / "mix_pins.txt"),
                 LEDGER=str(tmp_path / "mix_ledger.tsv"), STOPPED=str(tmp_path / "mix.STOPPED.txt"), FREEZE_BODIES=str(tmp_path / "fb"),
                 DRY_SIDE=str(tmp_path / "dryrun_side"), TAG_EVENTS=str(tmp_path / "tag_events"), FROZEN_DIR=str(tmp_path / "frozen"),
                 OUT_DIR=str(tmp_path / "rule_mix"), FETCH_LIST=str(fl))
    os.makedirs(paths["FROZEN_DIR"])
    for k, v in paths.items():
        monkeypatch.setattr(mix, k, v)
    monkeypatch.setattr(mix, "TSV", {k: str(tsv_dir / f"{k}.tsv") for k in mix.TSV})
    monkeypatch.setattr(mix, "load_core", lambda say: C)
    reads = []

    def fresh_M(say, C_, a, b):                       # every stage a FRESH market (new exports, bars, store)
        gc.collect()
        m = world["make_M"]()
        reads.append(m["store"].reads)
        say("- synthetic markets rebuilt (a fresh market for this stage)")
        return m
    monkeypatch.setattr(mix, "load_markets", fresh_M)
    monkeypatch.setattr(mix, "prev_population_claims", lambda say, C_: QuietPrev())
    monkeypatch.setattr(mix, "MixClaims", QuietClaims)
    monkeypatch.setattr(mix, "check_mix_inputs", lambda say: say("- inputs skipped (synthetic)"))
    monkeypatch.setattr(mix, "assert_populations", lambda say, C_: say("- populations skipped (synthetic)"))
    # G8 runs as written, against a stub audit script that checks the trade file's shape and prints parseable 0 / 0 lines
    stub = tmp_path / "trade_impact_stub.py"
    stub.write_text(G8_STUB)
    monkeypatch.setattr(mix, "TRADE_IMPACT", str(stub))
    monkeypatch.setattr(mix, "G8_FILES", {f"{k}_{e}": str(tmp_path / f"{k}_{e}") for k in ("flags", "export") for e in ("A", "B")})
    # gate (vii) runs as written (the frozen gate, its 41-record count), its known answer = the synthetic stream's shares
    monkeypatch.setattr(fz, "RANDOM_CONTROL_KNOWN", known["vii"])
    seen_vii = []
    real_vii = mix.gate_vii

    def vii(say, scored_all, prev):
        seen_vii.append((set(scored_all), set(prev)))
        return real_vii(say, scored_all, prev)
    monkeypatch.setattr(mix, "gate_vii", vii)
    monkeypatch.setattr(mix, "KNOWN_ENTER_STANDALONE", {"fit": known["enter_fit"], "check": known["enter_check"]})
    monkeypatch.setattr(mix, "KNOWN_EXIT_RATES", {"fit": known["exit_fit"], "check": known["check_exit"]})
    monkeypatch.setattr(mix, "KNOWN_TRIVIAL", {"fit": known["exit_fit_trivial"], "check": known["check_exit_trivial"], "check_und": known["check_und_trivial"]})
    fsl, cal, X = world["fsl"], world["cal"], world["X"]
    monkeypatch.setattr(mix, "FSLY", dict(eid=fsl.eid, sym="FSL", E=fsl.E, exit_lo=fsl.exit_lo, exit_hi=fsl.exit_hi, m1_by=cal[X].isoformat(), touch_by=cal[X + 1].isoformat()))
    return dict(doc=doc, body=body, known=known, reads=reads, seen_vii=seen_vii, tsv_dir=tsv_dir, paths=paths)


def paste_pins(env) -> dict:
    p = mix.mix_pins()
    write_doc(env["doc"], env["body"], [f"- {k}: {v}" for k, v in p.items()])
    return p


@needs_lock_inputs
def test_end_to_end_dry_run_then_the_tag_on_the_synthetic_world(world, tsv_cache, tmp_path, monkeypatch):
    env = e2e_env(world, tsv_cache, tmp_path, monkeypatch)
    P = env["paths"]
    assert env["known"]["level_rows"] >= 1                                              # the fit chain's level:L8 rows exist in the TSV
    # the tag refuses before the dry run
    assert mix.main(["--tag"]) == 2
    # --dry-run: completes, writes the side files, never opens a minute file
    assert mix.main(["--dry-run"]) == 0
    dry = open(P["P_DRY"]).read()
    assert dry.rstrip().splitlines()[-1].startswith("DRY RUN COMPLETE") and "(0 reads)" in dry and sum(env["reads"][0].values()) == 0
    assert dry.splitlines()[0].startswith(mix.DRY_HEADER) and mix.mix_dry_run_complete(P["P_DRY"])
    assert os.path.exists(os.path.join(P["DRY_SIDE"], "pending.psv")) and os.path.exists(os.path.join(P["DRY_SIDE"], "empty_pairs.psv"))
    pend = open(os.path.join(P["DRY_SIDE"], "pending.psv")).read()
    for d_, tk in world["missing"]:
        assert f"{tk}|{d_}|" in pend, (tk, d_)
    assert re.search(r"pending pairs \(in no tree's log\): [1-9]", dry) and "GAP|2020-07-22" in open(os.path.join(P["DRY_SIDE"], "empty_pairs.psv")).read()
    assert "THE LIBRARIES" in dry and "R16" in dry and "returning (STOP)" in dry and "T15 2020-02-14" in dry
    assert "composition line" in dry and "coverage STOP/EXIT" in dry and "- mix_dryrun_printout:" not in dry and "- mix_ledger:" not in dry
    # a second dry run on the same inputs prints byte for byte the same (no self-hash in it)
    dry1 = open(P["P_DRY"], "rb").read()
    os.remove(P["P_DRY"])
    assert mix.main(["--dry-run"]) == 0 and open(P["P_DRY"], "rb").read() == dry1
    # --print-pins: the module and the tests pinned, this read's ledger ABSENT
    assert mix.main(["--print-pins"]) == 0
    pins = open(P["P_PINS"]).read()
    assert f"- mix_module: {mix.sha(MOD_PATH)}" in pins and f"- mix_tests: {mix.sha(os.path.abspath(__file__))}" in pins and "- mix_ledger: ABSENT" in pins
    assert f"- mix_dryrun_printout: {mix.sha(P['P_DRY'])}" in pins
    # the tag refuses until every pin sits under the marker
    assert mix.main(["--tag"]) == 2
    paste_pins(env)
    assert mix.tag_lock() == []
    rc = mix.main(["--tag"])
    tag = open(P["P_TAG"]).read() if os.path.exists(P["P_TAG"]) else open(P["STOPPED"]).read()
    assert rc == 0, tag[-4000:]
    for s in ("gate (i) enter", "gate (i) clock arm enter", "gate (i) stop_exit", "gate (ii) enter", "gate (iii) stop_exit", "gate (viii) ENTER enter_fit_trades",
              "gate (viii) ENTER check_enter_trades", "gate (viii) STOP stop_fit_trades", "gate (viii) STOP check_stop_trades", "gate (viii-a) EXIT exit_fit_trades",
              "gate (viii-b) EXIT exit_fit_trades", "gate (viii-c) EXIT exit_fit_trades", "gate (viii-c) EXIT 2021-22 undated", "gate (ix) FSLY", "gate (x) identity",
              "ALL GATES PASSED", "decision ENTER — block 2020", "decision STOP — block 2020", "decision EXIT — block 2021-22", "decision EXIT — block untouched",
              "UNION", "discretion", "earliest-firing order", "no_room trades", "window_gt_20", "still_held", "non-losers (beside)",
              "the summary labels", "TAG COMPLETE", "R16 beside:", "NEW cells (§2b", "NEW cell (§2b), beside: on the 2020 dated (exit_fit_trades.tsv) rows"):
        assert s in tag, s
    # gate (vii) ran as written on the 41 previous undated records; G8 ran through the stub
    assert re.search(r"gate \(vii\) the random-price control's known answer on the previous 41 undated 2021-22 windows: .* -> reproduced", tag)
    assert env["seen_vii"] and env["seen_vii"][0][1] == env["known"]["prev_und"]
    assert "## G8 — mix_tag" in tag and "era A: entered after the cutoff 0, holds past the last bar 0" in tag and "era B: entered after the cutoff 0" in tag
    assert re.search(r"gate \(viii\) STOP stop_fit_trades: \d+ rows x 18 cells .*: 0 differences", tag)
    assert re.search(r"gate \(x\) identity: \d+ STOP / EXIT .*, \d+ ENTER .* and [1-9]\d* per-level shifted placements .* 0 differences", tag)
    assert re.search(r"gate \(i\) clock arm enter: buy-day sessions with a bar at minute 0 \(09:30\): (\d+) of \1 = 100.0%", tag)
    # F1: the fit's guard-bounded row was re-walked under ITS cut reason (cut_at_guard) and matched
    m_ = re.search(r"gate \(viii-a\) EXIT exit_fit_trades: .* row differences 0; rows whose J_tail the fit bounded (\d+)", tag)
    assert m_ and int(m_.group(1)) >= 1
    # the returning guard-5 windows are scored outside the replayed stream (R12) and named
    assert "outside it with `mix|rprice1|{eid}` draws" in tag
    # the per-trade files, the ledger, the module copy
    out = P["OUT_DIR"]
    for f in ("tags_enter.tsv", "tags_stop.tsv", "tags_exit.tsv", "control_windows.tsv.gz"):
        assert os.path.exists(os.path.join(out, f)), f
    te = pd.read_csv(os.path.join(out, "tags_exit.tsv"), sep="\t")
    assert {"M-1_bucket", "M-2s_booked_j", "tag", "earliest_tag", "ctl_a_union", "rlevel_ex"} <= set(te.columns)
    assert set(te["status"]) >= {"scorable", "still_held", "window_gt_20"} and te["era"].eq("B").any()
    assert set(te.loc[te["status"] == "scorable", "M-1_bucket"]) <= set(mix.BUCKETS)
    ts = pd.read_csv(os.path.join(out, "tags_stop.tsv"), sep="\t")
    assert ts["loser"].eq(True).any() and ts["loser"].eq(False).any() and ts["room"].eq(False).any()
    lw = ts[ts["sym"] == "LW"]
    assert len(lw) == 2 and set(lw["loser"]) == {True, False}                         # a winner and a loser on one name
    # the STOP table counts his LOSING exits only (the winners with room are out of its n)
    for blk in mix.BLOCKS:
        m2 = re.search(rf"decision STOP — block {re.escape(blk)} \(n scorable (\d+);", tag)
        sub = ts[(ts["block"] == blk) & (ts["status"] == "scorable") & ts["room"].eq(True)]
        assert m2 and int(m2.group(1)) == int(sub["loser"].eq(True).sum()), blk
        if blk == "2020":
            assert int(sub["loser"].eq(True).sum()) < len(sub)                          # a winner with room exists: the losers-only base is visible
    # F7: the era-B record's offsets are its OWN calendar's (2022-08-03 is not on it): +2 / +4, where the panel calendar reads +3 / +5
    rB = te[te["eid"] == world["eraB2"].eid].iloc[0]
    assert rB["era"] == "B" and (rB["exit_lo_j"], rB["exit_hi_j"]) == (2, 4) and rB["status"] == "scorable"
    assert ts[ts["eid"] == world["eraB2"].eid].iloc[0]["status"] == "scorable" and te[te["eid"] == world["eraB"].eid].iloc[0]["era"] == "B"
    # the real shapes: GAP's minute-less +2 opens under the prior low (M-2 at minute 0); UP's 60-minute close never falls under the EMA
    rg = te[te["eid"] == world["gap"].eid].iloc[0]
    assert rg["M-2_first_j"] == 2 and rg["M-2_first_minute"] == 0 and rg["M-2_bucket"] == ME
    ru = te[te["eid"] == world["up"].eid].iloc[0]
    assert ru["M-1_bucket"] == NE and pd.isna(ru["M-1_first_j"]) and pd.isna(ru["M-2s_first_j"]) and pd.isna(ru["M-2_first_j"])
    cw = pd.read_csv(os.path.join(out, "control_windows.tsv.gz"), sep="\t")
    assert set(cw["range"]) >= {"a", "b", "a_ff", "b_ff", "shared"}
    assert fz.ledger_verify(P["LEDGER"]) == [] and len(open(P["LEDGER"]).read().splitlines()) == 1 + 5
    assert os.path.exists(os.path.join(P["FROZEN_DIR"], f"01_mix_frozen_{mix.sha(MOD_PATH)[:12]}.py"))
    assert len(env["reads"]) == 3 and sum(env["reads"][-1].values()) > 0                # a fresh market per stage; the tag reads minutes
    # it runs ONCE: a second tag, a dry run, a reset are all refused
    assert mix.main(["--tag"]) == 2 and mix.main(["--dry-run"]) == 2 and mix.main(["--reset", "why"]) == 2


@needs_lock_inputs
def test_a_planted_tsv_row_stops_gate_viii_then_the_reset_archives_and_the_lock_waits_for_the_disclosure(world, tsv_cache, tmp_path, monkeypatch):
    env = e2e_env(world, tsv_cache, tmp_path, monkeypatch)
    P = env["paths"]
    # plant: one stop row's first_j shifted by a session
    p_ = env["tsv_dir"] / "stop_fit_trades.tsv"
    t = pd.read_csv(p_, sep="\t", dtype=str, keep_default_na=False)
    idx = next(i for i, v in enumerate(t["S3_T_first_j"]) if v not in ("", "nan"))
    t.loc[idx, "S3_T_first_j"] = str(int(float(t.loc[idx, "S3_T_first_j"])) + 1)
    t.to_csv(p_, sep="\t", index=False)
    assert mix.main(["--dry-run"]) == 0
    paste_pins(env)
    assert mix.main(["--tag"]) == 3
    stopped = open(P["STOPPED"]).read()
    assert "STOPPED: gate (viii) STOP stop_fit_trades: 1 cells differ" in stopped and "ALL GATES PASSED" not in stopped
    assert os.path.exists(os.path.join(P["OUT_DIR"], "gate_viii_stop_stop_fit_trades.tsv"))
    assert mix.main(["--tag"]) == 2                                                     # the STOPPED file refuses
    # the reset: everything COPIED then removed, never deleted; the lock then waits for the disclosure and a fresh dry run
    say = rp.Say()
    assert mix.reset_tag(say, "") == 2
    assert mix.main(["--reset", "gate viii: a planted row (test)"]) == 0
    evs = fz.fit_events(P["TAG_EVENTS"])
    assert len(evs) == 1
    ev = evs[0]["event"]
    man = pd.read_csv(os.path.join(P["TAG_EVENTS"], ev, "MANIFEST.tsv"), sep="\t")
    assert len(man) >= 3 and not os.path.exists(P["STOPPED"]) and not os.path.exists(P["P_DRY"])
    for row in man.to_dict("records"):
        assert os.path.exists(os.path.join(P["TAG_EVENTS"], ev, row["archived"])) and not os.path.exists(row["original"])
    bad = mix.tag_lock()
    assert any("dry run has not COMPLETED" in x for x in bad) and any("not disclosed" in x for x in bad)
    # the fix (the true row back), the dry run, the pins incl. the event: the lock opens
    restore_tsvs(tsv_cache, env["tsv_dir"])
    assert mix.main(["--dry-run"]) == 0
    p = paste_pins(env)
    assert f"fit_event_{ev}" in p
    assert mix.tag_lock() == []


# ═════════════════════════════════════════════════════════════════════════════════════════════ every gate STOPS on a planted failure (F5)
def _shift_cell(env, tsv: str, col: str, pred=lambda row: True, delta: int = 1) -> None:
    p_ = env["tsv_dir"] / f"{tsv}.tsv"
    t = pd.read_csv(p_, sep="\t", dtype=str, keep_default_na=False)
    idx = next(i for i, row in enumerate(t.to_dict("records")) if row[col] not in ("", "nan", "None") and pred(row))
    t.loc[idx, col] = str(int(float(t.loc[idx, col])) + delta)
    t.to_csv(p_, sep="\t", index=False)


def _flip_cell(env, tsv: str, col: str) -> None:
    p_ = env["tsv_dir"] / f"{tsv}.tsv"
    t = pd.read_csv(p_, sep="\t", dtype=str, keep_default_na=False)
    t.loc[0, col] = "False" if t.loc[0, col] == "True" else "True"
    t.to_csv(p_, sep="\t", index=False)


def _plant_wrong_day(monkeypatch, env, world):
    orig = SynthStore._build

    def build(self, d, tk):                                                  # the NEXT session's minutes under this session's date
        i = self.pos.get(d)
        return orig(self, self.cal[i + 1].isoformat(), tk) if (i is not None and i + 1 < len(self.cal)) else None
    monkeypatch.setattr(SynthStore, "_build", build)


def _plant_clock_plus_one(monkeypatch, env, world):
    orig = SynthStore._build

    def build(self, d, tk):                                                  # every stamp one minute late; the 15:59 bar falls off 0..389
        mb = orig(self, d, tk)
        if mb is None:
            return None
        keep = mb.minute < 389
        return cb.minute_bars_from_lists(list(mb.minute[keep] + 1), list(mb.o[keep]), list(mb.h[keep]), list(mb.l[keep]), list(mb.c[keep]), list(mb.v[keep]))
    monkeypatch.setattr(SynthStore, "_build", build)


def _plant_builder(monkeypatch, env, world):
    orig = mix.enter_gate_rows

    def rows(ER, scored):
        out = orig(ER, scored)
        k = next(i for i, rw in enumerate(out) if fz._isnum(rw.get("H60_0_high")))
        out[k] = dict(out[k], H60_0_high=fz.fnum(out[k]["H60_0_high"]) * 1.01)
        return out
    monkeypatch.setattr(mix, "enter_gate_rows", rows)


def _plant_last_bar(monkeypatch, env, world):
    orig = SynthStore.h60

    def h60(self, d, tk, b=None):                                            # the last 60-minute bar closes far above any level
        bars = orig(self, d, tk, b)
        if not bars:
            return bars
        out = list(bars)
        i = max(k for k, x in enumerate(out) if x is not None)
        out[i] = dataclasses.replace(out[i], c=out[i].c * 10.0)
        return out
    monkeypatch.setattr(SynthStore, "h60", h60)


def _plant_m2_primitive(monkeypatch, env, world):
    orig = mix.fire_m2

    def m2(*a, **k):
        f = orig(*a, **k)
        return dataclasses.replace(f, raw_jb=(f.raw_jb + 1) if f.raw_jb is not None else None)
    monkeypatch.setattr(mix, "fire_m2", m2)


def _plant_bucket_vec(monkeypatch, env, world):
    orig = mix.bucket_vec

    def bv(f, starts, width, frames=True):
        out = orig(f, starts, width, frames)
        return np.full(len(out), mix.CODE_OF[NE], dtype=np.int8)
    monkeypatch.setattr(mix, "bucket_vec", bv)


def _plant_shift_flag(monkeypatch, env, world):
    orig = mix.enter_one
    done = []

    def eo(rec, u, stream):                                                  # one frozen per-level shifted placement flag flipped (its share kept)
        out = orig(rec, u, stream)
        if not done:
            for lv in mix.LIB_CODES["ENTER"]:
                s_ = out["res"]["shift"][lv]
                if not s_["no_room"]:
                    f = np.asarray(s_["feas"], dtype=bool).copy()
                    f[0] = not f[0]
                    s_["feas"] = f
                    done.append(lv)
                    break
        return out
    monkeypatch.setattr(mix, "enter_one", eo)


PLANTS = {
    "x_shift": (_plant_shift_flag, "STOPPED: gate (x)"),
    "i_wrong_day": (_plant_wrong_day, "STOPPED: gate (i) enter"),
    "i_clock": (_plant_clock_plus_one, "STOPPED: gate (i) clock arm enter"),
    "ii_builder": (_plant_builder, "STOPPED: gate (ii) enter"),
    "iii_last_bar": (_plant_last_bar, "STOPPED: gate (iii) stop_exit"),
    "vii_known": (lambda mp, env, w: mp.setattr(fz, "RANDOM_CONTROL_KNOWN", (0.999, 0.001)), "STOPPED: gate (vii)"),
    "viii_enter": (lambda mp, env, w: _shift_cell(env, "enter_fit_trades", "L8_cross", lambda row: row.get("scorable") == "True"), "STOPPED: gate (viii) ENTER enter_fit_trades"),
    "viii_stop": (lambda mp, env, w: _flip_cell(env, "stop_fit_trades", "S1_T_certain"), "STOPPED: gate (viii) STOP stop_fit_trades"),
    "viii_a": (lambda mp, env, w: _shift_cell(env, "exit_fit_trades", "E2_last_j"), "STOPPED: gate (viii-a) EXIT exit_fit_trades"),
    "viii_b": (_plant_m2_primitive, "STOPPED: gate (viii-b) EXIT "),
    "x_identity": (_plant_bucket_vec, "STOPPED: gate (x)"),
}


@needs_lock_inputs
@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_every_gate_stops_the_tag_on_a_planted_failure(plant, world, tsv_cache, tmp_path, monkeypatch):
    env = e2e_env(world, tsv_cache, tmp_path, monkeypatch)
    P = env["paths"]
    assert mix.main(["--dry-run"]) == 0
    fn, want = PLANTS[plant]
    fn(monkeypatch, env, world)
    paste_pins(env)
    assert mix.tag_lock() == []
    assert mix.main(["--tag"]) == 3, plant
    stopped = open(P["STOPPED"]).read()
    assert want in stopped and "ALL GATES PASSED" not in stopped and not os.path.exists(P["P_TAG"]), (plant, stopped[-1500:])


@needs_lock_inputs
def test_a_dry_run_mismatch_stops_and_the_tag_stays_locked(world, tsv_cache, tmp_path, monkeypatch):
    """The real MixClaims (not the quiet one): the synthetic world reproduces none of the registration's counts, so the dry run STOPS (3), its
    printout carries no DRY RUN COMPLETE, and guard (1) refuses the tag."""
    env = e2e_env(world, tsv_cache, tmp_path, monkeypatch)
    monkeypatch.setattr(mix, "MixClaims", _REAL_CLAIMS)
    assert mix.main(["--dry-run"]) == 3
    dry = open(env["paths"]["P_DRY"]).read()
    assert "STOPPED: the dry run does not reproduce the registration" in dry and "MISMATCH [L" in dry and "DRY RUN COMPLETE" not in dry
    paste_pins(env)
    assert any("THIS read's dry run has not COMPLETED" in x for x in mix.tag_lock()) and mix.main(["--tag"]) == 2


