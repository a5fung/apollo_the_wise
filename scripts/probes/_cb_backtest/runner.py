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
         failing-gate funnel; `cell_flags` for K in k5/k10/full/tl; `watch.tsv.gz`.
Stage 3  breakouts: E = the ticker's next bar (must be the next SPY session), breakout iff high(E) >
         pivot_K(D) (K = k5/k10/full are HORIZONTAL levels; K = tl is the down-sloping TRENDLINE, already projected
         to E by the module, and a night with no down-sloping line has no tl level and no tl candidate; #702 P1c);
         ONE TRADE PER BASE under two keys - the spec key (ticker, pole_date, K; later breaks are
         `retrigger=1`) and the drift-robust chain key (`retrigger_chain`: poles <= 3 sessions apart = one
         base); the daily CLOSE variant + EVERY exit arm on DISCOVERY rows ONLY (D <= 2024-12-31;
         holdout rows get no outcome here - they are joined once, after the P4 freeze); the minute fetch list.

Data integrity (all runner-side; the module is frozen): a night needs 130 CONSECUTIVE sessions (holes /
reused tickers fail as 'history'), forward walks stop at a hole, splits executing after the last session are
dropped from the raw-price factor, exchange test symbols are excluded.

Outputs: DATA/out/ (large) and scripts/probes/_cb_backtest/out/ (small summaries, < 1 MB).
No DB, no network, no prod access. Read-only on DATA except DATA/out/.

The pre-2022 Alpaca era (#702 selection test, `daily` only; a default run is unchanged by a byte - proved by hashing candidates /
watch / close-variant against the pinned run): `--raw-close FILE` measures the RAW factor per bar (raw / adjusted) instead of reading
`cb702_splits.psv`; `--breaks FILE` skips a night whose 130 bars straddle an identity break (counted `identity_break`); `--watch-start` /
`--watch-end` bound the watch nights D (the export keeps its later bars, so E and its forward sessions exist); `--era-label X` stamps
`split = X` (so `read_candidates` refuses the file). Outputs of such a run carry NO outcome when `--no-close-variant` is given.

`--keys com` (#702 P4b, every stage but `holdout`): run the CENTER-OF-MASS level `cb.com_level` (his 2026-10-18 rule; not one
of the module's four `KS`) INSTEAD of the registered four. Every output then carries the suffix `_com` (`watch_com.tsv.gz`,
`candidates_com.tsv`, `minute_fetch_list_com.tsv`, `trades_discovery_com.tsv.gz`, `discovery_report_com.txt`, ...) beside
the pinned files, which a default run still writes byte for byte (proved 2026-10-18: the seven content hashes and the
three other pinned outputs unchanged). `--no-close-variant` (daily) skips the CLOSE-variant walk, so a `--keys com` daily
run computes no outcome at all.

`--keys comb` (#702 P4b step 6b): `com` read only on the nights the stock CLOSED AT OR BELOW the level (`close(D) <= pivot_com`;
the condition is C0's, so every cell inherits it). A night that closed above the line is not a `comb` night, so it gets no
`comb` candidate (else its first break would consume the base's one trade under the spec key). `--keys com,comb` runs both in
one pass: ONE set of files with the suffix `_com_comb` (`candidates_com_comb.tsv`, `trades_discovery_com_comb.tsv.gz`, ...), the
`K` column carrying `com` and `comb`. The daily stage asserts the `comb` (ticker, E) pairs are a subset of `com`'s, so no
minute fetch beyond `com`'s is needed.

Per-regime tables (#702 P4b step 6b; reported beside, never deciding): `report` writes `regime_report{sfx}.tsv` and `holdout`
writes `regime_report_holdout.tsv` - for every (key, cell, K) of the headline table, n / mean R / share >= 5R per
`apollo_regime` (Bull / Choppy / Correcting / Crisis / missing) from the same mature walks, joined to D at read time from the
candidates table; no existing output changes by a byte.

#702 P5 (operator 2026-10-18): the HOLDOUT read's primary exit is HIS rule with the stalled breakouts cut (`cb.CUT_EXIT_ARMS`,
`c3_p33_t20_cut3`). The `p5` stage walks it - and the article's arm, his rule uncut and the +2R-only arm beside it - on the
`lod` stop at ORH5 over the spec key's first breaks of `tl` / `com` / `comb` (DISCOVERY only; `trades_discovery_p5.tsv.gz`,
`p5_report_discovery.{tsv,txt}`, new files); `holdout` runs the SAME function once on the holdout after its minute engine
(`trades_holdout_p5.tsv.gz`, `p5_report_holdout.{tsv,txt}`, P5 rows appended to `regime_report_holdout`), behind the same
freeze_check and once-only guard. The registered arm inside the P5 table is proved equal, per trade, to the minute stage's table.

#702 pre-read (operator 2026-10-19; docs/analysis/cb_2017_21_read_prereg_2026-10-19.md): `pre-read --data /Users/alvinfung/apollo_data/cb702_pre`
reads the frozen primary ONCE on the pre-2022 Alpaca era (`out/candidates_tl_com.tsv`, rows stamped `split = pre`, D 2017-03-01 .. 2021-12-31).
It is the holdout's chain on that file's first breaks of `tl` (decides) and `com` (beside): the registered minute engine
(`trades_pre_tl_com.tsv.gz`, `entries_pre_tl_com.tsv.gz`), the P5 walk (`trades_pre_p5.tsv.gz`), the per-trade cross-check of the registered
arm (exit 3 on a difference), then `p5_report_pre.{tsv,txt}` (DATA/out and the small-summary dir): per cell the §5 PASS / CAN'T TELL / FAIL
for the whole era and for 2020-21 alone, C1 first, with the by-year and QQQ-phase slices. It REFUSES (exit 2, the count printed) while
any (date, ticker) pair of that population is missing from `MINUTES/_done.psv` (the fetch lands later in DATA/minutes) - no partial read -
and while any of its outputs, or a crashed run's `.partial`, exists (read once). `--dry-run` counts candidate rows and pairs and opens no bar
and no minute row. Every other stage is unchanged (`read_candidates` / `run_minute_stage` only gained keyword arguments whose defaults are
the old behaviour).
"""
from __future__ import annotations

import argparse
import bisect
import csv
import glob
import gzip
import hashlib
import io
import multiprocessing as mp
import os
import random
import re
import sys
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agents.market_intelligence import anticipation as ant  # noqa: E402  (Family A control: simulate, build_mixed_path)
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402
# The plumbing the nightly shadow shares: ONE definition, in the module (`cb`, section 7). Re-bound here by name so
# `runner.<name>` keeps working for the callers and tests that read it.
from agents.market_intelligence.consolidation_breakout import (  # noqa: E402
    CELL_NAMES, KS, POLE_BAD_HIGH_X, POLE_DRIFT_MAX, breaks_out, chain_bases, contiguous_window_mask,
    cross_section_one_date, forward_window, gap_fields, is_mature, is_test_symbol, resolve_sectype,
    stamp_base_chain, stamp_retrigger,
)
from agents.market_intelligence.consolidation_breakout import fwd_end  # noqa: E402,F401  (not called here; kept as `runner.fwd_end`)

HERE = Path(__file__).resolve().parent
WATCH_START = date(2022, 3, 28)          # first watch night D (plan: discovery 2022-03-28 .. 2024-12-31)
DISCOVERY_END = date(2024, 12, 31)       # D <= this -> discovery; later -> holdout
NEW_FETCH_KS = ("tl",)                    # the K added after the first minute pull (#702 P1c): its (ticker, E) pairs not in
#                                           _done.psv are written to minute_fetch_list_delta.tsv (k5/k10/full were all pulled)
EXTRA_KS = cb.EXTRA_PIVOT_KEYS            # ("com", "comb"): the #702 P4b levels, run only on request (`--keys com,comb`), never in a default run
GATE_NAMES = cb.WATCH_GATES


def parse_keys(spec) -> tuple:
    """`--keys` -> the breakout levels a run uses. None / '' = the module's four (`KS`: what every pinned output carries);
    otherwise a comma list of names from KS + EXTRA_KS ('com' = the P4b center-of-mass level). Unknown or repeated names
    raise - a typo must not silently run the default."""
    if spec in (None, ""):
        return KS
    keys = tuple(k.strip() for k in str(spec).split(",") if k.strip())
    bad = [k for k in keys if k not in KS + EXTRA_KS]
    if bad or not keys or len(set(keys)) != len(keys):
        raise ValueError(f"--keys: expected distinct names from {KS + EXTRA_KS}, got {spec!r}")
    return keys


def out_suffix(keys) -> str:
    """'' for the registered four (every pinned file keeps its name); '_<key>[_<key>]' otherwise, so a `--keys com` run writes
    `candidates_com.tsv`, `trades_discovery_com.tsv.gz`, ... BESIDE the pinned files and never over them."""
    return "" if tuple(keys) == KS else "_" + "_".join(keys)


def run_keys(args) -> tuple:
    """(keys, suffix) of a run from its args (`keys` absent -> the default, so the tests' hand-built namespaces still work)."""
    keys = parse_keys(getattr(args, "keys", None))
    return keys, out_suffix(keys)
# The watch-row features / cross-section context copied onto every candidate row, in candidates.tsv column order.
CAND_FEATURES = ("prior_move", "base_len", "retrace", "base_depth", "tightening_ratio", "pole_sessions",
                 "median_dollar_vol20", "pole_day_vol_ratio", "pole_max_gap", "atr14", "atr14_slope",
                 "trigger_bar_range_adr", "inside_day", "rs_best", "rs_all", "grp_pct", "phase_qqq_10_20",
                 "phase_qqq_10_20_s5", "phase_spy_qqq_50", "apollo_regime")
# pre-screen windows: P in [i-45, i-10] (explain_watch), pole_low in [P-40, P] -> [i-85, i-10]
PS_HI_LO, PS_HI_HI = 45, 10
PS_LOW_LO, PS_LOW_HI = 85, 10

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


def minute_fetch_delta(fetch_rows: list, cands: list, done: "dict | None", ks=NEW_FETCH_KS) -> list:
    """The rows of the full fetch list (`{ticker, date, tier}`, same order and tier) that the NEW K's candidates
    need and `_done.psv` does not already hold. `done` = `load_done_pairs` ({(date_iso, ticker): status}, any status
    - ok or empty - counts as fetched) or None when no `_done.psv` exists (then nothing was fetched: every pair
    the new K needs is in the delta)."""
    need = {(c["ticker"], c["E"]) for c in cands if c["K"] in ks}
    have = done or {}
    return [r for r in fetch_rows if (r["ticker"], r["date"]) in need and (r["date"], r["ticker"]) not in have]


def acct_pct(realized_r: float, width_pct: float) -> float:
    """Account-% P&L at the article's sizing (harvest row 9): position = min(20% of account, 1% risk /
    stop width); P&L% of account = position x (pnl/fill) = position x R x width = R x min(0.20 x width, 0.01)."""
    return realized_r * min(0.20 * width_pct, 0.01)


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
    raw_c: "np.ndarray | None" = None   # RAW close per flat row (`--raw-close`, the pre-2022 Alpaca era); None = the split list


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


def load_raw_close(path: Path, D: "Daily") -> np.ndarray:
    """`--raw-close` (the #702 selection test's Alpaca-era export): a headerless `ticker,date,raw_close` file -> the RAW close of
    every flat row of `D`, aligned by (ticker, SPY session) so the file's own row order does not matter. The factor per bar is then
    raw / adjusted - what `factor_by_bar` derives from a split list for the 2022+ export. Asserts every row of `D` has exactly one
    raw close and the file has no row `D` lacks: a half-aligned factor would silently mis-set the $5 floor."""
    import pandas as pd
    df = pd.read_csv(path, header=None, names=["ticker", "d", "c"], dtype={"ticker": str, "c": float}, parse_dates=["d"],
                     keep_default_na=False)
    cal_days = np.array([d.toordinal() for d in D.cal], dtype=np.int64)
    day = df["d"].to_numpy().astype("datetime64[D]").astype(np.int64) + 719163
    ci = np.searchsorted(cal_days, day)
    assert ((ci < len(cal_days)) & (cal_days[np.minimum(ci, len(cal_days) - 1)] == day)).all(), "raw-close dates off the SPY calendar"
    tid = np.array([D.tid.get(t, -1) for t in df["ticker"].tolist()], dtype=np.int64)
    assert (tid >= 0).all(), "raw-close tickers absent from the export"
    big = len(cal_days) + 1
    flat_key = np.repeat(np.arange(len(D.tickers), dtype=np.int64), D.stop - D.start) * big + D.ci.astype(np.int64)
    assert (np.diff(flat_key) > 0).all(), "export rows are not (ticker, date)-sorted"
    key = tid * big + ci
    pos = np.searchsorted(flat_key, key)
    assert ((pos < len(flat_key)) & (flat_key[np.minimum(pos, len(flat_key) - 1)] == key)).all(), "raw-close row not in the export"
    assert len(np.unique(pos)) == len(pos) == len(flat_key), \
        f"raw-close rows ({len(pos):,}) must cover the export's rows ({len(flat_key):,}) exactly once"
    out = np.empty(len(flat_key))
    out[pos] = df["c"].to_numpy(dtype=float)
    assert np.isfinite(out).all() and (out > 0).all(), "non-positive / non-finite raw close"
    return out


def load_breaks(path: Path) -> dict:
    """`--breaks` (the identity guard of `scripts/probes/_qm_streams/ext_bars.py`): a `symbol_guard.tsv`-shaped table (tab-separated,
    header, columns `symbol` and `breaks` = 'YYYY-MM-DD:kind;...') -> {symbol: sorted array of break ordinals}. Symbols without a
    break are absent. Columns are read BY NAME, so a reordered table cannot shift the break column silently."""
    lines = Path(path).read_text().splitlines()
    head = lines[0].split("\t")
    k_sym, k_brk = head.index("symbol"), head.index("breaks")
    out = {}
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) <= k_brk or not f[k_brk]:
            continue
        out[f[k_sym]] = np.array(sorted(date.fromisoformat(x.split(":")[0]).toordinal() for x in f[k_brk].split(";")), dtype=np.int64)
    return out


def break_mask(d_ord: np.ndarray, brk: np.ndarray, window: int = cb.MIN_HISTORY) -> np.ndarray:
    """True at bar i when an identity break falls INSIDE the `window` bars ending at i, i.e. d[i-window+1] < break <= d[i] (a break dated
    on the window's first bar is the move from the bar BEFORE it, outside the window: `ext_c0.Series.break_in`, the same test). A symbol's
    series changes hands or is corrupted at a break; a night whose 130 bars straddle one is not evaluated."""
    n = len(d_ord)
    out = np.zeros(n, dtype=bool)
    if n >= window and len(brk):
        hi = np.searchsorted(brk, d_ord[window - 1:], side="right")
        lo = np.searchsorted(brk, d_ord[:n - window + 1], side="right")
        out[window - 1:] = hi - lo > 0
    return out


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
                d0_ci: int, *, prescreen: bool = True, extra_keys: tuple = (), fac: "np.ndarray | None" = None,
                breaks: "np.ndarray | None" = None, end_ci: "int | None" = None) -> dict:
    """Universe membership + RS inputs + watch features for every night from calendar index `d0_ci`.
    A night is admitted only if (a) the ticker is not an exchange test symbol, (b) `universe_ok`, and (c) the
    130 bars ending at it are consecutive SPY sessions - a night failing only (c) is counted under 'history'
    (the module's own 'history' gate is >= 130 sessions; here it is >= 130 CONSECUTIVE ones).
    `extra_keys` containing "com" adds the P4b center-of-mass level (`cb.com_level`, its `pivot_com*` / `com_*` keys) to
    every watch row; "comb" computes the same level and adds `pivot_comb*` (`cb.comb_fields`); a default run passes none and
    the rows are exactly `explain_watch`'s (a `com`-only run carries no `pivot_comb*` column).
    Three additive options for the pre-2022 Alpaca era (#702 selection test; all None = the pinned behavior, byte for byte): `fac` = the
    RAW/adjusted factor per bar (replaces the one `factor_by_bar` derives from `splits`); `breaks` = the symbol's identity-break ordinals
    (a night with a break inside its 130 bars is counted under 'identity_break', before the 'history' test, as `ext_c0` orders them);
    `end_ci` = the last calendar index scanned (inclusive). `aux` in the result counts the unknown-security-type universe members."""
    n = len(bars)
    if fac is None:
        fac = factor_by_bar(bars.dates, splits)
    skip = prescreen_skip_mask(bars.h, bars.l) if prescreen else np.zeros(n, dtype=bool)
    contig = contiguous_window_mask(cidx, cb.MIN_HISTORY)
    test_sym = is_test_symbol(ticker)
    start = int(np.searchsorted(cidx, d0_ci))
    stop = n if end_ci is None else int(np.searchsorted(cidx, end_ci, side="right"))
    brk = break_mask(np.array([d.toordinal() for d in bars.dates], dtype=np.int64), breaks) if breaks is not None else None
    counts: Counter = Counter()
    aux: Counter = Counter()
    uni_ci, rs = [], []
    watch = []
    for i in range(start, stop):
        yr = bars.dates[i].year
        if test_sym or not cb.universe_ok(bars, i, raw_factor=float(fac[i]), ticker=ticker, security_type=sectype):
            counts[(yr, "universe_fail")] += 1
            continue
        if brk is not None and brk[i]:
            counts[(yr, "identity_break")] += 1
            continue
        if not contig[i]:
            counts[(yr, "history")] += 1
            continue
        if not sectype:                                 # admitted on an UNKNOWN security type (as prod does): counted, never hidden
            aux[(yr, "unknown_type_night")] += 1
            aux[(yr, "unknown_type_ticker")] = 1
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
        if "com" in extra_keys or "comb" in extra_keys:
            feat.update(cb.com_level(bars, feat["pole_idx"], i, feat["adr20"]))
        if "comb" in extra_keys:
            feat.update(cb.comb_fields(feat))
        watch.append(feat)
    return {"ticker": ticker, "uni_ci": np.asarray(uni_ci, dtype=np.int32),
            "rs": np.asarray(rs, dtype=float).reshape(-1, 3), "watch": watch, "counts": counts, "aux": aux}


def _scan_job(t: int) -> dict:
    D: Daily = _G["D"]
    ticker = D.tickers[t]
    bars, cidx = bars_for(D, t)
    fac = None if D.raw_c is None else D.raw_c[int(D.start[t]):int(D.stop[t])] / bars.c
    breaks = _G.get("breaks")                            # None = no identity guard (the pinned run)
    return scan_ticker(ticker, bars, cidx, _G["splits"].get(ticker, []),
                       resolve_sectype(ticker, _G["mi_types"], _G["sic_types"]), _G["d0_ci"],
                       extra_keys=_G.get("extra_keys", ()), fac=fac,
                       breaks=None if breaks is None else breaks.get(ticker, np.zeros(0, dtype=np.int64)),
                       end_ci=_G.get("end_ci"))


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
        fwd, cut = forward_window(bars, cidx, e, H)
        row["fwd_hole"] = int(cut)
        row["fwd_bars"] = len(fwd)
        row["fwd_last_date"] = fwd.dates[-1].isoformat() if len(fwd) else ""
        if entry["status"] == "filled":
            for name, res in cb.walk_arms(entry, closes_before=bars.c[:e + 1], fwd=fwd, adr20=c["adr20"],
                                          horizon=H).items():
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
    keys, sfx = run_keys(args)
    no_cv = bool(getattr(args, "no_close_variant", False))
    log: list = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        log.append(msg)

    T0 = time.time()
    timers = {}

    def lap(name: str, t: float) -> None:
        timers[name] = time.time() - t
        say(f"[{name}: {timers[name]:.0f}s]")

    # The pre-2022 Alpaca-era options (#702 selection test; every one None = the pinned run, byte for byte):
    era_label = getattr(args, "era_label", None)
    raw_close = getattr(args, "raw_close", None)
    breaks_path = getattr(args, "breaks", None)
    watch_start = date.fromisoformat(args.watch_start) if getattr(args, "watch_start", None) else WATCH_START
    watch_end = date.fromisoformat(args.watch_end) if getattr(args, "watch_end", None) else None
    label_of = (lambda d: era_label) if era_label else split_label

    t = time.time()
    D = load_daily(data / "daily_closes_all.csv.gz")
    mi_types, regime = load_small(data / "small_pulls.psv")
    if raw_close:                                 # the raw factor is measured per bar; there is no split list to apply or to drop
        D.raw_c = load_raw_close(Path(raw_close), D)
        splits, n_splits_all, n_splits = {}, 0, 0
    else:
        n_splits_all = sum(len(v) for v in load_splits(data / "cb702_splits.psv").values())
        splits = load_splits(data / "cb702_splits.psv", through=D.cal[-1])       # not splits executing after the data ends
        n_splits = sum(len(v) for v in splits.values())
    sic_by_tk, sic_types = load_sic(data / "cb702_sic.psv")
    breaks = load_breaks(Path(breaks_path)) if breaks_path else None
    lap("load", t)
    if args.check_prescreen:
        say(check_prescreen(D, args.check_prescreen, args.workers, data / "liquid_tickers.txt"))
        return
    cal = D.cal
    last_ci = len(cal) - 1
    d0_ci = bisect.bisect_left(cal, watch_start)
    end_ci = None if watch_end is None else bisect.bisect_right(cal, watch_end) - 1
    spy_i, qqq_i = D.tid["SPY"], D.tid["QQQ"]
    spy, _ = bars_for(D, spy_i)
    qqq, _ = bars_for(D, qqq_i)
    assert spy.dates == cal and qqq.dates == cal, "QQQ/SPY must carry every session (the phase join is by DATE)"

    # ── pass 1: per ticker ───────────────────────────────────────────────────────────────────
    t = time.time()
    _G.update(D=D, splits=splits, mi_types=mi_types, sic_types=sic_types, d0_ci=d0_ci,
              extra_keys=tuple(k for k in keys if k in EXTRA_KS), breaks=breaks, end_ci=end_ci)
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
    aux: Counter = Counter()
    for r in res:
        counts.update(r["counts"])
        aux.update(r["aux"])
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
        row["split"] = label_of(cal[j])
        for k in keys:
            fl = cb.cell_flags(w, ctx, k=k)
            for cell in CELL_NAMES:
                row[f"{cell}_{k}"] = fl[cell]
            row[f"C1_s5_{k}"] = cb.cell_flags(w, ctx5, k=k)["C1"]
        watch_rows.append(row)
    base_cols = ["ticker", "watch_date", "ci", "split"] + [k for k in watch_all[0] if k not in ("ticker", "watch_date", "ci")] \
        if watch_all else ["ticker", "watch_date"]
    ctx_cols = ["rs_best", "rs_all", "grp_pct", "phase_qqq_10_20", "phase_qqq_10_20_s5", "phase_spy_qqq_50", "apollo_regime"]
    cell_cols = [f"{c}_{k}" for k in keys for c in CELL_NAMES + ("C1_s5",)]
    n_watch = write_tsv(out / f"watch{sfx}.tsv.gz", watch_rows, base_cols + ctx_cols + cell_cols, gz=True)
    lap("watch rows + cells", t)

    # ── candidates (breakouts) ────────────────────────────────────────────────────────────────
    t = time.time()
    cands, nonok = [], Counter()
    gap_rows = []
    com_ref_pairs: set = set()                    # (ticker, E) of every night the `com` level breaks - what `comb` must be a subset of
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
        for k in keys:
            pivot = w[f"pivot_{k}"]
            if not breaks_out(float(D.h[e]), pivot):             # also: no tl level that night -> no tl candidate
                continue
            if k in cb.CLOSED_BELOW_KEYS:
                com_ref_pairs.add((w["ticker"], cal[e_ci].isoformat()))      # the com break this night would be (same level)
                if not w[f"C0_{k}"]:                             # closed ABOVE the line on D: not a comb night, no candidate
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
            for f_ in CAND_FEATURES:
                c[f_] = w[f_]
            c["pivot_date"] = w[f"pivot_{k}_date"]
            c["pole_hi_over_oc"] = w["pole_hi_over_oc"]
            c["pole_bad_high"] = int(w["pole_hi_over_oc"] is not None and w["pole_hi_over_oc"] > POLE_BAD_HIGH_X)
            cands.append(c)
    stamp_retrigger(cands)
    stamp_base_chain(cands, chain_bases((w["ticker"], w["pole_ci"], w["pole_date"]) for w in watch_rows))
    # the chain key only ever MERGES bases: a spec retrigger is always a chain retrigger
    assert all(c["retrigger_chain"] == 1 for c in cands if c["retrigger"] == 1), "chain key is not a coarsening"
    comb_note = ""
    if "comb" in keys:                            # the minute fetch for comb is a subset of com's: no new fetch is needed
        comb_note = comb_fetch_check({(c["ticker"], c["E"]) for c in cands if c["K"] == "comb"}, com_ref_pairs,
                                     {(c["ticker"], c["E"]) for c in cands if c["K"] == "com"} if "com" in keys else None)
    lap("stage 3 breakouts", t)

    # ── CLOSE variant, discovery only ─────────────────────────────────────────────────────────
    t = time.time()
    if no_cv:                                     # `--no-close-variant`: no outcome of any kind is computed in this run
        cv_rows, n_cv = [], 0
        for c in cands:
            c["overlap_open"] = ""
    else:
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
        n_cv = write_tsv(out / f"close_variant_discovery{sfx}.tsv.gz", cv_rows, cv_cols, gz=True)
    lap("close variant + 15 exit arms (discovery)" if not no_cv else "close variant SKIPPED (--no-close-variant)", t)

    # ── write candidates / fetch list / summaries ──────────────────────────────────────────────
    t = time.time()
    cand_cols = (["ticker", "D", "E", "K", "pole_date", "pole_ci", "pivot", "pivot_date", "adr20", "gap_open_pct",
                  "gap_over_1adr", "retrigger", "retrigger_chain", "base_id", "overlap_open", "split",
                  "pole_hi_over_oc", "pole_bad_high"]
                 + list(CELL_NAMES) + ["C1_s5"] + ["first_" + c for c in CELL_NAMES]
                 + ["first_chain_" + c for c in CELL_NAMES]
                 + ["open_E", "high_E", "low_E", "close_E", "vol_E", "adv20_vol_D", "breakout_vol_x"]
                 + list(CAND_FEATURES))
    cands.sort(key=lambda c: (c["E"], c["ticker"], c["K"]))
    write_tsv(out / f"candidates{sfx}.tsv", cands, cand_cols)
    write_tsv(out / f"gap_in_bars{sfx}.tsv", gap_rows, ["ticker", "D", "status", "next_bar_date", "expected_E"])
    fetch = {}
    for c in cands:
        tier = int(any(c[x] for x in CELL_NAMES if x != "C0"))
        key = (c["ticker"], c["E"])
        fetch[key] = max(fetch.get(key, 0), tier)
    fetch_rows = [{"ticker": k[0], "date": k[1], "tier": v} for k, v in sorted(fetch.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    write_tsv(out / f"minute_fetch_list{sfx}.tsv", fetch_rows, ["ticker", "date", "tier"])
    minutes_dir = Path(args.minutes) if args.minutes else data / "minutes"
    done = load_done_pairs(minutes_dir) if minutes_dir.is_dir() else None
    delta_ks = NEW_FETCH_KS if sfx == "" else keys        # a `--keys` run: the pairs ITS levels need that are not on disk
    delta_rows = minute_fetch_delta(fetch_rows, cands, done, ks=delta_ks)
    write_tsv(out / f"minute_fetch_list_delta{sfx}.tsv", delta_rows, ["ticker", "date", "tier"])
    write_tsv(small / f"universe_by_date{sfx}.tsv", uni_rows,
              ["date", "universe_n", "members_with_group", "groups_ge10", "watch_rows", "phase_qqq_10_20_s1",
               "phase_qqq_10_20_s5", "phase_spy_qqq_50", "apollo_regime"])

    # funnel
    years = sorted({y for (y, _g) in counts})
    names = ["universe_fail", "prescreen_skip"] + list(GATE_NAMES) + ["pass"]
    if breaks is not None:                        # an identity guard was passed: its exclusions are a funnel row of their own
        names.insert(1, "identity_break")
    funnel = []
    tot_by_year = {y: sum(v for (yy, _g), v in counts.items() if yy == y) for y in years}
    for nm in names:
        funnel.append({"stage": nm, "total": sum(v for (_y, g), v in counts.items() if g == nm),
                       **{str(y): counts.get((y, nm), 0) for y in years}})
    funnel.append({"stage": "TOTAL ticker-nights", "total": sum(tot_by_year.values()),
                   **{str(y): tot_by_year[y] for y in years}})
    write_tsv(small / f"gate_counts{sfx}.tsv", funnel, ["stage", "total"] + [str(y) for y in years])
    if raw_close:                                 # the Alpaca-era run: how many universe members carry NO security type (admitted, counted)
        ayears = sorted({y for (y, _k) in aux})
        write_tsv(small / f"universe_types{sfx}.tsv",
                  [{"year": y, "unknown_type_nights": aux.get((y, "unknown_type_night"), 0),
                    "unknown_type_tickers": aux.get((y, "unknown_type_ticker"), 0)} for y in ayears],
                  ["year", "unknown_type_nights", "unknown_type_tickers"])
    lap("write outputs", t)

    # ── report ─────────────────────────────────────────────────────────────────────────────────
    tot = sum(tot_by_year.values())
    uni_total = tot - sum(v for (_y, g), v in counts.items() if g in ("universe_fail", "history", "identity_break"))
    say("")
    say(f"DATA INTEGRITY: {D.n_hole_tickers:,} of {len(D.tickers):,} tickers have a missing SPY session inside their span "
        f"({D.n_holes:,} holes); a night is admitted only if its 130 bars are consecutive sessions, and a forward "
        f"walk stops at the first hole; splits executing after {cal[-1]} dropped: {n_splits_all - n_splits} of "
        f"{n_splits_all} (not yet in the adjusted series); exchange test symbols excluded: "
        f"{sum(1 for x in D.tickers if is_test_symbol(x))} tickers present in the export")
    if raw_close or breaks is not None or era_label or watch_end is not None:
        say(f"  ERA OPTIONS: raw factor {'measured per bar from ' + str(raw_close) if raw_close else 'from the split list'}; identity guard "
            f"{'on (' + format(len(breaks), ',') + ' symbols carry a break)' if breaks is not None else 'off'}; watch nights "
            f"{watch_start}..{watch_end or 'end of data'}; era label {era_label or 'discovery/holdout'}")
    say(f"GATE FUNNEL (ticker-nights with D >= {watch_start}; each night lands in exactly ONE row)")
    say(table([[r["stage"], f"{r['total']:,}", f"{r['total'] / tot:.2%}" if tot else ""] for r in funnel],
              ["stage", "nights", "share"]))
    say(f"  'history' = universe_ok passed but the 130 bars are NOT consecutive sessions (a hole / reused ticker); "
        f"universe members (nights) = total - universe_fail - history: {uni_total:,};  pre-screen skips are nights the real gate would fail "
        f"at prior_move (proved by --check-prescreen);  prior_move total incl. skips = "
        f"{counts_total(counts, 'prior_move') + counts_total(counts, 'prescreen_skip'):,}")
    say("")
    say(f"WATCH ROWS: {n_watch:,} (ticker x D) over {len({w['ticker'] for w in watch_rows}):,} tickers; "
        + (f"era {era_label} {len(watch_rows):,}" if era_label else
           f"discovery {sum(1 for w in watch_rows if w['split'] == 'discovery'):,} / "
           f"holdout {sum(1 for w in watch_rows if w['split'] == 'holdout'):,}"))
    say(f"  universe size per date: min {min(r['universe_n'] for r in uni_rows):,} "
        f"median {int(np.median([r['universe_n'] for r in uni_rows])):,} max {max(r['universe_n'] for r in uni_rows):,}; "
        f"watch rows with no group (grp_pct None): {sum(1 for w in watch_rows if w['grp_pct'] is None):,}; "
        f"rs_best None: {sum(1 for w in watch_rows if w['rs_best'] is None):,}")
    hdr = ["cell"] + [f"{k}" for k in keys]
    say("  watch nights with the cell true (all splits):")
    say(table([[c] + [sum(1 for w in watch_rows if w[f'{c}_{k}']) for k in keys] for c in CELL_NAMES + ("C1_s5",)], hdr))
    if {"k5", "tl"} <= set(keys):
        say("  tl vs the horizontal levels - the tl C0 population is a SUBSET (a night with no down-sloping line has no tl level), "
            "so a tl-vs-k5 difference is level AND population:")
        say(tl_population_text(watch_rows))
    if era_label and ("com" in keys or "comb" in keys):
        say("  (the com / comb level tables and STEP 0 are discovery-vs-holdout splits; under --era-label every row is one era, so they are not printed)")
    elif "com" in keys or "comb" in keys:
        say("  com - the center-of-mass level (the median of the base's highs; #702 P4b): where it sits against the watch night's "
            "close and high, per split (a level UNDER the close breaks out on any up-day):")
        say(com_population_text(watch_rows))
    if "comb" in keys:
        say("  comb - com, read only on the nights the stock CLOSED AT OR BELOW the level (C0_comb); a night that closed above it "
            "gets no comb candidate:")
        say(comb_population_text(watch_rows, cands))
        say(comb_note)
    say("")
    bad = [w for w in watch_rows if w["pole_hi_over_oc"] is not None and w["pole_hi_over_oc"] > POLE_BAD_HIGH_X]
    say(f"  DATA FLAG: {len(bad):,} watch rows on {len({w['ticker'] for w in bad}):,} tickers have a pole bar whose high is "
        f"> {POLE_BAD_HIGH_X}x max(open, close) (a suspect print can become pole_high); C1_{keys[0]} nights among them: "
        f"{sum(1 for w in bad if w[f'C1_{keys[0]}'])}")
    say("")
    say(f"BREAKOUT CANDIDATES (high(E) > pivot_K(D)): {len(cands):,} rows "
        f"(spec key {sum(1 for c in cands if c['retrigger'] == 0):,} trades + {sum(1 for c in cands if c['retrigger'] == 1):,} retriggers; "
        f"chain key {sum(1 for c in cands if c['retrigger_chain'] == 0):,} trades + {sum(1 for c in cands if c['retrigger_chain'] == 1):,} retriggers); "
        f"no-E statuses (watch rows, no trade): {dict(nonok)}")
    if not era_label:
        say(step0_text(cands, keys))
    say("")
    if no_cv:
        say("CLOSE VARIANT: SKIPPED (--no-close-variant) - this run computed no outcome; `overlap_open` is blank")
    else:
        say(f"CLOSE VARIANT (discovery): {n_cv:,} rows; "
            + str(dict(Counter(r["close_status"] for r in cv_rows)))
            + f"; walks cross into the holdout period (fwd_last_date > {DISCOVERY_END}): "
            f"{sum(1 for r in cv_rows if r['close_status'] == 'filled' and r['fwd_last_date'] > DISCOVERY_END.isoformat()):,} filled rows; "
            f"forward walk cut at a hole (ends 'degraded'): {sum(1 for r in cv_rows if r['close_status'] == 'filled' and r['fwd_hole']):,} filled rows")
    say(f"MINUTE FETCH LIST: {len(fetch_rows):,} unique (ticker, E) pairs over {len({r['date'] for r in fetch_rows}):,} dates "
        f"(tier 1 = any cell C1..C7/report cells true: {sum(1 for r in fetch_rows if r['tier']):,}; "
        f"non-retrigger only: {len({(c['ticker'], c['E']) for c in cands if c['retrigger'] == 0}):,})"
        + ("" if sfx == "" else "; per era: " + ", ".join(
            f"{sp} {len({(c['ticker'], c['E']) for c in cands if c['split'] == sp}):,}" for sp in ((era_label,) if era_label else ("discovery", "holdout")))))
    new_pairs = {(c["ticker"], c["E"]) for c in cands if c["K"] in delta_ks}
    say(f"MINUTE FETCH DELTA (pairs the {'/'.join(delta_ks)} candidates need that _done.psv does not hold; "
        f"{'no _done.psv under ' + str(minutes_dir) + ' - every pair counts as not fetched' if done is None else format(len(done), ',') + ' pairs in _done.psv'}): "
        f"{len(delta_rows):,} pairs over {len({r['date'] for r in delta_rows}):,} dates "
        f"(of {len(new_pairs):,} {'/'.join(delta_ks)} pairs; tier 1: {sum(1 for r in delta_rows if r['tier']):,}"
        + ("" if sfx == "" else "; per era: " + ", ".join(
            f"{sp} {sum(1 for r in delta_rows if label_of(date.fromisoformat(r['date'])) == sp):,}" for sp in ((era_label,) if era_label else ("discovery", "holdout"))))
        + f") -> {out / f'minute_fetch_list_delta{sfx}.tsv'}")
    say(f"WALL TIME: {time.time() - T0:.0f}s total  " + "  ".join(f"{k}={v:.0f}s" for k, v in timers.items()))
    (small / f"run_summary{sfx}.txt").write_text("\n".join(log) + "\n")


def counts_total(counts: Counter, gate: str) -> int:
    return sum(v for (_y, g), v in counts.items() if g == gate)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# STEP 0 - composition before any outcome
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _step0_block(rows: list, retrig: str, first: str, keys=KS) -> str:
    body = []
    for cell in CELL_NAMES:
        r = [cell]
        for k in keys:
            sub = [c for c in rows if c["K"] == k and c[cell]]
            tr = [c for c in sub if c[retrig] == 0]
            r += [f"{len(tr)}", f"{sum(1 for c in sub if c[first + cell] == 1)}",
                  f"{sum(1 for c in tr if c['gap_over_1adr'])}"]
        body.append(r)
    return table(body, ["cell"] + [f"{k}:{x}" for k in keys for x in ("trades", "first", "gap>1adr")])


def step0_text(cands: list, keys=KS) -> str:
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
        lines.append(_step0_block(rows, "retrigger", "first_", keys))
        lines.append(f"  -- CHAIN key (poles <= {POLE_DRIFT_MAX} sessions apart = one base): "
                     f"{sum(1 for c in rows if c['retrigger_chain'] == 0):,} trades --")
        lines.append(_step0_block(rows, "retrigger_chain", "first_chain_", keys))
    for label, retrig in (("SPEC key", "retrigger"), ("CHAIN key", "retrigger_chain")):
        h = [c for c in cands if c["split"] == "holdout" and c[retrig] == 0 and c["C1"]]
        by_year = Counter(c["E"][:4] for c in h)
        lines.append(f"  GO/NO-GO input, {label} (plan: C1 needs >= 30 holdout trades): "
                     + ", ".join(f"{k}: {sum(1 for c in h if c['K'] == k)}" for k in keys)
                     + "   [C1 holdout trades by year, all K: " + ", ".join(f"{y}={n}" for y, n in sorted(by_year.items())) + "]")
    for kk in ("com", "comb"):                     # entry-time fact: how often the level is already under the open / close of E
        if kk not in keys:
            continue
        for split in ("holdout", "discovery"):
            rows = [c for c in cands if c["split"] == split and c["K"] == kk and c["retrigger"] == 0]
            n_open = sum(1 for c in rows if c["open_E"] > c["pivot"])
            c1 = [c for c in rows if c["C1"]]
            lines.append(f"  {kk.upper()} LEVEL vs the breakout day, {split}, spec-key trades: {len(rows):,} first breaks; open(E) already above "
                         f"the level on {n_open:,} ({(n_open / len(rows) if rows else 0):.0%}); C1: {len(c1)} first breaks, "
                         f"open above the level on {sum(1 for c in c1 if c['open_E'] > c['pivot'])}")
    flagged = [c for c in cands if int(c["pole_bad_high"])]
    c1_flag = [c for c in flagged if c["C1"] and c["retrigger"] == 0]
    lines.append(f"  DATA FLAG (reported, not a gate): pole-bar high > {POLE_BAD_HIGH_X}x max(open, close) on "
                 f"{len(flagged):,} candidate rows ({len({c['ticker'] for c in flagged}):,} tickers); "
                 f"non-retrigger C1 trades affected: holdout {sum(1 for c in c1_flag if c['split'] == 'holdout')}, "
                 f"discovery {sum(1 for c in c1_flag if c['split'] == 'discovery')}  [column pole_bad_high]")
    return "\n".join(lines)


def tl_population_text(watch_rows: list) -> str:
    """The `tl` line is drawn from the base's highest high (the pole top, or a later wick that topped it); it is
    absent only while that high is under 3 sessions old, so its C0 population is a SUBSET of the horizontal levels'.
    A tl-vs-k5 difference can therefore mix the entry LEVEL with a change of POPULATION - this table is printed so the
    P4 read states the no-line count per split next to it (#702 P1c review, 10-17). `anchored on a later wick` = the
    nights whose line starts at a base high above the pole top, not at the pole top itself."""
    body = []
    for split in ("discovery", "holdout"):
        ws = [w for w in watch_rows if w["split"] == split]
        body.append([split, f"{len(ws):,}", f"{sum(1 for w in ws if w['C0_k5']):,}", f"{sum(1 for w in ws if w['C0_tl']):,}",
                     f"{sum(1 for w in ws if w['pivot_tl'] is None):,}",
                     f"{sum(1 for w in ws if w.get('tl_anchor_idx') is not None and w['tl_anchor_idx'] != w['pole_idx']):,}"])
    return table(body, ["split", "watch nights", "C0_k5", "C0_tl", "tl: no line", "tl anchored on a later wick"])


def com_population_text(watch_rows: list) -> str:
    """Where the `com` level (the median of the base's highs, #702 P4b) sits on the watch night, per split: nights with a
    level, nights where it is UNDER the close (any up-day on E "breaks out"), under the high, and the median distance
    of the level below `pivot_full` in ADR20 units - the number to put beside any com-vs-k5 comparison."""
    body = []
    for split in ("discovery", "holdout"):
        ws = [w for w in watch_rows if w["split"] == split]
        have = [w for w in ws if w.get("pivot_com") is not None]
        gap = [(w["pivot_full"] - w["pivot_com"]) / w["pivot_full"] / w["adr20"] for w in have if w["adr20"] > 0]
        body.append([split, f"{len(ws):,}", f"{len(have):,}", f"{sum(1 for w in have if w['pivot_com'] < w['close']):,}",
                     f"{sum(1 for w in have if w['pivot_com'] < w['pivot_k5']):,}",
                     f"{float(np.median(gap)):.2f}" if gap else ""])
    return table(body, ["split", "watch nights", "com: level", "level < close(D)", "level < k5", "median ADR below pivot_full"])


def comb_population_text(watch_rows: list, cands: list) -> str:
    """The `comb` reading of `com` (#702 P4b step 6b), per split: watch nights with a level, those the stock closed AT OR BELOW
    it on (C0_comb - the nights `comb` can trade), the share that closed ABOVE it (dropped), and the breakout candidates each
    reading produced (`com` is counted only when this run carries it)."""
    body = []
    for split in ("discovery", "holdout"):
        ws = [w for w in watch_rows if w["split"] == split]
        have = [w for w in ws if w.get("pivot_com") is not None]
        below = sum(1 for w in ws if w.get("C0_comb"))
        n_comb = sum(1 for c in cands if c["split"] == split and c["K"] == "comb")
        n_com = sum(1 for c in cands if c["split"] == split and c["K"] == "com")
        body.append([split, f"{len(ws):,}", f"{len(have):,}", f"{below:,}",
                     f"{(len(have) - below) / len(have):.0%}" if have else "", f"{n_comb:,}",
                     f"{n_com:,}" if any(c["K"] == "com" for c in cands) else "-"])
    return table(body, ["split", "watch nights", "com: level", "closed at/below (comb)", "closed above (dropped)",
                        "comb candidates", "com candidates"])


def comb_fetch_check(comb_pairs: set, com_pairs: set, com_cand_pairs: "set | None" = None) -> str:
    """The `comb` minute-fetch list is a subset of `com`'s (the same level on fewer nights), so a `com` fetch already covers
    it. `com_pairs` = every (ticker, E) the com level breaks on (computed whether or not the run carries K=com); when the run
    carries K=com its own candidate pairs must equal it. Raises AssertionError on a comb pair com does not have."""
    extra = comb_pairs - com_pairs
    if extra:
        raise AssertionError(f"comb fetch pairs outside com's: {len(extra):,} (first {sorted(extra)[:3]}) - a new minute fetch would be needed")
    if com_cand_pairs is not None and com_cand_pairs != com_pairs:
        raise AssertionError(f"the K=com candidate pairs ({len(com_cand_pairs):,}) differ from the com level's breaks ({len(com_pairs):,})")
    return (f"COMB FETCH CHECK: {len(comb_pairs):,} comb (ticker, E) pairs, ALL among com's {len(com_pairs):,} "
            f"({len(com_pairs) - len(comb_pairs):,} com pairs are nights that closed above the line) - no minute fetch beyond com's")


def run_step0(args) -> None:
    import pandas as pd
    keys, sfx = run_keys(args)
    path = (Path(args.out) if args.out else Path(args.data) / "out") / f"candidates{sfx}.tsv"
    df = pd.read_csv(path, sep="\t", keep_default_na=False, dtype=str)
    rows = []
    for rec in df.to_dict("records"):
        c = dict(rec)
        c["retrigger"] = int(rec["retrigger"])
        c["retrigger_chain"] = int(rec["retrigger_chain"])
        c["pole_bad_high"] = int(rec["pole_bad_high"])
        c["gap_over_1adr"] = rec["gap_over_1adr"] == "1"
        c["open_E"], c["pivot"] = float(rec["open_E"]), float(rec["pivot"])
        for cell in CELL_NAMES:
            c[cell] = rec[cell] == "1"
            c["first_" + cell] = int(rec["first_" + cell])
            c["first_chain_" + cell] = int(rec["first_chain_" + cell])
        rows.append(c)
    text = step0_text(rows, keys)
    print(text)
    small = Path(args.small_out) if args.small_out else HERE / "out"
    small.mkdir(parents=True, exist_ok=True)
    (small / f"step0{sfx}.txt").write_text(text + "\n")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# P2b - THE MINUTE STAGE: entries, exits, controls, sensitivities (DISCOVERY outcomes)
#
#   minute         every DISCOVERY candidate with minutes: the four minute entry variants -> day-0 walk -> every
#                  exit arm, the two controls, the sensitivities; the daily CLOSE variant joined in from the
#                  daily stage. Writes DATA/out/trades_discovery.tsv.gz + entries_discovery.tsv.gz.
#   step0-entries  HOLDOUT composition ONLY (entry-time facts; no day-0 walk, no exit, no outcome, no daily bars).
#   holdout        the `minute` engine on the HOLDOUT, behind freeze_check(). BUILT, NOT RUN: it is run once, after
#                  the P4 freeze.
#   report         the discovery read: month-block bootstrap CIs, tails, slices, controls, sensitivities.
#
# Every number that DECIDES (entries, day-0, exits) is a call into the frozen module. The runner adds only: the
# minute reader, the schedule, the two CONTROL adapters, the sensitivity bookkeeping, the maturity label, the tables.
# ═════════════════════════════════════════════════════════════════════════════════════════════
MINUTE_VARIANTS = cb.ENTRY_VARIANTS                       # orh1 orh5 orh60 pivot
ALL_VARIANTS = MINUTE_VARIANTS + ("close",)               # + the daily CLOSE variant (daily stage's rows, joined)
HEADLINE_VARIANT = "orh5"                                 # plan: primary entry = 5-minute opening-range high
HORIZON = cb.EXIT_HORIZON                                 # 120 sessions
H60 = 60                                                  # sensitivity: the primary arm re-walked at 60 sessions
SETTLE_BARS = ant.SETTLE_FORWARD_BARS                     # Family A: 5 forward daily bars (SETTLE_RULE's day-5 time stop)
PRIOR_CLOSE_DAYS = 40                                     # live_tracker._load_exit_state: 40 calendar days of pre-entry closes (#548)
FAMILY_A_ARM = "ctl_family_a_settle"
APOLLO_ARM = "ctl_apollo_today"
CONTROL_ARMS = (FAMILY_A_ARM, APOLLO_ARM)
ALL_ARMS = tuple(cb.ARMS) + CONTROL_ARMS
FLOORS = ((0.0, "floor_0"), (0.25, "floor_025"), (0.5, "floor_05"), (0.75, "floor_075"), (1.0, "floor_1"))
DATA_ABSTAINS = ("no_minutes", "minute_daily_mismatch", "minute_high_below_pivot")   # the entry abstains that say "the data disagrees"
DATA_ABSTAIN_MAX = 0.05                                   # plan Verification: more than 5% of these BLOCKS the read
BOOT_DRAWS, BOOT_SEED = 2000, 702                         # month-block bootstrap: 2,000 resamples, fixed seed
FREEZE_MARK = "<!-- FREEZE -->"
REPORT_NAME = "discovery_report"

FLAG_FIELDS = ("gap_over_1adr", "phase_qqq_10_20", "phase_qqq_10_20_s5", "phase_spy_qqq_50", "inside_day")
FLOAT_FIELDS = ("pivot", "adr20", "high_E", "low_E", "open_E", "close_E", "atr14", "median_dollar_vol20")

# ── output layouts ────────────────────────────────────────────────────────────────────────────────
CELL_COLS = list(CELL_NAMES) + ["C1_s5"]
TRADE_CAND_COLS = (["ticker", "D", "E", "K", "split", "year", "month", "retrigger", "retrigger_chain"] + CELL_COLS
                   + ["gap_over_1adr", "adr20", "atr14", "median_dollar_vol20", "phase_qqq_10_20",
                      "phase_qqq_10_20_s5", "phase_spy_qqq_50"])
TRADE_VAR_COLS = ["variant", "fill_minute", "width_pct", "day0_stopped", "abstain_reason", "atr14_wide"] + [n for _f, n in FLOORS]
TRADE_ARM_COLS = ["arm", "status", "realized_r", "pnl_adr", "acct_pct", "sessions_held", "mature", "open_mark", "beabove",
                  "fwd_bars", "fwd_hole", "arm_note"]
TRADE_SENS_COLS = ["r_h60", "st_h60", "mature_h60", "cap_stop", "cap_status", "cap_realized_r", "cap_pnl_adr",
                   "cap_acct_pct", "cap_mature", "cap_sessions_held"]
TRADE_COLS = TRADE_CAND_COLS + TRADE_VAR_COLS + TRADE_ARM_COLS + TRADE_SENS_COLS
ENTRY_COLS = (["ticker", "D", "E", "K", "split", "variant", "status", "reason", "minutes_state", "level", "fill", "stop",
               "width_pct", "fill_minute", "day0_stopped", "day0_exit_price", "day0_exit_minute", "atr14_wide",
               "retrigger", "retrigger_chain", "base_id"]
              + ["first_" + c for c in CELL_NAMES] + ["first_chain_" + c for c in CELL_NAMES] + CELL_COLS
              + ["gap_over_1adr", "pole_bad_high"])
# STEP 0 (holdout) - entry-time facts ONLY. No fill price, stop, day-0 or any outcome column exists in this layout.
COMPOSITION_COLS = (["ticker", "D", "E", "K", "split", "variant", "status", "reason", "minutes_state", "width_pct",
                     "fill_minute", "retrigger", "retrigger_chain"] + CELL_COLS)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# pure helpers (unit-tested)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def arm_result(res: dict, *, width: float, n_fwd: int, horizon: int = HORIZON) -> dict:
    """One `walk_exit` / `day0_result_to_outcome` result as a row of the trades table."""
    mature = is_mature(res["status"], n_fwd, horizon)
    return {"status": res["status"], "realized_r": res["realized_r"], "pnl_adr": res["pnl_adr"],
            "acct_pct": acct_pct(res["realized_r"], width), "sessions_held": res["sessions_held"],
            "mature": mature, "open_mark": not mature,
            "beabove": int(any(ev[1] == "be_above_close" for ev in res["events"])), "note": ""}


def walk_arms(entry: dict, *, closes_before, fwd: "cb.DailyBars", adr20: float, horizon: int = HORIZON,
              arms: "dict | None" = None) -> dict:
    """{arm: arm_result} for ONE filled entry: the module's shared `cb.walk_arms` (a day-0 stop-out is booked once
    by `day0_result_to_outcome` and is the outcome of EVERY arm; otherwise `walk_exit` per arm with closes_before =
    closes through E, whose last is E's own close) with each raw result turned into a trades-table row."""
    width, n_fwd = entry["width_pct"], len(fwd)
    raw = cb.walk_arms(entry, closes_before=closes_before, fwd=fwd, adr20=adr20, horizon=horizon, arms=arms)
    return {name: arm_result(res, width=width, n_fwd=n_fwd, horizon=horizon) for name, res in raw.items()}


def minute_dicts(mb: "cb.MinuteBars") -> list:
    """The {m,o,h,l,c} dict bars `anticipation.build_mixed_path` and `live_fill_counterfactuals.walk_arm` read."""
    return [{"m": int(m), "o": float(o), "h": float(h), "l": float(l), "c": float(c)}
            for m, o, h, l, c in zip(mb.minute.tolist(), mb.o.tolist(), mb.h.tolist(), mb.l.tolist(), mb.c.tolist())]


def fill_position(mb: "cb.MinuteBars", fill_minute: int) -> int:
    """Index of the fill minute inside the session's minute bars (the entry came FROM this bar)."""
    p = int(np.searchsorted(mb.minute, fill_minute))
    if p >= len(mb) or int(mb.minute[p]) != int(fill_minute):
        raise ValueError(f"fill minute {fill_minute} is not a stored minute bar")
    return p


def _control_result(realized_r: float, risk: float, fill: float, adr20: float, width: float, status: str,
                    held, mature: bool, note: str = "") -> dict:
    """A control's row, in the SAME R unit as every cb arm: R = pnl / (fill - the entry's own stop)."""
    return {"status": status, "realized_r": realized_r, "pnl_adr": realized_r * risk / (fill * adr20),
            "acct_pct": acct_pct(realized_r, width), "sessions_held": held, "mature": mature,
            "open_mark": not mature, "beabove": "", "note": note}


def family_a_control(*, mdicts: list, fill_pos: int, fwd: "cb.DailyBars", fill: float, stop: float,
                     adr20: float) -> dict:
    """CONTROL 1 - Family A's `SETTLE_RULE` (+1R half, +3R half, day-5 time stop) on THIS entry and THIS stop, through
    the shipped harvest evaluator: `anticipation.build_mixed_path` (day-0 MINUTES after the fill bar, then the daily
    forward bars) -> `anticipation.simulate(..., 'pess')`. Comparable to Confirm's +0.10R. It walks day 0 itself, so
    it is NEVER short-circuited by the module's day-0 stop-out (a +1R minute partial can precede the stop). The
    forward daily bars are the first SETTLE_BARS (5) of the walk window. R is `simulate`'s own (units of fill - stop).
    Mature = 5 forward bars existed (the day-5 time stop fired) or the position was fully out BEFORE the last
    available forward day; an exit ON the last available day is ambiguous (stop vs end-of-data mark) -> open mark."""
    daily = [{"o": float(fwd.o[k]), "h": float(fwd.h[k]), "l": float(fwd.l[k]), "c": float(fwd.c[k])}
             for k in range(min(SETTLE_BARS, len(fwd)))]
    path = ant.build_mixed_path(mdicts, fill_pos, daily)
    risk, width = fill - stop, (fill - stop) / fill
    if not path:
        return _control_result(0.0, risk, fill, adr20, width, "no_path", 0, False, "no minutes after the fill and no forward bar")
    out = ant.simulate(fill, stop, path, ant.SETTLE_RULE, "pess")
    if out is None:
        return _control_result(0.0, risk, fill, adr20, width, "no_risk", 0, False, "risk <= 0")
    realized_r, _captured, fills = out
    last_day = max(d for d, _f in fills) if fills else 0
    mature = len(daily) >= SETTLE_BARS or last_day < len(daily)
    return _control_result(float(realized_r), risk, fill, adr20, width, "settled" if mature else "open_mark",
                           last_day, mature)


_APOLLO_RULES = None


def apollo_rules() -> dict:
    """The exit stack the live MAGNA53 path runs NOW: `rule_eras.exit_rules_as_of(DEPTH_EXIT_LIVE_DATE, 'magna53',
    'depth')` = +8 ORB-R partial, price-armed breakeven at +3 ORB-R, SMA trail with the DEPTH exit (a close below the
    line sells at the NEXT open; the resting stop sits one ADR20 under the line). Read from the repo's own era table,
    never hand-typed."""
    global _APOLLO_RULES
    if _APOLLO_RULES is None:
        from agents.market_intelligence import rule_eras
        if rule_eras.DEPTH_EXIT_LIVE_DATE is None:
            raise RuntimeError("rule_eras.DEPTH_EXIT_LIVE_DATE is None: the depth exit is not recorded as live, so "
                               "'Apollo as it runs today' must be re-specified before this control is walked (or pass --no-apollo)")
        _APOLLO_RULES = rule_eras.exit_rules_as_of(rule_eras.DEPTH_EXIT_LIVE_DATE, "magna53", "depth")
    return _APOLLO_RULES


def apollo_walk_inputs(fill: float, stop: float, adr20: float) -> tuple:
    """(target, walk_arm kwargs) for 'Apollo as it runs today' on a Consolidation Breakout fill.

    FRAME DECISION (stated because a CB fill has no ORB): `walk_arm` is parameterised in ORB-R (stop = entry - 2 ORB-R,
    partial at +8 ORB-R, breakeven at +3 ORB-R), and a CB entry is not an opening-range entry - the first-minute low
    is not its risk. So the live ladder is anchored on the CB trade's OWN placed risk, exactly the relation the live
    path has: 1 placed-risk R = 2 ORB-R (recut.py: "1 money-R = 2 ORB-R"). The ORB-low stand-in is therefore the
    midpoint of fill and the CB stop, which makes `fill - 2 x (fill - orb_low) == the CB stop`: same entry, same stop,
    same R unit as every cb arm; the partial lands at fill + 4 R, the breakeven arms at fill + 1.5 R, the trail is
    the depth exit. Built by the repo's own `stack_walk_inputs` so the stamped stack and the walked stack cannot
    differ; precedent `scripts/probes/_runner_recut_1017/recut.py` CONTROL_KW (harvest live_ladder, trail sma,
    breakeven_at_r 3.0, breakeven_at_partial, trail_prior_closes, ladder_partial False, depth_exit True)."""
    from agents.market_intelligence import live_fill_counterfactuals as lfc
    orb_low_equiv = fill - (fill - stop) / 2.0
    target, kw = lfc.stack_walk_inputs(apollo_rules(), fill, orb_low_equiv, None)
    kw["depth_adr20_pct"] = adr20          # the 20 bars ending D == the 20 pre-entry sessions live reads (a fraction)
    return target, kw


def apollo_control(*, mdicts: list, fill_pos: int, sessions: list, prior_closes: list, e_date: date, fill: float,
                   stop: float, adr20: float, horizon: int = HORIZON) -> dict:
    """CONTROL 2 - 'Apollo as it runs today': `live_fill_counterfactuals.walk_arm` configured by `apollo_walk_inputs`
    on the CB fill and stop. Day 0 = the stored minutes from the fill bar on; `sessions` = the next `horizon` calendar
    sessions (a missing bar is None and blocks the walk); `prior_closes` = the stock's own closes in the 40 calendar
    days BEFORE E (#548, as live). HORIZON is 120, not the recorder's 40: it is a data window, not a rule, and 120 is
    what the other arms use. The fill bar's low is neutralised (see below). R = pnl / (fill - stop), the cb unit. settled / horizon (the cap reached, marked) are
    mature; pending (a hole or the data ended) and abstain (an unorderable day-0 bar) are open marks with no R."""
    from agents.market_intelligence import live_fill_counterfactuals as lfc
    target, kw = apollo_walk_inputs(fill, stop, adr20)
    risk, width = fill - stop, (fill - stop) / fill
    # The fill bar's LOW is neutralised. The CB stop is the low of the day INCLUDING the fill bar's own low, so on a
    # breakout bar that is also the low of the day `walk_arm`'s fill-bar test (low <= stop) would abstain ("straddles
    # the stop") on a stop the fill bar cannot be held to: the module's own day-0 walk looks only at minutes AFTER the
    # fill minute, and the low may well have printed before the fill. The bar's HIGH and CLOSE are kept: a buy that
    # triggered at the level cannot have a higher high before it, so they post-date the fill, and walk_arm's own
    # fill-bar target / breakeven tests (which its docstring argues are orderable) stay live. Presented bar:
    # open = low = the fill, high = max(bar high, fill), close = the bar's close (always >= the stop).
    fb = mdicts[fill_pos]
    day0 = [{"m": fb["m"], "o": fill, "h": max(fb["h"], fill), "l": fill, "c": fb["c"]}] + mdicts[fill_pos + 1:]
    out = lfc.walk_arm(entry=fill, stop=stop, target=target, day0_bars=day0, fill_idx=0,
                       sessions=sessions, prior_closes=prior_closes, harvest="live_ladder", fill_day=e_date,
                       horizon=horizon, **kw)
    st = out["status"]
    if st == "settled":
        pnl, label, mature = out["pnl_per_share"], "settled", True
    elif st == "horizon":
        pnl, label, mature = out["mark_pnl_per_share"], "censored", True
    else:
        return {"status": st, "realized_r": None, "pnl_adr": None, "acct_pct": None, "sessions_held": "",
                "mature": False, "open_mark": True, "beabove": "", "note": str(out.get("reason") or "")}
    held = out["exit_session"] if out["exit_session"] is not None else out["sessions_walked"]
    return _control_result(pnl / risk, risk, fill, adr20, width, label, held, mature, str(out.get("final_reason") or ""))


def apollo_sessions(bars: "cb.DailyBars", cidx, cal: list, e_ci: int, last_ci: int, horizon: int = HORIZON) -> list:
    """[(date, bar-or-None)] for the calendar sessions after E, up to `horizon` and the end of the calendar. A
    session the ticker has no bar for is None (walk_arm: pending, never leapt)."""
    hi = min(e_ci + horizon, last_ci)
    if hi <= e_ci:
        return []
    targets = np.arange(e_ci + 1, hi + 1)
    pos = np.searchsorted(cidx, targets)
    n, out = len(cidx), []
    for ci, p in zip(targets.tolist(), pos.tolist()):
        if p < n and int(cidx[p]) == ci:
            out.append((cal[ci], {"o": float(bars.o[p]), "h": float(bars.h[p]), "l": float(bars.l[p]), "c": float(bars.c[p])}))
        else:
            out.append((cal[ci], None))
    return out


def cap_sensitivity(entry: dict, minutes: "cb.MinuteBars", *, closes_before, fwd, adr20: float,
                    horizon: int = HORIZON) -> dict:
    """CAP-NOT-SKIP: a `too_wide` abstain re-run with the stop pulled up to fill x (1 - adr20) (a one-ADR stop). The
    module's own `day0_walk` on the capped stop, then the primary arm's walk. Recorded on the abstain row; none of it
    decides."""
    fill = entry["fill"]
    stop_c = fill * (1.0 - adr20)
    capped = {"status": "filled", "reason": None, "fill": fill, "stop": stop_c, "fill_minute": entry["fill_minute"],
              "width_pct": (fill - stop_c) / fill, "level": entry["level"],
              "day0": cb.day0_walk(minutes, fill_minute=entry["fill_minute"], stop=stop_c)}
    res = walk_arms(capped, closes_before=closes_before, fwd=fwd, adr20=adr20, horizon=horizon,
                    arms={cb.PRIMARY_ARM: cb.ARMS[cb.PRIMARY_ARM]})[cb.PRIMARY_ARM]
    return {"stop": stop_c, **res}


def entry_facts(minutes: "cb.MinuteBars | None", c: dict) -> dict:
    """STEP 0: the entry-time facts of every minute variant and NOTHING else - {variant: {status, reason, width_pct,
    fill_minute}}. `cb.entry_variants` also returns a `day0` walk inside each filled entry (module-internal, line 700);
    it is dropped here unread. This function and its callers must never reach `walk_exit`,
    `day0_result_to_outcome`, `simulate` or `walk_arm` (a test makes all four raise)."""
    ev = cb.entry_variants(minutes, pivot=c["pivot"], adr20=c["adr20"], day_high=c["high_E"], day_low=c["low_E"])
    return {v: {"status": ev[v]["status"], "reason": ev[v]["reason"], "width_pct": ev[v]["width_pct"],
                "fill_minute": ev[v]["fill_minute"]} for v in MINUTE_VARIANTS}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# minute files
# ═════════════════════════════════════════════════════════════════════════════════════════════
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


def load_done_pairs(minutes_dir: Path) -> "dict | None":
    """{(date_iso, ticker): status} from `_done.psv` (`date|ticker|n_bars|status`), or None if the file is absent."""
    p = Path(minutes_dir) / "_done.psv"
    if not p.exists():
        return None
    out = {}
    for line in p.read_text().splitlines():
        f = line.split("|")
        if len(f) >= 4:
            out[(f[0], f[1])] = f[3]
    return out


def minute_date_files(minutes_dir: Path) -> dict:
    """{date_iso: path} for every `<date>.psv.gz` in the directory."""
    out = {}
    for p in sorted(Path(minutes_dir).glob("*.psv.gz")):
        try:
            out[date.fromisoformat(p.name[:-len(".psv.gz")]).isoformat()] = p
        except ValueError:
            continue
    return out


def minutes_for(blocks: dict, done: "dict | None", date_iso: str, ticker: str) -> tuple:
    """(MinuteBars or None, state). state: 'ok' | 'invalid' (block unusable) | 'no_rows' (the fetch is logged done
    - 'empty' - or the block is missing) | 'pending' (never fetched: NOT an abstain, the candidate is skipped).
    With `_done.psv` the log decides what was fetched; without one, a ticker with rows in the date file was."""
    fetched = ((date_iso, ticker) in done) if done is not None else (ticker in blocks)
    if not fetched:
        return None, "pending"
    rows = blocks.get(ticker)
    if not rows:
        return None, "no_rows"
    mb = minute_bars_from_rows(rows)
    return (mb, "ok") if mb is not None else (None, "invalid")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# candidates
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _opt_float(x):
    return None if x in ("", None) else float(x)


def read_candidates(path: Path, split: "str | None" = None, extra_floats: tuple = (), era: "str | None" = None,
                    where=None) -> list:
    """candidates.tsv as typed dicts (Python `float()`, so values equal the daily stage's exactly). `split` keeps one
    side only: the OTHER side's rows are never even typed. THE LABEL IS NOT TRUSTED: every row's `split` must equal
    `split_label(D)` (the daily stage stamps it from D), else ValueError - so a relabelled file can neither carry
    holdout rows into `minute` (discovery outcomes) nor hide them from `holdout`. `extra_floats` (#702 his exit): more
    columns typed as optional floats (e.g. `tightening_ratio`); the default reads exactly what it always did.
    #702 pre-read (the pre-2022 Alpaca-era file, every row stamped `split = <era>` by the daily stage's `--era-label`): `era`
    replaces the `split_label(D)` rule by "every row carries exactly that label" (a file with an era label is still refused
    without `era`, and a discovery / holdout file is refused with it); `where(rec)` drops a raw row BEFORE it is typed, after
    its label has been checked (the pre-read keeps the first breaks of tl / com only)."""
    if era is not None and split is not None:
        raise ValueError("read_candidates: `era` and `split` are alternatives")
    out, label_of = [], {}
    with open(path, newline="") as fh:
        for rec in csv.DictReader(fh, delimiter="\t"):
            d = rec["D"]
            if era is not None:
                if rec["split"] != era:
                    raise ValueError(f"{path}: row {rec['ticker']} D={d} K={rec.get('K')} is labelled split={rec['split']!r}, not the "
                                     f"era label {era!r}: this is not that era's file - refusing to read it")
            else:
                if d not in label_of:
                    label_of[d] = split_label(date.fromisoformat(d))
                if rec["split"] != label_of[d]:
                    raise ValueError(f"{path}: row {rec['ticker']} D={d} K={rec.get('K')} is labelled split={rec['split']!r} but "
                                     f"D falls in the {label_of[d]!r} period (D <= {DISCOVERY_END} is discovery): the file was "
                                     f"relabelled or is stale - refusing to read it")
            if where is not None and not where(rec):
                continue
            if split is not None and rec["split"] != split:
                continue
            c = {k: rec.get(k, "") for k in ("ticker", "D", "E", "K", "split", "pole_date", "base_id", "apollo_regime")}
            for k in FLOAT_FIELDS + tuple(extra_floats):
                c[k] = _opt_float(rec.get(k))
            for k in ("retrigger", "retrigger_chain", "pole_bad_high"):
                c[k] = int(rec.get(k) or 0)
            for k in FLAG_FIELDS + tuple(CELL_COLS):
                c[k] = rec.get(k) == "1"
            for cell in CELL_NAMES:
                c["first_" + cell] = int(rec.get("first_" + cell) or 0)
                c["first_chain_" + cell] = int(rec.get("first_chain_" + cell) or 0)
            out.append(c)
    return out


def group_by_date(cands: list, available: set) -> dict:
    """{E date: [candidates sorted by (ticker, K)]} for the dates that have a minute file."""
    by = defaultdict(list)
    for c in cands:
        if c["E"] in available:
            by[c["E"]].append(c)
    for v in by.values():
        v.sort(key=lambda c: (c["ticker"], c["K"]))
    return dict(sorted(by.items()))


def load_close_variant(path: Path) -> dict:
    """close_variant_discovery.tsv.gz -> {(ticker, D, K): row dict (strings)}: the daily stage's CLOSE rows, reused."""
    out = {}
    with gzip.open(path, "rt", newline="") as fh:
        for rec in csv.DictReader(fh, delimiter="\t"):
            out[(rec["ticker"], rec["D"], rec["K"])] = rec
    return out


def close_variant_result(c: dict, cv: dict, horizon: int = HORIZON) -> dict:
    """A daily-stage CLOSE-variant row (wide: st_/r_/adr_/held_/acct_/beabove_ per arm, from a file or fresh from
    `close_variant_rows`) as one long variant result, with the maturity label the minute arms carry. Same arms,
    reused numbers - nothing is re-walked."""
    status = cv["close_status"]
    width = _opt_float(cv["close_width_pct"])
    ent = {"status": status, "reason": cv["close_reason"] or None, "fill": _opt_float(cv["close_fill"]),
           "stop": _opt_float(cv["close_stop"]), "fill_minute": None, "width_pct": width, "level": c["pivot"],
           "day0": dict(cb._NO_DAY0)}
    n_fwd, arms = int(float(cv["fwd_bars"] or 0)), {}
    if status == "filled":
        for name in cb.ARMS:
            st = cv[f"st_{name}"]
            mature = is_mature(st, n_fwd, horizon)
            arms[name] = {"status": st, "realized_r": _opt_float(cv[f"r_{name}"]), "pnl_adr": _opt_float(cv[f"adr_{name}"]),
                          "acct_pct": _opt_float(cv[f"acct_{name}"]), "sessions_held": int(float(cv[f"held_{name}"])),
                          "mature": mature, "open_mark": not mature, "beabove": int(float(cv[f"beabove_{name}"])), "note": ""}
    return {"variant": "close", "entry": ent, "arms": arms, "sens": {}, "n_fwd": n_fwd,
            "hole": int(float(cv["fwd_hole"] or 0))}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the per-candidate engine
# ═════════════════════════════════════════════════════════════════════════════════════════════
def evaluate_candidate(c: dict, bars: "cb.DailyBars", cidx: np.ndarray, e: int, minutes: "cb.MinuteBars | None", cal: list,
                       last_ci: int, horizon: int = HORIZON, apollo: bool = True) -> list:
    """One candidate -> a result per minute variant: {variant, entry (the module's dict), arms {arm: result}, sens,
    n_fwd, hole}. For every FILLED variant: all `cb.ARMS` (day-0 stop-outs booked once by the module), the two
    controls (never short-circuited by the day-0 stop), the horizon-60 re-walk of the primary arm; for a `too_wide`
    abstain: the cap-not-skip re-run. `e` = E's index in `bars`; the forward window, closes_before and the E alignment
    are wired exactly as `close_variant_rows` wires them."""
    adr20 = c["adr20"]
    assert bars.dates[e].isoformat() == c["E"], (c["ticker"], e, c["E"])
    # D was admitted on 130 consecutive bars; E follows D
    assert e >= cb.MIN_HISTORY and int(cidx[e]) - int(cidx[e - cb.MIN_HISTORY]) == cb.MIN_HISTORY, (c["ticker"], e)
    ev = cb.entry_variants(minutes, pivot=c["pivot"], adr20=adr20, day_high=float(bars.h[e]), day_low=float(bars.l[e]))
    closes_before = bars.c[:e + 1]
    fwd, cut = forward_window(bars, cidx, e, horizon)
    fwd60 = None
    cache: dict = {}
    out = []
    for name in MINUTE_VARIANTS:
        ent = ev[name]
        vr = {"variant": name, "entry": ent, "arms": {}, "sens": {}, "n_fwd": len(fwd), "hole": int(cut)}
        if ent["status"] == "filled":
            vr["arms"].update(walk_arms(ent, closes_before=closes_before, fwd=fwd, adr20=adr20, horizon=horizon))
            if fwd60 is None:
                fwd60 = forward_window(bars, cidx, e, H60)[0]
            r60 = walk_arms(ent, closes_before=closes_before, fwd=fwd60, adr20=adr20, horizon=H60,
                            arms={cb.PRIMARY_ARM: cb.ARMS[cb.PRIMARY_ARM]})[cb.PRIMARY_ARM]
            vr["sens"]["h60"] = r60
            if "md" not in cache:
                cache["md"] = minute_dicts(minutes)
                cache["prior"] = bars.c[bisect.bisect_left(bars.dates, bars.dates[e] - timedelta(days=PRIOR_CLOSE_DAYS)):e].tolist()
                cache["sessions"] = apollo_sessions(bars, cidx, cal, int(cidx[e]), last_ci, horizon)
            fp = fill_position(minutes, ent["fill_minute"])
            vr["arms"][FAMILY_A_ARM] = family_a_control(mdicts=cache["md"], fill_pos=fp, fwd=fwd, fill=ent["fill"],
                                                        stop=ent["stop"], adr20=adr20)
            if apollo:
                vr["arms"][APOLLO_ARM] = apollo_control(mdicts=cache["md"], fill_pos=fp, sessions=cache["sessions"],
                                                        prior_closes=cache["prior"], e_date=bars.dates[e], fill=ent["fill"],
                                                        stop=ent["stop"], adr20=adr20, horizon=horizon)
        elif ent["status"] == "abstain" and ent["reason"] == "too_wide":
            vr["sens"]["cap"] = cap_sensitivity(ent, minutes, closes_before=closes_before, fwd=fwd, adr20=adr20,
                                                horizon=horizon)
        out.append(vr)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# rows
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _by_cols(row: dict, cols) -> list:
    """The row's values in `cols` order, a column the row does not carry (or carries as None) as the empty cell ''.
    Values stay RAW (floats are not formatted here): `rows_to_text` / `rows_to_gz` apply `_fmt` when writing, the
    same cell rule `write_tsv` uses, so the bytes written are what the hand-padded rows gave."""
    return ["" if row.get(col) is None else row[col] for col in cols]


def cand_values(c: dict) -> dict:
    """The candidate-side trades columns (`TRADE_CAND_COLS`) of one candidate, by name."""
    row = {col: c[col] for col in TRADE_CAND_COLS if col not in ("year", "month")}
    row["year"], row["month"] = int(c["E"][:4]), c["E"][:7]
    return row


def atr_wide_flag(width, atr14):
    """Sensitivity: 1 when the stop is wider than ATR14(D) (both fractions of price); '' when either is unknown."""
    return "" if (width is None or atr14 is None) else int(width > atr14)


def floor_flags(width, adr20) -> list:
    """Sensitivity: 1 when width < f x adr20, for f in FLOORS (a report may drop those rows); '' without a width."""
    return [("" if width is None else int(width < f * adr20)) for f, _n in FLOORS]


def variant_values(c: dict, vr: dict) -> dict:
    """The variant-side trades columns (`TRADE_VAR_COLS`) of one variant of one candidate, by name."""
    ent = vr["entry"]
    width = ent["width_pct"]
    row = {"variant": vr["variant"], "fill_minute": ent["fill_minute"], "width_pct": width,
           "day0_stopped": int(ent["day0"]["stopped"]) if ent["status"] == "filled" else "",
           "abstain_reason": ent["reason"] or "", "atr14_wide": atr_wide_flag(width, c["atr14"])}
    row.update(zip((n for _f, n in FLOORS), floor_flags(width, c["adr20"])))
    return row


def trade_rows_for(c: dict, vr: dict, cand_row: dict) -> list:
    """The long trades rows of ONE variant of ONE candidate (each in `TRADE_COLS` order): one row per arm when filled;
    ONE row with no arm when it abstained or never triggered (carrying the cap-not-skip columns when it was `too_wide`).
    `cand_row` = `cand_values(c)`. A column a row does not carry stays empty."""
    ent = vr["entry"]
    base = {**cand_row, **variant_values(c, vr), "fwd_bars": vr["n_fwd"], "fwd_hole": vr["hole"]}
    if ent["status"] == "filled":
        h60 = vr["sens"].get("h60")
        rows = []
        for name, a in vr["arms"].items():
            row = {**base, "arm": name, "status": a["status"], "realized_r": a["realized_r"], "pnl_adr": a["pnl_adr"],
                   "acct_pct": a["acct_pct"], "sessions_held": a["sessions_held"], "mature": int(a["mature"]),
                   "open_mark": int(a["open_mark"]), "beabove": a["beabove"], "arm_note": a["note"]}
            if name == cb.PRIMARY_ARM and h60:
                row.update(r_h60=h60["realized_r"], st_h60=h60["status"], mature_h60=int(h60["mature"]))
            rows.append(_by_cols(row, TRADE_COLS))
        return rows
    row = {**base, "status": ent["status"]}
    cap = vr["sens"].get("cap")
    if cap:
        row.update(cap_stop=cap["stop"], cap_status=cap["status"], cap_realized_r=cap["realized_r"],
                   cap_pnl_adr=cap["pnl_adr"], cap_acct_pct=cap["acct_pct"], cap_mature=int(cap["mature"]),
                   cap_sessions_held=cap["sessions_held"])
    return [_by_cols(row, TRADE_COLS)]


def entry_row_for(c: dict, vr: dict, minutes_state: str) -> list:
    """One entries row (`ENTRY_COLS` order): the candidate's own columns plus the variant's entry and day-0 facts."""
    ent = vr["entry"]
    d0 = ent["day0"]
    filled = ent["status"] == "filled"
    row = {**c, "variant": vr["variant"], "status": ent["status"], "reason": ent["reason"] or "",
           "minutes_state": minutes_state, "level": ent["level"], "fill": ent["fill"], "stop": ent["stop"],
           "width_pct": ent["width_pct"], "fill_minute": ent["fill_minute"],
           "day0_stopped": int(d0["stopped"]) if filled else "", "day0_exit_price": d0["exit_price"] if filled else "",
           "day0_exit_minute": d0["exit_minute"] if filled else "",
           "atr14_wide": atr_wide_flag(ent["width_pct"], c["atr14"])}
    return _by_cols(row, ENTRY_COLS)


def composition_row_for(c: dict, variant: str, f: dict, minutes_state: str) -> list:
    """One STEP 0 composition row (`COMPOSITION_COLS` order): entry-time facts only."""
    row = {**c, "variant": variant, "status": f["status"], "reason": f["reason"] or "", "minutes_state": minutes_state,
           "width_pct": f["width_pct"], "fill_minute": f["fill_minute"]}
    return _by_cols(row, COMPOSITION_COLS)


def rows_to_text(rows: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", lineterminator="\n")
    for r in rows:
        w.writerow([_fmt(x) for x in r])
    return buf.getvalue()


def rows_to_gz(rows: list) -> bytes:
    """Rows -> ONE gzip member (mtime 0, so a re-run is byte-identical). Members concatenate into a valid gzip."""
    return gzip.compress(rows_to_text(rows).encode(), compresslevel=3, mtime=0)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# workers + stage runners
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _ticker_bars(ticker: str) -> tuple:
    cache = _G.setdefault("bars_cache", {})
    hit = cache.get(ticker)
    if hit is None:
        D: Daily = _G["D"]
        hit = cache[ticker] = bars_for(D, D.tid[ticker])
    return hit


def locate_breakout_index(cal: list, cidx, e_iso: str) -> int:
    """E's index inside one ticker's bars, found by its SPY-calendar index (asserted to be there)."""
    ci = bisect.bisect_left(cal, date.fromisoformat(e_iso))
    p = int(np.searchsorted(cidx, ci))
    assert p < len(cidx) and int(cidx[p]) == ci, (e_iso, "not a bar of this ticker")
    return p


def _minute_job(date_iso: str) -> tuple:
    """One E date: read its minute file ONCE, then every candidate of that date through `evaluate_candidate`. Returns
    (trades gzip member, entries gzip member, tally, n trade rows, n entry rows)."""
    D: Daily = _G["D"]
    cands = _G["by_date"][date_iso]
    blocks, info = read_minute_file(_G["files"][date_iso], {c["ticker"] for c in cands})
    done, close_map, cal = _G["done"], _G["close_map"], D.cal
    last_ci = len(cal) - 1
    tally: Counter = Counter()
    tally[("file", "refetched_tickers")] += info["refetched"]
    tally[("file", "bad_lines")] += info["bad_lines"]
    tally[("file", "truncated")] += int(info["truncated"])
    trades, entries = [], []
    for c in cands:
        mb, state = minutes_for(blocks, done, date_iso, c["ticker"])
        tally[("minutes_state", state)] += 1
        if state == "pending":
            continue
        bars, cidx = _ticker_bars(c["ticker"])
        e = locate_breakout_index(cal, cidx, c["E"])
        results = evaluate_candidate(c, bars, cidx, e, mb, cal, last_ci, apollo=_G["apollo"])
        r0 = results[0]["entry"]["reason"]
        tally[("data_abstain", r0 if r0 in DATA_ABSTAINS else "none")] += 1
        prefix = cand_values(c)
        for vr in results:
            ent = vr["entry"]
            tally[("entry", vr["variant"], ent["status"], ent["reason"] or "")] += 1
            for a, res in vr["arms"].items():
                tally[("arm_mature", a, int(res["mature"]))] += 1
            entries.append(entry_row_for(c, vr, state))
            trades.extend(trade_rows_for(c, vr, prefix))
        cv = close_map.get((c["ticker"], c["D"], c["K"])) if close_map is not None else None
        if _G["compute_close"]:
            cv = close_variant_rows(c["ticker"], bars, [dict(c, E_i=e)], cidx)[0]
        if cv is None:
            tally[("close_missing",)] += 1
            continue
        vr = close_variant_result(c, cv)
        tally[("entry", "close", vr["entry"]["status"], vr["entry"]["reason"] or "")] += 1
        entries.append(entry_row_for(c, vr, ""))
        trades.extend(trade_rows_for(c, vr, prefix))
    return rows_to_gz(trades), rows_to_gz(entries), tally, len(trades), len(entries)


def _entry_category(f: dict) -> str:
    if f["status"] == "filled":
        return "filled"
    if f["status"] == "no_trigger":
        return "no_trigger"
    return "too_wide" if f["reason"] == "too_wide" else "other_abstain"


def _step0_job(date_iso: str) -> tuple:
    """STEP 0 for one E date: ENTRY-TIME FACTS only. No daily bars are opened, and nothing here reaches an exit walker."""
    cands = _G["by_date"][date_iso]
    blocks, _info = read_minute_file(_G["files"][date_iso], {c["ticker"] for c in cands})
    done = _G["done"]
    tally: Counter = Counter()
    comp = []
    for c in cands:
        mb, state = minutes_for(blocks, done, date_iso, c["ticker"])
        tally[("minutes_state", state)] += 1
        if state == "pending":
            continue
        facts = entry_facts(mb, c)
        r0 = facts[MINUTE_VARIANTS[0]]["reason"]
        tally[("data_abstain", r0 if r0 in DATA_ABSTAINS else "none")] += 1
        for v in MINUTE_VARIANTS:
            comp.append(composition_row_for(c, v, facts[v], state))
            cat = _entry_category(facts[v])
            for key_name, rt in (("spec", c["retrigger"]), ("chain", c["retrigger_chain"])):
                if rt:
                    continue
                for cell in CELL_NAMES:
                    if c[cell]:
                        tally[(cell, c["K"], v, key_name, "candidates")] += 1
                        tally[(cell, c["K"], v, key_name, cat)] += 1
    return rows_to_text(comp), tally


def _pool_map(fn, items: list, workers: int):
    """Ordered results (so the outputs are deterministic) from `fn` over `items`, in a fork pool when workers > 1."""
    if workers > 1 and len(items) > 1:
        with _pool(workers) as p:
            yield from p.imap(fn, items, chunksize=1)
    else:
        for it in items:
            yield fn(it)


def partial_path(p: Path) -> Path:
    """`<name>.tsv.gz` -> `<name>.tsv.gz.partial` (appended: `with_suffix` would replace `.gz`)."""
    return Path(str(p) + ".partial")


def _setup_minute_inputs(args, split: str) -> dict:
    data = Path(args.data)
    out = Path(args.out) if args.out else data / "out"
    minutes_dir = Path(args.minutes) if args.minutes else data / "minutes"
    cands = read_candidates(out / f"candidates{run_keys(args)[1]}.tsv", split)
    files = minute_date_files(minutes_dir) if minutes_dir.is_dir() else {}
    if args.limit_dates:
        files = dict(list(files.items())[:args.limit_dates])
    by_date = group_by_date(cands, set(files))
    return {"data": data, "out": out, "minutes_dir": minutes_dir, "cands": cands, "files": files, "by_date": by_date,
            "done": load_done_pairs(minutes_dir) if minutes_dir.is_dir() else None}


def _fmt_tally_entries(tally: Counter) -> str:
    rows = []
    for v in ALL_VARIANTS:
        c = {(k[2], k[3]): n for k, n in tally.items() if k[0] == "entry" and k[1] == v}
        tot = sum(c.values())
        if not tot:
            continue
        filled = sum(n for (st, _r), n in c.items() if st == "filled")
        tw = sum(n for (_st, r), n in c.items() if r == "too_wide")
        nt = sum(n for (st, _r), n in c.items() if st == "no_trigger")
        rows.append([v, f"{tot:,}", f"{filled:,}", f"{tw:,}", f"{nt:,}",
                     f"{tot - filled - tw - nt:,}"])
    return table(rows, ["variant", "rows", "filled", "too_wide", "no_trigger", "other abstain"])


def minute_data_gate(tally: Counter) -> tuple:
    """(share, text): the share of fetched candidates whose entry abstained because the DATA disagrees (no minute
    bars, minute vs daily high/low off by > 1%, the minute high never reaching a pivot the daily high cleared).
    More than 5% BLOCKS the read (plan Verification)."""
    tot = sum(n for k, n in tally.items() if k[0] == "data_abstain")
    if not tot:
        return 0.0, "DATA GATE: no fetched candidate yet"
    by = {k[1]: n for k, n in tally.items() if k[0] == "data_abstain" and k[1] != "none"}
    bad = sum(by.values())
    share = bad / tot
    match = 1.0 - by.get("minute_daily_mismatch", 0) / tot
    verdict = "BLOCKS THE READ" if share > DATA_ABSTAIN_MAX else "ok"
    return share, (f"DATA GATE: {bad:,} of {tot:,} fetched candidates abstain on the data ({share:.2%}; "
                   f"{dict(sorted(by.items()))}) - limit {DATA_ABSTAIN_MAX:.0%}: {verdict}; "
                   f"minute-vs-daily high/low match rate {match:.2%}")


def run_minute_stage(args, split: str, inp: "dict | None" = None) -> None:
    """`minute` (split='discovery') and `holdout` (split='holdout', behind freeze_check): every candidate of the split
    whose minutes are on disk -> entries, day-0, every exit arm, the controls, the sensitivities.
    #702 pre-read: `inp` (the shape `_setup_minute_inputs` returns) is the pre-era population the caller already read and
    checked for completeness (split='pre'); None = the registered inputs, read here as always."""
    T0 = time.time()
    inp = _setup_minute_inputs(args, split) if inp is None else inp
    out, small = inp["out"], (Path(args.small_out) if args.small_out else HERE / "out")
    sfx = run_keys(args)[1]
    log: list = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        log.append(msg)

    n_c, by_date = len(inp["cands"]), inp["by_date"]
    n_with_file = sum(len(v) for v in by_date.values())
    say(f"{split.upper()} MINUTE STAGE: {n_c:,} {split} candidate rows; minute files on disk: {len(inp['files'])} dates "
        f"({inp['minutes_dir']}); candidates on those dates: {n_with_file:,}; "
        f"_done.psv: {'present (' + format(len(inp['done']), ',') + ' pairs)' if inp['done'] is not None else 'absent - a ticker with rows in the date file counts as fetched'}")
    if not by_date:
        say("nothing to do: no candidate falls on a date with a minute file (nothing written)")
        return
    out.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    t = time.time()
    D = load_daily(inp["data"] / "daily_closes_all.csv.gz")
    close_map, compute_close = None, False
    if not args.no_close:
        if split == "discovery":
            cvp = inp["out"] / f"close_variant_discovery{sfx}.tsv.gz"
            close_map = load_close_variant(cvp) if cvp.exists() else None
            if close_map is None:
                say(f"  ! {cvp} not found: the CLOSE variant is skipped")
        else:
            compute_close = True            # the daily stage never walks the holdout; this run does, once, after the freeze
    _G.update(D=D, by_date=by_date, files=inp["files"], done=inp["done"], close_map=close_map,
              compute_close=compute_close, bars_cache={}, apollo=not args.no_apollo)
    say(f"[load: {time.time() - t:.0f}s]")
    t = time.time()
    tp, ep = out / f"trades_{split}{sfx}.tsv.gz", out / f"entries_{split}{sfx}.tsv.gz"
    tpp, epp = partial_path(tp), partial_path(ep)
    tally: Counter = Counter()
    n_t = n_e = 0
    dates = list(by_date)
    # The tables are written to `<name>.partial` and renamed to the final name only after EVERY date has been walked: a
    # crash leaves no file under the final name (so none can be mistaken for a finished run, and the holdout's
    # "joined ONCE" guard keys on the final name) - only a visible `.partial`, which `run_holdout` refuses to ignore.
    with open(tpp, "wb") as tf, open(epp, "wb") as ef:
        tf.write(rows_to_gz([TRADE_COLS]))
        ef.write(rows_to_gz([ENTRY_COLS]))
        for k, (tg, eg, ty, nt, ne) in enumerate(_pool_map(_minute_job, dates, args.workers), 1):
            tf.write(tg)
            ef.write(eg)
            tally.update(ty)
            n_t, n_e = n_t + nt, n_e + ne
            if k % 50 == 0 or k == len(dates):
                print(f"  {k}/{len(dates)} dates, {n_t:,} trade rows", flush=True)
    os.replace(tpp, tp)
    os.replace(epp, ep)
    wall = time.time() - t
    states = {k[1]: n for k, n in tally.items() if k[0] == "minutes_state"}
    say(f"[entries + exits + controls: {wall:.0f}s]")
    say("")
    say(f"COVERAGE: candidates with minutes fetched {sum(n for s, n in states.items() if s != 'pending'):,} "
        f"(by state {dict(sorted(states.items()))}); PENDING fetch (skipped, NOT an abstain) {states.get('pending', 0):,}; "
        f"files: refetched tickers {tally[('file', 'refetched_tickers')]}, bad lines {tally[('file', 'bad_lines')]}, "
        f"truncated {tally[('file', 'truncated')]}")
    say(minute_data_gate(tally)[1])
    say("ENTRIES (candidate rows x variant; close = the daily stage's rows, joined):")
    say(_fmt_tally_entries(tally))
    mat = defaultdict(lambda: [0, 0])
    for k, n in tally.items():
        if k[0] == "arm_mature":
            mat[k[1]][k[2]] += n
    say("ARM MATURITY (minute variants; filled walks): " + "; ".join(
        f"{a} mature {m[1]:,} / open mark {m[0]:,}" for a, m in mat.items() if a in (cb.PRIMARY_ARM, FAMILY_A_ARM, APOLLO_ARM)))
    say(f"WROTE {tp} ({n_t:,} rows), {ep} ({n_e:,} rows)")
    say(f"WALL TIME: {time.time() - T0:.0f}s total")
    (small / f"minute_summary_{split}{sfx}.txt").write_text("\n".join(log) + "\n")
    if split == "holdout":                        # #702 P4b step 6b: the per-regime table of the ONE holdout run, beside the tables
        rname = f"regime_report_holdout{sfx}"
        df, _cuts, _counts = load_report_frame(tp, regime_of={c["D"]: regime_label(c["apollo_regime"]) for c in inp["cands"]})
        n_reg, reg_text = write_regime_report(df, out / f"{rname}.tsv", small / f"{rname}.txt",
                                              title="#702 HOLDOUT by regime", src=tp.name)
        print(reg_text)
        print(f"WROTE {out / (rname + '.tsv')} ({n_reg:,} rows), {small / (rname + '.txt')}")


def step0_text_entries(tally: Counter, keys=KS) -> str:
    """The go/no-go input: per cell x K x variant - candidates, filled, too_wide, other abstains, no_trigger - under
    BOTH base keys (non-retrigger rows only). Entry-time facts; no outcome exists anywhere in it."""
    lines = ["STEP 0 (entries) - HOLDOUT composition from ENTRY-TIME facts only; no day-0 walk, no exit, no outcome"]
    for key_name, label in (("spec", "SPEC key (ticker, pole_date, K)"), ("chain", "CHAIN key (poles <= 3 sessions apart = one base)")):
        body = []
        for cell in CELL_NAMES:
            for k in keys:
                for v in MINUTE_VARIANTS:
                    g = lambda cat: tally.get((cell, k, v, key_name, cat), 0)
                    body.append([cell, k, v, g("candidates"), g("filled"), g("too_wide"), g("other_abstain"), g("no_trigger")])
        lines.append(f"  -- {label} --")
        lines.append(table(body, ["cell", "K", "variant", "candidates", "filled", "too_wide", "other_abstain", "no_trigger"]))
    for key_name, label in (("spec", "SPEC key"), ("chain", "CHAIN key")):
        parts = []
        for v in MINUTE_VARIANTS:
            parts.append(f"{v}: " + ", ".join(f"{k}={tally.get(('C1', k, v, key_name, 'filled'), 0)}" for k in keys))
        lines.append(f"  GO/NO-GO input, {label} (plan: C1 primary entry needs >= 30 FILLED holdout trades): " + "; ".join(parts))
    return "\n".join(lines)


def run_step0_entries(args) -> None:
    """`step0-entries`: the HOLDOUT composition with no outcome. Reads candidates.tsv (holdout rows) and the minute
    files; never opens the daily export, so no daily bar after E - nor any exit - can reach it."""
    T0 = time.time()
    inp = _setup_minute_inputs(args, "holdout")
    out, small = inp["out"], (Path(args.small_out) if args.small_out else HERE / "out")
    keys, sfx = run_keys(args)
    by_date = inp["by_date"]
    n_c = len(inp["cands"])
    print(f"STEP 0 ENTRIES: {n_c:,} holdout candidate rows; minute files on disk: {len(inp['files'])} dates; "
          f"candidates on those dates: {sum(len(v) for v in by_date.values()):,}", flush=True)
    if not by_date:
        print("nothing to do: no holdout candidate falls on a date with a minute file (nothing written)")
        return
    out.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    _G.update(by_date=by_date, files=inp["files"], done=inp["done"])
    tally: Counter = Counter()
    cp = out / f"entries_holdout_composition{sfx}.tsv"
    n_rows = 0
    with open(cp, "w", newline="") as fh:
        fh.write("\t".join(COMPOSITION_COLS) + "\n")
        for text, ty in _pool_map(_step0_job, list(by_date), args.workers):
            fh.write(text)
            tally.update(ty)
            n_rows += text.count("\n")
    states = {k[1]: n for k, n in tally.items() if k[0] == "minutes_state"}
    txt = [f"COVERAGE: holdout candidates with minutes fetched {sum(n for s, n in states.items() if s != 'pending'):,} "
           f"(by state {dict(sorted(states.items()))}); PENDING fetch (skipped, NOT an abstain) {states.get('pending', 0):,}",
           minute_data_gate(tally)[1], step0_text_entries(tally, keys)]
    text = "\n".join(txt)
    print(text)
    (small / f"step0_entries{sfx}.txt").write_text(text + "\n")
    print(f"WROTE {cp} ({n_rows:,} rows, entry-time columns only); WALL TIME {time.time() - T0:.0f}s")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# #702 "his exit" (operator 2026-10-18): the `exits` and `exits-report` stages. DISCOVERY ONLY (the split is hard-coded;
# `holdout` refuses `--levels`), the headline entry only, the spec key's first breaks only, NEW files beside the pinned
# ones (`trades_discovery_exits<tag>.tsv.gz`, `exits_report<tag>.{tsv,txt}`; tag = "_" + the levels walked).
# ═════════════════════════════════════════════════════════════════════════════════════════════
EXITS_CELLS = ("C0", "C1", "C3", "C5")                                        # the cells the his-exit read reports (the brief)
EXITS_ARMS = {cb.PRIMARY_ARM: cb.ARMS[cb.PRIMARY_ARM], **cb.HIS_EXIT_ARMS}    # the registered primary BESIDE the 25 new arms
EXITS_RANK = "mean_pnl_adr"            # the statistic that orders arm x stop combos: R's unit differs by stop variant (R = fill - stop),
#                                      # P&L in ADR units does not - the #327 tight-stop lesson. Mean R and the tail are shown beside.
EXITS_PRIMARY = ("lod", cb.PRIMARY_ARM)                                       # the registered row: the lod stop, p33_s3_t10
EXITS_FULL_POP_MIN = 0.95              # a combo is ranked only when it kept >= 95% of the registered row's filled entries: a stop
#                                      # that abstains (too_wide) on most trades reads a DIFFERENT population (the tight bases), and
#                                      # a better number on it is the population, not the stop - such stops are compared on their
#                                      # own trades against the registered arm (the `matched` rows), never ranked
FIFTH_MEASURES = (("range5_adr", "fifth_range5_adr"), ("tightening_ratio", "fifth_tightening"))   # the tightness slice
EXITS_COLS = (["ticker", "D", "E", "K", "year", "month", "retrigger_chain"] + CELL_COLS
              + ["adr20", "atr14", "median_dollar_vol20", "phase_qqq_10_20", "gap_over_1adr", "tightening_ratio",
                 "range_recent5", "range5_adr", "fill", "fill_minute", "stop_variant", "stop", "width_pct", "abstain_reason",
                 "target", "arm", "status", "realized_r", "pnl_adr", "acct_pct", "sessions_held", "mature", "open_mark",
                 "partial_kind", "partial_session", "trail_n", "beabove", "fwd_bars", "fwd_hole"])


def exits_stat_cols() -> list:
    """The exits report's TSV layout (`STAT_COLS` is defined with the report section below; read at call time)."""
    return ["key", "cell", "K", "stop_variant", "arm", "slice", "value"] + STAT_COLS + ["too_wide"]


def parse_levels(spec, keys) -> tuple:
    """`--levels` -> the levels of the run's candidates file the exits stage walks: a comma list drawn from the run's `keys`
    (default: every one of them). The default-key run names `tl` to read the registered `candidates.tsv` and walk the
    trendline alone; `--keys com,comb` walks both from `candidates_com_comb.tsv`."""
    if spec in (None, ""):
        return tuple(keys)
    lv = tuple(k.strip() for k in str(spec).split(",") if k.strip())
    bad = [k for k in lv if k not in keys]
    if bad or not lv or len(set(lv)) != len(lv):
        raise ValueError(f"--levels: expected distinct names from the run's keys {tuple(keys)}, got {spec!r}")
    return lv


def exits_tag(levels) -> str:
    return "_" + "_".join(levels)


def base_low_at(bars: "cb.DailyBars", P: int, i: int) -> float:
    """`explain_watch`'s `base_low`: the lowest low of the base sessions (P, i]."""
    return float(bars.l[P + 1:i + 1].min())


def range_recent5_at(bars: "cb.DailyBars", i: int) -> float:
    """`explain_watch`'s `range_recent5`: the mean of (high - low) / close over the RECENT_WINDOW sessions ending at i."""
    w = cb.RECENT_WINDOW
    rng = (bars.h[i - w + 1:i + 1] - bars.l[i - w + 1:i + 1]) / bars.c[i - w + 1:i + 1]
    return float(rng.mean())


def partial_facts(events: list, arm: "cb.Arm") -> tuple:
    """(partial_kind, partial_session, trail_n) read off a walk's events: the kind of the FIRST partial ("day0_r" = the +R
    touch on the breakout day, "r" = the +R touch on a later session, "session" = the close of the arm's session, "" = none),
    its session, and the trail SMA the walk used (the `trail_n` event of the speed / distance arms, else the arm's own)."""
    kind, sess, tn = "", "", (arm.trail_sma if arm.trail_sma else "")
    for j, k, px, _f in events:
        if k in ("partial", "partial_r") and kind == "":
            kind = "session" if k == "partial" else ("day0_r" if j == 0 else "r")
            sess = j
        elif k == "trail_n":
            tn = int(px)
    return kind, sess, tn


def evaluate_exits(c: dict, bars: "cb.DailyBars", cidx: np.ndarray, e: int, minutes: "cb.MinuteBars | None",
                   horizon: int = HORIZON, *, stops: tuple = cb.STOP_VARIANTS, arms: "dict | None" = None) -> tuple:
    """One candidate -> (rows in EXITS_COLS order, tally). The headline entry (`cb.entry_variants` exactly as the minute
    stage calls it); a non-fill writes nothing (tallied). A fill is walked under every `cb.stop_variants` reading: an
    unusable stop is ONE row with no arm (`abstain_reason`); a usable one re-runs the module's `day0_walk` on it and walks
    `EXITS_ARMS` through `cb.walk_his_arms`. `base_low` and `range_recent5` are recomputed from the bars with
    `explain_watch`'s own formulas (they are not candidates.tsv columns); `base_low` is cross-checked against the row's
    `base_depth`.
    #702 P5: `stops` / `arms` narrow the walk (the P5 stage walks the `lod` stop and `P5_ARMS` only, on discovery and on the
    holdout alike - ONE function, so the discovery numbers the registration quotes come from the code the holdout will run);
    the defaults are the `exits` stage's, unchanged."""
    arms = EXITS_ARMS if arms is None else arms
    tally: Counter = Counter()
    adr20 = c["adr20"]
    assert bars.dates[e].isoformat() == c["E"], (c["ticker"], e, c["E"])
    assert e >= cb.MIN_HISTORY and int(cidx[e]) - int(cidx[e - cb.MIN_HISTORY]) == cb.MIN_HISTORY, (c["ticker"], e)
    ev = cb.entry_variants(minutes, pivot=c["pivot"], adr20=adr20, day_high=float(bars.h[e]), day_low=float(bars.l[e]))
    ent = ev[HEADLINE_VARIANT]
    tally[("entry", ent["status"], ent["reason"] or "")] += 1
    if ent["status"] != "filled":
        return [], tally
    i = e - 1                                                          # the watch night D
    P = bisect.bisect_left(bars.dates, date.fromisoformat(c["pole_date"]))
    assert P < i and bars.dates[P].isoformat() == c["pole_date"], (c["ticker"], c["pole_date"])
    base_low = base_low_at(bars, P, i)
    if c.get("base_depth") is not None:                                # the row's own number, as a cross-check of P
        implied = float(bars.h[P]) * (1.0 - float(c["base_depth"]))
        assert abs(implied - base_low) <= 1e-6 * max(1.0, base_low), (c["ticker"], c["D"], implied, base_low)
    rr5 = range_recent5_at(bars, i)
    closes_before = bars.c[:e + 1]
    fwd, cut = forward_window(bars, cidx, e, horizon)
    base = {col: c[col] for col in ("ticker", "D", "E", "K", "retrigger_chain", "adr20", "atr14", "median_dollar_vol20",
                                    "phase_qqq_10_20", "gap_over_1adr", "tightening_ratio") if col in c}
    base.update(year=int(c["E"][:4]), month=c["E"][:7], range_recent5=rr5, range5_adr=rr5 / adr20, fill=ent["fill"],
                fill_minute=ent["fill_minute"], fwd_bars=len(fwd), fwd_hole=int(cut))
    for cell in CELL_COLS:
        base[cell] = int(bool(c[cell]))
    rows = []
    for sv, s in cb.stop_variants(fill=ent["fill"], lod_stop=ent["stop"], pivot=c["pivot"], base_low=base_low,
                                  adr20=adr20).items():
        if sv not in stops:
            continue
        tally[("stop", sv, s["reason"] or "ok")] += 1
        if s["reason"]:
            rows.append(_by_cols({**base, "stop_variant": sv, "stop": s["stop"], "width_pct": s["width_pct"],
                                  "abstain_reason": s["reason"], "status": "abstain"}, EXITS_COLS))
            continue
        entry2 = {**ent, "stop": s["stop"], "width_pct": s["width_pct"],
                  "day0": cb.day0_walk(minutes, fill_minute=ent["fill_minute"], stop=s["stop"])}
        if sv == "lod":
            assert entry2["day0"] == ent["day0"] and entry2["stop"] == ent["stop"]     # the registered entry, untouched
        target = ent["fill"] + cb.PARTIAL_TARGET_R * (ent["fill"] - s["stop"])
        res = cb.walk_his_arms(entry2, closes_before=closes_before, fwd=fwd, adr20=adr20, minutes=minutes,
                               horizon=horizon, arms=arms)
        for name, raw in res.items():
            a = arm_result(raw, width=s["width_pct"], n_fwd=len(fwd), horizon=horizon)
            kind, sess, tn = partial_facts(raw["events"], arms[name])
            tally[("arm_mature", sv, name, int(a["mature"]))] += 1
            rows.append(_by_cols({**base, "stop_variant": sv, "stop": s["stop"], "width_pct": s["width_pct"],
                                  "abstain_reason": "", "target": target, "arm": name, "status": a["status"],
                                  "realized_r": a["realized_r"], "pnl_adr": a["pnl_adr"], "acct_pct": a["acct_pct"],
                                  "sessions_held": a["sessions_held"], "mature": int(a["mature"]),
                                  "open_mark": int(a["open_mark"]), "partial_kind": kind, "partial_session": sess,
                                  "trail_n": tn, "beabove": a["beabove"]}, EXITS_COLS))
    return rows, tally


def _exits_job(date_iso: str) -> tuple:
    """One E date of the exits stage: the minute file once, then every candidate of the date through `evaluate_exits`."""
    D: Daily = _G["D"]
    cands = _G["by_date"][date_iso]
    blocks, _info = read_minute_file(_G["files"][date_iso], {c["ticker"] for c in cands})
    done, cal = _G["done"], D.cal
    tally: Counter = Counter()
    rows = []
    for c in cands:
        mb, state = minutes_for(blocks, done, date_iso, c["ticker"])
        tally[("minutes_state", state)] += 1
        if state == "pending":
            continue
        bars, cidx = _ticker_bars(c["ticker"])
        e = locate_breakout_index(cal, cidx, c["E"])
        r, t = evaluate_exits(c, bars, cidx, e, mb, _G["horizon"], **_G.get("exits_kw", {}))
        rows.extend(r)
        tally.update(t)
    return rows_to_gz(rows), tally, len(rows)


def exits_population(cands: list, levels) -> list:
    """The exits stage's population: the spec key's FIRST breaks (`retrigger == 0`; the report drops retriggers anyway and the
    chain-key population is a subset) on the requested levels."""
    return [c for c in cands if c["retrigger"] == 0 and c["K"] in levels]


def run_exits(args) -> None:
    """`exits`: his exit (the +2R / day / combo partial, the trail switches) x the stop variants on the DISCOVERY first breaks at
    the headline entry -> `trades_discovery_exits<tag>.tsv.gz` (NEW; nothing pinned is written)."""
    T0 = time.time()
    data = Path(args.data)
    out = Path(args.out) if args.out else data / "out"
    small = Path(args.small_out) if args.small_out else HERE / "out"
    minutes_dir = Path(args.minutes) if args.minutes else data / "minutes"
    keys, sfx = run_keys(args)
    levels = parse_levels(getattr(args, "levels", None), keys)
    tag = exits_tag(levels)
    log: list = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        log.append(msg)

    cands = exits_population(read_candidates(out / f"candidates{sfx}.tsv", "discovery",
                                             extra_floats=("tightening_ratio", "base_depth")), levels)
    files = minute_date_files(minutes_dir) if minutes_dir.is_dir() else {}
    if args.limit_dates:
        files = dict(list(files.items())[:args.limit_dates])
    by_date = group_by_date(cands, set(files))
    say(f"DISCOVERY EXITS STAGE (#702 his exit): levels {'/'.join(levels)} from candidates{sfx}.tsv; {len(cands):,} first-break "
        f"candidate rows (spec key); minute files on disk: {len(files)} dates ({minutes_dir}); candidates on those dates: "
        f"{sum(len(v) for v in by_date.values()):,}; entry {HEADLINE_VARIANT}; arms {len(EXITS_ARMS)} ({cb.PRIMARY_ARM} + "
        f"{len(cb.HIS_EXIT_ARMS)} his-exit arms) x stops {'/'.join(cb.STOP_VARIANTS)}")
    if not by_date:
        say("nothing to do: no candidate falls on a date with a minute file (nothing written)")
        return
    out.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    t = time.time()
    D = load_daily(data / "daily_closes_all.csv.gz")
    _G.update(D=D, by_date=by_date, files=files, done=(load_done_pairs(minutes_dir) if minutes_dir.is_dir() else None),
              bars_cache={}, horizon=HORIZON, exits_kw={})
    say(f"[load: {time.time() - t:.0f}s]")
    t = time.time()
    tp = out / f"trades_discovery_exits{tag}.tsv.gz"
    tpp = partial_path(tp)
    tally: Counter = Counter()
    n_rows = 0
    dates = list(by_date)
    with open(tpp, "wb") as tf:
        tf.write(rows_to_gz([EXITS_COLS]))
        for k, (tg, ty, nr) in enumerate(_pool_map(_exits_job, dates, args.workers), 1):
            tf.write(tg)
            tally.update(ty)
            n_rows += nr
            if k % 100 == 0 or k == len(dates):
                print(f"  {k}/{len(dates)} dates, {n_rows:,} rows", flush=True)
    os.replace(tpp, tp)
    say(f"[entries + his-exit walks: {time.time() - t:.0f}s]")
    states = {k[1]: n for k, n in tally.items() if k[0] == "minutes_state"}
    say(f"COVERAGE: candidates with minutes fetched {sum(n for s, n in states.items() if s != 'pending'):,} "
        f"(by state {dict(sorted(states.items()))}); PENDING fetch (skipped) {states.get('pending', 0):,}")
    ent = {(k[1], k[2]): n for k, n in tally.items() if k[0] == "entry"}
    say(f"ENTRY ({HEADLINE_VARIANT}): " + "; ".join(f"{st}{(' ' + r) if r else ''} {n:,}" for (st, r), n in sorted(ent.items())))
    body = []
    for sv in cb.STOP_VARIANTS:
        ok = tally[("stop", sv, "ok")]
        tw = tally[("stop", sv, "too_wide")]
        ab = tally[("stop", sv, "stop_at_or_above_fill")]
        mat = sum(n for k, n in tally.items() if k[0] == "arm_mature" and k[1] == sv and k[2] == cb.PRIMARY_ARM and k[3] == 1)
        body.append([sv, f"{ok:,}", f"{tw:,}", f"{ab:,}", f"{mat:,}"])
    say("STOP VARIANTS (filled entries): usable / too_wide / stop_at_or_above_fill / mature primary-arm walks")
    say(table(body, ["stop", "usable", "too_wide", "at_or_above_fill", f"mature {cb.PRIMARY_ARM}"]))
    say(f"WROTE {tp} ({n_rows:,} rows)")
    say(f"WALL TIME: {time.time() - T0:.0f}s total")
    (small / f"exits_summary{tag}.txt").write_text("\n".join(log) + "\n")


# ── the exits report ─────────────────────────────────────────────────────────────────────────
EXITS_USECOLS = (["K", "retrigger_chain", "year", "month", "adr20", "range5_adr", "tightening_ratio", "stop_variant",
                  "abstain_reason", "arm", "status", "realized_r", "pnl_adr", "acct_pct", "mature", "fill", "D", "ticker"]
                 + list(EXITS_CELLS))


def load_exits_frame(path: Path):
    """The exits table as a DataFrame of what the report reads (every row is a spec-key first break already)."""
    import pandas as pd
    df = pd.read_csv(path, sep="\t", usecols=EXITS_USECOLS, keep_default_na=False, na_values=[""], low_memory=False)
    for col in ("K", "stop_variant", "arm", "month"):
        df[col] = df[col].astype("category")
    return df


def quintile_cuts(values) -> list:
    """The four cut points of the fifths of `values` (NaN ignored); [] when there is nothing to cut."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    return [float(np.quantile(v, q)) for q in (0.2, 0.4, 0.6, 0.8)] if len(v) else []


def fifth_of(x, cuts: list):
    """1 (lowest fifth) .. 5 for `x` against the cuts; 0 when unknown."""
    a = np.asarray(x, dtype=float)
    out = np.ones(len(a), dtype=int)
    for cut in cuts:
        out += (a > cut).astype(int)
    return np.where(np.isfinite(a) & (len(cuts) == 4), out, 0)


def _exits_group_row(g, cell: str, k, sv, a, slice_name: str, value, *, ci: bool, too_wide: int = 0) -> dict:
    row = _group_row(g, "spec", cell, k, HEADLINE_VARIANT, a, slice_name, value, ci=ci)
    row.update(stop_variant=sv, too_wide=too_wide)
    row.pop("variant", None)
    return row


def build_exits_rows(df) -> tuple:
    """(rows, fifth_cuts, best): every (cell, K, stop variant, arm) of EXITS_CELLS over the mature walks ('all' with the
    month-block interval), the too_wide count of each (cell, K, stop variant), for each stop variant that abstained on
    some trades the registered arm on exactly ITS usable trades (slice "matched", value = the variant), and the tightness
    slice (fifths of range_recent5 / ADR20 and of tightening_ratio, cut PER LEVEL on its C0 filled population) under the
    registered row and the best two NEW combos of that level. `best` = the combos ranked on C0 by `EXITS_RANK` (P&L in
    ADR units: R's unit changes with the stop) AMONG the full-population combos (`EXITS_FULL_POP_MIN`), written down
    here before any table is read."""
    import pandas as pd
    rows, cuts, best = [], {}, {}
    for k, kdf in df.groupby("K", observed=True):
        c0 = kdf[(kdf["C0"] == 1)]
        one = c0[(c0["stop_variant"] == EXITS_PRIMARY[0]) & (c0["arm"] == EXITS_PRIMARY[1])]      # one row per filled entry
        cuts[k] = {m: quintile_cuts(one[m].to_numpy(dtype=float)) for m, _s in FIFTH_MEASURES}
        fifth = {m: pd.Series(fifth_of(kdf[m], cuts[k][m]), index=kdf.index) for m, _s in FIFTH_MEASURES}   # by frame label
        key = kdf["ticker"].astype(str) + "|" + kdf["D"].astype(str)                                   # one entry = (ticker, D)
        usable = {sv: set(key[(kdf["stop_variant"] == sv) & kdf["arm"].notna()]) for sv in cb.STOP_VARIANTS}
        ranked = []
        for cell in EXITS_CELLS:
            sub = kdf[kdf[cell] == 1]
            tw = sub[sub["arm"].isna() & (sub["abstain_reason"] == "too_wide")].groupby("stop_variant", observed=True).size()
            ar = sub[sub["arm"].notna()]
            prim = ar[(ar["stop_variant"] == EXITS_PRIMARY[0]) & (ar["arm"] == EXITS_PRIMARY[1])]
            n_prim = len(prim)
            for (sv, a), g in ar.groupby(["stop_variant", "arm"], observed=True):
                r = _exits_group_row(g, cell, k, sv, a, "all", "", ci=True, too_wide=int(tw.get(sv, 0)))
                rows.append(r)
                full = n_prim > 0 and len(g) >= EXITS_FULL_POP_MIN * n_prim
                if cell == "C0" and full and (sv, a) != EXITS_PRIMARY and r["n"] and r.get(EXITS_RANK) is not None:
                    ranked.append((r[EXITS_RANK], sv, a))
            for sv in cb.STOP_VARIANTS:                      # the registered arm on the trades this stop variant kept
                if int(tw.get(sv, 0)) and len(prim):
                    gm = prim[key.loc[prim.index].isin(usable[sv])]
                    if len(gm):
                        rows.append(_exits_group_row(gm, cell, k, EXITS_PRIMARY[0], EXITS_PRIMARY[1], "matched", sv, ci=True))
        ranked.sort(key=lambda x: (-x[0], x[1], x[2]))
        best[k] = [(sv, a) for _v, sv, a in ranked[:3]]
        combos = [EXITS_PRIMARY] + best[k][:2]
        for cell in ("C0", "C1"):
            sub = kdf[(kdf[cell] == 1) & kdf["arm"].notna() & (kdf["mature"] == 1)]
            for sv, a in combos:
                g = sub[(sub["stop_variant"] == sv) & (sub["arm"] == a)]
                for m, sname in FIFTH_MEASURES:
                    f = fifth[m].loc[g.index].to_numpy() if len(g) else np.array([], dtype=int)
                    for q in range(1, 6):
                        gq = g[f == q]
                        if len(gq):
                            rows.append(_exits_group_row(gq, cell, k, sv, a, sname, q, ci=False))
    return rows, cuts, best


def exits_report_text(rows: list, cuts: dict, best: dict, src: Path, levels, counts: dict) -> str:
    idx = {(r["cell"], r["K"], r["stop_variant"], r["arm"], r["slice"], r["value"]): r for r in rows}
    out = []
    A = out.append
    A(f"#702 HIS EXIT - DISCOVERY READ (D 2022-03-28 .. 2024-12-31), levels {'/'.join(levels)}. Exploratory: nothing here decides; the "
      f"stop is the operator's call; the holdout is untouched.")
    A(f"source: {src.name}; rows read {counts['rows']:,}. POPULATION: the spec key's first breaks filled at {HEADLINE_VARIANT} under the "
      f"registered stop (the width rule at the fill); every stop variant can only remove a trade (too_wide), never add one.")
    A(f"ARMS: {cb.PRIMARY_ARM} (registered: 1/3 at the close of session 3, breakeven, SMA10 trail) beside {len(cb.HIS_EXIT_ARMS)} his-exit arms "
      f"<trigger>_p33_<trail>: trigger r2 = 1/3 at +2R (a gap open above it at the open; day 0 on the minutes), d3 / d5 = the close of "
      f"session 3 / 5, c3 / c5 = whichever comes first; trail t10 / t20 fixed, tspd = SMA10 when ADR20(D) > {cb.TRAIL_SPEED_ADR_CUT} "
      f"(his 'faster stocks': the top tercile of the discovery C0 ADR distribution) else SMA20, td1 / td2 = at the partial, SMA10 when "
      f"the close is more than 1 / 2 ADR20 above its SMA10 else SMA20. The trail is live only after the partial, filled at the next open.")
    A(f"STOPS: lod = the low of the day at the fill (registered); lod_cap05 = max(lod, fill - 0.5 ADR); lod_floor05 = min(lod, fill - 0.5 ADR); "
      f"level_m05 = the breakout level (the pivot) - 0.5 ADR; base_low = the base's low; each skipped as too_wide beyond one ADR20. "
      f"R = fill - that stop, so R is NOT comparable across stops: combos are ranked on {EXITS_RANK} (P&L in ADR units), R and the tail beside.")
    A(f"A group is the MATURE walks only; month-block bootstrap ({BOOT_DRAWS:,} draws, seed {BOOT_SEED}) 95% interval on the mean R.")
    A("")
    cols = ["stop", "arm", "n", "open", "mean pnl_adr", "mean R", "95% CI", ">=5R", ">=10R", "ex-top5", "median", "win", "too_wide"]

    def line(r):
        return [r["stop_variant"], r["arm"], r["n"], r["n_open"], _num(r.get("mean_pnl_adr")), _num(r.get("mean_r")), _ci(r),
                _pct(r.get("share_ge5")), _pct(r.get("share_ge10")), _num(r.get("mean_ex_top5")), _num(r.get("median_r")),
                _pct(r.get("win_rate")), r.get("too_wide", 0)]

    A(f"HEADLINE - per level, the registered row and the best three NEW arm x stop combos (ranked on C0 by {EXITS_RANK} among the combos "
      f"that kept >= {EXITS_FULL_POP_MIN:.0%} of the registered row's trades - the same population), on C0 and C1")
    for k in levels:
        for cell in ("C0", "C1"):
            body = []
            for sv, a in [EXITS_PRIMARY] + best.get(k, []):
                r = idx.get((cell, k, sv, a, "all", ""))
                if r:
                    body.append(line(r))
            if body:
                A(f"  {cell} / {k}")
                A(table(body, cols))
    A("")
    A("SUBPOPULATION STOPS - a stop that is too_wide on most trades keeps a DIFFERENT population (the bases whose low sits within one ADR "
      "of the fill); its best arm is shown against the registered arm on exactly the SAME trades ('matched'), never ranked above")
    for k in levels:
        for cell in ("C0", "C1"):
            body = []
            for sv in cb.STOP_VARIANTS:
                m = idx.get((cell, k, EXITS_PRIMARY[0], EXITS_PRIMARY[1], "matched", sv))
                if m is None:
                    continue
                rs = [r for key, r in idx.items() if key[:3] == (cell, k, sv) and key[4] == "all" and r["n"]]
                rs.sort(key=lambda r: (-(r.get(EXITS_RANK) if r.get(EXITS_RANK) is not None else -1e9), r["arm"]))
                if rs:
                    body.append(line(rs[0]))
                    mm = line(m)
                    mm[1] = f"{mm[1]} (matched)"
                    body.append(mm)
            if body:
                A(f"  {cell} / {k}")
                A(table(body, cols))
    A("")
    A(f"ALL COMBOS - per level and cell ({' / '.join(EXITS_CELLS)}), every stop x arm, sorted by {EXITS_RANK} (the registered row marked *)")
    for k in levels:
        for cell in EXITS_CELLS:
            rs = [r for key, r in idx.items() if key[0] == cell and key[1] == k and key[4] == "all"]
            rs.sort(key=lambda r: (-(r.get(EXITS_RANK) if r.get(EXITS_RANK) is not None else -1e9), r["stop_variant"], r["arm"]))
            body = []
            for r in rs:
                ln = line(r)
                if (r["stop_variant"], r["arm"]) == EXITS_PRIMARY:
                    ln[1] = ln[1] + " *"
                body.append(ln)
            if body:
                A(f"  {cell} / {k}")
                A(table(body, cols))
    A("")
    A("TIGHTNESS - fifths of range_recent5 / ADR20 (the last 5 sessions' mean range in ADR units) and of tightening_ratio (last 5 / first 5), "
      "cut per level on its C0 filled population; each cell is n / mean R / share >= 5R / mean pnl_adr. Under the registered row and the best "
      "two new combos. The operator's A+ question: tighter before the breakout = better?")
    for k in levels:
        for m, sname in FIFTH_MEASURES:
            c_ = cuts.get(k, {}).get(m, [])
            A(f"  {k} {m}: fifth cuts " + (" / ".join(f"{x:.3f}" for x in c_) if c_ else "(none)"))
            for cell in ("C0", "C1"):
                body = []
                for sv, a in [EXITS_PRIMARY] + best.get(k, [])[:2]:
                    ln = [cell, sv, a]
                    for q in range(1, 6):
                        r = idx.get((cell, k, sv, a, sname, q))
                        ln.append("0" if r is None or not r["n"] else
                                  f"{r['n']}/{_num(r.get('mean_r'), 2)}/{_pct(r.get('share_ge5'))}/{_num(r.get('mean_pnl_adr'), 2)}")
                    body.append(ln)
                A(table(body, ["cell", "stop", "arm", "1 (tightest)", "2", "3", "4", "5 (widest)"]))
    return "\n".join(out)


def run_exits_report(args) -> int:
    T0 = time.time()
    data = Path(args.data)
    out = Path(args.out) if args.out else data / "out"
    small = Path(args.small_out) if args.small_out else HERE / "out"
    keys, sfx = run_keys(args)
    levels = parse_levels(getattr(args, "levels", None), keys)
    tag = exits_tag(levels)
    src = Path(args.trades) if args.trades else out / f"trades_discovery_exits{tag}.tsv.gz"
    if not src.exists():
        print(f"exits-report: {src} not found - run `exits` first", file=sys.stderr)
        return 1
    small.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    df = load_exits_frame(src)
    counts = {"rows": len(df)}
    print(f"[read {len(df):,} rows: {time.time() - T0:.0f}s]", flush=True)
    name = f"exits_report{tag}"
    if not len(df):
        msg = f"exits-report: {src.name} is empty - nothing to report"
        (small / f"{name}.txt").write_text(msg + "\n")
        print(msg)
        return 0
    rows, cuts, best = build_exits_rows(df)
    cols = exits_stat_cols()
    write_tsv(out / f"{name}.tsv", rows, cols)
    compact = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]
    write_tsv(small / f"{name}.tsv", compact, cols)
    text = exits_report_text(rows, cuts, best, src, levels, counts)
    (small / f"{name}.txt").write_text(text + "\n")
    print(text)
    print(f"WROTE {out / (name + '.tsv')} ({len(rows):,} rows), {small / (name + '.tsv')}, {small / (name + '.txt')}; "
          f"WALL TIME {time.time() - T0:.0f}s")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the holdout guard - freeze_check, copied in structure from scripts/probes/_686/preregistered_read.py::freeze_check
# ═════════════════════════════════════════════════════════════════════════════════════════════
def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _is_minute_data_file(p: Path) -> bool:
    return p.is_file() and (p.name.endswith(".psv.gz") or p.name == "_done.psv")


def sha256_tree(root: Path) -> str:
    """One pin for the minute directory: sha256 over the sorted `relative path TAB file sha256` lines of its DATA files
    (`<date>.psv.gz` and `_done.psv`; not the fetch log or OS litter)."""
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if _is_minute_data_file(p):
            h.update(f"{p.relative_to(root).as_posix()}\t{sha256_file(p)}\n".encode())
    return h.hexdigest()


def doc_body_sha(doc_text: str) -> str:
    """sha256 of every byte of the registration doc ABOVE the freeze marker (a file cannot hold its own hash)."""
    return hashlib.sha256(doc_text.split(FREEZE_MARK, 1)[0].encode("utf-8")).hexdigest()


# Repo code, besides the module and this runner, that the holdout OUTCOME numbers are computed with: {footer label:
# path under the repo}. DERIVED, not guessed (`tests/test_cb_backtest_runner.py::TestHoldoutGuard::test_every_repo_file_the_
# outcome_path_computes_with_is_pinned` walks the call graph from `evaluate_candidate` and fails on a repo module that is
# neither here nor in FROZEN_CODE_EXEMPT): constants.py holds ENTRY_SLIPPAGE_PCT (sets every minute fill and so every R);
# anticipation.py = the Family A control (`simulate`, `build_mixed_path`, `SETTLE_RULE`); live_fill_counterfactuals.py
# = the Apollo control (`walk_arm`, `stack_walk_inputs`); rule_eras.py = the stack that control is built from;
# exit_logic.py = the ladder / depth-stop math `walk_arm` settles through.
FROZEN_CODE = {"code/constants.py": "agents/market_intelligence/constants.py",
               "code/anticipation.py": "agents/market_intelligence/anticipation.py",
               "code/live_fill_counterfactuals.py": "agents/market_intelligence/live_fill_counterfactuals.py",
               "code/rule_eras.py": "agents/market_intelligence/rule_eras.py",
               "code/exit_logic.py": "agents/market_intelligence/broker/exit_logic.py"}
# Repo modules the outcome path imports from but that are deliberately NOT pinned: {module: why}.
FROZEN_CODE_EXEMPT = {"agents.market_intelligence.db": "`_f`, a one-line float coercion, is all walk_arm takes from it; the file is "
                                                       "1 MB of live-DB code edited weekly, so pinning it would refuse a clean holdout"}


def frozen_files(data: Path, repo: Path = REPO, minutes: "Path | None" = None) -> dict:
    """{footer label: path} - everything the holdout read rests on. A label is the key the registration doc's footer
    must carry as `<label> sha256: <hex>`; `holdout --print-pins` prints the current lines for P4 to paste."""
    data = Path(data)
    out = {"module": Path(repo) / "agents" / "market_intelligence" / "consolidation_breakout.py",
           "runner": Path(__file__).resolve(),
           "cell table": data / "out" / "watch.tsv.gz"}            # the cells are post-hoc flags on this one table
    for label, rel in FROZEN_CODE.items():                         # the code and constants the controls and the fills use
        out[label] = Path(repo) / rel
    for p in sorted(data.glob("*")):                               # every data file (the export, SIC, splits, VIX, small pulls, ...)
        if p.is_file() and not p.name.startswith("."):
            out[f"data/{p.name}"] = p
    out["minutes (tree)"] = Path(minutes) if minutes else data / "minutes"
    for name in ("candidates.tsv", "minute_fetch_list.tsv", "gap_in_bars.tsv", "close_variant_discovery.tsv.gz",
                 "trades_discovery.tsv.gz", "entries_discovery.tsv.gz", "entries_holdout_composition.tsv",
                 f"{REPORT_NAME}.tsv"):
        out[name] = data / "out" / name
    out[f"{REPORT_NAME}.txt"] = HERE / "out" / f"{REPORT_NAME}.txt"
    # #702 P5: the holdout now also reads the com / comb candidates (their cell table too) and is registered beside the
    # entry-time composition of those levels and the discovery P5 walk whose numbers the registration quotes
    for name in ("candidates_com_comb.tsv", "watch_com_comb.tsv.gz", "entries_holdout_composition_com_comb.tsv",
                 f"trades_discovery_{P5_NAME}.tsv.gz", "p5_report_discovery.tsv"):
        out[name] = data / "out" / name
    out["p5_report_discovery.txt"] = HERE / "out" / "p5_report_discovery.txt"
    return out


def frozen_hashes(data: Path, repo: Path = REPO, minutes: "Path | None" = None) -> dict:
    got = {}
    for label, p in frozen_files(data, repo, minutes).items():
        p = Path(p)
        got[label] = sha256_tree(p) if p.is_dir() else (sha256_file(p) if p.is_file() else None)
    return got


def find_prereg_doc(repo: Path = REPO) -> tuple:
    """(path or None, problem or None): the single `docs/analysis/cb_preregistration_*.md`. None or several refuses."""
    hits = sorted(glob.glob(str(Path(repo) / "docs" / "analysis" / "cb_preregistration_*.md")))
    if len(hits) == 1:
        return Path(hits[0]), None
    if not hits:
        return None, "registration doc missing: docs/analysis/cb_preregistration_*.md"
    return None, f"{len(hits)} registration docs match docs/analysis/cb_preregistration_*.md - pass --prereg"


def freeze_check(*, doc: "Path | None" = None, data: Path, repo: Path = REPO, minutes: "Path | None" = None) -> list:
    """Problems (empty = every frozen artefact matches the registration doc's footer). Refuses on a missing doc, a
    missing FREEZE marker, a pin the footer does not carry, a pinned file that is missing, and any sha256 mismatch."""
    problems: list = []
    if doc is None:
        doc, problem = find_prereg_doc(repo)
        if problem:
            return [problem]
    doc = Path(doc)
    if not doc.is_file():
        return [f"registration doc missing: {doc}"]
    text = doc.read_text(encoding="utf-8")
    if FREEZE_MARK not in text:
        return [f"registration doc has no {FREEZE_MARK} marker"]
    footer = text.split(FREEZE_MARK, 1)[1]
    got = frozen_hashes(data, repo, minutes)
    got["doc body"] = doc_body_sha(text)
    for k, g in got.items():
        m = re.search(rf"(?m)^\s*[-*]?\s*{re.escape(k)}\s+sha256:\s*`?([0-9a-f]{{64}})", footer)
        if m is None:
            problems.append(f"footer carries no {k} sha256")
        elif g is None:
            problems.append(f"{k}: file missing")
        elif g != m.group(1):
            problems.append(f"{k} sha256 mismatch: footer {m.group(1)[:12]}... vs now {g[:12]}... - the frozen artefact was edited")
    return problems


def pin_lines(data: Path, repo: Path = REPO, minutes: "Path | None" = None) -> list:
    """The footer lines the registration doc must carry (everything but 'doc body', which P4 hashes last)."""
    return [f"- {k} sha256: `{h or 'MISSING'}`" for k, h in frozen_hashes(data, repo, minutes).items()]


def holdout_option_problems(args, data: Path) -> list:
    """Options the once-only holdout run may not carry. The freeze pins `DATA/out/*` and `HERE/out/*`, so anything that
    moves the run's inputs or outputs elsewhere (`--out`: an unpinned candidates.tsv AND a fresh place to look for
    "already joined"), or runs a part of it (`--limit-dates`, `--no-close`, `--no-apollo`), is a way round the freeze.
    `--small-out` only holds a summary, but it is refused with the rest: nothing legitimate needs it on the real run.
    `--minutes` is not here: the minute tree is pinned and the same directory is the one read."""
    bad = []
    if args.out and Path(args.out).resolve() != (Path(data) / "out").resolve():
        bad.append(f"--out {args.out} is not DATA/out ({Path(data) / 'out'}): the pinned candidates.tsv and the 'joined ONCE' check live there")
    if args.small_out and Path(args.small_out).resolve() != (HERE / "out").resolve():
        bad.append(f"--small-out {args.small_out} is not {HERE / 'out'}")
    for flag, on in (("--limit-dates", args.limit_dates), ("--no-close", args.no_close), ("--no-apollo", args.no_apollo)):
        if on:
            bad.append(f"{flag}: the holdout is one full run; a partial or altered run would also block the real one")
    if getattr(args, "keys", None):
        bad.append(f"--keys {args.keys}: the holdout reads the registered levels only ({'/'.join(KS)}); a level outside the "
                   f"registration (#702 P4b `com`) is read beside it in its own, separately registered run")
    if getattr(args, "levels", None):
        bad.append(f"--levels {args.levels}: an `exits`-stage option (#702 his exit, discovery only); the holdout walks the registered "
                   f"arms on every registered level")
    return bad


def holdout_existing_outputs(out: Path) -> list:
    """Holdout outputs already on disk: the final tables, or the `.partial` a crashed run left behind."""
    return [q for name in ("trades_holdout.tsv.gz", "entries_holdout.tsv.gz", f"trades_holdout_{P5_NAME}.tsv.gz")
            for q in (Path(out) / name, partial_path(Path(out) / name)) if q.exists()]


def run_holdout(args) -> int:
    """`holdout` - BUILT, NOT RUN. The same engine as `minute`, on the HOLDOUT, run ONCE after the P4 freeze.
    exit 2 on: --out / --small-out elsewhere or --limit-dates / --no-close / --no-apollo, --no-freeze-check without
    --dry-run, any freeze problem, outputs (or a crashed run's `.partial`) that already exist."""
    data = Path(args.data)
    minutes = Path(args.minutes) if args.minutes else None
    if args.print_pins:
        print("\n".join(pin_lines(data, REPO, minutes)))
        return 0
    bad = holdout_option_problems(args, data)
    if bad:
        print("REFUSED: the holdout runs only in its registered form:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 2
    if args.no_freeze_check and not args.dry_run:
        print("REFUSED: --no-freeze-check is honoured only together with --dry-run", file=sys.stderr)
        return 2
    if not args.no_freeze_check:
        problems = freeze_check(doc=Path(args.prereg) if args.prereg else None, data=data, repo=REPO, minutes=minutes)
        if problems:
            print("REFUSED: the freeze check failed - the holdout is not opened:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 2
    out = data / "out"
    if args.dry_run:
        inp = _setup_minute_inputs(args, "holdout")
        p5c = p5_candidates(out, "holdout")
        print(f"DRY RUN (freeze check {'SKIPPED' if args.no_freeze_check else 'passed'}): would read {out / 'candidates.tsv'} "
              f"({len(inp['cands']):,} holdout candidate rows), the minute files in {inp['minutes_dir']} "
              f"({len(inp['files'])} dates; {sum(len(v) for v in inp['by_date'].values()):,} candidates on them) and the daily export "
              f"{data / 'daily_closes_all.csv.gz'}; would write {out / 'trades_holdout.tsv.gz'} and {out / 'entries_holdout.tsv.gz'}; "
              f"then the P5 stage on {len(p5c):,} first-break rows of {'/'.join(P5_LEVELS)} (candidates.tsv + candidates_com_comb.tsv), "
              f"writing {out / f'trades_holdout_{P5_NAME}.tsv.gz'}, {out / 'p5_report_holdout.tsv'} and appending to "
              f"{out / 'regime_report_holdout.tsv'}. Nothing was opened beyond candidate counts.")
        return 0
    existing = holdout_existing_outputs(out)
    if existing:
        crashed = [q for q in existing if q.name.endswith(".partial")]
        if crashed:
            print(f"REFUSED: {crashed[0]} is what a CRASHED holdout run left behind - it holds some holdout outcomes. "
                  f"The holdout is joined ONCE: the operator inspects it and removes it by hand before any re-run", file=sys.stderr)
        else:
            print(f"REFUSED: the holdout outcomes are joined ONCE and {existing[0]} already exists", file=sys.stderr)
        return 2
    run_minute_stage(args, "holdout")
    return run_p5_stage(args, "holdout")      # #702 P5: the primary exit (his rule, stalls cut) and the rows beside it, same run


# ═════════════════════════════════════════════════════════════════════════════════════════════
# report - the DISCOVERY read
# ═════════════════════════════════════════════════════════════════════════════════════════════
STAT_COLS = ["n", "n_filled", "n_open", "mean_r", "ci_lo", "ci_hi", "share_ge3", "share_ge5", "share_ge10", "mean_ex_top5",
             "median_r", "win_rate", "mean_pnl_adr", "mean_acct_pct", "sum_r"]
REPORT_SLICES = (("year", "year"), ("phase", "phase_qqq_10_20"), ("gap_over_1adr", "gap_over_1adr"),
                 ("dv_tercile", "dv_t"), ("adr_tercile", "adr_t"), ("month", "month"))
REPORT_KEYS = (("spec", "retrigger", "SPEC key (ticker, pole_date, K)"),
               ("chain", "retrigger_chain", "CHAIN key (poles <= 3 sessions apart = one base)"))


def block_bootstrap_ci(values, blocks, *, draws: int = BOOT_DRAWS, seed: int = BOOT_SEED, key: str = "",
                       alpha: float = 0.05) -> tuple:
    """Month-block bootstrap of the MEAN: resample whole calendar-month blocks with replacement (as many blocks as
    there are months), `draws` times, and take the 2.5 / 97.5 percentiles. The generator is seeded from (seed,
    crc32(key)) so every group has its own fixed stream and the result never depends on iteration order."""
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return (float("nan"), float("nan"))
    uniq, inv = np.unique(np.asarray(blocks), return_inverse=True)
    m = len(uniq)
    sums = np.bincount(inv, weights=v, minlength=m)
    cnts = np.bincount(inv, minlength=m).astype(float)
    rng = np.random.default_rng([seed, zlib.crc32(key.encode())])
    idx = rng.integers(0, m, size=(draws, m))
    means = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return (float(np.percentile(means, 100.0 * alpha / 2)), float(np.percentile(means, 100.0 * (1.0 - alpha / 2))))


def tercile_cuts(values) -> tuple:
    """(q33, q67) of the values (NaN ignored) - the cut points of the dollar-volume / ADR terciles."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    return (float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3))) if len(v) else (float("nan"), float("nan"))


def tercile_of(x, cuts: tuple):
    """1 (low) .. 3 (high) for `x` against the cuts; 0 when x or a cut is unknown."""
    a = np.asarray(x, dtype=float)
    out = 1 + (a > cuts[0]).astype(int) + (a > cuts[1]).astype(int)
    return np.where(np.isfinite(a) & np.isfinite(cuts[0]), out, 0)


def rstats(r, pnl_adr=None, acct=None) -> dict:
    """The per-group statistics. `mean_ex_top5` drops the five largest R (None for n <= 5)."""
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n == 0:
        return {"n": 0}
    srt = np.sort(r)

    def nm(x):
        x = np.asarray(x, dtype=float)
        x = x[np.isfinite(x)]
        return float(x.mean()) if len(x) else None
    return {"n": n, "mean_r": float(r.mean()), "median_r": float(np.median(r)), "win_rate": float((r > 0).mean()),
            "share_ge3": float((r >= 3).mean()), "share_ge5": float((r >= 5).mean()), "share_ge10": float((r >= 10).mean()),
            "mean_ex_top5": float(srt[:-5].mean()) if n > 5 else None,
            "mean_pnl_adr": nm(pnl_adr) if pnl_adr is not None else None,
            "mean_acct_pct": nm(acct) if acct is not None else None, "sum_r": float(r.sum())}


REPORT_USECOLS = (["ticker", "D", "K", "variant", "arm", "status", "realized_r", "pnl_adr", "acct_pct", "mature", "retrigger",
                   "retrigger_chain", "year", "month", "gap_over_1adr", "adr20", "median_dollar_vol20", "phase_qqq_10_20",
                   "width_pct", "atr14_wide", "abstain_reason", "r_h60", "mature_h60", "cap_realized_r", "cap_mature"]
                  + [n for _f, n in FLOORS] + list(CELL_NAMES))


def load_report_frame(path: Path, regime_of: "dict | None" = None) -> tuple:
    """(DataFrame, tercile cuts, counts). Reads the trades table in chunks and keeps only what the read uses: the
    NON-RETRIGGER rows (spec key; the chain population is a subset of them), and of those only the rows that carry an
    arm or a `too_wide` abstain. The tercile cuts are taken on the discovery C0 distribution - one row per
    candidate at the headline entry - BEFORE any filtering to a cell.
    `regime_of` ({D: apollo_regime label}, #702 P4b step 6b) adds a `regime` column (D absent from the map -> "missing") for
    the per-regime table; the trades layout is untouched (the label is joined here, at read time) and nothing the
    default report writes reads the column."""
    import pandas as pd
    parts, dv, adr = [], [], []
    counts = Counter()
    for ch in pd.read_csv(path, sep="\t", usecols=REPORT_USECOLS, chunksize=500_000, keep_default_na=False,
                          na_values=[""], low_memory=False):
        counts["rows"] += len(ch)
        counts["retrigger_rows_dropped"] += int((ch["retrigger"] != 0).sum())
        ch = ch[ch["retrigger"] == 0]
        one = ch[(ch["variant"] == HEADLINE_VARIANT) & (ch["C0"] == 1) & (ch["arm"].isna() | (ch["arm"] == cb.PRIMARY_ARM))]
        dv.append(one["median_dollar_vol20"].to_numpy(dtype=float))
        adr.append(one["adr20"].to_numpy(dtype=float))
        ch = ch[ch["arm"].notna() | (ch["abstain_reason"] == "too_wide")]
        if regime_of is not None:
            ch = ch.assign(regime=ch["D"].map(regime_of).fillna(REGIME_MISSING))
        parts.append(ch.drop(columns=["ticker", "D"]))
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=[c for c in REPORT_USECOLS if c not in ("ticker", "D")] + (["regime"] if regime_of is not None else []))
    cuts = {"dv": tercile_cuts(np.concatenate(dv) if dv else []), "adr": tercile_cuts(np.concatenate(adr) if adr else [])}
    df["dv_t"] = tercile_of(df["median_dollar_vol20"], cuts["dv"])
    df["adr_t"] = tercile_of(df["adr20"], cuts["adr"])
    for c in ("K", "variant", "arm", "month") + (("regime",) if regime_of is not None else ()):
        df[c] = df[c].astype("category")
    return df, cuts, counts


def _group_row(g, key_name: str, cell: str, k, v, a, slice_name: str, value, *, ci: bool) -> dict:
    """One TSV row for one group of ARM rows (a pandas frame): maturity split, statistics, optional bootstrap CI."""
    if isinstance(value, (float, np.floating, np.integer)) and float(value).is_integer():
        value = int(value)
    gm = g[g["mature"] == 1]
    s = rstats(gm["realized_r"].to_numpy(dtype=float), gm["pnl_adr"].to_numpy(dtype=float), gm["acct_pct"].to_numpy(dtype=float))
    row = {"key": key_name, "cell": cell, "K": k, "variant": v, "arm": a, "slice": slice_name, "value": value,
           "n_filled": len(g), "n_open": len(g) - s["n"], **{c: s.get(c) for c in STAT_COLS if c in s}}
    if ci and s["n"] >= 2:
        row["ci_lo"], row["ci_hi"] = block_bootstrap_ci(gm["realized_r"].to_numpy(dtype=float), gm["month"].astype(str).to_numpy(),
                                                       key=f"{key_name}|{cell}|{k}|{v}|{a}")
    return row


def build_report_rows(df) -> tuple:
    """(rows, too_wide) - the full report table. rows: one per key x cell x K x variant x arm x slice ('all' carries the
    bootstrap CI; year / phase / gap_over_1adr / dv_tercile / adr_tercile / month slices carry the statistics).
    too_wide[(key, cell, K, variant)] = the skipped-entry count."""
    rows, too_wide = [], {}
    for key_name, col, _label in REPORT_KEYS:
        kdf = df if col == "retrigger" else df[df["retrigger_chain"] == 0]
        for cell in CELL_NAMES:
            sub = kdf[kdf[cell] == 1]
            tw = sub[sub["arm"].isna() & (sub["abstain_reason"] == "too_wide")]
            for (k, v), g in tw.groupby(["K", "variant"], observed=True):
                too_wide[(key_name, cell, k, v)] = len(g)
            ar = sub[sub["arm"].notna()]
            if not len(ar):
                continue
            for (k, v, a), g in ar.groupby(["K", "variant", "arm"], observed=True):
                rows.append(_group_row(g, key_name, cell, k, v, a, "all", "", ci=True))
            arm = ar[ar["mature"] == 1]
            for sname, scol in REPORT_SLICES:
                for (k, v, a, val), g in arm.groupby(["K", "variant", "arm", scol], observed=True):
                    rows.append(_group_row(g, key_name, cell, k, v, a, sname, val, ci=False))
    return rows, too_wide


# -- #702 P4b step 6b: the per-regime table (reported BESIDE, never deciding; its own files, no pinned byte moves) ----------
REGIME_ORDER = ("Bull", "Choppy", "Correcting", "Crisis")      # Apollo's daily regime label (`apollo_regime`)
REGIME_MISSING = "missing"                                     # a D with no label (blank in small_pulls) or absent from the map
REGIME_COLS = ["key", "cell", "K", "variant", "arm", "slice", "value"] + STAT_COLS


def regime_label(x) -> str:
    """The table's label for a candidate's `apollo_regime` ("" / None -> "missing")."""
    x = "" if x is None else str(x).strip()
    return x if x and x.lower() != "nan" else REGIME_MISSING


def regime_by_date(path: Path) -> dict:
    """{D: regime label} from a candidates table (`apollo_regime` is one value per date - the daily stage stamps it from D).
    A missing file is an empty map: every row then reads "missing", and the caller says so."""
    import pandas as pd
    if not Path(path).exists():
        return {}
    d = pd.read_csv(path, sep="\t", usecols=["D", "apollo_regime"], dtype=str, keep_default_na=False).drop_duplicates()
    return {k: regime_label(v) for k, v in zip(d["D"], d["apollo_regime"])}


def regime_report_rows(df) -> list:
    """The headline table (entry `HEADLINE_VARIANT`, arm `cb.PRIMARY_ARM`) split by `apollo_regime`: for every (key, cell, K) the
    discovery report already prints, an `ALL` row plus one row per regime (Bull / Choppy / Correcting / Crisis / missing, then any
    other label seen), each with n (mature walks) / n_open / mean R / share >= 5R and the rest of `STAT_COLS`. The groups are the
    report's own (`_group_row`, same mature-only rule), so the regime rows' n add up to the `ALL` row and the `ALL` row is the
    headline row of `build_report_rows`. `df` needs the `regime` column (`load_report_frame(regime_of=...)`)."""
    rows = []
    reg = df["regime"].astype(str)
    regimes = list(REGIME_ORDER) + [REGIME_MISSING] + sorted(set(reg.unique()) - set(REGIME_ORDER) - {REGIME_MISSING})
    for key_name, col, _label in REPORT_KEYS:
        kdf = df if col == "retrigger" else df[df["retrigger_chain"] == 0]
        for cell in CELL_NAMES:
            ar = kdf[(kdf[cell] == 1) & kdf["arm"].notna() & (kdf["variant"] == HEADLINE_VARIANT) & (kdf["arm"] == cb.PRIMARY_ARM)]
            for k, gk in ar.groupby("K", observed=True):
                rows.append(_group_row(gk, key_name, cell, k, HEADLINE_VARIANT, cb.PRIMARY_ARM, "regime", "ALL", ci=False))
                rk = reg.loc[gk.index].to_numpy()
                for r_ in regimes:
                    rows.append(_group_row(gk[rk == r_], key_name, cell, k, HEADLINE_VARIANT, cb.PRIMARY_ARM, "regime", r_, ci=False))
    return rows


def regime_report_text(rows: list, title: str, src: str) -> str:
    """The regime rows as text, one table per base key: each cell is `n / mean R / share >= 5R` (the SLICES block's format)."""
    out = [f"{title} - the headline table (entry {HEADLINE_VARIANT}, arm {cb.PRIMARY_ARM}) split by Apollo's daily regime at D. "
           f"Reported BESIDE the report, never deciding; the non-Bull groups are small. source: {src}.",
           "A cell is n / mean R / share >= 5R over the MATURE walks; `0` = no walk in that regime. missing = a D with no regime label."]
    labels = list(dict.fromkeys(r["value"] for r in rows))
    idx = {(r["key"], r["cell"], r["K"], r["value"]): r for r in rows}
    for key_name, _col, label in REPORT_KEYS:
        order = list(dict.fromkeys((r["cell"], r["K"]) for r in rows if r["key"] == key_name))
        body = []
        for cell, k in order:
            line = [cell, k]
            for lab in labels:
                r = idx.get((key_name, cell, k, lab))
                line.append("-" if r is None else ("0" if not r["n"] else f"{r['n']}/{_num(r.get('mean_r'), 2)}/{_pct(r.get('share_ge5'))}"))
            body.append(line)
        out.append(f"  -- {label} --")
        out.append(table(body, ["cell", "K"] + labels) if body else "  (no mature walk)")
    return "\n".join(out)


def write_regime_report(df, out_tsv: Path, out_txt: Path, *, title: str, src: str) -> tuple:
    """(rows written, text): the per-regime table of one report frame (`load_report_frame(regime_of=...)`) -> `out_tsv` (the rows)
    and `out_txt` (the text). An empty frame writes the header only."""
    rows = regime_report_rows(df) if len(df) else []
    write_tsv(out_tsv, rows, REGIME_COLS)
    text = regime_report_text(rows, title, src)
    Path(out_txt).write_text(text + "\n")
    return len(rows), text


def _pct(x):
    return "" if x is None or x != x else f"{100 * x:.1f}%"


def _num(x, nd=3):
    return "" if x is None or x != x else f"{x:+.{nd}f}"


def _ci(row):
    lo, hi = row.get("ci_lo"), row.get("ci_hi")
    return "" if lo is None or lo != lo else f"[{lo:+.2f}, {hi:+.2f}]"


def report_text(df, rows: list, too_wide: dict, cuts: dict, counts: Counter, src: Path, keys=KS) -> str:
    KS_ = tuple(keys)
    idx = {(r["key"], r["cell"], r["K"], r["variant"], r["arm"], r["slice"], r["value"]): r for r in rows}
    out = []
    A = out.append
    A("#702 CONSOLIDATION BREAKOUT - DISCOVERY REPORT (D 2022-03-28 .. 2024-12-31). Exploratory: nothing here decides. The holdout is untouched.")
    A(f"source: {src.name}; table rows read {counts['rows']:,}; retrigger rows dropped {counts['retrigger_rows_dropped']:,}.")
    A("A group is the MATURE walks only (a terminal exit, or the 120-session horizon with 121 forward sessions behind it); an open mark is counted in n_open and never enters a number.")
    A(f"BOOTSTRAP: month-block (calendar month of E), {BOOT_DRAWS:,} resamples, seed {BOOT_SEED}; 95% interval. Terciles are cut on the discovery C0 distribution at the headline entry: "
      f"dollar volume {cuts['dv'][0]:,.0f} / {cuts['dv'][1]:,.0f}; ADR {cuts['adr'][0]:.4f} / {cuts['adr'][1]:.4f}.")
    A(f"CONTROLS: {FAMILY_A_ARM} = Family A's SETTLE_RULE (+1R half, +3R half, day-5 stop) on the same entry and stop; "
      f"{APOLLO_ARM} = the live MAGNA53 ladder (+8 ORB-R partial, +3 ORB-R breakeven, depth trail) walked by live_fill_counterfactuals.walk_arm on the same entry and stop, anchored on the trade's "
      f"own placed risk (1 placed-risk R = 2 ORB-R). Every arm's R is in units of fill - the entry's own stop.")
    A("")
    A(f"HEADLINE - entry {HEADLINE_VARIANT}, arm {cb.PRIMARY_ARM}. Tail first: share of trades at >= 5R and >= 10R, then mean R with its month-block interval, the mean without the five best, the median.")
    for key_name, _col, label in REPORT_KEYS:
        A(f"  -- {label} --")
        body = []
        for cell in CELL_NAMES:
            for k in KS_:
                r = idx.get((key_name, cell, k, HEADLINE_VARIANT, cb.PRIMARY_ARM, "all", ""))
                tw = too_wide.get((key_name, cell, k, HEADLINE_VARIANT), 0)
                if r is None:
                    body.append([cell, k, 0, 0, "", "", "", "", "", "", "", tw])
                    continue
                body.append([cell, k, r["n"], r["n_open"], _pct(r.get("share_ge5")), _pct(r.get("share_ge10")),
                             _num(r.get("mean_r")), _ci(r), _num(r.get("mean_ex_top5")), _num(r.get("median_r")),
                             _pct(r.get("win_rate")), tw])
        A(table(body, ["cell", "K", "n", "open", ">=5R", ">=10R", "mean R", "95% CI", "ex-top5", "median", "win", "too_wide skips"]))
    A("")
    A("TOO_WIDE SKIPS per cell (entries skipped because the stop was wider than one ADR), spec key, by entry variant")
    for key_name, _col, label in REPORT_KEYS[:1]:
        body = []
        for cell in CELL_NAMES:
            for k in KS_:
                body.append([cell, k] + [too_wide.get((key_name, cell, k, v), 0) for v in ALL_VARIANTS])
        A(table(body, ["cell", "K"] + list(ALL_VARIANTS)))
    A("")
    A(f"ARMS - entry {HEADLINE_VARIANT}, spec key: every exit arm and both controls (n = mature walks; R in cb units; pnl_adr is the size-free comparison)")
    for cell in ("C0", "C1"):
        for k in KS_:
            body = []
            for a in ALL_ARMS:
                r = idx.get(("spec", cell, k, HEADLINE_VARIANT, a, "all", ""))
                if r:
                    body.append([a, r["n"], r["n_open"], _num(r.get("mean_r")), _ci(r), _pct(r.get("share_ge5")),
                                 _num(r.get("mean_ex_top5")), _num(r.get("median_r")), _num(r.get("mean_pnl_adr")),
                                 _num(r.get("mean_acct_pct"), 4)])
            if body:
                A(f"  {cell} / {k}")
                A(table(body, ["arm", "n", "open", "mean R", "95% CI", ">=5R", "ex-top5", "median", "mean pnl_adr", "mean acct%"]))
    A("")
    A(f"SLICES - entry {HEADLINE_VARIANT}, arm {cb.PRIMARY_ARM}, spec key: n / mean R / share >= 5R (by calendar year of E, QQQ 10/20 phase at D, gap over 1 ADR, dollar-volume and ADR terciles)")
    for cell in CELL_NAMES:
        for k in KS_:
            parts = []
            for sname, _scol in REPORT_SLICES[:-1]:
                vals = sorted({r["value"] for kk, r in idx.items() if kk[:5] == ("spec", cell, k, HEADLINE_VARIANT, cb.PRIMARY_ARM) and r["slice"] == sname},
                              key=lambda x: str(x))
                cells_ = []
                for val in vals:
                    r = idx[("spec", cell, k, HEADLINE_VARIANT, cb.PRIMARY_ARM, sname, val)]
                    cells_.append(f"{val}: {r['n']}/{_num(r.get('mean_r'), 2)}/{_pct(r.get('share_ge5'))}")
                if cells_:
                    parts.append(f"{sname} " + "  ".join(cells_))
            if parts:
                A(f"  {cell} {k}: " + " | ".join(parts))
    A("")
    A(f"SUM OF R PER MONTH - C0 and C1, K={KS_[0]}, entry {HEADLINE_VARIANT}, arm {cb.PRIMARY_ARM}, spec key (full table in the TSV)")
    for cell in ("C0", "C1"):
        ms = sorted((r["value"], r["sum_r"]) for kk, r in idx.items()
                    if kk[:5] == ("spec", cell, KS_[0], HEADLINE_VARIANT, cb.PRIMARY_ARM) and r["slice"] == "month")
        A(f"  {cell}: " + ("  ".join(f"{m}:{s:+.1f}" for m, s in ms) if ms else "(no mature trade)"))
    A("")
    A(f"SENSITIVITIES - entry {HEADLINE_VARIANT}, arm {cb.PRIMARY_ARM}, spec key; each cell is n / mean R; none of them decides")
    body = []
    base_df = df[(df["variant"] == HEADLINE_VARIANT) & (df["retrigger"] == 0)]
    for cell in CELL_NAMES:
        for k in KS_:
            sub = base_df[(base_df[cell] == 1) & (base_df["K"] == k)]
            prim = sub[(sub["arm"] == cb.PRIMARY_ARM) & (sub["mature"] == 1)]
            capd = sub[sub["arm"].isna() & (sub["abstain_reason"] == "too_wide") & (sub["cap_mature"] == 1)]
            h60 = sub[(sub["arm"] == cb.PRIMARY_ARM) & (sub["mature_h60"] == 1)]

            def nm(frame, col):
                x = frame[col].to_numpy(dtype=float)
                x = x[np.isfinite(x)]
                return f"{len(x)} / {x.mean():+.3f}" if len(x) else "0 / -"
            cap_n = len(capd) + len(prim)
            cap_mean = ((capd["cap_realized_r"].sum() + prim["realized_r"].sum()) / cap_n) if cap_n else None
            row = [cell, k, nm(prim, "realized_r"),
                   f"{cap_n} / {cap_mean:+.3f}" if cap_mean is not None else "0 / -", nm(h60, "r_h60")]
            for _f, nme in FLOORS[1:]:
                row.append(nm(prim[prim[nme] == 0], "realized_r"))
            row.append(nm(prim[prim["atr14_wide"] == 0], "realized_r"))
            row.append(f"{prim['acct_pct'].mean():+.4f}" if len(prim) else "-")
            body.append(row)
    A(table(body, ["cell", "K", "base", "+cap-not-skip", "horizon 60", "floor .25", "floor .5", "floor .75", "floor 1.0",
                   "width<=ATR14", "mean acct%"]))
    A("(floor f keeps rows whose stop width is at least f x ADR20; cap-not-skip adds the too_wide entries re-run with a one-ADR stop)")
    return "\n".join(out)


def run_report(args) -> int:
    T0 = time.time()
    data = Path(args.data)
    out = Path(args.out) if args.out else data / "out"
    small = Path(args.small_out) if args.small_out else HERE / "out"
    keys, sfx = run_keys(args)
    name = f"{REPORT_NAME}{sfx}"
    src = Path(args.trades) if args.trades else out / f"trades_discovery{sfx}.tsv.gz"
    if not src.exists():
        print(f"report: {src} not found - run `minute` first", file=sys.stderr)
        return 1
    small.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    cand_path = out / f"candidates{sfx}.tsv"
    regime_of = regime_by_date(cand_path)         # D -> apollo_regime, joined at read time (the trades layout carries none)
    if not regime_of:
        print(f"report: {cand_path} not found or empty - every row's regime reads {REGIME_MISSING!r} in the regime table", flush=True)
    df, cuts, counts = load_report_frame(src, regime_of=regime_of)
    print(f"[read {counts['rows']:,} trade rows, kept {len(df):,}: {time.time() - T0:.0f}s]", flush=True)
    if not len(df):
        msg = f"report: {src.name} has no non-retrigger row carrying an arm or a too_wide abstain - nothing to report"
        (small / f"{name}.txt").write_text(msg + "\n")
        print(msg)
        return 0
    rows, too_wide = build_report_rows(df)
    cols = ["key", "cell", "K", "variant", "arm", "slice", "value"] + STAT_COLS
    full = out / f"{name}.tsv"
    write_tsv(full, rows, cols)
    compact = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows
               if r["slice"] == "all" and r["n_filled"]]
    write_tsv(small / f"{name}.tsv", compact, cols)          # the repo-sized copy: 'all' slices, 6 decimals (< 1 MB)
    text = report_text(df, rows, too_wide, cuts, counts, src, keys)
    (small / f"{name}.txt").write_text(text + "\n")
    print(text)
    print(f"WROTE {full} ({len(rows):,} rows), {small / (name + '.tsv')}, {small / (name + '.txt')}; WALL TIME {time.time() - T0:.0f}s")
    rname = f"regime_report{sfx}"                 # the per-regime table: its own files, beside the report, never deciding
    n_reg, reg_text = write_regime_report(df, out / f"{rname}.tsv", small / f"{rname}.txt",
                                          title="#702 DISCOVERY REPORT by regime", src=src.name)
    print(reg_text)
    print(f"WROTE {out / (rname + '.tsv')} ({n_reg:,} rows), {small / (rname + '.txt')}")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# #702 P5 (operator 2026-10-18): the holdout read's PRIMARY = HIS exit with the stalled breakouts cut. The `p5` stage walks it,
# and the rows reported beside it, on the DISCOVERY first breaks (the numbers the registration quotes); the `holdout` stage
# walks the SAME function once on the holdout, behind freeze_check. ONE engine (`evaluate_exits`, narrowed to the `lod` stop
# and `P5_ARMS`), NEW files only (`trades_<split>_p5.tsv.gz`, `p5_report_<split>.{tsv,txt}`): no pinned output and no `exits`
# output moves. Measurement only - nothing here chooses an exit, a stop or a level; the operator's rulings are the registration's.
# ═════════════════════════════════════════════════════════════════════════════════════════════
P5_NAME = "p5"
P5_PRIMARY = cb.P5_PRIMARY_ARM                                 # tl / ORH5 / lod / this arm / spec key = the registered primary triple
P5_ARMS = {P5_PRIMARY: cb.CUT_EXIT_ARMS[cb.P5_PRIMARY_ARM],    # his rule + the stall cut (decides)
           cb.PRIMARY_ARM: cb.ARMS[cb.PRIMARY_ARM],            # the article's arm (the old primary)          - beside
           "c3_p33_t20": cb.HIS_EXIT_ARMS["c3_p33_t20"],       # his rule without the cut                     - beside
           "r2_p33_t20": cb.HIS_EXIT_ARMS["r2_p33_t20"]}       # +2R only, no day-3 partial                   - beside
P5_STOPS = ("lod",)                                            # the stop is the registered one: the low of the day at the fill
P5_LEVEL_FILES = (("", ("tl",)), ("_com_comb", ("com", "comb")))    # (candidates-file suffix, the levels read from it)
P5_LEVELS = tuple(k for _sfx, ks in P5_LEVEL_FILES for k in ks)     # tl first: the primary level; com / comb beside
P5_CELLS = CELL_NAMES                                          # C0..C7 and the three report-only cells
P5_USECOLS = (["K", "retrigger_chain", "year", "month", "phase_qqq_10_20", "arm", "status", "realized_r", "pnl_adr", "acct_pct",
               "sessions_held", "mature", "D", "ticker"] + list(P5_CELLS))
P5_XCHECK_TOL = 1e-9


def p5_cols() -> list:
    return ["key", "cell", "K", "arm", "slice", "value"] + STAT_COLS + ["n_cut", "mean_held"]


def p5_candidates(out: Path, split: str) -> list:
    """The P5 population: the spec key's FIRST breaks of `split` on `tl` (the registered `candidates.tsv`) and on `com` / `comb`
    (`candidates_com_comb.tsv`). Both files are pinned by the freeze (`frozen_files`)."""
    cands: list = []
    for sfx, levels in P5_LEVEL_FILES:
        cands += exits_population(read_candidates(Path(out) / f"candidates{sfx}.tsv", split,
                                                  extra_floats=("tightening_ratio", "base_depth")), levels)
    return cands


def p5_inputs(args, split: str) -> dict:
    data = Path(args.data)
    out = Path(args.out) if args.out else data / "out"
    minutes_dir = Path(args.minutes) if args.minutes else data / "minutes"
    cands = p5_candidates(out, split)
    files = minute_date_files(minutes_dir) if minutes_dir.is_dir() else {}
    if args.limit_dates:
        files = dict(list(files.items())[:args.limit_dates])
    return {"data": data, "out": out, "minutes_dir": minutes_dir, "cands": cands, "files": files,
            "by_date": group_by_date(cands, set(files)),
            "done": load_done_pairs(minutes_dir) if minutes_dir.is_dir() else None}


def p5_walk(inp: dict, workers: int, split: str, say) -> tuple:
    """Walk `P5_ARMS` on the lod stop over every candidate of `inp` -> (trades path, entry tally, rows). The table is written to
    `<name>.partial` and renamed only after every date is walked (the holdout's `.partial` protocol)."""
    t = time.time()
    D = load_daily(inp["data"] / "daily_closes_all.csv.gz")
    _G.update(D=D, by_date=inp["by_date"], files=inp["files"], done=inp["done"], bars_cache={}, horizon=HORIZON,
              exits_kw={"stops": P5_STOPS, "arms": P5_ARMS})
    say(f"[load: {time.time() - t:.0f}s]")
    t = time.time()
    tp = inp["out"] / f"trades_{split}_{P5_NAME}.tsv.gz"
    tpp = partial_path(tp)
    tally: Counter = Counter()
    n_rows = 0
    dates = list(inp["by_date"])
    try:
        with open(tpp, "wb") as tf:
            tf.write(rows_to_gz([EXITS_COLS]))
            for k, (tg, ty, nr) in enumerate(_pool_map(_exits_job, dates, workers), 1):
                tf.write(tg)
                tally.update(ty)
                n_rows += nr
                if k % 100 == 0 or k == len(dates):
                    print(f"  {k}/{len(dates)} dates, {n_rows:,} rows", flush=True)
    finally:
        _G["exits_kw"] = {}
    os.replace(tpp, tp)
    say(f"[entries + P5 walks: {time.time() - t:.0f}s]")
    return tp, tally, n_rows


def p5_crosscheck(p5_trades: Path, ref_trades: Path, levels) -> tuple:
    """(rows compared, problems): the registered arm `p33_s3_t10` inside the P5 table against the SAME arm's orh5 spec-key rows
    of the minute stage's table (`ref_trades`), per (ticker, D, K) on `levels`: every pair present on both sides, and
    status / mature / realized_r equal. Proves the P5 walk is the registered walk (same fill, stop, day 0, exit) before its
    other arms are read. A missing reference is reported, not skipped silently."""
    import pandas as pd
    if not Path(ref_trades).exists():
        return 0, [f"reference table {ref_trades} not found"]
    lv = set(levels)
    mine = pd.read_csv(p5_trades, sep="\t", usecols=["ticker", "D", "K", "arm", "status", "realized_r", "mature"],
                       keep_default_na=False, na_values=[""], low_memory=False)
    mine = mine[(mine["arm"] == cb.PRIMARY_ARM) & mine["K"].isin(lv)]
    parts = []
    for ch in pd.read_csv(ref_trades, sep="\t", usecols=["ticker", "D", "K", "variant", "arm", "retrigger", "status", "realized_r", "mature"],
                          chunksize=500_000, keep_default_na=False, na_values=[""], low_memory=False):
        ch = ch[(ch["variant"] == HEADLINE_VARIANT) & (ch["arm"] == cb.PRIMARY_ARM) & (ch["retrigger"] == 0) & ch["K"].isin(lv)]
        parts.append(ch.drop(columns=["variant", "arm", "retrigger"]))
    ref = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["ticker", "D", "K", "status", "realized_r", "mature"])
    j = mine.merge(ref, on=["ticker", "D", "K"], how="outer", suffixes=("", "_ref"), indicator=True)
    problems = []
    for side, label in (("left_only", "P5 table only"), ("right_only", "reference table only")):
        n = int((j["_merge"] == side).sum())
        if n:
            problems.append(f"{n:,} (ticker, D, K) rows are in the {label}")
    both = j[j["_merge"] == "both"]
    if len(both):
        bad_s = int((both["status"] != both["status_ref"]).sum())
        bad_m = int((both["mature"] != both["mature_ref"]).sum())
        bad_r = int(((both["realized_r"] - both["realized_r_ref"]).abs() > P5_XCHECK_TOL).sum())
        for n, what in ((bad_s, "status"), (bad_m, "mature"), (bad_r, "realized_r")):
            if n:
                problems.append(f"{n:,} of {len(both):,} paired rows differ in {what}")
    return int(len(both)), problems


def p5_regime_map(out: Path) -> dict:
    """{D: Apollo regime label} from both candidates files (one value per date; blank -> 'missing')."""
    m: dict = {}
    for sfx, _levels in P5_LEVEL_FILES:
        for d, lab in regime_by_date(Path(out) / f"candidates{sfx}.tsv").items():
            m.setdefault(d, lab)
    return m


def load_p5_frame(path: Path, regime_of: dict):
    """The P5 table as a DataFrame (every row is a spec-key first break already; an abstain row carries no arm and is dropped)."""
    import pandas as pd
    df = pd.read_csv(path, sep="\t", usecols=P5_USECOLS, keep_default_na=False, na_values=[""], low_memory=False)
    df = df[df["arm"].notna()].copy()
    df["regime"] = df["D"].map(regime_of).fillna(REGIME_MISSING)
    for col in ("K", "arm", "month", "regime"):
        df[col] = df[col].astype("category")
    return df


def _p5_row(g, key_name: str, cell: str, k, a, slice_name: str, value, *, ci: bool) -> dict:
    """One P5 report row. `_group_row` seeds the bootstrap from (key, cell, K, variant, arm) with variant = the headline entry,
    exactly as the discovery report and the exits report do - so the registered arm's interval equals the pinned report's."""
    row = _group_row(g, key_name, cell, k, HEADLINE_VARIANT, a, slice_name, value, ci=ci)
    row.pop("variant", None)
    gm = g[g["mature"] == 1]
    row["n_cut"] = int((gm["status"] == "time_exit").sum())        # a time_exit on these arms is the stall cut, nothing else
    row["mean_held"] = float(gm["sessions_held"].mean()) if len(gm) else None
    return row


def build_p5_rows(df) -> list:
    """Every (key, cell, K, arm) of `P5_CELLS` x `P5_LEVELS` x `P5_ARMS` over the MATURE walks: 'all' with the month-block
    interval under the SPEC key and the CHAIN key (the chain population is a subset), and under the spec key the slices the
    registration asks for: year, QQQ 10/20 phase (on the mature walks, as the discovery report slices), and Apollo's regime at D
    ('ALL' plus one row per label; n_open counted, as the regime table does)."""
    rows: list = []
    reg = df["regime"].astype(str)
    labels = list(REGIME_ORDER) + [REGIME_MISSING] + sorted(set(reg.unique()) - set(REGIME_ORDER) - {REGIME_MISSING})
    for key_name, col, _label in REPORT_KEYS:
        kdf = df if col == "retrigger" else df[df["retrigger_chain"] == 0]
        for k in P5_LEVELS:
            for cell in P5_CELLS:
                sub = kdf[(kdf["K"] == k) & (kdf[cell] == 1)]
                for a in P5_ARMS:
                    g = sub[sub["arm"] == a]
                    if not len(g):
                        continue
                    rows.append(_p5_row(g, key_name, cell, k, a, "all", "", ci=True))
                    if key_name != "spec":
                        continue
                    gm = g[g["mature"] == 1]
                    for sname, scol in (("year", "year"), ("phase", "phase_qqq_10_20")):
                        for val, gg in gm.groupby(scol, observed=True):
                            rows.append(_p5_row(gg, key_name, cell, k, a, sname, val, ci=False))
                    rows.append(_p5_row(g, key_name, cell, k, a, "regime", "ALL", ci=False))
                    rg = g["regime"].astype(str).to_numpy()
                    for lab in labels:
                        rows.append(_p5_row(g[rg == lab], key_name, cell, k, a, "regime", lab, ci=False))
    return rows


P5_TWIN = "c3_p33_t20"                                         # the primary arm without the cut
P5_CUT_CELLS = ("C0", "C1", "C3", "C5")


def p5_cut_effect(df) -> list:
    """The cut's own effect per level x cell: the primary arm against its uncut twin (`P5_TWIN`) on the SAME trades (both walks
    mature, paired on (ticker, D)): how many the cut sold at the session-3 close, and - on all the trades and on the cut ones -
    the mean R and the mean sessions held under each. The twin differs from the primary only where the cut fires (tested), so
    this is the cost / gain of cutting and the capital-days freed, nothing else."""
    out: list = []
    a_all, b_all = df[df["arm"] == P5_PRIMARY], df[df["arm"] == P5_TWIN]
    for k in P5_LEVELS:
        for cell in P5_CUT_CELLS:
            x = a_all[(a_all["K"] == k) & (a_all[cell] == 1) & (a_all["mature"] == 1)][["ticker", "D", "status", "realized_r", "sessions_held"]]
            y = b_all[(b_all["K"] == k) & (b_all[cell] == 1) & (b_all["mature"] == 1)][["ticker", "D", "realized_r", "sessions_held"]]
            m = x.merge(y, on=["ticker", "D"], suffixes=("_cut", "_twin"))
            if not len(m):
                continue
            c = m[m["status"] == "time_exit"]
            out.append({"K": k, "cell": cell, "n": len(m), "n_cut": len(c),
                        "r_cut": float(m["realized_r_cut"].mean()), "r_twin": float(m["realized_r_twin"].mean()),
                        "held_cut": float(m["sessions_held_cut"].mean()), "held_twin": float(m["sessions_held_twin"].mean()),
                        "cut_r_cut": float(c["realized_r_cut"].mean()) if len(c) else None,
                        "cut_r_twin": float(c["realized_r_twin"].mean()) if len(c) else None,
                        "cut_held_cut": float(c["sessions_held_cut"].mean()) if len(c) else None,
                        "cut_held_twin": float(c["sessions_held_twin"].mean()) if len(c) else None})
    return out


def _p5_line(r: dict, first) -> list:
    return [first, r["n"], r["n_open"], _num(r.get("mean_r")), _ci(r), _pct(r.get("share_ge5")), _pct(r.get("share_ge10")),
            _num(r.get("mean_ex_top5")), _num(r.get("mean_pnl_adr")), _pct(r.get("win_rate")), r.get("n_cut", 0),
            "" if r.get("mean_held") is None else f"{r['mean_held']:.1f}"]


P5_HEADER = ["", "n", "open", "mean R", "95% CI", ">=5R", ">=10R", "ex-top5", "pnl_adr", "win", "cut", "held"]


def p5_report_text(rows: list, split: str, src: Path, n_rows: int, cut_effect: "list | None" = None) -> str:
    idx = {(r["key"], r["cell"], r["K"], r["arm"], r["slice"], r["value"]): r for r in rows}
    out: list = []
    A = out.append
    window = ("D 2022-03-28 .. 2024-12-31, DISCOVERY" if split == "discovery" else "D 2025-01-01 .. 2026-10-15, the HOLDOUT, read ONCE")
    A(f"#702 P5 - the holdout read's PRIMARY (his exit with the stalled breakouts cut: {P5_PRIMARY}) and the rows reported beside it - "
      f"{window}. Measurement only: nothing here chooses a level, an entry, a stop or an exit.")
    A(f"source: {src.name}; rows read {n_rows:,}. POPULATION: the spec key's first breaks filled at {HEADLINE_VARIANT} under the registered stop "
      f"(the low of the day at the fill, no wider than one ADR20), on tl / com / comb. A group is the MATURE walks only (n_open counted, "
      f"never in a number); month-block bootstrap ({BOOT_DRAWS:,} draws, seed {BOOT_SEED}) 95% interval on the mean R; ADR = mean P&L in "
      f"ADR20 x price units.")
    A(f"ARMS: {P5_PRIMARY} = sell 1/3 at +2R or at the close of session 3, whichever first; stop to breakeven; trail the rest to the first "
      f"close under the 20-day average (filled at the next open); AND if the trade has not reached +{cb.STALL_CUT_R:g}R by the close of "
      f"session {cb.STALL_CUT_SESSION} (and was not stopped) everything is sold at that close ('cut'; 'held' = mean sessions held). "
      f"Beside: {cb.PRIMARY_ARM} (the article: 1/3 at the close of session 3, 10-day trail), c3_p33_t20 (the same without the cut), "
      f"r2_p33_t20 (+2R only, 20-day trail).")
    A("")
    A("FILLED ENTRIES per level x cell (the primary arm's n_filled = fills with a walk; the registration's STEP 0 counts for the holdout)")
    body = []
    for k in P5_LEVELS:
        ln = [k]
        for cell in P5_CELLS:
            r = idx.get(("spec", cell, k, P5_PRIMARY, "all", ""))
            ln.append(f"{r['n_filled']:,}" if r else "0")
        body.append(ln)
    A(table(body, ["K"] + list(P5_CELLS)))
    A("")
    for a in P5_ARMS:
        head = "PRIMARY" if a == P5_PRIMARY else "BESIDE"
        for k in P5_LEVELS:
            body = [_p5_line(r, cell) for cell in P5_CELLS for r in [idx.get(("spec", cell, k, a, "all", ""))] if r]
            if body:
                A(f"{head} - arm {a}, level {k}, SPEC key (cell rows; every row is its own population)")
                A(table(body, ["cell"] + P5_HEADER[1:]))
                A("")
    if cut_effect:
        A(f"THE CUT'S OWN EFFECT - {P5_PRIMARY} against its uncut twin {P5_TWIN} on the SAME mature trades (spec key). 'cut' = trades sold in full at the "
          f"close of session {cb.STALL_CUT_SESSION}; R = mean R; held = mean sessions held; the twin differs from the primary only where the cut fires")

        def _f(x, nd=2, sign=True):
            return "" if x is None else (f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}")
        body = [[f"{r['K']} {r['cell']}", r["n"], r["n_cut"], f"{_f(r['r_cut'], 3)} / {_f(r['r_twin'], 3)}",
                 f"{_f(r['held_cut'], 1, False)} / {_f(r['held_twin'], 1, False)}",
                 f"{_f(r['cut_r_cut'], 3)} / {_f(r['cut_r_twin'], 3)}", f"{_f(r['cut_held_cut'], 1, False)} / {_f(r['cut_held_twin'], 1, False)}"]
                for r in cut_effect]
        A(table(body, ["level cell", "n", "cut", "all: R cut / twin", "all: held cut / twin", "cut trades: R cut / twin", "cut trades: held cut / twin"]))
        A("")
    A(f"CHAIN KEY (poles <= 3 sessions apart = one base; a subset of the spec key), arm {P5_PRIMARY}")
    for k in P5_LEVELS:
        body = [_p5_line(r, cell) for cell in P5_CELLS for r in [idx.get(("chain", cell, k, P5_PRIMARY, "all", ""))] if r]
        if body:
            A(f"  level {k}")
            A(table(body, ["cell"] + P5_HEADER[1:]))
    A("")
    A(f"SLICES - arm {P5_PRIMARY}, spec key; each cell is n / mean R / share >= 5R over the MATURE walks (regime: all walks, "
      f"'missing' = a D with no Apollo label - the label starts 2025-03-03); `0` = none")
    for sname in ("year", "phase", "regime"):
        for k in P5_LEVELS:
            vals = list(dict.fromkeys(r["value"] for r in rows if r["slice"] == sname and r["K"] == k and r["arm"] == P5_PRIMARY))
            if not vals:
                continue
            body = []
            for cell in P5_CELLS:
                ln = [cell]
                for v in vals:
                    r = idx.get(("spec", cell, k, P5_PRIMARY, sname, v))
                    ln.append("-" if r is None else ("0" if not r["n"] else f"{r['n']}/{_num(r.get('mean_r'), 2)}/{_pct(r.get('share_ge5'))}"))
                body.append(ln)
            A(f"  {sname} / level {k}")
            A(table(body, ["cell"] + [str(v) for v in vals]))
    return "\n".join(out)


def p5_regime_rows(df) -> list:
    """The P5 arms x levels the holdout's `regime_report_holdout` does not already carry (that table holds the minute stage's
    `p33_s3_t10` on the registered levels), in its own layout: key spec, `ALL` + one row per regime label."""
    rows: list = []
    reg = df["regime"].astype(str)
    labels = list(REGIME_ORDER) + [REGIME_MISSING] + sorted(set(reg.unique()) - set(REGIME_ORDER) - {REGIME_MISSING})
    for k in P5_LEVELS:
        for cell in P5_CELLS:
            sub = df[(df["K"] == k) & (df[cell] == 1)]
            for a in P5_ARMS:
                if k in KS and a == cb.PRIMARY_ARM:
                    continue
                g = sub[sub["arm"] == a]
                if not len(g):
                    continue
                rows.append(_group_row(g, "spec", cell, k, HEADLINE_VARIANT, a, "regime", "ALL", ci=False))
                rg = g["regime"].astype(str).to_numpy()
                for lab in labels:
                    rows.append(_group_row(g[rg == lab], "spec", cell, k, HEADLINE_VARIANT, a, "regime", lab, ci=False))
    return rows


def p5_regime_text(rows: list) -> str:
    out = [f"#702 P5 - the rows beside the minute stage's table: arms {', '.join(P5_ARMS)} on {'/'.join(P5_LEVELS)} (entry {HEADLINE_VARIANT}, "
           f"lod stop, spec key; the minute stage's own p33_s3_t10 rows on the registered levels are above), split by Apollo's daily regime at D. "
           f"Reported BESIDE, never deciding; the non-Bull groups are small. A cell is n / mean R / share >= 5R."]
    labels = list(dict.fromkeys(r["value"] for r in rows))
    idx = {(r["cell"], r["K"], r["arm"], r["value"]): r for r in rows}
    order = list(dict.fromkeys((r["cell"], r["K"], r["arm"]) for r in rows))
    body = []
    for cell, k, a in order:
        ln = [cell, k, a]
        for lab in labels:
            r = idx.get((cell, k, a, lab))
            ln.append("-" if r is None else ("0" if not r["n"] else f"{r['n']}/{_num(r.get('mean_r'), 2)}/{_pct(r.get('share_ge5'))}"))
        body.append(ln)
    out.append(table(body, ["cell", "K", "arm"] + labels) if body else "  (no mature walk)")
    return "\n".join(out)


def append_regime_report(df, out_tsv: Path, out_txt: Path) -> int:
    """Append the P5 regime rows to `regime_report_holdout.{tsv,txt}` (the minute stage wrote the file first, in the same run;
    a missing file is created with its header)."""
    rows = p5_regime_rows(df) if len(df) else []
    new = not Path(out_tsv).exists()
    with open(out_tsv, "a", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        if new:
            w.writerow(REGIME_COLS)
        for r in rows:
            w.writerow([_fmt(r.get(c)) for c in REGIME_COLS])
    with open(out_txt, "a") as fh:
        fh.write(("\n" if not new else "") + p5_regime_text(rows) + "\n")
    return len(rows)


def run_p5_stage(args, split: str) -> int:
    """`p5` (split='discovery') and the second half of `holdout` (split='holdout', behind freeze_check, after the minute stage):
    walk `P5_ARMS` on the lod stop over the split's first breaks of tl / com / comb -> `trades_<split>_p5.tsv.gz`, prove the
    registered arm inside it equals the minute stage's rows (per trade), and write the report. 0 = ok, 3 = the cross-check failed."""
    T0 = time.time()
    inp = p5_inputs(args, split)
    out, small = inp["out"], (Path(args.small_out) if args.small_out else HERE / "out")
    log: list = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        log.append(msg)

    by_date = inp["by_date"]
    say(f"{split.upper()} P5 STAGE (#702): {len(inp['cands']):,} first-break candidate rows (spec key) on {'/'.join(P5_LEVELS)}; minute files "
        f"on disk: {len(inp['files'])} dates ({inp['minutes_dir']}); candidates on those dates: {sum(len(v) for v in by_date.values()):,}; "
        f"entry {HEADLINE_VARIANT}; stop {'/'.join(P5_STOPS)}; arms {', '.join(P5_ARMS)}")
    if not by_date:
        say("nothing to do: no candidate falls on a date with a minute file (nothing written)")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    tp, tally, n_rows = p5_walk(inp, args.workers, split, say)
    states = {k[1]: n for k, n in tally.items() if k[0] == "minutes_state"}
    say(f"COVERAGE: candidates with minutes fetched {sum(n for s, n in states.items() if s != 'pending'):,} "
        f"(by state {dict(sorted(states.items()))}); PENDING fetch (skipped) {states.get('pending', 0):,}")
    ent = {(k[1], k[2]): n for k, n in tally.items() if k[0] == "entry"}
    say(f"ENTRY ({HEADLINE_VARIANT}, all levels): " + "; ".join(f"{st}{(' ' + r) if r else ''} {n:,}" for (st, r), n in sorted(ent.items())))
    say(f"WROTE {tp} ({n_rows:,} rows)")
    # the registered arm inside this table IS the registered walk: per trade, against the minute stage's own table
    rc = 0
    for sfx, levels in P5_LEVEL_FILES:
        ref = out / (f"trades_{split}{sfx}.tsv.gz")
        if not ref.exists() and split == "holdout":
            say(f"CROSS-CHECK {'/'.join(levels)}: no minute-stage table for these levels on the holdout ({ref.name}) - not applicable")
            continue
        n_cmp, problems = p5_crosscheck(tp, ref, levels)
        if problems:
            rc = 3
            say(f"CROSS-CHECK {'/'.join(levels)} FAILED against {ref.name}: " + "; ".join(problems))
        else:
            say(f"CROSS-CHECK {'/'.join(levels)}: {n_cmp:,} paired {cb.PRIMARY_ARM} rows equal {ref.name}'s {HEADLINE_VARIANT} rows "
                f"(status, maturity, realized R to {P5_XCHECK_TOL:g})")
    if rc and split == "discovery":
        say("the P5 walk is not the registered walk: the report is NOT written")
        (small / f"p5_summary_{split}.txt").write_text("\n".join(log) + "\n")
        return rc
    df = load_p5_frame(tp, p5_regime_map(out))
    rows = build_p5_rows(df)
    cols = p5_cols()
    name = f"p5_report_{split}"
    write_tsv(out / f"{name}.tsv", rows, cols)
    compact = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows if r["slice"] == "all"]
    write_tsv(small / f"{name}.tsv", compact, cols)               # the repo-sized copy: 'all' slices, 6 decimals
    text = p5_report_text(rows, split, tp, n_rows, p5_cut_effect(df))
    (small / f"{name}.txt").write_text(text + "\n")
    print(text)
    say(f"WROTE {out / (name + '.tsv')} ({len(rows):,} rows), {small / (name + '.tsv')}, {small / (name + '.txt')}")
    if split == "holdout":
        n_reg = append_regime_report(df, out / "regime_report_holdout.tsv", small / "regime_report_holdout.txt")
        say(f"APPENDED {n_reg:,} P5 rows to {out / 'regime_report_holdout.tsv'} and {small / 'regime_report_holdout.txt'}")
    say(f"WALL TIME: {time.time() - T0:.0f}s total")
    (small / f"p5_summary_{split}.txt").write_text("\n".join(log) + "\n")
    return rc


# ═════════════════════════════════════════════════════════════════════════════════════════════
# #702 pre-read (operator 2026-10-19: "during the period 2020-2021 qullamaggie 10x his portfolio"): the FROZEN primary - level tl, ORH5,
# the low-of-day stop, `c3_p33_t20_cut3`, spec key, first break per base - read on the pre-2022 Alpaca era (D 2017-03-01 .. 2021-12-31),
# registered in docs/analysis/cb_2017_21_read_prereg_2026-10-19.md BEFORE any outcome. The holdout's own chain, once, on the era's
# first breaks of tl (decides) and com (beside): the registered minute engine (`run_minute_stage`, split 'pre'), the P5 walk
# (`p5_walk`), the registered arm's per-trade cross-check against the minute stage, then the §5 verdict per cell for the whole era and
# for 2020-21 alone. BUILT, NOT RUN: it refuses while ONE candidate pair is missing from `_done.psv` (no partial read).
# ═════════════════════════════════════════════════════════════════════════════════════════════
PRE_ERA = "pre"                                                # the daily stage's `--era-label` on cb702_pre/out/candidates_tl_com.tsv
PRE_KEYS = ("tl", "com")                                       # tl = the registered level (decides); com beside
PRE_FIRST, PRE_LAST = date(2017, 3, 1), date(2021, 12, 31)     # the era's watch nights D (selection_pre.WATCH_FIRST / WATCH_LAST)
PRE_LEVEL = PRE_KEYS[0]
PRE_MIN_N = 30                                                 # §5.2: n < 30 mature trades is CAN'T TELL whatever the interval says
PRE_DECIDING = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")      # C1 decides; C0 is the baseline (cannot pass); the rest are report cells
PRE_CELL_ORDER = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C0", "C1_no_retrace", "C1_no_tightening", "HTF")     # C1 first
PRE_WINDOWS = (("era", "the whole era (D 2017-03-01 .. 2021-12-31)", None),
               ("2020-21", "2020-21 alone (breakout day E in 2020 or 2021: his 10x years)", (2020, 2021)))
PRE_REPORT = "p5_report_pre"


def pre_cols() -> list:
    return ["window"] + p5_cols() + ["verdict", "why"]


def pre_first_breaks(rec: dict) -> bool:
    """Raw-row filter of the pre-read: the spec key's first break on the pre-read's levels (what `exits_population` keeps)."""
    return rec["K"] in PRE_KEYS and int(rec.get("retrigger") or 0) == 0


def pre_missing_pairs(pairs: list, on_disk: dict, done: "dict | None") -> tuple:
    """(missing, lost) over the population's (date, ticker) pairs: those `_done.psv` does not log as fetched (every one when the
    log is absent), and those it logs `ok` on a date that has no minute file (their rows are gone). Either makes the read partial."""
    log = done or {}
    missing = [p for p in pairs if p not in log]
    lost = [p for p in pairs if p in log and log[p] != "empty" and p[0] not in on_disk]
    return missing, lost


def pre_inputs(args) -> dict:
    """The pre-read's population and what the minute directory holds of it: the era file's first breaks of tl / com (the label is
    checked on every row, and every D must lie in the era), the pairs they need, and the pairs missing (see `pre_missing_pairs`).
    Opens no daily bar and no minute row."""
    data = Path(args.data)
    out = Path(args.out) if args.out else data / "out"
    minutes_dir = Path(args.minutes) if args.minutes else data / "minutes"
    path = out / f"candidates{out_suffix(PRE_KEYS)}.tsv"
    cands = exits_population(read_candidates(path, era=PRE_ERA, extra_floats=("tightening_ratio", "base_depth"),
                                             where=pre_first_breaks), PRE_KEYS)
    outside = [c for c in cands if not PRE_FIRST <= date.fromisoformat(c["D"]) <= PRE_LAST]
    if outside:
        raise ValueError(f"{path}: {len(outside):,} rows have a watch night D outside {PRE_FIRST}..{PRE_LAST} "
                         f"(first: {outside[0]['ticker']} D={outside[0]['D']}): this is not the pre-read's file")
    has_dir = minutes_dir.is_dir()
    on_disk = minute_date_files(minutes_dir) if has_dir else {}
    done = load_done_pairs(minutes_dir) if has_dir else None
    pairs = sorted({(c["E"], c["ticker"]) for c in cands})
    missing, lost = pre_missing_pairs(pairs, on_disk, done)
    return {"data": data, "out": out, "minutes_dir": minutes_dir, "cands": cands, "pairs": pairs, "on_disk": on_disk, "done": done,
            "missing": missing, "lost": lost, "path": path}


def pre_complete(inp: dict) -> dict:
    """The complete inputs the minute and P5 stages take (`_setup_minute_inputs`' shape), once nothing is missing. A date with no minute
    file is one whose every pair is logged `empty` (the fetcher writes no file for it): it is read as no minutes, never dropped."""
    files = dict(inp["on_disk"])
    for d in {e for e, _t in inp["pairs"]} - set(files):
        files[d] = Path(os.devnull)
    by_date = group_by_date(inp["cands"], set(files))
    assert sum(len(v) for v in by_date.values()) == len(inp["cands"])
    return {**inp, "files": files, "by_date": by_date}


def pre_existing_outputs(out: Path) -> list:
    """Pre-read outputs already on disk: the final tables, or the `.partial` a crashed run left behind."""
    sfx = out_suffix(PRE_KEYS)
    return [q for name in (f"trades_{PRE_ERA}{sfx}.tsv.gz", f"entries_{PRE_ERA}{sfx}.tsv.gz", f"trades_{PRE_ERA}_{P5_NAME}.tsv.gz")
            for q in (Path(out) / name, partial_path(Path(out) / name)) if q.exists()]


def pre_option_problems(args) -> list:
    """Options the one pre-read may not carry: it runs in its registered form (the registered minute engine in full, both levels)."""
    bad = []
    for flag, val in (("--keys", getattr(args, "keys", None)), ("--levels", getattr(args, "levels", None)),
                      ("--limit-dates", getattr(args, "limit_dates", 0)), ("--no-close", getattr(args, "no_close", False)),
                      ("--no-apollo", getattr(args, "no_apollo", False))):
        if val:
            bad.append(f"{flag}: the pre-read reads {'/'.join(PRE_KEYS)} from candidates{out_suffix(PRE_KEYS)}.tsv in full; a partial or "
                       f"altered run would also consume the one run")
    return bad


def _num_ok(x) -> bool:
    return x is not None and x == x


def cell_verdict(row: dict, base: "dict | None", min_n: int = PRE_MIN_N) -> tuple:
    """(verdict, why) of one deciding cell on the §5 bars of cb_preregistration_2026-10-18.md, word for word, with the precedence of
    §5.3 (n decides first). `row` and `base` are P5 report rows (spec key, slice all) of the cell and of C0 on the SAME level, arm and
    window. PASS = n >= 30 mature AND the month-block interval's lower end > 0 AND mean R without the top five > 0 AND mean P&L in ADR
    units > 0 AND the cell beats C0 on mean R AND on the >= 5R share. FAIL = n >= 30 AND (the interval's upper end < 0 OR the cell does
    not beat C0 on mean R). Otherwise CAN'T TELL: n < 30, or n >= 30 with the interval spanning zero / a bar not met. The two
    outcomes with n >= 30 cannot both hold (PASS needs lower > 0 and a higher mean than C0)."""
    n = int(row.get("n") or 0)
    if n < min_n:
        return "CAN'T TELL", f"n = {n} < {min_n}"
    if base is None or not _num_ok(base.get("mean_r")):
        return "CAN'T TELL", "no C0 row to compare with"
    mean, lo, hi = row.get("mean_r"), row.get("ci_lo"), row.get("ci_hi")
    fails = []
    if _num_ok(hi) and hi < 0:
        fails.append("interval upper end < 0")
    if not (_num_ok(mean) and mean > base["mean_r"]):
        fails.append("does not beat C0 on mean R")
    if fails:
        return "FAIL", "; ".join(fails)
    unmet = []
    if not (_num_ok(lo) and lo > 0):
        unmet.append("interval spans 0")
    if not (_num_ok(row.get("mean_ex_top5")) and row["mean_ex_top5"] > 0):
        unmet.append("mean without the top 5 <= 0")
    if not (_num_ok(row.get("mean_pnl_adr")) and row["mean_pnl_adr"] > 0):
        unmet.append("ADR P&L <= 0")
    if not (_num_ok(row.get("share_ge5")) and _num_ok(base.get("share_ge5")) and row["share_ge5"] > base["share_ge5"]):
        unmet.append("does not beat C0's >= 5R share")
    return ("CAN'T TELL", "; ".join(unmet)) if unmet else ("PASS", "all five bars met")


def stamp_pre_verdicts(rows: list) -> None:
    """Fill `verdict` / `why` on every row: the §5 verdict on the registered primary only (level tl, arm `P5_PRIMARY`, spec key, slice all)
    for C1..C7 against C0 of the same window; C0 = baseline, the report cells = report; every other row (com, the other arms, the chain
    key, the slices) carries none - reading one as a finding is excluded by §P5.3 / §8."""
    idx = {(r["window"], r["key"], r["cell"], r["K"], r["arm"], r["slice"], r["value"]): r for r in rows}
    for r in rows:
        r["verdict"], r["why"] = "", ""
        if not (r["key"] == "spec" and r["slice"] == "all" and r["K"] == PRE_LEVEL and r["arm"] == P5_PRIMARY):
            continue
        if r["cell"] == "C0":
            r["verdict"] = "baseline"
        elif r["cell"] in PRE_DECIDING:
            r["verdict"], r["why"] = cell_verdict(r, idx.get((r["window"], "spec", "C0", PRE_LEVEL, P5_PRIMARY, "all", "")))
        else:
            r["verdict"] = "report"


def build_pre_rows(df) -> list:
    """The P5 rows (`build_p5_rows`) of each window - the whole era, then 2020-21 alone (E in 2020 / 2021) - with the verdicts stamped. The
    Apollo-regime slice is dropped: its label starts 2025-03-03, so every pre-era night reads 'missing'."""
    rows: list = []
    for name, _label, years in PRE_WINDOWS:
        sub = df if years is None else df[df["year"].isin(years)]
        if not len(sub):
            continue
        rows += [{"window": name, **r} for r in build_p5_rows(sub) if r["slice"] != "regime"]
    stamp_pre_verdicts(rows)
    return rows


def pre_report_text(rows: list, src: Path, n_rows: int, notes: list) -> str:
    idx = {(r["window"], r["key"], r["cell"], r["K"], r["arm"], r["slice"], r["value"]): r for r in rows}
    out: list = []
    A = out.append
    A(f"#702 PRE-READ - the frozen primary ({PRE_LEVEL} / {HEADLINE_VARIANT} / the low-of-day stop / {P5_PRIMARY} / spec key, first break per base) read on "
      f"D 2017-03-01 .. 2021-12-31, the years he 10x'd, and on 2020-21 alone. Registered before any outcome: docs/analysis/cb_2017_21_read_prereg_2026-10-19.md. "
      f"Measurement only: nothing here chooses a level, an entry, a stop or an exit.")
    A(f"source: {src.name}; rows read {n_rows:,}. POPULATION: the era's spec-key first breaks filled at {HEADLINE_VARIANT} under the registered stop on "
      f"{'/'.join(PRE_KEYS)}; a group is the MATURE walks only (n_open counted, never in a number); month-block bootstrap ({BOOT_DRAWS:,} draws, seed {BOOT_SEED}) "
      f"95% interval on the mean R; ADR = mean P&L in ADR20 x price units; years are the calendar year of the breakout day E.")
    A(f"BARS (§5 of cb_preregistration_2026-10-18.md, word for word): PASS = n >= {PRE_MIN_N} mature AND interval lower end > 0 AND mean R without the top 5 > 0 AND "
      f"ADR P&L > 0 AND beats C0 on mean R and on the >= 5R share; FAIL = n >= {PRE_MIN_N} AND (interval upper end < 0 OR does not beat C0 on mean R); else CAN'T TELL "
      f"(n decides first). C1 decides; C0 is the baseline and cannot pass; com, the other arms, the chain key and the report cells are never a verdict.")
    A("NOT ANSWERED: Alpaca's symbol list omits many delisted names (survivorship), so a PASS is weaker than it looks and a FAIL is not explained by it; "
      "his discretion (what he chose, his sizing, adds) is not modelled; an edge that lives in one exceptional bull market is a regime bet.")
    for n_ in notes:
        A(n_)
    A("")
    for wname, wlabel, _years in PRE_WINDOWS:
        body = []
        for cell in PRE_CELL_ORDER:
            r = idx.get((wname, "spec", cell, PRE_LEVEL, P5_PRIMARY, "all", ""))
            if r:
                body.append([cell, f"{r['n_filled']:,}", r["n"], r["n_open"], _num(r.get("mean_r")), _ci(r), _pct(r.get("share_ge5")),
                             _pct(r.get("share_ge10")), _num(r.get("mean_ex_top5")), _num(r.get("mean_pnl_adr")), _pct(r.get("win_rate")),
                             r["verdict"], r["why"]])
            elif cell in PRE_DECIDING:                      # a deciding cell with no walk in this window is shown, not left out
                body.append([cell, "0", 0, 0, "", "", "", "", "", "", "", *cell_verdict({"n": 0}, None)])
        A(f"VERDICT - {wlabel}; level {PRE_LEVEL}, arm {P5_PRIMARY}, SPEC key (C1 decides; every row is its own population)")
        A(table(body, ["cell", "fills", "n", "open", "mean R", "95% CI", ">=5R", ">=10R", "ex-top5", "pnl_adr", "win", "VERDICT", "why"]))
        A("")
    for wname, wlabel, _years in PRE_WINDOWS:
        for k in PRE_KEYS:
            for a in P5_ARMS:
                if k == PRE_LEVEL and a == P5_PRIMARY:
                    continue
                body = [_p5_line(r, cell) for cell in PRE_CELL_ORDER for r in [idx.get((wname, "spec", cell, k, a, "all", ""))] if r]
                if body:
                    A(f"BESIDE (never a verdict) - {wlabel}; arm {a}, level {k}, SPEC key")
                    A(table(body, ["cell"] + P5_HEADER[1:]))
                    A("")
    A(f"SLICES - arm {P5_PRIMARY}, spec key; each cell is n / mean R / share >= 5R over the MATURE walks; `0` = none")
    for sname in ("year", "phase"):
        for wname, wlabel, _years in PRE_WINDOWS:
            if sname == "year" and wname != "era":
                continue
            for k in PRE_KEYS:
                vals = sorted({r["value"] for r in rows if r["window"] == wname and r["slice"] == sname and r["K"] == k and r["arm"] == P5_PRIMARY},
                              key=str)
                if not vals:
                    continue
                body = []
                for cell in PRE_CELL_ORDER:
                    ln = [cell]
                    for v in vals:
                        r = idx.get((wname, "spec", cell, k, P5_PRIMARY, sname, v))
                        ln.append("-" if r is None else ("0" if not r["n"] else f"{r['n']}/{_num(r.get('mean_r'), 2)}/{_pct(r.get('share_ge5'))}"))
                    body.append(ln)
                A(f"  {sname} / {wlabel} / level {k}" + (" (phase 1 = the QQQ 10/20 rule on)" if sname == "phase" else ""))
                A(table(body, ["cell"] + [str(v) for v in vals]))
    return "\n".join(out)


def run_pre_read(args) -> int:
    """`pre-read` - BUILT, NOT RUN. exit 2 on: an option that alters the registered form, any pair of the population missing from
    `_done.psv` (the count is printed; no partial read), outputs (or a crashed run's `.partial`) that already exist; exit 3 when the
    registered arm inside the P5 table differs from the minute stage's rows. `--dry-run` counts candidate rows and pairs only."""
    T0 = time.time()
    bad = pre_option_problems(args)
    if bad:
        print("REFUSED: the pre-read runs only in its registered form:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 2
    inp = pre_inputs(args)
    out, minutes_dir = inp["out"], inp["minutes_dir"]
    small = Path(args.small_out) if args.small_out else HERE / "out"
    pairs, missing, lost = inp["pairs"], inp["missing"], inp["lost"]
    existing = pre_existing_outputs(out)
    by_k = Counter(c["K"] for c in inp["cands"])
    dates = sorted({e for e, _t in pairs})
    state = ("ABSENT" if not minutes_dir.is_dir() else
             f"{len(inp['on_disk'])} date files, _done.psv " + (f"logs {len(inp['done']):,} pairs" if inp["done"] is not None else "ABSENT"))
    if args.dry_run:
        print(f"PRE-READ DRY RUN (counts only: no daily bar, minute row or outcome was opened): read {inp['path']}: "
              f"{len(inp['cands']):,} first-break rows ({', '.join(f'{k} {by_k[k]:,}' for k in PRE_KEYS)}) needing {len(pairs):,} (date, ticker) "
              f"pairs on {len(dates):,} breakout dates ({dates[0] if dates else '-'} .. {dates[-1] if dates else '-'}); minute directory "
              f"{minutes_dir}: {state}; pairs NOT logged in _done.psv: {len(missing):,}, logged ok on a date with no file: {len(lost):,} -> "
              f"{'the run would REFUSE (no partial read)' if (missing or lost) else 'complete'}; outputs already on disk: "
              f"{[q.name for q in existing] or 'none'}{' -> the run would REFUSE (read once)' if existing else ''}. Would write "
              f"{out / f'trades_{PRE_ERA}{out_suffix(PRE_KEYS)}.tsv.gz'} (the minute stage), {out / f'trades_{PRE_ERA}_{P5_NAME}.tsv.gz'}, "
              f"{out / (PRE_REPORT + '.tsv')} and {small / (PRE_REPORT + '.tsv')}, {small / (PRE_REPORT + '.txt')}.")
        return 0
    if existing:
        crashed = [q for q in existing if q.name.endswith(".partial")]
        if crashed:
            print(f"REFUSED: {crashed[0]} is what a CRASHED pre-read left behind - it holds some outcomes. The pre-read is run ONCE: "
                  f"the operator inspects it and removes it by hand before any re-run", file=sys.stderr)
        else:
            print(f"REFUSED: the pre-read outcomes are joined ONCE and {existing[0]} already exists", file=sys.stderr)
        return 2
    if not inp["cands"]:
        print(f"REFUSED: {inp['path']} holds no first-break row of {'/'.join(PRE_KEYS)}", file=sys.stderr)
        return 2
    if missing or lost:
        print(f"REFUSED: {len(missing):,} of {len(pairs):,} first-break (date, ticker) pairs are not logged in {minutes_dir / '_done.psv'} "
              f"(minute directory: {state})" + (f"; {len(lost):,} more are logged ok on a date that has no minute file" if lost else "") +
              ". A partial read is never run: finish the minute fetch first", file=sys.stderr)
        return 2
    inp = pre_complete(inp)
    out.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    log: list = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        log.append(msg)

    say(f"PRE-READ (#702): {len(inp['cands']):,} first-break rows ({', '.join(f'{k} {by_k[k]:,}' for k in PRE_KEYS)}), {len(pairs):,} pairs, all logged "
        f"in {minutes_dir / '_done.psv'}; code: consolidation_breakout.py sha256 {sha256_file(Path(cb.__file__))}, runner.py sha256 {sha256_file(Path(__file__))}")
    margs = argparse.Namespace(**vars(args))
    margs.keys, margs.no_close, margs.no_apollo, margs.limit_dates = ",".join(PRE_KEYS), False, False, 0
    run_minute_stage(margs, PRE_ERA, inp)                       # the registered minute engine, on the era's first breaks
    tp, tally, n_rows = p5_walk(inp, args.workers, PRE_ERA, say)
    states = {k[1]: n for k, n in tally.items() if k[0] == "minutes_state"}
    say(f"COVERAGE: candidates with minutes fetched {sum(n for s, n in states.items() if s != 'pending'):,} "
        f"(by state {dict(sorted(states.items()))}); PENDING fetch (skipped) {states.get('pending', 0):,}")
    ent = {(k[1], k[2]): n for k, n in tally.items() if k[0] == "entry"}
    say(f"ENTRY ({HEADLINE_VARIANT}, all levels): " + "; ".join(f"{st}{(' ' + r) if r else ''} {n:,}" for (st, r), n in sorted(ent.items())))
    gate = Counter()
    for k, n in tally.items():
        if k[0] == "entry":
            gate[("data_abstain", k[2] if k[2] in DATA_ABSTAINS else "none")] += n
    gate_text = minute_data_gate(gate)[1].replace("DATA GATE", f"DATA GATE ({HEADLINE_VARIANT})")
    say(gate_text)
    say(f"WROTE {tp} ({n_rows:,} rows)")
    ref = out / f"trades_{PRE_ERA}{out_suffix(PRE_KEYS)}.tsv.gz"
    n_cmp, problems = p5_crosscheck(tp, ref, PRE_KEYS)
    rc = 3 if problems else 0
    cross = (f"CROSS-CHECK {'/'.join(PRE_KEYS)} FAILED against {ref.name} - DO NOT READ THE VERDICTS: " + "; ".join(problems) if problems else
             f"CROSS-CHECK {'/'.join(PRE_KEYS)}: {n_cmp:,} paired {cb.PRIMARY_ARM} rows equal {ref.name}'s {HEADLINE_VARIANT} rows "
             f"(status, maturity, realized R to {P5_XCHECK_TOL:g})")
    say(cross)
    df = load_p5_frame(tp, {})
    rows = build_pre_rows(df)
    cols = pre_cols()
    write_tsv(out / f"{PRE_REPORT}.tsv", rows, cols)
    compact = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows if r["slice"] == "all"]
    write_tsv(small / f"{PRE_REPORT}.tsv", compact, cols)         # the repo-sized copy: 'all' slices, 6 decimals
    text = pre_report_text(rows, tp, n_rows, [cross, gate_text])
    (small / f"{PRE_REPORT}.txt").write_text(text + "\n")
    print(text)
    say(f"WROTE {out / (PRE_REPORT + '.tsv')} ({len(rows):,} rows), {small / (PRE_REPORT + '.tsv')}, {small / (PRE_REPORT + '.txt')}")
    say(f"WALL TIME: {time.time() - T0:.0f}s total")
    (small / f"p5_summary_{PRE_ERA}.txt").write_text("\n".join(log) + "\n")
    return rc


# ═════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stage", choices=["daily", "minute", "step0-entries", "holdout", "report", "exits", "exits-report", "p5", "pre-read"],
                    help="daily = P2a daily stage; minute = DISCOVERY entries/exits/controls; step0-entries = HOLDOUT "
                         "composition, no outcome; holdout = the minute engine AND the P5 stage on the HOLDOUT, behind "
                         "freeze_check (BUILT, NOT RUN); report = the DISCOVERY read; exits / exits-report = #702 his exit (the "
                         "+2R / day / combo partial x the trail switches x the stop variants) on the DISCOVERY first breaks, NEW "
                         "files only; p5 = #702 P5: his exit with the stalled breakouts cut (the holdout read's primary) and the "
                         "rows beside it, on the DISCOVERY first breaks of tl / com / comb, NEW files only; pre-read = #702 the "
                         "frozen primary read ONCE on the pre-2022 Alpaca era (candidates_tl_com.tsv, 2017-21; --data cb702_pre): "
                         "the minute engine and the P5 walk on its first breaks, the §5 verdict per cell for the whole era and "
                         "2020-21 alone; refuses while any minute pair is unfetched (BUILT, NOT RUN)")
    ap.add_argument("--data", required=True, help="DATA dir (daily_closes_all.csv.gz, small_pulls.psv, ...)")
    ap.add_argument("--out", help="large-output dir (default DATA/out); holdout refuses anything but DATA/out")
    ap.add_argument("--small-out", help="small-summary dir (default scripts/probes/_cb_backtest/out); holdout refuses it")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--step0", action="store_true", help="daily: print the STEP 0 composition table from candidates.tsv and exit")
    ap.add_argument("--check-prescreen", type=int, default=0, metavar="N",
                    help="daily: exhaustively prove the pre-screen on N tickers (real explain_watch on every night) and exit")
    ap.add_argument("--limit-tickers", type=int, default=0, help="daily, dev: random subset of tickers")
    ap.add_argument("--minutes", help="daily (fetch delta: reads _done.psv) / minute / step0-entries / holdout: the minute-file directory (default DATA/minutes)")
    ap.add_argument("--limit-dates", type=int, default=0, help="minute/step0-entries, dev: only the first N minute dates on disk (holdout refuses it)")
    ap.add_argument("--no-close", action="store_true", help="minute: skip the daily CLOSE variant (holdout refuses it)")
    ap.add_argument("--no-apollo", action="store_true",
                    help="minute: do not walk the 'Apollo as it runs today' control (its frame is an adaptation - see apollo_walk_inputs). "
                         "holdout REFUSES it: the control is on or off in the pinned runner, decided before the freeze")
    ap.add_argument("--trades", help="report: the trades table (default DATA/out/trades_discovery.tsv.gz)")
    ap.add_argument("--dry-run", action="store_true", help="holdout / pre-read: print what would be read (candidate and pair counts only) and exit")
    ap.add_argument("--no-freeze-check", action="store_true", help="holdout: skip the freeze check - ONLY together with --dry-run")
    ap.add_argument("--print-pins", action="store_true", help="holdout: print the footer pin lines for the registration doc and exit")
    ap.add_argument("--prereg", help="holdout: the registration doc (default: the one docs/analysis/cb_preregistration_*.md)")
    ap.add_argument("--keys", help="the breakout levels to run, comma-separated (default: the module's four, k5/k10/full/tl, which "
                                   "write the pinned files). 'com' = the #702 P4b center-of-mass level; 'comb' = com read only on "
                                   "the nights the stock closed at or below it. Every output then carries the suffix _<keys> "
                                   "(_com, _comb, _com_comb) beside the pinned files. holdout REFUSES it")
    ap.add_argument("--no-close-variant", action="store_true",
                    help="daily: skip the CLOSE-variant walk (no outcome of any kind is computed; overlap_open is left blank)")
    ap.add_argument("--watch-start", help="daily: first watch night D, YYYY-MM-DD (default 2022-03-28, the discovery start). With --era-label "
                                          "only: the #702 selection test's Alpaca-era run")
    ap.add_argument("--watch-end", help="daily: last watch night D, YYYY-MM-DD (default: every night to the end of the data). The export "
                                        "keeps its bars past it, so a breakout day E just after it still exists")
    ap.add_argument("--raw-close", help="daily: a headerless `ticker,date,raw_close` file (one row per row of the export); the RAW factor "
                                        "is then measured per bar as raw / adjusted instead of read from cb702_splits.psv (the $5 floor)")
    ap.add_argument("--breaks", help="daily: a symbol_guard.tsv (columns symbol, breaks): a night with an identity break inside its 130 "
                                     "bars is not evaluated and is counted as 'identity_break' (scripts/probes/_qm_streams/ext_bars.py)")
    ap.add_argument("--era-label", help="daily: stamp every row's `split` column with this label (e.g. 'pre') instead of discovery/holdout; "
                                        "read_candidates() then refuses the file, so it cannot feed the discovery or holdout stages")
    ap.add_argument("--levels", help="exits / exits-report: the levels of the run's candidates file to walk, comma-separated "
                                     "(default: every level of the run's keys). `--levels tl` reads the registered candidates.tsv and "
                                     "walks the trendline alone; `--keys com,comb` walks both. holdout REFUSES it")
    args = ap.parse_args(argv)
    era_opts = [o for o in ("watch_start", "watch_end", "raw_close", "breaks", "era_label") if getattr(args, o)]
    if era_opts and args.stage != "daily":
        ap.error(f"--{', --'.join(o.replace('_', '-') for o in era_opts)}: options of the `daily` stage only (the pre-2022 Alpaca-era run)")
    parse_keys(args.keys)                       # a bad --keys fails here, before any stage opens a file
    parse_levels(args.levels, parse_keys(args.keys))
    if args.stage == "exits":
        run_exits(args)
        return
    if args.stage == "exits-report":
        rc = run_exits_report(args)
        if rc:
            sys.exit(rc)
        return
    if args.stage == "p5":
        if args.keys or args.levels:                # the population is fixed by the registration: tl from candidates.tsv, com / comb from candidates_com_comb.tsv
            ap.error("p5: --keys / --levels are not options of this stage (it reads tl from candidates.tsv and com / comb from "
                     "candidates_com_comb.tsv)")
        rc = run_p5_stage(args, "discovery")
        if rc:
            sys.exit(rc)
        return
    if args.stage == "pre-read":
        rc = run_pre_read(args)
        if rc:
            sys.exit(rc)
        return
    if args.stage == "daily":
        if args.step0:
            run_step0(args)
        else:
            run_daily(args)
    elif args.stage == "minute":
        run_minute_stage(args, "discovery")
    elif args.stage == "step0-entries":
        run_step0_entries(args)
    elif args.stage == "holdout":
        rc = run_holdout(args)
        if rc:
            sys.exit(rc)
    else:
        rc = run_report(args)
        if rc:
            sys.exit(rc)


if __name__ == "__main__":
    main()
