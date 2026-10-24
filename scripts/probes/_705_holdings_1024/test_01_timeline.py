"""Synthetic tests for 01_timeline.py: the full flag, the session windows (pre / in / closed), the snapshot state machine (entries,
exits, initial, inverted, blip fill, flicker), the duplicate-upload drop and the clock order (F1), the look-alike guard (F2), the
panel clocks on E (F3), the buy-dating rule (latest event, both, undated reasons, the Q1-2022 hole) and the positive-control matching.
No real data file is opened."""
import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_705_holdings01", os.path.join(HERE, "01_timeline.py"))
T = importlib.util.module_from_spec(spec)
sys.modules["_705_holdings01"] = T
spec.loader.exec_module(T)

# a synthetic calendar: Mon-Fri 2020-01-06 .. 2020-03-31, plus the Q1-2022 span for the hole flag
import pandas as pd  # noqa: E402

CAL = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-06", "2020-03-31")] + \
      [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2021-12-01", "2022-05-31")]
S = T.Sessions(CAL)


def snap(idx, vid, date, ctx, syms, full=True, ts=0):
    return T.Snap(idx=idx, frame_id=f"f{idx}", vid=vid, folder="positions", date=date, frame_date=date, ctx=ctx, ctx_raw=ctx,
                  et_time="", stream_ts=ts, resolution="1920x1080", list_name="A", symbols=list(syms), visible_n=len(syms),
                  total_n=len(syms) if full else len(syms) + 3, full=full, full_how="test")


def rec(visible, total, rows_y, body=(688, 1017), res="1920x1080"):
    return {"visible_n": visible, "total_n": total, "rows": [{"y": [y, y + 6]} for y in rows_y], "layout": {"body": list(body)},
            "resolution": res}


# ---- the full flag --------------------------------------------------------------------------------------------------------------------
def test_full_flag_footer_wins():
    assert T.full_flag(rec(5, 5, [696 + 18 * i for i in range(5)])) == (True, "footer_eq")
    assert T.full_flag(rec(18, 21, [696 + 18 * i for i in range(18)])) == (False, "footer_scrolled")


def test_full_flag_geometry_when_footer_unusable():
    # footer below the rows read (misread): the list ends well above the bottom -> full
    full, how = T.full_flag(rec(5, 3, [696 + 18 * i for i in range(5)]))
    assert full and how == "geom_full"
    # footer missing, the rows reach the bottom -> not full
    ys = [696 + 18 * i for i in range(18)]          # last row ends 696 + 17*18 + 6 = 1008; gap to 1017 = 9 < 27
    full, how = T.full_flag(rec(18, None, ys))
    assert not full and how == "geom_reaches_bottom"
    # one row, pitch defaults by resolution
    assert T.full_flag(rec(1, None, [696]))[0]
    assert T.full_flag(rec(0, None, []))[1] == "no_rows_no_footer"


def test_empty_list_with_footer_zero_is_full():
    assert T.full_flag({"visible_n": 0, "total_n": 0, "rows": [], "layout": {"body": [726, 1024]}, "resolution": "1920x1080"}) == (True, "footer_eq")


# ---- sessions and the asof / lo rules ---------------------------------------------------------------------------------------------------
def test_asof_and_lo_by_context():
    pre = snap(0, "v", "2020-01-08", "pre", [])
    ins = snap(1, "v", "2020-01-08", "in", [])
    clo = snap(2, "v", "2020-01-08", "closed", [])
    assert S.date(T.asof(pre, S)) == "2020-01-07"
    assert S.date(T.asof(ins, S)) == "2020-01-08"
    assert S.date(T.asof(clo, S)) == "2020-01-08"
    assert S.date(T.lo_after(pre, S)) == "2020-01-08"      # a buy the same day may be missing from a pre-market list
    assert S.date(T.lo_after(ins, S)) == "2020-01-08"      # and from an in-session one
    assert S.date(T.lo_after(clo, S)) == "2020-01-09"      # not from an after-close one
    # a weekend date (he streams on a Saturday): asof = Friday; lo = Monday
    sat = snap(3, "v", "2020-01-11", "in", [])
    assert S.date(T.asof(sat, S)) == "2020-01-10" and S.date(T.lo_after(sat, S)) == "2020-01-13"


