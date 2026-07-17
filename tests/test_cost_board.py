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
    # the footer is _..._ (paired); strip paired italics then check for strays
    stripped = re.sub(r"_[^_]*_", "", body)
    assert "_" not in stripped, f"bare underscore outside code block: {body!r}"


@pytest.mark.asyncio
async def test_alarm_fires_on_budget_breach(monkeypatch):
    monkeypatch.setattr(cb, "compute_cost_board",
                        AsyncMock(return_value=_board(mtd=200.0, budget=150.0)))
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
