"""Tests for the #705 as-is read, step 5 re-run 2 (scripts/probes/_705_asis_1026/00c_windows_v2.py; the archive generalisation in
asis_common.py; the ranges-vs-windows claim of 03_check.py / asis_check_common.py). Synthetic fixtures only: no apollo_data, no machine
path; the real-data reproduction gate is the module's own --dry-run (its printout is pinned).

Covers: THE RULE on synthetic frame tables — a one-complete-frame session with a scrolled sighting is filled (kept), a session whose
complete frames all lack the stock is never filled (with no sighting the position ends and a new one begins at the next sighting; with a
scrolled sighting between two complete frames the unchanged exit rule carries the position), a one-complete-frame session with no sighting
is not filled and the unchanged exit rule cancels it at the next sighting, a session with no complete frame is skipped over; the old copy
bridges every one of those (so the two rules differ exactly where the operator's decision says); the split detector; the rows / written
form / differences (the reproduction gate can fail); symbol_join; every copied helper byte-identical to its source; the identifier scan and
the fresh-interpreter import belt on the new module; the any-generation archive (archive_path with a suffix, is_archive_of, ledger_verify
accepting two generations and refusing a non-archive row, archive_files' refusals and its ledger rows, 01_points --archive end to end);
ranges_vs_windows and the 6b claim that fails on another generation's ranges.tsv; the 6b dry run STOPS (never COMPLETE) on an absent
ranges.tsv. Review fixes of 2026-10-27: read_sheets' default read at call time (F1); the vanished positions and the v2 = v1 + pieces -
splits - vanished + unhosted identity (F2); R48's one-complete-frame outcomes, carried / not held / split (F3); windows changed without a split (F4); ranges_vs_windows
comparing the matched keys' (sym, lo, hi) (F5); windows_v2_gate on the rebuild's two printouts (F6); the scrolled-between count and the
registered archive suffixes (F7).
"""
from __future__ import annotations

import ast
import importlib.util
import io
import os
import subprocess
import sys
import tokenize
from datetime import date, timedelta
from pathlib import Path

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
W = _load("asis_windows00c", ASIS / "00c_windows_v2.py")
P = _load("asis_points01_w2", ASIS / "01_points.py")
K = _load("asis_check_common", ASIS / "asis_check_common.py")
M3 = _load("asis_check03_w2", ASIS / "03_check.py")


# ═════════════════════════════════════════════════════════════════════════════════════════════ fixtures
def weekday_cal(start: str = "2020-06-01", end: str = "2020-07-31") -> list:
    d, out = date.fromisoformat(start), []
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


S = C.Sessions(weekday_cal())
D = weekday_cal()[:8]           # eight sessions


def snap(idx: int, vid: str, d: str, clock: str, full: bool, symbols, ctx: str = "in") -> "W.Snap":
    return W.Snap(idx=idx, frame_id=f"f{idx}", vid=vid, date=d, ctx=ctx, clock=clock, full=full, full_how="footer_eq" if full else "footer_scrolled",
                  resolution="1920x1080", symbols=list(symbols))


def frames_for(middle: list) -> list:
    """Three sessions: s1 (two full frames holding XYZ and ABC), the MIDDLE session's frames as given (vid 'v2', date D[1]), s3 (two full
    frames holding both). ABC is held throughout and never missing: a control that the rule touches only the absent name."""
    out = [snap(0, "v1", D[0], "10:00", True, ["XYZ", "ABC"]), snap(1, "v1", D[0], "10:30", True, ["XYZ", "ABC"])]
    for k, (full, syms) in enumerate(middle):
        out.append(snap(len(out), "v2", D[1], f"10:{10 + 5 * k:02d}", full, syms))
    out.append(snap(len(out), "v3", D[2], "10:00", True, ["XYZ", "ABC"]))
    out.append(snap(len(out), "v3", D[2], "10:30", True, ["XYZ", "ABC"]))
    return out


def run(frames: list, rule):
    entries, tally, extra = W.build(frames, S, rule)
    return entries, tally, extra, W.fill_column(frames)


def xyz(entries):
    return [e for e in entries if e.sym == "XYZ"]


# ═════════════════════════════════════════════════════════════════════════════════════════════ the rule
def test_one_complete_frame_with_a_scrolled_sighting_is_filled_under_both_rules():
    fr = frames_for([(True, ["ABC"]), (False, ["XYZ", "ABC"])])            # one full frame without XYZ; a scrolled frame still shows it
    e_old, t_old, _, col_old = run(fr, W.blip_fill)
    e_new, t_new, dec, col_new = run(fr, W.blip_fill_single_frame)
    assert col_old == col_new and col_new[2] == "XYZ" and col_new[3] == ""                      # the single full frame is filled, the scrolled one not
    assert dec == [("v2", "XYZ", "kept_one_full_frame_scrolled_sighting")] and t_new["fills_kept"] == 1 and t_new["fills_dropped"] == 0
    assert len(xyz(e_old)) == len(xyz(e_new)) == 1 and xyz(e_new)[0].exit_snap is None
    assert xyz(e_new)[0].sightings == [0, 1, 2, 3, 4, 5]                                           # the filled frame counts as a sighting
    assert t_old["blips_filled"] == 1