# ---- the state machine -----------------------------------------------------------------------------------------------------------------
def build(seq):
    snaps = [snap(i, *args) for i, args in enumerate(seq)]
    tally = T.collections.Counter()
    T.blip_fill(snaps, tally)
    ents = T.timeline(snaps, S, tally)
    return snaps, ents, tally


def test_entries_exits_initial_and_windows():
    seq = [("v1", "2020-01-07", "pre", ["A", "B"]),                 # s0 full: initial A, B
           ("v1", "2020-01-07", "in", ["A", "B", "C"]),             # s1 full: C bought on 01-07 (window [01-07, 01-07])
           ("v2", "2020-01-08", "pre", ["A", "C"], False),          # s2 scrolled: B absent -> unknown, no exit
           ("v3", "2020-01-09", "pre", ["A", "C"]),                 # s3 full: B absent -> pending
           ("v3", "2020-01-09", "closed", ["A", "C", "D"]),         # s4 full: B absent again -> exit dated by s3: [01-07 (last seen s1 'in'), 01-08];
                                                                    #          D bought in [01-09, 01-09]
           ("v4", "2020-01-10", "pre", ["A", "C"]),                 # s5 full: D absent -> pending
           ("v5", "2020-01-13", "pre", ["A", "C"])]                 # s6 full: D absent again -> exit dated by s5: lo = 01-10 (after a closed list) > hi = 01-09 -> inverted
    snaps, ents, tally = build(seq)
    by = {e.sym: e for e in ents}
    assert tally["entries_initial"] == 2 and by["A"].initial and by["B"].initial
    c = by["C"]
    assert not c.initial and S.date(c.lo) == "2020-01-07" and S.date(c.hi) == "2020-01-07" and c.window_len == 1
    b = by["B"]
    assert b.exit_snap.idx == 3 and S.date(b.exit_lo) == "2020-01-07" and S.date(b.exit_hi) == "2020-01-08"
    d = by["D"]
    assert S.date(d.lo) == "2020-01-09" and S.date(d.hi) == "2020-01-09"
    assert d.exit_snap.idx == 5 and d.exit_lo == d.exit_hi and S.date(d.exit_hi) == "2020-01-09" and tally["exits_inverted_window"] == 1
    assert d.flicker and tally["entries_flicker"] == 1          # one stream, exit confirmed within 5 sessions
    assert not c.flicker                                       # C is seen in v1, v2, v3, v4, v5
    assert tally["still_held_at_end"] == 2 and by["A"].exit_snap is None and c.exit_snap is None
    assert tally["exits"] == 2 and tally["pending_exits_at_end"] == 0


def test_exit_needs_two_full_snapshots_single_frame_drop_cancelled():
    seq = [("v1", "2020-01-07", "in", ["A", "B"]),
           ("v1", "2020-01-07", "in", ["A"], True, 60),             # B absent from one full frame -> pending
           ("v1", "2020-01-07", "in", ["A", "B"], True, 120),       # B back -> the pending exit is cancelled
           ("v2", "2020-01-08", "in", ["A", "B"]),
           ("v3", "2020-01-09", "in", ["A"]),                       # pending
           ("v4", "2020-01-10", "in", ["A", "B"], False)]           # a PARTIAL sighting also cancels it
    snaps, ents, tally = build(seq)
    assert len(ents) == 2 and all(e.exit_snap is None for e in ents)
    assert tally["single_frame_drops_cancelled"] == 2 and tally["exits"] == 0 and tally["pending_exits_at_end"] == 0
    # absent from the LAST full snapshot only -> still held, pending counted
    seq2 = [("v1", "2020-01-07", "in", ["A", "B"]), ("v2", "2020-01-08", "in", ["A"])]
    snaps, ents, tally = build(seq2)
    assert tally["exits"] == 0 and tally["pending_exits_at_end"] == 1 and tally["still_held_at_end"] == 2


