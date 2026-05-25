"""Unit tests for the M&A filter direction-aware path (ma_filter.py).

Covers:
  - classify_direction: target / acquirer / ambiguous patterns
  - is_shareholder_litigation_notice: firm-name prefix detection
  - polygon_news_has_mna_headline: end-to-end with synthetic items
    mimicking the 5 audit-event sub-cases (CECO/THR/KALV/QBTS/INFQ).
"""
import asyncio
from unittest.mock import AsyncMock, patch

from agents.market_intelligence.ma_filter import (
    classify_direction,
    is_shareholder_litigation_notice,
    polygon_news_has_mna_headline,
)


# ── classify_direction ────────────────────────────────────────────────

def test_target_patterns():
    assert classify_direction("XYZ to be acquired by ABC for $50/sh") == "target"
    assert classify_direction("XYZ stockholders to receive $40 in cash") == "target"
    assert classify_direction("Avanos going private at $13 premium") == "target"
    assert classify_direction("KLAR agreed to sell to BigCo") == "target"
    assert classify_direction("All-cash offer for XYZ at $25") == "target"


def test_acquirer_patterns():
    assert classify_direction("CECO to acquire Thermon for $1B") == "acquirer"
    assert classify_direction("BigCo announces acquisition of SmallCo") == "acquirer"
    assert classify_direction("X agreed to acquire Y at premium") == "acquirer"
    assert classify_direction("Apple buys Beats for $3B") == "acquirer"


def test_ambiguous():
    assert classify_direction("") == "ambiguous"
    assert classify_direction(None) == "ambiguous"
    assert classify_direction("Quantum stocks rallied today") == "ambiguous"
    assert classify_direction("Merger of equals announced") == "ambiguous"


def test_target_beats_acquirer_when_both_match():
    # "X agreed to be acquired by Y" — both "to be acquired" (target) AND
    # implicit acquirer-direction-ish text in same sentence. Target wins.
    text = "X agreed to be acquired by Y in a deal where Y will acquire X"
    assert classify_direction(text) == "target"


# ── is_shareholder_litigation_notice ──────────────────────────────────

def test_shareholder_litigation_firms():
    assert is_shareholder_litigation_notice(
        "BRODSKY & SMITH SHAREHOLDER UPDATE: Notifying Investors..."
    )
    assert is_shareholder_litigation_notice(
        "POMERANTZ LAW Announces Investigation of KalVista"
    )
    assert is_shareholder_litigation_notice(
        "Halper Sadeh LLC Investigating Class Action"
    )
    assert is_shareholder_litigation_notice(
        "  Johnson Fistel investigating MNST  "  # leading whitespace + caps
    )


def test_non_litigation_notices_pass_through():
    assert not is_shareholder_litigation_notice(
        "CECO Environmental and Thermon Announce Election Deadline"
    )
    assert not is_shareholder_litigation_notice("Some Random Headline")
    assert not is_shareholder_litigation_notice("")
    assert not is_shareholder_litigation_notice(None)


# ── polygon_news_has_mna_headline (end-to-end) ────────────────────────

def _mk_item(title, description="", insights=None):
    return {
        "title": title, "description": description,
        "insights": insights or [],
        "published_utc": "2026-05-15T11:00:00Z",
        "publisher": "Test Publisher",
    }


def _run_polygon_check(items, ticker):
    """Run polygon_news_has_mna_headline against a synthetic news list."""
    with patch("agents.market_intelligence.collector.get_polygon_news",
               new=AsyncMock(return_value=items)):
        return asyncio.run(polygon_news_has_mna_headline(ticker))


# Canonical CECO/THR test fixture — same article, both tickers tagged with
# opposite directions. Reused across the two direction-aware tests below.
_CECO_THR_ITEM = _mk_item(
    title=(
        "CECO Environmental and Thermon Group Holdings Announce Election "
        "Deadline for Thermon Stockholders to Elect Form of Merger Consideration"
    ),
    insights=[
        {"ticker": "CECO", "sentiment_reasoning":
         "CECO Environmental is acquiring Thermon Group Holdings in this transaction."},
        {"ticker": "THR", "sentiment_reasoning":
         "Thermon Group stockholders to receive merger consideration as part of the buyout."},
    ],
)


def test_ceco_acquirer_blocked():
    """CECO is acquirer in 5/15 THR deal — Path A title-match + direction
    check should reject."""
    assert _run_polygon_check([_CECO_THR_ITEM], "CECO") is None


def test_thr_target_accepted():
    """THR (target) on the same article — should still fire."""
    result = _run_polygon_check([_CECO_THR_ITEM], "THR")
    assert result is not None
    assert result["ticker"] == "THR"
    assert result["match_path"] == "title"


def test_kalv_shareholder_litigation_blocked():
    """KALV in BRODSKY & SMITH investigation notice — should be blocked
    by the firm-prefix check regardless of M&A keyword presence."""
    item = _mk_item(
        title=(
            "BRODSKY & SMITH SHAREHOLDER UPDATE: Notifying Investors of the "
            "Following Investigations: KalVista Pharmaceuticals, Inc. (Nasdaq – KALV)"
        ),
        description="Class action investigation into the merger of equals announced last quarter.",
        insights=[
            {"ticker": "KALV", "sentiment_reasoning":
             "Investigation of KalVista following merger announcement."},
        ],
    )
    assert _run_polygon_check([item], "KALV") is None


def test_title_acquirer_without_insights_still_accepts():
    """Conservative: if insights are missing, can't determine direction.
    Accept the title-match (existing behavior preserved) — safer to over-
    filter occasionally than to miss a real M&A target."""
    item = _mk_item(
        title="BigCorp to acquire SmallCorp in $5B merger deal",
        insights=[],
    )
    assert _run_polygon_check([item], "BIGCORP") is not None


def test_target_in_body_with_acquirer_insights_blocked():
    """Path B sister case — description matches AND insights show acquirer
    direction for this ticker → should be blocked."""
    item = _mk_item(
        title="Quarterly market summary",
        description="Including news of the merger between A and B",
        insights=[
            {"ticker": "ACQ", "sentiment_reasoning":
             "ACQ Corp announces acquisition of Target Inc for $2B."},
        ],
    )
    assert _run_polygon_check([item], "ACQ") is None
