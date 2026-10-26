#!/usr/bin/env python3
"""#705 — CONTEXT RULES 01: which of his rules he applies in which context, matched closely — a context map chosen on 2020, scored on
2021-22, against one rule for all, shuffled contexts and random buyers and sellers (docs/analysis/cb_context_rules_prereg_2026-10-26.md).
REGISTERED, NOT FROZEN, NOT RUN. Built to execution depth; `--run` runs ONCE after the freeze. Research only: nothing here changes a
strategy, entry, stop, exit, size, safeguard or live trade state (THE LINE). The read is DESCRIPTIVE: it decides nothing.

The FROZEN rule-mix module (`scripts/probes/_705_rule_mix_1025/01_mix_frozen_75c832541cef.py`, sha pinned below, refused on drift) is imported
read-only, and through it the frozen intraday module, the frozen reverse module, the holdings replay, the runner and `cb`. Nothing in them is
edited and no attribute of them is reassigned. Every rule-mix helper that hard-codes the RULE-MIX files (its freeze lock, dry-run test, ledger,
pins, output writer, G8) is either replaced by this module's own `ctx_*` helper or called with THIS read's path passed explicitly (a module scan
in the tests enforces both: guard D4).

STAGES (§11)
  --dry-run       loads every input; the populations re-asserted against the rule-mix tag files BY EID reading ONLY their label, offset, clock and
                  fill columns (never a bucket column); every context computed from DECISION-TIME views (daily bars dated <= D, the buy day's
                  open, the buy day's minutes strictly before min(09:35, flat_clock) for C-E1 / strictly before the fill minute for C-S1); the
                  by-date assertion on every trade; the missing counts; the tertile cuts, the HW medians and the SW cut; every candidate split's
                  child sizes, the dedupe, the tree counts before / after the dedupe and the floor and the first ten trees; per minute tree C-E1's
                  distribution and the minute / export buy-day volume ratio; SPY's presence; the coverage from the fetch logs; every count of
                  the doc asserted (each mismatch printed, then STOP); the constants and the pins. NO outcome: no rule fired, no bucket read,
                  no map scored.
  --print-pins    (also --pins) the pins to paste under the doc's freeze marker line (the constants re-read from the dry run's printout).
  --run           ONCE, after the freeze: refuses unless every pin (incl. `doc_body`, the constants) sits under the marker BY NAME, the body
                  equals the freeze body, this module's sha equals its pin, THIS read's dry run is complete, no run output exists and every
                  reset event is disclosed; copies the module beside the pins; then the contexts and cuts re-derived and held to the pins (D2),
                  G6, G8, the rule-mix fires re-built, G1-G5 (each STOPS the run before any new number), then ENTER -> STOP -> EXIT on every block
                  and tolerance: the map, BEST, ORACLE-1, SHUF, the chance arms (c-1) / (c-2), UNION, the paired intervals, the labels, the
                  groups, the beside lines; the per-trade files.
  --reset "<reason>"   after a STOPPED run only: every artifact COPIED to run_events/<event>/ (sha256 verified, MANIFEST.tsv, DISCLOSURE.md,
                  events.tsv) and only then removed — never deleted; `fit_event_<event>` must sit under the marker before --run runs again.

READINGS fixed here where the registration is silent or two of its sentences pull apart (each the stricter one, printed by the dry run):
  C1  C-E1's per-minute rate = the mean volume of the minute BARS present in [09:30, bound) (bound = min(09:35, flat_clock)); no bar before
      the bound -> MISSING. ADV20 = the mean of the stock's 20 daily volumes ending at D, on the 20 consecutive record-calendar sessions
      ending at D (a hole inside them -> MISSING; a zero mean -> MISSING).
  C2  The market's trend: SPY's 50-day mean on the record's calendar needs a SPY bar on every one of the 50 sessions ending at D and at D-10
      (a gap -> MISSING); uptrend = the mean at D strictly above the mean 10 sessions earlier.
  C3  No stock bar dated D on the record's calendar -> EVERY context of the trade MISSING (ADR20 is a D read, so C-S1 and the market too).
  C4  A missing value follows the larger child by the 2020 count of DEFINED values; a tie -> the left (<= cut) child. Fixed per split, applied
      to every block.
  C5  A binary context's left child = the value 0 (C-E2: the open above the prior high; C-E3 / C-S3 / C-X4: not an uptrend).
  C6  The dedupe compares UNORDERED 2020 partitions (a split and its mirror are one partition); the earlier split in §5c's order is kept; a
      degenerate split (an empty side) stays a candidate and dies under the floor.
  C7  The canonical tree order = (groups, root split, left option, right option), option 0 = a group, option k = the k-th split (after the
      dedupe); the first maximum in that order IS the tie rule of §5c; a group's rule = the first maximum in library order.
  C8  B1 re-cross: a minute t in (flat, first] whose high >= the level in force at t (the doc's ">=", where a first crossing is ">"), the
      level existing at t, preceded by a minute u in [flat, t) whose close < that level. B2 = EXPLAINS or the frozen range_verdict HIT /
      BALLPARK (the instruction's union, exactly).
  C9  A rule that never fires or abstains reads its unwidened window at every tolerance (it is never CLOSE either way); every widened window
      is clipped at offset 0 and at J_tail; a random-level touch is a same-session firing ((a_f, b_f) = (1, 0) at ±1c).
  C10 (c-1) denominators = the rule-mix's own: the k-price arm over every window; the shared window and the random level over the trades
      with room; control (a) over every trade (each has >= 2 placements). (c-2): a trade without room on an arm contributes a row of
      False to every draw (it stays in the denominator for MAP and BEST alike).
  C11 Each mode of control (a) — frames and no frames (R15) — is its OWN arm for `beats chance` (stricter than the rule-mix's larger of two).
  C12 SHUF and (c-2) of a FIXED map (HW, HW-X', SW) = the fixed map scored on the permuted rows / on the control draws; SW has no context, so
      its SHUF equals its own share; SW is no library rule, so on the random-level arm its (c-2) column is the single-level draw (= its (c-1)).
  C13 SW's distance on held session j = (close_{j-1} - SMA20_{j-1}) / (ADR20_D x close_{j-1}), close_{-1} = close_D; an undefined distance
      (no bar at j-1, the 20-day not yet defined) reads -inf (not far) — so the cut -inf / +inf reproduce M-3 / M-4 Fire for Fire.
  C14 The real map's percentile among the 200 SHUF scores = the mid-rank (below + half the ties) / 200; p95 = numpy's linear percentile.
  C15 The paired bootstrap: the 2.5 / 97.5 percentiles of the 2,000 resampled mean differences; MAP - SHUF's per-trade term = the trade's mean
      CLOSE under the 200 permutations' maps. McNemar: the two discordant counts and the exact two-sided binomial p.
  C16 MAP-T1, HW, HW-X' and SW print (with their labels) at the primary tolerance; the MAP at every tolerance; the undated ENTER flickers are
      scored by the 2020-chosen map beside, never summed.
  C17 The panel-artefact flag (§1 4h): a group whose median bracket width (ENTER) is >= 2x or <= 0.5x the median of the rest of its block.
  C18 G1 parses the tag files as they serialize: offsets / minutes through `fnum` (never float()), a blank cell -> None, 'True' / 'False' ->
      bool (any other boolean cell refuses), floats equal within 1e-9 relative; every column the rule-mix wrote for a row is compared.
  C19 C-S1's candidate cuts in the table's order: his 1.0 first, then T1, T2.
  C20 The tests' fixture copy of the registered doc lives under this read's folder (`fixtures/`), not `tests/fixtures/` (the task's write scope).
  C21 MAP-T1 is labelled against ITS OWN no-split tree (the best tier-1 rule, BEST-T1); HW, HW-X' and SW against the full-library BEST.

No subagent, no DB, no network, no ssh, no docker. Read-only on every input. Nothing dated after 2024-12-31 is read (the frozen store's seal,
guard 12; every date a view reads asserted); nothing of 2025-26 is opened; replay/ and his_exits/ are never opened (guard 9).
Run:  python3 scripts/probes/_705_context_1026/01_ctx.py --dry-run
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True                  # never drop a .pyc beside a frozen module of another read

import argparse
import bisect
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
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
MIX_DIR = os.path.join(REPO, "scripts", "probes", "_705_rule_mix_1025")
MIX_FROZEN = os.path.join(MIX_DIR, "01_mix_frozen_75c832541cef.py")
MIX_FROZEN_SHA = "75c832541cef5e0abf2476a6484f37b857ab191284672914666996669d7bf300"      # the rule-mix read's frozen module (its tag copy)
MIX_DOC_BODY_PREFIX = "6a2512024c5f"                                                       # the rule-mix registration's doc_body (§11)


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_frozen_mix():
    got = sha(MIX_FROZEN)
    if got != MIX_FROZEN_SHA:
        raise SystemExit(f"REFUSED: the frozen rule-mix module is not the frozen one ({got} vs {MIX_FROZEN_SHA})")
    spec = importlib.util.spec_from_file_location("_705_mix_frozen_ctx", MIX_FROZEN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_705_mix_frozen_ctx"] = mod
    spec.loader.exec_module(mod)
    return mod


mix = _load_frozen_mix()
fz, rev, rp, R, cb, H = mix.fz, mix.rev, mix.rp, mix.R, mix.cb, mix.H
GuardStop = fz.GuardStop
Fire = mix.Fire
fnum, pct, binom_ci, hhmm_to_min, min_to_hhmm, bar_sym, era_of = fz.fnum, fz.pct, fz.binom_ci, fz.hhmm_to_min, fz.min_to_hhmm, fz.bar_sym, fz.era_of
EX, ME, UN, NE = mix.EX, mix.ME, mix.UN, mix.NE
CODE_OF, BUCKETS = mix.CODE_OF, mix.BUCKETS

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths: THIS read's (every module, printout, ledger and pins path lives in scripts/probes/_705_context_1026/; the per-trade files in out/)
# and the rule-mix read's files this read re-reads (pinned)
# ═════════════════════════════════════════════════════════════════════════════════════════════
DOC = os.path.join(REPO, "docs", "analysis", "cb_context_rules_prereg_2026-10-26.md")
OUT_DIR = os.path.join(HERE, "out")
P_DRY = os.path.join(HERE, "01_ctx_dryrun.txt")
P_RUN = os.path.join(HERE, "01_ctx_run.txt")
P_PINS = os.path.join(HERE, "01_ctx_pins.txt")
LEDGER = os.path.join(HERE, "01_ctx_ledger.tsv")
STOPPED = os.path.join(HERE, "01_ctx.STOPPED.txt")
FREEZE_BODIES = os.path.join(HERE, "freeze_bodies")
RUN_EVENTS = os.path.join(HERE, "run_events")
DRY_SIDE = os.path.join(HERE, "dryrun_side")
FROZEN_DIR = HERE                                                           # guard (2): the module copied here before --run reads a bar
TESTS = os.path.join(REPO, "tests", "test_context_rules.py")
CODE = {"ctx_module": os.path.abspath(__file__), "ctx_tests": TESTS}
MIX_DOC = mix.DOC                                                           # mix-path-ok (the rule-mix registration, read only)
MIX_TAG_DIR = mix.OUT_DIR                                                   # mix-path-ok (holdings_1024/rule_mix: the tag files, read only)
MIX_LEDGER = mix.LEDGER                                                     # mix-path-ok (the rule-mix ledger: verified, never appended)
MIX_FILES = {
    "mix_doc": MIX_DOC,
    "mix_frozen_module": MIX_FROZEN,
    "mix_tag_printout": mix.P_TAG,                                          # mix-path-ok
    "mix_recount_tag": os.path.join(MIX_DIR, "verify", "recount_tag.txt"),
    "mix_tags_enter": os.path.join(MIX_TAG_DIR, "tags_enter.tsv"),
    "mix_tags_stop": os.path.join(MIX_TAG_DIR, "tags_stop.tsv"),
    "mix_tags_exit": os.path.join(MIX_TAG_DIR, "tags_exit.tsv"),
    "mix_control_windows": os.path.join(MIX_TAG_DIR, "control_windows.tsv.gz"),
}
TRAIL_SPEED_SOURCE = os.path.join(REPO, "agents", "market_intelligence", "consolidation_breakout.py")   # read by one dry-run claim; live code: never pinned
TAG_FILE = {"ENTER": MIX_FILES["mix_tags_enter"], "STOP": MIX_FILES["mix_tags_stop"], "EXIT": MIX_FILES["mix_tags_exit"]}
TRADE_IMPACT, G8_FILES = mix.TRADE_IMPACT, mix.G8_FILES                     # G8 (guard 4): the audit script and its era files
FETCH_LIST = mix.FETCH_LIST                                                 # the intraday fetch list (§10: 19,470 pairs)
for _p in [OUT_DIR, HERE] + list(MIX_FILES.values()):
    assert not any(_p.startswith(d + "/") or _p == d for d in fz.FORBIDDEN_DIRS), _p      # guard (9)

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants (every number is the doc's)
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = fz.CUT_B                                # 2024-12-31 (guard 12)
SEED = fz.SEED                                  # 702
DRAWS = mix.DRAWS                               # 200: the rule-mix's control draws (the same streams)
PERMS = 200                                     # §6b
BOOTS = 2000                                    # §5d
PERM_KEY = "ctx|perm|{decision}|{block}|{p}"
BOOT_KEY = "ctx|boot|{decision}|{block}|{line}|{r}"
PLACE_KEY = "ctx|place|{decision}|{eid}|{d}"
FLOOR_MIN, FLOOR_SHARE = 15, 0.10               # §5b: m = max(15, ceil(0.10 x n_2020))
MARGIN = 0.10                                   # §7a: 10.0 points on every label
E1_MINUTE = 5                                   # 09:35 — the moment the 5-minute high exists (C-E1's bound)
SESSION_MINUTES = 390                           # ADV20 / 390 (a full session)
ADV_N, SPY_SMA_N, SPY_LAG = 20, 50, 10
C_S1_CAP = 1.0                                  # his cap: one ADR
HWX_PRIME_CUT = 0.0479                          # Apollo's TRAIL_SPEED_ADR_CUT (consolidation_breakout.py l.186)
BLOCKS = mix.BLOCKS                             # ("2020", "2021-22", "untouched")
LABEL_BLOCKS = mix.LABEL_BLOCKS                 # ("2020", "2021-22")
DECISIONS = mix.DECISIONS
LIB = mix.LIB_CODES
TIER1 = {d: tuple(r.code for r in mix.LIBRARY[d] if r.tier == 1) for d in DECISIONS}
TOLS = {"ENTER": ("bracket", "B1", "B2"), "STOP": ("pm1c", "pm0", "pm1", "pm2"), "EXIT": ("pm1c", "pm0", "pm1", "pm2")}
PRIMARY = {"ENTER": "bracket", "STOP": "pm1c", "EXIT": "pm1c"}
TOL_LABEL = {"bracket": "the bracket (primary)", "B1": "B1 re-cross", "B2": "B2 hit-or-ballpark", "pm1c": "±1c (primary)", "pm0": "±0", "pm1": "±1 symmetric",
             "pm2": "±2"}
ARMS = {"ENTER": ("kprice", "shared"), "STOP": ("a_frames", "a_noframes", "rlevel"), "EXIT": ("a_frames", "a_noframes", "rlevel")}
ARM_LABEL = {"kprice": "k-price random prices", "shared": "the shared random window", "a_frames": "control (a), frames", "a_noframes": "control (a), no frames",
             "rlevel": "random levels"}
TIMING_ARMS = {"shared", "a_frames", "a_noframes"}
DRY_HEADER = "# #705 CONTEXT RULES 01 — DRY RUN"
DRY_RESULT_RX = re.compile(r"^## RESULT: (\d+) claims, (\d+) OK, 0 MISMATCH\b")
RUN_HEADER = "# #705 CONTEXT RULES 01 — RUN"
HEX64_RX = re.compile(r"^[0-9a-f]{64}$")
CONST_RX = re.compile(r"^- (ctx_const_[A-Za-z0-9_.-]+): (\S+)\s*$")

# the known answers (G2 / G5), every one copied from the rule-mix tag printout the doc cites (01_mix_tag.txt)
KNOWN_BEST = {"ENTER": ("L1", {"2020": 0.364, "2021-22": 0.433}), "STOP": ("S1-T", {"2020": 0.453, "2021-22": 0.448}),
              "EXIT": ("M-8", {"2020": 0.309, "2021-22": 0.279})}
KNOWN_UNION = {"ENTER": {"2020": 0.568, "2021-22": 0.667}, "STOP": {"2020": 0.540, "2021-22": 0.578}, "EXIT": {"2020": 0.715, "2021-22": 0.729}}
KNOWN_G5 = {"ENTER": {"2020": {"kprice": 0.210, "shared": 0.031}, "2021-22": {"kprice": 0.313, "shared": 0.044}},
            "STOP": {"2020": {"a_frames": 0.300, "a_noframes": 0.315, "rlevel": 0.404}, "2021-22": {"a_frames": 0.285, "a_noframes": 0.296, "rlevel": 0.417}},
            "EXIT": {"2020": {"a_frames": 0.287, "a_noframes": 0.287, "rlevel": 0.236}, "2021-22": {"a_frames": 0.307, "a_noframes": 0.307, "rlevel": 0.281}}}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# THE CONTEXTS (§3): a fixed, short list per decision, each with its cite; the candidate splits in §5c's order
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Context:
    cid: str
    decision: str
    name: str
    kind: str                     # "cont" | "bin"
    cuts: tuple                   # cut tokens in §5c's order: "1.0" (his cap), "T1", "T2"; ("bin",) for a binary context
    read_at: str
    cite: str


CONTEXTS = {
    "ENTER": (
        Context("C-E1", "ENTER", "opening volume: the per-minute volume before min(09:35, flat_clock) / (ADV20 / 390)", "cont", ("T1", "T2"),
                "min(09:35, flat_clock)", "l.1712-1713 (his EP words, TRANSFERRED to all trades: our reading); l.1735-1736 the notes' summary"),
        Context("C-E2", "ENTER", "the daily breakout still ahead at the open (open <= the prior session's high = 1)", "bin", ("bin",), "the open",
                "l.2091-2092; l.1942"),
        Context("C-E3", "ENTER", "the market's trend (SPY's 50-day above 10 sessions earlier = 1) — OUR READING", "bin", ("bin",), "D's close",
                "l.2606 (the method line); l.2481 a phrasing ruling; 03_market_trend_split.py l.1-3"),
    ),
    "STOP": (
        Context("C-S1", "STOP", "the stop's width against his cap: (fill - the low before the fill minute) / (ADR20 x fill)", "cont", ("1.0", "T1", "T2"),
                "the fill", "l.1943 (his cap); coupled to S1-T (§1 4c)"),
        Context("C-S2", "STOP", "speed: ADR20", "cont", ("T1", "T2"), "D", "l.2046-2047, l.2095-2096 (his trail words; transferred to the stop: our reading)"),
        Context("C-S3", "STOP", "the market's trend — OUR READING", "bin", ("bin",), "D's close", "l.2606; l.2481 a phrasing ruling"),
    ),
    "EXIT": (
        Context("C-X1", "EXIT", "speed: ADR20", "cont", ("T1", "T2"), "D", "l.2046-2047, l.2095-2096, l.2054-2055; a prior read at 4.79% (§1 4e)"),
        Context("C-X2", "EXIT", "how far from the 10-day: (close_D - SMA10_D) / (ADR20 x close_D)", "cont", ("T1", "T2"), "D's close", "l.2047"),
        Context("C-X3", "EXIT", "how far from the 20-day: (close_D - SMA20_D) / (ADR20 x close_D)", "cont", ("T1", "T2"), "D's close", "l.2047"),
        Context("C-X4", "EXIT", "the market's trend — OUR READING", "bin", ("bin",), "D's close", "l.2606; l.2481 a phrasing ruling; l.1948 move size"),
    ),
}
CIDS = {d: tuple(c.cid for c in CONTEXTS[d]) for d in DECISIONS}
SPLIT_ORDER = {d: tuple((c.cid, t) for c in CONTEXTS[d] for t in c.cuts) for d in DECISIONS}
assert tuple(len(SPLIT_ORDER[d]) for d in DECISIONS) == (4, 6, 7)


def readings_lines() -> list:
    """C1-C21 of the module docstring, one reading per line (the dry run prints them)."""
    doc = __doc__ or ""
    block = doc.split("READINGS fixed here", 1)[1].split("No subagent", 1)[0]
    out, cur = [], ""
    for ln in block.splitlines()[1:]:
        if re.match(r"^\s+C\d+\s", ln):
            if cur:
                out.append(cur)
            cur = "  " + ln.strip()
        elif ln.strip() and cur:
            cur += " " + ln.strip()
    if cur:
        out.append(cur)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_tsv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)


def cell_int(s) -> "int | None":
    """A TSV offset / minute cell ('3.0') -> int; blank -> None (C18; `fnum`, never float())."""
    if s is None or str(s).strip() in ("", "nan", "None"):
        return None
    return int(round(fnum(str(s))))


def cell_bool(s) -> "bool | None":
    v = "" if s is None else str(s).strip()
    if v == "True":
        return True
    if v == "False":
        return False
    if v in ("", "nan", "None"):
        return None
    raise GuardStop(f"a boolean cell reads {v!r} (only 'True' / 'False' / blank)")


def cell_float(s) -> float:
    if s is None or str(s).strip() in ("", "nan", "None"):
        return math.nan
    return fnum(str(s))


def share(k, n) -> float:
    return (k / n) if n else math.nan


def tenths(x: float) -> int:
    return mix.tenths(x)


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def floor_m(n_2020: int) -> int:
    return max(FLOOR_MIN, int(math.ceil(FLOOR_SHARE * n_2020 - 1e-12)))


def fmt_val(x) -> str:
    """A constant as the printed (and pinned) string: repr round-trips a float exactly; None -> NONE."""
    if x is None:
        return "NONE"
    return repr(fnum(x))


def ctx_write_out(name: str, rows: list, compression=None, columns=None) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, name)
    pd.DataFrame(rows, columns=columns).to_csv(p, sep="\t", index=False, compression=compression)
    return p


# the frozen loaders and builders this read calls as they are (one name each, so the synthetic tests can stand a world in for the real data)
def load_core(say) -> dict:
    return mix.load_core(say)


def load_markets(say, C: dict, keep_A: set, keep_B: set) -> dict:
    return mix.load_markets(say, C, keep_A, keep_B)


def check_inputs(say) -> None:
    """The rule-mix read's own input check (the intraday pins and files through the frozen module), the rule-mix ledger against the disk
    (the tag files and its printout unchanged since the tag wrote them), the rule-mix doc body, then this read's files on disk."""
    mix.check_mix_inputs(say)
    bad = []
    if sha(MIX_FROZEN) != MIX_FROZEN_SHA:
        bad.append("the frozen rule-mix module")
    if not fz.doc_body_sha(MIX_DOC).startswith(MIX_DOC_BODY_PREFIX):
        bad.append(f"the rule-mix doc body ({fz.doc_body_sha(MIX_DOC)[:12]} vs {MIX_DOC_BODY_PREFIX})")
    for k, v in MIX_FILES.items():
        if not os.path.exists(v):
            bad.append(f"{k} missing ({v})")
    lb = fz.ledger_verify(MIX_LEDGER)
    if lb:
        bad.append("the rule-mix ledger does not match the disk: " + "; ".join(lb))
    if bad:
        raise GuardStop("this read's inputs: " + "; ".join(bad))
    say(f"- this read's inputs: the frozen rule-mix module {MIX_FROZEN_SHA[:12]}, the rule-mix doc body {MIX_DOC_BODY_PREFIX}, the rule-mix ledger "
        "re-verified (the three tag files, control_windows.tsv.gz and 01_mix_tag.txt unchanged since the tag), the recount on disk")


