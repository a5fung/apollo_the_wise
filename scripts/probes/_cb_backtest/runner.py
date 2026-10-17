#!/usr/bin/env python3
"""#702 P2a — Consolidation Breakout backtest runner, DAILY STAGE (stages 1-3 of the approved plan).

Plan: /Users/alvinfung/.claude/plans/soft-singing-hamster.md. Everything that DECIDES (universe, watch
gates, RS/group percentiles, phases, cells, entries, exits) is a call into the frozen pure module
`agents/market_intelligence/consolidation_breakout.py` (`cb`); this file only loads data, schedules
the calls, joins the cross-section, and writes tables. The one thing it adds is a numpy PRE-SCREEN that
skips `explain_watch` on nights that provably fail its first gate (see `prescreen_skip_mask`).

  python scripts/probes/_cb_backtest/runner.py daily --data /Users/alvinfung/apollo_data/cb702
  python scripts/probes/_cb_backtest/runner.py daily --data ... --step0        # composition only, reads candidates.tsv
  python scripts/probes/_cb_backtest/runner.py daily --data ... --check-prescreen 300   # exhaustive proof

Stage 1  universe + cross-section per session D (SPY calendar): `universe_ok`, `rs_returns` ->
         `percentile_ranks` (21/63/126), SIC-2 `group_returns` -> group percentile, three phase rules.
Stage 2  watch nights: `explain_watch(bars, i)` on every (ticker, D) in the universe from 2022-03-28;
         failing-gate funnel; `cell_flags` for K in k5/k10/full; `watch.tsv.gz`.
Stage 3  breakouts: E = the ticker's next bar (must be the next SPY session), breakout iff high(E) >
         pivot_K(D); ONE TRADE PER BASE under two keys - the spec key (ticker, pole_date, K; later breaks are
         `retrigger=1`) and the drift-robust chain key (`retrigger_chain`: poles <= 3 sessions apart = one
         base); the daily CLOSE variant + EVERY exit arm on DISCOVERY rows ONLY (D <= 2024-12-31;
         holdout rows get no outcome here - they are joined once, after the P4 freeze); the minute fetch list.

Data integrity (all runner-side; the module is frozen): a night needs 130 CONSECUTIVE sessions (holes /
reused tickers fail as 'history'), forward walks stop at a hole, splits executing after the last session are
dropped from the raw-price factor, exchange test symbols are excluded.

Outputs: DATA/out/ (large) and scripts/probes/_cb_backtest/out/ (small summaries, < 1 MB).
No DB, no network, no prod access. Read-only on DATA except DATA/out/.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import io
import multiprocessing as mp
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402

HERE = Path(__file__).resolve().parent
WATCH_START = date(2022, 3, 28)          # first watch night D (plan: discovery 2022-03-28 .. 2024-12-31)
DISCOVERY_END = date(2024, 12, 31)       # D <= this -> discovery; later -> holdout
KS = cb.PIVOT_KEYS                        # ("k5", "k10", "full")
CELL_NAMES = cb.CELLS + cb.REPORT_CELLS   # 8 deciding + 2 reported-only
GATE_NAMES = cb.WATCH_GATES
# pre-screen windows: P in [i-45, i-10] (explain_watch), pole_low in [P-40, P] -> [i-85, i-10]
PS_HI_LO, PS_HI_HI = 45, 10
PS_LOW_LO, PS_LOW_HI = 85, 10
POLE_DRIFT_MAX = 3                        # poles <= this many sessions apart are ONE base (chain key); the
#                                           module's own pole-top rule lets the top walk forward while "still extending"
POLE_BAD_HIGH_X = 1.25                    # data flag: pole-bar high above this x max(open, close) is a suspect print

# Exchange test symbols (Nasdaq/NYSE/Arca/Cboe/IEX test securities). The module's `universe_ok` admits an
# unknown-type ticker by design ("as prod does"), so the runner drops these before it. Fixed list + the
# Z?ZZ[TC] test family; every one of these is in the export with a fake price and ~no real volume.
TEST_SYMBOLS = frozenset({"ATEST", "CTEST", "MTEST", "NTEST", "PTEST", "ZTEST",
                          "ZBZX", "ZEXIT", "ZIEXT", "ZXIET"})
_TEST_FAMILY = re.compile(r"Z[A-Z]ZZ[TC]")

_G: dict = {}                             # fork-shared read-only globals for the worker pools


# ═════════════════════════════════════════════════════════════════════════════════════════════
# pure helpers (unit-tested in tests/test_cb_backtest_runner.py)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def prescreen_skip_mask(h: np.ndarray, l: np.ndarray) -> np.ndarray:
    """True where `explain_watch` PROVABLY fails at gate "prior_move" (given >= 130 sessions), so it
    need not run. Proof: `explain_watch` picks P in [i-45, i-10] and pole_low = min low in [P-40, P]
    (inside [i-85, i-10]); so pole_high <= H = max high[i-45..i-10] and pole_low >= L = min low[i-85..i-10].
    Division and subtraction are monotone in IEEE-754, so the computed `pole_high / pole_low - 1.0` can
    never exceed `H / L - 1.0`; when that is already < PRIOR_MOVE_MIN the gate fails. L <= 0 (bad data)
    is never skipped, and i < 85 (no full window) is never skipped. The exhaustive check in
    `check_prescreen` runs the real gate on every night of >= 200 tickers and asserts this."""
    from numpy.lib.stride_tricks import sliding_window_view as swv
    n = len(h)
    skip = np.zeros(n, dtype=bool)
    w_hi = PS_HI_LO - PS_HI_HI + 1                                # 36 bars: [i-45, i-10]
    w_lo = PS_LOW_LO - PS_LOW_HI + 1                              # 76 bars: [i-85, i-10]
    if n < PS_LOW_LO + 1 or n < w_hi or n < w_lo:
        return skip
    hmax = swv(np.asarray(h, dtype=float), w_hi).max(axis=1)     # hmax[s] = max h[s .. s+35]
    lmin = swv(np.asarray(l, dtype=float), w_lo).min(axis=1)     # lmin[s] = min l[s .. s+75]
    idx = np.arange(PS_LOW_LO, n)                                 # i with a full low window
    H = hmax[idx - PS_HI_LO]                                      # window [i-45, i-10]
    L = lmin[idx - PS_LOW_LO]                                     # window [i-85, i-10]
    with np.errstate(divide="ignore", invalid="ignore"):
        low_move = (L > 0) & (H / L - 1.0 < cb.PRIOR_MOVE_MIN)
    skip[idx] = low_move
    return skip


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


def split_label(d: date) -> str:
    return "discovery" if d <= DISCOVERY_END else "holdout"


def resolve_sectype(ticker: str, mi_types: dict, sic_types: dict) -> str:
    """`mi_security_types` value, else the SIC pull's point-in-time `type`, else "" (unknown, admitted)."""
    return mi_types.get(ticker) or sic_types.get(ticker) or ""


