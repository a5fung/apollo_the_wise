#!/usr/bin/env python3
"""#314 replay — STEP 0's population: the two eras loaded under the seal, the raw close, the price / dollar-volume bands, the symbol rules,
the 120-consecutive-session history, the identity guard's break classification, the owner record / company key / type / gone rules, the
distribution flagger, the adjustment-event lists, the two detector passes (plan §Method / population, §STEP 0). Walks nothing.

READINGS (continued from ps_common; the main loop decides):
  R6  STEP 0 is split into PHASES around the pulls it needs — the plan's "derive and count the populations; walk nothing" needs the
      Polygon reference records (for the type and the CIK) and the EDGAR / XBRL facts (for the cap, which sets the detector's tier),
      and those pulls need the population's own CIKs. Phase `derive` (reference pull in hand): the funnel through history, the break
      classes, the owners, the company keys, the candidate CIK list (R7). Phase `climax` (facts + submissions pull in hand): the cap and
      the two detector passes -> climax_list.tsv. Phase `features` (news + instances + corporate actions in hand): features.tsv, the
      suspects and their evidence class.
  R7  The CIK set for the EDGAR pull is bounded by an EXACT NECESSARY-CONDITION filter at the most permissive tier (prior move >= 50%)
      and the P2 dollar-volume floor ($2M), vectorized: base_low is the low of a session inside the last 60, so it is >= the 60-session
      minimum low and prior_move <= close / min_low_60 - 1; the SMA-50 extension, the velocity test, the days-up streak (>= 3), the
      2% gap and the 20-session volume high are computed exactly as the detector does. A night failing any of them is not a climax at
      ANY cap, so the owners of the surviving nights are every company whose cap can matter. The registered detector pass then runs on
      EVERY band night (the funnel counts each gate), never on the pre-filter's survivors only.
  R8  The funnel's `void_adjustment_event` and `duplicate_company_night` rows sit before the detector gates in the plan's printed order
      but are defined on CLIMAX rows (a void keeps its beside row, a duplicate keeps one of the pair); they are computed on the climax
      list and printed in the plan's position with that note.
  R9  The distribution flagger over ALL bars (the climax-independent OPLN / ZWS control) and the climax-tied `distribution_suspects.tsv`
      are TWO outputs: `distribution_flags.tsv` (every ticker-session with open / prior close - 1 <= -0.25, prior close = the ticker's
      previous bar; a missing session between the two is a printed column) and `distribution_suspects.tsv` (the climaxes whose
      D0+1..D0+7 holds one). The gap is read on the file's split-adjusted bars (a true split is absorbed there).
  R10 Era A's refetched symbol takes the record the build chose: `08_build_v2.py` keeps the LATEST-delisted record per ticker
      (`sort_values("delisted").drop_duplicates("ticker", keep="last")`), so that is "its record in refetch_combined_records_1023.tsv".
  R11 The straggler / placeholder re-resolution picks, among the symbol's pinned reference records, the delisted record with the
      smallest `delisted_utc` on or after the series' last bar, else the active record when the series runs to the file's end; a
      symbol with neither stays unresolved (date unknown, type / CIK from the record when present, gone unknown).
  R12 "460 of the 1,885 table-untyped symbols pass the symbol rules and reach $2M a day" and "194 of the 310 jump symbols reach a
      20-session dollar volume of $2M" both reproduce EXACTLY under one reading: "reach $2M" = the symbol's 20-session rolling MEDIAN
      dollar volume (close x volume) is >= $2M on some bar, and "pass the symbol rules" includes the W / U / R suffix rule (1,453 of the
      1,885 do; 460 of those reach the median; 194 of the 310 jump symbols reach it). The mean and single-day readings give 658 / 1,174
      and 216 / 263 and are printed beside, never claimed.
  R13 An applied `jump` inside the forward walk span (D0+1..D0+7) is not voided (the plan voids only the 120-row window and the
      adjustment events); it is counted `jump_in_walk` and printed. An era-B owner's `delisted_utc` inside the walk span cuts the walk
      there (the later bars belong to a later issuer) -> `ended_mid_walk`.
  R14 (revised 10-28 by the continuation card) The owner rule's "a record whose `name` disagrees with the SEC submissions `name` ...
      = unknown" makes the OWNER unknown (type unknown -> P2's unknown-type row; CIK unknown -> no cap, keyed by symbol), so it is
      applied in the CLIMAX phase, before population assignment (the submissions pull is in hand there; the candidate CIK list of
      derive was built before it, which only makes that list a superset). Equality after `ps_features.name_normal` (SEC's trailing
      state-of-incorporation and '/NEW/' tags — 'BANK OF AMERICA CORP /DE/', 'VALERO ENERGY CORP/TX' — and a trailing 'new',
      stripped first: added 10-28 after review, the first build read those genuine matches as disagreements; then case,
      punctuation, corporate suffix words); every disagreement listed. Derive carries the record as is and says so.
  R68 (review 10-28) The 15 `alias_outside_span` symbols own each night by `owner_alias`: the DELISTED record of the symbol with the
      smallest delisted_utc >= D0, else unknown (`no_record_covering_d0`) — the first build reused era B's `owner_B`, whose fallback
      to the ACTIVE record handed a leftover night after the old record's date to the later holder. Derive and the detector pass
      assert no alias row is owned by an active record.
  R33 The earlier-issuer lower bound is written for ACTIVE-owned era-B nights; a DELISTED-owned night can reach an earlier company's
      bars the same way (a symbol held by three issuers). Applied to every era-B night: the 120-row window's first bar may not be
      dated on or before the latest `delisted_utc` among the symbol's records of a DIFFERENT company key whose `delisted_utc` < D0
      (for an active-owned night that is exactly the plan's text: every delisted record is < D0). A night with no owning record
      compares against every record delisted before D0.
  R34 "Company key" counts for the jump / hole evidence use the key LITERALLY (CIK, else composite FIGI, else share-class FIGI, else
      the symbol): two empty-keyed records on one symbol share the symbol key = one company; a keyed and an empty-keyed record are two
      keys = multi-company. (The inherited code counted every empty-keyed record as its own company.)
  R35 The open-at-the-seal climaxes (era B, D0 2024-12-20 .. 12-31, the 7 sessions after the last settling D0) are DETECTED and listed
      with `open_at_seal = 1`; they are never walked and never in a number (the plan: "counted, never in a number"). Era A has none:
      era B owns every D0 after 2022-03-16.
  R36 The exact pre-filter (R7) is a SUPERSET by construction only up to floating point; each continuous comparison is loosened by a
      relative 1e-9 so a boundary night can never be dropped by rounding (the cumsum SMA vs the detector's sum). The 60-session
      minimum low is taken over POSITIVE lows (a zero / negative low elsewhere in the window cannot be the detector's base when its
      base low is > 0).
  R37 "Pre-break holder" (era A): a night dated strictly before the symbol's last APPLIED break (break_mask puts the break-date night
      itself inside its window, so it is `identity_break`) is ADMITTED with type / CIK unknown, keyed by its symbol, gone unknown —
      the owner bullet's "= type / CIK unknown, counted" — and printed beside `identity_break` in the funnel, not removed by it.
      It overrides the alias date rule on the two leftover symbols that carry a break (RSLS, KOOL).
  R61 The M1 re-resolution applies to REFETCH-sourced owners only (the plan's bullet sits in the refetched symbol's owner rule: the 31
      straggler placeholders, VIAC / VIACA, the 46 empty-keyed refetch records). An original symbol keeps its active Polygon record
      even when that record is empty-keyed (keyed by its symbol, gone "no"): re-resolving it to a delisted record would make it gone
      through a path the plan's subset test forbids.
  R38 Type when a record exists but carries no type (VIAC / VIACA after an unresolved re-resolution): unknown, never the fallback
      table (the plan: the table is used "only where the symbol has NO Polygon record"; VIAC "may stay" unknown). Era B: a symbol
      that has records but none covering D0 is unknown for the same reason.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ps_common as X  # noqa: E402

GuardStop = X.GuardStop


# ═════════════════════════════════════════════════════════════════════════════════════════════
# an era in memory
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Era:
    name: str
    D: object                      # asis_common.Daily (flat arrays)
    cal: list                      # ISO sessions (the era's calendar file content)
    cal_file: str                  # the calendar file this era's rows carry
    first_d0: int                  # session index of the first scorable D0
    last_d0: int                   # the last D0 that can SETTLE (era B: 2024-12-19)
    raw: np.ndarray                # RAW close per flat row
    fac: np.ndarray                # raw / adjusted per flat row
    row_tid: np.ndarray            # ticker id per flat row
    sym_ok: np.ndarray             # per ticker
    contig: np.ndarray             # per flat row: the 120 bars ending here are consecutive sessions
    scorable: np.ndarray           # per flat row: ci in [first_d0, last_d0]
    dv: np.ndarray
    band: np.ndarray               # raw >= $1 and dv >= $2M
    p1: np.ndarray                 # raw >= $5 and dv >= $10M
    info: dict = field(default_factory=dict)
    splits: dict = field(default_factory=dict)      # era B only
    detect: "np.ndarray | None" = None              # per flat row: ci in [first_d0, last_detect] (R35: era B adds the 7 open-at-seal sessions)
    last_detect: int = -1

    @property
    def tickers(self): return self.D.tickers
    @property
    def tid(self): return self.D.tid

    def rows_of(self, t: int) -> tuple:
        a, b = int(self.D.start[t]), int(self.D.stop[t])
        return a, b

    def dates_of(self, t: int) -> list:
        a, b = self.rows_of(t)
        return [self.cal[k] for k in self.D.ci[a:b]]

    def bar_index(self, ticker: str, d: str) -> int:
        """The flat row of (ticker, d) or -1."""
        t = self.tid.get(ticker)
        if t is None:
            return -1
        a, b = self.rows_of(t)
        ci_t = self.D.ci[a:b]
        target = self._cal_index(d)
        if target < 0:
            return -1
        pos = np.searchsorted(ci_t, target)
        if pos < len(ci_t) and ci_t[pos] == target:
            return a + int(pos)
        return -1

    def _cal_index(self, d: str) -> int:
        import bisect
        i = bisect.bisect_left(self.cal, d)
        return i if i < len(self.cal) and self.cal[i] == d else -1


def symbol_rules(tickers: list) -> dict:
    """Per ticker: the live pattern, the exchange test symbols, the W / U / R suffix (5 letters)."""
    pat = np.array([bool(X.TICKER_RE.fullmatch(t)) for t in tickers])
    test = np.array([X.is_test_symbol(t) for t in tickers])
    suffix = np.array([t[-1] if len(t) == 5 and t.isalpha() and t.isupper() and t[-1] in X.WUR_SUFFIX else "" for t in tickers])
    return {"pattern_ok": pat, "test_symbol": test, "suffix": suffix, "sym_ok": pat & ~test}


def _contig(D, window: int = X.HISTORY) -> np.ndarray:
    out = np.zeros(len(D.ci), dtype=bool)
    for t in range(len(D.tickers)):
        a, b = int(D.start[t]), int(D.stop[t])
        out[a:b] = X.contiguous_window_mask(D.ci[a:b], window)
    return out


def load_era(P: X.Paths, era: str, say=print) -> Era:
    """Era A = the v2 file whole (cut at its own end, R4); era B = the Polygon file through the seal. Asserts the calendar."""
    if era == "A":
        D, info = X.load_daily_subset(P.export_A, keep=None, cut=X.A_LAST)
        cal = [d.isoformat() for d in D.cal]
        with open(P.sessions_A) as fh:
            sess = [ln.strip() for ln in fh if ln.strip()]
        if cal != sess:
            raise GuardStop(f"era A: SPY's sessions ({len(cal)}) differ from sessions.txt ({len(sess)})")
        cal_file = P.sessions_A
        raw = X.load_raw_close(Path(P.raw_A), D)                 # asserts the raw file's key set == the export's (both ways)
        fac = raw / D.c
        splits = {}
        first_d0 = X.HISTORY - 1
        last_d0 = cal.index(X.A_D0_LAST) if X.A_D0_LAST in cal else len(cal) - 1 - X.WALK_AFTER
    elif era == "B":
        D, info = X.load_daily_subset(P.export_B, keep=None, cut=X.CUT_B)
        cal = [d.isoformat() for d in D.cal]
        if cal[-1] > X.CUT_B:
            raise GuardStop("era B: a session after the seal survived the read")
        cal_file = P.calendar_B
        splits = X.load_splits(Path(P.splits_B), through=date.fromisoformat(X.SPLITS_THROUGH))
        fac = np.ones(len(D.c))
        for t, tk in enumerate(D.tickers):
            s = splits.get(tk)
            if s:
                a, b = int(D.start[t]), int(D.stop[t])
                fac[a:b] = X.factor_by_bar([D.cal[k] for k in D.ci[a:b]], s)
        raw = D.c * fac
        first_d0 = X.HISTORY - 1
        last_d0 = len(cal) - 1 - X.WALK_AFTER
    else:
        raise ValueError(era)
    n = len(D.c)
    row_tid = np.repeat(np.arange(len(D.tickers)), D.stop - D.start)
    rules = symbol_rules(D.tickers)
    contig = _contig(D)
    scorable = (D.ci >= first_d0) & (D.ci <= last_d0)
    dv = D.c * D.v
    band = (raw >= X.BAND_RAW_FLOOR) & (dv >= X.BAND_DV_FLOOR)
    p1 = (raw >= X.P1_RAW_FLOOR) & (dv >= X.P1_DV_FLOOR)
    last_detect = last_d0 if era == "A" else len(cal) - 1
    detect = (D.ci >= first_d0) & (D.ci <= last_detect)
    e = Era(era, D, cal, cal_file, first_d0, last_d0, raw, fac, row_tid, rules["sym_ok"], contig, scorable, dv, band, p1, dict(info), splits,
            detect, last_detect)
    e.info.update({"pattern_ok": rules["pattern_ok"], "test_symbol": rules["test_symbol"], "suffix": rules["suffix"],
                   "rows": n, "symbols": len(D.tickers), "sessions": len(cal)})
    return e


def nights_mask(e: Era) -> np.ndarray:
    """The ticker-nights the funnel starts from: symbol rules, a detectable D0 (scorable + era B's open-at-seal sessions, R35),
    consecutive history."""
    return e.sym_ok[e.row_tid] & e.detect & e.contig


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the pinned tables
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_type_table(path: str) -> tuple:
    """small_pulls.psv `sectype|SYM|TYPE|EXCH` -> ({symbol: type}, stats). Two different types for one symbol = a conflict (expected 0)."""
    types, seen, rows, conflicts = {}, Counter(), 0, 0
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            f = ln.rstrip("\n").split("|")
            if f[0] != "sectype" or len(f) < 3:
                continue
            rows += 1
            seen[f[1]] += 1
            if f[1] in types and types[f[1]] != f[2]:
                conflicts += 1
            types.setdefault(f[1], f[2])
    return types, {"rows": rows, "symbols": len(types), "twice": sum(1 for v in seen.values() if v > 1), "conflicts": conflicts}


def load_sic_types(path: str) -> dict:
    """cb702_sic.psv `SYM|asof|http|sic|desc|TYPE` -> {symbol: type} (the fallback behind the type table)."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            f = ln.rstrip("\n").split("|")
            if len(f) >= 6 and f[5]:
                out[f[0]] = f[5]
    return out


def load_guard(path: str) -> dict:
    """symbol_guard.tsv -> {symbol: [(iso date, kind), ...]} read BY COLUMN NAME (as runner.load_breaks does)."""
    lines = Path(path).read_text().splitlines()
    head = lines[0].split("\t")
    k_sym, k_brk = head.index("symbol"), head.index("breaks")
    out = {}
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) <= k_brk or not f[k_brk]:
            continue
        out[f[k_sym]] = sorted((x.split(":")[0], x.split(":")[1]) for x in f[k_brk].split(";") if ":" in x)
    return out


