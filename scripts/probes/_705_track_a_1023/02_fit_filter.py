#!/usr/bin/env python3
"""#705 Track A — 02: the FIT MODULE of the label filter (docs/analysis/cb_track_a_filter_prereg_2026-10-23.md §5). OUTCOME-FREE.

What it does: the 12 registered features (§5 table, directions FIXED) for every tl candidate row of both eras, read from bars <= D only;
the within-day AUC screen of each feature on the 2017-20 FIT set (170 positive events against 15,107 same-day negatives); the SUBSET
(<= 5 features with fit AUC >= 0.58, an against-direction feature (< 0.50) excluded and reported, an empty subset = FAIL); the
equal-weight trailing-pool score; the 6-a-week cap (TAKE / CAPPED / PASS / UNRATED); recall on the fit set, the 2021 hold-out (66)
and the 2022-23 check (9); the plateau; the bar verdict in events; the beside rows; the readiness contrast at s0. No outcome column,
no forward flag (R1, R2, fill, exit, return after D), no minute bar and no bar dated after D enters a feature; nothing dated after
2024-12-31 is kept from any era-B file (dropped AT READ, asserted).

THE MODULE'S OWN GUARDS (§5 "The fit module's own guards", round 3):
  1. WHITELIST — every file is opened through `wl_read_*`, which refuses a column outside `WHITELIST[name]` BEFORE opening the file and
     records the read in READ_LOG; the E-day / forward columns are banned by name at import time (`FORBIDDEN`).
  2. SHUFFLE BEFORE THE FIT — the positive flag permuted within each fit E date (among that date's positives and negatives), 200
     permutations, seed 702: the mean fit-set AUC of EVERY feature must lie in [0.48, 0.52], else stop (exit 3).
  3. SHUFFLE AFTER THE SUBSET, BEFORE THE HOLD-OUT IS READ — the registered subset's TAKE flags (label-free) counted on the 2021 positive
     flags permuted within each E date, 200 permutations: the mean count must be <= 1.5 (chance about 0.66), else stop (exit 3).
  4. LOOK-AHEAD — for a 500-row sample (seed 702) every feature is recomputed after every bar of the ticker dated > D is replaced with
     noise, every watch row of the ticker dated > D is replaced with noise and fake DISCONTINUOUS events dated > D are added; the
     features must be identical (NaN = NaN), else stop. The eight table features are read as the pinned watch row at D carries them
     (their own look-ahead guard is the module's explain_watch slice test); this test proves the module never reaches a later row.

READINGS OF THE REGISTRATION CHOSEN HERE (each a named constant or a commented line; reported in the build return):
  R-a POOL MEMBERS ARE ALL RATED. §5.4 "a missing feature counts 0.5, as the A+ read counts a missing scale": every chosen feature is
      treated like an A+ concept-1 SCALE (missing own value, or fewer than 30 non-missing in the pool / pool minus the member -> 0.5),
      never like an A+ required concept (missing -> unrated). So a fill's reference set is the whole pool and UNRATED = fewer than
      24 (4N) pool members. The strict reading (a member counts only with every chosen feature present) is printed beside as a count.
  R-b DISCONTINUOUS windows, by return straddle (an event dated d breaks a return from s to e iff s < d <= e, on the SPY calendar):
      rs_best (D-126, D]; grp_pct (D-63, D]; prior_move (pole_low_date, pole_date] (the watch row's pole_low_date — prior_move's own
      named input). Every row of klass `discontinuous_across_known_adjustment` counts (all, not liquid-only).
      "the group aggregate excludes DISCONTINUOUS tickers" CANNOT be applied: the pinned grp_pct is a cross-section over the whole
      universe of the night (runner pass 1 + the SIC file), neither of which is on the whitelist; the stored grp_pct is used and only
      the event's own ticker rule is applied. Said in the printout.
  R-c era-B flags: `apollo_data/audit_runs_2026-10-23/B_flags.tsv` (the repo's runs_2026-10-23/run_all_B holds the console only; its
      price/B_flags.tsv was written to a session scratchpad; both copies carry the same 67 DISCONTINUOUS (ticker, date) pairs).
      Era A: the doc-named v2 audit `cb702_pre_v2/audit_1023/price/A_flags.tsv` (93 pairs).
  R-d the readiness contrast at s0 treats s0 as the watch night D: features from the watch row at s0 and bars <= s0, the pool = every
      tl row with E' in [s0 - 19, s0] (= the pool of E = s0 + 1).
  R-e plateau neighbours: the subset rule RE-RUN at 0.56 and 0.60, and re-run at 0.58 with each chosen feature removed from the
      candidates in turn (so a 6th qualifying feature enters when more than five reach 0.58); an empty neighbour flags 0 events.
      One chosen feature: the two thresholds + the next-ranked feature (fit AUC >= 0.50) swapped in; none -> CAN'T TELL.
  R-f AUC ties between features in the subset order break by the §5 table order (#1..#12).
  R-g the own-line beside subset: a positive event whose ON-OR-BEFORE-E positive label (bought or best) has its own grade's phrase in
      the ticker's own caption line; keyed (vid, ts, screen_ticker) — caption_ticker = screen_ticker on all 854 attributed labels.
  R-h the base-level beside reading: every tl row of a GRADED base (sym, base_id) is positive; its negatives = the other rows on those
      dates minus rows whose base was labelled on or before their own E (the round-3 rule) minus the base-level positives.
  R-i the SPY calendar is derived from each export's SPY rows (the export is whitelisted; the calendar files are not read):
      1,635 / 821 sessions asserted.
  R-j the bar's "23,632 tl rows" = the rows with E in calendar 2021 (the no-information rate's denominator); the hold-out SET is
      E > 2020-12-31 as in the join, which also holds era A's last E 2022-01-03 (85 rows, 0 positives, 0 negatives — asserted).

Run:  python3 scripts/probes/_705_track_a_1023/02_fit_filter.py --dry-run    (writes 02_fit_filter_dryrun.txt; no AUC, no score
                                                                             against labels, no recall, no shuffle on real labels)
      python3 scripts/probes/_705_track_a_1023/02_fit_filter.py              (the REAL fit: refuses unless this module's sha256, every
                                                                             input pin AND the doc-body hash (sha256 of the doc's text
                                                                             above the FREEZE marker, taken at run time) appear under
                                                                             the marker, and refuses if any output exists; writes
                                                                             02_fit_filter.txt + apollo_data/.../fit_take.tsv)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from scripts.probes._cb_backtest import aplus_read as ap          # noqa: E402  (read-only: the A+ registration's own feature code)

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths
# ═════════════════════════════════════════════════════════════════════════════════════════════
DATA = "/Users/alvinfung/apollo_data"
A_DIR = f"{DATA}/cb702_pre_v2"
B_DIR = f"{DATA}/cb702"
OUT = f"{B_DIR}/qm_streams/track_a_1023"
DOC = os.path.join(REPO, "docs", "analysis", "cb_track_a_filter_prereg_2026-10-23.md")
JOIN_SCRIPT = os.path.join(HERE, "01_join_labels.py")
PRINTOUT = os.path.join(HERE, "02_fit_filter.txt")
DRY_PRINTOUT = os.path.join(HERE, "02_fit_filter_dryrun.txt")
STOPPED = os.path.join(HERE, "02_fit_filter.STOPPED.txt")
TAKE_TSV = f"{OUT}/fit_take.tsv"

FILES = {
    "labels_joined": f"{OUT}/labels_joined.tsv",
    "matched_events": f"{OUT}/matched_events.tsv",
    "moments": f"{B_DIR}/qm_streams/vision/graded_moments.tsv",
    "cand_A": f"{A_DIR}/out/candidates_tl_com.tsv",
    "cand_B": f"{B_DIR}/out/candidates.tsv",
    "cand_B_com": f"{B_DIR}/out/candidates_com.tsv",
    "watch_A": f"{A_DIR}/out/watch_tl_com.tsv.gz",
    "watch_B": f"{B_DIR}/out/watch.tsv.gz",
    "export_A": f"{A_DIR}/daily_closes_all.csv.gz",
    "export_B": f"{B_DIR}/daily_closes_all.csv.gz",
    "flags_A": f"{A_DIR}/audit_1023/price/A_flags.tsv",
    "flags_B": f"{DATA}/audit_runs_2026-10-23/B_flags.tsv",
}
# the pins the registration's freeze record already carries (the join's inputs / outputs); any drift refuses before a number is read
PINNED = {
    "labels_joined": "d0299beba6f2d0def7947bb6e77eac008ced4586450bb260ceed51f7b0fdca3b",
    "matched_events": "4d07d6e542bf5064cacf5e446a20566e9a1cb17fd126efee560634a2f6cd11fc",
    "moments": "f2c81633de6c6765477368876e300c4636d34222b43a5b13245cdf96b8d3add0",
    "cand_A": "3c5a66dc3052d0a284cbfee8202f74deb4e5bb75c74565dd8147df015e1baa5a",
    "cand_B": "b75c828671171530225198f97fc1191c9bced8f9448b9b05aa46099d617ce0c7",
    "cand_B_com": "07c24ccea7dae4488428cb2f8fb6302c49c1090106f8a3cb6f13a6413a4ac6b3",
    "watch_A": "976c19cd51a71637789817851e9b84d86504270b60f306e5a720b0915810cf43",
    "watch_B": "59e757cacb3250066393d0395e4abe89adff3787c34d1f2f7ad5fd5e2f2a5c0b",
    "export_A": "0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d",
    "join_script": "6889819c41342c60831b0d62b277d47b677e4deaeab3443cbdde7a05d56b112c",
}

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants (every number is the doc's §5)
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = "2024-12-31"                  # nothing dated after this is kept from any era-B file
ERA_A_LAST_DAY = "2022-06-30"         # era A's export / calendar end
FIT_LAST_E = "2020-12-31"             # the fit set's last E (era A); 2021 (E > this, era A) is the hold-out
SCREEN = 0.58                         # subset rule: fit-set AUC >= 0.58
AGAINST = 0.50                        # below = against the fixed direction: excluded, reported, never flipped
MAX_SUBSET = 5
PLATEAU_THRESHOLDS = (0.56, 0.60)
POOL_SESSIONS = 20                    # pool: every tl row with E' in [E - 20, E - 1] sessions
POOL_FLOOR = 30                       # |S| >= 30 non-missing per feature, else that feature is 0.5
MISSING_PCT = 0.5
N_DECIDES = 6
NS = (4, 6, 8)                        # N = 6 decides; 4 and 8 beside
def cutoff_rank(N: int) -> int:       # the cutoff = the (N x 4 weeks)-th highest reference score
    return 4 * N
PERMS = 200
SEED = 702
GUARD2_BAND = (0.48, 0.52)
GUARD3_MAX = 1.5
BAR_PASS = 5                          # PASS >= 5 of 66 (with the plateau and >= 1 of the 9 era-B events)
BAR_FAIL = 1                          # FAIL <= 1 of 66
HOLDOUT_N = 66
LOOKAHEAD_N = 500
RS_WINDOW, GRP_WINDOW = 126, 63       # the longest RS return (6 months) and the group's 63-session return
DISC_KLASS = "discontinuous_across_known_adjustment"
EXPECT = {                            # the populations the fit module ASSERTS (§4, §5, §2h)
    "stream_A": 81015, "first_A": 20650, "stream_B": 41200, "first_B": 12250,
    "cal_A": 1635, "cal_B": 821,
    "pos_A": 236, "pos_fit": 170, "pos_hold": 66, "pos_B": 9,
    "neg_A": 23188, "neg_fit": 15107, "neg_hold": 8081, "neg_B": 345,
    "excl_A": 410, "excl_fit": 270, "excl_hold": 140, "excl_B": 7,
    "post_A": 87, "post_fit": 58, "post_hold": 29, "post_B": 3,
    "strict_A": 127, "strict_fit": 90, "strict_hold": 37, "strict_B": 6,
    "at0_A": 119, "at0_B": 3,
    "posny_A": 15, "posny_bought_A": 12,
    "ready_ny_s0_all": 50, "ready_ny_s0": 43, "ready_b_s0": 176, "ready_b_s0_tl": 153,
    "ready_ny_ev_all": 32, "ready_ny_ev": 25, "ready_b_ev": 138,
    "own_bought": 350, "own_not_yet": 58, "own_best": 35,
    "graded_dates_A": 156, "graded_dates_B": 7,
    "watch_B_dropped": 109961, "cand_B_not_discovery": 174495, "cand_B_after_cut": 328,
    "rows_2021": 23632,                # tl rows with E in calendar 2021 (the no-information rate's denominator)
    # MEASURED by this module's dry run (2026-10-23), NOT registration numbers: the hold-out SET = E > 2020-12-31 = 2021 + era A's last E
    "rows_hold_A": 23717, "rows_hold_2022_01_03": 85,
    # reading R-j: era A's last E (2022-01-03, 85 rows) holds no labelled event - ASSERTED, not only printed
    "pos_hold_2022": 0, "neg_hold_2022": 0,
}

# the 12 features, in the §5 table order: key -> (direction: +1 higher is better / -1 lower is better, source tag)
FEATURES = {
    "tightening_ratio": (-1, "S"), "wk_ratio": (-1, "S"), "pb_ratio": (-1, "S"), "base_depth": (-1, "S"), "retrace": (-1, "R/B"),
    "prior_move": (+1, "S/B"), "pole_day_vol_ratio": (+1, "B"), "rs_best": (+1, "S"), "grp_pct": (+1, "S/B"), "vol_dry5": (-1, "S"),
    "dist_level_adr": (-1, "S/B"), "trigger_bar_range_adr": (-1, "B"),
}
FEATURE_KEYS = tuple(FEATURES)
FIDX = {k: j for j, k in enumerate(FEATURE_KEYS)}
DIRECTION = np.array([FEATURES[k][0] for k in FEATURE_KEYS], dtype=float)
DISC_FEATURES = ("rs_best", "grp_pct", "prior_move")

# ═════════════════════════════════════════════════════════════════════════════════════════════
# GUARD 1 — the whitelist (files and columns); a read outside it raises before the file is opened
# ═════════════════════════════════════════════════════════════════════════════════════════════
TABLE_FEATURE_COLS = ("tightening_ratio", "base_depth", "retrace", "prior_move", "pole_day_vol_ratio", "rs_best", "grp_pct",
                      "trigger_bar_range_adr")
CAND_KEY_COLS = ("ticker", "D", "E", "K", "base_id", "pole_date", "retrigger", "retrigger_chain", "pivot", "adr20", "C1", "base_len",
                 "phase_qqq_10_20", "phase_qqq_10_20_s5", "phase_spy_qqq_50", "apollo_regime", "split")
# the watch row: its date column is `watch_date` (= D); `close` + `pivot_tl` are dist_level_adr's named inputs, `pole_high` the
# base-start check of wk_ratio / pb_ratio (the A+ check 12), `pole_low_date` prior_move's pole low (its DISCONTINUOUS window)
WATCH_KEY_COLS = ("ticker", "watch_date", "split", "pole_date", "base_len", "adr20", "close", "pivot_tl", "pole_high", "pole_low_date")
WHITELIST = {
    "labels_joined": ("vid", "ts", "screen_ticker", "sym", "s0", "era", "coverage", "grade", "is_bought", "is_not_yet", "is_best",
                      "watch_at_s0", "c0_tl_at_s0", "delta_tl", "E_tl", "base_id_tl"),
    "matched_events": ("era", "sym", "E_tl", "bought", "not_yet", "best", "base_id"),
    "moments": ("video", "ts", "ticker", "quote"),
    "cand_A": CAND_KEY_COLS + TABLE_FEATURE_COLS,
    "cand_B": CAND_KEY_COLS + TABLE_FEATURE_COLS,
    "cand_B_com": CAND_KEY_COLS + TABLE_FEATURE_COLS,
    "watch_A": WATCH_KEY_COLS + TABLE_FEATURE_COLS,
    "watch_B": WATCH_KEY_COLS + TABLE_FEATURE_COLS,
    "export_A": ("ticker", "date", "h", "l", "c", "v"),
    "export_B": ("ticker", "date", "h", "l", "c", "v"),
    "flags_A": ("klass", "ticker", "date"),
    "flags_B": ("klass", "ticker", "date"),
}
FORBIDDEN = {"open_E", "high_E", "low_E", "close_E", "vol_E", "breakout_vol_x", "gap_open_pct", "gap_over_1adr", "overlap_open",
             "r1_status", "r2", "r1_off_from_E", "delta_r1", "entry_date", "fill", "fill_minute", "realized_r", "status", "pnl_adr",
             "o", "open", "prev_close", "rc", "go", "c1_over_pc", "c5_over_pc"}
for _n, _cols in WHITELIST.items():
    assert not (set(_cols) & FORBIDDEN), (_n, set(_cols) & FORBIDDEN)
    assert not any(c.startswith(("first_", "C2", "C3", "C4", "C5", "C6", "C7")) for c in _cols), _n

READ_LOG: list = []


class WhitelistError(AssertionError):
    pass


def wl_check(name: str, cols) -> None:
    """Refuse a file outside the whitelist or a column outside its entry (and any FORBIDDEN column) — before anything is opened."""
    if name not in WHITELIST:
        raise WhitelistError(f"file '{name}' is not on the fit module's whitelist")
    extra = [c for c in cols if c not in WHITELIST[name]]
    if extra:
        raise WhitelistError(f"{name}: columns outside the whitelist {extra}")
    bad = [c for c in cols if c in FORBIDDEN]
    if bad:
        raise WhitelistError(f"{name}: forbidden columns {bad}")


def assert_none_after(df: pd.DataFrame, col: str, cut: str, what: str) -> None:
    """The era-B belt-and-braces: after the per-chunk cut, no row of `col` may be dated after `cut` (an AssertionError if one slipped through)."""
    assert len(df) == 0 or df[col].max() <= cut, f"{what}: a row dated after the cut {cut} survived the read"


def wl_read_tsv(name: str, cols, str_cols, path: "str | None" = None, keep=None, chunksize: int = 200_000) -> tuple:
    """A whitelisted TSV read: `usecols` = exactly `cols`; `str_cols` as text, the rest parsed round-trip ('' = NaN). `keep(chunk)` ->
    (kept chunk, Counter of dropped rows) is applied PER CHUNK, before concatenation (the era-B cut)."""
    cols = list(cols)
    wl_check(name, cols)
    path = path or FILES[name]
    dtype = {c: str for c in cols if c in str_cols}
    parts, dropped = [], Counter()
    for ch in pd.read_csv(path, sep="\t", usecols=cols, dtype=dtype, keep_default_na=False, na_values={c: [""] for c in cols if c not in str_cols},
                          float_precision="round_trip", chunksize=chunksize, low_memory=False):
        assert set(ch.columns) == set(cols), (name, sorted(ch.columns))
        if keep is not None:
            ch, d = keep(ch)
            dropped.update(d)
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
    READ_LOG.append((name, path, tuple(cols), len(df), dict(dropped)))
    return df, dropped


def wl_read_export(name: str, keep_tickers: set, cut: "str | None", path: "str | None" = None) -> tuple:
    """The daily export (no header: ticker, date, o, h, l, c, v; `o` is never read). Rows dated after `cut` are DROPPED PER CHUNK before any
    other filter (no later row reaches any set), then only `keep_tickers` are kept; SORTED by (ticker, date) into the A+ `Export` shape
    (the cb702 export is not date-ordered). Returns (Export, rows dropped after the cut)."""
    cols = list(WHITELIST[name])
    wl_check(name, cols)
    path = path or FILES[name]
    parts, n_after = [], 0
    for ch in pd.read_csv(path, header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], usecols=cols, dtype={"ticker": str, "date": str},
                          keep_default_na=False, float_precision="round_trip", chunksize=2_000_000):
        if cut is not None:
            m = ch["date"] <= cut
            n_after += int((~m).sum())
            ch = ch[m]
        parts.append(ch[ch["ticker"].isin(keep_tickers)])
    df = pd.concat(parts, ignore_index=True)
    if cut is not None:
        assert_none_after(df, "date", cut, "an export row")
    READ_LOG.append((name, path, tuple(cols), len(df), {"dated_after_cut": n_after} if cut else {}))
    return export_from_frame(df), n_after


def export_from_frame(df: pd.DataFrame) -> "ap.Export":
    """(ticker, date, h, l, c, v) rows -> the A+ read's `Export` (sorted by (ticker, date); the SPY rows are the session calendar; every
    row's date must be on it) — the same construction as `aplus_read.load_export`, from an already-filtered frame."""
    codes, uniques = pd.factorize(df["ticker"], sort=True)
    days = pd.to_datetime(df["date"]).to_numpy().astype("datetime64[D]").astype(np.int64)
    order = np.lexsort((days, codes))
    codes, days = codes[order], days[order]
    cols = {k: df[k].to_numpy(dtype=float)[order] for k in "hlcv"}
    tickers = [str(t) for t in uniques]
    tid = {t: k for k, t in enumerate(tickers)}
    bounds = np.concatenate(([0], np.flatnonzero(np.diff(codes)) + 1, [len(codes)]))
    start, stop = bounds[:-1], bounds[1:]
    if "SPY" not in tid:
        raise ValueError("no SPY rows - no session calendar")
    spy = tid["SPY"]
    cal_days = days[start[spy]:stop[spy]]
    assert (np.diff(cal_days) > 0).all(), "SPY carries a duplicate date"
    ci = np.searchsorted(cal_days, days)
    on_cal = (ci < len(cal_days)) & (cal_days[np.minimum(ci, len(cal_days) - 1)] == days)
    if not on_cal.all():
        raise ValueError(f"{int((~on_cal).sum())} rows have a date off the SPY calendar")
    for t in range(len(tickers)):                      # one row per (ticker, date)
        a, b = int(start[t]), int(stop[t])
        if b - a > 1 and not (np.diff(days[a:b]) > 0).all():
            raise ValueError(f"{tickers[t]}: a duplicate (ticker, date) row")
    cal = [str(np.datetime64(int(d), "D")) for d in cal_days]
    return ap.Export(tickers, start, stop, ci.astype(np.int64), cols["h"], cols["l"], cols["c"], cols["v"], cal, {d: k for k, d in enumerate(cal)}, tid)


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the 12 features of one night (ticker, D) — every one from the watch row at D, the ticker's export rows <= D and its flags <= D
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _num(x) -> float:
    if x is None:
        return math.nan
    try:
        f = float(x)
    except (TypeError, ValueError):
        return math.nan
    return f


