#!/usr/bin/env python3
"""#705 as-is read, STEP 5: every plausible entry and exit, read off the chart (docs/analysis/cb_asis_reconstruction_prereg_2026-10-26.md §3).
RULE-FREE BY CONSTRUCTION: no rule, setup name, pattern label or rule-library level enters; candidate points are described in raw chart
terms only; nothing is imported from the four rule folders (asis_common holds byte-identical copies of the rule-free helpers).

THE OPERATOR'S PRINCIPLE (2026-10-26): "stop trying to pigeon hole his trades, we're starting without any preconceptions, I want to reverse
eng his trades as they are, not as we want them to be and fit into our rules, that reconciliation comes later."

WHAT IT DOES (per position, per side — buy and sale):
  windows      the rule-free columns of entries.tsv / exits.tsv / snapshots.tsv (§3.1; the rule-derived columns are excluded BY NAME at
               read: `usecols` lists the rule-free ones). The sale window's last-sighting frame and its inversion are recomputed from
               snapshots.tsv (asserted equal to exits.tsv on all 1,861).
  bracket      the earlier frame -> the later frame (buy: the last full frame without the name -> the first frame with it; sale: the last
               sighting -> the first full frame without it), typed as §3.2's eight rows.
  reachable    the minutes the trade could physically have happened in (§3.2 layer A): the sessions `lo..hi`; on the earlier frame's own
               session, from its clock when that frame is in-session; on the later frame's own session, to its clock when in-session;
               `pre_market_possible` when the earlier frame is pre-market, `extended_hours_possible` when the later frame is pre-market
               (the trade may have happened in the night or the next pre-market). The `other` clock pairs: the full sessions, flagged
               `bracket_other`. 6+ sessions apart: daily resolution only (`wide_window`). Inverted: none.
  range        the lowest low to the highest high over the reachable minutes (minute bars) or over the reachable sessions' daily bars
               (`daily_only`); beside it the range with the panel's own price (the `% change` cell at the frame, against the prior close).
  candidates   §3.3's families F1-F8, F10, F11, both directions, with §3.4's raw chart features; `our_length` flags the lengths our old
               rules used. F9 (the band ends) is not a candidate row (the plan marks it '—' on both sides): it is `range_lo` / `range_hi`
               of ranges.tsv (R33).
  raw price    the bars are split-adjusted to 2026 (asis_common R12); every record carries the RAW factor of each session, and the raw
               columns (`price_raw`, `range_lo_raw`, ...) are added beside the bar-space ones; F10 and `dist_round` read raw price.
  density      §3.3: per family set, the median share of a side's reachable range covered by the candidates' tolerance (§4.2: max(1% of
               price, 10% of that session's range, $0.05), read in RAW price), F9 excluded by construction; above 60% "where he acts"
               is NOT DECIDABLE for that set.

STAGES  --dry-run   loads everything, asserts the populations against the inventory (data.md), prints coverage by year and bracket type,
                    the density check and the candidate counts per trade -> 01_points_dryrun.txt, ending 'DRY RUN COMPLETE' with a RESULT
                    line '<n> claims, <k> OK, <j> MISMATCH' before it. Writes no output file.
        --print-pins  the sha256 pins of every input, the modules and the doc body; written to 01_points_pins.txt as well.
        --run       writes candidates.tsv / ranges.tsv / coverage.tsv under apollo_data/cb702/qm_streams/asis_1026/ and 01_points.txt;
                    REFUSES (writing 01_points.refused.txt, never 01_points.txt) unless: the dry run completed with 0 MISMATCH; every
                    input / module / doc-body pin AND the dry-run printout's pin are pasted below the doc's freeze marker (any edit
                    above the marker changes `doc_body` and the run refuses); no rule module is loaded; the ledger (if any) verifies;
                    no output exists. On success appends two ledger rows: the dry-run printout it was frozen on and the run printout.

READINGS where the plan is silent, ambiguous or contradicts itself (numbered on from asis_common's R1-R11; the main loop decides):
  R12 The reachable sessions are exactly `lo..hi` (the window) for EVERY bracket type: `lo` is already "the first session a trade could
      be missing from the earlier frame" and `hi` "the last session the later frame reflects", so the clock clipping is applied on the
      frame's own session only, and only when that frame is in-session. The plan's eight rows are reproduced by this one rule; the
      'other' rows use the full sessions (no clipping), as the plan says.
  R13 A same-day bracket whose clocks run backwards (the later clock before the earlier one: a clock misread; 9+10 buys, 11+3 sales in
      the inventory) falls back to the FULL session, flagged `clock_order_broken`; a zero-width bracket keeps its one minute, flagged
      `width_zero`. A frame with no clock read (17 in-session frames) counts as the full session, flagged `clock_unknown`.
  R14 Clock -> minute: minutes since 09:30, inclusive at both ends; a clock before 09:30 clips to minute 0, after the close to the last
      regular minute (`session_end_minute` - 1: 389, or 209 on the 13:00 closes). Minutes at or after the close on an early-close day
      are after-hours prints and are dropped.
  R15 "Trades through" a level = the minute's high >= the level with the PREVIOUS BAR'S close below it (crossed from below, `up`), or
      the minute's low <= the level with the previous bar's close above it (`down`); the previous bar is the one before it in the day's
      bars, also for the first reachable minute (so a level crossed by the opening print is caught); only the day's FIRST bar uses its own
      open. A touch (equality) counts. F1 / F4 / F6 and the swing print carry direction `level`.
  R16 F5 swing points are read on 5-minute buckets of the minute bars (minute // 5); a swing high is a bucket whose high is strictly
      above the highs of the three buckets either side (all six must exist), confirmed at the end of the third bucket after it; the
      point 'swing' is the print itself (if its minute is reachable) and the point 'cross' the first reachable minute AFTER the
      confirmation that trades through it, in either direction.
  R17 F6: the close is the last regular minute's close (389 / 209), the market-on-close print the close of minute 385 / 205.
  R18 F10 round numbers: every multiple of $0.50 inside the reachable range IN RAW PRICE (the side's bars-only range x that session's raw
      factor), tagged with the coarsest step it satisfies ($10, $5, $1, $0.50); the row's `price` is the level divided by the factor (bar
      space), `price_raw` the level itself. Capped per R27.
  R19 F11 the average traded price = cumulative sum(close x volume) / sum(volume) over the reachable minutes so far; a cross at minute m
      when the previous close was on one side of the previous minute's average and this minute's high/low reaches this minute's
      average; the first reachable minute is never a cross (the average equals its own price).
  R20 Merging (review F7): points on the same (session, minute) merge into ONE row carrying every family tag (`families`, `levels`); a
      merged row's `price` is the MEAN of its levels (all inside that minute's bar), `family` the distinct families joined ('F2+F10'),
      `direction` the common one or 'mixed', `k` blank unless one; `our_length` is any-of, and the tags that carry it end in '*' inside
      `families` so step 7 can drop TAGS, not rows. The density check uses the unmerged levels (each with its own tolerance).
  R21 Daily-only sessions: F1 the open, F3 / F7 / F8 levels inside the day's low-high (direction from the open's side of the level),
      F4 the high and the low, F6 the close, F10 round numbers inside the day's range; no F2 / F5 / F11 (minute-only); minute blank.
      A 6+ session window (`wide_window`) reads the first 5 and the last 5 sessions this way and every session's close (§3.5), from
      daily bars even where minutes exist, so the fetch-value measurement is not polluted (`daily_only_reason`).
  R22 Panel price: computed on BOTH sides — the buy side at the first sighting frame, the sale side at the LAST sighting frame (he still
      held; the price at that clock is inside the sale's reachable range by construction) — as prior close x (1 + pct / 100) with the
      prior close = the close of the last session before the frame's date; inside/outside the bars-only range is flagged
      (`panel_outside_range`), the reader's own `pct_check` carried beside; never merged silently.
  R23 One export per record by the window END (`bar_sym`: <= 2022-03-31 the 2016-22 export under `sym_a`, after it the 2021-26 export
      under `sym`); when that export does not carry the ticker at all and the other does, the other is read and the record is flagged
      `export_fallback` (counted). The inventory's coverage claims are computed its way (A under `sym_a` OR B under `sym`, per session)
      so the claims compare like with like.
  R24 The 60 prior daily bars for the levels and the features are taken from the record's export at the ticker's own bar positions
      (holes inside the span are counted, `bar_holes`, never bridged); a feature with too short a history is blank (`short_history`).
  R25 Coverage by year uses the window END's year (`hi` / `exit_hi`), as the inventory does; the primary span is window end in
      2020-01-01..2022-06-30.
  R27 F10 is capped: more than 200 round-number levels in one side's raw range (a price in the thousands; before R12 the split-adjusted
      DRYS 2017 carried 11,700 levels in one window) coarsens the step ($1, $5, $10, $50, $100, ...) until the count fits; the side is
      flagged `round_thinned_to_<step>`. With the raw factor (R12) the cap now bites only on genuinely high-priced names.
  R28 The bracket typing is by the two frames' dates and clock contexts (R12): "sessions apart" = the calendar gap between the two frame
      dates in sessions (a 5-session gap is a 6-session window and sits in the 2-5 row). The inventory's all-years `other` / `6+` split
      differs by six buys and five sales (its throw-away script is not on disk); the review's probe showed the inventory's own split is
      inconsistent (its 'same day, other' row of 31 cannot hold the 34 inverted buys, all same-date frame pairs), and the build's probe
      showed the WHOLE difference sits OUTSIDE the primary span (14 buy / 6 sale `other` windows of 2017-19: Sunday frames, pre -> pre
      pairs): the inventory's IN-SPAN column (data.md §2.5) matches the build on every row, both sides. Tried and refuted: typing by
      window length; the no-clock frames. (Review F9, R32) The claims are therefore made on what both sides measured: the per-bracket
      in-span vectors, the in-span `bracket_other` (62 buys / 35 sales = the inventory's in-span other rows less the inverted), and the
      all-years sum other + 6+ (352 / 335); the all-years split is printed as a readout beside the inventory's, with the difference.
      The plan's §3.2 all-years 70 / 36 are the inventory's inconsistent split less the inverted; the build's 76 / 41 — the main loop
      decides whether the plan's table is corrected (the in-span numbers, which the read uses, are not in question).
  R29 The export fallback (R23) is taken only when the primary export has NO daily bar on any session of the window and the other export
      has one on at least one (a ticker merely present in the other export, with no bar in the window, is not a fallback).
  R30 The density check is printed at the §4.2 tolerance per family set (the plan's three sets), and BESIDE it, as readouts for the
      narrowing decision the plan leaves to the ledger: each set without F10 (the round numbers, every $0.50), and the tolerance at a half
      and a quarter. The first real run read 100% on every set at the §4.2 tolerance; nothing is decided here.
  R26 Stated-anchor placeholders: `stated_price`, `stated_kind`, `stated_outside_range` are blank columns of ranges.tsv, filled by step 6.
  R31 (review F2; asis_common R12) The raw factor per record and session: exact / carried / partial / missing, counted in the dry run;
      a side whose sessions' factors differ (a split inside the window) is flagged `split_inside_window` and its raw range is the min /
      max over the SESSIONS' raw ranges (never one factor x the bar range). `raw_factor` on the side row is the first reachable session's.
  R32 (review F9) The bracket claims are recast as R28 says; the four all-years `other` / `6+` claims are no longer claims.
  R33 (review F3) F9 is not a candidate family: the plan's §3.3 marks it '—' on both sides and defines it as the window's band ends,
      which ranges.tsv already carries (`range_lo` / `range_hi`, with their minutes); it is in no density set.
  R34 (review F4; the final review pass) The dry-run printout carries the sha of the three module files that made it, and --run refuses when
      they differ from the files on disk (nothing else ties the pinned printout to the pinned code). The dry run never writes the ledger (its printout is regenerated at every rerun, and `ledger_verify` would then fail
      every later --run); --run appends the dry-run row (the printout it was frozen on) and its own row. --run also refuses on a dry run
      whose RESULT line shows a MISMATCH ('DRY RUN COMPLETE' alone is written by a mismatching dry run too). The crash-fix history of the
      first real runs (10-24's lesson) is `BUILD_HISTORY` below, printed in both printouts, so the frozen dry-run printout discloses it.
  R35 (review F8) A later in-session frame whose clock reads before 09:30 (the context and the clock disagree: a misread) falls back to
      the full session, flagged `clock_before_open` (R13's pattern; before this it was clipped to minute 0 alone); the same misread on the
      EARLIER frame changes nothing (its clip was the session start already) and is flagged `clock_before_open_earlier`; an earlier frame AFTER the close, or a later frame after the close,
      flags `extended_hours_possible` (the trade may sit in that evening or the next pre-market, where we have no bars). `bar_holes`
      (calendar gaps inside the 60-bar history) and `short_history` (fewer than 60 prior bars) are columns of candidates.tsv and flags
      of ranges.tsv.
  R36 (review F9) The same-day width claims pass at a tolerance of 1 minute: the inventory prints integer medians (38, 44) where the
      build's medians of an even count are half-integers (38.5, 43.5) — a median convention, not a width difference.

BUILD HISTORY (the real-data crash-fix reruns, disclosed; see `BUILD_HISTORY`):
  2026-10-26 build: `R.Daily` shim missing (crash at load); tree B's 449 post-seal date files tripped the seal on LISTING (excluded
      unopened); F10 on split-adjusted prices (DRYS 2017: 11,700 levels; capped, R27); a mixed-key sort in the printout.
  2026-10-26 review fixes (this file): raw factor (R31), F9 dropped (R33), the run gates (R34), merged rows (R20), the clock /
      extended-hours flags (R35), the claims recast (R32); the dry run rerun after each.

Run:  python3 scripts/probes/_705_asis_1026/01_points.py --dry-run | --print-pins | --run
No subagent, no network, no production server, no paid call, nothing after 2024-12-31, none of the seven outcome folders.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import importlib.util
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import date

import numpy as np
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
fnum, GuardStop, Sessions = C.fnum, C.GuardStop, C.Sessions

# ---- the rule-free columns, BY NAME (§3.1): nothing else of entries.tsv is read -------------------------------------------------------------
ENTRY_COLS = ["eid", "sym", "sym_a", "has_bars", "first_frame", "first_vid", "first_date", "first_ctx", "prev_full_frame", "prev_full_date",
              "lo", "hi", "window_len", "inverted", "initial", "flicker", "n_sightings", "n_streams", "exit_lo", "exit_hi", "exit_frame",
              "still_held", "first_resolution"]
EXIT_COLS = ["eid", "sym", "sym_a", "exit_lo", "exit_hi", "exit_frame", "flicker", "initial"]
SNAP_COLS = ["idx", "frame_id", "vid", "date", "ctx", "clock", "full", "symbols", "blip_filled"]

BRACKETS = ("same_in_in", "same_pre_in", "same_other", "next_in_pre", "next_in_in", "next_other", "sessions_2_5", "sessions_6plus", "inverted")
BRACKET_WORDS = {"same_in_in": "same day, in-session -> in-session", "same_pre_in": "same day, pre-market -> in-session",
                 "same_other": "same day, other clock pairs", "next_in_pre": "next session, in-session -> pre-market",
                 "next_in_in": "next session, in-session -> in-session", "next_other": "next session, other",
                 "sessions_2_5": "2-5 sessions apart", "sessions_6plus": "6+ sessions apart", "inverted": "inverted (no regular session)"}
SPAN = ("2020-01-01", "2022-06-30")
WIDE_FROM = 6                      # sessions apart: daily resolution only (§3.5)
WIDE_CAP = 5                       # the first and last 5 sessions of a wide window carry the full daily-only families
OR_K = (1, 5, 15, 30, 60)          # F2
RECENT_N = (5, 10, 20, 60)         # F7
DIST_N = (3, 5, 10, 20, 40, 60)    # §3.4 dist_hi_N / dist_lo_N / ret_N
SINCE_N = (5, 20, 60)              # §3.4 sessions_since_hi_N
OUR_K = {"F2": (5, 60), "F7": (20, 60), "F8": (10, 20)}   # the lengths our old rules used (§3.3) — flagged, never a filter
ROUND_STEPS = ((1000.0, "1000"), (500.0, "500"), (100.0, "100"), (50.0, "50"), (10.0, "10"), (5.0, "5"), (1.0, "1"), (0.5, "0.5"))
ROUND_STEP_LADDER = (0.5, 1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0, 5000.0, 10000.0)   # R27: coarsened until the count fits the cap
ROUND_CAP = 200                    # R27: the most round-number levels one side carries
FAMILY_ORDER = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F10", "F11")     # F9 = the band ends, in ranges.tsv (R33)
CORE_SET = ("F1", "F3", "F4", "F6", "F10", "F11")
DENSITY_LINE = 0.60
RAW_SOURCES = ("exact", "carried", "partial", "missing")                           # R31
CAND_COLS = ["eid", "sym", "side", "date", "minute", "price", "price_raw", "raw_factor", "families", "levels", "n_families", "family",
             "direction", "k", "our_length", "source", "pos_in_day", "pos_in_day_so_far", "gap_pct", "range_pct", "range_vs_avgrange20",
             "dist_prev_high", "dist_prev_low", "dist_prev_close"] + [f"dist_hi_{n}" for n in DIST_N] + [f"dist_lo_{n}" for n in DIST_N] + \
            [f"dist_ma_{n}" for n in C.SMA_SWEEP] + ["dist_round", "dist_vwap"] + [f"ret_{n}" for n in DIST_N] + \
            ["vol_day_vs_20", "vol_sofar_vs_20", "vol_min_vs_median"] + [f"sessions_since_hi_{n}" for n in SINCE_N] + \
            ["bar_holes", "short_history", "hold_sessions_min", "hold_sessions_max", "flags"]
RANGE_COLS = ["eid", "sym", "bar_sym", "side", "year", "in_span", "flicker", "inverted", "bracket", "lo", "hi", "n_sessions", "reach_minutes",
              "resolution", "range_lo", "range_hi", "range_lo_minute", "range_hi_minute", "range_width_pct", "raw_factor", "raw_source",
              "range_lo_raw", "range_hi_raw", "panel_frame", "panel_pct", "panel_pct_check", "panel_price", "panel_price_raw",
              "panel_outside_range", "range_lo_with_panel", "range_hi_with_panel", "avg_traded_price", "avg_traded_price_raw",
              "n_candidates", "n_levels", "density_all", "density_no_our_length", "density_core", "hold_sessions_min", "hold_sessions_max",
              "stated_price", "stated_kind", "stated_outside_range", "flags"]
BUILD_HISTORY = (   # R34: the real-data crash-fix reruns, printed in both printouts (the frozen dry-run printout discloses them)
    "2026-10-26 build: `R.Daily` shim missing (crash at load); tree B's 449 post-seal date files tripped the seal on listing (now excluded "
    "unopened); F10 on split-adjusted prices (DRYS 2017: 11,700 levels; capped, R27); a mixed-key sort in the printout",
    "2026-10-26 review fixes: raw factor (R31), F9 dropped (R33), the run gates (R34), merged rows (R20), clock / extended-hours flags "
    "(R35), the bracket claims recast (R32); the dry run rerun after each",
)
COVER_COLS = ["eid", "sym", "bar_sym", "side", "year", "in_span", "bracket", "n_sessions", "daily_sessions", "minute_sessions", "resolution",
              "daily_only_reason", "export", "export_fallback"]


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


def pct(a, b) -> str:
    return f"{100.0 * a / b:.1f}%" if b else "n/a"


def table(say, hdr: list, rows: list) -> None:
    w = [max(len(str(x)) for x in col) for col in zip(hdr, *rows)] if rows else [len(h) for h in hdr]
    say("  " + "  ".join(str(h).ljust(w[k]) for k, h in enumerate(hdr)))
    for r in rows:
        say("  " + "  ".join(str(x).ljust(w[k]) for k, x in enumerate(r)))


def clock_minute(clock: str) -> "int | None":
    """'HH:MM' ET -> minutes since 09:30 (R14), unclipped; None when no clock."""
    if not clock or len(clock) < 5:
        return None
    return (int(clock[:2]) - 9) * 60 + int(clock[3:5]) - 30


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the inputs (nothing opened at import)
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Window:
    """One side of one position: the rule-free window and its two frames."""
    eid: int
    sym: str
    sym_a: str
    side: str                     # buy | sale
    lo: str                       # first session (ISO)
    hi: str                       # last session
    earlier: "C.Frame | None"     # the frame before the trade (buy: last full frame without the name; sale: the last sighting)
    later: "C.Frame | None"       # the frame after (buy: first sighting; sale: the first full frame without the name)
    inverted: bool
    flicker: bool
    first_frame: "C.Frame | None" = None
    bracket: str = ""
    year: int = 0
    in_span: bool = False
    hold_min: "int | None" = None
    hold_max: "int | None" = None
    bar_sym: str = ""
    sym_a_orig: str = ""          # entries.tsv's sym_a before the rename table (the inventory's coverage claims are made on it)
    export: str = ""
    export_fallback: bool = False
    reach: list = field(default_factory=list)       # [(date, mlo, mhi)] per reachable session (mlo/mhi: minutes, None = full)
    flags: set = field(default_factory=set)
    wide: bool = False
    raw: dict = field(default_factory=dict)         # R31: {date: (raw factor, source)} per reachable session with a daily bar


def read_frames(path: str) -> dict:
    df = pd.read_csv(C.checked(path), sep="\t", dtype=str, keep_default_na=False, usecols=SNAP_COLS)
    out = {}
    for r in df.to_dict("records"):
        f = C.Frame(idx=int(r["idx"]), frame_id=r["frame_id"], vid=r["vid"], date=r["date"], ctx=r["ctx"] or "in", clock=r["clock"],
                    full=(r["full"] == "True"), symbols=[s for s in r["symbols"].split(",") if s],
                    blip_filled=[s for s in r["blip_filled"].split(",") if s])
        out[f.frame_id] = f
    return out


def read_windows(frames: dict, S: Sessions, tally: collections.Counter, entries_path: str = None, exits_path: str = None) -> tuple:
    """-> (buys, sales, entries DataFrame). The sale's last sighting (a frame's `held` = symbols + blip_filled) and inversion are
    recomputed from the frames (claimed against exits.tsv). The paths default to this read's files; tests pass fixtures."""
    ent = pd.read_csv(C.checked(entries_path or C.FILES["entries"]), sep="\t", dtype=str, keep_default_na=False, usecols=ENTRY_COLS)
    exi = pd.read_csv(C.checked(exits_path or C.FILES["exits"]), sep="\t", dtype=str, keep_default_na=False, usecols=EXIT_COLS)
    by_idx = sorted(frames.values(), key=lambda f: f.idx)
    exits_by_eid = {int(r["eid"]): r for r in exi.to_dict("records")}
    buys, sales = [], []
    tally["entries"] = len(ent)
    for r in ent.to_dict("records"):
        eid, sym, sym_a = int(r["eid"]), r["sym"], r["sym_a"]
        initial, still, flick = r["initial"] == "True", r["still_held"] == "True", r["flicker"] == "True"
        first = frames[r["first_frame"]]
        tally["initial"] += initial
        tally["still_held"] += still
        tally["flicker"] += flick
        if not initial:
            prev = frames[r["prev_full_frame"]]
            w = Window(eid, sym, sym_a, "buy", r["lo"], r["hi"], prev, first, r["inverted"] == "True", flick, first_frame=first)
            buys.append(w)
        if not still and r["exit_frame"]:
            g1 = frames[r["exit_frame"]]
            seen = [f for f in by_idx if first.idx <= f.idx < g1.idx and sym in f.held]
            last_seen = seen[-1]
            lo_i, hi_i = C.lo_after(last_seen, S), C.asof(g1, S)
            inv = lo_i > hi_i
            if inv:
                lo_i = hi_i
            lo_d, hi_d = S.date(lo_i), S.date(hi_i)
            x = exits_by_eid.get(eid)
            if x is not None and x["exit_lo"] == lo_d and x["exit_hi"] == hi_d:
                tally["exit_windows_reproduced"] += 1
            if x is not None and x["exit_lo"] == r["exit_lo"] and x["exit_hi"] == r["exit_hi"]:
                tally["exit_windows_entries_match_exits"] += 1
            w = Window(eid, sym, sym_a, "sale", lo_d, hi_d, last_seen, g1, inv, flick, first_frame=first)
            sales.append(w)
            tally["sale_inverted"] += inv
    tally["buy_inverted"] = sum(w.inverted for w in buys)
    tally["exits_rows"] = len(exi)
    return buys, sales, ent


