#!/usr/bin/env python3
"""Backtest-data audit, lens POINT-IN-TIME / LOOK-AHEAD (#705, operator 2026-10-23: "categorize problems we know or potential ones
we don't know and verify the data, and do so for future runs as well").  Read-only; stdlib + pandas/numpy; no network, no DB.

Two halves:
  * `lint`     — a STATIC checklist of every place the #702 consolidation-breakout backtest could use a non-point-in-time input, let a
                 later bar reach an earlier decision, differ by feed / session calendar between eras, or bias R through the walk's fill
                 assumptions.  For each item it locates the code anchor (file:line, found by a regex so a moved line is reported, not
                 silently skipped), says whether a NAMED TEST guards it, and names the measurement below that sizes it.  Exit 1 when an
                 anchor is missing (the checklist is stale against the code) — run it before every new backtest read.
  * measurements (each prints counts with their n and writes a TSV of the flagged rows into --out):
      calendar  --export E [--minutes DIR]          sessions per year vs the NYSE count, the two unscheduled closures, early-close days,
                                                    and how many minute bars sit at >= 13:00 on an early-close day (after-hours prints
                                                    the fetcher keeps because its window is 09:30-16:00 every day)
      overlap   --era-a E --era-b E ...             the SAME dates (2022-03-28 .. 2022-06-30) through both exports: universe membership,
                                                    the RS percentile (max of 21/63/126) and the vendor OHLCV agreement — the direct size
                                                    of 'the RS denominator is not point-in-time' (survivorship, duplicates, vendor volume)
      inputs    --export E --sic S --small P ...    universe member-nights resting on a non-PIT input: no security type (admitted),
                                                    a name that reads as a fund/ETN, no SIC group, today's-symbol regex exclusions
      entries   --entries T --minutes DIR           entry-time facts only (never an exit): the stop taken from the FILL MINUTE's own low,
                                                    E on an early-close day, the minute-vs-daily abstain rate, fill at level vs at the open,
                                                    and what 0.1% of exit slippage costs in R given the stop widths
      chain     --watch W --candidates C            the chain key's first-break label recomputed with only the poles known by each D
                                                    (a later pole can merge two bases after the fact) vs the batch label
      horizon   --export E --candidates C ...       first breaks whose data ENDS inside the 121-session walk (delisted / acquired: the walk
                                                    ends 'degraded' and is dropped from every decisive number) and forward windows that
                                                    cross a symbol identity break (era A; `fwd_end` cuts on holes only)
Every measurement refuses a date past 2024-12-31 for anything outcome-adjacent (the 2025-26 table is sealed); none reads an exit.

  python3 scripts/backtest_data_audit/pit_lint.py lint
  python3 scripts/backtest_data_audit/pit_lint.py calendar --export ~/apollo_data/cb702_pre/daily_closes_all.csv.gz --minutes ~/apollo_data/cb702_pre/minutes --out OUT
  python3 scripts/backtest_data_audit/pit_lint.py overlap --era-a ~/apollo_data/cb702_pre --era-b ~/apollo_data/cb702 --out OUT
  python3 scripts/backtest_data_audit/pit_lint.py inputs  --data ~/apollo_data/cb702_pre --raw-close --breaks --start 2017-03-01 --end 2021-12-31 --out OUT
  python3 scripts/backtest_data_audit/pit_lint.py entries --entries ~/apollo_data/cb702/out/entries_discovery.tsv.gz --minutes ~/apollo_data/cb702/minutes --out OUT
  python3 scripts/backtest_data_audit/pit_lint.py horizon --data ~/apollo_data/cb702 --candidates ~/apollo_data/cb702/out/candidates.tsv --out OUT
  python3 scripts/backtest_data_audit/pit_lint.py chain   --watch ~/apollo_data/cb702/out/watch.tsv.gz --candidates ~/apollo_data/cb702/out/candidates.tsv --out OUT
  (entries also takes --candidates to split the minute_daily_mismatch abstains by side and count minute-vs-daily scale offsets)
A `--data DIR` is an export directory laid out as the runner reads it (daily_closes_all.csv.gz, cb702_sic.psv, small_pulls.psv,
cb702_splits.psv | daily_raw_close.csv.gz, symbol_guard.tsv)."""
from __future__ import annotations

import argparse
import bisect
import gzip
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SEALED_AFTER = date(2024, 12, 31)

# NYSE sessions per calendar year (full years; 2018 and 2025 carry one unscheduled closure each) — the calendar check's reference.
NYSE_SESSIONS = {2016: 252, 2017: 251, 2018: 251, 2019: 252, 2020: 253, 2021: 252, 2022: 251, 2023: 250, 2024: 252, 2025: 250}
UNSCHEDULED_CLOSURES = ("2018-12-05", "2025-01-09")          # Bush and Carter national days of mourning
EARLY_CLOSES = frozenset({                                   # 13:00 ET closes (the same list runner.H60_EARLY_CLOSE carries, + 2016)
    "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29", "2019-12-24",
    "2020-11-27", "2020-12-24", "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29", "2024-12-24",
    "2025-07-03", "2025-11-28", "2025-12-24"})
EARLY_CUT_MINUTE = 210                                       # minute index of 13:00 ET (0 = 09:30)

FUNDISH = re.compile(r"\b(ETF|ETFS|ETN|ETNS|FUND|INDEX|ISHARES|PROSHARES|VELOCITYSHARES|DIREXION|ULTRAPRO|ULTRASHORT|ULTRA|[23]X|"
                     r"INVERSE|LEVERAGED|EXCHANGE[- ]TRADED|TRUST UNITS?|CLOSED[- ]END)\b", re.I)   # a fund / ETN / leveraged product


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 1. THE STATIC CHECKLIST
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
MOD = "agents/market_intelligence/consolidation_breakout.py"
RUN = "scripts/probes/_cb_backtest/runner.py"
FET = "scripts/probes/_cb_backtest/fetch_minutes.py"
CON = "agents/market_intelligence/constants.py"
T_CB = "tests/test_consolidation_breakout.py"
T_RUN = "tests/test_cb_backtest_runner.py"
T_SH = "tests/test_cb_shadow.py"
T_AP = "tests/test_cb_backtest_aplus.py"

