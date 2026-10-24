#!/usr/bin/env python3
"""#705 EP JOIN 01 — his stream-confirmed calls that our BREAKOUT read did not match, placed against an outcome-free EP (gap-up)
event list built on the corrected daily files. OUTCOME-FREE: no return, R, stop, exit or any bar AFTER an event day E is read for
any feature or label (E's own open and volume define the event; E's close is never read). No file or bar dated after 2024-12-31 is
kept from any era-B price file (dropped AT READ, asserted). No subagent, no DB, no network. Read-only on every input.

Why: Qullamaggie's three setups are breakouts, EPs and parabolic shorts (operator rule 2026-10-23, operator_shared_notes.md: each
was profitable for him for years; a replay that misses one is OUR implementation's defect). 294 of his 729 positive stream labels
(bought or best) matched none of our consolidation-breakout events in [s0-10, s0+20] (Track A, 01_join_labels.py). This script
asks how many of them sit on an EP day instead, and classifies the rest — counts only. The next step (an EP replay registration)
needs the minute bars of those days: the fetch list is written here.

EVERY CHOICE BELOW WAS FIXED BEFORE THE FIRST RUN (this header is the record):

EP EVENT (PRIMARY) — on session E of a ticker, ALL of:
  G  gap: open(E) >= close(E-1) x 1.09 — the live floor `MIN_GAP_PCT` = 9.0 (agents/market_intelligence/ep_detector.py:126-127,
     `_MIN_GAP_PCT_DEFAULT`; env EP_MIN_GAP_PCT; was 10.0 before 2026-08-19, docs/setups/magna53_ep.md "Gap floor"). The
     constant is re-read from the source file at run time and asserted.
  V  volume: v(E) >= 3 x the MEAN volume of the 20 sessions E-20..E-1 — the operator-reviewed "real EP day" rule he graded ten
     charts against (operator_shared_notes.md 2026-10-05; tests/fixtures/must_not_trade_charts.py:599: "open >= 9% above the prior
     close, volume >= 3x its 20-day average"); the live detector's own baseline is also 20-day (`adv_20`). ⚠ The task text said
     "k x the 50-day average": no EP rule in this repo uses 50 days, so 20-day is primary (the repo's own threshold, as the task
     directs) and the 50-day reading is a BESIDE column (`vr50_mean`), never chosen after the fact. The 20 baseline sessions must
     be CONSECUTIVE calendar sessions with v > 0 on each (era B carries 22,658 `zero_volume_underflow` rows: a zero in the baseline
     deflates the mean and manufactures a 3x); a dirty window is skipped and COUNTED. The median-based reading (historical_scan.py
     DEFAULT_MIN_RVOL 2.0 x the 20-day MEDIAN) is beside (`vr20_med`).
  P  price: RAW close(E-1) >= $5 — `MIN_PREV_CLOSE` 5.0 (ep_detector.py:191) = `cb.MIN_PRICE` 5.0 (the breakout universe, RAW not
     adjusted). Era A: `daily_raw_close.csv.gz` (one raw row per export row, asserted). Era B: adjusted x `cb.raw_factor_for`
     with the split list loaded `through=2026-10-16` (the export's last session, the runner's convention) — a 2023 bar's RAW price
     needs the splits that executed AFTER it, including 2025-26 ones. DISCLOSED as the one post-cut input (split DATES and ratios,
     not a bar, not an outcome); the number of events whose $5 verdict differs under a 2024-12-31 split cut is printed.
  L  liquidity: MEDIAN of close x volume over the 20 sessions ending E-1 >= $10M — `cb.MIN_DOLLAR_VOL` (consolidation_breakout.py:
     126, operator-signed 2026-06-15 #286), the floor the breakout read used (the task: "same universe floors as the breakout
     read"). E's own volume never enters the median. BESIDE: the EP backtester's $1M (backtester/filters.py:21
     `MIN_ADV_DOLLAR_VOLUME`) — the count of ADDITIONAL label matches it admits is printed as a decision input for the registration
     (Qullamaggie: "the best EP is a neglected stock"), never as a re-tune here.
  U  ticker ^[A-Z]{1,5}$ (`cb.UNIVERSE_TICKER_RE`); security type in {CS, ADRC} or UNKNOWN (`cb.UNIVERSE_SECURITY_TYPES`; the
     SIC file types the ~3,900 liquid names only — an untyped name is admitted, as prod and the breakout read do).
  H  history: >= 20 prior sessions (the volume window). The breakout read's 130-session floor is an RS requirement, not an EP one:
     it is a BESIDE flag (`hist130`), counted.
  X  exclusions: (ticker, E) carrying a KNOWN ADJUSTMENT / DISCONTINUOUS flag in the audit's price flags — only the two klasses the
     frozen Track A fit module consumed, `known_adjustment_event` and `discontinuous_across_known_adjustment`; every other klass
     (`gap persistent`, `reverted_*`, ...) is defined by what the bars did AFTER the date and is NOT loaded (asserted) — and
     (ticker, E) or (ticker, E-1) on an identity-break date of the G4 symbol guard (a "jump" break IS a price jump).
  The extension cap `MAX_EXTENSION_PCT` 50.0 (ep_detector.py:247: skip if close(E-1) is >= 50% above MIN(close) over the 5
  sessions ending E-1) is a chase-risk filter on OUR entry, not part of what an EP is (his ruling 2026-09-05: the GAP defines it):
  a BESIDE flag (`ext_ok`), counted. Variants printed beside the primary, each as a recount of the same join: gap >= 10%
  (Qullamaggie's "up at least 10%", operator_shared_notes 2026-10-06; the pre-08-19 live floor); vr20_med >= 2 (historical_scan);
  vr20_mean >= 10 (his "best ~10x"); vr50_mean >= 3; $1M floor; ext_ok; hist130.
  The WIDE candidate table (every clean row with gap >= 5%, all flags) is written so the sub-floor classes can be counted.

ERAS / FILES: a label's era is the Track A join's (`era` column: screen date <= 2022-01-03 -> A, else B); its symbol is the join's
  resolved `sym` (era A: 783 own / 15 refetch / 13 rename, 0 unresolved). Era A events: cb702_pre_v2/daily_closes_all.csv.gz +
  daily_raw_close.csv.gz, the whole file (2016-01-04..2022-06-30; so every era-A label's window is covered — the two files overlap
  2021-09-27..2022-06-30 and the overlap months are stated). Era B events: cb702/daily_closes_all.csv.gz with every row dated after
  2024-12-31 dropped at read (asserted); the 13 era-B labels of Jan-Mar 2022 that were `coverage none` for BREAKOUT candidates
  (first candidate E 2022-04-01) are covered here: the B file starts 2021-09-27 and the first EP-eligible E is 20 sessions later.
  EP coverage is recomputed per label from the EP-eligible E range. Calendars: era A `sessions.txt`, era B
  `spy_sessions_eraB_le_2024-12-31.txt` (the Track A files); every bar date must sit on its calendar (off-calendar bars counted).

JOIN (the 294 unmatched positive labels; the 435 breakout-matched ones beside, for the overlap): s0 = the join's label session.
  WINDOW: E in [s0 - 10, s0 + 5] sessions. Why: "I bought" an EP is said on the gap day or in the days after it (the delayed /
  fishhook entries sit inside two weeks); a label BEFORE the gap can only be anticipation of a scheduled event, so the forward
  reach is short. SIGN (the join script's): delta = idx(E) - idx(s0): > 0 = the label came BEFORE the gap day, 0 = the screen
  date IS the gap day, < 0 = AFTER it. NEAREST by |delta|; a TIE (one before, one after at the same distance) goes to the
  EARLIER E — for an EP the label is about a gap that already happened (the opposite of the breakout join's tie rule, which read
  anticipation of a line break). Reported per era: matched; position before / on / after; distinct (sym, E) events.

CLASSIFICATION of the labels still unmatched (first-match LADDER, in this order; the independent flag counts are printed too):
  (a) matched an EP event in the window;
  (b) the symbol has no row in the era's daily file;
  (c) NOT IN OUR UNIVERSE: no session of the window passes the universe floors (U, P, L, H at that session) — split by the
      component failing most often (type/regex · $5 raw · $10M median $vol · fewer than 20 prior sessions · no bar in the window);
  (d) NEAR A BREAKOUT OUTSIDE THE WINDOW: a tl event within +-60 sessions (`delta_wide_tl` of labels_joined.tsv; reused, not
      recomputed — the breakout window was [-10, +20], so this is a tl event 11-60 sessions before or 21-60 after);
  (e) PARABOLIC RUN-UP at s0: the live extension test applied at the label date — close(s0) >= 1.5 x MIN(close) over the 5
      sessions ending s0-1 (bars <= s0 only; ep_detector.py:247's shape); `run10` = close(s0) / close(s0-10) - 1 beside;
  (f) a SUB-FLOOR GAP DAY in the window: a wide-table row (gap >= 5%) of the symbol in [s0-10, s0+5] that fails G or V or P or L;
  (g) nothing: in our universe, no event of any kind near the label.
  Counts per LABEL and per distinct (sym, s0) (2023-05-19 alone carries five labels).

FETCH LIST (minute bars the EP replay needs; `ticker|date|tier|era`, the fetch_minutes.py format): tier 0 = every primary EP
  event day matched to ANY positive label (the 294 and the 435 alike, the latter flagged); tier 1 = every OTHER primary EP event
  on those same E dates, same era (the same-day control the replay compares against). CAP: if tier 0 + tier 1 exceed 5,000 pairs,
  tier 1 is sampled per date in proportion (seed 702, at least 1 per date) to bring the total to 5,000. MINUS the pairs already in
  cb702_pre_v2/minutes/_done.psv (era A) and cb702/minutes/_done.psv (era B; the three other era-B minute folders' done lists are
  strict subsets of it — union 153,809 = its own count, checked 2026-10-23), ANY status (`ok` and `empty` were both fetched); the
  done lists are read with rows dated after 2024-12-31 dropped (asserted). Era B minutes start 2022-04-01: a Jan-Mar 2022 EP day
  is a fetch by construction.

ADDED AFTER THE FIRST RUN (2026-10-23; descriptive breakdowns only — no rule of the event list, the join or the ladder changed, and
  every count above them is byte-identical between the two runs): (i) the remainder (g) is split by the SIC `typed` flag — the funds
  (TNA, QQQ, XOP, SOXL ...) are UNTYPED in the SIC file and ADMITTED by `universe_ok` as unknown, exactly as the breakout read admitted
  them; the breakout read labelled them "untyped = fund proxy", so the same split is printed here; (ii) a WIDE beside read like the
  breakout join's: the nearest primary EP event of the symbol within [s0-60, s0+60] (histogram), and the count of labels with an EP
  event 11-40 sessions BEFORE the label (a post-EP base, the delayed-EP / fishhook family) — the first run's histogram piled up at the
  window's back edge (-10..-6), so the edge is read, not moved.

OUTPUTS (/Users/alvinfung/apollo_data/cb702/qm_streams/ep_join_1023/): ep_events_{A,B}.tsv.gz (primary events + beside flags),
  ep_wide_{A,B}.tsv.gz (every clean gap >= 5% row with flags), labels_ep_joined.tsv (729 positive labels: EP join + ladder class),
  ep_minute_fetch_list.psv; the printout beside this script as 01_ep_join.txt. Pins (sha256) of every input and this file last.

Run:  python3 scripts/probes/_705_ep_join_1023/01_ep_join.py > scripts/probes/_705_ep_join_1023/01_ep_join.txt
"""
from __future__ import annotations

