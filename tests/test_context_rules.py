"""Tests for scripts/probes/_705_context_1026/01_ctx.py (#705 context rules; the registration's fixture copy under
scripts/probes/_705_context_1026/fixtures/ — the tests never read the live doc).

Synthetic fixtures only — every bar, minute, frame and tag row here is made up; no real outcome is read. Mechanics per context and per
map (the tree enumeration's count and canonical order, the dedupe, the floor, the tie rules, a missing value following the larger child),
the ±k and ±1c bucket mapping on hand-built Fires (pinned against the frozen `bucket`, G3's independent derivation and its bite), the
clipped placements, B1 on a minute world, both controls (the permutation moves context rows only; (c-1) scores each trade with its own
group's rule — a planted pooled-rule leak differs), SW against M-3 / M-4, the decision-time guard (planted future bars / minutes change no
context; a leaky reader FAILS G6), the HW maps, the labels arm by arm on gains, the paired interval, every guard (the lock refuses when only
the rule-mix dry run exists; the module scans), and ONE end-to-end synthetic world (--dry-run -> --print-pins -> --run) with real shapes:
era-A and era-B trades, an SPY gap, a 1-session window, a loser and a winner on one name, a bracket opening before 09:35 and one flat at
09:30, open-fill STOP rows (C-S1 MISSING), exit_lo_j = 1, a missing minute session, a record with no stock bar on D, tag files written by
the FROZEN rule-mix writer in their real serialization, a fresh market (objects freed, ids reusable) per stage.
Run: python3 -m pytest tests/test_context_rules.py -q -p no:cacheprovider
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import gc
import importlib.util
import math
import os
import re
import shutil
import sys
import types
import zlib
from collections import Counter
from datetime import date, timedelta

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX_DIR = os.path.join(REPO, "scripts", "probes", "_705_context_1026")
MOD_PATH = os.path.join(CTX_DIR, "01_ctx.py")
FIXTURE_DOC = os.path.join(CTX_DIR, "fixtures", "cb_context_rules_prereg_registered.md")
_spec = importlib.util.spec_from_file_location("ctx01_under_test", MOD_PATH)
ctx = importlib.util.module_from_spec(_spec)
sys.modules["ctx01_under_test"] = ctx
_spec.loader.exec_module(ctx)
mix, fz, rev, cb, rp, R, H = ctx.mix, ctx.fz, ctx.rev, ctx.cb, ctx.rp, ctx.R, ctx.H
EX, ME, UN, NE = ctx.EX, ctx.ME, ctx.UN, ctx.NE
F = ctx.Fire
_REAL_CLAIMS = ctx.CtxClaims


# ═════════════════════════════════════════════════════════════════════════════════════════════ fixtures (the rule-mix tests' shapes)
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


def mbars(minutes, closes, vol=None):
    c = np.asarray(closes, dtype=float)
    o = np.concatenate([[c[0]], c[:-1]])
    v = [1000.0] * len(c) if vol is None else list(vol)
    return cb.minute_bars_from_lists(list(minutes), list(o), list(np.maximum(o, c)), list(np.minimum(o, c)), list(c), v)


def path_minutes(points, n: int = 390):
    m = np.arange(n)
    xs, ys = zip(*points)
    return mbars(m, np.interp(m, xs, ys))


def quiet(p: float, n: int = 390):
    return path_minutes([(0, p), (130, p * 1.002), (260, p * 0.998), (n - 1, p)], n)


def daily_walk(n: int, base: float, seed: int, trend: float = 0.0006):
    rng = np.random.default_rng(seed)
    r = rng.normal(trend, 0.015, n)
    c = base * np.cumprod(1 + r)
    o = c * (1 + rng.normal(0, 0.004, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n)) + 0.0005)
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, n)) - 0.0005)
    v = 1e6 * (1 + np.abs(rng.normal(0, 0.3, n)))
    return o, h, l, c, v


def minutes_from_daily(o, h, l, c, early: bool = False, after_hours: bool = False, open_boost: float = 1.0):
    n = 210 if early else 390
    m = np.arange(n)
    closes = np.interp(m, [0, n // 3, 2 * n // 3, n - 1], [o, h, l, c])
    opens = np.concatenate([[o], closes[:-1]])
    vol = [1000.0 * (open_boost if k < 5 else 1.0) for k in range(n)]
    mm, o_, h_, l_, c_ = list(m), list(opens), list(np.maximum(opens, closes)), list(np.minimum(opens, closes)), list(closes)
    if early and after_hours:
        for k in range(210, 215):
            mm.append(k); o_.append(c); h_.append(c); l_.append(c); c_.append(c); vol.append(1000.0)
    return cb.minute_bars_from_lists(mm, o_, h_, l_, c_, vol)


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
    def __init__(self, by_date: dict):
        super().__init__({}, {})
        self.by_date = by_date

    def state(self, d, tk, b=None):
        return "ok/FAKE" if self.by_date.get(d) is not None else "empty/FAKE"

    def preload(self, pairs):
        return Counter()

    def get(self, d, tk, b=None):
        self.seal(d)
        return self.by_date.get(d)


def sightings_from(frames: list):
    rows = [dict(idx=i, frame_id=f"f{i}", vid="v", date=d, ctx=c_, clock=clk, symbols=s, blip_filled="") for i, (d, s, c_, clk) in enumerate(frames)]
    return rev.Sightings.build(pd.DataFrame(rows, columns=["idx", "frame_id", "vid", "date", "ctx", "clock", "symbols", "blip_filled"]))


def unit_rec(n: int = 90, e: int = 70, exit_lo: int = 3, exit_hi: int = 5, sess=None, empty=(), flat="10:05", first="10:40", fill_minute=0, fill=None,
             stop=None, adr20=0.04, eid=1, sym="AAA", setup="undated", rise: float = 0.005, vol=None):
    """One record on its own calendar (the rule-mix tests' builder): quiet minute paths on a series rising `rise` per session unless
    `sess[offset]` gives a path; `empty` offsets have no minutes; the daily bars are the minutes' own OHLC (daily volume `vol` or 1e6)."""
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
    v = np.full(n, 1e6) if vol is None else np.asarray(vol, dtype=float)
    bars = cb.daily_bars_from_arrays(cal, np.array(o), np.array(h), np.array(l), np.array(c), v)
    E = cal[e].isoformat()
    b = mk_buy(eid=eid, sym=sym, sym_a=sym, E=E, lo=E, hi=E, setup=setup, exit_lo=cal[e + exit_lo].isoformat() if exit_lo is not None else "",
               exit_hi=cal[e + exit_hi].isoformat() if exit_hi is not None else "", flat_clock=flat or "", first_clock=first or "", f_ctx="in" if first else "",
               p_ctx="in" if flat else "")
    rev.index_calendar([b], [d.isoformat() for d in cal])
    store = FakeStore(by_date)
    r = fz.IRec(b=b, bars=bars, cidx=np.arange(n, dtype=np.int32), e=e, adr20=fz.fnum(rev.adr20_at(bars, e - 1, b)), cal=cal, era="A", mb=store.get(E, sym),
                minutes_state="ok")                                                         # ADR20 as the frozen record builder reads it
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
    M = {"guards": {"A": {}, "B": {}}}
    spy_c = 300.0 * (1.001 ** np.arange(n))
    spy = (cb.daily_bars_from_arrays(cal, spy_c, spy_c * 1.002, spy_c * 0.998, spy_c, np.full(n, 1e8)), np.arange(n, dtype=np.int64))
    return r, store, M, spy


def drop_D(r):
    """The same record with the stock's bar dated D removed (a hole on the record's calendar): every D context must read MISSING."""
    keep = np.array([k for k in range(len(r.cidx)) if k != r.e - 1])
    b = r.bars
    bars = cb.daily_bars_from_arrays([b.dates[k] for k in keep], b.o[keep], b.h[keep], b.l[keep], b.c[keep], b.v[keep])
    return dataclasses.replace(r, bars=bars, cidx=r.cidx[keep], e=r.e - 1)


def tr_of(r, dec: str, **kw):
    base = dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, block="2020", dated=r.b.dated, decision=dec, flat_m=fz.hhmm_to_min(r.b.flat_clock) if r.b.flat_clock else None,
                first_m=fz.hhmm_to_min(r.b.first_clock) if r.b.first_clock else None, era="A", exit_lo_j=r.exit_lo_j, exit_hi_j=r.exit_hi_j, fill=r.fill,
                fill_minute=r.fill_minute, fill_src=r.fill_src)
    base.update(kw)
    return ctx.TradeRow(**base)


def fires_of(r, store, M):
    prep = fz.exit_prepare(r, M, store)
    c_ = mix.make_ctx(r, prep, store)
    return mix.exit_fires(r, prep, store, c_, fz.smas_for(r.bars)), prep, c_


# ═════════════════════════════════════════════════════════════════════════════════════════════ the trees (§5b-c)
def toy_search(vals: dict, order: list, m: int, dec: str = "EXIT"):
    splits = [ctx.Split(dec, cid, tok, float(cut), ml, i) for i, (cid, tok, cut, ml) in enumerate(order)]
    kept, dropped = ctx.dedupe_splits(splits, vals)
    return ctx.Search(dec, kept, vals, m), kept, dropped


def test_tree_enumeration_count_canonical_order_and_groups():
    for s, n in ((4, 101), (6, 295), (7, 449), (0, 1), (1, 5)):
        keys = ctx.enumerate_trees(s)
        assert len(keys) == n == 1 + s + s * ((s + 1) ** 2 - 1) and keys == sorted(keys) and keys[0] == (1, -1, 0, 0)
    assert tuple(len(ctx.enumerate_trees(len(ctx.SPLIT_ORDER[d]))) for d in ctx.DECISIONS) == (101, 295, 449)
    assert tuple(len(ctx.SPLIT_ORDER[d]) for d in ctx.DECISIONS) == (4, 6, 7)
    k = ctx.enumerate_trees(2)
    assert k[:3] == [(1, -1, 0, 0), (2, 0, 0, 0), (2, 1, 0, 0)]
    # fewer groups first; then the root; then the left option (a group before a split) before the right
    assert k.index((2, 1, 0, 0)) < k.index((3, 0, 0, 1)) < k.index((3, 0, 0, 2)) < k.index((3, 0, 1, 0)) < k.index((3, 1, 0, 1)) < k.index((4, 0, 1, 1))
    # a child may re-split on the root's own split (an empty child: the floor kills it); the groups list the left subtree first
    assert (3, 0, 1, 0) in k and ctx.tree_groups((4, 0, 1, 2)) == [(0, 0), (0, 1), (1, 2), (1, 3)] and ctx.tree_groups((3, 1, 0, 1)) == [(2,), (3, 0), (3, 1)]
    # the registered split order: C-S1's 1.0 first (C19), T1 before T2, contexts in §3's order
    assert ctx.SPLIT_ORDER["STOP"] == (("C-S1", "1.0"), ("C-S1", "T1"), ("C-S1", "T2"), ("C-S2", "T1"), ("C-S2", "T2"), ("C-S3", "bin"))
    assert ctx.SPLIT_ORDER["ENTER"] == (("C-E1", "T1"), ("C-E1", "T2"), ("C-E2", "bin"), ("C-E3", "bin"))


def test_dedupe_identical_and_mirrored_partitions_and_the_floor():
    vals = {"A": [1, 2, 3, 4, 5, 6], "B": [10, 20, 30, 40, 50, 60], "C": [6, 5, 4, 3, 2, 1], "D": [1, 1, 2, 2, 1, 2]}
    se, kept, dropped = toy_search(vals, [("A", "T1", 2, True), ("B", "T1", 20, True), ("C", "T1", 4, True), ("D", "T1", 1, True)], m=2)
    assert [s.cid for s in kept] == ["A", "D"] and [(d.cid, k.cid) for d, k in dropped] == [("B", "A"), ("C", "A")]     # the earlier kept
    assert se.s == 2 and len(se.all_keys) == 1 + 2 + 2 * 8
    # the floor: a split leaving a child under m is no candidate (a one-trade child under m = 2), and every tree built on it is out
    se2, kept2, _d = toy_search({"A": [1, 2, 3, 4, 5, 6]}, [("A", "T1", 1, True), ("A", "T2", 3, True)], m=2)
    assert (2, 0, 0, 0) not in se2.keys and (2, 1, 0, 0) in se2.keys and (1, -1, 0, 0) in se2.keys
    assert all(k[1] != 0 for k in se2.keys if k[0] > 1)
    # re-splitting a child on the root's own split leaves an empty group: never a candidate
    assert (3, 1, 2, 0) not in se2.keys
    # the doc's floor: m = max(15, ceil(0.10 x n_2020))
    assert (ctx.floor_m(88), ctx.floor_m(139), ctx.floor_m(333), ctx.floor_m(150), ctx.floor_m(151)) == (15, 15, 34, 15, 16)