def assert_populations(say, C: dict) -> None:
    mix.assert_populations(say, C)


def market_names(C: dict) -> tuple:
    ni = C["S"]["ni"]
    return ({b.sym_a for b in ni if b.has_bars} | {"QQQ", "SPY"}, {b.sym for b in ni if b.has_bars and b.E > fz.A_LAST} | {"QQQ", "SPY"})


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the populations (§2): the rule-mix tag files' scorable sets, read from their label / offset / clock / fill columns ONLY (D2)
# ═════════════════════════════════════════════════════════════════════════════════════════════
LABEL_COLS = {"ENTER": ("eid", "sym", "E", "block", "dated", "flicker", "flat_clock", "first_clock", "tagged"),
              "STOP": ("eid", "sym", "E", "block", "dated", "era", "status", "room", "loser", "exit_lo_j", "exit_hi_j", "J_tail", "fill",
                       "fill_minute", "fill_src", "stop"),
              "EXIT": ("eid", "sym", "E", "block", "dated", "era", "status", "room", "loser", "exit_lo_j", "exit_hi_j", "J_tail", "fill",
                       "fill_minute", "fill_src", "stop")}


def read_labels(dec: str) -> pd.DataFrame:
    """A tag file's LABEL columns only (never a bucket column) — D2: the populations and the cuts before any bucket is read. The header is
    read first; then ONLY the label columns are parsed (`usecols`): no bucket cell is ever loaded by the dry run."""
    head = pd.read_csv(TAG_FILE[dec], sep="\t", dtype=str, keep_default_na=False, nrows=0)
    miss = [c for c in LABEL_COLS[dec] if c not in head.columns]
    if miss:
        raise GuardStop(f"{os.path.basename(TAG_FILE[dec])} lacks the label columns {miss}")
    t = pd.read_csv(TAG_FILE[dec], sep="\t", dtype=str, keep_default_na=False, usecols=list(LABEL_COLS[dec]))
    return t[list(LABEL_COLS[dec])].copy()


@dataclass
class TradeRow:
    """One scorable (or beside) trade of one decision, as the tag file's label columns give it."""
    eid: int
    sym: str
    E: str
    block: str
    dated: bool
    decision: str
    beside: bool = False
    flicker: bool = False
    flat_m: "int | None" = None
    first_m: "int | None" = None
    era: str = ""
    exit_lo_j: "int | None" = None
    exit_hi_j: "int | None" = None
    J_tail: "int | None" = None
    fill: float = math.nan
    fill_minute: "int | None" = None
    fill_src: str = ""
    loser: "bool | None" = None
    setup: str = ""

    @property
    def width(self) -> "int | None":
        return (self.first_m - self.flat_m) if (self.first_m is not None and self.flat_m is not None) else None

    @property
    def window_w(self) -> "int | None":
        return (self.exit_hi_j - self.exit_lo_j + 1) if (self.exit_hi_j is not None and self.exit_lo_j is not None) else None


def populations(C: dict) -> dict:
    """{decision: {"scorable": {block: [TradeRow]}, "beside": {block: [TradeRow]}}} from the tag files' label columns; every row's setup from
    the timeline (C['buys']). ENTER: tagged windows (dated flickers in); beside = the undated flickers. STOP: scorable, room, loser. EXIT:
    scorable, room."""
    setup = {b.eid: b.setup for b in C["buys"]}
    out = {}
    for dec in DECISIONS:
        t = read_labels(dec)
        sc, bs = defaultdict(list), defaultdict(list)
        for row in t.to_dict("records"):
            eid = int(row["eid"])
            tr = TradeRow(eid=eid, sym=row["sym"], E=row["E"], block=row["block"], dated=bool(cell_bool(row["dated"])), decision=dec, setup=setup.get(eid, ""))
            if row["E"] > CUT_B:
                raise GuardStop(f"guard (12): a tag row dated {row['E']} (after {CUT_B})")
            if dec == "ENTER":
                tr.flicker = bool(cell_bool(row["flicker"]))
                tr.flat_m, tr.first_m = hhmm_to_min(row["flat_clock"]), hhmm_to_min(row["first_clock"])
                if cell_bool(row["tagged"]):
                    sc[tr.block].append(tr)
                elif tr.flicker and not tr.dated:
                    tr.beside = True
                    bs[tr.block].append(tr)
                continue
            tr.era, tr.exit_lo_j, tr.exit_hi_j, tr.J_tail = row["era"], cell_int(row["exit_lo_j"]), cell_int(row["exit_hi_j"]), cell_int(row["J_tail"])
            tr.fill, tr.fill_minute, tr.fill_src, tr.loser = cell_float(row["fill"]), cell_int(row["fill_minute"]), row["fill_src"], cell_bool(row["loser"])
            if row["status"] != "scorable" or not cell_bool(row["room"]):
                continue
            if dec == "STOP" and not tr.loser:
                continue
            sc[tr.block].append(tr)
        out[dec] = dict(scorable={b: sorted(sc.get(b, []), key=lambda x: x.eid) for b in BLOCKS}, beside={b: sorted(bs.get(b, []), key=lambda x: x.eid) for b in BLOCKS})
    return out


def assert_tag_rows_against_records(say, C: dict, ER: dict, SR: dict) -> None:
    """Guard (3): every tag row's eid / sym / E / block / dated / era / exit offsets equals the record the frozen builders give (one calendar
    per record); every ENTER tagged row is a frozen ENTER block's tagged buy; every STOP / EXIT row a frozen STOP / EXIT block's buy."""
    bad = []
    eb, sb = mix.enter_blocks(C), mix.se_blocks(C)
    for dec in DECISIONS:
        t = read_labels(dec)
        for row in t.to_dict("records"):
            eid, blk = int(row["eid"]), row["block"]
            if dec == "ENTER":
                r = ER.get(eid)
                pool = {b.eid for b in eb[blk]["tagged"]} if cell_bool(row["tagged"]) else {b.eid for bs in eb[blk]["beside"].values() for b in bs}
                if eid not in pool:
                    bad.append(f"ENTER eid {eid}: not in the frozen block {blk}'s {'tagged' if cell_bool(row['tagged']) else 'beside'} buys")
            else:
                r = SR.get(eid)
                if eid not in {b.eid for bs in sb[blk].values() for b in bs}:
                    bad.append(f"{dec} eid {eid}: not in the frozen block {blk}")
            if r is None:
                bad.append(f"{dec} eid {eid}: no record")
                continue
            if (r.b.sym, r.b.E, bool(r.b.dated)) != (row["sym"], row["E"], bool(cell_bool(row["dated"]))):
                bad.append(f"{dec} eid {eid}: sym / E / dated {r.b.sym} {r.b.E} {r.b.dated} vs the tag row {row['sym']} {row['E']} {row['dated']}")
            if dec != "ENTER":
                if r.era != row["era"] or r.exit_lo_j != cell_int(row["exit_lo_j"]) or r.exit_hi_j != cell_int(row["exit_hi_j"]):
                    bad.append(f"{dec} eid {eid}: era / exit offsets {r.era} {r.exit_lo_j}..{r.exit_hi_j} vs {row['era']} {row['exit_lo_j']}..{row['exit_hi_j']}")
                room = cell_bool(row["room"])
                if room is not None and r.exit_lo_j is not None and room != (r.exit_lo_j + 1 >= mix.MIN_PLACEMENTS):
                    bad.append(f"{dec} eid {eid}: room {room} vs exit_lo_j {r.exit_lo_j}")
    n_rec = {"ENTER": len(read_labels("ENTER")), "STOP": len(read_labels("STOP")), "EXIT": len(read_labels("EXIT"))}
    if set(int(x) for x in read_labels("STOP")["eid"]) != set(SR) or set(int(x) for x in read_labels("EXIT")["eid"]) != set(SR):
        bad.append(f"the STOP / EXIT tag files' eids differ from the frozen builders' {len(SR)} records")
    if set(int(x) for x in read_labels("ENTER")["eid"]) - set(ER):
        bad.append("an ENTER tag row has no ENTER record")
    say(f"- populations re-asserted against the tag files by eid (labels, offsets, clocks only): ENTER {n_rec['ENTER']} rows / STOP {n_rec['STOP']} / EXIT "
        f"{n_rec['EXIT']}; records ENTER {len(ER)}, STOP / EXIT {len(SR)}; differences {len(bad)}")
    if bad:
        raise GuardStop("the populations differ from the tag files: " + "; ".join(bad[:6]) + (" ..." if len(bad) > 6 else ""))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# DECISION-TIME VIEWS (D1): every context is read from a view truncated at its decision time; the same pure function on the FULL record (G6)
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class View:
    b: object
    E: str
    D: "str | None"                 # the record calendar's predecessor of E
    ci_D: int
    cal: list                       # the record's calendar (truncated: sessions <= D)
    daily: object                   # DailyBars (truncated: dated < E)
    open_E: "float | None"          # the buy day's open (ENTER only)
    minutes: object                 # MinuteBars (truncated: strictly before the bound) or None
    bound_m: "int | None"           # the minute bound (C-E1: min(5, flat_m); C-S1: the fill minute; a close fill: the session's close, 210 on an early close)
    spy: object                     # SPY DailyBars (truncated: dated <= D)
    spy_ci: np.ndarray              # SPY's calendar indices
    fill: float = math.nan
    fill_minute: "int | None" = None
    fill_src: str = ""
    truncated: bool = True


def spy_of(M: dict, era: str) -> tuple:
    """(SPY DailyBars, calendar indices) in the era's export — the same pinned export the record's calendar is built from."""
    bars, cidx = fz.bars_of(M["Ds"][era], "SPY")
    if bars is None:
        raise GuardStop(f"SPY is absent from the era-{era} export (the calendar is built from its rows)")
    return bars, np.asarray(cidx)


def minute_bound(dec: str, tr: TradeRow) -> "int | None":
    if dec == "ENTER":
        return min(E1_MINUTE, int(tr.flat_m))
    if dec == "STOP":
        # a close-proxy fill: every minute of the session before the CLOSE — 16:00 = 390, or 13:00 = 210 on an early close (the minute
        # files keep the after-hours prints of an early-close day; they follow the fill and are never read)
        return fz.session_end_minute(tr.E) if tr.fill_minute is None else int(tr.fill_minute)
    return None


def _cut_minutes(mb, bound: int):
    sel = mb.minute < bound
    return cb.MinuteBars(mb.minute[sel], mb.o[sel], mb.h[sel], mb.l[sel], mb.c[sel], mb.v[sel])


def make_view(rec, dec: str, tr: TradeRow, spy: tuple, full: bool = False) -> View:
    """The decision-time view of one trade (full=False: arrays PHYSICALLY sliced at the decision time) or the full record (full=True: the
    same fields, nothing cut — G6 holds the two computations equal)."""
    e, e_ci = rec.e, rec.e_ci
    D = rec.cal[e_ci - 1].isoformat() if e_ci >= 1 else None
    if rec.b.E > CUT_B or (D is not None and D > CUT_B):
        raise GuardStop(f"guard (12): eid {rec.b.eid} reads a date after {CUT_B}")
    bound = minute_bound(dec, tr)
    sb, sci = spy
    if full:
        daily, cal, mins, spy_b, spy_ci = rec.bars, rec.cal, rec.mb, sb, sci
    else:
        daily, cal = rec.bars.slice(0, e), rec.cal[:e_ci]
        mins = _cut_minutes(rec.mb, bound) if (rec.mb is not None and bound is not None) else None
        k = int(np.searchsorted(sci, e_ci - 1, side="right"))
        spy_b, spy_ci = sb.slice(0, k), sci[:k]
    open_E = fnum(rec.bars.o[e]) if dec == "ENTER" else None
    return View(b=rec.b, E=rec.b.E, D=D, ci_D=e_ci - 1, cal=cal, daily=daily, open_E=open_E, minutes=mins if dec in ("ENTER", "STOP") else None, bound_m=bound,
                spy=spy_b, spy_ci=spy_ci, fill=tr.fill, fill_minute=tr.fill_minute, fill_src=tr.fill_src, truncated=not full)


def view_d_index(v: View) -> "int | None":
    """The index of the stock's bar DATED D in the view (searched by date, never by position: one calendar per record)."""
    if v.D is None:
        return None
    dd = date.fromisoformat(v.D)
    i = bisect.bisect_left(v.daily.dates, dd)
    return i if (i < len(v.daily.dates) and v.daily.dates[i] == dd) else None


def view_adr20(v: View, d_idx: int) -> float:
    try:
        return fnum(rev.adr20_at(v.daily, d_idx, v.b))
    except ValueError:
        return math.nan


def adv20(v: View, d_idx: int) -> float:
    """The mean daily volume of the 20 sessions ending at D (C1: on the 20 consecutive record-calendar sessions ending at D)."""
    lo = d_idx - ADV_N + 1
    if lo < 0 or v.ci_D - ADV_N + 1 < 0:
        return math.nan
    want = v.cal[v.ci_D - ADV_N + 1: v.ci_D + 1]
    if list(v.daily.dates[lo:d_idx + 1]) != list(want):
        return math.nan
    m = fnum(np.mean(np.asarray(v.daily.v[lo:d_idx + 1], dtype=float)))
    return m if m > 0 else math.nan


def spy_sma_at(v: View, ci: int) -> float:
    """SPY's 50-day mean at calendar index ci (C2: a SPY bar on every one of the 50 sessions ending there, else NaN)."""
    lo = ci - SPY_SMA_N + 1
    if lo < 0:
        return math.nan
    k0 = int(np.searchsorted(v.spy_ci, lo, side="left"))
    k1 = int(np.searchsorted(v.spy_ci, ci, side="right"))
    if k1 - k0 != SPY_SMA_N or int(v.spy_ci[k0]) != lo or int(v.spy_ci[k1 - 1]) != ci:
        return math.nan
    return fnum(np.mean(np.asarray(v.spy.c[k0:k1], dtype=float)))


def market_up(v: View) -> tuple:
    a, b = spy_sma_at(v, v.ci_D), spy_sma_at(v, v.ci_D - SPY_LAG)
    if not (np.isfinite(a) and np.isfinite(b)):
        return None, "spy_missing"
    return (1.0 if a > b else 0.0), ""


def context_values(dec: str, v: View) -> dict:
    """{cid: (value | None, missing reason)} — a PURE function of the view; it finds D by date and the minutes by the bound, so on the full
    record it must give the same values (G6)."""
    cids = CIDS[dec]
    d_idx = view_d_index(v)
    if d_idx is None:
        return {c: (None, "no_bar_D") for c in cids}
    adr = view_adr20(v, d_idx)
    adr_ok = bool(np.isfinite(adr) and adr > 0)
    out = {}
    if dec == "ENTER":
        if v.minutes is None:
            out["C-E1"] = (None, "no_minutes")
        else:
            sel = v.minutes.minute < v.bound_m
            if not sel.any():
                out["C-E1"] = (None, "no_minute_before_bound")
            else:
                a = adv20(v, d_idx)
                rate = fnum(np.mean(np.asarray(v.minutes.v[sel], dtype=float)))
                out["C-E1"] = (rate / (a / SESSION_MINUTES), "") if np.isfinite(a) else (None, "adv20_missing")
        out["C-E2"] = ((1.0 if v.open_E <= fnum(v.daily.h[d_idx]) else 0.0), "")
        out["C-E3"] = market_up(v)
        return out
    if dec == "STOP":
        if v.fill_minute == 0:
            out["C-S1"] = (None, "open_fill")
        elif v.minutes is None:
            out["C-S1"] = (None, "no_minutes")
        elif not adr_ok:
            out["C-S1"] = (None, "adr20_missing")
        else:
            sel = v.minutes.minute < v.bound_m
            if not sel.any():
                out["C-S1"] = (None, "no_minute_before_fill")
            else:
                low = fnum(np.min(np.asarray(v.minutes.l[sel], dtype=float)))
                out["C-S1"] = ((fnum(v.fill) - low) / (adr * fnum(v.fill)), "")
        out["C-S2"] = (adr, "") if adr_ok else (None, "adr20_missing")
        out["C-S3"] = market_up(v)
        return out
    # EXIT
    out["C-X1"] = (adr, "") if adr_ok else (None, "adr20_missing")
    cD = fnum(v.daily.c[d_idx])
    smas = fz.smas_for(v.daily)
    for cid, n in (("C-X2", 10), ("C-X3", 20)):
        s = fnum(smas[n][d_idx])
        out[cid] = (((cD - s) / (adr * cD)), "") if (adr_ok and np.isfinite(s)) else (None, "sma_or_adr_missing")
    out["C-X4"] = market_up(v)
    return out