def test_flicker_needs_a_near_exit():
    # one-stream sighting, exit confirmed 4 months later (a stream gap) -> NOT a flicker
    seq = [("v1", "2020-01-07", "in", ["A"]), ("v2", "2020-01-08", "in", ["A", "B"]),
           ("v3", "2020-03-02", "in", ["A"]), ("v4", "2020-03-03", "in", ["A"])]
    snaps, ents, tally = build(seq)
    b = {e.sym: e for e in ents}["B"]
    assert b.exit_snap is not None and len(b.streams) == 1 and not b.flicker and tally["entries_flicker"] == 0


def test_partial_snapshot_can_open_an_entry_with_the_window_from_the_last_full():
    seq = [("v1", "2020-01-07", "closed", ["A"]),                  # full, after close
           ("v2", "2020-01-09", "in", ["A", "X"], False),          # scrolled: X seen -> entry, lo = 01-08 (after a closed list), hi = 01-09
           ("v3", "2020-01-10", "pre", ["A", "X"])]
    snaps, ents, tally = build(seq)
    x = {e.sym: e for e in ents}["X"]
    assert S.date(x.lo) == "2020-01-08" and S.date(x.hi) == "2020-01-09" and x.window_len == 2 and not x.flicker


def test_blip_fill_one_stream_absence():
    seq = [("v1", "2020-01-07", "in", ["A", "B"]),
           ("v2", "2020-01-08", "in", ["A"]),                        # B missing from one full stream only
           ("v3", "2020-01-09", "in", ["A", "B"])]
    snaps, ents, tally = build(seq)
    assert tally["blips_filled"] == 1 and "B" in snaps[1].held and snaps[1].blip_filled == ["B"]
    assert len(ents) == 2 and all(e.exit_snap is None for e in ents)       # no exit, no re-entry
    # two consecutive full streams without B -> a real exit (dated by the first absence) and a re-entry
    seq2 = [("v1", "2020-01-07", "in", ["A", "B"]), ("v2", "2020-01-08", "in", ["A"]), ("v3", "2020-01-09", "in", ["A"]),
            ("v4", "2020-01-10", "in", ["A", "B"])]
    snaps, ents, tally = build(seq2)
    bs = [e for e in ents if e.sym == "B"]
    assert tally["blips_filled"] == 0 and len(bs) == 2
    assert S.date(bs[0].exit_hi) == "2020-01-08" and S.date(bs[0].exit_lo) == "2020-01-07" and bs[0].exit_snap.idx == 1
    assert S.date(bs[1].lo) == "2020-01-09" and S.date(bs[1].hi) == "2020-01-10"      # after the last full list without it (v3, in-session)


def test_blip_skips_streams_without_a_full_snapshot():
    seq = [("v1", "2020-01-07", "in", ["A", "B"]),
           ("v2", "2020-01-08", "in", ["A"], False),                 # scrolled: unknown, not a blip and not an exit
           ("v3", "2020-01-09", "in", ["A", "B"])]
    snaps, ents, tally = build(seq)
    assert tally["blips_filled"] == 0 and len(ents) == 2 and all(e.exit_snap is None for e in ents)


# ---- F1: duplicate uploads and the clock order -----------------------------------------------------------------------------------------
def frame(fid, vid, date, clock, ts, syms, ctx="in"):
    """One reader record (the jsonl's shape, footer = rows read)."""
    return {"frame_id": fid, "folder": "positions", "vid": vid, "stream_ts": ts, "screen_date": date, "clock_ctx": ctx,
            "et_time": f"{date}T{clock}-05:00" if clock else "", "resolution": "1920x1080", "panel_found": True, "list": "A",
            "symbols": list(syms), "visible_n": len(syms), "total_n": len(syms), "layout": {"body": [688, 1017]},
            "rows": [{"y": [696 + 18 * i, 702 + 18 * i], "sym": x, "pct": 1.0, "pct_check": "ok"} for i, x in enumerate(syms)]}


def write_jsonl(tmp_path, recs):
    import json
    p = tmp_path / "panel.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return str(p)


