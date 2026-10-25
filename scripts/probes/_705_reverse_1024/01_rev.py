#!/usr/bin/env python3
"""#705 — REVERSE 01: his rules inferred from his panel trades (docs/analysis/cb_reverse_engineer_his_rules_prereg_2026-10-24.md).
REGISTERED, NOT FROZEN, NOT RUN. The module is built to execution depth; every fit stage writes ONCE; the check runs ONCE after the freeze.

The frozen holdings replay (`scripts/probes/_705_holdings_1024/02_replay.py`, sha pinned below, refused on drift) is IMPORTED read-only,
and through it the frozen second and first reads, the runner and the cb module. Nothing in them is edited. This module reuses its
loaders (`load_events`, `mark_same_day_rebuys`, `unify_calendars`, `stitched_closes`, `held_names_by_day`), the first replay's
`load_daily_subset` / `load_done` / `simulate` / `Trade`, the second read's line-anchored freeze lock, `cb.walk_arms` (the speed trail)
and `cb.day0_walk`. The exits-study module is NOT imported (its pinned file is not on disk — its freeze note) and nothing is copied from it.
`security_type_check.resolve_type` (the data standard's type rule) and `qmlib.parse_vtt` (the caption parser) are imported read-only.

STAGES (the registration's §13; the time split: 2020 buys fit, 2021-01-04..2022-06-14 buys check)
  --dry-run       loads every input; asserts every composition count of §2 / §2b against the doc (every mismatch printed, then STOP);
                  derives the panel clock for EVERY row and writes both clock columns; prints the caption chain from the pinned
                  alternation; prints the data gate (minute coverage on the four pinned trees = the doc's pre-fetch numbers, then with
                  the new tree; the pending fetch list); prints the pins. Computes NO outcome: no bar after a buy day, no stop, exit,
                  R or return, no fit. (The holdings `event_facts`, which counted the sessions AFTER the buy day, is no longer called:
                  the walkability tally comes from `ex.history_reason`, which reads calendar indices up to the buy day only.)
  --select-fit    §5b on the 2020 exact-day no-event buys vs the same-day pool (incl. the 20 planted-name runs, §3); §5c placement of
                  the 2-10-session windows; §5d's rank fit. Writes once; prints `CHOSEN SELECT: ...`.
  --enter-fit     §6 on the 2020 in-session brackets; the random-level control. Writes once; prints `CHOSEN ENTER: ...`.
  --stop-fit      §7 held-through on dated 2020 + undated 2020; §7c risk. Writes once; prints `CHOSEN STOP: ...`.
  --exit-fit      §8 both families on the EXIT fit set, the held-out family choice, the refit. Writes once; prints `CHOSEN EXIT: ...`.
  --print-pins    (also --pins) the pins to paste under the doc's freeze marker line; prints unconditionally (absent fit printouts are
                  named, not refused).
  --check         every stage's check ONCE (refuses unless every pin sits under the marker, exactly one keyed CHOSEN line per stage
                  stands above it and equals the fit printout's, every fit printout exists, the check printout does not, every ledger
                  row matches the file on disk; copies the module beside the pins first); then WHY's 20-row 2020 hand-read sheet.
  --why-rates     after the hand read is filed in the sheet (`verdict` column): the precision gate and the per-class rates.

No subagent, no DB, no network, no ssh, no docker. Read-only on every input. Nothing dated after 2024-12-31 is kept from any era-B file
(the holdings loader's cut); nothing of 2025-26 is opened. Guard (9), stricter reading: `replay/trades.tsv.gz` and `his_exits/*` are
opened by NO stage for ANY name (asserted: no path under those folders is in FILES).
Run:  python3 scripts/probes/_705_reverse_1024/01_rev.py --dry-run
"""
from __future__ import annotations

import argparse
import bisect
import collections
import datetime as _dt
import glob
import gzip
import hashlib
import importlib.util
import json
import math
import os
import pickle
import re
import shutil
import subprocess
import sys
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
H_PATH = os.path.join(REPO, "scripts", "probes", "_705_holdings_1024", "02_replay.py")
H_TESTS = os.path.join(REPO, "scripts", "probes", "_705_holdings_1024", "test_02_replay.py")
H_SHA = "4275d72f82aaf66c7c24372afe48e0b503dedb51e2c7715d8fbd26c4372e9ce9"        # the holdings replay's freeze record (holdings_module)
H_TESTS_SHA = "eee66bf08ef8f70c5da66b4aeec0f626f592ca327dcfc7c6c0c6fd1943a0b75f"  # holdings_tests
SEC_PATH = os.path.join(REPO, "scripts", "backtest_data_audit", "security_type_check.py")
QMLIB_DIR = os.path.join(REPO, "scripts", "probes", "_qm_streams")


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


def _load_holdings():
    got = sha(H_PATH)
    if got != H_SHA:
        raise SystemExit(f"REFUSED: the holdings replay module is not the frozen one ({got} vs {H_SHA})")
    return _load_module("_705_holdings02_frozen_rev", H_PATH)


H = _load_holdings()
ex, rp, R, cb = H.ex, H.rp, H.R, H.cb
SEC = _load_module("_705_sec_type_rev", SEC_PATH)          # resolve_type / load_small / load_sic, read-only
if QMLIB_DIR not in sys.path:
    sys.path.insert(0, QMLIB_DIR)
import qmlib  # noqa: E402  (the caption parser, read-only)

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths, pins
# ═════════════════════════════════════════════════════════════════════════════════════════════
DATA = rp.DATA
A_DIR, B_DIR = rp.A_DIR, rp.B_DIR
QS = f"{B_DIR}/qm_streams"
H_DIR = H.H_DIR
OUT_DIR = f"{H_DIR}/reverse"
REV_MIN = f"{B_DIR}/minutes_rev_1024"
DOC = os.path.join(REPO, "docs", "analysis", "cb_reverse_engineer_his_rules_prereg_2026-10-24.md")
STAGES = ("select", "enter", "stop", "exit")
P_DRY = os.path.join(HERE, "01_rev_dryrun.txt")
P_PINS = os.path.join(HERE, "01_rev_pins.txt")
P_FIT = {s: os.path.join(HERE, f"01_rev_{s}_fit.txt") for s in STAGES}
P_CHECK = os.path.join(HERE, "01_rev_check.txt")
P_WHY = os.path.join(HERE, "01_rev_why.txt")
LEDGER = os.path.join(HERE, "01_rev_ledger.tsv")
STOPPED = os.path.join(HERE, "01_rev.STOPPED.txt")
WHY_SHEET = f"{OUT_DIR}/why_sheet_2020.tsv"
FETCH_LIST = f"{REV_MIN}/fetch_list.psv"
FETCH_LIST_SHA = "4191485f2abddc25c042132729742491c191dfbe85d0dc2099fa023d34e3770f"      # the doc's §12 pin
FORBIDDEN_DIRS = (f"{H_DIR}/replay", f"{H_DIR}/his_exits")   # guard (9): never opened, by any stage, for any name

FILES = {**H.FILES,
         "small_pulls": f"{B_DIR}/small_pulls.psv", "sic": f"{B_DIR}/cb702_sic.psv",
         "raw_close_A": f"{A_DIR}/daily_raw_close.csv.gz",
         "stream_moments": f"{QS}/stream_moments.tsv", "video_status": f"{QS}/video_status.tsv",
         "fetch_list": FETCH_LIST}
if os.path.exists(f"{REV_MIN}/_done.psv"):
    FILES["done_REV"] = f"{REV_MIN}/_done.psv"
SUBS_GLOB = f"{QS}/subs/*.vtt"
CODE = {**H.CODE,
        "qmlib": os.path.join(QMLIB_DIR, "qmlib.py"), "security_type_check": SEC_PATH,
        "rev_module": os.path.abspath(__file__), "rev_tests": os.path.join(HERE, "test_01_rev.py")}
MINUTES = {**H.MINUTES}
if "done_REV" in FILES:
    MINUTES["REV"] = REV_MIN
