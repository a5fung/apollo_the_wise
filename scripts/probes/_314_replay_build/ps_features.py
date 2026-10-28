#!/usr/bin/env python3
"""#314 replay — the point-in-time features on the climax list (plan §One cap rule, §Substitutions (a) (d), §Reads 2-5, §Distribution
artifacts): the cap from the latest periodic report before D0, every share count and per-share price moved onto D0's RAW basis by
S(end, D0), the loss-to-profit swing, the warrant / convertible overhang per tranche, the 8-K item 2.02 windows, the $0 M&A keyword
row, the news presence, and the distribution evidence class. Reads the pulls `ps_pull.py` saved; never the network.

THE PULL FILES (written by ps_pull.py; one JSON object per line, gzip):
  polygon_reference.jsonl.gz   a Polygon /v3/reference/tickers record + `_pull` (active | delisted) + `_pulled_at`
  edgar_submissions.jsonl.gz   {cik, status, name, tickers, sic, filings: [{form, filingDate, reportDate, acceptanceDateTime,
                               accessionNumber, primaryDocument, items, isXBRL}], files_fetched, pulled_at}  (recent + every older file)
  xbrl_facts.jsonl.gz          {cik, status, entityName, facts: {tag: [{unit, accn, end, start, filed, form, fp, fy, frame, val}]}}
                               for the tags in FACT_TAGS only
  xbrl_instances.jsonl.gz      {cik, accn, status, instance_url, instance_name, sha256, bytes, period_end, contexts: {id: {instant,
                               start, end, dims: [[axis, member]]}}, facts: [{tag, context, value, unit, decimals}] (INSTANCE_TAGS only),
                               text_tags_present: [tag]}
  polygon_news.jsonl.gz        {ticker, d0, kind (read3 | mna), gte, lte, status, pages, truncated, items: [{title, description,
                               published_utc, publisher, tickers, insights}]}
  alpaca_corporate_actions.jsonl.gz  {ticker, gap_date, start, end, status, actions: {type: [records]}}

READINGS (continued; the main loop decides):
  R15 The periodic report is matched on the EXACT form (10-K, 10-Q, 10-KT, 10-QT, 20-F); an amendment (10-K/A ...) is not "the latest
      periodic report" (it restates; its cover count may be the amended one). The filing's date order is `filingDate`, ties by acceptance.
  R16 The cover-page fact is the `dei:EntityCommonStockSharesOutstanding` entry of companyfacts whose `accn` equals the filing's; more
      than one DISTINCT (end, val) under that accn = `multi_class` = unknown (the plan's "more than one undimensioned value").
  R17 S(end, D0) on era A = factor(end) / factor(D0) with factor(d) = raw / adjusted on the name's last bar dated <= d; a date before the
      first bar = unknown (the plan's formula as written: never snapped to the step product). A "split between `end` and `filed`" on
      era A = a bar-to-bar factor step above 1% (JUMP_FAC_CHANGE, the jump evidence's own bound) among the name's bars dated between the
      two (revised 10-28 after review: the first build read S(end, filed) != 1 to 1e-9, which fires on the cent-rounded adjusted closes —
      GME's factor wanders 3.9993..3.9997 with no split and read "split" on most of its January 2021 nights; measured over the whole
      era-A file, 1,333 steps exceed 1% on 1,073 symbols, 1,324 of them above 10% and the other 9 real actions (HON's 2018 spin-offs,
      SLG's stock dividends, AIV, JCI), none at an adjusted close under $1, against 629,656 sub-1% noise steps); on era B = a listed
      split executing in (end, filed].
  R18 Any ADJUSTED price (the detector's base low, the climax close) is moved onto D0's raw basis by x factor(D0) — the adjusted series
      is continuous through a split, so one factor (D0's) carries every point of it.
  R19 Read 4's quarter = a NetIncomeLoss fact whose [start, end] spans 80-100 days; a quarter end reported in several filings takes its
      EARLIEST-filed value (the original report, point-in-time); Q4 = the fiscal-year fact (350-380 days) minus the 9-month fact
      (260-290 days, same end year, ending ~91 days before) when no 3-month fact ends on the FY end. Two quarters are consecutive when
      their ends are 80-100 days apart. The latest two consecutive quarters with `filed` < D0 decide; fewer = unknown.
  R20 8-K item 2.02 charging: an acceptance at or before 16:00 ET on a session is charged to that session, after 16:00 (or on a
      non-session day) to the NEXT session — "earnings on the climax day" = charged to D0-1 or D0 (the live {yesterday, today}).
      The earnings EXIT: an acceptance in (session s 16:00 ET, the next session's 09:30 ET] exits at s's close (`earnings_after`
      carries s). Form 8-K only (8-K/A excluded); `items` is the comma list EDGAR gives. The window of the era calendar's LAST
      session (era B 2024-12-31) closes at the next NYSE session's 09:30 ET from exchange_calendars (2025-01-02) — the first build
      left it open-ended, so any 2025-26 acceptance in the 2026-pulled submissions booked an earnings exit on 12-31 (review 10-28).
  R21 Read 5's tranche = a distinct dimension-member set among the instance's contexts whose INSTANT equals the filing's period end
      (DocumentPeriodEndDate when the instance carries it, else the submissions `reportDate` of the filing — R39: the inherited code
      passed the cover fact's `end`, which is the cover date weeks after the balance sheet, so every tranche was dropped and every
      parsed name read ratio 0); the undimensioned context is a tranche only
      when no dimensioned context carries that tag. Convertible principal tags: ConvertibleNotesPayable, ConvertibleDebt,
      ConvertibleNotesPayableCurrent, ConvertibleDebtCurrent, ConvertibleDebtNoncurrent, ConvertibleNotesPayableNoncurrent (the plan's
      "current or non-current").
  R22 The distribution evidence (ii) uses the 8-K's acceptance charged as in R20 and counts sessions on the era's calendar; a gap date
      that is not a session (impossible for a flagged bar) reads unknown. Alpaca action types read as evidence: `spin_offs` and
      `cash_dividends` with `special` true (a special cash distribution); `stock_dividends` / `splits` / `mergers` are not evidence.
  R39 Read 5's share basis per tranche: a tranche fact is dated at the balance-sheet date (the period end), not the cover date, so its
      count and price move to D0's basis by S(period end, D0), and a split between the PERIOD END and `filed` makes the name unknown
      (`split_between_end_and_filed`), as the cap rule does for the cover fact's own `end`. The denominator stays the cover count on
      D0's basis (the cap rule's `shares_d0`).
  R65 (review 10-28) A submissions record whose older file failed (ps_pull R64: `older_files_failed`, `coverage_from` = the recent
      block's first filing date) is holed before that date: the cap / read 5 lookup is decided only when the filing found is dated on or
      after it (no missing filing can be later), else `older_files_failed` = unknown; the 8-K item 2.02 flag needs the list to reach
      the session two before D0, the item 2.01 evidence the session before its window — else unknown, never "none".
  R40 The periodic-report lookup is indexed once per CIK (filings sorted by (filingDate, acceptance), bisect on D0) — `FilingIndex`;
      the cap is computed for every night of a pulled CIK, so a per-night scan of every filing would not finish.
"""
from __future__ import annotations

