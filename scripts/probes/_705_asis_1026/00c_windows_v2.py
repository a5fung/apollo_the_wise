#!/usr/bin/env python3
"""#705 as-is read, step 5 re-run 2 prep: THE WINDOWS v2 — every position's buy window and sale window rebuilt from the frame table
(`snapshots.tsv`) with gap-filling limited to single-frame misses (docs/analysis/cb_asis_reconstruction_prereg_2026-10-26.md, the freeze
record's re-run 2; his "Ok" to option A, 2026-10-27). RULE-FREE BY CONSTRUCTION: the timeline reading only — no bar, no minute file, no
rule, setup name or pattern label; nothing imported from the four rule folders (the reading helpers are COPIES, byte-identical, compared to
their source by `tests/test_asis_windows_v2.py` through the `COPIED` registry below; the ONE changed function is a NEW named function).

WHY: step 6b's R5 read 46 / 66 (bar 90%). The diagnosis (`fork/r5_miss_diagnosis.md`) found the windows mostly right and ONE real flaw: the
holdings timeline's blip fill bridged a stock's absence even when the stock was missing from EVERY complete frame of a session, merging two
real positions into one (SPXL 2020-04-20: absent from all 7 complete frames, his words "I covered late day on Friday" confirm the sale;
LAKE 2020-01-23 probable). 573 filled symbol-frames on 518 frames, every one on a frame marked full.

THE RULE (the one change; nothing else in the timeline reading changes):
  1. A frame that is not complete never proves an absence (as today: only full frames enter the fill and the exit reading).
  2. A fill may bridge a stock's absence ONLY when the stock is missing from a SINGLE complete frame of a session and is present in another
     frame of the SAME session (a misread row). The session is one stream (`vid`, a duplicate upload's leftovers joined to it); "another
     frame" is any other frame of that stream, complete or not (a scrolled list that shows the row still shows him holding it). As today,
     the candidate must be held in the nearest full streams before and after (a fill BRIDGES: both sides held).
  3. An absence from EVERY complete frame of a session — one session, or several in a row — is a real exit: nothing is filled, the
     position ends there and a new one begins at the next sighting (the unchanged two-complete-frame exit rule confirms it on the
     session's second complete frame; with no sighting in the session there is nothing to cancel it). One ORDER is an exception the
     unchanged exit rule makes, not this module (review F7): a scrolled sighting lying BETWEEN two complete frames of such a session
     cancels the first frame's pending exit, so the position is carried (the second frame's pending waits for the next session); the
     dry run counts that order among the 6 dropped scrolled-sighting candidates — 0 on the real table.
  4. A session with exactly ONE complete frame: an absence from it is at once "a single complete frame" and "every complete frame of the
     session", so the PRESENCE test decides — the fill is made when the stock is present in another (not complete) frame of that session,
     and NOT made otherwise. An unfilled one-frame absence is then read by the unchanged exit rule: it ends the position only together
     with the next complete frame (the next session's first) also lacking the stock; a sighting first cancels it as a single-frame drop
     (counted, as today). So a one-complete-frame session alone never ends a position; it ends one with the session after it.
  Measured on the real table before the rule was fixed in code (2026-10-27; the dry run prints the same four counts): 125 (stream, name)
  fills in all — 103 sessions with several complete frames and no sighting at all (dropped), 6 with several complete frames and a
  scrolled sighting (dropped: absent from every complete frame), 9 one-complete-frame sessions with a scrolled sighting (kept), 7
  one-complete-frame sessions with no sighting (dropped; the exit rule then needs the next session too).

  R48 (a READING, recorded for the main loop to confirm or reverse BEFORE `01 --print-pins`; review F3 of re-run 2, 2026-10-27). Point 4 is
  a choice the task's two clauses leave open: read literally, "an absence from every complete frame of a session is a real exit" ends a
  position at a one-complete-frame session that lacks the stock with no other sighting; "nothing else in the timeline reading changes"
  leaves that absence to the unchanged two-frame exit rule, which is what this module does. On the real table 7 such sessions exist
  (the `dropped_one_full_frame_no_sighting` shape); the dry run prints each with its outcome under v2 and claims the counts: 5 are
  CARRIED across the session as one position (the next session's first complete frame shows the stock, cancelling the pending exit) —
  TSLA 2017-02-02, BLDP 2019-12-19, QS 2020-12-14, CLF 2021-03-31, WEAT 2022-05-10 — 1 is NOT HELD in v2 at that session (the old
  fill had invented the position's START there; v2 begins it at the next sighting, 2019-10-21, so the literal reading changes nothing
  for it; it is the APPS buy among the moved windows) — APPS 2019-10-18 — and 1 SPLITS because the NEXT session's first complete frame
  also lacked the stock — LK 2020-01-15. (The review's F3 counted 5 stay / 2 split with WEAT among the splits; snapshots.tsv shows
  2022-05-17's first complete frame holding WEAT — idx 2824 lacks it, 2825 holds it — and v2 carries it as one position 04-12..05-17.)
  LK and WEAT are printed in full, v1 and v2, for the main loop to eyeball against snapshots.tsv. Reversing the reading (the literal
  clause) would touch the 5 carried only, ending each at that session; it is a change to build and disclose, NOT made here.

WHAT IT DOES
  read      `snapshots.tsv` (every column; the fill column is CLEARED), the lexicon and the alias map (for `sym_a` / `has_bars`, the two
            symbol columns of entries.tsv — the same two expressions as the holdings read's dating function, copied as `symbol_join`).
  v1        the OLD fill (`blip_fill`, a byte-identical copy) + the state machine (`timeline`, a copy) -> the reproduction gate: the rebuilt
            rows must equal `entries.tsv` (the rule-free columns, `ENTRY_COLS`), `exits.tsv` (`EXIT_COLS`) and `snapshots.tsv`'s
            `blip_filled` column EXACTLY (0 differences), so the only change between v1 and v2 is the rule.
  v2        the NEW fill (`blip_fill_single_frame`, ours) + the same state machine -> the v2 positions; `eid` is renumbered in creation
            order (a split position is two positions).
  splits    every v2 position is HOSTED by the v1 position of its symbol whose sightings span its first sighting (`pieces_by_host`). A v1
            position hosting TWO or more is `split` (every split listed; SPXL around 2020-04-20 and LAKE around 2020-01-23 printed in full,
            v1 and v2, whatever the count); hosting NONE it has VANISHED (review F2: every one of its sightings was a filled frame — a
            phantom the old fill invented inside a whole-session absence; listed and claimed by name); hosting ONE whose buy or sale
            window MOVED it is listed as changed-without-a-split (review F4). The identity claimed: v2 = v1 + (pieces − splits) − vanished
            + unhosted.
  counts    positions before / after; fills kept (single-frame) / dropped (whole-session), by the four shapes above; the buy / sale window
            counts by year (year of the window end, as the inventory counts), v1 beside v2; R48's 7 / 5 / 2.

STAGES  --dry-run   everything above, no file written -> 00c_windows_v2_dryrun.txt ending 'DRY RUN COMPLETE' with a RESULT line
                    '<n> claims, <k> OK, <j> MISMATCH' (the reproduction gate is three of the claims).
        --write     the same computation, then writes windows_v2/entries_v2.tsv, exits_v2.tsv and snapshots_v2.tsv (R40: the frame table
                    with ONLY `blip_filled` rewritten) -> 00c_windows_v2.txt, ending 'WRITE COMPLETE' with the three files' shas. REFUSES
                    when a claim mismatched or an output exists. Both printouts are pinned by step 5 and read by its run gate
                    (`asis_common.windows_v2_gate`, review F6): the dry run COMPLETE with 0 MISMATCH, both made by the modules on disk, the
                    written shas equal to the files.

No subagent, no network, no production server, no paid call, nothing after 2024-12-31, none of the seven outcome folders.
Run:  python3 scripts/probes/_705_asis_1026/00c_windows_v2.py --dry-run | --write
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import io
import os
import sys
import time
from dataclasses import dataclass, field

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_common():
    name = "asis_common"
    if name in sys.modules and getattr(sys.modules[name], "__file__", "") == os.path.join(HERE, "asis_common.py"):
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, "asis_common.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load_common()
Sessions, asof, lo_after, GuardStop = C.Sessions, C.asof, C.lo_after, C.GuardStop

# ---- the rule-free columns the windows carry (01_points reads exactly these; the lists are the same text) --------------------------------
ENTRY_COLS = ["eid", "sym", "sym_a", "has_bars", "first_frame", "first_vid", "first_date", "first_ctx", "prev_full_frame", "prev_full_date",
              "lo", "hi", "window_len", "inverted", "initial", "flicker", "n_sightings", "n_streams", "exit_lo", "exit_hi", "exit_frame",
              "still_held", "first_resolution"]
EXIT_COLS = ["eid", "sym", "sym_a", "exit_lo", "exit_hi", "exit_frame", "flicker", "initial"]
P_DRY = C.P_DRY_00C
P_WRITE = os.path.join(HERE, "00c_windows_v2.txt")
OUT = {"entries_v2": C.FILES["entries_v2"], "exits_v2": C.FILES["exits_v2"], "snapshots_v2": C.FILES["snapshots_v2"]}
NAMED_CASES = (("SPXL", "2020-04-13", "2020-04-24"), ("LAKE", "2020-01-21", "2020-01-29"))   # the diagnosis's two: printed in full, claimed split
EYEBALL_CASES = (("LK", "2019-12-30", "2020-01-17"), ("WEAT", "2022-05-02", "2022-05-20"))  # R48's two: printed in full, NOT claimed
FILL_SHAPES = ("kept_one_full_frame_scrolled_sighting", "dropped_one_full_frame_no_sighting", "dropped_many_full_frames_scrolled_sighting",
               "dropped_many_full_frames_no_sighting")


class Say:
    def __init__(self):
        self.lines = []

    def __call__(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.lines.append(msg)

    def write(self, path: str) -> None:
        with open(path + ".partial", "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")
        os.replace(path + ".partial", path)


class Claims:
    def __init__(self, say):
        self.say, self.rows = say, []

    def __call__(self, label: str, expected, got) -> None:
        ok = expected == got
        self.rows.append((label, expected, got, ok))
        self.say(f"  [{'OK' if ok else 'MISMATCH'}] {label}: expected {expected}, got {got}")

    def mismatches(self) -> int:
        return sum(1 for r in self.rows if not r[3])

    def result(self) -> str:
        n, k = len(self.rows), sum(1 for r in self.rows if r[3])
        return f"RESULT: {n} claims, {k} OK, {n - k} MISMATCH"


def table(say, hdr: list, rows: list) -> None:
    w = [max(len(str(x)) for x in col) for col in zip(hdr, *rows)] if rows else [len(h) for h in hdr]
    say("  " + "  ".join(str(h).ljust(w[k]) for k, h in enumerate(hdr)))
    for r in rows:
        say("  " + "  ".join(str(x).ljust(w[k]) for k, x in enumerate(r)))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the frames (the copied reading needs `.held`, `.full`, `.full_how`, `.idx`, `.vid`, `.date`, `.ctx`)
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Snap:
    """One row of snapshots.tsv as this rebuild reads it (a superset of asis_common.Frame: the fill reading also reads `full_how`)."""
    idx: int
    frame_id: str
    vid: str
    date: str
    ctx: str
    clock: str
    full: bool
    full_how: str
    resolution: str
    symbols: list
    blip_filled: list = field(default_factory=list)

    @property
    def held(self) -> set:
        return set(self.symbols) | set(self.blip_filled)


def read_snapshot_table(path: str) -> tuple:
    """-> (the DataFrame, every column as written; [Snap] in idx order with the fill column CLEARED — the fills are recomputed)."""
    df = pd.read_csv(C.checked(path), sep="\t", dtype=str, keep_default_na=False)
    snaps = []
    for r in df.to_dict("records"):
        snaps.append(Snap(idx=int(r["idx"]), frame_id=r["frame_id"], vid=r["vid"], date=r["date"], ctx=r["ctx"] or "in", clock=r["clock"],
                          full=(r["full"] == "True"), full_how=r["full_how"], resolution=r["resolution"],
                          symbols=[s for s in r["symbols"].split(",") if s]))
    snaps.sort(key=lambda s: s.idx)
    assert [s.idx for s in snaps] == list(range(len(snaps))), "snapshots.tsv idx is not 0..n-1"
    return df, snaps


def lookalike_pairs(*_a, **_k):
    """Never called here: the frame table already carries the look-alike renames (its `relabeled` column); `timeline` is run with
    `found=None`, so the copied text's reference is a shim that refuses."""
    raise GuardStop("the look-alike guard is not part of this rebuild (the frames are already renamed)")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# COPIES — byte-identical source text of the timeline reading (see `COPIED` at the end)