def brute_scores(vals, splits, X, keys, m):
    """An independent brute force: every tree's groups as python sets, each group's best rule (first in library order), the floor."""
    n = len(next(iter(vals.values())))

    def child(c):
        s = splits[c // 2]
        left = {i for i in range(n) if (vals[s.cid][i] is not None and vals[s.cid][i] <= s.cut) or (vals[s.cid][i] is None and s.missing_left)}
        return left if c % 2 == 0 else set(range(n)) - left
    out = {}
    for k in keys:
        groups = [set(range(n)) if not g else (child(g[0]) if len(g) == 1 else child(g[0]) & child(g[1])) for g in ctx.tree_groups(k)]
        if k[0] > 1 and any(len(g) < m for g in groups):
            continue
        tot, rules = 0, []
        for g in groups:
            cnt = [sum(int(X[i, r]) for i in g) for r in range(X.shape[1])]
            rules.append(int(np.argmax(cnt)))
            tot += max(cnt)
        out[k] = (tot, rules)
    return out


def test_the_search_is_exhaustive_and_its_ties_follow_the_registered_order():
    rng = np.random.default_rng(5)
    for trial in range(60):
        n = 14
        vals = {"P": [int(x) for x in rng.integers(0, 2, n)], "Q": [float(x) for x in rng.normal(0, 1, n)],
                "S": [None if rng.random() < 0.2 else float(x) for x in rng.normal(0, 1, n)]}
        order = [("P", "bin", 0.0, True), ("Q", "T1", float(np.quantile(vals["Q"], 0.4)), True), ("S", "T1", 0.0, bool(trial % 2))]
        se, kept, _d = toy_search(vals, order, m=3)
        X = rng.random((n, 3)) < 0.35
        G = se.membership(vals)
        fit = se.fit(G, X)
        bf = brute_scores(vals, kept, X, se.all_keys, 3)
        best = max(v[0] for v in bf.values())
        first = min(k for k, v in bf.items() if v[0] == best)                       # the canonical order IS the tie rule
        assert fit["key"] == first and fit["score20"] == best and fit["rules"] == bf[first][1], trial
        assert set(se.keys) == set(bf)                                             # the floor, independently
    # the named tie rules on a designed world: a 2-group tree ties a 4-group one -> fewer groups; two roots tie -> the earlier root
    P, Q = [0, 0, 0, 0, 1, 1, 1, 1], [0, 0, 1, 1, 0, 0, 1, 1]
    se, kept, _d = toy_search({"P": P, "Q": Q}, [("P", "bin", 0.0, True), ("Q", "bin", 0.0, True)], m=1)
    X = np.zeros((8, 2), dtype=bool)
    X[[0, 1], 0], X[[6, 7], 1] = True, True
    fit = se.fit(se.membership({"P": P, "Q": Q}), X)
    assert fit["score20"] == 4 and fit["key"] == (2, 0, 0, 0) and fit["rules"] == [0, 1]
    # a group's rule on a tie -> the library order (the first column); the no-split procedure likewise
    X2 = np.ones((8, 3), dtype=bool)
    assert se.fit(se.membership({"P": P, "Q": Q}), X2)["rules"] == [0] and se.fit_best_single(X2)["rules"] == [0]
    # restricted columns (MAP-T1): the rule comes from the allowed columns only
    X3 = np.zeros((8, 3), dtype=bool)
    X3[:, 0] = True
    X3[:6, 2] = True
    assert se.fit_best_single(X3, cols=(1, 2))["rules"] == [2]


def test_assign_rules_refuses_a_trade_in_two_groups_or_in_none():
    G = np.array([[True, True, False], [False, True, True]])
    with pytest.raises(ctx.GuardStop, match="two groups"):
        ctx.assign_rules(dict(gids=[0, 1], rules=[2, 5]), G)
    with pytest.raises(ctx.GuardStop, match="no group"):
        ctx.assign_rules(dict(gids=[0], rules=[2]), G)
    assert ctx.assign_rules(dict(gids=[0, 1], rules=[2, 5]), np.array([[True, True, False], [False, False, True]])).tolist() == [2, 2, 5]

def test_tertiles_medians_and_a_missing_value_follows_the_larger_child():
    v = [5, None, 1, 3, 2, 4, None]
    assert ctx.tertile_cuts(v) == (2.0, 4.0) and ctx.median_cut(v) == 3.0                 # ceil(5/3) = 2nd, ceil(10/3) = 4th, ceil(5/2) = 3rd
    assert ctx.tertile_cuts([None, None]) == (None, None)
    v48 = list(range(48)) + [None] * 91
    t1, t2 = ctx.tertile_cuts(v48)
    assert (t1, t2) == (15.0, 31.0)                                                         # the doc's "16th / 32nd of 48"
    # missing -> the larger child by the 2020 count of DEFINED values; a tie -> left (C4)
    assert ctx.missing_side([1, 2, 3, None], 2) is True and ctx.missing_side([1, 3, 4, None], 2) is False and ctx.missing_side([1, 3, None], 2) is True
    s = ctx.Split("STOP", "C-S1", "T1", 2.0, False, 0)
    assert list(ctx.left_mask(s, [1, 3, None, 2])) == [True, False, False, True]
    # a mass point: T1 == T2 gives one partition -> deduped (the earlier kept)
    mp = {"C-X1": [1.0, 1.0, 1.0, 1.0, 2.0, 2.0]}
    cuts = ctx.cut_values("EXIT", {"C-X1": mp["C-X1"], "C-X2": mp["C-X1"], "C-X3": mp["C-X1"], "C-X4": [0.0] * 6})
    assert cuts[("C-X1", "T1")] == cuts[("C-X1", "T2")] == 1.0 and cuts[("C-X4", "bin")] == 0.0
    sp = ctx.make_splits("EXIT", {"C-X1": mp["C-X1"], "C-X2": mp["C-X1"], "C-X3": mp["C-X1"], "C-X4": [0.0] * 6}, cuts)
    kept, dropped = ctx.dedupe_splits(sp, {"C-X1": mp["C-X1"], "C-X2": mp["C-X1"], "C-X3": mp["C-X1"], "C-X4": [0.0] * 6})
    assert kept[0].cid == "C-X1" and kept[0].token == "T1" and any(d.cid == "C-X1" and d.token == "T2" for d, _k in dropped)


# ═════════════════════════════════════════════════════════════════════════════════════════════ "close to" (§4a)
def test_the_convention_aware_window_on_hand_built_fires():
    lo, hi, J = 3, 3, 30
    cb_ = lambda f, tol: ctx.close_bucket(f, lo, hi, tol, J)          # noqa: E731
    # same-session booking: MISS-EARLY on exit_lo - 1 -> CLOSE at ±1c; a firing on exit_hi + 1 stays NEITHER at ±1c
    assert mix.bucket(F(je=2, jb=2), lo, hi) == ME and cb_(F(je=2, jb=2), "pm1c") == EX
    assert mix.bucket(F(je=4, jb=4), lo, hi) == NE and cb_(F(je=4, jb=4), "pm1c") == NE and cb_(F(je=4, jb=4), "pm1") == EX
    # next-session booking: booked on exit_hi + 1 -> CLOSE at ±1c; one booked on exit_lo - 1 stays MISS-EARLY at ±1c
    assert mix.bucket(F(je=3, jb=4), lo, hi) == NE and cb_(F(je=3, jb=4), "pm1c") == EX
    assert cb_(F(je=1, jb=2), "pm1c") == ME and cb_(F(je=1, jb=2), "pm1") == EX
    # first firing only: booked two sessions early stays MISS-EARLY at ±1c and ±1, reads CLOSE only at ±2
    assert cb_(F(je=1, jb=1), "pm1c") == ME and cb_(F(je=1, jb=1), "pm1") == ME and cb_(F(je=1, jb=1), "pm2") == EX
    # a buy-day firing without an in-session frame stays UNRESOLVED at every tolerance
    for tol in ("pm0", "pm1c", "pm1", "pm2"):
        assert ctx.close_bucket(F(je=0, jb=0, bd_unres=True), 1, 1, tol, J) == UN
    # a firing on exit_hi + 1 after a no-minute session before its event -> UNRESOLVED
    assert cb_(F(je=3, jb=4, missing=(2,)), "pm1c") == UN and cb_(F(je=4, jb=4, missing=(2,)), "pm1") == UN
    # §4a's ONE upgrade, pinned against the frozen bucket: next-session booking whose event lies on a missing exit_hi
    f = F(je=3, jb=4, missing=(3,))
    assert mix.bucket(f, lo, hi) == UN and mix.bucket(f, lo, hi + 1) == EX and cb_(f, "pm1c") == EX
    # the window clipped at offset 0 and at J_tail
    assert ctx.widened(0, 2, 1, 0, 30) == (0, 2) and ctx.widened(1, 5, 2, 2, 6) == (0, 6)
    assert ctx.close_bucket(F(je=6, jb=7), 3, 6, "pm1c", 6) == NE                         # hi + 1 beyond J_tail: clipped
    # an R2 Fire whose two readings book on different sides takes the OUTER Fire's side (outer: the buy day, same-session -> [lo - 1, hi])
    r2 = F(je=0, jb=0, alt=F(je=1, jb=2))
    assert ctx.fire_side(r2) == "same" and ctx.close_bucket(r2, 1, 2, "pm1c", 30) == EX
    assert mix.bucket(r2, 1, 3) == UN                                                       # the alt's own side ([lo, hi + 1]) would read UNRESOLVED
    # a never-fired or abstaining rule reads unwidened (C9)
    assert cb_(F(missing=(5,)), "pm2") == NE and cb_(F(abstain="ema_thin", je=3, jb=3), "pm1c") == NE
    assert ctx.tol_ab("pm1c", "next") == (0, 1) and ctx.tol_ab("pm1c", "same") == (1, 0) and ctx.tol_ab("pm2", "same") == (2, 2) and ctx.tol_ab("pm1c", None) == (0, 0)


def random_fires(rng, n):
    out = []
    for _ in range(n):
        je = int(rng.integers(0, 12)) if rng.random() < 0.85 else None
        jb = None if je is None else je + int(rng.random() < 0.35)
        miss = tuple(sorted(set(int(x) for x in rng.integers(0, 14, size=int(rng.integers(0, 3))))))
        f = F(je=je, jb=jb, bd_unres=bool(je == 0 and rng.random() < 0.4), missing=miss, abstain="x" if rng.random() < 0.05 else "")
        if je is not None and rng.random() < 0.15:
            f = F(je=0, jb=0, alt=dataclasses.replace(f, missing=()), missing=())
        out.append(f)
    return out


def test_g3_derivation_agrees_with_the_widened_frozen_bucket_and_bites():
    rng = np.random.default_rng(11)
    J = 13
    n_checked = 0
    for f in random_fires(rng, 2500):
        for lo, hi in ((0, 0), (1, 2), (3, 3), (4, 7), (2, 10)):
            b0 = mix.bucket(f, lo, hi)
            for tol in ("pm1c", "pm1", "pm2", "pm0"):
                assert ctx.derive_widened(b0, f, lo, hi, tol, J) == ctx.close_bucket(f, lo, hi, tol, J), (f, lo, hi, tol)
                n_checked += 1
    assert n_checked > 40000
    # a planted one-session shift of one booked_j: the file's ±0 bucket (the true Fire) vs the shifted Fire's widened bucket -> disagreement
    true_f = F(je=3, jb=3)
    shifted = dataclasses.replace(true_f, jb=4, je=4)                                      # the booking moved one session later
    assert ctx.derive_widened(mix.bucket(true_f, 3, 3), shifted, 3, 3, "pm1c", J) != ctx.close_bucket(shifted, 3, 3, "pm1c", J)
    # a flipped side in the path under test (tol_ab swapped): the independent derivation disagrees
    orig = ctx.tol_ab
    try:
        ctx.tol_ab = lambda tol, side: orig(tol, {"same": "next", "next": "same"}.get(side, side))
        f = F(je=2, jb=2)
        assert ctx.close_bucket(f, 3, 3, "pm1c", J) != ctx.derive_widened(mix.bucket(f, 3, 3), f, 3, 3, "pm1c", J)
    finally:
        ctx.tol_ab = orig


def test_clipped_placements_and_the_s_ge_af_variant():
    f = F(je=1, jb=1)
    codes, clipped = ctx.se_window_codes(f, np.array([0, 1, 2]), 2, "pm1c", 20, True)
    assert list(clipped) == [True, False, False]
    # s = 0 cannot widen before the buy day: [0, 1]; s = 2 widens to [1, 3] (a same-session booking on 1 = its start - 1 -> CLOSE)
    assert [mix.BUCKETS[int(c)] for c in codes] == [EX, EX, EX]
    codes0, _c = ctx.se_window_codes(f, np.array([0, 1, 2]), 2, "pm0", 20, True)
    assert [mix.BUCKETS[int(c)] for c in codes0] == [EX, EX, ME]
    nx = F(je=3, jb=4)
    c2, cl2 = ctx.se_window_codes(nx, np.array([0, 1, 2]), 2, "pm1c", 20, False)
    assert not cl2.any() and [mix.BUCKETS[int(c)] for c in c2] == [NE, NE, EX]              # next-session: [s, s + w] — the start never moves


def test_b1_recross_on_a_minute_world():
    level = 50.5
    pts = [(0, 50.0), (3, 50.8), (8, 50.6), (12, 50.2), (20, 50.9), (389, 51.0)]
    mb = path_minutes(pts)
    assert rev.first_cross(mb, level) <= 10                                                 # first crossed before flat (MISS-EARLY at the bracket)
    assert ctx.recross(mb, lambda m: level, 10, 30, 0) is True                              # a dip under the level, a second break inside -> CLOSE
    no_dip = path_minutes([(0, 50.0), (3, 50.8), (389, 51.2)])
    assert ctx.recross(no_dip, lambda m: level, 10, 30, 0) is False                         # no close under the level inside -> not
    assert ctx.recross(mb, lambda m: level, 10, 22, 25) is False                            # the level not existing by the window's end -> not
    assert ctx.recross(mb, lambda m: None, 10, 30, 0) is False


def ohlc_minutes(rows):
    """Minute bars 0..len(rows)-1 from explicit (o, h, l, c) rows."""
    o, h, l, c = (list(x) for x in zip(*rows))
    return cb.minute_bars_from_lists(list(range(len(rows))), o, h, l, c, [1000.0] * len(rows))


def test_b1_and_b2_at_their_boundaries():
    L, lo_m, hi_m = 50.5, 10, 20
    above = (50.6, 50.7, 50.55, 50.6)
    # the dip on the flat minute itself counts (u in [flat, t))
    rows = [above] * 10 + [(50.6, 50.6, 50.4, 50.4), (50.4, 50.6, 50.4, 50.6)] + [above] * 9
    assert ctx.recross(ohlc_minutes(rows), lambda m: L, lo_m, hi_m, 0) is True
    # a dip whose close EQUALS the level is no dip (close < level)
    rows = [above] * 12 + [(50.6, 50.6, 50.5, 50.5), (50.5, 50.6, 50.5, 50.6)] + [above] * 7
    assert ctx.recross(ohlc_minutes(rows), lambda m: L, lo_m, hi_m, 0) is False
    # a re-cross whose high EQUALS the level counts (high >= level); every later minute stays under it
    rows = [above] * 12 + [(50.6, 50.6, 50.3, 50.3), (50.3, 50.5, 50.3, 50.4)] + [(50.4, 50.45, 50.35, 50.4)] * 7
    assert ctx.recross(ohlc_minutes(rows), lambda m: L, lo_m, hi_m, 0) is True
    # B1 on a k-price draw first crossed EXACTLY at the flat minute (at or before flat_clock: it may re-cross)
    rows = [(50.0, 50.1, 49.9, 50.0)] * 10 + [(50.4, 50.6, 50.4, 50.45), (50.45, 50.6, 50.45, 50.55)] + [(50.55, 50.6, 50.5, 50.55)] * 9
    mb = ohlc_minutes(rows)
    assert rev.first_cross(mb, L) == lo_m
    e = dict(flat_m=lo_m, first_m=hi_m, width=hi_m - lo_m, kprice=dict(codes=np.zeros((1, 1), dtype=bool), prices=np.full((1, 1), L)), shared=dict(no_room=True))
    out = ctx.enter_controls(e, types.SimpleNamespace(mb=mb, adr20=0.04), "B1")
    assert out["kprice"].tolist() == [[True]] and out["shared"] is None
    assert ctx.enter_controls(e, types.SimpleNamespace(mb=mb, adr20=0.04), "bracket")["kprice"].tolist() == [[False]]
    # B2: a BALLPARK (not HIT) verdict reads CLOSE; the strict EXPLAINS kept; anything else not
    lib = ctx.LIB["ENTER"]
    real = {c: NE for c in lib}
    real[lib[3]] = EX
    res = {c: {"verdict": "MISS"} for c in lib}
    res[lib[1]], res[lib[2]] = {"verdict": "BALLPARK"}, {"verdict": "HIT"}
    row = ctx.enter_close_row(dict(real=real, res=res), None, "B2")
    assert row.tolist() == [False, True, True, True, False, False, False]
    assert ctx.enter_close_row(dict(real=real, res=res), None, "bracket").tolist() == [False, False, False, True, False, False, False]


# ═════════════════════════════════════════════════════════════════════════════════════════════ the controls on a toy decision
def toy_data(seed: int = 3):
    """A toy ENTER decision: 2020 / 2021-22 / untouched with contexts, a CLOSE matrix, (c-1) chances and (c-2) draws."""
    rng = np.random.default_rng(seed)
    ns = {"2020": 40, "2021-22": 24, "untouched": 6}
    vals = {b: {"C-E1": [None if rng.random() < 0.1 else float(x) for x in rng.gamma(2, 2, n)], "C-E2": [float(x) for x in rng.integers(0, 2, n)],
                "C-E3": [float(x) for x in rng.integers(0, 2, n)]} for b, n in ns.items()}
    v20 = vals["2020"]
    cuts = ctx.cut_values("ENTER", v20)
    sp = ctx.make_splits("ENTER", v20, cuts)
    kept, _d = ctx.dedupe_splits(sp, v20)
    se = ctx.Search("ENTER", kept, v20, 6)
    R_ = 7
    X = {b: rng.random((n, R_)) < np.linspace(0.2, 0.5, R_) for b, n in ns.items()}
    data = dict(X={"ENTER": {"bracket": X}}, chance1={"ENTER": {"bracket": {a: {b: rng.random((n, R_)) for b, n in ns.items()} for a in ("kprice", "shared")}}},
                draws2={"ENTER": {"bracket": {a: {b: rng.random((ctx.DRAWS, n, R_)) < 0.3 for b, n in ns.items()} for a in ("kprice", "shared")}}})
    G = {b: se.membership(vals[b]) for b in ns}
    return se, vals, data, G


def test_the_permutation_moves_context_rows_only_within_a_block_and_the_close_matrix_stays(monkeypatch):
    monkeypatch.setattr(ctx, "PERMS", 12)
    se, vals, data, G = toy_data()
    before = {b: x.copy() for b, x in data["X"]["ENTER"]["bracket"].items()}
    L = ctx.evaluate_line(ctx.Line("MAP", "search", cols=tuple(range(7))), "ENTER", "bracket", se, G, vals, data)
    for b, x in data["X"]["ENTER"]["bracket"].items():
        assert x.tobytes() == before[b].tobytes()                                           # the CLOSE matrix byte-equal
    # the permutations: keyed per decision, block and index; 2020 and 2021-22 independent; the untouched block never permuted
    p20, p22 = ctx.shuffled(40, "ENTER", "2020", 0), ctx.shuffled(24, "ENTER", "2021-22", 0)
    assert sorted(p20) == list(range(40)) and not np.array_equal(p20, ctx.shuffled(40, "ENTER", "2020", 1)) and np.array_equal(p20, ctx.shuffled(40, "ENTER", "2020", 0))
    assert set(L["shuf"]) == {"2020", "2021-22"}
    # the SHUF mean re-derived by hand: whole context rows permuted, the search re-run on the permuted 2020, scored on the permuted 2021-22
    X = data["X"]["ENTER"]["bracket"]
    s20, s22 = [], []
    for p in range(12):
        pa, pb = ctx.shuffled(40, "ENTER", "2020", p), ctx.shuffled(24, "ENTER", "2021-22", p)
        v20 = ctx.permute_vals(vals["2020"], pa)
        v22 = ctx.permute_vals(vals["2021-22"], pb)
        g20, g22 = se.membership(v20), se.membership(v22)
        fit = se.fit(g20, X["2020"])
        s20.append(ctx.map_share(fit, g20, X["2020"]))
        s22.append(ctx.map_share(fit, g22, X["2021-22"]))
    assert L["shuf"]["2020"]["mean"] == pytest.approx(np.mean(s20)) and L["shuf"]["2021-22"]["mean"] == pytest.approx(np.mean(s22))
    # the real map is in-sample on 2020: never below the no-split best there
    B = ctx.evaluate_line(ctx.Line("BEST", "best", cols=tuple(range(7))), "ENTER", "bracket", se, G, vals, data)
    assert L["share"]["2020"] >= B["share"]["2020"]


def test_per_leaf_chance_scores_each_trade_with_its_own_group_rule_and_a_pooled_leak_differs(monkeypatch):
    monkeypatch.setattr(ctx, "PERMS", 2)
    se, vals, data, G = toy_data(seed=8)
    L = ctx.evaluate_line(ctx.Line("MAP", "search", cols=tuple(range(7))), "ENTER", "bracket", se, G, vals, data)
    B = ctx.evaluate_line(ctx.Line("BEST", "best", cols=tuple(range(7))), "ENTER", "bracket", se, G, vals, data)
    assert len(L["fit"]["gids"]) > 1 and len(set(L["fit"]["rules"])) > 1                  # a map with two rules (else the test says nothing)
    for a in ("kprice", "shared"):
        ch = data["chance1"]["ENTER"]["bracket"][a]["2020"]
        rules = ctx.assign_rules(L["fit"], G["2020"])
        own = np.mean([ch[i, rules[i]] for i in range(len(rules))])
        pooled = np.mean(ch[:, B["fit"]["rules"][0]])
        assert L["c1"][a]["2020"] == pytest.approx(own) and abs(own - pooled) > 1e-6
        assert B["c1"][a]["2020"] == pytest.approx(pooled)                                  # the no-split tree = the best rule's own chance (G5)
    # NaN (no room) trades leave the mean
    ch = np.array([[0.5, np.nan], [np.nan, 0.2], [1.0, 0.0]])
    assert ctx.per_leaf_chance(np.array([0, 1, 1]), ch) == pytest.approx((0.5 + 0.2 + 0.0) / 3) and np.isnan(ctx.per_leaf_chance(np.array([1, 0]), ch[:2]))
    # (c-2): the procedure on each draw, chosen on 2020's draw — by hand on draw 0..DRAWS-1
    d20, d22 = data["draws2"]["ENTER"]["bracket"]["kprice"]["2020"], data["draws2"]["ENTER"]["bracket"]["kprice"]["2021-22"]
    s22 = [ctx.map_share(se.fit(G["2020"], d20[d]), G["2021-22"], d22[d]) for d in range(ctx.DRAWS)]
    assert L["c2"]["kprice"]["2021-22"] == pytest.approx(np.mean(s22))


# ═════════════════════════════════════════════════════════════════════════════════════════════ SW, the 10/20 switch
def sw_world():
    """A hold whose trail switches mid-hold: a slow climb (close near the 20-day), a dip under the 10-day only (+3), a steep rally (far
    above the 20-day), a second dip under the 10-day (+9), then a fall through the 20-day (+14)."""
    def day(k):
        return lambda p: path_minutes([(0, p), (389, p * k)])
    sess = {3: day(0.985), 4: day(1.002)}
    for j in range(5, 9):
        sess[j] = day(1.06)
    sess[9] = day(0.83)
    sess[10] = day(1.0)
    for j in range(11, 14):
        sess[j] = day(0.99)
    sess[14] = day(0.90)
    return unit_rec(n=110, e=70, exit_lo=12, exit_hi=15, sess=sess, rise=0.003, adr20=0.03)


def test_sw_equals_m3_m4_at_the_extreme_cuts_and_switches_mid_hold():
    r, store, M, _spy = sw_world()
    f, prep, c_ = fires_of(r, store, M)
    smas = fz.smas_for(r.bars)
    for cut, a_want, b_want in ((-math.inf, "M-3", "M-4"), (math.inf, "M-4", "M-3")):
        assert ctx.switch_fire(r, c_, smas, cut, "a") == f[a_want] and ctx.switch_fire(r, c_, smas, cut, "b") == f[b_want]
    # an independent walk of the switch at a cut between the two dips' distances
    c, adr = r.bars.c, r.adr20

    def dist(j):
        k = r.bar_at(j - 1)
        return (c[k] - smas[20][k]) / (adr * c[k])
    d3, d9 = dist(3), dist(9)
    assert d9 > d3                                                                          # the rally put the second dip far above the 20-day
    cut = (d3 + d9) / 2

    def walk(far_to_10: bool):
        for j in range(0, 30):
            k = r.bar_at(j)
            far = dist(j) >= cut
            n = 10 if (far == far_to_10) else 20
            if c[k] < smas[n][k]:
                return j
        return None
    sa, sb = ctx.switch_fire(r, c_, smas, cut, "a"), ctx.switch_fire(r, c_, smas, cut, "b")
    assert sa.je == walk(True) and sb.je == walk(False)
    assert f["M-3"].je == 3 and sa.je == 9 and sa.je not in (f["M-3"].je, f["M-4"].je)        # SW-a is neither M-3 nor M-4 here
    assert sa.jb == sa.je and sa.m == mix.CLOSE_M                                           # booked on its own session (as M-3 / M-4)
    # a distance EXACTLY on the cut is far (§5e: >= the cut): SW-a takes the 10-day on +3 and fires on its dip there; a hair above the cut
    # it is not far, the 20-day holds through +3 and SW-a fires later (the boundary discriminates)
    assert ctx.switch_fire(r, c_, smas, d3, "a").je == 3 and ctx.switch_fire(r, c_, smas, float(np.nextafter(d3, math.inf)), "a").je != 3
    # an undefined distance (no bar at j - 1) reads -inf: not far
    rD = drop_D(r)
    fD, pD, cD = fires_of(rD, store, M)
    assert ctx.switch_fire(rD, cD, fz.smas_for(rD.bars), -math.inf, "a") == fD["M-3"]


# ═════════════════════════════════════════════════════════════════════════════════════════════ the decision-time guard (D1, G6)
def test_planted_future_bars_and_minutes_change_no_context_and_a_leaky_reader_fails_g6(monkeypatch):
    r, store, M, spy = unit_rec(n=120, e=100, exit_lo=3, exit_hi=5, flat="10:05", first="10:40", fill_minute=45, setup="breakout", sym="DDD")
    r.b.dated = True
    trs = {d: tr_of(r, d) for d in ctx.DECISIONS}
    base = {d: ctx.context_values(d, ctx.make_view(r, d, trs[d], spy)) for d in ctx.DECISIONS}
    assert all(v[0] is not None for d in ctx.DECISIONS for v in base[d].values()), base
    # a planted bar on the buy day or later changes no D context (truncated AND full reader)
    for arr in (r.bars.h, r.bars.l, r.bars.c, r.bars.v):
        arr[r.e + 1:] *= 7.0
    r.bars.c[r.e] *= 3.0
    r.bars.v[r.e] *= 50.0
    spy[0].c[r.e_ci:] *= 2.0
    for d in ctx.DECISIONS:
        assert ctx.context_values(d, ctx.make_view(r, d, trs[d], spy)) == base[d]
        assert ctx.context_values(d, ctx.make_view(r, d, trs[d], spy, full=True)) == base[d]
    # a planted 09:35 minute (minute 5) changes no C-E1; on a bracket opening at 09:32, planted 09:32-09:34 minutes change nothing
    r.mb.v[5:30] *= 100.0
    assert ctx.context_values("ENTER", ctx.make_view(r, "ENTER", trs["ENTER"], spy))["C-E1"] == base["ENTER"]["C-E1"]
    t32 = tr_of(r, "ENTER", flat_m=2)
    e32 = ctx.context_values("ENTER", ctx.make_view(r, "ENTER", t32, spy))["C-E1"]
    r.mb.v[2:5] *= 1000.0
    assert ctx.context_values("ENTER", ctx.make_view(r, "ENTER", t32, spy))["C-E1"] == e32
    assert ctx.context_values("ENTER", ctx.make_view(r, "ENTER", tr_of(r, "ENTER", flat_m=0), spy))["C-E1"] == (None, "no_minute_before_bound")
    # a planted fill-minute low changes no C-S1 (strictly before the fill minute); a low one minute earlier does (the control)
    s0 = ctx.context_values("STOP", ctx.make_view(r, "STOP", trs["STOP"], spy))["C-S1"]
    r.mb.l[45] *= 0.5
    assert ctx.context_values("STOP", ctx.make_view(r, "STOP", trs["STOP"], spy))["C-S1"] == s0
    assert ctx.context_values("STOP", ctx.make_view(r, "STOP", trs["STOP"], spy, full=True))["C-S1"] == s0    # the full record too: strictly before
    r.mb.l[44] *= 0.5
    assert ctx.context_values("STOP", ctx.make_view(r, "STOP", trs["STOP"], spy))["C-S1"] != s0
    # an open fill -> C-S1 MISSING; a close fill reads every minute of the session
    assert ctx.context_values("STOP", ctx.make_view(r, "STOP", tr_of(r, "STOP", fill_minute=0), spy))["C-S1"] == (None, "open_fill")
    assert ctx.context_values("STOP", ctx.make_view(r, "STOP", tr_of(r, "STOP", fill_minute=None), spy))["C-S1"][0] is not None
    # the by-date assertion holds on the truncated view; the full view would fail it (it holds the future)
    v = ctx.make_view(r, "EXIT", trs["EXIT"], spy)
    assert ctx.assert_view_dates(v, r) == [] and ctx.assert_view_dates(ctx.make_view(r, "EXIT", trs["EXIT"], spy, full=True), r)
    vals, fails = ctx.compute_contexts("EXIT", [trs["EXIT"]], {r.b.eid: r}, {"A": spy}, check_full=True)
    assert fails == []
    # a LEAKY reader (D taken as the last bar the view holds): G6 catches it (the full record reads the future)
    monkeypatch.setattr(ctx, "view_d_index", lambda v_: len(v_.daily.dates) - 1)
    _v, fails = ctx.compute_contexts("EXIT", [trs["EXIT"]], {r.b.eid: r}, {"A": spy}, check_full=True)
    assert fails


def test_no_stock_bar_on_d_reads_every_context_missing_and_an_spy_gap_reads_the_market_missing():
    r, store, M, spy = unit_rec(n=120, e=100)
    rD = drop_D(r)
    assert rD.bar_at(-1) is None and rD.b.E == r.b.E
    for d in ctx.DECISIONS:
        vals = ctx.context_values(d, ctx.make_view(rD, d, tr_of(rD, d), spy))
        assert all(v == (None, "no_bar_D") for v in vals.values()), (d, vals)
        assert ctx.assert_view_dates(ctx.make_view(rD, d, tr_of(rD, d), spy), rD) == []
    # an SPY gap inside the 50 sessions ending at D (or at D - 10) -> the market's trend MISSING; outside -> defined
    sb, sci = spy
    for gap, want_missing in ((r.e_ci - 30, True), (r.e_ci - 65, False)):
        keep = np.array([k for k in range(len(sci)) if k != gap])
        sp2 = (cb.daily_bars_from_arrays([sb.dates[k] for k in keep], sb.o[keep], sb.h[keep], sb.l[keep], sb.c[keep], sb.v[keep]), sci[keep])
        v = ctx.context_values("EXIT", ctx.make_view(r, "EXIT", tr_of(r, "EXIT"), sp2))["C-X4"]
        assert (v == (None, "spy_missing")) is want_missing, gap
    # uptrend = SPY's 50-day above 10 sessions earlier (a rising SPY reads 1)
    assert ctx.context_values("EXIT", ctx.make_view(r, "EXIT", tr_of(r, "EXIT"), spy))["C-X4"] == (1.0, "")
    # ADV20 needs the 20 consecutive calendar sessions ending at D: a hole inside them -> C-E1 MISSING
    keep = np.array([k for k in range(len(r.cidx)) if k != r.e - 5])
    b = r.bars
    rH = dataclasses.replace(r, bars=cb.daily_bars_from_arrays([b.dates[k] for k in keep], b.o[keep], b.h[keep], b.l[keep], b.c[keep], b.v[keep]),
                             cidx=r.cidx[keep], e=r.e - 1)
    assert ctx.context_values("ENTER", ctx.make_view(rH, "ENTER", tr_of(rH, "ENTER"), spy))["C-E1"] == (None, "adv20_missing")


def test_the_context_formulas_on_a_hand_record():
    vol = np.full(120, 2e6)
    r, store, M, spy = unit_rec(n=120, e=100, vol=vol, flat="10:05", first="10:40")
    v = ctx.make_view(r, "ENTER", tr_of(r, "ENTER"), spy)
    e1, _w = ctx.context_values("ENTER", v)["C-E1"]
    assert e1 == pytest.approx(1000.0 / (2e6 / 390))                                         # minutes 0-4 at 1,000 against ADV20 / 390
    e2, _w = ctx.context_values("ENTER", v)["C-E2"]
    assert e2 == (1.0 if r.bars.o[r.e] <= r.bars.h[r.e - 1] else 0.0)
    x = ctx.context_values("EXIT", ctx.make_view(r, "EXIT", tr_of(r, "EXIT"), spy))
    sm = fz.smas_for(r.bars)
    k = r.e - 1
    assert x["C-X1"] == (pytest.approx(r.adr20), "")
    assert x["C-X2"][0] == pytest.approx((r.bars.c[k] - sm[10][k]) / (r.adr20 * r.bars.c[k]))
    assert x["C-X3"][0] == pytest.approx((r.bars.c[k] - sm[20][k]) / (r.adr20 * r.bars.c[k]))
    s = ctx.context_values("STOP", ctx.make_view(r, "STOP", tr_of(r, "STOP", fill_minute=45, fill=float(r.mb.h[:46].max())), spy))
    low = float(r.mb.l[:45].min())
    fill = float(r.mb.h[:46].max())
    assert s["C-S1"][0] == pytest.approx((fill - low) / (r.adr20 * fill))


def spy_tuple(cal, c):
    c = np.asarray(c, dtype=float)
    return cb.daily_bars_from_arrays(cal, c, c + 1.0, c - 1.0, c, np.full(len(c), 1e8)), np.arange(len(c), dtype=np.int64)


def test_the_market_trend_adv20_and_c_e2_at_their_registered_lengths_and_boundaries():
    vol = 1e6 * (1.0 + (np.arange(120) % 7))                                              # a daily volume that varies: ADV20 != ADV19
    r, store, M, _spy = unit_rec(n=120, e=100, vol=vol, flat="10:05", first="10:40")
    ci = r.e_ci - 1                                                                         # D's calendar index
    base = 300.0 + (np.arange(120) % 10)                                                   # period 10, integer-valued: the sums are exact
    # SPY's 50-day mean at D is the mean of the 50 closes ending at D
    v = ctx.make_view(r, "EXIT", tr_of(r, "EXIT"), spy_tuple(r.cal, base))
    assert ctx.spy_sma_at(v, ci) == pytest.approx(np.mean(base[ci - 49:ci + 1]))
    # the 50-day at D EXACTLY equal to the 50-day 10 sessions earlier: not an uptrend (strictly higher, C2)
    assert ctx.market_up(v) == (0.0, "")
    # one low close at D - 59 (the oldest of the D-10 window): an uptrend at 50 / 10 only (at 49 / 10 or 50 / 9 the windows stay equal)
    dip = base.copy()
    dip[ci - 59] -= 5.0
    vd = ctx.make_view(r, "EXIT", tr_of(r, "EXIT"), spy_tuple(r.cal, dip))
    assert ctx.market_up(vd) == (1.0, "") and ctx.context_values("EXIT", vd)["C-X4"] == (1.0, "")
    assert np.mean(dip[ci - 48:ci + 1]) == np.mean(dip[ci - 58:ci - 9]) and np.mean(dip[ci - 49:ci + 1]) == np.mean(dip[ci - 58:ci - 8])
    # ADV20 = the mean of the 20 daily volumes ending at D (not 19); C-E1 = the opening rate over ADV20 / 390
    ve = ctx.make_view(r, "ENTER", tr_of(r, "ENTER"), spy_tuple(r.cal, base))
    a20 = np.mean(vol[r.e - 20:r.e])
    assert a20 != np.mean(vol[r.e - 19:r.e]) and ctx.adv20(ve, ctx.view_d_index(ve)) == pytest.approx(a20)
    assert ctx.context_values("ENTER", ve)["C-E1"][0] == pytest.approx(1000.0 / (a20 / 390))
    # C-E2: an open EXACTLY at the prior high = 1 (open <= the prior high); a hair above = 0
    r.bars.o[r.e] = r.bars.h[r.e - 1]
    assert ctx.context_values("ENTER", ctx.make_view(r, "ENTER", tr_of(r, "ENTER"), spy_tuple(r.cal, base)))["C-E2"] == (1.0, "")
    r.bars.o[r.e] = float(np.nextafter(r.bars.h[r.e - 1], math.inf))
    assert ctx.context_values("ENTER", ctx.make_view(r, "ENTER", tr_of(r, "ENTER"), spy_tuple(r.cal, base)))["C-E2"] == (0.0, "")


def test_each_by_date_check_names_its_own_violation_and_g6_holds_the_adr20_identity():
    r, store, M, spy = unit_rec(n=120, e=100, flat="10:05", first="10:40", fill_minute=45, setup="breakout")
    tr = tr_of(r, "STOP")
    v = ctx.make_view(r, "STOP", tr, spy)
    assert ctx.assert_view_dates(v, r) == [] and v.bound_m == 45
    # one violation planted at a time; each names ITS check (deleting any one check fails here)
    assert ctx.assert_view_dates(dataclasses.replace(v, daily=r.bars.slice(0, r.e + 1)), r) == ["a daily bar dated >= E in the view"]
    assert ctx.assert_view_dates(dataclasses.replace(v, minutes=ctx._cut_minutes(r.mb, 46)), r) == ["a minute at or after the bound 45"]
    sb, sci = spy
    k = len(v.spy_ci)
    assert ctx.assert_view_dates(dataclasses.replace(v, spy=sb.slice(0, k + 1), spy_ci=sci[:k + 1]), r) == ["a SPY bar dated after D"]
    # G6: the ADR20 the view reads must be the record's own (a record whose ADR20 differs fails, every context otherwise equal)
    _v, fails = ctx.compute_contexts("STOP", [tr], {r.b.eid: r}, {"A": spy}, check_full=True)
    assert fails == []
    rA = dataclasses.replace(r, adr20=r.adr20 * 1.1)
    _v, fails = ctx.compute_contexts("STOP", [tr], {r.b.eid: rA}, {"A": spy}, check_full=True)
    assert len(fails) == 1 and fails[0][1].startswith("ADR20 from the view")


def test_a_close_proxy_fill_on_an_early_close_reads_no_after_hours_minute():
    cal = sessions(260, "2020-01-02")
    E = date(2020, 11, 27)
    assert E.isoformat() in fz.EARLY_CLOSE and fz.session_end_minute(E.isoformat()) == 210
    e = cal.index(E)

    def early(p):                                                                            # 09:30-13:00, then after-hours prints far lower
        reg = minutes_from_daily(p, p * 1.01, p * 0.99, p * 1.005, early=True)
        m = list(reg.minute) + list(range(210, 390))
        o = list(reg.o) + [p * 0.6] * 180
        return cb.minute_bars_from_lists(m, o, list(reg.h) + [p * 0.6] * 180, list(reg.l) + [p * 0.5] * 180, list(reg.c) + [p * 0.6] * 180, [1000.0] * 390)
    r, store, M, spy = unit_rec(n=e + 20, e=e, exit_lo=3, exit_hi=5, sess={0: early}, fill_minute=None, setup="breakout")
    assert r.fill_src == "close_proxy"
    tr = tr_of(r, "STOP", fill_minute=None, fill=float(r.mb.c[209]))
    v = ctx.make_view(r, "STOP", tr, spy)
    assert v.bound_m == 210 and int(v.minutes.minute.max()) == 209 and ctx.assert_view_dates(v, r) == []
    got = ctx.context_values("STOP", v)["C-S1"][0]
    reg_low = float(r.mb.l[r.mb.minute < 210].min())
    assert got == pytest.approx((tr.fill - reg_low) / (r.adr20 * tr.fill))
    assert reg_low > float(r.mb.l.min())                                                     # the after-hours low is lower: reading it would move C-S1
    _v, fails = ctx.compute_contexts("STOP", [tr], {r.b.eid: r}, {"A": spy}, check_full=True)
    assert fails == []
    # a full session's close proxy still reads to 16:00
    assert ctx.minute_bound("STOP", dataclasses.replace(tr, E="2020-11-25")) == 390


# ═════════════════════════════════════════════════════════════════════════════════════════════ the fixed maps, the labels, the intervals
def test_hw_maps_fixed_groups_and_hw_x_prime_at_apollos_cut():
    v = {"C-E1": [1.0, 2.0, 3.0, 4.0, None], "C-S1": [0.5, 1.5, None, None, 0.9], "C-X1": [0.03, 0.05, 0.06, 0.2, None]}
    e = ctx.hw_maps("ENTER", v, {"C-E1": ctx.median_cut(v["C-E1"])})
    assert len(e) == 1 and e[0].cut == 2.0 and list(e[0].rules([1.0, 3.0, None])) == [ctx.LIB_INDEX["ENTER"]["L8"], ctx.LIB_INDEX["ENTER"]["L1"], ctx.LIB_INDEX["ENTER"]["L8"]]
    s = ctx.hw_maps("STOP", v, {})
    assert s[0].cut == 1.0 and s[0].missing_left and list(s[0].rules([0.5, 1.5, None])) == [ctx.LIB_INDEX["STOP"][c] for c in ("S1-T", "S4-T", "S1-T")]
    x = {m.name: m for m in ctx.hw_maps("EXIT", v, {"C-X1": ctx.median_cut(v["C-X1"])})}
    assert set(x) == {"HW-X", "HW-X'"} and x["HW-X'"].cut == 0.0479
    assert list(x["HW-X'"].rules([0.0479, 0.048, 0.03])) == [ctx.LIB_INDEX["EXIT"][c] for c in ("M-4", "M-3", "M-4")]
    assert x["HW-X'"].missing_left is False                                                # the > side holds more 2020 defined rows here


def test_labels_on_the_printed_one_decimal_values_arm_by_arm_on_gains():
    assert ctx.context_helps(0.50, 0.40, 0.40) and not ctx.context_helps(0.4994, 0.40, 0.30) and not ctx.context_helps(0.50, 0.40, 0.401)
    assert ctx.context_helps(0.4996, 0.40, 0.30)                                            # 49.96% PRINTS 50.0%: the label follows the printout
    assert 0.50 - 0.40 < 0.1 + 1e-12 and ctx.context_helps(0.50, 0.40, 0.40)                # exactly 10.0 points passes, on the printed values
    levels_only = {"kprice": (0.21, 0.21, 0.30, 0.30)}
    assert ctx.beats_chance(0.55, 0.40, levels_only)                                       # a flat level arm: the gain is the gain
    timing = {"kprice": (0.21, 0.21, 0.30, 0.30), "shared": (0.12, 0.03, 0.10, 0.04)}
    assert not ctx.beats_chance(0.55, 0.40, timing)                                        # the timing arm shows 9 of the 15 points: FAILS
    c2_only = {"kprice": (0.21, 0.21, 0.40, 0.30)}
    assert not ctx.beats_chance(0.55, 0.40, c2_only)                                       # the procedure on random buyers gains 10 too: FAILS
    assert not ctx.beats_chance(0.55, 0.40, {"kprice": (math.nan, 0.2, 0.3, 0.3)}) and not ctx.beats_chance(0.55, 0.40, {})
    assert ctx.summary_label(True, True) == "context map" and ctx.summary_label(True, False) == "context helps, chance too"
    assert ctx.summary_label(False, True) == "no context gain"
    assert ctx.net_gain(0.55, 0.40, 0.12, 0.03) == pytest.approx(6.0) and ctx.sign_of(0.0004) == "0" and ctx.sign_of(-0.01) == "−" and ctx.sign_of(0.01) == "+"


def hand_line(share, shuf=None, c1=None, c2=None):
    """A hand-built ENTER line for labels_for: {block: value} per field, every arm the same unless given per arm."""
    arms = ctx.ARMS["ENTER"]
    per = lambda x: {a: dict(x[a]) if (x and a in x) else {b: 0.20 for b in ctx.BLOCKS} for a in arms}   # noqa: E731
    return dict(share=dict(share), shuf={b: {"mean": (shuf or {}).get(b, 0.40)} for b in ctx.LABEL_BLOCKS}, c1=per(c1), c2=per(c2))


def test_labels_for_needs_both_blocks_and_follows_the_maps_own_shuf():
    B = hand_line({"2020": 0.40, "2021-22": 0.40, "untouched": 0.40}, shuf={"2020": 0.0, "2021-22": 0.0})
    L = hand_line({"2020": 0.55, "2021-22": 0.55, "untouched": 0.5})
    ok = ctx.labels_for(L, B, "ENTER")
    assert ok["helps"] and ok["chance"] and ok["summary"] == "context map" and ok["2020"] == ok["2021-22"] == {"helps": True, "chance": True}
    # (a) 2020 passes, 2021-22 gains 9.9 points: context does NOT help (each label on BOTH blocks)
    a = ctx.labels_for(hand_line({"2020": 0.55, "2021-22": 0.499, "untouched": 0.5}), B, "ENTER")
    assert a["2020"]["helps"] and not a["2021-22"]["helps"] and not a["helps"] and not a["chance"] and a["summary"] == "no context gain"
    # (b) helps on both, but one arm's net gain on 2021-22 is 9.9: chance does NOT beat (both blocks)
    b = ctx.labels_for(hand_line({"2020": 0.55, "2021-22": 0.55, "untouched": 0.5}, c1={"kprice": {"2020": 0.20, "2021-22": 0.251, "untouched": 0.2}}), B, "ENTER")
    assert b["helps"] and b["2020"]["chance"] and not b["2021-22"]["chance"] and not b["chance"] and b["summary"] == "context helps, chance too"
    # (c) the SHUF a label reads is the MAP's own (L's), never BEST's: L's SHUF 50.0% on 2020 kills the 15-point gain there
    c = ctx.labels_for(hand_line({"2020": 0.55, "2021-22": 0.55, "untouched": 0.5}, shuf={"2020": 0.50, "2021-22": 0.40}), B, "ENTER")
    assert not c["2020"]["helps"] and c["2021-22"]["helps"] and not c["helps"]
    # (d) a net gain of EXACTLY 10.0 points passes beats_chance on (c-1) and on (c-2); 9.9 fails on either
    assert ctx.beats_chance(0.55, 0.40, {"kprice": (0.25, 0.20, 0.20, 0.20)}) and ctx.beats_chance(0.55, 0.40, {"kprice": (0.20, 0.20, 0.25, 0.20)})
    assert not ctx.beats_chance(0.55, 0.40, {"kprice": (0.251, 0.20, 0.20, 0.20)}) and not ctx.beats_chance(0.55, 0.40, {"kprice": (0.20, 0.20, 0.251, 0.20)})


def test_the_shuf_percentile_is_the_mid_rank_and_each_block_has_its_own_permutation_stream(monkeypatch):
    monkeypatch.setattr(ctx, "PERMS", 8)
    se, vals, data, G = toy_data()
    data = copy.deepcopy(data)
    for b, x in data["X"]["ENTER"]["bracket"].items():
        x[:] = True                                                                         # every map, real or permuted, closes on every trade
    L = ctx.evaluate_line(ctx.Line("MAP", "search", cols=tuple(range(7))), "ENTER", "bracket", se, G, vals, data)
    assert L["share"]["2020"] == 1.0 and L["shuf"]["2020"]["pctile"] == 0.5 and L["shuf"]["2021-22"]["pctile"] == 0.5   # all ties: below 0 + half of 8
    # the permutation key carries the block: equal n, same index, different blocks -> different streams
    assert not np.array_equal(ctx.shuffled(40, "ENTER", "2020", 0), ctx.shuffled(40, "ENTER", "2021-22", 0))
    assert ctx.PERM_KEY.format(decision="ENTER", block="2020", p=0) != ctx.PERM_KEY.format(decision="ENTER", block="2021-22", p=0)


def toy_report_world():
    """An ENTER decision whose map is forced (C-E2 splits it; C-E1 has no value, C-E3 one value): 2020 group C-E2 = 0 closes on L9 (not
    tier 1) and partly L1, group C-E2 = 1 on L8; 2021-22 closes on L2 (the 2021-22 oracle, never 2020's); brackets 20 vs 10 minutes."""
    rng = np.random.default_rng(4)
    lib = ctx.LIB["ENTER"]
    I = ctx.LIB_INDEX["ENTER"]
    ns = {"2020": 40, "2021-22": 30, "untouched": 6}
    P = {"ENTER": {"scorable": {}, "beside": {b: [] for b in ctx.BLOCKS}}}
    vals_dec, X, eid = {}, {}, 0
    for b, n in ns.items():
        trs, x = [], np.zeros((n, len(lib)), dtype=bool)
        for i in range(n):
            eid += 1
            e2 = 0.0 if i < n // 2 else 1.0
            trs.append(ctx.TradeRow(eid=eid, sym=f"S{eid}", E="2020-03-02", block=b, dated=False, decision="ENTER", flat_m=30, first_m=50 if e2 == 0.0 else 40))
            vals_dec[eid] = {"C-E1": (None, "no_minutes"), "C-E2": (e2, ""), "C-E3": (0.0, "")}
            if b == "2021-22":
                x[i, I["L2"]] = True
                x[i, I["L1"]] = i % 3 == 0
            elif e2 == 0.0:
                x[i, I["L9"]] = True
                x[i, I["L1"]] = i < 12
            else:
                x[i, I["L8"]] = True
                x[i, I["L9"]] = i < n // 2 + 5
        P["ENTER"]["scorable"][b] = trs
        X[b] = x
    for b in ctx.BLOCKS:
        X[f"{b}|beside"] = np.zeros((0, len(lib)), dtype=bool)
    v20 = {c: [vals_dec[t.eid][c][0] for t in P["ENTER"]["scorable"]["2020"]] for c in ctx.CIDS["ENTER"]}
    cuts = ctx.cut_values("ENTER", v20)
    kept, _d = ctx.dedupe_splits(ctx.make_splits("ENTER", v20, cuts), v20)
    se = ctx.Search("ENTER", kept, v20, 5)
    keys = list(X)
    data = dict(X={"ENTER": {"bracket": X}},
                chance1={"ENTER": {"bracket": {a: {k: rng.random((X[k].shape[0], len(lib))) for k in keys} for a in ctx.ARMS["ENTER"]}}},
                draws2={"ENTER": {"bracket": {a: {k: rng.random((ctx.DRAWS, X[k].shape[0], len(lib))) < 0.3 for k in keys} for a in ctx.ARMS["ENTER"]}}})
    d = dict(search=se, m=5, v20=v20, medians={}, cuts=cuts)
    return P, vals_dec, d, data


def test_the_template_oracle_union_panel_flag_and_map_t1_on_a_forced_map(monkeypatch):
    monkeypatch.setattr(ctx, "PERMS", 4)
    monkeypatch.setattr(ctx, "BOOTS", 30)
    P, vals_dec, d, data = toy_report_world()
    say, rows = rp.Say(), dict(maps=[], groups=[], controls=[])
    out = ctx.report_decision_tol(say, "ENTER", "bracket", P, vals_dec, d, data, rows)
    I, T1 = ctx.LIB_INDEX["ENTER"], {ctx.LIB_INDEX["ENTER"][c] for c in ctx.TIER1["ENTER"]}
    Lm = out["MAP"][0]
    assert [ctx.rule_name("ENTER", r_) for r_ in Lm["fit"]["rules"]] == ["L9", "L8"] and Lm["share"]["2020"] == 1.0
    assert ctx.rule_name("ENTER", out["BEST"][0]["fit"]["rules"][0]) == "L9"                         # the full library's BEST is not tier 1
    txt = "\n".join(say.lines)
    # ORACLE-1 = the best single rule ON 2021-22 (L2, never fit), not 2020's best (L9)
    orc = next(ln for ln in say.lines if ln.strip().startswith("ORACLE-1"))
    assert "(L2)" in orc and "100.0%" in orc
    # UNION: gap closed = (MAP - BEST) / (UNION - BEST): 2020 (100 - 62.5) / (100 - 62.5) = 100.0%
    un = next(ln for ln in say.lines if ln.strip().startswith("UNION"))
    assert "100.0%; gap closed 100.0%" in un.split("|")[1]
    # the panel-artefact flag at EXACTLY 2x (and 0.5x): brackets 20 vs 10 minutes
    flags = [ln for ln in say.lines if "PANEL ARTEFACT?" in ln]
    assert len(flags) == 2 and "bracket 20 vs the rest 10" in flags[0] and "bracket 10 vs the rest 20" in flags[1]
    # MAP-T1: searched within the tier-1 columns only, labelled against BEST-T1 (L8), never the full BEST (L9)
    LT1, lb = out["MAP-T1"]
    assert set(LT1["fit"]["rules"]) <= T1 and [ctx.rule_name("ENTER", r_) for r_ in LT1["fit"]["rules"]] == ["L1", "L8"]
    mrow = next(r_ for r_ in rows["maps"] if r_["line"] == "MAP-T1")
    assert mrow["best"] == "L8" and mrow["best_2020"] == pytest.approx(0.5)
    assert "beside MAP-T1" in txt and "vs its BEST 50.0%" in next(ln for ln in say.lines if "beside MAP-T1" in ln)


def test_the_paired_interval_holds_the_map_fixed_and_mcnemar():
    diff = np.array([1, 0, 0, -1, 1, 1, 0, 0, 0, 1], dtype=float)
    m, lo, hi = ctx.paired_interval(diff, "EXIT", "2020", "MAP-BEST", boots=300)
    assert m == pytest.approx(0.3) and lo <= m <= hi
    ms = [diff[fz.rng_for(ctx.BOOT_KEY.format(decision="EXIT", block="2020", line="MAP-BEST", r=r_)).integers(0, 10, 10)].mean() for r_ in range(300)]
    assert lo == pytest.approx(np.percentile(ms, 2.5)) and hi == pytest.approx(np.percentile(ms, 97.5))
    assert ctx.paired_interval(diff, "EXIT", "2020", "MAP-BEST", boots=300) == (m, lo, hi)  # re-scores the SAME per-trade vector: no re-search
    a = np.array([1, 1, 0, 0, 1], dtype=bool)
    b = np.array([1, 0, 0, 1, 0], dtype=bool)
    x, y, p = ctx.mcnemar(a, b)
    assert (x, y) == (2, 1) and p == pytest.approx(1.0)


# ═════════════════════════════════════════════════════════════════════════════════════════════ guards
FROZEN_NAMES = ("mix", "fz", "rev", "rp", "R", "cb", "H")


def test_module_scan_float_id_and_no_frozen_module_mutated():
    # source-pin-ok: D3 (never float() of a numpy array) and guard 11 (IdCache only — no id()-keyed cache) are properties of the module's own source; the paths that would trip either run only on the real --run, so no behaviour test can show them absent beforehand
    src = open(MOD_PATH, encoding="utf-8").read()
    tree = ast.parse(src)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("float", "id"):
            bad.append(f"l.{node.lineno} bare {node.func.id}(")
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            for tgt in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id in FROZEN_NAMES:
                    bad.append(f"l.{node.lineno} assigns {tgt.value.id}.{tgt.attr} (a frozen module is never mutated)")
    for i, ln in enumerate(src.splitlines(), 1):
        if re.search(r"(?<![\w.])id\(", ln) and not ln.lstrip().startswith("#"):
            bad.append(f"l.{i} id(")
    assert not bad, bad
    planted = ast.parse("x = float(np.zeros(1))\ny = id(x)\nfz.SEED = 1\n")
    hits = [n for n in ast.walk(planted) if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("float", "id"))
            or (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Attribute))]
    assert len(hits) == 3