PINNED = {**H.PINNED, "holdings_module": H_SHA, "holdings_tests": H_TESTS_SHA, "fetch_list": FETCH_LIST_SHA}
for _p in list(FILES.values()):
    assert not any(_p.startswith(d + "/") or _p == d for d in FORBIDDEN_DIRS), _p   # guard (9)

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants (every number is the doc's)
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = rp.CUT_B                                  # 2024-12-31: nothing after it is kept from any era-B file
A_LAST = "2022-03-31"                             # era by buy day (R10): <= A, >= 2022-04-01 B
B_FIRST = "2022-04-01"
A_EXPORT_LAST = "2022-06-30"                      # SELECT's pool: era A through its export end (§3); the pick's features on the same export
DENSE = ("2020-01-27", "2022-06-14")
FIT_WIN = ("2020-01-27", "2020-12-31")
CHECK_WIN = ("2021-01-04", "2022-06-14")
HOLDOUT = ("2020-07-01", "2020-12-31")            # §8b: the family choice's held-out buys
WINDOW_CAP = 10
HORIZON = H.HORIZON                               # 120
CAP30 = H.CAP30
SPEED_ARM = H.SPEED_ARM
ARMS = {SPEED_ARM: H.ARMS[SPEED_ARM]}
EXIT_SLIPS = rp.EXIT_SLIPS
ORDER_OPEN, ORDER_BUY, ORDER_INTRADAY, ORDER_CLOSE = rp.ORDER_OPEN, rp.ORDER_BUY, rp.ORDER_INTRADAY, rp.ORDER_CLOSE
SEED = 702
# SELECT
POOL_MIN_RAW_CLOSE = 5.0                          # the $5 test reads the RAW (unadjusted) close — the price his screen showed
POOL_MIN_DV = 10_000_000.0                        # the $10M test reads the export's close x the export's volume: both split-adjusted on one basis,
POOL_DV_WINDOW = 20                               # so the product is split-invariant (the data standard's `rolling_median_dv`); raw close x adjusted
POOL_MIN_HISTORY = 130                            # volume was NOT (a later split changed a 2020 decision: TSLA 15x too high, CODX 30x too low)
POOL_RATE_CAP = 0.20
SELECT_MAX_CONJ = 3
SELECT_ADD_RECALL = 0.10
SELECT_PASS_RECALL = 0.50
SELECT_FALSIFY_LIFT = 2.0
SELECT_PLANTED_RUNS = 20
SELECT_PLANTED_BEAT = 19
SHORT_CLUSTER_PCT = 95
RANK_PASS_PCTL = 0.25
RANK_FALSIFY_PCTL = 0.40
RIDGE_LAMBDA = 1.0
ADMIT_TYPES = frozenset({"CS", "ADRC", ""})
TYPE_OVERRIDE = {"LAZR": "CS"}                    # Luminar, a stock in 2020-22; typed ETF today (§2b, one override)
# ENTER
LEVELS = ("L1", "L2", "L3", "L4", "L5", "L6")
LEVEL_KNOWN_MIN = {"L1": 5, "L6": 60}             # the minute (since 09:30) a level EXISTS: ORH5 at 09:35, the first-hour high at 10:30; a bracket that
                                                  # ends before it reads `no_level_yet` for that level (counted), never HIT / BALLPARK
BALLPARK_ADR = 0.25
BALLPARK_ADR_UNBRACKETED = 0.5
ENTER_PASS_FEASIBLE = 0.50
ENTER_PASS_HIT = 0.70
ENTER_CONTROL_MARGIN = 0.15
ENTER_MIN_CHECK = 40
RANDOM_LEVELS = 200
RANDOM_KEY = "rev|minute"
ORH5_FIRST = "09:35"
# STOP
STOP_LEVELS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")   # the eight the ordering (Spearman) reads
STOP_CHOOSABLE = ("S1", "S2", "S3", "S4", "S5", "S6", "S7")      # "his stop" is chosen among these; S8 and the 50-day are CONTROLS, never his stop (§7b)
STOP_CONTROLS = ("S8", "SMA50")
STOP_VARIANTS = ("T", "C")
STOP_H_CHOOSE = 0.10
STOP_H_PASS = 0.15
STOP_H_FALSIFY = 0.30
STOP_MIN_TRADED = 20
STOP_SPEARMAN = 0.70
REC_MIN_BARS = 50                                 # §2b step 5 / §13 (registered 2026-10-24, check M7): a STOP / EXIT record (and a SELECT pick record) needs
REC_MIN_BARS_ENTER = 20                           # 50 bars before the buy day (SMA50, the 50-day control); an ENTER record 20 (ADR20, the prior-20 high /
                                                  # low — nothing in ENTER reads further back); the pool's 130-session floor applies to SELECT's buys
STOP_UNREAD_DATED = {("S2", "T"), ("S2", "C"), ("S4", "T"), ("S4", "C"), ("S6", "T"), ("S6", "C"), ("S8", "T"), ("S8", "C"),
                     ("SMA50", "T"), ("SMA50", "C"), ("S3", "T"), ("S5", "T"), ("S7", "T")}   # on dated 2021-22; the rest re-reads. A LABEL only: the
                                                  # dated 111 are beside on every level (re-check N1 — the EXIT fit walks them under the chosen stop)
# EXIT
EXIT_RECOVERY_BAR = 0.25
EXIT_VOID_RATIO = 1.25
EXIT_HIT_MAX_WINDOW = 20
EXIT_GRID = (("X1", "<=", 0.0), ("X1", "<=", -0.5), ("X2", "<=", 0.0), ("X2", "<=", -0.5),
             ("X7", ">=", 0.0), ("X7", ">=", 1.0), ("X7", ">=", 2.0), ("X7", ">=", 3.0), ("X7", "<=", 0.0),
             ("X8", ">=", 1.0), ("X8", ">=", 2.0), ("X5", ">=", 3), ("X5", ">=", 5), ("X5", ">=", 10),
             ("X3", "==", 1), ("X4", "==", 1), ("X9", "==", 1))
EXIT_MAX_RULES = 3
EXIT_MAX_COND_PER_RULE = 2
TRIVIAL_SESSION = 2                               # §3: "sell at the close of session 3" — sessions are numbered from the buy day = session 1, so session 3
                                                  # is offset 2 (his median hold of 3 trade-days = the buy day + 2); check L7
TRIVIAL_RED_FROM = 1                              # §3: "the first red close" is read from session 2 (offset 1) — the buy day's own close is not scored
# WHY
PHRASE_RX = (r"\bstopped out\b|\bgot stopped\b|\bstopped me out\b|\bi sold\b|\bsold it\b|\bsold all\b|\bsold everything\b|\bsold out\b|"
             r"\bsold a third\b|\bsold half\b|\bsold some\b|\btook partials?\b|\btook profits?\b|\btrimmed\b|\bi closed it\b")
PHRASE_CLASS = {"stopped out": "STOPPED", "got stopped": "STOPPED", "stopped me out": "STOPPED",
                "i sold": "SOLD", "sold it": "SOLD", "sold all": "SOLD", "sold everything": "SOLD", "sold out": "SOLD", "i closed it": "SOLD",
                "sold a third": "PARTIAL", "sold half": "PARTIAL", "sold some": "PARTIAL", "took partial": "PARTIAL", "took partials": "PARTIAL",
                "took profit": "PARTIAL", "took profits": "PARTIAL", "trimmed": "PARTIAL"}
SINGLE_FORMS = {"i sold": r"\bi sold\b", "stopped out": r"\bstopped out\b", "i got stopped": r"\bi got stopped\b", "stopped me out": r"\bstopped me out\b"}
WHY_WINDOW_S = 30.0
WHY_SEED = 1024
WHY_SAMPLE = {"STOPPED": 8, "SOLD": 8, "PARTIAL": 4}
WHY_PRECISION = 0.70
# clocks
CLOCK_MISREAD_S = 120

# ═════════════════════════════════════════════════════════════════════════════════════════════
# EXPECT — every composition count of §2 / §2b / §6 / §8 / §10 / §12 / §13, as the doc fixes them: (doc anchor, label) -> value.
# The anchor is a phrase of the doc line that carries the claim; the dry run resolves it to the CURRENT line number (so a doc edit cannot
# leave a stale "[L383]" in the printout) and prints "[L?]" when the phrase is gone. Labels are unique (asserted at import).
# ═════════════════════════════════════════════════════════════════════════════════════════════
EXPECT = [
    ("**1,861 non-initial**", "entries / initial / non-initial", "1874 / 13 / 1861"), ("**1,861 non-initial**", "snapshots", 2907), ("**1,861 non-initial**", "streams", 517),
    ("**dated, deciding**", "dated deciding n / names / dense / 2020 / 2021-22 / exits known", "294 / 153 / 264 / 149 / 115 / 290"),
    ("| dated, window > 10 |", "dated window > 10: n / names / held-to-exit median / 2017-18", "50 / 47 / 116 / 21"),
    ("**no event, non-flicker, window ≤ 10**", "no event non-flicker <= 10: n / names / w1 / w2 / w3-5 / w6-10", "633 / 274 / 427 / 103 / 66 / 37"),
    ("| no event, flicker, window ≤ 10 |", "no event flicker <= 10: n / names / one-session", "349 / 196 / 273"),
    ("| no event, window > 10 |", "no event window > 10", 58),
    ("| never a candidate |", "never a candidate: n / names / funds / ETF / ETV / ETN / other / typed stocks / no type row", "360 / 147 / 233 / 178 / 32 / 19 / 4 / 53 / 74"),
    ("| never a candidate |", "never a candidate ETFs TQQQ / SOXL / TNA / SPXL", "26 / 21 / 16 / 14"),
    ("| no bars |", "no bars: n / names", "117 / 81"),
    ("343 have none of our events", "633 vs events outside: none / 6-20 before / 1-5 before / 1-5 after (priority) / other level inside", "343 / 97 / 69 / 77 / 47"),
    ("**126 of the 633 have an event 1–5 sessions after**", "633 with any event 1-5 after", 126),
    ("By buy year (window start) the 633 fall", "633 by buy year 2017 / 2019 / 2020 / 2021 / 2022 / 2023", "6 / 69 / 301 / 196 / 45 / 16"),
    ("597 are era-A buys", "633 era A / B; touch the Q1-2022 hole", "597 / 36; 24"),
    ("| non-flicker | 427", "one-session non-flicker: all / exits known / inverted / dense / 2020 / 2021-22 / trade-days / to first / median", "427 / 427 / 8 / 374 / 197 / 177 / 4436 / 3203 / 6"),
    ("| flickers included | 700", "one-session incl flickers: all / flickers / left by close / inverted / dense / 2020 / 2021-22 / trade-days dense / median", "700 / 273 / 161 / 26 / 615 / 335 / 280 / 3438 / 3"),
    ("| dated deciding (for scale) |", "dated deciding: n / exits / same-day exits / flickers / dense / 2020 / 2021-22 / trade-days / to first / median", "294 / 290 / 42 / 91 / 264 / 149 / 115 / 3351 / 2260 / 5"),
    ("**185 (in session 94, pre-market 91)**", "dated in window: first seen in session / flat frame (in, pre) / both / both in-session (2020, 2021-22)", "172 / 185 (94, 91) / 135 / 53 (32, 21)"),
    ("in-session bracket width median 24 minutes", "dated in-session bracket width: median / q25 / q75 / <= 30 min", "24 / 15 / 42 / 29"),
    ("82 bracket from a pre-market flat frame", "dated: pre-market-flat brackets / no flat frame that day / held before 09:35", "82 / 37 / 9"),
    ("TSLA 2020-04-14, UAL 05-27", "held before 09:35 (dated in window)", "TSLA 2020-04-14, UAL 2020-05-27, DXCM 2020-07-29, PINS 2020-07-31, SHOP 2020-08-26, TTD 2020-08-26, KOLD 2022-04-19, LAC 2022-04-21, TSLA 2022-04-21"),
    ("first seen in session 237", "one-session no-event (window): first seen in session (2020, 2021-22) / flat frame that day", "237 (122, 115) / 237"),
    ("brackets 108** (60 / 48", "one-session no-event: in-session brackets (2020, 2021-22) / median / q25 / q75 / pre-market-flat / held before 09:35", "108 (60, 48) / 35.5 / 21 / 56.5 / 129 / 1 (ROKU 2020-09-15)"),
    ("with flickers 175 in-session brackets", "one-session no-event with flickers: in-session brackets (2020, 2021-22) / median", "175 (103, 72) / 34"),
    ("columns of `entries.tsv` are filled for dated rows only", "stored clock columns: dated in window matching the derivation / undated rows filled", "264 / 0"),
    ("**Re-buys:** 280 of the 684 panel names", "re-buys: names with > 1 entry / of 684 / their entries (non-initial)", "280 / 684 / 1467"),
    ("**A re-buy = an entry whose window start lies 0–14", "re-buy (0-14 days after the previous non-initial entry's exit_hi): n / 2020 / 2021 / 2019 / 2022 / deciding / undated", "564 / 282 / 184 / 60 / 28 / 75 / 486"),
    ("**A same-day re-buy**", "same-day re-buys in the 427 / the 700 / the dated 294", "8 / 24 / 2 (PLUG, SNAP)"),
    ("495 videos carry a caption track", "captions: vtt files", 495),
    ("It occurs **4,015 times in 477 videos**", "alternation: hits / videos / 2020 / 2021 / 2017 / 2019 / 2022 / 2023 / 2018", "4015 / 477 / 2224 / 884 / 425 / 341 / 87 / 41 / 13"),
    ('single forms: *"i sold"* 1,221', "single forms: i sold / stopped out / i got stopped / stopped me out", "1221 / 2099 / 883 / 321"),
    ("786 of those name a ticker whose panel exit window covers", "within 30 s of a ticker / qualifying (2020, 2021) / trades / deciding / ambiguous", "2261 / 786 (495, 212) / 380 / 88 / 150"),
    ("| no-event non-flicker, window ≤ 10 | 633 |", "§2b 633: type / inverted / same-day / used / one-session / 2-10", "55 / 8 / 8 / 562 / 375 / 187"),
    ("| no-event non-flicker, window ≤ 10 | 633 |", "§2b type removals", "UVXY 7, AGQ 7, GUSH 7, ERX 5, FAS 5, BOIL 5, KWEB 4, SLV 3, BRZU 2, JETS 2, VXX 2, 6 others 1 each"),
    ("| SELECT fit: one-session non-flicker, 2020 |", "SELECT fit 2020: 197 - type - inverted - same-day = used / never-a-candidate adds / flickers beside", "197 - 5 - 2 - 2 = 188 / 12 / 116"),
    ("| SELECT check: one-session non-flicker, 2021-01-04..2022-06-14 |", "SELECT check 2021-22: 177 - type - inverted - same-day = used / adds / flickers beside", "177 - 30 - 1 - 1 = 145 / 15 / 81"),
    ("| SELECT beside: 2017 / 2019 / 2023", "SELECT beside 2017 / 2019 / 2023 before -> after", "1 / 35 / 7 -> 1 / 26 / 5"),
    ("| STOP / EXIT undated fit: one-session incl. flickers, 2020 |", "STOP/EXIT undated fit 2020: 335 - type - inverted - same-day = used / trade-days / non-flicker", "335 - 9 - 14 - 8 = 304 / 1822 / 188"),
    ("| STOP / EXIT undated check: one-session incl. flickers, 2021-22 |", "STOP/EXIT undated check 2021-22: 280 - type - inverted - same-day = used / trade-days / non-flicker", "280 - 51 - 2 - 1 = 226 / 1260 / 145"),
    ("| dated deciding | 294 |", "dated deciding: 294 - type - inverted - same-day = used / known exits / 2020 / 2021-22", "294 - 2 - 0 - 2 = 290 / 286 / 149 / 111"),
    ("| dated deciding | 294 |", "dated type removals", "BOIL 2021-05-17, KOLD 2022-04-19"),
    ("KOLD leaves the held-before-09:35 list", "held before 09:35 after the type gate: dated + undated", "8 + 1"),
    ("**Never-a-candidate stocks back in, for SELECT only**", "never-a-candidate stocks (typed CS/ADRC or untyped) re-entering SELECT", 127),
    ("pre-market-flat brackets (dated 82, undated non-flicker 113 after §2b)", "ENTER beside after §2b: pre-market-flat brackets dated / undated non-flicker; dated no flat frame; dated pre-market first sightings / of", "82 / 113; 36; 78 / 260"),
    ("**Fit set:** the 32 in-session-bracketed dated + 59 in-session-bracketed exact-day undated buys of 2020", "ENTER fit: in-session brackets dated + undated (with flickers) / check", "32 + 59 (94) / 20 + 44 (63)"),
    ("**Flicker share, stated:**", "EXIT flicker share: fit / dated / undated / check (%); name-confirmed share of the fit (%)", "35 / 32 / 38 / 36; 48"),
    ("**The STOP / EXIT check's bars were partly walked.**", "§10 check buys inside a dated trade's 121-session path: of 280 / of 177 nf / of 226 / of 145 nf; fit side of 335", "69 / 40 / 65 / 38; 116"),
    ("**The forward event count (header):**", "§10 forward events: the 77 by fit / check / other; the 126; of the 177 nf check buys", "39 / 35 / 3; 70 / 48 / 8; 40"),
    ("**Minutes (the gate that bites).**", "§12 deciding with minute bars on E (four trees) / missing", "290 of 294 / DRYS 2017-02-01, DDOG 2019-11-13, FUBO 2021-01-05, QS 2021-02-12"),
    ("only 32 had minute bars on the buy day", "§12 one-session no-event 427: covered (four trees) / missing / by year 2020 2021 2019 2022 2023 2017", "32 / 395 / 188 141 35 25 5 1"),
    ("of their 273 one-session flicker siblings 17", "§12 273 flickers covered / 206 multi windows: sessions / covered", "17 / 717 / 22"),
    ("**1,322 distinct ticker|date pairs**", "§12 fetch list: pairs / sha prefix / latest / kinds nf flicker window / years 2017 2019 2020 2021 2022 2023", "1322 / 4191485f / 2023-12-14 / 394 235 693 / 17 139 615 368 131 52"),
    ("on the four pinned trees alone", "§12 ENTER scorable on the four pinned trees alone (pre-fetch): fit dated + undated / check", "32 + 7 / 20 + 4"),
    ("1,302 ok", "§12 the new tree minutes_rev_1024: fetch-list pairs ok / empty / still missing; rows not on the list", "1302 / 20 / 0; 0"),
    ("AXNX 2020-01-02", "§12 the 20 empty pairs", "AXNX 2020-01-02, AXNX 2020-01-03, AXNX 2020-01-06, AXNX 2020-01-07, AXNX 2020-01-08, AXNX 2020-01-09, AXNX 2020-01-10, CHRD 2020-04-30, FACT 2020-10-16, FACT 2020-11-05, FBR 2019-10-22, FBR 2019-10-23, FBR 2019-11-12, FBR 2019-11-15, FBR 2019-11-18, HTZ 2020-03-24, HTZ 2020-07-22, SRTA 2019-11-15, U 2020-07-24, XP 2019-11-29"),
    ("423 of 427", "§12 coverage with the new tree: one-session non-flicker / flickers / window sessions", "423 of 427 / 267 of 273 / 707 of 717"),
    ("32 + 58", "§12 ENTER set members with minute bars, five trees: fit dated + undated (with flickers) / check", "32 + 58 (91) / 20 + 44 (63)"),
    ("the 21 misread clocks are all 2019", "guard (8): clock reads off the fitted clock by > 2 min: n / all 2019", "21 / True"),
    # §2b step 5 and §13's record floors: the dry run runs the SAME path the fit runs (the record builder, then the pool floor) — values
    # written from the dry run of 2026-10-24 after the split-invariant dollar volume (check H2 / M7)
    ("Counted by the dry run", "§2b step 5: fit 188 -> passes / check 145 -> passes / never-a-candidate 12 -> / 15 -> / flickers 116 -> / 81 ->", "136 / 121 / 0 / 1 / 79 / 69"),
    ("record builder keeps", "§13 records: dated 290 -> / undated fit 304 -> / undated check 226 -> / windows 187 -> / ENTER fit 32 + 59 -> / check 20 + 44 -> / EXIT dated 286 ->", "288 / 282 / 212 / 175 / 32 + 57 / 20 + 41 / 284"),
    ("the four fit sets, as the dry run asserts them", "guard (5): the four fit sets on the real buys: SELECT / ENTER / STOP / EXIT buys; violations", "200 / 91 / 453 / 590; 0"),
    # re-check N3: the 47 other-level buys split by year — the fit reads the ones outside 2021-22, --check the 2021-22 ones
    ("**The 47 are split by year (re-check N3):**", "§5b the 47 other-level buys: fit (2019 / 2020 / 2023) / check (SELECT check buys + windows); 2022",
     "32 (1 / 30 / 1) / 15 (12 + 3); 0"),
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


class GuardStop(Exception):
    pass


# ═════════════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ═════════════════════════════════════════════════════════════════════════════════════════════
def fmt_claim(x) -> str:
    if isinstance(x, float):
        return f"{x:.4g}"
    return str(x)


class Claims:
    """The dry run's assertions against the doc: every line printed with the doc line the anchor resolves to, every mismatch collected,
    STOP at the end (never at the first)."""

    def __init__(self, say):
        self.say = say
        self.bad = []
        self.n = 0

    @staticmethod
    def _norm(x) -> str:
        """A 'SYM n, SYM n, ..., k others 1 each' list is a SET: compared order-free (the doc lists ties in no fixed order)."""
        s = fmt_claim(x)
        if re.fullmatch(r"([A-Z.\-]+ \d+, )+\d+ others 1 each", s):
            head, tail = s.rsplit(", ", 1)
            return ", ".join(sorted(head.split(", "))) + ", " + tail
        return s

    def __call__(self, anchor: str, label: str, doc, mine) -> bool:
        ok = self._norm(doc) == self._norm(mine)
        self.n += 1
        ln = doc_line_of(anchor)
        self.say(f"  [L{ln if ln else '?'}] {label} | doc {fmt_claim(doc)} | mine {fmt_claim(mine)} | {'OK' if ok else 'MISMATCH'}")
        if not ok:
            self.bad.append((ln, label, doc, mine))
        return ok


def pct(x, nd=1) -> str:
    return rp.pct(x, nd)


def binom_ci(k: int, n: int) -> tuple:
    """(share, half-width): the 95% binomial interval the doc quotes (normal approximation; 50% on 64 trades = +-12 points)."""
    if n <= 0:
        return float("nan"), float("nan")
    p = k / n
    return p, 1.96 * math.sqrt(p * (1 - p) / n)


def hhmm_to_min(c: str) -> "int | None":
    """'HH:MM' ET -> minutes since 09:30 (negative before the open)."""
    if not c:
        return None
    h, m = c.split(":")
    return int(h) * 60 + int(m) - (9 * 60 + 30)


def min_to_hhmm(m: int) -> str:
    t = 9 * 60 + 30 + int(m)
    return f"{t // 60:02d}:{t % 60:02d}"


def spearman(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(a) < 2:
        return float("nan")
    ra, rb = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def rng_for(key: str, seed: int = SEED) -> np.random.Generator:
    return np.random.default_rng([seed, zlib.crc32(key.encode()) & 0xFFFFFFFF])


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock (the second read's line-anchored lock, imported), the keyed CHOSEN lines, the ledger, the outputs
# ═════════════════════════════════════════════════════════════════════════════════════════════
FREEZE_MARKER = ex.FREEZE_MARKER
marker_spans, doc_body_sha, freeze_missing = ex.marker_spans, ex.doc_body_sha, ex.freeze_missing
_CHOSEN_RX = re.compile(r"^\s*(?:[-*>]\s*)?`?\**CHOSEN (SELECT|ENTER|STOP|EXIT):\**`?\s*(.*?)\s*$")


def chosen_lines(doc: str = None) -> dict:
    """{stage: [values]} of the `CHOSEN <STAGE>: ...` lines ABOVE the one line-anchored marker, parsed by their stage key (never by position).
    An empty dict when the doc has no single marker line."""
    with open(doc or DOC, "rb") as fh:
        raw = fh.read()
    sp = marker_spans(raw)
    if len(sp) != 1:
        return {}
    body = raw[:sp[0][0]].decode("utf-8", errors="replace")
    out = defaultdict(list)
    for ln in body.splitlines():
        m = _CHOSEN_RX.match(ln)
        if not m:
            continue
        val = m.group(2).strip().strip("`*").strip()
        if "CHOSEN " in val or val in ("", "…", "..."):
            continue                                   # a prose mention of the lines (§13 lists them inline), never a chosen value
        out[m.group(1).lower()].append(val)
    return dict(out)


def ledger_append(stage: str, path: str) -> None:
    """Append-only: stage, printout path, sha256, time. Verified by --check against the files on disk."""
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a") as fh:
        if new:
            fh.write("stage\tpath\tsha256\ttime\n")
        fh.write(f"{stage}\t{path}\t{sha(path)}\t{_dt.datetime.now().isoformat(timespec='seconds')}\n")


def ledger_verify() -> list:
    """Every ledger row's file must exist with the recorded sha (a deleted or regenerated printout is caught). -> the problems."""
    if not os.path.exists(LEDGER):
        return ["ledger missing"]
    bad = []
    rows = pd.read_csv(LEDGER, sep="\t", dtype=str, keep_default_na=False)
    for r in rows.to_dict("records"):
        if not os.path.exists(r["path"]):
            bad.append(f"{r['path']}: missing")
        elif sha(r["path"]) != r["sha256"]:
            bad.append(f"{r['path']}: changed since the ledger recorded it")
    return bad


def stage_outputs(stage: str) -> list:
    """Files whose existence refuses a stage: its own printout, a STOPPED file and, for the check, every stage output under reverse/
    (the dry run's `dryrun_*` files never refuse anything)."""
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
        out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR) if not f.startswith("dryrun_"))
    return out


def subs_list_sha(paths: list = None) -> str:
    """One sha over the sorted (basename, sha256) list of the caption files (§13: 'one sha over the sorted list')."""
    return rp.tree_sha(paths if paths is not None else sorted(glob.glob(SUBS_GLOB)))


def pins(minute_dates: "dict | None" = None, doc: "str | None" = None, include_outputs: bool = True) -> dict:
    """Every pin; the fit printouts and the ledger are included when they exist (named absent otherwise)."""
    p = {name: sha(path) for name, path in FILES.items()}
    p.update({name: sha(path) for name, path in CODE.items() if os.path.exists(path)})
    for name, path in CODE.items():
        if not os.path.exists(path):
            p[name] = "ABSENT"
    p["subs_list"] = subs_list_sha()
    p["first_doc_body"] = rp.doc_body_sha(rp.DOC)
    p["second_doc_body"] = ex.doc_body_sha(ex.DOC)
    p["holdings_doc_body"] = doc_body_sha(H.DOC)
    for tree, dates in (minute_dates or {}).items():
        files = R.minute_date_files(MINUTES[tree])
        p[f"minutes_{tree}_used"] = rp.tree_sha([str(files[d]) for d in sorted(set(dates)) if d in files])
    if include_outputs:
        p["dryrun_printout"] = sha(P_DRY) if os.path.exists(P_DRY) else "ABSENT"      # guard (3) / L3: the completed dry run is pinned too
        for s in STAGES:
            p[f"{s}_fit_printout"] = sha(P_FIT[s]) if os.path.exists(P_FIT[s]) else "ABSENT"
        p["ledger"] = sha(LEDGER) if os.path.exists(LEDGER) else "ABSENT"
    p["doc_body"] = doc_body_sha(doc or DOC)
    return p


def dry_run_complete(path: str = None) -> bool:
    """True when the dry run printout exists and its last non-empty line says DRY RUN COMPLETE (a STOPPED dry run also writes the file;
    guard (3) must not accept it — check L3)."""
    path = path or P_DRY
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    return bool(lines) and lines[-1].startswith("DRY RUN COMPLETE")


def check_pinned_inputs(say) -> None:
    """The holdings replay's pins (exports, candidates, labels, guards, the frozen modules) and this doc's own (the fetch list) must hold."""
    paths = {**FILES, **CODE}
    drift = []
    for k, v in PINNED.items():
        if k in paths and os.path.exists(paths[k]) and sha(paths[k]) != v:
            drift.append(f"{k}: {sha(paths[k])[:12]} (pinned {v[:12]})")
    if sha(H_PATH) != H_SHA or sha(H_TESTS) != H_TESTS_SHA:
        drift.append("holdings_module/tests")
    if drift:
        raise GuardStop("a pinned input changed: " + "; ".join(drift))
    say("- the holdings replay's pins re-checked (exports, candidates, labels, guards, the frozen modules and tests; the holdings module and tests = "
        "its freeze record; the fetch list = §12's sha): no drift")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the buys (entries.tsv + the holdings module's same-day re-buy rule + the panel clock derived for every row)
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Buy:
    eid: int
    sym: str
    sym_a: str
    has_bars: bool
    ever_candidate: bool
    setup: str                      # breakout | EP | both | undated | initial
    E: str                          # the buy day: the event day if dated, the window start (lo) if undated (the holdings `load_events`)
    D: str
    era: str                        # R10 by the buy day for undated; the timeline's for dated
    ticker: str                     # the bar-file symbol of its era
    pivot: "float | None"
    adr20: "float | None"
    base_id: str
    retrigger: int
    undated_reason: str
    first_frame: str
    prev_full_frame: str
    lo: str
    hi: str
    window_len: int
    inverted: bool
    initial: bool
    flicker: bool
    exit_lo: str
    exit_hi: str
    still_held: bool
    decides: bool
    stored_first_clock: str = ""
    stored_flat_clock: str = ""
    # derived
    dated: bool = False
    noev: bool = False
    year: int = 0
    Ei: int = -1
    lo_i: int = -1
    hi_i: int = -1
    exit_lo_i: int = -1
    exit_hi_i: int = -1
    first_clock: str = ""            # the first in-session frame on E showing the name (the timeline's rule: ctx != pre)
    flat_clock: str = ""             # the last full frame on E without it (ctx != closed)
    p_ctx: str = ""
    f_ctx: str = ""
    in_bracket: bool = False         # first in session AND the flat frame IN SESSION (ctx == in)
    pre_flat_bracket: bool = False   # first in session AND the flat frame pre-market
    held_before_0935: bool = False
    same_day_rebuy: bool = False
    rebuy_of: int = -1
    sec_type: str = ""
    type_src: str = ""
    type_ok: bool = True
    rebuy: bool = False              # §2: window start 0-14 calendar days after the same name's previous non-initial entry's exit_hi
    rebuy_prev_eid: int = -1         # that previous entry (the after-loss flag of §7b reads ITS exit against ITS inferred fill)
    in_dated_path: bool = False      # §10: the buy day inside a dated trade's 121-session path on the same name
    fwd_event_1_5: bool = False      # §2: one of our events 1-5 sessions AFTER the window (forward information; never a feature)
    other_level_inside: bool = False  # §2: a k5 / k10 / full / com level fired inside the window
    event_class: str = ""
    sets: set = field(default_factory=set)

    @property
    def wl(self) -> int:
        return self.window_len

    @property
    def has_exit(self) -> bool:
        return self.exit_hi_i >= 0

    def trade_days(self, to_lo: bool = False) -> int:
        j = self.exit_lo_i if to_lo else self.exit_hi_i
        return (j - self.Ei + 1) if (j >= 0 and self.Ei >= 0) else 0

    def exit_window_len(self) -> int:
        return (self.exit_hi_i - self.exit_lo_i + 1) if self.has_exit else -1


def era_of(E: str) -> str:
    return "A" if E <= A_LAST else "B"


def select_era_of(E: str) -> str:
    """SELECT's era (§3): era A through its export's last session, the pick's features on the same export as its pool."""
    return "A" if E <= A_EXPORT_LAST else "B"


def load_buys(entries_path: str = None) -> list:
    """entries.tsv -> Buy per row (initial rows included, flagged); the holdings module's same-day re-buy rule applied read-only."""
    t = pd.read_csv(entries_path or FILES["entries"], sep="\t", dtype=str, keep_default_na=False)
    evs, _c = H.load_events(entries_path or FILES["entries"])
    sdr = {ev.eid: (ev.same_day_rebuy, ev.rebuy_of) for ev in evs}
    out = []
    for r in t.to_dict("records"):
        initial = r["initial"] == "True"
        setup = r["setup"]
        dated = setup in H.SETUPS
        E = r["E"] if dated else r["lo"]
        era = r["era"] if (dated and r["era"]) else era_of(E) if E else ""
        b = Buy(eid=int(r["eid"]), sym=r["sym"], sym_a=r["sym_a"], has_bars=r["has_bars"] == "True", ever_candidate=r["ever_candidate"] == "True",
                setup=setup, E=E, D=r["D"], era=era, ticker=r["sym_a"] if era == "A" else r["sym"],
                pivot=float(r["pivot"]) if (setup in ("breakout", "both") and r["pivot"]) else (float(r["ep_prev_close"]) if (setup == "EP" and r["ep_prev_close"]) else None),
                adr20=float(r["adr20"]) if (setup in ("breakout", "both") and r["adr20"]) else None,
                base_id=r.get("base_id", ""), retrigger=int(r["retrigger"] or 0), undated_reason=r["undated_reason"],
                first_frame=r["first_frame"], prev_full_frame=r["prev_full_frame"], lo=r["lo"], hi=r["hi"],
                window_len=int(r["window_len"] or 0), inverted=r["inverted"] == "True", initial=initial, flicker=r["flicker"] == "True",
                exit_lo=r["exit_lo"], exit_hi=r["exit_hi"], still_held=r["still_held"] == "True", decides=r["decides"] == "True",
                stored_first_clock=r.get("first_clock_on_E", ""), stored_flat_clock=r.get("flat_clock_on_E", ""))
        b.dated = dated
        b.noev = (setup == "undated") and (r["undated_reason"] == "no_event_in_window")
        b.year = int(E[:4]) if E else 0
        b.same_day_rebuy, b.rebuy_of = sdr.get(b.eid, (False, -1))
        out.append(b)
    return out


def index_calendar(buys: list, cal: list) -> None:
    CI = {d: i for i, d in enumerate(cal)}
    for b in buys:
        b.Ei = CI.get(b.E, -1)
        b.lo_i, b.hi_i = CI.get(b.lo, -1), CI.get(b.hi, -1)
        b.exit_lo_i, b.exit_hi_i = CI.get(b.exit_lo, -1), CI.get(b.exit_hi, -1)


# ---- the panel clock on the buy day, one derivation for every row (the timeline's `panel_clocks` on the stored frames) -------------
def load_snapshots(path: str = None) -> pd.DataFrame:
    sn = pd.read_csv(path or FILES["snapshots"], sep="\t", dtype=str, keep_default_na=False)
    assert sn["frame_id"].is_unique
    return sn


def derive_clocks(buys: list, sn: pd.DataFrame) -> None:
    """first_clock = the first sighting frame's clock when it is on E and not pre-market; flat_clock = the last full frame without the
    name when it is on E and not after the close; in_bracket needs the flat frame IN SESSION (ctx == in). Initial rows carry nothing."""
    sni = sn.set_index("frame_id")
    for b in buys:
        b.first_clock = b.flat_clock = b.p_ctx = b.f_ctx = ""
        b.in_bracket = b.pre_flat_bracket = b.held_before_0935 = False
        if b.initial or not b.E:
            continue
        f = sni.loc[b.first_frame] if b.first_frame in sni.index else None
        p = sni.loc[b.prev_full_frame] if (b.prev_full_frame and b.prev_full_frame in sni.index) else None
        if f is not None:
            b.f_ctx = f["ctx"]
            if f["date"] == b.E and f["ctx"] != "pre":
                b.first_clock = f["clock"]
        if p is not None:
            b.p_ctx = p["ctx"]
            if p["date"] == b.E and p["ctx"] != "closed":
                b.flat_clock = p["clock"]
        b.in_bracket = bool(b.first_clock) and bool(b.flat_clock) and b.p_ctx == "in"
        b.pre_flat_bracket = bool(b.first_clock) and bool(b.flat_clock) and b.p_ctx == "pre"
        b.held_before_0935 = bool(b.first_clock) and b.first_clock < ORH5_FIRST


def et_seconds(et_time: str) -> "int | None":
    if not et_time or len(et_time) < 16:
        return None
    try:
        return int(et_time[11:13]) * 3600 + int(et_time[14:16]) * 60
    except ValueError:
        return None


def clock_misreads(sn: pd.DataFrame) -> dict:
    """Guard (8): per video the clock fit = median(clock read - stream time); a frame whose own read is off the fit by > 2 min is a misread.
    -> {frame_id: (date, off_seconds)} for the misread frames."""
    out = {}
    for vid, g in sn.groupby("vid"):
        reads = [(r["frame_id"], r["date"], et_seconds(r["et_time"]), int(float(r["stream_ts"]))) for r in g.to_dict("records") if et_seconds(r["et_time"]) is not None]
        if not reads:
            continue
        off = float(np.median([s - st for _f, _d, s, st in reads]))
        for fid, d, s, st in reads:
            if abs(s - st - off) > CLOCK_MISREAD_S:
                out[fid] = (d, s - st - off)
    return out


def bracket_width(b: Buy) -> "int | None":
    a, z = hhmm_to_min(b.flat_clock), hhmm_to_min(b.first_clock)
    return None if (a is None or z is None) else z - a


# ---- the type gate -------------------------------------------------------------------------------------------------------------------
def load_types() -> tuple:
    from pathlib import Path
    return SEC.load_small(Path(FILES["small_pulls"])), SEC.load_sic(Path(FILES["sic"]))


def type_of(sym_for_type: str, small: dict, sic: dict) -> tuple:
    """(type, source, admitted): `resolve_type` keyed by the bar symbol; CS / ADRC / no type row admitted; the one override (LAZR)."""
    if sym_for_type in TYPE_OVERRIDE:
        t = TYPE_OVERRIDE[sym_for_type]
        return t, "override", t in ADMIT_TYPES
    t, src = SEC.resolve_type(sym_for_type, small, sic)
    return t, src, t in ADMIT_TYPES


def apply_type_gate(buys: list, small: dict, sic: dict) -> None:
    for b in buys:
        key = b.sym_a if (b.E and b.E <= A_LAST) else b.sym     # keyed by sym_a on era-A buy days, the panel symbol on era-B days
        b.sec_type, b.type_src, b.type_ok = type_of(key, small, sic)


# ---- re-buys (§2's one definition) --------------------------------------------------------------------------------------------------
def mark_rebuys(buys: list) -> int:
    """An entry whose window start lies 0-14 calendar days after the same panel name's previous NON-INITIAL entry's exit_hi (entries of a
    name in eid order; the immediately preceding entry)."""
    n = 0
    by_sym = defaultdict(list)
    for b in sorted(buys, key=lambda x: x.eid):
        by_sym[b.sym].append(b)
    for sym, lst in by_sym.items():
        prev = None
        for b in lst:
            if prev is not None and not prev.initial and not b.initial and prev.exit_hi and b.lo:
                gap = (date.fromisoformat(b.lo) - date.fromisoformat(prev.exit_hi)).days
                if 0 <= gap <= 14:
                    b.rebuy, b.rebuy_prev_eid = True, prev.eid
                    n += 1
            prev = b
    return n


# ---- our events just outside the window (event dates only; the timeline's partition as is) ------------------------------------------
def load_event_dates() -> dict:
    """{kind: {(era, ticker): set(E)}} for tl / other levels (k5, k10, full, com) / EP primary — the columns `ticker / D / E / K / split` and
    `ticker / E / primary` only (event EXISTENCE on a day)."""
    cols = ["ticker", "D", "E", "K", "split"]
    ca = pd.read_csv(FILES["cand_A"], sep="\t", dtype=str, keep_default_na=False, usecols=cols)
    cbd = pd.read_csv(FILES["cand_B"], sep="\t", dtype=str, keep_default_na=False, usecols=cols)
    ca = ca[ca["E"] <= A_LAST]
    cbd = cbd[(cbd["E"] <= CUT_B) & (cbd["D"] <= CUT_B) & (cbd["E"] >= B_FIRST) & (cbd["split"] == "discovery")]
    EV = {k: defaultdict(set) for k in ("tl", "other", "ep")}
    for era, df in (("A", ca), ("B", cbd)):
        for r in df.itertuples():
            EV["tl" if r.K == "tl" else "other"][(era, r.ticker)].add(r.E)
    for era, p, lo_, hi_ in (("A", FILES["ep_A"], "0000-00-00", A_LAST), ("B", FILES["ep_B"], B_FIRST, CUT_B)):
        e = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False, usecols=["ticker", "E", "primary"])
        e = e[(e["primary"] == "True") & (e["E"] >= lo_) & (e["E"] <= hi_)]
        for r in e.itertuples():
            EV["ep"][(era, r.ticker)].add(r.E)
    return EV


def classify_events_outside(buys: list, EV: dict, CI: dict) -> Counter:
    """§2's priority partition on the 633: other level inside the window, then 1-5 before, then 1-5 after, then 6-20 before, else none."""
    c = Counter()
    for b in buys:
        base = EV["tl"].get(("A", b.sym_a), set()) | EV["tl"].get(("B", b.sym), set()) | EV["ep"].get(("A", b.sym_a), set()) | EV["ep"].get(("B", b.sym), set())
        oth = EV["other"].get(("A", b.sym_a), set()) | EV["other"].get(("B", b.sym), set())
        if any(b.lo <= e <= b.hi for e in base):
            raise GuardStop(f"a no-event entry has a tl / EP event inside its window: eid {b.eid}")
        ti = [CI[e] for e in base if e in CI]
        before = [b.lo_i - x for x in ti if x < b.lo_i]
        after = [x - b.hi_i for x in ti if x > b.hi_i]
        b.other_level_inside = any(b.lo <= e <= b.hi for e in oth)
        b15, b620, a15 = any(1 <= x <= 5 for x in before), any(6 <= x <= 20 for x in before), any(1 <= x <= 5 for x in after)
        b.fwd_event_1_5 = a15
        b.event_class = "other_level" if b.other_level_inside else "before_1_5" if b15 else "after_1_5" if a15 else "before_6_20" if b620 else "none"
        c[b.event_class] += 1
    return c


# ---- §10: the check buys inside a dated trade's 121-session path ------------------------------------------------------------------------
def mark_dated_paths(buys: list, dated: list) -> None:
    """A buy day inside [E, E + 120] (sessions) of a DATED entry of the same panel name (the exits study walked every dated trade's path)."""
    paths = defaultdict(list)
    for d in dated:
        if d.Ei >= 0:
            paths[d.sym].append((d.Ei, d.Ei + HORIZON, d.eid))
    for b in buys:
        b.in_dated_path = any(lo <= b.Ei <= hi and eid != b.eid for lo, hi, eid in paths.get(b.sym, ()))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the sets (§2 / §2b): named, in the registration's order; the removal counts kept for the table
# ═════════════════════════════════════════════════════════════════════════════════════════════
def inwin(bs: list, win: tuple) -> list:
    return [b for b in bs if win[0] <= b.E <= win[1]]


def gate_steps(bs: list) -> tuple:
    """§2b steps 1-3 in order: type, inverted, same-day. -> (used, n_type, n_inverted, n_same_day, removed_by_type)."""
    t_out = [b for b in bs if not b.type_ok]
    s1 = [b for b in bs if b.type_ok]
    s2 = [b for b in s1 if not b.inverted]
    s3 = [b for b in s2 if not b.same_day_rebuy]
    return s3, len(t_out), len(s1) - len(s2), len(s2) - len(s3), t_out


def build_sets(buys: list) -> dict:
    ni = [b for b in buys if not b.initial]
    noev = [b for b in ni if b.noev]
    S = {"ni": ni, "noev": noev}
    S["dec"] = [b for b in ni if b.decides]
    S["wide"] = [b for b in ni if b.dated and not b.decides]
    S["c633"] = [b for b in noev if b.wl <= WINDOW_CAP and not b.flicker]
    S["c349"] = [b for b in noev if b.wl <= WINDOW_CAP and b.flicker]
    S["noev_wide"] = [b for b in noev if b.wl > WINDOW_CAP]
    S["nc"] = [b for b in ni if b.undated_reason == "never_candidate"]
    S["nb"] = [b for b in ni if b.undated_reason == "no_bars"]
    S["ex_nf"] = [b for b in noev if b.wl == 1 and not b.flicker]
    S["ex_all"] = [b for b in noev if b.wl == 1]
    S["multi_nf"] = [b for b in noev if 2 <= b.wl <= WINDOW_CAP and not b.flicker]
    # §2b
    S["used_633"], S["n633_type"], S["n633_inv"], S["n633_sd"], S["type_out_633"] = gate_steps(S["c633"])
    S["sel_fit"], S["nfit_type"], S["nfit_inv"], S["nfit_sd"], _ = gate_steps(inwin(S["ex_nf"], FIT_WIN))
    S["sel_chk"], S["nchk_type"], S["nchk_inv"], S["nchk_sd"], _ = gate_steps(inwin(S["ex_nf"], CHECK_WIN))
    S["sel_fit_flick"], *_ = gate_steps([b for b in inwin(S["ex_all"], FIT_WIN) if b.flicker])
    S["sel_chk_flick"], *_ = gate_steps([b for b in inwin(S["ex_all"], CHECK_WIN) if b.flicker])
    nc_ex = [b for b in S["nc"] if b.wl == 1 and not b.flicker and b.type_ok and not b.inverted and not b.same_day_rebuy]
    S["nc_stocks"] = [b for b in S["nc"] if b.type_ok]
    S["sel_fit_nc"], S["sel_chk_nc"] = inwin(nc_ex, FIT_WIN), inwin(nc_ex, CHECK_WIN)
    S["sel_beside"] = {y: gate_steps([b for b in S["ex_nf"] if b.year == y])[0] for y in (2017, 2019, 2023)}
    S["sel_beside_before"] = {y: [b for b in S["ex_nf"] if b.year == y] for y in (2017, 2019, 2023)}
    S["und_fit"], S["nuf_type"], S["nuf_inv"], S["nuf_sd"], _ = gate_steps(inwin(S["ex_all"], FIT_WIN))
    S["und_chk"], S["nuc_type"], S["nuc_inv"], S["nuc_sd"], _ = gate_steps(inwin(S["ex_all"], CHECK_WIN))
    S["dec_used"], S["ndec_type"], S["ndec_inv"], S["ndec_sd"], S["type_out_dec"] = gate_steps(S["dec"])
    S["multi_used"] = [b for b in S["used_633"] if b.wl >= 2]
    S["other_level_47"] = [b for b in S["c633"] if b.other_level_inside]
    # re-check N3: the 2021-22 members (SELECT's check years) are read in --check only; the fit reads the 2019 / 2020 / 2023 members
    S["other_level_chk"] = [b for b in S["other_level_47"] if b.year in (2021, 2022)]
    S["other_level_fit"] = [b for b in S["other_level_47"] if b.year not in (2021, 2022)]
    # ENTER's sets (after §2b)
    S["ent_fit_dated"] = [b for b in inwin(S["dec_used"], FIT_WIN) if b.in_bracket]
    S["ent_chk_dated"] = [b for b in inwin(S["dec_used"], CHECK_WIN) if b.in_bracket]
    S["ent_fit_und"] = [b for b in S["sel_fit"] if b.in_bracket]
    S["ent_chk_und"] = [b for b in S["sel_chk"] if b.in_bracket]
    S["ent_fit_und_fl"] = [b for b in S["und_fit"] if b.in_bracket]
    S["ent_chk_und_fl"] = [b for b in S["und_chk"] if b.in_bracket]
    dw = inwin(S["dec_used"], DENSE)
    S["dec_used_dense"] = dw
    S["ent_pre_dated"] = [b for b in dw if b.pre_flat_bracket]
    S["ent_pre_und"] = [b for b in S["sel_fit"] + S["sel_chk"] if b.pre_flat_bracket]
    S["ent_noflat_dated"] = [b for b in dw if b.first_clock and not b.flat_clock]
    S["ent_prefirst_dated"] = [b for b in dw if b.f_ctx == "pre"]
    # EXIT's sets
    S["exit_fit_dated"] = [b for b in S["dec_used"] if b.has_exit]
    S["exit_fit"] = S["exit_fit_dated"] + S["und_fit"]
    S["exit_chk"] = S["und_chk"]
    S["exit_chk_nf"] = [b for b in S["und_chk"] if not b.flicker]
    S["exit_chk_untouched"] = [b for b in S["und_chk"] if not b.in_dated_path]
    # STOP's sets
    S["stop_fit_dated"] = inwin(S["dec_used"], FIT_WIN)
    S["stop_chk_dated"] = inwin(S["dec_used"], CHECK_WIN)
    for name, lst in S.items():
        if isinstance(lst, list):
            for b in lst:
                b.sets.add(name)
    return S


def tdays(bs: list, to_lo: bool = False) -> int:
    return int(sum(b.trade_days(to_lo) for b in bs if b.has_exit))


def med_held(bs: list) -> float:
    v = [b.trade_days() for b in bs if b.has_exit]
    return float(np.median(v)) if v else float("nan")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# captions: the chain from the pinned alternation (his words; never a source)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_caption_texts(paths: list) -> dict:
    """{video: (text, word_offsets, word_times)}: `qmlib.parse_vtt`, lowercased, joined by spaces."""
    out = {}
    for p in paths:
        v = os.path.basename(p).split(".")[0]
        ws = qmlib.parse_vtt(p)
        toks = [w.lower() for _, w in ws]
        offs, pos = [], 0
        for w in toks:
            offs.append(pos)
            pos += len(w) + 1
        out[v] = (" ".join(toks), offs, [t for t, _ in ws])
    return out


def phrase_hits(texts: dict, rx: str = PHRASE_RX) -> list:
    """[(video, t_seconds, phrase)] for every match of the alternation; t = the time of the word the match starts in."""
    r = re.compile(rx)
    out = []
    for v, (txt, offs, tim) in texts.items():
        for m in r.finditer(txt):
            i = bisect.bisect_right(offs, m.start()) - 1
            out.append((v, tim[i], m.group(0)))
    return out


def phrase_class(ph: str) -> str:
    return PHRASE_CLASS.get(ph, PHRASE_CLASS.get(ph.rstrip("s"), ""))


def caption_joins(hits: list, VS: pd.DataFrame, MG: dict, byname: dict, cal: list) -> dict:
    """§9's join rule: a phrase at t in video v; a ticker mention in v within 30 s of t; the ticker has a panel exit window with the stream's
    session s0 (the last session <= the upload date) in [exit_lo - 1, exit_hi + 2]. Two qualifying trades = ambiguous (dropped from rates)."""
    yrs, vids, near, qual, amb, trades, q_yrs = Counter(), set(), 0, 0, 0, set(), Counter()
    joins = []
    for v, t, ph in hits:
        up = VS.loc[v, "upload_date"] if v in VS.index else ""
        yrs[up[:4]] += 1
        vids.add(v)
        g = MG.get(v)
        if g is None or not up:
            continue
        ts = g["tf"].to_numpy()
        lo_, hi_ = bisect.bisect_left(ts, t - WHY_WINDOW_S), bisect.bisect_right(ts, t + WHY_WINDOW_S)
        if hi_ <= lo_:
            continue
        near += 1
        s0 = bisect.bisect_right(cal, f"{up[:4]}-{up[4:6]}-{up[6:]}") - 1
        tks = set(g["ticker"].iloc[lo_:hi_])
        quals = {b.eid: (tk, b) for tk in tks for b in byname.get(tk, ()) if b.exit_lo_i - 1 <= s0 <= b.exit_hi_i + 2}
        if quals:
            qual += 1
            q_yrs[up[:4]] += 1
            amb += int(len(quals) > 1)
            trades |= set(quals)
            joins.append(dict(video=v, t=t, phrase=ph, cls=phrase_class(ph), upload=up, s0=s0, ambiguous=len(quals) > 1,
                              eids=sorted(quals), tickers=sorted({tk for tk, _b in quals.values()})))
    return dict(hits=len(hits), videos=len(vids), yrs=dict(yrs), near=near, qual=qual, amb=amb, trades=trades, q_yrs=dict(q_yrs), joins=joins)


def load_caption_inputs() -> tuple:
    VS = pd.read_csv(FILES["video_status"], sep="\t", dtype=str, keep_default_na=False).set_index("id")
    MOM = pd.read_csv(FILES["stream_moments"], sep="\t", dtype=str, keep_default_na=False, usecols=["video", "t", "ticker"])
    MOM["tf"] = MOM["t"].astype(float)
    MG = {v: g.sort_values("tf") for v, g in MOM.groupby("video")}
    return VS, MG


# ═════════════════════════════════════════════════════════════════════════════════════════════
# minutes: the pinned trees, the new tree, coverage, the pending fetch list
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_done_all() -> tuple:
    done = {}
    done["A"], _ = rp.load_done(FILES["done_A"])
    done["B"], _ = rp.load_done(FILES["done_B"], cut=CUT_B)
    done["EP"], _ = rp.load_done(FILES["done_EP"])
    if "done_EP2" in FILES:
        done["EP2"], _ = rp.load_done(FILES["done_EP2"])
    if "done_REV" in FILES:
        done["REV"], _ = rp.load_done(FILES["done_REV"], cut=CUT_B)
    files = {k: R.minute_date_files(v) for k, v in MINUTES.items()}
    return done, files


def bar_sym(E: str, sym_a: str, sym: str) -> str:
    return sym_a if E <= A_LAST else sym


def covered_tree(E: str, tk: str, done: dict, files: dict, trees: tuple) -> "str | None":
    for tr in trees:
        if tr in done and done[tr].get((E, tk)) == "ok" and E in files[tr]:
            return tr
    return None


def minute_state(E: str, tk: str, done: dict, files: dict, trees: tuple) -> str:
    tr = covered_tree(E, tk, done, files, trees)
    if tr:
        return f"ok/{tr}"
    for t in trees:
        if t in done and done[t].get((E, tk)) == "empty":
            return f"empty/{t}"
    return "missing"


def read_minutes(E: str, tk: str, done: dict, files: dict, trees: tuple, cache: dict) -> "cb.MinuteBars | None":
    """The minute bars of (E, ticker) from the first tree whose log says ok and whose date file exists; one file read per (tree, date)."""
    tr = covered_tree(E, tk, done, files, trees)
    if tr is None:
        return None
    key = (tr, E)
    if key not in cache:
        cache[key] = R.read_minute_file(files[tr][E])[0]
    rows = cache[key].get(tk)
    if not rows:
        return None
    return R.minute_bars_from_rows(rows)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# bars: the exports (era B cut at read), raw closes, the pool floor
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_raw_close_subset(path: str, keep: set) -> dict:
    """{ticker: {date: raw close}} for `keep` from the headerless ticker,date,raw_close file (era A's measured raw close)."""
    out = defaultdict(dict)
    for ch in pd.read_csv(path, header=None, names=["t", "d", "c"], dtype={"t": str, "d": str, "c": float}, keep_default_na=False, chunksize=2_000_000):
        ch = ch[ch["t"].isin(keep)]
        for t, d, c in zip(ch["t"].tolist(), ch["d"].tolist(), ch["c"].tolist()):
            out[t][d] = c
    return out


def load_raw_flat(say, DA) -> np.ndarray:
    """Era A's measured raw close aligned to every export row (`R.load_raw_close` asserts exact coverage); on a coverage failure a tolerant
    join, the unmatched rows counted and treated as failing the $5 floor (-1)."""
    try:
        raw_flat = R.load_raw_close(FILES["raw_close_A"], DA)
        say(f"- raw closes (era A, measured) aligned to every export row ({len(raw_flat):,})")
        return raw_flat
    except AssertionError as e:
        say(f"- raw closes: exact alignment failed ({e}); falling back to a tolerant join")
        rd = load_raw_close_subset(FILES["raw_close_A"], set(DA.tickers))
        raw_flat = np.full(len(DA.ci), np.nan)
        for tk, tid in DA.tid.items():
            a, bnd = int(DA.start[tid]), int(DA.stop[tid])
            m = rd.get(tk, {})
            raw_flat[a:bnd] = [m.get(DA.cal[int(c)].isoformat(), np.nan) for c in DA.ci[a:bnd]]
        say(f"  unmatched export rows: {int(np.isnan(raw_flat).sum()):,} (treated as failing the floor)")
        return np.where(np.isnan(raw_flat), -1.0, raw_flat)


def bars_of(D, tk: str, cache: dict):
    key = (id(D), tk)
    if key not in cache:
        tid = D.tid.get(tk)
        cache[key] = R.bars_for(D, tid) if tid is not None else (None, None)
    return cache[key]


def floor_reason_from_table(T: dict, p: int) -> str:
    """§2b step 5, the ONE floor read for his picks (the fit's `pick_features` and the dry run share it): at bar p = the session before the buy
    day, (1) the buy day's bar is the very next session (the pool's adjacency rule), (2) 130 consecutive sessions end at p, (3) raw close
    >= $5, (4) the 20-session median export close x volume >= $10M. '' when every test passes."""
    if p < 0 or p >= len(T["raw"]):
        return "no_bar_on_prior_session"
    if not T["next_is_bar"][p]:
        return "no_bar_on_prior_session"
    if not T["contig130"][p]:
        return "history_lt_130"
    if not T["raw"][p] >= POOL_MIN_RAW_CLOSE:
        return "raw_close_lt_5"
    if not T["dv_med"][p] >= POOL_MIN_DV:
        return "dollar_vol_lt_10M"
    return ""


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run's load
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_core(say) -> dict:
    """Everything every stage needs: the buys, the clocks, the calendar, the types, the sets, the re-buys, the event classes."""
    buys = load_buys()
    sn = load_snapshots()
    derive_clocks(buys, sn)
    with gzip.open(FILES["calendar_cache"], "rb") as fh:
        cal_all, _sig = pickle.load(fh)
    cal = [d for d in cal_all if d <= CUT_B]
    sess_a = [ln.strip() for ln in open(FILES["sessions_A"]) if ln.strip()]
    if cal[:len(sess_a)] != sess_a:
        raise GuardStop("the calendar cache does not start with era A's sessions")
    CI = {d: i for i, d in enumerate(cal)}
    index_calendar(buys, cal)
    small, sic = load_types()
    apply_type_gate(buys, small, sic)
    n_rebuy = mark_rebuys(buys)
    EV = load_event_dates()
    ni = [b for b in buys if not b.initial]
    noev633 = [b for b in ni if b.noev and b.wl <= WINDOW_CAP and not b.flicker]
    ev_counts = classify_events_outside(noev633, EV, CI)
    dated_all = [b for b in ni if b.dated]
    mark_dated_paths([b for b in ni if b.noev], dated_all)
    S = build_sets(buys)
    say(f"- inputs: entries {len(buys):,} rows, snapshots {len(sn):,}; calendar {cal[0]}..{cal[-1]} = {len(cal):,} sessions (era A sessions.txt "
        f"{len(sess_a):,}, last {sess_a[-1]}); nothing after {CUT_B} kept; type tables {len(small):,} mi rows / {len(sic):,} SIC rows (as of 2026-10-16)")
    return dict(buys=buys, sn=sn, cal=cal, CI=CI, sess_a=sess_a, small=small, sic=sic, S=S, n_rebuy=n_rebuy, EV=EV, ev_counts=ev_counts)


def load_markets(say, keep_A: "set | None", keep_B: "set | None") -> dict:
    """The exports (era B cut at read), the unified calendar (asserted equal to the pickle calendar), QQQ / SPY stitched, the guards."""
    t0 = time.time()
    DA, infoA = rp.load_daily_subset(FILES["export_A"], keep=keep_A)
    DB, infoB = rp.load_daily_subset(FILES["export_B"], keep=keep_B, cut=CUT_B)
    say(f"- daily exports loaded in {time.time() - t0:.0f}s: era A {infoA['rows_kept']:,} of {infoA['rows_read']:,} rows ({len(DA.tickers):,} tickers, "
        f"{DA.cal[0]}..{DA.cal[-1]}); era B {infoB['rows_kept']:,} of {infoB['rows_read']:,} rows ({len(DB.tickers):,} tickers, {DB.cal[0]}..{DB.cal[-1]}), "
        f"rows dated after the cut DROPPED AT READ {infoB['dated_after_cut']:,}")
    assert DB.cal[-1].isoformat() <= CUT_B
    cal_u, map_b = H.unify_calendars(DA.cal, DB.cal)
    px = H.stitched_closes(DA, DB, cal_u, map_b)
    guards = {"A": R.load_breaks(FILES["guard_A"]), "B": R.load_breaks(FILES["guard_B"])}
    return dict(DA=DA, DB=DB, Ds={"A": DA, "B": DB}, cal_u=[d.isoformat() for d in cal_u], map_b=map_b, px=px, guards=guards)


def population_claims(say, C: dict) -> Claims:
    """Every composition claim of §2 / §2b / §6 / §8 / §10 against the doc (guard 3): the dry run prints them; every fit stage and the check
    re-run them before any bar is opened and STOP on a mismatch."""
    buys, sn, cal, CI, S = C["buys"], C["sn"], C["cal"], C["CI"], C["S"]
    claim = Claims(say)
    E = {lab: (anchor, v) for anchor, lab, v in EXPECT}

    def ck(lab, mine):
        return claim(E[lab][0], lab, E[lab][1], mine)

    ni, dec, wide, c633, c349 = S["ni"], S["dec"], S["wide"], S["c633"], S["c349"]
    say("\n## §2 — the population (the timeline as is)")
    T_init = sum(1 for b in buys if b.initial)
    ck("entries / initial / non-initial", f"{len(buys)} / {T_init} / {len(ni)}")
    ck("snapshots", len(sn))
    ck("streams", sn["vid"].nunique())
    ck("dated deciding n / names / dense / 2020 / 2021-22 / exits known",
       f"{len(dec)} / {len({b.sym for b in dec})} / {len(inwin(dec, DENSE))} / {len(inwin(dec, FIT_WIN))} / {len(inwin(dec, CHECK_WIN))} / {sum(1 for b in dec if b.has_exit)}")
    w_ex = [b for b in wide if b.has_exit]
    ck("dated window > 10: n / names / held-to-exit median / 2017-18",
       f"{len(wide)} / {len({b.sym for b in wide})} / {med_held(w_ex):.0f} / {sum(1 for b in wide if b.E[:4] in ('2017', '2018'))}")
    ck("no event non-flicker <= 10: n / names / w1 / w2 / w3-5 / w6-10",
       f"{len(c633)} / {len({b.sym for b in c633})} / {sum(1 for b in c633 if b.wl == 1)} / {sum(1 for b in c633 if b.wl == 2)} / "
       f"{sum(1 for b in c633 if 3 <= b.wl <= 5)} / {sum(1 for b in c633 if 6 <= b.wl <= 10)}")
    ck("no event flicker <= 10: n / names / one-session", f"{len(c349)} / {len({b.sym for b in c349})} / {sum(1 for b in c349 if b.wl == 1)}")
    ck("no event window > 10", len(S["noev_wide"]))
    nc = S["nc"]
    nc_types = Counter(b.sec_type for b in nc)
    funds = sum(v for k, v in nc_types.items() if k not in ADMIT_TYPES)
    other_fund = funds - nc_types.get("ETF", 0) - nc_types.get("ETV", 0) - nc_types.get("ETN", 0)
    typed_stock = sum(1 for b in nc if b.sec_type in ("CS", "ADRC"))
    untyped = sum(1 for b in nc if b.sec_type == "")
    ck("never a candidate: n / names / funds / ETF / ETV / ETN / other / typed stocks / no type row",
       f"{len(nc)} / {len({b.sym for b in nc})} / {funds} / {nc_types.get('ETF', 0)} / {nc_types.get('ETV', 0)} / {nc_types.get('ETN', 0)} / {other_fund} / {typed_stock} / {untyped}")
    vc = Counter(b.sym for b in nc)
    ck("never a candidate ETFs TQQQ / SOXL / TNA / SPXL", " / ".join(str(vc.get(s, 0)) for s in ("TQQQ", "SOXL", "TNA", "SPXL")))
    ck("no bars: n / names", f"{len(S['nb'])} / {len({b.sym for b in S['nb']})}")
    say(f"  - the seven groups sum to {len(dec) + len(wide) + len(c633) + len(c349) + len(S['noev_wide']) + len(nc) + len(S['nb'])} (non-initial {len(ni)})")
    cc = C["ev_counts"]
    ck("633 vs events outside: none / 6-20 before / 1-5 before / 1-5 after (priority) / other level inside",
       f"{cc['none']} / {cc['before_6_20']} / {cc['before_1_5']} / {cc['after_1_5']} / {cc['other_level']}")
    ck("633 with any event 1-5 after", sum(1 for b in c633 if b.fwd_event_1_5))
    yy = Counter(b.year for b in c633)
    ck("633 by buy year 2017 / 2019 / 2020 / 2021 / 2022 / 2023", " / ".join(str(yy.get(y, 0)) for y in (2017, 2019, 2020, 2021, 2022, 2023)))
    eras = Counter(b.era for b in c633)
    ent = pd.read_csv(FILES["entries"], sep="\t", dtype=str, keep_default_na=False, usecols=["eid", "q1_2022_hole"]).set_index("eid")["q1_2022_hole"]
    ck("633 era A / B; touch the Q1-2022 hole", f"{eras.get('A', 0)} / {eras.get('B', 0)}; {sum(1 for b in c633 if ent.get(str(b.eid)) == 'True')}")
    ex_nf, ex_all = S["ex_nf"], S["ex_all"]
    ck("one-session non-flicker: all / exits known / inverted / dense / 2020 / 2021-22 / trade-days / to first / median",
       f"{len(ex_nf)} / {sum(1 for b in ex_nf if b.has_exit)} / {sum(1 for b in ex_nf if b.inverted)} / {len(inwin(ex_nf, DENSE))} / {len(inwin(ex_nf, FIT_WIN))} / "
       f"{len(inwin(ex_nf, CHECK_WIN))} / {tdays(ex_nf)} / {tdays(ex_nf, True)} / {med_held(ex_nf):.0f}")
    ck("one-session incl flickers: all / flickers / left by close / inverted / dense / 2020 / 2021-22 / trade-days dense / median",
       f"{len(ex_all)} / {sum(1 for b in ex_all if b.flicker)} / {sum(1 for b in ex_all if b.has_exit and b.exit_hi_i == b.Ei)} / {sum(1 for b in ex_all if b.inverted)} / "
       f"{len(inwin(ex_all, DENSE))} / {len(inwin(ex_all, FIT_WIN))} / {len(inwin(ex_all, CHECK_WIN))} / {tdays(inwin(ex_all, DENSE))} / {med_held(ex_all):.0f}")
    ck("dated deciding: n / exits / same-day exits / flickers / dense / 2020 / 2021-22 / trade-days / to first / median",
       f"{len(dec)} / {sum(1 for b in dec if b.has_exit)} / {sum(1 for b in dec if b.has_exit and b.exit_hi_i == b.Ei)} / {sum(1 for b in dec if b.flicker)} / "
       f"{len(inwin(dec, DENSE))} / {len(inwin(dec, FIT_WIN))} / {len(inwin(dec, CHECK_WIN))} / {tdays(dec)} / {tdays(dec, True)} / {med_held(dec):.0f}")
    # ---- clocks
    say("\n## §2 — the clock on the buy day (one derivation for every row, from the stored frames)")
    dw = inwin(dec, DENSE)
    fcn = [b for b in dw if b.first_clock]
    fl = [b for b in dw if b.flat_clock]
    both = [b for b in dw if b.first_clock and b.flat_clock]
    br = [b for b in dw if b.in_bracket]
    ck("dated in window: first seen in session / flat frame (in, pre) / both / both in-session (2020, 2021-22)",
       f"{len(fcn)} / {len(fl)} ({sum(1 for b in fl if b.p_ctx == 'in')}, {sum(1 for b in fl if b.p_ctx == 'pre')}) / {len(both)} / {len(br)} "
       f"({len(inwin(br, FIT_WIN))}, {len(inwin(br, CHECK_WIN))})")
    w = np.array([bracket_width(b) for b in br], dtype=float)
    ck("dated in-session bracket width: median / q25 / q75 / <= 30 min", f"{np.median(w):g} / {np.percentile(w, 25):g} / {np.percentile(w, 75):g} / {int((w <= 30).sum())}")
    ck("dated: pre-market-flat brackets / no flat frame that day / held before 09:35",
       f"{sum(1 for b in dw if b.pre_flat_bracket)} / {sum(1 for b in dw if b.first_clock and not b.flat_clock)} / {sum(1 for b in dw if b.held_before_0935)}")
    ck("held before 09:35 (dated in window)", ", ".join(f"{b.sym} {b.E}" for b in sorted((b for b in dw if b.held_before_0935), key=lambda x: (x.E, x.sym))))
    un = inwin(ex_nf, DENSE)
    u_f = [b for b in un if b.first_clock]
    u_b = [b for b in un if b.in_bracket]
    wu = np.array([bracket_width(b) for b in u_b], dtype=float)
    ck("one-session no-event (window): first seen in session (2020, 2021-22) / flat frame that day",
       f"{len(u_f)} ({len(inwin(u_f, FIT_WIN))}, {len(inwin(u_f, CHECK_WIN))}) / {sum(1 for b in u_f if b.flat_clock)}")
    h935 = [b for b in un if b.held_before_0935]
    ck("one-session no-event: in-session brackets (2020, 2021-22) / median / q25 / q75 / pre-market-flat / held before 09:35",
       f"{len(u_b)} ({len(inwin(u_b, FIT_WIN))}, {len(inwin(u_b, CHECK_WIN))}) / {np.median(wu):g} / {np.percentile(wu, 25):g} / {np.percentile(wu, 75):g} / "
       f"{sum(1 for b in un if b.pre_flat_bracket)} / {len(h935)} ({', '.join(f'{b.sym} {b.E}' for b in h935)})")
    ua = inwin(ex_all, DENSE)
    ua_b = [b for b in ua if b.in_bracket]
    wa = np.array([bracket_width(b) for b in ua_b], dtype=float)
    ck("one-session no-event with flickers: in-session brackets (2020, 2021-22) / median", f"{len(ua_b)} ({len(inwin(ua_b, FIT_WIN))}, {len(inwin(ua_b, CHECK_WIN))}) / {np.median(wa):g}")
    match = sum(1 for b in dw if b.stored_first_clock == b.first_clock and b.stored_flat_clock == b.flat_clock)
    und_filled = sum(1 for b in ni if not b.dated and (b.stored_first_clock or b.stored_flat_clock))
    ck("stored clock columns: dated in window matching the derivation / undated rows filled", f"{match} / {und_filled}")
    # guard (8)
    mis = clock_misreads(sn)
    ck("guard (8): clock reads off the fitted clock by > 2 min: n / all 2019", f"{len(mis)} / {all(d.startswith('2019') for d, _o in mis.values())}")
    fit_chk = inwin([b for b in S["dec_used"] + S["und_fit"] + S["und_chk"] + S["sel_fit"] + S["sel_chk"] if b.in_bracket or b.pre_flat_bracket], DENSE)
    bad_frames = [(b.eid, fr) for b in fit_chk for fr in (b.first_frame, b.prev_full_frame) if fr in mis]
    say(f"  - bracket frames of fit / check trades with a misread clock: {len(bad_frames)} (asserted 0)")
    if bad_frames:
        claim.bad.append((doc_line_of("the 21 misread clocks are all 2019"), "misread clock on a fit / check bracket frame", 0, bad_frames))
    # ---- re-buys
    say("\n## §2 — re-buys")
    cnt = Counter(b.sym for b in buys)
    ck("re-buys: names with > 1 entry / of 684 / their entries (non-initial)",
       f"{sum(1 for v in cnt.values() if v > 1)} / {len(cnt)} / {sum(1 for b in ni if cnt[b.sym] > 1)}")
    rb = [b for b in buys if b.rebuy]
    ry = Counter(b.lo[:4] for b in rb)
    ck("re-buy (0-14 days after the previous non-initial entry's exit_hi): n / 2020 / 2021 / 2019 / 2022 / deciding / undated",
       f"{len(rb)} / {ry.get('2020', 0)} / {ry.get('2021', 0)} / {ry.get('2019', 0)} / {ry.get('2022', 0)} / {sum(1 for b in rb if b.decides)} / {sum(1 for b in rb if b.setup == 'undated')}")
    sd_dec = sorted(b.sym for b in dec if b.same_day_rebuy)
    ck("same-day re-buys in the 427 / the 700 / the dated 294",
       f"{sum(1 for b in ex_nf if b.same_day_rebuy)} / {sum(1 for b in ex_all if b.same_day_rebuy)} / {sum(1 for b in dec if b.same_day_rebuy)} ({', '.join(sd_dec)})")
    # ---- §2b
    say("\n## §2b — the sets used (type gate -> inverted -> same-day re-buys, in that order)")
    ck("§2b 633: type / inverted / same-day / used / one-session / 2-10",
       f"{S['n633_type']} / {S['n633_inv']} / {S['n633_sd']} / {len(S['used_633'])} / {sum(1 for b in S['used_633'] if b.wl == 1)} / {len(S['multi_used'])}")
    tc = Counter(b.sym for b in S["type_out_633"])
    top = [(s, n) for s, n in tc.most_common() if n >= 2]
    ones = sum(1 for s, n in tc.items() if n == 1)
    ck("§2b type removals", ", ".join(f"{s} {n}" for s, n in sorted(top, key=lambda x: (-x[1], x[0]))) + f", {ones} others 1 each")
    ck("SELECT fit 2020: 197 - type - inverted - same-day = used / never-a-candidate adds / flickers beside",
       f"{len(inwin(ex_nf, FIT_WIN))} - {S['nfit_type']} - {S['nfit_inv']} - {S['nfit_sd']} = {len(S['sel_fit'])} / {len(S['sel_fit_nc'])} / {len(S['sel_fit_flick'])}")
    ck("SELECT check 2021-22: 177 - type - inverted - same-day = used / adds / flickers beside",
       f"{len(inwin(ex_nf, CHECK_WIN))} - {S['nchk_type']} - {S['nchk_inv']} - {S['nchk_sd']} = {len(S['sel_chk'])} / {len(S['sel_chk_nc'])} / {len(S['sel_chk_flick'])}")
    ck("SELECT beside 2017 / 2019 / 2023 before -> after",
       " / ".join(str(len(S["sel_beside_before"][y])) for y in (2017, 2019, 2023)) + " -> " + " / ".join(str(len(S["sel_beside"][y])) for y in (2017, 2019, 2023)))
    ck("STOP/EXIT undated fit 2020: 335 - type - inverted - same-day = used / trade-days / non-flicker",
       f"{len(inwin(ex_all, FIT_WIN))} - {S['nuf_type']} - {S['nuf_inv']} - {S['nuf_sd']} = {len(S['und_fit'])} / {tdays(S['und_fit'])} / {sum(1 for b in S['und_fit'] if not b.flicker)}")
    ck("STOP/EXIT undated check 2021-22: 280 - type - inverted - same-day = used / trade-days / non-flicker",
       f"{len(inwin(ex_all, CHECK_WIN))} - {S['nuc_type']} - {S['nuc_inv']} - {S['nuc_sd']} = {len(S['und_chk'])} / {tdays(S['und_chk'])} / {sum(1 for b in S['und_chk'] if not b.flicker)}")
    ck("dated deciding: 294 - type - inverted - same-day = used / known exits / 2020 / 2021-22",
       f"{len(dec)} - {S['ndec_type']} - {S['ndec_inv']} - {S['ndec_sd']} = {len(S['dec_used'])} / {sum(1 for b in S['dec_used'] if b.has_exit)} / "
       f"{len(inwin(S['dec_used'], FIT_WIN))} / {len(inwin(S['dec_used'], CHECK_WIN))}")
    ck("dated type removals", ", ".join(f"{b.sym} {b.E}" for b in sorted(S["type_out_dec"], key=lambda x: x.E)))
    ck("held before 09:35 after the type gate: dated + undated", f"{sum(1 for b in inwin(S['dec_used'], DENSE) if b.held_before_0935)} + {sum(1 for b in S['sel_fit'] + S['sel_chk'] if b.held_before_0935)}")
    ck("never-a-candidate stocks (typed CS/ADRC or untyped) re-entering SELECT", len(S["nc_stocks"]))
    notype = {k: sum(1 for b in S[k] if b.sec_type == "") for k in ("sel_fit", "sel_chk", "und_fit", "und_chk", "dec_used")}
    say(f"  - no-type-row buys inside the used sets (flagged; every SELECT number is also printed without them): {notype}")
    # ---- ENTER's sets
    say("\n## §6 — ENTER's sets (in-session brackets after §2b)")
    ck("ENTER fit: in-session brackets dated + undated (with flickers) / check",
       f"{len(S['ent_fit_dated'])} + {len(S['ent_fit_und'])} ({len(S['ent_fit_und_fl'])}) / {len(S['ent_chk_dated'])} + {len(S['ent_chk_und'])} ({len(S['ent_chk_und_fl'])})")
    ck("ENTER beside after §2b: pre-market-flat brackets dated / undated non-flicker; dated no flat frame; dated pre-market first sightings / of",
       f"{len(S['ent_pre_dated'])} / {len(S['ent_pre_und'])}; {len(S['ent_noflat_dated'])}; {len(S['ent_prefirst_dated'])} / {len(S['dec_used_dense'])}")
    # ---- §8 flicker share, §10
    say("\n## §8 / §10 — flicker shares, the walked paths, the forward events")
    fit_ex = S["exit_fit"]
    ck("EXIT flicker share: fit / dated / undated / check (%); name-confirmed share of the fit (%)",
       f"{round(100 * np.mean([b.flicker for b in fit_ex]))} / {round(100 * np.mean([b.flicker for b in S['exit_fit_dated']]))} / "
       f"{round(100 * np.mean([b.flicker for b in S['und_fit']]))} / {round(100 * np.mean([b.flicker for b in S['und_chk']]))}; {round(100 * len(S['exit_fit_dated']) / len(fit_ex))}")
    chk280, chk177 = inwin(ex_all, CHECK_WIN), inwin(ex_nf, CHECK_WIN)
    ck("§10 check buys inside a dated trade's 121-session path: of 280 / of 177 nf / of 226 / of 145 nf; fit side of 335",
       f"{sum(1 for b in chk280 if b.in_dated_path)} / {sum(1 for b in chk177 if b.in_dated_path)} / {sum(1 for b in S['und_chk'] if b.in_dated_path)} / "
       f"{sum(1 for b in S['exit_chk_nf'] if b.in_dated_path)}; {sum(1 for b in inwin(ex_all, FIT_WIN) if b.in_dated_path)}")
    a77 = [b for b in c633 if b.event_class == "after_1_5"]
    a126 = [b for b in c633 if b.fwd_event_1_5]

    def split_fc(bs):
        f, c = len(inwin(bs, FIT_WIN)), len(inwin(bs, CHECK_WIN))
        return f"{f} / {c} / {len(bs) - f - c}"
    ck("§10 forward events: the 77 by fit / check / other; the 126; of the 177 nf check buys", f"{split_fc(a77)}; {split_fc(a126)}; {sum(1 for b in chk177 if b.fwd_event_1_5)}")
    olf, olc = S["other_level_fit"], S["other_level_chk"]
    yf = Counter(b.year for b in olf)
    ck("§5b the 47 other-level buys: fit (2019 / 2020 / 2023) / check (SELECT check buys + windows); 2022",
       f"{len(olf)} ({yf[2019]} / {yf[2020]} / {yf[2023]}) / {len(olc)} ({sum(1 for b in olc if 'sel_chk' in b.sets)} + {sum(1 for b in olc if b.wl >= 2)}); "
       f"{sum(1 for b in S['other_level_47'] if b.year == 2022)}")
    return claim


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run
# ═════════════════════════════════════════════════════════════════════════════════════════════
def dry_run(say) -> int:
    say("# #705 REVERSE 01 — DRY RUN: every input loaded, every composition count asserted against the registration, the clock columns written for "
        "every row, the caption chain, the data gate, the pins. NO outcome: no bar after a buy day, no stop / exit / R / return, no fit.")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    check_pinned_inputs(say)
    C = load_core(say)
    buys, sn, cal, CI, S = C["buys"], C["sn"], C["cal"], C["CI"], C["S"]
    claim = population_claims(say, C)
    E = {lab: (anchor, v) for anchor, lab, v in EXPECT}

    def ck(lab, mine):
        return claim(E[lab][0], lab, E[lab][1], mine)

    ni, dec, ex_nf, ex_all = S["ni"], S["dec"], S["ex_nf"], S["ex_all"]
    # ---- captions
    say("\n## §2 / §9 — the caption chain (the pinned alternation; qmlib.parse_vtt; his words, never a source)")
    paths = sorted(glob.glob(SUBS_GLOB))
    ck("captions: vtt files", len(paths))
    t0 = time.time()
    texts = load_caption_texts(paths)
    say(f"  - {len(texts)} videos parsed in {time.time() - t0:.0f}s, {sum(len(t[2]) for t in texts.values()):,} words")
    VS, MG = load_caption_inputs()
    byname = defaultdict(list)
    for b in ni:
        if b.has_exit:
            byname[b.sym].append(b)
            if b.sym_a != b.sym:
                byname[b.sym_a].append(b)
    hits = phrase_hits(texts)
    J = caption_joins(hits, VS, MG, byname, cal)
    yrs = J["yrs"]
    ck("alternation: hits / videos / 2020 / 2021 / 2017 / 2019 / 2022 / 2023 / 2018",
       f"{J['hits']} / {J['videos']} / " + " / ".join(str(yrs.get(y, 0)) for y in ("2020", "2021", "2017", "2019", "2022", "2023", "2018")))
    forms = {k: sum(len(re.compile(rx).findall(t[0])) for t in texts.values()) for k, rx in SINGLE_FORMS.items()}
    ck("single forms: i sold / stopped out / i got stopped / stopped me out", " / ".join(str(forms[k]) for k in ("i sold", "stopped out", "i got stopped", "stopped me out")))
    dec_eids = {b.eid for b in dec}
    ck("within 30 s of a ticker / qualifying (2020, 2021) / trades / deciding / ambiguous",
       f"{J['near']} / {J['qual']} ({J['q_yrs'].get('2020', 0)}, {J['q_yrs'].get('2021', 0)}) / {len(J['trades'])} / {len(J['trades'] & dec_eids)} / {J['amb']}")
    cls = Counter(j["cls"] for j in J["joins"] if not j["ambiguous"])
    say(f"  - unambiguous joins by class: {dict(cls)}; 2020 unambiguous joins by class: {dict(Counter(j['cls'] for j in J['joins'] if not j['ambiguous'] and j['upload'].startswith('2020')))} (the hand-read sample is drawn in --check)")
    # ---- minutes
    say("\n## §12 — the data gate: minute coverage (fetch logs and date files only; no minute file opened)")
    done, files = load_done_all()
    pinned_trees = tuple(t for t in ("A", "B", "EP", "EP2") if t in done)
    all_trees = pinned_trees + (("REV",) if "REV" in done else ())
    say(f"  - fetch logs: " + ", ".join(f"{k} {len(v):,}" for k, v in done.items()) + "; date files " + ", ".join(f"{k} {len(v):,}" for k, v in files.items())
        + ("" if "REV" in done else "; the new tree minutes_rev_1024 has NO _done.psv yet (the fetch has not happened)"))
    cov_dec = {b.eid: covered_tree(b.E, b.ticker, done, files, (("EP", "EP2", "A", "B") if b.setup == "EP" else ("A", "B", "EP", "EP2"))) for b in dec}
    miss_dec = [b for b in dec if cov_dec[b.eid] is None]
    ck("§12 deciding with minute bars on E (four trees) / missing", f"{len(dec) - len(miss_dec)} of {len(dec)} / " + ", ".join(f"{b.sym} {b.E}" for b in sorted(miss_dec, key=lambda x: x.E)))
    cov4 = {b.eid: covered_tree(b.E, bar_sym(b.E, b.sym_a, b.sym), done, files, pinned_trees) for b in ex_all + S["multi_nf"]}
    miss_nf = [b for b in ex_nf if cov4[b.eid] is None]
    my = Counter(b.year for b in miss_nf)
    ck("§12 one-session no-event 427: covered (four trees) / missing / by year 2020 2021 2019 2022 2023 2017",
       f"{len(ex_nf) - len(miss_nf)} / {len(miss_nf)} / " + " ".join(str(my.get(y, 0)) for y in (2020, 2021, 2019, 2022, 2023, 2017)))
    fl_ex = [b for b in ex_all if b.flicker]
    sess_rows = [(b, cal[i]) for b in S["multi_nf"] for i in range(b.lo_i, b.hi_i + 1)]
    cov_sess = [covered_tree(d, bar_sym(d, b.sym_a, b.sym), done, files, pinned_trees) for b, d in sess_rows]
    ck("§12 273 flickers covered / 206 multi windows: sessions / covered",
       f"{sum(1 for b in fl_ex if cov4[b.eid])} / {len(sess_rows)} / {sum(1 for x in cov_sess if x)}")
    # the fetch list as the doc pins it
    fl_pairs = [ln.rstrip("\n").split("|") for ln in open(FILES["fetch_list"]) if ln.strip()]
    fl_set = {(t, d) for t, d in fl_pairs}
    kinds = {}
    for b in ex_all:
        kinds.setdefault((bar_sym(b.E, b.sym_a, b.sym), b.E), "exact_flicker" if b.flicker else "exact_nf")
        if not b.flicker:
            kinds[(bar_sym(b.E, b.sym_a, b.sym), b.E)] = "exact_nf"
    for b, d in sess_rows:
        kinds.setdefault((bar_sym(d, b.sym_a, b.sym), d), "window_session")
    kc = Counter(kinds.get(p, "unknown") for p in fl_set)
    fy = Counter(d[:4] for _t, d in fl_set)
    ck("§12 fetch list: pairs / sha prefix / latest / kinds nf flicker window / years 2017 2019 2020 2021 2022 2023",
       f"{len(fl_set)} / {sha(FILES['fetch_list'])[:8]} / {max(d for _t, d in fl_set)} / {kc['exact_nf']} {kc['exact_flicker']} {kc['window_session']} / "
       + " ".join(str(fy.get(y, 0)) for y in ("2017", "2019", "2020", "2021", "2022", "2023")))
    ent_fit_d = sum(1 for b in S["ent_fit_dated"] if cov_dec[b.eid])
    ent_fit_u = sum(1 for b in S["ent_fit_und"] if cov4[b.eid])
    ent_chk_d = sum(1 for b in S["ent_chk_dated"] if cov_dec[b.eid])
    ent_chk_u = sum(1 for b in S["ent_chk_und"] if cov4[b.eid])
    ck("§12 ENTER scorable on the four pinned trees alone (pre-fetch): fit dated + undated / check", f"{ent_fit_d} + {ent_fit_u} / {ent_chk_d} + {ent_chk_u}")
    # with the new tree (fetched 2026-10-24 with the operator's permission; `_done.psv` pinned as done_REV)
    pending = []
    if "REV" in done:
        st = Counter()
        for t, d in sorted(fl_set, key=lambda x: (x[1], x[0])):
            s_ = minute_state(d, t, done, files, all_trees)
            st[s_.split("/")[0]] += 1
            if s_ == "missing":
                pending.append((t, d))
        extra = set(k for k in done["REV"]) - {(d, t) for t, d in fl_set}
        ck("§12 the new tree minutes_rev_1024: fetch-list pairs ok / empty / still missing; rows not on the list", f"{st['ok']} / {st['empty']} / {st['missing']}; {len(extra)}")
        empties = sorted((t, d) for t, d in fl_set if minute_state(d, t, done, files, all_trees).startswith("empty"))
        ck("§12 the 20 empty pairs", ", ".join(f"{t} {d}" for t, d in empties))
        emp_set = set(empties)
        in_sets = Counter()
        for b in ex_all:
            if (bar_sym(b.E, b.sym_a, b.sym), b.E) in emp_set:
                for k_ in ("sel_fit", "sel_chk", "und_fit", "und_chk", "ent_fit_und", "ent_chk_und", "ent_fit_und_fl", "ent_chk_und_fl"):
                    in_sets[k_] += int(k_ in b.sets)
        for b_, d_ in sess_rows:
            if (bar_sym(d_, b_.sym_a, b_.sym), d_) in emp_set:
                in_sets["window_session"] += 1
        say(f"  - the empty pairs by set (each abstains `no_minutes`, counted): " + (", ".join(f"{k} {v}" for k, v in sorted(in_sets.items())) or "none in a used set"))
        cov5 = {b.eid: covered_tree(b.E, bar_sym(b.E, b.sym_a, b.sym), done, files, all_trees) for b in ex_all + S["multi_nf"]}
        cov5s = [covered_tree(d, bar_sym(d, b.sym_a, b.sym), done, files, all_trees) for b, d in sess_rows]
        ck("§12 coverage with the new tree: one-session non-flicker / flickers / window sessions",
           f"{sum(1 for b in ex_nf if cov5[b.eid])} of {len(ex_nf)} / {sum(1 for b in fl_ex if cov5[b.eid])} of {len(fl_ex)} / {sum(1 for x in cov5s if x)} of {len(sess_rows)}")
        ck("§12 ENTER set members with minute bars, five trees: fit dated + undated (with flickers) / check",
           f"{sum(1 for b in S['ent_fit_dated'] if cov_dec[b.eid])} + {sum(1 for b in S['ent_fit_und'] if cov5[b.eid])} ({sum(1 for b in S['ent_fit_und_fl'] if cov5[b.eid])}) / "
           f"{sum(1 for b in S['ent_chk_dated'] if cov_dec[b.eid])} + {sum(1 for b in S['ent_chk_und'] if cov5[b.eid])} ({sum(1 for b in S['ent_chk_und_fl'] if cov5[b.eid])})")
    else:
        pending = sorted(fl_set, key=lambda x: (x[1], x[0]))
        say("  - the new tree minutes_rev_1024 has NO _done.psv: the §12 post-fetch claims cannot be read (MISMATCH by construction)")
        for lab in ("§12 the new tree minutes_rev_1024: fetch-list pairs ok / empty / still missing; rows not on the list", "§12 the 20 empty pairs",
                    "§12 coverage with the new tree: one-session non-flicker / flickers / window sessions", "§12 ENTER set members with minute bars, five trees: fit dated + undated (with flickers) / check"):
            ck(lab, "tree absent")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(f"{OUT_DIR}/dryrun_fetch_pending.psv", "w") as fh:
        for t, d in pending:
            fh.write(f"{t}|{d}\n")
    say(f"  - PENDING fetch pairs (on the list, in no tree): {len(pending)} -> {OUT_DIR}/dryrun_fetch_pending.psv")
    # ---- the pool floor on his buys (§2b step 5): the SAME path the SELECT fit runs — the record builder first, then the pool floor read from the
    # feature table (adjacency of the prior session, 130 consecutive sessions, raw close >= $5, export close x volume >= $10M); bars up to the buy day only
    say(f"\n## §2b step 5 — his buys against the pool's own floor on the session before the buy day (raw close >= $5; 20-session median export close x export volume "
        f">= $10M, split-invariant; 130 consecutive sessions; the prior session adjacent to the buy day), after the record builder (in the export, a bar on the buy day, "
        f">= {REC_MIN_BARS} bars before it)")
    need_A = {b.ticker for b in ni if b.has_bars and select_era_of(b.E) == "A"} | {b.sym_a for b in ni if b.has_bars} | {"QQQ", "SPY"}
    need_B = {b.sym for b in ni if b.has_bars and b.E > A_LAST} | {"QQQ", "SPY"}
    M = load_markets(say, need_A, need_B)
    if M["cal_u"] != cal:
        raise GuardStop("the unified export calendar differs from the pickle calendar")
    say(f"  - unified export calendar == the pickle calendar ({len(cal):,} sessions); QQQ / SPY stitched (overlap within 0.5%)")
    raw = load_raw_close_subset(FILES["raw_close_A"], set(M["DA"].tickers))
    say(f"  - raw closes (era A, measured): {sum(len(v) for v in raw.values()):,} rows for {len(raw):,} of his names (a row the raw file lacks fails the $5 test, as the fit's tolerant join does)")
    cache, tcache = {}, {}

    def floor_of(b: Buy) -> str:
        era = select_era_of(b.E)
        D = M["Ds"][era]
        tk = b.sym_a if era == "A" else b.sym
        why = rec_drop_reason(b, M, era, cache)
        if why is not None:
            return why
        bars, cidx = bars_of(D, tk, cache)
        e_ci = bisect.bisect_left(D.cal, date.fromisoformat(b.E))
        e = int(np.searchsorted(cidx, e_ci))
        rc = None
        if era == "A":
            rd = raw.get(tk, {})
            rc = np.array([rd.get(d.isoformat(), -1.0) for d in bars.dates], dtype=float)
        key = (id(bars), era)
        if key not in tcache:
            tcache[key] = ticker_feature_table(bars, cidx, rc, {})
        return floor_reason_from_table(tcache[key], e - 1)
    passes = {}
    for name in ("sel_fit", "sel_chk", "sel_fit_nc", "sel_chk_nc", "sel_fit_flick", "sel_chk_flick"):
        res = Counter(floor_of(b) or "passes" for b in S[name])
        passes[name] = res["passes"]
        say(f"  - {name}: {len(S[name])} -> passes {res['passes']}; loses " + (", ".join(f"{k} {v}" for k, v in sorted(res.items()) if k != "passes") or "none"))
    ck("§2b step 5: fit 188 -> passes / check 145 -> passes / never-a-candidate 12 -> / 15 -> / flickers 116 -> / 81 ->",
       " / ".join(str(passes[k]) for k in ("sel_fit", "sel_chk", "sel_fit_nc", "sel_chk_nc", "sel_fit_flick", "sel_chk_flick")))
    # ---- what the stages' record builder would drop from the FIXED sets (bars up to the buy day only; a population change at run time otherwise)
    say(f"\n## The stages' record builder on the fixed sets (needs the era's export, a bar on the buy day, >= {REC_MIN_BARS} bars before it — ENTER >= {REC_MIN_BARS_ENTER}; R10 era)")
    bc2 = {}
    nrec = {}
    for name in ("dec_used", "und_fit", "und_chk", "multi_used", "ent_fit_dated", "ent_fit_und", "ent_chk_dated", "ent_chk_und", "exit_fit_dated"):
        mb_ = REC_MIN_BARS_ENTER if name.startswith("ent_") else REC_MIN_BARS
        reasons = Counter(rec_drop_reason(b, M, era_of(b.E), bc2, mb_) or "record" for b in S[name])
        nrec[name] = reasons["record"]
        say(f"  - {name}: {len(S[name])} -> records {reasons['record']}; dropped " + (", ".join(f"{k} {v}" for k, v in sorted(reasons.items()) if k != "record") or "none"))
    ck("§13 records: dated 290 -> / undated fit 304 -> / undated check 226 -> / windows 187 -> / ENTER fit 32 + 59 -> / check 20 + 44 -> / EXIT dated 286 ->",
       f"{nrec['dec_used']} / {nrec['und_fit']} / {nrec['und_chk']} / {nrec['multi_used']} / {nrec['ent_fit_dated']} + {nrec['ent_fit_und']} / {nrec['ent_chk_dated']} + {nrec['ent_chk_und']} / {nrec['exit_fit_dated']}")
    # ---- guard (5), first half, on the REAL fit sets (Buy fields only, outcome-free): the registered predicates must admit every registered fit buy
    say("\n## Guard (5) on the real fit sets: every registered fit buy passes its stage's fit-set predicate (a violation here would STOP the first stage after the freeze)")
    fit_sets = {"select": S["sel_fit"] + S["sel_fit_nc"], "enter": S["ent_fit_dated"] + S["ent_fit_und"], "stop": S["stop_fit_dated"] + S["und_fit"], "exit": S["exit_fit"]}
    viol = {st: [(b.eid, b.sym, b.E, fit_set_violation(st, b)) for b in bs if fit_set_violation(st, b)] for st, bs in fit_sets.items()}
    for st, v in viol.items():
        if v:
            say(f"  - {st.upper()}: {len(v)} violation(s): " + "; ".join(f"{sy} {e} eid {i}: {w}" for i, sy, e, w in v[:5]))
    ck("guard (5): the four fit sets on the real buys: SELECT / ENTER / STOP / EXIT buys; violations",
       " / ".join(str(len(fit_sets[st])) for st in ("select", "enter", "stop", "exit")) + f"; {sum(len(v) for v in viol.values())}")
    # ---- the size of SELECT's same-day pools (fit days full; every other day light): a cost line, outcome-free (days only)
    fit_days = {CI[b.E] for b in fit_sets["select"]}
    other_days = set()
    for b in S["sel_fit_flick"] + S["other_level_fit"] + S["sel_beside"][2017] + S["sel_beside"][2019] + S["dec_used"]:
        if b.E <= A_EXPORT_LAST:
            other_days.add(CI[b.E])
    win_days = set()
    for b in S["multi_used"] + S["wide"]:
        if b.E <= A_EXPORT_LAST:
            win_days |= set(range(b.lo_i, b.hi_i + 1))
    other_days = (other_days | win_days) - fit_days
    say(f"  - SELECT's pools: full rows on {len(fit_days)} fit days; light rows (returns only) on {len(other_days)} other days, of which window sessions "
        f"{len(win_days - fit_days)} ({len([b for b in S['wide'] if b.E <= A_EXPORT_LAST])} dated-but-wider windows contribute "
        f"{len(set().union(*[set(range(b.lo_i, b.hi_i + 1)) for b in S['wide'] if b.E <= A_EXPORT_LAST]) - fit_days)} of them); check days {len({CI[b.E] for b in S['sel_chk'] + S['sel_chk_nc']})}")
    # ---- walkability under the holdings wiring (outcome-free: `ex.history_reason` reads calendar indices up to the buy day only; check L4)
    say("\n## Walkability of the used-set buys under the holdings wiring (`ex.history_reason`: a bar on the buy day, 130 consecutive sessions ending there, the prior bar = the session before)")
    used = {b.eid: b for k in ("dec_used", "und_fit", "und_chk", "sel_fit", "sel_chk", "sel_fit_nc", "sel_chk_nc", "multi_used") for b in S[k]}
    tally = Counter()
    for b in used.values():
        era = era_of(b.E)
        D = M["Ds"][era]
        bars, cidx = bars_of(D, b.sym_a if era == "A" else b.sym, bc2)
        if bars is None:
            tally["ticker_not_in_export"] += 1
            continue
        ns = SimpleNamespace(E=b.E, D=cal[b.Ei - 1] if b.Ei > 0 else "")
        tally[ex.history_reason(ns, bars, cidx, D.cal) or "walkable"] += 1
    say("  - used-set rows: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
    # ---- the clock table
    rows = [dict(eid=b.eid, sym=b.sym, sym_a=b.sym_a, setup=b.setup, E=b.E, era=b.era, first_clock_on_E=b.first_clock, flat_clock_on_E=b.flat_clock,
                 flat_ctx=b.p_ctx, first_ctx=b.f_ctx, in_session_bracket=b.in_bracket, pre_market_flat_bracket=b.pre_flat_bracket,
                 bracket_minutes=bracket_width(b) if (b.in_bracket or b.pre_flat_bracket) else "", held_before_0935=b.held_before_0935,
                 sec_type=b.sec_type, type_src=b.type_src, type_ok=b.type_ok, inverted=b.inverted, same_day_rebuy=b.same_day_rebuy, rebuy=b.rebuy,
                 in_dated_path=b.in_dated_path, event_class=b.event_class, sets=";".join(sorted(b.sets))) for b in ni]
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/dryrun_clocks.tsv", sep="\t", index=False)
    say(f"\n- clock columns written for every non-initial row ({len(rows)}) -> {OUT_DIR}/dryrun_clocks.tsv (outcome-free; never refuses a run)")
    # ---- pins
    p = pins()
    say("\n## Pins (sha256) — every value below goes under the doc's freeze marker line before the check (fit printouts and the ledger once they exist)")
    for k, v in p.items():
        say(f"- {k}: {v}")
    miss = freeze_missing(DOC, p)
    say(f"- freeze record: {'every pin above is written under the freeze marker line' if not miss else 'NOT YET under the freeze marker line: ' + str(len(miss)) + ' pins'}")
    ch = chosen_lines()
    say(f"- CHOSEN lines above the marker: " + (", ".join(f"{k} {len(v)}" for k, v in sorted(ch.items())) if ch else "none"))
    say(f"\n## RESULT: {claim.n} claims, {claim.n - len(claim.bad)} OK, {len(claim.bad)} MISMATCH")
    for ln, lab, doc, mine in claim.bad:
        say(f"  MISMATCH [L{ln}] {lab}: doc {fmt_claim(doc)} vs mine {fmt_claim(mine)}")
    if claim.bad:
        say("STOPPED: the dry run does not reproduce the registration (amend the doc or the derivation before the freeze)")
        return 3
    say("\nDRY RUN COMPLETE: every composition count reproduced; no minute file opened, no bar after a buy day read, no outcome computed.")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap_.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--select-fit", action="store_true")
    g.add_argument("--enter-fit", action="store_true")
    g.add_argument("--stop-fit", action="store_true")
    g.add_argument("--exit-fit", action="store_true")
    g.add_argument("--print-pins", "--pins", action="store_true", dest="print_pins")
    g.add_argument("--check", action="store_true")
    g.add_argument("--why-rates", action="store_true")
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
    from importlib import import_module  # noqa: F401  (the stages live below; nothing to import)
    for flag, stage in (("select_fit", "select"), ("enter_fit", "enter"), ("stop_fit", "stop"), ("exit_fit", "exit")):
        if getattr(args, flag):
            return run_fit_stage(stage, say)
    if args.check:
        return run_check(say)
    if args.why_rates:
        return run_why_rates(say)
    return 1


# ═════════════════════════════════════════════════════════════════════════════════════════════
# shared stage machinery: the forward-bar guard, bars + minutes per trade, the chain's fill and stop, G8, the chosen-object files
# ═════════════════════════════════════════════════════════════════════════════════════════════
class BarGuard:
    """Guard (5): a fit stage opens no bar after the buy day of any trade outside ITS OWN registered fit set. Each record carries its own
    horizon: unbounded for a trade in `allowed_eids` (the stage's fit set — the dated 2021-22 trades in the EXIT fit are in-sample by
    registration, §10), its buy day only (horizon 0) for every other trade. `allowed_eids=None` = the check: every forward bar may be read.
    Belt: an UNDATED buy inside the check window is refused by every fit stage whatever the set says — no undated 2021-22 trade is fit
    material in any stage (check H1: the old guard was a DATE limit that stopped the exit fit on its first dated 2021 trade)."""

    def __init__(self, allowed_eids: "set | None"):
        self.allowed = None if allowed_eids is None else frozenset(int(x) for x in allowed_eids)

    def horizon(self, b: "Buy") -> "int | None":
        """The last session offset a stage may read for this trade: None = unbounded, 0 = the buy day only."""
        if self.allowed is None:
            return None
        if not b.dated and CHECK_WIN[0] <= b.E <= CHECK_WIN[1]:
            return 0
        return None if b.eid in self.allowed else 0

    def forward(self, b: "Buy", j: int, who: str = "") -> None:
        h = self.horizon(b)
        if h is not None and j > h:
            raise GuardStop(f"guard (5): session +{j} of {who or b.sym} eid {b.eid} (buy day {b.E}) was requested by a fit stage whose fit set does not "
                            f"hold that trade (its horizon is the buy day)")


@dataclass
class Rec:
    """One trade as the chain sees it: bars, the buy day's index, ADR20 at the prior session, minutes, then ENTER's and STOP's results."""
    b: Buy
    bars: object
    cidx: np.ndarray
    e: int
    adr20: float
    mb: object = None
    minutes_state: str = "missing"
    qqq_c: "np.ndarray | None" = None             # QQQ closes aligned to the ticker's calendar indices (None when absent)
    levels: dict = field(default_factory=dict)
    cross: dict = field(default_factory=dict)
    feasible: dict = field(default_factory=dict)
    verdict: dict = field(default_factory=dict)
    fill: "float | None" = None
    fill_minute: "int | None" = None
    fill_src: str = ""
    fill_fallback: bool = False
    fill_checkwin_registered: bool = False         # M4: a dated 2021-22 in-session bracket (ENTER's dated check set) carries the REGISTERED fill
                                                   # inside the EXIT fit, so the chosen level's feasibility on it is not computed before --check
    stop: "float | None" = None                    # the chosen stop's price on the BUY DAY: sizing and the R unit
    stop_lvl: object = None                        # the chosen stop as an OBJECT (a price, or ('sma', n) for S7 / the 50-day): the walks follow it day by day (M10)
    stop_src: str = ""
    stop_levels: dict = field(default_factory=dict)
    day0: dict = field(default_factory=dict)
    guard: object = None                           # BarGuard: a fit stage may not read a forward bar of a trade outside its fit set

    @property
    def p(self) -> int:
        return self.e - 1

    @property
    def exit_hi_j(self) -> "int | None":
        """His exit session as an offset from the buy day along the ticker's CONSECUTIVE bars (None: no exit window)."""
        if not self.b.has_exit:
            return None
        return self._offset(self.b.exit_hi_i)

    @property
    def exit_lo_j(self) -> "int | None":
        return self._offset(self.b.exit_lo_i) if self.b.has_exit else None

    def _offset(self, ci: int) -> int:
        j = ci - int(self.cidx[self.e])
        return max(0, j)

    def bar_at(self, j: int) -> "int | None":
        """The ticker's bar index for session e + j on consecutive sessions only (None past a hole or the data's end)."""
        if j >= 1 and self.guard is not None:
            self.guard.forward(self.b, j, f"{self.b.sym} eid {self.b.eid}")
        k = self.e + j
        if k >= len(self.cidx) or int(self.cidx[k]) != int(self.cidx[self.e]) + j:
            return None
        return k


def adr20_at(bars, p: int, b: Buy) -> float:
    if b.setup in ("breakout", "both") and b.adr20:
        return float(b.adr20)
    return float(ex.adr_pair(bars, p)[0])


def rec_drop_reason(b: Buy, M: dict, era: str, bcache: dict, min_bars: int = REC_MIN_BARS) -> "str | None":
    """Why a buy gets no record (bars up to the buy day only): not in the era's export, no bar on the buy day, fewer than `min_bars` bars before it
    (§2b step 5 / §13: 50 for STOP / EXIT and the SELECT pick records, `REC_MIN_BARS_ENTER` = 20 for ENTER)."""
    D = M["Ds"][era]
    tk = b.sym_a if era == "A" else b.sym
    bars, cidx = bars_of(D, tk, bcache)
    if bars is None:
        return "ticker_not_in_export"
    e_ci = bisect.bisect_left(D.cal, date.fromisoformat(b.E))
    e = int(np.searchsorted(cidx, e_ci))
    if not (e < len(cidx) and int(cidx[e]) == e_ci):
        return "no_bar_on_E"
    if e < min_bars:
        return f"bars_before_E_lt_{min_bars}"
    return None


def make_rec(b: Buy, M: dict, era: str, done: dict, files: dict, mcache: dict, bcache: dict, want_minutes: bool = True, guard: "BarGuard | None" = None,
             min_bars: int = REC_MIN_BARS) -> "Rec | None":
    if rec_drop_reason(b, M, era, bcache, min_bars) is not None:
        return None
    D = M["Ds"][era]
    tk = b.sym_a if era == "A" else b.sym
    bars, cidx = bars_of(D, tk, bcache)
    e_ci = bisect.bisect_left(D.cal, date.fromisoformat(b.E))
    e = int(np.searchsorted(cidx, e_ci))
    rec = Rec(b=b, bars=bars, cidx=cidx, e=e, adr20=adr20_at(bars, e - 1, b), guard=guard)
    qb, qc = R.bars_for(D, D.tid["QQQ"])
    qpos = {int(c): k for k, c in enumerate(qc)}
    rec.qqq_c = np.array([qb.c[qpos[int(c)]] if int(c) in qpos else np.nan for c in cidx], dtype=float)
    if want_minutes:
        trees = ("EP", "EP2", "A", "B", "REV") if b.setup == "EP" else ("A", "B", "EP", "EP2", "REV")
        trees = tuple(t for t in trees if t in done)
        rec.mb = read_minutes(b.E, tk, done, files, trees, mcache)
        rec.minutes_state = minute_state(b.E, tk, done, files, trees)
        if rec.mb is not None and len(rec.mb) == 0:
            rec.mb = None
    return rec


def registered_fill(rec: Rec) -> tuple:
    """The registered fill (the holdings replay's): dated = ORH5 via `cb.entry_variants` where it filled (else the panel account's close-fill
    proxy, the buy day's close + 0.1%); undated = the open of lo (+ 0.1%, `H.undated_entry`). -> (fill, fill_minute, src, day0)."""
    b, bars, e = rec.b, rec.bars, rec.e
    if b.dated:
        if rec.mb is not None and b.pivot is not None:
            en = cb.entry_variants(rec.mb, pivot=float(b.pivot), adr20=rec.adr20, day_high=float(bars.h[e]), day_low=float(bars.l[e]))["orh5"]
            if en["status"] == "filled":
                return float(en["fill"]), int(en["fill_minute"]), "orh5", dict(en["day0"])
            if en["status"] == "abstain" and en.get("reason") == "too_wide" and en.get("fill") is not None:
                return float(en["fill"]), int(en["fill_minute"]), "orh5_too_wide", dict(en["day0"] or cb._NO_DAY0)
        return float(bars.c[e]) * (1.0 + cb.ENTRY_SLIPPAGE_PCT), None, "close_proxy", dict(cb._NO_DAY0)
    en = H.undated_entry(bars, e, rec.adr20)
    return float(en["fill"]), 0, "open", {"stopped": False, "exit_price": None, "exit_minute": None}


def day0_for(rec: Rec, fill_minute: "int | None", stop: float) -> dict:
    """The day-0 stop check after the fill minute (minutes: `cb.day0_walk`; an open fill without minutes: a low at the stop = a day-0 stop).
    A CLOSE fill (`fill_minute is None` = the dated close-fill proxy) has nothing left in the day: never a day-0 stop (re-check N2 — the
    day's low came before the fill, and under S1 = the day's low a `low <= stop` reading was true by equality)."""
    if fill_minute is None:
        return dict(cb._NO_DAY0)
    if rec.mb is not None:
        return cb.day0_walk(rec.mb, fill_minute=fill_minute, stop=stop)
    if fill_minute == 0:
        stopped = float(rec.bars.l[rec.e]) <= stop
        return {"stopped": bool(stopped), "exit_price": float(stop) if stopped else None, "exit_minute": None}
    return dict(cb._NO_DAY0)


def g8_run(say, recs: list, label: str) -> None:
    """§12 G8 before any number: this stage's own trade list (his panel trades: buy day -> exit_hi) per era through trade_impact.py;
    era A must read entered-after-cutoff 0 and holds-past-last-bar 0 (asserted). The R column is a placeholder (the gate reads dates)."""
    os.makedirs(OUT_DIR, exist_ok=True)
    say(f"\n## G8 — {label}: this read's own trade list through trade_impact.py (before any number)")
    for era in ("A", "B"):
        rows = [("rev", r.b.ticker, r.b.E, r.exit_hi_j if r.exit_hi_j is not None else 0, 0.0) for r in recs if r.b.era == era]
        if not rows:
            say(f"- era {era}: no trade; G8 not run")
            continue
        path, txt = os.path.join(OUT_DIR, f"{label}_g8_{era}.tsv"), os.path.join(OUT_DIR, f"{label}_g8_{era}_impact.txt")
        rp.write_g8_file(path, rows)
        cmd = [sys.executable, rp.TRADE_IMPACT, "--flags", rp.FILES[f"flags_{era}"], "--export", rp.FILES[f"export_{era}"], "--trades", path,
               "--label", era, "--kind", "r1", "--cell", "rev", "--cutoff", CUT_B]
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


def write_chosen(stage: str, obj: dict, text: str) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(chosen_path(stage), "w") as fh:
        json.dump({"stage": stage, "text": text, "object": obj}, fh, indent=1, default=str)
    ledger_append(f"{stage}-fit", chosen_path(stage))


def read_chosen(stage: str) -> dict:
    p = chosen_path(stage)
    if not os.path.exists(p):
        raise GuardStop(f"the {stage.upper()} fit has not run ({p} missing): the chain runs in order")
    with open(p) as fh:
        return json.load(fh)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# SELECT — the bar state (F1-F17) up to the prior session plus the buy day's open; the pool; the conjunction search; the planted control;
# the placement rule; the rank fit
# ═════════════════════════════════════════════════════════════════════════════════════════════
FEATURES = tuple(f"F{k}" for k in range(1, 18))
NUMERIC = tuple(f"F{k}" for k in range(1, 17))
F17_CATS = ("up", "mixed", "down")
SMA_N = (10, 20, 50)


def _roll_mean(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _roll_max(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n).max().to_numpy()


def _roll_min(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n).min().to_numpy()


def _roll_median(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n).median().to_numpy()


def ticker_feature_table(bars, cidx, raw_c: "np.ndarray | None", qqq_state: dict) -> dict:
    """Every per-bar quantity the SELECT features need, as arrays over the ticker's bars (bar p = the prior session; the buy day = p + 1).
    `qqq_state[ci]` = QQQ's state at the close of calendar index ci. Vectorised once per ticker."""
    o, h, l, c, v = (np.asarray(getattr(bars, k), dtype=float) for k in "ohlcv")
    n = len(c)
    T = {}
    adr = _roll_mean((h - l) / c, cb.ADR_WINDOW)
    T["adr"] = adr
    px = c * adr
    prev_max20 = np.concatenate(([np.nan], _roll_max(h, 20)[:-1]))     # the max high of the 20 sessions BEFORE p
    prev_max50 = np.concatenate(([np.nan], _roll_max(h, 50)[:-1]))
    T["F1"] = (c - prev_max20) / px
    T["F2"] = (c - prev_max50) / px
    # F3: sessions since the 252-session high (the available window when fewer than 252 bars precede p)
    f3 = np.full(n, np.nan)
    if n:
        W = 252
        from numpy.lib.stride_tricks import sliding_window_view
        if n >= W:
            am = np.argmax(sliding_window_view(h, W), axis=1)
            f3[W - 1:] = (W - 1) - am
        for p in range(min(n, W - 1)):
            f3[p] = p - int(np.argmax(h[:p + 1]))
    T["F3"] = f3
    T["F4"] = (_roll_max(h, 10) - _roll_min(l, 10)) / px
    for n_, name in zip(SMA_N, ("F5", "F6", "F7")):
        T[name] = (c - _roll_mean(c, n_)) / px
    sh = lambda k: np.concatenate((np.full(k, np.nan), c[:-k])) if n > k else np.full(n, np.nan)   # noqa: E731
    T["F8"] = c / sh(20) - 1.0
    T["F9"] = c / sh(60) - 1.0
    T["F10"] = adr
    vprev = np.concatenate(([np.nan], _roll_mean(v, 20)[:-1]))
    T["F11"] = v / vprev
    T["F12"] = (h - l) / px
    T["F13"] = np.where(h > l, (c - l) / np.where(h > l, h - l, 1.0), 0.5)
    o_next = np.concatenate((o[1:], [np.nan]))
    T["F14"] = (o_next - c) / px
    T["ret63"] = c / sh(63) - 1.0
    T["ret21"] = c / sh(21) - 1.0
    T["F17"] = np.array([qqq_state.get(int(ci), "") for ci in cidx], dtype=object)
    T["raw"] = raw_c if raw_c is not None else c                       # the $5 test: the raw close (era B: the export close stands in)
    T["dv_med"] = _roll_median(c * v, POOL_DV_WINDOW)                  # the $10M test: export close x export volume — split-invariant (H2)
    T["contig130"] = np.zeros(n, dtype=bool)
    if n >= POOL_MIN_HISTORY:
        ci64 = np.asarray(cidx, dtype=np.int64)
        T["contig130"][POOL_MIN_HISTORY - 1:] = (ci64[POOL_MIN_HISTORY - 1:] - ci64[:-(POOL_MIN_HISTORY - 1)]) == POOL_MIN_HISTORY - 1
    T["next_is_bar"] = np.concatenate(((np.diff(np.asarray(cidx, dtype=np.int64)) == 1), [False]))
    # beside, survival-confounded: the same F1 / F2 / F11 / F12 / F13 on the buy day's own bar (= the next bar's values)
    for k in ("F1", "F2", "F11", "F12", "F13"):
        T[f"{k}_E"] = np.concatenate((T[k][1:], [np.nan]))
    return T


def qqq_states(D) -> dict:
    qb, qc = R.bars_for(D, D.tid["QQQ"])
    return {int(ci): rp.qqq_state_at(qb.c, k) for k, ci in enumerate(qc)}


def pool_rows_for_days(D, raw_flat: "np.ndarray | None", day_cis: list, qst: dict, small: dict, sic: dict, held: dict, cal: list,
                       era: str, tickers: "list | None" = None, progress=None, light: bool = False) -> pd.DataFrame:
    """One row per (ticker, buy day) admitted to the pool on the session before the buy day (raw close >= $5, 20-session median export close x
    volume >= $10M, 130 consecutive sessions, type CS / ADRC / untyped, a bar on the buy day), with F1-F14, the 3- / 1-month returns, F17 and
    the held-that-day flag (his names; the pick stays). Era A: keyed by today's symbol (sym_a); era B: point in time.
    `light=True` emits only ticker / day / held / the two returns (+ F15 / F16): the same-day pool a non-fit day needs for a pick's return
    percentiles (placement sessions, flicker and beside days — check M5 / M6); it enters no grid and no pool rate."""
    want = np.asarray(sorted(set(day_cis)), dtype=np.int64)
    rows = []
    tks = tickers if tickers is not None else D.tickers
    for n_t, tk in enumerate(tks):
        tid = D.tid.get(tk)
        if tid is None:
            continue
        t_type, _src, ok = type_of(tk, small, sic)
        if not ok:
            continue
        a, bnd = int(D.start[tid]), int(D.stop[tid])
        cidx = D.ci[a:bnd]
        if len(cidx) < POOL_MIN_HISTORY + 1:
            continue
        # the prior-session bar index p for each wanted buy day: cidx[p] == day_ci - 1 and cidx[p + 1] == day_ci
        pos = np.searchsorted(cidx, want - 1)
        okp = (pos < len(cidx) - 1) & (cidx[np.minimum(pos, len(cidx) - 1)] == want - 1) & (cidx[np.minimum(pos + 1, len(cidx) - 1)] == want)
        if not okp.any():
            continue
        bars, _ = R.bars_for(D, tid)
        raw_c = raw_flat[a:bnd] if raw_flat is not None else None
        T = ticker_feature_table(bars, cidx, raw_c, qst)
        for p, dci in zip(pos[okp], want[okp]):
            p = int(p)
            if not (T["contig130"][p] and T["raw"][p] >= POOL_MIN_RAW_CLOSE and T["dv_med"][p] >= POOL_MIN_DV and np.isfinite(T["adr"][p]) and T["adr"][p] > 0):
                continue
            row = {"ticker": tk, "day_ci": int(dci), "day": cal[int(dci)], "sec_type": t_type, "era": era,
                   "held": tk in held.get(cal[int(dci)], set()), "ret63": float(T["ret63"][p]), "ret21": float(T["ret21"][p])}
            if not light:
                for k in NUMERIC[:14]:
                    row[k] = float(T[k][p])
                row["F17"] = T["F17"][p]
                for k in ("F1", "F2", "F11", "F12", "F13"):
                    row[f"{k}_E"] = float(T[f"{k}_E"][p])
            rows.append(row)
        if progress and (n_t + 1) % 2000 == 0:
            progress(f"  pool: {n_t + 1:,} / {len(tks):,} tickers scanned, {len(rows):,} admitted rows")
    df = pd.DataFrame(rows)
    if len(df):
        df = add_percentiles(df)
    return df


def add_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """F15 / F16: the 3- / 1-month return's percentile within that day's pool (0 = the lowest, 1 = the highest; ties averaged)."""
    for src, dst in (("ret63", "F15"), ("ret21", "F16")):
        df[dst] = df.groupby("day_ci")[src].rank(pct=True, method="average").astype(float)
    return df


def feature_table_for(rec: Rec, raw_c: "np.ndarray | None", qst: dict, tcache: "dict | None" = None) -> dict:
    """`ticker_feature_table` once per ticker's bar array (placement scores many sessions of one ticker)."""
    if tcache is None:
        return ticker_feature_table(rec.bars, rec.cidx, raw_c, qst)
    k = id(rec.bars)
    hit = tcache.get(k)
    if hit is None or hit[0] is not rec.bars:                # the entry holds the bar array itself, so its id cannot be reused by another
        hit = (rec.bars, ticker_feature_table(rec.bars, rec.cidx, raw_c, qst))   # ticker's array while cached (the 10-24 first SELECT fit crashed on a reused id)
        tcache[k] = hit
    return hit[1]


def pick_features(rec: Rec, raw_c: "np.ndarray | None", qst: dict, pool_day: "pd.DataFrame | None", tcache: "dict | None" = None) -> dict:
    """F1-F17 of his pick on its buy day (bars up to the prior session + the open), its F15 / F16 against that day's pool rows (the pool with
    the pick itself: the share of pool returns below the pick's plus half the ties, the pick's own return included). A day WITHOUT pool
    rows gives F15 = F16 = NaN and `pool_empty` = True (counted by every caller) — never a default percentile (check M5)."""
    T = feature_table_for(rec, raw_c, qst, tcache)
    p = rec.p
    f = {k: float(T[k][p]) for k in NUMERIC[:14]}
    f["F17"] = T["F17"][p]
    f["pool_empty"] = pool_day is None or not len(pool_day)
    for src, dst in (("ret63", "F15"), ("ret21", "F16")):
        r = float(T[src][p])
        if f["pool_empty"] or not np.isfinite(r):
            f[dst] = float("nan")
            continue
        others = pool_day[src].to_numpy(dtype=float)
        allv = np.concatenate((others[np.isfinite(others)], [r]))
        f[dst] = float((np.sum(allv < r) + 0.5 * np.sum(allv == r)) / len(allv))
    for k in ("F1", "F2", "F11", "F12", "F13"):
        f[f"{k}_E"] = float(T[f"{k}_E"][p])
    f["floor_reason"] = floor_reason_from_table(T, p)
    f["floor_ok"] = f["floor_reason"] == ""
    return f


# ---- the conjunction family -------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Cond:
    feat: str
    op: str          # "<=" | ">=" | "=="
    thr: object

    def text(self) -> str:
        return f"{self.feat}{self.op}{self.thr if self.op == '==' else f'{float(self.thr):.4g}'}"

    def eval(self, df) -> np.ndarray:
        x = df[self.feat].to_numpy() if hasattr(df, "columns") else np.asarray(df[self.feat])
        if self.op == "==":
            return np.asarray(x == self.thr)
        x = np.asarray(x, dtype=float)
        return (x <= float(self.thr)) if self.op == "<=" else (x >= float(self.thr))


def grid_from_pool(pool: pd.DataFrame) -> list:
    """The fixed grid: the pool's deciles (10..90) on the fit days per numeric feature, each as <= and >=; F17's three categories."""
    conds = []
    for k in NUMERIC:
        x = pool[k].to_numpy(dtype=float)
        x = x[np.isfinite(x)]
        cuts = np.unique(np.percentile(x, np.arange(10, 100, 10))) if len(x) else []
        for t in cuts:
            conds.append(Cond(k, "<=", float(t)))
            conds.append(Cond(k, ">=", float(t)))
    for cat in F17_CATS:
        conds.append(Cond("F17", "==", cat))
    return conds


def pack_bits(M: np.ndarray) -> np.ndarray:
    """bool [k, n] -> uint64 [k, W] (zero-padded)."""
    k, n = M.shape
    pb = np.packbits(M, axis=1)                        # uint8 [k, ceil(n/8)]
    pad = (-pb.shape[1]) % 8
    if pad:
        pb = np.concatenate((pb, np.zeros((k, pad), dtype=np.uint8)), axis=1)
    return pb.view(np.uint64).copy()


def popcount_rows(x: np.ndarray) -> np.ndarray:
    return np.bitwise_count(x).sum(axis=-1)


class ConjSearch:
    """Every conjunction of at most 3 single conditions over the pool bits and the buy bits: ids are (a, b, c) index triples (b, c = -1 when
    absent). The pool counts are computed ONCE; the buy counts per buy set (the real set and the 20 planted sets)."""

    def __init__(self, conds: list, pool_bits: np.ndarray, n_pool: int):
        self.conds, self.P, self.n_pool = conds, pool_bits, n_pool
        self.K = len(conds)
        self.a, self.b, self.c = self._ids()
        self.pool_cnt = None

    def _ids(self) -> tuple:
        K = self.K
        a1 = np.arange(K, dtype=np.int32)
        ii, jj = np.triu_indices(K, 1)
        a3, b3, c3 = [], [], []
        for a in range(K):
            for b in range(a + 1, K):
                cs = np.arange(b + 1, K, dtype=np.int32)
                a3.append(np.full(len(cs), a, dtype=np.int32)); b3.append(np.full(len(cs), b, dtype=np.int32)); c3.append(cs)
        a3 = np.concatenate(a3) if a3 else np.zeros(0, np.int32)
        b3 = np.concatenate(b3) if b3 else np.zeros(0, np.int32)
        c3 = np.concatenate(c3) if c3 else np.zeros(0, np.int32)
        A = np.concatenate((a1, ii.astype(np.int32), a3))
        B = np.concatenate((np.full(K, -1, np.int32), jj.astype(np.int32), b3))
        C = np.concatenate((np.full(K, -1, np.int32), np.full(len(ii), -1, np.int32), c3))
        return A, B, C

    def counts(self, bits: np.ndarray) -> np.ndarray:
        """Popcounts of every conjunction over `bits` (uint64 [K, W]) in id order: singles, pairs (a<b), triples (a<b<c)."""
        K = self.K
        out = [popcount_rows(bits)]
        pairs = []
        triples = []
        for a in range(K):
            if a + 1 < K:
                AB = bits[a] & bits[a + 1:]                            # [K-a-1, W]
                pairs.append(popcount_rows(AB))
                for i, b in enumerate(range(a + 1, K)):
                    if b + 1 < K:
                        triples.append(popcount_rows(AB[i] & bits[b + 1:]))
        out.append(np.concatenate(pairs) if pairs else np.zeros(0, np.int64))
        out.append(np.concatenate(triples) if triples else np.zeros(0, np.int64))
        return np.concatenate(out).astype(np.int64)

    def pool_counts(self) -> np.ndarray:
        if self.pool_cnt is None:
            self.pool_cnt = self.counts(self.P)
        return self.pool_cnt

    def size(self) -> np.ndarray:
        return 1 + (self.b >= 0).astype(np.int64) + (self.c >= 0).astype(np.int64)

    def text(self, i: int) -> str:
        parts = [self.conds[int(self.a[i])].text()]
        if self.b[i] >= 0:
            parts.append(self.conds[int(self.b[i])].text())
        if self.c[i] >= 0:
            parts.append(self.conds[int(self.c[i])].text())
        return " & ".join(parts)

    def conds_of(self, i: int) -> list:
        return [self.conds[int(x)] for x in (self.a[i], self.b[i], self.c[i]) if x >= 0]

    def bits_of(self, i: int, bits: np.ndarray) -> np.ndarray:
        v = bits[int(self.a[i])].copy()
        for x in (self.b[i], self.c[i]):
            if x >= 0:
                v &= bits[int(x)]
        return v


def cond_matrix(conds: list, df: pd.DataFrame) -> np.ndarray:
    M = np.zeros((len(conds), len(df)), dtype=bool)
    for k, cd in enumerate(conds):
        M[k] = cd.eval(df)
    return M


def choose_condition_set(cs: ConjSearch, pool_cnt: np.ndarray, buy_bits: np.ndarray, n_buys: int, pool_bits: np.ndarray, cap: float = POOL_RATE_CAP,
                         max_conj: int = SELECT_MAX_CONJ, add_recall: float = SELECT_ADD_RECALL) -> dict:
    """§5b's selection: the conjunction with the highest recall subject to pool rate <= cap; ties -> fewer conditions, then the higher lift
    (recall / pool rate), then id order. Up to `max_conj` kept greedily when each adds >= `add_recall` of recall with its own pool rate <= cap
    AND the set's (union) pool rate <= cap. -> {ids, texts, recall, pool_rate, lift, union buy bits, union pool bits}."""
    buy_cnt = cs.counts(buy_bits)
    rate = pool_cnt / max(cs.n_pool, 1)
    size = cs.size()
    elig = rate <= cap
    if not elig.any() or n_buys == 0:
        return dict(ids=[], texts=[], recall=0.0, pool_rate=float("nan"), lift=float("nan"), recall_each=[], rate_each=[], buy_cnt=buy_cnt)
    rec_ = buy_cnt / n_buys
    lift = np.where(rate > 0, rec_ / np.where(rate > 0, rate, 1), np.inf)
    order = np.lexsort((np.arange(len(rate)), -lift, size, -rec_))      # primary: recall desc; then size asc; then lift desc; then id
    order = order[elig[order]]
    first = int(order[0])
    ids = [first]
    Ub = cs.bits_of(first, buy_bits)
    Up = cs.bits_of(first, pool_bits)
    cur_recall = int(popcount_rows(Ub)) / n_buys
    while len(ids) < max_conj:
        best, best_gain, best_rate = None, 0.0, None
        # candidates: own pool rate <= cap, in the fit's order; union computed on the fly
        for i in order:
            i = int(i)
            if i in ids or rec_[i] < add_recall:
                continue
            ub = Ub | cs.bits_of(i, buy_bits)
            gain = int(popcount_rows(ub)) / n_buys - cur_recall
            if gain < add_recall or gain <= best_gain:
                continue
            up = Up | cs.bits_of(i, pool_bits)
            r_union = int(popcount_rows(up)) / max(cs.n_pool, 1)
            if r_union > cap:
                continue
            best, best_gain, best_rate = i, gain, r_union
        if best is None:
            break
        ids.append(best)
        Ub |= cs.bits_of(best, buy_bits)
        Up |= cs.bits_of(best, pool_bits)
        cur_recall += best_gain
    pr = int(popcount_rows(Up)) / max(cs.n_pool, 1)
    return dict(ids=ids, texts=[cs.text(i) for i in ids], recall=cur_recall, pool_rate=pr, lift=(cur_recall / pr) if pr > 0 else float("inf"),
                recall_each=[float(rec_[i]) for i in ids], rate_each=[float(rate[i]) for i in ids], buy_cnt=buy_cnt, union_buy=Ub, union_pool=Up)


def set_matches(conds_list: list, df: pd.DataFrame) -> np.ndarray:
    """Rows of `df` meeting the condition set (any conjunction; each conjunction = all its conditions)."""
    out = np.zeros(len(df), dtype=bool)
    for conj in conds_list:
        m = np.ones(len(df), dtype=bool)
        for cd in conj:
            m &= cd.eval(df)
        out |= m
    return out


def ridge_logistic(X: np.ndarray, y: np.ndarray, lam: float = RIDGE_LAMBDA, iters: int = 100) -> tuple:
    """L2-penalised logistic regression (lambda on the weights, not the intercept) on STANDARDISED features by Newton's method.
    -> (w, b, mean, std)."""
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    Z = (X - mu) / sd
    n, d = Z.shape
    A = np.hstack((Z, np.ones((n, 1))))
    th = np.zeros(d + 1)
    pen = np.full(d + 1, lam)
    pen[-1] = 0.0
    for _ in range(iters):
        z = A @ th
        p = 1.0 / (1.0 + np.exp(-z))
        g = A.T @ (y - p) - pen * th
        Wd = p * (1 - p)
        Hm = -(A.T * Wd) @ A - np.diag(pen)
        step = np.linalg.solve(Hm, g)
        th -= step
        if np.abs(step).max() < 1e-8:
            break
    return th[:-1], float(th[-1]), mu, sd


def rank_design(df: pd.DataFrame) -> np.ndarray:
    X = np.column_stack([df[k].to_numpy(dtype=float) for k in NUMERIC] + [(df["F17"].to_numpy() == c).astype(float) for c in F17_CATS])
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


def pick_percentile(score_pick: float, scores_pool: np.ndarray) -> float:
    """The pick's percentile from the TOP within the qualifying names (pool not held + the pick): 0 = the best score, ties averaged."""
    allv = np.concatenate((scores_pool, [score_pick]))
    return float((np.sum(allv > score_pick) + 0.5 * (np.sum(allv == score_pick) - 1)) / len(allv))


def short_cluster_flag(conj_buys: pd.DataFrame, pool: pd.DataFrame) -> bool:
    """§5b: a conjunction whose buys' median F8 or F9 is above the pool's 95th percentile reads `parabolic_short?`."""
    if not len(conj_buys):
        return False
    for k in ("F8", "F9"):
        x = pool[k].to_numpy(dtype=float)
        x = x[np.isfinite(x)]
        if len(x) and float(np.nanmedian(conj_buys[k].to_numpy(dtype=float))) > float(np.percentile(x, SHORT_CLUSTER_PCT)):
            return True
    return False


def place_window(session_meets: list) -> tuple:
    """§5c: a window's sessions scored by the fitted condition set (bools in session order lo..hi) -> (index of the placed session, by_default)."""
    hits = [i for i, m in enumerate(session_meets) if m]
    return (hits[-1], False) if hits else (0, True)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# ENTER — six levels, the bracket, feasibility, HIT / BALLPARK / MISS, the random-level control
# ═════════════════════════════════════════════════════════════════════════════════════════════
def opening_range_high(mb, k: int) -> "float | None":
    sel = mb.minute < k
    return float(mb.h[sel].max()) if sel.any() else None


def first_cross(mb, level: float) -> "int | None":
    """The first minute whose high is ABOVE the level (`cb._entry_one`'s crossing), or None."""
    hits = np.flatnonzero(mb.h > level)
    return int(mb.minute[hits[0]]) if len(hits) else None


def enter_levels(rec: Rec) -> dict:
    """L1 the 5-minute opening-range high (dated: max of it and the level) · L2 the prior session's high · L3 the base high (dated BREAKOUT: the
    candidate row's pivot; EP-dated and undated: the max high of the prior 20 sessions — an EP row's `pivot` is the prior close, which is L5;
    check L5) · L4 the session's open · L5 the prior close · L6 the first-hour high."""
    b, bars, e, p = rec.b, rec.bars, rec.e, rec.p
    L = {}
    o5 = opening_range_high(rec.mb, 5) if rec.mb is not None else None
    L["L1"] = (max(o5, float(b.pivot)) if (b.dated and b.pivot is not None) else o5) if o5 is not None else None
    L["L2"] = float(bars.h[p])
    L["L3"] = float(b.pivot) if (b.setup in ("breakout", "both") and b.pivot is not None) else float(np.max(bars.h[max(p - 19, 0):p + 1]))
    L["L4"] = float(bars.o[e])
    L["L5"] = float(bars.c[p])
    L["L6"] = opening_range_high(rec.mb, 60) if rec.mb is not None else None
    return L


def bracket_minutes(b: Buy) -> tuple:
    return hhmm_to_min(b.flat_clock), hhmm_to_min(b.first_clock)


def score_level(mb, level: "float | None", flat_m: int, first_m: int, adr20: float, tol_adr: float = BALLPARK_ADR) -> dict:
    """Feasible = the first crossing minute lies in (flat, first]. HIT = the level inside [min low, max high] of the bracket's minutes;
    BALLPARK = within tol_adr x ADR20 x level of the nearer edge; else MISS. -> {cross, feasible, verdict, range}."""
    out = dict(cross=None, feasible=False, verdict="no_level", range=None)
    if level is None or not np.isfinite(level):
        return out
    m = first_cross(mb, level)
    out["cross"] = m
    out["feasible"] = m is not None and flat_m < m <= first_m
    sel = (mb.minute > flat_m) & (mb.minute <= first_m)
    if not sel.any():
        out["verdict"] = "no_bracket_minutes"
        return out
    lo, hi = float(mb.l[sel].min()), float(mb.h[sel].max())
    out["range"] = (lo, hi)
    if lo <= level <= hi:
        out["verdict"] = "HIT"
    elif min(abs(level - lo), abs(level - hi)) <= tol_adr * adr20 * level:
        out["verdict"] = "BALLPARK"
    else:
        out["verdict"] = "MISS"
    return out


def score_unbracketed(mb, level: "float | None", first_m: "int | None", adr20: float) -> dict:
    """Beside: no flat frame that day -> feasible = crossed by first_clock (or that session when first_m is None); ballpark = the level within
    0.5 ADR20 of the crossing minute's close."""
    out = dict(cross=None, feasible=False, verdict="no_level")
    if level is None or not np.isfinite(level):
        return out
    m = first_cross(mb, level)
    out["cross"] = m
    if m is None or (first_m is not None and m > first_m):
        out["verdict"] = "MISS"
        return out
    out["feasible"] = True
    k = int(np.searchsorted(mb.minute, m))
    out["verdict"] = "BALLPARK" if abs(float(mb.c[k]) - level) <= BALLPARK_ADR_UNBRACKETED * adr20 * level else "MISS"
    return out


def random_levels(mb, n: int, rng) -> np.ndarray:
    """§3's price control: the close of a uniformly random minute of the session (09:30-16:00); a drawn minute with no bar takes the nearest
    prior bar's close (before the first bar: the first bar's open)."""
    u = rng.integers(0, 390, size=n)
    idx = np.searchsorted(mb.minute, u, side="right") - 1
    return np.where(idx >= 0, mb.c[np.maximum(idx, 0)], mb.o[0])


def enter_score_trade(rec: Rec, rng) -> dict:
    """Every level and the control on one in-session-bracketed trade with minutes. A level that does not EXIST yet at `first_clock` (L1 before
    09:35, L6 before 10:30: its value would include minutes after the frame that showed him holding) reads `no_level_yet`: not feasible,
    neither HIT nor MISS, counted (check L5)."""
    flat_m, first_m = bracket_minutes(rec.b)
    rec.levels = enter_levels(rec)
    res = {}
    for L in LEVELS:
        if first_m < LEVEL_KNOWN_MIN.get(L, 0):
            s = dict(cross=None, feasible=False, verdict="no_level_yet", range=None)
        else:
            s = score_level(rec.mb, rec.levels[L], flat_m, first_m, rec.adr20)
        rec.cross[L], rec.feasible[L], rec.verdict[L] = s["cross"], s["feasible"], s["verdict"]
        res[L] = s
    ctl = random_levels(rec.mb, RANDOM_LEVELS, rng)
    cf, ch = 0, 0
    for lv in ctl:
        s = score_level(rec.mb, float(lv), flat_m, first_m, rec.adr20)
        cf += int(s["feasible"])
        ch += int(s["verdict"] in ("HIT", "BALLPARK"))
    res["control"] = dict(feasible_share=cf / RANDOM_LEVELS, hit_share=ch / RANDOM_LEVELS)
    return res


def enter_summary(scored: dict) -> dict:
    """Per level: feasible share, hit-or-ballpark share (of all scorable trades) with the 95% interval; the control's shares."""
    n = len(scored)
    out = {"n": n}
    for L in LEVELS:
        f = sum(1 for r in scored.values() if r[L]["feasible"])
        h = sum(1 for r in scored.values() if r[L]["verdict"] in ("HIT", "BALLPARK"))
        out[L] = dict(feasible=f, hit=h, feasible_share=binom_ci(f, n), hit_share=binom_ci(h, n),
                      verdicts=Counter(r[L]["verdict"] for r in scored.values()))
    out["control"] = dict(feasible_share=float(np.mean([r["control"]["feasible_share"] for r in scored.values()])) if n else float("nan"),
                          hit_share=float(np.mean([r["control"]["hit_share"] for r in scored.values()])) if n else float("nan"))
    return out


def choose_level(summary: dict) -> str:
    """The highest feasible share on the fit; ties -> L1 (the registered reading), else the first in order."""
    best = max(summary[L]["feasible"] for L in LEVELS)
    tied = [L for L in LEVELS if summary[L]["feasible"] == best]
    return "L1" if "L1" in tied else tied[0]


def enter_deciding(scored: dict, dated_eids: set, chosen: str) -> tuple:
    """§6 / §10 (check M1): the trades whose scores DECIDE the ENTER check. L1 on the dated 2021-22 brackets is a re-read (the holdings replay
    printed ORH5 against the panel clock), so when L1 is the chosen level the deciding set is the UNDATED check brackets alone and the dated
    ones are printed beside; any other level decides on dated + undated. -> (deciding scores, beside scores)."""
    if chosen == "L1":
        return {k: v for k, v in scored.items() if k not in dated_eids}, {k: v for k, v in scored.items() if k in dated_eids}
    return dict(scored), {}


def score_crossed(mb, level: "float | None") -> dict:
    """§6c's weakest read, for the pre-market FIRST sightings (he held at the next morning's frame; no bracket): did the session cross the level
    at all? -> {cross, crossed}."""
    if mb is None or level is None or not np.isfinite(level):
        return dict(cross=None, crossed=False)
    m = first_cross(mb, level)
    return dict(cross=m, crossed=m is not None)


def enter_verdict(summary: dict, chosen: str) -> tuple:
    """(verdict, reasons): PASS / INCONCLUSIVE / FAIL on the check; fewer than 40 scorable trades -> INCONCLUSIVE."""
    n = summary["n"]
    if n < ENTER_MIN_CHECK:
        return "INCONCLUSIVE", [f"only {n} scorable check trades (< {ENTER_MIN_CHECK})"]
    fs, hs = summary[chosen]["feasible_share"][0], summary[chosen]["hit_share"][0]
    cf, chh = summary["control"]["feasible_share"], summary["control"]["hit_share"]
    reasons = []
    if fs < ENTER_PASS_FEASIBLE:
        reasons.append(f"feasible {pct(fs)} < {pct(ENTER_PASS_FEASIBLE)}")
    if fs < cf + ENTER_CONTROL_MARGIN:
        reasons.append(f"feasible {pct(fs)} not >= control {pct(cf)} + 15")
    if hs < ENTER_PASS_HIT:
        reasons.append(f"hit-or-ballpark {pct(hs)} < {pct(ENTER_PASS_HIT)}")
    if hs < chh + ENTER_CONTROL_MARGIN:
        reasons.append(f"hit-or-ballpark {pct(hs)} not >= control {pct(chh)} + 15")
    if not reasons:
        return "PASS", []
    if all(summary[L]["feasible_share"][0] < ENTER_PASS_FEASIBLE for L in LEVELS):
        return "FAIL", reasons + ["no level >= 50% feasible: his entry is not a level crossing we model"]
    return "INCONCLUSIVE", reasons


def chain_fill(rec: Rec, chosen_level: "str | None") -> None:
    """§4: the chosen level's price where it is feasible on that trade (fill minute = its crossing minute); otherwise the registered fill,
    flagged `fill_fallback`. No chosen level (ENTER failed / not run) -> the registered fill."""
    if chosen_level and rec.mb is not None and rec.b.in_bracket:
        if not rec.levels:
            rec.levels = enter_levels(rec)
        flat_m, first_m = bracket_minutes(rec.b)
        s = score_level(rec.mb, rec.levels.get(chosen_level), flat_m, first_m, rec.adr20)
        if s["feasible"]:
            rec.fill, rec.fill_minute, rec.fill_src, rec.fill_fallback = float(rec.levels[chosen_level]), int(s["cross"]), f"level:{chosen_level}", False
            return
    rec.fill, rec.fill_minute, rec.fill_src, d0 = registered_fill(rec)
    rec.fill_fallback = chosen_level is not None
    rec.day0 = d0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# STOP — eight levels x two variants, held-through on sessions he certainly held, §7c's risk
# ═════════════════════════════════════════════════════════════════════════════════════════════
def base_low(rec: Rec) -> float:
    """Dated: the lowest low of the candidate's base = the sessions from the base_id's date through D (the only base columns read);
    undated: the lowest low of the prior 20 sessions."""
    b, bars, p = rec.b, rec.bars, rec.p
    if b.dated and b.base_id and "|" in b.base_id:
        d0 = b.base_id.split("|", 1)[1]
        k = bisect.bisect_left(bars.dates, date.fromisoformat(d0))
        k = min(max(k, 0), p)
        return float(np.min(bars.l[k:p + 1]))
    return float(np.min(bars.l[max(p - 19, 0):p + 1]))


def sma_series(bars, n: int) -> np.ndarray:
    return _roll_mean(np.asarray(bars.c, dtype=float), n)


def stop_levels(rec: Rec, fill_minute_for_s1: "int | None") -> dict:
    """{level: price or ('sma', n)}; S1 from the minutes up to the fill minute (else the day's low, flagged `S1_is_S2`)."""
    b, bars, e, p = rec.b, rec.bars, rec.e, rec.p
    S = {}
    if rec.mb is not None and fill_minute_for_s1 is not None:
        sel = rec.mb.minute <= fill_minute_for_s1
        S["S1"] = float(rec.mb.l[sel].min()) if sel.any() else float(bars.l[e])
        S["S1_is_S2"] = not sel.any()
    else:
        S["S1"], S["S1_is_S2"] = float(bars.l[e]), True
    S["S2"] = float(bars.l[e])
    S["S3"] = float(bars.l[p])
    S["S4"] = float(rec.fill) * (1.0 - rec.adr20)
    S["S5"] = float(b.pivot) if (b.dated and b.pivot is not None) else float(np.max(bars.h[max(p - 19, 0):p + 1]))
    S["S6"] = base_low(rec)
    S["S7"] = ("sma", 10)
    S["S8"] = float(rec.fill) * (1.0 - 2.0 * rec.adr20)
    S["SMA50"] = ("sma", 50)
    return S


def level_at(rec: Rec, lvl, j: int, smas: dict) -> float:
    """The level's price on session j (a moving average is read at that session's close; the buy day's for sizing)."""
    if isinstance(lvl, tuple):
        k = rec.bar_at(j)
        return float(smas[lvl[1]][k]) if k is not None else float("nan")
    return float(lvl)


@dataclass
class Sightings:
    """The frames that bound his certainty on the exit window's first session and on the buy day (from snapshots.tsv)."""
    by_date_sym: dict          # (date, sym) -> [(idx, ctx, clock)] holding the name

    @classmethod
    def build(cls, sn: pd.DataFrame) -> "Sightings":
        d = defaultdict(list)
        for r in sn.to_dict("records"):
            names = set(x for x in (r.get("symbols") or "").split(",") if x) | set(x for x in (r.get("blip_filled") or "").split(",") if x)
            for s in names:
                d[(r["date"], s)].append((int(r["idx"]), r["ctx"], r["clock"]))
        return cls(d)

    def last_in_session_clock(self, d: str, sym: str) -> "str | None":
        fr = [x for x in self.by_date_sym.get((d, sym), ()) if x[1] == "in" and x[2]]
        return max(fr)[2] if fr else None

    def after_close_frame(self, d: str, sym: str) -> bool:
        return any(x[1] == "closed" for x in self.by_date_sym.get((d, sym), ()))

    def frame_after_minute(self, d: str, sym: str, m: int) -> bool:
        """A frame on d showing the name with an in-session clock later than minute m."""
        return any(x[1] == "in" and x[2] and hhmm_to_min(x[2]) is not None and hhmm_to_min(x[2]) > m for x in self.by_date_sym.get((d, sym), ()))


def held_through(rec: Rec, name, variant: str, smas: dict, sight: Sightings, exit_mb=None, last_j: "int | None" = None) -> dict:
    """§7b on one trade and one (level, variant): traded through on any session <= exit_hi (the denominator), traded through on a session he
    CERTAINLY held (the numerator), unresolved (a touch whose certainty needs minutes we lack). `name` = a key of rec.stop_levels (S1..S8,
    SMA50) or a bare price. S2 under T is tested from session 1 (and S1 when it IS the day's low, `S1_is_S2`)."""
    b = rec.b
    if isinstance(name, str):
        lvl = rec.stop_levels[name]
        j0 = 1 if (variant == "T" and (name == "S2" or (name == "S1" and rec.stop_levels.get("S1_is_S2")))) else 0
    else:
        lvl, j0 = name, 0
    J = rec.exit_hi_j if rec.exit_hi_j is not None else last_j
    out = dict(any=False, certain=False, unresolved=False, first_j=None, note="")
    if J is None:
        return out
    lo_j = rec.exit_lo_j if rec.exit_lo_j is not None else J + 1
    for j in range(j0, J + 1):
        k = rec.bar_at(j)
        if k is None:
            out["note"] = "hole"
            break
        L = level_at(rec, lvl, j, smas)
        if not np.isfinite(L):
            continue
        through, touch_m = False, None
        if variant == "C":
            through = float(rec.bars.c[k]) < L
        else:
            if j == 0:
                if rec.mb is not None and rec.fill_minute is not None:
                    after = rec.mb.minute > rec.fill_minute
                    hit = np.flatnonzero(after & ((rec.mb.l <= L) | (rec.mb.o < L)))
                    if len(hit):
                        through, touch_m = True, int(rec.mb.minute[hit[0]])
                elif rec.fill_minute == 0:
                    through = float(rec.bars.l[k]) <= L
                else:
                    if float(rec.bars.l[k]) <= L:
                        out["unresolved"] = True           # a day-0 touch, the fill minute unknown
                    continue
            else:
                through = float(rec.bars.l[k]) <= L
        if not through:
            continue
        out["any"] = True
        if out["first_j"] is None:
            out["first_j"] = j
        if j < lo_j:
            if j == 0 and variant == "T" and touch_m is None and rec.fill_minute != 0:
                out["unresolved"] = True
            else:
                out["certain"] = True
            break
        if j == lo_j:
            if variant == "C":
                if sight.after_close_frame(b.exit_lo, b.sym):
                    out["certain"] = True
            else:
                c_last = sight.last_in_session_clock(b.exit_lo, b.sym)
                if j == 0 and touch_m is not None:
                    if sight.frame_after_minute(b.E, b.sym, touch_m):
                        out["certain"] = True
                elif c_last is not None:
                    if exit_mb is not None:
                        hit = np.flatnonzero((exit_mb.l <= L) | (exit_mb.o < L))
                        if len(hit) and int(exit_mb.minute[hit[0]]) < hhmm_to_min(c_last):
                            out["certain"] = True
                    else:
                        out["unresolved"] = True
            break
        break        # after exit_lo: not evidence
    return out


def exit_minutes_for(recs: list, M: dict) -> dict:
    """{eid: MinuteBars} of the exit window's FIRST session (where a tree holds that date for the name) — §7a: a touch before the last frame's
    clock on exit_lo was held through. The buy day's own minutes serve when exit_lo is the buy day."""
    out, cache = {}, {}
    trees = tuple(t for t in ("A", "B", "EP", "EP2", "REV") if t in M["done"])
    for r in recs:
        b = r.b
        if not b.has_exit or b.exit_lo == b.E:
            continue
        tk = b.sym_a if b.exit_lo <= A_LAST else b.sym
        mb = read_minutes(b.exit_lo, tk, M["done"], M["files"], trees, cache)
        if mb is not None and len(mb):
            out[b.eid] = mb
    return out


def stop_table(recs: list, smas_of, sight: Sightings, levels=STOP_LEVELS + STOP_CONTROLS, variants=STOP_VARIANTS, exit_minutes=None) -> dict:
    """{(level, variant): {n, any, certain, unresolved, H_cond, H_all, tight}} over `recs` (each with fill, stop_levels)."""
    out = {}
    for L in levels:
        for V in variants:
            n_any = n_cert = n_unres = 0
            tight = []
            for r in recs:
                lvl = r.stop_levels.get(L)
                if lvl is None:
                    continue
                smas = smas_of(r)
                L0 = level_at(r, lvl, 0, smas)
                if np.isfinite(L0) and r.fill:
                    tight.append((r.fill - L0) / r.fill)
                h = held_through(r, L, V, smas, sight, exit_mb=(exit_minutes or {}).get(r.b.eid))
                n_any += int(h["any"]); n_cert += int(h["certain"]); n_unres += int(h["unresolved"])
            out[(L, V)] = dict(n=len(recs), any=n_any, certain=n_cert, unresolved=n_unres,
                               H_cond=(n_cert / n_any) if n_any else float("nan"), H_all=(n_cert / len(recs)) if recs else float("nan"),
                               tight=float(np.median(tight)) if tight else float("nan"), eligible=n_any >= STOP_MIN_TRADED)
    return out


def choose_stop(table: dict, levels=STOP_CHOOSABLE, variants=STOP_VARIANTS) -> tuple:
    """His stop ~ the tightest eligible level (>= 20 traded through, a median width BELOW the fill — a level at or above the fill is no stop)
    with H_cond <= 10%, per variant, among S1-S7 (S8 and the 50-day are controls, never "his stop": §7b, check L1); overall the tighter
    of the two (ties -> T). -> ((level, variant) or None, {variant: (level or None)})."""
    per = {}
    for V in variants:
        cands = [(table[(L, V)]["tight"], L) for L in levels
                 if table[(L, V)]["eligible"] and table[(L, V)]["H_cond"] <= STOP_H_CHOOSE and np.isfinite(table[(L, V)]["tight"]) and table[(L, V)]["tight"] > 0]
        per[V] = min(cands)[1] if cands else None
    both = [(table[(per[V], V)]["tight"], 0 if V == "T" else 1, per[V], V) for V in variants if per[V]]
    return ((min(both)[2], min(both)[3]) if both else None), per


def stop_verdict(fit_table: dict, chk_table: dict, chosen: "tuple | None") -> tuple:
    """§7's verdict, on the undated 2021-22 check ALONE (`chk_table`, every level and variant): the chosen level must keep H_cond <= 15% there,
    the ordering (Spearman) and the falsifier read the same table. The dated 2021-22 trades never enter it (re-check N1, option b: the EXIT
    fit walks those 111 under the chosen stop before --check, so their held-through rate is readable from its files; they are printed
    beside on every level and variant). Check M2's combining rule is superseded."""
    if chosen is None:
        return "INCONCLUSIVE", ["no level met H_cond <= 10% on the fit"]
    L, V = chosen
    reasons = []
    hc = chk_table[chosen]["H_cond"]
    if not hc <= STOP_H_PASS:
        reasons.append(f"{L}-{V} H_cond on the undated check {pct(hc)} > {pct(STOP_H_PASS)}")
    fit_o = [fit_table[(l, V)]["H_cond"] for l in STOP_LEVELS]
    chk_o = [chk_table[(l, V)]["H_cond"] for l in STOP_LEVELS]
    ok = [i for i in range(len(STOP_LEVELS)) if np.isfinite(fit_o[i]) and np.isfinite(chk_o[i])]
    rho = spearman([fit_o[i] for i in ok], [chk_o[i] for i in ok]) if len(ok) >= 3 else float("nan")
    if not rho >= STOP_SPEARMAN:
        reasons.append(f"ordering of the levels by H not preserved (Spearman {rho:.2f} < {STOP_SPEARMAN})")
    if not reasons:
        return "PASS", [f"Spearman {rho:.2f}"]
    if all(chk_table[(l, v)]["H_cond"] > STOP_H_FALSIFY for l in STOP_LEVELS for v in STOP_VARIANTS if np.isfinite(chk_table[(l, v)]["H_cond"])):
        return "FAIL", reasons + ["every level has H_cond > 30% on the check: his stop is not a fixed price level"]
    return "INCONCLUSIVE", reasons


def stop_walk(rec: Rec, lvl, variant: str, smas: dict, J: int) -> tuple:
    """§7c: the stop's actual exit before or at session J (his exit), else the close of J. Variant T: a session opening under the level exits at
    its open (the gap), else a low at the level exits at the level; day 0 after the fill on the minutes. Variant C: a close below the level
    exits at the NEXT session's open (the close of J when there is none). -> (j, price, kind) with kind stop | stop_gap | stop_close | mark."""
    L0 = level_at(rec, lvl, 0, smas)
    if variant == "T":
        d0 = day0_for(rec, rec.fill_minute, L0) if np.isfinite(L0) else dict(cb._NO_DAY0)
        if d0.get("stopped"):
            return 0, float(d0["exit_price"]), "day0_gap" if float(d0["exit_price"]) < L0 else "day0_stop"
    for j in range(1, J + 1):
        k = rec.bar_at(j)
        if k is None:
            kk = rec.bar_at(j - 1)
            return j - 1, float(rec.bars.c[kk]), "mark_hole"
        L = level_at(rec, lvl, j, smas)
        if not np.isfinite(L):
            continue
        if variant == "T":
            if float(rec.bars.o[k]) < L:
                return j, float(rec.bars.o[k]), "stop_gap"
            if float(rec.bars.l[k]) <= L:
                return j, L, "stop"
        else:
            kp = rec.bar_at(j - 1)
            Lp = level_at(rec, lvl, j - 1, smas)
            if np.isfinite(Lp) and float(rec.bars.c[kp]) < Lp:
                return j, float(rec.bars.o[k]), "stop_close"
    kJ = rec.bar_at(J)
    if variant == "C" and kJ is not None and J >= 0:
        LJ = level_at(rec, lvl, J, smas)
        if np.isfinite(LJ) and float(rec.bars.c[kJ]) < LJ:
            kn = rec.bar_at(J + 1)
            if kn is not None:
                return J + 1, float(rec.bars.o[kn]), "stop_close"
    return J, float(rec.bars.c[kJ]) if kJ is not None else float("nan"), "mark"


def make_simple_trade(rec: Rec, j: int, px: float, kind: str, width: float, map_b, cal_len: int) -> "rp.Trade | None":
    """One sell leg at session j (open / intraday / close by kind) for the account simulation; width sizes the position."""
    if not (np.isfinite(px) and width > 0):
        return None
    ci = int(rec.cidx[rec.e]) + j
    if ci >= cal_len:
        return None
    order = ORDER_OPEN if kind in ("stop_gap", "stop_close", "trail", "gap_open") else ORDER_CLOSE if kind in ("mark", "mark_hole", "mark_break", "cut", "sell_close", "partial") else ORDER_INTRADAY
    fill, stop = float(rec.fill), float(rec.fill) * (1.0 - width)
    legs = [(ci, order, 1.0, float(px), kind, j)]
    rs = tuple(rp.r_with_slip(legs, fill, stop, s) for s in EXIT_SLIPS)
    path = np.asarray(rec.bars.c[rec.e:rec.e + j + 1], dtype=float)
    if len(path) < j + 1:
        return None
    t = rp.Trade(key=(rec.b.era, rec.b.ticker, rec.b.E), ticker=rec.b.ticker, era=rec.b.era, e_ci=int(rec.cidx[rec.e]), fill_minute=int(rec.fill_minute or 0),
                 fill=fill, stop=stop, width=width, status=kind, mature=True, realized_r=rs[0], r_slip=rs, sessions_held=j, legs=legs, path_c=path,
                 retrigger=rec.b.retrigger, year=rec.b.year, month=rec.b.E[:7])
    return H.to_unified(t, map_b)


def risk_lines(say, label: str, trades: list, cal_u: list, w0: int) -> dict:
    """§7c's readout: the realised-R distribution of stop-outs, the largest single-trade loss as % of equity, the account's max drawdown."""
    stops = [t for t in trades if t.status.startswith("stop") or t.status.startswith("day0")]
    r = np.array([t.realized_r for t in stops], dtype=float)
    loss_pct = [min(CAP30.risk / t.width, CAP30.cap) * (t.legs[0][3] / t.fill - 1.0) for t in trades]
    sim = rp.simulate(trades, CAP30, [date.fromisoformat(d) for d in cal_u], w0) if trades else None
    out = dict(n=len(trades), stops=len(stops), worst=float(r.min()) if len(r) else float("nan"), p5=float(np.percentile(r, 5)) if len(r) else float("nan"),
               beyond_1_5=float(np.mean(r < -1.5)) if len(r) else float("nan"), beyond_2=float(np.mean(r < -2.0)) if len(r) else float("nan"),
               worst_loss_pct=float(min(loss_pct)) if loss_pct else float("nan"), max_dd=sim["max_dd"] if sim else float("nan"), final=sim["final"] if sim else float("nan"))
    say(f"    {label}: trades {out['n']}, stop-outs {out['stops']}; realised R of stop-outs worst {out['worst']:+.2f}, 5th pct {out['p5']:+.2f}, beyond -1.5R "
        f"{pct(out['beyond_1_5'])}, beyond -2R {pct(out['beyond_2'])}; largest single-trade loss {pct(out['worst_loss_pct'], 2)} of equity; account max DD {pct(out['max_dd'])}, final {out['final']:.3f}")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# EXIT — per-day features, the decision list, the logistic hazard, the family choice, the three accounts
# ═════════════════════════════════════════════════════════════════════════════════════════════
XFEATS = tuple(f"X{k}" for k in range(1, 11))


def exit_features(rec: Rec, J: int, smas: dict) -> "np.ndarray | None":
    """[J + 1, 10] over sessions j = 0..J (consecutive bars only; None when a hole precedes J): X1 close vs SMA10 · X2 vs SMA20 (ADR20 units) ·
    X3 red close · X4 close below the prior low · X5 sessions held · X6 the open gap vs the prior close · X7 R at the close · X8 the give-back
    from the max R (highs) · X9 QQQ red day · X10 the day's range."""
    bars, e, p = rec.bars, rec.e, rec.p
    fill, stop, adr = float(rec.fill), float(rec.stop), rec.adr20
    risk = fill - stop
    rows = []
    maxr = -np.inf
    for j in range(J + 1):
        k = rec.bar_at(j)
        if k is None:
            return None
        c, o, h, l = float(bars.c[k]), float(bars.o[k]), float(bars.h[k]), float(bars.l[k])
        cp, lp = float(bars.c[k - 1]), float(bars.l[k - 1])
        px = c * adr
        maxr = max(maxr, (h - fill) / risk)
        rj = (c - fill) / risk
        q, qp = rec.qqq_c[k], rec.qqq_c[k - 1]
        rows.append([(c - smas[10][k]) / px if np.isfinite(smas[10][k]) else 0.0, (c - smas[20][k]) / px if np.isfinite(smas[20][k]) else 0.0,
                     float(c < cp), float(c < lp), float(j), (o - cp) / (cp * adr), rj, maxr - rj,
                     float(q < qp) if (np.isfinite(q) and np.isfinite(qp)) else 0.0, (h - l) / px])
    return np.asarray(rows, dtype=float)


def cond_fire(X: np.ndarray, cond: tuple) -> np.ndarray:
    feat, op, thr = cond
    x = X[:, XFEATS.index(feat)]
    return (x <= thr) if op == "<=" else (x >= thr) if op == ">=" else (x == thr)


def rule_fire_day(X: np.ndarray, rule: tuple) -> int:
    """The first session j where every condition of the rule holds, else a large number."""
    m = np.ones(len(X), dtype=bool)
    for cond in rule:
        m &= cond_fire(X, cond)
    hits = np.flatnonzero(m)
    return int(hits[0]) if len(hits) else 10 ** 6


def all_rules() -> list:
    """Singles and pairs of distinct grid conditions (never two on the same feature with the same direction)."""
    g = list(EXIT_GRID)
    rules = [(c,) for c in g]
    for i in range(len(g)):
        for j in range(i + 1, len(g)):
            if g[i][0] == g[j][0] and g[i][1] == g[j][1]:
                continue
            rules.append((g[i], g[j]))
    return rules


def rule_text(rule: tuple) -> str:
    return " & ".join(f"{f}{op}{thr:g}" if op != "==" else f"{f}" for f, op, thr in rule)


def list_text(lst: list) -> str:
    return "list: " + " ; ".join(rule_text(r) for r in lst)


def fit_decision_list(fires: np.ndarray, lo: np.ndarray, hi: np.ndarray, scor: np.ndarray, rules: list, max_rules: int = EXIT_MAX_RULES) -> tuple:
    """`fires` [n_rules, n_trades] = each rule's first firing session; a list's sell session = the min over its rules; hit = inside [lo, hi] on
    the scorable trades. The list with the highest hit rate; ties -> fewer rules, fewer conditions, order. -> (list of rules, hit rate)."""
    nR, nT = fires.shape
    scor_idx = np.flatnonzero(scor)
    if not len(scor_idx):
        return [], float("nan")
    F = fires[:, scor_idx]
    L, Hh = lo[scor_idx], hi[scor_idx]
    ncond = np.array([len(r) for r in rules])

    def hits(sell):
        return ((sell >= L) & (sell <= Hh)).sum(axis=-1)
    best = (-1, 0, 0, ())
    h1 = hits(F)
    for i in np.argsort(-h1, kind="stable"):
        cand = (int(h1[i]), -1, -int(ncond[i]), (int(i),))
        if cand > best:
            best = cand
        break
    if max_rules >= 2:
        for a in range(nR):
            Fa = F[a]
            if a + 1 < nR:
                M2 = np.minimum(Fa[None, :], F[a + 1:])
                h2 = hits(M2)
                j = int(np.argmax(h2))
                cand = (int(h2[j]), -2, -int(ncond[a] + ncond[a + 1 + j]), (a, a + 1 + j))
                if cand > best:
                    best = cand
                if max_rules >= 3:
                    for i2, b in enumerate(range(a + 1, nR)):
                        if b + 1 < nR:
                            M3 = np.minimum(M2[i2][None, :], F[b + 1:])
                            h3 = hits(M3)
                            k = int(np.argmax(h3))
                            cand = (int(h3[k]), -3, -int(ncond[a] + ncond[b] + ncond[b + 1 + k]), (a, b, b + 1 + k))
                            if cand > best:
                                best = cand
    ids = best[3]
    return [rules[i] for i in ids], best[0] / len(scor_idx)


def list_sell_day(X: np.ndarray, lst: list) -> int:
    return min((rule_fire_day(X, r) for r in lst), default=10 ** 6)


def hazard_loglik_grad(theta: np.ndarray, Xs: list, lo: np.ndarray, hi: np.ndarray, lam: float = RIDGE_LAMBDA) -> tuple:
    """The interval-censored log-likelihood (+ the L2 penalty on the weights) and its gradient. Xs[t] = [J_t + 1, 11] (standardised features
    + a 1 for the intercept); the sale fell in [lo_t, hi_t] (session offsets; hi_t < 0 = still held: the trade contributes S(last))."""
    w = theta
    ll, grad = 0.0, np.zeros_like(theta)
    for X, a, b in zip(Xs, lo, hi):
        z = X @ w
        h = 1.0 / (1.0 + np.exp(-z))
        log1m = np.log1p(-np.clip(h, 1e-12, 1 - 1e-12))
        logS = np.cumsum(log1m)                        # logS[k] = log S(k)
        G = np.cumsum(h[:, None] * X, axis=0)          # G[k] = sum_{j<=k} h_j x_j  (d logS(k) / dw = -G[k])
        if b < 0:
            k = len(X) - 1
            ll += logS[k]
            grad -= G[k]
            continue
        a, b = int(a), int(min(b, len(X) - 1))
        Sa = 1.0 if a == 0 else math.exp(logS[a - 1])
        Sb = math.exp(logS[b])
        P = max(Sa - Sb, 1e-300)
        dP = (-Sa * G[a - 1] if a > 0 else 0.0) + Sb * G[b]
        ll += math.log(P)
        grad += dP / P
    pen = np.ones_like(theta) * lam
    pen[-1] = 0.0
    ll -= 0.5 * float(np.sum(pen * theta ** 2))
    grad -= pen * theta
    return ll, grad


def fit_hazard(Xs_raw: list, lo: np.ndarray, hi: np.ndarray, lam: float = RIDGE_LAMBDA, iters: int = 200) -> dict:
    """Standardise on the fit trade-days, then maximise the penalised interval-censored likelihood by damped Newton (numerical Hessian from the
    analytic gradient; 11 parameters). -> {w, mu, sd, loglik, iters}."""
    allX = np.vstack(Xs_raw)
    mu, sd = allX.mean(axis=0), allX.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    Xs = [np.hstack(((X - mu) / sd, np.ones((len(X), 1)))) for X in Xs_raw]
    th = np.zeros(allX.shape[1] + 1)
    th[-1] = -1.5
    ll, g = hazard_loglik_grad(th, Xs, lo, hi, lam)
    n_it = 0
    for n_it in range(1, iters + 1):
        eps = 1e-5
        Hm = np.zeros((len(th), len(th)))
        for i in range(len(th)):
            d = np.zeros_like(th)
            d[i] = eps
            _l, g2 = hazard_loglik_grad(th + d, Xs, lo, hi, lam)
            Hm[:, i] = (g2 - g) / eps
        Hm = 0.5 * (Hm + Hm.T) - 1e-6 * np.eye(len(th))
        try:
            step = np.linalg.solve(Hm, g)
        except np.linalg.LinAlgError:
            step = -g
        if np.dot(step, g) > 0:
            step = -step
        step = -step
        t = 1.0
        while t > 1e-6:
            th2 = th + t * step
            ll2, g2 = hazard_loglik_grad(th2, Xs, lo, hi, lam)
            if ll2 >= ll - 1e-12:
                break
            t *= 0.5
        if ll2 < ll:
            break
        th, ll, g = th2, ll2, g2
        if np.abs(g).max() < 1e-6 or np.abs(t * step).max() < 1e-9:
            break
    return dict(w=th, mu=mu, sd=sd, loglik=float(ll), iters=n_it)


def hazard_sell_day(X_raw: np.ndarray, model: dict) -> int:
    """The predicted MEDIAN exit: the first session j where the cumulative sale probability 1 - S(j) reaches 0.5 (a large number when it never does)."""
    X = np.hstack(((X_raw - model["mu"]) / model["sd"], np.ones((len(X_raw), 1))))
    h = 1.0 / (1.0 + np.exp(-(X @ model["w"])))
    S = np.cumprod(1.0 - h)
    hits = np.flatnonzero(1.0 - S >= 0.5)
    return int(hits[0]) if len(hits) else 10 ** 6


def trivial_sell_days(X: np.ndarray) -> dict:
    """§3's trivial exits as session OFFSETS from the buy day (buy day = session 1 = offset 0): 'the close of session 3' = offset 2; 'the first
    red close' = the first red close from session 2 on (the buy day's own close is not scored) — check L7."""
    red = np.flatnonzero(X[TRIVIAL_RED_FROM:, 2] > 0) + TRIVIAL_RED_FROM
    return {"close_of_session_3": TRIVIAL_SESSION, "first_red_close": int(red[0]) if len(red) else 10 ** 6}


def break_horizon(rec: Rec, guards: dict, horizon: int = HORIZON) -> tuple:
    """(max_j, why): the last session offset a walk may read — the forward window as the speed trail has it (`cb.forward_window`, cut before
    the first missing session) then cut at the ticker's identity break (`rp.cut_at_break`), so the chosen and his accounts stop where ours
    stops (check L2). `why` = "break" when the identity break shortened it, "hole" when a missing session did, "" otherwise. Asks the
    guard first (the window is forward)."""
    if rec.guard is not None:
        rec.guard.forward(rec.b, 1, f"{rec.b.sym} eid {rec.b.eid}")
    fwd, cut = cb.forward_window(rec.bars, rec.cidx, rec.e, horizon)
    n0 = len(fwd)
    fwd, brk = rp.cut_at_break(fwd, rec.bars.dates[rec.e], guards.get(rec.b.ticker) if guards else None)
    return len(fwd), ("break" if (brk and len(fwd) < n0) else "hole" if cut else "")


def exit_walk(rec: Rec, sell_day_fn, stop_lvl, stop_variant: str, smas: dict, horizon: int = HORIZON) -> tuple:
    """The chosen rule's forward walk under the chain's stop: per session j >= 1 the stop first (variant T: a gap open under it at the open, a
    low at it at the level; variant C: the prior close below it -> this open), then the rule's sell at the close of the first session it
    names (features along the forward path). Day 0: the day-0 stop (minutes after the fill), else the rule at the close of E. The horizon
    marks at the close of the last session. `stop_lvl` is the level OBJECT: a price, or ('sma', n) read at each session's close (M10).
    `horizon` is already cut at the ticker's identity break by the caller (L2). -> (j, price, kind)."""
    L0 = level_at(rec, stop_lvl, 0, smas)
    if np.isfinite(L0) and stop_variant == "T":
        d0 = day0_for(rec, rec.fill_minute, L0)
        if d0.get("stopped"):
            return 0, float(d0["exit_price"]), "day0_gap" if float(d0["exit_price"]) < L0 else "day0_stop"
    Jmax = 0
    while rec.bar_at(Jmax + 1) is not None and Jmax < horizon:
        Jmax += 1
    X = exit_features(rec, Jmax, smas)
    if X is None:
        return 0, float(rec.bars.c[rec.e]), "mark_hole"
    sell_j = sell_day_fn(X)
    for j in range(0, Jmax + 1):
        k = rec.bar_at(j)
        if j >= 1 and np.isfinite(L0):
            L = level_at(rec, stop_lvl, j, smas)
            if stop_variant == "T" and np.isfinite(L):
                if float(rec.bars.o[k]) < L:
                    return j, float(rec.bars.o[k]), "stop_gap"
                if float(rec.bars.l[k]) <= L:
                    return j, L, "stop"
            elif stop_variant == "C":
                Lp = level_at(rec, stop_lvl, j - 1, smas)
                if np.isfinite(Lp) and float(rec.bars.c[rec.bar_at(j - 1)]) < Lp:
                    return j, float(rec.bars.o[k]), "stop_close"
        if j == sell_j:
            return j, float(rec.bars.c[k]), "sell_close"
    kJ = rec.bar_at(Jmax)
    return Jmax, float(rec.bars.c[kJ]), "mark" if Jmax >= horizon else "mark_hole"


def speed_trail_trade(rec: Rec, M: dict, guards: dict) -> "rp.Trade | None":
    """`ours`: the speed trail (`cb.walk_arms`, the holdings DECIDING exit) under the chain's fill and stop."""
    bars, cidx, e = rec.bars, rec.cidx, rec.e
    width = (rec.fill - rec.stop) / rec.fill
    if not width > 0:
        return None
    d0 = rec.day0 if rec.day0 else day0_for(rec, rec.fill_minute, rec.stop)
    en = {"status": "filled", "reason": None, "fill": float(rec.fill), "stop": float(rec.stop), "fill_minute": int(rec.fill_minute or 0), "width_pct": width,
          "level": float(rec.fill), "day0": d0}
    if rec.guard is not None:
        rec.guard.forward(rec.b, 1, f"{rec.b.sym} eid {rec.b.eid}")       # `forward_window` bypasses `bar_at`: ask the guard explicitly
    fwd, cut = cb.forward_window(bars, cidx, e, HORIZON)
    fwd, _brk = rp.cut_at_break(fwd, bars.dates[e], guards.get(rec.b.ticker))
    raw = cb.walk_arms(en, closes_before=bars.c[:e + 1], fwd=fwd, adr20=rec.adr20, horizon=HORIZON, arms=ARMS)[SPEED_ARM]
    ev = SimpleNamespace(era=rec.b.era, ticker=rec.b.ticker, E=rec.b.E, retrigger=rec.b.retrigger, year=rec.b.year, month=rec.b.E[:7])
    t = rp.make_trade(ev, en, raw, bars, cidx, e, len(fwd))
    return H.to_unified(t, M["map_b"])


def panel_trade(rec: Rec, map_b, cal_len: int, max_j: "int | None" = None, cut_kind: str = "mark_break") -> "rp.Trade | None":
    """`his`: the panel exit at the close of exit_hi, NO stop (the chain's stop sets the size only); truncated at the ticker's last consecutive
    bar and at `max_j` (`break_horizon` — the same cut as ours and chosen; L2), kind `cut_kind` (`mark_break` after an identity break,
    `mark_hole` after a missing session) when it ends before exit_hi."""
    if rec.exit_hi_j is None:
        return None
    width = (rec.fill - rec.stop) / rec.fill
    if not width > 0:
        return None
    j = 0
    cap = rec.exit_hi_j if max_j is None else min(rec.exit_hi_j, max_j)
    while j < cap and rec.bar_at(j + 1) is not None:
        j += 1
    k = rec.bar_at(j)
    return make_simple_trade(rec, j, float(rec.bars.c[k]), "mark" if j == rec.exit_hi_j else cut_kind, width, map_b, cal_len)


def recovery(final_ours: float, final_chosen: float, final_his: float) -> tuple:
    """(recovery share, void reason): (ln chosen - ln ours) / (ln his - ln ours); VOID when his / ours < 1.25 (or <= 1)."""
    if not (final_his > 0 and final_ours > 0 and final_chosen > 0):
        return float("nan"), "a non-positive final equity"
    ratio = final_his / final_ours
    if ratio <= 1.0 or ratio < EXIT_VOID_RATIO:
        return float("nan"), f"his / ours = {ratio:.3f} < {EXIT_VOID_RATIO}"
    return (math.log(final_chosen) - math.log(final_ours)) / (math.log(final_his) - math.log(final_ours)), ""


# ═════════════════════════════════════════════════════════════════════════════════════════════
# WHY — the join (the counts in the dry run), the hand-read sheet, the rates
# ═════════════════════════════════════════════════════════════════════════════════════════════
def why_sheet_rows(joins: list, texts: dict, sn: pd.DataFrame, byeid: dict, year: str = "2020", seed: int = WHY_SEED) -> list:
    """§9's GATE sample: 8 STOPPED, 8 SOLD, 4 PARTIAL unambiguous joins of `year`'s streams, seed 1024, with the caption line (the words within
    30 s) and the nearest frame of that video; the `verdict` column is filled by hand (correct / wrong)."""
    rng = np.random.default_rng(seed)
    pool = [j for j in joins if not j["ambiguous"] and j["upload"].startswith(year)]
    frames = {v: g.sort_values("stream_ts", key=lambda s: s.astype(float)) for v, g in sn.groupby("vid")}
    rows = []
    for cls, n in WHY_SAMPLE.items():
        cand = sorted([j for j in pool if j["cls"] == cls], key=lambda j: (j["video"], j["t"]))
        idx = rng.choice(len(cand), size=min(n, len(cand)), replace=False) if cand else []
        for i in sorted(int(x) for x in idx):
            j = cand[i]
            txt, offs, tim = texts[j["video"]]
            words = [txt[offs[k]:(offs[k + 1] - 1 if k + 1 < len(offs) else len(txt))] for k in range(len(tim)) if abs(tim[k] - j["t"]) <= WHY_WINDOW_S]
            fr = frames.get(j["video"])
            frame = ""
            if fr is not None and len(fr):
                st = fr["stream_ts"].astype(float).to_numpy()
                frame = f"{fr.iloc[int(np.argmin(np.abs(st - j['t'])))]['frame_id']} ({fr.iloc[int(np.argmin(np.abs(st - j['t'])))]['folder']})"
            b = byeid[j["eids"][0]]
            rows.append(dict(n=len(rows) + 1, cls=cls, video=j["video"], upload=j["upload"], t_seconds=round(j["t"], 1),
                             t_hhmmss=f"{int(j['t']) // 3600}:{(int(j['t']) % 3600) // 60:02d}:{int(j['t']) % 60:02d}", phrase=j["phrase"],
                             ticker=",".join(j["tickers"]), eid=b.eid, sym=b.sym, buy_day=b.E, exit_lo=b.exit_lo, exit_hi=b.exit_hi, dated=b.dated,
                             caption=" ".join(words), frame=frame, verdict="", note=""))
    return rows


def why_precision(sheet: pd.DataFrame) -> tuple:
    v = sheet["verdict"].astype(str).str.strip().str.lower()
    if not v.isin(("correct", "wrong")).all():
        return float("nan"), "every row needs a verdict of correct / wrong"
    return float((v == "correct").mean()), ""


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the stage runners
# ═════════════════════════════════════════════════════════════════════════════════════════════
def print_pins(say) -> int:
    say("# #705 REVERSE 01 — pins (sha256): paste every line under the doc's freeze marker line after the four fit stages and the keyed CHOSEN lines")
    p = pins()
    for k, v in p.items():
        say(f"- {k}: {v}")
    miss = freeze_missing(DOC, p)
    say(f"- freeze record: {'complete' if not miss else 'NOT YET under the marker: ' + str(len(miss)) + ' of ' + str(len(p)) + ' pins'}")
    absent = [k for k, v in p.items() if v == "ABSENT"]
    say(f"- absent inputs (named, not refused): {', '.join(absent) if absent else 'none'}")
    ch = chosen_lines()
    say("- CHOSEN lines above the marker: " + (", ".join(f"{k.upper()} x{len(v)}" for k, v in sorted(ch.items())) if ch else "none"))
    say.write(P_PINS)
    return 0


def stage_header(say, stage: str, title: str) -> None:
    say(f"# #705 REVERSE 01 — {stage.upper()} FIT: {title}")
    say(f"# registration: {os.path.relpath(DOC, REPO)}; written once; the ledger records this printout")


def load_for_stage(say, C: dict, keep_A: "set | None", keep_B: "set | None") -> dict:
    M = load_markets(say, keep_A, keep_B)
    if M["cal_u"] != C["cal"]:
        raise GuardStop("the unified export calendar differs from the pickle calendar")
    done, files = load_done_all()
    M["done"], M["files"] = done, files
    M["sight"] = Sightings.build(C["sn"])
    M["held"] = H.held_names_by_day(FILES["entries"], [date.fromisoformat(d) for d in C["cal"]])
    return M


def recs_for(buys: list, M: dict, era_fn, guard: BarGuard, want_minutes: bool = True, min_bars: int = REC_MIN_BARS) -> tuple:
    mcache, bcache, out, drop = {}, {}, [], Counter()
    for b in buys:
        era = era_fn(b.E)
        r = make_rec(b, M, era, M["done"], M["files"], mcache, bcache, want_minutes, guard=guard, min_bars=min_bars)
        if r is None:
            drop[rec_drop_reason(b, M, era, bcache, min_bars) or "unknown"] += 1
            continue
        out.append(r)
    return out, drop


def fit_set_violation(stage: str, b: Buy) -> "str | None":
    """H1: the registered fit set of each stage, as a predicate on one buy (None = the buy belongs). SELECT: exact-day non-flicker no-event or
    never-a-candidate buys of 2020 after §2b. ENTER: in-session brackets of 2020 (dated deciding, or exact-day undated). STOP: dated deciding
    2020, or exact-day undated 2020 (flickers included). EXIT: any dated deciding trade with a known exit (every year — §10's in-sample
    reading), or exact-day undated 2020."""
    gate = b.type_ok and not b.inverted and not b.same_day_rebuy and not b.initial
    in_fit = FIT_WIN[0] <= b.E <= FIT_WIN[1]
    if not gate:
        return "fails the §2b gate (type / inverted / same-day re-buy)"
    if stage == "select":
        ok = (not b.dated) and in_fit and b.wl == 1 and not b.flicker and (b.noev or b.undated_reason == "never_candidate")
    elif stage == "enter":
        ok = in_fit and b.in_bracket and (b.decides if b.dated else (b.noev and b.wl == 1 and not b.flicker))
    elif stage == "stop":
        ok = in_fit and (b.decides if b.dated else (b.noev and b.wl == 1))
    elif stage == "exit":
        ok = (b.decides and b.has_exit) if b.dated else (in_fit and b.noev and b.wl == 1)
    else:
        raise ValueError(stage)
    return None if ok else f"not in the registered {stage.upper()} fit set ({'dated' if b.dated else 'undated'} {b.E}, window {b.wl}, flicker {b.flicker})"


def assert_fit_set(say, stage: str, buys: list) -> set:
    """Guard (5), first half (H1): the stage's fit set holds ONLY the registered fit trades; STOP otherwise. -> the fit eids (the BarGuard's
    allowed set: each record's own horizon is unbounded inside it, the buy day outside it)."""
    bad = [(b.eid, b.sym, b.E, fit_set_violation(stage, b)) for b in buys if fit_set_violation(stage, b)]
    if bad:
        raise GuardStop(f"the {stage.upper()} fit set holds {len(bad)} trade(s) outside the registered fit set: " + "; ".join(f"{s} {e} eid {i}: {w}" for i, s, e, w in bad[:5]))
    eids = {b.eid for b in buys}
    say(f"- fit set composition asserted (guard 5): {len(eids)} trades, every one in the registered {stage.upper()} fit set; the forward-bar guard allows these eids only")
    return eids


def smas_for(rec: Rec, cache: dict) -> dict:
    k = (id(rec.bars),)
    hit = cache.get(k)
    if hit is None or hit[0] is not rec.bars:                # holds the array (see feature_table_for): an id is never reused while cached
        hit = (rec.bars, {10: sma_series(rec.bars, 10), 20: sma_series(rec.bars, 20), 50: sma_series(rec.bars, 50)})
        cache[k] = hit
    return hit[1]


def apply_chain(recs: list, chosen_level: "str | None", chosen_stop: "tuple | None", smas_cache: dict, flag_fallback: bool = True,
                registered_fill_eids: "set | None" = None) -> Counter:
    """ENTER's fill then STOP's level on every record (the registered readings where a stage did not pass or has not run).
    `registered_fill_eids` (M4): trades that carry the REGISTERED fill whatever the chosen level — inside the EXIT fit the dated 2021-22
    in-session brackets, ENTER's dated check set, so the chosen level's feasibility on them is never computed before --check; flagged
    `fill_checkwin_registered`, counted. `r.stop` = the chosen stop's buy-day price (sizing, the R unit); `r.stop_lvl` = the level object the
    walks follow (M10: a moving-average stop moves)."""
    c = Counter()
    protect = registered_fill_eids or set()
    for r in recs:
        if r.b.eid in protect:
            chain_fill(r, None)
            r.fill_checkwin_registered = True
            c["fill_checkwin_registered"] += 1
        else:
            chain_fill(r, chosen_level)
        c["fill_" + r.fill_src] += 1
        c["fill_fallback"] += int(r.fill_fallback)
        s1_minute = r.fill_minute if (r.fill_src.startswith("level") or r.fill_src.startswith("orh5")) else None
        r.stop_levels = stop_levels(r, s1_minute)
        c["S1_is_S2"] += int(r.stop_levels.get("S1_is_S2", False))
        smas = smas_for(r, smas_cache)
        if chosen_stop:
            r.stop_lvl = r.stop_levels[chosen_stop[0]]
            r.stop, r.stop_src = level_at(r, r.stop_lvl, 0, smas), f"{chosen_stop[0]}-{chosen_stop[1]}"
        else:
            r.stop, r.stop_src = (r.stop_levels["S1"], "S1-T") if r.b.dated else (r.fill * (1.0 - r.adr20), "ADR20-T")
            r.stop_lvl = r.stop
        if not (np.isfinite(r.stop) and r.stop < r.fill):
            r.stop, r.stop_src = r.fill * (1.0 - r.adr20), r.stop_src + "->ADR20"
            r.stop_lvl = r.stop
            c["stop_above_fill_fallback"] += 1
        r.day0 = day0_for(r, r.fill_minute, r.stop)          # re-check N2: ALWAYS against the chain's actual stop (registered_fill's undated
                                                              # result is a hard-coded 'not stopped'; check_stages' second call changes the stop)
    return c


def assert_populations(say, C: dict) -> None:
    """Guard (3): the §2 / §2b claims re-run quietly at the start of a stage; any mismatch with the doc STOPs before a bar is opened."""
    cl = population_claims(lambda _m: None, C)
    if cl.bad:
        raise GuardStop("POPULATION MISMATCH with the registration: " + "; ".join(f"[L{ln}] {lab}: doc {fmt_claim(d)} vs {fmt_claim(m)}" for ln, lab, d, m in cl.bad))
    say(f"- populations re-asserted against §2 / §2b / §6 / §8 / §10: {cl.n} claims, every one equals the registration (guard 3)")


def run_fit_stage(stage: str, say) -> int:
    exo = stage_outputs(stage)
    if exo:
        print(f"REFUSED: output(s) already on disk: {exo} (each fit writes once; after a STOPPED run, recovery = the fix, then delete the STOPPED file by hand)", file=sys.stderr)
        return 2
    try:
        check_pinned_inputs(say)
        if not dry_run_complete():
            raise GuardStop("the dry run has not COMPLETED (01_rev_dryrun.txt missing, or its last line is not DRY RUN COMPLETE): populations, the caption "
                            "chain, the minute coverage and the fetch list are asserted there before any bar is opened (guard 3; check L3)")
        C = load_core(say)
        assert_populations(say, C)
        rc = {"select": select_fit, "enter": enter_fit, "stop": stop_fit, "exit": exit_fit}[stage](say, C)
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


# ---- SELECT fit --------------------------------------------------------------------------------------------------------------------------
def percentile_with(r: float, others: np.ndarray) -> float:
    """The share of `others` below r plus half the ties, r itself included (the F15 / F16 definition of §5b)."""
    if not np.isfinite(r):
        return float("nan")
    allv = np.concatenate((others[np.isfinite(others)], [r]))
    return float((np.sum(allv < r) + 0.5 * np.sum(allv == r)) / len(allv))


def place_windows(buys: list, M: dict, DA, raw_flat: "np.ndarray | None", qst: dict, by_day: dict, conj_list: list, cal: list, say=None) -> tuple:
    """§5c: each window's sessions scored by the FITTED condition set on their own prior-session bars and open — a session counts as meeting it
    only when the stock also meets the pool floor that day (a session the pool scan could not contain cannot be the placed day) and its
    same-day pool rows exist for F15 / F16 (a session without them is counted `session_pool_empty` and never meets); placed on the LATEST
    meeting session, else lo flagged `placed_by_default`. -> (rows, notes). Reads bars up to each scored session's open: outcome-free."""
    rows, notes, bcache, tcache = [], Counter(), {}, {}
    for b in buys:
        if b.E > A_EXPORT_LAST:
            notes["window_after_era_A_export"] += 1
            continue
        era = select_era_of(b.E)
        bars, cidx = bars_of(M["Ds"][era], b.sym_a if era == "A" else b.sym, bcache)
        if bars is None:
            notes["ticker_not_in_export"] += 1
            continue
        tid = DA.tid.get(b.sym_a)
        raw_c = raw_flat[int(DA.start[tid]):int(DA.stop[tid])] if (tid is not None and raw_flat is not None) else None
        meets = []
        for e_ci in range(b.lo_i, b.hi_i + 1):
            e = int(np.searchsorted(cidx, e_ci))
            if not (e < len(cidx) and int(cidx[e]) == e_ci and e >= cb.MIN_HISTORY):
                meets.append(False)
                notes["session_no_bar_or_short_history"] += 1
                continue
            rec = Rec(b=b, bars=bars, cidx=cidx, e=e, adr20=adr20_at(bars, e - 1, b))
            f = pick_features(rec, raw_c, qst, by_day.get(e_ci), tcache)
            if f["pool_empty"]:
                notes["session_pool_empty"] += 1
                meets.append(False)
                continue
            if not f["floor_ok"]:
                notes["session_fails_pool_floor"] += 1
                meets.append(False)
                continue
            meets.append(bool(set_matches(conj_list, pd.DataFrame([f]))[0]))
            notes["session_scored"] += 1
        k, default = place_window(meets)
        rows.append(dict(eid=b.eid, sym=b.sym, lo=b.lo, hi=b.hi, window_len=b.wl, placed=cal[b.lo_i + k], placed_by_default=default, dated_wide=b.dated))
    return rows, notes


def select_fit(say, C: dict) -> int:
    stage_header(say, "select", "the bar state he buys, against the same-day pool (§5b), the planted-name control (§3), the placement (§5c), the rank fit (§5d)")
    S, cal, CI, EV = C["S"], C["cal"], C["CI"], C["EV"]
    fit_buys = S["sel_fit"] + S["sel_fit_nc"]
    say(f"- fit buys: {len(S['sel_fit'])} exact-day non-flicker no-event 2020 + {len(S['sel_fit_nc'])} never-a-candidate stocks (before the pool floor); flickers beside {len(S['sel_fit_flick'])}")
    fit_eids = assert_fit_set(say, "select", fit_buys)
    M = load_for_stage(say, C, None, {"QQQ", "SPY"})          # era A FULL: the pool is every ticker in the export
    DA = M["DA"]
    raw_flat = load_raw_flat(say, DA)
    qst = qqq_states(DA)
    guard = BarGuard(fit_eids)
    # the pool whose deciles make the grid and whose rows make every pool rate: the FIT BUYS' days only (M6; the check mirrors it)
    fit_days = sorted({CI[b.E] for b in fit_buys})
    t0 = time.time()
    pool = pool_rows_for_days(DA, raw_flat, fit_days, qst, C["small"], C["sic"], M["held"], cal, "A", progress=say)
    say(f"- the pool on the {len(fit_days)} fit days (the days of the fit buys only): {len(pool):,} admitted rows ({pool['ticker'].nunique():,} tickers; per day median "
        f"{int(pool.groupby('day_ci').size().median())}) in {time.time() - t0:.0f}s; rows of names he held that day (excluded from the pool, the pick stays) {int(pool['held'].sum()):,}")
    pool_free = pool[~pool["held"]].reset_index(drop=True)
    by_day = {d: g for d, g in pool_free.groupby("day_ci")}
    # every OTHER day a pick is read on gets its own same-day pool for F15 / F16 only (light rows: no grid, no pool rate) — M5
    other_days = set()
    for b in S["sel_fit_flick"] + S["other_level_fit"] + S["sel_beside"][2017] + S["sel_beside"][2019] + S["dec_used"]:
        if b.E <= A_EXPORT_LAST:
            other_days.add(CI[b.E])
    for b in S["multi_used"] + S["wide"]:
        if b.E <= A_EXPORT_LAST:
            other_days |= set(range(b.lo_i, b.hi_i + 1))
    other_days -= set(fit_days)
    t0 = time.time()
    pool_light = pool_rows_for_days(DA, raw_flat, sorted(other_days), qst, C["small"], C["sic"], M["held"], cal, "A", light=True)
    light_free = pool_light[~pool_light["held"]].reset_index(drop=True) if len(pool_light) else pool_light
    if len(light_free):
        by_day.update({d: g for d, g in light_free.groupby("day_ci")})
    say(f"- same-day pools for the {len(other_days)} other days read (flicker, beside, positive-control and window sessions): {len(light_free):,} light rows "
        f"(returns only; they enter no grid and no pool rate) in {time.time() - t0:.0f}s")
    # his picks' features
    recs, drop = recs_for(fit_buys, M, select_era_of, guard, want_minutes=False)
    say(f"- pick records: {len(recs)} (dropped {dict(drop)}; the record floor = {REC_MIN_BARS} bars before the buy day)")
    tcache = {}
    rows = []
    for r in recs:
        tid = DA.tid[r.b.sym_a]
        a, bnd = int(DA.start[tid]), int(DA.stop[tid])
        f = pick_features(r, raw_flat[a:bnd], qst, by_day.get(CI[r.b.E]), tcache)
        f.update(eid=r.b.eid, ticker=r.b.sym_a, day=r.b.E, day_ci=CI[r.b.E], flicker=r.b.flicker, nc=r.b.undated_reason == "never_candidate", sec_type=r.b.sec_type)
        rows.append(f)
    picks = pd.DataFrame(rows)
    if len(picks) and picks["pool_empty"].any():
        raise GuardStop(f"{int(picks['pool_empty'].sum())} fit buy day(s) have no pool rows: F15 / F16 cannot be read")
    floor_fail = picks[~picks["floor_ok"]]
    say(f"- §2b step 5: picks failing the pool's floor on the prior session: {len(floor_fail)} (" + ", ".join(f"{k} {v}" for k, v in sorted(Counter(floor_fail['floor_reason']).items())) + ") -> kept out of recall")
    picks = picks[picks["floor_ok"]].reset_index(drop=True)
    say(f"- fit buys in recall: {len(picks)} (no-event {int((~picks['nc']).sum())}, never-a-candidate {int(picks['nc'].sum())}; no type row {int((picks['sec_type'] == '').sum())})")
    conds = grid_from_pool(pool_free)
    say(f"- the grid: {len(conds)} single conditions (pool deciles x two directions on F1-F16, F17's three states) -> {len(conds)} singles, {len(conds) * (len(conds) - 1) // 2:,} pairs, "
        f"{len(conds) * (len(conds) - 1) * (len(conds) - 2) // 6:,} triples")
    t0 = time.time()
    Pm = cond_matrix(conds, pool_free)
    cs = ConjSearch(conds, pack_bits(Pm), len(pool_free))
    pool_cnt = cs.pool_counts()
    say(f"- pool counts of every conjunction computed in {time.time() - t0:.0f}s ({len(pool_cnt):,} conjunctions; {int((pool_cnt / len(pool_free) <= POOL_RATE_CAP).sum()):,} at pool rate <= 20%; "
        f"a pool rate = the share of the POOLED (ticker, day) rows over the fit days meeting the condition)")
    os.makedirs(OUT_DIR, exist_ok=True)
    np.savez_compressed(f"{OUT_DIR}/select_fit_poolcounts.npz", pool_cnt=pool_cnt, a=cs.a, b=cs.b, c=cs.c)
    Bm = cond_matrix(conds, picks)
    real = choose_condition_set(cs, pool_cnt, pack_bits(Bm), len(picks), cs.P)
    say("\n## THE FIT (§5b): the condition set")
    for t_, rc_, ra_ in zip(real["texts"], real["recall_each"], real["rate_each"]):
        say(f"- {t_}: recall {pct(rc_)}, pool rate {pct(ra_)}, lift {rc_ / ra_ if ra_ else float('inf'):.2f}")
    say(f"- the SET: recall {pct(real['recall'])}, pool rate {pct(real['pool_rate'])} (the union's), lift {real['lift']:.2f}")
    conj_list = [cs.conds_of(i) for i in real["ids"]]
    flags = []
    for conj in conj_list:
        m = set_matches([conj], picks)
        flags.append(short_cluster_flag(picks[m], pool_free))
    say(f"- short-cluster flag `parabolic_short?` per conjunction (median F8 / F9 of its buys above the pool's 95th percentile): {flags}")
    # the planted-name control
    say("\n## THE SEARCH CONTROL (§3): 20 planted sets, one random pool name per fit buy (seed 702, key rev|select|k), drawn from that day's pool rows of names he did not hold")
    planted = []
    for k in range(1, SELECT_PLANTED_RUNS + 1):
        rng = rng_for(f"rev|select|{k}")
        idx = []
        for d in picks["day_ci"].tolist():
            g = by_day.get(d)
            if g is None or not len(g):
                continue
            idx.append(int(g.index[rng.integers(0, len(g))]))
        pl = pool_free.loc[idx].reset_index(drop=True)
        res = choose_condition_set(cs, pool_cnt, pack_bits(cond_matrix(conds, pl)), len(pl), cs.P)
        planted.append(res["recall"])
        say(f"- planted {k:2d}: recall {pct(res['recall'])} at pool rate {pct(res['pool_rate'])} — {' | '.join(res['texts'])}")
    beat = sum(1 for x in planted if real["recall"] > x)
    inconclusive = beat < SELECT_PLANTED_BEAT
    say(f"- the real fit beats {beat} of {SELECT_PLANTED_RUNS} planted runs (needs >= {SELECT_PLANTED_BEAT}) -> {'INCONCLUSIVE: the check is not read' if inconclusive else 'the check may be read'}")
    # beside: without the no-type-row buys; flickers; the other-level buys outside 2021-22 (N3); 2017 / 2019 (2023 listed: era B, no pool built); the positive control
    say("\n## BESIDE")
    m_real = set_matches(conj_list, picks)
    typed = picks["sec_type"] != ""
    say(f"- recall without the no-type-row buys: {pct(m_real[typed].mean()) if typed.any() else '-'} ({int(typed.sum())} buys)")
    nf = ~picks["nc"]
    say(f"- recall on the no-event buys alone: {pct(m_real[nf].mean()) if nf.any() else '-'}; on the never-a-candidate stocks: {pct(m_real[~nf].mean()) if (~nf).any() else '-'}")
    beside_sets = {"flickers 2020": S["sel_fit_flick"],
                   f"other-level buys, the {len(S['other_level_fit'])} of 2019 / 2020 / 2023 (the {len(S['other_level_chk'])} of 2021-22 are read in --check, re-check N3)": S["other_level_fit"], "positive control (the 290 dated): recall": S["dec_used"],
                   "2017": S["sel_beside"][2017], "2019": S["sel_beside"][2019]}
    beside_feats = {}
    for name, bs in beside_sets.items():
        bs_a = [b for b in bs if b.E <= A_EXPORT_LAST]
        rr, _d = recs_for(bs_a, M, select_era_of, guard, want_minutes=False)
        rows = []
        for r in rr:
            tid = DA.tid.get(r.b.sym_a)
            if tid is None:
                continue
            a, bnd = int(DA.start[tid]), int(DA.stop[tid])
            f = pick_features(r, raw_flat[a:bnd], qst, by_day.get(CI[r.b.E]), tcache)
            f.update(eid=r.b.eid, day_ci=CI[r.b.E])
            rows.append(f)
        if not rows:
            say(f"- {name}: no scorable buy")
            continue
        df = pd.DataFrame(rows)
        beside_feats[name] = df
        m = set_matches(conj_list, df)
        say(f"- {name}: the condition set fires on {int(m.sum())} of {len(df)} ({pct(m.mean())}); pool floor met by {int(df['floor_ok'].sum())}; same-day pool missing {int(df['pool_empty'].sum())}"
            + (f"; {len(bs) - len(bs_a)} after the era-A export's end not scored" if len(bs) != len(bs_a) else ""))
    b23 = S["sel_beside"][2023]
    say(f"- 2023 ({len(b23)} exact-day non-flicker buys): LISTED, not scored — era B, whose pool this stage does not build: " + ", ".join(f"{b.sym} {b.E}" for b in b23))
    # §5c placement of the 2-10-session windows (the fitted condition set; the latest session meeting it, else lo flagged placed_by_default)
    say("\n## PLACEMENT (§5c): the 2-10-session windows (never fit material; beside in ENTER / STOP / EXIT)")
    placed, pnotes = place_windows(S["multi_used"] + S["wide"], M, DA, raw_flat, qst, by_day, conj_list, cal)
    PL = pd.DataFrame(placed)
    say(f"- sessions: " + ", ".join(f"{k} {v}" for k, v in sorted(pnotes.items())))
    if len(PL):
        say(f"- placed {len(PL)} windows: by the condition set {int((~PL['placed_by_default']).sum())}, on lo by default {int(PL['placed_by_default'].sum())} "
            f"(dated-but-wider beside: {int(PL['dated_wide'].sum())})")
        PL.to_csv(f"{OUT_DIR}/select_fit_placed.tsv", sep="\t", index=False)
        ledger_append("select-fit", f"{OUT_DIR}/select_fit_placed.tsv")
    # §5d the rank fit: logistic on the 2020 buys vs the 2020 qualifying pool
    say("\n## RANK FIT (§5d): logistic (L2, lambda 1, standardised) on the 2020 buys vs the 2020 qualifying pool rows")
    qual_pool = pool_free[set_matches(conj_list, pool_free)]
    X = np.vstack((rank_design(picks[m_real]), rank_design(qual_pool)))
    y = np.concatenate((np.ones(int(m_real.sum())), np.zeros(len(qual_pool))))
    rank_model = None
    if m_real.sum() >= 5 and len(qual_pool) >= 20:
        w, b0, mu, sd = ridge_logistic(X, y)
        rank_model = dict(w=w.tolist(), b=b0, mu=mu.tolist(), sd=sd.tolist())
        say(f"- fitted on {int(m_real.sum())} qualifying buys vs {len(qual_pool):,} qualifying pool rows; the largest |weights|: "
            + ", ".join(f"{n} {v:+.2f}" for n, v in sorted(zip(list(NUMERIC) + [f'F17={c}' for c in F17_CATS], w), key=lambda x: -abs(x[1]))[:5]))
        sc_pool = ((rank_design(qual_pool) - mu) / sd) @ w + b0
        pcts = []
        for i in np.flatnonzero(m_real):
            d = picks.loc[i, "day_ci"]
            sp = sc_pool[(qual_pool["day_ci"] == d).to_numpy()]
            spick = float((((rank_design(picks.iloc[[i]]) - mu) / sd) @ w + b0)[0])   # one row -> one score (numpy 2 refuses float() of a 1-element array)
            pcts.append(pick_percentile(spick, sp))
        say(f"- in-sample: his qualifying picks' median percentile within the day's qualifying pool {np.median(pcts):.2f} (read as a baseline; the check reads 2021-22)")
        # beside (§5d): the dated 290 against the `tl` same-day pool — the names our trendline fired on that day, pool floor met, not held, plus the pick
        pos = beside_feats.get("positive control (the 290 dated): recall")
        if pos is not None and len(pos):
            pos_days = sorted(set(pos["day_ci"].tolist()))
            tl_names = sorted({tk for (era, tk), ds in EV["tl"].items() if era == "A" and any(cal[d] in ds for d in pos_days)})
            tl_rows = pool_rows_for_days(DA, raw_flat, pos_days, qst, C["small"], C["sic"], M["held"], cal, "A", tickers=tl_names)
            if len(tl_rows):
                tl_rows = tl_rows[[cal[d] in EV["tl"].get(("A", tk), set()) for tk, d in zip(tl_rows["ticker"], tl_rows["day_ci"])]]
                tl_rows = tl_rows[~tl_rows["held"]].reset_index(drop=True)
                # F15 / F16 of a tl row against the DAY's pool (not against the tl names alone)
                for src, dst in (("ret63", "F15"), ("ret21", "F16")):
                    tl_rows[dst] = [percentile_with(float(r_), by_day[d][src].to_numpy(dtype=float)) if d in by_day else float("nan")
                                    for r_, d in zip(tl_rows[src], tl_rows["day_ci"])]
                sc_tl = ((rank_design(tl_rows) - mu) / sd) @ w + b0 if len(tl_rows) else np.zeros(0)
                pp, n_alone = [], 0
                for i in range(len(pos)):
                    d = int(pos.loc[i, "day_ci"])
                    sp = sc_tl[(tl_rows["day_ci"] == d).to_numpy()]
                    if not len(sp):
                        n_alone += 1
                        continue
                    spick = float((((rank_design(pos.iloc[[i]]) - mu) / sd) @ w + b0)[0])
                    pp.append(pick_percentile(spick, sp))
                say(f"- beside, the positive control (§5d): his dated picks' median percentile within the day's `tl` pool {np.median(pp) if pp else float('nan'):.2f} "
                    f"({len(pp)} picks with >= 1 other tl name that day, pool floor met; {n_alone} alone in their band) — known from the holdings band, disclosed, not used to fit")
    else:
        say("- too few qualifying buys or pool rows for the rank fit; §5d reads INCONCLUSIVE on the check")
    # outputs
    picks.assign(meets=m_real).to_csv(f"{OUT_DIR}/select_fit_buys.tsv", sep="\t", index=False)
    ledger_append("select-fit", f"{OUT_DIR}/select_fit_buys.tsv")
    pool_free.to_csv(f"{OUT_DIR}/select_fit_pool.tsv.gz", sep="\t", index=False, compression="gzip")
    ledger_append("select-fit", f"{OUT_DIR}/select_fit_pool.tsv.gz")
    ledger_append("select-fit", f"{OUT_DIR}/select_fit_poolcounts.npz")
    chosen_text = " | ".join(real["texts"]) if real["texts"] else "none"
    obj = dict(conjunctions=[[(c.feat, c.op, c.thr) for c in conj] for conj in conj_list], recall=real["recall"], pool_rate=real["pool_rate"], lift=real["lift"],
               planted_recalls=planted, beat=beat, inconclusive=inconclusive, short_flags=flags, rank_model=rank_model, grid=[(c.feat, c.op, c.thr) for c in conds],
               n_pool_fit=len(pool_free), n_buys_fit=len(picks))
    write_chosen("select", obj, chosen_text)
    say(f"\nCHOSEN SELECT: {chosen_text}")
    say(f"- (search control: {'INCONCLUSIVE before the check' if inconclusive else 'passed'}; §5b's check reads recall / pool rate / lift of this set on 2021-22 ONCE in --check)")
    return 0


# ---- ENTER fit ---------------------------------------------------------------------------------------------------------------------------
def crossed_lines(say, label: str, recs: list) -> None:
    """§6c's pre-market FIRST sightings (no bracket): per level the share of sessions that crossed it at all (`score_crossed`)."""
    rr = [r for r in recs if r.mb is not None]
    if not rr:
        say(f"- {label}: no scorable trade")
        return
    cnt = Counter()
    for r in rr:
        r.levels = enter_levels(r)
        for L in LEVELS:
            cnt[L] += int(score_crossed(r.mb, r.levels[L])["crossed"])
    say(f"- {label} ({len(rr)} with minutes): crossed that session " + "; ".join(f"{L} {cnt[L]} = {pct(cnt[L] / len(rr))}" for L in LEVELS) + " (the level test degraded to 'crossed that session')")


def enter_fit(say, C: dict) -> int:
    stage_header(say, "enter", "the level he buys at, bounded by the panel clock (§6); the random-level control (§3)")
    S, cal = C["S"], C["cal"]
    sel = read_chosen("select")
    fit = S["ent_fit_dated"] + S["ent_fit_und"]
    fit_fl = [b for b in S["ent_fit_und_fl"] if b.flicker]
    say(f"- fit set: {len(S['ent_fit_dated'])} in-session-bracketed dated + {len(S['ent_fit_und'])} in-session-bracketed exact-day undated buys of 2020 (flickers beside {len(fit_fl)})")
    fit_eids = assert_fit_set(say, "enter", fit)
    M = load_for_stage(say, C, {b.sym_a for b in fit + fit_fl + S['ent_pre_dated'] + S['ent_pre_und'] + S['ent_noflat_dated'] + S['ent_prefirst_dated']} | {"QQQ", "SPY"},
                       {b.sym for b in fit + fit_fl if b.E > A_LAST} | {"QQQ", "SPY"})
    guard = BarGuard(fit_eids)
    recs, drop = recs_for(fit, M, era_of, guard, min_bars=REC_MIN_BARS_ENTER)
    say(f"- records: {len(recs)} (dropped {dict(drop)}; the ENTER record floor = {REC_MIN_BARS_ENTER} bars before the buy day); minutes: "
        + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r.minutes_state.split('/')[0] for r in recs).items())))
    rng = rng_for(RANDOM_KEY)
    scored = {}
    rows = []
    for r in sorted(recs, key=lambda x: (x.b.E, x.b.eid)):
        if r.mb is None:
            rows.append(dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, minutes=r.minutes_state, scorable=False))
            continue
        res = enter_score_trade(r, rng)
        scored[r.b.eid] = res
        row = dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, minutes=r.minutes_state, scorable=True,
                   flat_clock=r.b.flat_clock, first_clock=r.b.first_clock, adr20=r.adr20)
        for L in LEVELS:
            row[f"{L}_price"] = r.levels[L]
            row[f"{L}_cross"] = res[L]["cross"]
            row[f"{L}_feasible"] = res[L]["feasible"]
            row[f"{L}_verdict"] = res[L]["verdict"]
        row.update(control_feasible=res["control"]["feasible_share"], control_hit=res["control"]["hit_share"])
        rows.append(row)
    summ = enter_summary(scored)
    say(f"\n## THE FIT (§6c): {summ['n']} scorable trades ({sum(1 for r in recs if r.mb is None)} without minutes flagged `no_minutes`; a level that does not exist yet at "
        f"first_clock reads `no_level_yet`: L1 before 09:35, L6 before 10:30)")
    for L in LEVELS:
        s_ = summ[L]
        say(f"- {L}: feasible {s_['feasible']} = {pct(s_['feasible_share'][0])} +-{100 * s_['feasible_share'][1]:.0f}; hit-or-ballpark {s_['hit']} = {pct(s_['hit_share'][0])} +-{100 * s_['hit_share'][1]:.0f}; "
            + ", ".join(f"{k} {v}" for k, v in sorted(s_["verdicts"].items())))
    say(f"- random-level control: feasible {pct(summ['control']['feasible_share'])}, hit-or-ballpark {pct(summ['control']['hit_share'])}")
    chosen = choose_level(summ) if summ["n"] else "L1"
    say(f"- held before 09:35 (L1 falsified for them, listed): " + ", ".join(f"{b.sym} {b.E}" for b in inwin(S['dec_used'], DENSE) + S['sel_fit'] + S['sel_chk'] if b.held_before_0935))
    # by subset
    for lab, pred in (("dated", lambda r: r.b.dated), ("undated", lambda r: not r.b.dated)):
        sub = {k: v for k, v in scored.items() if pred(next(r for r in recs if r.b.eid == k))}
        if sub:
            ss = enter_summary(sub)
            say(f"- {lab} ({ss['n']}): " + "; ".join(f"{L} feasible {pct(ss[L]['feasible_share'][0])} hit {pct(ss[L]['hit_share'][0])}" for L in LEVELS))
    # beside: flickers, pre-market-flat brackets, no-flat-frame sightings, pre-market first sightings
    say("\n## BESIDE")
    for lab, bs, kind in (("flickers 2020 (in-session brackets)", fit_fl, "bracket"), ("pre-market-flat brackets, dated", inwin(S["ent_pre_dated"], FIT_WIN), "bracket"),
                          ("pre-market-flat brackets, undated 2020", inwin(S["ent_pre_und"], FIT_WIN), "bracket"), ("no flat frame that day, dated 2020", inwin(S["ent_noflat_dated"], FIT_WIN), "unbracketed"),
                          ("pre-market first sightings, dated 2020", inwin(S["ent_prefirst_dated"], FIT_WIN), "crossed")):
        rr, _d = recs_for(bs, M, era_of, guard, min_bars=REC_MIN_BARS_ENTER)
        rr = [r for r in rr if r.mb is not None]
        if kind == "crossed":
            crossed_lines(say, lab, rr)
            continue
        if not rr:
            say(f"- {lab}: no scorable trade")
            continue
        if kind == "bracket":
            sc = {r.b.eid: enter_score_trade(r, rng) for r in rr}
            ss = enter_summary(sc)
            say(f"- {lab} ({ss['n']}): " + "; ".join(f"{L} feasible {pct(ss[L]['feasible_share'][0])} hit {pct(ss[L]['hit_share'][0])}" for L in LEVELS) + f"; control feasible {pct(ss['control']['feasible_share'])}")
        else:
            cnt = Counter()
            for r in rr:
                r.levels = enter_levels(r)
                fm = hhmm_to_min(r.b.first_clock)
                for L in LEVELS:
                    s_ = score_unbracketed(r.mb, r.levels[L], fm, r.adr20)
                    cnt[(L, s_["verdict"])] += 1
            say(f"- {lab} ({len(rr)}): " + "; ".join(f"{L} crossed-by-first-clock {sum(v for (l, k), v in cnt.items() if l == L and k != 'MISS')}, within 0.5 ADR20 {cnt[(L, 'BALLPARK')]}" for L in LEVELS))
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/enter_fit_trades.tsv", sep="\t", index=False)
    ledger_append("enter-fit", f"{OUT_DIR}/enter_fit_trades.tsv")
    obj = dict(level=chosen, summary={L: dict(feasible=summ[L]["feasible"], hit=summ[L]["hit"]) for L in LEVELS} if summ["n"] else {}, n=summ["n"],
               control=summ["control"], select_short_flags=sel["object"].get("short_flags"))
    write_chosen("enter", obj, chosen)
    say(f"\nCHOSEN ENTER: {chosen}")
    say("- the chain carries this level's price where it is feasible on a trade, else the registered fill (`fill_fallback`); §6's check reads 2021-22 ONCE in --check")
    return 0


