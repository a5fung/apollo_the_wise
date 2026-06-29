"""/promotetheme — operator single-candidate theme promotion (theme_engine.promote_candidate_by_name).

The promoted theme is written exactly like the nightly auto-promote (source='shadow_promoted') and then
behaves like ANY other theme (operator 6/29: no special treatment — daily discovery re-writes it while
the cohort co-moves; the 7d recency cap ages it out if it dissolves). These pin the lookup branches +
the write.
"""
import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import theme_engine as te
from agents.market_intelligence import db as dbmod

_TODAY = _dt.date(2026, 6, 29)


def _cand(name, tickers, thesis="thesis", source="rs_slope_synthesis"):
    return {"name": name, "tickers": list(tickers), "thesis": thesis, "source": source}


@pytest.mark.asyncio
async def test_not_found_lists_available(monkeypatch):
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates",
                        AsyncMock(return_value=[_cand("Rare Biotech", ["A", "B", "C"])]))
    res = await te.promote_candidate_by_name("nonexistent xyz", _TODAY)
    assert res["status"] == "not_found"
    assert "Rare Biotech" in res["available"]


@pytest.mark.asyncio
async def test_too_few_members(monkeypatch):
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates",
                        AsyncMock(return_value=[_cand("Tiny", ["A", "B"])]))
    res = await te.promote_candidate_by_name("tiny", _TODAY)
    assert res["status"] == "too_few"
    assert res["n_members"] == 2


@pytest.mark.asyncio
async def test_ambiguous_substring(monkeypatch):
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand("Rare Metals", ["A", "B", "C"]), _cand("Rare Pharma", ["D", "E", "F"])]))
    res = await te.promote_candidate_by_name("rare", _TODAY)
    assert res["status"] == "ambiguous"
    assert len(res["matches"]) == 2


@pytest.mark.asyncio
async def test_promoted_writes_shadow_promoted(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])          # RS-lookup → empty (rs_avg None)
    conn.fetchrow = AsyncMock(return_value=None)     # no prior days_active
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand("Rare & Orphan Biotech Re-Rating", ["RARE", "MIRM", "RGNX", "AGIO"])]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))   # no rename
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())

    res = await te.promote_candidate_by_name("rare orphan", _TODAY)

    assert res["status"] == "promoted"
    assert res["name"] == "Rare & Orphan Biotech Re-Rating"
    assert res["n_members"] == 4
    assert res["canonicalized"] is False
    # the live write fired with the auto-promote's source (behaves like any other theme)
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO mi_themes" in sql
    assert "'shadow_promoted'" in sql


@pytest.mark.asyncio
async def test_noop_when_guard_skips_live_theme(monkeypatch):
    # ON CONFLICT WHERE source='shadow_promoted' skips a native live theme → "INSERT 0 0" → noop
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 0")
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand("Already Live", ["X", "Y", "Z"])]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())

    res = await te.promote_candidate_by_name("already live", _TODAY)
    assert res["status"] == "noop"