def hold_sessions(bw: Window, sw: Window, S: Sessions) -> tuple:
    """§3.4 `hold_sessions_min` / `max` from the two windows: the least = the sale window's first session minus the buy window's last
    (floored at 0: a same-session round trip), the most = the sale window's last minus the buy window's first."""
    return max(0, S.le(sw.lo) - S.le(bw.hi)), S.le(sw.hi) - S.le(bw.lo)


def type_bracket(w: Window, S: Sessions) -> str:
    if w.inverted:
        return "inverted"
    a, b = w.earlier, w.later
    if a.date == b.date:
        if a.ctx == "in" and b.ctx == "in":
            return "same_in_in"
        if a.ctx == "pre" and b.ctx == "in":
            return "same_pre_in"
        return "same_other"
    gap = S.le(b.date) - S.le(a.date)
    if gap <= 1:
        if a.ctx == "in" and b.ctx == "pre":
            return "next_in_pre"
        if a.ctx == "in" and b.ctx == "in":
            return "next_in_in"
        return "next_other"
    if gap <= WIDE_FROM - 1:
        return "sessions_2_5"
    return "sessions_6plus"


def reachable(w: Window, S: Sessions) -> None:
    """R12-R14: the reachable sessions and minutes of one side; sets w.reach, w.flags, w.wide."""
    w.reach, w.flags = [], set()
    if w.bracket == "inverted":
        w.flags.add("inverted")
        return
    lo_i, hi_i = S.le(w.lo), S.le(w.hi)
    assert S.date(lo_i) == w.lo and S.date(hi_i) == w.hi, (w.eid, w.side, w.lo, w.hi)
    sessions = [S.date(i) for i in range(lo_i, hi_i + 1)]
    a, b = w.earlier, w.later
    if a.ctx == "pre":
        w.flags.add("pre_market_possible")
    if b.ctx == "pre" or a.ctx == "closed" or b.ctx == "closed":      # R35: a frame after the close on either end, or a next pre-market
        w.flags.add("extended_hours_possible")
    if w.bracket in ("sessions_6plus",):
        w.wide = True
        w.flags.add("wide_window")
    clip = w.bracket not in ("same_other", "next_other")
    if not clip:
        w.flags.add("bracket_other")
    ma = clock_minute(a.clock) if (clip and a.ctx == "in" and a.date == sessions[0]) else None
    mb = clock_minute(b.clock) if (clip and b.ctx == "in" and b.date == sessions[-1]) else None
    if clip and a.ctx == "in" and a.date == sessions[0] and ma is None:
        w.flags.add("clock_unknown")
    if clip and b.ctx == "in" and b.date == sessions[-1] and mb is None:
        w.flags.add("clock_unknown")
    if ma is not None and ma < 0:                                        # R35: an in-session frame clocked before 09:30 is a misread; on the
        w.flags.add("clock_before_open_earlier")                         # earlier frame the session start is the clip either way (flag only)
        ma = None
    if mb is not None and mb < 0:                                        # on the later frame it would have left minute 0 alone: the full session
        w.flags.add("clock_before_open")
        mb = None
    if len(sessions) == 1 and ma is not None and mb is not None:
        if mb < ma:
            w.flags.add("clock_order_broken")
            ma = mb = None
        elif mb == ma:
            w.flags.add("width_zero")
    for k, d in enumerate(sessions):
        end = C.session_end_minute(d) - 1
        m0 = max(0, min(ma, end)) if (k == 0 and ma is not None) else None
        m1 = max(0, min(mb, end)) if (k == len(sessions) - 1 and mb is not None) else None
        w.reach.append((d, m0, m1))