def run_file(path):
    tally = T.collections.Counter()
    snaps = T.load_snapshots(path, tally)
    ents, _ren = T.build_timeline(snaps, S, tally)
    return snaps, ents, tally


def test_duplicate_upload_gives_no_extra_entry_or_exit(tmp_path):
    day1 = [frame("a1", "V1", "2020-01-08", "09:26", "0:05:00", ["A"], "pre"), frame("a2", "V1", "2020-01-08", "10:00", "0:39:00", ["A", "Q"]),
            frame("a3", "V1", "2020-01-08", "10:25", "1:04:00", ["A", "Q"])]
    later = [frame("c1", "V3", "2020-01-09", "10:00", "0:30:00", ["A", "Q"]), frame("c2", "V3", "2020-01-10", "10:00", "0:30:00", ["A", "Q"])]
    copy = [dict(r, frame_id=r["frame_id"] + "_copy", vid="V2") for r in day1]           # the same stream uploaded again
    _s1, e1, t1 = run_file(write_jsonl(tmp_path, day1 + later))
    snaps, e2, t2 = run_file(write_jsonl(tmp_path, day1 + copy + later))
    sig = lambda ents: sorted((e.sym, e.lo, e.hi, e.exit_hi) for e in ents)
    assert sig(e2) == sig(e1) and t2["exits"] == t1["exits"] == 0
    assert t2["duplicate_upload_videos"] == 1 and t2["duplicate_frames_dropped"] == 3 and t2["snapshots"] == 5 and t2["streams"] == 2
    q = [e for e in e2 if e.sym == "Q"]
    assert len(q) == 1 and q[0].first_snap.frame_id == "a2" and len(q[0].streams) == 2


def test_partial_duplicate_leftovers_join_the_kept_stream_and_frames_order_by_clock(tmp_path):
    big = [frame("b1", "BIG", "2020-01-08", "09:26", "0:05:00", ["A"], "pre"), frame("b2", "BIG", "2020-01-08", "10:00", "0:39:00", ["A"]),
           frame("b3", "BIG", "2020-01-08", "10:30", "1:09:00", ["A"])]
    small = [dict(big[0], frame_id="s1", vid="SMALL"), frame("s2", "SMALL", "2020-01-08", "10:15", "0:54:00", ["A"])]
    snaps, _e, t = run_file(write_jsonl(tmp_path, big + small))
    assert [x.frame_id for x in snaps] == ["b1", "b2", "s2", "b3"]                        # the leftover sits at its clock, inside BIG
    assert {x.vid for x in snaps} == {"BIG"} and snaps[2].vid_raw == "SMALL" and t["duplicate_leftover_frames_joined"] == 1
    # two DIFFERENT videos on one date (no shared frame): ordered by clock across them, not video by video
    v1 = [frame("x1", "VX", "2020-01-08", "09:40", "0:10:00", ["A"]), frame("x2", "VX", "2020-01-08", "10:40", "1:10:00", ["A"])]
    v2 = [frame("y1", "VY", "2020-01-08", "10:00", "0:02:00", ["A", "B"])]
    snaps, _e, t = run_file(write_jsonl(tmp_path, v1 + v2))
    assert [x.frame_id for x in snaps] == ["x1", "y1", "x2"] and t["duplicate_upload_videos"] == 0


def test_clock_fit_survives_a_misread_clock(tmp_path):
    fr = [frame("m1", "VM", "2020-01-08", "09:44", "0:23:00", ["A"]), frame("m2", "VM", "2020-01-08", "07:44", "0:23:10", ["A"]),   # 15:44 read 13:44
          frame("m3", "VM", "2020-01-08", "09:45", "0:24:00", ["A"])]
    snaps, _e, t = run_file(write_jsonl(tmp_path, fr))
    assert [x.frame_id for x in snaps] == ["m1", "m2", "m3"] and t["frames_clock_misread_over_2min"] == 1


# ---- F2: the look-alike guard ------------------------------------------------------------------------------------------------------------
def meta(sn, **rows):
    for sym, m in rows.items():
        sn.rows_meta[sym] = m
    return sn