# ═════════════════════════════════════════════════════════════════════════════════════════════
FLICKER_SESSIONS = 5                 # a one-stream sighting whose exit is confirmed within this many sessions of it

@dataclass
class Entry:
    eid: int
    sym: str                      # the panel's symbol
    first_snap: Snap
    prev_full: "Snap | None"      # the last full snapshot without the name (None -> initial)
    lo: int                       # session indices
    hi: int
    inverted: bool
    sightings: list = field(default_factory=list)      # snapshot idx
    streams: set = field(default_factory=set)
    exit_lo: "int | None" = None
    exit_hi: "int | None" = None
    exit_snap: "Snap | None" = None
    flicker: bool = False

    @property
    def initial(self) -> bool:
        return self.prev_full is None

    @property
    def window_len(self) -> int:
        return self.hi - self.lo + 1

def blip_fill(snaps: list, tally: collections.Counter) -> None:
    """A name absent from every full snapshot of exactly one stream, present in the nearest full streams before and after -> added to
    that stream's full snapshots (an OCR miss, not a round trip). Streams with no full snapshot are skipped over (unknown). A stream = one
    video (`vid`, a duplicate upload's leftovers joined to it), the streams in the order of their first frame."""
    order, streams = [], {}
    for s in snaps:                                   # ordered; group the frames of one video
        if s.vid not in streams:
            order.append(s.vid)
            streams[s.vid] = []
        streams[s.vid].append(s)
    full_streams = [(v, streams[v]) for v in order if any(x.full for x in streams[v])]
    for k in range(1, len(full_streams) - 1):
        _v, fr = full_streams[k]
        here = set().union(*(x.held for x in fr if x.full))
        before = set().union(*(x.held for x in full_streams[k - 1][1] if x.full))
        after = set().union(*(x.held for x in full_streams[k + 1][1] if x.full))
        for name in sorted((before & after) - here):
            footer_eq = False
            for x in fr:
                if x.full and name not in x.held:
                    footer_eq = footer_eq or x.full_how == "footer_eq"
                    x.blip_filled.append(name)
            tally["blips_filled"] += 1
            tally["blips_over_footer_consistent_absence"] += int(footer_eq)   # the footer total equals the rows read, and the name is not among them

