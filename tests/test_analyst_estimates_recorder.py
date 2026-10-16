"""#333 analyst-estimates recorder tests (2026-08-31; v2 2026-09-01; v3 2026-09-02).
Pure core (normalize / honest_valid_from / latest_filing_from_submissions /
estimate_for_scoring / the v3 quarterly-cadence resolution) + the orchestration half
with module-level db/fetch functions monkeypatched. THE LINE: this recorder writes
only mi_analyst_estimates (+ mi_audit_log via log_audit_event) and is SILENT — both
pinned below.

THE BUG the v2 arm exists for (2026-09-01, first live run): the filing-date anchor was
FMP /income-statement, which is 402 Payment Required on our plan — and v1 treated an
anchor fetch failure as a ticker-killing exception, so the run wrote 0 rows with 99
errors. The design already said a ticker with no resolvable filing date records with a
ZERO honest window (honest_valid_from(None) == as_of); only the orchestration aborted.
v2 anchors on SEC EDGAR (keyless, no payment tier) and makes no-anchor a FIRST-CLASS
outcome; a 402 on any FMP endpoint degrades that period, never the ticker. The honesty
contract (never claim history without a filing-date anchor; the read date is stamped,
never inferred) is the load-bearing guard here and is what the mutation tests target.

v3 (2026-09-02) adds the QUARTERLY leg from yfinance (FMP's period=quarter is not on
any FMP plan, ever — see the module docstring). yfinance's '0q'/'+1q' periods are
RELATIVE; resolve_quarterly_period_ends turns them into ABSOLUTE period_end_dates
using this ticker's OWN observed SEC filing lag + quarter length, anchored on
yfinance's own live next_earnings_date — verified against real AAPL/COST/WMT EDGAR
data during design (see the module docstring for why a naive fixed-3-month
extrapolation was rejected: it silently picked the WRONG MONTH on COST's 4-4-5
retail calendar). Every path here that cannot resolve a period returns None and the
caller skips + counts it — never a guessed date.

2026-10-16: the FMP /analyst-estimates ANNUAL leg was REMOVED (free tier serves ~1
ticker in 12; 21-26 `api_failure_fmp` rows a night for no estimate). yfinance is the
source of record, Finnhub the cross-check. What replaced the FMP-era tests: a spy
proving the job never calls FMP, the per-ticker pace now enforced on the yfinance
cadence the FMP sleeps used to impose, and the run-level `analyst_estimates_error` row a
run writes when yfinance recorded nothing (the FMP-era failures were loud only by accident).
"""
import asyncio
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import analyst_estimates_recorder as aer

AS_OF = date(2026, 8, 31)


# ── honest_valid_from (the lookahead guard — mutation target) ────────────────────────


def test_honest_window_anchors_on_the_filing_date():
    assert aer.honest_valid_from(date(2026, 7, 31), AS_OF) == date(2026, 7, 31)


def test_honest_window_without_anchor_claims_zero_history():
    """MUTATION TARGET: a row with no resolvable filing date may NEVER claim history —
    valid_from collapses to the read date (an ETF/non-filer buys zero days, by
    design). Dropping this guard is exactly the lookahead defect that invalidated
    the 08-25 structure study."""
    assert aer.honest_valid_from(None, AS_OF) == AS_OF


def test_honest_window_clamps_a_future_anchor():
    """A filingDate AFTER the read date is bad API data — clamp to the read date,
    never claim a window that starts in the future."""
    assert aer.honest_valid_from(date(2026, 9, 15), AS_OF) == AS_OF


# ── latest_filing_from_submissions (the EDGAR anchor parse — pure) ───────────────────


def _submissions(forms_dates):
    return {"filings": {"recent": {
        "form": [f for f, _ in forms_dates],
        "filingDate": [d for _, d in forms_dates],
    }}}


def test_edgar_anchor_takes_the_most_recent_anchor_form():
    """MUTATION TARGET (max, not first): the anchor is the LATEST 10-Q/10-K-class
    filing, robust to EDGAR's ordering — an older filing as anchor would misdate
    the window; a NEWER one is impossible to invent from this payload."""
    payload = _submissions([
        ("8-K", "2026-08-20"),          # not an anchor form — ignored
        ("10-Q", "2026-05-06"),         # deliberately BEFORE the newest: first-match
        ("10-K", "2026-02-25"),         #   instead of max would return 05-06
        ("10-Q", "2026-08-05"),
    ])
    assert aer.latest_filing_from_submissions(payload) == date(2026, 8, 5)


def test_edgar_anchor_ignores_non_anchor_forms_entirely():
    """Only filing-class forms anchor the window — an 8-K press release is not a
    financial filing and must never widen the claimed history."""
    assert aer.latest_filing_from_submissions(
        _submissions([("8-K", "2026-08-20"), ("SC 13G", "2026-08-01")])) is None


def test_edgar_anchor_malformed_payload_is_none_never_a_guess():
    assert aer.latest_filing_from_submissions(None) is None
    assert aer.latest_filing_from_submissions({}) is None
    assert aer.latest_filing_from_submissions({"filings": {}}) is None
    assert aer.latest_filing_from_submissions(
        _submissions([("10-Q", "not-a-date")])) is None


# ── quarterly_cadence_facts (v3 — the SEC-sourced cadence facts, pure) ───────────────


def _submissions_full(records):
    """records: list of (form, filingDate, reportDate) — mirrors real EDGAR shape."""
    return {"filings": {"recent": {
        "form": [r[0] for r in records],
        "filingDate": [r[1] for r in records],
        "reportDate": [r[2] for r in records],
    }}}


def test_cadence_facts_pulls_the_two_most_recent_reportdates():
    """MUTATION TARGET: reportDate (period end), NOT filingDate, becomes
    last_reported_quarter_end / prior_reported_quarter_end — the MAX and
    second-MAX reportDate among QUARTERLY_CADENCE_FORMS filings, robust to
    EDGAR's ordering (same defensive shape as latest_filing_from_submissions)."""
    payload = _submissions_full([
        ("10-Q", "2026-05-01", "2026-03-28"),
        ("10-Q", "2026-07-31", "2026-06-27"),   # newest reportDate
        ("8-K", "2026-08-20", "2026-08-20"),    # not a cadence form — ignored
    ])
    facts = aer.quarterly_cadence_facts(payload)
    assert facts["last_reported_quarter_end"] == date(2026, 6, 27)
    assert facts["prior_reported_quarter_end"] == date(2026, 3, 28)


def test_cadence_facts_excludes_foreign_filer_forms():
    """20-F/6-K are in the broader ANCHOR_FORMS (honesty-window) set but NOT
    QUARTERLY_CADENCE_FORMS — annual-only/irregular filing cadences can't support
    the lag/quarter-length arithmetic. A ticker with only these gets no cadence
    facts even though its annual honesty window resolves fine."""
    payload = _submissions_full([("20-F", "2026-04-01", "2025-12-31")])
    facts = aer.quarterly_cadence_facts(payload)
    assert facts == dict(aer._EMPTY_CADENCE_FACTS)


def test_cadence_facts_single_filing_has_no_prior():
    """A recent IPO with only one anchor-form filing on record: last_reported_quarter_end
    resolves ('0q' can still resolve) but prior_reported_quarter_end is None ('+1q'
    cannot — resolve_quarterly_period_ends handles that split)."""
    payload = _submissions_full([("10-Q", "2026-07-31", "2026-06-27")])
    facts = aer.quarterly_cadence_facts(payload)
    assert facts["last_reported_quarter_end"] == date(2026, 6, 27)
    assert facts["prior_reported_quarter_end"] is None


def test_cadence_facts_malformed_payload_is_empty_never_a_guess():
    assert aer.quarterly_cadence_facts(None) == dict(aer._EMPTY_CADENCE_FACTS)
    assert aer.quarterly_cadence_facts({}) == dict(aer._EMPTY_CADENCE_FACTS)
    assert aer.quarterly_cadence_facts({"filings": {}}) == dict(aer._EMPTY_CADENCE_FACTS)


def test_cadence_facts_extracts_fiscal_year_end_from_the_top_level_payload():
    """v4 — THE SINGLE POINT THE WHOLE FINNHUB-LABELING PATH DEPENDS ON, and every
    orchestration test mocks _fetch_quarter_cadence_facts so this real extraction
    never runs under those tests. fiscalYearEnd lives at the TOP LEVEL of the real
    EDGAR submissions payload (probed live 2026-09-03: AAPL "0926", COST "0830"),
    a DIFFERENT level than filings.recent — extracted independently of whether the
    recent-filings parse below it succeeds at all."""
    payload = {"fiscalYearEnd": "0926", **_submissions_full([
        ("10-Q", "2026-07-31", "2026-06-27"),
        ("10-Q", "2026-05-01", "2026-03-28"),
    ])}
    facts = aer.quarterly_cadence_facts(payload)
    assert facts["fiscal_year_end"] == "0926"
    assert facts["last_reported_quarter_end"] == date(2026, 6, 27)


def test_cadence_facts_fiscal_year_end_survives_a_broken_recent_filings_parse():
    """fiscalYearEnd is extracted BEFORE the filings.recent parse is even attempted —
    a malformed/missing filings.recent must not cost this ticker its FYE fact too."""
    facts = aer.quarterly_cadence_facts({"fiscalYearEnd": "0830"})
    assert facts["fiscal_year_end"] == "0830"
    assert facts["last_reported_quarter_end"] is None


