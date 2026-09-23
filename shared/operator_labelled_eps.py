"""The operator-labelled EP identity list — ticker + alert_date, nothing else.

⚠⚠⚠ OPERATOR-AUTHORED. NEVER ADD A NAME HERE ON YOUR OWN JUDGEMENT. ⚠⚠⚠
A name enters this list ONLY when the operator has personally called that stock a real EP, in his
own words, in the same conversation turn those words are quoted into
`docs/methodology/operator_labelled_eps.md`. Never add one because it made money (return-selected
cohorts are explicitly NOT ground truth here — see the doc); never remove one because it didn't.

WHY THIS FILE EXISTS: `agents/` cannot import from `tests/fixtures/`, which is where the
machine-readable list lived before this file (`tests/fixtures/must_not_miss_eps.py::MUST_NOT_MISS`,
filtered to `label_source == "operator"`). The invariant this module feeds
(`agents/market_intelligence/audit_invariants.py::check_operator_ep_downgraded`) needs to import
the identity list from inside `agents/`, so the identity — and ONLY the identity — moved here.
The fixture now takes ITS identity from this module rather than keeping a second hand-typed copy.

THREE SURFACES, ONE TRUTH, kept in sync by tests, not by care:
  - `docs/methodology/operator_labelled_eps.md` — the HUMAN source of truth: his exact words, the
    gap, and what our system actually did with each name. Edit this FIRST when he names one.
  - THIS MODULE — identity only (ticker + alert_date). What code checks against.
  - `tests/fixtures/must_not_miss_eps.py` — the rich selection-quality fixture; its operator-named
    members source `ticker`/`alert_date` FROM `OPERATOR_LABELLED_EPS` below, not a re-typed literal.
`tests/test_operator_labelled_ep_list.py` fails the build the moment any two of the three drift.

HOW TO ADD A NAME (mirrors the doc's "The rule for adding one"):
  1. Add a row to `OPERATOR_LABELLED_EPS` below — ticker + alert_date, quoting his words in the
     commit, not in this file (this file stays identity-only on purpose).
  2. Add the row to `docs/methodology/operator_labelled_eps.md`'s table, his exact words + what our
     system did.
  3. Add the corresponding `EPFixtureMember(...)` to `tests/fixtures/must_not_miss_eps.py`
     (`label_source="operator"`), sourcing ticker/alert_date from this module.
"""
from __future__ import annotations

from typing import NamedTuple


class OperatorLabelledEP(NamedTuple):
    ticker: str
    alert_date: str  # ISO "YYYY-MM-DD" — the EP/gap day, as he named it


# The list, in the SAME order as the doc table's rows (`docs/methodology/operator_labelled_eps.md`)
# — keep new rows appended in that order so a diff of one is a diff of both.
OPERATOR_LABELLED_EPS: tuple[OperatorLabelledEP, ...] = (
    OperatorLabelledEP("BFLY", "2026-06-18"),
    OperatorLabelledEP("PLTR", "2026-08-04"),
    OperatorLabelledEP("ABNB", "2026-08-07"),
    OperatorLabelledEP("TEAM", "2026-08-07"),
    OperatorLabelledEP("HTFL", "2026-08-14"),
    OperatorLabelledEP("MRNA", "2026-08-19"),
    OperatorLabelledEP("CHPT", "2026-09-03"),
)


def identity(ticker: str) -> OperatorLabelledEP:
    """Look up an operator-labelled EP's identity by ticker. Raises KeyError if the ticker is
    not on the list — used by the fixture to source its members FROM this module instead of
    keeping a second hand-typed copy, so a typo diverges loudly instead of silently."""
    for ep in OPERATOR_LABELLED_EPS:
        if ep.ticker == ticker:
            return ep
    raise KeyError(
        f"{ticker!r} is not in OPERATOR_LABELLED_EPS — add it there first "
        "(and to docs/methodology/operator_labelled_eps.md) before referencing it elsewhere."
    )