def timeline(snaps: list, S: Sessions, tally: collections.Counter, found: "list | None" = None) -> list:
    """The snapshot-level state machine -> entries (each carrying its exit, if the panel showed one). An exit needs two consecutive
    full snapshots without the name; a sighting in between cancels it (a single-frame drop). With `found` a list, the look-alike guard's
    proposals (F2) are appended to it (detection only; `build_timeline` applies them)."""
    entries, held, last_full, pending = [], {}, None, {}
    for s in snaps:
        H = s.held
        if found is not None and last_full is not None:
            new = [n for n in sorted(H) if n not in held]
            if new:
                found.extend(lookalike_pairs(new, s, last_full, tally))
        for name in sorted(H):
            if name in pending:
                del pending[name]
                tally["single_frame_drops_cancelled"] += 1
            if name in held:
                e = held[name]
            else:
                if last_full is None:
                    lo, hi, inv = -1, asof(s, S), False
                    tally["entries_initial"] += 1
                else:
                    assert name not in last_full.held
                    lo, hi = lo_after(last_full, S), asof(s, S)
                    inv = lo > hi
                    if inv:
                        lo = hi
                        tally["entries_inverted_window"] += 1
                e = Entry(eid=len(entries), sym=name, first_snap=s, prev_full=last_full, lo=lo, hi=hi, inverted=inv)
                entries.append(e)
                held[name] = e
            e.sightings.append(s.idx)
            e.streams.add(s.vid)
        if s.full:
            for name in sorted(set(held) - H):
                g1 = pending.get(name)
                if g1 is None:
                    pending[name] = s                      # first full snapshot without the name: pending
                    continue
                e = held.pop(name)                         # second consecutive full snapshot without it: the exit, dated by the first
                del pending[name]
                last_seen = snaps[e.sightings[-1]]
                e.exit_lo, e.exit_hi, e.exit_snap = lo_after(last_seen, S), asof(g1, S), g1
                if e.exit_lo > e.exit_hi:
                    e.exit_lo = e.exit_hi
                    tally["exits_inverted_window"] += 1
            last_full = s
    tally["pending_exits_at_end"] = len(pending)
    for e in entries:
        if e.exit_snap is not None and len(e.streams) == 1 and not e.initial and e.exit_hi <= asof(e.first_snap, S) + FLICKER_SESSIONS:
            e.flicker = True
            tally["entries_flicker"] += 1
    tally["entries"] = len(entries)
    tally["exits"] = sum(1 for e in entries if e.exit_snap is not None)
    tally["still_held_at_end"] = len(held)
    return entries


