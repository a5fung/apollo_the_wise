"""#448 — a NEGATED mention of earnings is not an earnings catalyst.

`_claude_text_signals_earnings` is the textual fallback that pulls a name into the earnings
rubric path when yfinance's calendar misses the date. It had no notion of negation, so a
sentence saying there was NO earnings release matched it.

BFLY 2026-06-18 is the case, and the operator has called it a real EP twice. Our own stored
analysis said: "No new earnings release, FDA decision, major contract, or 8-K filing has been
identified as the trigger" — `earnings release` matched, the name entered the earnings path,
and it was downgraded strong->routine on `news_corpus_sparse_no_q_rev` for lacking quarterly
revenue that a PARTNERSHIP catalyst could never have had.

Operator 2026-09-05: "we should know if it's earnings on the day or not, if not, we shouldn't
look at any earnings data and focus on news."
"""
import pytest

from agents.market_intelligence.ep_detector import _claude_text_signals_earnings

# The exact sentence from mi_ep_catalyst_metrics for BFLY 2026-06-18.
BFLY_REAL_TEXT = (
    "There is no concrete, verifiable company-specific catalyst driving BFLY's gap-up. The move "
    "appears entirely sentiment- and narrative-driven: BFLY was flagged on premarket momentum/mover "
    "screens attracting retail and day-trader flow, and was cited in a thematic AI imaging editorial "
    "piece (re: congenital heart care) — neither of which constitutes a fresh fundamental event. "
    "No new earnings release, FDA decision, major contract, or 8-K filing has been identified as "
    "the trigger; absent a real hard catalyst, this is a narrative/momentum gap with no repricing "
    "of underlying fundamentals."
)


def test_the_real_bfly_text_no_longer_reads_as_an_earnings_catalyst():
    assert _claude_text_signals_earnings(BFLY_REAL_TEXT) is False, (
        "BFLY's analysis explicitly says there was NO earnings release — it must not be "
        "pulled into the earnings rubric path"
    )


@pytest.mark.parametrize("text", [
    "No new earnings release has been identified as the trigger.",
    "There was no earnings report this quarter.",
    "absent any earnings results, the move is narrative-driven",
    "The company has not reported quarterly figures.",
    "This was never an earnings report.",
    "Nothing in the earnings results explains the move.",
])
def test_negated_mentions_are_not_signals(text):
    assert _claude_text_signals_earnings(text) is False, f"negated mention matched: {text!r}"


@pytest.mark.parametrize("text", [
    "The company reported Q2 results with revenue of $1.9B, up 93% Y/Y.",
    "Atlassian reported quarterly revenue of $1.766B, beating consensus.",
    "Q3 2026 earnings came in ahead of expectations.",
    "EPS of $2.14 versus $1.80 expected.",
    "The earnings release detailed record bookings.",
])
def test_real_earnings_language_still_signals(text):
    assert _claude_text_signals_earnings(text) is True, f"real earnings text missed: {text!r}"


def test_a_negation_far_away_does_not_suppress_a_real_signal():
    """The lookbehind is short on purpose — an unrelated 'not' earlier in the paragraph must
    not silence a genuine earnings mention that follows it."""
    text = (
        "The stock is not a biotech and has no FDA pathway to speak of, which matters because "
        "the sector trades on trial data rather than fundamentals in most cases here. "
        "Separately the company reported Q2 results this morning with revenue of $4.2B."
    )
    assert _claude_text_signals_earnings(text) is True


def test_mixed_text_takes_the_unnegated_signal():
    text = ("No new earnings release was identified at first. Later the company reported "
            "Q2 results with revenue of $500M.")
    assert _claude_text_signals_earnings(text) is True


def test_empty_input():
    assert _claude_text_signals_earnings(None) is False
    assert _claude_text_signals_earnings("") is False