import gzip
import hashlib
import os
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from agents.market_intelligence import consolidation_breakout as cb      # noqa: E402  (constants + raw_factor_for; read-only)
from scripts.probes._cb_backtest import runner as R                     # noqa: E402  (load_splits / load_sic; read-only)

DATA = "/Users/alvinfung/apollo_data"
A = f"{DATA}/cb702_pre_v2"
B = f"{DATA}/cb702"
TA = f"{B}/qm_streams/track_a_1023"
OUT = f"{B}/qm_streams/ep_join_1023"
FILES = {
    "labels_joined": f"{TA}/labels_joined.tsv",
    "daily_A": f"{A}/daily_closes_all.csv.gz",
    "raw_A": f"{A}/daily_raw_close.csv.gz",
    "daily_B": f"{B}/daily_closes_all.csv.gz",
    "splits_B": f"{B}/cb702_splits.psv",
    "cal_A": f"{A}/sessions.txt",
    "cal_B": f"{TA}/spy_sessions_eraB_le_2024-12-31.txt",
    "sic_A": f"{A}/cb702_sic.psv",
    "sic_B": f"{B}/cb702_sic.psv",
    "flags_A": f"{A}/audit_1023/price/A_flags.tsv",
    "flags_B": f"{DATA}/audit_runs_2026-10-23/B_flags.tsv",
    "guard_A": f"{A}/audit_1023/universe/symbol_guard_A.tsv",
    "guard_B": os.path.join(REPO, "scripts", "backtest_data_audit", "runs_2026-10-23", "universe", "symbol_guard_B.tsv"),
    "done_A": f"{A}/minutes/_done.psv",
    "done_B": f"{B}/minutes/_done.psv",
    "ep_detector": os.path.join(REPO, "agents", "market_intelligence", "ep_detector.py"),
    "historical_scan": os.path.join(REPO, "agents", "market_intelligence", "backtester", "historical_scan.py"),
    "bt_filters": os.path.join(REPO, "agents", "market_intelligence", "backtester", "filters.py"),
}