# Each item: id, category, title, anchor (file, regex), guards [(test file, test-function regex)], measure (subcommand or None),
# and the status the 2026-10-23 audit reached (the lint prints it; the evidence is in the commit / the findings doc).
CHECKLIST = [
    # ── non point-in-time INPUTS ──────────────────────────────────────────────────────────────────────────────────────────────────
    dict(id="N1", cat="non_pit_input", title="SIC as of 2026-10-16 (one row per ticker) -> group membership constant in time",
         anchor=(RUN, r"def load_sic"), guards=[], measure="inputs", status="confirmed"),
    dict(id="N2", cat="non_pit_input", title="security type = today's mi_security_types / SIC-pull type; unknown type ADMITTED",
         anchor=(MOD, r"def resolve_sectype"), guards=[], measure="inputs", status="confirmed"),
    dict(id="N3", cat="non_pit_input", title="RS denominator = the export's universe members that night (survivors only in era A; "
         "duplicate symbols counted twice; not prod's mi_stock_scores denominator)",
         anchor=(MOD, r"def cross_section_one_date"), guards=[], measure="overlap", status="confirmed"),
    dict(id="N4", cat="non_pit_input", title="era A symbol set = Alpaca's CURRENT asset list (history keyed by today's symbol)",
         anchor=(RUN, r"def load_breaks"), guards=[], measure="overlap", status="confirmed"),
    dict(id="N9", cat="non_pit_input", title="era A history is keyed by TODAY's symbol (XYZ not SQ, OPLN not KAR): any join to a "
         "symbol-at-the-time list (labelled EPs, stream notes, prod tables) misses or mis-joins renamed names",
         anchor=(RUN, r"def load_daily"), guards=[], measure="overlap", status="confirmed"),
    dict(id="N5", cat="non_pit_input", title="ticker regex ^[A-Z]{1,5}$ applied to TODAY's symbol in era A",
         anchor=(MOD, r"UNIVERSE_TICKER_RE = "), guards=[], measure="inputs", status="suspected"),
    dict(id="N6", cat="non_pit_input", title="market cap / float / shares: not used by the CB backtest",
         anchor=(MOD, r"def universe_ok"), guards=[], measure=None, status="ruled_out"),
    dict(id="N7", cat="non_pit_input", title="thresholds cut on the WHOLE discovery distribution (TRAIL_SPEED_ADR_CUT, report terciles)"
         " applied to every discovery trade (in-sample)", anchor=(MOD, r"TRAIL_SPEED_ADR_CUT = "), guards=[], measure=None,
         status="suspected"),
    dict(id="N8", cat="non_pit_input", title="split list as of 2026-10-16; splits after the export's last session dropped from the raw "
         "factor", anchor=(RUN, r"def load_splits"), guards=[(T_SH, r"test_an_announced_future_split_changes_nothing")],
         measure=None, status="ruled_out"),
    # ── LOOK-AHEAD: a later bar reaching an earlier decision ──────────────────────────────────────────────────────────────────────
    dict(id="L1", cat="lookahead", title="watch-night features (pole, base, pivots, tl, ADR, SMA) use bars <= D only",
         anchor=(MOD, r"def explain_watch"), guards=[(T_SH, r"test_a_150_bar_slice_gives_the_same_features_as_the_whole_history")],
         measure=None, status="ruled_out"),
    dict(id="L2", cat="lookahead", title="pre-screen skip uses windows ending at i-10 only, proved by --check-prescreen",
         anchor=(RUN, r"def prescreen_skip_mask"), guards=[(T_RUN, r"prescreen")], measure=None, status="ruled_out"),
    dict(id="L3", cat="lookahead", title="E-day columns (open/high/low/close/vol_E, breakout_vol_x) never select: source-shuffle check",
         anchor=("scripts/probes/_cb_backtest/aplus_read.py", r"CAND_LOOKAHEAD_COLS = "), guards=[(T_AP, r"test_check1b_a_feature_that_reads_an_e_day_column|test_check1c_a_feature_that_reads_past_d")],
         measure=None, status="ruled_out"),
    dict(id="L4", cat="lookahead", title="stop = low of the day THROUGH the fill minute, INCLUDING the fill minute's own low (part of "
         "that low can print after the fill)", anchor=(MOD, r"stop = float\(minutes\.l\[:m \+ 1\]\.min\(\)\)"), guards=[],
         measure="entries", status="confirmed"),
    dict(id="L5", cat="lookahead", title="minute_daily_mismatch abstain compares the WHOLE day's minute high/low with the daily bar "
         "(a same-day data filter decided with the day's later prints)", anchor=(MOD, r"pre = \"minute_daily_mismatch\""),
         guards=[], measure="entries", status="suspected"),
    dict(id="L6", cat="lookahead", title="symbol identity breaks (symbol_guard.tsv) are computed over the full series; a break INSIDE "
         "a forward walk is not cut (fwd_end cuts holes only)", anchor=(MOD, r"def fwd_end"), guards=[], measure="horizon",
         status="confirmed"),
    dict(id="L7", cat="lookahead", title="discovery walks near 2024-12-31 read 2025 bars (selection is by D; R can hold holdout prices)",
         anchor=(RUN, r"DISCOVERY_END = date\(2024, 12, 31\)"), guards=[], measure=None, status="confirmed"),
    dict(id="L8", cat="lookahead", title="'degraded' walks (data ends inside the horizon: delisted / acquired) dropped from decisive "
         "numbers -> a population chosen by the stock's future", anchor=(MOD, r"def is_mature"), guards=[],
         measure="horizon", status="confirmed"),
    dict(id="L9", cat="lookahead", title="trail signal on close j fills at open j+1; partial at a session close; breakeven rests from "
         "the next session", anchor=(MOD, r"if j < n:\s+# session j\+1 exists"), guards=[(T_CB, r"next_open|trail")],
         measure=None, status="ruled_out"),
    dict(id="L10", cat="lookahead", title="chain key (`chain_bases`) built from EVERY watch row's pole, incl. nights after D: a later "
         "pole can merge two bases and make a first break a retrigger after the fact", anchor=(MOD, r"def chain_bases"),
         guards=[(T_SH, r"test_a_later_bridging_pole_is_the_documented_difference")], measure="chain", status="ruled_out"),
    dict(id="L11", cat="lookahead", title="identity-guard break dates (hole = first bar after it; jump = that bar vs the 20 before) are "
         "causal for the watch-night exclusion", anchor=("scripts/probes/_qm_streams/ext_bars.py", r"JUMP_MAX = "), guards=[],
         measure=None, status="ruled_out"),
    dict(id="L12", cat="lookahead", title="overlap_open (report-only) uses the previous trade's exit, known before E",
         anchor=(RUN, r"def stamp_overlap_open"), guards=[], measure=None, status="ruled_out"),
    # ── FEED / SESSION CALENDAR differences between eras ─────────────────────────────────────────────────────────────────────────
    dict(id="F1", cat="feed_calendar", title="minutes fetched 09:30-16:00 EVERY day: on a 13:00 close the 13:00-16:00 after-hours "
         "prints enter the minute engine's day-0 walk (only h60 trims them)", anchor=(FET, r"time\(16, 0\)"),
         guards=[], measure="calendar", status="confirmed"),
    dict(id="F2", cat="feed_calendar", title="daily bars from two vendors (era A Alpaca, era B Polygon): high/low/volume differ -> "
         "breakout test, stop, $10M floor and RS differ on the same day", anchor=(RUN, r"def load_daily"), guards=[],
         measure="overlap", status="confirmed"),
    dict(id="F3", cat="feed_calendar", title="minute feed = SIP in both eras (DataFeed.SIP)", anchor=(FET, r"feed=DataFeed\.SIP"),
         guards=[], measure="entries", status="ruled_out"),
    dict(id="F6", cat="feed_calendar", title="minute bars (Alpaca, split-only) and daily bars (era vendor) on different price scales: "
         "> 1% abstains (minute_daily_mismatch); < 1% passes and mixes scales in R", anchor=(MOD, r"MINUTE_DAILY_MISMATCH_MAX = "),
         guards=[], measure="entries", status="ruled_out"),
    dict(id="F4", cat="feed_calendar", title="session calendar = SPY's sessions; per-year counts vs NYSE, the two unscheduled closures",
         anchor=(RUN, r"SPY calendar not strictly ascending"), guards=[], measure="calendar", status="ruled_out"),
    dict(id="F5", cat="feed_calendar", title="halts / missing sessions: 130-bar contiguity on the watch night; forward walk cut at the "
         "first hole", anchor=(MOD, r"def contiguous_window_mask"), guards=[(T_RUN, r"hole|contig")], measure=None,
         status="ruled_out"),
    # ── WALK ASSUMPTIONS that bias R ─────────────────────────────────────────────────────────────────────────────────────────────
    dict(id="W1", cat="walk_assumption", title="same daily bar touching stop and target books the STOP (pessimistic)",
         anchor=(MOD, r"pessimistic: touching both -> the stop"), guards=[(T_CB, r"touching_both")], measure=None, status="ruled_out"),
    dict(id="W2", cat="walk_assumption", title="entry slippage 0.1% (ENTRY_SLIPPAGE_PCT); exits at the stop / open / close with NO "
         "slippage", anchor=(CON, r"ENTRY_SLIPPAGE_PCT = "), guards=[], measure="entries", status="confirmed"),
    dict(id="W3", cat="walk_assumption", title="a stop-buy fills AT the level (+0.1%) whenever the minute opened at or below it",
         anchor=(MOD, r"fill = \(level if op <= level else op\)"), guards=[], measure="entries", status="suspected"),
    dict(id="W4", cat="walk_assumption", title="no fees: commission-free broker; SEC/TAF sell fees ~0.003% of notional",
         anchor=(MOD, r"def _outcome"), guards=[], measure=None, status="ruled_out"),
    dict(id="W5", cat="walk_assumption", title="no borrow cost: the setup is long-only", anchor=(MOD, r"def walk_exit"), guards=[],
         measure=None, status="ruled_out"),
    dict(id="W6", cat="walk_assumption", title="gap through the stop exits at the OPEN (worse than -1R), not at the stop",
         anchor=(MOD, r"open <= stop exits ALL remaining"), guards=[(T_CB, r"gap_down_through_the_stop")], measure=None, status="ruled_out"),
]


