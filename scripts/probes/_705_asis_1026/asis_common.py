#!/usr/bin/env python3
"""#705 as-is read, shared module for steps 5-6 (docs/analysis/cb_asis_reconstruction_prereg_2026-10-26.md, §10). RULE-FREE BY CONSTRUCTION.

Paths, the seal (nothing dated after 2024-12-31 is read), the forbidden-folder guard (the seven outcome folders of the earlier reads), the
tokenize-based identifier scan, seeded draws through `rng_for`, and the COPIES of the rule-free helpers the plan lists: each copied as
source text from the rule-laden module it lives in, never imported (those modules load the rule library at import), and compared to its
source by the test (`tests/test_asis_points.py`) so a drift in either direction fails the build. `COPIED` below is the registry the test
iterates (the population is derived from it, never hand-listed in the test).

THE OPERATOR'S PRINCIPLE (2026-10-26): "stop trying to pigeon hole his trades, we're starting without any preconceptions, I want to reverse
eng his trades as they are, not as we want them to be and fit into our rules, that reconciliation comes later." Nothing here names a rule,
a pattern, a level of our library or a buy day of ours; the identifier scan refuses the excluded names of the plan's §3.1 as whole
identifiers or whole string literals (the list lives in `forbidden_identifiers.txt`, a data file, so this module can hold the scan without
holding the names).

The copies reference a few names of their home modules (`rev.`, `R.`, `cb.`, `rp.`); those are SHIMS defined here (plain namespaces over
the copied functions), so the copied text stays byte-identical and nothing is imported.

READINGS where the plan is silent, ambiguous or contradicts itself (numbered; the main loop decides):
  R1  Four helpers carry a parameter named with one of the excluded single-letter identifiers of §3.1 (the buy-day letter) in their source:
      `session_end_minute`, `bar_sym`, `covered_tree`, `minute_state`. A byte-identical copy would fail the identifier scan the plan also
      requires. The scan wins (stricter): the copy renames that ONE parameter to `d`, and the copy test compares the copy with the source
      after the same single NAME-token rename (tokenize), byte for byte otherwise. Declared per entry in `COPIED` (`renames`).
  R2  `MinuteStore` cannot be copied whole: its `h60` method and `all_trees` use names the scan refuses (`h60_bars`, `trees_for` reads a
      setup tag) and `restricted` serves a gate of the intraday read. The class here is built from BYTE-IDENTICAL copies of the methods
      step 5 needs (`__init__`, `check_forbid`, `state`, `seal`, `_tree`, `preload`, `get`, each compared to its source) plus one method of
      ours, `all_trees`, a fixed tree order with no setup tag (the inventory: every (symbol, session) pair sits in exactly ONE tree, so the
      order cannot change a read). `h60`, `restricted` are not copied.
  R3  `runner.load_daily` has no cut and reads the whole 13.8M-row era-B export; the plan's §7 demands the cut at read. The sealed loader
      `load_daily_subset` (chunked, `cut=`, `keep=`) of `_705_qm_replay_1023/01_replay.py` is copied instead, with `load_done` (the
      fetch-log reader with the cut). That file is not one of the four forbidden folders; it is still never imported.
  R4  `smas_for` is copied as it is (fixed 10/20/50 through `rev.sma_series`); the seven-length sweep the plan asks for is `smas_sweep`,
      ours, over the copied `sma_series` / `_roll_mean`.
  R5  `bars_for(D, t)` of the runner has a parameter named with the other excluded single letter; it is not copied. `bars_of_ticker` is
      ours (the same slice of the flat arrays through the copied `daily_bars_from_arrays`).
  R6  `minute_bars_from_rows` returns the cb module's `MinuteBars`; `MinuteBars`, `minute_bars_from_lists`, `DailyBars`,
      `daily_bars_from_arrays` are copied from `agents/market_intelligence/consolidation_breakout.py` (data containers with validation,
      no rule) and served through the `cb` shim, so the cb module is never imported.
  R7  Step 5 reads `snapshots.tsv` / `entries.tsv` / `exits.tsv` (the already-built frame table and windows); it does not rebuild the
      timeline, so `load_snapshots`, `dedupe_uploads`, `full_flag`, `blip_fill`, `lookalike_pairs`, `timeline`, `build_timeline` and
      `panel_clocks` are NOT copied here (step 6 copies what it needs). The frame's clock is the TSV's `clock` column (the reading
      `clock_of` wrote), re-read on every day.
  R8  The lexicon holds no rename evidence that can DERIVE GSX -> GOTU or SBE -> CHPT (GSX has no era-A rows and its era-B rows start
      after the seal; SBE is absent, only SBE.U is listed), so "extending the alias join from the lexicon's own rename evidence" cannot be
      computed from that file. Stricter reading: `RENAMES` is a hand-entered two-row table cited to the inventory (data.md §3.1), applied
      by `extend_alias_renames` ONLY when the panel symbol has no era-A rows in the lexicon and the target has era-A rows; the windows it
      recovers are counted and printed; the coverage CLAIMS of the dry run are made on the pre-extension numbers the inventory measured,
      the post-extension numbers printed beside.
  R9  The calendar cache runs to 2026-10-16; `Sessions` is cut at 2024-12-31 by the caller (`sealed_sessions`), `load_sessions` stays as
      copied. The export calendars are asserted equal to it on their spans, so one bisect calendar serves every record (§10 guard 6).
  R10 `GuardStop` is defined here (the reverse read's is a bare Exception subclass; same shape).
  R11 The ledger, the dry-run marker and the pins are THIS read's files (`LEDGER`, `P_DRY`, `P_PINS` under scripts/probes/_705_asis_1026/);
      the copied `ledger_append` / `ledger_verify` / `dry_run_complete` read those names from this module.
  R12 (review F2) The daily and minute bars on disk are split-ADJUSTED to the fetch date (2026), not the prices he saw: NVDA 2020-10-21
      closes 13.52 on the bars against $540.99 raw; CHPT's 2025 1:20 reverse split puts SBE's Dec-2020 bars at $650-800. The plan's F10
      ("the numbers a person says and types") and step 6's R1 (his SPOKEN prices against our range) are about the prices he saw, so the
      plan's intent needs a raw factor, but its §10 pin list names no raw-price input. Stricter reading, listed for the main loop: TWO
      inputs are added and pinned — `raw_close_A` (`cb702_pre_v2/daily_raw_close.csv.gz`: ticker,date,RAW close for every export-A row,
      2016-01-04..2022-06-30, a data file of the #702 selection test; 573 of the 683 panel bar symbols align row for row with export A)
      and `splits_B` (`cb702/cb702_splits.psv`, the split list, cut at the seal at read). The factor of a session = raw(sym_a, d) / the
      close of the RECORD'S OWN export at d (`exact`); a session after the raw file's last row carries the ticker's last exact factor
      forward through the split list (`carried`); a name with no raw row at all takes the product of its listed splits after the session
      (`partial`: splits after the seal are unknown); otherwise 1.0 (`missing`). Every bar-space column stays as it is; `raw_factor`,
      `price_raw`, `range_lo_raw` / `range_hi_raw`, `avg_traded_price_raw`, `panel_price_raw` are ADDED; F10 levels are raw round
      numbers (price = level / factor); `dist_round` and the density tolerance are read in raw price (the $0.05 floor is a tick size).
      The helpers `raw_factor_for` (cb), `load_splits` and `factor_by_bar` (runner) are copied byte-identically; the subset loader is ours.

  R37-R39 (re-run 1, 2026-10-26; numbered in 01_points.py's docstring): the seventh minute tree `ASIS` (his pull, regular hours only) is last in
      `FILES` / `MINUTES` / `TREE_ORDER`; `PRE_PULL_TREES` names the six the inventory's claims were measured on; `ledger_verify` is ours (not
      a copy) and accepts run 1's archived files (`ARCHIVE_STAGE`, `archive_path`).

No network, no model client, no DB, no subagent. Nothing is opened at import.
"""
from __future__ import annotations