class AcknowledgedDowngrade(NamedTuple):
    reason: str    # the NAMED root cause — not "looked and it's fine"
    owner: str     # the task/doc that investigated and owns the fix, e.g. "#210"
    note: str      # one line of context, citable in a Telegram body


# ⚠⚠⚠ ADDING A ROW HERE SILENCES AN ALARM. ⚠⚠⚠
# `audit_invariants.check_operator_ep_downgraded` breaches on every operator-labelled real EP the
# catalyst rubric downgraded (`agents/market_intelligence/ep_detector.py`'s
# `catalyst_earnings_revenue_weak_downgrade` / `catalyst_prose_mismatch_downgrade` /
# `catalyst_pplx_hedge_downgrade` events) UNLESS the exact (ticker, alert_date, event_type) triple
# is listed below. A triple, not a (ticker, alert_date) pair: the cause has to be understood PER
# MECHANISM — acknowledging BFLY's revenue-safety-net downgrade must not silently also acknowledge
# a hedge or prose downgrade on BFLY nobody has looked at.
#
# The bar for a row here is a NAMED root cause plus the task/doc that owns it. "We looked and it
# seems fine" is never a reason. If a new operator-named EP shows up here, that is the automation
# doing exactly the job the operator asked for on 2026-09-07 — investigate it for real (or leave
# it unacknowledged and let the invariant breach) before adding a row.
ACKNOWLEDGED_DOWNGRADES: dict[tuple[str, str, str], AcknowledgedDowngrade] = {
    ("BFLY", "2026-06-18", "catalyst_earnings_revenue_weak_downgrade"): AcknowledgedDowngrade(
        reason=(
            "news_corpus_sparse_no_q_rev — a RETRIEVAL failure, not a rubric defect. BFLY's "
            "catalyst was a partnership (Midjourney Medical, up to $74M over 5 years), so there "
            "was no quarterly revenue line for the earnings-safety-net gate to extract, and the "
            "corpus never contained the partnership announcement at all — the gate downgraded it "
            "for lacking data it could never have had, on top of never having found the real news."
        ),
        owner="#210 (source coverage — an accurate read of the news, PLAN.md)",
        note=(
            "strong -> routine, 2026-06-18. Stock 5.71 -> 8.90 same day (+55.9%) -> 9.00 two "
            "months on. docs/methodology/operator_labelled_eps.md and PLAN.md #448 (2026-09-05) "
            "carry the full trace."
        ),
    ),
    ("TEAM", "2026-08-07", "catalyst_earnings_revenue_weak_downgrade"): AcknowledgedDowngrade(
        reason=(
            "extraction_failed_extraction_call_failed — the 2026-08-06/08-07 extraction-outage "
            "bug (health_checks.py's grading-health check tracks this exact incident: 46 of 52 "
            "grading decisions were extraction FAILURES that day, not weak data). The operator "
            "ruled mid-incident, 2026-08-07: \"we shouldn't downgrade stocks due to call "
            "failure.\" That rule is already live in ep_detector.py (a failed extraction call now "
            "KEEPS the grade — see `_extraction_failed_no_downgrade` / "
            "`catalyst_extraction_failed_grade_kept`) — this row predates that fix landing the "
            "same day. The rubric never actually judged TEAM: its final acting grade held at "
            "strong / 115.2 / HIGH and it was entered live."
        ),
        owner="#448 (PLAN.md) — verified against prod 2026-09-05 and re-verified 2026-09-07",
        note=(
            "raw grade knocked strong -> routine on 2026-08-07; the FINAL acting grade nonetheless "
            "held at strong / 115.2 / HIGH and TEAM was entered live (PLAN.md #448, prod-verified) "
            "— the exact recovery mechanism (a later re-resolve vs. a same-day fix landing before "
            "scoring) was not independently re-traced here, only the recorded outcome. TEAM was "
            "one of 14 earnings names the same outage knocked down that morning (DOCS/PUBM/TEAM/"
            "NET/TWLO/FROG, per ep_detector.py's own incident comment)."
        ),
    ),
}
