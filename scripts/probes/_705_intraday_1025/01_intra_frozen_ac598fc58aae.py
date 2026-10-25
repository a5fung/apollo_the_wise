#!/usr/bin/env python3
"""#705 — INTRADAY 01: his 1-minute / 30-minute opening-range entries, intraday stops and the 60-minute exit, read on his panel trades
(docs/analysis/cb_intraday_layer_prereg_2026-10-25.md). REGISTERED, NOT FROZEN, NOT RUN. Built to execution depth; every fit stage
writes ONCE; the check runs ONCE after the freeze.

The FROZEN previous module (`scripts/probes/_705_reverse_1024/01_rev_frozen_e908253f7405.py`, sha pinned below, refused on drift) is
imported read-only, and through it the frozen holdings replay, the second and first reads, the runner and the cb module. Nothing in them is
edited. Reused read-only where they fit: `load_core` (the buys, the clocks, the calendar, the types, the sets), `population_claims` (the
previous registration's 63 composition counts), `score_level`, `random_levels`, `enter_levels` (L1-L6 re-reads), `registered_fill`,
`stop_levels` (S1 / S3 / S8 / the 50-day), `level_at`, `sma_series`, `Sightings`, `speed_trail_trade`, `panel_trade`, `make_simple_trade`,
`recovery`, `break_horizon`, `day0_for`, the caption chain, the freeze-lock helpers, and the runner's `h60_windows` / `h60_trim` /
`H60_EARLY_CLOSE`. NOT reused for any number: the frozen `held_through` (the OLD certainty rule; it runs only inside known-answer gate (iv)),
the frozen `Rec` / `make_rec` / `bars_of` / `smas_for` (the era-B calendar mix and the identity-keyed caches): this module builds its own record
type with ONE calendar per record (§11c) and one `IdCache` (§11d).

STAGES (the registration's §12)
  --dry-run     loads every input; re-runs the previous registration's 63 counts; asserts every count of §2 / §2a-d / §11 of THIS doc
                (every mismatch printed, then STOP); lists every window §2c drops by name; the data gate on the fetch list (coverage per
                block from the fetch logs ONLY — no minute file opened; the pending pairs written); the era-B offsets on each record's own
                calendar; from clocks alone, the records with S9 != S1 and S10 != S1; the record builder on the fixed sets; guard (5) on the
                real fit sets; the FSLY-693 identity; the pins. Computes NO outcome: no bar after a buy day, no stop / exit / R, no fit.
  --enter-fit   §5 on the 2020 in-session windows after §2c (31 dated + 59 undated non-flicker decide; flickers beside); the two
                controls; gates (i), (ii), (iv). Writes once; prints `CHOSEN ENTER: ...`.
  --stop-fit    §6 on dated 2020 + undated 2020 under the chain's fill; 12 cells + the controls under T / C / H with the buy-day certainty
                rule; the risk under every cell; gates (i), (iii), (iv), (vi). Writes once; prints `CHOSEN STOP: ...`.
  --exit-fit    §7 on dated 2020: E1-E4 on the clock-anchored 60-minute 20-EMA (seeded on the first 20 bars of the 10-session warm-up;
                `ema_thin` unless 20 seed + 45 post-seed bars = 65 stand before the first armed bar); the hit rates; the 2020 accounts for
                scale; gate (i). Writes once; prints `CHOSEN EXIT: ...`.
  --print-pins  (also --pins) the pins to paste under the doc's freeze marker line; prints unconditionally.
  --check       ONCE: refuses unless every pin sits under the marker, exactly one `CHOSEN <STAGE>: ` line per stage stands above it at
                column 0 and equals the fit printout's, every fit printout exists, the check printout does not, the ledger matches the disk,
                the body above the marker differs from the freeze commit's only in the three keyed lines, AND the freeze body and the module
                sha recorded by each of the three fit stages equal the pin under the marker and this file; copies the module beside the
                pins; then ENTER (2021-22 undated non-flicker decide; the virgin 9 veto by sign; the random-price control's known answer on
                the previous 41 undated windows), STOP (the 62 undated untouched decide), EXIT (dated 2021-22 decide; the virgin dated
                veto by sign), the sealed test's branch, WHY-lite's 10-row sheet.
  --why-rates   after the hand read is filed in the sheet (`verdict` column): the precision gate and the 60-minute-close share.
  --reset-fits "<reason>"   §12's recovery (N2): after a fit stage or the check STOPPED once an earlier fit ran, and the fix is in the code,
                moves every artifact (printouts, chosen files, ledger, STOPPED, the dry run's printout, intraday/ files, module copies) to
                verify/fit_events/<event>/ with a manifest — copied and verified before any original leaves its place; never deletes. Then
                the dry run, ALL three fits on a fresh ledger, and `fit_event_<event>` pinned under the marker (--check refuses until it is).

Guard (5) is per TRADE and per (bar symbol, date): a fit stage opens no bar after the buy day of a trade outside its fit set, and no bar on a
(symbol, session) that lies after the buy day of ANY check-side trade (buy day + 1 .. exit_hi + 20; a still-held trade: its last frame + 20).
A fit trade whose planned span — from the daily lookback the stage reads (ENTER 20 sessions before the buy day; STOP / EXIT 50) to the last
session a walk can book on (ENTER the buy day; STOP exit_hi + 1; EXIT exit_hi + 21) — touches such a pair is EXCLUDED from that fit stage by
dates alone, named and counted (the dry run lists them; N1 / N3); the per-date refusal is the belt, on the pre-buy lookback by bar index too.
The frozen speed trail's 121-session forward window is bounded before the first forbidden session in a fit stage (X1, `guard_bound_guards`).

No subagent, no DB, no network, no ssh, no docker. Read-only on every input. Nothing dated after 2024-12-31 is read from any file (every
minute date is asserted at read — guard 12); nothing of 2025-26 is opened. Guard (9): `replay/` and `his_exits/` are opened by NO stage.
Run:  python3 scripts/probes/_705_intraday_1025/01_intra.py --dry-run
"""
from __future__ import annotations

import argparse
import bisect
import datetime as _dt
import glob
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
REV_DIR = os.path.join(REPO, "scripts", "probes", "_705_reverse_1024")
REV_FROZEN = os.path.join(REV_DIR, "01_rev_frozen_e908253f7405.py")
REV_FROZEN_SHA = "e908253f7405f814351ced03bd61a80b7886268bcee366f70f66c4a5f74aaeff"      # the previous read's freeze record (rev_module)


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_frozen_rev():
    got = sha(REV_FROZEN)
    if got != REV_FROZEN_SHA:
        raise SystemExit(f"REFUSED: the frozen previous module is not the frozen one ({got} vs {REV_FROZEN_SHA})")
    return _load_module("_705_rev_frozen_intra", REV_FROZEN)


rev = _load_frozen_rev()
H, ex, rp, R, cb = rev.H, rev.ex, rev.rp, rev.R, rev.cb
GuardStop = rev.GuardStop

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths, pins
# ═════════════════════════════════════════════════════════════════════════════════════════════
DATA, A_DIR, B_DIR = rev.DATA, rev.A_DIR, rev.B_DIR
H_DIR = rev.H_DIR
REV_OUT = rev.OUT_DIR                                   # holdings_1024/reverse — the previous read's outputs, READ here (gate iv, the daily list)
OUT_DIR = f"{H_DIR}/intraday"
FREEZE_BODIES = f"{OUT_DIR}/freeze_bodies"
INTRA_MIN = f"{B_DIR}/minutes_intra_1025"
FETCH_LIST = f"{INTRA_MIN}/fetch_list_intra_1025.psv"
DOC = os.path.join(REPO, "docs", "analysis", "cb_intraday_layer_prereg_2026-10-25.md")
STAGES = ("enter", "stop", "exit")
P_DRY = os.path.join(HERE, "01_intra_dryrun.txt")
P_PINS = os.path.join(HERE, "01_intra_pins.txt")
P_FIT = {s: os.path.join(HERE, f"01_intra_{s}_fit.txt") for s in STAGES}
P_CHECK = os.path.join(HERE, "01_intra_check.txt")
P_WHY = os.path.join(HERE, "01_intra_why.txt")
LEDGER = os.path.join(HERE, "01_intra_ledger.tsv")
STOPPED = os.path.join(HERE, "01_intra.STOPPED.txt")
FROZEN_DIR = HERE                                         # --check copies the module here (guard 2)
FIT_EVENTS = os.path.join(HERE, "verify", "fit_events")  # N2: --reset-fits moves a stopped run's artifacts here, one folder per event (never deleted)
WHY_SHEET = f"{OUT_DIR}/why_sheet_h60_2020.tsv"
POP_SCRIPT = os.path.join(HERE, "00_pop_fetch.py")
POP_PRINTOUT = os.path.join(HERE, "00_pop_fetch.txt")
FORBIDDEN_DIRS = rev.FORBIDDEN_DIRS                     # guard (9): replay/ and his_exits/ — never opened, by any stage, for any name

FILES = {**rev.FILES,
         "fetch_list_intra": FETCH_LIST,
         "pop_fetch_script": POP_SCRIPT, "pop_fetch_printout": POP_PRINTOUT,
         "rev_frozen_module": REV_FROZEN,
         "rev_enter_fit_trades": f"{REV_OUT}/enter_fit_trades.tsv",        # gate (iv): the previous fit's rows, re-read row for row
         "rev_stop_fit_trades": f"{REV_OUT}/stop_fit_trades.tsv",
         "rev_exit_fit_chosen": f"{REV_OUT}/exit_fit_chosen.json",         # the previous daily exit list (the hit-rate benchmark, beside)
         "rev_check_printout": os.path.join(REV_DIR, "01_rev_check.txt")}
if os.path.exists(f"{INTRA_MIN}/_done.psv"):
    FILES["done_INTRA"] = f"{INTRA_MIN}/_done.psv"
CODE = {"intra_module": os.path.abspath(__file__), "intra_tests": os.path.join(HERE, "test_01_intra.py")}
MINUTES = {**rev.MINUTES, "INTRA": INTRA_MIN}
PINNED = {"fetch_list_intra": "e66f33d690f7d0d2ac9c797bedc16ff5bc79b9fffda268859016ed0d1d3f6254",
          "pop_fetch_script": "b7b75d56adb80aeb0a6833a3cf4b9f274e7038e7f4e85de6f96db89a6db4cd67",
          "pop_fetch_printout": "d6bd0f6743773f562ce92f28fcfc6cb9fc872227dfe5bf8fe04afd954245c7d5",
          "rev_frozen_module": REV_FROZEN_SHA}
SUBS_GLOB = rev.SUBS_GLOB
for _p in list(FILES.values()):
    assert not any(_p.startswith(d + "/") or _p == d for d in FORBIDDEN_DIRS), _p   # guard (9)

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants (every number is the doc's)
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = rev.CUT_B                                   # 2024-12-31: nothing dated after it is read from any file (guard 12)
A_LAST, B_FIRST = rev.A_LAST, rev.B_FIRST           # era by buy day: <= 2022-03-31 A, else B
FIT_WIN = rev.FIT_WIN                               # 2020-01-27..2020-12-31
CHECK_WIN = rev.CHECK_WIN                           # 2021-01-04..2022-06-14 (2021-22)
PRE_FIT = ("2020-01-01", "2020-01-26")              # the January-2020-before-the-27th virgin block
VIRGIN_YEARS = (2019, 2023)
SEED = 702
HORIZON = rev.HORIZON                               # 120
CAP30, SPEED_ARM, ARMS, EXIT_SLIPS = rev.CAP30, rev.SPEED_ARM, rev.ARMS, rev.EXIT_SLIPS
ORDER_OPEN, ORDER_BUY, ORDER_INTRADAY, ORDER_CLOSE = rev.ORDER_OPEN, rev.ORDER_BUY, rev.ORDER_INTRADAY, rev.ORDER_CLOSE
REC_MIN_BARS, REC_MIN_BARS_ENTER = rev.REC_MIN_BARS, rev.REC_MIN_BARS_ENTER      # 50 / 20 bars before the buy day
# the 60-minute bars
H60_VARIANT = "h60"
EARLY_CLOSE = frozenset(R.H60_EARLY_CLOSE)          # the 13:00 closes (20 listed; 17 on or before 2024-12-31)
SESSION_END, EARLY_END = 390, R.H60_EARLY_CUT       # the close as a minute bound: 16:00 = 390, 13:00 = 210
# ENTER
NEW_LEVELS = ("L7", "L8", "L9")
OLD_LEVELS = rev.LEVELS                             # L1-L6, re-reads
ALL_LEVELS = NEW_LEVELS + OLD_LEVELS
LEVEL_EXISTS = {"L7": 1, "L8": 30, "L9": 30, "L1": 5, "L6": 60}      # the minute (since 09:30) a level EXISTS; others from 0
UNION_LEVELS = ("L7", "L1", "L8")                   # "any opening range" (beside)
BALLPARK_ADR = rev.BALLPARK_ADR                     # 0.25
ENTER_PASS_FEASIBLE = 0.50
ENTER_CONTROL_MARGIN = 0.15
ENTER_HIT_FLOOR = 0.70                              # F1: a floor only (no +15 margin on hit-or-ballpark)
ENTER_MIN_CHECK = 40                                # 39 records or fewer -> INCONCLUSIVE-by-size
ENTER_VETO_MIN = 5                                  # fewer scorable untouched windows -> the veto abstains
RANDOM_LEVELS, RANDOM_KEY = rev.RANDOM_LEVELS, rev.RANDOM_KEY          # 200, "rev|minute" (identical draws)
SHIFT_DRAWS = 200
SHIFT_KEY = "intra|bracket|{eid}|{level}|{draw}"
# STOP
STOP_LEVELS = ("S1", "S3", "S9", "S10")
STOP_CONTROLS = ("S8", "SMA50")
STOP_VARIANTS = ("T", "C", "H")
STOP_VARIANT_TIE = {"T": 0, "C": 1, "H": 2}         # ties on the median width: the touch reading first (a reading, listed)
STOP_H_CHOOSE, STOP_H_PASS, STOP_H_FALSIFY = 0.10, 0.15, 0.30
STOP_MIN_TRADED = 20
STOP_MIN_DIFFER = 20                                # S9 / S10 chosen: records differing from S1 on the deciding set
# EXIT
WARMUP_SESSIONS, TAIL_SESSIONS = 10, 20
LOOKBACK_SESSIONS = {"enter": 20, "stop": 50, "exit": 50}   # N3 (DECIDED 2026-10-25): the daily lookback before the buy day each fit stage reads
                                                            # (ADR20 / L3 20 bars; the 50-day average 50 bars) — the LOWER bound of its planned span
EMA_N, EMA_ALPHA = 20, 2.0 / 21.0
EMA_SEED_BARS, EMA_POST_SEED_BARS = 20, 45              # C3 (DECIDED 2026-10-25): 65 bars; a 10-session warm-up holds 70 (67 across an early close), so the
                                                        # floor sits under every logged warm-up of the deciding set; the seed keeps (19/21)^45 = 1.1%
EXIT_VARIANTS = ("E1", "E2", "E3", "E4")
EXIT_TIE_ORDER = ("E1", "E4", "E2", "E3")           # ties on the hit rate -> fewer legs
EXIT_RECOVERY_BAR, EXIT_VOID_RATIO, EXIT_HIT_MAX_WINDOW = 0.25, 1.25, 20
EXIT_ABSTAIN_MAX = 0.10                             # the cuts + ema_thin + no-bar abstentions over the deciding trades
CUT_KINDS = ("cut_at_tail", "cut_at_horizon", "cut_at_data_end", "cut_at_guard", "mark_hole", "mark_break")   # a walk's last leg booked at a mark, not a rule (N7)
BOOT_DRAWS, BOOT_KEY = 1000, "intra|boot"
# WHY-lite
WHY_P_60 = r"60[ -]?min|hourly|hour chart"
WHY_P_EMA = r"(20|twenty)[ -]?ema"
WHY_PHRASE = r"(60[ -]?min(ute)?|hourly).{0,80}(20|twenty)[ -]?(ema|day)|(20|twenty)[ -]?ema.{0,80}(60[ -]?min(ute)?|hourly)"
WHY_WINDOW_S = rev.WHY_WINDOW_S                     # 30 s
WHY_SEED, WHY_SAMPLE, WHY_PRECISION = 1025, 10, 0.70
# known-answer gates
# (i) minute-built session OHLC vs the daily export, two arms (C1, DECIDED 2026-10-25). The daily open and close are the auction prints; the minute
# bars open and close on ordinary trades, so open / close carry a basis difference (median 0.03%, p90 0.19%, one 4.9% day on the 88 ENTER-fit buy
# days) while high / low are set by trades on both sides (exact to the cent on 88 of 88). The bug classes the gate exists for read, on the same 88
# pairs: a one-hour clock shift — high AND low within 0.5% on 8%, open AND close on 3.4%; a wrong day — 0% and 1.1%. The bars sit between the true
# reading (100% / 95.5%) and the broken ones with margin on both sides; they are not the first bar the reading clears.
AUCTION_BAND = 0.005                                # the open / close (auction) basis band, shared by gate (i)'s open-close arm and gate (iii)
GATE_HL_TOL, GATE_HL_SHARE = 0.005, 0.98            # (i-a) high AND low within 0.5% on >= 98% of pairs (decides)
GATE_OC_TOL, GATE_OC_SHARE = AUCTION_BAND, 0.90     # (i-b) open AND close within 0.5% on >= 90% of pairs (decides)
GATE_III_SHARE = 0.98                               # (iii) >= 98% of the C-event days BEYOND the auction band are H-event days (C2)
GATE_L8_EQ_L6_SHARE = 0.90                          # (ii): "L8 equal to L6 on nearly every trade" read as > 90% of the windows with both (a reading, listed)
OLD_TREES = ("A", "B", "EP", "EP2", "REV")          # the trees the previous fit's `exit_minutes_for` read, in its FIXED order (gate iv's re-read; C4)
RANDOM_CONTROL_KNOWN = (0.317, 0.859)               # (vii) the random-price control on the previous 41 undated 2021-22 windows: feasible / hit-or-ballpark
                                                    # (`01_rev_check.txt` l.33, printed at one decimal) — identical draws must reproduce it (C6)
FSLY_GATE = dict(eid=693, sym="FSLY", E="2020-06-29", exit_lo="2020-07-13", exit_hi="2020-07-14", h60_below_on="2020-07-10", prior_low_touch_on="2020-07-13")
GATE_V_RATIO_OLD = "1.398 / 2.620 / 1.87"           # l.116 of 01_rev_check.txt: the OLD aggregate under the old offsets, named, not a target

# ═════════════════════════════════════════════════════════════════════════════════════════════
# EXPECT — every composition count of §2 / §2a-d / §5d / §11 as THIS doc fixes them: (doc anchor, label, value). The anchor is a phrase of the
# doc line carrying the claim; the dry run resolves it to the CURRENT line number ([L?] when the phrase is gone). Labels unique (asserted).
# ═════════════════════════════════════════════════════════════════════════════════════════════
EXPECT = [
    ("against the previous dry run's 63 counts", "the previous registration's 63 counts: the 47 composition claims its frozen population_claims carries (the other 16 were data-gate / caption / record-builder lines derived only inside its dry run; their current equivalents are this doc's own §8 / §11 claims below)", "47 OK, 0 MISMATCH"),
    ("| **fit, dated 2020** (2020-01-27..12-31) | **149**", "fit dated 2020: n / non-flicker / in-session (nf) / exits known / era B", "149 / 104 / 32 (24) / 149 / 0"),
    ("| **fit, undated exact-day 2020** (flickers included) | **304**", "fit undated 2020: n / non-flicker / in-session (nf) / exits known / era B", "304 / 188 / 94 (59) / 304 / 0"),
    ("| **2021-22 dated** (2021-01-04..2022-06-14) | **111**", "2021-22 dated: n / non-flicker / in-session (nf) / exits known / era B", "111 / 68 / 20 (13) / 111 / 7"),
    ("| **2021-22 undated exact-day** | **226**", "2021-22 undated: n / non-flicker / in-session (nf) / exits known / era B", "226 / 145 / 63 (44) / 226 / 8"),
    ("| **untouched: 2019 dated** | 16", "untouched 2019 dated: n / non-flicker / in-session (nf) / exits known / era B", "16 / 13 / 1 (1) / 16 / 0"),
    ("| untouched: 2019 undated exact-day | 44", "untouched 2019 undated: n / non-flicker / in-session (nf) / exits known / era B", "44 / 26 / 18 (10) / 44 / 0"),
    ("| untouched: 2023 dated | 7", "untouched 2023 dated: n / non-flicker / in-session / exits known (still held) / era B", "7 / 7 / 0 / 3 (4) / 7"),
    ("| untouched: 2023 undated exact-day | 8", "untouched 2023 undated: n / non-flicker / in-session (nf) / exits known / era B", "8 / 5 / 3 (2) / 8 / 8"),
    ("| untouched: 2022 after 06-14 | 2 dated + 1 undated", "untouched 2022 after 06-14: dated + undated / non-flicker / in-session / exits known / era B", "2 + 1 / 3 / 0 / 3 / 3"),
    ("| untouched: 2020 before 01-27 | 2 dated + 9 undated", "untouched 2020 before 01-27: dated + undated / non-flicker / in-session (nf) / exits known / era B", "2 + 9 / 11 / 7 (7) / 11 / 0"),
    ("| **the virgin block, all** | **89 = 62 undated + 27 dated**", "the virgin block: n = undated + dated / non-flicker / in-session (nf) -> scorable (nf) / exits known / era B", "89 = 62 + 27 / 65 / 29 (20) -> 17 (9) / 85 / 18"),
    ("| listed, never walked: 2017-18 | 4", "listed 2017-18: n / non-flicker / in-session / exits known / era B", "4 / 4 / 0 / 4 / 0"),
    ("**2a. Streams per year", "streams per year (videos / session dates): 2017 / 2018 / 2019 / 2020 / 2021 / 2022 / 2023", "11/11 / 1/1 / 39/39 / 218/216 / 177/177 / 59/59 / 12/12"),
    ("43 of the 44 undated non-flicker and 17 of the 20 dated close at or after 10:00", "2021-22 in-session windows closing at or after 10:00: undated nf / dated; undated nf opening at or after 10:00", "43 of 44 / 17 of 20; 14 of 44"),
    ("On the fit, 48 of 59 undated", "fit in-session windows closing at or after 10:00: undated nf / dated", "48 of 59 / 19 of 32"),
    ("Nine trades were held before 09:35", "held before 09:35 (KOLD out): n / L7 exists (first seen 09:31-09:34) / not (09:30)", "9 / 7 / 2"),
    ("block's 29 in-session windows", "§2c virgin: in-session -> scorable (nf); 2021-22 undated nf -> ; dated -> ; fit dated -> ; fit undated nf -> ; fit flickers ->", "29 -> 17 (9); 43; 20; 31; 59; 34"),
    ("**Effect:** the virgin", "§2c the 9 scorable non-flicker untouched windows", "ASPS 2019-10-03, JCP 2019-10-07, RLGY 2019-10-10, CCS 2019-10-17, BABA 2019-11-01, LX 2019-11-15, APT 2020-01-23, CVNA 2023-05-18, AI 2023-05-19"),
    ("block's 29 in-session windows", "§2c 2021-22 undated window dropped", "DWAC 2022-01-31 flat_before_open"),
    ("sell window one session wide on 80 of the 101", "2d: 2021-22 dated with exits / 2021 trades with a one-session sell window", "111 / 80 of 101"),
    ("GSIT and GTLB 2023 span 121", "2d: 2019 dated sell windows span (sessions) / GSIT and GTLB 2023 span", "1-14 / 121, 121"),
    ("Eighteen of the 89 untouched trades are era B", "era B among the virgin block / of the 2021-22 dated / of the 2021-22 undated", "18 / 7 / 8"),
    ("**19,470 pairs", "fetch list: pairs / dates / sha prefix / by block fit2020 fit2020+virgin fit2020+y2122 virgin y2122 / by year 2019 2020 2021 2022 2023 2024",
     "19470 / 1005 / e66f33d6 / 8795 52 135 3179 7309 / 1405 9367 6304 1454 924 16"),
    ("19,184 ok, 286 empty at the source, 0", "the fetch log on the list: ok / empty / failed / rows not on the list / pending", "19184 / 286 / 0 / 0 / 0"),
    ("logged 286 more pairs empty at the source (fit 2020 213,", "empty at the source by block (the list's block column): fit 2020 / the untouched years / 2021-22", "213 / 58 / 15"),
    ("four scorable ENTER windows have no buy-day bars", "scorable ENTER windows (after §2c) with no buy-day bars, by name", "FBR 2019-10-22, OAS 2020-04-30, HTZ 2020-07-22, U 2020-07-24"),
    ("All 43", "2021-22 deciding ENTER windows with buy-day bars ok", "43 of 43"),
    ("20 in the runner's list, 17 inside this read's dates", "early-close days: the runner's list / on or before 2024-12-31 / among the fetch list's dates", "20 / 17 / 8"),
    ("the 8 undated 2021-22 check trades: 0-1, 4-4, 5-6, 5-6, 0-7, 2-6, 0-4, 0-4", "era-B offsets (own calendar) of the 8 undated 2021-22 trades, sorted", "0-1, 0-4, 0-4, 0-7, 2-6, 4-4, 5-6, 5-6"),
    ("expected n = 40 records** after the 20-bar", "ENTER deciding 2021-22 windows -> records after the 20-bar floor", "43 -> 40"),
    ("L8 and L9 on 59 scorable before the record floor (3 dated +", "2021-22 in-session windows after §2c closing before 10:00: dated / undated", "3 / 1"),
    ("of 495 caption files, 358 match", "captions (parsed words): files / 60-minute mentions / 20-EMA mentions / the phrase set", "495 / 358 / 122 / 77"),
    ("FSLY eid 693", "the FSLY known answer: eid 693 = sym, buy day, exit window, undated, non-flicker", "FSLY 2020-06-29 2020-07-13..2020-07-14 undated non-flicker"),
    ("warm-up alone under the 65-bar floor", "EXIT warm-up bars from the fetch logs + calendar: under the 65-bar floor, deciding 2021-22 dated / fit 2020 dated / virgin dated; 67-bar warm-ups (an early close inside) deciding / fit / virgin",
     "0 of 111 / 0 of 149 / 0 of 23; 13 / 9 / 0"),
    ("collide with a check-side trade's post-buy sessions", "guard (5) per ticker-date: fit trades excluded by their planned span, ENTER / STOP / EXIT; check-side trades exposed", "1 / 16 / 10; 1 / 7 / 8"),
    ("excluded, by name", "guard (5) per ticker-date: the excluded fit trades by name",
     "ENTER: APT 2020-02-28; STOP: FCEL 2020-02-10, BLDP 2020-02-10, APT 2020-02-21, APT 2020-02-28, APT 2020-03-02, STNE 2020-03-03, APT 2020-03-05, SE 2020-04-06, "
     "TDOC 2020-04-07, APT 2020-04-22, FCEL 2020-04-22, APT 2020-04-23, SE 2020-04-27, SE 2020-05-05, APT 2020-05-06, TDOC 2020-05-12; EXIT: BLDP 2020-02-10, APT 2020-02-21, "
     "APT 2020-02-28, APT 2020-04-22, APT 2020-04-23, TDOC 2020-05-12, FEAC 2020-11-30, TLRY 2020-12-16, MSTR 2020-12-28, NIO 2020-12-30"),
    ("ENTER's beside windows lose", "guard (5) per ticker-date: ENTER's beside windows excluded (N5): n of windows; by name",
     "6 of 194; FCEL 2020-02-10, BLDP 2020-02-10, APT 2020-02-21, APT 2020-03-05, SE 2020-04-06, TSLA 2022-04-21"),
    ("pre-buy daily reads by bar index", "guard (5) the kept fit trades' pre-buy daily reads by bar index on a forbidden pair (N3): ENTER / ENTER beside / STOP / EXIT", "0 / 0 / 0 / 0"),
    ("speed-trail window holds a forbidden session", "X1: the kept EXIT fit trades whose speed-trail window the guard bounds: n; by name",
     "22; PINS 2020-07-31, BE 2020-08-13, NIO 2020-09-14, TSLA 2020-09-21, TWTR 2020-09-22, SE 2020-09-25, NIO 2020-09-29, TSLA 2020-09-30, ZM 2020-10-09, TSLA 2020-10-12, "
     "TTD 2020-10-29, ENPH 2020-11-05, SQ 2020-11-06, TSLA 2020-11-09, TSLA 2020-11-18, JMIA 2020-11-18, MRNA 2020-11-30, SE 2020-12-03, LAZR 2020-12-08, NVAX 2020-12-17, "
     "NCLH 2020-12-28, CCL 2020-12-28"),
    ("replayed over the previous read's population", "ENTER check: the random-price draw population (the previous read's) = dated (flickers) + undated non-flicker (DWAC in)", "64 = 20 (7) + 44 (1)"),
]
assert len({lab for _a, lab, _v in EXPECT}) == len(EXPECT), "EXPECT labels must be unique"


def doc_line_of(anchor: str, doc: str = None, _cache: dict = {}) -> int:
    """The 1-based number of the FIRST doc line containing `anchor` (0 when the phrase is gone — a stale claim, printed as [L?])."""
    path = doc or DOC
    if path not in _cache:
        with open(path, encoding="utf-8") as fh:
            _cache[path] = fh.read().splitlines()
    for i, ln in enumerate(_cache[path], 1):
        if anchor in ln:
            return i
    return 0


def fmt_claim(x) -> str:
    return f"{x:.4g}" if isinstance(x, float) else str(x)


class Claims:
    """The dry run's assertions against THIS doc: every line printed with the doc line the anchor resolves to, every mismatch collected,
    STOP at the end (never at the first). A value whose label ends in ', sorted' is compared as a sorted token list."""

    def __init__(self, say):
        self.say = say
        self.bad = []
        self.n = 0

    @staticmethod
    def _norm(x, label: str) -> str:
        s = fmt_claim(x)
        if label.endswith(", sorted") or label.endswith("by name"):
            return ", ".join(sorted(t.strip() for t in s.split(",")))
        return s

    def __call__(self, anchor: str, label: str, doc, mine) -> bool:
        ok = self._norm(doc, label) == self._norm(mine, label)
        self.n += 1
        ln = doc_line_of(anchor)
        self.say(f"  [L{ln if ln else '?'}] {label} | doc {fmt_claim(doc)} | mine {fmt_claim(mine)} | {'OK' if ok else 'MISMATCH'}")
        if not ok:
            self.bad.append((ln, label, doc, mine))
        return ok


# ═════════════════════════════════════════════════════════════════════════════════════════════
# small helpers (the frozen module's where they are pure)
# ═════════════════════════════════════════════════════════════════════════════════════════════
pct, binom_ci, hhmm_to_min, min_to_hhmm, spearman = rev.pct, rev.binom_ci, rev.hhmm_to_min, rev.min_to_hhmm, rev.spearman
inwin, gate_steps, era_of, bar_sym = rev.inwin, rev.gate_steps, rev.era_of, rev.bar_sym


def rng_for(key: str, seed: int = SEED) -> np.random.Generator:
    return np.random.default_rng([seed, zlib.crc32(key.encode()) & 0xFFFFFFFF])


def fnum(x) -> float:
    """A float from a Python number, a numpy scalar or a ONE-element array (never float() of an array: numpy 2 refuses it)."""
    a = np.asarray(x, dtype=float)
    if a.ndim == 0:
        return float(a)
    if a.size != 1:
        raise ValueError(f"fnum: expected one value, got shape {a.shape}")
    return float(a.reshape(-1)[0])


def session_end_minute(E: str) -> int:
    return EARLY_END if E in EARLY_CLOSE else SESSION_END


# ═════════════════════════════════════════════════════════════════════════════════════════════
# IdCache — the module's ONLY identity-keyed cache (§11d): an entry is served only when the object it was built for is still the one asked
# about (`entry.obj is obj`), so a freed object's reused id can never serve another object's entry.
# ═════════════════════════════════════════════════════════════════════════════════════════════
class IdCache:
    def __init__(self):
        self._d = {}

    def get(self, obj, build=None, key=None):
        """The entry for `obj` (built by `build(obj)` when absent or when the id now belongs to another object). `key` sub-keys one object."""
        k = (id(obj), key)
        ent = self._d.get(k)
        if ent is not None and ent[0] is obj:
            return ent[1]
        if build is None:
            return None
        val = build(obj)
        self._d[k] = (obj, val)
        return val

    def __len__(self) -> int:
        return len(self._d)


_BARS = IdCache()      # per export D: {ticker: (bars, cidx)}
_SMAS = IdCache()      # per bars object: {10, 20, 50: series}
_QQQ = IdCache()       # per export D: (bars, cidx) of QQQ


def bars_of(D, tk: str):
    """(DailyBars, calendar indices) of `tk` in export D, or (None, None); cached per export OBJECT (never by a bare id)."""
    tab = _BARS.get(D, lambda _D: {})
    if tk not in tab:
        tid = D.tid.get(tk)
        tab[tk] = R.bars_for(D, tid) if tid is not None else (None, None)
    return tab[tk]


def smas_for(bars) -> dict:
    return _SMAS.get(bars, lambda b: {10: rev.sma_series(b, 10), 20: rev.sma_series(b, 20), 50: rev.sma_series(b, 50)})


def qqq_of(D):
    return _QQQ.get(D, lambda _D: R.bars_for(_D, _D.tid["QQQ"]))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock (line-anchored marker; the keyed chosen lines at column 0; the freeze body), the ledger, the outputs, the pins
# ═════════════════════════════════════════════════════════════════════════════════════════════
FREEZE_MARKER = ex.FREEZE_MARKER
marker_spans, doc_body_sha, freeze_missing = ex.marker_spans, ex.doc_body_sha, ex.freeze_missing
CHOSEN_RX = re.compile(r"^CHOSEN (ENTER|STOP|EXIT): (.*?)\s*$")        # column 0, the stage key, a space (F13)


def doc_body_text(doc: str = None) -> "str | None":
    """The text above the one line-anchored marker (None when the doc has not exactly one marker line)."""
    with open(doc or DOC, "rb") as fh:
        raw = fh.read()
    sp = marker_spans(raw)
    if len(sp) != 1:
        return None
    return raw[:sp[0][0]].decode("utf-8", errors="replace")


def chosen_lines(doc: str = None) -> dict:
    """{stage: [values]} of the `CHOSEN <STAGE>: ...` lines ABOVE the marker, at column 0, parsed by their stage key (never by position)."""
    body = doc_body_text(doc)
    out = defaultdict(list)
    if body is None:
        return {}
    for ln in body.splitlines():
        m = CHOSEN_RX.match(ln)
        if m:
            out[m.group(1).lower()].append(m.group(2).strip())
    return dict(out)


def pin_under_marker(name: str, doc: str = None) -> "str | None":
    """The value written under the marker for pin `name` (`- name: value`), or None."""
    with open(doc or DOC, "rb") as fh:
        raw = fh.read()
    sp = marker_spans(raw)
    if len(sp) != 1:
        return None
    tail = raw[sp[0][1]:].decode("utf-8", errors="replace")
    m = re.search(rf"^\s*[-*]?\s*`?{re.escape(name)}`?\s*:\s*`?([0-9a-fA-F]{{64}})`?", tail, re.M)
    return m.group(1).lower() if m else None


def store_freeze_body(doc: str = None, out_dir: str = None) -> str:
    """Keep a content-addressed copy of the body above the marker (so the 'only the three keyed lines differ' assertion can read the freeze
    commit's text without git); idempotent. -> the body's sha256."""
    body = doc_body_text(doc)
    if body is None:
        raise GuardStop("the doc does not carry exactly one freeze marker line")
    h = hashlib.sha256(body.encode("utf-8")).hexdigest()
    d = out_dir or FREEZE_BODIES
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"doc_body_{h}.md")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return h