# ---- STOP fit ----------------------------------------------------------------------------------------------------------------------------
def after_loss_count(say, recs: list, C: dict, M: dict, chosen_level: "str | None", guard: "BarGuard | None", label: str) -> int:
    """§7b's after-loss flag with the INFERRED fill (L6): a re-buy whose earlier entry's exit-window last close sat below that entry's chain fill
    (the chosen level where feasible, else the registered fill). The earlier entry's exit bars are read under `guard` (fit: its eid must be
    allowed — a 2020 re-buy's earlier entry exited in or before 2020; check: no guard)."""
    byeid = {b.eid: b for b in C["buys"]}
    n_rebuy, after_loss, unread = 0, 0, Counter()
    for r in recs:
        if not r.b.rebuy:
            continue
        n_rebuy += 1
        pb = byeid.get(r.b.rebuy_prev_eid)
        if pb is None or not pb.has_bars:
            unread["earlier_entry_without_bars"] += 1
            continue
        pr = make_rec(pb, M, era_of(pb.E), M["done"], M["files"], {}, {}, guard=guard)
        if pr is None or pr.exit_hi_j is None:
            unread["earlier_entry_without_record_or_exit"] += 1
            continue
        chain_fill(pr, chosen_level)
        k = pr.bar_at(pr.exit_hi_j)
        if k is None:
            unread["earlier_exit_past_a_hole"] += 1
            continue
        after_loss += int(float(pr.bars.c[k]) < pr.fill)
    say(f"- {label}: re-buys {n_rebuy}, of them after a loss (the earlier entry's exit-window last close below its INFERRED fill) {after_loss}"
        + (f"; unread {dict(unread)}" if unread else ""))
    return after_loss


