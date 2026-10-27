"""Tests for the #705 as-is read, steps 6b and 6c (scripts/probes/_705_asis_1026/03_check.py, 04_band.py, asis_check_common.py; the plan's §10
step-6 test list). Synthetic fixtures only: no apollo_data, no machine path; the two real-data dry runs carry a skip guard naming the data.

Covers: the statement classes (fill / level, clean / garbled, the price kind matching the action's side, a day class that names a day — the
primary is chosen by the reader's labels alone, R85); the join reads the readers' ticker and the stream date only — a 'sold' landing on a buy
window is an R5 miss; the shifted window moves both frames and keeps the clock bracket; the §4.2 tolerance and containment; R1's gap bar
PASSES on a true reconstruction and FAILS on a deliberately shifted window and on a deliberately swapped symbol, through the real scorer AND
through the real control path (build_controls -> shifted_window -> RangeEngine.range_row on synthetic daily bars); the §9 floor on the
SCORED n; only the primary line carries a verdict; the cross-symbol control uses the same join rule; R3 offsets and the other_date nearest-
window offset; R4's band; the account path as a constant mix (the money deployed never above the exposure, staggered entries, slots for the
held names with no range, the marks); ytd and the distance to his figure; the run gates (6b, 6c incl. 'if 6b fails, 6c is not read', a 6c
dry run made before 6b refused, an ABSENT pin refused); the side of a position read from statements beside it; the consequence labels
verbatim in the frozen doc; the identifier scan and the fresh-interpreter import test extended to 03 / 04 / the shared module; the dry runs on
real data end DRY RUN COMPLETE with 0 MISMATCH.
"""
from __future__ import annotations

import ast
import gzip
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
ASIS = REPO / "scripts" / "probes" / "_705_asis_1026"
DOC = REPO / "docs" / "analysis" / "cb_asis_reconstruction_prereg_2026-10-26.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


K = _load("asis_check_common", ASIS / "asis_check_common.py")
M3 = _load("asis_check03", ASIS / "03_check.py")
M4 = _load("asis_band04", ASIS / "04_band.py")
C, P, CAP = K.C, K.P, K.CAP

REAL_DATA = os.path.isdir(C.OUT_DIR) and all(os.path.exists(p) for p in K.V2_SHEETS) and os.path.exists(K.RANGES)
needs_real_data = pytest.mark.skipif(not REAL_DATA, reason="needs the local apollo_data cb702/qm_streams/asis_1026 tree (ranges.tsv + the v2 sheets)")


