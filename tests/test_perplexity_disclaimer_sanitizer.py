"""Regression tests for Perplexity catalyst disclaimer wholesale-discard (#130, 2026-05-27).

CRSR / DY 2026-05-27 EP alerts had broken catalyst blocks:
  - CRSR: "I don't have any reliable, up-to-date news... Given that, here's
    how I'd approach it as an analyst, and what is usually driv" (mid-word cut)
  - DY:   "DY is likely a ticker mismatch here: the search results point to
    DiDi Global, whose symbol is DIDIY, not DY... If you meant DIDIY, t"
    (mid-word cut + speculative ticker hallucination)

The original sanitizer only stripped the first disclaimer sentence; speculative
follow-up prose survived. Plus the raw `[:300]` slice cut mid-word.

Fix: wholesale-discard when any signal phrase appears AND smart-truncate.
"""
from agents.market_intelligence.briefing import (
    _sanitize_perplexity_filler,
    _truncate_sentence,
)


# ── Wholesale-discard signals (new in #130) ─────────────────────────────────

def test_crsr_no_data_disclaimer_discarded():
    """The CRSR case — wholesale-discard."""
    text = (
        "I don't have any reliable, up-to-date news or tape-level data in the "
        "feed you've provided that explains the most recent gap up in Corsair "
        "Gaming (CRSR), and none of the results shown are about the stock or "
        "its catalysts. Given that, here's how I'd approach it as an analyst, "
        "and what is usually driving these moves."
    )
    assert _sanitize_perplexity_filler(text) == "See news"


def test_dy_ticker_mismatch_discarded():
    """The DY case — ticker mismatch phrase wholesale-discards."""
    text = (
        "DY is likely a ticker mismatch here: the search results point to DiDi "
        "Global, whose symbol is DIDIY, not DY. The available result says Didi "
        "has been moving lower without a clear news catalyst, so there is no "
        "evidence here of a specific event explaining a gap up in DY/DIDIY. "
        "If you meant DIDIY, the catalyst is..."
    )
    assert _sanitize_perplexity_filler(text) == "See news"


def test_speculative_analyst_approach_discarded():
    """'here's how I'd approach it as an analyst' is a tell that Perplexity
    didn't find data and is speculating."""
    text = (
        "Looking at the data shown, here's how I'd approach it as an analyst, "
        "and what is usually driving these moves."
    )
    assert _sanitize_perplexity_filler(text) == "See news"


def test_if_you_meant_other_ticker_discarded():
    """Ticker hallucination of the form 'If you meant XYZ' = wrong-ticker
    speculation; wholesale discard."""
    text = "FOO is unclear from the data. If you meant BARZ, the catalyst is X."
    assert _sanitize_perplexity_filler(text) == "See news"


# ── Legit content survives (regression guards) ──────────────────────────────

def test_legit_earnings_catalyst_preserved():
    """A real earnings catalyst with revenue + EPS numbers must NOT be
    discarded by the new wholesale rule."""
    text = (
        "AGYS reported Q4 earnings with 12% revenue growth to $185M and EPS "
        "of $0.42, beating consensus."
    )
    out = _sanitize_perplexity_filler(text)
    assert out == text
    assert "12% revenue growth" in out


def test_legit_with_old_style_disclaimer_partially_strips():
    """An old-style disclaimer ('I cannot find...') still strips the first
    sentence (existing behavior preserved); doesn't wholesale-discard."""
    text = (
        "I cannot find specific Q4 numbers for XYZ. However, the company "
        "announced a strategic acquisition yesterday."
    )
    out = _sanitize_perplexity_filler(text)
    # First sentence stripped, second survives — existing behavior, NOT a
    # wholesale discard.
    assert out != "See news"
    assert "strategic acquisition" in out


def test_partial_phrase_match_not_overgreedy():
    """Defensive: 'data' alone shouldn't trigger wholesale discard. The
    pattern requires a 'don't have data' or similar full phrase."""
    text = "Strong revenue beat with $185M in data center sales."
    assert _sanitize_perplexity_filler(text) == text


def test_if_you_meant_quarter_not_ticker_preserved():
    """Advisor 2026-05-27: 'If you meant Q1, the comparison is...' is legit
    analyst prose discussing quarter — must NOT wholesale-discard. The
    `If you meant [A-Z]{3,6}` pattern requires 3+ char minimum to skip
    Q1/Q2/Q3/Q4 false-positives."""
    text = (
        "FOO posted earnings yesterday. If you meant Q1 results, "
        "revenue grew 18% YoY to $200M."
    )
    out = _sanitize_perplexity_filler(text)
    assert out != "See news", "must not wholesale-discard legit analyst prose"


# ── Smart truncation (replaces [:300] mid-word cut) ──────────────────────────

def test_truncate_at_sentence_boundary():
    """Long catalyst → cut at last sentence terminator within max_len, not
    mid-word."""
    text = (
        "Apple reported Q4 revenue of $94B beating consensus. iPhone sales "
        "up 17%. Services revenue hit record. AI Vision Pro launch upcoming."
    )
    out = _truncate_sentence(text, 100)
    assert not out.endswith("driv")  # no mid-word cut
    assert out.endswith(".") or out.endswith("…")


def test_truncate_short_text_unchanged():
    """Text shorter than max_len returns as-is."""
    text = "AAPL Q4 revenue $94B."
    assert _truncate_sentence(text, 300) == text


def test_truncate_no_sentence_terminator_falls_back_to_word_boundary():
    """If no '. ' found in the cut, fall back to word boundary + ellipsis —
    still no mid-word cut."""
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    out = _truncate_sentence(text, 25)
    assert not out.endswith("kapp")  # no mid-word cut
    assert out.endswith("…")