def assert_view_dates(v: View, rec) -> list:
    """The by-date assertion (§7d, G6): every daily bar in the truncated view dated < E, the D bar dated the record calendar's predecessor of
    E (or MISSING), every minute < the bound, every SPY bar dated <= D, D <= 2024-12-31. -> the violations."""
    bad = []
    E = date.fromisoformat(v.E)
    if any(d >= E for d in v.daily.dates):
        bad.append("a daily bar dated >= E in the view")
    pred = rec.cal[rec.e_ci - 1].isoformat() if rec.e_ci >= 1 else None
    if v.D != pred:
        bad.append(f"D {v.D} is not the record calendar's predecessor of E ({pred})")
    di = view_d_index(v)
    if (di is not None) != (rec.bar_at(-1) is not None):
        bad.append("the bar read at D disagrees with the record's own bar e - 1")
    if di is not None and v.daily.dates[di].isoformat() != pred:
        bad.append("the bar read at D is not dated D")
    if v.minutes is not None and v.bound_m is not None and len(v.minutes) and int(v.minutes.minute.max()) >= v.bound_m:
        bad.append(f"a minute at or after the bound {v.bound_m}")
    if len(v.spy_ci) and int(v.spy_ci.max()) > v.ci_D:
        bad.append("a SPY bar dated after D")
    if v.D is not None and v.D > CUT_B:
        bad.append("D after the seal")
    return bad


def compute_contexts(dec: str, trades: list, recs: dict, spy_by_era: dict, check_full: bool = False) -> tuple:
    """{eid: {cid: (value, reason)}} from the truncated views (the dry run, the run); check_full = G6: the same function on the full record must
    give the same values, and the truncated view must pass the by-date assertion, on EVERY trade. -> (values, G6 failures)."""
    vals, fails = {}, []
    for tr in trades:
        rec = recs[tr.eid]
        sp = spy_by_era[rec.era]
        v = make_view(rec, dec, tr, sp)
        bad = assert_view_dates(v, rec)
        vals[tr.eid] = context_values(dec, v)
        if bad:
            fails.append((tr.eid, "; ".join(bad)))
        if check_full:
            vf = context_values(dec, make_view(rec, dec, tr, sp, full=True))
            for c in CIDS[dec]:
                a, b = vals[tr.eid][c], vf[c]
                if a != b:
                    fails.append((tr.eid, f"{c}: truncated {a} vs full {b}"))
            if np.isfinite(rec.adr20) and vals[tr.eid] and view_d_index(v) is not None:
                ad = view_adr20(v, view_d_index(v))
                if not (ad == fnum(rec.adr20)):
                    fails.append((tr.eid, f"ADR20 from the view {ad} vs the record's {rec.adr20}"))
    return vals, fails


# ═════════════════════════════════════════════════════════════════════════════════════════════
# THE CUTS (§3): tertiles on the 2020 DEFINED values; the HW medians; the splits with the missing rule; the dedupe
# ═════════════════════════════════════════════════════════════════════════════════════════════
def kth_smallest(vals: list, k: int) -> "float | None":
    v = sorted(fnum(x) for x in vals if x is not None)
    if not v or k < 1:
        return None
    return v[min(k, len(v)) - 1]


def tertile_cuts(vals: list) -> tuple:
    """(T1, T2) = the ceil(n/3)-th and ceil(2n/3)-th smallest DEFINED value (missing excluded); (None, None) on no defined value."""
    n = sum(1 for x in vals if x is not None)
    if n == 0:
        return None, None
    return kth_smallest(vals, ceil_div(n, 3)), kth_smallest(vals, ceil_div(2 * n, 3))


def median_cut(vals: list) -> "float | None":
    n = sum(1 for x in vals if x is not None)
    return kth_smallest(vals, ceil_div(n, 2)) if n else None


@dataclass(frozen=True)
class Split:
    decision: str
    cid: str
    token: str                     # "1.0" | "T1" | "T2" | "bin"
    cut: float
    missing_left: bool
    order: int                     # the position in §5c's order (before the dedupe)

    @property
    def name(self) -> str:
        return f"{self.cid} <= {self.token}" if self.token != "bin" else f"{self.cid} = 0"


def missing_side(vals: list, cut: float) -> bool:
    """C4: a missing value follows the larger child by the 2020 count of defined values; a tie -> left."""
    nl = sum(1 for x in vals if x is not None and fnum(x) <= cut)
    nr = sum(1 for x in vals if x is not None and fnum(x) > cut)
    return nl >= nr


def cut_values(dec: str, vals20: dict) -> dict:
    """{(cid, token): cut} on the 2020 scorable trades' values (vals20 = {cid: [value | None]})."""
    out = {}
    for c in CONTEXTS[dec]:
        if c.kind == "bin":
            out[(c.cid, "bin")] = 0.0
            continue
        t1, t2 = tertile_cuts(vals20[c.cid])
        for tok in c.cuts:
            out[(c.cid, tok)] = C_S1_CAP if tok == "1.0" else (t1 if tok == "T1" else t2)
    return out


def make_splits(dec: str, vals20: dict, cuts: dict) -> list:
    out = []
    for i, (cid, tok) in enumerate(SPLIT_ORDER[dec]):
        cut = cuts[(cid, tok)]
        if cut is None:
            continue
        out.append(Split(dec, cid, tok, fnum(cut), missing_side(vals20[cid], fnum(cut)), i))
    return out


def left_mask(s: Split, vals: list) -> np.ndarray:
    return np.array([(fnum(x) <= s.cut) if x is not None else s.missing_left for x in vals], dtype=bool)


def dedupe_splits(splits: list, vals20: dict) -> tuple:
    """C6: splits giving the SAME (unordered) 2020 partition merged, the earlier kept. -> (kept, [(dropped, kept_for)])."""
    kept, dropped, seen = [], [], []
    for s in splits:
        m = left_mask(s, vals20[s.cid])
        twin = next((k for k, km in seen if np.array_equal(km, m) or np.array_equal(km, ~m)), None)
        if twin is not None:
            dropped.append((s, twin))
            continue
        seen.append((s, m))
        kept.append(s)
    return kept, dropped


# ═════════════════════════════════════════════════════════════════════════════════════════════
# THE TREES (§5b-c): depth <= 2, at most 4 groups, the canonical order (C7), the floor; the exhaustive search on a CLOSE matrix
# ═════════════════════════════════════════════════════════════════════════════════════════════
def enumerate_trees(s: int) -> list:
    """Every tree on s candidate splits BEFORE the floor, in the canonical order: (groups, root, left option, right option); option 0 = a
    group, option k = split k - 1. 1 + s + s((s + 1)^2 - 1) trees."""
    keys = [(1, -1, 0, 0)]
    for r in range(s):
        keys.append((2, r, 0, 0))
    for r in range(s):
        for lo in range(s + 1):
            for ro in range(s + 1):
                if lo == 0 and ro == 0:
                    continue
                keys.append((2 + (lo > 0) + (ro > 0), r, lo, ro))
    keys.sort()
    assert len(keys) == 1 + s + s * ((s + 1) ** 2 - 1)
    return keys


def tree_groups(key: tuple) -> list:
    """The groups of a tree as child-mask signatures, left subtree first: () = every trade; (c,) one child mask; (c1, c2) an intersection.
    Child mask 2k = split k's left child, 2k + 1 its right."""
    ng, r, lo, ro = key
    if ng == 1:
        return [()]
    out = []
    for side, opt in ((2 * r, lo), (2 * r + 1, ro)):
        if opt == 0:
            out.append((side,))
        else:
            t = opt - 1
            out += [(side, 2 * t), (side, 2 * t + 1)]
    return out


def tree_desc(key: tuple, splits: list, rules: "list | None" = None) -> str:
    ng, r, lo, ro = key
    names = [s.name for s in splits]
    it = iter(rules or [])
    if ng == 1:
        return f"[one group -> {next(it, 'group')}]"

    def side(opt):
        if opt == 0:
            return next(it, "group")
        t = names[opt - 1]
        return f"({t} ? {next(it, 'group')} : {next(it, 'group')})"
    return f"{names[r]} ? {side(lo)} : {side(ro)}"


class Search:
    """The exhaustive search of one decision: the deduped splits, the trees that pass the floor on 2020, the unique groups and their
    membership on any block. Permuting whole context rows leaves every child size unchanged, so the tree list is built ONCE (SHUF re-scores)."""

    def __init__(self, dec: str, splits: list, vals20: dict, m: int):
        self.dec, self.splits, self.m = dec, splits, m
        self.s = len(splits)
        self.all_keys = enumerate_trees(self.s)
        self.uniq = {}
        self.tree_gids = {}
        for k in self.all_keys:
            self.tree_gids[k] = [self._gid(g) for g in tree_groups(k)]
        G20 = self.membership(vals20)
        sizes = G20.sum(axis=1)
        self.keys = [k for k in self.all_keys if k[0] == 1 or all(sizes[g] >= m for g in self.tree_gids[k])]      # one rule for all is always a tree
        self.n_keys = len(self.keys)
        self.TG = np.full((self.n_keys, 4), len(self.uniq), dtype=np.int64)            # padded with the zero sentinel
        for i, k in enumerate(self.keys):
            g = self.tree_gids[k]
            self.TG[i, :len(g)] = g
        self.sizes20 = sizes

    def _gid(self, sig: tuple) -> int:
        if sig not in self.uniq:
            self.uniq[sig] = len(self.uniq)
        return self.uniq[sig]

    def child_masks(self, vals: dict) -> np.ndarray:
        n = len(next(iter(vals.values()))) if vals else 0
        out = np.zeros((2 * self.s, n), dtype=bool)
        for k, s in enumerate(self.splits):
            lm = left_mask(s, vals[s.cid])
            out[2 * k], out[2 * k + 1] = lm, ~lm
        return out

    def membership(self, vals: dict) -> np.ndarray:
        """Unique groups x trades (bool) for the trades whose context values are `vals` ({cid: [value | None]})."""
        cm = self.child_masks(vals)
        n = cm.shape[1]
        G = np.zeros((len(self.uniq), n), dtype=bool)
        for sig, gi in self.uniq.items():
            if not sig:
                G[gi] = True
            elif len(sig) == 1:
                G[gi] = cm[sig[0]]
            else:
                G[gi] = cm[sig[0]] & cm[sig[1]]
        return G

    def fit(self, G20: np.ndarray, X20: np.ndarray, cols: "tuple | None" = None) -> dict:
        """The chosen tree on a 2020 CLOSE matrix X20 (trades x library rules): each group's rule = the first maximum in library order (within
        `cols`); the tree with the most CLOSE trades, the first in the canonical order on a tie (C7)."""
        R_ = X20.shape[1]
        cols = tuple(range(R_)) if cols is None else tuple(cols)
        Xc = X20[:, cols].astype(np.int64)
        CNT = G20.astype(np.int64) @ Xc
        best = np.concatenate([CNT.max(axis=1), [0]]) if CNT.shape[1] else np.zeros(len(self.uniq) + 1, dtype=np.int64)
        arg = CNT.argmax(axis=1)
        scores = best[self.TG].sum(axis=1)
        i = int(np.argmax(scores))
        key = self.keys[i]
        gids = self.tree_gids[key]
        return dict(key=key, gids=gids, rules=[cols[int(arg[g])] for g in gids], score20=int(scores[i]), tree_index=i)

    def fit_best_single(self, X20: np.ndarray, cols: "tuple | None" = None) -> dict:
        """The no-split tree (BEST): the rule with the most CLOSE trades on 2020, the first in library order on a tie."""
        cols = tuple(range(X20.shape[1])) if cols is None else tuple(cols)
        sums = X20[:, cols].sum(axis=0)
        r = cols[int(np.argmax(sums))]
        return dict(key=(1, -1, 0, 0), gids=[self.uniq[()]], rules=[r], score20=int(sums.max()), tree_index=0)


def assign_rules(fit: dict, G: np.ndarray) -> np.ndarray:
    """Per trade: the rule column of ITS group (every trade sits in exactly one group of the tree: asserted)."""
    n = G.shape[1]
    out = np.full(n, -1, dtype=np.int64)
    for g, r in zip(fit["gids"], fit["rules"]):
        sel = G[g]
        if (out[sel] >= 0).any():
            raise GuardStop("a trade sits in two groups of one tree")
        out[sel] = r
    if (out < 0).any():
        raise GuardStop("a trade sits in no group of the tree")
    return out


def close_of(fit: dict, G: np.ndarray, X: np.ndarray) -> np.ndarray:
    a = assign_rules(fit, G)
    return X[np.arange(X.shape[0]), a] if X.shape[0] else np.zeros(0, dtype=bool)


def map_share(fit: dict, G: np.ndarray, X: np.ndarray) -> float:
    c = close_of(fit, G, X)
    return share(int(c.sum()), len(c))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# "CLOSE TO" (§4a): the convention-aware widening per Fire, the frozen `bucket` on the widened window; G3's independent derivation
# ═════════════════════════════════════════════════════════════════════════════════════════════
def fire_side(f: Fire) -> "str | None":
    """'next' (booked on a later session than its event: jb > je), 'same', or None (never fired / abstains: no side). An R2 Fire takes the
    OUTER Fire's side."""
    if f.abstain or f.jb is None or f.je is None:
        return None
    return "next" if f.jb > f.je else "same"


def tol_ab(tol: str, side: "str | None") -> tuple:
    """(a_f, b_f): the sessions a window widens before exit_lo / after exit_hi for a firing on `side` at tolerance `tol`."""
    if side is None or tol == "pm0":
        return 0, 0
    if tol == "pm1c":
        return (0, 1) if side == "next" else (1, 0)
    k = {"pm1": 1, "pm2": 2}[tol]
    return k, k


def widened(lo: int, hi: int, a: int, b: int, J_tail: int) -> tuple:
    return max(0, lo - a), min(hi + b, int(J_tail))


def close_bucket(f: Fire, lo: int, hi: int, tol: str, J_tail: int) -> str:
    """The frozen `bucket` on the firing's widened window (first firing only; the window clipped at offset 0 and J_tail)."""
    a, b = tol_ab(tol, fire_side(f))
    lo_f, hi_f = widened(lo, hi, a, b, J_tail)
    return mix.bucket(f, lo_f, hi_f)


def derive_widened(b0: str, f: Fire, lo: int, hi: int, tol: str, J_tail: int) -> str:
    """G3's INDEPENDENT derivation of the widened bucket from the ±0 bucket (from the tag file), jb, je and the missing sessions — the
    transitions §4a states, with its OWN window rule (never `tol_ab` / `fire_side` / the frozen `bucket` on the widened window), so a flipped
    side or a shifted booking in the path under test cannot pass. R2: both readings derived on the OUTER Fire's side, equal -> it, else
    UNRESOLVED (each reading's ±0 is the frozen bucket on [exit_lo, exit_hi])."""
    if f.abstain:
        return NE
    if f.alt is not None:
        inner = dataclasses.replace(f, alt=None)
        a = _derive_one(mix.bucket(inner, lo, hi), inner, lo, hi, tol, J_tail, f)
        bb = _derive_one(mix.bucket(f.alt, lo, hi), f.alt, lo, hi, tol, J_tail, f)
        return a if a == bb else UN
    return _derive_one(b0, f, lo, hi, tol, J_tail, f)


def _derive_window(tol: str, outer: Fire, lo: int, hi: int, J_tail: int) -> tuple:
    """§4a's windows, written out: ±1c = [exit_lo - 1, exit_hi] for a same-session booking, [exit_lo, exit_hi + 1] for a next-session one;
    ±k = [exit_lo - k, exit_hi + k]; a never-fired rule unwidened; clipped at offset 0 and J_tail."""
    if tol == "pm0" or outer.abstain or outer.jb is None or outer.je is None:
        return lo, hi
    if tol == "pm1c":
        return (lo, min(hi + 1, int(J_tail))) if outer.jb > outer.je else (max(0, lo - 1), hi)
    k = 1 if tol == "pm1" else 2
    return max(0, lo - k), min(hi + k, int(J_tail))


def _derive_one(b0: str, f: Fire, lo: int, hi: int, tol: str, J_tail: int, outer: Fire) -> str:
    if f.abstain:
        return NE
    lo_f, hi_f = _derive_window(tol, outer, lo, hi, J_tail)
    if (lo_f, hi_f) == (lo, hi):
        return b0
    if f.jb is None:
        return UN if (b0 == UN or any(s <= hi_f for s in f.missing)) else NE
    miss_before_event = any(s < f.je for s in f.missing)
    if b0 == EX:
        return EX
    if b0 == ME:
        # an early booking moves inside only when the widened start reaches it
        return EX if (f.jb >= lo_f and not f.bd_unres and not miss_before_event) else ME
    if b0 == NE:
        # NEITHER at ±0: booked after exit_hi with no missing session up to exit_hi and no buy-day flag
        if f.jb <= hi_f:
            return UN if (f.bd_unres or miss_before_event) else EX
        return UN if (f.bd_unres or any(s <= hi_f for s in f.missing)) else NE
    # UNRESOLVED at ±0
    if f.bd_unres:
        return UN
    if f.jb > hi and f.jb <= hi_f and not miss_before_event:
        return EX                                   # §4a's one upgrade: the missing session lay at or after the event, before the booking
    return UN


