"""#214 name-inheritance guard — pattern shape + fail-open contract.

The guard blocks Jaccard name-inheritance from donors whose name was recently
mass-evicted by validation (the name-narrower-than-cluster signature). Night-one
evidence 2026-06-09: inheritance resurrected 'Pure-Play Hydraulic Fracturing &
Completion Services' over the correctly-named 'U.S. Shale & Onshore E&P'.
"""
import asyncio
import re

from agents.market_intelligence.theme_engine import (
    _MASS_REMOVAL_SUMMARY_FMT, _REMOVAL_SUMMARY_FMT,
    _mass_evicted_patterns, _name_recently_mass_evicted,
)

_PUREPLAY = "Pure-Play Hydraulic Fracturing & Completion Services"
_FRAGMENT = "Hydraulic Fracturing & Completion Services"


def _like(pattern: str, s: str) -> bool:
    """SQL LIKE semantics for the patterns under test (% = any run, _ unused)."""
    rx = "^" + ".*".join(re.escape(part) for part in pattern.split("%")) + "$"
    return re.match(rx, s) is not None


def test_removal_pattern_matches_what_the_emit_site_writes():
    # Producer↔matcher binding: the expected summary is built from the SAME format
    # constant the emit site uses, so a rewording can't silently kill the guard.
    _, removal = _mass_evicted_patterns(_PUREPLAY)
    assert _like(removal, _REMOVAL_SUMMARY_FMT.format(tk="XOM", theme=_PUREPLAY))


def test_tripwire_pattern_matches_what_the_emit_site_writes():
    tripwire, _ = _mass_evicted_patterns(_PUREPLAY)
    assert _like(tripwire, _MASS_REMOVAL_SUMMARY_FMT.format(
        theme=_PUREPLAY, n_flagged=12, n_members=15))


def test_fragment_name_does_not_substring_match_pureplay_rows():
    # 'Hydraulic Fracturing…' is a substring of 'Pure-Play Hydraulic Fracturing…';
    # the quoted/anchored patterns must NOT cross-match.
    tripwire, removal = _mass_evicted_patterns(_FRAGMENT)
    assert not _like(removal, f"XOM removed from '{_PUREPLAY}' by validation")
    assert not _like(tripwire, f"'{_PUREPLAY}': validation flagged 12/15 members")


def test_guard_fails_open_on_db_error(monkeypatch):
    def _boom():
        raise RuntimeError("no pool in tests")
    import agents.market_intelligence.theme_engine as theme_engine
    monkeypatch.setattr(theme_engine, "get_pool", _boom)
    assert asyncio.run(_name_recently_mass_evicted(_PUREPLAY)) is False