def freeze_body_text(h: str, doc: str = None, out_dir: str = None) -> "str | None":
    """The body text whose sha256 is `h`: the stored copy first, else any commit of the doc in git whose body hashes to it."""
    p = os.path.join(out_dir or FREEZE_BODIES, f"doc_body_{h}.md")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
        if hashlib.sha256(txt.encode("utf-8")).hexdigest() == h:
            return txt
    rel = os.path.relpath(doc or DOC, REPO)
    try:
        log = subprocess.run(["git", "-C", REPO, "log", "--format=%H", "--", rel], capture_output=True, text=True, timeout=120).stdout.split()
        for commit in log:
            raw = subprocess.run(["git", "-C", REPO, "show", f"{commit}:{rel}"], capture_output=True, timeout=120).stdout
            sp = marker_spans(raw)
            body = raw[:sp[0][0]] if len(sp) == 1 else raw
            if hashlib.sha256(body).hexdigest() == h:
                return body.decode("utf-8", errors="replace")
    except Exception:
        return None
    return None


def body_diff_beyond_chosen(freeze_body: str, now_body: str) -> list:
    """The lines that differ between the freeze body and the current body, excluding keyed CHOSEN lines at column 0 (F13). -> offending lines."""
    import difflib
    a, b = freeze_body.splitlines(), now_body.splitlines()
    bad = []
    for ln in difflib.unified_diff(a, b, lineterm="", n=0):
        if ln.startswith(("---", "+++", "@@")):
            continue
        if ln.startswith(("+", "-")) and not CHOSEN_RX.match(ln[1:]):
            bad.append(ln)
    return bad


def freeze_state(doc: str = None, out_dir: str = None) -> tuple:
    """(ok, why): the freeze pin `doc_body_freeze` is under the marker, its body text is known, and the current body differs from it only in
    the keyed CHOSEN lines."""
    h = pin_under_marker("doc_body_freeze", doc)
    if h is None:
        return False, "doc_body_freeze is not under the marker (the freeze has not happened: run --print-pins at the freeze and paste it)"
    fb = freeze_body_text(h, doc, out_dir)
    if fb is None:
        return False, f"the freeze body {h[:12]}... is neither stored under freeze_bodies/ nor in any git commit of the doc"
    now = doc_body_text(doc)
    bad = body_diff_beyond_chosen(fb, now or "")
    if bad:
        return False, "the body above the marker differs from the freeze commit's beyond the keyed CHOSEN lines: " + " | ".join(bad[:4])
    return True, ""


def ledger_append(stage: str, path: str, ledger: str = None) -> None:
    """Append-only: stage, printout path, sha256, time. Verified by --check against the files on disk."""
    L = ledger or LEDGER
    new = not os.path.exists(L)
    with open(L, "a") as fh:
        if new:
            fh.write("stage\tpath\tsha256\ttime\n")
        fh.write(f"{stage}\t{path}\t{sha(path)}\t{_dt.datetime.now().isoformat(timespec='seconds')}\n")


def ledger_verify(ledger: str = None) -> list:
    L = ledger or LEDGER
    if not os.path.exists(L):
        return ["ledger missing"]
    bad = []
    rows = pd.read_csv(L, sep="\t", dtype=str, keep_default_na=False)
    for r in rows.to_dict("records"):
        if not os.path.exists(r["path"]):
            bad.append(f"{r['path']}: missing")
        elif sha(r["path"]) != r["sha256"]:
            bad.append(f"{r['path']}: changed since the ledger recorded it")
    return bad


def stage_outputs(stage: str) -> list:
    """Files whose existence refuses a stage: its own printout, a STOPPED file and its files under intraday/ (the dry run's `dryrun_*` files
    and `freeze_bodies/` never refuse anything)."""
    out = [p for p in (STOPPED,) if os.path.exists(p)]
    if stage in STAGES:
        out += [P_FIT[stage]] if os.path.exists(P_FIT[stage]) else []
        if os.path.isdir(OUT_DIR):
            out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR) if f.startswith(f"{stage}_fit"))
    elif stage == "check":
        out += [P_CHECK] if os.path.exists(P_CHECK) else []
        if os.path.isdir(OUT_DIR):
            out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR) if f.startswith("check_") or f.startswith("why_sheet"))
    elif stage == "why":
        out += [P_WHY] if os.path.exists(P_WHY) else []
    return out


def any_stage_output() -> list:
    out = [p for p in [STOPPED, P_CHECK, P_WHY, LEDGER] + list(P_FIT.values()) if os.path.exists(p)]
    if os.path.isdir(OUT_DIR):
        out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR) if not f.startswith("dryrun_") and f != "freeze_bodies")
    return out


def pins(doc: "str | None" = None, include_outputs: bool = True) -> dict:
    """Every pin: the previous registration's (its outputs renamed `rev_*`), this read's inputs, this module and its tests, this read's
    outputs when they exist (named absent otherwise), `doc_body_freeze` (the value under the marker, else the current body = the freeze),
    `doc_body`."""
    prev = rev.pins(include_outputs=True)
    p = {}
    for k, v in prev.items():
        if k in ("dryrun_printout", "select_fit_printout", "enter_fit_printout", "stop_fit_printout", "exit_fit_printout", "ledger", "doc_body"):
            p["rev_" + k] = v
        else:
            p[k] = v
    for name, path in FILES.items():
        if name not in rev.FILES:
            p[name] = sha(path) if os.path.exists(path) else "ABSENT"
    for name, path in CODE.items():
        p[name] = sha(path) if os.path.exists(path) else "ABSENT"
    if include_outputs:
        p["dryrun_printout"] = sha(P_DRY) if os.path.exists(P_DRY) else "ABSENT"
        for s in STAGES:
            p[f"{s}_fit_printout"] = sha(P_FIT[s]) if os.path.exists(P_FIT[s]) else "ABSENT"
        p["ledger"] = sha(LEDGER) if os.path.exists(LEDGER) else "ABSENT"
    p.update(fit_event_pins())
    d = doc or DOC
    p["doc_body_freeze"] = pin_under_marker("doc_body_freeze", d) or doc_body_sha(d)
    p["doc_body"] = doc_body_sha(d)
    return p


def dry_run_complete(path: str = None) -> bool:
    path = path or P_DRY
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    return bool(lines) and lines[-1].startswith("DRY RUN COMPLETE")


def check_pinned_inputs(say) -> None:
    """The previous read's pins (through the frozen module) and this read's (the fetch list, the derivation script and printout, the frozen
    module itself) must hold."""
    rev.check_pinned_inputs(lambda _m: None)
    drift = []
    for k, v in PINNED.items():
        if k in FILES and os.path.exists(FILES[k]) and sha(FILES[k]) != v:
            drift.append(f"{k}: {sha(FILES[k])[:12]} (pinned {v[:12]})")
    if drift:
        raise GuardStop("a pinned input changed: " + "; ".join(drift))
    say("- pins re-checked: the previous read's (exports, candidates, labels, guards, the frozen modules and tests) through the frozen module; this read's "
        "(the fetch list, 00_pop_fetch.py and its printout, the frozen previous module): no drift")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# minutes: the trees (the five pinned + INTRA), the fetch logs, the store (each (tree, date) file read once), the seal
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_done_all() -> tuple:
    done, files = rev.load_done_all()
    if "done_INTRA" in FILES:
        done["INTRA"], _ = rp.load_done(FILES["done_INTRA"], cut=CUT_B)
        files["INTRA"] = R.minute_date_files(MINUTES["INTRA"])
    return done, files


def trees_for(b) -> tuple:
    order = ("EP", "EP2", "A", "B", "REV", "INTRA") if getattr(b, "setup", "") == "EP" else ("A", "B", "EP", "EP2", "REV", "INTRA")
    return order


class MinuteStore:
    """Minute bars per (date, bar symbol). `preload(pairs)` reads each (tree, date) file ONCE for the symbols wanted on it; `get` serves the
    cache (a lazy single read when a pair was not preloaded). Every date is asserted <= 2024-12-31 at read (guard 12). `h60(d, tk)` = the
    session's clock-anchored 60-minute bars (None when the session has no minutes)."""

    def __init__(self, done: dict, files: dict):
        self.done, self.files = done, files
        self.cache = {}            # (d, tk) -> MinuteBars | None
        self.h60_cache = {}        # (d, tk) -> list | None
        self.reads = Counter()
        self.forbid = frozenset()  # guard (5) per (bar symbol, date): pairs a FIT stage may not read (set by the stage; empty in the check)

    def all_trees(self, b=None) -> tuple:
        return tuple(t for t in (trees_for(b) if b is not None else ("A", "B", "EP", "EP2", "REV", "INTRA")) if t in self.done)

    def restricted(self, trees: tuple = OLD_TREES) -> "MinuteStore":
        """A store over `trees` only, in that FIXED order, with its own cache (gate iv's re-read must take the exit window's first-session
        minutes from the trees the previous fit read — never from the new tree)."""
        st = MinuteStore({k: v for k, v in self.done.items() if k in trees}, {k: v for k, v in self.files.items() if k in trees})
        st.all_trees = lambda b=None: tuple(t for t in trees if t in st.done)       # the fixed order whatever the setup
        st.forbid = self.forbid
        return st

    def check_forbid(self, d: str, tk: str) -> None:
        if (tk, d) in self.forbid:
            raise GuardStop(f"guard (5): minutes of {tk} on {d} lie after the buy day of a check-side trade on that name; a fit stage may not read them")

    def state(self, d: str, tk: str, b=None) -> str:
        return rev.minute_state(d, tk, self.done, self.files, self.all_trees(b))

    @staticmethod
    def seal(d: str) -> None:
        if d > CUT_B:
            raise GuardStop(f"guard (12): a minute date after {CUT_B} was requested ({d}); 2025-26 is sealed")

    def _tree(self, d: str, tk: str, b=None) -> "str | None":
        return rev.covered_tree(d, tk, self.done, self.files, self.all_trees(b))

    def preload(self, pairs) -> Counter:
        """pairs: iterable of (d, tk[, b]). One file read per (tree, date) with the wanted symbols. -> counts by state."""
        by_file = defaultdict(set)
        st = Counter()
        for p in pairs:
            d, tk = p[0], p[1]
            b = p[2] if len(p) > 2 else None
            self.seal(d)
            self.check_forbid(d, tk)
            if (d, tk) in self.cache:
                st["cached"] += 1
                continue
            tr = self._tree(d, tk, b)
            if tr is None:
                self.cache[(d, tk)] = None
                st[self.state(d, tk, b).split("/")[0]] += 1
                continue
            by_file[(tr, d)].add(tk)
        for (tr, d), want in sorted(by_file.items()):
            blocks = R.read_minute_file(self.files[tr][d], want=want)[0]
            self.reads[tr] += 1
            for tk in want:
                rows = blocks.get(tk)
                mb = R.minute_bars_from_rows(rows) if rows else None
                if mb is not None and len(mb) == 0:
                    mb = None
                self.cache[(d, tk)] = mb
                st["ok" if mb is not None else "no_rows"] += 1
        return st

    def get(self, d: str, tk: str, b=None):
        self.seal(d)
        self.check_forbid(d, tk)
        if (d, tk) not in self.cache:
            self.preload([(d, tk, b)])
        return self.cache[(d, tk)]

    def h60(self, d: str, tk: str, b=None):
        key = (d, tk)
        if key not in self.h60_cache:
            mb = self.get(d, tk, b)
            self.h60_cache[key] = h60_bars(mb, d) if mb is not None else None
        return self.h60_cache[key]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the forward-bar guard (5): daily AND minute reads by date; the record (one calendar per record, §11c); the record builder
# ═════════════════════════════════════════════════════════════════════════════════════════════
class BarGuard:
    """A fit stage opens no DAILY OR MINUTE bar after the buy day of any trade outside ITS OWN registered fit set (`allowed_eids`), and no bar
    on a (bar symbol, date) pair that lies after the buy day of ANY check-side trade (`forbid`, guard (5) per ticker and date — C9).
    `allowed_eids=None` = the check (every forward bar may be read; `forbid` empty). Belt: any buy outside the fit window 2020-01-27..12-31
    (every 2021-22 and every virgin-block buy, dated or undated) is refused by every fit stage whatever the set says."""

    def __init__(self, allowed_eids: "set | None", forbid: "frozenset | None" = None):
        self.allowed = None if allowed_eids is None else frozenset(int(x) for x in allowed_eids)
        self.forbid = frozenset(forbid or ())

    def horizon(self, b) -> "int | None":
        if self.allowed is None:
            return None
        if not (FIT_WIN[0] <= b.E <= FIT_WIN[1]):
            return 0
        return None if b.eid in self.allowed else 0

    def forward(self, b, j: int, who: str = "") -> None:
        h = self.horizon(b)
        if h is not None and j > h:
            raise GuardStop(f"guard (5): session +{j} of {who or b.sym} eid {b.eid} (buy day {b.E}) was requested by a fit stage whose fit set does not "
                            f"hold that trade (its horizon is the buy day)")

    def check_pair(self, sym: str, d: str, who: str = "") -> None:
        """Guard (5) per ticker and date: the (bar symbol, date) pair may not lie after the buy day of a check-side trade on that name."""
        if self.forbid and (sym, d) in self.forbid:
            raise GuardStop(f"guard (5): the bar of {sym} on {d} lies after the buy day of a check-side trade on that name; a fit stage may not read it ({who})")

    def forward_date(self, b, d: str, who: str = "") -> None:
        self.check_pair(bar_sym(d, b.sym_a, b.sym), d, who or f"{b.sym} eid {b.eid}")
        if d > b.E:
            h = self.horizon(b)
            if h is not None:
                raise GuardStop(f"guard (5): minutes of {d} (after the buy day {b.E}) of {who or b.sym} eid {b.eid} were requested by a fit stage whose "
                                "fit set does not hold that trade")


@dataclass
class IRec:
    """One trade as this read sees it. ONE calendar per record: `cal` is the record's own export calendar (D.cal of its era) and EVERY session
    offset (the buy day, exit_lo, exit_hi, the still-held last frame, every walked session) is a bisect of the date on it (§11c)."""
    b: object
    bars: object
    cidx: np.ndarray
    e: int
    adr20: float
    cal: list
    era: str
    mb: object = None
    minutes_state: str = "missing"
    qqq_c: "np.ndarray | None" = None
    guard: object = None
    exit_lo_j: "int | None" = None
    exit_hi_j: "int | None" = None
    last_j: "int | None" = None            # a still-held trade: the session of its last frame showing the name
    off_snapped: int = 0                   # exit dates that were not sessions of the own calendar (snapped to the next session; expected 0)
    levels: dict = field(default_factory=dict)
    cross: dict = field(default_factory=dict)
    feasible: dict = field(default_factory=dict)
    verdict: dict = field(default_factory=dict)
    fill: "float | None" = None
    fill_minute: "int | None" = None
    fill_src: str = ""
    fill_fallback: bool = False
    stop: "float | None" = None
    stop_lvl: object = None
    stop_src: str = ""
    stop_variant: str = "T"
    stop_levels: dict = field(default_factory=dict)
    day0: dict = field(default_factory=dict)
    read_minute: "int | None" = None

    @property
    def p(self) -> int:
        return self.e - 1

    @property
    def e_ci(self) -> int:
        return int(self.cidx[self.e])

    def off(self, d: str) -> "int | None":
        """The session offset of date `d` from the buy day on the record's OWN calendar (None for an empty date); refuses a date beyond it."""
        if not d:
            return None
        dd = date.fromisoformat(d)
        ci = bisect.bisect_left(self.cal, dd)
        if ci >= len(self.cal):
            raise GuardStop(f"guard (10): {self.b.sym} eid {self.b.eid}: the date {d} lies beyond the record's own calendar ({self.cal[-1]})")
        if self.cal[ci] != dd:
            self.off_snapped += 1
        return max(0, ci - self.e_ci)

    def session_date(self, j: int) -> "str | None":
        """The date of session offset j on the record's own calendar (None outside it)."""
        k = self.e_ci + j
        if k < 0 or k >= len(self.cal):
            return None
        return self.cal[k].isoformat()

    def _ask_guard(self, j: int, d: "str | None") -> None:
        """Forward reads (j >= 1) ask the per-trade guard; EVERY read (the warm-up and the buy day included) asks the per-(symbol, date) guard."""
        if self.guard is None:
            return
        who = f"{self.b.sym} eid {self.b.eid}"
        if d is not None:
            self.guard.check_pair(bar_sym(d, self.b.sym_a, self.b.sym), d, who)
        if j >= 1:
            self.guard.forward(self.b, j, who)

    def bar_at(self, j: int) -> "int | None":
        """The ticker's bar index for session e + j on consecutive sessions only (None past a hole or the data's end); the guard is asked first."""
        if self.guard is not None:
            self._ask_guard(j, self.session_date(j) if self.guard.forbid else None)
        k = self.e + j
        if k < 0 or k >= len(self.cidx) or int(self.cidx[k]) != self.e_ci + j:
            return None
        return k

    def minutes(self, store: MinuteStore, j: int):
        """The minute bars of session offset j (own calendar; the bar symbol by the SESSION's date); the guard is asked first."""
        d = self.session_date(j)
        if d is None:
            return None
        if self.guard is not None:
            self._ask_guard(j, d)
            if j >= 1:
                self.guard.forward_date(self.b, d, f"{self.b.sym} eid {self.b.eid}")
        return store.get(d, bar_sym(d, self.b.sym_a, self.b.sym), self.b)

    def h60(self, store: MinuteStore, j: int):
        d = self.session_date(j)
        if d is None:
            return None
        if self.guard is not None:
            self._ask_guard(j, d)
            if j >= 1:
                self.guard.forward_date(self.b, d, f"{self.b.sym} eid {self.b.eid}")
        return store.h60(d, bar_sym(d, self.b.sym_a, self.b.sym), self.b)


def rec_drop_reason(b, M: dict, era: str, min_bars: int = REC_MIN_BARS) -> "str | None":
    """Why a buy gets no record (bars up to the buy day only): not in the era's export, no bar on the buy day, fewer than `min_bars` bars before it."""
    D = M["Ds"][era]
    tk = b.sym_a if era == "A" else b.sym
    bars, cidx = bars_of(D, tk)
    if bars is None:
        return "ticker_not_in_export"
    e_ci = bisect.bisect_left(D.cal, date.fromisoformat(b.E))
    if e_ci >= len(D.cal) or D.cal[e_ci] != date.fromisoformat(b.E):
        return "buy_day_not_on_calendar"
    e = int(np.searchsorted(cidx, e_ci))
    if not (e < len(cidx) and int(cidx[e]) == e_ci):
        return "no_bar_on_E"
    if e < min_bars:
        return f"bars_before_E_lt_{min_bars}"
    return None


def last_seen_date(M: dict, b) -> "str | None":
    """A still-held trade: the last frame date showing the name on or after the buy day (the Sightings' frames), else None."""
    ls = M.get("last_seen") or {}
    ds = [d for d in ls.get(b.sym, ()) if d >= b.E]
    return max(ds) if ds else None


def make_irec(b, M: dict, era: str, store: "MinuteStore | None", guard: "BarGuard | None", min_bars: int = REC_MIN_BARS,
              want_minutes: bool = True) -> "IRec | None":
    why = rec_drop_reason(b, M, era, min_bars)
    if why is not None:
        return None
    D = M["Ds"][era]
    tk = b.sym_a if era == "A" else b.sym
    bars, cidx = bars_of(D, tk)
    e_ci = bisect.bisect_left(D.cal, date.fromisoformat(b.E))
    e = int(np.searchsorted(cidx, e_ci))
    if guard is not None and guard.forbid:
        # the belt for the PRE-BUY daily reads (N3): ADR20 / the 50-day average / the base low index the bar arrays directly, outside `bar_at`
        for sym_d, d in lookback_pairs(b, bars, cidx, e, D.cal, min_bars):
            guard.check_pair(sym_d, d, f"{b.sym} eid {b.eid} (a pre-buy daily lookback)")
    rec = IRec(b=b, bars=bars, cidx=cidx, e=e, adr20=rev.adr20_at(bars, e - 1, b), cal=D.cal, era=era, guard=guard)
    qb, qc = qqq_of(D)
    qpos = {int(c): k for k, c in enumerate(qc)}
    # QQQ's closes aligned to the ticker's indices (`exit_features` reads them through guarded indices). A dates-only build (`want_minutes`
    # False: the dry run's era-B offsets) stops at the buy day, so the record holds no close after it (C13).
    cut = len(cidx) if want_minutes else e + 1
    rec.qqq_c = np.array([(qb.c[qpos[int(c)]] if (i < cut and int(c) in qpos) else np.nan) for i, c in enumerate(cidx)], dtype=float)
    if b.has_exit:
        rec.exit_lo_j, rec.exit_hi_j = rec.off(b.exit_lo), rec.off(b.exit_hi)
    else:
        ld = last_seen_date(M, b)
        rec.last_j = rec.off(ld) if ld else None
    if want_minutes and store is not None:
        rec.mb = store.get(b.E, tk, b)
        rec.minutes_state = store.state(b.E, tk, b)
    return rec


def recs_for(buys: list, M: dict, store, guard, min_bars: int = REC_MIN_BARS, want_minutes: bool = True) -> tuple:
    out, drop = [], Counter()
    for b in buys:
        era = era_of(b.E)
        r = make_irec(b, M, era, store, guard, min_bars, want_minutes)
        if r is None:
            drop[rec_drop_reason(b, M, era, min_bars) or "unknown"] += 1
            continue
        out.append(r)
    return out, drop


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the sets (§2): the previous registration's sets as they stand, plus the untouched years; the clock-sanity rule (§2c)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def intra_sets(S: dict) -> dict:
    """The §2 table from the frozen sets: dec_used (dated deciding after §2b), ex_all / ex_nf (exact-day undated; gate_steps = §2b)."""
    dec, ex_all = S["dec_used"], S["ex_all"]
    I = {}
    I["fit_dated"] = inwin(dec, FIT_WIN)
    I["fit_und"] = gate_steps(inwin(ex_all, FIT_WIN))[0]
    I["chk22_dated"] = inwin(dec, CHECK_WIN)
    I["chk22_und"] = gate_steps(inwin(ex_all, CHECK_WIN))[0]
    I["v19_dated"] = [b for b in dec if b.year == 2019]
    I["v19_und"] = gate_steps([b for b in ex_all if b.year == 2019])[0]
    I["v23_dated"] = [b for b in dec if b.year == 2023]
    I["v23_und"] = gate_steps([b for b in ex_all if b.year == 2023])[0]
    I["v22h2_dated"] = [b for b in dec if b.year == 2022 and b.E > CHECK_WIN[1]]
    I["v22h2_und"] = gate_steps([b for b in ex_all if b.year == 2022 and b.E > CHECK_WIN[1]])[0]
    I["v20pre_dated"] = inwin(dec, PRE_FIT)
    I["v20pre_und"] = gate_steps(inwin(ex_all, PRE_FIT))[0]
    I["virgin_dated"] = I["v19_dated"] + I["v23_dated"] + I["v22h2_dated"] + I["v20pre_dated"]
    I["virgin_und"] = I["v19_und"] + I["v23_und"] + I["v22h2_und"] + I["v20pre_und"]
    I["virgin_all"] = I["virgin_dated"] + I["virgin_und"]
    I["listed_1718"] = [b for b in dec if b.year <= 2018] + gate_steps([b for b in ex_all if b.year <= 2018])[0]
    return I


def clock_sane(b, mis: dict) -> str:
    """§2c, in order: (i) the flat frame's clock reads 09:30 or later (in-session by the clock), (ii) a positive width, (iii) neither frame is a
    misread clock under guard (8). -> 'ok' | 'flat_before_open' | 'zero_width' | 'clock_misread'."""
    fl, fm = hhmm_to_min(b.flat_clock), hhmm_to_min(b.first_clock)
    if fl is None or fm is None or fl < 0:
        return "flat_before_open"
    if fm - fl <= 0:
        return "zero_width"
    if b.first_frame in mis or b.prev_full_frame in mis:
        return "clock_misread"
    return "ok"


def windows_of(bs: list, mis: dict, flicker: "bool | None" = None) -> list:
    """The in-session windows of `bs` that pass §2c; `flicker` True / False restricts, None takes both."""
    out = []
    for b in bs:
        if not b.in_bracket or clock_sane(b, mis) != "ok":
            continue
        if flicker is not None and b.flicker != flicker:
            continue
        out.append(b)
    return out


def dropped_windows(bs: list, mis: dict) -> list:
    return [(b, clock_sane(b, mis)) for b in bs if b.in_bracket and clock_sane(b, mis) != "ok"]


def enter_sets(I: dict, S: dict, mis: dict) -> dict:
    """ENTER's windows: the fit (31 dated + 59 undated non-flicker decide; 34 flickers beside), 2021-22 (43 undated nf decide; 20 dated + 19
    flickers beside), the virgin block (17 scorable, 9 non-flicker = the sign veto), the pre-market-flat windows, the held-before-09:35, the
    pre-market first sightings."""
    E = {}
    E["fit_dated"] = windows_of(I["fit_dated"], mis)
    E["fit_und"] = windows_of(I["fit_und"], mis, flicker=False)
    E["fit_fl"] = windows_of(I["fit_und"], mis, flicker=True)
    E["chk22_und"] = windows_of(I["chk22_und"], mis, flicker=False)
    E["chk22_dated"] = windows_of(I["chk22_dated"], mis)
    E["chk22_fl"] = windows_of(I["chk22_und"], mis, flicker=True)
    E["virgin"] = windows_of(I["virgin_all"], mis)
    E["virgin_nf"] = [b for b in E["virgin"] if not b.flicker]
    E["virgin_fl"] = [b for b in E["virgin"] if b.flicker]
    E["pre_dated_fit"] = inwin(S["ent_pre_dated"], FIT_WIN)
    E["pre_dated_chk"] = inwin(S["ent_pre_dated"], CHECK_WIN)
    E["pre_und_fit"] = inwin(S["ent_pre_und"], FIT_WIN)
    E["pre_und_chk"] = inwin(S["ent_pre_und"], CHECK_WIN)
    E["held_0935"] = [b for b in S["dec_used_dense"] + S["sel_fit"] + S["sel_chk"] if b.held_before_0935]
    E["prefirst_fit"] = inwin(S["ent_prefirst_dated"], FIT_WIN)
    E["prefirst_chk"] = inwin(S["ent_prefirst_dated"], CHECK_WIN)
    return E


def fit_set_violation(stage: str, b) -> "str | None":
    """Guard (5), first half: the registered fit set of each stage as a predicate on one buy (None = the buy belongs). ENTER: the 2020
    in-session windows after §2c (dated deciding, or exact-day undated non-flicker no-event). STOP: dated deciding 2020, or exact-day undated
    2020 (flickers included). EXIT: dated deciding 2020 with a known exit. No buy outside 2020-01-27..12-31 is fit material in any stage."""
    gate = b.type_ok and not b.inverted and not b.same_day_rebuy and not b.initial
    if not gate:
        return "fails the §2b gate (type / inverted / same-day re-buy)"
    if not (FIT_WIN[0] <= b.E <= FIT_WIN[1]):
        return f"outside the fit window ({b.E}): a 2021-22 or virgin-block buy is never fit material"
    if stage == "enter":
        ok = b.in_bracket and (b.decides if b.dated else (b.noev and b.wl == 1 and not b.flicker))
    elif stage == "stop":
        ok = b.decides if b.dated else (b.noev and b.wl == 1)
    elif stage == "exit":
        ok = b.dated and b.decides and b.has_exit
    else:
        raise ValueError(stage)
    return None if ok else f"not in the registered {stage.upper()} fit set ({'dated' if b.dated else 'undated'} {b.E}, window {b.wl}, flicker {b.flicker})"


def assert_fit_set(say, stage: str, buys: list) -> set:
    bad = [(b.eid, b.sym, b.E, fit_set_violation(stage, b)) for b in buys if fit_set_violation(stage, b)]
    if bad:
        raise GuardStop(f"the {stage.upper()} fit set holds {len(bad)} trade(s) outside the registered fit set: " + "; ".join(f"{s} {e} eid {i}: {w}" for i, s, e, w in bad[:5]))
    eids = {b.eid for b in buys}
    say(f"- fit set composition asserted (guard 5): {len(eids)} trades, every one in the registered {stage.upper()} fit set; the forward-bar guard allows these eids only")
    return eids


# ═════════════════════════════════════════════════════════════════════════════════════════════
# guard (5) per TICKER and DATE (C9): the (bar symbol, date) pairs after any check-side trade's buy day; a fit trade whose planned span touches
# one is excluded from that fit stage BY DATES ALONE (no bar read decides it); the per-date refusal in BarGuard / MinuteStore is the belt
# ═════════════════════════════════════════════════════════════════════════════════════════════
def check_side_buys(I: dict) -> list:
    return I["chk22_dated"] + I["chk22_und"] + I["virgin_all"]


def forbidden_pairs(C: dict, last_seen: "dict | None" = None) -> dict:
    """{(bar symbol, date): set of (eid, sym, E)} over the check-side trades' post-buy sessions on the pickle calendar: buy day + 1 ..
    exit_hi + TAIL_SESSIONS; a still-held trade: the last frame showing the name + TAIL_SESSIONS (the buy day alone when no frame is known)."""
    cal, CI = C["cal"], C["CI"]
    out = defaultdict(set)
    for b in check_side_buys(C["I"]):
        if b.Ei < 0:
            continue
        if b.has_exit:
            hi_i = b.exit_hi_i
        else:
            ds = [d for d in (last_seen or {}).get(b.sym, ()) if d >= b.E and d in CI]
            hi_i = max(CI[d] for d in ds) if ds else b.Ei
        for i in range(b.Ei + 1, min(len(cal), hi_i + TAIL_SESSIONS + 1)):
            d = cal[i]
            out[(bar_sym(d, b.sym_a, b.sym), d)].add((b.eid, b.sym, b.E))
    return dict(out)


def planned_span(stage: str, b, cal: list) -> list:
    """The (bar symbol, date) pairs a fit stage READS for one buy, by dates alone (N1 / N3, DECIDED 2026-10-25). LOWER bound = the daily
    lookback the stage reads before the buy day (ENTER 20 sessions: ADR20, L2 / L3 / L5; STOP / EXIT 50: the 50-day average, the dated base
    low, the 10-session warm-up inside it). UPPER bound = the last session a walk can book on: ENTER the buy day; STOP exit_hi + 1 (a close or
    60-minute stop sells at the NEXT open); EXIT exit_hi + 20 + 1 (the tail's last session, then a next-session open booked after it). A trade
    without an exit: the buy day stands for exit_hi. The bar-index belt in `make_irec` (`lookback_pairs`) catches a lookback a hole stretches."""
    if b.Ei < 0:
        return []
    hi = b.exit_hi_i if b.has_exit else b.Ei
    if stage == "enter":
        hi_i = b.Ei
    elif stage == "stop":
        hi_i = hi + 1
    elif stage == "exit":
        hi_i = hi + TAIL_SESSIONS + 1
    else:
        raise ValueError(stage)
    lo_i = b.Ei - LOOKBACK_SESSIONS[stage]
    return [(bar_sym(cal[i], b.sym_a, b.sym), cal[i]) for i in range(max(0, lo_i), min(len(cal), hi_i + 1))]


def lookback_pairs(b, bars, cidx, e: int, cal: list, min_bars: int) -> list:
    """The (bar symbol, date) pairs of a record's PRE-BUY daily reads, by BAR index on its own calendar (dates only, N3): the `min_bars` bars
    before the buy day (ENTER 20: ADR20 and L2 / L3 / L5; STOP / EXIT 50: the 50-day average), and on a dated trade read under the 50-bar floor
    the base low's bars from its base date (S6, computed inside the frozen `stop_levels`). A hole makes 50 bars span more than 50 sessions;
    this list is what the belt in `make_irec` and the dry run's assertion check."""
    k0 = max(0, e - min_bars)
    if min_bars >= REC_MIN_BARS and getattr(b, "dated", False) and b.base_id and "|" in b.base_id:
        kb = bisect.bisect_left(bars.dates, date.fromisoformat(b.base_id.split("|", 1)[1]))
        k0 = min(k0, max(0, min(kb, e - 1)))
    out = []
    for k in range(k0, e):
        d = cal[int(cidx[k])].isoformat()
        out.append((bar_sym(d, b.sym_a, b.sym), d))
    return out


def collisions(stage: str, buys: list, forbid: dict, cal: list) -> list:
    """[(buy, [pairs hit], {exposed check-side trades})] for the buys whose planned span touches a forbidden pair, in (E, eid) order."""
    out = []
    for b in sorted(buys, key=lambda x: (x.E, x.eid)):
        hit = [p for p in planned_span(stage, b, cal) if p in forbid]
        if hit:
            out.append((b, hit, set().union(*(forbid[p] for p in hit))))
    return out


def exclude_collisions(say, stage: str, buys: list, forbid: dict, cal: list, label: str = "") -> list:
    """The buys of a fit stage minus the colliding ones, each named with the check-side trade(s) it would expose."""
    col = collisions(stage, buys, forbid, cal)
    bad = {b.eid for b, _h, _x in col}
    say(f"- guard (5) per ticker-date{(' (' + label + ')') if label else ''}: {len(col)} of {len(buys)} trades excluded because their planned span touches a (symbol, session) "
        f"after a check-side trade's buy day: " + ("; ".join(f"{b.sym} {b.E} ({len(h)} pairs; exposes " + ", ".join(f"{s} {e}" for _i, s, e in sorted(x, key=lambda t: t[2])) + ")" for b, h, x in col) or "none"))
    return [b for b in buys if b.eid not in bad]


def enter_beside_buys(E: dict) -> list:
    """ENTER's beside windows (the fit's flickers, the pre-market-flat windows, the held-before-09:35 trades, the pre-market first sightings):
    ONE list for `enter_fit` and the dry run's collision summary (N5), so the two cannot drift."""
    return E["fit_fl"] + E["pre_dated_fit"] + E["pre_und_fit"] + E["held_0935"] + E["prefirst_fit"]


def fit_stage_sets(C: dict) -> dict:
    """{label: (stage whose planned span applies, buys)}: the three fit sets and ENTER's beside windows."""
    I, E = C["I"], C["E"]
    return {"enter": ("enter", E["fit_dated"] + E["fit_und"]), "enter_beside": ("enter", enter_beside_buys(E)),
            "stop": ("stop", I["fit_dated"] + I["fit_und"]), "exit": ("exit", [b for b in I["fit_dated"] if b.has_exit])}