def _in_window(disc: "np.ndarray | None", lo: int, hi: int) -> bool:
    """A DISCONTINUOUS event at calendar index d breaks a return from lo to hi iff lo < d <= hi."""
    if disc is None or len(disc) == 0:
        return False
    return bool(((disc > lo) & (disc <= hi)).any())


class WatchTable:
    """The watch rows keyed (ticker, watch_date); `get` returns a dict of the whitelisted columns (floats; '' already NaN) or None."""

    def __init__(self, df: pd.DataFrame):
        self.cols = [c for c in df.columns]
        self.arr = {c: df[c].to_numpy() for c in self.cols}
        self.idx = {(t, d): i for i, (t, d) in enumerate(zip(df["ticker"].to_numpy(), df["watch_date"].to_numpy()))}
        assert len(self.idx) == len(df), "duplicate (ticker, watch_date) watch rows"

    def get(self, ticker: str, d: str):
        i = self.idx.get((ticker, d))
        if i is None:
            return None
        return {c: self.arr[c][i] for c in self.cols}


def features_for(ticker: str, D: str, wacc, ex: "ap.Export", disc_ci: "np.ndarray | None") -> tuple:
    """(12 raw feature values in FEATURE_KEYS order, NaN = missing; flags). The §5 definitions:
      1 tightening_ratio   the watch row's (mean (h-l)/c over D-4..D / over P+1..P+5)
      2 wk_ratio           A+ concept 1 weekly (aplus_read.wk_ratio_of over the export rows [pole_date, D]); missing k < 3
      3 pb_ratio           A+ concept 1 pullbacks (aplus_read.pb_ratio_of); missing with < 2 completed pullbacks
         (2 and 3 are missing, counted, when the base rows are not base_len + 1 or h at P != the watch row's pole_high — A+ check 12)
      4 base_depth         the watch row's 1 - base_low / pole_high
      5 retrace            the watch row's (pole_high - base_low) / (pole_high - pole_low)
      6 prior_move         the watch row's pole_high / pole_low - 1; MISSING with a DISCONTINUOUS event in (pole_low_date, pole_date]
      7 pole_day_vol_ratio the watch row's telemetry
      8 rs_best            the watch row's; MISSING with a DISCONTINUOUS event in (D-126, D]
      9 grp_pct            the watch row's; MISSING with a DISCONTINUOUS event in (D-63, D]
     10 vol_dry5           aplus_read.vol_dry5_of: mean volume D-4..D / D-9..D-5 of the ticker's rows ending at D
     11 dist_level_adr     (pivot_tl(D) - close(D)) / (close(D) x adr20(D)), the watch row; missing without a line
     12 trigger_bar_range_adr the watch row's D-bar range / ADR20"""
    w = wacc.get(ticker, D)
    if w is None:
        raise KeyError(f"no watch row for ({ticker}, {D})")
    iD = ex.cal_ci[D]
    v = dict.fromkeys(FEATURE_KEYS, math.nan)
    fl = {"base_mismatch": False, "disc_rs_best": False, "disc_grp_pct": False, "disc_prior_move": False}
    v["tightening_ratio"] = _num(w["tightening_ratio"])
    bl = int(w["base_len"])
    h, l, c = ap.base_rows(ex, ticker, w["pole_date"], D)
    if len(h) == bl + 1 and len(h) > 0 and float(h[0]) == _num(w["pole_high"]):
        v["wk_ratio"] = _num(ap.wk_ratio_of(h, l, c, bl))
        v["pb_ratio"] = _num(ap.pb_ratio_of(h, l))
    else:
        fl["base_mismatch"] = True
    v["base_depth"] = _num(w["base_depth"])
    v["retrace"] = _num(w["retrace"])
    pm = _num(w["prior_move"])
    if _in_window(disc_ci, ex.cal_ci[w["pole_low_date"]], ex.cal_ci[w["pole_date"]]):
        fl["disc_prior_move"] = not math.isnan(pm)
        pm = math.nan
    v["prior_move"] = pm
    v["pole_day_vol_ratio"] = _num(w["pole_day_vol_ratio"])
    rs = _num(w["rs_best"])
    if _in_window(disc_ci, iD - RS_WINDOW, iD):
        fl["disc_rs_best"] = not math.isnan(rs)
        rs = math.nan
    v["rs_best"] = rs
    gp = _num(w["grp_pct"])
    if _in_window(disc_ci, iD - GRP_WINDOW, iD):
        fl["disc_grp_pct"] = not math.isnan(gp)
        gp = math.nan
    v["grp_pct"] = gp
    v["vol_dry5"] = _num(ap.vol_dry5_of(ex, ticker, D))
    p, cl, a = _num(w["pivot_tl"]), _num(w["close"]), _num(w["adr20"])
    if not math.isnan(p) and cl > 0 and a > 0:
        v["dist_level_adr"] = (p - cl) / (cl * a)
    v["trigger_bar_range_adr"] = _num(w["trigger_bar_range_adr"])
    return np.array([v[k] for k in FEATURE_KEYS], dtype=float), fl


