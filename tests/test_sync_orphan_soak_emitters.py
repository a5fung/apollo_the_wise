"""RED-2 follow-up (2026-07-12): durable soak-visible emitters at the two
TERMINAL orphan-naked sites in sync_positions.

A prior red-team flagged that some terminal "position stays naked" paths fire
only a Telegram/digest CRITICAL and write NO durable audit row — so the FL-1
soak (scripts/v1_closeout_status.py::SOAK_FAILURE_EVENT_TYPES) counted a
hands-fixed-intraday naked day as CLEAN. The two sync_positions orphan shapes
run at 4:05 PM / 9:00 PM ET — OUTSIDE the stop-ack watchdog's 9:00-16:00
window — so nothing else emits a durable marker the same day:

  1. Orphaned position with NO stop anchor (no stop_price / orb_low in DB) —
     nothing automated can EVER protect it            → stop_ack_remediation_failed
  2. Orphan stop remediation failed after 3 attempts  → stop_ack_remediation_failed

These tests drive both terminal paths and assert the durable emit, plus a
self-healed (transient) control that must NOT emit — a false emit would
falsely reset the v1 soak (RED-2 discipline).

Also frozen here: the emitted summary must NOT start with the
"{ticker} #{trade_id}" prefix — scheduler._stop_ack_timeout_watchdog_job
dedups its own remediation attempts on `summary LIKE '{ticker} #{trade_id}%'`
across the same event types, and the new observability rows must not suppress
the watchdog's real remediation attempt (that would be a control-flow change
through data).
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

MODULE = "agents.market_intelligence.broker.order_manager"

SOAK_EVENT = "stop_ack_remediation_failed"
SOAK_EVENTS = {"stop_ack_remediation_failed", "naked_position_remediation_failed"}


def _make_db_trade(trade_id, ticker, remaining=100, stop_price=None, orb_low=None):
    """Filled trade, live at broker, DB stop pointer NULL (orphan-loop shape)."""
    return {
        "id": trade_id, "ticker": ticker,
        "remaining_shares": remaining, "entry_price": 100.0,
        "status": "filled", "stop_order_id": None,
        "stop_price": stop_price, "orb_low": orb_low,
        "signal_type": "magna53",
    }


def _stub_pool(db_trades):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=db_trades)
    conn.execute = AsyncMock()
    return pool, conn


def _run_sync(db_trades, alpaca_positions, audit_calls, place_stop):
    """Patch-context builder: everything _sync_positions_for_mode touches on
    the orphan path, with adopt → None (no broker stop to adopt) and the #151
    coverage invariant stubbed out (its own tests cover it)."""

    async def _audit(event_type, summary="", detail=""):
        audit_calls.append((event_type, summary, detail))

    pool, _conn = _stub_pool(db_trades)
    return patch.multiple(
        MODULE,
        get_pool=AsyncMock(return_value=pool),
        log_audit_event=_audit,
        _try_adopt_existing_stop=AsyncMock(return_value=None),
        get_pending_exit_qty=AsyncMock(return_value=0),
        set_stop_order_id=AsyncMock(),
        _ensure_stop_coverage=AsyncMock(return_value=None),
        send_telegram_message=AsyncMock(return_value=True),
    ), patch(
        f"{MODULE}.alpaca.get_all_positions",
        new=AsyncMock(return_value=alpaca_positions),
    ), patch(
        f"{MODULE}.alpaca.place_stop_order",
        new=place_stop,
    ), patch(
        f"{MODULE}.asyncio.sleep",  # skip the 2s/4s remediation backoff
        new=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_orphan_no_anchor_emits_soak_failure():
    """TERMINAL shape 1: filled at broker, no live/adoptable stop, and no
    stop_price/orb_low anchor in DB — nothing automated can protect it.
    Previously digest+log only; must now write the durable soak marker."""
    from agents.market_intelligence.broker.order_manager import _sync_positions_for_mode

    audit_calls = []
    place_stop = AsyncMock()  # must NOT be reached — no anchor to place at
    patches = _run_sync(
        [_make_db_trade(431, "WULF", stop_price=None, orb_low=None)],
        [{"symbol": "WULF", "qty": 100}],
        audit_calls, place_stop,
    )
    p1, p2, p3, p4 = patches
    with p1, p2, p3, p4:
        discrepancies = await _sync_positions_for_mode("live")

    emits = [c for c in audit_calls if c[0] == SOAK_EVENT]
    assert len(emits) == 1, f"expected 1 {SOAK_EVENT}, got {audit_calls}"
    _, summary, detail = emits[0]
    payload = json.loads(detail)
    assert payload["trade_id"] == 431
    assert payload["ticker"] == "WULF"
    assert payload["reason"] == "no_stop_anchor"
    assert payload["account_mode"] == "live"
    # Watchdog-dedup non-collision: must not look like "WULF #431..."
    assert not summary.startswith("WULF #431"), (
        "summary matches the stop-ack watchdog dedup prefix — would suppress "
        "the watchdog's own remediation attempt (control-flow change)"
    )
    # Existing control flow untouched: no placement attempted (no anchor),
    # and the operator digest line still present.
    place_stop.assert_not_awaited()
    assert any("Orphaned position WULF" in d for d in discrepancies)


@pytest.mark.asyncio
async def test_orphan_remediation_3_attempts_failed_emits_soak_failure():
    """TERMINAL shape 2: anchor exists but all 3 place_stop_order attempts
    raise — loop gives up, position stays naked until hands or a much-later
    pass. Previously digest+log only; must now write the durable soak marker."""
    from agents.market_intelligence.broker.order_manager import _sync_positions_for_mode

    audit_calls = []
    place_stop = AsyncMock(side_effect=RuntimeError("alpaca 500"))
    patches = _run_sync(
        [_make_db_trade(432, "CRMD", stop_price=95.0)],
        [{"symbol": "CRMD", "qty": 100}],
        audit_calls, place_stop,
    )
    p1, p2, p3, p4 = patches
    with p1, p2, p3, p4:
        discrepancies = await _sync_positions_for_mode("live")

    emits = [c for c in audit_calls if c[0] == SOAK_EVENT]
    assert len(emits) == 1, f"expected 1 {SOAK_EVENT}, got {audit_calls}"
    _, summary, detail = emits[0]
    payload = json.loads(detail)
    assert payload["trade_id"] == 432
    assert payload["ticker"] == "CRMD"
    assert payload["reason"] == "place_stop_failed_3_attempts"
    assert "RuntimeError" in payload["error"]
    assert not summary.startswith("CRMD #432"), (
        "summary matches the stop-ack watchdog dedup prefix"
    )
    # Existing remediation logic untouched: still exactly 3 attempts, still
    # the digest line.
    assert place_stop.await_count == 3
    assert any("after 3 attempts" in d for d in discrepancies)


@pytest.mark.asyncio
async def test_orphan_remediation_success_is_transient_no_soak_emit():
    """SELF-HEALED control: remediation stop places fine on attempt 1 — the
    day ran clean and NO soak-failure event may be written (a false emit
    would falsely reset the FL-1 soak; RED-2 discipline)."""
    from agents.market_intelligence.broker.order_manager import _sync_positions_for_mode

    audit_calls = []
    place_stop = AsyncMock(return_value={"id": "new-stop-id", "status": "accepted"})
    patches = _run_sync(
        [_make_db_trade(433, "FPS", stop_price=95.0)],
        [{"symbol": "FPS", "qty": 100}],
        audit_calls, place_stop,
    )
    p1, p2, p3, p4 = patches
    with p1, p2, p3, p4:
        discrepancies = await _sync_positions_for_mode("live")

    bad = [c for c in audit_calls if c[0] in SOAK_EVENTS]
    assert bad == [], f"self-healed remediation must not emit soak failures: {bad}"
    assert place_stop.await_count == 1
    assert any("Orphaned stop remediated" in d for d in discrepancies)


@pytest.mark.asyncio
async def test_orphan_adopted_broker_stop_is_transient_no_soak_emit():
    """SELF-HEALED control 2: the broker already had a covering stop the DB
    lost track of — adopt path (pure DB write). Not naked at any point; NO
    soak-failure event may be written."""
    from agents.market_intelligence.broker.order_manager import _sync_positions_for_mode

    audit_calls = []
    place_stop = AsyncMock()
    patches = _run_sync(
        [_make_db_trade(434, "QURE", stop_price=95.0)],
        [{"symbol": "QURE", "qty": 100}],
        audit_calls, place_stop,
    )
    p1, p2, p3, p4 = patches
    with p1, p2, p3, p4, patch(
        f"{MODULE}._try_adopt_existing_stop",
        new=AsyncMock(return_value="df9ff732-adopted"),
    ):
        discrepancies = await _sync_positions_for_mode("live")

    bad = [c for c in audit_calls if c[0] in SOAK_EVENTS]
    assert bad == [], f"adopted-stop path must not emit soak failures: {bad}"
    place_stop.assert_not_awaited()
    assert any("Adopted existing broker stop" in d for d in discrepancies)