def is_test_symbol(ticker: str) -> bool:
    """An exchange test security (ZVZZT, NTEST, ...): never a universe member, never in the RS denominator."""
    return ticker in TEST_SYMBOLS or bool(_TEST_FAMILY.fullmatch(ticker))


def contiguous_window_mask(cidx: np.ndarray, window: int) -> np.ndarray:
    """True at bar i when the `window` bars ending at i are CONSECUTIVE SPY sessions, i.e.
    cidx[i] - cidx[i-window+1] == window-1 (cidx is strictly ascending, so equality means no session is
    missing). Everything the module reads at a watch night - the 130-bar history, RS 21/63/126, SMA50, the
    pole window, ADR20 - sits inside the 130 bars ending at i, so one test here covers all of it. A hole
    inside the span means a halt, a data gap or a REUSED TICKER (two companies glued into one series)."""
    n = len(cidx)
    out = np.zeros(n, dtype=bool)
    span = window - 1
    if n > span:
        c = np.asarray(cidx, dtype=np.int64)
        out[span:] = (c[span:] - c[:n - span]) == span
    return out


def fwd_end(cidx: np.ndarray, e: int, hi: int) -> tuple:
    """(end, cut): exclusive end index of the forward walk that starts after breakout bar `e` and would run to
    `hi` (exclusive). The walk stops BEFORE the first bar that follows a missing session, so it never reads
    across a hole (a delisted-and-reused ticker would otherwise be booked on another company's prices); the
    shortened window makes `walk_exit` end 'degraded' - an unsettled mark that the decisive numbers exclude."""
    end = min(hi, len(cidx))
    if end - e >= 2:
        brk = np.flatnonzero(np.diff(np.asarray(cidx[e:end], dtype=np.int64)) != 1)
        if len(brk):
            return e + 1 + int(brk[0]), True
    return end, False


def next_bar_status(cidx: np.ndarray, i: int, last_ci: int) -> str:
    """Where is the breakout day E = the ticker's next bar? 'ok' only if it IS the next SPY session.
    'pending' = D is the last session on the calendar (E does not exist yet); 'no_next_bar' = the ticker's
    data ends before the calendar does (delisting / data end); 'gap_in_bars' = the ticker has a later bar
    but not on the next session (halt / missing day)."""
    ci = int(cidx[i])
    if ci >= last_ci:
        return "pending"
    if i + 1 >= len(cidx):
        return "no_next_bar"
    return "ok" if int(cidx[i + 1]) == ci + 1 else "gap_in_bars"


def gap_fields(open_e: float, pivot: float, adr20: float) -> tuple:
    """(gap_open_pct, gap_over_1adr): open(E)/pivot - 1, and open(E) > pivot x (1 + adr20)."""
    return open_e / pivot - 1.0, bool(open_e > pivot * (1.0 + adr20))


def acct_pct(realized_r: float, width_pct: float) -> float:
    """Account-% P&L at the article's sizing (harvest row 9): position = min(20% of account, 1% risk /
    stop width); P&L% of account = position x (pnl/fill) = position x R x width = R x min(0.20 x width, 0.01)."""
    return realized_r * min(0.20 * width_pct, 0.01)


def stamp_retrigger(cands: list, *, key=None, retrig: str = "retrigger", first: str = "first_") -> None:
    """ONE TRADE PER BASE (harvest row 1): per (ticker, pole_date, K) the first breakout (by E) is the
    trade (retrigger=0); later ones retrigger=1. Also `first_<cell>`: within the same base+K, the first
    breakout where THAT cell held on the watch night - a cell whose flag was off on the base's first
    break would otherwise lose its valid later entry to the base-level rule (reported beside, not the spec).
    `key`/`retrig`/`first` let the same stamping run under another base key (see `stamp_base_chain`)."""
    key = key or (lambda c: (c["ticker"], c["pole_date"], c["K"]))
    groups = defaultdict(list)
    for c in cands:
        groups[key(c)].append(c)
    for g in groups.values():
        g.sort(key=lambda c: c["E"])
        seen = set()
        for k, c in enumerate(g):
            c[retrig] = 0 if k == 0 else 1
            for cell in CELL_NAMES:
                if c[cell] and cell not in seen:
                    seen.add(cell)
                    c[first + cell] = 1
                else:
                    c[first + cell] = 0


def chain_bases(poles) -> dict:
    """{(ticker, pole_ci): base_id} from `poles` = iterable of (ticker, pole_ci, pole_date) over EVERY watch row.
    A ticker's distinct poles, sorted by calendar index, are cut into runs wherever two neighbours are more
    than POLE_DRIFT_MAX sessions apart; each run is ONE base, id = ticker|pole_date of its earliest pole.
    Why components over poles, not a walk over breakouts: the module's pole top can drift 1-3 sessions inside
    ONE consolidation, and (in real data) alternate between two poles from night to night, so a chain that
    follows breakouts in E order misses the revisit; a component is E-order independent and is a COARSENING of
    the spec key by construction (same pole_date -> same pole_ci -> same base)."""
    by_tk = defaultdict(dict)
    for ticker, pci, pdate in poles:
        by_tk[ticker][int(pci)] = pdate
    out = {}
    for ticker, pm in by_tk.items():
        base, prev = None, None
        for pci in sorted(pm):
            if prev is None or pci - prev > POLE_DRIFT_MAX:
                base = f"{ticker}|{pm[pci]}"
            out[(ticker, pci)] = base
            prev = pci
    return out


def stamp_base_chain(cands: list, base_of: dict) -> None:
    """Stamp the drift-robust key BESIDE the spec key: `base_id` (from `chain_bases`), `retrigger_chain`,
    `first_chain_<cell>` - the same one-trade-per-base stamping, keyed (base_id, K). Which key is the
    decisive population is a P4 ruling, made before the 30-trade go/no-go is read. Raises KeyError if a
    candidate's pole was not in the watch rows it came from (cannot happen by construction)."""
    for c in cands:
        c["base_id"] = base_of[(c["ticker"], int(c["pole_ci"]))]
    stamp_retrigger(cands, key=lambda c: (c["base_id"], c["K"]), retrig="retrigger_chain", first="first_chain_")


def stamp_overlap_open(cands: list, outcomes: dict) -> None:
    """report-only. DISCOVERY non-retrigger rows: 1 if the previous FILLED trade of the same ticker+K
    (a different base - same-base breaks are retriggers) was still open under the PRIMARY arm when this
    breakout day E arrived. `outcomes[(ticker, D, K)] = (filled, sessions_held, status)` from the CLOSE
    variant (a proxy: the real entry is ORH). Holdout rows and retriggers are left '' - an exit date is
    an outcome, and holdout outcomes are joined once after the freeze."""
    by_tk = defaultdict(list)
    for c in cands:
        c["overlap_open"] = ""
        if c["split"] == "discovery" and c["retrigger"] == 0:
            by_tk[(c["ticker"], c["K"])].append(c)
    for rows in by_tk.values():
        rows.sort(key=lambda c: c["E"])
        prev_end = None                    # session index (cal) at which the LATEST-ending filled trade ends; inf = unsettled
        for c in rows:
            c["overlap_open"] = int(prev_end is not None and c["E_ci"] <= prev_end)
            o = outcomes.get((c["ticker"], c["D"], c["K"]))
            if o and o[0]:
                filled, held, status = o
                new_end = float("inf") if status == "degraded" else c["E_ci"] + held
                # MAX, not overwrite: a short trade that opens inside a long one must not hide the long one
                prev_end = new_end if prev_end is None else max(prev_end, new_end)