# ═════════════════════════════════════════════════════════════════════════════════════════════
# GUARD 4 — the look-ahead test
# ═════════════════════════════════════════════════════════════════════════════════════════════
def one_ticker_export(ex: "ap.Export", ticker: str, after_ci: "int | None" = None, rng=None) -> "ap.Export":
    """The ticker's rows as a one-ticker Export (same calendar); with `rng`, every bar dated after calendar index `after_ci` is NOISE."""
    ci, h, l, c, v = (np.array(x, copy=True) for x in ex.rows(ticker))
    if rng is not None:
        m = ci > after_ci
        k = int(m.sum())
        if k:
            hh = rng.uniform(1.0, 1000.0, k)
            h[m], l[m], c[m], v[m] = hh, hh * rng.uniform(0.3, 0.99, k), hh * rng.uniform(0.3, 1.0, k), rng.uniform(1e3, 1e9, k)
    return ap.Export([ticker], np.array([0]), np.array([len(ci)]), ci.astype(np.int64), h, l, c, v, ex.cal, ex.cal_ci, {ticker: 0})


class NoisyAfter:
    """A watch accessor that returns NOISE for every row of `ticker` dated after D (a feature reaching a later watch row would change)."""

    def __init__(self, base, ticker: str, D: str, rng):
        self.base, self.ticker, self.D, self.rng = base, ticker, D, rng

    def get(self, t: str, d: str):
        r = self.base.get(t, d)
        if r is None or t != self.ticker or d <= self.D:
            return r
        out = dict(r)
        for k, x in r.items():
            if isinstance(x, (float, np.floating)) and k not in ("base_len",):
                out[k] = float(self.rng.uniform(-10, 10))
        return out


def same_features(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.array_equal(a, b, equal_nan=True))


def lookahead_test(rows: list, wacc, ex: "ap.Export", disc_of: dict, feat_fn=features_for, seed: int = SEED, reference: "dict | None" = None) -> tuple:
    """rows = [(ticker, D)]. Each row's features are recomputed with every later bar, later watch row and later flag date replaced by noise;
    (n checked, list of differing rows). `reference[(ticker, D)]` = the values computed on the FULL export (the stream's), compared too."""
    rng = np.random.default_rng(seed)
    diffs = []
    for t, D in rows:
        iD = ex.cal_ci[D]
        disc = disc_of.get(t)
        base, _ = feat_fn(t, D, wacc, one_ticker_export(ex, t), disc)
        ex2 = one_ticker_export(ex, t, iD, rng)
        fake = iD + 1 + rng.integers(0, 60, 3)
        disc2 = np.sort(np.concatenate([disc if disc is not None else np.zeros(0, dtype=np.int64), fake])).astype(np.int64)
        pert, _ = feat_fn(t, D, NoisyAfter(wacc, t, D, rng), ex2, disc2)
        ok = same_features(base, pert)
        if reference is not None:
            ok = ok and same_features(base, reference[(t, D)])
        if not ok:
            diffs.append((t, D, [FEATURE_KEYS[j] for j in range(len(base)) if not same_features(base[j:j + 1], pert[j:j + 1])]))
    return len(rows), diffs


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the within-day AUC screen
# ═════════════════════════════════════════════════════════════════════════════════════════════
def day_groups(day: np.ndarray) -> dict:
    """{day code: row indices}."""
    order = np.argsort(day, kind="stable")
    d = day[order]
    cut = np.flatnonzero(np.concatenate(([True], d[1:] != d[:-1], [True])))
    return {d[cut[k]]: order[cut[k]:cut[k + 1]] for k in range(len(cut) - 1)}


def within_day_auc(Xo: np.ndarray, day: np.ndarray, pos: np.ndarray, neg: np.ndarray, groups: "dict | None" = None) -> list:
    """Per column of `Xo` (oriented: higher = better, NaN missing): the mean over positive events of the event's percentile among THAT day's
    negative rows with a value, (worse + 0.5 equal) / n — the event itself, every other positive and every excluded row are out of the
    denominator (they are not in `neg`). A positive with a missing value is skipped; a positive whose day has no negative with a value is
    skipped. Returns [dict(auc, n_pos, skip_missing, skip_no_neg, n_neg)] per column."""
    Xo = np.asarray(Xo, dtype=float)
    if Xo.ndim == 1:
        Xo = Xo[:, None]
    F = Xo.shape[1]
    groups = groups if groups is not None else day_groups(day)
    tot, npos, smiss, snoneg, nneg = np.zeros(F), np.zeros(F, dtype=int), np.zeros(F, dtype=int), np.zeros(F, dtype=int), np.zeros(F, dtype=int)
    pdays = np.unique(day[pos])
    for d in pdays:
        rows = groups[d]
        pr, nr = rows[pos[rows]], rows[neg[rows]]
        for f in range(F):
            nv = Xo[nr, f]
            nv = np.sort(nv[~np.isnan(nv)])
            pv = Xo[pr, f]
            ok = ~np.isnan(pv)
            smiss[f] += int((~ok).sum())
            if len(nv) == 0:
                snoneg[f] += int(ok.sum())
                continue
            nneg[f] += len(nv)
            x = pv[ok]
            lo, hi = np.searchsorted(nv, x, "left"), np.searchsorted(nv, x, "right")
            tot[f] += float(((lo + 0.5 * (hi - lo)) / len(nv)).sum())
            npos[f] += int(ok.sum())
    return [dict(auc=(tot[f] / npos[f]) if npos[f] else math.nan, n_pos=int(npos[f]), skip_missing=int(smiss[f]), skip_no_neg=int(snoneg[f]),
                 n_neg=int(nneg[f])) for f in range(F)]


def permute_within_day(pos: np.ndarray, neg: np.ndarray, groups: dict, rng) -> np.ndarray:
    """A permuted positive flag: on each day that holds a positive, the same NUMBER of positives drawn at random among that day's positives
    and negatives (excluded rows stay out)."""
    out = np.zeros(len(pos), dtype=bool)
    for d, rows in groups.items():
        k = int(pos[rows].sum())
        if k == 0:
            continue
        cand = rows[pos[rows] | neg[rows]]
        out[rng.choice(cand, size=k, replace=False)] = True
    return out


def guard2_shuffle(Xo: np.ndarray, day: np.ndarray, pos: np.ndarray, neg: np.ndarray, perms: int = PERMS, seed: int = SEED,
                   band: tuple = GUARD2_BAND, auc_fn=within_day_auc) -> tuple:
    """GUARD 2: (ok, mean shuffled AUC per column). The positive flag permuted within each E date, `perms` times; every column's mean AUC must
    lie in `band`."""
    rng = np.random.default_rng(seed)
    groups = day_groups(day)
    pgroups = {d: r for d, r in groups.items() if pos[r].any()}
    acc = np.zeros(Xo.shape[1] if Xo.ndim > 1 else 1)
    for _ in range(perms):
        p = permute_within_day(pos, neg, pgroups, rng)
        n = (pos | neg) & ~p
        res = auc_fn(Xo, day, p, n, groups)
        acc += np.array([r["auc"] for r in res])
    means = acc / perms
    ok = bool(np.all((means >= band[0]) & (means <= band[1])))
    return ok, means


def guard3_shuffle(take: np.ndarray, day: np.ndarray, pos: np.ndarray, neg: np.ndarray, perms: int = PERMS, seed: int = SEED,
                   limit: float = GUARD3_MAX) -> tuple:
    """GUARD 3: (ok, mean count). The hold-out positive flags permuted within each E date; the count of permuted positives flagged TAKE,
    averaged over `perms`, must be <= `limit` (a cap or cutoff that flags too much shows here as a high chance count)."""
    rng = np.random.default_rng(seed)
    groups = {d: r for d, r in day_groups(day).items() if pos[r].any()}
    tot = 0
    for _ in range(perms):
        p = permute_within_day(pos, neg, groups, rng)
        tot += int((p & take).sum())
    mean = tot / perms
    return mean <= limit, mean


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the subset rule, the plateau, the bar
# ═════════════════════════════════════════════════════════════════════════════════════════════
def subset_rule(aucs: dict, threshold: float = SCREEN, max_k: int = MAX_SUBSET, exclude=()) -> tuple:
    """(subset in descending fit AUC (ties by the §5 table order), against-direction features (AUC < 0.50) — excluded, never flipped)."""
    order = {k: j for j, k in enumerate(FEATURE_KEYS)}
    against = [k for k, a in aucs.items() if a == a and a < AGAINST]
    elig = [(k, a) for k, a in aucs.items() if k not in exclude and a == a and a >= threshold and a >= AGAINST]
    elig.sort(key=lambda x: (-x[1], order.get(x[0], 99)))
    return [k for k, _ in elig[:max_k]], against


