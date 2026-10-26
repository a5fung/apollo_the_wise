#!/usr/bin/env python3
"""#705 — RULE MIX 01: which of his rules explains which trade, and what the set covers together — against the same set by chance
(docs/analysis/cb_rule_mix_prereg_2026-10-25.md). REGISTERED, NOT FROZEN, NOT RUN. Built to execution depth; `--tag` runs ONCE after the
freeze. Research only: nothing here changes a strategy, entry, stop, exit, size, safeguard or live trade state (THE LINE). The read is
DESCRIPTIVE: it decides nothing.

The FROZEN intraday module (`scripts/probes/_705_intraday_1025/01_intra_frozen_ac598fc58aae.py`, sha pinned below, refused on drift) is
imported read-only, and through it the frozen reverse module, the holdings replay, the runner and `cb`. Nothing in them is edited and no
attribute of them is reassigned: every helper that hard-codes the intraday read's files (the freeze lock, the ledger, the dry-run test, the
pins) is called with THIS read's paths passed explicitly, and the frozen gates that WRITE their failing rows into the intraday folder
(`gate_ohlc`, `gate_level_order`, `gate_c_implies_h`, `g8_run`, `write_rows`) are never called: their pure row builders are (`ohlc_pair_rows`,
`gate_ohlc_verdict`, `enter_row`) and the thin wrappers here write into this read's own folders (a module-scan test enforces both).

STAGES (§9)
  --dry-run       loads every input; the intraday registration's set claims (the frozen `population_claims`) and every count of §2 / §8
                  of THIS doc asserted (every mismatch printed, then STOP); the composition line from the panel clocks alone; the data gate
                  from the fetch logs ONLY (no minute file opened; `dryrun_side/pending.psv`, expected empty); the intraday TSVs' eids
                  against the printout populations (the eid / group columns only); the library order printed from the constants with each
                  source; the pins. NO outcome: no bar after a buy day, no rule fired, the loss share NOT computed.
  --print-pins    (also --pins) the pins to paste under the doc's freeze marker line.
  --tag           ONCE, after the freeze: refuses unless every pin (incl. `doc_body`) sits under the marker, the body equals the freeze body,
                  this module's sha equals its pin, THIS read's dry run ends `DRY RUN COMPLETE`, no tag output exists and every reset event
                  is disclosed; copies the module beside the pins; then the known-answer gates (i), (ii), (iii), (vii), (viii), (viii-a/b/c),
                  (ix), (x) on real data — each STOPS the run before any new number — then ENTER -> STOP -> EXIT on every block, the
                  controls, the tables, the per-trade files.
  --reset "<reason>"   after a STOPPED tag only (N2): every artifact COPIED to tag_events/<event>/ (sha256 verified, MANIFEST.tsv,
                  DISCLOSURE.md, events.tsv) and only then removed from its place — never deleted; `fit_event_<event>` must sit under the
                  marker before --tag runs again.

READINGS fixed here where the registration is silent or two of its sentences pull apart (each the stricter one, listed in the dry run):
  R1  Bucket precedence (one function for the real window and every control placement): abstain -> NEITHER; a buy-day firing that is
      UNRESOLVED -> UNRESOLVED (ahead of EXPLAINS: a firing that may precede his buy explains nothing); a missing minute session between
      the armed point and the firing -> UNRESOLVED; booked session in the window -> EXPLAINS; before it -> MISS-EARLY; none by the
      window's end -> UNRESOLVED when a missing session lies at or before the window's end, else NEITHER. The missing sessions are the
      minute-less sessions for the rules that read 60-minute bars (M-1, M-2s through its arming, the STOP H cells); the touch and daily
      rules read the daily bar, which a minute-less session cannot hide; a daily hole bounds the path (J_tail) and never precedes a firing.
  R2  The frozen close-fill touch (T, a dated close-proxy fill, a buy-day low at the level — `held_through_intra` marks it unresolved and
      scans on): two alternatives, the touch after his fill (a buy-day firing) or before it (the later first touch); the bucket is theirs
      when both agree, else UNRESOLVED (reproduces the mapping table's MISS-EARLY row and never lets the unresolved touch read EXPLAINS).
  R3  An exit_lo `unresolved` of the frozen function (no frame minute on exit_lo) is NOT a buy-day unresolved: the window unit reads it
      EXPLAINS (§4a), counted in the contradicted line only when a frame contradicts it.
  R4  STOP H cells: the bucket compares the BOOKED session (§4a's table: a close below on the day's last 60-minute bar books on the next
      session); gate (viii) compares the frozen fields (the event session) row for row.
  R5  Gate (viii-b) compares the frame-free first firing (the frozen walk reads no frame) with the frozen leg; the tag applies the buy-day
      frame rule (a firing at or before flat_clock is not an event and the scan goes on); the rows the frame rule moves are counted.
  R6  M-2 / M-7 abstain only without an armed 60-minute bar (their trigger is the armed bar's CLOSE, not the average); `ema_thin` abstains
      M-1 and, through it, M-2s.
  R7  M-5 sits on the session-3 close of THIS doc's numbering (the buy day = session 1 = offset 2) — a strict subset of M-9; the +1R test
      reads the day-0 peak after the fill minute (`cb.day0_peak_high`; an open fill without minutes: the daily high; a close fill: none)
      and the highs of offsets 1-2.
  R8  M-10 and the daily rules arm at the fill (§4a): the buy day's own close counts (M-8 alone starts at session 2, R17).
  R9  The random-level control: its per-rule floor is ONE level per draw (key `mix|rlevel|{eid}|{d}`); its UNION line is a union of k
      levels per draw, price i standing for library rule i (key `mix|rlevel|{eid}|{d}|{i}`) — one level cannot stand for k rules (the
      k-price reasoning of §5). Its touch is the frozen T reading from the fill (`held_through_intra` on a bare price), in his real window.
  R10 The ENTER chance line a rule is held against = the LARGEST of the random-price floor, the frozen per-level shifted share and the
      shared-window share; the union against the largest of the k-price, shared-window and per-level shifted unions (§6).
  R11 Blocks for the labels: 2020, 2021-22 and the untouched years, dated and undated together (ENTER: the in-session non-flicker windows
      plus the dated windows); the sub-blocks (dated / undated) are printed beside with their own labels, never deciding.
  R12 A record outside the previous draw population (a returning guard-5 trade, a beside window the fit excluded) takes its 200
      random-price draws from `mix|rprice1|{eid}` — the previous stream is replayed exactly and never re-ordered to make room.
  R13 Gate (ix): M-1's first firing must be BOOKED on or before 2020-07-10's offset (stricter than the event).
  R14 The dry run's side files (pending.psv, the freeze body copy) go under this module's folder (the task's write scope); the tag's
      per-trade files go where §9 puts them (holdings_1024/rule_mix/). The tests are `tests/test_rule_mix.py` (the task's name; §9
      says test_01_mix.py) and are pinned as `mix_tests`.
  R15 The window controls run in two modes and the chance line is the LARGER: frame-aware (R1 on every placement, the mode gate (x) holds
      equal to the real tag at s = exit_lo) and frame-free (§4a: "the controls have no frames" — a buy-day firing inside a placement is
      EXPLAINS, before it MISS-EARLY; the close-fill touch reads its buy-day alternative; the missing-session rule unchanged).
  R16 A daily close on the buy day (the STOP C cells, M-3, M-4, M-7, M-10) takes §4a's buy-day clock test at the close: no in-session
      buy-day frame -> UNRESOLVED; at or before flat_clock (a flat frame after the close) -> not an event, the scan goes on. The frozen
      held_through_intra applies no buy-day test to C (`if j == 0 and variant != "C"`) and reads such a close certain; §4a's sentence
      ("every buy-day firing is unresolved") and the exit daily rules decide it here, so the STOP C cells and the EXIT library read the
      same close alike. Gate (viii) still compares the frozen fields; the (trade, C cell) pairs R16 moves are counted beside the STOP table.

No subagent, no DB, no network, no ssh, no docker. Read-only on every input. Nothing dated after 2024-12-31 is read (the frozen store's seal,
guard 12); nothing of 2025-26 is opened; replay/ and his_exits/ are never opened (guard 9).
Run:  python3 scripts/probes/_705_rule_mix_1025/01_mix.py --dry-run
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True                  # never drop a .pyc beside a frozen module of another read

import argparse
import dataclasses
import datetime as _dt
import glob
import hashlib
import importlib.util
import math
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
INTRA_DIR = os.path.join(REPO, "scripts", "probes", "_705_intraday_1025")
INTRA_FROZEN = os.path.join(INTRA_DIR, "01_intra_frozen_ac598fc58aae.py")
INTRA_FROZEN_SHA = "ac598fc58aae62dc03c93f5d274aa26af37594821f98d1e1c162c2bb8d20f7ee"     # the intraday read's frozen module (its check copy)
INTRA_DOC_BODY_PREFIX = "6c3741e48788"                                                      # the intraday registration's doc_body (§9)


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_frozen_intra():
    got = sha(INTRA_FROZEN)
    if got != INTRA_FROZEN_SHA:
        raise SystemExit(f"REFUSED: the frozen intraday module is not the frozen one ({got} vs {INTRA_FROZEN_SHA})")
    spec = importlib.util.spec_from_file_location("_705_intra_frozen_mix", INTRA_FROZEN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_705_intra_frozen_mix"] = mod
    spec.loader.exec_module(mod)
    return mod


fz = _load_frozen_intra()
rev, rp, R, cb, H = fz.rev, fz.rp, fz.R, fz.cb, fz.H
GuardStop = fz.GuardStop
fnum, hhmm_to_min, min_to_hhmm, pct, binom_ci, bar_sym, era_of = fz.fnum, fz.hhmm_to_min, fz.min_to_hhmm, fz.pct, fz.binom_ci, fz.bar_sym, fz.era_of

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths (THIS read's) and the intraday read's files this read re-reads (pinned)
# ═════════════════════════════════════════════════════════════════════════════════════════════
DOC = os.path.join(REPO, "docs", "analysis", "cb_rule_mix_prereg_2026-10-25.md")
INTRA_DOC = fz.DOC                                                          # intra-path-ok
INTRA_OUT = fz.OUT_DIR                                                      # intra-path-ok (holdings_1024/intraday: read only)
OUT_DIR = os.path.join(fz.H_DIR, "rule_mix")                                # §9: the per-trade files
P_DRY = os.path.join(HERE, "01_mix_dryrun.txt")
P_TAG = os.path.join(HERE, "01_mix_tag.txt")
P_PINS = os.path.join(HERE, "01_mix_pins.txt")
LEDGER = os.path.join(HERE, "01_mix_ledger.tsv")
STOPPED = os.path.join(HERE, "01_mix.STOPPED.txt")
FREEZE_BODIES = os.path.join(HERE, "freeze_bodies")
DRY_SIDE = os.path.join(HERE, "dryrun_side")                                # R14
TAG_EVENTS = os.path.join(HERE, "tag_events")                              # N2's archive (verify/ is left as it is)
FROZEN_DIR = HERE                                                           # guard (2): the module copied here before the tag reads a bar
TESTS = os.path.join(REPO, "tests", "test_rule_mix.py")
CODE = {"mix_module": os.path.abspath(__file__), "mix_tests": TESTS}
EXITS_STUDY = os.path.join(REPO, "docs", "analysis", "cb_his_exits_study_2026-10-24.md")
INTRA_FILES = {                                                             # intra-path-ok (every entry below)
    "intra_doc": INTRA_DOC,
    "intra_frozen_module": INTRA_FROZEN,
    "intra_dryrun_printout": os.path.join(INTRA_DIR, "01_intra_dryrun.txt"),
    "intra_enter_fit_printout": os.path.join(INTRA_DIR, "01_intra_enter_fit.txt"),
    "intra_stop_fit_printout": os.path.join(INTRA_DIR, "01_intra_stop_fit.txt"),
    "intra_exit_fit_printout": os.path.join(INTRA_DIR, "01_intra_exit_fit.txt"),
    "intra_check_printout": os.path.join(INTRA_DIR, "01_intra_check.txt"),
    "intra_ledger": os.path.join(INTRA_DIR, "01_intra_ledger.tsv"),
    "intra_enter_fit_trades": os.path.join(INTRA_OUT, "enter_fit_trades.tsv"),
    "intra_check_enter_trades": os.path.join(INTRA_OUT, "check_enter_trades.tsv"),
    "intra_stop_fit_trades": os.path.join(INTRA_OUT, "stop_fit_trades.tsv"),
    "intra_check_stop_trades": os.path.join(INTRA_OUT, "check_stop_trades.tsv"),
    "intra_exit_fit_trades": os.path.join(INTRA_OUT, "exit_fit_trades.tsv"),
    "intra_check_exit_trades": os.path.join(INTRA_OUT, "check_exit_trades.tsv"),
    "exits_study": EXITS_STUDY,
}
TSV = {k[len("intra_"):]: v for k, v in INTRA_FILES.items() if k.endswith("_trades")}
FETCH_LIST = fz.FETCH_LIST                                                  # the intraday fetch list (§8: the data gate reads its logs)
TRADE_IMPACT, G8_FILES = rp.TRADE_IMPACT, rp.FILES                          # G8 (guard 4): the audit script and its era files, as the runner has them
for _p in [OUT_DIR] + list(INTRA_FILES.values()):
    assert not any(_p.startswith(d + "/") or _p == d for d in fz.FORBIDDEN_DIRS), _p      # guard (9)

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants (every number is the doc's)
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = fz.CUT_B
FIT_WIN, CHECK_WIN = fz.FIT_WIN, fz.CHECK_WIN
SEED = fz.SEED                                  # 702
DRAWS = 200
RANDOM_KEY = fz.RANDOM_KEY                      # "rev|minute": the previous read's shared stream (identical draws)
K1_KEY = "mix|rprice1|{eid}"                    # R12
K_KEY = "mix|rprice|{eid}|{d}|{i}"              # §5: the k-price control
SHARED_KEY = "mix|bracket|{eid}|{d}"            # §5: the shared-window control
RLEVEL_KEY = "mix|rlevel|{eid}|{d}"             # §5: the random-level control
RLEVEL_K_KEY = "mix|rlevel|{eid}|{d}|{i}"       # R9
WARMUP, TAIL = fz.WARMUP_SESSIONS, fz.TAIL_SESSIONS          # 10 / 20
MAX_WINDOW = fz.EXIT_HIT_MAX_WINDOW                          # 20 sessions (R17 / §7b)
MIN_PLACEMENTS = 2                                           # §4b: control (a) has room
GATE_CLOCK_SHARE = 0.98                                      # §9 gate (i), the clock arm (buy days with a bar at minute 0)
CARRIES_MARGIN, CHANCE_BAND, PRECISION_BAR, MIX_MARGIN = 0.15, 0.05, 0.50, 0.15     # §6
EXT_ADR, BIGUP_ADR = 2.0, 1.5                               # M-10 (the exits study's fixed markers)
STALL_R, TARGET_R = 1.0, 2.0                                # M-5 / M-6 on the registered R unit
SESSION_3, SESSION_5 = 2, 4                                 # offsets (the buy day = session 1 = offset 0)
CLOSE_M, UNKNOWN_M = 390, 10 ** 5                           # a daily close; a touch whose minute is unknown (after any bar event)
EARLY_CLOSE = fz.EARLY_CLOSE
BUCKETS = ("EXPLAINS", "MISS-EARLY", "UNRESOLVED", "NEITHER")
EX, ME, UN, NE = BUCKETS
CODE_OF = {EX: 0, ME: 1, UN: 2, NE: 3}
LETTER = {EX: "E", ME: "M", UN: "U", NE: "N"}
BLOCKS = ("2020", "2021-22", "untouched")
LABEL_BLOCKS = ("2020", "2021-22")
# the known answers (gate viii / vii / ix), every one copied from the printouts the doc cites
RANDOM_CONTROL_KNOWN = fz.RANDOM_CONTROL_KNOWN                                              # (0.317, 0.859) on 41
KNOWN_ENTER_STANDALONE = {"fit": ({"L1": 0.368, "L2": 0.184, "L3": 0.138, "L4": 0.011, "L5": 0.011, "L6": 0.161, "L7": 0.161, "L8": 0.345,
                                   "L9": 0.345}, 87),
                          "check": ({"L7": 0.275, "L8": 0.450, "L9": 0.450, "L1": 0.350}, 40)}
KNOWN_EXIT_RATES = {"fit": ({"E1": 0.403, "E2": 0.403, "E3": 0.396, "E4": 0.396}, 139),
                    "check": ({"E1": 0.383, "E2": 0.364, "E3": 0.355, "E4": 0.355}, 107)}
KNOWN_TRIVIAL = {"fit": (0.317, 0.201, 139), "check": (0.252, 0.140, 107), "check_und": (0.276, 0.211, 199)}     # first red close / session-3 close
FSLY = dict(eid=693, sym="FSLY", E="2020-06-29", exit_lo="2020-07-13", exit_hi="2020-07-14", m1_by="2020-07-10", touch_by="2020-07-13")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# THE LIBRARIES (§3): fixed rules in a fixed order — the table's row order IS the order (a constant, printed by the dry run, pinned with
# the module). `source` names his words (line cites into operator_shared_notes.md) or labels our reading; `order_no` is the 2020 printout
# number the order was taken from, as printed (never re-measured).
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Rule:
    nid: str
    code: str
    name: str
    tier: int
    source: str
    order_no: str


LIBRARY = {
    "ENTER": (
        Rule("E-1", "L1", "the 5-minute opening-range high", 1, "his words l.1941-1942", "feasible 36.0% on 89 (01_rev_enter_fit.txt l.12); re-read 36.8% on 87 (01_intra_enter_fit.txt l.27)"),
        Rule("E-2", "L8", "the 30-minute high (his 60-minute first candle)", 1, "his words l.1941-1942, l.2090", "34.5% on 87 (01_intra_enter_fit.txt l.25)"),
        Rule("E-3", "L2", "the prior session's high", 1, "a READING of his words l.2091-2092 (no level named)", "18.0% (01_rev_enter_fit.txt l.13); re-read 18.4% on 87 (l.28)"),
        Rule("E-4", "L7", "the 1-minute opening-range high", 1, "his words l.1941-1942", "16.1% (01_intra_enter_fit.txt l.24)"),
        Rule("E-5", "L3", "the base high / breakout level", 1, "a READING of his words l.2091-2092 (no level named)", "13.5% (01_rev_enter_fit.txt l.14); re-read 13.8% on 87 (l.29)"),
        Rule("E-6", "L9", "the prior completed 60-minute bar's high", 2, "our reading (the intraday §5a; caption tnHw5CKxcH4)", "34.5% (01_intra_enter_fit.txt l.26) - tier 2"),
        Rule("E-7", "L4", "the open", 2, "our reading (pre-market buys)", "1.1% (01_rev_enter_fit.txt l.15)"),
    ),
    "STOP": (
        Rule("S-1", "S1-T", "the low of the day up to the fill minute, touched", 1, "his words l.1943", "tier 1 alone"),
        Rule("S-2", "S10-T", "the last completed 60-minute bar's low, touched", 2, "our reading (the 60-minute lows of the option-1 ruling)", "median width 2.8% (01_intra_stop_fit.txt l.49)"),
        Rule("S-3", "S10-H", "the last completed 60-minute bar's low, 60-minute close below", 2, "our reading", "after S-2 (fire order T, H, C within a level)"),
        Rule("S-4", "S10-C", "the last completed 60-minute bar's low, daily close below", 2, "our reading", "after S-3"),
        Rule("S-5", "S9-T", "the 09:30-10:00 low, touched", 2, "our reading (his first-candle low)", "2.9% (01_intra_stop_fit.txt l.46)"),
        Rule("S-6", "S9-H", "the 09:30-10:00 low, 60-minute close below", 2, "our reading", "after S-5"),
        Rule("S-7", "S9-C", "the 09:30-10:00 low, daily close below", 2, "our reading", "after S-6"),
        Rule("S-8", "S1-H", "the low of the day at the fill, 60-minute close below", 2, "our reading (a close below where his words name the low)", "3.2% (01_intra_stop_fit.txt l.42)"),
        Rule("S-9", "S1-C", "the low of the day at the fill, daily close below", 2, "our reading", "after S-8"),
        Rule("S-10", "S3-T", "the prior session's low, touched", 2, "our reading (his FSLY words name it as an EXIT; as a stop it is our transfer)", "5.6% (01_intra_stop_fit.txt l.43)"),
        Rule("S-11", "S3-H", "the prior session's low, 60-minute close below", 2, "our reading", "after S-10"),
        Rule("S-12", "S3-C", "the prior session's low, daily close below", 2, "our reading", "after S-11"),
        Rule("S-13", "S4-T", "one ADR20 below the fill, touched", 2, "our reading of l.1943's cap used as a level", "last by definition"),
        Rule("S-14", "S4-H", "one ADR20 below the fill, 60-minute close below", 2, "our reading", "after S-13"),
        Rule("S-15", "S4-C", "one ADR20 below the fill, daily close below", 2, "our reading", "after S-14"),
    ),
    "EXIT": (
        Rule("M-1", "M-1", "the 60-minute 20-EMA close", 1, "his words (the FSLY captions cMkRsqvlVHM / YwMoUTd4naQ); all out = our reading", "E1 last-leg hit 40.3% on 139 (01_intra_exit_fit.txt l.37)"),
        Rule("M-2", "M-2", "the prior session's low, touched", 1, "his words (FSLY: took out the previous day's lows)", "39.6% (01_intra_exit_fit.txt l.37)"),
        Rule("M-3", "M-3", "the 10-day average, first close below", 1, "his words l.1946-1947, l.2046", "39 of 117 = 33.3% (exits study §3)"),
        Rule("M-4", "M-4", "the 20-day average, first close below", 1, "his words l.1946-1947, l.2046", "28 of 117 = 23.9% (exits study §3)"),
        Rule("M-5", "M-5", "the session-3 stall cut (no +1R by then)", 1, "his yes l.2078-2079 to the definition", "an upper bound only: <= 13.7% (exits study §3); a strict subset of M-9"),
        Rule("M-9", "M-9", "the close of session 3", 1, "his words l.1946 and l.2060; all out = our reading", "20.1% on 139 (01_intra_exit_fit.txt l.40)"),
        Rule("M-6", "M-6", "+2R", 1, "his words l.2046; all out = our reading", "12 of 117 = 10.3% (exits study §3)"),
        Rule("M-2s", "M-2s", "the prior session's low touched on or after the first 60-minute close below the 20-EMA", 1, "his words (the FSLY captions read as the sequence they state)", "no 2020 number: after the numbered tier-1 rules, before M-11"),
        Rule("M-11", "M-11", "the close of session 5", 1, "his words l.1946, l.2060; all out = our reading", "no 2020 hit rate: last in tier 1"),
        Rule("M-7", "M-7", "the prior session's low, daily close below", 2, "our reading (a daily close where his word was took out)", "E2 last-leg hit 40.3% on 139 (01_intra_exit_fit.txt l.37)"),
        Rule("M-8", "M-8", "the first red close", 2, "our reading (the exits study's description)", "31.7% on 139 (01_intra_exit_fit.txt l.40)"),
        Rule("M-10", "M-10", "an extension or big up day", 2, "our reading (the brief's example)", "extension 13 / big up 6 of 117 (exits study §3) -> 11.1%"),
    ),
}
DECISIONS = ("ENTER", "STOP", "EXIT")
LIB_CODES = {d: tuple(r.code for r in LIBRARY[d]) for d in DECISIONS}
STOP_CELLS = {r.code: (r.code.split("-")[0], r.code.split("-")[1]) for r in LIBRARY["STOP"]}          # "S1-T" -> ("S1", "T")
assert len(set(LIB_CODES["EXIT"])) == 12 and len(set(LIB_CODES["STOP"])) == 15 and len(set(LIB_CODES["ENTER"])) == 7


def readings_lines() -> list:
    """R1-R16 of the module docstring, one reading per line (the dry run prints them)."""
    doc = __doc__ or ""
    block = doc.split("READINGS fixed here", 1)[1].split("No subagent", 1)[0]
    out, cur = [], ""
    for ln in block.splitlines()[1:]:
        if re.match(r"^\s+R\d+\s", ln):
            if cur:
                out.append(cur)
            cur = "  " + ln.strip()
        elif ln.strip() and cur:
            cur += " " + ln.strip()
    if cur:
        out.append(cur)
    return out


def library_lines() -> list:
    out = []
    for d in DECISIONS:
        out.append(f"- {d} (the order IS the row order of §3; tier 1 = his words, tier 2 = our proposal):")
        for i, r in enumerate(LIBRARY[d], 1):
            out.append(f"  {i:2d}. {r.nid:5s} {r.code:6s} tier {r.tier} | {r.name} | source: {r.source} | ordering number: {r.order_no}")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _ival(s) -> "int | None":
    """A TSV cell -> int (None for an empty cell); `fnum` reads '45.0' (never float())."""
    if s is None or str(s).strip() in ("", "nan", "None"):
        return None
    return int(round(fnum(str(s))))


def _bval(s) -> bool:
    return str(s).strip() == "True"


def _fval(s) -> float:
    if s is None or str(s).strip() in ("", "nan", "None"):
        return math.nan
    return fnum(str(s))


def read_tsv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)


def ci_text(k: int, n: int) -> str:
    p, h = binom_ci(k, n)
    if not n:
        return "- (n 0)"
    return f"{pct(p)} [{pct(max(0.0, p - h))}, {pct(min(1.0, p + h))}] (n {n})"


def share(k, n) -> float:
    return (k / n) if n else math.nan


def write_out(name: str, rows: list, compression=None) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, name)
    pd.DataFrame(rows).to_csv(p, sep="\t", index=False, compression=compression)
    return p


# the frozen loaders and gates this read calls as they are (one name each, so the synthetic tests can stand a world in for the real data)
def load_core(say) -> dict:
    return fz.load_core(say)


def load_markets(say, C: dict, keep_A: set, keep_B: set) -> dict:
    return fz.load_for_stage(say, C, keep_A, keep_B)


def prev_population_claims(say, C: dict):
    return fz.population_claims(say, C)


def assert_populations(say, C: dict) -> None:
    fz.assert_populations(say, C)


def gate_vii(say, scored_all: dict, prev_und_eids: set) -> None:
    """(vii) the frozen gate: the random-price control re-reads 31.7% / 85.9% on the previous 41 undated 2021-22 records."""
    fz.gate_vii_random_control(say, scored_all, prev_und_eids)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock, the ledger, the outputs, the pins — the frozen helpers called with THIS read's paths (never bare: a module-scan test)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def mix_stage_outputs() -> list:
    """Files whose existence refuses --tag: its printout, a STOPPED file, every tag file under rule_mix/."""
    out = [p for p in (STOPPED, P_TAG) if os.path.exists(p)]
    if os.path.isdir(OUT_DIR):
        out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR))
    return out


def mix_any_stage_output() -> list:
    """Files whose existence refuses the dry run (it precedes the tag): the tag's outputs and the ledger."""
    return mix_stage_outputs() + ([LEDGER] if os.path.exists(LEDGER) else [])


