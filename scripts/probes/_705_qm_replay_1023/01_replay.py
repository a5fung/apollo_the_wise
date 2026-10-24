#!/usr/bin/env python3
"""#705 — QULLAMAGGIE REPLAY 01: his own stream-confirmed calls, walked under his own rules, and the account they compound into
(docs/analysis/cb_qm_replay_prereg_2026-10-23.md). Registration only until the freeze; the real run happens ONCE after it.

What it does (the registration's §2-§8, nothing else):
  POPULATION  the Track A positive events — a bought / best label said ON OR BEFORE the breakout day E (era A 236, era B 9) — derived by the
              FROZEN Track A fit module's own `label_sets` + `assign_classes` (imported read-only), so the set is the registered one by
              construction; the 87 / 3 post-E-only events BESIDE (the hindsight reading) and the 127 / 6 strictly-before events beside.
  CONTROL     the same day's OTHER tl breakouts, the Track A round-3 exclusion (a row excluded only for a label said on or before its own E):
              era A 23,188, era B 345 — asserted.
  HIS RULES   entry ORH5 on E (`cb.entry_variants`: the first minute after the 5-minute opening range whose high clears max(ORH, the level),
              filled at that level or the open if gapped, 0.1% slippage), stop = the low of the day at the fill, skipped when wider than
              ADR20 (`too_wide`); exit `p33_s3_t10` (1/3 sold at the session-3 close, stop to breakeven, the rest on the first close under
              the 10-day SMA, filled at the next open, 120-session horizon) through `cb.walk_arms` — the function `runner.walk_arms` wraps
              (called directly because the account curve needs the exit EVENTS that `runner.arm_result` drops; parity tested). BESIDE:
              the 7 other S-grid arms (1/2 sold, day 5, the 20-day trail), his operator exit `pp` (`runner.exitpb_walk_arms`, unchanged),
              ORH1 and ORH60 under the primary arm. Re-entries are COUNTED, never walked.
  MEASURES    per trade R, tail first; month-block intervals (2,000 resamples, seed 702, one draw of months applied to BOTH arms) on the
              his-calls minus control difference, DATE-MATCHED: each control trade weighted by his trades / the control's trades in the
              same (date, first-break / retrigger) cell (filled + mature only; a cell the control does not cover is dropped and counted);
              the stratum-only (his first-break / retrigger shares) and the pooled differences beside.
  ACCOUNT     a chronological portfolio of HIS calls at HIS sizing (operator_shared_notes.md: risk 0.25-1% a trade, positions 10-20%, at
              most 30% of the account in one stock; the SSoT's article sizing min(20%, 1% / stop width)): start 1.0; 1% of equity risked per
              trade; position capped at 20% of equity; at most 30% of equity at cost in one stock (a second position takes the room left,
              else skipped and counted); no margin (a trade whose full position does not fit the free cash is SKIPPED and counted);
              year-end equity, yearly return, max drawdown; the SAME simulation on 200 same-day control draws (seed 702) as the band.
  FORK        written in the registration before any outcome: strong (the curve arm needs his curve above the band too) -> SELECTION;
              his curve strong but the band at or above it -> DATES / market; weak -> EXECUTION / data.

No subagent, no DB, no network. Read-only on every input. Nothing dated after 2024-12-31 is kept from any era-B file (dropped AT READ, asserted).

Run:  python3 scripts/probes/_705_qm_replay_1023/01_replay.py --dry-run   (loads everything, asserts the populations, checks minute
                                                                         coverage from the fetch logs, prints the pins; opens NO minute
                                                                         file, calls NO entry or exit function, computes NO outcome)
      python3 scripts/probes/_705_qm_replay_1023/01_replay.py             (the REAL run: refuses (exit 2) unless every pin incl. the doc-body
                                                                         hash is written under <!-- FREEZE --> in the doc, or if any
                                                                         output exists; writes 01_replay.txt + the trade tables)
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import importlib.util
import math
import os
import re
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
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from scripts.probes._cb_backtest import runner as R      # noqa: E402  (read-only: the fill, stop and exit walkers; hash-pinned)

cb = R.cb
# every fill pays the entry slippage `cb.entry_variants` defaults to (constants.ENTRY_SLIPPAGE_PCT, pinned in CODE): 0.1%, as registered
assert cb.ENTRY_SLIPPAGE_PCT == 0.001, cb.ENTRY_SLIPPAGE_PCT
import inspect as _inspect                                  # noqa: E402
assert _inspect.signature(cb.entry_variants).parameters["slippage"].default == 0.001

FIT_PATH = os.path.join(REPO, "scripts", "probes", "_705_track_a_1023", "02_fit_filter.py")


def _load_fit():
    """The FROZEN Track A fit module (pinned 3fca7bf4…), imported read-only for `label_sets` / `assign_classes` / `population_counts`."""
    spec = importlib.util.spec_from_file_location("_705_fit02_frozen", FIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_705_fit02_frozen"] = mod
    spec.loader.exec_module(mod)
    return mod


FIT = _load_fit()

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths
# ═════════════════════════════════════════════════════════════════════════════════════════════
DATA = "/Users/alvinfung/apollo_data"
A_DIR = f"{DATA}/cb702_pre_v2"
B_DIR = f"{DATA}/cb702"
TA = f"{B_DIR}/qm_streams/track_a_1023"
OUT_DIR = f"{B_DIR}/qm_streams/qm_replay_1023"
DOC = os.path.join(REPO, "docs", "analysis", "cb_qm_replay_prereg_2026-10-23.md")
PRINTOUT = os.path.join(HERE, "01_replay.txt")
DRY_PRINTOUT = os.path.join(HERE, "01_replay_dryrun.txt")
STOPPED = os.path.join(HERE, "01_replay.STOPPED.txt")
TRADE_IMPACT = os.path.join(REPO, "scripts", "backtest_data_audit", "trade_impact.py")
OUT_FILES = ("trades.tsv.gz", "g8_A.tsv", "g8_B.tsv", "g8_A_impact.txt", "g8_B_impact.txt", "account_his.tsv", "account_band.tsv")

FILES = {
    "labels_joined": f"{TA}/labels_joined.tsv",
    "matched_events": f"{TA}/matched_events.tsv",
    "moments": f"{B_DIR}/qm_streams/vision/graded_moments.tsv",
    "cand_A": f"{A_DIR}/out/candidates_tl_com.tsv",
    "cand_B": f"{B_DIR}/out/candidates.tsv",
    "export_A": f"{A_DIR}/daily_closes_all.csv.gz",
    "export_B": f"{B_DIR}/daily_closes_all.csv.gz",
    "sessions_A": f"{A_DIR}/sessions.txt",
    "guard_A": f"{A_DIR}/symbol_guard.tsv",
    "guard_A_audit": f"{A_DIR}/audit_1023/universe/symbol_guard_A.tsv",
    "guard_B": os.path.join(REPO, "scripts", "backtest_data_audit", "runs_2026-10-23", "universe", "symbol_guard_B.tsv"),
    "flags_A": f"{A_DIR}/audit_1023/price/A_flags.tsv",
    "flags_B": f"{DATA}/audit_runs_2026-10-23/B_flags.tsv",
    "verdict_A": f"{A_DIR}/audit_1023/verdict.txt",
    "done_A": f"{A_DIR}/minutes/_done.psv",
    "done_B": f"{B_DIR}/minutes/_done.psv",
}
MINUTES = {"A": f"{A_DIR}/minutes", "B": f"{B_DIR}/minutes"}
CODE = {
    "runner": os.path.join(REPO, "scripts", "probes", "_cb_backtest", "runner.py"),
    "registered_read": os.path.join(REPO, "scripts", "probes", "_cb_backtest", "registered_read.py"),
    "cb_module": os.path.join(REPO, "agents", "market_intelligence", "consolidation_breakout.py"),
    "constants": os.path.join(REPO, "agents", "market_intelligence", "constants.py"),   # ENTRY_SLIPPAGE_PCT, every fill's default
    "fit_module": FIT_PATH,
    "join_script": os.path.join(REPO, "scripts", "probes", "_705_track_a_1023", "01_join_labels.py"),
    "aplus_read": os.path.join(REPO, "scripts", "probes", "_cb_backtest", "aplus_read.py"),
    "trade_impact": TRADE_IMPACT,
    "replay_module": os.path.abspath(__file__),
    "replay_tests": os.path.join(HERE, "test_01_replay.py"),
}
# the pins the Track A freeze record already carries; any drift refuses before a number is read (dry run included)
PINNED = {
    "labels_joined": "d0299beba6f2d0def7947bb6e77eac008ced4586450bb260ceed51f7b0fdca3b",
    "matched_events": "4d07d6e542bf5064cacf5e446a20566e9a1cb17fd126efee560634a2f6cd11fc",
    "moments": "f2c81633de6c6765477368876e300c4636d34222b43a5b13245cdf96b8d3add0",
    "cand_A": "3c5a66dc3052d0a284cbfee8202f74deb4e5bb75c74565dd8147df015e1baa5a",
    "cand_B": "b75c828671171530225198f97fc1191c9bced8f9448b9b05aa46099d617ce0c7",
    "export_A": "0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d",
    "export_B": "ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba",
    "sessions_A": "098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0",
    "flags_A": "5358e31dc1b27d25c5143bdfca7a98b91a6c7a2d5b1da6c9c9d9ed9c55474c1d",
    "flags_B": "8bf843859afb70ea59edf6f11cda12160020936c8df3e978b6a819590ea5c3d5",
    "fit_module": "3fca7bf4f26ffcdf7152ddc9d4180c295aafe29067591def812fcc6884f38d27",
    "join_script": "6889819c41342c60831b0d62b277d47b677e4deaeab3443cbdde7a05d56b112c",
    "aplus_read": "e344277817db88de7af2e65ad8858d4ca515c3cc3a647b3e0a67e0df9f7ec9ee",
    "registered_read": "28fbc47f862f205071ab921af3a29f6093fca95e2d41e3a0f4a0f7afcd9aa449",
    "cb_module": R.EXITPB_MODULE_SHA,          # the `pp` registration's hard pin = the live shadow's module
}

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants (every number is the doc's)
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = "2024-12-31"                     # nothing dated after this is kept from any era-B file
HORIZON = R.HORIZON                      # 120 sessions (cb.EXIT_HORIZON)
ENTRY = "orh5"                           # PRIMARY entry
BESIDE_ENTRIES = ("orh1", "orh60")       # beside, primary arm only
PRIMARY_ARM = cb.PRIMARY_ARM             # p33_s3_t10
GRID_ARMS = tuple(f"p{p}_s{s}_t{t}" for p in (33, 50) for s in (3, 5) for t in (10, 20))   # the S grid: 1/3 | 1/2 x day 3 | 5 x SMA10 | 20
PP_ARM = "pp"                            # his operator exit (runner.EXITPB_ARMS["pp"]): beside
EXIT_SLIPS = (0.0, 0.001, 0.002)         # the standard's step 8: per exit leg; the entry already pays 0.1% (cb.ENTRY_SLIPPAGE_PCT)
SEED = 702
BOOT_DRAWS = 2000
BAND_DRAWS = 200
PER = 100.0
TAILS = (5.0, 10.0, 20.0)
REENTRY_WINDOW = 20                      # a later break of the same base within 20 sessions of E (Track A's T2 window) — COUNTED only
BREAK_PRE, BREAK_POST = cb.MIN_HISTORY, HORIZON   # a listed identity break in (E - 130, E] EXCLUDES the event (outcome-free, counted); one
                                                  # AFTER E cuts the walk's forward window at the session before it (`walk_event`), no exclusion
FORK_YEARS = (2017, 2018, 2019, 2020, 2021)
STRONG_YEAR_RET = 0.50                   # yearly return >= +50% ...
STRONG_YEARS_MIN = 2                     # ... in at least 2 of the 2017-21 years (at the primary sizing) ...
BAND_SHARE_MAX = 0.05                    # ... AND at most 5% of the same-day band's draws end at or above his final equity (primary config)
BAND_REGISTERED = "same-day (registered)"
EARLY_CLOSE = R.H60_EARLY_CLOSE          # the runner's 13:00-close list; ORH fills read minutes as stored (counted beside, G9)
EARLY_CUT = R.H60_EARLY_CUT              # 210 = 13:00 ET


@dataclass(frozen=True)
class Config:
    """One account-simulation configuration. PRIMARY = HIS sizing (docs/methodology/operator_shared_notes.md, the consolidation-breakout
    article: "positions 10-20% of the account; risk 0.25-1% a trade, rarely more than 1%; at most 30% of the account in one stock
    overnight"; the SSoT's article sizing, docs/setups/consolidation_breakout.md: position = min(20%, 1% / stop width)): `risk` 1% of
    equity, position `cap` 20% of equity, `stock_limit` 30% of equity AT COST in one ticker (None = no limit). `room`: "skip" = a trade
    whose full position does not fit the free cash is skipped (PRIMARY, no parameter), "trim" = it takes the free cash (beside).
    `same_ticker`: "allow" = a second position in a ticker already held is opened inside the stock limit (PRIMARY; Track A's
    every-event-walked unit), "skip" = it is skipped (beside)."""
    name: str
    risk: float = 0.01
    cap: float = 0.20
    stock_limit: "float | None" = 0.30
    room: str = "skip"
    same_ticker: str = "allow"
    exit_slip: float = 0.0


PRIMARY_CONFIG = Config("primary")
CONFIGS = (PRIMARY_CONFIG, Config("risk_0.25", risk=0.0025), Config("risk_0.5", risk=0.005), Config("cap_10", cap=0.10),
           Config("cap_30", cap=0.30), Config("room_trim", room="trim"), Config("same_ticker_skip", same_ticker="skip"),
           Config("exit_slip_0.1", exit_slip=0.001))

EXPECT = {                               # the populations this module ASSERTS (Track A §2h / §4 / §6; the fit module's own EXPECT)
    "stream_A": 81015, "first_A": 20650, "stream_B": 41200, "first_B": 12250,
    "pos_A": 236, "pos_fit": 170, "pos_hold": 66, "pos_B": 9,
    "neg_A": 23188, "neg_fit": 15107, "neg_hold": 8081, "neg_B": 345,
    "excl_A": 410, "excl_B": 7, "post_A": 87, "post_B": 3, "strict_A": 127, "strict_B": 6,
    # the ON-E split of his 236 (the fit module's `at0` = a bought / best label said ON E): 119 carry one, 109 rest ONLY on one (no label
    # strictly before E), 10 carry both; 127 strictly-before + 109 on-E-only = 236
    "at0_A": 119, "on_E_only_A": 109, "at0_and_strict_A": 10,
    "graded_dates_A": 156, "graded_dates_B": 7,
    "pos_first_A": 132, "pos_retrig_A": 104,          # Track A §6: GRADED's mix 132 first breaks / 104 retriggers of 236
    "cal_A": 1635, "cal_B": 821,
    # MEASURED by this module's dry run (2026-10-23) on `candidates.tsv` alone, NOT registration numbers: Track A's 174,495 / 328 sum
    # `candidates.tsv` AND `candidates_com.tsv` (the `com` level, which this read never opens)
    "cand_B_not_discovery": 109478, "cand_B_after_cut": 240,
}

SELL_KINDS = frozenset({"partial", "partial_r", "stop", "stop_gap", "trail", "mark", "cut", "day0_stop", "day0_gap"})
ORDER_OPEN, ORDER_BUY, ORDER_INTRADAY, ORDER_CLOSE = 0, 1, 2, 3


# ═════════════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ═════════════════════════════════════════════════════════════════════════════════════════════
class Say:
    def __init__(self):
        self.lines = []

    def __call__(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.lines.append(msg)

    def write(self, path: str) -> None:
        tmp = path + ".partial"
        with open(tmp, "w") as fh:
            fh.write("\n".join(self.lines) + "\n")
        os.replace(tmp, path)


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fmt(x, nd=2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "-"
    return f"{x:+.{nd}f}" if isinstance(x, float) else str(x)


def pct(x, nd=1) -> str:
    return "-" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{100.0 * x:.{nd}f}%"


def table(hdr: list, rows: list) -> list:
    w = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(hdr)]
    out = ["  " + " | ".join(str(h).ljust(w[i]) for i, h in enumerate(hdr)), "  " + "-+-".join("-" * x for x in w)]
    out += ["  " + " | ".join(str(c).ljust(w[i]) for i, c in enumerate(r)) for r in rows]
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# freeze lock (the fit module's pattern)
# ═════════════════════════════════════════════════════════════════════════════════════════════
FREEZE_MARKER = "<!-- FREEZE -->"


def doc_body_sha(doc: str) -> str:
    """sha256 of the doc's BYTES above the `<!-- FREEZE -->` marker (the whole file without one). Taken at RUN time."""
    with open(doc, "rb") as fh:
        return hashlib.sha256(fh.read().split(FREEZE_MARKER.encode(), 1)[0]).hexdigest()


def minute_files_used(era: str, dates: list) -> list:
    """The minute date files the walk set needs (era B: dated <= CUT_B only, asserted)."""
    files = R.minute_date_files(MINUTES[era])
    out = []
    for d in sorted(set(dates)):
        if era == "B":
            assert d <= CUT_B, d
        if d in files:
            out.append(str(files[d]))
    return out


def tree_sha(paths: list) -> str:
    """sha256 over (basename, sha256(file)) of the given files, sorted — the minute tree this read opens, and nothing else."""
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(os.path.basename(p).encode() + b"\0" + sha(p).encode() + b"\n")
    return h.hexdigest()


def pins(minute_dates: "dict | None" = None, doc: "str | None" = None) -> dict:
    p = {name: sha(path) for name, path in FILES.items()}
    p.update({name: sha(path) for name, path in CODE.items()})
    for era, dates in (minute_dates or {}).items():
        p[f"minutes_{era}_used"] = tree_sha(minute_files_used(era, dates))
    p["doc_body"] = doc_body_sha(doc or DOC)
    return p


def freeze_missing(doc: str, p: dict) -> list:
    """The pins NOT yet written under the doc's `<!-- FREEZE -->` marker (the real run refuses unless this is empty)."""
    txt = open(doc).read()
    if FREEZE_MARKER not in txt:
        return list(p)
    tail = txt.split(FREEZE_MARKER, 1)[1]
    return [k for k, v in p.items() if v not in tail]


def existing_outputs() -> list:
    out = [p for p in (PRINTOUT, STOPPED) if os.path.exists(p)]
    out += [os.path.join(OUT_DIR, f) for f in OUT_FILES if os.path.exists(os.path.join(OUT_DIR, f))]
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# loading — labels, candidates, the daily export (era B cut AT READ), the fetch logs
# ═════════════════════════════════════════════════════════════════════════════════════════════
LJ_COLS = ("vid", "ts", "screen_ticker", "sym", "s0", "era", "coverage", "grade", "is_bought", "is_not_yet", "is_best", "watch_at_s0",
           "c0_tl_at_s0", "delta_tl", "E_tl", "base_id_tl")
ME_COLS = ("era", "sym", "E_tl", "bought", "not_yet", "best")          # never r1_status / r2 (forward flags)
MO_COLS = ("video", "ts", "ticker", "quote")
CAND_COLS = ("ticker", "D", "E", "K", "base_id", "pole_date", "retrigger", "retrigger_chain", "pivot", "adr20", "split", "C1")
FORBIDDEN = {"open_E", "high_E", "low_E", "close_E", "vol_E", "breakout_vol_x", "gap_open_pct", "gap_over_1adr", "overlap_open",
             "r1_status", "r2", "r1_off_from_E", "delta_r1"}
assert not (FORBIDDEN & (set(LJ_COLS) | set(ME_COLS) | set(CAND_COLS))), "an E-day / forward column is on a read list"


def read_tsv(path: str, cols, keep=None, chunksize: int = 200_000) -> tuple:
    """A tab-separated file read as strings, only `cols`; `keep(chunk) -> (chunk, Counter)` filters each chunk AT READ."""
    parts, dropped = [], Counter()
    for ch in pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, usecols=list(cols), chunksize=chunksize):
        if keep is not None:
            ch, d = keep(ch)
            dropped.update(d)
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(cols))
    return df[list(cols)], dropped