def recross(mb, price_at, lo_m: int, hi_m: int, exist_m: int) -> bool:
    """B1 (C8): a minute t in (lo_m, hi_m] with high >= the level in force at t (existing at t), preceded by a minute u in [lo_m, t) whose
    close < that level."""
    m = mb.minute
    idx = np.flatnonzero((m > lo_m) & (m <= hi_m) & (m >= exist_m))
    for i in idx:
        L = price_at(int(m[i]))
        if L is None or not np.isfinite(L):
            continue
        if fnum(mb.h[i]) >= L:
            u = (m >= lo_m) & (m < m[i]) & (mb.c < L)
            if u.any():
                return True
    return False


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the rule-mix fires re-built through the frozen module (its tag stage's scoring, without its gates or files)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def rebuild_rule_mix(say, C: dict, M: dict) -> dict:
    """The frozen tag's records, ENTER scoring (the replayed draw stream, R12's returning windows) and STOP / EXIT tags, in its order; no
    gate, no file (G1 then holds every cell to the tag files)."""
    store, sight, guard = M["store"], M["sight"], fz.BarGuard(None)
    store.forbid = frozenset()                                    # guard (5): every block read once
    cs = fz.collision_summary(C, M.get("last_seen"))
    eb = mix.enter_blocks(C)
    ER, SR, drop_e, drop_s, cc = mix.build_records(C, M, store, guard)
    say(f"- records: ENTER {len(ER)} (dropped {dict(drop_e)}), STOP / EXIT {len(SR)} (dropped {dict(drop_s)}); the registered chain: "
        + ", ".join(f"{k} {v}" for k, v in sorted(cc.items())))
    fz.preload_sessions(store, list(SR.values()), -mix.WARMUP, lambda r: (r.exit_hi_j + mix.TAIL) if r.exit_hi_j is not None else r.last_j)
    has_mb = lambda b: b.eid in ER and ER[b.eid].mb is not None                       # noqa: E731
    orders = mix.enter_draw_orders(C, cs, has_mb)
    draws = mix.replay_draws(orders)
    scored = {}
    for stream, groups in orders.items():
        for _g, eids in groups:
            for eid in eids:
                scored[(stream, eid)] = mix.enter_one(ER[eid], draws[(stream, eid)], stream)
    for blk, spec in eb.items():
        stream = mix.stream_of_block(blk)
        for b in spec["tagged"] + [x for bs in spec["beside"].values() for x in bs]:
            r = ER.get(b.eid)
            if r is None or r.mb is None or (stream, b.eid) in scored or not mix.clocks_ok(b):
                continue
            u = fz.rng_for(mix.K1_KEY.format(eid=b.eid)).integers(0, 390, size=fz.RANDOM_LEVELS)
            scored[(stream, b.eid)] = mix.enter_one(r, u, stream)
    se = {}
    for eid, r in SR.items():
        se[eid] = mix.tag_se(r, M, store, sight)
        se[eid]["tagged"] = not se[eid]["status"]
    for e in scored.values():
        e["tag"] = mix.greedy_tag(e["real"], LIB["ENTER"])
        e["etag"] = mix.earliest_tag(e["real"], e["times"], LIB["ENTER"])
    say(f"- the rule-mix fires re-built: {len(scored)} ENTER windows, {sum(1 for t in se.values() if t['tagged'])} STOP / EXIT records tagged")
    return dict(ER=ER, SR=SR, scored=scored, se=se, eb=eb, cs=cs, store=store, sight=sight)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# G1 — identity: the re-built ±0 buckets (and every population column) equal the tag files cell for cell, parsed as the files serialize them
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        fa = math.nan if a is None else fnum(a)
        fb = math.nan if b is None else fnum(b)
        if np.isnan(fa) and np.isnan(fb):
            return True
        return abs(fa - fb) <= 1e-9 * max(1.0, abs(fa), abs(fb))
    return a == b


def enter_expected_row(b, e: dict, blk: str, tagged_eids: set) -> dict:
    """The frozen write_tables' ENTER row, typed."""
    row = dict(eid=b.eid, sym=b.sym, E=b.E, block=blk, dated=bool(b.dated), flicker=bool(b.flicker), flat_clock=b.flat_clock, first_clock=b.first_clock,
               tagged=b.eid in tagged_eids, tag=e["tag"], earliest_tag=e["etag"])
    for c in LIB["ENTER"]:
        row[f"{c}_bucket"], row[f"{c}_cross"] = e["real"][c], e["res"][c]["cross"]
    row.update(rprice_feasible=e["rprice"]["ex"], kprice_union=e["kprice"]["union"], shared_union=e["shared"].get("union"), shift_union=e["shift"]["union"])
    return row


def se_expected_row(t: dict, blk: str, dec: str) -> dict:
    """The frozen write_tables' STOP / EXIT row, typed."""
    r = t["rec"]
    d = dec.lower()
    row = dict(eid=r.b.eid, sym=r.b.sym, E=r.b.E, block=blk, dated=bool(r.b.dated), era=r.era, status=t["status"] or "scorable", room=t.get("room"),
               loser=t.get("loser"), loser_lo=t.get("loser_lo"), exit_lo_j=r.exit_lo_j, exit_hi_j=r.exit_hi_j, J_tail=int(t["prep"]["J_tail"]),
               fill=r.fill, fill_minute=r.fill_minute, fill_src=r.fill_src, stop=r.stop)
    if t.get("tagged"):
        for c in LIB[dec]:
            f = t[f"{d}_fires"][c]
            row[f"{c}_bucket"], row[f"{c}_first_j"], row[f"{c}_booked_j"], row[f"{c}_first_minute"] = t[f"{d}_real"][c], f.je, f.jb, f.m
        row.update(tag=t[f"{d}_tag"], earliest_tag=t[f"{d}_etag"], ctl_a_union=t[f"{d}_win_a"].get("union"), ctl_b_union=t[f"{d}_win_b"].get("union"),
                   rlevel_ex=t["rlevel"].get("ex"))
    return row


INT_SUFFIX = ("_cross", "_first_j", "_booked_j", "_first_minute")
INT_COLS = ("eid", "exit_lo_j", "exit_hi_j", "J_tail", "fill_minute")
BOOL_COLS = ("dated", "flicker", "tagged", "room", "loser", "loser_lo")
FLOAT_COLS = ("fill", "stop", "rprice_feasible", "kprice_union", "shared_union", "shift_union", "ctl_a_union", "ctl_b_union", "rlevel_ex")


def parse_cell(col: str, s: str):
    if col in INT_COLS or col.endswith(INT_SUFFIX):
        return cell_int(s)
    if col in BOOL_COLS:
        return cell_bool(s)
    if col in FLOAT_COLS:
        v = cell_float(s)
        return None if np.isnan(v) else v
    return s


def g1_identity(say, P: dict, rb: dict) -> dict:
    """G1: every cell of the three tag files re-read from the re-built fires; STOP on any difference. -> the ±0 bucket tables
    {decision: {eid: {rule: bucket}}} read FROM THE FILES (G3's ±0 input)."""
    eb, scored, se = rb["eb"], rb["scored"], rb["se"]
    bad, n = [], Counter()
    b0 = {d: {} for d in DECISIONS}
    t = read_tsv(TAG_FILE["ENTER"])
    for row in t.to_dict("records"):
        blk, eid = row["block"], int(row["eid"])
        e = scored.get((mix.stream_of_block(blk), eid))
        b = rb["ER"][eid].b if eid in rb["ER"] else None
        if e is None or b is None:
            bad.append(f"ENTER eid {eid}: not re-built")
            continue
        want = enter_expected_row(b, e, blk, {x.eid for x in eb[blk]["tagged"]})
        for col, v in want.items():
            if col not in row:
                bad.append(f"ENTER: column {col} absent from the tag file")
                continue
            got = parse_cell(col, row[col])
            if not _same(got, v):
                bad.append(f"ENTER eid {eid} {col}: file {row[col]!r} vs re-built {v!r}")
            n["ENTER"] += 1
        b0["ENTER"][eid] = {c: row[f"{c}_bucket"] for c in LIB["ENTER"]}
    for dec in ("STOP", "EXIT"):
        t = read_tsv(TAG_FILE[dec])
        for row in t.to_dict("records"):
            eid = int(row["eid"])
            tt = se.get(eid)
            if tt is None:
                bad.append(f"{dec} eid {eid}: not re-built")
                continue
            want = se_expected_row(tt, row["block"], dec)
            for col, v in want.items():
                if col not in row:
                    bad.append(f"{dec}: column {col} absent from the tag file")
                    continue
                got = parse_cell(col, row[col])
                if not _same(got, v):
                    bad.append(f"{dec} eid {eid} {col}: file {row[col]!r} vs re-built {v!r}")
                n[dec] += 1
            if tt.get("tagged"):
                b0[dec][eid] = {c: row[f"{c}_bucket"] for c in LIB[dec]}
    say(f"- G1 identity: the re-built cells vs the tag files — ENTER {n['ENTER']}, STOP {n['STOP']}, EXIT {n['EXIT']} cells: {len(bad)} differences")
    if bad:
        p = ctx_write_out("g1_failures.tsv", [dict(failure=x) for x in bad])
        raise GuardStop(f"G1: {len(bad)} cells differ from the tag files (first: {bad[0]}); rows -> {p}")
    return b0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the CLOSE matrices per decision, tolerance and block; the controls (§6c) per arm
# ═════════════════════════════════════════════════════════════════════════════════════════════
def enter_level_tools(rec) -> dict:
    """The frozen level prices (crossing, price_at) and existence minutes of one ENTER record (after enter_one set rec.levels)."""
    Lv = fz.intraday_levels(rec)
    out = {}
    for lv in LIB["ENTER"]:
        cross, price_at = fz.level_price_fn(lv, rec, Lv)
        out[lv] = (cross, price_at, fz.LEVEL_EXISTS.get(lv, 0))
    return out


def enter_close_row(e: dict, rec, tol: str) -> np.ndarray:
    """One ENTER window's CLOSE vector over the library at tolerance `tol`."""
    real = e["real"]
    out = np.array([real[c] == EX for c in LIB["ENTER"]], dtype=bool)
    if tol == "bracket":
        return out
    if tol == "B2":
        return out | np.array([e["res"][c]["verdict"] in ("HIT", "BALLPARK") for c in LIB["ENTER"]], dtype=bool)
    tools = enter_level_tools(rec)
    flat_m, first_m = e["flat_m"], e["first_m"]
    for i, c in enumerate(LIB["ENTER"]):
        if not out[i] and real[c] == ME:
            _cr, price_at, exist = tools[c]
            out[i] = recross(rec.mb, price_at, flat_m, first_m, exist)
    return out


def enter_controls(e: dict, rec, tol: str) -> dict:
    """The two ENTER arms at `tol`: k-price {draws x rules} (price i standing for rule i) and the shared window {draws x rules}; None when the
    shared window has no room."""
    flat_m, first_m, w = e["flat_m"], e["first_m"], e["width"]
    kx = np.asarray(e["kprice"]["codes"], dtype=bool).copy()
    kp = np.asarray(e["kprice"]["prices"], dtype=float)
    sh = e["shared"]
    sx = None if sh.get("no_room") else np.asarray(sh["codes"], dtype=bool).copy()
    if tol == "bracket":
        return dict(kprice=kx, shared=sx)
    mb, adr = rec.mb, rec.adr20
    if tol == "B2":
        for d in range(kp.shape[0]):
            for i in range(kp.shape[1]):
                if not kx[d, i]:
                    kx[d, i] = fz.range_verdict(mb, fnum(kp[d, i]), flat_m, first_m, adr)[0] in ("HIT", "BALLPARK")
        if sx is not None:
            tools = enter_level_tools(rec)
            for d, s in enumerate(sh["starts"]):
                s = int(s)
                for i, c in enumerate(LIB["ENTER"]):
                    if sx[d, i]:
                        continue
                    pr = tools[c][1](s + w)
                    if pr is None or not np.isfinite(pr):
                        continue
                    sx[d, i] = fz.range_verdict(mb, fnum(pr), s, s + w, adr)[0] in ("HIT", "BALLPARK")
        return dict(kprice=kx, shared=sx)
    # B1: the re-cross on every draw whose first crossing came at or before the window's start
    for d in range(kp.shape[0]):
        for i in range(kp.shape[1]):
            if kx[d, i]:
                continue
            p = fnum(kp[d, i])
            c = rev.first_cross(mb, p)
            if c is not None and c <= flat_m:
                kx[d, i] = recross(mb, (lambda m, _p=p: _p), flat_m, first_m, 0)
    if sx is not None:
        tools = enter_level_tools(rec)
        for d, s in enumerate(sh["starts"]):
            s = int(s)
            for i, c in enumerate(LIB["ENTER"]):
                if sx[d, i]:
                    continue
                cr, price_at, exist = tools[c]
                if cr is not None and cr <= s:
                    sx[d, i] = recross(mb, price_at, s, s + w, exist)
    return dict(kprice=kx, shared=sx)


def touch_path_to(rec, store, j_to: int) -> dict:
    """The frozen touch_path walked to session j_to (the frozen function on a copy whose exit_hi is j_to; the draws are untouched)."""
    r2 = dataclasses.replace(rec, exit_hi_j=int(j_to))
    return mix.touch_path(r2, store)


def se_close_rows(t: dict, dec: str, tol: str) -> tuple:
    """(CLOSE vector over the library, the widened bucket of each rule) of one STOP / EXIT trade at `tol`."""
    r = t["rec"]
    lo, hi, J = r.exit_lo_j, r.exit_hi_j, int(t["prep"]["J_tail"])
    fires = t[f"{dec.lower()}_fires"]
    bk = {c: close_bucket(fires[c], lo, hi, tol, J) for c in LIB[dec]}
    return np.array([bk[c] == EX for c in LIB[dec]], dtype=bool), bk


def se_window_codes(f: Fire, starts: np.ndarray, width: int, tol: str, J_tail: int, frames: bool) -> tuple:
    """Control (a) on one rule at `tol`: every placement [s, s + width - 1] widened per this firing (a_f, b_f), clipped at 0 and J_tail, through
    the frozen bucket_vec. -> (codes per placement, clipped flags)."""
    a, b = tol_ab(tol, fire_side(f))
    starts = np.asarray(starts, dtype=np.int64)
    out = np.zeros(len(starts), dtype=np.int8)
    clipped = starts < a
    for i, s in enumerate(starts):
        lo_s, hi_s = widened(int(s), int(s) + width - 1, a, b, J_tail)
        out[i] = mix.bucket_vec(f, np.array([lo_s]), hi_s - lo_s + 1, frames)[0]
    return out, clipped


def se_controls(t: dict, dec: str, tol: str, store, cache: "dict | None" = None) -> dict:
    """The three STOP / EXIT arms of one trade at `tol`: control (a) per mode {placements x rules} (EX flags) and the clipped flags; the random
    level's single-level EX flags (200) and its k-level EX matrix (200 x k); None on no room."""
    r = t["rec"]
    lo, hi, J = r.exit_lo_j, r.exit_hi_j, int(t["prep"]["J_tail"])
    fires = t[f"{dec.lower()}_fires"]
    win = mix.random_windows(r, J, "a")
    starts, w = win["starts"], win["width"]
    out = {}
    for arm, frames in (("a_frames", True), ("a_noframes", False)):
        P = np.zeros((len(starts), len(LIB[dec])), dtype=bool)
        CL = np.zeros((len(starts), len(LIB[dec])), dtype=bool)
        for i, c in enumerate(LIB[dec]):
            codes, clipped = se_window_codes(fires[c], starts, w, tol, J, frames)
            P[:, i] = codes == CODE_OF[EX]
            CL[:, i] = clipped
        out[arm] = P
        out[arm + "_clipped"] = CL
    out["starts"] = np.asarray(starts)
    rl = t["rlevel"]
    if rl.get("no_room"):
        out["rlevel1"], out["rlevelk"] = None, None
        return out
    a, b = tol_ab(tol, "same")
    lo_f, hi_f = widened(lo, hi, a, b, J)
    cache = {} if cache is None else cache
    pk = ("path", r.b.eid, hi_f)
    if pk not in cache:
        cache[pk] = touch_path_to(r, store, hi_f)
    path = cache[pk]
    out["rlevel1"] = mix.touch_buckets_vec(path, rl["levels"], lo_f, hi_f) == CODE_OF[EX]
    k = len(LIB[dec])
    lkk = ("lk", r.b.eid, k)
    if lkk not in cache:
        cache[lkk] = mix.random_level_draws(r, mix.RLEVEL_K_KEY, k)              # the k-level draws are tolerance-free: drawn once
    lk = cache[lkk]
    out["rlevelk"] = np.column_stack([mix.touch_buckets_vec(path, lk[:, i], lo_f, hi_f) == CODE_OF[EX] for i in range(k)])
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# SW — the 10/20 switch (§5e), a COMPOSITE rule through the frozen `_daily_first` (G4: at the cut -inf / +inf it IS M-3 / M-4)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def switch_fire(rec, ctx, smas: dict, cut: float, variant: str) -> Fire:
    """SW-a (far -> the 10-day) / SW-b (far -> the 20-day): on held session j the trail in force is chosen by the distance of close_{j-1}
    above the 20-day (C13); the first close below it fires, booked on its own session (as M-3 / M-4)."""
    c = rec.bars.c
    adr = fnum(rec.adr20)

    def far(j: int) -> bool:
        kp = rec.bar_at(j - 1)
        dist = -math.inf
        if kp is not None:
            s20, cp = fnum(smas[20][kp]), fnum(c[kp])
            if np.isfinite(s20) and cp > 0 and adr > 0:
                dist = (cp - s20) / (adr * cp)
        return dist >= cut

    def pred(j, k):
        n = 10 if (far(j) == (variant == "a")) else 20
        return np.isfinite(smas[n][k]) and fnum(c[k]) < fnum(smas[n][k])
    return mix._daily_first(rec, ctx, 0, pred)


def g4_switch(say, se: dict, store) -> None:
    """G4: SW at the cut -inf equals M-3 (SW-a) / M-4 (SW-b), at +inf the reverse, Fire for Fire on every tagged STOP / EXIT record."""
    bad, n = [], 0
    for eid, t in se.items():
        if not t.get("tagged"):
            continue
        r = t["rec"]
        ctx = mix.make_ctx(r, t["prep"], store)
        smas = fz.smas_for(r.bars)
        f = t["exit_fires"]
        for cut, want_a, want_b in ((-math.inf, "M-3", "M-4"), (math.inf, "M-4", "M-3")):
            for variant, want in (("a", want_a), ("b", want_b)):
                n += 1
                got = switch_fire(r, ctx, smas, cut, variant)
                if got != f[want]:
                    bad.append(f"eid {eid} SW-{variant} at {cut}: {got} vs {want} {f[want]}")
    say(f"- G4 the 10/20 switch at the extreme cuts: {n} (trade, reading, cut) firings vs M-3 / M-4: {len(bad)} differences")
    if bad:
        raise GuardStop(f"G4: {len(bad)} SW firings differ from M-3 / M-4 at the extreme cuts (first: {bad[0]})")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the comparators and the controls (§6), the labels (§7a), the intervals (§5d)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def per_leaf_chance(rules: np.ndarray, chance: np.ndarray) -> float:
    """(c-1): each trade's chance share under ITS OWN group's rule (never the pooled best rule); trades without room (NaN) out of the mean."""
    if not len(rules):
        return math.nan
    v = chance[np.arange(len(rules)), rules]
    v = v[np.isfinite(v)]
    return fnum(np.mean(v)) if len(v) else math.nan


def shuffled(n: int, dec: str, block: str, p: int) -> np.ndarray:
    """The p-th permutation of a block's trades (whole context rows move; the CLOSE matrix never does)."""
    return fz.rng_for(PERM_KEY.format(decision=dec, block=block, p=p)).permutation(n)


def permute_vals(vals: dict, perm: np.ndarray) -> dict:
    return {c: [v[i] for i in perm] for c, v in vals.items()}


def paired_interval(diff: np.ndarray, dec: str, block: str, line: str, boots: "int | None" = None) -> tuple:
    """The paired bootstrap of a per-trade difference (the map, the groups and BEST held FIXED: a resample re-scores, it does not re-search).
    -> (mean, lo, hi) in shares."""
    boots = BOOTS if boots is None else boots
    n = len(diff)
    if not n:
        return math.nan, math.nan, math.nan
    ms = np.empty(boots)
    for r_ in range(boots):
        idx = fz.rng_for(BOOT_KEY.format(decision=dec, block=block, line=line, r=r_)).integers(0, n, n)
        ms[r_] = diff[idx].mean()
    return fnum(diff.mean()), fnum(np.percentile(ms, 2.5)), fnum(np.percentile(ms, 97.5))


def mcnemar(a: np.ndarray, b: np.ndarray) -> tuple:
    """(MAP close & BEST not, BEST close & MAP not, the exact two-sided binomial p)."""
    x, y = int((a & ~b).sum()), int((b & ~a).sum())
    n = x + y
    if n == 0:
        return x, y, 1.0
    k = min(x, y)
    p = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return x, y, min(1.0, 2 * p)


def context_helps(m: float, best: float, shuf: float) -> bool:
    if not all(np.isfinite(v) for v in (m, best, shuf)):
        return False
    return tenths(m) - tenths(best) >= tenths(MARGIN) and tenths(m) - tenths(shuf) >= tenths(MARGIN)


def beats_chance(m: float, best: float, arms: dict) -> bool:
    """§7a on GAINS, arm by arm, on the printed one-decimal percentages: for EVERY arm, (MAP - BEST) - ((c-1)(MAP) - (c-1)(BEST)) >= 10.0
    AND (MAP - BEST) - ((c-2)(MAP) - (c-2)(BEST)) >= 10.0. arms = {arm: (c1_map, c1_best, c2_map, c2_best)}."""
    if not (np.isfinite(m) and np.isfinite(best)) or not arms:
        return False
    g = tenths(m) - tenths(best)
    for c1m, c1b, c2m, c2b in arms.values():
        if not all(np.isfinite(v) for v in (c1m, c1b, c2m, c2b)):
            return False
        if g - (tenths(c1m) - tenths(c1b)) < tenths(MARGIN) or g - (tenths(c2m) - tenths(c2b)) < tenths(MARGIN):
            return False
    return True


def summary_label(helps: bool, chance: bool) -> str:
    if helps and chance:
        return "context map"
    if helps:
        return "context helps, chance too"
    return "no context gain"


def net_gain(m, best, cm, cb_) -> float:
    if not all(np.isfinite(v) for v in (m, best, cm, cb_)):
        return math.nan
    return ((tenths(m) - tenths(best)) - (tenths(cm) - tenths(cb_))) / 10.0


def sign_of(x: float) -> str:
    if not np.isfinite(x):
        return "-"
    t = tenths(abs(x)) if x >= 0 else -tenths(abs(x))
    return "+" if t > 0 else ("0" if t == 0 else "−")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the fixed maps (§5e): HW-E, HW-S, HW-X, HW-X' — no search; a fixed map is a one-split "fit"
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class FixedMap:
    name: str
    cid: str
    cut: float
    left_rule: str
    right_rule: str
    missing_left: bool
    source: str

    def rules(self, vals: list) -> np.ndarray:
        """Per trade: the rule column (library index)."""
        lib = LIB_INDEX[self.decision]
        return np.array([lib[self.left_rule] if ((fnum(x) <= self.cut) if x is not None else self.missing_left) else lib[self.right_rule] for x in vals], dtype=np.int64)

    @property
    def decision(self) -> str:
        return {"C-E1": "ENTER", "C-S1": "STOP", "C-X1": "EXIT"}[self.cid]


LIB_INDEX = {d: {c: i for i, c in enumerate(LIB[d])} for d in DECISIONS}


def hw_maps(dec: str, vals20: dict, medians: dict) -> list:
    """His words' own maps, fixed now (§5e): the cut = the 2020 median where his words give no number (C-E1, C-X1), his 1.0 on C-S1,
    Apollo's 0.0479 on HW-X'. A missing value follows the larger side (C4)."""
    def mk(name, cid, cut, lrule, rrule, src):
        return FixedMap(name, cid, fnum(cut), lrule, rrule, missing_side(vals20[cid], fnum(cut)), src)
    if dec == "ENTER":
        return [mk("HW-E", "C-E1", medians["C-E1"], "L8", "L1", "C-E1 above the 2020 median -> L1, else L8 (l.1712-1713)")] if medians.get("C-E1") is not None else []
    if dec == "STOP":
        return [mk("HW-S", "C-S1", C_S1_CAP, "S1-T", "S4-T", "C-S1 <= 1.0 -> S1-T, else S4-T (l.1943)")]
    out = []
    if medians.get("C-X1") is not None:
        out.append(mk("HW-X", "C-X1", medians["C-X1"], "M-4", "M-3", "C-X1 above the 2020 median -> M-3 (the 10-day), else M-4 (l.2046-2047)"))
    out.append(mk("HW-X'", "C-X1", HWX_PRIME_CUT, "M-4", "M-3", "C-X1 > 0.0479 (TRAIL_SPEED_ADR_CUT) -> M-3, else M-4"))
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the constants the dry run prints and the freeze pins (§3: the cut VALUES, the HW medians, the SW cut, each split's missing side, the tree order)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def constants_of(D: dict) -> dict:
    """{pin name: printed value} from a decision table built by `decision_setup` (every decision)."""
    out = {}
    for dec in DECISIONS:
        d = D[dec]
        for (cid, tok), v in sorted(d["cuts"].items(), key=lambda kv: SPLIT_ORDER[dec].index(kv[0])):
            if tok in ("T1", "T2"):
                out[f"ctx_const_{dec}_{cid}_{tok}"] = fmt_val(v)
        for cid, v in sorted(d["medians"].items()):
            out[f"ctx_const_{dec}_{cid}_median"] = fmt_val(v)
        for s in d["splits_all"]:                                            # C4: each split's missing side, fixed per split (F10)
            out[f"ctx_const_{dec}_{s.cid}_{s.token}_missing_left"] = str(bool(s.missing_left))
        out[f"ctx_const_{dec}_floor_m"] = str(d["m"])
        out[f"ctx_const_{dec}_tree_order"] = hashlib.sha256("\n".join(d["tree_listing"]).encode("utf-8")).hexdigest()
    return out


def tree_listing(search: Search) -> list:
    return [f"{i}: {k} {tree_desc(k, search.splits)}" for i, k in enumerate(search.keys)]


def decision_setup(dec: str, P: dict, vals: dict) -> dict:
    """The outcome-free half of one decision: the 2020 values, the cuts, the splits (dedupe), the floor, the search, the medians."""
    pop = P[dec]["scorable"]
    v20 = {c: [vals[tr.eid][c][0] for tr in pop["2020"]] for c in CIDS[dec]}
    cuts = cut_values(dec, v20)
    splits_all = make_splits(dec, v20, cuts)
    kept, dropped = dedupe_splits(splits_all, v20)
    m = floor_m(len(pop["2020"]))
    search = Search(dec, kept, v20, m)
    medians = {}
    if dec == "ENTER":
        medians["C-E1"] = median_cut(v20["C-E1"])
    if dec == "EXIT":
        medians["C-X1"] = median_cut(v20["C-X1"])
    out = dict(dec=dec, v20=v20, cuts=cuts, splits_all=splits_all, splits=kept, dropped=dropped, m=m, search=search, medians=medians,
               tree_listing=tree_listing(search))
    if dec == "EXIT":
        out["sw_cut"] = cuts[("C-X3", "T2")]
    return out


def block_vals(dec: str, trades: list, vals: dict) -> dict:
    return {c: [vals[tr.eid][c][0] for tr in trades] for c in CIDS[dec]}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run's claims against THIS doc (anchors resolve into THIS doc; every mismatch collected, STOP at the end)
# ═════════════════════════════════════════════════════════════════════════════════════════════
class CtxClaims(mix.MixClaims):
    """The rule-mix's claim printer bound to THIS doc's path (never its default: the rule-mix doc)."""

    def __init__(self, say, doc: str = None):
        super().__init__(say, doc=doc or DOC)


EXPECT = {   # key: (anchor in THIS doc, the doc's value, label)
    "enter_2020": ("| 2020 | **88** (31 + 57) | 26 / 3 / 2 |", "88 (31 + 57); 26 / 3 / 2", "ENTER 2020: n (dated + undated); breakout / EP / both within dated"),
    "enter_2122": ("| ENTER | 2021-22 | **60** (20 + 40) | 15 / 4 / 1 |", "60 (20 + 40); 15 / 4 / 1", "ENTER 2021-22: n (dated + undated); setup within dated"),
    "enter_untouched": ("| ENTER | untouched | **9** (0 + 9) |", "9 (0 + 9)", "ENTER untouched: n (dated + undated)"),
    "enter_beside": ("undated flickers 30 / 19 / 7", "30 / 19 / 7", "ENTER beside: the undated flickers by block"),
    "stop_2020": ("**139** (48 + 91) | 39 / 6 / 3", "139 (48 + 91); 39 / 6 / 3", "STOP 2020 losers with room: n; setup within dated"),
    "stop_2122": ("**116** (40 + 76) | 32 / 8 / 0", "116 (40 + 76); 32 / 8 / 0", "STOP 2021-22: n; setup within dated"),
    "stop_untouched": ("**12** (4 + 8) | 3 / 1 / 0", "12 (4 + 8); 3 / 1 / 0", "STOP untouched: n; setup within dated"),
    "exit_2020": ("**333** (122 + 211) | 103 / 13 / 6", "333 (122 + 211); 103 / 13 / 6", "EXIT 2020 with room: n; setup within dated"),
    "exit_2122": ("**229** (79 + 150) | 62 / 16 / 1", "229 (79 + 150); 62 / 16 / 1", "EXIT 2021-22: n; setup within dated"),
    "exit_untouched": ("**44** (16 + 28) | 9 / 7 / 0", "44 (16 + 28); 9 / 7 / 0", "EXIT untouched: n; setup within dated"),
    "noroom_exit": ("every other `no_room` trade in control (a): 97 / 92 / 28", "97 / 92 / 28", "EXIT scorable trades without room in control (a), by block"),
    "noroom_stop": ("EXIT, 56 / 57 / 14 STOP losers", "56 / 57 / 14", "STOP losers without room in control (a), by block"),
    "ep_small": ("(2020: 5 of 31 dated ENTER windows, 19 of 122 dated exits", "5 of 31 / 19 of 122", "EP (EP + both) among the 2020 dated ENTER windows / EXIT trades"),
    "flat_before_0935": ("(17 of 88 scorable 2020 brackets and 20 of 60 on 2021-22 have flat_clock before 09:35, 1 of 9", "17 of 88 / 20 of 60 / 1 of 9",
                         "ENTER scorable brackets with flat_clock before 09:35, by block"),
    "flat_0930": ("(a 09:30 flat_clock: 0 / 7 / 0 by block, from the clocks)", "0 / 7 / 0", "ENTER scorable brackets flat at 09:30 (C-E1 MISSING by construction)"),
    "e1_missing": ("C-E1 missing on 0 / 7 / 0 (the 09:30 flat clocks)", "0 / 7 / 0", "C-E1 MISSING by block (computed from the decision-time views)"),
    "open_fills": ("211 of the 333 2020 EXIT trades", "211 of 333 / 150 of 229 / 28 of 44", "EXIT trades with room filled at the open (fill_src open = every undated row), by block"),
    "stop_undated_91": ("the 91 undated of 139 2020 STOP losers", "91 of 139", "STOP 2020 losers filled at the open (undated)"),
    "s1_missing": ("C-S1 missing on 91 of 139 / 76 of 116 / 8 of 12 STOP losers", "91 of 139 / 76 of 116 / 8 of 12", "C-S1 MISSING by block (computed)"),
    "s1_tertile_ranks": ("losers: T1 / T2 are the 16th / 32nd of 48", "16th / 32nd of 48", "C-S1's tertile ranks on the 2020 defined rows"),
    "orh5_too_wide": ("flagged 43 ORH5 fills (all blocks; 18 of the 333 2020 EXIT trades with room by `fill_src`)", "43; 18 of 333",
                      "fill_src orh5_too_wide over every STOP / EXIT record; among the 333 2020 EXIT trades with room"),
    "one_session_exit": ("One-session sell windows are 231 of 333 EXIT trades on 2020 and 165 of 229 on", "231 of 333 / 165 of 229", "one-session sell windows, EXIT 2020 / 2021-22"),
    "one_session_stop": ("2021-22 (108 of 139 and 80 of 116 STOP losers)", "108 of 139 / 80 of 116", "one-session sell windows, STOP 2020 / 2021-22"),
    "exit_lo_quartiles": ("3, quartiles 1-9, from the offsets", "3 / 1-9", "exit_lo_j median / quartiles (EXIT 2020)"),
    "exit_lo_one": ("(exit_lo_j = 1 on 102 of the 333 2020 EXIT trades", "102 of 333", "EXIT 2020 trades with exit_lo_j = 1"),
    "bracket_median": ("in-session bracket median 27 minutes on 2020, 46 on 2021-22, non-flicker windows", "27 / 46",
                       "the median in-session bracket width (minutes), non-flicker scorable windows, 2020 / 2021-22"),
    "floor_m": ("ENTER 15, STOP 15, EXIT 34.**", "15 / 15 / 34", "the floor m = max(15, ceil(0.10 x n_2020)) per decision"),
    "n_splits": ("Candidate splits (the setup is out, §13 Q5): ENTER 4 (C-E1 × 2, C-E2, C-E3), STOP 6 (C-S1 × 3, C-S2 × 2,", "4 / 6 / 7",
                 "candidate splits per decision (before the dedupe)"),
    "n_trees": ("1 + s + s·((s + 1)² − 1) = **101 / 295 / 449**", "101 / 295 / 449", "trees before the dedupe and the floor (enumerated)"),
    "feb_may": ("(2020 buys Feb-May: 30 of 88 by date)", "30 of 88", "ENTER 2020 scorable buys dated February-May"),
    "margin_6": ("ENTER scores 60 trades on 2021-22: a 10-point margin is 6 trades", "60; 6", "ENTER 2021-22 n; a 10-point margin in trades"),
    "fetch_pairs": ("19,470 pairs", "19470", "the intraday fetch list's pairs"),
    "k_levels": ("`mix|rlevel|{eid}|{d}|{i}`, k = 15", "15 / 12", "the k-level draws: k = the library size, STOP / EXIT"),
    "speed_cut": ("(`TRAIL_SPEED_ADR_CUT = 0.0479`, `consolidation_breakout.py` l.186)", "0.0479", "Apollo's TRAIL_SPEED_ADR_CUT in consolidation_breakout.py"),
}
NOTES = {   # printed, never stopping: the doc's "about" numbers and expectations
    "s1_wide": ("its wide child on 2020 STOP losers is about 18 or fewer", "<= 18 (expected under the floor of 15)", "C-S1 > 1.0 among the 2020 STOP losers"),
    "others_missing": ("the others near zero (the dry run counts them, outcome-free)", "near zero", "every other context's MISSING count"),
}


def _ofn(k: int, n: int) -> str:
    return f"{k} of {n}"


def dry_claims(say, claim, P: dict, vals: dict, D: dict, recs_se: dict) -> None:
    """Every count of the doc the dry run can reproduce from the populations and the decision-time contexts."""
    def ck(key, mine):
        a, v, lab = EXPECT[key]
        return claim(a, f"{key}: {lab}", v, mine)

    def note(key, mine):
        a, v, lab = NOTES[key]
        return claim(a, f"{key}: {lab}", v, mine, note=True)
    sc = {d: P[d]["scorable"] for d in DECISIONS}

    def setup_split(trs):
        dt = [t for t in trs if t.dated]
        return f"{sum(1 for t in dt if t.setup == 'breakout')} / {sum(1 for t in dt if t.setup == 'EP')} / {sum(1 for t in dt if t.setup == 'both')}"

    def nd(trs):
        return f"{len(trs)} ({sum(1 for t in trs if t.dated)} + {sum(1 for t in trs if not t.dated)})"
    ck("enter_2020", f"{nd(sc['ENTER']['2020'])}; {setup_split(sc['ENTER']['2020'])}")
    ck("enter_2122", f"{nd(sc['ENTER']['2021-22'])}; {setup_split(sc['ENTER']['2021-22'])}")
    ck("enter_untouched", nd(sc["ENTER"]["untouched"]))
    ck("enter_beside", " / ".join(str(len(P["ENTER"]["beside"][b])) for b in BLOCKS))
    for dec, keys in (("STOP", ("stop_2020", "stop_2122", "stop_untouched")), ("EXIT", ("exit_2020", "exit_2122", "exit_untouched"))):
        for key, blk in zip(keys, BLOCKS):
            ck(key, f"{nd(sc[dec][blk])}; {setup_split(sc[dec][blk])}")
    # no_room counts: the scorable rows (STOP: losers) whose room is False
    nr = {}
    for dec in ("STOP", "EXIT"):
        t = read_labels(dec)
        t = t[t["status"] == "scorable"]
        if dec == "STOP":
            t = t[t["loser"] == "True"]
        nr[dec] = " / ".join(str(int(((t["block"] == b) & (t["room"] == "False")).sum())) for b in BLOCKS)
    ck("noroom_exit", nr["EXIT"])
    ck("noroom_stop", nr["STOP"])
    ep = lambda trs: sum(1 for t in trs if t.dated and t.setup in ("EP", "both"))           # noqa: E731
    e20d = [t for t in sc["ENTER"]["2020"] if t.dated]
    x20d = [t for t in sc["EXIT"]["2020"] if t.dated]
    ck("ep_small", f"{_ofn(ep(e20d), len(e20d))} / {_ofn(ep(x20d), len(x20d))}")
    ck("flat_before_0935", " / ".join(_ofn(sum(1 for t in sc["ENTER"][b] if t.flat_m < E1_MINUTE), len(sc["ENTER"][b])) for b in BLOCKS))
    ck("flat_0930", " / ".join(str(sum(1 for t in sc["ENTER"][b] if t.flat_m == 0)) for b in BLOCKS))
    ck("e1_missing", " / ".join(str(sum(1 for t in sc["ENTER"][b] if vals["ENTER"][t.eid]["C-E1"][0] is None)) for b in BLOCKS))
    ck("open_fills", " / ".join(_ofn(sum(1 for t in sc["EXIT"][b] if t.fill_src == "open"), len(sc["EXIT"][b])) for b in BLOCKS))
    s20 = sc["STOP"]["2020"]
    ck("stop_undated_91", _ofn(sum(1 for t in s20 if t.fill_src == "open" and not t.dated), len(s20)))
    ck("s1_missing", " / ".join(_ofn(sum(1 for t in sc["STOP"][b] if vals["STOP"][t.eid]["C-S1"][0] is None), len(sc["STOP"][b])) for b in BLOCKS))
    nd20 = sum(1 for t in s20 if vals["STOP"][t.eid]["C-S1"][0] is not None)
    ck("s1_tertile_ranks", f"{ceil_div(nd20, 3)}th / {ceil_div(2 * nd20, 3)}nd of {nd20}")
    allsrc = read_labels("STOP")["fill_src"]
    ck("orh5_too_wide", f"{int((allsrc == 'orh5_too_wide').sum())}; {_ofn(sum(1 for t in sc['EXIT']['2020'] if t.fill_src == 'orh5_too_wide'), len(sc['EXIT']['2020']))}")
    one = lambda trs: sum(1 for t in trs if t.window_w == 1)                                # noqa: E731
    ck("one_session_exit", f"{_ofn(one(sc['EXIT']['2020']), len(sc['EXIT']['2020']))} / {_ofn(one(sc['EXIT']['2021-22']), len(sc['EXIT']['2021-22']))}")
    ck("one_session_stop", f"{_ofn(one(sc['STOP']['2020']), len(sc['STOP']['2020']))} / {_ofn(one(sc['STOP']['2021-22']), len(sc['STOP']['2021-22']))}")
    lo = np.array([t.exit_lo_j for t in sc["EXIT"]["2020"]], dtype=float)
    q = np.percentile(lo, [25, 50, 75]) if len(lo) else [math.nan] * 3
    ck("exit_lo_quartiles", f"{q[1]:g} / {q[0]:g}-{q[2]:g}")
    ck("exit_lo_one", _ofn(sum(1 for t in sc["EXIT"]["2020"] if t.exit_lo_j == 1), len(sc["EXIT"]["2020"])))
    wid = lambda b: [t.width for t in sc["ENTER"][b] if not t.flicker]                     # noqa: E731
    ck("bracket_median", f"{np.median(wid('2020')):g} / {np.median(wid('2021-22')):g}" if wid("2020") and wid("2021-22") else "-")
    ck("floor_m", " / ".join(str(D[d]["m"]) for d in DECISIONS))
    ck("n_splits", " / ".join(str(len(SPLIT_ORDER[d])) for d in DECISIONS))
    ck("n_trees", " / ".join(str(len(enumerate_trees(len(SPLIT_ORDER[d])))) for d in DECISIONS))
    ck("feb_may", _ofn(sum(1 for t in sc["ENTER"]["2020"] if t.E[5:7] in ("02", "03", "04", "05")), len(sc["ENTER"]["2020"])))
    n22 = len(sc["ENTER"]["2021-22"])
    ck("margin_6", f"{n22}; {int(round(MARGIN * n22))}")
    with open(FETCH_LIST) as fh:
        ck("fetch_pairs", str(sum(1 for ln in fh if ln.strip())))
    ck("k_levels", f"{len(LIB['STOP'])} / {len(LIB['EXIT'])}")
    with open(TRAIL_SPEED_SOURCE, encoding="utf-8") as fh:
        m_ = re.search(r"^TRAIL_SPEED_ADR_CUT\s*=\s*([0-9.]+)", fh.read(), re.M)
    ck("speed_cut", m_.group(1) if m_ else "absent")
    wide = sum(1 for t in s20 if vals["STOP"][t.eid]["C-S1"][0] is not None and vals["STOP"][t.eid]["C-S1"][0] > C_S1_CAP)
    note("s1_wide", f"{wide}")
    others = []
    for dec in DECISIONS:
        for c in CIDS[dec]:
            if (dec, c) in (("ENTER", "C-E1"), ("STOP", "C-S1")):
                continue
            others.append(f"{c} " + "/".join(str(sum(1 for t in sc[dec][b] if vals[dec][t.eid][c][0] is None)) for b in BLOCKS))
    note("others_missing", "; ".join(others))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock, the ledger, the outputs, the pins — THIS read's own helpers (D4: the rule-mix's default to the RULE-MIX files)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def ctx_stage_outputs() -> list:
    """Files whose existence refuses --run: its printout, a STOPPED file, every file under out/."""
    out = [p for p in (STOPPED, P_RUN) if os.path.exists(p)]
    if os.path.isdir(OUT_DIR):
        out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR))
    return out