def select_close_variant_candidates(cands: list) -> list:
    """The ONLY rows that ever get an outcome at this stage: DISCOVERY (D <= 2024-12-31). Holdout rows are
    never walked here - their outcomes are joined once, after the P4 freeze (pre-registration)."""
    return [c for c in cands if c["split"] == "discovery"]


def cross_section_one_date(r21: list, r63: list, r126: list, groups: list) -> tuple:
    """Stage-1 cross-section for ONE date over the universe members (parallel lists; None allowed).
    rs_best = max of the three percentiles, rs_all = min (None if any is None); the group return is
    `cb.group_returns` over members' r63 (groups < 10 members drop out), grp_pct = `cb.percentile_ranks`
    of the group medians; a member without a (surviving) group reads None."""
    p = [cb.percentile_ranks(list(r)) for r in (r21, r63, r126)]
    rs_best, rs_all = [], []
    for a, b, c in zip(*p):
        vals = [x for x in (a, b, c) if x is not None]
        rs_best.append(max(vals) if vals else None)
        rs_all.append(min(vals) if len(vals) == 3 else None)
    member_r63 = defaultdict(list)
    for g, r in zip(groups, r63):
        if g is not None:
            member_r63[g].append(r)
    gr = cb.group_returns(member_r63)
    gp = dict(zip(gr.keys(), cb.percentile_ranks(list(gr.values())))) if gr else {}
    grp = [gp.get(g) if g is not None else None for g in groups]
    return rs_best, rs_all, grp, len(gr)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# loading
# ═════════════════════════════════════════════════════════════════════════════════════════════
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


def load_daily(path: Path) -> Daily:
    """The whole export as flat sorted arrays (a deliberate departure from `_610.load_bars`, which builds
    13.8M `date` objects: ~1 GB that fork would dirty per worker). Per-ticker dates are rebuilt in the
    worker from the calendar index. Asserts: calendar = SPY's dates; every bar date is on it; dates
    strictly ascending within a ticker; every value finite. A ticker's bars are NOT required to be
    consecutive sessions (6,000+ tickers have holes: halts, thin names, reused tickers) - the hole COUNT is
    returned and `scan_ticker` / `fwd_end` refuse to read across one."""
    import pandas as pd
    t0 = time.time()
    # keep_default_na=False: a ticker literally named "NA" must stay a string, not become NaN
    df = pd.read_csv(path, header=None, names=["ticker", "d", "o", "h", "l", "c", "v"],
                     dtype={"ticker": str, "o": float, "h": float, "l": float, "c": float, "v": float},
                     parse_dates=["d"], keep_default_na=False)
    codes, uniques = pd.factorize(df["ticker"], sort=True)
    days = df["d"].to_numpy().astype("datetime64[D]").astype(np.int64)
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
    brk = same & (np.diff(ci.astype(np.int64)) != 1)               # a missing SPY session between two bars
    n_holes, n_hole_tickers = int(brk.sum()), int(len(np.unique(codes[1:][brk])))
    cal = [date.fromordinal(int(d) + 719163) for d in cal_days]          # datetime64[D] int -> ordinal
    print(f"bars: {len(codes):,} rows / {len(tickers):,} tickers / {len(cal)} sessions "
          f"{cal[0]}..{cal[-1]} ({time.time() - t0:.0f}s); {n_hole_tickers:,} tickers have a missing session "
          f"inside their span ({n_holes:,} holes)", flush=True)
    return Daily(tickers, start, stop, ci.astype(np.int32), cols["o"], cols["h"], cols["l"], cols["c"],
                 cols["v"], cal, tid, n_hole_tickers, n_holes)


def bars_for(D: Daily, t: int):
    """(DailyBars, calendar-index array) of ticker id `t` - views into the flat arrays."""
    a, b = int(D.start[t]), int(D.stop[t])
    cidx = D.ci[a:b]
    dates = [D.cal[k] for k in cidx]
    return cb.daily_bars_from_arrays(dates, D.o[a:b], D.h[a:b], D.l[a:b], D.c[a:b], D.v[a:b]), cidx


def load_small(path: Path) -> tuple:
    """small_pulls.psv -> (mi_security_types {ticker: type}, regime {date: label})."""
    sec, reg = {}, {}
    for line in path.read_text().splitlines():
        f = line.split("|")
        if f[0] == "sectype" and len(f) >= 3:
            sec[f[1]] = f[2]
        elif f[0] == "regime" and len(f) >= 3:
            reg[date.fromisoformat(f[1])] = f[2]
    return sec, reg


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


def load_sic(path: Path) -> tuple:
    """cb702_sic.psv -> ({ticker: sic2 or None}, {ticker: pull `type`}). The pull is ONE row per ticker
    (as of 2026-10-16, or the delisting date for the dead ones), so a ticker's group is constant in
    time - 'point-in-time' only in the sense of that one date. Empty sic_code / HTTP 404 -> no group."""
    sic, typ = {}, {}
    for line in path.read_text().splitlines():
        f = line.split("|")
        if len(f) < 6:
            continue
        sic[f[0]] = cb.sic2(f[3]) if f[3] else None
        typ[f[0]] = f[5]
    return sic, typ


