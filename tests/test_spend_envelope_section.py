"""FL-6 / #378 S-C — the weekly-review cost-envelope appendix (deterministic MTD spend)."""
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool
from agents.market_intelligence import system_review as sr


def _setup(monkeypatch, total, callers, budget="10"):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=total)
    conn.fetch = AsyncMock(return_value=callers)
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", AsyncMock(return_value=pool))
    monkeypatch.setenv("ANTHROPIC_MONTHLY_BUDGET", budget)
    return conn


@pytest.mark.asyncio
async def test_over_budget_flags_red(monkeypatch):
    _setup(monkeypatch, {"calls": 903, "cost": 11.75},
           [{"caller": "perplexity_news_search", "cost": 3.42},
            {"caller": "ep_grade_judge", "cost": 3.26}], budget="10")
    out = await sr._spend_envelope_section()
    assert "Cost envelope (MTD)" in out
    assert "$11.75 / $10 (118%)" in out and "🔴 OVER" in out
    assert "perplexity news search: $3.42" in out
    assert "fixed infra/data subs" in out           # the honesty note


@pytest.mark.asyncio
async def test_under_budget_ok_check(monkeypatch):
    _setup(monkeypatch, {"calls": 100, "cost": 4.0}, [], budget="10")
    out = await sr._spend_envelope_section()
    assert "$4.00 / $10 (40%) ✓" in out


@pytest.mark.asyncio
async def test_near_budget_amber(monkeypatch):
    _setup(monkeypatch, {"calls": 200, "cost": 8.5}, [], budget="10")
    out = await sr._spend_envelope_section()
    assert "(85%) 🟠" in out


@pytest.mark.asyncio
async def test_no_budget_prompts_to_set_one(monkeypatch):
    _setup(monkeypatch, {"calls": 50, "cost": 2.0}, [], budget="0")
    out = await sr._spend_envelope_section()
    assert "no budget set" in out and "$2.00" in out


@pytest.mark.asyncio
async def test_empty_meter_never_crashes(monkeypatch):
    _setup(monkeypatch, {"calls": 0, "cost": 0}, [], budget="10")
    out = await sr._spend_envelope_section()
    assert "$0.00 / $10 (0%)" in out