def test_cadence_facts_rejects_a_malformed_fiscal_year_end_never_a_guess():
    for bad in ("", "926", 926, None, "not-a-date"):
        facts = aer.quarterly_cadence_facts({"fiscalYearEnd": bad})
        assert facts["fiscal_year_end"] is None, f"{bad!r} must not be accepted as-is"


# ── resolve_quarterly_period_ends (v3 — the relative->absolute date resolver) ────────
# v3.1 (second design review, 2026-09-02): the lag is RELEASE-to-RELEASE (yfinance's
# last actual earnings date minus SEC EDGAR's reportDate), not release-to-FILING — an
# earlier draft mixed those two different event types and, while accidentally close on
# AAPL, was measurably off on real WMT data (see test_release_lag_beats_filing_lag_on_wmt).


def test_resolves_0q_and_plus1q_from_real_aapl_shaped_facts():
    """Real EDGAR/yfinance numbers captured live 2026-09-02 (see the module
    docstring): last reported quarter end 2026-06-27, released 2026-07-30 (33-day
    release lag), prior quarter end 2026-03-28 (91-day quarter length), next
    scheduled earnings date 2026-10-29 — lands on AAPL's real fiscal Sept-end."""
    cadence = {"last_reported_quarter_end": date(2026, 6, 27),
               "prior_reported_quarter_end": date(2026, 3, 28)}
    out = aer.resolve_quarterly_period_ends(date(2026, 10, 29), date(2026, 7, 30), cadence)
    assert out["0q"] == date(2026, 9, 26)
    assert out["+1q"] == date(2026, 12, 26)


def test_naive_three_month_extrapolation_would_pick_the_wrong_month_on_a_445_calendar():
    """THE REASON a fixed 3-calendar-month step was rejected (documented in the module
    docstring): on COST's real EDGAR data, last reported quarter end 2026-05-10 + 3
    calendar months = 2026-08-10, one month early relative to the true fiscal-year-end
    quarter (2025's equivalent landed 2025-08-31). resolve_quarterly_period_ends
    instead anchors on the real next earnings date and lands within the correct month —
    not exact-day precision (a known, documented residual: a Q4/FYE release lag differs
    from a regular quarter's, see the function's own docstring), but never the wrong
    month, which is what the guessed-date failure this test guards against looks like."""
    cadence = {"last_reported_quarter_end": date(2026, 5, 10),
               "prior_reported_quarter_end": date(2026, 2, 15)}
    naive_extrapolation = date(2026, 5, 10).replace(month=8, day=10)  # last_q_end + 3 months
    out = aer.resolve_quarterly_period_ends(date(2026, 9, 24), date(2026, 5, 28), cadence)
    assert out["0q"] != naive_extrapolation, (
        "the naive approach lands a month early on this real 4-4-5 retail calendar")
    assert out["0q"].month == 9, "expected September, within the documented ~1-week residual " \
        "of the true 2026-08-30ish fiscal-year-end — never the wrong month"
    assert out["+1q"] == date(2026, 11, 29)


def test_release_lag_beats_filing_lag_on_real_wmt_data():
    """v3.1's reason for existing: on WMT's real EDGAR/yfinance data, the (rejected)
    filing-lag formula computed 2026-10-22 for the next quarter end — 9 days off the
    true 2026-10-31 pattern (WMT's quarters are calendar-month-aligned). The
    release-lag formula lands within 1 day."""
    cadence = {"last_reported_quarter_end": date(2026, 7, 31),
               "prior_reported_quarter_end": date(2026, 4, 30)}
    out = aer.resolve_quarterly_period_ends(date(2026, 11, 19), date(2026, 8, 20), cadence)
    assert out["0q"] == date(2026, 10, 30)
    assert abs((out["0q"] - date(2026, 10, 31)).days) <= 1


def test_plus1q_needs_a_prior_quarter_but_0q_does_not():
    """A recent IPO (one filing on record): 0q resolves from the lag alone; +1q has
    no quarter-length to add and stays None — skip that ONE period, not the ticker."""
    cadence = {"last_reported_quarter_end": date(2026, 6, 27),
               "prior_reported_quarter_end": None}
    out = aer.resolve_quarterly_period_ends(date(2026, 10, 29), date(2026, 7, 30), cadence)
    assert out["0q"] == date(2026, 9, 26)
    assert out["+1q"] is None


def test_resolve_returns_none_without_next_earnings_date_release_date_or_cadence_facts():
    empty = dict(aer._EMPTY_CADENCE_FACTS)
    assert aer.resolve_quarterly_period_ends(None, date(2026, 7, 30), empty) == \
        {"0q": None, "+1q": None}
    assert aer.resolve_quarterly_period_ends(date(2026, 10, 29), None, empty) == \
        {"0q": None, "+1q": None}
    assert aer.resolve_quarterly_period_ends(date(2026, 10, 29), date(2026, 7, 30), empty) == \
        {"0q": None, "+1q": None}


def test_resolve_rejects_out_of_range_release_lag():
    """MUTATION TARGET: an implausible release lag (>75 days) means mismatched/bad
    inputs, not an unusual filer — reject rather than store an implausible date.
    This bound is also what protects against the "reporting gap" mismatch (see the
    function's docstring): a stale EDGAR anchor inflates the measured lag by
    roughly a quarter-length, comfortably clearing this bound."""
    cadence = {"last_reported_quarter_end": date(2026, 6, 27),
               "prior_reported_quarter_end": date(2026, 3, 28)}
    assert aer.resolve_quarterly_period_ends(
        date(2026, 10, 29), date(2026, 9, 15), cadence)["0q"] is None   # 80-day "lag"


def test_resolve_rejects_the_reporting_gap_mismatch():
    """The concrete gap scenario: yfinance's last actual release already reflects a
    NEWER quarter than EDGAR's stale last_reported_quarter_end (the filing hasn't
    posted yet). The mismatched lag runs about a quarter-length too long and is
    rejected outright — skipped and counted, never mislabeled."""
    cadence = {"last_reported_quarter_end": date(2026, 6, 27),   # EDGAR hasn't caught up yet
               "prior_reported_quarter_end": date(2026, 3, 28)}
    # yfinance already knows about the (newer) Sept-quarter release
    out = aer.resolve_quarterly_period_ends(date(2027, 1, 28), date(2026, 10, 29), cadence)
    assert out["0q"] is None and out["+1q"] is None


def test_resolve_rejects_out_of_range_quarter_length():
    """MUTATION TARGET: an implausible quarter length (<60 or >130 days) skips ONLY
    +1q — 0q is unaffected since it never uses quarter length."""
    cadence = {"last_reported_quarter_end": date(2026, 6, 27),
               "prior_reported_quarter_end": date(2025, 6, 27)}   # ~365-day "quarter"
    out = aer.resolve_quarterly_period_ends(date(2026, 10, 29), date(2026, 7, 30), cadence)
    assert out["0q"] == date(2026, 9, 26)
    assert out["+1q"] is None


def test_resolve_rejects_a_computed_0q_that_precedes_the_last_reported_quarter():
    """MUTATION TARGET: a stale/bad next_earnings_date that would compute 0q at or
    before the last reported quarter end is bad data, not a real forward estimate."""
    cadence = {"last_reported_quarter_end": date(2026, 6, 27),
               "prior_reported_quarter_end": date(2026, 3, 28)}
    assert aer.resolve_quarterly_period_ends(
        date(2026, 7, 1), date(2026, 7, 30), cadence)["0q"] is None


# ── stabilize_period_end (v3.1 — the label-stability fix, mutation target) ───────────


def test_stabilize_reuses_an_existing_date_within_tolerance():
    """THE FRACTURE THIS FIXES: a filing-boundary lag swing (or a refining
    next_earnings_date) computes a slightly different candidate for the SAME
    quarter day to day — reuse the existing recorded date instead of minting a new
    primary key. `recent_dates` is recency-ordered (most-recently-written first)."""
    assert aer.stabilize_period_end(
        date(2026, 12, 24), [date(2026, 12, 25), date(2026, 9, 26)]) == date(2026, 12, 25)


def test_stabilize_leaves_a_genuinely_new_quarter_alone():
    """A candidate far (beyond tolerance) from every recorded date is a genuinely
    NEW quarter, not drift — keep the fresh candidate, don't collapse two real
    quarters into one."""
    assert aer.stabilize_period_end(
        date(2026, 12, 26), [date(2026, 9, 26)]) == date(2026, 12, 26)


def test_stabilize_passes_through_with_no_candidate_or_no_history():
    assert aer.stabilize_period_end(None, [date(2026, 12, 25)]) is None
    assert aer.stabilize_period_end(date(2026, 12, 25), []) == date(2026, 12, 25)


def test_stabilize_prefers_recency_over_raw_distance_when_two_dates_are_in_tolerance():
    """MUTATION TARGET (design review, 2026-09-02): when TWO historical dates both
    sit within tolerance of today's candidate — e.g. a stale early estimate from
    months ago alongside a recently-confirmed one — the MOST RECENTLY WRITTEN one
    wins, even though it is not the numerically closer of the two. `recent_dates`
    is recency-ordered (db.get_recent_quarterly_period_ends: MAX(as_of_date) DESC),
    so `stabilize_period_end` must take the FIRST match, not `min()` by distance —
    reverting to nearest-by-distance would silently resurrect a stale label over
    the series' own most recent, better-informed one."""
    candidate = date(2026, 12, 24)
    recent_dates = [date(2026, 12, 20), date(2026, 12, 26)]   # written-most-recently first
    assert abs((candidate - date(2026, 12, 26)).days) < abs((candidate - date(2026, 12, 20)).days), (
        "the test setup must make the SECOND (older) entry the numerically closer one, "
        "or this test doesn't actually distinguish recency from nearest-by-distance")
    assert aer.stabilize_period_end(candidate, recent_dates) == date(2026, 12, 20)