def mix_pins(include_outputs: bool = True) -> dict:
    """Every pin: the intraday read's CARRIED pins (`fz.pins(DOC, include_outputs=False)` minus its doc-body entries, which would name THIS
    doc), the intraday printouts / TSVs / module / doc this read re-reads, this module and its tests, the dry run, the ledger, the reset
    events, `doc_body_freeze` and `doc_body` of THIS doc."""
    carried = fz.pins(DOC, include_outputs=False)
    p = {k: v for k, v in carried.items() if k not in ("doc_body_freeze", "doc_body")}
    for name, path in INTRA_FILES.items():
        p[name] = sha(path) if os.path.exists(path) else "ABSENT"
    p["intra_doc_body"] = fz.doc_body_sha(INTRA_DOC)
    for name, path in CODE.items():
        p[name] = sha(path) if os.path.exists(path) else "ABSENT"
    if include_outputs:
        p["mix_dryrun_printout"] = sha(P_DRY) if os.path.exists(P_DRY) else "ABSENT"
        p["mix_ledger"] = sha(LEDGER) if os.path.exists(LEDGER) else "ABSENT"
    p.update(fz.fit_event_pins(TAG_EVENTS))
    p["doc_body_freeze"] = fz.pin_under_marker("doc_body_freeze", DOC) or fz.doc_body_sha(DOC)
    p["doc_body"] = fz.doc_body_sha(DOC)
    return p


def check_mix_inputs(say) -> None:
    """The intraday read's pins through the frozen module, then this read's: the frozen intraday module (its sha), the intraday doc body,
    every TSV this read re-reads on disk."""
    fz.check_pinned_inputs(say)
    bad = []
    if sha(INTRA_FROZEN) != INTRA_FROZEN_SHA:
        bad.append("the frozen intraday module")
    if not fz.doc_body_sha(INTRA_DOC).startswith(INTRA_DOC_BODY_PREFIX):
        bad.append(f"the intraday doc body ({fz.doc_body_sha(INTRA_DOC)[:12]} vs {INTRA_DOC_BODY_PREFIX})")
    for k, v in INTRA_FILES.items():
        if not os.path.exists(v):
            bad.append(f"{k} missing ({v})")
    if bad:
        raise GuardStop("this read's inputs: " + "; ".join(bad))
    say("- this read's inputs: the frozen intraday module ac598fc58aae, the intraday doc body 6c3741e48788, the six intraday TSVs and the "
        "printouts on disk (their sha256 pinned under the marker)")


DRY_HEADER = "# #705 RULE MIX 01 — DRY RUN"
DRY_RESULT_RX = re.compile(r"^## RESULT: (\d+) claims, (\d+) OK, 0 MISMATCH\b")
HEX64_RX = re.compile(r"^[0-9a-f]{64}$")


def mix_dry_run_complete(path: str) -> bool:
    """THIS read's dry run, by its own text: the frozen test (the last line DRY RUN COMPLETE) on `path`, AND the first line is this module's
    dry-run header, AND a `## RESULT: .. 0 MISMATCH` line — so the intraday read's dry run copied over it does not count (guard 1)."""
    if not fz.dry_run_complete(path):
        return False
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    return bool(lines) and lines[0].startswith(DRY_HEADER) and any(DRY_RESULT_RX.match(ln) for ln in lines)


def _marker_tail(doc: str) -> "str | None":
    with open(doc, "rb") as fh:
        raw = fh.read()
    sp = fz.marker_spans(raw)
    if len(sp) != 1:
        return None
    return raw[sp[0][1]:].decode("utf-8", errors="replace")


def pins_missing_by_name(doc: str, p: dict) -> list:
    """Guard (1) by NAME (the frozen `freeze_missing` asks only that each VALUE appears somewhere under the marker): a 64-hex pin must be the
    value `pin_under_marker(name, doc)` reads on that pin's own line; an ABSENT pin must sit on its own literal `- name: ABSENT` line; any other
    value on a `- name: value` line. -> the names that fail."""
    tail = _marker_tail(doc)
    if tail is None:
        return list(p)
    bad = []
    for name, v in p.items():
        v = str(v)
        if HEX64_RX.match(v):
            ok = fz.pin_under_marker(name, doc) == v
        else:
            ok = re.search(rf"^\s*[-*]?\s*`?{re.escape(name)}`?\s*:\s*`?{re.escape(v)}`?\s*$", tail, re.M) is not None
        if not ok:
            bad.append(name)
    return bad


def tag_lock(say=None) -> list:
    """Guard (1): the reasons --tag refuses (empty = it may run)."""
    bad = []
    exo = mix_stage_outputs()
    if exo:
        bad.append(f"tag output(s) already on disk: {exo[:4]}{' ...' if len(exo) > 4 else ''} (the tag runs once; after a STOP: --reset)")
    if not mix_dry_run_complete(P_DRY):
        bad.append(f"THIS read's dry run has not COMPLETED ({os.path.basename(P_DRY)} missing, its last line is not DRY RUN COMPLETE, its first line is not "
                   f"'{DRY_HEADER}' or it carries no '## RESULT: .. 0 MISMATCH' line) — the intraday read's dry run does not count")
    ok, why = fz.freeze_state(DOC, FREEZE_BODIES)
    if not ok:
        bad.append("the freeze lock: " + why)
    p = mix_pins()
    miss = fz.freeze_missing(DOC, p)
    if miss:
        bad.append("pins not under the marker: " + ", ".join(miss[:8]) + (" ..." if len(miss) > 8 else ""))
    by_name = [k for k in pins_missing_by_name(DOC, p) if k not in miss]
    if by_name:
        bad.append("pins whose OWN line under the marker does not carry their value (checked by name): " + ", ".join(by_name[:8])
                   + (" ..." if len(by_name) > 8 else ""))
    if fz.pin_under_marker("mix_module", DOC) != sha(CODE["mix_module"]):
        bad.append("the mix_module pin under the marker is not this file")
    if os.path.exists(LEDGER):
        lb = fz.ledger_verify(LEDGER)
        if lb:
            bad.append("the ledger does not match the disk: " + "; ".join(lb))
    ub = fz.fit_events_undisclosed(DOC, TAG_EVENTS)
    if ub:
        bad.append("a reset's archived run is not disclosed (N2): " + "; ".join(ub))
    return bad


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the four buckets (§4a). ONE scalar function for the real window; ONE vectorised function for every control placement — gate (x) holds
# them equal at the real window, so neither can drift from the other.
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Fire:
    """A rule's first firing on one trade: the event's session and minute, the BOOKED session (§4a's table), the buy-day unresolved flag,
    the missing minute sessions at or after the armed point, an abstention, the sale's minute on the booked session (the exit_lo frame
    test), the frame-free first firing's booked session (gate viii-b), R2's alternative."""
    je: "int | None" = None
    m: "int | None" = None
    jb: "int | None" = None
    bd_unres: bool = False
    missing: tuple = ()
    abstain: str = ""
    sale_m: "int | None" = None
    raw_jb: "int | None" = None
    alt: "Fire | None" = None
    r16: str = ""                                 # R16: a STOP C cell's buy-day close the clock test moved ('unres' / 'skip'), else ''


def bucket(f: Fire, lo: int, hi: int) -> str:
    """R1 on one window [lo, hi] (session offsets)."""
    if f.abstain:
        return NE
    if f.alt is not None:                                                 # R2
        a = bucket(dataclasses.replace(f, alt=None), lo, hi)
        b = bucket(f.alt, lo, hi)
        return a if a == b else UN
    if f.jb is not None and f.jb <= hi:
        if f.bd_unres:
            return UN
        if any(s < f.je for s in f.missing):
            return UN
        return EX if f.jb >= lo else ME
    if f.jb is not None and f.bd_unres:
        return UN
    if any(s <= hi for s in f.missing):
        return UN
    return NE


def bucket_vec(f: Fire, starts: np.ndarray, width: int, frames: bool = True) -> np.ndarray:
    """R1 on every placement [s, s + width - 1] at once -> bucket codes (CODE_OF). `frames=False` (R15): the buy-day frame rule is not
    applied (a placement has no frames): a buy-day firing reads by the window alone; R2's close-fill touch reads its buy-day alternative."""
    starts = np.asarray(starts, dtype=np.int64)
    ends = starts + width - 1
    out = np.full(len(starts), CODE_OF[NE], dtype=np.int8)
    if f.abstain:
        return out
    if f.alt is not None:
        a = bucket_vec(dataclasses.replace(f, alt=None), starts, width, frames)
        if not frames:
            return a
        b = bucket_vec(f.alt, starts, width, frames)
        return np.where(a == b, a, CODE_OF[UN]).astype(np.int8)
    if not frames and f.bd_unres:
        f = dataclasses.replace(f, bd_unres=False)
    miss_min = min(f.missing) if f.missing else 10 ** 9
    if f.jb is not None:
        fired = f.jb <= ends
        if f.bd_unres or (f.missing and miss_min < f.je):
            out[fired] = CODE_OF[UN]
        else:
            out[fired & (f.jb >= starts)] = CODE_OF[EX]
            out[fired & (f.jb < starts)] = CODE_OF[ME]
        rest = ~fired
        if f.bd_unres:
            out[rest] = CODE_OF[UN]
        out[rest & (miss_min <= ends)] = CODE_OF[UN]
        return out
    out[miss_min <= ends] = CODE_OF[UN]
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the buy day's frames (§6a's certainty rule, the frozen held_through_intra's reading of it)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def frame_minutes(rec) -> tuple:
    """(first_m, flat_m): the in-session holding frame's minute on the buy day (None without one) and the flat frame's (None when absent or
    pre-market) — as `held_through_intra` reads them."""
    b = rec.b
    first_m = hhmm_to_min(b.first_clock) if (b.first_clock and b.f_ctx == "in") else None
    if first_m is not None and first_m < 0:
        first_m = None
    flat_m = hhmm_to_min(b.flat_clock) if b.flat_clock else None
    if flat_m is not None and flat_m < 0:
        flat_m = None
    return first_m, flat_m


def day0_lower(rec, flat_m) -> int:
    """Buy-day events at or before this minute are not events (he was flat, or had not filled): the later of the fill minute and flat_clock;
    a close fill (None) leaves only the close itself."""
    if rec.fill_minute is None:
        return CLOSE_M - 1
    return max(int(rec.fill_minute), flat_m if flat_m is not None else -1)


def day0_status(m, lower: int, first_m) -> str:
    """'skip' (not an event: the scan goes on) | 'certain' | 'unres' for a buy-day event at minute m (None = unknown)."""
    if m is None:
        return "unres"
    if m <= lower:
        return "skip"
    if first_m is None:
        return "unres"
    return "certain" if m >= first_m else "unres"


def nomin_sessions(rec, store, j_to: int) -> tuple:
    """The sessions 0..j_to (own calendar) without a 60-minute bar (no minutes): the missing sessions of §4a / §8."""
    out = []
    for j in range(0, j_to + 1):
        if rec.session_date(j) is None:
            break
        bars = (fz.h60_bars(rec.mb, rec.b.E) if rec.mb is not None else None) if j == 0 else rec.h60(store, j)
        if bars is None:
            out.append(j)
    return tuple(out)


def h_booking(rec, store, je: int, close_minute: int) -> tuple:
    """(booked session, sale minute) of a 60-minute close below: the next minute's open in that session, else the next session's open, else
    that session's close (the frozen `exit_walk_intra` / `stop_walk_h` booking)."""
    mb_j = rec.mb if je == 0 else rec.minutes(store, je)
    nx = fz.next_minute_open(R.h60_trim(mb_j, rec.session_date(je) in EARLY_CLOSE), close_minute) if mb_j is not None else None
    if nx is not None:
        return je, int(nx[0])
    if rec.bar_at(je + 1) is not None:
        return je + 1, 0
    return je, CLOSE_M


# ═════════════════════════════════════════════════════════════════════════════════════════════
# STOP — the fifteen cells through the frozen held_through_intra (the real window), continued past exit_hi for control (b)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def add_s4(rec) -> None:
    """S4 = one ADR20 below the REGISTERED fill (§3b), beside the frozen levels."""
    rec.stop_levels = dict(rec.stop_levels, S4=fnum(rec.fill) * (1.0 - fnum(rec.adr20)))


def continue_scan(rec, lvl, variant: str, smas: dict, store, j_from: int, j_to: int) -> tuple:
    """The first firing of a stop cell on sessions j_from..j_to (the tail past exit_hi, for control b): T a daily low at the level, C a
    daily close below, H a 60-minute close below (a session without minutes is skipped; it is in the record's missing list). -> (j, m)."""
    for j in range(j_from, j_to + 1):
        k = rec.bar_at(j)
        if k is None:
            return None, None
        L = rev.level_at(rec, lvl, j, smas)
        if not np.isfinite(L):
            continue
        if variant == "T":
            if fnum(rec.bars.l[k]) <= L:
                m = fz.first_touch_minute(rec.minutes(store, j), L)
                return j, (m if m is not None else UNKNOWN_M)
        elif variant == "C":
            if fnum(rec.bars.c[k]) < L:
                return j, CLOSE_M
        else:
            bars = rec.h60(store, j)
            if bars is None:
                continue
            for x in bars:
                if x is not None and x.c < L:
                    return j, int(x.close_minute)
    return None, None


def stop_fire(rec, code: str, smas: dict, sight, store, J_tail: int, nomin: tuple) -> tuple:
    """(Fire, the frozen held_through_intra output) for one STOP cell on one record (registered fill; `rec.stop_levels` carries S4)."""
    name, V = STOP_CELLS[code]
    lvl = rec.stop_levels.get(name)
    if lvl is None:
        return Fire(abstain="no_level"), None
    L0 = rev.level_at(rec, lvl, 0, smas)
    if not np.isfinite(L0):
        return Fire(abstain="no_level"), None
    h = fz.held_through_intra(rec, name, V, smas, sight, store)
    lo, hi = rec.exit_lo_j, rec.exit_hi_j
    is_day_low = bool(rec.stop_levels.get("S1_is_S2")) and (name == "S1" or (name in ("S9", "S10") and rec.stop_levels.get(f"{name}_is_S1")))
    j0 = 1 if (V == "T" and is_day_low) else 0
    missing = tuple(s for s in nomin if s >= (0 if rec.fill_minute is not None else 1)) if V == "H" else ()
    je, m = h["first_j"], h["event_m"]
    r16 = ""
    if V == "C" and je == 0:
        # R16: the frozen function applies no buy-day clock test to C; §4a's (and the exit daily rules') does — no in-session buy-day frame ->
        # UNRESOLVED; a close at or before flat_clock is not an event and the scan goes on
        first_m, flat_m = frame_minutes(rec)
        st = day0_status(CLOSE_M, day0_lower(rec, flat_m), first_m)
        if st == "skip":
            r16 = "skip"
            je, m = continue_scan(rec, lvl, V, smas, store, 1, J_tail)
        elif st == "unres":
            r16 = "unres"
    if je is None:
        je, m = continue_scan(rec, lvl, V, smas, store, hi + 1, J_tail)
    elif m is None:
        if V == "C":
            m = CLOSE_M
        elif V == "T" and je >= 1:
            mm = fz.first_touch_minute(rec.minutes(store, je), rev.level_at(rec, lvl, je, smas))
            m = mm if mm is not None else UNKNOWN_M

    def booked(j, mm):
        if j is None:
            return None, None
        if V == "H":
            return h_booking(rec, store, j, mm)
        return j, (CLOSE_M if V == "C" else mm)

    jb, sale = booked(je, m)
    close_fill = (V == "T" and j0 == 0 and not (rec.mb is not None and rec.fill_minute is not None) and rec.fill_minute != 0
                  and fnum(rec.bars.l[rec.e]) <= L0)
    if close_fill:                                                                   # R2
        alt = Fire(je=je, m=m, jb=jb, sale_m=sale, missing=missing)
        return Fire(je=0, m=None, jb=0, sale_m=None, missing=missing, alt=alt), h
    bd = False
    if r16 == "unres":
        bd = True                                                                    # R16
    elif r16 == "skip":
        bd = False
    elif h["unresolved"]:
        if h["first_j"] == 0:
            bd = True
        elif h["first_j"] is not None and h["first_j"] == lo:
            bd = False                                                               # R3: an exit_lo unresolved
        else:
            bd = True
    return Fire(je=je, m=m, jb=jb, sale_m=sale, bd_unres=bd, missing=missing, r16=r16), h