def ctx_any_stage_output() -> list:
    """Files whose existence refuses the dry run (it precedes the run): the run's outputs and the ledger."""
    return ctx_stage_outputs() + ([LEDGER] if os.path.exists(LEDGER) else [])


def ctx_dry_run_complete(path: str) -> bool:
    """THIS read's dry run by its own text: the last line DRY RUN COMPLETE (the frozen test on `path`), the first line this module's header,
    a `## RESULT: .. 0 MISMATCH` line — the rule-mix dry run (which also ends DRY RUN COMPLETE) does not count (D4)."""
    if not fz.dry_run_complete(path):
        return False
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    return bool(lines) and lines[0].startswith(DRY_HEADER) and any(DRY_RESULT_RX.match(ln) for ln in lines)


def dry_constants(path: str) -> dict:
    """The constants the dry run printed (`- ctx_const_<name>: <value>` lines of its CONSTANTS section)."""
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            m = CONST_RX.match(ln.rstrip("\n"))
            if m:
                out[m.group(1)] = m.group(2)
    return out


def carried_pins() -> dict:
    """Everything the rule-mix pinned (its own pins function on ITS doc by design — the carried pins of the read this one builds on), its doc
    body pins renamed `mix_doc_body_*`."""
    p = mix.mix_pins(include_outputs=True)                                  # mix-path-ok: the rule-mix's OWN pins, read for carrying
    out = {}
    for k, v in p.items():
        out[{"doc_body_freeze": "mix_doc_body_freeze", "doc_body": "mix_doc_body"}.get(k, k)] = v
    return out


