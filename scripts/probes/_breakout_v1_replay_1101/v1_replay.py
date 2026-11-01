#!/usr/bin/env python3
"""Breakout v1 — the PAPER BASELINE replay, 2017-01-03 .. 2024-12-31 (TASK C, 2026-11-01).

Registration: docs/analysis/breakout_v1_paper_replay_prereg_2026-11-01.md (the bar is written there BEFORE any
outcome; the `walk` stage refuses unless that doc's footer pins match every artefact it rests on).

THE LINE: offline research, $0, no live change; this recommends nothing about live money.
THE SEAL: no bar, row or file dated 2025-01-01 or later is read (#710's sealed 2025-26 period). Every loader is gated
(`SEAL`): the cb702 daily export is stream-filtered to dates < SEAL before any bar is parsed; split rows and regime rows
dated >= SEAL are skipped on their date column alone; minute files are chosen by their date name; the walk refuses an E
or a forward bar >= SEAL.

What it CALLS (the live code, unchanged):
  * the nightly list: `breakout_v1.security_admitted` / `fund_rule`, `v1_gates`, `cb.cross_section_one_date` (the RS pool,
    his ruling (a)); the per-name pool arithmetic (`rs_returns_contiguous`, `history_ok`, `cb._dollar_vol_median`) is
    RE-IMPLEMENTED vectorised in `ticker_facts` and ASSERTED EQUAL to the live functions, and `night_members` (a copy of
    `breakout_v1_list.scan_members`) is ASSERTED EQUAL to `scan_members` on sampled nights — both in the `parity` stage;
  * the entry: `breakout_v1_entry.evaluate` (ORH5 / level / day-low stop / width / F1 through the last completed
    minute), `f1_permits`, `stop_from_low`, `_terminal_reason` (EOD > abstain > volume lapse), `stop_at_fill_decision`
    (the stop at the TRUE low one minute after the fill), `breakout_v1_volume_curve.CUM_SHARE`,
    `order_manager.stop_limit_buy_price` (ast-extracted, not imported: the module pulls the broker stack);
  * the exit: `breakout_pp_rules.day0_facts`, `session3_decision`, `trail_decision`, `reached_plus_1r`,
    `stop_after_third`, `target_price`, `retry_decision` (asserted wired; never reached in a replay where every sale
    completes), and the DEFINITION `consolidation_breakout_pp.walk_pp` the stepper is asserted equal to, trade by
    trade and on a fuzz;
  * the data plumbing: `scripts/probes/_cb_backtest/runner.py` loaders (`load_daily`, `load_raw_close`, `load_splits`,
    `load_small`, `load_breaks`, `break_mask`, `read_minute_file`, `minutes_for`, `load_done_pairs`),
    `block_bootstrap_ci` (month-block, 2,000 draws, seed 702), `cb.forward_window`, `cb.is_mature`,
    `cb.phase_qqq_10_20`.
What it RE-IMPLEMENTS (the broker I/O; each declared in the registration §4-5): the stop-limit / limit fill mechanics on
minute bars, the cancel + re-place of the stop, the #500 fallback's "latest trade" (= the last completed minute's close;
`order_manager.submit_entry`), the width at the expected fill (`breakout_v1_entry.width_at_expected_fill`), the re-price
trigger (`_manage`), the day-0 +2R limit (the walk's touch-is-a-fill reading), the stop leg on daily bars, and the PAPER
BOOK as one chronological event loop (`apply_book`): the same-ticker guard (`entry_pipeline.submit_trade_entry` step 1b),
the 5-slot cap, and — the lane row — the 2% daily-loss limit and the 10-loss circuit breaker
(`live_tracker._check_safeguards`) on a declared risk-fraction model. The drawdown breaker (active on paper) needs an
equity path and is NOT modelled (named).

Stages (argparse): population | request | parity | dryrun | pins | coverage | walk. Only `walk` computes an outcome,
and only once.
"""
from __future__ import annotations

import argparse
import ast
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import subprocess

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agents.market_intelligence import breakout_v1 as bv  # noqa: E402
from agents.market_intelligence import breakout_v1_list as bvl  # noqa: E402
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402
from agents.market_intelligence import consolidation_breakout_pp as cpp  # noqa: E402
from agents.market_intelligence import constants as K  # noqa: E402
from agents.market_intelligence.broker import breakout_pp_rules as ppr  # noqa: E402
from agents.market_intelligence.broker import breakout_v1_entry as bve  # noqa: E402
from agents.market_intelligence.broker import breakout_v1_volume_curve as curve  # noqa: E402
from scripts.probes._cb_backtest import runner  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 0. Constants, paths, the seal
# ═══════════════════════════════════════════════════════════════════════════════════════════════
SEAL = date(2025, 1, 1)                      # nothing dated here or later is read
E_FIRST = date(2017, 1, 3)                   # the first breakout day of the window
E_LAST = date(2024, 12, 31)                  # the last breakout day of the window
ERA_A_D_LAST = date(2022, 3, 31)             # watch nights D <= this read cb702_pre_v2 (daily 2016-01-04 .. 2022-06-30)
ERA_B_D_FIRST = date(2022, 4, 1)             # watch nights D >= this read cb702 (daily 2021-09-27 .., sealed < 2025)
ERA_A_E_LAST = date(2021, 12, 31)            # the REPORTING eras split on the breakout day: 2017-21 vs 2022-24
DATA = Path(os.environ.get("APOLLO_DATA", "/Users/alvinfung/apollo_data"))
PRE = DATA / "cb702_pre_v2"
CB = DATA / "cb702"
SCRATCH = Path(os.environ.get("BV1_SCRATCH", "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/"
                              "d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/Creplay"))
OUT = HERE / "out"
DOC = REPO / "docs" / "analysis" / "breakout_v1_paper_replay_prereg_2026-11-01.md"
REQUEST = HERE / "minute_request.tsv"        # written ONCE by `request`, pinned in the body, never rewritten
RAW_REQUEST = HERE / "raw_close_request.tsv"  # the era-B tickers whose raw scale rests on the split list only (raw_src 2)
NEW_MINUTE_DIR = CB / "minutes_bv1_1101"     # where the main loop's minute pull lands (read last, see MINUTE_DIRS)
RAW_PULL = CB / "raw_close_bv1_1101.csv.gz"  # the main loop's raw-close pull: headerless `ticker,date,raw_close`, dates < SEAL
RAW_PULL_META = CB / "raw_close_bv1_1101.meta.json"   # {"adjustment": "raw", "request_sha256": sha of RAW_REQUEST, ...}
FREEZE_MARK = runner.FREEZE_MARK             # "<!-- FREEZE -->"
UNFETCHABLE_MAX = 0.02                       # the walk refuses when more than 2% of the request is unfetchable / missing raw

# the minute stores, in precedence order (the first store that logged the (date, ticker) pair as fetched is read)
MINUTE_DIRS = [PRE / "minutes", CB / "minutes", CB / "minutes_asis_1026", CB / "minutes_rev_1024",
               CB / "minutes_intra_1025", CB / "minutes_ep_1023", CB / "minutes_ep_1024",
               CB / "minutes_com_delta_1018", CB / "minutes_pre_com_1018", CB / "cb702_minutes_delta_out",
               NEW_MINUTE_DIR]

# the replay's own parameters (declared in the registration; none is a rule of his)
CAP_SLOTS = K.MAX_CONCURRENT_LIVE_POSITIONS  # 5: the paper account's cap, shared with the small-cap lane (its occupancy = 0 here)
DAILY_LOSS = K.DAILY_LOSS_LIMIT_PCT          # 0.02: the lane row's daily-loss limit (live_tracker._check_safeguards)
BREAKER_N = K.CIRCUIT_BREAKER_CONSEC_LOSSES  # 10: the lane row's circuit breaker
RISK_FRAC = K.RISK_PCT                       # 0.02 of equity risked per trade (sizing, for the lane row's loss fractions)
NOTIONAL_CAP = K.MAX_POSITION_PCT            # 0.20 of equity: the notional cap that bounds the risk fraction
COST_CENTS = (0.0, 2.0, 5.0)                 # per share, RAW price scale, on the entry and on every exit
PRIMARY_COST = 2.0                           # the primary row's cents
HORIZON = cb.EXIT_HORIZON                    # 120 sessions, the registered maturity convention (live has none)
BOOKS = ("guard", "cap", "lane")             # ticker guard only | guard + 5 slots (PRIMARY) | guard + slots + daily loss + breaker
MISMATCH_MAX = cb.MINUTE_DAILY_MISMATCH_MAX  # 1%: minute-day high/low vs the daily bar's
BRIDGE_TOL = 0.005                           # the era-B raw-factor bridge: raw/adjusted must be stable across the overlap
N_FLOOR = 100                                # the bar's n floor (mature trades)
TAIL_SHARE = 0.08                            # the bar's tail: the share of trades at >= 3R
FAIL_MEAN_REF = 0.25                         # FAIL needs the whole interval under a quarter of his +1.06R per trade
BOOT_KEY = "bv1_replay"

GATE_ORDER = ("ticker", "identity_break", "short_history", "below_floors", "no_r63")


def sealed(d: date) -> bool:
    return d < SEAL


def assert_sealed(d: date, what: str) -> None:
    if not sealed(d):
        raise RuntimeError(f"SEAL: {what} dated {d} is >= {SEAL} — refused")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Loaders (every one gated on the seal)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def sealed_copy_of_daily(src: Path, dst: Path) -> Path:
    """cb702's daily export runs to 2026-10-16: stream-filter it to bar dates < SEAL BEFORE any bar is parsed. A row is
    dropped on its date column alone (the string compare on 'YYYY-MM-DD'); its prices are never decoded. A sidecar
    (`<dst>.src.json`) records the SOURCE's sha256 and the kept / dropped counts: a copy whose sidecar names another
    source (or has none) is regenerated, never reused (review LOW, 2026-11-01)."""
    side = dst.with_name(dst.name + ".src.json")
    src_sha = sha(src)
    if dst.exists() and side.exists():
        try:
            meta = json.loads(side.read_text())
        except Exception:  # loud-ok: an unreadable sidecar is a missing one — regenerate
            meta = {}
        if meta.get("source_sha256") == src_sha and meta.get("seal") == SEAL.isoformat():
            return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f"{dst.name}.{os.getpid()}.tmp")    # per process: two stages may regenerate it at once
    seal = SEAL.isoformat()
    kept = dropped = 0
    with gzip.open(src, "rt") as fh, gzip.open(tmp, "wt", compresslevel=6) as out:
        for ln in fh:
            d = ln.split(",", 2)[1]
            if d >= seal:
                dropped += 1
                continue
            out.write(ln)
            kept += 1
    tmp.rename(dst)
    side.write_text(json.dumps({"source": str(src), "source_sha256": src_sha, "seal": seal, "kept": kept, "dropped": dropped}))
    print(f"sealed copy {dst.name}: kept {kept:,} rows < {seal}, dropped {dropped:,} (dates only compared)", flush=True)
    return dst


def load_raw_pull(path: Path = RAW_PULL, meta_path: Path = RAW_PULL_META, request_path: Path = RAW_REQUEST) -> tuple:
    """The main loop's raw-close pull for the `raw_src = 2` list tickers (registration §7): headerless
    `ticker,date,raw_close` at RAW_PULL, with the sidecar RAW_PULL_META naming `adjustment: raw` and the sha256 of the
    request it answered. -> ({(ticker, date_iso): raw close}, meta). A row dated >= SEAL REFUSES the run (the pull must be
    bounded at 2024-12-31); a bad sidecar refuses. Missing file -> ({}, None)."""
    if not path.exists():
        return {}, None
    if not meta_path.exists():
        raise SystemExit(f"REFUSED — {path} has no sidecar {meta_path.name}")
    meta = json.loads(meta_path.read_text())
    if str(meta.get("adjustment", "")).lower() != "raw":
        raise SystemExit(f"REFUSED — the raw-close pull's sidecar says adjustment={meta.get('adjustment')!r}, not 'raw'")
    if request_path.exists() and meta.get("request_sha256") != sha(request_path):
        raise SystemExit("REFUSED — the raw-close pull's sidecar names another request than raw_close_request.tsv on disk")
    out = {}
    seal = SEAL.isoformat()
    with gzip.open(path, "rt") as fh:
        for ln in fh:
            f = ln.rstrip("\n").split(",")
            if len(f) < 3 or f[1] == "date":
                continue
            if f[1] >= seal:
                raise SystemExit(f"REFUSED — the raw-close pull carries a row dated {f[1]} >= {seal}")
            c = float(f[2])
            if not c > 0:
                continue
            out[(f[0], f[1])] = c
    return out, meta


def load_splits_sealed(path: Path) -> tuple:
    """`runner.load_splits` on the rows dated < SEAL only (a split executing >= SEAL is a sealed row: skipped on its
    date column alone, counted). -> ({ticker: [(exec_date, ratio)]}, n_skipped)."""
    kept, skipped = [], 0
    for line in path.read_text().splitlines():
        f = line.split("|")
        if len(f) < 4:
            continue
        if date.fromisoformat(f[1]) >= SEAL:
            skipped += 1
            continue
        kept.append(line)
    tmp = SCRATCH / "pop" / "splits_sealed.psv"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("\n".join(kept) + "\n")
    return runner.load_splits(tmp), skipped


ETV_NAMES = REPO / "tests" / "fixtures" / "breakout_v1_parity" / "etv_names_2026-10-28.tsv"


def load_etv_names() -> dict:
    """The committed Polygon reference NAMES of the ETV tickers as of 2026-10-28 (the parity fixture): the fund rule
    is a NAME rule, and the local stores carry no names. Applied to every night (a point-in-time approximation,
    declared); an ETV not in the file fails closed (`no_name`), as the live rule does with no stored name."""
    out = {}
    for row in csv.DictReader(ETV_NAMES.open(), delimiter="\t"):
        out[row["ticker"]] = row["name"]
    return out


def load_types(path: Path) -> dict:
    """`sectype|ticker|type|exchange` rows -> {ticker: type}. The regime rows (dated 2025-03-03 ..) are NOT read: the
    file's regime labels start inside the seal, so the replay carries no Apollo regime (the QQQ phase is the market-state
    slice instead)."""
    sec = {}
    for line in path.read_text().splitlines():
        f = line.split("|")
        if f[0] == "sectype" and len(f) >= 3:
            sec[f[1]] = f[2]
    return sec


@dataclass
class Store:
    name: str
    D: "runner.Daily"
    raw_factor: np.ndarray            # per flat row: raw = adjusted x factor
    raw_src: np.ndarray               # per flat row: 0 = raw file, 1 = bridge, 2 = split list only
    types: dict
    etv_names: dict                   # {ticker: Polygon name} for the fund rule (the committed 2026-10-28 list)
    breaks: dict                      # {ticker: break ordinals} (era A only; {} for era B)
    cal_ord: np.ndarray               # SPY calendar as ordinals
    notes: dict = field(default_factory=dict)


def load_store(era: str) -> Store:
    t0 = time.time()
    if era == "A":
        D = runner.load_daily(PRE / "daily_closes_all.csv.gz")
        assert D.cal[-1] < SEAL
        raw_c = runner.load_raw_close(PRE / "daily_raw_close.csv.gz", D)
        factor = raw_c / D.c
        src = np.zeros(len(D.c), dtype=np.int8)
        types = load_types(PRE / "small_pulls.psv")
        breaks = runner.load_breaks(PRE / "symbol_guard.tsv")
        notes = {"raw_factor": "pre_v2 daily_raw_close.csv.gz per bar (exact)"}
    elif era == "B":
        sealed_path = sealed_copy_of_daily(CB / "daily_closes_all.csv.gz", SCRATCH / "pop" / "cb702_daily_lt2025.csv.gz")
        D = runner.load_daily(sealed_path)
        assert D.cal[-1] < SEAL, D.cal[-1]
        splits, n_skipped = load_splits_sealed(CB / "cb702_splits.psv")
        factor, src, bridge_notes = era_b_raw_factor(D, splits)
        types = load_types(CB / "small_pulls.psv")
        breaks = {}
        notes = {"raw_factor": "bridge (pre_v2 raw / cb702 adjusted on the 2022-04..06 overlap, then the split list "
                               "<= 2024-12-31) where the ticker is in both stores; else the split list <= 2024-12-31 only",
                 "splits_rows_skipped_sealed": n_skipped, **bridge_notes}
    else:
        raise ValueError(era)
    cal_ord = np.array([d.toordinal() for d in D.cal], dtype=np.int64)
    etv_names = load_etv_names()
    n_etv = sum(1 for t, st in types.items() if st == bv.FUND_SECURITY_TYPE)
    notes["etv_tickers_typed"] = n_etv
    notes["etv_tickers_with_a_name"] = sum(1 for t, st in types.items() if st == bv.FUND_SECURITY_TYPE and t in etv_names)
    print(f"store {era}: loaded in {time.time() - t0:.0f}s; {notes}", flush=True)
    return Store(era, D, factor, src, types, etv_names, breaks, cal_ord, notes)