def test_absent_from_every_complete_frame_with_no_sighting_is_a_real_exit():
    fr = frames_for([(True, ["ABC"]), (True, ["ABC"])])                      # two full frames, XYZ in neither, no scrolled frame
    e_old, t_old, _, col_old = run(fr, W.blip_fill)
    e_new, t_new, dec, col_new = run(fr, W.blip_fill_single_frame)
    assert col_old[2] == col_old[3] == "XYZ" and col_new == [""] * 6                               # the old copy bridged; the new rule fills nothing
    assert dec == [("v2", "XYZ", "dropped_many_full_frames_no_sighting")] and t_new["fills_dropped"] == 1 and t_new["fills_kept"] == 0
    assert len(xyz(e_old)) == 1 and xyz(e_old)[0].exit_snap is None
    a, b = xyz(e_new)
    assert a.exit_snap is fr[2] and (S.date(a.exit_lo), S.date(a.exit_hi)) == (D[0], D[1])          # the exit, dated by the first complete frame of v2
    assert b.first_snap is fr[4] and (S.date(b.lo), S.date(b.hi)) == (D[1], D[2]) and b.exit_snap is None   # the new position at the next sighting
    assert t_new["single_frame_drops_cancelled"] == 0 and len([e for e in e_new if e.sym == "ABC"]) == 1   # ABC untouched
    assert len(W.splits(e_old, e_new, fr)) == 1 and [p.first_snap.idx for p in W.splits(e_old, e_new, fr)[0][1]] == [0, 4]


def test_absent_from_every_complete_frame_with_a_scrolled_sighting_between_is_not_filled():
    fr = frames_for([(True, ["ABC"]), (False, ["XYZ", "ABC"]), (True, ["ABC"])])
    e_old, _, _, col_old = run(fr, W.blip_fill)
    e_new, t_new, dec, col_new = run(fr, W.blip_fill_single_frame)
    assert col_old[2] == col_old[4] == "XYZ" and col_new == [""] * 7
    assert dec == [("v2", "XYZ", "dropped_many_full_frames_scrolled_sighting")]
    # the unchanged exit rule: the scrolled sighting cancels the first pending; the second complete frame is pending until v3's sighting
    assert len(xyz(e_new)) == 1 and xyz(e_new)[0].exit_snap is None and t_new["single_frame_drops_cancelled"] == 2
    assert xyz(e_new)[0].sightings == [0, 1, 3, 5, 6]                                              # the complete frames without it are not sightings


def test_one_complete_frame_with_no_sighting_is_not_filled_and_the_next_sighting_cancels_it():
    fr = frames_for([(True, ["ABC"])])                                       # exactly one complete frame in the session, XYZ nowhere in it
    e_old, _, _, col_old = run(fr, W.blip_fill)
    e_new, t_new, dec, col_new = run(fr, W.blip_fill_single_frame)
    assert col_old[2] == "XYZ" and col_new == [""] * 5
    assert dec == [("v2", "XYZ", "dropped_one_full_frame_no_sighting")]
    assert len(xyz(e_new)) == 1 and xyz(e_new)[0].exit_snap is None and t_new["single_frame_drops_cancelled"] == 1
    assert xyz(e_new)[0].sightings == [0, 1, 3, 4]
    # ... and it ends the position together with the NEXT session's first complete frame lacking the stock
    fr2 = frames_for([(True, ["ABC"])])
    fr2[3].symbols = ["ABC"]                                                  # v3's first complete frame also lacks XYZ
    e2, t2, _, _ = run(fr2, W.blip_fill_single_frame)
    a, b = xyz(e2)
    assert a.exit_snap is fr2[2] and b.first_snap is fr2[4] and t2["single_frame_drops_cancelled"] == 0
    e2o, _, _, _ = run(fr2, W.blip_fill)
    assert len(xyz(e2o)) == 1                                                 # the old copy bridged this too


def test_a_session_with_no_complete_frame_is_skipped_over_by_both_rules():
    fr = frames_for([(False, ["ABC"]), (False, ["ABC"])])                    # scrolled lists only: they prove nothing
    e_old, t_old, _, col_old = run(fr, W.blip_fill)
    e_new, t_new, dec, col_new = run(fr, W.blip_fill_single_frame)
    assert col_old == col_new == [""] * 6 and dec == [] and t_old["blips_filled"] == 0
    assert len(xyz(e_old)) == len(xyz(e_new)) == 1 and xyz(e_new)[0].exit_snap is None