# ═════════════════════════════════════════════════════════════════════════════════════════════
# pass 1 - per ticker (worker): universe, RS inputs, watch nights
# ═════════════════════════════════════════════════════════════════════════════════════════════
def scan_ticker(ticker: str, bars: "cb.DailyBars", cidx: np.ndarray, splits: list, sectype: str,
                d0_ci: int, *, prescreen: bool = True) -> dict:
    """Universe membership + RS inputs + watch features for every night from calendar index `d0_ci`.
    A night is admitted only if (a) the ticker is not an exchange test symbol, (b) `universe_ok`, and (c) the
    130 bars ending at it are consecutive SPY sessions - a night failing only (c) is counted under 'history'
    (the module's own 'history' gate is >= 130 sessions; here it is >= 130 CONSECUTIVE ones)."""
    n = len(bars)
    fac = factor_by_bar(bars.dates, splits)
    skip = prescreen_skip_mask(bars.h, bars.l) if prescreen else np.zeros(n, dtype=bool)
    contig = contiguous_window_mask(cidx, cb.MIN_HISTORY)
    test_sym = is_test_symbol(ticker)
    start = int(np.searchsorted(cidx, d0_ci))
    counts: Counter = Counter()
    uni_ci, rs = [], []
    watch = []
    for i in range(start, n):
        yr = bars.dates[i].year
        if test_sym or not cb.universe_ok(bars, i, raw_factor=float(fac[i]), ticker=ticker, security_type=sectype):
            counts[(yr, "universe_fail")] += 1
            continue
        if not contig[i]:
            counts[(yr, "history")] += 1
            continue
        ci = int(cidx[i])
        uni_ci.append(ci)
        rs.append(tuple(np.nan if x is None else x for x in cb.rs_returns(bars, i)))
        if skip[i]:
            counts[(yr, "prescreen_skip")] += 1
            continue
        feat, gate = cb.explain_watch(bars, i)
        if feat is None:
            counts[(yr, gate)] += 1
            continue
        assert feat["watch_date"] == bars.dates[i].isoformat(), (ticker, i)       # the module's i IS this D
        counts[(yr, "pass")] += 1
        feat["ticker"], feat["ci"] = ticker, ci
        feat["pole_ci"] = int(cidx[feat["pole_idx"]])                               # drift-robust base key input
        top = max(float(bars.o[feat["pole_idx"]]), float(bars.c[feat["pole_idx"]]))
        feat["pole_hi_over_oc"] = float(feat["pole_high"]) / top if top > 0 else None   # data flag (bad high print)
        watch.append(feat)
    return {"ticker": ticker, "uni_ci": np.asarray(uni_ci, dtype=np.int32),
            "rs": np.asarray(rs, dtype=float).reshape(-1, 3), "watch": watch, "counts": counts}


def _scan_job(t: int) -> dict:
    D: Daily = _G["D"]
    ticker = D.tickers[t]
    bars, cidx = bars_for(D, t)
    return scan_ticker(ticker, bars, cidx, _G["splits"].get(ticker, []),
                       resolve_sectype(ticker, _G["mi_types"], _G["sic_types"]), _G["d0_ci"])


def _check_job(t: int) -> dict:
    """Exhaustive pre-screen proof for one ticker: the real gate on EVERY night i >= 129."""
    D: Daily = _G["D"]
    bars, _ = bars_for(D, t)
    skip = prescreen_skip_mask(bars.h, bars.l)
    out = dict(ticker=D.tickers[t], nights=0, skipped=0, passed_gate=0, watch_pass=0, violations=[])
    for i in range(cb.MIN_HISTORY - 1, len(bars)):
        feat, gate = cb.explain_watch(bars, i)
        out["nights"] += 1
        if feat is not None:
            out["watch_pass"] += 1
        if skip[i]:
            out["skipped"] += 1
            if not (feat is None and gate == "prior_move"):
                out["violations"].append((D.tickers[t], bars.dates[i].isoformat(), gate))
        elif gate != "prior_move":
            out["passed_gate"] += 1
    return out


def _pool(workers: int):
    return mp.get_context("fork").Pool(workers)