def cand_keep_A(ch: pd.DataFrame) -> tuple:
    return ch[ch["K"] == "tl"], Counter()


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


# ═════════════════════════════════════════════════════════════════════════════════════════════
# populations (the frozen Track A classes)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def label_sets_from_files() -> dict:
    J, _ = read_tsv(FILES["labels_joined"], LJ_COLS)
    ME, _ = read_tsv(FILES["matched_events"], ME_COLS)
    MO, _ = read_tsv(FILES["moments"], MO_COLS)
    return FIT.label_sets(J, ME, MO, FIT.load_grade_rx())


def era_stream(e: str, cand: pd.DataFrame, ls: dict) -> SimpleNamespace:
    """One era's tl stream as the duck-typed `Era` the frozen `assign_classes` reads (name, ticker, E, base_id; it writes `cls`)."""
    ns = SimpleNamespace(name=e, ticker=cand["ticker"].to_numpy(dtype=str), E=cand["E"].to_numpy(dtype=str),
                         D=cand["D"].to_numpy(dtype=str), base_id=cand["base_id"].to_numpy(dtype=str),
                         retrigger=cand["retrigger"].astype(int).to_numpy(), pivot=cand["pivot"].astype(float).to_numpy(),
                         adr20=cand["adr20"].astype(float).to_numpy(), cls={})
    FIT.assign_classes(ns, ls)
    return ns


def population_counts(eras: dict) -> dict:
    c = FIT.population_counts(eras)
    A = eras["A"]
    c["stream_A"], c["stream_B"] = len(A.E), len(eras["B"].E)
    c["first_A"], c["first_B"] = int((A.retrigger == 0).sum()), int((eras["B"].retrigger == 0).sum())
    c["pos_first_A"] = int((A.cls["pos"] & (A.retrigger == 0)).sum())
    c["pos_retrig_A"] = int((A.cls["pos"] & (A.retrigger == 1)).sum())
    c["on_E_only_A"] = int((A.cls["pos"] & ~A.cls["strict"]).sum())
    c["at0_and_strict_A"] = int((A.cls["pos"] & A.cls["at0"] & A.cls["strict"]).sum())
    return c


def check_expect(got: dict, expect: dict) -> list:
    bad = []
    for k, want in expect.items():
        if k not in got:
            bad.append(f"{k}: NOT MEASURED (registered {want})")
        elif got[k] != want:
            bad.append(f"{k}: {got[k]} (registered {want})")
    return bad


@dataclass
class Event:
    era: str
    ticker: str
    D: str
    E: str
    base_id: str
    retrigger: int
    pivot: float
    adr20: float
    his: bool = False
    ctl: bool = False
    post: bool = False
    strict: bool = False
    first_of_base: bool = False          # the first HIS event of its (ticker, base_id) by E (the one-event-per-base reading)
    year: int = 0
    month: str = ""
    qqq: str = ""                        # "up" (QQQ close above its SMA10 AND SMA20 at D) | "mixed" | "down" (below both) | "" unknown
    minutes_state: str = ""             # ok | empty | missing (from the fetch log)
    break_pre: bool = False              # an identity break in (E - 130, E] (excluded)
    break_cut: str = ""                  # the date of the first identity break AFTER E inside the forward window, where the walk's forward
                                         # window was cut (the session before it is the last one read); real run only, never an exclusion
    early_close: bool = False
    keep: bool = True                    # in the walk set after the data exclusions


def build_events(eras: dict) -> list:
    """Every event of the walk set: HIS (pos) ∪ CTL (neg) ∪ POST (post-E-only, beside), each era; one Event per (era, ticker, E)."""
    evs = []
    for e, ns in eras.items():
        m = ns.cls["pos"] | ns.cls["neg"] | ns.cls["post"]
        for i in np.flatnonzero(m):
            E = str(ns.E[i])
            evs.append(Event(era=e, ticker=str(ns.ticker[i]), D=str(ns.D[i]), E=E, base_id=str(ns.base_id[i]),
                             retrigger=int(ns.retrigger[i]), pivot=float(ns.pivot[i]), adr20=float(ns.adr20[i]),
                             his=bool(ns.cls["pos"][i]), ctl=bool(ns.cls["neg"][i]), post=bool(ns.cls["post"][i]),
                             strict=bool(ns.cls["strict"][i]), year=int(E[:4]), month=E[:7], early_close=E in EARLY_CLOSE))
    seen = {}
    for ev in sorted((x for x in evs if x.his), key=lambda x: (x.era, x.ticker, x.base_id, x.E)):
        k = (ev.era, ev.ticker, ev.base_id)
        if k not in seen:
            seen[k] = ev
            ev.first_of_base = True
    return evs