import bisect
import collections
import sys
import datetime as _dt
import glob
import gzip
import hashlib
import io
import os
import pickle
import re
import tokenize
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DOC = os.path.join(REPO, "docs", "analysis", "cb_asis_reconstruction_prereg_2026-10-26.md")

# ---- paths (local files only; the production server is never touched) -----------------------------------------------------------------
DATA = "/Users/alvinfung/apollo_data"
A_DIR = f"{DATA}/cb702_pre_v2"
B_DIR = f"{DATA}/cb702"
QS = f"{B_DIR}/qm_streams"
VIS = f"{QS}/vision"
H_DIR = f"{QS}/holdings_1024"
OUT_DIR = f"{QS}/asis_1026"
SUBS_GLOB = f"{QS}/subs/*.vtt"

FILES = {
    "entries": f"{H_DIR}/entries.tsv",
    "exits": f"{H_DIR}/exits.tsv",
    "snapshots": f"{H_DIR}/snapshots.tsv",
    "control": f"{H_DIR}/control.tsv",                                   # PINNED only (the plan's four holdings TSVs); never read
    "panel": f"{VIS}/positions_panel_all.jsonl",
    "calendar_cache": f"{VIS}/positions_pct_calendar.pkl.gz",           # (SPY sessions of both bar files, the overlap-close signatures)
    "lexicon": f"{VIS}/positions_ticker_lexicon_v2.tsv",
    "dedupe_A": f"{A_DIR}/dedupe_applied.tsv",
    "sessions_A": f"{A_DIR}/sessions.txt",
    "export_A": f"{A_DIR}/daily_closes_all.csv.gz",                     # 2016-01-04..2022-06-30, keyed by today's symbol
    "export_B": f"{B_DIR}/daily_closes_all.csv.gz",                     # 2021-09-27.., symbol of the day; cut at 2024-12-31 at read
    "done_A": f"{A_DIR}/minutes/_done.psv",
    "done_B": f"{B_DIR}/minutes/_done.psv",
    "done_EP": f"{B_DIR}/minutes_ep_1023/_done.psv",
    "done_EP2": f"{B_DIR}/minutes_ep_1024/_done.psv",
    "done_REV": f"{B_DIR}/minutes_rev_1024/_done.psv",
    "done_INTRA": f"{B_DIR}/minutes_intra_1025/_done.psv",
    "done_ASIS": f"{B_DIR}/minutes_asis_1026/_done.psv",                 # R37: the re-run 1 pull (his 'Yes' 2026-10-26), regular hours only
    "raw_close_A": f"{A_DIR}/daily_raw_close.csv.gz",                    # R12: ticker,date,RAW close of every export-A row (today's symbol)
    "splits_B": f"{B_DIR}/cb702_splits.psv",                             # R12: sym|exec_date|from|to; cut at the seal at read
}
MINUTES = {"A": f"{A_DIR}/minutes", "B": f"{B_DIR}/minutes", "EP": f"{B_DIR}/minutes_ep_1023", "EP2": f"{B_DIR}/minutes_ep_1024",
           "REV": f"{B_DIR}/minutes_rev_1024", "INTRA": f"{B_DIR}/minutes_intra_1025", "ASIS": f"{B_DIR}/minutes_asis_1026"}
TREE_ORDER = ("A", "B", "EP", "EP2", "REV", "INTRA", "ASIS")        # R37: ASIS LAST, so no pair already covered changes tree
PRE_PULL_TREES = ("A", "B", "EP", "EP2", "REV", "INTRA")            # R37: the six trees the inventory's coverage facts were measured on
FORBIDDEN_DIRS = tuple(f"{H_DIR}/{d}" for d in ("replay", "his_exits", "intraday", "reverse", "rule_mix", "reverse_fit_events",
                                                 "reverse_recount_cache"))        # guard (2): the seven outcome folders, never opened
OUTPUTS = {k: f"{OUT_DIR}/{k}.tsv" for k in ("candidates", "ranges", "coverage")}
P_DRY = os.path.join(HERE, "01_points_dryrun.txt")
P_PINS = os.path.join(HERE, "01_points_pins.txt")
P_RUN = os.path.join(HERE, "01_points.txt")
P_REFUSED = os.path.join(HERE, "01_points.refused.txt")   # a refused --run writes here, never P_RUN (a refusal must not poison the next run)
LEDGER = os.path.join(HERE, "01_ledger.tsv")
FORBIDDEN_NAMES_FILE = os.path.join(HERE, "forbidden_identifiers.txt")

