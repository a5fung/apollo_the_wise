"""2026-08-31 — #333 ANALYST-ESTIMATES RECORDER (the sourcing backbone's 60-day clock).

Pradeep's durability test is FORWARD: ~2 quarters realized PLUS ~4 quarters projected of
high revenue growth. The rubric can only score the trailing leg because we have never
stored a single analyst estimate — #333's build gate is this backbone plus >=60 days of
stored estimates, and the clock starts when this module's first snapshot lands.

THE LINE — read before touching anything here. DATA CAPTURE ONLY:
  - Writes EXACTLY ONE table: `mi_analyst_estimates` (+ `mi_audit_log` via the shared
    `log_audit_event` telemetry helper — never a trade-state table).
  - No rubric axis, no scoring change, no admission change lives here. The #333 axis
    itself needs operator sign-off + CHANGE_PROCESS long after this capture.
  - Read by NO grading / entry / sizing / ordering / safeguard path.
  - Never touches the 09:45 ET scan path — this is an EOD scheduled job (18:12 ET).
  - SILENT: no Telegram on any path. Errors degrade to mi_audit_log + logs; the
    detector-liveness registry (health_checks._DETECTOR_LIVENESS_TABLES,
    mi_analyst_estimates) is the watchdog for a silently-dead writer.

THE HONESTY CONSTRAINT (this decided the whole design). Estimates are point-in-time:
what FMP returns today for a future period is TODAY'S consensus — stamping it onto a
past alert date is lookahead, the defect class that invalidated the 08-25 structure
study. But there is a genuine, bounded backfill (operator-identified): an estimate for a
future period persists until that period's results land, so today's read IS the estimate
that stood on any date since THAT TICKER'S most recent filing. Hence every row stores:
  as_of_date         the date the value was READ (never inferred by a future reader)
  anchor_filing_date the ticker's most recent 10-Q/10-K-class filingDate at read time
  valid_from_date    = anchor_filing_date (or as_of_date when no anchor resolves —
                       NEVER claim history without an anchor; CHECK-enforced)
The backfill window is PER TICKER, back to its own last filing — never a flat lookback.
Measured on the real alert population (2026-08-31, SEC EDGAR filing dates, 306/335
alert tickers resolved): mean reach 28 days, median 25 — BELOW the ~45-day estimate,
because the measurement ran just past earnings season; the reach is cyclical and grows
toward ~45+ mid-cycle. `docs/analysis/analyst_estimates_backfill_reach_2026-08-31.md`.

NO-ANCHOR IS A FIRST-CLASS OUTCOME, NEVER AN ABORT (v2, 2026-09-01). The first live
run (2026-09-01 18:12 ET) wrote 0 rows with 99 errors: FMP's /income-statement — v1's
filing-date anchor — is 402 Payment Required on our plan, and v1 treated an anchor
fetch failure as a ticker-killing exception. Wrong shape: a ticker whose filing date
cannot be resolved must still record its estimates with a ZERO honest window
(valid_from_date == as_of_date) and be counted — `honest_valid_from` already encodes
that; only the orchestration aborted. NEVER invent or approximate a filing date to
widen a window — no anchor means no claimed history, full stop.

THE ANCHOR SOURCE IS SEC EDGAR (v2, 2026-09-01) — the authority FMP's filingDate is
derived from, keyless and $0, so no payment tier can take it away again:
  https://www.sec.gov/files/company_tickers.json        ticker -> CIK (1 call/run, cached)
  https://data.sec.gov/submissions/CIK##########.json   filings.recent, newest-first
Anchor = the MOST RECENT filing among ANCHOR_FORMS (10-Q/10-K/20-F/6-K + /A) — the
same conservative bound as before: the filing lands at or after the results release,
so anchoring on it claims FEWER days, never more. yfinance earnings dates were probed
and REJECTED: they are ANNOUNCEMENT dates (at-or-before the filing), so anchoring on
them would WIDEN the window — the forbidden direction. The 08-31 reach measurement
used this exact EDGAR path and resolved 306/335 real alert tickers; the unresolved 29
are ETFs/preferreds/non-filers, which buy zero days BY DESIGN. SEC asks for a
declared User-Agent (collector._SEC_UA, `SEC_USER_AGENT` env) and <=10 req/s; the run pace
is ~4 req/s worst case.

A 402 DEGRADES THE FIELD, NEVER THE TICKER (v2). Any FMP endpoint going 402 marks
that period unavailable and the snapshot continues; the run summary carries the
counts, and an annual-period 402 — the endpoint verified in-plan 2026-08-31 —
additionally writes ONE `analyst_estimates_plan_change` audit row, because that means
the FMP plan itself changed and must be visible, not silent.

RAW VALUES, NEVER A COMPUTED SCORE: thresholds belong to today's rule set; a stored
score goes stale the moment one is swept. The sketch's n_analysts<3 -> None rule is
applied READ-SIDE (`estimate_for_scoring`, threshold parameterized) and the count is
stored, so the rule can be re-tuned without re-fetching.

ENDPOINTS (estimates: FMP /stable/, the subscription we already pay for —
collector._fmp_get is the canonical transport; anchor: SEC EDGAR, above):
  /analyst-estimates?symbol=X&period=annual   verified in-plan (2026-08-31); a 402
                                              here = plan change -> audit + degrade
  /analyst-estimates?symbol=X&period=quarter  NOT yet verified — degrade gracefully:
                                              a 402 records annual only + counter
  /income-statement                           402 on our plan (verified live
                                              2026-09-01, 99/99 tickers) — NEVER call
  /earnings                                   402 on our plan — same
COST: fixed subscription — call budget only. ~3 calls per ticker per run (1 EDGAR +
2 FMP) + 1 EDGAR ticker-map call per run; the daily population (live-source EP
alerts, trailing 30 days) is ~100 tickers => ~300 calls/day, paced under FMP's
300/min limit and EDGAR's 10/s policy. The one-shot backfill over the full alert
population (~335 tickers) is ~1,000 calls, once.
The v3 quarterly leg ADDS 3 yfinance calls per ticker (revenue_estimate,
earnings_estimate, earnings_dates — fetched concurrently) and ZERO extra EDGAR
calls (the cadence facts are parsed from the SAME submissions payload already
fetched above). yfinance is free/unofficial, not a paid-plan concern; pacing is
YFINANCE_PACE_SECONDS, a courtesy, not a limit FMP_PACE_SECONDS doesn't already
dominate (see the module's pacing note below).

CREDENTIALS: FMP authenticates by QUERY STRING, so raw exception text can carry the
live key (it did — 99 audit rows on 2026-09-01). `db.log_audit_event` redacts at the
chokepoint; every log line here that formats an exception goes through
`redact_secrets` too, so the key never lands in container logs either.

THE QUARTERLY LEG IS YFINANCE (v3, 2026-09-02) — operator-approved after the pacing
root-cause: FMP's `period=quarter` is not on any FMP plan and never will be for
free; `yf.Ticker(t).revenue_estimate` / `.earnings_estimate` give '0q'/'+1q' rows
(avg/low/high/numberOfAnalysts) for $0, no key, already a dependency. Rows land in
the SAME `mi_analyst_estimates` shape the annual leg uses (period_type='quarter'
was already a valid value in the CHECK constraint) — `source` (already a column,
default 'fmp_stable') is set to 'yfinance' so a future reader can tell the two
vendors apart without guessing. No schema change was needed.

THE HARD PART: yfinance's periods are RELATIVE ('0q' = whatever quarter hasn't
reported yet, '+1q' = the one after). A stored row needs an ABSOLUTE
period_end_date or two different runs could both call themselves "the Q3
estimate" while meaning different quarters. REJECTED: anchoring on SEC EDGAR's
last-reported quarter end (reportDate, already fetched for anchor_filing_date —
see quarterly_cadence_facts) and adding a fixed 3 calendar months. Verified
empirically on real EDGAR data: AAPL's 52/53-week calendar only drifts +/-1 day
per step, but COST's 4-4-5 retail calendar missed the correct MONTH outright
(Sept 1 + 3mo = Dec 1; the real next quarter end was Nov 24) — not a rounding
error, a wrong quarter, which is exactly the guessed-date failure THE HONESTY
CONSTRAINT forbids.

CHOSEN (resolve_quarterly_period_ends): anchor '0q' on yfinance's OWN next
scheduled earnings date (next_earnings_date_from_yfinance, from `earnings_dates`
— a real, ticker-specific, always-current value: it moves in lockstep with
whichever quarter revenue_estimate/earnings_estimate currently label '0q'
because both come from the same live system) minus this ticker's OWN observed
RELEASE lag (last_actual_release_date, also from `earnings_dates`, MINUS SEC
EDGAR's last_reported_quarter_end — release compared to release, never release
compared to a filing date, per the house rule of never mixing two vendors'
different event types as if they measured the same thing). '+1q' = '0q' + this
ticker's OWN observed quarter length (last_reported_quarter_end -
prior_reported_quarter_end, an EDGAR-to-EDGAR, same-vendor comparison). Both
offsets are MEASURED facts about this ticker, never a fixed assumption — checked
against AAPL/COST/WMT during design and landed within roughly a week of the true
period end (NOT a tighter "0-2 day" precision — an earlier draft of this design
claimed that from a filing-lag formula that turned out to measure a DIFFERENT
lag than the one it was applied to; see resolve_quarterly_period_ends' own
docstring for the residual this version still carries: a company's Q4/FYE report
often releases later than a regular quarter's, so a lag measured off a regular
quarter under-estimates the FYE transition by roughly a week). This design also
closes the "reporting gap" race (a company's earnings RELEASE can precede its
formal 10-Q/10-K FILING by up to ~40 days; during that window EDGAR's anchor is
one quarter stale) MORE ROBUSTLY than the rejected filing-lag version: comparing
release-to-release, a stale-anchor mismatch inflates the measured lag by roughly
a full quarter-length, which _MAX_RELEASE_LAG_DAYS (75) reliably rejects — the
ticker is skipped and counted for that day rather than mislabeled.

DAY-TO-DAY STABILITY (stabilize_period_end, added after a second design review
caught that the above resolves a DIFFERENT, still-open problem — see next
paragraph). resolve_quarterly_period_ends' inputs are LIVE: next_earnings_date
can shift a few days as yfinance's own estimate refines, and the release
lag / quarter length can swing whenever a NEW SEC filing lands. Recomputing from
scratch every day would mint a slightly different period_end_date for the SAME
fiscal quarter — a NEW primary key — fracturing the very revision series this
table exists to build. Before storing, snapshot_ticker checks
db.get_recent_quarterly_period_ends (this ticker's own already-stored quarter
dates, `source='yfinance'`) and stabilize_period_end REUSES an existing date
within tolerance rather than minting a new one. This — not a calendar heuristic
like snapping to the nearest month-end, which was tried and rejected: it fixes
calendar-aligned filers (AAPL, WMT) but systematically MISDATES a true 4-4-5
retailer like COST, whose real quarter ends sit 1-3 weeks from any month
boundary — is the only fix verified to hold for both filer types, because it
compares against this ticker's OWN recorded history instead of any general rule.

Sanity-bounded, never a guess passed off as data: an out-of-range lag or quarter
length, or a computed '0q' that doesn't fall after the last reported quarter,
returns None for that period. QUARTERLY_CADENCE_FORMS (10-Q/10-K only, narrower
than ANCHOR_FORMS) excludes 20-F/6-K foreign-filer forms — annual-only/irregular
filing cadences can't support this lag/length arithmetic. Any ticker that cannot
resolve a period this way has that period SKIPPED and COUNTED
(quarter_yf_no_cadence) — never stored against an invented date.
⚠ EXPECT A NONZERO quarter_yf_no_cadence BASELINE EVERY NIGHT, NOT JUST ON A BAD
RUN: on any given day some slice of the population is genuinely mid reporting-gap
(released, not yet filed — see above), and the rejection there is CORRECT
behavior, not a defect to chase. A yfinance
outage or empty frame is a SEPARATE, first-class outcome (quarter_yf_unavailable)
that degrades only the quarterly leg — it never touches the annual FMP row and
never raises into the scheduler. A get_recent_quarterly_period_ends read failure
degrades to "no history to stabilize against" (today's date may drift a little;
self-heals the next run) rather than aborting anything.

NOT STORED: yfinance's growth/yearAgoRevenue/yearAgoEps/currency fields, even
though they are genuine raw (not computed) values — kept out to hold the
quarterly row to the SAME shape as the annual leg, which has never carried them
either. Revisit if a future reader actually needs them; they cost nothing to add
later (additive column) and nothing was thrown away (yfinance is queried live).

PACING: revenue_estimate + earnings_estimate + earnings_dates are fetched
concurrently per ticker (YFINANCE_PACE_SECONDS pause after), the same
run_in_executor + wait_for shape fundamentals.get_fundamentals already uses for
this synchronous, scraped library. FMP_PACE_SECONDS (12s x2) already dominates
per-ticker wall time; the yfinance pause is a modest added courtesy, not the
binding limiter.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Any, Optional

from agents.market_intelligence.db import (
    _f,
    get_analyst_estimate_population,
    get_recent_quarterly_period_ends,
    log_audit_event,
    upsert_analyst_estimates,
)
from shared.secret_redaction import redact_secrets

logger = logging.getLogger(__name__)

RECORDER_VERSION = "v3"           # v2 2026-09-01: anchor source FMP -> SEC EDGAR (402 fix)
                                   # v3 2026-09-02: quarterly leg added (yfinance, see below)
ESTIMATES_SOURCE = "fmp_stable"   # the ANNUAL estimate values are FMP; only the anchor moved
QUARTERLY_ESTIMATES_SOURCE = "yfinance"  # the QUARTERLY leg (v3) — distinguishes vendor in
                                          # the existing `source` column; no schema change
POPULATION_LOOKBACK_DAYS = 30     # daily run: tickers with a live-source alert this recent
MIN_ANALYSTS_DEFAULT = 3          # the sketch's n<3 -> None rule (read-side, re-tunable)
MAX_PERIODS_PER_CALL = 20         # bound the per-ticker estimate payload
# 🛑 PACING IS THE WHOLE BUG (root-caused 2026-09-02). This was 0.25s — its own comment said
# "~240 calls/min worst case" — against a FREE tier. FMP answers a rate breach with HTTP **402**,
# not 429, so it is indistinguishable from "endpoint not in your plan" unless you read the body:
# a plan refusal says "not available under your current subscription", a rate breach says nothing
# and CLEARS ON ITS OWN. Proven by probing the identical URL minutes apart from inside the
# container: 200 -> 402 -> 200. The 09-02 run's "99 annual-402" was NOT a plan change; the alarm
# that fired said the plan had changed, and it was wrong.
FMP_PACE_SECONDS = 12.0           # ~5 calls/min — the free tier's documented allowance

# ── SEC EDGAR anchor source (v2) ──────────────────────────────────────────────────────
# The exact form set the 08-31 reach measurement used (306/335 resolved) — foreign
# filers report on 20-F/6-K; amendments carry the same filing-date semantics.
ANCHOR_FORMS = frozenset({"10-Q", "10-K", "20-F", "6-K", "10-Q/A", "10-K/A", "20-F/A"})
# QUARTERLY_CADENCE_FORMS (v3) — a NARROWER set than ANCHOR_FORMS, used only to derive the
# quarterly-leg's lag/quarter-length facts (quarterly_cadence_facts below). 20-F is annual-only
# and 6-K interim filings are irregular for foreign private issuers — neither supports a
# quarterly cadence, so a ticker anchored only on those gets no cadence facts (its quarterly
# leg is skipped and counted) even though its ANNUAL honesty window still resolves fine.
QUARTERLY_CADENCE_FORMS = frozenset({"10-Q", "10-K", "10-Q/A", "10-K/A"})
_EDGAR_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# SEC's access policy asks every client to identify itself — with ONE identity per codebase.
# We declare collector._SEC_UA (env `SEC_USER_AGENT`), which has been this repo's SEC contact
# since #187. This module briefly shipped its own `SEC_EDGAR_USER_AGENT` (2026-09-01), which
# meant SEC saw two different names from one process for the same purpose and an operator could
# set either env var without knowing the other existed. Imported lazily inside the fetch so the
# module keeps its no-collector-at-import-time property.
_EDGAR_TIMEOUT_SECONDS = 30

# One ticker->CIK map fetch per as_of day, success OR failure — a dead sec.gov must
# cost the run ONE timeout, not one per ticker. {"as_of": date|None, "map": dict|None}.
_cik_map_state: dict[str, Any] = {"as_of": None, "map": None}

# ── quarterly leg (v3) — yfinance estimates + SEC-sourced cadence resolution ──────────
_EMPTY_CADENCE_FACTS: dict[str, Optional[date]] = {
    "last_reported_quarter_end": None, "prior_reported_quarter_end": None,
}
# Sanity bounds for resolve_quarterly_period_ends — an out-of-range lag or quarter length
# means the inputs are bad/mismatched, not that this ticker is unusual; treat it the same
# as unresolvable rather than storing an implausible date.
_MIN_RELEASE_LAG_DAYS = 0
_MAX_RELEASE_LAG_DAYS = 75        # most companies release within ~20-45 days of quarter end;
                                   # 75 is generous headroom AND (deliberately) tight enough to
                                   # reject the "reporting gap" mismatch — see the module
                                   # docstring — where the release just seen belongs to a
                                   # DIFFERENT (newer) quarter than the EDGAR anchor still
                                   # reflects: that mismatch always runs a quarter-length (~90d)
                                   # too long, so it fails this bound and is skipped, not guessed
_MIN_QUARTER_LENGTH_DAYS = 60     # a real fiscal quarter is ~91 days; COST's short Q1 measured
_MAX_QUARTER_LENGTH_DAYS = 130    # at 84 days (4-4-5 retail calendar) — bound loosely around that
_STABILIZE_TOLERANCE_DAYS = 15    # see stabilize_period_end — about half a quarter's worth of
                                   # slack: wide enough to absorb the day-level jitter a
                                   # refining next_earnings_date estimate (or a filing-boundary
                                   # lag swing) introduces run to run, narrow enough that two
                                   # genuinely DIFFERENT quarters (~90 days apart) never collapse
_STABILIZE_LOOKBACK_DAYS = 120    # how far back to look for a prior recorded date to reuse —
                                   # a bit over one quarter, so a population-coverage gap never
                                   # loses the prior snapshot of the SAME quarter
YFINANCE_PACE_SECONDS = 1.0       # a modest courtesy pause; FMP_PACE_SECONDS (12s x2) already
                                   # dominates per-ticker wall time and is the binding limiter
_YF_QUARTER_TIMEOUT_SECONDS = 30.0  # mirrors fundamentals.py's _YF_TIMEOUT
_YF_QUARTER_PERIODS = ("0q", "+1q")  # the only two yfinance periods this leg stores — '0y'/'+1y'
                                      # are the annual leg's territory (FMP), never duplicated here


# ── pure core (mock-free, the house idiom) ────────────────────────────────────────────

def _i(v) -> Optional[int]:
    """None-safe int coercion. NOT db._int_or_none — that one raises on garbage
    (its callers want a BIGINT param to fail loudly); an FMP field must degrade to
    None instead. Float coercion is db._f, imported above."""
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _d(v) -> Optional[date]:
    """ISO date string (or date) -> date; anything unparseable -> None, never a guess."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _nan_to_none(v: Any) -> Any:
    """yfinance/pandas represents a missing numeric field as float('nan'), not None.
    float(nan) survives db._f unchanged (nan is not None, so _f's guard doesn't
    catch it) and would store NaN into a DOUBLE PRECISION column — the FMP leg
    never hit this because FMP's JSON uses explicit null for a missing value.
    Filter it out before handing a value to _f/_i (_i is unaffected: int(nan)
    already raises ValueError, which _i already catches)."""
    try:
        if v is None or v != v:   # NaN is the only value that is not equal to itself
            return None
    except Exception:  # loud-ok: a value that can't even be compared is not a number
        pass
    return v