def test_the_candidate_set_is_the_old_rules_and_kept_plus_dropped_equals_it():
    fr = frames_for([(True, ["ABC"]), (False, ["XYZ", "ABC"])])
    fr[0].symbols, fr[1].symbols = ["ABC"], ["ABC"]                          # XYZ not held before the session: no candidate at all
    _, t_old, _, _ = run(fr, W.blip_fill)
    _, t_new, dec, _ = run(fr, W.blip_fill_single_frame)
    assert t_old["blips_filled"] == 0 and dec == [] and t_new["fills_kept"] + t_new["fills_dropped"] == 0
    assert set(W.FILL_SHAPES) == {"kept_one_full_frame_scrolled_sighting", "dropped_one_full_frame_no_sighting",
                                  "dropped_many_full_frames_scrolled_sighting", "dropped_many_full_frames_no_sighting"}


# ═════════════════════════════════════════════════════════════════════════════════════════════ the rows and the reproduction gate
def test_rows_written_form_and_differences_can_fail_the_gate():
    fr = frames_for([(True, ["ABC"]), (True, ["ABC"])])
    lex = {"XYZ": ("2019-01-02", "2022-06-30", "", ""), "ABC": ("", "", "2021-09-27", "2026-10-16")}
    alias = {"ABC": "ABCD"}
    e_new, _, _, _ = run(fr, W.blip_fill_single_frame)
    rows = W.entry_rows(e_new, S, lex, alias)
    assert [r["eid"] for r in rows] == [0, 1, 2] and {r["sym"] for r in rows} == {"XYZ", "ABC"}
    first = [r for r in rows if r["sym"] == "XYZ"][0]
    assert first["initial"] is True and first["lo"] == "" and first["window_len"] == "" and first["exit_frame"] == "f2" and first["still_held"] is False
    assert first["sym_a"] == "XYZ" and first["has_bars"] is True and first["first_resolution"] == "1920x1080"
    abc = [r for r in rows if r["sym"] == "ABC"][0]
    assert abc["sym_a"] == "ABCD" and abc["has_bars"] is True                 # no era-A rows under its own name -> the alias; era-B rows -> bars
    assert W.symbol_join("NOPE", lex, alias) == ("NOPE", False)
    ex = W.exit_rows(rows)
    assert len(ex) == 1 and list(ex[0]) == W.EXIT_COLS and ex[0]["exit_frame"] == "f2"
    a = W.as_written(rows, W.ENTRY_COLS)
    assert list(a.columns) == W.ENTRY_COLS and a["initial"].tolist() == ["True", "True", "False"] and a["window_len"].tolist()[2] == "2"
    assert W.differences(a, a) == []
    b = a.copy()
    b.loc[2, "hi"] = "2020-01-01"
    assert W.differences(a, b) == [("2", "hi", a["hi"].tolist()[2], "2020-01-01")]
    c = a.iloc[:2]
    assert W.differences(a, c)[0][1] == "order/count"
    assert W.ENTRY_COLS == P.ENTRY_COLS and W.EXIT_COLS == P.EXIT_COLS      # the columns step 5 reads, the same text


def test_by_year_counts_window_ends():
    fr = frames_for([(True, ["ABC"]), (True, ["ABC"])])
    e_new, _, _, _ = run(fr, W.blip_fill_single_frame)
    buys, sales = W.by_year(e_new, S)
    assert dict(buys) == {"2020": 1} and dict(sales) == {"2020": 1}          # the initial two have no buy window; one exit


# ═════════════════════════════════════════════════════════════════════════════════════════════ the review's printouts (F2, F3, F4, F7)
def three_sessions(a: list, b: list, c: list) -> list:
    """Frames of three sessions v1 / v2 / v3 from (full, symbols) lists."""
    out = []
    for vid, d, fr in (("v1", D[0], a), ("v2", D[1], b), ("v3", D[2], c)):
        for k, (full, syms) in enumerate(fr):
            out.append(snap(len(out), vid, d, f"10:{10 + 5 * k:02d}", full, syms))
    return out