def test_stabilize_boundary_is_inclusive():
    """MUTATION TARGET: the tolerance boundary (15 days) is inclusive."""
    assert aer.stabilize_period_end(
        date(2026, 12, 25), [date(2026, 12, 10)], tolerance_days=15) == date(2026, 12, 10)
    assert aer.stabilize_period_end(
        date(2026, 12, 25), [date(2026, 12, 9)], tolerance_days=15) == date(2026, 12, 25)


def test_stabilize_skips_an_out_of_tolerance_head_and_matches_further_down_the_list():
    """MUTATION TARGET: the recency scan must actually SCAN, not just check
    recent_dates[0]. The most-recently-written entry (index 0) is for a DIFFERENT
    quarter entirely (89 days away — beyond tolerance); an OLDER entry further down
    the list is the real match for today's candidate and must still be found."""
    candidate = date(2026, 12, 24)
    recent_dates = [date(2026, 9, 26), date(2026, 12, 20)]   # index 0 = most recent write
    assert aer.stabilize_period_end(candidate, recent_dates) == date(2026, 12, 20)


def test_stabilize_leaves_a_candidate_just_outside_tolerance_alone():
    """The gap between _MIN_QUARTER_LENGTH_DAYS (60) and _STABILIZE_TOLERANCE_DAYS
    (15) must not silently swallow a genuinely different (if unusually close)
    quarter: a candidate 20 days from the nearest stored date (5 days past the
    15-day tolerance) is left as the fresh candidate, not collapsed onto it."""
    assert aer.stabilize_period_end(
        date(2026, 12, 24), [date(2026, 12, 4)]) == date(2026, 12, 24)


# ── v4 — fiscal_quarter_end_from_label (Finnhub's quarter+year -> a calendar date) ────
# MEASURED against real EDGAR report dates during design (module docstring's "THE
# BIGGEST WIN"): AAPL (calendar-adjacent FYE) lands EXACTLY on the real reportDate;
# COST (true 4-4-5 retail calendar) is off by 0-20 days across its 4 real quarters.


def test_fiscal_label_lands_exactly_on_aapl_real_report_dates():
    """AAPL fiscalYearEnd '0926' (probed live from SEC EDGAR, 2026-09-03) reproduces
    the SAME 2026-09-26 last_reported_quarter_end already used throughout this suite
    (e.g. _AAPL_CADENCE) — the two labeling methods AGREE exactly for this filer."""
    assert aer.fiscal_quarter_end_from_label(4, 2026, "0926") == date(2026, 9, 26)
    assert aer.fiscal_quarter_end_from_label(3, 2026, "0926") == date(2026, 6, 26)
    assert aer.fiscal_quarter_end_from_label(1, 2026, "0926") == date(2025, 12, 26)


def test_fiscal_label_measured_error_on_a_445_retail_calendar():
    """MUTATION TARGET (the numbers this design accepts, not assumes): COST
    fiscalYearEnd '0830' (probed live from SEC EDGAR, 2026-09-03) against COST's REAL
    reportDates — 2025-11-23 (Q1), 2026-02-15 (Q2), 2026-05-10 (Q3). Worst case ~20
    days (Q3) — see the module docstring for why this is accepted (deterministic,
    Dec-FYE-dominant population, ~90-day quarter spacing) rather than rejected the
    way the yfinance leg's fixed-3-month extrapolation was."""
    assert aer.fiscal_quarter_end_from_label(1, 2026, "0830") == date(2025, 11, 30)
    assert abs((aer.fiscal_quarter_end_from_label(1, 2026, "0830")
                - date(2025, 11, 23)).days) == 7
    assert aer.fiscal_quarter_end_from_label(2, 2026, "0830") == date(2026, 2, 28)
    assert abs((aer.fiscal_quarter_end_from_label(2, 2026, "0830")
                - date(2026, 2, 15)).days) == 13
    assert aer.fiscal_quarter_end_from_label(3, 2026, "0830") == date(2026, 5, 30)
    assert abs((aer.fiscal_quarter_end_from_label(3, 2026, "0830")
                - date(2026, 5, 10)).days) == 20


def test_fiscal_label_rejects_bad_inputs_never_a_guess():
    assert aer.fiscal_quarter_end_from_label(0, 2026, "0926") is None
    assert aer.fiscal_quarter_end_from_label(5, 2026, "0926") is None
    assert aer.fiscal_quarter_end_from_label(4, None, "0926") is None
    assert aer.fiscal_quarter_end_from_label(4, 2026, None) is None
    assert aer.fiscal_quarter_end_from_label(4, 2026, "") is None
    assert aer.fiscal_quarter_end_from_label(4, 2026, "not-a-date") is None
    assert aer.fiscal_quarter_end_from_label(4, 2026, "1332") is None  # month 13, day 32


# ── v4 — finnhub_period_end_from_entry (the self-consistency guards) ─────────────────


def test_finnhub_entry_resolves_when_both_guards_pass():
    """AAPL-shaped: fiscal label -> 2026-09-26; Finnhub's own announced date
    2026-10-29 is 33 days later (within [0,75]); last reported quarter (2026-06-27)
    precedes it — both guards pass."""
    assert aer.finnhub_period_end_from_entry(
        date(2026, 10, 29), 4, 2026, "0926", date(2026, 6, 27)) == date(2026, 9, 26)


def test_finnhub_entry_rejects_a_release_lag_guard_failure():
    """MUTATION TARGET: a wrong fiscal/calendar-year convention runs the announce-
    date-minus-period-end gap off by ~a year — comfortably outside [0,75] — and must
    be rejected, not stored against an unverified label. Using year=2025 here
    (instead of the correct 2026) simulates exactly that class of misread."""
    assert aer.finnhub_period_end_from_entry(
        date(2026, 10, 29), 4, 2025, "0926", date(2026, 6, 27)) is None


def test_finnhub_entry_rejects_a_date_before_the_last_reported_quarter():
    """MUTATION TARGET: a fiscal label that resolves to a quarter EDGAR already has
    on record is stale, not a genuine forward estimate — reject it."""
    assert aer.finnhub_period_end_from_entry(
        date(2026, 7, 1), 3, 2026, "0926", date(2026, 6, 27)) is None


def test_finnhub_entry_missing_inputs_is_none_never_a_guess():
    assert aer.finnhub_period_end_from_entry(None, 4, 2026, "0926", None) is None
    assert aer.finnhub_period_end_from_entry(date(2026, 10, 29), None, None, None, None) is None


# ── v4 — pair_finnhub_periods_to_slots (cross-source corroboration, never required) ──


def test_pairing_matches_within_tolerance_by_slot():
    finnhub_ends = [date(2026, 9, 26), date(2026, 12, 28)]
    reconstructed = {"0q": date(2026, 9, 20), "+1q": date(2026, 12, 20)}
    out = aer.pair_finnhub_periods_to_slots(finnhub_ends, reconstructed)
    assert out == {"0q": 0, "+1q": 1}


def test_pairing_declines_a_slot_beyond_tolerance():
    """No corroboration -> None for that slot; the reconstruction stays the fallback,
    exactly as if Finnhub did not cover this ticker at all."""
    finnhub_ends = [date(2027, 1, 15)]   # ~110 days from the '0q' candidate below
    reconstructed = {"0q": date(2026, 9, 26), "+1q": None}
    out = aer.pair_finnhub_periods_to_slots(finnhub_ends, reconstructed)
    assert out == {"0q": None, "+1q": None}


def test_pairing_never_reuses_the_same_finnhub_index_for_two_slots():
    """MUTATION TARGET: one Finnhub entry can corroborate AT MOST one slot — two
    calendar entries about the SAME real quarter would be a vendor data bug, not a
    genuine double-match. Only one entry is supplied here; the closer slot ('0q')
    wins it and '+1q' is left unmatched rather than reusing index 0."""
    finnhub_ends = [date(2026, 9, 24)]
    reconstructed = {"0q": date(2026, 9, 26), "+1q": date(2026, 9, 30)}
    out = aer.pair_finnhub_periods_to_slots(finnhub_ends, reconstructed)
    assert out == {"0q": 0, "+1q": None}


def test_pairing_missing_reconstructed_candidate_never_matches():
    out = aer.pair_finnhub_periods_to_slots([date(2026, 9, 26)], {"0q": None, "+1q": None})
    assert out == {"0q": None, "+1q": None}


# ── v4 — normalize_finnhub_estimate (raw capture, no analyst count) ──────────────────


def _finnhub_entry(**over):
    base = {"date": date(2026, 10, 7), "quarter": 3, "year": 2026,
            "revenue_estimate": 22765125.0, "eps_estimate": -0.5891}
    base.update(over)
    return base


