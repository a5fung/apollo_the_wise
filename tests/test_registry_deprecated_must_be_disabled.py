"""`phase='deprecated'` + `enabled=true` must be IMPOSSIBLE, not merely currently-false.

Found 2026-08-02: ALL THREE deprecated strategies were sitting enabled — 9M Day 2 (since
2026-07-06), Continuation Flag, and Fishhook. The phase gate blocks entries so nothing traded,
which is precisely why it went unnoticed for 26 days: the rows kept their jobs registered and their
code paths live while looking retired.

That half-alive state already cost something. 9M Day 2 stayed in the shared submit_trade_entry
funnel long enough for #490's submission-time gap guard to come within one review of applying
MAGNA53's 10% floor to a strategy whose own bar is 3%.
"""
import pytest

from agents.market_intelligence.strategies.registry import assert_no_deprecated_but_enabled


class _S:
    def __init__(self, name, phase, enabled):
        self.name, self.phase, self.enabled = name, phase, enabled


def _reg(*rows):
    return {r.name: r for r in rows}


def test_raises_on_a_deprecated_but_enabled_row():
    with pytest.raises(RuntimeError, match="deprecated strategies are still enabled"):
        assert_no_deprecated_but_enabled(_reg(_S("9M Day 2 ORB", "deprecated", True)))


def test_the_error_names_every_offender_not_just_the_first():
    """All three were in this state at once — an error naming one would send you round the loop."""
    with pytest.raises(RuntimeError) as e:
        assert_no_deprecated_but_enabled(_reg(
            _S("9M Day 2 ORB", "deprecated", True),
            _S("Fishhook", "deprecated", True),
            _S("Continuation Flag", "deprecated", True)))
    for n in ("9M Day 2 ORB", "Fishhook", "Continuation Flag"):
        assert n in str(e.value)


def test_deprecated_and_disabled_is_fine():
    assert_no_deprecated_but_enabled(_reg(_S("9M Day 2 ORB", "deprecated", False)))


def test_live_and_shadow_are_untouched():
    assert_no_deprecated_but_enabled(_reg(
        _S("MAGNA53 EP", "live", True),
        _S("Parabolic Short", "shadow", True),
        _S("Wick-Fill", "shadow", True)))


def test_phase_check_is_case_insensitive():
    """A 'Deprecated' row must not slip through on capitalisation."""
    with pytest.raises(RuntimeError):
        assert_no_deprecated_but_enabled(_reg(_S("X", "Deprecated", True)))


def test_empty_registry_is_not_an_error():
    assert_no_deprecated_but_enabled({})