import bisect
import gzip
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ps_common as X  # noqa: E402

GuardStop = X.GuardStop
_ET = ZoneInfo("America/New_York")

FACT_TAGS = ("dei:EntityCommonStockSharesOutstanding", "us-gaap:NetIncomeLoss")
WARRANT_COUNT = "us-gaap:ClassOfWarrantOrRightNumberOfSecuritiesCalledByWarrantsOrRights"
WARRANT_OUTSTANDING = "us-gaap:ClassOfWarrantOrRightOutstanding"
WARRANT_PRICE = "us-gaap:ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1"
CONV_SHARES = "us-gaap:DebtInstrumentConvertibleNumberOfEquityInstruments"
CONV_PRICE = "us-gaap:DebtInstrumentConvertibleConversionPrice1"
CONV_PRINCIPAL = ("us-gaap:ConvertibleNotesPayable", "us-gaap:ConvertibleDebt", "us-gaap:ConvertibleNotesPayableCurrent",
                  "us-gaap:ConvertibleDebtCurrent", "us-gaap:ConvertibleDebtNoncurrent", "us-gaap:ConvertibleNotesPayableNoncurrent")
WARRANT_TEXT = "us-gaap:ClassOfWarrantOrRightTitleOfSecurityWarrantsOrRightsOutstanding"
INSTANCE_TAGS = (WARRANT_COUNT, WARRANT_OUTSTANDING, WARRANT_PRICE, CONV_SHARES, CONV_PRICE) + CONV_PRINCIPAL + (
    "dei:EntityCommonStockSharesOutstanding", "dei:DocumentPeriodEndDate")
INSTANCE_TEXT_TAGS = (WARRANT_TEXT,)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the pulls, loaded
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_jsonl(path: str) -> list:
    """Every record of a pull file; a line that does not parse (a pull killed mid-write) refuses with its count, never a traceback."""
    out, bad = [], 0
    if not os.path.exists(path):
        return out
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip():
                    try:
                        out.append(json.loads(ln))
                    except ValueError:
                        bad += 1
    except (EOFError, OSError) as ex:                     # a gzip stream cut short
        raise GuardStop(f"{path}: the gzip stream is cut short ({type(ex).__name__}) after {len(out):,} records — re-run its pull to repair it")
    if bad:
        raise GuardStop(f"{path}: {bad:,} lines do not parse (a pull killed mid-write?) — re-run its pull to repair the file")
    return out


def load_submissions(path: str) -> dict:
    """{cik: record}; a CIK pulled twice keeps the LAST record (a retry)."""
    return {r["cik"]: r for r in read_jsonl(path)}


def load_facts(path: str) -> dict:
    return {r["cik"]: r for r in read_jsonl(path)}