CUT_B = "2024-12-31"
EXPORT_B_LAST = date(2026, 10, 16)          # the era-B export's last session: the split list is loaded through it (header, P)
GAP = 0.09                                  # G  (ep_detector _MIN_GAP_PCT_DEFAULT, asserted below)
GAP_QM = 0.10                               # beside: Qullamaggie / pre-08-19 live / historical_scan DEFAULT_MIN_GAP_PCT
VR = 3.0                                    # V  (the 10-05 real-EP-day rule; 20-session MEAN)
VR_MED_HS = 2.0                             # beside: historical_scan DEFAULT_MIN_RVOL on the 20-day MEDIAN
VR_QM_BEST = 10.0                           # beside: his "best ~10x"
VOL_WIN = 20
VOL_WIN_50 = 50
MIN_PRICE = cb.MIN_PRICE                    # P  5.0 RAW
MIN_DV = cb.MIN_DOLLAR_VOL                  # L  10,000,000 median $vol
MIN_DV_BT = 1_000_000.0                     # beside: backtester/filters.py MIN_ADV_DOLLAR_VOLUME (asserted below)
EXT_MAX = 0.50                              # beside: MAX_EXTENSION_PCT 50.0 (asserted below)
HIST130 = cb.MIN_HISTORY                    # beside flag
WIDE_GAP = 0.05                             # the wide candidate table's floor
W_BACK, W_FWD = 10, 5                       # the join window, sessions
FETCH_CAP = 5000
SEED = 702
FLAG_KLASSES = {"known_adjustment_event", "discontinuous_across_known_adjustment"}
ERA_A_LAST_SCREEN = "2022-01-03"
ADMIT_TYPES = set(cb.UNIVERSE_SECURITY_TYPES) | {""}
TICK_RE = re.compile(r"^[A-Z]{1,5}$")
assert cb.UNIVERSE_TICKER_RE.pattern == "[A-Z]{1,5}" and cb.DOLLAR_VOL_WINDOW == VOL_WIN


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def src_const(path: str, name: str) -> float:
    txt = open(path).read()
    m = re.search(rf"^{name}\s*=\s*([0-9_.]+)", txt, re.M)
    assert m, f"{name} not found in {path}"
    return float(m.group(1).replace("_", ""))


def read_cal(path: str, cut: str | None = None) -> np.ndarray:
    d = [ln.strip() for ln in open(path) if ln.strip()]
    if cut:
        d = [x for x in d if x <= cut]
    arr = np.array(sorted(d), dtype="U10")
    assert len(np.unique(arr)) == len(arr)
    return arr


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100.0 * a / b:.1f}%)" if b else f"{a}/0"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# daily files -> the wide candidate table with every flag
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def load_daily(era: str, cal: np.ndarray) -> tuple[pd.DataFrame, dict]:
    """Sorted (ticker, d) bars with a calendar index; era B cut at CUT_B at read. Returns the frame and read counters."""
    cnt = Counter()
    path = FILES[f"daily_{era}"]
    cols = ["ticker", "d", "o", "h", "l", "c", "v"]
    parts = []
    for ch in pd.read_csv(path, header=None, names=cols, usecols=["ticker", "d", "o", "c", "v"],
                          dtype={"ticker": str, "d": str, "o": "float64", "c": "float64", "v": "float64"},
                          keep_default_na=False, chunksize=2_000_000):
        cnt["rows_read"] += len(ch)
        if era == "B":
            m = ch.d <= CUT_B
            cnt["rows_dropped_after_cut"] += int((~m).sum())
            ch = ch[m]
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    del parts
    if era == "B":
        assert df.d.max() <= CUT_B, df.d.max()
    ci = np.searchsorted(cal, df.d.to_numpy(dtype="U10"))
    on_cal = (ci < len(cal)) & (cal[np.minimum(ci, len(cal) - 1)] == df.d.to_numpy(dtype="U10"))
    cnt["rows_off_calendar_dropped"] = int((~on_cal).sum())
    df = df[on_cal].copy()
    df["ci"] = ci[on_cal].astype(np.int64)
    df.sort_values(["ticker", "ci"], inplace=True, kind="mergesort")
    df.reset_index(drop=True, inplace=True)
    dup = df.duplicated(["ticker", "ci"]).sum()
    assert dup == 0, f"era {era}: {dup} duplicate (ticker, date) rows"
    cnt["rows_kept"] = len(df)
    cnt["symbols"] = int(df.ticker.nunique())
    return df, cnt


def attach_raw_A(df: pd.DataFrame) -> int:
    """Era A: the RAW close per export row from daily_raw_close.csv.gz (asserted to cover every row exactly once)."""
    raw = pd.read_csv(FILES["raw_A"], header=None, names=["ticker", "d", "raw_c"], dtype={"ticker": str, "d": str, "raw_c": "float64"},
                      keep_default_na=False)
    raw.sort_values(["ticker", "d"], inplace=True, kind="mergesort")
    raw.reset_index(drop=True, inplace=True)
    assert len(raw) == len(df), (len(raw), len(df))
    assert (raw.ticker.to_numpy() == df.ticker.to_numpy()).all() and (raw.d.to_numpy() == df.d.to_numpy()).all(), "raw rows != export rows"
    assert np.isfinite(raw.raw_c.to_numpy()).all() and (raw.raw_c.to_numpy() > 0).all()
    df["raw_c"] = raw.raw_c.to_numpy()
    return len(raw)


