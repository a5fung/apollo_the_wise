#!/usr/bin/env python3
"""#705 — HOLDINGS 01: his positions panel -> the holdings timeline -> the buy dating -> the positive control. OUTCOME-FREE.
(docs/analysis/cb_holdings_replay_prereg_2026-10-24.md). Reads the panel reader's output (every stream frame's "A - Positions" list),
the candidate streams (pre-E facts only: D, E, level, ADR20), the EP gap-day events and the frozen Track A label classes. It opens NO
bar after any buy day, NO minute file, NO replay outcome file. Every rule below was fixed BEFORE any count was read.

THE TIMELINE (snapshot level, aggregated to streams)
  snapshot    one frame with the panel found (list A, or the 2017 'B - Positions' list). Its date = the MODE of its video's taskbar dates
              (a stray frame date never misplaces a snapshot). Its clock context: pre (before the open), in (session), closed (after).
  full        the list is wholly visible: the footer total equals the rows read; a footer total above the rows read = scrolled (NOT
              full); no usable footer -> geometry: the last row ends >= 1.5 row pitches above the panel's bottom (the list ends) = full.
              A list reading "0 items" is a full EMPTY snapshot (he holds nothing).
  duplicates  (F1) the same stream uploaded twice on one date: a frame whose (clock read, stream time, list, rows read, footer total)
              already appeared in ANOTHER video that date is dropped (videos taken largest first, then by vid); a video that lost a
              frame so is a duplicate upload, and its leftover frames join the kept copy's STREAM (`vid`; `vid_raw` keeps the upload).
  order       (F1) each date's frames by their ET clock ACROSS videos: the frame's video clock fitted to stream time (stream time + the
              median of clock read - stream time over the video; a misread clock - 21, all 2019 - never reorders a video's frames), then
              the stream time. A video with no clock read keeps its stream time (all 7 are the only video on their date). (Until F1:
              video by video, by the video's earliest context and clock - a duplicate upload replayed its frames after the first copy's
              and the clock ran backwards.)
  asof(s)     the last session whose close the snapshot's holdings reflect: pre -> the session before its date; in / closed -> its date.
  entry       a name in snapshot s that is not held: bought in the window [lo, hi] of SESSIONS, hi = asof(s), lo = the first session on
              which a buy could be missing from the LAST FULL snapshot f: f pre or in -> f's own date (a buy later that day is
              possible), f closed -> the next session. No full snapshot before s -> INITIAL (undatable; counted; never replayed).
              lo > hi (after-hours / OCR) -> lo = hi, flagged `inverted`.
  exit        only FULL snapshots can show an exit, and it takes TWO: a held name absent from a full snapshot g1 is pending; absent again
              from the next full snapshot g2 (with no sighting in between) it was sold in [lo, hi], lo from its last sighting as for an
              entry, hi = asof(g1). A sighting before g2 cancels the pending exit (a single-frame OCR drop, counted). A name still
              held at the last snapshot is `still_held`. (Fixed after the first timeline run, before any outcome: 231 of 2,131
              one-frame exits were undone by the very next full frame, 174 of them inside the same stream - the reader's ~2% per-symbol
              miss rate, not round trips. The first run's one-frame rule is recorded in the registration's revision log.)
  blip        a name absent from every full snapshot of exactly ONE stream and present in the nearest full streams before and after is an
              OCR miss: held throughout (the stream's full snapshots are filled, counted). A stream = one video (its duplicate's leftovers
              joined), the streams in the order of their first frame.
  look-alike  (F2) a name X first appears in snapshot s; the last full snapshot f holds a symbol Y one edit away from X (UI / LI, SO /
              SQ, BIL / BILI); Y is absent from s; and the reader flagged Y's row in f - its % cell disagrees with Y's own bars that day
              (`mismatch_kept`) or its look-alike search suggested X (`pct_suggest`). Then Y in f is X misread: f is relabelled Y -> X (X
              was held there, so no entry for Y and X's window starts before f) and the timeline is recomputed, to a fixed point. The %
              check uses the frame day's own range - no bar after it. One X with several such Y: only the suggested one, else no rename;
              one Y claimed by several X: the suggested X, else the X whose % read in s is nearest Y's in f, else no rename. Counted, and
              every rename printed with both frames.
  flicker     an entry seen in ONE stream only whose exit is confirmed within 5 sessions of the sighting: a short hold (a same-day round
              trip) or a misread. Counted and FLAGGED; a dated flicker still decides (it is a setup trade he left quickly - dropping it
              would drop his likely losers; the first run's "never replayed" is withdrawn in the revision log, no outcome seen). The
              deciding set without flickers is read beside.
THE BUY DATING (fixed before any count; `WINDOW_CAP` decides)
  events      the name's tl breakout days E (era A `candidates_tl_com.tsv` K = tl for E <= 2022-03-31; era B `candidates.tsv` K = tl,
              discovery, E >= 2022-04-01, every row after 2024-12-31 dropped at read) and its EP gap days (ep_events_{A,B}, `primary`),
              with E inside [lo, hi]. The panel's symbol is the contemporary one; era A's files key today's symbol, so a name with no
              era-A rows is mapped by the overlap-close signature (FB -> META) or the dedupe map (a dropped twin -> its kept twin).
  rule        the LATEST event in the window dates the buy (the position held at hi was most plausibly opened at the most recent
              trigger); both kinds on that day -> `both` (the breakout row carries the level). The EARLIEST event is read beside.
  undated     no event -> the buy is placed on lo (the first session after the last full snapshot without the name), at its open:
              BESIDE only, never deciding. A name our bars never carry (GBTC, ETNs, SPACs) is `no_bars`; an ETF / name never in a
              candidate stream is `never_candidate` - both undated, listed.
  panel clock (F3, read beside the fill minute in the run, never a filter) `first_clock_on_E` = the first sighting's ET clock when it is
              on E in session; `flat_clock_on_E` = the clock of the last full snapshot without the name when it is on E;
              `orh5_infeasible` = held on E before 09:35 ET (before any ORH5 fill can exist).
  decides     dated (breakout / EP / both) AND window <= WINDOW_CAP sessions AND not initial. A wider window is read beside. The
              DECIDING WINDOW of the account (fixed from stream coverage and frame resolution, outcome-free, in the registration) is
              the 1920x1080 era with dense streams; the 1280x720 streams (2019-10 .. 2020-01: symbols alternate between a name and
              its look-alike inside one stream, APPS / ASPS) and the sparse 2022-11 .. 2023-12 tail are read beside.
  Q1 2022     no breakout stream covers 2022-01-04..2022-03-31 (era A's last E is 2022-01-03; era B's discovery starts 2022-04-01): an
              entry there can only be EP or undated. Stated, counted.
THE POSITIVE CONTROL (the 236 stream calls, labels said on or before E, from the frozen fit module): how many are panel entries whose
  window holds E, dated ON E by the rule (and by the earliest rule), decided; the nearest snapshot after E; seen in E..E+20 at all.

A name's later entry dated to the SAME E as its earlier one is listed here and classified `same_day_rebuy` by the replay (F4).

No subagent, no DB, no network. Read-only on every input. Writes the printout and four TSVs (snapshots, entries, exits, control).
Run:  python3 scripts/probes/_705_holdings_1024/01_timeline.py
"""
from __future__ import annotations

import argparse
import bisect
import collections
import gzip
import hashlib
import importlib.util
import json
import os
import pickle
import statistics
import sys
from dataclasses import dataclass, field

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXEC_PATH = os.path.join(REPO, "scripts", "probes", "_705_qm_replay_1023", "02_execution_variants.py")