def _test_functions(path: Path) -> list:
    if not path.exists():
        return []
    return re.findall(r"^\s*def (test_\w+)", path.read_text(), flags=re.M)


def run_lint(args) -> int:
    rows, missing = [], 0
    for it in CHECKLIST:
        f, rx = it["anchor"]
        p = REPO / f
        line = None
        if p.exists():
            txt = p.read_text()
            m = re.search(rx, txt)
            if m:
                line = txt.count("\n", 0, m.start()) + 1
        if line is None:
            missing += 1
        guard = []
        for tf, trx in it["guards"]:
            hits = [n for n in _test_functions(REPO / tf) if re.search(trx, n)]
            if hits:
                guard.append(f"{tf}::{hits[0]}" + (f" (+{len(hits) - 1})" if len(hits) > 1 else ""))
        rows.append([it["id"], it["cat"], it["status"], f"{f}:{line}" if line else f"{f}: ANCHOR MISSING",
                     "; ".join(guard) if guard else "NO TEST", it["measure"] or "-", it["title"]])
    hdr = ["id", "category", "status", "anchor", "guarded by", "measure", "item"]
    w = [max(len(str(r[k])) for r in rows + [hdr]) for k in range(6)]
    print("  ".join(h.ljust(w[k]) if k < 6 else h for k, h in enumerate(hdr)))
    for r in rows:
        print("  ".join(str(x).ljust(w[k]) if k < 6 else str(x) for k, x in enumerate(r)))
    n_unguarded = sum(1 for r in rows if r[4] == "NO TEST" and r[2] != "ruled_out")
    by = Counter(r[2] for r in rows)
    print(f"\n{len(rows)} items: {by['confirmed']} confirmed, {by['suspected']} suspected, {by['ruled_out']} ruled out; "
          f"{n_unguarded} confirmed/suspected items have NO guarding test; anchors missing: {missing}")
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "pit_lint_checklist.tsv", "w") as fh:
            fh.write("\t".join(hdr) + "\n")
            for r in rows:
                fh.write("\t".join(str(x) for x in r) + "\n")
    return 1 if missing else 0


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 2. LOADING
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
class Export:
    """A date-filtered export as per-ticker numpy arrays aligned to SPY's sessions inside the window."""

    def __init__(self, path: Path, start: "date | None" = None, end: "date | None" = None, usecols_ohlcv: bool = True):
        import pandas as pd
        df = pd.read_csv(path, header=None, names=["t", "d", "o", "h", "l", "c", "v"], dtype={"t": str},
                         keep_default_na=False)
        self.last_date_full = date.fromisoformat(df["d"].max())
        if start is not None:
            df = df[df["d"] >= start.isoformat()]
        if end is not None:
            df = df[df["d"] <= end.isoformat()]
        df = df.sort_values(["t", "d"], kind="mergesort").reset_index(drop=True)
        spy = df.loc[df["t"] == "SPY", "d"].tolist()
        self.cal = [date.fromisoformat(x) for x in spy]
        pos = {d: k for k, d in enumerate(spy)}
        ci = df["d"].map(pos)
        off = ci.isna()
        self.n_off_calendar = int(off.sum())
        df = df[~off].reset_index(drop=True)
        self.ci = df["d"].map(pos).to_numpy(dtype=np.int64)
        self.t = df["t"].to_numpy()
        self.o, self.h, self.l, self.c, self.v = (df[k].to_numpy(dtype=float) for k in "ohlcv")
        tk, first = np.unique(self.t, return_index=True)
        self.tickers = [str(x) for x in tk]
        self.start = first
        self.stop = np.append(first[1:], len(self.t))
        self.tid = {t: k for k, t in enumerate(self.tickers)}
        self.dates_iso = df["d"].to_numpy()

    def rows(self, t: str) -> slice:
        k = self.tid[t]
        return slice(int(self.start[k]), int(self.stop[k]))


def load_small(path: Path) -> dict:
    sec = {}
    for line in Path(path).read_text().splitlines():
        f = line.split("|")
        if f[0] == "sectype" and len(f) >= 3:
            sec[f[1]] = f[2]
    return sec


def load_sic_rows(path: Path) -> dict:
    """{ticker: (as_of, status, sic_code, sic_desc, type)} — the pull's one row per ticker."""
    out = {}
    for line in Path(path).read_text().splitlines():
        f = line.split("|")
        if len(f) >= 6:
            out[f[0]] = (f[1], f[2], f[3], f[4], f[5])
    return out


def load_assets(path: "Path | None") -> dict:
    if not path or not Path(path).exists():
        return {}
    out = {}
    lines = Path(path).read_text().splitlines()
    head = lines[0].split("\t")
    ks, kn, kst = head.index("symbol"), head.index("name"), head.index("status")
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) > max(ks, kn, kst):
            out[f[ks]] = (f[kn], f[kst])
    return out


def raw_factor(ex: Export, data: Path, use_raw_close: bool) -> np.ndarray:
    """RAW / adjusted per flat row: era A from daily_raw_close.csv.gz, era B from the split list (runner.load_splits + factor_by_bar,
    `through` = the FULL export's last session, exactly as the runner calls it)."""
    from scripts.probes._cb_backtest import runner as rn
    fac = np.ones(len(ex.c))
    if use_raw_close:
        import pandas as pd
        rc = pd.read_csv(data / "daily_raw_close.csv.gz", header=None, names=["t", "d", "rc"], dtype={"t": str}, keep_default_na=False)
        rc = rc[(rc["d"] >= ex.dates_iso.min()) & (rc["d"] <= ex.dates_iso.max())]
        key = pd.Series(rc["rc"].to_numpy(), index=pd.MultiIndex.from_arrays([rc["t"], rc["d"]]))
        got = key.reindex(pd.MultiIndex.from_arrays([ex.t, ex.dates_iso])).to_numpy(dtype=float)
        assert np.isfinite(got).all(), "raw close missing for some export rows"
        return got / ex.c
    splits = rn.load_splits(data / "cb702_splits.psv", through=ex.last_date_full)
    for t, sp in splits.items():
        if t in ex.tid:
            s = ex.rows(t)
            fac[s] = rn.factor_by_bar([date.fromisoformat(x) for x in ex.dates_iso[s]], sp)
    return fac


def universe_mask(ex: Export, fac: np.ndarray, sectype: dict, breaks: "dict | None") -> np.ndarray:
    """Vectorised `cb.universe_ok` + not a test symbol + 130 consecutive SPY sessions + (era A) no identity break inside the 130 bars —
    the runner's scan_ticker admission, row by row. Spot-checked against the module by `_spot_check_universe`."""
    from agents.market_intelligence import consolidation_breakout as cb
    from scripts.probes._cb_backtest import runner as rn
    import pandas as pd
    out = np.zeros(len(ex.c), dtype=bool)
    for k, t in enumerate(ex.tickers):
        a, b = int(ex.start[k]), int(ex.stop[k])
        n = b - a
        if n < cb.MIN_HISTORY or cb.is_test_symbol(t) or not cb.UNIVERSE_TICKER_RE.fullmatch(t):
            continue
        st = sectype.get(t, "")
        if st and st not in cb.UNIVERSE_SECURITY_TYPES:
            continue
        c, v = ex.c[a:b], ex.v[a:b]
        med = pd.Series(c * v).rolling(cb.DOLLAR_VOL_WINDOW).median().to_numpy()
        ok = (c * fac[a:b] >= cb.MIN_PRICE) & (med >= cb.MIN_DOLLAR_VOL)
        ok[:cb.MIN_HISTORY - 1] = False
        ok &= cb.contiguous_window_mask(ex.ci[a:b], cb.MIN_HISTORY)
        if breaks is not None and t in breaks:
            d_ord = np.array([date.fromisoformat(x).toordinal() for x in ex.dates_iso[a:b]], dtype=np.int64)
            ok &= ~rn.break_mask(d_ord, breaks[t])
        out[a:b] = ok
    return out