def wide_table(era: str, df: pd.DataFrame, cal: np.ndarray, sectype: dict, flagged: set, breaks: dict, splits: dict | None,
               splits_cut: dict | None) -> tuple[pd.DataFrame, dict]:
    """Every row with a clean 20-session baseline and gap >= WIDE_GAP, with every primary term and beside flag as columns."""
    cnt = Counter()
    t = df.ticker.to_numpy()
    ci = df.ci.to_numpy()
    o = df.o.to_numpy()
    c = df.c.to_numpy()
    v = df.v.to_numpy()
    n = len(df)
    # group starts
    new = np.ones(n, dtype=bool)
    new[1:] = t[1:] != t[:-1]
    g0 = np.maximum.accumulate(np.where(new, np.arange(n), 0))
    hist = np.arange(n) - g0                                  # prior rows of the same ticker
    # prior bar = the previous row, which must be the previous calendar session
    prev_ok = (hist >= 1)
    prev_ci = np.empty(n, dtype=np.int64)
    prev_ci[0] = -99
    prev_ci[1:] = ci[:-1]
    prev_ok &= (ci - prev_ci) == 1
    prev_c = np.empty(n)
    prev_c[0] = np.nan
    prev_c[1:] = c[:-1]
    prev_ok &= np.isfinite(prev_c) & (prev_c > 0)
    cnt["rows_with_prior_bar_not_prev_session"] = int(((hist >= 1) & ((ci - prev_ci) != 1)).sum())
    # 20-session baseline: rows i-20..i-1, consecutive sessions, all v > 0
    cv = np.concatenate([[0.0], np.cumsum(v)])
    cz = np.concatenate([[0], np.cumsum((v <= 0) | ~np.isfinite(v))])
    idx = np.arange(n)
    has20 = hist >= VOL_WIN
    i20 = np.where(has20, idx - VOL_WIN, 0)
    consec20 = has20 & ((ci - ci[i20]) == VOL_WIN)
    zeros20 = cz[idx] - cz[i20]                               # zero-volume bars among rows i-20..i-1
    clean20 = consec20 & (zeros20 == 0)
    mean20 = np.where(has20, (cv[idx] - cv[i20]) / VOL_WIN, np.nan)
    has50 = hist >= VOL_WIN_50
    i50 = np.where(has50, idx - VOL_WIN_50, 0)
    consec50 = has50 & ((ci - ci[i50]) == VOL_WIN_50)
    zeros50 = cz[idx] - cz[i50]
    mean50 = np.where(consec50 & (zeros50 == 0), (cv[idx] - cv[i50]) / VOL_WIN_50, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        gap = o / prev_c - 1.0
        vr20 = v / mean20
        vr50 = v / mean50
    valid = prev_ok & (o > 0) & (v > 0) & np.isfinite(gap)
    cnt["rows_gap_ge_wide_any"] = int((valid & (gap >= WIDE_GAP)).sum())
    cnt["rows_gap_ge_wide_dirty_or_short_baseline"] = int((valid & (gap >= WIDE_GAP) & ~clean20).sum())
    cnt["rows_gap_ge_9_vr_ge_3_but_dirty_baseline"] = int((valid & (gap >= GAP) & has20 & ~clean20 & (v >= VR * np.nan_to_num(mean20, nan=np.inf))).sum())
    sel = np.flatnonzero(valid & (gap >= WIDE_GAP) & clean20)
    cnt["wide_rows"] = len(sel)
    # per-candidate: 20-session medians (volume, $vol) ending E-1, extension, raw prev close, type, flags, breaks
    med_v = np.empty(len(sel))
    med_dv = np.empty(len(sel))
    ext5 = np.empty(len(sel))
    dv = c * v
    for k, i in enumerate(sel):
        a = i - VOL_WIN
        med_v[k] = np.median(v[a:i])
        med_dv[k] = np.median(dv[a:i])
        ext5[k] = prev_c[i] / np.min(c[i - 5:i]) - 1.0        # close(E-1) vs MIN(close) over the 5 sessions ending E-1
    tk = t[sel]
    if era == "A":
        raw_prev = df.raw_c.to_numpy()[sel - 1]
        raw_prev_cut = raw_prev
    else:
        prev_dates = [date.fromisoformat(x) for x in cal[prev_ci[sel]]]
        raw_prev = np.array([prev_c[i] * cb.raw_factor_for(pd_, splits.get(tk[k], [])) for k, (i, pd_) in enumerate(zip(sel, prev_dates))])
        raw_prev_cut = np.array([prev_c[i] * cb.raw_factor_for(pd_, splits_cut.get(tk[k], [])) for k, (i, pd_) in enumerate(zip(sel, prev_dates))])
    typ = np.array([sectype.get(x, "") for x in tk], dtype=object)
    E = cal[ci[sel]]
    Em1 = cal[prev_ci[sel]]
    W = pd.DataFrame({
        "ticker": tk, "E": E, "D": Em1, "iE": ci[sel], "hist_n": hist[sel],
        "prev_close_adj": prev_c[sel], "prev_close_raw": raw_prev, "open": o[sel], "gap_pct": 100.0 * gap[sel],
        "vol_E": v[sel], "mean_v20": mean20[sel], "med_v20": med_v, "vr20_mean": vr20[sel], "vr20_med": v[sel] / med_v,
        "vr50_mean": vr50[sel], "med_dv20": med_dv, "ext5_pct": 100.0 * ext5, "sectype": typ,
    })
    W["ok_gap"] = W.gap_pct >= 100.0 * GAP - 1e-9
    W["ok_vol"] = W.vr20_mean >= VR - 1e-12
    W["ok_price"] = W.prev_close_raw >= MIN_PRICE
    W["ok_liq"] = W.med_dv20 >= MIN_DV
    W["ok_tick"] = W.ticker.map(lambda x: bool(TICK_RE.match(x)))
    W["ok_type"] = W.sectype.isin(ADMIT_TYPES)
    W["flag_adj"] = [(a_, b_) in flagged for a_, b_ in zip(W.ticker, W.E)]
    W["flag_adj_Dm1"] = [(a_, b_) in flagged for a_, b_ in zip(W.ticker, W.D)]
    W["break_on_E_or_D"] = [bool(breaks.get(a_) and (b_ in breaks[a_] or c_ in breaks[a_])) for a_, b_, c_ in zip(W.ticker, W.E, W.D)]
    W["ok_excl"] = ~W.flag_adj & ~W.break_on_E_or_D
    W["primary"] = W.ok_gap & W.ok_vol & W.ok_price & W.ok_liq & W.ok_tick & W.ok_type & W.ok_excl
    # beside flags
    W["b_gap10"] = W.gap_pct >= 100.0 * GAP_QM - 1e-9
    W["b_vrmed2"] = W.vr20_med >= VR_MED_HS
    W["b_vr10"] = W.vr20_mean >= VR_QM_BEST
    W["b_vr50_3"] = W.vr50_mean >= VR
    W["b_liq1m"] = W.med_dv20 >= MIN_DV_BT
    W["b_ext_ok"] = W.ext5_pct < 100.0 * EXT_MAX
    W["b_hist130"] = W.hist_n >= HIST130
    W["b_price_raw_cut_differs"] = (raw_prev_cut >= MIN_PRICE) != (raw_prev >= MIN_PRICE)
    W["era"] = era
    cnt["primary_events"] = int(W.primary.sum())
    cnt["primary_excl_adj_flag"] = int((W.ok_gap & W.ok_vol & W.ok_price & W.ok_liq & W.ok_tick & W.ok_type & W.flag_adj).sum())
    cnt["primary_excl_identity_break"] = int((W.ok_gap & W.ok_vol & W.ok_price & W.ok_liq & W.ok_tick & W.ok_type & ~W.flag_adj & W.break_on_E_or_D).sum())
    cnt["primary_if_liq_1m"] = int((W.ok_gap & W.ok_vol & W.ok_price & W.b_liq1m & W.ok_tick & W.ok_type & W.ok_excl).sum())
    cnt["primary_price_verdict_differs_under_2024_split_cut"] = int((W.primary & W.b_price_raw_cut_differs).sum()) if era == "B" else 0
    return W, cnt


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# universe status per (ticker, session) for the label symbols (the ladder's rung c)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def universe_rows(df: pd.DataFrame, syms: set, era: str, sectype: dict, splits: dict | None) -> pd.DataFrame:
    sub = df[df.ticker.isin(syms)].copy()
    out = []
    for tkr, g in sub.groupby("ticker", sort=False):
        c = g.c.to_numpy()
        v = g.v.to_numpy()
        ci = g.ci.to_numpy()
        n = len(g)
        dv = c * v
        med = np.full(n, np.nan)
        for i in range(VOL_WIN - 1, n):
            if ci[i] - ci[i - VOL_WIN + 1] == VOL_WIN - 1:
                med[i] = np.median(dv[i - VOL_WIN + 1:i + 1])
        if era == "A":
            raw = g.raw_c.to_numpy()
        else:
            sp = splits.get(tkr, [])
            raw = np.array([c[i] * cb.raw_factor_for(date.fromisoformat(d), sp) for i, d in enumerate(g.d)])
        ext5 = np.full(n, np.nan)
        run10 = np.full(n, np.nan)
        for i in range(5, n):
            if ci[i] - ci[i - 5] == 5:
                ext5[i] = c[i] / np.min(c[i - 5:i]) - 1.0
        for i in range(10, n):
            if ci[i] - ci[i - 10] == 10:
                run10[i] = c[i] / c[i - 10] - 1.0
        typ = sectype.get(tkr, "")
        out.append(pd.DataFrame({"ticker": tkr, "ci": ci, "hist_n": np.arange(n), "raw_c": raw, "med_dv20": med, "ext5": ext5, "run10": run10,
                                 "ok_tick": bool(TICK_RE.match(tkr)), "ok_type": typ in ADMIT_TYPES}))
    U = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["ticker", "ci"])
    U["ok_price"] = U.raw_c >= MIN_PRICE
    U["ok_liq"] = U.med_dv20 >= MIN_DV
    U["ok_hist"] = U.hist_n >= VOL_WIN
    U["ok"] = U.ok_tick & U.ok_type & U.ok_price & U.ok_liq & U.ok_hist
    return U


