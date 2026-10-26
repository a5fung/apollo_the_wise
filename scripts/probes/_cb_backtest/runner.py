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

#702 h60 (operator 2026-10-19; docs/analysis/cb_hourly_entry_prereg_2026-10-19.md): the HOURLY-CLOSE entry - buy only after an intraday bar
CLOSES above the line - `h60-step0 --period P` (the entry-time table: confirmations, fills, abstains, the registered-table check; no exit),
`h60-read --period P` (the one-run read per period behind the freeze check on every pin of both data trees, STEP 0 equal to the registered
table, the ORH5 twin re-walked and equal in content to the pinned P5 table; then the exits, the paired bars, the verdict and the consequence
cell; `--print-pins`, `--dry-run`), `h60-hindsight --period P` (the 39 multibaggers and TSLA, refused until the verdict file exists).
`--data` = cb702, `--data-pre` = cb702_pre (default the sibling). Every other stage is unchanged (`p5_walk` gained `name=`, `freeze_check` /
`pin_lines` gained `files=`; the defaults are the old behaviour). BUILT ON SYNTHETIC DATA; the build computed no real outcome.

#702 exit read (operator 2026-10-19; docs/analysis/cb_exit_partial_prereg_2026-10-19.md): his partial and the stop after it - the day-based
third only in profit (`pp`, his ruling), then the WHOLE-TRADE breakeven stop (`pp_wbe`, his proposal, the test) against the entry-price
stop. `exit-read --period P` walks six arms on a RUNNER-SIDE copy of `walk_exit`'s qm path (`exitpb_walk`, two flags) over the pinned P5
fills (ORH5; decides on tl) and the pinned hourly-close fills (descriptive), read off the pinned tables themselves; before any new-arm
number the copy with every flag off is proved equal to the pinned rows (P1 / P2) and to the module's own walk event for event (exit 3,
nothing written, on a mismatch); then the deciding per-trade delta pp_wbe - pp on C1 (C0 beside), the cell verdict under pp_wbe, the
registration's consequence row, the expectations and the WOULD-FAIL-IF implementation checks. `--print-pins`, `--dry-run`, `--parity-only`
(the control alone, match counts, nothing written). The module is hard-pinned to `EXITPB_MODULE_SHA`. Every other stage is unchanged
(nothing existing was edited). BUILT ON SYNTHETIC DATA; the build computed no real outcome.
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
MODULE_REL = Path("agents/market_intelligence/consolidation_breakout.py")      # the module the registered reads pin, relative to the repo
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
from scripts.probes._cb_backtest import registered_read as rr  # noqa: E402  (#705 (a): the shared registered-read scaffold + speed helpers)

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


def read_tsv(path: Path, **kw):
    """A tab-separated table with no NA guessing (`""` is the one missing value), the way the pre-read, h60 and exit-read stages load a
    pinned table; `kw` carries `usecols`."""
    import pandas as pd
    return pd.read_csv(path, sep="\t", keep_default_na=False, na_values=[""], low_memory=False, **kw)


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