def _spot_check_universe(ex: Export, fac, sectype, mask, n: int = 4000, seed: int = 705, skip_breaks=None) -> int:
    """The vectorised mask vs `cb.universe_ok` (+ contiguity) on `n` random rows; returns the number of disagreements."""
    from agents.market_intelligence import consolidation_breakout as cb
    rng = np.random.default_rng(seed)
    bad = 0
    for r in rng.choice(len(ex.c), size=min(n, len(ex.c)), replace=False):
        t = ex.t[r]
        k = ex.tid[t]
        a, b = int(ex.start[k]), int(ex.stop[k])
        bars = cb.daily_bars_from_arrays([date.fromisoformat(x) for x in ex.dates_iso[a:b]], ex.o[a:b], ex.h[a:b], ex.l[a:b],
                                         ex.c[a:b], ex.v[a:b])
        i = r - a
        want = (not cb.is_test_symbol(t)) and cb.universe_ok(bars, i, raw_factor=float(fac[r]), ticker=t,
                                                              security_type=sectype.get(t, "")) \
            and bool(cb.contiguous_window_mask(ex.ci[a:b], cb.MIN_HISTORY)[i])
        if skip_breaks and t in skip_breaks:
            continue                                   # the identity guard is applied by the mask only
        bad += int(want != bool(mask[r]))
    return bad


def rs_inputs(ex: Export) -> np.ndarray:
    """(r21, r63, r126) per flat row = close[i]/close[i-h] - 1 inside the ticker's own bars (NaN without history)."""
    out = np.full((len(ex.c), 3), np.nan)
    for k in range(len(ex.tickers)):
        a, b = int(ex.start[k]), int(ex.stop[k])
        c = ex.c[a:b]
        for j, hz in enumerate((21, 63, 126)):
            if b - a > hz:
                base = c[:-hz]
                with np.errstate(divide="ignore", invalid="ignore"):
                    out[a + hz:b, j] = np.where(base > 0, c[hz:] / base - 1.0, np.nan)
    return out


def cross_section(ex: Export, member: np.ndarray, rs: np.ndarray, sic2_of: dict, ci_lo: int, ci_hi: int) -> dict:
    """{(ticker, ci): (rs_best, grp_pct)} over universe members, one `cb.cross_section_one_date` per session (members in ticker
    order, the runner's tie order)."""
    from agents.market_intelligence import consolidation_breakout as cb
    out = {}
    idx = np.flatnonzero(member & (ex.ci >= ci_lo) & (ex.ci <= ci_hi))
    by_ci = defaultdict(list)
    for r in idx:
        by_ci[int(ex.ci[r])].append(r)
    for j, rows in by_ci.items():
        rows.sort(key=lambda r: ex.t[r])
        r21, r63, r126 = ([None if x != x else float(x) for x in rs[rows, k]] for k in range(3))
        groups = [sic2_of.get(ex.t[r]) for r in rows]
        best, _all, grp, _ng = cb.cross_section_one_date(r21, r63, r126, groups)
        for r, b_, g_ in zip(rows, best, grp):
            out[(ex.t[r], j)] = (b_, g_)
    return out


def write_flags(out: Path, name: str, rows: list, cols: list) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    p = out / name
    with open(p, "w") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    return p


def _sic2_map(sic_rows: dict) -> dict:
    from agents.market_intelligence import consolidation_breakout as cb
    return {t: (cb.sic2(v[2]) if v[2] else None) for t, v in sic_rows.items()}


def _sectypes(data: Path) -> dict:
    """runner.resolve_sectype's two sources merged: mi_security_types first, else the SIC pull's type."""
    mi = load_small(data / "small_pulls.psv")
    sic = load_sic_rows(data / "cb702_sic.psv")
    out = {t: v[4] for t, v in sic.items() if v[4]}
    out.update({t: v for t, v in mi.items() if v})
    return out


def _guard(data: Path, on: bool) -> "dict | None":
    if not on:
        return None
    from scripts.probes._cb_backtest import runner as rn
    return rn.load_breaks(data / "symbol_guard.tsv")


def _refuse_sealed(d: date, what: str) -> None:
    if d > SEALED_AFTER:
        sys.exit(f"refusing {what} {d}: the 2025-26 table is sealed (max {SEALED_AFTER})")


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 3. MEASUREMENTS
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def run_calendar(args) -> int:
    import pandas as pd
    df = pd.read_csv(args.export, header=None, usecols=[0, 1], names=["t", "d"], dtype=str, keep_default_na=False)
    spy = sorted(df.loc[df["t"] == "SPY", "d"].unique())
    flags = []
    yrs = Counter(int(d[:4]) for d in spy)
    first, last = spy[0], spy[-1]
    print(f"CALENDAR {args.export}: {len(spy):,} SPY sessions {first}..{last}")
    for y in sorted(yrs):
        full = f"{y}-01-01" >= first[:4] + "-01-01" and first <= f"{y}-01-05" and last >= f"{y}-12-28"
        ref = NYSE_SESSIONS.get(y)
        verdict = ("ok" if yrs[y] == ref else "MISMATCH") if (full and ref) else "partial year"
        print(f"  {y}: {yrs[y]} sessions (NYSE {ref if ref else '?'}) {verdict}")
        if verdict == "MISMATCH":
            flags.append({"kind": "session_count", "date": str(y), "detail": f"{yrs[y]} vs NYSE {ref}"})
    sset = set(spy)
    for d in UNSCHEDULED_CLOSURES:
        if first <= d <= last:
            print(f"  unscheduled closure {d}: {'PRESENT (wrong)' if d in sset else 'absent (right)'}")
            if d in sset:
                flags.append({"kind": "closure_present", "date": d, "detail": "a closed day carries bars"})
    ec = sorted(d for d in EARLY_CLOSES if first <= d <= last)
    print(f"  early-close (13:00) days in range: {len(ec)}; on the calendar: {sum(1 for d in ec if d in sset)}")
    # rows per non-SPY ticker on a date SPY lacks (load_daily asserts none)
    off = int((~df["d"].isin(sset)).sum())
    print(f"  bars dated off SPY's calendar: {off:,}")
    if args.minutes:
        mdir = Path(args.minutes)
        tot_late, tot_bars, tk = 0, 0, 0
        for d in ec:
            p = mdir / f"{d}.psv.gz"
            if not p.exists() or date.fromisoformat(d) > SEALED_AFTER:
                continue
            late = Counter()
            n = 0
            with gzip.open(p, "rt") as fh:
                for line in fh:
                    f = line.split("|")
                    if len(f) < 7:
                        continue
                    n += 1
                    if int(f[1]) >= EARLY_CUT_MINUTE:
                        late[f[0]] += 1
            tot_late += sum(late.values())
            tot_bars += n
            tk += len(late)
            print(f"  minutes {d}: {n:,} bars, {sum(late.values()):,} at >= 13:00 ({sum(late.values()) / max(n, 1):.1%}) on {len(late)} tickers")
            for t, k in late.items():
                flags.append({"kind": "after_hours_minutes_on_early_close", "date": d, "ticker": t, "detail": f"{k} bars >= 13:00"})
        print(f"  MINUTE TREE: on early-close days {tot_late:,} of {tot_bars:,} minute bars ({tot_late / max(tot_bars, 1):.1%}) are "
              f"after-hours prints the minute engine treats as the session (ticker-days {tk:,})")
    p = write_flags(Path(args.out), f"pit_calendar_{args.label}.tsv", flags, ["kind", "date", "ticker", "detail"])
    print(f"flagged rows: {len(flags):,} -> {p}")
    return 0


