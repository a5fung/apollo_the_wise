"""#705 (b) - the A+ RATING read (docs/analysis/cb_aplus_rating_prereg_2026-10-21.md) on the registered-read scaffold. BUILT ON
SYNTHETIC DATA; the build computed no real outcome (`aplus-profile` reads minute VOLUMES only; `aplus-read --dry-run` counts features).

Stages (every one dispatched by runner.py):
  aplus-profile   --data CB702 --data-pre CB702_PRE          the pinned intraday volume profile (the PROFILE block): the 2017-21 tree's
                                                             ok pairs minus zero-volume days, early-close sessions and the population's own
                                                             pairs; the pointwise median of CUM(m); `cb702_pre/out/aplus_intraday_profile.tsv`
                                                             byte for byte; refuses to overwrite; exit 3 unless its sha256 equals EXPECTED
  aplus-read      --period pre|discovery                     the deciding read (a RegisteredRead): the freeze, STEP 0 (equality targets), the
                                                             rating, the WOULD-FAIL-IF checks, the independent re-derivation, the bars, the
                                                             verdict file. `--dry-run` = the census only; `--dry-run --self-check` adds the
                                                             rating counts and the checks (no outcome column is opened by either)
  aplus-confirm   --period holdout                           the SAME rule on the sealed 2025-26 table; refuses unless both deciding verdict
                                                             files exist and the consequence cell reads RECORD
  aplus-hindsight --period pre|discovery                     the 39 and the within-week top-N; refuses until BOTH verdict files exist
  aplus-verdict                                              reads both verdict JSONs and prints the consequence cell, nothing else

Every helper of the runner is reached through the runtime module (`ctx.rt` / `rt`) so this module imports no runner code at import time
(the runner imports it to register the reads). The scaffold pins this file as `spec module`; the re-derivation module is pinned by name.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import sys
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from scripts.probes._cb_backtest import registered_read as rr

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants (every number is the doc's)
# ═════════════════════════════════════════════════════════════════════════════════════════════
APLUS_DOC = "cb_aplus_rating_prereg_2026-10-21.md"
APLUS_TAG = "aplus"
APLUS_PERIODS = ("pre", "discovery")                      # the two deciding eras; both decide
CONFIRM_PERIODS = ("holdout",)                            # the sealed 2025-26 read
PROFILE_NAME = "aplus_intraday_profile.tsv"               # under cb702_pre/out - ONE constant for every era
PROFILE_SHA_EXPECTED = "0a5bf816ed8d1e241aa80bb8db17012923ad9a8cad7222433a6df9268fa4bedb"   # the recheck's independent build
PROFILE_PINS = {5: 0.029973, 10: 0.045943, 30: 0.105939, 60: 0.189745, 120: 0.334574, 210: 0.503368, 300: 0.661951, 389: 0.971481}
PROFILE_TALLY = {"ok": 126811, "zero": 9, "early": 937, "population": 13258, "kept": 112607}
PROFILE_TOL = 1e-6
POOL_SESSIONS = 20                                        # the pool: population fills with E' in [E - 20, E - 1] sessions
STAIR_SESSIONS = 120                                      # concept 5's window: candidate rows with E' in [E - 120, E - 1]
POOL_FLOOR = 30                                           # |S| >= 30 non-missing pool values, every concept (per scale for concept 1)
NS = (1, 3, 5)                                            # N = 3 decides; 1 and 5 beside
N_DECIDES = 3
CUTOFF_RANK = {1: 4, 3: 12, 5: 20}                        # the cutoff = the rank-th highest reference score (N x 4 weeks of pool)
MIN_N = 30                                                # the PASS bar's n floor
BOOT_DRAWS, BOOT_SEED = 2000, 702
TAIL_R, TAIL_WIDTH_ADR, TAIL_TICKERS, TAIL_MONTHS = 10.0, 0.25, 3, 3
BURN_IN_WEEKS = 4
SAMPLE_SEED = 702
CHECK1_SAMPLE, CHECK2_SAMPLE, CHECK9_SAMPLE, CHECK12_SAMPLE = 50, 50, 50, 200
EDGE_DROP = {"pre": "2022-01-03", "discovery": None, "holdout": "2025-01-03"}      # the fill dates whose ISO week belongs to another era
ERA_LAST_MONDAY = {"pre": dt.date(2021, 12, 31), "discovery": dt.date(2024, 12, 31), "holdout": dt.date(2099, 12, 31)}
ERA_FIRST_MONDAY = {"pre": dt.date(1900, 1, 1), "discovery": dt.date(2022, 1, 1), "holdout": dt.date(2025, 1, 1)}
# C0 = the PUBLISHED C0 tl ORH5 pp row of the era, its mature fills (the edge fills STAY in the baseline - one choice)
C0_PUBLISHED = {"pre": {"n": 13363, "ge10": 165, "mean_r": 0.025, "ge5_per100": 3.47, "ge10_per100": 1.235},
                "discovery": {"n": 8984, "ge10": 85, "mean_r": -0.169, "ge5_per100": 2.57, "ge10_per100": 0.946},
                "holdout": {"n": 7531, "ge10": 89, "mean_r": -0.129, "ge5_per100": 2.95, "ge10_per100": 1.18}}
EXPECT_APLUS_N = {"pre": (520, 760), "discovery": (300, 435), "holdout": (215, 279)}
THE_39 = ("LVGO", "TSLA", "PTON", "ZM", "NIO", "PLUG", "ENPH", "FUBO", "ETSY", "CRWD", "DOCU", "NVAX", "BLNK", "SE", "SHOP", "FSLY", "NET",
          "DDOG", "NXH", "W", "CVNA", "APPS", "SNAP", "MRNA", "TDOC", "ROKU", "PINS", "UPST", "GME", "AMC", "DKNG", "FVRR", "PENN", "QS",
          "SPCE", "TTD", "LULU", "NVDA", "AMD")
FM_BINS = ((5, 10), (10, 15), (15, 30), (30, 60), (60, 120), (120, 180), (180, 240), (240, 300), (300, 360), (360, 390))

# STEP 0 equality targets (check 2) - the doc's tables, per period. The holdout's census beyond the five pinned counts is TAKEN at the
# confirm read (printed, not compared).
APLUS_EXPECTED = {
    "pre": {"joined": 13368, "fills": 13359, "open": 5, "weeks": 253, "dropped": 9, "c5_unrated": 505, "thin": 36,
            "wk_present": 5166, "wk_floor_strip": 346, "pb_present": 5713, "pb_floor_strip": 234, "both": 4391, "neither": 6871,
            "fm_bins": (4355, 1396, 2111, 1760, 1544, 693, 510, 429, 335, 226), "fm_min": 5, "fm_max": 389, "fm_at5": 2040, "fm_ge210": 1213,
            "fm_median": 19, "fm_q1": 7, "fm_q3": 70, "fm_p90": 196, "absent_any": 7448, "min0_absent": 123,
            "zero_vol": (("RUBI", "2020-06-23"), ("ABTC", "2021-02-25"), ("ABTC", "2021-03-02")), "early": 100, "early_ge210": 1,
            "exp_missing": 0, "exp_le0": 458, "exp_median": 0.4307, "exp_q1": 0.2390, "exp_q3": 0.6758, "rho_width": 0.427, "rho_fm": 0.054,
            "grp_present": 9059},
    "discovery": {"joined": 8989, "fills": 8989, "open": 5, "weeks": 145, "dropped": 0, "c5_unrated": 1778, "thin": 77,
                  "wk_present": 3919, "wk_floor_strip": 79, "pb_present": 4138, "pb_floor_strip": 49, "both": 3291, "neither": 4223,
                  "fm_bins": (2811, 960, 1428, 1300, 970, 449, 311, 320, 280, 160), "fm_min": 5, "fm_max": 389, "fm_at5": 1295, "fm_ge210": 902,
                  "fm_median": 20, "fm_q1": 8, "fm_q3": 70, "fm_p90": 210, "absent_any": 5082, "min0_absent": 93,
                  "zero_vol": (), "early": 89, "early_ge210": 1,
                  "exp_missing": 0, "exp_le0": 370, "exp_median": 0.4347, "exp_q1": 0.2371, "exp_q3": 0.6859, "rho_width": 0.417, "rho_fm": 0.026,
                  "grp_present": 7291},
    "holdout": {"joined": 7570, "fills": 7547, "open": 39, "weeks": 93, "dropped": 23, "c5_unrated": 0, "thin": 0},
}
EXP_TOL, RHO_TOL = 1e-4, 1e-3

# the exitpb table's columns that are OUTCOMES - never read before STEP 0 and the checks; never read by a dry run
OUTCOME_COLS = ("status", "realized_r", "pnl_adr", "acct_pct", "sessions_held", "fill_day_stop", "partial_kind", "partial_session", "partial_px",
                "stop_to", "exit_kind", "exit_px", "exit_session", "stopped_after_third_le_fill", "beabove", "beabove_kind", "fwd_bars", "fwd_hole")
FILL_COLS = ["ticker", "D", "E", "K", "entry", "arm", "fill", "fill_minute", "fill_month", "adr20", "width_adr", "stop", "mature", "open_mark",
             "early_close", "phase_qqq_10_20"]
# the candidates columns read - `base_id` and every E-day column (open_E, high_E, low_E, close_E, vol_E, breakout_vol_x) are NOT among them
CAND_COLS = ["ticker", "D", "E", "K", "split", "retrigger", "pole_date", "pole_ci", "adv20_vol_D", "prior_move", "base_len", "base_depth",
             "tightening_ratio", "atr14_slope", "rs_best", "rs_all", "grp_pct", "phase_qqq_10_20"]
CAND_LOOKAHEAD_COLS = ["open_E", "high_E", "low_E", "close_E", "vol_E", "breakout_vol_x"]       # joined back ONLY for check 1's shuffle
WATCH_COLS = ["ticker", "watch_date", "close", "pole_date", "pole_ci", "pole_high", "range_recent5", "range_early5", "adr20"]
P5_COLS = ["ticker", "D", "E", "K", "arm", "stop_variant", "range5_adr"]
P5_ARM, P5_STOP = "c3_p33_t20_cut3", "lod"
POP_ARM, POP_ENTRY, POP_K = "pp", "orh5", "tl"

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the score specs: ONE engine over feature percentiles. A feature is oriented (dir = +1 higher is better, -1 lower is better) before the
# pool percentile; a spec names its required features, its optional ones (missing -> scored on the rest), its composite (concept 1: the
# mean of the three scale percentiles, a missing scale 0.5, the daily scale required) and the features it reads reversed (pct -> 1 - pct).
# ═════════════════════════════════════════════════════════════════════════════════════════════
FEATURES = {                                             # feature key -> (column, direction)
    "c1_daily": ("tightening_ratio", -1), "c1_wk": ("wk_ratio", -1), "c1_pb": ("pb_ratio", -1),
    "c2": ("vol_dry5", -1), "c3": ("rs_best", +1), "c4": ("prior_move", +1), "c5": ("stair_n", -1), "c6": ("exp_up_adr", +1),
    "c7": ("vol_sofar_x", +1), "grp": ("grp_pct", +1),
    "base_len": ("base_len", +1), "range5_adr": ("range5_adr", -1), "base_depth": ("base_depth", -1), "atr14_slope": ("atr14_slope", -1),
    "rs_all": ("rs_all", +1), "range_sofar_adr": ("range_sofar_adr", +1),
}
FEATURE_KEYS = tuple(FEATURES)
CORE_REQUIRED = ("c1", "c2", "c3", "c4", "c6", "c7")
C1_SCALES = ("c1_daily", "c1_wk", "c1_pb")


@dataclass(frozen=True)
class ScoreSpec:
    name: str
    required: tuple                                      # concept keys that must be present (c1 = the composite, daily required)
    optional: tuple = ()                                 # concept keys scored when present (c5)
    reversed: tuple = ()                                 # feature keys read as 1 - pct (the reversed stair-step row; the golden flip)
    composite: bool = True                               # "c1" = mean of the three scale percentiles, a missing scale 0.5

    @property
    def concepts(self) -> tuple:
        return self.required + self.optional


def score_specs() -> dict:
    """The reported rows: core (N = 1 / 3 / 5), +grp, the core with concept 5 reversed, the seven concepts alone, the three scales alone,
    the six beside features alone. Keys = the literal `<score>` tokens of the bootstrap keys."""
    specs = {"core": ScoreSpec("core", CORE_REQUIRED, ("c5",)),
             "grp": ScoreSpec("grp", CORE_REQUIRED + ("grp",), ("c5",)),
             "rev_stair": ScoreSpec("rev_stair", CORE_REQUIRED, ("c5",), reversed=("c5",))}
    for k in ("c1", "c2", "c3", "c4", "c5", "c6", "c7"):
        specs[f"alone_{k}"] = ScoreSpec(f"alone_{k}", (k,))
    for k, sc in (("weekly", "c1_wk"), ("daily", "c1_daily"), ("pullbacks", "c1_pb")):
        specs[f"alone_c1_{k}"] = ScoreSpec(f"alone_c1_{k}", (sc,), composite=False)
    for k in ("base_len", "range5_adr", "base_depth", "atr14_slope", "rs_all", "range_sofar_adr"):
        specs[f"alone_{k}"] = ScoreSpec(f"alone_{k}", (k,))
    return specs


SPECS = score_specs()
SPEC_NS = {name: (NS if name == "core" else (N_DECIDES,)) for name in SPECS}


def _isodate(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def iso_week(e: str) -> str:
    y, w, _ = _isodate(e).isocalendar()
    return f"{y}-W{w:02d}"


def iso_monday(e: str) -> dt.date:
    d = _isodate(e)
    return d - dt.timedelta(days=d.weekday())


def week_in_era(e: str, period: str) -> bool:
    """A week belongs to the era of its MONDAY (the edge rule, generic): pre <= 2021-12-31; discovery 2022-01-01..2024-12-31; holdout 2025-."""
    m = iso_monday(e)
    return ERA_FIRST_MONDAY[period] <= m <= ERA_LAST_MONDAY[period]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# readers - every table parsed with float_precision="round_trip" (the re-derivation reads the same way, so an exact-ties rank cannot
# differ by a parser ULP). The daily export is sorted by (ticker, date) before any row is read (the cb702 export is not date-ordered).
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _pd():
    import pandas as pd
    return pd


STR_COLS = {"ticker": str, "D": str, "E": str, "K": str, "split": str, "pole_date": str, "watch_date": str, "entry": str, "arm": str,
            "stop_variant": str, "fill_month": str}


def read_table(path, usecols: "list | None"):
    pd = _pd()
    dtype = STR_COLS if usecols is None else {k: v for k, v in STR_COLS.items() if k in usecols}
    return pd.read_csv(path, sep="\t", usecols=usecols, dtype=dtype, keep_default_na=False, na_values=[""], low_memory=False, float_precision="round_trip")


def read_fills(path, period: str) -> tuple:
    """The population of `period` (the C0 fills: arm pp, entry orh5, K tl) with FEATURE columns only - no outcome column is in `usecols`.
    Returns (frame after the edge rule, n_joined, n_dropped): the fills whose ISO week belongs to another era are dropped (pre: 2022-01-03;
    holdout: 2025-01-03 - those 23 stay as pool-only members, see `prepare`)."""
    f = read_table(path, FILL_COLS)
    f = f[(f["arm"] == POP_ARM) & (f["entry"] == POP_ENTRY) & (f["K"] == POP_K)].copy()
    n_joined = len(f)
    f = f.sort_values(["E", "fill_minute", "ticker"]).reset_index(drop=True)
    in_era = np.array([week_in_era(e, period) for e in f["E"]])
    return f, n_joined, in_era


def read_outcomes(path) -> dict:
    """{(ticker, D, E, K): (status, realized_r, pnl_adr, mature)} of the population rows - opened ONLY after STEP 0 and the checks."""
    t = read_table(path, ["ticker", "D", "E", "K", "entry", "arm", "status", "realized_r", "pnl_adr", "mature"])
    t = t[(t["arm"] == POP_ARM) & (t["entry"] == POP_ENTRY) & (t["K"] == POP_K)]
    return {(a, b, c, d): (s, float(r), float(p), int(m)) for a, b, c, d, s, r, p, m in
            t[["ticker", "D", "E", "K", "status", "realized_r", "pnl_adr", "mature"]].itertuples(index=False)}


def read_cands(path, label_of):
    """The candidates file's tl rows by `CAND_COLS` (never `base_id`, never an E-day column). THE LABEL IS NOT TRUSTED: every row's `split`
    must equal `label_of(D)`, else ValueError."""
    c = read_table(path, CAND_COLS)
    bad = [(t, d, s) for t, d, s in c[["ticker", "D", "split"]].itertuples(index=False) if s != label_of(d)]
    if bad:
        t, d, s = bad[0]
        raise ValueError(f"{path}: row {t} D={d} is labelled split={s!r}, not {label_of(d)!r}: this is not the period's file - refusing to read it")
    return c[c["K"] == POP_K].reset_index(drop=True)


def read_watch(path):
    """{(ticker, watch_date): {close, pole_date, pole_ci, pole_high, range_recent5, range_early5, adr20}} and {ticker: [(watch_date, pole_ci,
    pole_date)]} - the watch table by `usecols`, in chunks."""
    pd = _pd()
    rows, poles = {}, defaultdict(list)
    for df in pd.read_csv(path, sep="\t", usecols=WATCH_COLS, dtype={"ticker": str, "watch_date": str, "pole_date": str}, keep_default_na=False,
                          na_values=[""], chunksize=200_000, float_precision="round_trip"):
        for t, d, cl, pdt, pci, ph, rr5, re5, adr in df[WATCH_COLS].itertuples(index=False):
            rows[(t, d)] = {"close": float(cl), "pole_date": pdt, "pole_ci": int(pci), "pole_high": float(ph), "range_recent5": float(rr5),
                            "range_early5": float(re5), "adr20": float(adr)}
            poles[t].append((d, int(pci), pdt))
    for t in poles:
        poles[t].sort()
    return rows, poles


def read_p5(path) -> dict:
    """{(ticker, D, E, K): range5_adr} from the P5 table's rows K = tl, arm = c3_p33_t20_cut3, stop_variant = lod (one per fill)."""
    t = read_table(path, P5_COLS)
    t = t[(t["K"] == POP_K) & (t["arm"] == P5_ARM) & (t["stop_variant"] == P5_STOP)]
    out = {}
    for a, b, c, d, v in t[["ticker", "D", "E", "K", "range5_adr"]].itertuples(index=False):
        if (a, b, c, d) in out:
            raise ValueError(f"{path}: the P5 filter yields two rows for {(a, b, c, d)}")
        out[(a, b, c, d)] = float(v)
    return out


@dataclass
class Export:
    """The daily export sorted by (ticker, date): flat arrays, per-ticker offsets, the SPY session calendar (date -> index)."""
    tickers: list
    start: np.ndarray
    stop: np.ndarray
    ci: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    cal: list
    cal_ci: dict
    tid: dict

    def rows(self, ticker: str) -> tuple:
        """(ci, h, l, c, v) views of the ticker's rows, date-ascending; empty arrays for an unknown ticker."""
        t = self.tid.get(ticker)
        if t is None:
            z = np.zeros(0)
            return z.astype(np.int64), z, z, z, z
        a, b = int(self.start[t]), int(self.stop[t])
        return self.ci[a:b], self.h[a:b], self.l[a:b], self.c[a:b], self.v[a:b]