# ═════════════════════════════════════════════════════════════════════════════════════════════
# THE ONE CHANGE — a new named function (the copy above is left as it is, for the reproduction gate)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def blip_fill_single_frame(snaps: list, tally: collections.Counter) -> list:
    """THE RULE (module docstring). The same candidate set as `blip_fill` — a name absent from every full frame of one stream, held in the
    nearest full streams before and after — but the fill is made ONLY when that stream has exactly ONE full frame (the name is missing from
    a single complete frame) AND the name is present in another frame of the same stream (a scrolled list that still shows the row: a
    misread row). Every other candidate is a whole-session absence: nothing is filled, counted by shape. Streams with no full frame are
    skipped over (unknown), as today. -> the decisions [(stream vid, name, shape)]."""
    order, streams = [], {}
    for s in snaps:
        if s.vid not in streams:
            order.append(s.vid)
            streams[s.vid] = []
        streams[s.vid].append(s)
    full_streams = [(v, streams[v]) for v in order if any(x.full for x in streams[v])]
    decisions = []
    for k in range(1, len(full_streams) - 1):
        v, fr = full_streams[k]
        full_fr = [x for x in fr if x.full]
        here = set().union(*(x.held for x in full_fr))
        before = set().union(*(x.held for x in full_streams[k - 1][1] if x.full))
        after = set().union(*(x.held for x in full_streams[k + 1][1] if x.full))
        for name in sorted((before & after) - here):
            one_frame = len(full_fr) == 1
            seen_in_session = any(name in x.held for x in fr if not x.full)
            if one_frame and seen_in_session:
                full_fr[0].blip_filled.append(name)
                shape = "kept_one_full_frame_scrolled_sighting"
            elif one_frame:
                shape = "dropped_one_full_frame_no_sighting"
            elif seen_in_session:
                shape = "dropped_many_full_frames_scrolled_sighting"
            else:
                shape = "dropped_many_full_frames_no_sighting"
            tally[f"fills_{shape}"] += 1
            tally["fills_kept" if shape.startswith("kept") else "fills_dropped"] += 1
            decisions.append((v, name, shape))
    return decisions


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the rows (the same cells the holdings read writes for the rule-free columns)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def symbol_join(sym: str, lex: dict, alias: dict) -> tuple:
    """(sym_a, has_bars): the two symbol cells of entries.tsv, the same two expressions as the holdings read's dating function (which is
    not copied: it dates a buy by our events)."""
    sym_a = sym if lex.get(sym, ("",))[0] else alias.get(sym, sym)
    has_bars = bool(lex.get(sym, ("",))[0] or lex.get(sym, ("", "", ""))[2] or (sym_a != sym and lex.get(sym_a, ("",))[0]))
    return sym_a, has_bars


def entry_rows(entries: list, S: Sessions, lex: dict, alias: dict) -> list:
    """The rule-free cells of entries.tsv for every Entry (the dating cells are not built here)."""
    rows = []
    for e in entries:
        sym_a, has_bars = symbol_join(e.sym, lex, alias)
        rows.append({"eid": e.eid, "sym": e.sym, "sym_a": sym_a, "has_bars": has_bars, "first_frame": e.first_snap.frame_id,
                     "first_vid": e.first_snap.vid, "first_date": e.first_snap.date, "first_ctx": e.first_snap.ctx,
                     "prev_full_frame": e.prev_full.frame_id if e.prev_full else "", "prev_full_date": e.prev_full.date if e.prev_full else "",
                     "lo": S.date(e.lo) if e.lo >= 0 else "", "hi": S.date(e.hi), "window_len": e.window_len if not e.initial else "",
                     "inverted": e.inverted, "initial": e.initial, "flicker": e.flicker, "n_sightings": len(e.sightings),
                     "n_streams": len(e.streams), "exit_lo": S.date(e.exit_lo) if e.exit_lo is not None else "",
                     "exit_hi": S.date(e.exit_hi) if e.exit_hi is not None else "", "exit_frame": e.exit_snap.frame_id if e.exit_snap else "",
                     "still_held": e.exit_snap is None, "first_resolution": e.first_snap.resolution})
    return rows


def exit_rows(ent_rows: list) -> list:
    return [{c: r[c] for c in EXIT_COLS} for r in ent_rows if r["exit_frame"]]


def as_written(rows: list, cols: list) -> pd.DataFrame:
    """The rows as pandas writes and re-reads them (strings), so a rebuilt table compares cell for cell with the file on disk."""
    buf = io.StringIO()
    pd.DataFrame(rows, columns=cols).to_csv(buf, sep="\t", index=False)
    buf.seek(0)
    return pd.read_csv(buf, sep="\t", dtype=str, keep_default_na=False, usecols=cols)[cols]