def ctx_pins(include_outputs: bool = True) -> dict:
    p = carried_pins()
    for name, path in MIX_FILES.items():
        p[name] = sha(path) if os.path.exists(path) else "ABSENT"
    for name, path in CODE.items():
        p[name] = sha(path) if os.path.exists(path) else "ABSENT"
    if include_outputs:
        p["ctx_dryrun_printout"] = sha(P_DRY) if os.path.exists(P_DRY) else "ABSENT"
        p["ctx_ledger"] = sha(LEDGER) if os.path.exists(LEDGER) else "ABSENT"
        p.update(dry_constants(P_DRY))
    p.update(fz.fit_event_pins(RUN_EVENTS))
    p["doc_body_freeze"] = fz.pin_under_marker("doc_body_freeze", DOC) or fz.doc_body_sha(DOC)
    p["doc_body"] = fz.doc_body_sha(DOC)
    return p


def pin_value_under_marker(name: str, doc: str) -> "str | None":
    """The value written under the marker for a NON-hex pin (`- name: value`), or None."""
    with open(doc, "rb") as fh:
        raw = fh.read()
    sp = fz.marker_spans(raw)
    if len(sp) != 1:
        return None
    tail = raw[sp[0][1]:].decode("utf-8", errors="replace")
    m = re.search(rf"^\s*[-*]?\s*`?{re.escape(name)}`?\s*:\s*`?(\S+?)`?\s*$", tail, re.M)
    return m.group(1) if m else None


def ctx_lock() -> list:
    """Guard (1): the reasons --run refuses (empty = it may run)."""
    bad = []
    exo = ctx_stage_outputs()
    if exo:
        bad.append(f"run output(s) already on disk: {exo[:4]}{' ...' if len(exo) > 4 else ''} (the run runs once; after a STOP: --reset)")
    if not ctx_dry_run_complete(P_DRY):
        bad.append(f"THIS read's dry run has not COMPLETED ({os.path.basename(P_DRY)} missing, its last line is not DRY RUN COMPLETE, its first line is not "
                   f"'{DRY_HEADER}' or it carries no '## RESULT: .. 0 MISMATCH' line) — the rule-mix dry run does not count")
    ok, why = fz.freeze_state(DOC, FREEZE_BODIES)
    if not ok:
        bad.append("the freeze lock: " + why)
    p = ctx_pins()
    if not any(k.startswith("ctx_const_") for k in p):
        bad.append("no constant (cut value, median, tree order) from the dry run")
    miss = fz.freeze_missing(DOC, p)
    if miss:
        bad.append("pins not under the marker: " + ", ".join(miss[:8]) + (" ..." if len(miss) > 8 else ""))
    by_name = [k for k in mix.pins_missing_by_name(DOC, p) if k not in miss]
    if by_name:
        bad.append("pins whose OWN line under the marker does not carry their value (checked by name): " + ", ".join(by_name[:8])
                   + (" ..." if len(by_name) > 8 else ""))
    if fz.pin_under_marker("ctx_module", DOC) != sha(CODE["ctx_module"]):
        bad.append("the ctx_module pin under the marker is not this file")
    if os.path.exists(LEDGER):
        lb = fz.ledger_verify(LEDGER)
        if lb:
            bad.append("the ledger does not match the disk: " + "; ".join(lb))
    ub = fz.fit_events_undisclosed(DOC, RUN_EVENTS)
    if ub:
        bad.append("a reset's archived run is not disclosed (N2): " + "; ".join(ub))
    return bad


def ctx_g8(say, recs: list, label: str) -> None:
    """Guard (4) G8 before any number: this read's trade list per era through trade_impact.py (era A must read 0 / 0); files land in out/."""
    os.makedirs(OUT_DIR, exist_ok=True)
    say(f"\n## G8 — {label}: this read's own trade list through trade_impact.py (before any number)")
    for era in ("A", "B"):
        rows = [("ctx", r.b.ticker, r.b.E, r.exit_hi_j if r.exit_hi_j is not None else 0, 0.0) for r in recs if r.era == era]
        if not rows:
            say(f"- era {era}: no trade; G8 not run")
            continue
        path, txt = os.path.join(OUT_DIR, f"{label}_g8_{era}.tsv"), os.path.join(OUT_DIR, f"{label}_g8_{era}_impact.txt")
        rp.write_g8_file(path, rows)
        cmd = [sys.executable, TRADE_IMPACT, "--flags", G8_FILES[f"flags_{era}"], "--export", G8_FILES[f"export_{era}"], "--trades", path,
               "--label", era, "--kind", "r1", "--cell", "ctx", "--cutoff", CUT_B]
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


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run
# ═════════════════════════════════════════════════════════════════════════════════════════════
def dry_records(say, C: dict, M: dict) -> tuple:
    """The frozen record builders on the ENTER and STOP / EXIT buys (one calendar per record) — WITHOUT the chain (its day-0 walk reads post-fill
    minutes): the fill is the tag file's (a label column), asserted equal to the re-built one by G1 at --run."""
    store, guard = M["store"], fz.BarGuard(None)
    store.forbid = frozenset()
    eb = mix.all_enter_buys(C)
    sb = mix.all_se_buys(C)
    fz.preload_buy_days(store, [b for b in eb + sb if b.E <= CUT_B])
    ER, de = fz.recs_for(eb, M, store, guard, min_bars=fz.REC_MIN_BARS_ENTER)
    SR, ds = fz.recs_for(sb, M, store, guard)
    say(f"- records (no chain): ENTER {len(ER)} (dropped {dict(de)}), STOP / EXIT {len(SR)} (dropped {dict(ds)}); the buy-day minute files read "
        f"{sum(store.reads.values())}")
    return {r.b.eid: r for r in ER}, {r.b.eid: r for r in SR}


def all_vals(P: dict, ER: dict, SR: dict, spy_by_era: dict, check_full: bool) -> tuple:
    vals, fails = {}, []
    for dec in DECISIONS:
        trades = [t for b in BLOCKS for t in P[dec]["scorable"][b]] + [t for b in BLOCKS for t in P[dec]["beside"][b]]
        recs = ER if dec == "ENTER" else SR
        v, f = compute_contexts(dec, trades, recs, spy_by_era, check_full=check_full)
        vals[dec] = v
        fails += [(dec,) + x for x in f]
    return vals, fails


def print_contexts_and_splits(say, P: dict, vals: dict, D: dict) -> None:
    for dec in DECISIONS:
        d = D[dec]
        sc = P[dec]["scorable"]
        say(f"\n## {dec} — the contexts (decision-time views), their MISSING counts, the cuts, the splits, the trees")
        for c in CONTEXTS[dec]:
            say(f"- {c.cid} {c.name} | read at {c.read_at} | {c.cite}")
            for b in BLOCKS:
                vv = [vals[dec][t.eid][c.cid] for t in sc[b]]
                defined = [x for x, _r in vv if x is not None]
                why = Counter(r for x, r in vv if x is None)
                q = np.percentile(defined, [25, 50, 75]) if defined else [math.nan] * 3
                say(f"    {b}: n {len(vv)}, defined {len(defined)}, MISSING {len(vv) - len(defined)} " + (f"({dict(why)})" if why else "")
                    + (f"; quartiles {q[0]:.4g} / {q[1]:.4g} / {q[2]:.4g}" if defined and c.kind == "cont" else (f"; value 1 on {sum(1 for x in defined if x == 1.0)}" if defined else "")))
        say("- the cuts on the 2020 DEFINED values (T1 = the ceil(n/3)-th, T2 = the ceil(2n/3)-th smallest; ≤ goes left): " + "; ".join(
            f"{cid} {tok} = {fmt_val(v)}" for (cid, tok), v in d["cuts"].items() if tok != "bin"))
        if d["medians"]:
            say("- the HW medians (the ceil(n/2)-th 2020 defined value): " + "; ".join(f"{k} = {fmt_val(v)}" for k, v in d["medians"].items()))
        if dec == "EXIT":
            say(f"- the SW cut (T2 of C-X3) = {fmt_val(d['sw_cut'])}")
        say(f"- the candidate splits in §5c's order and their child sizes (left / right, missing included; missing -> the larger defined side):")
        for s in d["splits_all"]:
            sizes = []
            for b in BLOCKS:
                lm = left_mask(s, [vals[dec][t.eid][s.cid][0] for t in sc[b]])
                sizes.append(f"{b} {int(lm.sum())} / {int((~lm).sum())}")
            dropped = next((k for x, k in d["dropped"] if x is s), None)
            floor_ok = all(sz >= d["m"] for sz in (int(left_mask(s, d["v20"][s.cid]).sum()), int((~left_mask(s, d["v20"][s.cid])).sum())))
            say(f"    {s.order + 1}. {s.name} (cut {fmt_val(s.cut)}; missing -> {'left' if s.missing_left else 'right'}): " + " | ".join(sizes)
                + f"; 2020 floor {d['m']}: {'both children pass' if floor_ok else 'a child UNDER the floor'}" + (f"; DEDUPED into {dropped.name}" if dropped else ""))
        se = d["search"]
        say(f"- trees: {len(enumerate_trees(len(SPLIT_ORDER[dec])))} before the dedupe and the floor (s = {len(SPLIT_ORDER[dec])}); after the dedupe "
            f"(s = {se.s}) {len(se.all_keys)}; after the floor m = {d['m']}: {se.n_keys}")
        say("- the first ten trees in the canonical order (groups, root, left option, right option):")
        for ln in d["tree_listing"][:10]:
            say(f"    {ln}")
        for hw in hw_maps(dec, d["v20"], d["medians"]):
            nl = int(sum(1 for x in d["v20"][hw.cid] if (x is not None and fnum(x) <= hw.cut) or (x is None and hw.missing_left)))
            say(f"- {hw.name} (fixed, no search): {hw.source}; cut {fmt_val(hw.cut)}; 2020 sides {nl} ≤ / {len(d['v20'][hw.cid]) - nl} >; missing -> "
                f"{'≤' if hw.missing_left else '>'}")


def minute_tree_lines(say, P: dict, vals: dict, ER: dict, store) -> None:
    """§10: per minute tree, C-E1's distribution and the buy day's summed minute volume / the export's buy-day volume (read for the bars'
    convention only, never a context)."""
    say("\n## §10 — C-E1 and the buy-day volume ratio per minute tree (the convention check; outcome-free)")
    by = defaultdict(list)
    for b in BLOCKS:
        for t in P["ENTER"]["scorable"][b]:
            r = ER[t.eid]
            tree = store.state(r.b.E, bar_sym(r.b.E, r.b.sym_a, r.b.sym), r.b).split("/")[-1]
            ratio = math.nan
            if r.mb is not None and fnum(r.bars.v[r.e]) > 0:
                ratio = fnum(np.sum(np.asarray(r.mb.v, dtype=float))) / fnum(r.bars.v[r.e])
            by[tree].append((vals["ENTER"][t.eid]["C-E1"][0], ratio))
    for tree, xs in sorted(by.items()):
        e1 = [x for x, _r in xs if x is not None]
        ra = [r_ for _x, r_ in xs if np.isfinite(r_)]
        q = lambda a: " / ".join(f"{v:.3g}" for v in np.percentile(a, [25, 50, 75])) if a else "-"      # noqa: E731
        say(f"- tree {tree}: n {len(xs)}; C-E1 quartiles {q(e1)} (defined {len(e1)}); minute / export volume quartiles {q(ra)}")


def spy_lines(say, M: dict, P: dict, SR: dict, ER: dict) -> None:
    say("\n## SPY's presence (the market contexts read the SAME pinned era exports; the calendar is built from SPY's rows)")
    for era in ("A", "B"):
        bars, cidx = spy_of(M, era)
        n_cal = len(M["Ds"][era].cal)
        gaps = int(np.sum(np.diff(cidx) != 1)) if len(cidx) > 1 else 0
        say(f"- era {era}: SPY {len(bars)} bars {bars.dates[0]}..{bars.dates[-1]} on a calendar of {n_cal} sessions; gaps {gaps}; last date <= {CUT_B}: "
            f"{bars.dates[-1].isoformat() <= CUT_B}")