def plateau(aucs: dict, subset: list, count_fn, c: int) -> dict:
    """§5.6. Neighbours: the subset rule re-run at 0.56 and 0.60, and with each chosen feature left out in turn (re-run at 0.58 without it);
    ONE chosen feature: the two thresholds + the next-ranked feature (fit AUC >= 0.50) swapped in (none -> CAN'T TELL). The plateau HOLDS iff
    every neighbour flags at least max(4, ceil(0.75 c)) hold-out events (one-sided). `count_fn(subset)` -> hold-out count (empty -> 0)."""
    need = max(4, math.ceil(0.75 * c))
    nb = []
    for t in PLATEAU_THRESHOLDS:
        nb.append((f"screen {t:.2f}", subset_rule(aucs, t)[0]))
    verdict_extra = None
    if len(subset) >= 2:
        for k in subset:
            nb.append((f"without {k}", subset_rule(aucs, SCREEN, exclude=(k,))[0]))
    elif len(subset) == 1:
        order = {k: j for j, k in enumerate(FEATURE_KEYS)}
        rest = sorted([(k, a) for k, a in aucs.items() if k != subset[0] and a == a and a >= AGAINST], key=lambda x: (-x[1], order.get(x[0], 99)))
        if rest:
            nb.append((f"{rest[0][0]} swapped in for {subset[0]}", [rest[0][0]]))
        else:
            verdict_extra = "CAN'T TELL (one chosen feature and no next-ranked feature with fit AUC >= 0.50)"
    rows = []
    for name, sub in nb:
        n = count_fn(sub) if sub else 0
        rows.append(dict(name=name, subset=sub, count=n, ok=n >= need))
    if not subset:
        v = "n/a (empty subset)"
    elif verdict_extra:
        v = "CAN'T TELL"
    else:
        v = "HOLDS" if all(r["ok"] for r in rows) else "FAILS"
    return dict(need=need, c=c, neighbours=rows, verdict=v, note=verdict_extra)


def bar_verdict(subset_empty: bool, c: int, plateau_verdict: str, era_b: int) -> tuple:
    """§5 the fit's own bar, in events: FAIL = an empty subset or <= 1 of 66; PASS = >= 5 of 66 AND the plateau holds AND >= 1 of the 9 era-B
    events; CAN'T TELL otherwise (2-4, or >= 5 with no era-B event, or >= 5 with the plateau failing / undecidable — a spike)."""
    if subset_empty:
        return "FAIL", "empty subset (no feature reached 0.58)"
    if c <= BAR_FAIL:
        return "FAIL", f"{c} of {HOLDOUT_N} hold-out events flagged (<= {BAR_FAIL})"
    if c >= BAR_PASS:
        if plateau_verdict != "HOLDS":
            return "CAN'T TELL", f"{c} of {HOLDOUT_N} flagged but the plateau {plateau_verdict.lower()} (a spike)"
        if era_b < 1:
            return "CAN'T TELL", f"{c} of {HOLDOUT_N} flagged but none of the era-B check events"
        return "PASS", f"{c} of {HOLDOUT_N} flagged, the plateau holds, {era_b} of the era-B check events flagged"
    return "CAN'T TELL", f"{c} of {HOLDOUT_N} flagged (2-4)"


def poisson_tail(k: int, mu: float) -> float:
    """P(X >= k), X ~ Poisson(mu)."""
    return 1.0 - sum(math.exp(-mu) * mu ** j / math.factorial(j) for j in range(k))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the score, the pool, the cap
# ═════════════════════════════════════════════════════════════════════════════════════════════
FLAG_TAKE, FLAG_CAPPED, FLAG_PASS, FLAG_UNRATED = "TAKE", "CAPPED", "PASS", "UNRATED"


def subset_score(P: np.ndarray, subset_idx: list) -> np.ndarray:
    """The equal-weight score: the mean of the chosen features' pool percentiles, a missing one (own value or pool floor) counted 0.5."""
    if len(P) == 0:
        return np.zeros(0)
    Q = P[:, subset_idx]
    return np.where(np.isnan(Q), MISSING_PCT, Q).mean(axis=1)


def apply_cap(score: np.ndarray, cutoff: np.ndarray, week: np.ndarray, N: int) -> np.ndarray:
    """Rows in (E, ticker) order: TAKE = score >= cutoff and fewer than N TAKE already in the ISO week; CAPPED = at or above after the week's
    N; PASS = below; UNRATED = no cutoff (fewer than 4N rated pool members)."""
    flags = np.empty(len(score), dtype=object)
    cnt = Counter()
    for i in range(len(score)):
        cut = cutoff[i]
        if cut != cut:
            flags[i] = FLAG_UNRATED
        elif score[i] >= cut:
            if cnt[week[i]] < N:
                cnt[week[i]] += 1
                flags[i] = FLAG_TAKE
            else:
                flags[i] = FLAG_CAPPED
        else:
            flags[i] = FLAG_PASS
    return flags


class PoolEngine:
    """One era's stream in (E, ticker) order; per E date the day's own percentiles against the trailing pool and every pool member's
    reference percentiles against the pool minus itself (`aplus_read.pool_percentiles`: mid-rank, ties half, floor 30). Label-free."""

    def __init__(self, Xo: np.ndarray, E_ci: np.ndarray, ticker: np.ndarray, week: np.ndarray, pool_sessions: int = POOL_SESSIONS, floor: int = POOL_FLOOR):
        E_ci = np.asarray(E_ci, dtype=np.int64)
        n = len(E_ci)
        order = np.lexsort((np.asarray(ticker).astype(str), E_ci))
        assert (order == np.arange(n)).all(), "the stream must be in (E, ticker) order"
        self.n, self.week = n, np.asarray(week)
        self.own = np.full(Xo.shape, np.nan)
        self.pool_n = np.zeros(n, dtype=np.int64)
        self.days = []
        starts = np.flatnonzero(np.concatenate(([True], E_ci[1:] != E_ci[:-1]))) if n else np.zeros(0, dtype=int)
        ends = np.concatenate((starts[1:], [n])) if n else np.zeros(0, dtype=int)
        for a, b in zip(starts, ends):
            e = int(E_ci[a])
            p0, p1 = int(np.searchsorted(E_ci, e - pool_sessions, "left")), int(np.searchsorted(E_ci, e - 1, "right"))
            own, ref = ap.pool_percentiles(Xo, np.arange(p0, p1), np.arange(a, b), floor)
            self.own[a:b] = own
            self.pool_n[a:b] = p1 - p0
            self.days.append((int(a), int(b), ref))

    def rate(self, subset_idx: list, N: int) -> dict:
        score = subset_score(self.own, subset_idx)
        cutoff = np.full(self.n, np.nan)
        strict_short = np.zeros(self.n, dtype=bool)
        for a, b, ref in self.days:
            rs = subset_score(ref, subset_idx)
            cutoff[a:b] = ap.cutoff_of(rs, cutoff_rank(N)) if len(rs) else np.nan
            strict = int((~np.isnan(ref[:, subset_idx])).all(axis=1).sum()) if len(ref) else 0
            strict_short[a:b] = strict < cutoff_rank(N)
        flags = apply_cap(score, cutoff, self.week, N)
        return dict(score=score, cutoff=cutoff, flag=flags, strict_unrated=strict_short)


def score_at_nights(Xo_stream: np.ndarray, E_ci_stream: np.ndarray, Xo_nights: np.ndarray, d_ci: np.ndarray, subset_idx: list,
                    floor: int = POOL_FLOOR) -> tuple:
    """The readiness contrast's score of a watch night d (no event): the pool = every stream row with E' in [d - 19, d] (= the pool of
    E = d + 1, reading R-d); (score, pool size) per night."""
    E_ci_stream = np.asarray(E_ci_stream, dtype=np.int64)
    out, pn = np.full(len(d_ci), np.nan), np.zeros(len(d_ci), dtype=np.int64)
    for k, d in enumerate(np.asarray(d_ci, dtype=np.int64)):
        p0, p1 = int(np.searchsorted(E_ci_stream, d - (POOL_SESSIONS - 1), "left")), int(np.searchsorted(E_ci_stream, d, "right"))
        M = np.vstack([Xo_stream[p0:p1], Xo_nights[k:k + 1]])
        own, _ = ap.pool_percentiles(M, np.arange(p1 - p0), np.array([p1 - p0]), floor)
        out[k] = subset_score(own, subset_idx)[0]
        pn[k] = p1 - p0
    return out, pn