def guard_symbols(path: str) -> list:
    lines = Path(path).read_text().splitlines()
    k = lines[0].split("\t").index("symbol")
    return [ln.split("\t")[k] for ln in lines[1:] if ln.strip()]


def break_classes(guard: dict) -> Counter:
    c = Counter()
    for brks in guard.values():
        kinds = {k for _d, k in brks}
        c["jump_only" if kinds == {"jump"} else "hole_only" if kinds == {"hole"} else "both"] += 1
    c["symbols"] = len(guard)
    return c


def load_adj_events(path: str, cut: str) -> list:
    """The `adj_event` rows of a price-flags table -> [(ticker, date)], asserted dated <= cut."""
    df = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, usecols=["check", "klass", "ticker", "date"])
    ev = df[df["check"] == "adj_event"]
    out = sorted(set(zip(ev["ticker"], ev["date"])))
    bad = [d for _t, d in out if d > cut]
    if bad:
        raise GuardStop(f"adjustment events dated after {cut}: {bad[:5]}")
    return out


def adj_event_rows(path: str) -> int:
    """The number of `adj_event` ROWS of a price-flags table (the plan's 93 / 67 count rows; three era-A rows repeat a (ticker, date))."""
    df = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, usecols=["check"])
    return int((df["check"] == "adj_event").sum())


def sic_names(path: str) -> int:
    """The names of the SIC pull (one row each; the plan's 3,942), typed or not."""
    with open(path, encoding="utf-8") as fh:
        return len({ln.split("|", 1)[0] for ln in fh if ln.strip()})


def load_dedupe(path: str) -> list:
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False).to_dict("records")