def load_instances(path: str) -> dict:
    return {(r["cik"], r["accn"]): r for r in read_jsonl(path)}


def load_news(path: str) -> dict:
    return {(r["ticker"], r["d0"], r["kind"]): r for r in read_jsonl(path)}


def load_alpaca_ca(path: str) -> dict:
    return {(r["ticker"], r["gap_date"]): r for r in read_jsonl(path)}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the share basis: S(end, D0)
# ═════════════════════════════════════════════════════════════════════════════════════════════
class Basis:
    """factor(d) per name: era A from the raw / adjusted factor on the name's last bar <= d; era B from the splits file."""

    def __init__(self, era: str, splits: dict = None, dates: dict = None, fac: dict = None):
        self.era, self.splits = era, splits or {}
        self.dates, self.fac = dates or {}, fac or {}     # era A: ticker -> (ISO dates list, factor array)

    def factor_A(self, ticker: str, d: str):
        ds = self.dates.get(ticker)
        if ds is None:
            return None
        i = bisect.bisect_right(ds, d) - 1
        if i < 0:
            return None
        return X.num(self.fac[ticker][i])

    def S(self, ticker: str, end: str, d0: str):
        """The cumulative split ratio between the fact's `end` and D0 (count x S, price / S); None = unknown."""
        if self.era == "B":
            f = 1.0
            for ex, ratio in self.splits.get(ticker, []):
                if end < ex.isoformat() <= d0:
                    f *= ratio
            return f
        fe, f0 = self.factor_A(ticker, end), self.factor_A(ticker, d0)
        if fe is None or f0 is None or f0 == 0:
            return None
        return fe / f0

    def steps_A(self, ticker: str, lo: str, hi: str) -> "bool | None":
        """Era A (R17): any bar-to-bar factor step above JUMP_FAC_CHANGE (1%) among the name's bars dated in (its last bar <= lo,
        its last bar <= hi]; None when either date precedes the name's first bar or a factor is not finite."""
        ds = self.dates.get(ticker)
        if ds is None:
            return None
        i, j = bisect.bisect_right(ds, lo) - 1, bisect.bisect_right(ds, hi) - 1
        if i < 0 or j < 0:
            return None
        f = np.asarray(self.fac[ticker][i: j + 1], dtype=float)
        return _any_step(f)

    def split_between(self, ticker: str, end: str, filed: str) -> "bool | None":
        """R17: era B = a listed split executing in (end, filed]; era A = a factor STEP above 1% between the two dates (the cent-rounded
        adjusted close moves the raw / adjusted ratio by up to ~0.1% a bar with no split, so 'S != 1' would fire on noise)."""
        lo, hi = (end, filed) if filed >= end else (filed, end)
        if self.era == "B":
            return any(lo < ex.isoformat() <= hi for ex, _r in self.splits.get(ticker, []))
        return self.steps_A(ticker, lo, hi)


def _any_step(f: np.ndarray) -> "bool | None":
    if len(f) < 2:
        return False
    if not np.all(np.isfinite(f)) or np.any(f == 0):
        return None
    return bool(np.any(np.abs(f[1:] / f[:-1] - 1.0) > X.JUMP_FAC_CHANGE))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the filing rule (shared by the cap and read 5)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def filings_of(sub: "dict | None") -> list:
    return list((sub or {}).get("filings") or [])


def coverage_from(sub: "dict | None") -> str:
    """R65: '' when the submissions list is whole; else the recent block's first filing date (an older file failed: every filing before
    it may be missing, so a lookup that needs one reads unknown, never 'none')."""
    return ((sub or {}).get("coverage_from") or "0000-00-00") if (sub or {}).get("older_files_failed") else ""


def lookup_covered(sub: "dict | None", f: "dict | None") -> bool:
    """The latest periodic report before D0 is decided on a holed list only when the one found is dated inside the covered block (no
    missing filing can be later than it)."""
    cov = coverage_from(sub)
    return not cov or (f is not None and (f.get("filingDate") or "") >= cov)


class FilingIndex:
    """R40: per CIK, the periodic reports sorted by (filingDate, acceptance) -> the latest one filed before D0 by bisect."""

    def __init__(self, sub: "dict | None"):
        rows = [f for f in filings_of(sub) if f.get("form") in X.PERIODIC_FORMS and f.get("filingDate")]
        rows.sort(key=lambda f: (f.get("filingDate") or "", f.get("acceptanceDateTime") or ""))
        self.rows = rows
        self.dates = [f["filingDate"] for f in rows]

    def latest_before(self, d0: str) -> "dict | None":
        i = bisect.bisect_left(self.dates, d0) - 1
        return self.rows[i] if i >= 0 else None