def collision_summary(C: dict, last_seen: "dict | None" = None) -> dict:
    """The dry run's dates-only summary: per fit stage (and ENTER's beside windows, N5) the excluded trades (by name) and the check-side
    trades they would expose; `kept` = the buys each stage keeps."""
    cal = C["cal"]
    forbid = forbidden_pairs(C, last_seen)
    out = {}
    for lab, (st, bs) in fit_stage_sets(C).items():
        col = collisions(st, bs, forbid, cal)
        bad = {b.eid for b, _h, _x in col}
        out[lab] = dict(n=len(bs), excluded=[(b.sym, b.E) for b, _h, _x in col], pairs=sum(len(h) for _b, h, _x in col),
                        exposed=sorted(set().union(*(x for _b, _h, x in col)) if col else set(), key=lambda t: t[2]),
                        kept=[b for b in bs if b.eid not in bad])
    out["forbid"] = forbid
    return out


def speed_trail_bound(b, cal: list, forbid: dict) -> "int | None":
    """X1, dates only: the offset of the first forbidden session inside the speed trail's 121-session forward window (sessions 1 .. HORIZON + 1
    after the buy day, on the pickle calendar), else None — the dry run's count of the kept EXIT fit trades whose ours / his / chosen the fit
    bounds there (`guard_bound_guards`)."""
    for j in range(1, HORIZON + 2):
        i = b.Ei + j
        if i >= len(cal):
            return None
        if (bar_sym(cal[i], b.sym_a, b.sym), cal[i]) in forbid:
            return j
    return None


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the clock-anchored 60-minute bars (§5a / §7a) and the 20-period average on them
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class H60Bar:
    k: int                  # the window's index: 0 = 09:30-10:00, 1 = 10:00-11:00, ...
    lo: int
    hi: int
    o: float
    h: float
    l: float
    c: float
    first_minute: int       # the first present minute in the window
    close_minute: int       # the last present minute in the window (its close is the bar's close)
    n: int


def h60_windows_for(E: str) -> list:
    return R.h60_windows(H60_VARIANT, E in EARLY_CLOSE)


def h60_bars(mb, E: str) -> list:
    """The session's clock-anchored 60-minute bars: [0,29] first (09:30-10:00), then [30,89] ... [330,389] — 7 on a full day, 4 on a listed
    early-close day (minutes >= 210 dropped first, `h60_trim`). A window with no minute is None (no bar). Never a [0,59] first bar."""
    early = E in EARLY_CLOSE
    mb = R.h60_trim(mb, early)
    out = []
    for k, (lo, hi) in enumerate(R.h60_windows(H60_VARIANT, early)):
        sel = (mb.minute >= lo) & (mb.minute <= hi)
        if not sel.any():
            out.append(None)
            continue
        idx = np.flatnonzero(sel)
        out.append(H60Bar(k, lo, hi, fnum(mb.o[idx[0]]), fnum(mb.h[sel].max()), fnum(mb.l[sel].min()), fnum(mb.c[idx[-1]]),
                          int(mb.minute[idx[0]]), int(mb.minute[idx[-1]]), int(len(idx))))
    return out


def next_minute_open(mb, m: int) -> "tuple | None":
    """(minute, open) of the first present minute after m (the session's minutes as stored), or None when none is left in the session."""
    if mb is None:
        return None
    hits = np.flatnonzero(mb.minute > m)
    if not len(hits):
        return None
    return int(mb.minute[hits[0]]), fnum(mb.o[hits[0]])


def ema_series(closes: np.ndarray, n: int = EMA_N, seed_bars: int = EMA_SEED_BARS) -> np.ndarray:
    """The EMA with weight 2 / (n + 1) on each bar's close, seeded with the plain average of the first `seed_bars` closes (the value at index
    seed_bars - 1); nan before the seed completes."""
    c = np.asarray(closes, dtype=float)
    out = np.full(len(c), np.nan)
    if len(c) < seed_bars:
        return out
    alpha = 2.0 / (n + 1.0)
    out[seed_bars - 1] = float(np.mean(c[:seed_bars]))
    for i in range(seed_bars, len(c)):
        out[i] = alpha * c[i] + (1.0 - alpha) * out[i - 1]
    return out


def sma_series_bars(closes: np.ndarray, n: int = EMA_N) -> np.ndarray:
    c = np.asarray(closes, dtype=float)
    out = np.full(len(c), np.nan)
    for i in range(n - 1, len(c)):
        out[i] = float(np.mean(c[i - n + 1:i + 1]))
    return out


@dataclass
class BarSeq:
    """A trade's 60-minute bars in time order over sessions j_from..j_to of its own calendar: items = (j, bar); the EMA and the plain
    average on the closes; the sessions in the range with no minutes (counted); the bars before the buy day (the warm-up)."""
    items: list
    closes: np.ndarray
    ema: np.ndarray
    sma: np.ndarray
    missing_sessions: int
    warmup_bars: int
    j_from: int
    j_to: int

    def index_of_session(self, j: int) -> list:
        return [i for i, (jj, _x) in enumerate(self.items) if jj == j]


def bar_sequence(rec: IRec, store: MinuteStore, j_from: int, j_to: int) -> BarSeq:
    """The bars over sessions j_from..j_to (own calendar; a session beyond the calendar ends the range). Sessions j >= 1 are forward reads
    (the guard)."""
    items, missing = [], 0
    for j in range(j_from, j_to + 1):
        d = rec.session_date(j)
        if d is None:
            break
        bars = rec.h60(store, j) if j != 0 else (h60_bars(rec.mb, rec.b.E) if rec.mb is not None else None)
        if bars is None:
            missing += 1
            continue
        for x in bars:
            if x is not None:
                items.append((j, x))
    closes = np.array([x.c for _j, x in items], dtype=float)
    return BarSeq(items, closes, ema_series(closes), sma_series_bars(closes), missing, sum(1 for j, _x in items if j < 0), j_from, j_to)


def armed_index(seq: BarSeq, fill_minute: "int | None") -> "int | None":
    """The index in `seq.items` of the first completed 60-minute bar after the fill minute: on the buy day a bar whose window ends after the fill
    minute; a close fill (None) arms on the next session's first bar. None when no such bar exists."""
    for i, (j, x) in enumerate(seq.items):
        if j < 0:
            continue
        if j == 0:
            if fill_minute is not None and x.hi > fill_minute:
                return i
            continue
        return i
    return None


def seed_residual(bars_before_armed: int) -> float:
    """The weight the seed keeps at the first armed bar: (1 - alpha)^(bars after the seed)."""
    return (1.0 - EMA_ALPHA) ** max(0, bars_before_armed - EMA_SEED_BARS)


def ema_is_thin(bars_before_armed: int) -> bool:
    return bars_before_armed < EMA_SEED_BARS + EMA_POST_SEED_BARS


# ═════════════════════════════════════════════════════════════════════════════════════════════
# ENTER — L7 / L8 / L9 (the new levels), L1-L6 re-reads, feasibility / HIT / BALLPARK, the two controls, the union
# ═════════════════════════════════════════════════════════════════════════════════════════════
def pivot_floor(b) -> "float | None":
    """Dated BREAKOUT rows keep the previous convention: the level is max(the intraday level, the candidate row's pivot); EP and undated rows
    use the intraday level alone (§5a)."""
    return float(b.pivot) if (b.dated and b.setup in ("breakout", "both") and b.pivot is not None) else None


def floored(x: "float | None", floor: "float | None") -> "float | None":
    if x is None:
        return None
    return max(x, floor) if floor is not None else x


def intraday_levels(rec: IRec) -> dict:
    """L7 the high of the 09:30 minute bar (no bar at minute 0 -> None, `no_bar_0930`) · L8 the max high over minutes 0-29 · L9 the schedule of
    the prior completed 60-minute bar's high (per window k >= 1: bar k-1's high, None when that bar has no minutes). Raw and floored."""
    mb, b = rec.mb, rec.b
    floor = pivot_floor(b)
    sel0 = mb.minute == 0
    L7 = fnum(mb.h[sel0]) if sel0.any() else None
    sel = mb.minute <= 29
    L8 = fnum(mb.h[sel].max()) if sel.any() else None
    bars = h60_bars(mb, b.E)
    sched = [None] + [(bars[k - 1].h if bars[k - 1] is not None else None) for k in range(1, len(bars))]
    return dict(L7_raw=L7, L8_raw=L8, L9_raw=sched, L7=floored(L7, floor), L8=floored(L8, floor), L9=[floored(x, floor) for x in sched],
                windows=R.h60_windows(H60_VARIANT, b.E in EARLY_CLOSE), floor=floor)


def l9_level_at(levels: dict, m: int) -> "float | None":
    """The L9 level in force at minute m: the prior completed bar's high (None before 10:00 or when that bar has no minutes)."""
    for k, (lo, hi) in enumerate(levels["windows"]):
        if lo <= m <= hi:
            return levels["L9"][k] if k >= 1 else None
    return None


def l9_cross(mb, levels: dict) -> "int | None":
    """The FIRST minute of the session from 10:00 whose high exceeds the then-current L9 level (one bar, never 'any bar')."""
    for i in np.flatnonzero(mb.minute >= 30):
        m = int(mb.minute[i])
        lvl = l9_level_at(levels, m)
        if lvl is not None and fnum(mb.h[i]) > lvl:
            return m
    return None


def range_verdict(mb, price: float, flat_m: int, first_m: int, adr20: float) -> tuple:
    """HIT = the price inside [lowest low, highest high] of the window's minutes; BALLPARK = within 0.25 ADR20 of the nearer edge; else MISS;
    no minute in the window -> no_bracket_minutes. -> (verdict, range)."""
    sel = (mb.minute > flat_m) & (mb.minute <= first_m)
    if not sel.any():
        return "no_bracket_minutes", None
    lo, hi = fnum(mb.l[sel].min()), fnum(mb.h[sel].max())
    if lo <= price <= hi:
        return "HIT", (lo, hi)
    if min(abs(price - lo), abs(price - hi)) <= BALLPARK_ADR * adr20 * price:
        return "BALLPARK", (lo, hi)
    return "MISS", (lo, hi)


def score_fixed(mb, level: "float | None", flat_m: int, first_m: int, adr20: float) -> dict:
    """A fixed price level inside the window (flat, first]: the frozen `score_level` (L1-L6, the re-reads — gate (iv) matches them row for row)."""
    s = rev.score_level(mb, level, flat_m, first_m, adr20)
    s["price"] = level
    return s


def first_cross_from(mb, level: "float | None", m_from: int) -> "int | None":
    """The first minute AT OR AFTER `m_from` whose high is above the level (the frozen `first_cross` from a start minute)."""
    if mb is None or level is None or not np.isfinite(level):
        return None
    hits = np.flatnonzero((mb.minute >= m_from) & (mb.h > level))
    return int(mb.minute[hits[0]]) if len(hits) else None


def score_new_fixed(mb, level: "float | None", lv: str, flat_m: int, first_m: int, adr20: float) -> dict:
    """L7 / L8 inside the window: as `score_fixed`, but the crossing is searched from the minute the level EXISTS (L7 from 09:31, L8 from
    10:00 — C14: on a dated breakout row the pivot floor can lift the level above the raw range, and a crossing before the level exists is
    not a crossing he could have bought). On a raw level the two searches agree (no minute inside the range exceeds its own maximum)."""
    out = dict(cross=None, feasible=False, verdict="no_level", range=None, price=level)
    if level is None or not np.isfinite(level):
        return out
    m = first_cross_from(mb, level, LEVEL_EXISTS.get(lv, 0))
    out["cross"] = m
    out["feasible"] = m is not None and flat_m < m <= first_m
    out["verdict"], out["range"] = range_verdict(mb, float(level), flat_m, first_m, adr20)
    return out


def score_l9(mb, levels: dict, flat_m: int, first_m: int, adr20: float) -> dict:
    """L9 inside the window: feasible = the first crossing minute (from 10:00) lies in (flat, first]; HIT / BALLPARK against the level in force
    at first_clock (the value he could have seen at the frame — a reading, listed); that level absent (the prior bar has no minutes) ->
    `no_bar`."""
    out = dict(cross=None, feasible=False, verdict="no_level", range=None, price=None)
    m = l9_cross(mb, levels)
    out["cross"] = m
    out["feasible"] = m is not None and flat_m < m <= first_m
    price = l9_level_at(levels, first_m)
    out["price"] = price
    if price is None:
        out["verdict"] = "no_bar"
        return out
    out["verdict"], out["range"] = range_verdict(mb, price, flat_m, first_m, adr20)
    return out


def no_level_yet(level: str, first_m: int) -> bool:
    return first_m < LEVEL_EXISTS.get(level, 0)


def level_price_fn(level: str, rec: IRec, levels: dict):
    """(cross, price_at(m)) for a level: fixed levels have one price; L9's price is the level in force at m."""
    if level == "L9":
        return l9_cross(rec.mb, levels), (lambda m: l9_level_at(levels, m))
    price = levels.get(level) if level in NEW_LEVELS else rec.levels.get(level)
    if price is None or not np.isfinite(price):
        cross = None
    elif level in NEW_LEVELS:
        cross = first_cross_from(rec.mb, price, LEVEL_EXISTS.get(level, 0))        # C14: from the minute the level exists
    else:
        cross = rev.first_cross(rec.mb, price)
    return cross, (lambda m, _p=price: _p)


def shifted_control(rec: IRec, level: str, cross: "int | None", price_at, n: int = SHIFT_DRAWS) -> dict:
    """§3's shifted-window control: the trade's own width placed at `n` random starts, uniform over [the level's existence minute, the session
    close - width]; key f"intra|bracket|{eid}|{level}|{draw}" (seed 702). A width larger than close - existence -> `no_room`, abstains.
    -> {no_room, feas (bool per draw), hit (bool per draw), feasible_share, hit_share, no_minutes}."""
    flat_m, first_m = hhmm_to_min(rec.b.flat_clock), hhmm_to_min(rec.b.first_clock)
    w = first_m - flat_m
    exist = LEVEL_EXISTS.get(level, 0)
    close = session_end_minute(rec.b.E)
    room = close - w - exist
    if room < 0 or w <= 0:
        return dict(no_room=True, feas=np.zeros(n, dtype=bool), hit=np.zeros(n, dtype=bool), feasible_share=float("nan"), hit_share=float("nan"), no_minutes=0, starts=[])
    feas, hit = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    nomin = 0
    mb = rec.mb
    starts = []
    for d in range(n):
        s = exist + int(rng_for(SHIFT_KEY.format(eid=rec.b.eid, level=level, draw=d)).integers(0, room + 1))
        starts.append(s)
        feas[d] = cross is not None and s < cross <= s + w
        price = price_at(s + w)
        if price is None or not np.isfinite(price):
            continue
        v, _r = range_verdict(mb, float(price), s, s + w, rec.adr20)
        if v == "no_bracket_minutes":
            nomin += 1
        hit[d] = v in ("HIT", "BALLPARK")
    return dict(no_room=False, feas=feas, hit=hit, feasible_share=float(feas.mean()), hit_share=float(hit.mean()), no_minutes=nomin, starts=starts)


def enter_score_trade(rec: IRec, rng, with_shift: bool = True) -> dict:
    """Every level (L7-L9 new; L1-L6 re-reads through the frozen `enter_levels`), the random-price control (identical draws: one 200-draw per
    scorable record from the shared generator), the shifted-window control per level, and the 'any opening range' union. A level that does
    not exist yet at first_clock reads `no_level_yet` (not feasible, neither HIT nor MISS, counted)."""
    flat_m, first_m = hhmm_to_min(rec.b.flat_clock), hhmm_to_min(rec.b.first_clock)
    rec.levels = rev.enter_levels(rec)
    L = intraday_levels(rec)
    rec.levels.update(L7=L["L7"], L8=L["L8"], L9=L["L9"], L7_raw=L["L7_raw"], L8_raw=L["L8_raw"], L9_raw=L["L9_raw"])
    res = {}
    for lv in ALL_LEVELS:
        if no_level_yet(lv, first_m):
            s = dict(cross=None, feasible=False, verdict="no_level_yet", range=None, price=None)
        elif lv == "L9":
            s = score_l9(rec.mb, L, flat_m, first_m, rec.adr20)
        elif lv == "L7" and L["L7"] is None:
            s = dict(cross=None, feasible=False, verdict="no_bar_0930", range=None, price=None)
        elif lv in NEW_LEVELS:
            s = score_new_fixed(rec.mb, L[lv], lv, flat_m, first_m, rec.adr20)
        else:
            s = score_fixed(rec.mb, rec.levels[lv], flat_m, first_m, rec.adr20)
        rec.cross[lv], rec.feasible[lv], rec.verdict[lv] = s["cross"], s["feasible"], s["verdict"]
        res[lv] = s
    # the random-price control: 200 seeded closes of random minutes (the frozen draw), each scored as a level
    ctl = rev.random_levels(rec.mb, RANDOM_LEVELS, rng)
    cf, ch = np.zeros(RANDOM_LEVELS, dtype=bool), np.zeros(RANDOM_LEVELS, dtype=bool)
    for i, lvp in enumerate(ctl):
        s = rev.score_level(rec.mb, fnum(lvp), flat_m, first_m, rec.adr20)
        cf[i], ch[i] = bool(s["feasible"]), s["verdict"] in ("HIT", "BALLPARK")
    res["control"] = dict(feasible_share=float(cf.mean()), hit_share=float(ch.mean()), feas=cf, hit=ch)
    # the shifted-window control, per level (each level keeps its own key)
    res["shift"] = {}
    if with_shift:
        for lv in ALL_LEVELS:
            cross, price_at = level_price_fn(lv, rec, L)
            res["shift"][lv] = shifted_control(rec, lv, cross, price_at)
    # the union "any opening range": feasible when the first crossing of ANY of L7 / L1 / L8 lies inside the window; hit when any of them hits
    res["union"] = dict(feasible=any(res[lv]["feasible"] for lv in UNION_LEVELS), hit=any(res[lv]["verdict"] in ("HIT", "BALLPARK") for lv in UNION_LEVELS),
                        control_feasible=res["control"]["feasible_share"], control_hit=res["control"]["hit_share"])
    if with_shift:
        uf = np.zeros(SHIFT_DRAWS, dtype=bool)
        uh = np.zeros(SHIFT_DRAWS, dtype=bool)
        for lv in UNION_LEVELS:
            uf |= res["shift"][lv]["feas"]
            uh |= res["shift"][lv]["hit"]
        res["union"].update(shift_feasible=float(uf.mean()), shift_hit=float(uh.mean()))
    return res


def enter_summary(scored: dict) -> dict:
    """Per level: feasible / hit-or-ballpark counts and shares with the 95% interval, the verdict counts; the random-price control (the mean of
    the per-record shares); the shifted-window control per level (records with room only; no_room counted); the union and its controls."""
    n = len(scored)
    out = {"n": n}
    for lv in ALL_LEVELS:
        f = sum(1 for r in scored.values() if r[lv]["feasible"])
        h = sum(1 for r in scored.values() if r[lv]["verdict"] in ("HIT", "BALLPARK"))
        sh = [r["shift"][lv] for r in scored.values() if r.get("shift") and lv in r["shift"]]
        room = [s for s in sh if not s["no_room"]]
        out[lv] = dict(feasible=f, hit=h, feasible_share=binom_ci(f, n), hit_share=binom_ci(h, n), verdicts=Counter(r[lv]["verdict"] for r in scored.values()),
                       shift_feasible=float(np.mean([s["feasible_share"] for s in room])) if room else float("nan"),
                       shift_hit=float(np.mean([s["hit_share"] for s in room])) if room else float("nan"),
                       shift_no_room=len(sh) - len(room), shift_n=len(room))
    out["control"] = dict(feasible_share=float(np.mean([r["control"]["feasible_share"] for r in scored.values()])) if n else float("nan"),
                          hit_share=float(np.mean([r["control"]["hit_share"] for r in scored.values()])) if n else float("nan"))
    uf = sum(1 for r in scored.values() if r["union"]["feasible"])
    uh = sum(1 for r in scored.values() if r["union"]["hit"])
    us = [r["union"]["shift_feasible"] for r in scored.values() if "shift_feasible" in r["union"]]
    out["union"] = dict(feasible=uf, hit=uh, feasible_share=binom_ci(uf, n), hit_share=binom_ci(uh, n), control_feasible=out["control"]["feasible_share"],
                        shift_feasible=float(np.mean(us)) if us else float("nan"))
    return out


def choose_level(summary: dict) -> str:
    """The highest feasible share among L7-L9 on the deciding fit windows; ties -> L8 (the article's own hourly entry) when L8 is tied, else the
    first in order."""
    best = max(summary[lv]["feasible"] for lv in NEW_LEVELS)
    tied = [lv for lv in NEW_LEVELS if summary[lv]["feasible"] == best]
    return "L8" if "L8" in tied else tied[0]


def control_bar(summary: dict, lv: str) -> tuple:
    """(random-price control feasible share, shifted-window control feasible share) for a level."""
    return summary["control"]["feasible_share"], summary[lv]["shift_feasible"]


def enter_verdict(summary: dict, chosen: str) -> tuple:
    """§5d on the deciding set: n <= 39 -> INCONCLUSIVE-by-size; PASS = feasible >= 50% AND >= each control + 15 points AND hit-or-ballpark
    >= 70% (a floor only); FAIL otherwise (the falsifier line names whether any new level reaches 50%)."""
    n = summary["n"]
    if n < ENTER_MIN_CHECK:
        return "INCONCLUSIVE-by-size", [f"{n} records (< {ENTER_MIN_CHECK})"]
    fs, hs = summary[chosen]["feasible_share"][0], summary[chosen]["hit_share"][0]
    cf, sf = control_bar(summary, chosen)
    reasons = []
    if fs < ENTER_PASS_FEASIBLE:
        reasons.append(f"feasible {pct(fs)} < {pct(ENTER_PASS_FEASIBLE)}")
    if not fs >= cf + ENTER_CONTROL_MARGIN:
        reasons.append(f"feasible {pct(fs)} not >= random-price control {pct(cf)} + 15")
    if np.isfinite(sf) and not fs >= sf + ENTER_CONTROL_MARGIN:
        reasons.append(f"feasible {pct(fs)} not >= shifted-window control {pct(sf)} + 15")
    if not np.isfinite(sf):
        reasons.append("the shifted-window control could not be read (no record with room)")
    if hs < ENTER_HIT_FLOOR:
        reasons.append(f"hit-or-ballpark {pct(hs)} < {pct(ENTER_HIT_FLOOR)}")
    if not reasons:
        return "PASS", []
    if all(summary[lv]["feasible_share"][0] < ENTER_PASS_FEASIBLE for lv in NEW_LEVELS):
        reasons.append("falsifier: no new level >= 50% feasible")
    return "FAIL", reasons


def enter_veto(summary_virgin: dict, chosen: str) -> tuple:
    """§5d's sign veto on the untouched non-flicker windows: fewer than 5 scorable -> abstains; the chosen level's feasible share STRICTLY below
    the larger of the two controls' feasible shares there -> a PASS reads INCONCLUSIVE. -> (fires, text)."""
    n = summary_virgin["n"]
    if n < ENTER_VETO_MIN:
        return False, f"abstains ({n} scorable untouched windows < {ENTER_VETO_MIN})"
    fs = summary_virgin[chosen]["feasible_share"][0]
    cf, sf = control_bar(summary_virgin, chosen)
    bar = max(x for x in (cf, sf) if np.isfinite(x)) if any(np.isfinite(x) for x in (cf, sf)) else float("nan")
    fires = np.isfinite(bar) and fs < bar
    return bool(fires), f"{chosen} feasible {pct(fs)} vs the larger control {pct(bar)} on {n} untouched windows -> {'VETO' if fires else 'no veto'}"


def registered_fill(rec: IRec) -> tuple:
    """The registered fill (the frozen reading): dated = ORH5 where it filled (else the close-fill proxy); undated = the open of the buy day."""
    return rev.registered_fill(rec)


def chain_fill(rec: IRec, chosen_level: "str | None", mis: dict) -> None:
    """§4: the chosen level's price where it is feasible on the trade (the fill minute = its crossing minute; L9's price = the level in force at
    the crossing); otherwise the registered fill, flagged `fill_fallback` when a level was chosen."""
    if chosen_level and rec.mb is not None and rec.b.in_bracket and clock_sane(rec.b, mis) == "ok":
        flat_m, first_m = hhmm_to_min(rec.b.flat_clock), hhmm_to_min(rec.b.first_clock)
        if not no_level_yet(chosen_level, first_m):
            L = intraday_levels(rec)
            if chosen_level == "L9":
                m = l9_cross(rec.mb, L)
                price = l9_level_at(L, m) if m is not None else None
                feasible = m is not None and flat_m < m <= first_m and price is not None
            else:
                s = score_new_fixed(rec.mb, L[chosen_level], chosen_level, flat_m, first_m, rec.adr20)
                m, price, feasible = s["cross"], L[chosen_level], s["feasible"]
            if feasible:
                rec.fill, rec.fill_minute, rec.fill_src, rec.fill_fallback = float(price), int(m), f"level:{chosen_level}", False
                rec.day0 = {}
                return
    rec.fill, rec.fill_minute, rec.fill_src, d0 = registered_fill(rec)
    rec.fill_fallback = chosen_level is not None
    rec.day0 = d0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# STOP — S1 / S3 / S9 / S10 (+ the controls) under T / C / H with the buy-day certainty rule; the choice; the walks; the risk
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_minute_of(rec: IRec) -> "int | None":
    """The read minute for S9 / S10: first_clock when the buy day carries an IN-SESSION holding frame, else the fill minute (None for a close fill)."""
    b = rec.b
    if b.first_clock and b.f_ctx == "in":
        m = hhmm_to_min(b.first_clock)
        if m is not None and m >= 0:
            return m
    return rec.fill_minute


def stop_levels_intra(rec: IRec) -> dict:
    """S1 the low of the day up to the fill minute (the frozen reading; `S1_is_S2` when the fill minute is unknown) · S3 the prior session's low
    · S9 the 09:30-10:00 low at the read minute (read minute before 10:00 or unknown -> S1, `S9_is_S1`) · S10 the low of the last COMPLETED
    60-minute bar before the read minute (none -> S1, `S10_is_S1`) · S8 and the 50-day (controls)."""
    s1_minute = rec.fill_minute if rec.fill_src.startswith(("level", "orh5")) else None
    base = rev.stop_levels(rec, s1_minute)
    S = {"S1": base["S1"], "S1_is_S2": bool(base["S1_is_S2"]), "S3": base["S3"], "S8": base["S8"], "SMA50": base["SMA50"]}
    rm = read_minute_of(rec)
    rec.read_minute = rm
    S["S9"], S["S9_is_S1"] = S["S1"], True
    S["S10"], S["S10_is_S1"] = S["S1"], True
    if rec.mb is not None and rm is not None and rm >= 30:
        sel = rec.mb.minute <= 29
        if sel.any():
            S["S9"], S["S9_is_S1"] = fnum(rec.mb.l[sel].min()), False
        done = [x for x in h60_bars(rec.mb, rec.b.E) if x is not None and x.hi < rm]
        if done:
            S["S10"], S["S10_is_S1"] = done[-1].l, False
    return S


def first_touch_minute(mb, L: float, after_m: int = -1) -> "int | None":
    """The first minute after `after_m` whose low is at or under L or whose open is under it (a touch); None when none (or no minutes)."""
    if mb is None:
        return None
    hit = np.flatnonzero((mb.minute > after_m) & ((mb.l <= L) | (mb.o < L)))
    return int(mb.minute[hit[0]]) if len(hit) else None


def held_through_intra(rec: IRec, name, variant: str, smas: dict, sight, store: MinuteStore) -> dict:
    """§6a on one trade and one (level, variant): traded through on any session <= exit_hi (the denominator), on a session he CERTAINLY held
    (the numerator), unresolved. The buy-day certainty rule for T and H: an event at or after first_clock is certain; between the later of
    (fill minute, flat_clock) and first_clock unresolved; at or before flat_clock not an event (the scan goes on — later minutes of the buy
    day, then later sessions; a reading, listed); no in-session holding frame on the buy day -> every buy-day event unresolved. On exit_lo:
    T needs the touch minute before the last in-session frame's clock, H the bar's close minute before it, C a frame after the close. A
    still-held trade contributes its certain sessions up to its last frame. H abstains for a session with no 60-minute bar (`no_bar`)."""
    b = rec.b
    lvl = rec.stop_levels[name] if isinstance(name, str) else name
    is_day_low = isinstance(name, str) and rec.stop_levels.get("S1_is_S2") and (name == "S1" or (name in ("S9", "S10") and rec.stop_levels.get(f"{name}_is_S1")))
    j0 = 1 if (variant == "T" and is_day_low) else 0
    J = rec.exit_hi_j if rec.exit_hi_j is not None else rec.last_j
    out = dict(any=False, certain=False, unresolved=False, first_j=None, note="", event_m=None, no_bar_sessions=0)
    if J is None:
        return out
    lo_j = rec.exit_lo_j if rec.exit_lo_j is not None else J + 1
    first_m = hhmm_to_min(b.first_clock) if (b.first_clock and b.f_ctx == "in") else None
    if first_m is not None and first_m < 0:
        first_m = None
    flat_m = hhmm_to_min(b.flat_clock) if b.flat_clock else None
    if flat_m is not None and flat_m < 0:
        flat_m = None
    for j in range(j0, J + 1):
        k = rec.bar_at(j)
        if k is None:
            out["note"] = "hole"
            break
        L = rev.level_at(rec, lvl, j, smas)
        if not np.isfinite(L):
            continue
        through, m = False, None
        if variant == "C":
            through = fnum(rec.bars.c[k]) < L
        elif variant == "T":
            if j == 0:
                if rec.mb is not None and rec.fill_minute is not None:
                    lower = max(rec.fill_minute, flat_m if flat_m is not None else -1)
                    m = first_touch_minute(rec.mb, L, lower)
                    through = m is not None
                elif rec.fill_minute == 0:
                    through = fnum(rec.bars.l[k]) <= L            # an open fill without minutes: the minute unknown
                else:
                    if fnum(rec.bars.l[k]) <= L:
                        out["unresolved"] = True                   # a close fill: a day-0 touch may precede the fill
                    continue
            else:
                through = fnum(rec.bars.l[k]) <= L
                if through and j == lo_j:
                    m = first_touch_minute(rec.minutes(store, j), L)
        else:
            bars = rec.h60(store, j) if j >= 1 else (h60_bars(rec.mb, b.E) if rec.mb is not None else None)
            if bars is None:
                out["no_bar_sessions"] += 1
                out["note"] = "no_bar"
                continue
            if j == 0:
                if rec.fill_minute is None:
                    continue
                lower = max(rec.fill_minute, flat_m if flat_m is not None else -1)
                cands = [x for x in bars if x is not None and x.close_minute > lower]
            else:
                cands = [x for x in bars if x is not None]
            for x in cands:
                if x.c < L:
                    through, m = True, x.close_minute
                    break
        if not through:
            continue
        out["any"] = True
        if out["first_j"] is None:
            out["first_j"] = j
        out["event_m"] = m
        if j == 0 and variant != "C":
            if first_m is None or m is None:
                out["unresolved"] = True
            elif m >= first_m:
                if j == lo_j:
                    c_last = sight.last_in_session_clock(b.exit_lo, b.sym)
                    out["certain"] = c_last is not None and m < hhmm_to_min(c_last)
                else:
                    out["certain"] = True
            else:
                out["unresolved"] = True
            break
        if j < lo_j:
            out["certain"] = True
            break
        if j == lo_j:
            if variant == "C":
                out["certain"] = bool(sight.after_close_frame(b.exit_lo, b.sym))
            else:
                c_last = sight.last_in_session_clock(b.exit_lo, b.sym)
                if c_last is None or m is None:
                    out["unresolved"] = True
                elif m < hhmm_to_min(c_last):
                    out["certain"] = True
            break
        break
    return out


def stop_table_intra(recs: list, sight, store: MinuteStore, levels=STOP_LEVELS + STOP_CONTROLS, variants=STOP_VARIANTS) -> dict:
    """{(level, variant): {n, any, certain, unresolved, H_cond, H_all, tight, eligible, differ, no_bar}} over `recs` (each with fill, stop_levels)."""
    out = {}
    for Lname in levels:
        for V in variants:
            n_any = n_cert = n_unres = n_nobar = 0
            tight, differ = [], 0
            for r in recs:
                lvl = r.stop_levels.get(Lname)
                if lvl is None:
                    continue
                smas = smas_for(r.bars)
                L0 = rev.level_at(r, lvl, 0, smas)
                if np.isfinite(L0) and r.fill:
                    tight.append((r.fill - L0) / r.fill)
                if Lname in ("S9", "S10"):
                    differ += int(not r.stop_levels.get(f"{Lname}_is_S1", True))
                h = held_through_intra(r, Lname, V, smas, sight, store)
                n_any += int(h["any"]); n_cert += int(h["certain"]); n_unres += int(h["unresolved"]); n_nobar += int(h["no_bar_sessions"] > 0)
            out[(Lname, V)] = dict(n=len(recs), any=n_any, certain=n_cert, unresolved=n_unres,
                                   H_cond=(n_cert / n_any) if n_any else float("nan"), H_all=(n_cert / len(recs)) if recs else float("nan"),
                                   tight=float(np.median(tight)) if tight else float("nan"), eligible=n_any >= STOP_MIN_TRADED,
                                   differ=differ if Lname in ("S9", "S10") else len(recs), no_bar=n_nobar)
    return out


def choose_stop(table: dict, levels=STOP_LEVELS, variants=STOP_VARIANTS) -> "tuple | None":
    """His stop ~ the tightest (level, variant) with a positive median width, >= 20 traded through on the fit and H_cond <= 10%, among the 12
    cells (S8 and the 50-day never); ties on the width -> T, then C, then H (a reading, listed)."""
    cands = []
    for Lname in levels:
        for V in variants:
            t = table[(Lname, V)]
            if t["eligible"] and np.isfinite(t["H_cond"]) and t["H_cond"] <= STOP_H_CHOOSE and np.isfinite(t["tight"]) and t["tight"] > 0:
                cands.append((t["tight"], STOP_VARIANT_TIE[V], levels.index(Lname), Lname, V))
    if not cands:
        return None
    c = min(cands)
    return c[3], c[4]