def panel_pcts(path: str, wanted: set) -> dict:
    """{frame_id: {sym: (pct, pct_check)}} for the frames in `wanted`, from the reader's jsonl; counts over every panel frame."""
    out, n = {}, collections.Counter()
    with open(C.checked(path), encoding="utf-8") as fh:
        for ln in fh:
            r = json.loads(ln)
            n["frames"] += 1
            if not r.get("panel_found"):
                continue
            n["panel_frames"] += 1
            rows = r.get("rows") or []
            n["rows"] += len(rows)
            n["rows_with_pct"] += sum(1 for x in rows if x.get("pct") is not None)
            n["rows_pct_ok"] += sum(1 for x in rows if x.get("pct_check") == "ok")
            if r["frame_id"] in wanted:
                out[r["frame_id"]] = {x["sym"]: (x.get("pct"), x.get("pct_check") or "") for x in rows if x.get("sym")}
    out["_counts"] = n
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# bars: the record's export, the per-ticker daily bars, the minute store
# ═════════════════════════════════════════════════════════════════════════════════════════════
class Bars:
    def __init__(self, dailies: dict, store, S: Sessions):
        self.dailies, self.store, self.S = dailies, store, S
        self._bars = {}          # (export, tk) -> (DailyBars, {date: j}) | (None, None)

    def daily(self, export: str, tk: str):
        key = (export, tk)
        if key not in self._bars:
            b, _cidx = C.bars_of_ticker(self.dailies[export], tk)
            self._bars[key] = (b, {d.isoformat(): j for j, d in enumerate(b.dates)}) if b is not None else (None, None)
        return self._bars[key]

    def has_daily(self, export: str, tk: str, d: str) -> bool:
        b, ix = self.daily(export, tk)
        return b is not None and d in ix


def assign_export(w: Window, bars: Bars, tally: collections.Counter) -> None:
    """R23: one export per record by the window end; the other export only when the first carries none of the ticker."""
    end = w.hi
    w.bar_sym = C.bar_sym(end, w.sym_a, w.sym)
    primary = "A" if end <= C.A_LAST else "B"
    other = "B" if primary == "A" else "A"
    w.export = primary
    sessions = [d for d, _, _ in w.reach]
    if not any(bars.has_daily(primary, w.bar_sym, d) for d in sessions):
        alt = w.sym if primary == "A" else w.sym_a
        if any(bars.has_daily(other, alt, d) for d in sessions):
            w.export, w.bar_sym, w.export_fallback = other, alt, True
            tally["export_fallback"] += 1
    if w.lo <= C.A_LAST < w.hi:
        tally["windows_straddle_A_LAST"] += 1


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the candidate generator — pure over (reachable minutes, the day's minute bars, the day's context from daily bars)
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Point:
    date: str
    minute: "int | None"
    price: float
    family: str
    direction: str                # up | down | level
    k: str = ""
    which: str = ""               # high | low | close | open | swing | cross | moc ...
    our_length: bool = False
    source: str = "minute"
    sofar_idx: "int | None" = None   # the bar index in the minute arrays (for the so-far features)
    price_raw: "float | None" = None  # R31: the level in the prices he saw (F10: the round number itself; else price x the raw factor)


def _rel(x: float, ref: float) -> "float | str":
    return "" if (ref is None or not np.isfinite(ref) or ref == 0) else round(100.0 * (x - ref) / ref, 4)


def day_context(bars, ix: dict, d: str) -> "dict | None":
    """The day's own bar and its prior-session levels from the ticker's daily bars (R24)."""
    j = ix.get(d)
    if j is None:
        return None
    h, l, c, o, v = bars.h, bars.l, bars.c, bars.o, bars.v
    ctx = {"j": j, "o": fnum(o[j]), "h": fnum(h[j]), "l": fnum(l[j]), "c": fnum(c[j]), "v": fnum(v[j]), "short_history": j < 60,
           "bar_holes": 0}
    if j >= 1:
        ctx["prev_h"], ctx["prev_l"], ctx["prev_c"] = fnum(h[j - 1]), fnum(l[j - 1]), fnum(c[j - 1])
    else:
        ctx["prev_h"] = ctx["prev_l"] = ctx["prev_c"] = None
    for n in sorted(set(DIST_N) | set(RECENT_N) | set(SINCE_N)):
        if j >= n:
            seg_h, seg_l = h[j - n:j], l[j - n:j]
            ctx[f"hi_{n}"], ctx[f"lo_{n}"] = fnum(seg_h.max()), fnum(seg_l.min())
            ctx[f"since_hi_{n}"] = n - 1 - int(np.argmax(seg_h))     # sessions since the N-session high, counted back from the prior session
        else:
            ctx[f"hi_{n}"] = ctx[f"lo_{n}"] = ctx[f"since_hi_{n}"] = None
    for n in DIST_N:
        ctx[f"ret_{n}"] = _rel(fnum(c[j - 1]), fnum(c[j - 1 - n])) if j - 1 - n >= 0 else ""
    sm = C.smas_sweep(bars)
    for n in C.SMA_SWEEP:
        val = fnum(sm[n][j - 1]) if j >= 1 else float("nan")
        ctx[f"ma_{n}"] = val if np.isfinite(val) else None
    if j >= 20:
        ctx["avgrange20"] = fnum((h[j - 20:j] - l[j - 20:j]).mean())
        ctx["vol20"] = fnum(v[j - 20:j].mean())
    else:
        ctx["avgrange20"] = ctx["vol20"] = None
    # holes inside the 60-session history: the calendar gaps between consecutive bars
    if j >= 1:
        lo_j = max(0, j - 60)
        ds = bars.dates[lo_j:j + 1]
        ctx["bar_holes"] = sum(1 for a, b in zip(ds, ds[1:]) if (b - a).days > 4)
    return ctx


def first_cross(level: float, m: np.ndarray, o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, i0: int, i1: int,
                direction: str) -> "int | None":
    """R15: the first bar index in [i0, i1] whose bar trades through `level` in `direction`; the previous bar's close (the first bar's open)
    must sit on the other side. Vectorised: `prev` = [o[0], c[0], c[1], ...]."""
    if i0 > i1 or i0 < 0:
        return None
    prev = np.concatenate([o[:1], c[:-1]])[i0:i1 + 1]
    if direction == "up":
        hit = np.flatnonzero((prev < level) & (h[i0:i1 + 1] >= level))
    else:
        hit = np.flatnonzero((prev > level) & (l[i0:i1 + 1] <= level))
    return int(i0 + hit[0]) if len(hit) else None