def existing_outputs(out: Path, names: tuple) -> list:
    """The once-only guards' scan: of each of `names` under `out`, the final file and the `.partial` a crashed run left behind, whichever
    exists - in `names` order (the first hit is the one a refusal prints)."""
    return [q for name in names for q in (Path(out) / name, partial_path(Path(out) / name)) if q.exists()]


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
    """Streamed since #705 (a) (`hashlib.file_digest`): the identical digest without reading a 270 MB export whole. Kept HERE, not
    delegated to the scaffold: the four finished reads' freeze records pin this runner, and the hash their freeze rests on must live
    inside what they pin."""
    with open(p, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


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
    out = {"module": Path(repo) / MODULE_REL,
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


def hashes_of(files: dict) -> dict:
    """{label: sha256} of a {label: path} map - a directory is `sha256_tree`, a missing path None."""
    got = {}
    for label, p in files.items():
        p = Path(p)
        got[label] = sha256_tree(p) if p.is_dir() else (sha256_file(p) if p.is_file() else None)
    return got


def frozen_hashes(data: Path, repo: Path = REPO, minutes: "Path | None" = None) -> dict:
    return hashes_of(frozen_files(data, repo, minutes))


def find_prereg_doc(repo: Path = REPO) -> tuple:
    """(path or None, problem or None): the single `docs/analysis/cb_preregistration_*.md`. None or several refuses."""
    hits = sorted(glob.glob(str(Path(repo) / "docs" / "analysis" / "cb_preregistration_*.md")))
    if len(hits) == 1:
        return Path(hits[0]), None
    if not hits:
        return None, "registration doc missing: docs/analysis/cb_preregistration_*.md"
    return None, f"{len(hits)} registration docs match docs/analysis/cb_preregistration_*.md - pass --prereg"


def freeze_check(*, doc: "Path | None" = None, data: "Path | None" = None, repo: Path = REPO, minutes: "Path | None" = None,
                 files: "dict | None" = None) -> list:
    """Problems (empty = every frozen artefact matches the registration doc's footer). Refuses on a missing doc, a
    missing FREEZE marker, a pin the footer does not carry, a pinned file that is missing, and any sha256 mismatch.
    `files` (#702 h60): a {footer label: path} map to check INSTEAD of the holdout's `frozen_files` (the h60 registration pins
    other files under other labels); the default is the holdout's, unchanged."""
    problems: list = []
    if doc is None and files is not None:
        return ["registration doc not given (a `files` map needs its own doc)"]
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
    got = frozen_hashes(data, repo, minutes) if files is None else hashes_of(files)
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


def pin_lines(data: Path, repo: Path = REPO, minutes: "Path | None" = None, files: "dict | None" = None) -> list:
    """The footer lines the registration doc must carry (everything but 'doc body', which P4 hashes last). `files` (#702 h60): the
    map to pin instead of the holdout's."""
    got = frozen_hashes(data, repo, minutes) if files is None else hashes_of(files)
    return [f"- {k} sha256: `{h or 'MISSING'}`" for k, h in got.items()]


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
    return existing_outputs(out, ("trades_holdout.tsv.gz", "entries_holdout.tsv.gz", f"trades_holdout_{P5_NAME}.tsv.gz"))


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


def p5_walk(inp: dict, workers: int, split: str, say, name: str = P5_NAME) -> tuple:
    """Walk `P5_ARMS` on the lod stop over every candidate of `inp` -> (trades path, entry tally, rows). The table is written to
    `<name>.partial` and renamed only after every date is walked (the holdout's `.partial` protocol). `name` (#702 h60): the file
    tag - the h60 read re-walks the pinned P5 population into `trades_<split>_h60twin.tsv.gz` with this very function and proves it
    equal in content to `trades_<split>_p5.tsv.gz`; the default is the P5 file, unchanged."""
    t = time.time()
    D = load_daily(inp["data"] / "daily_closes_all.csv.gz")
    _G.update(D=D, by_date=inp["by_date"], files=inp["files"], done=inp["done"], bars_cache={}, horizon=HORIZON,
              exits_kw={"stops": P5_STOPS, "arms": P5_ARMS})
    say(f"[load: {time.time() - t:.0f}s]")
    t = time.time()
    tp = inp["out"] / f"trades_{split}_{name}.tsv.gz"
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


def minute_inputs(rows: list, minutes_dir: Path) -> dict:
    """The (E, ticker) pairs `rows` need, what the minute directory holds of them (`pre_missing_pairs`), and the per-date file map with
    `os.devnull` for a date whose pairs are all logged `empty` (the fetcher writes no file for it: read as no minutes, never dropped) -
    the one chain under the pre-read, the h60 read and the exit read."""
    pairs = sorted({(r["E"], r["ticker"]) for r in rows})
    has_dir = minutes_dir.is_dir()
    on_disk = minute_date_files(minutes_dir) if has_dir else {}
    done = load_done_pairs(minutes_dir) if has_dir else None
    missing, lost = pre_missing_pairs(pairs, on_disk, done)
    files = dict(on_disk)
    for d in {e for e, _t in pairs} - set(files):
        files[d] = Path(os.devnull)
    return {"minutes_dir": minutes_dir, "pairs": pairs, "on_disk": on_disk, "done": done, "missing": missing, "lost": lost, "files": files,
            "by_date": group_by_date(rows, set(files))}


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
    return {"data": data, "out": out, "cands": cands, "path": path, **minute_inputs(cands, minutes_dir)}


def pre_complete(inp: dict) -> dict:
    """The complete inputs the minute and P5 stages take (`_setup_minute_inputs`' shape), once nothing is missing: `minute_inputs` already
    mapped a date with no minute file to `os.devnull`, so every row is grouped (asserted), none dropped."""
    assert sum(len(v) for v in inp["by_date"].values()) == len(inp["cands"])
    return inp


def pre_existing_outputs(out: Path) -> list:
    """Pre-read outputs already on disk: the final tables, or the `.partial` a crashed run left behind."""
    sfx = out_suffix(PRE_KEYS)
    return existing_outputs(out, (f"trades_{PRE_ERA}{sfx}.tsv.gz", f"entries_{PRE_ERA}{sfx}.tsv.gz", f"trades_{PRE_ERA}_{P5_NAME}.tsv.gz"))


def pre_option_problems(args) -> list:
    """Options the one pre-read may not carry: it runs in its registered form (the registered minute engine in full, both levels)."""
    bad = []
    for flag, val in (("--keys", getattr(args, "keys", None)), ("--levels", getattr(args, "levels", None)),
                      ("--limit-dates", getattr(args, "limit_dates", 0)), ("--no-close", getattr(args, "no_close", False)),
                      ("--no-apollo", getattr(args, "no_apollo", False))):
        if val:
            bad.append(f"{flag}: the pre-read reads {'/'.join(PRE_KEYS)} from candidates{out_suffix(PRE_KEYS)}.tsv in full; a partial or "
                       f"altered run would also consume the one run")
    out = getattr(args, "out", None)
    if out and Path(out).resolve() != (Path(args.data) / "out").resolve():
        bad.append("--out: the pre-read reads and writes DATA/out only - the one-run guard looks there, so another dir would sidestep it")
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
# #702 h60 (operator 2026-10-19; docs/analysis/cb_hourly_entry_prereg_2026-10-19.md): the HOURLY-CLOSE entry - buy only after
# an intraday bar CLOSES above the line - read on 2022-24 (decides), 2017-21 (+ 2020-21 alone) and 2025-26 beside, registered
# BEFORE any outcome. Three stages: `h60-step0` (the entry-time table; no exit, no daily bar), `h60-read` (the one-run read per
# period: the freeze check on every pin, STEP 0 against the registered table, the ORH5 twin re-walk against the pinned P5
# table, then the exits, the report and the verdict), `h60-hindsight` (the 39 multibaggers and TSLA row by row, refused until
# the period's verdict file exists). Every exit number is the module's (`day0_walk`, `walk_his_arms`); the runner adds the
# clock-anchored windows, the confirmation, the fill, the stop readings, the one-trade-per-base consumption and the tables.
# BUILT ON SYNTHETIC DATA ONLY: the build computed no real outcome (`h60-step0` and `--dry-run` / `--print-pins` only).
# ═════════════════════════════════════════════════════════════════════════════════════════════
H60_DOC = "cb_hourly_entry_prereg_2026-10-19.md"
H60_PERIODS = ("discovery", "pre", "holdout")
H60_LEVELS = ("tl", "com")                               # tl decides; com beside
H60_LEVEL = "tl"
H60_PRE_LAST_E = date(2021, 12, 31)                      # 2017-21 = bases whose FIRST-break E is on or before this; the pre file's last day
#                                                        # (2022-01-03) holds 13 first breaks outside the era and 57 eligible repeats
H60_WINDOW_2021 = ("2020-21", (2020, 2021))              # the sub-window reported beside on the pre period: first-break E year in 2020 / 2021
H60_EARLY_CLOSE = frozenset({
    "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29", "2019-12-24", "2020-11-27",
    "2020-12-24", "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29", "2024-12-24", "2025-07-03",
    "2025-11-28", "2025-12-24"})                         # the 13:00 closes (read from the files, matching the exchange's list)
H60_EARLY_CUT = 210                                      # minutes >= 13:00 on those days are after-hours prints: dropped for the bar entries ONLY
H60_EARLY_SHARE = 0.25                                   # check 2: a listed date < 25% of its bars at minute >= 210; every other date >= 25%
H60_BARS = {"h60": 60, "h30": 30, "h5": 5}               # the bar entries: [0,29] first (the article's first candle is 09:30-10:00), then
#                                                        # every k minutes to the close; h5 from 0 in fives. The LAST window never fills
H60_ENTRIES = ("h60", "h30", "h5", "h60_first", "h60_m025", "h60_line0", "orh60")
H60_FIRST_ONLY = ("h60_first", "orh60")                  # tried on the base's FIRST break day only (ORH60 = the registered first-break rule)
H60_ENTRY = "h60"                                        # the primary: the 60-minute bar on every eligible row of the base
H60_M025_X = 0.25                                        # h60_m025: close > line x (1 + 0.25 x ADR20 of the confirming row's D) - decides nothing
H60_STOPS = ("lod", "cbar_low", "base_low_cap1")
H60_STOP = "lod"                                         # the primary stop: the lowest minute low from 09:30 through the END of the window
H60_STOP_CANDIDATE = "cbar_low"                          # the registered STOP CANDIDATE: the confirming bar's own low (the paired stop bar)
H60_ARMS = {cb.P5_PRIMARY_ARM: cb.CUT_EXIT_ARMS[cb.P5_PRIMARY_ARM],     # c3_p33_t20_cut3: his exit with the staller cut (decides)
            cb.PRIMARY_ARM: cb.ARMS[cb.PRIMARY_ARM],                     # p33_s3_t10: the article                       - beside
            "r2_p33_t20": cb.HIS_EXIT_ARMS["r2_p33_t20"]}                # +2R only, 20-day trail                          - beside
H60_ARM = cb.P5_PRIMARY_ARM
H60_MIN_N = 30                                           # n < 30 mature trades is CAN'T TELL whatever the interval says
H60_PAIR_MIN_N = 30                                      # the paired bars: >= 30 bases with a trade on at least one side
H60_TAIL_R, H60_TAIL_TICKERS, H60_TAIL_MONTHS, H60_TAIL_WIDTH_ADR = 10.0, 3, 3, 0.25   # the >= 10R spread rule (stop >= 0.25 ADR20 wide)
H60_TOP_SHARE = 0.02                                     # "the top-2% share": the sum of R of the top 2% of trades, and its share of the total
H60_DATA_ABSTAINS = DATA_ABSTAINS + ("no_minute_after_bar",)
H60_DATA_ABSTAIN_MAX = DATA_ABSTAIN_MAX                  # check 3: <= 5% of the rows the rule actually READS
H60_TWIN = "h60twin"                                     # the ORH5 twin re-walk: trades_<period>_h60twin.tsv.gz, equal in content to trades_<period>_p5.tsv.gz
H60_CONSUMING = ("filled", "too_wide", "stop_at_or_above_fill")    # a confirmed day consumes the base whatever these three say
H60_MULTIBAGGERS = ("LVGO", "TSLA", "PTON", "ZM", "NIO", "PLUG", "ENPH", "FUBO", "ETSY", "CRWD", "DOCU", "NVAX", "BLNK", "SE", "SHOP",
                    "FSLY", "NET", "DDOG", "NXH", "W", "CVNA", "APPS", "SNAP", "MRNA", "TDOC", "ROKU", "PINS", "UPST", "GME", "AMC",
                    "DKNG", "FVRR", "PENN", "QS", "SPCE", "TTD", "LULU", "NVDA", "AMD")   # the 2017-21 addendum's 39 (SQ absent from Alpaca)
H60_TSLA = ("TSLA", "2020-04-30")                        # the layout check: exactly ONE confirmed day among its six rows, printed at STEP 0
H60_FALSE_PASS = ("Chance of a false pass: three deciding one-sided tests on 2022-24 (the C1 interval, the paired entry delta, the paired "
                  "stop delta), each ~2.5% under a true zero if the block bootstrap is calibrated -> ~7% that at least one passes by "
                  "chance; the tail-spread and beat-C0 conditions make a C1 chance pass rarer.")
# STEP 0 must equal the registration's expected-n table (candidate counts only; `multi` = bases with >= 2 distinct break days;
# orh5_C1_fills = the published fill count). A difference refuses the read before any exit is walked.
H60_EXPECTED = {
    "discovery": {"C0": 12285, "C0_multi": 7672, "C1": 102, "C1_multi": 63, "orh5_C1_fills": 79, "C2": 7, "C3": 183, "C4": 507, "C5": 198,
                  "C6": 20, "C7": 127, "com_C1": 112, "tl_rows": 41307},
    "pre": {"C0": 17392, "C0_multi": 11414, "C1": 216, "C1_multi": 129, "orh5_C1_fills": 180, "C2": 16, "C3": 355, "C4": 1252, "C5": 414,
            "C6": 36, "C7": 305, "com_C1": 245, "tl_rows": 68939},
    "2020-21": {"C0": 11600, "C0_multi": 7672, "C1": 88, "C1_multi": 49, "orh5_C1_fills": 72, "C2": 8, "C3": 128, "C4": 839, "C5": 202,
                "C6": 13, "C7": 115},
    "holdout": {"C0": 10554, "C0_multi": 6564, "C1": 43, "C1_multi": 29, "orh5_C1_fills": 31, "C2": 3, "C3": 107, "C4": 317, "C5": 99,
                "C6": 6, "C7": 76, "com_C1": 42, "tl_rows": 37917},
}
H60_EXPECT_C1_N = (60, 90)                               # expectation (changes no rule): discovery C1 n in 60-90
H60_EXPECT_FILL_DAY_STOP = 0.25                          # expectation: the C0 share stopped on the fill day under h60 < 25% (ORH5 ~ 35%)
H60_EXPECT_ORH5_C0 = (-0.17, 0.31, 0.9)                  # expectation: the ORH5 C0 baseline reads -0.17R, win 31%, >= 10R 0.9 per 100

H60_STEP0_COLS = (["ticker", "D", "E", "K", "period", "pole_date", "row_no", "n_rows", "retrigger", "first_E", "sessions_since_first",
                   "gap_kind", "early_close", "minutes_state", "variant", "status", "reason", "tried", "trade", "window_end", "walk_from",
                   "fill_minute", "width_pct", "fill_le_line", "lbo_kind", "own_C1"] + CELL_COLS)
H60_TRADE_COLS = (["ticker", "D", "E", "K", "period", "pole_date", "base", "first_E", "first_month", "fill_month", "year", "row_no",
                   "sessions_since_first", "gap_kind", "early_close"] + CELL_COLS
                  + ["own_C1", "gap_over_1adr", "phase_qqq_10_20", "apollo_regime", "adr20", "entry", "window_end", "walk_from",
                     "fill_minute", "fill", "level", "fill_le_line", "stop_variant", "stop", "width_pct", "width_adr", "abstain_reason",
                     "status", "arm", "realized_r", "pnl_adr", "acct_pct", "sessions_held", "mature", "open_mark", "fill_day_stop",
                     "partial_kind", "partial_session", "beabove", "fwd_bars", "fwd_hole"])
H60_PAIR_COLS = (["ticker", "pole_date", "K", "base", "period", "first_D", "first_E", "first_month", "first_year", "n_rows"] + CELL_COLS
                 + ["orh5_status", "orh5_reason", "orh5_data_abstain", "orh5_fill", "orh5_r", "orh5_adr", "orh5_mature", "orh5_open",
                    "h60_status", "h60_reason", "h60_E", "h60_row_no", "h60_fill", "h60_fill_minute", "h60_r", "h60_adr", "h60_mature",
                    "h60_open", "h60_same_day", "h60_gap_kind", "own_C1", "h60_first_status", "h60_first_r", "h60_first_mature",
                    "h60_first_open", "cbar_status", "cbar_r", "cbar_adr", "cbar_mature", "cbar_open"])
H60_STAT_COLS = ["n_filled", "n", "n_open", "mean_r", "ci_lo", "ci_hi", "win_rate", "avg_win", "avg_loss", "median_r", "share_ge5",
                 "share_ge10", "share_ge20", "sum_r", "top2_sum_r", "top2_share", "mean_pnl_adr", "mean_acct_pct", "fill_day_stop_share",
                 "median_held", "tail_n", "tail_tickers", "tail_months", "tail_n_nowidth", "tail_tickers_nowidth", "tail_months_nowidth"]
H60_REPORT_COLS = ["period", "window", "cell", "K", "entry", "stop", "arm", "slice", "value"] + H60_STAT_COLS + ["too_wide", "stop_abstain",
                                                                                                                 "never_confirmed", "data_abstain",
                                                                                                                 "verdict", "why"]


# ── windows, bars, the confirmation and the fill ─────────────────────────────────────────────────────────────────────────────
def h60_windows(variant: str, early_close: bool) -> list:
    """The clock-anchored minute-index windows of a bar entry, in order: [0,29] first (the article's 09:30-10:00 candle), then every
    k minutes to the close (`h5`: fives from 0). On an early-close day the last window ends at 209. The last window never fills."""
    k = H60_BARS[variant]
    last = H60_EARLY_CUT - 1 if early_close else 389
    ends = list(range(4, last + 1, 5)) if k == 5 else [29] + list(range(29 + k, last + 1, k))
    out, lo = [], 0
    for hi in ends:
        out.append((lo, hi))
        lo = hi + 1
    return out


def h60_trim(mb: "cb.MinuteBars | None", early_close: bool) -> "cb.MinuteBars | None":
    """The bar entries' minutes: on a listed early-close day every minute >= 210 is dropped BEFORE any minute check (the fetcher keeps
    prints stamped to 15:59; after 13:00 they are after-hours trades). Any other day, and the ORH entries, read the minutes as stored."""
    if mb is None or not early_close:
        return mb
    keep = mb.minute < H60_EARLY_CUT
    if bool(keep.all()):
        return mb
    return cb.MinuteBars(mb.minute[keep], mb.o[keep], mb.h[keep], mb.l[keep], mb.c[keep], mb.v[keep])


def h60_confirm(mb: "cb.MinuteBars", windows: list, level: float) -> dict:
    """The FIRST bar of the day whose close is above `level` (strict). A bar's close = the close of the LAST minute present in its
    window; a window with no minute is no bar. The final window never fills (`last_bar_only`); a confirming window with no present
    minute after it is `no_minute_after_bar` (a data abstain: the day cannot confirm later, no later minute exists). On a confirmation:
    `walk_from` = the window's last present minute (the module's day-0 functions start there, so the fill minute is read inclusive),
    `fill_minute` / `fill_open` = the first present minute after the window and its open, `lod` = the lowest low of the minutes through
    the window's end, `cbar_low` = the lowest low inside the window."""
    last_w = len(windows) - 1
    for w, (lo, hi) in enumerate(windows):
        pos = np.flatnonzero((mb.minute >= lo) & (mb.minute <= hi))
        if not len(pos):
            continue
        j = int(pos[-1])
        close = float(mb.c[j])
        if not close > level:
            continue
        base = {"window_end": hi, "walk_from": int(mb.minute[j]), "bar_close": close}
        if w == last_w:
            return {"status": "last_bar_only", **base}
        if j + 1 >= len(mb):
            return {"status": "no_minute_after_bar", **base}
        return {"status": "confirmed", **base, "fill_minute": int(mb.minute[j + 1]), "fill_open": float(mb.o[j + 1]),
                "lod": float(mb.l[:j + 1].min()), "cbar_low": float(mb.l[pos].min())}
    return {"status": "no_confirm"}


def h60_entry(conf: dict, level: float, adr20: float) -> dict:
    """The entry of a confirmed day in the module's `_entry_row` shape, plus `walk_from`, `window_end`, `bar_close`, `fill_open`,
    `cbar_low`. Fill = the fill minute's open x (1 + ENTRY_SLIPPAGE_PCT); stop = `lod`. Abstain `stop_at_or_above_fill` when that
    OPEN <= the stop (the registration: the trigger is the open, tighter than the module's `stop >= fill` by the slippage), else the
    module's own width rule (`_finish_entry`: `too_wide` beyond one ADR20). A fill at or under the line is legal and taken as is."""
    fill = conf["fill_open"] * (1.0 + cb.ENTRY_SLIPPAGE_PCT)
    stop = conf["lod"]
    extra = {k: conf[k] for k in ("walk_from", "window_end", "bar_close", "fill_open", "cbar_low")}
    if conf["fill_open"] <= stop:
        return {**cb._entry_row("abstain", "stop_at_or_above_fill", fill=fill, stop=stop, fill_minute=conf["fill_minute"], level=level), **extra}
    bad = cb._finish_entry(fill, stop, conf["fill_minute"], level, adr20)
    if bad is not None:
        return {**bad, **extra}
    return {**cb._entry_row("filled", None, fill=fill, stop=stop, fill_minute=conf["fill_minute"], width_pct=(fill - stop) / fill,
                            level=level), **extra}


def h60_stop_readings(entry: dict, base_low: "float | None", adr20: float) -> dict:
    """The three stop readings of a FILLED h60 entry, each {stop, reason, width_pct}: `lod` (the entry's own); `cbar_low` (the
    confirming bar's low) with the same two abstains; `base_low_cap1` = max(base low, fill x (1 - ADR20)) - never `too_wide` by
    construction and never abstains in the registration, but a cap cannot pull a base low that sits at or above the fill under it: that
    case is `stop_at_or_above_fill` here (it cannot be walked) and is COUNTED in the report, not hidden. `base_low` None (no watch row)
    reads as the capped level alone."""
    fill, op = float(entry["fill"]), float(entry["fill_open"])
    cap = fill * (1.0 - adr20)
    raw = {"lod": float(entry["stop"]), "cbar_low": float(entry["cbar_low"]),
           "base_low_cap1": max(float(base_low), cap) if base_low is not None else cap}
    out = {}
    for name in H60_STOPS:
        s = raw[name]
        if op <= s:
            out[name] = {"stop": s, "reason": "stop_at_or_above_fill", "width_pct": None}
            continue
        width = (fill - s) / fill
        out[name] = {"stop": s, "reason": ("too_wide" if (name != "base_low_cap1" and width > adr20) else None), "width_pct": width}
    return out


def h60_levels(c: dict) -> dict:
    """{variant: the level its bars must close above} for one candidate row: the row's own `pivot` (the redrawn line; `com` its level),
    `h60_m025` the line lifted by 0.25 ADR20 of the row's D, `h60_line0` the FIRST-break night's line projected to this row (stamped by
    `h60_annotate`; None on `com` and when the first break had no line)."""
    p = float(c["pivot"])
    return {"h60": p, "h30": p, "h5": p, "h60_first": p, "h60_m025": p * (1.0 + H60_M025_X * float(c["adr20"])), "h60_line0": c.get("line0")}


def _h60_fact(status, reason=None, **kw) -> dict:
    out = {"status": status, "reason": reason, "window_end": None, "walk_from": None, "fill_minute": None, "width_pct": None,
           "fill_le_line": None}
    out.update(kw)
    return out


def h60_row_facts(c: dict, mb_raw: "cb.MinuteBars | None") -> dict:
    """STEP 0: the ENTRY-TIME facts of every entry variant on one candidate row - {variant: {status, reason, window_end, walk_from,
    fill_minute, width_pct, fill_le_line}} and nothing else (no fill price, no stop, no day-0, no exit). The bar entries read the
    trimmed minutes (`h60_trim`) through the module's registered pre-checks (`entry_variants` on those minutes: no_minutes /
    minute_daily_mismatch / minute_high_below_pivot), then `h60_confirm` + `h60_entry`; `orh60` and `orh5` are the module's own
    variants on the minutes AS STORED (the registered first-break rules, after-hours prints included). `fill_le_line` = the fill at or
    under the row's `pivot`."""
    early = c["E"] in H60_EARLY_CLOSE
    pivot, adr20 = float(c["pivot"]), float(c["adr20"])
    out = {}
    mb = h60_trim(mb_raw, early)
    pre = cb.entry_variants(mb, pivot=pivot, adr20=adr20, day_high=float(c["high_E"]), day_low=float(c["low_E"]))["pivot"]
    data = pre["reason"] if pre["status"] == "abstain" and pre["reason"] in DATA_ABSTAINS else None
    for v, level in h60_levels(c).items():
        if data is not None:
            out[v] = _h60_fact("abstain", data)
            continue
        if level is None:
            out[v] = _h60_fact("no_level")
            continue
        conf = h60_confirm(mb, h60_windows("h60" if v.startswith("h60") else v, early), float(level))
        if conf["status"] != "confirmed":
            out[v] = (_h60_fact("abstain", "no_minute_after_bar", window_end=conf["window_end"], walk_from=conf["walk_from"])
                      if conf["status"] == "no_minute_after_bar" else
                      _h60_fact(conf["status"], window_end=conf.get("window_end"), walk_from=conf.get("walk_from")))
            continue
        ent = h60_entry(conf, float(level), adr20)
        out[v] = _h60_fact(ent["status"], ent["reason"], window_end=ent["window_end"], walk_from=ent["walk_from"],
                           fill_minute=ent["fill_minute"], width_pct=ent["width_pct"], fill_le_line=int(ent["fill"] <= pivot))
    raw = cb.entry_variants(mb_raw, pivot=pivot, adr20=adr20, day_high=float(c["high_E"]), day_low=float(c["low_E"]))
    for v in ("orh60", "orh5"):
        o = raw[v]
        out[v] = _h60_fact(o["status"], o["reason"], fill_minute=o["fill_minute"], width_pct=o["width_pct"],
                           fill_le_line=(int(o["fill"] <= pivot) if o["fill"] is not None else None))
    return out


# ── population: every row under the pole, the base's period, the watch-night facts, the consumption rule ─────────────────────
def h60_sources(period: str) -> list:
    """[(candidates file name, levels read from it)] of a period: cb702's `candidates.tsv` (tl) and `candidates_com_comb.tsv` (com)
    for discovery / holdout; the pre file carries both."""
    return [("candidates_tl_com.tsv", ("tl", "com"))] if period == "pre" else [("candidates.tsv", ("tl",)), ("candidates_com_comb.tsv", ("com",))]


def h60_watch_file(period: str, k: str) -> str:
    if period == "pre":
        return "watch_tl_com.tsv.gz"
    return "watch.tsv.gz" if k == "tl" else "watch_com_comb.tsv.gz"


def h60_dirs(args) -> dict:
    """{"cb702": the 2022+ data dir (--data), "cb702_pre": the Alpaca-era dir (--data-pre, default the sibling `cb702_pre`)}."""
    data = Path(args.data)
    pre = getattr(args, "data_pre", None)
    return {"cb702": data, "cb702_pre": Path(pre) if pre else data.parent / "cb702_pre"}


def h60_period_dir(dirs: dict, period: str) -> Path:
    return dirs["cb702_pre"] if period == "pre" else dirs["cb702"]


def h60_in_period(first: dict, period: str) -> bool:
    """A base belongs to the period of its FIRST-break row: the row's split label (cb702; a discovery base keeps its holdout-labelled
    repeats), or a first-break E inside the era (pre; the 13 first breaks on 2022-01-03 are out)."""
    if period == "pre":
        return date.fromisoformat(first["E"]) <= H60_PRE_LAST_E
    return first["split"] == period


def h60_read_bases(out: Path, period: str) -> dict:
    """{(ticker, pole_date, K): rows in E order} - EVERY row under the pole (rule (b): the runner's own spec key, which never ends a base
    on an absent night), both split labels read, the base kept when its first break is in the period. The first row carries
    `retrigger = 0` by the daily stage's stamping (asserted)."""
    rows: list = []
    for name, levels in h60_sources(period):
        kw = {"era": PRE_ERA} if period == "pre" else {"split": None}
        rows += read_candidates(out / name, extra_floats=("base_depth",), where=lambda rec, lv=levels: rec["K"] in lv, **kw)
    groups = defaultdict(list)
    for r in rows:
        groups[(r["ticker"], r["pole_date"], r["K"])].append(r)
    keep = {}
    for key, rs in groups.items():
        rs.sort(key=lambda r: r["E"])
        assert rs[0]["retrigger"] == 0, key
        if h60_in_period(rs[0], period):
            keep[key] = rs
    return keep


def h60_watch_index(path: Path, k: str) -> dict:
    """The watch-night facts the read joins: {"row": {(ticker, D): {ci, i, pole_high, base_low, pivot, slope, anchor}}, "nights": {ticker:
    set of ci with a watch row}, "noline": {(ticker, pole_date): set of ci whose watch row carries no level}}. `slope` / `anchor` only on tl."""
    cols = ["ticker", "watch_date", "ci", "i", "pole_date", "pole_high", "base_low", f"pivot_{k}"] + (["tl_slope_pct", "tl_anchor_idx"] if k == "tl" else [])
    df = read_tsv(path, usecols=cols)
    row, nights, noline = {}, defaultdict(set), defaultdict(set)
    piv = df[f"pivot_{k}"].to_numpy(dtype=float)
    slope = df["tl_slope_pct"].to_numpy(dtype=float) if k == "tl" else np.full(len(df), np.nan)
    anchor = df["tl_anchor_idx"].to_numpy(dtype=float) if k == "tl" else np.full(len(df), np.nan)
    for n, (t, d, ci, i, pole, ph, bl) in enumerate(zip(df["ticker"], df["watch_date"], df["ci"], df["i"], df["pole_date"],
                                                         df["pole_high"], df["base_low"])):
        ci = int(ci)
        row[(t, d)] = {"ci": ci, "i": int(i), "pole_high": float(ph), "base_low": float(bl),
                       "pivot": None if np.isnan(piv[n]) else float(piv[n]), "slope": None if np.isnan(slope[n]) else float(slope[n]),
                       "anchor": None if np.isnan(anchor[n]) else int(anchor[n])}
        nights[t].add(ci)
        if np.isnan(piv[n]):
            noline[(t, pole)].add(ci)
    return {"row": row, "nights": nights, "noline": noline}


def h60_anchor_high(w: dict) -> "float | None":
    """high[A] of a tl watch night from its pivot, slope and anchor: pivot_tl = high[A] x (1 + slope x (i + 1 - A))."""
    if w.get("pivot") is None or w.get("slope") is None or w.get("anchor") is None:
        return None
    den = 1.0 + w["slope"] * (w["i"] + 1 - w["anchor"])
    return w["pivot"] / den if den > 0 else None


def h60_gap_kind(ticker: str, pole: str, ci0: int, ci1: int, widx: dict) -> str:
    """The absent-night kinds between the first break's watch night (ci0) and this row's (ci1), exclusive: "absent" = a session with no
    watch row for the ticker at all (the stock failed a gate that night), "no_line" = a watch row of the same pole with no level (a
    high topped the base's highest high; the line is gone for 3 nights). "" = none. Reported beside, never deciding."""
    if ci1 - ci0 <= 1:
        return ""
    between = range(ci0 + 1, ci1)
    nights = widx["nights"].get(ticker, set())
    absent = any(ci not in nights for ci in between)
    nl = widx["noline"].get((ticker, pole), set())
    noline = any(ci in nl for ci in between)
    return "+".join(x for x, on in (("absent", absent), ("no_line", noline)) if on)


def h60_annotate(bases: dict, widx_by_k: dict) -> None:
    """Stamp on every row what the read needs beyond the candidates table: `_ci` / `_i` (the watch night), `pole_high`, `base_low`,
    `anchor_high`, `line0` (tl: the first-break night's line projected forward, anchor high x (1 + slope0 x sessions since the anchor)),
    `row_no`, `n_rows`, `first_E`, `first_month`, `sessions_since_first`, `gap_kind`, `_first` (the first-break row's cell flags)."""
    for (ticker, pole, k), rows in bases.items():
        widx = widx_by_k[k]
        w0 = widx["row"][(ticker, rows[0]["D"])]
        high_a0 = h60_anchor_high(w0) if k == "tl" else None
        first_cells = {cell: bool(rows[0][cell]) for cell in CELL_COLS}
        for n, r in enumerate(rows):
            w = widx["row"][(ticker, r["D"])]
            r["_ci"], r["_i"] = w["ci"], w["i"]
            r["pole_high"], r["base_low"] = w["pole_high"], w["base_low"]
            r["anchor_high"] = h60_anchor_high(w) if k == "tl" else None
            r["line0"] = (high_a0 * (1.0 + w0["slope"] * (w["i"] + 1 - w0["anchor"]))) if high_a0 is not None else None
            r["row_no"], r["n_rows"] = n, len(rows)
            r["first_E"], r["first_month"] = rows[0]["E"], rows[0]["E"][:7]
            r["sessions_since_first"] = w["ci"] - w0["ci"]
            r["gap_kind"] = h60_gap_kind(ticker, pole, w0["ci"], w["ci"], widx)
            r["_first"] = first_cells
            r["base"] = f"{ticker}|{pole}|{k}"


def h60_select(bases: dict, facts: dict) -> dict:
    """The one trade per base, per entry variant: {(ticker, E, K): {variant: "tried" | "trade"}}. Rows in E order; a data abstain
    (`no_minutes`, `minute_daily_mismatch`, `minute_high_below_pivot`, `no_minute_after_bar`) is tried and consumes nothing; a day that
    confirmed - `filled`, or an abstain `too_wide` / `stop_at_or_above_fill` - is the base's trade and consumes it; `no_confirm`,
    `last_bar_only`, `no_level`, `no_trigger` move to the next row. The first-break-only variants (`h60_first`, `orh60`) try the
    first row alone."""
    out: dict = defaultdict(dict)
    for key, rows in bases.items():
        for v in H60_ENTRIES:
            for r in (rows[:1] if v in H60_FIRST_ONLY else rows):
                f = facts[(r["ticker"], r["E"], r["K"])][v]
                consumes = f["status"] == "filled" or (f["status"] == "abstain" and f["reason"] in H60_CONSUMING)
                out[(r["ticker"], r["E"], r["K"])][v] = "trade" if consumes else "tried"
                if consumes:
                    break
    return dict(out)


def h60_lbo_kind(rows: list, n: int, variant: str, facts: dict, pick: dict) -> str:
    """What followed a day whose ONLY confirming bar was the final one (the hole the registration counts, not fixes): a later row of the
    base confirmed; no row follows - the close ended the base (above the pole high) or not; later rows exist and none confirmed - the
    high topped the anchor (tl: no line for 3 nights) or the next row's redrawn line sat near that high and was not cleared."""
    r = rows[n]
    later = rows[n + 1:]
    if any(pick.get((x["ticker"], x["E"], x["K"]), {}).get(variant) == "trade" for x in later):
        return "later_confirmed"
    if not later:
        return "ended_base" if (r.get("pole_high") is not None and float(r["close_E"]) > r["pole_high"]) else "no_later_row"
    if r.get("anchor_high") is not None and float(r["high_E"]) > r["anchor_high"]:
        return "topped_anchor"
    return "next_line_not_cleared"


# ── the minute inputs of a period ──────────────────────────────────────────────────────────────────────────────────────────────
def h60_minute_inputs(bases: dict, minutes_dir: Path) -> dict:
    """`minute_inputs` over every row of every base."""
    return minute_inputs([r for rs in bases.values() for r in rs], minutes_dir)


def _h60_step0_job(date_iso: str) -> tuple:
    """STEP 0 for one E date: the minute file once, every candidate row of the date through `h60_row_facts` (entry-time facts only; no daily
    bar is opened, nothing reaches an exit walker). Returns ({(ticker, E, K): {variant: fact}}, minutes_state per row, the early-close
    tally of the file's wanted blocks: (bars, bars at minute >= 210))."""
    cands = _G["by_date"][date_iso]
    blocks, _info = read_minute_file(_G["files"][date_iso], {c["ticker"] for c in cands})
    done = _G["done"]
    facts, states = {}, {}
    n_bars = n_late = 0
    for t, rows in blocks.items():
        n_bars += len(rows)
        n_late += sum(1 for r in rows if int(r[1]) >= H60_EARLY_CUT)
    for c in cands:
        mb, state = minutes_for(blocks, done, date_iso, c["ticker"])
        key = (c["ticker"], c["E"], c["K"])
        states[key] = state
        facts[key] = h60_row_facts(c, None if state == "pending" else mb)
    return facts, states, (n_bars, n_late)


def h60_early_close_problems(shares: dict) -> list:
    """Check 2: every listed date on which minutes were read shows < 25% of its bars at minute >= 210; every other date >= 25%. A date with
    no bar read is not judged."""
    bad = []
    for d, (n, late) in sorted(shares.items()):
        if not n:
            continue
        share = late / n
        if d in H60_EARLY_CLOSE and share >= H60_EARLY_SHARE:
            bad.append(f"{d} is a listed early close but {share:.0%} of its bars are at minute >= {H60_EARLY_CUT}")
        elif d not in H60_EARLY_CLOSE and share < H60_EARLY_SHARE:
            bad.append(f"{d} is not a listed early close but only {share:.0%} of its bars are at minute >= {H60_EARLY_CUT}")
    return bad


# ── STEP 0: the entry-time table and its check against the registered counts ───────────────────────────────────────────────────
def h60_windows_of(period: str) -> list:
    """The report windows of a period: the period itself, plus 2020-21 alone on the pre era (first-break E year)."""
    return [(period, None)] + ([H60_WINDOW_2021] if period == "pre" else [])


def h60_base_in_window(rows: list, years) -> bool:
    return years is None or int(rows[0]["E"][:4]) in years


def h60_step0_rows(bases: dict, facts: dict, states: dict, pick: dict, period: str) -> list:
    rows_out = []
    for key, rows in bases.items():
        for n, r in enumerate(rows):
            rk = (r["ticker"], r["E"], r["K"])
            fx, pk = facts[rk], pick.get(rk, {})
            for v in H60_ENTRIES:
                f = fx[v]
                tag = pk.get(v)
                row = {"ticker": r["ticker"], "D": r["D"], "E": r["E"], "K": r["K"], "period": period, "pole_date": r["pole_date"],
                       "row_no": n, "n_rows": len(rows), "retrigger": r["retrigger"], "first_E": r["first_E"],
                       "sessions_since_first": r["sessions_since_first"], "gap_kind": r["gap_kind"],
                       "early_close": int(r["E"] in H60_EARLY_CLOSE), "minutes_state": states[rk], "variant": v,
                       "status": f["status"], "reason": f["reason"] or "", "tried": int(tag is not None), "trade": int(tag == "trade"),
                       "window_end": f["window_end"], "walk_from": f["walk_from"], "fill_minute": f["fill_minute"],
                       "width_pct": f["width_pct"], "fill_le_line": f["fill_le_line"],
                       "lbo_kind": h60_lbo_kind(rows, n, v, facts, pick) if f["status"] == "last_bar_only" else "",
                       "own_C1": int(bool(r["C1"]))}
                for cell in CELL_COLS:
                    row[cell] = int(r["_first"][cell])
                rows_out.append(row)
    return rows_out


def h60_base_outcome(rows: list, facts: dict, pick: dict, variant: str) -> tuple:
    """(status, reason, the confirming row or None) of a base under a variant from the entry-time facts: the row tagged "trade" (its status
    `filled` / `too_wide` / `stop_at_or_above_fill`), else `never_confirmed` (every tried row: no_confirm / last_bar_only / no_level /
    no_trigger / a data abstain) with the reason `data_only` when every tried row was a data abstain."""
    tried = []
    for r in rows:
        tag = pick.get((r["ticker"], r["E"], r["K"]), {}).get(variant)
        if tag is None:
            continue
        f = facts[(r["ticker"], r["E"], r["K"])][variant]
        if tag == "trade":
            return ("filled" if f["status"] == "filled" else f["reason"]), f["reason"], r
        tried.append(f)
    data_only = bool(tried) and all(f["status"] == "abstain" and f["reason"] in H60_DATA_ABSTAINS for f in tried)
    return "never_confirmed", ("data_only" if data_only else ""), None


def h60_step0_counts(bases: dict, facts: dict, pick: dict, years=None) -> dict:
    """The registered-table counts of one window (bases whose first-break E year is in `years`, all when None): per cell the bases (tl),
    the multi-break bases, com C1 bases, the ORH5 C1 fills (the module's orh5 status on the first break), and per cell the h60 outcomes."""
    c: Counter = Counter()
    for key, rows in bases.items():
        if not h60_base_in_window(rows, years):
            continue
        k = key[2]
        first = rows[0]
        multi = len({r["E"] for r in rows}) >= 2
        cells = [cell for cell in CELL_COLS if first["_first"][cell]]
        f5 = facts[(first["ticker"], first["E"], k)]["orh5"]
        for cell in cells:
            c[(k, cell)] += 1
            c[(k, cell + "_multi")] += int(multi)
            if f5["status"] == "filled":
                c[(k, cell + "_orh5_fills")] += 1
            for v in H60_ENTRIES:
                st, reason, row = h60_base_outcome(rows, facts, pick, v)
                c[(k, cell, v, st)] += 1
                if st == "never_confirmed" and reason == "data_only":
                    c[(k, cell, v, "data_only")] += 1
                if row is not None:
                    if row["gap_kind"]:
                        c[(k, cell, v, "after_gap")] += 1
                    if row["row_no"] == 0:
                        c[(k, cell, v, "same_day")] += 1
    return dict(c)


def h60_step0_problems(counts: dict, expected: dict) -> list:
    """Check 5: the STEP 0 counts must equal the registered table (candidate counts). Every key the table carries is compared - but
    `tl_rows`, which the caller leaves out (the row count is by label / file: `h60_label_rows`)."""
    got = {"C0": counts.get(("tl", "C0"), 0), "C0_multi": counts.get(("tl", "C0_multi"), 0), "C1": counts.get(("tl", "C1"), 0),
           "C1_multi": counts.get(("tl", "C1_multi"), 0), "orh5_C1_fills": counts.get(("tl", "C1_orh5_fills"), 0),
           "com_C1": counts.get(("com", "C1"), 0)}
    for cell in ("C2", "C3", "C4", "C5", "C6", "C7"):
        got[cell] = counts.get(("tl", cell), 0)
    return [f"{k}: STEP 0 reads {got.get(k)}, the registration's table says {want}" for k, want in expected.items() if got.get(k) != want]


def _dist(values: list, cuts: tuple) -> str:
    """A small histogram of integers over the cut points (`<= c1`, `c1 < x <= c2`, ..., `> cn`)."""
    v = [x for x in values if x is not None]
    if not v:
        return "(none)"
    parts, lo = [], None
    for cut in cuts:
        parts.append(f"{'<= ' + str(cut) if lo is None else str(lo + 1) + '-' + str(cut)}: {sum(1 for x in v if (lo is None or x > lo) and x <= cut)}")
        lo = cut
    parts.append(f"> {lo}: {sum(1 for x in v if x > lo)}")
    return "  ".join(parts) + f"  (n {len(v)}, median {int(np.median(v))})"


def h60_step0_text(period: str, bases: dict, facts: dict, states: dict, pick: dict, counts_by_window: dict, problems_by_window: dict,
                   shares: dict, inp: dict, pinned_fills: "dict | None", tried: list, data_abstains: list, early_problems: list) -> str:
    """`tried` = the h60 facts of the tl rows the rule READ; `data_abstains` = those of them that abstained on a data reason;
    `early_problems` = `h60_early_close_problems(shares)` - all three computed once, in `h60_step0`."""
    out: list = []
    A = out.append
    A(f"#702 h60 STEP 0 - {period}: ENTRY-TIME facts only (no fill price, stop, day-0 or exit was computed here). Population: every row under "
      f"the pole (spec key, rule (b)), the base's period from its FIRST-break row; levels tl (decides) / com (beside).")
    n_rows = sum(len(rs) for rs in bases.values())
    A(f"bases {len(bases):,} ({sum(1 for k in bases if k[2] == 'tl'):,} tl / {sum(1 for k in bases if k[2] == 'com'):,} com); rows {n_rows:,}; "
      f"(E, ticker) pairs {len(inp['pairs']):,}; pairs not logged in _done.psv {len(inp['missing']):,}; logged ok with no file {len(inp['lost']):,}; "
      f"minutes state {dict(sorted(Counter(states.values()).items()))}")
    listed = {d: s for d, s in shares.items() if d in H60_EARLY_CLOSE and s[0]}
    A(f"EARLY-CLOSE CHECK (check 2): listed dates read {len(listed)} - " + ", ".join(f"{d} {s[1] / s[0]:.0%}" for d, s in sorted(listed.items()))
      + f"; other dates with < {H60_EARLY_SHARE:.0%} at minute >= {H60_EARLY_CUT}: {sum(1 for d, s in shares.items() if d not in H60_EARLY_CLOSE and s[0] and s[1] / s[0] < H60_EARLY_SHARE)}"
      + (" -> FAILS: " + "; ".join(early_problems) if early_problems else " -> ok"))
    n_da = len(data_abstains)
    A(f"DATA-ABSTAIN SHARE (check 3, h60 on tl, the rows the rule READ): {n_da:,} of {len(tried):,} ({(n_da / len(tried) if tried else 0):.2%}; "
      f"{dict(Counter(f['reason'] for f in data_abstains))}) - limit "
      f"{H60_DATA_ABSTAIN_MAX:.0%}: {'BLOCKS THE READ' if tried and n_da / len(tried) > H60_DATA_ABSTAIN_MAX else 'ok'}")
    for wname, counts in counts_by_window.items():
        pr = problems_by_window[wname]
        A("")
        A(f"REGISTERED TABLE CHECK (check 5) - window {wname}: " + ("NO REGISTERED TABLE YET (expected=None: the counts below are what a new "
                                                                    "registration registers; nothing was compared)" if pr is None else
                                                                    "EQUAL to the registration's table" if not pr else "DIFFERS: " + "; ".join(pr)))
        body = []
        for cell in CELL_COLS:
            body.append([cell, counts.get(("tl", cell), 0), counts.get(("tl", cell + "_multi"), 0), counts.get(("tl", cell + "_orh5_fills"), 0),
                         (pinned_fills or {}).get((wname, cell), "-"), counts.get(("com", cell), 0), counts.get(("com", cell + "_orh5_fills"), 0)])
        A(table(body, ["cell", "tl bases", "tl multi-break", "ORH5 fills (entry facts)", "ORH5 fills (pinned P5 table)", "com bases", "com ORH5 fills"]))
        A(f"  h60 (tl) per cell: confirmed+filled / confirmed too_wide / confirmed stop_at_or_above_fill / never confirmed (of which data abstains only) / "
          f"confirmed on the first break day / confirmed after an absent or no-line night")
        body = []
        for cell in CELL_COLS:
            g = lambda st: counts.get(("tl", cell, "h60", st), 0)
            body.append([cell, g("filled"), g("too_wide"), g("stop_at_or_above_fill"), f"{g('never_confirmed')} ({g('data_only')})", g("same_day"), g("after_gap")])
        A(table(body, ["cell", "filled", "too_wide", "saaf", "never (data only)", "first day", "after a gap"]))
        A("  every entry (tl, C0 / C1): confirmed+filled / too_wide / saaf / never")
        body = []
        for v in H60_ENTRIES:
            ln = [v]
            for cell in ("C0", "C1"):
                g = lambda st: counts.get(("tl", cell, v, st), 0)
                ln.append(f"{g('filled')} / {g('too_wide')} / {g('stop_at_or_above_fill')} / {g('never_confirmed')}")
            body.append(ln)
        A(table(body, ["entry", "C0", "C1"]))
    # per-row facts on tl, h60: the nesting check, last_bar_only kinds, fill-minute and first-to-confirmed distributions, fill at/under the line
    rows_tl = [r for rs in bases.values() for r in rs if r["K"] == H60_LEVEL]
    fx = lambda r, v: facts[(r["ticker"], r["E"], r["K"])][v]
    conf = lambda f: f["status"] == "filled" or (f["status"] == "abstain" and f["reason"] in H60_CONSUMING)
    nest = sum(1 for r in rows_tl if conf(fx(r, "h60")) and not conf(fx(r, "h30"))) + sum(1 for r in rows_tl if conf(fx(r, "h30")) and not conf(fx(r, "h5")))
    A("")
    A(f"NESTING (per row, tl): rows h60 confirms that h30 does not, plus rows h30 confirms that h5 does not: {nest} (must be 0); rows confirmed by "
      f"h5 {sum(1 for r in rows_tl if conf(fx(r, 'h5')))}, h30 {sum(1 for r in rows_tl if conf(fx(r, 'h30')))}, h60 {sum(1 for r in rows_tl if conf(fx(r, 'h60')))} "
      f"of {len(rows_tl):,} rows")
    lbo = Counter(h60_lbo_kind(rs, n, "h60", facts, pick) for rs in bases.values() for n, r in enumerate(rs)
                  if r["K"] == H60_LEVEL and fx(r, "h60")["status"] == "last_bar_only")
    A(f"LAST_BAR_ONLY (tl, h60; the hole counted, not fixed): {sum(lbo.values())} rows, by what followed: {dict(sorted(lbo.items()))}")
    l0 = sum(1 for r in rows_tl if conf(fx(r, "h60_line0")))
    A(f"h60_line0 (the first-break night's line held) vs the redrawn line: rows confirmed {l0} vs {sum(1 for r in rows_tl if conf(fx(r, 'h60')))}; "
      f"rows where the two disagree: {sum(1 for r in rows_tl if conf(fx(r, 'h60_line0')) != conf(fx(r, 'h60')))}")
    trades = [(r, fx(r, "h60")) for r in rows_tl if pick.get((r["ticker"], r["E"], r["K"]), {}).get("h60") == "trade" and fx(r, "h60")["status"] == "filled"]
    A(f"FILL MINUTE (tl, h60 filled trades, minutes since 09:30): " + _dist([f["fill_minute"] for _r, f in trades], (30, 90, 150, 210, 270, 330)))
    A(f"FIRST BREAK -> CONFIRMED BREAK (sessions): " + _dist([r["sessions_since_first"] for r, _f in trades], (0, 1, 5, 20)))
    A(f"FILLED AT OR UNDER THE LINE: {sum(1 for _r, f in trades if f['fill_le_line'])} of {len(trades)}")
    ts = [(r, fx(r, "h60")) for rs in bases.values() for r in rs if (r["ticker"], r["pole_date"], r["K"]) == (H60_TSLA[0], H60_TSLA[1], "tl")]
    if ts:
        picks = [(r["E"], pick.get((r["ticker"], r["E"], r["K"]), {}).get("h60"), f["status"], f["reason"] or "") for r, f in ts]
        tr = [p for p in picks if p[1] == "trade"]
        A(f"TSLA {H60_TSLA[1]} (tl): rows " + ", ".join(f"{e} {st}{(' ' + rs) if rs else ''}{' <- TRADE' if tag == 'trade' else ''}" for e, tag, st, rs in picks)
          + f"; confirmed days: {len(tr)} ({'ONE, as the layout check expects' if len(tr) == 1 else 'NOT one - broken re-try logic or a layout surprise'})")
    return "\n".join(out)


def h60_pinned_fills(out: Path, period: str, bases: dict) -> dict:
    """{(window, cell): the ORH5 fills the PINNED P5 table carries} for the period's tl bases - the entry status read off the pinned file
    (a row with the primary arm = a filled entry); no outcome column is read."""
    p = out / f"trades_{period}_p5.tsv.gz"
    if not p.exists():
        return {}
    df = read_tsv(p, usecols=["ticker", "D", "K", "arm"] + list(CELL_COLS))
    df = df[(df["K"] == H60_LEVEL) & (df["arm"] == H60_ARM)]
    first = {(rs[0]["ticker"], rs[0]["D"]): rs for key, rs in bases.items() if key[2] == H60_LEVEL}
    out_: Counter = Counter()
    for t, d, *cells in df[["ticker", "D"] + list(CELL_COLS)].itertuples(index=False):
        rs = first.get((t, d))
        if rs is None:
            continue
        for wname, years in h60_windows_of(period):
            if h60_base_in_window(rs, years):
                for cell, on in zip(CELL_COLS, cells):
                    if int(on):
                        out_[(wname, cell)] += 1
    return dict(out_)


_H60_EXPECTED_DEFAULT = object()          # `h60_step0(expected=...)` unset: the module's H60_EXPECTED, looked up at CALL time (a rebind is seen)


def h60_step0(bases: dict, inp: dict, workers: int, period: str, out: Path, small: Path, pinned_fills: "dict | None",
              expected=_H60_EXPECTED_DEFAULT) -> dict:
    """Run STEP 0 (the per-date job, the selection, the counts, the checks) and write `h60_step0_<period>.tsv.gz` + `.txt`. Returns
    {facts, pick, problems (by window), text, data_share, early_problems} - what the callers read.
    `expected` (#705 v2 re-run, docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md B1 - the one named exception to "unchanged"): the
    registered table the counts are checked against, {window: {key: count}}. Unset = `H60_EXPECTED` (today's bytes, every finished caller);
    a dict = that table (the v2 reads pass the doc's §5); None = no registered table yet (stage 0 of a new registration: problems are None
    per window and the text says nothing was compared - never "EQUAL" against an empty table)."""
    table = H60_EXPECTED if expected is _H60_EXPECTED_DEFAULT else expected
    _G.update(by_date=inp["by_date"], files=inp["files"], done=inp["done"])
    facts, states, shares = {}, {}, {}
    for d, (fx, st, share) in zip(list(inp["by_date"]), _pool_map(_h60_step0_job, list(inp["by_date"]), workers)):
        facts.update(fx)
        states.update(st)
        shares[d] = share
    pick = h60_select(bases, facts)
    tl_rows = sum(len(rs) for key, rs in bases.items() if key[2] == H60_LEVEL)
    counts, problems = {}, {}
    for wname, years in h60_windows_of(period):
        counts[wname] = h60_step0_counts(bases, facts, pick, years)
        if table is None:
            problems[wname] = None
            continue
        exp = table.get(wname, {})
        problems[wname] = h60_step0_problems(counts[wname], {k: v for k, v in exp.items() if k != "tl_rows"})
    rows = h60_step0_rows(bases, facts, states, pick, period)
    out.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    write_tsv(out / f"h60_step0_{period}.tsv.gz", rows, H60_STEP0_COLS, gz=True)
    tried = [facts[(r['ticker'], r['E'], r['K'])]['h60'] for rs in bases.values() for r in rs
             if pick.get((r['ticker'], r['E'], r['K']), {}).get('h60') is not None and r['K'] == H60_LEVEL]
    data_abstains = [f for f in tried if f["status"] == "abstain" and f["reason"] in H60_DATA_ABSTAINS]
    early_problems = h60_early_close_problems(shares)
    text = h60_step0_text(period, bases, facts, states, pick, counts, problems, shares, inp, pinned_fills, tried, data_abstains, early_problems)
    text += f"\nTL ROWS of the period's bases: {tl_rows:,} (the registration's row count is by row LABEL / file: see the read's header)\n"
    (small / f"h60_step0_{period}.txt").write_text(text + "\n")
    (out / f"h60_step0_{period}.txt").write_text(text + "\n")
    return {"facts": facts, "pick": pick, "problems": problems, "text": text,
            "data_share": (len(data_abstains) / len(tried)) if tried else 0.0, "early_problems": early_problems}


def h60_label_rows(out: Path, period: str) -> "int | None":
    """The registration's `tl` row count: rows LABELLED with the period in cb702's candidates.tsv, or every tl row of the pre file."""
    name, levels = h60_sources(period)[0]
    p = out / name
    if not p.exists():
        return None
    n = 0
    with open(p, newline="") as fh:
        for rec in csv.DictReader(fh, delimiter="\t"):
            if rec["K"] == H60_LEVEL and (period == "pre" or rec["split"] == period):
                n += 1
    return n


# ── the exits ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def h60_walk(entry: dict, mb: "cb.MinuteBars", bars: "cb.DailyBars", cidx, e: int, adr20: float, stop: float, width: float,
             walk_from: int) -> tuple:
    """(fwd, cut, {arm: (arm_result, partial facts)}) of one filled entry on one stop: the module's `day0_walk` from `walk_from` (the
    confirming window's last present minute, so the fill minute's own low is read against the stop first) and `walk_his_arms` over
    `H60_ARMS` with closes through E and the forward window of E - exactly as the P5 walk wires them."""
    closes_before = bars.c[:e + 1]
    fwd, cut = forward_window(bars, cidx, e, HORIZON)
    entry2 = {**entry, "status": "filled", "reason": None, "stop": stop, "width_pct": width, "fill_minute": walk_from,
              "day0": cb.day0_walk(mb, fill_minute=walk_from, stop=stop)}
    res = cb.walk_his_arms(entry2, closes_before=closes_before, fwd=fwd, adr20=adr20, minutes=mb, horizon=HORIZON, arms=H60_ARMS)
    out = {}
    for name, raw in res.items():
        a = arm_result(raw, width=width, n_fwd=len(fwd), horizon=HORIZON)
        out[name] = (a, partial_facts(raw["events"], H60_ARMS[name]))
    return fwd, cut, out


def _h60_trade_base(c: dict, period: str, variant: str) -> dict:
    row = {"ticker": c["ticker"], "D": c["D"], "E": c["E"], "K": c["K"], "period": period, "pole_date": c["pole_date"], "base": c["base"],
           "first_E": c["first_E"], "first_month": c["first_month"], "fill_month": c["E"][:7], "year": int(c["E"][:4]), "row_no": c["row_no"],
           "sessions_since_first": c["sessions_since_first"], "gap_kind": c["gap_kind"], "early_close": int(c["E"] in H60_EARLY_CLOSE),
           "own_C1": int(bool(c["C1"])), "gap_over_1adr": int(bool(c["gap_over_1adr"])), "phase_qqq_10_20": int(bool(c["phase_qqq_10_20"])),
           "apollo_regime": c.get("apollo_regime", ""), "adr20": c["adr20"], "entry": variant}
    for cell in CELL_COLS:
        row[cell] = int(c["_first"][cell])
    return row


def h60_exit_rows(c: dict, variants: list, mb_raw: "cb.MinuteBars | None", bars: "cb.DailyBars", cidx, e: int, period: str) -> tuple:
    """The trades rows (H60_TRADE_COLS order) of one row's chosen variants: the entry re-derived from the minutes (the same `h60_confirm` /
    `h60_entry` STEP 0 ran, on the trimmed minutes), the stop readings (every reading on `h60`; `lod` on the others), the walks. An abstain
    is ONE row with no arm. `orh60` = the module's own variant on the stored minutes (its stop, its day 0)."""
    assert bars.dates[e].isoformat() == c["E"], (c["ticker"], e, c["E"])
    assert e >= cb.MIN_HISTORY and int(cidx[e]) - int(cidx[e - cb.MIN_HISTORY]) == cb.MIN_HISTORY, (c["ticker"], e)
    early = c["E"] in H60_EARLY_CLOSE
    adr20 = float(c["adr20"])
    mb = h60_trim(mb_raw, early)
    rows, tally = [], Counter()
    levels = h60_levels(c)
    pivot = float(c["pivot"])
    for v in variants:
        base = _h60_trade_base(c, period, v)
        if v == "orh60":
            ent = cb.entry_variants(mb_raw, pivot=pivot, adr20=adr20, day_high=float(c["high_E"]), day_low=float(c["low_E"]))["orh60"]
            if ent["status"] != "filled":
                rows.append(_by_cols({**base, "stop_variant": H60_STOP, "status": ent["status"], "abstain_reason": ent["reason"] or "",
                                      "fill_minute": ent["fill_minute"], "fill": ent["fill"], "stop": ent["stop"], "level": ent["level"],
                                      "width_pct": ent["width_pct"]}, H60_TRADE_COLS))
                tally[(v, H60_STOP, ent["status"], ent["reason"] or "")] += 1
                continue
            readings = {H60_STOP: {"stop": ent["stop"], "reason": None, "width_pct": ent["width_pct"]}}
            walk_from, mb_v = ent["fill_minute"], mb_raw
        else:
            conf = h60_confirm(mb, h60_windows("h60" if v.startswith("h60") else v, early), float(levels[v]))
            assert conf["status"] == "confirmed", (c["ticker"], c["E"], v, conf["status"])      # STEP 0 chose this row: it confirms
            ent = h60_entry(conf, float(levels[v]), adr20)
            base.update(window_end=ent["window_end"], walk_from=ent["walk_from"])
            if ent["status"] != "filled":
                rows.append(_by_cols({**base, "stop_variant": H60_STOP, "status": "abstain", "abstain_reason": ent["reason"],
                                      "fill_minute": ent["fill_minute"], "fill": ent["fill"], "stop": ent["stop"], "level": ent["level"],
                                      "width_pct": ent["width_pct"], "fill_le_line": int(ent["fill"] <= pivot)}, H60_TRADE_COLS))
                tally[(v, H60_STOP, "abstain", ent["reason"])] += 1
                if v != H60_ENTRY:
                    continue
                # the PRIMARY's confirmed day: every stop reading is computed here even when `lod` abstains (the registration) - a side
                # stop that is usable is walked (its own trade), one that abstains is its own abstain row (0R)
                readings = {sv: r_ for sv, r_ in h60_stop_readings(ent, c.get("base_low"), adr20).items() if sv != H60_STOP}
            else:
                all_ = h60_stop_readings(ent, c.get("base_low"), adr20)
                readings = all_ if v == H60_ENTRY else {H60_STOP: all_[H60_STOP]}
            walk_from, mb_v = ent["walk_from"], mb
        common = {**base, "fill_minute": ent["fill_minute"], "fill": ent["fill"], "level": ent["level"], "fill_le_line": int(ent["fill"] <= pivot)}
        for sv, s in readings.items():
            if s["reason"]:
                rows.append(_by_cols({**common, "stop_variant": sv, "stop": s["stop"], "width_pct": s["width_pct"], "status": "abstain",
                                      "abstain_reason": s["reason"]}, H60_TRADE_COLS))
                tally[(v, sv, "abstain", s["reason"])] += 1
                continue
            fwd, cut, res = h60_walk(ent, mb_v, bars, cidx, e, adr20, s["stop"], s["width_pct"], walk_from)
            tally[(v, sv, "filled", "")] += 1
            for name, (a, (kind, sess, _tn)) in res.items():
                rows.append(_by_cols({**common, "stop_variant": sv, "stop": s["stop"], "width_pct": s["width_pct"], "width_adr": s["width_pct"] / adr20,
                                      "abstain_reason": "", "arm": name, "status": a["status"], "realized_r": a["realized_r"], "pnl_adr": a["pnl_adr"],
                                      "acct_pct": a["acct_pct"], "sessions_held": a["sessions_held"], "mature": int(a["mature"]),
                                      "open_mark": int(a["open_mark"]), "fill_day_stop": int(a["status"] == "stopped_day0"), "partial_kind": kind,
                                      "partial_session": sess, "beabove": a["beabove"], "fwd_bars": len(fwd), "fwd_hole": int(cut)}, H60_TRADE_COLS))
    return rows, tally


def _h60_exit_job(date_iso: str) -> tuple:
    D: Daily = _G["D"]
    cands = _G["by_date"][date_iso]
    todo = [(c, sorted(v for v, tag in _G["pick"].get((c["ticker"], c["E"], c["K"]), {}).items() if tag == "trade")) for c in cands]
    todo = [(c, vs) for c, vs in todo if vs]
    if not todo:
        return rows_to_gz([]), Counter()
    blocks, _info = read_minute_file(_G["files"][date_iso], {c["ticker"] for c, _v in todo})
    done, cal = _G["done"], D.cal
    rows, tally = [], Counter()
    for c, vs in todo:
        mb, _state = minutes_for(blocks, done, date_iso, c["ticker"])
        bars, cidx = _ticker_bars(c["ticker"])
        e = locate_breakout_index(cal, cidx, c["E"])
        r, t = h60_exit_rows(c, vs, mb, bars, cidx, e, _G["period"])
        rows.extend(r)
        tally.update(t)
    return rows_to_gz(rows), tally


def h60_exits(bases: dict, inp: dict, pick: dict, D: "Daily", workers: int, period: str, out: Path, say) -> tuple:
    """Walk the chosen trades -> `trades_<period>_h60.tsv.gz` (the `.partial` protocol). Returns (path, tally)."""
    t = time.time()
    _G.update(D=D, by_date=inp["by_date"], files=inp["files"], done=inp["done"], pick=pick, period=period, bars_cache={})
    tp = out / f"trades_{period}_h60.tsv.gz"
    tpp = partial_path(tp)
    tally: Counter = Counter()
    dates = list(inp["by_date"])
    n = 0
    with open(tpp, "wb") as tf:
        tf.write(rows_to_gz([H60_TRADE_COLS]))
        for k, (tg, ty) in enumerate(_pool_map(_h60_exit_job, dates, workers), 1):
            tf.write(tg)
            tally.update(ty)
            n += sum(ty.values())
            if k % 100 == 0 or k == len(dates):
                print(f"  {k}/{len(dates)} dates, {n:,} entries walked or abstained", flush=True)
    os.replace(tpp, tp)
    say(f"[h60 exits: {time.time() - t:.0f}s]")
    return tp, tally


# ── the ORH5 twin: the pinned P5 population re-walked, equal in content to the pinned table ─────────────────────────────────────
def h60_twin_inputs(args, dirs: dict, period: str) -> dict:
    """The P5 population of the period, exactly as `p5` / `holdout` / `pre-read` build it."""
    d = h60_period_dir(dirs, period)
    ns = argparse.Namespace(data=str(d), out=None, minutes=None, limit_dates=0)
    if period == "pre":
        return pre_complete(pre_inputs(ns))
    return p5_inputs(ns, period)


def gz_content_sha(path: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(path, "rb") as fh:
        while True:
            b = fh.read(1 << 24)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def h60_twin_check(twin: Path, pinned: Path) -> list:
    """Check 4: the re-walked twin against the pinned P5 table - the gzip CONTENT equal (every row, every column), else the per-row
    differences in status / mature / realized R (1e-9) / the abstain rows are named. A missing pinned table is a problem."""
    if not pinned.exists():
        return [f"pinned twin {pinned} not found"]
    if gz_content_sha(twin) == gz_content_sha(pinned):
        return []
    cols = ["ticker", "D", "K", "stop_variant", "abstain_reason", "arm", "status", "realized_r", "mature"]
    a = read_tsv(twin, usecols=cols)
    b = read_tsv(pinned, usecols=cols)
    keys = ["ticker", "D", "K", "stop_variant", "arm"]
    for df in (a, b):
        df["arm"] = df["arm"].fillna("")
    j = a.merge(b, on=keys, how="outer", suffixes=("", "_ref"), indicator=True)
    problems = [f"content differs (sha {gz_content_sha(twin)[:12]} vs pinned {gz_content_sha(pinned)[:12]})"]
    for side, label in (("left_only", "re-walk only"), ("right_only", "pinned table only")):
        n = int((j["_merge"] == side).sum())
        if n:
            problems.append(f"{n:,} rows in the {label}")
    both = j[j["_merge"] == "both"]
    if len(both):
        for col, what in (("status", "status"), ("mature", "mature"), ("abstain_reason", "abstain_reason")):
            n = int((both[col].fillna("") != both[col + "_ref"].fillna("")).sum())
            if n:
                problems.append(f"{n:,} of {len(both):,} paired rows differ in {what}")
        r = both[["realized_r", "realized_r_ref"]].to_numpy(dtype=float)
        n = int(((np.abs(r[:, 0] - r[:, 1]) > P5_XCHECK_TOL) & ~(np.isnan(r[:, 0]) & np.isnan(r[:, 1]))).sum())
        if n:
            problems.append(f"{n:,} of {len(both):,} paired rows differ in realized_r")
    return problems


# ── the pairs table (one row per base, both sides) ─────────────────────────────────────────────────────────────────────────────
def h60_load_twin_side(twin: Path) -> dict:
    """{(ticker, D, K): {fill, r, adr, mature, open}} of the twin's primary-arm rows (ORH5 filled first breaks)."""
    df = read_tsv(twin, usecols=["ticker", "D", "K", "arm", "fill", "realized_r", "pnl_adr", "mature"])
    df = df[df["arm"] == H60_ARM]
    return {(t, d, k): {"fill": f, "r": r, "adr": a, "mature": int(m), "open": int(not m)}
            for t, d, k, f, r, a, m in df[["ticker", "D", "K", "fill", "realized_r", "pnl_adr", "mature"]].itertuples(index=False)}


def h60_load_trade_side(trades: Path) -> dict:
    """{(ticker, E, K, entry, stop): {status "filled", fill, fill_minute, r, adr, mature, open} | {status "abstain", reason}} of the h60
    table: the primary-arm rows (a walked trade) and the abstain rows (a stop reading that could not be taken), so every side's status is
    read off ITS OWN rows."""
    df = read_tsv(trades, usecols=["ticker", "E", "K", "entry", "stop_variant", "arm", "abstain_reason", "fill", "fill_minute",
                                  "realized_r", "pnl_adr", "mature"])
    out = {}
    for t, e, k, v, sv, reason in df[df["arm"].isna()][["ticker", "E", "K", "entry", "stop_variant", "abstain_reason"]].itertuples(index=False):
        out[(t, e, k, v, sv)] = {"status": "abstain", "reason": ("" if reason != reason else str(reason))}
    for t, e, k, v, sv, f, fm, r, a, m in df[df["arm"] == H60_ARM][["ticker", "E", "K", "entry", "stop_variant", "fill", "fill_minute", "realized_r",
                                                                      "pnl_adr", "mature"]].itertuples(index=False):
        out[(t, e, k, v, sv)] = {"status": "filled", "fill": f, "fill_minute": fm, "r": r, "adr": a, "mature": int(m), "open": int(not m)}
    return out


def _h60_side(side: "dict | None", fallback: str) -> dict:
    """One side of a pair from its trade-side record: a walked trade carries its R; an abstain or a missing record is no trade (0R)."""
    if side is not None and side["status"] == "filled":
        return {"status": "filled", "fill": side["fill"], "fill_minute": side["fill_minute"], "r": side["r"], "adr": side["adr"],
                "mature": side["mature"], "open": side["open"]}
    return {"status": (side["reason"] or "abstain") if side is not None else fallback, "fill": None, "fill_minute": None, "r": 0.0, "adr": 0.0,
            "mature": "", "open": 0}


def h60_pair_rows(bases: dict, facts: dict, pick: dict, twin_side: dict, trade_side: dict, period: str) -> list:
    rows = []
    for key, rs in bases.items():
        first = rs[0]
        t, pole, k = key
        f5 = facts[(t, first["E"], k)]["orh5"]
        orh = twin_side.get((t, first["D"], k))
        row = {"ticker": t, "pole_date": pole, "K": k, "base": first["base"], "period": period, "first_D": first["D"], "first_E": first["E"], "first_month": first["first_month"],
               "first_year": int(first["E"][:4]), "n_rows": len(rs),
               "orh5_status": f5["status"], "orh5_reason": f5["reason"] or "",
               "orh5_data_abstain": int(f5["status"] == "abstain" and f5["reason"] in DATA_ABSTAINS),
               "orh5_fill": orh["fill"] if orh else None, "orh5_r": (orh["r"] if orh else 0.0), "orh5_adr": (orh["adr"] if orh else 0.0),
               "orh5_mature": (orh["mature"] if orh else ""), "orh5_open": (orh["open"] if orh else 0)}
        for cell in CELL_COLS:
            row[cell] = int(first["_first"][cell])
        st, reason, r60 = h60_base_outcome(rs, facts, pick, "h60")
        side = _h60_side(trade_side.get((t, r60["E"], k, "h60", "lod")) if r60 is not None else None, st)
        row.update(h60_status=st, h60_reason=reason or "", h60_E=(r60["E"] if r60 is not None else ""), h60_row_no=(r60["row_no"] if r60 is not None else ""),
                   h60_fill=side["fill"], h60_fill_minute=side["fill_minute"], h60_r=side["r"], h60_adr=side["adr"], h60_mature=side["mature"],
                   h60_open=side["open"], h60_same_day=(int(r60["row_no"] == 0) if r60 is not None else ""),
                   h60_gap_kind=(r60["gap_kind"] if r60 is not None else ""), own_C1=(int(bool(r60["C1"])) if r60 is not None else ""))
        stf, _rf, rf = h60_base_outcome(rs, facts, pick, "h60_first")
        sf = _h60_side(trade_side.get((t, rf["E"], k, "h60_first", "lod")) if rf is not None else None, stf)
        row.update(h60_first_status=stf, h60_first_r=sf["r"], h60_first_mature=sf["mature"], h60_first_open=sf["open"])
        # the stop candidate on the PRIMARY's confirmed day, from its OWN rows (walked, or its own abstain); no confirmed day = no trade
        cb_ = _h60_side(trade_side.get((t, r60["E"], k, "h60", "cbar_low")) if r60 is not None else None, st)
        row.update(cbar_status=cb_["status"], cbar_r=cb_["r"], cbar_adr=cb_["adr"], cbar_mature=cb_["mature"], cbar_open=cb_["open"])
        rows.append(row)
    return rows


# ── the report: statistics, the bars, the paired bars, the consequence ─────────────────────────────────────────────────────────
def h60_stats(g, key: str, ci: bool = True) -> dict:
    """The per-group statistics over the MATURE walks of a frame of primary-arm rows (`n_filled` = every walk, `n_open` the open marks):
    the registration's columns. The interval: `block_bootstrap_ci` on the FILL month (2,000 draws, seed 702, stream keyed on `key`)."""
    gm = g[g["mature"] == 1]
    r = gm["realized_r"].to_numpy(dtype=float)
    n = len(r)
    out = {"n_filled": int(len(g)), "n": n, "n_open": int(len(g) - n)}
    if n == 0:
        return out
    srt = np.sort(r)[::-1]
    k_top = max(1, int(np.ceil(H60_TOP_SHARE * n)))
    wins, losses = r[r > 0], r[r <= 0]
    tail = gm[(gm["realized_r"] >= H60_TAIL_R)]
    tail_w = tail[tail["width_adr"] >= H60_TAIL_WIDTH_ADR]
    out.update(mean_r=float(r.mean()), median_r=float(np.median(r)), win_rate=float((r > 0).mean()),
               avg_win=(float(wins.mean()) if len(wins) else None), avg_loss=(float(losses.mean()) if len(losses) else None),
               share_ge5=float((r >= 5).mean()), share_ge10=float((r >= 10).mean()), share_ge20=float((r >= 20).mean()), sum_r=float(r.sum()),
               top2_sum_r=float(srt[:k_top].sum()), top2_share=(float(srt[:k_top].sum() / r.sum()) if r.sum() != 0 else None),
               mean_pnl_adr=float(gm["pnl_adr"].to_numpy(dtype=float).mean()), mean_acct_pct=float(gm["acct_pct"].to_numpy(dtype=float).mean()),
               fill_day_stop_share=float(gm["fill_day_stop"].to_numpy(dtype=float).mean()),
               median_held=float(np.median(gm["sessions_held"].to_numpy(dtype=float))),
               tail_n=int(len(tail_w)), tail_tickers=int(tail_w["ticker"].nunique()), tail_months=int(tail_w["fill_month"].nunique()),
               tail_n_nowidth=int(len(tail)), tail_tickers_nowidth=int(tail["ticker"].nunique()), tail_months_nowidth=int(tail["fill_month"].nunique()))
    if ci and n >= 2:
        out["ci_lo"], out["ci_hi"] = block_bootstrap_ci(r, gm["fill_month"].astype(str).to_numpy(), key=key)
    return out


def h60_verdict(row: dict, base: "dict | None", min_n: int = H60_MIN_N) -> tuple:
    """(verdict, why) on the registration's bars, n first. PASS = n >= 30 AND the interval's lower end > 0 AND ADR P&L > 0 AND beats C0 on
    mean R AND on the >= 5R share AND the >= 10R trades (stop >= 0.25 ADR20 wide) come from >= 3 tickers AND >= 3 fill months. FAIL = n >= 30
    AND (upper end < 0 OR not above C0 on mean R). Else CAN'T TELL; when the tail is the ONLY miss: "CAN'T TELL (positive, no tail)"."""
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
    if not (_num_ok(row.get("mean_pnl_adr")) and row["mean_pnl_adr"] > 0):
        unmet.append("ADR P&L <= 0")
    if not (_num_ok(row.get("share_ge5")) and _num_ok(base.get("share_ge5")) and row["share_ge5"] > base["share_ge5"]):
        unmet.append("does not beat C0's >= 5R share")
    tail_ok = int(row.get("tail_tickers") or 0) >= H60_TAIL_TICKERS and int(row.get("tail_months") or 0) >= H60_TAIL_MONTHS
    if not tail_ok:
        unmet.append(f">= 10R trades from {row.get('tail_tickers') or 0} tickers / {row.get('tail_months') or 0} months (need {H60_TAIL_TICKERS} / {H60_TAIL_MONTHS})")
    if not unmet:
        return "PASS", "every bar met"
    if len(unmet) == 1 and not tail_ok:
        return "CAN'T TELL (positive, no tail)", unmet[0]
    return "CAN'T TELL", "; ".join(unmet)


def h60_pair_ci(deltas, months, key: str) -> dict:
    """The month-block interval of a paired delta (blocks = the first break's month)."""
    d = np.asarray(deltas, dtype=float)
    out = {"n": int(len(d)), "mean": (float(d.mean()) if len(d) else None)}
    if len(d) >= 2:
        out["lo"], out["hi"] = block_bootstrap_ci(d, np.asarray(months).astype(str), key=key)
    return out


def h60_pair_verdict(ci: dict, min_n: int = H60_PAIR_MIN_N) -> str:
    """win | loss | can't tell | n < 30 on a paired entry interval."""
    if ci["n"] < min_n:
        return f"can't tell (n = {ci['n']} < {min_n})"
    lo, hi = ci.get("lo"), ci.get("hi")
    if _num_ok(lo) and lo > 0:
        return "win"
    if _num_ok(hi) and hi < 0:
        return "loss"
    return "can't tell"


def h60_stop_verdict(ci: dict, adr_delta: "float | None", min_n: int = H60_PAIR_MIN_N) -> str:
    """`cbar_low` is carried forward when its paired R interval's lower end > 0 AND its ADR P&L delta > 0; else `lod` stays."""
    if ci["n"] >= min_n and _num_ok(ci.get("lo")) and ci["lo"] > 0 and _num_ok(adr_delta) and adr_delta > 0:
        return H60_STOP_CANDIDATE
    return H60_STOP


def h60_consequence(verdict: str, pair: str, c0_pair_lo) -> str:
    """The registration's consequence table, cell by cell."""
    v = "PASS" if verdict == "PASS" else ("FAIL" if verdict == "FAIL" else "CAN'T TELL")
    p = pair if pair in ("win", "loss") else "can't tell"
    if v == "PASS":
        return {"win": "RECORD; next tests under h60",
                "can't tell": "RECORD; next tests under h60; 'not separated from ORH5 on the same bases' is reported",
                "loss": "LEAD only (recorded, no claim: ORH5 made more on the same bases); next tests under ORH5"}[p]
    if v == "CAN'T TELL":
        if p == "win":
            return "LEAD (recorded); next tests under h60"
        if p == "can't tell":
            lead = _num_ok(c0_pair_lo) and c0_pair_lo > 0
            return (f"LEAD only because the C0 paired interval's lower end > 0 ({c0_pair_lo:+.3f}); next tests under ORH5" if lead else
                    f"not recorded (the C0 paired interval's lower end is {('%+.3f' % c0_pair_lo) if _num_ok(c0_pair_lo) else 'unknown'}, not > 0); next tests under ORH5")
        return "not recorded; next tests under ORH5"
    return {"win": "not recorded; 'loses less than ORH5' reported; next tests under ORH5"}.get(p, "not recorded; next tests under ORH5")


def h60_sign(x) -> str:
    return "unknown" if not _num_ok(x) else ("positive" if x > 0 else ("negative" if x < 0 else "zero"))


H60_SLICES = (("year", "year"), ("phase", "phase_qqq_10_20"), ("gap_over_1adr", "gap_over_1adr"), ("regime", "apollo_regime"))


def h60_report_rows(df, pairs, period: str) -> tuple:
    """(rows, verdicts): every (window, cell, K, entry, stop, arm) over the mature walks with the interval ('all'), the slices on the primary
    triple, the own-C1 and no-gap restricted C1 rows, the verdict stamped on the tl / h60 / lod / primary rows; `verdicts` = {window: the
    C1 verdict row and the paired results}."""
    import pandas as pd
    rows: list = []
    verdicts: dict = {}
    for wname, years in h60_windows_of(period):
        sub = df if years is None else df[df["year_first"].isin(years)]
        psub = pairs if years is None else pairs[pairs["first_year"].isin(years)]
        arm_rows = sub[sub["arm"].notna()]
        idx: dict = {}
        for (k, v, sv, a), g in arm_rows.groupby(["K", "entry", "stop_variant", "arm"], observed=True):
            for cell in CELL_COLS:
                gc = g[g[cell] == 1]
                if not len(gc):
                    continue
                ab = sub[(sub["K"] == k) & (sub["entry"] == v) & (sub["stop_variant"] == sv) & sub["arm"].isna() & (sub[cell] == 1)]
                s = h60_stats(gc, key=f"h60|{period}|{wname}|{cell}|{k}|{v}|{sv}|{a}")
                r = {"period": period, "window": wname, "cell": cell, "K": k, "entry": v, "stop": sv, "arm": a, "slice": "all", "value": "",
                     **s, "too_wide": int((ab["abstain_reason"] == "too_wide").sum()),
                     "stop_abstain": int((ab["abstain_reason"] == "stop_at_or_above_fill").sum())}
                idx[(cell, k, v, sv, a)] = r
                rows.append(r)
                if (k, v, sv, a) == (H60_LEVEL, H60_ENTRY, H60_STOP, H60_ARM):
                    gm = gc[gc["mature"] == 1]
                    for sname, scol in H60_SLICES:
                        if sname == "regime" and period != "holdout":
                            continue
                        for val, gg in gm.groupby(scol, observed=True):
                            rows.append({"period": period, "window": wname, "cell": cell, "K": k, "entry": v, "stop": sv, "arm": a, "slice": sname,
                                         "value": val, **h60_stats(gg, key="", ci=False)})
                    if cell == "C1":
                        for sname, mask in (("own_C1", gc["own_C1"] == 1), ("no_gap", gc["gap_kind"] == "")):
                            gg = gc[mask]
                            rows.append({"period": period, "window": wname, "cell": cell, "K": k, "entry": v, "stop": sv, "arm": a, "slice": sname,
                                         "value": "", **h60_stats(gg, key=f"h60|{period}|{wname}|{cell}|{k}|{v}|{sv}|{a}|{sname}")})
        # never confirmed / data abstains per cell (from the pairs table) on the primary rows
        for cell in CELL_COLS:
            pc = psub[(psub["K"] == H60_LEVEL) & (psub[cell] == 1)]
            r = idx.get((cell, H60_LEVEL, H60_ENTRY, H60_STOP, H60_ARM))
            if r is None and len(pc):
                r = {"period": period, "window": wname, "cell": cell, "K": H60_LEVEL, "entry": H60_ENTRY, "stop": H60_STOP, "arm": H60_ARM, "slice": "all",
                     "value": "", "n_filled": 0, "n": 0, "n_open": 0, "too_wide": int((pc["h60_status"] == "too_wide").sum()),
                     "stop_abstain": int((pc["h60_status"] == "stop_at_or_above_fill").sum())}
                idx[(cell, H60_LEVEL, H60_ENTRY, H60_STOP, H60_ARM)] = r
                rows.append(r)
            if r is not None:
                r["never_confirmed"] = int((pc["h60_status"] == "never_confirmed").sum())
                r["data_abstain"] = int((pc["h60_reason"] == "data_only").sum())
        base = idx.get(("C0", H60_LEVEL, H60_ENTRY, H60_STOP, H60_ARM))
        for cell in CELL_COLS:
            r = idx.get((cell, H60_LEVEL, H60_ENTRY, H60_STOP, H60_ARM))
            if r is None:
                continue
            if cell == "C0":
                r["verdict"], r["why"] = "baseline", ""
            elif cell in PRE_DECIDING:
                r["verdict"], r["why"] = h60_verdict(r, base)
            else:
                r["verdict"], r["why"] = "report", ""
        # the paired bars
        pv: dict = {}
        for cell in ("C1", "C0"):
            pc = psub[(psub["K"] == H60_LEVEL) & (psub[cell] == 1)]
            keep = pc[(pc["orh5_data_abstain"] == 0) & (pc["orh5_open"] == 0) & (pc["h60_open"] == 0)]
            traded = keep[(keep["orh5_status"] == "filled") | (keep["h60_status"] == "filled")]
            d = traded["h60_r"].to_numpy(dtype=float) - traded["orh5_r"].to_numpy(dtype=float)
            ci = h60_pair_ci(d, traded["first_month"], key=f"h60pair|{period}|{wname}|{cell}|entry")
            same = traded[(traded["h60_same_day"] == 1) & (traded["h60_status"] == "filled") & (traded["orh5_status"] == "filled")]
            later = traded[(traded["h60_same_day"] == 0) & (traded["h60_status"] == "filled")]
            first_abst = keep[(keep["h60_same_day"] == 1) & keep["h60_status"].isin(("too_wide", "stop_at_or_above_fill"))]
            never = keep[(keep["orh5_status"] == "filled") & (keep["h60_status"] == "never_confirmed")]
            kf = keep[(keep["h60_first_open"] == 0)]
            tf = kf[(kf["orh5_status"] == "filled") | (kf["h60_first_status"] == "filled")]
            df_ = tf["h60_first_r"].to_numpy(dtype=float) - tf["orh5_r"].to_numpy(dtype=float)
            ci_f = h60_pair_ci(df_, tf["first_month"], key=f"h60pair|{period}|{wname}|{cell}|entry_first")
            same_f = same                                                                  # both sides filled the same day
            above = same_f[same_f["h60_fill"].astype(float) > same_f["orh5_fill"].astype(float)]
            pv[cell] = {"n": ci["n"], "mean": ci["mean"], "lo": ci.get("lo"), "hi": ci.get("hi"), "verdict": h60_pair_verdict(ci),
                        "excluded_open": int(((pc["orh5_open"] == 1) | (pc["h60_open"] == 1)).sum()),
                        "excluded_data": int((pc["orh5_data_abstain"] == 1).sum()),
                        "same_day_n": int(len(same)), "same_day_mean": (float((same["h60_r"] - same["orh5_r"]).mean()) if len(same) else None),
                        "first_day_abstain_n": int(len(first_abst)),
                        "later_n": int(len(later)), "later_mean": (float((later["h60_r"] - later["orh5_r"]).mean()) if len(later) else None),
                        "never_n": int(len(never)), "never_orh5_mean": (float(never["orh5_r"].mean()) if len(never) else None),
                        "share_orh5": (float((keep["orh5_status"] == "filled").mean()) if len(keep) else None),
                        "share_h60": (float((keep["h60_status"] == "filled").mean()) if len(keep) else None),
                        "first_n": ci_f["n"], "first_mean": ci_f["mean"], "first_lo": ci_f.get("lo"), "first_hi": ci_f.get("hi"),
                        "first_verdict": h60_pair_verdict(ci_f),
                        "ge5_orh5": int((traded["orh5_r"] >= 5).sum()), "ge5_h60": int((traded["h60_r"] >= 5).sum()),
                        "ge5_both": int(((traded["orh5_r"] >= 5) & (traded["h60_r"] >= 5)).sum()),
                        "ge10_orh5": int((traded["orh5_r"] >= 10).sum()), "ge10_h60": int((traded["h60_r"] >= 10).sum()),
                        "ge10_both": int(((traded["orh5_r"] >= 10) & (traded["h60_r"] >= 10)).sum()),
                        "same_day_fill_n": int(len(same_f)), "same_day_fill_above": int(len(above)),
                        "same_day_fill_median_ratio": (float(np.median(same_f["h60_fill"].astype(float) / same_f["orh5_fill"].astype(float))) if len(same_f) else None)}
            # the paired stop (under h60): cbar_low - lod per base on the PRIMARY's confirmed day (filled or abstained on either stop; a side
            # that abstained is 0R), the entry pair's exclusions, bases with a trade on at least one side
            ps = pc[pc["h60_status"].isin(H60_CONSUMING) & (pc["h60_open"] == 0) & (pc["cbar_open"] == 0) & (pc["orh5_data_abstain"] == 0)]
            pst = ps[(ps["h60_status"] == "filled") | (ps["cbar_status"] == "filled")]
            ds = pst["cbar_r"].to_numpy(dtype=float) - pst["h60_r"].to_numpy(dtype=float)
            cis = h60_pair_ci(ds, pst["first_month"], key=f"h60pair|{period}|{wname}|{cell}|stop")
            adr_d = float((pst["cbar_adr"].to_numpy(dtype=float) - pst["h60_adr"].to_numpy(dtype=float)).mean()) if len(pst) else None
            pv[cell]["stop"] = {"n": cis["n"], "mean": cis["mean"], "lo": cis.get("lo"), "hi": cis.get("hi"), "adr_delta": adr_d,
                                "carry": h60_stop_verdict(cis, adr_d),
                                "cbar_abstain": int(ps["cbar_status"].isin(("too_wide", "stop_at_or_above_fill")).sum()),
                                "lod_abstain": int(ps["h60_status"].isin(("too_wide", "stop_at_or_above_fill")).sum())}
        c1 = idx.get(("C1", H60_LEVEL, H60_ENTRY, H60_STOP, H60_ARM)) or {"n": 0, "verdict": "CAN'T TELL", "why": "n = 0 < 30"}
        verdicts[wname] = {"c1": c1, "c0": base, "pairs": pv, "idx": idx}
    return rows, verdicts


def _h60_line(r: dict, first) -> list:
    g = r.get
    return [first, g("n_filled", 0), g("n", 0), g("n_open", 0), _num(g("mean_r")), _ci(r), _pct(g("win_rate")), _num(g("avg_win"), 2), _num(g("avg_loss"), 2),
            "" if g("share_ge5") is None else f"{100 * g('share_ge5'):.1f}", "" if g("share_ge10") is None else f"{100 * g('share_ge10'):.1f}",
            "" if g("share_ge20") is None else f"{100 * g('share_ge20'):.1f}", _num(g("sum_r"), 1), _num(g("mean_pnl_adr")), _num(g("mean_acct_pct"), 4),
            _pct(g("fill_day_stop_share")), "" if g("median_held") is None else f"{g('median_held'):.0f}",
            "" if g("tail_n") is None else f"{g('tail_n')}: {g('tail_tickers')}t/{g('tail_months')}m ({g('tail_n_nowidth')} no width rule)",
            _pct(g("top2_share")), g("too_wide", 0), g("stop_abstain", 0), g("never_confirmed", ""), g("verdict", ""), g("why", "")]


H60_HEADER = ["cell", "fills", "n", "open", "mean R", "95% CI", "win", "avg win", "avg loss", ">=5R/100", ">=10R/100", ">=20R/100", "total R",
              "pnl_adr", "acct%", "fill-day stop", "med held", ">=10R spread", "top-2% share", "too_wide", "saaf", "never", "VERDICT", "why"]


def h60_report_text(period: str, rows: list, verdicts: dict, notes: list, twin_c0: "dict | None", stamps: list, df) -> str:
    out: list = []
    A = out.append
    decides = period == "discovery"
    A(f"#702 h60 - the HOURLY-CLOSE entry read on {period} ({'2022-03-28..2024-12-31, DECIDES' if decides else ('2017-21, beside (and 2020-21 alone)' if period == 'pre' else '2025-01..2026-10, descriptive only')}). "
      f"Registered before any outcome: docs/analysis/{H60_DOC}. Measurement only: nothing here switches the deciding entry, a stop outside the stop bar, "
      f"a cell, a period, the horizon, the n floor, the seed or the draw count.")
    A(f"POPULATION: every row under the pole (spec key, rule (b)); the base's ONE trade = the first break day on which a 60-minute bar closed above the "
      f"row's line and the next minute's open could fill; cell + period from the FIRST-break row, the day's facts from the CONFIRMING row. Entry h60, stop "
      f"lod (the day's low through the bar's end), exit {H60_ARM} (sell 1/3 at +2R or the session-3 close, breakeven, 20-day trail, stallers cut at the "
      f"session-3 close), level tl (decides) / com (beside). A group is the MATURE walks only; an open mark is counted, never in a number.")
    A(f"INTERVAL RECIPE (check 6 reproduces it with no runner code): month-block bootstrap of the mean - blocks = calendar months (the FILL month for a "
      f"cell's trades; the FIRST-break month for a paired delta), 2,000 resamples of as many blocks as there are months, with replacement, each resample's "
      f"mean = sum of the drawn blocks' R / their trade count; the 2.5 / 97.5 percentiles (numpy.percentile, linear); generator "
      f"numpy.random.default_rng([702, zlib.crc32(key)]) with key 'h60|<period>|<window>|<cell>|<K>|<entry>|<stop>|<arm>' for a cell and "
      f"'h60pair|<period>|<window>|<cell>|entry' / '|entry_first' / '|stop' for the paired deltas (the stream is drawn as integers(0, n_months, size=(2000, n_months))).")
    for n_ in notes:
        A(n_)
    A("")
    for wname, years in h60_windows_of(period):
        v = verdicts.get(wname)
        if v is None:
            continue
        idx, c1, pv = v["idx"], v["c1"], v["pairs"]
        A(f"========== WINDOW {wname}{'' if years is None else ' (first-break E in ' + '/'.join(map(str, years)) + ')'} ==========")
        # expectations first
        c0 = idx.get(("C0", H60_LEVEL, H60_ENTRY, H60_STOP, H60_ARM)) or {}
        exp = []
        fds = c0.get("fill_day_stop_share")
        exp.append(("MET" if _num_ok(fds) and fds < H60_EXPECT_FILL_DAY_STOP else "MISSED") +
                   f": the C0 share stopped on the fill day under h60 reads {_pct(fds)} (expected < {H60_EXPECT_FILL_DAY_STOP:.0%}; ORH5 ~ 35%)")
        if decides:
            n1 = int(c1.get("n") or 0)
            exp.append(("MET" if H60_EXPECT_C1_N[0] <= n1 <= H60_EXPECT_C1_N[1] else "MISSED") + f": C1 n reads {n1} (expected {H60_EXPECT_C1_N[0]}-{H60_EXPECT_C1_N[1]})")
        p1 = pv.get("C1", {})
        sd_n, sd_ab, sd_ratio = p1.get("same_day_fill_n", 0), p1.get("same_day_fill_above", 0), p1.get("same_day_fill_median_ratio")
        exp.append(("MET" if sd_n and _num_ok(sd_ratio) and sd_ratio > 1.0 else ("MISSED" if sd_n else "NO SAME-DAY PAIR")) +
                   f": on the {sd_n} same-day C1 pairs the h60 fill sits above ORH5's on {sd_ab} (median fill ratio {('%.4f' % sd_ratio) if _num_ok(sd_ratio) else '-'}; "
                   f"the reading chosen for 'sits above': the MEDIAN pair's h60 fill is above ORH5's)")
        if twin_c0 is not None and years is None:
            m, w, t10 = twin_c0.get("mean_r"), twin_c0.get("win_rate"), twin_c0.get("share_ge10")
            exp.append(f"ORH5 C0 BASELINE from the twin: mean R {_num(m, 2)}, win {_pct(w)}, >= 10R {('%.1f' % (100 * t10)) if _num_ok(t10) else '-'} per 100 "
                       f"(the registration's numbers: {H60_EXPECT_ORH5_C0[0]:+.2f}R, {H60_EXPECT_ORH5_C0[1]:.0%}, {H60_EXPECT_ORH5_C0[2]} per 100 on discovery)")
        missed = [e for e in exp if e.startswith("MISSED")]
        A("EXPECTATIONS (fixed before the run; a missed one is reported first and changes NO rule):")
        for e in missed + [e for e in exp if not e.startswith("MISSED")]:
            A("  " + e)
        A("")
        A(f"VERDICT TABLE - level {H60_LEVEL}, entry {H60_ENTRY}, stop {H60_STOP}, arm {H60_ARM}, SPEC key, mature walks (C1 decides on 2022-24; every other row "
          f"is its own population; the >= 10R spread counts trades whose stop is >= {H60_TAIL_WIDTH_ADR} ADR20 wide: tickers/months)")
        body = [_h60_line(idx[(cell, H60_LEVEL, H60_ENTRY, H60_STOP, H60_ARM)], cell) for cell in PRE_CELL_ORDER if (cell, H60_LEVEL, H60_ENTRY, H60_STOP, H60_ARM) in idx]
        A(table(body, H60_HEADER))
        tail2 = c1.get("tail_tickers_nowidth"), c1.get("tail_months_nowidth")
        A(f"  C1 >= 10R spread, the 2-and-2 reading (beside): {'met' if int(c1.get('tail_tickers') or 0) >= 2 and int(c1.get('tail_months') or 0) >= 2 else 'not met'} "
          f"with the width rule; without it {tail2[0]} tickers / {tail2[1]} months")
        for sname, label in (("own_C1", "C1 restricted to confirmations whose OWN watch night still passed C1 (his regime caution)"),
                             ("no_gap", "C1 restricted to confirmations with no absent / no-line night since the first break")):
            rr = [r for r in rows if r["window"] == wname and r["cell"] == "C1" and r["slice"] == sname and r["K"] == H60_LEVEL and r["entry"] == H60_ENTRY and r["stop"] == H60_STOP and r["arm"] == H60_ARM]
            if rr:
                r = dict(rr[0])
                r["verdict"], r["why"] = h60_verdict(r, c0 if c0.get("n") else None)
                A(f"  {label}:")
                A(table([_h60_line(r, "C1*")], H60_HEADER))
        A("")
        A("PAIRED ENTRY BAR - per base delta = R(h60) - R(ORH5), no trade = 0R; excluded: an open mark on either side, an ORH5 first break that was a data abstain; "
          "month-block interval on the FIRST-break month; C1 decides, C0 = the mechanism at scale")
        body = []
        for cell in ("C1", "C0"):
            p = pv.get(cell)
            if p is None:
                continue
            body.append([cell, p["n"], _num(p["mean"]), _ci({"ci_lo": p.get("lo"), "ci_hi": p.get("hi")}), p["verdict"], p["excluded_open"], p["excluded_data"],
                         f"{p['same_day_n']} / {_num(p['same_day_mean'], 2)}", p["first_day_abstain_n"], f"{p['later_n']} / {_num(p['later_mean'], 2)}",
                         f"{p['never_n']} / {_num(p['never_orh5_mean'], 2)}", f"{_pct(p['share_orh5'])} / {_pct(p['share_h60'])}",
                         f"{p['first_n']} / {_num(p['first_mean'])} {_ci({'ci_lo': p.get('first_lo'), 'ci_hi': p.get('first_hi')})} {p['first_verdict']}",
                         f"{p['ge5_orh5']} / {p['ge5_h60']} / {p['ge5_both']}", f"{p['ge10_orh5']} / {p['ge10_h60']} / {p['ge10_both']}"])
        A(table(body, ["cell", "n bases", "mean delta", "95% CI", "paired verdict", "excl open", "excl ORH5 data", "same day (both filled): n / delta",
                       "first-day abstains", "later row: n / delta",
                       "h60 never: n / ORH5 R", "traded by ORH5 / h60", "h60_first delta", ">=5R ORH5 / h60 / both", ">=10R ORH5 / h60 / both"]))
        A("")
        A(f"PAIRED STOP BAR (under h60) - delta = R({H60_STOP_CANDIDATE}) - R({H60_STOP}) per base on the primary's confirmed day (a stop that abstained there = 0R; "
          f"the entry bar's exclusions; bases with a trade on at least one side); carried forward only when the interval's lower end > 0 AND the ADR P&L delta > 0")
        body = []
        for cell in ("C1", "C0"):
            p = pv.get(cell, {}).get("stop")
            if p:
                body.append([cell, p["n"], _num(p["mean"]), _ci({"ci_lo": p.get("lo"), "ci_hi": p.get("hi")}), _num(p["adr_delta"]), p["cbar_abstain"],
                             p["lod_abstain"], p["carry"]])
        A(table(body, ["cell", "n bases", "mean delta R", "95% CI", "ADR P&L delta", "cbar_low abstains (0R)", "lod abstains (0R)", "stop carried"]))
        A("")
        if decides and years is None:
            c0p = pv.get("C0", {})
            A(f"C1 VERDICT: {c1.get('verdict')} ({c1.get('why')}); paired entry: {pv.get('C1', {}).get('verdict')}; paired stop: carry {pv.get('C1', {}).get('stop', {}).get('carry')}")
            A(f"CONSEQUENCE (the registration's table): {h60_consequence(str(c1.get('verdict')), str(pv.get('C1', {}).get('verdict')), c0p.get('lo'))}; "
              f"whatever is recorded carries the stop {pv.get('C1', {}).get('stop', {}).get('carry')}")
            A(H60_FALSE_PASS)
        else:
            A(f"STAMP (decides nothing): C1 mean R {h60_sign(c1.get('mean_r'))} ({_num(c1.get('mean_r'))}, n {c1.get('n')}), paired delta "
              f"{h60_sign(pv.get('C1', {}).get('mean'))} ({_num(pv.get('C1', {}).get('mean'))}); bars read as a label only: {c1.get('verdict')} ({c1.get('why')})")
        for s in stamps:
            A("  " + s)
        A("")
        A("BESIDE - every entry on the lod stop, the primary arm, per cell (tl); then h60 x every stop x every arm (C0 / C1); then com")
        for v_ in H60_ENTRIES:
            body = [_h60_line(idx[(cell, H60_LEVEL, v_, H60_STOP, H60_ARM)], cell) for cell in PRE_CELL_ORDER if (cell, H60_LEVEL, v_, H60_STOP, H60_ARM) in idx]
            if body:
                A(f"  entry {v_} / tl / lod / {H60_ARM}")
                A(table(body, H60_HEADER))
        for cell in ("C0", "C1"):
            body = [_h60_line(idx[(cell, H60_LEVEL, H60_ENTRY, sv, a)], f"{sv} / {a}") for sv in H60_STOPS for a in H60_ARMS if (cell, H60_LEVEL, H60_ENTRY, sv, a) in idx]
            if body:
                A(f"  {cell} / tl / h60: stop x arm")
                A(table(body, ["stop / arm"] + H60_HEADER[1:]))
        body = [_h60_line(idx[(cell, "com", H60_ENTRY, H60_STOP, H60_ARM)], cell) for cell in PRE_CELL_ORDER if (cell, "com", H60_ENTRY, H60_STOP, H60_ARM) in idx]
        if body:
            A(f"  level com / h60 / lod / {H60_ARM} (beside, never a verdict)")
            A(table(body, H60_HEADER))
        A("")
        A(f"SLICES - tl / h60 / lod / {H60_ARM}, spec key; each cell is n / mean R / share >= 5R over the mature walks (phase and gap over 1 ADR AT THE CONFIRMATION)")
        for sname, _scol in H60_SLICES:
            rr = [r for r in rows if r["window"] == wname and r["slice"] == sname and r["K"] == H60_LEVEL and r["entry"] == H60_ENTRY and r["stop"] == H60_STOP and r["arm"] == H60_ARM]
            if not rr:
                continue
            vals = sorted({r["value"] for r in rr}, key=str)
            body = []
            for cell in PRE_CELL_ORDER:
                ln = [cell]
                for val in vals:
                    m = [r for r in rr if r["cell"] == cell and r["value"] == val]
                    ln.append("-" if not m else ("0" if not m[0]["n"] else f"{m[0]['n']}/{_num(m[0].get('mean_r'), 2)}/{_pct(m[0].get('share_ge5'))}"))
                body.append(ln)
            A(f"  {sname}")
            A(table(body, ["cell"] + [str(x) for x in vals]))
        A("")
        if df is not None:
            prim = df[(df["K"] == H60_LEVEL) & (df["entry"] == H60_ENTRY) & (df["stop_variant"] == H60_STOP) & (df["arm"] == H60_ARM) & (df["mature"] == 1)]
            prim = prim if years is None else prim[prim["year_first"].isin(years)]
            for cell in ("C1", "C0"):
                g = prim[prim[cell] == 1]
                A(f"DISTRIBUTIONS {cell} (tl / h60 / lod / {H60_ARM}, mature): fill minute " + _dist([int(x) for x in g["fill_minute"].to_numpy(dtype=float)], (30, 90, 150, 210, 270, 330))
                  + "; first break -> confirmed (sessions) " + _dist([int(x) for x in g["sessions_since_first"].to_numpy(dtype=float)], (0, 1, 5, 20)))
                big = g[g["realized_r"] >= H60_TAIL_R].sort_values("realized_r", ascending=False)
                A(f"  >= 10R trades ({len(big)}): " + ("; ".join(f"{t} {e} {r:+.1f}R stop {w:.2f} ADR" for t, e, r, w in big[["ticker", "E", "realized_r", "width_adr"]].itertuples(index=False)) if len(big) else "none"))
        A("")
    return "\n".join(out)


def h60_load_frame(trades: Path, pairs: Path) -> tuple:
    """(trades frame with `year_first`, pairs frame) for the report."""
    df = read_tsv(trades)
    df["year_first"] = df["first_E"].astype(str).str[:4].astype(int)
    for col in ("K", "entry", "stop_variant", "fill_month", "first_month"):
        df[col] = df[col].astype("category")
    pf = read_tsv(pairs)
    return df, pf


# ── the guards ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def h60_frozen_files(dirs: dict, repo: Path = REPO) -> dict:
    """{footer label: path} of the h60 freeze: the data pins with the labels the registration's footer carries, the code pins (the module,
    this runner incl. the h60 code, constants.py, exit_logic.py), the two daily exports and the two minute trees. The doc body is hashed by
    `freeze_check`."""
    d, p = Path(dirs["cb702"]), Path(dirs["cb702_pre"])
    out = {"module": Path(repo) / MODULE_REL, "runner": Path(__file__).resolve(),
           "code/constants.py": Path(repo) / FROZEN_CODE["code/constants.py"], "code/exit_logic.py": Path(repo) / FROZEN_CODE["code/exit_logic.py"],
           "cb702/daily_closes_all.csv.gz": d / "daily_closes_all.csv.gz",            # every walked R is read off these two exports
           "cb702_pre/daily_closes_all.csv.gz": p / "daily_closes_all.csv.gz"}
    for name in ("candidates.tsv", "candidates_com_comb.tsv", "watch.tsv.gz", "watch_com_comb.tsv.gz", "trades_discovery_p5.tsv.gz", "trades_holdout_p5.tsv.gz"):
        out[f"cb702/out/{name}"] = d / "out" / name
    out["cb702/minutes/_done.psv"] = d / "minutes" / "_done.psv"
    for name in ("candidates_tl_com.tsv", "watch_tl_com.tsv.gz", "trades_pre_p5.tsv.gz"):
        out[f"cb702_pre/out/{name}"] = p / "out" / name
    out["cb702_pre/minutes/_done.psv"] = p / "minutes" / "_done.psv"
    out["cb702/minutes (tree)"] = d / "minutes"
    out["cb702_pre/minutes (tree)"] = p / "minutes"
    return out


def registration_doc_path(args, name: str) -> Path:
    """A one-run read's registration doc (`H60_DOC` / `EXITPB_DOC`): `--prereg`, else `docs/analysis/<name>` under the repo (looked up at
    call time)."""
    pre = getattr(args, "prereg", None)
    return Path(pre) if pre else Path(REPO) / "docs" / "analysis" / name


def h60_option_problems(args, data: Path) -> list:
    """Options the one-run read may not carry (as `pre_option_problems`): anything that moves the inputs or outputs, narrows the run, or
    swaps a table. `--minutes` too: the trees are pinned under the data dirs and those are the ones read."""
    bad = []
    for flag, val in (("--keys", getattr(args, "keys", None)), ("--levels", getattr(args, "levels", None)), ("--limit-dates", getattr(args, "limit_dates", 0)),
                      ("--no-close", getattr(args, "no_close", False)), ("--no-apollo", getattr(args, "no_apollo", False)),
                      ("--trades", getattr(args, "trades", None)), ("--minutes", getattr(args, "minutes", None))):
        if val:
            bad.append(f"{flag}: the h60 read runs in its registered form only (every row of tl and com, the pinned minute trees, the registered tables)")
    out = getattr(args, "out", None)
    if out and Path(out).resolve() != (Path(data) / "out").resolve():
        bad.append(f"--out {out} is not DATA/out ({Path(data) / 'out'}): the pinned inputs and the once-only check live there")
    so = getattr(args, "small_out", None)
    if so and Path(so).resolve() != (HERE / "out").resolve():
        bad.append(f"--small-out {so} is not {HERE / 'out'}")
    return bad


def h60_existing_outputs(out: Path, period: str) -> list:
    """The once-only guard: the period's trades table, the twin, or the `.partial` a crashed run left behind."""
    return existing_outputs(out, (f"trades_{period}_h60.tsv.gz", f"trades_{period}_{H60_TWIN}.tsv.gz"))


def h60_prepare(args, dirs: dict, period: str) -> dict:
    """The population and its minute inputs, annotated - what both `h60-step0` and `h60-read` start from. Opens no daily bar."""
    d = h60_period_dir(dirs, period)
    out = Path(getattr(args, "out", None) or d / "out")
    bases = h60_read_bases(out, period)
    widx = {k: h60_watch_index(out / h60_watch_file(period, k), k) for k in H60_LEVELS if any(key[2] == k for key in bases)}
    h60_annotate(bases, widx)
    inp = h60_minute_inputs(bases, d / "minutes")
    return {"data": d, "out": out, "bases": bases, "inp": inp, "label_rows": h60_label_rows(out, period)}


def run_h60_step0(args) -> int:
    """`h60-step0 --period P`: the entry-time table of a period, written and printed; no exit, no daily export. Allowed on the real dirs."""
    T0 = time.time()
    period = getattr(args, "period", None)
    if period not in H60_PERIODS:
        print(f"REFUSED: --period is required: one of {H60_PERIODS}", file=sys.stderr)
        return 2
    dirs = h60_dirs(args)
    prep = h60_prepare(args, dirs, period)
    small = Path(args.small_out) if getattr(args, "small_out", None) else HERE / "out"
    bases, inp = prep["bases"], prep["inp"]
    if inp["missing"] or inp["lost"]:
        print(f"REFUSED: {len(inp['missing']):,} of {len(inp['pairs']):,} (date, ticker) pairs are not logged in {inp['minutes_dir'] / '_done.psv'}"
              + (f"; {len(inp['lost']):,} more are logged ok on a date that has no minute file" if inp["lost"] else "") + ". STEP 0 reads every row or none", file=sys.stderr)
        return 2
    res = h60_step0(bases, inp, args.workers, period, prep["out"], small, h60_pinned_fills(prep["out"], period, bases))
    print(res["text"])
    tl_rows = H60_EXPECTED.get(period, {}).get("tl_rows")
    print(f"TL ROWS by label / file: {prep['label_rows']} (the registration's table: {tl_rows}) -> {'EQUAL' if prep['label_rows'] == tl_rows else 'DIFFERS'}")
    print(f"WROTE {prep['out'] / f'h60_step0_{period}.tsv.gz'}, {small / f'h60_step0_{period}.txt'}; WALL TIME {time.time() - T0:.0f}s")
    return 0


def h60_stamps(dirs: dict, period: str, c1_mean, delta_mean) -> list:
    """The agrees / contradicts stamps against the other periods' verdict files, when they exist (the sign of mean R and of the delta). Each
    period's file lives under ITS OWN data dir (`pre` writes to cb702_pre/out, the others to cb702/out)."""
    import json
    lines = []
    for other in H60_PERIODS:
        if other == period:
            continue
        p = h60_period_dir(dirs, other) / "out" / f"h60_verdict_{other}.json"
        if not p.exists():
            lines.append(f"{other}: no verdict file yet (not run) - no stamp")
            continue
        o = json.loads(p.read_text())
        for wname, rec in o.get("windows", {}).items():
            a = "agrees" if h60_sign(rec.get("c1_mean_r")) == h60_sign(c1_mean) else "contradicts"
            b = "agrees" if h60_sign(rec.get("delta_c1")) == h60_sign(delta_mean) else "contradicts"
            lines.append(f"{other} / {wname}: C1 mean R {h60_sign(rec.get('c1_mean_r'))} -> {a}; paired delta {h60_sign(rec.get('delta_c1'))} -> {b} (decides nothing)")
    return lines


def run_h60_read(args) -> int:
    """`h60-read --period P` - BUILT, NOT RUN. exit 2 on: a refused option, a freeze problem, missing minute pairs, outputs (or a crashed run's
    `.partial`) that exist, STEP 0 not equal to the registered table, the early-close or the data-abstain check failing, `--prereg` on a real run
    (the doc is pinned under docs/analysis); exit 3 when the twin re-walk differs from the pinned P5 table (no report written). `--print-pins`
    prints the footer lines; `--dry-run` counts only."""
    T0 = time.time()
    dirs = h60_dirs(args)
    data = dirs["cb702"]
    if getattr(args, "print_pins", False):
        doc = registration_doc_path(args, H60_DOC)
        lines = pin_lines(data, REPO, files=h60_frozen_files(dirs, REPO))
        lines.append(f"- doc body sha256: `{doc_body_sha(doc.read_text(encoding='utf-8')) if doc.is_file() else 'MISSING'}`")
        print("\n".join(lines))
        return 0
    period = getattr(args, "period", None)
    if period not in H60_PERIODS:
        print(f"REFUSED: --period is required: one of {H60_PERIODS}", file=sys.stderr)
        return 2
    if getattr(args, "prereg", None) and not getattr(args, "dry_run", False):
        print(f"REFUSED: --prereg is honoured only with --print-pins or --dry-run - the read pins the registration doc at docs/analysis/{H60_DOC} itself",
              file=sys.stderr)
        return 2
    bad = h60_option_problems(args, data)
    if bad:
        print("REFUSED: the h60 read runs only in its registered form:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 2
    dry, no_fc = getattr(args, "dry_run", False), getattr(args, "no_freeze_check", False)
    if no_fc and not dry:
        print("REFUSED: --no-freeze-check is honoured only together with --dry-run", file=sys.stderr)
        return 2
    if not no_fc:
        problems = freeze_check(doc=registration_doc_path(args, H60_DOC), data=data, repo=REPO, files=h60_frozen_files(dirs, REPO))
        if problems:
            print("REFUSED: the freeze check failed - the read is not opened:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 2
    prep = h60_prepare(args, dirs, period)
    out, bases, inp = prep["out"], prep["bases"], prep["inp"]
    small = HERE / "out"
    existing = h60_existing_outputs(out, period)
    if dry:
        print(f"H60 DRY RUN (freeze check {'SKIPPED' if no_fc else 'passed'}; counts only - no daily bar, minute row or outcome was opened): period {period}: "
              f"{len(bases):,} bases ({', '.join(f'{k} {sum(1 for key in bases if key[2] == k):,}' for k in H60_LEVELS)}), {sum(len(rs) for rs in bases.values()):,} rows, "
              f"{len(inp['pairs']):,} (date, ticker) pairs; pairs NOT logged in _done.psv: {len(inp['missing']):,}, logged ok with no file: {len(inp['lost']):,} -> "
              f"{'the run would REFUSE' if (inp['missing'] or inp['lost']) else 'complete'}; outputs already on disk: {[q.name for q in existing] or 'none'}"
              f"{' -> the run would REFUSE (read once)' if existing else ''}. Would write {out / f'trades_{period}_h60.tsv.gz'}, the twin "
              f"{out / f'trades_{period}_{H60_TWIN}.tsv.gz'}, {out / f'h60_pairs_{period}.tsv.gz'}, {out / f'h60_report_{period}.tsv'}, "
              f"{out / f'h60_verdict_{period}.txt'} and the small copies under {small}.")
        return 0
    if existing:
        crashed = [q for q in existing if q.name.endswith(".partial")]
        if crashed:
            print(f"REFUSED: {crashed[0]} is what a CRASHED h60 run left behind - it holds some outcomes. The read is run ONCE per period: the operator "
                  f"inspects it and removes it by hand before any re-run", file=sys.stderr)
        else:
            print(f"REFUSED: the h60 outcomes are read ONCE per period and {existing[0]} already exists", file=sys.stderr)
        return 2
    if not bases:
        print(f"REFUSED: no base of {period} in {out}", file=sys.stderr)
        return 2
    if inp["missing"] or inp["lost"]:
        print(f"REFUSED: {len(inp['missing']):,} of {len(inp['pairs']):,} (date, ticker) pairs are not logged in {inp['minutes_dir'] / '_done.psv'}"
              + (f"; {len(inp['lost']):,} more are logged ok on a date that has no minute file" if inp["lost"] else "") + ". A partial read is never run", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    log: list = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        log.append(msg)

    say(f"H60 READ (#702): period {period}; {len(bases):,} bases, {sum(len(rs) for rs in bases.values()):,} rows, {len(inp['pairs']):,} pairs all logged; "
        f"freeze check {'SKIPPED' if no_fc else 'passed'}; code: module sha256 {sha256_file(Path(cb.__file__))}, runner sha256 {sha256_file(Path(__file__))}")
    # STEP 0 first - written and checked before any exit is walked
    t = time.time()
    s0 = h60_step0(bases, inp, args.workers, period, out, small, h60_pinned_fills(out, period, bases))
    say(f"[STEP 0: {time.time() - t:.0f}s]")
    print(s0["text"])
    gate_lines = []
    tl_rows = H60_EXPECTED.get(period, {}).get("tl_rows")
    gate_lines.append(f"TL ROWS by label / file: {prep['label_rows']} (the registration's table: {tl_rows}) -> {'EQUAL' if prep['label_rows'] == tl_rows else 'DIFFERS'}")
    refuse = []
    if prep["label_rows"] != tl_rows:
        refuse.append(gate_lines[-1])
    for wname, pr in s0["problems"].items():
        refuse += [f"{wname}: {p}" for p in pr]
    if s0["early_problems"]:
        refuse += s0["early_problems"]
    if s0["data_share"] > H60_DATA_ABSTAIN_MAX:
        refuse.append(f"data-abstain share {s0['data_share']:.2%} > {H60_DATA_ABSTAIN_MAX:.0%}")
    for g in gate_lines:
        say(g)
    if refuse:
        say("REFUSED before any exit: STEP 0 does not pass the registered checks: " + "; ".join(refuse))
        (small / f"h60_summary_{period}.txt").write_text("\n".join(log) + "\n")
        return 2
    say("STEP 0 CHECKS: the registered table EQUAL in every window; early-close check ok; data-abstain share "
        f"{s0['data_share']:.2%} <= {H60_DATA_ABSTAIN_MAX:.0%}; 0 missing pairs")
    # the ORH5 twin: the pinned P5 population re-walked, equal in content to the pinned table
    t = time.time()
    tin = h60_twin_inputs(args, dirs, period)
    twin, _tally, n_tw = p5_walk(tin, args.workers, period, say, name=H60_TWIN)
    pinned = out / f"trades_{period}_p5.tsv.gz"
    tw_problems = h60_twin_check(twin, pinned)
    if tw_problems:
        say(f"TWIN CHECK FAILED - the ORH5 re-walk ({twin.name}, {n_tw:,} rows) is not the pinned {pinned.name}: " + "; ".join(tw_problems) + " - the report is NOT written")
        (small / f"h60_summary_{period}.txt").write_text("\n".join(log) + "\n")
        return 3
    say(f"TWIN CHECK: {twin.name} ({n_tw:,} rows) equals {pinned.name} in content (sha256 {gz_content_sha(twin)[:12]}) [{time.time() - t:.0f}s]")
    # the exits
    tp, tally = h60_exits(bases, inp, s0["pick"], _G["D"], args.workers, period, out, say)
    ent = Counter()
    for (v, sv, st, rs), n in tally.items():
        ent[(v, sv, st + ((" " + rs) if rs else ""))] += n
    say("ENTRIES WALKED (entry / stop: status n): " + "; ".join(f"{v}/{sv} {st} {n:,}" for (v, sv, st), n in sorted(ent.items())))
    say(f"WROTE {tp}")
    # the pairs table
    pairs_rows = h60_pair_rows(bases, s0["facts"], s0["pick"], h60_load_twin_side(twin), h60_load_trade_side(tp), period)
    pp = out / f"h60_pairs_{period}.tsv.gz"
    write_tsv(pp, pairs_rows, H60_PAIR_COLS, gz=True)
    say(f"WROTE {pp} ({len(pairs_rows):,} bases)")
    # the report
    df, pf = h60_load_frame(tp, pp)
    rows, verdicts = h60_report_rows(df, pf, period)
    twin_c0 = None
    try:
        tw = read_tsv(twin, usecols=["K", "arm", "C0", "realized_r", "mature"])
        tw = tw[(tw["K"] == H60_LEVEL) & (tw["arm"] == H60_ARM) & (tw["C0"] == 1) & (tw["mature"] == 1)]
        r = tw["realized_r"].to_numpy(dtype=float)
        twin_c0 = {"mean_r": float(r.mean()), "win_rate": float((r > 0).mean()), "share_ge10": float((r >= 10).mean())} if len(r) else None
    except Exception as exc:                       # the baseline line is informative only; the twin itself was checked above
        say(f"  ! ORH5 C0 baseline not read from the twin: {exc!r}")
    main_w = verdicts.get(period, {})
    stamps = h60_stamps(dirs, period, main_w.get("c1", {}).get("mean_r"), main_w.get("pairs", {}).get("C1", {}).get("mean"))
    notes = [f"DATA CHECKS: freeze {'SKIPPED' if no_fc else 'passed'}; STEP 0 equal to the registered table; early-close ok; data-abstain share "
             f"{s0['data_share']:.2%}; twin equal in content to {pinned.name}; rows walked {sum(tally.values()):,}"]
    text = h60_report_text(period, rows, verdicts, notes, twin_c0, stamps, df)
    name = f"h60_report_{period}"
    write_tsv(out / f"{name}.tsv", rows, H60_REPORT_COLS)
    compact = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows if r["slice"] in ("all", "own_C1", "no_gap")]
    write_tsv(small / f"{name}.tsv", compact, H60_REPORT_COLS)
    (small / f"{name}.txt").write_text(text + "\n")
    (out / f"{name}.txt").write_text(text + "\n")
    print(text)
    # the verdict file (the hindsight gate) and its machine-readable sidecar
    import json
    vj = {"period": period, "windows": {}}
    vlines = [f"#702 h60 C1 VERDICT FILE - period {period} - written {time.strftime('%Y-%m-%d')}"]
    for wname, v in verdicts.items():
        c1, pv = v["c1"], v["pairs"]
        p1 = pv.get("C1", {})
        vj["windows"][wname] = {"c1_verdict": c1.get("verdict"), "c1_why": c1.get("why"), "c1_n": c1.get("n"), "c1_mean_r": c1.get("mean_r"),
                                "c1_ci": [c1.get("ci_lo"), c1.get("ci_hi")], "delta_c1": p1.get("mean"), "delta_c1_ci": [p1.get("lo"), p1.get("hi")],
                                "pair_verdict_c1": p1.get("verdict"), "stop_carry_c1": p1.get("stop", {}).get("carry"),
                                "delta_c0_lo": pv.get("C0", {}).get("lo"),
                                "consequence": (h60_consequence(str(c1.get("verdict")), str(p1.get("verdict")), pv.get("C0", {}).get("lo")) if period == "discovery" else "decides nothing")}
        w = vj["windows"][wname]
        vlines.append(f"{wname}: C1 {w['c1_verdict']} ({w['c1_why']}); n {w['c1_n']}; mean R {_num(w['c1_mean_r'])} {_ci({'ci_lo': w['c1_ci'][0], 'ci_hi': w['c1_ci'][1]})}; "
                      f"paired entry {w['pair_verdict_c1']} (delta {_num(w['delta_c1'])}); stop carried {w['stop_carry_c1']}; consequence: {w['consequence']}")
    (out / f"h60_verdict_{period}.json").write_text(json.dumps(vj, indent=1) + "\n")
    (out / f"h60_verdict_{period}.txt").write_text("\n".join(vlines) + "\n")
    (small / f"h60_verdict_{period}.txt").write_text("\n".join(vlines) + "\n")
    say(f"WROTE {out / (name + '.tsv')} ({len(rows):,} rows), {small / (name + '.txt')}, {out / f'h60_verdict_{period}.txt'}")
    say(f"WALL TIME: {time.time() - T0:.0f}s total")
    (small / f"h60_summary_{period}.txt").write_text("\n".join(log) + "\n")
    return 0


# ── hindsight (after the verdict): the 39 multibaggers and TSLA row by row ─────────────────────────────────────────────────────
def h60_hindsight_rows(pf, years) -> tuple:
    """(per-ticker rows, the two totals) of the multibaggers' C0 tl bases in the window under h60 vs ORH5, from the pairs table: n (filled),
    mean R, total R, fill-day stop share (needs the trades table: passed as `fill_day` columns on the pairs frame by the caller), >= 5R / >= 10R."""
    sub = pf[(pf["K"] == H60_LEVEL) & (pf["C0"] == 1) & pf["ticker"].isin(H60_MULTIBAGGERS)]
    if years is not None:
        sub = sub[sub["first_year"].isin(years)]
    rows = []

    def side(g, pre):
        f = g[(g[pre + "_status"] == "filled") & (g[pre + "_mature"] == 1)]
        r = f[pre + "_r"].to_numpy(dtype=float)
        return {"n": int(len(f)), "mean_r": (float(r.mean()) if len(r) else None), "sum_r": float(r.sum()), "ge5": int((r >= 5).sum()), "ge10": int((r >= 10).sum()),
                "fill_day_stop": (float(f[pre + "_fill_day_stop"].to_numpy(dtype=float).mean()) if len(f) and (pre + "_fill_day_stop") in f else None)}
    for t, g in sub.groupby("ticker"):
        a, b = side(g, "h60"), side(g, "orh5")
        rows.append({"ticker": t, "bases": int(len(g)), **{"h60_" + k: v for k, v in a.items()}, **{"orh5_" + k: v for k, v in b.items()}})
    tot = {"ticker": "ALL", "bases": int(len(sub)), **{"h60_" + k: v for k, v in side(sub, "h60").items()}, **{"orh5_" + k: v for k, v in side(sub, "orh5").items()}}
    return rows, tot


def run_h60_hindsight(args) -> int:
    """`h60-hindsight --period P`: refused until `h60_verdict_<P>.txt` exists (the verdict is read first; hindsight never decides)."""
    T0 = time.time()
    period = getattr(args, "period", None)
    if period not in H60_PERIODS:
        print(f"REFUSED: --period is required: one of {H60_PERIODS}", file=sys.stderr)
        return 2
    dirs = h60_dirs(args)
    d = h60_period_dir(dirs, period)
    out = Path(getattr(args, "out", None) or d / "out")
    small = Path(args.small_out) if getattr(args, "small_out", None) else HERE / "out"
    deciding = dirs["cb702"] / "out" / "h60_verdict_discovery.txt"
    if not deciding.exists():
        print(f"REFUSED: {deciding} does not exist - the hindsight tables (any period) are written only AFTER the DECIDING 2022-24 verdict is read (check 1)",
              file=sys.stderr)
        return 2
    gate = out / f"h60_verdict_{period}.txt"
    if not gate.exists():
        print(f"REFUSED: {gate} does not exist - the hindsight tables are written only AFTER the period's C1 verdict (check 1)", file=sys.stderr)
        return 2
    tp, pp = out / f"trades_{period}_h60.tsv.gz", out / f"h60_pairs_{period}.tsv.gz"
    if not tp.exists() or not pp.exists():
        print(f"REFUSED: {tp} / {pp} missing - run h60-read first", file=sys.stderr)
        return 2
    df, pf = h60_load_frame(tp, pp)
    prim = df[(df["K"] == H60_LEVEL) & (df["entry"] == H60_ENTRY) & (df["stop_variant"] == H60_STOP) & (df["arm"] == H60_ARM)]
    fds = {b: int(x) for b, x in prim[["base", "fill_day_stop"]].itertuples(index=False)}
    pf["h60_fill_day_stop"] = pf["base"].map(fds)
    twin = out / f"trades_{period}_{H60_TWIN}.tsv.gz"
    if twin.exists():
        tw = read_tsv(twin, usecols=["ticker", "D", "K", "arm", "status"])
        tw = tw[(tw["arm"] == H60_ARM)]
        fd5 = {(t, dd, k): int(s == "stopped_day0") for t, dd, k, s in tw[["ticker", "D", "K", "status"]].itertuples(index=False)}
        pf["orh5_fill_day_stop"] = [fd5.get((t, dd, k)) for t, dd, k in zip(pf["ticker"], pf["first_D"], pf["K"])]
    lines = [f"#702 h60 HINDSIGHT - period {period} (descriptive; written AFTER the verdict; naming winners afterwards always looks good; decides nothing)"]
    all_rows = []
    for wname, years in h60_windows_of(period):
        rows, tot = h60_hindsight_rows(pf, years)
        for r in rows + [tot]:
            r["window"] = wname
        all_rows += rows + [tot]
        lines.append(f"THE 39 MULTIBAGGERS, C0 tl bases, window {wname}: h60 vs ORH5 (n filled & mature / mean R / total R / fill-day stop share / >= 5R / >= 10R)")
        body = [[r["ticker"], r["bases"], f"{r['h60_n']} / {_num(r['h60_mean_r'], 2)} / {_num(r['h60_sum_r'], 1)} / {_pct(r['h60_fill_day_stop'])} / {r['h60_ge5']} / {r['h60_ge10']}",
                 f"{r['orh5_n']} / {_num(r['orh5_mean_r'], 2)} / {_num(r['orh5_sum_r'], 1)} / {_pct(r['orh5_fill_day_stop'])} / {r['orh5_ge5']} / {r['orh5_ge10']}"]
                for r in rows + [tot]]
        lines.append(table(body, ["ticker", "bases", "h60", "ORH5"]))
    tsla = pf[(pf["ticker"] == H60_TSLA[0]) & (pf["K"] == H60_LEVEL)].sort_values("first_E")
    lines.append("TSLA, every tl base row by row: first break (ORH5's day) -> status / R; h60's confirmed day -> status / R")
    body = [[r.pole_date, r.first_E, f"{r.orh5_status} / {_num(r.orh5_r, 2)}", f"{r.h60_E or '-'} ({r.h60_status}) / {_num(r.h60_r, 2)}", int(r.C1)] for r in tsla.itertuples()]
    lines.append(table(body, ["pole", "first E", "ORH5", "h60", "C1"]) if body else "  (no TSLA base in this period)")
    text = "\n".join(lines)
    cols = ["window", "ticker", "bases"] + [p + k for p in ("h60_", "orh5_") for k in ("n", "mean_r", "sum_r", "fill_day_stop", "ge5", "ge10")]
    write_tsv(out / f"h60_hindsight_{period}.tsv", all_rows, cols)
    write_tsv(small / f"h60_hindsight_{period}.tsv", all_rows, cols)
    (small / f"h60_hindsight_{period}.txt").write_text(text + "\n")
    (out / f"h60_hindsight_{period}.txt").write_text(text + "\n")
    print(text)
    print(f"WROTE {out / f'h60_hindsight_{period}.tsv'}, {small / f'h60_hindsight_{period}.txt'}; WALL TIME {time.time() - T0:.0f}s")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# #702 EXIT READ (operator 2026-10-19; docs/analysis/cb_exit_partial_prereg_2026-10-19.md): his partial and the stop after it. The
# day-based third sells only in profit (`pp` - his RULING, adopted, not tested); after a third the stop goes where the WHOLE trade nets
# zero (`pp_wbe` - his PROPOSAL, the test) instead of to the entry price. Every arm walks the SAME fills as the pinned P5 tables (ORH5,
# the deciding population) and, descriptively, the pinned hourly-close fills; only the exit changes, so the comparison is per trade.
# The arms run on a RUNNER-SIDE COPY of `walk_exit`'s qm path (`exitpb_walk`) with two flags - the session-leg rule and the
# post-third stop rule - dispatched like `walk_his_arms` on the module's own day-0 functions; the module stays byte-identical (its
# sha256 is hard-checked against `EXITPB_MODULE_SHA`). Before any new-arm number exists the copy with every flag off is proved equal,
# per trade, to the pinned P5 rows (P1) and to the pinned hourly-close rows (P2), and to the module's own walk event for event (the
# `stop_to` events the copy adds are excluded); a mismatch exits 3 and writes nothing. BUILT ON SYNTHETIC DATA; the build computed
# no real outcome (`--parity-only` walks the control alone and prints the match counts).
# ═════════════════════════════════════════════════════════════════════════════════════════════
EXITPB_DOC = "cb_exit_partial_prereg_2026-10-19.md"
EXITPB_NAME = "exitpb"                                         # the file tag: trades_<period>_exitpb.tsv.gz, exitpb_report_<period>.*
EXITPB_PERIODS = H60_PERIODS                                   # discovery decides; pre beside; holdout descriptive
EXITPB_MODULE_SHA = "e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b"   # the registration: the module MUST equal it
EXITPB_BASE = cb.CUT_EXIT_ARMS[cb.P5_PRIMARY_ARM]              # c3_p33_t20_cut3: the mechanics every arm shares (1/3; the +2R leg; the
#                                                              # session-3 leg; the 20-day trail at the next open; the +1R-by-session-3 cut)
EXITPB_SESSION_RULES = ("always", "profit_only", "profit_3to5")   # the session leg: the session-3 close whatever the price (A) | only a
#                                                              # session-3 close ABOVE the fill (his ruling) | the FIRST close in 3..5 above it
EXITPB_STOP_RULES = ("entry", "wbe", "stop0")                  # after a third sold at p: max(stop, fill) | max(stop0, min(fill, fill - (p -
#                                                              # fill) / 2)) - the whole-trade breakeven | the stop stays at stop0
EXITPB_LEG_FIRST = int(EXITPB_BASE.partial_session)            # 3: the session leg's session, and the session the pp-family trail goes live
EXITPB_LEG_LAST = 5                                            # `profit_3to5`: the last session of its window
EXITPB_LEVEL = H60_LEVEL                                       # tl: the registered level (com / comb rows are walked for parity and kept beside)
EXITPB_ENTRIES = ("orh5", "h60")                               # orh5 = the pinned P5 fills (decides); h60 = the pinned hourly-close fills (descriptive)
EXITPB_ENTRY = "orh5"
EXITPB_MIN_N = H60_PAIR_MIN_N                                  # 30: the n floor of the deciding delta and of a cell verdict
EXITPB_TOL = P5_XCHECK_TOL                                     # 1e-9: parity on realized R; the stop_to formula check (relative)
EXITPB_CONTROL, EXITPB_RULED, EXITPB_PRIMARY = "A", "pp", "pp_wbe"
EXITPB_DELTAS = (("pp_wbe", "pp"), ("pp", "A"), ("pp_wbe", "A"), ("pp_s0", "pp"), ("pp5_wbe", "pp_wbe"), ("wbe", "A"))   # (x, y): R(x) - R(y); the first DECIDES
EXITPB_DELTA_CELLS = ("C1", "C0")                              # C1 decides; C0 = the mechanism at scale (breaks a C1 can't-tell)
EXITPB_TSLA = ("TSLA", "2020-06-01")                           # the WOULD-FAIL-IF mechanics check on the pre period's hourly-close fills
EXITPB_REACH_DOC = {"discovery": {"C1": {"fills": 79, "third": 34, "third_day0_r": 12, "third_r": 17, "third_session": 5, "stopped_after_third_le_fill": 24,
                                         "session_third_le_fill": 1},
                                  "C0": {"mature": 8984, "third": 2874, "stopped_after_third_le_fill": 1943, "session_third_le_fill": 112}}}
#                                                              # the registration's reach line from A's rows ("stopped AT COST after the third" there = stopped
#                                                              # after the third at or below the fill here, a gap under the fill included) - printed beside, never a gate
EXITPB_TRADE_COLS = (["ticker", "D", "E", "K", "period", "entry", "year", "fill_month", "retrigger_chain", "pole_date", "base", "first_E",
                      "first_month", "row_no", "own_C1", "early_close"] + CELL_COLS
                     + ["gap_over_1adr", "phase_qqq_10_20", "adr20", "fill", "fill_minute", "walk_from", "stop", "width_pct", "width_adr", "target",
                        "arm", "session_rule", "stop_rule", "status", "realized_r", "pnl_adr", "acct_pct", "sessions_held", "mature", "open_mark",
                        "fill_day_stop", "partial_kind", "partial_session", "partial_px", "stop_to", "exit_kind", "exit_px", "exit_session",
                        "stopped_after_third_le_fill", "beabove", "beabove_kind", "fwd_bars", "fwd_hole"])
EXITPB_STAT_COLS = H60_STAT_COLS + ["n_third", "n_third_day0_r", "n_third_r", "n_third_session", "share_third", "n_stopped_after_third_le_fill",
                                    "share_stopped_after_third_le_fill", "n_beabove_session", "n_beabove_r", "n_ge10", "n_ge10_a", "n_ge10_both"]
EXITPB_REPORT_COLS = ["period", "entry", "cell", "K", "arm", "slice", "value"] + EXITPB_STAT_COLS + ["verdict", "why"]
EXITPB_DELTA_COLS = ["period", "entry", "cell", "K", "delta", "x", "y", "n", "n_excluded_open", "n_differ", "mean", "ci_lo", "ci_hi", "verdict", "deciding"]


@dataclass(frozen=True)
class ExitArm:
    """One arm of the exit read: the shared mechanics of `EXITPB_BASE` plus the two registered flags."""
    name: str
    session_rule: str
    stop_rule: str

    def __post_init__(self):
        if self.session_rule not in EXITPB_SESSION_RULES:
            raise ValueError(f"ExitArm {self.name!r}: session_rule must be one of {EXITPB_SESSION_RULES}, got {self.session_rule!r}")
        if self.stop_rule not in EXITPB_STOP_RULES:
            raise ValueError(f"ExitArm {self.name!r}: stop_rule must be one of {EXITPB_STOP_RULES}, got {self.stop_rule!r}")

    @property
    def profit_gated(self) -> bool:
        """The pp family: the session third needs a close above the fill; the trail is live from session 3 whether or not it sold."""
        return self.session_rule != "always"

    @property
    def day0_breakeven(self) -> bool:
        """Day 0 on the minutes: the stop moves to the fill after a day-0 third only under the entry-price rule (`A`, `pp`); the wbe /
        stop0 family keeps stop0 (a +2R third gives exactly stop0 under the wbe formula)."""
        return self.stop_rule == "entry"


EXITPB_ARMS = {"A": ExitArm("A", "always", "entry"),                 # the control = c3_p33_t20_cut3 exactly (P1 / P2 prove it)
               "pp": ExitArm("pp", "profit_only", "entry"),          # his ruling: the session-3 third only on a close above the fill
               "pp_wbe": ExitArm("pp_wbe", "profit_only", "wbe"),    # PRIMARY: pp + his proposal, the whole-trade breakeven stop
               "wbe": ExitArm("wbe", "always", "wbe"),               # beside: A's partial rule + the wbe stop (a below-cost third caps at the fill)
               "pp_s0": ExitArm("pp_s0", "profit_only", "stop0"),    # beside: pp with the stop left at stop0 after ANY third, day 0 included
               "pp5_wbe": ExitArm("pp5_wbe", "profit_3to5", "wbe")}  # beside: the FIRST close in sessions 3..5 above the fill, then the wbe stop


def exitpb_stop_after_third(rule: str, stop_now: float, stop0: float, fill: float, px: float) -> float:
    """The stop resting from the NEXT session after a third sold at `px`: `entry` = max(stop, fill) (the module's breakeven); `wbe` =
    max(stop0, min(fill, fill - (px - fill) / 2)) - the level at which the two thirds left lose exactly what the third made, never below
    the original stop, never above the fill (a below-cost third caps at the fill, i.e. as `entry`); `stop0` = the original stop."""
    if rule == "entry":
        return max(stop_now, fill)
    if rule == "wbe":
        return max(stop0, min(fill, fill - (px - fill) / 2.0))
    if rule == "stop0":
        return stop0
    raise ValueError(f"exitpb_stop_after_third: unknown stop rule {rule!r}")


def exitpb_session_leg(rule: str, j: int, close_j: float, fill: float) -> bool:
    """Does the session leg sell the third at the close of session j? `always`: session 3 whatever the price (the module's combo partial);
    `profit_only`: session 3 only on a close ABOVE the fill; `profit_3to5`: the first close in sessions 3..5 above the fill."""
    if rule == "always":
        return j == EXITPB_LEG_FIRST
    if rule == "profit_only":
        return j == EXITPB_LEG_FIRST and close_j > fill
    if rule == "profit_3to5":
        return EXITPB_LEG_FIRST <= j <= EXITPB_LEG_LAST and close_j > fill
    raise ValueError(f"exitpb_session_leg: unknown session rule {rule!r}")


def exitpb_walk(*, fill: float, stop: float, closes_before, fwd: "cb.DailyBars", arm: ExitArm, adr20: float, horizon: int = HORIZON,
                day0_partial_px: "float | None" = None, day0_peak: "float | None" = None) -> dict:
    """The runner-side copy of `cb.walk_exit`'s qm path for `EXITPB_BASE` (a combo +2R / session-3 third of 1/3, the 20-day trail filled
    at the next open, the +1R-by-session-3 stall cut, horizon 120), with the two registered flags. Per session the module's order is
    kept: the gap partial, the stop in force BEFORE the session, the +2R leg, the reach / cut test, the session leg, the trail.
    What the flags change: (1) the session leg sells per `arm.session_rule` (`exitpb_session_leg`); (2) after ANY third the stop rests
    per `arm.stop_rule` (`exitpb_stop_after_third`) from the next session, and the copy emits `(j, "stop_to", level, 0.0)` after every
    third (the level in force from the next session, even when it is stop0 itself - the pp_s0 arm, a +2R third under wbe); an event
    `(j, "be_above_close", close, 0.0)` follows whenever that level sits above the session's close (the module's hidden one-day time
    stop; under the pp family the +2R kind remains and is counted); (3) the trail: `partial_done` under `always` (the module's own
    expression for this arm) and `partial_done or j >= 3` for the pp family - the session-3 close itself is tested against the 20-day
    whether or not the third sold, and a signal then sells EVERYTHING left at the next open. With every flag off (`A`) the walk is the
    module's, event for event but for the `stop_to` events (P1 / P2, and `exitpb_compare_module`). Day 0 is the caller's
    (`exitpb_walk_arms`): `day0_partial_px` = the day-0 +2R third already taken, `day0_peak` = day 0's highest minute high after the fill."""
    adr20 = cb._check_adr(adr20)
    risk = float(fill) - float(stop)
    if not risk > 0:
        raise ValueError(f"exitpb_walk: stop {stop} must be below fill {fill}")
    base = EXITPB_BASE
    fill, stop0 = float(fill), float(stop)
    o, h, l, c = fwd.o, fwd.h, fwd.l, fwd.c
    n = len(c)
    events: list = []
    pnl = 0.0
    last_before = float(np.asarray(closes_before, dtype=float)[-1]) if len(closes_before) else None
    cb_arr = np.asarray(closes_before, dtype=float)
    trail_n = int(base.trail_sma)
    tail = cb_arr[-trail_n:]
    n_before = len(tail)
    cs = np.concatenate(([0.0], np.cumsum(np.concatenate((tail, c)))))
    remaining = 1.0
    stop_now = stop0
    partial_done = False
    frac = base.partial_frac
    target = fill + float(base.partial_r) * risk

    def _after_third(j: int, px: float, close_j: float) -> None:
        nonlocal stop_now
        stop_now = exitpb_stop_after_third(arm.stop_rule, stop_now, stop0, fill, px)
        events.append((j, "stop_to", stop_now, 0.0))
        if stop_now > close_j:                  # the session closed under the resting stop: tomorrow's open takes it
            events.append((j, "be_above_close", close_j, 0.0))

    def _book_r_partial(j: int, px: float, close_j: float) -> None:
        nonlocal pnl, remaining, partial_done
        events.append((j, "partial_r", px, frac))
        pnl += (px - fill) * frac
        remaining -= frac
        partial_done = True
        _after_third(j, px, close_j)

    if day0_partial_px is not None:
        if last_before is None:
            raise ValueError("exitpb_walk: day0_partial_px needs E's close in closes_before")
        _book_r_partial(0, float(day0_partial_px), last_before)
    cut_level = fill + float(base.stall_cut_r) * risk
    reached = day0_partial_px is not None and float(day0_partial_px) >= cut_level
    if not reached:
        if day0_peak is None:
            raise ValueError("exitpb_walk: the stall cut needs day0_peak (day 0's highest minute high after the fill)")
        reached = float(day0_peak) >= cut_level
    cut_session = int(base.stall_cut_session)
    for j in range(1, min(int(horizon), n) + 1):
        oj, lj, cj = float(o[j - 1]), float(l[j - 1]), float(c[j - 1])
        stop_j = stop_now                       # the stop this session is judged against (a third today moves it from tomorrow)
        gap_px = oj if (not partial_done and oj >= target) else None
        if oj <= stop_j or lj <= stop_j:        # 1. the stop (a gap-open third first: its open came before the low)
            if gap_px is not None:
                events.append((j, "partial_r", gap_px, frac))
                pnl += (gap_px - fill) * frac
                remaining -= frac
            px = oj if oj <= stop_j else stop_j
            events.append((j, "stop_gap" if oj < stop_j else "stop", px, remaining))
            pnl += (px - fill) * remaining
            return cb._outcome("stopped", pnl, risk, fill, adr20, j, events)
        if gap_px is not None:                  # 1b. the +2R leg: at the open when it gapped above, else AT the target
            _book_r_partial(j, gap_px, cj)
        elif not partial_done and float(h[j - 1]) >= target:
            _book_r_partial(j, target, cj)
        if not reached and j <= cut_session and float(h[j - 1]) >= cut_level:    # 1c. the reach test, then the cut
            reached = True
        if not reached and j == cut_session:
            events.append((j, "cut", cj, remaining))
            pnl += (cj - fill) * remaining
            return cb._outcome("time_exit", pnl, risk, fill, adr20, j, events)
        if not partial_done and exitpb_session_leg(arm.session_rule, j, cj, fill):   # 2. the session leg, at the close
            events.append((j, "partial", cj, frac))
            pnl += (cj - fill) * frac
            remaining -= frac
            partial_done = True
            _after_third(j, cj, cj)
        trail_live = partial_done if not arm.profit_gated else (partial_done or j >= EXITPB_LEG_FIRST)   # 3. the trail
        if trail_live:
            pos = n_before + j
            if pos - trail_n >= 0:
                sma = (cs[pos] - cs[pos - trail_n]) / trail_n
                if cj < sma and j < n:          # the remainder sells at the next open; no next open falls through to the mark
                    opx = float(o[j])
                    events.append((j + 1, "trail", opx, remaining))
                    pnl += (opx - fill) * remaining
                    return cb._outcome("censored" if j == int(horizon) else "trailed", pnl, risk, fill, adr20, j + 1, events)
        if j == int(horizon):                   # 4. the horizon
            events.append((j, "mark", cj, remaining))
            pnl += (cj - fill) * remaining
            return cb._outcome("censored", pnl, risk, fill, adr20, j, events)
    return cb._degraded(c, n, remaining, pnl, fill, risk, adr20, events, last_before)


def exitpb_walk_arms(entry: dict, *, closes_before, fwd: "cb.DailyBars", adr20: float, minutes: "cb.MinuteBars", horizon: int = HORIZON,
                     arms: "dict | None" = None) -> dict:
    """{arm name: `walk_exit`-shaped result} for ONE filled entry {fill, stop, fill_minute} over `arms` (default `EXITPB_ARMS`), dispatched
    as `walk_his_arms` dispatches a +R-target arm: day 0 on the MINUTES through the module's own `day0_walk_target` (once per breakeven
    flag: True for the entry-price family, False for the wbe / stop0 family), nothing left after day 0 -> `day0_target_to_outcome`
    (a day-0 third then gets its `stop_to` = the stop in force when the day ended), else `exitpb_walk` with the day-0 third and
    `day0_peak_high`. `fill_minute` is the minute the day-0 walk starts AFTER (ORH5: the fill minute; the hourly-close fills: `walk_from`)."""
    arms = EXITPB_ARMS if arms is None else arms
    adr20 = cb._check_adr(adr20)
    base = EXITPB_BASE
    fill, stop = float(entry["fill"]), float(entry["stop"])
    target = fill + float(base.partial_r) * (fill - stop)
    d0: dict = {}
    peak = None
    out = {}
    for name, arm in arms.items():
        be = arm.day0_breakeven
        if be not in d0:
            d0[be] = cb.day0_walk_target(minutes, fill=fill, fill_minute=entry["fill_minute"], stop=stop, target=target,
                                         partial_frac=base.partial_frac, breakeven=be)
        r = d0[be]
        if r["stopped"]:
            res = cb.day0_target_to_outcome(entry, r, adr20, base.partial_frac)
            if r.get("partial_price") is not None:
                res["events"] = res["events"][:1] + [(0, "stop_to", float(r["stop_in_force"]), 0.0)] + res["events"][1:]
            out[name] = res
            continue
        if peak is None:
            peak = cb.day0_peak_high(minutes, entry["fill_minute"])
        out[name] = exitpb_walk(fill=fill, stop=stop, closes_before=closes_before, fwd=fwd, arm=arm, adr20=adr20, horizon=horizon,
                                day0_partial_px=r["partial_price"], day0_peak=peak)
    return out


def exitpb_facts(events: list, fill: float) -> dict:
    """The event-derived columns of one walk: the third (kind as `partial_facts` names it - day0_r / r / session / '' -, its session and
    price), the stop resting after it (`stop_to`), the exit (the last event: kind, price, session), whether the trade was stopped after
    its third at or below the fill, and the kind of third a `be_above_close` followed ('session' or 'r')."""
    kind, sess, _tn = partial_facts(events, EXITPB_BASE)
    px, stop_to, beabove_kind = None, None, ""
    for _j, k, p, _f in events:
        if k in ("partial", "partial_r") and px is None:
            px = float(p)
        elif k == "stop_to":
            stop_to = float(p)
        elif k == "be_above_close":
            beabove_kind = "session" if kind == "session" else "r"
    if events:
        ej, ek, ep, _ef = events[-1]
        exit_kind, exit_px, exit_session = ek, float(ep), int(ej)
    else:
        exit_kind, exit_px, exit_session = "", None, None
    stopped_le = int(kind != "" and exit_kind in ("stop", "stop_gap", "day0_stop", "day0_gap") and exit_px is not None and exit_px <= fill + EXITPB_TOL)
    return {"partial_kind": kind, "partial_session": sess, "partial_px": px, "stop_to": stop_to, "exit_kind": exit_kind, "exit_px": exit_px,
            "exit_session": exit_session, "stopped_after_third_le_fill": stopped_le,
            "beabove": int(any(ev[1] == "be_above_close" for ev in events)), "beabove_kind": beabove_kind}


# ── the pinned populations ───────────────────────────────────────────────────────────────────────────────────────────────────────
def exitpb_pinned_trades(out: Path, period: str) -> list:
    """One dict per FILLED trade of the period's two pinned tables: the P5 table's control rows (`c3_p33_t20_cut3` on the lod stop;
    entry orh5; every level) and the hourly-close table's h60 / lod / control rows (entry h60; every level). The fill, its stop, the
    minute the day-0 walk starts after, ADR20 and the entry-time facts are read; the pinned OUTCOME columns ride along under
    `_pinned` for the parity check and nothing else reads them."""
    trades: list = []
    ctl = EXITPB_BASE.name
    p5 = Path(out) / f"trades_{period}_{P5_NAME}.tsv.gz"
    with gzip.open(p5, "rt", newline="") as fh:
        for rec in csv.DictReader(fh, delimiter="\t"):
            if rec["arm"] != ctl or rec["stop_variant"] != "lod":
                continue
            trades.append(_exitpb_trade(rec, period, "orh5", walk_from=int(rec["fill_minute"]), fill_month=rec["E"][:7],
                                        pole_date="", base="", first_E="", first_month="", row_no="", own_C1="",
                                        retrigger_chain=int(rec.get("retrigger_chain") or 0)))
    h60 = Path(out) / f"trades_{period}_h60.tsv.gz"
    with gzip.open(h60, "rt", newline="") as fh:
        for rec in csv.DictReader(fh, delimiter="\t"):
            if rec["arm"] != ctl or rec["stop_variant"] != H60_STOP or rec["entry"] != H60_ENTRY:
                continue
            trades.append(_exitpb_trade(rec, period, "h60", walk_from=int(rec["walk_from"]), fill_month=rec["fill_month"],
                                        pole_date=rec["pole_date"], base=rec["base"], first_E=rec["first_E"], first_month=rec["first_month"],
                                        row_no=int(rec["row_no"]), own_C1=int(rec["own_C1"]), retrigger_chain=""))
    return trades


def _exitpb_trade(rec: dict, period: str, entry: str, **extra) -> dict:
    fill, stop, adr20, width = float(rec["fill"]), float(rec["stop"]), float(rec["adr20"]), float(rec["width_pct"])
    t = {"ticker": rec["ticker"], "D": rec["D"], "E": rec["E"], "K": rec["K"], "period": period, "entry": entry, "year": int(rec["E"][:4]),
         "early_close": int(rec["E"] in H60_EARLY_CLOSE), "gap_over_1adr": int(rec.get("gap_over_1adr") or 0),
         "phase_qqq_10_20": int(rec.get("phase_qqq_10_20") or 0), "adr20": adr20, "fill": fill, "fill_minute": int(rec["fill_minute"]),
         "stop": stop, "width_pct": width, "width_adr": width / adr20, "target": fill + float(EXITPB_BASE.partial_r) * (fill - stop),
         "_pinned": {"status": rec["status"], "mature": int(rec["mature"]), "sessions_held": int(rec["sessions_held"]),
                     "partial_kind": rec["partial_kind"], "partial_session": rec["partial_session"], "realized_r": float(rec["realized_r"]),
                     "beabove": int(rec["beabove"]), "fwd_bars": int(rec["fwd_bars"]), "fwd_hole": int(rec["fwd_hole"])}}
    for cell in CELL_COLS:
        t[cell] = int(rec.get(cell) or 0)
    t.update(extra)
    return t


def exitpb_trade_key(t: dict) -> str:
    return f"{t['ticker']}|{t['E']}|{t['K']}|{t['entry']}"


# ── the parity checks ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def exitpb_compare_pinned(key: str, pinned: dict, ar: dict, facts: dict, n_fwd: int, cut: bool) -> list:
    """P1 / P2: the copy with every flag off against the pinned row - status, maturity, sessions held, the third's kind and session, the
    be_above_close flag, the forward window, and realized R to 1e-9."""
    bad = []

    def _sess(x) -> str:                        # the third's session: '' or an integer, however the table spelled it ('3' / '3.0')
        return "" if x in ("", None) else str(int(float(x)))
    for col, mine in (("status", ar["status"]), ("mature", int(ar["mature"])), ("sessions_held", int(ar["sessions_held"])),
                      ("partial_kind", facts["partial_kind"]), ("partial_session", _sess(facts["partial_session"])), ("beabove", int(facts["beabove"])),
                      ("fwd_bars", n_fwd), ("fwd_hole", int(cut))):
        theirs = _sess(pinned[col]) if col == "partial_session" else pinned[col]
        if str(mine) != str(theirs):
            bad.append(f"{key}: {col} copy {mine!r} vs pinned {theirs!r}")
    if abs(float(ar["realized_r"]) - float(pinned["realized_r"])) > EXITPB_TOL:
        bad.append(f"{key}: realized_r copy {ar['realized_r']!r} vs pinned {pinned['realized_r']!r}")
    return bad


def exitpb_compare_module(key: str, ref: dict, copy: dict) -> list:
    """The copy with every flag off against the module's own walk of the same entry: the same status, sessions held, realized R and
    events (the copy's `stop_to` events excluded)."""
    import math
    bad = []
    mine = [ev for ev in copy["events"] if ev[1] != "stop_to"]
    theirs = list(ref["events"])
    if len(mine) != len(theirs):
        bad.append(f"{key}: {len(mine)} events vs the module's {len(theirs)}")
    else:
        for a, b in zip(mine, theirs):
            if a[0] != b[0] or a[1] != b[1] or not math.isclose(float(a[2]), float(b[2]), rel_tol=1e-12, abs_tol=1e-12) or a[3] != b[3]:
                bad.append(f"{key}: event {a} vs the module's {b}")
                break
    if copy["status"] != ref["status"] or int(copy["sessions_held"]) != int(ref["sessions_held"]):
        bad.append(f"{key}: status / sessions_held {copy['status']} / {copy['sessions_held']} vs the module's {ref['status']} / {ref['sessions_held']}")
    if not math.isclose(float(copy["realized_r"]), float(ref["realized_r"]), rel_tol=1e-12, abs_tol=1e-12):
        bad.append(f"{key}: realized_r {copy['realized_r']!r} vs the module's {ref['realized_r']!r}")
    return bad


def exitpb_reach_facts(t: dict, ar: dict, facts: dict) -> Counter:
    """The registration's reach line, from the control's own rows: per (entry, K, cell) the fills, the mature walks, the thirds by kind,
    the trades stopped after the third at the fill (`at_cost`) / at or below it, the session thirds at or below the fill, and the
    `movable` trades (either of the last two: the only ones the pp / pp_wbe rules can change)."""
    c: Counter = Counter()
    kind = facts["partial_kind"]
    at_cost = int(kind != "" and facts["exit_kind"] in ("stop", "day0_stop") and facts["exit_px"] is not None
                  and abs(facts["exit_px"] - t["fill"]) <= EXITPB_TOL)
    sess_le = int(kind == "session" and facts["partial_px"] is not None and facts["partial_px"] <= t["fill"])
    for cell in CELL_COLS:
        if not t[cell]:
            continue
        k = (t["entry"], t["K"], cell)
        c[k + ("fills",)] += 1
        c[k + ("mature",)] += int(ar["mature"])
        if kind:
            c[k + ("third",)] += 1
            c[k + ("third_" + kind,)] += 1
        c[k + ("stopped_after_third_at_cost",)] += at_cost
        c[k + ("stopped_after_third_le_fill",)] += facts["stopped_after_third_le_fill"]
        c[k + ("session_third_le_fill",)] += sess_le
        c[k + ("movable",)] += int(bool(sess_le or facts["stopped_after_third_le_fill"]))
    return c


def exitpb_reach_text(reach: Counter, period: str) -> str:
    doc = EXITPB_REACH_DOC.get(period, {})
    lines = [f"REACH from the control's rows (entry / level / cell: fills, mature, thirds (day0_r / r / session), stopped after the third at the "
             f"fill, at or below it, session thirds at or below the fill, movable = trades the pp / pp_wbe rules can change)"
             + (" - the registration's line beside" if doc else "")]
    keys = sorted({k[:3] for k in reach})
    for entry, k, cell in keys:
        if cell not in ("C1", "C0") or k != EXITPB_LEVEL:
            continue
        g = lambda m: reach.get((entry, k, cell, m), 0)
        ln = (f"  {entry} / {k} / {cell}: fills {g('fills'):,}, mature {g('mature'):,}, thirds {g('third'):,} ({g('third_day0_r'):,} / {g('third_r'):,} / "
              f"{g('third_session'):,}), stopped after the third at cost {g('stopped_after_third_at_cost'):,}, at or below the fill "
              f"{g('stopped_after_third_le_fill'):,}, session thirds <= fill {g('session_third_le_fill'):,}, movable {g('movable'):,}")
        d = doc.get(cell) if entry == EXITPB_ENTRY else None
        if d:
            ln += "  | registration: " + ", ".join(f"{kk} {v:,} ({'=' if g(kk) == v else 'reads ' + format(g(kk), ',')})" for kk, v in d.items())
        lines.append(ln)
    return "\n".join(lines)


def exitpb_row(t: dict, arm: ExitArm, raw: dict, n_fwd: int, cut: bool) -> list:
    a = arm_result(raw, width=t["width_pct"], n_fwd=n_fwd, horizon=HORIZON)
    f = exitpb_facts(raw["events"], t["fill"])
    row = {k: v for k, v in t.items() if k != "_pinned"}
    row.update(arm=arm.name, session_rule=arm.session_rule, stop_rule=arm.stop_rule, status=a["status"], realized_r=a["realized_r"],
               pnl_adr=a["pnl_adr"], acct_pct=a["acct_pct"], sessions_held=a["sessions_held"], mature=int(a["mature"]), open_mark=int(a["open_mark"]),
               fill_day_stop=int(a["status"] == "stopped_day0"), fwd_bars=n_fwd, fwd_hole=int(cut), **f)
    return _by_cols(row, EXITPB_TRADE_COLS)


def _exitpb_job(date_iso: str) -> tuple:
    """One fill date: the minute file once, every pinned fill of the date through the copy. `_G["exitpb_mode"]` 'parity' = the control
    alone against the pinned row and the module's walk (no new-arm number); 'full' = every arm, the parity check repeated on the control.
    Returns (rows gzip member, tally, problems, reach counter)."""
    D: Daily = _G["D"]
    trades = _G["by_date"][date_iso]
    blocks, _info = read_minute_file(_G["files"][date_iso], {t["ticker"] for t in trades})
    done, cal = _G["done"], D.cal
    mode, arms = _G["exitpb_mode"], _G["exitpb_arms"]
    rows, tally, problems, reach = [], Counter(), [], Counter()
    ctl = {EXITPB_CONTROL: EXITPB_ARMS[EXITPB_CONTROL]}
    for t in trades:
        mb, state = minutes_for(blocks, done, date_iso, t["ticker"])
        key = exitpb_trade_key(t)
        if mb is None:
            problems.append(f"{key}: minutes {state} - a pinned fill whose breakout-day minutes cannot be read")
            tally[("minutes", state)] += 1
            continue
        if t["entry"] == "h60":
            mb = h60_trim(mb, t["E"] in H60_EARLY_CLOSE)
        bars, cidx = _ticker_bars(t["ticker"])
        e = locate_breakout_index(cal, cidx, t["E"])
        closes_before = bars.c[:e + 1]
        fwd, cut = forward_window(bars, cidx, e, HORIZON)
        entry = {"fill": t["fill"], "stop": t["stop"], "fill_minute": t["walk_from"]}
        res = exitpb_walk_arms(entry, closes_before=closes_before, fwd=fwd, adr20=t["adr20"], minutes=mb, horizon=HORIZON,
                               arms=(ctl if mode == "parity" else arms))
        a = res[EXITPB_CONTROL]
        ar = arm_result(a, width=t["width_pct"], n_fwd=len(fwd), horizon=HORIZON)
        af = exitpb_facts(a["events"], t["fill"])
        problems += exitpb_compare_pinned(key, t["_pinned"], ar, af, len(fwd), cut)
        if mode == "parity":
            entry2 = {"status": "filled", "reason": None, "fill": t["fill"], "stop": t["stop"], "width_pct": t["width_pct"], "fill_minute": t["walk_from"],
                      "day0": cb.day0_walk(mb, fill_minute=t["walk_from"], stop=t["stop"])}
            ref = cb.walk_his_arms(entry2, closes_before=closes_before, fwd=fwd, adr20=t["adr20"], minutes=mb, horizon=HORIZON,
                                   arms={EXITPB_BASE.name: EXITPB_BASE})[EXITPB_BASE.name]
            problems += exitpb_compare_module(key, ref, a)
            reach.update(exitpb_reach_facts(t, ar, af))
            tally[("parity", t["entry"], t["K"])] += 1
            continue
        for name, raw in res.items():
            rows.append(exitpb_row(t, arms[name], raw, len(fwd), cut))
        tally[("walked", t["entry"], t["K"])] += 1
    return rows_to_gz(rows), tally, problems, reach


def exitpb_parity(prep: dict, workers: int, say) -> tuple:
    """Pass 1: the control alone over every pinned fill of the period -> (counts per (entry, K), problems, reach). Opens the daily export
    and the minute files; computes NO new-arm number and writes nothing."""
    t0 = time.time()
    if "D" not in _G or _G.get("exitpb_data") != str(prep["data"]):
        _G.update(D=load_daily(prep["data"] / "daily_closes_all.csv.gz"), exitpb_data=str(prep["data"]))
    inp = prep["inp"]
    _G.update(by_date=inp["by_date"], files=inp["files"], done=inp["done"], bars_cache={}, exitpb_mode="parity", exitpb_arms=EXITPB_ARMS)
    tally: Counter = Counter()
    problems: list = []
    reach: Counter = Counter()
    dates = list(inp["by_date"])
    for k, (_gz, ty, pr, rc) in enumerate(_pool_map(_exitpb_job, dates, workers), 1):
        tally.update(ty)
        problems += pr
        reach.update(rc)
        if k % 200 == 0 or k == len(dates):
            print(f"  parity {k}/{len(dates)} dates, {sum(n for kk, n in tally.items() if kk[0] == 'parity'):,} fills", flush=True)
    counts = {kk[1:]: n for kk, n in tally.items() if kk[0] == "parity"}
    say(f"[parity: {time.time() - t0:.0f}s]")
    return counts, problems, reach


def exitpb_walk_all(prep: dict, workers: int, period: str, say) -> tuple:
    """Pass 2: every arm over every pinned fill -> (trades path, tally, problems). Written to `.partial` and renamed only after every
    date is walked (the once-only protocol)."""
    t0 = time.time()
    if "D" not in _G or _G.get("exitpb_data") != str(prep["data"]):
        _G.update(D=load_daily(prep["data"] / "daily_closes_all.csv.gz"), exitpb_data=str(prep["data"]))
    inp = prep["inp"]
    _G.update(by_date=inp["by_date"], files=inp["files"], done=inp["done"], bars_cache={}, exitpb_mode="full", exitpb_arms=EXITPB_ARMS)
    tp = prep["out"] / f"trades_{period}_{EXITPB_NAME}.tsv.gz"
    tpp = partial_path(tp)
    tally: Counter = Counter()
    problems: list = []
    dates = list(inp["by_date"])
    with open(tpp, "wb") as tf:
        tf.write(rows_to_gz([EXITPB_TRADE_COLS]))
        for k, (gz, ty, pr, _rc) in enumerate(_pool_map(_exitpb_job, dates, workers), 1):
            tf.write(gz)
            tally.update(ty)
            problems += pr
            if k % 200 == 0 or k == len(dates):
                print(f"  walk {k}/{len(dates)} dates, {sum(n for kk, n in tally.items() if kk[0] == 'walked'):,} fills x {len(EXITPB_ARMS)} arms", flush=True)
    if problems:                                # the control differed mid-walk: the table is not a read
        tpp.unlink()
        return None, tally, problems
    os.replace(tpp, tp)
    say(f"[exit walks: {time.time() - t0:.0f}s]")
    return tp, tally, problems


# ── the self-checks (the registration's WOULD-FAIL-IF lines, on the written table) ─────────────────────────────────────────────
def exitpb_self_checks(df, period: str) -> tuple:
    """(problems, lines): every WOULD-FAIL-IF of the registration that the table can decide. A problem = a broken implementation: the
    report is not written. `df` = `exitpb_load_frame`'s frame."""
    problems, lines = [], []
    arm = df["arm"].astype(str)
    pk = df["partial_kind"].fillna("").astype(str)
    gated = arm.map(lambda n: EXITPB_ARMS[n].profit_gated).astype(bool)
    wbe = arm.map(lambda n: EXITPB_ARMS[n].stop_rule == "wbe").astype(bool)
    nobe = arm.map(lambda n: EXITPB_ARMS[n].stop_rule != "entry").astype(bool)
    # (a) a pp-family session third on a close <= the fill
    bad = df[gated & (pk == "session") & (df["partial_px"].astype(float) <= df["fill"].astype(float))]
    lines.append(f"(a) pp-family session thirds on a close <= the fill: {len(bad)} (must be 0)")
    if len(bad):
        problems.append(f"(a) {len(bad)} pp-family session thirds sold on a close at or below the fill")
    # (b) a wbe-family stop_to off the formula or below stop0
    w = df[wbe & df["stop_to"].notna()]
    if len(w):
        fill, s0, px, st = (w[c].to_numpy(dtype=float) for c in ("fill", "stop", "partial_px", "stop_to"))
        formula = np.maximum(s0, np.minimum(fill, fill - (px - fill) / 2.0))
        off = (np.abs(st - formula) > EXITPB_TOL * np.maximum(1.0, np.abs(formula))) | (st < s0 - EXITPB_TOL)
        n_off = int(off.sum())
    else:
        n_off = 0
    lines.append(f"(b) wbe-family stop_to levels off max(stop0, min(fill, fill - (p - fill)/2)) or below stop0: {n_off} of {len(w)} (must be 0)")
    if n_off:
        problems.append(f"(b) {n_off} wbe-family stop_to levels are not the registered formula")
    # (c) a wbe / stop0 trade with a day-0 third that ended stopped_day0 above stop0
    bad = df[nobe & (df["status"] == "stopped_day0") & (pk == "day0_r") & (df["exit_px"].astype(float) > df["stop"].astype(float) + EXITPB_TOL)]
    lines.append(f"(c) wbe / stop0 day-0 thirds stopped on day 0 above stop0: {len(bad)} (must be 0)")
    if len(bad):
        problems.append(f"(c) {len(bad)} wbe / stop0 trades with a day-0 third were stopped on day 0 above stop0")
    # (d) a trade the control stopped or cut with NO third: every arm equals it;  (e) the control trailed out after a +2R third or an
    #     above-fill session third: pp equals it
    A = df[arm == EXITPB_CONTROL].set_index("tkey")
    apk = A["partial_kind"].fillna("").astype(str)
    idx_d = A.index[(apk == "") & A["status"].isin(("stopped", "stopped_day0", "time_exit"))]
    for name in EXITPB_ARMS:
        if name == EXITPB_CONTROL:
            continue
        X = df[arm == name].set_index("tkey").reindex(idx_d)
        n_bad = int(((X["realized_r"].astype(float) - A.loc[idx_d, "realized_r"].astype(float)).abs() > EXITPB_TOL).sum() + X["realized_r"].isna().sum())
        lines.append(f"(d) {name} differs from A on a trade A stopped or cut with no third: {n_bad} of {len(idx_d)} (must be 0)")
        if n_bad:
            problems.append(f"(d) {name}: {n_bad} trades A stopped or cut with no third have a different R")
    idx_e = A.index[(A["status"] == "trailed") & (apk.isin(("day0_r", "r")) | ((apk == "session") & (A["partial_px"].astype(float) > A["fill"].astype(float))))]
    PP = df[arm == EXITPB_RULED].set_index("tkey").reindex(idx_e)
    n_bad = int(((PP["realized_r"].astype(float) - A.loc[idx_e, "realized_r"].astype(float)).abs() > EXITPB_TOL).sum() + PP["realized_r"].isna().sum())
    lines.append(f"(e) pp differs from A on a trade A trailed out after a +2R or above-fill session third: {n_bad} of {len(idx_e)} (must be 0)")
    if n_bad:
        problems.append(f"(e) pp: {n_bad} trades A trailed out after a +2R / above-fill third have a different R")
    # (f) the primary's >= 10R count never below the control's (per cell, the deciding entry and level, mature walks)
    PW = df[arm == EXITPB_PRIMARY].set_index("tkey")
    short = []
    for cell in CELL_COLS:
        for ent in EXITPB_ENTRIES:
            sel_a = A[(A["entry"].astype(str) == ent) & (A["K"].astype(str) == EXITPB_LEVEL) & (A[cell] == 1) & (A["mature"] == 1)]
            sel_p = PW[(PW["entry"].astype(str) == ent) & (PW["K"].astype(str) == EXITPB_LEVEL) & (PW[cell] == 1) & (PW["mature"] == 1)]
            na, npw = int((sel_a["realized_r"].astype(float) >= H60_TAIL_R).sum()), int((sel_p["realized_r"].astype(float) >= H60_TAIL_R).sum())
            if npw < na:
                short.append(f"{ent} {cell}: pp_wbe {npw} < A {na}")
    lines.append(f"(f) cells where the pp_wbe >= 10R count is below A's: {len(short)} (must be 0){(': ' + '; '.join(short)) if short else ''}")
    if short:
        problems.append(f"(f) the pp_wbe >= 10R count is below A's in {len(short)} cells")
    # (g) TSLA 2020-06-01 on the hourly-close fills (the pre period): no third on 06-04 (session 3), not stopped on 06-05 (session 4)
    if period == "pre":
        row = df[(df["ticker"] == EXITPB_TSLA[0]) & (df["E"] == EXITPB_TSLA[1]) & (df["K"].astype(str) == EXITPB_LEVEL) & (df["entry"].astype(str) == "h60")
                 & (arm == EXITPB_PRIMARY)]
        if not len(row):
            lines.append("(g) TSLA 2020-06-01 hourly-close fill: NOT FOUND (must exist)")
            problems.append("(g) the TSLA 2020-06-01 hourly-close fill is not in the table")
        else:
            r = row.iloc[0]
            kind, sess = str(r["partial_kind"]) if r["partial_kind"] == r["partial_kind"] else "", r["partial_session"]
            third_d4 = kind == "session" and int(float(sess)) == 3
            stopped_d5 = r["status"] == "stopped" and int(r["sessions_held"]) == 4
            lines.append(f"(g) TSLA 2020-06-01 under pp_wbe: third {kind or 'none'}{(' session ' + str(int(float(sess)))) if kind else ''}, "
                         f"status {r['status']} after {int(r['sessions_held'])} sessions, R {float(r['realized_r']):+.3f} "
                         f"(must be: no session-3 third, not stopped on session 4)")
            if third_d4 or stopped_d5:
                problems.append("(g) TSLA 2020-06-01 under pp_wbe took the session-3 third or was stopped on session 4")
    else:
        lines.append("(g) TSLA 2020-06-01: not in this period (the pre period's check)")
    return problems, lines


# ── the report ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def exitpb_load_frame(path: Path):
    df = read_tsv(path)
    df["tkey"] = df["ticker"].astype(str) + "|" + df["E"].astype(str) + "|" + df["K"].astype(str) + "|" + df["entry"].astype(str)
    for col in ("K", "entry", "arm", "fill_month"):
        df[col] = df[col].astype("category")
    return df


def exitpb_group_stats(g, a_r: dict, key: str, ci: bool = True) -> dict:
    """`h60_stats` (the registration's columns, the interval on the FILL month) plus the thirds by kind, the share stopped after the third at
    or below the fill, the be_above_close counts by kind and the >= 10R overlap with the control on the SAME trades."""
    s = h60_stats(g, key, ci)
    gm = g[g["mature"] == 1]
    n = len(gm)
    kinds = gm["partial_kind"].fillna("").astype(str)
    bk = gm["beabove_kind"].fillna("").astype(str)
    s.update(n_third=int((kinds != "").sum()), n_third_day0_r=int((kinds == "day0_r").sum()), n_third_r=int((kinds == "r").sum()),
             n_third_session=int((kinds == "session").sum()), share_third=(float((kinds != "").mean()) if n else None),
             n_stopped_after_third_le_fill=int(gm["stopped_after_third_le_fill"].astype(int).sum()),
             share_stopped_after_third_le_fill=(float(gm["stopped_after_third_le_fill"].astype(float).mean()) if n else None),
             n_beabove_session=int((bk == "session").sum()), n_beabove_r=int((bk == "r").sum()))
    r = gm["realized_r"].to_numpy(dtype=float)
    ra = np.array([a_r.get(k, np.nan) for k in gm["tkey"]], dtype=float) if n else np.zeros(0)
    with np.errstate(invalid="ignore"):
        s.update(n_ge10=int((r >= H60_TAIL_R).sum()), n_ge10_a=int(np.nansum(ra >= H60_TAIL_R)), n_ge10_both=int(((r >= H60_TAIL_R) & (ra >= H60_TAIL_R)).sum()))
    return s


def exitpb_delta(gx, gy, key: str) -> dict:
    """R(x) - R(y) per trade on the SAME fills, both walks mature (a trade with an open mark on either arm is excluded and counted); the
    month-block interval on the FILL month; the verdict on the n floor (`h60_pair_verdict`: lower end > 0 win, upper end < 0 loss)."""
    m = gx[["tkey", "mature", "realized_r", "fill_month"]].merge(gy[["tkey", "mature", "realized_r"]], on="tkey", suffixes=("_x", "_y"))
    both = m[(m["mature_x"] == 1) & (m["mature_y"] == 1)]
    d = both["realized_r_x"].to_numpy(dtype=float) - both["realized_r_y"].to_numpy(dtype=float)
    ci = h60_pair_ci(d, both["fill_month"].astype(str).to_numpy(), key=key)
    return {**ci, "n_excluded_open": int(len(m) - len(both)), "n_differ": int((np.abs(d) > EXITPB_TOL).sum()), "verdict": h60_pair_verdict(ci, EXITPB_MIN_N)}


def exitpb_consequence(c1_verdict: str, c0_hi) -> tuple:
    """The registration's consequence table: (the exit carried into every next registration, the row's text)."""
    if c1_verdict == "win":
        return EXITPB_PRIMARY, "win -> pp_wbe"
    if c1_verdict == "loss":
        return EXITPB_RULED, "loss -> pp (his ruling stands; the stop goes to the entry price after the third)"
    if _num_ok(c0_hi) and c0_hi < 0:
        return EXITPB_RULED, f"can't tell, and C0's interval upper end {c0_hi:+.3f} < 0 -> pp"
    return EXITPB_PRIMARY, f"can't tell -> pp_wbe (his proposal, not shown worse at scale: C0 upper end {('%+.3f' % c0_hi) if _num_ok(c0_hi) else 'unknown'})"


def exitpb_report_rows(df, period: str) -> tuple:
    """(rows, deltas, verdicts): per (entry, cell, K = tl, arm) the statistics over the mature walks with the interval ('all'), the year
    slice on the control and the primary (orh5), the cell verdict under the primary (orh5 / tl) against C0 under the primary; every
    registered delta on C1 and C0 per entry; `verdicts` = {entry: {"c1": the primary's C1 row, "c0": ..., "deltas": {...}}}."""
    rows, deltas, verdicts = [], [], {}
    arm_s = df["arm"].astype(str)
    for ent in EXITPB_ENTRIES:
        sub = df[(df["entry"].astype(str) == ent) & (df["K"].astype(str) == EXITPB_LEVEL)]
        if not len(sub):
            continue
        A = sub[arm_s[sub.index] == EXITPB_CONTROL]
        a_r = {k: float(r) for k, r, m in zip(A["tkey"], A["realized_r"], A["mature"]) if int(m) == 1}
        idx: dict = {}
        for name in EXITPB_ARMS:
            g_arm = sub[arm_s[sub.index] == name]
            for cell in CELL_COLS:
                g = g_arm[g_arm[cell] == 1]
                if not len(g):
                    continue
                r = {"period": period, "entry": ent, "cell": cell, "K": EXITPB_LEVEL, "arm": name, "slice": "all", "value": "",
                     **exitpb_group_stats(g, a_r, key=f"exitpb|{period}|{ent}|{cell}|{EXITPB_LEVEL}|{name}")}
                idx[(cell, name)] = r
                rows.append(r)
                if ent == EXITPB_ENTRY and name in (EXITPB_CONTROL, EXITPB_PRIMARY):
                    gm = g[g["mature"] == 1]
                    for val, gg in gm.groupby("year"):
                        rows.append({"period": period, "entry": ent, "cell": cell, "K": EXITPB_LEVEL, "arm": name, "slice": "year", "value": int(val),
                                     **exitpb_group_stats(gg, a_r, key="", ci=False)})
        base = idx.get(("C0", EXITPB_PRIMARY))
        for cell in CELL_COLS:
            r = idx.get((cell, EXITPB_PRIMARY))
            if r is None:
                continue
            if cell == "C0":
                r["verdict"], r["why"] = "baseline", ""
            elif cell in PRE_DECIDING and ent == EXITPB_ENTRY:
                r["verdict"], r["why"] = h60_verdict(r, base, EXITPB_MIN_N)
            else:
                r["verdict"], r["why"] = "report", ""
        dv: dict = {}
        for cell in EXITPB_DELTA_CELLS:
            for x, y in EXITPB_DELTAS:
                gx = sub[(arm_s[sub.index] == x) & (sub[cell] == 1)]
                gy = sub[(arm_s[sub.index] == y) & (sub[cell] == 1)]
                d = exitpb_delta(gx, gy, key=f"exitpb_delta|{period}|{ent}|{cell}|{EXITPB_LEVEL}|{x}-{y}")
                deciding = int(ent == EXITPB_ENTRY and (x, y) == EXITPB_DELTAS[0])
                dv[(cell, x, y)] = d
                deltas.append({"period": period, "entry": ent, "cell": cell, "K": EXITPB_LEVEL, "delta": f"{x}-{y}", "x": x, "y": y, "n": d["n"],
                               "n_excluded_open": d["n_excluded_open"], "n_differ": d["n_differ"], "mean": d.get("mean"), "ci_lo": d.get("lo"),
                               "ci_hi": d.get("hi"), "verdict": d["verdict"], "deciding": deciding})
        verdicts[ent] = {"c1": idx.get(("C1", EXITPB_PRIMARY)) or {"n": 0, "verdict": "CAN'T TELL", "why": "n = 0 < 30"},
                         "c0": base, "deltas": dv, "idx": idx}
    return rows, deltas, verdicts


def exitpb_expectations(v: dict) -> list:
    """The registration's two expectations (fixed before the run; a missed one changes no rule and is reported first): C0 delta(pp_wbe -
    pp) >= 0 at the point estimate; the median sessions held under pp_wbe >= A's (reported on C1 and on C0)."""
    exp = []
    d = v["deltas"].get(("C0", EXITPB_PRIMARY, EXITPB_RULED), {})
    m = d.get("mean")
    exp.append(("MET" if _num_ok(m) and m >= 0 else ("MISSED" if _num_ok(m) else "NO DATA")) +
               f": C0 delta(pp_wbe - pp) point estimate {('%+.4f' % m) if _num_ok(m) else '-'}R on {d.get('n', 0):,} trades (expected >= 0: it keeps runners the "
               f"entry-price stop took out and costs only on trades that fall from the third to the original stop)")
    for cell in EXITPB_DELTA_CELLS:
        p, a = v["idx"].get((cell, EXITPB_PRIMARY), {}), v["idx"].get((cell, EXITPB_CONTROL), {})
        hp, ha = p.get("median_held"), a.get("median_held")
        exp.append(("MET" if _num_ok(hp) and _num_ok(ha) and hp >= ha else ("MISSED" if _num_ok(hp) and _num_ok(ha) else "NO DATA")) +
                   f": {cell} median sessions held under pp_wbe {('%.0f' % hp) if _num_ok(hp) else '-'} vs A's {('%.0f' % ha) if _num_ok(ha) else '-'} (expected >=)")
    return exp


def _exitpb_line(r: dict, first) -> list:
    g = r.get
    return [first, g("n_filled", 0), g("n", 0), g("n_open", 0), _num(g("mean_r")), _ci(r), _pct(g("win_rate")), _num(g("avg_win"), 2), _num(g("avg_loss"), 2),
            "" if g("share_ge5") is None else f"{100 * g('share_ge5'):.1f}", "" if g("share_ge10") is None else f"{100 * g('share_ge10'):.1f}",
            "" if g("share_ge20") is None else f"{100 * g('share_ge20'):.1f}", _num(g("sum_r"), 1), _pct(g("top2_share")), _num(g("mean_pnl_adr")),
            "" if g("median_held") is None else f"{g('median_held'):.0f}",
            "" if g("n") is None else f"{g('n_third', 0)} ({g('n_third_day0_r', 0)}/{g('n_third_r', 0)}/{g('n_third_session', 0)})",
            _pct(g("share_stopped_after_third_le_fill")), f"{g('n_beabove_session', 0)}/{g('n_beabove_r', 0)}",
            "" if g("n") is None else f"{g('n_ge10', 0)} / A {g('n_ge10_a', 0)} / both {g('n_ge10_both', 0)}",
            "" if g("tail_n") is None else f"{g('tail_n')}: {g('tail_tickers')}t/{g('tail_months')}m", g("verdict", ""), g("why", "")]


EXITPB_HEADER = ["cell", "fills", "n", "open", "mean R", "95% CI", "win", "avg win", "avg loss", ">=5R/100", ">=10R/100", ">=20R/100", "total R",
                 "top-2% share", "pnl_adr", "med held", "thirds (d0/r/sess)", "stopped after third <= fill", "beabove sess/r", ">=10R vs A",
                 ">=10R spread", "VERDICT", "why"]


def _exitpb_delta_line(cell: str, x: str, y: str, d: dict) -> list:
    return [f"{cell} {x} - {y}", d["n"], d["n_excluded_open"], d["n_differ"], _num(d.get("mean"), 4), _ci({"ci_lo": d.get("lo"), "ci_hi": d.get("hi")}), d["verdict"]]


EXITPB_DELTA_HEADER = ["delta", "n trades", "excl open", "n differing", "mean delta R", "95% CI", "verdict"]


def exitpb_stamps(dirs: dict, period: str, c1_delta_mean) -> list:
    """The other periods' deciding-delta sign against this one's, when their verdict files exist (decides nothing)."""
    import json
    lines = []
    for other in EXITPB_PERIODS:
        if other == period:
            continue
        p = h60_period_dir(dirs, other) / "out" / f"{EXITPB_NAME}_verdict_{other}.json"
        if not p.exists():
            lines.append(f"{other}: no verdict file yet (not run) - no stamp")
            continue
        o = json.loads(p.read_text())
        m = o.get("delta_c1", {}).get("mean")
        lines.append(f"{other}: C1 delta(pp_wbe - pp) {h60_sign(m)} ({_num(m, 4)}) -> {'agrees' if h60_sign(m) == h60_sign(c1_delta_mean) else 'contradicts'} (decides nothing)")
    return lines


def exitpb_report_text(period: str, rows: list, verdicts: dict, notes: list, check_lines: list, stamps: list) -> str:
    out: list = []
    A = out.append
    decides = period == "discovery"
    A(f"#702 EXIT READ - his partial and the stop after it, on {period} ({'2022-03-28..2024-12-31, DECIDES' if decides else ('2017-21, beside' if period == 'pre' else '2025-01..2026-10, descriptive only')}). "
      f"Registered before any outcome: docs/analysis/{EXITPB_DOC}. Measurement only: nothing here switches the deciding comparison, the primary arm, the entry, "
      f"the stop, a cell, a period, the horizon, the seed, the draw count, the n floor or the open-mark exclusion.")
    A(f"POPULATION: the pinned P5 fills (level {EXITPB_LEVEL}, entry ORH5, the low-of-day stop no wider than one ADR20, the spec key's first break per base) - "
      f"every arm walks the SAME fills, so the comparison is per trade; the pinned hourly-close fills (entry h60) are walked beside, descriptively. A group is "
      f"the MATURE walks only; an open mark is counted, never in a number. ARMS: A = {EXITPB_BASE.name} (the control: the session-3 third whatever the "
      f"price, stop to the fill after any third); pp = his RULING (the session-3 third only on a close above the fill, else skipped, the +2R leg stays "
      f"armed; stop to the fill after a third); pp_wbe = the PRIMARY: pp + his PROPOSAL (after a third sold at p the stop rests at max(stop0, min(fill, "
      f"fill - (p - fill)/2)), the whole-trade breakeven); beside: wbe (A's partial rule + the wbe stop), pp_s0 (pp with the stop left at stop0 after any "
      f"third), pp5_wbe (the first close in sessions 3-5 above the fill, then the wbe stop). Common to all: 1/3; the +2R leg (day 0 on the minutes); "
      f"the +1R-by-session-3 cut; the 20-day trail filled at the next open; R against the entry stop; horizon 120. The pp-family trail is live from "
      f"session 3 whether or not the third sold.")
    A(f"INTERVAL RECIPE (the independent re-derivation reproduces it with no runner code): month-block bootstrap of the mean - blocks = the FILL month "
      f"(E's month), {BOOT_DRAWS:,} resamples of as many blocks as there are months, with replacement, each resample's mean = sum of the drawn blocks' "
      f"values / their trade count; the 2.5 / 97.5 percentiles (numpy.percentile, linear); generator numpy.random.default_rng([{BOOT_SEED}, "
      f"zlib.crc32(key)]) with key 'exitpb|<period>|<entry>|<cell>|{EXITPB_LEVEL}|<arm>' for a cell's R and 'exitpb_delta|<period>|<entry>|<cell>|"
      f"{EXITPB_LEVEL}|<x>-<y>' for a per-trade delta R(x) - R(y) (both walks mature); the stream is drawn as integers(0, n_months, size=({BOOT_DRAWS}, n_months)). "
      f"The deciding delta: pp_wbe - pp on C1, n floor {EXITPB_MIN_N}; lower end > 0 = wbe WINS, upper end < 0 = wbe LOSES, else can't tell; C0 the same, read "
      f"when C1 can't tell.")
    for n_ in notes:
        A(n_)
    A("")
    for ent in EXITPB_ENTRIES:
        v = verdicts.get(ent)
        if v is None:
            continue
        idx, dv = v["idx"], v["deltas"]
        A(f"========== ENTRY {ent} / level {EXITPB_LEVEL}{' - DECIDES' if (ent == EXITPB_ENTRY and decides) else (' - the ORH5 fills, beside' if ent == EXITPB_ENTRY else ' - the hourly-close fills, DESCRIPTIVE')} ==========")
        exp = exitpb_expectations(v)
        A("EXPECTATIONS (fixed before the run; a missed one is reported first and changes NO rule):")
        for e in [e for e in exp if e.startswith("MISSED")] + [e for e in exp if not e.startswith("MISSED")]:
            A("  " + e)
        A("")
        A("THE DECIDING EXIT BAR - per trade delta = R(pp_wbe) - R(pp) on the SAME fills (the ruled rule with vs without his stop); a trade with an open mark "
          "on either arm excluded and counted; 'n differing' = trades whose R differs at all")
        body = [_exitpb_delta_line(cell, EXITPB_PRIMARY, EXITPB_RULED, dv[(cell, EXITPB_PRIMARY, EXITPB_RULED)]) for cell in EXITPB_DELTA_CELLS
                if (cell, EXITPB_PRIMARY, EXITPB_RULED) in dv]
        A(table(body, EXITPB_DELTA_HEADER))
        d1, d0 = dv.get(("C1", EXITPB_PRIMARY, EXITPB_RULED), {}), dv.get(("C0", EXITPB_PRIMARY, EXITPB_RULED), {})
        if ent == EXITPB_ENTRY and decides:
            carried, text = exitpb_consequence(d1.get("verdict", "can't tell"), d0.get("hi"))
            A(f"C1 VERDICT on the stop change: {d1.get('verdict')} (n {d1.get('n')}, mean {_num(d1.get('mean'), 4)} {_ci({'ci_lo': d1.get('lo'), 'ci_hi': d1.get('hi')})}); "
              f"C0: {d0.get('verdict')} (n {d0.get('n')}, mean {_num(d0.get('mean'), 4)} {_ci({'ci_lo': d0.get('lo'), 'ci_hi': d0.get('hi')})})")
            A(f"CONSEQUENCE (the registration's table): {text}; the exit carried into every next registration = {carried}; pp replaces A in every case "
              f"(his ruling); paper: nothing from this read.")
        else:
            A(f"STAMP (decides nothing): C1 delta(pp_wbe - pp) {h60_sign(d1.get('mean'))} ({_num(d1.get('mean'), 4)}, n {d1.get('n')}, {d1.get('verdict')}); "
              f"C0 {h60_sign(d0.get('mean'))} ({_num(d0.get('mean'), 4)}, n {d0.get('n')}, {d0.get('verdict')})")
        if ent == EXITPB_ENTRY:
            for s in stamps:
                A("  " + s)
        A("")
        A("REPORTED, NEVER DECIDING - every registered delta per trade (x - y), C1 and C0")
        body = [_exitpb_delta_line(cell, x, y, dv[(cell, x, y)]) for cell in EXITPB_DELTA_CELLS for x, y in EXITPB_DELTAS if (cell, x, y) in dv]
        A(table(body, EXITPB_DELTA_HEADER))
        A("")
        A(f"CELL VERDICT under pp_wbe (whether the SETUP passes with his exit; the hourly-close read's bars word for word: PASS = n >= {EXITPB_MIN_N}, interval lower end > 0, "
          f"ADR P&L > 0, beats C0 under the same exit on mean R AND the >= 5R share, >= 10R trades from >= {H60_TAIL_TICKERS} tickers AND >= {H60_TAIL_MONTHS} months "
          f"counting only stops >= {H60_TAIL_WIDTH_ADR} ADR20 wide; FAIL = n >= {EXITPB_MIN_N} AND (upper end < 0 OR not beating C0 on mean R); else CAN'T TELL)"
          + ("" if ent == EXITPB_ENTRY else " - labels only on the hourly-close fills"))
        body = [_exitpb_line(idx[(cell, EXITPB_PRIMARY)], cell) for cell in PRE_CELL_ORDER if (cell, EXITPB_PRIMARY) in idx]
        A(table(body, EXITPB_HEADER))
        A("")
        A("PER ARM x CELL (mature walks; 'thirds' = trades that sold a third, by kind: the day-0 +2R touch / a later +2R touch / the session close; "
          "'stopped after third <= fill' = share of the mature walks stopped after their third at or below the fill; 'beabove' = be_above_close counts by the "
          "kind of third it followed (session / +2R); '>=10R vs A' = the arm's >= 10R trades, A's on the same trades, and the overlap)")
        for name in EXITPB_ARMS:
            body = [_exitpb_line(idx[(cell, name)], cell) for cell in PRE_CELL_ORDER if (cell, name) in idx]
            if body:
                A(f"  arm {name} ({'PRIMARY' if name == EXITPB_PRIMARY else ('his ruling' if name == EXITPB_RULED else ('control' if name == EXITPB_CONTROL else 'beside'))}; "
                  f"session leg {EXITPB_ARMS[name].session_rule}, stop after the third {EXITPB_ARMS[name].stop_rule})")
                A(table(body, EXITPB_HEADER))
        A("")
        if ent == EXITPB_ENTRY:
            A("BE_ABOVE_CLOSE by kind (A's registration counts: 2022-24 C1 1 / C0 112 session kind, C1 1 / C0 27 +2R kind; 2017-21 0 / 170 and 0 / 48): "
              "session third sold below cost / +2R third on a bar closing under the fill - impossible under pp_wbe and pp5_wbe, the +2R kind remains under pp")
            body = [[f"{cell} {name}", idx[(cell, name)].get("n_beabove_session", 0), idx[(cell, name)].get("n_beabove_r", 0)]
                    for cell in EXITPB_DELTA_CELLS for name in EXITPB_ARMS if (cell, name) in idx]
            A(table(body, ["cell arm", "session kind", "+2R kind"]))
            A("")
            A(f"SLICES - year, arms A and pp_wbe (orh5 / {EXITPB_LEVEL}); each cell is n / mean R / share >= 5R over the mature walks")
            for name in (EXITPB_CONTROL, EXITPB_PRIMARY):
                rr = [r for r in rows if r["entry"] == ent and r["slice"] == "year" and r["arm"] == name]
                if not rr:
                    continue
                vals = sorted({r["value"] for r in rr})
                body = []
                for cell in PRE_CELL_ORDER:
                    ln = [cell]
                    for val in vals:
                        m = [r for r in rr if r["cell"] == cell and r["value"] == val]
                        ln.append("-" if not m else ("0" if not m[0]["n"] else f"{m[0]['n']}/{_num(m[0].get('mean_r'), 2)}/{_pct(m[0].get('share_ge5'))}"))
                    body.append(ln)
                A(f"  arm {name}")
                A(table(body, ["cell"] + [str(x) for x in vals]))
            A("")
    A("IMPLEMENTATION CHECKS (the registration's WOULD-FAIL-IF lines, on this table; every one must hold or the report is not written):")
    for ln in check_lines:
        A("  " + ln)
    return "\n".join(out)


# ── the guards and the stage ─────────────────────────────────────────────────────────────────────────────────────────────────────
def exitpb_frozen_files(dirs: dict, repo: Path = REPO) -> dict:
    """{footer label: path} of the exit read's freeze - the registration's pin list: both pinned P5 tables and both hourly-close tables
    per data dir, both daily exports, both minute trees, the candidates files, the module, this runner. The doc body is hashed by
    `freeze_check`."""
    d, p = Path(dirs["cb702"]), Path(dirs["cb702_pre"])
    out = {"module": Path(repo) / MODULE_REL, "runner": Path(__file__).resolve(),
           "cb702/daily_closes_all.csv.gz": d / "daily_closes_all.csv.gz", "cb702_pre/daily_closes_all.csv.gz": p / "daily_closes_all.csv.gz"}
    for name in ("candidates.tsv", "candidates_com_comb.tsv", f"trades_discovery_{P5_NAME}.tsv.gz", f"trades_holdout_{P5_NAME}.tsv.gz",
                 "trades_discovery_h60.tsv.gz", "trades_holdout_h60.tsv.gz"):
        out[f"cb702/out/{name}"] = d / "out" / name
    for name in ("candidates_tl_com.tsv", f"trades_pre_{P5_NAME}.tsv.gz", "trades_pre_h60.tsv.gz"):
        out[f"cb702_pre/out/{name}"] = p / "out" / name
    out["cb702/minutes (tree)"] = d / "minutes"
    out["cb702_pre/minutes (tree)"] = p / "minutes"
    return out


def exitpb_module_problem(repo: Path = REPO) -> "str | None":
    """The registration's hard pin: the module must equal `EXITPB_MODULE_SHA` (the live shadow's module), footer or no footer."""
    p = Path(repo) / MODULE_REL
    if not p.is_file():
        return f"module missing: {p}"
    got = sha256_file(p)
    if got != EXITPB_MODULE_SHA:
        return f"module sha256 {got[:12]}... is not the registered {EXITPB_MODULE_SHA[:12]}... - consolidation_breakout.py was edited; the read does not open"
    return None


def exitpb_existing_outputs(out: Path, period: str) -> list:
    """The once-only guard: the period's new trades table, or the `.partial` a crashed run left behind."""
    return existing_outputs(out, (f"trades_{period}_{EXITPB_NAME}.tsv.gz",))


def exitpb_prepare(dirs: dict, period: str) -> dict:
    """The period's pinned fills and their minute inputs. Opens the two pinned trades tables and the minute directory's log; no daily
    bar and no minute row."""
    d = h60_period_dir(dirs, period)
    out = d / "out"
    trades = exitpb_pinned_trades(out, period)
    return {"data": d, "out": out, "trades": trades, "inp": minute_inputs(trades, d / "minutes")}


def run_exit_read(args) -> int:
    """`exit-read --period P` - BUILT, NOT RUN. exit 2 on: a refused option, the module not equal to the registered sha, a freeze problem,
    missing minute pairs, outputs (or a crashed run's `.partial`) that exist, `--prereg` on a real run; exit 3 when the parity check (P1 /
    P2, and the copy against the module) or an implementation check fails (no report written). `--print-pins` prints the footer lines;
    `--dry-run` counts only (the pinned tables, no daily bar or minute row); `--parity-only` runs pass 1 alone - the control on every
    pinned fill, the match / mismatch counts and the reach line printed - computes no new-arm number and writes nothing (the footer
    freeze check is not run for it: the footer carries no pins before the freeze commit; the module sha is still hard-checked)."""
    T0 = time.time()
    dirs = h60_dirs(args)
    data = dirs["cb702"]
    if getattr(args, "print_pins", False):
        doc = registration_doc_path(args, EXITPB_DOC)
        lines = pin_lines(data, REPO, files=exitpb_frozen_files(dirs, REPO))
        lines.append(f"- doc body sha256: `{doc_body_sha(doc.read_text(encoding='utf-8')) if doc.is_file() else 'MISSING'}`")
        print("\n".join(lines))
        return 0
    period = getattr(args, "period", None)
    if period not in EXITPB_PERIODS:
        print(f"REFUSED: --period is required: one of {EXITPB_PERIODS}", file=sys.stderr)
        return 2
    dry, no_fc, parity_only = getattr(args, "dry_run", False), getattr(args, "no_freeze_check", False), getattr(args, "parity_only", False)
    if getattr(args, "prereg", None) and not dry:
        print(f"REFUSED: --prereg is honoured only with --print-pins or --dry-run - the read pins the registration doc at docs/analysis/{EXITPB_DOC} itself",
              file=sys.stderr)
        return 2
    bad = h60_option_problems(args, data)
    if bad:
        print("REFUSED: the exit read runs only in its registered form:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 2
    if no_fc and not dry:
        print("REFUSED: --no-freeze-check is honoured only together with --dry-run", file=sys.stderr)
        return 2
    mp_ = exitpb_module_problem(REPO)
    if mp_:
        print(f"REFUSED: {mp_}", file=sys.stderr)
        return 2
    if not no_fc and not parity_only:
        problems = freeze_check(doc=registration_doc_path(args, EXITPB_DOC), data=data, repo=REPO, files=exitpb_frozen_files(dirs, REPO))
        if problems:
            print("REFUSED: the freeze check failed - the read is not opened:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 2
    prep = exitpb_prepare(dirs, period)
    out, trades, inp = prep["out"], prep["trades"], prep["inp"]
    small = HERE / "out"
    existing = exitpb_existing_outputs(out, period)
    counts = Counter((t["entry"], t["K"]) for t in trades)
    pop = ", ".join(f"{e}/{k} {n:,}" for (e, k), n in sorted(counts.items()))
    if dry:
        print(f"EXIT-READ DRY RUN (freeze check {'SKIPPED' if no_fc else 'passed'}; module sha {EXITPB_MODULE_SHA[:12]}... ok; counts only - no daily bar, minute row "
              f"or outcome was opened): period {period}: {len(trades):,} pinned fills ({pop}) on {len(inp['by_date']):,} dates, {len(inp['pairs']):,} (date, ticker) "
              f"pairs; pairs NOT logged in _done.psv: {len(inp['missing']):,}, logged ok with no file: {len(inp['lost']):,} -> "
              f"{'the run would REFUSE' if (inp['missing'] or inp['lost']) else 'complete'}; outputs already on disk: {[q.name for q in existing] or 'none'}"
              f"{' -> the run would REFUSE (read once)' if existing else ''}. Would write {out / f'trades_{period}_{EXITPB_NAME}.tsv.gz'}, "
              f"{out / f'{EXITPB_NAME}_report_{period}.tsv'}, {out / f'{EXITPB_NAME}_deltas_{period}.tsv'}, {out / f'{EXITPB_NAME}_verdict_{period}.txt'} and the small "
              f"copies under {small}; arms {', '.join(EXITPB_ARMS)}.")
        return 0
    if not trades:
        print(f"REFUSED: no pinned fill of {period} in {out}", file=sys.stderr)
        return 2
    if inp["missing"] or inp["lost"]:
        print(f"REFUSED: {len(inp['missing']):,} of {len(inp['pairs']):,} (date, ticker) pairs are not logged in {inp['minutes_dir'] / '_done.psv'}"
              + (f"; {len(inp['lost']):,} more are logged ok on a date that has no minute file" if inp["lost"] else "") + ". A partial read is never run", file=sys.stderr)
        return 2
    if existing and not parity_only:
        crashed = [q for q in existing if q.name.endswith(".partial")]
        if crashed:
            print(f"REFUSED: {crashed[0]} is what a CRASHED exit read left behind - it holds some outcomes. The read is run ONCE per period: the operator "
                  f"inspects it and removes it by hand before any re-run", file=sys.stderr)
        else:
            print(f"REFUSED: the exit read's outcomes are read ONCE per period and {existing[0]} already exists", file=sys.stderr)
        return 2
    log: list = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        log.append(msg)

    say(f"EXIT READ (#702){' - PARITY ONLY' if parity_only else ''}: period {period}; {len(trades):,} pinned fills ({pop}) on {len(inp['by_date']):,} dates, "
        f"{len(inp['pairs']):,} pairs all logged; freeze check {'NOT RUN (parity only)' if parity_only else ('SKIPPED' if no_fc else 'passed')}; module sha256 "
        f"{sha256_file(Path(REPO) / MODULE_REL)} (registered), runner sha256 {sha256_file(Path(__file__))}")
    # pass 1: parity, before any new-arm number
    pc, problems, reach = exitpb_parity(prep, args.workers, say)
    n_par = sum(pc.values())
    if problems:
        say(f"PARITY FAILED: {len(problems):,} mismatches over {n_par:,} fills - the copy is not the registered walk; nothing is written. First 20:")
        for p in problems[:20]:
            say("  - " + p)
        if not parity_only:
            small.mkdir(parents=True, exist_ok=True)
            (small / f"{EXITPB_NAME}_summary_{period}.txt").write_text("\n".join(log) + "\n")
        return 3
    say("PARITY: " + "; ".join(f"P{1 if e == 'orh5' else 2} {e}/{k}: {n:,} match, 0 mismatch" for (e, k), n in sorted(pc.items()))
        + f" (status, maturity, sessions held, third kind and session, be_above_close, forward window, R to {EXITPB_TOL:g}; and the module's own walk event for event)")
    say(exitpb_reach_text(reach, period))
    if parity_only:
        say(f"WALL TIME: {time.time() - T0:.0f}s total (no new-arm number computed; nothing written)")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    # pass 2: every arm
    tp, tally, problems = exitpb_walk_all(prep, args.workers, period, say)
    if problems or tp is None:
        say(f"PARITY FAILED in the full walk: {len(problems):,} mismatches - nothing kept")
        (small / f"{EXITPB_NAME}_summary_{period}.txt").write_text("\n".join(log) + "\n")
        return 3
    say(f"WROTE {tp} ({sum(n for k, n in tally.items() if k[0] == 'walked'):,} fills x {len(EXITPB_ARMS)} arms)")
    df = exitpb_load_frame(tp)
    cp, check_lines = exitpb_self_checks(df, period)
    for ln in check_lines:
        say("  " + ln)
    if cp:
        say(f"IMPLEMENTATION CHECK FAILED ({len(cp)}): " + "; ".join(cp) + " - the report is NOT written (the table stays for inspection; the operator removes it by hand before any re-run)")
        (small / f"{EXITPB_NAME}_summary_{period}.txt").write_text("\n".join(log) + "\n")
        return 3
    rows, deltas, verdicts = exitpb_report_rows(df, period)
    main_v = verdicts.get(EXITPB_ENTRY, {})
    d1 = main_v.get("deltas", {}).get(("C1", EXITPB_PRIMARY, EXITPB_RULED), {})
    d0 = main_v.get("deltas", {}).get(("C0", EXITPB_PRIMARY, EXITPB_RULED), {})
    stamps = exitpb_stamps(dirs, period, d1.get("mean"))
    notes = [f"DATA CHECKS: freeze {'SKIPPED' if no_fc else 'passed'}; module {EXITPB_MODULE_SHA[:12]}... equal; parity P1 / P2 {n_par:,} fills, 0 mismatches; "
             f"implementation checks passed; rows walked {sum(n for k, n in tally.items() if k[0] == 'walked'):,} x {len(EXITPB_ARMS)} arms"]
    text = exitpb_report_text(period, rows, verdicts, notes, check_lines, stamps)
    name = f"{EXITPB_NAME}_report_{period}"
    write_tsv(out / f"{name}.tsv", rows, EXITPB_REPORT_COLS)
    write_tsv(out / f"{EXITPB_NAME}_deltas_{period}.tsv", deltas, EXITPB_DELTA_COLS)
    compact = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows if r["slice"] == "all"]
    write_tsv(small / f"{name}.tsv", compact, EXITPB_REPORT_COLS)
    write_tsv(small / f"{EXITPB_NAME}_deltas_{period}.tsv", [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in deltas], EXITPB_DELTA_COLS)
    (small / f"{name}.txt").write_text(text + "\n")
    (out / f"{name}.txt").write_text(text + "\n")
    print(text)
    import json
    c1 = main_v.get("c1", {})
    carried, ctext = exitpb_consequence(d1.get("verdict", "can't tell"), d0.get("hi")) if period == "discovery" else (None, "decides nothing")
    vj = {"period": period, "delta_c1": {k: d1.get(k) for k in ("n", "mean", "lo", "hi", "verdict", "n_excluded_open", "n_differ")},
          "delta_c0": {k: d0.get(k) for k in ("n", "mean", "lo", "hi", "verdict", "n_excluded_open", "n_differ")},
          "cell_c1_pp_wbe": {"n": c1.get("n"), "mean_r": c1.get("mean_r"), "ci": [c1.get("ci_lo"), c1.get("ci_hi")], "verdict": c1.get("verdict"), "why": c1.get("why")},
          "consequence": ctext, "carried_exit": carried}
    vlines = [f"#702 EXIT READ VERDICT FILE - period {period} - written {time.strftime('%Y-%m-%d')}",
              f"C1 delta(pp_wbe - pp): {d1.get('verdict')} (n {d1.get('n')}, mean {_num(d1.get('mean'), 4)} {_ci({'ci_lo': d1.get('lo'), 'ci_hi': d1.get('hi')})}); "
              f"C0: {d0.get('verdict')} (n {d0.get('n')}, mean {_num(d0.get('mean'), 4)} {_ci({'ci_lo': d0.get('lo'), 'ci_hi': d0.get('hi')})}); "
              f"C1 cell under pp_wbe: {c1.get('verdict')} ({c1.get('why')}); consequence: {ctext}; carried exit: {carried}"]
    (out / f"{EXITPB_NAME}_verdict_{period}.json").write_text(json.dumps(vj, indent=1) + "\n")
    (out / f"{EXITPB_NAME}_verdict_{period}.txt").write_text("\n".join(vlines) + "\n")
    (small / f"{EXITPB_NAME}_verdict_{period}.txt").write_text("\n".join(vlines) + "\n")
    say(f"WROTE {out / (name + '.tsv')} ({len(rows):,} rows), {out / f'{EXITPB_NAME}_deltas_{period}.tsv'} ({len(deltas):,} rows), {small / (name + '.txt')}, "
        f"{out / f'{EXITPB_NAME}_verdict_{period}.txt'}")
    say(f"WALL TIME: {time.time() - T0:.0f}s total")
    (small / f"{EXITPB_NAME}_summary_{period}.txt").write_text("\n".join(log) + "\n")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# #705 (a): the registered-read registry. A read built after the four finished ones is a `rr.RegisteredRead` registered here by its
# stage name; `main()` dispatches it to the ONE driver (freeze map + --print-pins, option refusals with --out checked against the dir
# the period READS, --dry-run, once-only + .partial, the verdict files). The four finished stages above are NOT migrated: their freeze
# records pin the runner that ran them, and tests/test_cb_backtest_golden.py pins their every byte.
# ═════════════════════════════════════════════════════════════════════════════════════════════
REGISTERED_READS: dict = {}
BUILTIN_STAGES = ("daily", "minute", "step0-entries", "holdout", "report", "exits", "exits-report", "p5", "pre-read",
                  "h60-step0", "h60-read", "h60-hindsight", "exit-read",
                  "aplus-profile", "aplus-verdict")                                # a registered read may not wear one of these names
# #705 (b): the A+ rating (docs/analysis/cb_aplus_rating_prereg_2026-10-21.md) - `aplus-read` / `aplus-confirm` / `aplus-hindsight` are
# registered reads on the scaffold (their bodies live in aplus_read.py, the pinned `spec module`); `aplus-profile` (the pinned intraday
# volume profile, built BEFORE the pins) and `aplus-verdict` (the consequence cell) are plain stages dispatched below. The module reaches
# every helper here through the runtime namespace, so it imports no runner code at import time. BUILT ON SYNTHETIC DATA; no real outcome.
from scripts.probes._cb_backtest import aplus_read as _aplus  # noqa: E402
REGISTERED_READS.update(_aplus.REGISTERED)
# #705 (c): `rs-alone-read` (docs/analysis/cb_rs_alone_prereg_2026-10-22.md) - the parent's `alone_c3` row on the sealed 2025-26, once; a registered read
# on the same scaffold, its own artefact names (`rs_alone_*`, never `aplus_*holdout*`). BUILT ON SYNTHETIC DATA; no real outcome.
from scripts.probes._cb_backtest import rs_alone_read as _rs_alone  # noqa: E402
REGISTERED_READS.update(_rs_alone.REGISTERED)
# #705 v2 re-run (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md): `v2-h60-step0` (stage 0, before the freeze, doc=None), `v2-pre-read`,
# `v2-h60-read`, `v2-exit-read` - the 2017-21 chain on cb702_pre_v2 under a NEW lock (their bodies live in v2_rerun_read.py, the pinned `spec
# module`; every tag starts with `v2`). BUILT ON SYNTHETIC DATA + a parity run on a scratch copy of the old file; not run on v2.
from scripts.probes._cb_backtest import v2_rerun_read as _v2  # noqa: E402
REGISTERED_READS.update(_v2.REGISTERED)


def run_registered_read(spec: "rr.RegisteredRead", args) -> int:
    """Run a registered read with THIS module as the runtime (HERE / REPO / freeze_check / pin_lines / existing_outputs / minute_inputs ...)."""
    return rr.run_registered_read(spec, args, sys.modules[__name__])


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    clash = sorted(set(REGISTERED_READS) & set(BUILTIN_STAGES))
    if clash:                                   # a registered read named after a finished stage would replace its guards with the scaffold's
        ap.error(f"registered read(s) {clash} carry the name of a built-in stage - the finished stages are not replaced; rename the read")
    ap.add_argument("stage", choices=list(BUILTIN_STAGES) + sorted(REGISTERED_READS),
                    help="daily = P2a daily stage; minute = DISCOVERY entries/exits/controls; step0-entries = HOLDOUT "
                         "composition, no outcome; holdout = the minute engine AND the P5 stage on the HOLDOUT, behind "
                         "freeze_check (BUILT, NOT RUN); report = the DISCOVERY read; exits / exits-report = #702 his exit (the "
                         "+2R / day / combo partial x the trail switches x the stop variants) on the DISCOVERY first breaks, NEW "
                         "files only; p5 = #702 P5: his exit with the stalled breakouts cut (the holdout read's primary) and the "
                         "rows beside it, on the DISCOVERY first breaks of tl / com / comb, NEW files only; pre-read = #702 the "
                         "frozen primary read ONCE on the pre-2022 Alpaca era (candidates_tl_com.tsv, 2017-21; --data cb702_pre): "
                         "the minute engine and the P5 walk on its first breaks, the §5 verdict per cell for the whole era and "
                         "2020-21 alone; refuses while any minute pair is unfetched (BUILT, NOT RUN); h60-step0 / h60-read / h60-hindsight = "
                         "#702 the HOURLY-CLOSE entry read (docs/analysis/cb_hourly_entry_prereg_2026-10-19.md; --period required): the "
                         "entry-time table, the one-run read per period behind the freeze / STEP 0 / twin checks, the hindsight tables "
                         "after the verdict (BUILT ON SYNTHETIC DATA; NOT RUN); exit-read = #702 his partial and the stop after it "
                         "(docs/analysis/cb_exit_partial_prereg_2026-10-19.md; --period required): the six exit arms on the pinned P5 fills "
                         "and the pinned hourly-close fills, behind the freeze check and the parity of the runner-side walk copy with the "
                         "pinned rows; --parity-only = the control alone, match counts, nothing written (BUILT ON SYNTHETIC DATA; NOT RUN)")
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
    periods = list(H60_PERIODS) + [p for s in REGISTERED_READS.values() for p in s.periods if p not in H60_PERIODS]
    ap.add_argument("--period", choices=list(dict.fromkeys(periods)), help="h60-step0 / h60-read / h60-hindsight / exit-read: the period (discovery decides; pre = "
                                                                           "2017-21 and 2020-21 alone; holdout = 2025-26, descriptive)")
    ap.add_argument("--parity-only", action="store_true", help="exit-read: pass 1 alone - the control arm re-walked by the copy on every pinned fill "
                                                               "against the pinned rows and the module's own walk; prints the match / mismatch counts "
                                                               "and the reach line; computes no new-arm number and writes nothing")
    ap.add_argument("--data-pre", help="h60 stages: the Alpaca-era data dir (default: the sibling `cb702_pre` of --data); the freeze check pins both trees")
    ap.add_argument("--self-check", action="store_true", help="aplus-read / aplus-confirm / rs-alone-read, ONLY together with --dry-run: the STEP 0 rating counts "
                                                               "and every WOULD-FAIL-IF check on the inputs (features and the flag; no outcome column opened; "
                                                               "nothing written)")
    ap.add_argument("--levels", help="exits / exits-report: the levels of the run's candidates file to walk, comma-separated "
                                     "(default: every level of the run's keys). `--levels tl` reads the registered candidates.tsv and "
                                     "walks the trendline alone; `--keys com,comb` walks both. holdout REFUSES it")
    args = ap.parse_args(argv)
    era_opts = [o for o in ("watch_start", "watch_end", "raw_close", "breaks", "era_label") if getattr(args, o)]
    if era_opts and args.stage != "daily":
        ap.error(f"--{', --'.join(o.replace('_', '-') for o in era_opts)}: options of the `daily` stage only (the pre-2022 Alpaca-era run)")
    parse_keys(args.keys)                       # a bad --keys fails here, before any stage opens a file
    parse_levels(args.levels, parse_keys(args.keys))
    if getattr(args, "self_check", False) and not args.dry_run:
        ap.error("--self-check is honoured only together with --dry-run (the real run runs the same checks itself)")
    if args.stage in REGISTERED_READS:          # #705 (a): a read on the shared scaffold
        rc = run_registered_read(REGISTERED_READS[args.stage], args)
        if rc:
            sys.exit(rc)
        return
    if args.stage in ("aplus-profile", "aplus-verdict"):     # #705 (b): the profile build (before the pins) and the consequence cell
        rc = {"aplus-profile": _aplus.run_profile, "aplus-verdict": _aplus.run_verdict}[args.stage](args, sys.modules[__name__])
        if rc:
            sys.exit(rc)
        return
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
    if args.stage in ("h60-step0", "h60-read", "h60-hindsight", "exit-read"):
        rc = {"h60-step0": run_h60_step0, "h60-read": run_h60_read, "h60-hindsight": run_h60_hindsight, "exit-read": run_exit_read}[args.stage](args)
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