def coverage_lines(say, P: dict, ER: dict, SR: dict, store) -> None:
    say("\n## Coverage from the fetch logs (the buy-day minute pair of every scorable trade)")
    for dec in DECISIONS:
        recs = ER if dec == "ENTER" else SR
        for b in BLOCKS:
            c = Counter()
            for t in P[dec]["scorable"][b]:
                r = recs[t.eid]
                c[store.state(r.b.E, bar_sym(r.b.E, r.b.sym_a, r.b.sym), r.b).split("/")[0]] += 1
            say(f"- {dec} {b}: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))


def dry_run(say) -> int:
    say(f"{DRY_HEADER}: every input loaded; the populations re-asserted against the rule-mix tag files by eid (labels, offsets, clocks, fills only — "
        "never a bucket column); every context from decision-time views; the cuts, the medians, the splits, the trees; every count of the doc "
        "asserted; the constants and the pins. NO outcome: no rule fired, no bucket read, no map scored.")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    check_inputs(say)
    C = load_core(say)
    assert_populations(say, C)
    kA, kB = market_names(C)
    M = load_markets(say, C, kA, kB)
    store = M["store"]
    ER, SR = dry_records(say, C, M)
    P = populations(C)
    assert_tag_rows_against_records(say, C, ER, SR)
    spy_by_era = {"A": spy_of(M, "A"), "B": spy_of(M, "B")}
    vals, fails = all_vals(P, ER, SR, spy_by_era, check_full=False)
    say(f"- the by-date assertion on every trade's decision-time view (every daily bar < E, the D bar dated the record calendar's predecessor of E, "
        f"every minute < the bound, SPY <= D): {len(fails)} violations")
    if fails:
        raise GuardStop(f"the decision-time views: {len(fails)} violations (first: {fails[0]})")
    D = {dec: decision_setup(dec, P, vals[dec]) for dec in DECISIONS}
    print_contexts_and_splits(say, P, vals, D)
    minute_tree_lines(say, P, vals, ER, store)
    spy_lines(say, M, P, SR, ER)
    coverage_lines(say, P, ER, SR, store)
    say("\n## The doc's counts (every claim; a mismatch STOPS the dry run at the end)")
    claim = CtxClaims(say)
    dry_claims(say, claim, P, vals, D, SR)
    say("\n## The readings this module fixes where the registration is silent (the stricter each time; the module docstring C1-C21)")
    for ln in readings_lines():
        say(ln)
    say("\n## CONSTANTS (pinned under the marker by name; --run re-derives each and STOPS on a difference)")
    for k, v in constants_of(D).items():
        say(f"- {k}: {v}")
    h = fz.store_freeze_body(DOC, FREEZE_BODIES)
    say(f"\n- the body above the marker stored under freeze_bodies/ ({h[:12]}...): the freeze pin `doc_body_freeze` will name it")
    p = ctx_pins(include_outputs=False)
    say("\n## Pins (sha256) — the inputs; --print-pins adds the dry run, the ledger and the constants; every value goes under the doc's freeze marker line")
    for k, v in p.items():
        say(f"  {k}: {v}")
    miss = fz.freeze_missing(DOC, p)
    say(f"- freeze record: {'every pin above is written under the freeze marker line' if not miss else 'NOT YET under the freeze marker line: ' + str(len(miss)) + ' pins'}")
    say(f"\n## RESULT: {claim.n} claims, {claim.n - len(claim.bad)} OK, {len(claim.bad)} MISMATCH; {len(claim.notes)} notes")
    for ln, lab, d_, m_ in claim.bad:
        say(f"  MISMATCH [L{ln}] {lab}: doc {fz.fmt_claim(d_)} vs mine {fz.fmt_claim(m_)}")
    if claim.bad:
        say("STOPPED: the dry run does not reproduce the registration (amend the doc or the derivation before the freeze)")
        return 3
    say(f"\nDRY RUN COMPLETE: every count reproduced; contexts from decision-time views only; no rule fired, no bucket read, no map scored.")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# --run: the gates, then ENTER -> STOP -> EXIT
# ═════════════════════════════════════════════════════════════════════════════════════════════
def run_stage(say) -> int:
    bad = ctx_lock()
    if bad:
        print("REFUSED (guard 1): " + " | ".join(bad), file=sys.stderr)
        return 2
    msha = sha(CODE["ctx_module"])
    frozen_copy = os.path.join(FROZEN_DIR, f"01_ctx_frozen_{msha[:12]}.py")
    shutil.copyfile(CODE["ctx_module"], frozen_copy)                          # guard (2)
    say(f"{RUN_HEADER} (ONE run): the gates, then ENTER -> STOP -> EXIT on every block and tolerance, the comparators, the controls, the tables")
    say(f"# registration: {os.path.relpath(DOC, REPO)}; module {msha[:12]}... copied to {os.path.basename(frozen_copy)}; every pin under the marker; the dry run COMPLETE")
    try:
        rc = run_stages(say)
    except GuardStop as g:
        say(f"STOPPED: {g}")
        say.write(STOPPED)
        return 3
    except Exception:
        import traceback
        say("STOPPED (crash):\n" + traceback.format_exc())
        say.write(STOPPED)
        return 4
    say.write(P_RUN)
    fz.ledger_append("run", P_RUN, LEDGER)
    return rc


def g2_known(say, X0: dict, P: dict) -> None:
    """G2: the no-split tree's ±0 share re-reads the rule-mix standalone shares at one decimal, and the ±0 UNION re-reads 56.8 / 66.7, 54.0 /
    57.8, 71.5 / 72.9."""
    bad = []
    for dec in DECISIONS:
        nl = len(LIB[dec])
        X20 = X0[dec]["2020"][:, :nl]
        r = int(np.argmax(X20.sum(axis=0)))
        code, want = KNOWN_BEST[dec]
        if LIB[dec][r] != code:
            bad.append(f"{dec}: BEST at ±0 is {LIB[dec][r]}, not {code}")
        for b in LABEL_BLOCKS:
            X = X0[dec][b][:, :nl]
            got = share(int(X[:, r].sum()), X.shape[0])
            if pct(got) != pct(want[b]):
                bad.append(f"{dec} {b}: {code} {pct(got)} vs {pct(want[b])}")
            u = share(int(X.any(axis=1).sum()), X.shape[0])
            if pct(u) != pct(KNOWN_UNION[dec][b]):
                bad.append(f"{dec} {b}: UNION {pct(u)} vs {pct(KNOWN_UNION[dec][b])}")
    say(f"- G2 the ±0 known answers (BEST {', '.join(KNOWN_BEST[d][0] for d in DECISIONS)} and the UNION on 2020 / 2021-22): {len(bad)} differences")
    if bad:
        raise GuardStop("G2: " + "; ".join(bad))


def g3_tolerance(say, data: dict, b0: dict) -> None:
    """G3: every widened bucket (the frozen `bucket` on the per-Fire window) equals the independent derivation from the ±0 bucket of the TAG
    FILE, jb, je and the missing sessions, at ±1c and the symmetric ±1 / ±2."""
    bad, n, ups = [], 0, Counter()
    for dec in ("STOP", "EXIT"):
        for eid, t in data["se"].items():
            if not t.get("tagged"):
                continue
            r = t["rec"]
            lo, hi, J = r.exit_lo_j, r.exit_hi_j, int(t["prep"]["J_tail"])
            fires = t[f"{dec.lower()}_fires"]
            for c in LIB[dec]:
                f = fires[c]
                base = b0[dec][eid][c]
                for tol in ("pm1c", "pm1", "pm2"):
                    n += 1
                    got = close_bucket(f, lo, hi, tol, J)
                    want = derive_widened(base, f, lo, hi, tol, J)
                    if got != want:
                        bad.append(f"{dec} eid {eid} {c} {tol}: bucket {got} vs derived {want} (±0 {base}, je {f.je}, jb {f.jb}, missing {f.missing})")
                    if base == UN and got == EX:
                        ups[(dec, tol)] += 1
    say(f"- G3 tolerance consistency: {n} widened (trade, rule, tolerance) buckets vs the derivation from the ±0 tag bucket, jb, je and the missing "
        f"sessions: {len(bad)} differences; UNRESOLVED -> CLOSE upgrades {dict(ups)}")
    if bad:
        raise GuardStop(f"G3: {len(bad)} widened buckets differ from the derivation (first: {bad[0]})")


def g5_chance(say, chance1: dict, X0: dict) -> None:
    """G5: the no-split tree's (c-1) at ±0 equals the best rule's own chance share as the rule-mix printed it, arm by arm, on both blocks."""
    bad = []
    for dec in DECISIONS:
        code = KNOWN_BEST[dec][0]
        r = LIB_INDEX[dec][code]
        for b in LABEL_BLOCKS:
            for arm, want in KNOWN_G5[dec][b].items():
                ch = chance1[dec]["pm0" if dec != "ENTER" else "bracket"][arm][b]
                got = per_leaf_chance(np.full(ch.shape[0], r, dtype=np.int64), ch)
                if pct(got) != pct(want):
                    bad.append(f"{dec} {b} {arm}: {code} {pct(got)} vs printed {pct(want)}")
    say(f"- G5 the no-split tree's per-leaf chance at ±0 vs the rule-mix printout ({' / '.join(KNOWN_BEST[d][0] for d in DECISIONS)}, every arm, 2020 and "
        f"2021-22): {len(bad)} differences")
    if bad:
        raise GuardStop("G5: " + "; ".join(bad))


def run_stages(say, C: "dict | None" = None, M: "dict | None" = None) -> int:
    check_inputs(say)
    if C is None:
        C = load_core(say)
    assert_populations(say, C)
    if M is None:
        kA, kB = market_names(C)
        M = load_markets(say, C, kA, kB)
    P = populations(C)
    # ---- the contexts and the cuts first (D2: before any bucket column is read), held to the pins (G6 on every trade)
    ER_d, SR_d = dry_records(say, C, M)
    assert_tag_rows_against_records(say, C, ER_d, SR_d)
    spy_by_era = {"A": spy_of(M, "A"), "B": spy_of(M, "B")}
    vals, fails = all_vals(P, ER_d, SR_d, spy_by_era, check_full=True)
    say(f"- G6 the decision-time guard: every context of every trade from the truncated view vs the full record, the by-date assertion: {len(fails)} failures")
    if fails:
        raise GuardStop(f"G6: {len(fails)} failures (first: {fails[0]})")
    D = {dec: decision_setup(dec, P, vals[dec]) for dec in DECISIONS}
    consts = constants_of(D)
    off = [f"{k} {v} vs pinned {pin_value_under_marker(k, DOC) or fz.pin_under_marker(k, DOC)}" for k, v in consts.items()
           if (pin_value_under_marker(k, DOC) if not HEX64_RX.match(v) else fz.pin_under_marker(k, DOC)) != v]
    say(f"- the constants re-derived (the cuts, the medians, the floors, the tree orders): {len(consts)}; differing from the pins {len(off)}")
    if off:
        raise GuardStop("the constants differ from the pins (D2): " + "; ".join(off[:4]))
    del ER_d, SR_d
    # ---- the rule-mix fires re-built, G8, G1
    rb = rebuild_rule_mix(say, C, M)
    store = rb["store"]
    ctx_g8(say, [t["rec"] for t in rb["se"].values()], "ctx_run")
    say("\n## THE KNOWN-ANSWER GATES (each STOPS the run before any new number)")
    say(f"- G6 passed above (before any bucket was read)")
    b0 = g1_identity(say, P, rb)
    data = build_matrices(say, P, rb, store, sw_cut=D["EXIT"]["sw_cut"])
    g2_known(say, {d: data["X"][d]["pm0" if d != "ENTER" else "bracket"] for d in DECISIONS}, P)
    g3_tolerance(say, rb, b0)
    g4_switch(say, rb["se"], store)
    g5_chance(say, data["chance1"], data["X"])
    say("\nALL GATES PASSED — the numbers below are new")
    rows = report_all(say, P, vals, D, data, rb)
    write_files(say, P, vals, rows)
    say("\nRUN COMPLETE")
    return 0


def trade_sets(dec: str, P: dict) -> list:
    """(key, trades): every block's scorable trades; for ENTER also the undated flickers beside ('<block>|beside', never summed)."""
    out = [(b, P[dec]["scorable"][b]) for b in BLOCKS]
    if dec == "ENTER":
        out += [(f"{b}|beside", P[dec]["beside"][b]) for b in BLOCKS]
    return out


def build_matrices(say, P: dict, rb: dict, store, sw_cut: "float | None" = None) -> dict:
    """Per decision, tolerance and trade set: the CLOSE matrix X (trades x rules; EXIT carries SW-a / SW-b as two more columns), the (c-1)
    chance per arm (trades x rules, NaN without room), the (c-2) draws per arm (draws x trades x rules), the widened buckets (the upgrade
    counts), the clipped placement counts and control (a) at s >= a_f (beside)."""
    X = {d: {tol: {} for tol in TOLS[d]} for d in DECISIONS}
    BK = {d: {tol: {} for tol in TOLS[d]} for d in ("STOP", "EXIT")}
    chance1 = {d: {tol: {a: {} for a in ARMS[d]} for tol in TOLS[d]} for d in DECISIONS}
    draws2 = {d: {tol: {a: {} for a in ARMS[d]} for tol in TOLS[d]} for d in DECISIONS}
    clip = {d: {tol: {} for tol in TOLS[d]} for d in ("STOP", "EXIT")}
    chance1_sa = {d: {tol: {} for tol in TOLS[d]} for d in ("STOP", "EXIT")}
    ER, scored, se = rb["ER"], rb["scored"], rb["se"]
    cache = {}
    for dec in DECISIONS:
        R_ = len(LIB[dec]) + (2 if dec == "EXIT" else 0)
        for key, trades in trade_sets(dec, P):
            b = key.split("|")[0]
            n = len(trades)
            sw_fires = {}
            if dec == "EXIT":
                for tr in trades:
                    t = se[tr.eid]
                    r = t["rec"]
                    ctx = mix.make_ctx(r, t["prep"], store)
                    smas = fz.smas_for(r.bars)
                    sw_fires[tr.eid] = [switch_fire(r, ctx, smas, sw_cut, v) for v in ("a", "b")]
            for tol in TOLS[dec]:
                Xb = np.zeros((n, R_), dtype=bool)
                ch = {a: np.full((n, R_), np.nan) for a in ARMS[dec]}
                dr = {a: np.zeros((DRAWS, n, R_), dtype=bool) for a in ARMS[dec]}
                bks, clip_n, clip_tot = [], 0, 0
                sa = np.full((n, R_), np.nan)
                for i, tr in enumerate(trades):
                    if dec == "ENTER":
                        e = scored[(mix.stream_of_block(b), tr.eid)]
                        rec = ER[tr.eid]
                        Xb[i] = enter_close_row(e, rec, tol)
                        ctl = enter_controls(e, rec, tol)
                        ch["kprice"][i] = ctl["kprice"].mean(axis=0)
                        dr["kprice"][:, i, :] = ctl["kprice"]
                        if ctl["shared"] is not None:
                            ch["shared"][i] = ctl["shared"].mean(axis=0)
                            dr["shared"][:, i, :] = ctl["shared"]
                        continue
                    t = se[tr.eid]
                    r = t["rec"]
                    J = int(t["prep"]["J_tail"])
                    row, bk = se_close_rows(t, dec, tol)
                    fires = [t[f"{dec.lower()}_fires"][c] for c in LIB[dec]]
                    if dec == "EXIT":
                        for f in sw_fires[tr.eid]:
                            row = np.append(row, close_bucket(f, r.exit_lo_j, r.exit_hi_j, tol, J) == EX)
                        fires += sw_fires[tr.eid]
                    Xb[i] = row
                    bks.append(bk)
                    ctl = se_controls(t, dec, tol, store, cache)
                    starts = ctl["starts"]
                    win = mix.random_windows(r, J, "a")
                    nplace = len(starts)
                    ik = ("place", dec, tr.eid)
                    if ik not in cache:
                        cache[ik] = np.array([fz.rng_for(PLACE_KEY.format(decision=dec, eid=tr.eid, d=d_)).integers(0, nplace) for d_ in range(DRAWS)], dtype=np.int64)
                    idx = cache[ik]
                    for arm, frames in (("a_frames", True), ("a_noframes", False)):
                        Pm, CL = ctl[arm], ctl[arm + "_clipped"]
                        if dec == "EXIT":
                            ex_ = [se_window_codes(f, starts, win["width"], tol, J, frames) for f in sw_fires[tr.eid]]
                            Pm = np.column_stack([Pm] + [c_ == CODE_OF[EX] for c_, _cl in ex_])
                            CL = np.column_stack([CL] + [cl_ for _c, cl_ in ex_])
                        ch[arm][i] = Pm.mean(axis=0)
                        dr[arm][:, i, :] = Pm[idx]
                        if arm == "a_frames":
                            fired = np.array([fire_side(f) is not None for f in fires], dtype=bool)
                            clip_n += int(CL[:, fired].sum())
                            clip_tot += int(CL.shape[0] * fired.sum())
                            for j in range(R_):
                                keep = ~CL[:, j]
                                if keep.any():
                                    sa[i, j] = Pm[keep, j].mean()
                    if ctl["rlevel1"] is not None:
                        ch["rlevel"][i] = ctl["rlevel1"].mean()
                        rk = ctl["rlevelk"]
                        if dec == "EXIT":
                            rk = np.column_stack([rk, ctl["rlevel1"], ctl["rlevel1"]])          # SW: no library column — the single-level draw (C12)
                        dr["rlevel"][:, i, :] = rk
                X[dec][tol][key] = Xb
                for a in ARMS[dec]:
                    chance1[dec][tol][a][key] = ch[a]
                    draws2[dec][tol][a][key] = dr[a]
                if dec != "ENTER":
                    BK[dec][tol][key] = bks
                    clip[dec][tol][key] = (clip_n, clip_tot)
                    chance1_sa[dec][tol][key] = sa
    say("- the CLOSE matrices and the chance arms built: " + "; ".join(f"{d} " + ", ".join(f"{b} {X[d][PRIMARY[d]][b].shape[0]}" for b in BLOCKS) for d in DECISIONS))
    return dict(X=X, BK=BK, chance1=chance1, draws2=draws2, clip=clip, chance1_sa=chance1_sa)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# one LINE (the map, MAP-T1, a fixed map, SW) against BEST: shares, SHUF, (c-1), (c-2), the paired intervals, the labels
# ═════════════════════════════════════════════════════════════════════════════════════════════
def child_name(splits: list, cm: int) -> str:
    s = splits[cm // 2]
    if s.token == "bin":
        return f"{s.cid} = {0 if cm % 2 == 0 else 1}"
    return f"{s.cid} {'<=' if cm % 2 == 0 else '>'} {s.token} ({s.cut:.4g})"


def group_name(splits: list, sig: tuple) -> str:
    return "all" if not sig else " & ".join(child_name(splits, c) for c in sig)


def fit_desc(dec: str, fit: dict, search: Search, cols_lib: tuple) -> str:
    inv = {v: k for k, v in search.uniq.items()}
    parts = [f"[{group_name(search.splits, inv[g])}] -> {rule_name(dec, r)}" for g, r in zip(fit["gids"], fit["rules"])]
    return f"{len(fit['gids'])} group{'s' if len(fit['gids']) > 1 else ''}: " + "; ".join(parts)


def rule_name(dec: str, r: int) -> str:
    lib = LIB[dec]
    if r < len(lib):
        return lib[r]
    return ("SW-a", "SW-b")[r - len(lib)]


class Line:
    """A line of the template: kind 'search' (the exhaustive search within `cols`), 'best' (the no-split procedure within `cols`) or 'fixed'
    (per trade rules from a fixed map of one context, or one fixed column)."""

    def __init__(self, name: str, kind: str, cols: "tuple | None" = None, fixed: "FixedMap | None" = None, col: "int | None" = None):
        self.name, self.kind, self.cols, self.fixed, self.col = name, kind, cols, fixed, col

    def rules_for(self, search: Search, Gs: dict, Xs: dict, vals: dict, perm: "dict | None" = None) -> tuple:
        """(fit or None, {set key: rules per trade}) — fitted on 2020 (X20 = Xs['2020']); `perm` = {set key: permutation} permutes context rows."""
        perm = perm or {}
        Gp = {k: (G[:, perm[k]] if k in perm else G) for k, G in Gs.items()}
        if self.kind == "search":
            fit = search.fit(Gp["2020"], Xs["2020"], self.cols)
            return fit, {k: assign_rules(fit, G) for k, G in Gp.items()}
        if self.kind == "best":
            fit = search.fit_best_single(Xs["2020"], self.cols)
            return fit, {k: np.full(G.shape[1], fit["rules"][0], dtype=np.int64) for k, G in Gp.items()}
        if self.col is not None:
            return None, {k: np.full(G.shape[1], self.col, dtype=np.int64) for k, G in Gp.items()}
        out = {}
        for k in Gs:
            v = vals[k][self.fixed.cid]
            if k in perm:
                v = [v[i] for i in perm[k]]
            out[k] = self.fixed.rules(v)
        return None, out


def closes(rules: np.ndarray, X: np.ndarray) -> np.ndarray:
    return X[np.arange(X.shape[0]), rules] if X.shape[0] else np.zeros(0, dtype=bool)


def evaluate_line(line: Line, dec: str, tol: str, search: Search, Gs: dict, vals: dict, data: dict, boots: "int | None" = None, with_controls: bool = True) -> dict:
    """Every number one line prints: the shares per set, SHUF (mean, p95, the real map's percentile, the per-trade mean close), (c-1) and (c-2)
    per arm, the closes per set; plus the permutation / draw rows for controls.tsv.gz."""
    Xs = {k: data["X"][dec][tol][k] for k in Gs}
    fit, rules = line.rules_for(search, Gs, Xs, vals)
    out = dict(name=line.name, fit=fit, rules=rules, close={k: closes(rules[k], Xs[k]) for k in Gs})
    out["share"] = {k: share(int(c.sum()), len(c)) for k, c in out["close"].items()}
    if not with_controls:
        return out
    # SHUF: whole context rows permuted within each LABEL block (the untouched block is not permuted, §6b); the CLOSE matrix never moves
    n20, n22 = Gs["2020"].shape[1], Gs["2021-22"].shape[1]
    sh = {b: [] for b in LABEL_BLOCKS}
    pc = {b: np.zeros(Gs[b].shape[1]) for b in LABEL_BLOCKS}
    rows = []
    for p in range(PERMS):
        perm = {"2020": shuffled(n20, dec, "2020", p), "2021-22": shuffled(n22, dec, "2021-22", p)}
        f_p, r_p = line.rules_for(search, {b: Gs[b] for b in LABEL_BLOCKS}, Xs, vals, perm)
        for b in LABEL_BLOCKS:
            c = closes(r_p[b], Xs[b])
            sh[b].append(share(int(c.sum()), len(c)))
            pc[b] += c
        rows.append(dict(decision=dec, tolerance=tol, line=line.name, kind="perm", index=p, tree=str(f_p["key"]) if f_p else "-",
                         rules=";".join(rule_name(dec, r) for r in f_p["rules"]) if f_p else "-", share_2020=sh["2020"][-1], share_2021_22=sh["2021-22"][-1]))
    out["shuf"] = {}
    for b in LABEL_BLOCKS:
        a = np.array(sh[b])
        real = out["share"][b]
        out["shuf"][b] = dict(mean=fnum(a.mean()), p95=fnum(np.percentile(a, 95)), pctile=fnum(((a < real).sum() + 0.5 * (a == real).sum()) / len(a)),
                              per_trade=pc[b] / PERMS)
    # (c-1) per arm: each trade's chance under ITS OWN group's rule
    out["c1"] = {a: {b: per_leaf_chance(rules[b], data["chance1"][dec][tol][a][b]) for b in BLOCKS} for a in ARMS[dec]}
    if dec != "ENTER":
        out["c1_sa"] = {b: per_leaf_chance(rules[b], data["chance1_sa"][dec][tol][b]) for b in BLOCKS}
    # (c-2) per arm: the full procedure on each control draw (chosen on 2020's draw, scored on 2021-22's draw)
    out["c2"] = {}
    for a in ARMS[dec]:
        d20, d22 = data["draws2"][dec][tol][a]["2020"], data["draws2"][dec][tol][a]["2021-22"]
        s20, s22 = [], []
        for d_ in range(DRAWS):
            Xd = {"2020": d20[d_], "2021-22": d22[d_]}
            f_d, r_d = line.rules_for(search, {b: Gs[b] for b in LABEL_BLOCKS}, Xd, vals)
            s20.append(share(int(closes(r_d["2020"], Xd["2020"]).sum()), n20))
            s22.append(share(int(closes(r_d["2021-22"], Xd["2021-22"]).sum()), n22))
            rows.append(dict(decision=dec, tolerance=tol, line=line.name, kind=f"draw:{a}", index=d_, tree=str(f_d["key"]) if f_d else "-",
                             rules=";".join(rule_name(dec, r) for r in f_d["rules"]) if f_d else "-", share_2020=s20[-1], share_2021_22=s22[-1]))
        out["c2"][a] = {"2020": fnum(np.mean(s20)), "2021-22": fnum(np.mean(s22))}
    out["rows"] = rows
    return out


def labels_for(L: dict, B: dict, dec: str) -> dict:
    """The §7a labels of a line L against BEST B, per label block and overall."""
    out = {}
    for b in LABEL_BLOCKS:
        arms = {a: (L["c1"][a][b], B["c1"][a][b], L["c2"][a][b], B["c2"][a][b]) for a in ARMS[dec]}
        out[b] = dict(helps=context_helps(L["share"][b], B["share"][b], L["shuf"][b]["mean"]), chance=beats_chance(L["share"][b], B["share"][b], arms))
    helps = all(out[b]["helps"] for b in LABEL_BLOCKS)
    chance = all(out[b]["chance"] for b in LABEL_BLOCKS)
    out["helps"], out["chance"], out["summary"] = helps, chance, summary_label(helps, chance)
    return out


def ci_line(x: np.ndarray) -> str:
    k, n = int(x.sum()), len(x)
    return mix.ci_text(k, n)


def pts(x: float) -> str:
    return "-" if not np.isfinite(x) else f"{100 * x:+.1f}"


def median_or_dash(xs) -> str:
    xs = [x for x in xs if x is not None]
    return f"{np.median(xs):g}" if xs else "-"


def report_decision_tol(say, dec: str, tol: str, P: dict, vals_dec: dict, d: dict, data: dict, rows: dict) -> dict:
    """The template of §11 for one decision and tolerance (+ the beside lines at the primary tolerance). -> {line name: (L, labels)}."""
    search = d["search"]
    sets = dict(trade_sets(dec, P))
    vals = {k: block_vals(dec, trs, vals_dec) for k, trs in sets.items()}
    Gs = {k: search.membership(v) for k, v in vals.items()}
    lab_cols = tuple(range(len(LIB[dec])))
    t1_cols = tuple(LIB_INDEX[dec][c] for c in TIER1[dec])
    best_line = Line("BEST", "best", cols=lab_cols)
    B = evaluate_line(best_line, dec, tol, search, Gs, vals, data)
    Lm = evaluate_line(Line("MAP", "search", cols=lab_cols), dec, tol, search, Gs, vals, data)
    labs = labels_for(Lm, B, dec)
    n = {b: Gs[b].shape[1] for b in BLOCKS}
    m_fit = Lm["fit"]
    say(f"\ndecision {dec} — tolerance {TOL_LABEL[tol]} — n {n['2020']} / {n['2021-22']} / {n['untouched']}; the chosen map: {fit_desc(dec, m_fit, search, lab_cols)}; "
        f"m {d['m']}; trees searched {search.n_keys}")
    X = {k: data["X"][dec][tol][k] for k in sets}
    oracle = int(np.argmax(X["2021-22"][:, :len(LIB[dec])].sum(axis=0))) if n["2021-22"] else 0
    hdr = ["line", "2020 (fit, in-sample)", "2021-22 (scored as chosen)", "untouched (sign)"]
    tab = []
    un_d = Lm["share"]["untouched"] - B["share"]["untouched"] if n["untouched"] else math.nan
    tab.append(["MAP", ci_line(Lm["close"]["2020"]), ci_line(Lm["close"]["2021-22"]), f"MAP − BEST {sign_of(un_d)} (n {n['untouched']})"])
    tab.append([f"BEST ({rule_name(dec, B['fit']['rules'][0])})", pct(B["share"]["2020"]), pct(B["share"]["2021-22"]), pct(B["share"]["untouched"])])
    cells = []
    for b in LABEL_BLOCKS:
        diff = Lm["close"][b].astype(float) - B["close"][b].astype(float)
        mn, lo, hi = paired_interval(diff, dec, b, "MAP-BEST")
        x, y, p_ = mcnemar(Lm["close"][b], B["close"][b])
        cells.append(f"{pts(mn)} [{pts(lo)}, {pts(hi)}]; McNemar {x} / {y} (p {p_:.3f})")
    tab.append(["MAP − BEST (paired)"] + cells + [""])
    tab.append(["ORACLE-1", "—", f"{pct(share(int(X['2021-22'][:, oracle].sum()), n['2021-22']))} ({rule_name(dec, oracle)})", ""])
    tab.append(["SHUF mean", f"{pct(Lm['shuf']['2020']['mean'])} (p95 {pct(Lm['shuf']['2020']['p95'])}; MAP at pctile {100 * Lm['shuf']['2020']['pctile']:.1f})",
                f"{pct(Lm['shuf']['2021-22']['mean'])} (p95 {pct(Lm['shuf']['2021-22']['p95'])})", ""])
    cells = []
    for b in LABEL_BLOCKS:
        diff = Lm["close"][b].astype(float) - Lm["shuf"][b]["per_trade"]
        mn, lo, hi = paired_interval(diff, dec, b, "MAP-SHUF")
        cells.append(f"{pts(mn)} [{pts(lo)}, {pts(hi)}]")
    tab.append(["MAP − SHUF (paired)"] + cells + [""])
    for kind in ("c1", "c2"):
        for a in ARMS[dec]:
            cl = []
            for b in LABEL_BLOCKS:
                cl.append(f"MAP {pct(Lm[kind][a][b])} / BEST {pct(B[kind][a][b])} -> net gain {net_gain(Lm['share'][b], B['share'][b], Lm[kind][a][b], B[kind][a][b]):+.1f}"
                          if np.isfinite(net_gain(Lm['share'][b], B['share'][b], Lm[kind][a][b], B[kind][a][b])) else f"MAP {pct(Lm[kind][a][b])} / BEST {pct(B[kind][a][b])}")
            tab.append([f"({'c-1' if kind == 'c1' else 'c-2'}) {ARM_LABEL[a]}"] + cl + [""])
    big = {b: (max((Lm["c1"][a][b] for a in ARMS[dec] if np.isfinite(Lm["c1"][a][b])), default=math.nan),
               max((Lm["c2"][a][b] for a in ARMS[dec] if np.isfinite(Lm["c2"][a][b])), default=math.nan)) for b in LABEL_BLOCKS}
    tab.append(["(largest arm, layout only)"] + [f"(c-1) {pct(big[b][0])} / (c-2) {pct(big[b][1])}" for b in LABEL_BLOCKS] + [""])
    ucells = []
    for b in LABEL_BLOCKS:
        u = share(int(X[b][:, :len(LIB[dec])].any(axis=1).sum()), n[b])
        gap = (Lm["share"][b] - B["share"][b]) / (u - B["share"][b]) if (np.isfinite(u) and u > B["share"][b]) else math.nan
        ucells.append(f"{pct(u)}; gap closed {pct(gap)}")
    tab.append(["UNION"] + ucells + [""])
    for ln in rp.table(hdr, tab):
        say(ln)
    say(f"  -> context helps: {'yes' if labs['helps'] else 'no'} (2020 {'yes' if labs['2020']['helps'] else 'no'}, 2021-22 {'yes' if labs['2021-22']['helps'] else 'no'}) "
        f"| beats chance (every arm's net gain >= 10.0, (c-1) and (c-2)): {'yes' if labs['chance'] else 'no'} | SUMMARY{' (beside, never the summary)' if tol != PRIMARY[dec] else ''}: "
        f"{labs['summary']}")
    # the groups
    inv = {v: k for k, v in search.uniq.items()}
    for g, r in zip(m_fit["gids"], m_fit["rules"]):
        parts = []
        for b in BLOCKS:
            sel = Gs[b][g]
            trs = [t for t, s in zip(sets[b], sel) if s]
            cc = closes(np.full(int(sel.sum()), r, dtype=np.int64), X[b][sel]) if sel.any() else np.zeros(0, dtype=bool)
            conf = (f"bracket median {median_or_dash(t.width for t in trs)}" if dec == "ENTER" else
                    f"window median {median_or_dash(t.window_w for t in trs)}, exit_lo_j median {median_or_dash(t.exit_lo_j for t in trs)}")
            parts.append(f"{b} n {len(trs)} -> {pct(share(int(cc.sum()), len(cc)))} (dated {sum(1 for t in trs if t.dated)}, EP {sum(1 for t in trs if t.setup in ('EP', 'both'))}; {conf})")
        flag = ""
        if dec == "ENTER" and len(m_fit["gids"]) > 1:
            w_in = [t.width for t, s in zip(sets["2020"], Gs["2020"][g]) if s and t.width is not None]
            w_out = [t.width for t, s in zip(sets["2020"], Gs["2020"][g]) if not s and t.width is not None]
            if w_in and w_out:
                q = np.median(w_in) / max(np.median(w_out), 1e-9)
                if q >= 2.0 or q <= 0.5:
                    flag = f" | PANEL ARTEFACT? the group's 2020 median bracket {np.median(w_in):g} vs the rest {np.median(w_out):g} (C17)"
        say(f"  group [{group_name(search.splits, inv[g])}] rule {rule_name(dec, r)}: " + " | ".join(parts) + flag)
    # the controls line
    if dec != "ENTER":
        cl = data["clip"][dec][tol]
        clip_txt = ", ".join(f"{b} {pct(share(cl[b][0], cl[b][1]))}" for b in BLOCKS)
        sa = ", ".join(f"{b} MAP {pct(Lm['c1_sa'][b])} / BEST {pct(B['c1_sa'][b])}" for b in BLOCKS)
        ups = Counter()
        if tol != "pm0":
            for b in BLOCKS:
                for bk0, bk in zip(data["BK"][dec]["pm0"][b], data["BK"][dec][tol][b]):
                    for c in LIB[dec]:
                        if bk0[c] == UN and bk[c] == EX:
                            ups[(b, c)] += 1
        say(f"  controls: clipped placements (s < a_f, fired rules, frames) {clip_txt}; control (a) frames at s >= a_f {sa} | UNRESOLVED -> CLOSE upgrades "
            + (", ".join(f"{b} {c} {v}" for (b, c), v in sorted(ups.items())) if ups else "none"))
    miss = "; ".join(f"{c} " + "/".join(str(sum(1 for x in vals[b][c] if x is None)) for b in BLOCKS) for c in CIDS[dec])
    say(f"  missing per context (2020 / 2021-22 / untouched): {miss}")
    out = {"MAP": (Lm, labs), "BEST": (B, None)}
    rows["controls"] += Lm["rows"]
    rows["maps"].append(dict(decision=dec, tolerance=tol, line="MAP", tree=str(m_fit["key"]), desc=fit_desc(dec, m_fit, search, lab_cols),
                             share_2020=Lm["share"]["2020"], share_2021_22=Lm["share"]["2021-22"], share_untouched=Lm["share"]["untouched"],
                             best=rule_name(dec, B["fit"]["rules"][0]), best_2020=B["share"]["2020"], best_2021_22=B["share"]["2021-22"], helps=labs["helps"],
                             beats_chance=labs["chance"], summary=labs["summary"], primary=tol == PRIMARY[dec]))
    for k, trs in sets.items():
        for j, (tr, rr, cc) in enumerate(zip(trs, Lm["rules"][k], Lm["close"][k])):
            gi = next(i for i, g in enumerate(m_fit["gids"]) if Gs[k][g][j])
            rows["groups"].append(dict(eid=tr.eid, decision=dec, set=k, tolerance=tol, map="MAP", group=gi, group_desc=group_name(search.splits, inv[m_fit["gids"][gi]]),
                                       rule=rule_name(dec, int(rr)), close=bool(cc)))
    if dec == "ENTER":
        say("  beside, the undated flickers (scored by the 2020-chosen map, never summed): " + "; ".join(
            f"{b} n {Gs[b + '|beside'].shape[1]}: MAP {pct(Lm['share'][b + '|beside'])} / BEST {pct(B['share'][b + '|beside'])}" for b in BLOCKS))
    if dec == "EXIT":
        lz = []
        for b in BLOCKS:
            lose = np.array([bool(t.loser) for t in sets[b]], dtype=bool)
            for nm, sel in (("losers", lose), ("non-losers", ~lose)):
                lz.append(f"{b} {nm} n {int(sel.sum())}: MAP {pct(share(int(Lm['close'][b][sel].sum()), int(sel.sum())))} / BEST "
                          f"{pct(share(int(B['close'][b][sel].sum()), int(sel.sum())))}")
        say("  beside, losers / non-losers: " + "; ".join(lz))
    if tol != PRIMARY[dec]:
        return out
    # the beside lines at the primary tolerance (labelled, never the summary): MAP-T1, the HW maps, SW
    beside = []
    if len(t1_cols) > 1:
        BT1 = evaluate_line(Line("BEST-T1", "best", cols=t1_cols), dec, tol, search, Gs, vals, data)
        LT1 = evaluate_line(Line("MAP-T1", "search", cols=t1_cols), dec, tol, search, Gs, vals, data)
        beside.append(("MAP-T1", LT1, BT1, fit_desc(dec, LT1["fit"], search, t1_cols)))
        rows["controls"] += LT1["rows"]
    else:
        BT1 = evaluate_line(Line("BEST-T1", "best", cols=t1_cols), dec, tol, search, Gs, vals, data)
        beside.append(("MAP-T1", BT1, BT1, f"the single tier-1 rule {rule_name(dec, t1_cols[0])} (no search)"))
    for hw in hw_maps(dec, d["v20"], d["medians"]):
        L = evaluate_line(Line(hw.name, "fixed", fixed=hw), dec, tol, search, Gs, vals, data)
        beside.append((hw.name, L, B, hw.source + f"; cut {fmt_val(hw.cut)}"))
    if dec == "EXIT":
        for i, v in enumerate(("a", "b")):
            L = evaluate_line(Line(f"SW-{v}", "fixed", col=len(LIB[dec]) + i), dec, tol, search, Gs, vals, data)
            beside.append((f"SW-{v}", L, B, f"the 10/20 switch, far -> the {'10' if v == 'a' else '20'}-day (cut T2 of C-X3 = {fmt_val(d['sw_cut'])}); a composite rule, not in the library"))
    for nm, L, BB, desc in beside:
        lb = labels_for(L, BB, dec)
        out[nm] = (L, lb)
        arms = "; ".join(f"{a}: (c-1) {pct(L['c1'][a]['2020'])} / {pct(L['c1'][a]['2021-22'])}, (c-2) {pct(L['c2'][a]['2020'])} / {pct(L['c2'][a]['2021-22'])}" for a in ARMS[dec])
        say(f"  beside {nm} — {desc}: 2020 {pct(L['share']['2020'])} / 2021-22 {pct(L['share']['2021-22'])} / untouched {pct(L['share']['untouched'])} vs its BEST "
            f"{pct(BB['share']['2020'])} / {pct(BB['share']['2021-22'])}; SHUF {pct(L['shuf']['2020']['mean'])} / {pct(L['shuf']['2021-22']['mean'])}; {arms} -> "
            f"helps {'yes' if lb['helps'] else 'no'}, beats chance {'yes' if lb['chance'] else 'no'}: {lb['summary']} (beside, never the summary)")
        rows["maps"].append(dict(decision=dec, tolerance=tol, line=nm, tree=str(L["fit"]["key"]) if L["fit"] else "-", desc=desc, share_2020=L["share"]["2020"],
                                 share_2021_22=L["share"]["2021-22"], share_untouched=L["share"]["untouched"], best=rule_name(dec, BB["fit"]["rules"][0]) if BB["fit"] else "-",
                                 best_2020=BB["share"]["2020"], best_2021_22=BB["share"]["2021-22"], helps=lb["helps"], beats_chance=lb["chance"], summary=lb["summary"], primary=False))
        for k, trs in sets.items():
            for tr, rr, cc in zip(trs, L["rules"][k], L["close"][k]):
                rows["groups"].append(dict(eid=tr.eid, decision=dec, set=k, tolerance=tol, map=nm, group=-1, group_desc="-", rule=rule_name(dec, int(rr)), close=bool(cc)))
    return out


def report_all(say, P: dict, vals: dict, D: dict, data: dict, rb: dict) -> dict:
    rows = dict(maps=[], groups=[], controls=[])
    summary = {}
    for dec in DECISIONS:
        say(f"\n## {dec} — the map chosen on 2020, scored on 2021-22; the untouched block a sign check")
        res = {}
        for tol in TOLS[dec]:
            res[tol] = report_decision_tol(say, dec, tol, P, vals[dec], D[dec], data, rows)
        summary[dec] = res[PRIMARY[dec]]["MAP"][1]["summary"]
        say(f"\n  {dec} beside (never the summary): " + " | ".join(f"{TOL_LABEL[t]} {res[t]['MAP'][1]['summary']}" for t in TOLS[dec] if t != PRIMARY[dec])
            + " | " + " | ".join(f"{nm} {lab[1]['summary']}" for nm, lab in res[PRIMARY[dec]].items() if nm not in ("MAP", "BEST")))
    say("\n## THE SUMMARY (the primary tolerance; a description, not a verdict — it moves no rule, threshold, size or safeguard)")
    for dec in DECISIONS:
        say(f"- {dec}: {summary[dec]}")
    return rows


def write_files(say, P: dict, vals: dict, rows: dict) -> None:
    """The per-trade files (§11 Outputs): contexts.tsv, maps.tsv, groups.tsv, controls.tsv.gz — each recorded in the ledger."""
    crow = []
    for dec in DECISIONS:
        for key, trs in trade_sets(dec, P):
            for tr in trs:
                row = dict(eid=tr.eid, sym=tr.sym, E=tr.E, decision=dec, block=key.split("|")[0], set="beside" if "|" in key else "scorable")
                for c in CIDS[dec]:
                    v, why = vals[dec][tr.eid][c]
                    row[c] = v
                    row[f"{c}_missing"] = why
                crow.append(row)
    for name, rr, comp in (("contexts.tsv", crow, None), ("maps.tsv", rows["maps"], None), ("groups.tsv", rows["groups"], None),
                           ("controls.tsv.gz", rows["controls"], "gzip")):
        p = ctx_write_out(name, rr, compression=comp)
        fz.ledger_append("run", p, LEDGER)
    say(f"\n- per-trade files -> {OUT_DIR}/ (contexts.tsv, maps.tsv, groups.tsv, controls.tsv.gz); the ledger records each")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# --print-pins, --reset (N2), main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def print_pins(say) -> int:
    say("# #705 CONTEXT RULES 01 — pins (sha256 and the dry run's constants): paste every line under the doc's freeze marker line (doc_body_freeze / doc_body = the freeze)")
    p = ctx_pins()
    for k, v in p.items():
        say(f"- {k}: {v}")
    miss = fz.freeze_missing(DOC, p)
    say(f"- freeze record: {'complete' if not miss else 'NOT YET under the marker: ' + str(len(miss)) + ' of ' + str(len(p)) + ' pins'}")
    absent = [k for k, v in p.items() if v == "ABSENT"]
    say(f"- absent inputs / outputs (named, not refused): {', '.join(absent) if absent else 'none'}")
    if not any(k.startswith("ctx_const_") for k in p):
        say("- the constants: NONE (no complete dry run on disk; run --dry-run first)")
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
    out += sorted(glob.glob(os.path.join(FROZEN_DIR, "01_ctx_frozen_*.py")))
    if os.path.isdir(OUT_DIR):
        out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR) if os.path.isfile(os.path.join(OUT_DIR, f)))
    return out