def stop_verdict(chk_table: dict, chosen: "tuple | None") -> tuple:
    """§6b on the deciding set: no cell chosen on the fit -> INCONCLUSIVE; fewer than 20 traded through there -> INCONCLUSIVE-by-size; S9 / S10
    chosen with fewer than 20 records differing from S1 -> INCONCLUSIVE-by-size; H_cond <= 15% -> PASS; else FAIL (the falsifier line says
    whether every cell is above 30%)."""
    if chosen is None:
        return "INCONCLUSIVE", ["no cell met H_cond <= 10% on the fit (with >= 20 traded through and a positive width)"]
    t = chk_table[chosen]
    name = f"{chosen[0]}-{chosen[1]}"
    if t["any"] < STOP_MIN_TRADED:
        return "INCONCLUSIVE-by-size", [f"{name}: only {t['any']} trades traded through on the deciding set (< {STOP_MIN_TRADED})"]
    if chosen[0] in ("S9", "S10") and t["differ"] < STOP_MIN_DIFFER:
        return "INCONCLUSIVE-by-size", [f"{name}: only {t['differ']} deciding records differ from S1 (< {STOP_MIN_DIFFER})"]
    if t["H_cond"] <= STOP_H_PASS:
        return "PASS", [f"{name} H_cond {pct(t['H_cond'])} <= {pct(STOP_H_PASS)} ({t['certain']} / {t['any']})"]
    reasons = [f"{name} H_cond {pct(t['H_cond'])} > {pct(STOP_H_PASS)} ({t['certain']} / {t['any']})"]
    every = all(chk_table[(l, v)]["H_cond"] > STOP_H_FALSIFY for l in STOP_LEVELS for v in STOP_VARIANTS if np.isfinite(chk_table[(l, v)]["H_cond"]))
    reasons.append("falsifier: every cell > 30% -> his stop is not a fixed intraday level either" if every else "some cell <= 30% on the deciding set")
    return "FAIL", reasons


def spearman_cells(fit_table: dict, chk_table: dict, recs: list) -> tuple:
    """Beside: the 12 cells ordered by H_cond on the fit vs the check (ties at average rank), cells equal to S1 on more than half their records
    left out. -> (rho, cells used)."""
    used = []
    for Lname in STOP_LEVELS:
        for V in STOP_VARIANTS:
            if Lname in ("S9", "S10"):
                n = len(recs)
                same = sum(1 for r in recs if r.stop_levels.get(f"{Lname}_is_S1", True))
                if n and same > n / 2:
                    continue
            if np.isfinite(fit_table[(Lname, V)]["H_cond"]) and np.isfinite(chk_table[(Lname, V)]["H_cond"]):
                used.append((Lname, V))
    if len(used) < 3:
        return float("nan"), used
    return spearman([fit_table[c]["H_cond"] for c in used], [chk_table[c]["H_cond"] for c in used]), used


def stop_walk_h(rec: IRec, lvl, smas: dict, store: MinuteStore, J: int) -> tuple:
    """The H variant's actual exit before or at session J: the first 60-minute bar closing below the level (on the buy day: bars completing after
    the fill minute) -> sold at the next minute's open (the day's last bar -> the next session's open); else the close of J. -> (j, price, kind)."""
    L0 = rev.level_at(rec, lvl, 0, smas)
    if rec.mb is not None and rec.fill_minute is not None and np.isfinite(L0):
        for x in h60_bars(rec.mb, rec.b.E):
            if x is not None and x.hi > rec.fill_minute and x.close_minute > rec.fill_minute and x.c < L0:
                nx = next_minute_open(R.h60_trim(rec.mb, rec.b.E in EARLY_CLOSE), x.close_minute)
                if nx is not None:
                    return 0, nx[1], "stop_h"
                kn = rec.bar_at(1)
                return (1, fnum(rec.bars.o[kn]), "stop_h_nextopen") if kn is not None else (0, fnum(rec.bars.c[rec.e]), "mark_hole")
    for j in range(1, J + 1):
        k = rec.bar_at(j)
        if k is None:
            kk = rec.bar_at(j - 1)
            return j - 1, fnum(rec.bars.c[kk]), "mark_hole"
        L = rev.level_at(rec, lvl, j, smas)
        if not np.isfinite(L):
            continue
        bars = rec.h60(store, j)
        if bars is None:
            continue
        for x in bars:
            if x is not None and x.c < L:
                mb = rec.minutes(store, j)
                nx = next_minute_open(R.h60_trim(mb, rec.session_date(j) in EARLY_CLOSE), x.close_minute)
                if nx is not None:
                    return j, nx[1], "stop_h"
                kn = rec.bar_at(j + 1)
                return (j + 1, fnum(rec.bars.o[kn]), "stop_h_nextopen") if kn is not None else (j, fnum(rec.bars.c[k]), "mark_hole")
    kJ = rec.bar_at(J)
    return J, fnum(rec.bars.c[kJ]) if kJ is not None else float("nan"), "mark"


def stop_walk_cell(rec: IRec, lvl, variant: str, smas: dict, store: MinuteStore, J: int) -> tuple:
    if variant == "H":
        return stop_walk_h(rec, lvl, smas, store, J)
    return rev.stop_walk(rec, lvl, variant, smas, J)


def order_of(kind: str) -> int:
    """The order code a sell kind implies: at the open (a gap under the level, a close-based stop's next open, the next session's open after the day's
    last bar), at the close (marks and cuts), else intraday (a touch, a bar's next minute)."""
    if kind in ("stop_gap", "stop_close", "stop_h_nextopen", "trail", "gap_open"):
        return ORDER_OPEN
    if kind.startswith("mark") or kind.startswith("cut") or kind in ("sell_close", "partial"):
        return ORDER_CLOSE
    return ORDER_INTRADAY


def simple_leg_trade(rec: IRec, j: int, px: float, kind: str, width: float, map_b, cal_len: int):
    """One sell leg at session j for the account simulation (the order by its kind); None when unbuildable."""
    return make_legs_trade(rec, [Leg(j, None, px, kind, 1.0, order_of(kind))], width, map_b, cal_len)


def risk_readout(say, label: str, trades: list, cal_u: list, w0: int) -> dict:
    """§6a's readout per cell: the realised R of stop-outs (worst, 5th percentile, shares beyond -1R / -1.5R / -2R), the largest single-trade
    loss as % of equity, the account's max drawdown and final equity (the frozen `simulate` at cap_30)."""
    stops = [t for t in trades if t.status.startswith("stop") or t.status.startswith("day0")]
    r = np.array([t.realized_r for t in stops], dtype=float)
    loss_pct = [min(CAP30.risk / t.width, CAP30.cap) * (t.legs[0][3] / t.fill - 1.0) for t in trades]
    sim = rp.simulate(trades, CAP30, [date.fromisoformat(d) for d in cal_u], w0) if trades else None
    out = dict(n=len(trades), stops=len(stops), worst=float(r.min()) if len(r) else float("nan"), p5=float(np.percentile(r, 5)) if len(r) else float("nan"),
               beyond_1=float(np.mean(r < -1.0)) if len(r) else float("nan"), beyond_1_5=float(np.mean(r < -1.5)) if len(r) else float("nan"),
               beyond_2=float(np.mean(r < -2.0)) if len(r) else float("nan"), worst_loss_pct=float(min(loss_pct)) if loss_pct else float("nan"),
               max_dd=sim["max_dd"] if sim else float("nan"), final=sim["final"] if sim else float("nan"))
    say(f"    {label}: trades {out['n']}, stop-outs {out['stops']}; realised R of stop-outs worst {out['worst']:+.2f}, 5th pct {out['p5']:+.2f}, beyond -1R "
        f"{pct(out['beyond_1'])}, beyond -1.5R {pct(out['beyond_1_5'])}, beyond -2R {pct(out['beyond_2'])}; largest single-trade loss {pct(out['worst_loss_pct'], 2)} of equity; "
        f"account max DD {pct(out['max_dd'])}, final {out['final']:.3f}")
    return out


def apply_chain(recs: list, chosen_level: "str | None", chosen_stop: "tuple | None", mis: dict) -> Counter:
    """ENTER's fill then STOP's level on every record (the registered readings where a stage did not pass or has not run). `r.stop` = the chosen
    stop's buy-day price (sizing, the R unit); `r.stop_lvl` the level object the walks follow; `r.stop_variant` T / C / H."""
    c = Counter()
    for r in recs:
        chain_fill(r, chosen_level, mis)
        c["fill_" + r.fill_src] += 1
        c["fill_fallback"] += int(r.fill_fallback)
        r.stop_levels = stop_levels_intra(r)
        c["S1_is_S2"] += int(r.stop_levels["S1_is_S2"])
        c["S9_is_S1"] += int(r.stop_levels["S9_is_S1"])
        c["S10_is_S1"] += int(r.stop_levels["S10_is_S1"])
        smas = smas_for(r.bars)
        if chosen_stop:
            r.stop_lvl = r.stop_levels[chosen_stop[0]]
            r.stop, r.stop_src, r.stop_variant = rev.level_at(r, r.stop_lvl, 0, smas), f"{chosen_stop[0]}-{chosen_stop[1]}", chosen_stop[1]
        else:
            r.stop, r.stop_src = (r.stop_levels["S1"], "S1-T") if r.b.dated else (r.fill * (1.0 - r.adr20), "ADR20-T")
            r.stop_lvl, r.stop_variant = r.stop, "T"
        if not (np.isfinite(r.stop) and r.stop < r.fill):
            r.stop, r.stop_src = r.fill * (1.0 - r.adr20), r.stop_src + "->ADR20"
            r.stop_lvl, r.stop_variant = r.stop, "T"
            c["stop_above_fill_fallback"] += 1
        r.day0 = rev.day0_for(r, r.fill_minute, r.stop) if r.stop_variant == "T" else dict(cb._NO_DAY0)
    return c


# ═════════════════════════════════════════════════════════════════════════════════════════════
# EXIT — the FSLY rule on the 60-minute 20-EMA: E1-E4 under the chain's stop; the legs; the three accounts; recovery; the vetoes
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Leg:
    j: int                  # the session the leg is BOOKED on (a next-session open books on j + 1)
    minute: "int | None"    # the minute inside that session (None: the open / the close)
    px: float
    kind: str
    frac: float
    order: int              # ORDER_OPEN / ORDER_INTRADAY / ORDER_CLOSE


def prior_low(rec: IRec, j: int) -> "float | None":
    """The prior session's low for session j (the session before the buy day for j = 0), on consecutive bars only."""
    k = rec.bar_at(j - 1) if j >= 1 else rec.p
    return fnum(rec.bars.l[k]) if k is not None and k >= 0 else None


def stop_event(rec: IRec, j: int, smas: dict, store: MinuteStore, seq: "BarSeq | None" = None) -> "tuple | None":
    """The chain's stop on session j, if it fires: (minute_or_None, price, kind). T: day 0 = the day-0 walk after the fill; j >= 1 a gap open
    under the level (at the open) or a low at it (at the level). C: the prior close below the prior level -> this open. H: the first
    60-minute bar closing below -> the next minute's open (the day's last bar -> the next session's open, booked on j + 1: returned as
    kind 'stop_h_nextopen' with minute None)."""
    lvl, V = rec.stop_lvl, rec.stop_variant
    k = rec.bar_at(j)
    if k is None:
        return None
    L = rev.level_at(rec, lvl, j, smas)
    if V == "T":
        if j == 0:
            d0 = rec.day0 if rec.day0 else rev.day0_for(rec, rec.fill_minute, L)
            if d0.get("stopped"):
                return d0.get("exit_minute"), float(d0["exit_price"]), "day0_gap" if float(d0["exit_price"]) < L else "day0_stop"
            return None
        if not np.isfinite(L):
            return None
        if fnum(rec.bars.o[k]) < L:
            return 0, fnum(rec.bars.o[k]), "stop_gap"
        if fnum(rec.bars.l[k]) <= L:
            m = first_touch_minute(rec.minutes(store, j), L)
            return m, L, "stop"
        return None
    if V == "C":
        if j == 0:
            return None
        kp = rec.bar_at(j - 1)
        Lp = rev.level_at(rec, lvl, j - 1, smas)
        if kp is not None and np.isfinite(Lp) and fnum(rec.bars.c[kp]) < Lp:
            return 0, fnum(rec.bars.o[k]), "stop_close"
        return None
    # H
    if not np.isfinite(L):
        return None
    bars = (h60_bars(rec.mb, rec.b.E) if rec.mb is not None else None) if j == 0 else rec.h60(store, j)
    if bars is None:
        return None
    for x in bars:
        if x is None:
            continue
        if j == 0 and (rec.fill_minute is None or x.hi <= rec.fill_minute):
            continue
        if x.c < L:
            mb = rec.mb if j == 0 else rec.minutes(store, j)
            nx = next_minute_open(R.h60_trim(mb, rec.session_date(j) in EARLY_CLOSE), x.close_minute)
            if nx is not None:
                return nx[0], nx[1], "stop_h"
            return None, float("nan"), "stop_h_nextopen"
    return None


def exit_walk_intra(rec: IRec, variant: str, seq: BarSeq, armed: int, store: MinuteStore, smas: dict, J_tail: int, avg: str = "ema",
                    second_close: bool = False, tail_kind: str = "cut_at_tail") -> dict:
    """E1-E4 from the first armed bar under the chain's stop (the stop pre-empts any leg inside a session — a reading, listed). E1 all out at the
    first 60-minute close below the average (sold at the next minute's open; the day's last bar -> the next session's open). E2 half at E1's
    bar, the rest at the first daily close below the prior session's low (sold at the next open); E3 half at E1's bar, the rest at an intraday
    touch of the prior session's low (sold at the level; a gap below it -> the open); E2 / E3 all out when their prior-low event comes before
    E1's bar. E4 all out at the touch. The walk is cut at J_tail (booked at that close, `tail_kind`), at a hole (`mark_hole`).
    -> dict(legs, half_j, last_j, cut, stop_preempt, e1_j)."""
    legs, rem = [], 1.0
    a = seq.ema if avg == "ema" else seq.sma
    out = dict(legs=legs, half_j=None, last_j=None, cut="", stop_preempt=False, e1_j=None)
    below_seen = 0
    armed_j, armed_close_m = seq.items[armed][0], seq.items[armed][1].close_minute      # the armed session and the armed bar's close minute (C15)
    for j in range(0, J_tail + 1):
        k = rec.bar_at(j)
        if k is None:
            kk = rec.bar_at(j - 1)
            if kk is not None and rem > 0:
                legs.append(Leg(j - 1, None, fnum(rec.bars.c[kk]), "mark_hole", rem, ORDER_CLOSE))
                rem = 0.0
            out["cut"] = "hole"
            break
        # the stop first
        se = stop_event(rec, j, smas, store, seq)
        if se is not None:
            m, px, kind = se
            if kind == "stop_h_nextopen":
                kn = rec.bar_at(j + 1)
                if kn is not None:
                    legs.append(Leg(j + 1, None, fnum(rec.bars.o[kn]), kind, rem, ORDER_OPEN))
                else:
                    legs.append(Leg(j, None, fnum(rec.bars.c[k]), "mark_hole", rem, ORDER_CLOSE))
                    out["cut"] = "hole"
            else:
                legs.append(Leg(j, m, px, kind, rem, ORDER_OPEN if kind in ("stop_gap", "stop_close") else ORDER_INTRADAY))
            rem = 0.0
            out["stop_preempt"] = True
            break
        # the events of session j, in minute order: (minute, type, price_fn)
        events = []
        mb_j = rec.mb if j == 0 else rec.minutes(store, j)
        early = rec.session_date(j) in EARLY_CLOSE
        if variant in ("E1", "E2", "E3"):
            for i, (jj, x) in enumerate(seq.items):
                if jj != j or i < armed:
                    continue
                if np.isfinite(a[i]) and x.c < a[i]:
                    below_seen += 1
                    if second_close and below_seen < 2:
                        continue
                    nx = next_minute_open(R.h60_trim(mb_j, early), x.close_minute) if mb_j is not None else None
                    if nx is not None:
                        events.append((x.close_minute, "e1", nx[1], ORDER_INTRADAY, j))
                    else:
                        kn = rec.bar_at(j + 1)
                        if kn is not None:
                            events.append((x.close_minute, "e1", fnum(rec.bars.o[kn]), ORDER_OPEN, j + 1))
                        else:
                            events.append((x.close_minute, "e1", fnum(rec.bars.c[k]), ORDER_CLOSE, j))
                    break
        PL = prior_low(rec, j)
        if variant in ("E3", "E4") and PL is not None:
            # a prior-low touch counts only once the armed bar has completed: no touch before the armed session, touches after the armed
            # bar's close minute on the armed session (whatever its j), any minute on later sessions (C15)
            after = 10 ** 6 if j < armed_j else (armed_close_m if j == armed_j else -1)
            if after < 10 ** 6:
                if mb_j is not None:
                    m = first_touch_minute(R.h60_trim(mb_j, early), PL, after)
                    if m is not None:
                        i = int(np.searchsorted(mb_j.minute, m))
                        o_m = fnum(mb_j.o[i])
                        events.append((m, "touch", o_m if o_m < PL else PL, ORDER_INTRADAY, j))
                elif j >= 1:
                    if fnum(rec.bars.o[k]) < PL:
                        events.append((0, "touch", fnum(rec.bars.o[k]), ORDER_OPEN, j))
                    elif fnum(rec.bars.l[k]) <= PL:
                        events.append((10 ** 5, "touch", PL, ORDER_INTRADAY, j))     # the minute unknown: after any bar event (a reading)
        if variant == "E2" and PL is not None and j >= armed_j:          # the daily close is after any bar of its session: counted from the armed session on (C15)
            if fnum(rec.bars.c[k]) < PL:
                kn = rec.bar_at(j + 1)
                if kn is not None:
                    events.append((session_end_minute(rec.session_date(j)), "dclose", fnum(rec.bars.o[kn]), ORDER_OPEN, j + 1))
                else:
                    events.append((session_end_minute(rec.session_date(j)), "dclose", fnum(rec.bars.c[k]), ORDER_CLOSE, j))
        events.sort(key=lambda t: (t[0], 0 if t[1] == "e1" else 1))
        for m, typ, px, order, jb in events:
            if rem <= 0:
                break
            if variant == "E1":
                legs.append(Leg(jb, m, px, "e1", rem, order)); rem = 0.0
                out["e1_j"] = jb
            elif variant == "E4":
                legs.append(Leg(jb, m, px, "touch", rem, order)); rem = 0.0
            else:
                second = "dclose" if variant == "E2" else "touch"
                if typ == "e1" and out["half_j"] is None and rem == 1.0:
                    legs.append(Leg(jb, m, px, "e1_half", 0.5, order)); rem = 0.5
                    out["half_j"], out["e1_j"] = jb, jb
                elif typ == second:
                    legs.append(Leg(jb, m, px, second if rem < 1.0 else second + "_all", rem, order)); rem = 0.0
        if rem <= 0:
            break
    if rem > 0:
        kJ = rec.bar_at(J_tail)
        if kJ is not None:
            legs.append(Leg(J_tail, None, fnum(rec.bars.c[kJ]), tail_kind, rem, ORDER_CLOSE))
            out["cut"] = out["cut"] or "tail"
        rem = 0.0
    out["last_j"] = max(lg.j for lg in legs) if legs else None
    return out


def make_legs_trade(rec: IRec, legs: list, width: float, map_b, cal_len: int):
    """A multi-leg Trade for the account simulation (fractions sum to 1); None when unbuildable."""
    if not legs or not (width > 0):
        return None
    fill, stop = float(rec.fill), float(rec.fill) * (1.0 - width)
    ci0 = rec.e_ci
    if any(not np.isfinite(lg.px) for lg in legs):
        return None
    rp_legs = [(ci0 + lg.j, lg.order, lg.frac, float(lg.px), lg.kind, lg.j) for lg in legs]
    if abs(sum(lg.frac for lg in legs) - 1.0) > 1e-9:
        return None
    last = max(lg.j for lg in legs)
    if rec.bar_at(last) is None:
        return None
    path = np.asarray(rec.bars.c[rec.e:rec.e + last + 1], dtype=float)
    rs = tuple(rp.r_with_slip(rp_legs, fill, stop, s) for s in EXIT_SLIPS)
    t = rp.Trade(key=(rec.b.era, rec.b.ticker, rec.b.E), ticker=rec.b.ticker, era=rec.b.era, e_ci=ci0, fill_minute=int(rec.fill_minute or 0),
                 fill=fill, stop=stop, width=width, status=legs[-1].kind, mature=True, realized_r=rs[0], r_slip=rs, sessions_held=last, legs=rp_legs,
                 path_c=path, retrigger=rec.b.retrigger, year=rec.b.year, month=rec.b.E[:7])
    return H.to_unified(t, map_b)


def tail_kind_for(rec: IRec, J_tail: int, why: str, bh: int) -> str:
    """How a walk that reaches J_tail is labelled: `cut_at_tail` when J_tail is his sell window + 20; `mark_break` / `mark_hole` when the ticker's
    identity break or a missing session shortened the range; `cut_at_guard` when a fit stage's guard bound did (X1 — by the planned-span
    exclusion it never reaches J_tail on a kept trade); `cut_at_horizon` when the 120-session horizon did (the frozen window = the buy day
    + 1 .. + 121 bars; a sell window longer than it: GSIT / GTLB 2023 — C11); `cut_at_data_end` when the export's last bar did. Every one of
    them is counted in the abstention share (N7) and the cuts printed by name."""
    if rec.exit_hi_j is not None and J_tail == rec.exit_hi_j + TAIL_SESSIONS:
        return "cut_at_tail"
    if why == "guard":
        return "cut_at_guard"
    if why == "break":
        return "mark_break"
    if why == "hole":
        return "mark_hole"
    return "cut_at_horizon" if bh >= HORIZON + 1 else "cut_at_data_end"


def guard_bound_guards(rec: IRec, guards: dict) -> tuple:
    """(guards, j) — X1 (found 2026-10-25 by the N1 fix's card): the frozen speed trail (`ours`) and `break_horizon` slice the 121-session
    forward window straight off the bar arrays (`cb.forward_window`), outside `bar_at` and the per-pair belt. In a FIT stage (the record's
    guard carries forbidden pairs) the ticker's identity-break list gets one more entry, dated on the first forbidden session of that window,
    so `rp.cut_at_break` ends ours, his (`max_j = bh`) and chosen (`J_tail = min(..., bh)`) on the session before it — dates only; no price of
    the window is read before the cut. j = that session's offset (None: nothing forbidden in the window, or the check, whose forbid is empty)."""
    g = rec.guard
    if g is None or not g.forbid:
        return guards, None
    for j in range(1, HORIZON + 2):
        d = rec.session_date(j)
        if d is None:
            break
        if (bar_sym(d, rec.b.sym_a, rec.b.sym), d) in g.forbid:
            old = (guards or {}).get(rec.b.ticker)
            brk = np.asarray(old if old is not None else [], dtype=np.int64)
            out = dict(guards or {})
            out[rec.b.ticker] = np.unique(np.concatenate([brk, np.array([date.fromisoformat(d).toordinal()], dtype=np.int64)]))
            return out, j
    return guards, None


def exit_prepare(rec: IRec, M: dict, store: MinuteStore) -> dict:
    """The forward range, the bar sequence (warm-up + buy day + hold + tail), the armed bar and the thin flag for one trade. In a fit stage the
    forward range is bounded before the first forbidden session (X1, `guard_bound_guards`): `why` = "guard" when that bound is what cut it."""
    guards = M["guards"].get(rec.b.era, {}) if isinstance(M.get("guards"), dict) else {}
    guards_g, guard_j = guard_bound_guards(rec, guards)
    bh, why = rev.break_horizon(rec, guards_g)
    if guard_j is not None:
        bh0, why0 = rev.break_horizon(rec, guards)
        why = "guard" if bh < bh0 else why0
        guards = guards_g
    J_tail = min(rec.exit_hi_j + TAIL_SESSIONS, bh) if rec.exit_hi_j is not None else min(TAIL_SESSIONS, bh)
    seq = bar_sequence(rec, store, -WARMUP_SESSIONS, J_tail)
    armed = armed_index(seq, rec.fill_minute)
    thin = armed is None or ema_is_thin(armed)
    return dict(bh=bh, why=why, J_tail=J_tail, seq=seq, armed=armed, thin=thin, residual=seed_residual(armed) if armed is not None else float("nan"),
                abstain=("no_armed_bar" if armed is None else ("ema_thin" if thin else "")), guards=guards, guard_j=guard_j, tail_kind=tail_kind_for(rec, J_tail, why, bh))


def exit_window_sessions(rec: IRec) -> int:
    """The sell window's width in sessions on the record's OWN calendar (§11c; never the main calendar's indices — C12)."""
    return rec.exit_hi_j - rec.exit_lo_j + 1


def exit_hit(walk: dict, rec: IRec, prep: dict) -> tuple:
    """(scorable, hit, half_hit): the LAST leg's booked session inside [exit_lo_j, exit_hi_j], on windows <= 20 sessions whose walk was not cut
    before the window; the half leg's session likewise."""
    if rec.exit_hi_j is None or exit_window_sessions(rec) > EXIT_HIT_MAX_WINDOW or walk["last_j"] is None:
        return False, False, False
    if walk["cut"] == "hole" and walk["last_j"] < rec.exit_lo_j:
        return False, False, False
    if prep["J_tail"] < rec.exit_hi_j:
        return False, False, False
    lo, hi = rec.exit_lo_j, rec.exit_hi_j
    hit = lo <= walk["last_j"] <= hi
    half = walk["half_j"] is not None and lo <= walk["half_j"] <= hi
    return True, bool(hit), bool(half)


def accounts_intra(say, recs: list, variant: str, M: dict, cal_u: list, w0: int, store: MinuteStore, label: str = "", avg: str = "ema",
                   preps: "dict | None" = None, bootstrap: bool = False) -> dict:
    """The three accounts (§7c): ours = the speed trail under the chain's fill and stop; chosen = the variant's legs; his = the panel exit at
    the close of exit_hi, no stop — all through the frozen `simulate` at cap_30, on the SAME trades (an `ema_thin` / no-bar trade leaves all
    three, counted). Recovery = (ln chosen - ln ours) / (ln his - ln ours); VOID when his / ours < 1.25; the recovery without the
    `cut_at_tail` trades beside; a trade-resampled 90% interval when asked."""
    cal_dates = [date.fromisoformat(d) for d in cal_u]
    ours, chosen, his, c = [], [], [], Counter()
    rows, horizon_names, guard_names = [], [], []
    for r in recs:
        if r.exit_hi_j is None:
            c["no_exit"] += 1
            continue
        width = (r.fill - r.stop) / r.fill
        if not width > 0:
            c["stop_at_or_above_fill"] += 1
            continue
        prep = preps[r.b.eid] if preps and r.b.eid in preps else exit_prepare(r, M, store)
        if prep["abstain"]:
            c[prep["abstain"]] += 1
            continue
        smas = smas_for(r.bars)
        tail_kind = prep["tail_kind"]
        w = exit_walk_intra(r, variant, prep["seq"], prep["armed"], store, smas, prep["J_tail"], avg=avg, tail_kind=tail_kind)
        t_c = make_legs_trade(r, w["legs"], width, M["map_b"], len(cal_u))
        t_o = rev.speed_trail_trade(r, M, prep["guards"])
        t_h = rev.panel_trade(r, M["map_b"], len(cal_u), max_j=prep["bh"], cut_kind=tail_kind if tail_kind != "cut_at_tail" else "mark_hole")
        if t_o is None or t_c is None or t_h is None:
            c["unbuildable"] += 1
            continue
        c["trades"] += 1
        c["cut_at_tail"] += int(any(lg.kind == "cut_at_tail" for lg in w["legs"]))
        # N7 (DECIDED 2026-10-25): a walk a missing session or an identity break shortened counts with the cuts, whether the hole came
        # mid-walk (`cut` == "hole") or shortened the tail (`tail_kind_for` -> a `mark_hole` / `mark_break` tail leg): a cut is a cut (C11)
        c["cut_at_hole"] += int(w["cut"] == "hole" or any(lg.kind == "mark_hole" for lg in w["legs"]))
        c["cut_at_break"] += int(any(lg.kind == "mark_break" for lg in w["legs"]))
        for kind in ("cut_at_horizon", "cut_at_data_end", "cut_at_guard", "mark_hole", "mark_break"):
            if any(lg.kind == kind for lg in w["legs"]):
                if kind.startswith("cut_at_"):
                    c[kind] += 1
                horizon_names.append(f"{r.b.sym} {r.b.E} ({kind}; exit_hi offset {r.exit_hi_j}, J_tail {prep['J_tail']})")
        if prep.get("guard_j") is not None:                     # X1: ours / his / chosen bounded before the first forbidden session (a fit stage only)
            c["guard_bounded"] += 1
            guard_names.append(f"{r.b.sym} {r.b.E} (first forbidden session +{prep['guard_j']}, bh {prep['bh']}, J_tail {prep['J_tail']})")
        c["stop_preempt"] += int(w["stop_preempt"])
        ours.append(t_o); chosen.append(t_c); his.append(t_h)
        rows.append(dict(eid=r.b.eid, cut_tail=any(lg.kind in CUT_KINDS for lg in w["legs"]), last_j=w["last_j"], half_j=w["half_j"], legs=len(w["legs"])))
    sims = {k: rp.simulate(v, CAP30, cal_dates, w0) for k, v in (("ours", ours), ("chosen", chosen), ("his", his))}
    rec_, void = rev.recovery(sims["ours"]["final"], sims["chosen"]["final"], sims["his"]["final"])
    n = c["trades"]
    abst, abst_share = abstention_share(c)
    say(f"- {label}{variant} ({', '.join(f'{k} {v}' for k, v in sorted(c.items()))}): ours {sims['ours']['final']:.3f} | chosen {sims['chosen']['final']:.3f} | his {sims['his']['final']:.3f} "
        f"| his / ours {sims['his']['final'] / sims['ours']['final'] if sims['ours']['final'] > 0 else float('nan'):.2f} | recovery {rec_:+.3f}" + (f" | VOID ({void})" if void else "")
        + f" | abstentions (cut_at_tail + cut_at_horizon + cut_at_data_end + cut_at_guard + a hole (mark_hole) + an identity break (mark_break) + ema_thin + no-bar) {abst} = {pct(abst_share)} of the trades"
        + (" -> INCONCLUSIVE clause" if abst_share > EXIT_ABSTAIN_MAX else ""))
    if horizon_names:
        say(f"    cut at the 120-session horizon or the export's last bar, or marked at a hole / an identity break / the guard bound, before his sell window + 20 ('his' is that mark there): " + ", ".join(horizon_names))
    if guard_names:
        say(f"    X1, a fit stage only: the forward window (ours = the speed trail; his; chosen) bounded on the session before the first forbidden (symbol, session) pair, "
            f"by dates ({len(guard_names)}; a trail still open there is the frozen walk's unsettled mark at its last close): " + ", ".join(guard_names))
    for k, s_ in sims.items():
        say(f"    {k}: by year " + ", ".join(f"{y} {pct(x)}" for y, x in sorted(s_["yearly"].items())) + f" | max DD {pct(s_['max_dd'])} | entered {s_['counts']['entered']}, skipped no room {s_['counts']['skipped_no_room']}")
    out = dict(ours=sims["ours"]["final"], chosen=sims["chosen"]["final"], his=sims["his"]["final"], recovery=rec_, void=void, n=n, counts=dict(c), abstain_share=abst_share,
               rows=rows)
    keep = [i for i, rw in enumerate(rows) if not rw["cut_tail"]]
    if keep and len(keep) < len(rows):
        s2 = {k: rp.simulate([v[i] for i in keep], CAP30, cal_dates, w0) for k, v in (("ours", ours), ("chosen", chosen), ("his", his))}
        r2, v2 = rev.recovery(s2["ours"]["final"], s2["chosen"]["final"], s2["his"]["final"])
        say(f"    without the cut / marked trades ({len(keep)}): ours {s2['ours']['final']:.3f} | chosen {s2['chosen']['final']:.3f} | his {s2['his']['final']:.3f} | recovery {r2:+.3f}" + (f" | VOID ({v2})" if v2 else ""))
        out["recovery_no_tail"] = r2
    if bootstrap and n >= 2:
        lo_, hi_ = bootstrap_recovery(ours, chosen, his, cal_dates, w0)
        say(f"    trade-resampled 90% interval of the recovery ({BOOT_DRAWS} draws, seed {SEED}, key {BOOT_KEY}; information, not a bar): [{lo_:+.3f}, {hi_:+.3f}]")
        out["boot"] = (lo_, hi_)
    return out


def abstention_share(c: Counter) -> tuple:
    """§7c's clause: (count, share) of cut_at_tail + cut_at_horizon + cut_at_data_end + cut_at_guard + cut_at_hole (mark_hole, mid-walk or
    tail) + cut_at_break (mark_break) + ema_thin + no_armed_bar over the deciding trades (the account trades plus the trades that left before
    an account could be built). N7: a walk a hole or an identity break shortened is a cut too."""
    abst = (c["cut_at_tail"] + c["cut_at_horizon"] + c["cut_at_data_end"] + c["cut_at_guard"] + c["cut_at_hole"] + c["cut_at_break"]
            + c["ema_thin"] + c["no_armed_bar"])
    denom = c["trades"] + c["ema_thin"] + c["no_armed_bar"]
    return abst, (abst / denom if denom else float("nan"))


def exit_verdict(acc: dict) -> tuple:
    """§7c on the deciding line's accounts: VOID (his / ours < 1.25) before INCONCLUSIVE (abstentions > 10%) before PASS (recovery >= 0.25) /
    FAIL. -> (verdict, reason)."""
    if acc["void"]:
        return "VOID", acc["void"]
    if acc["abstain_share"] > EXIT_ABSTAIN_MAX:
        return "INCONCLUSIVE", f"abstentions {pct(acc['abstain_share'])} > {pct(EXIT_ABSTAIN_MAX)}"
    return ("PASS" if acc["recovery"] >= EXIT_RECOVERY_BAR else "FAIL"), f"recovery {acc['recovery']:+.3f} vs the bar {EXIT_RECOVERY_BAR}"


def apply_sign_veto(verdict: str, fires: bool, where: str) -> tuple:
    """A PASS vetoed by the untouched years' sign reads INCONCLUSIVE; any other verdict stands. -> (verdict, reason or None)."""
    if verdict == "PASS" and fires:
        return "INCONCLUSIVE", f"a PASS on {where} vetoed by the untouched years' sign"
    return verdict, None


def chain_after(verdict: str, chosen):
    """§4: the chain carries a stage's chosen object only on a PASS; otherwise the REGISTERED reading (None)."""
    return chosen if verdict == "PASS" else None


def deciding_line_for(verdicts: dict) -> str:
    """§7d: EXIT decides on the chain's fill and stop when ENTER or STOP passed, else on the registered ones."""
    return "chain" if (verdicts.get("enter") == "PASS" or verdicts.get("stop") == "PASS") else "registered"


def bootstrap_recovery(ours: list, chosen: list, his: list, cal_dates: list, w0: int, draws: int = BOOT_DRAWS) -> tuple:
    rng = rng_for(BOOT_KEY)
    n = len(ours)
    vals = []
    for _ in range(draws):
        idx = rng.integers(0, n, size=n)
        s = {k: rp.simulate([v[i] for i in idx], CAP30, cal_dates, w0) for k, v in (("ours", ours), ("chosen", chosen), ("his", his))}
        r_, v_ = rev.recovery(s["ours"]["final"], s["chosen"]["final"], s["his"]["final"])
        if np.isfinite(r_):
            vals.append(r_)
    if not vals:
        return float("nan"), float("nan")
    return float(np.percentile(vals, 5)), float(np.percentile(vals, 95))