def test_one_edit():
    assert T.one_edit("UI", "LI") and T.one_edit("SO", "SQ") and T.one_edit("BIL", "BILI") and T.one_edit("CCJ", "CC")
    assert T.one_edit("ASPS", "APPS")                                                   # the 720p alternation (S / P)
    assert not T.one_edit("SI", "SI") and not T.one_edit("UI", "XYZ") and not T.one_edit("ASPS", "SPAS") and not T.one_edit("U", "UIX")


def test_lookalike_misread_in_the_last_full_snapshot_is_renamed():
    snaps = [snap(0, "v1", "2020-01-10", "in", ["A"]),                                    # flat in LI (Friday, in session)
             meta(snap(1, "v2", "2020-01-13", "pre", ["A", "UI"]), UI=("mismatch_kept", None, 7.65)),   # Monday pre-market: LI misread as UI
             meta(snap(2, "v2", "2020-01-13", "in", ["A", "LI", "SI"]), LI=("ok", None, 8.02), SI=("ok", None, 4.08))]
    tally = T.collections.Counter()
    ents, ren = T.build_timeline(snaps, S, tally)
    by = {e.sym: e for e in ents}
    assert "UI" not in by and snaps[1].symbols == ["A", "LI"] and snaps[1].relabeled == [("UI", "LI")]
    li = by["LI"]
    assert li.first_snap.idx == 1 and li.prev_full.idx == 0 and S.date(li.lo) == "2020-01-10" and S.date(li.hi) == "2020-01-10"
    assert by["SI"].first_snap.idx == 2 and len(ren) == 1 and ren[0]["how"] == "mismatch_kept_nearest_pct"
    assert tally["lookalike_renames"] == 1 and tally["lookalike_ambiguous"] == 0


def test_lookalike_suggested_and_no_rename_on_a_clean_row():
    snaps = [snap(0, "v", "2020-02-03", "in", ["A"]),
             meta(snap(1, "v", "2020-02-03", "in", ["A", "SO"]), SO=("mismatch_kept", "SQ", 0.92)),
             snap(2, "v", "2020-02-03", "in", ["A", "SQ"])]
    ents, ren = T.build_timeline(snaps, S, T.collections.Counter())
    sq = [e for e in ents if e.sym == "SQ"]
    assert not [e for e in ents if e.sym == "SO"] and len(sq) == 1 and sq[0].first_snap.idx == 1 and sq[0].prev_full.idx == 0
    assert ren[0]["how"] == "suggested"
    # the row passed its % check and nobody suggested SQ: a real SO, then a real SQ -> no rename
    snaps = [snap(0, "v", "2020-02-03", "in", ["A"]), meta(snap(1, "v", "2020-02-03", "in", ["A", "SO"]), SO=("ok", None, 0.1)),
             snap(2, "v", "2020-02-03", "in", ["A", "SQ"])]
    ents, ren = T.build_timeline(snaps, S, T.collections.Counter())
    assert not ren and {e.sym for e in ents} == {"A", "SO", "SQ"}
    # Y still on screen in s: not a misread of X
    snaps = [snap(0, "v", "2020-02-03", "in", ["A"]), meta(snap(1, "v", "2020-02-03", "in", ["A", "SO"]), SO=("mismatch_kept", None, 0.9)),
             snap(2, "v", "2020-02-03", "in", ["A", "SO", "SQ"])]
    ents, ren = T.build_timeline(snaps, S, T.collections.Counter())
    assert not ren