# ═════════════════════════════════════════════════════════════════════════════════════════════
# outcome-free per-event facts: QQQ state at D, identity breaks, fetch-log coverage
# ═════════════════════════════════════════════════════════════════════════════════════════════
def qqq_state_at(closes: np.ndarray, i: int) -> str:
    """QQQ at the close of bar i (= D, the last close known when the entry is made on E): "up" when the close is above BOTH its 10- and
    20-day simple averages (the registration's "uptrend"), "down" when below both, "mixed" otherwise; "" with fewer than 20 closes."""
    if i < 19:
        return ""
    c = float(closes[i])
    s10, s20 = float(closes[i - 9:i + 1].mean()), float(closes[i - 19:i + 1].mean())
    if c > s10 and c > s20:
        return "up"
    if c < s10 and c < s20:
        return "down"
    return "mixed"


def break_in(breaks: "np.ndarray | None", lo_ord: int, hi_ord: int) -> bool:
    """An identity break b with lo < b <= hi (`runner.break_mask`'s rule: a break dated on the window's first bar is outside it)."""
    if breaks is None or not len(breaks):
        return False
    return bool(np.searchsorted(breaks, hi_ord, side="right") - np.searchsorted(breaks, lo_ord, side="right") > 0)


def window_ords(cal: list, e_ci: int, pre: int, post: int) -> tuple:
    """(ordinal of the session `pre` before E, of E, of the session `post` after E, clipped to the calendar)."""
    lo = cal[max(0, e_ci - pre)].toordinal()
    return lo, cal[e_ci].toordinal(), cal[min(len(cal) - 1, e_ci + post)].toordinal()


# ═════════════════════════════════════════════════════════════════════════════════════════════
# THE WALK (real run only): the runner's / module's functions, unchanged
# ═════════════════════════════════════════════════════════════════════════════════════════════
def cut_at_break(fwd, e_date: date, breaks: "np.ndarray | None") -> tuple:
    """(fwd, break date iso or ""): the forward window cut at the FIRST listed identity break dated after E, as `cb.forward_window` cuts
    at a hole — only the forward bars dated strictly BEFORE the break are kept (a break dated on bar X is the move INTO X: `break_in`'s
    rule), so the session before the break is the last one the walk reads. A break dated after the window's last bar cuts nothing. A
    walk that exited before the break is unchanged (and stays mature); one still open there ends `degraded` (an unsettled mark: booked
    in the account at its last close, in no per-trade number)."""
    if breaks is None or not len(breaks) or not len(fwd):
        return fwd, ""
    j = int(np.searchsorted(breaks, e_date.toordinal(), side="right"))
    if j >= len(breaks):
        return fwd, ""
    b = int(breaks[j])
    k = int(np.searchsorted(np.array([d.toordinal() for d in fwd.dates], dtype=np.int64), b, side="left"))
    if k >= len(fwd):
        return fwd, ""
    return fwd.slice(0, k), date.fromordinal(b).isoformat()


def walk_event(ev: Event, bars, cidx, e: int, mb, breaks: "np.ndarray | None" = None) -> dict:
    """{variant: {"entry": the module's entry dict, "arms": {arm: raw walk result with events}}} for ONE event, wired exactly as
    `runner.evaluate_candidate` wires it (E alignment, the 130-session contiguity, closes_before through E, `forward_window`). ORH5 walks
    the 8 S-grid arms (`cb.walk_arms`, which `runner.walk_arms` wraps) and `pp` (`runner.exitpb_walk_arms`); ORH1 / ORH60 the primary arm.
    `breaks` = the ticker's identity-break ordinals: the forward window is cut at the first one after E (`cut_at_break`), never excluded."""
    adr20 = ev.adr20
    assert bars.dates[e].isoformat() == ev.E, (ev.ticker, e, ev.E)
    assert e >= cb.MIN_HISTORY and int(cidx[e]) - int(cidx[e - cb.MIN_HISTORY]) == cb.MIN_HISTORY, (ev.ticker, ev.E)
    ent = cb.entry_variants(mb, pivot=ev.pivot, adr20=adr20, day_high=float(bars.h[e]), day_low=float(bars.l[e]))
    closes_before = bars.c[:e + 1]
    assert float(closes_before[-1]) == float(bars.c[e])
    fwd, cut = cb.forward_window(bars, cidx, e, HORIZON)
    fwd, brk = cut_at_break(fwd, bars.dates[e], breaks)
    out = {"n_fwd": len(fwd), "hole": bool(cut), "break_cut": brk}
    for v in (ENTRY,) + BESIDE_ENTRIES:
        en = ent[v]
        res = {"entry": en, "arms": {}}
        if en["status"] == "filled":
            arms = {a: cb.ARMS[a] for a in (GRID_ARMS if v == ENTRY else (PRIMARY_ARM,))}
            res["arms"].update(cb.walk_arms(en, closes_before=closes_before, fwd=fwd, adr20=adr20, horizon=HORIZON, arms=arms))
            if v == ENTRY:
                res["arms"].update(R.exitpb_walk_arms(en, closes_before=closes_before, fwd=fwd, adr20=adr20, minutes=mb,
                                                      horizon=HORIZON, arms={PP_ARM: R.EXITPB_ARMS[PP_ARM]}))
        out[v] = res
    return out


def legs_of(events: list, bars, cidx, e: int) -> list:
    """The SELL legs of one walk, dated: [(calendar index, order inside the day, fraction of the ORIGINAL position, price, kind, session)].
    Session s of a walk is bar e + s (`fwd` is cut before the first missing session, so the offsets hold); a trail event already carries
    the session of its next-open fill. Order inside a day: 0 at the open (a trail fill; a stop / +R partial printed AT the open), 2
    intraday (a stop or +R target touched inside the bar; every day-0 exit, which follows the fill), 3 at the close (a session partial,
    the stall cut, a mark). Entries are order 1."""
    out = []
    for s, kind, px, frac in events:
        if kind not in SELL_KINDS or not frac > 0:
            continue
        s = int(s)
        bi = e + s
        ci = int(cidx[bi])
        if s == 0:
            order = ORDER_CLOSE if kind == "mark" else ORDER_INTRADAY
        elif kind == "trail":
            order = ORDER_OPEN
        elif kind in ("partial", "cut", "mark"):
            order = ORDER_CLOSE
        elif float(px) == float(bars.o[bi]):
            order = ORDER_OPEN
        else:
            order = ORDER_INTRADAY
        out.append((ci, order, float(frac), float(px), kind, s))
    return out


def r_with_slip(legs: list, fill: float, stop: float, slip: float) -> float:
    """Realised R with `slip` paid on every exit leg: sum frac x (px x (1 - slip) - fill) / (fill - stop). At slip 0 it equals the walk's
    own `realized_r` (asserted on every trade)."""
    risk = fill - stop
    return sum(f * (px * (1.0 - slip) - fill) for _ci, _o, f, px, _k, _s in legs) / risk


@dataclass
class Trade:
    """One filled walk under one (variant, arm), ready for the tables and the account simulation."""
    key: tuple                           # (era, ticker, E)
    ticker: str
    era: str
    e_ci: int
    fill_minute: int
    fill: float
    stop: float
    width: float
    status: str
    mature: bool
    realized_r: float
    r_slip: tuple
    sessions_held: int
    legs: list
    path_c: np.ndarray                   # closes of sessions 0..last leg (consecutive calendar sessions from e_ci)
    retrigger: int = 0
    year: int = 0
    month: str = ""


def make_trade(ev: Event, en: dict, raw: dict, bars, cidx, e: int, n_fwd: int) -> Trade:
    legs = legs_of(raw["events"], bars, cidx, e)
    fill, stop = float(en["fill"]), float(en["stop"])
    rs = tuple(r_with_slip(legs, fill, stop, s) for s in EXIT_SLIPS) if legs else (0.0,) * len(EXIT_SLIPS)
    if legs:
        assert abs(rs[0] - float(raw["realized_r"])) < 1e-9, (ev.ticker, ev.E, rs[0], raw["realized_r"])
        assert abs(sum(lg[2] for lg in legs) - 1.0) < 1e-9, (ev.ticker, ev.E, legs)
    last = max((lg[0] for lg in legs), default=int(cidx[e])) - int(cidx[e])
    return Trade(key=(ev.era, ev.ticker, ev.E), ticker=ev.ticker, era=ev.era, e_ci=int(cidx[e]), fill_minute=int(en["fill_minute"]),
                 fill=fill, stop=stop, width=(fill - stop) / fill, status=raw["status"],
                 mature=bool(cb.is_mature(raw["status"], n_fwd, HORIZON)), realized_r=float(raw["realized_r"]), r_slip=rs,
                 sessions_held=int(raw["sessions_held"]), legs=legs, path_c=np.asarray(bars.c[e:e + last + 1], dtype=float),
                 retrigger=ev.retrigger, year=ev.year, month=ev.month)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# measures
# ═════════════════════════════════════════════════════════════════════════════════════════════
def tail_stats(r, n_events: "int | None" = None) -> dict:
    """Per-trade R statistics, tail first. Rates are per 100 TRADES; `n_events` (filled + not filled) gives the per-100-events beside."""
    r = np.asarray(r, dtype=float)
    n = len(r)
    out = {"n": n}
    if n == 0:
        return out
    for t in TAILS:
        out[f"ge{int(t)}"] = PER * float((r >= t).mean())
        if n_events:
            out[f"ge{int(t)}_ev"] = PER * float((r >= t).sum()) / n_events
    out.update(max=float(r.max()), worst=float(r.min()), win=float((r > 0).mean()), mean=float(r.mean()), median=float(np.median(r)),
               sum=float(r.sum()), p5=float(np.percentile(r, 5)))
    if n_events:
        out["mean_ev"] = float(r.sum()) / n_events
    return out