def stop_fit(say, C: dict) -> int:
    stage_header(say, "stop", "which levels he held THROUGH (§7); the risk under a close-based stop (§7c)")
    S, cal = C["S"], C["cal"]
    ent = read_chosen("enter")
    chosen_level = ent["object"]["level"]
    fit_d, fit_u = S["stop_fit_dated"], S["und_fit"]
    say(f"- fit set: dated 2020 {len(fit_d)} + exact-day undated 2020 {len(fit_u)} (flickers included); ENTER's fit level {chosen_level} where feasible, else the registered fill")
    fit_eids = assert_fit_set(say, "stop", fit_d + fit_u)
    byeid = {b.eid: b for b in C["buys"]}
    prev_eids = {b.rebuy_prev_eid for b in fit_d + fit_u if b.rebuy and b.rebuy_prev_eid in byeid}
    assert all(byeid[e].E <= FIT_WIN[1] for e in prev_eids), "a 2020 re-buy's earlier entry after 2020"
    names_A = {b.sym_a for b in fit_d + fit_u} | {"QQQ", "SPY"}
    M = load_for_stage(say, C, names_A, {"QQQ", "SPY"})
    guard = BarGuard(fit_eids | prev_eids)                    # the earlier entries of the 2020 re-buys: their exits are read for the after-loss flag
    recs, drop = recs_for(fit_d + fit_u, M, era_of, guard)
    say(f"- records: {len(recs)} (dropped {dict(drop)}; the record floor = {REC_MIN_BARS} bars before the buy day)")
    g8_run(say, recs, "stop_fit")
    smas_cache = {}
    cc = apply_chain(recs, chosen_level, None, smas_cache)
    say("- the chain's fills: " + ", ".join(f"{k} {v}" for k, v in sorted(cc.items())))
    sight = M["sight"]
    smas_of = lambda r: smas_for(r, smas_cache)   # noqa: E731
    exm = exit_minutes_for(recs, M)
    say(f"- exit-window first sessions with minute bars in a tree (a touch before the last frame's clock counts): {len(exm)} of {sum(1 for r in recs if r.b.has_exit and r.b.exit_lo != r.b.E)}")
    say("\n## THE FIT (§7b): held-through rates, level x variant (H_cond = certain / traded through by exit_hi; H_all = certain / all)")
    tab_all = stop_table(recs, smas_of, sight, exit_minutes=exm)
    tab_d = stop_table([r for r in recs if r.b.dated], smas_of, sight, exit_minutes=exm)
    tab_u = stop_table([r for r in recs if not r.b.dated], smas_of, sight, exit_minutes=exm)
    hdr = ["level-variant", "tightness (median width)", "traded through", "certain", "unresolved", "H_cond", "H_all", "eligible", "dated H_cond", "undated H_cond"]
    rows = []
    for L in STOP_LEVELS + STOP_CONTROLS:
        for V in STOP_VARIANTS:
            t = tab_all[(L, V)]
            rows.append([f"{L}-{V}", pct(t["tight"]), t["any"], t["certain"], t["unresolved"], pct(t["H_cond"]), pct(t["H_all"]), t["eligible"], pct(tab_d[(L, V)]["H_cond"]), pct(tab_u[(L, V)]["H_cond"])])
    for ln in rp.table(hdr, rows):
        say(ln)
    chosen, per = choose_stop(tab_all)
    say(f"- his stop ~ the tightest eligible level among S1-S7 (S8 and the 50-day are controls) with a positive median width and H_cond <= 10%: variant T {per['T']}, variant C {per['C']} "
        f"-> CHOSEN {chosen[0] + '-' + chosen[1] if chosen else 'none'}")
    # re-buys apart; the after-loss flag with the inferred fill (2020 re-buys: the earlier entry's exit is fit-era data)
    rb = [r for r in recs if r.b.rebuy]
    if rb:
        tr = stop_table(rb, smas_of, sight, exit_minutes=exm)
        say(f"- re-buys ({len(rb)}) apart: " + "; ".join(f"{L}-{V} H_cond {pct(tr[(L, V)]['H_cond'])}" for L in STOP_LEVELS for V in STOP_VARIANTS))
    after_loss_count(say, recs, C, M, chosen_level, guard, "2020 fit")
    # §7c risk under each level x variant
    say("\n## RISK (§7c): sized on the level's distance (1% / 30% cap / 30% per stock, no margin), booked at the actual exit; every level sized (no skip rule)")
    w0 = C["CI"][FIT_WIN[0]]
    cal_u = C["cal"]
    risk = {}
    for L in STOP_LEVELS + STOP_CONTROLS:
        for V in STOP_VARIANTS:
            trades, skipped = [], Counter()
            for r in recs:
                if r.exit_hi_j is None:
                    skipped["no_exit"] += 1
                    continue
                lvl = r.stop_levels[L]
                smas = smas_of(r)
                L0 = level_at(r, lvl, 0, smas)
                width = (r.fill - L0) / r.fill if np.isfinite(L0) else float("nan")
                if not width > 0:
                    skipped["level_at_or_above_fill"] += 1
                    continue
                skipped["wider_than_ADR20 (the registered skip, beside)"] += int(width > r.adr20)
                j, px, kind = stop_walk(r, lvl, V, smas, r.exit_hi_j)
                t = make_simple_trade(r, j, px, kind, width, M["map_b"], len(cal_u))
                if t is not None:
                    trades.append(t)
            say(f"- {L}-{V} (skipped: " + ", ".join(f"{k} {v}" for k, v in sorted(skipped.items())) + ")")
            risk[f"{L}-{V}"] = risk_lines(say, "sized on the level", trades, cal_u, w0)
            # same-size variant: shares fixed by S1's width
            trades2 = []
            for r in recs:
                if r.exit_hi_j is None:
                    continue
                lvl = r.stop_levels[L]
                smas = smas_of(r)
                L0 = level_at(r, lvl, 0, smas)
                w1 = (r.fill - r.stop_levels["S1"]) / r.fill
                if not (np.isfinite(L0) and L0 < r.fill and w1 > 0):
                    continue
                j, px, kind = stop_walk(r, lvl, V, smas, r.exit_hi_j)
                t = make_simple_trade(r, j, px, kind, w1, M["map_b"], len(cal_u))
                if t is not None:
                    trades2.append(t)
            if trades2:
                eff = [(r.fill - level_at(r, r.stop_levels[L], 0, smas_of(r))) / (r.fill - r.stop_levels["S1"]) for r in recs
                       if r.exit_hi_j is not None and np.isfinite(level_at(r, r.stop_levels[L], 0, smas_of(r))) and r.stop_levels["S1"] < r.fill]
                say(f"    same-size variant (S1's width sizes the shares; risk per trade {100 * float(np.median(eff)):.1f}% of equity at the median, max {100 * float(np.max(eff)):.1f}%):")
                risk_lines(say, "same size", trades2, cal_u, w0)
    # outputs
    rows = []
    for r in recs:
        row = dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, rebuy=r.b.rebuy, fill=r.fill, fill_minute=r.fill_minute, fill_src=r.fill_src,
                   fill_fallback=r.fill_fallback, adr20=r.adr20, exit_lo=r.b.exit_lo, exit_hi=r.b.exit_hi, minutes=r.minutes_state, S1_is_S2=r.stop_levels.get("S1_is_S2"))
        for L in STOP_LEVELS + STOP_CONTROLS:
            row[f"{L}_level0"] = level_at(r, r.stop_levels[L], 0, smas_of(r))
            for V in STOP_VARIANTS:
                h = held_through(r, L, V, smas_of(r), sight, exit_mb=exm.get(r.b.eid))
                row[f"{L}_{V}_any"], row[f"{L}_{V}_certain"], row[f"{L}_{V}_unresolved"], row[f"{L}_{V}_first_j"] = h["any"], h["certain"], h["unresolved"], h["first_j"]
        rows.append(row)
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/stop_fit_trades.tsv", sep="\t", index=False)
    ledger_append("stop-fit", f"{OUT_DIR}/stop_fit_trades.tsv")
    tab_rows = [dict(level=L, variant=V, **{k: v for k, v in tab_all[(L, V)].items()}) for L in STOP_LEVELS + STOP_CONTROLS for V in STOP_VARIANTS]
    pd.DataFrame(tab_rows).to_csv(f"{OUT_DIR}/stop_fit_levels.tsv", sep="\t", index=False)
    ledger_append("stop-fit", f"{OUT_DIR}/stop_fit_levels.tsv")
    text = f"{chosen[0]}-{chosen[1]}" if chosen else "none"
    obj = dict(level=chosen[0] if chosen else None, variant=chosen[1] if chosen else None, per_variant=per,
               fit_table={f"{L}-{V}": {k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in tab_all[(L, V)].items()} for L in STOP_LEVELS + STOP_CONTROLS for V in STOP_VARIANTS},
               enter_level=chosen_level, risk=risk)
    write_chosen("stop", obj, text)
    say(f"\nCHOSEN STOP: {text}")
    say("- §7's check reads the undated 2021-22 buys on every level and variant ONCE in --check (the chosen level must hold H_cond <= 15% there); dated 2021-22 is printed beside, never deciding (re-check N1)")
    return 0