def minute_points(d: str, mb, m0: "int | None", m1: "int | None", ctx: dict, end: int, round_range: tuple, factor: float = 1.0) -> tuple:
    """-> (points, not_reached Counter, info) for one session with minute bars; the reachable minutes are [m0, m1] (None = the end).
    `round_range` is the side's bars-only range; `factor` the session's raw factor (R31): F10 levels are raw round numbers inside
    round_range x factor, crossed in bar space at level / factor."""
    sel = mb.minute < end                                    # R14: after-hours prints on an early-close day dropped
    m, o, h, l, c, v = mb.minute[sel], mb.o[sel], mb.h[sel], mb.l[sel], mb.c[sel], mb.v[sel]
    nr, pts, info = collections.Counter(), [], {}
    if len(m) == 0:
        return pts, nr, {"empty": True}
    mlo = 0 if m0 is None else m0
    mhi = end - 1 if m1 is None else m1
    idx = np.flatnonzero((m >= mlo) & (m <= mhi))
    if len(idx) == 0:
        return pts, nr, {"no_bar_in_reach": True}
    i0, i1 = int(idx[0]), int(idx[-1])
    info["i0"], info["i1"] = i0, i1
    info["range_lo"], info["range_hi"] = fnum(l[i0:i1 + 1].min()), fnum(h[i0:i1 + 1].max())
    info["range_lo_minute"] = int(m[i0 + int(np.argmin(l[i0:i1 + 1]))])
    info["range_hi_minute"] = int(m[i0 + int(np.argmax(h[i0:i1 + 1]))])
    cv = np.cumsum(c[i0:i1 + 1] * v[i0:i1 + 1])
    vv = np.cumsum(v[i0:i1 + 1])
    vwap = np.where(vv > 0, cv / np.where(vv > 0, vv, 1.0), c[i0:i1 + 1])
    info["avg_traded_price"] = fnum(vwap[-1])
    info["n_minutes"] = i1 - i0 + 1

    def add(level, direction, fam, k="", which="", our=False, at=None, raw=None):
        """A level crossed inside the reachable set (or a print at `at`)."""
        if at is None:
            i = first_cross(level, m, o, h, l, c, i0, i1, direction)
            if i is None:
                nr[f"{fam}:{which or direction}"] += 1
                return
        else:
            i = at
        pts.append(Point(d, int(m[i]), float(level), fam, direction, str(k), which, our, "minute", i, raw))

    def levels_both(level, fam, k="", which="", our=False, raw=None):
        add(level, "up", fam, k, which, our, raw=raw)
        add(level, "down", fam, k, which, our, raw=raw)

    # F1 the open: minute 0's print
    if int(m[0]) == 0 and i0 == 0:
        pts.append(Point(d, 0, fnum(o[0]), "F1", "level", "", "open", False, "minute", 0))
    else:
        nr["F1:open"] += 1
    # F2 opening-range high / low, k minutes; the cross must come at or after minute k
    for k in OR_K:
        if k >= end:
            continue
        s = m < k
        if not s.any():
            nr[f"no_level:F2:{k}"] += 2
            continue
        k_high, k_low = fnum(h[s].max()), fnum(l[s].min())
        j0 = max(i0, int(np.searchsorted(m, k)))
        if j0 > i1:
            nr[f"F2:{k}:after_reach"] += 4
            continue
        for level, which in ((k_high, "high"), (k_low, "low")):
            for direction in ("up", "down"):
                i = first_cross(level, m, o, h, l, c, j0, i1, direction)
                if i is None:
                    nr[f"F2:{k}:{which}:{direction}"] += 1
                else:
                    pts.append(Point(d, int(m[i]), level, "F2", direction, str(k), which, k in OUR_K["F2"], "minute", i))
    # F3 the prior session's high, low, close
    if ctx.get("prev_c") is not None:
        for level, which in ((ctx["prev_h"], "high"), (ctx["prev_l"], "low"), (ctx["prev_c"], "close")):
            levels_both(level, "F3", "", which)
    # F4 the day's own high and low: the first print of each
    ih, il = int(np.argmax(h)), int(np.argmin(l))
    for i, which, arr in ((ih, "high", h), (il, "low", l)):
        if i0 <= i <= i1:
            pts.append(Point(d, int(m[i]), fnum(arr[i]), "F4", "level", "", which, False, "minute", i))
        else:
            nr[f"F4:{which}"] += 1
    # F5 swing points on 5-minute buckets (R16)
    bucket = m // 5
    ub = np.unique(bucket)
    bh = np.array([fnum(h[bucket == b].max()) for b in ub])
    bl = np.array([fnum(l[bucket == b].min()) for b in ub])
    for q in range(3, len(ub) - 3):
        if not (ub[q - 3] == ub[q] - 3 and ub[q + 3] == ub[q] + 3):
            continue
        confirm_min = int((ub[q] + 4) * 5 - 1)
        for arr, which, is_high in ((bh, "high", True), (bl, "low", False)):
            val = fnum(arr[q])
            neigh = np.concatenate([arr[q - 3:q], arr[q + 1:q + 4]])
            ok = (val > neigh.max()) if is_high else (val < neigh.min())
            if not ok:
                continue
            inb = np.flatnonzero(bucket == ub[q])
            ip = int(inb[int(np.argmax(h[inb]))] if is_high else inb[int(np.argmin(l[inb]))])
            if i0 <= ip <= i1:
                pts.append(Point(d, int(m[ip]), val, "F5", "level", "", f"swing_{which}", False, "minute", ip))
            else:
                nr[f"F5:swing_{which}"] += 1
            j0 = max(i0, int(np.searchsorted(m, confirm_min + 1)))
            if j0 > i1:
                nr[f"F5:cross_{which}"] += 2
                continue
            for direction in ("up", "down"):
                i = first_cross(val, m, o, h, l, c, j0, i1, direction)
                if i is None:
                    nr[f"F5:cross_{which}:{direction}"] += 1
                else:
                    pts.append(Point(d, int(m[i]), val, "F5", direction, "", f"cross_{which}", False, "minute", i))
    # F6 the close and the market-on-close print (R17)
    last = len(m) - 1
    if i0 <= last <= i1 and int(m[last]) == end - 1:
        pts.append(Point(d, int(m[last]), fnum(c[last]), "F6", "level", "", "close", False, "minute", last))
    else:
        nr["F6:close"] += 1
    imoc = np.flatnonzero(m == end - 5)
    if len(imoc) and i0 <= int(imoc[0]) <= i1:
        pts.append(Point(d, int(m[int(imoc[0])]), fnum(c[int(imoc[0])]), "F6", "level", "", "moc", False, "minute", int(imoc[0])))
    else:
        nr["F6:moc"] += 1
    # F7 the prior N sessions' highest high / lowest low
    for n in RECENT_N:
        if ctx.get(f"hi_{n}") is None:
            nr[f"no_level:F7:{n}"] += 4
            continue
        levels_both(ctx[f"hi_{n}"], "F7", n, "high", n in OUR_K["F7"])
        levels_both(ctx[f"lo_{n}"], "F7", n, "low", n in OUR_K["F7"])
    # F8 the averages, seven lengths
    for n in C.SMA_SWEEP:
        if ctx.get(f"ma_{n}") is None:
            nr[f"no_level:F8:{n}"] += 2
            continue
        levels_both(ctx[f"ma_{n}"], "F8", n, "ma", n in OUR_K["F8"])
    # (F9, the band ends, is not a candidate row: ranges.tsv carries them — R33)
    # F10 round numbers inside the side's reachable range, in RAW price (R18 / R31)
    rlo, rhi = round_range
    for level_raw, tag in round_levels(rlo * factor, rhi * factor):
        levels_both(level_raw / factor, "F10", tag, "round", raw=level_raw)
    # F11 the average traded price so far (R19)
    found = {"up": False, "down": False}
    for q in range(1, i1 - i0 + 1):
        i = i0 + q
        pc, pv = fnum(c[i - 1]), fnum(vwap[q - 1])
        cur = fnum(vwap[q])
        if not found["up"] and pc < pv and fnum(h[i]) >= cur:
            pts.append(Point(d, int(m[i]), cur, "F11", "up", "", "vwap", False, "minute", i))
            found["up"] = True
        if not found["down"] and pc > pv and fnum(l[i]) <= cur:
            pts.append(Point(d, int(m[i]), cur, "F11", "down", "", "vwap", False, "minute", i))
            found["down"] = True
        if found["up"] and found["down"]:
            break
    for direction, ok in found.items():
        if not ok:
            nr[f"F11:{direction}"] += 1
    info["arrays"] = (m, o, h, l, c, v, vwap, i0)
    return pts, nr, info


def round_levels(lo: float, hi: float, cap: int = None) -> list:
    """Every multiple of $0.50 in [lo, hi], tagged with the coarsest step it satisfies (R18). R27: when more than `cap` levels would fall in
    the range (a split-adjusted price in the thousands or more), the step is coarsened ($1, $5, $10, $50, $100, ...) until the count fits,
    and the caller flags the side `round_thinned`. Returns [(level, tag)]; `round_levels.last_step` carries the step used."""
    cap = ROUND_CAP if cap is None else cap
    round_levels.last_step = 0.5
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi < lo:
        return []
    for step in ROUND_STEP_LADDER:
        start, stop = int(np.ceil(lo / step - 1e-9)), int(np.floor(hi / step + 1e-9))
        if stop - start + 1 <= cap or step == ROUND_STEP_LADDER[-1]:
            break
    round_levels.last_step = step
    out = []
    for q in range(start, stop + 1):
        level = q * step
        tag = next((t for st, t in ROUND_STEPS if abs(level / st - round(level / st)) < 1e-9), str(step))
        out.append((level, tag))
    return out


def daily_points(d: str, ctx: dict, families: tuple, round_range: tuple, factor: float = 1.0) -> tuple:
    """R21: the daily-only families of one session (minute blank). `families` limits a wide window's middle sessions to the close.
    `factor` = the session's raw factor (R31) for the F10 levels."""
    o, h, l, c = ctx["o"], ctx["h"], ctx["l"], ctx["c"]
    pts, nr = [], collections.Counter()

    def crossed(level, fam, k="", which="", our=False, raw=None):
        if not (l <= level <= h):
            nr[f"{fam}:{which}"] += 1
            return
        direction = "up" if o < level else ("down" if o > level else "level")
        pts.append(Point(d, None, float(level), fam, direction, str(k), which, our, "daily_only", None, raw))

    if "F1" in families:
        pts.append(Point(d, None, o, "F1", "level", "", "open", False, "daily_only"))
    if "F3" in families and ctx.get("prev_c") is not None:
        for level, which in ((ctx["prev_h"], "high"), (ctx["prev_l"], "low"), (ctx["prev_c"], "close")):
            crossed(level, "F3", "", which)
    if "F4" in families:
        pts.append(Point(d, None, h, "F4", "level", "", "high", False, "daily_only"))
        pts.append(Point(d, None, l, "F4", "level", "", "low", False, "daily_only"))
    if "F6" in families:
        pts.append(Point(d, None, c, "F6", "level", "", "close", False, "daily_only"))
    if "F7" in families:
        for n in RECENT_N:
            if ctx.get(f"hi_{n}") is None:
                continue
            crossed(ctx[f"hi_{n}"], "F7", n, "high", n in OUR_K["F7"])
            crossed(ctx[f"lo_{n}"], "F7", n, "low", n in OUR_K["F7"])
    if "F8" in families:
        for n in C.SMA_SWEEP:
            if ctx.get(f"ma_{n}") is not None:
                crossed(ctx[f"ma_{n}"], "F8", n, "ma", n in OUR_K["F8"])
    if "F10" in families:
        rlo, rhi = round_range
        for level_raw, tag in round_levels(max(rlo, l) * factor, min(rhi, h) * factor):
            crossed(level_raw / factor, "F10", tag, "round", raw=level_raw)
    return pts, nr


def features(p: Point, ctx: dict, arrays, round_range: tuple) -> dict:
    """§3.4: the raw chart features of one candidate."""
    o, h, l, c = ctx["o"], ctx["h"], ctx["l"], ctx["c"]
    f = {}
    rng = h - l
    f["pos_in_day"] = round((p.price - l) / rng, 4) if rng > 0 else ""
    f["gap_pct"] = _rel(o, ctx.get("prev_c"))
    f["range_pct"] = round(100.0 * rng / c, 4) if c else ""
    f["range_vs_avgrange20"] = round(rng / ctx["avgrange20"], 4) if ctx.get("avgrange20") else ""
    f["dist_prev_high"], f["dist_prev_low"], f["dist_prev_close"] = _rel(p.price, ctx.get("prev_h")), _rel(p.price, ctx.get("prev_l")), _rel(p.price, ctx.get("prev_c"))
    for n in DIST_N:
        f[f"dist_hi_{n}"], f[f"dist_lo_{n}"] = _rel(p.price, ctx.get(f"hi_{n}")), _rel(p.price, ctx.get(f"lo_{n}"))
        f[f"ret_{n}"] = ctx.get(f"ret_{n}", "")
    for n in C.SMA_SWEEP:
        f[f"dist_ma_{n}"] = _rel(p.price, ctx.get(f"ma_{n}"))
    praw = p.price_raw if p.price_raw is not None else p.price      # R31: the nearest round number in the prices he saw
    nearest = round(praw / 0.5) * 0.5
    f["dist_round"] = _rel(praw, nearest) if nearest else ""
    f["bar_holes"], f["short_history"] = ctx.get("bar_holes", ""), ctx.get("short_history", "")
    f["vol_day_vs_20"] = round(ctx["v"] / ctx["vol20"], 4) if ctx.get("vol20") else ""
    for n in SINCE_N:
        f[f"sessions_since_hi_{n}"] = "" if ctx.get(f"since_hi_{n}") is None else ctx[f"since_hi_{n}"]
    f["pos_in_day_so_far"] = f["dist_vwap"] = f["vol_sofar_vs_20"] = f["vol_min_vs_median"] = ""
    if arrays is not None and p.sofar_idx is not None:
        m, mo, mh, ml, mc, mv, vwap, i0 = arrays
        i = p.sofar_idx
        hs, ls = fnum(mh[:i + 1].max()), fnum(ml[:i + 1].min())
        f["pos_in_day_so_far"] = round((p.price - ls) / (hs - ls), 4) if hs > ls else ""
        q = i - i0
        if 0 <= q < len(vwap):
            f["dist_vwap"] = _rel(p.price, fnum(vwap[q]))
        f["vol_sofar_vs_20"] = round(fnum(mv[:i + 1].sum()) / ctx["vol20"], 4) if ctx.get("vol20") else ""
        med = fnum(np.median(mv))
        f["vol_min_vs_median"] = round(fnum(mv[i]) / med, 4) if med > 0 else ""
    return f


def merge_points(pts: list) -> list:
    """R20: one row per (session, minute); every family tag kept."""
    groups = collections.OrderedDict()
    for p in sorted(pts, key=lambda p: (p.date, -1 if p.minute is None else p.minute, FAMILY_ORDER.index(p.family), p.k, p.which, p.direction)):
        key = (p.date, p.minute, p.price if p.minute is None else None)
        groups.setdefault(key, []).append(p)
    return list(groups.values())


def tolerance(price: float, day_range: float, scale: float = 1.0) -> float:
    """§4.2: max(1% of price, 10% of that session's range, $0.05); `scale` < 1 is a READOUT arm of the dry run (R30), never the bar."""
    return max(0.01 * price * scale, 0.10 * day_range * scale, 0.05)


def density(levels: list, lo: float, hi: float, scale: float = 1.0) -> "float | str":
    """The share of [lo, hi] covered by the union of the levels' tolerance bands; levels = [(price, day_range)]."""
    if not levels:
        return 0.0
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return ""
    if hi <= lo:
        return 1.0
    ivs = sorted((max(lo, p - tolerance(p, r, scale)), min(hi, p + tolerance(p, r, scale))) for p, r in levels)
    cov, cur_a, cur_b = 0.0, None, None
    for a, b in ivs:
        if b < a:
            continue
        if cur_a is None:
            cur_a, cur_b = a, b
        elif a <= cur_b:
            cur_b = max(cur_b, b)
        else:
            cov += cur_b - cur_a
            cur_a, cur_b = a, b
    if cur_a is not None:
        cov += cur_b - cur_a
    return cov / (hi - lo)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# one side end to end