# ---- constants ---------------------------------------------------------------------------------------------------------------------------
CUT_B = "2024-12-31"                 # the seal: nothing dated after this is read from any file (2025-26 stays for #710)
A_LAST = "2022-03-31"                # the bar-symbol rule of the inventory (§3): `sym_a` through here, `sym` after
SEED = 705
SIG_DATES = ("2021-10-01", "2021-11-01", "2021-12-01")   # the reader's overlap sessions (load_alias)
RENAMES = {"GSX": "GOTU", "SBE": "CHPT"}                 # R8: the two rename gaps the inventory found (data.md §3.1); hand-entered, cited


class GuardStop(Exception):
    pass


def checked(path) -> str:
    """Guard (2): refuse any path under one of the seven outcome folders. Called on every path this read opens."""
    p = os.path.abspath(str(path))
    for d in FORBIDDEN_DIRS:
        if p == d or p.startswith(d + os.sep):
            raise GuardStop(f"guard (2): {p} lies under a forbidden outcome folder ({d})")
    return p


def seal_date(d: str, what: str = "") -> None:
    """Guard (1): a date read from any file must be <= 2024-12-31."""
    if d > CUT_B:
        raise GuardStop(f"guard (1): a date after {CUT_B} was requested ({d}{' ' + what if what else ''}); 2025-26 is sealed")


# ---- the identifier scan (guard 3): whole NAME tokens and whole STRING literals, via tokenize --------------------------------------------
def load_forbidden_names(path: str = None) -> frozenset:
    with open(path or FORBIDDEN_NAMES_FILE, encoding="utf-8") as fh:
        return frozenset(ln.strip() for ln in fh if ln.strip() and not ln.startswith("#"))


def _string_value(tok: str) -> "str | None":
    """The value of a plain STRING token (no f-strings: those tokenize into parts); None when it cannot be evaluated."""
    try:
        import ast
        v = ast.literal_eval(tok)
    except Exception:
        return None
    return v if isinstance(v, str) else None


def scan_identifiers(paths, forbidden=None) -> list:
    """[(path, line, token)] for every NAME token or whole STRING literal in `paths` that is one of the forbidden names. Substrings never
    match (`era` inside `average`, `setup` inside `setup_paths`). f-string pieces: the names inside braces are NAME tokens and are scanned."""
    forb = forbidden if forbidden is not None else load_forbidden_names()
    hits = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            toks = list(tokenize.generate_tokens(fh.readline))
        for t in toks:
            if t.type == tokenize.NAME and t.string in forb:
                hits.append((p, t.start[0], t.string))
            elif t.type == tokenize.STRING:
                v = _string_value(t.string)
                if v is not None and v in forb:
                    hits.append((p, t.start[0], t.string))
    return hits



# ═════════════════════════════════════════════════════════════════════════════════════════════
# COPIES — byte-identical source text of the rule-free helpers (see the module docstring and `COPIED` at the end)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()

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

def et_seconds(et_time: str) -> "int | None":
    """'2020-05-20T10:40-04:00' -> 38400 (the ET wall clock of the frame's own clock read); '' -> None."""
    if not et_time or len(et_time) < 16:
        return None
    return int(et_time[11:13]) * 3600 + int(et_time[14:16]) * 60

def hhmm(sec: float) -> str:
    sec = int(sec) % 86400
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}"

def asof(s: Snap, S: Sessions) -> int:
    return S.lt(s.date) if s.ctx == "pre" else S.le(s.date)

def lo_after(s: Snap, S: Sessions) -> int:
    """The first session on which a buy / sell could be missing from snapshot s."""
    return S.gt(s.date) if s.ctx == "closed" else S.ge(s.date)

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


@dataclass
class Frame:
    """One row of `snapshots.tsv` as step 5 reads it (the plan's rule-free frame columns). `asof` / `lo_after` read `.date` and `.ctx`."""
    idx: int
    frame_id: str
    vid: str
    date: str
    ctx: str
    clock: str                 # 'HH:MM' ET or '' (17 frames carry no clock read)
    full: bool
    symbols: list
    blip_filled: list

    @property
    def held(self) -> set:
        return set(self.symbols) | set(self.blip_filled)


Snap = Frame     # the copied `asof` / `lo_after` annotate their frame as `Snap`


def sealed_sessions() -> Sessions:
    """R9: the copied calendar, cut at the seal."""
    S = load_sessions()
    return Sessions([d for d in S.cal if d <= CUT_B])


def extend_alias_renames(alias: dict, lex: dict, tally: collections.Counter) -> dict:
    """R8: the two hand-entered renames, applied only when the panel symbol has NO era-A rows in the lexicon and the target HAS them."""
    out = dict(alias)
    n = 0
    for old, new in RENAMES.items():
        if old in out:
            continue
        if lex.get(old, ("",))[0]:
            tally["rename_skipped_has_era_a"] += 1
            continue
        if not lex.get(new, ("",))[0]:
            tally["rename_skipped_target_absent"] += 1
            continue
        out[old] = new
        n += 1
    tally["alias_rename_table"] = n
    return out


@dataclass(frozen=True, eq=False)
class DailyBars:
    """Ascending daily bars. `eq=False`: numpy fields make a generated __eq__ ambiguous."""
    dates: list            # list[datetime.date], strictly ascending
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray

    def __len__(self) -> int:
        return len(self.c)

    def slice(self, lo: int, hi: int) -> "DailyBars":
        """Sessions [lo, hi) — e.g. `bars.slice(E + 1, E + 2 + horizon)` is the forward walk input:
        horizon + 1 sessions, the extra one being the next open a trail signal on the horizon
        session fills at (see `walk_exit`'s CALLER CONTRACT)."""
        return DailyBars(self.dates[lo:hi], self.o[lo:hi], self.h[lo:hi], self.l[lo:hi],
                         self.c[lo:hi], self.v[lo:hi])

def daily_bars_from_arrays(dates, o, h, l, c, v) -> DailyBars:
    """Validate and freeze. Raises ValueError on a length mismatch, non-ascending dates or a
    non-finite value — a silent NaN would make every comparison False and read as a pass."""
    dates = list(dates)
    arrs = [np.asarray(x, dtype=float) for x in (o, h, l, c, v)]
    n = len(dates)
    if any(a.shape != (n,) for a in arrs):
        raise ValueError("daily bars: dates/o/h/l/c/v lengths differ")
    if any(dates[k] >= dates[k + 1] for k in range(n - 1)):
        raise ValueError("daily bars: dates must be strictly ascending")
    if not all(np.isfinite(a).all() for a in arrs):
        raise ValueError("daily bars: non-finite value")
    return DailyBars(dates, *arrs)