def test_module_scan_every_reused_helper_gets_this_reads_path_d4():
    # source-pin-ok: D4 — that every reused freeze / dry-run / ledger / pins / output helper is called with THIS read's path (or replaced) is a property of the call sites in the source; a bare call would bind to the RULE-MIX files only on the real --run, which no test may execute beforehand
    src = open(MOD_PATH, encoding="utf-8").read()
    tree = ast.parse(src)
    need = {"doc_body_text": 1, "pin_under_marker": 2, "store_freeze_body": 2, "freeze_body_text": 3, "freeze_state": 2, "ledger_append": 3, "ledger_verify": 1,
            "dry_run_complete": 1, "pins": 1, "fit_events": 1, "fit_event_pins": 1, "fit_events_undisclosed": 2, "doc_line_of": 2, "freeze_missing": 2,
            "doc_body_sha": 1, "chosen_lines": 1}
    banned_fz = {"stage_outputs", "any_stage_output", "reset_fits", "reset_artifacts", "print_pins", "run_check", "write_rows", "gate_ohlc", "gate_level_order",
                 "gate_c_implies_h", "g8_run", "write_chosen", "read_chosen", "freeze_record_now", "freeze_records_agree", "run_fit_stage", "dry_run", "main"}
    banned_mix = {"tag_lock", "mix_stage_outputs", "mix_any_stage_output", "mix_dry_run_complete", "write_out", "g8_mix", "dry_run", "tag_stages", "write_tables",
                  "print_pins", "reset_tag", "reset_artifacts", "run_tag", "main", "gate_i", "gate_ii", "gate_iii", "gate_viii_enter", "gate_viii_stop",
                  "gate_viii_exit", "gate_viii_c", "gate_x"}
    lines = src.splitlines()
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            mod, name = node.func.value.id, node.func.attr
            if mod == "fz" and name in banned_fz:
                bad.append(f"l.{node.lineno} fz.{name} (bound to the intraday read's files)")
            if mod == "fz" and name in need and len(node.args) + len(node.keywords) < need[name]:
                bad.append(f"l.{node.lineno} fz.{name} called without its path argument")
            if mod == "mix" and name in banned_mix:
                bad.append(f"l.{node.lineno} mix.{name} (bound to the rule-mix read's files)")
            if mod == "mix" and name == "mix_pins" and "mix-path-ok" not in lines[node.lineno - 1]:
                bad.append(f"l.{node.lineno} mix.mix_pins without its reviewed mix-path-ok note")
            if mod == "mix" and name == "pins_missing_by_name" and not (node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "DOC"):
                bad.append(f"l.{node.lineno} mix.pins_missing_by_name not on THIS doc")
    for i, ln in enumerate(lines, 1):
        if re.search(r"\b(mix|fz)\.(DOC|P_DRY|P_TAG|P_PINS|LEDGER|OUT_DIR|STOPPED|FREEZE_BODIES|TAG_EVENTS|DRY_SIDE|FROZEN_DIR|P_FIT|P_CHECK)\b", ln) and "mix-path-ok" not in ln:
            bad.append(f"l.{i} reads another read's path constant without its reviewed mix-path-ok note: {ln.strip()[:90]}")
    assert not bad, bad
    # the scan bites: a planted bare ledger_append, a planted mix.tag_lock and a path constant without its note are caught
    planted = ast.parse("fz.ledger_append('run', p)\nmix.tag_lock()\n")
    hits = [n for n in ast.walk(planted) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and ((n.func.attr in need and len(n.args) < need[n.func.attr]) or n.func.attr in banned_mix)]
    assert len(hits) == 2 and re.search(r"\b(mix|fz)\.(DOC|LEDGER)\b", "x = mix.LEDGER")