def differences(a: pd.DataFrame, b: pd.DataFrame, key: str = "eid") -> list:
    """[(key, column, ours, theirs)] where the two tables differ (a row missing on one side counts once per row)."""
    out = []
    if list(a.columns) != list(b.columns):
        out.append(("columns", "", list(a.columns), list(b.columns)))
        return out
    ak, bk = a[key].tolist(), b[key].tolist()
    if ak != bk:
        out.append((key, "order/count", len(ak), len(bk)))
        return out
    for col in a.columns:
        av, bv = a[col].tolist(), b[col].tolist()
        for i, (x, y) in enumerate(zip(av, bv)):
            if x != y:
                out.append((ak[i], col, x, y))
    return out


def build(snaps: list, S: Sessions, rule) -> tuple:
    """Clear the fills, apply `rule` (the old `blip_fill` or the new `blip_fill_single_frame`), run the copied state machine.
    -> (entries, tally, the rule's return value)."""
    for s in snaps:
        s.blip_filled = []
    tally = collections.Counter()
    extra = rule(snaps, tally)
    entries = timeline(snaps, S, tally, None)
    return entries, tally, extra


def fill_column(snaps: list) -> list:
    return [",".join(s.blip_filled) for s in snaps]


def pieces_by_host(v1: list, v2: list) -> tuple:
    """({v1 eid: [v2 entries]} — every v2 position hosted by the ONE v1 position of its symbol whose sightings span its first sighting,
    in v2 order; [v2 entries] hosted by none or several). A v1 position maps to its pieces: 0 = vanished, 1 = kept, 2+ = split."""
    span = collections.defaultdict(list)
    for e in v1:
        span[e.sym].append(e)
    pieces, unhosted = collections.defaultdict(list), []
    for e2 in v2:
        first = e2.sightings[0]
        hosts = [e for e in span.get(e2.sym, ()) if e.sightings[0] <= first <= e.sightings[-1]]
        if len(hosts) == 1:
            pieces[hosts[0].eid].append(e2)
        else:
            unhosted.append(e2)
    return pieces, unhosted


def splits(v1: list, v2: list, snaps: list) -> list:
    """[(v1 entry, [v2 entries])] for every v1 position whose sightings hold the FIRST sighting of two or more v2 positions of its symbol."""
    pieces, _un = pieces_by_host(v1, v2)
    return [(e, pieces[e.eid]) for e in v1 if len(pieces.get(e.eid, ())) >= 2]


def vanished(v1: list, pieces: dict, v1_fill: list) -> list:
    """Review F2: [(v1 entry, every sighting was a filled frame)] for every v1 position hosting NO v2 piece. Under the rule a dropped fill
    never merges, so a v1 position can only disappear when every one of its sightings was a frame the old fill put it on."""
    out = []
    for e in v1:
        if not pieces.get(e.eid):
            all_fills = all(e.sym in v1_fill[i].split(",") for i in e.sightings)
            out.append((e, all_fills))
    return out


def changed_without_split(v1: list, pieces: dict) -> tuple:
    """Review F4: ([v1 entry, its one v2 piece] whose buy window moved, [...] whose sale window moved) among the v1 positions hosting exactly
    ONE v2 piece (a position neither split nor vanished whose window still moved: a neighbour's dropped fill re-dated it)."""
    buy, sale = [], []
    for e in v1:
        ps = pieces.get(e.eid, ())
        if len(ps) != 1:
            continue
        p = ps[0]
        if (e.lo, e.hi, e.inverted) != (p.lo, p.hi, p.inverted):
            buy.append((e, p))
        if (e.exit_lo, e.exit_hi, e.exit_snap is not None) != (p.exit_lo, p.exit_hi, p.exit_snap is not None):
            sale.append((e, p))
    return buy, sale


def one_frame_no_sighting(decisions: list, snaps: list, v2: list) -> list:
    """R48: [(session date, name, outcome)] for every `dropped_one_full_frame_no_sighting` candidate (a one-complete-frame session lacking
    the stock with no other sighting), the outcome under the v2 timeline: 'split' — a v2 position of that name EXITS on that stream's
    complete frame (the next session's first complete frame also lacked it); 'carried' — a v2 position of that name is held ACROSS the
    session (a sighting before the stream and one after: the next sighting cancelled the pending exit; the literal reading would end it
    here); 'not_held' — no v2 position of that name spans the session (the old fill had invented a START there, so the position now
    begins at the next sighting; the literal reading changes nothing)."""
    first_date, span = {}, {}
    for s in snaps:
        first_date.setdefault(s.vid, s.date)
        lo, hi = span.get(s.vid, (s.idx, s.idx))
        span[s.vid] = (min(lo, s.idx), max(hi, s.idx))
    out = []
    for vid, name, shape in decisions:
        if shape != "dropped_one_full_frame_no_sighting":
            continue
        lo, hi = span[vid]
        if any(e.sym == name and e.exit_snap is not None and e.exit_snap.vid == vid for e in v2):
            outcome = "split"
        elif any(e.sym == name and e.sightings[0] < lo and e.sightings[-1] > hi for e in v2):
            outcome = "carried"
        else:
            outcome = "not_held"
        out.append((first_date[vid], name, outcome))
    return out