def pair_auc(a: np.ndarray, b: np.ndarray) -> float:
    """P(a random member of a scores above a random member of b), ties half."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if not len(a) or not len(b):
        return math.nan
    bs = np.sort(b)
    lo, hi = np.searchsorted(bs, a, "left"), np.searchsorted(bs, a, "right")
    return float(((lo + 0.5 * (hi - lo)) / len(bs)).mean())


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the labels -> the populations (exactly 01_join_labels.py §11-§13, outcome-free)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_grade_rx() -> dict:
    spec = importlib.util.spec_from_file_location("_join01", JOIN_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.GRADE_RX)


def label_sets(J: pd.DataFrame, ME: pd.DataFrame, MO: pd.DataFrame, grade_rx: dict) -> dict:
    """Event keys (era, sym, E) and label rows the fit needs, from labels_joined / matched_events / graded_moments."""
    Jc = J[J["coverage"] != "none"]
    M = Jc[Jc["E_tl"] != ""].copy()
    M["d"] = M["delta_tl"].astype(int)
    isb, isbest, isny = M["is_bought"] == "1", M["is_best"] == "1", M["is_not_yet"] == "1"
    # the per-label own-line flag (§2h): the grade's phrase in the ticker's own caption line (graded_moments `quote`)
    assert not MO.duplicated(["video", "ts", "ticker"]).any()
    qmap = {(v, t, c): q for v, t, c, q in zip(MO["video"], MO["ts"], MO["ticker"], MO["quote"])}
    own_counts = Counter()

    def own_of(vid, ts, tk, grade) -> dict:
        q = qmap.get((vid, ts, tk))
        return {g: (q is not None and re.search(grade_rx[g], q.lower()) is not None) for g in grade.split(",")}
    for vid, ts, tk, grade in zip(J["vid"], J["ts"], J["screen_ticker"], J["grade"]):
        for g, ok in own_of(vid, ts, tk, grade).items():
            own_counts[g] += int(ok)
    pos_lab = M[isb | isbest]
    tim = defaultdict(lambda: [-10 ** 9, False, False])     # (era, sym, E) -> [dmax, at0, own-line on an on-or-before label]
    for r in pos_lab.itertuples(index=False):
        k = (r.era, r.sym, r.E_tl)
        t = tim[k]
        t[0] = max(t[0], r.d)
        t[1] = t[1] or r.d == 0
        if r.d >= 0:
            o = own_of(r.vid, r.ts, r.screen_ticker, r.grade)
            t[2] = t[2] or (r.is_bought == "1" and o.get("bought", False)) or (r.is_best == "1" and o.get("best", False))
    keys = {e: dict(pos=set(), post=set(), strict=set(), at0=set(), own=set()) for e in ("A", "B")}
    for (e, s, E), (dmax, at0, own) in tim.items():
        k = (s, E)
        if dmax >= 0:
            keys[e]["pos"].add(k)
            if at0:
                keys[e]["at0"].add(k)
            if own:
                keys[e]["own"].add(k)
            if dmax >= 1:
                keys[e]["strict"].add(k)
        else:
            keys[e]["post"].add(k)
    lab_first = {}                                          # (era, sym, base_id) -> earliest s0 of a matched label, any grade
    for e, s, b, s0 in zip(M["era"], M["sym"], M["base_id_tl"], M["s0"]):
        k = (e, s, b)
        lab_first[k] = min(lab_first.get(k, s0), s0)
    # events carrying a not-yet label; those that also carry a positive (bought or best) label (§3: 15 in era A)
    me = ME.copy()
    for c in ("bought", "not_yet", "best"):
        me[c] = me[c].astype(int)
    ny_ev = {e: set(zip(me.loc[(me.era == e) & (me.not_yet > 0), "sym"], me.loc[(me.era == e) & (me.not_yet > 0), "E_tl"])) for e in ("A", "B")}
    posny = me[(me.not_yet > 0) & ((me.bought > 0) | (me.best > 0))]
    posny_ev = {e: set(zip(posny.loc[posny.era == e, "sym"], posny.loc[posny.era == e, "E_tl"])) for e in ("A", "B")}
    # the readiness contrast's label rows (era A)
    JA = Jc[Jc["era"] == "A"]
    ev_key = list(zip(JA["sym"], JA["E_tl"]))
    in15 = np.array([k in posny_ev["A"] for k in ev_key])
    nyA, bA, s0w = (JA["is_not_yet"] == "1").to_numpy(), (JA["is_bought"] == "1").to_numpy(), (JA["watch_at_s0"] == "1").to_numpy()
    matched = (JA["E_tl"] != "").to_numpy()
    d01 = np.array([x != "" and int(x) in (0, 1) for x in JA["delta_tl"]])
    tl0 = (JA["c0_tl_at_s0"] == "1").to_numpy()
    ready = dict(
        ny_s0_all=JA[nyA & s0w], ny_s0=JA[nyA & s0w & ~in15], b_s0=JA[bA & s0w], b_s0_tl=JA[bA & s0w & tl0],
        ny_ev_all=JA[nyA & matched & d01], ny_ev=JA[nyA & matched & d01 & ~in15], b_ev=JA[bA & matched & d01])
    return dict(keys=keys, lab_first=lab_first, ny_ev=ny_ev, posny_ev=posny_ev, posny_bought=int(((posny.era == "A") & (posny.bought > 0)).sum()),
                own_counts=own_counts, ready=ready)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# one era's stream + classes
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Era:
    name: str
    cal: list
    ticker: np.ndarray
    D: np.ndarray
    E: np.ndarray
    E_ci: np.ndarray
    week: np.ndarray
    year: np.ndarray
    retrigger: np.ndarray
    C1: np.ndarray
    base_id: np.ndarray
    phase: dict
    X: np.ndarray                                # raw features, NaN = missing
    cls: dict = field(default_factory=dict)       # boolean arrays over the stream
    flags: dict = field(default_factory=dict)     # per-row feature flags (DISCONTINUOUS / base mismatch)
    ready: dict = field(default_factory=dict)     # the readiness contrast's label rows (era A)

    @property
    def Xo(self) -> np.ndarray:
        return self.X * DIRECTION


def assign_classes(era: Era, ls: dict) -> None:
    """The stream's classes: pos (GRADED), neg (the same-day negatives, round-3 rule), excl, post, strict, at0, own, the base-level reading,
    not-yet events, fit / hold-out."""
    e = era.name
    K = ls["keys"][e]
    key = list(zip(era.ticker, era.E))
    ki = {k: i for i, k in enumerate(key)}
    assert len(ki) == len(key), "duplicate (ticker, E) in the tl stream"
    n = len(key)

    def mask(keys: set) -> np.ndarray:
        m = np.zeros(n, dtype=bool)
        miss = [k for k in keys if k not in ki]
        assert not miss, f"era {e}: {len(miss)} labelled events not in the tl stream, e.g. {miss[:3]}"
        for k in keys:
            m[ki[k]] = True
        return m
    pos = mask(K["pos"])
    lab_by_E = np.array([ls["lab_first"].get((e, t, b), "9999") <= E for t, b, E in zip(era.ticker, era.base_id, era.E)])
    gdates = set(era.E[pos])
    on_g = np.array([x in gdates for x in era.E])
    neg = on_g & ~pos & ~lab_by_E
    excl = on_g & ~pos & lab_by_E
    gbases = set(zip(era.ticker[pos], era.base_id[pos]))
    bpos = np.array([(t, b) in gbases for t, b in zip(era.ticker, era.base_id)])
    bdates = set(era.E[bpos])
    bneg = np.array([x in bdates for x in era.E]) & ~bpos & ~lab_by_E
    fit = (era.E <= FIT_LAST_E) if e == "A" else np.zeros(n, dtype=bool)
    era.cls = dict(pos=pos, neg=neg, excl=excl, post=mask(K["post"]), strict=mask(K["strict"]), at0=mask(K["at0"]), own=mask(K["own"]),
                   bpos=bpos, bneg=bneg, ny=mask(ls["ny_ev"][e]), ny_only=mask(ls["ny_ev"][e] - ls["posny_ev"][e]), fit=fit,
                   hold=(~fit) if e == "A" else np.zeros(n, dtype=bool), lab_by_E=lab_by_E, n_gdates=np.array([len(gdates)]))


def population_counts(eras: dict) -> dict:
    A, B = eras["A"].cls, eras["B"].cls
    c = {}
    for nm in ("pos", "neg", "excl", "post", "strict"):
        c[f"{nm}_A"] = int(A[nm].sum())
        c[f"{nm}_fit"] = int((A[nm] & A["fit"]).sum())
        c[f"{nm}_hold"] = int((A[nm] & A["hold"]).sum())
        c[f"{nm}_B"] = int(B[nm].sum())
    c["at0_A"], c["at0_B"] = int(A["at0"].sum()), int(B["at0"].sum())
    c["graded_dates_A"], c["graded_dates_B"] = int(A["n_gdates"][0]), int(B["n_gdates"][0])
    return c


def check_expect(got: dict, expect: dict, say) -> list:
    """Every EXPECT key must be MEASURED and equal: a key missing from `got` (a renamed / dropped measurement) is a failure, never a silent skip."""
    bad = []
    for k, want in expect.items():
        if k not in got:
            bad.append(f"{k}: NOT MEASURED (registered {want})")
        elif got[k] != want:
            bad.append(f"{k}: {got[k]} (registered {want})")
    if bad:
        say("POPULATION ASSERT FAILED: " + "; ".join(bad))
    return bad


# ═════════════════════════════════════════════════════════════════════════════════════════════
# loading (real files; every read through the whitelist)
# ═════════════════════════════════════════════════════════════════════════════════════════════
CAND_STR = ("ticker", "D", "E", "K", "base_id", "pole_date", "retrigger", "retrigger_chain", "C1", "phase_qqq_10_20", "phase_qqq_10_20_s5",
            "phase_spy_qqq_50", "apollo_regime", "split")
WATCH_STR = ("ticker", "watch_date", "split", "pole_date", "pole_low_date")


def era_b_cand_keep(ch: pd.DataFrame) -> tuple:
    """Era-B candidate chunk: discovery split only, then E and D <= CUT_B (counted), then the tl rows. Applied PER CHUNK at read."""
    d = Counter()
    n0 = len(ch)
    ch = ch[ch["split"] == "discovery"]
    d["not_discovery"] += n0 - len(ch)
    n1 = len(ch)
    ch = ch[(ch["E"] <= CUT_B) & (ch["D"] <= CUT_B)]
    d["dated_after_cut"] += n1 - len(ch)
    return ch[ch["K"] == "tl"], d


def era_b_watch_keep(ch: pd.DataFrame) -> tuple:
    """Era-B watch chunk: discovery split only and watch_date <= CUT_B. Applied PER CHUNK at read."""
    n0 = len(ch)
    ch = ch[(ch["split"] == "discovery") & (ch["watch_date"] <= CUT_B)]
    return ch, Counter({"dropped_after_cut_or_holdout": n0 - len(ch)})


def read_flags(name: str, cut: "str | None", path: "str | None" = None) -> tuple:
    def keep(ch):
        d = Counter()
        ch = ch[ch["klass"] == DISC_KLASS]
        if cut is not None:
            m = ch["date"] <= cut
            d["dated_after_cut"] += int((~m).sum())
            ch = ch[m]
        return ch, d
    df, dropped = wl_read_tsv(name, ["klass", "ticker", "date"], ("klass", "ticker", "date"), path=path, keep=keep)
    return df, dropped


def disc_index(flags: pd.DataFrame, ex: "ap.Export") -> dict:
    """{ticker: sorted calendar indices of its DISCONTINUOUS events} (a date off the calendar maps to the next session)."""
    cal = np.array(ex.cal)
    out = defaultdict(list)
    for t, d in zip(flags["ticker"], flags["date"]):
        out[t].append(int(np.searchsorted(cal, d, "left")))
    return {t: np.array(sorted(v), dtype=np.int64) for t, v in out.items()}


def load_era(e: str, ls: dict, say, lookahead_rows: int = LOOKAHEAD_N) -> tuple:
    """Read one era through the whitelist, compute the 12 features of every tl row (and of the readiness label nights in era A), run the
    look-ahead test on a seeded sample; returns (Era, info dict). The export is freed before returning."""
    t0 = time.time()
    info = {}
    num_c = [c for c in WHITELIST[f"cand_{e}"] if c not in CAND_STR]
    if e == "A":
        cand, _ = wl_read_tsv("cand_A", WHITELIST["cand_A"], CAND_STR, keep=lambda ch: (ch[ch["K"] == "tl"], Counter()))
        assert (cand["split"] == "pre").all()
    else:
        drop = Counter()
        c1, d1 = wl_read_tsv("cand_B", WHITELIST["cand_B"], CAND_STR, keep=era_b_cand_keep)
        c2, d2 = wl_read_tsv("cand_B_com", WHITELIST["cand_B_com"], CAND_STR, keep=era_b_cand_keep)
        drop.update(d1)
        drop.update(d2)
        info["cand_B_not_discovery"], info["cand_B_after_cut"], info["cand_B_com_tl"] = drop["not_discovery"], drop["dated_after_cut"], len(c2)
        cand = pd.concat([c1, c2], ignore_index=True)
        assert_none_after(cand, "E", CUT_B, "an era-B candidate E")
        assert_none_after(cand, "D", CUT_B, "an era-B candidate D")
    del num_c
    cand = cand.sort_values(["E", "ticker"], kind="stable").reset_index(drop=True)
    _o = np.lexsort((cand["ticker"].to_numpy().astype(str), cand["E"].to_numpy().astype(str)))
    assert (_o == np.arange(len(cand))).all(), "the pandas (E, ticker) order differs from the engine's lexsort order"
    info[f"stream_{e}"] = len(cand)
    info[f"first_{e}"] = int((cand["retrigger"] == "0").sum())
    # watch rows
    if e == "A":
        wdf, _ = wl_read_tsv("watch_A", WHITELIST["watch_A"], WATCH_STR)
    else:
        wdf, wd = wl_read_tsv("watch_B", WHITELIST["watch_B"], WATCH_STR, keep=era_b_watch_keep)
        info["watch_B_dropped"] = wd["dropped_after_cut_or_holdout"]
        assert_none_after(wdf, "watch_date", CUT_B, "an era-B watch row")
    W = WatchTable(wdf)
    # integrity: the candidate row's copies equal the watch row at (ticker, D)
    wi = np.array([W.idx.get((t, d), -1) for t, d in zip(cand["ticker"], cand["D"])])
    assert (wi >= 0).all(), f"era {e}: {int((wi < 0).sum())} candidate rows without a watch row at D"
    for cc, wc in [("pivot", "pivot_tl"), ("adr20", "adr20"), ("base_len", "base_len"), ("pole_date", "pole_date")] + [(f, f) for f in TABLE_FEATURE_COLS]:
        a, b = cand[cc].to_numpy(), W.arr[wc][wi]
        same = np.array_equal(a.astype(float), b.astype(float), equal_nan=True) if cc != "pole_date" else bool((a == b).all())
        assert same, f"era {e}: candidates.{cc} != watch.{wc} at (ticker, D)"
    # the export (tickers of the stream + the readiness nights + SPY), cut at read for era B
    keep_t = set(cand["ticker"]) | {"SPY"}
    if e == "A":
        rd = ls["ready"]
        for k in ("ny_s0_all", "b_s0"):
            keep_t |= set(rd[k]["sym"])
    ex, n_after = wl_read_export(f"export_{e}", keep_t, CUT_B if e == "B" else None)
    info[f"export_{e}_dated_after_cut"] = n_after
    info[f"cal_{e}"] = len(ex.cal)
    assert ex.cal[-1] <= (CUT_B if e == "B" else ERA_A_LAST_DAY)
    fl, fdrop = read_flags(f"flags_{e}", CUT_B if e == "B" else None)
    info[f"flags_{e}_disc"] = len(fl)
    info[f"flags_{e}_dated_after_cut"] = fdrop.get("dated_after_cut", 0)
    disc = disc_index(fl, ex)
    E_ci = np.array([ex.cal_ci[x] for x in cand["E"]], dtype=np.int64)
    D_ci = np.array([ex.cal_ci[x] for x in cand["D"]], dtype=np.int64)
    assert (D_ci == E_ci - 1).all(), "a candidate whose D is not the session before E"
    # the 12 features of every stream row
    n = len(cand)
    X = np.full((n, len(FEATURE_KEYS)), np.nan)
    fcount = Counter()
    rowflags = {k: np.zeros(n, dtype=bool) for k in ("base_mismatch", "disc_rs_best", "disc_grp_pct", "disc_prior_move")}
    tk, Dd = cand["ticker"].to_numpy(), cand["D"].to_numpy()
    for i in range(n):
        X[i], f = features_for(tk[i], Dd[i], W, ex, disc.get(tk[i]))
        for k, v in f.items():
            if v:
                rowflags[k][i] = True
                fcount[k] += 1
    era = Era(name=e, cal=ex.cal, ticker=tk.astype(str), D=Dd.astype(str), E=cand["E"].to_numpy().astype(str), E_ci=E_ci,
              week=np.array([ap.iso_week(x) for x in cand["E"]]), year=np.array([int(x[:4]) for x in cand["E"]]),
              retrigger=cand["retrigger"].astype(int).to_numpy(), C1=cand["C1"].astype(int).to_numpy(), base_id=cand["base_id"].to_numpy().astype(str),
              phase={c: cand[c].to_numpy().astype(str) for c in ("phase_qqq_10_20", "phase_qqq_10_20_s5", "phase_spy_qqq_50", "apollo_regime")}, X=X,
              flags=rowflags)
    # the readiness nights (era A): the watch row at s0 + bars <= s0
    if e == "A":
        rd = ls["ready"]
        for k in ("ny_s0_all", "b_s0"):
            g = rd[k]
            Xr = np.full((len(g), len(FEATURE_KEYS)), np.nan)
            for j, (s, s0) in enumerate(zip(g["sym"], g["s0"])):
                Xr[j], _ = features_for(s, s0, W, ex, disc.get(s))
            era.ready[k] = dict(X=Xr, d_ci=np.array([ex.cal_ci[x] for x in g["s0"]], dtype=np.int64),
                                tl=(g["c0_tl_at_s0"] == "1").to_numpy(), key=list(zip(g["sym"], g["E_tl"])))
        ki = {k: i for i, k in enumerate(zip(era.ticker, era.E))}
        for k in ("ny_ev_all", "ny_ev", "b_ev"):
            era.ready[k] = dict(row=np.array([ki[x] for x in zip(rd[k]["sym"], rd[k]["E_tl"])], dtype=np.int64))
        ny43 = set(map(tuple, rd["ny_s0"][["vid", "ts", "screen_ticker"]].to_numpy().tolist()))
        era.ready["ny_s0_in43"] = np.array([tuple(x) in ny43 for x in rd["ny_s0_all"][["vid", "ts", "screen_ticker"]].to_numpy().tolist()])
    # GUARD 4 on a seeded sample of this era's stream rows (the caller decides the count per era)
    rng = np.random.default_rng(SEED + (0 if e == "A" else 1))
    pick = np.sort(rng.choice(n, size=min(lookahead_rows, n), replace=False)) if lookahead_rows else np.zeros(0, dtype=int)
    ref = {(tk[i], Dd[i]): X[i] for i in pick}
    nchk, diffs = lookahead_test([(tk[i], Dd[i]) for i in pick], W, ex, disc, reference=ref)
    info[f"lookahead_{e}"] = (nchk, diffs)
    info[f"feature_flags_{e}"] = dict(fcount)
    info[f"secs_{e}"] = time.time() - t0
    del ex, W, wdf, cand
    return era, info


# ═════════════════════════════════════════════════════════════════════════════════════════════
# printing helpers
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


def fmt(x, nd=3) -> str:
    return "-" if x is None or (isinstance(x, float) and x != x) else f"{x:.{nd}f}"


def coverage_lines(eras: dict) -> list:
    """Non-missing counts per feature over the stream and over each population (positives + negatives POOLED — no class split in the dry run)."""
    hdr = ["feature", "dir", "tag", "A stream", "A fit pop", "A 2021 pop", "B stream", "B check pop", "DISC-set-missing A / B"]
    rows = []
    A, B = eras["A"], eras["B"]
    popA_fit = (A.cls["pos"] | A.cls["neg"]) & A.cls["fit"]
    popA_hold = (A.cls["pos"] | A.cls["neg"]) & A.cls["hold"]
    popB = B.cls["pos"] | B.cls["neg"]
    for k in FEATURE_KEYS:
        j = FIDX[k]
        okA, okB = ~np.isnan(A.X[:, j]), ~np.isnan(B.X[:, j])
        dA = int(A.flags[f"disc_{k}"].sum()) if f"disc_{k}" in A.flags else 0
        dB = int(B.flags[f"disc_{k}"].sum()) if f"disc_{k}" in B.flags else 0
        rows.append([k, "lower" if FEATURES[k][0] < 0 else "higher", FEATURES[k][1],
                     f"{int(okA.sum())} of {len(okA)}", f"{int((okA & popA_fit).sum())} of {int(popA_fit.sum())}",
                     f"{int((okA & popA_hold).sum())} of {int(popA_hold.sum())}", f"{int(okB.sum())} of {len(okB)}",
                     f"{int((okB & popB).sum())} of {int(popB.sum())}", f"{dA} / {dB}" if k in DISC_FEATURES else "n/a"])
    w = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(len(hdr))]
    out = ["  " + " | ".join(str(h).ljust(w[i]) for i, h in enumerate(hdr)), "  " + "-+-".join("-" * x for x in w)]
    out += ["  " + " | ".join(str(c).ljust(w[i]) for i, c in enumerate(r)) for r in rows]
    return out


FREEZE_MARKER = "<!-- FREEZE -->"


def doc_body_sha(doc: str) -> str:
    """sha256 of the doc's BYTES above the `<!-- FREEZE -->` marker (the whole file when there is no marker). Taken at RUN time: any edit to the
    registration body after the freeze commit changes it, and the real run then refuses (the freeze record must carry the value).
    By hand: python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read().split(b'<!-- FREEZE -->',1)[0]).hexdigest())" <doc>"""
    with open(doc, "rb") as fh:
        return hashlib.sha256(fh.read().split(FREEZE_MARKER.encode(), 1)[0]).hexdigest()