def run_overlap(args) -> int:
    """Both exports over the SAME window; the RS percentile computed by the module's own cross-section on each export's members."""
    a_dir, b_dir = Path(args.era_a), Path(args.era_b)
    s, e = date.fromisoformat(args.hist_start), date.fromisoformat(args.end)
    d0 = date.fromisoformat(args.start)
    _refuse_sealed(e, "--end")
    A = Export(a_dir / "daily_closes_all.csv.gz", s, e)
    B = Export(b_dir / "daily_closes_all.csv.gz", s, e)
    assert A.cal == B.cal, "the two exports' SPY sessions differ inside the window"
    cal = A.cal
    lo = bisect.bisect_left(cal, d0)
    hi = len(cal) - 1
    print(f"OVERLAP {cal[lo]}..{cal[hi]} ({hi - lo + 1} sessions), history from {cal[0]}; era A {len(A.tickers):,} tickers, "
          f"era B {len(B.tickers):,} tickers in the window")
    secA, secB = _sectypes(a_dir), _sectypes(b_dir)
    facA = raw_factor(A, a_dir, use_raw_close=(a_dir / "daily_raw_close.csv.gz").exists())
    facB = raw_factor(B, b_dir, use_raw_close=False)
    gA = _guard(a_dir, (a_dir / "symbol_guard.tsv").exists())
    mA = universe_mask(A, facA, secA, gA)
    mB = universe_mask(B, facB, secB, None)
    badA, badB = _spot_check_universe(A, facA, secA, mA, skip_breaks=gA), _spot_check_universe(B, facB, secB, mB)
    print(f"  vectorised universe vs cb.universe_ok on 4,000 random rows: era A {badA} disagreements, era B {badB}")
    sic2A, sic2B = _sic2_map(load_sic_rows(a_dir / "cb702_sic.psv")), _sic2_map(load_sic_rows(b_dir / "cb702_sic.psv"))
    xa = cross_section(A, mA, rs_inputs(A), sic2A, lo, hi)
    xb = cross_section(B, mB, rs_inputs(B), sic2B, lo, hi)
    # validate era B against the pinned watch table where available (rs_best is a frozen column there)
    wt = b_dir / "out" / "watch.tsv.gz"
    if wt.exists():
        import pandas as pd
        w = pd.read_csv(wt, sep="\t", usecols=["ticker", "watch_date", "rs_best", "grp_pct"], dtype={"ticker": str},
                        keep_default_na=False)
        w = w[(w["watch_date"] >= cal[lo].isoformat()) & (w["watch_date"] <= cal[hi].isoformat())]
        pos = {d.isoformat(): k for k, d in enumerate(cal)}
        n_eq = n_cmp = n_miss = 0
        for t, d, rb in zip(w["ticker"], w["watch_date"], w["rs_best"]):
            got = xb.get((t, pos[d]))
            if got is None:
                n_miss += 1
                continue
            n_cmp += 1
            n_eq += int(rb != "" and got[0] is not None and abs(float(rb) - got[0]) < 1e-9)
        print(f"  REPRODUCTION: era B rs_best recomputed here vs the pinned watch.tsv.gz: {n_eq:,} of {n_cmp:,} watch nights equal "
              f"({n_miss} watch nights not universe members here)")
    flags = []
    per_day = []
    for j in range(lo, hi + 1):
        ka = {t for (t, c) in xa if c == j}
        kb = {t for (t, c) in xb if c == j}
        per_day.append((len(ka), len(kb), len(ka & kb), len(ka - kb), len(kb - ka)))
    arr = np.array(per_day)
    print(f"  universe members per night (median over {len(per_day)} nights): era A {int(np.median(arr[:, 0])):,}, era B "
          f"{int(np.median(arr[:, 1])):,}; in both {int(np.median(arr[:, 2])):,}; only A {int(np.median(arr[:, 3])):,}; only B "
          f"{int(np.median(arr[:, 4])):,}")
    # why a B member is not an A member
    onlyB = Counter()
    onlyB_tk = defaultdict(set)
    for (t, j) in xb:
        if (t, j) in xa:
            continue
        if t not in A.tid:
            why = "absent_from_era_A_export"          # survivorship / symbol-at-the-time naming
        else:
            r = _row_at(A, t, j)
            why = "no_bar_that_day_in_A" if r is None else ("A_fails_universe" if not mA[r] else "?")
        onlyB[why] += 1
        onlyB_tk[why].add(t)
        flags.append({"kind": "member_only_B", "ticker": t, "date": cal[j].isoformat(), "detail": why})
    onlyA = Counter()
    onlyA_tk = defaultdict(set)
    for (t, j) in xa:
        if (t, j) in xb:
            continue
        why = "absent_from_era_B_export" if t not in B.tid else (
            "no_bar_that_day_in_B" if _row_at(B, t, j) is None else "B_fails_universe")
        onlyA[why] += 1
        onlyA_tk[why].add(t)
        flags.append({"kind": "member_only_A", "ticker": t, "date": cal[j].isoformat(), "detail": why})
    print("  member-nights in B not in A: " + ", ".join(f"{k} {v:,} ({len(onlyB_tk[k])} tickers)" for k, v in onlyB.most_common()))
    print("  member-nights in A not in B: " + ", ".join(f"{k} {v:,} ({len(onlyA_tk[k])} tickers)" for k, v in onlyA.most_common()))
    # RS on the same (ticker, night)
    both = [(k, xa[k][0], xb[k][0]) for k in xa if k in xb and xa[k][0] is not None and xb[k][0] is not None]
    d = np.array([x[1] - x[2] for x in both])
    print(f"  rs_best on the {len(both):,} member-nights in both: A - B median {np.median(d):+.2f}, mean {d.mean():+.2f}, "
          f"|diff| >= 1.0 pct-pt {np.mean(np.abs(d) >= 1.0):.1%}, >= 2.0 {np.mean(np.abs(d) >= 2.0):.1%}")
    for thr in (95.0, 98.0, 99.0):
        ia = np.array([x[1] >= thr for x in both])
        ib = np.array([x[2] >= thr for x in both])
        print(f"    rs_best >= {thr:g}: A {ia.sum():,} / B {ib.sum():,} member-nights; A-only {np.sum(ia & ~ib):,}, B-only "
              f"{np.sum(ib & ~ia):,} (of B's {ib.sum():,}: {np.sum(ib & ~ia) / max(ib.sum(), 1):.1%} drop out under A's denominator)")
    for (k, ra, rb_) in both:
        if (ra >= 98.0) != (rb_ >= 98.0):
            flags.append({"kind": "rs98_flip", "ticker": k[0], "date": cal[k[1]].isoformat(), "detail": f"A {ra} B {rb_}"})
    # vendor OHLCV agreement on common ticker-days in the window
    rowsA = {(A.t[r], int(A.ci[r])): r for r in range(len(A.c)) if A.ci[r] >= lo}
    hd, ld, cd, vr, dvflip = [], [], [], [], 0
    n = 0
    for r in range(len(B.c)):
        if B.ci[r] < lo:
            continue
        ra = rowsA.get((B.t[r], int(B.ci[r])))
        if ra is None or B.c[r] <= 0 or A.c[ra] <= 0:
            continue
        n += 1
        hd.append(A.h[ra] / B.h[r] - 1.0)
        ld.append(A.l[ra] / B.l[r] - 1.0)
        cd.append(A.c[ra] / B.c[r] - 1.0)
        vr.append(A.v[ra] / B.v[r] if B.v[r] > 0 else np.nan)
        if mA[ra] != mB[r]:
            dvflip += 1
    hd, ld, cd, vr = map(np.array, (hd, ld, cd, vr))
    print(f"  vendor agreement on {n:,} common ticker-days: |high diff| > 0.5% {np.mean(np.abs(hd) > 0.005):.2%}, |low diff| > 0.5% "
          f"{np.mean(np.abs(ld) > 0.005):.2%}, |close diff| > 0.1% {np.mean(np.abs(cd) > 0.001):.2%}; volume A/B median "
          f"{np.nanmedian(vr):.3f} (P10 {np.nanpercentile(vr, 10):.3f}, P90 {np.nanpercentile(vr, 90):.3f}); universe membership "
          f"differs on {dvflip:,} common ticker-days")
    p = write_flags(Path(args.out), "pit_overlap.tsv", flags, ["kind", "ticker", "date", "detail"])
    print(f"flagged rows: {len(flags):,} -> {p}")
    return 0


def _row_at(ex: Export, t: str, j: int):
    s = ex.rows(t)
    k = np.searchsorted(ex.ci[s], j)
    r = s.start + int(k)
    return r if r < s.stop and ex.ci[r] == j else None


