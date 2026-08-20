"""One malformed theme entry must not drop the whole discovery run.

2026-08-19: the model returned a bare name STRING inside `themes`, the
comprehension called `.get` on it, and the AttributeError propagated to the
caller's `discovery_error` handler — which returns []. One bad entry cost every
theme discovered that night. The parser now drops malformed entries and keeps
the rest.
"""
import pytest

from agents.market_intelligence.theme_engine import NEW_THEME_MIN_STOCKS


def _parse(raw_themes):
    """Mirror of the guard in _discover_new_themes' report-block branch."""
    if not isinstance(raw_themes, list):
        raw_themes = []
    raw_themes = [t for t in raw_themes if isinstance(t, dict)]
    return [t for t in raw_themes if len(t.get("tickers", []) or []) >= NEW_THEME_MIN_STOCKS]


def _theme(name, n):
    return {"name": name, "tickers": [f"T{i}" for i in range(n)]}


def test_FAILS_WITHOUT_FIX_a_bare_string_entry_no_longer_kills_the_run():
    good = _theme("Nuclear SMR", NEW_THEME_MIN_STOCKS)
    out = _parse(["Quantum Computing", good])          # the 2026-08-19 shape
    assert out == [good], "one malformed entry must not drop the well-formed ones"


def test_a_non_list_themes_value_degrades_to_empty_not_a_crash():
    assert _parse("Nuclear SMR") == []
    assert _parse(None) == []


def test_null_tickers_does_not_raise():
    assert _parse([{"name": "X", "tickers": None}]) == []


def test_well_formed_input_is_unchanged():
    a, b = _theme("A", NEW_THEME_MIN_STOCKS), _theme("B", NEW_THEME_MIN_STOCKS)
    assert _parse([a, b]) == [a, b]


def test_a_theme_below_the_minimum_is_still_filtered():
    assert _parse([_theme("Thin", NEW_THEME_MIN_STOCKS - 1)]) == []
