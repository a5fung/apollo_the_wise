"""The #577 extension-cap watch sends only EPs the cap ALONE blocked (2026-09-28).

His trigger: "if/when we miss a real strong EP because of this". The scan checks extension before the
quality filters, so a name recorded as `extension_gate` can fail them too — SVRN 2026-09-21 (+133% in
five sessions) had a ~$367k median dollar volume against the live $1M floor and would not have been
bought with no cap at all. Those are recorded as `blocked_anyway`, not sent.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import missed_outcomes
from agents.market_intelligence.backtester import filters
from tests.conftest import make_mock_pool

_ROWS = [
    {"ticker": "SVRN", "alert_date": date(2026, 9, 21), "open_gap_pct": 0.297, "ret_5d": 0.97,
     "max_high_5d": 1.33, "skip_reason": "already up 83% in prior 5 days (extended)"},
    {"ticker": "GOOD", "alert_date": date(2026, 9, 22), "open_gap_pct": 0.15, "ret_5d": 0.8,
     "max_high_5d": 1.10, "skip_reason": "already up 60% in prior 5 days (extended)"},
]


@pytest.mark.asyncio
async def test_only_names_the_cap_alone_blocked_are_sent(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=_ROWS)
    conn.fetchval = AsyncMock(return_value=20)
    monkeypatch.setattr(missed_outcomes, "get_pool", AsyncMock(return_value=pool))

    async def fake_check(ticker, alert_date, *a, **k):
        return (False, "filter:adv_too_low: $366,743") if ticker == "SVRN" else (True, None)
    monkeypatch.setattr(filters, "check_filters", fake_check)

    out = await missed_outcomes.check_extension_cap_revisit()

    assert [n["ticker"] for n in out["names"]] == ["GOOD"]
    assert [b["ticker"] for b in out["blocked_anyway"]] == ["SVRN"]
    assert out["blocked_anyway"][0]["also_blocked_by"].startswith("filter:adv_too_low")
    assert out["error"] is None


@pytest.mark.asyncio
async def test_a_failing_filter_lookup_is_counted_not_raised(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=_ROWS[:1])
    conn.fetchval = AsyncMock(return_value=20)
    monkeypatch.setattr(missed_outcomes, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(filters, "check_filters", AsyncMock(side_effect=RuntimeError("db down")))
    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", AsyncMock())

    out = await missed_outcomes.check_extension_cap_revisit()

    assert out["names"] == []
    assert "RuntimeError" in (out["error"] or "")