def load_export(path) -> Export:
    """`daily_closes_all.csv.gz` (no header: ticker, date, o, h, l, c, v) parsed round-trip and SORTED by (ticker, date); the SPY rows are the
    session calendar (every bar date must be on it)."""
    pd = _pd()
    df = pd.read_csv(path, header=None, names=["ticker", "d", "o", "h", "l", "c", "v"], dtype={"ticker": str}, keep_default_na=False,
                     float_precision="round_trip")
    codes, uniques = pd.factorize(df["ticker"], sort=True)
    days = pd.to_datetime(df["d"]).to_numpy().astype("datetime64[D]").astype(np.int64)
    order = np.lexsort((days, codes))
    codes, days = codes[order], days[order]
    cols = {k: df[k].to_numpy(dtype=float)[order] for k in "hlcv"}
    del df
    tickers = [str(t) for t in uniques]
    tid = {t: k for k, t in enumerate(tickers)}
    bounds = np.concatenate(([0], np.flatnonzero(np.diff(codes)) + 1, [len(codes)]))
    start, stop = bounds[:-1], bounds[1:]
    if "SPY" not in tid:
        raise ValueError(f"{path}: no SPY rows - no session calendar")
    spy = tid["SPY"]
    cal_days = days[start[spy]:stop[spy]]
    ci = np.searchsorted(cal_days, days)
    on_cal = (ci < len(cal_days)) & (cal_days[np.minimum(ci, len(cal_days) - 1)] == days)
    if not on_cal.all():
        raise ValueError(f"{path}: {int((~on_cal).sum())} rows have a date off the SPY calendar")
    cal = [dt.date.fromordinal(int(d) + 719163).isoformat() for d in cal_days]
    return Export(tickers, start, stop, ci.astype(np.int64), cols["h"], cols["l"], cols["c"], cols["v"], cal, {d: k for k, d in enumerate(cal)}, tid)


def read_profile(path) -> np.ndarray:
    """The pinned profile: exactly 391 rows m = 0..390 in order, `m<TAB>profile`; ValueError on any other shape."""
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    if lines[-1] != "" or lines[0] != "m\tprofile" or len(lines) != 393:
        raise ValueError(f"{path}: not the profile's byte-for-byte format (header + 391 rows + a final newline)")
    vals = []
    for m, ln in enumerate(lines[1:-1]):
        a, b = ln.split("\t")
        if int(a) != m:
            raise ValueError(f"{path}: row {m} carries m = {a}")
        vals.append(float(b))
    return np.asarray(vals, dtype=float)


def profile_problems(prof: np.ndarray) -> list:
    p = []
    if len(prof) != 391:
        p.append(f"profile has {len(prof)} rows, not 391")
    if prof[0] != 0.0 or prof[-1] != 1.0:
        p.append(f"PROFILE(0) = {prof[0]!r}, PROFILE(390) = {prof[-1]!r} (must be 0 and 1 exactly)")
    if (np.diff(prof) < 0).any():
        p.append("profile is not non-decreasing")
    for m, want in PROFILE_PINS.items():
        if abs(prof[m] - want) > PROFILE_TOL:
            p.append(f"PROFILE({m}) = {prof[m]:.6f}, pinned {want}")
    return p


def profile_text(prof: np.ndarray) -> str:
    return "m\tprofile\n" + "".join(f"{m}\t{prof[m]:.10f}\n" for m in range(391))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the per-fill features - pure functions over injectable inputs (the ticker's rows, the minute block, the watch rows), so a check can
# perturb one fill's inputs and recompute just that fill
# ═════════════════════════════════════════════════════════════════════════════════════════════
def base_rows(ex: Export, ticker: str, pole_date: str, D: str) -> tuple:
    """(h, l, c) of the ticker's export rows with date in [pole_date, D] - index 0 = P, the last = D; nothing after D is read."""
    ci, h, l, c, _v = ex.rows(ticker)
    pci, dci = ex.cal_ci.get(pole_date), ex.cal_ci.get(D)
    if pci is None or dci is None or len(ci) == 0:
        return np.zeros(0), np.zeros(0), np.zeros(0)
    a, b = np.searchsorted(ci, pci), np.searchsorted(ci, dci, side="right")
    return h[a:b], l[a:b], c[a:b]


def wk_ratio_of(h, l, c, base_len: int):
    """WEEKLY: k = floor(base_len / 5) full 5-session blocks counted back from D (block 1 = D-4..D); envelope = (max h - min l) / its last
    close; m = floor(k / 2); the mean envelope of the LAST m blocks / the FIRST m blocks. None when k < 3 or the early mean is 0."""
    n = len(h)
    k = base_len // 5
    if k < 3 or n < 1 + 5 * k:
        return None
    env = []
    for j in range(1, k + 1):                                # block j = positions n - 5j .. n - 5j + 4
        a = n - 5 * j
        seg_h, seg_l, last_c = h[a:a + 5], l[a:a + 5], c[a + 4]
        if not float(last_c) > 0:                                # a non-positive close (a data defect) leaves the scale missing
            return None
        env.append((float(seg_h.max()) - float(seg_l.min())) / float(last_c))
    m = k // 2
    late, early = float(np.mean(env[:m])), float(np.mean(env[k - m:]))
    return (late / early) if early > 0 else None


def swing_highs(h) -> list:
    """P (index 0) and every j in [2, n - 3] with h[j] > h[j-1], h[j] > h[j-2], h[j] >= h[j+1], h[j] >= h[j+2] (the first of a tie counts)."""
    n = len(h)
    out = [0]
    for j in range(2, n - 2):
        if h[j] > h[j - 1] and h[j] > h[j - 2] and h[j] >= h[j + 1] and h[j] >= h[j + 2]:
            out.append(j)
    return out


def pullbacks_of(h, l) -> list:
    """The COMPLETED pullbacks: for consecutive swing highs s_k < s_k+1, (h[s_k] - min l strictly between) / h[s_k]; the pullback from the
    last swing high to D is incomplete and never counted."""
    s = swing_highs(h)
    out = []
    for a, b in zip(s[:-1], s[1:]):
        out.append((float(h[a]) - float(l[a + 1:b].min())) / float(h[a]))
    return out


def pb_ratio_of(h, l):
    """PULLBACKS: the last completed pullback / the first; None with fewer than 2 completed pullbacks or a first of depth 0."""
    if len(h) < 3:
        return None
    pb = pullbacks_of(h, l)
    if len(pb) < 2 or pb[0] <= 0:
        return None
    return pb[-1] / pb[0]


def vol_dry5_of(ex: Export, ticker: str, D: str):
    """Mean daily volume over the ticker's rows D-4..D / the mean over D-9..D-5 (the last ten rows ending D); None when fewer than ten rows
    end at D or the earlier mean is 0."""
    ci, _h, _l, _c, v = ex.rows(ticker)
    dci = ex.cal_ci.get(D)
    if dci is None or len(ci) == 0:
        return None
    b = np.searchsorted(ci, dci, side="right")
    if b < 10 or ci[b - 1] != dci:
        return None
    recent, earlier = v[b - 5:b], v[b - 10:b - 5]
    em = float(earlier.mean())
    return (float(recent.mean()) / em) if em > 0 else None


def chain_at_d(poles_of_ticker: list, D: str, drift_max: int) -> dict:
    """{pole_ci: base id} over the ticker's watch rows with watch_date <= D: distinct poles sorted by calendar index, cut wherever two
    neighbours are more than `drift_max` sessions apart (the module's `chain_bases` rule, built AT D)."""
    pm = {}
    for d, pci, pdt in poles_of_ticker:
        if d <= D:
            pm[int(pci)] = pdt
    out, base, prev = {}, None, None
    for pci in sorted(pm):
        if prev is None or pci - prev > drift_max:
            base = pm[pci]
        out[pci] = base
        prev = pci
    return out


def stair_n_of(ticker: str, E_ci: int, own_pole_ci: int, cand_rows: list, chain: dict, first_E_ci: int):
    """Concept 5: the count of DISTINCT bases (by the chain at D) among the ticker's `K = tl`, `retrigger = 0` candidate rows with E' in
    [E - 120, E - 1] sessions, excluding the fill's own base. None (unrated on this concept) when the window starts before the candidates
    file's first E. `cand_rows` = [(E'_ci, pole_ci)] of the ticker's first-break rows."""
    lo, hi = E_ci - STAIR_SESSIONS, E_ci - 1
    if lo < first_E_ci:
        return None
    own = chain.get(own_pole_ci)
    bases = set()
    for eci, pci in cand_rows:
        if lo <= eci <= hi:
            b = chain.get(pci)
            if b is None:
                raise ValueError(f"{ticker}: a candidate row's pole (ci {pci}) is not in the chain built at D")
            bases.add(b)
    bases.discard(own)
    return len(bases)


def window_stats(mb, fill_minute: int) -> dict:
    """The breakout-day minute window: the PRESENT minutes 0..fill_minute-1 (never the fill minute). Sum v, max h, min l, the first present
    minute's open, the present / absent counts, whether minute 0 is absent; and the fill minute's own bar (h, v, present) for check 5's
    positive discriminator; the day's total volume (the profile's zero-volume-day rule)."""
    mi = np.asarray(mb.minute)
    w = mi < fill_minute
    n_present = int(w.sum())
    out = {"n_present": n_present, "n_absent": int(fill_minute - n_present), "min0_absent": int(not (mi == 0).any()),
           "day_total_v": float(np.asarray(mb.v).sum())}
    if n_present == 0:
        out.update(sumv=None, maxh=None, minl=None, first_open=None)
    else:
        out.update(sumv=float(np.asarray(mb.v)[w].sum()), maxh=float(np.asarray(mb.h)[w].max()), minl=float(np.asarray(mb.l)[w].min()),
                   first_open=float(np.asarray(mb.o)[w][0]))
    j = np.flatnonzero(mi == fill_minute)
    out["fill_present"] = int(len(j) == 1)
    out["h_fill"] = float(np.asarray(mb.h)[j[0]]) if len(j) else None
    out["v_fill"] = float(np.asarray(mb.v)[j[0]]) if len(j) else None
    return out


def exp_up_adr_of(fill: float, close_d, adr20):
    """Concept 6: (fill - close_D) / (close_D x adr20); None when close_D is absent or <= 0 or adr20 <= 0. A fill below D's close is a valid
    (negative) value."""
    if close_d is None or not close_d > 0 or adr20 is None or not adr20 > 0:
        return None
    return (float(fill) - float(close_d)) / (float(close_d) * float(adr20))


def vol_sofar_of(sumv, adv20, prof_m):
    """Concept 7: sum v over the window / (adv20_vol_D x PROFILE(fill_minute)); None when the window sum is 0 / absent or adv20 <= 0."""
    if sumv is None or sumv <= 0 or adv20 is None or not adv20 > 0 or prof_m is None or not prof_m > 0:
        return None
    return float(sumv) / (float(adv20) * float(prof_m))


def range_sofar_of(maxh, minl, first_open, adr20):
    """The beside row: (max h - min l over the window) / (the first present minute's open x adr20)."""
    if maxh is None or first_open is None or not first_open > 0 or adr20 is None or not adr20 > 0:
        return None
    return (float(maxh) - float(minl)) / (float(first_open) * float(adr20))


def perturb_minutes(mb, fill_minute: int, rng, cb_module):
    """A copy of the block with every minute >= fill_minute (the fill minute itself included) replaced by random values (check 1)."""
    mi = np.asarray(mb.minute)
    o, h, l, c, v = (np.array(x, dtype=float) for x in (mb.o, mb.h, mb.l, mb.c, mb.v))
    w = mi >= fill_minute
    k = int(w.sum())
    if k:
        o[w] = rng.uniform(1, 1000, k)
        h[w] = o[w] * rng.uniform(1.0, 1.5, k)
        l[w] = o[w] * rng.uniform(0.5, 1.0, k)
        c[w] = rng.uniform(l[w], h[w])
        v[w] = rng.integers(0, 10_000_000, k).astype(float)
    return cb_module.minute_bars_from_lists(mi, o, h, l, c, v)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the rating engine: pools, mid-rank percentiles, reference scores, cutoffs, the weekly cap in fill order. Pools and reference scores are
# computed ONCE per E date (every fill on E shares the pool; a fill is never in its own pool) - a vectorised restatement of the per-fill
# rule, the identical numbers.
# ═════════════════════════════════════════════════════════════════════════════════════════════
FLAG_APLUS, FLAG_CAPPED, FLAG_REST, FLAG_UNRATED, FLAG_POOL = "aplus", "capped", "rest", "unrated", ""


def oriented_matrix(cols: dict, keys: tuple = FEATURE_KEYS, features: dict = FEATURES) -> np.ndarray:
    """n x F: every feature oriented so that HIGHER = better (value x direction); NaN = missing."""
    n = len(cols["E_ci"])
    X = np.full((n, len(keys)), np.nan)
    for j, k in enumerate(keys):
        col, d = features[k]
        v = np.asarray([np.nan if x is None else float(x) for x in cols[col]], dtype=float)
        X[:, j] = v * d
    return X


def pool_percentiles(X: np.ndarray, pool: np.ndarray, day: np.ndarray, floor: int = POOL_FLOOR) -> tuple:
    """(own, ref): the fills of the day against the pool's non-missing values per feature (the mid-rank percentile (worse + 0.5 equal) / |S|,
    NaN when the fill's value is missing or |S| < floor), and every pool member against the pool MINUS ITSELF (|S| - 1 >= floor)."""
    own = np.full((len(day), X.shape[1]), np.nan)
    ref = np.full((len(pool), X.shape[1]), np.nan)
    for f in range(X.shape[1]):
        S = X[pool, f]
        S = np.sort(S[~np.isnan(S)])
        nS = len(S)
        if nS >= floor:
            x = X[day, f]
            ok = ~np.isnan(x)
            lo, hi = np.searchsorted(S, x[ok], side="left"), np.searchsorted(S, x[ok], side="right")
            own[ok, f] = (lo + 0.5 * (hi - lo)) / nS
        if nS - 1 >= floor:
            xm = X[pool, f]
            okm = ~np.isnan(xm)
            lo, hi = np.searchsorted(S, xm[okm], side="left"), np.searchsorted(S, xm[okm], side="right")
            ref[okm, f] = (lo + 0.5 * (hi - lo - 1)) / (nS - 1)
    return own, ref


KEY_IDX = {k: j for j, k in enumerate(FEATURE_KEYS)}


def spec_scores(P: np.ndarray, spec: ScoreSpec) -> np.ndarray:
    """The score of every row of a percentile matrix under `spec`: the mean of the present concepts' percentiles; NaN (unrated) when a required
    concept is missing. Concept 1 = the mean of its three scale percentiles with a missing scale 0.5 (the daily scale required)."""
    n = P.shape[0]
    parts, present_required = [], np.ones(n, dtype=bool)

    def pct_of(key):
        v = P[:, KEY_IDX[key]].copy()
        if key in spec.reversed:
            v = 1.0 - v
        return v
    for key in spec.concepts:
        if key == "c1" and spec.composite:
            daily = pct_of("c1_daily")
            wk, pb = pct_of("c1_wk"), pct_of("c1_pb")
            wk = np.where(np.isnan(wk), 0.5, wk)
            pb = np.where(np.isnan(pb), 0.5, pb)
            v = (daily + wk + pb) / 3.0
        else:
            v = pct_of(key)
        if key in spec.required:
            present_required &= ~np.isnan(v)
        parts.append(v)
    M = np.column_stack(parts)
    with np.errstate(invalid="ignore"):
        cnt = (~np.isnan(M)).sum(axis=1)
        s = np.where(cnt > 0, np.nansum(M, axis=1) / np.maximum(cnt, 1), np.nan)
    s[~present_required] = np.nan
    return s


def cutoff_of(ref_scores: np.ndarray, rank: int):
    """The rank-th highest reference score among the RATED pool members; NaN with fewer rated members than `rank`."""
    r = ref_scores[~np.isnan(ref_scores)]
    if len(r) < rank:
        return np.nan
    return float(np.sort(r)[::-1][rank - 1])


def rate_day(X: np.ndarray, pool: np.ndarray, day: np.ndarray, specs: dict, ns: dict, floor: int = POOL_FLOOR, ranks: dict = CUTOFF_RANK) -> dict:
    """One E date: {"own": own pct matrix, "ref": ref pct matrix, "score": {spec: own scores}, "ref_score": {spec: member scores},
    "cutoff": {(spec, N): cutoff}}."""
    own, ref = pool_percentiles(X, pool, day, floor)
    out = {"own": own, "ref": ref, "score": {}, "ref_score": {}, "cutoff": {}}
    for name, spec in specs.items():
        out["score"][name] = spec_scores(own, spec) if len(day) else np.zeros(0)
        rs = spec_scores(ref, spec) if len(pool) else np.zeros(0)
        out["ref_score"][name] = rs
        for N in ns[name]:
            out["cutoff"][(name, N)] = cutoff_of(rs, ranks[N])
    return out


def rate_population(cols: dict, specs: dict = SPECS, ns: dict = SPEC_NS, floor: int = POOL_FLOOR, ranks: dict = CUTOFF_RANK,
                    pool_sessions: int = POOL_SESSIONS, features: dict = FEATURES) -> dict:
    """The whole population in fill order (rows sorted by (E_ci, fill_minute, ticker) - asserted): per row the pool size, the own percentile of
    every feature, the score per spec, the cutoff and the flag per (spec, N). `cols["eligible"]` False = a pool-only row (the sealed read's
    trailing 2022-24 fills, the 23 excluded 2025-01-03 fills): in every pool, never flagged (flag ""). The weekly cap counts A+ per
    (spec, N, ISO week) in fill order."""
    E_in = np.asarray(cols["E_ci"], dtype=np.int64)
    n = len(E_in)
    fm_in = np.asarray(cols["fill_minute"], dtype=np.int64)
    tk_in = np.asarray(cols["ticker"], dtype=object)
    order = np.lexsort((tk_in.astype(str), fm_in, E_in))                      # the engine sorts into fill order itself (check 7: any input order)
    inv = np.empty(n, dtype=np.int64)
    inv[order] = np.arange(n)
    E_ci = E_in[order]
    weeks = np.asarray(cols["week"], dtype=object)[order]
    eligible = np.asarray(cols["eligible"], dtype=bool)[order]
    X = oriented_matrix(cols, FEATURE_KEYS, features)[order]
    res = {"pool_n": np.zeros(n, dtype=np.int64), "pct": np.full((n, len(FEATURE_KEYS)), np.nan),
           "score": {s: np.full(n, np.nan) for s in specs}, "cutoff": {(s, N): np.full(n, np.nan) for s in specs for N in ns[s]},
           "flag": {(s, N): np.full(n, FLAG_POOL, dtype=object) for s in specs for N in ns[s]}}
    counters = {(s, N): Counter() for s in specs for N in ns[s]}
    starts = np.flatnonzero(np.concatenate(([True], E_ci[1:] != E_ci[:-1])))
    ends = np.concatenate((starts[1:], [n]))
    for a, b in zip(starts, ends):
        eci = int(E_ci[a])
        day = np.arange(a, b)
        p0, p1 = np.searchsorted(E_ci, eci - pool_sessions, side="left"), np.searchsorted(E_ci, eci - 1, side="right")
        pool = np.arange(p0, p1)
        r = rate_day(X, pool, day, specs, ns, floor, ranks)
        res["pool_n"][day] = len(pool)
        res["pct"][day] = r["own"]
        for s in specs:
            res["score"][s][day] = r["score"][s]
            for N in ns[s]:
                res["cutoff"][(s, N)][day] = r["cutoff"][(s, N)]
        for k, i in enumerate(day):
            if not eligible[i]:
                continue
            for s in specs:
                sc = r["score"][s][k]
                for N in ns[s]:
                    cut = r["cutoff"][(s, N)]
                    if np.isnan(sc) or np.isnan(cut):
                        flag = FLAG_UNRATED
                    elif sc >= cut:
                        c = counters[(s, N)]
                        if c[weeks[i]] < N:
                            c[weeks[i]] += 1
                            flag = FLAG_APLUS
                        else:
                            flag = FLAG_CAPPED
                    else:
                        flag = FLAG_REST
                    res["flag"][(s, N)][i] = flag
    # back to the input order
    res["pool_n"], res["pct"] = res["pool_n"][inv], res["pct"][inv]
    res["score"] = {s: v[inv] for s, v in res["score"].items()}
    res["cutoff"] = {k: v[inv] for k, v in res["cutoff"].items()}
    res["flag"] = {k: v[inv] for k, v in res["flag"].items()}
    return res


def hindsight_topn(cols: dict, res: dict, spec: ScoreSpec, N: int, floor_members: int = 1) -> np.ndarray:
    """The HINDSIGHT row (beside, labelled so): within each ISO week, over the week's RATED fills (core score present), the fill against the
    week's OTHER rated fills by the same mid-rank formula per feature, its score under `spec`; the top N by score, then rs_best, then the
    earlier fill_minute, then ticker. A fill with no other rated fill in its week has no hindsight score. Returns a bool mask."""
    n = len(cols["E_ci"])
    weeks = np.asarray(cols["week"], dtype=object)
    rated = ~np.isnan(res["score"]["core"]) & np.asarray(cols["eligible"], dtype=bool)
    X = oriented_matrix(cols)
    out = np.zeros(n, dtype=bool)
    for w in sorted(set(weeks[rated])):
        idx = np.flatnonzero(rated & (weeks == w))
        if len(idx) <= floor_members:
            continue
        P = np.full((len(idx), X.shape[1]), np.nan)
        for f in range(X.shape[1]):
            S = X[idx, f]
            for k, i in enumerate(idx):
                others = np.delete(S, k)
                others = others[~np.isnan(others)]
                if np.isnan(S[k]) or len(others) == 0:
                    continue
                P[k, f] = ((others < S[k]).sum() + 0.5 * (others == S[k]).sum()) / len(others)
        sc = spec_scores(P, spec)
        rs = np.asarray([np.nan if x is None else float(x) for x in np.asarray(cols["rs_best"], dtype=object)[idx]], dtype=float)
        fm = np.asarray(cols["fill_minute"], dtype=np.int64)[idx]
        tk = np.asarray(cols["ticker"], dtype=object)[idx]
        order = sorted((k for k in range(len(idx)) if not np.isnan(sc[k])), key=lambda k: (-sc[k], -(rs[k] if not np.isnan(rs[k]) else -1e9), fm[k], tk[k]))
        for k in order[:N]:
            out[idx[k]] = True
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the bars (per era; mature walks; precedence: n first), the paired bars, the consequence table
# ═════════════════════════════════════════════════════════════════════════════════════════════
def boot_key(period: str, N: int, score: str) -> str:
    return f"aplus|{period}|{N}|{score}"


def pair_key(period: str, N: int, score: str) -> str:
    return f"aplus_pair|{period}|{N}|{score}"


def grp_pair_key(period: str) -> str:
    return f"aplus_pair_grp|{period}|3"


def group_stats(r: np.ndarray, pnl: np.ndarray, width: np.ndarray, tickers, months, key: str, boot) -> dict:
    """The mature group's statistics: n, mean R and its month-block interval (`boot` = the runner's block_bootstrap_ci, seed 702, stream `key`),
    win rate, average win / loss, >= 5R / 10R / 20R per 100, total R, ADR P&L, the median stop width in ADR, the >= 10R count at ALL widths
    and the spread (distinct tickers / fill months) over the >= 10R trades whose stop is >= 0.25 ADR20 wide (the spread at all widths beside)."""
    r = np.asarray(r, dtype=float)
    n = len(r)
    out = {"n": n, "key": key}
    if n == 0:
        return out
    wins, losses = r[r > 0], r[r <= 0]
    tail = r >= TAIL_R
    tail_w = tail & (np.asarray(width, dtype=float) >= TAIL_WIDTH_ADR)
    tk, mo = np.asarray(tickers, dtype=object), np.asarray(months, dtype=object)
    out.update(mean_r=float(r.mean()), win_rate=float((r > 0).mean()), avg_win=(float(wins.mean()) if len(wins) else None),
               avg_loss=(float(losses.mean()) if len(losses) else None), ge5_per100=float(100 * (r >= 5).mean()),
               ge10_per100=float(100 * tail.mean()), ge20_per100=float(100 * (r >= 20).mean()), sum_r=float(r.sum()),
               mean_pnl_adr=float(np.asarray(pnl, dtype=float).mean()), median_width_adr=float(np.median(np.asarray(width, dtype=float))),
               count_ge10=int(tail.sum()), tail_tickers=int(len(set(tk[tail_w]))), tail_months=int(len(set(mo[tail_w]))),
               tail_tickers_allwidths=int(len(set(tk[tail]))), tail_months_allwidths=int(len(set(mo[tail]))))
    if n >= 2:
        out["ci_lo"], out["ci_hi"] = boot(r, mo.astype(str), key=key)
    else:
        out["ci_lo"], out["ci_hi"] = (float("nan"), float("nan"))
    return out


def verdict_of(g: dict, c0: dict, c0_n: int, c0_ge10: int) -> tuple:
    """(verdict, why) on the registration's bars, n first. PASS = n >= 30 AND the interval's lower end > 0 AND ADR P&L > 0 AND beats C0 on mean
    R AND on the >= 5R share AND the OUTLIER bar (count_ge10 x c0_n >= 2 x c0_ge10 x n, integers, no rounding) AND those >= 10R trades (stop
    >= 0.25 ADR20) come from >= 3 tickers AND >= 3 fill months. FAIL = n >= 30 AND (upper end < 0 OR not beating C0 on mean R). Else CAN'T
    TELL (the tail the only miss: 'positive, no tail')."""
    n = int(g.get("n") or 0)
    if n < MIN_N:
        return "CAN'T TELL", f"n = {n} < {MIN_N}"
    lo, hi, mean = g.get("ci_lo"), g.get("ci_hi"), g.get("mean_r")
    fails = []
    if hi == hi and hi < 0:
        fails.append("interval upper end < 0")
    if not (mean > c0["mean_r"]):
        fails.append(f"does not beat C0 on mean R ({mean:+.4f} vs {c0['mean_r']:+.4f})")
    if fails:
        return "FAIL", "; ".join(fails)
    unmet = []
    if not (lo == lo and lo > 0):
        unmet.append("interval spans 0")
    if not (g["mean_pnl_adr"] > 0):
        unmet.append("ADR P&L <= 0")
    if not (g["ge5_per100"] > c0["ge5_per100"]):
        unmet.append(f"does not beat C0's >= 5R share ({g['ge5_per100']:.3f} vs {c0['ge5_per100']:.3f} per 100)")
    outlier = g["count_ge10"] * c0_n >= 2 * c0_ge10 * n
    spread = g["tail_tickers"] >= TAIL_TICKERS and g["tail_months"] >= TAIL_MONTHS
    tail_miss = []
    if not outlier:
        tail_miss.append(f">= 10R rate not twice C0's ({g['count_ge10']} x {c0_n} = {g['count_ge10'] * c0_n} < 2 x {c0_ge10} x {n} = {2 * c0_ge10 * n})")
    if not spread:
        tail_miss.append(f">= 10R trades from {g['tail_tickers']} tickers / {g['tail_months']} months (need {TAIL_TICKERS} / {TAIL_MONTHS})")
    if not unmet and not tail_miss:
        return "PASS", "every bar met"
    if not unmet:
        return "CAN'T TELL (positive, no tail)", "; ".join(tail_miss)
    return "CAN'T TELL", "; ".join(unmet + tail_miss)


def paired_delta(r_a, m_a, r_b, m_b, key: str, draws: int = BOOT_DRAWS, seed: int = BOOT_SEED) -> dict:
    """The paired month-block bar: months = the sorted distinct fill months over BOTH groups; each attempt draws `rng.integers(0, m, size=m)`
    (one call), takes both groups' trades inside the drawn months (with multiplicity) and the difference of the two means (a - b); an attempt
    with an empty side is discarded (counted) and the next attempt drawn; the 2.5 / 97.5 percentiles (numpy, linear) of `draws` accepted
    draws. Generator default_rng([seed, crc32(key)])."""
    r_a, r_b = np.asarray(r_a, dtype=float), np.asarray(r_b, dtype=float)
    m_a, m_b = np.asarray(m_a, dtype=object).astype(str), np.asarray(m_b, dtype=object).astype(str)
    months = sorted(set(m_a) | set(m_b))
    m = len(months)
    out = {"n_a": int(len(r_a)), "n_b": int(len(r_b)), "months": m, "key": key, "discarded": 0}
    if len(r_a) == 0 or len(r_b) == 0 or m == 0:
        out.update(mean=float("nan"), lo=float("nan"), hi=float("nan"), reading="can't tell")
        return out
    idx = {mo: k for k, mo in enumerate(months)}
    ia, ib = np.array([idx[x] for x in m_a]), np.array([idx[x] for x in m_b])
    sum_a, cnt_a = np.bincount(ia, weights=r_a, minlength=m), np.bincount(ia, minlength=m).astype(float)
    sum_b, cnt_b = np.bincount(ib, weights=r_b, minlength=m), np.bincount(ib, minlength=m).astype(float)
    rng = np.random.default_rng([seed, zlib.crc32(key.encode())])
    diffs = []
    while len(diffs) < draws:
        d = rng.integers(0, m, size=m)
        na, nb = cnt_a[d].sum(), cnt_b[d].sum()
        if na == 0 or nb == 0:
            out["discarded"] += 1
            continue
        diffs.append(sum_a[d].sum() / na - sum_b[d].sum() / nb)
    diffs = np.asarray(diffs)
    lo, hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
    out.update(mean=float(r_a.mean() - r_b.mean()), lo=lo, hi=hi)
    out["reading"] = "separates" if lo > 0 else ("picks worse" if hi < 0 else "can't tell")
    return out


def grp_reading(d: dict) -> str:
    """+grp's bar: lower end > 0 ADDS; upper end < 0 SUBTRACTS; else CAN'T TELL."""
    lo, hi = d.get("lo"), d.get("hi")
    if lo == lo and lo > 0:
        return "ADDS"
    if hi == hi and hi < 0:
        return "SUBTRACTS"
    return "CAN'T TELL"


def _verdict_class(v: str) -> str:
    return "PASS" if v == "PASS" else ("FAIL" if v == "FAIL" else "CAN'T TELL")


def consequence(pre: dict, disc: dict) -> dict:
    """The consequence table over (2017-21 x 2022-24) with its precedence: (1) the paired bar reading 'picks worse' in EITHER era -> not
    recorded, whatever the cell; (2) the cell; (3) 'separates' promotes nothing beyond the cell except in CAN'T TELL x CAN'T TELL (LEAD only
    when it separates in BOTH). `pre` / `disc` = the verdict JSONs. Returns {"cell", "record_core", "record_grp", "why"}."""
    vp, vd = _verdict_class(pre["verdict"]), _verdict_class(disc["verdict"])
    pp, pd_ = pre["paired"]["reading"], disc["paired"]["reading"]
    if pp == "picks worse" or pd_ == "picks worse":
        cell, why = "NOT RECORDED", f"the paired bar reads 'picks worse' ({'pre' if pp == 'picks worse' else 'discovery'}) - precedence (1)"
    elif vp == "PASS" and vd == "PASS":
        cell, why = "RECORD", "PASS x PASS: the shadow records the deciding rule; then the sealed 2025-26 read ONCE (aplus-confirm)"
    elif "FAIL" in (vp, vd):
        cell, why = "NOT RECORDED", f"a FAIL in one decade beats a PASS in the other ({vp} x {vd})"
    elif "PASS" in (vp, vd):
        cell, why = "LEAD", f"{vp} x {vd}: recorded, no claim"
    elif pp == "separates" and pd_ == "separates":
        cell, why = "LEAD", "CAN'T TELL x CAN'T TELL and the paired bar separates in BOTH eras: recorded, no claim"
    else:
        cell, why = "NOT RECORDED", f"CAN'T TELL x CAN'T TELL and the paired bar does not separate in both ({pp} / {pd_})"
    record_core = cell in ("RECORD", "LEAD")
    record_grp = record_core and pre["grp"]["reading"] == "ADDS" and disc["grp"]["reading"] == "ADDS"
    return {"cell": cell, "record_core": record_core, "record_grp": record_grp, "why": why,
            "next_registration": None if record_core else "the alone table's eligible row (the seven core concepts' alone rows only)"}


def next_registration(pre_rows: dict, disc_rows: dict):
    """Not recorded -> the next registration: among `alone_c1` .. `alone_c7` ONLY, the one with the highest two-era mean of >= 10R per 100 that
    also meets the 3-ticker / 3-month spread in both eras; ties -> the higher two-era mean R, then the lower concept number. None when no
    row meets it. `*_rows` = {score: group stats}."""
    best = None
    for k in range(1, 8):
        name = f"alone_c{k}"
        a, b = pre_rows.get(name) or {}, disc_rows.get(name) or {}
        if not a.get("n") or not b.get("n"):
            continue
        if not (a["tail_tickers"] >= TAIL_TICKERS and a["tail_months"] >= TAIL_MONTHS and b["tail_tickers"] >= TAIL_TICKERS and b["tail_months"] >= TAIL_MONTHS):
            continue
        key = (-(a["ge10_per100"] + b["ge10_per100"]) / 2, -(a["mean_r"] + b["mean_r"]) / 2, k)
        if best is None or key < best[0]:
            best = (key, name)
    return None if best is None else best[1]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the inputs: prepare (the pinned tables, the minute log; no daily bar, no minute row) and the feature build (the export, the minutes)
# ═════════════════════════════════════════════════════════════════════════════════════════════
_EXPORT_SLOT: dict = {}


def export_cached(path) -> Export:
    """`load_export` once per (path, size, mtime): one slot of this module's own (the runner's slot holds a different type)."""
    p = Path(path).resolve()
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns)
    if _EXPORT_SLOT.get("key") == key:
        return _EXPORT_SLOT["value"]
    v = load_export(p)
    _EXPORT_SLOT.clear()
    _EXPORT_SLOT.update(key=key, value=v)
    return v


