"""Regression tests for theme_engine Pass1 protect-strip logic.

Locks the BOTH_PROTECTED tiebreaker (2026-05-14 SNDK incident fix) and
the equal-size case advisor flagged as undefined-by-iteration-order.

Run: pytest tests/test_theme_engine_pass1.py -v
"""
from __future__ import annotations

import asyncio
import pytest

from agents.market_intelligence import theme_engine


@pytest.mark.asyncio
async def test_both_protected_strip_favors_larger_theme(monkeypatch):
    """SNDK 2026-05-14 case: AI Memory & Storage (8 tickers) vs new
    Front-End Interconnect (3 tickers). Both protected. Intersection
    {SNDK, ICHR, TSEM}. Larger theme should KEEP the intersection;
    smaller theme gets stripped.
    """
    audit_calls: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        audit_calls.append((event_type, summary))

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    monkeypatch.setattr(theme_engine, "_strip_commodity_contradictions", lambda t: t)

    themes = [
        {
            "name": "AI Memory & Storage",  # larger, 8 tickers
            "tickers": ["MU", "SNDK", "WDC", "STX", "MRAM", "SIMO", "ICHR", "TSEM"],
            "score": 80.0,
            "stage": "Mainstream",
        },
        {
            "name": "Semiconductor Front-End Interconnect",  # smaller, 3 tickers
            "tickers": ["SNDK", "ICHR", "TSEM"],
            "score": 79.5,
            "stage": "Mainstream",
        },
    ]
    protected_names = {"AI Memory & Storage", "Semiconductor Front-End Interconnect"}
    result = await theme_engine._merge_overlapping_themes(
        themes, stocks_by_ticker={}, protected_names=protected_names,
        sub_theme_parents={},
    )

    by_name = {t["name"]: set(t.get("tickers") or []) for t in result}
    # Larger theme keeps SNDK + ICHR + TSEM
    assert "SNDK" in by_name["AI Memory & Storage"], \
        f"AI Memory & Storage should retain SNDK; got {by_name['AI Memory & Storage']}"
    assert "ICHR" in by_name["AI Memory & Storage"]
    assert "TSEM" in by_name["AI Memory & Storage"]
    # Smaller theme has the intersection stripped
    assert "SNDK" not in by_name["Semiconductor Front-End Interconnect"]


@pytest.mark.asyncio
async def test_both_protected_equal_size_deterministic(monkeypatch):
    """Advisor flag: when both themes are protected and EQUAL size, the
    current implementation defaults to stripping from `j` (iteration-
    order) since `len(i) >= len(j)` is True at equality. Lock this
    behavior so any refactor is intentional.

    Better future behavior: alphabetically-earlier name wins. Not
    enforced today; this test locks current behavior so the change is
    explicit when made.
    """
    async def fake_audit(*args, **kwargs):
        pass

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    monkeypatch.setattr(theme_engine, "_strip_commodity_contradictions", lambda t: t)

    themes = [
        {"name": "Z Theme First In List", "tickers": ["A", "B", "C", "D", "E"],
         "score": 80.0, "stage": "Mainstream"},
        {"name": "A Theme Second In List", "tickers": ["A", "B", "C", "D", "E"],
         "score": 79.0, "stage": "Mainstream"},
    ]
    protected_names = {"Z Theme First In List", "A Theme Second In List"}
    result = await theme_engine._merge_overlapping_themes(
        themes, stocks_by_ticker={}, protected_names=protected_names,
        sub_theme_parents={},
    )

    by_name = {t["name"]: set(t.get("tickers") or []) for t in result}
    # At equal size, current code strips from j (iteration-order later).
    # "Z Theme First In List" is iterated first (i), so it KEEPS the tickers.
    # When refactored to alphabetical preference, "A Theme..." should keep.
    # Update this assertion when refactoring.
    assert by_name["Z Theme First In List"] == {"A", "B", "C", "D", "E"}, \
        "Current behavior: iteration-order i wins at equal size."