def run_inputs(args) -> int:
    data = Path(args.data)
    s, e = date.fromisoformat(args.start), date.fromisoformat(args.end)
    _refuse_sealed(e, "--end")
    hist = date(s.year - 1, 1, 1) if s.month <= 8 else date(s.year, 1, 1)
    X = Export(data / "daily_closes_all.csv.gz", hist, e)
    sec_mi = load_small(data / "small_pulls.psv")
    sic = load_sic_rows(data / "cb702_sic.psv")
    sect = _sectypes(data)
    assets = load_assets(Path(args.assets) if args.assets else None)
    fac = raw_factor(X, data, use_raw_close=args.raw_close)
    mem = universe_mask(X, fac, sect, _guard(data, args.breaks))
    d_lo = bisect.bisect_left(X.cal, s)
    sel = mem & (X.ci >= d_lo)
    n_nights = int(sel.sum())
    tick = Counter(X.t[sel])
    print(f"INPUTS {data}: universe member-nights {s}..{e}: {n_nights:,} on {len(tick):,} tickers")
    flags = []
    unk = [t for t in tick if not sect.get(t)]
    print(f"  N2 no security type (admitted as unknown): {len(unk):,} tickers, {sum(tick[t] for t in unk):,} member-nights "
          f"({sum(tick[t] for t in unk) / max(n_nights, 1):.2%})")
    srcs = Counter(("mi" if sec_mi.get(t) else ("sic_pull" if sic.get(t, ("",) * 5)[4] else "none")) for t in tick)
    print(f"  N2 type source per member ticker: {dict(srcs)}")
    fundish = []
    for t in tick:
        nm = assets.get(t, ("", ""))[0]
        if nm and FUNDISH.search(nm):
            fundish.append(t)
    if assets:
        print(f"  N2 member tickers whose CURRENT asset-list name reads as a fund / ETF / ETN / leveraged product: {len(fundish):,} tickers, "
              f"{sum(tick[t] for t in fundish):,} member-nights; of them with no type: {sum(1 for t in fundish if not sect.get(t))}")
        for t in sorted(fundish, key=lambda x: -tick[x]):
            flags.append({"kind": "fundish_name_member", "ticker": t, "nights": tick[t], "detail": f"{assets[t][0]} | type "
                          f"{sect.get(t) or 'unknown'}"})
    nosic = [t for t in tick if not (sic.get(t) and sic[t][2])]
    print(f"  N1 no SIC code (no group -> every group cell False): {len(nosic):,} tickers, {sum(tick[t] for t in nosic):,} member-nights "
          f"({sum(tick[t] for t in nosic) / max(n_nights, 1):.2%})")
    asof = Counter((sic[t][0] if t in sic else "absent") for t in tick)
    top = asof.most_common(3)
    print(f"  N1 SIC 'as of' date per member ticker: {', '.join(f'{k} {v:,}' for k, v in top)}; other dates {sum(asof.values()) - sum(v for _k, v in top):,}"
          f" -> every night reads the industry the symbol had on its as-of date, not the one it had that night")
    for t in unk:
        flags.append({"kind": "unknown_type_member", "ticker": t, "nights": tick[t], "detail": assets.get(t, ("", ""))[0]})
    for t in nosic:
        flags.append({"kind": "no_sic_member", "ticker": t, "nights": tick[t], "detail": assets.get(t, ("", ""))[0]})
    # N5: liquid symbols the ^[A-Z]{1,5}$ regex drops (judged on the symbol the export carries)
    from agents.market_intelligence import consolidation_breakout as cb
    rx_out = [t for t in X.tickers if not cb.UNIVERSE_TICKER_RE.fullmatch(t)]
    print(f"  N5 export symbols the ticker regex excludes outright: {len(rx_out):,} (e.g. {', '.join(rx_out[:8])})")
    p = write_flags(Path(args.out), f"pit_inputs_{args.label}.tsv", flags, ["kind", "ticker", "nights", "detail"])
    print(f"flagged rows: {len(flags):,} -> {p}")
    return 0


def _read_minutes(mdirs, d: str, want: set) -> dict:
    """{ticker: [(minute, o, h, l), ...]} for date `d` over one or more minute trees (a later tree / a later block wins)."""
    out = defaultdict(list)
    for mdir in ([mdirs] if isinstance(mdirs, Path) else mdirs):
        p = Path(mdir) / f"{d}.psv.gz"
        if not p.exists():
            continue
        blk = defaultdict(list)
        with gzip.open(p, "rt") as fh:
            for line in fh:
                f = line.rstrip("\n").split("|")
                if len(f) >= 7 and f[0] in want:
                    blk[f[0]].append((int(f[1]), float(f[2]), float(f[3]), float(f[4])))
        for t, rows in blk.items():
            out[t] = rows                  # this tree's block replaces an earlier tree's
    res = {}
    for t, rows in out.items():
        last = {}
        for r in rows:                     # readers keep the LAST block per (date, ticker): a later duplicate minute replaces
            last[r[0]] = r
        res[t] = sorted(last.values())
    return res