def test_the_test_file_carries_no_absolute_machine_path():
    # source-pin-ok: the shallow-clone rule (CI runs elsewhere) is a property of this test file's own text, not of any behaviour
    text = open(os.path.abspath(__file__), encoding="utf-8").read()
    assert ("/" + "Users/") not in text and ("/" + "home/") not in text


def write_doc(path, body_lines: list, tail_lines: list):
    path.write_text("\n".join(body_lines) + "\n<!-- FREEZE -->\n" + "\n".join(tail_lines) + "\n")


def lock_env(tmp_path, monkeypatch):
    doc = tmp_path / "doc.md"
    body = ["# synthetic context-rules registration", "the fixed contexts"]
    write_doc(doc, body, [])
    paths = dict(DOC=str(doc), P_DRY=str(tmp_path / "ctx_dry.txt"), P_RUN=str(tmp_path / "ctx_run.txt"), P_PINS=str(tmp_path / "ctx_pins.txt"),
                 LEDGER=str(tmp_path / "ctx_ledger.tsv"), STOPPED=str(tmp_path / "ctx.STOPPED.txt"), FREEZE_BODIES=str(tmp_path / "fb"),
                 RUN_EVENTS=str(tmp_path / "ev"), OUT_DIR=str(tmp_path / "out"), FROZEN_DIR=str(tmp_path / "frozen"), DRY_SIDE=str(tmp_path / "side"))
    os.makedirs(paths["FROZEN_DIR"])
    for k, v in paths.items():
        monkeypatch.setattr(ctx, k, v)
    monkeypatch.setattr(ctx, "carried_pins", lambda: {"mix_carried_example": "a" * 64})
    files = {}
    for k in ctx.MIX_FILES:
        p = tmp_path / f"in_{k}.txt"
        p.write_text(k)
        files[k] = str(p)
    monkeypatch.setattr(ctx, "MIX_FILES", files)
    return doc, body


