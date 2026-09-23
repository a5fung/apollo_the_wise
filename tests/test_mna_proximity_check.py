"""Regression tests for the M&A filter Part B proximity check (#119, 2026-05-27).

Bug: Polygon's per-ticker sentiment_reasoning sometimes attributes M&A
activity to a DIFFERENT tagged ticker (e.g. QBTS reasoning says
"Stock gained...driven by IonQ's acquisition..." — IonQ's deal, not
QBTS's). Existing Part A passed these as M&A-relevant for the filing
ticker because the reasoning DID contain an M&A keyword.

Fix (narrow per advisor 2026-05-27): when the M&A keyword in
sentiment_reasoning is sentence-preceded by a `[Sister]'s ` possessive
where Sister matches another tagged ticker (case-insensitive), reject
the article. Catches the QBTS/RGTI class; leaves other-entity-name
cases (e.g. "Hewlett-Packard's") to upstream filters.
"""
from agents.market_intelligence.ma_filter import (
    reasoning_other_entity_owns_deal,
)


# ── FP cases from corpus (must return True = block) ──────────────────────────

def test_qbts_ionq_acquisition_blocks():
    """The motivating case. QBTS reasoning attributes acquisition to IonQ."""
    reasoning = (
        "Stock gained 6.47% as part of broader quantum computing sector "
        "enthusiasm driven by IonQ's acquisition news and industry momentum."
    )
    insights = ["IONQ", "IONQ.WS", "SKYT", "QBTS", "RGTI", "RGTIW"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "acquisition", "QBTS", insights,
    ) is True


def test_rgti_ionq_merger_blocks():
    """Same article, different filing ticker. RGTI reasoning has 'IonQ's merger'."""
    reasoning = (
        "Stock gained 8.29% reflecting broader positive sentiment in the "
        "quantum computing sector following IonQ's merger approval."
    )
    insights = ["IONQ", "IONQ.WS", "SKYT", "QBTS", "RGTI", "RGTIW"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "merger", "RGTI", insights,
    ) is True


def test_warrant_suffix_normalized():
    """If insight_tickers has IONQ.WS but not bare IONQ, prose 'IonQ' still
    matches via the .WS → IONQ split-and-add behavior."""
    reasoning = "Stock gained driven by IonQ's acquisition news."
    insights_no_base = ["IONQ.WS", "QBTS"]  # no bare 'IONQ'
    assert reasoning_other_entity_owns_deal(
        reasoning, "acquisition", "QBTS", insights_no_base,
    ) is True


# ── TP cases from corpus (must return False = keep) ──────────────────────────

def test_d_dominion_merger_keeps():
    """The Dominion TP. Reasoning has 'merger' preceded by 'The' (article),
    not a sister-ticker possessive. Sister tickers (NEE, MSFT, AMZN, etc.)
    don't appear as possessives in this sentence."""
    reasoning = (
        "The merger would provide Dominion access to NextEra's expertise and "
        "resources while leveraging its valuable footprint in Virginia and "
        "the Carolinas."
    )
    insights = ["NEE", "NEEpN", "D", "MSFT", "AMZN", "GOOG", "GOOGL", "META"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "merger", "D", insights,
    ) is False


def test_nextera_possessive_after_keyword_ignored():
    """NextEra's appears in D's reasoning AFTER the merger keyword. Look-back
    only checks BEFORE the keyword, so NextEra's possessive doesn't trigger."""
    reasoning = (
        "The merger would provide Dominion access to NextEra's expertise."
    )
    # Even with NEE as sister ticker:
    insights = ["D", "NEE"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "merger", "D", insights,
    ) is False


def test_iren_the_acquisition_keeps():
    """IREN's reasoning has 'The acquisition represents...'. No possessive
    precedes 'acquisition'. Part B doesn't block; IREN is caught later by
    the existing direction check (IREN is acquirer)."""
    reasoning = (
        "The acquisition represents strategic expansion into Europe, "
        "increases power capacity to 5GW."
    )
    insights = ["IREN"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "acquisition", "IREN", insights,
    ) is False


# ── Defensive cases ──────────────────────────────────────────────────────────

def test_empty_reasoning_no_block():
    assert reasoning_other_entity_owns_deal("", "merger", "X", ["X", "Y"]) is False
    assert reasoning_other_entity_owns_deal(None, "merger", "X", ["X"]) is False


def test_no_sister_tickers_no_block():
    """When the article only tags the filing ticker, no sister to attribute
    to. Even possessive of filing ticker's own name should pass through."""
    reasoning = "Tesla's merger talks moved forward."
    insights = ["TSLA"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "merger", "TSLA", insights,
    ) is False


def test_unknown_proper_noun_possessive_no_block():
    """'Hewlett-Packard's acquisition' for HPQ ticker — the possessive proper
    noun doesn't match any sister ticker by symbol. Per advisor 2026-05-27:
    we don't have a name→ticker map, so this case passes through. Upstream
    filters handle it."""
    reasoning = "Move attributed to Hewlett-Packard's acquisition of XYZ."
    insights = ["HPQ", "XYZ"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "acquisition", "HPQ", insights,
    ) is False


def test_filing_ticker_own_possessive_no_block():
    """If the prose form happens to match the filing ticker itself (rare),
    don't block. The function explicitly excludes filing_ticker from
    sister_set."""
    reasoning = "ABC's acquisition completed yesterday."
    insights = ["ABC", "XYZ"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "acquisition", "ABC", insights,
    ) is False


def test_sentence_boundary_isolated():
    """If 'IonQ's' is in a DIFFERENT sentence from the M&A keyword, don't
    block — separation indicates the topics are not joined."""
    reasoning = (
        "IonQ's prior deal closed last year. Separately, this company "
        "announced a merger today."
    )
    insights = ["IONQ", "TGT", "QBTS"]
    # The "merger" keyword is in the SECOND sentence, IonQ's possessive is
    # in the FIRST. Sentence-bounded look-back should NOT find IonQ's before
    # merger.
    assert reasoning_other_entity_owns_deal(
        reasoning, "merger", "TGT", insights,
    ) is False


def test_multi_sentence_correct_attribution():
    """If the M&A keyword sentence DOES have the sister possessive, block —
    even if there are other sentences. Walk every sentence containing the
    keyword."""
    reasoning = (
        "This is the first sentence with no possessive. "
        "Then driven by IonQ's acquisition news."
    )
    insights = ["IONQ", "QBTS"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "acquisition", "QBTS", insights,
    ) is True


def test_curly_apostrophe_supported():
    """Polygon's prose sometimes uses curly apostrophe (’ instead of '). The
    regex must match both."""
    reasoning = "Stock moved on IonQ’s acquisition announcement."
    insights = ["IONQ", "QBTS"]
    assert reasoning_other_entity_owns_deal(
        reasoning, "acquisition", "QBTS", insights,
    ) is True