# ═════════════════════════════════════════════════════════════════════════════════════════════
def raw_factors(w: Window, bars: Bars, rawmap: dict, splits: dict, tally: collections.Counter) -> None:
    """R31: w.raw = {session: (factor, source)} for every reachable session with a daily bar in the record's export. exact = the raw file's
    close for (sym_a, d) over the record's OWN export's close at d; carried = the ticker's last exact factor moved through the split list
    (keyed by the bar symbol) to d; partial = no raw row at all: the product of the listed splits after d (those after the seal are
    unknown); missing = neither. Also sets `split_inside_window` when the sessions' factors differ."""
    w.raw = {}
    b, ix = bars.daily(w.export, w.bar_sym)
    if b is None:
        return
    rw = rawmap.get(w.sym_a)
    spl = splits.get(w.bar_sym, [])
    for d, _, _ in w.reach:
        j = ix.get(d)
        if j is None:
            continue
        adj = fnum(b.c[j])
        if rw is not None:
            k = bisect.bisect_left(rw[0], d)
            if k < len(rw[0]) and rw[0][k] == d and adj > 0:
                w.raw[d] = (fnum(rw[1][k]) / adj, "exact")
                continue
            if k > 0:                                                    # the last raw session before d, carried through the splits
                d0 = rw[0][k - 1]
                j0 = ix.get(d0)
                if j0 is not None and fnum(b.c[j0]) > 0:
                    f0 = fnum(rw[1][k - 1]) / fnum(b.c[j0])
                    from_d0 = C.raw_factor_for(date.fromisoformat(d0), spl)
                    at_d = C.raw_factor_for(date.fromisoformat(d), spl)
                    w.raw[d] = (f0 * at_d / from_d0, "carried")
                    continue
        if spl:
            w.raw[d] = (C.raw_factor_for(date.fromisoformat(d), spl), "partial")
        else:
            w.raw[d] = (1.0, "missing")
    for _d, (_f, src) in w.raw.items():
        tally[("raw_source", w.side, src)] += 1
    fs = [f for f, _ in w.raw.values()]
    if fs and max(fs) / min(fs) > 1.001:
        w.flags.add("split_inside_window")


def side_rows(w: Window, bars: Bars, panel: dict, S: Sessions, tally: collections.Counter, nr_all: collections.Counter) -> tuple:
    """-> (range row, coverage row, candidate rows) for one side."""
    b, ix = bars.daily(w.export, w.bar_sym)
    cover = {"eid": w.eid, "sym": w.sym, "bar_sym": w.bar_sym, "side": w.side, "year": w.year, "in_span": w.in_span, "bracket": w.bracket,
             "n_sessions": len(w.reach), "daily_sessions": 0, "minute_sessions": 0, "resolution": "none", "daily_only_reason": "",
             "export": w.export, "export_fallback": w.export_fallback}
    rng = {k: "" for k in RANGE_COLS}
    rng.update({"eid": w.eid, "sym": w.sym, "bar_sym": w.bar_sym, "side": w.side, "year": w.year, "in_span": w.in_span, "flicker": w.flicker,
                "inverted": w.inverted, "bracket": w.bracket, "lo": w.lo, "hi": w.hi, "n_sessions": len(w.reach), "hold_sessions_min": "" if w.hold_min is None else w.hold_min,
                "hold_sessions_max": "" if w.hold_max is None else w.hold_max, "n_candidates": 0, "n_levels": 0})
    flags = set(w.flags)
    if not w.reach:
        rng["flags"] = "|".join(sorted(flags))
        return rng, cover, []
    sessions = [d for d, _, _ in w.reach]
    daily_ok = [bars.has_daily(w.export, w.bar_sym, d) for d in sessions] if b is not None else [False] * len(sessions)
    cover["daily_sessions"] = sum(daily_ok)
    minute_ok = []
    for d in sessions:
        st = w.wide and "wide" or (bars.store.state(d, w.bar_sym).split("/")[0] if b is not None else "missing")
        minute_ok.append(st == "ok")
    cover["minute_sessions"] = sum(minute_ok)
    if cover["daily_sessions"] == 0:
        cover["resolution"] = "none"
        flags.add("no_daily_bar")
        rng["flags"] = "|".join(sorted(flags))
        rng["resolution"] = "none"
        return rng, cover, []
    if cover["daily_sessions"] < len(sessions):
        flags.add("range_incomplete")
    if w.wide:
        cover["resolution"], cover["daily_only_reason"] = "daily_only", "wide_window"
    elif cover["minute_sessions"] == len(sessions):
        cover["resolution"] = "minute"
    elif cover["minute_sessions"] == 0:
        cover["resolution"], cover["daily_only_reason"] = "daily_only", "no_minute_file"
    else:
        cover["resolution"], cover["daily_only_reason"] = "partial", "some_sessions_no_minute_file"
    rng["resolution"] = cover["resolution"]
    # pass 1: the bars-only range over the reachable set (minutes where they exist, else the day's low-high); the raw range per session (R31)
    per_day = []
    lo_v, hi_v, lo_at, hi_at, total_cv, total_v, total_cvf, n_min = np.inf, -np.inf, ("", ""), ("", ""), 0.0, 0.0, 0.0, 0
    lo_raw, hi_raw = np.inf, -np.inf
    first_factor, first_source = None, None
    for k, (d, m0, m1) in enumerate(w.reach):
        if not daily_ok[k]:
            per_day.append(None)
            continue
        ctx = day_context(b, ix, d)
        fac, src = w.raw.get(d, (1.0, "missing"))
        if first_factor is None:
            first_factor, first_source = fac, src
        if ctx.get("short_history"):
            flags.add("short_history")
        if ctx.get("bar_holes"):
            flags.add("bar_holes")
        end = C.session_end_minute(d)
        mb = None
        if minute_ok[k] and not w.wide:
            mb = bars.store.get(d, w.bar_sym)
            if mb is None:
                minute_ok[k] = False
        if mb is not None:
            sel = mb.minute < end
            m, h_, l_, c_, v_ = mb.minute[sel], mb.h[sel], mb.l[sel], mb.c[sel], mb.v[sel]
            mlo, mhi = (0 if m0 is None else m0), (end - 1 if m1 is None else m1)
            idx = np.flatnonzero((m >= mlo) & (m <= mhi))
            if len(idx) == 0:
                flags.add("no_minute_bar_in_reach")
                per_day.append({"d": d, "ctx": ctx, "mb": None, "m0": m0, "m1": m1, "daily_only": True, "factor": fac})
                lo_d, hi_d = ctx["l"], ctx["h"]
                lo_m = hi_m = ""
            else:
                i0, i1 = int(idx[0]), int(idx[-1])
                if ctx["c"] > 0 and abs(fnum(c_[-1]) / ctx["c"] - 1.0) > 0.02:
                    flags.add("minute_daily_close_differ")     # the last minute close vs the daily close: > 2% apart (an auction print, or
                lo_d, hi_d = fnum(l_[i0:i1 + 1].min()), fnum(h_[i0:i1 + 1].max())   # a differently adjusted tree); the raw factor is the daily's
                lo_m, hi_m = int(m[i0 + int(np.argmin(l_[i0:i1 + 1]))]), int(m[i0 + int(np.argmax(h_[i0:i1 + 1]))])
                cv_d = fnum((c_[i0:i1 + 1] * v_[i0:i1 + 1]).sum())
                total_cv += cv_d
                total_cvf += cv_d * fac
                total_v += fnum(v_[i0:i1 + 1].sum())
                n_min += i1 - i0 + 1
                per_day.append({"d": d, "ctx": ctx, "mb": mb, "m0": m0, "m1": m1, "daily_only": False, "factor": fac})
        else:
            lo_d, hi_d = ctx["l"], ctx["h"]
            lo_m = hi_m = ""
            per_day.append({"d": d, "ctx": ctx, "mb": None, "m0": m0, "m1": m1, "daily_only": True, "factor": fac})
            if m0 is not None or m1 is not None:
                flags.add("bracket_clipped_lost_daily_only")   # the clock bracket cannot narrow a daily bar
        if lo_d < lo_v:
            lo_v, lo_at = lo_d, (d, lo_m)
        if hi_d > hi_v:
            hi_v, hi_at = hi_d, (d, hi_m)
        lo_raw, hi_raw = min(lo_raw, lo_d * fac), max(hi_raw, hi_d * fac)
    rng["range_lo"], rng["range_hi"] = round(lo_v, 4), round(hi_v, 4)
    rng["range_lo_minute"], rng["range_hi_minute"] = f"{lo_at[0]}:{lo_at[1]}", f"{hi_at[0]}:{hi_at[1]}"
    rng["range_width_pct"] = round(100.0 * (hi_v - lo_v) / lo_v, 4) if lo_v > 0 else ""
    rng["raw_factor"], rng["raw_source"] = round(first_factor, 6), first_source
    rng["range_lo_raw"], rng["range_hi_raw"] = round(lo_raw, 4), round(hi_raw, 4)
    rng["reach_minutes"] = n_min
    rng["avg_traded_price"] = round(total_cv / total_v, 4) if total_v > 0 else ""
    rng["avg_traded_price_raw"] = round(total_cvf / total_v, 4) if total_v > 0 else ""
    # the panel's own price (R22)
    pf = w.later if w.side == "buy" else w.earlier
    cell = (panel.get(pf.frame_id) or {}).get(w.sym)
    rng["panel_frame"] = pf.frame_id
    lo_p, hi_p = lo_v, hi_v
    if cell is not None and cell[0] is not None:
        rng["panel_pct"], rng["panel_pct_check"] = cell[0], cell[1]
        pj = S.lt(pf.date)
        prev_d = S.date(pj) if pj >= 0 else None
        if prev_d is not None and ix is not None and prev_d in ix:
            prev_c = fnum(b.c[ix[prev_d]])
            price = prev_c * (1.0 + fnum(cell[0]) / 100.0)
            rng["panel_price"] = round(price, 4)
            pfac = w.raw.get(S.date(S.le(pf.date)), w.raw.get(prev_d, (first_factor, "")))[0] if w.raw else first_factor
            rng["panel_price_raw"] = round(price * pfac, 4)
            outside = not (lo_v <= price <= hi_v)
            rng["panel_outside_range"] = outside
            if outside:
                flags.add("panel_outside_range")
                tally[("panel_outside_ctx", f"{w.side}:{pf.ctx}")] += 1
            lo_p, hi_p = min(lo_v, price), max(hi_v, price)
            tally[f"panel_{w.side}_inside" if not outside else f"panel_{w.side}_outside"] += 1
            if w.in_span:
                tally[f"panel_{w.side}_inside_span" if not outside else f"panel_{w.side}_outside_span"] += 1
        else:
            flags.add("panel_no_prior_close")
    else:
        flags.add("panel_no_pct")
    rng["range_lo_with_panel"], rng["range_hi_with_panel"] = round(lo_p, 4), round(hi_p, 4)
    # pass 2: the candidates (F10 in raw price per session: R18 / R31)
    round_range = (lo_v, hi_v)
    all_pts, cand_rows, levels_all = [], [], []
    n_days = len(per_day)
    for k, pdy in enumerate(per_day):
        if pdy is None:
            continue
        d, ctx, fac = pdy["d"], pdy["ctx"], pdy["factor"]
        day_range_raw = (ctx["h"] - ctx["l"]) * fac
        arrays = None
        round_levels.last_step = 0.5
        if pdy["mb"] is not None:
            pts, nr, info = minute_points(d, pdy["mb"], pdy["m0"], pdy["m1"], ctx, C.session_end_minute(d), round_range, fac)
            arrays = info.get("arrays")
        else:
            if w.wide and WIDE_CAP <= k < n_days - WIDE_CAP:
                fams = ("F6",)
            else:
                fams = ("F1", "F3", "F4", "F6", "F7", "F8", "F10")
            pts, nr = daily_points(d, ctx, fams, round_range, fac)
        if round_levels.last_step != 0.5:
            flags.add(f"round_thinned_to_{round_levels.last_step:g}")
        for key, n in nr.items():
            nr_all[key] += n
        for p in pts:
            if p.price_raw is None:
                p.price_raw = p.price * fac
            levels_all.append((p.price_raw, day_range_raw, p.family, p.our_length))
        for grp in merge_points(pts):
            p0 = grp[0]
            fams_in = []
            for p in grp:
                if p.family not in fams_in:
                    fams_in.append(p.family)
            dirs = {p.direction for p in grp}
            merged = len(grp) > 1
            row_price = sum(p.price for p in grp) / len(grp) if merged else p0.price
            row_raw = sum(p.price_raw for p in grp) / len(grp) if merged else p0.price_raw
            pm = Point(p0.date, p0.minute, row_price, "+".join(fams_in), (dirs.pop() if len(dirs) == 1 else "mixed"),
                       p0.k if len(grp) == 1 else "", "", any(p.our_length for p in grp), p0.source, p0.sofar_idx, row_raw)
            f = features(pm, ctx, arrays, round_range)
            row = {"eid": w.eid, "sym": w.sym, "side": w.side, "date": d, "minute": "" if p0.minute is None else p0.minute,
                   "price": round(pm.price, 4), "price_raw": round(pm.price_raw, 4), "raw_factor": round(fac, 6),
                   "families": "+".join(f"{p.family}{'(' + p.k + ')' if p.k else ''}{':' + p.which if p.which else ''}:{p.direction}{'*' if p.our_length else ''}" for p in grp),
                   "levels": "|".join(f"{p.family}:{round(p.price, 4)}" for p in grp), "n_families": len(grp), "family": pm.family,
                   "direction": pm.direction, "k": pm.k, "our_length": pm.our_length, "source": p0.source,
                   "hold_sessions_min": rng["hold_sessions_min"], "hold_sessions_max": rng["hold_sessions_max"],
                   "flags": "|".join(sorted(f for f in flags if f in ("daily_only", "wide_window", "pre_market_possible", "extended_hours_possible",
                                                                      "split_inside_window", "clock_before_open")))}
            if pdy["daily_only"]:
                row["flags"] = "|".join(sorted(set(row["flags"].split("|")) - {""} | {"daily_only"}))
            row.update(f)
            cand_rows.append(row)
        all_pts.extend(pts)
    rng["n_candidates"], rng["n_levels"] = len(cand_rows), len(levels_all)
    # the density check in RAW price (the $0.05 floor is a tick size): levels_all = (price_raw, day range raw, family, our_length)
    rng["density_all"] = density([(p, r) for p, r, _f, _o in levels_all], lo_raw, hi_raw)
    rng["density_no_our_length"] = density([(p, r) for p, r, _f, o in levels_all if not o], lo_raw, hi_raw)
    rng["density_core"] = density([(p, r) for p, r, fam, _o in levels_all if fam in CORE_SET], lo_raw, hi_raw)
    for key in ("density_all", "density_no_our_length", "density_core"):
        if rng[key] != "":
            rng[key] = round(rng[key], 4)
    # R30: readout arms for the narrowing decision (never a bar): each set without F10, and the §4.2 tolerance at 1/2 and 1/4
    sets = {"all": levels_all, "no_our_length": [x for x in levels_all if not x[3]], "core": [x for x in levels_all if x[2] in CORE_SET]}
    for name, lv in sets.items():
        rng[f"density_{name}_no_F10"] = density([(p, r) for p, r, fam, _o in lv if fam != "F10"], lo_raw, hi_raw)
        for sc, tag in ((0.5, "half"), (0.25, "quarter")):
            rng[f"density_{name}_{tag}"] = density([(p, r) for p, r, _f, _o in lv], lo_raw, hi_raw, sc)
            rng[f"density_{name}_no_F10_{tag}"] = density([(p, r) for p, r, fam, _o in lv if fam != "F10"], lo_raw, hi_raw, sc)
    rng["flags"] = "|".join(sorted(flags))
    return rng, cover, cand_rows


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the stages
# ═════════════════════════════════════════════════════════════════════════════════════════════
class Claims:
    """The dry run's checks against the inventory: every one printed; the RESULT line counts OK / MISMATCH (never tuned)."""

    def __init__(self, say):
        self.say, self.rows = say, []

    def __call__(self, label: str, expected, got, tol: float = 0.0) -> None:
        if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
            ok = abs(float(got) - float(expected)) <= tol
        else:
            ok = expected == got
        self.rows.append((label, expected, got, ok))
        self.say(f"  [{'OK' if ok else 'MISMATCH'}] {label}: expected {expected}, got {got}")

    def result(self) -> str:
        n, k = len(self.rows), sum(1 for r in self.rows if r[3])
        return f"RESULT: {n} claims, {k} OK, {n - k} MISMATCH"


