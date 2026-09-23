"""#246 — theme_engine transient-exception guards must never `isinstance()`-TypeError.

The handlers do `isinstance(e, (anthropic.APIError, …))`. In a local/CI env where the
`anthropic` module is stubbed/shadowed, `anthropic.APIError` is not a real class and
`isinstance()` raises `TypeError: arg 2 must be a type`. The fix resolves the exception
classes to actual types once at import (`_real_types`), so the guards are always valid.
"""
from unittest.mock import MagicMock

import agents.market_intelligence.theme_engine as te


def test_real_types_filters_non_types():
    # A Mock (what a stubbed anthropic.APIError looks like) is dropped; real types kept.
    assert te._real_types(MagicMock(), ValueError, "not a type", None) == (ValueError,)
    assert te._real_types() == ()
    assert te._real_types(MagicMock()) == ()  # the #246 repro: all non-types → empty tuple


def test_module_exc_tuples_are_valid_isinstance_args():
    # Both module constants must be tuples containing ONLY real types (or empty), so
    # isinstance() against them can never raise — that is the bug guard.
    for tup in (te._THEME_TRANSIENT_EXC, te._THEME_RATELIMIT_EXC):
        assert isinstance(tup, tuple)
        assert all(isinstance(t, type) for t in tup)
        # The operative property: isinstance must not raise for any of them.
        assert isinstance(ValueError("x"), tup) in (True, False)


def test_timeout_error_always_classified_transient():
    # asyncio.TimeoutError is always a real type → must remain in the transient set
    # regardless of whether anthropic's classes resolved (the graceful-degradation floor).
    import asyncio
    assert asyncio.TimeoutError in te._THEME_TRANSIENT_EXC
    assert isinstance(asyncio.TimeoutError(), te._THEME_TRANSIENT_EXC) is True