def clear_export_cache() -> None:
    _EXPORT_SLOT.clear()


def period_paths(ctx: rr.Ctx, period: str) -> dict:
    """Every file the period's read opens, by role (the pre era's tables carry the `_tl_com` names)."""
    d, p = ctx.dirs["cb702"], ctx.dirs["cb702_pre"]
    pdir = p if period == "pre" else d
    cands = "candidates_tl_com.tsv" if period == "pre" else "candidates.tsv"
    watch = "watch_tl_com.tsv.gz" if period == "pre" else "watch.tsv.gz"
    out = {"fills": pdir / "out" / f"trades_{period}_exitpb.tsv.gz", "cands": pdir / "out" / cands, "watch": pdir / "out" / watch,
           "p5": pdir / "out" / f"trades_{period}_p5.tsv.gz", "export": pdir / "daily_closes_all.csv.gz", "profile": p / "out" / PROFILE_NAME,
           "minutes": pdir / "minutes"}
    if period == "holdout":
        out["pool_fills"] = d / "out" / "trades_discovery_exitpb.tsv.gz"
    return out


def aplus_frozen(ctx: rr.Ctx) -> dict:
    """The registration's pin list: the profile, the three exitpb tables (the holdout's sealed - pinned so the confirm read runs on the same
    bytes), the three P5 tables, both candidates files, both watch tables, both exports, both `_done.psv`, both minute trees, the module,
    the re-derivation module (the runner, this scaffold and the spec module are added by the driver)."""
    d, p = ctx.dirs["cb702"], ctx.dirs["cb702_pre"]
    files = {"module": ctx.repo / ctx.rt.MODULE_REL, "rederivation module": Path(__file__).resolve().parent / "aplus_rederive.py",
             "cb702_pre/out/aplus_intraday_profile.tsv": p / "out" / PROFILE_NAME}
    for name in ("trades_discovery_exitpb.tsv.gz", "trades_holdout_exitpb.tsv.gz", "trades_discovery_p5.tsv.gz", "trades_holdout_p5.tsv.gz",
                 "candidates.tsv", "watch.tsv.gz"):
        files[f"cb702/out/{name}"] = d / "out" / name
    for name in ("trades_pre_exitpb.tsv.gz", "trades_pre_p5.tsv.gz", "candidates_tl_com.tsv", "watch_tl_com.tsv.gz"):
        files[f"cb702_pre/out/{name}"] = p / "out" / name
    files["cb702/daily_closes_all.csv.gz"] = d / "daily_closes_all.csv.gz"
    files["cb702_pre/daily_closes_all.csv.gz"] = p / "daily_closes_all.csv.gz"
    files["cb702/minutes/_done.psv"] = d / "minutes" / "_done.psv"
    files["cb702_pre/minutes/_done.psv"] = p / "minutes" / "_done.psv"
    files["cb702/minutes (tree)"] = d / "minutes"
    files["cb702_pre/minutes (tree)"] = p / "minutes"
    return files


def holdout_artefacts(ctx: rr.Ctx) -> list:
    """The sealed era's A+ artefacts (check 10): the table, the verdict files, the report, their `.partial`s - under cb702/out and the small dir."""
    d = ctx.dirs["cb702"] / "out"
    names = ("trades_holdout_aplus.tsv.gz", "aplus_verdict_holdout.json", "aplus_verdict_holdout.txt", "aplus_report_holdout.tsv", "aplus_report_holdout.txt")
    return ctx.rt.existing_outputs(d, names) + ctx.rt.existing_outputs(ctx.here / "out", ("aplus_verdict_holdout.txt", "aplus_report_holdout.txt"))


def _refuse(*lines) -> None:
    for ln in lines:
        print(ln, file=sys.stderr)
    raise SystemExit(2)