def paired_block_diff(a_val, a_month, a_strat, b_val, b_month, b_strat, weights: dict, *, a_date=None, b_date=None,
                      draws: int = BOOT_DRAWS, seed: int = SEED, key: str = "", alpha: float = 0.05) -> dict:
    """The his-calls (a) minus control (b) difference of a MEAN, with a month-block bootstrap whose ONE draw of calendar months per
    resample is applied to BOTH arms (the months are the union of both arms'; a month carries whole dates), every difference computed
    inside each resample from the SAME draw.
      matched (DECIDING; needs `a_date` / `b_date`): DATE-MATCHED. A cell is (date, stratum); each control trade is weighted by his trades
        / the control's trades in its own cell, so matched = sum over cells of n_a,c x (mean_a,c - mean_b,c) / sum of n_a,c — his trades'
        own dates and strata, the control read on exactly those. A cell holding his trades but no control trade is DROPPED and counted
        (cells, his trades). The cell weights are his trade COUNTS from the full sample; a month drawn k times enters k times (its cells'
        means do not change), so nothing is re-estimated inside a resample. A resample whose drawn months hold no covered cell is
        dropped and counted.
      weighted (beside, stratum-only): `weights` {stratum: w} FIXED (his full-sample shares): sum_s w_s (mean_a,s - mean_b,s), the
        control reweighted to his first-break / retrigger mix but pooled across dates. A resample with a weighted stratum empty in either
        arm is dropped and counted.
      raw (beside, pooled): mean_a - mean_b.
    Generator: default_rng([seed, crc32(key)]) (the runner's convention)."""
    a_val, b_val = np.asarray(a_val, dtype=float), np.asarray(b_val, dtype=float)
    months = np.unique(np.concatenate([np.asarray(a_month, dtype=str), np.asarray(b_month, dtype=str)]))
    strata = sorted(weights)
    M, S = len(months), len(strata)
    nan = float("nan")
    if M == 0:                           # both arms empty: nothing to compare
        out = {"weighted": nan, "w_lo": nan, "w_hi": nan, "raw": nan, "r_lo": nan, "r_hi": nan, "dropped_w": 0, "dropped_r": 0,
               "months": 0, "draws": draws}
        if a_date is not None:
            out.update(matched=nan, m_lo=nan, m_hi=nan, dropped_m=0, cells_his=0, cells_uncovered=0, his_uncovered=0, his_matched=0)
        return out
    sidx = {s: j for j, s in enumerate(strata)}

    def cells(val, mon, st):
        mi = np.searchsorted(months, np.asarray(mon, dtype=str))
        sj = np.array([sidx[s] for s in st], dtype=np.int64) if len(val) else np.zeros(0, dtype=np.int64)
        sums, cnts = np.zeros((M, S)), np.zeros((M, S))
        np.add.at(sums, (mi, sj), val)
        np.add.at(cnts, (mi, sj), 1.0)
        return sums, cnts
    sa, ca = cells(a_val, a_month, a_strat)
    sb, cb_ = cells(b_val, b_month, b_strat)
    w = np.array([weights[s] for s in strata], dtype=float)

    def stats(sa_, ca_, sb_, cb2):
        with np.errstate(invalid="ignore", divide="ignore"):
            ma, mb = sa_ / ca_, sb_ / cb2
            pos = w > 0                  # a zero-weight stratum (his arm holds none of it) carries no information
            weighted = (w[pos] * (ma - mb)[..., pos]).sum(axis=-1)
            raw = sa_.sum(axis=-1) / ca_.sum(axis=-1) - sb_.sum(axis=-1) / cb2.sum(axis=-1)
        return weighted, raw
    pw, pr = stats(sa.sum(0), ca.sum(0), sb.sum(0), cb_.sum(0))
    rng = np.random.default_rng([seed, zlib.crc32(key.encode())])
    idx = rng.integers(0, M, size=(draws, M))
    dw, dr = stats(sa[idx].sum(1), ca[idx].sum(1), sb[idx].sum(1), cb_[idx].sum(1))
    ok_w, ok_r = np.isfinite(dw), np.isfinite(dr)
    q = (100.0 * alpha / 2, 100.0 * (1 - alpha / 2))
    lo_w, hi_w = (np.percentile(dw[ok_w], q) if ok_w.any() else (float("nan"), float("nan")))
    lo_r, hi_r = (np.percentile(dr[ok_r], q) if ok_r.any() else (float("nan"), float("nan")))
    out = {"weighted": float(pw), "w_lo": float(lo_w), "w_hi": float(hi_w), "raw": float(pr), "r_lo": float(lo_r), "r_hi": float(hi_r),
           "dropped_w": int((~ok_w).sum()), "dropped_r": int((~ok_r).sum()), "months": M, "draws": draws}
    if a_date is None:
        return out
    # ---- the DATE-MATCHED difference (deciding): cells (date, stratum), aggregated to the month blocks of the same draw `idx`
    a_date, b_date = np.asarray(a_date, dtype=str), np.asarray(b_date, dtype=str)
    assert len(a_date) == len(a_val) and len(b_date) == len(b_val)
    assert all(d[:7] == m for d, m in zip(a_date, np.asarray(a_month, dtype=str))), "a date outside its month block (his arm)"
    assert all(d[:7] == m for d, m in zip(b_date, np.asarray(b_month, dtype=str))), "a date outside its month block (control)"
    ka = [f"{d}|{s}" for d, s in zip(a_date, a_strat)]
    kb = [f"{d}|{s}" for d, s in zip(b_date, b_strat)]
    ckeys = np.unique(np.array(ka + kb, dtype=str))
    C = len(ckeys)
    ia = np.searchsorted(ckeys, np.array(ka, dtype=str)).astype(np.int64) if ka else np.zeros(0, dtype=np.int64)
    ib = np.searchsorted(ckeys, np.array(kb, dtype=str)).astype(np.int64) if kb else np.zeros(0, dtype=np.int64)
    na, sa_c = np.bincount(ia, minlength=C).astype(float), np.bincount(ia, weights=a_val, minlength=C)
    nb, sb_c = np.bincount(ib, minlength=C).astype(float), np.bincount(ib, weights=b_val, minlength=C)
    his_cell = na > 0
    cov = his_cell & (nb > 0)
    unc = his_cell & ~cov
    d_c = np.zeros(C)
    d_c[cov] = sa_c[cov] - na[cov] * (sb_c[cov] / nb[cov])          # n_a,c x (mean_a,c - mean_b,c)
    n_c = np.where(cov, na, 0.0)
    cm = np.searchsorted(months, np.array([c[:7] for c in ckeys], dtype=str)) if C else np.zeros(0, dtype=np.int64)
    Dm, Nm = np.bincount(cm, weights=d_c, minlength=M), np.bincount(cm, weights=n_c, minlength=M)
    pm = float(Dm.sum() / Nm.sum()) if Nm.sum() > 0 else nan
    with np.errstate(invalid="ignore", divide="ignore"):
        dm = Dm[idx].sum(1) / Nm[idx].sum(1)
    ok_m = np.isfinite(dm)
    lo_m, hi_m = (np.percentile(dm[ok_m], q) if ok_m.any() else (nan, nan))
    out.update(matched=pm, m_lo=float(lo_m), m_hi=float(hi_m), dropped_m=int((~ok_m).sum()), cells_his=int(his_cell.sum()),
               cells_uncovered=int(unc.sum()), his_uncovered=int(na[unc].sum()), his_matched=int(na[cov].sum()))
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the account simulation
# ═════════════════════════════════════════════════════════════════════════════════════════════
def simulate(trades: list, cfg: Config, cal: list, start_ci: int) -> dict:
    """A chronological account over `trades` (Trade objects; each a filled walk with dated sell legs). Start equity 1.0 at the close
    before `start_ci`. Per calendar session, in order: (0) exits AT THE OPEN; (1) entries in (fill minute, ticker) order — sized on the
    equity at the PREVIOUS close (cash + every open position at that close): position value = equity x min(risk / width, cap), width =
    (fill - stop) / fill; HIS per-stock limit (`stock_limit`, 30% primary): the COST still held in that ticker (shares not yet sold x
    their fill) may not exceed stock_limit x that same equity — a position that would cross it takes only the room left (counted
    `stock_limit_trimmed`), and with no room left it is SKIPPED (counted `skipped_stock_limit`); no margin: a position larger than the
    free cash is SKIPPED (`room = "skip"`, primary) or cut to the free cash (`room = "trim"`, beside); a second position in a ticker
    already held is opened inside the stock limit (`same_ticker = "allow"`, primary) or skipped; (2) intraday exits (stops / targets
    touched, every day-0 exit); (3) exits at the close (session partials, the stall cut, marks). A sell leg sells its fraction of the
    ORIGINAL shares at its price less `exit_slip`, and takes those shares' COST off the ticker's held cost (zeroed when its last position
    closes). Equity is marked at every close; drawdown is read on that daily curve. Returns the daily curve, year-end equity, yearly
    return, max drawdown and the counts."""
    acts = []
    for k, t in enumerate(trades):
        acts.append((t.e_ci, ORDER_BUY, t.fill_minute, t.ticker, 0, k))
        for li, lg in enumerate(t.legs):
            acts.append((lg[0], lg[1], 0, "", li + 1, k))
    acts.sort()
    end_ci = max([a[0] for a in acts], default=start_ci)
    cash = 1.0
    shares0 = {}                                   # k -> shares bought
    rem = {}                                       # k -> shares still held (open positions only)
    held = Counter()                               # ticker -> open positions
    cost_held = defaultdict(float)                 # ticker -> cost of the shares still held (the per-stock limit is at cost)
    counts = Counter()
    entered_by_year, skipped_by_year = Counter(), Counter()
    eq_prev = 1.0
    curve_ci, curve_eq = [], []
    max_open, max_gross = 0, 0.0
    p = 0
    n_act = len(acts)
    for ci in range(start_ci, end_ci + 1):
        while p < n_act and acts[p][0] == ci:
            _ci, order, _fm, _tk, seq, k = acts[p]
            t = trades[k]
            if order == ORDER_BUY:
                y = cal[ci].year
                if cfg.same_ticker == "skip" and held[t.ticker] > 0:
                    counts["skipped_same_ticker"] += 1
                    skipped_by_year[y] += 1
                else:
                    value = eq_prev * min(cfg.risk / t.width, cfg.cap)
                    stock_trim = False
                    if cfg.stock_limit is not None:
                        room_stock = cfg.stock_limit * eq_prev - cost_held[t.ticker]
                        if room_stock <= 1e-12:
                            counts["skipped_stock_limit"] += 1
                            skipped_by_year[y] += 1
                            value = 0.0
                        elif value > room_stock + 1e-12:
                            value = room_stock
                            stock_trim = True
                    if value > 0 and value > cash + 1e-12:
                        if cfg.room == "trim" and cash > 1e-12:
                            value = cash
                            counts["trimmed"] += 1
                        else:
                            counts["skipped_no_room"] += 1
                            skipped_by_year[y] += 1
                            value = 0.0
                    if value > 0:
                        if held[t.ticker] > 0:
                            counts["same_ticker_concurrent"] += 1
                        if min(cfg.risk / t.width, cfg.cap) == cfg.cap:
                            counts["cap_bound"] += 1
                        if stock_trim:
                            counts["stock_limit_trimmed"] += 1
                        sh = value / t.fill
                        shares0[k] = sh
                        rem[k] = sh
                        held[t.ticker] += 1
                        cost_held[t.ticker] += value
                        cash -= value
                        counts["entered"] += 1
                        entered_by_year[y] += 1
                        max_open = max(max_open, len(rem))
            elif k in rem:
                _lci, _o, frac, px, _kind, _s = t.legs[seq - 1]
                sh = shares0[k] * frac
                cash += sh * px * (1.0 - cfg.exit_slip)
                rem[k] -= sh
                cost_held[t.ticker] -= sh * t.fill
                if rem[k] <= shares0[k] * 1e-9:
                    del rem[k]
                    held[t.ticker] -= 1
                    if held[t.ticker] == 0:
                        cost_held[t.ticker] = 0.0
            p += 1
        pos_val = 0.0
        for k, sh in rem.items():
            t = trades[k]
            pos_val += sh * float(t.path_c[ci - t.e_ci])
        eq = cash + pos_val
        if eq > 0:
            max_gross = max(max_gross, pos_val / eq)
        curve_ci.append(ci)
        curve_eq.append(eq)
        eq_prev = eq
    assert not rem, f"{len(rem)} positions still open after the last leg"
    eqa = np.asarray(curve_eq, dtype=float)
    peak = np.maximum.accumulate(np.concatenate(([1.0], eqa)))[1:] if len(eqa) else eqa
    dd = float((1.0 - eqa / peak).max()) if len(eqa) else 0.0
    year_end, prev, yearly = {}, 1.0, {}
    for ci, eq in zip(curve_ci, curve_eq):
        year_end[cal[ci].year] = eq
    for y in sorted(year_end):
        yearly[y] = year_end[y] / prev - 1.0
        prev = year_end[y]
    return {"final": float(eqa[-1]) if len(eqa) else 1.0, "year_end": year_end, "yearly": yearly, "max_dd": dd, "counts": counts,
            "entered_by_year": entered_by_year, "skipped_by_year": skipped_by_year, "max_open": max_open, "max_gross": max_gross,
            "curve": (curve_ci, curve_eq)}