@dataclass(frozen=True, eq=False)
class MinuteBars:
    """Regular-hours minute bars of ONE session. `minute` = minutes since 09:30 ET (0..389),
    strictly ascending; gaps are allowed (a thin minute has no bar)."""
    minute: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray

    def __len__(self) -> int:
        return len(self.minute)

def minute_bars_from_lists(minute, o, h, l, c, v) -> MinuteBars:
    m = np.asarray(minute, dtype=np.int64)
    arrs = [np.asarray(x, dtype=float) for x in (o, h, l, c, v)]
    n = len(m)
    if any(a.shape != (n,) for a in arrs):
        raise ValueError("minute bars: lengths differ")
    if n and (m[0] < 0 or m[-1] > 389 or (np.diff(m) <= 0).any()):
        raise ValueError("minute bars: minute must be strictly ascending within 0..389")
    if not all(np.isfinite(a).all() for a in arrs):
        raise ValueError("minute bars: non-finite value")
    return MinuteBars(m, *arrs)

@dataclass
class Daily:
    tickers: list           # sorted
    start: np.ndarray       # flat-array offsets per ticker id
    stop: np.ndarray
    ci: np.ndarray          # SPY-calendar index of every flat row
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    cal: list               # list[date] - SPY's sessions
    tid: dict               # ticker -> id
    n_hole_tickers: int = 0  # tickers with >= 1 missing SPY session inside their own span
    n_holes: int = 0         # such missing-session breaks, all tickers
    raw_c: "np.ndarray | None" = None   # RAW close per flat row (`--raw-close`, the pre-2022 Alpaca era); None = the split list

H60_EARLY_CLOSE = frozenset({
    "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29", "2019-12-24", "2020-11-27",
    "2020-12-24", "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29", "2024-12-24", "2025-07-03",
    "2025-11-28", "2025-12-24"})                         # the 13:00 closes (read from the files, matching the exchange's list)

H60_EARLY_CUT = 210                                      # minutes >= 13:00 on those days are after-hours prints: dropped for the bar entries ONLY

def gz_complete_members(path: Path) -> tuple:
    """([text of each COMPLETE gzip member, in order], truncated). A truncated or corrupt member (a kill mid-append) and
    anything after it is dropped and `truncated` is True. `gzip.open` cannot be used for this: it raises on the broken
    member and discards the decoded data of the complete members still in its read buffer."""
    raw = Path(path).read_bytes()
    mv, pos, parts, truncated = memoryview(raw), 0, [], False
    while pos < len(raw):
        d = zlib.decompressobj(wbits=31)
        try:
            data = d.decompress(mv[pos:])
        except zlib.error:
            truncated = True
            break
        if not d.eof:
            truncated = True
            break
        parts.append(data.decode("utf-8", errors="replace"))
        pos = len(raw) - len(d.unused_data)
    return parts, truncated

def read_minute_file(path: Path, want: "set | None" = None) -> tuple:
    """({ticker: [field lists]}, info) from one `<date>.psv.gz` (`ticker|minute|o|h|l|c|v`, multi-member gzip). A BLOCK
    is a maximal run of consecutive lines for one ticker INSIDE ONE gzip member - a block never spans a member
    boundary. The fetcher writes exactly ONE member per symbol per fetch (`fetch_minutes.fetch_date.settle`), so a ticker
    that appears again - in a later member, including the member right after its own (a crash lost its done-line, so the
    resume re-fetched it FIRST) - is a re-fetch and its LAST block REPLACES the earlier one: the fetcher's documented
    reader contract. A truncated tail member is dropped (`info["truncated"]`); a cut never splits a block. `want` limits
    the work to the tickers a date's candidates need."""
    members, truncated = gz_complete_members(path)
    blocks: dict = {}
    info = {"bad_lines": 0, "refetched": 0, "truncated": truncated}
    for text in members:
        prev, cur = None, None                  # a run is per member: the next member's first ticker starts a new block
        for line in text.splitlines():
            f = line.split("|")
            if len(f) != 7:
                if line.strip():
                    info["bad_lines"] += 1
                continue
            t = f[0]
            if t != prev:
                prev = t
                if want is not None and t not in want:
                    cur = None
                    continue
                if t in blocks:
                    info["refetched"] += 1
                cur = []
                blocks[t] = cur
            if cur is not None:
                cur.append(f)
    return blocks, info

def minute_bars_from_rows(rows: list) -> "cb.MinuteBars | None":
    """Validated MinuteBars, or None when the block is unusable (duplicate/unsorted minutes, out of 0..389, a
    non-finite or unparseable value) - the caller records `minutes_state = invalid` and the module abstains."""
    try:
        return cb.minute_bars_from_lists([int(r[1]) for r in rows], [float(r[2]) for r in rows],
                                         [float(r[3]) for r in rows], [float(r[4]) for r in rows],
                                         [float(r[5]) for r in rows], [float(r[6]) for r in rows])
    except (ValueError, IndexError):
        return None

def minute_date_files(minutes_dir: Path) -> dict:
    """{date_iso: path} for every `<date>.psv.gz` in the directory."""
    out = {}
    for p in sorted(Path(minutes_dir).glob("*.psv.gz")):
        try:
            out[date.fromisoformat(p.name[:-len(".psv.gz")]).isoformat()] = p
        except ValueError:
            continue
    return out