def exit_veto(acc: dict) -> tuple:
    """§7d's sign veto on the untouched dated trades: fires only when ln(his / ours) > 0 there AND ln(chosen / ours) < 0; else abstains."""
    o, c, h = acc.get("ours", float("nan")), acc.get("chosen", float("nan")), acc.get("his", float("nan"))
    if not (o > 0 and c > 0 and h > 0):
        return False, "abstains (a non-positive account)"
    if math.log(h / o) <= 0:
        return False, f"abstains (his {h:.3f} <= ours {o:.3f} there: the recovery's sign means nothing)"
    fires = math.log(c / o) < 0
    return fires, f"his {h:.3f} > ours {o:.3f}; chosen {c:.3f} {'<' if fires else '>='} ours -> {'VETO' if fires else 'no veto'}"


def hit_rates_for(recs: list, M: dict, store: MinuteStore, preps: dict, variants=EXIT_VARIANTS, avg: str = "ema", second_close: bool = False) -> dict:
    """{variant: (hit_rate, half_hit_rate, n_scorable, per-trade dict)} on `recs` under the chain's fill and stop."""
    out = {}
    for v in variants:
        hits, halves, n, per = 0, 0, 0, {}
        for r in recs:
            if r.exit_hi_j is None:
                continue
            prep = preps.get(r.b.eid)
            if prep is None or prep["abstain"]:
                per[r.b.eid] = dict(scorable=False, last_j=None, half_j=None, abstain=prep["abstain"] if prep else "no_prep")
                continue
            w = exit_walk_intra(r, v, prep["seq"], prep["armed"], store, smas_for(r.bars), prep["J_tail"], avg=avg, second_close=second_close, tail_kind=prep["tail_kind"])
            sc, hit, half = exit_hit(w, r, prep)
            per[r.b.eid] = dict(scorable=sc, last_j=w["last_j"], half_j=w["half_j"], hit=hit, half_hit=half, cut=w["cut"], stop_preempt=w["stop_preempt"],
                                legs=";".join(f"{lg.kind}@{lg.j}" for lg in w["legs"]))
            if sc:
                n += 1; hits += int(hit); halves += int(half)
        out[v] = (hits / n if n else float("nan"), halves / n if n else float("nan"), n, per)
    return out


def choose_exit(rates: dict) -> str:
    """The variant with the highest last-leg hit rate; ties -> fewer legs (E1, E4, then E2, E3)."""
    best = max((rates[v][0] for v in EXIT_VARIANTS if np.isfinite(rates[v][0])), default=float("nan"))
    for v in EXIT_TIE_ORDER:
        if np.isfinite(rates[v][0]) and rates[v][0] == best:
            return v
    return "E1"


def trivial_and_list_hits(recs: list, preps: dict, lst: "list | None") -> dict:
    """The trivial exits (the close of session 3; the first red close from session 2) and the previous daily list on the same scorable trades."""
    out = Counter()
    n = 0
    for r in recs:
        if r.exit_hi_j is None or exit_window_sessions(r) > EXIT_HIT_MAX_WINDOW:
            continue
        prep = preps.get(r.b.eid)
        if prep is None or prep["abstain"] or prep["J_tail"] < r.exit_hi_j:
            continue
        X = rev.exit_features(r, r.exit_hi_j, smas_for(r.bars))
        if X is None:
            continue
        n += 1
        tv = rev.trivial_sell_days(X)
        lo, hi = r.exit_lo_j, r.exit_hi_j
        out["close_of_session_3"] += int(lo <= tv["close_of_session_3"] <= hi)
        out["first_red_close"] += int(lo <= tv["first_red_close"] <= hi)
        if lst is not None:
            out["daily_list"] += int(lo <= rev.list_sell_day(X, lst) <= hi)
    return dict(n=n, **{k: (v / n if n else float("nan")) for k, v in out.items()})


def load_prev_daily_list() -> "list | None":
    """The previous read's chosen daily exit list (`reverse/exit_fit_chosen.json`): the hit-rate benchmark printed beside."""
    p = FILES["rev_exit_fit_chosen"]
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        obj = json.load(fh)["object"]
    if obj.get("family") != "list":
        return None
    return [tuple(tuple(c) for c in r) for r in obj["list"]]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# WHY-lite (§8): his 60-minute words joined to the trades the panel dates — a cross-check, never a source
# ═════════════════════════════════════════════════════════════════════════════════════════════
def why_counts(texts: dict) -> tuple:
    """(files, files matching the 60-minute pattern, files mentioning the 20 EMA, files carrying the phrase set) on the PARSED words."""
    r60, rema, rph = re.compile(WHY_P_60), re.compile(WHY_P_EMA), re.compile(WHY_PHRASE)
    n60 = sum(1 for t in texts.values() if r60.search(t[0]))
    nema = sum(1 for t in texts.values() if rema.search(t[0]))
    nph = sum(1 for t in texts.values() if rph.search(t[0]))
    return len(texts), n60, nema, nph


def why_joins(texts: dict, C: dict) -> dict:
    """The join rule (the previous §9's): a phrase hit; a ticker mention within 30 s; the ticker's panel exit window covers the stream's session;
    ambiguous dropped — with the 60-minute / 20-EMA phrase set."""
    VS, MG = rev.load_caption_inputs()
    byname = defaultdict(list)
    for b in C["S"]["ni"]:
        if b.has_exit:
            byname[b.sym].append(b)
            if b.sym_a != b.sym:
                byname[b.sym_a].append(b)
    hits = rev.phrase_hits(texts, rx=WHY_PHRASE)
    return rev.caption_joins(hits, VS, MG, byname, C["cal"])


def why_sheet_rows(joins: list, texts: dict, year: str = "2020", seed: int = WHY_SEED, n: int = WHY_SAMPLE) -> list:
    """The GATE sample: `n` unambiguous joins of `year`'s streams (seed 1025) with the caption words around the phrase; `verdict` blank."""
    pool = [j for j in joins if not j["ambiguous"] and j["upload"].startswith(year)]
    rng = np.random.default_rng(seed)
    idx = sorted(rng.choice(len(pool), size=min(n, len(pool)), replace=False).tolist()) if pool else []
    rows = []
    for i in idx:
        j = pool[i]
        txt, offs, tim = texts[j["video"]]
        k = bisect.bisect_right(tim, j["t"]) - 1
        a, bnd = max(0, k - 40), min(len(offs) - 1, k + 40)
        snippet = txt[offs[a]:offs[bnd]]
        rows.append(dict(video=j["video"], t=round(float(j["t"]), 1), phrase=j["phrase"], upload=j["upload"], eids=";".join(str(x) for x in j["eids"]),
                         tickers=";".join(j["tickers"]), snippet=snippet, verdict=""))
    return rows


def why_precision(sheet: pd.DataFrame) -> tuple:
    v = sheet["verdict"].astype(str).str.strip().str.lower()
    yes, no = int((v == "yes").sum()), int((v == "no").sum())
    return (yes / (yes + no) if (yes + no) else float("nan")), yes, no


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the known-answer gates on REAL data (§12): each STOPS the stage before any new number and writes the failing rows
# ═════════════════════════════════════════════════════════════════════════════════════════════
def write_rows(name: str, rows: list) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, name)
    pd.DataFrame(rows).to_csv(p, sep="\t", index=False)
    return p


def ohlc_pair_rows(recs: list, store: MinuteStore, sessions_of) -> list:
    """Per (ticker, session) the stage reads: the minute-built session open / high / low / close against the daily export, as relative
    deviations (a listed early-close day is trimmed first; a session without minutes or without a daily bar is skipped)."""
    rows = []
    for r in recs:
        for j in sessions_of(r):
            k = r.bar_at(j) if j >= 0 else (r.e + j if (r.e + j >= 0 and int(r.cidx[r.e + j]) == r.e_ci + j) else None)
            if k is None:
                continue
            mb = r.mb if j == 0 else r.minutes(store, j)
            if mb is None or len(mb) == 0:
                continue
            d = r.session_date(j)
            mb = R.h60_trim(mb, d in EARLY_CLOSE)
            if len(mb) == 0:
                continue
            mo, mh, ml, mc = fnum(mb.o[0]), fnum(mb.h.max()), fnum(mb.l.min()), fnum(mb.c[-1])
            do, dh, dl, dc = (fnum(r.bars.o[k]), fnum(r.bars.h[k]), fnum(r.bars.l[k]), fnum(r.bars.c[k]))
            rows.append(dict(eid=r.b.eid, sym=r.b.sym, session=d, j=j, dev_o=abs(mo / do - 1), dev_h=abs(mh / dh - 1), dev_l=abs(ml / dl - 1), dev_c=abs(mc / dc - 1),
                             daily_o=do, daily_h=dh, daily_l=dl, daily_c=dc, minute_o=mo, minute_h=mh, minute_l=ml, minute_c=mc))
    return rows


def gate_ohlc_verdict(rows: list) -> dict:
    """(i) in two arms (C1): (a) high AND low within GATE_HL_TOL on >= GATE_HL_SHARE of pairs — set by trades on both sides, exact on a right day,
    gross on a wrong day / symbol / calendar / clock; (b) open AND close within GATE_OC_TOL on >= GATE_OC_SHARE — the auction-print basis
    leaves a band on the right day, a clock shift reads a different minute's price on most pairs. -> the counts, shares, failing rows, ok."""
    n = len(rows)
    hl_fail = [x for x in rows if max(x["dev_h"], x["dev_l"]) > GATE_HL_TOL]
    oc_fail = [x for x in rows if max(x["dev_o"], x["dev_c"]) > GATE_OC_TOL]
    hl_share = (n - len(hl_fail)) / n if n else float("nan")
    oc_share = (n - len(oc_fail)) / n if n else float("nan")
    ok = (not n) or (hl_share >= GATE_HL_SHARE and oc_share >= GATE_OC_SHARE)
    return dict(n=n, hl_ok=n - len(hl_fail), hl_share=hl_share, oc_ok=n - len(oc_fail), oc_share=oc_share, hl_fail=hl_fail, oc_fail=oc_fail, ok=ok)


def gate_ohlc(say, recs: list, store: MinuteStore, sessions_of, label: str) -> dict:
    """(i) per (ticker, session) the stage reads: the minute-built session high and low agree with the daily export within 0.5% on >= 98% of
    pairs AND the open and close within 0.5% on >= 90% (two arms, C1); every failing pair written, the failures listed by ticker."""
    rows = ohlc_pair_rows(recs, store, sessions_of)
    v = gate_ohlc_verdict(rows)
    by_hl = Counter(f["sym"] for f in v["hl_fail"])
    by_oc = Counter(f["sym"] for f in v["oc_fail"])
    say(f"- gate (i) {label}: minute-built session bars vs the daily export on {v['n']} (ticker, session) pairs — high AND low within {pct(GATE_HL_TOL)}: {v['hl_ok']} = {pct(v['hl_share'])} "
        f"(bar {pct(GATE_HL_SHARE)}; failures by ticker: " + (", ".join(f"{k} {c}" for k, c in by_hl.most_common(8)) or "none") + f"); open AND close within {pct(GATE_OC_TOL)}: {v['oc_ok']} = {pct(v['oc_share'])} "
        f"(bar {pct(GATE_OC_SHARE)}; the auction-print band; failures by ticker: " + (", ".join(f"{k} {c}" for k, c in by_oc.most_common(8)) or "none") + ")")
    for f in (v["hl_fail"] + [x for x in v["oc_fail"] if x not in v["hl_fail"]])[:12]:
        say(f"    {f['sym']} {f['session']}: dev o {pct(f['dev_o'], 2)} h {pct(f['dev_h'], 2)} l {pct(f['dev_l'], 2)} c {pct(f['dev_c'], 2)} (daily c {f['daily_c']:.3f} vs minute {f['minute_c']:.3f})")
    if v["n"] and (v["hl_fail"] or v["oc_fail"]):
        p = write_rows(f"gate_i_pairs_{label}.tsv", v["hl_fail"] + [x for x in v["oc_fail"] if x not in v["hl_fail"]])
        say(f"    every pair outside a band written -> {p}")
    if not v["ok"]:
        raise GuardStop(f"gate (i): high/low within {pct(GATE_HL_TOL)} on {pct(v['hl_share'])} of {v['n']} pairs (bar {pct(GATE_HL_SHARE)}); open/close within {pct(GATE_OC_TOL)} on "
                        f"{pct(v['oc_share'])} (bar {pct(GATE_OC_SHARE)})")
    return v


def _isnum(x) -> bool:
    return x is not None and not (isinstance(x, float) and not np.isfinite(x))


def gate_level_order(say, rows: list, label: str) -> None:
    """(ii) per window, on the raw intraday levels: L7 <= L1 <= L8 <= L6 (where each exists), the count of L8 < L6 printed; the 60-minute bar
    BUILDER's first bar (`H60_0_high`, the high of `h60_bars(...)[0]`) must equal L8_raw on every window, and that builder value equal to L6
    on more than 90% of the windows with both is the [0,59] first-bar bug and stops the stage (C8: the builder is what L9, S10 and EXIT use)."""
    bad, both, lt, builder_bad = [], 0, 0, []
    for rw in rows:
        L7, L1, L8, L6, B0 = rw.get("L7_raw"), rw.get("L1_raw"), rw.get("L8_raw"), rw.get("L6_raw"), rw.get("H60_0_high")
        chain = [x for x in (L7, L1, L8, L6) if _isnum(x)]
        if any(chain[i] > chain[i + 1] + 1e-9 for i in range(len(chain) - 1)):
            bad.append(rw)
        if _isnum(L8) and _isnum(B0) and abs(float(L8) - float(B0)) > 1e-9:
            builder_bad.append(rw)
        if _isnum(B0) and _isnum(L6):
            both += 1
            lt += int(float(B0) < float(L6) - 1e-9)
    say(f"- gate (ii) {label}: raw L7 <= L1 <= L8 <= L6 on {len(rows) - len(bad)} of {len(rows)} windows; the builder's first bar equals L8_raw on "
        f"{len(rows) - len(builder_bad)} of {len(rows)}; builder first-bar high < L6 on {lt} of {both} windows with both")
    if bad:
        p = write_rows(f"gate_ii_failures_{label}.tsv", bad)
        raise GuardStop(f"gate (ii): the level order fails on {len(bad)} windows; rows -> {p}")
    if builder_bad:
        p = write_rows(f"gate_ii_builder_failures_{label}.tsv", builder_bad)
        raise GuardStop(f"gate (ii): the 60-minute builder's first bar differs from the raw 30-minute high on {len(builder_bad)} windows; rows -> {p}")
    if both and (both - lt) / both > GATE_L8_EQ_L6_SHARE:
        raise GuardStop(f"gate (ii): the builder's first-bar high equals L6 on {both - lt} of {both} windows (> {pct(GATE_L8_EQ_L6_SHARE)}): the [0,59] first-bar bug")


def gate_c_implies_h(say, recs: list, store: MinuteStore, label: str, levels=STOP_LEVELS + STOP_CONTROLS) -> dict:
    """(iii) a daily close below a level implies the last 60-minute bar closes below it — up to the auction band (C2): the daily close is the
    closing auction print, the last bar's close the 15:59 minute's last trade. Over the sessions the stage reads (the buy day .. exit_hi, the
    still-held last frame), per (session, level) with a last 60-minute bar: a C event BEYOND the band (daily close < level x (1 - 0.5%)) whose
    last bar closes at or above the level is a failure; the gate holds when >= 98% of the beyond-band C days are H days (failures listed).
    C days inside the band that are not H days are counted beside, never failing."""
    bad, n_beyond, n_band, n_band_not_h = [], 0, 0, 0
    for r in recs:
        J = r.exit_hi_j if r.exit_hi_j is not None else r.last_j
        if J is None:
            continue
        smas = smas_for(r.bars)
        for j in range(0, J + 1):
            k = r.bar_at(j)
            if k is None:
                break
            bars = (h60_bars(r.mb, r.b.E) if r.mb is not None else None) if j == 0 else r.h60(store, j)
            if bars is None:
                continue
            last = next((x for x in reversed(bars) if x is not None), None)
            if last is None or last.k != len(bars) - 1:
                continue
            dc = fnum(r.bars.c[k])
            for Lname in levels:
                lvl = r.stop_levels.get(Lname)
                if lvl is None:
                    continue
                L = rev.level_at(r, lvl, j, smas)
                if not np.isfinite(L) or not dc < L:
                    continue
                if dc < L * (1.0 - AUCTION_BAND):
                    n_beyond += 1
                    if not last.c < L:
                        bad.append(dict(eid=r.b.eid, sym=r.b.sym, session=r.session_date(j), j=j, level=Lname, L=L, daily_close=dc, last_bar_close=last.c))
                else:
                    n_band += 1
                    n_band_not_h += int(not last.c < L)
    share = (n_beyond - len(bad)) / n_beyond if n_beyond else float("nan")
    say(f"- gate (iii) {label}: C event days beyond the {pct(AUCTION_BAND)} auction band with a last 60-minute bar {n_beyond}; H event days among them {n_beyond - len(bad)} = {pct(share)} "
        f"(bar {pct(GATE_III_SHARE)}); C days inside the band {n_band}, of which not H {n_band_not_h} (counted, never failing)")
    if bad:
        p = write_rows(f"gate_iii_failures_{label}.tsv", bad)
        say(f"    the {len(bad)} beyond-band C day(s) that are not H days -> {p}")
    if n_beyond and share < GATE_III_SHARE:
        raise GuardStop(f"gate (iii): only {pct(share)} of {n_beyond} beyond-band C event days are H event days (bar {pct(GATE_III_SHARE)})")
    return dict(n_beyond=n_beyond, bad=len(bad), n_band=n_band, n_band_not_h=n_band_not_h, share=share)


def gate_iv_enter(say, recs: list) -> None:
    """(iv) ENTER: the L1-L6 crossing minute, feasibility and verdict on the 2020 fit windows equal `reverse/enter_fit_trades.tsv` row for row
    (the frozen `enter_levels` + `score_level`; a difference is a bug)."""
    tsv = pd.read_csv(FILES["rev_enter_fit_trades"], sep="\t", dtype=str, keep_default_na=False).set_index("eid")
    bad, n = [], 0
    for r in recs:
        key = str(r.b.eid)
        if key not in tsv.index or r.mb is None or tsv.loc[key, "scorable"] != "True":
            continue
        flat_m, first_m = hhmm_to_min(r.b.flat_clock), hhmm_to_min(r.b.first_clock)
        lv = rev.enter_levels(r)
        for L in OLD_LEVELS:
            n += 1
            if first_m < rev.LEVEL_KNOWN_MIN.get(L, 0):
                s = dict(cross=None, feasible=False, verdict="no_level_yet")
            else:
                s = rev.score_level(r.mb, lv[L], flat_m, first_m, r.adr20)
            tc = tsv.loc[key, f"{L}_cross"]
            tc = None if tc in ("", "nan") else int(float(tc))
            tf = tsv.loc[key, f"{L}_feasible"] == "True"
            tv = tsv.loc[key, f"{L}_verdict"]
            if (s["cross"] != tc) or (bool(s["feasible"]) != tf) or (s["verdict"] != tv):
                bad.append(dict(eid=r.b.eid, sym=r.b.sym, level=L, mine_cross=s["cross"], tsv_cross=tc, mine_feasible=s["feasible"], tsv_feasible=tf, mine_verdict=s["verdict"], tsv_verdict=tv))
    say(f"- gate (iv) ENTER: the L1-L6 re-read equals the previous fit's rows on {n - len(bad)} of {n} (window, level) cells")
    if bad:
        p = write_rows("gate_iv_enter_failures.tsv", bad)
        raise GuardStop(f"gate (iv) ENTER: {len(bad)} cells differ from reverse/enter_fit_trades.tsv; rows -> {p}")


def old_exit_minutes(r: IRec, old_store: MinuteStore):
    """The exit window's first-session minutes AS THE PREVIOUS FIT READ THEM (`exit_minutes_for`: the trees A, B, EP, EP2, REV in that fixed
    order, the bar symbol by the session's date, never the new tree) — gate (iv)'s re-read and the old-rule re-print (C4). None when exit_lo
    is the buy day or no old tree holds the pair."""
    b = r.b
    if not b.has_exit or b.exit_lo == b.E:
        return None
    if r.guard is not None and r.guard.horizon(b) is not None:
        return None
    mb = old_store.get(b.exit_lo, bar_sym(b.exit_lo, b.sym_a, b.sym))
    return mb if (mb is not None and len(mb)) else None


def gate_iv_stop(say, recs: list, sight, store: MinuteStore, old_store: "MinuteStore | None" = None) -> None:
    """(iv) STOP: S1 / S3 under T and C equal `reverse/stop_fit_trades.tsv` row for row, taking each row's `fill_src` and `fill_minute` FROM
    THE TSV, the exit window's first-session minutes from the OLD trees only (`old_store`, as the previous fit's `exit_minutes_for` did — C4)
    and applying the OLD certainty rule (the frozen `held_through`) — a difference is a bug."""
    import dataclasses
    old_store = old_store if old_store is not None else store.restricted(OLD_TREES)
    tsv = pd.read_csv(FILES["rev_stop_fit_trades"], sep="\t", dtype=str, keep_default_na=False).set_index("eid")
    bad, n = [], 0
    for r in recs:
        key = str(r.b.eid)
        if key not in tsv.index:
            continue
        row = tsv.loc[key]
        r2 = dataclasses.replace(r)
        r2.fill = float(row["fill"])
        r2.fill_src = row["fill_src"]
        r2.fill_minute = None if row["fill_minute"] in ("", "nan") else int(float(row["fill_minute"]))
        r2.stop_levels = rev.stop_levels(r2, r2.fill_minute if r2.fill_src.startswith(("level", "orh5")) else None)
        smas = smas_for(r2.bars)
        for Lname in ("S1", "S3"):
            n += 1
            mine_L0 = rev.level_at(r2, r2.stop_levels[Lname], 0, smas)
            if abs(mine_L0 - float(row[f"{Lname}_level0"])) > 1e-6 * max(1.0, abs(mine_L0)):
                bad.append(dict(eid=r.b.eid, sym=r.b.sym, cell=f"{Lname}_level0", mine=mine_L0, tsv=row[f"{Lname}_level0"]))
            exit_mb = old_exit_minutes(r, old_store)
            for V in ("T", "C"):
                n += 1
                h = rev.held_through(r2, Lname, V, smas, sight, exit_mb=exit_mb)
                for fld in ("any", "certain", "unresolved"):
                    if bool(h[fld]) != (row[f"{Lname}_{V}_{fld}"] == "True"):
                        bad.append(dict(eid=r.b.eid, sym=r.b.sym, cell=f"{Lname}_{V}_{fld}", mine=h[fld], tsv=row[f"{Lname}_{V}_{fld}"]))
                tj = row[f"{Lname}_{V}_first_j"]
                tj = None if tj in ("", "nan") else int(float(tj))
                if h["first_j"] != tj:
                    bad.append(dict(eid=r.b.eid, sym=r.b.sym, cell=f"{Lname}_{V}_first_j", mine=h["first_j"], tsv=tj))
    say(f"- gate (iv) STOP: S1 / S3 under T and C with the TSV's own fills, the OLD trees' exit minutes and the OLD certainty rule equal the previous fit's rows on {n - len(bad)} of {n} cells "
        f"(old-tree exit minutes read for {sum(1 for r in recs if old_exit_minutes(r, old_store) is not None)} of {len(recs)} records)")
    if bad:
        p = write_rows("gate_iv_stop_failures.tsv", bad)
        raise GuardStop(f"gate (iv) STOP: {len(bad)} cells differ from reverse/stop_fit_trades.tsv; rows -> {p}")


def old_rule_table(recs: list, sight, store: MinuteStore, old_store: "MinuteStore | None" = None) -> dict:
    """The four old cells (S1-T, S1-C, S3-T, S3-C) under the OLD certainty rule (the frozen `held_through`) on this chain's fills, the exit
    window's first-session minutes from the OLD trees only (C4) — for the re-print beside the new rule (gate iv's second half)."""
    old_store = old_store if old_store is not None else store.restricted(OLD_TREES)
    out = {}
    for Lname in ("S1", "S3"):
        for V in ("T", "C"):
            n_any = n_cert = 0
            for r in recs:
                h = rev.held_through(r, Lname, V, smas_for(r.bars), sight, exit_mb=old_exit_minutes(r, old_store))
                n_any += int(h["any"]); n_cert += int(h["certain"])
            out[(Lname, V)] = dict(any=n_any, certain=n_cert, H_cond=(n_cert / n_any) if n_any else float("nan"))
    return out


def gate_vii_random_control(say, scored_all: dict, prev_und_eids: set) -> None:
    """(vii) at --check (C6): the random-price control is the previous read's IDENTICAL draws, so its mean feasible / hit-or-ballpark shares on
    the previous 41 undated 2021-22 windows (the `ent_chk_und` records with minutes, DWAC in) must reproduce `01_rev_check.txt` l.33 —
    31.7% / 85.9% at one decimal; else the draw population, its order or the scorer has changed and the stage stops."""
    prev = {k: v for k, v in scored_all.items() if k in prev_und_eids}
    s = enter_summary(prev)["control"] if prev else dict(feasible_share=float("nan"), hit_share=float("nan"))
    f, h = s["feasible_share"], s["hit_share"]
    ok = len(prev) == 41 and np.isfinite(f) and np.isfinite(h) and pct(f) == pct(RANDOM_CONTROL_KNOWN[0]) and pct(h) == pct(RANDOM_CONTROL_KNOWN[1])
    say(f"- gate (vii) the random-price control's known answer on the previous {len(prev)} undated 2021-22 windows: feasible {pct(f)}, hit-or-ballpark {pct(h)} "
        f"(known {pct(RANDOM_CONTROL_KNOWN[0])} / {pct(RANDOM_CONTROL_KNOWN[1])} on 41) -> {'reproduced' if ok else 'NOT reproduced'}")
    if not ok:
        raise GuardStop(f"gate (vii): the random-price control on the previous undated windows reads {pct(f)} / {pct(h)} on {len(prev)} records, not the known "
                        f"{pct(RANDOM_CONTROL_KNOWN[0])} / {pct(RANDOM_CONTROL_KNOWN[1])} on 41: the draws are not the previous read's")


def gate_v_accounts(say, recs: list, M: dict, cal_u: list, store: MinuteStore) -> None:
    """(v) at --check: under the registered fill and stop, the frozen module's record (`rev.make_rec` + `registered_fill`) and this module's
    (`IRec`) give the same 'ours' and 'his' trades per era-A dated 2021-22 trade (realised R, sessions held, legs) — a module-against-module
    check that needs no old offsets; the era-B trades are printed beside under the fixed offsets."""
    import dataclasses
    bad, n, beside = [], 0, []
    mcache, bcache = {}, {}
    for r in recs:
        if r.era != "A":
            beside.append(r)
            continue
        fr = rev.make_rec(r.b, M, "A", M["done"], M["files"], mcache, bcache, False, guard=None)
        if fr is None:
            continue
        mine = dataclasses.replace(r)
        fr.mb, fr.minutes_state = mine.mb, mine.minutes_state          # the same minutes on both sides: the gate compares the record builders, not the trees
        for x in (fr, mine):
            x.fill, x.fill_minute, x.fill_src, x.day0 = rev.registered_fill(x)
            x.stop_levels = rev.stop_levels(x, x.fill_minute if x.fill_src.startswith("orh5") else None)
            x.stop = x.stop_levels["S1"]
            if not x.stop < x.fill:
                x.stop = x.fill * (1.0 - x.adr20)
            x.stop_lvl = x.stop
            x.day0 = rev.day0_for(x, x.fill_minute, x.stop)
        guards = M["guards"].get("A", {})
        bh_f, _w = rev.break_horizon(fr, guards)
        bh_m, _w2 = rev.break_horizon(mine, guards)
        to_f, to_m = rev.speed_trail_trade(fr, M, guards), rev.speed_trail_trade(mine, M, guards)
        th_f, th_m = rev.panel_trade(fr, M["map_b"], len(cal_u), max_j=bh_f), rev.panel_trade(mine, M["map_b"], len(cal_u), max_j=bh_m)
        n += 1
        for name, a, b2 in (("ours", to_f, to_m), ("his", th_f, th_m)):
            if (a is None) != (b2 is None):
                bad.append(dict(eid=r.b.eid, sym=r.b.sym, account=name, frozen="None" if a is None else "trade", mine="None" if b2 is None else "trade"))
                continue
            if a is None:
                continue
            if abs(a.realized_r - b2.realized_r) > 1e-9 or a.sessions_held != b2.sessions_held or len(a.legs) != len(b2.legs) or abs(a.fill - b2.fill) > 1e-9 or abs(a.stop - b2.stop) > 1e-9:
                bad.append(dict(eid=r.b.eid, sym=r.b.sym, account=name, frozen=f"R {a.realized_r:.4f} held {a.sessions_held} legs {len(a.legs)}", mine=f"R {b2.realized_r:.4f} held {b2.sessions_held} legs {len(b2.legs)}"))
    say(f"- gate (v): the frozen record builder and this module's agree on 'ours' and 'his' per trade on {n - len({x['eid'] for x in bad})} of {n} era-A dated 2021-22 trades "
        f"(the old aggregate {GATE_V_RATIO_OLD} is named, not a target); era-B trades beside under the fixed offsets: {len(beside)}")
    for r in beside:
        say(f"    era B {r.b.sym} {r.b.E}: own-calendar offsets exit_lo {r.exit_lo_j} exit_hi {r.exit_hi_j}")
    if bad:
        p = write_rows("gate_v_failures.tsv", bad)
        raise GuardStop(f"gate (v): {len(bad)} account rows differ between the frozen and this record builder; rows -> {p}")


def gate_vi_fsly(say, recs: list, store: MinuteStore) -> None:
    """(vi) his own words as a known answer: FSLY eid 693 (undated 2020-06-29, exit window 07-13..07-14) shows a 60-minute close below the
    20-EMA on 2020-07-10 and a touch of the prior day's low on 2020-07-13 — else the bar builder or the reading is wrong. Decides nothing."""
    g = FSLY_GATE
    r = next((x for x in recs if x.b.eid == g["eid"]), None)
    if r is None:
        raise GuardStop(f"gate (vi): eid {g['eid']} ({g['sym']} {g['E']}) is not among this stage's records")
    if r.b.sym != g["sym"] or r.b.E != g["E"] or r.b.exit_lo != g["exit_lo"] or r.b.exit_hi != g["exit_hi"]:
        raise GuardStop(f"gate (vi): eid {g['eid']} is {r.b.sym} {r.b.E} {r.b.exit_lo}..{r.b.exit_hi}, not the FSLY trade of his captions")
    seq = bar_sequence(r, store, -WARMUP_SESSIONS, r.exit_hi_j)
    j_below, j_touch = r.off(g["h60_below_on"]), r.off(g["prior_low_touch_on"])
    below = [x for i, (j, x) in enumerate(seq.items) if j == j_below and np.isfinite(seq.ema[i]) and x.c < seq.ema[i]]
    k_t, k_p = r.bar_at(j_touch), r.bar_at(j_touch - 1)
    touch = k_t is not None and k_p is not None and fnum(r.bars.l[k_t]) <= fnum(r.bars.l[k_p])
    say(f"- gate (vi) FSLY 693: 60-minute closes below the 20-EMA on {g['h60_below_on']}: {len(below)} (first at {min_to_hhmm(below[0].close_minute) if below else '-'}); "
        f"a touch of the prior day's low on {g['prior_low_touch_on']}: {touch}; warm-up bars {seq.warmup_bars}, sessions without minutes {seq.missing_sessions}")
    if not below or not touch:
        raise GuardStop("gate (vi): his FSLY words are not reproduced by the bar builder / the reading (a 60-minute close below the 20-EMA on 2020-07-10 and a "
                        "touch of the prior day's low on 2020-07-13)")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# shared stage machinery: the core load, the markets + store, preloads, G8, the chosen-object files
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_core(say) -> dict:
    """The frozen `load_core` (the buys, the clocks, the calendar, the types, the sets) plus this read's sets, the misread-clock frames and
    ENTER's windows."""
    C = rev.load_core(say)
    C["I"] = intra_sets(C["S"])
    C["mis"] = rev.clock_misreads(C["sn"])
    C["E"] = enter_sets(C["I"], C["S"], C["mis"])
    return C


def last_seen_map(sight) -> dict:
    out = defaultdict(set)
    for (d, s), frames in sight.by_date_sym.items():
        if any(x[1] in ("in", "closed") for x in frames):
            out[s].add(d)
    return {s: sorted(v) for s, v in out.items()}


def load_for_stage(say, C: dict, keep_A: "set | None", keep_B: "set | None") -> dict:
    M = rev.load_markets(say, keep_A, keep_B)
    if M["cal_u"] != C["cal"]:
        raise GuardStop("the unified export calendar differs from the pickle calendar")
    done, files = load_done_all()
    M["done"], M["files"] = done, files
    M["store"] = MinuteStore(done, files)
    M["sight"] = rev.Sightings.build(C["sn"])
    M["last_seen"] = last_seen_map(M["sight"])
    say(f"- minute trees: " + ", ".join(f"{k} {len(v):,} log rows" for k, v in done.items()) + f"; era B export calendar {M['DB'].cal[0]}..{M['DB'].cal[-1]} "
        f"({len(M['DB'].cal):,} sessions) — every era-B record's offsets are bisected on it (one calendar per record)")
    return M


def names_of(buys: list) -> tuple:
    """(era-A names, era-B names) to load from the exports for these buys."""
    return {b.sym_a for b in buys} | {"QQQ", "SPY"}, {b.sym for b in buys if b.E > A_LAST} | {"QQQ", "SPY"}


def preload_buy_days(store: MinuteStore, buys: list) -> Counter:
    return store.preload([(b.E, bar_sym(b.E, b.sym_a, b.sym), b) for b in buys])


def preload_sessions(store: MinuteStore, recs: list, j_from: int, j_to_fn) -> Counter:
    """The minute pairs of sessions j_from..j_to(rec) on each record's own calendar; forward sessions only for trades the guard allows."""
    pairs = []
    for r in recs:
        jt = j_to_fn(r)
        if jt is None:
            continue
        fwd_ok = r.guard is None or r.guard.horizon(r.b) is None
        for j in range(j_from, jt + 1):
            if j >= 1 and not fwd_ok:
                break
            d = r.session_date(j)
            if d is None:
                continue
            pairs.append((d, bar_sym(d, r.b.sym_a, r.b.sym), r.b))
    return store.preload(pairs)