def honest_valid_from(anchor_filing_date: Optional[date], as_of: date) -> date:
    """The earliest date a value read on `as_of` can honestly be said to have stood.

    GUARD (mutation-tested): no anchor -> as_of (a row may NEVER claim history without
    a resolved filing date — ETFs/non-filers buy zero days, by design). An anchor in
    the future of the read (a bad API date) is clamped to as_of the same way.
    """
    if anchor_filing_date is None or anchor_filing_date > as_of:
        return as_of
    return anchor_filing_date


def latest_filing_from_submissions(payload: Any) -> Optional[date]:
    """EDGAR submissions payload -> the ticker's most recent anchor-form filing date.

    Pure and defensive: takes the MAX parsed date over ANCHOR_FORMS rather than
    trusting EDGAR's newest-first ordering; any malformed payload -> None (which the
    caller records as zero honest window — never a guess, never a widened window).
    """
    try:
        recent = payload["filings"]["recent"]
        forms, dates = recent["form"], recent["filingDate"]
    except (TypeError, KeyError):
        return None
    best: Optional[date] = None
    for form, fdate in zip(forms, dates):
        if form not in ANCHOR_FORMS:
            continue
        parsed = _d(fdate)
        if parsed is not None and (best is None or parsed > best):
            best = parsed
    return best