def aplus_prepare(ctx: rr.Ctx) -> dict:
    """The period's population (feature columns only) joined to the candidates / watch / P5 rows, the minute log, the files the body opens.
    Opens no daily bar and no minute row. The sealed era's artefacts on disk during `aplus-read` are a broken run (check 10): refused."""
    period = ctx.period
    if period in APLUS_PERIODS:
        broken = holdout_artefacts(ctx)
        if broken:
            _refuse(f"REFUSED: {broken[0]} exists - a sealed-era (holdout) A+ artefact during aplus-read is a BROKEN run (check 10); only "
                    f"aplus-confirm writes it, after PASS x PASS. The operator inspects and removes it by hand")
    paths = period_paths(ctx, period)
    fills, n_joined, in_era = read_fills(paths["fills"], period)
    fills["eligible"] = in_era
    n_dropped = int((~in_era).sum())
    if period == "pre":
        fills = fills[in_era].reset_index(drop=True)                   # the 9 fills of 2022-01-03: dropped (no later fill pools them)
    pool_only = None
    if period == "holdout":
        pool_only, _n, _m = read_fills(paths["pool_fills"], "discovery")
        first_e = fills.loc[fills["eligible"], "E"].min()
        cutoff = (_isodate(first_e) - dt.timedelta(days=45)).isoformat()
        pool_only = pool_only[pool_only["E"] >= cutoff].copy()
        pool_only["eligible"] = False
        pd = _pd()
        fills = pd.concat([pool_only, fills], ignore_index=True).sort_values(["E", "fill_minute", "ticker"]).reset_index(drop=True)
    rows = [{"ticker": t, "E": e, "K": POP_K, "D": d} for t, d, e in fills[["ticker", "D", "E"]].itertuples(index=False)]
    rt = ctx.rt
    label_of = (lambda d: "pre") if period == "pre" else (lambda d: rt.split_label(_isodate(d)))
    cands = read_cands(paths["cands"], label_of)
    watch_rows, watch_poles = read_watch(paths["watch"])
    p5 = read_p5(paths["p5"])
    inp = rt.minute_inputs(rows, ctx.minutes)
    opens = [paths["fills"], paths["watch"], paths["p5"], paths["export"], paths["profile"]]
    if period == "holdout":
        opens.append(paths["pool_fills"])
    eligible_rows = [r for r, ok in zip(rows, fills["eligible"]) if ok]
    return {"rows": eligible_rows, "inp": inp, "path": paths["cands"], "opens": tuple(opens), "fills": fills, "cands": cands,
            "watch_rows": watch_rows, "watch_poles": watch_poles, "p5": p5, "paths": paths, "n_joined": n_joined, "n_dropped": n_dropped,
            "period": period}


def _f(x):
    return None if x is None or x != x else float(x)


def build_features(ctx: rr.Ctx, prep: dict, say, with_perturbation: bool = True) -> dict:
    """Every feature of every row of the frame (eligible and pool-only): the candidates / watch / P5 joins, the export-derived scales, vol_dry5,
    the chain-at-D stair step, the minute windows, concepts 6-7 and the beside row. Returns `cols` (plain lists / arrays, one entry per row,
    in fill order) plus the join problems, the minute-pass tallies and (check 1's minute clause) whether every window survived the
    randomisation of the minutes from the fill minute on."""
    rt, period = ctx.rt, prep["period"]
    fills, cands, wrows, wpoles, p5, paths = prep["fills"], prep["cands"], prep["watch_rows"], prep["watch_poles"], prep["p5"], prep["paths"]
    t0 = time.time()
    ex = export_cached(paths["export"])
    say(f"export: {len(ex.tickers):,} tickers / {len(ex.cal)} sessions {ex.cal[0]}..{ex.cal[-1]} [load: {time.time() - t0:.0f}s]")
    prof = read_profile(paths["profile"])
    n = len(fills)
    cols = {k: list(fills[k]) for k in ("ticker", "D", "E", "K", "fill", "fill_minute", "fill_month", "adr20", "width_adr", "stop", "mature",
                                        "open_mark", "early_close", "phase_qqq_10_20", "eligible")}
    cols["fill_minute"] = [int(x) for x in cols["fill_minute"]]
    cols["E_ci"] = [ex.cal_ci.get(e, -1) for e in cols["E"]]
    cols["D_ci"] = [ex.cal_ci.get(d, -1) for d in cols["D"]]
    cols["week"] = [iso_week(e) for e in cols["E"]]
    cols["weekday"] = [_isodate(e).weekday() for e in cols["E"]]
    problems = []
    # the candidates join (one row per fill)
    ck = {}
    for rec in cands[CAND_COLS].itertuples(index=False):
        key = (rec.ticker, rec.D, rec.E, rec.K)
        if key in ck:
            problems.append(f"candidates: two rows for {key}")
        ck[key] = rec
    first_e_ci = min(ex.cal_ci.get(e, 10**9) for e in cands["E"]) if len(cands) else 10**9
    per_ticker_rows = defaultdict(list)                                 # the ticker's first-break rows: (E'_ci, pole_ci)
    for t, e, pci, rtg in cands[["ticker", "E", "pole_ci", "retrigger"]].itertuples(index=False):
        if int(rtg) == 0 and e in ex.cal_ci:
            per_ticker_rows[t].append((ex.cal_ci[e], int(pci)))
    feat = {k: [None] * n for k in ("tightening_ratio", "rs_best", "rs_all", "prior_move", "adv20_vol_D", "grp_pct", "base_len", "base_depth",
                                    "atr14_slope", "pole_date", "pole_ci", "phase_cand", "close_D", "pole_high", "range_recent5", "range_early5",
                                    "adr20_watch", "watch_pole_ci", "range5_adr", "wk_ratio", "pb_ratio", "base_rows_n", "h_at_pole", "vol_dry5",
                                    "stair_n", "chain_base")}
    chain_cache: dict = {}
    for i in range(n):
        key = (cols["ticker"][i], cols["D"][i], cols["E"][i], cols["K"][i])
        rec = ck.get(key)
        if rec is None:
            problems.append(f"candidates: no row for {key}")
            continue
        for k in ("tightening_ratio", "rs_best", "rs_all", "prior_move", "adv20_vol_D", "grp_pct", "base_len", "base_depth", "atr14_slope"):
            feat[k][i] = _f(getattr(rec, k))
        feat["pole_date"][i], feat["pole_ci"][i] = rec.pole_date, int(rec.pole_ci)
        feat["phase_cand"][i] = int(rec.phase_qqq_10_20) if rec.phase_qqq_10_20 == rec.phase_qqq_10_20 else None
        w = wrows.get((cols["ticker"][i], cols["D"][i]))
        if w is None:
            problems.append(f"watch: no row for {key[:2]}")
        else:
            feat["close_D"][i], feat["pole_high"][i], feat["range_recent5"][i] = w["close"], w["pole_high"], w["range_recent5"]
            feat["range_early5"][i], feat["adr20_watch"][i], feat["watch_pole_ci"][i] = w["range_early5"], w["adr20"], w["pole_ci"]
        r5 = p5.get(key)
        if r5 is None:
            problems.append(f"P5: no row for {key}")
        feat["range5_adr"][i] = r5
        # the base's export rows [pole_date, D]
        h, l, c = base_rows(ex, cols["ticker"][i], rec.pole_date, cols["D"][i])
        feat["base_rows_n"][i] = int(len(h))
        feat["h_at_pole"][i] = float(h[0]) if len(h) else None
        bl = int(rec.base_len) if rec.base_len == rec.base_len else None
        if bl is not None and len(h) == bl + 1:
            feat["wk_ratio"][i] = wk_ratio_of(h, l, c, bl)
            feat["pb_ratio"][i] = pb_ratio_of(h, l)
        feat["vol_dry5"][i] = vol_dry5_of(ex, cols["ticker"][i], cols["D"][i])
        # concept 5: the chain built at D over the ticker's watch rows <= D
        ckey = (cols["ticker"][i], cols["D"][i])
        chain = chain_cache.get(ckey)
        if chain is None:
            chain = chain_cache[ckey] = chain_at_d(wpoles.get(cols["ticker"][i], []), cols["D"][i], rt.POLE_DRIFT_MAX)
        feat["chain_base"][i] = chain.get(int(rec.pole_ci))
        feat["stair_n"][i] = stair_n_of(cols["ticker"][i], cols["E_ci"][i], int(rec.pole_ci), per_ticker_rows.get(cols["ticker"][i], []), chain, first_e_ci)
    cols.update(feat)
    say(f"features at D: {n:,} rows [{time.time() - t0:.0f}s]")
    # the breakout-day minute windows (concept 7, the beside row; check 5's fill-minute bar; check 1's minute clause)
    inp = prep["inp"]
    by_date = defaultdict(list)
    for i in range(n):
        by_date[cols["E"][i]].append(i)
    win = {k: [None] * n for k in ("sumv", "maxh", "minl", "first_open", "n_present", "n_absent", "min0_absent", "fill_present", "h_fill", "v_fill",
                                   "day_total_v", "block_state")}
    rng = np.random.default_rng([SAMPLE_SEED, zlib.crc32(b"aplus_check1_minutes")])
    pert_ok, info_tot = 0, Counter()
    for k, (e, idx) in enumerate(sorted(by_date.items())):
        path = inp["files"].get(e)
        want = {cols["ticker"][i] for i in idx}
        if path is None or str(path) == os.devnull:
            blocks, info = {}, {"bad_lines": 0, "refetched": 0, "truncated": False}
        else:
            blocks, info = rt.read_minute_file(path, want)
        info_tot["bad_lines"] += info["bad_lines"]
        info_tot["refetched"] += info["refetched"]
        info_tot["truncated"] += int(info["truncated"])
        for i in idx:
            rws = blocks.get(cols["ticker"][i])
            mb = rt.minute_bars_from_rows(rws) if rws else None
            if mb is None:
                win["block_state"][i] = "no_block" if not rws else "invalid"
                win["n_present"][i], win["n_absent"][i] = 0, cols["fill_minute"][i]
                continue
            win["block_state"][i] = "ok"
            st = window_stats(mb, cols["fill_minute"][i])
            for kk, v in st.items():
                win[kk][i] = v
            if with_perturbation:
                pst = window_stats(perturb_minutes(mb, cols["fill_minute"][i], rng, rt.cb), cols["fill_minute"][i])
                if all(pst[kk] == st[kk] for kk in ("sumv", "maxh", "minl", "first_open", "n_present", "n_absent", "min0_absent")):
                    pert_ok += 1
        if k % 200 == 0:
            say(f"  minutes: {k + 1}/{len(by_date)} dates [{time.time() - t0:.0f}s]")
    cols.update(win)
    cols["prof_m"] = [float(prof[fm]) for fm in cols["fill_minute"]]
    cols["exp_up_adr"] = [exp_up_adr_of(cols["fill"][i], cols["close_D"][i], cols["adr20"][i]) for i in range(n)]
    cols["vol_sofar_x"] = [vol_sofar_of(cols["sumv"][i], cols["adv20_vol_D"][i], cols["prof_m"][i]) for i in range(n)]
    cols["range_sofar_adr"] = [range_sofar_of(cols["maxh"][i], cols["minl"][i], cols["first_open"][i], cols["adr20"][i]) for i in range(n)]
    say(f"minute windows: {n:,} rows; bad lines {info_tot['bad_lines']}, refetched blocks {info_tot['refetched']}, truncated files "
        f"{info_tot['truncated']} [{time.time() - t0:.0f}s]")
    return {"cols": cols, "problems": problems, "ex": ex, "prof": prof, "pert_ok": pert_ok, "n_blocks_ok": sum(1 for s in win["block_state"] if s == "ok"),
            "first_e_ci": first_e_ci, "per_ticker_rows": per_ticker_rows, "chain_cache": chain_cache, "cands_key": ck}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# STEP 0 - the census (features only), its equality targets, the rating counts
# ═════════════════════════════════════════════════════════════════════════════════════════════
def pool_counts(cols: dict, keys: tuple = ("wk_ratio", "pb_ratio"), pool_sessions: int = POOL_SESSIONS) -> dict:
    """Per row: the pool size and, per key, the pool's count of non-missing values (the per-scale floor) - an independent count by date."""
    E_ci = np.asarray(cols["E_ci"], dtype=np.int64)
    n = len(E_ci)
    out = {"pool_n": np.zeros(n, dtype=np.int64)}
    present = {k: np.asarray([x is not None for x in cols[k]], dtype=bool) for k in keys}
    cum = {k: np.concatenate(([0], np.cumsum(present[k]))) for k in keys}
    for k in keys:
        out[f"pool_{k}"] = np.zeros(n, dtype=np.int64)
    for i in range(n):
        p0, p1 = np.searchsorted(E_ci, E_ci[i] - pool_sessions, side="left"), np.searchsorted(E_ci, E_ci[i] - 1, side="right")
        out["pool_n"][i] = p1 - p0
        for k in keys:
            out[f"pool_{k}"][i] = cum[k][p1] - cum[k][p0]
    return out


def _spearman(a, b) -> float:
    """Spearman = Pearson on average ranks (the doc's definition; pandas' `corr(method="spearman")` computes the same through scipy)."""
    pd = _pd()
    s = pd.DataFrame({"a": np.asarray(a, dtype=float), "b": np.asarray(b, dtype=float)}).dropna()
    if len(s) < 3:
        return float("nan")
    return float(s["a"].rank(method="average").corr(s["b"].rank(method="average")))


def census(cols: dict, prep: dict, early_close: frozenset) -> dict:
    """The STEP 0 census over the ELIGIBLE rows (the rated population): the counts the doc pins as equality targets, in its units."""
    el = np.asarray(cols["eligible"], dtype=bool)
    idx = np.flatnonzero(el)
    pc = pool_counts(cols)
    fm = np.asarray(cols["fill_minute"], dtype=np.int64)[idx]
    wk = np.asarray([cols["wk_ratio"][i] is not None for i in idx])
    pb = np.asarray([cols["pb_ratio"][i] is not None for i in idx])
    wk_floor = wk & (pc["pool_wk_ratio"][idx] < POOL_FLOOR)
    pb_floor = pb & (pc["pool_pb_ratio"][idx] < POOL_FLOOR)
    exp = np.asarray([np.nan if cols["exp_up_adr"][i] is None else cols["exp_up_adr"][i] for i in idx], dtype=float)
    width = np.asarray(cols["width_adr"], dtype=float)[idx]
    early = np.asarray([cols["E"][i] in early_close for i in idx])
    zero = sorted((cols["ticker"][i], cols["E"][i]) for i in idx if cols["block_state"][i] == "ok" and cols["n_present"][i] > 0 and cols["sumv"][i] == 0)
    c = {"joined": int(prep["n_joined"]), "fills": int(len(idx)), "open": int(sum(int(cols["open_mark"][i]) for i in idx)),
         "weeks": len({cols["week"][i] for i in idx}), "dropped": int(prep["n_dropped"]),
         "c5_unrated": int(sum(cols["stair_n"][i] is None for i in idx)), "thin": int((pc["pool_n"][idx] < POOL_FLOOR).sum()),
         "wk_present": int(wk.sum()), "wk_floor_strip": int(wk_floor.sum()), "pb_present": int(pb.sum()), "pb_floor_strip": int(pb_floor.sum()),
         "both": int((wk & pb).sum()), "neither": int((~wk & ~pb).sum()),
         "fm_bins": tuple(int(((fm >= a) & (fm < b)).sum()) for a, b in FM_BINS), "fm_min": int(fm.min()) if len(fm) else None,
         "fm_max": int(fm.max()) if len(fm) else None, "fm_at5": int((fm == 5).sum()), "fm_ge210": int((fm >= 210).sum()),
         "fm_median": float(np.percentile(fm, 50)) if len(fm) else None, "fm_q1": float(np.percentile(fm, 25)) if len(fm) else None,
         "fm_q3": float(np.percentile(fm, 75)) if len(fm) else None, "fm_p90": float(np.percentile(fm, 90)) if len(fm) else None,
         "absent_any": int(sum(1 for i in idx if (cols["n_absent"][i] or 0) >= 1)), "min0_absent": int(sum(1 for i in idx if cols["min0_absent"][i])),
         "zero_vol": tuple(zero), "early": int(early.sum()), "early_ge210": int((early & (fm >= 210)).sum()),
         "exp_missing": int(np.isnan(exp).sum()), "exp_le0": int((exp <= 0).sum()),
         "exp_median": float(np.nanquantile(exp, 0.5)) if len(exp) and not np.isnan(exp).all() else None,
         "exp_q1": float(np.nanquantile(exp, 0.25)) if len(exp) and not np.isnan(exp).all() else None,
         "exp_q3": float(np.nanquantile(exp, 0.75)) if len(exp) and not np.isnan(exp).all() else None,
         "rho_width": _spearman(exp, width) if len(exp) > 2 else None, "rho_fm": _spearman(exp, fm) if len(exp) > 2 else None,
         "grp_present": int(sum(cols["grp_pct"][i] is not None for i in idx)), "pool_min": int(pc["pool_n"][idx].min()) if len(idx) else None,
         "pool_median": float(np.median(pc["pool_n"][idx])) if len(idx) else None, "no_block": int(sum(cols["block_state"][i] != "ok" for i in idx)),
         "pool_only": int((~el).sum())}
    return c


def census_problems(c: dict, expected: dict) -> list:
    """The equality targets: every key of `expected` must equal the census (counts exactly; the medians / quartiles to 1e-4, the rank
    correlations to 1e-3; the zero-volume windows by name)."""
    p = []
    for k, want in expected.items():
        got = c.get(k)
        if k in ("exp_median", "exp_q1", "exp_q3"):
            ok = got is not None and abs(got - want) <= EXP_TOL
        elif k in ("rho_width", "rho_fm"):
            ok = got is not None and abs(got - want) <= RHO_TOL
        elif k in ("fm_median", "fm_q1", "fm_q3", "fm_p90"):
            ok = got is not None and abs(got - want) <= 1e-9
        elif k == "zero_vol":
            ok = tuple(sorted(got)) == tuple(sorted(want))
        else:
            ok = got == want
        if not ok:
            p.append(f"STEP 0: {k} = {got!r}, registered {want!r}")
    return p


def census_text(c: dict, period: str, expected: dict) -> list:
    bins = " ".join(f"{a}-{b - 1}:{v}" for (a, b), v in zip(FM_BINS, c["fm_bins"]))
    lines = [f"STEP 0 ({period}, features only, no outcome column opened): joined {c['joined']:,} -> fills {c['fills']:,} after the edge rule "
             f"({c['dropped']} dropped / excluded; pool-only rows {c['pool_only']}); open marks {c['open']}; ISO weeks {c['weeks']}; unrated on "
             f"concept 5: {c['c5_unrated']:,}; thin pool (< {POOL_FLOOR}): {c['thin']}; pool size min {c['pool_min']} / median {c['pool_median']}",
             f"  concept 1 scales: weekly present {c['wk_present']:,} (floor strips {c['wk_floor_strip']}); pullbacks present {c['pb_present']:,} "
             f"(floor strips {c['pb_floor_strip']}); both {c['both']:,}; neither {c['neither']:,}",
             f"  fill_minute: {bins}; min {c['fm_min']} max {c['fm_max']}; at 5: {c['fm_at5']:,}; >= 210: {c['fm_ge210']:,}; median {c['fm_median']} "
             f"quartiles {c['fm_q1']}-{c['fm_q3']} 90th {c['fm_p90']}",
             f"  windows: an absent minute inside {c['absent_any']:,}; minute 0 absent {c['min0_absent']}; zero-volume windows {len(c['zero_vol'])} "
             f"{list(c['zero_vol'])}; no block {c['no_block']}; early-close fills {c['early']} of which >= 210: {c['early_ge210']}",
             f"  concept 6: exp_up_adr missing {c['exp_missing']}; <= 0: {c['exp_le0']:,}; median {_r(c['exp_median'], 4)} quartiles "
             f"{_r(c['exp_q1'], 4)}-{_r(c['exp_q3'], 4)}; Spearman with width_adr {_r(c['rho_width'], 3)}, with fill_minute {_r(c['rho_fm'], 3)}",
             f"  grp_pct present {c['grp_present']:,}"]
    missing = [k for k in c if k in expected and k not in ("fm_bins",)]
    lines.append(f"  equality targets checked: {len(expected)} ({', '.join(sorted(expected))})" if expected else "  equality targets: none registered for this period (taken at the confirm read)")
    return lines


def _r(x, nd):
    return "" if x is None or x != x else f"{x:.{nd}f}"