def test_the_lock_refuses_when_only_the_rule_mix_dry_run_exists_d4_and_the_freeze(tmp_path, monkeypatch):
    doc, body = lock_env(tmp_path, monkeypatch)
    bad = ctx.ctx_lock()
    assert any("THIS read's dry run has not COMPLETED" in x for x in bad) and any("freeze lock" in x for x in bad)
    # the RULE-MIX dry run (its own header, a 0-mismatch RESULT, DRY RUN COMPLETE) copied over this read's: refused
    (tmp_path / "ctx_dry.txt").write_text(f"{mix.DRY_HEADER}: the rule-mix dry run\n## RESULT: 9 claims, 9 OK, 0 MISMATCH; 0 notes\n- ctx_const_EXIT_floor_m: 34\n"
                                          "DRY RUN COMPLETE: x\n")
    assert mix.mix_dry_run_complete(str(tmp_path / "ctx_dry.txt")) and not ctx.ctx_dry_run_complete(str(tmp_path / "ctx_dry.txt"))
    h = fz.store_freeze_body(str(doc), str(tmp_path / "fb"))
    write_doc(doc, body, [f"- {k}: {v}" for k, v in ctx.ctx_pins().items()])
    assert any("THIS read's dry run has not COMPLETED" in x for x in ctx.ctx_lock())
    # THIS read's dry run, the pins (incl. its constants) pasted by name: the lock opens
    dry = f"{ctx.DRY_HEADER}: synthetic\n## RESULT: 3 claims, 3 OK, 0 MISMATCH; 0 notes\n- ctx_const_EXIT_floor_m: 34\n- ctx_const_EXIT_C-X1_T1: 0.05785964566155742\nDRY RUN COMPLETE: x\n"
    (tmp_path / "ctx_dry.txt").write_text(dry)
    p = ctx.ctx_pins()
    assert p["doc_body"] == h and p["ctx_module"] == ctx.sha(MOD_PATH) and p["ctx_const_EXIT_C-X1_T1"] == "0.05785964566155742" and p["ctx_tests"] == ctx.sha(os.path.abspath(__file__))
    write_doc(doc, body, [f"- {k}: {v}" for k, v in p.items()])
    assert ctx.ctx_lock() == []
    # a constant under the marker that is not the dry run's (checked BY NAME): refused
    lines = [f"- {k}: {v}" if k != "ctx_const_EXIT_floor_m" else "- ctx_const_EXIT_floor_m: 35\n- note: 34" for k, v in p.items()]
    write_doc(doc, body, lines)
    assert any("checked by name" in x and "ctx_const_EXIT_floor_m" in x for x in ctx.ctx_lock())
    write_doc(doc, body, [f"- {k}: {v}" for k, v in p.items()])
    # an edit above the marker after the freeze: refused
    write_doc(doc, body + ["a late edit"], [f"- {k}: {v}" for k, v in p.items()])
    assert any("freeze lock" in x or "pins not under" in x for x in ctx.ctx_lock())
    write_doc(doc, body, [f"- {k}: {v}" for k, v in p.items()])
    assert ctx.ctx_lock() == []
    # a run output on disk refuses; a STOPPED file refuses; a changed ledger row refuses
    (tmp_path / "ctx.STOPPED.txt").write_text("STOPPED: x\n")
    assert any("already on disk" in x for x in ctx.ctx_lock())
    os.remove(tmp_path / "ctx.STOPPED.txt")
    lp = tmp_path / "x.txt"
    lp.write_text("a\n")
    fz.ledger_append("run", str(lp), str(tmp_path / "ctx_ledger.tsv"))
    write_doc(doc, body, [f"- {k}: {v}" for k, v in ctx.ctx_pins().items()])        # the ledger's own pin re-pasted: the lock opens again
    assert ctx.ctx_lock() == []
    lp.write_text("b\n")                                                            # a ledgered file changed on disk: ONLY the verify branch refuses
    bad = ctx.ctx_lock()
    assert len(bad) == 1 and bad[0].startswith("the ledger does not match the disk"), bad