def latest_periodic_before(sub: "dict | None", d0: str) -> "dict | None":
    """R15: the latest PERIODIC report (exact form) with filingDate < D0, by filingDate then acceptance."""
    best = None
    for f in filings_of(sub):
        if f.get("form") not in X.PERIODIC_FORMS:
            continue
        fd = f.get("filingDate") or ""
        if not fd or fd >= d0:
            continue
        key = (fd, f.get("acceptanceDateTime") or "")
        if best is None or key > best[0]:
            best = (key, f)
    return best[1] if best else None


def cover_shares(fact_rec: "dict | None", accn: str) -> tuple:
    """R16 -> (val, end, reason): the cover-page count of the filing `accn`; reason '' when found."""
    entries = ((fact_rec or {}).get("facts") or {}).get("dei:EntityCommonStockSharesOutstanding") or []
    hits = {(e.get("end"), e.get("val")) for e in entries if e.get("accn") == accn}
    if not hits:
        return (None, None, "no_cover_fact")
    if len(hits) > 1:
        return (None, None, "multi_class")
    (end, val), = hits
    return (val, end, "")


def cap_for(ticker: str, d0: str, cik: str, sub: "dict | None", facts: "dict | None", basis: Basis, raw_close_d0: float,
            index: "FilingIndex | None" = None) -> dict:
    """cap(D0) = cover shares of the latest periodic report filed < D0, x S(end, D0), x RAW close(D0); every unknown reason named.
    `index` (R40) replaces the per-night scan of the submissions list (same answer: tested)."""
    out = {"cap": None, "cap_source": "unknown", "cap_reason": "", "filing_accn": "", "filing_filed": "", "fact_end": "", "shares_d0": None}
    if not cik:
        out["cap_reason"] = "no_cik"
        return out
    if sub is None or sub.get("status") != 200:
        out["cap_reason"] = "no_submissions"
        return out
    f = index.latest_before(d0) if index is not None else latest_periodic_before(sub, d0)
    if not lookup_covered(sub, f):
        out["cap_reason"] = "older_files_failed"
        return out
    if f is None:
        out["cap_reason"] = "no_periodic_report_before_d0"
        return out
    out["filing_accn"], out["filing_filed"] = f.get("accessionNumber", ""), f.get("filingDate", "")
    if out["filing_filed"] >= d0:
        raise GuardStop(f"cap: a filing dated {out['filing_filed']} >= D0 {d0} reached the cap rule ({ticker})")
    if facts is None or facts.get("status") != 200:
        out["cap_reason"] = "no_companyfacts"
        return out
    val, end, why = cover_shares(facts, f.get("accessionNumber"))
    if why:
        out["cap_reason"] = why
        return out
    out["fact_end"] = end
    sb = basis.split_between(ticker, end, out["filing_filed"])
    if sb is None:
        out["cap_reason"] = "no_raw_close_on_end_or_filed"
        return out
    if sb:
        out["cap_reason"] = "split_between_end_and_filed"
        return out
    s = basis.S(ticker, end, d0)
    if s is None or raw_close_d0 is None:
        out["cap_reason"] = "no_raw_close_on_end_or_d0"
        return out
    shares = float(val) * s                                                   # str->float
    out.update({"cap": shares * float(raw_close_d0), "cap_source": "xbrl_cover_page", "shares_d0": shares})   # str->float
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# read 4 — the loss-to-profit swing
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def quarters_before(facts: "dict | None", d0: str) -> list:
    """R19 -> [(end, val, filed)] sorted by end, the quarterly NetIncomeLoss facts with filed < D0 (derived Q4s included)."""
    entries = ((facts or {}).get("facts") or {}).get("us-gaap:NetIncomeLoss") or []
    q, fy, nine = {}, {}, {}
    for e in entries:
        if e.get("unit") not in (None, "USD") or not e.get("start") or not e.get("end") or not e.get("filed"):
            continue
        if e["filed"] >= d0:
            continue
        span = _days(e["start"], e["end"])
        key, val, filed = e["end"], e.get("val"), e["filed"]
        if val is None:
            continue
        if 80 <= span <= 100:
            if key not in q or filed < q[key][1]:
                q[key] = (val, filed)
        elif 350 <= span <= 380:
            if key not in fy or filed < fy[key][1]:
                fy[key] = (val, filed, e["start"])
        elif 260 <= span <= 290:
            if key not in nine or filed < nine[key][1]:
                nine[key] = (val, filed, e["start"])
    for end, (v, filed, start) in fy.items():
        if end in q:
            continue
        cands = [(e9, v9, f9) for e9, (v9, f9, s9) in nine.items() if s9 == start and 80 <= _days(e9, end) <= 100]
        if cands:
            e9, v9, f9 = cands[0]
            q[end] = (v - v9, max(filed, f9))
    return sorted((end, v, f) for end, (v, f) in q.items())


