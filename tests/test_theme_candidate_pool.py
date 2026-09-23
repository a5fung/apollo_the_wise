"""ADR 0007 (c)/(c2) — discovery candidate-pool union covers velocity/turners.

Regression guard: sector-enrichment + description-fetch must cover EVERY discovery
candidate pool, not just the top-60 `leaders`. A velocity/turner (or future
accelerator) candidate with a blank sector is unclusterable, and one with no
description is silently dropped from discovery (`_discover_new_themes` ~line 2356) —
the mechanism that left the igniting drone leaders (below the top-60 cut) out of
clustering on 5/28. This test pins that `_all_candidate_pool` includes those pools.
"""
from agents.market_intelligence.theme_engine import _all_candidate_pool


def test_union_includes_leaders_velocity_turners():
    leaders = [{"ticker": "AAA"}, {"ticker": "BBB"}]
    velocity = [{"ticker": "VEL"}]
    turners = [{"ticker": "TRN"}]
    tickers = {s["ticker"] for s in _all_candidate_pool(leaders, velocity, turners)}
    assert tickers == {"AAA", "BBB", "VEL", "TRN"}
    # velocity + turner names MUST be present — that is the whole fix
    assert "VEL" in tickers and "TRN" in tickers


def test_handles_none_pools():
    leaders = [{"ticker": "AAA"}]
    assert {s["ticker"] for s in _all_candidate_pool(leaders, None, None)} == {"AAA"}
    assert _all_candidate_pool([], None, None) == []


def test_preserves_dicts_for_in_place_sector_enrichment():
    # enrichment mutates each dict's "sector" in place, so the SAME dict objects
    # from each pool must flow through (not copies) — assert identity is preserved.
    vel = {"ticker": "VEL", "sector": ""}
    pool = _all_candidate_pool([{"ticker": "AAA"}], [vel], None)
    assert any(s is vel for s in pool)