def g8_run(say, recs: list, label: str) -> None:
    """§11 G8 before any number: this stage's own trade list per era through trade_impact.py; era A must read 0 / 0 (asserted)."""
    os.makedirs(OUT_DIR, exist_ok=True)
    say(f"\n## G8 — {label}: this read's own trade list through trade_impact.py (before any number)")
    for era in ("A", "B"):
        rows = [("intra", r.b.ticker, r.b.E, r.exit_hi_j if r.exit_hi_j is not None else 0, 0.0) for r in recs if r.era == era]
        if not rows:
            say(f"- era {era}: no trade; G8 not run")
            continue
        path, txt = os.path.join(OUT_DIR, f"{label}_g8_{era}.tsv"), os.path.join(OUT_DIR, f"{label}_g8_{era}_impact.txt")
        rp.write_g8_file(path, rows)
        cmd = [sys.executable, rp.TRADE_IMPACT, "--flags", rp.FILES[f"flags_{era}"], "--export", rp.FILES[f"export_{era}"], "--trades", path,
               "--label", era, "--kind", "r1", "--cell", "intra", "--cutoff", CUT_B]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        text = res.stdout + ("\n[stderr]\n" + res.stderr if res.stderr.strip() else "")
        with open(txt, "w") as fh:
            fh.write(" ".join(cmd) + "\n\n" + text)
        if res.returncode != 0:
            raise GuardStop(f"trade_impact.py exited {res.returncode} for era {era}")
        after, past = rp.parse_g8(text)
        say(f"- era {era}: entered after the cutoff {after}, holds past the last bar {past} ({len(rows)} trades)")
        if era == "A" and (after or past):
            raise GuardStop(f"G8 era A reads {after} / {past}, not 0 / 0")


def chosen_path(stage: str) -> str:
    return os.path.join(OUT_DIR, f"{stage}_fit_chosen.json")


def module_sha() -> str:
    return sha(os.path.abspath(__file__))


def freeze_record_now(doc: str = None) -> dict:
    """What a fit stage runs under (C5): the freeze body pinned under the marker and this module's sha. Each fit writes it into its chosen file
    and printout; --check refuses unless all three equal the pin under the marker and the module it is running."""
    return {"doc_body_freeze": pin_under_marker("doc_body_freeze", doc), "intra_module": module_sha()}


def write_chosen(stage: str, obj: dict, text: str) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(chosen_path(stage), "w") as fh:
        json.dump({"stage": stage, "text": text, "object": obj, "freeze": freeze_record_now()}, fh, indent=1, default=str)
    ledger_append(f"{stage}-fit", chosen_path(stage))


def freeze_records_agree(doc: str = None) -> list:
    """The reasons --check must refuse (C5): a fit's recorded freeze body or module sha differs from the pin under the marker / this module, or a
    fit recorded none. Empty when all three fits ran under the current freeze body and this module."""
    now = freeze_record_now(doc)
    bad = []
    for s in STAGES:
        fz = read_chosen(s).get("freeze")
        if not fz:
            bad.append(f"the {s.upper()} fit recorded no freeze body / module sha")
            continue
        for k in ("doc_body_freeze", "intra_module"):
            if fz.get(k) != now[k]:
                bad.append(f"the {s.upper()} fit ran under {k} {str(fz.get(k))[:12]}..., the check sees {str(now[k])[:12]}...")
    return bad


def read_chosen(stage: str) -> dict:
    p = chosen_path(stage)
    if not os.path.exists(p):
        raise GuardStop(f"the {stage.upper()} fit has not run ({p} missing): the chain runs in order")
    with open(p) as fh:
        return json.load(fh)


def stage_header(say, stage: str, title: str) -> None:
    say(f"# #705 INTRADAY 01 — {stage.upper()} FIT: {title}")
    say(f"# registration: {os.path.relpath(DOC, REPO)}; written once; the ledger records this printout")
    fz = freeze_record_now()
    say(f"# runs under the freeze body {fz['doc_body_freeze']} and the module {fz['intra_module']} (recorded in the chosen file; --check refuses on a difference)")


def registered_copy(rec: IRec) -> IRec:
    """A copy of the record under the REGISTERED fill and stop (ORH5 where it filled / the open; S1-T dated / one ADR20 undated)."""
    import dataclasses
    r2 = dataclasses.replace(rec)
    r2.fill, r2.fill_minute, r2.fill_src, r2.day0 = registered_fill(r2)
    r2.fill_fallback = False
    r2.stop_levels = stop_levels_intra(r2)
    r2.stop = r2.stop_levels["S1"] if rec.b.dated else r2.fill * (1.0 - r2.adr20)
    r2.stop_src = "S1-T" if rec.b.dated else "ADR20-T"
    if not (np.isfinite(r2.stop) and r2.stop < r2.fill):
        r2.stop, r2.stop_src = r2.fill * (1.0 - r2.adr20), r2.stop_src + "->ADR20"
    r2.stop_lvl, r2.stop_variant = r2.stop, "T"
    r2.day0 = rev.day0_for(r2, r2.fill_minute, r2.stop)
    return r2


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the population claims of THIS doc (§2, §2a-d, §5d, §11): the set-only part (every stage re-asserts it) and the dry run's full read
# ═════════════════════════════════════════════════════════════════════════════════════════════
def set_row(bs: list) -> str:
    nf = [b for b in bs if not b.flicker]
    ins = [b for b in bs if b.in_bracket]
    ins_nf = [b for b in ins if not b.flicker]
    return f"{len(bs)} / {len(nf)} / {f'{len(ins)} ({len(ins_nf)})' if ins else '0'} / {sum(1 for b in bs if b.has_exit)} / {sum(1 for b in bs if b.E >= B_FIRST)}"


def population_claims(say, C: dict) -> Claims:
    """The set-composition claims (no export, no bar): the previous 63 through the frozen `population_claims`, then §2's table, §2a-d, the §2c
    drops by name, the era-B counts, the FSLY identity."""
    S, I, E, sn, mis = C["S"], C["I"], C["E"], C["sn"], C["mis"]
    claim = Claims(say)
    EX = {lab: (anchor, v) for anchor, lab, v in EXPECT}

    def ck(lab, mine):
        return claim(EX[lab][0], lab, EX[lab][1], mine)

    say("\n## The previous registration's 63 composition counts (the frozen population_claims, re-run quietly)")
    prev = rev.population_claims(lambda _m: None, C)
    ck("the previous registration's 63 counts: the 47 composition claims its frozen population_claims carries (the other 16 were data-gate / caption / record-builder lines derived only inside its dry run; their current equivalents are this doc's own §8 / §11 claims below)", f"{prev.n - len(prev.bad)} OK, {len(prev.bad)} MISMATCH")
    for ln, lab, d, m in prev.bad:
        say(f"  previous MISMATCH [L{ln}] {lab}: doc {fmt_claim(d)} vs mine {fmt_claim(m)}")
    say("\n## §2 — the population table (n / non-flicker / in-session windows (nf) / exits known / era B)")
    ck("fit dated 2020: n / non-flicker / in-session (nf) / exits known / era B", set_row(I["fit_dated"]))
    ck("fit undated 2020: n / non-flicker / in-session (nf) / exits known / era B", set_row(I["fit_und"]))
    ck("2021-22 dated: n / non-flicker / in-session (nf) / exits known / era B", set_row(I["chk22_dated"]))
    ck("2021-22 undated: n / non-flicker / in-session (nf) / exits known / era B", set_row(I["chk22_und"]))
    ck("untouched 2019 dated: n / non-flicker / in-session (nf) / exits known / era B", set_row(I["v19_dated"]))
    ck("untouched 2019 undated: n / non-flicker / in-session (nf) / exits known / era B", set_row(I["v19_und"]))
    v23 = I["v23_dated"]
    ck("untouched 2023 dated: n / non-flicker / in-session / exits known (still held) / era B",
       f"{len(v23)} / {sum(1 for b in v23 if not b.flicker)} / {sum(1 for b in v23 if b.in_bracket)} / {sum(1 for b in v23 if b.has_exit)} ({sum(1 for b in v23 if not b.has_exit)}) / {sum(1 for b in v23 if b.E >= B_FIRST)}")
    ck("untouched 2023 undated: n / non-flicker / in-session (nf) / exits known / era B", set_row(I["v23_und"]))
    h2 = I["v22h2_dated"] + I["v22h2_und"]
    ck("untouched 2022 after 06-14: dated + undated / non-flicker / in-session / exits known / era B",
       f"{len(I['v22h2_dated'])} + {len(I['v22h2_und'])} / {sum(1 for b in h2 if not b.flicker)} / {sum(1 for b in h2 if b.in_bracket)} / {sum(1 for b in h2 if b.has_exit)} / {sum(1 for b in h2 if b.E >= B_FIRST)}")
    pre = I["v20pre_dated"] + I["v20pre_und"]
    ins = [b for b in pre if b.in_bracket]
    ck("untouched 2020 before 01-27: dated + undated / non-flicker / in-session (nf) / exits known / era B",
       f"{len(I['v20pre_dated'])} + {len(I['v20pre_und'])} / {sum(1 for b in pre if not b.flicker)} / {len(ins)} ({sum(1 for b in ins if not b.flicker)}) / {sum(1 for b in pre if b.has_exit)} / {sum(1 for b in pre if b.E >= B_FIRST)}")
    va = I["virgin_all"]
    vins = [b for b in va if b.in_bracket]
    ck("the virgin block: n = undated + dated / non-flicker / in-session (nf) -> scorable (nf) / exits known / era B",
       f"{len(va)} = {len(I['virgin_und'])} + {len(I['virgin_dated'])} / {sum(1 for b in va if not b.flicker)} / {len(vins)} ({sum(1 for b in vins if not b.flicker)}) -> "
       f"{len(E['virgin'])} ({len(E['virgin_nf'])}) / {sum(1 for b in va if b.has_exit)} / {sum(1 for b in va if b.E >= B_FIRST)}")
    ck("listed 2017-18: n / non-flicker / in-session / exits known / era B", set_row(I["listed_1718"]))
    say("\n## §2a-d — streams per year, the windows' clocks, the clock-sanity rule, his sells")
    yr = sn["date"].str[:4]
    ck("streams per year (videos / session dates): 2017 / 2018 / 2019 / 2020 / 2021 / 2022 / 2023",
       " / ".join(f"{sn.loc[yr == y, 'vid'].nunique()}/{sn.loc[yr == y, 'date'].nunique()}" for y in ("2017", "2018", "2019", "2020", "2021", "2022", "2023")))
    u22 = [b for b in I["chk22_und"] if b.in_bracket and not b.flicker]
    d22 = [b for b in I["chk22_dated"] if b.in_bracket]
    fm = lambda b: hhmm_to_min(b.first_clock)   # noqa: E731
    fl = lambda b: hhmm_to_min(b.flat_clock)    # noqa: E731
    ck("2021-22 in-session windows closing at or after 10:00: undated nf / dated; undated nf opening at or after 10:00",
       f"{sum(1 for b in u22 if fm(b) >= 30)} of {len(u22)} / {sum(1 for b in d22 if fm(b) >= 30)} of {len(d22)}; {sum(1 for b in u22 if fl(b) >= 30)} of {len(u22)}")
    uf = [b for b in I["fit_und"] if b.in_bracket and not b.flicker]
    df_ = [b for b in I["fit_dated"] if b.in_bracket]
    ck("fit in-session windows closing at or after 10:00: undated nf / dated", f"{sum(1 for b in uf if fm(b) >= 30)} of {len(uf)} / {sum(1 for b in df_ if fm(b) >= 30)} of {len(df_)}")
    hb = E["held_0935"]
    ck("held before 09:35 (KOLD out): n / L7 exists (first seen 09:31-09:34) / not (09:30)", f"{len(hb)} / {sum(1 for b in hb if fm(b) >= 1)} / {sum(1 for b in hb if fm(b) < 1)}")
    ck("§2c virgin: in-session -> scorable (nf); 2021-22 undated nf -> ; dated -> ; fit dated -> ; fit undated nf -> ; fit flickers ->",
       f"{len(vins)} -> {len(E['virgin'])} ({len(E['virgin_nf'])}); {len(E['chk22_und'])}; {len(E['chk22_dated'])}; {len(E['fit_dated'])}; {len(E['fit_und'])}; {len(E['fit_fl'])}")
    ck("§2c the 9 scorable non-flicker untouched windows", ", ".join(f"{b.sym} {b.E}" for b in sorted(E["virgin_nf"], key=lambda x: (x.E, x.sym))))
    ck("§2c 2021-22 undated window dropped", ", ".join(f"{b.sym} {b.E} {why}" for b, why in dropped_windows(I["chk22_und"], mis)))
    for name, bs in (("fit dated", I["fit_dated"]), ("fit undated", I["fit_und"]), ("2021-22 dated", I["chk22_dated"]), ("virgin block", I["virgin_all"])):
        dr = dropped_windows(bs, mis)
        say(f"  - §2c dropped, {name}: " + (", ".join(f"{b.sym} {b.E}{' (flicker)' if b.flicker else ''} {why}" for b, why in dr) or "none"))
    d22x = [b for b in I["chk22_dated"] if b.has_exit]
    y21 = [b for b in d22x if b.E[:4] == "2021"]
    ck("2d: 2021-22 dated with exits / 2021 trades with a one-session sell window", f"{len(d22x)} / {sum(1 for b in y21 if b.exit_window_len() == 1)} of {len(y21)}")
    w19 = [b.exit_window_len() for b in I["v19_dated"] if b.has_exit]
    gg = {b.sym: b.exit_window_len() for b in I["v23_dated"] if b.sym in ("GSIT", "GTLB") and b.has_exit}
    ck("2d: 2019 dated sell windows span (sessions) / GSIT and GTLB 2023 span", f"{min(w19)}-{max(w19)} / {gg.get('GSIT')}, {gg.get('GTLB')}")
    ck("era B among the virgin block / of the 2021-22 dated / of the 2021-22 undated",
       f"{sum(1 for b in va if b.E >= B_FIRST)} / {sum(1 for b in I['chk22_dated'] if b.E >= B_FIRST)} / {sum(1 for b in I['chk22_und'] if b.E >= B_FIRST)}")
    ck("2021-22 in-session windows after §2c closing before 10:00: dated / undated", f"{sum(1 for b in E['chk22_dated'] if fm(b) < 30)} / {sum(1 for b in E['chk22_und'] if fm(b) < 30)}")
    f693 = next((b for b in C["buys"] if b.eid == FSLY_GATE["eid"]), None)
    ck("the FSLY known answer: eid 693 = sym, buy day, exit window, undated, non-flicker",
       f"{f693.sym} {f693.E} {f693.exit_lo}..{f693.exit_hi} {'undated' if not f693.dated else 'dated'} {'non-flicker' if not f693.flicker else 'flicker'}" if f693 else "eid 693 absent")
    return claim


def assert_populations(say, C: dict) -> None:
    """Guard (3): the set-composition claims re-run quietly at the start of a stage; any mismatch STOPs before a bar is opened."""
    cl = population_claims(lambda _m: None, C)
    if cl.bad:
        raise GuardStop("POPULATION MISMATCH with the registration: " + "; ".join(f"[L{ln}] {lab}: doc {fmt_claim(d)} vs {fmt_claim(m)}" for ln, lab, d, m in cl.bad))
    say(f"- populations re-asserted against §2 / §2a-d of this doc and the previous 63 counts: {cl.n} claims, every one equals the registration (guard 3)")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run
# ═════════════════════════════════════════════════════════════════════════════════════════════
def dry_run(say) -> int:
    say("# #705 INTRADAY 01 — DRY RUN: every input loaded, the previous 63 counts and every count of §2 / §2a-d / §11 asserted against the registration, "
        "the §2c drops listed, the data gate on the fetch list (logs only), the era-B offsets on each record's own calendar, the record builder, the pins. "
        "NO outcome: no minute file opened, no bar after a buy day, no stop / exit / R, no fit.")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    check_pinned_inputs(say)
    C = load_core(say)
    S, I, E, cal, CI, mis = C["S"], C["I"], C["E"], C["cal"], C["CI"], C["mis"]
    claim = population_claims(say, C)
    EX = {lab: (anchor, v) for anchor, lab, v in EXPECT}

    def ck(lab, mine):
        return claim(EX[lab][0], lab, EX[lab][1], mine)

    # ---- captions (parsed words)
    say("\n## §8 — WHY-lite's counts on the parsed words (his words, never a source)")
    paths = sorted(glob.glob(SUBS_GLOB))
    t0 = time.time()
    texts = rev.load_caption_texts(paths)
    nf, n60, nema, nph = why_counts(texts)
    say(f"  - {nf} videos parsed in {time.time() - t0:.0f}s")
    ck("captions (parsed words): files / 60-minute mentions / 20-EMA mentions / the phrase set", f"{nf} / {n60} / {nema} / {nph}")
    J = why_joins(texts, C)
    say(f"  - the join (phrase hit -> ticker within 30 s -> the panel exit window covers the stream's session): hits {J['hits']}, qualifying {J['qual']}, ambiguous {J['amb']}, "
        f"unambiguous 2020 joins {sum(1 for j in J['joins'] if not j['ambiguous'] and j['upload'].startswith('2020'))} (the 10-row hand-read sheet is drawn in --check)")
    # ---- the data gate
    say("\n## §11 — the data gate: the fetch list and the fetch logs (no minute file opened)")
    done, files = load_done_all()
    store = MinuteStore(done, files)
    say("  - fetch logs: " + ", ".join(f"{k} {len(v):,}" for k, v in done.items()) + "; date files " + ", ".join(f"{k} {len(v):,}" for k, v in files.items())
        + ("" if "INTRA" in done else "; the tree minutes_intra_1025 has NO _done.psv (the fetch has not run)"))
    rows = [ln.rstrip("\n").split("|") for ln in open(FETCH_LIST) if ln.strip()]
    L = {(t, d): blk for t, d, blk in rows}
    byb = Counter(L.values())
    byy = Counter(d[:4] for (_t, d) in L)
    ck("fetch list: pairs / dates / sha prefix / by block fit2020 fit2020+virgin fit2020+y2122 virgin y2122 / by year 2019 2020 2021 2022 2023 2024",
       f"{len(L)} / {len({d for _t, d in L})} / {sha(FETCH_LIST)[:8]} / {byb['fit2020']} {byb['fit2020+virgin']} {byb['fit2020+y2122']} {byb['virgin']} {byb['y2122']} / "
       + " ".join(str(byy.get(y, 0)) for y in ("2019", "2020", "2021", "2022", "2023", "2024")))
    pending, st = [], Counter()
    for (t, d) in sorted(L, key=lambda x: (x[1], x[0])):
        s_ = store.state(d, t).split("/")[0]
        st[s_] += 1
        if s_ == "missing":
            pending.append((t, d))
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(f"{OUT_DIR}/dryrun_fetch_pending.psv", "w") as fh:
        for t, d in pending:
            fh.write(f"{t}|{d}\n")
    if "INTRA" in done:
        di = done["INTRA"]
        on = {k: v for k, v in di.items() if (k[1], k[0]) in L}
        c = Counter(on.values())
        ck("the fetch log on the list: ok / empty / failed / rows not on the list / pending", f"{c['ok']} / {c['empty']} / {c.get('failed', 0)} / {len(di) - len(on)} / {len(pending)}")
        eb = Counter(L[(k[1], k[0])].split("+")[0] for k, v in on.items() if v == "empty")
        ck("empty at the source by block (the list's block column): fit 2020 / the untouched years / 2021-22", f"{eb['fit2020']} / {eb['virgin']} / {eb['y2122']}")
    else:
        say(f"  - DATA GATE OPEN: {len(pending)} pairs of the list are in no tree's log (written to dryrun_fetch_pending.psv); the fetch-log claims are not read; "
            "every fit stage refuses until minutes_intra_1025/_done.psv exists")
        for lab in ("the fetch log on the list: ok / empty / failed / rows not on the list / pending", "empty at the source by block (the list's block column): fit 2020 / the untouched years / 2021-22"):
            say(f"  [L{doc_line_of(EX[lab][0]) or '?'}] {lab} | doc {EX[lab][1]} | mine NOT READ (tree absent)")
    say(f"  - coverage of the list across every tree: " + ", ".join(f"{k} {v:,}" for k, v in sorted(st.items())) + f"; PENDING pairs {len(pending)} -> {OUT_DIR}/dryrun_fetch_pending.psv")
    allw = E["fit_dated"] + E["fit_und"] + E["fit_fl"] + E["chk22_und"] + E["chk22_dated"] + E["chk22_fl"] + E["virgin"]
    nob = sorted({(b.sym, b.E) for b in allw if not store.state(b.E, bar_sym(b.E, b.sym_a, b.sym), b).startswith("ok")}, key=lambda x: (x[1], x[0]))
    ck("scorable ENTER windows (after §2c) with no buy-day bars, by name", ", ".join(f"{s} {d}" for s, d in nob))
    ck("2021-22 deciding ENTER windows with buy-day bars ok", f"{sum(1 for b in E['chk22_und'] if store.state(b.E, bar_sym(b.E, b.sym_a, b.sym), b).startswith('ok'))} of {len(E['chk22_und'])}")
    ld = {d for _t, d in L}
    ck("early-close days: the runner's list / on or before 2024-12-31 / among the fetch list's dates",
       f"{len(EARLY_CLOSE)} / {sum(1 for d in EARLY_CLOSE if d <= CUT_B)} / {sum(1 for d in EARLY_CLOSE if d in ld)}")
    say("  - early-close dates inside the list: " + ", ".join(sorted(d for d in EARLY_CLOSE if d in ld)))
    # per-block coverage (the fetch list's blocks)
    cov = defaultdict(Counter)
    for (t, d), blk in L.items():
        cov[blk][store.state(d, t).split("/")[0]] += 1
    say("  - coverage per block: " + "; ".join(f"{blk}: " + ", ".join(f"{k} {v:,}" for k, v in sorted(c.items())) for blk, c in sorted(cov.items())))
    # ---- the exports: the era-B offsets on each record's own calendar; the record builder on the fixed sets
    say("\n## §11c — the era-B calendar index: every era-B trade's offsets bisected on ITS OWN export calendar (the previous read mixed two calendars)")
    ni = S["ni"]
    need_A, need_B = {b.sym_a for b in ni if b.has_bars} | {"QQQ", "SPY"}, {b.sym for b in ni if b.has_bars and b.E > A_LAST} | {"QQQ", "SPY"}
    M = load_for_stage(say, C, need_A, need_B)
    eraB = [b for b in I["chk22_und"] + I["chk22_dated"] + I["virgin_all"] if b.E >= B_FIRST]
    offs = {}
    for b in eraB:
        r = make_irec(b, M, "B", None, None, min_bars=0, want_minutes=False)
        if r is None:
            say(f"  - {b.sym} {b.E}: no record ({rec_drop_reason(b, M, 'B', 0)})")
            continue
        offs[b.eid] = (r.exit_lo_j, r.exit_hi_j, r.last_j, r.off_snapped)
        say(f"  - {b.sym} {b.E} ({'dated' if b.dated else 'undated'}; {'2021-22' if CHECK_WIN[0] <= b.E <= CHECK_WIN[1] else 'virgin'}): exit window {b.exit_lo or '-'}..{b.exit_hi or '-'} -> offsets "
            f"{r.exit_lo_j}-{r.exit_hi_j}" + (f"; still held, last frame offset {r.last_j}" if not b.has_exit else "") + (f"; snapped {r.off_snapped}" if r.off_snapped else ""))
    u8 = sorted(f"{offs[b.eid][0]}-{offs[b.eid][1]}" for b in I["chk22_und"] if b.E >= B_FIRST and b.eid in offs)
    ck("era-B offsets (own calendar) of the 8 undated 2021-22 trades, sorted", ", ".join(u8))
    say(f"  - exit dates not on the record's own calendar (snapped to the next session): {sum(v[3] for v in offs.values())} (expected 0)")
    say(f"\n## The record builder on the fixed sets (the era's export, a bar on the buy day, >= {REC_MIN_BARS} bars before it — ENTER >= {REC_MIN_BARS_ENTER}); nothing after the buy day read")
    nrec = {}
    for name, bs, mb_ in (("ENTER fit dated (after §2c)", E["fit_dated"], REC_MIN_BARS_ENTER), ("ENTER fit undated nf", E["fit_und"], REC_MIN_BARS_ENTER),
                          ("ENTER fit flickers", E["fit_fl"], REC_MIN_BARS_ENTER), ("ENTER 2021-22 undated nf (deciding)", E["chk22_und"], REC_MIN_BARS_ENTER),
                          ("ENTER 2021-22 dated", E["chk22_dated"], REC_MIN_BARS_ENTER), ("ENTER 2021-22 flickers", E["chk22_fl"], REC_MIN_BARS_ENTER),
                          ("ENTER virgin (veto)", E["virgin"], REC_MIN_BARS_ENTER),
                          ("STOP fit dated", I["fit_dated"], REC_MIN_BARS), ("STOP fit undated", I["fit_und"], REC_MIN_BARS), ("STOP check: virgin undated (deciding)", I["virgin_und"], REC_MIN_BARS),
                          ("STOP virgin dated (beside)", I["virgin_dated"], REC_MIN_BARS), ("STOP 2021-22 undated (beside)", I["chk22_und"], REC_MIN_BARS),
                          ("EXIT fit dated 2020", [b for b in I["fit_dated"] if b.has_exit], REC_MIN_BARS), ("EXIT check: 2021-22 dated (deciding)", I["chk22_dated"], REC_MIN_BARS),
                          ("EXIT virgin dated with exits (veto)", [b for b in I["virgin_dated"] if b.has_exit], REC_MIN_BARS)):
        reasons = Counter(rec_drop_reason(b, M, era_of(b.E), mb_) or "record" for b in bs)
        nrec[name] = reasons["record"]
        say(f"  - {name}: {len(bs)} -> records {reasons['record']}; dropped " + (", ".join(f"{k} {v}" for k, v in sorted(reasons.items()) if k != "record") or "none"))
    ck("ENTER deciding 2021-22 windows -> records after the 20-bar floor", f"{len(E['chk22_und'])} -> {nrec['ENTER 2021-22 undated nf (deciding)']}")
    say(f"  - STOP's deciding set: 62 undated untouched -> {nrec['STOP check: virgin undated (deciding)']} records (the doc expects about 58 at the 2021-22 rate; a too-few reading is live)")
    # ---- from clocks alone: the records whose S9 / S10 can differ from S1 (an in-session holding frame at or after 10:00)
    say("\n## §6b — from clocks alone: records with an in-session holding frame on the buy day at or after 10:00 (the read minute lets S9 and S10 differ from S1)")
    for name, bs in (("STOP fit dated", I["fit_dated"]), ("STOP fit undated", I["fit_und"]), ("STOP check: virgin undated (deciding)", I["virgin_und"]),
                     ("virgin dated", I["virgin_dated"]), ("2021-22 undated", I["chk22_und"]), ("2021-22 dated", I["chk22_dated"])):
        n10 = sum(1 for b in bs if b.first_clock and b.f_ctx == "in" and hhmm_to_min(b.first_clock) >= 30)
        say(f"  - {name}: {n10} of {len(bs)} (S9 != S1 and S10 != S1 possible; S9 / S10 read at first_clock on these, at the fill minute elsewhere)"
            + (" -> under 20: an S9 / S10 choice would read INCONCLUSIVE-by-size there" if (n10 < STOP_MIN_DIFFER and "deciding" in name) else ""))
    # ---- the EXIT warm-up from the fetch logs + the calendar (no file opened): the bars before the buy day per trade, against the 65-bar floor
    floor = EMA_SEED_BARS + EMA_POST_SEED_BARS
    say(f"\n## §7a — the EXIT warm-up from the fetch logs and the calendar alone: 60-minute bars in the {WARMUP_SESSIONS} sessions before the buy day (7 per logged session, 4 on an "
        f"early-close day, 0 when the log says empty) against the `ema_thin` floor of {EMA_SEED_BARS} seed + {EMA_POST_SEED_BARS} post-seed = {floor} bars (the buy day's own pre-fill bars add to these)")
    thin = {}
    for name, bs in (("EXIT check 2021-22 dated (deciding)", [b for b in I["chk22_dated"] if b.has_exit]), ("EXIT fit dated 2020", [b for b in I["fit_dated"] if b.has_exit]),
                     ("EXIT virgin dated (veto)", [b for b in I["virgin_dated"] if b.has_exit]), ("2021-22 undated (beside)", [b for b in I["chk22_und"] if b.has_exit])):
        wb = []
        for b in bs:
            bars = 0
            for i in range(max(0, b.Ei - WARMUP_SESSIONS), b.Ei):
                d = cal[i]
                if store.state(d, bar_sym(d, b.sym_a, b.sym), b).startswith("ok"):
                    bars += 4 if d in EARLY_CLOSE else 7
            wb.append((bars, b))
        under = [(n_, b) for n_, b in wb if n_ < floor]
        dist = Counter(n_ for n_, _b in wb)
        thin[name] = (len(under), len(bs), sum(1 for n_, _b in wb if n_ == 67))
        say(f"  - {name}: warm-up bars {dict(sorted(dist.items()))}; under the {floor}-bar floor {len(under)} of {len(bs)} = {pct(len(under) / len(bs) if bs else float('nan'))} "
            f"(the §7c INCONCLUSIVE bar is {pct(EXIT_ABSTAIN_MAX)} of the deciding trades; a 67 = one early close inside)" + (": " + ", ".join(f"{b.sym} {b.E} ({n_})" for n_, b in under) if under else ""))
    t_dec, t_fit, t_v = thin["EXIT check 2021-22 dated (deciding)"], thin["EXIT fit dated 2020"], thin["EXIT virgin dated (veto)"]
    ck("EXIT warm-up bars from the fetch logs + calendar: under the 65-bar floor, deciding 2021-22 dated / fit 2020 dated / virgin dated; 67-bar warm-ups (an early close inside) deciding / fit / virgin",
       f"{t_dec[0]} of {t_dec[1]} / {t_fit[0]} of {t_fit[1]} / {t_v[0]} of {t_v[1]}; {t_dec[2]} / {t_fit[2]} / {t_v[2]}")
    # ---- guard (5) on the real fit sets
    say("\n## Guard (5) on the real fit sets: every registered fit buy passes its stage's predicate; every 2021-22 and virgin-block buy is refused by every fit stage")
    fit_sets = {"enter": E["fit_dated"] + E["fit_und"], "stop": I["fit_dated"] + I["fit_und"], "exit": [b for b in I["fit_dated"] if b.has_exit]}
    viol = {st_: [(b.eid, b.sym, b.E, fit_set_violation(st_, b)) for b in bs if fit_set_violation(st_, b)] for st_, bs in fit_sets.items()}
    refused = {st_: sum(1 for b in I["chk22_dated"] + I["chk22_und"] + I["virgin_all"] if fit_set_violation(st_, b) is not None) for st_ in fit_sets}
    say("  - fit sets: " + ", ".join(f"{k} {len(v)} buys, violations {len(viol[k])}" for k, v in fit_sets.items()) + f"; check-side buys refused by every stage: {refused} of {len(I['chk22_dated'] + I['chk22_und'] + I['virgin_all'])}")
    if any(viol.values()):
        claim.bad.append((0, "guard (5) fit-set predicates", 0, sum(len(v) for v in viol.values())))
    # ---- guard (5) per ticker and date (dates only): fit trades whose planned span touches a session after a check-side trade's buy day
    say(f"\n## Guard (5) per ticker and date (C9 / N1 / N3 / N5, dates only): the (symbol, session) pairs after any check-side trade's buy day (buy day + 1 .. "
        f"exit_hi + {TAIL_SESSIONS}; a still-held trade: its last frame + {TAIL_SESSIONS}); a fit trade whose planned span — ENTER {LOOKBACK_SESSIONS['enter']} sessions "
        f"before .. the buy day; STOP {LOOKBACK_SESSIONS['stop']} before .. exit_hi + 1; EXIT {LOOKBACK_SESSIONS['exit']} before .. exit_hi + {TAIL_SESSIONS} + 1 — "
        "touches one is excluded from that fit stage, by name (ENTER's beside windows too)")
    cs = collision_summary(C, M.get("last_seen"))
    say(f"  - forbidden (symbol, session) pairs: {len(cs['forbid']):,} over {len({p[0] for p in cs['forbid']})} names")
    for lab in ("enter", "enter_beside", "stop", "exit"):
        x = cs[lab]
        say(f"  - {lab.upper().replace('_', ' ')} ({x['n']} trades): excluded {len(x['excluded'])} ({x['pairs']} pairs): " + (", ".join(f"{s} {e}" for s, e in x["excluded"]) or "none")
            + "; check-side trades they would expose: " + (", ".join(f"{s} {e}" for _i, s, e in x["exposed"]) or "none"))
    ck("guard (5) per ticker-date: fit trades excluded by their planned span, ENTER / STOP / EXIT; check-side trades exposed",
       f"{len(cs['enter']['excluded'])} / {len(cs['stop']['excluded'])} / {len(cs['exit']['excluded'])}; {len(cs['enter']['exposed'])} / {len(cs['stop']['exposed'])} / {len(cs['exit']['exposed'])}")
    ck("guard (5) per ticker-date: the excluded fit trades by name",
       "; ".join(f"{st_.upper()}: " + ", ".join(f"{s} {e}" for s, e in cs[st_]["excluded"]) for st_ in STAGES))
    xb = cs["enter_beside"]
    ck("guard (5) per ticker-date: ENTER's beside windows excluded (N5): n of windows; by name", f"{len(xb['excluded'])} of {xb['n']}; " + ", ".join(f"{s} {e}" for s, e in xb["excluded"]))
    # N3: the belt on BAR indices — every kept fit trade's pre-buy daily reads (the bars `lookback_pairs` lists on the record's own calendar,
    # dates only) against the forbidden pairs; a hole stretches 50 bars past 50 sessions, which the session span cannot see
    lb = {}
    for lab, (st_, _bs) in fit_stage_sets(C).items():
        mb_ = REC_MIN_BARS_ENTER if st_ == "enter" else REC_MIN_BARS
        hits, longer = [], []
        for b in cs[lab]["kept"]:
            era = era_of(b.E)
            if rec_drop_reason(b, M, era, mb_) is not None or b.Ei < 0:
                continue
            D = M["Ds"][era]
            bars_, cidx_ = bars_of(D, b.sym_a if era == "A" else b.sym)
            e_ = int(np.searchsorted(cidx_, bisect.bisect_left(D.cal, date.fromisoformat(b.E))))
            pr = lookback_pairs(b, bars_, cidx_, e_, D.cal, mb_)
            if pr and pr[0][1] < cal[max(0, b.Ei - LOOKBACK_SESSIONS[st_])]:
                longer.append(f"{b.sym} {b.E}")
            if any(p_ in cs["forbid"] for p_ in pr):
                hits.append(f"{b.sym} {b.E}")
        lb[lab] = (hits, longer)
        say(f"  - {lab.upper().replace('_', ' ')}: kept {len(cs[lab]['kept'])}; pre-buy daily reads by bar index ({mb_} bars" + (", the dated base low from its base date" if mb_ >= REC_MIN_BARS else "")
            + f") reaching further back than the {LOOKBACK_SESSIONS[st_]}-session span {len(longer)}" + (f" ({', '.join(longer[:8])}{' ...' if len(longer) > 8 else ''})" if longer else "")
            + f"; on a forbidden pair {len(hits)}" + (": " + ", ".join(hits) if hits else ""))
    ck("guard (5) the kept fit trades' pre-buy daily reads by bar index on a forbidden pair (N3): ENTER / ENTER beside / STOP / EXIT",
       " / ".join(str(len(lb[k][0])) for k in ("enter", "enter_beside", "stop", "exit")))
    # X1: the speed trail's 121-session forward window (sliced off the bar arrays by the frozen `cb.forward_window`) on the kept EXIT fit trades
    sb = [(b, speed_trail_bound(b, cal, cs["forbid"])) for b in sorted(cs["exit"]["kept"], key=lambda x: (x.E, x.eid))]
    sb = [(b, j) for b, j in sb if j is not None]
    say(f"  - X1: kept EXIT fit trades whose speed-trail window (sessions 1 .. {HORIZON + 1}) holds a forbidden session: {len(sb)} — the fit bounds their ours / his / chosen "
        "on the session before it (`guard_bound_guards`; every one lies after exit_hi + 21 by the exclusion above): " + ", ".join(f"{b.sym} {b.E} (+{j})" for b, j in sb))
    ck("X1: the kept EXIT fit trades whose speed-trail window the guard bounds: n; by name", f"{len(sb)}; " + ", ".join(f"{b.sym} {b.E}" for b, _j in sb))
    if any(j <= (b.exit_hi_i - b.Ei) + TAIL_SESSIONS + 1 for b, j in sb):
        claim.bad.append((0, "X1: a guard bound inside exit_hi + 21 on a kept EXIT fit trade", 0, sum(1 for b, j in sb if j <= (b.exit_hi_i - b.Ei) + TAIL_SESSIONS + 1)))
    # ---- ENTER's check: the previous read's draw population (sets only)
    dp = S["ent_chk_dated"] + S["ent_chk_und"]
    ck("ENTER check: the random-price draw population (the previous read's) = dated (flickers) + undated non-flicker (DWAC in)",
       f"{len(dp)} = {len(S['ent_chk_dated'])} ({sum(1 for b in S['ent_chk_dated'] if b.flicker)}) + {len(S['ent_chk_und'])} ({sum(1 for b in S['ent_chk_und'] if b.eid not in {x.eid for x in E['chk22_und']})})")
    # ---- the window table (outcome-free)
    rows = []
    for name, bs in (("fit_dated", E["fit_dated"]), ("fit_und", E["fit_und"]), ("fit_fl", E["fit_fl"]), ("chk22_und", E["chk22_und"]), ("chk22_dated", E["chk22_dated"]),
                     ("chk22_fl", E["chk22_fl"]), ("virgin", E["virgin"])):
        for b in bs:
            rows.append(dict(set=name, eid=b.eid, sym=b.sym, E=b.E, dated=b.dated, flicker=b.flicker, flat_clock=b.flat_clock, first_clock=b.first_clock,
                             width_min=hhmm_to_min(b.first_clock) - hhmm_to_min(b.flat_clock), minutes=store.state(b.E, bar_sym(b.E, b.sym_a, b.sym), b),
                             early_close=b.E in EARLY_CLOSE, exit_lo=b.exit_lo, exit_hi=b.exit_hi))
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/dryrun_windows.tsv", sep="\t", index=False)
    say(f"\n- ENTER's windows written ({len(rows)} rows) -> {OUT_DIR}/dryrun_windows.tsv (clocks and coverage only; never refuses a run)")
    # ---- the freeze body, the pins
    h = store_freeze_body()
    say(f"- the body above the marker stored under freeze_bodies/ ({h[:12]}...): the freeze pin `doc_body_freeze` will name it")
    p = pins()
    say("\n## Pins (sha256) — every value below goes under the doc's freeze marker line before the check (fit printouts and the ledger once they exist)")
    for k, v in p.items():
        say(f"- {k}: {v}")
    miss = freeze_missing(DOC, p)
    say(f"- freeze record: {'every pin above is written under the freeze marker line' if not miss else 'NOT YET under the freeze marker line: ' + str(len(miss)) + ' pins'}")
    ch = chosen_lines()
    say("- CHOSEN lines above the marker: " + (", ".join(f"{k.upper()} {len(v)}" for k, v in sorted(ch.items())) if ch else "none"))
    say(f"\n## RESULT: {claim.n} claims, {claim.n - len(claim.bad)} OK, {len(claim.bad)} MISMATCH")
    for ln, lab, d, m in claim.bad:
        say(f"  MISMATCH [L{ln}] {lab}: doc {fmt_claim(d)} vs mine {fmt_claim(m)}")
    if claim.bad:
        say("STOPPED: the dry run does not reproduce the registration (amend the doc or the derivation before the freeze)")
        return 3
    say(f"\nDRY RUN COMPLETE: every count reproduced; no minute file opened ({sum(store.reads.values())} reads), no bar after a buy day read, no outcome computed"
        + (f"; DATA GATE OPEN: {len(pending)} pairs pending" if pending else "; the data gate is closed (0 pairs pending)") + ".")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# ENTER fit