# ═════════════════════════════════════════════════════════════════════════════════════════════
# EXIT — the twelve rules' first firings WITHOUT a stop (§9), on the frozen primitives (the 60-minute bars, the EMA, armed_index,
# prior_low, first_touch_minute, the trivial session offsets)
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Ctx:
    lo: "int | None"
    hi: "int | None"
    J_tail: int
    first_m: "int | None"
    flat_m: "int | None"
    lower: int
    armed: "int | None"
    armed_j: "int | None"
    armed_close_m: "int | None"
    thin: bool
    nomin: tuple


def make_ctx(rec, prep: dict, store) -> Ctx:
    first_m, flat_m = frame_minutes(rec)
    seq, armed = prep["seq"], prep["armed"]
    aj = seq.items[armed][0] if armed is not None else None
    am = int(seq.items[armed][1].close_minute) if armed is not None else None
    return Ctx(rec.exit_lo_j, rec.exit_hi_j, int(prep["J_tail"]), first_m, flat_m, day0_lower(rec, flat_m), armed, aj, am, bool(prep["thin"]),
               nomin_sessions(rec, store, int(prep["J_tail"])))


def _touch_scan(rec, store, ctx: Ctx, j_from: int, after_first: int, j_to: int, frames: bool) -> "tuple | None":
    """The first touch of the prior session's low from session j_from (minutes after `after_first` on that session, any minute later):
    the minutes when present (the 60-minute trim), else the daily bar (a gap under it at the open, else a low at it, minute unknown) —
    the frozen E4 reading. `frames` applies the buy-day rule. -> (j, m, status) or None."""
    for j in range(max(0, j_from), j_to + 1):
        k = rec.bar_at(j)
        if k is None:
            return None
        PL = fz.prior_low(rec, j)
        if PL is None:
            continue
        after = after_first if j == j_from else -1
        mb_j = rec.mb if j == 0 else rec.minutes(store, j)
        if mb_j is not None:
            tr = R.h60_trim(mb_j, rec.session_date(j) in EARLY_CLOSE)
            if j == 0 and frames:
                after = max(after, ctx.lower)
            m = fz.first_touch_minute(tr, PL, after)
            if m is None:
                continue
            st = day0_status(m, ctx.lower, ctx.first_m) if (j == 0 and frames) else "certain"
            return j, int(m), st
        if j >= 1:
            if fnum(rec.bars.o[k]) < PL:
                return j, 0, "certain"
            if fnum(rec.bars.l[k]) <= PL:
                return j, UNKNOWN_M, "certain"
    return None


def fire_m1(rec, prep: dict, store, ctx: Ctx) -> Fire:
    if ctx.armed is None:
        return Fire(abstain="no_armed_bar")
    if ctx.thin:
        return Fire(abstain="ema_thin")
    seq = prep["seq"]
    missing = tuple(s for s in ctx.nomin if s >= ctx.armed_j)
    raw = None
    for i in range(ctx.armed, len(seq.items)):
        j, x = seq.items[i]
        if j > ctx.J_tail:
            break
        if not (np.isfinite(seq.ema[i]) and x.c < seq.ema[i]):
            continue
        cm = int(x.close_minute)
        if raw is None:
            raw = h_booking(rec, store, j, cm)[0]
        st = day0_status(cm, ctx.lower, ctx.first_m) if j == 0 else "certain"
        if st == "skip":
            continue
        jb, sale = h_booking(rec, store, j, cm)
        return Fire(je=j, m=cm, jb=jb, sale_m=sale, bd_unres=(st == "unres"), missing=missing, raw_jb=raw)
    return Fire(missing=missing, raw_jb=raw)


def fire_m2(rec, prep: dict, store, ctx: Ctx) -> Fire:
    if ctx.armed is None:
        return Fire(abstain="no_armed_bar")
    raw = _touch_scan(rec, store, ctx, ctx.armed_j, ctx.armed_close_m, ctx.J_tail, frames=False)
    t = _touch_scan(rec, store, ctx, ctx.armed_j, ctx.armed_close_m, ctx.J_tail, frames=True)
    rj = raw[0] if raw else None
    if t is None:
        return Fire(raw_jb=rj)
    j, m, st = t
    return Fire(je=j, m=m, jb=j, sale_m=m, bd_unres=(st == "unres"), raw_jb=rj)


def fire_m2s(rec, prep: dict, store, ctx: Ctx, f1: Fire) -> Fire:
    """Armed at M-1's first firing's bar close WHATEVER its bucket (UNRESOLVED included); M-1 abstaining -> M-2s abstains; M-1's missing
    sessions before its firing stay with M-2s (its arming could have come earlier)."""
    if f1.abstain:
        return Fire(abstain="m1_" + f1.abstain)
    if f1.je is None:
        return Fire(missing=f1.missing)
    missing = tuple(s for s in f1.missing if s < f1.je)
    t = _touch_scan(rec, store, ctx, f1.je, f1.m, ctx.J_tail, frames=True)
    if t is None:
        return Fire(missing=missing)
    j, m, st = t
    return Fire(je=j, m=m, jb=j, sale_m=m, bd_unres=(st == "unres"), missing=missing)


def fire_m7(rec, prep: dict, store, ctx: Ctx) -> Fire:
    if ctx.armed is None:
        return Fire(abstain="no_armed_bar")
    for j in range(ctx.armed_j, ctx.J_tail + 1):
        k = rec.bar_at(j)
        if k is None:
            break
        PL = fz.prior_low(rec, j)
        if PL is not None and fnum(rec.bars.c[k]) < PL:
            st = day0_status(CLOSE_M, ctx.lower, ctx.first_m) if j == 0 else "certain"
            if st == "skip":                                                         # R16: not an event; the scan goes on
                continue
            nxt = rec.bar_at(j + 1) is not None
            jb = j + 1 if nxt else j
            return Fire(je=j, m=CLOSE_M, jb=jb, sale_m=(0 if nxt else CLOSE_M), bd_unres=(st == "unres"), raw_jb=jb)
    return Fire()


def _daily_first(rec, ctx: Ctx, j_from: int, pred) -> Fire:
    """The first session j >= j_from (to J_tail) whose daily bar meets `pred(j, k)`; booked at that close."""
    for j in range(j_from, ctx.J_tail + 1):
        k = rec.bar_at(j)
        if k is None:
            break
        if pred(j, k):
            st = day0_status(CLOSE_M, ctx.lower, ctx.first_m) if j == 0 else "certain"
            if st == "skip":                                                         # R16: not an event; the scan goes on
                continue
            return Fire(je=j, m=CLOSE_M, jb=j, sale_m=CLOSE_M, bd_unres=(st == "unres"))
    return Fire()


def _fixed_session(rec, ctx: Ctx, j: int) -> Fire:
    """A rule that fires at the close of one fixed session (M-9, M-11): needs every bar up to it."""
    for jj in range(0, j + 1):
        if rec.bar_at(jj) is None:
            return Fire(abstain="hole")
    if j > ctx.J_tail:
        return Fire()
    return Fire(je=j, m=CLOSE_M, jb=j, sale_m=CLOSE_M)


def r_unit(rec) -> float:
    return fnum(rec.fill) - fnum(rec.stop)


def day0_post_fill(rec) -> "tuple | None":
    """(minutes, highs) after the fill minute on the buy day (`cb.day0_peak_high`'s minutes); an open fill without minutes -> ([None], [the
    daily high]); a close fill -> None (nothing of the buy day follows it)."""
    if rec.fill_minute is None:
        return None
    if rec.mb is not None:
        sel = rec.mb.minute > int(rec.fill_minute)
        return [int(x) for x in rec.mb.minute[sel]], [fnum(x) for x in rec.mb.h[sel]]
    if int(rec.fill_minute) == 0:
        return [None], [fnum(rec.bars.h[rec.e])]
    return None


def fire_m5(rec, ctx: Ctx) -> Fire:
    """R7: the close of offset 2 when no high reached fill + 1R by then (the day-0 peak after the fill, offsets 1-2)."""
    R_ = r_unit(rec)
    if not R_ > 0:
        return Fire(abstain="no_r_unit")
    for jj in range(0, SESSION_3 + 1):
        if rec.bar_at(jj) is None:
            return Fire(abstain="hole")
    target = fnum(rec.fill) + STALL_R * R_
    if rec.mb is not None and rec.fill_minute is not None:
        peak = fnum(cb.day0_peak_high(rec.mb, int(rec.fill_minute)))
    else:
        d0 = day0_post_fill(rec)
        peak = max(d0[1]) if d0 else -math.inf
    peak = max([peak] + [fnum(rec.bars.h[rec.bar_at(j)]) for j in range(1, SESSION_3 + 1)])
    if peak >= target:
        return Fire()
    if SESSION_3 > ctx.J_tail:
        return Fire()
    return Fire(je=SESSION_3, m=CLOSE_M, jb=SESSION_3, sale_m=CLOSE_M)


def fire_m6(rec, ctx: Ctx, store) -> Fire:
    """The first session whose high reaches fill + 2R (the registered stop's width): day 0 on the minutes after the fill (the buy-day rule),
    later sessions on the daily high (the minute from the minutes where present)."""
    R_ = r_unit(rec)
    if not R_ > 0:
        return Fire(abstain="no_r_unit")
    target = fnum(rec.fill) + TARGET_R * R_
    d0 = day0_post_fill(rec)
    if d0 is not None:
        for m, h in zip(*d0):
            if h >= target:
                st = day0_status(m, ctx.lower, ctx.first_m)
                if st == "skip":
                    continue
                return Fire(je=0, m=m, jb=0, sale_m=m, bd_unres=(st == "unres"))
    for j in range(1, ctx.J_tail + 1):
        k = rec.bar_at(j)
        if k is None:
            break
        if fnum(rec.bars.h[k]) >= target:
            mb_j = rec.minutes(store, j)
            m = UNKNOWN_M
            if mb_j is not None:
                hit = np.flatnonzero(mb_j.h >= target)
                if len(hit):
                    m = int(mb_j.minute[hit[0]])
            return Fire(je=j, m=m, jb=j, sale_m=m)
    return Fire()


def exit_fires(rec, prep: dict, store, ctx: Ctx, smas: dict) -> dict:
    """{rule code: Fire} for the twelve EXIT rules on one record (registered fill and stop)."""
    c = rec.bars.c
    adr = fnum(rec.adr20)
    out = {}
    f1 = fire_m1(rec, prep, store, ctx)
    out["M-1"] = f1
    out["M-2"] = fire_m2(rec, prep, store, ctx)
    out["M-3"] = _daily_first(rec, ctx, 0, lambda j, k: np.isfinite(smas[10][k]) and fnum(c[k]) < fnum(smas[10][k]))
    out["M-4"] = _daily_first(rec, ctx, 0, lambda j, k: np.isfinite(smas[20][k]) and fnum(c[k]) < fnum(smas[20][k]))
    out["M-5"] = fire_m5(rec, ctx)
    out["M-9"] = _fixed_session(rec, ctx, SESSION_3)
    out["M-6"] = fire_m6(rec, ctx, store)
    out["M-2s"] = fire_m2s(rec, prep, store, ctx, f1)
    out["M-11"] = _fixed_session(rec, ctx, SESSION_5)
    out["M-7"] = fire_m7(rec, prep, store, ctx)

    def red(j, k):
        kp = rec.bar_at(j - 1)
        return kp is not None and fnum(c[k]) < fnum(c[kp])
    out["M-8"] = _daily_first(rec, ctx, 1, red)

    def strong(j, k):
        kp = rec.bar_at(j - 1) if j >= 1 else rec.p
        cp = fnum(c[kp]) if (kp is not None and kp >= 0) else math.nan
        ext = np.isfinite(smas[10][k]) and fnum(c[k]) >= fnum(smas[10][k]) * (1.0 + EXT_ADR * adr)
        big = np.isfinite(cp) and fnum(c[k]) >= cp * (1.0 + BIGUP_ADR * adr)
        return bool(ext or big)
    out["M-10"] = _daily_first(rec, ctx, 0, strong)
    assert set(out) == set(LIB_CODES["EXIT"])
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the greedy tag, the earliest-firing order, the contradicted line
# ═════════════════════════════════════════════════════════════════════════════════════════════
def greedy_tag(buckets: dict, order: tuple) -> str:
    """The first rule in the library order whose bucket is EXPLAINS; none -> discretion."""
    for code in order:
        if buckets.get(code) == EX:
            return code
    return "discretion"


def earliest_tag(buckets: dict, times: dict, order: tuple) -> str:
    """The EXPLAINS rule that fired first in clock time (session, minute); ties -> the library order; none -> discretion."""
    cands = [(times[c], order.index(c), c) for c in order if buckets.get(c) == EX and times.get(c) is not None]
    return min(cands)[2] if cands else "discretion"


def fire_time(f: Fire) -> "tuple | None":
    if f.abstain or f.je is None:
        return None
    return (int(f.je), int(f.m) if f.m is not None else UNKNOWN_M)


def contradicted(rec, f: Fire, sight) -> bool:
    """An EXPLAINS booked ON exit_lo whose sale time a frame that day contradicts: a frame showing the name later in session than the sale
    minute (an open sale: any such frame), or an after-close frame for a sale at or before the close."""
    b = rec.b
    c_last = sight.last_in_session_clock(b.exit_lo, b.sym)
    after_close = bool(sight.after_close_frame(b.exit_lo, b.sym))
    sale = f.sale_m
    if sale is None or sale >= UNKNOWN_M:
        return False
    if c_last is not None and sale < hhmm_to_min(c_last):
        return True
    return after_close


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the random windows (§5): every placement enumerated with equal weight on the record's own calendar
# ═════════════════════════════════════════════════════════════════════════════════════════════
def random_windows(rec, J_tail: int, rng_range: str) -> dict:
    """(a) inside the hold: starts 0..exit_lo (his own window included); (b) hold plus tail: starts 0..exit_hi + 20 - width + 1, bounded by
    the path (J_tail: a hole, the horizon or the data's end). -> {starts, width, no_room, cut}."""
    lo, hi = rec.exit_lo_j, rec.exit_hi_j
    w = fz.exit_window_sessions(rec)
    if rng_range == "a":
        starts = np.arange(0, lo + 1, dtype=np.int64)
        return dict(starts=starts, width=w, no_room=len(starts) < MIN_PLACEMENTS, cut=False)
    last = min(hi + TAIL, int(J_tail))
    starts = np.arange(0, max(0, last - w + 1) + 1, dtype=np.int64) if last - w + 1 >= 0 else np.zeros(0, dtype=np.int64)
    return dict(starts=starts, width=w, no_room=len(starts) < MIN_PLACEMENTS, cut=int(J_tail) < hi + TAIL)


def window_summary(fires: dict, order: tuple, starts: np.ndarray, width: int, frames: bool = True) -> dict:
    """Per rule: the EXPLAINS / MISS-EARLY shares over the placements; the greedy shares; the union share. -> plus the per-placement codes."""
    n = len(starts)
    codes = {c: bucket_vec(fires[c], starts, width, frames) for c in order}
    ex = {c: codes[c] == CODE_OF[EX] for c in order}
    out = dict(n=n, ex={c: share(int(ex[c].sum()), n) for c in order}, me={c: share(int((codes[c] == CODE_OF[ME]).sum()), n) for c in order})
    taken = np.zeros(n, dtype=bool)
    greedy = {}
    for c in order:
        g = ex[c] & ~taken
        greedy[c] = share(int(g.sum()), n)
        taken |= ex[c]
    out["greedy"], out["union"], out["codes"] = greedy, share(int(taken.sum()), n), codes
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the random-level control (§5, R9): a level uniform between the hold's lowest low (from the fill minute through exit_hi) and the fill
# ═════════════════════════════════════════════════════════════════════════════════════════════
def hold_lowest_low(rec, store) -> float:
    lows = []
    if rec.fill_minute is not None:
        if rec.mb is not None:
            sel = rec.mb.minute > int(rec.fill_minute)
            if sel.any():
                lows.append(fnum(rec.mb.l[sel].min()))
        elif int(rec.fill_minute) == 0:
            lows.append(fnum(rec.bars.l[rec.e]))
    for j in range(1, rec.exit_hi_j + 1):
        k = rec.bar_at(j)
        if k is None:
            break
        lows.append(fnum(rec.bars.l[k]))
    return min(lows) if lows else math.nan


def touch_path(rec, store) -> dict:
    """The T path the frozen held_through_intra walks on a bare price from the fill, as arrays: the buy day's minutes after the later of the
    fill minute and flat_clock (their lows and minutes), then the daily lows of sessions 1..exit_hi."""
    first_m, flat_m = frame_minutes(rec)
    d0_kind, d0_m, d0_l = "none", np.zeros(0, dtype=np.int64), np.zeros(0)
    if rec.mb is not None and rec.fill_minute is not None:
        lower = max(int(rec.fill_minute), flat_m if flat_m is not None else -1)
        sel = rec.mb.minute > lower
        d0_kind, d0_m, d0_l = "minutes", rec.mb.minute[sel].astype(np.int64), np.minimum(rec.mb.l[sel], rec.mb.o[sel]).astype(float)
    elif rec.fill_minute == 0:
        d0_kind, d0_l = "open_no_minutes", np.array([fnum(rec.bars.l[rec.e])])
    else:
        d0_kind, d0_l = "close_fill", np.array([fnum(rec.bars.l[rec.e])])
    later = []
    for j in range(1, rec.exit_hi_j + 1):
        k = rec.bar_at(j)
        if k is None:
            break
        later.append(fnum(rec.bars.l[k]))
    return dict(kind=d0_kind, m=d0_m, l=d0_l, later=np.asarray(later, dtype=float), first_m=first_m)


