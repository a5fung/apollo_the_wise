"""#495 (2026-07-25) — evening-brief send observability.

send_telegram_message returns False on failure without raising (never
raises — see its own docstring), so the evening brief's send outcome was
LOG-ONLY: no DB row, no alert. A same-day container restart erased the
only record, so "did tonight's 18:00 ET brief actually send?" was
unanswerable from the DB — the exact gap exposed by the 2026-07-20 false
alarm.

Fix: send_evening_briefing() (agents/market_intelligence/briefing.py) now
calls `_emit_evening_brief_outcome` right where `send_telegram_message`'s
return value is observed — success -> EVENING_BRIEF_SENT audit row;
failure -> EVENING_BRIEF_SEND_FAILED audit row + a best-effort Telegram
alert. The helper is extracted specifically so it's testable without
standing up send_evening_briefing's full DB gather (mirrors the existing
"avoids standing up the full briefing's many other DB dependencies"
rationale in tests/test_v1_closeout_status.py).

Covers: success emits EVENING_BRIEF_SENT and does not alert; failure emits
EVENING_BRIEF_SEND_FAILED and does alert; a log_audit_event failure on
either branch does not propagate out (the audit write must never suppress
a brief that otherwise sent fine, nor swallow the failure alert).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import agents.market_intelligence.briefing as briefing
from agents.market_intelligence.audit_events import (
    EVENING_BRIEF_SENT,
    EVENING_BRIEF_SEND_FAILED,
)


def test_event_constants_are_centralized_and_pinned():
    """Values are frozen — a rename here silently breaks any predicate/query
    keyed off the old string."""
    assert EVENING_BRIEF_SENT == "evening_brief_sent"
    assert EVENING_BRIEF_SEND_FAILED == "evening_brief_send_failed"


@pytest.mark.asyncio
async def test_success_emits_evening_brief_sent_and_does_not_alert(monkeypatch):
    audit_mock = AsyncMock()
    send_mock = AsyncMock()
    monkeypatch.setattr(briefing, "log_audit_event", audit_mock)
    monkeypatch.setattr(briefing, "send_telegram_message", send_mock)

    await briefing._emit_evening_brief_outcome(True, "2026-07-25", 1234)

    assert audit_mock.await_count == 1
    event_type, summary = audit_mock.await_args.args[0], audit_mock.await_args.args[1]
    assert event_type == EVENING_BRIEF_SENT
    assert "2026-07-25" in summary and "1234" in summary
    send_mock.assert_not_awaited()  # no failure alert on a successful send


@pytest.mark.asyncio
async def test_failure_emits_evening_brief_send_failed_and_alerts(monkeypatch):
    audit_mock = AsyncMock()
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(briefing, "log_audit_event", audit_mock)
    monkeypatch.setattr(briefing, "send_telegram_message", send_mock)

    await briefing._emit_evening_brief_outcome(False, "2026-07-25", 1234)

    assert audit_mock.await_count == 1
    event_type, summary = audit_mock.await_args.args[0], audit_mock.await_args.args[1]
    assert event_type == EVENING_BRIEF_SEND_FAILED
    assert "2026-07-25" in summary
    send_mock.assert_awaited_once()  # the best-effort failure alert fired
    alert_text = send_mock.await_args.args[0]
    assert "FAILED to send" in alert_text and "2026-07-25" in alert_text


@pytest.mark.asyncio
async def test_success_path_survives_audit_write_failure(monkeypatch):
    """A DB hiccup on the audit write must never propagate — the brief already
    sent fine and nothing downstream may be suppressed by this call raising."""
    monkeypatch.setattr(briefing, "log_audit_event", AsyncMock(side_effect=RuntimeError("db down")))
    send_mock = AsyncMock()
    monkeypatch.setattr(briefing, "send_telegram_message", send_mock)

    await briefing._emit_evening_brief_outcome(True, "2026-07-25", 1234)  # must not raise

    send_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_failure_path_survives_audit_write_failure_and_still_alerts(monkeypatch):
    """Even if the durable audit row itself fails to write, the best-effort
    Telegram alert must still be attempted — the audit write is not on the
    critical path for the alert."""
    monkeypatch.setattr(briefing, "log_audit_event", AsyncMock(side_effect=RuntimeError("db down")))
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(briefing, "send_telegram_message", send_mock)

    await briefing._emit_evening_brief_outcome(False, "2026-07-25", 1234)  # must not raise

    send_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_failure_path_survives_alert_send_also_failing(monkeypatch):
    """If the failure-alert send itself raises, that must still leave an
    audit row — the primary EVENING_BRIEF_SEND_FAILED write happens BEFORE
    the best-effort alert attempt, so it's durable regardless."""
    audit_mock = AsyncMock()
    monkeypatch.setattr(briefing, "log_audit_event", audit_mock)
    monkeypatch.setattr(briefing, "send_telegram_message", AsyncMock(side_effect=RuntimeError("telegram down")))

    await briefing._emit_evening_brief_outcome(False, "2026-07-25", 1234)  # must not raise

    assert audit_mock.await_count == 1
    assert audit_mock.await_args.args[0] == EVENING_BRIEF_SEND_FAILED


def test_send_evening_briefing_wires_the_outcome_helper():
    """Structural pin (mirrors test_send_evening_briefing_wraps_v1_closeout_in_try_except
    in test_v1_closeout_status.py): send_evening_briefing must route the
    send_telegram_message result through _emit_evening_brief_outcome, not
    inline log-only handling — guards against the emit silently getting
    un-wired by a future edit to this function."""
    import inspect

    src = inspect.getsource(briefing.send_evening_briefing)
    assert "success = await send_telegram_message(text, chat_id)" in src
    assert "await _emit_evening_brief_outcome(success, today_str, len(text))" in src