# ---- EXIT fit ----------------------------------------------------------------------------------------------------------------------------
def exit_rows_for(recs: list, smas_cache: dict, notes: "Counter | None" = None) -> tuple:
    """(Xs, lo, hi, scor, keep): per trade the feature rows over his hold (0..exit_hi_j; still-held: the available path to the horizon), the
    window as session offsets (hi -1 = still held), the hit-rate eligibility (an exit window <= 20 sessions wide). A data hole BEFORE
    exit_lo cuts the rows short of the window: that trade is then read as still held at its last bar (hi = -1, not scorable) and counted in
    `notes["held_to_hole_before_window"]` — never a window past the data, whose P = S(a-1) - S(b) would be negative (check M9). A window
    cut by a hole after exit_lo keeps its rows in the likelihood and leaves the hit rate (`window_cut_by_hole`)."""
    Xs, lo, hi, scor, keep = [], [], [], [], []
    for r in recs:
        smas = smas_for(r, smas_cache)
        if r.exit_hi_j is not None:
            J = r.exit_hi_j
        else:
            J = 0
            while r.bar_at(J + 1) is not None and J < HORIZON:
                J += 1
        X = exit_features(r, J, smas)
        truncated = False
        if X is None:
            # a hole inside his hold: use the consecutive part
            J2 = 0
            while r.bar_at(J2 + 1) is not None and J2 < J:
                J2 += 1
            X = exit_features(r, J2, smas)
            if X is None:
                keep.append(False)
                continue
            truncated = True
        keep.append(True)
        Xs.append(X)
        if r.exit_hi_j is not None and r.exit_lo_j <= len(X) - 1:
            lo.append(r.exit_lo_j)
            hi.append(min(r.exit_hi_j, len(X) - 1))
            scor.append(r.b.exit_window_len() <= EXIT_HIT_MAX_WINDOW and not truncated)
            if truncated and notes is not None:
                notes["window_cut_by_hole"] += 1
        else:
            if r.exit_hi_j is not None and notes is not None:
                notes["held_to_hole_before_window"] += 1
            lo.append(0)
            hi.append(-1)
            scor.append(False)
    return Xs, np.asarray(lo), np.asarray(hi), np.asarray(scor, dtype=bool), np.asarray(keep, dtype=bool)


