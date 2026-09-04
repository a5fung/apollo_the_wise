"""#607 (2026-09-04) — `/trade TICKER` must render a self-healed stop update as
RECOVERED, not FAILED.

`stop_update_failed` used to fire at BOTH the transient attempt-1
place_stop_order failure (order_manager.py's #433 retry-in-3s class — usually
wins, protection never lapses) AND the genuinely terminal both-attempts-failed
case. `/trade`'s STOPS section rendered every row of that type as
"⚠️ update FAILED" with no counterpart row to contradict it — a healthy
self-heal read as an open alarm. AMLX 2026-08-24..28: 5 of 5 "failures" were
retries that won, and the trade closed +$62.92 with the stop exactly where the
trail wanted it, yet `/trade AMLX` told the operator its stop update failed.

The fix splits the type at the raise site (`stop_update_retry_triggered` for
the transient case, `stop_update_failed` reserved for the terminal one) and
adds a DATED BRIDGE here for rows written before the rename, which still carry
the old overloaded `stop_update_failed` name and must be told apart by their
own `detail.attempt` field.

These tests exercise the real `_handle_trade_query` handler end to end (DB
mocked, matching every other handler test in this suite) and assert on the
literal rendered string — the operator-facing surface, not the DB rows.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from agents.market_intelligence.agent import MarketIntelligenceAgent
from shared.models import AgentRequest
from tests.conftest import make_mock_pool


def _utc(y, m, d, hh, mm, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


def _trade_row(**over):
    row = {
        "id": 9001, "ticker": "AMLX", "alert_date": date(2026, 8, 24),
        "status": "closed", "entry_price": 25.00, "stop_price": 25.40,
        "entry_shares": 100, "remaining_shares": 0, "total_pnl": 62.92,
        "hold_days": 4,
        "exits": json.dumps([{
            "time": "2026-08-28T15:50:00", "price": 25.75, "shares": 100,
            "reason": "trail_stop", "pnl": 62.92,
        }]),
        "closed_at": _utc(2026, 8, 28, 19, 50),
        "entry_attempt": 1,
    }
    row.update(over)
    return row


def _entry_order():
    return {
        "id": 1, "alpaca_order_id": "buy-1", "side": "buy", "order_type": "stop_limit",
        "qty": 100, "filled_qty": 100, "filled_avg_price": 25.00, "status": "filled",
        "purpose": "entry", "exit_reason": None,
        "stop_price": 24.90, "limit_price": 25.05,
        "submitted_at": _utc(2026, 8, 24, 13, 31), "filled_at": _utc(2026, 8, 24, 13, 31, 20),
        "cancelled_at": None,
    }


def _wire(monkeypatch, *, trade, orders, events):
    """Stub the handler's DB surface (mirrors test_why_catalyst_grade_593.py::_wire).
    `_handle_trade_query` has its OWN locally-nested `_send_plain_with_keyboard`
    (does not use the module-level #178 helper), so it isn't independently
    monkeypatchable — it reads TELEGRAM_BOT_TOKEN directly and returns False
    when unset, which is already true in this test environment, sending the
    body back to us as `result` instead of over the wire.
    """
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=trade)
    conn.fetch = AsyncMock(side_effect=[orders, events])
    monkeypatch.setattr("agents.market_intelligence.db.get_pool",
                        AsyncMock(return_value=pool))
    monkeypatch.setattr("agents.market_intelligence.db.get_security_exchange_map",
                        AsyncMock(return_value={}))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)


def _render(request_task="/trade AMLX"):
    agent = MarketIntelligenceAgent()
    res = asyncio.run(agent._handle_trade_query(
        AgentRequest(task=request_task, user_id=1, conversation_id="t")))
    return res.result if hasattr(res, "result") else res["result"]


def test_amlx_five_self_healed_stops_render_as_recovered_not_failed(monkeypatch):
    """The exact AMLX shape from the PLAN.md #607 line: 5 attempt-1 failures,
    each paired with a stop_update_retry_succeeded 3s later. None of them
    should render as FAILED."""
    events = []
    price = 24.90
    for dom in (24, 25, 26, 27, 28):
        price += 0.10
        events.append({
            "created_at": _utc(2026, 8, dom, 14, 5, 0), "event_type": "stop_update_failed",
            "summary": "AMLX: place_stop_order raised on first attempt — APIError — retrying in 3s",
            "detail": json.dumps({
                "trade_id": 9001, "ticker": "AMLX", "new_stop_price": price,
                "attempt": 1, "old_cancel_ok": True, "error": "APIError: insufficient qty",
            }),
        })
        events.append({
            "created_at": _utc(2026, 8, dom, 14, 5, 3), "event_type": "stop_update_retry_succeeded",
            "summary": f"AMLX: retry placed stop @${price:.2f}",
            "detail": json.dumps({"trade_id": 9001, "ticker": "AMLX", "new_stop_price": price}),
        })

    _wire(monkeypatch, trade=_trade_row(), orders=[_entry_order()], events=events)
    body = _render()

    assert "⚠️ update FAILED" not in body, (
        f"a self-healed stop update rendered as FAILED — the #607 bug is back:\n{body}")
    assert body.count("✅ update recovered") == 5, (
        f"expected all 5 self-healed rows to render as recovered:\n{body}")
    assert "$+62.92" in body


def test_pre_rename_terminal_stop_failure_still_renders_as_failed(monkeypatch):
    """Negative case: a pre-rename `stop_update_failed` row whose `detail.attempt`
    is 2 (both retry placements failed — the genuinely-naked terminal case) must
    NOT be swept into the recovered bridge. The fix must not turn a real alarm
    into silence."""
    events = [{
        "created_at": _utc(2026, 8, 26, 14, 5, 3), "event_type": "stop_update_failed",
        "summary": "AMLX: retry also failed — position naked, APIError",
        "detail": json.dumps({
            "trade_id": 9001, "ticker": "AMLX", "new_stop_price": 25.20,
            "attempt": 2, "old_cancel_ok": True,
            "error_first": "APIError", "error_retry": "APIError",
        }),
    }]
    _wire(monkeypatch, trade=_trade_row(), orders=[_entry_order()], events=events)
    body = _render()

    assert "⚠️ update FAILED" in body, f"a genuine terminal stop failure was hidden:\n{body}"
    assert "✅ update recovered" not in body


def test_unreadable_detail_fails_toward_the_alarm_not_silence(monkeypatch):
    """If `detail` can't be parsed, the fail direction must be COUNT IT AS A
    FAILURE (same rule system_review.py's _recovered uses) — an unreadable row
    must never buy silence on the stop path."""
    events = [{
        "created_at": _utc(2026, 8, 26, 14, 5, 3), "event_type": "stop_update_failed",
        "summary": "AMLX: place_stop_order raised on first attempt — APIError",
        "detail": "not valid json{{{",
    }]
    _wire(monkeypatch, trade=_trade_row(), orders=[_entry_order()], events=events)
    body = _render()

    assert "⚠️ update FAILED" in body
    assert "✅ update recovered" not in body


def test_new_vocabulary_retry_succeeded_alone_renders_as_recovered(monkeypatch):
    """Going forward, the transient half never even reaches this query (it logs as
    `stop_update_retry_triggered`, not selected here) — only the confirmation row
    shows up, and it must render as recovered."""
    events = [{
        "created_at": _utc(2026, 8, 26, 14, 5, 3), "event_type": "stop_update_retry_succeeded",
        "summary": "AMLX: retry placed stop @$25.20",
        "detail": json.dumps({"trade_id": 9001, "ticker": "AMLX", "new_stop_price": 25.20}),
    }]
    _wire(monkeypatch, trade=_trade_row(), orders=[_entry_order()], events=events)
    body = _render()

    assert "✅ update recovered" in body
    assert "⚠️ update FAILED" not in body