def check_prescreen(D: Daily, n_tickers: int, workers: int, liquid_path: Path) -> str:
    """Run the real `explain_watch` on every night of >= `n_tickers` tickers (liquid first, deterministic
    sample) and assert the pre-screen only ever skips nights that fail at 'prior_move'."""
    rng = random.Random(702)
    liquid = [l.split("|")[0].strip() for l in liquid_path.read_text().splitlines() if l.strip()] \
        if liquid_path.exists() else []
    liquid = sorted(t for t in set(liquid) if t in D.tid and D.stop[D.tid[t]] - D.start[D.tid[t]] >= 200)
    other = sorted(t for t in D.tickers if t not in set(liquid) and D.stop[D.tid[t]] - D.start[D.tid[t]] >= 200)
    n_liq = min(len(liquid), (2 * n_tickers) // 3)
    sample = rng.sample(liquid, n_liq) + rng.sample(other, min(len(other), n_tickers - n_liq))
    _G["D"] = D
    t0 = time.time()
    with _pool(workers) as p:
        res = p.map(_check_job, [D.tid[t] for t in sample], chunksize=4)
    nights = sum(r["nights"] for r in res)
    skipped = sum(r["skipped"] for r in res)
    watch = sum(r["watch_pass"] for r in res)
    viol = [v for r in res for v in r["violations"]]
    msg = (f"PRESCREEN CHECK: {len(sample)} tickers ({n_liq} liquid + {len(sample) - n_liq} other), "
           f"{nights:,} nights (real explain_watch on every night i>=129), pre-screen skips {skipped:,} "
           f"({skipped / nights:.1%}), every skip failed at prior_move: {'YES' if not viol else 'NO'}; "
           f"{watch:,} nights pass all gates and 0 of them were skipped; violations={len(viol)}; "
           f"{time.time() - t0:.0f}s")
    if viol:
        msg += "\n  first violations: " + repr(viol[:5])
    return msg


# ═════════════════════════════════════════════════════════════════════════════════════════════
# stage 3 - close variant (worker)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def close_variant_rows(ticker: str, bars: "cb.DailyBars", cands: list, cidx: "np.ndarray | None" = None) -> list:
    """CLOSE entry + every exit arm for DISCOVERY candidates of one ticker. E is session 0;
    closes_before = closes through E (asserted); fwd = bars E+1 .. E+1+horizon (horizon + 1 sessions),
    CUT at the first missing session when `cidx` (the ticker's SPY-calendar indices) is given - the walk then
    ends 'degraded' instead of reading across a hole (`fwd_hole` = 1 on those rows)."""
    out = []
    H = cb.EXIT_HORIZON
    for c in cands:
        e = c["E_i"]
        assert bars.dates[e].isoformat() == c["E"], (ticker, e, c["E"])
        if cidx is not None:                                 # D was admitted on 130 consecutive bars; E follows D
            assert e >= cb.MIN_HISTORY and int(cidx[e]) - int(cidx[e - cb.MIN_HISTORY]) == cb.MIN_HISTORY, (ticker, e)
        entry = cb.close_entry(float(bars.c[e]), float(bars.l[e]), c["pivot"], c["adr20"])
        row = {"ticker": ticker, "D": c["D"], "E": c["E"], "K": c["K"], "pole_date": c["pole_date"],
               "pivot": c["pivot"], "adr20": c["adr20"], "retrigger": c["retrigger"],
               "close_status": entry["status"], "close_reason": entry["reason"],
               "close_fill": entry["fill"], "close_stop": entry["stop"],
               "close_width_pct": entry["width_pct"],
               "base_id": c.get("base_id", ""), "retrigger_chain": c.get("retrigger_chain", "")}
        for cell in CELL_NAMES:
            row[cell] = c[cell]
            row["first_" + cell] = c["first_" + cell]
            row["first_chain_" + cell] = c.get("first_chain_" + cell, "")
        end, cut = fwd_end(cidx, e, e + 2 + H) if cidx is not None else (min(e + 2 + H, len(bars)), False)
        fwd = bars.slice(e + 1, end)
        row["fwd_hole"] = int(cut)
        row["fwd_bars"] = len(fwd)
        row["fwd_last_date"] = fwd.dates[-1].isoformat() if len(fwd) else ""
        if entry["status"] == "filled":
            cb_closes = bars.c[:e + 1]
            assert cb_closes[-1] == bars.c[e]
            for name, arm in cb.ARMS.items():
                res = cb.walk_exit(fill=entry["fill"], stop=entry["stop"], closes_before=cb_closes,
                                   fwd=fwd, arm=arm, adr20=c["adr20"], horizon=H)
                row[f"st_{name}"] = res["status"]
                row[f"r_{name}"] = res["realized_r"]
                row[f"adr_{name}"] = res["pnl_adr"]
                row[f"held_{name}"] = res["sessions_held"]
                row[f"acct_{name}"] = acct_pct(res["realized_r"], entry["width_pct"])
                row[f"beabove_{name}"] = int(any(ev[1] == "be_above_close" for ev in res["events"]))
        out.append(row)
    return out


def _close_job(item: tuple) -> list:
    t, cands = item
    D: Daily = _G["D"]
    bars, cidx = bars_for(D, t)
    return close_variant_rows(D.tickers[t], bars, cands, cidx)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# output
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _fmt(x) -> str:
    if x is None:
        return ""
    if isinstance(x, (bool, np.bool_)):
        return "1" if x else "0"
    if isinstance(x, (float, np.floating)):
        return "" if x != x else repr(float(x))
    return str(x)


def write_tsv(path: Path, rows: list, cols: list, gz: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = (lambda p: gzip.open(p, "wt", newline="")) if gz else (lambda p: open(p, "w", newline=""))
    with opener(path) as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([_fmt(r.get(c)) for c in cols])
    return len(rows)


def table(rows: list, header: list) -> str:
    """Fixed-width text table (monospace)."""
    cells = [header] + [[str(x) for x in r] for r in rows]
    w = [max(len(r[k]) for r in cells) for k in range(len(header))]
    return "\n".join("  ".join(c.rjust(w[k]) if k else c.ljust(w[k]) for k, c in enumerate(r)) for r in cells)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the daily stage
# ═════════════════════════════════════════════════════════════════════════════════════════════
def run_daily(args) -> None:
    data = Path(args.data)
    out = Path(args.out) if args.out else data / "out"
    small = Path(args.small_out) if args.small_out else HERE / "out"
    out.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    log: list = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        log.append(msg)

    T0 = time.time()
    timers = {}

    def lap(name: str, t: float) -> None:
        timers[name] = time.time() - t
        say(f"[{name}: {timers[name]:.0f}s]")

    t = time.time()
    D = load_daily(data / "daily_closes_all.csv.gz")
    mi_types, regime = load_small(data / "small_pulls.psv")
    n_splits_all = sum(len(v) for v in load_splits(data / "cb702_splits.psv").values())
    splits = load_splits(data / "cb702_splits.psv", through=D.cal[-1])       # not splits executing after the data ends
    n_splits = sum(len(v) for v in splits.values())
    sic_by_tk, sic_types = load_sic(data / "cb702_sic.psv")
    lap("load", t)
    if args.check_prescreen:
        say(check_prescreen(D, args.check_prescreen, args.workers, data / "liquid_tickers.txt"))
        return
    cal = D.cal
    last_ci = len(cal) - 1
    d0_ci = bisect.bisect_left(cal, WATCH_START)
    spy_i, qqq_i = D.tid["SPY"], D.tid["QQQ"]
    spy, _ = bars_for(D, spy_i)
    qqq, _ = bars_for(D, qqq_i)
    assert spy.dates == cal and qqq.dates == cal, "QQQ/SPY must carry every session (the phase join is by DATE)"

    # ── pass 1: per ticker ───────────────────────────────────────────────────────────────────
    t = time.time()
    _G.update(D=D, splits=splits, mi_types=mi_types, sic_types=sic_types, d0_ci=d0_ci)
    tids = list(range(len(D.tickers)))
    if args.limit_tickers:
        keep = set(random.Random(7).sample(tids, args.limit_tickers)) | {D.tid[x] for x in ("MRNA", "OUST", "HPE") if x in D.tid}
        tids = [x for x in tids if x in keep]
    if args.workers > 1:
        with _pool(args.workers) as p:
            res = p.map(_scan_job, tids, chunksize=8)
    else:
        res = [_scan_job(x) for x in tids]
    lap("pass 1 (universe + RS inputs + explain_watch)", t)

    counts: Counter = Counter()
    for r in res:
        counts.update(r["counts"])
    watch_all = [w for r in res for w in r["watch"]]
    tid_of = D.tid

    # ── stage 1 cross-section per date ────────────────────────────────────────────────────────
    t = time.time()
    m_tid = np.concatenate([np.full(len(r["uni_ci"]), tid_of[r["ticker"]], dtype=np.int32) for r in res]) \
        if res else np.zeros(0, dtype=np.int32)
    m_ci = np.concatenate([r["uni_ci"] for r in res]) if res else np.zeros(0, dtype=np.int32)
    m_rs = np.concatenate([r["rs"] for r in res]) if res else np.zeros((0, 3))
    order = np.lexsort((m_tid, m_ci))          # by date, then ticker id (alphabetical = input order for ties)
    m_tid, m_ci, m_rs = m_tid[order], m_ci[order], m_rs[order]
    bounds = np.searchsorted(m_ci, np.arange(len(cal) + 1))
    sic_of_tid = [sic_by_tk.get(x) for x in D.tickers]
    watch_by_ci = defaultdict(list)
    for w in watch_all:
        watch_by_ci[w["ci"]].append(w)
    phase_a1 = [cb.phase_qqq_10_20(qqq, j, 1) for j in range(len(cal))]
    phase_a5 = [cb.phase_qqq_10_20(qqq, j, 5) for j in range(len(cal))]
    phase_b = [cb.phase_spy_qqq_50(spy, qqq, j, j) for j in range(len(cal))]
    uni_rows = []
    ctx_of: dict = {}                          # (ci, ticker) -> ctx, watch tickers only
    for j in range(d0_ci, len(cal)):
        a, b = int(bounds[j]), int(bounds[j + 1])
        if b == a:
            continue
        ids = m_tid[a:b]
        r21, r63, r126 = ([None if x != x else float(x) for x in m_rs[a:b, k]] for k in range(3))
        groups = [sic_of_tid[x] for x in ids]
        rs_best, rs_all, grp, n_groups = cross_section_one_date(r21, r63, r126, groups)
        pos = {int(x): k for k, x in enumerate(ids)}
        for w in watch_by_ci.get(j, []):
            k = pos[tid_of[w["ticker"]]]          # a watch night is a universe member by construction
            ctx_of[(j, w["ticker"])] = {"rs_best": rs_best[k], "rs_all": rs_all[k], "grp_pct": grp[k]}
        uni_rows.append({"date": cal[j].isoformat(), "universe_n": b - a,
                         "members_with_group": sum(1 for g in groups if g is not None),
                         "groups_ge10": n_groups, "watch_rows": len(watch_by_ci.get(j, [])),
                         "phase_qqq_10_20_s1": phase_a1[j], "phase_qqq_10_20_s5": phase_a5[j],
                         "phase_spy_qqq_50": phase_b[j], "apollo_regime": regime.get(cal[j], "")})
    lap("stage 1 cross-section", t)

    # ── watch rows + cells ────────────────────────────────────────────────────────────────────
    t = time.time()
    watch_cols_feat = None
    watch_rows = []
    for w in sorted(watch_all, key=lambda x: (x["ci"], x["ticker"])):
        j = w["ci"]
        assert qqq.dates[j] == cal[j] == date.fromisoformat(w["watch_date"])
        ctx = dict(ctx_of[(j, w["ticker"])])
        ctx.update(phase_qqq_10_20=phase_a1[j], phase_spy_qqq_50=phase_b[j])
        ctx5 = dict(ctx, phase_qqq_10_20=phase_a5[j])
        row = dict(w)
        row.update(ctx)
        row["phase_qqq_10_20_s5"] = phase_a5[j]
        row["apollo_regime"] = regime.get(cal[j], "")
        row["split"] = split_label(cal[j])
        for k in KS:
            fl = cb.cell_flags(w, ctx, k=k)
            for cell in CELL_NAMES:
                row[f"{cell}_{k}"] = fl[cell]
            row[f"C1_s5_{k}"] = cb.cell_flags(w, ctx5, k=k)["C1"]
        watch_rows.append(row)
    base_cols = ["ticker", "watch_date", "ci", "split"] + [k for k in watch_all[0] if k not in ("ticker", "watch_date", "ci")] \
        if watch_all else ["ticker", "watch_date"]
    ctx_cols = ["rs_best", "rs_all", "grp_pct", "phase_qqq_10_20", "phase_qqq_10_20_s5", "phase_spy_qqq_50", "apollo_regime"]
    cell_cols = [f"{c}_{k}" for k in KS for c in CELL_NAMES + ("C1_s5",)]
    n_watch = write_tsv(out / "watch.tsv.gz", watch_rows, base_cols + ctx_cols + cell_cols, gz=True)
    lap("watch rows + cells", t)

    # ── candidates (breakouts) ────────────────────────────────────────────────────────────────
    t = time.time()
    cands, nonok = [], Counter()
    gap_rows = []
    for w in watch_rows:
        tid = tid_of[w["ticker"]]
        a = int(D.start[tid])
        bars_cidx = D.ci[a:int(D.stop[tid])]
        i = w["i"]
        st = next_bar_status(bars_cidx, i, last_ci)
        if st != "ok":
            nonok[(st, w["split"])] += 1
            if st != "pending":
                gap_rows.append({"ticker": w["ticker"], "D": w["watch_date"], "status": st,
                                 "next_bar_date": cal[int(bars_cidx[i + 1])].isoformat() if st == "gap_in_bars" else "",
                                 "expected_E": cal[w["ci"] + 1].isoformat()})
            continue
        e = a + i + 1
        e_ci = int(D.ci[e])
        assert e_ci == w["ci"] + 1
        adv20 = float(D.v[a + i - 19:a + i + 1].mean())
        for k in KS:
            pivot = w[f"pivot_{k}"]
            if not D.h[e] > pivot:
                continue
            gap_open, over1 = gap_fields(float(D.o[e]), pivot, w["adr20"])
            c = {"ticker": w["ticker"], "D": w["watch_date"], "E": cal[e_ci].isoformat(), "K": k,
                 "pole_date": w["pole_date"], "pole_ci": w["pole_ci"], "pivot": pivot, "adr20": w["adr20"],
                 "gap_open_pct": gap_open,
                 "gap_over_1adr": over1, "split": w["split"], "E_i": i + 1, "E_ci": e_ci,
                 "open_E": float(D.o[e]), "high_E": float(D.h[e]), "low_E": float(D.l[e]),
                 "close_E": float(D.c[e]), "vol_E": float(D.v[e]), "adv20_vol_D": adv20,
                 "breakout_vol_x": float(D.v[e]) / adv20 if adv20 > 0 else None}
            for cell in CELL_NAMES:
                c[cell] = w[f"{cell}_{k}"]
            c["C1_s5"] = w[f"C1_s5_{k}"]
            for f_ in ("prior_move", "base_len", "retrace", "base_depth", "tightening_ratio", "pole_sessions",
                       "median_dollar_vol20", "pole_day_vol_ratio", "pole_max_gap", "atr14", "atr14_slope",
                       "trigger_bar_range_adr", "inside_day"):
                c[f_] = w[f_]
            for f_ in ("rs_best", "rs_all", "grp_pct", "phase_qqq_10_20", "phase_qqq_10_20_s5",
                       "phase_spy_qqq_50", "apollo_regime"):
                c[f_] = w[f_]
            c["pivot_date"] = w[f"pivot_{k}_date"]
            c["pole_hi_over_oc"] = w["pole_hi_over_oc"]
            c["pole_bad_high"] = int(w["pole_hi_over_oc"] is not None and w["pole_hi_over_oc"] > POLE_BAD_HIGH_X)
            cands.append(c)
    stamp_retrigger(cands)
    stamp_base_chain(cands, chain_bases((w["ticker"], w["pole_ci"], w["pole_date"]) for w in watch_rows))
    # the chain key only ever MERGES bases: a spec retrigger is always a chain retrigger
    assert all(c["retrigger_chain"] == 1 for c in cands if c["retrigger"] == 1), "chain key is not a coarsening"
    lap("stage 3 breakouts", t)

    # ── CLOSE variant, discovery only ─────────────────────────────────────────────────────────
    t = time.time()
    by_tk = defaultdict(list)
    for c in select_close_variant_candidates(cands):
        by_tk[tid_of[c["ticker"]]].append(c)
    items = sorted(by_tk.items())
    if args.workers > 1:
        with _pool(args.workers) as p:
            parts = p.map(_close_job, items, chunksize=8)
    else:
        parts = [_close_job(x) for x in items]
    cv_rows = [r for part in parts for r in part]
    primary = cb.PRIMARY_ARM
    outcomes = {}
    for r in cv_rows:
        filled = r["close_status"] == "filled"
        outcomes[(r["ticker"], r["D"], r["K"])] = (filled, r.get(f"held_{primary}", 0) or 0,
                                                   r.get(f"st_{primary}"))
    stamp_overlap_open(cands, outcomes)
    arm_cols = [f"{p}_{n}" for n in cb.ARMS for p in ("st", "r", "adr", "held", "acct", "beabove")]
    cv_cols = (["ticker", "D", "E", "K", "pole_date", "pivot", "adr20", "retrigger", "retrigger_chain", "base_id",
                "close_status", "close_reason", "close_fill", "close_stop", "close_width_pct", "fwd_bars",
                "fwd_last_date", "fwd_hole"]
               + list(CELL_NAMES) + ["first_" + c for c in CELL_NAMES] + ["first_chain_" + c for c in CELL_NAMES]
               + arm_cols)
    n_cv = write_tsv(out / "close_variant_discovery.tsv.gz", cv_rows, cv_cols, gz=True)
    lap("close variant + 15 exit arms (discovery)", t)

    # ── write candidates / fetch list / summaries ──────────────────────────────────────────────
    t = time.time()
    cand_cols = (["ticker", "D", "E", "K", "pole_date", "pole_ci", "pivot", "pivot_date", "adr20", "gap_open_pct",
                  "gap_over_1adr", "retrigger", "retrigger_chain", "base_id", "overlap_open", "split",
                  "pole_hi_over_oc", "pole_bad_high"]
                 + list(CELL_NAMES) + ["C1_s5"] + ["first_" + c for c in CELL_NAMES]
                 + ["first_chain_" + c for c in CELL_NAMES]
                 + ["open_E", "high_E", "low_E", "close_E", "vol_E", "adv20_vol_D", "breakout_vol_x"]
                 + ["prior_move", "base_len", "retrace", "base_depth", "tightening_ratio", "pole_sessions",
                    "median_dollar_vol20", "pole_day_vol_ratio", "pole_max_gap", "atr14", "atr14_slope",
                    "trigger_bar_range_adr", "inside_day", "rs_best", "rs_all", "grp_pct", "phase_qqq_10_20",
                    "phase_qqq_10_20_s5", "phase_spy_qqq_50", "apollo_regime"])
    cands.sort(key=lambda c: (c["E"], c["ticker"], c["K"]))
    write_tsv(out / "candidates.tsv", cands, cand_cols)
    write_tsv(out / "gap_in_bars.tsv", gap_rows, ["ticker", "D", "status", "next_bar_date", "expected_E"])
    fetch = {}
    for c in cands:
        tier = int(any(c[x] for x in CELL_NAMES if x != "C0"))
        key = (c["ticker"], c["E"])
        fetch[key] = max(fetch.get(key, 0), tier)
    fetch_rows = [{"ticker": k[0], "date": k[1], "tier": v} for k, v in sorted(fetch.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    write_tsv(out / "minute_fetch_list.tsv", fetch_rows, ["ticker", "date", "tier"])
    write_tsv(small / "universe_by_date.tsv", uni_rows,
              ["date", "universe_n", "members_with_group", "groups_ge10", "watch_rows", "phase_qqq_10_20_s1",
               "phase_qqq_10_20_s5", "phase_spy_qqq_50", "apollo_regime"])

    # funnel
    years = sorted({y for (y, _g) in counts})
    names = ["universe_fail", "prescreen_skip"] + list(GATE_NAMES) + ["pass"]
    funnel = []
    tot_by_year = {y: sum(v for (yy, _g), v in counts.items() if yy == y) for y in years}
    for nm in names:
        funnel.append({"stage": nm, "total": sum(v for (_y, g), v in counts.items() if g == nm),
                       **{str(y): counts.get((y, nm), 0) for y in years}})
    funnel.append({"stage": "TOTAL ticker-nights", "total": sum(tot_by_year.values()),
                   **{str(y): tot_by_year[y] for y in years}})
    write_tsv(small / "gate_counts.tsv", funnel, ["stage", "total"] + [str(y) for y in years])
    lap("write outputs", t)

    # ── report ─────────────────────────────────────────────────────────────────────────────────
    tot = sum(tot_by_year.values())
    uni_total = tot - sum(v for (_y, g), v in counts.items() if g in ("universe_fail", "history"))
    say("")
    say(f"DATA INTEGRITY: {D.n_hole_tickers:,} of {len(D.tickers):,} tickers have a missing SPY session inside their span "
        f"({D.n_holes:,} holes); a night is admitted only if its 130 bars are consecutive sessions, and a forward "
        f"walk stops at the first hole; splits executing after {cal[-1]} dropped: {n_splits_all - n_splits} of "
        f"{n_splits_all} (not yet in the adjusted series); exchange test symbols excluded: "
        f"{sum(1 for x in D.tickers if is_test_symbol(x))} tickers present in the export")
    say(f"GATE FUNNEL (ticker-nights with D >= {WATCH_START}; each night lands in exactly ONE row)")
    say(table([[r["stage"], f"{r['total']:,}", f"{r['total'] / tot:.2%}" if tot else ""] for r in funnel],
              ["stage", "nights", "share"]))
    say(f"  'history' = universe_ok passed but the 130 bars are NOT consecutive sessions (a hole / reused ticker); "
        f"universe members (nights) = total - universe_fail - history: {uni_total:,};  pre-screen skips are nights the real gate would fail "
        f"at prior_move (proved by --check-prescreen);  prior_move total incl. skips = "
        f"{counts_total(counts, 'prior_move') + counts_total(counts, 'prescreen_skip'):,}")
    say("")
    say(f"WATCH ROWS: {n_watch:,} (ticker x D) over {len({w['ticker'] for w in watch_rows}):,} tickers; "
        f"discovery {sum(1 for w in watch_rows if w['split'] == 'discovery'):,} / "
        f"holdout {sum(1 for w in watch_rows if w['split'] == 'holdout'):,}")
    say(f"  universe size per date: min {min(r['universe_n'] for r in uni_rows):,} "
        f"median {int(np.median([r['universe_n'] for r in uni_rows])):,} max {max(r['universe_n'] for r in uni_rows):,}; "
        f"watch rows with no group (grp_pct None): {sum(1 for w in watch_rows if w['grp_pct'] is None):,}; "
        f"rs_best None: {sum(1 for w in watch_rows if w['rs_best'] is None):,}")
    hdr = ["cell"] + [f"{k}" for k in KS]
    say("  watch nights with the cell true (all splits):")
    say(table([[c] + [sum(1 for w in watch_rows if w[f'{c}_{k}']) for k in KS] for c in CELL_NAMES + ("C1_s5",)], hdr))
    say("")
    bad = [w for w in watch_rows if w["pole_hi_over_oc"] is not None and w["pole_hi_over_oc"] > POLE_BAD_HIGH_X]
    say(f"  DATA FLAG: {len(bad):,} watch rows on {len({w['ticker'] for w in bad}):,} tickers have a pole bar whose high is "
        f"> {POLE_BAD_HIGH_X}x max(open, close) (a suspect print can become pole_high); C1_k5 nights among them: "
        f"{sum(1 for w in bad if w['C1_k5'])}")
    say("")
    say(f"BREAKOUT CANDIDATES (high(E) > pivot_K(D)): {len(cands):,} rows "
        f"(spec key {sum(1 for c in cands if c['retrigger'] == 0):,} trades + {sum(1 for c in cands if c['retrigger'] == 1):,} retriggers; "
        f"chain key {sum(1 for c in cands if c['retrigger_chain'] == 0):,} trades + {sum(1 for c in cands if c['retrigger_chain'] == 1):,} retriggers); "
        f"no-E statuses (watch rows, no trade): {dict(nonok)}")
    say(step0_text(cands))
    say("")
    say(f"CLOSE VARIANT (discovery): {n_cv:,} rows; "
        + str(dict(Counter(r["close_status"] for r in cv_rows)))
        + f"; walks cross into the holdout period (fwd_last_date > {DISCOVERY_END}): "
        f"{sum(1 for r in cv_rows if r['close_status'] == 'filled' and r['fwd_last_date'] > DISCOVERY_END.isoformat()):,} filled rows; "
        f"forward walk cut at a hole (ends 'degraded'): {sum(1 for r in cv_rows if r['close_status'] == 'filled' and r['fwd_hole']):,} filled rows")
    say(f"MINUTE FETCH LIST: {len(fetch_rows):,} unique (ticker, E) pairs over {len({r['date'] for r in fetch_rows}):,} dates "
        f"(tier 1 = any cell C1..C7/report cells true: {sum(1 for r in fetch_rows if r['tier']):,}; "
        f"non-retrigger only: {len({(c['ticker'], c['E']) for c in cands if c['retrigger'] == 0}):,})")
    say(f"WALL TIME: {time.time() - T0:.0f}s total  " + "  ".join(f"{k}={v:.0f}s" for k, v in timers.items()))
    (small / "run_summary.txt").write_text("\n".join(log) + "\n")


def counts_total(counts: Counter, gate: str) -> int:
    return sum(v for (_y, g), v in counts.items() if g == gate)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# STEP 0 - composition before any outcome
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _step0_block(rows: list, retrig: str, first: str) -> str:
    body = []
    for cell in CELL_NAMES:
        r = [cell]
        for k in KS:
            sub = [c for c in rows if c["K"] == k and c[cell]]
            tr = [c for c in sub if c[retrig] == 0]
            r += [f"{len(tr)}", f"{sum(1 for c in sub if c[first + cell] == 1)}",
                  f"{sum(1 for c in tr if c['gap_over_1adr'])}"]
        body.append(r)
    return table(body, ["cell"] + [f"{k}:{x}" for k in KS for x in ("trades", "first", "gap>1adr")])


def step0_text(cands: list) -> str:
    """n per cell per K, HOLDOUT then DISCOVERY - composition only, no outcome, under BOTH base keys.
    SPEC key = (ticker, pole_date, K): 'trades' = non-retrigger breakouts (the spec's one-trade-per-base rule).
    CHAIN key = poles within POLE_DRIFT_MAX sessions are one base (the pole top drifts 1-3 sessions inside one
    consolidation, which re-keys the same base under the spec key). 'first' = the first breakout of a base on
    which THAT cell held. Which key is decisive is a P4 ruling, made before the 30-trade go/no-go is read."""
    lines = ["STEP 0 - composition (no outcomes). n = breakout candidates, before entry abstains"]
    for split in ("holdout", "discovery"):
        rows = [c for c in cands if c["split"] == split]
        lines.append(f"  {split.upper()}: {len(rows):,} candidate rows")
        lines.append(f"  -- SPEC key (ticker, pole_date, K): {sum(1 for c in rows if c['retrigger'] == 0):,} trades --")
        lines.append(_step0_block(rows, "retrigger", "first_"))
        lines.append(f"  -- CHAIN key (poles <= {POLE_DRIFT_MAX} sessions apart = one base): "
                     f"{sum(1 for c in rows if c['retrigger_chain'] == 0):,} trades --")
        lines.append(_step0_block(rows, "retrigger_chain", "first_chain_"))
    for label, retrig in (("SPEC key", "retrigger"), ("CHAIN key", "retrigger_chain")):
        h = [c for c in cands if c["split"] == "holdout" and c[retrig] == 0 and c["C1"]]
        by_year = Counter(c["E"][:4] for c in h)
        lines.append(f"  GO/NO-GO input, {label} (plan: C1 needs >= 30 holdout trades): "
                     + ", ".join(f"{k}: {sum(1 for c in h if c['K'] == k)}" for k in KS)
                     + "   [C1 holdout trades by year, all K: " + ", ".join(f"{y}={n}" for y, n in sorted(by_year.items())) + "]")
    flagged = [c for c in cands if int(c["pole_bad_high"])]
    c1_flag = [c for c in flagged if c["C1"] and c["retrigger"] == 0]
    lines.append(f"  DATA FLAG (reported, not a gate): pole-bar high > {POLE_BAD_HIGH_X}x max(open, close) on "
                 f"{len(flagged):,} candidate rows ({len({c['ticker'] for c in flagged}):,} tickers); "
                 f"non-retrigger C1 trades affected: holdout {sum(1 for c in c1_flag if c['split'] == 'holdout')}, "
                 f"discovery {sum(1 for c in c1_flag if c['split'] == 'discovery')}  [column pole_bad_high]")
    return "\n".join(lines)


def run_step0(args) -> None:
    import pandas as pd
    path = (Path(args.out) if args.out else Path(args.data) / "out") / "candidates.tsv"
    df = pd.read_csv(path, sep="\t", keep_default_na=False, dtype=str)
    rows = []
    for rec in df.to_dict("records"):
        c = dict(rec)
        c["retrigger"] = int(rec["retrigger"])
        c["retrigger_chain"] = int(rec["retrigger_chain"])
        c["pole_bad_high"] = int(rec["pole_bad_high"])
        c["gap_over_1adr"] = rec["gap_over_1adr"] == "1"
        for cell in CELL_NAMES:
            c[cell] = rec[cell] == "1"
            c["first_" + cell] = int(rec["first_" + cell])
            c["first_chain_" + cell] = int(rec["first_chain_" + cell])
        rows.append(c)
    text = step0_text(rows)
    print(text)
    small = Path(args.small_out) if args.small_out else HERE / "out"
    small.mkdir(parents=True, exist_ok=True)
    (small / "step0.txt").write_text(text + "\n")


# ═════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stage", choices=["daily"])
    ap.add_argument("--data", required=True, help="DATA dir (daily_closes_all.csv.gz, small_pulls.psv, ...)")
    ap.add_argument("--out", help="large-output dir (default DATA/out)")
    ap.add_argument("--small-out", help="small-summary dir (default scripts/probes/_cb_backtest/out)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--step0", action="store_true", help="print the STEP 0 composition table from candidates.tsv and exit")
    ap.add_argument("--check-prescreen", type=int, default=0, metavar="N",
                    help="exhaustively prove the pre-screen on N tickers (real explain_watch on every night) and exit")
    ap.add_argument("--limit-tickers", type=int, default=0, help="dev: random subset of tickers")
    args = ap.parse_args(argv)
    if args.step0:
        run_step0(args)
    else:
        run_daily(args)


if __name__ == "__main__":
    main()