def exit_rows_for_safe(recs: list, smas_cache: dict) -> tuple:
    """`exit_rows_for` with its notes."""
    notes = Counter()
    Xs, lo, hi, scor, keep = exit_rows_for(recs, smas_cache, notes)
    return Xs, lo, hi, scor, keep, notes


def hit_rate(sell_days: np.ndarray, lo: np.ndarray, hi: np.ndarray, scor: np.ndarray) -> float:
    m = scor & (hi >= 0)
    return float(((sell_days[m] >= lo[m]) & (sell_days[m] <= hi[m])).mean()) if m.any() else float("nan")


def fit_families(say, Xs: list, lo, hi, scor, label: str) -> dict:
    """Both families on the given trades; -> {list, list_hit, hazard, hazard_hit}."""
    rules = all_rules()
    fires = np.array([[rule_fire_day(X, r) for X in Xs] for r in rules], dtype=np.int64)
    lst, lst_hit = fit_decision_list(fires, lo, hi, scor, rules)
    hz = fit_hazard(Xs, lo, hi)
    hz_days = np.array([hazard_sell_day(X, hz) for X in Xs])
    hz_hit = hit_rate(hz_days, lo, hi, scor)
    say(f"- {label}: decision list {list_text(lst)} (hit rate {pct(lst_hit)} on {int(scor.sum())} scorable trades); hazard log-likelihood {hz['loglik']:.1f} "
        f"({hz['iters']} Newton steps; hit rate of its median exit {pct(hz_hit)})")
    return dict(list=lst, list_hit=lst_hit, hazard=hz, hazard_hit=hz_hit, rules=rules)