def test_a_phantom_position_made_of_fills_vanishes_and_the_identity_holds():
    # XYZ exits inside v1 (two complete frames without it), v2's complete frames lack it, v3 shows it only on its third complete frame:
    # the old fill bridges v2 and the state machine makes a position of NOTHING BUT fills there, ended by v3's first two frames
    fr = three_sessions([(True, ["XYZ", "ABC"]), (True, ["ABC"]), (True, ["ABC"])], [(True, ["ABC"]), (True, ["ABC"])],
                        [(True, ["ABC"]), (True, ["ABC"]), (True, ["XYZ", "ABC"])])
    e_old, _, _, col_old = run(fr, W.blip_fill)
    v1_fill = list(col_old)
    e_new, _, dec, _ = run(fr, W.blip_fill_single_frame)
    assert [e.sightings for e in xyz(e_old)] == [[0], [3, 4], [7]] and col_old[3] == col_old[4] == "XYZ"
    assert [e.sightings for e in xyz(e_new)] == [[0], [7]] and dec == [("v2", "XYZ", "dropped_many_full_frames_no_sighting")]
    pieces, unhosted = W.pieces_by_host(e_old, e_new)
    van = W.vanished(e_old, pieces, v1_fill)
    assert [(e.sightings, ok) for e, ok in van] == [([3, 4], True)] and unhosted == [] and W.splits(e_old, e_new, fr) == []
    sp = W.splits(e_old, e_new, fr)
    assert len(e_new) == len(e_old) + sum(len(ps) for _e, ps in sp) - len(sp) - len(van) + len(unhosted)
    # a position with a real sighting is never 'all fills'
    assert W.vanished(e_old, {}, v1_fill)[0][1] is False


def test_a_window_moved_without_a_split_is_listed():
    # XYZ exits inside v1; v2 lacks it on two complete frames; v3 holds it from its first frame: the old fill back-dated the re-buy to v2
    fr = three_sessions([(True, ["XYZ", "ABC"]), (True, ["ABC"]), (True, ["ABC"])], [(True, ["ABC"]), (True, ["ABC"])],
                        [(True, ["XYZ", "ABC"]), (True, ["XYZ", "ABC"])])
    e_old, _, _, _ = run(fr, W.blip_fill)
    e_new, _, _, _ = run(fr, W.blip_fill_single_frame)
    pieces, _un = W.pieces_by_host(e_old, e_new)
    buy, sale = W.changed_without_split(e_old, pieces)
    assert [(e.sightings, p.sightings) for e, p in buy] == [([3, 4, 5, 6], [5, 6])] and sale == []
    e, p = buy[0]
    assert (S.date(e.lo), S.date(e.hi)) == (D[0], D[1]) and (S.date(p.lo), S.date(p.hi)) == (D[1], D[2])
    # a sale moved: XYZ held through v1 and v2, v3's complete frames lack it; v2's second complete frame lacked it (filled by the old rule)
    fr2 = three_sessions([(True, ["XYZ", "ABC"]), (True, ["XYZ", "ABC"])], [(True, ["XYZ", "ABC"]), (True, ["ABC"])], [(True, ["ABC"]), (True, ["ABC"])])
    e_old2, _, _, _ = run(fr2, W.blip_fill)
    e_new2, _, _, _ = run(fr2, W.blip_fill_single_frame)
    assert [e.exit_snap.idx for e in xyz(e_old2)] == [e.exit_snap.idx for e in xyz(e_new2)] == [3]   # v2 has a complete-frame sighting: no candidate, both rules agree
    assert W.changed_without_split(e_old2, W.pieces_by_host(e_old2, e_new2)[0]) == ([], [])


def test_r48_one_complete_frame_sessions_are_classified_carried_not_held_or_split():
    fr = frames_for([(True, ["ABC"])])                                       # the next session shows XYZ: the pending exit is cancelled
    e_new, _, dec, _ = run(fr, W.blip_fill_single_frame)
    assert W.one_frame_no_sighting(dec, fr, e_new) == [(D[1], "XYZ", "carried")]
    fr2 = frames_for([(True, ["ABC"])])
    fr2[3].symbols = ["ABC"]                                                  # the next session's first complete frame also lacks it
    e2, _, dec2, _ = run(fr2, W.blip_fill_single_frame)
    assert W.one_frame_no_sighting(dec2, fr2, e2) == [(D[1], "XYZ", "split")]
    # XYZ exited inside v1 (its last two complete frames lack it): the old fill invented a START at v2; v2 holds nothing there
    fr3 = three_sessions([(True, ["XYZ", "ABC"]), (True, ["ABC"]), (True, ["ABC"])], [(True, ["ABC"])], [(True, ["XYZ", "ABC"]), (True, ["XYZ", "ABC"])])
    e3, _, dec3, _ = run(fr3, W.blip_fill_single_frame)
    assert dec3 == [("v2", "XYZ", "dropped_one_full_frame_no_sighting")] and W.one_frame_no_sighting(dec3, fr3, e3) == [(D[1], "XYZ", "not_held")]
    assert [e.sightings for e in xyz(e3)] == [[0], [4, 5]]
    assert W.one_frame_no_sighting([("v2", "XYZ", "kept_one_full_frame_scrolled_sighting")], fr, e_new) == []