def test_normalize_finnhub_maps_raw_fields_and_marks_no_analyst_count():
    row = aer.normalize_finnhub_estimate(
        _finnhub_entry(), ticker="NRIX", as_of=AS_OF,
        anchor_filing_date=date(2026, 7, 31), period_end_date=date(2026, 9, 26))
    assert row["ticker"] == "NRIX"
    assert row["period_type"] == "quarter"
    assert row["period_end_date"] == date(2026, 9, 26)
    assert row["revenue_avg"] == 22765125.0 and row["eps_avg"] == -0.5891
    assert row["revenue_high"] is None and row["revenue_low"] is None, (
        "Finnhub's calendar gives no high/low spread")
    assert row["num_analysts_revenue"] is None and row["num_analysts_eps"] is None
    assert row["analyst_count_available"] is False, (
        "THE ONE GAP — this NULL means 'never provided,' not 'we looked and it was low'")
    assert row["fiscal_quarter"] == 3 and row["fiscal_year"] == 2026
    assert row["source"] == "finnhub_calendar"
    assert row["period_label_method"] == aer.LABEL_METHOD_FINNHUB_FISCAL
    assert row["recorder_version"] == aer.RECORDER_VERSION


# ── v4 — estimate_for_scoring: the analyst_count_available short-circuit ─────────────


def test_scoring_rejects_a_row_with_no_analyst_count_available_even_with_other_fields():
    """MUTATION TARGET: analyst_count_available=False must short-circuit to None on
    its own, in code, not merely because num_analysts_revenue also happens to be
    None — a future Finnhub-shaped source that DID carry some other numeric count in
    that field must still be rejected here."""
    row = {"analyst_count_available": False, "num_analysts_revenue": 99,
           "revenue_avg": 1.0}
    assert aer.estimate_for_scoring(row) is None


# ── v4 — compute_estimate_divergences (raw diff, no threshold) ───────────────────────


def _quarter_row(source, ticker="NRIX", period_end=date(2026, 9, 26), as_of=AS_OF,
                  revenue_avg=None, eps_avg=None):
    return {"ticker": ticker, "period_type": "quarter", "period_end_date": period_end,
            "as_of_date": as_of, "source": source,
            "revenue_avg": revenue_avg, "eps_avg": eps_avg}


def test_divergence_fires_only_when_both_sources_share_the_same_period():
    rows = [
        _quarter_row("yfinance", revenue_avg=479_500_000.0, eps_avg=-0.40),
        _quarter_row("finnhub_calendar", revenue_avg=22_765_125.0, eps_avg=-0.5891),
        {**_quarter_row("fmp_stable", period_end=date(2026, 12, 31)),
         "period_type": "annual"},   # a third source/period_type present; ignored
    ]
    out = aer.compute_estimate_divergences(rows)
    assert len(out) == 1
    row = out[0]
    assert row["ticker"] == "NRIX" and row["period_end_date"] == date(2026, 9, 26)
    assert row["yfinance_revenue_avg"] == 479_500_000.0
    assert row["finnhub_revenue_avg"] == 22_765_125.0
    assert row["revenue_diff"] == pytest.approx(22_765_125.0 - 479_500_000.0)
    assert row["eps_diff"] == pytest.approx(-0.5891 - (-0.40))


def test_divergence_does_not_fire_with_only_one_source():
    rows = [_quarter_row("yfinance", revenue_avg=1.0)]
    assert aer.compute_estimate_divergences(rows) == []


def test_divergence_stores_null_diff_when_a_value_is_missing_never_zero():
    """MUTATION TARGET: a missing value on either side must produce a NULL diff, not
    treat the missing side as zero (which would fabricate a huge fake divergence)."""
    rows = [
        _quarter_row("yfinance", revenue_avg=1_000_000.0, eps_avg=None),
        _quarter_row("finnhub_calendar", revenue_avg=None, eps_avg=-0.10),
    ]
    out = aer.compute_estimate_divergences(rows)
    assert len(out) == 1
    assert out[0]["revenue_diff"] is None and out[0]["eps_diff"] is None
    assert out[0]["yfinance_revenue_avg"] == 1_000_000.0
    assert out[0]["finnhub_eps_avg"] == -0.10


def test_divergence_ignores_annual_rows_entirely():
    rows = [
        _quarter_row("fmp_stable", period_end=date(2026, 12, 31)),
        {**_quarter_row("fmp_stable", period_end=date(2026, 12, 31)), "period_type": "annual"},
    ]
    assert aer.compute_estimate_divergences(rows) == []


# ── next_earnings_date_from_yfinance (pure — the earnings_dates frame parse) ─────────


def _earnings_dates_df(rows):
    """rows: list of (date_str, reported_eps_or_None) — mirrors yfinance's real
    tz-aware DatetimeIndex + 'Reported EPS' column shape (probed live 2026-09-02)."""
    idx = pd.DatetimeIndex([pd.Timestamp(d, tz="America/New_York") for d, _ in rows])
    return pd.DataFrame({"Reported EPS": [r for _, r in rows]}, index=idx)


def test_next_earnings_date_finds_the_soonest_unreported_row():
    df = _earnings_dates_df([
        ("2026-10-29", None),        # next — not yet reported
        ("2026-07-30", 2.02),        # already reported
        ("2026-04-30", 2.01),
    ])
    assert aer.next_earnings_date_from_yfinance(df) == date(2026, 10, 29)


def test_next_earnings_date_none_when_everything_reported():
    df = _earnings_dates_df([("2026-07-30", 2.02), ("2026-04-30", 2.01)])
    assert aer.next_earnings_date_from_yfinance(df) is None


def test_next_earnings_date_malformed_frame_is_none_never_a_guess():
    assert aer.next_earnings_date_from_yfinance(None) is None
    assert aer.next_earnings_date_from_yfinance(pd.DataFrame()) is None
    assert aer.next_earnings_date_from_yfinance(pd.DataFrame({"Other": [1]})) is None


# ── last_actual_earnings_date_from_yfinance (pure — the release-lag's release half) ──


def test_last_actual_earnings_date_finds_the_most_recent_reported_row():
    df = _earnings_dates_df([
        ("2026-10-29", None),
        ("2026-07-30", 2.02),        # most recent ACTUAL release
        ("2026-04-30", 2.01),
    ])
    assert aer.last_actual_earnings_date_from_yfinance(df) == date(2026, 7, 30)


def test_last_actual_earnings_date_none_when_nothing_reported_yet():
    df = _earnings_dates_df([("2026-10-29", None)])
    assert aer.last_actual_earnings_date_from_yfinance(df) is None


def test_last_actual_earnings_date_malformed_frame_is_none_never_a_guess():
    assert aer.last_actual_earnings_date_from_yfinance(None) is None
    assert aer.last_actual_earnings_date_from_yfinance(pd.DataFrame()) is None
    assert aer.last_actual_earnings_date_from_yfinance(pd.DataFrame({"Other": [1]})) is None


# ── normalize_yfinance_quarterly_estimate (raw capture, never derived) ───────────────


def _yf_row(**over):
    base = {"avg": 1.97656, "low": 1.93, "high": 2.07, "numberOfAnalysts": 28,
            "yearAgoEps": 1.85, "growth": 0.0684, "currency": "USD"}
    base.update(over)
    return base


def test_normalize_yfinance_quarterly_maps_raw_fields_and_stamps_source():
    row = aer.normalize_yfinance_quarterly_estimate(
        ticker="AAPL", yf_period="0q", as_of=AS_OF,
        anchor_filing_date=date(2026, 7, 31), period_end_date=date(2026, 9, 25),
        revenue_row={"avg": 113563145910.0, "high": 117219700000.0,
                     "low": 112137000000.0, "numberOfAnalysts": 28},
        earnings_row=_yf_row(),
    )
    assert row["ticker"] == "AAPL"
    assert row["period_type"] == "quarter"
    assert row["period_end_date"] == date(2026, 9, 25)
    assert row["as_of_date"] == AS_OF
    assert row["valid_from_date"] == date(2026, 7, 31)
    assert row["revenue_avg"] == 113563145910.0
    assert row["eps_high"] == 2.07
    assert row["num_analysts_revenue"] == 28 and row["num_analysts_eps"] == 28
    assert row["source"] == "yfinance", "must be distinguishable from the annual (fmp_stable) leg"
    assert row["recorder_version"] == aer.RECORDER_VERSION


def test_normalize_yfinance_quarterly_nan_becomes_null_never_zero():
    """MUTATION TARGET: yfinance/pandas represents a missing value as float('nan'),
    NOT None — unlike FMP's explicit JSON null. A naive _f(nan) would store NaN into
    a DOUBLE PRECISION column; _nan_to_none must intercept it first."""
    row = aer.normalize_yfinance_quarterly_estimate(
        ticker="X", yf_period="0q", as_of=AS_OF, anchor_filing_date=None,
        period_end_date=date(2026, 9, 30),
        revenue_row={"avg": float("nan"), "high": 1.0, "low": 1.0,
                     "numberOfAnalysts": float("nan")},
        earnings_row=None,
    )
    assert row["revenue_avg"] is None          # never NaN — NaN != NaN, None == None
    assert row["num_analysts_revenue"] is None
    assert row["eps_avg"] is None and row["eps_high"] is None   # earnings_row=None -> all NULL


def test_normalize_yfinance_quarterly_without_period_end_returns_none():
    """MUTATION TARGET — THE HONESTY CONSTRAINT: never store a quarterly row against
    an unresolved (or guessed) period end date."""
    assert aer.normalize_yfinance_quarterly_estimate(
        ticker="X", yf_period="0q", as_of=AS_OF, anchor_filing_date=None,
        period_end_date=None, revenue_row=_yf_row(), earnings_row=_yf_row()) is None


def test_normalize_yfinance_quarterly_with_no_data_returns_none():
    assert aer.normalize_yfinance_quarterly_estimate(
        ticker="X", yf_period="0q", as_of=AS_OF, anchor_filing_date=None,
        period_end_date=date(2026, 9, 30), revenue_row=None, earnings_row=None) is None