def test_every_claim_anchor_resolves_in_the_registered_fixture_and_a_mismatch_stops():
    for key, (anchor, _v, _lab) in list(ctx.EXPECT.items()) + list(ctx.NOTES.items()):
        assert fz.doc_line_of(anchor, FIXTURE_DOC), key
    say = rp.Say()
    c = ctx.CtxClaims(say, doc=FIXTURE_DOC)
    a = ctx.EXPECT["n_trees"][0]
    assert c(a, "x", "101 / 295 / 449", "101 / 295 / 449") and not c.bad
    c(a, "y", "101", "100")
    c("an anchor that is not in the doc", "z", "1", "1")
    assert len(c.bad) == 2 and "anchor not found" in c.bad[1][1]
    c(a, "n", "9", "9", note=True)
    assert len(c.notes) == 1
    # the fixture IS the registered body (REGISTERED, NOT FROZEN): one marker line, the four questions decided
    raw = open(FIXTURE_DOC, "rb").read()
    assert len(fz.marker_spans(raw)) == 1 and b"REGISTERED, NOT FROZEN" in raw


def test_the_readings_and_the_contexts_constants():
    # source-pin-ok: C1-C21 are the module docstring's fixed readings, which the dry run prints verbatim (readings_lines); that the docstring carries all 21 is a property of the text itself, and the e2e dry run asserts the printed C21
    lines = ctx.readings_lines()
    assert len(lines) == 21 and all(ln.strip().startswith(f"C{i}") for i, ln in enumerate(lines, 1))
    assert "trail_speed_source" not in ctx.MIX_FILES and os.path.exists(ctx.TRAIL_SPEED_SOURCE)          # live code is read by a claim, never pinned
    assert ctx.CIDS == {"ENTER": ("C-E1", "C-E2", "C-E3"), "STOP": ("C-S1", "C-S2", "C-S3"), "EXIT": ("C-X1", "C-X2", "C-X3", "C-X4")}
    for d in ctx.DECISIONS:
        for c in ctx.CONTEXTS[d]:
            assert re.search(r"l\.\d{4}", c.cite), c
            assert c.kind in ("cont", "bin")
    assert [c.cid for d in ctx.DECISIONS for c in ctx.CONTEXTS[d] if "OUR READING" in c.name] == ["C-E3", "C-S3", "C-X4"]
    assert ctx.TIER1 == {"ENTER": ("L1", "L8", "L2", "L7", "L3"), "STOP": ("S1-T",), "EXIT": ("M-1", "M-2", "M-3", "M-4", "M-5", "M-9", "M-6", "M-2s", "M-11")}
    assert ctx.HWX_PRIME_CUT == 0.0479 and ctx.C_S1_CAP == 1.0 and ctx.MARGIN == 0.10 and ctx.PERMS == 200 and ctx.BOOTS == 2000 and ctx.DRAWS == 200


# ═════════════════════════════════════════════════════════════════════════════════════════════ the synthetic world (end to end)
class SynthStore(fz.MinuteStore):
    """Minutes built from the world's daily bars on demand (the opening five minutes' volume varies by (date, ticker): C-E1 has a spread);
    `empty` pairs have none; every pair built counts as one read."""

    def __init__(self, daily: dict, cal: list, empty: set):
        super().__init__({}, {})
        self.daily, self.cal, self.empty = daily, cal, set(empty)
        self.pos = {d.isoformat(): i for i, d in enumerate(cal)}

    def state(self, d, tk, b=None):
        if (d, tk) in self.empty:
            return "empty/SYN"
        return "ok/SYN" if (tk in self.daily and d in self.pos) else "missing"

    def _build(self, d, tk):
        if (d, tk) in self.empty or tk not in self.daily or d not in self.pos:
            return None
        i = self.pos[d]
        o, h, l, c, _v = self.daily[tk]
        boost = 1.0 + (zlib.crc32(f"{d}|{tk}".encode()) % 9)
        return minutes_from_daily(float(o[i]), float(h[i]), float(l[i]), float(c[i]), early=d in fz.EARLY_CLOSE, after_hours=d in fz.EARLY_CLOSE, open_boost=boost)

    def _get(self, d, tk):
        self.seal(d)
        if (d, tk) not in self.cache:
            self.cache[(d, tk)] = self._build(d, tk)
            self.reads["SYN"] += 1
        return self.cache[(d, tk)]

    def preload(self, pairs):
        c = Counter()
        for p in pairs:
            self._get(p[0], p[1])
            c[self.state(p[0], p[1]).split("/")[0]] += 1
        return c

    def get(self, d, tk, b=None):
        return self._get(d, tk)


def make_D(daily: dict, cal: list, idx, drops: "dict | None" = None):
    """An export over the sessions `idx` of the world calendar; `drops` = {ticker: {world indices}} the export lacks (an SPY gap, a missing D)."""
    idx = list(idx)
    pos = {w: k for k, w in enumerate(idx)}
    tks = sorted(daily)
    o, h, l, c, v, ci, start, stop = [], [], [], [], [], [], [], []
    n0 = 0
    for tk in tks:
        oo, hh, ll, cc, vv = daily[tk]
        keep = [w for w in idx if w not in (drops or {}).get(tk, set())]
        o.append(oo[keep]); h.append(hh[keep]); l.append(ll[keep]); c.append(cc[keep]); v.append(vv[keep])
        ci.append(np.array([pos[w] for w in keep], dtype=np.int32))
        start.append(n0)
        n0 += len(keep)
        stop.append(n0)
    return R.Daily(tks, np.array(start), np.array(stop), np.concatenate(ci), np.concatenate(o), np.concatenate(h), np.concatenate(l), np.concatenate(c),
                   np.concatenate(v), [cal[i] for i in idx], {t: k for k, t in enumerate(tks)}, 0, 0)


def build_world():
    """The rule-mix tests' world (two eras on one calendar, era B on its OWN calendar with a session dropped, 60 tickers + QQQ / SPY + designed
    names, buys in every set) plus this read's shapes: a bracket opening at 09:32, one flat at 09:30, a buy whose stock has no bar on D (NOD),
    an SPY gap in era A's export (2020-05-05), opening volume that varies by (date, ticker)."""
    cal = weekday_cal("2019-01-02", "2024-06-28")
    CI = {d.isoformat(): i for i, d in enumerate(cal)}
    n = len(cal)
    tks = [f"T{k:02d}" for k in range(60)] + ["QQQ", "SPY", "OPA", "OPB", "NOD"]
    daily = {tk: daily_walk(n, 20.0 + 1.5 * k, 100 + k) for k, tk in enumerate(tks)}
    daily["SPY"] = daily_walk(n, 300.0, 7, trend=0.0004)
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
    iA, iB = CI["2022-06-30"] + 1, CI["2021-09-27"]
    drop_B = CI["2022-08-03"]
    buys, frames = [], []
    eid = [0]

    def add(sym, E, kind="und", flat="10:05", first="10:40", exit_off=(3, 5), flicker=False, window=True, p_ctx="in", still=False, f_ctx="in"):
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
    for k, E in enumerate(["2020-02-05", "2020-03-04", "2020-04-06", "2020-05-06", "2020-06-08", "2020-07-08", "2020-08-12", "2020-09-23", "2020-10-28",
                           "2020-02-24", "2020-03-25", "2020-05-27", "2020-07-21", "2020-08-26", "2020-10-07"]):
        add(f"T{23 + k:02d}", E, kind="bo", flat=clocks[k % len(clocks)][0], first=clocks[k % len(clocks)][1], exit_off=((2, 4), (4, 7), (1, 1), (3, 5), (6, 9), (2, 3))[k % 6])
    add("T33", "2020-11-18", exit_off=(5, 9))
    add("T34", "2020-06-22", exit_off=(2, 4))
    add("T35", "2020-08-05", exit_off=(4, 6))                                          # a missing minute day inside the hold
    fsl = add("FSL", "2020-06-29", flat="10:05", first="10:40", exit_off=(10, 11))
    add("LW", "2020-08-03", exit_off=(2, 3))                                           # a winner ...
    add("LW", "2020-09-08", exit_off=(2, 3))                                           # ... and a loser on one name
    add("T16", "2020-10-05", exit_off=(0, 0))                                          # a buy-day sell: control (a) no_room
    add("T17", "2020-10-20", exit_off=(2, 4), window=False)
    add("T18", "2020-03-23", exit_off=(3, 25))                                         # a window over 20 sessions
    opa = add("OPA", "2020-06-10", flat="09:32", first="09:50", exit_off=(1, 1))       # a bracket opening before 09:35; a 1-session window
    opb = add("OPB", "2020-07-27", flat="09:30", first="09:45", exit_off=(1, 2))       # a bracket flat at 09:30 (C-E1 MISSING)
    nod = add("NOD", "2020-09-21", flat="10:05", first="10:40", exit_off=(2, 3))       # no stock bar on D (every context MISSING)
    for k, E in enumerate(["2021-02-01", "2021-03-15", "2021-05-03", "2021-08-02", "2021-11-01", "2022-02-01", "2022-03-01"]):
        add(f"T{36 + k:02d}", E, flat=clocks[k % 4][0], first=clocks[k % 4][1], exit_off=((2, 3), (1, 1), (4, 6), (3, 3), (6, 10), (2, 2), (5, 5))[k])
    eraB = add("T43", "2022-05-02", flat="10:05", first="10:40", exit_off=(5, 5))      # era B
    sane = [("10:05", "10:40"), ("10:30", "11:20"), ("09:40", "09:50"), ("11:00", "12:30")]
    for k, E in enumerate([d.isoformat() for d in weekday_cal("2021-02-08", "2022-03-18")[::9][:32]]):
        add(f"T{k:02d}", E, flat=sane[k % 4][0], first=sane[k % 4][1], exit_off=((1, 2), (2, 3), (3, 3), (2, 5))[k % 4])
    add("T45", "2021-06-01", flicker=True, flat="10:05", first="10:40")
    for k, E in enumerate(["2021-02-08", "2021-06-14", "2022-01-10"]):
        add(f"T{47 + k:02d}", E, kind="bo", flat="10:05", first="10:40", exit_off=((2, 4), (1, 3), (3, 3))[k])
    for k, E in enumerate(["2019-10-03", "2019-10-10", "2019-11-01", "2019-11-15"]):
        add(f"T{54 + k:02d}", E, flat="10:05", first="10:40", exit_off=((1, 1), (10, 14), (3, 3), (8, 8))[k])
    add("T02", "2019-10-22", flicker=True, flat="09:40", first="09:55")
    add("T04", "2023-06-01", kind="bo", window=False, exit_off=(6, 9))
    add("T06", "2023-12-01", kind="bo", window=False, still=True)                   # still held: the offsets serialize as float strings ('3.0')
    add("T07", "2023-12-04", kind="bo", window=False, still=True)
    add("T09", "2023-05-19", flat="09:42", first="09:51", exit_off=(2, 8))
    eraB2 = add("T19", "2022-08-01", exit_off=(3, 5))                                  # era B: 2022-08-03 is not on its OWN calendar
    rev.index_calendar(buys, [d.isoformat() for d in cal])
    S = rev.build_sets(buys)
    I = fz.intra_sets(S)
    mis = {}
    E_ = fz.enter_sets(I, S, mis)
    rows = [dict(idx=i, frame_id=f"f{i}", vid="v", date=d, ctx=c_, clock=clk, symbols=(s if shows else ""), blip_filled="") for i, (d, s, c_, clk, shows) in enumerate(frames)]
    sn = pd.DataFrame(rows)
    C = dict(buys=buys, S=S, I=I, E=E_, mis=mis, sn=sn, cal=[d.isoformat() for d in cal], CI=CI)
    empty = {("2020-06-22", "T34"), (cal[CI["2020-08-05"] + 2].isoformat(), "T35")}
    sight = rev.Sightings.build(sn)
    drops_A = {"SPY": {CI["2020-05-05"]}, "NOD": {CI["2020-09-18"]}}

    def make_M():
        DA_, DB_ = make_D(daily, cal, range(0, iA), drops_A), make_D(daily, cal, [i for i in range(iB, n) if i != drop_B])
        cal_u, map_b = H.unify_calendars(DA_.cal, DB_.cal)
        return dict(DA=DA_, DB=DB_, Ds={"A": DA_, "B": DB_}, cal_u=[d.isoformat() for d in cal_u], map_b=map_b, px=None, guards={"A": {}, "B": {}}, done={}, files={},
                    store=SynthStore(daily, cal, empty), sight=sight, last_seen=fz.last_seen_map(sight))
    return dict(C=C, make_M=make_M, cal=cal, CI=CI, daily=daily, fsl=fsl, eraB=eraB, eraB2=eraB2, opa=opa, opb=opb, nod=nod, byeid={b.eid: b for b in buys})