def load_all(say, tally: collections.Counter) -> dict:
    t0 = time.time()
    for p in list(C.FILES.values()) + list(C.MINUTES.values()):
        C.checked(p)
    S = C.sealed_sessions()
    say(f"- calendar: {len(S.cal):,} sessions {S.cal[0]}..{S.cal[-1]} (the reader's cache, cut at {C.CUT_B})")
    frames = read_frames(C.FILES["snapshots"])
    say(f"- snapshots: {len(frames):,} frames, {sum(f.full for f in frames.values()):,} full")
    buys, sales, ent = read_windows(frames, S, tally)
    lex = C.load_lexicon()
    alias = C.load_alias(lex, tally)
    alias2 = C.extend_alias_renames(alias, lex, tally)
    say(f"- lexicon {len(lex):,} symbols; alias map {len(alias):,} (signature {tally['alias_signature']}, dedupe {tally['alias_dedupe']}); "
        f"rename table added {tally['alias_rename_table']} (R8)")
    for w in buys + sales:
        w.year = int(w.hi[:4])
        w.in_span = SPAN[0] <= w.hi <= SPAN[1]
        w.bracket = type_bracket(w, S)
        reachable(w, S)
        w.sym_a_orig = w.sym_a
        if w.sym in alias2 and w.sym_a == w.sym:
            w.sym_a = alias2[w.sym]
            tally[f"renamed_{w.side}"] += 1
    by_eid = {w.eid: w for w in buys}
    for w in sales:
        bw = by_eid.get(w.eid)
        if bw is not None:
            w.hold_min, w.hold_max = hold_sessions(bw, w, S)
    keep = {w.sym for w in buys + sales} | {w.sym_a for w in buys + sales} | set(alias2.values())
    dailies = {}
    for ex in ("A", "B"):
        t1 = time.time()
        d, info = C.load_daily_subset(C.checked(C.FILES[f"export_{ex}"]), keep=keep, cut=C.CUT_B)
        assert d.cal[-1].isoformat() <= C.CUT_B
        cal_iso = [x.isoformat() for x in d.cal]
        i0 = S.cal.index(cal_iso[0])
        assert S.cal[i0:i0 + len(cal_iso)] == cal_iso, f"export {ex} calendar differs from the reader's calendar on its span"
        dailies[ex] = d
        say(f"- export {ex}: {info['rows_read']:,} rows read, {info['rows_kept']:,} kept for {len(keep):,} names, {info['dated_after_cut']:,} "
            f"dated after the cut dropped at read; calendar {cal_iso[0]}..{cal_iso[-1]} = the reader's ({time.time() - t1:.0f}s)")
        tally[f"export_{ex}_rows_kept"] = info["rows_kept"]
        tally[f"export_{ex}_cut"] = info["dated_after_cut"]
    done, files = C.load_done_all()
    store = C.MinuteStore(done, files)
    say(f"- minute trees: " + ", ".join(f"{tr} {len(files[tr]):,} date files / {len(done[tr]):,} logged pairs" for tr in C.TREE_ORDER) +
        f"; date files after the seal left unopened: " + ", ".join(f"{tr} {n}" for tr, n in C.SEALED_FILES.items() if n))
    bars = Bars(dailies, store, S)
    for w in buys + sales:
        assign_export(w, bars, tally)
    t1 = time.time()
    rawmap, rinfo = C.load_raw_close_subset(C.checked(C.FILES["raw_close_A"]), keep={w.sym_a for w in buys + sales}, cut=C.CUT_B)
    splits, n_split_sealed = C.load_splits_sealed()
    say(f"- raw closes (R12): {rinfo['rows_read']:,} rows read, {rinfo['rows_kept']:,} kept for {rinfo['tickers']:,} of "
        f"{len({w.sym_a for w in buys + sales}):,} bar symbols, {rinfo['dated_after_cut']:,} dated after the cut dropped at read; split list "
        f"{sum(len(v) for v in splits.values()):,} splits of {len(splits):,} names to the seal, {n_split_sealed:,} after it dropped at read "
        f"({time.time() - t1:.0f}s)")
    tally["raw_tickers"], tally["splits_dropped_after_seal"] = rinfo["tickers"], n_split_sealed
    for w in buys + sales:
        raw_factors(w, bars, rawmap, splits, tally)
    panel = panel_pcts(C.FILES["panel"], {w.later.frame_id for w in buys} | {w.earlier.frame_id for w in sales})
    say(f"- panel: {panel['_counts']['panel_frames']:,} panel frames, {panel['_counts']['rows']:,} rows, {panel['_counts']['rows_with_pct']:,} with a % "
        f"read, {panel['_counts']['rows_pct_ok']:,} agreeing with the bars")
    say(f"- loaded in {time.time() - t0:.0f}s")
    return {"S": S, "frames": frames, "buys": buys, "sales": sales, "ent": ent, "lex": lex, "alias": alias2, "bars": bars, "panel": panel,
            "dailies": dailies, "store": store, "rawmap": rawmap, "splits": splits}


def preload_minutes(L: dict, say) -> None:
    pairs = set()
    for w in L["buys"] + L["sales"]:
        if w.wide or not w.reach:
            continue
        for d, _, _ in w.reach:
            pairs.add((d, w.bar_sym))
    t0 = time.time()
    st = L["store"].preload(sorted(pairs))
    say(f"- minutes preloaded: {len(pairs):,} (session, symbol) pairs -> " + ", ".join(f"{k} {v:,}" for k, v in sorted(st.items())) +
        f"; files read " + ", ".join(f"{k} {v}" for k, v in sorted(L["store"].reads.items())) + f" ({time.time() - t0:.0f}s)")


def inventory_coverage(w: Window, bars: Bars, S: Sessions, renamed: bool = False) -> tuple:
    """R23: the inventory's own coverage definition per window session: daily = A under sym_a OR B under sym; minute = any tree ok under the
    inventory's bar symbol. `renamed=False` uses entries.tsv's sym_a (the inventory's numbers, the claims); True the rename-extended one.
    -> (daily_all, daily_any, minute_all)."""
    lo_i, hi_i = S.le(w.lo), S.le(w.hi)
    ds = [S.date(i) for i in range(lo_i, hi_i + 1)]
    sym_a = w.sym_a if renamed else w.sym_a_orig
    inv_sym = C.bar_sym(w.hi, sym_a, w.sym)
    daily = [bars.has_daily("A", sym_a, d) or bars.has_daily("B", w.sym, d) for d in ds]
    minute = [bars.store.state(d, inv_sym).startswith("ok") for d in ds]
    return all(daily), any(daily), all(minute)


def compute_all(L: dict, say, tally: collections.Counter) -> dict:
    nr_all = collections.Counter()
    ranges, covers, cands = [], [], []
    t0 = time.time()
    for w in L["buys"] + L["sales"]:
        r, cv, cr = side_rows(w, L["bars"], L["panel"], L["S"], tally, nr_all)
        ranges.append(r)
        covers.append(cv)
        cands.extend(cr)
    say(f"- candidates built for {len(ranges):,} sides in {time.time() - t0:.0f}s: {len(cands):,} rows")
    return {"ranges": ranges, "covers": covers, "cands": cands, "not_reached": nr_all}