def alias_outside_span(dedupe: list, e: Era) -> dict:
    """R(H2): every dropped_symbol still in v2 -> {symbol: {'outside': n, 'inside': n, 'first', 'last', 'kept'}}; rows INSIDE the span
    are a runner refusal (the file is not the deduped one)."""
    out = {}
    for r in dedupe:
        s = r["dropped_symbol"]
        t = e.tid.get(s)
        if t is None:
            continue
        a, b = e.rows_of(t)
        ds = np.array(e.dates_of(t))
        inside = int(((ds >= r["first"]) & (ds <= r["last"])).sum())
        rec = out.setdefault(s, {"outside": 0, "inside": 0, "spans": [], "kept": r["kept_symbol"], "n": b - a})
        rec["inside"] += inside
        rec["spans"].append((r["first"], r["last"], r["kept_symbol"], r["kind"]))
    for s, rec in out.items():
        t = e.tid[s]
        ds = np.array(e.dates_of(t))
        ins = np.zeros(len(ds), dtype=bool)
        for f0, l0, _k, _kind in rec["spans"]:
            ins |= (ds >= f0) & (ds <= l0)
        rec["inside"], rec["outside"] = int(ins.sum()), int((~ins).sum())
    return out


def alias_map_in_span(dedupe: list) -> list:
    """[(dropped, kept, first, last)] — the alias map applies only to dates inside its span (round 4)."""
    return [(r["dropped_symbol"], r["kept_symbol"], r["first"], r["last"]) for r in dedupe]


def load_refetch_records(path: str) -> dict:
    """refetch_combined_records_1023.tsv -> {ticker: record} (R10: the latest-delisted record per ticker, as the build chose)."""
    df = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    df = df.sort_values("delisted", kind="stable").drop_duplicates("ticker", keep="last")
    return {r["ticker"]: {**r, "_source": "refetch_record"} for r in df.to_dict("records")}


def refetch_set(P: X.Paths, e: Era) -> tuple:
    """(the refetch-sourced symbols = records' tickers ∩ v2's, v2 minus cb702_pre's guard symbol list) — both expected 2,669 and equal."""
    recs = pd.read_csv(P.refetch_records, sep="\t", dtype=str, keep_default_na=False)
    a = set(recs["ticker"]) & set(e.tickers)
    b = set(e.tickers) - set(guard_symbols(P.guard_pre)) if os.path.exists(P.guard_pre) else None
    return a, b


def ended_early(e: Era, end: str) -> int:
    """Symbols whose last bar is dated before the era's last session."""
    last = np.array([e.cal[e.D.ci[int(e.D.stop[t]) - 1]] for t in range(len(e.tickers))])
    return int((last < end).sum())


