"""#378 Phase 2 — /cost board + daily spend alarm pins.

Pins: (1) the board math (variable split, projection, flat total, headroom vs
over-budget vs no-budget); (2) the alarm's two triggers (budget cap ·
2×-median anomaly with the $1 noise floor) and its silence otherwise;
(3) render is legacy-Markdown safe (snake_case callers live inside the code
block; the one italics footer is paired).
"""
from __future__ import annotations

import re
from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import cost_board as cb


def _board(mtd=42.0, pplx=6.0, today_spend=1.5, median=1.4, budget=150.0,
           callers=None):
    return {
        "today": "2026-07-16", "mtd_variable": mtd, "mtd_perplexity": pplx,
        "mtd_claude": round(mtd - pplx, 2), "mtd_calls": 812,
        "today_spend": today_spend, "median30_daily": median,
        "projected_variable": round(mtd / 16 * 31, 2), "budget": budget,
        "flat_total": cb.FLAT_TOTAL,
        "top_callers": callers or [("theme_validation", 12.5), ("ep_judge", 9.1)],
    }


def test_render_full_board_with_budget_headroom():
    out = cb.render_cost_board(_board())
    assert "$42.00" in out and "812 calls" in out
    assert "$36.00" in out          # claude = mtd - pplx
    assert f"${cb.FLAT_TOTAL:.0f}/mo" in out
    assert "headroom" in out
    assert "Massive" in out          # the operator's open flat-subs question stays visible


def test_render_over_budget_and_no_budget():
    assert "OVER by $10.00" in cb.render_cost_board(_board(mtd=160.0, budget=150.0))
    assert "no budget set" in cb.render_cost_board(_board(budget=0.0))


def test_render_is_markdown_parity_safe():
    """Snake_case caller names must not leak bare underscores OUTSIDE the code
    block (#477 parity class). Everything dynamic sits between the ``` fences;
    the footer italics pair."""
    out = cb.render_cost_board(_board())
    in_code = False
    outside = []
    for line in out.split("\n"):
        if line.strip() == "```":
            in_code = not in_code
            continue
        if not in_code:
            outside.append(line)
    body = "\n".join(outside)
    # 7/17: the footer is PLAIN (V1 fails italics after a ``` fence) — nothing
    # outside the code block may carry any underscore at all.
    assert "_" not in body, f"bare underscore outside code block: {body!r}"


def _mock_dedupe_pool(monkeypatch, already_fired=0):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=already_fired)
    monkeypatch.setattr(cb, "get_pool", AsyncMock(return_value=pool))
    return conn


@pytest.mark.asyncio
async def test_alarm_fires_on_budget_breach(monkeypatch):
    monkeypatch.setattr(cb, "compute_cost_board",
                        AsyncMock(return_value=_board(mtd=200.0, budget=150.0)))
    _mock_dedupe_pool(monkeypatch, already_fired=0)
    audit = AsyncMock()
    monkeypatch.setattr(cb, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    fired = await cb.run_daily_spend_alarm(date(2026, 7, 16))

    assert fired is not None
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "spend_alarm_fired"
    tg.assert_awaited_once()
    assert "SPEND ALARM" in tg.await_args.args[0]


@pytest.mark.asyncio
async def test_budget_breach_fires_once_per_month(monkeypatch):
    """Review 7/17: after the first breach the alarm re-fired every weekday for
    the rest of the month. The audit log is the state — an existing this-month
    budget alarm suppresses the refire (the day-scoped anomaly is unaffected)."""
    monkeypatch.setattr(cb, "compute_cost_board",
                        AsyncMock(return_value=_board(mtd=200.0, budget=150.0)))
    _mock_dedupe_pool(monkeypatch, already_fired=1)
    audit = AsyncMock()
    monkeypatch.setattr(cb, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    fired = await cb.run_daily_spend_alarm(date(2026, 7, 16))

    assert fired is None
    tg.assert_not_awaited()


@pytest.mark.asyncio
async def test_alarm_fires_on_daily_anomaly(monkeypatch):
    monkeypatch.setattr(cb, "compute_cost_board", AsyncMock(return_value=_board(
        mtd=20.0, budget=150.0, today_spend=5.0, median=1.5)))
    audit = AsyncMock()
    monkeypatch.setattr(cb, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    fired = await cb.run_daily_spend_alarm(date(2026, 7, 16))

    assert fired is not None and "2×" in tg.await_args.args[0]


@pytest.mark.asyncio
async def test_alarm_quiet_within_budget_and_below_noise_floor(monkeypatch):
    # today 0.9 < the $1 floor even though median is tiny (2× median would trip)
    monkeypatch.setattr(cb, "compute_cost_board", AsyncMock(return_value=_board(
        mtd=20.0, budget=150.0, today_spend=0.9, median=0.1)))
    audit = AsyncMock()
    monkeypatch.setattr(cb, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    fired = await cb.run_daily_spend_alarm(date(2026, 7, 16))

    assert fired is None
    audit.assert_not_awaited()
    tg.assert_not_awaited()


@pytest.mark.asyncio
async def test_cost_handler_returns_via_base_ok(monkeypatch):
    """7/17 prod bug: the handler hand-rolled AgentResponse(agent=self.name) —
    the class has no .name (it's .agent_name via base._ok) → '/cost' 500'd on
    its FIRST live use. Pin the handler end-to-end through a real agent
    instance shape (the operator-facing command path, not just compute+render)."""
    from unittest.mock import MagicMock

    from agents.market_intelligence.agent import MarketIntelligenceAgent

    agent = MarketIntelligenceAgent.__new__(MarketIntelligenceAgent)
    agent.agent_name = "market_intelligence"
    monkeypatch.setattr(cb, "compute_cost_board", AsyncMock(return_value=_board()))
    monkeypatch.setattr(cb, "compute_cost_watchdog",
                        AsyncMock(return_value={"anomalies": [], "opportunities": []}))
    req = MagicMock()
    req.request_id = "t-1"

    resp = await agent._handle_cost_query(req)

    assert resp.success is True
    assert "COST BOARD" in resp.result
    assert "WATCHDOG" not in resp.result  # empty watchdog -> no appendix
    assert resp.agent == "market_intelligence"


@pytest.mark.asyncio
async def test_cost_handler_appends_watchdog_when_present(monkeypatch):
    """When the watchdog has something to report, /cost appends it after the
    board (still one message, appendix only when non-empty)."""
    from unittest.mock import MagicMock

    from agents.market_intelligence.agent import MarketIntelligenceAgent

    agent = MarketIntelligenceAgent.__new__(MarketIntelligenceAgent)
    agent.agent_name = "market_intelligence"
    monkeypatch.setattr(cb, "compute_cost_board", AsyncMock(return_value=_board()))
    monkeypatch.setattr(cb, "compute_cost_watchdog", AsyncMock(return_value={
        "anomalies": [{"caller": "theme_validation", "today_spend": 12.0,
                       "median30": 1.0, "mad": 0.1, "ratio": 12.0,
                       "today_calls": 40, "median_calls": 4.0,
                       "calls_ratio": 10.0, "leak_class": "call-volume (possible retry loop)"}],
        "opportunities": [],
    }))
    req = MagicMock()
    req.request_id = "t-2"

    resp = await agent._handle_cost_query(req)

    assert resp.success is True
    assert "COST BOARD" in resp.result
    assert "WATCHDOG" in resp.result
    assert "theme_validation" in resp.result