def report(L: dict, R: dict, say, claims: "Claims | None", tally: collections.Counter) -> None:
    S, buys, sales = L["S"], L["buys"], L["sales"]
    ent = L["ent"]
    say("\n## Population (data.md §0, §2.1, §2.3)")
    if claims:
        claims("positions (entries.tsv rows)", 1874, len(ent))
        claims("buy windows", 1861, len(buys))
        claims("sale windows", 1861, len(sales))
        claims("round trips (both windows)", 1848, len({w.eid for w in buys} & {w.eid for w in sales}))
        claims("initial holdings", 13, tally["initial"])
        claims("still held at the end", 13, tally["still_held"])
        claims("flickers", 659, tally["flicker"])
        claims("inverted buy windows", 34, tally["buy_inverted"])
        claims("inverted sale windows (recomputed)", 38, tally["sale_inverted"])
        claims("sale windows reproduced from snapshots.tsv", 1861, tally["exit_windows_reproduced"])
        claims("snapshots", 2907, len(L["frames"]))
        claims("full snapshots", 2082, sum(f.full for f in L["frames"].values()))
        claims("calendar sessions to 2024-12-31", 2264, len(S.cal))
        pc = L["panel"]["_counts"]
        claims("panel rows", 41099, pc["rows"])
        claims("panel rows with a % read", 39137, pc["rows_with_pct"])
        claims("panel rows agreeing with the bars", 34355, pc["rows_pct_ok"])
    say("\n## Counts by year (year of the window end)")
    years = [2017, 2018, 2019, 2020, 2021, 2022, 2023]
    exp_buy = {2017: 81, 2018: 16, 2019: 198, 2020: 803, 2021: 583, 2022: 132, 2023: 48}
    exp_sale = {2017: 46, 2018: 48, 2019: 184, 2020: 814, 2021: 589, 2022: 139, 2023: 41}
    rows = []
    for side, ws, exp in (("buys", buys, exp_buy), ("sales", sales, exp_sale)):
        cnt = collections.Counter(w.year for w in ws)
        rows.append([side] + [cnt.get(y, 0) for y in years] + [len(ws)])
        if claims:
            claims(f"{side} by year 2017..2023", [exp[y] for y in years], [cnt.get(y, 0) for y in years])
    table(say, ["side"] + [str(y) for y in years] + ["total"], rows)
    say("\n## Primary span (window end 2020-01-01..2022-06-30) — data.md §3, plan §3.1")
    bs, ss = [w for w in buys if w.in_span], [w for w in sales if w.in_span]
    if claims:
        claims("buys in span", 1511, len(bs))
        claims("sales in span", 1538, len(ss))
        claims("flicker buys in span", 565, sum(w.flicker for w in bs))
        claims("flicker sales in span", 567, sum(w.flicker for w in ss))
        claims("inverted buys in span", 21, sum(w.inverted for w in bs))
        claims("inverted sales in span", 26, sum(w.inverted for w in ss))
    say("\n## Bracket types (data.md §2.5; the plan's §3.2 rows with `other` split as the inventory's two rows) — R28 / R32: the claims are the"
        " IN-SPAN vectors, the in-span bracket_other and the all-years sum other + 6+; the all-years split is a readout")
    exp_b = {"same_in_in": (338, 289), "same_pre_in": (436, 271), "same_other": (31, 35), "next_in_pre": (318, 490), "next_in_in": (64, 81),
             "next_other": (73, 39), "sessions_2_5": (353, 395), "sessions_6plus": (248, 261)}
    exp_span = {"same_in_in": (301, 252), "same_pre_in": (400, 252), "same_other": (21, 26), "next_in_pre": (305, 460), "next_in_in": (44, 74),
                "next_other": (62, 35), "sessions_2_5": (287, 341), "sessions_6plus": (91, 98)}
    cb_, cs_ = collections.Counter(w.bracket for w in buys), collections.Counter(w.bracket for w in sales)
    # the inventory types the inverted windows by their frames (they sit inside its two `other` rows): count them that way for the claims
    cb_inv = collections.Counter(type_bracket_frames(w, S) for w in buys)
    cs_inv = collections.Counter(type_bracket_frames(w, S) for w in sales)
    cb_sp = collections.Counter(type_bracket_frames(w, S) for w in buys if w.in_span)
    cs_sp = collections.Counter(type_bracket_frames(w, S) for w in sales if w.in_span)
    rows = [[BRACKET_WORDS[b], cb_inv.get(b, 0), exp_b[b][0], cb_sp.get(b, 0), exp_span[b][0], cs_inv.get(b, 0), exp_b[b][1], cs_sp.get(b, 0), exp_span[b][1]]
            for b in exp_b]
    rows.append(["inverted (plan's row; inside the inventory's `other` rows)", cb_.get("inverted", 0), 34, sum(w.inverted for w in bs), 21,
                 cs_.get("inverted", 0), 38, sum(w.inverted for w in ss), 26])
    table(say, ["bracket (frames)", "buys", "inventory", "buys span", "inventory", "sales", "inventory", "sales span", "inventory"], rows)
    oth = ("same_other", "next_other", "sessions_6plus")
    say(f"- all-years other + 6+ (buys): build {[cb_inv.get(b, 0) for b in oth]} vs inventory {[exp_b[b][0] for b in oth]}; sales build "
        f"{[cs_inv.get(b, 0) for b in oth]} vs inventory {[exp_b[b][1] for b in oth]} — the split differs by "
        f"{cb_inv.get('same_other', 0) + cb_inv.get('next_other', 0) - 31 - 73} buys / {cs_inv.get('same_other', 0) + cs_inv.get('next_other', 0) - 35 - 39} "
        f"sales, all OUTSIDE the span (R28: 2017-19 Sunday frames and pre -> pre pairs); the in-span column agrees on every row")
    if claims:
        claims("buys by bracket type, in span (inventory typing)", [exp_span[b][0] for b in exp_b], [cb_sp.get(b, 0) for b in exp_b])
        claims("sales by bracket type, in span (inventory typing)", [exp_span[b][1] for b in exp_b], [cs_sp.get(b, 0) for b in exp_b])
        claims("buys by bracket type, all years, the six undisputed rows", [exp_b[b][0] for b in exp_b if b not in oth], [cb_inv.get(b, 0) for b in exp_b if b not in oth])
        claims("sales by bracket type, all years, the six undisputed rows", [exp_b[b][1] for b in exp_b if b not in oth], [cs_inv.get(b, 0) for b in exp_b if b not in oth])
        claims("buys all years, other + 6+ together", 31 + 73 + 248, sum(cb_inv.get(b, 0) for b in oth))
        claims("sales all years, other + 6+ together", 35 + 39 + 261, sum(cs_inv.get(b, 0) for b in oth))
        claims("bracket_other buys in span (inventory's in-span other rows 21 + 62 less the 21 inverted)", 62,
               sum(1 for w in bs if w.bracket in ("same_other", "next_other")))
        claims("bracket_other sales in span (inventory's in-span other rows 26 + 35 less the 26 inverted)", 35,
               sum(1 for w in ss if w.bracket in ("same_other", "next_other")))
        say(f"- (readout, not a claim) all-years bracket_other: buys {cb_.get('same_other', 0) + cb_.get('next_other', 0)} / plan §3.2 70, sales "
            f"{cs_.get('same_other', 0) + cs_.get('next_other', 0)} / plan §3.2 36 — the plan's figures are the inventory's inconsistent split less "
            "the inverted (R28); the main loop decides whether the plan's table is corrected")
    say("\n## Same-day bracket widths in minutes (data.md §2.5)")
    rows = []
    for side, ws in (("BUY", buys), ("SALE", sales)):
        for b in ("same_in_in", "same_pre_in"):
            sel = [w for w in ws if w.bracket == b]
            widths, nonpos = [], 0
            for w in sel:
                ma, mb = clock_minute(w.earlier.clock), clock_minute(w.later.clock)
                if ma is None or mb is None:
                    continue
                if b == "same_pre_in":
                    ma = 0
                wd = mb - ma
                if wd <= 0:
                    nonpos += 1
                else:
                    widths.append(wd)
            med = statistics.median(widths) if widths else ""
            rows.append([side, BRACKET_WORDS[b], len(sel), nonpos, med])
            if claims and med != "":
                claims(f"{side} {b} median width (min; tolerance 1: the inventory prints integer medians, R36)",
                       {"BUYsame_in_in": 31, "BUYsame_pre_in": 38, "SALEsame_in_in": 31, "SALEsame_pre_in": 44}[side + b], med, tol=1.0)
    table(say, ["side", "bracket", "n", "width <= 0", "median width"], rows)
    say("\n## Coverage in the span, the inventory's definitions (data.md §3.1-3.2; before the rename extension these are the claims)")
    bars = L["bars"]
    rows = []
    for side, ws, exp_d, exp_m, exp_none, exp_d1, exp_m1 in (("BUY", bs, 88.7, 70.4, 168, 91.3, 76.0), ("SALE", ss, 88.8, 60.5, 172, 89.9, 64.9)):
        cov = [inventory_coverage(w, bars, S) for w in ws]
        d_all = sum(c[0] for c in cov)
        d_none = sum(1 for c in cov if not c[1])
        m_all = sum(c[2] for c in cov)
        one = [c for w, c in zip(ws, cov) if S.le(w.hi) == S.le(w.lo)]
        rows.append([side, len(ws), pct(d_all, len(ws)), d_none, pct(m_all, len(ws)), len(one), pct(sum(c[0] for c in one), len(one)), pct(sum(c[2] for c in one), len(one))])
        if claims:
            claims(f"{side} every session has a daily bar (%)", exp_d, round(100.0 * d_all / len(ws), 1), tol=0.15)
            claims(f"{side} no session has a daily bar", exp_none, d_none)
            claims(f"{side} every session has minute bars (%)", exp_m, round(100.0 * m_all / len(ws), 1), tol=0.15)
            claims(f"{side} width-1 daily (%)", exp_d1, round(100.0 * sum(c[0] for c in one) / len(one), 1), tol=0.15)
            claims(f"{side} width-1 minute (%)", exp_m1, round(100.0 * sum(c[2] for c in one) / len(one), 1), tol=0.15)
    table(say, ["side", "n", "daily all sessions", "daily none", "minute all sessions", "width-1 n", "width-1 daily", "width-1 minute"], rows)
    say(f"- the rename table (R8) re-pointed {tally['renamed_buy']} buy and {tally['renamed_sale']} sale windows (GSX -> GOTU, SBE -> CHPT); "
        "after it (span):")
    rows = []
    for side, ws in (("BUY", bs), ("SALE", ss)):
        cov = [inventory_coverage(w, bars, S, renamed=True) for w in ws]
        rows.append([side, len(ws), pct(sum(c[0] for c in cov), len(ws)), sum(1 for c in cov if not c[1]), pct(sum(c[2] for c in cov), len(ws))])
    table(say, ["side", "n", "daily all sessions", "daily none", "minute all sessions"], rows)
    covers = R["covers"]
    say("\n## Coverage of the REACHABLE sets, this read's export rule (R23), by year and resolution")
    rows = []
    for side in ("buy", "sale"):
        for y in years + ["span"]:
            sel = [c for c in covers if c["side"] == side and ((c["in_span"]) if y == "span" else c["year"] == y)]
            if not sel:
                continue
            cnt = collections.Counter(c["resolution"] for c in sel)
            rows.append([side, y, len(sel), cnt.get("minute", 0), cnt.get("partial", 0), cnt.get("daily_only", 0), cnt.get("none", 0),
                         sum(1 for c in sel if c["daily_only_reason"] == "wide_window"), sum(1 for c in sel if c["export_fallback"])])
    table(say, ["side", "year", "n", "minute", "partial", "daily_only", "none", "of which wide", "export fallback"], rows)
    say(f"- windows straddling {C.A_LAST} (the export split): {tally['windows_straddle_A_LAST']}; export fallbacks {tally['export_fallback']}")
    say("\n## Coverage by bracket type (span)")
    rows = []
    for b in BRACKETS:
        for side in ("buy", "sale"):
            sel = [c for c in covers if c["side"] == side and c["in_span"] and c["bracket"] == b]
            cnt = collections.Counter(c["resolution"] for c in sel)
            rows.append([BRACKET_WORDS[b], side, len(sel), cnt.get("minute", 0), cnt.get("partial", 0), cnt.get("daily_only", 0), cnt.get("none", 0)])
    table(say, ["bracket", "side", "n", "minute", "partial", "daily_only", "none"], rows)
    say("\n## The reachable band (bars only), span, sides with a range")
    ranges = R["ranges"]
    rows = []
    for side in ("buy", "sale"):
        for res in ("minute", "partial", "daily_only"):
            sel = [r for r in ranges if r["side"] == side and r["in_span"] and r["resolution"] == res and r["range_width_pct"] != ""]
            if not sel:
                continue
            ws_ = sorted(r["range_width_pct"] for r in sel)
            rows.append([side, res, len(sel), round(statistics.median(ws_), 2), round(ws_[len(ws_) // 4], 2), round(ws_[3 * len(ws_) // 4], 2),
                         sum(1 for r in sel if r["panel_outside_range"] is True), sum(1 for r in sel if r["panel_price"] != "")])
    table(say, ["side", "resolution", "n", "median width %", "q1", "q3", "panel outside", "panel priced"], rows)
    zero = [r for r in ranges if r["in_span"] and r["range_lo"] != "" and r["range_lo"] == r["range_hi"]]
    say(f"- sides whose reachable range has zero width (one print; density reads 1.0 by construction): {len(zero)}")
    say(f"- panel price inside / outside the bars-only range, ALL YEARS: buys {tally['panel_buy_inside']} / {tally['panel_buy_outside']}, "
        f"sales {tally['panel_sale_inside']} / {tally['panel_sale_outside']}; IN SPAN: buys {tally['panel_buy_inside_span']} / "
        f"{tally['panel_buy_outside_span']}, sales {tally['panel_sale_inside_span']} / {tally['panel_sale_outside_span']}; outside by the "
        "frame's clock context, all years (side:ctx): " + ", ".join(
        f"{k[1]} {v}" for k, v in sorted((k, v) for k, v in tally.items() if isinstance(k, tuple) and k[0] == "panel_outside_ctx")))
    say("\n## Raw price (R12 / R31): the bars are split-adjusted to 2026; each session's factor = raw close / the record's own export close")
    rows = []
    for side in ("buy", "sale"):
        sel = [r for r in ranges if r["side"] == side and r["in_span"] and r["raw_source"] != ""]
        src = collections.Counter(r["raw_source"] for r in sel)
        off = sum(1 for r in sel if abs(float(r["raw_factor"]) - 1.0) > 0.02)
        rows.append([side, len(sel)] + [src.get(k, 0) for k in RAW_SOURCES] + [off, sum(1 for r in sel if "split_inside_window" in r["flags"])])
    table(say, ["side", "sides with a range (span)", "exact", "carried", "partial", "missing", "factor off by > 2%", "split inside the window"], rows)
    say("- sessions by raw source, all years: " + ", ".join(f"{side} {src} {tally[('raw_source', side, src)]:,}" for side in ("buy", "sale") for src in RAW_SOURCES
                                                              if tally[("raw_source", side, src)]))
    rawmap = L["rawmap"]
    if claims:
        def raw_close_of(tk, d):
            rw = rawmap.get(tk)
            if rw is None or d not in rw[0]:
                return ""
            return round(float(rw[1][rw[0].index(d)]), 2)
        claims("raw close NVDA 2020-10-21 (review F2's hand-check)", 540.99, raw_close_of("NVDA", "2020-10-21"))
        nv = [r for r in ranges if r["sym"] == "NVDA" and r["range_lo"] != "" and r["lo"] <= "2020-10-21" <= r["hi"]]
        if nv:
            claims("NVDA window holding 2020-10-21: raw factor (the 4:1 of 2021 x the 10:1 of 2024; tolerance 0.05, the bars are cent-rounded)",
                   40.0, round(float(nv[0]["raw_factor"]), 2), tol=0.05)
        sbe = [r for r in ranges if r["sym"] == "SBE" and r["range_lo"] != "" and r["lo"][:7] == "2020-12"]
        if sbe:
            claims("SBE Dec-2020 range in raw price lands under $100 (CHPT's 2025 1:20 reverse split undone)", True, float(sbe[0]["range_hi_raw"]) < 100)
    unk = collections.Counter((r["sym"], r["raw_source"]) for r in ranges if r["in_span"] and r["raw_source"] in ("partial", "missing"))
    say("- in-span sides with a range whose factor is NOT exact or carried (names absent from the raw file; `partial` = the listed splits to the "
        "seal only, `missing` = no raw row and no listed split, factor 1.0 assumed): " + (", ".join(f"{s} {src} x{n}" for (s, src), n in sorted(unk.items())) or "none"))
    say("\n## Candidates per side (span), by bracket type and resolution — plan §3.5 expected 5-15 bracketed, 15-30 unbracketed one-session")
    rows = []
    for b in BRACKETS:
        for side in ("buy", "sale"):
            sel = [r for r in ranges if r["side"] == side and r["in_span"] and r["bracket"] == b and r["resolution"] != "none" and r["resolution"] != ""]
            if not sel:
                continue
            ns = sorted(r["n_candidates"] for r in sel)
            rows.append([BRACKET_WORDS[b], side, len(sel), ns[len(ns) // 2], ns[len(ns) // 4], ns[3 * len(ns) // 4], sum(ns)])
    table(say, ["bracket", "side", "n", "median rows", "q1", "q3", "total rows"], rows)
    cands = R["cands"]
    span_eids = {(r["eid"], r["side"]) for r in ranges if r["in_span"]}
    n_span = sum(1 for c in cands if (c["eid"], c["side"]) in span_eids)
    say(f"- candidate rows: {len(cands):,} all years, {n_span:,} in the span (plan §3.5 guessed 30,000-55,000 in the span)")
    say("\n## Candidates per family (merged rows count a family once per row), span")
    fam = collections.Counter()
    for c in cands:
        if (c["eid"], c["side"]) not in span_eids:
            continue
        for tag in c["families"].split("+"):
            fam[(c["side"], tag.split("(")[0].split(":")[0])] += 1
    rows = [[f, fam.get(("buy", f), 0), fam.get(("sale", f), 0)] for f in FAMILY_ORDER]
    table(say, ["family", "buys", "sales"], rows)
    say("\n## Levels never reached inside the reachable set (not_reached: the level existed and was never traded through; beside it no_level: "
        "the level did not exist — too short a history for F7 / F8, no opening bars for F2), all years")
    nr = R["not_reached"]
    agg, nolv = collections.Counter(), collections.Counter()
    for k, v in nr.items():
        if k.startswith("no_level:"):
            nolv[k.split(":")[1]] += v
        else:
            agg[k.split(":")[0]] += v
    table(say, ["family", "not reached", "no level"], [[f, agg.get(f, 0), nolv.get(f, 0)] for f in FAMILY_ORDER])
    say("\n## DENSITY CHECK (plan §3.3): median share of a side's reachable range covered by the candidates' tolerance, per family set")
    rows = []
    verdicts = {}
    for key, name in (("density_all", "all families"), ("density_no_our_length", "without our_length"), ("density_core", "F1+F3+F4+F6+F10+F11")):
        for side in ("buy", "sale", "both"):
            sel = [r[key] for r in ranges if r["in_span"] and r[key] != "" and (side == "both" or r["side"] == side)]
            if not sel:
                continue
            med = statistics.median(sel)
            verdict = "NOT DECIDABLE" if med > DENSITY_LINE else "readable"
            if side == "both":
                verdicts[name] = (med, verdict)
            rows.append([name, side, len(sel), round(med, 3), round(sorted(sel)[len(sel) // 4], 3), round(sorted(sel)[3 * len(sel) // 4], 3), verdict])
    table(say, ["family set", "side", "n", "median share", "q1", "q3", "verdict (> 60% = not decidable)"], rows)
    say("\n## DENSITY READOUTS for the narrowing decision (R30; §3.3 says the tolerance is narrowed or the set thinned, decided then and recorded "
        "in the ledger): median share, both sides, span")
    rows = []
    for name, words in (("all", "all families"), ("no_our_length", "without our_length"), ("core", "F1+F3+F4+F6+F10+F11")):
        for arm, key in (("§4.2 tolerance", f"density_{name}"), ("without F10", f"density_{name}_no_F10"), ("tolerance / 2", f"density_{name}_half"),
                         ("without F10, tolerance / 2", f"density_{name}_no_F10_half"), ("tolerance / 4", f"density_{name}_quarter"),
                         ("without F10, tolerance / 4", f"density_{name}_no_F10_quarter")):
            sel = [r[key] for r in ranges if r["in_span"] and r.get(key, "") != ""]
            if sel:
                med = statistics.median(sel)
                rows.append([words, arm, len(sel), round(med, 3), "NOT DECIDABLE" if med > DENSITY_LINE else "readable"])
    table(say, ["family set", "arm", "n", "median share", "verdict at 60%"], rows)
    say("- by resolution (both sides, all families): " + ", ".join(
        f"{res} {round(statistics.median([r['density_all'] for r in ranges if r['in_span'] and r['resolution'] == res and r['density_all'] != '']), 3)}"
        for res in ("minute", "partial", "daily_only") if any(r["in_span"] and r["resolution"] == res and r["density_all"] != "" for r in ranges)))
    say("\n## DENSITY VERDICT (both sides, span): " + "; ".join(f"{k}: {v[1]} (median {v[0]:.1%})" for k, v in verdicts.items()))
    say("\n## Beside: 2017-2019 and 2023, the initial 13 and the still-held 13 — run, never in a bar")
    say(f"- sides outside the span: {sum(1 for r in ranges if not r['in_span']):,}; with a range {sum(1 for r in ranges if not r['in_span'] and r['range_lo'] != ''):,}")
    say(f"- excluded names (no daily bar on any session, span): " + ", ".join(
        f"{s} {n}" for s, n in collections.Counter(r["sym"] for r in ranges if r["in_span"] and r["resolution"] == "none").most_common(24)))
    say("\n## Flags over the sides (all years)")
    fl = collections.Counter()
    for r in ranges:
        for f in r["flags"].split("|"):
            if f:
                fl[(r["side"], f)] += 1
    table(say, ["flag", "buys", "sales"], [[f, fl.get(("buy", f), 0), fl.get(("sale", f), 0)] for f in sorted({k[1] for k in fl})])


def type_bracket_frames(w: Window, S: Sessions) -> str:
    """The inventory's typing (by the frames alone; an inverted window is typed by its frames too)."""
    inv = w.inverted
    w.inverted = False
    try:
        return type_bracket(w, S)
    finally:
        w.inverted = inv


def write_tsv(rows: list, cols: list, path: str) -> None:
    pd.DataFrame(rows, columns=cols).to_csv(path + ".partial", sep="\t", index=False)
    os.replace(path + ".partial", path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--print-pins", action="store_true")
    g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    if a.print_pins:
        lines = [f"{k}\t{v}" for k, v in C.pins().items()]
        print("\n".join(lines))
        with open(C.P_PINS, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"(written to {C.P_PINS})")
        return 0
    say = Say()
    tally = collections.Counter()
    stage = "DRY RUN" if a.dry_run else "RUN"
    say(f"# #705 as-is STEP 5 — {stage} ({time.strftime('%Y-%m-%d %H:%M')})")
    say("Guards: no network, no production server, no paid call, nothing after 2024-12-31, the seven outcome folders never opened, nothing "
        "imported from the rule folders (asis_common copies). No rule, setup name or pattern label enters.")
    refused_to = C.P_DRY if a.dry_run else C.P_REFUSED      # R34: a refused --run never writes 01_points.txt
    hits = C.scan_identifiers([os.path.join(HERE, "asis_common.py"), os.path.join(HERE, "01_points.py")])
    if hits:
        say("IDENTIFIER SCAN FAILED: " + "; ".join(f"{os.path.basename(p)}:{ln} {t}" for p, ln, t in hits))
        say.write(refused_to)
        return 2
    say("- identifier scan: clean (the step-5 modules hold none of the excluded names)")
    loaded = C.rule_modules_loaded()
    if loaded:
        say("RULE MODULE LOADED (guard 3): " + ", ".join(loaded))
        say.write(refused_to)
        return 2
    say("- import belt: no rule module in sys.modules")
    say("- modules: " + module_shas_line())                   # R34: --run refuses when the dry run was made by other code than this
    say("- build history (R34): " + " | ".join(BUILD_HISTORY))
    if a.run:
        problems = run_gate()
        if problems:
            for pr in problems:
                say("REFUSED: " + pr)
            say.write(C.P_REFUSED)
            return 3
        say("- run gates: the dry run completed with 0 MISMATCH; every pin (inputs, modules, doc body, the dry-run printout) is below the doc's "
            "freeze marker; the ledger verifies; no output exists")
    say("\n## Inputs")
    L = load_all(say, tally)
    preload_minutes(L, say)
    R = compute_all(L, say, tally)
    claims = Claims(say) if a.dry_run else None
    report(L, R, say, claims, tally)
    if a.dry_run:
        say("")
        say(claims.result())
        say("DRY RUN COMPLETE")
        say.write(C.P_DRY)
        return 0
    os.makedirs(C.OUT_DIR, exist_ok=True)
    write_tsv(R["cands"], CAND_COLS, C.OUTPUTS["candidates"])
    write_tsv(R["ranges"], RANGE_COLS, C.OUTPUTS["ranges"])
    write_tsv(R["covers"], COVER_COLS, C.OUTPUTS["coverage"])
    say("\n## Outputs")
    for k, p in C.OUTPUTS.items():
        say(f"- {k}: {p} ({C.sha(p)[:16]})")
    say("RUN COMPLETE")
    say.write(C.P_RUN)
    C.ledger_append("step5_dry_run", C.P_DRY)       # R34: the dry-run printout this run was frozen on, then the run itself
    C.ledger_append("step5_points", C.P_RUN)
    for k, p in C.OUTPUTS.items():
        C.ledger_append(f"step5_{k}", p)
    return 0


MODULE_FILES = ("asis_common.py", "01_points.py", "forbidden_identifiers.txt")


def module_shas_line() -> str:
    """'asis_common.py <sha16> 01_points.py <sha16> forbidden_identifiers.txt <sha16>' of the files as they are now."""
    return " ".join(f"{n} {C.sha(os.path.join(HERE, n))[:16]}" for n in MODULE_FILES)


def dry_run_modules_line(path: str = None) -> "str | None":
    """The '- modules:' line of the dry-run printout (None when absent: a dry run made before the line existed, or a stopped one)."""
    path = path or C.P_DRY
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("- modules: "):
                return ln[len("- modules: "):].strip()
    return None


def dry_run_mismatches(path: str = None) -> "int | None":
    """The MISMATCH count of the dry run's RESULT line (None when the line is absent): R34, a mismatching dry run also ends COMPLETE."""
    path = path or C.P_DRY
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("RESULT:"):
                try:
                    return int(ln.split("MISMATCH")[0].strip().split()[-1])
                except (ValueError, IndexError):
                    return None
    return None


def run_gate(doc: str = None) -> list:
    """R34: the reasons a --run is refused (empty = go). The dry run complete with 0 MISMATCH; every input / module / doc-body pin AND the
    dry-run printout's pin pasted below the doc's freeze marker; the ledger (if any) verifying; no output present."""
    problems = []
    if not C.dry_run_complete():
        problems.append("the dry run has not completed (01_points_dryrun.txt)")
    else:
        mm = dry_run_mismatches()
        if mm is None:
            problems.append("the dry run's RESULT line is missing or unreadable")
        elif mm > 0:
            problems.append(f"the dry run ended with {mm} MISMATCH")
        ml = dry_run_modules_line()
        if ml != module_shas_line():
            problems.append("the dry run was made by other code than the modules on disk (or carries no module line): rerun --dry-run first"
                            + (f" (dry run: {ml})" if ml else ""))
    p = C.pins(doc, include_outputs=False)
    p["dryrun_printout"] = C.sha(C.P_DRY) if os.path.exists(C.P_DRY) else "ABSENT"
    miss = C.freeze_missing(doc or C.DOC, p)
    if miss:
        problems.append("pins not below the doc's freeze marker (freeze first, --print-pins, paste): " + ", ".join(miss))
    bad = C.ledger_verify() if os.path.exists(C.LEDGER) else []
    if bad:
        problems.append("ledger: " + "; ".join(bad))
    existing = [q for q in list(C.OUTPUTS.values()) + [C.P_RUN] if os.path.exists(q)]
    if existing:
        problems.append("outputs exist: " + ", ".join(existing))
    return problems


if __name__ == "__main__":
    sys.exit(main())