def normalize_fmp_estimate(
    rec: dict, *, ticker: str, period_type: str, as_of: date,
    anchor_filing_date: Optional[date],
) -> Optional[dict]:
    """One FMP /stable/analyst-estimates record -> one mi_analyst_estimates row.

    Raw field capture only — no derived numbers. Returns None when the record has no
    parseable period date (a row that is FOR no period is meaningless). Missing value
    fields store as NULL, never 0 — zero is a claim, NULL is an absence.
    """
    period_end = _d(rec.get("date"))
    if period_end is None:
        return None
    return {
        "ticker": ticker,
        "as_of_date": as_of,
        "anchor_filing_date": anchor_filing_date,
        "valid_from_date": honest_valid_from(anchor_filing_date, as_of),
        "period_type": period_type,
        "period_end_date": period_end,
        "revenue_avg": _f(rec.get("revenueAvg")),
        "revenue_high": _f(rec.get("revenueHigh")),
        "revenue_low": _f(rec.get("revenueLow")),
        "eps_avg": _f(rec.get("epsAvg")),
        "eps_high": _f(rec.get("epsHigh")),
        "eps_low": _f(rec.get("epsLow")),
        "num_analysts_revenue": _i(rec.get("numAnalystsRevenue")),
        "num_analysts_eps": _i(rec.get("numAnalystsEps")),
        "source": ESTIMATES_SOURCE,
        "recorder_version": RECORDER_VERSION,
    }


