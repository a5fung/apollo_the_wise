"""The co-movement membership test must be able to price every name the assignment pass judges
(2026-09-28). Names only in the assignment pool — the RS-floor pool and the #491 M2 seeded converts —
were missing from the price universe, so the signed test called them unjudgeable and the retired sector
label decided (IREN 09-17, CIFR 09-21 and 09-28).
"""
from agents.market_intelligence.theme_engine import _comove_universe_for


def test_assignment_pool_names_are_priced():
    u = _comove_universe_for(
        leaders=[{"ticker": "NVDA"}], velocity_all=[{"ticker": "SMCI"}], turners_all=[],
        updated_themes=[{"tickers": ["HUT", "RIOT"]}], clusters=[{"tickers": ["CLSK"]}],
        assignment_pool=[{"ticker": "CIFR"}, {"ticker": "IREN"}])
    assert {"CIFR", "IREN"} <= u
    assert {"NVDA", "SMCI", "HUT", "RIOT", "CLSK"} <= u


def test_no_pool_still_builds():
    u = _comove_universe_for([], [], [], [], None, None)
    assert u == set()