def rating_counts(cols: dict, res: dict, period: str) -> dict:
    """The STEP 0 rating counts (before any outcome): rated / unrated / capped / A+ per N on the core, the share of weeks with fewer than N
    A+ after the burn-in, the pool sizes."""
    el = np.asarray(cols["eligible"], dtype=bool)
    out = {}
    weeks = np.asarray(cols["week"], dtype=object)
    all_weeks = sorted(set(weeks[el]))
    for N in NS:
        fl = res["flag"][("core", N)]
        out[N] = {"aplus": int(((fl == FLAG_APLUS) & el).sum()), "capped": int(((fl == FLAG_CAPPED) & el).sum()), "rest": int(((fl == FLAG_REST) & el).sum()),
                  "unrated": int(((fl == FLAG_UNRATED) & el).sum())}
        after = all_weeks[BURN_IN_WEEKS:]
        cnt = Counter(weeks[(fl == FLAG_APLUS) & el])
        out[N]["weeks_under_n_share"] = (sum(1 for w in after if cnt[w] < N) / len(after)) if after else None
        lo, hi = EXPECT_APLUS_N.get(period, (None, None))
        out[N]["expected_range"] = (lo, hi)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the WOULD-FAIL-IF checks (features and the flag, never an outcome number): 1, 2, 3, 5, 6, 7, 9, 12. Each returns (problems, lines).
# ═════════════════════════════════════════════════════════════════════════════════════════════
class PerturbedExport:
    """`Export` seen through a per-fill perturbation: every ticker's h, l, c, v on every row dated AFTER `D` randomised (check 1's export
    clause, check 12's incomplete-pullback clause)."""

    def __init__(self, ex: Export, D: str, seed: int):
        self.ex, self.d_ci, self.cal_ci, self.cal = ex, ex.cal_ci[D], ex.cal_ci, ex.cal
        self.rng = np.random.default_rng([seed, self.d_ci])

    def rows(self, ticker: str) -> tuple:
        ci, h, l, c, v = self.ex.rows(ticker)
        after = ci > self.d_ci
        k = int(after.sum())
        if not k:
            return ci, h, l, c, v
        h, l, c, v = h.copy(), l.copy(), c.copy(), v.copy()
        base = self.rng.uniform(1, 1000, k)
        h[after], l[after] = base * self.rng.uniform(1.0, 1.5, k), base * self.rng.uniform(0.5, 1.0, k)
        c[after] = self.rng.uniform(l[after], h[after])
        v[after] = self.rng.integers(0, 10_000_000, k).astype(float)
        return ci, h, l, c, v


def export_features(ex, ticker: str, pole_date: str, D: str, base_len) -> tuple:
    """(wk_ratio, pb_ratio, vol_dry5, n_rows, h_at_pole) from an export view - the three export-derived features of one fill."""
    h, l, c = base_rows(ex, ticker, pole_date, D)
    wk = pb = None
    if base_len is not None and len(h) == int(base_len) + 1:
        wk, pb = wk_ratio_of(h, l, c, int(base_len)), pb_ratio_of(h, l)
    return wk, pb, vol_dry5_of(ex, ticker, D), int(len(h)), (float(h[0]) if len(h) else None)


def aplus_set(cols: dict, res: dict, spec: str = "core", N: int = N_DECIDES) -> set:
    fl = res["flag"][(spec, N)]
    return {(cols["ticker"][i], cols["E"][i]) for i in np.flatnonzero(fl == FLAG_APLUS)}


def sample_rows(idx: np.ndarray, k: int, tag: str) -> np.ndarray:
    rng = np.random.default_rng([SAMPLE_SEED, zlib.crc32(tag.encode())])
    idx = np.asarray(idx)
    if len(idx) <= k:
        return idx
    return np.sort(rng.choice(idx, size=k, replace=False))


def _eq(a, b, tol=1e-9) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def check3_join(cols: dict, feats: dict, prep: dict, ctx: rr.Ctx, profile_sha: str) -> tuple:
    """Data check 3: the joins, the six D-night inputs, concept 6's inputs, the base rows, the calendar, uniqueness, the minute blocks, the
    profile file."""
    n = len(cols["E"])
    el = np.asarray(cols["eligible"], dtype=bool)
    ex = feats["ex"]
    p = list(feats["problems"])
    for k in ("rs_best", "prior_move", "base_len", "tightening_ratio", "adv20_vol_D", "range5_adr"):
        miss = sum(1 for i in range(n) if cols[k][i] is None)
        if miss:
            p.append(f"check 3: {k} missing for {miss} rows")
    bad_adv = sum(1 for i in range(n) if cols["adv20_vol_D"][i] is not None and not cols["adv20_vol_D"][i] > 0)
    if bad_adv:
        p.append(f"check 3: adv20_vol_D <= 0 for {bad_adv} rows")
    close_miss = sum(1 for i in range(n) if cols["close_D"][i] is None or not cols["close_D"][i] > 0)
    if close_miss:
        p.append(f"check 3: the watch row's close at D absent or <= 0 for {close_miss} rows")
    diff_close = 0
    for i in range(n):
        ci, _h, _l, c, _v = ex.rows(cols["ticker"][i])
        j = np.searchsorted(ci, cols["D_ci"][i])
        cx = float(c[j]) if j < len(ci) and ci[j] == cols["D_ci"][i] else None
        if cols["close_D"][i] is None or cx is None or abs(cx - cols["close_D"][i]) > 1e-9:
            diff_close += 1
    if diff_close:
        p.append(f"check 3: the watch close at D differs from the sorted export's c at D for {diff_close} rows")
    if any(not (cols["adr20"][i] > 0) for i in range(n)):
        p.append("check 3: adr20 <= 0 on a row")
    if any(cols["fill"][i] is None or cols["fill"][i] != cols["fill"][i] for i in range(n)):
        p.append("check 3: a fill is absent")
    rows_bad = sum(1 for i in range(n) if cols["base_len"][i] is None or cols["base_rows_n"][i] != int(cols["base_len"][i]) + 1)
    if rows_bad:
        p.append(f"check 3: the base's export rows != base_len + 1 for {rows_bad} rows")
    ph_bad = sum(1 for i in range(n) if not _eq(cols["h_at_pole"][i], cols["pole_high"][i]))
    if ph_bad:
        p.append(f"check 3: h at pole_date != the watch row's pole_high for {ph_bad} rows")
    if any(cols["E_ci"][i] < 0 or cols["D_ci"][i] < 0 for i in range(n)):
        p.append("check 3: an E or D is not on the SPY calendar")
    keys = Counter((cols["ticker"][i], cols["E"][i]) for i in range(n))
    if any(v > 1 for v in keys.values()):
        p.append("check 3: (ticker, E) not unique")
    blk = sum(1 for i in range(n) if cols["block_state"][i] != "ok" or cols["n_present"][i] < 1)
    if blk:
        p.append(f"check 3: {blk} population pairs have no block / no present minute before the fill minute")
    if any(cols["fill_minute"][i] < 5 for i in range(n)):
        p.append("check 3: a fill_minute < 5")
    pp = profile_problems(feats["prof"])
    p += [f"check 3: profile: {x}" for x in pp]
    got = rr.sha256_file(prep["paths"]["profile"])
    if got != profile_sha:
        p.append(f"check 3: the profile file's sha256 {got[:12]}... is not the EXPECTED {profile_sha[:12]}...")
    vd = sum(1 for i in range(n) if cols["vol_dry5"][i] is None)
    wkm = sum(1 for i in range(n) if cols["wk_ratio"][i] is None)
    pbm = sum(1 for i in range(n) if cols["pb_ratio"][i] is None)
    lines = [f"check 3 (join): {n:,} rows ({int(el.sum()):,} eligible); the six D-night inputs complete; close at D = the export's c at D for every row; "
             f"base rows = base_len + 1 and h at P = pole_high for every row; blocks ok {feats['n_blocks_ok']:,}; profile {got[:12]}... = EXPECTED; "
             f"vol_dry5 missing {vd}, wk_ratio missing {wkm:,}, pb_ratio missing {pbm:,} (by their stated rules)"]
    return p, lines


def check1_lookahead(cols: dict, res: dict, feats: dict, prep: dict, ctx: rr.Ctx) -> tuple:
    """WOULD-FAIL-IF 1: (a) every window survived the randomisation of its own minutes from the fill minute on (computed in the minute pass);
    (b) the E-day columns of the candidates (open_E .. breakout_vol_x) joined back and SHUFFLED leave every score, cutoff and flag identical
    (the outcome columns are not in the frame at all before the checks); (c) PER FILL (50 sampled + every A+ fill), with every ticker's
    h / l / c / v after THAT fill's D randomised, the fill's score, cutoff and flag are identical."""
    p, lines = [], []
    if feats["pert_ok"] != feats["n_blocks_ok"]:
        p.append(f"check 1: {feats['n_blocks_ok'] - feats['pert_ok']} windows changed when the minutes from the fill minute on were randomised")
    lines.append(f"check 1 (a): {feats['pert_ok']:,} of {feats['n_blocks_ok']:,} windows identical under the per-fill minute randomisation")
    # (b) the look-ahead columns shuffled
    la = read_table(prep["paths"]["cands"], ["ticker", "D", "E", "K"] + CAND_LOOKAHEAD_COLS)
    la = la[la["K"] == POP_K]
    lam = {(a, b, c, d): tuple(rest) for a, b, c, d, *rest in la[["ticker", "D", "E", "K"] + CAND_LOOKAHEAD_COLS].itertuples(index=False)}
    rng = np.random.default_rng([SAMPLE_SEED, zlib.crc32(b"aplus_check1_columns")])
    n = len(cols["E"])
    perm = rng.permutation(n)
    cols2 = dict(cols)
    vals = [lam.get((cols["ticker"][i], cols["D"][i], cols["E"][i], cols["K"][i]), (None,) * len(CAND_LOOKAHEAD_COLS)) for i in range(n)]
    for j, k in enumerate(CAND_LOOKAHEAD_COLS):
        cols2[k] = [vals[perm[i]][j] for i in range(n)]
    res2 = rate_population(cols2)
    diff = _res_diff(res, res2)
    if diff:
        p.append(f"check 1 (b): {diff} under the E-day column shuffle")
    lines.append(f"check 1 (b): the E-day columns {CAND_LOOKAHEAD_COLS} joined and shuffled - every score, cutoff and flag identical")
    # (c) per-fill export randomisation after D
    el = np.flatnonzero(np.asarray(cols["eligible"], dtype=bool))
    ap = np.flatnonzero(res["flag"][("core", N_DECIDES)] == FLAG_APLUS)
    sample = np.unique(np.concatenate((sample_rows(el, CHECK1_SAMPLE, "check1"), ap)))
    X = oriented_matrix(cols)
    E_ci = np.asarray(cols["E_ci"], dtype=np.int64)
    bad = 0
    for i in sample:
        pex = PerturbedExport(feats["ex"], cols["D"][i], SAMPLE_SEED)
        p0, p1 = np.searchsorted(E_ci, E_ci[i] - POOL_SESSIONS, side="left"), np.searchsorted(E_ci, E_ci[i] - 1, side="right")
        pool = np.arange(p0, p1)
        Xp = X.copy()
        for j in np.concatenate((pool, [i])):
            wk, pb, vd, _n, _h = export_features(pex, cols["ticker"][j], cols["pole_date"][j], cols["D"][j], cols["base_len"][j])
            Xp[j, KEY_IDX["c1_wk"]] = np.nan if wk is None else -wk
            Xp[j, KEY_IDX["c1_pb"]] = np.nan if pb is None else -pb
            Xp[j, KEY_IDX["c2"]] = np.nan if vd is None else -vd
        r = rate_day(Xp, pool, np.array([i]), SPECS, SPEC_NS)
        for s in SPECS:
            if not _same(r["score"][s][0], res["score"][s][i]):
                bad += 1
                break
            if any(not _same(r["cutoff"][(s, N)], res["cutoff"][(s, N)][i]) for N in SPEC_NS[s]):
                bad += 1
                break
    if bad:
        p.append(f"check 1 (c): {bad} of {len(sample)} fills changed score or cutoff when the export after their D was randomised")
    lines.append(f"check 1 (c): {len(sample)} fills (50 sampled + {len(ap)} A+) - score, cutoff and flag identical with every row after the fill's D randomised")
    return p, lines


def _same(a, b) -> bool:
    a, b = float(a), float(b)
    return (a != a and b != b) or a == b


def _res_diff(r1: dict, r2: dict) -> str:
    for s in r1["score"]:
        a, b = r1["score"][s], r2["score"][s]
        if not np.array_equal(np.isnan(a), np.isnan(b)) or not np.array_equal(np.nan_to_num(a), np.nan_to_num(b)):
            return f"scores differ on {s}"
    for k in r1["cutoff"]:
        a, b = r1["cutoff"][k], r2["cutoff"][k]
        if not np.array_equal(np.isnan(a), np.isnan(b)) or not np.array_equal(np.nan_to_num(a), np.nan_to_num(b)):
            return f"cutoffs differ on {k}"
        if not np.array_equal(r1["flag"][k], r2["flag"][k]):
            return f"flags differ on {k}"
    return ""


def check2_later_fills(cols: dict, res: dict) -> tuple:
    """WOULD-FAIL-IF 2: for 50 A+ fills (seed 702) remove every fill after it in (E, fill_minute, ticker) order - its score, cutoff and flag
    are unchanged."""
    ap = np.flatnonzero(res["flag"][("core", N_DECIDES)] == FLAG_APLUS)
    sample = sample_rows(ap, CHECK2_SAMPLE, "check2")
    n = len(cols["E"])
    order = np.lexsort((np.asarray(cols["ticker"], dtype=str), np.asarray(cols["fill_minute"], dtype=np.int64), np.asarray(cols["E_ci"], dtype=np.int64)))
    pos = np.empty(n, dtype=np.int64)
    pos[order] = np.arange(n)
    bad = 0
    for i in sample:
        keep = np.flatnonzero(pos <= pos[i])                                 # every fill at or before it in (E, fill_minute, ticker) order
        j = int(np.flatnonzero(keep == i)[0])
        trunc = {k: [v[q] for q in keep] for k, v in cols.items()}
        r = rate_population(trunc)
        for s in SPECS:
            if not _same(r["score"][s][j], res["score"][s][i]) or any(not _same(r["cutoff"][(s, N)][j], res["cutoff"][(s, N)][i]) or
                                                                    r["flag"][(s, N)][j] != res["flag"][(s, N)][i] for N in SPEC_NS[s]):
                bad += 1
                break
    p = [f"check 2: {bad} of {len(sample)} A+ fills changed when the later fills were removed"] if bad else []
    return p, [f"check 2 (later-fill removal): {len(sample)} A+ fills - score, cutoff and flag unchanged"]


def check5_breakout_inputs(cols: dict, res: dict, feats: dict, prep: dict, ctx: rr.Ctx) -> tuple:
    """WOULD-FAIL-IF 5: for every A+ fill, concept 6 recomputed from the fills table's `fill` / `adr20` and the watch close at D equals the stored
    value; the stored fill equals the table's; recomputed with close_E (the candidates' E-day close) in place of close_D it DIFFERS for every
    A+ fill whose close_E != close_D (count printed). Concept 7 and the beside row recomputed from the minute files equal the stored values;
    prof_m = the pinned file's row; fill_minute = the table's; the window EXTENDED by the fill minute changes the range for EVERY A+ fill and
    the volume sum for every A+ fill whose fill minute carries volume (an A+ fill changing neither fails)."""
    rt = ctx.rt
    ap = np.flatnonzero(res["flag"][("core", N_DECIDES)] == FLAG_APLUS)
    p, lines = [], []
    ft = read_table(prep["paths"]["fills"], ["ticker", "D", "E", "K", "entry", "arm", "fill", "fill_minute", "adr20"])
    ft = ft[(ft["arm"] == POP_ARM) & (ft["entry"] == POP_ENTRY) & (ft["K"] == POP_K)]
    fills_of = {(a, b, c, d): (float(f), int(m), float(adr)) for a, b, c, d, f, m, adr in ft[["ticker", "D", "E", "K", "fill", "fill_minute", "adr20"]].itertuples(index=False)}
    ce = read_table(prep["paths"]["cands"], ["ticker", "D", "E", "K", "close_E"])
    close_e = {(a, b, c, d): _f(v) for a, b, c, d, v in ce[ce["K"] == POP_K].itertuples(index=False)}
    prof = feats["prof"]
    n_c6_bad = n_c6_disc = n_c6_differ = 0
    for i in ap:
        key = (cols["ticker"][i], cols["D"][i], cols["E"][i], cols["K"][i])
        fill, fm, adr = fills_of[key]
        if fill != cols["fill"][i] or fm != cols["fill_minute"][i]:
            n_c6_bad += 1
            continue
        if not _eq(exp_up_adr_of(fill, cols["close_D"][i], adr), cols["exp_up_adr"][i]):
            n_c6_bad += 1
        if cols["prof_m"][i] != float(prof[fm]):
            n_c6_bad += 1
        ce_ = close_e.get(key)
        if ce_ is not None and cols["close_D"][i] is not None and ce_ != cols["close_D"][i]:
            n_c6_differ += 1
            alt = exp_up_adr_of(fill, ce_, adr)
            if _eq(alt, cols["exp_up_adr"][i]):
                n_c6_disc += 1
    if n_c6_bad:
        p.append(f"check 5: concept 6 / prof_m / fill / fill_minute recomputed differ from the stored values for {n_c6_bad} A+ fills")
    if n_c6_disc:
        p.append(f"check 5: concept 6 with close_E in place of close_D did NOT differ for {n_c6_disc} A+ fills whose close_E != close_D")
    lines.append(f"check 5 (concept 6): {len(ap)} A+ fills recomputed from the table's fill / adr20 and the watch close at D - equal; with close_E in "
                 f"place of close_D the number differs for every one of the {n_c6_differ} A+ fills whose close_E != close_D")
    # concept 7 and the beside row from the minute files, and the extended window
    by_date = defaultdict(list)
    for i in ap:
        by_date[cols["E"][i]].append(i)
    n7_bad = n_range_same = n_vol_same = n_vol_zero = n_neither = 0
    for e, idx in sorted(by_date.items()):
        path = prep["inp"]["files"].get(e)
        blocks, _info = rt.read_minute_file(path, {cols["ticker"][i] for i in idx}) if path is not None and str(path) != os.devnull else ({}, None)
        for i in idx:
            mb = rt.minute_bars_from_rows(blocks.get(cols["ticker"][i]) or [])
            fm = cols["fill_minute"][i]
            if mb is None:
                n7_bad += 1
                continue
            mi, h, l, v = np.asarray(mb.minute), np.asarray(mb.h), np.asarray(mb.l), np.asarray(mb.v)
            w, wx = mi < fm, mi <= fm
            sumv, maxh, minl = float(v[w].sum()), float(h[w].max()), float(l[w].min())
            first_open = float(np.asarray(mb.o)[w][0])
            vs = sumv / (cols["adv20_vol_D"][i] * float(prof[fm])) if sumv > 0 else None
            rs = (maxh - minl) / (first_open * cols["adr20"][i])
            if not _eq(vs, cols["vol_sofar_x"][i]) or not _eq(rs, cols["range_sofar_adr"][i]) or not _eq(sumv, cols["sumv"][i]):
                n7_bad += 1
            range_same = float(h[wx].max()) == maxh and float(l[wx].min()) == minl
            vol_same = float(v[wx].sum()) == sumv
            fill_v = float(v[mi == fm].sum())
            if fill_v == 0:
                n_vol_zero += 1
            n_range_same += int(range_same)
            n_vol_same += int(vol_same and fill_v > 0)
            n_neither += int(range_same and vol_same)
    if n7_bad:
        p.append(f"check 5: concept 7 / the beside row recomputed from the minute files differ for {n7_bad} A+ fills")
    if n_range_same:
        p.append(f"check 5: the window extended by the fill minute left the range unchanged for {n_range_same} A+ fills")
    if n_vol_same:
        p.append(f"check 5: the window extended by the fill minute left the volume sum unchanged for {n_vol_same} A+ fills whose fill minute carries volume")
    if n_neither:
        p.append(f"check 5: {n_neither} A+ fills change NEITHER number under the extended window")
    lines.append(f"check 5 (concept 7, the beside row): {len(ap)} A+ fills recomputed from the minute files over 0..fill_minute-1 - equal; the window "
                 f"extended by the fill minute changes the range for every A+ fill and the volume sum for every A+ fill with volume on the fill "
                 f"minute ({n_vol_zero} fill minutes carry no volume)")
    return p, lines