# ── quarterly leg (v3) — SEC-sourced cadence resolution + yfinance normalization ──────
# See the module docstring's "THE QUARTERLY LEG IS YFINANCE" section for the full design
# rationale, including why the rejected fixed-3-month extrapolation fails on 4-4-5 retail
# calendars and how the chosen lag/quarter-length design closes the reporting-gap race.


def quarterly_cadence_facts(payload: Any) -> dict[str, Optional[date]]:
    """The SEC-sourced facts resolve_quarterly_period_ends needs, pulled from the SAME
    EDGAR submissions payload already fetched for the honesty-window anchor (zero extra
    network cost) and restricted to QUARTERLY_CADENCE_FORMS (10-Q/10-K only):
      last_reported_quarter_end   reportDate of the most recent QUARTERLY_CADENCE_FORMS filing
      prior_reported_quarter_end  reportDate of the filing before that (this ticker's OWN
                                   observed quarter length = last - prior)
    Any field the payload can't support -> None; never a guess. A recent IPO with only one
    filing on record gets last_reported_quarter_end but no prior — '0q' can still resolve,
    '+1q' cannot (resolve_quarterly_period_ends handles that split)."""
    try:
        recent = payload["filings"]["recent"]
        forms, report_dates = recent["form"], recent["reportDate"]
    except (TypeError, KeyError):
        return dict(_EMPTY_CADENCE_FACTS)
    dates: list[date] = []
    for form, rdate in zip(forms, report_dates):
        if form not in QUARTERLY_CADENCE_FORMS:
            continue
        parsed = _d(rdate)
        if parsed is not None:
            dates.append(parsed)
    if not dates:
        return dict(_EMPTY_CADENCE_FACTS)
    ordered = sorted(set(dates))
    last_report = ordered[-1]
    prior_report = ordered[-2] if len(ordered) >= 2 else None
    return {"last_reported_quarter_end": last_report,
            "prior_reported_quarter_end": prior_report}


def resolve_quarterly_period_ends(
    next_earnings_date: Optional[date], last_actual_release_date: Optional[date],
    cadence: dict[str, Optional[date]],
) -> dict[str, Optional[date]]:
    """yfinance's RELATIVE quarter labels ('0q','+1q') -> ABSOLUTE period-end dates.

    '0q' = next_earnings_date - this ticker's OWN observed RELEASE lag
           (last_actual_release_date - last_reported_quarter_end — both are "the world
           learned the results" events, one from yfinance, one from SEC EDGAR's
           reportDate; comparing a RELEASE to a RELEASE, never a release to a filing).
    '+1q' = '0q' + this ticker's OWN observed quarter length (from `cadence` — see
            quarterly_cadence_facts — a same-vendor, same-quarter-type EDGAR-to-EDGAR
            comparison, so no cross-vendor mismatch risk there).
    Both offsets are MEASURED facts about THIS ticker, never a fixed assumption. See
    the module docstring for why this design (anchored on yfinance's own always-
    current next_earnings_date) out-performs a fixed-3-month extrapolation on
    irregular fiscal calendars, and why comparing release-to-release — rather than
    the earlier release-to-FILING design — closes the earnings-release-vs-10-Q-filing
    reporting-gap race more robustly: a stale EDGAR anchor during that gap produces a
    release_lag inflated by roughly one quarter-length, which _MAX_RELEASE_LAG_DAYS
    rejects outright instead of quietly mislabeling the wrong quarter.

    KNOWN RESIDUAL (documented, not solved here): a company's Q4/FYE report often
    takes longer to release than a regular quarter (audited annual figures), so a
    lag measured from a REGULAR quarter slightly under-estimates the FYE quarter's
    true release lag (and vice versa) — checked against real COST/AAPL/WMT EDGAR
    data during design, this shows up as roughly a week of extra imprecision on a
    regular-to-FYE transition, not a wrong-quarter failure. snapshot_ticker's
    stabilize_period_end then LOCKS IN whichever date resolves first, so this
    residual affects a quarter's INITIAL label once, never its day-to-day stability.

    Sanity-bounded, never a guess passed off as data: missing inputs, an out-of-range
    lag or quarter length, or a computed '0q' that doesn't fall after the last
    reported quarter, return None for that period — the caller skips and counts it."""
    out: dict[str, Optional[date]] = {"0q": None, "+1q": None}
    last_q_end = cadence.get("last_reported_quarter_end")
    prior_q_end = cadence.get("prior_reported_quarter_end")
    if next_earnings_date is None or last_q_end is None or last_actual_release_date is None:
        return out
    release_lag_days = (last_actual_release_date - last_q_end).days
    if not (_MIN_RELEASE_LAG_DAYS <= release_lag_days <= _MAX_RELEASE_LAG_DAYS):
        return out
    q0 = next_earnings_date - timedelta(days=release_lag_days)
    if q0 <= last_q_end:
        return out
    out["0q"] = q0
    if prior_q_end is not None:
        quarter_len = (last_q_end - prior_q_end).days
        if _MIN_QUARTER_LENGTH_DAYS <= quarter_len <= _MAX_QUARTER_LENGTH_DAYS:
            out["+1q"] = q0 + timedelta(days=quarter_len)
    return out


