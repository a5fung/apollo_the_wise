"""Unit tests for the #189 pure materiality helpers (shadow/eval-only module)."""
from __future__ import annotations

import pytest

from agents.market_intelligence.catalyst_materiality import (
    extract_deal_value,
    rule_materiality,
    is_material,
)


@pytest.mark.parametrize("text,expected", [
    ("a multi-year $270 million agreement", 270e6),
    ("$1.2B buyback authorized", 1.2e9),
    ("entered into a $270M deal", 270e6),
    ("USD 1.5 billion contract", 1.5e9),
    ("revenue of $500 million, a $2.1 billion order", 2.1e9),  # MAX of several
    ("$500,000 grant", 500_000.0),
    ("no dollar figure here", None),
    ("founded in 2019, 250 employees", None),  # bare numbers, no unit -> ignored
    ("", None),
    (None, None),
])
def test_extract_deal_value(text, expected):
    assert extract_deal_value(text) == expected


@pytest.mark.parametrize("deal,cap,tier", [
    (270e6, 2.5e9, "material"),        # RUM anchor ~10.8%
    (270e6, 600e9, "immaterial"),      # same deal, mega-cap ~0.045%
    (60e6, 200e6, "transformative"),   # 30% of a micro-cap
    (30e6, 2e9, "minor"),              # 1.5%
    (None, 2e9, None),                 # no deal value -> abstain
    (270e6, None, None),               # no cap -> abstain
    (270e6, 0, None),                  # zero cap -> abstain
])
def test_rule_materiality(deal, cap, tier):
    assert rule_materiality(deal, cap) == tier


def test_is_material_thresholds():
    assert is_material("transformative") is True
    assert is_material("material") is True
    assert is_material("minor") is False
    assert is_material("immaterial") is False
    # Unknown signal fails OPEN — never demote a real EP on a missing materiality read
    assert is_material(None) is True