def check4_counts(cols: dict, res: dict) -> tuple:
    """WOULD-FAIL-IF 4: per spec x N, A+ unique by (ticker, E); per ISO week A+ = min(N, the rated fills at or above the cutoff that week);
    never more than N."""
    el = np.asarray(cols["eligible"], dtype=bool)
    weeks = np.asarray(cols["week"], dtype=object)
    p, n_weeks = [], 0
    for s in SPECS:
        for N in SPEC_NS[s]:
            fl = res["flag"][(s, N)]
            ap = (fl == FLAG_APLUS) & el
            keys = [(cols["ticker"][i], cols["E"][i]) for i in np.flatnonzero(ap)]
            if len(keys) != len(set(keys)):
                p.append(f"check 4: A+ not unique by (ticker, E) on ({s}, N = {N})")
            above = ((fl == FLAG_APLUS) | (fl == FLAG_CAPPED)) & el
            for w in set(weeks[above]):
                n_ap, n_above = int((ap & (weeks == w)).sum()), int((above & (weeks == w)).sum())
                n_weeks += 1
                if n_ap != min(N, n_above) or n_ap > N:
                    p.append(f"check 4: week {w} on ({s}, N = {N}) has {n_ap} A+ for {n_above} fills at or above the cutoff (N = {N})")
    return p, [f"check 4 (counts): {n_weeks} week x row pairs asserted - A+ unique by (ticker, E); per week A+ = min(N, fills at or above the cutoff); never more than N"]


def check6_pool(cols: dict, res: dict) -> tuple:
    """WOULD-FAIL-IF 6: each fill's pool count = the population fills with E' in [E - 20, E - 1] (an independent count); >= 30 for every rated
    fill; every fill's week = the ISO week of its own E."""
    pc = pool_counts(cols, keys=())
    p = []
    if not np.array_equal(pc["pool_n"], res["pool_n"]):
        p.append("check 6: the pool count differs from an independent count")
    rated = (res["flag"][("core", N_DECIDES)] != FLAG_UNRATED) & (res["flag"][("core", N_DECIDES)] != FLAG_POOL)
    thin = int((res["pool_n"][rated] < POOL_FLOOR).sum())
    if thin:
        p.append(f"check 6: {thin} rated fills have a pool under {POOL_FLOOR}")
    wk_bad = sum(1 for i in range(len(cols["E"])) if cols["week"][i] != iso_week(cols["E"][i]))
    if wk_bad:
        p.append(f"check 6: {wk_bad} rows carry a week that is not the ISO week of their E")
    return p, [f"check 6 (pool): pool counts equal an independent count; every rated fill's pool >= {POOL_FLOOR}; every week = the ISO week of E"]


def check7_shuffle(cols: dict, res: dict) -> tuple:
    """WOULD-FAIL-IF 7: the A+ set (every spec, every N) is unchanged when the input rows are shuffled (seed 702) - the engine, not the check,
    puts the rows into fill order."""
    n = len(cols["E"])
    rng = np.random.default_rng([SAMPLE_SEED, zlib.crc32(b"aplus_check7")])
    perm = rng.permutation(n)
    cols2 = {k: [np.asarray(v, dtype=object)[j] for j in perm] for k, v in cols.items()}
    res2 = rate_population(cols2)
    p = []
    for s in SPECS:
        for N in SPEC_NS[s]:
            if aplus_set(cols, res, s, N) != aplus_set(cols2, res2, s, N):
                p.append(f"check 7: the A+ set differs after a shuffle on ({s}, N = {N})")
    return p, ["check 7 (shuffle invariance): every A+ set unchanged under a seed-702 shuffle of the input rows"]


def check9_stair(cols: dict, feats: dict, prep: dict, ctx: rr.Ctx) -> tuple:
    """WOULD-FAIL-IF 9: for 50 fills (seed 702) `stair_n` recomputed from a watch copy whose rows of that ticker with watch_date > D carry
    randomised pole_ci / pole_date is unchanged; and every stair_n recomputed from a candidates re-read that CARRIES `base_id` (shuffled)
    is unchanged - the column is never read (the run's own usecols exclude it)."""
    rt = ctx.rt
    n = len(cols["E"])
    el = np.flatnonzero(np.asarray(cols["eligible"], dtype=bool))
    sample = sample_rows(el, CHECK9_SAMPLE, "check9")
    rng = np.random.default_rng([SAMPLE_SEED, zlib.crc32(b"aplus_check9")])
    bad = 0
    for i in sample:
        t, D = cols["ticker"][i], cols["D"][i]
        poles = [(d, int(rng.integers(0, 10_000)), f"rnd-{int(rng.integers(0, 10**6))}") if d > D else (d, pci, pdt) for d, pci, pdt in prep["watch_poles"].get(t, [])]
        chain = chain_at_d(poles, D, rt.POLE_DRIFT_MAX)
        sn = stair_n_of(t, cols["E_ci"][i], cols["pole_ci"][i], feats["per_ticker_rows"].get(t, []), chain, feats["first_e_ci"])
        if sn != cols["stair_n"][i]:
            bad += 1
    p = [f"check 9: {bad} of {len(sample)} stair_n changed when the watch rows after D were randomised"] if bad else []
    c2 = read_table(prep["paths"]["cands"], ["ticker", "D", "E", "K", "retrigger", "pole_ci", "base_id"])
    c2 = c2[c2["K"] == POP_K].copy()
    c2["base_id"] = c2["base_id"].to_numpy()[rng.permutation(len(c2))]
    ex = feats["ex"]
    ptr = defaultdict(list)
    for t, e, pci, rtg in c2[["ticker", "E", "pole_ci", "retrigger"]].itertuples(index=False):
        if int(rtg) == 0 and e in ex.cal_ci:
            ptr[t].append((ex.cal_ci[e], int(pci)))
    bad2 = 0
    for i in range(n):
        t = cols["ticker"][i]
        chain = feats["chain_cache"][(t, cols["D"][i])]
        if stair_n_of(t, cols["E_ci"][i], cols["pole_ci"][i], ptr.get(t, []), chain, feats["first_e_ci"]) != cols["stair_n"][i]:
            bad2 += 1
    if bad2:
        p.append(f"check 9: {bad2} stair_n changed when recomputed from a candidates frame carrying a shuffled base_id")
    return p, [f"check 9 (concept 5): {len(sample)} fills unchanged with the watch rows after D randomised; every stair_n unchanged from a frame with "
               f"base_id present and shuffled (the run's usecols: {CAND_COLS} - no base_id)"]


def check12_scales(cols: dict, res: dict, feats: dict) -> tuple:
    """WOULD-FAIL-IF 12: for every A+ fill and 200 sampled: the base rows = base_len + 1 with h at pole_date = pole_high; wk_ratio / pb_ratio
    recomputed by the pinned formulas equal the stored values (1e-9) with equal missing flags; tightening_ratio = range_recent5 /
    range_early5 (1e-9); the block ending at D is full and no block reaches past D; the incomplete last pullback is never counted (a copy with
    every row after D randomised gives the same two numbers)."""
    ex = feats["ex"]
    el = np.flatnonzero(np.asarray(cols["eligible"], dtype=bool))
    ap = np.flatnonzero(res["flag"][("core", N_DECIDES)] == FLAG_APLUS)
    sample = np.unique(np.concatenate((sample_rows(el, CHECK12_SAMPLE, "check12"), ap)))
    bad = Counter()
    for i in sample:
        t, D, pdt, bl = cols["ticker"][i], cols["D"][i], cols["pole_date"][i], cols["base_len"][i]
        h, l, c = base_rows(ex, t, pdt, D)
        if bl is None or len(h) != int(bl) + 1:
            bad["rows"] += 1
            continue
        if not _eq(float(h[0]), cols["pole_high"][i]):
            bad["pole_high"] += 1
        wk, pb = wk_ratio_of(h, l, c, int(bl)), pb_ratio_of(h, l)
        if not _eq(wk, cols["wk_ratio"][i]) or not _eq(pb, cols["pb_ratio"][i]):
            bad["scales"] += 1
        k = int(bl) // 5
        if k >= 3 and (len(h) - 5 * k < 1):
            bad["blocks"] += 1
        re5 = cols["range_early5"][i]
        tr = (cols["range_recent5"][i] / re5) if re5 and re5 > 0 else None
        if not _eq(tr, cols["tightening_ratio"][i]):
            bad["tightening"] += 1
        pex = PerturbedExport(ex, D, SAMPLE_SEED + 1)
        wk2, pb2, _vd, n2, _h = export_features(pex, t, pdt, D, bl)
        if not _eq(wk2, wk) or not _eq(pb2, pb) or n2 != len(h):
            bad["after_D"] += 1
    p = [f"check 12: {v} fills failed on {k}" for k, v in bad.items()]
    return p, [f"check 12 (concept 1's scales): {len(sample)} fills (200 sampled + {len(ap)} A+) - base rows = base_len + 1, h at P = pole_high, wk_ratio / "
               f"pb_ratio / tightening_ratio recomputed equal the stored values, no block past D, the same numbers with every row after D randomised"]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the outcome join (after STEP 0 and the checks), the report rows, the A+ table
# ═════════════════════════════════════════════════════════════════════════════════════════════
def join_outcomes(cols: dict, outcomes: dict) -> tuple:
    """realized_r / pnl_adr / mature / status per row from the pinned exitpb rows (read, never re-walked); a missing outcome is a problem."""
    n = len(cols["E"])
    r, pnl, mat, st = np.full(n, np.nan), np.full(n, np.nan), np.zeros(n, dtype=np.int64), [""] * n
    problems = []
    for i in range(n):
        o = outcomes.get((cols["ticker"][i], cols["D"][i], cols["E"][i], cols["K"][i]))
        if o is None:
            problems.append(f"outcome: no pinned row for {(cols['ticker'][i], cols['E'][i])}")
            continue
        st[i], r[i], pnl[i], mat[i] = o
        if int(mat[i]) != int(cols["mature"][i]):
            problems.append(f"outcome: mature differs from the feature read for {(cols['ticker'][i], cols['E'][i])}")
    return {"realized_r": r, "pnl_adr": pnl, "mature": mat, "status": st}, problems


def group_of(cols: dict, oc: dict, mask: np.ndarray, key: str, boot) -> dict:
    """The MATURE rows of `mask` as a group's statistics."""
    m = mask & (oc["mature"] == 1) & np.asarray(cols["eligible"], dtype=bool)
    idx = np.flatnonzero(m)
    g = group_stats(oc["realized_r"][idx], oc["pnl_adr"][idx], np.asarray(cols["width_adr"], dtype=float)[idx],
                    np.asarray(cols["ticker"], dtype=object)[idx], np.asarray(cols["fill_month"], dtype=object)[idx], key, boot)
    g["n_filled"] = int((mask & np.asarray(cols["eligible"], dtype=bool)).sum())
    g["n_open"] = g["n_filled"] - g["n"]
    return g


def c0_baseline(cols: dict, oc: dict, c0_all: dict, period: str) -> dict:
    """The table's own C0: EVERY mature pp / orh5 / tl row of the period's table (the edge fills included), beside the pinned published
    numbers. `c0_all` = {(ticker, D, E, K): (status, r, pnl, mature)} of the whole table."""
    r = np.asarray([v[1] for v in c0_all.values() if v[3] == 1], dtype=float)
    pub = C0_PUBLISHED[period]
    return {"n": int(len(r)), "mean_r": float(r.mean()) if len(r) else None, "ge5_per100": float(100 * (r >= 5).mean()) if len(r) else None,
            "count_ge10": int((r >= 10).sum()), "ge10_per100": float(100 * (r >= 10).mean()) if len(r) else None, "published": pub,
            "integers_match": (int(len(r)) == pub["n"] and int((r >= 10).sum()) == pub["ge10"])}


def bins_of(fm: np.ndarray) -> tuple:
    return tuple(int(((fm >= a) & (fm < b)).sum()) for a, b in FM_BINS)


def report_rows(cols: dict, res: dict, oc: dict, period: str, boot, c0: dict) -> tuple:
    """Every reported row (spec x N) with its statistics and verdict (the verdict is decided for every row; only the core at N = 3 decides),
    the paired bars (the core's A+ vs REST; +grp vs the core A+ on the grp-present subset), the core's mixes and splits."""
    el = np.asarray(cols["eligible"], dtype=bool)
    rows, extras = [], {}
    c0n, c0g = C0_PUBLISHED[period]["n"], C0_PUBLISHED[period]["ge10"]
    for s in SPECS:
        for N in SPEC_NS[s]:
            fl = res["flag"][(s, N)]
            g = group_of(cols, oc, fl == FLAG_APLUS, boot_key(period, N, s), boot)
            g.update(spec=s, N=N, period=period, unrated=int(((fl == FLAG_UNRATED) & el).sum()), capped=int(((fl == FLAG_CAPPED) & el).sum()),
                     rest=int(((fl == FLAG_REST) & el).sum()))
            g["verdict"], g["why"] = verdict_of(g, c0, c0n, c0g) if g["n"] else ("CAN'T TELL", "n = 0")
            g["median_width_vs_c0"] = (g["median_width_adr"] - c0["median_width_adr"]) if g.get("median_width_adr") is not None else None
            rows.append(g)
    core = res["flag"][("core", N_DECIDES)]
    mature = (oc["mature"] == 1) & el
    # the paired bar: A+ minus REST (the rated fills not in A+, capped included), mature
    a, b = np.flatnonzero((core == FLAG_APLUS) & mature), np.flatnonzero(((core == FLAG_REST) | (core == FLAG_CAPPED)) & mature)
    months = np.asarray(cols["fill_month"], dtype=object)
    extras["paired"] = paired_delta(oc["realized_r"][a], months[a], oc["realized_r"][b], months[b], pair_key(period, N_DECIDES, "core"))
    # +grp: the +grp A+ set vs the core A+ set, each on the grp-present subset, mature
    grp_present = np.asarray([x is not None for x in cols["grp_pct"]])
    ga = np.flatnonzero((res["flag"][("grp", N_DECIDES)] == FLAG_APLUS) & mature & grp_present)
    ca = np.flatnonzero((core == FLAG_APLUS) & mature & grp_present)
    d = paired_delta(oc["realized_r"][ga], months[ga], oc["realized_r"][ca], months[ca], grp_pair_key(period))
    d["reading"] = grp_reading(d)
    d["grp_present_share"] = float(grp_present[el].mean()) if el.any() else None
    d["overlap"] = int(len(set(ga) & set(ca)))
    extras["grp"] = d
    # the core's mixes and splits (N = 3)
    fm = np.asarray(cols["fill_minute"], dtype=np.int64)
    wd = np.asarray(cols["weekday"], dtype=np.int64)
    ap = (core == FLAG_APLUS) & el
    extras["mix"] = {"aplus_fm_bins": bins_of(fm[ap]), "c0_fm_bins": bins_of(fm[el]), "aplus_weekday": tuple(int((wd[ap] == k).sum()) for k in range(5)),
                     "c0_weekday": tuple(int((wd[el] == k).sum()) for k in range(5)),
                     "aplus_early_close": int(sum(1 for i in np.flatnonzero(ap) if cols["early_close"][i])),
                     "aplus_zero_window": int(sum(1 for i in np.flatnonzero(ap) if cols["block_state"][i] == "ok" and cols["sumv"][i] == 0))}
    ph = np.asarray([None if x is None else int(x) for x in cols["phase_cand"]], dtype=object)
    split = {}
    for side, val in (("phase_on", 1), ("phase_off", 0)):
        m = np.flatnonzero(ap & mature & (ph == val))
        split[side] = {"n": int(len(m)), "mean_r": (float(oc["realized_r"][m].mean()) if len(m) else None)}
    extras["phase_split"] = split
    bl = np.asarray([np.nan if x is None else float(x) for x in cols["base_len"]], dtype=float)
    wk = np.asarray([np.nan if x is None else float(x) for x in cols["wk_ratio"]], dtype=float)
    pb = np.asarray([np.nan if x is None else float(x) for x in cols["pb_ratio"]], dtype=float)
    extras["shares"] = {"aplus_base_ge15": float((bl[ap] >= 15).mean()) if ap.any() else None, "c0_base_ge15": float((bl[el] >= 15).mean()) if el.any() else None,
                        "aplus_wk_median": float(np.nanmedian(wk[ap])) if ap.any() and not np.isnan(wk[ap]).all() else None,
                        "c0_wk_median": float(np.nanmedian(wk[el])) if not np.isnan(wk[el]).all() else None,
                        "aplus_pb_median": float(np.nanmedian(pb[ap])) if ap.any() and not np.isnan(pb[ap]).all() else None,
                        "c0_pb_median": float(np.nanmedian(pb[el])) if not np.isnan(pb[el]).all() else None}
    return rows, extras


def expectations(rows: list, extras: dict, c0: dict, counts: dict, period: str) -> list:
    """The registered expectations (a miss is reported first and changes NO rule)."""
    core = next(r for r in rows if r["spec"] == "core" and r["N"] == N_DECIDES)
    lo, hi = EXPECT_APLUS_N.get(period, (None, None))
    out = []
    n3 = counts[N_DECIDES]["aplus"]
    out.append(f"A+ n (N = 3) {n3} in {lo}-{hi}: {'met' if lo is not None and lo <= n3 <= hi else 'MISS'}")
    mw = core.get("median_width_adr")
    out.append(f"A+ median stop width {_r(mw, 3)} ADR vs C0's {_r(c0.get('median_width_adr'), 3)}: "
               f"{'met' if mw is not None and mw >= c0['median_width_adr'] else 'MISS'}")
    sh = counts[N_DECIDES]["weeks_under_n_share"]
    out.append(f"weeks with fewer than 3 A+ after the first {BURN_IN_WEEKS} weeks {_r(sh, 3)}: {'met' if sh is not None and sh <= 0.40 else 'MISS'}")
    pub = c0["published"]
    c0_ok = c0["mean_r"] is not None and abs(c0["mean_r"] - pub["mean_r"]) <= 0.0005 and abs(c0["ge10_per100"] - pub["ge10_per100"]) <= 0.0005
    out.append(f"C0 under pp reads as published (mean R {_r(c0['mean_r'], 4)} vs {pub['mean_r']:+.3f}; >= 10R {_r(c0['ge10_per100'], 3)} vs {pub['ge10_per100']} per 100; "
               f"n {c0['n']} vs {pub['n']}; >= 10R count {c0['count_ge10']} vs {pub['ge10']}): {'met' if c0_ok and c0['integers_match'] else 'MISS'}")
    s = extras["shares"]
    out.append(f"A+ share of bases >= 15 sessions {_r(s['aplus_base_ge15'], 3)} above C0's {_r(s['c0_base_ge15'], 3)}: "
               f"{'met' if s['aplus_base_ge15'] is not None and s['c0_base_ge15'] is not None and s['aplus_base_ge15'] > s['c0_base_ge15'] else 'MISS'}")
    out.append(f"A+ median wk_ratio {_r(s['aplus_wk_median'], 3)} below the population's {_r(s['c0_wk_median'], 3)} and pb_ratio {_r(s['aplus_pb_median'], 3)} below "
               f"{_r(s['c0_pb_median'], 3)} (carrying fills): "
               f"{'met' if all(s[a] is not None and s[b] is not None and s[a] < s[b] for a, b in (('aplus_wk_median', 'c0_wk_median'), ('aplus_pb_median', 'c0_pb_median'))) else 'MISS'}")
    mx = extras["mix"]
    out.append(f"fill-minute mix A+ {mx['aplus_fm_bins']} vs C0 {mx['c0_fm_bins']}; weekday mix A+ {mx['aplus_weekday']} vs C0 {mx['c0_weekday']} (Mon..Fri) - "
               f"expected at or earlier than C0's from the cap alone; reported")
    return out