def rolling_mean(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def dv20_max_by_ticker(e: Era, how: str = "median") -> np.ndarray:
    """R12: per ticker the max over its bars of the 20-session rolling MEDIAN (the plan's reading) or mean dollar volume (NaN under 20 bars)."""
    out = np.full(len(e.tickers), np.nan)
    for t in range(len(e.tickers)):
        a, b = e.rows_of(t)
        if b - a >= 20:
            s = pd.Series(e.dv[a:b]).rolling(20)
            out[t] = np.nanmax((s.median() if how == "median" else s.mean()).to_numpy())
    return out


def dv20_max_by_ticker_subset(e: Era, ids: list, how: str = "median") -> np.ndarray:
    """R12 on a subset of ticker ids (the dry run's three counts): the max over each ticker's bars of the 20-session rolling median /
    mean dollar volume (NaN under 20 bars)."""
    out = np.full(len(ids), np.nan)
    for k, t in enumerate(ids):
        a, b = e.rows_of(t)
        if b - a >= 20:
            r = pd.Series(e.dv[a:b]).rolling(20)
            out[k] = np.nanmax((r.median() if how == "median" else r.mean()).to_numpy())
    return out


def dv_max_by_ticker(e: Era) -> np.ndarray:
    return np.array([e.dv[a:b].max() if b > a else np.nan for a, b in (e.rows_of(t) for t in range(len(e.tickers)))])


# ═════════════════════════════════════════════════════════════════════════════════════════════
# breaks (the identity guard, classified by the written evidence rule)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def fac_change_on(e: Era, symbol: str, d: str) -> tuple:
    """Era A: the raw / adjusted factor on the jump date against the prior bar's -> (changed > 1%, relative change | None)."""
    i = e.bar_index(symbol, d)
    if i < 0:
        return (False, None)
    a, _b = e.rows_of(e.tid[symbol])
    if i <= a:
        return (False, None)
    rel = abs(X.num(e.fac[i]) / X.num(e.fac[i - 1]) - 1.0)
    return (rel > X.JUMP_FAC_CHANGE, rel)


def split_on(e: Era, symbol: str, d: str) -> bool:
    """Era B: a `cb702_splits.psv` split executing on the jump date."""
    return any(ex.isoformat() == d for ex, _r in e.splits.get(symbol, []))


def classify_breaks(e: Era, guard: dict, company_count: "dict | None") -> list:
    """`breaks_applied.tsv` rows: symbol, date, kind, evidence, applied (yes / no). `company_count` = {symbol: number of distinct company
    keys among its Polygon records} (None = the pull is not in hand: the company evidence reads `pending`). A `jump` is applied with a
    factor change (era A) / a split on the date (era B) or on a multi-company symbol; a no-record symbol keeps the guard's reading;
    a one-company jump with neither is `jump_unevidenced` (not applied). A `hole` is always a session hole (applied: the window rule
    already excludes it); its company evidence decides the TYPE of the nights before it (era A)."""
    rows = []
    for s in sorted(guard):
        nrec = None if company_count is None else company_count.get(s)
        company = ("pending" if company_count is None else "no_record" if nrec is None or nrec == 0 else
                   "multi_company" if nrec >= 2 else "one_company")
        for d, kind in guard[s]:
            if kind == "jump":
                if e.name == "A":
                    chg, rel = fac_change_on(e, s, d)
                    fac_ev = f"fac_change={rel:.4f}" if rel is not None else "fac_change=no_bar"
                else:
                    chg, fac_ev = split_on(e, s, d), ""
                    fac_ev = "split_on_date" if chg else "no_split_on_date"
                if chg:
                    applied, ev = "yes", f"{fac_ev};{company}"
                elif company == "multi_company":
                    applied, ev = "yes", f"{fac_ev};multi_company"
                elif company == "no_record":
                    applied, ev = "yes", f"{fac_ev};no_record(guard kept)"
                elif company == "pending":
                    applied, ev = "pending", f"{fac_ev};pending_pull"
                else:
                    applied, ev = "no", f"{fac_ev};one_company:jump_unevidenced"
            else:
                applied, ev = "yes", f"session_hole;{company}"
            rows.append({"symbol": s, "date": d, "kind": kind, "evidence": ev, "applied": applied})
    return rows


def applied_breaks(rows: list) -> dict:
    """{symbol: sorted ordinals of APPLIED breaks} — what `--breaks` carries."""
    out = defaultdict(list)
    for r in rows:
        if r["applied"] == "yes":
            out[r["symbol"]].append(X.ord_of(r["date"]))
    return {s: np.array(sorted(v), dtype=np.int64) for s, v in out.items()}


def unevidenced_jumps(rows: list) -> dict:
    out = defaultdict(list)
    for r in rows:
        if r["kind"] == "jump" and r["applied"] == "no":
            out[r["symbol"]].append(X.ord_of(r["date"]))
    return {s: np.array(sorted(v), dtype=np.int64) for s, v in out.items()}


def break_window_mask(e: Era, brk: dict, window: int = X.HISTORY) -> np.ndarray:
    """Per flat row: a break of `brk` falls inside the `window` bars ending here (runner.break_mask, window = 120)."""
    out = np.zeros(len(e.D.ci), dtype=bool)
    if not brk:
        return out
    cal_ord = np.array([X.ord_of(d) for d in e.cal], dtype=np.int64)
    for s, b in brk.items():
        t = e.tid.get(s)
        if t is None:
            continue
        a, z = e.rows_of(t)
        out[a:z] = X.break_mask(cal_ord[e.D.ci[a:z]], b, window=window)
    return out


def last_applied_break(rows: list, company_count: "dict | None") -> dict:
    """Era A: {symbol: ordinal of the symbol's last APPLIED break that unknowns the nights before it} — an applied jump, or a hole on a
    multi-company symbol. A hole on a one-company symbol keeps the owner's type (`pre_hole`)."""
    out = {}
    for r in rows:
        if r["kind"] == "jump" and r["applied"] == "yes":
            out[r["symbol"]] = max(out.get(r["symbol"], 0), X.ord_of(r["date"]))
        elif r["kind"] == "hole" and company_count is not None and (company_count.get(r["symbol"]) or 0) >= 2:
            out[r["symbol"]] = max(out.get(r["symbol"], 0), X.ord_of(r["date"]))
    return out


def hole_before_mask(e: Era, guard: dict, rows: list, company_count: "dict | None") -> np.ndarray:
    """Era A `pre_hole`: nights dated before a hole on a ONE-company symbol (the owner's type kept, flagged)."""
    out = np.zeros(len(e.D.ci), dtype=bool)
    cal_ord = np.array([X.ord_of(d) for d in e.cal], dtype=np.int64)
    for r in rows:
        if r["kind"] != "hole":
            continue
        n = None if company_count is None else company_count.get(r["symbol"])
        if company_count is not None and (n or 0) >= 2:
            continue
        t = e.tid.get(r["symbol"])
        if t is None:
            continue
        a, z = e.rows_of(t)
        out[a:z] |= cal_ord[e.D.ci[a:z]] < X.ord_of(r["date"])
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the distribution flagger (R9) — over all bars, independent of the climax list
# ═════════════════════════════════════════════════════════════════════════════════════════════
def distribution_flags(e: Era) -> pd.DataFrame:
    """Every (ticker, session) whose open / prior close - 1 <= -0.25 (prior close = the ticker's previous bar), with the hint column:
    the new listings (first bar) within [-2, +1] sessions of the gap date."""
    n = len(e.D.c)
    same = np.zeros(n, dtype=bool)
    same[1:] = e.row_tid[1:] == e.row_tid[:-1]
    gap = np.full(n, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        gap[1:] = e.D.o[1:] / e.D.c[:-1] - 1.0
    hit = same & (gap <= X.GAP_CUT) & (e.D.c[np.maximum(np.arange(n) - 1, 0)] > 0)
    idx = np.flatnonzero(hit)
    first_ci = e.D.ci[e.D.start]                                   # each ticker's first session index
    order = np.argsort(first_ci, kind="stable")
    fc_sorted = first_ci[order]
    rows = []
    for i in idx:
        ci = int(e.D.ci[i])
        lo, hi = ci + X.CA_WINDOW[0], ci + X.CA_WINDOW[1]
        a, b = np.searchsorted(fc_sorted, lo, side="left"), np.searchsorted(fc_sorted, hi, side="right")
        listed = [e.tickers[k] for k in order[a:b]]
        rows.append({"ticker": e.tickers[e.row_tid[i]], "gap_date": e.cal[ci], "gap": round(X.num(gap[i]), 6),
                     "prior_close": X.num(e.D.c[i - 1]), "open": X.num(e.D.o[i]),
                     "hole_between": int(e.D.ci[i] - e.D.ci[i - 1] != 1),
                     "n_new_listings": len(listed), "new_listings": "|".join(listed[:25])})
    return pd.DataFrame(rows, columns=["ticker", "gap_date", "gap", "prior_close", "open", "hole_between", "n_new_listings", "new_listings"])


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the overlap (printed; decides nothing)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def overlap_capture(e: Era) -> pd.DataFrame:
    """Era A's closes on the overlap sessions (>= 2021-09-27) keyed by (ticker, date)."""
    m = np.array([d >= X.B_FIRST for d in e.cal])[e.D.ci]
    idx = np.flatnonzero(m)
    return pd.DataFrame({"ticker": [e.tickers[k] for k in e.row_tid[idx]], "date": [e.cal[k] for k in e.D.ci[idx]], "c_a": e.D.c[idx]})


def overlap_compare(e: Era, cap: pd.DataFrame) -> dict:
    m = np.array([d <= X.A_LAST for d in e.cal])[e.D.ci]
    idx = np.flatnonzero(m)
    b = pd.DataFrame({"ticker": [e.tickers[k] for k in e.row_tid[idx]], "date": [e.cal[k] for k in e.D.ci[idx]], "c_b": e.D.c[idx]})
    j = cap.merge(b, on=["ticker", "date"], how="inner")
    diff = (np.abs(j["c_a"].to_numpy() / j["c_b"].to_numpy() - 1.0) > X.OVERLAP_DIFF)
    return {"shared": int(len(j)), "differ": int(diff.sum()), "share": float(diff.mean()) if len(j) else float("nan")}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the Polygon reference records: owners, company keys, types, the gone test (STEP 0 derive)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_reference(path: str) -> dict:
    """polygon_reference.jsonl.gz (one record per line, `_pull` = active | delisted) -> {ticker: [records]}."""
    by = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for ln in fh:
            if not ln.strip():
                continue
            r = json.loads(ln)
            r["_delisted"] = (r.get("delisted_utc") or "")[:10]
            r["_cik"] = cik10(r.get("cik"))
            by[r["ticker"]].append(r)
    return dict(by)


REF_DUP_FIELDS = ("ticker", "_pull", "cik", "composite_figi", "share_class_figi", "delisted_utc")


def reference_duplicates(ref: dict) -> dict:
    """R63: {ticker: extra copies} of EXACT duplicate records (same ticker, pull, CIK, both FIGIs, delisted_utc) — a retried pull that
    appended to its own partial file would double every record and turn each delisted owner into `two_delisted_same_date`."""
    out = {}
    for t, recs in ref.items():
        c = Counter(tuple(str(r.get(k) or "") for k in REF_DUP_FIELDS) for r in recs)
        extra = sum(v - 1 for v in c.values() if v > 1)
        if extra:
            out[t] = extra
    return out


def cik10(v) -> str:
    if v is None or v == "":
        return ""
    s = str(v).strip()
    return s.zfill(10) if s.isdigit() else s


def company_key_of(rec: "dict | None", symbol: str, alias_symbol: "str | None" = None) -> tuple:
    """(key, source): the record's CIK, else its composite FIGI, else its share-class FIGI, else the symbol after the alias map."""
    if rec:
        if rec.get("_cik") or cik10(rec.get("cik")):
            return ("cik:" + (rec.get("_cik") or cik10(rec.get("cik"))), "cik")
        if rec.get("composite_figi"):
            return ("cfigi:" + rec["composite_figi"], "composite_figi")
        if rec.get("share_class_figi"):
            return ("sfigi:" + rec["share_class_figi"], "share_class_figi")
    return ("sym:" + (alias_symbol or symbol), "symbol")


def company_counts(ref: dict) -> dict:
    """{symbol: number of DISTINCT company keys among its records} — the key read literally (R34): two empty-keyed records on one
    symbol share the symbol key."""
    return {s: len({company_key_of(r, s)[0] for r in recs}) for s, recs in ref.items()}


def active_record(recs: list) -> "dict | None":
    act = [r for r in recs if r.get("active") is True or r.get("_pull") == "active"]
    return act[0] if act else None


def delisted_records(recs: list) -> list:
    return sorted([r for r in recs if r.get("_delisted")], key=lambda r: r["_delisted"])


def owner_B(recs: list, d0: str) -> tuple:
    """Era B date rule: the delisted record with the smallest delisted_utc >= D0 if any, else the active record; none = unknown.
    Two delisted records sharing that date = unknown. -> (record | None, path)."""
    if not recs:
        return (None, "no_record")
    dl = [r for r in delisted_records(recs) if r["_delisted"] >= d0]
    if dl:
        first = dl[0]["_delisted"]
        tie = [r for r in dl if r["_delisted"] == first]
        if len(tie) > 1:
            return (None, "two_delisted_same_date")
        return (dl[0], "delisted_date_rule")
    act = active_record(recs)
    return (act, "active") if act else (None, "no_record_covering_d0")


def owner_alias(recs: list, d0: str) -> tuple:
    """The 15 dedupe leftovers (`alias_outside_span`, plan §Dedupe leftovers): the DELISTED record of the symbol whose delisted_utc is the
    smallest >= D0, else unknown — NEVER the later holder's active record (owner_B's active fallback is era B's rule, not this one).
    Two delisted records sharing that date = unknown. -> (record | None, path)."""
    dl = [r for r in delisted_records(recs) if r["_delisted"] >= d0 and not is_active_record(r)]
    if not dl:
        return (None, "no_record_covering_d0")
    if len(dl) > 1 and dl[1]["_delisted"] == dl[0]["_delisted"]:
        return (None, "two_delisted_same_date")
    return (dl[0], "alias_date_rule")


def is_active_record(r: "dict | None") -> bool:
    return bool(r) and (r.get("active") is True or r.get("_pull") == "active")


def assert_alias_owners(nt) -> None:
    """The plan's WOULD-FAIL-IF 'an alias_outside_span row typed by ... a later holder's record': no such row owned by an active record."""
    m = ((nt.flags & F_ALIAS_OUTSIDE) != 0) & (nt.owner >= 0)
    bad = sorted({nt.recs[o].get("ticker", "") for o in np.unique(nt.owner[m]) if is_active_record(nt.recs[o])})
    if bad:
        raise GuardStop(f"alias_outside_span rows owned by an ACTIVE (later-holder) record: {', '.join(bad)}")


class FormerSymbols:
    """R67: era A keys every series by TODAY's symbol (META holds Facebook's 2016-22 bars) while Polygon news is tagged with the symbol in
    use when the item was published. For an era-A night, the symbol the company used at D0 = the ticker of a DELISTED record of the same
    security under ANOTHER symbol with the smallest delisted_utc >= D0 — same share-class FIGI, or same composite FIGI, or the same CIK
    and type when the share-class FIGIs do not disagree (two share classes of one company are never a rename)."""

    def __init__(self, ref: dict):
        self.by = defaultdict(list)
        for recs in ref.values():
            for r in recs:
                if not r.get("_delisted") or is_active_record(r):
                    continue
                for k in (("s", r.get("share_class_figi")), ("c", r.get("composite_figi")), ("k", r.get("_cik"))):
                    if k[1]:
                        self.by[k].append(r)

    def at(self, ticker: str, d0: str, cik: str, cfigi: str, sfigi: str, typ: str) -> tuple:
        """-> (symbol at D0, status): status `series` (no other symbol found), `renamed`, or `ambiguous` (two symbols on one date)."""
        cands = {}
        for k in (("s", sfigi), ("c", cfigi), ("k", cik)):
            if not k[1]:
                continue
            for r in self.by.get(k, []):
                if r["ticker"] == ticker or r["_delisted"] < d0:
                    continue
                if k[0] == "k" and ((r.get("type") or "") != (typ or "") or (sfigi and r.get("share_class_figi") and r["share_class_figi"] != sfigi)):
                    continue
                cands[id_of(r)] = r
        if not cands:
            return (ticker, "series")
        first = min(r["_delisted"] for r in cands.values())
        syms = sorted({r["ticker"] for r in cands.values() if r["_delisted"] == first})
        return (syms[0], "renamed") if len(syms) == 1 else ("", "ambiguous")


def owner_A_series(symbol: str, ref: dict, refetch_recs: dict, is_refetched: bool) -> tuple:
    """Era A series owner: an original symbol = its ACTIVE record (none -> the latest delisted record, path printed); a refetched
    symbol = its refetch record (R10). -> (record | None, path)."""
    recs = ref.get(symbol, [])
    if is_refetched:
        r = refetch_recs.get(symbol)
        return (r, "refetch_record") if r else (None, "refetch_record_missing")
    act = active_record(recs)
    if act:
        return (act, "active")
    dl = delisted_records(recs)
    if dl:
        return (dl[-1], "no active record -> latest delisted")
    return (None, "no_record")


def needs_reresolution(rec: "dict | None") -> bool:
    if not rec:
        return False
    delisted = rec.get("_delisted") or (rec.get("delisted") or "")[:10]
    empty = not (rec.get("_cik") or cik10(rec.get("cik")) or rec.get("composite_figi") or rec.get("share_class_figi"))
    return delisted == X.PLACEHOLDER_DELISTED or empty


def reresolve(symbol: str, rec: dict, ref: dict, series_last: str) -> tuple:
    """R11 / the plan's M1: a placeholder-dated or empty-keyed owner re-resolved from the pinned reference pull (same symbol; a record
    whose span holds the series). -> (record, path)."""
    recs = ref.get(symbol, [])
    dl = [r for r in delisted_records(recs) if r["_delisted"] >= series_last]
    if dl:
        return (dl[0], "reresolved_delisted")
    act = active_record(recs)
    if act and series_last >= X.A_LAST:
        return (act, "reresolved_active")
    out = dict(rec)
    if (out.get("_delisted") or (out.get("delisted") or "")[:10]) == X.PLACEHOLDER_DELISTED:
        out["_delisted"] = ""
        out["delisted"] = ""
        out["_date_unknown"] = True
    return (out, "unresolved")


def record_type(rec: "dict | None") -> str:
    return (rec or {}).get("type") or ""


def resolve_type(symbol: str, rec: "dict | None", types: dict, sic: dict) -> tuple:
    """(type, source): the owning record's type; no record -> the era's type table -> the SIC pull -> unknown."""
    if rec is not None and rec.get("type"):
        return (rec["type"], "polygon_record")
    if symbol in types:
        return (types[symbol], "type_table")
    if symbol in sic:
        return (sic[symbol], "sic_pull")
    return ("", "unknown")


def gone_flag(rec: "dict | None", active_keys: set) -> str:
    """'yes' when the owner is delisted and no active record shares its CIK / composite FIGI / share-class FIGI; 'no' when a match
    exists (a rename) or the owner is active; 'unknown' with no record, an empty key, or an unknown date (round 4)."""
    if rec is None:
        return "unknown"
    if rec.get("_date_unknown"):
        return "unknown"
    delisted = rec.get("_delisted") or (rec.get("delisted") or "")[:10]
    if not delisted:
        return "no"
    keys = [k for k in (rec.get("_cik") or cik10(rec.get("cik")), rec.get("composite_figi"), rec.get("share_class_figi")) if k]
    if not keys:
        return "unknown"
    return "no" if any(k in active_keys for k in keys) else "yes"


def active_key_set(ref: dict) -> set:
    out = set()
    for recs in ref.values():
        for r in recs:
            if r.get("active") is True or r.get("_pull") == "active":
                for k in (r.get("_cik"), r.get("composite_figi"), r.get("share_class_figi")):
                    if k:
                        out.add(k)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the detector (never edited; called with explicit parameters)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def detector_module():
    from agents.market_intelligence import parabolic_detector as pdm
    return pdm


def assert_dollar_vol_const(pop: str) -> int:
    """Each process asserts the constant it expects (2,000,000 in P2 / 10,000,000 in P1) — a mismatch exits non-zero."""
    pdm = detector_module()
    want = X.P2_DOLLAR_VOL_CONST if pop == "P2" else X.P1_DOLLAR_VOL_CONST
    got = pdm._MIN_DOLLAR_VOL_TODAY
    if got != want:
        raise GuardStop(f"{pop} process: parabolic_detector._MIN_DOLLAR_VOL_TODAY is {got:,}, expected {want:,}")
    return got


def patch_p2_constant() -> int:
    """The P2 process patches the module global at runtime (never on disk) before its first call."""
    pdm = detector_module()
    setattr(pdm, "_MIN_DOLLAR_VOL_TODAY", X.P2_DOLLAR_VOL_CONST)
    return pdm._MIN_DOLLAR_VOL_TODAY


def ticker_dicts(e: Era, t: int) -> list:
    """The detector's row shape for one ticker's whole series (built per ticker, never cached by id())."""
    a, b = e.rows_of(t)
    cal = e.cal
    ci, o, h, l, c, v = e.D.ci[a:b], e.D.o[a:b], e.D.h[a:b], e.D.l[a:b], e.D.c[a:b], e.D.v[a:b]
    return [{"trade_date": date.fromisoformat(cal[ci[k]]), "open_price": float(o[k]), "high_price": float(h[k]),   # str->float
             "low_price": float(l[k]), "close": float(c[k]), "volume": float(v[k])} for k in range(b - a)]          # str->float


GATE_ORDER = ("dollar_volume", "base_anchor", "prior_move", "sma_extension", "acceleration", "burst_score", "gapped_today", "climax_volume",
              "days_up_streak", "earnings", "climax")


def gate_of(res: dict) -> str:
    """The first failing gate in the plan's funnel order (or `climax`)."""
    reason = res.get("reason") or ""
    stage = res.get("stage")
    if reason.startswith("dollar_vol_"):
        return "dollar_volume"
    if reason == "no_base_anchor":
        return "base_anchor"
    if reason.startswith("prior_move_"):
        return "prior_move"
    if reason.startswith("ext_sma50_") or reason == "insufficient_sma_history":
        return "sma_extension"
    if reason.startswith("not_accelerating") or reason == "insufficient_roc_history":
        return "acceleration"
    if stage == "climax":
        return "climax"
    if stage == "watch":
        return "burst_score"
    if not res.get("gapped_today"):
        return "gapped_today"
    if not res.get("climax_volume_flag"):
        return "climax_volume"
    if (res.get("days_up_streak") or 0) < 3:
        return "days_up_streak"
    if res.get("is_earnings_today"):
        return "earnings"
    return "burst_score"


def run_detector(rows: list, cap, is_earnings_today=None) -> dict:
    return detector_module().compute_parabolic_metrics(rows, market_cap=cap, is_earnings_today=is_earnings_today)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# R7 — the exact necessary-condition pre-filter (the CIK set for the EDGAR pull)
# ═════════════════════════════════════════════════════════════════════════════════════════════
EPS = 1e-9          # R36


def superset_mask(e: Era) -> np.ndarray:
    """Per flat row: the night could be a climax at SOME cap — every condition below is necessary for the detector's `climax` at any
    tier (R7). Only rows with 120 consecutive sessions of history are tested."""
    pdm = detector_module()
    n = len(e.D.c)
    out = np.zeros(n, dtype=bool)
    base = nights_mask(e) & e.band
    for t in range(len(e.tickers)):
        a, b = e.rows_of(t)
        if not base[a:b].any():
            continue
        c, o, l, v = e.D.c[a:b], e.D.o[a:b], e.D.l[a:b], e.D.v[a:b]
        m = b - a
        ok = base[a:b].copy()
        idx = np.arange(m)
        # gate 2 (necessary): close / min low over [i-60, i] - 1 >= the most permissive threshold
        lpos = np.where(l > 0, l, np.inf)                                            # R36: only a positive low can be the base
        min_low = pd.Series(lpos).rolling(pdm._BASE_LOOKBACK_DAYS + 1, min_periods=1).min().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            ok &= (c / min_low - 1.0) >= pdm._PRIOR_MOVE_LARGE * (1.0 - EPS) - EPS
        # gate 3 (exact): close / SMA50 >= 1.5
        sma50 = rolling_mean(c, pdm._SMA50_DAYS)
        ok &= np.isfinite(sma50) & (c >= pdm._MIN_EXT_VS_SMA50 * np.where(np.isfinite(sma50), sma50, np.inf) * (1.0 - EPS))
        # gate 4 (exact): daily_5d > daily_20d * 1.10, roc_20d > 0, roc_5d > -1
        roc5 = np.full(m, np.nan); roc20 = np.full(m, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            roc5[5:] = c[5:] / c[:-5] - 1.0
            roc20[20:] = c[20:] / c[:-20] - 1.0
            d5 = (1.0 + roc5) ** (1.0 / pdm._ROC_SHORT_DAYS) - 1.0
            d20 = (1.0 + roc20) ** (1.0 / pdm._ROC_LONG_DAYS) - 1.0
        vel = (np.isfinite(roc5) & np.isfinite(roc20) & (roc20 > -EPS) & (roc5 > -1) & (d20 > -EPS)
               & (d5 >= d20 * pdm._VELOCITY_DAILY_RATIO_MIN - EPS * (1.0 + np.abs(d20))))
        ok &= vel
        # climax hard gate (exact): days_up_streak >= 3 -> c[i] > c[i-1] > c[i-2] > c[i-3]
        up = np.zeros(m, dtype=bool)
        up[1:] = c[1:] > c[:-1]
        streak3 = np.zeros(m, dtype=bool)
        streak3[3:] = up[3:] & up[2:-1] & up[1:-2]
        ok &= streak3
        # gapped today (exact): open > prior close * 1.02
        gapped = np.zeros(m, dtype=bool)
        gapped[1:] = o[1:] >= c[:-1] * (1.0 + pdm._GAPPED_TODAY_PCT) * (1.0 - EPS)
        ok &= gapped
        # climax volume (exact): today's volume = max over the last 20 and > 0
        vmax = pd.Series(v).rolling(pdm._SMA20_DAYS, min_periods=pdm._SMA20_DAYS).max().to_numpy()
        ok &= np.isfinite(vmax) & (v >= np.where(np.isfinite(vmax), vmax, np.inf)) & (v > 0)
        out[a:b] = ok
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the funnel for the dry run (file-only)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def funnel_dry(e: Era) -> dict:
    """Counts the dry run prints per era: ticker-nights -> symbol rules -> scorable -> history -> band / P1 / P2-band, and the
    adjusted-pass / raw-fail tally. No owner, no type, no detector."""
    rt = e.row_tid
    pat_ok = e.info["pattern_ok"][rt]
    test = e.info["test_symbol"][rt]
    f = {}
    f["ticker_nights"] = int(len(rt))
    f["detectable ticker-nights (scorable D0 + open-at-seal)"] = int(e.detect.sum())
    f["  of which open at the seal (era B, R35)"] = int((e.detect & ~e.scorable).sum())
    f["excluded: symbol pattern"] = int((e.detect & ~pat_ok).sum())
    f["excluded: test symbol"] = int((e.detect & pat_ok & test).sum())
    s = e.detect & e.sym_ok[rt]
    f["after symbol rules"] = int(s.sum())
    f["excluded: history (not 120 consecutive sessions)"] = int((s & ~e.contig).sum())
    s &= e.contig
    f["after history"] = int(s.sum())
    f["band ($1 / $2M on the RAW close)"] = int((s & e.band).sum())
    f["P1 ($5 / $10M on the RAW close)"] = int((s & e.p1).sum())
    f["P2 band (the complement)"] = int((s & e.band & ~e.p1).sum())
    f["P1 nights outside the $1 / $2M band (0: P1 implies the band)"] = int((s & e.p1 & ~e.band).sum())
    adj_p1 = (e.D.c >= X.P1_RAW_FLOOR) & (e.dv >= X.P1_DV_FLOOR)
    adj_band = (e.D.c >= X.BAND_RAW_FLOOR) & (e.dv >= X.BAND_DV_FLOOR)
    f["adjusted-pass / raw-fail: P1 floor"] = int((s & adj_p1 & (e.raw < X.P1_RAW_FLOOR)).sum())
    f["adjusted-pass / raw-fail: band floor"] = int((s & adj_band & (e.raw < X.BAND_RAW_FLOOR)).sum())
    f["raw-pass / adjusted-fail: P1 floor"] = int((s & ~adj_p1 & e.p1).sum())
    f["raw-pass / adjusted-fail: band floor"] = int((s & ~adj_band & e.band).sum())
    yrs = Counter()
    for ci in e.D.ci[s & e.band]:
        yrs[e.cal[ci][:4]] += 1
    f["band nights by year"] = dict(sorted(yrs.items()))
    return f


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the night table: owner record, type, company key, gone flag and identity flags per flat row (STEP 0 derive / climax)
# ═════════════════════════════════════════════════════════════════════════════════════════════
F_PRE_HOLE = 1 << 0          # era A: dated before a hole on a ONE-company symbol (owner's type kept, flagged)
F_ALIAS_OUTSIDE = 1 << 1     # era A: a dedupe dropped symbol's row outside its span (typed by the date rule)
F_PRE_BREAK = 1 << 2         # era A: dated before the symbol's last APPLIED break -> an earlier, unidentified holder (R37)
F_JUMP_UNEV = 1 << 3         # the 120-row window holds an unevidenced jump (admitted, flagged)
F_ID_GUARD = 1 << 4          # an APPLIED break inside the 120-row window -> identity_break
F_ID_EARLIER = 1 << 5        # era B: the window reaches an earlier issuer's bars -> identity_break (R33)
F_REFETCHED = 1 << 6         # era A: the symbol is one of the 2,669 the build added
F_NAME_MISMATCH = 1 << 7     # the owning record's name disagrees with SEC's for its CIK -> owner unknown (R14, climax phase)
F_TYPE_EXCLUDED = 1 << 8     # typed other than CS / ADRC / unknown (ETF, WARRANT, PFD ...)
F_SUFFIX_EXCLUDED = 1 << 9   # untyped 5-letter symbol ending W / U / R
F_NO_ACTIVE = 1 << 10        # era A original symbol with no active record -> latest delisted (path printed)
F_RERESOLVED = 1 << 11       # a placeholder / empty-keyed owner re-resolved from the reference pull
F_UNRESOLVED = 1 << 12       # ... and left unresolved (date unknown -> gone unknown)

T_UNKNOWN, T_CS, T_ADRC, T_OTHER = 0, 1, 2, 3
TYPE_CODES = {"CS": T_CS, "ADRC": T_ADRC}
TSRC = ("polygon_record", "refetch_record", "type_table", "sic_pull", "unknown", "record_without_type", "record_not_covering",
        "pre_break_holder", "name_mismatch")
G_NO, G_YES, G_UNKNOWN = 0, 1, 2
PATHS = ("no_record", "active", "no active record -> latest delisted", "refetch_record", "reresolved_delisted", "reresolved_active",
         "unresolved", "delisted_date_rule", "alias_date_rule", "two_delisted_same_date", "no_record_covering_d0", "pre_break_holder",
         "name_mismatch")
P_IDX = {p: k for k, p in enumerate(PATHS)}


def refetch_record_as_ref(r: dict) -> dict:
    """A refetch_combined_records_1023.tsv row in the reference-record shape (R10)."""
    out = dict(r)
    out["delisted_utc"] = r.get("delisted") or ""
    out["_delisted"] = (r.get("delisted") or "")[:10]
    out["_cik"] = cik10(r.get("cik"))
    out["_pull"] = "refetch"
    for k in ("composite_figi", "share_class_figi", "type", "name"):
        out[k] = r.get(k) or ""
    return out


def rec_key(rec: dict, symbol: str) -> str:
    return company_key_of(rec, symbol)[0]


def owner_has_placeholder(rec: "dict | None") -> bool:
    """The assertion of the M1 re-resolution: no owner taken from the REFETCH file still carries the 2022-06-30 fetch cut-off."""
    return bool(rec) and rec.get("_pull") == "refetch" and (rec.get("_delisted") or "") == X.PLACEHOLDER_DELISTED


@dataclass
class Ctx:
    """What the night table needs besides the bars (each field read from a pinned file or pull)."""
    ref: dict = field(default_factory=dict)              # {ticker: [Polygon records]}; empty dict = the pull is not in hand
    refetch: dict = field(default_factory=dict)          # {ticker: refetch record (reference shape)} (era A)
    refetched: set = field(default_factory=set)          # the refetch-sourced symbols (era A)
    breaks: list = field(default_factory=list)           # classified guard rows (breaks_applied)
    company_count: "dict | None" = None
    alias_outside: dict = field(default_factory=dict)    # alias_outside_span(...) (era A)
    types: dict = field(default_factory=dict)
    sic: dict = field(default_factory=dict)
    active_keys: set = field(default_factory=set)
    name_mismatch: set = field(default_factory=set)      # record ids (id_of) whose name disagrees with SEC's (R14)


def id_of(rec: dict) -> tuple:
    """A record's identity across processes (never id(), the runner rule): (ticker, source, delisted date, cik, composite FIGI)."""
    return (rec.get("ticker") or "", rec.get("_pull") or "", rec.get("_delisted") or "", rec.get("_cik") or cik10(rec.get("cik")),
            rec.get("composite_figi") or "")


@dataclass
class Nights:
    """Per flat row of an era: the owner record (index into `recs`), its path, the type and its source, the company key (index into
    `keys`), the gone flag, the flag bits. `recs` / `keys` are lists; nothing is keyed by id()."""
    owner: np.ndarray
    path: np.ndarray
    tcode: np.ndarray
    tsrc: np.ndarray
    key: np.ndarray
    gone: np.ndarray
    flags: np.ndarray
    recs: list
    keys: list
    info: dict = field(default_factory=dict)

    def key_of(self, i: int) -> str:
        return self.keys[int(self.key[i])]

    def rec_of(self, i: int) -> "dict | None":
        k = int(self.owner[i])
        return self.recs[k] if k >= 0 else None


def _type_of(rec: "dict | None") -> tuple:
    t = (rec or {}).get("type") or ""
    return (TYPE_CODES.get(t, T_OTHER) if t else T_UNKNOWN), t


def night_table(e: Era, ctx: Ctx) -> Nights:
    """The owner / type / key / gone / identity flags of every flat row of era `e` (plan §Security type, identity and CIK; §History;
    R33-R38). Era A owns by SERIES (original symbol = its active record, refetched = its refetch record, re-resolved when a
    placeholder); era B by the date rule per night."""
    n = len(e.D.c)
    owner = np.full(n, -1, np.int32)
    path = np.zeros(n, np.int8)
    tcode = np.zeros(n, np.int8)
    tsrc = np.full(n, TSRC.index("unknown"), np.int8)
    key = np.zeros(n, np.int32)
    gone = np.full(n, G_UNKNOWN, np.int8)
    flags = np.zeros(n, np.uint16)
    recs, keys, key_idx = [], [], {}
    rec_idx = {}

    def add_rec(r: dict) -> int:
        k = id_of(r)
        if k not in rec_idx:
            rec_idx[k] = len(recs)
            recs.append(r)
        return rec_idx[k]

    def add_key(k: str) -> int:
        if k not in key_idx:
            key_idx[k] = len(keys)
            keys.append(k)
        return key_idx[k]

    cal_ord = np.array([X.ord_of(d) for d in e.cal], dtype=np.int64)
    applied = applied_breaks(ctx.breaks) if ctx.breaks else {}
    unev = unevidenced_jumps(ctx.breaks) if ctx.breaks else {}
    last_brk = last_applied_break(ctx.breaks, ctx.company_count) if (ctx.breaks and e.name == "A") else {}
    info = Counter()
    for t, s in enumerate(e.tickers):
        a, b = e.rows_of(t)
        if b <= a:
            continue
        d_ord = cal_ord[e.D.ci[a:b]]
        recs_s = ctx.ref.get(s, [])
        if e.name == "A":
            is_ref = s in ctx.refetched
            if is_ref:
                flags[a:b] |= F_REFETCHED
            r0, p0 = owner_A_series(s, ctx.ref, ctx.refetch, is_ref)
            if p0 == "no active record -> latest delisted":
                dl = delisted_records(recs_s)
                if len(dl) >= 2 and dl[-1]["_delisted"] == dl[-2]["_delisted"]:
                    r0, p0 = None, "two_delisted_same_date"
                else:
                    flags[a:b] |= F_NO_ACTIVE
            if r0 is not None and r0.get("_pull") == "refetch" and needs_reresolution(r0) and ctx.ref:      # R61
                series_last = e.cal[e.D.ci[b - 1]]
                r0, p0 = reresolve(s, r0, ctx.ref, series_last)
                flags[a:b] |= (F_UNRESOLVED if p0 == "unresolved" else F_RERESOLVED)
                info[f"reresolution:{p0}"] += 1
            if r0 is not None and id_of(r0) in ctx.name_mismatch:
                r0, p0 = None, "name_mismatch"
                flags[a:b] |= F_NAME_MISMATCH
            oi = add_rec(r0) if r0 is not None else -1
            owner[a:b] = oi
            path[a:b] = P_IDX[p0]
            if s in ctx.alias_outside:                      # the 15 leftover symbols: the era-B date rule per night
                flags[a:b] |= F_ALIAS_OUTSIDE
                for k in range(a, b):
                    r, p = owner_alias(recs_s, e.cal[e.D.ci[k]])
                    if r is not None and id_of(r) in ctx.name_mismatch:
                        r, p = None, "name_mismatch"
                    owner[k] = add_rec(r) if r is not None else -1
                    path[k] = P_IDX[p]
            if s in last_brk:                               # R37: before the last applied break = an earlier, unidentified holder
                pre = d_ord < last_brk[s]
                idx = np.flatnonzero(pre) + a
                owner[idx] = -1
                path[idx] = P_IDX["pre_break_holder"]
                flags[idx] |= F_PRE_BREAK
            if ctx.breaks:
                flags[a:b] |= np.where(_pre_hole_mask(s, d_ord, ctx) & ~(flags[a:b] & F_PRE_BREAK).astype(bool), F_PRE_HOLE, 0).astype(np.uint16)
        else:
            _owners_B(s, recs_s, d_ord, a, b, owner, path, add_rec, ctx)
            if recs_s:
                _earlier_issuer(s, recs_s, d_ord, a, b, owner, recs, flags, ctx)
        # identity: applied breaks in the window -> identity_break; unevidenced jumps in the window -> flagged
        if s in applied:
            m = X.break_mask(d_ord, applied[s], window=X.HISTORY)
            flags[a:b] |= np.where(m, F_ID_GUARD, 0).astype(np.uint16)
        if s in unev:
            m = X.break_mask(d_ord, unev[s], window=X.HISTORY)
            flags[a:b] |= np.where(m, F_JUMP_UNEV, 0).astype(np.uint16)
        # type, key, gone per row (per distinct owner run)
        has_records = bool(recs_s) or (e.name == "A" and s in ctx.refetch)
        for k0, k1, oi, pc in _runs(owner[a:b], path[a:b]):
            sl = slice(a + k0, a + k1)
            pname = PATHS[pc]
            if oi >= 0:
                rec = recs[oi]
                tc, tname = _type_of(rec)
                tcode[sl] = tc
                tsrc[sl] = TSRC.index(("refetch_record" if rec.get("_pull") == "refetch" else "polygon_record") if tname else "record_without_type")
                key[sl] = add_key(rec_key(rec, s))
                gone[sl] = {"no": G_NO, "yes": G_YES}.get(gone_flag(rec, ctx.active_keys), G_UNKNOWN)
            else:
                key[sl] = add_key("sym:" + s)
                gone[sl] = G_UNKNOWN
                if pname in ("pre_break_holder", "name_mismatch"):
                    tcode[sl], tsrc[sl] = T_UNKNOWN, TSRC.index(pname)
                elif has_records and ctx.ref:
                    tcode[sl], tsrc[sl] = T_UNKNOWN, TSRC.index("record_not_covering")
                elif s in ctx.types:
                    tt = ctx.types[s]
                    tcode[sl], tsrc[sl] = TYPE_CODES.get(tt, T_OTHER) if tt else T_UNKNOWN, TSRC.index("type_table")
                elif s in ctx.sic:
                    tt = ctx.sic[s]
                    tcode[sl], tsrc[sl] = TYPE_CODES.get(tt, T_OTHER) if tt else T_UNKNOWN, TSRC.index("sic_pull")
                else:
                    tcode[sl], tsrc[sl] = T_UNKNOWN, TSRC.index("unknown")
        sfx = e.info["suffix"][t] if "suffix" in e.info else ""
        sub = slice(a, b)
        flags[sub] |= np.where(tcode[sub] == T_OTHER, F_TYPE_EXCLUDED, 0).astype(np.uint16)
        if sfx:
            flags[sub] |= np.where(tcode[sub] == T_UNKNOWN, F_SUFFIX_EXCLUDED, 0).astype(np.uint16)
    return Nights(owner, path, tcode, tsrc, key, gone, flags, recs, keys, dict(info))


def _runs(owner_slice: np.ndarray, path_slice: np.ndarray):
    """(start, stop, owner, path) of maximal runs of equal (owner, path) in a ticker's rows."""
    n = len(owner_slice)
    if n == 0:
        return
    chg = np.flatnonzero((np.diff(owner_slice) != 0) | (np.diff(path_slice) != 0)) + 1
    bounds = np.concatenate(([0], chg, [n]))
    for k0, k1 in zip(bounds[:-1], bounds[1:]):
        yield int(k0), int(k1), int(owner_slice[k0]), int(path_slice[k0])


def _pre_hole_mask(s: str, d_ord: np.ndarray, ctx: Ctx) -> np.ndarray:
    out = np.zeros(len(d_ord), dtype=bool)
    for r in ctx.breaks:
        if r["symbol"] != s or r["kind"] != "hole":
            continue
        n = None if ctx.company_count is None else ctx.company_count.get(s)
        if ctx.company_count is not None and (n or 0) >= 2:
            continue
        out |= d_ord < X.ord_of(r["date"])
    return out


def _owners_B(s, recs_s, d_ord, a, b, owner, path, add_rec, ctx) -> None:
    """Era B's date rule per night: the delisted record with the smallest delisted_utc >= D0 (a tie = unknown), else the active
    record, else unknown."""
    if not recs_s:
        owner[a:b] = -1
        path[a:b] = P_IDX["no_record"]
        return
    dl = delisted_records(recs_s)
    dl_ord = np.array([X.ord_of(r["_delisted"]) for r in dl], dtype=np.int64)
    act = active_record(recs_s)
    pos = np.searchsorted(dl_ord, d_ord, side="left")
    for k in range(len(d_ord)):
        p = int(pos[k])
        if p < len(dl):
            if p + 1 < len(dl) and dl_ord[p + 1] == dl_ord[p]:
                owner[a + k], path[a + k] = -1, P_IDX["two_delisted_same_date"]
                continue
            r, pn = dl[p], "delisted_date_rule"
        elif act is not None:
            r, pn = act, "active"
        else:
            owner[a + k], path[a + k] = -1, P_IDX["no_record_covering_d0"]
            continue
        if id_of(r) in ctx.name_mismatch:
            owner[a + k], path[a + k] = -1, P_IDX["name_mismatch"]
            continue
        owner[a + k], path[a + k] = add_rec(r), P_IDX[pn]


def _earlier_issuer(s, recs_s, d_ord, a, b, owner, recs, flags, ctx) -> None:
    """R33: the window's first bar may not be dated on or before the latest delisted_utc of a DIFFERENT company key's record
    delisted before D0."""
    m = b - a
    if m < X.HISTORY:
        return
    own_key = np.array([rec_key(recs[o], s) if o >= 0 else "" for o in owner[a:b]], dtype=object)
    L = np.full(m, -1, dtype=np.int64)
    for r in delisted_records(recs_s):
        dr = X.ord_of(r["_delisted"])
        kr = rec_key(r, s)
        hit = (dr < d_ord) & (own_key != kr)
        L = np.where(hit & (dr > L), dr, L)
    first = np.full(m, np.iinfo(np.int64).max, dtype=np.int64)
    first[X.HISTORY - 1:] = d_ord[: m - X.HISTORY + 1]
    bad = (L >= 0) & (first <= L)
    flags[a:b] |= np.where(bad, F_ID_EARLIER, 0).astype(np.uint16)


def earlier_issuer_first_bar_date(e: Era, symbol: str, d0: str) -> "str | None":
    """The first bar of the 120-row window ending at (symbol, D0), or None (printed beside the INBX / DOC controls)."""
    i = e.bar_index(symbol, d0)
    a, _b = e.rows_of(e.tid[symbol]) if symbol in e.tid else (0, 0)
    if i < 0 or i - X.HISTORY + 1 < a:
        return None
    return e.cal[e.D.ci[i - X.HISTORY + 1]]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# populations from the night table (the band rule, the complement, the type rule) and the STEP 0 funnel
# ═════════════════════════════════════════════════════════════════════════════════════════════
def admitted_mask(e: Era, nt: Nights) -> np.ndarray:
    """Symbol rules, a detectable D0, 120 consecutive sessions, no identity break, not excluded by type / suffix."""
    bad = F_ID_GUARD | F_ID_EARLIER | F_TYPE_EXCLUDED | F_SUFFIX_EXCLUDED
    return nights_mask(e) & ((nt.flags & bad) == 0)


def populations(e: Era, nt: Nights) -> dict:
    """{P1, P2, P2unk}: P1 = raw >= $5 and dv >= $10M (CS / ADRC / unknown); P2 = the complement inside the $1 / $2M band, CS / ADRC;
    P2unk = the complement band's unknown-type nights (a counted beside row). Asserts P1 ∩ P2 = ∅ and P1 ∪ P2 ∪ P2unk = the admitted band."""
    adm = admitted_mask(e, nt)
    typed = (nt.tcode == T_CS) | (nt.tcode == T_ADRC)
    p1 = adm & e.p1
    comp = adm & e.band & ~e.p1
    p2 = comp & typed
    p2u = comp & (nt.tcode == T_UNKNOWN)
    if (p1 & p2).any():
        raise GuardStop(f"era {e.name}: P1 ∩ P2 is not empty ({int((p1 & p2).sum())} nights)")
    if not np.array_equal(p1 | p2 | p2u, adm & e.band):
        raise GuardStop(f"era {e.name}: P1 ∪ P2 ∪ P2's unknown-type row differs from the admitted $1 / $2M band")
    return {"P1": p1, "P2": p2, "P2unk": p2u}


def funnel_step0(e: Era, nt: Nights) -> dict:
    """The STEP 0 funnel through history and identity, per population band (plan §STEP 0), counts only."""
    rt = e.row_tid
    f = {}
    base = e.detect.copy()
    f["ticker-nights (detectable D0)"] = int(base.sum())
    f["excluded: symbol pattern / test symbol"] = int((base & ~e.sym_ok[rt]).sum())
    base &= e.sym_ok[rt]
    texcl = (nt.flags & (F_TYPE_EXCLUDED | F_SUFFIX_EXCLUDED)) != 0
    f["excluded: security type (typed other than CS / ADRC)"] = int((base & ((nt.flags & F_TYPE_EXCLUDED) != 0)).sum())
    f["excluded: security type (untyped W / U / R suffix)"] = int((base & ((nt.flags & F_SUFFIX_EXCLUDED) != 0)).sum())
    base &= ~texcl
    f["raw_unknown (no raw close)"] = int((base & ~np.isfinite(e.raw)).sum())
    for pop, band in (("P1", e.p1), ("P2-band", e.band & ~e.p1)):
        s = base & band
        f[f"{pop}: in the raw-price / dollar-volume band"] = int(s.sum())
        f[f"{pop}: excluded: history (not 120 consecutive sessions)"] = int((s & ~e.contig).sum())
        s = s & e.contig
        g = (nt.flags & F_ID_GUARD) != 0
        ea = (nt.flags & F_ID_EARLIER) != 0
        f[f"{pop}: excluded: identity_break (applied guard break in the window)"] = int((s & g).sum())
        f[f"{pop}: excluded: identity_break (earlier-issuer rule, era B)"] = int((s & ~g & ea).sum())
        s = s & ~g & ~ea
        f[f"{pop}: admitted"] = int(s.sum())
        f[f"{pop}:   pre-break holder (typed unknown, admitted; R37)"] = int((s & ((nt.flags & F_PRE_BREAK) != 0)).sum())
        f[f"{pop}:   jump_unevidenced in the window (kept, flagged)"] = int((s & ((nt.flags & F_JUMP_UNEV) != 0)).sum())
        f[f"{pop}:   pre_hole (kept, flagged)"] = int((s & ((nt.flags & F_PRE_HOLE) != 0)).sum())
        f[f"{pop}:   alias_outside_span (date-rule owner)"] = int((s & ((nt.flags & F_ALIAS_OUTSIDE) != 0)).sum())
        for k, nm in enumerate(TSRC):
            c = int((s & (nt.tsrc == k)).sum())
            if c:
                f[f"{pop}:   type source {nm}"] = c
        if pop == "P2-band":
            typed = (nt.tcode == T_CS) | (nt.tcode == T_ADRC)
            f["P2 (typed CS / ADRC)"] = int((s & typed).sum())
            f["P2's unknown-type row"] = int((s & (nt.tcode == T_UNKNOWN)).sum())
            f["P2 untyped share"] = pct(int((s & (nt.tcode == T_UNKNOWN)).sum()), int(s.sum()))
    return f


def pct(a, b) -> str:
    return X.pct(a, b)