def choose_family(say, Xs: list, lo, hi, scor, Es: list, label: str) -> dict:
    """§8b's family choice, ONE rule for every fit (the dated-inclusive fit and the undated-only fit alike — L6): both families fit WITHOUT the
    buys of 2020-07-01..12-31, compared on those buys' hit rate (ties -> the list), the winner refit on the whole set given."""
    held = np.array([HOLDOUT[0] <= E <= HOLDOUT[1] for E in Es], dtype=bool)
    tr = ~held
    fam = fit_families(say, [X for X, m in zip(Xs, tr) if m], lo[tr], hi[tr], scor[tr], f"{label}: training part (without 2020-07-01..12-31)")
    Xh = [X for X, m in zip(Xs, held) if m]
    lst_days = np.array([list_sell_day(X, fam["list"]) for X in Xh]) if Xh else np.zeros(0, int)
    hz_days = np.array([hazard_sell_day(X, fam["hazard"]) for X in Xh]) if Xh else np.zeros(0, int)
    lh, hh = hit_rate(lst_days, lo[held], hi[held], scor[held]), hit_rate(hz_days, lo[held], hi[held], scor[held])
    winner = "hazard" if (np.isfinite(hh) and (not np.isfinite(lh) or hh > lh)) else "list"
    say(f"- {label}: held-out hit rates: decision list {pct(lh)}, hazard {pct(hh)} on {int(scor[held].sum())} scorable held-out trades -> the {winner} family wins (ties -> the list)")
    full = fit_families(say, Xs, lo, hi, scor, f"{label}: refit on the whole set")
    return dict(winner=winner, full=full, holdout=dict(list=lh, hazard=hh))


def family_obj(ch: dict) -> dict:
    full = ch["full"]
    return dict(family=ch["winner"], list=[[list(c) for c in r] for r in full["list"]],
                hazard=dict(w=full["hazard"]["w"].tolist(), mu=full["hazard"]["mu"].tolist(), sd=full["hazard"]["sd"].tolist()),
                list_hit=full["list_hit"], hazard_hit=full["hazard_hit"], holdout=ch["holdout"])


def exit_fit(say, C: dict) -> int:
    stage_header(say, "exit", "a per-day hold-or-sell rule learned from the bar state (§8)")
    S, cal, CI = C["S"], C["cal"], C["CI"]
    ent, stp = read_chosen("enter"), read_chosen("stop")
    chosen_level = ent["object"]["level"]
    chosen_stop = (stp["object"]["level"], stp["object"]["variant"]) if stp["object"]["level"] else None
    fit = S["exit_fit"]
    say(f"- fit set: dated deciding with a known exit {len(S['exit_fit_dated'])} (all years) + exact-day undated 2020 {len(S['und_fit'])} = {len(fit)}; "
        f"the chain: fill {chosen_level} (fit choice; registered where infeasible), stop {chosen_stop or 'registered (S1-T dated / one ADR20 undated)'}")
    fit_eids = assert_fit_set(say, "exit", fit)
    M = load_for_stage(say, C, {b.sym_a for b in fit} | {"QQQ", "SPY"}, {b.sym for b in fit if b.E > A_LAST} | {"QQQ", "SPY"})
    guard = BarGuard(fit_eids)                                 # each record's own horizon: unbounded inside the fit set, the buy day outside it (H1)
    recs, drop = recs_for(fit, M, era_of, guard)
    say(f"- records: {len(recs)} (dropped {dict(drop)}; the record floor = {REC_MIN_BARS} bars before the buy day)")
    g8_run(say, recs, "exit_fit")
    smas_cache = {}
    protect = {b.eid for b in S["ent_chk_dated"]}             # M4: ENTER's dated check set carries the registered fill here, never the chosen level
    cc = apply_chain(recs, chosen_level, chosen_stop, smas_cache, registered_fill_eids=protect)
    say("- the chain: " + ", ".join(f"{k} {v}" for k, v in sorted(cc.items())) + f" (the {len(protect)} dated 2021-22 in-session brackets = ENTER's dated check set carry the "
        "REGISTERED fill here, flagged `fill_checkwin_registered`, so the chosen level's feasibility on them stays unread until --check)")
    Xs, lo, hi, scor, keep, notes = exit_rows_for_safe(recs, smas_cache)
    recs_k = [r for r, k in zip(recs, keep) if k]
    Es = [r.b.E for r in recs_k]
    say(f"- trade-days: {sum(len(X) for X in Xs):,} over {len(Xs)} trades ({int((~keep).sum())} dropped for a hole on the buy day's path); scorable for the hit rate "
        f"(exit window <= {EXIT_HIT_MAX_WINDOW} sessions, not cut by a hole) {int(scor.sum())}; holes: " + (", ".join(f"{k} {v}" for k, v in sorted(notes.items())) or "none"))
    say("\n## THE FAMILY CHOICE (§8b): both families fit without the 2020-07-01..12-31 buys, compared on those buys' hit rate; the winner refit on the whole fit set")
    ch = choose_family(say, Xs, lo, hi, scor, Es, "dated-inclusive fit")
    winner, full = ch["winner"], ch["full"]
    chosen_obj = family_obj(ch)
    chosen_obj.update(enter_level=chosen_level, stop=chosen_stop)
    text = list_text(full["list"]) if winner == "list" else "hazard: " + " ".join(f"{n}{w:+.2f}" for n, w in zip(list(XFEATS) + ["b"], full["hazard"]["w"]))
    # trivial exits on the fit, for scale
    triv = {k: np.array([trivial_sell_days(X)[k] for X in Xs]) for k in ("close_of_session_3", "first_red_close")}
    say("- trivial exits on the fit (for scale; the buy day = session 1, so 'session 3' = offset 2; the first red close from session 2 on): "
        + ", ".join(f"{k} hit {pct(hit_rate(v, lo, hi, scor))}" for k, v in triv.items()))
    # beside: the undated-2020-only fit, by the SAME held-out rule
    say("\n## BESIDE: the fit on the undated 2020 set alone (population shift vs rule quality; checked on the same 226), the same held-out family rule")
    und = np.array([not r.b.dated for r in recs_k])
    ch_u = choose_family(say, [X for X, m in zip(Xs, und) if m], lo[und], hi[und], scor[und], [E for E, m in zip(Es, und) if m], "undated 2020 only")
    chosen_obj["undated_only"] = family_obj(ch_u)
    # the 2020 accounts (in-sample; for scale): ours / chosen / his over 2020-01-27..12-31 on the 2020 fit trades
    say("\n## THE 2020 ACCOUNTS (in-sample, for scale; the check's bar is on 2021-22): ours = speed trail, chosen = the rule, his = panel exit, all at cap_30")
    sub = [r for r in recs_k if FIT_WIN[0] <= r.b.E <= FIT_WIN[1]]
    acc = accounts_for(say, sub, chosen_obj, M, C, FIT_WIN, smas_cache)
    rows = [dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, fill=r.fill, fill_src=r.fill_src, fill_checkwin_registered=r.fill_checkwin_registered,
                 stop=r.stop, stop_src=r.stop_src, exit_lo_j=r.exit_lo_j, exit_hi_j=r.exit_hi_j, n_days=len(X), list_day=list_sell_day(X, full["list"]), hazard_day=hazard_sell_day(X, full["hazard"]))
            for r, X in zip(recs_k, Xs)]
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/exit_fit_trades.tsv", sep="\t", index=False)
    ledger_append("exit-fit", f"{OUT_DIR}/exit_fit_trades.tsv")
    day_rows = []
    for r, X in zip(recs_k, Xs):
        for j, x in enumerate(X):
            day_rows.append(dict(eid=r.b.eid, j=j, **{k: float(v) for k, v in zip(XFEATS, x)}))
    pd.DataFrame(day_rows).to_csv(f"{OUT_DIR}/exit_fit_days.tsv.gz", sep="\t", index=False, compression="gzip")
    ledger_append("exit-fit", f"{OUT_DIR}/exit_fit_days.tsv.gz")
    chosen_obj["accounts_2020"] = acc
    write_chosen("exit", chosen_obj, text)
    say(f"\nCHOSEN EXIT: {text}")
    say("- §8's check runs the three accounts on the undated 2021-22 buys ONCE in --check (recovery >= 0.25 PASS; VOID when his / ours < 1.25)")
    return 0