APLUS_TABLE_BASE = ["ticker", "D", "E", "K", "period", "eligible", "week", "weekday", "fill", "fill_minute", "fill_month", "adr20", "width_adr", "stop",
                    "mature", "open_mark", "early_close", "pool_n"]
APLUS_TABLE_FEATS = ["tightening_ratio", "wk_ratio", "pb_ratio", "vol_dry5", "rs_best", "prior_move", "stair_n", "exp_up_adr", "vol_sofar_x", "prof_m",
                     "range_sofar_adr", "grp_pct", "base_len", "range5_adr", "base_depth", "atr14_slope", "rs_all", "phase_cand", "close_D", "pole_date",
                     "pole_ci", "chain_base", "base_rows_n", "sumv", "maxh", "minl", "first_open", "n_present", "n_absent", "min0_absent", "fill_present",
                     "h_fill", "v_fill", "block_state"]


def aplus_table_cols() -> list:
    cols = APLUS_TABLE_BASE + APLUS_TABLE_FEATS + [f"pct_{k}" for k in FEATURE_KEYS]
    for s in SPECS:
        cols.append(f"score_{s}")
        for N in SPEC_NS[s]:
            cols += [f"cutoff_{s}_n{N}", f"flag_{s}_n{N}"]
    return cols + ["status", "realized_r", "pnl_adr"]


def aplus_table_rows(cols: dict, res: dict, oc: "dict | None", period: str) -> list:
    n = len(cols["E"])
    out = []
    for i in range(n):
        r = {k: cols[k][i] for k in APLUS_TABLE_BASE if k in cols}
        r["period"], r["pool_n"] = period, int(res["pool_n"][i])
        r["eligible"] = int(bool(cols["eligible"][i]))
        for k in APLUS_TABLE_FEATS:
            r[k] = cols[k][i]
        for j, k in enumerate(FEATURE_KEYS):
            r[f"pct_{k}"] = res["pct"][i, j]
        for s in SPECS:
            r[f"score_{s}"] = res["score"][s][i]
            for N in SPEC_NS[s]:
                r[f"cutoff_{s}_n{N}"], r[f"flag_{s}_n{N}"] = res["cutoff"][(s, N)][i], res["flag"][(s, N)][i]
        if oc is not None:
            r["status"], r["realized_r"], r["pnl_adr"] = oc["status"][i], oc["realized_r"][i], oc["pnl_adr"][i]
        out.append(r)
    return out


REPORT_COLS = ["period", "spec", "N", "n_filled", "n", "n_open", "mean_r", "ci_lo", "ci_hi", "win_rate", "avg_win", "avg_loss", "ge5_per100", "ge10_per100",
               "ge20_per100", "sum_r", "mean_pnl_adr", "median_width_adr", "median_width_vs_c0", "count_ge10", "tail_tickers", "tail_months",
               "tail_tickers_allwidths", "tail_months_allwidths", "unrated", "capped", "rest", "verdict", "why", "key"]


def report_text(period: str, rows: list, extras: dict, c0: dict, counts: dict, exp_lines: list, check_lines: list, notes: list, rt) -> str:
    L = [f"#705 A+ RATING READ - period {period} - tl - ORH5 - pp - mature walks (N = 3 decides; every other row beside, never a finding)"]
    L += notes
    L.append("")
    L.append(f"C0 (the table's own, every mature pp / orh5 / tl row): n {c0['n']:,}, mean R {_r(c0['mean_r'], 4)}, >= 5R {_r(c0['ge5_per100'], 3)} / 100, "
             f">= 10R {c0['count_ge10']} ({_r(c0['ge10_per100'], 3)} / 100); published {C0_PUBLISHED[period]}; median stop width {_r(c0['median_width_adr'], 3)} ADR")
    body = []
    for r in rows:
        body.append([f"{r['spec']} N={r['N']}", r["n_filled"], r["n"], _r(r.get("mean_r"), 3), f"[{_r(r.get('ci_lo'), 2)}, {_r(r.get('ci_hi'), 2)}]" if r.get("n", 0) >= 2 else "",
                     _r(r.get("win_rate"), 3), _r(r.get("ge5_per100"), 2), _r(r.get("ge10_per100"), 2), _r(r.get("ge20_per100"), 2), _r(r.get("sum_r"), 1),
                     _r(r.get("mean_pnl_adr"), 3), _r(r.get("median_width_adr"), 3), f"{r.get('count_ge10', '')}: {r.get('tail_tickers', '')}t/{r.get('tail_months', '')}m" if r.get("n") else "",
                     r["unrated"], r["capped"], r["verdict"], r["why"]])
    L.append(rt.table(body, ["row", "filled", "n", "mean R", "95% CI", "win", ">=5R/100", ">=10R/100", ">=20R/100", "total R", "ADR P&L", "med width", ">=10R spread",
                             "unrated", "capped", "verdict", "why"]))
    L.append("")
    pr = extras["paired"]
    L.append(f"PAIRED (core A+ minus REST, N = 3, mature): n {pr['n_a']} vs {pr['n_b']}, mean delta {_r(pr.get('mean'), 4)} [{_r(pr.get('lo'), 3)}, {_r(pr.get('hi'), 3)}] "
             f"over {pr['months']} months ({pr['discarded']} empty draws redrawn) -> {pr['reading']}")
    g = extras["grp"]
    L.append(f"+grp (the +grp A+ set minus the core A+ set on the grp-present subset, {_r(g.get('grp_present_share'), 3)} of fills; overlap {g['overlap']}): n {g['n_a']} vs {g['n_b']}, "
             f"mean delta {_r(g.get('mean'), 4)} [{_r(g.get('lo'), 3)}, {_r(g.get('hi'), 3)}] ({g['discarded']} redrawn) -> {g['reading']}")
    ps = extras["phase_split"]
    L.append(f"PHASE SPLIT (core A+, mature): phase on n {ps['phase_on']['n']} mean R {_r(ps['phase_on']['mean_r'], 3)}; phase off n {ps['phase_off']['n']} mean R "
             f"{_r(ps['phase_off']['mean_r'], 3)}")
    mx = extras["mix"]
    L.append(f"A+ on early-close sessions {mx['aplus_early_close']}; with a zero-volume window {mx['aplus_zero_window']}")
    for N in NS:
        c = counts[N]
        L.append(f"core N = {N}: A+ {c['aplus']}, capped {c['capped']}, rest {c['rest']}, unrated {c['unrated']}; weeks with fewer than {N} A+ after burn-in {_r(c['weeks_under_n_share'], 3)}")
    L.append("")
    L.append("EXPECTATIONS (a miss is reported first and changes NO rule):")
    L += [f"  {x}" for x in exp_lines]
    L.append("")
    L.append("CHECKS:")
    L += [f"  {x}" for x in check_lines]
    return "\n".join(L)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the read: STEP 0 -> checks -> outcomes -> bars -> the re-derivation -> the verdict
# ═════════════════════════════════════════════════════════════════════════════════════════════
def aplus_outputs(ctx: rr.Ctx) -> tuple:
    return (f"trades_{ctx.period}_{APLUS_TAG}.tsv.gz", f"{APLUS_TAG}_report_{ctx.period}.tsv", f"{APLUS_TAG}_report_{ctx.period}.txt")


def step0(ctx: rr.Ctx, prep: dict, say, with_perturbation: bool = True) -> tuple:
    """The census and its equality targets (no outcome column opened). Returns (feats, census, problems)."""
    feats = build_features(ctx, prep, say, with_perturbation)
    c = census(feats["cols"], prep, ctx.rt.H60_EARLY_CLOSE)
    expected = APLUS_EXPECTED.get(prep["period"], {})
    for ln in census_text(c, prep["period"], expected):
        say(ln)
    problems = census_problems(c, expected)
    pp = profile_problems(feats["prof"])
    got = rr.sha256_file(prep["paths"]["profile"])
    if got != PROFILE_SHA_EXPECTED:
        pp.append(f"sha256 {got[:12]}... is not the EXPECTED {PROFILE_SHA_EXPECTED[:12]}...")
    say(f"  profile {prep['paths']['profile'].name}: {'format, endpoints, monotone and the eight pinned values ok; sha256 = EXPECTED' if not pp else 'PROBLEMS: ' + '; '.join(pp)}")
    problems += [f"STEP 0: profile: {x}" for x in pp]
    return feats, c, problems


def run_checks(ctx: rr.Ctx, prep: dict, feats: dict, res: dict, say) -> tuple:
    """WOULD-FAIL-IF 1, 2, 5, 6, 7, 9, 12 and data check 3 on the inputs (features and the flag, never an outcome number); check 4 = the
    golden fixtures on the committed code."""
    cols = feats["cols"]
    problems, lines = [], []
    for fn in (lambda: check3_join(cols, feats, prep, ctx, PROFILE_SHA_EXPECTED), lambda: check1_lookahead(cols, res, feats, prep, ctx),
               lambda: check2_later_fills(cols, res), lambda: check4_counts(cols, res), lambda: check5_breakout_inputs(cols, res, feats, prep, ctx),
               lambda: check6_pool(cols, res),
               lambda: check7_shuffle(cols, res), lambda: check9_stair(cols, feats, prep, ctx), lambda: check12_scales(cols, res, feats)):
        p, ln = fn()
        problems += p
        lines += ln
        for x in ln:
            say("  " + x)
    from scripts.probes._cb_backtest import aplus_fixtures
    gp = aplus_fixtures.run_golden()
    problems += [f"check 4 (golden fixtures): {x}" for x in gp]
    g = f"check 4 (golden fixtures E / E2 / E3 on the committed code): {'pass' if not gp else 'FAIL: ' + '; '.join(gp)}"
    lines.append(g)
    say("  " + g)
    return problems, lines


def aplus_dry_run(ctx: rr.Ctx, prep: dict, existing: list) -> str:
    """`--dry-run`: the STEP 0 census against its equality targets (no outcome column opened, nothing written). `--dry-run --self-check` adds
    the rating counts and every WOULD-FAIL-IF check (still no outcome)."""
    say = ctx.say
    say(f"APLUS DRY RUN (freeze check {ctx.freeze}; features only): period {ctx.period}: {len(prep['rows']):,} eligible rows from {prep['paths']['fills']}, "
        f"{len(prep['inp']['pairs']):,} (date, ticker) pairs; pairs NOT logged in _done.psv: {len(prep['inp']['missing'])}, logged ok with no file: "
        f"{len(prep['inp']['lost'])}; outputs already on disk: {[q.name for q in existing] or 'none'}")
    feats, c, problems = step0(ctx, prep, say, with_perturbation=bool(getattr(ctx.args, "self_check", False)))
    if getattr(ctx.args, "self_check", False):
        res = rate_population(feats["cols"])
        counts = rating_counts(feats["cols"], res, ctx.period)
        for N in NS:
            say(f"  core N = {N}: A+ {counts[N]['aplus']}, capped {counts[N]['capped']}, rest {counts[N]['rest']}, unrated {counts[N]['unrated']} (expectation {counts[N]['expected_range']})")
        p2, _lines = run_checks(ctx, prep, feats, res, say)
        problems += p2
    return ("STEP 0 PASSED: every equality target met" + ("; SELF-CHECK PASSED" if getattr(ctx.args, "self_check", False) else "")) if not problems else \
        "STEP 0 / SELF-CHECK FAILED (the read would exit 3):\n" + "\n".join("  - " + x for x in problems)


def aplus_body(ctx: rr.Ctx, prep: dict, say) -> "rr.Verdict | int":
    rt, period = ctx.rt, prep["period"]
    feats, c, problems = step0(ctx, prep, say)
    if problems:
        say("STEP 0 FAILED: " + "; ".join(problems) + " - the read stops here; no outcome column was opened")
        return 3
    cols = feats["cols"]
    res = rate_population(cols)
    counts = rating_counts(cols, res, period)
    for N in NS:
        say(f"  STEP 0 rating counts, core N = {N}: A+ {counts[N]['aplus']}, capped {counts[N]['capped']}, rest {counts[N]['rest']}, unrated {counts[N]['unrated']} "
            f"(expectation {counts[N]['expected_range']}); pool size min {c['pool_min']} / median {c['pool_median']}")
    problems, check_lines = run_checks(ctx, prep, feats, res, say)
    if problems:
        say("IMPLEMENTATION CHECK FAILED (" + str(len(problems)) + "): " + "; ".join(problems) + " - the report is NOT written; no outcome column was opened")
        return 3
    # the outcomes - opened ONLY now
    outcomes = read_outcomes(prep["paths"]["fills"])
    if period == "holdout":
        outcomes.update(read_outcomes(prep["paths"]["pool_fills"]))
    oc, p = join_outcomes(cols, outcomes)
    if p:
        say("OUTCOME JOIN FAILED: " + "; ".join(p[:5]))
        return 3
    el = np.asarray(cols["eligible"], dtype=bool)
    c0 = c0_baseline(cols, oc, read_outcomes(prep["paths"]["fills"]), period)
    c0["median_width_adr"] = float(np.median(np.asarray(cols["width_adr"], dtype=float)[el & (oc["mature"] == 1)]))
    if not c0["integers_match"]:
        say(f"C0 INTEGERS DIFFER: the table's mature n {c0['n']} / >= 10R count {c0['count_ge10']} are not the registered {C0_PUBLISHED[period]['n']} / "
            f"{C0_PUBLISHED[period]['ge10']} - the outlier bar's constants do not describe this table; the report is NOT written")
        return 3
    rows, extras = report_rows(cols, res, oc, period, rt.block_bootstrap_ci, c0)
    exp_lines = expectations(rows, extras, c0, counts, period)
    core = next(r for r in rows if r["spec"] == "core" and r["N"] == N_DECIDES)
    # check 3's outcome clause: the A+ rows' outcomes equal the pinned rows (re-read)
    pinned = read_outcomes(prep["paths"]["fills"])
    ap = np.flatnonzero(res["flag"][("core", N_DECIDES)] == FLAG_APLUS)
    bad = sum(1 for i in ap if abs(pinned[(cols["ticker"][i], cols["D"][i], cols["E"][i], cols["K"][i])][1] - oc["realized_r"][i]) > 1e-9)
    if bad:
        say(f"CHECK 3 (outcomes) FAILED: {bad} A+ rows differ from the pinned exitpb rows")
        return 3
    check_lines.append(f"check 3 (outcomes): every A+ row's realized_r equals the pinned exitpb row (1e-9) - read, never re-walked")
    # the independent re-derivation (check 11, data check 6): VERDICT MATCH before the result is written
    from scripts.probes._cb_backtest import aplus_rederive
    t0 = time.time()
    rd = aplus_rederive.rederive(prep["paths"], period, pool_only_min_e=(min(cols["E"][i] for i in range(len(cols["E"]))) if period == "holdout" else None),
                                 early_close=set(rt.H60_EARLY_CLOSE), drift_max=rt.POLE_DRIFT_MAX, pre_minutes=ctx.dirs["cb702_pre"] / "minutes",
                                 pre_fills=ctx.dirs["cb702_pre"] / "out" / "trades_pre_exitpb.tsv.gz", c0=C0_PUBLISHED[period], log=say)
    mp = match_problems(cols, res, rows, extras, rd, feats["prof"])
    say(f"RE-DERIVATION (pandas, no runner code) [{time.time() - t0:.0f}s]: {'VERDICT MATCH' if not mp else 'MISMATCH: ' + '; '.join(mp)}")
    if mp:
        say("the result is NOT written")
        return 3
    check_lines.append(f"check 11 (re-derivation): VERDICT MATCH - the A+ sets (core N = 1 / 3 / 5, +grp, the reversed stair-step row), n, mean R, the "
                       f"intervals, both paired deltas, every PASS component and the +grp reading; the profile re-derived from the 2017-21 tree "
                       f"(tally {rd['profile']['tally']}) equal to the pinned file to 1e-9")
    notes = [f"DATA CHECKS: freeze {ctx.freeze}; STEP 0 equal to the registered counts; implementation checks passed; re-derivation VERDICT MATCH"]
    text = report_text(period, rows, extras, c0, counts, exp_lines, check_lines, notes, rt)
    table_name, rep_tsv, rep_txt = aplus_outputs(ctx)
    trows = aplus_table_rows(cols, res, oc, period)
    tcols = aplus_table_cols()
    with ctx.partial_write(table_name) as fh:
        fh.write(rt.rows_to_gz([tcols]))
        fh.write(rt.rows_to_gz([[r.get(k) for k in tcols] for r in trows]))
    rt.write_tsv(ctx.out / rep_tsv, rows, REPORT_COLS)
    rt.write_tsv(ctx.small / rep_tsv, [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows], REPORT_COLS)
    (ctx.out / rep_txt).write_text(text + "\n")
    (ctx.small / rep_txt).write_text(text + "\n")
    print(text)
    say(f"WROTE {ctx.out / table_name} ({len(trows):,} rows), {ctx.out / rep_tsv} ({len(rows)} rows), {ctx.small / rep_txt}")
    data = {"period": period, "verdict": core["verdict"], "why": core["why"], "n": core["n"], "aplus_n": {N: counts[N]["aplus"] for N in NS},
            "components": {k: core.get(k) for k in ("mean_r", "ci_lo", "ci_hi", "mean_pnl_adr", "ge5_per100", "count_ge10", "ge10_per100", "tail_tickers", "tail_months",
                                                    "median_width_adr")},
            "c0": {k: c0.get(k) for k in ("n", "mean_r", "ge5_per100", "count_ge10", "ge10_per100", "median_width_adr")},
            "paired": {k: extras["paired"].get(k) for k in ("n_a", "n_b", "mean", "lo", "hi", "reading", "discarded", "key")},
            "grp": {k: extras["grp"].get(k) for k in ("n_a", "n_b", "mean", "lo", "hi", "reading", "discarded", "overlap", "grp_present_share", "key")},
            "rows": {f"{r['spec']}|{r['N']}": {k: r.get(k) for k in ("n", "mean_r", "ci_lo", "ci_hi", "ge5_per100", "ge10_per100", "count_ge10", "tail_tickers", "tail_months", "verdict")} for r in rows},
            "expectations": exp_lines, "rederivation": "MATCH", "written": time.strftime("%Y-%m-%d")}
    lines = (f"#705 A+ RATING VERDICT FILE - period {period} - written {time.strftime('%Y-%m-%d')}",
             f"core N = 3: {core['verdict']} ({core['why']}); n {core['n']}, mean R {_r(core.get('mean_r'), 4)} [{_r(core.get('ci_lo'), 3)}, {_r(core.get('ci_hi'), 3)}], "
             f">= 5R {_r(core.get('ge5_per100'), 3)} / 100, >= 10R {core.get('count_ge10')} ({core.get('tail_tickers')}t / {core.get('tail_months')}m), ADR P&L {_r(core.get('mean_pnl_adr'), 4)}",
             f"paired A+ minus REST: {extras['paired']['reading']} [{_r(extras['paired'].get('lo'), 3)}, {_r(extras['paired'].get('hi'), 3)}]; "
             f"+grp: {extras['grp']['reading']} [{_r(extras['grp'].get('lo'), 3)}, {_r(extras['grp'].get('hi'), 3)}]; re-derivation: VERDICT MATCH")
    return rr.Verdict(data, lines)