def touch_buckets_vec(path: dict, levels: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """The frozen T reading on many bare levels at once, in his real window -> bucket codes (R1 / R2)."""
    levels = np.asarray(levels, dtype=float)
    n = len(levels)
    out = np.full(n, CODE_OF[NE], dtype=np.int8)

    def later_first(lv):                       # the first session j >= 1 whose low is at or under the level (None: not by exit_hi)
        lat = path["later"]
        if not len(lat):
            return np.full(len(lv), -1)
        run = np.minimum.accumulate(lat)
        idx = np.searchsorted(-run, -lv, side="left")
        return np.where(idx < len(lat), idx + 1, -1)

    def code_at(j):
        return np.where(j < 0, CODE_OF[NE], np.where(j < lo, CODE_OF[ME], np.where(j <= hi, CODE_OF[EX], CODE_OF[NE])))
    jl = later_first(levels)
    kind = path["kind"]
    if kind == "minutes" and len(path["l"]):
        run = np.minimum.accumulate(path["l"])
        idx = np.searchsorted(-run, -levels, side="left")
        d0 = idx < len(run)
        mm = np.where(d0, path["m"][np.minimum(idx, len(run) - 1)], -1)
        fm = path["first_m"]
        cert = d0 & (fm is not None) & (mm >= (fm if fm is not None else 10 ** 9))
        d0code = np.where(cert, CODE_OF[EX] if lo == 0 else CODE_OF[ME], CODE_OF[UN])
        out = np.where(d0, d0code, code_at(jl)).astype(np.int8)
        return out
    if kind == "open_no_minutes":
        d0 = path["l"][0] <= levels
        return np.where(d0, CODE_OF[UN], code_at(jl)).astype(np.int8)
    if kind == "close_fill":
        d0 = path["l"][0] <= levels
        a = CODE_OF[EX] if lo == 0 else CODE_OF[ME]
        b = code_at(jl)
        return np.where(d0, np.where(b == a, a, CODE_OF[UN]), b).astype(np.int8)
    return code_at(jl).astype(np.int8)


def random_level_draws(rec, key: str, k: int = 0) -> "np.ndarray | None":
    """The 200 drawn levels (k = 0: one per draw, the per-rule floor; k > 0: k per draw, the union line); None when there is no room."""
    lowest = rec.rlevel_lowest
    fill = fnum(rec.fill)
    if not (np.isfinite(lowest) and lowest < fill):
        return None
    if k == 0:
        return np.array([fz.rng_for(key.format(eid=rec.b.eid, d=d)).uniform(lowest, fill) for d in range(DRAWS)])
    return np.array([[fz.rng_for(key.format(eid=rec.b.eid, d=d, i=i)).uniform(lowest, fill) for i in range(1, k + 1)] for d in range(DRAWS)])


# ═════════════════════════════════════════════════════════════════════════════════════════════
# ENTER — the previous draw stream replayed exactly; the frozen scoring; the four controls
# ═════════════════════════════════════════════════════════════════════════════════════════════
class Playback:
    """Hands the frozen `random_levels` the replayed draw of THIS record (one call, the exact shape) — `enter_score_trade` then scores the
    previous read's identical random prices."""

    def __init__(self, u):
        self.u = np.asarray(u, dtype=np.int64)
        self.calls = 0

    def integers(self, low, high, size=None):
        if self.calls or (low, high) != (0, 390) or size != len(self.u):
            raise GuardStop(f"the replayed draw was asked twice or in another shape ({low}, {high}, {size})")
        self.calls += 1
        return self.u.copy()


def clocks_ok(b) -> bool:
    return hhmm_to_min(b.first_clock) is not None and hhmm_to_min(b.flat_clock) is not None


def enter_draw_orders(C: dict, cs: dict, has_mb) -> dict:
    """The previous read's draw ORDER, per stream (the fit's and the check's: each a fresh `rng_for(RANDOM_KEY)`), group by group, exactly as
    the frozen stages walked it: {stream: [(group, [eids])]}. `has_mb(b)` = the buy has a record with buy-day minutes."""
    E, S = C["E"], C["S"]
    by_date = lambda b: (b.E, b.eid)                                         # noqa: E731

    def ordered(bs, key=by_date, clocks=False):
        return [b.eid for b in sorted(bs, key=key) if has_mb(b) and (not clocks or clocks_ok(b))]
    kept_b = {b.eid for b in cs["enter_beside"]["kept"]}
    fit = [("", ordered(cs["enter"]["kept"]))]
    for lab, key in (("flickers 2020 (in-session windows after §2c)", "fit_fl"), ("pre-market-flat windows, dated 2020", "pre_dated_fit"),
                     ("pre-market-flat windows, undated 2020", "pre_und_fit")):
        fit.append((lab, ordered([b for b in E[key] if b.eid in kept_b], clocks=True)))
    chk = [("", ordered(S["ent_chk_dated"] + S["ent_chk_und"])), ("flickers", ordered(E["chk22_fl"])),
           ("virgin", ordered(E["virgin"], key=lambda b: (b.flicker, b.E, b.eid))),
           ("pre-dated-2021-22", ordered(E["pre_dated_chk"], clocks=True)), ("pre-undated-2021-22", ordered(E["pre_und_chk"], clocks=True))]
    return {"fit": fit, "check": chk}


def replay_draws(orders: dict) -> dict:
    """{(stream, eid): the 200 minute draws} — the shared generator walked over the EXACT previous population in its order."""
    out = {}
    for stream, groups in orders.items():
        rng = fz.rng_for(RANDOM_KEY)
        for _g, eids in groups:
            for eid in eids:
                if (stream, eid) in out:
                    raise GuardStop(f"eid {eid} appears twice in the {stream} draw population")
                out[(stream, eid)] = rng.integers(0, 390, size=fz.RANDOM_LEVELS)
    return out


def enter_bucket(s: dict, flat_m: int, first_m: int) -> str:
    """ENTER: EXPLAINS = first crossed in (flat, first] (feasible); MISS-EARLY = crossed at or before flat_clock; NEITHER otherwise or when
    the level abstains (no_level_yet / no_bar_0930 / no_level)."""
    c = s.get("cross")
    if s.get("verdict") in ("no_level_yet", "no_bar_0930", "no_level") and c is None:
        return NE
    if c is None:
        return NE
    if s.get("feasible"):
        return EX
    return ME if c <= flat_m else NE


def window_feasible(cross, exist_min: int, starts: np.ndarray, width: int) -> tuple:
    """(EXPLAINS flags, MISS-EARLY flags) of a level whose first crossing minute is `cross`, in windows (s, s + width] — not feasible when the
    level does not yet exist at the window's end (§5)."""
    starts = np.asarray(starts, dtype=np.int64)
    exists = starts + width >= exist_min
    if cross is None:
        z = np.zeros(len(starts), dtype=bool)
        return z, z
    return exists & (starts < cross) & (cross <= starts + width), exists & (cross <= starts)


def enter_one(rec, u, stream: str) -> dict:
    """The frozen scoring of one in-session window (L1-L9, the random-price control on the replayed draw, the per-level shifted control, the
    union), then this read's: the library's buckets, the k-price control, the shared-window control, the precision of every control."""
    order = LIB_CODES["ENTER"]
    flat_m, first_m = hhmm_to_min(rec.b.flat_clock), hhmm_to_min(rec.b.first_clock)
    w = first_m - flat_m
    res = fz.enter_score_trade(rec, Playback(u), with_shift=True)
    Lv = fz.intraday_levels(rec)
    real = {lv: enter_bucket(res[lv], flat_m, first_m) for lv in order}
    times = {lv: ((0, int(res[lv]["cross"])) if res[lv]["cross"] is not None else None) for lv in order}
    crosses = {lv: fz.level_price_fn(lv, rec, Lv)[0] for lv in order}
    exists = {lv: fz.LEVEL_EXISTS.get(lv, 0) for lv in order}
    out = dict(res=res, real=real, times=times, crosses=crosses, stream=stream, flat_m=flat_m, first_m=first_m, width=w)
    # the random-price control (the replayed draw): EXPLAINS = feasible, MISS-EARLY = crossed at or before flat_clock
    prices = rev.random_levels(rec.mb, fz.RANDOM_LEVELS, Playback(u))
    cr = [rev.first_cross(rec.mb, fnum(p)) for p in prices]
    rf = np.array([c is not None and flat_m < c <= first_m for c in cr])
    rm = np.array([c is not None and c <= flat_m for c in cr])
    if not np.array_equal(rf, np.asarray(res["control"]["feas"], dtype=bool)):
        raise GuardStop(f"the random-price control re-score differs from the frozen one on eid {rec.b.eid}")
    out["rprice"] = dict(ex=fnum(rf.mean()), me=fnum(rm.mean()))
    # the k-price control: 7 random prices per draw, price i standing for library rule i
    kx = np.zeros((DRAWS, len(order)), dtype=bool)
    km = np.zeros((DRAWS, len(order)), dtype=bool)
    kp = np.zeros((DRAWS, len(order)), dtype=float)
    for d in range(DRAWS):
        for i in range(len(order)):
            p = fnum(rev.random_levels(rec.mb, 1, fz.rng_for(K_KEY.format(eid=rec.b.eid, d=d, i=i + 1)))[0])
            kp[d, i] = p
            c = rev.first_cross(rec.mb, p)
            kx[d, i] = c is not None and flat_m < c <= first_m
            km[d, i] = c is not None and c <= flat_m
    out["kprice"] = dict(matrix_summary(kx, km, order), prices=kp, codes=kx)
    # the shared-window control: one start per draw, every level scored in that same window
    close = fz.session_end_minute(rec.b.E)
    if close - w < 1 or w <= 0:
        out["shared"] = dict(no_room=True)
    else:
        starts = np.array([1 + int(fz.rng_for(SHARED_KEY.format(eid=rec.b.eid, d=d)).integers(0, close - w)) for d in range(DRAWS)], dtype=np.int64)
        sx = np.zeros((DRAWS, len(order)), dtype=bool)
        sm = np.zeros((DRAWS, len(order)), dtype=bool)
        for i, lv in enumerate(order):
            sx[:, i], sm[:, i] = window_feasible(crosses[lv], exists[lv], starts, w)
        out["shared"] = dict(matrix_summary(sx, sm, order), no_room=False, starts=starts, codes=sx)
    # the per-level shifted control (frozen draws, each level its own window): its union over the library
    px = np.zeros((DRAWS, len(order)), dtype=bool)
    pm = np.zeros((DRAWS, len(order)), dtype=bool)
    room = {}
    for i, lv in enumerate(order):
        s_ = res["shift"][lv]
        room[lv] = not s_["no_room"]
        if s_["no_room"]:
            continue
        px[:, i] = np.asarray(s_["feas"], dtype=bool)
        st = np.asarray(s_["starts"], dtype=np.int64)
        c = crosses[lv]
        pm[:, i] = (c is not None) & (st >= (c if c is not None else 10 ** 9))
    out["shift"] = dict(matrix_summary(px, pm, order), room=room, ex_lv={lv: (fnum(res["shift"][lv]["feasible_share"]) if room[lv] else math.nan) for lv in order})
    return out


def matrix_summary(X: np.ndarray, Mx: np.ndarray, order: tuple) -> dict:
    """Draw x rule EXPLAINS / MISS-EARLY flags -> per-rule shares, greedy shares (the library order), the union share."""
    n = X.shape[0]
    taken = np.zeros(n, dtype=bool)
    greedy = {}
    for i, c in enumerate(order):
        greedy[c] = share(int((X[:, i] & ~taken).sum()), n)
        taken |= X[:, i]
    return dict(ex={c: share(int(X[:, i].sum()), n) for i, c in enumerate(order)}, me={c: share(int(Mx[:, i].sum()), n) for i, c in enumerate(order)},
                greedy=greedy, union=share(int(taken.sum()), n))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the populations (§2): the sets as the intraday read has them; ENTER / STOP / EXIT blocks; the printout populations (guard 5 applied)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def enter_blocks(C: dict) -> dict:
    """{block: {"tagged": [buys], "sub": {name: [buys]}, "beside": {label: [buys]}}} (R11)."""
    E = C["E"]
    return {
        "2020": dict(tagged=E["fit_dated"] + E["fit_und"], sub={"dated": E["fit_dated"], "undated non-flicker": E["fit_und"]},
                     beside={"flickers": E["fit_fl"], "pre-market-flat, dated": E["pre_dated_fit"], "pre-market-flat, undated": E["pre_und_fit"]}),
        "2021-22": dict(tagged=E["chk22_und"] + E["chk22_dated"], sub={"undated non-flicker": E["chk22_und"], "dated": E["chk22_dated"]},
                        beside={"flickers": E["chk22_fl"], "pre-market-flat, dated": E["pre_dated_chk"], "pre-market-flat, undated": E["pre_und_chk"]}),
        "untouched": dict(tagged=E["virgin_nf"], sub={"non-flicker": E["virgin_nf"]}, beside={"flickers": E["virgin_fl"]}),
    }


def se_blocks(C: dict) -> dict:
    """STOP / EXIT: {block: {sub: [buys]}} — dated and undated per block (R11)."""
    I = C["I"]
    return {"2020": {"dated": I["fit_dated"], "undated": I["fit_und"]},
            "2021-22": {"dated": I["chk22_dated"], "undated": I["chk22_und"]},
            "untouched": {"dated": I["virgin_dated"], "undated": I["virgin_und"]}}


def stream_of_block(block: str) -> str:
    return "fit" if block == "2020" else "check"


def all_enter_buys(C: dict) -> list:
    seen, out = set(), []
    for blk in enter_blocks(C).values():
        for bs in [blk["tagged"]] + list(blk["beside"].values()):
            for b in bs:
                if b.eid not in seen:
                    seen.add(b.eid)
                    out.append(b)
    for b in C["S"]["ent_chk_dated"] + C["S"]["ent_chk_und"] + C["E"]["virgin"]:
        if b.eid not in seen:
            seen.add(b.eid)
            out.append(b)
    return out


def all_se_buys(C: dict) -> list:
    out, seen = [], set()
    for blk in se_blocks(C).values():
        for bs in blk.values():
            for b in bs:
                if b.eid not in seen:
                    seen.add(b.eid)
                    out.append(b)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run's claims against THIS doc (anchors resolve into THIS doc; the intraday registration's set claims run through the frozen
# `population_claims` against its own doc)
# ═════════════════════════════════════════════════════════════════════════════════════════════
class MixClaims(fz.Claims):
    """Every claim printed with the line of THIS doc its anchor resolves to; every mismatch collected; STOP at the end, never at the first.
    `note=True` claims print and never stop (an "about" number, a count the dry run cannot read without an outcome)."""

    def __init__(self, say, doc: str = None):
        super().__init__(say)
        self.doc = doc or DOC
        self.notes = []

    def __call__(self, anchor: str, label: str, doc, mine, note: bool = False) -> bool:
        ok = self._norm(doc, label) == self._norm(mine, label)
        ln = fz.doc_line_of(anchor, self.doc)
        tag = "OK" if ok else ("NOTE" if note else "MISMATCH")
        self.say(f"  [L{ln if ln else '?'}] {label} | doc {fz.fmt_claim(doc)} | mine {fz.fmt_claim(mine)} | {tag}")
        if note:
            self.notes.append((ln, label, doc, mine))
            return ok
        self.n += 1
        if not ok or not ln:
            self.bad.append((ln, label + ("" if ln else " (anchor not found in the doc)"), doc, mine))
        return ok


EXPECT_MIX = {   # label: (anchor in THIS doc, value)
    "guard5_returning": ("ENTER fit 1 of 90", "1 of 90 / 16 of 453 / 10 of 149"),
    "run_records": ("the run's records are about 88 / 431 / 149", "88 / 431 / 149"),
    "enter_2020": ("in-session windows after §2c: 31 dated + 59 undated non-flicker (34 flickers beside)", "31 + 59 (34); 87 = 30 + 57; 28"),
    "enter_2122": ("20 dated (7 flickers) + 43 undated non-flicker windows (19 undated flickers)", "20 (7) + 43 (19); 40 + 20; 19"),
    "enter_untouched": ("9 non-flicker + 8 flickers (2019: 6 nf; APT 2020-01-23; CVNA, AI 2023)", "9 + 8; 9 + 7"),
    "enter_premarket": ("pre-market-flat windows: 2020 41 dated + 56 undated scored (58 in the population)", "41 + 56 (58); 41 + 52 (55)"),
    "stop_2020": ("dated 149 + undated 304 (flickers in), THOSE whose exit was a loss", "149 + 304"),
    "se_2122": ("dated 111 (110 records) + undated 226 (212), the losers", "111 (110) + 226 (212)"),
    "stop_untouched": ("62 undated (58 records) + 27 dated (26), the losers", "62 (58) + 27 (26)"),
    "exit_2020": ("139 scorable for the hit rate", "149; 139"),
    "exit_2122": ("107 armed / 199 scorable", "107"),
    "exit_untouched": ("27 dated (23 with exits on the timeline, 19 of them with windows ≤ 20 sessions; after the record floor 22 trades, 18 windows",
                       "27 / 23 / 19; 22 / 18; 62"),
    "fit_chain_rows": ("`fill_level:L8` on 33 stop rows and", "33 / 8 / 22"),
    "fetch_log": ("19,184 ok, 286 empty at the source", "19470 / 19184 / 286 / 0"),
    "vii_population": ("Gate (vii) re-reads 31.7% / 85.9% on the previous 41 undated 2021-22 records", "41"),
    "fsly": ("FSLY eid 693 (undated 2020-06-29", "FSLY 2020-06-29 2020-07-13..2020-07-14 undated"),
}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run
# ═════════════════════════════════════════════════════════════════════════════════════════════
def composition_enter(C: dict, store, mis: dict) -> dict:
    """§4c from the clocks alone (+ the fetch logs for no_minutes): per block, every buy after §2b."""
    I = C["I"]
    out = {}
    for blk, bs in (("2020", I["fit_dated"] + I["fit_und"]), ("2021-22", I["chk22_dated"] + I["chk22_und"]), ("untouched", I["virgin_all"])):
        c = Counter()
        for b in bs:
            if b.in_bracket:
                if fz.clock_sane(b, mis) != "ok":
                    c["dropped by §2c"] += 1
                elif b.flicker and not b.dated:
                    c["in-session, undated flicker (beside)"] += 1
                elif not store.state(b.E, bar_sym(b.E, b.sym_a, b.sym), b).startswith("ok"):
                    c["in-session, no_minutes"] += 1
                else:
                    c["in-session (taggable)"] += 1
            elif b.pre_flat_bracket:
                c["pre-market-flat window (beside)"] += 1
            elif b.first_clock and not b.flat_clock:
                c["no flat frame on the buy day"] += 1
            elif b.f_ctx == "pre":
                c["pre-market first sighting"] += 1
            else:
                c["no frame on the buy day / first seen after the close"] += 1
        out[blk] = (len(bs), c)
    return out


def dry_run(say) -> int:
    say(f"{DRY_HEADER}: every input loaded; the intraday registration's set claims and every count of §2 / §8 of THIS doc "
        "asserted; the composition line from the clocks; the data gate from the fetch logs only; the library order; the pins. NO outcome: "
        "no minute file opened, no bar after a buy day, no rule fired, the loss share not computed.")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    check_mix_inputs(say)
    C = load_core(say)
    S, I, E, mis = C["S"], C["I"], C["E"], C["mis"]
    claim = MixClaims(say)

    def ck(key, mine, note=False):
        a, v = EXPECT_MIX[key]
        return claim(a, key + ": " + LABELS[key], v, mine, note=note)
    say("\n## The intraday registration's set claims (the frozen population_claims, against its own doc)")
    prev = prev_population_claims(say, C)
    claim("Every set equals the previous registrations' counts", "the intraday registration's set claims: OK / MISMATCH", f"{prev.n} OK, 0 MISMATCH",
          f"{prev.n - len(prev.bad)} OK, {len(prev.bad)} MISMATCH")
    ni = S["ni"]
    need_A = {b.sym_a for b in ni if b.has_bars} | {"QQQ", "SPY"}
    need_B = {b.sym for b in ni if b.has_bars and b.E > fz.A_LAST} | {"QQQ", "SPY"}
    M = load_markets(say, C, need_A, need_B)
    store = M["store"]
    cs = fz.collision_summary(C, M["last_seen"])

    def rec_ok(b, floor):
        return fz.rec_drop_reason(b, M, era_of(b.E), floor) is None

    def min_ok(b):
        return store.state(b.E, bar_sym(b.E, b.sym_a, b.sym), b).startswith("ok")
    say("\n## §2 — the populations (sets, records by the floor, buy-day minutes from the fetch logs); the guard-5 trades the fits excluded RETURN")
    ck("guard5_returning", f"{len(cs['enter']['excluded'])} of {cs['enter']['n']} / {len(cs['stop']['excluded'])} of {cs['stop']['n']} / "
                           f"{len(cs['exit']['excluded'])} of {cs['exit']['n']}")
    for lab in ("enter", "stop", "exit"):
        say(f"  - returning ({lab.upper()}): " + ", ".join(f"{s} {e}" for s, e in cs[lab]["excluded"]))
    floor_e, floor_s = fz.REC_MIN_BARS_ENTER, fz.REC_MIN_BARS
    ent20 = [b for b in E["fit_dated"] + E["fit_und"] if rec_ok(b, floor_e) and min_ok(b)]
    stop20 = [b for b in I["fit_dated"] + I["fit_und"] if rec_ok(b, floor_s)]
    exit20 = [b for b in I["fit_dated"] if b.has_exit and rec_ok(b, floor_s)]
    ck("run_records", f"{len(ent20)} / {len(stop20)} / {len(exit20)}")
    kept_e = {b.eid for b in cs["enter"]["kept"]}
    kept_b = {b.eid for b in cs["enter_beside"]["kept"]}
    pf_d = [b for b in E["fit_dated"] if b.eid in kept_e and rec_ok(b, floor_e) and min_ok(b)]
    pf_u = [b for b in E["fit_und"] if b.eid in kept_e and rec_ok(b, floor_e) and min_ok(b)]
    pf_fl = [b for b in E["fit_fl"] if b.eid in kept_b and rec_ok(b, floor_e) and min_ok(b)]
    ck("enter_2020", f"{len(E['fit_dated'])} + {len(E['fit_und'])} ({len(E['fit_fl'])}); {len(pf_d) + len(pf_u)} = {len(pf_d)} + {len(pf_u)}; {len(pf_fl)}")
    sc = lambda bs: [b for b in bs if rec_ok(b, floor_e) and min_ok(b)]                     # noqa: E731
    d22 = E["chk22_dated"]
    ck("enter_2122", f"{len(d22)} ({sum(1 for b in d22 if b.flicker)}) + {len(E['chk22_und'])} ({len(E['chk22_fl'])}); {len(sc(E['chk22_und']))} + {len(sc(d22))}; "
                     f"{len(sc(E['chk22_fl']))}")
    ck("enter_untouched", f"{len(E['virgin_nf'])} + {len(E['virgin_fl'])}; {len(sc(E['virgin_nf']))} + {len(sc(E['virgin_fl']))}")
    pd_f = [b for b in E["pre_dated_fit"] if b.eid in kept_b and clocks_ok(b)]
    pu_f = [b for b in E["pre_und_fit"] if b.eid in kept_b and clocks_ok(b)]
    ck("enter_premarket", f"{len(sc(pd_f))} + {len(sc(pu_f))} ({len(E['pre_und_fit'])}); {len(sc([b for b in E['pre_dated_chk'] if clocks_ok(b)]))} + "
                          f"{len(sc([b for b in E['pre_und_chk'] if clocks_ok(b)]))} ({len(E['pre_und_chk'])})")
    say(f"  - this run's ENTER records with minutes (no guard-5 exclusion): 2020 {len(ent20)}; pre-market-flat 2020 dated {len(sc(E['pre_dated_fit']))} / "
        f"undated {len(sc(E['pre_und_fit']))}; flickers 2020 {len(sc(E['fit_fl']))}")
    ck("stop_2020", f"{len(I['fit_dated'])} + {len(I['fit_und'])}")
    say(f"  - STOP / EXIT 2020 records (floor {floor_s}): dated {sum(1 for b in I['fit_dated'] if rec_ok(b, floor_s))}, undated {sum(1 for b in I['fit_und'] if rec_ok(b, floor_s))}; "
        f"the STOP fit printout's {len([b for b in cs['stop']['kept'] if rec_ok(b, floor_s)])} after guard 5")
    ck("se_2122", f"{len(I['chk22_dated'])} ({sum(1 for b in I['chk22_dated'] if rec_ok(b, floor_s))}) + {len(I['chk22_und'])} ({sum(1 for b in I['chk22_und'] if rec_ok(b, floor_s))})")
    ck("stop_untouched", f"{len(I['virgin_und'])} ({sum(1 for b in I['virgin_und'] if rec_ok(b, floor_s))}) + {len(I['virgin_dated'])} ({sum(1 for b in I['virgin_dated'] if rec_ok(b, floor_s))})")
    tsvs = {k: read_tsv(v)[["eid"] + [c for c in ("beside", "scorable", "abstain", "E1_scorable", "fill_src", "cut_why") if c in read_tsv(v).columns]] for k, v in TSV.items()}
    ck("exit_2020", f"{len(I['fit_dated'])}; {int((tsvs['exit_fit_trades']['E1_scorable'] == 'True').sum())}")
    ck("exit_2122", f"{int((tsvs['check_exit_trades']['abstain'] == '').sum())}")
    claim(EXPECT_MIX["exit_2122"][0], "exit_2122b: the 2021-22 undated EXIT scorable (the trivial-exit base; read at --tag, gate viii-c)", "199", "at --tag", note=True)
    vd = I["virgin_dated"]
    vdx = [b for b in vd if b.has_exit]
    vdr = [b for b in vdx if rec_ok(b, floor_s)]
    ck("exit_untouched", f"{len(vd)} / {len(vdx)} / {sum(1 for b in vdx if b.exit_window_len() <= MAX_WINDOW)}; {len(vdr)} / "
                         f"{sum(1 for b in vdr if b.exit_window_len() <= MAX_WINDOW)}; {len(I['virgin_und'])}")
    st_fs = tsvs["stop_fit_trades"]["fill_src"]
    ex_fs = tsvs["exit_fit_trades"]["fill_src"]
    ck("fit_chain_rows", f"{int((st_fs == 'level:L8').sum())} / {int((ex_fs == 'level:L8').sum())} / {int((tsvs['exit_fit_trades']['cut_why'] == 'guard').sum())}")
    f693 = next((b for b in C["buys"] if b.eid == FSLY["eid"]), None)
    ck("fsly", f"{f693.sym} {f693.E} {f693.exit_lo}..{f693.exit_hi} {'dated' if f693.dated else 'undated'}" if f693 else "eid 693 absent")
    say(f"  - FSLY 693 in the STOP / EXIT 2020 undated set: {any(b.eid == FSLY['eid'] for b in I['fit_und'])}; record (floor {floor_s}): "
        f"{rec_ok(f693, floor_s) if f693 else False}")
    # the intraday TSVs' eids against the printout populations (dates and the eid / group columns only)
    say("\n## The intraday TSVs gate (viii) re-reads: their eids against the printout populations (guard 5 applied as the fits had it)")
    has_mb = lambda b: rec_ok(b, floor_e) and min_ok(b)                                   # noqa: E731
    orders = enter_draw_orders(C, cs, has_mb)
    want = {("enter_fit_trades", g): set(e) for g, e in orders["fit"]}
    want.update({("check_enter_trades", g): set(e) for g, e in orders["check"] if g in ("", "flickers", "virgin")})
    for (tname, g), eids in sorted(want.items()):
        t = tsvs[tname]
        got = set(int(x) for x in t.loc[(t["beside"] == g) & (t["scorable"] == "True"), "eid"])
        claim("Every gate (viii) arm runs ONLY on the eids present in the intraday TSV", f"TSV {tname} group '{g or 'deciding'}': its eids = the replayed draw "
              f"population's records with minutes", f"{len(eids)} eids", f"{len(got)} eids" + ("" if got == eids else f" ({len(got ^ eids)} differ)"))
    prev_und = {b.eid for b in S["ent_chk_und"]}
    ck("vii_population", f"{sum(1 for e in orders['check'][0][1] if e in prev_und)}")
    st_pop = {b.eid for b in cs["stop"]["kept"] if rec_ok(b, floor_s)}
    ex_pop = {b.eid for b in cs["exit"]["kept"] if rec_ok(b, floor_s)}
    chk_stop = {b.eid for b in I["virgin_und"] + I["virgin_dated"] + I["chk22_und"] + I["chk22_dated"] if rec_ok(b, floor_s)}
    chk_exit = {b.eid for b in I["chk22_dated"] if rec_ok(b, floor_s)}
    for tname, pop in (("stop_fit_trades", st_pop), ("exit_fit_trades", ex_pop), ("check_stop_trades", chk_stop), ("check_exit_trades", chk_exit)):
        got = set(int(x) for x in tsvs[tname]["eid"])
        claim("Every gate (viii) arm runs ONLY on the eids present in the intraday TSV", f"TSV {tname}: its eids = the printout population's records",
              f"{len(pop)} eids", f"{len(got)} eids" + ("" if got == pop else f" ({len(got ^ pop)} differ)"))
    # the composition line (§4c), clocks alone
    say("\n## §4c — the composition line from the panel clocks (every buy after §2b; what share of his buys the ENTER library CAN speak to)")
    for blk, (n, c) in composition_enter(C, store, mis).items():
        say(f"  - ENTER {blk} ({n} buys): " + " | ".join(f"{k} {v}" for k, v in sorted(c.items())))
    for blk, subs in se_blocks(C).items():
        for sub, bs in subs.items():
            recs = [b for b in bs if rec_ok(b, floor_s)]
            say(f"  - STOP / EXIT {blk} {sub}: {len(bs)} buys, records {len(recs)}; still held {sum(1 for b in recs if not b.has_exit)}; windows > {MAX_WINDOW} sessions "
                f"{sum(1 for b in recs if b.has_exit and b.exit_window_len() > MAX_WINDOW)}; sell window starting on the buy day (control (a) no_room) "
                f"{sum(1 for b in recs if b.has_exit and b.exit_lo == b.E)} (the losers' share is an outcome: read at --tag)")
    # the data gate (§8): the fetch log claims, then every pair this read walks, from the fetch logs ONLY
    say("\n## §8 — the data gate: the intraday fetch list and the logs, then every (session, symbol) pair the tag walks (logs only; no minute file opened)")
    with open(FETCH_LIST) as fh:
        fl = [ln.rstrip("\n").split("|") for ln in fh if ln.strip()]
    Lst = {(t, d): blk for t, d, blk in fl}
    di = store.done.get("INTRA", {})
    on = Counter(v for k, v in di.items() if (k[1], k[0]) in Lst)
    pend_list = [(t, d) for (t, d) in Lst if store.state(d, t).split("/")[0] == "missing"]
    ck("fetch_log", f"{len(Lst)} / {on['ok']} / {on['empty']} / {len(pend_list)}")
    pending, empty = [], []
    cov = defaultdict(Counter)
    for b in all_enter_buys(C):
        if not rec_ok(b, floor_e):
            continue
        tk = bar_sym(b.E, b.sym_a, b.sym)
        s_ = store.state(b.E, tk, b).split("/")[0]
        cov[("ENTER", "buy day")][s_] += 1
        if s_ == "missing":
            pending.append((tk, b.E, "ENTER"))
        elif s_ == "empty":
            empty.append((tk, b.E, "ENTER"))
    for blk, subs in se_blocks(C).items():
        for sub, bs in subs.items():
            for b in bs:
                if not rec_ok(b, floor_s):
                    continue
                r = fz.make_irec(b, M, era_of(b.E), None, None, min_bars=floor_s, want_minutes=False)
                j_to = (r.exit_hi_j + TAIL) if r.exit_hi_j is not None else (r.last_j or 0)
                for j in range(-WARMUP, j_to + 1):
                    d = r.session_date(j)
                    if d is None:
                        break
                    tk = bar_sym(d, b.sym_a, b.sym)
                    s_ = store.state(d, tk, b).split("/")[0]
                    cov[(f"STOP/EXIT {blk}", sub)][s_] += 1
                    if s_ == "missing":
                        pending.append((tk, d, f"SE {blk} {sub}"))
                    elif s_ == "empty":
                        empty.append((tk, d, f"SE {blk} {sub}"))
    for k, c in sorted(cov.items()):
        say(f"  - coverage {k[0]} {k[1]}: " + ", ".join(f"{s} {v:,}" for s, v in sorted(c.items())))
    os.makedirs(DRY_SIDE, exist_ok=True)
    with open(os.path.join(DRY_SIDE, "pending.psv"), "w") as fh:
        for t, d, why in sorted(set(pending), key=lambda x: (x[1], x[0])):
            fh.write(f"{t}|{d}|{why}\n")
    with open(os.path.join(DRY_SIDE, "empty_pairs.psv"), "w") as fh:
        for t, d, why in sorted(set(empty), key=lambda x: (x[1], x[0])):
            fh.write(f"{t}|{d}|{why}\n")
    say(f"  - pending pairs (in no tree's log): {len(set(pending))} -> dryrun_side/pending.psv (expected empty; a missing pair reads no_minutes / UNRESOLVED, never "
        f"skipped); empty at the source: {len(set(empty))} pairs by set: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(w for _t, _d, w in set(empty)).items()))
        + " -> dryrun_side/empty_pairs.psv")
    claim("writes `pending.psv` (expected empty)", "pending pairs on the walked sessions", "0", f"{len(set(pending))}", note=True)
    # the library
    say("\n## §3 — THE LIBRARIES, fixed rules in the fixed order (the constant `LIBRARY`, pinned with the module)")
    for ln in library_lines():
        say(ln)
    say("\n## The readings this module fixes where the registration is silent (the stricter each time; the module docstring R1-R16)")
    for ln in readings_lines():
        say(ln)
    # the pins
    h = fz.store_freeze_body(DOC, FREEZE_BODIES)
    say(f"\n- the body above the marker stored under freeze_bodies/ ({h[:12]}...): the freeze pin `doc_body_freeze` will name it")
    p = mix_pins(include_outputs=False)            # the inputs only: this printout's own sha and the ledger come from --print-pins (reproducible)
    say("\n## Pins (sha256) — the inputs; --print-pins adds the dry run and the ledger; every value goes under the doc's freeze marker line before --tag")
    for k, v in p.items():
        say(f"- {k}: {v}")
    miss = fz.freeze_missing(DOC, p)
    say(f"- freeze record: {'every pin above is written under the freeze marker line' if not miss else 'NOT YET under the freeze marker line: ' + str(len(miss)) + ' pins'}")
    say(f"\n## RESULT: {claim.n} claims, {claim.n - len(claim.bad)} OK, {len(claim.bad)} MISMATCH; {len(claim.notes)} notes")
    for ln, lab, d, m in claim.bad:
        say(f"  MISMATCH [L{ln}] {lab}: doc {fz.fmt_claim(d)} vs mine {fz.fmt_claim(m)}")
    if claim.bad:
        say("STOPPED: the dry run does not reproduce the registration (amend the doc or the derivation before the freeze)")
        return 3
    say(f"\nDRY RUN COMPLETE: every count reproduced; no minute file opened ({sum(store.reads.values())} reads), no bar after a buy day read, no rule fired, "
        f"no outcome computed; pending pairs {len(set(pending))}.")
    return 0


LABELS = {
    "guard5_returning": "guard (5) fit exclusions that RETURN here: ENTER / STOP / EXIT",
    "run_records": "this run's records: ENTER 2020 with minutes / STOP 2020 / EXIT 2020 dated",
    "enter_2020": "ENTER 2020: windows dated + undated nf (undated flickers); the printout's scorable deciding = dated + undated; flickers scorable",
    "enter_2122": "ENTER 2021-22: dated (flickers) + undated nf (undated flickers); scorable undated nf + dated; flickers scorable",
    "enter_untouched": "ENTER untouched: non-flicker + flicker windows; scorable",
    "enter_premarket": "ENTER beside, pre-market-flat scored: 2020 dated + undated (undated population); 2021-22 dated + undated (undated population)",
    "stop_2020": "STOP 2020: dated + undated",
    "se_2122": "STOP / EXIT 2021-22: dated (records) + undated (records)",
    "stop_untouched": "STOP untouched: undated (records) + dated (records)",
    "exit_2020": "EXIT 2020 dated: n; the intraday EXIT fit's scorable rows (exit_fit_trades.tsv E1_scorable)",
    "exit_2122": "EXIT 2021-22 dated: the armed rows of check_exit_trades.tsv (abstain empty)",
    "exit_untouched": "EXIT untouched dated: n / with exits / windows <= 20; records with exits / windows <= 20; undated n",
    "fit_chain_rows": "the 2020 fit-chain rows of the TSVs: stop rows fill_src level:L8 / exit rows level:L8 / exit walks bounded by the guard (cut_why guard)",
    "fetch_log": "the intraday fetch list / its log ok / empty / pending",
    "vii_population": "the previous draw population's undated 2021-22 records with minutes (gate vii's base)",
    "fsly": "the FSLY known answer: eid 693",
}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the known-answer gates (§9) — each STOPS the run before any new number; failing rows land in rule_mix/
# ═════════════════════════════════════════════════════════════════════════════════════════════
def gate_i(say, recs: list, store, sessions_of, label: str) -> dict:
    """(i) the minute-built session bars vs the daily export, two arms — the frozen pure row builder and verdict; the wrapper writes here."""
    rows = fz.ohlc_pair_rows(recs, store, sessions_of)
    v = fz.gate_ohlc_verdict(rows)
    say(f"- gate (i) {label}: {v['n']} (ticker, session) pairs; high AND low within {pct(fz.GATE_HL_TOL)}: {v['hl_ok']} = {pct(v['hl_share'])} (bar {pct(fz.GATE_HL_SHARE)}); "
        f"open AND close within {pct(fz.GATE_OC_TOL)}: {v['oc_ok']} = {pct(v['oc_share'])} (bar {pct(fz.GATE_OC_SHARE)})")
    bad = v["hl_fail"] + [x for x in v["oc_fail"] if x not in v["hl_fail"]]
    if bad:
        say(f"    rows outside a band -> {write_out(f'gate_i_pairs_{label}.tsv', bad)}")
    if not v["ok"]:
        raise GuardStop(f"gate (i) {label}: high/low {pct(v['hl_share'])}, open/close {pct(v['oc_share'])} of {v['n']} pairs")
    return v


def gate_i_clock(say, recs: list, label: str) -> dict:
    """(i) the clock arm (outcome-free): the share of buy-day sessions whose minutes hold a bar at minute 0 (09:30) must be >= GATE_CLOCK_SHARE.
    A one-minute-late stamp empties minute 0 on every session (the minute files hold 0..389 only), which the open / close arm passes with
    almost no margin. Expected on correct data from the printouts: `no_bar_0930` on 3 of the 400 scored ENTER windows (01_intra_enter_fit.txt
    l.62, 01_intra_check.txt l.44, l.56) = 99.25%."""
    n = sum(1 for r in recs if r.mb is not None and len(r.mb))
    k = sum(1 for r in recs if r.mb is not None and len(r.mb) and bool((r.mb.minute == 0).any()))
    sh = share(k, n)
    say(f"- gate (i) clock arm {label}: buy-day sessions with a bar at minute 0 (09:30): {k} of {n} = {pct(sh)} (bar {pct(GATE_CLOCK_SHARE)})")
    if n and sh < GATE_CLOCK_SHARE:
        raise GuardStop(f"gate (i) clock arm {label}: a bar at minute 0 on {pct(sh)} of {n} buy days (bar {pct(GATE_CLOCK_SHARE)}): a clock shift")
    return dict(n=n, k=k)


def enter_gate_rows(ER: dict, scored: dict) -> list:
    """Gate (ii)'s input: the frozen `enter_row` of every scored ENTER window (the raw levels and the builder's first 60-minute bar)."""
    return [dict(fz.enter_row(ER[k[1]], v["res"])) for k, v in scored.items()]


def gate_ii(say, rows: list, label: str) -> None:
    """(ii) raw L7 <= L1 <= L8 <= L6 on every window; the 60-minute builder's first bar = L8_raw on every window; equal to L6 on > 90% of the
    windows with both = the [0,59] first-bar bug (the frozen gate's reading, re-typed so its rows land here)."""
    bad, both, lt, builder_bad = [], 0, 0, []
    for rw in rows:
        L7, L1, L8, L6, B0 = rw.get("L7_raw"), rw.get("L1_raw"), rw.get("L8_raw"), rw.get("L6_raw"), rw.get("H60_0_high")
        chain = [fnum(x) for x in (L7, L1, L8, L6) if fz._isnum(x)]
        if any(chain[i] > chain[i + 1] + 1e-9 for i in range(len(chain) - 1)):
            bad.append(rw)
        if fz._isnum(L8) and fz._isnum(B0) and abs(fnum(L8) - fnum(B0)) > 1e-9:
            builder_bad.append(rw)
        if fz._isnum(B0) and fz._isnum(L6):
            both += 1
            lt += int(fnum(B0) < fnum(L6) - 1e-9)
    say(f"- gate (ii) {label}: raw L7 <= L1 <= L8 <= L6 on {len(rows) - len(bad)} of {len(rows)}; the builder's first bar = L8_raw on {len(rows) - len(builder_bad)} of {len(rows)}; "
        f"builder first-bar high < L6 on {lt} of {both}")
    if bad or builder_bad:
        p = write_out(f"gate_ii_failures_{label}.tsv", bad + builder_bad)
        raise GuardStop(f"gate (ii) {label}: {len(bad)} order failures, {len(builder_bad)} builder failures; rows -> {p}")
    if both and (both - lt) / both > fz.GATE_L8_EQ_L6_SHARE:
        raise GuardStop(f"gate (ii) {label}: the builder's first-bar high equals L6 on {both - lt} of {both} windows: the [0,59] first-bar bug")


def gate_iii(say, recs: list, store, label: str) -> dict:
    """(iii) a daily close below a level beyond the auction band implies the last 60-minute bar closes below it on >= 98% of such days (the
    frozen gate's reading re-typed; S4 among the levels)."""
    bad, n_beyond, n_band, n_band_not_h = [], 0, 0, 0
    levels = fz.STOP_LEVELS + fz.STOP_CONTROLS + ("S4",)
    for r in recs:
        J = r.exit_hi_j if r.exit_hi_j is not None else r.last_j
        if J is None:
            continue
        smas = fz.smas_for(r.bars)
        for j in range(0, J + 1):
            k = r.bar_at(j)
            if k is None:
                break
            bars = (fz.h60_bars(r.mb, r.b.E) if r.mb is not None else None) if j == 0 else r.h60(store, j)
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
                if dc < L * (1.0 - fz.AUCTION_BAND):
                    n_beyond += 1
                    if not last.c < L:
                        bad.append(dict(eid=r.b.eid, sym=r.b.sym, session=r.session_date(j), j=j, level=Lname, L=L, daily_close=dc, last_bar_close=last.c))
                else:
                    n_band += 1
                    n_band_not_h += int(not last.c < L)
    sh = (n_beyond - len(bad)) / n_beyond if n_beyond else math.nan
    say(f"- gate (iii) {label}: C days beyond the band {n_beyond}; H days among them {n_beyond - len(bad)} = {pct(sh)} (bar {pct(fz.GATE_III_SHARE)}); inside the band {n_band}, "
        f"not H {n_band_not_h} (counted, never failing)")
    if bad:
        say(f"    beyond-band C days that are not H days -> {write_out(f'gate_iii_failures_{label}.tsv', bad)}")
    if n_beyond and sh < fz.GATE_III_SHARE:
        raise GuardStop(f"gate (iii) {label}: {pct(sh)} of {n_beyond}")
    return dict(n_beyond=n_beyond, bad=len(bad))


def g8_mix(say, recs: list, label: str) -> None:
    """Guard (4) G8 before any number: the trade list per era through trade_impact.py (era A must read 0 / 0); the files land in rule_mix/."""
    os.makedirs(OUT_DIR, exist_ok=True)
    say(f"\n## G8 — {label}: this read's own trade list through trade_impact.py (before any number)")
    for era in ("A", "B"):
        rows = [("mix", r.b.ticker, r.b.E, r.exit_hi_j if r.exit_hi_j is not None else 0, 0.0) for r in recs if r.era == era]
        if not rows:
            say(f"- era {era}: no trade; G8 not run")
            continue
        path, txt = os.path.join(OUT_DIR, f"{label}_g8_{era}.tsv"), os.path.join(OUT_DIR, f"{label}_g8_{era}_impact.txt")
        rp.write_g8_file(path, rows)
        cmd = [sys.executable, TRADE_IMPACT, "--flags", G8_FILES[f"flags_{era}"], "--export", G8_FILES[f"export_{era}"], "--trades", path,
               "--label", era, "--kind", "r1", "--cell", "mix", "--cutoff", CUT_B]
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


def _legs_j(legs: str, kinds: tuple) -> "int | None":
    """The session of the first leg of `kinds` in a frozen `E*_legs` string ('e1_half@3;dclose@5'), else None."""
    for part in (legs or "").split(";"):
        if "@" in part:
            k, j = part.rsplit("@", 1)
            if k in kinds:
                return int(j)
    return None


def row_copy_stop(r, row: dict):
    """A copy of the record under the TSV row's OWN fill, fill minute and fill source (the frozen stop levels re-built on it)."""
    r2 = dataclasses.replace(r)
    r2.fill, r2.fill_minute, r2.fill_src = fnum(row["fill"]), _ival(row["fill_minute"]), row["fill_src"]
    r2.stop_levels = fz.stop_levels_intra(r2)
    return r2


def row_copy_exit(r, row: dict):
    """A copy under the TSV row's OWN fill, fill minute, fill source and chain stop (T; the day-0 walk on that stop)."""
    r2 = row_copy_stop(r, row)
    r2.stop, r2.stop_src = fnum(row["stop"]), row["stop_src"]
    r2.stop_lvl, r2.stop_variant = r2.stop, "T"
    r2.day0 = rev.day0_for(r2, r2.fill_minute, r2.stop)
    return r2


def _cut_why(row: dict) -> str:
    """The TSV row's own `cut_why` ('' for an empty / nan / None cell)."""
    v = str(row.get("cut_why", "") if row is not None else "").strip()
    return "" if v in ("", "nan", "None") else v


def prep_with_tail(r2, M: dict, store, J_tail: "int | None", row: "dict | None" = None) -> tuple:
    """The frozen exit_prepare on the copy; the row's own J_tail when it differs (the walk bounded where the fit had it). -> (prep, differs).
    The bounded walk is labelled by the ROW's own cut reason (the fit's `why` / `bh`), never by this run's unbounded walk: a row the fit's guard
    bounded books `cut_at_guard@J` (the frozen `tail_kind_for` with why = 'guard'), so gate (viii-a) compares like with like."""
    prep = fz.exit_prepare(r2, M, store)
    if J_tail is None or J_tail == prep["J_tail"]:
        return prep, False
    seq = fz.bar_sequence(r2, store, -WARMUP, J_tail)
    armed = fz.armed_index(seq, r2.fill_minute)
    thin = armed is None or fz.ema_is_thin(armed)
    why = _cut_why(row)
    bh = J_tail if why == "guard" else prep["bh"]
    return dict(prep, J_tail=J_tail, seq=seq, armed=armed, thin=thin, residual=fz.seed_residual(armed) if armed is not None else math.nan,
                abstain=("no_armed_bar" if armed is None else ("ema_thin" if thin else "")), why=why, bh=bh,
                tail_kind=fz.tail_kind_for(r2, J_tail, why, bh)), True


def gate_viii_enter(say, scored: dict, tsv_name: str, stream: str, known: "tuple | None", deciding: set) -> None:
    """(viii) ENTER row for row on the TSV's eids: every level's cross / feasible / verdict / shifted share, the control columns; then the
    standalone shares re-read at one decimal on the deciding rows."""
    t = read_tsv(TSV[tsv_name])
    bad, n = [], 0
    for row in t.to_dict("records"):
        if not _bval(row.get("scorable")):
            continue
        key = (stream, int(row["eid"]))
        if key not in scored:
            bad.append(dict(eid=row["eid"], field="record", mine="absent", tsv="scored"))
            continue
        res = scored[key]["res"]
        n += 1
        for lv in fz.ALL_LEVELS:
            mine_c = res[lv]["cross"]
            if mine_c != _ival(row[f"{lv}_cross"]):
                bad.append(dict(eid=row["eid"], field=f"{lv}_cross", mine=mine_c, tsv=row[f"{lv}_cross"]))
            if bool(res[lv]["feasible"]) != _bval(row[f"{lv}_feasible"]):
                bad.append(dict(eid=row["eid"], field=f"{lv}_feasible", mine=res[lv]["feasible"], tsv=row[f"{lv}_feasible"]))
            if str(res[lv]["verdict"]) != row[f"{lv}_verdict"]:
                bad.append(dict(eid=row["eid"], field=f"{lv}_verdict", mine=res[lv]["verdict"], tsv=row[f"{lv}_verdict"]))
            sf = res["shift"][lv]["feasible_share"]
            tv = _fval(row.get(f"{lv}_shift_feasible"))
            if not ((np.isnan(sf) and np.isnan(tv)) or abs(fnum(sf) - tv) < 1e-9):
                bad.append(dict(eid=row["eid"], field=f"{lv}_shift_feasible", mine=sf, tsv=row.get(f"{lv}_shift_feasible")))
        for fld, mine in (("control_feasible", res["control"]["feasible_share"]), ("control_hit", res["control"]["hit_share"]),
                          ("union_shift_feasible", res["union"].get("shift_feasible"))):
            if abs(fnum(mine) - _fval(row[fld])) > 1e-9:
                bad.append(dict(eid=row["eid"], field=fld, mine=mine, tsv=row[fld]))
        if bool(res["union"]["feasible"]) != _bval(row["union_feasible"]):
            bad.append(dict(eid=row["eid"], field="union_feasible", mine=res["union"]["feasible"], tsv=row["union_feasible"]))
    say(f"- gate (viii) ENTER {tsv_name}: {n} scorable rows re-read cell for cell (L1-L9 cross / feasible / verdict / shifted share; control_feasible, control_hit, "
        f"union_feasible, union_shift_feasible): {len(bad)} differences")
    if bad:
        p = write_out(f"gate_viii_enter_{tsv_name}.tsv", bad)
        raise GuardStop(f"gate (viii) ENTER {tsv_name}: {len(bad)} cells differ; rows -> {p}")
    if known is not None:
        shares, n_known = known
        dec = [scored[(stream, e)]["res"] for e in sorted(deciding) if (stream, e) in scored]
        mine = {lv: share(sum(1 for r_ in dec if r_[lv]["feasible"]), len(dec)) for lv in shares}
        off = [f"{lv} {pct(mine[lv])} vs {pct(v)}" for lv, v in shares.items() if pct(mine[lv]) != pct(v)]
        say(f"- gate (viii) ENTER {tsv_name}: the standalone shares on the {len(dec)} deciding TSV rows: " + ", ".join(f"{lv} {pct(mine[lv])}" for lv in shares)
            + f" (printed: on {n_known})")
        if len(dec) != n_known or off:
            raise GuardStop(f"gate (viii) ENTER {tsv_name}: the standalone shares do not re-read the printout ({len(dec)} vs {n_known}; {'; '.join(off)})")


def gate_viii_stop(say, recs_by_eid: dict, sight, store, tsv_name: str) -> list:
    """(viii) STOP row for row: every cell's any / certain / unresolved / first_j / event_m (S1 S3 S9 S10 S8 SMA50 x T C H) and the level
    at the buy day, each row re-run under its OWN fill, fill minute and fill source."""
    t = read_tsv(TSV[tsv_name])
    bad, n = [], 0
    for row in t.to_dict("records"):
        eid = int(row["eid"])
        r = recs_by_eid.get(eid)
        if r is None:
            bad.append(dict(eid=eid, cell="record", mine="absent", tsv="row"))
            continue
        r2 = row_copy_stop(r, row)
        smas = fz.smas_for(r2.bars)
        n += 1
        for Lname in fz.STOP_LEVELS + fz.STOP_CONTROLS:
            L0 = rev.level_at(r2, r2.stop_levels[Lname], 0, smas)
            tv = _fval(row[f"{Lname}_level0"])
            if not ((np.isnan(L0) and np.isnan(tv)) or abs(L0 - tv) <= 1e-6 * max(1.0, abs(L0))):
                bad.append(dict(eid=eid, cell=f"{Lname}_level0", mine=L0, tsv=row[f"{Lname}_level0"]))
            for V in fz.STOP_VARIANTS:
                h = fz.held_through_intra(r2, Lname, V, smas, sight, store)
                for fld in ("any", "certain", "unresolved"):
                    if bool(h[fld]) != _bval(row[f"{Lname}_{V}_{fld}"]):
                        bad.append(dict(eid=eid, cell=f"{Lname}_{V}_{fld}", mine=h[fld], tsv=row[f"{Lname}_{V}_{fld}"]))
                for fld in ("first_j", "event_m"):
                    if h[fld] != _ival(row[f"{Lname}_{V}_{fld}"]):
                        bad.append(dict(eid=eid, cell=f"{Lname}_{V}_{fld}", mine=h[fld], tsv=row[f"{Lname}_{V}_{fld}"]))
    say(f"- gate (viii) STOP {tsv_name}: {n} rows x 18 cells re-run under each row's own fill (the §6a certainty rule through the frozen function, the S8 / "
        f"SMA50 control cells included): {len(bad)} differences")
    if bad:
        p = write_out(f"gate_viii_stop_{tsv_name}.tsv", bad)
        raise GuardStop(f"gate (viii) STOP {tsv_name}: {len(bad)} cells differ; rows -> {p}")
    return [int(row["eid"]) for row in t.to_dict("records") if str(row["fill_src"]).startswith("level")]


def gate_viii_exit(say, recs_by_eid: dict, M: dict, store, tsv_name: str, known_rates: tuple, known_trivial: tuple) -> dict:
    """(viii-a) the frozen exit_walk_intra re-run WITH each row's own chain stop, fill and J_tail reproduces every E1-E4 last_j / half_j / hit /
    stop_preempt / legs and the printed hit rates; (viii-b) on the rows no stop pre-empted, this module's frame-free first firing of M-1 /
    M-2 / M-7 = the frozen E1 / E4 / E2 leg's booked session; (viii-c) M-8 / M-9 standalone on the frozen trivial-exit base = the printed
    trivial exits (and the frozen trivial_and_list_hits row for row)."""
    t = read_tsv(TSV[tsv_name])
    recs2, preps, rows, bad, tail_diff = [], {}, {}, [], []
    for row in t.to_dict("records"):
        eid = int(row["eid"])
        r = recs_by_eid.get(eid)
        if r is None:
            bad.append(dict(eid=eid, field="record", mine="absent", tsv="row"))
            continue
        r2 = row_copy_exit(r, row)
        prep, d = prep_with_tail(r2, M, store, _ival(row["J_tail"]), row)
        if d:
            tail_diff.append(eid)
        recs2.append(r2)
        preps[eid] = prep
        rows[eid] = row
    rates = fz.hit_rates_for(recs2, M, store, preps)
    for r2 in recs2:
        eid, row = r2.b.eid, rows[r2.b.eid]
        for v in fz.EXIT_VARIANTS:
            per = rates[v][3].get(eid, {})
            for fld in ("scorable", "hit", "stop_preempt"):
                if fld in per and bool(per[fld]) != _bval(row.get(f"{v}_{fld}", "")):
                    bad.append(dict(eid=eid, field=f"{v}_{fld}", mine=per[fld], tsv=row.get(f"{v}_{fld}")))
            for fld in ("last_j", "half_j"):
                if fld in per and per[fld] != _ival(row.get(f"{v}_{fld}")):
                    bad.append(dict(eid=eid, field=f"{v}_{fld}", mine=per[fld], tsv=row.get(f"{v}_{fld}")))
            if "legs" in per and per["legs"] != row.get(f"{v}_legs", ""):
                bad.append(dict(eid=eid, field=f"{v}_legs", mine=per["legs"], tsv=row.get(f"{v}_legs")))
    kr, kn = known_rates
    off = [f"{v} {pct(rates[v][0])} vs {pct(kr[v])}" for v in fz.EXIT_VARIANTS if pct(rates[v][0]) != pct(kr[v]) or rates[v][2] != kn]
    say(f"- gate (viii-a) EXIT {tsv_name}: the frozen walk re-run with each row's own fill, chain stop and J_tail on {len(recs2)} rows: "
        + ", ".join(f"{v} {pct(rates[v][0])} on {rates[v][2]}" for v in fz.EXIT_VARIANTS) + f" (printed {', '.join(f'{v} {pct(kr[v])}' for v in kr)} on {kn}); "
        f"row differences {len(bad)}; rows whose J_tail the fit bounded {len(tail_diff)}")
    if bad or off:
        p = write_out(f"gate_viii_a_{tsv_name}.tsv", bad) if bad else "-"
        raise GuardStop(f"gate (viii-a) EXIT {tsv_name}: {len(bad)} row differences ({p}); rates {'; '.join(off) or 'ok'}")
    # (viii-b)
    b_bad, b_n, moved = [], Counter(), Counter()
    pre_rows, pre_fired = Counter(), Counter()                   # §2b's NEW cell: the no-stop first firing on the rows the frozen walk stopped first
    for r2 in recs2:
        eid, row, prep = r2.b.eid, rows[r2.b.eid], preps[r2.b.eid]
        if prep["abstain"]:
            continue
        ctx = make_ctx(r2, prep, store)
        mine = {"M-1": fire_m1(r2, prep, store, ctx), "M-2": fire_m2(r2, prep, store, ctx), "M-7": fire_m7(r2, prep, store, ctx)}
        for code, v, kinds in (("M-1", "E1", ("e1",)), ("M-2", "E4", ("touch",)), ("M-7", "E2", ("dclose", "dclose_all"))):
            if _bval(row.get(f"{v}_stop_preempt")):
                pre_rows[code] += 1
                pre_fired[code] += int(mine[code].jb is not None)
                continue
            b_n[code] += 1
            want = _legs_j(row.get(f"{v}_legs", ""), kinds)
            got = mine[code].raw_jb
            if got != want:
                b_bad.append(dict(eid=eid, rule=code, mine=got, tsv=want, legs=row.get(f"{v}_legs")))
            if mine[code].jb != got:
                moved[code] += 1
    say(f"- gate (viii-b) EXIT {tsv_name}: no-stop first firings (frame-free, R5) vs the frozen leg on the rows no stop pre-empted: "
        + ", ".join(f"{c} {b_n[c] - sum(1 for x in b_bad if x['rule'] == c)} of {b_n[c]}" for c in ("M-1", "M-2", "M-7"))
        + f"; rows the buy-day frame rule moves in the tag (beside): " + ", ".join(f"{c} {moved[c]}" for c in ("M-1", "M-2", "M-7")))
    if b_bad:
        p = write_out(f"gate_viii_b_{tsv_name}.tsv", b_bad)
        raise GuardStop(f"gate (viii-b) EXIT {tsv_name}: {len(b_bad)} first firings differ from the frozen legs; rows -> {p}")
    gate_viii_c(say, recs2, preps, store, known_trivial, tsv_name)
    return dict(n=len(recs2), tail_diff=tail_diff, fill_level=[e for e in rows if rows[e]["fill_src"].startswith("level")],
                guard_bounded=[e for e in rows if rows[e].get("cut_why") == "guard"], preempt={c: (pre_rows[c], pre_fired[c]) for c in ("M-1", "M-2", "M-7")})


def gate_viii_c(say, recs: list, preps: dict, store, known: tuple, label: str) -> None:
    """(viii-c) M-8 and M-9 standalone (own-session convention) on the frozen trivial-exit base re-read the printed trivial exits; the frozen
    trivial_and_list_hits gives the same shares on the same rows."""
    fr = fz.trivial_and_list_hits(recs, preps, None)
    n, h8, h9 = 0, 0, 0
    for r in recs:
        if r.exit_hi_j is None or fz.exit_window_sessions(r) > MAX_WINDOW:
            continue
        prep = preps.get(r.b.eid)
        if prep is None or prep["abstain"] or prep["J_tail"] < r.exit_hi_j:
            continue
        if rev.exit_features(r, r.exit_hi_j, fz.smas_for(r.bars)) is None:
            continue
        ctx = make_ctx(r, prep, store)
        f8 = _daily_first(r, ctx, 1, lambda j, k, r=r: r.bar_at(j - 1) is not None and fnum(r.bars.c[k]) < fnum(r.bars.c[r.bar_at(j - 1)]))
        f9 = _fixed_session(r, ctx, SESSION_3)
        n += 1
        h8 += int(f8.jb is not None and r.exit_lo_j <= f8.jb <= r.exit_hi_j)
        h9 += int(f9.jb is not None and r.exit_lo_j <= f9.jb <= r.exit_hi_j)
    k8, k9, kn = known
    m8, m9 = share(h8, n), share(h9, n)
    say(f"- gate (viii-c) EXIT {label}: M-8 {pct(m8)} / M-9 {pct(m9)} on {n} (the frozen trivial exits {pct(fr.get('first_red_close', math.nan))} / "
        f"{pct(fr.get('close_of_session_3', math.nan))} on {fr['n']}; printed {pct(k8)} / {pct(k9)} on {kn})")
    if n != kn or fr["n"] != kn or pct(m8) != pct(k8) or pct(m9) != pct(k9) or pct(m8) != pct(fr.get("first_red_close")) or pct(m9) != pct(fr.get("close_of_session_3")):
        raise GuardStop(f"gate (viii-c) EXIT {label}: M-8 / M-9 {pct(m8)} / {pct(m9)} on {n} do not re-read {pct(k8)} / {pct(k9)} on {kn}")


def gate_ix(say, se: dict, store) -> None:
    """(ix) FSLY 693 as far as his words and the gate-(vi) printout establish it: M-1 not EXPLAINS and not NEITHER, booked on or before
    2020-07-10's offset (R13); M-2 and M-2s not NEITHER, each firing on or before 2020-07-13's offset. The TAG is not pinned."""
    t = se.get(FSLY["eid"])
    if t is not None and t.get("status"):
        raise GuardStop(f"gate (ix): eid {FSLY['eid']} is not scorable here ({t['status']})")
    if t is None:
        raise GuardStop(f"gate (ix): eid {FSLY['eid']} is not among this run's STOP / EXIT records")
    r = t["rec"]
    if r.b.sym != FSLY["sym"] or r.b.E != FSLY["E"] or r.b.exit_lo != FSLY["exit_lo"] or r.b.exit_hi != FSLY["exit_hi"]:
        raise GuardStop(f"gate (ix): eid {FSLY['eid']} is {r.b.sym} {r.b.E} {r.b.exit_lo}..{r.b.exit_hi}, not his FSLY trade")
    j10, j13 = r.off(FSLY["m1_by"]), r.off(FSLY["touch_by"])
    f = t["exit_fires"]
    b = t["exit_real"]
    say(f"- gate (ix) FSLY 693: M-1 {b['M-1']} (event +{f['M-1'].je} {min_to_hhmm(f['M-1'].m) if f['M-1'].m is not None and f['M-1'].m < CLOSE_M else '-'}, booked +{f['M-1'].jb}; "
        f"2020-07-10 = +{j10}); M-2 {b['M-2']} (+{f['M-2'].jb}); M-2s {b['M-2s']} (+{f['M-2s'].jb}); 2020-07-13 = +{j13}; the tag {t['exit_tag']} (not pinned)")
    ok = (b["M-1"] not in (EX, NE) and f["M-1"].jb is not None and f["M-1"].jb <= j10
          and b["M-2"] != NE and f["M-2"].jb is not None and f["M-2"].jb <= j13
          and b["M-2s"] != NE and f["M-2s"].jb is not None and f["M-2s"].jb <= j13)
    if not ok:
        raise GuardStop("gate (ix): his FSLY words are not reproduced by the tagger (M-1 MISS-EARLY / UNRESOLVED by 07-10; M-2, M-2s fired by 07-13)")


def gate_x(say, se: dict, ent: dict) -> None:
    """(x) the identity gate: the random-window machinery placed at s = exit_lo reproduces every real bucket for every rule and trade (STOP /
    EXIT); the shared-window and per-level shifted machinery placed at the real window reproduce every real ENTER feasible flag."""
    bad, n = [], 0
    for eid, t in se.items():
        r = t["rec"]
        if not t.get("tagged"):
            continue
        w = fz.exit_window_sessions(r)
        for dec in ("STOP", "EXIT"):
            fires, real = t[f"{dec.lower()}_fires"], t[f"{dec.lower()}_real"]
            for code in LIB_CODES[dec]:
                n += 1
                got = BUCKETS[int(bucket_vec(fires[code], np.array([r.exit_lo_j]), w)[0])]
                if got != real[code]:
                    bad.append(dict(eid=eid, decision=dec, rule=code, real=real[code], placed=got))
    m, ms = 0, 0
    for key, e in ent.items():
        for lv in LIB_CODES["ENTER"]:
            m += 1
            x, _me = window_feasible(e["crosses"][lv], fz.LEVEL_EXISTS.get(lv, 0), np.array([e["flat_m"]]), e["width"])
            if bool(x[0]) != (e["real"][lv] == EX):
                bad.append(dict(eid=key[1], decision="ENTER", rule=lv, real=e["real"][lv], placed=bool(x[0])))
            # the per-level shifted arm: the frozen shifted_control's OWN placements re-read by this module's window predicate
            s_ = e["res"]["shift"][lv]
            if s_["no_room"]:
                continue
            st = np.asarray(s_["starts"], dtype=np.int64)
            ms += len(st)
            xs, _ms = window_feasible(e["crosses"][lv], fz.LEVEL_EXISTS.get(lv, 0), st, e["width"])
            fr = np.asarray(s_["feas"], dtype=bool)
            if len(st) != len(fr) or not np.array_equal(xs, fr):
                bad.append(dict(eid=key[1], decision="ENTER-shift", rule=lv, real=int(fr.sum()), placed=int(xs.sum())))
    say(f"- gate (x) identity: {n} STOP / EXIT (trade, rule) buckets, {m} ENTER (window, level) flags and {ms} per-level shifted placements re-read "
        f"through the control machinery placed at the real (or the frozen shifted) window: {len(bad)} differences")
    if bad:
        p = write_out("gate_x_failures.tsv", bad)
        raise GuardStop(f"gate (x): {len(bad)} differences; rows -> {p}")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the tag: records, fires, buckets, controls
# ═════════════════════════════════════════════════════════════════════════════════════════════
def se_status(r, prep: dict) -> str:
    """§4b's ONE denominator for STOP / EXIT (before the room test): '' = scorable, else the reason it is out."""
    if r.exit_hi_j is None:
        return "still_held"
    if fz.exit_window_sessions(r) > MAX_WINDOW:
        return "window_gt_20"
    if prep["J_tail"] < r.exit_hi_j:
        return "cut_before_window"
    return ""


def tag_se(r, M: dict, store, sight) -> dict:
    """Every STOP cell and EXIT rule on one record (registered fill and stop): first firings, real buckets, the two window controls, the
    random-level control's draws (per-rule floor and the k-level union), the sign at exit_hi / exit_lo."""
    prep = fz.exit_prepare(r, M, store)
    out = dict(rec=r, prep=prep, status=se_status(r, prep))
    if out["status"]:
        return out
    smas = fz.smas_for(r.bars)
    lo, hi, J_tail = r.exit_lo_j, r.exit_hi_j, int(prep["J_tail"])
    ctx = make_ctx(r, prep, store)
    out["room"] = lo + 1 >= MIN_PLACEMENTS
    kc_hi, kc_lo = r.bar_at(hi), r.bar_at(lo)
    out["loser"] = fnum(r.bars.c[kc_hi]) < fnum(r.fill)
    out["loser_lo"] = fnum(r.bars.c[kc_lo]) < fnum(r.fill)
    out["sign_ambiguous"] = out["loser"] != out["loser_lo"]
    sf = {}
    for code in LIB_CODES["STOP"]:
        sf[code], _h = stop_fire(r, code, smas, sight, store, J_tail, ctx.nomin)
    out["stop_r16"] = {c: sf[c].r16 for c in LIB_CODES["STOP"] if sf[c].r16}
    xf = exit_fires(r, prep, store, ctx, smas)
    for dec, fires in (("stop", sf), ("exit", xf)):
        order = LIB_CODES[dec.upper()]
        real = {c: bucket(fires[c], lo, hi) for c in order}
        times = {c: fire_time(fires[c]) for c in order}
        out[f"{dec}_fires"], out[f"{dec}_real"] = fires, real
        out[f"{dec}_tag"] = greedy_tag(real, order)
        out[f"{dec}_etag"] = earliest_tag(real, times, order)
        out[f"{dec}_contra"] = {c: (real[c] == EX and fires[c].jb == lo and contradicted(r, fires[c], sight)) for c in order}
        for rng_range in ("a", "b"):
            win = random_windows(r, J_tail, rng_range)
            for mode, frames in (("", True), ("_ff", False)):
                out[f"{dec}_win_{rng_range}{mode}"] = dict(win, **(window_summary(fires, order, win["starts"], win["width"], frames) if len(win["starts"]) else {}))
    # the random-level control (shared by STOP and EXIT: one window, one set of draws per trade)
    r.rlevel_lowest = hold_lowest_low(r, store)
    lv1 = random_level_draws(r, RLEVEL_KEY)
    if lv1 is None:
        out["rlevel"] = dict(no_room=True)
    else:
        path = touch_path(r, store)
        codes1 = np.array([CODE_OF[bucket(stop_fire_bare(r, fnum(L), smas, sight, store), lo, hi)] for L in lv1], dtype=np.int8)
        vec1 = touch_buckets_vec(path, lv1, lo, hi)
        if not np.array_equal(codes1, vec1):
            raise GuardStop(f"the random-level touch scan disagrees with the frozen held_through_intra on eid {r.b.eid} ({int((codes1 != vec1).sum())} of {DRAWS} draws)")
        rl = dict(no_room=False, ex=share(int((codes1 == CODE_OF[EX]).sum()), DRAWS), me=share(int((codes1 == CODE_OF[ME]).sum()), DRAWS), codes=codes1, levels=lv1)
        for dec in ("STOP", "EXIT"):
            k = len(LIB_CODES[dec])
            lk = random_level_draws(r, RLEVEL_K_KEY, k)
            X = np.zeros((DRAWS, k), dtype=bool)
            Mx = np.zeros((DRAWS, k), dtype=bool)
            for i in range(k):
                cc = touch_buckets_vec(path, lk[:, i], lo, hi)
                X[:, i], Mx[:, i] = cc == CODE_OF[EX], cc == CODE_OF[ME]
            rl[dec] = matrix_summary(X, Mx, LIB_CODES[dec])
        out["rlevel"] = rl
    return out


def stop_fire_bare(r, price: float, smas: dict, sight, store) -> Fire:
    """A bare price's first touch from the fill (the frozen T reading through held_through_intra; R2 for the close fill)."""
    h = fz.held_through_intra(r, price, "T", smas, sight, store)
    je, m = h["first_j"], h["event_m"]
    if not (r.mb is not None and r.fill_minute is not None) and r.fill_minute != 0 and fnum(r.bars.l[r.e]) <= price:
        return Fire(je=0, jb=0, alt=Fire(je=je, m=m, jb=je))
    bd = bool(h["unresolved"]) and (h["first_j"] == 0 or h["first_j"] is None or h["first_j"] != r.exit_lo_j)
    return Fire(je=je, m=m, jb=je, bd_unres=bd)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the tables (§9's template) and the labels (§6)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def tenths(x: float) -> int:
    """A share as the PRINTED one-decimal percentage in tenths of a point (`pct`'s own string), so a label never contradicts the numbers
    printed beside it (0.40 - 0.35 > 0.05 in float; 40.0% vs 35.0% is exactly 5.0 points)."""
    return int(round(fnum(pct(x)[:-1]) * 10))


def label_of(standalone: float, chance: float, precision: float) -> str:
    """§6's labelling convention (a label, not a verdict), on the printed one-decimal percentages: >= 15 points over the chance share AND
    precision >= 50% -> carries; within 5 points -> chance; more than 5 under -> below chance; the rest -> weak."""
    if not (np.isfinite(standalone) and np.isfinite(chance)):
        return "-"
    d = tenths(standalone) - tenths(chance)
    if d >= tenths(CARRIES_MARGIN) and np.isfinite(precision) and tenths(precision) >= tenths(PRECISION_BAR):
        return "carries"
    if abs(d) <= tenths(CHANCE_BAND):
        return "chance"
    if d < -tenths(CHANCE_BAND):
        return "below chance"
    return "weak"


def mix_label(union: float, chance_union: float) -> bool:
    """§6: the union beats the chance union by >= 15 points, on the printed one-decimal percentages."""
    return bool(np.isfinite(union) and np.isfinite(chance_union) and tenths(union) - tenths(chance_union) >= tenths(MIX_MARGIN))


def _maxf(*xs) -> float:
    v = [x for x in xs if x is not None and np.isfinite(x)]
    return max(v) if v else math.nan


def _mean(xs) -> float:
    xs = [x for x in xs if x is not None and np.isfinite(x)]
    return fnum(np.mean(xs)) if xs else math.nan


def summarize_se(trades: list, dec: str) -> dict:
    """One block's STOP or EXIT summary on its scorable trades (the room test passed): per rule greedy / standalone / precision, the union,
    the discretion remainder, the earliest-firing order, the contradicted count; the controls (a), (b) and the random level, same trades."""
    order = LIB_CODES[dec]
    d = dec.lower()
    n = len(trades)
    out = dict(n=n, rules={})
    for c in order:
        ex = sum(1 for t in trades if t[f"{d}_real"][c] == EX)
        me = sum(1 for t in trades if t[f"{d}_real"][c] == ME)
        out["rules"][c] = dict(ex=ex, me=me, un=sum(1 for t in trades if t[f"{d}_real"][c] == UN), greedy=sum(1 for t in trades if t[f"{d}_tag"] == c),
                               etag=sum(1 for t in trades if t[f"{d}_etag"] == c), precision=share(ex, ex + me),
                               contra=sum(1 for t in trades if t[f"{d}_contra"][c]),
                               a_ex_fa=_mean(t[f"{d}_win_a"]["ex"][c] for t in trades), a_ex_ff=_mean(t[f"{d}_win_a_ff"]["ex"][c] for t in trades),
                               a_greedy=_mean(t[f"{d}_win_a"]["greedy"][c] for t in trades), a_greedy_ff=_mean(t[f"{d}_win_a_ff"]["greedy"][c] for t in trades),
                               b_ex=_mean(t[f"{d}_win_b"]["ex"][c] for t in trades if t[f"{d}_win_b"].get("n")),
                               b_ex_ff=_mean(t[f"{d}_win_b_ff"]["ex"][c] for t in trades if t[f"{d}_win_b_ff"].get("n")),
                               a_me=_mean(t[f"{d}_win_a"]["me"][c] for t in trades), a_me_ff=_mean(t[f"{d}_win_a_ff"]["me"][c] for t in trades))
        x = out["rules"][c]
        x["a_ex"] = _maxf(x["a_ex_fa"], x["a_ex_ff"])                                # R15: the larger of the two modes
    out["union"] = sum(1 for t in trades if t[f"{d}_tag"] != "discretion")
    out["a_union_fa"] = _mean(t[f"{d}_win_a"]["union"] for t in trades)
    out["a_union_ff"] = _mean(t[f"{d}_win_a_ff"]["union"] for t in trades)
    out["a_union"] = _maxf(out["a_union_fa"], out["a_union_ff"])
    out["b_union"] = _mean(t[f"{d}_win_b"]["union"] for t in trades if t[f"{d}_win_b"].get("n"))
    out["b_union_ff"] = _mean(t[f"{d}_win_b_ff"]["union"] for t in trades if t[f"{d}_win_b_ff"].get("n"))
    rl = [t["rlevel"] for t in trades if not t["rlevel"].get("no_room")]
    out["rl_n"], out["rl_ex"], out["rl_me"] = len(rl), _mean(x["ex"] for x in rl), _mean(x["me"] for x in rl)
    out["rl_union"] = _mean(x[dec]["union"] for x in rl)
    out["rl_greedy"] = {c: _mean(x[dec]["greedy"][c] for x in rl) for c in order}
    out["b_cut"] = sum(1 for t in trades if t[f"{d}_win_b"]["cut"])
    return out


NEW_CELL_WHY = {"S4-H": "S4-H is read by no stage", "S4": "S4 on the untouched block", "undated_untouched": "the EXIT library on the untouched undated trades",
                "h60_2020_undated": "the 60-minute and touch rules on the 2020 undated trades", "m10_undated": "the extension / big-up markers on undated trades"}


def new_cells(dec: str, blk: str, sub: "str | None") -> dict:
    """§2b's NEW cells (read by no stage) for one table: {rule code: why}. sub None = the whole block (every sub-block's new cells, the part
    named)."""
    if sub is None:
        out = {}
        for s_ in ("dated", "undated"):
            for c, why in new_cells(dec, blk, s_).items():
                out.setdefault(c, why + ("" if s_ == "dated" or why.startswith("S4") else " (the undated part)"))
        return out
    out = {}
    if dec == "STOP":
        out["S4-H"] = NEW_CELL_WHY["S4-H"]
        if blk == "untouched":
            out.setdefault("S4-T", NEW_CELL_WHY["S4"])
            out.setdefault("S4-C", NEW_CELL_WHY["S4"])
        return out
    if sub == "undated":
        if blk == "untouched":
            return {c: NEW_CELL_WHY["undated_untouched"] for c in LIB_CODES["EXIT"]}
        if blk == "2020":
            out.update({c: NEW_CELL_WHY["h60_2020_undated"] for c in ("M-1", "M-2", "M-2s")})
        out["M-10"] = NEW_CELL_WHY["m10_undated"]
    return out


def se_table_lines(say, summ: dict, dec: str, block: str, header: str, new: "dict | None" = None) -> dict:
    order = LIB_CODES[dec]
    n = summ["n"]
    new = new or {}
    say(f"\ndecision {dec} — block {block} (n scorable {n}; {header})")
    if new:
        by_why = defaultdict(list)
        for c, w in new.items():
            by_why[w].append(c)
        say("  NEW cells (§2b: read by no stage; flagged NEW in the source column): " + "; ".join(f"{w}: {', '.join(cs)}" for w, cs in by_why.items()))
    hdr = ["rule", "source", "greedy share (95%)", "standalone", "chance (a) inside the hold: frames / no frames", "chance: random level",
           "chance (b) hold + tail: frames / no frames", "greedy chance (a) frames / no frames / random level", "precision (floor)", "earliest-order",
           "exit_lo contradicted", "label"]
    rows, labels = [], {}
    src = {r.code: ("his words" if r.tier == 1 else "our reading") + (" NEW" if r.code in new else "") for r in LIBRARY[dec]}
    for c in order:
        x = summ["rules"][c]
        stand = share(x["ex"], n)
        chance = max(v for v in (x["a_ex"], summ["rl_ex"]) if np.isfinite(v)) if any(np.isfinite(v) for v in (x["a_ex"], summ["rl_ex"])) else math.nan
        labels[c] = label_of(stand, chance, x["precision"])
        rows.append([c, src[c], ci_text(x["greedy"], n), f"{pct(stand)} ({x['ex']})", f"{pct(x['a_ex_fa'])} / {pct(x['a_ex_ff'])}", pct(summ["rl_ex"]),
                     f"{pct(x['b_ex'])} / {pct(x['b_ex_ff'])}", f"{pct(x['a_greedy'])} / {pct(x['a_greedy_ff'])} / {pct(summ['rl_greedy'][c])}",
                     f"{pct(x['precision'])} ({x['ex']} / {x['ex'] + x['me']})", pct(share(x["etag"], n)), x["contra"], labels[c]])
    for ln in rp.table(hdr, rows):
        say(ln)
    disc = n - summ["union"]
    chance_u = max(v for v in (summ["a_union"], summ["rl_union"]) if np.isfinite(v)) if any(np.isfinite(v) for v in (summ["a_union"], summ["rl_union"])) else math.nan
    say(f"  discretion {ci_text(disc, n)}")
    say(f"  UNION {ci_text(summ['union'], n)} vs chance union: (a) inside the hold {pct(summ['a_union_fa'])} with frames / {pct(summ['a_union_ff'])} without | "
        f"random level (k = {len(order)}) {pct(summ['rl_union'])} | (b) hold + tail {pct(summ['b_union'])} / {pct(summ['b_union_ff'])} -> the larger of (a) and the "
        f"random level {pct(chance_u)}")
    say(f"  random-level control: {summ['rl_n']} trades with room (a hold whose lowest low is under the fill); per-rule floor EXPLAINS {pct(summ['rl_ex'])}, precision "
        f"{pct(share(summ['rl_ex'], summ['rl_ex'] + summ['rl_me']) if np.isfinite(summ['rl_ex']) else math.nan)}; control (b) paths cut short (a hole / the horizon / "
        f"the data's end) {summ['b_cut']}")
    say("  control (a) precision per rule (frames / no frames): " + ", ".join(
        f"{c} {pct(share(summ['rules'][c]['a_ex_fa'], summ['rules'][c]['a_ex_fa'] + summ['rules'][c]['a_me']))} / "
        f"{pct(share(summ['rules'][c]['a_ex_ff'], summ['rules'][c]['a_ex_ff'] + summ['rules'][c]['a_me_ff']))}" for c in order))
    say("  earliest-firing order: " + ", ".join(f"{c} {pct(share(summ['rules'][c]['etag'], n))}" for c in order) + " (union unchanged by construction)")
    return dict(labels=labels, union=share(summ["union"], n), chance_union=chance_u)


def summarize_enter(items: list) -> dict:
    order = LIB_CODES["ENTER"]
    n = len(items)
    out = dict(n=n, rules={})
    for c in order:
        ex = sum(1 for e in items if e["real"][c] == EX)
        me = sum(1 for e in items if e["real"][c] == ME)
        sh = [e["shift"]["ex_lv"][c] for e in items if e["shift"]["room"][c]]
        out["rules"][c] = dict(ex=ex, me=me, precision=share(ex, ex + me), greedy=sum(1 for e in items if e["tag"] == c),
                               etag=sum(1 for e in items if e["etag"] == c), shift_lv=_mean(sh),
                               shared=_mean(e["shared"]["ex"][c] for e in items if not e["shared"].get("no_room")),
                               shared_greedy=_mean(e["shared"]["greedy"][c] for e in items if not e["shared"].get("no_room")),
                               k_ex=_mean(e["kprice"]["ex"][c] for e in items), k_greedy=_mean(e["kprice"]["greedy"][c] for e in items),
                               shift_greedy=_mean(e["shift"]["greedy"][c] for e in items))
        for nm, key in (("k_prec", "kprice"), ("shared_prec", "shared"), ("shift_prec", "shift")):
            xs = [e[key] for e in items if not e[key].get("no_room")]
            exm, mem = _mean(x["ex"][c] for x in xs), _mean(x["me"][c] for x in xs)
            out["rules"][c][nm] = share(exm, exm + mem) if np.isfinite(exm) and np.isfinite(mem) and (exm + mem) > 0 else math.nan
    out["rprice"] = _mean(e["rprice"]["ex"] for e in items)
    out["rprice_prec"] = share(_mean(e["rprice"]["ex"] for e in items), _mean(e["rprice"]["ex"] + e["rprice"]["me"] for e in items))
    out["union"] = sum(1 for e in items if e["tag"] != "discretion")
    out["k_union"] = _mean(e["kprice"]["union"] for e in items)
    out["shared_union"] = _mean(e["shared"]["union"] for e in items if not e["shared"].get("no_room"))
    out["shift_union"] = _mean(e["shift"]["union"] for e in items)
    out["shared_no_room"] = sum(1 for e in items if e["shared"].get("no_room"))
    return out


def enter_table_lines(say, summ: dict, block: str, header: str) -> dict:
    order = LIB_CODES["ENTER"]
    n = summ["n"]
    say(f"\ndecision ENTER — block {block} (n scorable {n}; {header})")
    hdr = ["rule", "source", "greedy share (95%)", "standalone", "chance: random-price", "chance: shifted per level / shared window", "chance (greedy): k-price / shared / shifted",
           "precision (floor)", "earliest-order", "label"]
    rows, labels = [], {}
    src = {r.code: ("his words" if r.tier == 1 else "our reading") for r in LIBRARY["ENTER"]}
    for c in order:
        x = summ["rules"][c]
        stand = share(x["ex"], n)
        cands = [v for v in (summ["rprice"], x["shift_lv"], x["shared"]) if np.isfinite(v)]
        chance = max(cands) if cands else math.nan
        labels[c] = label_of(stand, chance, x["precision"])
        rows.append([c, src[c], ci_text(x["greedy"], n), f"{pct(stand)} ({x['ex']})", pct(summ["rprice"]), f"{pct(x['shift_lv'])} / {pct(x['shared'])}",
                     f"{pct(x['k_greedy'])} / {pct(x['shared_greedy'])} / {pct(x['shift_greedy'])}", f"{pct(x['precision'])} ({x['ex']} / {x['ex'] + x['me']})",
                     pct(share(x["etag"], n)), labels[c]])
    for ln in rp.table(hdr, rows):
        say(ln)
    cu = [v for v in (summ["k_union"], summ["shared_union"], summ["shift_union"]) if np.isfinite(v)]
    chance_u = max(cu) if cu else math.nan
    say(f"  discretion {ci_text(n - summ['union'], n)}")
    say(f"  UNION {ci_text(summ['union'], n)} vs chance union: k-price {pct(summ['k_union'])} | shared-window {pct(summ['shared_union'])} | per-level shifted "
        f"{pct(summ['shift_union'])} -> the largest {pct(chance_u)}")
    say(f"  random-price control precision {pct(summ['rprice_prec'])}; shared-window no_room {summ['shared_no_room']}; k-price standalone per rule: "
        + ", ".join(f"{c} {pct(summ['rules'][c]['k_ex'])}" for c in order))
    say("  control precision per rule (k-price / shared window / per-level shifted): " + ", ".join(
        f"{c} {pct(summ['rules'][c]['k_prec'])} / {pct(summ['rules'][c]['shared_prec'])} / {pct(summ['rules'][c]['shift_prec'])}" for c in order))
    say("  earliest-firing order: " + ", ".join(f"{c} {pct(share(summ['rules'][c]['etag'], n))}" for c in order) + " (union unchanged by construction)")
    return dict(labels=labels, union=share(summ["union"], n), chance_union=chance_u)


def summary_labels(say, dec: str, per_block: dict) -> None:
    """A rule is `carries` only when it is `carries` on BOTH 2020 and 2021-22 (each against its own chance line); the union `mix` when it beats
    the chance union by >= 15 points on both — labels that order the next registration's candidates, never a PASS / FAIL (§6)."""
    say(f"\n## {dec} — the summary labels (2020 AND 2021-22; untouched beside)")
    rows = []
    for c in LIB_CODES[dec]:
        labs = [per_block.get(b, {}).get("labels", {}).get(c, "-") for b in BLOCKS]
        rows.append([c] + labs + ["carries" if all(per_block.get(b, {}).get("labels", {}).get(c) == "carries" for b in LABEL_BLOCKS) else "-"])
    for ln in rp.table(["rule"] + list(BLOCKS) + ["summary"], rows):
        say(ln)
    mix = all(mix_label(per_block.get(b, {}).get("union", math.nan), per_block.get(b, {}).get("chance_union", math.nan)) for b in LABEL_BLOCKS)
    say(f"  UNION: " + "; ".join(f"{b} {pct(per_block.get(b, {}).get('union', math.nan))} vs {pct(per_block.get(b, {}).get('chance_union', math.nan))}" for b in BLOCKS)
        + f" -> {'mix' if mix else 'no mix'}")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# --tag
# ═════════════════════════════════════════════════════════════════════════════════════════════
def run_tag(say) -> int:
    bad = tag_lock()
    if bad:
        print("REFUSED (guard 1): " + " | ".join(bad), file=sys.stderr)
        return 2
    msha = sha(CODE["mix_module"])
    frozen_copy = os.path.join(FROZEN_DIR, f"01_mix_frozen_{msha[:12]}.py")
    shutil.copyfile(CODE["mix_module"], frozen_copy)                          # guard (2)
    say("# #705 RULE MIX 01 — TAG (ONE run): the known-answer gates, then ENTER -> STOP -> EXIT on every block, the controls, the tables")
    say(f"# registration: {os.path.relpath(DOC, REPO)}; module {msha[:12]}... copied to {os.path.basename(frozen_copy)}; every pin under the marker; the dry run COMPLETE")
    try:
        rc = tag_stages(say)
    except GuardStop as g:
        say(f"STOPPED: {g}")
        say.write(STOPPED)
        return 3
    except Exception:
        import traceback
        say("STOPPED (crash):\n" + traceback.format_exc())
        say.write(STOPPED)
        return 4
    say.write(P_TAG)
    fz.ledger_append("tag", P_TAG, LEDGER)
    return rc


def build_records(C: dict, M: dict, store, guard) -> tuple:
    """(ENTER records by eid, STOP / EXIT records by eid): one make_irec per buy (one calendar per record); the registered chain on every
    STOP / EXIT record (§4d) and S4 beside the frozen levels."""
    er, drop_e = fz.recs_for(all_enter_buys(C), M, store, guard, min_bars=fz.REC_MIN_BARS_ENTER)
    sr, drop_s = fz.recs_for(all_se_buys(C), M, store, guard)
    cc = fz.apply_chain(sr, None, None, C["mis"])
    for r in sr:
        add_s4(r)
    return {r.b.eid: r for r in er}, {r.b.eid: r for r in sr}, drop_e, drop_s, cc


def tag_stages(say, C: "dict | None" = None, M: "dict | None" = None) -> int:
    check_mix_inputs(say)
    if C is None:
        C = load_core(say)
    assert_populations(say, C)
    if M is None:
        ni = C["S"]["ni"]
        M = load_markets(say, C, {b.sym_a for b in ni if b.has_bars} | {"QQQ", "SPY"},
                         {b.sym for b in ni if b.has_bars and b.E > fz.A_LAST} | {"QQQ", "SPY"})
    store, sight, guard = M["store"], M["sight"], fz.BarGuard(None)
    store.forbid = frozenset()                                    # guard (5): no fit stage, no held-out set — every block read once
    cs = fz.collision_summary(C, M.get("last_seen"))
    eb = enter_blocks(C)
    ER, SR, drop_e, drop_s, cc = build_records(C, M, store, guard)
    say(f"- records: ENTER {len(ER)} (dropped {dict(drop_e)}), STOP / EXIT {len(SR)} (dropped {dict(drop_s)}); the registered chain: "
        + ", ".join(f"{k} {v}" for k, v in sorted(cc.items())))
    fz.preload_sessions(store, list(SR.values()), -WARMUP, lambda r: (r.exit_hi_j + TAIL) if r.exit_hi_j is not None else r.last_j)
    g8_mix(say, list(SR.values()), "mix_tag")
    # ---- gates (i), (ii), (iii)
    say("\n## THE KNOWN-ANSWER GATES (each STOPS the run before any new number)")
    gate_i(say, [r for r in ER.values() if r.mb is not None], store, lambda r: [0], "enter")
    gate_i_clock(say, [r for r in ER.values() if r.mb is not None], "enter")
    gate_i(say, [r for r in SR.values() if r.exit_hi_j is not None], store, lambda r: range(-WARMUP, r.exit_hi_j + TAIL + 1), "stop_exit")
    gate_iii(say, list(SR.values()), store, "stop_exit")
    # ---- ENTER scoring: the replayed stream (gate vii, viii), then every record
    has_mb = lambda b: b.eid in ER and ER[b.eid].mb is not None                       # noqa: E731
    orders = enter_draw_orders(C, cs, has_mb)
    draws = replay_draws(orders)
    scored = {}
    for stream, groups in orders.items():
        for _g, eids in groups:
            for eid in eids:
                scored[(stream, eid)] = enter_one(ER[eid], draws[(stream, eid)], stream)
    returning = []
    for blk, spec in eb.items():
        stream = stream_of_block(blk)
        for b in spec["tagged"] + [x for bs in spec["beside"].values() for x in bs]:
            r = ER.get(b.eid)
            if r is None or r.mb is None or (stream, b.eid) in scored or not clocks_ok(b):
                continue
            u = fz.rng_for(K1_KEY.format(eid=b.eid)).integers(0, 390, size=fz.RANDOM_LEVELS)
            scored[(stream, b.eid)] = enter_one(r, u, stream)
            returning.append((blk, b.sym, b.E))
    say(f"- ENTER: {len(scored)} windows scored ({sum(len(e) for g in orders.values() for _x, e in g)} on the replayed stream; {len(returning)} outside it with "
        f"`{K1_KEY}` draws (R12): " + ", ".join(f"{s} {e} ({b})" for b, s, e in returning) + ")")
    gate_ii(say, enter_gate_rows(ER, scored), "enter")
    gate_vii(say, {k[1]: v["res"] for k, v in scored.items() if k[0] == "check" and k[1] in set(orders["check"][0][1])},
                               {b.eid for b in C["S"]["ent_chk_und"]})
    gate_viii_enter(say, scored, "enter_fit_trades", "fit", KNOWN_ENTER_STANDALONE["fit"], set(orders["fit"][0][1]))
    gate_viii_enter(say, scored, "check_enter_trades", "check", KNOWN_ENTER_STANDALONE["check"], {b.eid for b in C["E"]["chk22_und"] if has_mb(b)})
    # ---- STOP / EXIT: gates (viii) on the TSV rows, then every record tagged
    st_fit = gate_viii_stop(say, SR, sight, store, "stop_fit_trades")
    gate_viii_stop(say, SR, sight, store, "check_stop_trades")
    vfit = gate_viii_exit(say, SR, M, store, "exit_fit_trades", KNOWN_EXIT_RATES["fit"], KNOWN_TRIVIAL["fit"])
    vchk = gate_viii_exit(say, SR, M, store, "check_exit_trades", KNOWN_EXIT_RATES["check"], KNOWN_TRIVIAL["check"])
    und = [r for r in SR.values() if r.b.eid in {b.eid for b in C["I"]["chk22_und"]} and r.exit_hi_j is not None]
    gate_viii_c(say, und, {r.b.eid: fz.exit_prepare(r, M, store) for r in und}, store, KNOWN_TRIVIAL["check_und"], "2021-22 undated (no TSV: the check's records)")
    se = {}
    for eid, r in SR.items():
        se[eid] = tag_se(r, M, store, sight)
        se[eid]["tagged"] = not se[eid]["status"]
    gate_ix(say, se, store)
    for key, e in scored.items():
        e["tag"] = greedy_tag(e["real"], LIB_CODES["ENTER"])
        e["etag"] = earliest_tag(e["real"], e["times"], LIB_CODES["ENTER"])
    gate_x(say, se, scored)
    say(f"- the 2020 fit-chain rows beside (the tag runs under the registered fill; the gates re-ran each with its own): fill level:L8 on stop rows "
        f"{len(st_fit)} (eids {st_fit}); on exit rows {len(vfit['fill_level'])} (eids {vfit['fill_level']}); the exit walks the guard bounded "
        f"{len(vfit['guard_bounded'])} (eids {vfit['guard_bounded']}); check rows bounded {len(vchk['guard_bounded'])}")
    say("- the guard-5 trades the fits excluded RETURN here (every block read once, BarGuard(None)): ENTER " + ", ".join(f"{s_} {e_}" for s_, e_ in cs["enter"]["excluded"])
        + "; STOP " + ", ".join(f"{s_} {e_}" for s_, e_ in cs["stop"]["excluded"]) + "; EXIT " + ", ".join(f"{s_} {e_}" for s_, e_ in cs["exit"]["excluded"]))
    say("\nALL GATES PASSED — the numbers below are new")
    # ---- the tables
    write_tables(say, C, eb, ER, scored, se, store, preempt={"2020 dated (exit_fit_trades.tsv)": vfit["preempt"], "2021-22 dated (check_exit_trades.tsv)": vchk["preempt"]})
    say("\nTAG COMPLETE")
    return 0


def write_tables(say, C: dict, eb: dict, ER: dict, scored: dict, se: dict, store, preempt: "dict | None" = None) -> None:
    """The tables; `preempt` = {TSV label: {rule: (rows the frozen walk's stop pre-empted, of them with a no-stop first firing)}} (§2b's NEW
    cell, printed beside the EXIT table)."""
    bset = se_blocks(C)
    per = {"ENTER": {}, "STOP": {}, "EXIT": {}}
    # ENTER
    say("\n## ENTER (in-session windows; the pre-market-flat windows beside, never summed)")
    rows_e = []
    comp = composition_enter(C, store, C["mis"])
    for blk, spec in eb.items():
        stream = stream_of_block(blk)
        tagged_eids = {b.eid for b in spec["tagged"]}
        items = [scored[(stream, b.eid)] for b in spec["tagged"] if (stream, b.eid) in scored]
        no_min = sum(1 for b in spec["tagged"] if b.eid in ER and ER[b.eid].mb is None)
        nb, cc = comp[blk]
        per["ENTER"][blk] = enter_table_lines(say, summarize_enter(items), blk, f"no record or no_minutes among the tagged windows {len(spec['tagged']) - len(items)} "
                                              f"(no_minutes {no_min}); composition of the {nb} buys: " + " | ".join(f"{k} {v}" for k, v in sorted(cc.items())))
        for sub, bs in spec["sub"].items():
            its = [scored[(stream, b.eid)] for b in bs if (stream, b.eid) in scored]
            if its and len(spec["sub"]) > 1:
                enter_table_lines(say, summarize_enter(its), f"{blk} / {sub} (beside)", "a sub-block, never deciding")
        for lab, bs in spec["beside"].items():
            its = [scored[(stream, b.eid)] for b in bs if (stream, b.eid) in scored]
            if its:
                enter_table_lines(say, summarize_enter(its), f"{blk} / {lab} (beside)", "beside, never summed")
        for b in spec["tagged"] + [x for bs in spec["beside"].values() for x in bs]:
            e = scored.get((stream, b.eid))
            if e is None:
                continue
            row = dict(eid=b.eid, sym=b.sym, E=b.E, block=blk, dated=b.dated, flicker=b.flicker, flat_clock=b.flat_clock, first_clock=b.first_clock,
                       tagged=b.eid in tagged_eids, tag=e["tag"], earliest_tag=e["etag"])
            for c in LIB_CODES["ENTER"]:
                row[f"{c}_bucket"], row[f"{c}_cross"] = e["real"][c], e["res"][c]["cross"]
            row.update(rprice_feasible=e["rprice"]["ex"], kprice_union=e["kprice"]["union"], shared_union=e["shared"].get("union"), shift_union=e["shift"]["union"])
            rows_e.append(row)
    summary_labels(say, "ENTER", per["ENTER"])
    # STOP / EXIT
    rows_s, rows_x, ctl = [], [], []
    for dec in ("STOP", "EXIT"):
        d = dec.lower()
        say(f"\n## {dec} ({'his LOSING exits: the close of exit_hi under the registered fill' if dec == 'STOP' else 'ALL exits; the losers / non-losers split beside'})")
        if dec == "EXIT":
            for lab, pr in (preempt or {}).items():
                say(f"- NEW cell (§2b), beside: on the {lab} rows the frozen walk's stop pre-empted, the no-stop first firing (by J_tail) of "
                    + ", ".join(f"{c} {f_} of {n_}" for c, (n_, f_) in pr.items()) + " (gate viii-b does not gate these: a new number)")
        for blk, subs in bset.items():
            eids = [b.eid for bs in subs.values() for b in bs if b.eid in se]
            ts = [se[e] for e in eids]
            sc = [t for t in ts if t.get("tagged")]
            base = [t for t in sc if t["loser"]] if dec == "STOP" else sc
            roomy = [t for t in base if t["room"]]
            noroom = [t for t in base if not t["room"]]
            comp = Counter(t["status"] or ("scorable" if t["room"] else "no_room in (a)") for t in ts)
            hdr = (f"composition: " + ", ".join(f"{k} {v}" for k, v in sorted(comp.items())) + f"; losers at exit_hi {sum(1 for t in sc if t['loser'])} of {len(sc)} = "
                   f"{pct(share(sum(1 for t in sc if t['loser']), len(sc)))} (at exit_lo {sum(1 for t in sc if t['loser_lo'])}; sign_ambiguous {sum(1 for t in sc if t['sign_ambiguous'])}); "
                   f"no_room trades beside {len(noroom)}")
            per[dec][blk] = se_table_lines(say, summarize_se(roomy, dec), dec, blk, hdr, new_cells(dec, blk, None))
            if dec == "STOP":
                mv = Counter((c, k) for t in base for c, k in t.get("stop_r16", {}).items())
                say(f"  R16 beside: (trade, C cell) pairs among these {len(base)} losers whose buy-day close the clock test moved off the frozen 'certain' "
                    f"(no in-session buy-day frame -> UNRESOLVED; a flat frame after the close -> the scan went on): {sum(mv.values())}"
                    + (" — " + ", ".join(f"{c} {k} {v}" for (c, k), v in sorted(mv.items())) if mv else ""))
            if noroom:
                say(f"  the {len(noroom)} no_room trades' real buckets (beside, out of the same-trades comparison): "
                    + ", ".join(f"{c} E{sum(1 for t in noroom if t[d + '_real'][c] == EX)}/M{sum(1 for t in noroom if t[d + '_real'][c] == ME)}" for c in LIB_CODES[dec]))
            for sub, bs in subs.items():
                st_ = [se[b.eid] for b in bs if b.eid in se and se[b.eid].get("tagged") and se[b.eid]["room"] and (dec == "EXIT" or se[b.eid]["loser"])]
                if st_ and len(subs) > 1:
                    se_table_lines(say, summarize_se(st_, dec), dec, f"{blk} / {sub} (beside)", "a sub-block, never deciding", new_cells(dec, blk, sub))
            if dec == "EXIT":
                for sign, pred in (("losers", lambda t: t["loser"]), ("non-losers", lambda t: not t["loser"])):
                    st_ = [t for t in roomy if pred(t)]
                    if st_:
                        se_table_lines(say, summarize_se(st_, dec), dec, f"{blk} / {sign} (beside)", "the split by sign, beside", new_cells(dec, blk, None))
            for t in ts:
                r = t["rec"]
                row = dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, block=blk, dated=r.b.dated, era=r.era, status=t["status"] or "scorable", room=t.get("room"),
                           loser=t.get("loser"), loser_lo=t.get("loser_lo"), exit_lo_j=r.exit_lo_j, exit_hi_j=r.exit_hi_j, J_tail=t["prep"]["J_tail"],
                           fill=r.fill, fill_minute=r.fill_minute, fill_src=r.fill_src, stop=r.stop)
                if t.get("tagged"):
                    for c in LIB_CODES[dec]:
                        f = t[f"{d}_fires"][c]
                        row[f"{c}_bucket"], row[f"{c}_first_j"], row[f"{c}_booked_j"], row[f"{c}_first_minute"] = t[f"{d}_real"][c], f.je, f.jb, f.m
                    row.update(tag=t[f"{d}_tag"], earliest_tag=t[f"{d}_etag"], ctl_a_union=t[f"{d}_win_a"].get("union"), ctl_b_union=t[f"{d}_win_b"].get("union"),
                               rlevel_ex=t["rlevel"].get("ex"))
                    for rng_range in ("a", "b", "a_ff", "b_ff"):
                        w = t[f"{d}_win_{rng_range}"]
                        if not w.get("n"):
                            continue
                        for i, s in enumerate(w["starts"]):
                            ctl.append(dict(decision=dec, eid=r.b.eid, range=rng_range, start=int(s),
                                            **{c: LETTER[BUCKETS[int(w["codes"][c][i])]] for c in LIB_CODES[dec]}))
                (rows_s if dec == "STOP" else rows_x).append(row)
        summary_labels(say, dec, per[dec])
    for key, e in scored.items():
        sh = e["shared"]
        if sh.get("no_room"):
            continue
        for i, s in enumerate(sh["starts"]):
            ctl.append(dict(decision="ENTER", eid=key[1], range="shared", start=int(s), **{c: ("E" if sh["codes"][i, j] else "-") for j, c in enumerate(LIB_CODES["ENTER"])}))
    for name, rows in (("tags_enter.tsv", rows_e), ("tags_stop.tsv", rows_s), ("tags_exit.tsv", rows_x)):
        p = write_out(name, rows)
        fz.ledger_append("tag", p, LEDGER)
    p = write_out("control_windows.tsv.gz", ctl, compression="gzip")
    fz.ledger_append("tag", p, LEDGER)
    say(f"\n- per-trade files -> {OUT_DIR}/ (tags_enter.tsv, tags_stop.tsv, tags_exit.tsv, control_windows.tsv.gz); the ledger records each")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# --print-pins, --reset (N2), main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def print_pins(say) -> int:
    say("# #705 RULE MIX 01 — pins (sha256): paste every line under the doc's freeze marker line (doc_body_freeze / doc_body = the freeze)")
    p = mix_pins()
    for k, v in p.items():
        say(f"- {k}: {v}")
    miss = fz.freeze_missing(DOC, p)
    say(f"- freeze record: {'complete' if not miss else 'NOT YET under the marker: ' + str(len(miss)) + ' of ' + str(len(p)) + ' pins'}")
    absent = [k for k, v in p.items() if v == "ABSENT"]
    say(f"- absent inputs / outputs (named, not refused): {', '.join(absent) if absent else 'none'}")
    try:
        h = fz.store_freeze_body(DOC, FREEZE_BODIES)
        say(f"- the body above the marker stored under freeze_bodies/ ({h[:12]}...); doc_body_freeze above = "
            f"{'the pinned value under the marker' if fz.pin_under_marker('doc_body_freeze', DOC) else 'the CURRENT body (paste it: this is the freeze)'}")
    except GuardStop as g:
        say(f"- freeze body not stored: {g}")
    say.write(P_PINS)
    return 0


def reset_artifacts() -> list:
    out = [p for p in (STOPPED, LEDGER, P_DRY, P_PINS) if os.path.exists(p)]
    out += sorted(glob.glob(os.path.join(FROZEN_DIR, "01_mix_frozen_*.py")))
    if os.path.isdir(OUT_DIR):
        out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR) if os.path.isfile(os.path.join(OUT_DIR, f)))
    return out