def frozen_tag(world, out_dir):
    """The rule-mix TAG's scoring on the world, line for line as the frozen `tag_stages` runs it (its records, the replayed draw stream,
    R12's returning windows, every STOP / EXIT record tagged), then the FROZEN `write_tables` writes the tag files in their real
    serialization; the known answers (G2 / G5) from the frozen summaries."""
    C, M = world["C"], world["make_M"]()
    store, sight, guard = M["store"], M["sight"], fz.BarGuard(None)
    store.forbid = frozenset()
    cs = fz.collision_summary(C, M.get("last_seen"))
    eb = mix.enter_blocks(C)
    ER, SR, _de, _ds, _cc = mix.build_records(C, M, store, guard)
    has_mb = lambda b: b.eid in ER and ER[b.eid].mb is not None                       # noqa: E731
    orders = mix.enter_draw_orders(C, cs, has_mb)
    draws = mix.replay_draws(orders)
    scored = {}
    for stream, groups in orders.items():
        for _g, eids in groups:
            for e_ in eids:
                scored[(stream, e_)] = mix.enter_one(ER[e_], draws[(stream, e_)], stream)
    for blk, spec in eb.items():
        stream = mix.stream_of_block(blk)
        for b in spec["tagged"] + [x for bs in spec["beside"].values() for x in bs]:
            r = ER.get(b.eid)
            if r is None or r.mb is None or (stream, b.eid) in scored or not mix.clocks_ok(b):
                continue
            u = fz.rng_for(mix.K1_KEY.format(eid=b.eid)).integers(0, 390, size=fz.RANDOM_LEVELS)
            scored[(stream, b.eid)] = mix.enter_one(r, u, stream)
    se = {}
    for e_, r in SR.items():
        se[e_] = mix.tag_se(r, M, store, sight)
        se[e_]["tagged"] = not se[e_]["status"]
    for e in scored.values():
        e["tag"] = mix.greedy_tag(e["real"], mix.LIB_CODES["ENTER"])
        e["etag"] = mix.earliest_tag(e["real"], e["times"], mix.LIB_CODES["ENTER"])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mix, "OUT_DIR", str(out_dir))
        mp.setattr(mix, "LEDGER", str(out_dir / "mix_ledger.tsv"))
        mix.write_tables(rp.Say(), C, eb, ER, scored, se, store)
    # the known answers, from the FROZEN summaries on the frozen tag's own objects
    known_best, known_union, known_g5 = {}, {}, {}
    for dec in ctx.DECISIONS:
        per = {}
        for blk in ctx.BLOCKS:
            if dec == "ENTER":
                items = [scored[(mix.stream_of_block(blk), b.eid)] for b in eb[blk]["tagged"] if (mix.stream_of_block(blk), b.eid) in scored]
                per[blk] = ("E", mix.summarize_enter(items), items)
            else:
                ts = [se[b.eid] for bs in mix.se_blocks(C)[blk].values() for b in bs if b.eid in se]
                base = [t for t in ts if t.get("tagged") and t["room"] and (dec == "EXIT" or t["loser"])]
                per[blk] = ("S", mix.summarize_se(base, dec), base)
        lib = mix.LIB_CODES[dec]
        s20 = per["2020"][1]
        best = lib[int(np.argmax([s20["rules"][c]["ex"] for c in lib]))]
        known_best[dec] = (best, {b: ctx.share(per[b][1]["rules"][best]["ex"], per[b][1]["n"]) for b in ctx.LABEL_BLOCKS})
        known_union[dec] = {b: ctx.share(per[b][1]["union"], per[b][1]["n"]) for b in ctx.LABEL_BLOCKS}
        g5 = {}
        for b in ctx.LABEL_BLOCKS:
            s = per[b][1]
            x = s["rules"][best]
            g5[b] = dict(kprice=x["k_ex"], shared=x["shared"]) if dec == "ENTER" else dict(a_frames=x["a_ex_fa"], a_noframes=x["a_ex_ff"], rlevel=s["rl_ex"])
        known_g5[dec] = g5
    return dict(best=known_best, union=known_union, g5=known_g5, se=se, scored=scored)


@pytest.fixture(scope="module")
def world():
    return build_world()


@pytest.fixture(scope="module")
def tag_cache(world, tmp_path_factory):
    d = tmp_path_factory.mktemp("rule_mix_tags")
    known = frozen_tag(world, d)
    return d, known


def test_the_world_holds_the_shapes_the_e2e_relies_on(world, tag_cache):
    d, known = tag_cache
    te = pd.read_csv(d / "tags_exit.tsv", sep="\t", dtype=str, keep_default_na=False)
    tn = pd.read_csv(d / "tags_enter.tsv", sep="\t", dtype=str, keep_default_na=False)
    ts = pd.read_csv(d / "tags_stop.tsv", sep="\t", dtype=str, keep_default_na=False)
    sc = te[(te["status"] == "scorable") & (te["room"] == "True")]
    assert set(te["era"]) >= {"A", "B"} and set(sc["block"]) >= {"2020", "2021-22", "untouched"}
    assert (sc["exit_lo_j"] == "1.0").any() and (sc["exit_lo_j"] == sc["exit_hi_j"]).any()                    # exit_lo_j = 1; a 1-session window
    assert re.fullmatch(r"\d+\.0", sc["exit_lo_j"].iloc[0]) and (te["status"] == "still_held").sum() + (te["M-1_bucket"] == "").sum() >= 0
    assert (ts.loc[(ts["status"] == "scorable") & (ts["room"] == "True") & (ts["loser"] == "True"), "fill_src"] == "open").any()   # open-fill STOP rows
    assert set(ts.loc[ts["sym"] == "LW", "loser"]) == {"True", "False"}
    tagged = tn[tn["tagged"] == "True"]
    assert {"09:32", "09:30"} <= set(tagged["flat_clock"]) and str(world["nod"].eid) in set(tagged["eid"]) and str(world["nod"].eid) in set(sc["eid"])
    assert (te["M-1_first_j"] == "").any() and any(re.fullmatch(r"\d+\.0", x) for x in te["M-1_first_j"] if x)  # blank when never fired; floats as '3.0'


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


class QuietClaims(ctx.CtxClaims):
    """Records every claim, asserts none: the synthetic world cannot reproduce the registration's counts (under test: the mechanics)."""

    def __call__(self, anchor, label, doc, mine, note=False):
        self.n += 1
        self.say(f"  [quiet] {label} | doc {doc} | mine {mine}")
        return True


def e2e_env(world, tag_cache, tmp_path, monkeypatch) -> dict:
    tags_dir, known = tag_cache
    tdir = tmp_path / "rule_mix"
    tdir.mkdir()
    for f in ("tags_enter.tsv", "tags_stop.tsv", "tags_exit.tsv", "control_windows.tsv.gz"):
        shutil.copyfile(tags_dir / f, tdir / f)
    doc, body = lock_env(tmp_path, monkeypatch)
    files = dict(ctx.MIX_FILES)
    files.update(mix_tags_enter=str(tdir / "tags_enter.tsv"), mix_tags_stop=str(tdir / "tags_stop.tsv"), mix_tags_exit=str(tdir / "tags_exit.tsv"),
                 mix_control_windows=str(tdir / "control_windows.tsv.gz"))
    monkeypatch.setattr(ctx, "MIX_FILES", files)
    monkeypatch.setattr(ctx, "TAG_FILE", {"ENTER": files["mix_tags_enter"], "STOP": files["mix_tags_stop"], "EXIT": files["mix_tags_exit"]})
    fl = tmp_path / "fetch_list.psv"
    fl.write_text("T00|2020-02-03|fit2020\nT01|2020-02-18|fit2020\n")
    monkeypatch.setattr(ctx, "FETCH_LIST", str(fl))
    C = world["C"]
    monkeypatch.setattr(ctx, "load_core", lambda say: C)
    reads = []

    def fresh_M(say, C_, a, b):                       # every stage a FRESH market (new exports, bars, store): objects freed, ids reusable
        gc.collect()
        m = world["make_M"]()
        reads.append(m["store"].reads)
        say("- synthetic markets rebuilt (a fresh market for this stage)")
        return m
    monkeypatch.setattr(ctx, "load_markets", fresh_M)
    monkeypatch.setattr(ctx, "check_inputs", lambda say: say("- inputs skipped (synthetic)"))
    monkeypatch.setattr(ctx, "assert_populations", lambda say, C_: say("- populations skipped (synthetic)"))
    monkeypatch.setattr(ctx, "CtxClaims", QuietClaims)
    stub = tmp_path / "trade_impact_stub.py"
    stub.write_text(G8_STUB)
    monkeypatch.setattr(ctx, "TRADE_IMPACT", str(stub))
    monkeypatch.setattr(ctx, "G8_FILES", {f"{k}_{e}": str(tmp_path / f"{k}_{e}") for k in ("flags", "export") for e in ("A", "B")})
    monkeypatch.setattr(ctx, "KNOWN_BEST", known["best"])
    monkeypatch.setattr(ctx, "KNOWN_UNION", known["union"])
    monkeypatch.setattr(ctx, "KNOWN_G5", known["g5"])
    monkeypatch.setattr(ctx, "FLOOR_MIN", 3)                     # the synthetic blocks are small: the floor's MECHANICS, not the doc's 15
    monkeypatch.setattr(ctx, "PERMS", 6)
    monkeypatch.setattr(ctx, "BOOTS", 40)
    return dict(doc=doc, body=body, tdir=tdir, reads=reads, known=known)


def paste_pins(env) -> dict:
    p = ctx.ctx_pins()
    write_doc(env["doc"], env["body"], [f"- {k}: {v}" for k, v in p.items()])
    return p


def test_end_to_end_dry_run_then_the_run_on_the_synthetic_world(world, tag_cache, tmp_path, monkeypatch):
    env = e2e_env(world, tag_cache, tmp_path, monkeypatch)
    assert ctx.main(["--run"]) == 2                                                          # the run refuses before the dry run
    assert ctx.main(["--dry-run"]) == 0
    dry = open(ctx.P_DRY).read()
    assert dry.splitlines()[0].startswith(ctx.DRY_HEADER) and dry.rstrip().splitlines()[-1].startswith("DRY RUN COMPLETE") and ctx.ctx_dry_run_complete(ctx.P_DRY)
    for s in ("the by-date assertion on every trade's decision-time view", "0 violations", "## CONSTANTS", "- ctx_const_EXIT_C-X1_T1:", "- ctx_const_ENTER_tree_order:",
              "the first ten trees in the canonical order", "HW-X'", "the SW cut (T2 of C-X3)", "§10 — C-E1 and the buy-day volume ratio", "SPY's presence",
              "Coverage from the fetch logs", "C21", "no_minute_before_bound", "open_fill", "no_bar_D", "spy_missing"):
        assert s in dry, s
    assert "bucket" not in "".join(ln for ln in dry.splitlines() if ln.startswith("- populations re-asserted"))
    consts0 = ctx.dry_constants(ctx.P_DRY)
    sw = re.search(r"^- the SW cut \(T2 of C-X3\) = (\S+)$", dry, re.M).group(1)
    assert sw == consts0["ctx_const_EXIT_C-X3_T2"] != consts0["ctx_const_EXIT_C-X3_T1"]                    # the SW cut is T2, never T1
    assert {"ctx_const_ENTER_C-E1_median", "ctx_const_EXIT_C-X1_median"} <= set(consts0)                 # the HW medians are pinned
    for dec in ctx.DECISIONS:                                                                             # each split's missing side is pinned,
        for cid, tok in ctx.SPLIT_ORDER[dec]:                                                             # and equals the side the dry run prints
            side = consts0[f"ctx_const_{dec}_{cid}_{tok}_missing_left"]
            name = f"{cid} <= {tok}" if tok != "bin" else f"{cid} = 0"
            m_ = re.search(rf"^    \d+\. {re.escape(name)} \(cut \S+; missing -> (left|right)\)", dry.split(f"## {dec} — the contexts")[1], re.M)
            assert m_ and side == str(m_.group(1) == "left"), (dec, cid, tok)
    # a second dry run prints byte for byte the same
    d1 = open(ctx.P_DRY, "rb").read()
    os.remove(ctx.P_DRY)
    assert ctx.main(["--dry-run"]) == 0 and open(ctx.P_DRY, "rb").read() == d1
    assert ctx.main(["--print-pins"]) == 0
    pins = open(ctx.P_PINS).read()
    assert f"- ctx_module: {ctx.sha(MOD_PATH)}" in pins and "- ctx_ledger: ABSENT" in pins and "- ctx_const_STOP_C-S2_T1:" in pins
    assert ctx.main(["--run"]) == 2                                                          # the pins are not under the marker yet
    paste_pins(env)
    assert ctx.ctx_lock() == []
    rc = ctx.main(["--run"])
    out = open(ctx.P_RUN).read() if os.path.exists(ctx.P_RUN) else open(ctx.STOPPED).read()
    assert rc == 0, out[-5000:]
    for s in ("G6 the decision-time guard", "G1 identity", "0 differences", "G2 the ±0 known answers", "G3 tolerance consistency", "G4 the 10/20 switch",
              "G5 the no-split tree's per-leaf chance", "ALL GATES PASSED", "## G8 — ctx_run", "decision ENTER — tolerance the bracket (primary)",
              "decision STOP — tolerance ±1c (primary)", "decision EXIT — tolerance ±2", "MAP − BEST (paired)", "SHUF mean", "(c-1) control (a), frames",
              "(c-2) random levels", "(c-1) k-price random prices", "(c-2) the shared random window", "ORACLE-1", "UNION", "-> context helps:", "beats chance",
              "beside MAP-T1", "beside HW-E", "beside HW-S", "beside HW-X'", "beside SW-a", "beside SW-b", "losers / non-losers", "the undated flickers",
              "clipped placements", "UNRESOLVED -> CLOSE upgrades", "missing per context", "THE SUMMARY", "RUN COMPLETE"):
        assert s in out, s
    assert re.search(r"G1 identity: .* ENTER \d+, STOP \d+, EXIT \d+ cells: 0 differences", out)
    assert re.search(r"G3 tolerance consistency: \d+ widened .*: 0 differences", out)
    # §4a's one upgrade really occurs in the world (a next-session booking on a missing exit_hi): counted, never overridden
    assert re.search(r"UNRESOLVED -> CLOSE upgrades \{[^}]*'pm1c'\): [1-9]", out)
    assert re.search(r"- (ENTER|STOP|EXIT): (context map|context helps, chance too|no context gain)", out)
    # the per-trade files; the contexts.tsv join: sym and E equal the tag row's by eid on every row
    o = ctx.OUT_DIR
    for f in ("contexts.tsv", "maps.tsv", "groups.tsv", "controls.tsv.gz"):
        assert os.path.exists(os.path.join(o, f)), f
    cx = pd.read_csv(os.path.join(o, "contexts.tsv"), sep="\t", dtype=str, keep_default_na=False)
    for dec in ctx.DECISIONS:
        t = pd.read_csv(ctx.TAG_FILE[dec], sep="\t", dtype=str, keep_default_na=False).set_index("eid")
        sub = cx[cx["decision"] == dec]
        assert len(sub) and all(t.loc[r_["eid"], "sym"] == r_["sym"] and t.loc[r_["eid"], "E"] == r_["E"] for r_ in sub.to_dict("records")), dec
    nod = cx[cx["eid"] == str(world["nod"].eid)]
    assert len(nod) >= 2 and set(nod["C-X1_missing"].replace("", np.nan).dropna()) <= {"no_bar_D"} and (nod["decision"] == "EXIT").any()
    assert (cx.loc[(cx["eid"] == str(world["nod"].eid)) & (cx["decision"] == "EXIT"), "C-X1_missing"] == "no_bar_D").all()
    assert (cx.loc[(cx["eid"] == str(world["opb"].eid)) & (cx["decision"] == "ENTER"), "C-E1_missing"] == "no_minute_before_bound").all()
    # ties at a cut: the dated breakouts share one ADR20 (0.05), and a speed tertile lands on that mass point
    consts = ctx.dry_constants(ctx.P_DRY)
    ties = []
    for dec, cid in (("STOP", "C-S2"), ("EXIT", "C-X1")):
        s2 = pd.to_numeric(cx.loc[(cx["decision"] == dec) & (cx["block"] == "2020") & (cx["set"] == "scorable"), cid], errors="coerce").dropna()
        ties += [int((s2 == float(consts[f"ctx_const_{dec}_{cid}_{t}"])).sum()) for t in ("T1", "T2")]
    assert max(ties) >= 2, ties
    mp_ = pd.read_csv(os.path.join(o, "maps.tsv"), sep="\t")
    assert set(mp_["line"]) >= {"MAP", "MAP-T1", "HW-E", "HW-S", "HW-X", "HW-X'", "SW-a", "SW-b"} and mp_["primary"].sum() == 3
    cw = pd.read_csv(os.path.join(o, "controls.tsv.gz"), sep="\t")
    assert set(cw["kind"]) >= {"perm", "draw:kprice", "draw:shared", "draw:a_frames", "draw:a_noframes", "draw:rlevel"}
    assert fz.ledger_verify(ctx.LEDGER) == [] and len(open(ctx.LEDGER).read().splitlines()) == 1 + 5
    assert os.path.exists(os.path.join(ctx.FROZEN_DIR, f"01_ctx_frozen_{ctx.sha(MOD_PATH)[:12]}.py"))
    assert len(env["reads"]) == 3 and sum(env["reads"][-1].values()) > 0                     # a fresh market per stage
    # it runs ONCE: a second run, a dry run, a reset are all refused
    assert ctx.main(["--run"]) == 2 and ctx.main(["--dry-run"]) == 2 and ctx.main(["--reset", "why"]) == 2