def sample_control(his_by_date: dict, ctl_by_date: dict, rng, mix: "dict | None" = None) -> tuple:
    """One control draw: on every date with k HIS events, k control events of THAT date drawn without replacement (all of them when the
    date holds fewer, counted). `mix` {date: (k_first, k_retrigger)} + control events tagged by stratum = the mix-matched draw (beside):
    per date k_first first breaks and k_retrigger retriggers, a stratum short of events topped up from the other (counted).
    Dates in sorted order, so the draw depends only on the seed. -> (list of control event ids, Counter)."""
    out, c = [], Counter()
    for d in sorted(his_by_date):
        k = his_by_date[d]
        pool = ctl_by_date.get(d, [])
        if mix is None:
            if len(pool) <= k:
                c["dates_short"] += int(len(pool) < k)
                out.extend(pool)
                continue
            pick = rng.choice(len(pool), size=k, replace=False)
            out.extend(pool[j] for j in sorted(pick.tolist()))
            continue
        kf, kr = mix[d]
        firsts = [x for x, s in pool if s == 0]
        rets = [x for x, s in pool if s == 1]
        take_f, take_r = min(kf, len(firsts)), min(kr, len(rets))
        short = (kf - take_f) + (kr - take_r)
        if short:
            c["mix_topped_up"] += short
            extra_f = min(len(firsts) - take_f, kr - take_r)
            extra_r = min(len(rets) - take_r, kf - take_f)
            take_f += max(0, extra_f)
            take_r += max(0, extra_r)
        for grp, n in ((firsts, take_f), (rets, take_r)):
            if n >= len(grp):
                out.extend(grp)
            elif n > 0:
                pick = rng.choice(len(grp), size=n, replace=False)
                out.extend(grp[j] for j in sorted(pick.tolist()))
    return out, c


def band_summary(values: list) -> dict:
    v = np.asarray([x for x in values if x is not None and math.isfinite(x)], dtype=float)
    if not len(v):
        return {}
    return {q: float(np.percentile(v, q)) for q in (5, 25, 50, 75, 95)}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the fork (written in the registration before any outcome)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def fork_verdict(yearly: dict, diff_lo: float, band_share_ge: float) -> tuple:
    """The registered fork (era A, ORH5 + p33_s3_t10, the primary account config).
      curve strong = the his-calls curve returns >= +50% in at least 2 of the 2017-21 years;
      curve arm    = curve strong AND at most 5% of the registered same-day band's draws end at or above his final equity;
      interval arm = the DATE-MATCHED his-calls minus control mean-R interval (per filled mature trade) has its LOWER end above zero.
    curve arm OR interval arm -> SELECTION; else curve strong (the band at or above his curve) -> DATES / market (the days carry it, not
    the picks); else -> EXECUTION / data. A band share that is not a number is a refusal (raises), never a silent arm.
    -> (verdict, strong_years, curve_strong, curve_arm, interval_arm)."""
    if band_share_ge is None or not math.isfinite(band_share_ge):
        raise ValueError(f"the control band's share at or above his final equity is not a number ({band_share_ge}): the fork is unreadable")
    strong_years = [y for y in FORK_YEARS if y in yearly and yearly[y] >= STRONG_YEAR_RET]
    curve_strong = len(strong_years) >= STRONG_YEARS_MIN
    curve_arm = curve_strong and band_share_ge <= BAND_SHARE_MAX
    interval_arm = diff_lo is not None and math.isfinite(diff_lo) and diff_lo > 0
    verdict = "SELECTION" if (curve_arm or interval_arm) else ("DATES / market" if curve_strong else "EXECUTION / data")
    return verdict, strong_years, curve_strong, curve_arm, interval_arm


# ═════════════════════════════════════════════════════════════════════════════════════════════
# G8 — trade_impact.py on this read's own trade list
# ═════════════════════════════════════════════════════════════════════════════════════════════
G8_AFTER = re.compile(r"trades entered after the cutoff \S+ \(their bars are sealed\): (\d+)")
G8_PAST = re.compile(r"trades whose hold runs past the last bar kept \(truncated or no bars\): (\d+)")


def parse_g8(text: str) -> tuple:
    a, b = G8_AFTER.search(text), G8_PAST.search(text)
    if a is None or b is None:
        raise ValueError("trade_impact.py output carries no G8 lines (an unreadable line is a refusal, never a PASS)")
    return int(a.group(1)), int(b.group(1))


def write_g8_file(path: str, rows: list) -> None:
    """The `--kind r1` shape trade_impact.py reads: cell (= the arm), attempt (0: no re-entry is walked), ticker, entry_date (= E),
    exit_j (= sessions held), realized_r."""
    with open(path, "w") as fh:
        fh.write("cell\tattempt\tticker\tentry_date\texit_j\trealized_r\n")
        for arm, tk, E, held, r in rows:
            fh.write(f"{arm}\t0\t{tk}\t{E}\t{held}\t{r:.10f}\n")


def run_g8(era: str, trades_path: str, out_txt: str) -> tuple:
    export = FILES[f"export_{era}"]
    flags = FILES[f"flags_{era}"]
    cmd = [sys.executable, TRADE_IMPACT, "--flags", flags, "--export", export, "--trades", trades_path, "--label", era, "--kind", "r1",
           "--cell", PRIMARY_ARM, "--cutoff", CUT_B]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    text = res.stdout + ("\n[stderr]\n" + res.stderr if res.stderr.strip() else "")
    with open(out_txt, "w") as fh:
        fh.write(" ".join(cmd) + "\n\n" + text)
    if res.returncode != 0:
        raise RuntimeError(f"trade_impact.py exited {res.returncode} for era {era}")
    return parse_g8(text)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_all(say, dry: bool) -> dict:
    """Labels -> the frozen classes -> events; the daily exports (era B cut at read); the fetch logs; the outcome-free per-event facts."""
    ls = label_sets_from_files()
    candA, dA = read_tsv(FILES["cand_A"], CAND_COLS, keep=cand_keep_A)
    candB, dB = read_tsv(FILES["cand_B"], CAND_COLS, keep=FIT.era_b_cand_keep)
    assert candB["E"].max() <= CUT_B and candB["D"].max() <= CUT_B
    eras = {"A": era_stream("A", candA, ls), "B": era_stream("B", candB, ls)}
    got = population_counts(eras)
    got["cand_B_not_discovery"], got["cand_B_after_cut"] = dB["not_discovery"], dB["dated_after_cut"]
    evs = build_events(eras)
    need = {e: {ev.ticker for ev in evs if ev.era == e} | {"QQQ"} for e in ("A", "B")}
    t0 = time.time()
    DA, infoA = load_daily_subset(FILES["export_A"], keep=need["A"])
    DB, infoB = load_daily_subset(FILES["export_B"], keep=need["B"], cut=CUT_B)
    got["cal_A"], got["cal_B"] = len(DA.cal), len(DB.cal)
    say(f"- daily exports loaded in {time.time() - t0:.0f}s: era A {infoA['rows_kept']:,} of {infoA['rows_read']:,} rows kept ({len(DA.tickers):,} "
        f"tickers, calendar {DA.cal[0]}..{DA.cal[-1]}); era B {infoB['rows_kept']:,} of {infoB['rows_read']:,} rows kept ({len(DB.tickers):,} "
        f"tickers, calendar {DB.cal[0]}..{DB.cal[-1]}), rows dated after {CUT_B} DROPPED AT READ {infoB['dated_after_cut']:,} (asserted: "
        f"max date kept {DB.cal[-1]} <= {CUT_B})")
    assert DB.cal[-1].isoformat() <= CUT_B
    with open(FILES["sessions_A"]) as fh:
        sess_A = [ln.strip() for ln in fh if ln.strip()]
    assert sess_A == [d.isoformat() for d in DA.cal], "era A export calendar != cb702_pre_v2/sessions.txt"
    doneA, _ = load_done(FILES["done_A"])
    doneB, doneB_dropped = load_done(FILES["done_B"], cut=CUT_B)
    guards = {"A": R.load_breaks(FILES["guard_A"]), "B": R.load_breaks(FILES["guard_B"])}
    gA_audit = R.load_breaks(FILES["guard_A_audit"])
    guard_A_equal = set(guards["A"]) == set(gA_audit) and all(np.array_equal(guards["A"][s], gA_audit[s]) for s in guards["A"])
    Ds = {"A": DA, "B": DB}
    qqq = {}
    for e, D in Ds.items():
        qb, qc = R.bars_for(D, D.tid["QQQ"])
        qqq[e] = (qb, qc)
    files = {e: R.minute_date_files(MINUTES[e]) for e in ("A", "B")}
    for ev in evs:
        D = Ds[ev.era]
        e_ci = bisect.bisect_left(D.cal, date.fromisoformat(ev.E))
        assert D.cal[e_ci].isoformat() == ev.E
        qb, qc = qqq[ev.era]
        d_ci = e_ci - 1
        p = int(np.searchsorted(qc, d_ci))
        ev.qqq = qqq_state_at(qb.c, p) if (p < len(qc) and int(qc[p]) == d_ci) else ""
        lo, eo, _hi = window_ords(D.cal, e_ci, BREAK_PRE, BREAK_POST)
        ev.break_pre = break_in(guards[ev.era].get(ev.ticker), lo, eo)
        st = (doneA if ev.era == "A" else doneB).get((ev.E, ev.ticker))
        ev.minutes_state = "ok" if (st == "ok" and ev.E in files[ev.era]) else ("empty" if st == "empty" else "missing")
        ev.keep = ev.minutes_state != "missing" and not ev.break_pre
    return dict(ls=ls, eras=eras, got=got, evs=evs, Ds=Ds, guards=guards, guard_A_equal=guard_A_equal, doneB_dropped=doneB_dropped,
                dA=dA, dB=dB, qqq=qqq, files=files)