# ── _yf_period_row (pure — the revenue_estimate/earnings_estimate frame parse) ───────


def _estimate_df(rows: dict):
    """rows: {"0q": {...}, "+1q": {...}} -> a yfinance-shaped DataFrame indexed by period."""
    return pd.DataFrame(rows).T


def test_yf_period_row_extracts_the_requested_period():
    df = _estimate_df({"0q": _yf_row(avg=1.97656), "+1q": _yf_row(avg=2.89268)})
    row = aer._yf_period_row(df, "0q")
    assert row["avg"] == 1.97656


def test_yf_period_row_missing_period_or_frame_is_none():
    assert aer._yf_period_row(None, "0q") is None
    df = _estimate_df({"0q": _yf_row()})
    assert aer._yf_period_row(df, "+1q") is None


# ── estimate_for_scoring (the sketch's n<3 -> None rule — mutation target) ───────────


def test_thin_coverage_scores_none_and_threshold_is_tunable():
    """MUTATION TARGET (the sketch's contract): n_analysts < 3 -> None; the count is
    stored so the threshold re-tunes without re-fetching — proven by the override."""
    assert aer.estimate_for_scoring({"num_analysts_revenue": 2}) is None
    assert aer.estimate_for_scoring({"num_analysts_revenue": None}) is None
    row = {"num_analysts_revenue": 3, "revenue_avg": 1.0}
    assert aer.estimate_for_scoring(row) is row
    assert aer.estimate_for_scoring(row, min_analysts=5) is None
    assert aer.estimate_for_scoring({"num_analysts_revenue": 2}, min_analysts=2) is not None


# ── orchestration (db + fetch monkeypatched; never raises; per-ticker isolation) ─────


def _wire(monkeypatch, *, anchors=None,
          anchor_fail_tickers=(), quarter_cadence=None, yf_data=None,
          yf_fail_tickers=(), recent_period_ends=None,
          finnhub_data=None, finnhub_fail_tickers=(), upsert_fail_tickers=()):
    written = []
    audits = []
    divergences = []

    async def fake_filing(ticker, as_of):
        if ticker in anchor_fail_tickers:
            raise RuntimeError("EDGAR down")
        return (anchors or {}).get(ticker)

    async def fake_quarter_cadence(ticker, as_of):
        # NOTE: in production this shares the SAME EDGAR fetch as fake_filing (both
        # read _get_edgar_facts), so an anchor_fail_tickers entry never reaches here —
        # snapshot_ticker's try/except skips this call the moment fake_filing raises.
        # Under test the two are wired independently for clarity; default is "no
        # cadence facts" (an ETF/non-filer, or a ticker the test didn't configure).
        return dict((quarter_cadence or {}).get(ticker, aer._EMPTY_CADENCE_FACTS))

    async def fake_yf_quarterly(ticker):
        if ticker in yf_fail_tickers:
            raise RuntimeError("yfinance boom")
        return (yf_data or {}).get(ticker)  # default None -> quarter_yf_unavailable

    async def fake_finnhub_calendar(ticker, as_of):
        if ticker in finnhub_fail_tickers:
            raise RuntimeError("finnhub boom")
        return (finnhub_data or {}).get(ticker)  # default None -> quarter_finnhub_unavailable

    async def fake_recent_period_ends(ticker, since):
        return list((recent_period_ends or {}).get(ticker, []))

    async def fake_upsert(rows):
        if rows and rows[0]["ticker"] in upsert_fail_tickers:
            raise RuntimeError("db boom")   # the only per-ticker raise path left
        written.extend(rows)
        return len(rows)

    async def fake_upsert_divergence(rows):
        divergences.extend(rows)
        return len(rows)

    async def fake_audit(event_type, summary, detail=""):
        audits.append((event_type, summary))

    monkeypatch.setattr(aer, "_fetch_last_filing_date", fake_filing)
    monkeypatch.setattr(aer, "_fetch_quarter_cadence_facts", fake_quarter_cadence)
    monkeypatch.setattr(aer, "_fetch_yfinance_quarterly", fake_yf_quarterly)
    monkeypatch.setattr(aer, "_fetch_finnhub_calendar", fake_finnhub_calendar)
    monkeypatch.setattr(aer, "get_recent_quarterly_period_ends", fake_recent_period_ends)
    monkeypatch.setattr(aer, "upsert_analyst_estimates", fake_upsert)
    monkeypatch.setattr(aer, "upsert_analyst_estimates_divergence", fake_upsert_divergence)
    monkeypatch.setattr(aer, "log_audit_event", fake_audit)
    monkeypatch.setattr(aer, "YFINANCE_PACE_SECONDS", 0)
    monkeypatch.setattr(aer, "FINNHUB_PACE_SECONDS", 0)
    return written, audits, divergences


@pytest.mark.asyncio
async def test_snapshot_writes_rows_with_the_read_date_stamped(monkeypatch):
    written, audits, _div = _wire(
        monkeypatch,
        anchors={"MRNA": date(2026, 7, 31)},
        quarter_cadence={"MRNA": _AAPL_CADENCE},
        yf_data={"MRNA": _yf_data_for("MRNA")},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["MRNA"])
    assert out["rows_written"] == 2 and out["errors"] == 0   # '0q' + '+1q'
    assert {r["period_type"] for r in written} == {"quarter"}
    assert {r["source"] for r in written} == {"yfinance"}
    assert all(r["as_of_date"] == AS_OF for r in written)
    assert all(r["valid_from_date"] == date(2026, 7, 31) for r in written)
    assert any(e == "analyst_estimates_snapshot" for e, _ in audits)


@pytest.mark.asyncio
async def test_one_bad_ticker_never_kills_the_run(monkeypatch):
    """Per-ticker isolation. With the FMP leg gone the only raise path left in a ticker is
    the DB write; one failing must not stop the next ticker."""
    written, audits, _div = _wire(
        monkeypatch,
        anchors={"GOOD": date(2026, 8, 7), "BAD": date(2026, 8, 7)},
        quarter_cadence={"GOOD": _AAPL_CADENCE, "BAD": _AAPL_CADENCE},
        yf_data={"GOOD": _yf_data_for("GOOD"), "BAD": _yf_data_for("BAD")},
        upsert_fail_tickers={"BAD"},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["BAD", "GOOD"])
    assert out["errors"] == 1
    assert out["tickers_written"] == 1
    assert {r["ticker"] for r in written} == {"GOOD"}
    assert any(e == "analyst_estimates_error" for e, _ in audits)


@pytest.mark.asyncio
async def test_true_non_filer_counts_no_anchor_and_claims_zero_history(monkeypatch):
    """An ETF/non-filer (anchor resolves to None without error) is the BY-DESIGN
    zero-window case: counted as no_anchor, never as an error — and the rows it DOES
    record claim ZERO history (valid_from == as_of; the lookahead guard)."""
    written, _, _div = _wire(
        monkeypatch,
        quarter_cadence={"SPYX": _AAPL_CADENCE},
        yf_data={"SPYX": _yf_data_for("SPYX")},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["SPYX"])
    assert out["no_anchor"] == 1 and out["anchor_errors"] == 0 and out["errors"] == 0
    assert out["rows_written"] == 2
    assert all(r["valid_from_date"] == AS_OF for r in written)
    assert all(r["anchor_filing_date"] is None for r in written)


def test_the_pace_is_the_cadence_the_fmp_sleeps_used_to_impose():
    """Removing the FMP leg also removed its two 12s sleeps per ticker — the only thing that
    ever spaced the yfinance scrapes (the old YFINANCE_PACE_SECONDS=1.0 was declared and never
    awaited). 24s keeps every vendor's request pattern exactly as the 09-04..10-16 runs had
    it. Lowering it is a deliberate, MEASURED decision: change this number and this test
    together, with the Yahoo tolerance in the commit."""
    assert aer.YFINANCE_PACE_SECONDS == 24.0


@pytest.mark.asyncio
async def test_tickers_are_paced_between_each_other_not_after_the_last(monkeypatch):
    """MUTATION TARGET: dropping the pause (a 25x speed-up of every scrape), or sleeping
    after the last ticker (wall time for nothing)."""
    _wire(monkeypatch,
          quarter_cadence={t: _AAPL_CADENCE for t in "ABC"},
          yf_data={t: _yf_data_for(t) for t in "ABC"})
    monkeypatch.setattr(aer, "YFINANCE_PACE_SECONDS", 7.5)
    sleeps = []

    async def fake_sleep(seconds, *a, **k):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["A", "B", "C"])
    assert sleeps == [7.5, 7.5]
    sleeps.clear()
    await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["A"])
    assert sleeps == [], "one ticker has nothing to be paced against"