def scrolled_between(decisions: list, snaps: list) -> int:
    """Review F7: among the `dropped_many_full_frames_scrolled_sighting` candidates, how many have a scrolled sighting lying BETWEEN two complete
    frames of the stream (the order on which the unchanged exit rule carries the position instead of ending it)."""
    by_vid = collections.defaultdict(list)
    for s in snaps:
        by_vid[s.vid].append(s)
    n = 0
    for vid, name, shape in decisions:
        if shape != "dropped_many_full_frames_scrolled_sighting":
            continue
        fr = by_vid[vid]
        full_idx = [k for k, x in enumerate(fr) if x.full]
        if any(not x.full and name in x.held and full_idx[0] < k < full_idx[-1] for k, x in enumerate(fr)):
            n += 1
    return n


def window_words(e, S: Sessions) -> str:
    buy = f"buy [{S.date(e.lo) if e.lo >= 0 else 'initial'}..{S.date(e.hi)}]"
    sale = f"sale [{S.date(e.exit_lo)}..{S.date(e.exit_hi)}]" if e.exit_snap is not None else "still held"
    return f"#{e.eid} {e.sym} {buy} {sale} (first {e.first_snap.frame_id} {e.first_snap.date} {e.first_snap.ctx}; {len(e.sightings)} sightings, " \
           f"{len(e.streams)} streams{'; flicker' if e.flicker else ''})"