# ---- F3: the panel's clock on E ------------------------------------------------------------------------------------------------------------
def test_panel_clocks():
    flat = snap(0, "v", "2020-01-08", "in", [])
    flat.et_time = "2020-01-08T10:36-05:00"
    held = snap(1, "v", "2020-01-08", "in", ["X"])
    held.et_time = "2020-01-08T11:00-05:00"
    e = T.Entry(eid=0, sym="X", first_snap=held, prev_full=flat, lo=S.ge("2020-01-08"), hi=S.le("2020-01-08"), inverted=False)
    c = T.panel_clocks(e, {"E": "2020-01-08"})
    assert c == {"first_clock_on_E": "11:00", "flat_clock_on_E": "10:36", "orh5_infeasible": False}
    held.et_time = "2020-01-08T09:32-05:00"
    flat.ctx, flat.et_time = "pre", "2020-01-08T09:24-05:00"
    c = T.panel_clocks(e, {"E": "2020-01-08"})
    assert c["orh5_infeasible"] and c["first_clock_on_E"] == "09:32" and c["flat_clock_on_E"] == "09:24"
    # first seen the next morning (pre-market reflects E) and flat the day before: no clock on E
    held.date, held.ctx = "2020-01-09", "pre"
    flat.date, flat.ctx = "2020-01-07", "in"
    assert T.panel_clocks(e, {"E": "2020-01-08"}) == {"first_clock_on_E": "", "flat_clock_on_E": "", "orh5_infeasible": False}
    assert T.panel_clocks(e, {"E": ""})["first_clock_on_E"] == ""


# ---- the dating rule -------------------------------------------------------------------------------------------------------------------
LEX = {"ABC": ("2016-01-04", "2022-06-30", "2021-09-27", "2026-10-16"), "FB": ("", "", "2021-09-27", "2022-06-08"),
       "META": ("2016-01-04", "2022-06-30", "2022-06-09", "2026-10-16"), "GBTC": ("", "", "", "")}
ALIAS = {"FB": "META"}
BK = {("A", "ABC"): [("2020-01-08", {"D": "2020-01-07", "pivot": "10", "adr20": "0.05", "base_id": "ABC|x", "retrigger": "0"}),
                     ("2020-01-15", {"D": "2020-01-14", "pivot": "11", "adr20": "0.05", "base_id": "ABC|x", "retrigger": "1"})],
      ("A", "META"): [("2020-01-09", {"D": "2020-01-08", "pivot": "200", "adr20": "0.03", "base_id": "META|y", "retrigger": "0"})]}
EP = {("A", "ABC"): [("2020-01-13", {"D": "2020-01-10", "prev_close_adj": "9.5", "gap_pct": "12.0"})],
      ("A", "META"): [("2020-01-09", {"D": "2020-01-08", "prev_close_adj": "190", "gap_pct": "9.5"})]}
CANDS = {"ABC", "META"}


def entry(sym, lo, hi, initial=False):
    s = snap(1, "v", hi, "in", [sym])
    return T.Entry(eid=0, sym=sym, first_snap=s, prev_full=None if initial else snap(0, "v0", lo, "pre", []), lo=S.ge(lo), hi=S.le(hi),
                   inverted=False)


def test_latest_event_dates_the_buy():
    d = T.date_entry(entry("ABC", "2020-01-08", "2020-01-10"), S, ALIAS, LEX, CANDS, BK, EP)
    assert d["setup"] == "breakout" and d["E"] == "2020-01-08" and d["D"] == "2020-01-07" and d["pivot"] == "10" and d["era"] == "A"
    d = T.date_entry(entry("ABC", "2020-01-08", "2020-01-16"), S, ALIAS, LEX, CANDS, BK, EP)     # breakout 01-08, EP 01-13, retrigger 01-15
    assert d["setup"] == "breakout" and d["E"] == "2020-01-15" and d["retrigger"] == "1" and d["n_events_in_window"] == 3
    assert d["E_earliest"] == "2020-01-08" and d["kind_earliest"] == "breakout"
    d = T.date_entry(entry("ABC", "2020-01-10", "2020-01-14"), S, ALIAS, LEX, CANDS, BK, EP)
    assert d["setup"] == "EP" and d["E"] == "2020-01-13" and d["D"] == "2020-01-10" and d["ep_gap_pct"] == "12.0"


def test_both_on_the_same_day_and_the_alias():
    d = T.date_entry(entry("FB", "2020-01-09", "2020-01-09"), S, ALIAS, LEX, CANDS, BK, EP)
    assert d["sym_a"] == "META" and d["setup"] == "both" and d["E"] == "2020-01-09" and d["pivot"] == "200" and d["ep_prev_close"] == "190"