def accounts_for(say, recs: list, chosen_obj: dict, M: dict, C: dict, win: tuple, smas_cache: dict, label: str = "") -> dict:
    """The three accounts (§8c) over `win`: ours (speed trail), chosen (the rule), his (panel exit, no stop), under the chain's fill and stop;
    the registered fill and stop beside. The chosen account follows the stop LEVEL day by day (`r.stop_lvl`: a moving average moves — M10);
    ours takes the buy-day price (`cb.walk_arms` takes a fixed stop) and his takes no stop. Every account is cut at the ticker's identity
    break (`break_horizon`, L2). -> finals, recovery, void."""
    cal_u, CI = C["cal"], C["CI"]
    w0 = CI[win[0]]
    cal_dates = [date.fromisoformat(d) for d in cal_u]
    stop_v = (chosen_obj.get("stop") or [None, "T"])[1] or "T"

    def sell_fn(X):
        if chosen_obj["family"] == "list":
            lst = [tuple(tuple(c) for c in r) for r in chosen_obj["list"]]
            return list_sell_day(X, lst)
        hz = {k: np.asarray(v) for k, v in chosen_obj["hazard"].items()}
        return hazard_sell_day(X, hz)
    out = {}
    for variant in ("chain", "registered"):
        ours, chosen, his, c = [], [], [], Counter()
        for r in recs:
            if variant == "registered":
                r2 = Rec(b=r.b, bars=r.bars, cidx=r.cidx, e=r.e, adr20=r.adr20, mb=r.mb, minutes_state=r.minutes_state, qqq_c=r.qqq_c, guard=r.guard)
                r2.fill, r2.fill_minute, r2.fill_src, r2.day0 = registered_fill(r2)
                r2.stop_levels = stop_levels(r2, r2.fill_minute if r2.fill_src.startswith("orh5") else None)
                r2.stop = r2.stop_levels["S1"] if r.b.dated else r2.fill * (1.0 - r2.adr20)
                if not r2.stop < r2.fill:
                    r2.stop = r2.fill * (1.0 - r2.adr20)
                r2.day0 = day0_for(r2, r2.fill_minute, r2.stop)
                stop_lvl, sv = r2.stop, "T"
            else:
                r2, stop_lvl, sv = r, (r.stop_lvl if r.stop_lvl is not None else r.stop), stop_v
            if r2.exit_hi_j is None:
                c["no_exit"] += 1
                continue
            smas = smas_for(r2, smas_cache)
            width = (r2.fill - r2.stop) / r2.fill
            if not width > 0:
                c["stop_at_or_above_fill"] += 1
                continue
            guards = M["guards"].get(r2.b.era, {}) if isinstance(M.get("guards"), dict) else {}
            bh, why = break_horizon(r2, guards)
            c[f"cut_at_{why}"] += int(bool(why) and r2.exit_hi_j > bh)
            t_o = speed_trail_trade(r2, M, guards)
            j, px, kind = exit_walk(r2, sell_fn, stop_lvl, sv, smas, horizon=min(HORIZON, bh))
            if kind == "mark" and why and j == bh and bh < HORIZON:
                kind = "mark_break" if why == "break" else "mark_hole"
            t_c = make_simple_trade(r2, j, px, kind, width, M["map_b"], len(cal_u))
            t_h = panel_trade(r2, M["map_b"], len(cal_u), max_j=bh, cut_kind="mark_break" if why == "break" else "mark_hole")
            if t_o is None or t_c is None or t_h is None:
                c["unbuildable"] += 1
                continue
            ours.append(t_o); chosen.append(t_c); his.append(t_h)
            c["trades"] += 1
        sims = {k: rp.simulate(v, CAP30, cal_dates, w0) for k, v in (("ours", ours), ("chosen", chosen), ("his", his))}
        rec_, void = recovery(sims["ours"]["final"], sims["chosen"]["final"], sims["his"]["final"])
        say(f"- {label}{variant} fill and stop ({', '.join(f'{k} {v}' for k, v in sorted(c.items()))}): ours {sims['ours']['final']:.3f} | chosen {sims['chosen']['final']:.3f} | his {sims['his']['final']:.3f} "
            f"| his / ours {sims['his']['final'] / sims['ours']['final'] if sims['ours']['final'] > 0 else float('nan'):.2f} | recovery {rec_:+.3f}" + (f" | VOID ({void})" if void else ""))
        for k, s_ in sims.items():
            say(f"    {k}: by year " + ", ".join(f"{y} {pct(x)}" for y, x in sorted(s_["yearly"].items())) + f" | max DD {pct(s_['max_dd'])} | entered {s_['counts']['entered']}, skipped no room {s_['counts']['skipped_no_room']}")
        out[variant] = dict(ours=sims["ours"]["final"], chosen=sims["chosen"]["final"], his=sims["his"]["final"], recovery=rec_, void=void, n=c["trades"])
    return out


# ---- THE CHECK ---------------------------------------------------------------------------------------------------------------------------
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
            print(f"REFUSED: exactly one `CHOSEN {s.upper()}:` line must stand above the marker (found {len(ch.get(s, []))})", file=sys.stderr)
            return 2
        fit_text = read_chosen(s)["text"]
        if ch[s][0] != fit_text:
            print(f"REFUSED: the doc's CHOSEN {s.upper()} ({ch[s][0]!r}) differs from the fit printout's ({fit_text!r})", file=sys.stderr)
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
    frozen_copy = os.path.join(HERE, f"01_rev_frozen_{sha(os.path.abspath(__file__))[:12]}.py")
    shutil.copyfile(os.path.abspath(__file__), frozen_copy)          # guard (2): the module beside the pins before any post-check edit
    say("# #705 REVERSE 01 — CHECK (ONE run): SELECT -> ENTER -> STOP -> EXIT on 2021-01-04..2022-06-14, each ONCE; then WHY's 2020 hand-read sheet")
    say(f"# registration: {os.path.relpath(DOC, REPO)}; module copied to {os.path.basename(frozen_copy)}")
    say(f"- freeze: every pin incl. doc_body {p['doc_body'][:12]}... sits under the marker; CHOSEN lines match the fit printouts; the ledger matches the disk")
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


def check_stages(say, C: dict) -> int:
    S, cal, CI = C["S"], C["cal"], C["CI"]
    sel, ent, stp, xit = (read_chosen(s)["object"] for s in STAGES)
    verdicts = {}
    # ---------------- SELECT
    say("\n## SELECT CHECK (§5b / §5d): the CHOSEN condition set on the 2021-01-04..2022-06-14 exact-day non-flicker no-event buys vs the pool")
    conj_list = [[Cond(f, op, thr) for f, op, thr in conj] for conj in sel["conjunctions"]]
    if sel.get("inconclusive") or not conj_list:
        verdicts["select"] = "INCONCLUSIVE"
        say("- SELECT read INCONCLUSIVE before the check (the search control) or chose nothing: its check is not read; the sealed test's branch = our-detector")
        M = load_for_stage(say, C, None, {"QQQ", "SPY"})
    else:
        M = load_for_stage(say, C, None, {"QQQ", "SPY"})
        DA = M["DA"]
        raw_flat = load_raw_flat(say, DA)
        qst = qqq_states(DA)
        chk_buys = S["sel_chk"] + S["sel_chk_nc"]
        chk_days = sorted({CI[b.E] for b in chk_buys})
        pool = pool_rows_for_days(DA, raw_flat, chk_days, qst, C["small"], C["sic"], M["held"], cal, "A", progress=say)
        pool_free = pool[~pool["held"]].reset_index(drop=True)
        recs, drop = recs_for(chk_buys, M, select_era_of, BarGuard(None), want_minutes=False)
        rows = []
        for r in recs:
            tid = DA.tid[r.b.sym_a]
            a, bnd = int(DA.start[tid]), int(DA.stop[tid])
            f = pick_features(r, raw_flat[a:bnd], qst, pool_free[pool_free["day_ci"] == CI[r.b.E]])
            f.update(eid=r.b.eid, ticker=r.b.sym_a, day=r.b.E, day_ci=CI[r.b.E], nc=r.b.undated_reason == "never_candidate", sec_type=r.b.sec_type)
            rows.append(f)
        picks = pd.DataFrame(rows)
        if len(picks) and picks["pool_empty"].any():
            raise GuardStop(f"{int(picks['pool_empty'].sum())} check buy day(s) have no pool rows: F15 / F16 cannot be read")
        say(f"- check buys {len(picks)} (failing the pool floor, kept out: {int((~picks['floor_ok']).sum())}); pool rows on {len(chk_days)} days (the check buys' days only, as the fit) {len(pool_free):,}")
        picks = picks[picks["floor_ok"]].reset_index(drop=True)
        m = set_matches(conj_list, picks)
        mp = set_matches(conj_list, pool_free)
        rec_, rate = float(m.mean()) if len(m) else float("nan"), float(mp.mean()) if len(mp) else float("nan")
        lift = rec_ / rate if rate > 0 else float("inf")
        v = "PASS" if (rec_ >= SELECT_PASS_RECALL and rate <= POOL_RATE_CAP) else "FAIL" if lift < SELECT_FALSIFY_LIFT else "INCONCLUSIVE"
        verdicts["select"] = v
        say(f"- the CHOSEN set on the check: recall {pct(rec_)} (+-{100 * binom_ci(int(m.sum()), len(m))[1]:.0f}), pool rate {pct(rate)}, lift {lift:.2f} -> **{v}** "
            f"(PASS recall >= 50% at pool rate <= 20%; falsifier lift < 2.0)")
        typed = picks["sec_type"] != ""
        say(f"- without the no-type-row buys: recall {pct(m[typed].mean()) if typed.any() else '-'}; no-event only {pct(m[~picks['nc']].mean())}; never-a-candidate {pct(m[picks['nc']].mean()) if picks['nc'].any() else '-'}")
        picks.assign(meets=m).to_csv(f"{OUT_DIR}/check_select_buys.tsv", sep="\t", index=False)
        ledger_append("check", f"{OUT_DIR}/check_select_buys.tsv")
        # §5d
        if sel.get("rank_model"):
            rm = {k: np.asarray(v) for k, v in sel["rank_model"].items() if k in ("w", "mu", "sd")}
            b0 = sel["rank_model"]["b"]
            qp = pool_free[mp]
            sc = ((rank_design(qp) - rm["mu"]) / rm["sd"]) @ rm["w"] + b0
            pcts = []
            for i in np.flatnonzero(m):
                d = picks.loc[i, "day_ci"]
                spick = float((((rank_design(picks.iloc[[i]]) - rm["mu"]) / rm["sd"]) @ rm["w"] + b0)[0])
                pcts.append(pick_percentile(spick, sc[(qp["day_ci"] == d).to_numpy()]))
            med = float(np.median(pcts)) if pcts else float("nan")
            rv = "PASS" if med <= RANK_PASS_PCTL else "FAIL" if med >= RANK_FALSIFY_PCTL else "INCONCLUSIVE"
            say(f"- §5d rank: his qualifying picks' median percentile within the day's qualifying pool {med:.2f} ({len(pcts)} picks) -> {rv} (PASS <= 0.25; falsifier >= 0.40)")
        flick, _d = recs_for(S["sel_chk_flick"], M, select_era_of, BarGuard(None), want_minutes=False)
        fl_days = sorted({CI[r.b.E] for r in flick} - set(chk_days))
        fl_light = pool_rows_for_days(DA, raw_flat, fl_days, qst, C["small"], C["sic"], M["held"], cal, "A", light=True) if fl_days else pd.DataFrame()
        by_day_c = {d: g for d, g in pool_free.groupby("day_ci")}
        if len(fl_light):
            by_day_c.update({d: g for d, g in fl_light[~fl_light["held"]].groupby("day_ci")})
        frows = []
        for r in flick:
            tid = DA.tid[r.b.sym_a]
            a, bnd = int(DA.start[tid]), int(DA.stop[tid])
            f = pick_features(r, raw_flat[a:bnd], qst, by_day_c.get(CI[r.b.E]))
            f.update(eid=r.b.eid, ticker=r.b.sym_a, day=r.b.E, day_ci=CI[r.b.E], sec_type=r.b.sec_type)
            frows.append(f)
        fpk = pd.DataFrame(frows)
        if len(fpk):
            fok = fpk[fpk["floor_ok"] & ~fpk["pool_empty"]].reset_index(drop=True)
            mf = set_matches(conj_list, fok) if len(fok) else np.zeros(0, bool)
            say(f"- flickers beside: {len(fpk)} records, {len(fok)} past the floor; the CHOSEN set fires on {int(mf.sum())} of {len(fok)} ({pct(mf.mean()) if len(fok) else '-'}); same-day pool missing {int(fpk['pool_empty'].sum())}")
            fpk.to_csv(f"{OUT_DIR}/check_select_flickers.tsv", sep="\t", index=False)
            ledger_append("check", f"{OUT_DIR}/check_select_flickers.tsv")
        else:
            say("- flickers beside: no record")
        # re-check N3: the 2021-22 members of the 47 other-level buys (moved here from the fit), scored with the CHOSEN set, beside
        olc = [b for b in S["other_level_chk"] if b.E <= A_EXPORT_LAST]
        orecs, _d = recs_for(olc, M, select_era_of, BarGuard(None), want_minutes=False)
        ol_days = sorted({CI[r.b.E] for r in orecs} - set(by_day_c))
        ol_light = pool_rows_for_days(DA, raw_flat, ol_days, qst, C["small"], C["sic"], M["held"], cal, "A", light=True) if ol_days else pd.DataFrame()
        if len(ol_light):
            by_day_c.update({d: g for d, g in ol_light[~ol_light["held"]].groupby("day_ci")})
        orows = []
        for r in orecs:
            tid = DA.tid[r.b.sym_a]
            a, bnd = int(DA.start[tid]), int(DA.stop[tid])
            f = pick_features(r, raw_flat[a:bnd], qst, by_day_c.get(CI[r.b.E]))
            f.update(eid=r.b.eid, ticker=r.b.sym_a, day=r.b.E, day_ci=CI[r.b.E], sec_type=r.b.sec_type, window_len=r.b.wl)
            orows.append(f)
        opk = pd.DataFrame(orows)
        if len(opk):
            mo = set_matches(conj_list, opk)
            say(f"- beside, the {len(S['other_level_chk'])} other-level buys of 2021-22 (re-check N3; {len(opk)} records): the CHOSEN set fires on {int(mo.sum())} of {len(opk)} ({pct(mo.mean())}); "
                f"pool floor met by {int(opk['floor_ok'].sum())}; same-day pool missing {int(opk['pool_empty'].sum())}")
            opk.assign(meets=mo).to_csv(f"{OUT_DIR}/check_select_other_level.tsv", sep="\t", index=False)
            ledger_append("check", f"{OUT_DIR}/check_select_other_level.tsv")
        else:
            say("- beside, the other-level buys of 2021-22: no record")
    # ---------------- ENTER
    say("\n## ENTER CHECK (§6): the CHOSEN level on the 2021-22 in-session brackets")
    chosen_level = ent["level"]
    chk = S["ent_chk_dated"] + S["ent_chk_und"]
    chk_fl = [b for b in S["ent_chk_und_fl"] if b.flicker]
    names_A = {b.sym_a for b in chk + chk_fl + S["und_chk"] + S["stop_chk_dated"]} | {"QQQ", "SPY"}
    names_B = {b.sym for b in chk + chk_fl + S["und_chk"] + S["stop_chk_dated"] if b.E > A_LAST} | {"QQQ", "SPY"}
    names_A |= {b.sym_a for b in inwin(S["ent_prefirst_dated"], CHECK_WIN)}
    M2 = load_for_stage(say, C, names_A, names_B)
    recs_e, drop = recs_for(chk, M2, era_of, BarGuard(None), min_bars=REC_MIN_BARS_ENTER)
    rng = rng_for(RANDOM_KEY)                       # the registered seed and key (a fresh generator; trades in (E, eid) order)
    scored = {r.b.eid: enter_score_trade(r, rng) for r in sorted(recs_e, key=lambda x: (x.b.E, x.b.eid)) if r.mb is not None}
    dated_eids = {r.b.eid for r in recs_e if r.b.dated}
    deciding, beside_l1 = enter_deciding(scored, dated_eids, chosen_level)          # M1: L1 chosen -> the undated brackets alone decide
    summ = enter_summary(deciding)
    summ_all = enter_summary(scored)
    say(f"- records {len(recs_e)} (dropped {dict(drop)}; the ENTER record floor = {REC_MIN_BARS_ENTER} bars); scorable {summ_all['n']} ({sum(1 for r in recs_e if r.mb is None)} no_minutes); "
        f"DECIDING {summ['n']}" + (f" = the undated brackets alone (L1 chosen: L1 on the {len(beside_l1)} dated 2021-22 brackets is a re-read, printed beside)" if chosen_level == "L1" else " = dated + undated"))
    for L in LEVELS:
        s_ = summ[L]
        say(f"- {L}: feasible {pct(s_['feasible_share'][0])} +-{100 * s_['feasible_share'][1]:.0f}; hit-or-ballpark {pct(s_['hit_share'][0])} +-{100 * s_['hit_share'][1]:.0f} ({'CHOSEN' if L == chosen_level else 'beside'}; "
            + ", ".join(f"{k} {v}" for k, v in sorted(s_["verdicts"].items())) + ")")
    say(f"- control: feasible {pct(summ['control']['feasible_share'])}, hit-or-ballpark {pct(summ['control']['hit_share'])} on the deciding set")
    if beside_l1:
        sb = enter_summary(beside_l1)
        say(f"- beside, L1 on the dated 2021-22 brackets (a re-read; {sb['n']}): feasible {pct(sb['L1']['feasible_share'][0])}, hit-or-ballpark {pct(sb['L1']['hit_share'][0])}")
    ev, reasons = enter_verdict(summ, chosen_level) if summ["n"] else ("INCONCLUSIVE", ["no scorable trade"])
    verdicts["enter"] = ev
    say(f"- ENTER: **{ev}** " + ("; ".join(reasons) if reasons else ""))
    for lab, bs in (("flickers", chk_fl), ("pre-market-flat brackets dated", inwin(S["ent_pre_dated"], CHECK_WIN)), ("pre-market-flat brackets undated", inwin(S["ent_pre_und"], CHECK_WIN))):
        rr, _d = recs_for(bs, M2, era_of, BarGuard(None), min_bars=REC_MIN_BARS_ENTER)
        sc = {r.b.eid: enter_score_trade(r, rng) for r in rr if r.mb is not None}
        if sc:
            ss = enter_summary(sc)
            say(f"- beside {lab} ({ss['n']}): " + "; ".join(f"{L} feasible {pct(ss[L]['feasible_share'][0])} hit {pct(ss[L]['hit_share'][0])}" for L in LEVELS))
    rr, _d = recs_for(inwin(S["ent_prefirst_dated"], CHECK_WIN), M2, era_of, BarGuard(None), min_bars=REC_MIN_BARS_ENTER)
    crossed_lines(say, "beside pre-market first sightings, dated 2021-22", rr)
    chain_level = chosen_level if ev == "PASS" else None
    say(f"- the chain carries: {'the chosen level ' + chosen_level if chain_level else 'the REGISTERED fill (words-based)'}")
    # ---------------- STOP
    say("\n## STOP CHECK (§7): the undated 2021-22 buys decide, on every level and variant; dated 2021-22 beside (re-check N1: the EXIT fit walked them under the chosen stop)")
    chosen_stop = (stp["level"], stp["variant"]) if stp["level"] else None
    recs_u, _d = recs_for(S["und_chk"], M2, era_of, BarGuard(None))
    recs_d, _d2 = recs_for(S["stop_chk_dated"], M2, era_of, BarGuard(None))
    smas_cache = {}
    cc = apply_chain(recs_u + recs_d, chain_level, None, smas_cache)
    say("- fills: " + ", ".join(f"{k} {v}" for k, v in sorted(cc.items())))
    g8_run(say, recs_u + recs_d, "check")
    sight = M2["sight"]
    smas_of = lambda r: smas_for(r, smas_cache)   # noqa: E731
    exm = exit_minutes_for(recs_u + recs_d, M2)
    say(f"- exit-window first sessions with minute bars in a tree: {len(exm)} of {sum(1 for r in recs_u + recs_d if r.b.has_exit and r.b.exit_lo != r.b.E)}")
    fit_table = {tuple(k.split("-")): v for k, v in stp["fit_table"].items()}
    tab_u = stop_table(recs_u, smas_of, sight, exit_minutes=exm)
    tab_u_nf = stop_table([r for r in recs_u if not r.b.flicker], smas_of, sight, exit_minutes=exm)
    tab_u_un = stop_table([r for r in recs_u if not r.b.in_dated_path], smas_of, sight, exit_minutes=exm)
    tab_d = stop_table(recs_d, smas_of, sight, exit_minutes=exm)
    hdr = ["level-variant", "undated 226 H_cond (traded / certain)", "fit H_cond", "non-flicker 145", "untouched 161", "dated 111 (beside, never deciding)"]
    rows = []
    for L in STOP_LEVELS + STOP_CONTROLS:
        for V in STOP_VARIANTS:
            t = tab_u[(L, V)]
            dd = tab_d[(L, V)]
            rows.append([f"{L}-{V}", f"{pct(t['H_cond'])} ({t['any']} / {t['certain']})", pct(fit_table[(L, V)]["H_cond"]), pct(tab_u_nf[(L, V)]["H_cond"]), pct(tab_u_un[(L, V)]["H_cond"]),
                         (f"{pct(dd['H_cond'])} (unread by the exits study)" if (L, V) in STOP_UNREAD_DATED else f"{pct(dd['H_cond'])} (a re-read)")])
    for ln in rp.table(hdr, rows):
        say(ln)
    sv, sreasons = stop_verdict(fit_table, tab_u, chosen_stop)       # re-check N1: the undated 226 decide alone; the dated 111 are beside
    sv_nf, _r = stop_verdict(fit_table, tab_u_nf, chosen_stop)
    sv_un, _r2 = stop_verdict(fit_table, tab_u_un, chosen_stop)
    verdicts["stop"] = sv
    say(f"- STOP: **{sv}** " + "; ".join(sreasons) + f" | non-flicker 145: {sv_nf} | untouched 161: {sv_un}" + (" (a flip between them is reported as such)" if len({sv, sv_nf, sv_un}) > 1 else "")
        + (f" | beside, the chosen {'-'.join(chosen_stop)} on the dated 2021-22 (never deciding; the EXIT fit walked them under it): H_cond {pct(tab_d[chosen_stop]['H_cond'])}" if chosen_stop else ""))
    # the after-loss flag with the INFERRED fill (only here for 2021-22; the earlier entry's exit is read now, no guard)
    byeid = {b.eid: b for b in C["buys"]}
    after_loss_count(say, recs_u, C, M2, chain_level, None, "2021-22 check")
    chain_stop = chosen_stop if sv == "PASS" else None
    apply_chain(recs_u + recs_d, chain_level, chain_stop, smas_cache)
    say(f"- the chain carries: {'the chosen stop ' + '-'.join(chosen_stop) if chain_stop else 'the REGISTERED stop (words-based: S1-T dated / one ADR20 undated)'}")
    rows = [dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, dated=r.b.dated, flicker=r.b.flicker, fill=r.fill, fill_src=r.fill_src, stop=r.stop, stop_src=r.stop_src,
                 **{f"{L}_{V}_{k}": held_through(r, L, V, smas_of(r), sight, exit_mb=exm.get(r.b.eid))[k] for L in STOP_LEVELS + STOP_CONTROLS for V in STOP_VARIANTS for k in ("any", "certain", "unresolved")})
            for r in recs_u + recs_d]
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/check_stop_trades.tsv", sep="\t", index=False)
    ledger_append("check", f"{OUT_DIR}/check_stop_trades.tsv")
    # ---------------- EXIT
    say("\n## EXIT CHECK (§8): the three accounts on the undated 2021-22 buys (226, flickers included) under the chain's fill and stop")
    chosen_obj = dict(xit)
    chosen_obj["stop"] = list(chain_stop) if chain_stop else None
    sub = [r for r in recs_u if r.exit_hi_j is not None]
    acc = accounts_for(say, sub, chosen_obj, M2, C, CHECK_WIN, smas_cache, label="all 226, ")
    ch_ = acc["chain"]
    if ch_["void"]:
        xv = "VOID (no bar)"
    else:
        xv = "PASS" if ch_["recovery"] >= EXIT_RECOVERY_BAR else "FAIL"
    verdicts["exit"] = xv
    say(f"- EXIT: **{xv}** (recovery {ch_['recovery']:+.3f}; bar {EXIT_RECOVERY_BAR}; his / ours {ch_['his'] / ch_['ours'] if ch_['ours'] > 0 else float('nan'):.2f})")
    for lab, pred in (("non-flicker 145", lambda r: not r.b.flicker), ("untouched 161", lambda r: not r.b.in_dated_path)):
        accounts_for(say, [r for r in sub if pred(r)], chosen_obj, M2, C, CHECK_WIN, smas_cache, label=f"{lab}, ")
    # hit rates vs the trivial rules
    Xs, lo, hi, scor, keep, xnotes = exit_rows_for_safe(sub, smas_cache)
    if xnotes:
        say("- holes on the check paths: " + ", ".join(f"{k} {v}" for k, v in sorted(xnotes.items())))
    sub_k = [r for r, k in zip(sub, keep) if k]
    lst = [tuple(tuple(c) for c in r) for r in xit["list"]]
    hz = {k: np.asarray(v) for k, v in xit["hazard"].items()}
    days = {"chosen (" + xit["family"] + ")": np.array([list_sell_day(X, lst) if xit["family"] == "list" else hazard_sell_day(X, hz) for X in Xs]),
            "decision list": np.array([list_sell_day(X, lst) for X in Xs]), "hazard median": np.array([hazard_sell_day(X, hz) for X in Xs]),
            "close of session 3": np.array([trivial_sell_days(X)["close_of_session_3"] for X in Xs]), "first red close": np.array([trivial_sell_days(X)["first_red_close"] for X in Xs])}
    say("- hit rates on the check (the rule's sell session inside his window; windows <= 20 sessions): " + ", ".join(f"{k} {pct(hit_rate(v, lo, hi, scor))}" for k, v in days.items()))
    if ch_["void"]:
        say(f"- VOID: the readout is the hit rate above; SELECT's short-cluster flags {sel.get('short_flags')}; the sealed test carries the registered speed trail")
    uo = xit.get("undated_only")
    if uo:
        uo_obj = dict(family=uo["family"], list=uo["list"], hazard=uo["hazard"], stop=chosen_obj["stop"])
        say("- beside, the undated-2020-only fit on the same 226:")
        accounts_for(say, sub, uo_obj, M2, C, CHECK_WIN, smas_cache, label="undated-only fit, ")
    say("- dated 2021-22 under the chosen rule (IN-SAMPLE, never deciding):")
    accounts_for(say, [r for r in recs_d if r.exit_hi_j is not None], chosen_obj, M2, C, CHECK_WIN, smas_cache, label="dated 2021-22, ")
    rows = [dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, flicker=r.b.flicker, in_dated_path=r.b.in_dated_path, fill=r.fill, fill_src=r.fill_src, stop=r.stop, stop_src=r.stop_src,
                 exit_lo_j=r.exit_lo_j, exit_hi_j=r.exit_hi_j, **{k: int(v[i]) for k, v in days.items()}) for i, r in enumerate(sub_k)]
    pd.DataFrame(rows).to_csv(f"{OUT_DIR}/check_exit_trades.tsv", sep="\t", index=False)
    ledger_append("check", f"{OUT_DIR}/check_exit_trades.tsv")
    # ---------------- the sealed-test branch labels
    say("\n## THE SEALED TEST'S BRANCH (stated, not run here)")
    say(f"- SELECT {verdicts['select']} -> {'the condition set scans the daily universe' if verdicts['select'] == 'PASS' else 'our-detector (tl / EP events)'}; "
        f"ENTER {verdicts['enter']} -> {'inferred ' + chosen_level if verdicts['enter'] == 'PASS' else 'words-based (ORH5 / the open)'}; "
        f"STOP {verdicts['stop']} -> {'inferred ' + '-'.join(chosen_stop) if (verdicts['stop'] == 'PASS' and chosen_stop) else 'words-based (low of the day / one ADR20)'}; "
        f"EXIT {verdicts['exit']} -> {'the inferred rule' if verdicts['exit'] == 'PASS' else 'words-based (the speed trail)'}")
    # ---------------- WHY's 2020 hand-read sheet
    say("\n## WHY (§9): the 20-row 2020 hand-read sheet (8 STOPPED, 8 SOLD, 4 PARTIAL; seed 1024) -> fill `verdict` by hand, then --why-rates")
    texts = load_caption_texts(sorted(glob.glob(SUBS_GLOB)))
    VS, MG = load_caption_inputs()
    byname = defaultdict(list)
    for b in S["ni"]:
        if b.has_exit:
            byname[b.sym].append(b)
            if b.sym_a != b.sym:
                byname[b.sym_a].append(b)
    J = caption_joins(phrase_hits(texts), VS, MG, byname, cal)
    rows = why_sheet_rows(J["joins"], texts, C["sn"], byeid)
    pd.DataFrame(rows).to_csv(WHY_SHEET, sep="\t", index=False)
    ledger_append("check", WHY_SHEET)
    say(f"- {len(rows)} joins written to {WHY_SHEET} (by class " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['cls'] for r in rows).items())) + ")")
    with open(f"{OUT_DIR}/check_verdicts.json", "w") as fh:
        json.dump(verdicts, fh, indent=1)
    ledger_append("check", f"{OUT_DIR}/check_verdicts.json")
    say("\nCHECK COMPLETE: " + ", ".join(f"{k.upper()} {v}" for k, v in verdicts.items()))
    return 0


# ---- WHY rates ---------------------------------------------------------------------------------------------------------------------------
def run_why_rates(say) -> int:
    if os.path.exists(P_WHY) or os.path.exists(STOPPED):
        print("REFUSED: the WHY printout or a STOPPED file exists", file=sys.stderr)
        return 2
    if not os.path.exists(P_CHECK) or not os.path.exists(WHY_SHEET):
        print("REFUSED: --why-rates runs after --check wrote the hand-read sheet", file=sys.stderr)
        return 2
    sheet = pd.read_csv(WHY_SHEET, sep="\t", dtype=str, keep_default_na=False)
    say("# #705 REVERSE 01 — WHY rates (§9): the hand-read precision gate, then the per-class rates")
    prec, why = why_precision(sheet)
    if why:
        say(f"REFUSED: {why}")
        say.write(P_WHY)
        return 2
    say(f"- hand-read precision on {len(sheet)} joins: {pct(prec)} (gate {pct(WHY_PRECISION)})")
    try:
        C = load_core(say)
        texts = load_caption_texts(sorted(glob.glob(SUBS_GLOB)))
        VS, MG = load_caption_inputs()
        byname = defaultdict(list)
        for b in C["S"]["ni"]:
            if b.has_exit:
                byname[b.sym].append(b)
                if b.sym_a != b.sym:
                    byname[b.sym_a].append(b)
        J = caption_joins(phrase_hits(texts), VS, MG, byname, C["cal"])
        un = [j for j in J["joins"] if not j["ambiguous"]]
        if prec < WHY_PRECISION:
            say("- precision below the gate: NO rate is quoted; the joins are listed")
            for j in un[:200]:
                say(f"    {j['video']} {j['t']:.0f}s {j['cls']} {j['phrase']!r} -> eid {j['eids'][0]} ({','.join(j['tickers'])})")
            say(f"    ... {len(un)} unambiguous joins in all")
        else:
            say("- rates per class (unambiguous joins; by upload year):")
            for cls in ("STOPPED", "SOLD", "PARTIAL"):
                jj = [j for j in un if j["cls"] == cls]
                say(f"    {cls}: joins {len(jj)}, trades {len({j['eids'][0] for j in jj})}, by year " + ", ".join(f"{y} {n}" for y, n in sorted(Counter(j['upload'][:4] for j in jj).items())))
            byeid = {b.eid: b for b in C["buys"]}
            M = load_for_stage(say, C, {byeid[j["eids"][0]].sym_a for j in un} | {"QQQ", "SPY"}, {byeid[j["eids"][0]].sym for j in un if byeid[j["eids"][0]].E > A_LAST} | {"QQQ", "SPY"})
            smas_cache = {}
            lvl_hits, partial_r, sold_x = Counter(), [], []
            for j in un:
                b = byeid[j["eids"][0]]
                r = make_rec(b, M, era_of(b.E), M["done"], M["files"], {}, {})
                if r is None or r.exit_hi_j is None:
                    continue
                r.fill, r.fill_minute, r.fill_src, r.day0 = registered_fill(r)
                r.stop_levels = stop_levels(r, r.fill_minute if r.fill_src.startswith("orh5") else None)
                r.stop = r.stop_levels["S1"] if b.dated else r.fill * (1 - r.adr20)
                if not r.stop < r.fill:
                    r.stop = r.fill * (1 - r.adr20)
                smas = smas_for(r, smas_cache)
                s0 = int(j["s0"])
                jj = min(max(s0 - int(r.cidx[r.e]), r.exit_lo_j), r.exit_hi_j)
                k = r.bar_at(jj)
                if k is None:
                    continue
                if j["cls"] == "STOPPED":
                    touched = [L for L in STOP_LEVELS if np.isfinite(level_at(r, r.stop_levels[L], jj, smas)) and float(r.bars.l[k]) <= level_at(r, r.stop_levels[L], jj, smas)]
                    lowest = min(touched, key=lambda L: level_at(r, r.stop_levels[L], jj, smas)) if touched else "none"
                    lvl_hits[lowest] += 1
                elif j["cls"] == "SOLD":
                    X = exit_features(r, jj, smas)                       # §9: SOLD -> EXIT: the exit session's X1-X10 (L6)
                    if X is not None:
                        sold_x.append(X[jj])
                elif j["cls"] == "PARTIAL" and r.stop < r.fill:
                    partial_r.append((float(r.bars.c[k]) - r.fill) / (r.fill - r.stop))
            say("    STOPPED -> the lowest of S1-S8 touched on the exit session (his stated stop's proxy): " + ", ".join(f"{k} {v}" for k, v in lvl_hits.most_common()))
            if sold_x:
                SX = np.asarray(sold_x)
                say(f"    SOLD -> {len(SX)} trades: the exit session's X1-X10, median " + ", ".join(f"{n} {np.median(SX[:, i]):+.2f}" for i, n in enumerate(XFEATS))
                    + "; share red close (X3) " + pct(float(np.mean(SX[:, 2] > 0))) + ", below the prior low (X4) " + pct(float(np.mean(SX[:, 3] > 0))))
            else:
                say("    SOLD -> none scorable")
            say(f"    PARTIAL -> {len(partial_r)} trades with a partial phrase; R at the caption day's close median {np.median(partial_r):+.2f}" if partial_r else "    PARTIAL -> none scorable")
    except GuardStop as g:
        say(f"STOPPED: {g}")
        say.write(STOPPED)
        return 3
    say.write(P_WHY)
    ledger_append("why", P_WHY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