def reset_tag(say, reason: str, root: str = None) -> int:
    """N2 for a STOPPED tag (the fix in the code): every artifact COPIED to tag_events/<event>/ (each copy's sha256 verified, MANIFEST.tsv,
    DISCLOSURE.md, events.tsv appended), and only then removed from its place — never deleted. Then the dry run, --print-pins, the pins and
    the `fit_event_<event>` line pasted under the marker, and --tag (it refuses an undisclosed or altered event)."""
    root = root or TAG_EVENTS
    if not (reason or "").strip():
        print("REFUSED: --reset needs the reason (the gate or bug that stopped the run, and the fix)", file=sys.stderr)
        return 2
    if os.path.exists(P_TAG):
        print(f"REFUSED: the tag COMPLETED ({P_TAG}); it runs once and is never reset", file=sys.stderr)
        return 2
    if not os.path.exists(STOPPED):
        print("REFUSED: no STOPPED file — a reset follows a STOPPED tag only", file=sys.stderr)
        return 2
    arts = reset_artifacts()
    n_prev = len(fz.fit_events(root))
    ev = f"{_dt.datetime.now():%Y%m%dT%H%M%S}_{n_prev + 1:02d}"
    dest = os.path.join(root, ev)
    if os.path.exists(dest):
        print(f"REFUSED: {dest} exists", file=sys.stderr)
        return 2
    rows = []
    for p_ in arts:
        sub = "rule_mix" if os.path.abspath(os.path.dirname(p_)) == os.path.abspath(OUT_DIR) else "module"
        tgt = os.path.join(dest, sub, os.path.basename(p_))
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        if os.path.exists(tgt):
            print(f"REFUSED: two artifacts archive to the same name {tgt}; nothing was removed", file=sys.stderr)
            return 3
        h = sha(p_)
        shutil.copy2(p_, tgt)
        if sha(tgt) != h:
            print(f"REFUSED: the copy of {p_} does not match its sha256; nothing was removed", file=sys.stderr)
            return 3
        rows.append(dict(original=os.path.abspath(p_), archived=os.path.relpath(tgt, dest), sha256=h, bytes=os.path.getsize(p_)))
    man = os.path.join(dest, "MANIFEST.tsv")
    pd.DataFrame(rows, columns=["original", "archived", "sha256", "bytes"]).to_csv(man, sep="\t", index=False)
    msha = sha(CODE["mix_module"])
    disc = [f"# tag event {ev}: a stopped tag archived before the re-run (N2) — disclose it under the doc's freeze marker", f"- reason: {reason.strip()}",
            f"- time: {_dt.datetime.now().isoformat(timespec='seconds')}", f"- the module at the reset: {msha}", f"- MANIFEST.tsv sha256: {sha(man)} ({len(rows)} files)", "",
            "## the archived printouts (already seen)"]
    for r_ in rows:
        if r_["archived"].startswith("module/") and r_["archived"].endswith(".txt"):
            try:
                with open(os.path.join(dest, r_["archived"]), encoding="utf-8", errors="replace") as fh:
                    lines = [ln.rstrip() for ln in fh if ln.startswith(("STOPPED", "DRY RUN COMPLETE", "ALL GATES PASSED"))]
            except OSError:
                lines = []
            disc.append(f"- {os.path.basename(r_['original'])} ({r_['sha256']}): " + (" | ".join(lines) if lines else "no STOPPED / COMPLETE line"))
    with open(os.path.join(dest, "DISCLOSURE.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(disc) + "\n")
    L = os.path.join(root, "events.tsv")
    new = not os.path.exists(L)
    with open(L, "a") as fh:
        if new:
            fh.write("event\ttime\treason\tmanifest_sha256\tfiles\tmodule_sha\n")
        fh.write(f"{ev}\t{_dt.datetime.now().isoformat(timespec='seconds')}\t{reason.strip().replace(chr(9), ' ').replace(chr(10), ' ')}\t{sha(man)}\t{len(rows)}\t{msha}\n")
    for r_ in rows:
        os.remove(r_["original"])
    say(f"# #705 RULE MIX 01 — RESET (N2): tag event {ev}; {len(rows)} files moved to {os.path.relpath(dest, REPO)}; reason: {reason.strip()}")
    say(f"- next, in order: --dry-run, --print-pins; paste every pin incl. `- fit_event_{ev}: {sha(man)}` and the disclosure under the marker; then --tag")
    return 0


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    g = ap_.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--print-pins", "--pins", action="store_true", dest="print_pins")
    g.add_argument("--tag", action="store_true")
    g.add_argument("--reset", metavar="REASON", default=None)
    args = ap_.parse_args(argv)
    say = rp.Say()
    if args.dry_run:
        exo = mix_any_stage_output()
        if exo:
            print(f"REFUSED: stage output(s) already on disk: {exo[:6]} (the dry run precedes the tag)", file=sys.stderr)
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
    if args.reset is not None:
        return reset_tag(say, args.reset)
    if args.tag:
        return run_tag(say)
    return 1


if __name__ == "__main__":
    sys.exit(main())