# ═════════════════════════════════════════════════════════════════════════════════════════════
def enter_row(r: IRec, res: dict) -> dict:
    b0 = h60_bars(r.mb, r.b.E)[0]                                      # the BUILDER's first bar (gate ii compares it with the raw 30-minute high — C8)
    row = dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, minutes=r.minutes_state, scorable=True, flat_clock=r.b.flat_clock,
               first_clock=r.b.first_clock, adr20=r.adr20, early_close=r.b.E in EARLY_CLOSE,
               L1_raw=rev.opening_range_high(r.mb, 5), L6_raw=rev.opening_range_high(r.mb, 60), L7_raw=r.levels.get("L7_raw"), L8_raw=r.levels.get("L8_raw"),
               H60_0_high=(b0.h if b0 is not None else None))
    for lv in ALL_LEVELS:
        row[f"{lv}_price"] = res[lv].get("price") if lv in NEW_LEVELS else r.levels.get(lv)
        row[f"{lv}_cross"] = res[lv]["cross"]
        row[f"{lv}_feasible"] = res[lv]["feasible"]
        row[f"{lv}_verdict"] = res[lv]["verdict"]
        if lv in res.get("shift", {}):
            row[f"{lv}_shift_feasible"] = res["shift"][lv]["feasible_share"]
            row[f"{lv}_shift_hit"] = res["shift"][lv]["hit_share"]
            row[f"{lv}_shift_no_room"] = res["shift"][lv]["no_room"]
    row.update(control_feasible=res["control"]["feasible_share"], control_hit=res["control"]["hit_share"], union_feasible=res["union"]["feasible"], union_hit=res["union"]["hit"],
               union_shift_feasible=res["union"].get("shift_feasible"))
    return row


def enter_level_lines(say, summ: dict, label: str, chosen: "str | None" = None) -> None:
    say(f"- {label}: {summ['n']} scorable windows")
    for lv in ALL_LEVELS:
        s_ = summ[lv]
        tag = " (CHOSEN)" if lv == chosen else (" (new)" if lv in NEW_LEVELS else " (re-read)")
        say(f"  {lv}{tag}: feasible {s_['feasible']} = {pct(s_['feasible_share'][0])} +-{100 * s_['feasible_share'][1]:.0f}; hit-or-ballpark {s_['hit']} = {pct(s_['hit_share'][0])} "
            f"+-{100 * s_['hit_share'][1]:.0f}; shifted-window control feasible {pct(s_['shift_feasible'])} hit {pct(s_['shift_hit'])} (no_room {s_['shift_no_room']}); "
            + ", ".join(f"{k} {v}" for k, v in sorted(s_["verdicts"].items())))
    say(f"  random-price control: feasible {pct(summ['control']['feasible_share'])}, hit-or-ballpark {pct(summ['control']['hit_share'])}")
    u = summ["union"]
    say(f"  'any opening range' (L7 / L1 / L8; beside): feasible {pct(u['feasible_share'][0])}, hit {pct(u['hit_share'][0])}; its random-price control = the plain one "
        f"({pct(u['control_feasible'])}: a price is not level-specific, so the union's draw is the same draw); its shifted-window control {pct(u['shift_feasible'])}")


def enter_fit(say, C: dict, M: "dict | None" = None) -> int:
    stage_header(say, "enter", "the opening-range level he buys at — L7 (1-minute), L8 (30-minute), L9 (prior 60-minute bar) — bounded by the panel clock (§5)")
    S, E, I, mis, cal = C["S"], C["E"], C["I"], C["mis"], C["cal"]
    fit = E["fit_dated"] + E["fit_und"]
    say(f"- fit set: {len(E['fit_dated'])} dated + {len(E['fit_und'])} undated non-flicker in-session windows of 2020 after §2c decide; {len(E['fit_fl'])} flickers beside")
    fit_eids = assert_fit_set(say, "enter", fit)
    beside_buys = enter_beside_buys(E)
    if M is None:
        a, b_ = names_of(fit + beside_buys)
        M = load_for_stage(say, C, a, b_)
    forbid = forbidden_pairs(C, M.get("last_seen"))
    fit = exclude_collisions(say, "enter", fit, forbid, cal, "the fit windows")
    beside_buys = exclude_collisions(say, "enter", beside_buys, forbid, cal, "the beside windows")
    keep = {b.eid for b in beside_buys}
    E = dict(E, **{k: [b for b in E[k] if b.eid in keep] for k in ("fit_fl", "pre_dated_fit", "pre_und_fit", "held_0935", "prefirst_fit")})
    store, guard = M["store"], BarGuard(fit_eids, frozenset(forbid))
    store.forbid = frozenset(forbid)
    preload_buy_days(store, fit + beside_buys)
    recs, drop = recs_for(fit, M, store, guard, min_bars=REC_MIN_BARS_ENTER)
    say(f"- records: {len(recs)} (dropped {dict(drop)}; the ENTER record floor = {REC_MIN_BARS_ENTER} bars before the buy day); minutes: "
        + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r.minutes_state.split('/')[0] for r in recs).items())))
    gate_ohlc(say, [r for r in recs if r.mb is not None], store, lambda r: [0], "enter_fit")
    rng = rng_for(RANDOM_KEY)
    scored, rows = {}, []
    for r in sorted(recs, key=lambda x: (x.b.E, x.b.eid)):
        if r.mb is None:
            rows.append(dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, minutes=r.minutes_state, scorable=False))
            continue
        res = enter_score_trade(r, rng)
        scored[r.b.eid] = res
        rows.append(enter_row(r, res))
    gate_level_order(say, [rw for rw in rows if rw.get("scorable")], "enter_fit")
    gate_iv_enter(say, recs)
    summ = enter_summary(scored)
    say(f"\n## THE FIT (§5c): L7-L9 on the deciding windows ({sum(1 for r in recs if r.mb is None)} without minutes read `no_minutes`; a level that does not exist yet at first_clock reads "
        "`no_level_yet`: L7 before 09:31, L8 / L9 before 10:00, L1 before 09:35, L6 before 10:30)")
    chosen = choose_level(summ) if summ["n"] else "L8"
    enter_level_lines(say, summ, "deciding fit windows (dated + undated non-flicker)", chosen)
    for lab, pred in (("dated", lambda r: r.b.dated), ("undated non-flicker", lambda r: not r.b.dated)):
        sub = {k: v for k, v in scored.items() if pred(next(r for r in recs if r.b.eid == k))}
        if sub:
            enter_level_lines(say, enter_summary(sub), lab)
    say("\n## BESIDE")
    for lab, bs in (("flickers 2020 (in-session windows after §2c)", E["fit_fl"]), ("pre-market-flat windows, dated 2020", E["pre_dated_fit"]), ("pre-market-flat windows, undated 2020", E["pre_und_fit"])):
        rr, _d = recs_for(bs, M, store, guard, min_bars=REC_MIN_BARS_ENTER)
        rr = [r for r in rr if r.mb is not None and hhmm_to_min(r.b.first_clock) is not None and hhmm_to_min(r.b.flat_clock) is not None]
        if not rr:
            say(f"- {lab}: no scorable trade")
            continue
        sc = {r.b.eid: enter_score_trade(r, rng) for r in sorted(rr, key=lambda x: (x.b.E, x.b.eid))}
        enter_level_lines(say, enter_summary(sc), lab)
        rows += [dict(enter_row(r, sc[r.b.eid]), beside=lab) for r in rr]
    held_lines(say, E["held_0935"], M, store, guard)
    crossed_lines(say, "pre-market first sightings, dated 2020 (crossed that session)", E["prefirst_fit"], M, store, guard)
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/enter_fit_trades.tsv", sep="\t", index=False)
    ledger_append("enter-fit", f"{OUT_DIR}/enter_fit_trades.tsv")
    obj = dict(level=chosen, n=summ["n"], summary={lv: dict(feasible=summ[lv]["feasible"], hit=summ[lv]["hit"], shift_feasible=summ[lv]["shift_feasible"]) for lv in ALL_LEVELS} if summ["n"] else {},
               control=summ["control"] if summ["n"] else {})
    write_chosen("enter", obj, chosen)
    say(f"\nCHOSEN ENTER: {chosen}")
    say("- the chain carries this level's price where it is feasible on a trade, else the registered fill (`fill_fallback`); §5d's check reads 2021-22 ONCE in --check")
    return 0


def held_lines(say, buys: list, M: dict, store: MinuteStore, guard) -> None:
    """Beside: the held-before-09:35 trades on L7 — the 1-minute high exists for those first seen at 09:31 or later; did the session cross it by first_clock?"""
    rr, _d = recs_for(buys, M, store, guard, min_bars=REC_MIN_BARS_ENTER)
    out = []
    for r in rr:
        fm = hhmm_to_min(r.b.first_clock)
        if r.mb is None or fm is None:
            out.append(f"{r.b.sym} {r.b.E}: no minutes")
            continue
        L = intraday_levels(r)
        if fm < 1 or L["L7"] is None:
            out.append(f"{r.b.sym} {r.b.E} first {r.b.first_clock}: L7 does not exist yet")
            continue
        m = first_cross_from(r.mb, L["L7"], LEVEL_EXISTS["L7"])
        out.append(f"{r.b.sym} {r.b.E} first {r.b.first_clock}: L7 {L['L7']:.2f} crossed at {min_to_hhmm(m) if m is not None else '-'} -> {'by first_clock' if (m is not None and m <= fm) else 'not by first_clock'}")
    say("- held before 09:35, L7 (beside): " + ("; ".join(out) if out else "none"))


def crossed_lines(say, label: str, buys: list, M: dict, store: MinuteStore, guard) -> None:
    rr, _d = recs_for(buys, M, store, guard, min_bars=REC_MIN_BARS_ENTER)
    rr = [r for r in rr if r.mb is not None]
    if not rr:
        say(f"- {label}: no scorable trade")
        return
    cnt = Counter()
    for r in rr:
        L = intraday_levels(r)
        cnt[("L7", first_cross_from(r.mb, L["L7"], LEVEL_EXISTS["L7"]) is not None)] += 1
        cnt[("L8", first_cross_from(r.mb, L["L8"], LEVEL_EXISTS["L8"]) is not None)] += 1
        cnt[("L9", l9_cross(r.mb, L) is not None)] += 1
    say(f"- {label} ({len(rr)}): " + "; ".join(f"{lv} crossed that session {cnt[(lv, True)]}" for lv in NEW_LEVELS))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# STOP fit
# ═════════════════════════════════════════════════════════════════════════════════════════════
def stop_table_lines(say, tab: dict, extra: "dict | None" = None, label: str = "") -> None:
    hdr = ["level-variant", "tightness (median width)", "traded through", "certain", "unresolved", "H_cond", "H_all", "eligible", "differ from S1", "no-bar sessions"]
    if extra:
        hdr += list(extra.keys())
    rows = []
    for Lname in STOP_LEVELS + STOP_CONTROLS:
        for V in STOP_VARIANTS:
            t = tab[(Lname, V)]
            row = [f"{Lname}-{V}", pct(t["tight"]), t["any"], t["certain"], t["unresolved"], pct(t["H_cond"]), pct(t["H_all"]), t["eligible"],
                   t["differ"] if Lname in ("S9", "S10") else "-", t["no_bar"] if V == "H" else "-"]
            if extra:
                row += [pct(x[(Lname, V)]["H_cond"]) if (Lname, V) in x else "-" for x in extra.values()]
            rows.append(row)
    if label:
        say(label)
    for ln in rp.table(hdr, rows):
        say(ln)


def stop_rows(recs: list, sight, store: MinuteStore) -> list:
    rows = []
    for r in recs:
        row = dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, era=r.era, dated=r.b.dated, flicker=r.b.flicker, rebuy=r.b.rebuy, fill=r.fill, fill_minute=r.fill_minute, fill_src=r.fill_src,
                   fill_fallback=r.fill_fallback, adr20=r.adr20, exit_lo=r.b.exit_lo, exit_hi=r.b.exit_hi, exit_lo_j=r.exit_lo_j, exit_hi_j=r.exit_hi_j, last_j=r.last_j,
                   minutes=r.minutes_state, read_minute=r.read_minute, S1_is_S2=r.stop_levels.get("S1_is_S2"), S9_is_S1=r.stop_levels.get("S9_is_S1"), S10_is_S1=r.stop_levels.get("S10_is_S1"))
        smas = smas_for(r.bars)
        for Lname in STOP_LEVELS + STOP_CONTROLS:
            row[f"{Lname}_level0"] = rev.level_at(r, r.stop_levels[Lname], 0, smas)
            for V in STOP_VARIANTS:
                h = held_through_intra(r, Lname, V, smas, sight, store)
                row[f"{Lname}_{V}_any"], row[f"{Lname}_{V}_certain"], row[f"{Lname}_{V}_unresolved"], row[f"{Lname}_{V}_first_j"], row[f"{Lname}_{V}_event_m"] = h["any"], h["certain"], h["unresolved"], h["first_j"], h["event_m"]
        rows.append(row)
    return rows


def risk_block(say, recs: list, cal_u: list, w0: int, map_b, store: MinuteStore, label: str) -> dict:
    """§6a: sized on the level's distance (1% / 30% cap), booked at the actual exit under the cell, through his exit_hi; the realised-R tail."""
    say(f"\n## RISK ({label}): sized on the level's distance, booked at the cell's exit (T at the level / the gap open; C the next open; H the next minute's open after the bar); "
        "an H stop can realise well beyond -1R; nothing is resized")
    risk = {}
    for Lname in STOP_LEVELS + STOP_CONTROLS:
        for V in STOP_VARIANTS:
            trades, skipped = [], Counter()
            for r in recs:
                if r.exit_hi_j is None:
                    skipped["no_exit"] += 1
                    continue
                lvl = r.stop_levels[Lname]
                smas = smas_for(r.bars)
                L0 = rev.level_at(r, lvl, 0, smas)
                width = (r.fill - L0) / r.fill if np.isfinite(L0) else float("nan")
                if not width > 0:
                    skipped["level_at_or_above_fill"] += 1
                    continue
                j, px, kind = stop_walk_cell(r, lvl, V, smas, store, r.exit_hi_j)
                t = simple_leg_trade(r, j, px, kind, width, map_b, len(cal_u))
                if t is not None:
                    trades.append(t)
            say(f"- {Lname}-{V} (skipped: " + (", ".join(f"{k} {v}" for k, v in sorted(skipped.items())) or "none") + ")")
            risk[f"{Lname}-{V}"] = risk_readout(say, "sized on the level", trades, cal_u, w0)
    return risk


def stop_fit(say, C: dict, M: "dict | None" = None) -> int:
    stage_header(say, "stop", "the intraday lows he held THROUGH — S1 / S3 / S9 / S10 as a touch, a daily close and a 60-minute close (§6)")
    S, I, mis, cal, CI = C["S"], C["I"], C["mis"], C["cal"], C["CI"]
    ent = read_chosen("enter")
    chosen_level = ent["object"]["level"]
    fit = I["fit_dated"] + I["fit_und"]
    say(f"- fit set: dated 2020 {len(I['fit_dated'])} + exact-day undated 2020 {len(I['fit_und'])} (flickers included); ENTER's fit level {chosen_level} where feasible, else the registered fill")
    fit_eids = assert_fit_set(say, "stop", fit)
    if M is None:
        a, b_ = names_of(fit)
        M = load_for_stage(say, C, a, b_)
    forbid = forbidden_pairs(C, M.get("last_seen"))
    fit = exclude_collisions(say, "stop", fit, forbid, cal, "the fit trades")
    store, guard, sight = M["store"], BarGuard(fit_eids, frozenset(forbid)), M["sight"]
    store.forbid = frozenset(forbid)
    old_store = store.restricted(OLD_TREES)
    preload_buy_days(store, fit)
    recs, drop = recs_for(fit, M, store, guard)
    say(f"- records: {len(recs)} (dropped {dict(drop)}; the record floor = {REC_MIN_BARS} bars before the buy day)")
    st = preload_sessions(store, recs, 1, lambda r: r.exit_hi_j if r.exit_hi_j is not None else r.last_j)
    say(f"- hold sessions preloaded: " + ", ".join(f"{k} {v:,}" for k, v in sorted(st.items())) + f"; files read " + ", ".join(f"{k} {v}" for k, v in sorted(store.reads.items())))
    g8_run(say, recs, "stop_fit")
    cc = apply_chain(recs, chosen_level, None, mis)
    say("- the chain's fills: " + ", ".join(f"{k} {v}" for k, v in sorted(cc.items())))
    gate_ohlc(say, recs, store, lambda r: range(0, (r.exit_hi_j if r.exit_hi_j is not None else 0) + 1), "stop_fit")
    gate_iv_stop(say, recs, sight, store, old_store)
    gate_c_implies_h(say, recs, store, "stop_fit")
    gate_vi_fsly(say, recs, store)
    say("\n## THE FIT (§6b): held-through rates, level x variant (H_cond = certain / traded through by exit_hi; H_all = certain / all; the buy-day certainty rule)")
    tab_all = stop_table_intra(recs, sight, store)
    tab_d = stop_table_intra([r for r in recs if r.b.dated], sight, store)
    tab_u = stop_table_intra([r for r in recs if not r.b.dated], sight, store)
    old = old_rule_table(recs, sight, store, old_store)
    stop_table_lines(say, tab_all, {"dated": tab_d, "undated": tab_u, "OLD rule (S1 / S3 T / C)": old})
    say("- the four old cells under the OLD certainty rule vs the NEW: " + "; ".join(f"{L}-{V} old {pct(old[(L, V)]['H_cond'])} ({old[(L, V)]['certain']} / {old[(L, V)]['any']}) -> new "
        f"{pct(tab_all[(L, V)]['H_cond'])} ({tab_all[(L, V)]['certain']} / {tab_all[(L, V)]['any']})" for L in ("S1", "S3") for V in ("T", "C")))
    chosen = choose_stop(tab_all)
    say(f"- his stop ~ the tightest eligible cell among the 12 (S8 and the 50-day are controls) with a positive median width, >= {STOP_MIN_TRADED} traded through and H_cond <= {pct(STOP_H_CHOOSE)} "
        f"-> CHOSEN {chosen[0] + '-' + chosen[1] if chosen else 'none'}")
    rb = [r for r in recs if r.b.rebuy]
    if rb:
        tr = stop_table_intra(rb, sight, store)
        say(f"- re-buys ({len(rb)}) apart: " + "; ".join(f"{L}-{V} H_cond {pct(tr[(L, V)]['H_cond'])}" for L in STOP_LEVELS for V in STOP_VARIANTS))
    risk = risk_block(say, recs, cal, CI[FIT_WIN[0]], M["map_b"], store, "§6a, the 2020 fit")
    rows = stop_rows(recs, sight, store)
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/stop_fit_trades.tsv", sep="\t", index=False)
    ledger_append("stop-fit", f"{OUT_DIR}/stop_fit_trades.tsv")
    tab_rows = [dict(level=L, variant=V, **{k: v for k, v in tab_all[(L, V)].items()}) for L in STOP_LEVELS + STOP_CONTROLS for V in STOP_VARIANTS]
    pd.DataFrame(tab_rows).to_csv(f"{OUT_DIR}/stop_fit_levels.tsv", sep="\t", index=False)
    ledger_append("stop-fit", f"{OUT_DIR}/stop_fit_levels.tsv")
    text = f"{chosen[0]}-{chosen[1]}" if chosen else "none"
    obj = dict(level=chosen[0] if chosen else None, variant=chosen[1] if chosen else None,
               fit_table={f"{L}-{V}": {k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in tab_all[(L, V)].items()} for L in STOP_LEVELS + STOP_CONTROLS for V in STOP_VARIANTS},
               enter_level=chosen_level, risk=risk)
    write_chosen("stop", obj, text)
    say(f"\nCHOSEN STOP: {text}")
    say("- §6b's check reads the 62 undated untouched trades on every cell ONCE in --check (the chosen cell must hold H_cond <= 15% there); the 27 untouched dated and 2021-22 are beside")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# EXIT fit
# ═════════════════════════════════════════════════════════════════════════════════════════════
def exit_rate_lines(say, rates: dict, label: str, chosen: "str | None" = None) -> None:
    say(f"- {label}: " + "; ".join(f"{v}{' (CHOSEN)' if v == chosen else ''} last-leg hit {pct(rates[v][0])} / half-leg hit {pct(rates[v][1])} on {rates[v][2]}" for v in EXIT_VARIANTS))


def exit_rows(recs: list, preps: dict, rates: dict) -> list:
    rows = []
    for r in recs:
        prep = preps.get(r.b.eid)
        row = dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, era=r.era, flicker=r.b.flicker, fill=r.fill, fill_minute=r.fill_minute, fill_src=r.fill_src, stop=r.stop, stop_src=r.stop_src,
                   exit_lo_j=r.exit_lo_j, exit_hi_j=r.exit_hi_j, window_len=r.b.exit_window_len(), J_tail=prep["J_tail"] if prep else None, cut_why=prep["why"] if prep else None,
                   bars_before_armed=prep["armed"] if prep else None, seed_residual=prep["residual"] if prep else None, abstain=prep["abstain"] if prep else None,
                   warmup_bars=prep["seq"].warmup_bars if prep else None, missing_sessions=prep["seq"].missing_sessions if prep else None)
        for v in EXIT_VARIANTS:
            per = rates[v][3].get(r.b.eid, {})
            for k_, val in per.items():
                row[f"{v}_{k_}"] = val
        rows.append(row)
    return rows


def bar_rows(recs: list, preps: dict) -> list:
    out = []
    for r in recs:
        prep = preps.get(r.b.eid)
        if not prep:
            continue
        seq = prep["seq"]
        for i, (j, x) in enumerate(seq.items):
            out.append(dict(eid=r.b.eid, sym=r.b.sym, j=j, k=x.k, close_minute=x.close_minute, o=x.o, h=x.h, l=x.l, c=x.c, ema=seq.ema[i], sma=seq.sma[i], armed=int(i >= (prep["armed"] or 10 ** 9))))
    return out


def exit_fit(say, C: dict, M: "dict | None" = None) -> int:
    stage_header(say, "exit", "the FSLY rule on the clock-anchored 60-minute 20-EMA — E1-E4 under the chain's fill and stop (§7)")
    S, I, mis, cal, CI = C["S"], C["I"], C["mis"], C["cal"], C["CI"]
    ent, stp = read_chosen("enter"), read_chosen("stop")
    chosen_level = ent["object"]["level"]
    chosen_stop = (stp["object"]["level"], stp["object"]["variant"]) if stp["object"]["level"] else None
    fit = [b for b in I["fit_dated"] if b.has_exit]
    say(f"- fit set: dated 2020 with a known exit {len(fit)}; the chain: fill {chosen_level} (fit choice; registered where infeasible), stop {chosen_stop or 'registered (S1-T dated)'}")
    fit_eids = assert_fit_set(say, "exit", fit)
    if M is None:
        a, b_ = names_of(fit)
        M = load_for_stage(say, C, a, b_)
    forbid = forbidden_pairs(C, M.get("last_seen"))
    fit = exclude_collisions(say, "exit", fit, forbid, cal, "the fit trades")
    store, guard = M["store"], BarGuard(fit_eids, frozenset(forbid))
    store.forbid = frozenset(forbid)
    preload_buy_days(store, fit)
    recs, drop = recs_for(fit, M, store, guard)
    say(f"- records: {len(recs)} (dropped {dict(drop)}; the record floor = {REC_MIN_BARS} bars before the buy day)")
    st = preload_sessions(store, recs, -WARMUP_SESSIONS, lambda r: (r.exit_hi_j + TAIL_SESSIONS) if r.exit_hi_j is not None else None)
    say(f"- warm-up + hold + tail sessions preloaded: " + ", ".join(f"{k} {v:,}" for k, v in sorted(st.items())) + "; files read " + ", ".join(f"{k} {v}" for k, v in sorted(store.reads.items())))
    g8_run(say, recs, "exit_fit")
    cc = apply_chain(recs, chosen_level, chosen_stop, mis)
    say("- the chain: " + ", ".join(f"{k} {v}" for k, v in sorted(cc.items())))
    gate_ohlc(say, recs, store, lambda r: range(-WARMUP_SESSIONS, (r.exit_hi_j or 0) + TAIL_SESSIONS + 1), "exit_fit")
    preps = {r.b.eid: exit_prepare(r, M, store) for r in recs}
    ab = Counter(p["abstain"] or "armed" for p in preps.values())
    res_ = [p["residual"] for p in preps.values() if np.isfinite(p["residual"])]
    say(f"- arming (`ema_thin` under {EMA_SEED_BARS} + {EMA_POST_SEED_BARS} = {EMA_SEED_BARS + EMA_POST_SEED_BARS} bars before the armed bar): " + ", ".join(f"{k} {v}" for k, v in sorted(ab.items()))
        + (f"; the seed's residual weight at the first armed bar: median {np.median(res_):.4f}, max {np.max(res_):.4f}" if res_ else ""))
    say(f"- warm-up bars before the buy day: median {np.median([p['seq'].warmup_bars for p in preps.values()]):.0f}; sessions in the range without minutes: {sum(p['seq'].missing_sessions for p in preps.values())}")
    say("\n## THE FIT (§7b): the hit rate of each variant (the LAST leg's booked session inside his sell window; windows <= 20 sessions)")
    rates = hit_rates_for(recs, M, store, preps)
    chosen = choose_exit(rates)
    exit_rate_lines(say, rates, "EMA(20) on the 60-minute bars", chosen)
    rates_sma = hit_rates_for(recs, M, store, preps, avg="sma")
    exit_rate_lines(say, rates_sma, "beside: the 20-bar plain average")
    r2 = hit_rates_for(recs, M, store, preps, variants=("E1",), second_close=True)
    say(f"- beside: E1 on the SECOND 60-minute close below the EMA: last-leg hit {pct(r2['E1'][0])} on {r2['E1'][2]}")
    lst = load_prev_daily_list()
    tl = trivial_and_list_hits(recs, preps, lst)
    say(f"- trivial exits and the previous daily list on the same trades ({tl['n']}): close of session 3 {pct(tl.get('close_of_session_3', float('nan')))}, first red close {pct(tl.get('first_red_close', float('nan')))}, "
        f"the daily list {pct(tl.get('daily_list', float('nan')))}")
    say("\n## THE 2020 ACCOUNTS (in-sample, for scale; the check's bar is on dated 2021-22): ours = the speed trail, chosen = the variant, his = the panel exit, all at cap_30")
    acc = accounts_intra(say, recs, chosen, M, cal, CI[FIT_WIN[0]], store, label="2020 fit, chain fill and stop, ", preps=preps)
    reg = [registered_copy(r) for r in recs]
    preps_reg = {r.b.eid: exit_prepare(r, M, store) for r in reg}
    acc_reg = accounts_intra(say, reg, chosen, M, cal, CI[FIT_WIN[0]], store, label="2020 fit, registered fill and stop, ", preps=preps_reg)
    rows = exit_rows(recs, preps, rates)
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/exit_fit_trades.tsv", sep="\t", index=False)
    ledger_append("exit-fit", f"{OUT_DIR}/exit_fit_trades.tsv")
    pd.DataFrame(bar_rows(recs, preps)).to_csv(f"{OUT_DIR}/exit_fit_bars.tsv.gz", sep="\t", index=False, compression="gzip")
    ledger_append("exit-fit", f"{OUT_DIR}/exit_fit_bars.tsv.gz")
    obj = dict(variant=chosen, rates={v: dict(hit=rates[v][0], half=rates[v][1], n=rates[v][2]) for v in EXIT_VARIANTS}, enter_level=chosen_level, stop=list(chosen_stop) if chosen_stop else None,
               accounts_2020=dict(chain={k: acc[k] for k in ("ours", "chosen", "his", "recovery", "void", "n")}, registered={k: acc_reg[k] for k in ("ours", "chosen", "his", "recovery", "void", "n")}))
    write_chosen("exit", obj, chosen)
    say(f"\nCHOSEN EXIT: {chosen}")
    say("- §7's check runs the three accounts on the dated 2021-22 trades ONCE in --check (recovery >= 0.25 PASS; VOID when his / ours < 1.25; > 10% abstentions INCONCLUSIVE)")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the fit-stage runner, the pins, the check, the WHY rates, main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def run_fit_stage(stage: str, say) -> int:
    exo = stage_outputs(stage)
    if exo:
        print(f"REFUSED: output(s) already on disk: {exo} (each fit writes once; after a STOPPED run the recovery is §12's: the fix in the code, then "
              "--reset-fits \"<reason>\", the dry run and ALL three fits again)", file=sys.stderr)
        return 2
    try:
        check_pinned_inputs(say)
        if not dry_run_complete():
            raise GuardStop("the dry run has not COMPLETED (01_intra_dryrun.txt missing, or its last line is not DRY RUN COMPLETE) — guard (3)")
        if "done_INTRA" not in FILES:
            raise GuardStop("the data gate is open: minutes_intra_1025/_done.psv does not exist (the fetch has not run)")
        ok, why = freeze_state()
        if not ok:
            raise GuardStop("the freeze lock: " + why)
        C = load_core(say)
        assert_populations(say, C)
        rc = {"enter": enter_fit, "stop": stop_fit, "exit": exit_fit}[stage](say, C)
    except GuardStop as g:
        say(f"STOPPED: {g}")
        say.write(STOPPED)
        return 3
    except Exception:
        import traceback
        say("STOPPED (crash):\n" + traceback.format_exc())
        say.write(STOPPED)
        return 4
    say.write(P_FIT[stage])
    ledger_append(f"{stage}-fit", P_FIT[stage])
    return rc


# ═════════════════════════════════════════════════════════════════════════════════════════════
# N2 (DECIDED 2026-10-25): the recovery after a STOP once an earlier fit ran — archive (never delete), re-run everything, disclose
# ═════════════════════════════════════════════════════════════════════════════════════════════
def fit_events_log(root: str = None) -> str:
    return os.path.join(root or FIT_EVENTS, "events.tsv")


def fit_events(root: str = None) -> list:
    """[{event, time, reason, manifest_sha256, files, module_sha}] from the append-only events.tsv (empty when no reset ever ran)."""
    L = fit_events_log(root)
    if not os.path.exists(L):
        return []
    return pd.read_csv(L, sep="\t", dtype=str, keep_default_na=False).to_dict("records")


def fit_event_pins(root: str = None) -> dict:
    """{`fit_event_<event>`: the sha256 of that event's MANIFEST.tsv} — pinned under the marker = the event and its archived printouts
    disclosed there (--check refuses until each is)."""
    out = {}
    for ev in fit_events(root):
        m = os.path.join(root or FIT_EVENTS, ev["event"], "MANIFEST.tsv")
        out[f"fit_event_{ev['event']}"] = sha(m) if os.path.exists(m) else "ABSENT"
    return out