def run_entries(args) -> int:
    import pandas as pd
    through = date.fromisoformat(args.through)
    _refuse_sealed(through, "--through")
    usecols = ["ticker", "D", "E", "K", "variant", "status", "reason", "level", "fill", "stop", "width_pct", "fill_minute",
               "retrigger"]
    df = pd.read_csv(args.entries, sep="\t", usecols=usecols, dtype={"ticker": str, "E": str, "D": str}, keep_default_na=False)
    df = df[df["E"] <= through.isoformat()]
    if args.k:
        df = df[df["K"].isin(args.k.split(","))]
    first = df[df["retrigger"].astype(str) == "0"]
    print(f"ENTRIES {args.entries}: {len(df):,} rows (E <= {through}); first breaks {len(first):,}")
    flags = []
    # data abstains by variant (entry-time; L5)
    for v in ("orh5", "orh1"):
        g = first[first["variant"] == v]
        rc = Counter(g["reason"].where(g["status"] == "abstain", g["status"]))
        n = len(g)
        mm = rc.get("minute_daily_mismatch", 0)
        hb = rc.get("minute_high_below_pivot", 0)
        print(f"  {v}: n {n:,}; filled {rc.get('filled', 0):,}; minute_daily_mismatch {mm:,} ({mm / max(n, 1):.2%}); "
              f"minute_high_below_pivot {hb:,} ({hb / max(n, 1):.2%}); no_minutes {rc.get('no_minutes', 0):,}; too_wide "
              f"{rc.get('too_wide', 0):,}")
    fv = first[(first["variant"] == args.variant) & (first["status"] == "filled")].copy()
    fv["fill"] = fv["fill"].astype(float)
    fv["level"] = fv["level"].astype(float)
    fv["stop"] = fv["stop"].astype(float)
    fv["width_pct"] = fv["width_pct"].astype(float)
    fv["fill_minute"] = fv["fill_minute"].astype(int)
    n = len(fv)
    # W2: R cost of exit slippage
    w = fv["width_pct"].to_numpy()
    cost = 0.001 / w
    print(f"  W2 {args.variant} filled first breaks n {n:,}: stop width median {np.median(w):.2%} (P10 {np.percentile(w, 10):.2%}, P90 "
          f"{np.percentile(w, 90):.2%}); 0.1% of price per side = {np.median(cost):.3f} R median, {cost.mean():.3f} R mean, "
          f"{np.percentile(cost, 90):.3f} R at P90 (per exit leg; a round trip with 0.1% more on entry doubles it)")
    # W3: fill at the level vs at the open
    at_level = np.isclose(fv["fill"].to_numpy(), fv["level"].to_numpy() * 1.001, rtol=1e-9)
    print(f"  W3 fills AT the level + 0.1% (the minute opened at/below it): {at_level.sum():,} of {n:,} ({at_level.mean():.1%}); "
          f"the rest at the minute's open (gapped over)")
    # early-close E
    ec = fv[fv["E"].isin(EARLY_CLOSES)]
    print(f"  F1 filled first breaks with E on a 13:00-close day: {len(ec):,} of {n:,}")
    for _, r in ec.iterrows():
        flags.append({"kind": "E_on_early_close", "ticker": r["ticker"], "E": r["E"], "K": r["K"], "detail": f"fill minute {r['fill_minute']}"})
    # L4: the stop from the fill minute's own low
    if args.minutes:
        mdir = [Path(x) for x in args.minutes.split(",")]
        n_chk = n_self = n_late = 0
        extra_w, run_through = [], []
        for E, g in fv.groupby("E"):
            mins = _read_minutes(mdir, E, set(g["ticker"]))
            for _, r in g.iterrows():
                mb = mins.get(r["ticker"])
                if not mb:
                    continue
                fm = int(r["fill_minute"])
                before = [x[3] for x in mb if x[0] < fm]       # lows strictly before the fill minute
                at = [x for x in mb if x[0] == fm]
                if not at:
                    continue
                n_chk += 1
                low_fill = at[0][3]
                lvl = float(r["level"])
                if abs(float(r["fill"]) - lvl * 1.001) < 1e-9 * lvl:
                    run_through.append(at[0][2] / lvl - 1.0)
                if E in EARLY_CLOSES and any(x[0] >= EARLY_CUT_MINUTE for x in mb):
                    n_late += 1
                lb = min(before) if before else None
                if lb is None or low_fill < lb - 1e-12:
                    n_self += 1
                    stop_known = lb                                  # the low of the day the moment before the fill minute
                    if stop_known is not None and stop_known > 0:
                        extra_w.append((stop_known - low_fill) / float(r["fill"]))
                    flags.append({"kind": "stop_from_fill_minute_low", "ticker": r["ticker"], "E": E, "K": r["K"],
                                  "detail": f"fill_minute {fm} low {low_fill} prior low {lb}"})
        ew = np.array(extra_w) if extra_w else np.zeros(1)
        print(f"  L4 the stop IS the fill minute's own low (below every earlier low, or the first minute): {n_self:,} of {n_chk:,} "
              f"checked ({n_self / max(n_chk, 1):.1%}); where an earlier low exists ({len(extra_w):,}) the stop sits a median "
              f"{np.median(ew):.2%} of price ({np.median(ew / np.median(w)) if len(extra_w) else 0:.2f} x the median width) under "
              f"the low known before that minute")
        rt = np.array(run_through) if run_through else np.zeros(1)
        print(f"  W3 at-level fills ({len(run_through):,}): the fill minute's high runs a median {np.median(rt):.2%} above the level "
              f"(P75 {np.percentile(rt, 75):.2%}, P90 {np.percentile(rt, 90):.2%}); in R at the median width: median "
              f"{np.median(rt) / np.median(w):.2f} R, P90 {np.percentile(rt, 90) / np.median(w):.2f} R - the room a stop-market order "
              f"has to fill above level + 0.1%")
        print(f"  F1 of the checked fills on an early-close E, minutes at >= 13:00 present: {n_late}")
    if args.minutes and args.candidates:
        # L5 / F2: which side disagrees on the minute_daily_mismatch abstains (daily bar vendor vs SIP minutes)
        cd = pd.read_csv(args.candidates, sep="\t", usecols=["ticker", "E", "K", "high_E", "low_E"], dtype={"ticker": str},
                         keep_default_na=False)
        hl = {(t, e_, k_): (float(h_), float(l_)) for t, e_, k_, h_, l_ in zip(cd["ticker"], cd["E"], cd["K"], cd["high_E"], cd["low_E"])}
        mm = first[(first["variant"] == args.variant) & (first["reason"] == "minute_daily_mismatch")]
        side = Counter()
        for E, g in mm.groupby("E"):
            mins = _read_minutes([Path(x) for x in args.minutes.split(",")], E, set(g["ticker"]))
            for t, k_ in zip(g["ticker"], g["K"]):
                mb, dh = mins.get(t), hl.get((t, E, k_))
                if not mb or dh is None:
                    side["no_minutes_or_daily"] += 1
                    continue
                mh, ml = max(x[2] for x in mb), min(x[3] for x in mb)
                tags = []
                if dh[0] > mh * 1.01:
                    tags.append("daily_high_above_minutes")
                if mh > dh[0] * 1.01:
                    tags.append("minute_high_above_daily")
                if dh[1] < ml / 1.01:
                    tags.append("daily_low_below_minutes")
                if ml < dh[1] / 1.01:
                    tags.append("minute_low_below_daily")
                side["+".join(tags) or "within_1pct?"] += 1
                flags.append({"kind": "minute_daily_mismatch", "ticker": t, "E": E, "K": k_,
                              "detail": f"daily h/l {dh[0]}/{dh[1]} minutes h/l {mh}/{ml}"})
        # F6: a constant price-SCALE offset between the minute bars (Alpaca, split-only) and the daily bar (the export's vendor)
        # that the 1% guard lets through: the fill / stop come from the minutes, the forward walk from the daily bars, so R mixes
        # two scales. Measured on the FILLED entries: offset = minute high / daily high when high and low agree on one ratio.
        offs, offR, n_cmp = [], [], 0
        for E, g in fv.groupby("E"):
            mins = _read_minutes([Path(x) for x in args.minutes.split(",")], E, set(g["ticker"]))
            for t, k_, w_ in zip(g["ticker"], g["K"], g["width_pct"]):
                mb, dh = mins.get(t), hl.get((t, E, k_))
                if not mb or dh is None or E in EARLY_CLOSES:
                    continue
                n_cmp += 1
                rh, rl = max(x[2] for x in mb) / dh[0], min(x[3] for x in mb) / dh[1]
                if abs(rh - rl) < 0.0005 and abs(rh - 1.0) >= 0.001:
                    offs.append(rh - 1.0)
                    offR.append(abs(rh - 1.0) / float(w_))
                    flags.append({"kind": "minute_daily_scale_offset", "ticker": t, "E": E, "K": k_,
                                  "detail": f"minute/daily {rh:.4f} (high) {rl:.4f} (low); width {float(w_):.4f}"})
        oa = np.abs(np.array(offs)) if offs else np.zeros(1)
        orr = np.array(offR) if offR else np.zeros(1)
        print(f"  F6 filled {args.variant} first breaks whose minute and daily bars sit on DIFFERENT price scales (one ratio for high "
              f"and low, >= 0.1% off): {len(offs):,} of {n_cmp:,} compared ({len(offs) / max(n_cmp, 1):.2%}); offset median "
              f"{np.median(oa):.2%}, max {oa.max():.2%}; as R at each trade's own width: median {np.median(orr):.2f} R, max "
              f"{orr.max():.2f} R (the fill/stop are on the minute scale, every forward daily bar on the other)")
        print(f"  L5 the {len(mm):,} {args.variant} minute_daily_mismatch abstains, by which side disagrees by > 1%: "
              + ", ".join(f"{k} {v:,}" for k, v in side.most_common()))
    p = write_flags(Path(args.out), f"pit_entries_{args.label}.tsv", flags, ["kind", "ticker", "E", "K", "detail"])
    print(f"flagged rows: {len(flags):,} -> {p}")
    return 0