def load_daily_subset(path: str, keep: "set | None" = None, cut: "str | None" = None, chunksize: int = 2_000_000) -> tuple:
    """`runner.load_daily`'s flat arrays (the same construction, line for line after the read — parity-tested on synthetic files) from
    the export's rows of the tickers in `keep` (None = all; SPY is always kept: it defines the calendar) with every row dated after `cut`
    DROPPED AT READ, chunk by chunk, and the cut asserted. -> (Daily, info)."""
    parts, info = [], Counter()
    keep = None if keep is None else set(keep) | {"SPY"}
    for ch in pd.read_csv(path, header=None, names=["ticker", "d", "o", "h", "l", "c", "v"],
                          dtype={"ticker": str, "d": str, "o": float, "h": float, "l": float, "c": float, "v": float},
                          keep_default_na=False, chunksize=chunksize):
        info["rows_read"] += len(ch)
        if cut is not None:
            m = ch["d"] <= cut
            info["dated_after_cut"] += int((~m).sum())
            ch = ch[m]
        if keep is not None:
            ch = ch[ch["ticker"].isin(keep)]
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    if cut is not None:
        assert df["d"].max() <= cut, f"a row dated after {cut} survived the read"
    info["rows_kept"] = len(df)
    # ---- from here: runner.load_daily, unchanged in substance ------------------------------------------------------------------
    codes, uniques = pd.factorize(df["ticker"], sort=True)
    days = pd.to_datetime(df["d"], format="%Y-%m-%d").to_numpy().astype("datetime64[D]").astype(np.int64)
    order = np.lexsort((days, codes))
    codes, days = codes[order], days[order]
    cols = {k: df[k].to_numpy(dtype=float)[order] for k in "ohlcv"}
    del df
    tickers = [str(t) for t in uniques]
    tid = {t: k for k, t in enumerate(tickers)}
    bounds = np.concatenate(([0], np.flatnonzero(np.diff(codes)) + 1, [len(codes)]))
    start, stop = bounds[:-1], bounds[1:]
    assert len(start) == len(tickers)
    spy = tid["SPY"]
    cal_days = days[start[spy]:stop[spy]]
    assert (np.diff(cal_days) > 0).all(), "SPY calendar not strictly ascending"
    ci = np.searchsorted(cal_days, days)
    on_cal = (ci < len(cal_days)) & (cal_days[np.minimum(ci, len(cal_days) - 1)] == days)
    if not on_cal.all():
        bad = sorted({tickers[k] for k in np.unique(codes[~on_cal])})
        raise AssertionError(f"{len(bad)} tickers have bar dates off the SPY calendar, e.g. {bad[:10]}")
    same = codes[1:] == codes[:-1]
    assert (days[1:][same] > days[:-1][same]).all(), "dates not strictly ascending within a ticker"
    for k, a in cols.items():
        assert np.isfinite(a).all(), f"non-finite {k}"
    brk = same & (np.diff(ci.astype(np.int64)) != 1)
    n_holes, n_hole_tickers = int(brk.sum()), int(len(np.unique(codes[1:][brk])))
    cal = [date.fromordinal(int(d) + 719163) for d in cal_days]
    return R.Daily(tickers, start, stop, ci.astype(np.int32), cols["o"], cols["h"], cols["l"], cols["c"], cols["v"], cal, tid,
                   n_hole_tickers, n_holes), info

def load_done(path: str, cut: "str | None" = None) -> tuple:
    """`runner.load_done_pairs` with era B's rows dated after `cut` dropped at read (counted) -> ({(date, ticker): status}, n_dropped)."""
    out, dropped = {}, 0
    with open(path) as fh:
        for line in fh:
            f = line.rstrip("\n").split("|")
            if len(f) < 4:
                continue
            if cut is not None and f[0] > cut:
                dropped += 1
                continue
            out[(f[0], f[1])] = f[3]
    if cut is not None:
        assert all(d <= cut for d, _ in out), "a fetch-log row dated after the cut survived"
    return out, dropped

def tree_sha(paths: list) -> str:
    """sha256 over (basename, sha256(file)) of the given files, sorted — the minute tree this read opens, and nothing else."""
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(os.path.basename(p).encode() + b"\0" + sha(p).encode() + b"\n")
    return h.hexdigest()

FREEZE_MARKER = "<!-- FREEZE -->"

_MARKER_LINE = re.compile(rb"^" + re.escape(FREEZE_MARKER.encode()) + rb"[ \t]*\r?$", re.M)

def marker_spans(raw: bytes) -> list:
    return [m.span() for m in _MARKER_LINE.finditer(raw)]

def doc_body_sha(doc: str) -> str:
    """sha256 of the doc's BYTES above its one line-anchored marker line (the whole file when there is not exactly one). At RUN time."""
    with open(doc, "rb") as fh:
        raw = fh.read()
    sp = marker_spans(raw)
    return hashlib.sha256(raw[:sp[0][0]] if len(sp) == 1 else raw).hexdigest()

def freeze_missing(doc: str, p: dict) -> list:
    """The pins NOT yet written below the doc's marker line. Not exactly one line-anchored marker -> every pin is missing (refused)."""
    with open(doc, "rb") as fh:
        raw = fh.read()
    sp = marker_spans(raw)
    if len(sp) != 1:
        return list(p)
    tail = raw[sp[0][1]:].decode("utf-8", errors="replace")
    return [k for k, v in p.items() if v not in tail]

def raw_factor_for(on: date, splits: Sequence[tuple]) -> float:
    """adjusted close x factor = RAW close on `on`. `splits` = [(execution_date, split_to /
    split_from), ...]; the factor is the product of the ratios of splits executing AFTER `on`
    (a 10:1 forward split -> 10, a 1:10 reverse -> 0.1). On the execution date itself the
    price is already post-split, so that split is excluded."""
    f = 1.0
    for exec_date, ratio in splits:
        if not ratio > 0:
            raise ValueError(f"split ratio must be > 0, got {ratio!r}")
        if exec_date > on:
            f *= float(ratio)
    return f

def load_splits(path: Path, through: "date | None" = None) -> dict:
    """cb702_splits.psv -> {ticker: [(execution_date, split_to / split_from), ...]} (deduplicated).
    `through` = the last session of the price export: a split that EXECUTES AFTER it is not in the adjusted
    series yet, so `raw = adjusted x factor` must not multiply it in (it would make every bar of that
    ticker's raw price wrong). Splits executing ON `through` are kept (that bar is already post-split)."""
    seen, out = set(), defaultdict(list)
    for line in path.read_text().splitlines():
        f = line.split("|")
        if len(f) < 4:
            continue
        key = (f[0], f[1], f[2], f[3])
        if key in seen:
            continue
        seen.add(key)
        ex = date.fromisoformat(f[1])
        if through is not None and ex > through:
            continue
        out[f[0]].append((ex, float(f[3]) / float(f[2])))
    for v in out.values():
        v.sort()
    return {k: v for k, v in out.items() if v}