def era_b_raw_factor(D: "runner.Daily", splits: dict) -> tuple:
    """RAW/adjusted factor per flat row of the sealed cb702 export WITHOUT reading a 2025+ split row.
    For a ticker in BOTH stores: F* = pre_v2 RAW close / cb702 ADJUSTED close on the last common date d* of the
    2022-04-01 .. 2022-06-30 overlap = the product of every split executing after d* (the 2025-26 ones included,
    derived, not read); then factor(t) = F* x prod(splits in (t, d*]) / prod(splits in (d*, t]) — every split in those
    spans is dated <= 2024-12-31 (readable). The overlap ratio must be stable (max/min - 1 <= BRIDGE_TOL) on the common
    dates, else the ticker falls back to the split list. A ticker not in pre_v2 (a listing after mid-2022 or a dedupe
    casualty): the split list <= 2024-12-31 alone — a 2025-26 splitter among them carries the wrong raw scale (bias
    declared in the registration)."""
    # pre_v2 raw closes on the overlap, keyed by (ticker, ordinal)
    raw = {}
    lo, hi = date(2022, 4, 1).isoformat(), date(2022, 6, 30).isoformat()
    with gzip.open(PRE / "daily_raw_close.csv.gz", "rt") as fh:
        for ln in fh:
            t, d, c = ln.rstrip("\n").split(",")
            if lo <= d <= hi:
                raw[(t, date.fromisoformat(d).toordinal())] = float(c)
    cal_ord = np.array([d.toordinal() for d in D.cal], dtype=np.int64)
    factor = np.ones(len(D.c))
    src = np.full(len(D.c), 2, dtype=np.int8)
    n_bridge = n_unstable = n_split_only = 0
    for k, t in enumerate(D.tickers):
        a, b = int(D.start[k]), int(D.stop[k])
        ords = cal_ord[D.ci[a:b]]
        dates = [D.cal[i] for i in D.ci[a:b]]
        sp = splits.get(t, [])
        ratios = []
        for i in range(a, b):
            r = raw.get((t, int(ords[i - a])))
            if r is not None and D.c[i] > 0:
                ratios.append((i, r / D.c[i]))
        if ratios:
            vals = np.array([x[1] for x in ratios])
            if vals.max() / vals.min() - 1.0 <= BRIDGE_TOL:
                i_star, f_star = ratios[-1]
                d_star = dates[i_star - a]
                for i in range(a, b):
                    d = dates[i - a]
                    f = f_star
                    for ex, ratio in sp:
                        if d < ex <= d_star:
                            f *= ratio          # a split between this bar and d*: this bar's raw price is pre-split
                        elif d_star < ex <= d:
                            f /= ratio          # a split between d* and this bar: already in this bar's raw price
                    factor[i] = f
                src[a:b] = 1
                n_bridge += 1
                continue
            n_unstable += 1
        factor[a:b] = runner.factor_by_bar(dates, sp)
        n_split_only += 1
    return factor, src, {"bridge_tickers": n_bridge, "bridge_unstable_fell_back": n_unstable, "split_list_only_tickers": n_split_only}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The nightly list (the live gates on the historical bars)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _rolling_median(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        win = np.lib.stride_tricks.sliding_window_view(x, w)
        out[w - 1:] = np.median(win, axis=1)
    return out


def ticker_facts(S: Store, k: int) -> dict:
    """Per-bar facts of ticker id k that the pool test needs, vectorised but EQUAL to the live per-name arithmetic:
    raw close, the 20-session median dollar volume (`cb._dollar_vol_median`), r21/r63/r126 over consecutive sessions
    (`bv.rs_returns_contiguous`), the 86-session consecutive history (`bv.history_ok`), the identity-break mask."""
    D = S.D
    a, b = int(D.start[k]), int(D.stop[k])
    c, v = D.c[a:b], D.v[a:b]
    cidx = D.ci[a:b].astype(np.int64)
    n = b - a
    dv = _rolling_median(c * v, cb.DOLLAR_VOL_WINDOW)
    rets = {}
    for hz in bv.RS_HORIZONS:
        r = np.full(n, np.nan)
        if n > hz:
            j = np.arange(hz, n)
            ok = (c[j - hz] > 0) & (cidx[j] - cidx[j - hz] == hz)
            with np.errstate(invalid="ignore", divide="ignore"):
                r[j[ok]] = c[j[ok]] / c[j[ok] - hz] - 1.0
        rets[hz] = r
    hist = np.zeros(n, dtype=bool)
    if n > bv.DEEP:
        j = np.arange(bv.DEEP, n)
        hist[j] = (cidx[j] - cidx[j - bv.DEEP]) == bv.DEEP
    brk = np.zeros(n, dtype=bool)
    t = D.tickers[k]
    if t in S.breaks:
        brk = runner.break_mask(S.cal_ord[cidx], S.breaks[t], window=bv.MIN_BARS)
    return {"a": a, "b": b, "raw": S.raw_factor[a:b] * c, "dv": dv, "r21": rets[21], "r63": rets[63], "r126": rets[126],
            "hist": hist, "brk": brk, "cidx": cidx}


class _RowsAt:
    """{calendar index: [(ticker id, flat row)]} without materialising 12M tuples: a stable argsort of the flat rows
    by calendar index, sliced per night."""

    def __init__(self, order: np.ndarray, ci_sorted: np.ndarray, row_tid: np.ndarray):
        self.order, self.ci_sorted, self.row_tid = order, ci_sorted, row_tid

    def get(self, ci: int, default=None):
        lo = int(np.searchsorted(self.ci_sorted, ci, "left"))
        hi = int(np.searchsorted(self.ci_sorted, ci, "right"))
        idx = self.order[lo:hi]
        return [(int(self.row_tid[i]), int(i)) for i in idx]


def night_members(S: Store, facts: list, ci: int, rows_at) -> tuple:
    """Tonight's RS-pool members (his ruling (a): every security at the floors, funds and ETFs included) and the pool
    counts, mirroring `breakout_v1_list.scan_members` test for test. `rows_at[ci]` = [(ticker id, bar index)]."""
    members, counts = [], Counter()
    for k, i in rows_at.get(ci, []):
        t = S.D.tickers[k]
        f = facts[k]
        li = i - f["a"]
        st = S.types.get(t)
        ok, why = bv.security_admitted(t, st, S.etv_names.get(t))   # the fund rule on the committed 2026-10-28 names; no name -> fails closed
        if why == "ticker":
            counts["excluded_ticker"] += 1
            continue
        counts[("admitted_" if ok else "rank_only_") + why] += 1
        if st == bv.FUND_SECURITY_TYPE:
            counts["fund_kept" if ok else "fund_excluded_" + why.replace("fund_", "")] += 1
        if f["brk"][li]:
            counts["identity_break"] += 1
            continue
        if li + 1 < cb.DOLLAR_VOL_WINDOW:
            counts["short_history"] += 1
            continue
        if not (f["raw"][li] >= bv.MIN_PRICE and f["dv"][li] >= bv.MIN_DOLLAR_VOL):
            counts["below_floors"] += 1
            continue
        r21, r63, r126 = (None if np.isnan(f[h][li]) else float(f[h][li]) for h in ("r21", "r63", "r126"))
        if r63 is None:
            counts["no_r63"] += 1
            continue
        members.append({"k": k, "i": i, "ticker": t, "st": st or "", "r21": r21, "r63": r63, "r126": r126,
                        "listable": bool(ok), "history": bool(f["hist"][li]), "raw_close": float(f["raw"][li]),
                        "is_etv": st == bv.FUND_SECURITY_TYPE})
    return members, counts


def run_population(era: str, out_dir: Path) -> dict:
    S = load_store(era)
    D = S.D
    cal = D.cal
    d_lo = max(E_FIRST - timedelta(days=10), cal[0]) if era == "A" else ERA_B_D_FIRST
    d_hi = ERA_A_D_LAST if era == "A" else E_LAST
    # the nights: every SPY session D with d_lo <= D <= d_hi whose next session E exists and E <= E_LAST, E >= E_FIRST
    nights = []
    for ci, d in enumerate(cal):
        if d < d_lo or d > d_hi or ci + 1 >= len(cal):
            continue
        e = cal[ci + 1]
        if e < E_FIRST or e > E_LAST:
            continue
        assert_sealed(e, "breakout day")
        nights.append(ci)
    print(f"era {era}: {len(nights)} watch nights {cal[nights[0]]} .. {cal[nights[-1]]}", flush=True)
    t0 = time.time()
    facts = [ticker_facts(S, k) for k in range(len(D.tickers))]
    print(f"  per-ticker facts in {time.time() - t0:.0f}s", flush=True)
    row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
    order = np.argsort(D.ci, kind="stable")
    ci_sorted = D.ci[order]
    rows_at = _RowsAt(order, ci_sorted, row_tid)
    bars_cache: dict = {}
    qqq = runner.bars_for(D, D.tid["QQQ"])[0] if "QQQ" in D.tid else None
    qqq_pos = {d: j for j, d in enumerate(qqq.dates)} if qqq is not None else {}
    list_rows, night_rows = [], []
    gate_fails_all = Counter()
    t0 = time.time()
    for n_i, ci in enumerate(nights):
        Dd = cal[ci]
        members, counts = night_members(S, facts, ci, rows_at)
        rs_best, _, _, _ = cb.cross_section_one_date([m["r21"] for m in members], [m["r63"] for m in members],
                                                     [m["r126"] for m in members], [None] * len(members))
        fails = Counter()
        rows_tonight = []
        n_rs, n_eval, n_etv_lost, n_rank_only_rs = 0, 0, 0, 0
        for m, rb in zip(members, rs_best):
            if rb is None or rb < bv.RS_MIN:
                continue                                     # the rs gate fails: the name cannot list whatever the rest says
            n_rs += 1
            if not m["listable"]:
                n_rank_only_rs += 1
                if not m["is_etv"]:
                    continue
            if not m["history"]:
                fails["history"] += 1
                continue
            if m["k"] not in bars_cache:
                bars_cache[m["k"]] = runner.bars_for(D, m["k"])
            bars, cidx = bars_cache[m["k"]]
            Di = m["i"] - facts[m["k"]]["a"]
            try:
                g = bv.v1_gates(bars, Di, rs_best=rb, raw_close=m["raw_close"], cidx=cidx)
            except Exception as e:  # loud-ok: counted, as the live job counts it
                fails["gate_error"] += 1
                print(f"  gate error {m['ticker']} {Dd}: {type(e).__name__}: {e}", flush=True)
                continue
            if not m["listable"]:                            # an ETV that would list with its name known: counted, never listed
                if g["ok"]:
                    n_etv_lost += 1
                continue
            n_eval += 1
            for kk in g["failed"]:
                fails[kk] += 1
            if not g["ok"]:
                continue
            e_date = cal[ci + 1]
            rows_tonight.append({"scan_date": Dd.isoformat(), "E": e_date.isoformat(), "ticker": m["ticker"],
                                 "level": float(g["level"]), "vol_bar": float(g["vol_bar"]), "adr20": g["adr20"],
                                 "rs_best": float(rb), "close": g["close"], "raw_factor_D": float(S.raw_factor[m["i"]]),
                                 "raw_src": int(S.raw_src[m["i"]]), "security_type": m["st"],
                                 "prior_move": g["prior_move"], "pole_date": g["pole_date"], "base_low": g["base_low"],
                                 "era_store": era})
        rows_tonight.sort(key=lambda r: (-r["rs_best"], r["ticker"]))
        for rank, r in enumerate(rows_tonight, 1):
            r["list_rank"] = rank
        list_rows.extend(rows_tonight)
        gate_fails_all.update(fails)
        phase = None
        if qqq is not None and Dd in qqq_pos:
            phase = bool(cb.phase_qqq_10_20(qqq, qqq_pos[Dd]))
        night_rows.append({"scan_date": Dd.isoformat(), "E": cal[ci + 1].isoformat(), "pool": len(members),
                           "listable": sum(1 for m in members if m["listable"]), "rs_ge98": n_rs,
                           "rank_only_rs_ge98": n_rank_only_rs, "evaluated": n_eval, "passing": len(rows_tonight),
                           "etv_would_list": n_etv_lost, "qqq_phase": phase,
                           **{f"pool_{k}": v for k, v in counts.items()}, **{f"fail_{k}": v for k, v in fails.items()}})
        if n_i % 100 == 0:
            print(f"  night {n_i}/{len(nights)} {Dd}: pool {len(members)} rs>=98 {n_rs} passing {len(rows_tonight)} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["scan_date", "E", "ticker", "list_rank", "level", "vol_bar", "adr20", "rs_best", "close", "raw_factor_D",
            "raw_src", "security_type", "prior_move", "pole_date", "base_low", "era_store"]
    write_tsv(out_dir / f"list_era{era}.tsv.gz", list_rows, cols)
    ncols = sorted({k for r in night_rows for k in r}, key=lambda k: (k not in ("scan_date", "E", "pool", "listable", "rs_ge98",
                                                                                 "rank_only_rs_ge98", "evaluated", "passing",
                                                                                 "etv_would_list", "qqq_phase"), k))
    write_tsv(out_dir / f"nights_era{era}.tsv", night_rows, ncols)
    summary = {"era": era, "nights": len(nights), "first_D": cal[nights[0]].isoformat(), "last_D": cal[nights[-1]].isoformat(),
               "list_rows": len(list_rows), "names_per_night": len(list_rows) / max(1, len(nights)),
               "nights_with_names": sum(1 for r in night_rows if r["passing"]),
               "etv_would_list_total": sum(r["etv_would_list"] for r in night_rows),
               "gate_fails_among_rs_ge98_listable": dict(gate_fails_all),
               "mean_pool": float(np.mean([r["pool"] for r in night_rows])),
               "mean_listable": float(np.mean([r["listable"] for r in night_rows])),
               "store_notes": S.notes, "calendar": f"{cal[0]}..{cal[-1]} ({len(cal)} sessions)"}
    (out_dir / f"population_era{era}.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str), flush=True)
    return summary


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Minute stores + the request file
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def minute_index() -> list:
    """[(dir, done pairs {(date, ticker): status}, {date: file})] in precedence order, over the dirs that exist."""
    out = []
    for d in MINUTE_DIRS:
        if not d.is_dir():
            continue
        done = runner.load_done_pairs(d) or {}
        seal = SEAL.isoformat()
        done = {k: v for k, v in done.items() if k[0] < seal}           # a logged 2025+ pair is never read
        files = runner.minute_date_files(d)
        files = {k: v for k, v in files.items() if date.fromisoformat(k) < SEAL}
        out.append((d, done, files))
    return out


FETCHED_STATUSES = ("ok", "empty")           # a logged 'empty' (no bars that session) is a known fact, not a missing pull


def held_in(index: list, e_iso: str, ticker: str) -> Optional[Path]:
    """The first store that logged (E, ticker) as fetched ('ok' or 'empty') AND has E's file. An 'empty' pair walks
    as the data abstain `minutes_no_rows` (`runner.minutes_for`'s reading)."""
    for d, done, files in index:
        if done.get((e_iso, ticker)) in FETCHED_STATUSES and e_iso in files:
            return d
    return None


def read_tsv_rows(path: Path) -> list:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def read_list(out_dir: Path) -> list:
    rows = []
    for era in ("A", "B"):
        p = out_dir / f"list_era{era}.tsv.gz"
        if p.exists():
            rows.extend(read_tsv_rows(p))
    for r in rows:
        for k in ("level", "vol_bar", "adr20", "rs_best", "close", "raw_factor_D", "prior_move", "base_low"):
            r[k] = None if r.get(k) in ("", None) else float(r[k])
        r["list_rank"] = int(r["list_rank"])
    rows.sort(key=lambda r: (r["E"], r["list_rank"], r["ticker"]))
    return rows


FAILED_NAME = "_failed.psv"                  # the fetcher's `date|ticker|error` log of pairs it could not get


def load_failed_pairs(minutes_dir: Path) -> set:
    p = Path(minutes_dir) / FAILED_NAME
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text().splitlines():
        f = line.split("|")
        if len(f) >= 2:
            out.add((f[0], f[1]))
    return out


def read_request(path: Path = REQUEST) -> list:
    if not path.exists():
        return []
    return list(csv.DictReader(path.open(), delimiter="\t"))


def coverage(index: list, request: list, failed: Optional[set] = None) -> dict:
    """The pull's coverage of the PINNED request (registration §7-8): every requested (ticker, session) must be HELD
    (logged ok / empty in a store that has the day's file) or UNFETCHABLE (in the pull directory's `_failed.psv`: the
    vendor had no bars — a counted data abstain, `minutes_unfetchable`, never traded, holding no slot); anything else
    is MISSING and the walk refuses. -> {"held", "unfetchable", "missing", "missing_rows": [...], "unfetchable_pairs"}."""
    failed = load_failed_pairs(NEW_MINUTE_DIR) if failed is None else failed
    held = unf = 0
    missing, unf_pairs = [], set()
    for r in request:
        key = (r["session_date"], r["ticker"])
        if held_in(index, r["session_date"], r["ticker"]) is not None:
            held += 1
        elif key in failed:
            unf += 1
            unf_pairs.add(key)
        else:
            missing.append(r)
    return {"rows": len(request), "held": held, "unfetchable": unf, "missing": len(missing), "missing_rows": missing,
            "unfetchable_pairs": unf_pairs}


def coverage_problems(cov: dict, n_request: int) -> list:
    out = []
    if cov["missing"]:
        ex = ", ".join(f"{r['ticker']} {r['session_date']}" for r in cov["missing_rows"][:5])
        out.append(f"{cov['missing']:,} requested minute session(s) neither held nor logged unfetchable (e.g. {ex})")
    if n_request and cov["unfetchable"] > UNFETCHABLE_MAX * n_request:
        out.append(f"{cov['unfetchable']:,} unfetchable sessions > {UNFETCHABLE_MAX:.0%} of the request ({n_request:,}): a partial pull")
    return out


def run_coverage(out_dir: Path) -> dict:
    """The main loop's check after the pull: the pinned request against the stores (+ the raw-close pull)."""
    req = read_request()
    cov = coverage(minute_index(), req)
    raw, meta = load_raw_pull()
    raw_req = read_request(RAW_REQUEST)
    raw_missing = [r for r in raw_req if not any((r["ticker"], d) in raw for d in (r["first_date"], r["last_date"]))]
    summary = {"request_rows": cov["rows"], "held": cov["held"], "unfetchable": cov["unfetchable"], "missing": cov["missing"],
               "problems": coverage_problems(cov, len(req)),
               "raw_pull_rows": len(raw), "raw_request_tickers": len(raw_req),
               "raw_tickers_without_a_row_at_first_or_last_date": len(raw_missing),
               "raw_pull_present": RAW_PULL.exists(), "raw_meta": meta}
    if not RAW_PULL.exists() and raw_req:
        summary["problems"].append(f"raw-close pull missing: {RAW_PULL} ({len(raw_req)} tickers requested)")
    print(json.dumps(summary, indent=1, default=str), flush=True)
    return summary


def run_request(out_dir: Path) -> dict:
    if REQUEST.exists():
        raise SystemExit(f"REFUSED — {REQUEST} exists: the request is written once and pinned; delete it on purpose to rewrite")
    rows = read_list(out_dir)
    if not rows:
        raise SystemExit("no list rows: run `population A` and `population B` first")
    # daily high on E per store (for the `why` column): read the two stores' E bars for the list's (E, ticker) pairs
    need = defaultdict(set)
    for r in rows:
        need[r["era_store"]].add((r["ticker"], r["E"]))
    high_e, vol_e = {}, {}
    for era, pairs in need.items():
        S = load_store(era)
        D = S.D
        pos = {d.isoformat(): i for i, d in enumerate(D.cal)}
        for t, e in pairs:
            k = D.tid.get(t)
            if k is None or e not in pos:
                continue
            a, b = int(D.start[k]), int(D.stop[k])
            ci = pos[e]
            j = np.searchsorted(D.ci[a:b], ci)
            if j < b - a and D.ci[a + j] == ci:
                high_e[(t, e)] = float(D.h[a + j])
                vol_e[(t, e)] = float(D.v[a + j])
        del S
    index = minute_index()
    req, cov = [], Counter()
    for r in rows:
        key = (r["ticker"], r["E"])
        if key not in high_e:
            cov["no_daily_bar_E"] += 1
            r["minutes"] = "no_daily_bar_E"
            continue
        why = "fill_possible" if high_e[key] > r["level"] * (1.0 - MISMATCH_MAX) else "cap_occupancy_only"
        fired = bv.breakout_triggered({"h": high_e[key], "v": vol_e[key]}, {"ok": True, "level": r["level"], "vol_bar": r["vol_bar"]})
        r["fired"] = int(fired["fired"])
        r["level_pass"] = int(fired["level_pass"])
        cov["fired_E"] += int(fired["fired"])
        cov["level_cleared_E"] += int(fired["level_pass"])
        src = held_in(index, r["E"], r["ticker"])
        if src is not None:
            cov[f"held_{why}"] += 1
            r["minutes"] = f"held:{src.name}"
        else:
            cov[f"missing_{why}"] += 1
            r["minutes"] = "missing"
            req.append({"ticker": r["ticker"], "session_date": r["E"], "why": why})
    req.sort(key=lambda x: (x["session_date"], x["ticker"]))
    for x in req:
        assert_sealed(date.fromisoformat(x["session_date"]), "requested minute session")
    with open(REQUEST, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["ticker", "session_date", "why"])
        for x in req:
            w.writerow([x["ticker"], x["session_date"], x["why"]])
    # the raw-close request (review MEDIUM 5, 2026-11-01): the era-B list tickers whose raw price scale rests on the
    # split list <= 2024-12-31 alone (raw_src 2) — a 2025-26 splitter among them is mis-scaled. The main loop pulls
    # their UNADJUSTED daily closes over the span of their list rows (dates < SEAL only); the walk re-judges the $2
    # floor and the cost cents on those rows from the pulled closes (the list itself stays pinned).
    span: dict = {}
    for r in rows:
        if int(r.get("raw_src") or 0) == 2:
            t = r["ticker"]
            s = span.setdefault(t, [r["scan_date"], r["scan_date"], 0])
            s[0] = min(s[0], r["scan_date"]); s[1] = max(s[1], r["scan_date"]); s[2] += 1
    with open(RAW_REQUEST, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["ticker", "first_date", "last_date", "n_list_rows"])
        for t in sorted(span):
            w.writerow([t, span[t][0], span[t][1], span[t][2]])
    nights = len({r["E"] for r in rows})
    summary = {"list_rows": len(rows), "nights": nights, "names_per_night": len(rows) / nights,
               "fires_per_night": cov["fired_E"] / nights, "level_cleared_per_night": cov["level_cleared_E"] / nights,
               "fires_held": sum(1 for r in rows if r.get("fired") and str(r["minutes"]).startswith("held")),
               "fires_missing": sum(1 for r in rows if r.get("fired") and r["minutes"] == "missing"),
               "coverage": dict(cov), "request_rows": len(req),
               "request_fill_possible": sum(1 for x in req if x["why"] == "fill_possible"),
               "request_cap_occupancy_only": sum(1 for x in req if x["why"] == "cap_occupancy_only"),
               "request_sessions": len({x["session_date"] for x in req}),
               "raw_close_request_tickers": len(span), "raw_close_request_list_rows": sum(s[2] for s in span.values()),
               "stores": [str(d) for d, _, _ in index]}
    (out_dir / "request_summary.json").write_text(json.dumps(summary, indent=1))
    write_tsv(out_dir / "list_coverage.tsv", rows, ["scan_date", "E", "ticker", "list_rank", "level", "minutes", "level_pass", "fired"])
    print(json.dumps(summary, indent=1), flush=True)
    return summary


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The entry on the next session's minute bars (the live tick, minute by minute)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _live_source(path: Path, name: str):
    """ast-extract ONE function's source from a live module and exec it in a bare namespace (used for
    `order_manager.stop_limit_buy_price`, whose module imports the broker stack). Pinned by the module's sha."""
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            ns: dict = {}
            exec(ast.get_source_segment(path.read_text(), node), {"__builtins__": __builtins__}, ns)
            return ns[name]
    raise KeyError(f"{name} not in {path}")


ORDER_MANAGER = REPO / "agents" / "market_intelligence" / "broker" / "order_manager.py"
stop_limit_buy_price = _live_source(ORDER_MANAGER, "stop_limit_buy_price")
CHASE_CAP = 1.5                              # order_manager.CHASE_RISK_INFLATION_CAP's default (the env override is not read)
FALLBACK_X = 1.002                           # the #500 fallback limit: latest trade x 1.002


def minutes_to_dict(mb: "cb.MinuteBars") -> dict:
    """{minute: {open, high, low, close, volume}} — the shape `breakout_v1_entry.evaluate` reads."""
    return {int(m): {"open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)}
            for m, o, h, l, c, v in zip(mb.minute, mb.o, mb.h, mb.l, mb.c, mb.v)}


def simulate_entry(mins_all: dict, *, list_level: float, adr20: Optional[float], vol_bar: float) -> dict:
    """The breakout day of ONE list name, tick by tick (09:35 .. 15:55, `bve.FIRST_MINUTE .. bve.EOD_MINUTE`), on the
    session's minute bars `mins_all` = {minute: {open, high, low, close, volume}}. Each tick at minute m reads the bars
    through m-1 (`bve.evaluate`), decides (place / hold / cancel / re-price / the stop at the fill), then bar m prints
    and a resting order is checked for a fill. Returns the trace: {outcome, reason, placed_m, order, fill, fill_minute,
    placed_stop, stop, stop_check, sold_after_fill_px, cancel_m, holds}.

    outcome: 'filled' | 'sold_after_fill' (the true low too wide: the whole position sold at the next minute's open)
           | 'cancelled' (reason) | 'abstain' (reason) | 'never_placed'.
    Broker mechanics re-implemented (registration §4): a stop-limit buy at `level` (limit `stop_limit_buy_price`)
    triggers in the first bar m' >= the placement tick whose high >= level and fills at level when that bar opened at or
    under it, at the open when it opened between the level and the limit, at the limit when the bar's low came back to
    it, else rests as a limit at `limit` for a later bar; the #500 fallback (the last completed bar's close > level)
    is a limit at round(close x 1.002, 2) inside the 1.5x chase cap, filled at the open when the bar opens at or under
    it, else at the limit when the low reaches it; a cancel + re-place is instantaneous (no race); the fill minute's
    own low after the fill is not read (cb's day-0 convention); the stop at the fill (`stop_at_fill_decision`) is
    applied at the start of minute fm + 1 on the true low through fm."""
    tr: dict = {"outcome": None, "reason": None, "placed_m": None, "order": None, "fill": None, "fill_minute": None,
                "placed_stop": None, "stop": None, "stop_check": None, "sold_after_fill_px": None, "cancel_m": None,
                "holds": 0, "reprices": 0, "level": None, "orh5": None, "orl5": None, "fill_bar_low": None,
                "adverse_stop": False}
    order = None            # {"kind": "stop_limit"|"limit", "level", "limit", "stop", "triggered": bool}
    position = None
    mins: dict = {}
    for m in range(bve.FIRST_MINUTE, bve.EOD_MINUTE + 1):
        last_completed = m - 1
        for k in (range(0, last_completed + 1) if m == bve.FIRST_MINUTE else (last_completed,)):
            if k in mins_all:
                mins[k] = mins_all[k]                            # the bars through the last COMPLETED minute only
        if position is not None:
            if m == position["fill_minute"] + 1:
                # HIS RULING (1): one minute after the fill, the TRUE low through the fill minute
                true_low = min(float(b["low"]) for mm, b in mins_all.items() if mm <= position["fill_minute"])
                dec = bve.stop_at_fill_decision(fill=position["fill"], true_low=true_low, adr20=adr20,
                                                placed_stop=position["placed_stop"])
                tr["stop_check"] = dec
                if dec["action"] == "sell_all":
                    later = sorted(mm for mm in mins_all if mm >= m)
                    px = float(mins_all[later[0]]["open"]) if later else float(mins_all[max(mins_all)]["close"])
                    tr.update(outcome="sold_after_fill", reason=dec["reason"], sold_after_fill_px=px, stop=position["placed_stop"])
                    return tr
                if dec["action"] == "lower":
                    position["stop"] = float(dec["new_stop"])
                tr["stop"] = position["stop"]
                return tr
            continue
        st = bve.evaluate(mins, list_level=float(list_level), adr20=adr20, vol_bar=float(vol_bar), last_completed=last_completed)
        if order is None:
            if m >= bve.EOD_MINUTE:
                tr.update(outcome="never_placed", reason="window:never_placed")
                return tr
            if st["status"] == "wait":
                continue
            if st["status"] == "abstain":
                tr.update(outcome="abstain", reason=st["reason"])
                return tr
            if not st["f1_ok"]:
                tr["holds"] += 1
                continue
            level, stop = float(st["level"]), float(st["stop"])
            tr.update(level=level, orh5=st["orh5"], orl5=st["orl5"])
            latest = float(mins[max(mins)]["close"])
            if latest > level:                                   # #500: the trigger is already in the money
                lim = round(latest * FALLBACK_X, 2)
                width = (lim - stop) / lim
                if adr20 is None or width > float(adr20):
                    tr.update(outcome="abstain", reason=f"setup:stop_too_wide: fallback fill ${lim:.2f} - stop ${stop:.2f} = {width:.2%} > ADR20")
                    return tr
                if (lim - stop) > CHASE_CAP * (level - stop):
                    tr.update(outcome="abstain", reason=f"setup:chase_cap_exceeded: limit ${lim:.2f} risk > {CHASE_CAP}x planned")
                    return tr
                order = {"kind": "limit", "level": level, "limit": lim, "stop": stop, "triggered": True}
            else:
                order = {"kind": "stop_limit", "level": level, "limit": float(stop_limit_buy_price(level)), "stop": stop,
                         "triggered": False}
            tr.update(placed_m=m, order=dict(order))
        else:
            reason = bve._terminal_reason(st, m)
            if reason is not None:
                tr.update(outcome="cancelled", reason=reason, cancel_m=m)
                return tr
            if st["status"] == "ok" and float(st["stop"]) < order["stop"] - bve.STOP_EPS:
                order["stop"] = float(st["stop"])             # the re-price: cancel + place at the new day low
                tr["reprices"] += 1
        # bar m prints: is the resting order filled?
        bar = mins_all.get(m)
        if bar is None:
            continue
        o, h, l = float(bar["open"]), float(bar["high"]), float(bar["low"])
        fill = None
        if order["kind"] == "stop_limit" and not order["triggered"]:
            if h >= order["level"]:
                order["triggered"] = True
                if o <= order["level"]:
                    fill = order["level"]
                elif o <= order["limit"]:
                    fill = o
                elif l <= order["limit"]:
                    fill = order["limit"]
        else:                                                    # a resting limit (the fallback, or a triggered stop-limit)
            if o <= order["limit"]:
                fill = o
            elif l <= order["limit"]:
                fill = order["limit"]
        if fill is not None:
            position = {"fill": float(fill), "fill_minute": m, "placed_stop": order["stop"], "stop": order["stop"]}
            # the fill bar's own low: when it is under the placed stop, live's OTO stop (active from the fill) may have
            # fired inside this minute — the ADVERSE-ORDERING row books that (registration §4; review HIGH 4)
            tr.update(outcome="filled", fill=float(fill), fill_minute=m, placed_stop=order["stop"], stop=order["stop"],
                      fill_bar_low=l, adverse_stop=bool(l < order["stop"]))
    if position is not None:                                     # filled in the 15:55 minute: no tick after it (disclosed live)
        tr["stop_check"] = {"action": "unchecked_eod", "reason": "filled in the last minute: the live job pages, the stop stands"}
        return tr
    if order is not None:
        tr.update(outcome="cancelled", reason=f"{bve.WINDOW_BREAKOUT_UNFILLED_EOD}: unfilled at 15:55 ET", cancel_m=bve.EOD_MINUTE)
        return tr
    tr.update(outcome="never_placed", reason="window:never_placed")
    return tr


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The exit: the live decisions on daily bars, asserted equal to the definition (walk_pp)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def step_pp(*, fill: float, stop: float, day0: dict, closes_before, fwd: "cb.DailyBars", adr20: float,
            horizon: int = HORIZON) -> dict:
    """The paper lane's pp exit, session by session from E+1, calling the LIVE decision functions
    (`breakout_pp_rules`): the broker's stop leg (rule 1), the +2R third at the target / at the open (the 5-minute poll's
    touch, read as a fill), `session3_decision` at the session-3 close (cut / third), `trail_decision` on every settled
    close (the rest at the next open), `stop_after_third` from the next session. `day0` = `ppr.day0_facts` of the
    breakout day. Returns `walk_pp`'s shape so the two can be compared event for event."""
    risk = fill - stop
    if not risk > 0:
        raise ValueError("step_pp: stop must be below the fill")
    adr20 = cb._check_adr(adr20)
    o, h, l, c = fwd.o, fwd.h, fwd.l, fwd.c
    n = len(c)
    events: list = []
    pnl = 0.0
    remaining = 1.0
    frac = ppr.PARTIAL_FRAC
    target = ppr.target_price(fill, stop)
    stop_now = stop
    partial_taken = False
    fwd_dicts: list = []
    cb_list = [float(x) for x in closes_before]

    def after_third(j: int, close_j: float) -> None:
        nonlocal stop_now
        stop_now = ppr.stop_after_third(stop_now, fill)
        events.append((j, "stop_to", stop_now, 0.0))
        if stop_now > close_j:
            events.append((j, "be_above_close", close_j, 0.0))

    if day0.get("partial_price") is not None:                    # the day-0 third (the minutes after the fill)
        px = float(day0["partial_price"])
        events.append((0, "partial_r", px, frac))
        pnl += (px - fill) * frac
        remaining -= frac
        partial_taken = True
        after_third(0, cb_list[-1])
    for j in range(1, min(int(horizon), n) + 1):
        oj, hj, lj, cj = float(o[j - 1]), float(h[j - 1]), float(l[j - 1]), float(c[j - 1])
        fwd_dicts.append({"o": oj, "h": hj, "l": lj, "c": cj})
        stop_j = stop_now
        gap_px = oj if (not partial_taken and oj >= target) else None
        if oj <= stop_j or lj <= stop_j:                         # 1. the broker's stop leg (a gap-open third first)
            if gap_px is not None:
                events.append((j, "partial_r", gap_px, frac))
                pnl += (gap_px - fill) * frac
                remaining -= frac
            px = oj if oj <= stop_j else stop_j
            events.append((j, "stop_gap" if oj < stop_j else "stop", px, remaining))
            pnl += (px - fill) * remaining
            return cb._outcome("stopped", pnl, risk, fill, adr20, j, events)
        if gap_px is not None or (not partial_taken and hj >= target):     # 1b. the +2R third (the poll's touch)
            px = gap_px if gap_px is not None else target
            events.append((j, "partial_r", px, frac))
            pnl += (px - fill) * frac
            remaining -= frac
            partial_taken = True
            after_third(j, cj)
        if j == ppr.LEG_SESSION:                                 # 2. 15:45 on session 3 (modelled at the close)
            dec = ppr.session3_decision(fill=fill, stop=stop, day0=day0, fwd=fwd_dicts, partial_taken=partial_taken)
            if dec == "cut":
                events.append((j, "cut", cj, remaining))
                pnl += (cj - fill) * remaining
                return cb._outcome("time_exit", pnl, risk, fill, adr20, j, events)
            if dec in ("session_third", ppr.CANCEL_RESTING_THIRD):
                events.append((j, "partial", cj, frac))
                pnl += (cj - fill) * frac
                remaining -= frac
                partial_taken = True
                after_third(j, cj)
        elif j > ppr.LEG_SESSION:
            assert ppr.retry_decision(fwd=fwd_dicts, partial_taken=partial_taken, session_third_due=False) is None
        td = ppr.trail_decision(closes_before=cb_list, fwd=fwd_dicts, partial_taken=partial_taken)   # 3. 16:45
        if td["sell"] and j < n:
            opx = float(o[j])
            events.append((j + 1, "trail", opx, remaining))
            pnl += (opx - fill) * remaining
            return cb._outcome("censored" if j == int(horizon) else "trailed", pnl, risk, fill, adr20, j + 1, events)
        if j == int(horizon):
            events.append((j, "mark", cj, remaining))
            pnl += (cj - fill) * remaining
            return cb._outcome("censored", pnl, risk, fill, adr20, j, events)
    return cb._degraded(c, n, remaining, pnl, fill, risk, adr20, events, cb_list[-1] if cb_list else None)


def walk_definition(*, fill: float, stop: float, day0: dict, closes_before, fwd: "cb.DailyBars", adr20: float,
                    horizon: int = HORIZON) -> dict:
    """The DEFINITION: `consolidation_breakout_pp.walk_pp_arms` on the `pp` arm (a day-0 stop-out booked by
    `cb.day0_target_to_outcome`)."""
    return cpp.walk_pp_arms({"fill": fill, "stop": stop}, day0, closes_before=closes_before, fwd=fwd, adr20=adr20,
                            horizon=horizon, arms=(cpp.PP_ARM,))[cpp.PP_ARM]


def events_equal(a: list, b: list, tol: float = 1e-9) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x[0] != y[0] or x[1] != y[1] or abs(float(x[2]) - float(y[2])) > tol or abs(float(x[3]) - float(y[3])) > tol:
            return False
    return True


def exit_one(*, fill: float, stop: float, day0: dict, closes_before, fwd: "cb.DailyBars", adr20: float,
             horizon: int = HORIZON) -> dict:
    """The stepper's result, asserted equal to the definition event for event (a mismatch raises: the stepper drifted)."""
    if day0.get("stopped"):
        res = cb.day0_target_to_outcome({"fill": fill, "stop": stop}, day0, adr20, ppr.PARTIAL_FRAC)
        if day0.get("partial_price") is not None:
            res["events"] = res["events"][:1] + [(0, "stop_to", float(day0["stop_in_force"]), 0.0)] + res["events"][1:]
    else:
        res = step_pp(fill=fill, stop=stop, day0=day0, closes_before=closes_before, fwd=fwd, adr20=adr20, horizon=horizon)
    ref = walk_definition(fill=fill, stop=stop, day0=day0, closes_before=closes_before, fwd=fwd, adr20=adr20, horizon=horizon)
    if res["status"] != ref["status"] or not events_equal(res["events"], ref["events"]) \
            or abs(float(res["realized_r"]) - float(ref["realized_r"])) > 1e-9:
        raise AssertionError(f"stepper != walk_pp: {res['status']} {res['events']} vs {ref['status']} {ref['events']}")
    return res


def r_at_cost(events: list, fill: float, stop: float, cost: float) -> float:
    """Realized R with `cost` (adjusted-scale dollars per share) paid on the entry and on every exit leg; the
    denominator is the sized risk fill - stop (no cost)."""
    pnl = 0.0
    for _j, kind, px, frac in events:
        if frac > 0 and kind not in ("stop_to", "be_above_close"):
            pnl += (float(px) - cost - (fill + cost)) * float(frac)
    return pnl / (fill - stop)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The PAPER BOOK: one chronological event loop over every placed name-day (guard, cap, the lane's safeguards)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
BLOCK_TICKER = "block:ticker_open_position"
BLOCK_CAP = "block:max_positions"
BLOCK_DAILY = "block:daily_loss"
BLOCK_BREAKER = "block:circuit_breaker"
DAILY_BAR_MINUTE = -1            # a leg booked on a DAILY bar has no minute: it is read as realized at the day's open (pessimistic)


def risk_fraction(fill: float, stop: float) -> float:
    """The share of equity a trade risks under the lane's sizing (`breakout_v1_entry.size_breakout`): 2% of equity, cut
    by the 20% notional cap -> min(RISK_FRAC, NOTIONAL_CAP x (fill - stop) / fill). Whole shares and the regime
    multiplier are not modelled (declared)."""
    return float(min(RISK_FRAC, NOTIONAL_CAP * (float(fill) - float(stop)) / float(fill)))


def _t(d: str, m) -> tuple:
    """An order key for events: (date, minute); a daily-bar leg sorts before every tick of its day."""
    return (d, DAILY_BAR_MINUTE if m is None else int(m))


def apply_book(trades: list, *, slots: Optional[int], safeguards: bool, sessions: Optional[list] = None) -> dict:
    """ONE chronological pass over every list name-day that PLACED an order in the walk (admissions cascade: a
    blocked name holds nothing, so a later name may take its place), in the LIVE tick's order — day, then minute,
    then list rank. Each trade carries: key, E, ticker, list_rank, placed_m, cancel_m (None if filled), filled,
    free_date (the session its last share leaves: a mature exit's date; a degraded walk's last forward bar; a
    censored walk's mark session; E for a day-0 exit / a sale after the fill), free_minute (the day-0 / after-fill
    exit minute; None = the end of free_date), exit_at_open (a trail sale at free_date's open: freed before the first
    tick), legs [(date, minute | None, kind, r_leg)] at the primary cost, f_risk, total_r.

    At a placement (m, rank) on day d:
      1. the TICKER GUARD (`entry_pipeline` step 1b): an admitted FILLED position of the same ticker from an earlier
         day still holding shares at this tick -> BLOCK_TICKER (a position whose last share left before this tick
         does not block; one with 2/3 left does);
      2. the CAP (`slots`): held = carried positions not yet freed + today's admitted orders not yet cancelled
         (`OPEN_POSITION_STATUSES` = filled, order_placed, confirmed). A cancel at (m, r') frees the slot only for
         placements at m with rank > r' (the tick processes names in list order); a day-0 exit at minute x frees
         it for placements at minutes > x -> BLOCK_CAP;
      3. the lane's SAFEGUARDS (`live_tracker._check_safeguards`, `safeguards=True`): the DAILY-LOSS limit — the
         P&L realized today by each admitted trade (its legs dated d, netted per trade: a close day nets the
         trade's earlier legs out, ruling (iv); a losing partial on an open trade counts at once, ruling (1)),
         weighted by the trade's risk fraction, losses summed; a daily-bar leg counts from the day's first tick
         (pessimistic), a minute-timed leg from its minute; trip at <= -DAILY_LOSS of a constant equity 1.0 ->
         BLOCK_DAILY. The CIRCUIT BREAKER — the last BREAKER_N outcomes before this tick (closed trades' totals at
         their close time; the partial legs of trades still open at this tick, each at its own time; a partial
         profit is a win) all <= 0 -> blocked until one calendar day after the latest loss's time; a daily-bar loss
         (no time) blocks the rest of its session and the whole next session -> BLOCK_BREAKER.
    `sessions` = every session of the walk in order (the next session after a daily-bar loss is read from it; a day
    with no placement is still a session); default: the days that placed an order.
    Returns {"admitted": {key: bool}, "reason": {key: str | None}, "blocked": Counter}."""
    import bisect
    by_day: dict = defaultdict(list)
    for t in trades:
        by_day[t["E"]].append(t)
    days = sorted(by_day)
    all_days = sorted(set(sessions or []) | set(days))
    next_session = {d: (all_days[i + 1] if i + 1 < len(all_days) else None) for i, d in enumerate(all_days)}
    positions: list = []             # admitted filled positions: {ticker, free_date, free_minute, at_open}
    ev_times: list = []              # the safeguards' outcome events, sorted by time: parallel lists
    ev_vals: list = []
    ev_kind: list = []               # 'close' | 'partial'
    ev_key: list = []
    close_time: dict = {}            # trade key -> its close time key
    legs_by_day: dict = defaultdict(list)   # day -> [(time, key, r_leg x f)]
    admitted, reason, blocked = {}, {}, Counter()

    def held_at(p: dict, d: str, m: int) -> bool:
        return p["free_date"] > d or p["free_minute"] is None or p["free_minute"] >= m

    for d in days:
        positions = [p for p in positions if p["free_date"] > d or (p["free_date"] == d and not p["at_open"])]
        today_sorted = sorted(by_day[d], key=lambda t: (int(t["placed_m"]), int(t["list_rank"])))
        resting: list = []           # today's admitted orders: {cancel_m (None if filled), rank, pos (if filled)}
        new_pos: list = []           # today's fills join `positions` when the day ends (they are counted via `resting` today)
        for t in today_sorted:
            m, rank = int(t["placed_m"]), int(t["list_rank"])
            now = (d, m)
            why = None
            # 1. the ticker guard
            for p in positions:
                if p["ticker"] == t["ticker"] and held_at(p, d, m):
                    why = BLOCK_TICKER
                    break
            # 2. the cap
            if why is None and slots is not None:
                carried = sum(1 for p in positions if held_at(p, d, m))
                live_today = 0
                for r in resting:
                    if r["cancel_m"] is not None:
                        if r["cancel_m"] > m or (r["cancel_m"] == m and r["rank"] > rank):
                            live_today += 1
                    elif r["pos"] is not None:
                        if held_at(r["pos"], d, m):
                            live_today += 1
                    else:
                        live_today += 1
                if carried + live_today >= slots:
                    why = BLOCK_CAP
            # 3. the lane's safeguards
            if why is None and safeguards:
                per_trade: dict = defaultdict(float)
                for tm, k, v in legs_by_day.get(d, ()):
                    if tm < now:
                        per_trade[k] += v
                if sum(v for v in per_trade.values() if v < 0) <= -DAILY_LOSS:
                    why = BLOCK_DAILY
                else:
                    last = []
                    i = bisect.bisect_left(ev_times, now)
                    while i > 0 and len(last) < BREAKER_N:
                        i -= 1
                        if ev_kind[i] == "partial" and close_time[ev_key[i]] < now:
                            continue                     # its trade has closed: the total counts instead
                        last.append((ev_times[i], ev_vals[i]))
                    if len(last) >= BREAKER_N and all(v <= 0 for _tk, v in last):
                        ld, lm = last[0][0]
                        if lm == DAILY_BAR_MINUTE:
                            if d == ld or d == next_session.get(ld):
                                why = BLOCK_BREAKER
                        else:
                            cool = (date.fromisoformat(ld) + timedelta(days=1)).isoformat()
                            if (d == ld and m > lm) or (ld < d < cool) or (d == cool and m <= lm):
                                why = BLOCK_BREAKER
            if why is not None:
                admitted[t["key"]] = False
                reason[t["key"]] = why
                blocked[why] += 1
                continue
            admitted[t["key"]] = True
            reason[t["key"]] = None
            pos = None
            if t["filled"]:
                pos = {"ticker": t["ticker"], "free_date": t["free_date"] or d, "free_minute": t.get("free_minute"),
                       "at_open": bool(t.get("exit_at_open"))}
                new_pos.append(pos)
                if safeguards:
                    f = float(t["f_risk"])
                    ct = _t(pos["free_date"], pos["free_minute"])
                    close_time[t["key"]] = ct
                    j = bisect.bisect_right(ev_times, ct)
                    ev_times.insert(j, ct); ev_vals.insert(j, float(t["total_r"]) * f); ev_kind.insert(j, "close"); ev_key.insert(j, t["key"])
                    for ld, lm, kind, r_leg in t["legs"]:
                        tm = _t(ld, lm)
                        if kind != "mark":                   # a mark is not realized money (an open mark's slot still frees)
                            legs_by_day[ld].append((tm, t["key"], float(r_leg) * f))
                        if kind in ("partial_r", "partial") and tm < ct:
                            j = bisect.bisect_right(ev_times, tm)
                            ev_times.insert(j, tm); ev_vals.insert(j, float(r_leg) * f); ev_kind.insert(j, "partial"); ev_key.insert(j, t["key"])
            resting.append({"cancel_m": t["cancel_m"] if not t["filled"] else None, "rank": rank, "pos": pos})
        positions = [p for p in positions + new_pos if p["free_date"] > d]
    return {"admitted": admitted, "reason": reason, "blocked": blocked}


def apply_cap(trades: list, slots: int = CAP_SLOTS) -> dict:
    """The cap alone (no ticker guard, no safeguards) — kept for the dry run's hand-computed cap cases; the walk uses
    `apply_book`. The ticker guard is OFF here only because these cases carry distinct tickers."""
    for t in trades:
        t.setdefault("ticker", t["key"])
        t.setdefault("free_date", t.get("exit_date"))
        t.setdefault("free_minute", None)
    res = apply_book(trades, slots=slots, safeguards=False)
    return {"admitted": res["admitted"], "blocked": sum(res["blocked"].values())}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Measures, the bar, the report
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def stats(r: np.ndarray, months: list, key: str) -> dict:
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n == 0:
        return {"n": 0}
    lo, hi = runner.block_bootstrap_ci(r, months, key=key)
    return {"n": n, "mean_r": float(r.mean()), "ci_lo": lo, "ci_hi": hi, "median_r": float(np.median(r)),
            "win_rate": float((r > 0).mean()), "n_ge3": int((r >= 3).sum()), "share_ge3": float((r >= 3).mean()),
            "n_ge5": int((r >= 5).sum()), "share_ge5": float((r >= 5).mean()), "n_ge10": int((r >= 10).sum()),
            "share_ge10": float((r >= 10).mean()), "sum_r": float(r.sum()), "max_r": float(r.max()), "min_r": float(r.min()),
            "mean_ex_top5": float(np.sort(r)[:-5].mean()) if n > 5 else None}


def verdict(s: dict) -> tuple:
    """PASS / FAIL / CAN'T TELL on one group's stats (the bar, registration §6)."""
    if s.get("n", 0) < N_FLOOR:
        return "CAN'T TELL", f"n = {s.get('n', 0)} < {N_FLOOR}"
    tail = s["share_ge3"] >= TAIL_SHARE
    if s["ci_lo"] > 0 and tail:
        return "PASS", "interval lower end > 0 and the >= 3R share at or above the tail bar"
    if s["ci_hi"] < FAIL_MEAN_REF and not tail:
        return "FAIL", f"whole interval under +{FAIL_MEAN_REF}R and the >= 3R share under the tail bar"
    if tail and s["ci_lo"] <= 0:
        return "CAN'T TELL", "tail present, mean not shown positive: an entry / exit question, not selection"
    if not tail and s["ci_lo"] > 0:
        return "CAN'T TELL", "mean positive, tail thin: the big winners are not being found or held"
    return "CAN'T TELL", "interval spans the bar"


def reason_key(reason) -> str:
    """'setup:stop_too_wide: level ...' -> 'setup:stop_too_wide' (the skip-reason family and name, no numbers)."""
    if not reason:
        return ""
    parts = str(reason).split(":")
    if len(parts) < 2:
        return parts[0].strip()
    return parts[0].strip() + ":" + parts[1].strip().split(" ")[0]


CANT = "CAN'T TELL"


def fmt_stats(name: str, s: dict) -> str:
    if s.get("n", 0) == 0:
        return f"{name:34s} n 0"
    return (f"{name:34s} n {s['n']:5d}  mean {s['mean_r']:+.3f} [{s['ci_lo']:+.2f}, {s['ci_hi']:+.2f}]  win {s['win_rate']:5.1%}  "
            f"med {s['median_r']:+.2f}  >=3R {s['share_ge3']:5.1%} ({s['n_ge3']})  >=5R {s['share_ge5']:5.1%} ({s['n_ge5']})  "
            f">=10R {s['share_ge10']:5.1%} ({s['n_ge10']})  sum {s['sum_r']:+.0f}")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 8. Small I/O
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def write_tsv(path: Path, rows: list, cols: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "wt", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])


def sha(p: Path) -> str:
    return runner.sha256_file(p)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 9. Freeze: the pins the registration must carry — a CODE table in the body (pre-pull) + a footer (post-pull)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Whole-file pins: the RULE modules (a change there is a new registration) and this replay.
LIVE_PINS = {"breakout_v1.py": REPO / "agents/market_intelligence/breakout_v1.py",
             "consolidation_breakout.py": REPO / "agents/market_intelligence/consolidation_breakout.py",
             "consolidation_breakout_pp.py": REPO / "agents/market_intelligence/consolidation_breakout_pp.py",
             "breakout_pp_rules.py": REPO / "agents/market_intelligence/broker/breakout_pp_rules.py",
             "breakout_v1_volume_curve.py": REPO / "agents/market_intelligence/broker/breakout_v1_volume_curve.py",
             "etv_names_2026-10-28.tsv": ETV_NAMES,
             "v1_replay.py": Path(__file__).resolve()}
# Function-level pins: the modules edited often are pinned on the SOURCE SEGMENTS of exactly the functions and
# constants the replay calls OR re-implements — an edit elsewhere in those files does not refuse the run; an edit
# inside a pinned function does (the registration's §8 rule). Review MEDIUM 8 (2026-11-01) added the re-implemented
# ones: `scan_members` (copied as `night_members`), `submit_entry` (the #500 fallback + chase cap),
# `width_at_expected_fill` / `_manage` / `_replace` / `_enter` / `prepare_breakout_order` (the placement, the width at the
# expected fill, the re-price trigger), `submit_trade_entry` (the ticker guard) and `_check_safeguards` + its constants.
ENTRY_PIPELINE = REPO / "agents" / "market_intelligence" / "broker" / "entry_pipeline.py"
LIVE_TRACKER = REPO / "agents" / "market_intelligence" / "broker" / "live_tracker.py"
CONSTANTS = REPO / "agents" / "market_intelligence" / "constants.py"
FUNCTION_PINS = {
    "breakout_v1_entry.py (called functions)": (REPO / "agents/market_intelligence/broker/breakout_v1_entry.py",
        ("evaluate", "f1_permits", "stop_from_low", "_terminal_reason", "stop_at_fill_decision", "width_at_expected_fill",
         "prepare_breakout_order", "_enter", "_replace", "_manage", "size_breakout", "resize_for_new_stop",
         "N_SESSION_MINUTES", "OR_MINUTES", "FIRST_MINUTE", "EOD_MINUTE", "STOP_EPS")),
    "breakout_v1_list.py (called functions)": (REPO / "agents/market_intelligence/breakout_v1_list.py",
        ("scan_members", "evaluate_members", "rank_rows")),
    "order_manager.py (called functions)": (ORDER_MANAGER, ("stop_limit_buy_price", "CHASE_RISK_INFLATION_CAP", "submit_entry")),
    "entry_pipeline.py (called functions)": (ENTRY_PIPELINE, ("submit_trade_entry",)),
    "live_tracker.py (called functions)": (LIVE_TRACKER, ("_check_safeguards", "count_open_positions",
                                                           "_closed_losses_realized_on", "_partial_losses_realized_on")),
    "constants.py (called constants)": (CONSTANTS, ("MAX_CONCURRENT_LIVE_POSITIONS", "DAILY_LOSS_LIMIT_PCT",
                                                    "CIRCUIT_BREAKER_CONSEC_LOSSES", "CIRCUIT_BREAKER_COOLDOWN_DAYS",
                                                    "RISK_PCT", "MAX_POSITION_PCT")),
    "runner.py (called functions)": (REPO / "scripts/probes/_cb_backtest/runner.py",
        ("Daily", "load_daily", "bars_for", "load_raw_close", "load_breaks", "break_mask", "load_splits", "factor_by_bar",
         "gz_complete_members", "read_minute_file", "minute_bars_from_rows", "load_done_pairs", "minute_date_files",
         "minutes_for", "block_bootstrap_ci", "sha256_file", "doc_body_sha", "FREEZE_MARK", "BOOT_DRAWS", "BOOT_SEED")),
}


def function_source_sha(path: Path, names: tuple) -> str:
    """sha256 over the source segments of the named top-level functions / classes / constant assignments of `path`,
    in `names` order, each prefixed by its name. A name that is not found is a hard error (a renamed function is a
    change, never a silent pass)."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    found = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found[node.name] = ast.get_source_segment(text, node)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                for nm in ([tgt.id] if isinstance(tgt, ast.Name) else [e.id for e in getattr(tgt, "elts", []) if isinstance(e, ast.Name)]):
                    found[nm] = ast.get_source_segment(text, node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found[node.target.id] = ast.get_source_segment(text, node)
    h = hashlib.sha256()
    for nm in names:
        if nm not in found:
            raise KeyError(f"{path.name}: pinned name {nm!r} not found at top level")
        h.update(f"### {nm}\n{found[nm]}\n".encode("utf-8"))
    return h.hexdigest()


class _FunctionPin:
    """A pseudo-path for `hashes_of`: hashed through `function_source_sha`, never as a file."""

    def __init__(self, path: Path, names: tuple):
        self.path, self.names = path, names

    def sha(self) -> str:
        return function_source_sha(self.path, self.names)


class _SealedTree:
    """A minute store pinned over its DATA files named by a date < SEAL (and `_done.psv` / `_failed.psv`): a file dated
    2025-01-01 or later is neither opened nor hashed (review LOW, 2026-11-01)."""

    def __init__(self, root: Path):
        self.root = root

    def sha(self) -> str:
        h = hashlib.sha256()
        for p in sorted(self.root.rglob("*")):
            if not p.is_file():
                continue
            if p.name in ("_done.psv", FAILED_NAME):
                pass
            elif p.name.endswith(".psv.gz"):
                try:
                    if date.fromisoformat(p.name[:-len(".psv.gz")]) >= SEAL:
                        continue
                except ValueError:
                    continue
            else:
                continue
            h.update(f"{p.relative_to(self.root).as_posix()}\t{sha(p)}\n".encode())
        return h.hexdigest()


DATA_PINS = {"data/cb702_pre_v2/daily_closes_all.csv.gz": PRE / "daily_closes_all.csv.gz",
             "data/cb702_pre_v2/daily_raw_close.csv.gz": PRE / "daily_raw_close.csv.gz",
             "data/cb702_pre_v2/small_pulls.psv": PRE / "small_pulls.psv",
             "data/cb702_pre_v2/symbol_guard.tsv": PRE / "symbol_guard.tsv",
             "data/cb702/daily_closes_all.csv.gz": CB / "daily_closes_all.csv.gz",
             "data/cb702/cb702_splits.psv": CB / "cb702_splits.psv",
             "data/cb702/small_pulls.psv": CB / "small_pulls.psv"}
# Files tracked in this repo whose committed copy at `freeze_commit` must equal the disk copy (the proof that nothing
# changed once bars were on disk) — every repo-tracked body pin.
GIT_TRACKED_BODY = ("v1_replay.py", "minute_request.tsv", "raw_close_request.tsv", "dryrun.txt", "calibration.txt", "parity.txt",
                    "empirical_pp_c0_r.npy", "empirical_pp_c0_months.npy")


def body_pin_map(out_dir: Path) -> dict:
    """The PRE-PULL pins, written ABOVE the freeze marker: code, data, the lists, the night tables, the two request
    files, the dry run, the calibration, the parity check and the calibration anchors."""
    m = dict(LIVE_PINS)
    m.update({k: _FunctionPin(p, names) for k, (p, names) in FUNCTION_PINS.items()})
    m.update(DATA_PINS)
    for era in ("A", "B"):
        m[f"list_era{era}.tsv.gz"] = out_dir / f"list_era{era}.tsv.gz"
        m[f"nights_era{era}.tsv"] = out_dir / f"nights_era{era}.tsv"
    m["minute_request.tsv"] = REQUEST
    m["raw_close_request.tsv"] = RAW_REQUEST
    m["dryrun.txt"] = out_dir / "dryrun.txt"
    m["calibration.txt"] = out_dir / "calibration.txt"
    m["parity.txt"] = out_dir / "parity.txt"
    m["empirical_pp_c0_r.npy"] = HERE / "empirical_pp_c0_r.npy"
    m["empirical_pp_c0_months.npy"] = HERE / "empirical_pp_c0_months.npy"
    return m


def footer_pin_map() -> dict:
    """The POST-PULL pins, pasted BELOW the marker by the main loop: every minute store tree (sealed) including the
    pull's, the raw-close pull and its sidecar."""
    m = {}
    for d in MINUTE_DIRS:
        if d.is_dir():
            m[f"minutes ({d.parent.name}/{d.name}) (tree)"] = _SealedTree(d)
    m["raw_close_bv1_1101.csv.gz"] = RAW_PULL
    m["raw_close_bv1_1101.meta.json"] = RAW_PULL_META
    return m


def pin_map(out_dir: Path) -> dict:
    m = body_pin_map(out_dir)
    m.update(footer_pin_map())
    return m


def hashes_of(files: dict) -> dict:
    """{label: sha256 | None}: a file by `runner.sha256_file`, a function pin / sealed tree by its own `.sha()`."""
    got = {}
    for k, v in files.items():
        if isinstance(v, (_FunctionPin, _SealedTree)):
            got[k] = v.sha()
        else:
            p = Path(v)
            got[k] = sha(p) if p.is_file() else None
    return got


def pins(out_dir: Path, which: str = "body") -> list:
    """`pins body` -> the markdown table rows for the body (| key | sha256 |); `pins footer` -> the footer lines."""
    if which == "body":
        return [f"| {k} | `{h or 'MISSING'}` |" for k, h in hashes_of(body_pin_map(out_dir)).items()]
    lines = [f"- {k} sha256: `{h or 'MISSING'}`" for k, h in hashes_of(footer_pin_map()).items()]
    if DOC.is_file():
        lines.append(f"- doc_body = {runner.doc_body_sha(DOC.read_text(encoding='utf-8'))}")
    return lines


def _pin_in(text: str, k: str) -> Optional[str]:
    """The sha the text carries for pin `k`: a table row (| k | sha |) or a footer line (- k sha256: sha / - k = sha)."""
    m = re.search(rf"(?m)^\|\s*{re.escape(k)}\s*\|\s*`?([0-9a-f]{{64}})`?\s*\|", text)
    if m is None:
        m = re.search(rf"(?m)^\s*[-*]?\s*{re.escape(k)}\s+(?:sha256:|=)\s*`?([0-9a-f]{{64}})", text)
    return m.group(1) if m else None


def git_blob_sha256(commit: str, rel: str) -> Optional[str]:
    """sha256 of a repo-tracked file as committed at `commit` (local git, no network); None if absent."""
    try:
        out = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{rel}"], capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    return hashlib.sha256(out).hexdigest()


def freeze_problems(out_dir: Path) -> list:
    """The freeze (registration §8): the BODY pin table above the marker must match every artefact on disk; the FOOTER
    below it must carry `freeze_commit`, `doc_body` (the sha of every byte above the marker) and every post-pull pin;
    the committed copies at `freeze_commit` of the repo-tracked body pins and of this document's body must equal the
    disk copies. Missing marker / pin / file, any mismatch -> a problem each."""
    if not DOC.is_file():
        return [f"registration doc missing: {DOC}"]
    text = DOC.read_text(encoding="utf-8")
    if text.count(FREEZE_MARK) != 1:
        return [f"registration doc must carry the {FREEZE_MARK} marker exactly once (found {text.count(FREEZE_MARK)}): "
                f"the body is every byte before its FIRST occurrence"]
    body, footer = text.split(FREEZE_MARK, 1)
    problems = []
    body_map = body_pin_map(out_dir)
    got = hashes_of(body_map)
    for k, g in got.items():
        want = _pin_in(body, k)
        if want is None:
            problems.append(f"body carries no pin for {k}")
        elif g is None:
            problems.append(f"{k}: file missing")
        elif g != want:
            problems.append(f"{k} sha256 mismatch: body {want[:12]}... vs now {g[:12]}... - the frozen artefact was edited")
    got_f = hashes_of(footer_pin_map())
    got_f["doc_body"] = runner.doc_body_sha(text)
    for k, g in got_f.items():
        want = _pin_in(footer, k)
        if want is None:
            problems.append(f"footer carries no {k}")
        elif g is None:
            problems.append(f"{k}: file missing")
        elif g != want:
            problems.append(f"{k} sha256 mismatch: footer {want[:12]}... vs now {g[:12]}...")
    m = re.search(r"(?m)^\s*[-*]?\s*freeze_commit\s*=\s*([0-9a-f]{7,40})", footer)
    if m is None:
        problems.append("footer carries no freeze_commit")
    else:
        commit = m.group(1)
        for k in GIT_TRACKED_BODY:
            p = Path(body_map[k])
            rel = p.resolve().relative_to(REPO).as_posix()
            committed = git_blob_sha256(commit, rel)
            if committed is None:
                problems.append(f"{rel} is not in commit {commit[:10]}")
            elif got.get(k) != committed:
                problems.append(f"{rel}: the copy committed at {commit[:10]} differs from disk")
        doc_rel = DOC.resolve().relative_to(REPO).as_posix()
        try:
            committed_doc = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{doc_rel}"], capture_output=True,
                                           check=True).stdout.decode("utf-8")
            if runner.doc_body_sha(committed_doc) != got_f["doc_body"]:
                problems.append(f"the registration body committed at {commit[:10]} differs from the body on disk")
        except subprocess.CalledProcessError:
            problems.append(f"{doc_rel} is not in commit {commit[:10]}")
    return problems


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 10. The walk (ONCE, after the freeze)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _ticker_series(S: Store, t: str) -> tuple:
    k = S.D.tid.get(t)
    if k is None:
        return None, None
    return runner.bars_for(S.D, k)


def _bar_index(S: Store, cidx: np.ndarray, d: date) -> Optional[int]:
    """The index of session `d` in a ticker's series (None when the ticker has no bar that session)."""
    pos = S.cal_pos.get(d) if hasattr(S, "cal_pos") else None
    if pos is None:
        S.cal_pos = {dd: i for i, dd in enumerate(S.D.cal)}
        pos = S.cal_pos.get(d)
    if pos is None:
        return None
    j = int(np.searchsorted(cidx, pos))
    return j if j < len(cidx) and int(cidx[j]) == pos else None


def e_cutoff(S_B: Store) -> date:
    """The outcome-INDEPENDENT decisive cutoff on E (review LOW, 2026-11-01): the last session whose 120-session walk
    plus the trail's next open fits before the seal — the sealed calendar's session len - 1 - (HORIZON + 1). A trade
    with a later E is walked (it holds its slot, blocks its ticker, feeds the safeguards) but is NEVER decisive,
    whatever its outcome — otherwise a late-2024 fill keeps its fast losers and loses its slow winners."""
    cal = S_B.D.cal
    return cal[len(cal) - 1 - (HORIZON + 1)]


def walk_inputs(stores: dict, get_store, lr: dict, ed: date) -> tuple:
    """(bars, cidx, e_i, store_name) for the forward walk of a list row. Era-A list rows with E in the REPORTING era
    B (E > ERA_A_E_LAST: the Q1-2022 store seam) walk forward on the sealed cb702 copy when that store has the ticker
    with an E bar whose high and low agree with pre_v2's within MISMATCH_MAX — pre_v2's bars end 2022-06-30 and would
    leave every trade still open then an open mark. Otherwise the row's own store."""
    t = lr["ticker"]
    S = get_store(lr["era_store"])
    bars, cidx = _ticker_series(S, t)
    e_i = _bar_index(S, cidx, ed) if bars is not None else None
    chosen = lr["era_store"]
    if lr["era_store"] == "A" and ed > ERA_A_E_LAST and e_i is not None:
        SB = get_store("B")
        barsB, cidxB = _ticker_series(SB, t)
        e_iB = _bar_index(SB, cidxB, ed) if barsB is not None else None
        if e_iB is not None:
            hA, lA = float(bars.h[e_i]), float(bars.l[e_i])
            hB, lB = float(barsB.h[e_iB]), float(barsB.l[e_iB])
            if abs(hB - hA) / hA <= MISMATCH_MAX and abs(lB - lA) / lA <= MISMATCH_MAX:
                bars, cidx, e_i, chosen = barsB, cidxB, e_iB, "B"
    return bars, cidx, e_i, chosen


def free_point(status: str, held: int, fwd, day0: dict, e_iso: str, date_at) -> tuple:
    """(free_date, free_minute): when the trade's LAST share leaves — the slot and the ticker guard free then
    (review HIGH 3: an open mark used to hold its slot to the data end). A day-0 stop-out: E at its exit minute; a
    DEGRADED walk (a hole, a delisting, the store's end): its last forward bar (E itself with none), the end of that
    day; a terminal exit or the 120-session mark: the session of its last event (the trail's next open: that day,
    freed before the first tick by `exit_at_open`)."""
    if status == "stopped_day0":
        return e_iso, day0.get("exit_minute")
    if status == "degraded":
        return (fwd.dates[-1].isoformat() if len(fwd) else e_iso), None
    return date_at(int(held)).isoformat(), None


def leg_rows(events: list, *, fill: float, stop: float, cost: float, e_iso: str, dates_from_e, day0: dict,
             fm: Optional[int]) -> list:
    """[(date, minute | None, kind, r_leg)] — every leg that moves shares, in R at `cost` (adjusted-scale dollars a
    share, paid on the entry and on the leg). Day-0 legs carry their minute (`day0_facts`); daily legs carry None."""
    out = []
    for j, kind, px, frac in events:
        if not frac > 0 or kind in ("stop_to", "be_above_close"):
            continue
        r_leg = ((float(px) - cost) - (fill + cost)) * float(frac) / (fill - stop)
        if j == 0:
            if kind == "partial_r":
                minute = day0.get("partial_minute")
            elif kind in ("day0_stop", "day0_gap"):
                minute = day0.get("exit_minute")
            elif kind == "sold_after_fill":
                minute = (fm + 1) if fm is not None else None
            else:
                minute = None
            out.append((e_iso, minute, kind, r_leg))
        else:
            out.append((dates_from_e(int(j)).isoformat(), None, kind, r_leg))
    return out


def run_walk(out_dir: Path, *, force_unfrozen: bool = False, limit_days: Optional[int] = None,
             smoke_from: Optional[str] = None) -> dict:
    index = minute_index()
    request = read_request()
    if not force_unfrozen:
        problems = freeze_problems(out_dir)
        if problems:
            raise SystemExit("REFUSED — the freeze does not hold:\n  " + "\n  ".join(problems))
        problems = coverage_problems(coverage(index, request), len(request))
        if problems:
            raise SystemExit("REFUSED — the pull does not cover the pinned request:\n  " + "\n  ".join(problems))
        if read_request(RAW_REQUEST) and not RAW_PULL.exists():
            raise SystemExit(f"REFUSED — the raw-close pull is missing: {RAW_PULL}")
        for name in ("trades.tsv.gz", "report.txt"):
            if (out_dir / name).exists():
                raise SystemExit(f"REFUSED — {out_dir / name} exists: the walk runs once")
    unfetchable = coverage(index, request)["unfetchable_pairs"] if request else set()
    raw, raw_meta = load_raw_pull()
    rows = read_list(OUT)                       # the list always lives in the probe's out/ (a smoke writes elsewhere)
    by_e = defaultdict(list)
    for r in rows:
        by_e[r["E"]].append(r)
    e_dates = sorted(by_e)
    if smoke_from:
        e_dates = [e for e in e_dates if e >= smoke_from]
    if limit_days:
        e_dates = e_dates[:limit_days]
    smoke = force_unfrozen
    stores: dict = {}

    def get_store(era: str) -> Store:
        if era not in stores:
            stores[era] = load_store(era)
            stores[era].cal_pos = {dd: i for i, dd in enumerate(stores[era].D.cal)}
        return stores[era]

    cutoff = e_cutoff(get_store("B"))
    trades, excl = [], Counter()
    n_raw2 = n_raw_missing = 0
    t0 = time.time()
    for n_e, e in enumerate(e_dates):
        ed = date.fromisoformat(e)
        assert_sealed(ed, "breakout day")
        names = by_e[e]
        era = names[0]["era_store"]
        S = get_store(era)
        src = {}
        for lr in names:
            src.setdefault(held_in(index, e, lr["ticker"]), []).append(lr["ticker"])
        blocks = {}
        for d, want in src.items():
            if d is None:
                continue
            files = next(f for dd, _, f in index if dd == d)
            b, _info = runner.read_minute_file(files[e], set(want))
            done = next(dn for dd, dn, _ in index if dd == d)
            for t in want:
                blocks[t] = runner.minutes_for(b, done, e, t)
        for lr in names:
            t = lr["ticker"]
            key = (e, t)
            raw_factor = float(lr["raw_factor_D"])
            if int(lr.get("raw_src") or 0) == 2:
                # the raw scale of a split-list-only ticker, re-judged from the main loop's raw-close pull (§7)
                n_raw2 += 1
                raw_d = raw.get((t, lr["scan_date"]))
                if raw_d is None:
                    n_raw_missing += 1
                    excl["raw_close_missing"] += 1
                    continue
                if raw_d < bv.MIN_PRICE:
                    excl["below_floor_raw"] += 1            # never on the live list: no order, no slot
                    continue
                raw_factor = raw_d / float(lr["close"])
            mb, state = blocks.get(t, (None, "pending"))
            if state != "ok" or mb is None or len(mb) == 0:
                excl["minutes_unfetchable" if (e, t) in unfetchable else f"minutes_{state}"] += 1
                continue
            bars, cidx, e_i, fwd_store = walk_inputs(stores, get_store, lr, ed)
            if e_i is None:
                excl["no_daily_bar_E"] += 1
                continue
            dh, dl = float(bars.h[e_i]), float(bars.l[e_i])
            if abs(float(mb.h.max()) - dh) / dh > MISMATCH_MAX or abs(float(mb.l.min()) - dl) / dl > MISMATCH_MAX:
                excl["minute_daily_mismatch"] += 1
                continue
            mins = minutes_to_dict(mb)
            tr = simulate_entry(mins, list_level=lr["level"], adr20=lr["adr20"], vol_bar=lr["vol_bar"])
            rec = {"key": f"{e}|{t}", "E": e, "D": lr["scan_date"], "ticker": t, "list_rank": lr["list_rank"], "era_store": era,
                   "fwd_store": fwd_store, "era": "2017-21" if ed <= ERA_A_E_LAST else "2022-24", "year": ed.year, "month": e[:7],
                   "list_level": lr["level"], "adr20": lr["adr20"], "vol_bar": lr["vol_bar"], "rs_best": lr["rs_best"],
                   "raw_factor": raw_factor, "raw_src": int(lr.get("raw_src") or 0), "outcome": tr["outcome"], "reason": tr["reason"],
                   "placed_m": tr["placed_m"], "cancel_m": tr["cancel_m"], "order_kind": (tr["order"] or {}).get("kind"),
                   "level": tr["level"], "orh5": tr["orh5"], "fill": tr["fill"], "fill_minute": tr["fill_minute"],
                   "placed_stop": tr["placed_stop"], "stop": tr["stop"], "stop_check": (tr["stop_check"] or {}).get("action"),
                   "fill_bar_low": tr["fill_bar_low"], "adverse_stop": bool(tr["adverse_stop"]),
                   "holds": tr["holds"], "reprices": tr["reprices"], "filled": tr["outcome"] in ("filled", "sold_after_fill"),
                   "after_cutoff": ed > cutoff, "decisive": False, "free_date": None, "free_minute": None, "exit_at_open": False}
            excl[f"entry_{tr['outcome']}"] += 1
            if tr["outcome"] == "sold_after_fill":
                fill, stop, px, fm = tr["fill"], tr["stop"], tr["sold_after_fill_px"], tr["fill_minute"]
                rec.update(status="sold_after_fill", events=[(0, "sold_after_fill", px, 1.0)], sessions_held=0, mature=True,
                           exit_date=e, free_date=e, free_minute=fm + 1, exit_kind="sold_after_fill", open_mark=False,
                           decisive=not rec["after_cutoff"])
                _book_costs(rec, fill, stop, {"partial_minute": None, "exit_minute": None}, fm, lambda j: ed)
                trades.append(rec)
                continue
            if tr["outcome"] != "filled":
                trades.append(rec)
                continue
            fill, stop, fm = tr["fill"], tr["stop"], tr["fill_minute"]
            if not stop < fill:
                excl["stop_at_or_above_fill"] += 1
                rec.update(outcome="abstain", reason="stop_at_or_above_fill", filled=False)
                trades.append(rec)
                continue
            day0 = ppr.day0_facts([(m, b["open"], b["high"], b["low"]) for m, b in sorted(mins.items())], fill=fill, stop=stop,
                                  fill_minute=fm)
            fwd, cut = cb.forward_window(bars, cidx, e_i, HORIZON)
            for d in fwd.dates:
                assert_sealed(d, "forward bar")
            res = exit_one(fill=fill, stop=stop, day0=day0, closes_before=bars.c[:e_i + 1], fwd=fwd, adr20=lr["adr20"])
            held = int(res["sessions_held"])
            exit_kind = res["events"][-1][1] if res["events"] else None
            mature = bool(cb.is_mature(res["status"], len(fwd)))
            date_at = lambda j, _b=bars, _e=e_i: _b.dates[min(_e + j, len(_b) - 1)]
            free_date, free_minute = free_point(res["status"], held, fwd, day0, e, date_at)
            rec.update(status=res["status"], events=res["events"], sessions_held=held, mature=mature, open_mark=not mature,
                       hole_cut=bool(cut), n_fwd=len(fwd), day0_third=day0.get("partial_price"),
                       day0_stopped=bool(day0.get("stopped")), day0_peak=day0.get("peak"), exit_kind=exit_kind,
                       exit_date=(free_date if mature else None),
                       free_date=free_date, free_minute=free_minute, exit_at_open=(exit_kind == "trail"),
                       realized_r=float(res["realized_r"]), decisive=bool(mature and not rec["after_cutoff"]))
            _book_costs(rec, fill, stop, day0, fm, date_at)
            trades.append(rec)
        if n_e % 50 == 0:
            print(f"  day {n_e}/{len(e_dates)} {e}: {len(trades)} rows, {dict(excl)} ({time.time() - t0:.0f}s)", flush=True)
    if not smoke and n_raw2 and n_raw_missing > UNFETCHABLE_MAX * n_raw2:
        raise SystemExit(f"REFUSED — {n_raw_missing:,} of {n_raw2:,} raw_src=2 list rows have no pulled raw close on D (> {UNFETCHABLE_MAX:.0%})")
    # the books
    placed = [t for t in trades if t.get("placed_m") is not None]
    books = {"guard": apply_book(placed, slots=None, safeguards=False, sessions=e_dates),
             "cap": apply_book(placed, slots=CAP_SLOTS, safeguards=False, sessions=e_dates),
             "lane": apply_book(placed, slots=CAP_SLOTS, safeguards=True, sessions=e_dates)}
    for t in trades:
        for b in BOOKS:
            t[f"adm_{b}"] = books[b]["admitted"].get(t["key"], None)
            t[f"why_{b}"] = books[b]["reason"].get(t["key"], None)
    blocked = {b: dict(books[b]["blocked"]) for b in BOOKS}
    if smoke:
        # a SMOKE run: the funnel tally and the row SHAPES only — no R is written or printed (the registration is
        # read once, after the freeze); the rows go to the scratch copy for the crash check with every R column removed
        phase = phase_by_night()
        tally = {"days": len(e_dates), "rows": len(trades), "excl": dict(excl), "blocked": blocked, "cutoff": cutoff.isoformat(),
                 "qqq_phase_join": dict(Counter(phase.get(t["D"], "phase_unknown") for t in trades)),
                 "outcomes": dict(Counter(t.get("outcome") for t in trades)),
                 "reasons": dict(Counter(reason_key(t.get("reason")) for t in trades if not t.get("filled"))),
                 "stop_checks": dict(Counter(t.get("stop_check") for t in trades if t.get("filled"))),
                 "statuses": dict(Counter(t.get("status") for t in trades if t.get("filled"))),
                 "fwd_store": dict(Counter(t.get("fwd_store") for t in trades)),
                 "adverse_fill_minute": sum(1 for t in trades if t.get("adverse_stop")),
                 "mature": sum(1 for t in trades if t.get("mature")), "decisive": sum(1 for t in trades if t.get("decisive")),
                 "stepper_equal_walk_pp": "asserted on every trade", "raw_pull_present": bool(raw)}
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "smoke_tally.json").write_text(json.dumps(tally, indent=1, default=str))
        print(json.dumps(tally, indent=1, default=str), flush=True)
        drop = {"realized_r", "events", "legs", "total_r"} | {k for t in trades for k in t if k.startswith("r_")}
        keep = sorted({k for t in trades for k in t} - drop)
        write_tsv(out_dir / "smoke_rows.tsv.gz", trades, keep)
        return tally
    write_report(trades, excl, blocked, out_dir, stores, cutoff, raw_meta)
    cols = sorted({k for t in trades for k in t}, key=lambda k: (k != "key", k))
    for t in trades:
        t["events"] = json.dumps(t.get("events"))
        t["legs"] = json.dumps(t.get("legs"))
    write_tsv(out_dir / "trades.tsv.gz", trades, cols)
    return {"trades": len(trades), "excl": dict(excl), "blocked": blocked}


def _book_costs(rec: dict, fill: float, stop: float, day0: dict, fm: Optional[int], date_at) -> None:
    """The cost rows, the adverse-ordering row, the safeguards' legs and risk fraction of ONE filled trade."""
    for cc in COST_CENTS:
        c = cc / 100.0 / rec["raw_factor"]
        r = r_at_cost(rec["events"], fill, stop, c)
        rec[f"r_{int(cc)}c"] = r
        # ADVERSE ordering (review HIGH 4): the fill bar's low under the placed stop -> live's OTO stop (active from
        # the fill) fired inside the fill minute: stopped at the placed stop, R against the placed risk
        if rec["adverse_stop"]:
            ps = float(rec["placed_stop"])
            rec[f"r_adv_{int(cc)}c"] = ((ps - c) - (fill + c)) / (fill - ps)
        else:
            rec[f"r_adv_{int(cc)}c"] = r
    c_primary = PRIMARY_COST / 100.0 / rec["raw_factor"]
    rec["legs"] = leg_rows(rec["events"], fill=fill, stop=stop, cost=c_primary, e_iso=rec["E"], dates_from_e=date_at,
                           day0=day0, fm=fm)
    rec["total_r"] = rec[f"r_{int(PRIMARY_COST)}c"]
    rec["f_risk"] = risk_fraction(fill, stop)


def phase_by_night() -> dict:
    """{scan_date: 'phase_on' | 'phase_off' | 'phase_unknown'} from the population stage's night tables (the QQQ
    10/20 phase at D, `cb.phase_qqq_10_20`)."""
    out = {}
    for era in ("A", "B"):
        pth = OUT / f"nights_era{era}.tsv"
        if not pth.exists():
            continue
        for r in read_tsv_rows(pth):
            v = (r.get("qqq_phase") or "").strip()
            out[r["scan_date"]] = "phase_on" if v == "True" else ("phase_off" if v == "False" else "phase_unknown")
    return out


BOOK_LABEL = {"guard": "GUARD ONLY (no cap: the same-ticker guard on every fill)",
              "cap": "CAPPED (guard + 5 slots) — THE PRIMARY ROW",
              "lane": "LANE (guard + 5 slots + 2% daily loss + 10-loss breaker; the drawdown breaker not modelled)"}


def write_report(trades: list, excl: Counter, blocked: dict, out_dir: Path, stores: dict, cutoff: date, raw_meta) -> None:
    phase = phase_by_night()
    for t in trades:
        t["qqq_phase"] = phase.get(t["D"], "phase_unknown")
    L: list = []
    A = L.append
    A("BREAKOUT V1 — PAPER BASELINE REPLAY (registration docs/analysis/breakout_v1_paper_replay_prereg_2026-11-01.md)")
    A(f"written {date.today().isoformat()}; list rows walked {len(trades):,}; exclusions {dict(excl)}")
    A(f"blocked per book: {blocked}")
    n_filled = sum(1 for t in trades if t.get("filled"))
    A(f"filled {n_filled:,}; mature {sum(1 for t in trades if t.get('mature')):,}; open marks "
      f"{sum(1 for t in trades if t.get('filled') and not t.get('mature')):,}; walked but NOT decisive (E after the cutoff "
      f"{cutoff}) {sum(1 for t in trades if t.get('filled') and t.get('after_cutoff')):,}; sold after the fill (too wide) "
      f"{sum(1 for t in trades if t.get('status') == 'sold_after_fill'):,}; Q1-2022 seam walked on the sealed cb702 copy "
      f"{sum(1 for t in trades if t.get('era_store') == 'A' and t.get('fwd_store') == 'B'):,}; fill-minute low under the "
      f"placed stop (the adverse row) {sum(1 for t in trades if t.get('adverse_stop')):,} of {n_filled:,}")
    A(f"raw-close pull: {raw_meta}")
    A("")
    A("THE PRIMARY ROW: the CAPPED book (guard + 5 slots, the small-cap lane's occupancy 0) at 2c on the entry and every exit;")
    A("decisive trades only (mature, E on or before the cutoff). Verdict per group (the bar, §6 of the registration):")
    A("PASS = n >= 100, interval lower end > 0, >= 3R share >= 8%; FAIL = n >= 100, interval wholly under +0.25R, >= 3R share < 8%;")
    A("else CAN'T TELL (with its named sub-reading). Every other row is reported beside with the same words and decides nothing.")
    A("")
    decisive = [t for t in trades if t.get("filled") and t.get("decisive")]
    for book in ("cap", "lane", "guard"):
        pop = [t for t in decisive if t.get(f"adm_{book}")]
        A(f"==== {BOOK_LABEL[book]} ====")
        cols = [(f"r_{int(cc)}c", f"cost {int(cc)}c per share each way") for cc in COST_CENTS]
        if book == "cap":
            cols.append((f"r_adv_{int(PRIMARY_COST)}c", f"ADVERSE fill-minute ordering at {int(PRIMARY_COST)}c (beside)"))
        for col, title in cols:
            A(f"-- {title} --")
            groups = [("all", pop)]
            for era in ("2017-21", "2022-24"):
                groups.append((f"era {era}", [t for t in pop if t["era"] == era]))
            for y in sorted({t["year"] for t in pop}):
                groups.append((f"year {y}", [t for t in pop if t["year"] == y]))
            for ph in ("phase_on", "phase_off", "phase_unknown"):
                g = [t for t in pop if t["qqq_phase"] == ph]
                if g:
                    groups.append((f"QQQ {ph} at D", g))
            for name, g in groups:
                s = stats(np.array([t[col] for t in g]), [t["month"] for t in g], key=f"{BOOT_KEY}|{book}|{col}|{name}")
                line = fmt_stats(name, s)
                if col == f"r_{int(PRIMARY_COST)}c" and (name == "all" or name.startswith("era")):
                    v, why = verdict(s)
                    line += f"   VERDICT {v} ({why})" if book == "cap" else f"   [beside: {v}]"
                A(line)
            A("")
    A("THE TAIL FIRST — the 15 biggest winners of the primary row (ticker, E, R, sessions held, exit)")
    top = sorted([t for t in decisive if t.get("adm_cap")], key=lambda t: -t[f"r_{int(PRIMARY_COST)}c"])[:15]
    for t in top:
        A(f"  {t['ticker']:6s} {t['E']}  {t[f'r_{int(PRIMARY_COST)}c']:+7.2f}R  held {t['sessions_held']:3d}  {t['exit_kind']}  fill {t['fill']:.2f} stop {t['stop']:.2f}")
    A("")
    A("ENTRY FUNNEL (every list name-day with minutes)")
    for k, v in sorted(excl.items()):
        A(f"  {k:40s} {v:7d}")
    reasons = Counter(reason_key(t.get("reason")) for t in trades if not t.get("filled"))
    for k, v in reasons.most_common():
        A(f"  not filled: {k:50s} {v:7d}")
    A(f"  fill-stop decisions: {dict(Counter(t.get('stop_check') for t in trades if t.get('filled')))}")
    A(f"  order kinds: {dict(Counter(t.get('order_kind') for t in trades if t.get('placed_m') is not None))}")
    A(f"  exits (decisive): {dict(Counter(t.get('exit_kind') for t in decisive))}")
    A(f"  statuses (all filled): {dict(Counter(t.get('status') for t in trades if t.get('filled')))}")
    for book in BOOKS:
        A(f"  book {book}: admitted fills {sum(1 for t in trades if t.get('filled') and t.get(f'adm_{book}')):,}, "
          f"blocked {blocked[book]}")
    A("")
    for era, S in stores.items():
        A(f"store {era}: {S.notes}")
    (out_dir / "report.txt").write_text("\n".join(L) + "\n")
    print("\n".join(L), flush=True)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 11. The dry run: hand-computed cases, the fuzz, the calibration
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _day(bars: dict) -> dict:
    """A synthetic session from {minute: (o, h, l, c, v)}."""
    return {m: {"open": o, "high": h, "low": l, "close": c, "volume": v} for m, (o, h, l, c, v) in bars.items()}


def flat_day(n: int = 390, px: float = 10.0, vol: float = 1_000.0, over: Optional[dict] = None) -> dict:
    d = {m: (px, px, px, px, vol) for m in range(n)}
    d.update(over or {})
    return _day(d)


def dry_cases() -> list:
    """Hand-computed cases; each returns (name, passed, detail). The volume bar is 390 x 1,000 = 390,000 shares a day;
    with 1,000 shares a minute the pace is 1 / CUM_SHARE-weighted — F1 is set per case through `vol_bar`."""
    out = []
    def chk(name, cond, detail=""):
        out.append((name, bool(cond), detail))
    big = 10.0
    # F1 arithmetic: a day of 1,000 shares a minute; by minute m the cumulative is 1,000 x (m+1); the need is
    # vol_bar x CUM_SHARE[m]. With vol_bar = 100,000: need at m=4 is 3,120 -> 5,000 >= 3,120 permits.
    vb = 100_000.0
    # 1. fill at the level: ORH5 = 10.10 (minute 2 high), the list level 10.00, the stop = the day low 9.90 (minute 3),
    #    the break in minute 7 (high 10.20, open 10.05 <= level) -> fill 10.10 at minute 7; placed stop 9.90; the true
    #    low through minute 7 is 9.90 -> 'keep'. ADR 5%: width (10.10-9.90)/10.10 = 1.98% ok.
    d = flat_day(px=10.0, vol=1000, over={2: (10.0, 10.10, 10.0, 10.05, 1000), 3: (10.0, 10.05, 9.90, 10.0, 1000),
                                       7: (10.05, 10.20, 10.05, 10.15, 1000)})
    tr = simulate_entry(d, list_level=10.0, adr20=0.05, vol_bar=vb)
    chk("fill at the level (ORH5 10.10 > list 10.00), stop = day low 9.90, kept",
        tr["outcome"] == "filled" and abs(tr["fill"] - 10.10) < 1e-9 and tr["fill_minute"] == 7 and abs(tr["stop"] - 9.90) < 1e-9
        and tr["stop_check"]["action"] == "keep" and tr["placed_m"] == 5, json.dumps(tr, default=str)[:300])
    # 2. never filled: the level never breaks -> cancelled at 15:55 (window:breakout_unfilled_eod), placed at 09:35
    d = flat_day(px=10.0, vol=1000, over={2: (10.0, 10.10, 10.0, 10.05, 1000), 3: (10.0, 10.05, 9.90, 10.0, 1000)})
    tr = simulate_entry(d, list_level=10.0, adr20=0.05, vol_bar=vb)
    chk("never filled -> cancelled 15:55 window:breakout_unfilled_eod", tr["outcome"] == "cancelled" and tr["cancel_m"] == 385
        and tr["reason"].startswith("window:breakout_unfilled_eod") and tr["placed_m"] == 5, tr["reason"])
    # 3. too wide: ADR 1%; at 09:35 the width (10.10 - 9.90)/10.10 = 1.98% > 1% -> abstain before any order
    tr = simulate_entry(d, list_level=10.0, adr20=0.01, vol_bar=vb)
    chk("too wide at 09:35 -> abstain setup:stop_too_wide, no order", tr["outcome"] == "abstain" and "stop_too_wide" in tr["reason"]
        and tr["placed_m"] is None, tr["reason"])
    # 3b. too wide AFTER the order rests: ADR 3%; a new low 9.70 in minute 20 makes (10.10-9.70)/10.10 = 3.96% -> the
    #     tick at minute 21 cancels it (setup:stop_too_wide)
    d2 = flat_day(px=10.0, vol=1000, over={2: (10.0, 10.10, 10.0, 10.05, 1000), 3: (10.0, 10.05, 9.90, 10.0, 1000),
                                        20: (10.0, 10.0, 9.70, 9.8, 1000)})
    tr = simulate_entry(d2, list_level=10.0, adr20=0.03, vol_bar=vb)
    chk("a new low widens past ADR while resting -> cancelled setup:stop_too_wide at the next tick",
        tr["outcome"] == "cancelled" and "stop_too_wide" in tr["reason"] and tr["cancel_m"] == 21, f"{tr['reason']} m={tr['cancel_m']}")
    # 4. volume lapse: vol_bar 390,000 (1.2x of a 325,000-share average): need at m=4 is 390,000 x 0.0312 = 12,169 but
    #    only 5,000 traded -> hold; make minutes 0..4 heavy (20,000 each = 100,000 by minute 4 -> permits at 09:35),
    #    then 1,000 a minute: by minute 60 cumulative 156,000 vs need 390,000 x CUM_SHARE[60] = 66,195 -> still ok;
    #    by minute 200 cum 296,000 vs need 390,000 x 0.4021 = 156,836 ok ... the curve ends at 0.8035 -> 313,000 at
    #    m=389 vs cum 485,000: never lapses. Use a lighter tail: 100 shares a minute after minute 4: cum at m=60 =
    #    105,600 vs need 66,195 ok; at m=120: 111,600 vs 390,000 x 0.2838 = 110,700 ok; at m=125: 112,100 vs
    #    390,000 x 0.2912 = 113,560 -> LAPSE at last_completed 125 -> cancelled at the tick of minute 126.
    heavy = {m: (10.0, 10.10 if m == 2 else 10.0, 9.90 if m == 3 else 10.0, 10.0, 20_000) for m in range(5)}
    light = {m: (10.0, 10.0, 10.0, 10.0, 100) for m in range(5, 390)}
    d3 = _day({**heavy, **light})
    # the hand-computed lapse minute: the first last-completed L >= 5 with 100,000 + 100 x (L - 4) < 390,000 x CUM_SHARE[L]
    lapse_L = next(L for L in range(5, 390) if 100_000 + 100 * (L - 4) < 390_000.0 * curve.CUM_SHARE[L])
    tr = simulate_entry(d3, list_level=10.0, adr20=0.05, vol_bar=390_000.0)
    chk(f"volume pace lapses (F1) while resting -> cancelled setup:breakout_volume_below_curve at the tick after minute {lapse_L} (minute {lapse_L + 1})",
        tr["outcome"] == "cancelled" and "volume_below_curve" in tr["reason"] and tr["cancel_m"] == lapse_L + 1, f"{tr['reason']} m={tr['cancel_m']}")
    # 4b. F1 holds the buy before the first order: 100 shares a minute from the open; vol_bar 390,000: never permits ->
    #     never placed
    d4 = _day({m: (10.0, 10.10 if m == 2 else 10.0, 9.90 if m == 3 else 10.0, 10.0, 100) for m in range(390)})
    tr = simulate_entry(d4, list_level=10.0, adr20=0.05, vol_bar=390_000.0)
    chk("F1 never permits -> never placed (holds every tick)", tr["outcome"] == "never_placed" and tr["holds"] == 380, f"holds={tr['holds']}")
    # 5. the stop at the TRUE low: a flush INSIDE the fill minute. Minute 7: open 10.05, high 10.20, low 9.80 — the
    #    order (placed stop 9.90 through minute 6) fills at 10.10; the tick at minute 8 reads the true low 9.80:
    #    width (10.10 - 9.80)/10.10 = 2.97% <= ADR 5% -> LOWERED to 9.80.
    d5 = flat_day(px=10.0, vol=1000, over={2: (10.0, 10.10, 10.0, 10.05, 1000), 3: (10.0, 10.05, 9.90, 10.0, 1000),
                                        7: (10.05, 10.20, 9.80, 10.15, 1000)})
    tr = simulate_entry(d5, list_level=10.0, adr20=0.05, vol_bar=vb)
    chk("a flush inside the fill minute -> the stop LOWERED to the true low 9.80 one minute after",
        tr["outcome"] == "filled" and tr["stop_check"]["action"] == "lower" and abs(tr["stop"] - 9.80) < 1e-9 and abs(tr["placed_stop"] - 9.90) < 1e-9, json.dumps(tr["stop_check"]))
    #    with ADR 2%: 2.97% > 2% -> SOLD at the open of minute 8 (10.0) -> R = (10.0-10.10)/(10.10-9.90) = -0.5 at 0c
    tr = simulate_entry(d5, list_level=10.0, adr20=0.02, vol_bar=vb)
    chk("the true low too wide -> the whole position sold at minute 8's open (setup:stop_too_wide_after_fill)",
        tr["outcome"] == "sold_after_fill" and abs(tr["sold_after_fill_px"] - 10.0) < 1e-9 and "too_wide_after_fill" in tr["reason"], tr["reason"])
    # 6. the #500 fallback: F1 permits only at minute 30 (heavy volume in minutes 25..29) while the price is already
    #    above the level (10.30 from minute 10): the order is a LIMIT at round(10.30 x 1.002, 2) = 10.32, filled at the
    #    next bar's open 10.30 (<= 10.32). Width (10.32 - 9.90)/10.32 = 4.07% <= 5%; chase (10.32-9.90)/(10.10-9.90) = 2.1 > 1.5 -> abstain chase cap.
    #    (heavy volume in minute 29 ONLY, so F1 first permits at last-completed 29: cum 3,000 + 50,000 = 53,000 >=
    #    390,000 x CUM_SHARE[29] = 38,412, while at 28 cum 2,900 < 37,000)
    base = {m: (10.0, 10.10 if m == 2 else 10.0, 9.90 if m == 3 else 10.0, 10.0, 100) for m in range(390)}
    for m in range(10, 390):
        base[m] = (10.30, 10.30, 10.30, 10.30, 100)
    base[29] = (10.30, 10.30, 10.30, 10.30, 50_000)
    assert 3_000 + 50_000 >= 390_000 * curve.CUM_SHARE[29] and 2_900 < 390_000 * curve.CUM_SHARE[28]
    d6 = _day(base)
    tr = simulate_entry(d6, list_level=10.0, adr20=0.05, vol_bar=390_000.0)
    chk("#500: price already past the level when F1 first permits (tick 30) -> limit fallback at 10.32, refused by the 1.5x chase cap",
        tr["outcome"] == "abstain" and "chase_cap" in tr["reason"] and "10.32" in tr["reason"], tr["reason"])
    #    the same with the stop at 9.50 (a minute-3 low of 9.50): planned risk 0.60, fallback risk 0.82 -> 1.37x < 1.5
    #    -> a limit at 10.32 placed at the tick of minute 30, filled at minute 30's open 10.30; ADR 10% so the width 7.9% passes
    base[3] = (10.0, 10.0, 9.50, 10.0, 100)
    tr = simulate_entry(_day(base), list_level=10.0, adr20=0.10, vol_bar=390_000.0)
    chk("#500: the limit fallback (10.32) fills at the next bar's open 10.30 inside the chase cap; placed and filled at minute 30",
        tr["outcome"] == "filled" and tr["order"]["kind"] == "limit" and abs(tr["order"]["limit"] - 10.32) < 1e-9
        and abs(tr["fill"] - 10.30) < 1e-9 and tr["fill_minute"] == 30 and tr["placed_m"] == 30 and tr["stop_check"]["action"] == "keep",
        json.dumps(tr, default=str)[:300])
    # 7. re-price: a new low 9.85 in minute 10 (ADR 5%) moves the resting stop 9.90 -> 9.85 at the tick of minute 11;
    #    the break in minute 12 fills at 10.10 with the placed stop 9.85; true low 9.85 -> keep
    d7 = flat_day(px=10.0, vol=1000, over={2: (10.0, 10.10, 10.0, 10.05, 1000), 3: (10.0, 10.05, 9.90, 10.0, 1000),
                                        10: (10.0, 10.0, 9.85, 9.9, 1000), 12: (10.0, 10.20, 10.0, 10.1, 1000)})
    tr = simulate_entry(d7, list_level=10.0, adr20=0.05, vol_bar=vb)
    chk("a new day low while resting re-prices the stop (9.90 -> 9.85) before the fill", tr["outcome"] == "filled"
        and abs(tr["placed_stop"] - 9.85) < 1e-9 and tr["reprices"] == 1 and tr["stop_check"]["action"] == "keep", json.dumps(tr, default=str)[:200])
    # 8. gapped through the level: minute 7 opens 10.15 (> level 10.10, <= limit 10.17) -> fill at the open 10.15
    d8 = flat_day(px=10.0, vol=1000, over={2: (10.0, 10.10, 10.0, 10.05, 1000), 3: (10.0, 10.05, 9.90, 10.0, 1000),
                                        7: (10.15, 10.30, 10.15, 10.2, 1000)})
    tr = simulate_entry(d8, list_level=10.0, adr20=0.05, vol_bar=vb)
    chk("a bar opening between the level and the limit fills at its open (10.15)", tr["outcome"] == "filled" and abs(tr["fill"] - 10.15) < 1e-9, str(tr["fill"]))
    #    opening ABOVE the limit (10.25 > 10.17): the triggered limit rests; minute 9's low 10.12 <= 10.17 -> fill at 10.17
    d9 = flat_day(px=10.0, vol=1000, over={2: (10.0, 10.10, 10.0, 10.05, 1000), 3: (10.0, 10.05, 9.90, 10.0, 1000),
                                        7: (10.25, 10.30, 10.25, 10.3, 1000), 8: (10.30, 10.30, 10.30, 10.30, 1000),
                                        9: (10.20, 10.20, 10.12, 10.15, 1000)})
    tr = simulate_entry(d9, list_level=10.0, adr20=0.05, vol_bar=vb)
    lim = stop_limit_buy_price(10.10)
    chk(f"a bar opening above the limit {lim:.2f} leaves the triggered limit resting; filled at the limit when a later low reaches it",
        tr["outcome"] == "filled" and abs(tr["fill"] - lim) < 1e-9 and tr["fill_minute"] == 9, f"fill={tr['fill']} m={tr['fill_minute']}")
    # 9. the exits (daily): fill 10, stop 9 (R = 1), day 0 nothing. +2R third: session 2 high 12.5 -> a third at 12.0,
    #    the stop to 10 from session 3; session 3 close 11 > fill: no second third (one third ever); trail live:
    #    closes_before 20 x 10 -> SMA20 after session 6 = (14 x 10 + 10.8 + 11.5 + 11.0 + 11.1 + 10.9 + 10.06) / 20 =
    #    10.268 > close 10.06 -> the rest sold at session 7's open 10.2: R = (12-10)/3 + (10.2-10) x 2/3 = +0.800
    cb20 = [10.0] * 20
    fwd = cb.daily_bars_from_arrays([date(2020, 1, 2) + timedelta(days=i) for i in range(8)],
                                    [10.5, 11.0, 11.5, 11.2, 11.0, 10.3, 10.2, 10.1], [11.0, 12.5, 11.8, 11.5, 11.2, 10.4, 10.3, 10.2],
                                    [10.2, 10.9, 11.0, 11.0, 10.8, 10.05, 10.0, 10.0], [10.8, 11.5, 11.0, 11.1, 10.9, 10.06, 10.1, 10.1], [1] * 8)
    d0 = ppr.day0_facts([], fill=10.0, stop=9.0, fill_minute=100)
    res = exit_one(fill=10.0, stop=9.0, day0=d0, closes_before=cb20, fwd=fwd, adr20=0.05)
    chk("+2R third at the target on session 2, stop to the fill, one third ever, the trail sells the rest at session 7's open: R +0.800",
        res["status"] == "trailed" and abs(res["realized_r"] - 0.8) < 1e-9 and [e[1] for e in res["events"]] == ["partial_r", "stop_to", "trail"]
        and res["events"][-1][0] == 7, str(res["events"]))
    # 10. the session-3 third at the close (no +2R): closes 10.5, 10.8, 10.6 (> fill), highs reach 11.0 >= +1R -> no cut;
    #     a third at 10.6; stop to 10; session 4 low 9.5 -> stopped at 10 (the stop in force from session 4):
    #     R = (10.6-10)/3 + 0 x 2/3 = +0.200
    fwd2 = cb.daily_bars_from_arrays([date(2020, 1, 2) + timedelta(days=i) for i in range(5)],
                                     [10.2, 10.6, 10.7, 10.4, 10.0], [11.0, 11.0, 11.0, 10.5, 10.1], [10.1, 10.4, 10.3, 9.5, 9.8],
                                     [10.5, 10.8, 10.6, 9.7, 10.0], [1] * 5)
    res = exit_one(fill=10.0, stop=9.0, day0=d0, closes_before=cb20, fwd=fwd2, adr20=0.05)
    chk("the session-3 third at the close (above the fill), then the stop rests at the fill and takes the rest on session 4: R +0.200",
        res["status"] == "stopped" and abs(res["realized_r"] - 0.2) < 1e-9 and [e[1] for e in res["events"]] == ["partial", "stop_to", "stop"], str(res["events"]))
    #     the same closes but session 3 closes UNDER the fill (9.8): no third; trail live from 3: SMA20 of 17x10 + 10.5 + 10.8 + 9.8 = 10.055 > 9.8 -> sold at session 4's open 10.4: R = +0.4 (the stall cut does not fire: highs reached 11)
    fwd3 = cb.daily_bars_from_arrays(fwd2.dates, fwd2.o, fwd2.h, fwd2.l, [10.5, 10.8, 9.8, 9.7, 10.0], fwd2.v)
    res = exit_one(fill=10.0, stop=9.0, day0=d0, closes_before=cb20, fwd=fwd3, adr20=0.05)
    chk("session 3 closes under the fill: NO third (his rule), the 20-day trail (live from 3) sells all at session 4's open: R +0.400",
        res["status"] == "trailed" and abs(res["realized_r"] - 0.4) < 1e-9 and [e[1] for e in res["events"]] == ["trail"], str(res["events"]))
    # 11. the stall cut: no high at +1R (11.0) by session 3 -> everything sold at session 3's close 10.4: R +0.4
    fwd4 = cb.daily_bars_from_arrays(fwd2.dates, [10.2, 10.3, 10.3, 10.4, 10.0], [10.6, 10.7, 10.9, 10.5, 10.1], [10.1, 10.2, 10.2, 9.5, 9.8],
                                     [10.5, 10.6, 10.4, 9.7, 10.0], fwd2.v)
    res = exit_one(fill=10.0, stop=9.0, day0=d0, closes_before=cb20, fwd=fwd4, adr20=0.05)
    chk("the stall cut: no high at fill + 1R by the close of session 3 -> all sold at that close: R +0.400",
        res["status"] == "time_exit" and abs(res["realized_r"] - 0.4) < 1e-9 and res["events"][-1][1] == "cut", str(res["events"]))
    # 12. the stop at the day low on session 1 (gap under): open 8.5 < stop 9 -> stop_gap at 8.5: R = -1.5
    fwd5 = cb.daily_bars_from_arrays(fwd2.dates, [8.5, 9, 9, 9, 9], [9.0, 9, 9, 9, 9], [8.0, 9, 9, 9, 9], [8.6, 9, 9, 9, 9], fwd2.v)
    res = exit_one(fill=10.0, stop=9.0, day0=d0, closes_before=cb20, fwd=fwd5, adr20=0.05)
    chk("a gap under the stop books the open (worse than -1R): R -1.500", res["status"] == "stopped" and abs(res["realized_r"] + 1.5) < 1e-9, str(res["events"]))
    # 13. same-bar ties: session 1 touches BOTH the stop (low 8.9) and the target (high 12.5) but opened under the
    #     target (10.5) -> the STOP is booked (pessimistic, no third): R -1
    fwd6 = cb.daily_bars_from_arrays(fwd2.dates, [10.5, 9, 9, 9, 9], [12.5, 9, 9, 9, 9], [8.9, 9, 9, 9, 9], [9.0, 9, 9, 9, 9], fwd2.v)
    res = exit_one(fill=10.0, stop=9.0, day0=d0, closes_before=cb20, fwd=fwd6, adr20=0.05)
    chk("a bar touching the stop AND the target that opened under the target books the stop, no third: R -1.000",
        res["status"] == "stopped" and abs(res["realized_r"] + 1.0) < 1e-9 and [e[1] for e in res["events"]] == ["stop"], str(res["events"]))
    #     ... but opened ABOVE the target (12.2): the third at the open 12.2 first, then the stop on the rest:
    #     R = (12.2-10)/3 + (9-10) x 2/3 = 0.7333 - 0.6667 = +0.0667
    fwd7 = cb.daily_bars_from_arrays(fwd2.dates, [12.2, 9, 9, 9, 9], [12.5, 9, 9, 9, 9], [8.9, 9, 9, 9, 9], [9.0, 9, 9, 9, 9], fwd2.v)
    res = exit_one(fill=10.0, stop=9.0, day0=d0, closes_before=cb20, fwd=fwd7, adr20=0.05)
    chk("the same bar opened above the target: the third at the open, then the stop: R +0.0667",
        res["status"] == "stopped" and abs(res["realized_r"] - (2.2 / 3 - 2 / 3)) < 1e-9 and [e[1] for e in res["events"]] == ["partial_r", "stop"], str(res["events"]))
    # 14. day 0 on the minutes: fill 10 at minute 7 (stop 9, target 12); minute 20 high 12.1 -> the third at 12.0 on day 0,
    #     the stop to 10 from minute 21; minute 30 low 9.95 -> stopped at 10 on day 0: nothing left. R = (12-10)/3 = +0.667
    mins = flat_day(px=10.5, vol=1000, over={20: (10.5, 12.1, 10.5, 11.0, 1000), 30: (10.2, 10.2, 9.95, 10.0, 1000)})
    d0b = ppr.day0_facts([(m, b["open"], b["high"], b["low"]) for m, b in sorted(mins.items())], fill=10.0, stop=9.0, fill_minute=7)
    res = exit_one(fill=10.0, stop=9.0, day0=d0b, closes_before=cb20, fwd=fwd2, adr20=0.05)
    chk("day 0: a +2R third on the minutes, then the stop at cost takes the rest the same day: R +0.667",
        d0b["partial_price"] == 12.0 and d0b["stopped"] and res["status"] == "stopped_day0" and abs(res["realized_r"] - 2 / 3) < 1e-9, str(d0b))
    # 15. the retry path is WIRED live but never reached here: every sale completes in a replay
    chk("retry_decision returns 'retry_third' on a due flag with no third sold (live path exists), None once a third sold",
        ppr.retry_decision(fwd=[{}] * 4, partial_taken=False, session_third_due=True) == ppr.RETRY_THIRD
        and ppr.retry_decision(fwd=[{}] * 4, partial_taken=True, session_third_due=True) is None
        and ppr.retry_decision(fwd=[{}] * 3, partial_taken=False, session_third_due=True) is None)
    # 16. costs: case 9's R at 2c with raw factor 1: entry 10.02, exits 11.98 (third) and 10.18: 1.96/3 + 0.16 x 2/3 = +0.7600
    chk("the 2c cost row: +0.800 -> +0.760 (2c on the entry and on each exit leg; the stop_to event carries no shares)",
        abs(r_at_cost([(2, "partial_r", 12.0, 1 / 3), (2, "stop_to", 10.0, 0.0), (7, "trail", 10.2, 2 / 3)], 10.0, 9.0, 0.02) - (1.96 / 3 + 0.16 * 2 / 3)) < 1e-9)
    # 17. the cap: 6 names placed at 09:35 the same day -> the 6th blocked; a name cancelled at minute 40 frees its
    #     slot for a 7th placed at minute 50; a position from an earlier day exiting at today's open does not count
    tl = [{"key": f"d1|{i}", "E": "2020-01-02", "list_rank": i, "placed_m": 5, "cancel_m": None, "filled": True, "exit_date": "2020-01-10", "exit_at_open": True} for i in range(1, 6)]
    tl.append({"key": "d1|6", "E": "2020-01-02", "list_rank": 6, "placed_m": 5, "cancel_m": None, "filled": True, "exit_date": "2020-01-20", "exit_at_open": False})
    tl.append({"key": "d1|7", "E": "2020-01-02", "list_rank": 7, "placed_m": 50, "cancel_m": 385, "filled": False, "exit_date": None, "exit_at_open": False})
    tl[0].update(filled=False, cancel_m=40, exit_date=None)
    tl.append({"key": "d2|1", "E": "2020-01-10", "list_rank": 1, "placed_m": 5, "cancel_m": None, "filled": True, "exit_date": "2020-01-15", "exit_at_open": False})
    tl.append({"key": "d2|2", "E": "2020-01-10", "list_rank": 2, "placed_m": 5, "cancel_m": None, "filled": True, "exit_date": "2020-01-15", "exit_at_open": False})
    tl.append({"key": "d3|1", "E": "2020-01-13", "list_rank": 1, "placed_m": 5, "cancel_m": None, "filled": True, "exit_date": None, "exit_at_open": False})
    tl.append({"key": "d3|2", "E": "2020-01-13", "list_rank": 2, "placed_m": 5, "cancel_m": None, "filled": True, "exit_date": None, "exit_at_open": False})
    tl.append({"key": "d3|3", "E": "2020-01-13", "list_rank": 3, "placed_m": 5, "cancel_m": None, "filled": True, "exit_date": None, "exit_at_open": False})
    cap = apply_cap(tl)
    a = cap["admitted"]
    # day 1: names 1-5 at minute 5 fill the 5 slots, name 6 (rank 6, same minute) is BLOCKED and so never holds a slot;
    # name 1's cancel at minute 40 frees a slot for name 7 at minute 50. Day 2 (01-10): names 2-5 exit at that open
    # (freed before the first tick) -> 0 carried -> both day-2 names admitted. Day 3 (01-13): the two day-2 names
    # (exit 01-15) -> 2 carried -> all three day-3 names admitted (2 + 3 = 5). Blocked in all: 1.
    # (The first hand count put name 6 in the carried set — a blocked name holds nothing; the dry run caught it.)
    chk("the cap: 5 of 6 same-minute names admitted in rank order (a blocked name holds no slot); a cancel frees its slot "
        "the same day; an exit at today's open frees the slot before the first tick; 2 carried + 3 new = 5 admitted",
        [a[f"d1|{i}"] for i in range(1, 8)] == [True, True, True, True, True, False, True] and a["d2|1"] and a["d2|2"]
        and a["d3|1"] and a["d3|2"] and a["d3|3"] and cap["blocked"] == 1, json.dumps(a))
    # a 4th day-3 name at minute 5 is the 6th slot -> blocked
    tl.append({"key": "d3|4", "E": "2020-01-13", "list_rank": 4, "placed_m": 5, "cancel_m": None, "filled": True, "exit_date": None, "exit_at_open": False})
    cap2 = apply_cap(tl)
    chk("the cap: a 4th day-3 name (2 carried + 4 new) is the 6th slot -> blocked", cap2["admitted"]["d3|4"] is False and cap2["blocked"] == 2)

    # ── review 2026-11-01: the book (guard, free dates, same-minute order, the adverse row, the lane's safeguards) ──
    def T(key, E, ticker, rank, m, *, filled=True, cancel_m=None, free_date=None, free_minute=None, at_open=False,
          legs=(), total_r=-1.0, fill=10.0, stop=9.0):
        return {"key": key, "E": E, "ticker": ticker, "list_rank": rank, "placed_m": m, "cancel_m": cancel_m, "filled": filled,
                "free_date": free_date, "free_minute": free_minute, "exit_at_open": at_open, "legs": list(legs),
                "total_r": total_r, "f_risk": risk_fraction(fill, stop)}
    # 18. the ticker guard (entry_pipeline step 1b): AAA held 01-02 .. 01-10 (stop on the 10th, end of day) blocks AAA on
    #     01-06 and on 01-10, not on 01-13; BBB's day-0 stop (minute 100) does not block BBB the next day; CCC's trail
    #     sale at 01-08's open frees it before that day's first tick; a 2/3-remaining DDD (a third sold 01-07, the rest
    #     held to 01-20) still blocks DDD on 01-09
    g = [T("x", "2020-01-02", "AAA", 1, 5, free_date="2020-01-10"), T("y", "2020-01-06", "AAA", 1, 5), T("z", "2020-01-10", "AAA", 1, 5),
         T("w", "2020-01-13", "AAA", 1, 5, free_date="2020-01-20"),
         T("p", "2020-01-02", "BBB", 2, 5, free_date="2020-01-02", free_minute=100), T("q", "2020-01-03", "BBB", 1, 5, free_date="2020-01-09"),
         T("t", "2020-01-02", "CCC", 3, 5, free_date="2020-01-08", at_open=True), T("u", "2020-01-08", "CCC", 1, 5, free_date="2020-01-15"),
         T("dd", "2020-01-02", "DDD", 4, 5, free_date="2020-01-20", legs=[("2020-01-07", None, "partial_r", 0.667)]),
         T("de", "2020-01-09", "DDD", 2, 5)]
    bk = apply_book(g, slots=None, safeguards=False)
    a, w = bk["admitted"], bk["reason"]
    chk("the ticker guard: a held name blocks its re-buy (01-06, 01-10 end-of-day) and frees on 01-13; a day-0 exit does not "
        "block the next day; a trail sale at the open frees before the first tick; 2/3 remaining still blocks",
        a["x"] and not a["y"] and not a["z"] and a["w"] and w["y"] == BLOCK_TICKER and w["z"] == BLOCK_TICKER
        and a["p"] and a["q"] and a["t"] and a["u"] and a["dd"] and not a["de"] and w["de"] == BLOCK_TICKER
        and bk["blocked"] == {BLOCK_TICKER: 3}, json.dumps({"adm": a, "why": w}))
    # 19. a DEGRADED / censored walk frees its slot at its last bar (free_date), not at the data end: five 01-02 fills
    #     freed 02-03 block a 6th name on 02-03 (end of day) and admit it on 02-04
    g = [T(f"a{i}", "2020-01-02", f"T{i}", i, 5, free_date="2020-02-03") for i in range(1, 6)]
    g += [T("b", "2020-02-03", "T9", 1, 5), T("c", "2020-02-04", "T9", 1, 5)]
    bk = apply_book(g, slots=5, safeguards=False)
    chk("a degraded / censored walk frees its slot at its last bar: the 6th name blocked on that day, admitted the day after",
        bk["admitted"]["b"] is False and bk["reason"]["b"] == BLOCK_CAP and bk["admitted"]["c"] is True, json.dumps(bk["reason"]))
    # 20. the same-minute order (the tick walks names in list order): ranks 1,3,4,5,6 placed at 09:35 (rank 3 unfilled,
    #     cancelled at tick 40); rank 2 placed at tick 40 is processed BEFORE rank 3's cancel -> 5 held -> blocked;
    #     rank 7 at tick 40 after it -> 4 held -> admitted; rank 8 at tick 41 -> 5 again -> blocked
    g = [T("r1", "2020-01-02", "R1", 1, 5, free_date="2020-01-09"), T("r3", "2020-01-02", "R3", 3, 5, filled=False, cancel_m=40),
         T("r4", "2020-01-02", "R4", 4, 5, free_date="2020-01-09"), T("r5", "2020-01-02", "R5", 5, 5, free_date="2020-01-09"),
         T("r6", "2020-01-02", "R6", 6, 5, free_date="2020-01-09"), T("r2", "2020-01-02", "R2", 2, 40, free_date="2020-01-09"),
         T("r7", "2020-01-02", "R7", 7, 40, free_date="2020-01-09"), T("r8", "2020-01-02", "R8", 8, 41, free_date="2020-01-09")]
    bk = apply_book(g, slots=5, safeguards=False)
    chk("a cancel at tick m frees the slot only for LOWER-ranked names placed at m (list order): rank 2 blocked, rank 7 admitted, rank 8 blocked",
        bk["admitted"]["r2"] is False and bk["admitted"]["r7"] is True and bk["admitted"]["r8"] is False, json.dumps(bk["admitted"]))
    # 21. a day-0 exit at minute 50 frees its slot for placements AFTER minute 50: rank 6 at tick 50 blocked, rank 7 at 51 admitted
    g = [T("k1", "2020-01-02", "K1", 1, 5, free_date="2020-01-02", free_minute=50)]
    g += [T(f"k{i}", "2020-01-02", f"K{i}", i, 5, free_date="2020-01-09") for i in range(2, 6)]
    g += [T("k6", "2020-01-02", "K6", 6, 50), T("k7", "2020-01-02", "K7", 7, 51)]
    bk = apply_book(g, slots=5, safeguards=False)
    chk("a day-0 stop at minute 50 frees its slot from minute 51: the 6th name at tick 50 blocked, at tick 51 admitted",
        bk["admitted"]["k6"] is False and bk["admitted"]["k7"] is True, json.dumps(bk["admitted"]))
    # 22. the ADVERSE fill-minute row (review HIGH 4): case 5's shape (fill 10.10, placed stop 9.90, the fill bar's low
    #     9.80 -> stop lowered to 9.80; stopped next session at 9.80): primary R -1.000 at 0c, -1.1333 at 2c; the
    #     adverse reading (stopped at the placed 9.90 inside the fill minute, R against the placed risk 0.20): -1.000
    #     at 0c, -1.200 at 2c. Case 1's fill (bar low 10.05 >= 9.90) carries no adverse flag.
    tr5 = simulate_entry(d5, list_level=10.0, adr20=0.05, vol_bar=vb)
    tr1 = simulate_entry(flat_day(px=10.0, vol=1000, over={2: (10.0, 10.10, 10.0, 10.05, 1000), 3: (10.0, 10.05, 9.90, 10.0, 1000),
                                                          7: (10.05, 10.20, 10.05, 10.15, 1000)}), list_level=10.0, adr20=0.05, vol_bar=vb)
    rec = {"E": "2020-01-02", "raw_factor": 1.0, "placed_stop": 9.90, "adverse_stop": tr5["adverse_stop"], "events": [(1, "stop", 9.80, 1.0)]}
    _book_costs(rec, 10.10, 9.80, {"partial_minute": None, "exit_minute": None}, 7, lambda j: date(2020, 1, 3))
    chk("the adverse fill-minute row: a fill bar low under the placed stop is flagged (case 5) and not otherwise (case 1); "
        "R -1.000/-1.133 (0c/2c) primary vs -1.000/-1.200 adverse at the placed stop; f = 0.2 x 2.97% = 0.0059",
        tr5["adverse_stop"] is True and tr1["adverse_stop"] is False and abs(rec["r_0c"] + 1.0) < 1e-9
        and abs(rec["r_2c"] + 1.1333333333) < 1e-9 and abs(rec["r_adv_0c"] + 1.0) < 1e-9 and abs(rec["r_adv_2c"] + 1.2) < 1e-9
        and rec["legs"] == [("2020-01-03", None, "stop", rec["r_2c"])] and abs(rec["f_risk"] - 0.2 * 0.30 / 10.10) < 1e-12,
        json.dumps({k: rec[k] for k in ("r_0c", "r_2c", "r_adv_0c", "r_adv_2c", "legs", "f_risk")}))
    # 23. the lane's DAILY-LOSS limit: a 10%-wide stop risks the full 2% (f = 0.02), a 3%-wide one 0.6%; one full -1R stop
    #     on 01-03 (a daily bar: counted from the first tick) trips the 2% limit for the rest of 01-03, not on 01-06; a
    #     minute-timed day-0 stop at minute 100 blocks a tick-101 placement, not a tick-50 one; a 0.6% loss trips nothing
    chk("risk fractions: 10%-wide stop -> 0.02 (the 2% cap), 3%-wide -> 0.006 (the 20% notional cap binds)",
        abs(risk_fraction(10.0, 9.0) - 0.02) < 1e-12 and abs(risk_fraction(10.0, 9.7) - 0.006) < 1e-12)
    g = [T("L", "2020-01-02", "LA", 1, 5, free_date="2020-01-03", legs=[("2020-01-03", None, "stop", -1.0)], total_r=-1.0),
         T("C", "2020-01-03", "CA", 1, 5, free_date="2020-01-09"), T("D", "2020-01-06", "DA", 1, 5, free_date="2020-01-09"),
         T("M", "2020-01-07", "MA", 1, 5, free_date="2020-01-07", free_minute=100, legs=[("2020-01-07", 100, "day0_stop", -1.0)], total_r=-1.0),
         T("N50", "2020-01-07", "NA", 2, 50, free_date="2020-01-15"), T("N101", "2020-01-07", "NB", 3, 101, free_date="2020-01-15"),
         T("S", "2020-01-08", "SA", 1, 5, free_date="2020-01-09", legs=[("2020-01-09", None, "stop", -1.0)], total_r=-1.0, stop=9.7),
         T("V", "2020-01-09", "VA", 1, 5, free_date="2020-01-15")]
    bk = apply_book(g, slots=5, safeguards=True)
    a, w = bk["admitted"], bk["reason"]
    chk("the daily-loss limit: one full-size -1R stop (daily bar, from the first tick) blocks the rest of that day and not the next; "
        "a day-0 stop at minute 100 blocks tick 101 not tick 50; a 0.6%-risk loss trips nothing",
        a["L"] and not a["C"] and w["C"] == BLOCK_DAILY and a["D"] and a["M"] and a["N50"] and not a["N101"] and w["N101"] == BLOCK_DAILY
        and a["S"] and a["V"], json.dumps({"adm": a, "why": w}))
    # 24. the CIRCUIT BREAKER: ten -1R stops (3% wide: 0.6% of equity each, so the daily-loss limit never trips) closing
    #     one a session (daily bars) -> the next placement on the 10th loss's close day and on the next session are
    #     blocked; the session after that admitted. A +2R partial profit on a still-open trade dated inside the window
    #     breaks the streak (a banked partial is a win).
    wk = [d for d in (date(2020, 2, 3) + timedelta(days=i) for i in range(30)) if d.weekday() < 5]
    def streak(with_partial: bool):
        gg = []
        for i in range(10):
            e_, f_ = wk[i].isoformat(), wk[i + 1].isoformat()
            gg.append(T(f"s{i}", e_, f"S{i}", 1, 5, free_date=f_, legs=[(f_, None, "stop", -1.0)], total_r=-1.0, stop=9.7))
        if with_partial:
            gg.append(T("win", wk[4].isoformat(), "WIN", 2, 5, free_date=wk[15].isoformat(),
                        legs=[(wk[7].isoformat(), None, "partial_r", 0.667)], total_r=0.5))
        gg += [T("n11", wk[10].isoformat(), "N11", 1, 5, free_date=wk[15].isoformat()),
               T("n12", wk[11].isoformat(), "N12", 1, 5, free_date=wk[15].isoformat()),
               T("n13", wk[12].isoformat(), "N13", 1, 5, free_date=wk[15].isoformat())]
        return apply_book(gg, slots=5, safeguards=True)
    b0, b1 = streak(False), streak(True)
    # ... and the cooldown is ONE session, read from the full session list: with no placement on the session after the
    # 10th loss's close, a placement two sessions after it is admitted (the days that placed orders are not the calendar)
    def streak_gap():
        gg = []
        for i in range(10):
            e_, f_ = wk[i].isoformat(), wk[i + 1].isoformat()
            gg.append(T(f"s{i}", e_, f"S{i}", 1, 5, free_date=f_, legs=[(f_, None, "stop", -1.0)], total_r=-1.0, stop=9.7))
        gg.append(T("n13", wk[12].isoformat(), "N13", 1, 5, free_date=wk[15].isoformat()))
        return apply_book(gg, slots=5, safeguards=True, sessions=[d.isoformat() for d in wk])
    b2 = streak_gap()
    chk(f"the breaker's cooldown is one SESSION of the calendar, not of the placement days: no placement on {wk[11]}, a placement on "
        f"{wk[12]} two sessions after the 10th loss's close is admitted",
        b2["admitted"]["n13"] is True, json.dumps(b2["reason"]))
    chk(f"the circuit breaker: 10 straight losses -> blocked on the 10th loss's day ({wk[10]}) and the next session, admitted on "
        f"{wk[12]}; a partial profit inside the window breaks the streak",
        b0["admitted"]["n11"] is False and b0["reason"]["n11"] == BLOCK_BREAKER and b0["admitted"]["n12"] is False
        and b0["admitted"]["n13"] is True and b1["admitted"]["n11"] is True and b1["admitted"]["n12"] is True,
        json.dumps({"no_partial": b0["reason"], "with_partial": b1["reason"]}))
    # 25. the coverage rule: a requested pair held in a store is fine; one in the pull's _failed.psv is `unfetchable`
    #     (counted, bounded at 2%); one in neither is MISSING and refuses; 3 unfetchable of 100 refuses too
    fake_index = [(Path("/x"), {("2020-01-02", "HELD"): "ok", ("2020-01-02", "EMPTY"): "empty"}, {"2020-01-02": Path("/x/2020-01-02.psv.gz")})]
    req = [{"ticker": "HELD", "session_date": "2020-01-02"}, {"ticker": "EMPTY", "session_date": "2020-01-02"},
           {"ticker": "GONE", "session_date": "2020-01-02"}, {"ticker": "LOST", "session_date": "2020-01-02"}]
    cv = coverage(fake_index, req, failed={("2020-01-02", "GONE")})
    big_req = [{"ticker": f"U{i}", "session_date": "2020-01-02"} for i in range(100)]
    cv2 = coverage(fake_index, big_req, failed={("2020-01-02", f"U{i}") for i in range(3)} | {("2020-01-02", f"U{i}") for i in range(3, 100)})
    chk("the coverage rule: held 2, unfetchable 1, missing 1 -> refuses twice (a missing row; 1 of 4 over the 2% bound); 100 unfetchable of 100 -> refuses on the bound",
        cv["held"] == 2 and cv["unfetchable"] == 1 and cv["missing"] == 1 and len(coverage_problems(cv, 4)) == 2
        and cv2["missing"] == 0 and cv2["unfetchable"] == 100 and len(coverage_problems(cv2, 100)) == 1, json.dumps({k: cv[k] for k in ("held", "unfetchable", "missing")}))
    # 26. the decisive cutoff on E: a 200-session calendar -> E <= session index 200 - 1 - 121 = 78
    class _D: pass
    fake = _D(); fake.D = _D(); fake.D.cal = [date(2020, 1, 1) + timedelta(days=i) for i in range(200)]
    chk("the decisive cutoff: the last E whose 120-session walk plus the trail's next open fits before the data's end (index 78 of 200)",
        e_cutoff(fake) == fake.D.cal[78])
    # 27. the raw-close pull's loader: a 2025 row refuses; a sidecar naming another request refuses; a clean file loads
    tmp = SCRATCH / "dry" / "rawpull"
    tmp.mkdir(parents=True, exist_ok=True)
    rq = tmp / "raw_close_request.tsv"; rq.write_text("ticker\tfirst_date\tlast_date\tn_list_rows\nAAA\t2023-01-03\t2023-01-04\t1\n")
    okf, okm = tmp / "ok.csv.gz", tmp / "ok.meta.json"
    with gzip.open(okf, "wt") as fh:
        fh.write("AAA,2023-01-03,1.50\nAAA,2023-01-04,1.60\n")
    okm.write_text(json.dumps({"adjustment": "raw", "request_sha256": sha(rq)}))
    badf = tmp / "bad.csv.gz"
    with gzip.open(badf, "wt") as fh:
        fh.write("AAA,2023-01-03,1.50\nAAA,2025-01-02,9.00\n")
    badm = tmp / "bad.meta.json"; badm.write_text(json.dumps({"adjustment": "raw", "request_sha256": "0" * 64}))
    got, _meta = load_raw_pull(okf, okm, rq)
    refused_seal = refused_meta = False
    try:
        load_raw_pull(badf, okm, rq)
    except SystemExit:
        refused_seal = True
    try:
        load_raw_pull(okf, badm, rq)
    except SystemExit:
        refused_meta = True
    chk("the raw-close loader: a clean pull loads (2 rows); a row dated 2025 refuses; a sidecar naming another request refuses",
        got == {("AAA", "2023-01-03"): 1.5, ("AAA", "2023-01-04"): 1.6} and refused_seal and refused_meta)
    return out


def fuzz_exit(n: int = 600, seed: int = 1101) -> dict:
    """Random daily + minute paths: the stepper equals walk_pp event for event on every one (a mismatch raises)."""
    rng = np.random.default_rng(seed)
    kinds = Counter()
    for _ in range(n):
        fill = float(rng.uniform(5, 200))
        risk = fill * float(rng.uniform(0.005, 0.08))
        stop = fill - risk
        n_min = int(rng.integers(0, 380))
        fm = int(rng.integers(0, 389))
        mins = []
        px = fill
        for m in range(fm + 1, min(390, fm + 1 + n_min)):
            o = px * (1 + rng.normal(0, 0.004))
            h = o * (1 + abs(rng.normal(0, 0.006)))
            l = o * (1 - abs(rng.normal(0, 0.006)))
            px = float(rng.uniform(l, h))
            mins.append((m, o, h, l))
        d0 = ppr.day0_facts(mins, fill=fill, stop=stop, fill_minute=fm)
        nb = int(rng.integers(0, 60))
        closes_before = list(fill * (1 + rng.normal(0, 0.02, size=nb)).cumprod() if nb else [])
        closes_before = (closes_before + [fill])[-25:] if rng.random() < 0.9 else closes_before + [fill]
        nf = int(rng.integers(0, 140))
        o = []; h = []; l = []; c = []
        p = fill
        for _j in range(nf):
            oj = p * (1 + rng.normal(0, 0.02))
            hj = oj * (1 + abs(rng.normal(0, 0.03)))
            lj = oj * (1 - abs(rng.normal(0, 0.03)))
            cj = float(rng.uniform(lj, hj))
            o.append(oj); h.append(hj); l.append(lj); c.append(cj)
            p = cj
        fwd = cb.daily_bars_from_arrays([date(2020, 1, 1) + timedelta(days=i) for i in range(nf)], o, h, l, c, [1.0] * nf)
        res = exit_one(fill=fill, stop=stop, day0=d0, closes_before=closes_before, fwd=fwd, adr20=0.05)
        kinds[res["status"]] += 1
    return dict(kinds)


def fuzz_no_lookahead(n: int = 60, seed: int = 7) -> dict:
    """No look-ahead in the entry loop: on random days, the PLACEMENT minute (and the cancel minute of a never-filled
    order) is unchanged when every bar from that minute on is replaced by garbage — the tick at m reads bars <= m-1
    only. Returns the tally of what was checked."""
    rng = np.random.default_rng(seed)
    tally = Counter()
    for _ in range(n):
        px = float(rng.uniform(5, 100))
        d = {}
        p = px
        for m in range(390):
            o = p * (1 + rng.normal(0, 0.002)); hh = o * (1 + abs(rng.normal(0, 0.004))); ll = o * (1 - abs(rng.normal(0, 0.004)))
            cc = float(rng.uniform(ll, hh)); d[m] = (o, hh, ll, cc, float(rng.uniform(100, 5000)))
            p = cc
        level = px * float(rng.uniform(0.99, 1.02))
        vb = float(rng.uniform(1e5, 1.5e6))
        tr = simulate_entry(_day(d), list_level=level, adr20=0.06, vol_bar=vb)
        if tr["placed_m"] is not None:
            d2 = dict(d)
            for m in range(tr["placed_m"], 390):
                d2[m] = (1e6, 1e6, 1e6, 1e6, 1e9)
            tr2 = simulate_entry(_day(d2), list_level=level, adr20=0.06, vol_bar=vb)
            assert tr2["placed_m"] == tr["placed_m"], (tr["placed_m"], tr2["placed_m"])
            tally["placement_checked"] += 1
        if tr["outcome"] == "cancelled" and tr["cancel_m"] is not None and tr["cancel_m"] < bve.EOD_MINUTE:
            d2 = dict(d)
            for m in range(tr["cancel_m"], 390):
                d2[m] = (1e6, 1e6, 1e6, 1e6, 1e9)
            tr2 = simulate_entry(_day(d2), list_level=level, adr20=0.06, vol_bar=vb)
            assert tr2["cancel_m"] == tr["cancel_m"] and reason_key(tr2["reason"]) == reason_key(tr["reason"]), (tr, tr2)
            tally["cancel_checked"] += 1
        tally[tr["outcome"]] += 1
    return dict(tally)


W_MEANS = (0.30, 0.50, 0.75, 1.05)           # the working populations calibrated: his replay (+1.05) and three weaker ones
CAL_NS = (100, 300, 700, 1000, 2000, 3000)


def load_anchor() -> tuple:
    """The empirical anchor (R, fill month) of every structural breakout 2017-21 under this exact exit
    (`cb702_pre_v2/out/trades_pre_exitpb.tsv.gz`, C0 / orh5 / tl / pp / mature / first break), saved beside this
    file as two parallel arrays and pinned."""
    r = np.load(HERE / "empirical_pp_c0_r.npy")
    months = np.load(HERE / "empirical_pp_c0_months.npy")
    assert len(r) == len(months)
    return r, months


def calibration(out_path: Path, reps: int = 300, seed: int = 702) -> list:
    """The bar on synthetic populations (registration §6.3). N = the empirical anchor, drawn WITH each trade's real
    fill month (review MEDIUM 6: random months understated the month clustering 2.75x); W(mu) = N's losers as they
    are, N's winners scaled by one factor so the mean lands on mu, for mu in W_MEANS (+1.05 = his holdings replay);
    M = 12% W(1.05) + 88% N. Rows: population x n -> verdict rates; then the smallest W mean that PASSES > 80% at
    each n."""
    emp, months = load_anchor()
    rng = np.random.default_rng(seed)
    win = emp > 0
    sum_w, sum_l, N = float(emp[win].sum()), float(emp[~win].sum()), len(emp)
    scales = {mu: (mu * N - sum_l) / sum_w for mu in W_MEANS}

    def draw(n: int, kind: str, mu: float = 1.05):
        idx = rng.integers(0, N, size=n)
        r = emp[idx].copy()
        mo = months[idx]
        if kind == "W":
            r = np.where(r > 0, r * scales[mu], r)
        elif kind == "M":
            w = (rng.random(n) < 0.12) & (r > 0)
            r = np.where(w, r * scales[1.05], r)
        return r, [str(x) for x in mo]
    anchors = {"N": {"mean": float(emp.mean()), "win": float(win.mean()), "ge3": float((emp >= 3).mean()),
                     "ge5": float((emp >= 5).mean()), "ge10": float((emp >= 10).mean()), "n": int(N), "months": int(len(set(months.tolist())))}}
    for mu in W_MEANS:
        big = np.where(emp > 0, emp * scales[mu], emp)
        anchors[f"W{mu:.2f}"] = {"mean": float(big.mean()), "win": float(win.mean()), "ge3": float((big >= 3).mean()),
                                 "ge5": float((big >= 5).mean()), "ge10": float((big >= 10).mean()), "scale": float(scales[mu])}
    bigm, _ = draw(200_000, "M")
    anchors["M"] = {"mean": float(bigm.mean()), "win": float((bigm > 0).mean()), "ge3": float((bigm >= 3).mean()),
                    "ge5": float((bigm >= 5).mean()), "ge10": float((bigm >= 10).mean())}
    pops = [("N (every structural breakout, pp)", "N", None)] + [(f"W {mu:+.2f}R (winners x {scales[mu]:.2f})", "W", mu) for mu in W_MEANS] \
        + [("M (12% W+1.05 + 88% N)", "M", None)]
    rows = []
    for name, kind, mu in pops:
        for n in CAL_NS:
            vs = Counter()
            for r_i in range(reps):
                r, mo = draw(n, kind, mu or 1.05)
                s = stats(r, mo, key=f"calib|{name}|{n}|{r_i}")
                vs[verdict(s)[0]] += 1
            rows.append({"population": name, "kind": kind, "mu": mu, "n": n, **{k: v / reps for k, v in vs.items()}})
    L = [f"CALIBRATION of the bar (PASS: n >= {N_FLOOR}, CI lo > 0, >= 3R share >= {TAIL_SHARE:.0%}; FAIL: n >= {N_FLOOR}, CI hi < +{FAIL_MEAN_REF}, "
         f">= 3R share < {TAIL_SHARE:.0%}); {reps} replicates each; months = each drawn trade's REAL fill month (the block bootstrap's blocks)"]
    for k, v in anchors.items():
        L.append(f"{k} anchor: {v}")
    L.append(f"{'population':40s} {'n':>5s}  {'PASS':>6s} {'FAIL':>6s} {'CANT':>6s}")
    for r in rows:
        L.append(f"{r['population']:40s} {r['n']:5d}  {r.get('PASS', 0):6.1%} {r.get('FAIL', 0):6.1%} {r.get(CANT, 0):6.1%}")
    L.append("")
    L.append("the smallest W mean that PASSES more than 80% of the time, per n (the bar's power on a working population):")
    for n in CAL_NS:
        ok = [r["mu"] for r in rows if r["kind"] == "W" and r["n"] == n and r.get("PASS", 0) > 0.80]
        L.append(f"  n {n:5d}: {('+%.2fR' % min(ok)) if ok else 'none of ' + ', '.join('%+.2f' % m for m in W_MEANS)}")
    out_path.write_text("\n".join(L) + "\n")
    print("\n".join(L), flush=True)
    return rows


def run_dryrun(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    L = []
    cases = dry_cases()
    for name, ok, detail in cases:
        L.append(f"[{'ok' if ok else 'FAIL'}] {name}" + ("" if ok else f"\n      {detail}"))
    kinds = fuzz_exit()
    L.append(f"[ok] fuzz: {sum(kinds.values())} random day-0 + daily paths, the stepper == walk_pp event for event: {kinds}")
    la = fuzz_no_lookahead()
    L.append(f"[ok] no look-ahead in the entry loop on random days: {la}")
    # the live `day0_facts` port equals the recorder's on random minutes (both are called; a drift would show here)
    rng = np.random.default_rng(3)
    for _ in range(200):
        fill = 20.0; stop = 19.0; fm = int(rng.integers(0, 300))
        mins = []
        p = fill
        for m in range(fm + 1, 390):
            o = p * (1 + rng.normal(0, 0.003)); h = o * (1 + abs(rng.normal(0, 0.01))); l = o * (1 - abs(rng.normal(0, 0.01)))
            mins.append((m, o, h, l, float(rng.uniform(l, h)), 1.0)); p = mins[-1][4]
        a = ppr.day0_facts([(m, o, h, l) for m, o, h, l, _c, _v in mins], fill=fill, stop=stop, fill_minute=fm)
        mb = cb.minute_bars_from_lists([x[0] for x in mins], [x[1] for x in mins], [x[2] for x in mins], [x[3] for x in mins], [x[4] for x in mins], [x[5] for x in mins])
        b = cpp.day0_facts(mb, fill=fill, stop=stop, fill_minute=fm)
        assert a == b, (a, b)
    L.append("[ok] breakout_pp_rules.day0_facts == consolidation_breakout_pp.day0_facts on 200 random minute days")
    calib = calibration(out_dir / "calibration.txt")
    L.append(f"[ok] calibration written: {out_dir / 'calibration.txt'}")
    n_fail = sum(1 for _n, ok, _d in cases if not ok)
    L.append(f"DRY RUN {'COMPLETE' if not n_fail else 'FAILED'}: {len(cases)} hand-computed cases, {n_fail} failed")
    txt = "\n".join(L) + "\n"
    (out_dir / "dryrun.txt").write_text(txt)
    print(txt, flush=True)
    return {"cases": len(cases), "failed": n_fail, "fuzz": kinds, "calibration_rows": len(calib)}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 11b. Parity: the vectorised pool arithmetic and the copied `scan_members` against the LIVE functions, on the stores
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def run_parity(out_dir: Path, n_tickers: int = 300, n_bars: int = 40, n_nights: int = 3, seed: int = 5) -> dict:
    """Review MEDIUM 8 (2026-11-01): `ticker_facts` is asserted equal to `cb._dollar_vol_median`,
    `bv.rs_returns_contiguous` and `bv.history_ok` on sampled bars of sampled tickers, and `night_members` (the copy)
    to `breakout_v1_list.scan_members` (the live function, called on the same bars sliced to the night) on sampled
    watch nights — member for member (ticker, r21/r63/r126, listable, history, type) and on the shared counts. Both
    eras. Writes out/parity.txt (pinned); any difference FAILS the stage."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    L, bad_total = [], 0
    for era in ("A", "B"):
        S = load_store(era)
        D = S.D
        ks = rng.choice(len(D.tickers), min(n_tickers, len(D.tickers)), replace=False)
        checked = bad = 0
        for k in ks:
            f = ticker_facts(S, int(k))
            bars, cidx = runner.bars_for(D, int(k))
            n = len(bars)
            for i in rng.choice(n, min(n, n_bars), replace=False):
                i = int(i); checked += 1
                if i + 1 >= cb.DOLLAR_VOL_WINDOW:
                    a = cb._dollar_vol_median(bars, i); b = f["dv"][i]
                    if not np.isclose(a, b, rtol=1e-12, atol=0):
                        bad += 1; L.append(f"  dv {era} {D.tickers[k]} {i}: live {a} vs {b}")
                r = bv.rs_returns_contiguous(bars, i, cidx)
                for hz, x in zip(bv.RS_HORIZONS, r):
                    y = f[f"r{hz}"][i]; y = None if np.isnan(y) else float(y)
                    if (x is None) != (y is None) or (x is not None and not np.isclose(x, y, rtol=1e-12)):
                        bad += 1; L.append(f"  r{hz} {era} {D.tickers[k]} {i}: live {x} vs {y}")
                if bv.history_ok(i, cidx) != bool(f["hist"][i]):
                    bad += 1; L.append(f"  history {era} {D.tickers[k]} {i}")
        L.append(f"[{'ok' if not bad else 'FAIL'}] era {era}: ticker_facts == live per-name arithmetic on {checked:,} sampled bars "
                 f"of {len(ks)} tickers ({bad} differences)")
        bad_total += bad
        # the nightly members: the copy vs the live scan_members on sampled watch nights
        facts = [ticker_facts(S, k) for k in range(len(D.tickers))]
        row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
        order = np.argsort(D.ci, kind="stable")
        rows_at = _RowsAt(order, D.ci[order], row_tid)
        d_lo = max(E_FIRST - timedelta(days=10), D.cal[0]) if era == "A" else ERA_B_D_FIRST
        d_hi = ERA_A_D_LAST if era == "A" else E_LAST
        nights = [ci for ci, d in enumerate(D.cal) if d_lo <= d <= d_hi and ci + 1 < len(D.cal)]
        for ci in rng.choice(nights, min(n_nights, len(nights)), replace=False):
            ci = int(ci)
            mine, counts = night_members(S, facts, ci, rows_at)
            series, types, unapplied = {}, {}, set()
            for k, i in rows_at.get(ci, []):
                t = D.tickers[k]
                bars, cidx = runner.bars_for(D, k)
                li = i - facts[k]["a"]
                # the LIVE basis: `mi_daily_closes` holds each day's row as printed (never re-adjusted; a name across an
                # unapplied split sits out), so `bars.c[D]` is the RAW close there. The stores are adjusted as of 2026:
                # the night's series is put on the raw basis (prices x the raw factor at D, volume / it — the dollar
                # volume is unchanged) before the live function reads it; `night_members` reads the raw close directly.
                f = float(S.raw_factor[i])
                b = bars.slice(0, li + 1)
                series[t] = (cb.DailyBars(b.dates, b.o * f, b.h * f, b.l * f, b.c * f, b.v / f), cidx[:li + 1])
                st = S.types.get(t)
                types[t] = (st, S.etv_names.get(t))
                if facts[k]["brk"][li]:
                    unapplied.add(t)
            live = bvl.scan_members(series, today_ci=ci, types=types, unapplied=unapplied)
            A_ = {m["ticker"]: (m["r21"], m["r63"], m["r126"], m["listable"], m["history"], m["st"]) for m in mine}
            B_ = {m["ticker"]: (m["r21"], m["r63"], m["r126"], m["listable"], m["history"], m["security_type"]) for m in live["members"]}
            diff = len(set(A_) ^ set(B_))
            for t in set(A_) & set(B_):
                x, y = A_[t], B_[t]
                if x[3] != y[3] or x[4] != y[4] or x[5] != y[5] or any(
                        (u is None) != (v is None) or (u is not None and not np.isclose(u, v, rtol=1e-9)) for u, v in zip(x[:3], y[:3])):
                    diff += 1
                    if diff <= 5:
                        L.append(f"  member {era} {D.cal[ci]} {t}: mine {x} vs live {y}")
            for t in sorted(set(A_) ^ set(B_))[:5]:
                L.append(f"  only in {'mine' if t in A_ else 'live'} {era} {D.cal[ci]}: {t}")
            shared = {k: v for k, v in live["counts"].items() if k not in ("split_unapplied", "no_bar_today")}
            mine_counts = {k: v for k, v in counts.items() if k in shared}
            cdiff = {k: (shared[k], counts.get(k, 0)) for k in shared if shared[k] != counts.get(k, 0)}
            cdiff.update({"identity_break_vs_split_unapplied": (live["counts"].get("split_unapplied", 0), counts.get("identity_break", 0))}
                         if live["counts"].get("split_unapplied", 0) != counts.get("identity_break", 0) else {})
            ok = diff == 0 and not cdiff
            bad_total += 0 if ok else 1
            L.append(f"[{'ok' if ok else 'FAIL'}] era {era} night {D.cal[ci]}: night_members == scan_members — {len(A_)} members vs "
                     f"{len(B_)} live, {diff} member differences, count differences {cdiff or 'none'}")
        del S, facts
    L.append(f"PARITY {'COMPLETE' if not bad_total else 'FAILED'}: {bad_total} differences")
    (out_dir / "parity.txt").write_text("\n".join(L) + "\n")
    print("\n".join(L), flush=True)
    return {"bad": bad_total}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 12. CLI
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stage", choices=["population", "request", "parity", "dryrun", "pins", "coverage", "walk"])
    ap.add_argument("era", nargs="?", choices=["A", "B", "body", "footer"], help="population: which store; pins: body | footer")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--force-unfrozen", action="store_true", help="walk: skip the freeze check (a SMOKE run on a few days only; never the registered run)")
    ap.add_argument("--limit-days", type=int, default=None, help="walk --force-unfrozen only: the first N breakout days")
    ap.add_argument("--smoke-from", default=None, help="walk --force-unfrozen only: start at this breakout day (ISO)")
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    if args.stage == "population":
        if args.era not in ("A", "B"):
            ap.error("population needs an era: A | B")
        run_population(args.era, out_dir)
    elif args.stage == "request":
        run_request(out_dir)
    elif args.stage == "parity":
        r = run_parity(out_dir)
        return 1 if r["bad"] else 0
    elif args.stage == "dryrun":
        r = run_dryrun(out_dir)
        return 1 if r["failed"] else 0
    elif args.stage == "pins":
        print("\n".join(pins(out_dir, "footer" if args.era == "footer" else "body")))
    elif args.stage == "coverage":
        r = run_coverage(out_dir)
        return 1 if r["problems"] else 0
    elif args.stage == "walk":
        if args.limit_days and not args.force_unfrozen:
            ap.error("--limit-days is a smoke-run option: it needs --force-unfrozen and never writes the registered outputs")
        if args.force_unfrozen:
            if not args.limit_days or args.limit_days > 5:
                ap.error("a smoke run is at most 5 breakout days (--limit-days <= 5)")
            out_dir = SCRATCH / "smoke"
        run_walk(out_dir, force_unfrozen=args.force_unfrozen, limit_days=args.limit_days, smoke_from=args.smoke_from)
    return 0


if __name__ == "__main__":
    sys.exit(main())
