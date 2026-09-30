"""#580 — a newborn theme is born WITH breadth, from the same function the rescore path uses.

`_score_new_theme` (discovery / fat-theme split births) never set `pct_above_20sma`, so a newborn
carried NULL until its first nightly rescore and the /themes board had nothing to show for it.
The promotion write (`_upsert_promoted_theme`) is pinned in test_promotetheme.py; the render side
in test_theme_ecosystems.py (§7). No DB, no network.
"""
from __future__ import annotations

import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import theme_engine as te

_TODAY = _dt.date(2026, 9, 30)
_STOCKS = {
    "AAA": {"rs_composite": 90.0}, "BBB": {"rs_composite": 80.0}, "CCC": {"rs_composite": 70.0},
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(te, "_news_check", AsyncMock(return_value=(20, "fresh description", False)))


@pytest.mark.asyncio
async def test_newborn_carries_breadth_from_the_rescore_function(monkeypatch):
    breadth = AsyncMock(return_value=0.667)
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20", breadth)

    born = await te._score_new_theme(
        {"name": "Fresh Cohort", "tickers": ["AAA", "BBB", "CCC"], "thesis": "t"},
        _STOCKS, _TODAY)

    assert born["pct_above_20sma"] == 0.667
    # SAME function, SAME argument shape as _rescore_existing_theme
    # (`get_ticker_breadth_above_sma20(tickers, today)`): no second breadth definition.
    breadth.assert_awaited_once_with(["AAA", "BBB", "CCC"], _TODAY)
    # nothing else about the newborn changed
    assert born["stage"] == "Nascent" and born["name"] == "Fresh Cohort"
    assert born["tickers"] == ["AAA", "BBB", "CCC"] and born["description"] == "fresh description"
    assert born["theme_date"] == _TODAY


@pytest.mark.asyncio
async def test_no_scored_members_yields_null_not_a_made_up_number(monkeypatch):
    """get_ticker_breadth_above_sma20 returns None when no member has a 20-day average yet —
    that must reach the row as NULL (the render then shows the member count and no percentage)."""
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20", AsyncMock(return_value=None))
    born = await te._score_new_theme(
        {"name": "Fresh Cohort", "tickers": ["AAA"], "thesis": "t"}, _STOCKS, _TODAY)
    assert "pct_above_20sma" in born and born["pct_above_20sma"] is None


@pytest.mark.asyncio
async def test_breadth_lookup_error_never_aborts_the_birth(monkeypatch):
    """Discovery scores every survivor inside one asyncio.gather — an exception here would
    lose the whole night's births. Breadth is display data: log, store NULL, carry on."""
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20",
                        AsyncMock(side_effect=RuntimeError("pool closed")))
    born = await te._score_new_theme(
        {"name": "Fresh Cohort", "tickers": ["AAA", "BBB"], "thesis": "t"}, _STOCKS, _TODAY)
    assert born["pct_above_20sma"] is None
    assert born["name"] == "Fresh Cohort" and born["score"] > 0


@pytest.mark.asyncio
async def test_newborn_breadth_is_persisted_by_the_save_path(monkeypatch):
    """The born dict flows into `_save_themes`, whose INSERT already binds
    `t.get("pct_above_20sma")` as the last parameter — pin that the key set at birth is the one
    it reads (so a rename of either side cannot silently re-NULL every newborn)."""
    from tests.conftest import make_mock_pool
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20", AsyncMock(return_value=0.6))
    born = await te._score_new_theme(
        {"name": "Fresh Cohort", "tickers": ["AAA", "BBB", "CCC"], "thesis": "t"},
        _STOCKS, _TODAY)

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    for helper in ("_emit_cross_run_dup_probe", "_canonicalize_theme_names", "log_audit_event"):
        monkeypatch.setattr(te, helper, AsyncMock(return_value=0))

    await te._save_themes([born])

    inserts = [c for c in conn.execute.call_args_list
               if "INSERT INTO mi_themes" in str(c.args[0])]
    assert inserts, "the newborn was never written"
    assert inserts[0].args[-1] == 0.6