def factor_by_bar(dates: list, splits: list) -> np.ndarray:
    """RAW-price factor per bar: `cb.raw_factor_for(dates[i], splits)`, evaluated once per run of bars
    between split execution dates (the factor only changes when a split date is crossed)."""
    n = len(dates)
    out = np.ones(n)
    if not splits:
        return out
    ex = sorted(s[0] for s in splits)
    last_key, last_f = None, 1.0
    for i in range(n):
        key = bisect.bisect_right(ex, dates[i])
        if key != last_key:
            last_key, last_f = key, cb.raw_factor_for(dates[i], splits)
        out[i] = last_f
    return out


# ---- shims: the names the copied text reads from its home modules, bound to the copies above --------------------------------------------
cb = SimpleNamespace(DailyBars=DailyBars, daily_bars_from_arrays=daily_bars_from_arrays, MinuteBars=MinuteBars,
                     minute_bars_from_lists=minute_bars_from_lists, raw_factor_for=raw_factor_for)
R = SimpleNamespace(Daily=Daily, H60_EARLY_CLOSE=H60_EARLY_CLOSE, H60_EARLY_CUT=H60_EARLY_CUT, read_minute_file=read_minute_file,
                    minute_bars_from_rows=minute_bars_from_rows, minute_date_files=minute_date_files)


SESSION_END, EARLY_END = 390, R.H60_EARLY_CUT       # the close as a minute bound: 16:00 = 390, 13:00 = 210

EARLY_CLOSE = frozenset(R.H60_EARLY_CLOSE)          # the 13:00 closes (20 listed; 17 on or before 2024-12-31)

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

def session_end_minute(d: str) -> int:
    return EARLY_END if d in EARLY_CLOSE else SESSION_END

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

def smas_for(bars) -> dict:
    return _SMAS.get(bars, lambda b: {10: rev.sma_series(b, 10), 20: rev.sma_series(b, 20), 50: rev.sma_series(b, 50)})