def test_scrolled_between_counts_the_order_the_exit_rule_carries():
    fr = frames_for([(True, ["ABC"]), (False, ["XYZ", "ABC"]), (True, ["ABC"])])     # the sighting BETWEEN the two complete frames
    _, _, dec, _ = run(fr, W.blip_fill_single_frame)
    assert W.scrolled_between(dec, fr) == 1
    fr2 = frames_for([(False, ["XYZ", "ABC"]), (True, ["ABC"]), (True, ["ABC"])])    # the sighting before both: the exit is confirmed
    e2, _, dec2, _ = run(fr2, W.blip_fill_single_frame)
    assert dec2 == [("v2", "XYZ", "dropped_many_full_frames_scrolled_sighting")] and W.scrolled_between(dec2, fr2) == 0
    assert len(xyz(e2)) == 2


def test_windows_v2_gate_reads_both_printouts_and_the_written_shas(tmp_path, monkeypatch):
    files = dict(C.FILES)
    for k in ("entries_v2", "exits_v2", "snapshots_v2"):
        files[k] = str(tmp_path / f"{k}.tsv")
        Path(files[k]).write_text(f"{k}\n")
    monkeypatch.setattr(C, "FILES", files)
    dry, wr = tmp_path / "00c_dry.txt", tmp_path / "00c_write.txt"
    monkeypatch.setattr(C, "P_DRY_00C", str(dry))
    monkeypatch.setattr(C, "P_WRITE_00C", str(wr))
    ml = C.modules_line(C.MODULES_00C)
    assert ml.startswith("asis_common.py ") and " 00c_windows_v2.py " in ml
    gate = C.windows_v2_gate
    assert len(gate()) == 2 and all("not completed" in x for x in gate())
    dry.write_text(f"# x\n- modules: {ml}\n\nRESULT: 23 claims, 22 OK, 1 MISMATCH\nDRY RUN COMPLETE\n")
    assert any("1 MISMATCH" in x for x in gate())
    dry.write_text(f"# x\n- modules: {ml}\n\nRESULT: 23 claims, 23 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    outs = "\n".join(f"- {k}: {files[k]} (1 rows, {C.sha(files[k])[:16]})" for k in ("entries_v2", "exits_v2", "snapshots_v2"))
    wr.write_text(f"# x\n- modules: {ml}\n## Outputs\n{outs}\nWRITE COMPLETE\n")
    assert gate() == []
    Path(files["exits_v2"]).write_text("edited\n")                            # a v2 file that is not the one the write recorded
    assert [x for x in gate() if x.startswith("exits_v2:")] and len(gate()) == 1
    Path(files["exits_v2"]).write_text("exits_v2\n")
    assert gate() == []
    wr.write_text(f"# x\n- modules: {ml}x\n## Outputs\n{outs}\nWRITE COMPLETE\n")   # made by other code
    assert len(gate()) == 1 and "other code" in gate()[0]
    wr.write_text(f"# x\n- modules: {ml}\n## Outputs\n{outs}\nREFUSED: outputs exist\n")
    assert any("write has not completed" in x for x in gate())
    dry.write_text(f"# x\n- modules: {ml}\n\nRESULT: 23 claims, 23 OK, 0 MISMATCH\nSTOPPED\n")
    assert any("dry run has not completed" in x for x in gate())
    assert C.printout_mismatches(str(dry)) == 0 and C.printout_line(str(dry), "- nope: ") is None and not C.printout_ends(str(tmp_path / "none"), "x")


# ═════════════════════════════════════════════════════════════════════════════════════════════ guards on the new module
def _segment(src: str, name: str, cls: str = None) -> str:
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    body = tree.body
    if cls is not None:
        body = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    for node in body:
        nm = None
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            nm = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            nm = node.targets[0].id
        if nm == name:
            start = node.lineno - 1
            if getattr(node, "decorator_list", None):
                start = node.decorator_list[0].lineno - 1
            return "".join(lines[start:node.end_lineno])
    raise KeyError(name)


def test_every_copied_helper_of_the_rebuild_matches_its_source():
    # source-pin-ok: the plan (§10) requires every copied rule-free helper to be byte-identical to its source, never imported; this compares text
    copy_src = (ASIS / "00c_windows_v2.py").read_text(encoding="utf-8")
    assert {n for _s, n, _k, _r in W.COPIED} == {"FLICKER_SESSIONS", "Entry", "blip_fill", "timeline"}
    for src_rel, name, kind, ren in W.COPIED:
        assert not ren
        src_text = (REPO / src_rel).read_text(encoding="utf-8")
        assert _segment(src_text, name) == _segment(copy_src, name), f"{src_rel}:{name} drifted from its copy"
    assert "blip_fill_single_frame" not in (REPO / W.COPIED[0][0]).read_text(encoding="utf-8")   # the change is a NEW function, not an edit


def test_new_module_scans_clean_and_holds_no_rule_import(tmp_path):
    # source-pin-ok: the plan's guard (3) IS a scan of the step-5 source text; the module must hold none of the excluded names
    assert C.scan_identifiers([str(ASIS / "00c_windows_v2.py")]) == []
    tree = ast.parse((ASIS / "00c_windows_v2.py").read_text(encoding="utf-8"))
    names = {n.module.split(".")[0] if isinstance(n, ast.ImportFrom) and n.module else "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
            {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not names & {"socket", "requests", "urllib", "anthropic", "psycopg2", "asyncpg", "httpx"}
    code = (
        "import importlib.util, sys, json\n"
        f"spec = importlib.util.spec_from_file_location('asis_windows00c', {str(ASIS / '00c_windows_v2.py')!r})\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['asis_windows00c'] = m; spec.loader.exec_module(m)\n"
        "print(json.dumps(m.C.rule_modules_loaded()))\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout.strip().splitlines()[-1]) == []


def test_no_absolute_machine_path_in_this_test_file():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "/Users" + "/" not in text


# ═════════════════════════════════════════════════════════════════════════════════════════════ the any-generation archive (asis_common R41)
def test_archive_path_and_is_archive_of():
    assert C.archive_path("/x/candidates.tsv") == "/x/candidates_run1.tsv"
    assert C.archive_path("/x/candidates.tsv", "_run2_prev") == "/x/candidates_run2_prev.tsv"
    assert C.is_archive_of("/x/candidates.tsv", "/x/candidates_run1.tsv") and C.is_archive_of("/x/candidates.tsv", "/x/candidates_run2_prev.tsv")
    assert not C.is_archive_of("/x/candidates.tsv", "/x/candidates.tsv")
    assert not C.is_archive_of("/x/candidates.tsv", "/y/candidates_run1.tsv") and not C.is_archive_of("/x/candidates.tsv", "/x/candidates_run1.txt")
    assert not C.is_archive_of("/x/candidates.tsv", "/x/candidatesrun1.tsv") and not C.is_archive_of("/x/ranges.tsv", "/x/candidates_run1.tsv")
    # review F7: only a REGISTERED suffix makes an archive — a sibling printout is never read as one
    assert not C.is_archive_of("/x/01_points.txt", "/x/01_points_dryrun_run1.txt") and not C.is_archive_of("/x/candidates.tsv", "/x/candidates_run9.tsv")
    assert C.ARCHIVE_SUFFIXES == ("_run1", "_run2_prev")


def test_ledger_verify_accepts_two_generations_and_refuses_a_non_archive_row(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    b = tmp_path / "candidates.tsv"
    b.write_text("run 1\n")
    C.ledger_append("step5_candidates", str(b))
    # generation 1 archived, run 2 written, verified
    os.replace(b, C.archive_path(str(b)))
    C.ledger_append("archive_run1_candidates", C.archive_path(str(b)))
    b.write_text("run 2\n")
    C.ledger_append("step5_rerun1_candidates", str(b))
    assert C.ledger_verify() == []
    # generation 2 archived under ANOTHER suffix: both the run-1 and the run-2 rows are excused by their own copies
    os.replace(b, C.archive_path(str(b), "_run2_prev"))
    C.ledger_append("archive_run2_prev_candidates", C.archive_path(str(b), "_run2_prev"))
    assert C.ledger_verify() == []
    b.write_text("run 3\n")
    C.ledger_append("step5_rerun2_candidates", str(b))
    assert C.ledger_verify() == []
    # the copies are themselves checked
    (tmp_path / "candidates_run2_prev.tsv").write_text("tampered\n")
    bad = C.ledger_verify()
    assert any("candidates_run2_prev.tsv: changed" in x for x in bad) and any(x.startswith(f"{b}: changed") for x in bad)
    # a non-archive row naming an archived path excuses nothing
    (tmp_path / "candidates_run2_prev.tsv").write_text("run 2\n")
    assert C.ledger_verify() == []
    c = tmp_path / "ranges.tsv"
    c.write_text("r\n")
    C.ledger_append("step5_ranges", str(c))
    os.replace(c, C.archive_path(str(c), "_run2_prev"))
    C.ledger_append("step5_something", C.archive_path(str(c), "_run2_prev"))
    assert any(x.startswith(f"{c}: missing") for x in C.ledger_verify())
    # an archive row is never excused by another archive row
    (tmp_path / "candidates_run1.tsv").unlink()
    assert any("candidates_run1.tsv: missing" in x for x in C.ledger_verify())


def test_archive_files_moves_writes_rows_and_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    a, b = tmp_path / "01_points.txt", tmp_path / "candidates.tsv"
    a.write_text("printout\n")
    b.write_text("table\n")
    C.ledger_append("step5_points", str(a))
    C.ledger_append("step5_candidates", str(b))
    with pytest.raises(C.GuardStop):                                        # a stage prefix that is not an archive prefix
        C.archive_files([("points", str(a))], "_run2_prev", "step5_")
    with pytest.raises(C.GuardStop):                                        # review F7: an unregistered suffix
        C.archive_files([("points", str(a))], "_run3", "archive_run3_")
    assert a.exists()
    with pytest.raises(C.GuardStop):                                        # a missing file: nothing moved
        C.archive_files([("points", str(a)), ("nope", str(tmp_path / "nope.tsv"))], "_run2_prev", "archive_run2_prev_")
    assert a.exists()
    b.write_text("edited after the run\n")
    with pytest.raises(C.GuardStop):                                        # a file whose content differs from its ledger row
        C.archive_files([("candidates", str(b))], "_run2_prev", "archive_run2_prev_")
    b.write_text("table\n")
    out = C.archive_files([("points", str(a)), ("candidates", str(b))], "_run2_prev", "archive_run2_prev_")
    assert [(p, arc) for p, arc, _s in out] == [(str(a), str(tmp_path / "01_points_run2_prev.txt")), (str(b), str(tmp_path / "candidates_run2_prev.tsv"))]
    assert not a.exists() and (tmp_path / "01_points_run2_prev.txt").read_text() == "printout\n"
    assert C.ledger_verify() == []
    rows = (tmp_path / "ledger.tsv").read_text().splitlines()
    assert rows[-2].startswith("archive_run2_prev_points\t") and rows[-1].startswith("archive_run2_prev_candidates\t")
    a.write_text("printout\n")
    with pytest.raises(C.GuardStop):                                        # the target exists now
        C.archive_files([("points", str(a))], "_run2_prev", "archive_run2_prev_")
    assert C.ledger_last_sha(str(tmp_path / "never.tsv")) is None


def test_points_archive_stage_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "P_DRY", str(tmp_path / "dry.txt"))
    monkeypatch.setattr(C, "P_RUN", str(tmp_path / "run.txt"))
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    monkeypatch.setattr(C, "OUTPUTS", {k: str(tmp_path / f"{k}.tsv") for k in ("candidates", "ranges", "coverage")})
    assert [k for k, _p in P.archive_items()] == ["dry_run", "points", "candidates", "ranges", "coverage"]
    assert P.ARCHIVE_SUFFIX == "_run2_prev" and P.ARCHIVE_STAGE.startswith(C.ARCHIVE_PREFIX) and P.RERUN_STAGE == "step5_rerun2_"
    assert P.RERUN_STAGE != "step5_rerun1_" and not "step5_candidates".startswith(P.RERUN_STAGE)
    for k, p in P.archive_items():
        Path(p).write_text(f"{k}\n")
        C.ledger_append("step5_rerun1_" + k, p)
    assert P.main(["--archive"]) == 0
    assert all(not Path(p).exists() and Path(C.archive_path(p, "_run2_prev")).exists() for _k, p in P.archive_items())
    assert C.ledger_verify() == [] and P.main(["--archive"]) == 3          # nothing left to archive: a missing file refuses
    doc = tmp_path / "doc.md"
    doc.write_text("# body\n\n<!-- FREEZE -->\n")
    assert not any("outputs exist" in x or "ledger" in x for x in P.run_gate(str(doc)))


def test_pins_carry_the_v2_files_and_the_rebuild_module(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# body\n\n<!-- FREEZE -->\n")
    p = C.pins(str(doc), include_outputs=False)
    assert {"entries_v2", "exits_v2", "snapshots_v2", "00c_windows_v2.py", "dryrun00c_printout", "write00c_printout"} <= set(p)
    assert C.FILES["snapshots_v2"].endswith("/windows_v2/snapshots_v2.tsv") and C.W2_DIR.endswith("/windows_v2")


# ═════════════════════════════════════════════════════════════════════════════════════════════ 6b: ranges against the loaded windows (R89, R90)
def test_ranges_vs_windows_and_the_6b_claim_fails_on_another_generation():
    ws = [(1, "buy", "XYZ", D[0], D[0]), (1, "sale", "XYZ", D[1], D[1]), (2, "buy", "ABC", D[0], D[0])]
    row = lambda side, in_span, sym, lo, hi: {"side": side, "in_span": in_span, "sym": sym, "lo": lo, "hi": hi}
    ranges = {(1, "buy"): row("buy", "True", "XYZ", D[0], D[0]), (1, "sale"): row("sale", "True", "XYZ", D[1], D[1]), (2, "buy"): row("buy", "False", "ABC", D[0], D[0])}
    assert K.ranges_vs_windows(ranges, ws) == ([], [], [])
    other = {(1, "buy"): ranges[(1, "buy")], (3, "buy"): row("buy", "True", "QQQ", D[0], D[0])}         # another generation's eids
    assert K.ranges_vs_windows(other, ws) == ([(3, "buy")], [(1, "sale"), (2, "buy")], [])
    # review F5: the keys all match but one window moved (a subset generation under re-dated windows) — caught by the third list
    moved = {k: dict(v) for k, v in ranges.items()}
    moved[(1, "sale")]["lo"] = D[0]
    assert K.ranges_vs_windows(moved, ws) == ([], [], [((1, "sale"), ("XYZ", D[0], D[1]), ("XYZ", D[1], D[1]))])
    swapped = {k: dict(v) for k, v in ranges.items()}
    swapped[(2, "buy")]["sym"] = "XYZ"
    assert K.ranges_vs_windows(swapped, ws)[2] == [((2, "buy"), ("XYZ", D[0], D[0]), ("ABC", D[0], D[0]))]
    say = K.Say()
    claims = K.Claims(say)
    M3.report_populations(say, [], [], other, claims, ws)
    text = "\n".join(say.lines)
    assert "[MISMATCH] every ranges.tsv (eid, side) is a loaded window" in text and "pre-fix facts (§3.1" in text
    assert claims.result().endswith("MISMATCH") and not claims.result().endswith("0 MISMATCH")
    say3 = K.Say()
    claims3 = K.Claims(say3)
    M3.report_populations(say3, [], [], moved, claims3, ws)
    text3 = "\n".join(say3.lines)
    assert "[OK] every ranges.tsv (eid, side) is a loaded window" in text3 and "[MISMATCH] every matched ranges.tsv row's (sym, lo, hi)" in text3
    say2 = K.Say()
    claims2 = K.Claims(say2)
    M3.report_populations(say2, [], [], ranges, claims2, ws)
    assert "[OK] every ranges.tsv (eid, side) is a loaded window" in "\n".join(say2.lines)
    assert "[OK] every matched ranges.tsv row's (sym, lo, hi)" in "\n".join(say2.lines)
    assert all("ranges.tsv sides = the loaded windows" not in r[0] or r[3] for r in claims2.rows)


def test_read_sheets_default_is_read_at_call_time(tmp_path, monkeypatch):
    # review F1: a module-constant default is bound at definition and escapes a monkeypatch; the default must be resolved when called
    p = tmp_path / "reader1_t1_v2_part1.tsv"
    p.write_text("stmt_id\tx\n1\ta\n")
    monkeypatch.setattr(K, "V2_SHEETS", (str(p),))
    rows = K.read_sheets()
    assert rows == [{"stmt_id": "1", "x": "a", "part": "reader1_t1_v2_part1"}]
    assert K.read_sheets.__defaults__ == (None,)


def test_6b_dry_run_stops_on_an_absent_ranges_file(tmp_path, monkeypatch):
    paths = {"dry": str(tmp_path / "dry.txt"), "run": str(tmp_path / "run.txt"), "refused": str(tmp_path / "refused.txt"), "pins": str(tmp_path / "pins.txt")}
    monkeypatch.setattr(K, "P03", paths)
    sheets = tuple(str(tmp_path / f"reader1_t1_v2_part{k}.tsv") for k in (1, 2, 3))
    for p in sheets:
        Path(p).write_text("stmt_id\n")
    monkeypatch.setattr(K, "V2_SHEETS", sheets)
    monkeypatch.setattr(K, "WORDING_V2", str(tmp_path / "wording.txt"))
    Path(K.WORDING_V2).write_text("v2\n")
    monkeypatch.setattr(K, "RANGES", str(tmp_path / "absent" / "ranges.tsv"))
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])              # a shared pytest process may hold other tests' modules
    assert M3.main(["--dry-run"]) == 2
    lines = [ln for ln in Path(paths["dry"]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines[-1].startswith("STOPPED: ranges.tsv is absent") and not C.dry_run_complete(paths["dry"])
    assert [k for k, _p in K.archive_items_6b()] == ["dry_run", "check", "check_r1_r5", "control_ranges"]
    assert K.ARCHIVE_SUFFIX_6B == "_run1" and K.ARCHIVE_STAGE_6B.startswith(C.ARCHIVE_PREFIX) and K.STAGE_6B == "step6b_rerun2_" and K.STAGE_6B != K.STAGE_6B_FIRST