def fit_events_undisclosed(doc: str = None, root: str = None) -> list:
    """The reasons --check refuses on the reset path (N2): an event whose manifest is missing or changed since events.tsv recorded it, or
    whose `fit_event_<event>` pin is not under the marker (its already-seen printouts not disclosed)."""
    bad = []
    for ev in fit_events(root):
        m = os.path.join(root or FIT_EVENTS, ev["event"], "MANIFEST.tsv")
        if not os.path.exists(m):
            bad.append(f"fit event {ev['event']}: MANIFEST.tsv missing")
            continue
        h = sha(m)
        if h != ev["manifest_sha256"]:
            bad.append(f"fit event {ev['event']}: MANIFEST.tsv changed since events.tsv recorded it")
        if pin_under_marker(f"fit_event_{ev['event']}", doc) != h:
            bad.append(f"fit event {ev['event']} ({ev['reason']}) is not disclosed under the marker (paste `- fit_event_{ev['event']}: {h}` and the "
                       "printouts its DISCLOSURE.md lists)")
    return bad


def reset_artifacts() -> list:
    """What --reset-fits archives: every file a fit stage or the check wrote — the fit / check / WHY printouts, the STOPPED file, the ledger, the
    dry run's printout and the pins printout (the procedure re-runs both under the fixed module), the module copies guard (2) made, and every
    file under intraday/ except the dry run's own `dryrun_*` files (freeze_bodies/ is a folder of content-addressed bodies and stays)."""
    out = [p for p in [STOPPED, P_CHECK, P_WHY, LEDGER, P_DRY, P_PINS] + [P_FIT[s] for s in STAGES] if os.path.exists(p)]
    out += sorted(glob.glob(os.path.join(FROZEN_DIR, "01_intra_frozen_*.py")))
    if os.path.isdir(OUT_DIR):
        out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR) if os.path.isfile(os.path.join(OUT_DIR, f)) and not f.startswith("dryrun_"))
    seen, uniq = set(), []
    for p_ in out:
        a = os.path.abspath(p_)
        if a not in seen:
            seen.add(a)
            uniq.append(p_)
    return uniq


def _printout_lines(path: str) -> list:
    """The lines of an archived text printout a disclosure must carry: its CHOSEN line(s) and the line that stopped it."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return [ln.rstrip() for ln in fh if ln.startswith(("CHOSEN ", "STOPPED"))]
    except OSError:
        return []


def reset_fits(say, reason: str, root: str = None) -> int:
    """§12's recovery (N2, DECIDED 2026-10-25), for a fit stage or the check that STOPPED (a gate, the belt, a crash) after an earlier fit ran:
    with the fix made in the code, every artifact (`reset_artifacts`) is COPIED into verify/fit_events/<event>/ (module/ and intraday/), each
    copy's sha256 verified, MANIFEST.tsv and DISCLOSURE.md written and the event appended to events.tsv — and only then are the originals
    removed from their places, so nothing is lost and nothing is deleted. Then, in order: the dry run, ALL three fits on the fresh ledger,
    `--print-pins` (it lists `fit_event_<event>`), the pins and the disclosure pasted under the marker, the check (it refuses an undisclosed
    or altered event). Refused when the check completed (it runs once), when nothing STOPPED (a reset never re-rolls a fit that completed),
    or without a reason."""
    root = root or FIT_EVENTS
    if not (reason or "").strip():
        print("REFUSED: --reset-fits needs the reason (the gate or bug that stopped the run, and the fix)", file=sys.stderr)
        return 2
    if os.path.exists(P_CHECK):
        print(f"REFUSED: the check COMPLETED ({P_CHECK}); it runs once and is never reset", file=sys.stderr)
        return 2
    if not os.path.exists(STOPPED):
        print("REFUSED: no STOPPED file — a reset follows a STOPPED fit stage or check only; it never re-rolls a fit that completed", file=sys.stderr)
        return 2
    arts = reset_artifacts()
    n_prev = len(fit_events(root))
    ev = f"{_dt.datetime.now():%Y%m%dT%H%M%S}_{n_prev + 1:02d}"
    dest = os.path.join(root, ev)
    if os.path.exists(dest):
        print(f"REFUSED: {dest} exists", file=sys.stderr)
        return 2
    rows = []
    for p_ in arts:
        sub = "intraday" if os.path.abspath(os.path.dirname(p_)) == os.path.abspath(OUT_DIR) else "module"
        tgt = os.path.join(dest, sub, os.path.basename(p_))
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        if os.path.exists(tgt):
            print(f"REFUSED: two artifacts archive to the same name {tgt}; nothing was removed from its place", file=sys.stderr)
            return 3
        h = sha(p_)
        shutil.copy2(p_, tgt)
        if sha(tgt) != h:
            print(f"REFUSED: the copy of {p_} does not match its sha256; nothing was removed from its place (the partial copies stay in {dest})", file=sys.stderr)
            return 3
        rows.append(dict(original=os.path.abspath(p_), archived=os.path.relpath(tgt, dest), sha256=h, bytes=os.path.getsize(p_)))
    man = os.path.join(dest, "MANIFEST.tsv")
    pd.DataFrame(rows, columns=["original", "archived", "sha256", "bytes"]).to_csv(man, sep="\t", index=False)
    fz = freeze_record_now()
    disc = [f"# fit event {ev}: a stopped run archived before the re-run (N2) — disclose every printout below under the doc's freeze marker",
            f"- reason: {reason.strip()}", f"- time: {_dt.datetime.now().isoformat(timespec='seconds')}",
            f"- the module at the reset: {fz['intra_module']}; doc_body_freeze under the marker: {fz['doc_body_freeze']}",
            f"- MANIFEST.tsv sha256: {sha(man)} ({len(rows)} files)", "", "## the archived printouts (already seen; what each carried)"]
    for r_ in rows:
        if r_["archived"].startswith("module/") and r_["archived"].endswith(".txt"):
            lines = _printout_lines(os.path.join(dest, r_["archived"]))
            disc.append(f"- {os.path.basename(r_['original'])} ({r_['sha256']}): " + (" | ".join(lines) if lines else "no CHOSEN / STOPPED line"))
    with open(os.path.join(dest, "DISCLOSURE.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(disc) + "\n")
    L = fit_events_log(root)
    new = not os.path.exists(L)
    with open(L, "a") as fh:
        if new:
            fh.write("event\ttime\treason\tmanifest_sha256\tfiles\tmodule_sha\n")
        clean = reason.strip().replace("\t", " ").replace("\n", " ")
        fh.write(f"{ev}\t{_dt.datetime.now().isoformat(timespec='seconds')}\t{clean}\t{sha(man)}\t{len(rows)}\t{fz['intra_module']}\n")
    for r_ in rows:                                                  # every copy verified above: only now leave the original places
        os.remove(r_["original"])
    say(f"# #705 INTRADAY 01 — RESET (N2): fit event {ev}; {len(rows)} files moved to {os.path.relpath(dest, REPO)} (MANIFEST.tsv, DISCLOSURE.md); reason: {reason.strip()}")
    for ln in disc[5:]:
        say(ln)
    say(f"- next, in order: --dry-run (DRY RUN COMPLETE), --enter-fit, --stop-fit, --exit-fit on the fresh ledger, --print-pins; paste every pin incl. "
        f"`- fit_event_{ev}: {sha(man)}` and the disclosure under the marker; then --check")
    return 0


def print_pins(say) -> int:
    say("# #705 INTRADAY 01 — pins (sha256): paste every line under the doc's freeze marker line (doc_body_freeze at the freeze; the rest after the three fit stages and the keyed CHOSEN lines)")
    p = pins()
    for k, v in p.items():
        say(f"- {k}: {v}")
    miss = freeze_missing(DOC, p)
    say(f"- freeze record: {'complete' if not miss else 'NOT YET under the marker: ' + str(len(miss)) + ' of ' + str(len(p)) + ' pins'}")
    absent = [k for k, v in p.items() if v == "ABSENT"]
    say(f"- absent inputs / outputs (named, not refused): {', '.join(absent) if absent else 'none'}")
    ch = chosen_lines()
    say("- CHOSEN lines above the marker (column 0, keyed): " + (", ".join(f"{k.upper()} x{len(v)}" for k, v in sorted(ch.items())) if ch else "none"))
    try:
        h = store_freeze_body()
        say(f"- the body above the marker stored under freeze_bodies/ ({h[:12]}...); doc_body_freeze above = {'the pinned value under the marker' if pin_under_marker('doc_body_freeze') else 'the CURRENT body (paste it: this is the freeze)'}")
    except GuardStop as g:
        say(f"- freeze body not stored: {g}")
    say.write(P_PINS)
    return 0


def run_check(say) -> int:
    exo = stage_outputs("check")
    if exo:
        print(f"REFUSED: {exo} exist (the check runs once)", file=sys.stderr)
        return 2
    for s in STAGES:
        if not os.path.exists(P_FIT[s]) or not os.path.exists(chosen_path(s)):
            print(f"REFUSED: the {s.upper()} fit printout or its chosen file is missing", file=sys.stderr)
            return 2
    ch = chosen_lines()
    for s in STAGES:
        if len(ch.get(s, [])) != 1:
            print(f"REFUSED: exactly one `CHOSEN {s.upper()}: ` line at column 0 must stand above the marker (found {len(ch.get(s, []))})", file=sys.stderr)
            return 2
        fit_text = read_chosen(s)["text"]
        if ch[s][0] != fit_text:
            print(f"REFUSED: the doc's CHOSEN {s.upper()} ({ch[s][0]!r}) differs from the fit printout's ({fit_text!r})", file=sys.stderr)
            return 2
    ok, why = freeze_state()
    if not ok:
        print("REFUSED: the freeze lock: " + why, file=sys.stderr)
        return 2
    p = pins()
    miss = freeze_missing(DOC, p)
    if miss:
        print("REFUSED: pins not under the marker: " + ", ".join(miss), file=sys.stderr)
        return 2
    bad = ledger_verify()
    if bad:
        print("REFUSED: the ledger does not match the files on disk: " + "; ".join(bad), file=sys.stderr)
        return 2
    bad = fit_events_undisclosed()
    if bad:
        print("REFUSED: a reset's archived run is not disclosed (N2): " + "; ".join(bad), file=sys.stderr)
        return 2
    bad = freeze_records_agree()
    if bad or p.get("intra_module") != module_sha():
        print("REFUSED: the fits did not run under this freeze body / module (C5): " + "; ".join(bad or ["the intra_module pin is not this file"]), file=sys.stderr)
        return 2
    frozen_copy = os.path.join(FROZEN_DIR, f"01_intra_frozen_{sha(os.path.abspath(__file__))[:12]}.py")
    shutil.copyfile(os.path.abspath(__file__), frozen_copy)          # guard (2): the module beside the pins before any post-check edit
    say("# #705 INTRADAY 01 — CHECK (ONE run): ENTER (2021-22 undated non-flicker; the virgin 9 veto) -> STOP (the 62 undated untouched) -> EXIT (dated 2021-22; the virgin dated veto), each ONCE; the sealed test's branch; WHY-lite's sheet")
    say(f"# registration: {os.path.relpath(DOC, REPO)}; module copied to {os.path.basename(frozen_copy)}")
    say(f"- freeze: every pin incl. doc_body {p['doc_body'][:12]}... sits under the marker; the body differs from the freeze commit's ({p['doc_body_freeze'][:12]}...) only in the three keyed lines; "
        f"CHOSEN lines match the fit printouts; the ledger matches the disk; all three fits ran under this freeze body and this module ({module_sha()[:12]}...)")
    try:
        check_pinned_inputs(say)
        C = load_core(say)
        assert_populations(say, C)
        rc = check_stages(say, C)
    except GuardStop as g:
        say(f"STOPPED: {g}")
        say.write(STOPPED)
        return 3
    except Exception:
        import traceback
        say("STOPPED (crash):\n" + traceback.format_exc())
        say.write(STOPPED)
        return 4
    say.write(P_CHECK)
    ledger_append("check", P_CHECK)
    return rc


def check_stages(say, C: dict, M: "dict | None" = None, with_why: bool = True) -> int:
    S, I, E, mis, cal, CI = C["S"], C["I"], C["E"], C["mis"], C["cal"], C["CI"]
    ent, stp, xit = (read_chosen(s)["object"] for s in STAGES)
    verdicts, notes = {}, {}
    all_buys = I["chk22_dated"] + I["chk22_und"] + I["virgin_all"] + E["pre_dated_chk"] + E["pre_und_chk"] + E["prefirst_chk"] + E["held_0935"]
    if M is None:
        a, b_ = names_of(all_buys)
        M = load_for_stage(say, C, a, b_)
    store, sight, guard = M["store"], M["sight"], BarGuard(None)
    store.forbid = frozenset()                                   # the check reads every forward bar: guard (5) per ticker-date is a FIT-stage rule
    preload_buy_days(store, all_buys)
    # ---------------- ENTER
    say("\n## ENTER CHECK (§5d): the CHOSEN level on the 2021-22 undated non-flicker windows after §2c (deciding); the virgin 9 veto by sign; dated / flickers / L1-L6 / the union beside")
    chosen_level = ent["level"]
    # the random-price draws are the previous read's IDENTICAL draws: the same population (its `ent_chk_dated` 20 incl. 7 dated flickers + `ent_chk_und`
    # 44 incl. DWAC), scored in the same (E, eid) order over the records with minutes; DWAC and the dated flickers are scored, never deciding (C6)
    draw_pop = sorted(S["ent_chk_dated"] + S["ent_chk_und"], key=lambda b: (b.E, b.eid))
    prev_und_eids = {b.eid for b in S["ent_chk_und"]}
    recs_e, drop = recs_for(draw_pop, M, store, guard, min_bars=REC_MIN_BARS_ENTER)
    gate_ohlc(say, [r for r in recs_e if r.mb is not None], store, lambda r: [0], "check_enter")
    rng = rng_for(RANDOM_KEY)
    scored_all, rows = {}, []
    for r in sorted(recs_e, key=lambda x: (x.b.E, x.b.eid)):
        if r.mb is None:
            rows.append(dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, minutes=r.minutes_state, scorable=False))
            continue
        res = enter_score_trade(r, rng)
        scored_all[r.b.eid] = res
        rows.append(dict(enter_row(r, res), sane=clock_sane(r.b, mis)))
    gate_level_order(say, [rw for rw in rows if rw.get("scorable")], "check_enter")
    gate_vii_random_control(say, scored_all, prev_und_eids)
    dec_eids = {b.eid for b in E["chk22_und"]}
    dated_eids = {b.eid for b in E["chk22_dated"]}
    deciding = {k: v for k, v in scored_all.items() if k in dec_eids}
    beside_d = {k: v for k, v in scored_all.items() if k in dated_eids}
    say(f"- records {len(recs_e)} of {len(draw_pop)} windows (the previous read's draw population: {sum(1 for b in draw_pop if b.dated)} dated incl. {sum(1 for b in draw_pop if b.dated and b.flicker)} flickers + "
        f"{sum(1 for b in draw_pop if not b.dated)} undated non-flicker incl. DWAC; dropped {dict(drop)}; the ENTER record floor = {REC_MIN_BARS_ENTER} bars); scorable {len(scored_all)}; DECIDING {len(deciding)} "
        f"(the {len(E['chk22_und'])} undated non-flicker windows after §2c; the random draws replayed in the same (E, eid) order)")
    summ = enter_summary(deciding)
    enter_level_lines(say, summ, "DECIDING: 2021-22 undated non-flicker", chosen_level)
    ev, reasons = enter_verdict(summ, chosen_level) if summ["n"] else ("INCONCLUSIVE-by-size", ["no scorable trade"])
    if beside_d:
        enter_level_lines(say, enter_summary(beside_d), f"beside: the {len(beside_d)} dated 2021-22 windows (max(level, pivot) on breakout rows; flickers included)")
    rr_fl, _d = recs_for(E["chk22_fl"], M, store, guard, min_bars=REC_MIN_BARS_ENTER)
    sc_fl = {r.b.eid: enter_score_trade(r, rng) for r in sorted(rr_fl, key=lambda x: (x.b.E, x.b.eid)) if r.mb is not None}
    if sc_fl:
        enter_level_lines(say, enter_summary(sc_fl), "beside: 2021-22 flickers")
        rows += [dict(enter_row(r, sc_fl[r.b.eid]), beside="flickers") for r in rr_fl if r.b.eid in sc_fl]
    rr_v, _d = recs_for(E["virgin"], M, store, guard, min_bars=REC_MIN_BARS_ENTER)
    sc_v = {r.b.eid: enter_score_trade(r, rng) for r in sorted(rr_v, key=lambda x: (x.b.flicker, x.b.E, x.b.eid)) if r.mb is not None}
    sc_vnf = {k: v for k, v in sc_v.items() if not next(r for r in rr_v if r.b.eid == k).b.flicker}
    sc_vfl = {k: v for k, v in sc_v.items() if next(r for r in rr_v if r.b.eid == k).b.flicker}
    summ_v = enter_summary(sc_vnf)
    enter_level_lines(say, summ_v, "the untouched years, non-flicker (the sign veto)")
    if sc_vfl:
        enter_level_lines(say, enter_summary(sc_vfl), "beside: the untouched years, flickers")
    rows += [dict(enter_row(r, sc_v[r.b.eid]), beside="virgin") for r in rr_v if r.b.eid in sc_v]
    veto, vtext = enter_veto(summ_v, chosen_level) if summ_v["n"] else (False, "abstains (no scorable untouched window)")
    say(f"- the sign veto: {vtext}")
    ev, vreason = apply_sign_veto(ev, veto, "2021-22")
    if vreason:
        reasons = [vreason]
    verdicts["enter"] = ev
    say(f"- ENTER: **{ev}** " + ("; ".join(reasons) if reasons else f"{chosen_level} feasible {pct(summ[chosen_level]['feasible_share'][0])} >= 50%, >= both controls + 15, hit-or-ballpark >= 70%"))
    for lab, bs in (("pre-market-flat windows, dated 2021-22", E["pre_dated_chk"]), ("pre-market-flat windows, undated 2021-22", E["pre_und_chk"])):
        rr, _d = recs_for(bs, M, store, guard, min_bars=REC_MIN_BARS_ENTER)
        rr = [r for r in rr if r.mb is not None and hhmm_to_min(r.b.first_clock) is not None and hhmm_to_min(r.b.flat_clock) is not None]
        sc = {r.b.eid: enter_score_trade(r, rng) for r in sorted(rr, key=lambda x: (x.b.E, x.b.eid))}
        if sc:
            enter_level_lines(say, enter_summary(sc), "beside: " + lab)
    held_lines(say, E["held_0935"], M, store, guard)
    crossed_lines(say, "beside: pre-market first sightings, dated 2021-22 (crossed that session)", E["prefirst_chk"], M, store, guard)
    chain_level = chain_after(ev, chosen_level)
    say(f"- the chain carries: {'the chosen level ' + chosen_level if chain_level else 'the REGISTERED fill (words-based: ORH5 / the open)'}")
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/check_enter_trades.tsv", sep="\t", index=False)
    ledger_append("check", f"{OUT_DIR}/check_enter_trades.tsv")
    # ---------------- STOP
    say("\n## STOP CHECK (§6b): the 62 undated untouched trades decide on every cell; the 27 untouched dated, the 2021-22 undated (226) and dated (111) beside")
    chosen_stop = (stp["level"], stp["variant"]) if stp["level"] else None
    recs_vu, d1 = recs_for(I["virgin_und"], M, store, guard)
    recs_vd, d2 = recs_for(I["virgin_dated"], M, store, guard)
    recs_22u, d3 = recs_for(I["chk22_und"], M, store, guard)
    recs_22d, d4 = recs_for(I["chk22_dated"], M, store, guard)
    allr = recs_vu + recs_vd + recs_22u + recs_22d
    say(f"- records: virgin undated {len(recs_vu)} of {len(I['virgin_und'])} (dropped {dict(d1)}); virgin dated {len(recs_vd)} (dropped {dict(d2)}); 2021-22 undated {len(recs_22u)} (dropped {dict(d3)}); "
        f"2021-22 dated {len(recs_22d)} (dropped {dict(d4)})")
    st = preload_sessions(store, allr, 1, lambda r: r.exit_hi_j if r.exit_hi_j is not None else r.last_j)
    say(f"- hold sessions preloaded: " + ", ".join(f"{k} {v:,}" for k, v in sorted(st.items())))
    cc = apply_chain(allr, chain_level, None, mis)
    say("- fills: " + ", ".join(f"{k} {v}" for k, v in sorted(cc.items())))
    g8_run(say, allr, "check")
    gate_ohlc(say, allr, store, lambda r: range(0, (r.exit_hi_j if r.exit_hi_j is not None else (r.last_j or 0)) + 1), "check_stop")
    gate_c_implies_h(say, allr, store, "check_stop")
    tab_dec = stop_table_intra(recs_vu, sight, store)
    tab_vd = stop_table_intra(recs_vd, sight, store)
    tab_22u = stop_table_intra(recs_22u, sight, store)
    tab_22u_nf = stop_table_intra([r for r in recs_22u if not r.b.flicker], sight, store)
    tab_22u_un = stop_table_intra([r for r in recs_22u if not r.b.in_dated_path], sight, store)
    tab_22d = stop_table_intra(recs_22d, sight, store)
    fit_table = {tuple(k.split("-")): v for k, v in stp["fit_table"].items()}
    stop_table_lines(say, tab_dec, {"fit H_cond": fit_table, "virgin dated 27": tab_vd, "2021-22 undated 226": tab_22u, "nf": tab_22u_nf, "untouched-by-path": tab_22u_un, "2021-22 dated 111": tab_22d},
                     label="- the deciding table (the 62 undated untouched trades), the fit and the beside sets:")
    sv, sreasons = stop_verdict(tab_dec, chosen_stop)
    rho, used = spearman_cells(fit_table, tab_dec, recs_vu)
    say(f"- beside: the cells' ordering by H_cond, fit vs the deciding set (cells equal to S1 on more than half their records left out): Spearman {rho:.2f} on {len(used)} cells")
    verdicts["stop"] = sv
    say(f"- STOP: **{sv}** " + "; ".join(sreasons))
    rb = [r for r in recs_vu if r.b.rebuy]
    if rb:
        tr = stop_table_intra(rb, sight, store)
        say(f"- re-buys among the deciding ({len(rb)}) apart: " + "; ".join(f"{L}-{V} H_cond {pct(tr[(L, V)]['H_cond'])}" for L in STOP_LEVELS for V in STOP_VARIANTS))
    chain_stop = chain_after(sv, chosen_stop)
    apply_chain(allr, chain_level, chain_stop, mis)
    say(f"- the chain carries: {'the chosen stop ' + '-'.join(chosen_stop) if chain_stop else 'the REGISTERED stop (words-based: S1-T dated / one ADR20 undated)'}")
    if chosen_stop and chosen_stop[1] == "H":
        say("- the chosen stop is an H cell: its realised R tail on the deciding set (nothing resized):")
        risk_block(say, recs_vu, cal, CI[min(b.E for b in I['virgin_und'])] if I["virgin_und"] else 0, M["map_b"], store, "the deciding set under every cell")
    pd.DataFrame(stop_rows(allr, sight, store)).to_csv(f"{OUT_DIR}/check_stop_trades.tsv", sep="\t", index=False)
    ledger_append("check", f"{OUT_DIR}/check_stop_trades.tsv")
    # ---------------- EXIT
    say("\n## EXIT CHECK (§7d): the CHOSEN variant on the dated 2021-22 trades (deciding); the untouched dated veto by sign; the undated 2021-22 beside")
    chosen_variant = xit["variant"]
    dec = [r for r in recs_22d if r.exit_hi_j is not None]
    st = preload_sessions(store, dec + [r for r in recs_vd if r.exit_hi_j is not None] + [r for r in recs_22u if r.exit_hi_j is not None], -WARMUP_SESSIONS,
                          lambda r: r.exit_hi_j + TAIL_SESSIONS)
    say(f"- warm-up + hold + tail sessions preloaded: " + ", ".join(f"{k} {v:,}" for k, v in sorted(st.items())))
    gate_ohlc(say, dec, store, lambda r: range(-WARMUP_SESSIONS, r.exit_hi_j + TAIL_SESSIONS + 1), "check_exit")
    gate_v_accounts(say, recs_22d, M, cal, store)
    preps = {r.b.eid: exit_prepare(r, M, store) for r in dec}
    ab = Counter(p["abstain"] or "armed" for p in preps.values())
    say(f"- arming on dated 2021-22: " + ", ".join(f"{k} {v}" for k, v in sorted(ab.items())))
    rates = hit_rates_for(dec, M, store, preps)
    exit_rate_lines(say, rates, "dated 2021-22, EMA(20) on the 60-minute bars (the half-leg hit rate is the out-of-sample part)", chosen_variant)
    lst = load_prev_daily_list()
    tl = trivial_and_list_hits(dec, preps, lst)
    say(f"- trivial exits and the previous daily list on the same trades ({tl['n']}): close of session 3 {pct(tl.get('close_of_session_3', float('nan')))}, first red close {pct(tl.get('first_red_close', float('nan')))}, "
        f"the daily list (IN-SAMPLE there) {pct(tl.get('daily_list', float('nan')))}")
    w0 = CI[CHECK_WIN[0]]
    acc_chain = accounts_intra(say, dec, chosen_variant, M, cal, w0, store, label="dated 2021-22, chain fill and stop, ", preps=preps, bootstrap=True)
    reg = [registered_copy(r) for r in dec]
    preps_reg = {r.b.eid: exit_prepare(r, M, store) for r in reg}
    acc_reg = accounts_intra(say, reg, chosen_variant, M, cal, w0, store, label="dated 2021-22, registered fill and stop, ", preps=preps_reg, bootstrap=True)
    deciding_line = deciding_line_for(verdicts)
    acc = acc_chain if deciding_line == "chain" else acc_reg
    say(f"- the deciding line = the {deciding_line} fill and stop ({'ENTER or STOP passed' if deciding_line == 'chain' else 'neither ENTER nor STOP passed'})")
    xv, xreason = exit_verdict(acc)
    # the sign veto on the untouched dated trades with exits
    vd = [r for r in recs_vd if r.exit_hi_j is not None]
    if vd:
        preps_v = {r.b.eid: exit_prepare(r, M, store) for r in vd}
        if deciding_line == "registered":
            vd = [registered_copy(r) for r in vd]
            preps_v = {r.b.eid: exit_prepare(r, M, store) for r in vd}
        w0v = CI[min(r.b.E for r in vd)]
        acc_v = accounts_intra(say, vd, chosen_variant, M, cal, w0v, store, label="the untouched dated trades (the sign veto), ", preps=preps_v)
        fires, vtext = exit_veto(acc_v)
        rates_v = hit_rates_for(vd, M, store, preps_v)
        exit_rate_lines(say, rates_v, "the untouched dated trades (windows <= 20 sessions)")
    else:
        fires, vtext = False, "abstains (no untouched dated trade with an exit)"
    say(f"- the sign veto: {vtext}")
    xv, vreason = apply_sign_veto(xv, fires, "dated 2021-22")
    xreason = vreason or xreason
    verdicts["exit"] = xv
    say(f"- EXIT: **{xv}** ({xreason}; his / ours {acc['his'] / acc['ours'] if acc['ours'] > 0 else float('nan'):.2f}; the hit rate says whether the rule at least SEES his sell day: {pct(rates[chosen_variant][0])})")
    # beside: the undated 2021-22
    und = [r for r in recs_22u if r.exit_hi_j is not None]
    if und:
        preps_u = {r.b.eid: exit_prepare(r, M, store) for r in und}
        rates_u = hit_rates_for(und, M, store, preps_u)
        exit_rate_lines(say, rates_u, "beside: undated 2021-22")
        tlu = trivial_and_list_hits(und, preps_u, lst)
        say(f"- beside: undated 2021-22 trivial exits and the daily list ({tlu['n']}): close of session 3 {pct(tlu.get('close_of_session_3', float('nan')))}, first red close {pct(tlu.get('first_red_close', float('nan')))}, "
            f"the daily list {pct(tlu.get('daily_list', float('nan')))} (the previous read: 37.7%)")
        accounts_intra(say, und, chosen_variant, M, cal, w0, store, label="beside: undated 2021-22, chain fill and stop, ", preps=preps_u)
    pd.DataFrame(exit_rows(dec, preps, rates)).to_csv(f"{OUT_DIR}/check_exit_trades.tsv", sep="\t", index=False)
    ledger_append("check", f"{OUT_DIR}/check_exit_trades.tsv")
    pd.DataFrame(bar_rows(dec, preps)).to_csv(f"{OUT_DIR}/check_exit_bars.tsv.gz", sep="\t", index=False, compression="gzip")
    ledger_append("check", f"{OUT_DIR}/check_exit_bars.tsv.gz")
    # ---------------- the sealed test's branch
    say("\n## THE SEALED TEST'S BRANCH (stated, not run here; research only, no rule moves)")
    say(f"- universe = SELECT's PASSED condition set (the previous read); ENTER {verdicts['enter']} -> {'inferred ' + chosen_level if verdicts['enter'] == 'PASS' else 'words-based (ORH5 / the open)'}; "
        f"STOP {verdicts['stop']} -> {'inferred ' + '-'.join(chosen_stop) if (verdicts['stop'] == 'PASS' and chosen_stop) else 'words-based (the low of the day at the fill / one ADR20)'}; "
        f"EXIT {verdicts['exit']} -> {'the inferred FSLY variant ' + chosen_variant if verdicts['exit'] == 'PASS' else 'words-based (the speed trail)'}")
    # ---------------- WHY-lite's sheet
    if with_why:
        say("\n## WHY-lite (§8): the 10-row 2020 hand-read sheet (seed 1025) -> fill `verdict` (yes / no) by hand, then --why-rates")
        texts = rev.load_caption_texts(sorted(glob.glob(SUBS_GLOB)))
        J = why_joins(texts, C)
        rows = why_sheet_rows(J["joins"], texts)
        pd.DataFrame(rows).to_csv(WHY_SHEET, sep="\t", index=False)
        ledger_append("check", WHY_SHEET)
        say(f"- {len(rows)} joins written to {WHY_SHEET} (unambiguous 2020 joins available {sum(1 for j in J['joins'] if not j['ambiguous'] and j['upload'].startswith('2020'))})")
    with open(f"{OUT_DIR}/check_verdicts.json", "w") as fh:
        json.dump(verdicts, fh, indent=1)
    ledger_append("check", f"{OUT_DIR}/check_verdicts.json")
    say("\nCHECK COMPLETE: " + ", ".join(f"{k.upper()} {v}" for k, v in verdicts.items()))
    return 0


def run_why_rates(say) -> int:
    if os.path.exists(P_WHY) or os.path.exists(STOPPED):
        print("REFUSED: the WHY printout or a STOPPED file exists", file=sys.stderr)
        return 2
    if not os.path.exists(WHY_SHEET):
        print("REFUSED: the hand-read sheet does not exist (run --check first)", file=sys.stderr)
        return 2
    say("# #705 INTRADAY 01 — WHY-lite rates: the hand-read precision gate, then the share of his 60-minute-EMA sells whose exit session carries a 60-minute close below the 20-EMA")
    sheet = pd.read_csv(WHY_SHEET, sep="\t", dtype=str, keep_default_na=False)
    prec, yes, no = why_precision(sheet)
    say(f"- hand read: yes {yes}, no {no}, blank {len(sheet) - yes - no}; precision {pct(prec)} (gate {pct(WHY_PRECISION)})")
    if not (yes + no) == len(sheet):
        say("STOPPED: the sheet's `verdict` column is not fully filled (yes / no)")
        say.write(P_WHY)
        return 3
    if prec < WHY_PRECISION:
        say("- precision below the gate: the joins are listed, no rate is quoted")
        for r in sheet.to_dict("records"):
            say(f"  {r['video']} t {r['t']} {r['tickers']} eids {r['eids']} -> {r['verdict']}")
        say("WHY RATES COMPLETE (no rate)")
        say.write(P_WHY)
        return 0
    try:
        C = load_core(say)
        byeid = {b.eid: b for b in C["buys"]}
        eids = sorted({int(x) for r in sheet.to_dict("records") if r["verdict"].strip().lower() == "yes" for x in r["eids"].split(";") if x})
        buys = [byeid[e] for e in eids if e in byeid]
        a, b_ = names_of(buys)
        M = load_for_stage(say, C, a, b_)
        store = M["store"]
        preload_buy_days(store, buys)
        recs, drop = recs_for(buys, M, store, BarGuard(None))
        preload_sessions(store, recs, -WARMUP_SESSIONS, lambda r: r.exit_hi_j)
        n, hit = 0, 0
        for r in recs:
            if r.exit_hi_j is None:
                continue
            seq = bar_sequence(r, store, -WARMUP_SESSIONS, r.exit_hi_j)
            below = any(np.isfinite(seq.ema[i]) and x.c < seq.ema[i] for i, (j, x) in enumerate(seq.items) if r.exit_lo_j <= j <= r.exit_hi_j)
            n += 1; hit += int(below)
            say(f"  {r.b.sym} {r.b.E} exit {r.b.exit_lo}..{r.b.exit_hi}: a 60-minute close below the 20-EMA inside the exit window: {below}")
        say(f"- the share of his 60-minute-EMA sells whose exit session carries a 60-minute close below the 20-EMA: {hit} of {n} = {pct(hit / n if n else float('nan'))} (decides nothing)")
    except GuardStop as g:
        say(f"STOPPED: {g}")
        say.write(P_WHY)
        return 3
    say("WHY RATES COMPLETE")
    say.write(P_WHY)
    ledger_append("why", P_WHY)
    return 0


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap_.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--enter-fit", action="store_true")
    g.add_argument("--stop-fit", action="store_true")
    g.add_argument("--exit-fit", action="store_true")
    g.add_argument("--print-pins", "--pins", action="store_true", dest="print_pins")
    g.add_argument("--check", action="store_true")
    g.add_argument("--why-rates", action="store_true")
    g.add_argument("--reset-fits", metavar="REASON", default=None, help="N2: archive a STOPPED run's artifacts to verify/fit_events/ (never deletes)")
    args = ap_.parse_args(argv)
    say = rp.Say()
    if args.dry_run:
        exo = any_stage_output()
        if exo:
            print(f"REFUSED: stage output(s) already on disk: {exo[:6]}{' ...' if len(exo) > 6 else ''} (the dry run precedes the stages)", file=sys.stderr)
            return 2
        try:
            rc = dry_run(say)
        except GuardStop as gs:
            say(f"STOPPED: {gs}")
            rc = 3
        say.write(P_DRY)
        return rc
    if args.print_pins:
        return print_pins(say)
    if args.reset_fits is not None:
        return reset_fits(say, args.reset_fits)
    for flag, stage in (("enter_fit", "enter"), ("stop_fit", "stop"), ("exit_fit", "exit")):
        if getattr(args, flag):
            return run_fit_stage(stage, say)
    if args.check:
        return run_check(say)
    if args.why_rates:
        return run_why_rates(say)
    return 1


if __name__ == "__main__":
    sys.exit(main())