def describe_population(say, S: dict) -> None:
    evs = S["evs"]
    say("\n## Populations (asserted against the Track A registration)")
    bad = check_expect(S["got"], EXPECT)
    for k in sorted(EXPECT):
        say(f"- {k}: {S['got'].get(k)}" + ("" if S["got"].get(k) == EXPECT[k] else f"  <-- registered {EXPECT[k]}"))
    if bad:
        raise AssertionError("POPULATION ASSERT FAILED: " + "; ".join(bad))
    say("- every population equals the registration")
    for e in ("A", "B"):
        his = [x for x in evs if x.era == e and x.his]
        ctl = [x for x in evs if x.era == e and x.ctl]
        post = [x for x in evs if x.era == e and x.post]
        say(f"\n### era {e}")
        yrs = sorted({x.year for x in his + ctl})
        rows = [[y, sum(1 for x in his if x.year == y), sum(1 for x in his if x.year == y and x.retrigger == 0),
                 sum(1 for x in his if x.year == y and x.retrigger == 1), sum(1 for x in ctl if x.year == y),
                 sum(1 for x in ctl if x.year == y and x.retrigger == 0), sum(1 for x in post if x.year == y)] for y in yrs]
        rows.append(["all", len(his), sum(1 for x in his if x.retrigger == 0), sum(1 for x in his if x.retrigger == 1), len(ctl),
                     sum(1 for x in ctl if x.retrigger == 0), len(post)])
        for ln in table(["year of E", "his calls n", "first breaks", "retriggers", "control n", "control first breaks", "post-E-only n (beside)"], rows):
            say(ln)
        per_date = Counter(x.E for x in his)
        say(f"- his calls on {len(per_date)} dates; per date: " + ", ".join(f"{k} call(s) on {v} dates" for k, v in sorted(Counter(per_date.values()).items())))
        bases = {(x.ticker, x.base_id) for x in his}
        say(f"- his calls sit on {len(bases)} bases ({sum(1 for x in his if x.first_of_base)} first-of-base events, the one-event-per-base "
            f"reading); strictly-before subset {sum(1 for x in his if x.strict)}; post-E-only events also in the control "
            f"{sum(1 for x in post if x.ctl)}")
        short = [d for d, k in per_date.items() if sum(1 for x in ctl if x.E == d) < k]
        say(f"- dates whose control holds fewer events than his calls that day: {len(short)}")
        say("- QQQ at D (close vs its 10- and 20-day averages; outcome-free): "
            + "; ".join(f"{nm} " + ", ".join(f"{s or 'unknown'} {sum(1 for x in grp if x.qqq == s)}" for s in ("up", "mixed", "down", ""))
                        for nm, grp in (("his", his), ("control", ctl))))
        mst = {nm: Counter(x.minutes_state for x in grp) for nm, grp in (("his", his), ("control", ctl), ("post", post))}
        say("- minute coverage from the fetch log (`_done.psv` status; no minute file opened): "
            + "; ".join(f"{nm} ok {c['ok']} / empty {c['empty']} (abstains `no_minutes`) / MISSING {c['missing']}" for nm, c in mst.items()))
        say("- identity break inside (E - 130, E] (excluded, counted): "
            + ", ".join(f"{nm} {sum(1 for x in grp if x.break_pre)}" for nm, grp in (("his", his), ("control", ctl), ("post", post)))
            + "; a break AFTER E is forward information, read in the real run only, where it CUTS the walk's forward window at the "
              "session before it (never an exclusion)")
        if e == "A":
            say(f"- his calls by timing: strictly before E {S['got'].get('strict_A')}, resting ONLY on a label said on E "
                f"{S['got'].get('on_E_only_A')} (= {len(his)} - {S['got'].get('strict_A')}); carrying an on-E label {S['got'].get('at0_A')}, "
                f"of which {S['got'].get('at0_and_strict_A')} also carry one strictly before")
        say("- events on a 13:00-close day (ORH fills there read the minutes as stored; fills after 13:00 counted in the real run): "
            + ", ".join(f"{nm} {sum(1 for x in grp if x.early_close)}" for nm, grp in (("his", his), ("control", ctl))))
        kept = {nm: sum(1 for x in grp if x.keep) for nm, grp in (("his", his), ("control", ctl), ("post", post))}
        say(f"- the walk set after the two data exclusions: his {kept['his']} of {len(his)}, control {kept['control']} of {len(ctl)}, "
            f"post-E-only {kept['post']} of {len(post)}")
        D = S["Ds"][e]
        last = D.cal[-1]
        late = [x for x in his + ctl if bisect.bisect_left(D.cal, date.fromisoformat(x.E)) + HORIZON + 1 > len(D.cal) - 1]
        say(f"- events whose E + {HORIZON + 1} sessions run past the era's last session {last} (calendar only): {len(late)}")


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.add_argument("--dry-run", action="store_true", help="load + populations + coverage + pins; no minute file, no entry, no exit, no outcome")
    args = ap_.parse_args(argv)
    dry = args.dry_run
    say = Say()
    if not dry:
        ex = existing_outputs()
        if ex:
            print(f"REFUSED: output(s) already on disk: {ex} (the replay runs once; after a STOPPED run, recovery = the fix, then delete the "
                  f"STOPPED file AND every file under {OUT_DIR} by hand, re-freeze if the module changed)", file=sys.stderr)
            return 2
    t0 = time.time()
    say(f"# #705 QM replay — 01_replay ({'DRY RUN: no minute file opened, no entry / exit function called, no outcome computed' if dry else 'THE REGISTERED REPLAY'})")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    p0 = {k: sha(v) for k, v in {**FILES, **CODE}.items() if k in PINNED}
    drift = [f"{k}: {p0[k]} (pinned {v})" for k, v in PINNED.items() if p0.get(k) != v]
    if drift:
        say("REFUSED: a pinned input changed: " + "; ".join(drift))
        say.write(DRY_PRINTOUT if dry else STOPPED)
        return 2
    say("- Track A pins re-checked (labels, events, candidates, exports, calendar, flags, the frozen fit module, the join script, "
        "aplus_read, registered_read, the cb module = `runner.EXITPB_MODULE_SHA`): no drift")
    say("\n## Loads (era B: every row dated after 2024-12-31 dropped at read)")
    S = load_all(say, dry)
    say(f"- era B candidates: discovery split only, D and E <= {CUT_B} (dropped at read: not discovery {S['dB']['not_discovery']:,}, "
        f"dated after the cut {S['dB']['dated_after_cut']:,}); era B fetch-log rows dated after the cut dropped at read {S['doneB_dropped']:,}")
    say(f"- identity-break files: era A `cb702_pre_v2/symbol_guard.tsv` ({len(S['guards']['A'])} symbols with a break; equal to the audit's "
        f"`symbol_guard_A.tsv`: {S['guard_A_equal']}), era B `runs_2026-10-23/universe/symbol_guard_B.tsv` ({len(S['guards']['B'])} symbols)")
    with open(FILES["verdict_A"]) as fh:
        vlines = [ln.rstrip() for ln in fh if re.match(r"\s+(S0|G\d+)\s", ln)]
    say("- era A STEP 0 verdict (`cb702_pre_v2/audit_1023/verdict.txt`, pinned):")
    for ln in vlines:
        say("    " + ln.strip()[:160])
    describe_population(say, S)
    mdates = {e: sorted({x.E for x in S["evs"] if x.era == e and x.keep}) for e in ("A", "B")}
    p = pins(mdates)
    say("\n## Pins (sha256) — every value below goes under `<!-- FREEZE -->` in the doc before the real run")
    for k, v in p.items():
        say(f"- {k}: {v}  {FILES.get(k) or CODE.get(k) or ('the ' + str(len(mdates[k[8]])) + ' minute date files the walk set opens' if k.startswith('minutes_') else 'the doc text above the marker')}")
    miss = freeze_missing(DOC, p)
    say(f"- freeze record: {'every pin above is written under the FREEZE marker' if not miss else 'NOT YET under the FREEZE marker: ' + ', '.join(miss)}")
    if dry:
        say(f"\n## DRY RUN ends here: no minute file opened, no entry / exit / R / return computed. ({time.time() - t0:.0f}s)")
        say.write(DRY_PRINTOUT)
        return 0
    if miss:
        say("REFUSED: the real replay runs only after the freeze commit records every pin above under the marker.")
        print("\n".join(say.lines[-2:]), file=sys.stderr)
        return 2
    try:
        run_replay(S, say)
    except GuardStop as g:
        say(f"\nSTOPPED: {g} ({time.time() - t0:.0f}s)")
        say.write(STOPPED)
        return 3
    except Exception:                    # a crash after outcomes were opened is recorded, never silently retried
        import traceback
        say("\nCRASHED:\n" + traceback.format_exc())
        say.write(STOPPED)
        return 3
    say(f"\n({time.time() - t0:.0f}s)")
    say.write(PRINTOUT)
    return 0


class GuardStop(Exception):
    pass


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the real run (after the freeze only)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def walk_all(S: dict, say) -> tuple:
    """Walk every kept event once. -> ({(era, ticker, E): walk result}, {(era, ticker, E): minutes state}, Counter)."""
    res, tally = {}, Counter()
    for e in ("A", "B"):
        D = S["Ds"][e]
        by_date = defaultdict(list)
        for ev in S["evs"]:
            if ev.era == e and ev.keep:
                by_date[ev.E].append(ev)
        cache = {}
        for di, (d, evs) in enumerate(sorted(by_date.items())):
            path = S["files"][e].get(d)
            if path is None:             # only an `empty`-logged event can reach here (a `missing` one is excluded): its entry abstains
                blocks, info = {}, {"truncated": False}
                tally[f"{e}_minute_date_file_absent"] += 1
            else:
                blocks, info = R.read_minute_file(path, want={x.ticker for x in evs})
            tally[f"{e}_minute_truncated"] += int(info["truncated"])
            done = {(d, x.ticker): x.minutes_state for x in evs}
            for ev in evs:
                mb, state = R.minutes_for(blocks, done, d, ev.ticker)        # no block -> None -> `no_minutes`
                tally[f"{e}_minutes_{state}"] += 1
                if ev.ticker not in cache:
                    cache[ev.ticker] = R.bars_for(D, D.tid[ev.ticker])
                bars, cidx = cache[ev.ticker]
                eidx = R.locate_breakout_index(D.cal, cidx, ev.E)
                w = walk_event(ev, bars, cidx, eidx, mb, breaks=S["guards"][e].get(ev.ticker))
                if w["break_cut"]:
                    ev.break_cut = w["break_cut"]
                    tally[f"{e}_forward_window_cut_at_a_break"] += 1
                w["bars"], w["cidx"], w["e"] = bars, cidx, eidx
                res[(e, ev.ticker, ev.E)] = w
            if (di + 1) % 25 == 0:
                print(f"  era {e}: {di + 1}/{len(by_date)} dates walked", flush=True)
    return res, tally


def trades_for(S: dict, res: dict, variant: str, arm: str) -> dict:
    """{(era, ticker, E): Trade} for every FILLED walk under (variant, arm)."""
    out = {}
    evmap = {(x.era, x.ticker, x.E): x for x in S["evs"]}
    for k, w in res.items():
        v = w[variant]
        if v["entry"]["status"] != "filled" or arm not in v["arms"]:
            continue
        out[k] = make_trade(evmap[k], v["entry"], v["arms"][arm], w["bars"], w["cidx"], w["e"], w["n_fwd"])
    return out


def stat_row(name: str, evs: list, T: dict, slip_i: int = 0) -> list:
    keys = [(x.era, x.ticker, x.E) for x in evs]
    tr = [T[k] for k in keys if k in T]
    mat = [t for t in tr if t.mature]
    r = [t.r_slip[slip_i] for t in mat]
    n_ev = len(keys) - (len(tr) - len(mat))      # a filled walk that is not mature is in no number, either denominator
    st = tail_stats(r, n_events=n_ev)
    return [name, len(keys), len(tr), len(mat), fmt(st.get("ge5"), 1), fmt(st.get("ge10"), 1), fmt(st.get("ge20"), 1), fmt(st.get("max")),
            fmt(st.get("worst")), pct(st.get("win")), fmt(st.get("mean"), 3), fmt(st.get("median"), 3), fmt(st.get("ge10_ev"), 1),
            fmt(st.get("mean_ev"), 3)]


STAT_HDR = ["group", "events n", "filled n", "mature n", ">=5R /100 trades", ">=10R /100", ">=20R /100", "max R", "worst R", "win rate",
            "mean R", "median R", ">=10R /100 events", "mean R /event"]