def pins(extra: "dict | None" = None, doc: "str | None" = None) -> dict:
    p = {name: sha(path) for name, path in FILES.items()}
    p["join_script"] = sha(JOIN_SCRIPT)
    p["fit_module"] = sha(os.path.abspath(__file__))
    p["aplus_read"] = sha(os.path.join(REPO, "scripts", "probes", "_cb_backtest", "aplus_read.py"))
    p["registered_read"] = sha(os.path.join(REPO, "scripts", "probes", "_cb_backtest", "registered_read.py"))
    p["doc_body"] = doc_body_sha(doc or DOC)
    if extra:
        p.update(extra)
    return p


def freeze_missing(doc: str, p: dict) -> list:
    """The pins NOT yet written under the doc's `<!-- FREEZE -->` marker (the real run refuses unless this is empty)."""
    txt = open(doc).read()
    if FREEZE_MARKER not in txt:
        return list(p)
    tail = txt.split(FREEZE_MARKER, 1)[1]
    return [k for k, v in p.items() if v not in tail]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registered fit (pure on Era objects; the synthetic end-to-end test calls it directly)
# ═════════════════════════════════════════════════════════════════════════════════════════════
class GuardStop(Exception):
    pass


def auc_table(eras: dict, say, pos_key: str, neg_key: str, sets: list, title: str) -> dict:
    """AUC of all 12 features on each named set: ('fit' | 'hold' | 'B' | 'A'). Returns {set: [dict per feature]}."""
    out = {}
    for s in sets:
        era = eras["B"] if s == "B" else eras["A"]
        m = np.ones(len(era.E), dtype=bool) if s in ("A", "B") else era.cls[s]
        pos, neg = era.cls[pos_key] & m, era.cls[neg_key] & m
        out[s] = within_day_auc(era.Xo, era.E_ci, pos, neg)
    say(f"- {title}")
    hdr = "    feature                 dir    " + " ".join(f"{s:>22s}" for s in sets)
    say(hdr)
    for k in FEATURE_KEYS:
        j = FIDX[k]
        cells = []
        for s in sets:
            r = out[s][j]
            cells.append(f"{fmt(r['auc'])} (n {r['n_pos']}; skip {r['skip_missing']}/{r['skip_no_neg']})".rjust(22))
        say(f"    {k:23s} {'lower' if FEATURES[k][0] < 0 else 'higher':6s} " + " ".join(cells))
    say("    (n = positive events scored; skip = positives with a missing value / with no negative carrying a value that day)")
    return out