def stabilize_period_end(
    candidate: Optional[date], recent_dates: list[date],
    tolerance_days: int = _STABILIZE_TOLERANCE_DAYS,
) -> Optional[date]:
    """THE LABEL-STABILITY FIX: if an EXISTING stored period_end_date for this ticker
    (`recent_dates` — see db.get_recent_quarterly_period_ends, which orders them
    MOST-RECENTLY-WRITTEN FIRST) is within `tolerance_days` of a freshly computed
    `candidate`, REUSE that existing date instead of the new one.

    WHY THIS EXISTS: resolve_quarterly_period_ends anchors on yfinance's live
    next_earnings_date, which can shift a few days as the estimate refines, and on
    the SEC's observed release lag, which can swing when a NEW filing lands (a
    fresh reportDate/lag pair). Recomputing from scratch every day would mint a
    slightly different period_end_date — and therefore a DIFFERENT primary key —
    for what is really the SAME fiscal quarter, fracturing the revision series this
    table exists to build (get_analyst_estimates_asof's
    DISTINCT ON (period_type, period_end_date) would then read one quarter as two
    or three). Reusing recorded history, rather than a calendar heuristic (e.g.
    snapping to the nearest month-end), is the ONLY fix verified to work for BOTH
    calendar-aligned filers (AAPL, WMT) and true 4-4-5 retail filers (COST) — a
    month-end snap fixes the former and systematically misdates the latter (COST's
    real quarter ends land 1-3 weeks from any month boundary).

    TIE-BREAK IS RECENCY, NOT DISTANCE (design review, 2026-09-02): the FIRST entry
    in `recent_dates` within tolerance wins, even if a later (older) entry happens
    to sit a day or two closer to `candidate`. This matters when more than one
    historical date sits within tolerance at once — e.g. an early, poorly-informed
    estimate from months ago (yfinance's date guessed ~6 months before the actual
    report) alongside a recently-confirmed one. Picking "numerically nearest"
    there could resurrect the stale early guess over the label the series most
    recently settled on; picking "most recently written, if plausible" keeps the
    series following its own confirmed history. Requires the caller to pass
    `recent_dates` in that order — get_recent_quarterly_period_ends already does.

    None candidate, or no recent history to check against, passes through
    unchanged (nothing to stabilize; the FIRST time a quarter is seen, its
    freshly resolved date is what gets recorded — and, by construction, becomes
    the label every later run converges back onto)."""
    if candidate is None:
        return candidate
    for stored in recent_dates:
        if abs((stored - candidate).days) <= tolerance_days:
            return stored
    return candidate


def next_earnings_date_from_yfinance(df: Any) -> Optional[date]:
    """The soonest date in a yfinance `earnings_dates` frame that has NO Reported EPS
    yet — yfinance's own live "next quarter to report," which is exactly what
    resolve_quarterly_period_ends anchors '0q' on. Defensive: any shape surprise
    (yfinance is unofficial and scraped) -> None, never a guess."""
    try:
        if df is None or df.empty or "Reported EPS" not in df.columns:
            return None
        pending = df[df["Reported EPS"].isna()]
        if pending.empty:
            return None
        idx = pending.index.min()
        return idx.date() if hasattr(idx, "date") else None
    except Exception:  # loud-ok: optional-parse fallback — yfinance is unofficial and
                        # scraped, any shape surprise here just means "unknown," never a guess
        return None


def last_actual_earnings_date_from_yfinance(df: Any) -> Optional[date]:
    """The MOST RECENT date in a yfinance `earnings_dates` frame that HAS a Reported
    EPS — this ticker's own last actual results RELEASE, the release-side half of
    resolve_quarterly_period_ends' release-to-release lag measurement (the other
    half, last_reported_quarter_end, is SEC EDGAR's reportDate for the SAME
    quarter). Defensive: any shape surprise -> None, never a guess."""
    try:
        if df is None or df.empty or "Reported EPS" not in df.columns:
            return None
        reported = df[df["Reported EPS"].notna()]
        if reported.empty:
            return None
        idx = reported.index.max()
        return idx.date() if hasattr(idx, "date") else None
    except Exception:  # loud-ok: optional-parse fallback — same defensive posture as
                        # next_earnings_date_from_yfinance just above
        return None


def _yf_period_row(df: Any, period: str) -> Optional[dict]:
    """One row of a yfinance revenue_estimate/earnings_estimate DataFrame -> a plain
    dict, or None when the frame is missing/empty/lacks the period (yfinance is
    unofficial and scraped — every shape is untrustworthy by default)."""
    try:
        if df is None or period not in df.index:
            return None
        return df.loc[period].to_dict()
    except Exception:  # loud-ok: optional-parse fallback — same as above, a shape
                        # surprise on a scraped frame degrades to "no row," not a guess
        return None


def normalize_yfinance_quarterly_estimate(
    *, ticker: str, yf_period: str, as_of: date,
    anchor_filing_date: Optional[date], period_end_date: Optional[date],
    revenue_row: Optional[dict], earnings_row: Optional[dict],
) -> Optional[dict]:
    """One yfinance revenue_estimate/earnings_estimate period ('0q' or '+1q') -> one
    mi_analyst_estimates row, in the SAME shape normalize_fmp_estimate produces — a
    future reader cannot tell which vendor a field came from without checking `source`
    (set to QUARTERLY_ESTIMATES_SOURCE here, ESTIMATES_SOURCE for the annual/FMP leg).
    Raw capture only, same discipline as the annual leg: growth/yearAgoRevenue/
    yearAgoEps/currency are available on the yfinance frames but deliberately NOT
    stored — kept out to hold this row to the annual leg's shape, which has never
    carried them either (see the module docstring).

    Returns None when the period end date could not be resolved (never store against
    a guessed date — the caller already enforces this by only calling with a resolved
    date, but the guard holds here too) or when neither vendor row has any data.
    Missing individual fields store as NULL, never 0 — zero is a claim, NULL is an
    absence (NaN, yfinance's own "missing" sentinel, is normalized to NULL too via
    _nan_to_none, unlike FMP's explicit JSON null which _f/_i already handle)."""
    if period_end_date is None:
        return None
    if not revenue_row and not earnings_row:
        return None
    revenue_row = revenue_row or {}
    earnings_row = earnings_row or {}
    return {
        "ticker": ticker,
        "as_of_date": as_of,
        "anchor_filing_date": anchor_filing_date,
        "valid_from_date": honest_valid_from(anchor_filing_date, as_of),
        "period_type": "quarter",
        "period_end_date": period_end_date,
        "revenue_avg": _f(_nan_to_none(revenue_row.get("avg"))),
        "revenue_high": _f(_nan_to_none(revenue_row.get("high"))),
        "revenue_low": _f(_nan_to_none(revenue_row.get("low"))),
        "eps_avg": _f(_nan_to_none(earnings_row.get("avg"))),
        "eps_high": _f(_nan_to_none(earnings_row.get("high"))),
        "eps_low": _f(_nan_to_none(earnings_row.get("low"))),
        "num_analysts_revenue": _i(_nan_to_none(revenue_row.get("numberOfAnalysts"))),
        "num_analysts_eps": _i(_nan_to_none(earnings_row.get("numberOfAnalysts"))),
        "source": QUARTERLY_ESTIMATES_SOURCE,
        "recorder_version": RECORDER_VERSION,
    }


def estimate_for_scoring(
    row: dict, min_analysts: int = MIN_ANALYSTS_DEFAULT
) -> Optional[dict]:
    """READ-SIDE neglect rule (the sketch's contract, mutation-tested): a thin-coverage
    estimate scores None — the missing-data scaling absorbs it; never penalize the
    un-covered. The count is STORED on every row so this threshold can be re-tuned
    without re-fetching. An unknown count is thin by definition (None, not 0 analysts,
    but either way not >= min_analysts).

    THE LINE: no live path calls this today — it exists so the future #333 axis has ONE
    sanctioned accessor instead of re-deriving the rule per caller.
    """
    n = row.get("num_analysts_revenue")
    if n is None or n < min_analysts:
        return None
    return row


# ── anchor fetch (SEC EDGAR — keyless, $0, no payment tier) ───────────────────────────