def run_replay(S: dict, say) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    evs = [x for x in S["evs"]]
    res, tally = walk_all(S, say)
    say("\n## The walk")
    say("- " + ", ".join(f"{k} {v:,}" for k, v in sorted(tally.items())))
    cut_evs = [x for x in evs if x.break_cut and (x.era, x.ticker, x.E) in res]
    say(f"- forward windows CUT at an identity break after E (the session before the break is the last one read; no event excluded): "
        f"{len(cut_evs) or 'none'}")
    for x in cut_evs:
        en = res[(x.era, x.ticker, x.E)][ENTRY]
        raw = en["arms"].get(PRIMARY_ARM)
        st = (f"primary walk {raw['status']} ({'mature' if cb.is_mature(raw['status'], res[(x.era, x.ticker, x.E)]['n_fwd'], HORIZON) else 'NOT mature: booked in the account, in no per-trade number'})"
              if raw is not None else f"ORH5 {en['entry']['status']}")
        say(f"    {x.era} {x.ticker} E {x.E} ({'his' if x.his else 'control' if x.ctl else 'post-E-only'}"
            f"{', also post-E-only' if x.post and x.ctl else ''}): break {x.break_cut}; {st}")
    groups = {}
    for e in ("A", "B"):
        groups[e] = {"his": [x for x in evs if x.era == e and x.his and x.keep], "ctl": [x for x in evs if x.era == e and x.ctl and x.keep],
                     "post": [x for x in evs if x.era == e and x.post and x.keep]}
    # every (variant, arm) the registration names
    combos = [(ENTRY, a) for a in GRID_ARMS] + [(ENTRY, PP_ARM)] + [(v, PRIMARY_ARM) for v in BESIDE_ENTRIES]
    TT = {c: trades_for(S, res, *c) for c in combos}
    T = TT[(ENTRY, PRIMARY_ARM)]
    # ---- the trade table + G8 files
    evmap = {(x.era, x.ticker, x.E): x for x in evs}
    rows = []
    for k, w in sorted(res.items()):
        ev = evmap[k]
        for v in (ENTRY,) + BESIDE_ENTRIES:
            en = w[v]["entry"]
            base = [ev.era, ev.ticker, ev.D, ev.E, ev.base_id, ev.retrigger, ev.year, ev.qqq, int(ev.his), int(ev.ctl), int(ev.post),
                    int(ev.strict), int(ev.first_of_base), v, en["status"], en["reason"] or "", en["fill"], en["stop"], en["fill_minute"],
                    en["width_pct"], int(ev.early_close and en["status"] == "filled" and (en["fill_minute"] or 0) >= EARLY_CUT)]
            if en["status"] != "filled":
                rows.append(base + [""] * 9)
                continue
            for arm in w[v]["arms"]:
                t = TT[(v, arm)][k]
                legs = ";".join(f"{lg[5]}:{lg[4]}:{lg[2]:.6f}:{lg[3]:.6f}" for lg in t.legs)
                rows.append(base + [arm, t.status, int(t.mature), t.sessions_held, t.realized_r, t.r_slip[1], t.r_slip[2], len(t.legs), legs])
    cols = ["era", "ticker", "D", "E", "base_id", "retrigger", "year", "qqq_at_D", "is_his", "is_ctl", "is_post", "is_strict", "first_of_base",
            "variant", "entry_status", "entry_reason", "fill", "stop", "fill_minute", "width_pct", "fill_after_13_on_early_close", "arm", "status",
            "mature", "sessions_held", "realized_r", "r_exit_slip_0.1", "r_exit_slip_0.2", "n_legs", "legs"]
    with gzip.open(os.path.join(OUT_DIR, "trades.tsv.gz"), "wt") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join("" if x is None else (f"{x:.10g}" if isinstance(x, float) else str(x)) for x in r) + "\n")
    g8 = {}
    for e in ("A", "B"):
        g8rows = [(arm, k[1], k[2], TT[(ENTRY, arm)][k].sessions_held, TT[(ENTRY, arm)][k].realized_r)
                  for arm in GRID_ARMS + (PP_ARM,) for k in sorted(TT[(ENTRY, arm)]) if k[0] == e]
        path = os.path.join(OUT_DIR, f"g8_{e}.tsv")
        write_g8_file(path, g8rows)
        g8[e] = run_g8(e, path, os.path.join(OUT_DIR, f"g8_{e}_impact.txt"))
    say("\n## G8 — trade_impact.py on THIS read's trade list (ORH5, p33_s3_t10), run BEFORE any number below")
    say(f"- era A: entered after the cutoff {g8['A'][0]}, holds past the last bar kept {g8['A'][1]} (registered: both 0, asserted)")
    say(f"- era B: entered after the cutoff {g8['B'][0]}, holds past the last bar kept {g8['B'][1]} (censored: a walk not mature is in no number)")
    if g8["A"] != (0, 0):
        raise GuardStop(f"G8 era A {g8['A']} != (0, 0): the read does not quote a number")
    # ---- data facts beside every fill statistic
    say("\n## Entry facts (ORH5)")
    for e in ("A", "B"):
        for nm in ("his", "ctl", "post"):
            st = Counter(res[(x.era, x.ticker, x.E)][ENTRY]["entry"]["status"] + ":" + (res[(x.era, x.ticker, x.E)][ENTRY]["entry"]["reason"] or "")
                         for x in groups[e][nm] if (x.era, x.ticker, x.E) in res)
            late = sum(1 for x in groups[e][nm] if (x.era, x.ticker, x.E) in res and x.early_close
                       and res[(x.era, x.ticker, x.E)][ENTRY]["entry"]["status"] == "filled"
                       and res[(x.era, x.ticker, x.E)][ENTRY]["entry"]["fill_minute"] >= EARLY_CUT)
            say(f"- era {e} {nm}: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())) + f" | fills after 13:00 on a 13:00-close day {late}")
    # ---- headline: per-trade, tail first
    say("\n## HEADLINE — per trade R, tail first (ORH5 · low-of-day stop · p33_s3_t10; mature walks; exit slippage 0)")
    for e in ("A", "B"):
        G = groups[e]
        rws = [stat_row("HIS calls", G["his"], T), stat_row("control (same day)", G["ctl"], T),
               stat_row("HIS first breaks", [x for x in G["his"] if x.retrigger == 0], T),
               stat_row("HIS retriggers", [x for x in G["his"] if x.retrigger == 1], T),
               stat_row("control first breaks", [x for x in G["ctl"] if x.retrigger == 0], T),
               stat_row("control retriggers", [x for x in G["ctl"] if x.retrigger == 1], T),
               stat_row("HIS strictly-before (beside)", [x for x in G["his"] if x.strict], T),
               stat_row("HIS one event per base (beside)", [x for x in G["his"] if x.first_of_base], T),
               stat_row("post-E-only (hindsight, beside)", G["post"], T)]
        say(f"\n### era {e}{' (descriptive, n small)' if e == 'B' else ' (decides)'}")
        for ln in table(STAT_HDR, rws):
            say(ln)
        for si, s in enumerate(EXIT_SLIPS[1:], start=1):
            say(f"- exit slippage {100 * s:.1f}% per leg: " + "; ".join(
                f"{nm} mean R {r[10]}, >=10R /100 {r[5]}" for nm, r in
                (("his", stat_row("h", G["his"], T, si)), ("control", stat_row("c", G["ctl"], T, si)))))
        for nm, grp in (("his calls", G["his"]), ("control", G["ctl"]), ("post-E-only", G["post"])):
            op = [T[(x.era, x.ticker, x.E)] for x in grp if (x.era, x.ticker, x.E) in T and not T[(x.era, x.ticker, x.E)].mature]
            cut = sum(1 for x in grp if x.break_cut and (x.era, x.ticker, x.E) in T and not T[(x.era, x.ticker, x.E)].mature)
            say(f"- {nm}: filled walks NOT mature (degraded = the bars ended inside the horizon, a delisting / buyout / a cut at an identity "
                f"break; booked in the account at their last close, in no per-trade number above): {len(op)} "
                f"(degraded {sum(1 for t in op if t.status == 'degraded')}, of them cut at an identity break {cut}; other open marks "
                f"{sum(1 for t in op if t.status != 'degraded')}); their summed booked R {sum(t.realized_r for t in op):+.2f}")
    # ---- the difference, era A
    say("\n## HIS minus CONTROL (era A; DATE-MATCHED: each control trade weighted to his trades in its own (date, first-break / retrigger) "
        "cell; month-block, 2,000 resamples, seed 702, one draw of months for every difference)")
    G = groups["A"]
    his_t = [T[(x.era, x.ticker, x.E)] for x in G["his"] if (x.era, x.ticker, x.E) in T and T[(x.era, x.ticker, x.E)].mature]
    ctl_t = [T[(x.era, x.ticker, x.E)] for x in G["ctl"] if (x.era, x.ticker, x.E) in T and T[(x.era, x.ticker, x.E)].mature]

    def his_minus_control(his_tr: list, ctl_tr: list, tag: str = "") -> dict:
        nf_ = Counter(t.retrigger for t in his_tr)
        w_ = {s: nf_[s] / len(his_tr) for s in (0, 1)} if his_tr else {0: 0.5, 1: 0.5}
        out_ = {"_weights": (nf_, w_)}
        for meas, f in (("mean R", lambda r: r), (">=5R /100", lambda r: PER * (r >= 5.0)), (">=10R /100", lambda r: PER * (r >= 10.0))):
            out_[meas] = paired_block_diff(
                f(np.array([t.realized_r for t in his_tr], dtype=float)), [t.month for t in his_tr], [t.retrigger for t in his_tr],
                f(np.array([t.realized_r for t in ctl_tr], dtype=float)), [t.month for t in ctl_tr], [t.retrigger for t in ctl_tr], w_,
                a_date=[t.key[2] for t in his_tr], b_date=[t.key[2] for t in ctl_tr], key=f"qm_replay|A|{ENTRY}|{PRIMARY_ARM}|{meas}{tag}")
        return out_
    diffs = his_minus_control(his_t, ctl_t)
    nf, weights = diffs.pop("_weights")
    d0 = diffs["mean R"]
    say(f"- cells (date, stratum) holding his filled mature trades: {d0.get('cells_his')}; NOT covered by a control trade (dropped, counted): "
        f"{d0.get('cells_uncovered')} cells, {d0.get('his_uncovered')} of his {len(his_t)} trades; his trades matched {d0.get('his_matched')}")
    say(f"- the stratum-only beside: weights fixed at his filled mature trades' shares, first breaks {nf[0]} ({weights[0]:.3f}), retriggers "
        f"{nf[1]} ({weights[1]:.3f}), pooled across dates; the pooled beside: no weighting")
    for meas, d in diffs.items():
        say(f"- {meas}: DATE-MATCHED {d['matched']:+.3f} [{d['m_lo']:+.3f}, {d['m_hi']:+.3f}] | beside: stratum-only {d['weighted']:+.3f} "
            f"[{d['w_lo']:+.3f}, {d['w_hi']:+.3f}], pooled {d['raw']:+.3f} [{d['r_lo']:+.3f}, {d['r_hi']:+.3f}] | months {d['months']}, "
            f"resamples dropped {d['dropped_m']} / {d['dropped_w']} / {d['dropped_r']}")
    # ---- by year and by QQQ state
    say("\n## By year of E (era A; primary)")
    rws = []
    for y in sorted({x.year for x in G["his"]} | {x.year for x in G["ctl"]}):
        rws.append(stat_row(f"{y} his", [x for x in G["his"] if x.year == y], T))
        rws.append(stat_row(f"{y} control", [x for x in G["ctl"] if x.year == y], T))
    for ln in table(STAT_HDR, rws):
        say(ln)
    say("\n## By QQQ at D (era A; up = above BOTH its 10- and 20-day averages)")
    rws = []
    for s in ("up", "mixed", "down", ""):
        rws.append(stat_row(f"{s or 'unknown'} his", [x for x in G["his"] if x.qqq == s], T))
        rws.append(stat_row(f"{s or 'unknown'} control", [x for x in G["ctl"] if x.qqq == s], T))
    for ln in table(STAT_HDR, rws):
        say(ln)
    # ---- beside arms and entries
    say("\n## BESIDE — the other exits and entries (era A; never deciding)")
    rws = []
    for c in combos:
        rws.append(stat_row(f"{c[0]} {c[1]} his", G["his"], TT[c]))
        rws.append(stat_row(f"{c[0]} {c[1]} control", G["ctl"], TT[c]))
    for ln in table(STAT_HDR, rws):
        say(ln)
    # ---- corporate actions: worst trade with and without a DISCONTINUOUS event inside the hold
    flags = pd.read_csv(FILES["flags_A"], sep="\t", dtype=str, keep_default_na=False, usecols=["klass", "ticker", "date"])
    disc = defaultdict(list)
    for tk, d in zip(flags.loc[flags.klass == FIT.DISC_KLASS, "ticker"], flags.loc[flags.klass == FIT.DISC_KLASS, "date"]):
        disc[tk].append(d)
    calA = S["Ds"]["A"].cal
    hit = [t for t in his_t if any(calA[t.e_ci].isoformat() <= d <= calA[t.e_ci + t.sessions_held].isoformat() for d in disc.get(t.ticker, []))]
    rest = [t.realized_r for t in his_t if t not in hit]
    say(f"\n- his trades holding a G5 DISCONTINUOUS event: {len(hit)}" + (f" ({', '.join(f'{t.ticker} {calA[t.e_ci]} {t.realized_r:+.2f}R' for t in hit)})" if hit else "")
        + f"; worst trade with them {min([t.realized_r for t in his_t], default=float('nan')):+.2f}R, without {min(rest, default=float('nan')):+.2f}R")
    # ---- re-entries, counted only
    candA = S["eras"]["A"]
    later = defaultdict(list)
    for tk, b, E in zip(candA.ticker, candA.base_id, candA.E):
        later[(str(tk), str(b))].append(str(E))
    n_stop, n_with, n_rows, n_his_rows = 0, 0, 0, 0
    his_keys = {(x.ticker, x.E) for x in G["his"]}
    for x in G["his"]:
        k = (x.era, x.ticker, x.E)
        if k not in T or T[k].status not in ("stopped", "stopped_day0"):
            continue
        t = T[k]
        n_stop += 1
        exit_d = calA[t.e_ci + t.sessions_held].isoformat()
        lim = calA[min(len(calA) - 1, t.e_ci + REENTRY_WINDOW)].isoformat()
        nxt = [E for E in later[(x.ticker, x.base_id)] if exit_d < E <= lim]
        n_with += int(bool(nxt))
        n_rows += len(nxt)
        n_his_rows += sum(1 for E in nxt if (x.ticker, E) in his_keys)
    say(f"- RE-ENTRIES (counted, never walked): of {n_stop} his-call trades stopped out, {n_with} have a later break of the same base after the "
        f"exit day and within {REENTRY_WINDOW} sessions of E ({n_rows} such breaks; {n_his_rows} of them are themselves his calls)")
    # ---- the account
    say("\n## ACCOUNT CURVE — his calls, chronological (era A; start 1.0; PRIMARY = his sizing: 1% risk, 20% position cap, 30% per stock "
        "at cost, no margin)")
    startA = bisect.bisect_left(calA, date.fromisoformat(min(x.E for x in G["his"] + G["ctl"])))
    his_trades = [T[(x.era, x.ticker, x.E)] for x in G["his"] if (x.era, x.ticker, x.E) in T]
    acc_rows, curves = [], {}
    for cfg in CONFIGS:
        sim = simulate(his_trades, cfg, calA, startA)
        curves[cfg.name] = sim
        acc_rows.append([cfg.name, cfg.risk, cfg.cap, cfg.stock_limit if cfg.stock_limit is not None else "none", cfg.room, cfg.same_ticker,
                         cfg.exit_slip]
                        + [pct(sim["yearly"].get(y)) for y in FORK_YEARS] + [pct(sim["yearly"].get(2022)), f"{sim['final']:.3f}", pct(sim["max_dd"]),
                           sim["counts"]["entered"], sim["counts"]["skipped_no_room"], sim["counts"]["skipped_stock_limit"],
                           sim["counts"]["stock_limit_trimmed"], sim["counts"]["skipped_same_ticker"], sim["counts"]["same_ticker_concurrent"],
                           sim["counts"]["cap_bound"], sim["max_open"], pct(sim["max_gross"])])
    hdr = ["config", "risk", "cap", "stock limit", "room", "same ticker", "exit slip"] + [f"{y} return" for y in FORK_YEARS] + [
        "2022 (exits only)", "final equity", "max drawdown", "entered", "skipped no room", "skipped stock limit", "trimmed to the stock limit",
        "skipped same ticker", "concurrent same ticker", "cap bound", "max open", "max gross"]
    for ln in table(hdr, acc_rows):
        say(ln)
    prim = curves[PRIMARY_CONFIG.name]
    say("- primary: equity at each year end " + ", ".join(f"{y} {v:.3f}" for y, v in sorted(prim["year_end"].items()))
        + "; trades entered per year " + ", ".join(f"{y} {n}" for y, n in sorted(prim["entered_by_year"].items()))
        + "; skipped per year " + ", ".join(f"{y} {n}" for y, n in sorted(prim["skipped_by_year"].items())))
    with open(os.path.join(OUT_DIR, "account_his.tsv"), "w") as fh:
        fh.write("config\tdate\tequity\n")
        for nm, sim in curves.items():
            for ci, eq in zip(*sim["curve"]):
                fh.write(f"{nm}\t{calA[ci]}\t{eq:.10f}\n")
    # beside arms under the primary config
    rws = []
    for c in combos:
        tr = [TT[c][(x.era, x.ticker, x.E)] for x in G["his"] if (x.era, x.ticker, x.E) in TT[c]]
        sim = simulate(tr, PRIMARY_CONFIG, calA, startA)
        rws.append([f"{c[0]} {c[1]}"] + [pct(sim["yearly"].get(y)) for y in FORK_YEARS] + [f"{sim['final']:.3f}", pct(sim["max_dd"]), sim["counts"]["entered"]])
    post_tr = [T[(x.era, x.ticker, x.E)] for x in G["post"] if (x.era, x.ticker, x.E) in T]
    sim = simulate(post_tr, PRIMARY_CONFIG, calA, startA)
    rws.append(["post-E-only events (hindsight), ORH5 p33_s3_t10"] + [pct(sim["yearly"].get(y)) for y in FORK_YEARS] + [f"{sim['final']:.3f}", pct(sim["max_dd"]), sim["counts"]["entered"]])
    say("\n- beside (primary config): his calls under the other exits / entries, and the post-E-only events")
    for ln in table(["walk"] + [f"{y} return" for y in FORK_YEARS] + ["final equity", "max drawdown", "entered"], rws):
        say(ln)
    # ---- the control band
    say(f"\n## CONTROL BAND — the same simulation on {BAND_DRAWS} draws of same-day control events, the same count per day (seed {SEED})")
    his_by_date = Counter(x.E for x in G["his"])
    ctl_by_date, ctl_by_date_mix = defaultdict(list), defaultdict(list)
    for x in G["ctl"]:
        ctl_by_date[x.E].append((x.era, x.ticker, x.E))
        ctl_by_date_mix[x.E].append(((x.era, x.ticker, x.E), x.retrigger))
    mix = {d: (sum(1 for x in G["his"] if x.E == d and x.retrigger == 0), sum(1 for x in G["his"] if x.E == d and x.retrigger == 1)) for d in his_by_date}

    def band_draws(label: str, by_date: dict, pool: dict, mix_=None) -> tuple:
        rng = np.random.default_rng([SEED, zlib.crc32(f"qm_replay|band|A|{label}".encode())])
        dr, cnt_ = [], Counter()
        for _ in range(BAND_DRAWS):
            ids, c = sample_control(by_date, pool, rng, mix=mix_)
            cnt_.update(c)
            dr.append([T[k] for k in ids if k in T])
        return dr, cnt_

    def share_at_or_above(vals: list, hv) -> float:
        return (sum(1 for v in vals if v is not None and hv is not None and v >= hv) / len(vals)) if (hv is not None and vals) else float("nan")

    MEAS_LABEL = {"final": "final equity", "max_dd": "max drawdown (higher = WORSE)"}
    band_rows, band_out, band_share = [], [], {}
    for label, use_mix in ((BAND_REGISTERED, False), ("same-day, mix-matched (beside)", True)):
        draws, cnt = band_draws(label, his_by_date, ctl_by_date_mix if use_mix else ctl_by_date, mix if use_mix else None)
        for cfg in CONFIGS:
            sims = [simulate(tr, cfg, calA, startA) for tr in draws]
            his_sim = curves[cfg.name]
            for y in FORK_YEARS + ("final", "max_dd"):
                vals = [s["yearly"].get(y) for s in sims] if isinstance(y, int) else [s[y] for s in sims]
                hv = his_sim["yearly"].get(y) if isinstance(y, int) else his_sim[y]
                bs = band_summary(vals)
                share_ge = share_at_or_above(vals, hv)
                band_out.append((label, cfg.name, y, bs, hv, share_ge))
                band_share[(label, cfg.name, y)] = share_ge
                if cfg is PRIMARY_CONFIG or y == "final":
                    band_rows.append([label, cfg.name, MEAS_LABEL.get(y, f"{y} return"), fmt(hv, 3), fmt(bs.get(5), 3), fmt(bs.get(50), 3),
                                      fmt(bs.get(95), 3), pct(share_ge)])
        say(f"- {label}: draw facts " + (", ".join(f"{k} {v}" for k, v in sorted(cnt.items())) or "none short"))
    for ln in table(["band", "config", "year / measure", "his calls", "control 5th pct", "control median", "control 95th pct",
                     "share of draws >= his (for max drawdown: draws as deep or DEEPER, i.e. worse)"], band_rows):
        say(ln)
    with open(os.path.join(OUT_DIR, "account_band.tsv"), "w") as fh:
        fh.write("band\tconfig\tmeasure\this\tp5\tp25\tp50\tp75\tp95\tshare_ge_his\n")
        for label, nm, y, bs, hv, sg in band_out:
            fh.write("\t".join(str(x) for x in (label, nm, y, hv, bs.get(5), bs.get(25), bs.get(50), bs.get(75), bs.get(95), sg)) + "\n")
    # ---- era B, descriptive
    calB = S["Ds"]["B"].cal
    GB = groups["B"]
    trB = [T[(x.era, x.ticker, x.E)] for x in GB["his"] if (x.era, x.ticker, x.E) in T]
    if trB:
        sB = simulate(trB, PRIMARY_CONFIG, calB, min(t.e_ci for t in trB))
        say(f"\n- era B his calls (descriptive, {len(trB)} trades): yearly " + ", ".join(f"{y} {pct(v)}" for y, v in sorted(sB["yearly"].items()))
            + f", final {sB['final']:.3f}, max drawdown {pct(sB['max_dd'])}")
    # ---- the fork
    bshare = band_share[(BAND_REGISTERED, PRIMARY_CONFIG.name, "final")]
    d = diffs["mean R"]
    verdict, strong_years, curve_strong, curve_arm, interval_arm = fork_verdict(prim["yearly"], d["m_lo"], bshare)
    say("\n## THE FORK (registered before any outcome; era A, ORH5 + p33_s3_t10, the primary account: 1% risk, 20% cap, 30% per stock)")
    say(f"- curve arm: yearly return >= +{100 * STRONG_YEAR_RET:.0f}% in {len(strong_years)} of 2017-21 ({strong_years or 'none'}; needs >= "
        f"{STRONG_YEARS_MIN} -> {'strong' if curve_strong else 'not strong'}) AND the registered same-day band at or above his final equity "
        f"in {pct(bshare)} of {BAND_DRAWS} draws (needs <= {pct(BAND_SHARE_MAX, 0)}) -> {'MET' if curve_arm else 'not met'}")
    say(f"- interval arm: his minus control mean R per filled mature trade, DATE-MATCHED {d['matched']:+.3f} [{d['m_lo']:+.3f}, "
        f"{d['m_hi']:+.3f}] -> {'MET (lower end above zero)' if interval_arm else 'not met'}")
    say(f"- VERDICT: **{verdict}** — " + {
        "SELECTION": "his calls, executed under his rules, carry the result: the gap between our system and his record is WHICH breakouts "
                     "are taken (the next work fixes the filter)",
        "DATES / market": "his curve is strong but the same day's other breakouts compound as well or better: the DATES / the market carry "
                          "it, not his stock picks (the next work is which days to be in, its own registration)",
        "EXECUTION / data": "even his own calls do not carry it under these rules: the gap is EXECUTION / data (vary entry, stop, exit, "
                            "sizing per his words)"}[verdict])
    # ---- both fork arms on the strictly-before calls (beside the verdict; decide nothing)
    strict = [x for x in G["his"] if x.strict]
    st_tr = [T[(x.era, x.ticker, x.E)] for x in strict if (x.era, x.ticker, x.E) in T]
    st_sim = simulate(st_tr, PRIMARY_CONFIG, calA, startA)
    st_draws, st_cnt = band_draws("strictly-before (beside)", Counter(x.E for x in strict), ctl_by_date)
    st_share = share_at_or_above([simulate(tr, PRIMARY_CONFIG, calA, startA)["final"] for tr in st_draws], st_sim["final"])
    st_his_t = [t for t in st_tr if t.mature]
    st_d = his_minus_control(st_his_t, ctl_t, tag="|strict")["mean R"]
    st_years = [y for y in FORK_YEARS if y in st_sim["yearly"] and st_sim["yearly"][y] >= STRONG_YEAR_RET]
    st_curve = len(st_years) >= STRONG_YEARS_MIN and math.isfinite(st_share) and st_share <= BAND_SHARE_MAX
    st_int = math.isfinite(st_d["m_lo"]) and st_d["m_lo"] > 0
    say(f"- BESIDE (decides nothing): both arms on the {len(strict)} strictly-before calls (clean of E's bar; {len(st_tr)} filled, "
        f"{len(st_his_t)} mature): curve — yearly >= +50% in {st_years or 'none'}, final {st_sim['final']:.3f}, their own same-day band "
        f"({BAND_DRAWS} draws, {len(strict)} events on {len(set(x.E for x in strict))} dates"
        f"{'; ' + ', '.join(f'{k} {v}' for k, v in sorted(st_cnt.items())) if st_cnt else ''}) at or above it in {pct(st_share)} -> "
        f"{'MET' if st_curve else 'not met'}; interval — DATE-MATCHED {st_d['matched']:+.3f} [{st_d['m_lo']:+.3f}, {st_d['m_hi']:+.3f}] "
        f"({st_d.get('cells_uncovered')} cells / {st_d.get('his_uncovered')} trades uncovered, dropped) -> {'MET' if st_int else 'not met'}")

if __name__ == "__main__":
    sys.exit(main())