def swing_feature(facts: "dict | None", cik: str, d0: str, base_date: "str | None") -> dict:
    """Groups swing / no swing / unknown; primary = the swing's `filed` inside [base_date, D0]; beside = whenever filed."""
    out = {"swing_group": "unknown", "swing_filed": "", "swing_group_any": "unknown", "swing_reason": ""}
    if not cik:
        out["swing_reason"] = "no_cik"
        return out
    if facts is None or facts.get("status") != 200:
        out["swing_reason"] = "no_companyfacts"
        return out
    qs = quarters_before(facts, d0)
    if len(qs) < 2:
        out["swing_reason"] = "fewer_than_two_quarters"
        return out
    (e_prev, v_prev, _f_prev), (e_last, v_last, f_last) = qs[-2], qs[-1]
    if not (80 <= _days(e_prev, e_last) <= 100):
        out["swing_reason"] = "latest_two_not_consecutive"
        return out
    swing = v_last > 0 and v_prev < 0
    out["swing_group_any"] = "swing" if swing else "no_swing"
    out["swing_filed"] = f_last
    if swing and base_date and base_date <= f_last <= d0:
        out["swing_group"] = "swing"
    elif swing:
        out["swing_group"] = "no_swing"           # the swing was not the news behind THIS run (filed outside [base_date, D0])
    else:
        out["swing_group"] = "no_swing"
    if f_last >= d0:
        raise GuardStop(f"read 4: a filing dated {f_last} >= D0 {d0} reached the swing rule")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# read 5 — stealth dilution, the tranche sum
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _val(v):
    try:
        return float(str(v).replace(",", ""))          # str->float
    except (TypeError, ValueError):
        return None


def tranches(inst: dict, period_end: "str | None") -> tuple:
    """R21 -> ([{dims, warrant_shares, warrant_price, conv_shares, conv_price, conv_principal}], reason)."""
    ctx = inst.get("contexts") or {}
    facts = inst.get("facts") or []
    pe = inst.get("period_end") or period_end
    by = defaultdict(dict)                     # dims tuple -> {tag: value}
    dimmed_tags = set()
    for f in facts:
        c = ctx.get(f.get("context"))
        if c is None:
            continue
        inst_date = c.get("instant") or c.get("end")
        if pe and inst_date != pe:
            continue
        dims = tuple(tuple(x) for x in (c.get("dims") or []))
        tag = f.get("tag")
        v = _val(f.get("value"))
        if v is None:
            continue
        if dims:
            dimmed_tags.add(tag)
        by[dims].setdefault(tag, v)
    out = []
    for dims, tags in by.items():
        if not dims and any(t in dimmed_tags for t in tags):
            tags = {t: v for t, v in tags.items() if t not in dimmed_tags}    # the undimensioned fact is a tranche only without a dimensioned one
        ws = tags.get(WARRANT_COUNT, tags.get(WARRANT_OUTSTANDING))
        wp = tags.get(WARRANT_PRICE)
        cs = tags.get(CONV_SHARES)
        cp = tags.get(CONV_PRICE)
        principal = next((tags[t] for t in CONV_PRINCIPAL if t in tags), None)
        if ws is None and wp is None and cs is None and cp is None and principal is None:
            continue
        out.append({"dims": dims, "warrant_shares": ws, "warrant_price": wp, "conv_shares": cs, "conv_price": cp, "conv_principal": principal})
    return out, ""