def run_horizon(args) -> int:
    """First breaks (spec key) whose ticker's bars END before E + horizon + 1 sessions while the export runs on: the walk can only end
    'degraded' (dropped from decisive numbers) unless an exit came first. Uses bar AVAILABILITY only, never a price after E."""
    import pandas as pd
    data = Path(args.data)
    through = date.fromisoformat(args.through)
    _refuse_sealed(through, "--through")
    hz = int(args.horizon)
    c = pd.read_csv(args.candidates, sep="\t", usecols=["ticker", "D", "E", "K", "retrigger"], dtype={"ticker": str},
                    keep_default_na=False)
    c = c[(c["E"] <= through.isoformat()) & (c["retrigger"].astype(str) == "0")]
    if args.k:
        c = c[c["K"].isin(args.k.split(","))]
    df = pd.read_csv(data / "daily_closes_all.csv.gz", header=None, usecols=[0, 1], names=["t", "d"], dtype=str, keep_default_na=False)
    spy = sorted(df.loc[df["t"] == "SPY", "d"].unique())
    pos = {d: k for k, d in enumerate(spy)}
    last_ci = len(spy) - 1
    df["ci"] = df["d"].map(pos)
    ci_of = {t: np.sort(g_.to_numpy(dtype=np.int64)) for t, g_ in df.groupby("t")["ci"]}
    last_of = {t: int(a[-1]) for t, a in ci_of.items()}
    brk = _guard(data, args.breaks) or {}
    flags = []
    n = len(c)
    ends, gone, brk_in, holes = 0, Counter(), 0, Counter()
    seal_ci = bisect.bisect_right(spy, SEALED_AFTER.isoformat()) - 1
    n_cross = 0
    for t, E, K in zip(c["ticker"], c["E"], c["K"]):
        e_ci = pos.get(E)
        if e_ci is None:
            continue
        need = e_ci + hz + 1
        n_cross += int(need > seal_ci)
        if need > last_ci:
            ends += 1                                   # the export ends first: an open mark by construction
            continue
        lt = last_of.get(t)
        if lt is not None and lt < need:
            gone[K] += 1
            flags.append({"kind": "data_ends_inside_horizon", "ticker": t, "E": E, "K": K,
                          "detail": f"last bar {spy[lt]} ({lt - e_ci} sessions after E)"})
        a = ci_of.get(t)
        if a is not None and not (lt is not None and lt < need):
            k0 = int(np.searchsorted(a, e_ci))
            seg = a[k0:k0 + hz + 2]
            seg = seg[seg <= need]
            if len(seg) >= 2 and np.any(np.diff(seg) != 1):
                holes[K] += 1
                flags.append({"kind": "missing_session_inside_walk", "ticker": t, "E": E, "K": K,
                              "detail": f"first hole after {spy[int(seg[np.flatnonzero(np.diff(seg) != 1)[0]])]}"})
        if t in brk:
            e_ord = date.fromisoformat(E).toordinal()
            end_ord = date.fromisoformat(spy[min(need, last_ci)]).toordinal()
            b = brk[t]
            if np.any((b > e_ord) & (b <= end_ord)):
                brk_in += 1
                flags.append({"kind": "identity_break_inside_walk", "ticker": t, "E": E, "K": K,
                              "detail": ";".join(date.fromordinal(int(x)).isoformat() for x in b[(b > e_ord) & (b <= end_ord)])})
    print(f"HORIZON {args.candidates}: first breaks (spec key) with E <= {through}: {n:,}; walk window {hz} + 1 sessions")
    print(f"  export ends inside the window (open marks by construction): {ends:,}")
    print(f"  walk window reaches past {SEALED_AFTER} (a discovery R can hold sealed-era prices; L7): {n_cross:,} ({n_cross / max(n, 1):.2%})")
    print(f"  ticker's bars END inside the window while the export runs on (delisted / acquired / renamed): {sum(gone.values()):,} "
          f"({sum(gone.values()) / max(n - ends, 1):.2%} of the {n - ends:,} with a full window) by K {dict(gone)}")
    print(f"  a missing session inside the window (fwd_end cuts there -> 'degraded' unless exited first): {sum(holes.values()):,} "
          f"by K {dict(holes)}")
    if brk:
        print(f"  a symbol identity break falls INSIDE the walk window (not cut by fwd_end): {brk_in:,}")
    p = write_flags(Path(args.out), f"pit_horizon_{args.label}.tsv", flags, ["kind", "ticker", "E", "K", "detail"])
    print(f"flagged rows: {len(flags):,} -> {p}")
    return 0


def run_chain(args) -> int:
    """L10: the chain key (`cb.chain_bases`) is built from the poles of EVERY watch row, including nights AFTER a candidate's D, so a
    later pole can bridge two bases and turn a first break into a retrigger after the fact (documented in
    tests/test_cb_shadow.py::test_a_later_bridging_pole_is_the_documented_difference; never counted). Here every first-or-not label is
    recomputed with only the poles known by that candidate's D, and compared with the batch `retrigger_chain`. No price is read."""
    import pandas as pd
    from agents.market_intelligence import consolidation_breakout as cb
    through = date.fromisoformat(args.through)
    _refuse_sealed(through, "--through")
    w = pd.read_csv(args.watch, sep="\t", usecols=["ticker", "watch_date", "ci", "pole_ci", "pole_date"], dtype={"ticker": str},
                    keep_default_na=False)
    c = pd.read_csv(args.candidates, sep="\t", usecols=["ticker", "D", "E", "K", "pole_ci", "pole_date", "retrigger", "retrigger_chain"],
                    dtype={"ticker": str}, keep_default_na=False)
    c = c[c["E"] <= through.isoformat()]
    ci_of_d = dict(zip(w["watch_date"], w["ci"]))
    wp = {t: (g["ci"].to_numpy(), g["pole_ci"].to_numpy(), g["pole_date"].to_numpy()) for t, g in w.groupby("ticker")}
    flags = []
    n = 0
    flip = Counter()
    for t, g in c.groupby("ticker"):
        g = g.sort_values("E")
        wci, pci, pdt = wp[t]
        order = np.argsort(wci, kind="stable")
        wci, pci, pdt = wci[order], pci[order], pdt[order]
        seen = []                                   # (E, K, pole_ci) of earlier candidates
        for D_, E_, K_, pc, rc in zip(g["D"], g["E"], g["K"], g["pole_ci"], g["retrigger_chain"]):
            dci = ci_of_d[D_]
            k = int(np.searchsorted(wci, dci, side="right"))
            known = set(zip([t] * k, pci[:k].tolist(), pdt[:k].tolist()))
            base = cb.chain_bases(known)
            mine = base[(t, int(pc))]
            causal = int(any(kk == K_ and base.get((t, int(p_))) == mine for (_e, kk, p_) in seen if _e < E_))
            n += 1
            if causal != int(rc):
                flip[(int(rc), causal)] += 1
                flags.append({"kind": "chain_key_uses_a_later_pole", "ticker": t, "E": E_, "K": K_,
                              "detail": f"batch retrigger_chain {int(rc)} causal {causal}"})
            seen.append((E_, K_, int(pc)))
    first_batch = int((c["retrigger_chain"].astype(int) == 0).sum())
    print(f"CHAIN KEY {args.candidates}: {n:,} candidates (E <= {through}); batch first breaks (retrigger_chain 0) {first_batch:,}")
    print(f"  label differs from the point-in-time chain key: {sum(flip.values()):,} ("
          + ", ".join(f"batch {a} -> causal {b}: {v:,}" for (a, b), v in sorted(flip.items())) + ")")
    print(f"  i.e. {flip.get((1, 0), 0):,} breakouts a live system would have taken as a base's FIRST break are dropped by the batch key "
          f"({flip.get((1, 0), 0) / max(first_batch, 1):.2%} of the batch first breaks)")
    p = write_flags(Path(args.out), f"pit_chain_{args.label}.tsv", flags, ["kind", "ticker", "E", "K", "detail"])
    print(f"flagged rows: {len(flags):,} -> {p}")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("lint")
    p.add_argument("--out")
    p = sp.add_parser("calendar")
    p.add_argument("--export", required=True)
    p.add_argument("--minutes")
    p.add_argument("--label", default="export")
    p.add_argument("--out", required=True)
    p = sp.add_parser("overlap")
    p.add_argument("--era-a", required=True)
    p.add_argument("--era-b", required=True)
    p.add_argument("--hist-start", default="2021-09-27")
    p.add_argument("--start", default="2022-03-28")
    p.add_argument("--end", default="2022-06-30")
    p.add_argument("--out", required=True)
    p = sp.add_parser("inputs")
    p.add_argument("--data", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--raw-close", action="store_true")
    p.add_argument("--breaks", action="store_true")
    p.add_argument("--assets")
    p.add_argument("--label", default="export")
    p.add_argument("--out", required=True)
    p = sp.add_parser("entries")
    p.add_argument("--entries", required=True)
    p.add_argument("--minutes")
    p.add_argument("--variant", default="orh5")
    p.add_argument("--candidates", help="candidates TSV (high_E / low_E) -> which side a minute_daily_mismatch disagrees on")
    p.add_argument("--k", default="")
    p.add_argument("--through", default=SEALED_AFTER.isoformat())
    p.add_argument("--label", default="export")
    p.add_argument("--out", required=True)
    p = sp.add_parser("horizon")
    p.add_argument("--data", required=True)
    p.add_argument("--candidates", required=True)
    p.add_argument("--horizon", default=120)
    p.add_argument("--k", default="")
    p.add_argument("--breaks", action="store_true")
    p.add_argument("--through", default=SEALED_AFTER.isoformat())
    p.add_argument("--label", default="export")
    p.add_argument("--out", required=True)
    p = sp.add_parser("chain")
    p.add_argument("--watch", required=True)
    p.add_argument("--candidates", required=True)
    p.add_argument("--through", default=SEALED_AFTER.isoformat())
    p.add_argument("--label", default="export")
    p.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    return {"lint": run_lint, "calendar": run_calendar, "overlap": run_overlap, "inputs": run_inputs, "entries": run_entries,
            "horizon": run_horizon, "chain": run_chain}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