def _load_frozen():
    """The FROZEN second read (pinned 346516fb...), imported read-only; it imports the frozen first read (c4478588...) and the frozen Track A
    fit module. Used here ONLY for the label classes (his 236 calls) and the shared readers."""
    spec = importlib.util.spec_from_file_location("_705_exec02_frozen_h", EXEC_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_705_exec02_frozen_h"] = mod
    spec.loader.exec_module(mod)
    return mod


ex = _load_frozen()
rp = ex.rp

DATA = "/Users/alvinfung/apollo_data"
VIS = f"{DATA}/cb702/qm_streams/vision"
OUT_DIR = f"{DATA}/cb702/qm_streams/holdings_1024"
PRINTOUT = os.path.join(HERE, "01_timeline.txt")
FILES = {
    "panel": f"{VIS}/positions_panel_all.jsonl",
    "calendar_cache": f"{VIS}/positions_pct_calendar.pkl.gz",          # (SPY sessions of both bar files, the overlap-close signatures)
    "lexicon": f"{VIS}/positions_ticker_lexicon_v2.tsv",              # ticker, first/last in the 2016-22 file, first/last in the 2021-26 file
    "dedupe_A": f"{DATA}/cb702_pre_v2/dedupe_applied.tsv",             # dropped twin -> kept twin (era A)
    "cand_A": rp.FILES["cand_A"],
    "cand_B": rp.FILES["cand_B"],
    "ep_A": f"{DATA}/cb702/qm_streams/ep_join_1023/ep_events_A.tsv.gz",
    "ep_B": f"{DATA}/cb702/qm_streams/ep_join_1023/ep_events_B.tsv.gz",
    "sessions_A": rp.FILES["sessions_A"],
    "labels_joined": rp.FILES["labels_joined"],
    "matched_events": rp.FILES["matched_events"],
    "moments": rp.FILES["moments"],
}
OUT = {k: os.path.join(OUT_DIR, f"{k}.tsv") for k in ("snapshots", "entries", "exits", "control")}

# ---- the registration's constants -------------------------------------------------------------------------------------------------------
CUT_B = "2024-12-31"                 # nothing dated after this is kept from any era-B file
ERA_A_LAST_E = "2022-03-31"          # breakout / EP events up to here come from the era-A files (era A's own last E is 2022-01-03)
ERA_B_FIRST_E = "2022-04-01"         # and from here from era B (discovery split)
WINDOW_CAP = 10                      # sessions: a dated entry whose window is at most this DECIDES; wider is beside
SIG_DATES = ("2021-10-01", "2021-11-01", "2021-12-01")   # the reader's overlap sessions: a renamed symbol's era-A name by its closes
CTX_RANK = {"pre": 0, "in": 1, "closed": 2}
PITCH_DEFAULT = {"1920x1080": 18.0, "1280x720": 12.0}
FULL_GAP_PITCHES = 1.5               # geometry: the last row ends at least this many row pitches above the panel body's bottom
CONTROL_LOOKAHEAD = 20               # sessions after E in which "seen in the panel at all" is read
DECIDING_WINDOW = ("2020-01-27", "2022-06-14")   # the deciding account's span (registration §2, R5): the counts below are read on it too
ORH5_FIRST = "09:35"                 # the first minute an ORH5 fill can exist (the 5-minute opening range ends 09:35 ET)


class Say:
    def __init__(self):
        self.lines = []

    def __call__(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.lines.append(msg)

    def write(self, path: str) -> None:
        with open(path + ".partial", "w") as fh:
            fh.write("\n".join(self.lines) + "\n")
        os.replace(path + ".partial", path)


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def ts_seconds(ts: str) -> int:
    p = [int(x) for x in ts.split(":")]
    while len(p) < 3:
        p.insert(0, 0)
    return p[0] * 3600 + p[1] * 60 + p[2]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the sessions
# ═════════════════════════════════════════════════════════════════════════════════════════════
class Sessions:
    """ISO session dates, sorted. Indices are session numbers."""

    def __init__(self, cal: list):
        self.cal = list(cal)
        assert all(a < b for a, b in zip(self.cal, self.cal[1:])), "calendar not strictly ascending"

    def le(self, d: str) -> int:       # last session <= d (-1 if none)
        return bisect.bisect_right(self.cal, d) - 1

    def lt(self, d: str) -> int:       # last session < d
        return bisect.bisect_left(self.cal, d) - 1

    def ge(self, d: str) -> int:       # first session >= d (len if none)
        return bisect.bisect_left(self.cal, d)

    def gt(self, d: str) -> int:       # first session > d
        return bisect.bisect_right(self.cal, d)

    def date(self, i: int) -> str:
        return self.cal[i]


def load_sessions() -> Sessions:
    """The reader's calendar cache = the SPY sessions of both bar files (asserted equal to `sessions_A` on era A's span)."""
    with gzip.open(FILES["calendar_cache"], "rb") as fh:
        cal, _sig = pickle.load(fh)
    with open(FILES["sessions_A"]) as fh:
        sess_a = [ln.strip() for ln in fh if ln.strip()]
    assert cal[:len(sess_a)] == sess_a, "the calendar cache does not start with cb702_pre_v2/sessions.txt"
    return Sessions(cal)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the snapshots
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Snap:
    idx: int                 # position in the ordered timeline
    frame_id: str
    vid: str
    folder: str
    date: str                # the video's mode date
    frame_date: str          # this frame's own taskbar date
    ctx: str                 # pre | in | closed  ('' / None -> 'in', the widest reading)
    ctx_raw: str
    et_time: str
    stream_ts: int
    resolution: str
    list_name: str
    symbols: list
    visible_n: int
    total_n: "int | None"
    full: bool
    full_how: str
    blip_filled: list = field(default_factory=list)   # names added by the blip rule
    vid_raw: str = ""                                  # the uploaded video (a duplicate upload's leftover frames carry the kept copy's vid)
    clock_s: float = 0.0                               # the frame's ET clock, seconds: its video's clock fitted to stream time (F1)
    rows_meta: dict = field(default_factory=dict)      # sym -> (pct_check, pct_suggest, pct) of the reader's row (F2)
    relabeled: list = field(default_factory=list)      # [(read, held)] look-alike renames applied to this snapshot (F2)
    clock_known: bool = True                           # False: its video carries no clock read at all (clock_s = stream time)

    @property
    def held(self) -> set:
        return set(self.symbols) | set(self.blip_filled)


def full_flag(rec: dict) -> tuple:
    """(full, how). Footer first; geometry when the footer is unusable."""
    v, t = int(rec.get("visible_n") or 0), rec.get("total_n")
    rows = rec.get("rows") or []
    if t is not None and t == v:
        return True, "footer_eq"
    if t is not None and t > v:
        return False, "footer_scrolled"
    # footer missing or below the rows read: geometry
    body = (rec.get("layout") or {}).get("body")
    if not rows or not body:
        return False, "no_rows_no_footer"
    ys0 = [r["y"][0] for r in rows]
    if len(ys0) >= 2:
        pitch = statistics.median(b - a for a, b in zip(ys0, ys0[1:]))
    else:
        pitch = PITCH_DEFAULT.get(rec.get("resolution"), 18.0)
    if not pitch or pitch <= 0:
        pitch = PITCH_DEFAULT.get(rec.get("resolution"), 18.0)
    gap = body[1] - max(r["y"][1] for r in rows)
    return (gap >= FULL_GAP_PITCHES * pitch), ("geom_full" if gap >= FULL_GAP_PITCHES * pitch else "geom_reaches_bottom")


def et_seconds(et_time: str) -> "int | None":
    """'2020-05-20T10:40-04:00' -> 38400 (the ET wall clock of the frame's own clock read); '' -> None."""
    if not et_time or len(et_time) < 16:
        return None
    return int(et_time[11:13]) * 3600 + int(et_time[14:16]) * 60


def hhmm(sec: float) -> str:
    sec = int(sec) % 86400
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}"


def frame_signature(r: dict) -> tuple:
    """A frame's identity across duplicate uploads (F1): its clock read, stream time, list, rows read and footer total."""
    return (r.get("et_time") or "", ts_seconds(r["stream_ts"]), tuple(s for s in r.get("symbols") or [] if s), int(r.get("visible_n") or 0),
            r.get("total_n"))


def dedupe_uploads(recs: list, vdate: dict, tally: collections.Counter) -> tuple:
    """(kept recs, stream vid per kept rec's vid). F1: the same stream uploaded twice (or more) on one date carries identical frames. On
    each date the videos are taken largest first (frame count, then vid); a frame whose signature already appeared in an earlier-taken
    video that day is DROPPED; a video that lost any frame this way is a duplicate upload of the video it matched, and its leftover frames
    (the same stream sampled a few seconds apart) join that video's STREAM (`vid`; `vid_raw` keeps the upload)."""
    by_vid = collections.defaultdict(list)
    for r in recs:
        by_vid[r["vid"]].append(r)
    by_date = collections.defaultdict(list)
    for v in by_vid:
        by_date[vdate[v]].append(v)
    stream_of, keep = {}, []
    for d in sorted(by_date):
        seen = {}                                      # signature -> the stream vid of the earlier-taken video that carried it
        for v in sorted(by_date[d], key=lambda x: (-len(by_vid[x]), x)):
            hits = [seen[frame_signature(r)] for r in by_vid[v] if frame_signature(r) in seen]
            stream_of[v] = collections.Counter(hits).most_common(1)[0][0] if hits else v
            if hits:
                tally["duplicate_upload_videos"] += 1
                tally["duplicate_frames_dropped"] += len(hits)
            mine = {}
            for r in by_vid[v]:
                sg = frame_signature(r)
                if sg in seen:                         # carried by ANOTHER video that day (repeats inside one video are kept)
                    continue
                if hits:
                    tally["duplicate_leftover_frames_joined"] += 1
                mine[sg] = stream_of[v]
                keep.append(r)
            for sg, sv in mine.items():
                seen.setdefault(sg, sv)
        tally["duplicate_upload_dates"] += int(any(stream_of[v] != v for v in by_date[d]))
    return keep, stream_of


def load_snapshots(path: str, tally: collections.Counter) -> list:
    recs = []
    with open(path) as fh:
        for line in fh:
            r = json.loads(line)
            tally["frames"] += 1
            if not r.get("panel_found") or r.get("list") not in ("A", "B"):
                tally["frames_no_panel"] += 1
                continue
            recs.append(r)
    tally["frames_panel_found"] = len(recs)
    # the video's date = the mode of its frames' taskbar dates (ties -> the earliest)
    by_vid = collections.defaultdict(list)
    for r in recs:
        by_vid[r["vid"]].append(r)
    tally["videos"] = len(by_vid)
    vdate = {}
    for v, fr in by_vid.items():
        c = collections.Counter(f["screen_date"] for f in fr)
        top = max(c.values())
        vdate[v] = min(d for d, n in c.items() if n == top)
        if len(c) > 1:
            tally["videos_with_mixed_frame_dates"] += 1
    # the video's clock fitted to stream time: offset = the median of (clock read - stream time) over its frames with a clock read
    offset = {}
    for v, fr in by_vid.items():
        offs = [et_seconds(f.get("et_time") or "") - ts_seconds(f["stream_ts"]) for f in fr if et_seconds(f.get("et_time") or "") is not None]
        offset[v] = statistics.median(offs) if offs else None
        if offs:
            tally["frames_clock_misread_over_2min"] += sum(1 for f in fr if et_seconds(f.get("et_time") or "") is not None and abs(
                et_seconds(f["et_time"]) - ts_seconds(f["stream_ts"]) - offset[v]) > 120)
    recs, stream_of = dedupe_uploads(recs, vdate, tally)
    snaps = []
    for r in recs:
        ctx_raw = r.get("clock_ctx") or ""
        ctx = ctx_raw if ctx_raw in CTX_RANK else "in"
        if ctx_raw not in CTX_RANK:
            tally["frames_ctx_unknown_read_as_in"] += 1
        full, how = full_flag(r)
        tally[f"full_{how}"] += 1
        syms = [s for s in r.get("symbols") or [] if s]
        if r.get("list") == "B":
            tally["frames_list_B_2017"] += 1
        st = ts_seconds(r["stream_ts"])
        meta = {row["sym"]: (row.get("pct_check"), row.get("pct_suggest"), row.get("pct")) for row in r.get("rows") or [] if row.get("sym")}
        snaps.append(Snap(idx=-1, frame_id=r["frame_id"], vid=stream_of[r["vid"]], folder=r["folder"], date=vdate[r["vid"]],
                          frame_date=r["screen_date"], ctx=ctx, ctx_raw=ctx_raw, et_time=r.get("et_time") or "",
                          stream_ts=st, resolution=r.get("resolution") or "", list_name=r.get("list"),
                          symbols=syms, visible_n=int(r.get("visible_n") or 0), total_n=r.get("total_n"), full=full, full_how=how,
                          vid_raw=r["vid"], clock_s=float(st + offset[r["vid"]]) if offset[r["vid"]] is not None else float(st),
                          rows_meta=meta, clock_known=offset[r["vid"]] is not None))
    # order (F1): each date's frames by their ET clock ACROSS videos (the fitted clock; within one video it is the stream-time order);
    # a video with no clock read at all keeps its stream time (all such videos are the only video on their date - counted)
    clockless = {v for v in by_vid if offset[v] is None}
    tally["videos_without_any_clock"] = len(clockless)
    vids_on = collections.defaultdict(set)
    for s in snaps:
        vids_on[s.date].add(s.vid)
    tally["clockless_videos_sharing_a_date"] = sum(1 for v in clockless if stream_of[v] == v and len(vids_on[vdate[v]]) > 1)
    snaps.sort(key=lambda s: (s.date, s.clock_s, s.vid, s.stream_ts, s.frame_id))
    for i, s in enumerate(snaps):
        s.idx = i
    # videos whose frames interleave with another video's on the same date after the clock order (not duplicates: 2 different uploads)
    runs = collections.Counter()
    for a, b in zip(snaps, snaps[1:]):
        if a.date == b.date and a.vid != b.vid:
            runs[a.date] += 1
    tally["dates_with_videos_interleaved"] = sum(1 for d, n in runs.items() if n > len(vids_on[d]) - 1)
    tally["snapshots"] = len(snaps)
    tally["streams"] = len({s.vid for s in snaps})
    return snaps


def clock_of(s: Snap) -> str:
    """The frame's ET clock 'HH:MM': its own clock read, else its video's fitted clock, else '' (a video with no clock read)."""
    if et_seconds(s.et_time) is not None:
        return s.et_time[11:16]
    return hhmm(s.clock_s) if s.clock_known else ""


def panel_clocks(e: "Entry", d: dict) -> dict:
    """F3, the panel's clock on the buy day E (outcome-free; read beside the fill minute in the run, never a filter):
      first_clock_on_E  the first sighting's ET clock when that sighting is ON E in session (pre-market sightings reflect E - 1);
      flat_clock_on_E   the clock of the last full snapshot WITHOUT the name when it is on E (pre-market or in session): he was flat then;
      orh5_infeasible   held on E before the first minute an ORH5 fill can exist (09:35 ET)."""
    out = {"first_clock_on_E": "", "flat_clock_on_E": "", "orh5_infeasible": False}
    E = d.get("E") or ""
    if not E or e.initial:
        return out
    f, p = e.first_snap, e.prev_full
    if f.date == E and f.ctx != "pre":
        out["first_clock_on_E"] = clock_of(f)
        out["orh5_infeasible"] = bool(out["first_clock_on_E"]) and out["first_clock_on_E"] < ORH5_FIRST
    if p is not None and p.date == E and p.ctx != "closed":
        out["flat_clock_on_E"] = clock_of(p)
    return out


def asof(s: Snap, S: Sessions) -> int:
    return S.lt(s.date) if s.ctx == "pre" else S.le(s.date)


def lo_after(s: Snap, S: Sessions) -> int:
    """The first session on which a buy / sell could be missing from snapshot s."""
    return S.gt(s.date) if s.ctx == "closed" else S.ge(s.date)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the blip fill (stream level) and the state machine (snapshot level)
# ═════════════════════════════════════════════════════════════════════════════════════════════
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


FLICKER_SESSIONS = 5                 # a one-stream sighting whose exit is confirmed within this many sessions of it
LOOKALIKE_MAX_ROUNDS = 500           # the look-alike guard's fixed-point loop (one snapshot's renames per round)


def one_edit(a: str, b: str) -> bool:
    """True when a and b are exactly one edit apart (one substitution, insertion or deletion): UI / LI, SO / SQ."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def lookalike_pairs(new: list, s: Snap, f: Snap, tally: collections.Counter) -> list:
    """F2, the look-alike guard. A name X first appears in snapshot s; the last full snapshot f holds a symbol Y one edit away from X;
    Y is absent from s; and the reader flagged Y's row in f - its % cell disagrees with Y's own bars that day (`mismatch_kept`) or the
    reader's look-alike search suggested X (`pct_suggest`). Then Y in f was X misread: X was held at f. (The % check uses the frame
    day's own range, never a bar after it.) One X with several such Y: only the one the reader suggested, else ambiguous (no rename).
    One Y claimed by several X: the suggested X, else the X whose % read in s is nearest Y's % read in f (a unique nearest), else
    ambiguous. A symbol already renamed in f is never renamed again. -> [proposal dicts]"""
    relab = {x for _y, x in f.relabeled}
    by_x = collections.defaultdict(list)
    for x in new:
        for y in f.symbols:
            if y == x or y in relab or y in s.held or not one_edit(x, y):
                continue
            chk, sug, _pct = f.rows_meta.get(y, (None, None, None))
            if chk == "mismatch_kept" or sug == x:
                by_x[x].append(y)
    pairs = []
    for x, ys in sorted(by_x.items()):
        if len(ys) > 1:
            ys = [y for y in ys if f.rows_meta[y][1] == x]
            if len(ys) != 1:
                tally["lookalike_ambiguous"] += 1
                continue
        pairs.append((x, ys[0]))
    by_y = collections.defaultdict(list)
    for x, y in pairs:
        by_y[y].append(x)
    out = []
    for y, xs in sorted(by_y.items()):
        _chk, sug, pct_y = f.rows_meta[y]
        how = "suggested" if sug in xs else "mismatch_kept"
        if len(xs) > 1:
            if sug in xs:
                xs = [sug]
            else:
                dist = sorted((abs(float(s.rows_meta[x][2]) - float(pct_y)), x) for x in xs
                              if pct_y is not None and s.rows_meta.get(x, (None, None, None))[2] is not None)
                if len(dist) == len(xs) and dist[0][0] < dist[1][0]:
                    xs, how = [dist[0][1]], "mismatch_kept_nearest_pct"
                else:
                    tally["lookalike_ambiguous"] += 1
                    continue
        out.append({"s_idx": s.idx, "f_idx": f.idx, "read": y, "held": xs[0], "how": how, "s_full": s.full})
    return out


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


def build_timeline(snaps: list, S: Sessions, tally: collections.Counter) -> tuple:
    """(entries, renames): the blip fill and the state machine, with the look-alike guard (F2) run to a fixed point - each round applies
    the renames proposed at the EARLIEST snapshot (Y -> X in that full snapshot f: 'treat Y as X in that snapshot'), then everything is
    recomputed from scratch, so the blips, exits and flickers all see the renamed snapshot."""
    renames = []
    for _round in range(LOOKALIKE_MAX_ROUNDS):
        for x in snaps:
            x.blip_filled = []
        t = collections.Counter()
        blip_fill(snaps, t)
        found = []
        entries = timeline(snaps, S, t, found)
        if not found:
            break
        k = min(p["s_idx"] for p in found)
        for p in found:
            if p["s_idx"] != k:
                continue
            f = snaps[p["f_idx"]]
            f.symbols[f.symbols.index(p["read"])] = p["held"]
            f.rows_meta[p["held"]] = f.rows_meta.pop(p["read"])
            f.relabeled.append((p["read"], p["held"]))
            renames.append(p)
    else:
        raise RuntimeError(f"the look-alike guard did not reach a fixed point in {LOOKALIKE_MAX_ROUNDS} rounds")
    tally.update(t)
    tally["lookalike_renames"] = len(renames)
    for p in renames:
        tally[f"lookalike_renames_{p['how']}"] += 1
        tally["lookalike_renames_s_scrolled"] += int(not p["s_full"])
    return entries, renames


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the symbol join and the events
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_lexicon() -> dict:
    """{ticker: (a_first, a_last, b_first, b_last)} - which bar file carries the symbol and when."""
    out = {}
    with open(FILES["lexicon"]) as fh:
        for ln in fh:
            t, a0, a1, b0, b1 = ln.rstrip("\n").split("\t")
            out[t] = (a0, a1, b0, b1)
    return out


def load_alias(lex: dict, tally: collections.Counter) -> dict:
    """panel (contemporary) symbol -> era-A symbol (today's name), two sources: (1) the reader's overlap-close signature - an era-B symbol
    with NO era-A rows whose closes on the three overlap sessions equal exactly one era-A symbol's (FB -> META); (2) the era-A dedupe map
    (a dropped twin -> its kept twin). The rename map (polygon vs alpaca vendor names) is NOT a time-rename map and is not used."""
    with gzip.open(FILES["calendar_cache"], "rb") as fh:
        _cal, sig = pickle.load(fh)
    sa, sb = collections.defaultdict(dict), collections.defaultdict(dict)
    for (t, d), v in sig[0].items():
        sa[t][d] = round(v[3], 2)
    for (t, d), v in sig[1].items():
        sb[t][d] = round(v[3], 2)
    ia = collections.defaultdict(list)
    for t, m in sa.items():
        if len(m) == len(SIG_DATES):
            ia[tuple(m[d] for d in SIG_DATES)].append(t)
    alias = {}
    for t, m in sb.items():
        if lex.get(t, ("",))[0]:                      # has era-A rows under its own name: no alias needed
            continue
        if len(m) == len(SIG_DATES):
            hit = ia.get(tuple(m[d] for d in SIG_DATES), [])
            if len(hit) == 1 and hit[0] != t:
                alias[t] = hit[0]
    tally["alias_signature"] = len(alias)
    dd = pd.read_csv(FILES["dedupe_A"], sep="\t", dtype=str, keep_default_na=False)
    n = 0
    for a, b in zip(dd["dropped_symbol"], dd["kept_symbol"]):
        if a and b and a != b and a not in alias and not lex.get(a, ("",))[0]:
            alias[a] = b
            n += 1
    tally["alias_dedupe"] = n
    return alias


def load_breakouts(tally: collections.Counter) -> dict:
    """{(era, ticker): sorted [(E, row dict)]} of the tl streams: era A for E <= ERA_A_LAST_E, era B (discovery, <= CUT_B) for
    E >= ERA_B_FIRST_E. Only pre-E columns are read."""
    cols = ["ticker", "D", "E", "K", "base_id", "retrigger", "pivot", "adr20", "split"]
    a = pd.read_csv(FILES["cand_A"], sep="\t", dtype=str, keep_default_na=False, usecols=cols)
    tally["cand_A_rows"] = len(a)
    a = a[a["K"] == "tl"]
    tally["cand_A_tl"] = len(a)
    a = a[a["E"] <= ERA_A_LAST_E]
    b = pd.read_csv(FILES["cand_B"], sep="\t", dtype=str, keep_default_na=False, usecols=cols)
    tally["cand_B_rows"] = len(b)
    b = b[b["K"] == "tl"]
    tally["cand_B_tl"] = len(b)
    after = b[(b["E"] > CUT_B) | (b["D"] > CUT_B)]
    tally["cand_B_tl_after_cut_dropped"] = len(after)
    b = b[(b["E"] <= CUT_B) & (b["D"] <= CUT_B)]
    assert b["E"].max() <= CUT_B
    nd = b[b["split"] != "discovery"]
    tally["cand_B_tl_not_discovery_dropped"] = len(nd)
    b = b[(b["split"] == "discovery") & (b["E"] >= ERA_B_FIRST_E)]
    out = collections.defaultdict(list)
    for era, df in (("A", a), ("B", b)):
        for r in df.to_dict("records"):
            out[(era, r["ticker"])].append((r["E"], r))
        tally[f"breakout_events_{era}"] = len(df)
    for k in out:
        out[k].sort(key=lambda x: x[0])
    return out


def load_eps(tally: collections.Counter) -> dict:
    """{(era, ticker): sorted [(E, row)]} of the primary EP gap days (gap-day facts only: E, D, the prior close, the gap)."""
    cols = ["ticker", "E", "D", "prev_close_adj", "gap_pct", "primary", "era"]
    out = collections.defaultdict(list)
    for era, key, lo, hi in (("A", "ep_A", "0000-00-00", ERA_A_LAST_E), ("B", "ep_B", ERA_B_FIRST_E, CUT_B)):
        t = pd.read_csv(FILES[key], sep="\t", dtype=str, keep_default_na=False, usecols=cols)
        tally[f"ep_{era}_rows"] = len(t)
        t = t[(t["primary"] == "True") & (t["E"] >= lo) & (t["E"] <= hi)]
        tally[f"ep_{era}_primary_in_span"] = len(t)
        for r in t.to_dict("records"):
            out[(era, r["ticker"])].append((r["E"], r))
    for k in out:
        out[k].sort(key=lambda x: x[0])
    return out


def events_in(sym: str, sym_a: str, lo_d: str, hi_d: str, BK: dict, EP: dict) -> list:
    """[(E, kind, era, row)] of the name's events inside [lo_d, hi_d]: era A under the era-A name, era B under the panel's own."""
    out = []
    for era, name in (("A", sym_a), ("B", sym)):
        for src, kind in ((BK, "breakout"), (EP, "EP")):
            for E, row in src.get((era, name), ()):
                if lo_d <= E <= hi_d:
                    out.append((E, kind, era, row))
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def date_entry(e: Entry, S: Sessions, alias: dict, lex: dict, cand_names: set, BK: dict, EP: dict) -> dict:
    """The dating of one entry (the rule in the docstring). Returns the fields written to entries.tsv."""
    sym = e.sym
    sym_a = sym if lex.get(sym, ("",))[0] else alias.get(sym, sym)
    has_bars = bool(lex.get(sym, ("",))[0] or lex.get(sym, ("", "", ""))[2] or (sym_a != sym and lex.get(sym_a, ("",))[0]))
    is_cand = (sym_a in cand_names) or (sym in cand_names)
    d = {"sym": sym, "sym_a": sym_a, "has_bars": has_bars, "ever_candidate": is_cand, "setup": "", "E": "", "D": "", "era": "",
         "pivot": "", "adr20": "", "base_id": "", "retrigger": "", "ep_prev_close": "", "ep_gap_pct": "", "n_events_in_window": 0,
         "E_earliest": "", "kind_earliest": "", "q1_2022_hole": False, "undated_reason": ""}
    if e.initial:
        d["setup"] = "initial"
        d["undated_reason"] = "initial"
        return d
    lo_d, hi_d = S.date(e.lo), S.date(e.hi)
    d["q1_2022_hole"] = not (hi_d < "2022-01-04" or lo_d > ERA_A_LAST_E)
    evs = events_in(sym, sym_a, lo_d, hi_d, BK, EP)
    d["n_events_in_window"] = len(evs)
    if not evs:
        d["setup"] = "undated"
        d["era"] = "A" if lo_d <= ERA_A_LAST_E else "B"
        d["undated_reason"] = "no_bars" if not has_bars else ("never_candidate" if not is_cand else "no_event_in_window")
        return d
    E_last = evs[-1][0]
    kinds = {k for E, k, _era, _r in evs if E == E_last}
    chosen = [x for x in evs if x[0] == E_last]
    bk = next((x for x in chosen if x[1] == "breakout"), None)
    ep = next((x for x in chosen if x[1] == "EP"), None)
    d["setup"] = "both" if (bk and ep) else ("breakout" if bk else "EP")
    d["E"] = E_last
    d["E_earliest"], d["kind_earliest"] = evs[0][0], evs[0][1]
    src = bk or ep
    d["era"] = src[2]
    if bk:
        r = bk[3]
        d.update(D=r["D"], pivot=r["pivot"], adr20=r["adr20"], base_id=r["base_id"], retrigger=r["retrigger"])
    if ep:
        r = ep[3]
        d["ep_prev_close"], d["ep_gap_pct"] = r["prev_close_adj"], r["gap_pct"]
        if not bk:
            d["D"] = r["D"]
    return d


# ═════════════════════════════════════════════════════════════════════════════════════════════
# his 236 calls (the frozen classes) and the positive control
# ═════════════════════════════════════════════════════════════════════════════════════════════
def his_calls() -> list:
    """[(ticker, E, strict)] - the Track A positive events of era A, derived by the frozen fit module (as the first replay does)."""
    ls = rp.label_sets_from_files()
    candA, _ = rp.read_tsv(rp.FILES["cand_A"], rp.CAND_COLS, keep=rp.cand_keep_A)
    ns = rp.era_stream("A", candA, ls)
    out = []
    for i in range(len(ns.E)):
        if ns.cls["pos"][i]:
            out.append((str(ns.ticker[i]), str(ns.E[i]), bool(ns.cls["strict"][i])))
    assert len(out) == 236, len(out)
    return sorted(out, key=lambda x: (x[1], x[0]))


def control_rows(calls: list, entries: list, dated: list, snaps: list, S: Sessions, alias: dict, lex: dict) -> list:
    snap_sess = sorted({asof(s, S) for s in snaps})
    seen_at = collections.defaultdict(set)              # era-A name -> set of sessions (asof) with a sighting
    for s in snaps:
        a = asof(s, S)
        for name in s.held:
            na = name if lex.get(name, ("",))[0] else alias.get(name, name)
            seen_at[na].add(a)
            seen_at[name].add(a)
    by_name = collections.defaultdict(list)
    for e, d in zip(entries, dated):
        by_name[d["sym_a"]].append((e, d))
        if d["sym"] != d["sym_a"]:
            by_name[d["sym"]].append((e, d))
    rows = []
    for tk, E, strict in calls:
        eI = S.ge(E)
        assert S.date(eI) == E, E
        cands = {id(e): (e, d) for e, d in by_name.get(tk, []) if not e.initial and e.lo <= eI <= e.hi}
        cands = list(cands.values())
        k = bisect.bisect_left(snap_sess, eI)
        nearest = snap_sess[k] - eI if k < len(snap_sess) else None
        seen = any(eI <= a <= eI + CONTROL_LOOKAHEAD for a in seen_at.get(tk, ()))
        held_before = any(eI - CONTROL_LOOKAHEAD <= a < eI for a in seen_at.get(tk, ()))
        # the panel entry OPEN at E (bought before E, not yet sold at E), if any
        open_at = [(e, d) for e, d in by_name.get(tk, []) if e.hi < eI and (e.exit_hi is None or e.exit_hi >= eI)]
        row = {"ticker": tk, "E": E, "strict": strict, "ever_in_panel": tk in seen_at, "seen_E_to_E20": seen, "held_before_E": held_before,
               "open_entry_at_E": len(open_at) > 0, "open_entry_hi": S.date(open_at[-1][0].hi) if open_at else "",
               "open_entry_setup": open_at[-1][1]["setup"] if open_at else "",
               "nearest_snapshot_after_E_sessions": nearest, "n_entries_window_holds_E": len(cands),
               "dated_on_E": False, "dated_on_E_earliest": False, "decides": False, "dated_minus_E": "", "window_len": "",
               "setup": "", "flicker": False}
        if cands:
            e, d = min(cands, key=lambda x: x[0].window_len)
            row.update(window_len=e.window_len, setup=d["setup"], flicker=e.flicker)
            if d["E"]:
                row["dated_on_E"] = d["E"] == E
                row["dated_minus_E"] = S.ge(d["E"]) - eI
                row["decides"] = d["setup"] in ("breakout", "EP", "both") and e.window_len <= WINDOW_CAP
            row["dated_on_E_earliest"] = d["E_earliest"] == E
        row["class"] = ("dated_on_E" if row["dated_on_E"] else "window_holds_E_dated_elsewhere" if cands else
                        "open_entry_before_E" if open_at else "held_before_E_no_entry" if held_before else
                        "seen_after_E_only" if seen else "in_panel_elsewhere" if tk in seen_at else "never_in_panel")
        rows.append(row)
    return rows


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the report
# ═════════════════════════════════════════════════════════════════════════════════════════════
def say_window(say, win: list, S: Sessions) -> None:
    """The deciding window's entries, outcome-free: when the panel first shows each buy (survival conditioning), same-day exits, the
    panel clocks on E (F3) and repeated (name, E) pairs (F4)."""
    n = len(win)
    on_e, after_close, later = 0, 0, 0
    for e, d in win:
        eI = S.ge(d["E"])
        if e.first_snap.date == d["E"] and e.first_snap.ctx != "pre":
            on_e += 1
        elif asof(e.first_snap, S) == eI:
            after_close += 1
        else:
            later += 1
    say(f"    first sighting of the {n}: in session on E {on_e}, after E's close (closed on E or pre-market the next session) {after_close}, a "
        f"session or more after E {later} - only buys still held at a snapshot are seen (survival conditioning)")
    gone_e = [(e, d) for e, d in win if e.exit_hi is not None and S.date(e.exit_hi) == d["E"]]
    say(f"    leave the panel by E's close (exit window ends on E): {len(gone_e)} of {n} (EP-dated {sum(1 for _e, d in gone_e if d['setup'] == 'EP')} "
        f"of {sum(1 for _e, d in win if d['setup'] == 'EP')})")
    pc = [(e, d, panel_clocks(e, d)) for e, d in win]
    inf = [(e, d, c) for e, d, c in pc if c["orh5_infeasible"]]
    say(f"    F3 held on E before {ORH5_FIRST} ET (no ORH5 fill can precede it): {len(inf)} - "
        + ", ".join(f"{d['sym']} {d['E']} {c['first_clock_on_E']}" for _e, d, c in inf))
    flat = [c["flat_clock_on_E"] for _e, _d, c in pc if c["flat_clock_on_E"]]
    say(f"    F3 flat at a full snapshot on E: {len(flat)} (in session {sum(1 for x in flat if x >= '09:30')}, at >= 10:00 "
        f"{sum(1 for x in flat if x >= '10:00')}, at >= 10:30 {sum(1 for x in flat if x >= '10:30')}); first seen in session on E "
        f"{sum(1 for _e, _d, c in pc if c['first_clock_on_E'])}; bracketed on both sides within E "
        f"{sum(1 for _e, _d, c in pc if c['first_clock_on_E'] and c['flat_clock_on_E'] >= '09:30')}")
    seen, rep = {}, []
    for e, d in win:
        k = (d["era"], d["sym_a"] if d["era"] == "A" else d["sym"], d["E"])
        if k in seen:
            rep.append((seen[k], e, d))
        else:
            seen[k] = e
    say(f"    a name's later entry dated to the SAME E as its earlier one (the replay classifies it `same_day_rebuy`, F4): {len(rep)} - "
        + ", ".join(f"{d['sym']} {d['E']} (#{e0.eid} then #{e.eid}, flat at {panel_clocks(e, d)['flat_clock_on_E'] or '-'})" for e0, e, d in rep))


def table(say, hdr: list, rows: list) -> None:
    w = [max(len(str(x)) for x in col) for col in zip(hdr, *rows)]
    say("  " + " | ".join(str(h).ljust(n) for h, n in zip(hdr, w)))
    say("  " + "-+-".join("-" * n for n in w))
    for r in rows:
        say("  " + " | ".join(str(x).ljust(n) for x, n in zip(r, w)))


def pct(a, b) -> str:
    return f"{a} ({100.0 * a / b:.0f}%)" if b else f"{a}"


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.parse_args(argv)
    os.makedirs(OUT_DIR, exist_ok=True)
    say = Say()
    tally = collections.Counter()
    say("# #705 HOLDINGS 01 — his positions panel -> holdings timeline -> buy dating -> positive control (OUTCOME-FREE: no bar after a "
        "buy day, no minute file, no replay outcome file)")
    say("# registration: docs/analysis/cb_holdings_replay_prereg_2026-10-24.md")
    say(f"# rules: window cap {WINDOW_CAP} sessions decides; the LATEST event in the window dates the buy; full = footer, else the list ends "
        f">= {FULL_GAP_PITCHES} row pitches above the panel bottom; an exit needs two consecutive full snapshots without the name; blips "
        f"(one-stream absences) filled; flickers (one-stream sightings, exit within {FLICKER_SESSIONS} sessions) flagged, dated ones decide")
    S = load_sessions()
    snaps = load_snapshots(FILES["panel"], tally)
    entries, renames = build_timeline(snaps, S, tally)
    lex = load_lexicon()
    alias = load_alias(lex, tally)
    BK = load_breakouts(tally)
    EP = load_eps(tally)
    cand_names = {t for _e, t in BK} | {t for _e, t in EP}
    dated = [date_entry(e, S, alias, lex, cand_names, BK, EP) for e in entries]
    calls = his_calls()
    ctl = control_rows(calls, entries, dated, snaps, S, alias, lex)

    # ---- frames and snapshots
    say("\n## Frames -> snapshots")
    say(f"- frames {tally['frames']:,}: panel found (list A or the 2017 B list) {tally['frames_panel_found']:,} in {tally['videos']} videos; no panel "
        f"{tally['frames_no_panel']:,}")
    say(f"- duplicate uploads (F1): {tally['duplicate_upload_videos']} videos on {tally['duplicate_upload_dates']} dates repeat another video's frames "
        f"(same clock read, stream time, list, rows read, footer); {tally['duplicate_frames_dropped']} frames dropped, "
        f"{tally['duplicate_leftover_frames_joined']} leftover frames joined to the kept copy's stream -> {tally['snapshots']:,} snapshots in "
        f"{tally['streams']} streams; 2017 'B - Positions' frames {tally['frames_list_B_2017']}")
    say(f"- order (F1): each date's frames by ET clock across videos = the video's clock fitted to stream time (median of clock read - stream "
        f"time; {tally['frames_clock_misread_over_2min']} clock reads off the fit by > 2 min, all treated as misreads); videos with no clock "
        f"read {tally['videos_without_any_clock']} (sharing a date with another video: {tally['clockless_videos_sharing_a_date']}); dates whose "
        f"videos interleave after the clock order {tally['dates_with_videos_interleaved']}")
    say(f"- full flag: footer equals rows {tally['full_footer_eq']:,} | footer above rows (scrolled) {tally['full_footer_scrolled']:,} | "
        f"geometry full {tally['full_geom_full']} | geometry reaches the bottom {tally['full_geom_reaches_bottom']} | no rows and no footer "
        f"{tally['full_no_rows_no_footer']}")
    say(f"- clock context unknown, read as in-session (widest window) {tally['frames_ctx_unknown_read_as_in']}; videos whose frames carry "
        f"two taskbar dates (the mode taken) {tally['videos_with_mixed_frame_dates']}")
    say(f"- blips filled (a name absent from one full stream, present either side) {tally['blips_filled']} (of which over a footer-consistent "
        f"absence - footer total = rows read, the name not among them - {tally['blips_over_footer_consistent_absence']}); single-frame drops cancelled "
        f"(a name absent from one full snapshot, seen again before the next full one) {tally['single_frame_drops_cancelled']}; pending "
        f"exits at the end (absent from the last full snapshot only) {tally['pending_exits_at_end']}")
    say(f"- look-alike guard (F2): {tally['lookalike_renames']} renames (the reader suggested the held name "
        f"{tally['lookalike_renames_suggested']}, % cell mismatch {tally['lookalike_renames_mismatch_kept']}, % mismatch with two candidates "
        f"settled by the nearest % read {tally['lookalike_renames_mismatch_kept_nearest_pct']}; the first sighting s scrolled "
        f"{tally['lookalike_renames_s_scrolled']}); ambiguous, not renamed {tally['lookalike_ambiguous']}")
    for p in renames:
        f, s2 = snaps[p["f_idx"]], snaps[p["s_idx"]]
        say(f"    {f.date} {f.frame_id} {clock_of(f)} ({f.ctx}) read {p['read']} -> held {p['held']} [{p['how']}]; {p['held']} first read in "
            f"{s2.frame_id} {clock_of(s2)} ({s2.ctx}, {'full' if s2.full else 'scrolled'})")
    full_n = sum(1 for s in snaps if s.full)
    say(f"- full snapshots {full_n:,} of {len(snaps):,}; streams with >= 1 full snapshot {len({s.vid for s in snaps if s.full})} of {tally['streams']}")
    by_res = collections.defaultdict(set)
    for s in snaps:
        by_res[s.date].add(s.resolution)
    only_hd = sorted(d for d, r in by_res.items() if r == {"1920x1080"} and d >= "2020-01-01")
    last_720 = max((d for d, r in by_res.items() if "1280x720" in r), default="-")
    say(f"- resolution: last 1280x720 stream date {last_720}; first all-1920x1080 stream date in 2020 {only_hd[0] if only_hd else '-'} "
        f"(the deciding window's start candidate; its end = the last stream before the first >30-day gap after 2022-01-01)")

    # ---- per year
    say("\n## The timeline by year (stream date year)")
    years = sorted({s.date[:4] for s in snaps})
    rows = []
    by_year_entries = collections.defaultdict(list)
    for e, d in zip(entries, dated):
        by_year_entries[e.first_snap.date[:4]].append((e, d))
    for y in years:
        ss = [s for s in snaps if s.date[:4] == y]
        vids = {s.vid for s in ss}
        dates = sorted({s.date for s in ss})
        gaps = [(pd.Timestamp(b) - pd.Timestamp(a)).days for a, b in zip(dates, dates[1:])]
        names = set().union(*(s.held for s in ss)) if ss else set()
        ents = by_year_entries.get(y, [])
        n_ent = sum(1 for e, _d in ents if not e.initial)
        n_init = sum(1 for e, _d in ents if e.initial)
        n_flick = sum(1 for e, _d in ents if e.flicker)
        exits_y = sum(1 for e in entries if e.exit_snap is not None and e.exit_snap.date[:4] == y)
        rows.append([y, len(vids), len(dates), len(ss), sum(1 for s in ss if s.full), len(names), n_ent, n_init, n_flick, exits_y,
                     f"{statistics.median(gaps):.0f}" if gaps else "-", f"{max(gaps)}" if gaps else "-"])
    table(say, ["year", "streams", "stream dates", "snapshots", "full", "distinct holdings", "entries", "initial", "flickers", "exits",
                "median days between streams", "max gap"], rows)
    say(f"- totals: entries {tally['entries']} (initial {tally['entries_initial']}, flickers {tally['entries_flicker']}, inverted windows "
        f"{tally['entries_inverted_window']}), exits {tally['exits']} (inverted {tally['exits_inverted_window']}), still held at the last "
        f"snapshot {tally['still_held_at_end']}")

    # ---- windows
    say("\n## Entry windows (sessions; non-initial entries)")
    wl = [e.window_len for e in entries if not e.initial]
    bins = [(1, 1), (2, 2), (3, 5), (6, 10), (11, 20), (21, 60), (61, 10 ** 6)]
    say("- " + "; ".join(f"{a}{'' if a == b else ('-' + str(b) if b < 10 ** 6 else '+')}: {sum(1 for w in wl if a <= w <= b)}" for a, b in bins)
        + f" | median {statistics.median(wl) if wl else '-'}")
    say(f"- within the cap ({WINDOW_CAP} sessions): {sum(1 for w in wl if w <= WINDOW_CAP)} of {len(wl)}")

    # ---- symbol join census
    say("\n## Symbol join (distinct panel names)")
    names_all = sorted(set().union(*(set(s.symbols) for s in snaps)))
    cen = collections.Counter()
    for n in names_all:
        na = n if lex.get(n, ("",))[0] else alias.get(n, n)
        if n in cand_names or na in cand_names:
            cen["candidate_direct" if n in cand_names else "candidate_via_alias"] += 1
        elif lex.get(n, ("",))[0] or lex.get(n, ("", "", ""))[2] or (na != n and lex.get(na, ("",))[0]):
            cen["bars_never_candidate"] += 1
        else:
            cen["no_bars"] += 1
    say(f"- {len(names_all)} names: in a candidate stream directly {cen['candidate_direct']}, via alias {cen['candidate_via_alias']} "
        f"(aliases: signature {tally['alias_signature']}, dedupe {tally['alias_dedupe']}), bars but never a candidate (ETFs, leveraged, "
        f"thin) {cen['bars_never_candidate']}, no bars at all {cen['no_bars']}")
    nb = sorted({d["sym"] for d in dated if d["setup"] == "undated" and d["undated_reason"] == "no_bars"})
    nc = sorted({d["sym"] for d in dated if d["setup"] == "undated" and d["undated_reason"] == "never_candidate"})
    say(f"- undated for no bars ({len(nb)} names): {', '.join(nb[:40])}{' ...' if len(nb) > 40 else ''}")
    say(f"- undated as never a candidate ({len(nc)} names): {', '.join(nc[:40])}{' ...' if len(nc) > 40 else ''}")
    say(f"- streams: era A tl {tally['breakout_events_A']:,} events (of {tally['cand_A_tl']:,} tl rows), era B tl discovery "
        f"{tally['breakout_events_B']:,} (not discovery dropped {tally['cand_B_tl_not_discovery_dropped']:,}; after {CUT_B} dropped "
        f"{tally['cand_B_tl_after_cut_dropped']:,}); EP primary era A {tally['ep_A_primary_in_span']:,}, era B {tally['ep_B_primary_in_span']:,}")

    # ---- dating split
    say("\n## Buy dating (non-initial entries; the latest event in the window)")
    rows = []
    setups = ("breakout", "EP", "both", "undated")
    for y in years + ["all"]:
        sel = [(e, d) for e, d in zip(entries, dated) if not e.initial and (y == "all" or e.first_snap.date[:4] == y)]
        r = [y, len(sel)]
        for st in setups:
            r.append(sum(1 for _e, d in sel if d["setup"] == st))
        r.append(sum(1 for e, d in sel if d["setup"] in ("breakout", "EP", "both") and e.window_len <= WINDOW_CAP))
        r.append(sum(1 for e, d in sel if d["setup"] in ("breakout", "EP", "both") and e.window_len <= WINDOW_CAP and e.flicker))
        r.append(sum(1 for e, d in sel if d["setup"] in ("breakout", "EP", "both") and (e.window_len > WINDOW_CAP)))
        r.append(sum(1 for _e, d in sel if d["undated_reason"] == "no_bars"))
        r.append(sum(1 for _e, d in sel if d["undated_reason"] == "never_candidate"))
        r.append(sum(1 for _e, d in sel if d["undated_reason"] == "no_event_in_window"))
        r.append(sum(1 for _e, d in sel if d["q1_2022_hole"]))
        rows.append(r)
    table(say, ["year", "entries", "breakout", "EP", "both", "undated", "DECIDES (dated, window <= cap)", "of which flickers",
                "dated, wider than cap", "undated: no bars", "undated: never candidate", "undated: no event", "window touches Q1-2022 hole"], rows)
    n_dated = sum(1 for e, d in zip(entries, dated) if d["setup"] in ("breakout", "EP", "both"))
    n_multi = sum(1 for d in dated if d["n_events_in_window"] > 1)
    n_diff = sum(1 for d in dated if d["n_events_in_window"] > 1 and d["E_earliest"] != d["E"])
    say(f"- dated entries {n_dated}; windows holding more than one event {n_multi}, where the earliest event differs from the latest {n_diff}")
    decides = [(e, d) for e, d in zip(entries, dated) if d["setup"] in ("breakout", "EP", "both") and e.window_len <= WINDOW_CAP]
    say(f"- DECIDING population: {len(decides)} entries, {len({d['sym'] for _e, d in decides})} names, "
        f"{len({d['E'] for _e, d in decides})} buy days, by era A {sum(1 for _e, d in decides if d['era'] == 'A')} / B "
        f"{sum(1 for _e, d in decides if d['era'] == 'B')}; retriggers among the breakout-dated "
        f"{sum(1 for _e, d in decides if d['setup'] != 'EP' and d['retrigger'] == '1')}; flickers {sum(1 for e, _d in decides if e.flicker)}; "
        f"by setup " + ", ".join(f"{k} {v}" for k, v in sorted(collections.Counter(d['setup'] for _e, d in decides).items())))
    win = [(e, d) for e, d in decides if DECIDING_WINDOW[0] <= d["E"] <= DECIDING_WINDOW[1]]
    say(f"- in the deciding window {DECIDING_WINDOW[0]}..{DECIDING_WINDOW[1]}: {len(win)} deciding entries, by setup "
        + ", ".join(f"{k} {v}" for k, v in sorted(collections.Counter(d['setup'] for _e, d in win).items()))
        + f"; {len({d['sym'] for _e, d in win})} panel names, {len({d['E'] for _e, d in win})} buy days")
    if win:
        say_window(say, win, S)
    say(f"- deciding entries by first-sighting resolution: " + ", ".join(f"{k} {v}" for k, v in sorted(collections.Counter(e.first_snap.resolution for e, _d in decides).items()))
        + "; by year: " + ", ".join(f"{k} {v}" for k, v in sorted(collections.Counter(e.first_snap.date[:4] for e, _d in decides).items())))
    say(f"- exits of the deciding entries: panel exit seen {sum(1 for e, _d in decides if e.exit_snap is not None)}, still held at the last "
        f"snapshot {sum(1 for e, _d in decides if e.exit_snap is None)}; exit window median "
        f"{statistics.median([e.exit_hi - e.exit_lo + 1 for e, _d in decides if e.exit_snap is not None]) if any(e.exit_snap for e, _d in decides) else '-'} sessions")
    # the account's deciding start: the first session after every initial holding has left the panel
    inits = [e for e in entries if e.initial]
    if inits:
        last_init_exit = max((e.exit_hi for e in inits if e.exit_snap is not None), default=None)
        open_init = [e.sym for e in inits if e.exit_snap is None]
        say(f"- initial holdings {len(inits)}: the last one leaves the panel on {S.date(last_init_exit) if last_init_exit is not None else '-'}"
            f"; never seen to leave {len(open_init)} ({', '.join(open_init[:12])}{' ...' if len(open_init) > 12 else ''})")
    # coverage by year of the first-full-snapshot era (for the deciding window): first and last snapshot dates
    say(f"- snapshot span {snaps[0].date} .. {snaps[-1].date}; first full snapshot {next(s.date for s in snaps if s.full)}; stream-date gaps "
        f"over 30 days: " + ", ".join(f"{a}->{b}" for a, b in zip(sorted({s.date for s in snaps}), sorted({s.date for s in snaps})[1:])
                                    if (pd.Timestamp(b) - pd.Timestamp(a)).days > 30))

    # ---- positive control
    say(f"\n## Positive control: his 236 stream calls (labels on or before E; strict = said strictly before E)")
    n = len(ctl)
    for lab, sel in (("all 236", ctl), ("strictly-before 127", [r for r in ctl if r["strict"]])):
        m = len(sel)
        say(f"- {lab}: ever in the panel {pct(sum(r['ever_in_panel'] for r in sel), m)}; seen in E..E+{CONTROL_LOOKAHEAD} "
            f"{pct(sum(r['seen_E_to_E20'] for r in sel), m)}; a panel entry whose window holds E {pct(sum(r['n_entries_window_holds_E'] > 0 for r in sel), m)}; "
            f"DATED ON E by the rule {pct(sum(r['dated_on_E'] for r in sel), m)} (earliest rule {sum(r['dated_on_E_earliest'] for r in sel)}); "
            f"deciding {pct(sum(r['decides'] for r in sel), m)}")
    near = [r["nearest_snapshot_after_E_sessions"] for r in ctl if r["nearest_snapshot_after_E_sessions"] is not None]
    say(f"- nearest snapshot at or after E: same session {sum(1 for x in near if x == 0)}, 1 session {sum(1 for x in near if x == 1)}, 2-5 "
        f"{sum(1 for x in near if 2 <= x <= 5)}, 6-20 {sum(1 for x in near if 6 <= x <= 20)}, over 20 {sum(1 for x in near if x > 20)}, none {n - len(near)}")
    dm = collections.Counter(r["dated_minus_E"] for r in ctl if r["dated_minus_E"] != "")
    say(f"- dated day minus E (sessions) for calls whose window holds E and is dated: " + ", ".join(f"{k:+d}: {v}" for k, v in sorted(dm.items())))
    st = collections.Counter((r["setup"] or "no entry") for r in ctl)
    say(f"- the holding entry's setup for those calls: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())))
    say("- every call classified (one class each): " + ", ".join(f"{k} {v}" for k, v in sorted(collections.Counter(r["class"] for r in ctl).items(), key=lambda x: -x[1])))
    opn = [r for r in ctl if r["class"] == "open_entry_before_E"]
    say(f"- calls where the panel already held the name at E ({len(opn)}): the open entry's setup " + ", ".join(f"{k} {v}" for k, v in sorted(collections.Counter(r['open_entry_setup'] for r in opn).items()))
        + f"; its window ended 1-5 sessions before E {sum(1 for r in opn if 1 <= S.ge(r['E']) - S.le(r['open_entry_hi']) <= 5)}, 6-20 "
        f"{sum(1 for r in opn if 6 <= S.ge(r['E']) - S.le(r['open_entry_hi']) <= 20)}, over 20 {sum(1 for r in opn if S.ge(r['E']) - S.le(r['open_entry_hi']) > 20)}")

    # ---- outputs
    snap_rows = [{"idx": s.idx, "frame_id": s.frame_id, "vid": s.vid, "folder": s.folder, "date": s.date, "frame_date": s.frame_date,
                  "ctx": s.ctx, "ctx_raw": s.ctx_raw, "et_time": s.et_time, "stream_ts": s.stream_ts, "resolution": s.resolution,
                  "list": s.list_name, "full": s.full, "full_how": s.full_how, "asof": S.date(asof(s, S)), "visible_n": s.visible_n,
                  "total_n": s.total_n, "symbols": ",".join(s.symbols), "blip_filled": ",".join(s.blip_filled), "vid_raw": s.vid_raw,
                  "clock": clock_of(s), "relabeled": ",".join(f"{y}>{x}" for y, x in s.relabeled)} for s in snaps]
    pd.DataFrame(snap_rows).to_csv(OUT["snapshots"], sep="\t", index=False)
    ent_rows = []
    for e, d in zip(entries, dated):
        ent_rows.append({"eid": e.eid, **d, **panel_clocks(e, d), "first_frame": e.first_snap.frame_id, "first_vid": e.first_snap.vid,
                         "first_date": e.first_snap.date, "first_ctx": e.first_snap.ctx,
                         "prev_full_frame": e.prev_full.frame_id if e.prev_full else "", "prev_full_date": e.prev_full.date if e.prev_full else "",
                         "lo": S.date(e.lo) if e.lo >= 0 else "", "hi": S.date(e.hi), "window_len": e.window_len if not e.initial else "",
                         "inverted": e.inverted, "initial": e.initial, "flicker": e.flicker, "n_sightings": len(e.sightings),
                         "n_streams": len(e.streams), "exit_lo": S.date(e.exit_lo) if e.exit_lo is not None else "",
                         "exit_hi": S.date(e.exit_hi) if e.exit_hi is not None else "", "exit_frame": e.exit_snap.frame_id if e.exit_snap else "",
                         "still_held": e.exit_snap is None, "first_resolution": e.first_snap.resolution,
                         "decides": d["setup"] in ("breakout", "EP", "both") and not e.initial and e.window_len <= WINDOW_CAP})
    pd.DataFrame(ent_rows).to_csv(OUT["entries"], sep="\t", index=False)
    pd.DataFrame([r for r in ent_rows if r["exit_frame"]])[["eid", "sym", "sym_a", "exit_lo", "exit_hi", "exit_frame", "flicker", "initial"]].to_csv(OUT["exits"], sep="\t", index=False)
    pd.DataFrame(ctl).to_csv(OUT["control"], sep="\t", index=False)
    say("\n## Outputs")
    for k, p in OUT.items():
        say(f"- {k}: {p} ({sum(1 for _ in open(p)) - 1:,} rows)")
    say("\n## Pins (sha256) — inputs, then outputs; the replay pins them again")
    for k, p in {**FILES, **OUT}.items():
        say(f"- {k}: {sha(p)}  {p}")
    say(f"- timeline_module: {sha(os.path.abspath(__file__))}  {os.path.abspath(__file__)}")
    say.write(PRINTOUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