def dilution_feature(ticker: str, d0: str, cik: str, sub, facts, inst_by_key: dict, basis: Basis, raw_close_d0: float,
                     base_low_raw: "float | None", cap_info: dict) -> dict:
    """The overhang ratio on D0's raw basis; buckets >= 20% / < 20% / unknown with the reason; the beside (all in the money) ratio."""
    out = {"dilution_bucket": "unknown", "dilution_ratio": None, "dilution_ratio_itm": None, "tranche_count": 0, "dilution_accn": "",
           "dilution_filed": "", "dilution_reason": "", "warrant_text_present": 0}
    if not cik:
        out["dilution_reason"] = "no_cik"
        return out
    f = latest_periodic_before(sub, d0) if sub and sub.get("status") == 200 else None
    if sub and sub.get("status") == 200 and not lookup_covered(sub, f):
        out["dilution_reason"] = "older_files_failed"
        return out
    if f is None:
        out["dilution_reason"] = "no_filing_before_d0"
        return out
    accn = f.get("accessionNumber", "")
    out["dilution_accn"], out["dilution_filed"] = accn, f.get("filingDate", "")
    if out["dilution_filed"] >= d0:
        raise GuardStop(f"read 5: a filing dated {out['dilution_filed']} >= D0 {d0} reached the dilution rule ({ticker})")
    if cap_info.get("filing_accn") and cap_info["filing_accn"] != accn:
        raise GuardStop(f"read 5 and the cap read different filings for ({ticker}, {d0}): {accn} vs {cap_info['filing_accn']}")
    inst = inst_by_key.get((cik, accn))
    if inst is None or inst.get("status") != 200:
        out["dilution_reason"] = "instance_fetch_failed" if inst is not None else "instance_not_pulled"
        return out
    out["warrant_text_present"] = int(WARRANT_TEXT in (inst.get("text_tags_present") or []))
    if cap_info.get("cap_reason") in ("multi_class", "no_cover_fact", "no_companyfacts"):
        out["dilution_reason"] = "no_denominator:" + cap_info["cap_reason"]
        return out
    if cap_info.get("cap_reason") == "split_between_end_and_filed":
        out["dilution_reason"] = "split_between_end_and_filed"
        return out
    if cap_info.get("shares_d0") is None:
        out["dilution_reason"] = "no_denominator:" + (cap_info.get("cap_reason") or "unknown")
        return out
    pe = (inst.get("period_end") or f.get("reportDate") or "")[:10]
    if not pe:
        out["dilution_reason"] = "no_period_end"
        return out
    sb = basis.split_between(ticker, pe, out["dilution_filed"])
    if sb is None:
        out["dilution_reason"] = "no_raw_close_on_period_end_or_filed"
        return out
    if sb:
        out["dilution_reason"] = "split_between_end_and_filed"
        return out
    s = basis.S(ticker, pe, d0)
    if s is None:
        out["dilution_reason"] = "no_raw_close_on_period_end_or_d0"
        return out
    trs, why = tranches(inst, pe)
    if f.get("form") in ("20-F",) and not trs:
        out["dilution_reason"] = "foreign_filer_no_tags"
        return out
    out["tranche_count"] = len(trs)
    primary, itm = 0.0, 0.0
    for tr in trs:
        pairs = []
        if tr["warrant_shares"] is not None or tr["warrant_price"] is not None:
            if tr["warrant_shares"] is None or tr["warrant_price"] is None:
                out["dilution_reason"] = "unpaired_tranche"
                return out
            pairs.append((tr["warrant_shares"], tr["warrant_price"]))
        if tr["conv_shares"] is not None or tr["conv_price"] is not None or tr["conv_principal"] is not None:
            if tr["conv_price"] is None or tr["conv_price"] <= 0:
                out["dilution_reason"] = "unpaired_tranche"           # a variable-price convertible has no fixed price
                return out
            shares = tr["conv_shares"] if tr["conv_shares"] is not None else (
                tr["conv_principal"] / tr["conv_price"] if tr["conv_principal"] is not None else None)
            if shares is None:
                out["dilution_reason"] = "unpaired_tranche"
                return out
            pairs.append((shares, tr["conv_price"]))
        for count, price in pairs:
            count_d0, price_d0 = count * s, price / s
            if price_d0 <= raw_close_d0:
                itm += count_d0
                if base_low_raw is not None and price_d0 > base_low_raw:
                    primary += count_d0
    denom = cap_info["shares_d0"]
    if not denom or denom <= 0:
        out["dilution_reason"] = "zero_denominator"
        return out
    out["dilution_ratio"], out["dilution_ratio_itm"] = primary / denom, itm / denom
    out["dilution_bucket"] = "ge20" if out["dilution_ratio"] >= X.DILUTION_CUT else "lt20"
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 8-K item 2.02 (the earnings substitute) and item 2.01 (the distribution evidence)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def accepted_et(acc: str) -> "datetime | None":
    """'2023-05-04T16:05:12.000Z' -> an aware ET datetime."""
    if not acc:
        return None
    try:
        s = acc.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_ET)


def charge_session(acc_et: datetime, cal: list) -> "str | None":
    """R20: the session an acceptance is charged to: the same session when at or before 16:00 ET on a session day, else the next."""
    d = acc_et.date().isoformat()
    i = bisect.bisect_left(cal, d)
    on_session = i < len(cal) and cal[i] == d
    if on_session and (acc_et.hour, acc_et.minute, acc_et.second) <= (16, 0, 0):
        return d
    j = i + 1 if on_session else i
    return cal[j] if j < len(cal) else None


def items_of(f: dict) -> list:
    return [x.strip() for x in (f.get("items") or "").split(",") if x.strip()]