# ═══════════════════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    print("# #705 EP JOIN 01 (outcome-free). Every choice fixed in the script header before the first run.")
    print(f"# EP event (primary): open(E) >= close(E-1) x {1 + GAP:.2f} AND v(E) >= {VR:.0f} x mean v(E-20..E-1) AND raw close(E-1) >= ${MIN_PRICE:.0f}"
          f" AND median $vol(E-20..E-1) >= ${MIN_DV / 1e6:.0f}M AND ticker/type universe AND no adjustment flag / identity break on E")
    print(f"# join window E in [s0-{W_BACK}, s0+{W_FWD}] sessions; delta = idx(E) - idx(s0): >0 label BEFORE the gap day, 0 ON it, <0 AFTER it; tie -> the earlier E")

    # the cited constants, re-read from the source files
    assert src_const(FILES["ep_detector"], "_MIN_GAP_PCT_DEFAULT") == 100.0 * GAP
    assert src_const(FILES["ep_detector"], "MIN_PREV_CLOSE") == MIN_PRICE
    assert src_const(FILES["ep_detector"], "MAX_EXTENSION_PCT") == 100.0 * EXT_MAX
    assert src_const(FILES["historical_scan"], "DEFAULT_MIN_GAP_PCT") == 100.0 * GAP_QM
    assert src_const(FILES["historical_scan"], "DEFAULT_MIN_RVOL") == VR_MED_HS
    assert src_const(FILES["bt_filters"], "MIN_ADV_DOLLAR_VOLUME") == MIN_DV_BT
    print(f"- constants asserted against source: ep_detector _MIN_GAP_PCT_DEFAULT {100 * GAP:.1f} · MIN_PREV_CLOSE {MIN_PRICE} · MAX_EXTENSION_PCT {100 * EXT_MAX:.0f}"
          f" · cb.MIN_PRICE {cb.MIN_PRICE} · cb.MIN_DOLLAR_VOL {cb.MIN_DOLLAR_VOL:,.0f} · cb.MIN_HISTORY {cb.MIN_HISTORY}"
          f" · historical_scan gap {100 * GAP_QM:.0f} / rvol {VR_MED_HS} · backtester MIN_ADV_DOLLAR_VOLUME {MIN_DV_BT:,.0f}")

    # ------------------------------------------------------------------ labels
    J = pd.read_csv(FILES["labels_joined"], sep="\t", dtype=str, keep_default_na=False)
    P = J[(J.is_bought == "1") | (J.is_best == "1")].copy()
    P["bo_matched"] = P.E_tl.ne("")
    assert len(P) == 729 and int((~P.bo_matched).sum()) == 294, (len(P), int((~P.bo_matched).sum()))
    print(f"\n## 0. Labels: positive (bought or best) {len(P)} | breakout-matched {int(P.bo_matched.sum())} | UNMATCHED {int((~P.bo_matched).sum())}"
          f" (era A {int(((~P.bo_matched) & (P.era == 'A')).sum())}, era B {int(((~P.bo_matched) & (P.era == 'B')).sum())})")
    assert (P.loc[P.era == "A", "screen_date"] <= ERA_A_LAST_SCREEN).all() and (P.loc[P.era == "B", "screen_date"] > ERA_A_LAST_SCREEN).all()

    cal = {"A": read_cal(FILES["cal_A"]), "B": read_cal(FILES["cal_B"], CUT_B)}
    assert cal["B"][-1] <= CUT_B and cal["A"][-1] == "2022-06-30"
    print(f"- calendars: A {len(cal['A'])} sessions {cal['A'][0]}..{cal['A'][-1]} | B {len(cal['B'])} sessions {cal['B'][0]}..{cal['B'][-1]}"
          f" | the two daily files overlap {cal['B'][0]}..{cal['A'][-1]}")

    # ------------------------------------------------------------------ side inputs
    sectype = {}
    for e in ("A", "B"):
        _, typ = R.load_sic(Path(FILES[f"sic_{e}"]))
        sectype[e] = typ
    flagged = {}
    for e in ("A", "B"):
        f = pd.read_csv(FILES[f"flags_{e}"], sep="\t", usecols=["klass", "ticker", "date"], dtype=str, keep_default_na=False)
        f = f[f.klass.isin(FLAG_KLASSES)]
        assert set(f.klass) <= FLAG_KLASSES
        if e == "B":
            f = f[f.date <= CUT_B]
        flagged[e] = set(zip(f.ticker, f.date))
    breaks = {}
    for e in ("A", "B"):
        g = pd.read_csv(FILES[f"guard_{e}"], sep="\t", dtype=str, keep_default_na=False)
        d = defaultdict(set)
        for tkr, br in zip(g.symbol, g.breaks):
            for item in br.split(";"):
                if ":" in item:
                    d[tkr].add(item.split(":")[0])
        breaks[e] = d
    print(f"- side inputs: typed symbols A {len(sectype['A'])} / B {len(sectype['B'])} (untyped admitted) | adjustment/discontinuous flags loaded"
          f" (only klasses {sorted(FLAG_KLASSES)}) A {len(flagged['A'])} / B {len(flagged['B'])} pairs | identity-break symbols A {len(breaks['A'])} / B {len(breaks['B'])}")
    splits_B = R.load_splits(Path(FILES["splits_B"]), through=EXPORT_B_LAST)
    splits_B_cut = R.load_splits(Path(FILES["splits_B"]), through=date.fromisoformat(CUT_B))
    n_sp = sum(len(v) for v in splits_B.values())
    n_sp_cut = sum(len(v) for v in splits_B_cut.values())
    print(f"- era B split list: {n_sp} splits through {EXPORT_B_LAST} (the export's last session — DISCLOSED post-cut input: split dates/ratios only);"
          f" {n_sp - n_sp_cut} of them execute after {CUT_B}")

    # ------------------------------------------------------------------ events per era
    W = {}
    U = {}
    label_syms = {e: set(P.loc[P.era == e, "sym"]) for e in ("A", "B")}
    for e in ("A", "B"):
        df, cnt = load_daily(e, cal[e])
        if e == "A":
            attach_raw_A(df)
        print(f"\n## 1{e}. Era {e} daily file: {dict(cnt)}")
        w, c2 = wide_table(e, df, cal[e], sectype[e], flagged[e], breaks[e], splits_B if e == "B" else None, splits_B_cut if e == "B" else None)
        print(f"- wide table + primary: {dict(c2)}")
        W[e] = w
        U[e] = universe_rows(df, label_syms[e], e, sectype[e], splits_B if e == "B" else None)
        del df
        prim = w[w.primary]
        if e == "B":
            assert prim.E.max() <= CUT_B and w.E.max() <= CUT_B
        print(f"- PRIMARY EP events: {len(prim):,} on {prim.E.nunique()} days, {prim.ticker.nunique()} symbols; E range {prim.E.min()}..{prim.E.max()};"
              f" per year {dict(sorted(Counter(prim.E.str[:4]).items()))}; median per day {float(prim.groupby('E').size().median()):.0f}")
        print(f"- beside, within the primary events: gap >= 10% {int(prim.b_gap10.sum())} | vr20_med >= 2 {int(prim.b_vrmed2.sum())} | vr20_mean >= 10 {int(prim.b_vr10.sum())}"
              f" | vr50_mean >= 3 {int(prim.b_vr50_3.sum())} (vr50 missing {int(prim.vr50_mean.isna().sum())}) | ext_ok (<50%) {int(prim.b_ext_ok.sum())} | hist >= 130 {int(prim.b_hist130.sum())}")
        print(f"- the $1M floor instead of $10M would admit {c2['primary_if_liq_1m'] - c2['primary_events']:,} more events ({c2['primary_if_liq_1m']:,} total)")
        w.to_csv(f"{OUT}/ep_wide_{e}.tsv.gz", sep="\t", index=False, float_format="%.6g")
        prim.to_csv(f"{OUT}/ep_events_{e}.tsv.gz", sep="\t", index=False, float_format="%.6g")

    # ------------------------------------------------------------------ the join
    print(f"\n## 2. Join of the positive labels to EP events (window [s0-{W_BACK}, s0+{W_FWD}]; nearest |delta|, tie -> earlier E)")
    ev = {}          # (era, variant) -> {ticker: (iE array, row positions)}

    def index_events(e: str, mask: pd.Series, name: str):
        g = W[e][mask]
        d = {}
        for tkr, gg in g.groupby("ticker", sort=False):
            gg = gg.sort_values("iE")
            d[tkr] = (gg.iE.to_numpy(), gg.index.to_numpy())
        ev[(e, name)] = d

    VARIANTS = {
        "primary": lambda w: w.primary,
        "gap10": lambda w: w.primary & w.b_gap10,
        "vrmed2": lambda w: w.ok_gap & w.b_vrmed2 & w.ok_price & w.ok_liq & w.ok_tick & w.ok_type & w.ok_excl,
        "vr10": lambda w: w.primary & w.b_vr10,
        "vr50_3": lambda w: w.ok_gap & w.b_vr50_3 & w.ok_price & w.ok_liq & w.ok_tick & w.ok_type & w.ok_excl,
        "liq1m": lambda w: w.ok_gap & w.ok_vol & w.ok_price & w.b_liq1m & w.ok_tick & w.ok_type & w.ok_excl,
        "ext_ok": lambda w: w.primary & w.b_ext_ok,
        "hist130": lambda w: w.primary & w.b_hist130,
        "subfloor": lambda w: w.ok_tick & w.ok_type & w.ok_excl & ~(w.ok_gap & w.ok_vol & w.ok_price & w.ok_liq),   # rung (f)
    }
    for e in ("A", "B"):
        for name, fn in VARIANTS.items():
            index_events(e, fn(W[e]), name)
    ep_range = {e: (int(W[e].loc[W[e].primary, "iE"].min()), int(W[e].loc[W[e].primary, "iE"].max())) for e in ("A", "B")}

    def nearest(e: str, name: str, sym: str, i0: int, back: int = W_BACK, fwd: int = W_FWD):
        arr = ev[(e, name)].get(sym)
        if arr is None:
            return None
        ie, pos = arr
        d = ie - i0
        m = (d >= -back) & (d <= fwd)
        if not m.any():
            return None
        dd, pp = d[m], pos[m]
        order = np.lexsort((dd, np.abs(dd)))         # |delta| ascending, then the EARLIER E (smaller delta) first on a tie
        return int(dd[order[0]]), int(pp[order[0]]), int(m.sum())

    syms_in_file = {e: set(U[e].ticker) for e in ("A", "B")}       # U holds every row of the label symbols present in the era's file
    rows = []
    for L in P.itertuples(index=False):
        e = L.era
        c_ = cal[e]
        i0 = int(np.searchsorted(c_, L.s0, "right")) - 1
        assert i0 >= 0 and c_[i0] == L.s0, (L.sym, L.s0)
        lo, hi = i0 - W_BACK, i0 + W_FWD
        emin, emax = ep_range[e]
        cov = "none" if (hi < emin or lo > emax) else ("full" if (lo >= emin and hi <= emax) else "partial")
        rec = dict(frame_id=L.frame_id, screen_ticker=L.screen_ticker, sym=L.sym, screen_date=L.screen_date, s0=L.s0, era=e, grade=L.grade,
                   is_bought=int(L.is_bought), is_best=int(L.is_best), bo_matched=int(L.bo_matched), delta_tl=L.delta_tl, E_tl=L.E_tl,
                   delta_wide_tl=L.delta_wide_tl, ep_coverage=cov, typed=int(L.typed))
        for name in VARIANTS:
            nb = nearest(e, name, L.sym, i0)
            rec[f"m_{name}"] = int(nb is not None)
            if name == "primary":
                rec["delta_ep"] = nb[0] if nb else ""
                rec["E_ep"] = W[e].at[nb[1], "E"] if nb else ""
                rec["n_win_ep"] = nb[2] if nb else 0
                if nb:
                    r = W[e].loc[nb[1]]
                    for col in ("gap_pct", "vr20_mean", "vr20_med", "vr50_mean", "med_dv20", "ext5_pct", "hist_n", "prev_close_raw", "sectype"):
                        rec[f"ep_{col}"] = r[col]
            if name == "primary":                       # added after the first run: the wide beside read (+-60) and the post-EP flag
                nw = nearest(e, name, L.sym, i0, back=60, fwd=60)
                rec["delta_ep_wide60"] = nw[0] if nw else ""
                npost = nearest(e, name, L.sym, i0, back=40, fwd=-11)
                rec["ep_11_40_before"] = int(npost is not None)
            if name == "subfloor":
                rec["delta_subfloor"] = nb[0] if nb else ""
                rec["E_subfloor"] = W[e].at[nb[1], "E"] if nb else ""
                if nb:
                    r = W[e].loc[nb[1]]
                    rec["subfloor_fail"] = ",".join(k for k, ok in (("gap", r.ok_gap), ("vol", r.ok_vol), ("price", r.ok_price), ("liq", r.ok_liq)) if not ok)
                    rec["subfloor_gap_pct"] = r.gap_pct
                    rec["subfloor_vr20"] = r.vr20_mean
        # universe state in the window (rung c) + parabolic (rung e)
        u = U[e]
        uw = u[(u.ticker == L.sym) & (u.ci >= lo) & (u.ci <= hi)]
        rec["uni_rows_in_window"] = len(uw)
        rec["uni_ok_any"] = int(bool(uw.ok.any())) if len(uw) else 0
        if len(uw) and not uw.ok.any():
            fails = Counter()
            for col, nm in (("ok_tick", "ticker_regex"), ("ok_type", "security_type"), ("ok_price", "raw_price_lt_5"), ("ok_liq", "median_dollar_vol_lt_10M"), ("ok_hist", "under_20_sessions_history")):
                fails[nm] = int((~uw[col]).sum())
            rec["uni_fail_reason"] = fails.most_common(1)[0][0]
            rec["uni_fail_all"] = ";".join(f"{k}:{v_}" for k, v_ in fails.items() if v_)
        else:
            rec["uni_fail_reason"] = "" if len(uw) else "no_bar_in_window"
            rec["uni_fail_all"] = ""
        u0 = u[(u.ticker == L.sym) & (u.ci == i0)]
        rec["ext5_s0_pct"] = float(100.0 * u0.ext5.iloc[0]) if len(u0) and np.isfinite(u0.ext5.iloc[0]) else ""
        rec["run10_s0_pct"] = float(100.0 * u0.run10.iloc[0]) if len(u0) and np.isfinite(u0.run10.iloc[0]) else ""
        rec["sym_in_file"] = int(L.sym in syms_in_file[e])
        rows.append(rec)
    X = pd.DataFrame(rows)

    # the ladder (first match), on the 294
    def ladder(r) -> str:
        if r.m_primary:
            return "a_EP_matched"
        if not r.sym_in_file:
            return "b_symbol_not_in_file"
        if r.uni_rows_in_window == 0 or not r.uni_ok_any:
            return "c_not_in_universe"
        if r.delta_wide_tl != "":
            return "d_breakout_outside_window"
        if r.ext5_s0_pct != "" and float(r.ext5_s0_pct) >= 100.0 * EXT_MAX:
            return "e_parabolic_runup"
        if r.m_subfloor:
            return "f_subfloor_gap_day"
        return "g_nothing"

    X["ladder"] = X.apply(ladder, axis=1)
    X.to_csv(f"{OUT}/labels_ep_joined.tsv", sep="\t", index=False)
    Un = X[X.bo_matched == 0]
    Mt = X[X.bo_matched == 1]

    for e in ("A", "B"):
        g = Un[Un.era == e]
        print(f"- era {e} unmatched positive labels n = {len(g)} | EP coverage {dict(Counter(g.ep_coverage))} | EP-eligible E range {cal[e][ep_range[e][0]]}..{cal[e][ep_range[e][1]]}")

    def position(d: pd.Series, title: str):
        d = d[d != ""].astype(int)
        n = len(d)
        if n == 0:
            print(f"- {title}: n = 0")
            return
        print(f"- {title}: n = {n} | label BEFORE the gap day (delta >= +1) {int((d >= 1).sum())} | ON it (0) {int((d == 0).sum())} | AFTER it (delta <= -1) {int((d <= -1).sum())}"
              f" | median delta {float(d.median()):+.1f} | histogram (delta: n) " + " ".join(f"{k:+d}:{v_}" for k, v_ in sorted(Counter(d).items())))

    print("\n### 2a. The 294 UNMATCHED positive labels against PRIMARY EP events")
    for e in ("A", "B"):
        g = Un[Un.era == e]
        m = g[g.m_primary == 1]
        print(f"- era {e}: matched to an EP event {pct(len(m), len(g))} | distinct (sym, E) events {len(m.drop_duplicates(['sym', 'E_ep']))} | labels with > 1 event in the window {int((g.n_win_ep > 1).sum())}"
              f" | bought {int((m.is_bought == 1).sum())} · best {int((m.is_best == 1).sum())}")
        position(m.delta_ep, f"era {e} position of the label vs the EP day")
        if len(m):
            print(f"    matched events' gap %: median {float(m.ep_gap_pct.median()):.1f} (quartiles {float(m.ep_gap_pct.quantile(.25)):.1f}..{float(m.ep_gap_pct.quantile(.75)):.1f})"
                  f" | vr20_mean median {float(m.ep_vr20_mean.median()):.1f} | median $vol20 median ${float(m.ep_med_dv20.median()) / 1e6:.0f}M"
                  f" | ext5 >= 50% (would fail the live extension cap) {int((m.ep_ext5_pct >= 100 * EXT_MAX).sum())} | hist < 130 {int((m.ep_hist_n < HIST130).sum())}")
            print(f"    matched (sym, E, delta): " + ", ".join(f"{s}@{E_}({int(d):+d})" for s, E_, d in m.sort_values(['E_ep', 'sym'])[['sym', 'E_ep', 'delta_ep']].drop_duplicates().itertuples(index=False)))

    print("\n### 2b. Variants beside (the same join, the event set re-defined; per era: matched labels of the 294)")
    hdr = ["primary", "gap10", "vrmed2", "vr10", "vr50_3", "liq1m", "ext_ok", "hist130"]
    for e in ("A", "B"):
        g = Un[Un.era == e]
        print(f"- era {e} (n = {len(g)}): " + " | ".join(f"{h} {int(g[f'm_{h}'].sum())}" for h in hdr)
              + f" | the $1M floor admits {int(g.m_liq1m.sum()) - int(g.m_primary.sum())} more labels than $10M")

    print("\n### 2c. Overlap beside: the 435 BREAKOUT-MATCHED positive labels that also have a primary EP event in the EP window")
    for e in ("A", "B"):
        g = Mt[Mt.era == e]
        m = g[g.m_primary == 1]
        print(f"- era {e}: {pct(len(m), len(g))} | distinct events {len(m.drop_duplicates(['sym', 'E_ep']))}; of those, EP day == our breakout day E_tl {int((m.E_ep == m.E_tl).sum())}")

    print("\n## 3. CLASSIFICATION LADDER of the 294 (first match, in the header's order) — per label and per distinct (sym, s0)")
    order = ["a_EP_matched", "b_symbol_not_in_file", "c_not_in_universe", "d_breakout_outside_window", "e_parabolic_runup", "f_subfloor_gap_day", "g_nothing"]
    for e in ("A", "B"):
        g = Un[Un.era == e]
        gd = g.drop_duplicates(["sym", "s0"])
        cl = Counter(g.ladder)
        cd = Counter(gd.ladder)
        print(f"- era {e} (labels {len(g)}; distinct (sym, s0) {len(gd)}): " + " | ".join(f"{k} {cl.get(k, 0)} ({cd.get(k, 0)})" for k in order))
        nu = g[g.ladder == "c_not_in_universe"]
        if len(nu):
            print(f"    not-in-universe reasons (most frequent failing component per label): {dict(Counter(nu.uni_fail_reason))}")
            print(f"    symbols: {sorted(Counter(nu.sym).items(), key=lambda x: -x[1])}")
        sf = g[g.ladder == "f_subfloor_gap_day"]
        if len(sf):
            print(f"    sub-floor gap days: failing terms {dict(Counter(sf.subfloor_fail))}; gap % median {float(sf.subfloor_gap_pct.median()):.1f}, vr20 median {float(sf.subfloor_vr20.median()):.1f}")
        pb = g[g.ladder == "e_parabolic_runup"]
        if len(pb):
            print(f"    parabolic: {sorted(set(zip(pb.sym, pb.s0)))}")
        gn = g[g.ladder == "g_nothing"]
        if len(gn):
            un_ = gn[gn.typed == 0]
            print(f"    (g) split by the SIC `typed` flag (added after run 1): UNTYPED = fund proxy, admitted as unknown by universe_ok {len(un_)}"
                  f" ({sorted(Counter(un_.sym).items(), key=lambda x: -x[1])}) | typed common stock / ADR {len(gn) - len(un_)}"
                  f" ({sorted(Counter(gn[gn.typed == 1].sym).items(), key=lambda x: -x[1])})")
    print("- wide beside read (added after run 1): the nearest primary EP event of the symbol within +-60 sessions of the label (delta: n; >0 = label before the gap day)")
    for e in ("A", "B"):
        g = Un[Un.era == e]
        dw = g.delta_ep_wide60[g.delta_ep_wide60 != ""].astype(int)
        print(f"    era {e}: labels with an EP event within +-60 {len(dw)} of {len(g)} | in the window [-10, +5] {int(g.m_primary.sum())} | an EP event 11-40 sessions BEFORE the label (post-EP base) {int(g.ep_11_40_before.sum())}"
              f" | histogram " + " ".join(f"{k:+d}:{v_}" for k, v_ in sorted(Counter(dw).items())))
    print("- independent flags (not first-match), per era, on the 294: EP matched | breakout within +-60 | parabolic at s0 (ext5 >= 50%) | run10 >= 50% | sub-floor gap in window | universe ok on some session")
    for e in ("A", "B"):
        g = Un[Un.era == e]
        print(f"    era {e}: {int(g.m_primary.sum())} | {int((g.delta_wide_tl != '').sum())} | {int(((g.ext5_s0_pct != '') & (pd.to_numeric(g.ext5_s0_pct, errors='coerce') >= 100 * EXT_MAX)).sum())}"
              f" | {int(((g.run10_s0_pct != '') & (pd.to_numeric(g.run10_s0_pct, errors='coerce') >= 50)).sum())} | {int(g.m_subfloor.sum())} | {int(g.uni_ok_any.sum())}")

    # ------------------------------------------------------------------ fetch list
    print("\n## 4. Minute-fetch list (ticker|date|tier|era): tier 0 = EP days matched to any positive label, tier 1 = the other primary EP events of those days")
    done = {}
    for e in ("A", "B"):
        d = pd.read_csv(FILES[f"done_{e}"], sep="|", header=None, names=["d", "t", "n", "st"], dtype=str, keep_default_na=False)
        n0 = len(d)
        d = d[d.d <= CUT_B]
        assert d.d.max() <= CUT_B
        done[e] = set(zip(d.t, d.d))
        print(f"- era {e} done list: {n0} rows read, {n0 - len(d)} dated after {CUT_B} dropped, {len(done[e])} (ticker, date) pairs kept (status {dict(Counter(d.st))})")
    t0 = X[X.m_primary == 1][["era", "sym", "E_ep", "bo_matched"]].rename(columns={"sym": "ticker", "E_ep": "date"})
    t0 = t0.groupby(["era", "ticker", "date"], as_index=False).bo_matched.min()      # 0 if any label on it was breakout-unmatched
    t0["tier"] = 0
    days = {e: set(t0.loc[t0.era == e, "date"]) for e in ("A", "B")}
    t1_parts = []
    for e in ("A", "B"):
        prim = W[e][W[e].primary & W[e].E.isin(days[e])][["ticker", "E"]].rename(columns={"E": "date"})
        prim["era"] = e
        key0 = set(zip(t0.loc[t0.era == e, "ticker"], t0.loc[t0.era == e, "date"]))
        prim = prim[[(a_, b_) not in key0 for a_, b_ in zip(prim.ticker, prim.date)]]
        t1_parts.append(prim)
    t1 = pd.concat(t1_parts, ignore_index=True)
    t1["tier"] = 1
    t1["bo_matched"] = ""
    n_total = len(t0) + len(t1)
    print(f"- tier 0: {len(t0)} pairs (era A {int((t0.era == 'A').sum())}, B {int((t0.era == 'B').sum())}; on {len(set(zip(t0.era, t0.date)))} days;"
          f" {int((t0.bo_matched == 0).sum())} carry a breakout-UNMATCHED label) | tier 1 (all other EP events of those days): {len(t1)} | total {n_total} (cap {FETCH_CAP})")
    if n_total > FETCH_CAP:
        room = FETCH_CAP - len(t0)
        rng = random.Random(SEED)
        keep = []
        share = room / len(t1)
        for (e, d_), g in t1.groupby(["era", "date"], sort=True):
            k = max(1, int(round(share * len(g))))
            idx_ = sorted(g.index.tolist())
            rng.shuffle(idx_)
            keep.extend(idx_[:k])
        t1 = t1.loc[sorted(keep)]
        print(f"- tier 1 SAMPLED per date in proportion (seed {SEED}, >= 1 per date) to {len(t1)} pairs; total {len(t0) + len(t1)}")
    F = pd.concat([t0, t1], ignore_index=True)
    F["already"] = [(t_, d_) in done[e] for e, t_, d_ in zip(F.era, F.ticker, F.date)]
    print(f"- already fetched (in the era's done list, any status): tier 0 {int((F.already & (F.tier == 0)).sum())} of {len(t0)} | tier 1 {int((F.already & (F.tier == 1)).sum())} of {len(t1)}")
    Fo = F[~F.already].sort_values(["era", "date", "tier", "ticker"])
    with open(f"{OUT}/ep_minute_fetch_list.psv", "w") as fh:
        fh.write("ticker|date|tier|era\n")
        for r in Fo.itertuples(index=False):
            fh.write(f"{r.ticker}|{r.date}|{r.tier}|{r.era}\n")
    print(f"- FETCH LIST written: {len(Fo)} pairs (tier 0 {int((Fo.tier == 0).sum())}, tier 1 {int((Fo.tier == 1).sum())}; era A {int((Fo.era == 'A').sum())}, era B {int((Fo.era == 'B').sum())};"
          f" {Fo.date.nunique()} dates; max date {Fo.date.max()}) -> {OUT}/ep_minute_fetch_list.psv")
    with open(f"{OUT}/ep_fetch_tier0_labels.tsv", "w") as fh:
        t0.sort_values(["era", "date", "ticker"]).to_csv(fh, sep="\t", index=False)

    # ------------------------------------------------------------------ pins
    print("\n## 5. Pins (sha256)")
    for k, p in FILES.items():
        print(f"- {k}: {sha(p)}  {p}")
    print(f"- this script: {sha(os.path.abspath(__file__))}")
    for f in sorted(os.listdir(OUT)):
        print(f"- output {f}: {sha(os.path.join(OUT, f))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
