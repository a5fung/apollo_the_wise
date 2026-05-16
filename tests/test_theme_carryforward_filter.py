"""Tests for _apply_carryforward_deterministic_filter (2026-05-15).

Regression: the 4 oncology biotechs (RVMD/AVBP/DAWN/AJRD) cycling through
Satellite-named themes for ~3 weeks despite Fix B global ban + validation
cooldowns. Filter closes the adds/removes asymmetry: deterministic removes
(banned/cooldown/outlier) now run daily against carryforward members.

Critical invariant under test: STRIP-ONLY behavior. Themes with 0 members
after strip must PERSIST in the list (not retired). Retirement is handled
by the existing post-assignment logic so assignment LLM gets a chance to
refill the theme.
"""
from __future__ import annotations

import pytest

from agents.market_intelligence import theme_engine


@pytest.mark.asyncio
async def test_strips_all_banned_members_does_not_retire(monkeypatch):
    """SATELLITE BIOTECH CASE: a theme with 4 banned members should have all
    4 stripped, but the theme MUST persist in the list (zero members) so
    assignment LLM can refill it in the same run."""
    audit_calls: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        audit_calls.append((event_type, summary))

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Satellite Earth Observation & Geospatial Intelligence",
            "tickers": ["RVMD", "AVBP", "DAWN", "AJRD"],
            "score": 79.5,
            "stage": "Mainstream",
        },
    ]
    globally_banned = {"RVMD", "AVBP", "DAWN", "AJRD"}
    cooldown_set: set[tuple[str, str]] = set()
    stocks_by_ticker: dict = {}

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, globally_banned, cooldown_set, stocks_by_ticker,
    )

    assert stripped == 4
    # Theme still in the list (NOT retired) — critical retire-deferral
    assert len(themes) == 1
    # All members stripped
    assert themes[0]["tickers"] == []
    # Audit event fired
    assert any(e[0] == "theme_carryforward_filter_stripped" for e in audit_calls)


@pytest.mark.asyncio
async def test_partial_strip_preserves_other_members(monkeypatch):
    """Theme with mixed members: only banned/cooldown should be stripped."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "AI Memory & Storage",
            "tickers": ["MU", "SNDK", "WDC", "BANNED_X", "STX"],
            "score": 80.0,
            "stage": "Mainstream",
        },
    ]
    globally_banned = {"BANNED_X"}
    cooldown_set: set[tuple[str, str]] = set()
    stocks_by_ticker: dict = {}

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, globally_banned, cooldown_set, stocks_by_ticker,
    )

    assert stripped == 1
    assert "BANNED_X" not in themes[0]["tickers"]
    # Other members preserved
    assert {"MU", "SNDK", "WDC", "STX"}.issubset(set(themes[0]["tickers"]))


@pytest.mark.asyncio
async def test_cooldown_pair_strip(monkeypatch):
    """(ticker, theme_name) cooldown should strip even if ticker not globally banned."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Theme A",
            "tickers": ["X", "Y", "Z"],
            "score": 70.0,
            "stage": "Accelerating",
        },
        {
            "name": "Theme B",
            "tickers": ["X", "W"],
            "score": 70.0,
            "stage": "Accelerating",
        },
    ]
    globally_banned: set[str] = set()
    # X is cooled-down only for Theme A, not Theme B
    cooldown_set = {("X", "Theme A")}
    stocks_by_ticker: dict = {}

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, globally_banned, cooldown_set, stocks_by_ticker,
    )

    assert stripped == 1
    assert themes[0]["tickers"] == ["Y", "Z"]  # X stripped from Theme A
    assert "X" in themes[1]["tickers"]          # X remains in Theme B


@pytest.mark.asyncio
async def test_sector_outlier_strip(monkeypatch):
    """Singleton-sector members in a ≥3 member theme should be stripped."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Semiconductors",
            "tickers": ["NVDA", "AMD", "INTC", "JPM"],  # JPM is the outlier
            "score": 75.0,
            "stage": "Mainstream",
        },
    ]
    stocks_by_ticker = {
        "NVDA": {"sector": "Technology"},
        "AMD": {"sector": "Technology"},
        "INTC": {"sector": "Technology"},
        "JPM": {"sector": "Financial Services"},
    }

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), stocks_by_ticker,
    )

    assert stripped == 1
    assert "JPM" not in themes[0]["tickers"]
    assert set(themes[0]["tickers"]) == {"NVDA", "AMD", "INTC"}


@pytest.mark.asyncio
async def test_noop_when_no_violations(monkeypatch):
    """Clean theme: no strips, no audit events."""
    audit_calls: list = []

    async def fake_audit(*a, **kw):
        audit_calls.append(a)

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Clean Theme",
            "tickers": ["A", "B", "C"],
            "score": 70.0,
            "stage": "Accelerating",
        },
    ]
    stocks_by_ticker = {
        "A": {"sector": "Tech"},
        "B": {"sector": "Tech"},
        "C": {"sector": "Tech"},
    }

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), stocks_by_ticker,
    )

    assert stripped == 0
    assert themes[0]["tickers"] == ["A", "B", "C"]
    assert len(audit_calls) == 0


@pytest.mark.asyncio
async def test_sector_outlier_skipped_for_small_themes(monkeypatch):
    """Themes with <3 members don't trigger sector outlier strip
    (insufficient data to define a majority)."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Small Theme",
            "tickers": ["NVDA", "JPM"],
            "score": 70.0,
            "stage": "Nascent",
        },
    ]
    stocks_by_ticker = {
        "NVDA": {"sector": "Technology"},
        "JPM": {"sector": "Financial Services"},
    }

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), stocks_by_ticker,
    )

    assert stripped == 0
    assert set(themes[0]["tickers"]) == {"NVDA", "JPM"}