def by_year(entries: list, S: Sessions) -> tuple:
    """(buy windows by year of the window end, sale windows by year of the window end) — non-initial buys; exits."""
    buys = collections.Counter(S.date(e.hi)[:4] for e in entries if not e.initial)
    sales = collections.Counter(S.date(e.exit_hi)[:4] for e in entries if e.exit_snap is not None)
    return buys, sales


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the stages
# ═════════════════════════════════════════════════════════════════════════════════════════════
def compute(say, claims: Claims) -> dict:
    t0 = time.time()
    S = C.sealed_sessions()
    df, snaps = read_snapshot_table(C.FILES["snapshots"])
    say(f"- snapshots.tsv: {len(snaps):,} frames, {sum(s.full for s in snaps):,} full; {len({s.vid for s in snaps})} streams, "
        f"{len({s.vid for s in snaps if s.full})} with a full frame, {sum(1 for v, n in collections.Counter(s.vid for s in snaps if s.full).items() if n == 1)} "
        f"with exactly one full frame; calendar {len(S.cal):,} sessions to {C.CUT_B}")
    lex = C.load_lexicon()
    tally_alias = collections.Counter()
    alias = C.load_alias(lex, tally_alias)
    say(f"- lexicon {len(lex):,} symbols; alias map {len(alias):,} (signature {tally_alias['alias_signature']}, dedupe {tally_alias['alias_dedupe']}) — "
        "the holdings read's own map (no rename table: entries.tsv's sym_a predates it)")
    ent1 = pd.read_csv(C.checked(C.FILES["entries"]), sep="\t", dtype=str, keep_default_na=False, usecols=ENTRY_COLS)[ENTRY_COLS]
    exi1 = pd.read_csv(C.checked(C.FILES["exits"]), sep="\t", dtype=str, keep_default_na=False, usecols=EXIT_COLS)[EXIT_COLS]
    old_fill = df["blip_filled"].tolist()
    claims("frames (snapshots.tsv rows)", 2907, len(snaps))
    claims("full frames", 2082, sum(s.full for s in snaps))
    claims("positions on disk (entries.tsv rows)", 1874, len(ent1))
    claims("exits on disk (exits.tsv rows)", 1861, len(exi1))
    claims("filled symbol-frames on disk (the diagnosis: 573 on 518 frames)", (573, 518),
           (sum(len([x for x in c.split(",") if x]) for c in old_fill), sum(1 for c in old_fill if c)))
    claims("every fill on disk sits on a frame marked full", 0, sum(1 for s, c in zip(snaps, old_fill) if c and not s.full))

    # ---- v1: the old rule, rebuilt -> the reproduction gate
    say("\n## The reproduction gate (the OLD rule rebuilt from snapshots.tsv must reproduce the files on disk exactly)")
    v1, t1, _ = build(snaps, S, blip_fill)
    rows1 = entry_rows(v1, S, lex, alias)
    d_ent = differences(as_written(rows1, ENTRY_COLS), ent1)
    d_exi = differences(as_written(exit_rows(rows1), EXIT_COLS), exi1)
    new_fill = fill_column(snaps)
    d_fill = [(s.frame_id, "blip_filled", a, b) for s, a, b in zip(snaps, new_fill, old_fill) if a != b]
    for lab, d in (("entries.tsv (the rule-free columns)", d_ent), ("exits.tsv", d_exi), ("snapshots.tsv blip_filled", d_fill)):
        for x in d[:20]:
            say(f"    differs: {lab} {x}")
    claims("reproduction: entries.tsv differences", 0, len(d_ent))
    claims("reproduction: exits.tsv differences", 0, len(d_exi))
    claims("reproduction: snapshots.tsv blip_filled differences", 0, len(d_fill))
    say(f"- old rule rebuilt: {len(v1):,} positions, {t1['exits']:,} exits, {t1['blips_filled']} (stream, name) fills "
        f"({t1['blips_over_footer_consistent_absence']} over a footer-consistent absence), single-frame drops cancelled {t1['single_frame_drops_cancelled']}, "
        f"flickers {t1['entries_flicker']}")
    v1_fill = list(new_fill)

    # ---- v2: the new rule
    say("\n## The windows v2 (the NEW rule: a fill bridges a single-frame miss only)")
    v2, t2, decisions = build(snaps, S, blip_fill_single_frame)
    rows2 = entry_rows(v2, S, lex, alias)
    v2_fill = fill_column(snaps)
    say(f"- (stream, name) fill candidates {len(decisions)}: kept {t2['fills_kept']} (single-frame: one complete frame, the stock in a scrolled "
        f"frame of the same session) / dropped {t2['fills_dropped']} (whole-session absences); by shape: "
        + ", ".join(f"{sh} {t2['fills_' + sh]}" for sh in FILL_SHAPES))
    claims("fills kept + dropped = the old rule's (stream, name) fills (the same candidate set)", t1["blips_filled"], t2["fills_kept"] + t2["fills_dropped"])
    claims("filled symbol-frames v2 <= v1", True, sum(len(s.blip_filled) for s in snaps) <= sum(len([x for x in c.split(",") if x]) for c in old_fill))
    say(f"- positions before {len(v1):,} -> after {len(v2):,} (+{len(v2) - len(v1)}); exits {t1['exits']:,} -> {t2['exits']:,}; initial {t1['entries_initial']} -> "
        f"{t2['entries_initial']}; still held at the end {t1['still_held_at_end']} -> {t2['still_held_at_end']}; flickers {t1['entries_flicker']} -> {t2['entries_flicker']}; "
        f"single-frame drops cancelled {t1['single_frame_drops_cancelled']} -> {t2['single_frame_drops_cancelled']}; inverted buy windows "
        f"{t1['entries_inverted_window']} -> {t2['entries_inverted_window']}, inverted sale windows {t1['exits_inverted_window']} -> {t2['exits_inverted_window']}")
    claims("v2 positions >= v1 positions (a dropped fill never merges; the splits, the vanished and the moved windows are counted below)", True,
           len(v2) >= len(v1))
    pieces, unhosted = pieces_by_host(v1, v2)
    sp = splits(v1, v2, snaps)
    van = vanished(v1, pieces, v1_fill)
    n_pieces = sum(len(ps) for _e, ps in sp)
    say(f"- positions SPLIT (a v1 position now hosting the first sighting of 2+ v2 positions): {len(sp)}, into {n_pieces} pieces (+{n_pieces - len(sp)}); "
        f"VANISHED (a v1 position hosting no v2 position: every sighting was a fill, review F2): {len(van)} (-{len(van)}); v2 positions not hosted by "
        f"any v1 position of their symbol: {len(unhosted)}; net {len(v2) - len(v1):+d}")
    for e, ps in sp:
        say(f"    {window_words(e, S)} -> " + " | ".join(window_words(p, S) for p in ps))
    for e, all_fills in van:
        say(f"    vanished: {window_words(e, S)}; every sighting a filled frame: {all_fills}")
    claims("v2 positions = v1 + (pieces - splits) - vanished + unhosted (every v1 position hosts 0, 1 or 2+ pieces)", len(v2),
           len(v1) + n_pieces - len(sp) - len(van) + len(unhosted))
    claims("vanished v1 positions (review F2): every sighting was a filled frame", [], [e.sym for e, ok in van if not ok])
    claims("vanished v1 positions (review F2): the two phantoms (symbol, first sighting)", [("BNTX", "2020-07-27"), ("SE", "2021-03-15")],
           [(e.sym, e.first_snap.date) for e, _ok in van])
    cb, cs = changed_without_split(v1, pieces)
    say(f"- windows changed WITHOUT a split (a v1 position hosting exactly one v2 piece whose window moved, review F4): {len(cb)} buy / {len(cs)} sale")
    for lab, lst in (("buy", cb), ("sale", cs)):
        for e, p in lst:
            say(f"    {lab} moved: {window_words(e, S)} -> {window_words(p, S)}")
    claims("windows changed without a split (review F4): buy / sale", (9, 12), (len(cb), len(cs)))
    def spans(e, sym, d0, d1):
        """The position (of `sym`) is held somewhere in d0..d1: its buy window starts by d1 and its sale window ends at or after d0."""
        return e.sym == sym and S.date(e.lo if e.lo >= 0 else e.hi) <= d1 and (e.exit_snap is None or S.date(e.exit_hi) >= d0)
    for sym, d0, d1 in NAMED_CASES + EYEBALL_CASES:
        say(f"- {sym} {d0}..{d1} ({'the diagnosis' if (sym, d0, d1) in NAMED_CASES else 'R48, to eyeball'}'s case), v1:")
        for e in v1:
            if spans(e, sym, d0, d1):
                say(f"    {window_words(e, S)}")
        say(f"  v2:")
        for e in v2:
            if spans(e, sym, d0, d1):
                say(f"    {window_words(e, S)}")
    def is_split(sym, day):
        return any(e.sym == sym and S.date(e.lo if e.lo >= 0 else e.hi) <= day <= (S.date(e.exit_hi) if e.exit_snap is not None else "9999") for e, _ps in sp)
    claims("SPXL: the position holding 2020-04-20 is split", True, is_split("SPXL", "2020-04-20"))
    claims("LAKE: the position holding 2020-01-23 is split", True, is_split("LAKE", "2020-01-23"))
    r48 = one_frame_no_sighting(decisions, snaps, v2)
    n_of = lambda o: sum(1 for x in r48 if x[2] == o)
    say(f"- R48 (one-complete-frame sessions lacking the stock with no other sighting; the reading to confirm or reverse before 01 --print-pins): "
        f"{len(r48)} — carried across the session as one v2 position (the literal reading would end it there) {n_of('carried')}, not held in v2 at "
        f"that session (the old fill invented the start; the literal reading changes nothing) {n_of('not_held')}, split (the next session's first "
        f"complete frame also lacked it) {n_of('split')}: " + ", ".join(f"{n} {d} {o}" for d, n, o in r48))
    claims("R48: one-complete-frame sessions with no sighting (total, carried, not held in v2, split)", (7, 5, 1, 1),
           (len(r48), n_of("carried"), n_of("not_held"), n_of("split")))
    claims("R48: the five carried (the review's F3 counted WEAT 2022-05-10 as split; the next session's first complete frame holds it)",
           [("TSLA", "2017-02-02"), ("BLDP", "2019-12-19"), ("QS", "2020-12-14"), ("CLF", "2021-03-31"), ("WEAT", "2022-05-10")],
           [(n, d) for d, n, o in r48 if o == "carried"])
    claims("R48: the one not held in v2 at that session (the old fill back-dated its buy; v2 #176 starts 2019-10-21)", [("APPS", "2019-10-18")],
           [(n, d) for d, n, o in r48 if o == "not_held"])
    claims("R48: the one that splits", [("LK", "2020-01-15")], [(n, d) for d, n, o in r48 if o == "split"])
    claims("review F7: dropped scrolled-sighting candidates whose sighting lies between two complete frames (the position carried)", 0,
           scrolled_between(decisions, snaps))
    say("\n## Buy / sale windows by year (year of the window end), v1 beside v2")
    b1, s1 = by_year(v1, S)
    b2, s2 = by_year(v2, S)
    years = sorted(set(b1) | set(b2) | set(s1) | set(s2))
    table(say, ["side"] + years + ["total"], [["buys v1"] + [b1.get(y, 0) for y in years] + [sum(b1.values())],
                                               ["buys v2"] + [b2.get(y, 0) for y in years] + [sum(b2.values())],
                                               ["sales v1"] + [s1.get(y, 0) for y in years] + [sum(s1.values())],
                                               ["sales v2"] + [s2.get(y, 0) for y in years] + [sum(s2.values())]])
    say(f"- in {time.time() - t0:.0f}s")
    df2 = df.copy()
    df2["blip_filled"] = v2_fill
    same = [c for c in df.columns if c != "blip_filled" and df[c].tolist() != df2[c].tolist()]
    claims("snapshots_v2: every column but blip_filled identical to snapshots.tsv", [], same)
    return {"S": S, "snaps": snaps, "v1": v1, "v2": v2, "rows2": rows2, "df2": df2, "t1": t1, "t2": t2, "splits": sp, "v1_fill": v1_fill}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    say = Say()
    out_path = P_DRY if a.dry_run else P_WRITE
    say(f"# #705 as-is STEP 5 re-run 2 prep — THE WINDOWS v2 — {'DRY RUN' if a.dry_run else 'WRITE'} ({time.strftime('%Y-%m-%d %H:%M')})")
    say("Guards: no network, no production server, no paid call, nothing after 2024-12-31, the seven outcome folders never opened, nothing "
        "imported from the rule folders (copies). No rule, setup name or pattern label enters; no bar or minute file is opened.")
    hits = C.scan_identifiers([os.path.join(HERE, "asis_common.py"), os.path.abspath(__file__)])
    if hits:
        say("IDENTIFIER SCAN FAILED: " + "; ".join(f"{os.path.basename(p)}:{ln} {t}" for p, ln, t in hits))
        say.write(out_path)
        return 2
    say("- identifier scan: clean")
    loaded = C.rule_modules_loaded()
    if loaded:
        say("RULE MODULE LOADED (guard 3): " + ", ".join(loaded))
        say.write(out_path)
        return 2
    say("- import belt: no rule module in sys.modules")
    say("- modules: " + C.modules_line(C.MODULES_00C))      # the one builder step 5's run gate compares against (review F6)
    say("- inputs: " + " ".join(f"{k} {C.sha(C.FILES[k])[:16]}" for k in ("snapshots", "entries", "exits", "lexicon", "calendar_cache", "dedupe_A", "sessions_A")))
    say("\n## Inputs")
    claims = Claims(say)
    R = compute(say, claims)
    say("")
    say(claims.result())
    if a.dry_run:
        say("DRY RUN COMPLETE")
        say.write(P_DRY)
        return 0
    if claims.mismatches():
        say("REFUSED: a claim mismatched; nothing written")
        say.write(P_WRITE)
        return 3
    existing = [p for p in OUT.values() if os.path.exists(p)]
    if existing:
        say("REFUSED: outputs exist: " + ", ".join(existing))
        say.write(P_WRITE)
        return 3
    os.makedirs(C.W2_DIR, exist_ok=True)
    rows2 = R["rows2"]
    for key, rows, cols in (("entries_v2", rows2, ENTRY_COLS), ("exits_v2", exit_rows(rows2), EXIT_COLS)):
        pd.DataFrame(rows, columns=cols).to_csv(OUT[key] + ".partial", sep="\t", index=False)
        os.replace(OUT[key] + ".partial", OUT[key])
    R["df2"].to_csv(OUT["snapshots_v2"] + ".partial", sep="\t", index=False)
    os.replace(OUT["snapshots_v2"] + ".partial", OUT["snapshots_v2"])
    say("\n## Outputs")
    for k, p in OUT.items():
        say(f"- {k}: {p} ({sum(1 for _ in open(p)) - 1:,} rows, {C.sha(p)[:16]})")
    say("WRITE COMPLETE")
    say.write(P_WRITE)
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registry the copy test iterates (asis_common.COPIED's shape): (source file; name; kind; NAME-token renames)
# ═════════════════════════════════════════════════════════════════════════════════════════════
COPIED = (
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'FLICKER_SESSIONS', 'assign', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'Entry', 'class', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'blip_fill', 'def', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'timeline', 'def', {}),
)


if __name__ == "__main__":
    sys.exit(main())