# ═════════════════════════════════════════════════════════════════════════════════════════════ fixtures
def cal(n: int = 40, start=(2020, 6, 1)) -> list:
    """A weekday calendar of n sessions from 2020-06-01 (a Monday)."""
    import datetime as dt
    d, out = dt.date(*start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


SESS = C.Sessions(cal())


def frame(fid: str, date: str, ctx: str = "in", clock: str = "10:00", syms=()):
    return C.Frame(idx=int(fid[1:]), frame_id=fid, vid="v", date=date, ctx=ctx, clock=clock, full=True, symbols=list(syms), blip_filled=[])


def window(eid: int, sym: str, side: str, lo: str, hi: str, clock_a: str = "09:40", clock_b: str = "10:10", flicker: bool = False, S=SESS):
    a, b = frame(f"f{eid * 2}", lo, "in", clock_a), frame(f"f{eid * 2 + 1}", hi, "in", clock_b)
    w = P.Window(eid, sym, sym, side, lo, hi, a, b, False, flicker, first_frame=b)
    w.bracket, w.year, w.in_span = P.type_bracket(w, S), int(hi[:4]), True
    return w


def sheet_row(stmt_id: str, date: str, ticker: str, action: str, price="", kind="entry", garbled="N", day="implied_recent", own="Y", ident="Y",
              side="", shares="", dollars=""):
    return {"stmt_id": stmt_id, "sid": stmt_id, "part": "p1", "stream_date": date, "his_trade": own, "ticker_ident": ident, "ticker": ticker,
            "ticker_inferred": "", "action": action, "side": side, "date_pinnable": day, "price_stated": "Y" if price != "" else "N",
            "price_value": str(price), "price_garbled": garbled, "price_kind": kind, "shares": shares, "dollar_result": dollars, "note": ""}


def range_row(eid: int, side: str, lo: str, hi: str, lo_raw: float, hi_raw: float, factor: float = 1.0, flicker=False, resolution="minute", flags=""):
    return {"eid": str(eid), "side": side, "lo": lo, "hi": hi, "bracket": "same_in_in", "flicker": str(flicker), "resolution": resolution,
            "year": hi[:4], "in_span": "True", "flags": flags, "raw_factor": str(factor), "range_lo_raw": str(lo_raw), "range_hi_raw": str(hi_raw),
            "range_lo": str(lo_raw / factor), "range_hi": str(hi_raw / factor), "range_lo_with_panel": str(lo_raw / factor),
            "range_hi_with_panel": str(hi_raw / factor), "avg_traded_price": str((lo_raw + hi_raw) / 2 / factor),
            "avg_traded_price_raw": str((lo_raw + hi_raw) / 2), "hold_sessions_max": "3", "sym": "AAA", "density_all": "1.0"}


class FakeEngine:
    """Enough of RangeEngine for the scorer: the windows by key and a session range of 0 (so the tolerance is max(1%, $0.05))."""

    def __init__(self, windows: list):
        self.by_key = {(w.eid, w.side): w for w in windows}
        self.S = SESS

    def window(self, eid, side):
        return self.by_key.get((int(eid), side))

    def session_range_raw(self, w, day):
        return 0.0


# ═════════════════════════════════════════════════════════════════════════════════════════════ the statement classes
def test_classify_fill_level_clean_garbled_matched_and_day_named():
    k = K.classify(sheet_row("a", "2020-06-03", "AAA", "buy", 42.5))
    assert k["own"] and k["ident"] == "Y" and k["ticker"] == "AAA" and k["fill"] == "fill" and not k["garbled"] and k["price"] == 42.5
    assert k["matched"] and k["day_named"] and K.is_primary_class(k)
    assert K.classify(sheet_row("a", "2020-06-03", "AAA", "stopped", 40, kind="stop"))["fill"] == "level"        # a stop-out states the level (R63)
    assert K.classify(sheet_row("a", "2020-06-03", "AAA", "stop_level", 40, kind="stop"))["fill"] == "level"
    h = K.classify(sheet_row("a", "2020-06-03", "AAA", "holding", 40, kind="entry"))
    assert h["fill"] == "fill" and not h["matched"] and not K.is_primary_class(h)                                  # a past fill: beside (R85)
    assert K.classify(sheet_row("a", "2020-06-03", "AAA", "stopped", 40, kind="exit"))["matched"]                # an exit price on a sale action
    assert not K.classify(sheet_row("a", "2020-06-03", "AAA", "stopped", 40, kind="entry"))["matched"]           # an entry price on a sale action: beside
    assert not K.classify(sheet_row("a", "2020-06-03", "AAA", "buy", 40, kind="exit"))["matched"]
    assert K.classify(sheet_row("a", "2020-06-03", "AAA", "shorted", 40, kind="entry"))["matched"]
    assert K.classify(sheet_row("a", "2020-06-03", "AAA", "covered", 40, kind="exit"))["matched"]
    for day in ("stream_day", "stated_earlier", "implied_recent"):
        assert K.classify(sheet_row("a", "2020-06-03", "AAA", "buy", 40, day=day))["day_named"]
    for day in ("unstated", "approx_earlier"):
        u = K.classify(sheet_row("a", "2020-06-03", "AAA", "buy", 40, day=day))
        assert not u["day_named"] and not K.is_primary_class(u)                                                   # the stream date has no stated meaning
    assert K.classify(sheet_row("a", "2020-06-03", "AAA", "buy", 40, garbled="Y"))["garbled"]
    assert not K.classify(sheet_row("a", "2020-06-03", "AAA", "buy", 40, garbled=""))["garbled"]                  # Y-only flag (R64)
    assert K.classify(sheet_row("a", "2020-06-03", "$aaa", "buy", 40, ident="amb"))["ident"] == "amb"
    assert not K.classify(sheet_row("a", "2020-06-03", "AAA", "buy", 40, own="advice"))["own"]
    assert K.classify(sheet_row("a", "2020-06-03", "AAA", "buy", 40, shares="20000", dollars="-180000"))["dollar_result"] == -180000.0
    assert K.statement_day(sheet_row("a", "2020-06-03", "AAA", "buy")) == "2020-06-03"                              # R62


def test_t1_readings_count_the_tier_under_each_wording():
    ks = [K.classify(sheet_row("a", "2020-06-03", "AAA", a, 40, day=d)) for a, d in
          [("buy", "stream_day"), ("sell_unspec", "stated_earlier"), ("stopped", "implied_recent"), ("buy", "unstated"), ("buy", "approx_earlier"),
           ("holding", "implied_recent"), ("stop_level", "implied_recent"), ("stop_level", "unstated")]]
    t = K.t1_readings(ks)
    assert t == {"freeze_record": 8, "s41_words": 3, "s41_with_approx": 4, "s41_with_approx_and_stop_level": 5}


# ═════════════════════════════════════════════════════════════════════════════════════════════ the join and R5
def two_positions():
    ws = [window(1, "AAA", "buy", "2020-06-03", "2020-06-03"), window(1, "AAA", "sale", "2020-06-10", "2020-06-10"),
          window(2, "BBB", "buy", "2020-06-03", "2020-06-03"), window(2, "BBB", "sale", "2020-06-12", "2020-06-12")]
    ranges = {(1, "buy"): range_row(1, "buy", "2020-06-03", "2020-06-03", 40.0, 42.0), (1, "sale"): range_row(1, "sale", "2020-06-10", "2020-06-10", 50.0, 52.0),
              (2, "buy"): range_row(2, "buy", "2020-06-03", "2020-06-03", 400.0, 420.0), (2, "sale"): range_row(2, "sale", "2020-06-12", "2020-06-12", 500.0, 520.0)}
    tup = K.windows_tuple(ws)
    return ws, ranges, CAP.index_windows(tup), CAP.index_holds(tup)


def test_join_uses_readers_ticker_and_stream_date_and_a_sold_on_a_buy_window_is_an_r5_miss():
    ws, ranges, by_sym, holds = two_positions()
    eng = FakeEngine(ws)
    rows = [sheet_row("s1", "2020-06-03", "AAA", "sell_unspec", 41.0, kind="exit"),      # said 'sold' on the BUY day: joins the buy window by day alone
            sheet_row("s2", "2020-06-11", "AAA", "stopped", 51.0, kind="exit", day="stated_earlier"),   # 'yesterday': one session off the sale window
            sheet_row("s3", "2020-06-05", "AAA", "buy", 41.0),                                          # mid-hold: none, inside_hold (R82)
            sheet_row("s4", "2020-06-03", "ZZZ", "buy", 9.0),                                           # never on the panel
            sheet_row("s5", "2020-06-03", "AAA", "holding", 41.0),                                      # no side: excluded from R5
            sheet_row("s6", "2020-06-19", "AAA", "buy", 41.0)]                                          # another date: 7 sessions after the sale window (R88)
    st = M3.build_statements(rows, by_sym, holds, ranges, eng, SESS)
    by = {s["stmt_id"]: s for s in st}
    assert by["s1"]["join_status"] == "unique" and by["s1"]["side"] == "buy" and by["s1"]["dist"] == 0
    assert by["s2"]["join_status"] == "unique" and by["s2"]["side"] == "sale" and by["s2"]["dist"] == 1 and by["s2"]["offset_end"] == 1
    assert by["s3"]["join_status"] == "none" and by["s3"]["join_reason"] == "inside_hold" and by["s3"]["beside_eid"] == "1"
    assert by["s4"]["join_status"] == "none" and by["s4"]["join_reason"] == "not_on_panel"
    assert by["s6"]["join_status"] == "none" and by["s6"]["join_reason"] == "other_date" and by["s6"]["nearest_offset"] == 7
    jc = M3.join_counts(st)
    assert (jc["unique"], jc["ambiguous"], jc["none"]) == (3, 0, 3)
    M3.score(st, [], ranges, eng, SESS)
    r5 = K.r5_agreement([(s["action"], s["side"]) for s in st if s["join_status"] == "unique"])
    assert r5["n"] == 2 and r5["agree"] == 1 and r5["excluded_no_side"] == 1 and r5["misses"] == [("sell_unspec", "buy")]
    assert r5["verdict"] == K.VERDICT_FAIL
    assert by["s1"]["r5_agree"] is False and by["s2"]["r5_agree"] is True and by["s5"]["r5_agree"] == ""
    # the join signature carries no action and no price
    args = CAP.join_position.__code__.co_varnames[:CAP.join_position.__code__.co_argcount]
    assert "action" not in args and "price" not in args


def test_nearest_window_offset_is_signed_and_any_distance():
    ws, ranges, by_sym, holds = two_positions()
    assert K.nearest_window_offset("AAA", "2020-06-01", by_sym, SESS) == -2       # two sessions before the buy window
    assert K.nearest_window_offset("AAA", "2020-06-03", by_sym, SESS) == 0
    assert K.nearest_window_offset("AAA", "2020-06-19", by_sym, SESS) == 7        # seven after the sale window
    assert K.nearest_window_offset("ZZZ", "2020-06-19", by_sym, SESS) is None


def test_r5_map_is_the_plans_and_the_bar():
    items = [("stopped", "sale"), ("sold_x", "sale"), ("buy", "buy"), ("shorted", "buy"), ("covered", "sale"), ("add", "buy"), ("sell_all", "sale"),
             ("sell_part", "sale"), ("sell_unspec", "sale"), ("holding", "buy"), ("stop_level", "sale"), ("result", "buy")]
    r = K.r5_agreement(items)
    assert r["n"] == 8 and r["agree"] == 8 and r["excluded_no_side"] == 4 and r["verdict"] == K.VERDICT_PASS
    assert K.r5_agreement([("buy", "buy")] * 9 + [("buy", "sale")])["verdict"] == K.VERDICT_PASS           # 90% is the bar
    assert K.r5_agreement([("buy", "buy")] * 8 + [("buy", "sale")] * 2)["verdict"] == K.VERDICT_FAIL
    assert K.r5_agreement([])["verdict"] == K.VERDICT_ND


def test_cross_names_use_the_same_join_rule_and_never_the_statements_symbol():
    ws, ranges, by_sym, holds = two_positions()
    assert K.cross_names("AAA", "2020-06-03", by_sym, SESS) == [("BBB", 2, "buy")]
    assert K.cross_names("AAA", "2020-06-12", by_sym, SESS) == [("BBB", 2, "sale")]
    assert K.cross_names("AAA", "2020-06-08", by_sym, SESS) == []                       # BBB held, but no window within a session (R67)


# ═════════════════════════════════════════════════════════════════════════════════════════════ the shifted window
def test_shifted_window_moves_lo_hi_and_both_frames_and_keeps_the_clock_bracket():
    w = window(7, "AAA", "buy", "2020-06-10", "2020-06-10", "09:45", "10:05")
    w2 = K.shifted_window(w, -2, SESS)
    assert (w2.lo, w2.hi) == ("2020-06-08", "2020-06-08") and w2.earlier.date == "2020-06-08" and w2.later.date == "2020-06-08"
    assert (w2.earlier.clock, w2.later.clock, w2.earlier.ctx) == ("09:45", "10:05", "in") and w2.bracket == "same_in_in"
    P.reachable(w2, SESS)
    assert w2.reach == [("2020-06-08", 15, 35)]                                           # the clock bracket survives the shift (R66)
    assert w2.reach != w.reach and w.lo == "2020-06-10"                                   # the real window is untouched
    assert K.shifted_window(window(8, "AAA", "buy", "2020-06-01", "2020-06-01"), -1, SESS) is None     # off the calendar
    w3 = K.shifted_window(window(9, "AAA", "buy", "2020-06-10", "2020-06-12"), 3, SESS)
    assert (w3.lo, w3.hi) == ("2020-06-15", "2020-06-17") and w3.bracket == "sessions_2_5"


# ═════════════════════════════════════════════════════════════════════════════════════════════ tolerance, containment, the gap bar
def test_tolerance_and_containment():
    assert K.tolerance(100.0, None) == 1.0 and K.tolerance(1.0, None) == 0.05 and K.tolerance(100.0, 20.0) == 2.0 and K.tolerance(100.0, 0.0) == 1.0
    assert K.contains(42.0, 42.5, 44.0, 0.5) and not K.contains(42.0, 42.6, 44.0, 0.5) and K.contains(44.4, 42.0, 44.0, 0.5)
    assert K.share([True, False, True, True]) == 75.0 and K.share([]) is None
    assert K.control_share([[True, False], [False, False], []]) == 25.0


def controls_for(stmts: list, real_ranges: dict, shift_ranges: dict, cross_ranges: dict) -> list:
    """Control rows as build_controls writes them: six shifts from `shift_ranges[(eid, side, k)]`, cross names from `cross_ranges[(eid, side)]`."""
    rows = []
    for s in stmts:
        if s["join_status"] != "unique":
            continue
        key = (int(s["eid"]), s["side"])
        for k in K.SHIFTS:
            lo, hi = shift_ranges[key + (k,)]
            rows.append({"stmt_id": s["stmt_id"], "control": "shifted", "k": k, "symbol": s["ticker"], "eid": s["eid"], "side": s["side"], "range_lo_raw": lo,
                         "range_hi_raw": hi, "session_range_raw": "", "tolerance": "", "inside": ""})
        for sym, (lo, hi) in cross_ranges.get(key, {}).items():
            rows.append({"stmt_id": s["stmt_id"], "control": "cross", "k": "", "symbol": sym, "eid": "", "side": "", "range_lo_raw": lo, "range_hi_raw": hi,
                         "session_range_raw": "", "tolerance": "", "inside": ""})
    return rows


def ladder_fixture(reconstruction: str = "true"):
    """Stock AAA trades a different $10 band every session (session i: 100+10i .. 102+10i); stock BBB trades 500+. Twelve one-session windows on
    AAA, one clean fill statement inside each. `reconstruction`: 'true' (the real windows), 'shifted' (every window one session late), or
    'swapped' (the statements' prices read against BBB's windows on the same days)."""
    days = cal(20)
    ws, ranges, rows, shift_ranges, cross_ranges = [], {}, [], {}, {}
    band = lambda i: (100.0 + 10 * i, 102.0 + 10 * i)
    for n in range(12):
        i = n + 3
        eid, side = n + 1, ("buy" if n % 2 == 0 else "sale")
        action = "buy" if side == "buy" else "sell_unspec"
        kind = "entry" if side == "buy" else "exit"
        j = i + 1 if reconstruction == "shifted" else i
        lo, hi = (500.0 + 10 * i, 520.0 + 10 * i) if reconstruction == "swapped" else band(j)
        ws.append(window(eid, "AAA", side, days[j], days[j]))
        ranges[(eid, side)] = range_row(eid, side, days[j], days[j], lo, hi)
        for k in K.SHIFTS:
            shift_ranges[(eid, side, k)] = (500.0 + 10 * (j + k), 520.0 + 10 * (j + k)) if reconstruction == "swapped" else band(j + k)
        cross_ranges[(eid, side)] = {"BBB": band(i) if reconstruction == "swapped" else (500.0 + 10 * i, 520.0 + 10 * i)}
        rows.append(sheet_row(f"s{n}", days[j], "AAA", action, 101.0 + 10 * i, kind=kind))
    tup = K.windows_tuple(ws)
    return ws, ranges, rows, CAP.index_windows(tup), CAP.index_holds(tup), shift_ranges, cross_ranges


def scored_block(reconstruction: str, floor: int = 0) -> dict:
    ws, ranges, rows, by_sym, holds, shift_ranges, cross_ranges = ladder_fixture(reconstruction)
    eng = FakeEngine(ws)
    st = M3.build_statements(rows, by_sym, holds, ranges, eng, SESS)
    assert all(s["join_status"] == "unique" for s in st)
    ctrl = controls_for(st, ranges, shift_ranges, cross_ranges)
    M3.score(st, ctrl, ranges, eng, SESS)
    prim = [s for s in st if M3.is_primary(s)]
    assert len(prim) == 12
    return M3.r1_block(prim, floor=floor)


def test_r1_gap_bar_passes_on_the_true_reconstruction():
    b = scored_block("true")
    assert b["real"] == 100.0 and b["shifted"] == 0.0 and b["cross"] == 0.0
    assert b["gap_shifted"] == 100.0 and b["gap_cross"] == 100.0 and b["verdict"] == K.VERDICT_PASS and b["label"] == K.LABEL_R1_PASS


def test_r1_gap_bar_fails_on_a_deliberately_shifted_window():
    b = scored_block("shifted")
    assert b["real"] == 0.0                                        # the stated prices miss the late windows
    assert b["shifted"] == pytest.approx(100.0 / 6)                # one of the six shifts lands back on the truth
    assert b["gap_shifted"] < K.GAP_BAR_POINTS and b["verdict"] == K.VERDICT_FAIL and b["label"] == K.LABEL_R1_FAIL


def test_r1_gap_bar_fails_on_a_deliberately_swapped_symbol():
    b = scored_block("swapped")
    assert b["real"] == 0.0 and b["cross"] == 100.0               # the other held name's window holds the price, ours does not
    assert b["gap_cross"] < K.GAP_BAR_POINTS and b["verdict"] == K.VERDICT_FAIL


def test_the_section_9_floor_is_read_on_the_scored_n_and_carries_the_would_be_verdict():
    b = scored_block("true", floor=K.T1_FLOOR)                     # 12 scored < 100, whatever the input count
    assert b["verdict"] == K.VERDICT_ND and b["would_be"] == K.VERDICT_PASS and b["label"] == K.LABEL_R1_NOT_DECIDABLE
    assert K.gap_bar(100.0, 0.0, 0.0, 99)["verdict"] == K.VERDICT_ND and K.gap_bar(100.0, 0.0, 0.0, 100)["verdict"] == K.VERDICT_PASS
    g = K.gap_bar(80.0, 50.0, 40.0, 150)
    assert g["verdict"] == K.VERDICT_PASS and g["gap_shifted"] == 30.0 and g["gap_cross"] == 40.0
    assert K.gap_bar(80.0, 60.0, 40.0, 150)["verdict"] == K.VERDICT_FAIL                      # one control under 25 points fails
    assert K.gap_bar(80.0, None, 40.0, 150)["verdict"] == K.VERDICT_ND                       # a missing control cannot pass
    args = K.gap_bar.__code__.co_varnames[:K.gap_bar.__code__.co_argcount]
    assert "n_scored" in args and "n_t1" not in args


def test_the_primary_is_chosen_by_the_readers_labels_never_by_where_the_statement_landed():
    """R85: a holding/entry, a sale action with an entry price, a buy with an exit price, an unstated and an approx_earlier day each join a
    window and have a range, and each stays OUT of the primary — on the beside lines, which carry no bar."""
    ws, ranges, rows, by_sym, holds, shift_ranges, cross_ranges = ladder_fixture("true")
    d = rows[1]["stream_date"]                                                                  # position 2's sale window day
    rows += [sheet_row("h", d, "AAA", "holding", 131.0),                                        # a past entry price said while holding
             sheet_row("x", d, "AAA", "sell_part", 131.0, kind="entry"),                        # an entry price on a sale action
             sheet_row("y", d, "AAA", "buy", 141.0, kind="exit"),                               # an exit price on a buy action
             sheet_row("u", d, "AAA", "sell_unspec", 141.0, kind="exit", day="unstated"),        # chart pointing
             sheet_row("v", d, "AAA", "sell_unspec", 141.0, kind="exit", day="approx_earlier")]  # 'last week'
    eng = FakeEngine(ws)
    st = M3.build_statements(rows, by_sym, holds, ranges, eng, SESS)
    by = {s["stmt_id"]: s for s in st}
    assert all(by[x]["join_status"] == "unique" and by[x]["range_lo_raw"] != "" for x in "hxyuv")
    assert [M3.is_primary(by[x]) for x in "hxyuv"] == [False] * 5
    assert [M3.is_unmatched_fill(by[x]) for x in "hxy"] == [True] * 3 and [M3.is_unnamed_day_fill(by[x]) for x in "uv"] == [True, True]
    assert sum(M3.is_primary(s) for s in st) == 12
    M3.score(st, controls_for(st, ranges, shift_ranges, cross_ranges), ranges, eng, SESS)
    say = K.Say()
    res = M3.report_scores(say, st, ranges, len(st), SESS)
    text = "\n".join(say.lines)
    assert res["r1"]["n"] == 12 and res["anchors"][(2, "sale")]["n"] == 1                       # the beside statements never anchor
    assert "holding/entry or side-mismatched fills" in text and "matched fills, unstated / approx day" in text
    assert re.search(r"holding/entry or side-mismatched fills\s+3\s", text) and re.search(r"unstated / approx day\s+2\s", text)


def test_only_the_primary_line_carries_a_verdict_every_other_row_is_beside():
    ws, ranges, rows, by_sym, holds, shift_ranges, cross_ranges = ladder_fixture("true")
    rows.append(sheet_row("g", rows[0]["stream_date"], "AAA", "buy", 131.0, garbled="Y"))
    eng = FakeEngine(ws)
    st = M3.build_statements(rows, by_sym, holds, ranges, eng, SESS)
    M3.score(st, controls_for(st, ranges, shift_ranges, cross_ranges), ranges, eng, SESS)
    say = K.Say()
    M3.report_scores(say, st, ranges, len(st), SESS)
    r1_rows = [ln for ln in say.lines if re.match(r"\s+(all|2020|2021-22|without flickers|flickers only|without daily-only|daily-only only|same_in_in|"
                                                  r"pre_market_possible|holding/entry|matched fills|garbled fills|levels)", ln)]
    verdicts = [ln for ln in r1_rows if (K.VERDICT_ND in ln or ln.rstrip().endswith(K.VERDICT_PASS) or ln.rstrip().endswith(K.VERDICT_FAIL)) and K.NO_BAR not in ln]
    assert len(verdicts) == 1 and verdicts[0].lstrip().startswith("all")                      # the bar
    assert sum(K.NO_BAR in ln for ln in r1_rows) == len(r1_rows) - 1
    b = M3.r1_block([s for s in st if M3.is_primary(s)])
    assert M3.r1_row("x", b)[-1] == K.NO_BAR and M3.r1_row("x", b, bar=True)[-1].startswith(K.VERDICT_ND)


def test_anchors_mean_the_primary_fills_and_flag_a_spread_beyond_the_tolerance():
    ws, ranges, rows, by_sym, holds, shift_ranges, cross_ranges = ladder_fixture("true")
    rows.append(sheet_row("dup", rows[0]["stream_date"], "AAA", "add", 131.0 + 5.0))                    # a second fill on position 1's buy side, $5 off
    eng = FakeEngine(ws)
    st = M3.build_statements(rows, by_sym, holds, ranges, eng, SESS)
    M3.score(st, controls_for(st, ranges, shift_ranges, cross_ranges), ranges, eng, SESS)
    a = M3.anchors(st)
    assert a[(1, "buy")]["n"] == 2 and a[(1, "buy")]["price_raw"] == 133.5 and a[(1, "buy")]["differ"] and a[(1, "buy")]["outside"]
    assert a[(2, "sale")]["n"] == 1 and not a[(2, "sale")]["differ"] and not a[(2, "sale")]["outside"]
    by = {s["stmt_id"]: s for s in st}
    assert by["s0"]["inside"] is True and by["dup"]["inside"] is False                               # R86: the per-statement flag differs from the side's


def test_report_scores_runs_on_the_ladder_fixture_and_prints_the_verdict_lines():
    ws, ranges, rows, by_sym, holds, shift_ranges, cross_ranges = ladder_fixture("true")
    rows.append(sheet_row("mid", "2020-06-09", "AAA", "buy", 999.0, shares="1000", dollars="5000"))        # R4 input; lands on a sale window by day alone
    rows.append(sheet_row("far", "2020-06-26", "AAA", "buy", 50.0, day="stated_earlier"))                  # other_date: 5 sessions after the last window (R88)
    eng = FakeEngine(ws)
    st = M3.build_statements(rows, by_sym, holds, ranges, eng, SESS)
    M3.score(st, controls_for(st, ranges, shift_ranges, cross_ranges), ranges, eng, SESS)
    say = K.Say()
    res = M3.report_scores(say, st, ranges, len(st), SESS)
    text = "\n".join(say.lines)
    assert f"{K.LINE_R1}{K.VERDICT_ND}" in text and "would read PASS" in text and K.LABEL_R1_NOT_DECIDABLE in text
    assert f"{K.LINE_R5}{K.VERDICT_PASS}" in text and K.LABEL_DENSITY_ND in text and "R3 day offset" in text and "R4 implied move" in text
    assert res["r1"]["n"] == 13 and res["r5"]["n"] == 13 and res["r5"]["misses"] == [("buy", "sale")]
    assert len(res["anchors"]) == 12 and res["anchors"][(4, "sale")]["n"] == 2 and res["anchors"][(4, "sale")]["differ"]     # 'mid' joins position 4's sale side
    assert "pre_market_possible (any bracket)" in text and "garbled fills" in text and re.search(r"mid\s+AAA\s+1000\.0\s+5000\.0", text) and "no band (a side has no range)" in text and "n = 0: the 70% bar is printed" in text
    assert "R3 beside (secondary, R88)" in text and re.search(r"stated_earlier\s+1\s+\+5:1\s+5\s+100\.0%", text)    # the other_date statement's offset


# ═════════════════════════════════════════════════════════════════════════════════════════════ the real control path on synthetic bars (review F8)
def write_export(path: Path, tickers: dict, cal_: list) -> None:
    """A header-less export (ticker,date,o,h,l,c,v) with SPY (the calendar) and the given tickers' bars (the points tests' writer)."""
    with gzip.open(path, "wt") as fh:
        for d in cal_:
            fh.write(f"SPY,{d},300,301,299,300,1000000\n")
        for tk, rows in tickers.items():
            for d, (o, h, l, c, v) in rows.items():
                fh.write(f"{tk},{d},{o},{h},{l},{c},{v}\n")


@pytest.fixture
def bar_world(tmp_path):
    """Daily bars only (no minute file: every window is daily_only): AAA trades 100+20i..102+20i on session i (a $20 step, wider than the
    1%-of-price tolerance at these prices), BBB 500+20i..520+20i; the calendar runs 150 sessions from 2020-01-02 so every day used has
    60+ sessions of history."""
    cal_ = cal(150, (2020, 1, 2))
    S2 = C.Sessions(cal_)
    rows_a = {d: (100.0 + 20 * i + 1, 102.0 + 20 * i, 100.0 + 20 * i, 101.0 + 20 * i, 1000.0) for i, d in enumerate(cal_)}
    rows_b = {d: (500.0 + 20 * i + 1, 520.0 + 20 * i, 500.0 + 20 * i, 510.0 + 20 * i, 1000.0) for i, d in enumerate(cal_)}
    export = tmp_path / "daily.csv.gz"
    write_export(export, {"AAA": rows_a, "BBB": rows_b}, cal_)
    daily, _info = C.load_daily_subset(str(export), keep={"AAA", "BBB"}, cut=C.CUT_B)
    bars = P.Bars({"A": daily, "B": daily}, C.MinuteStore({}, {}), S2)
    return {"S": S2, "bars": bars, "cal": cal_}


def test_controls_through_the_range_engine_on_synthetic_bars(bar_world):
    S2, bars, days = bar_world["S"], bar_world["bars"], bar_world["cal"]
    ws = []
    I0 = 70
    for n in range(12):
        i = I0 + n
        eid, side = n + 1, ("buy" if n % 2 == 0 else "sale")
        ws.append(window(eid, "AAA", side, days[i], days[i], S=S2))
        ws.append(window(100 + eid, "BBB", side, days[i], days[i], S=S2))
    L = {"S": S2, "bars": bars, "buys": [w for w in ws if w.side == "buy"], "sales": [w for w in ws if w.side == "sale"], "rawmap": {}, "splits": {}}
    engine = K.RangeEngine(L)
    ranges = {}
    for w in ws:
        row = engine.range_row(K.shifted_window(w, 0, S2))
        assert row["resolution"] == "daily_only" and K.raw_range(row) is not None
        ranges[(w.eid, w.side)] = row
    assert K.raw_range(ranges[(1, "buy")]) == (100.0 + 20 * I0, 102.0 + 20 * I0)                     # the day's low..high, raw = adjusted (no splits)
    sh = engine.shifted(ws[0], -1)
    assert K.raw_range(sh["row"]) == (100.0 + 20 * (I0 - 1), 102.0 + 20 * (I0 - 1)) and sh["window"].lo == days[I0 - 1]
    assert engine.session_range_raw(sh["window"], days[I0 - 1]) == pytest.approx(2.0)
    rows = [sheet_row(f"s{n}", days[I0 + n], "AAA", "buy" if n % 2 == 0 else "sell_unspec", 101.0 + 20 * (I0 + n), kind="entry" if n % 2 == 0 else "exit")
            for n in range(12)]
    tup = K.windows_tuple(ws)
    by_sym, holds = CAP.index_windows(tup), CAP.index_holds(tup)
    st = M3.build_statements(rows, by_sym, holds, ranges, engine, S2)
    assert all(s["join_status"] == "unique" and s["ticker"] == "AAA" for s in st)
    say = K.Say()
    ctrl = M3.build_controls(st, by_sym, ranges, engine, S2, say)
    assert sum(c["control"] == "shifted" for c in ctrl) == 72 and sum(c["control"] == "cross" for c in ctrl) == 12
    assert all(c["range_lo_raw"] != "" for c in ctrl) and {c["symbol"] for c in ctrl if c["control"] == "cross"} == {"BBB"}
    M3.score(st, ctrl, ranges, engine, S2)
    b = M3.r1_block([s for s in st if M3.is_primary(s)], floor=0)
    assert b["n"] == 12 and b["real"] == 100.0 and b["shifted"] == 0.0 and b["cross"] == 0.0 and b["verdict"] == K.VERDICT_PASS
    # the same statements against windows one session late, through the same engine: the gap collapses
    late = [window(w.eid, w.sym, w.side, days[S2.le(w.lo) + 1], days[S2.le(w.hi) + 1], S=S2) for w in ws if w.sym == "AAA"] + [w for w in ws if w.sym == "BBB"]
    L2 = dict(L, buys=[w for w in late if w.side == "buy"], sales=[w for w in late if w.side == "sale"])
    engine2 = K.RangeEngine(L2)
    ranges2 = {(w.eid, w.side): engine2.range_row(K.shifted_window(w, 0, S2)) for w in late}
    tup2 = K.windows_tuple(late)
    rows2 = [dict(r, stream_date=days[S2.le(r["stream_date"]) + 1]) for r in rows]                  # said on the late windows' days, the true days' prices
    st2 = M3.build_statements(rows2, CAP.index_windows(tup2), CAP.index_holds(tup2), ranges2, engine2, S2)
    assert all(s["join_status"] == "unique" and s["dist"] == 0 for s in st2)
    ctrl2 = M3.build_controls(st2, CAP.index_windows(tup2), ranges2, engine2, S2, K.Say())
    M3.score(st2, ctrl2, ranges2, engine2, S2)
    b2 = M3.r1_block([s for s in st2 if M3.is_primary(s)], floor=0)
    assert b2["real"] == 0.0 and b2["shifted"] == pytest.approx(100.0 / 6) and b2["verdict"] == K.VERDICT_FAIL


# ═════════════════════════════════════════════════════════════════════════════════════════════ R3, R4
def test_day_offsets_implied_move_and_outcome_band():
    assert K.day_offsets("2020-06-10", "2020-06-08", "2020-06-09", SESS) == (2, 1)
    assert K.implied_move(-180000.0, 20000.0, 45.0) == pytest.approx(-20.0)
    assert K.implied_move(1.0, 0.0, 45.0) is None
    lo, hi = K.outcome_band(40.0, 42.0, 50.0, 52.0)
    assert lo == pytest.approx(100 * (50 / 42 - 1)) and hi == pytest.approx(30.0)


# ═════════════════════════════════════════════════════════════════════════════════════════════ 6c: the account path (a constant mix, R76)
def trade(eid, sessions, a, b, ret, side="long"):
    return {"eid": eid, "entry_session": sessions[a], "exit_session": sessions[b], "daily": K.geometric_daily(ret, sessions[a:b + 1], side)}


def test_marks_and_geometric_daily_compound_to_the_trades_return():
    d = K.marks_to_daily([("d1", 1.02), ("d2", 1.05), ("d3", 1.10)])
    assert list(d) == ["d1", "d2", "d3"] and d["d1"] == pytest.approx(0.02) and d["d2"] == pytest.approx(1.05 / 1.02 - 1)
    assert np.prod([1 + r for r in d.values()]) == pytest.approx(1.10)
    s = K.marks_to_daily([("d1", 1.02), ("d2", 0.90)], "short")
    assert s["d1"] == pytest.approx(-0.02) and s["d2"] == pytest.approx(-(0.90 / 1.02 - 1))
    g = K.geometric_daily(0.10, ["a", "b", "c", "d"])
    assert len(g) == 4 and len(set(round(v, 12) for v in g.values())) == 1 and np.prod([1 + r for r in g.values()]) == pytest.approx(1.10)
    assert K.geometric_daily(-1.5, ["a", "b"])["a"] == -1.0                                                 # a wiped-out name


def test_account_path_is_a_constant_mix_that_never_deploys_more_than_the_exposure():
    sessions = cal(12)
    one = [trade(1, sessions, 0, 3, 0.10)]
    p = K.account_path(one, sessions, 1.0)
    assert p[sessions[3]] == pytest.approx(1.10) and p[sessions[11]] == pytest.approx(1.10) and p[sessions[0]] > 1.0     # one name: the whole account, telescoping
    assert K.account_path(one, sessions, 0.5)[sessions[3]] == pytest.approx(np.prod([1 + 0.5 * r for r in one[0]["daily"].values()]))
    # five entries on consecutive sessions, each +10% over five sessions (review F4's planted case): the money deployed is 1.0 on every held
    # session, never 2.3x; the account compounds the mean daily return of the names open, 9 sessions at 1.1^(1/5)
    five = [trade(k + 1, sessions, k, k + 4, 0.10) for k in range(5)]
    dep = K.deployed_share(five, sessions, 1.0)
    assert all(dep[d] == 1.0 for d in sessions[:9]) and dep[sessions[9]] == 0.0
    p5 = K.account_path(five, sessions, 1.0)
    assert p5[sessions[8]] == pytest.approx(1.10 ** (9 / 5)) and p5[sessions[8]] < 1.228
    # two identical names on one span read as one; a + and a - of the same size on one span nearly cancel
    assert K.account_path([trade(1, sessions, 0, 3, 0.10), trade(2, sessions, 0, 3, 0.10)], sessions)[sessions[3]] == pytest.approx(1.10)
    pm = K.account_path([trade(1, sessions, 0, 3, 0.10), trade(2, sessions, 0, 3, -0.10)], sessions)[sessions[3]]
    assert 0.99 < pm < 1.0
    # a SLOT (held, no range) takes a place in N and halves the weight of the known name
    with_slot = K.account_path(one + [{"eid": 9, "entry_session": sessions[0], "exit_session": sessions[3], "daily": {}}], sessions)
    assert 1.0 < with_slot[sessions[3]] < 1.10 and with_slot[sessions[3]] == pytest.approx(np.prod([1 + 0.5 * r for r in one[0]["daily"].values()]))
    # a short's daily returns are negated; a wipe-out floors at 0
    sh = K.account_path([trade(1, sessions, 0, 3, -0.10, "short")], sessions)
    assert sh[sessions[3]] > 1.0
    assert K.account_path([{"eid": 1, "entry_session": sessions[0], "exit_session": sessions[0], "daily": {sessions[0]: -1.0}}], sessions, 1.5)[sessions[0]] == 0.0
    # ytd and the distance to his figure
    assert K.ytd(p, sessions, sessions[5]) == pytest.approx(10.0) and K.ytd(p, sessions, "2019-12-31") is None
    assert K.distance_to_his(120.0, 100.0, 120.0) == 0.0 and K.distance_to_his(90.0, 100.0, None) == 10.0 and K.distance_to_his(130.0, 100.0, 120.0) == 10.0
    assert K.distance_to_his(900.0, 150.0, None) == 0.0 and K.distance_to_his(None, 1.0, 2.0) is None
    assert M4.trade_return(100.0, 110.0, "long") == pytest.approx(0.10) and M4.trade_return(100.0, 90.0, "short") == pytest.approx(0.10)


class _DailyStub:
    def __init__(self, dates: list, closes: list):
        self.c = np.array(closes)
        self.h, self.l, self.v = self.c * 1.02, self.c * 0.98, np.full(len(closes), 1000.0)
        self.ix = {d: i for i, d in enumerate(dates)}


class _BarsStub:
    def __init__(self, stub):
        self.stub = stub

    def daily(self, export, tk):
        return self.stub, self.stub.ix


def test_marks_for_reads_the_closes_and_falls_back_to_a_geometric_spread():
    sessions = cal(6)
    bars = _BarsStub(_DailyStub(sessions, [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]))
    marks, src = M4.marks_for(bars, "A", "AAA", sessions[1], sessions[3], 10.0, 13.5, SESS)
    assert src == "closes" and marks == [(sessions[1], 1.1), (sessions[2], 1.2), (sessions[3], 1.35)]   # closes over the entry price, the exit price last
    marks2, src2 = M4.marks_for(_BarsStub(_DailyStub([], [])), "A", "AAA", sessions[1], sessions[3], 10.0, 13.5, SESS)
    assert src2 == "geometric" and marks2[-1][1] == pytest.approx(1.35) and len(marks2) == 3
    marks3, src3 = M4.marks_for(_BarsStub(_DailyStub([], [])), "A", "AAA", sessions[1], sessions[1], 10.0, 13.5, SESS)
    assert src3 == "closes" and marks3 == [(sessions[1], 1.35)]                                            # one session: the exit price is the mark
    gap = _DailyStub([sessions[1], sessions[3]], [10.0, 13.0])                                               # a hole on session 2 carries the mark
    assert M4.marks_for(_BarsStub(gap), "A", "AAA", sessions[1], sessions[3], 10.0, 13.5, SESS)[0] == [(sessions[1], 1.0), (sessions[2], 1.0), (sessions[3], 1.35)]


def test_build_trades_readings_sides_slots_and_anchors_on_a_fixture():
    ws, ranges, by_sym, holds = two_positions()
    ws.append(window(3, "CCC", "buy", "2020-06-04", "2020-06-04"))                                  # one side only: not a trade
    ranges[(3, "buy")] = range_row(3, "buy", "2020-06-04", "2020-06-04", 10.0, 11.0)
    ws += [window(4, "DDD", "buy", "2020-06-04", "2020-06-04"), window(4, "DDD", "sale", "2020-06-08", "2020-06-08")]   # held, no range: a slot
    ranges[(4, "buy")] = dict(range_row(4, "buy", "2020-06-04", "2020-06-04", 10.0, 11.0), range_lo="", range_hi="", range_lo_raw="", range_hi_raw="")
    ranges[(4, "sale")] = range_row(4, "sale", "2020-06-08", "2020-06-08", 10.0, 11.0)
    ranges[(1, "sale")]["avg_traded_price"] = ""                                                    # a daily-only sale side: the typical-price fallback

    class Eng(FakeEngine):
        class bars:
            @staticmethod
            def daily(export, tk):
                b = type("B", (), {})()
                b.h, b.l, b.c, b.v = np.array([52.0]), np.array([50.0]), np.array([51.0]), np.array([1000.0])
                return b, {"2020-06-10": 0}
    eng = Eng(ws)
    for w in ws:
        w.export, w.bar_sym = "A", w.sym
        w.reach = [(w.lo, None, None)]
    trades, slots, n = M4.build_trades(ranges, eng, {(2, "buy"): 405.0}, {2: "short"}, SESS)
    assert n["round_trips"] == 3 and n["one_side_only"] == 1 and len(trades) == 2 and len(slots) == 1 and slots[0]["eid"] == 4 and slots[0]["daily"] == {}
    t1, t2 = {t["eid"]: t for t in trades}[1], {t["eid"]: t for t in trades}[2]
    assert t1["sale"]["mid_source"] == "daily_typical" and t1["sale"]["mid"] == pytest.approx(51.0) and t1["ret_middle"] == pytest.approx(51.0 / 41.0 - 1)
    assert t1["ret_worst"] == pytest.approx(50.0 / 42.0 - 1) and t1["ret_best"] == pytest.approx(52.0 / 40.0 - 1)
    assert t2["side"] == "short" and t2["ret_middle"] == pytest.approx(1 - 510.0 / 410.0) and t2["ret_anchored"] == pytest.approx(1 - 510.0 / 405.0)
    assert (t1["entry_session"], t1["exit_session"]) == ("2020-06-03", "2020-06-10")
    assert np.prod([1 + r for r in t1["daily_middle"].values()]) == pytest.approx(1 + t1["ret_middle"]) and len(t1["daily_middle"]) == 6
    assert set(t1["daily_anchored"]) == set(t1["daily_middle"]) and t1["marks_source"] == "geometric"       # no close on the hold but the exit day's
    assert M4._compound(t1["daily_middle"]) == pytest.approx(t1["ret_middle"])


def test_the_side_of_a_position_is_read_from_statements_beside_it_too():
    rows = [{"join_status": "unique", "eid": "1", "side": "buy", "anchor_price_bar": "40.5", "side_said": "", "action": "buy", "beside_eid": ""},
            {"join_status": "none", "eid": "", "side": "", "anchor_price_bar": "", "side_said": "", "action": "shorted", "beside_eid": "2"},     # mid-hold (R82)
            {"join_status": "ambiguous", "eid": "", "side": "", "anchor_price_bar": "", "side_said": "short", "action": "holding", "beside_eid": "3"},  # a one-position tie (R83)
            {"join_status": "none", "eid": "", "side": "", "anchor_price_bar": "", "side_said": "short", "action": "shorted", "beside_eid": ""}]    # names no position
    anchors, shorts = M4.anchors_and_sides(rows)
    assert anchors == {(1, "buy"): 40.5} and shorts == {2: "short", 3: "short"}


def test_report_readouts_runs_on_a_two_trade_fixture_and_the_shifted_trades_outside_the_path_are_dropped():
    sessions = M4.path_sessions([{"entry_session": "2020-06-03", "exit_session": "2020-06-10"}], SESS)
    assert sessions[0] == "2020-06-01" and sessions[-1] == "2020-06-15"                         # the year start, padded by the widest shift at the end
    h1, h2 = sessions[sessions.index("2020-06-03"):sessions.index("2020-06-10") + 1], sessions[sessions.index("2020-06-03"):sessions.index("2020-06-12") + 1]
    trades = [{"eid": 1, "sym": "AAA", "entry_session": "2020-06-03", "exit_session": "2020-06-10", "flicker": False, "side": "long", "year": 2020,
               "ret_middle": 0.2, "ret_anchored": 0.25, "ret_worst": 0.1, "ret_best": 0.3, "daily_middle": K.geometric_daily(0.2, h1), "daily_anchored": K.geometric_daily(0.25, h1)},
              {"eid": 2, "sym": "BBB", "entry_session": "2020-06-03", "exit_session": "2020-06-12", "flicker": True, "side": "short", "year": 2020,
               "ret_middle": -0.1, "ret_anchored": -0.1, "ret_worst": -0.2, "ret_best": 0.0, "daily_middle": K.geometric_daily(0.1, h2, "short"),
               "daily_anchored": K.geometric_daily(0.1, h2, "short")}]
    paths = {M4.arm_name(*a): M4.arm_path(trades, sessions, *a) for a in M4.ARMS}
    assert paths[M4.arm_name(1.0, "flickers_out", "middle")]["2020-06-12"] == pytest.approx(1.20)             # the flicker out: one name, telescoping
    assert paths[M4.arm_name(1.0, "flickers_out", "anchored")]["2020-06-12"] == pytest.approx(1.25)
    both = paths[M4.arm_name(1.0, "flickers_in", "middle")]["2020-06-12"]
    r1, r2 = trades[0]["daily_middle"], trades[1]["daily_middle"]
    acct = 1.0
    for d in sessions:
        rs = [r[d] for r in (r1, r2) if d in r]
        acct *= 1 + (sum(rs) / len(rs) if rs else 0.0)
    assert both == pytest.approx(acct) and both < 1.20
    kept, off = M4.within_sessions([{"eid": 1, "entry_session": "2020-06-03", "exit_session": "2020-06-30", "daily": {}}], sessions)
    assert kept == [] and off == 1
    assert M4.shifted_slots([{"eid": 9, "entry_session": "2020-06-02", "exit_session": "2020-06-03", "flicker": False}], SESS, -1) == \
        [{"eid": 9, "entry_session": "2020-06-01", "exit_session": "2020-06-02", "flicker": False, "daily": {}}]
    assert M4.shifted_slots([{"eid": 9, "entry_session": "2020-06-01", "exit_session": "2020-06-03", "flicker": False}], SESS, -1) == []
    shifted = {k: K.account_path([{"eid": 1, "entry_session": "2020-06-04", "exit_session": "2020-06-11", "daily": K.geometric_daily(0.2, sessions[3:9])}], sessions, 1.0) for k in K.SHIFTS}
    say = K.Say()
    at_rows, per_session = M4.report_readouts(say, trades, sessions, paths, shifted)
    text = "\n".join(say.lines)
    assert len(at_rows) == 15 and len(per_session) == len(sessions) and "(4) the 2021 drawdown" in text and "WOULD-FAIL-IF" in text
    assert at_rows[0]["date"] == "2020-06-09" and at_rows[0]["real_closer_than_shifts"] == "0/6"


# ═════════════════════════════════════════════════════════════════════════════════════════════ the run gates
def _paths(tmp_path, stage: str, monkeypatch):
    d = {"dry": str(tmp_path / f"{stage}_dry.txt"), "run": str(tmp_path / f"{stage}_run.txt"), "refused": str(tmp_path / f"{stage}_refused.txt"),
         "pins": str(tmp_path / f"{stage}_pins.txt")}
    monkeypatch.setattr(K, "P03" if stage == "6b" else "P04", d)
    return d


def _stage_inputs(tmp_path, monkeypatch) -> None:
    """Every file a 6b / 6c pin names, present in tmp (so no stage pin reads ABSENT in CI, where the real sheets are not on disk)."""
    sheets = tuple(str(tmp_path / f"reader1_t1_v2_part{k}.tsv") for k in (1, 2, 3))
    for p in sheets:
        Path(p).write_text("stmt_id\n")
    monkeypatch.setattr(K, "V2_SHEETS", sheets)
    monkeypatch.setattr(K, "WORDING_V2", str(tmp_path / "wording.txt"))
    Path(K.WORDING_V2).write_text("v2\n")
    monkeypatch.setattr(C, "OUTPUTS", {k: str(tmp_path / f"{k}.tsv") for k in ("candidates", "ranges", "coverage")})
    for p in C.OUTPUTS.values():
        Path(p).write_text("eid\n")
    monkeypatch.setattr(K, "JOINS_6A", str(tmp_path / "joins.tsv"))
    Path(K.JOINS_6A).write_text("x\n")


def _freeze(doc: Path, pins: dict) -> None:
    doc.write_text("# body\n\n<!-- FREEZE -->\n## Freeze record\n" + "\n".join(f"- {k}: {v}" for k, v in pins.items()) + "\n")


def test_run_gates_refuse_until_everything_is_in_order(tmp_path, monkeypatch):
    p3, p4 = _paths(tmp_path, "6b", monkeypatch), _paths(tmp_path, "6c", monkeypatch)
    _stage_inputs(tmp_path, monkeypatch)
    monkeypatch.setattr(K, "OUT_6B", {"check_r1_r5": str(tmp_path / "c.tsv"), "control_ranges": str(tmp_path / "cr.tsv")})
    monkeypatch.setattr(K, "OUT_6C", {"band_by_session": str(tmp_path / "b.tsv"), "band_at_dates": str(tmp_path / "d.tsv")})
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    doc = tmp_path / "doc.md"
    doc.write_text("# body\n\n<!-- FREEZE -->\n## Freeze record\n")
    pr = K.run_gate("6b", str(doc))
    assert any("has not completed" in x for x in pr) and any("pins not below" in x for x in pr)
    Path(p3["dry"]).write_text("# x\n- modules: " + K.module_shas_line(K.MODULE_FILES_6B) + "\n\nRESULT: 3 claims, 2 OK, 1 MISMATCH\nDRY RUN COMPLETE\n")
    pr = K.run_gate("6b", str(doc))
    assert any("1 MISMATCH" in x for x in pr) and not any("has not completed" in x for x in pr)
    Path(p3["dry"]).write_text("# x\n- modules: stale\n\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert any("other code" in x for x in K.run_gate("6b", str(doc)))
    Path(p3["dry"]).write_text("# x\n- modules: " + K.module_shas_line(K.MODULE_FILES_6B) + "\n\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    pins = K.pins_6b(str(doc), p3["dry"])
    assert "doc_body" in pins and "dryrun6b_printout" in pins and "reader1_t1_v2_part1" in pins and "ranges" in pins
    assert set(K.stage_pin_keys(pins, str(doc))) >= {"reader1_t1_v2_part1", "ranges", "joins_6a", "03_check.py", "dryrun6b_printout"} and "doc_body" not in K.stage_pin_keys(pins, str(doc))
    _freeze(doc, pins)
    assert K.run_gate("6b", str(doc)) == []                                                          # the gate opens
    # an ABSENT stage pin is refused even though the word sits below the marker
    Path(K.JOINS_6A).unlink()
    pins_absent = K.pins_6b(str(doc), p3["dry"])
    assert pins_absent["joins_6a"] == "ABSENT"
    _freeze(doc, pins_absent)
    assert any("reading ABSENT" in x and "joins_6a" in x for x in K.run_gate("6b", str(doc)))
    Path(K.JOINS_6A).write_text("x\n")
    _freeze(doc, pins)
    assert K.run_gate("6b", str(doc)) == []
    Path(p3["run"]).write_text("stale run\n")
    assert any("outputs exist" in x for x in K.run_gate("6b", str(doc)))
    Path(p3["run"]).unlink()
    # 6c: a dry run made BEFORE 6b ran (its artefact line says ABSENT) is refused however it is pinned (review F3)
    Path(p4["dry"]).write_text("# x\n- modules: " + K.module_shas_line(K.MODULE_FILES_6C) + "\n" + K.LINE_6B_ARTEFACTS + K.artefacts_6b_line() +
                               "\n\nRESULT: 2 claims, 2 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert "ABSENT" in K.artefacts_6b_line()
    _freeze(doc, K.pins_6c(str(doc), p4["dry"]))
    pr = K.run_gate("6c", str(doc))
    assert any("6b has not run" in x for x in pr) and any("saw 6b's files absent" in x for x in pr) and any("reading ABSENT" in x for x in pr)
    Path(p3["run"]).write_text(f"{K.LINE_R1}{K.VERDICT_PASS} — gap 40.0\n{K.LINE_R5}{K.VERDICT_PASS} — 60 / 62\n")
    Path(K.OUT_6B["check_r1_r5"]).write_text("stmt_id\n")
    Path(K.OUT_6B["control_ranges"]).write_text("stmt_id\n")
    _freeze(doc, K.pins_6c(str(doc), p4["dry"]))                                                      # pins now carry the real shas, the dry run still says ABSENT
    pr = K.run_gate("6c", str(doc))
    assert any("saw 6b's files absent" in x for x in pr) and not any("reading ABSENT" in x for x in pr) and not any("6b has not run" in x for x in pr)
    # the dry run re-made after 6b: its artefact line matches the disk; the verdict checks still bite
    def dry6c():
        Path(p4["dry"]).write_text("# x\n- modules: " + K.module_shas_line(K.MODULE_FILES_6C) + "\n" + K.LINE_6B_ARTEFACTS + K.artefacts_6b_line() +
                                   "\n\nRESULT: 2 claims, 2 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
        _freeze(doc, K.pins_6c(str(doc), p4["dry"]))
    Path(p3["run"]).write_text(f"{K.LINE_R1}{K.VERDICT_FAIL} — gap 3.0\n{K.LINE_R5}{K.VERDICT_PASS} — 60 / 62\n")
    dry6c()
    pr = K.run_gate("6c", str(doc))
    assert any("R1 verdict is FAIL" in x for x in pr) and not any("R5 verdict" in x for x in pr) and not any("saw" in x for x in pr)
    Path(p3["run"]).write_text(f"{K.LINE_R1}{K.VERDICT_ND} — gap\n{K.LINE_R5}{K.VERDICT_FAIL} — 40 / 62\n")
    dry6c()
    pr = K.run_gate("6c", str(doc))
    assert any("R1 verdict is NOT" in x for x in pr) and any("R5 verdict is FAIL" in x for x in pr)
    Path(p3["run"]).write_text(f"{K.LINE_R1}{K.VERDICT_PASS} — gap 40.0\n{K.LINE_R5}{K.VERDICT_PASS} — 60 / 62\n")
    dry6c()
    assert K.run_gate("6c", str(doc)) == []
    # 03's printout changes after the 6c dry run: the dry run saw other files than the disk holds
    Path(p3["run"]).write_text(f"{K.LINE_R1}{K.VERDICT_PASS} — gap 41.0\n{K.LINE_R5}{K.VERDICT_PASS} — 61 / 62\n")
    _freeze(doc, K.pins_6c(str(doc), p4["dry"]))
    assert any("saw other 6b files" in x for x in K.run_gate("6c", str(doc)))
    dry6c()
    assert K.run_gate("6c", str(doc)) == []
    assert K.dry_mismatches(str(tmp_path / "absent.txt")) is None and K.dry_mismatches(p3["dry"]) == 0


def test_a_refused_run_writes_the_refusal_never_the_run_printout(tmp_path, monkeypatch):
    p3 = _paths(tmp_path, "6b", monkeypatch)
    p4 = _paths(tmp_path, "6c", monkeypatch)
    monkeypatch.setattr(K, "run_gate", lambda stage, doc=None: ["a reason"])
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])
    assert M3.main(["--run"]) == 3 and Path(p3["refused"]).exists() and not Path(p3["run"]).exists()
    assert M4.main(["--run"]) == 3 and Path(p4["refused"]).exists() and not Path(p4["run"]).exists()
    assert "REFUSED: a reason" in Path(p3["refused"]).read_text() and "REFUSED: a reason" in Path(p4["refused"]).read_text()


# ═════════════════════════════════════════════════════════════════════════════════════════════ the labels, the scan, the import test
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def test_consequence_labels_appear_verbatim_in_the_frozen_doc():
    body = _norm(DOC.read_text(encoding="utf-8").split("<!-- FREEZE -->")[0])
    for label in K.CONSEQUENCE_LABELS:
        assert _norm(label) in body, label
    assert K.LINE_R1 != K.LINE_R5 and K.HIS_DATED_POINTS[0][0] == "2020-06-09" and len(K.HIS_DATED_POINTS) == 15 and K.DRAWDOWN_2021 == ("2021-03-12", "2021-03-24")


def test_step6b_6c_modules_scan_clean_and_a_planted_name_fails(tmp_path):
    # source-pin-ok: the plan's guard (3) IS a scan of the step-5/6 source text; 03 / 04 / the shared module must hold none of the excluded names
    assert C.scan_identifiers([str(ASIS / n) for n in ("asis_check_common.py", "03_check.py", "04_band.py")]) == []
    planted = tmp_path / "planted.py"
    planted.write_text("def f(E):\n    return 'level_at'\n")
    assert [t for _p, _l, t in C.scan_identifiers([str(planted)])] == ["E", "'level_at'"]


def _fresh_import_report(module_path: Path, prelude: str = "") -> list:
    code = ("import importlib.util, sys, json\n" f"{prelude}\n"
            f"spec = importlib.util.spec_from_file_location('asis_mod_under_test', {str(module_path)!r})\n"
            "m = importlib.util.module_from_spec(spec); sys.modules['asis_mod_under_test'] = m; spec.loader.exec_module(m)\n"
            "print(json.dumps(m.C.rule_modules_loaded()))\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("name", ["asis_check_common.py", "03_check.py", "04_band.py"])
def test_fresh_interpreter_import_holds_no_rule_module(name, tmp_path):
    assert _fresh_import_report(ASIS / name) == []
    stub_dir = tmp_path / "_705_intraday_1025"
    stub_dir.mkdir()
    (stub_dir / "01_intra.py").write_text("PLANTED = True\n")
    prelude = (f"spec2 = importlib.util.spec_from_file_location('intra01_planted', {str(stub_dir / '01_intra.py')!r})\n"
               "m2 = importlib.util.module_from_spec(spec2); sys.modules['intra01_planted'] = m2; spec2.loader.exec_module(m2)")
    assert _fresh_import_report(ASIS / name, prelude) == ["intra01_planted"]


@pytest.mark.parametrize("name", ["asis_check_common.py", "03_check.py", "04_band.py"])
def test_no_network_model_client_or_rule_import(name):
    tree = ast.parse((ASIS / name).read_text(encoding="utf-8"))  # source-pin-ok: guards (4) and (5): no socket, no model client, no rule import may enter these modules
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert not (mods & {"socket", "requests", "urllib", "http", "anthropic", "openai", "psycopg2", "sqlalchemy", "random", "subprocess"})
    assert not [m for m in mods if m.startswith("_705") or m == "_cb_backtest"]


def test_no_absolute_machine_path_in_this_test_file():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "/Users" + "/" not in text


# ═════════════════════════════════════════════════════════════════════════════════════════════ the dry runs on real data
@needs_real_data
@pytest.mark.parametrize("mod,key", [(M3, "P03"), (M4, "P04")])
def test_dry_run_on_real_data_ends_complete_with_zero_mismatch(mod, key, tmp_path, monkeypatch):
    paths = dict(getattr(K, key))
    paths["dry"] = str(tmp_path / "dry.txt")                      # never the pinned printout
    monkeypatch.setattr(K, key, paths)
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])    # a shared pytest process may hold other tests' modules; the fresh-interpreter test covers the belt
    assert mod.main(["--dry-run"]) == 0
    lines = [ln for ln in Path(paths["dry"]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines[-1].startswith("DRY RUN COMPLETE") and K.dry_mismatches(paths["dry"]) == 0
    text = "\n".join(lines)
    assert "inside %" not in text and K.LINE_R1 not in text         # no R1 number in a dry run (R81)
    if key == "P04":
        assert K.printout_line(paths["dry"], K.LINE_6B_ARTEFACTS) is not None