async def _edgar_get_json(url: str) -> Any:
    import httpx

    from agents.market_intelligence.collector import _SEC_UA
    # ⚠ KNOWN, MEASURED, DELIBERATELY NOT FIXED HERE: this opens a fresh connection per call —
    # ~100 TLS handshakes on the daily run (est. 5-20s) and ~335 on the backfill. Reusing one
    # client means threading it through snapshot_ticker and _fetch_last_filing_date, both of
    # which the test suite monkeypatches by signature. Seconds on a once-a-day job did not
    # justify churning those the day after this module shipped. Revisit if the population grows.
    async with httpx.AsyncClient(
        timeout=_EDGAR_TIMEOUT_SECONDS, headers=_SEC_UA
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def _get_cik_map(as_of: date) -> Optional[dict]:
    """Ticker->CIK map, fetched AT MOST ONCE per as_of day (success or failure) —
    a dead sec.gov costs the run one timeout, never one per ticker. None = the map
    is unavailable today; callers raise so the failure is COUNTED per ticker
    (anchor_errors), distinguishing an EDGAR outage from true non-filers."""
    if _cik_map_state["as_of"] == as_of:
        return _cik_map_state["map"]
    _cik_map_state["as_of"] = as_of
    _cik_map_state["map"] = None
    try:
        raw = await _edgar_get_json(_EDGAR_TICKER_MAP_URL)
        _cik_map_state["map"] = {
            str(v["ticker"]).upper(): int(v["cik_str"]) for v in raw.values()
        }
    except Exception as e:
        logger.warning(f"EDGAR ticker map fetch failed: "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
    return _cik_map_state["map"]


# One EDGAR submissions payload fetched AT MOST ONCE per (ticker, as_of day), reduced
# IMMEDIATELY to the small set of dates this module needs, then discarded — deliberately
# NOT caching the raw payload (a single ticker's submissions JSON can run past 1MB; the
# backfill touches ~335 tickers in one run, so retaining all of them would be real memory).
# Both _fetch_last_filing_date (the honesty-window anchor) and _fetch_quarter_cadence_facts
# (the v3 quarterly-leg cadence facts) read this cache, so one ticker never costs SEC EDGAR
# two requests for the same information. {"as_of": date|None, "facts": {ticker: dict}}.
_edgar_facts_cache_state: dict[str, Any] = {"as_of": None, "facts": {}}


async def _get_edgar_facts(ticker: str, as_of: date) -> dict[str, Any]:
    """Fetch this ticker's EDGAR submissions payload (at most once per ticker per
    as_of day) and immediately reduce it to {"anchor_filing_date": ..., plus the
    quarterly_cadence_facts keys}. None-CIK (ETF/non-filer) resolves to all-None
    facts, not an exception. Raises on transport failure (NOT cached as a failure —
    each ticker is only visited once per run anyway) so the caller can COUNT it
    (anchor_errors); the caller still records the ticker with a zero window rather
    than aborting the snapshot."""
    if _edgar_facts_cache_state["as_of"] != as_of:
        _edgar_facts_cache_state["as_of"] = as_of
        _edgar_facts_cache_state["facts"] = {}
    cache = _edgar_facts_cache_state["facts"]
    key = ticker.upper()
    if key in cache:
        return cache[key]
    cik_map = await _get_cik_map(as_of)
    if cik_map is None:
        raise RuntimeError("EDGAR ticker map unavailable")
    cik = cik_map.get(key)
    if cik is None:
        # ETF / preferred / non-filer — zero honest days AND no cadence facts, by design.
        facts = {"anchor_filing_date": None, **_EMPTY_CADENCE_FACTS}
        cache[key] = facts
        return facts
    payload = await _edgar_get_json(_EDGAR_SUBMISSIONS_URL.format(cik=cik))
    facts = {"anchor_filing_date": latest_filing_from_submissions(payload),
             **quarterly_cadence_facts(payload)}
    cache[key] = facts
    return facts


async def _fetch_last_filing_date(ticker: str, as_of: date) -> Optional[date]:
    """The ticker's most recent anchor-form EDGAR filing date — the honest-window
    anchor. None = the ticker genuinely resolves no filing (not in EDGAR's map, or
    no anchor-form filing) -> zero honest window BY DESIGN. Raises on transport
    failure so the caller can COUNT it (anchor_errors) — but the caller still
    records the ticker with a zero window; no anchor path aborts a snapshot.

    v1 used FMP /income-statement filingDate; it is 402 on our plan (2026-09-01,
    99/99 tickers) — never call it again."""
    facts = await _get_edgar_facts(ticker, as_of)
    return facts["anchor_filing_date"]


async def _fetch_quarter_cadence_facts(ticker: str, as_of: date) -> dict[str, Optional[date]]:
    """The v3 quarterly-leg cadence facts (see quarterly_cadence_facts) for this
    ticker — shares the SAME EDGAR fetch as _fetch_last_filing_date via
    _get_edgar_facts, so this never costs a second network round trip. Raises on
    transport failure exactly like _fetch_last_filing_date (same underlying call);
    snapshot_ticker calls both inside one try block, so an EDGAR outage degrades
    ONE ticker's whole anchor story (annual window AND quarterly cadence) together,
    never independently."""
    facts = await _get_edgar_facts(ticker, as_of)
    return {k: v for k, v in facts.items() if k != "anchor_filing_date"}


# ── estimates fetch (collector._fmp_get is the canonical FMP transport) ───────────────

async def _fetch_estimates(ticker: str, period: str) -> list[dict]:
    from agents.market_intelligence.collector import _fmp_get
    out = await _fmp_get("/analyst-estimates",
                         {"symbol": ticker, "period": period,
                          "page": 0, "limit": MAX_PERIODS_PER_CALL})
    return out if isinstance(out, list) else []


def _is_payment_required(exc: Exception) -> bool:
    """True for FMP's 402 (endpoint not in plan) — the degrade-not-die case."""
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None) == 402


# ── quarterly estimates fetch (v3 — yfinance, unofficial and scraped) ────────────────
# THE LINE for this function specifically: every failure mode here (import error, bad
# ticker, timeout, malformed frame, scrape breakage) returns None. It never raises past
# this function and never touches the annual FMP row — see snapshot_ticker's call site.

async def _fetch_yfinance_quarterly(ticker: str) -> Optional[dict[str, Any]]:
    """revenue_estimate + earnings_estimate + earnings_dates via yfinance, for the two
    quarterly periods ('0q','+1q') plus the next scheduled earnings date AND the last
    actual release date (resolve_quarterly_period_ends needs both — see
    next_earnings_date_from_yfinance / last_actual_earnings_date_from_yfinance).
    Uses the same run_in_executor + wait_for shape as fundamentals.get_fundamentals —
    this repo's house pattern for calling this synchronous, scraped library from
    async code. Returns None (never raises) on any failure, or when neither period has
    any data at all; otherwise {"next_earnings_date": date|None,
    "last_actual_release_date": date|None,
    "periods": {"0q"|"+1q": {"revenue": dict|None, "earnings": dict|None}}}."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        loop = asyncio.get_event_loop()
        t = yf.Ticker(ticker.upper())
    except Exception as e:
        logger.warning(f"yfinance Ticker init failed for {ticker}: "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
        return None

    def _fetch_revenue():
        return t.revenue_estimate

    def _fetch_earnings():
        return t.earnings_estimate

    def _fetch_earnings_dates():
        return t.earnings_dates

    try:
        revenue_df, earnings_df, dates_df = await asyncio.gather(
            asyncio.wait_for(loop.run_in_executor(None, _fetch_revenue),
                              timeout=_YF_QUARTER_TIMEOUT_SECONDS),
            asyncio.wait_for(loop.run_in_executor(None, _fetch_earnings),
                              timeout=_YF_QUARTER_TIMEOUT_SECONDS),
            asyncio.wait_for(loop.run_in_executor(None, _fetch_earnings_dates),
                              timeout=_YF_QUARTER_TIMEOUT_SECONDS),
            return_exceptions=True,
        )
    except Exception as e:  # loud-ok: gather itself failing is as good as every leg failing
        logger.warning(f"yfinance quarterly gather failed for {ticker}: "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
        return None
    if isinstance(revenue_df, Exception):
        logger.warning(f"yfinance revenue_estimate failed for {ticker}: "
                       f"{redact_secrets(f'{type(revenue_df).__name__}: {revenue_df}')}")
        revenue_df = None
    if isinstance(earnings_df, Exception):
        logger.warning(f"yfinance earnings_estimate failed for {ticker}: "
                       f"{redact_secrets(f'{type(earnings_df).__name__}: {earnings_df}')}")
        earnings_df = None
    if isinstance(dates_df, Exception):
        logger.warning(f"yfinance earnings_dates failed for {ticker}: "
                       f"{redact_secrets(f'{type(dates_df).__name__}: {dates_df}')}")
        dates_df = None

    periods: dict[str, Any] = {}
    for period in _YF_QUARTER_PERIODS:
        rev_row = _yf_period_row(revenue_df, period)
        earn_row = _yf_period_row(earnings_df, period)
        if rev_row is None and earn_row is None:
            continue
        periods[period] = {"revenue": rev_row, "earnings": earn_row}
    if not periods:
        return None
    return {"next_earnings_date": next_earnings_date_from_yfinance(dates_df),
            "last_actual_release_date": last_actual_earnings_date_from_yfinance(dates_df),
            "periods": periods}


async def snapshot_ticker(ticker: str, as_of: date) -> dict[str, Any]:
    """Fetch + normalize one ticker's estimates. Returns {rows, annual_unavailable,
    anchor, anchor_error, quarter_yf_rows, quarter_yf_unavailable,
    quarter_yf_no_cadence} — raises only on a hard ANNUAL FMP fetch failure the
    caller counts (per-ticker isolation lives in the run loop, not here). The anchor
    NEVER aborts: an unresolvable or failed anchor records the rows with a zero
    honest window (the 2026-09-01 first-run bug was exactly this abort). The v3
    quarterly (yfinance) leg is equally non-fatal: any failure there degrades to
    nothing-recorded-and-counted and never touches the annual row."""
    anchor: Optional[date] = None
    quarter_cadence: dict[str, Optional[date]] = dict(_EMPTY_CADENCE_FACTS)
    anchor_error = False
    try:
        anchor = await _fetch_last_filing_date(ticker, as_of)
        quarter_cadence = await _fetch_quarter_cadence_facts(ticker, as_of)
    except Exception as e:
        # FIRST-CLASS no-anchor: zero honest window (annual leg) + no cadence facts
        # (quarterly leg), counted, never fatal. One EDGAR outage degrades this
        # ticker's whole anchor story, not two independent ones (both calls share
        # the same underlying fetch — see _get_edgar_facts).
        anchor_error = True
        logger.warning(f"anchor fetch failed for {ticker} (zero honest window): "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
    # ⏱ THE YFINANCE LEG STARTS HERE, NOT AFTER THE FMP SLEEPS (2026-09-02). It is a different
    # vendor with an independent rate limit, so running it in series behind FMP's two deliberate
    # 12s pauses just adds its latency to every ticker — roughly 2-8 minutes across the ~99-ticker
    # nightly population, and ~3x that on the one-shot backfill. Launched as a task, awaited only
    # where its result is needed, so the pauses become cover time. It still cannot take the annual
    # row down: _fetch_yfinance_quarterly catches everything internally.
    _yf_task = asyncio.ensure_future(_fetch_yfinance_quarterly(ticker))

    await asyncio.sleep(FMP_PACE_SECONDS)
    rows: list[dict] = []
    annual_unavailable = False
    # ⚠ ANNUAL ONLY FROM FMP (2026-09-02). `period=quarter` is NOT on this tier — FMP says so
    # explicitly: "This value set for 'period' is not available under your current subscription".
    # Calling it anyway DOUBLED our call volume for a guaranteed 402, on the exact quota the
    # annual call needs, which is how a working endpoint came back 99-for-99 empty. The quarterly
    # leg is yfinance — see the module docstring's "THE QUARTERLY LEG IS YFINANCE" section.
    # Straight-line rather than a one-element loop: a `for period in ("annual",)` reads as though
    # a per-period fetch still happens, and carried a `quarter_unavailable` counter that could
    # never be anything but zero.
    try:
        recs = await _fetch_estimates(ticker, "annual")
    except Exception as e:
        if not _is_payment_required(e):
            raise
        # A 402 degrades the FIELD, never the ticker. Annual IS in-plan (verified 08-31,
        # re-verified 09-02), so a 402 here is most likely a RATE BREACH — FMP answers both
        # with 402 — which is why the run loop's alarm no longer asserts a plan change.
        annual_unavailable = True
        recs = []
    for rec in recs:
        row = normalize_fmp_estimate(
            rec, ticker=ticker, period_type="annual", as_of=as_of,
            anchor_filing_date=anchor,
        )
        if row is not None:
            rows.append(row)
    await asyncio.sleep(FMP_PACE_SECONDS)

    # ── quarterly leg (v3, yfinance) — never raises past this block ──────────────────
    quarter_yf_unavailable = False
    quarter_no_cadence = False
    quarter_rows: list[dict] = []
    try:
        yf_data = await _yf_task          # started before the FMP pauses; usually already done
    except Exception as e:  # belt-and-suspenders: _fetch_yfinance_quarterly already
        # catches everything internally and returns None, but this leg must NEVER be
        # able to take the annual row down with it even if that contract slips.
        yf_data = None
        logger.warning(f"yfinance quarterly fetch failed for {ticker} (annual row "
                       f"unaffected): {redact_secrets(f'{type(e).__name__}: {e}')}")
    if not yf_data:
        quarter_yf_unavailable = True
    else:
        resolved = resolve_quarterly_period_ends(
            yf_data.get("next_earnings_date"), yf_data.get("last_actual_release_date"),
            quarter_cadence)
        # STABILITY (see stabilize_period_end): reuse an already-recorded date for this
        # SAME quarter rather than minting a slightly-different one from today's live
        # inputs. A read failure here degrades to "no history to check" — today's
        # labels may drift, but nothing aborts, and it self-heals the moment the read
        # succeeds again.
        recent_period_ends: list[date] = []
        try:
            recent_period_ends = await get_recent_quarterly_period_ends(
                ticker, as_of - timedelta(days=_STABILIZE_LOOKBACK_DAYS))
        except Exception as e:
            logger.warning(f"recent period-end lookup failed for {ticker} (today's "
                           f"quarterly labels may drift; self-heals next run): "
                           f"{redact_secrets(f'{type(e).__name__}: {e}')}")
        for period, payload in yf_data["periods"].items():
            period_end = stabilize_period_end(resolved.get(period), recent_period_ends)
            row = normalize_yfinance_quarterly_estimate(
                ticker=ticker, yf_period=period, as_of=as_of,
                anchor_filing_date=anchor, period_end_date=period_end,
                revenue_row=payload.get("revenue"), earnings_row=payload.get("earnings"),
            )
            if row is not None:
                quarter_rows.append(row)
        if not quarter_rows:
            # yfinance HAD data for this ticker but no period could be resolved to an
            # absolute date (no cadence facts, or every candidate failed the sanity
            # bounds) — skipped and counted, never stored against a guessed date.
            quarter_no_cadence = True
    rows.extend(quarter_rows)

    return {"rows": rows, "annual_unavailable": annual_unavailable,
            "anchor": anchor, "anchor_error": anchor_error,
            "quarter_yf_rows": len(quarter_rows),
            "quarter_yf_unavailable": quarter_yf_unavailable,
            "quarter_yf_no_cadence": quarter_no_cadence}


# ── run functions (never raise into the scheduler — the house shadow contract) ────────

async def _run_over_tickers(tickers: list[str], as_of: date, label: str) -> dict[str, Any]:
    out = {"population": len(tickers), "tickers_written": 0, "rows_written": 0,
           "no_anchor": 0, "anchor_errors": 0,
           "annual_unavailable": 0, "errors": 0,
           "quarter_yf_rows_written": 0, "quarter_yf_unavailable": 0,
           "quarter_yf_no_cadence": 0}
    for ticker in tickers:
        try:
            snap = await snapshot_ticker(ticker, as_of)
            written = await upsert_analyst_estimates(snap["rows"])
            out["rows_written"] += written
            if written:
                out["tickers_written"] += 1
            out["quarter_yf_rows_written"] += snap["quarter_yf_rows"]
            if snap["quarter_yf_unavailable"]:
                out["quarter_yf_unavailable"] += 1   # yfinance outage/empty for this ticker
            if snap["quarter_yf_no_cadence"]:
                out["quarter_yf_no_cadence"] += 1    # yfinance had data, period end unresolvable
            if snap["anchor_error"]:
                out["anchor_errors"] += 1        # EDGAR outage — NOT the by-design case
            elif snap["anchor"] is None:
                out["no_anchor"] += 1            # true non-filer/ETF — zero days by design
            if snap["annual_unavailable"]:
                out["annual_unavailable"] += 1
        except Exception as e:  # per-ticker isolation: one bad name never kills the run
            out["errors"] += 1
            logger.warning(redact_secrets(
                f"{label}: {ticker} failed: {type(e).__name__}: {e}"))
            try:
                await log_audit_event(
                    "analyst_estimates_error",
                    f"{label}: {ticker}: {type(e).__name__}: {e}"[:400],
                )
            except Exception:  # loud-ok: logger.warning above already fired
                pass
    if out["annual_unavailable"]:
        # Annual is IN-PLAN (verified 2026-08-31, re-verified 2026-09-02). A 402 here is
        # therefore almost always a RATE BREACH — FMP returns 402 for both, which is why the
        # 09-02 run read as a plan change when it was our own 240-calls/min pacing. One loud
        # row per run either way: a run that stored nothing must never be silent.
        try:
            await log_audit_event(
                "analyst_estimates_plan_change",
                f"{label}: /analyst-estimates period=annual returned 402 for "
                f"{out['annual_unavailable']} ticker(s). FMP answers a RATE BREACH with 402, "
                f"not 429, so this is most likely pacing, not a plan change — verified "
                f"2026-09-02 by probing the identical URL minutes apart: 200 -> 402 -> 200. "
                f"Check the pace before assuming a downgrade; a genuine plan refusal says "
                f"'not available under your current subscription' in the body and does NOT "
                f"clear on its own.",
            )
        except Exception:  # loud-ok: the run-summary row still carries the counter
            pass
    return out


_EMPTY_RUN = {"population": 0, "tickers_written": 0, "rows_written": 0,
              "no_anchor": 0, "anchor_errors": 0,
              "annual_unavailable": 0, "errors": 1,
              "quarter_yf_rows_written": 0, "quarter_yf_unavailable": 0,
              "quarter_yf_no_cadence": 0}


async def _run_and_log(tickers: list[str], today: date, event_type: str,
                       summary_prefix: str = "") -> dict[str, Any]:
    """Run the population and write ONE audit row. The daily snapshot and the one-shot
    backfill are the same run over different populations — extracted so a change to the
    counters or the audit shape lands in one place, not two (the duplication class
    `_persist_minute_bars_for_ticker_day` was pulled apart for the same day).
    Never raises into the scheduler; SILENT (no Telegram on any path)."""
    try:
        out = await _run_over_tickers(tickers, today, event_type)
        try:
            await log_audit_event(
                event_type,
                f"{summary_prefix}{out['rows_written']} row(s) across "
                f"{out['tickers_written']}/{out['population']} ticker(s) "
                f"({out['quarter_yf_rows_written']} quarterly-from-yfinance); "
                f"{out['no_anchor']} no-anchor (zero honest days, by design), "
                f"{out['anchor_errors']} anchor-error (zero honest days, EDGAR fetch failed), "
                f"{out['annual_unavailable']} annual-402, "
                f"{out['quarter_yf_no_cadence']} quarter-no-cadence-anchor "
                f"(yfinance had data, period end unresolvable — no EDGAR cadence facts, "
                f"OR the ticker is mid reporting-gap today; a nonzero baseline here EVERY "
                f"night is expected, not a defect — see the module docstring), "
                f"{out['quarter_yf_unavailable']} quarter-yfinance-unavailable, "
                f"{out['errors']} error(s)",
            )
        except Exception:  # loud-ok: counters already logged by the scheduler wrapper
            pass
        return out
    except Exception as e:
        logger.error(f"{event_type} failed: {e}", exc_info=True)
        return dict(_EMPTY_RUN)


async def run_analyst_estimates_snapshot(
    today: date, tickers: "list[str] | None" = None
) -> dict[str, Any]:
    """The daily 18:12 ET snapshot. Population: live-source EP-alert tickers from the
    trailing POPULATION_LOOKBACK_DAYS — today's alerts get their estimates recorded
    the same evening (honest as-of the alert day: as_of_date is the read date, never
    back-stamped), and recent-alert names keep accruing a revision series."""
    try:
        if tickers is None:
            from datetime import timedelta
            since = today - timedelta(days=POPULATION_LOOKBACK_DAYS)
            tickers = await get_analyst_estimate_population(since)
    except Exception as e:
        logger.error(f"analyst_estimates_snapshot population query failed: {e}", exc_info=True)
        return dict(_EMPTY_RUN)
    return await _run_and_log(tickers, today, "analyst_estimates_snapshot")


async def run_analyst_estimates_backfill(today: date) -> dict[str, Any]:
    """The ONE-SHOT bounded backfill (run by hand at deploy, not scheduled): a snapshot
    over the FULL live-source alert population, all history. The per-ticker honest
    window [anchor_filing_date, as_of_date] is baked into every row — the backfill IS
    a snapshot with a wider population; the valid-from semantics do the rest. A ticker
    that reported last week buys days; one with no resolvable filing buys ZERO, by
    design. ~1,000 calls once (~335 tickers x 3)."""
    try:
        tickers = await get_analyst_estimate_population(date(2000, 1, 1))
    except Exception as e:
        logger.error(f"analyst_estimates_backfill population query failed: {e}", exc_info=True)
        return dict(_EMPTY_RUN)
    return await _run_and_log(tickers, today, "analyst_estimates_backfill",
                              summary_prefix="one-shot backfill: ")