def test_undated_reasons_and_initial():
    d = T.date_entry(entry("ABC", "2020-01-20", "2020-01-24"), S, ALIAS, LEX, CANDS, BK, EP)
    assert d["setup"] == "undated" and d["undated_reason"] == "no_event_in_window" and d["has_bars"] and d["ever_candidate"]
    d = T.date_entry(entry("GBTC", "2020-01-08", "2020-01-10"), S, ALIAS, LEX, CANDS, BK, EP)
    assert d["setup"] == "undated" and d["undated_reason"] == "no_bars" and not d["has_bars"]
    LEX2 = {**LEX, "TQQQ": ("2016-01-04", "2022-06-30", "2021-09-27", "2026-10-16")}
    d = T.date_entry(entry("TQQQ", "2020-01-08", "2020-01-10"), S, ALIAS, LEX2, CANDS, BK, EP)
    assert d["undated_reason"] == "never_candidate" and d["has_bars"]
    d = T.date_entry(entry("ABC", "2020-01-08", "2020-01-10", initial=True), S, ALIAS, LEX, CANDS, BK, EP)
    assert d["setup"] == "initial"


def test_q1_2022_hole_flag():
    assert T.date_entry(entry("ABC", "2022-01-10", "2022-01-14"), S, ALIAS, LEX, CANDS, BK, EP)["q1_2022_hole"]
    assert not T.date_entry(entry("ABC", "2021-12-06", "2021-12-10"), S, ALIAS, LEX, CANDS, BK, EP)["q1_2022_hole"]
    assert not T.date_entry(entry("ABC", "2022-04-04", "2022-04-08"), S, ALIAS, LEX, CANDS, BK, EP)["q1_2022_hole"]


# ---- the positive control --------------------------------------------------------------------------------------------------------------
def test_control_matching():
    seq = [("v1", "2020-01-07", "pre", ["Z"]),                        # full
           ("v2", "2020-01-08", "in", ["Z", "ABC"]),                   # ABC bought on 01-08 (window [01-07.. wait: lo = 01-07 (pre list), hi = 01-08])
           ("v3", "2020-01-09", "pre", ["Z", "ABC"])]
    snaps, ents, tally = build(seq)
    dated = [T.date_entry(e, S, ALIAS, LEX, CANDS, BK, EP) for e in ents]
    abc = [d for d in dated if d["sym"] == "ABC"][0]
    assert abc["setup"] == "breakout" and abc["E"] == "2020-01-08"
    calls = [("ABC", "2020-01-08", True), ("META", "2020-01-09", False), ("ABC", "2020-01-15", False)]
    rows = T.control_rows(calls, ents, dated, snaps, S, ALIAS, LEX)
    r = {(x["ticker"], x["E"]): x for x in rows}
    a = r[("ABC", "2020-01-08")]
    assert a["n_entries_window_holds_E"] == 1 and a["dated_on_E"] and a["decides"] and a["dated_minus_E"] == 0 and a["seen_E_to_E20"]
    assert a["nearest_snapshot_after_E_sessions"] == 0 and a["window_len"] == 2 and a["class"] == "dated_on_E"
    m = r[("META", "2020-01-09")]
    assert not m["ever_in_panel"] and m["n_entries_window_holds_E"] == 0 and not m["dated_on_E"] and m["class"] == "never_in_panel"
    late = r[("ABC", "2020-01-15")]
    assert late["ever_in_panel"] and not late["seen_E_to_E20"] and late["n_entries_window_holds_E"] == 0
    assert late["held_before_E"] and late["open_entry_at_E"] and late["open_entry_hi"] == "2020-01-08" and late["class"] == "open_entry_before_E"


def test_sessions_helpers():
    assert S.date(S.le("2020-01-11")) == "2020-01-10" and S.date(S.lt("2020-01-10")) == "2020-01-09"
    assert S.date(S.ge("2020-01-11")) == "2020-01-13" and S.date(S.gt("2020-01-10")) == "2020-01-13"
    assert T.ts_seconds("1:23:34") == 5014 and T.ts_seconds("05:00") == 300


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