def run_fit(eras: dict, say, take_path: "str | None" = None, expect: "dict | None" = EXPECT) -> dict:
    """The REAL fit, in the registered order: guard 2, the screen, the subset, guard 3, the score / cap / TAKE, recall on fit / 2021 / era B,
    the plateau, the bar, the beside rows, the readiness contrast. Guard 1 (whitelist) and guard 4 (look-ahead) ran at load."""
    A, B = eras["A"], eras["B"]
    res = {}
    # ---------------------------------------------------------------- GUARD 2
    fitpos, fitneg = A.cls["pos"] & A.cls["fit"], A.cls["neg"] & A.cls["fit"]
    ok2, means = guard2_shuffle(A.Xo, A.E_ci, fitpos, fitneg)
    say(f"\n## GUARD 2 — shuffle before the fit: positive flag permuted within each fit E date, {PERMS} permutations, seed {SEED}; "
        f"band [{GUARD2_BAND[0]}, {GUARD2_BAND[1]}]")
    say("    " + " | ".join(f"{k} {m:.4f}" for k, m in zip(FEATURE_KEYS, means)))
    res["guard2"] = (ok2, means)
    if not ok2:
        say("    GUARD 2 FAILED — a feature's shuffled mean AUC left the band (a leak or a bug). STOP.")
        raise GuardStop("guard 2")
    say("    PASS — every feature's shuffled mean AUC lies in the band")
    # ---------------------------------------------------------------- the screen + the subset (fit set only)
    say(f"\n## THE SCREEN — within-day AUC on the FIT set (E <= {FIT_LAST_E}): {int(fitpos.sum())} positive events vs {int(fitneg.sum())} same-day negatives")
    fit_auc = within_day_auc(A.Xo, A.E_ci, fitpos, fitneg)
    aucs = {k: fit_auc[FIDX[k]]["auc"] for k in FEATURE_KEYS}
    for k in FEATURE_KEYS:
        r = fit_auc[FIDX[k]]
        say(f"    {k:23s} {'lower' if FEATURES[k][0] < 0 else 'higher':6s} better ({FEATURES[k][1]:3s}) AUC {fmt(r['auc'], 4)} | n {r['n_pos']} positives scored,"
            f" {r['skip_missing']} missing, {r['skip_no_neg']} with no negative value that day, {r['n_neg']} negative values")
    subset, against = subset_rule(aucs)
    res.update(fit_auc=aucs, subset=subset, against=against)
    say(f"\n## THE SUBSET — fit AUC >= {SCREEN}, descending, at most {MAX_SUBSET}; below {AGAINST} = against the fixed direction, excluded")
    say(f"- chosen: {subset if subset else 'NONE'}")
    say(f"- against the fixed direction (reported, never flipped): {[(k, round(aucs[k], 4)) for k in against] if against else 'none'}")
    if not subset:
        verdict, why = bar_verdict(True, 0, "n/a", 0)
        res.update(verdict=verdict, why=why)
        say(f"\n## BAR VERDICT: {verdict} — {why}. All 12 fit AUCs above. No filter, no TAKE table; §7: his R2 definition is the combined test's filter.")
        auc_table(eras, say, "pos", "neg", ["hold", "B"], "check-set AUCs (descriptive; no subset)")
        return res
    sidx = [FIDX[k] for k in subset]
    # ---------------------------------------------------------------- the score / cap (label-free) and GUARD 3
    eng = {e: PoolEngine(eras[e].Xo, eras[e].E_ci, eras[e].ticker, eras[e].week) for e in ("A", "B")}
    rated = {(e, N): eng[e].rate(sidx, N) for e in ("A", "B") for N in NS}
    holdpos, holdneg = A.cls["pos"] & A.cls["hold"], A.cls["neg"] & A.cls["hold"]
    take6 = rated[("A", N_DECIDES)]["flag"] == FLAG_TAKE
    ok3, m3 = guard3_shuffle(take6, A.E_ci, holdpos, holdneg)
    say(f"\n## GUARD 3 — the registered subset's TAKE flags (N = {N_DECIDES}) on the 2021 positive flags permuted within each E date, {PERMS} permutations:"
        f" mean count {m3:.3f} (must be <= {GUARD3_MAX}; chance about 0.66)")
    res["guard3"] = (ok3, m3)
    if not ok3:
        say("    GUARD 3 FAILED. STOP (the hold-out is not read).")
        raise GuardStop("guard 3")
    say("    PASS")
    # ---------------------------------------------------------------- TAKE, recall
    say(f"\n## SCORE / CAP / TAKE (subset {subset}; pool = every tl row with E' in [E-{POOL_SESSIONS}, E-1], floor {POOL_FLOOR}, a missing feature 0.5;"
        f" cutoff = the {cutoff_rank(N_DECIDES)}th-highest reference score; cap {N_DECIDES} a week in (E, ticker) order)")
    for e in ("A", "B"):
        r = rated[(e, N_DECIDES)]
        fc = Counter(r["flag"])
        wk = Counter(eras[e].week[r["flag"] == FLAG_TAKE])
        allw = sorted(set(eras[e].week))
        per = np.array([wk.get(w, 0) for w in allw])
        say(f"- era {e}: rows {len(r['flag'])} | TAKE {fc[FLAG_TAKE]} | CAPPED {fc[FLAG_CAPPED]} | PASS {fc[FLAG_PASS]} | UNRATED {fc[FLAG_UNRATED]}"
            f" (strict reading R-a beside: {int(r['strict_unrated'].sum())} rows with fewer than {cutoff_rank(N_DECIDES)} members carrying every chosen feature)")
        say(f"    TAKE per ISO week over {len(allw)} weeks: median {float(np.median(per)):.1f}, max {int(per.max()) if len(per) else 0}, weeks at the cap {int((per == N_DECIDES).sum())}"
            f" | pool size median {int(np.median(eng[e].pool_n))}")
        t = r["flag"] == FLAG_TAKE
        if t.any():
            say(f"    TAKE rows: C1 {int((eras[e].C1[t] == 1).sum())} ({100 * float((eras[e].C1[t] == 1).mean()):.1f}%; stream {100 * float((eras[e].C1 == 1).mean()):.1f}%)"
                f" | first breaks {int((eras[e].retrigger[t] == 0).sum())} ({100 * float((eras[e].retrigger[t] == 0).mean()):.1f}%; stream {100 * float((eras[e].retrigger == 0).mean()):.1f}%)")
    # the no-information rate (label-free; the doc's denominator = the tl rows with E in calendar 2021 — the hold-out SET also holds the
    # 2022-01-03 rows, era A's last E, printed beside) and the chance expectation of the 66 on their own weeks
    hold = A.cls["hold"]
    y21 = hold & (A.year == 2021)
    wk21 = Counter(A.week[y21])
    nir = sum(min(N_DECIDES, v) for v in wk21.values()) / max(int(y21.sum()), 1)
    wkc = Counter(A.week[hold])
    chance = sum(min(N_DECIDES, wkc[w]) / wkc[w] for w in A.week[holdpos])
    say(f"- the 2021 no-information rate: sum min({N_DECIDES}, rows in the week) / {int(y21.sum())} tl rows with E in 2021 = {100 * nir:.2f}% -> {nir * HOLDOUT_N:.2f} of {HOLDOUT_N} expected"
        f" (beside: the hold-out set also holds {int((hold & ~y21).sum())} rows of 2022-01-03, {int((holdpos & ~y21).sum())} of them positive);"
        f" chance on the 66's own weeks {chance:.2f}; P(>= {BAR_PASS} | Poisson {nir * HOLDOUT_N:.2f}) = {100 * poisson_tail(BAR_PASS, nir * HOLDOUT_N):.2f}%")
    say(f"\n## RECALL — the share of positive events flagged TAKE (N = {N_DECIDES} decides; 4 and 8 beside)")
    rec = {}
    for nm, era, m in (("fit 2017-20", A, A.cls["fit"]), ("hold-out 2021", A, A.cls["hold"]), ("era B 2022-23", B, np.ones(len(B.E), dtype=bool))):
        cells = []
        for N in NS:
            f = rated[(era.name, N)]["flag"]
            p = era.cls["pos"] & m
            k = int((p & (f == FLAG_TAKE)).sum())
            rec[(nm, N)] = k
            cells.append(f"N={N}: {k} of {int(p.sum())}" + (f" (CAPPED {int((p & (f == FLAG_CAPPED)).sum())}, UNRATED {int((p & (f == FLAG_UNRATED)).sum())})" if N == N_DECIDES else ""))
        say(f"- {nm}: " + " | ".join(cells))
    c = rec[("hold-out 2021", N_DECIDES)]
    eb = rec[("era B 2022-23", N_DECIDES)]
    res.update(c=c, era_b=eb, recall=rec)
    # ---------------------------------------------------------------- check-set AUCs
    say("")
    res["check_auc"] = auc_table(eras, say, "pos", "neg", ["fit", "hold", "B"], "the 12 AUCs on the fit set and the two check sets (fixed directions)")
    # ---------------------------------------------------------------- plateau
    def count_hold(sub: list) -> int:
        if not sub:
            return 0
        f = eng["A"].rate([FIDX[k] for k in sub], N_DECIDES)["flag"]
        return int((holdpos & (f == FLAG_TAKE)).sum())
    pl = plateau(aucs, subset, count_hold, c)
    res["plateau"] = pl
    say(f"\n## PLATEAU — every neighbour must flag at least max(4, ceil(0.75 x {c})) = {pl['need']} of the {HOLDOUT_N} hold-out events at N = {N_DECIDES} (one-sided)")
    for r in pl["neighbours"]:
        say(f"- {r['name']}: subset {r['subset'] if r['subset'] else 'EMPTY'} -> {r['count']} flagged -> {'ok' if r['ok'] else 'BELOW'}")
    say(f"- plateau: {pl['verdict']}" + (f" — {pl['note']}" if pl["note"] else ""))
    # ---------------------------------------------------------------- the bar
    verdict, why = bar_verdict(False, c, pl["verdict"], eb)
    res.update(verdict=verdict, why=why)
    say(f"\n## BAR VERDICT (decided on the 2021 hold-out, in events): {verdict} — {why}")
    say(f"    PASS >= {BAR_PASS} of {HOLDOUT_N} with the plateau and >= 1 of the {int(B.cls['pos'].sum())} era-B events | FAIL <= {BAR_FAIL} or an empty subset | CAN'T TELL otherwise."
        f" The bar is coarse: one event moves a verdict at its edges.")
    # ---------------------------------------------------------------- beside rows
    say("\n## BESIDE (descriptive, never deciding)")
    for nm, key in (("post-E-only events (hindsight)", "post"), ("strictly-before events (clean of E)", "strict")):
        cells = []
        for snm, era, m in (("fit", A, A.cls["fit"]), ("2021", A, A.cls["hold"]), ("era B", B, np.ones(len(B.E), dtype=bool))):
            p = era.cls[key] & m
            f = rated[(era.name, N_DECIDES)]["flag"]
            cells.append(f"{snm} {int((p & (f == FLAG_TAKE)).sum())} of {int(p.sum())}")
        say(f"- recall on the {nm}: " + " | ".join(cells))
    fA = rated[("A", N_DECIDES)]["flag"]
    for nm, key in (("not-yet EVENTS (all)", "ny"), ("not-yet events carrying no positive label", "ny_only")):
        p = A.cls[key]
        say(f"- share of era-A {nm} flagged TAKE: {int((p & (fA == FLAG_TAKE)).sum())} of {int(p.sum())} (descriptive; not the readiness contrast)")
    for e in ("A", "B"):
        era = eras[e]
        f = rated[(e, N_DECIDES)]["flag"]
        t = f == FLAG_TAKE
        yrs = sorted(set(era.year))
        say(f"- era {e} by year of E: " + " | ".join(f"{y}: TAKE {int((t & (era.year == y)).sum())}, positives flagged {int((t & era.cls['pos'] & (era.year == y)).sum())} of {int((era.cls['pos'] & (era.year == y)).sum())}" for y in yrs))
        for ph in ("phase_qqq_10_20", "phase_qqq_10_20_s5", "phase_spy_qqq_50", "apollo_regime"):
            vals = sorted(set(era.phase[ph]))
            if vals == [""]:
                say(f"    by {ph}: n/a (empty for every row)")
                continue
            say(f"    by {ph} at D: " + " | ".join(f"'{v}': rows {int((era.phase[ph] == v).sum())}, TAKE {int((t & (era.phase[ph] == v)).sum())}, positives flagged {int((t & era.cls['pos'] & (era.phase[ph] == v)).sum())} of {int((era.cls['pos'] & (era.phase[ph] == v)).sum())}" for v in vals))
    say("")
    auc_table(eras, say, "at0", "neg", ["A", "B"], "AUCs on the delta-0 subset (a positive label exactly on E; the only timing signal) against the same-day negatives")
    auc_table(eras, say, "own", "neg", ["fit", "hold", "B"], "AUCs on the own-line subset (the positive grade's phrase in the ticker's own caption line)")
    auc_table(eras, say, "bpos", "bneg", ["fit", "hold", "B"], "AUCs on the base-level reading (every tl row of a GRADED base positive; reading R-h)")
    for snm, era, m in (("fit", A, A.cls["fit"]), ("2021", A, A.cls["hold"]), ("era B", B, np.ones(len(B.E), dtype=bool))):
        p = era.cls["bpos"] & m
        f = rated[(era.name, N_DECIDES)]["flag"]
        say(f"- base-level recall {snm}: {int((p & (f == FLAG_TAKE)).sum())} of {int(p.sum())} rows")
    # ---------------------------------------------------------------- the readiness contrast (era A)
    say("\n## READINESS CONTRAST (outcome-free; the state he was looking at; expected: the not-yet side scores LOWER)")
    rd = A.ready
    sc_ny, pn_ny = score_at_nights(A.Xo, A.E_ci, rd["ny_s0_all"]["X"] * DIRECTION, rd["ny_s0_all"]["d_ci"], sidx)
    sc_b, pn_b = score_at_nights(A.Xo, A.E_ci, rd["b_s0"]["X"] * DIRECTION, rd["b_s0"]["d_ci"], sidx)
    in43 = rd["ny_s0_in43"]

    def desc(x):
        x = x[~np.isnan(x)]
        return f"n {len(x)}, median {fmt(float(np.median(x)) if len(x) else math.nan)}, mean {fmt(float(x.mean()) if len(x) else math.nan)}"
    say(f"- at s0 (reading R-d): not-yet {desc(sc_ny[in43])} vs bought {desc(sc_b)} -> P(bought scores above not-yet) {fmt(pair_auc(sc_b, sc_ny[in43]))}")
    say(f"    beside: the 50 not-yet before the 15-event exclusion {desc(sc_ny)} (pair AUC {fmt(pair_auc(sc_b, sc_ny))});"
        f" bought with a trendline at s0 {desc(sc_b[rd['b_s0']['tl']])} (pair AUC vs the 43 {fmt(pair_auc(sc_b[rd['b_s0']['tl']], sc_ny[in43]))});"
        f" pool size at s0 min {int(min(pn_ny.min(), pn_b.min()))}")
    s6 = rated[("A", N_DECIDES)]["score"]
    ny_ev, ny_ev_all, b_ev = s6[rd["ny_ev"]["row"]], s6[rd["ny_ev_all"]["row"]], s6[rd["b_ev"]["row"]]
    say(f"- beside, at the matched event's D (delta 0 or +1): not-yet {desc(ny_ev)} vs bought {desc(b_ev)} -> pair AUC {fmt(pair_auc(b_ev, ny_ev))};"
        f" the 32 before the exclusion {desc(ny_ev_all)} (pair AUC {fmt(pair_auc(b_ev, ny_ev_all))})")
    # ---------------------------------------------------------------- the TAKE table (label-free; the §8 interface's columns)
    if take_path:
        rows = []
        for e in ("A", "B"):
            era = eras[e]
            r6, r4, r8 = rated[(e, 6)], rated[(e, 4)], rated[(e, 8)]
            P = eng[e].own[:, sidx]
            for i in range(len(era.E)):
                rows.append([e, era.ticker[i], era.D[i], era.E[i], "tl", int(era.retrigger[i]), era.base_id[i], int(eng[e].pool_n[i]),
                             f"{r6['score'][i]:.10f}", "" if r6["cutoff"][i] != r6["cutoff"][i] else f"{r6['cutoff'][i]:.10f}", r6["flag"][i], r4["flag"][i], r8["flag"][i]]
                            + ["" if x != x else f"{x:.10f}" for x in P[i]])
        cols = ["era", "ticker", "D", "E", "K", "retrigger", "base_id", "pool_n", "score", "cutoff", "flag", "flag_N4", "flag_N8"] + [f"pct_{k}" for k in subset]
        tmp = take_path + ".partial"
        with open(tmp, "w") as fh:
            fh.write("\t".join(cols) + "\n")
            for r in rows:
                fh.write("\t".join(str(x) for x in r) + "\n")
        os.replace(tmp, take_path)
        say(f"\n- TAKE table written: {take_path} ({len(rows)} rows; a blank pct = a missing feature counted 0.5)")
    return res


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.add_argument("--dry-run", action="store_true", help="load + populations + feature coverage + look-ahead + pins; no AUC / score / recall / shuffle")
    args = ap_.parse_args(argv)
    say = Say()
    dry = args.dry_run
    outfile = DRY_PRINTOUT if dry else PRINTOUT
    if not dry:
        existing = [p for p in (PRINTOUT, TAKE_TSV, STOPPED) if os.path.exists(p)]
        if existing:
            print(f"REFUSED: output(s) already on disk: {existing} (the fit runs once; a STOPPED file is removed by hand after the fix)", file=sys.stderr)
            return 2
    t0 = time.time()
    say(f"# #705 Track A — 02_fit_filter ({'DRY RUN: no AUC, no score against labels, no recall, no shuffle on real labels' if dry else 'THE REGISTERED FIT'})")
    say(f"# registration: {os.path.relpath(DOC, REPO)} §5; directions fixed; the module's readings R-a..R-i are in its header")
    # ---------------------------------------------------------------- pins (refuse on drift of a pinned input)
    p = pins()
    drift = [f"{k}: {p[k]} (pinned {v})" for k, v in PINNED.items() if p.get(k) != v]
    say("\n## Pins (sha256)")
    for k, v in p.items():
        if k == "doc_body":
            say(f"- doc_body: {v}  <- live sha256 of the doc text above `{FREEZE_MARKER}` = the value the freeze commit must pin "
                f"(any later edit above the marker changes it and the real run refuses)")
        else:
            say(f"- {k}: {v}  {FILES.get(k, '')}")
    if drift:
        say("REFUSED: a pinned input changed: " + "; ".join(drift))
        say.write(outfile if dry else STOPPED)
        return 2
    miss = freeze_missing(DOC, p)
    say(f"- freeze record: {'every pin above is written under the FREEZE marker' if not miss else 'NOT YET under the FREEZE marker: ' + ', '.join(miss)}")
    if not dry and miss:
        say("REFUSED: the real fit runs only after the freeze commit records this module and every input pin under the marker.")
        print("\n".join(say.lines[-2:]), file=sys.stderr)
        return 2
    # ---------------------------------------------------------------- labels -> populations
    J, _ = wl_read_tsv("labels_joined", WHITELIST["labels_joined"], WHITELIST["labels_joined"])
    ME, _ = wl_read_tsv("matched_events", WHITELIST["matched_events"], WHITELIST["matched_events"])
    MO, _ = wl_read_tsv("moments", WHITELIST["moments"], WHITELIST["moments"])
    ls = label_sets(J, ME, MO, load_grade_rx())
    lab_counts = {"own_bought": ls["own_counts"]["bought"], "own_not_yet": ls["own_counts"]["not_yet"], "own_best": ls["own_counts"]["best"],
                  "posny_A": len(ls["posny_ev"]["A"]), "posny_bought_A": ls["posny_bought"]}
    lab_counts.update({f"ready_{k}": len(v) for k, v in ls["ready"].items()})
    # ---------------------------------------------------------------- the two eras
    eras, info = {}, {}
    for e in ("A", "B"):
        era, inf = load_era(e, ls, say, lookahead_rows=LOOKAHEAD_N // 2)
        assign_classes(era, ls)
        eras[e], info = era, {**info, **inf}
    got = {**{k: info[k] for k in ("stream_A", "first_A", "stream_B", "first_B", "cal_A", "cal_B", "watch_B_dropped", "cand_B_not_discovery", "cand_B_after_cut")},
           **population_counts(eras), **lab_counts, "rows_2021": int((eras["A"].cls["hold"] & (eras["A"].year == 2021)).sum()),
           "rows_hold_A": int(eras["A"].cls["hold"].sum()), "rows_hold_2022_01_03": int((eras["A"].cls["hold"] & (eras["A"].year == 2022)).sum()),
           "pos_hold_2022": int((eras["A"].cls["pos"] & (eras["A"].year == 2022)).sum()), "neg_hold_2022": int((eras["A"].cls["neg"] & (eras["A"].year == 2022)).sum())}
    say("\n## Reads (GUARD 1 — every file through the whitelist; columns exactly as listed)")
    for name, path, cols, n, dropped in READ_LOG:
        say(f"- {name}: {n} rows kept{(' | dropped at read ' + str(dropped)) if dropped else ''} | columns {list(cols)}")
    bad_reads = [r for r in READ_LOG if r[0] not in WHITELIST or not set(r[2]) <= set(WHITELIST[r[0]])]
    assert not bad_reads, bad_reads
    say(f"- whitelist: {len(READ_LOG)} reads, every one inside its entry; no E-day, forward or outcome column on any entry (FORBIDDEN checked at import)")
    say(f"- era B candidates_com.tsv: {info['cand_B_com_tl']} tl rows (it carries `com` only; read for the pinned dropped-at-read counts)")
    say("\n## Populations (asserted; the registration's numbers)")
    for k in sorted(got):
        say(f"- {k}: {got[k]}" + ("" if EXPECT.get(k, got[k]) == got[k] else f"  <-- registered {EXPECT[k]}"))
    bad = check_expect(got, EXPECT, say)
    if bad:
        say.write(outfile if dry else STOPPED)
        return 3
    say("- every population equals the registration (§2h, §4, §5)")
    say("\n## Feature computation")
    for e in ("A", "B"):
        say(f"- era {e}: {len(eras[e].E)} rows in {info[f'secs_{e}']:.0f}s | export rows dated after the cut dropped at read {info[f'export_{e}_dated_after_cut']}"
            f" | calendar {info[f'cal_{e}']} sessions {eras[e].cal[0]}..{eras[e].cal[-1]} | DISCONTINUOUS events in the flags {info[f'flags_{e}_disc']}"
            f" (dated after the cut, dropped {info[f'flags_{e}_dated_after_cut']}) | rule hits {info[f'feature_flags_{e}']}")
    nA = int(eras["A"].flags["base_mismatch"].sum())
    nB = int(eras["B"].flags["base_mismatch"].sum())
    say(f"- base rows != base_len + 1 or h at P != pole_high (wk_ratio / pb_ratio missing, counted): era A {nA}, era B {nB}")
    say(f"- DISCONTINUOUS rule (reading R-b; the group-aggregate exclusion is NOT applied — the pinned grp_pct is a whole-universe cross-section off the whitelist)")
    for e in ("A", "B"):
        era = eras[e]
        anyd = era.flags["disc_rs_best"] | era.flags["disc_grp_pct"] | era.flags["disc_prior_move"]
        pop = era.cls["pos"] | era.cls["neg"]
        say(f"    era {e}: rows with a present value set MISSING — rs_best {int(era.flags['disc_rs_best'].sum())}, grp_pct {int(era.flags['disc_grp_pct'].sum())},"
            f" prior_move {int(era.flags['disc_prior_move'].sum())}; rows affected on any {int(anyd.sum())} (of them in the fit/check populations {int((anyd & pop).sum())})")
    say("\n## Coverage — non-missing values per feature (the population columns pool positives and negatives; no class split)")
    for ln in coverage_lines(eras):
        say(ln)
    rdA = eras["A"].ready
    rX = np.vstack([rdA["ny_s0_all"]["X"], rdA["b_s0"]["X"]])
    say(f"- readiness nights at s0 (not-yet 50 + bought 176 pooled, {len(rX)} nights): " + ", ".join(f"{k} {int((~np.isnan(rX[:, FIDX[k]])).sum())}" for k in FEATURE_KEYS))
    say("\n## GUARD 4 — look-ahead test (bars, watch rows and flag dates after D replaced with noise; features must be identical)")
    la_bad = []
    for e in ("A", "B"):
        nchk, diffs = info[f"lookahead_{e}"]
        la_bad += diffs
        say(f"- era {e}: {nchk} rows checked (seed {SEED + (0 if e == 'A' else 1)}) -> {len(diffs)} differ" + (f": {diffs[:5]}" if diffs else ""))
    if la_bad:
        say("GUARD 4 FAILED — a feature reads past D. STOP.")
        say.write(outfile if dry else STOPPED)
        return 3
    say(f"- PASS: {LOOKAHEAD_N} rows, every feature identical with everything after D replaced")
    if dry:
        say(f"\n## DRY RUN ends here: no AUC, no score against labels, no recall, no shuffle on real labels was computed. ({time.time() - t0:.0f}s)")
        say.write(DRY_PRINTOUT)
        return 0
    try:
        run_fit(eras, say, take_path=TAKE_TSV)
    except GuardStop as g:
        say(f"\nSTOPPED at {g}. ({time.time() - t0:.0f}s)")
        say.write(STOPPED)
        return 3
    say(f"\n({time.time() - t0:.0f}s)")
    say.write(PRINTOUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