@pytest.mark.asyncio
async def test_the_job_never_calls_fmp_and_cannot_write_an_fmp_shaped_error_row(monkeypatch):
    """MUTATION TARGET: putting the FMP leg (or any FMP call) back. `_fmp_get` is the only
    emitter of an `api_failure_fmp` row, and the old leg also wrote
    `analyst_estimates_plan_change` every night; neither may come from this job any more.
    Exercises every branch a ticker can take (healthy, yfinance empty, EDGAR down) so a
    call hiding in a failure path is caught too."""
    from agents.market_intelligence import collector, llm_health
    fmp_calls, api_alerts = [], []

    async def spy_fmp_get(path, params=None):
        fmp_calls.append((path, params))
        raise RuntimeError("the estimates job must not call FMP")

    async def spy_alert(provider, exc, **kw):
        api_alerts.append(provider)

    monkeypatch.setattr(collector, "_fmp_get", spy_fmp_get)
    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", spy_alert)
    monkeypatch.setattr(llm_health, "alert_api_failure", spy_alert)
    written, audits, _div = _wire(
        monkeypatch,
        anchors={"GOOD": date(2026, 7, 31), "NOYF": date(2026, 7, 31)},
        anchor_fail_tickers={"EDGARDOWN"},
        quarter_cadence={"GOOD": _AAPL_CADENCE, "NOYF": _AAPL_CADENCE},
        yf_data={"GOOD": _yf_data_for("GOOD")},          # NOYF -> None (unavailable)
    )
    out = await aer.run_analyst_estimates_snapshot(
        AS_OF, tickers=["GOOD", "NOYF", "EDGARDOWN"])

    assert fmp_calls == [] and api_alerts == []
    event_types = {e for e, _ in audits}
    assert "analyst_estimates_plan_change" not in event_types
    assert not any(e.startswith("api_failure") for e in event_types)
    assert out["rows_written"] == 2, "yfinance rows are still written"
    assert "annual_unavailable" not in out, "the FMP-402 counter is gone with its leg"
    assert all(r["source"] == "yfinance" and r["period_type"] == "quarter" for r in written)
    for gone in ("_fetch_estimates", "normalize_fmp_estimate", "_is_payment_required",
                 "FMP_PACE_SECONDS", "ESTIMATES_SOURCE", "MAX_PERIODS_PER_CALL",
                 "LABEL_METHOD_VENDOR_REPORTED"):
        assert not hasattr(aer, gone), f"{gone} is a dead remnant of the removed FMP leg"


@pytest.mark.asyncio
async def test_a_run_where_yfinance_wrote_nothing_says_so_once_and_loudly(monkeypatch):
    """MUTATION TARGET: the clock stopping silently. With FMP gone, yfinance returns None on
    every failure BY CONTRACT, so per ticker "Yahoo is down" and "an ETF has no estimates" look
    the same. A run-level zero is not ambiguous: ONE `analyst_estimates_error` row, naming the
    counts, and no per-ticker spam. errors stays 0 (it counts raising tickers, not this)."""
    written, audits, _div = _wire(
        monkeypatch,
        anchors={t: date(2026, 7, 31) for t in "ABC"},
        quarter_cadence={t: _AAPL_CADENCE for t in "ABC"},
        yf_data={},                                   # yfinance returns None for all three
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["A", "B", "C"])
    assert written == [] and out["rows_written"] == 0 and out["errors"] == 0
    assert out["quarter_yf_unavailable"] == 3
    errs = [m for e, m in audits if e == "analyst_estimates_error"]
    assert len(errs) == 1, f"one run-level row, not one per ticker: {errs}"
    assert "yfinance wrote 0 quarterly rows for 3 ticker(s)" in errs[0]
    assert "3 unavailable" in errs[0]
    assert any(e == "analyst_estimates_snapshot" for e, _ in audits), "the summary row too"


@pytest.mark.asyncio
async def test_a_healthy_or_partly_covered_run_writes_no_error_row(monkeypatch):
    """The other half: an ETF with no estimates beside a name that has them is NORMAL
    (quarter_yf_unavailable has a nonzero nightly baseline) and must not page the audit log;
    nor does an empty population (nothing to record is not a failure)."""
    _, audits, _div = _wire(
        monkeypatch,
        anchors={"GOOD": date(2026, 7, 31), "ETF": date(2026, 7, 31)},
        quarter_cadence={"GOOD": _AAPL_CADENCE, "ETF": _AAPL_CADENCE},
        yf_data={"GOOD": _yf_data_for("GOOD")},       # ETF -> None
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["GOOD", "ETF"])
    assert out["quarter_yf_rows_written"] == 2 and out["quarter_yf_unavailable"] == 1
    assert not any(e == "analyst_estimates_error" for e, _ in audits)

    audits.clear()
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=[])
    assert out["population"] == 0
    assert not any(e == "analyst_estimates_error" for e, _ in audits)


# ── quarterly leg orchestration (v3, yfinance) ────────────────────────────────────────


def _yf_data_for(ticker, next_earnings_date=date(2026, 10, 29),
                  last_actual_release_date=date(2026, 7, 30)):
    """A ready-to-store yfinance quarterly payload: real AAPL-shaped numbers, both
    '0q' and '+1q' present with revenue + earnings rows."""
    return {
        "next_earnings_date": next_earnings_date,
        "last_actual_release_date": last_actual_release_date,
        "periods": {
            "0q": {"revenue": {"avg": 113563145910.0, "high": 117219700000.0,
                                "low": 112137000000.0, "numberOfAnalysts": 28},
                   "earnings": {"avg": 1.97656, "high": 2.07, "low": 1.93,
                                "numberOfAnalysts": 28}},
            "+1q": {"revenue": {"avg": 153735499960.0, "high": 160000000000.0,
                                 "low": 132850061129.0, "numberOfAnalysts": 22},
                    "earnings": {"avg": 2.89268, "high": 3.42, "low": 2.51,
                                 "numberOfAnalysts": 22}},
        },
    }


_AAPL_CADENCE = {"last_reported_quarter_end": date(2026, 6, 27),
                  "prior_reported_quarter_end": date(2026, 3, 28)}


@pytest.mark.asyncio
async def test_yfinance_leg_writes_both_quarters_and_nothing_else(monkeypatch):
    """Happy path: both quarterly periods ('0q','+1q') land as source=yfinance quarter rows,
    and a healthy run writes no error row — there is no other source of estimate rows in
    this job any more (Finnhub is wired to None here)."""
    written, audits, _div = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": _AAPL_CADENCE},
        yf_data={"AAPL": _yf_data_for("AAPL")},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    assert out["errors"] == 0
    assert out["rows_written"] == 2   # '0q','+1q'
    assert out["quarter_yf_rows_written"] == 2
    assert out["quarter_yf_unavailable"] == 0 and out["quarter_yf_no_cadence"] == 0
    assert len(written) == 2
    assert all(r["period_type"] == "quarter" and r["source"] == "yfinance" for r in written)
    assert {r["period_end_date"] for r in written} == {date(2026, 9, 26), date(2026, 12, 26)}
    assert all(r["num_analysts_revenue"] is not None for r in written), (
        "numberOfAnalysts must be preserved, not dropped — the n<3 rule reads it later")
    assert not any(e == "analyst_estimates_error" for e, _ in audits)


@pytest.mark.asyncio
async def test_yfinance_failure_is_counted_and_gets_its_own_error_row(monkeypatch):
    """A yfinance outage writes no estimate rows (it IS the estimate source now), is counted
    (quarter_yf_unavailable), never raises — and writes its own `analyst_estimates_error`
    row, so the clock cannot stop silently."""
    written, audits, _div = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": _AAPL_CADENCE},
        yf_fail_tickers={"AAPL"},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    assert out["errors"] == 0
    assert out["rows_written"] == 0 and out["tickers_written"] == 0 and written == []
    assert out["quarter_yf_rows_written"] == 0
    assert out["quarter_yf_unavailable"] == 1
    assert any(e == "analyst_estimates_error" and "yfinance wrote 0 quarterly rows" in m
               for e, m in audits)


@pytest.mark.asyncio
async def test_yfinance_empty_frame_counts_as_unavailable_not_an_error(monkeypatch):
    """yfinance returning nothing usable (empty/short frame, no periods) is the SAME
    degrade as a hard failure from the run's point of view — counted, not an error."""
    written, _, _div = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": _AAPL_CADENCE},
        yf_data={"AAPL": None},   # _fetch_yfinance_quarterly's own "nothing usable" return
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    assert out["errors"] == 0
    assert out["quarter_yf_unavailable"] == 1 and out["quarter_yf_no_cadence"] == 0
    assert written == []


@pytest.mark.asyncio
async def test_no_cadence_anchor_skips_quarterly_rows_and_counts_it_not_an_error(monkeypatch):
    """yfinance HAD estimate data, but no SEC cadence facts were resolvable (ETF-like
    ticker, or QUARTERLY_CADENCE_FORMS never matched) — never store against a guessed
    date: skip both periods and count it distinctly from a yfinance outage."""
    written, audits, _div = _wire(
        monkeypatch,
        anchors={"SPYX": date(2026, 7, 31)},
        # quarter_cadence omitted -> defaults to _EMPTY_CADENCE_FACTS for SPYX
        yf_data={"SPYX": _yf_data_for("SPYX")},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["SPYX"])
    assert out["errors"] == 0
    assert out["quarter_yf_no_cadence"] == 1 and out["quarter_yf_unavailable"] == 0
    assert out["quarter_yf_rows_written"] == 0
    assert written == []
    assert any(e == "analyst_estimates_error" and "1 no-cadence-anchor" in m
               for e, m in audits)