def eight_k_feature(sub: "dict | None", cik: str, d0: str, cal: list, walk_sessions: list) -> dict:
    """{earnings_flag: on_climax_day | none | unknown, earnings_acceptance, earnings_after: [sessions]}."""
    out = {"earnings_flag": "unknown", "earnings_acceptance": "", "earnings_after": [], "earnings_reason": ""}
    if not cik:
        out["earnings_reason"] = "no_cik"
        return out
    if sub is None or sub.get("status") != 200:
        out["earnings_reason"] = "no_submissions"
        return out
    fl = filings_of(sub)
    if not fl:
        out["earnings_reason"] = "no_filing_history"
        return out
    forms = {f.get("form") for f in fl}
    if "8-K" not in forms and ("6-K" in forms or "20-F" in forms):
        out["earnings_reason"] = "foreign_filer_6k"
        return out
    i0 = bisect.bisect_left(cal, d0)
    prev = cal[i0 - 1] if i0 > 0 else None
    cov = coverage_from(sub)
    if cov and (i0 < 2 or cov > cal[i0 - 2]):              # R65: an acceptance charged to D0-1 can carry the filingDate of D0-2
        out["earnings_reason"] = "older_files_failed"
        return out
    hits = []
    for f in fl:
        if f.get("form") != "8-K" or X.EARNINGS_ITEM not in items_of(f):
            continue
        acc = accepted_et(f.get("acceptanceDateTime"))
        if acc is None:
            continue
        hits.append(acc)
    out["earnings_flag"] = "none"
    for acc in hits:
        ch = charge_session(acc, cal)
        if ch in (prev, d0):
            out["earnings_flag"] = "on_climax_day"
            out["earnings_acceptance"] = acc.isoformat()
            if ch and ch > d0:
                raise GuardStop(f"8-K: an acceptance charged to {ch} after D0 {d0} was counted on the climax day")
    for s in walk_sessions:
        if s > X.CUT_B:
            raise GuardStop(f"8-K: a walk session {s} after the seal {X.CUT_B} reached the earnings exit window")
        j = bisect.bisect_left(cal, s)
        nxt = cal[j + 1] if j + 1 < len(cal) else X.next_nyse_session(s)     # R20: the calendar's last session is bounded too
        close_s = datetime.combine(date.fromisoformat(s), datetime.min.time(), _ET).replace(hour=16)
        open_n = datetime.combine(date.fromisoformat(nxt), datetime.min.time(), _ET).replace(hour=9, minute=30)
        for acc in hits:
            if close_s < acc <= open_n:
                out["earnings_after"].append(s)
                break
    return out


def item_201_near(sub: "dict | None", gap_date: str, cal: list) -> tuple:
    """(bool, acceptance) — an 8-K with item 2.01 charged within [gap - 10, gap + 4] sessions (R22)."""
    if sub is None or sub.get("status") != 200:
        return (None, "")
    i = bisect.bisect_left(cal, gap_date)
    if i >= len(cal) or cal[i] != gap_date:
        return (None, "")
    lo, hi = max(0, i + X.ITEM_201_WINDOW[0]), min(len(cal) - 1, i + X.ITEM_201_WINDOW[1])
    cov = coverage_from(sub)
    if cov and (lo < 1 or cov > cal[lo - 1]):              # R65: the window's first charged filing can be dated the session before
        return (None, "")
    for f in filings_of(sub):
        if f.get("form") != "8-K" or X.DISPOSITION_ITEM not in items_of(f):
            continue
        acc = accepted_et(f.get("acceptanceDateTime"))
        if acc is None:
            continue
        ch = charge_session(acc, cal)
        if ch is None:
            continue
        j = bisect.bisect_left(cal, ch)
        if lo <= j <= hi:
            return (True, acc.isoformat())
    return (False, "")


def alpaca_ca_evidence(rec: "dict | None", gap_date: str, cal: list) -> tuple:
    """(bool | None, detail): a spin-off or a special cash distribution with an ex-date within [-2, +1] sessions of the gap."""
    if rec is None or rec.get("status") != 200:
        return (None, "no_pull" if rec is None else f"status_{rec.get('status')}")
    i = bisect.bisect_left(cal, gap_date)
    lo, hi = max(0, i + X.CA_WINDOW[0]), min(len(cal) - 1, i + X.CA_WINDOW[1])
    acts = rec.get("actions") or {}
    for kind in ("spin_offs", "cash_dividends"):
        for a in acts.get(kind) or []:
            if kind == "cash_dividends" and not a.get("special"):
                continue
            ex = (a.get("ex_date") or "")[:10]
            if not ex:
                continue
            j = bisect.bisect_left(cal, ex)
            if lo <= j <= hi:
                return (True, f"{kind}:{ex}")
    return (False, "none_in_window")


def distribution_class(ticker: str, gap_date: str, cal: list, sub, ca_rec) -> dict:
    """The written evidence rule: `distribution` with (i) an Alpaca spin-off / special distribution or (ii) an 8-K item 2.01 in the
    window; no evidence = `real_move`. Decided without looking at price."""
    ca, ca_detail = alpaca_ca_evidence(ca_rec, gap_date, cal)
    k, acc = item_201_near(sub, gap_date, cal)
    if ca:
        return {"class": "distribution", "evidence": f"alpaca:{ca_detail}"}
    if k:
        return {"class": "distribution", "evidence": f"8-K_2.01:{acc}"}
    return {"class": "real_move", "evidence": f"alpaca:{ca_detail};8-K_2.01:{'none' if k is False else 'no_submissions'}"}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# news: read 3 and the M&A keyword row (a)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def news_window_read3(cal: list, base_date: "str | None") -> "tuple | None":
    """(gte, lte, start) as ISO-8601 UTC timestamps: the three sessions [start - 2, start], start = the session after base_date;
    items published after 16:00 ET of the session before start - 2 and at or before 16:00 ET of start."""
    if not base_date or base_date not in cal:
        return None
    i = cal.index(base_date) + 1
    if i >= len(cal) or i - 3 < 0:
        return None
    start = cal[i]
    before = cal[i - 3]
    gte = datetime.combine(date.fromisoformat(before), datetime.min.time(), _ET).replace(hour=16)
    lte = datetime.combine(date.fromisoformat(start), datetime.min.time(), _ET).replace(hour=16)
    return (gte.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"), lte.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"), start)


