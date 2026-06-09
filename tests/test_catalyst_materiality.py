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
    ("revenue of $500 million, a $2.1 billion order", 2.1e9),  # metric vetoed, deal kept
    ("$500,000 grant", 500_000.0),
    ("no dollar figure here", None),
    ("founded in 2019, 250 employees", None),  # bare numbers, no unit -> ignored
    ("", None),
    (None, None),
    # #251 — earnings/metric figures are NOT deal values; rule must abstain (None)
    ("Q1 revenue of $500 million, up 42% year-over-year", None),
    ("reported record quarterly sales of $890 million", None),
    ("raised full-year guidance to $2.1 billion", None),       # 'raised' near, but guidance vetoes
    ("EPS of $1.25 on net income of $45 million", None),
    ("market capitalization of $2.5 billion", None),
    ("reported $500 million in revenue", None),
    ("adjusted EBITDA of $120M beat estimates", None),
    # #251 — deal figures still extracted, incl. mixed deal+metric text
    ("acquires Foo for $450 million; Foo had revenue of $120 million", 450e6),
    ("deal valued at $2.1 billion in cash and stock", 2.1e9),
    ("a $50 million milestone payment from its partner", 50e6),
    ("company announced a $30M contract", 30e6),               # W1 integration fixture shape
    # #251 — a plain large figure with NO deal context abstains (judge decides)
    ("shares surged after the $3 billion announcement", None),
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