@pytest.mark.asyncio
async def test_anchor_outage_is_counted_never_an_abort_and_skips_the_quarterly_leg(monkeypatch):
    """MUTATION TARGET — THE 2026-09-01 FIRST-RUN BUG (0 rows, 99 errors). An anchor fetch
    failing must NOT raise out of the ticker: it is counted (anchor_errors, not errors) and
    the run carries on. An EDGAR outage kills _fetch_last_filing_date, and snapshot_ticker's
    try/except means _fetch_quarter_cadence_facts is never even called for that ticker — one
    outage degrades BOTH the honesty window and the cadence facts together, exactly as the
    shared _get_edgar_facts cache implies. (The FMP annual row used to be recorded anyway,
    with a zero window; with that leg gone an EDGAR outage means no row for the night — and
    the run-level error row says so.)"""
    written, audits, _div = _wire(
        monkeypatch,
        anchor_fail_tickers={"MRNA"},
        quarter_cadence={"MRNA": _AAPL_CADENCE},   # would resolve fine IF it were reached
        yf_data={"MRNA": _yf_data_for("MRNA")},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["MRNA"])
    assert out["errors"] == 0 and out["anchor_errors"] == 1 and out["no_anchor"] == 0
    assert out["quarter_yf_no_cadence"] == 1
    assert out["quarter_yf_rows_written"] == 0
    assert written == []
    assert any(e == "analyst_estimates_error" and "1 EDGAR anchor-error" in m
               for e, m in audits)


@pytest.mark.asyncio
async def test_label_stability_across_a_filing_boundary_reuses_the_recorded_date(monkeypatch):
    """THE LABEL-FRACTURE THIS GUARDS AGAINST (caught in design review, not by the
    first draft of this test suite): resolve_quarterly_period_ends' inputs are live
    and can shift day to day (a refining next_earnings_date, a new SEC filing
    advancing the cadence anchor). Without stabilize_period_end, the SAME fiscal
    quarter would mint a DIFFERENT period_end_date — a different primary key — on
    two different days, fracturing the revision series
    get_analyst_estimates_asof's DISTINCT ON (period_type, period_end_date, source) reads.

    This simulates exactly that: day 1 resolves the Dec-quarter as '+1q' from the
    Jun27 anchor; day 40 (after the Sep-quarter's 10-K has posted) resolves the SAME
    Dec-quarter as '0q' from the ADVANCED Sep26 anchor — a genuinely different
    cadence-fact input. `recent_period_ends` supplies day 1's stored date, and
    stabilize_period_end must make day 40 reuse it rather than storing a second,
    slightly different date for the same quarter."""
    day1_cadence = {"last_reported_quarter_end": date(2026, 6, 27),
                     "prior_reported_quarter_end": date(2026, 3, 28)}
    written_day1, _, _div1 = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": day1_cadence},
        yf_data={"AAPL": _yf_data_for("AAPL", next_earnings_date=date(2026, 10, 29),
                                       last_actual_release_date=date(2026, 7, 30))},
        recent_period_ends={"AAPL": []},   # nothing recorded yet
    )
    out1 = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    dec_row_day1 = next(r for r in written_day1
                        if r["period_type"] == "quarter" and r["period_end_date"].month == 12)
    stored_dec_date = dec_row_day1["period_end_date"]
    assert stored_dec_date == date(2026, 12, 26)

    # Day 40: the Sep-quarter's 10-K has now posted (advancing the cadence anchor) AND
    # yfinance's own next_earnings_date estimate has drifted 2 days — the SAME Dec
    # quarter is now yfinance's '0q', resolved from GENUINELY DIFFERENT inputs. Proven
    # below: the FRESH (unstabilized) computation actually lands on a different day.
    day40_cadence = {"last_reported_quarter_end": date(2026, 9, 26),
                      "prior_reported_quarter_end": date(2026, 6, 27)}
    day40_next_earnings = date(2027, 1, 30)
    fresh_day40 = aer.resolve_quarterly_period_ends(
        day40_next_earnings, date(2026, 10, 29), day40_cadence)
    assert fresh_day40["0q"] != stored_dec_date, (
        "the test must exercise a genuine input drift — if the fresh computation "
        "already agreed with day 1, stabilize_period_end wouldn't be tested at all")
    assert fresh_day40["0q"] == date(2026, 12, 28)

    day40 = date(2026, 10, 12)
    written_day40, _, _div40 = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 10, 31)},
        quarter_cadence={"AAPL": day40_cadence},
        yf_data={"AAPL": _yf_data_for("AAPL", next_earnings_date=day40_next_earnings,
                                       last_actual_release_date=date(2026, 10, 29))},
        recent_period_ends={"AAPL": [stored_dec_date]},   # day 1's row is now history
    )
    out40 = await aer.run_analyst_estimates_snapshot(day40, tickers=["AAPL"])
    dec_row_day40 = next(r for r in written_day40
                         if r["period_type"] == "quarter" and r["period_end_date"].month == 12)
    assert dec_row_day40["period_end_date"] == stored_dec_date, (
        "the SAME fiscal quarter must keep the SAME period_end_date across the filing "
        "boundary, or the revision series fractures into two 'different' periods")
    # The OTHER half of the same fix: day 40's '+1q' (the Mar quarter) is a genuinely
    # DIFFERENT, NEW quarter (~93 days from the Dec quarter's stored date) and must NOT
    # be collapsed onto it just because Dec26 is the only entry in history.
    mar_row_day40 = next(r for r in written_day40
                         if r["period_type"] == "quarter" and r["period_end_date"].month == 3)
    assert mar_row_day40["period_end_date"] == date(2027, 3, 29), (
        "a genuinely new quarter must keep its own fresh date, not get pulled onto "
        "the unrelated Dec-quarter's stored date")
    assert out1["errors"] == 0 and out40["errors"] == 0


# ── v4 — Finnhub leg orchestration (the second estimates source) ─────────────────────

_AAPL_CADENCE_WITH_FYE = {**_AAPL_CADENCE, "fiscal_year_end": "0926"}


def _finnhub_entries_for_aapl():
    """Two Finnhub calendar entries that CORROBORATE both of _yf_data_for("AAPL")'s
    resolved slots exactly (fiscal_quarter_end_from_label(4, 2026, "0926") ==
    2026-09-26 == resolved['0q']; fiscal_quarter_end_from_label(1, 2027, "0926") ==
    2026-12-26 == resolved['+1q']) — both verified by
    test_fiscal_label_lands_exactly_on_aapl_real_report_dates and
    test_resolves_0q_and_plus1q_from_real_aapl_shaped_facts independently."""
    return [
        {"date": date(2026, 10, 29), "quarter": 4, "year": 2026,
         "revenue_estimate": 100_000_000_000.0, "eps_estimate": 2.00},
        {"date": date(2027, 1, 28), "quarter": 1, "year": 2027,
         "revenue_estimate": 130_000_000_000.0, "eps_estimate": 2.50},
    ]


@pytest.mark.asyncio
async def test_finnhub_corroboration_overrides_the_yfinance_label_and_writes_divergence(
        monkeypatch):
    """Happy path — the whole point of v4: a Finnhub calendar entry that CORROBORATES
    a yfinance slot (a) overrides that row's period_end_date with the fiscal-label
    date, tagging fiscal_quarter/fiscal_year and flipping period_label_method to
    LABEL_METHOD_FINNHUB_FISCAL, (b) is ALSO stored as its own row
    (source='finnhub_calendar'), and (c) produces a divergence row comparing both
    sources' raw values for the same period."""
    written, _, divergences = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": _AAPL_CADENCE_WITH_FYE},
        yf_data={"AAPL": _yf_data_for("AAPL")},
        finnhub_data={"AAPL": _finnhub_entries_for_aapl()},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    assert out["errors"] == 0
    # 2 quarterly (yfinance, now finnhub-labeled) + 2 finnhub_calendar
    assert out["rows_written"] == 4
    assert out["quarter_finnhub_rows_written"] == 2
    assert out["quarter_finnhub_unavailable"] == 0 and out["quarter_finnhub_no_cadence"] == 0
    assert out["divergence_rows_written"] == 2

    yf_rows = [r for r in written if r["source"] == "yfinance"]
    fh_rows = [r for r in written if r["source"] == "finnhub_calendar"]
    assert len(yf_rows) == 2 and len(fh_rows) == 2
    assert {r["period_end_date"] for r in yf_rows} == {date(2026, 9, 26), date(2026, 12, 26)}
    assert {r["period_end_date"] for r in fh_rows} == {date(2026, 9, 26), date(2026, 12, 26)}, (
        "the corroborated finnhub row and the overridden yfinance row must share the "
        "IDENTICAL period_end_date — that identity is what makes the divergence join work")
    assert all(r["period_label_method"] == aer.LABEL_METHOD_FINNHUB_FISCAL for r in yf_rows)
    q4_yf = next(r for r in yf_rows if r["period_end_date"] == date(2026, 9, 26))
    assert q4_yf["fiscal_quarter"] == 4 and q4_yf["fiscal_year"] == 2026
    assert all(r["analyst_count_available"] is False for r in fh_rows)
    assert all(r["num_analysts_revenue"] is None for r in fh_rows)

    assert len(divergences) == 2
    div_q4 = next(d for d in divergences if d["period_end_date"] == date(2026, 9, 26))
    assert div_q4["finnhub_revenue_avg"] == 100_000_000_000.0
    assert div_q4["yfinance_revenue_avg"] == q4_yf["revenue_avg"]
    assert div_q4["revenue_diff"] == pytest.approx(
        100_000_000_000.0 - q4_yf["revenue_avg"])


