"""Unit tests for strip_perplexity_disclaimer (2026-05-14 ship).

Locks the marker-detection behavior so future expansions don't regress.
"""
from __future__ import annotations

import pytest

from agents.market_intelligence.collector import strip_perplexity_disclaimer


@pytest.mark.parametrize("text,expect_disclaimer", [
    ("No recent catalysts found for RAL stock gapping up.", True),
    ("No direct catalyst found for P (Parsley Energy or similar)", True),
    ("I don't have information about GLIBK or any gap-up movement", True),
    ("No specific news or catalyst found for FOUR", True),
    ("Nearest match is 5N Plus (FPLSF)", True),
    ("Closest match is Rocket Lab", True),
    ("Search results reference Rocket Lab wins", True),
    ("Search results focus on broader biotech market activity", True),
    # Legitimate catalyst — no disclaimer
    ("NBIS gapped up due to Bank of America raising price target to $205", False),
    ("Q1 earnings beat: revenue $1.2B up 18% YoY", False),
    # Edge: disclaimer phrase appears mid-content (after 200 chars) — should NOT trip
    (
        "Nebius reported strong Q1 with revenue up 30%, EPS beat estimates by 15%. "
        "BofA raised target. Analyst commentary focused on AI cloud growth. "
        "Forward guidance suggests continued momentum. Note: search results "
        "reference an old article from last quarter that's no longer relevant.",
        False,
    ),
    # Empty / None
    (None, False),
    ("", False),
])
def test_disclaimer_detection(text, expect_disclaimer):
    _, is_disc = strip_perplexity_disclaimer(text)
    assert is_disc == expect_disclaimer, \
        f"Disclaimer detection wrong for: {text!r} (expected {expect_disclaimer})"