def _roll_mean(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out

def sma_series(bars, n: int) -> np.ndarray:
    return _roll_mean(np.asarray(bars.c, dtype=float), n)

def bar_sym(d: str, sym_a: str, sym: str) -> str:
    return sym_a if d <= A_LAST else sym

def covered_tree(d: str, tk: str, done: dict, files: dict, trees: tuple) -> "str | None":
    for tr in trees:
        if tr in done and done[tr].get((d, tk)) == "ok" and d in files[tr]:
            return tr
    return None

def minute_state(d: str, tk: str, done: dict, files: dict, trees: tuple) -> str:
    tr = covered_tree(d, tk, done, files, trees)
    if tr:
        return f"ok/{tr}"
    for t in trees:
        if t in done and done[t].get((d, tk)) == "empty":
            return f"empty/{t}"
    return "missing"

def subs_list_sha(paths: list = None) -> str:
    """One sha over the sorted (basename, sha256) list of the caption files (§13: 'one sha over the sorted list')."""
    return rp.tree_sha(paths if paths is not None else sorted(glob.glob(SUBS_GLOB)))

def ledger_append(stage: str, path: str) -> None:
    """Append-only: stage, printout path, sha256, time. Verified by --check against the files on disk."""
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a") as fh:
        if new:
            fh.write("stage\tpath\tsha256\ttime\n")
        fh.write(f"{stage}\t{path}\t{sha(path)}\t{_dt.datetime.now().isoformat(timespec='seconds')}\n")

ARCHIVE_STAGE = "archive_run1_"      # R38: the stage prefix of the ledger rows that record run 1's files after their rename


def archive_path(path: str) -> str:
    """R38: where run 1's copy of `path` lives after the re-run's archive step: `_run1` before the extension (candidates.tsv ->
    candidates_run1.tsv, 01_points.txt -> 01_points_run1.txt)."""
    root, ext = os.path.splitext(path)
    return f"{root}_run1{ext}"


def ledger_verify() -> list:
    """Every ledger row's file must exist with the recorded sha (a deleted or regenerated printout is caught). -> the problems.
    R38 (ours, no longer a copy of the reverse read's): a row whose file is missing or changed is accepted ONLY when run 1's archived copy
    (`archive_path`) exists with the recorded sha AND the ledger carries an `archive_run1_*` row for that exact archived path and sha — the
    rename is a ledger fact, the content is checked, and anything else (a deleted or edited file with no archive) is still a problem."""
    if not os.path.exists(LEDGER):
        return ["ledger missing"]
    bad = []
    rows = pd.read_csv(LEDGER, sep="\t", dtype=str, keep_default_na=False).to_dict("records")
    archived = {(r["path"], r["sha256"]) for r in rows if r["stage"].startswith(ARCHIVE_STAGE)}
    for r in rows:
        if os.path.exists(r["path"]) and sha(r["path"]) == r["sha256"]:
            continue
        arc = archive_path(r["path"])
        if (not r["stage"].startswith(ARCHIVE_STAGE) and (arc, r["sha256"]) in archived and os.path.exists(arc) and sha(arc) == r["sha256"]):
            continue
        bad.append(f"{r['path']}: " + ("missing" if not os.path.exists(r["path"]) else "changed since the ledger recorded it"))
    return bad

def dry_run_complete(path: str = None) -> bool:
    """True when the dry run printout exists and its last non-empty line says DRY RUN COMPLETE (a STOPPED dry run also writes the file;
    guard (3) must not accept it — check L3)."""
    path = path or P_DRY
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    return bool(lines) and lines[-1].startswith("DRY RUN COMPLETE")


rev = SimpleNamespace(covered_tree=covered_tree, minute_state=minute_state, sma_series=sma_series)
rp = SimpleNamespace(tree_sha=tree_sha, load_done=load_done)
_SMAS = IdCache()      # per bars object: {10, 20, 50: series} (the copied `smas_for`)
_SWEEP = IdCache()     # per bars object: the seven-length sweep (ours)
SMA_SWEEP = (5, 8, 10, 13, 20, 30, 50)


def smas_sweep(bars) -> dict:
    """R4: the plan's seven-length sweep of simple averages of closes, through the copied `sma_series`."""
    return _SWEEP.get(bars, lambda b: {n: sma_series(b, n) for n in SMA_SWEEP})


def bars_of_ticker(daily: Daily, tk: str):
    """R5: (DailyBars, calendar-index array) of `tk` in the export, or (None, None) — the runner's slice of the flat arrays."""
    t = daily.tid.get(tk)
    if t is None:
        return None, None
    a, b = int(daily.start[t]), int(daily.stop[t])
    cidx = daily.ci[a:b]
    dates = [daily.cal[k] for k in cidx]
    return daily_bars_from_arrays(dates, daily.o[a:b], daily.h[a:b], daily.l[a:b], daily.c[a:b], daily.v[a:b]), cidx

def load_raw_close_subset(path: str, keep: set, cut: str) -> tuple:
    """R12: {ticker: (dates_iso list, raw closes array)} for the tickers in `keep` from the headerless `ticker,date,raw_close` file, every
    row dated after `cut` DROPPED AT READ (counted) and the cut asserted; the dates of each ticker are sorted and asserted unique.
    -> (map, info). The RAW factor of a bar is then raw / the close of the RECORD'S OWN export at that session (never a factor from the
    other export: the two vendors disagree on CBIO by 36x)."""
    keep, parts, info = set(keep), [], Counter()
    for ch in pd.read_csv(path, header=None, names=["ticker", "d", "c"], dtype={"ticker": str, "d": str, "c": float},
                          keep_default_na=False, chunksize=2_000_000):
        info["rows_read"] += len(ch)
        m = ch["d"] <= cut
        info["dated_after_cut"] += int((~m).sum())
        ch = ch[m]
        parts.append(ch[ch["ticker"].isin(keep)])
    df = pd.concat(parts, ignore_index=True)
    if len(df):
        assert df["d"].max() <= cut, f"a raw-close row dated after {cut} survived the read"
    assert np.isfinite(df["c"].to_numpy()).all() and (df["c"].to_numpy() > 0).all(), "non-positive / non-finite raw close"
    out = {}
    for t, g in df.groupby("ticker", sort=True):
        g = g.sort_values("d")
        ds = g["d"].tolist()
        assert len(set(ds)) == len(ds), f"raw close: duplicate dates for {t}"
        out[t] = (ds, g["c"].to_numpy(dtype=float))
    info["rows_kept"], info["tickers"] = int(len(df)), len(out)
    return out, info


def load_splits_sealed(path: str = None) -> tuple:
    """R12: the copied `load_splits` with `through` = the seal, so a split executing after 2024-12-31 is never read into a factor (the rows
    are still in the file; the copy drops them by date). -> (splits, n_dropped_after_seal)."""
    p = Path(checked(path or FILES["splits_B"]))
    all_ = load_splits(p)
    cut = load_splits(p, through=date.fromisoformat(CUT_B))
    return cut, sum(len(v) for v in all_.values()) - sum(len(v) for v in cut.values())


SEALED_FILES = {}      # tree -> date files after the seal left unopened by load_done_all (printed by the dry run)


def load_done_all() -> tuple:
    """The six trees' fetch logs (every one read with the seal) and their date files up to the seal. -> (done, files)."""
    done, files = {}, {}
    for tr in TREE_ORDER:
        done[tr], _ = load_done(checked(FILES[f"done_{tr}"]), cut=CUT_B)
        all_files = minute_date_files(checked(MINUTES[tr]))
        files[tr] = {d: p for d, p in all_files.items() if d <= CUT_B}     # a date file after the seal is never opened (tree B holds 449)
        SEALED_FILES[tr] = len(all_files) - len(files[tr])
    return done, files


class MinuteStore:
    """R2: the per-(date, bar symbol) minute cache with the seal. The methods marked COPY are byte-identical to the intraday read's
    `MinuteStore` (compared by the test); `all_trees` is ours (fixed order, no setup tag)."""

    def all_trees(self, b=None) -> tuple:
        return tuple(t for t in TREE_ORDER if t in self.done)

    # COPY
    def __init__(self, done: dict, files: dict):
        self.done, self.files = done, files
        self.cache = {}            # (d, tk) -> MinuteBars | None
        self.h60_cache = {}        # (d, tk) -> list | None
        self.reads = Counter()
        self.forbid = frozenset()  # guard (5) per (bar symbol, date): pairs a FIT stage may not read (set by the stage; empty in the check)

    # COPY
    def check_forbid(self, d: str, tk: str) -> None:
        if (tk, d) in self.forbid:
            raise GuardStop(f"guard (5): minutes of {tk} on {d} lie after the buy day of a check-side trade on that name; a fit stage may not read them")

    # COPY
    def state(self, d: str, tk: str, b=None) -> str:
        return rev.minute_state(d, tk, self.done, self.files, self.all_trees(b))

    # COPY
    @staticmethod
    def seal(d: str) -> None:
        if d > CUT_B:
            raise GuardStop(f"guard (12): a minute date after {CUT_B} was requested ({d}); 2025-26 is sealed")

    # COPY
    def _tree(self, d: str, tk: str, b=None) -> "str | None":
        return rev.covered_tree(d, tk, self.done, self.files, self.all_trees(b))

    # COPY
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

    # COPY
    def get(self, d: str, tk: str, b=None):
        self.seal(d)
        self.check_forbid(d, tk)
        if (d, tk) not in self.cache:
            self.preload([(d, tk, b)])
        return self.cache[(d, tk)]



RULE_FOLDERS = ("_705_holdings_1024", "_705_reverse_1024", "_705_intraday_1025", "_cb_backtest")
RULE_MODULE_FILES = (("_705_qm_replay_1023", "02_execution_variants.py"), ("market_intelligence", "consolidation_breakout.py"),
                     ("_cb_backtest", "runner.py"), ("backtest_data_audit", "security_type_check.py"))   # (parent folder, file)


def rule_modules_loaded(modules: dict = None) -> list:
    """Guard (3), the import test: the loaded modules whose file lies in one of the four rule folders or is one of the execution-variants,
    cb, runner or sec modules. The test runs it in a fresh interpreter after importing each step module; main() runs it as a belt."""
    mods = sys.modules if modules is None else modules
    out = []
    for name, mod in list(mods.items()):
        f = getattr(mod, "__file__", None) or ""
        if not f:
            continue
        parts = Path(f).parts
        if set(parts) & set(RULE_FOLDERS) or (len(parts) >= 2 and tuple(parts[-2:]) in RULE_MODULE_FILES):
            out.append(name)
    return sorted(out)


def pins(doc: str = None, include_outputs: bool = True) -> dict:
    """R11: every pin of THIS read — the inputs (the four holdings TSVs, the panel, the calendar cache, the lexicon, the dedupe map, the
    era-A sessions, the two exports as files, the six fetch logs), the caption list, this module and the step modules, the doc body."""
    p = {}
    for name, path in FILES.items():
        p[name] = sha(checked(path)) if os.path.exists(path) else "ABSENT"
    p["subs_list"] = subs_list_sha()
    for name in ("asis_common.py", "01_points.py", "forbidden_identifiers.txt"):
        path = os.path.join(HERE, name)
        p[name] = sha(path) if os.path.exists(path) else "ABSENT"
    if include_outputs:
        p["dryrun_printout"] = sha(P_DRY) if os.path.exists(P_DRY) else "ABSENT"
        p["run_printout"] = sha(P_RUN) if os.path.exists(P_RUN) else "ABSENT"
        p["ledger"] = sha(LEDGER) if os.path.exists(LEDGER) else "ABSENT"
    p["doc_body"] = doc_body_sha(doc or DOC)
    return p


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registry the copy test iterates: (source file, relative to the repo; name in the source; kind; NAME-token renames applied)
# kind: def | class | assign | method ("Class.method", compared against the method of the same name in this module's class)
# renames: {} or {"param_index": i, "to": name} — the i-th parameter of the source def is renamed (R1); the source name is read from the
# source's own AST by the test, never written here (the scan refuses it as a literal)
# ═════════════════════════════════════════════════════════════════════════════════════════════
COPIED = (
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'sha', 'def', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'Sessions', 'class', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'load_sessions', 'def', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'et_seconds', 'def', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'hhmm', 'def', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'asof', 'def', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'lo_after', 'def', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'load_lexicon', 'def', {}),
    ('scripts/probes/_705_holdings_1024/01_timeline.py', 'load_alias', 'def', {}),
    ('agents/market_intelligence/consolidation_breakout.py', 'DailyBars', 'class', {}),
    ('agents/market_intelligence/consolidation_breakout.py', 'daily_bars_from_arrays', 'def', {}),
    ('agents/market_intelligence/consolidation_breakout.py', 'MinuteBars', 'class', {}),
    ('agents/market_intelligence/consolidation_breakout.py', 'minute_bars_from_lists', 'def', {}),
    ('scripts/probes/_cb_backtest/runner.py', 'Daily', 'class', {}),
    ('scripts/probes/_cb_backtest/runner.py', 'H60_EARLY_CLOSE', 'assign', {}),
    ('scripts/probes/_cb_backtest/runner.py', 'H60_EARLY_CUT', 'assign', {}),
    ('scripts/probes/_cb_backtest/runner.py', 'gz_complete_members', 'def', {}),
    ('scripts/probes/_cb_backtest/runner.py', 'read_minute_file', 'def', {}),
    ('scripts/probes/_cb_backtest/runner.py', 'minute_bars_from_rows', 'def', {}),
    ('scripts/probes/_cb_backtest/runner.py', 'minute_date_files', 'def', {}),
    ('scripts/probes/_cb_backtest/runner.py', 'load_splits', 'def', {}),
    ('scripts/probes/_cb_backtest/runner.py', 'factor_by_bar', 'def', {}),
    ('agents/market_intelligence/consolidation_breakout.py', 'raw_factor_for', 'def', {}),
    ('scripts/probes/_705_qm_replay_1023/01_replay.py', 'load_daily_subset', 'def', {}),
    ('scripts/probes/_705_qm_replay_1023/01_replay.py', 'load_done', 'def', {}),
    ('scripts/probes/_705_qm_replay_1023/01_replay.py', 'tree_sha', 'def', {}),
    ('scripts/probes/_705_qm_replay_1023/02_execution_variants.py', 'FREEZE_MARKER', 'assign', {}),
    ('scripts/probes/_705_qm_replay_1023/02_execution_variants.py', '_MARKER_LINE', 'assign', {}),
    ('scripts/probes/_705_qm_replay_1023/02_execution_variants.py', 'marker_spans', 'def', {}),
    ('scripts/probes/_705_qm_replay_1023/02_execution_variants.py', 'doc_body_sha', 'def', {}),
    ('scripts/probes/_705_qm_replay_1023/02_execution_variants.py', 'freeze_missing', 'def', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'SESSION_END,EARLY_END', 'assign', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'EARLY_CLOSE', 'assign', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'rng_for', 'def', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'fnum', 'def', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'session_end_minute', 'def', {'param_index': 0, 'to': 'd'}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'IdCache', 'class', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'smas_for', 'def', {}),
    ('scripts/probes/_705_reverse_1024/01_rev.py', '_roll_mean', 'def', {}),
    ('scripts/probes/_705_reverse_1024/01_rev.py', 'sma_series', 'def', {}),
    ('scripts/probes/_705_reverse_1024/01_rev.py', 'bar_sym', 'def', {'param_index': 0, 'to': 'd'}),
    ('scripts/probes/_705_reverse_1024/01_rev.py', 'covered_tree', 'def', {'param_index': 0, 'to': 'd'}),
    ('scripts/probes/_705_reverse_1024/01_rev.py', 'minute_state', 'def', {'param_index': 0, 'to': 'd'}),
    ('scripts/probes/_705_reverse_1024/01_rev.py', 'subs_list_sha', 'def', {}),
    ('scripts/probes/_705_reverse_1024/01_rev.py', 'ledger_append', 'def', {}),
    ('scripts/probes/_705_reverse_1024/01_rev.py', 'dry_run_complete', 'def', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'MinuteStore.__init__', 'method', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'MinuteStore.check_forbid', 'method', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'MinuteStore.state', 'method', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'MinuteStore.seal', 'method', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'MinuteStore._tree', 'method', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'MinuteStore.preload', 'method', {}),
    ('scripts/probes/_705_intraday_1025/01_intra.py', 'MinuteStore.get', 'method', {}),
)
