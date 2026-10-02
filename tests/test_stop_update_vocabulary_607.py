"""#607 (2026-09-04) — split `stop_update_failed` at the raise site.

Before this fix, `update_stop` (broker/order_manager.py) logged
`stop_update_failed` at BOTH the transient attempt-1 place_stop_order failure
(the #433 OTO-leg-vs-refresh class — a 3s retry usually wins, protection never
lapses) and the genuinely terminal both-attempts-failed case (position naked).
One raw type meant every reader had to re-derive "was this the transient one?"
from the `attempt` field in `detail` — and one reader (agent.py's /trade
timeline, see test_trade_query_stop_recovered_607.py) never did, rendering a
healthy self-heal as an open alarm (AMLX 2026-08-24..28).

This pins the RAISE SITE itself: attempt-1 now logs `stop_update_retry_triggered`
(never `stop_update_failed`), and `stop_update_failed` fires ONLY when the
retry also fails. The retry mechanism's own behavior (timing, when a stop is
placed, the raise-only floor) is untouched — these tests assert vocabulary
only, reusing the exact mock harness `test_stop_reason_560.py` already
established for this function.
"""
from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

TRADE_ID = 307
TICKER = "PLTR"
OLD_STOP = 149.05
NEW_STOP = 150.15


def _trade(**overrides):
    t = {
        "id": TRADE_ID, "ticker": TICKER, "remaining_shares": 4,
        "stop_price": OLD_STOP, "stop_order_id": "old_leg_id",
        "account_mode": "live", "signal_type": "magna53",
        "entry_price": 149.05, "hard_stop": 143.28,
    }
    t.update(overrides)
    return t


def _make_pool(trade):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=trade)
    conn.fetchval = AsyncMock(return_value=0)  # get_pending_exit_qty -> 0 held
    conn.execute = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool


@pytest.mark.asyncio
async def test_attempt_1_fails_retry_succeeds_logs_retry_triggered_never_failed():
    """The #433 self-heal shape: first place_stop_order raises, the 3s retry
    wins. Must log `stop_update_retry_triggered` (not `stop_update_failed`)
    for the transient half, then `stop_update_retry_succeeded` — and must
    NEVER log `stop_update_failed` anywhere in this run."""
    import agents.market_intelligence.broker.order_manager as om

    trade = _trade()
    pool = _make_pool(trade)
    audit = AsyncMock()

    place_calls = {"n": 0}

    async def _place_fake(**kwargs):
        place_calls["n"] += 1
        if place_calls["n"] == 1:
            raise RuntimeError("insufficient qty available for order")
        return {"id": "new-stop-id", "status": "accepted"}

    async def _get_order_fake(order_id, account_mode=None):
        return {"id": order_id, "status": "accepted", "stop_price": OLD_STOP}

    with ExitStack() as stack:
        for p in [
            patch.object(om, "get_pool", AsyncMock(return_value=pool)),
            patch.object(om, "log_audit_event", audit),
            patch.object(om, "send_telegram_message", AsyncMock(return_value=True)),
            patch.object(om, "set_stop_order_id", AsyncMock()),
            patch.object(om.asyncio, "sleep", AsyncMock()),
            patch.object(om.alpaca, "get_order", _get_order_fake),
            patch.object(om.alpaca, "cancel_order", AsyncMock(return_value=True)),
            patch.object(om.alpaca, "place_stop_order", _place_fake),
            patch.object(om.alpaca, "make_client_order_id",
                         lambda m, s, t: f"apollo_{m}_{s}_{t}_x"),
        ]:
            stack.enter_context(p)

        ok = await om.update_stop(TRADE_ID, NEW_STOP, stop_source="trail")

    assert ok is True
    logged_types = [c.args[0] for c in audit.call_args_list]
    assert "stop_update_failed" not in logged_types, (
        f"a self-healed attempt-1 must never log the terminal type: {logged_types}")
    assert "stop_update_retry_triggered" in logged_types, (
        f"the transient attempt-1 failure must log the new type: {logged_types}")
    assert "stop_update_retry_succeeded" in logged_types
    # ORDER matters: the transient marker fires before the recovery confirms.
    assert logged_types.index("stop_update_retry_triggered") < logged_types.index(
        "stop_update_retry_succeeded")

    # The transient row's detail still carries attempt=1 (the dated-bridge
    # readers key off this for pre-rename rows; new rows don't need it, but
    # nothing should have dropped the field).
    triggered_call = next(c for c in audit.call_args_list if c.args[0] == "stop_update_retry_triggered")
    import json as _json
    detail = _json.loads(triggered_call.args[2])
    assert detail["attempt"] == 1


@pytest.mark.asyncio
async def test_both_attempts_fail_logs_terminal_stop_update_failed():
    """The genuinely-naked case: both placements raise. Must log
    `stop_update_retry_triggered` for attempt 1, then the TERMINAL
    `stop_update_failed` (attempt=2) — the type readers key off as the real
    alarm — and must clear the stop pointer + Telegram the naked alert."""
    import agents.market_intelligence.broker.order_manager as om

    trade = _trade()
    pool = _make_pool(trade)
    audit = AsyncMock()
    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    async def _place_always_fails(**kwargs):
        raise RuntimeError("insufficient qty available for order")

    async def _get_order_fake(order_id, account_mode=None):
        return {"id": order_id, "status": "accepted", "stop_price": OLD_STOP}

    set_stop = AsyncMock()

    with ExitStack() as stack:
        for p in [
            patch.object(om, "get_pool", AsyncMock(return_value=pool)),
            patch.object(om, "log_audit_event", audit),
            patch.object(om, "send_telegram_message", _capture),
            patch.object(om, "set_stop_order_id", set_stop),
            patch.object(om.asyncio, "sleep", AsyncMock()),
            patch.object(om.alpaca, "get_order", _get_order_fake),
            patch.object(om.alpaca, "cancel_order", AsyncMock(return_value=True)),
            patch.object(om.alpaca, "place_stop_order", _place_always_fails),
            patch.object(om.alpaca, "make_client_order_id",
                         lambda m, s, t: f"apollo_{m}_{s}_{t}_x"),
        ]:
            stack.enter_context(p)

        ok = await om.update_stop(TRADE_ID, NEW_STOP, stop_source="trail")

    assert ok is False
    logged_types = [c.args[0] for c in audit.call_args_list]
    assert logged_types.count("stop_update_retry_triggered") == 1
    assert "stop_update_failed" in logged_types, (
        f"both attempts failing must still log the terminal type: {logged_types}")
    failed_call = next(c for c in audit.call_args_list if c.args[0] == "stop_update_failed")
    import json as _json
    detail = _json.loads(failed_call.args[2])
    assert detail["attempt"] == 2

    # Pointer cleared for sync_positions remediation, and the operator was
    # alerted LOUD — unchanged mechanism, just pinning it survives the split.
    set_stop.assert_awaited_once()
    assert set_stop.call_args.kwargs["reason"] == "stop_update_failed"
    assert any("STOP FAILED" in m for m in sent)