def ctx_reset(say, reason: str, root: str = None) -> int:
    """N2 for a STOPPED run (the fix in the code): every artifact COPIED to run_events/<event>/ (each copy's sha256 verified, MANIFEST.tsv,
    DISCLOSURE.md, events.tsv appended), and only then removed from its place — never deleted. Then the dry run, --print-pins, the pins and
    the `fit_event_<event>` line pasted under the marker, and --run (it refuses an undisclosed or altered event)."""
    root = root or RUN_EVENTS
    if not (reason or "").strip():
        print("REFUSED: --reset needs the reason (the gate or bug that stopped the run, and the fix)", file=sys.stderr)
        return 2
    if os.path.exists(P_RUN):
        print(f"REFUSED: the run COMPLETED ({P_RUN}); it runs once and is never reset", file=sys.stderr)
        return 2
    if not os.path.exists(STOPPED):
        print("REFUSED: no STOPPED file — a reset follows a STOPPED run only", file=sys.stderr)
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
        sub = "out" if os.path.abspath(os.path.dirname(p_)) == os.path.abspath(OUT_DIR) else "module"
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
    msha = sha(CODE["ctx_module"])
    disc = [f"# run event {ev}: a stopped run archived before the re-run (N2) — disclose it under the doc's freeze marker", f"- reason: {reason.strip()}",
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
    say(f"# #705 CONTEXT RULES 01 — RESET (N2): run event {ev}; {len(rows)} files moved to {os.path.relpath(dest, REPO)}; reason: {reason.strip()}")
    say(f"- next, in order: --dry-run, --print-pins; paste every pin incl. `- fit_event_{ev}: {sha(man)}` and the disclosure under the marker; then --run")
    return 0


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    g = ap_.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--print-pins", "--pins", action="store_true", dest="print_pins")
    g.add_argument("--run", action="store_true")
    g.add_argument("--reset", metavar="REASON", default=None)
    args = ap_.parse_args(argv)
    say = rp.Say()
    if args.dry_run:
        exo = ctx_any_stage_output()
        if exo:
            print(f"REFUSED: stage output(s) already on disk: {exo[:6]} (the dry run precedes the run)", file=sys.stderr)
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
        return ctx_reset(say, args.reset)
    if args.run:
        return run_stage(say)
    return 1


if __name__ == "__main__":
    sys.exit(main())