def test_a_planted_tag_cell_stops_g1_then_the_reset_archives_and_waits_for_the_disclosure(world, tag_cache, tmp_path, monkeypatch):
    env = e2e_env(world, tag_cache, tmp_path, monkeypatch)
    p_ = env["tdir"] / "tags_stop.tsv"
    t = pd.read_csv(p_, sep="\t", dtype=str, keep_default_na=False)
    idx = next(i for i, v in enumerate(t["S1-T_booked_j"]) if v not in ("", "nan"))
    t.loc[idx, "S1-T_booked_j"] = str(int(float(t.loc[idx, "S1-T_booked_j"])) + 1) + ".0"     # one booked session shifted
    t.to_csv(p_, sep="\t", index=False)
    assert ctx.main(["--dry-run"]) == 0                                                      # the dry run reads no bucket column: it cannot see it
    paste_pins(env)
    assert ctx.main(["--run"]) == 3
    stopped = open(ctx.STOPPED).read()
    assert "STOPPED: G1:" in stopped and "S1-T_booked_j" in stopped and "ALL GATES PASSED" not in stopped
    assert ctx.main(["--run"]) == 2
    assert ctx.ctx_reset(rp.Say(), "") == 2
    before = {os.path.abspath(p0): (ctx.sha(p0), os.path.getsize(p0)) for p0 in ctx.reset_artifacts()}
    assert len(before) >= 3 and any(sz > 0 for _h, sz in before.values())
    assert ctx.main(["--reset", "G1: a planted tag cell (test)"]) == 0
    evs = fz.fit_events(ctx.RUN_EVENTS)
    assert len(evs) == 1
    ev = evs[0]["event"]
    man = pd.read_csv(os.path.join(ctx.RUN_EVENTS, ev, "MANIFEST.tsv"), sep="\t")
    assert len(man) >= 3 and not os.path.exists(ctx.STOPPED) and not os.path.exists(ctx.P_DRY)
    assert set(man["original"]) == set(before)                                               # every artifact archived, none left out
    for row in man.to_dict("records"):
        arch = os.path.join(ctx.RUN_EVENTS, ev, row["archived"])
        assert os.path.exists(arch) and not os.path.exists(row["original"])
        h0, sz0 = before[row["original"]]
        assert row["sha256"] == h0 == ctx.sha(arch) and int(row["bytes"]) == sz0 == os.path.getsize(arch)   # the copy IS the file, byte for byte
    bad = ctx.ctx_lock()
    assert any("dry run has not COMPLETED" in x for x in bad) and any("not disclosed" in x for x in bad)
    shutil.copyfile(tag_cache[0] / "tags_stop.tsv", p_)
    assert ctx.main(["--dry-run"]) == 0
    p = paste_pins(env)
    assert f"fit_event_{ev}" in p and ctx.ctx_lock() == []


@pytest.mark.parametrize("plant", ["floor", "missing_side"])
def test_a_constant_that_moved_after_the_dry_run_stops_the_run_d2(plant, world, tag_cache, tmp_path, monkeypatch):
    env = e2e_env(world, tag_cache, tmp_path, monkeypatch)
    assert ctx.main(["--dry-run"]) == 0
    paste_pins(env)
    assert ctx.ctx_lock() == []
    if plant == "floor":
        monkeypatch.setattr(ctx, "FLOOR_MIN", 4)                                            # the registered constant changes after the freeze
    else:
        orig = ctx.missing_side                                                             # C4 flipped after the freeze: a missing value
        monkeypatch.setattr(ctx, "missing_side", lambda vals, cut: not orig(vals, cut))     # now follows the SMALLER child
    assert ctx.main(["--run"]) == 3
    stopped = open(ctx.STOPPED).read()
    assert "the constants differ from the pins (D2)" in stopped and "G1 identity" not in stopped
    assert ("_missing_left" in stopped) == (plant == "missing_side")


def test_a_dry_run_mismatch_stops_and_the_run_stays_locked(world, tag_cache, tmp_path, monkeypatch):
    env = e2e_env(world, tag_cache, tmp_path, monkeypatch)
    monkeypatch.setattr(ctx, "CtxClaims", _REAL_CLAIMS)
    monkeypatch.setattr(ctx, "DOC", FIXTURE_DOC)                                             # the claims resolve into the registered fixture
    monkeypatch.setattr(ctx, "FREEZE_BODIES", str(tmp_path / "fb_fixture"))
    assert ctx.main(["--dry-run"]) == 3
    dry = open(ctx.P_DRY).read()
    assert "STOPPED: the dry run does not reproduce the registration" in dry and "MISMATCH [L" in dry and "DRY RUN COMPLETE" not in dry
    assert not ctx.ctx_dry_run_complete(ctx.P_DRY)


# ═════════════════════════════════════════════════════════════════════════════════════════════ every known-answer gate STOPS the run (§11, §7d)
@pytest.fixture(scope="module")
def built(world, tag_cache):
    """The rule-mix fires re-built and the CLOSE / chance matrices built ONCE on a fresh market of the world (the real builders, the frozen
    tag files' populations): the control-build test reads them, and the gate tests hand them to --run (they hold arrays only, no record)."""
    tags_dir = tag_cache[0]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ctx, "TAG_FILE", {d: str(tags_dir / f"tags_{d.lower()}.tsv") for d in ctx.DECISIONS})
        C, M = world["C"], world["make_M"]()
        rb = ctx.rebuild_rule_mix(rp.Say(), C, M)
        P = ctx.populations(C)
        data = ctx.build_matrices(rp.Say(), P, rb, rb["store"], sw_cut=0.0)
    return dict(rb=rb, P=P, data=data)


@pytest.mark.parametrize("gate", ["G2", "G3", "G4", "G5", "G6"])
def test_each_known_answer_gate_stops_the_run_on_its_planted_defect(gate, world, tag_cache, built, tmp_path, monkeypatch):
    """One planted defect per gate, AFTER the dry run and the pins (so the dry run cannot see it): the run STOPS at that gate (exit 3, a
    STOPPED file naming it), before any new number. G2: a known ±0 share off by one printed point; G3: the ±1c side flipped in the path under
    test; G4: SW's booking one session late; G5: a known chance share off by one point; G6: a reader of the LAST bar it is given wherever D is
    defined (identical on every truncated view, the future on the full record — the truncated by-date check alone cannot see it)."""
    env = e2e_env(world, tag_cache, tmp_path, monkeypatch)
    assert ctx.main(["--dry-run"]) == 0
    paste_pins(env)
    assert ctx.ctx_lock() == []
    known = env["known"]
    monkeypatch.setattr(ctx, "build_matrices", lambda say, P, rb, store, sw_cut=None: built["data"])   # the matrices built once (G2 / G5 read them)
    if gate == "G2":
        code, sh = known["best"]["ENTER"]
        monkeypatch.setattr(ctx, "KNOWN_BEST", {**known["best"], "ENTER": (code, {**sh, "2021-22": sh["2021-22"] + 0.01})})
    elif gate == "G3":
        orig = ctx.tol_ab
        monkeypatch.setattr(ctx, "tol_ab", lambda tol, side: orig(tol, {"same": "next", "next": "same"}.get(side, side)))
    elif gate == "G4":
        orig = ctx.switch_fire

        def late(rec, c_, smas, cut, variant):
            f = orig(rec, c_, smas, cut, variant)
            return f if f.jb is None else dataclasses.replace(f, jb=f.jb + 1)
        monkeypatch.setattr(ctx, "switch_fire", late)
    elif gate == "G5":
        g5 = copy.deepcopy(known["g5"])
        g5["ENTER"]["2021-22"]["kprice"] += 0.01
        monkeypatch.setattr(ctx, "KNOWN_G5", g5)
    else:
        orig = ctx.view_d_index
        monkeypatch.setattr(ctx, "view_d_index", lambda v_: None if orig(v_) is None else len(v_.daily.dates) - 1)
    assert ctx.main(["--run"]) == 3
    stopped = open(ctx.STOPPED).read()
    assert f"STOPPED: {gate}:" in stopped and "ALL GATES PASSED" not in stopped and not os.path.exists(ctx.P_RUN), stopped[-3000:]
    earlier = {"G2": ["G1 identity"], "G3": ["G1 identity", "G2 the ±0"], "G4": ["G1 identity", "G2 the ±0", "G3 tolerance"],
               "G5": ["G1 identity", "G2 the ±0", "G3 tolerance", "G4 the 10/20"], "G6": []}[gate]
    for g in earlier:                                                                        # every earlier gate ran and passed
        assert re.search(rf"- {re.escape(g)}.*: 0 differences", stopped), g


# ═════════════════════════════════════════════════════════════════════════════════════════════ the (c-2) and ±1c control builds, rebuilt independently
def test_the_control_builds_rebuilt_independently_on_the_world(built):
    """(a) control (a)'s (c-2) row on draw d = the placement PLACE_KEY drew, widened per firing (±1c: [s - 1, s + w - 1] same-session,
    [s, s + w] next-session), through the frozen bucket_vec; its (c-1) = the mean over placements; (b) the random level's ±1c window =
    [exit_lo - 1, exit_hi] (a touch is a same-session firing, C9); (c) its (c-2) columns = the k-level draws (RLEVEL_K_KEY), one per
    rule; (d) control (a) at s >= a_f = the mean over the unclipped placements."""
    rb, P, data = built["rb"], built["P"], built["data"]
    store = rb["store"]
    EXc = ctx.CODE_OF[EX]
    tol, hits = "pm1c", Counter()
    for dec in ("STOP", "EXIT"):
        k = len(ctx.LIB[dec])
        for b in ("2020", "2021-22"):
            for i, tr in enumerate(P[dec]["scorable"][b]):
                t = rb["se"][tr.eid]
                r = t["rec"]
                J, lo, hi = int(t["prep"]["J_tail"]), r.exit_lo_j, r.exit_hi_j
                win = mix.random_windows(r, J, "a")
                starts, w = np.asarray(win["starts"]), int(win["width"])
                fires = [t[f"{dec.lower()}_fires"][c] for c in ctx.LIB[dec]]
                for arm, frames in (("a_frames", True), ("a_noframes", False)):
                    codes = np.zeros((len(starts), k), dtype=bool)
                    af = np.zeros(k, dtype=np.int64)
                    for j, f in enumerate(fires):
                        a_, b_ = (0, 0) if (f.abstain or f.jb is None or f.je is None) else ((0, 1) if f.jb > f.je else (1, 0))
                        af[j] = a_
                        for q, s0 in enumerate(starts):
                            lo_s, hi_s = max(0, int(s0) - a_), min(int(s0) + w - 1 + b_, J)
                            codes[q, j] = mix.bucket_vec(f, np.array([lo_s]), hi_s - lo_s + 1, frames)[0] == EXc
                    assert np.allclose(data["chance1"][dec][tol][arm][b][i, :k], codes.mean(axis=0)), (dec, b, tr.eid, arm)
                    dr = data["draws2"][dec][tol][arm][b]
                    for d_ in range(ctx.DRAWS):
                        q = int(fz.rng_for(ctx.PLACE_KEY.format(decision=dec, eid=tr.eid, d=d_)).integers(0, len(starts)))
                        assert (dr[d_, i, :k] == codes[q]).all(), (dec, b, tr.eid, arm, d_)
                    hits["placements_differ"] += int((codes != codes[0]).any())
                    if arm == "a_frames":
                        sa = data["chance1_sa"][dec][tol][b][i, :k]
                        for j in range(k):
                            keep = starts >= af[j]
                            want = codes[keep, j].mean() if keep.any() else math.nan
                            assert (np.isnan(sa[j]) and np.isnan(want)) or sa[j] == pytest.approx(want), (dec, b, tr.eid, j)
                            hits["clipped_changes_the_mean"] += int(keep.any() and not keep.all() and want != codes[:, j].mean())
                rl = t["rlevel"]
                if rl.get("no_room"):
                    continue
                path = mix.touch_path(r, store)
                one = mix.touch_buckets_vec(path, rl["levels"], max(0, lo - 1), hi) == EXc
                assert np.allclose(data["chance1"][dec][tol]["rlevel"][b][i, :k], one.mean()), (dec, b, tr.eid)
                nxt_hi = min(hi + 1, J)
                nxt = mix.touch_buckets_vec(mix.touch_path(dataclasses.replace(r, exit_hi_j=nxt_hi), store), rl["levels"], lo, nxt_hi) == EXc
                hits["next_side_differs"] += int(nxt.mean() != one.mean())
                lk = mix.random_level_draws(r, mix.RLEVEL_K_KEY, k)
                drl = data["draws2"][dec][tol]["rlevel"][b]
                for j in range(k):
                    col = mix.touch_buckets_vec(path, lk[:, j], max(0, lo - 1), hi) == EXc
                    assert (drl[:, i, j] == col).all(), (dec, b, tr.eid, j)
                    hits["k_level_differs_from_single"] += int((col != one).any())
    # every check bites somewhere in the world (else it would say nothing)
    assert all(hits[x] > 0 for x in ("placements_differ", "clipped_changes_the_mean", "next_side_differs", "k_level_differs_from_single")), hits


# ═════════════════════════════════════════════════════════════════════════════════════════════ D2: the dry run reads no bucket column
BUCKETISH = re.compile(r"(_bucket|_first_j|_booked_j|_first_minute|_cross|_union)$|^(tag|earliest_tag|rlevel_ex|loser_lo|rprice_feasible)$")


def test_the_dry_run_reads_no_bucket_column_d2(world, tag_cache, tmp_path, monkeypatch):
    env = e2e_env(world, tag_cache, tmp_path, monkeypatch)
    # the reader parses ONLY the label columns (usecols), header first
    calls = []
    orig_read = pd.read_csv

    def spy(*a, **k):
        calls.append(k)
        return orig_read(*a, **k)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ctx.pd, "read_csv", spy)
        for dec in ctx.DECISIONS:
            t = ctx.read_labels(dec)
            assert tuple(t.columns) == ctx.LABEL_COLS[dec] and not any(BUCKETISH.search(c) for c in t.columns)
    assert calls and all(k.get("nrows") == 0 or list(k.get("usecols") or []) == list(ctx.LABEL_COLS[d]) for k, d in
                         zip(calls, [d for d in ctx.DECISIONS for _ in (0, 1)]))
    assert "loser_lo" not in ctx.LABEL_COLS["STOP"] + ctx.LABEL_COLS["EXIT"]
    # the printout is the same with every bucket / firing / tag column garbled (half of them dropped): only the three tag-file sha pins move
    assert ctx.main(["--dry-run"]) == 0
    clean = open(ctx.P_DRY).read()
    os.remove(ctx.P_DRY)
    for f in ("tags_enter.tsv", "tags_stop.tsv", "tags_exit.tsv"):
        p_ = env["tdir"] / f
        t = pd.read_csv(p_, sep="\t", dtype=str, keep_default_na=False)
        cols = [c for c in t.columns if BUCKETISH.search(c)]
        assert len(cols) >= 4, f
        t[cols] = "GARBAGE"
        t.drop(columns=cols[::2]).to_csv(p_, sep="\t", index=False)
    assert ctx.main(["--dry-run"]) == 0
    garbled = open(ctx.P_DRY).read()
    keep = lambda txt: [ln for ln in txt.splitlines() if not re.match(r"\s+mix_tags_(enter|stop|exit): ", ln)]   # noqa: E731
    assert keep(garbled) == keep(clean) and garbled != clean