@pytest.mark.asyncio
async def test_finnhub_override_realigns_to_an_already_established_date(monkeypatch):
    """MUTATION TARGET (advisor-caught, 2026-09-03) — THE FRACTURE THIS GUARDS AGAINST:
    an EARLIER run (yfinance-only, before Finnhub covered this ticker) already
    recorded 2026-09-24 for this quarter. TONIGHT Finnhub corroborates the SAME slot
    with its own fiscal-label date (2026-09-26, 2 days off, within
    _STABILIZE_TOLERANCE_DAYS) — stabilize_period_end correctly REUSES the
    established 2026-09-24 rather than minting a new key. Without the realignment
    fix, the Finnhub row would sit at its own fresh 2026-09-26 while the yfinance
    row reused 2026-09-24: two different period_end_date keys for the SAME real
    quarter, `period_label_method` would FALSELY claim 'finnhub_fiscal_label' for a
    date Finnhub never actually produced, and compute_estimate_divergences would
    never see them as the same period — silently, forever. Both sources must land
    on 2026-09-24."""
    established_date = date(2026, 9, 24)
    written, _, divergences = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": _AAPL_CADENCE_WITH_FYE},
        yf_data={"AAPL": _yf_data_for("AAPL")},
        finnhub_data={"AAPL": _finnhub_entries_for_aapl()},
        recent_period_ends={"AAPL": [established_date]},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    assert out["errors"] == 0

    yf_rows = [r for r in written if r["source"] == "yfinance"]
    fh_rows = [r for r in written if r["source"] == "finnhub_calendar"]
    yf_q4 = next(r for r in yf_rows if r["fiscal_quarter"] == 4)
    fh_q4 = next(r for r in fh_rows if r["fiscal_quarter"] == 4)
    assert yf_q4["period_end_date"] == established_date, (
        "stabilize_period_end must win the STORED KEY when history already exists")
    assert fh_q4["period_end_date"] == established_date, (
        "the Finnhub row must be REALIGNED to the established key, not left at its "
        "own fresh fiscal-label date, or the two sources silently stop being joinable")
    assert yf_q4["period_label_method"] == aer.LABEL_METHOD_FINNHUB_FISCAL, (
        "Finnhub still identified WHICH quarter this is, even though the established "
        "date (not Finnhub's freshly-computed one) is what gets stored")

    div_q4 = next(d for d in divergences if d["period_end_date"] == established_date)
    assert div_q4["finnhub_revenue_avg"] == fh_q4["revenue_avg"]
    assert div_q4["yfinance_revenue_avg"] == yf_q4["revenue_avg"]


@pytest.mark.asyncio
async def test_finnhub_row_is_stored_even_when_yfinance_is_unavailable(monkeypatch):
    """THE RESILIENCE PROPERTY (module docstring's "PREFER, NEVER REQUIRE"): a
    Finnhub calendar row does NOT depend on yfinance succeeding at all — an
    independent second source, not a mere corroboration signal. It is NOT a substitute for
    yfinance, though: with yfinance down the run still says so (the Finnhub rows carry no
    analyst count, so nothing the n<3 rule can admit was recorded)."""
    written, audits, divergences = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": _AAPL_CADENCE_WITH_FYE},
        yf_fail_tickers={"AAPL"},
        finnhub_data={"AAPL": _finnhub_entries_for_aapl()},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    assert out["errors"] == 0
    assert out["quarter_yf_unavailable"] == 1 and out["quarter_yf_rows_written"] == 0
    assert out["quarter_finnhub_rows_written"] == 2
    fh_rows = [r for r in written if r["source"] == "finnhub_calendar"]
    assert len(fh_rows) == 2
    assert divergences == [], "no yfinance row exists to diverge against"
    assert any(e == "analyst_estimates_error" and "Finnhub wrote 2 row(s)" in m
               for e, m in audits)


@pytest.mark.asyncio
async def test_finnhub_uncorroborated_slot_keeps_the_reconstruction(monkeypatch):
    """No Finnhub entry near a slot's reconstructed candidate -> that yfinance row
    keeps its OWN date and LABEL_METHOD_YF_RECONSTRUCTED, exactly as if Finnhub did
    not cover this ticker for that quarter at all — Finnhub's own row for the
    entry it DID have still writes independently."""
    far_entry = {"date": date(2027, 6, 1), "quarter": 2, "year": 2027,
                 "revenue_estimate": 1.0, "eps_estimate": 1.0}
    written, _, divergences = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": _AAPL_CADENCE_WITH_FYE},
        yf_data={"AAPL": _yf_data_for("AAPL")},
        finnhub_data={"AAPL": [far_entry]},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    assert out["errors"] == 0
    yf_rows = [r for r in written if r["source"] == "yfinance"]
    assert all(r["period_label_method"] == aer.LABEL_METHOD_YF_RECONSTRUCTED for r in yf_rows)
    assert all(r["fiscal_quarter"] is None for r in yf_rows)
    assert {r["period_end_date"] for r in yf_rows} == {date(2026, 9, 26), date(2026, 12, 26)}, (
        "unchanged from the pure yfinance reconstruction")
    assert divergences == [], "the finnhub row's period_end_date never matches either slot"


@pytest.mark.asyncio
async def test_finnhub_outage_degrades_only_that_leg_and_never_touches_yfinance(
        monkeypatch):
    written, _, divergences = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": _AAPL_CADENCE_WITH_FYE},
        yf_data={"AAPL": _yf_data_for("AAPL")},
        finnhub_fail_tickers={"AAPL"},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    assert out["errors"] == 0
    assert out["quarter_finnhub_unavailable"] == 1 and out["quarter_finnhub_rows_written"] == 0
    assert out["quarter_finnhub_no_cadence"] == 0
    assert out["rows_written"] == 2   # unaffected: the 2 yfinance quarterly rows
    assert divergences == []


@pytest.mark.asyncio
async def test_finnhub_entries_that_all_fail_guards_count_as_label_rejected(monkeypatch):
    """Finnhub HAD calendar entries, but none passed finnhub_period_end_from_entry's
    self-consistency guards (here: no EDGAR fiscal_year_end resolved at all, since
    quarter_cadence omits it) — skipped and counted, distinct from an outage."""
    written, _, _div = _wire(
        monkeypatch,
        anchors={"AAPL": date(2026, 7, 31)},
        quarter_cadence={"AAPL": _AAPL_CADENCE},   # no fiscal_year_end
        yf_data={"AAPL": _yf_data_for("AAPL")},
        finnhub_data={"AAPL": _finnhub_entries_for_aapl()},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["AAPL"])
    assert out["errors"] == 0
    assert out["quarter_finnhub_no_cadence"] == 1 and out["quarter_finnhub_unavailable"] == 0
    assert out["quarter_finnhub_rows_written"] == 0
    assert all(r["source"] != "finnhub_calendar" for r in written)
    yf_rows = [r for r in written if r["source"] == "yfinance"]
    assert all(r["period_label_method"] == aer.LABEL_METHOD_YF_RECONSTRUCTED for r in yf_rows)


@pytest.mark.asyncio
async def test_run_never_raises_into_the_scheduler(monkeypatch):
    async def boom(since):
        raise RuntimeError("db down")
    monkeypatch.setattr(aer, "get_analyst_estimate_population", boom)
    out = await aer.run_analyst_estimates_snapshot(AS_OF)   # population lookup fails
    assert out["errors"] == 1 and out["rows_written"] == 0


# ── registration + THE LINE pins ─────────────────────────────────────────────────────


def test_liveness_registry_watches_the_recorder_on_its_business_date():
    """The recorder is SILENT, so the detector-liveness registry is its ONLY watchdog —
    a dead writer silently stops the 60-day clock gating #333. Keyed on the plain-DATE
    column (a timestamptz key would silently never be checked)."""
    from agents.market_intelligence.health_checks import _DETECTOR_LIVENESS_TABLES
    entries = [t for t in _DETECTOR_LIVENESS_TABLES if t[0] == "mi_analyst_estimates"]
    assert len(entries) == 1
    assert entries[0][2] == "as_of_date"


def test_job_is_classified_intelligence_owned():
    from agents.market_intelligence.scheduler import (
        EXECUTION_OWNED_JOB_IDS, INTELLIGENCE_OWNED_JOB_IDS,
    )
    assert "analyst_estimates_snapshot" in INTELLIGENCE_OWNED_JOB_IDS
    assert "analyst_estimates_snapshot" not in EXECUTION_OWNED_JOB_IDS


def test_the_line_no_telegram_no_broker_no_score():
    """DATA CAPTURE ONLY, pinned to the source: no Telegram send, no broker import,
    and no computed durability score anywhere in the recorder (raw values only —
    a stored score goes stale the moment a threshold is swept)."""
    src = Path(aer.__file__).read_text()
    assert "send_telegram" not in src
    assert "notify_job_failure" not in src
    assert "from agents.market_intelligence.broker" not in src
    assert "durability_score" not in src and "a7_durability" not in src


def test_the_402_endpoint_is_never_called_and_log_lines_are_redacted():
    """Two pins from the 2026-09-01 incident. (1) FMP /income-statement and /earnings
    are 402 on our plan — verified live, 99/99 tickers — so no fetch may target them
    again (the docstring may MENTION them as history; _fmp_get may not be pointed at
    them). (2) FMP puts the API key in the QUERY STRING and 99 audit rows landed
    carrying a live key: db.log_audit_event now redacts at the chokepoint, and every
    recorder log line that formats an exception must go through redact_secrets so the
    key never lands in container logs either."""
    src = Path(aer.__file__).read_text()
    assert '_fmp_get("/income-statement"' not in src
    assert '_fmp_get("/earnings"' not in src
    assert "from shared.secret_redaction import redact_secrets" in src
    assert "logger.warning(redact_secrets(" in src   # the per-ticker failure line