def news_window_mna(d0: str) -> tuple:
    """[D0 - 30 calendar days, D0] as full timestamps (00:00 ET of the first day .. 16:00 ET of D0)."""
    lo = date.fromisoformat(d0) - timedelta(days=X.MNA_DAYS)
    gte = datetime.combine(lo, datetime.min.time(), _ET)
    lte = datetime.combine(date.fromisoformat(d0), datetime.min.time(), _ET).replace(hour=16)
    return (gte.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"), lte.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"))


def news_present(pull: "dict | None", ticker: str) -> dict:
    """read 3: present / absent / unknown. Unknown on a failed or non-200 pull, a truncated pull, or tagged items that carry no
    insights at all; present when an item has the ticker in `tickers` AND an `insights` entry naming it."""
    out = {"news_group": "unknown", "news_status": "", "news_pages": 0, "news_truncated": 0, "news_item_date": "", "news_reason": ""}
    if pull is None:
        out["news_reason"] = "not_pulled"
        return out
    out["news_status"], out["news_pages"], out["news_truncated"] = str(pull.get("status")), int(pull.get("pages") or 0), int(bool(pull.get("truncated")))
    if pull.get("status") != 200:
        out["news_reason"] = "http_" + str(pull.get("status"))
        return out
    if pull.get("truncated"):
        out["news_reason"] = "truncated"
        return out
    items = pull.get("items") or []
    tagged = [it for it in items if ticker in (it.get("tickers") or [])]
    if tagged and all(not it.get("insights") for it in tagged):
        out["news_reason"] = "tagged_without_insights"
        return out
    for it in sorted(tagged, key=lambda x: x.get("published_utc") or ""):
        if any((ins or {}).get("ticker") == ticker for ins in (it.get("insights") or [])):
            out["news_group"], out["news_item_date"] = "present", (it.get("published_utc") or "")[:10]
            return out
    out["news_group"] = "absent"
    return out


def mna_flag(pull: "dict | None", ticker: str) -> dict:
    """Row (a): a $0 keyword candidate in the [D0 - 30d, D0] pull (`ma_filter._candidate_articles`, the #88 rule)."""
    out = {"mna_flag": "unknown", "mna_item_date": "", "mna_keyword": ""}
    if pull is None or pull.get("status") != 200 or pull.get("truncated"):
        return out
    from agents.market_intelligence import ma_filter
    items = pull.get("items") or []
    cands = ma_filter._candidate_articles(ticker, items)
    if cands:
        item, _path, kw, _r = cands[0]
        out.update({"mna_flag": "flagged", "mna_item_date": (item.get("published_utc") or "")[:10], "mna_keyword": kw or ""})
    else:
        out["mna_flag"] = "clear"
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# read 2 — the straight-up shape (bars only)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def pause_count(rows: list, base_date, d0_idx: int) -> dict:
    """Sessions i in (base_date, D0] with close[i] < close[i-1] (the base session itself not counted); run length = sessions from
    base_date to D0; `anchor` when base_date is the 60-sessions-ago anchor (no SMA20 touch) — the caller decides that flag."""
    if base_date is None:
        return {"pause_count": None, "run_length": None}
    bi = next((k for k in range(d0_idx, -1, -1) if rows[k]["trade_date"] == base_date), None)
    if bi is None:
        return {"pause_count": None, "run_length": None}
    pauses = sum(1 for i in range(bi + 1, d0_idx + 1) if float(rows[i]["close"]) < float(rows[i - 1]["close"]))     # str->float
    return {"pause_count": pauses, "run_length": d0_idx - bi}


_STATE_TAG = re.compile(r"\s*[/\\]\s*[A-Za-z]{2,3}\s*[/\\]?\s*$")      # SEC's trailing '/DE/', '/MD', '/NEW/', '\DE\' tags
_TRAILING_NEW = re.compile(r"[\s,]+new\s*$", re.I)


def name_normal(s: str) -> str:
    """The printed normalisation for the record-vs-submissions name cross-check: SEC's state-of-incorporation and '/NEW/' tags (R14:
    'BANK OF AMERICA CORP /DE/' is Bank of America Corporation), case, punctuation, corporate suffixes."""
    s = (s or "").strip()
    prev = None
    while prev != s:                                    # 'CORP /NEW/ /DE/' and 'INC NEW' strip in turn
        prev = s
        s = _TRAILING_NEW.sub("", _STATE_TAG.sub("", s)).strip()
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    words = [w for w in s.split() if w not in {"inc", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "llc", "lp", "holdings",
                                               "holding", "group", "the", "incorporated", "sa", "nv", "ag", "se", "class", "a", "b", "common",
                                               "stock", "ordinary", "shares", "share", "adr", "ads", "depositary", "american", "trust", "n", "v"}]
    return " ".join(words)