def match_problems(cols: dict, res: dict, rows: list, extras: dict, rd: dict, prof: np.ndarray, tol: float = 1e-9) -> list:
    """MATCH: first the identical (ticker, E) A+ set per N for the core, for +grp and for the reversed-concept-5 row; only then n / mean R /
    the interval / the two paired deltas / every PASS component / the +grp reading; the re-derived profile equal to the pinned file to 1e-9."""
    p = []
    for s, N in (("core", 1), ("core", 3), ("core", 5), ("grp", 3), ("rev_stair", 3)):
        ours, theirs = aplus_set(cols, res, s, N), rd["aplus"].get((s, N))
        if theirs is None or ours != theirs:
            d = (len(ours - (theirs or set())), len((theirs or set()) - ours))
            p.append(f"the A+ set differs on ({s}, N = {N}): {d[0]} only ours, {d[1]} only re-derived")
    if p:
        return p
    # a numeric mismatch names the component and the size of the gap - never the values (no outcome number leaves a FAILED run)
    def gap(a, b) -> str:
        if a is None or b is None or a != a or b != b:
            return "one side missing / NaN"
        return f"|difference| {abs(float(a) - float(b)):.3g}"
    core = next(r for r in rows if r["spec"] == "core" and r["N"] == N_DECIDES)
    for k in ("n", "mean_r", "ci_lo", "ci_hi", "ge5_per100", "mean_pnl_adr", "count_ge10", "tail_tickers", "tail_months"):
        a, b = core.get(k), rd["core"].get(k)
        if a is None or b is None or (isinstance(a, float) and abs(a - b) > tol) or (not isinstance(a, float) and a != b):
            p.append(f"core N = 3 {k} differs from the re-derivation ({gap(a, b)})")
    if core["verdict"] != rd["core"].get("verdict"):
        p.append("the verdict class differs from the re-derivation")
    for name, ours in (("paired", extras["paired"]), ("grp", extras["grp"])):
        th = rd[name]
        for k in ("mean", "lo", "hi"):
            a, b = ours.get(k), th.get(k)
            if not ((a != a and b != b) or (a is not None and b is not None and abs(a - b) <= tol)):
                p.append(f"{name} {k} differs from the re-derivation ({gap(a, b)})")
        if ours["reading"] != th["reading"]:
            p.append(f"the {name} reading differs from the re-derivation")
    pr = rd["profile"]
    if pr["tally"] != PROFILE_TALLY:
        p.append(f"the re-derived profile tally {pr['tally']} is not the registered {PROFILE_TALLY}")
    if np.abs(np.asarray(pr["values"]) - prof).max() > tol:
        p.append("the re-derived profile differs from the pinned file by more than 1e-9")
    return p


# ═════════════════════════════════════════════════════════════════════════════════════════════
# aplus-confirm: the sealed 2025-26 read - refuses unless both deciding verdict files exist and the consequence cell reads RECORD
# ═════════════════════════════════════════════════════════════════════════════════════════════
def verdict_paths(ctx: rr.Ctx) -> dict:
    return {"pre": ctx.dirs["cb702_pre"] / "out" / f"{APLUS_TAG}_verdict_pre.json", "discovery": ctx.dirs["cb702"] / "out" / f"{APLUS_TAG}_verdict_discovery.json"}


def load_verdicts(ctx: rr.Ctx) -> "dict | str":
    vp = verdict_paths(ctx)
    missing = [str(p) for p in vp.values() if not p.exists()]
    if missing:
        return f"the deciding verdict file(s) {missing} do not exist"
    return {k: json.loads(p.read_text()) for k, p in vp.items()}


def confirm_prepare(ctx: rr.Ctx) -> dict:
    v = load_verdicts(ctx)
    if isinstance(v, str):
        _refuse(f"REFUSED: aplus-confirm reads the sealed 2025-26 table ONLY after both deciding eras are read: {v}")
    cell = consequence(v["pre"], v["discovery"])
    if cell["cell"] != "RECORD":
        _refuse(f"REFUSED: the consequence cell reads {cell['cell']} ({cell['why']}) - the sealed 2025-26 read runs only on RECORD (PASS x PASS, no veto)")
    return aplus_prepare(ctx)


def confirm_outputs(ctx: rr.Ctx) -> tuple:
    return aplus_outputs(ctx)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# aplus-hindsight: the 39 and the within-week top-N; refuses until BOTH verdict files exist
# ═════════════════════════════════════════════════════════════════════════════════════════════
def hindsight_prepare(ctx: rr.Ctx) -> dict:
    v = load_verdicts(ctx)
    if isinstance(v, str):
        _refuse(f"REFUSED: the hindsight tables are written only AFTER both deciding verdict files exist: {v}")
    table = ctx.out / f"trades_{ctx.period}_{APLUS_TAG}.tsv.gz"
    if not table.exists():
        _refuse(f"REFUSED: {table} missing - run aplus-read first")
    t = read_table(table, None)
    rows = [{"ticker": a, "E": b, "K": POP_K, "D": d} for a, b, d in t[["ticker", "E", "D"]].itertuples(index=False)]
    return {"rows": rows, "inp": None, "opens": (), "table": t}           # the A+ table is aplus-read's OWN output, not a pinned input


def hindsight_outputs(ctx: rr.Ctx) -> tuple:
    return (f"{APLUS_TAG}_hindsight_{ctx.period}.tsv", f"{APLUS_TAG}_hindsight_{ctx.period}.txt")


def hindsight_dry_run(ctx: rr.Ctx, prep: dict, existing: list) -> str:
    return (f"APLUS HINDSIGHT DRY RUN (freeze check {ctx.freeze}): period {ctx.period}: {len(prep['rows']):,} rows of the A+ table; outputs already on disk: "
            f"{[q.name for q in existing] or 'none'}")


def hindsight_body(ctx: rr.Ctx, prep: dict, say) -> int:
    """The within-ISO-week top-N by the same percentile formula over the week's rated fills (the HINDSIGHT row, labelled so), and the 39: per
    ticker of the list, its fills, A+ among them, mean / total R. Decides nothing."""
    rt, t = ctx.rt, prep["table"]
    t = t[t["eligible"] == 1].reset_index(drop=True)
    n = len(t)
    cols = {k: [None if (isinstance(x, float) and x != x) else x for x in t[k]] for k in t.columns}
    cols["E_ci"] = list(range(n))
    cols["eligible"] = [True] * n
    cols["fill_minute"] = [int(x) for x in cols["fill_minute"]]
    res = {"score": {"core": np.asarray([np.nan if x is None else float(x) for x in cols["score_core"]], dtype=float)}}
    lines = [f"#705 A+ HINDSIGHT - period {ctx.period} (descriptive; written AFTER both verdicts; naming winners afterwards always looks good; decides nothing)"]
    out_rows = []
    mature = np.asarray([int(x or 0) for x in cols["mature"]]) == 1
    r = np.asarray([np.nan if x is None else float(x) for x in cols["realized_r"]], dtype=float)
    for N in NS:
        top = hindsight_topn(cols, res, SPECS["core"], N)
        m = top & mature
        fwd = np.asarray([cols[f"flag_core_n{N}"][i] == FLAG_APLUS for i in range(n)])
        both = int((top & fwd).sum())
        lines.append(f"HINDSIGHT within-week top-{N}: n {int(top.sum())} (mature {int(m.sum())}), mean R {_r(float(r[m].mean()) if m.any() else None, 3)}, "
                     f">= 10R {int((r[m] >= 10).sum())}; shares {both} fills with the forward A+ set (N = {N}: {int(fwd.sum())})")
        for i in np.flatnonzero(top):
            out_rows.append({"row": f"hindsight_top{N}", "ticker": cols["ticker"][i], "E": cols["E"][i], "week": cols["week"][i], "score_core": cols["score_core"][i],
                             "forward_flag": cols[f"flag_core_n{N}"][i], "mature": cols["mature"][i], "realized_r": cols["realized_r"][i]})
    lines.append("THE 39 (hindsight; the 2017-21 list - a ticker absent from this period's table shows 0 fills):")
    body = []
    for tk in THE_39:
        idx = np.flatnonzero(np.asarray(cols["ticker"], dtype=object) == tk)
        mi = idx[mature[idx]]
        ap = sum(1 for i in idx if cols["flag_core_n3"][i] == FLAG_APLUS)
        body.append([tk, len(idx), ap, _r(float(r[mi].mean()) if len(mi) else None, 2), _r(float(r[mi].sum()) if len(mi) else None, 1), int((r[mi] >= 10).sum()) if len(mi) else 0])
        out_rows.append({"row": "the_39", "ticker": tk, "E": "", "week": "", "score_core": None, "forward_flag": f"{ap} A+ of {len(idx)} fills", "mature": int(len(mi)),
                         "realized_r": float(r[mi].sum()) if len(mi) else None})
    lines.append(rt.table(body, ["ticker", "fills", "A+ (N=3)", "mean R", "total R", ">=10R"]))
    text = "\n".join(lines)
    tsv, txt = hindsight_outputs(ctx)
    hcols = ["row", "ticker", "E", "week", "score_core", "forward_flag", "mature", "realized_r"]
    rt.write_tsv(ctx.out / tsv, out_rows, hcols)
    rt.write_tsv(ctx.small / tsv, out_rows, hcols)
    (ctx.out / txt).write_text(text + "\n")
    (ctx.small / txt).write_text(text + "\n")
    print(text)
    say(f"WROTE {ctx.out / tsv} ({len(out_rows)} rows), {ctx.small / txt}")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the specs
# ═════════════════════════════════════════════════════════════════════════════════════════════
APLUS_READ = rr.RegisteredRead(name="aplus-read", tag=APLUS_TAG, doc=APLUS_DOC, frozen=aplus_frozen, prepare=aplus_prepare, outputs=aplus_outputs,
                               dry_run=aplus_dry_run, body=aplus_body, periods=APLUS_PERIODS)
APLUS_CONFIRM = rr.RegisteredRead(name="aplus-confirm", tag=APLUS_TAG, doc=APLUS_DOC, frozen=aplus_frozen, prepare=confirm_prepare, outputs=confirm_outputs,
                                  dry_run=aplus_dry_run, body=aplus_body, periods=CONFIRM_PERIODS)
APLUS_HINDSIGHT = rr.RegisteredRead(name="aplus-hindsight", tag=f"{APLUS_TAG}_hind", doc=APLUS_DOC, frozen=aplus_frozen, prepare=hindsight_prepare,
                                    outputs=hindsight_outputs, dry_run=hindsight_dry_run, body=hindsight_body, periods=APLUS_PERIODS)
REGISTERED = {s.name: s for s in (APLUS_READ, APLUS_CONFIRM, APLUS_HINDSIGHT)}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# aplus-profile (a build, before the pins) and aplus-verdict (the consequence cell) - plain stages
# ═════════════════════════════════════════════════════════════════════════════════════════════
def profile_pairs(minutes_dir: Path, rt, early_close: frozenset, population: set, log=print) -> tuple:
    """CUM(m) for every pair logged ok in `_done.psv` (an absent / invalid block = a zero-volume day), with the per-pair tally flags."""
    done = rt.load_done_pairs(minutes_dir)
    if done is None:
        raise ValueError(f"{minutes_dir}: no _done.psv")
    ok_pairs = sorted(k for k, s in done.items() if s == "ok")
    files = rt.minute_date_files(minutes_dir)
    by_date = defaultdict(list)
    for d, t in ok_pairs:
        by_date[d].append(t)
    rows, meta = [], []
    t0 = time.time()
    for k, (d, tks) in enumerate(sorted(by_date.items())):
        p = files.get(d)
        blocks = rt.read_minute_file(p)[0] if p is not None else {}
        for t in tks:
            vec = np.zeros(390)
            rws = blocks.get(t)
            mb = rt.minute_bars_from_rows(rws) if rws else None
            if mb is not None:
                np.add.at(vec, np.asarray(mb.minute), np.asarray(mb.v))
            tot = vec.sum()
            cum = np.concatenate([[0.0], np.cumsum(vec)]) / tot if tot > 0 else np.full(391, np.nan)
            rows.append(cum)
            meta.append((d, t, tot > 0, d in early_close, (d, t) in population))
        if k % 200 == 0:
            log(f"  profile: {k + 1}/{len(by_date)} dates, {len(rows):,} pairs [{time.time() - t0:.0f}s]")
    return np.vstack(rows) if rows else np.zeros((0, 391)), meta


def build_profile(minutes_dir: Path, rt, early_close: frozenset, population: set, log=print) -> tuple:
    """(profile, tally): the pointwise MEDIAN (numpy, float64, unsmoothed) of CUM over the kept pairs = ok - zero-volume - early-close -
    population."""
    M, meta = profile_pairs(minutes_dir, rt, early_close, population, log)
    nonzero = np.array([m[2] for m in meta], dtype=bool)
    early = np.array([m[3] for m in meta], dtype=bool)
    pop = np.array([m[4] for m in meta], dtype=bool)
    keep = nonzero & ~early & ~pop
    tally = {"ok": int(len(meta)), "zero": int((~nonzero).sum()), "early": int((nonzero & early).sum()), "population": int((nonzero & ~early & pop).sum()),
             "kept": int(keep.sum())}
    prof = np.median(M[keep], axis=0) if keep.any() else np.full(391, np.nan)
    return prof, tally


def run_profile(args, rt) -> int:
    """`aplus-profile --data CB702 --data-pre CB702_PRE`: builds `cb702_pre/out/aplus_intraday_profile.tsv` per the PROFILE block from the
    2017-21 tree (minute volumes only; the population's (E, ticker) keys from the pre fills table's feature columns). Refuses to overwrite an
    existing file (a pin is never rebuilt). The build must equal EXPECTED: on a mismatch the file stays as `.partial` and the stage exits 3."""
    T0 = time.time()
    dirs = rt.h60_dirs(args)
    pre = dirs["cb702_pre"]
    small = Path(args.small_out) if getattr(args, "small_out", None) else Path(rt.HERE) / "out"
    out = pre / "out" / PROFILE_NAME
    log: list = []

    def say(msg=""):
        print(msg, flush=True)
        log.append(msg)
    if out.exists() or rt.partial_path(out).exists():
        print(f"REFUSED: {out} (or its .partial) exists - the profile is a pin, built ONCE; the operator removes it by hand before any rebuild", file=sys.stderr)
        return 2
    fills, _n, in_era = read_fills(pre / "out" / "trades_pre_exitpb.tsv.gz", "pre")
    population = {(e, t) for t, e, ok in zip(fills["ticker"], fills["E"], in_era) if ok}
    say(f"APLUS-PROFILE: tree {pre / 'minutes'}; population {len(population):,} (E, ticker) pairs after the edge rule; early-close sessions {len(rt.H60_EARLY_CLOSE)} listed")
    prof, tally = build_profile(pre / "minutes", rt, rt.H60_EARLY_CLOSE, population, say)
    text = profile_text(prof)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    say(f"tally: ok pairs {tally['ok']:,} - zero-volume {tally['zero']} - early-close {tally['early']} - population {tally['population']:,} = kept {tally['kept']:,} "
        f"(registered {PROFILE_TALLY})")
    say("values: " + "; ".join(f"PROFILE({m}) = {prof[m]:.6f} (pinned {v}, {'ok' if abs(prof[m] - v) <= PROFILE_TOL else 'OFF'})" for m, v in PROFILE_PINS.items()))
    say(f"monotone {bool((np.diff(prof) >= 0).all())}; PROFILE(0) = {prof[0]!r}, PROFILE(390) = {prof[-1]!r}")
    out.parent.mkdir(parents=True, exist_ok=True)
    small.mkdir(parents=True, exist_ok=True)
    partial = rt.partial_path(out)
    partial.write_bytes(text.encode("utf-8"))
    problems = profile_problems(prof) + ([] if tally == PROFILE_TALLY else [f"tally {tally} != registered {PROFILE_TALLY}"])
    if sha != PROFILE_SHA_EXPECTED:
        problems.append(f"sha256 {sha} is not the EXPECTED {PROFILE_SHA_EXPECTED}")
    if problems:
        say(f"PROFILE BUILD FAILED: {'; '.join(problems)} - left as {partial} (not a pin); WALL TIME {time.time() - T0:.0f}s")
        (small / "aplus_profile_summary.txt").write_text("\n".join(log) + "\n")
        return 3
    os.replace(partial, out)
    say(f"sha256 {sha} = EXPECTED; WROTE {out}; WALL TIME {time.time() - T0:.0f}s")
    (small / "aplus_profile_summary.txt").write_text("\n".join(log) + "\n")
    return 0


def run_verdict(args, rt) -> int:
    """`aplus-verdict`: reads both deciding verdict JSONs and prints the consequence cell, nothing else."""
    dirs = rt.h60_dirs(args)
    vp = {"pre": dirs["cb702_pre"] / "out" / f"{APLUS_TAG}_verdict_pre.json", "discovery": dirs["cb702"] / "out" / f"{APLUS_TAG}_verdict_discovery.json"}
    missing = [str(p) for p in vp.values() if not p.exists()]
    if missing:
        print(f"REFUSED: the consequence table is applied only when BOTH verdict files exist: missing {missing}", file=sys.stderr)
        return 2
    v = {k: json.loads(p.read_text()) for k, p in vp.items()}
    c = consequence(v["pre"], v["discovery"])
    rows3 = {k: {s.split("|")[0]: r for s, r in v[k].get("rows", {}).items() if s.endswith(f"|{N_DECIDES}")} for k in ("pre", "discovery")}
    nxt = None if c["record_core"] else next_registration(rows3["pre"], rows3["discovery"])
    print(f"#705 A+ CONSEQUENCE: 2017-21 {v['pre']['verdict']} (paired {v['pre']['paired']['reading']}, +grp {v['pre']['grp']['reading']}) x 2022-24 "
          f"{v['discovery']['verdict']} (paired {v['discovery']['paired']['reading']}, +grp {v['discovery']['grp']['reading']}) -> {c['cell']}: {c['why']}")
    print(f"  the shadow records the core: {c['record_core']}; records +grp beside: {c['record_grp']}"
          + ("" if c["record_core"] else f"; next registration: {nxt or 'no eligible alone row - the rating does not select on these ingredients'}"))
    if c["cell"] == "RECORD":
        print("  then: aplus-confirm --period holdout (the sealed 2025-26 read, once); PASS there -> a paper proposal to him (THE LINE)")
    return 0
