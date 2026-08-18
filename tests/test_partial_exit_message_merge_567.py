"""#567 (2026-08-18) — merge the three partial-exit Telegrams into one.

Operator got three separate messages for ONE AMLX +2R partial exit: the profit-
trigger notice (order_manager.scan_profit_triggers), the #566 OCO carve-out
notice (order_manager.execute_partial_exit Step 3), and the WS safety-net
"Stop replaced" (trade_stream._handle_cancel_or_reject) confirming the
remaining shares' breakeven stop. Asked: "these 3 msgs can be merged into one?"

Design (see order_manager.py / trade_stream.py comments for the full reasoning):
  - AUTHOR = execute_partial_exit's Step 3. scan_profit_triggers hands it the
    trigger facts via a `trigger` dict; Step 3 folds them into its own message
    (trigger + sale + protection + the confirmed breakeven-stop fact) and sets
    trigger["delivered"] = True right before sending.
  - scan_profit_triggers speaks its OWN fallback only when `delivered` is still
    False afterward (paused / circuit-open / any abort before Step 3) — never
    silently drops the trigger fact.
  - trade_stream's WS safety-net extends the #561 `_agrees` idiom: a NEW audit
    event type, `partial_exit_stop_telegram_pending`, written by
    execute_partial_exit ONLY when `trigger` was given and the breakeven stop
    is CONFIRMED live — same shape (trade_id/new_stop_id/new_stop_price) as
    the existing `stop_update_retry_succeeded` evidence, so the Python match
    logic is untouched; only the SQL event_type filter widens.
  - Gated on `trigger is not None`: agent.py's /partialnow and live_tracker.py's
    partials render Step 3 byte-identical to before this change and write NO
    evidence row — the WS safety net stays their only notice, unchanged.

This file pins, behaviourally (real functions against faked alpaca client +
faked db pool/WS payloads, not source-grepped):
  A. execute_partial_exit: one merged Telegram carries all five required
     facts and marks `trigger["delivered"] = True`; writes the new evidence
     row ONLY when trigger is given.
  B. scan_profit_triggers: suppresses its own fallback when execute_partial_exit
     delivered; speaks it, unchanged, when execute_partial_exit did not.
  C. trade_stream: the new evidence event type suppresses the WS safety net
     (extends #561, doesn't compete with it) — and audits the suppression.
  D. trade_stream: a mismatched new_stop_id on the new event type must NOT
     suppress — ambiguity still speaks.
  E. trade_stream: with NO evidence of either type, the safety net still
     fires ALONE — its core purpose, unbroken by this change.

Mutation-proven: see the note at the bottom of each section.
"""
from __future__ import annotations

import json
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

_ET = ZoneInfo("America/New_York")


# ═══════════════════════════════════════════════════════════════════════════
# A. execute_partial_exit — the merged message (AUTHOR)
# ═══════════════════════════════════════════════════════════════════════════

TRADE_ID = 850
TICKER = "AMLX"
SHARES = 5
FULL_REMAINING = 16
NEW_REMAINING = FULL_REMAINING - SHARES
STOP_PRICE = 28.00            # original stop, below entry -> breakeven raises it
ENTRY_PRICE = 30.21
BREAKEVEN_PRICE = max(STOP_PRICE, ENTRY_PRICE)
LIMIT_PRICE = 33.47            # the +2R target
TRIGGER_HIGH = 33.49           # the tape price that actually fired the trigger
ACCOUNT_MODE = "live"


def _noop_lock():
    @asynccontextmanager
    async def _cm(trade_id):
        yield
    return _cm


def _trade(**overrides):
    t = {
        "id": TRADE_ID, "ticker": TICKER, "remaining_shares": FULL_REMAINING,
        "stop_price": STOP_PRICE, "hard_stop": STOP_PRICE, "stop_order_id": "old_stop_id",
        "account_mode": ACCOUNT_MODE, "signal_type": "9m_day2", "entry_price": ENTRY_PRICE,
    }
    t.update(overrides)
    return t


def _make_pool(trade):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[trade, None])  # trade lookup, then dedup-pending
    conn.execute = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool, conn


def _replace_order_fake(calls):
    """Step 1 (qty given): reduces the stop to NEW_REMAINING @ the original price.
    Step 2b (qty is None, price-only): the breakeven replace — a DIFFERENT id, so
    the two are distinguishable exactly like the real broker's two separate orders."""
    async def _replace(order_id, *, qty=None, stop_price=None, limit_price=None,
                        account_mode=None, client_order_id=None):
        calls.append((order_id, qty, stop_price))
        if qty is not None:
            return {"id": "new_stop_id", "status": "accepted"}
        return {"id": "be_stop_id", "status": "accepted"}
    return _replace


async def _get_order_all_live(order_id, account_mode=None):
    return {"id": order_id, "status": "accepted", "order_class": "simple"}


def _oco_parent_response():
    return {
        "id": "oco_parent_1", "status": "new", "order_class": "oco",
        "type": "limit", "side": "sell", "qty": float(SHARES),
        "limit_price": LIMIT_PRICE,
        "legs": [{"id": "oco_leg_1", "type": "stop", "status": "held",
                  "qty": float(SHARES), "stop_price": BREAKEVEN_PRICE}],
    }


def _harness(om):
    trade = _trade()
    pool, conn = _make_pool(trade)
    calls: list = []
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    telegram_mock = AsyncMock(return_value=True)

    patches = [
        patch.object(om, "_PARTIAL_EXIT_PAUSED", False),
        patch.object(om, "_consecutive_partial_exit_failures", AsyncMock(return_value=0)),
        patch.object(om, "_trade_advisory_lock", _noop_lock()),
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "send_telegram_message", telegram_mock),
        patch.object(om, "set_stop_order_id", AsyncMock()),
        patch.object(om, "_ensure_stop_coverage", AsyncMock(return_value="repaired")),
        patch.object(om, "get_runtime_toggle", AsyncMock(return_value=False)),
        patch.object(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=True)),
        patch.object(om, "_profit_take_oco_enabled", AsyncMock(return_value=True)),
        patch.object(om, "_breakeven_at_broker_enabled", AsyncMock(return_value=True)),
        patch.object(om.asyncio, "sleep", AsyncMock()),
        patch.object(om.alpaca, "replace_order", AsyncMock(side_effect=_replace_order_fake(calls))),
        patch.object(om.alpaca, "get_order", _get_order_all_live),
        patch.object(om.alpaca, "get_position", AsyncMock(
            return_value={"qty": float(FULL_REMAINING), "qty_available": float(FULL_REMAINING)})),
        patch.object(om.alpaca, "place_oco_sell", AsyncMock(return_value=_oco_parent_response())),
        patch.object(om.alpaca, "place_limit_sell", AsyncMock(
            return_value={"id": "limit_sell_id", "status": "new"})),
        patch.object(om.alpaca, "place_market_sell", AsyncMock(
            return_value={"id": "market_sell_id", "status": "new"})),
        patch.object(om.alpaca, "make_client_order_id",
                     lambda m, s, t: f"apollo_{m}_{s}_{t}_x"),
    ]
    return {"patches": patches, "audited": audited, "telegram": telegram_mock, "conn": conn}


async def _run(om, h, trigger=None):
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        return await om.execute_partial_exit(
            TRADE_ID, SHARES, force=True, limit_price=LIMIT_PRICE, trigger=trigger)


@pytest.mark.asyncio
async def test_merged_message_carries_all_five_facts_and_marks_delivered():
    """The AMLX shape: trigger fired, 5 of 16 sold as an OCO, remaining 11 sh's
    stop confirmed at breakeven. Must land as ONE Telegram carrying all five
    required facts, not three separate ones.

    MUTATION-PROVEN: reverting the `if trigger is not None:` branch in Step 3
    back to the old unconditional OCO text (so the trigger line, the "of
    {full_remaining}" phrasing, and the Remaining-sh line are all dropped)
    reddens every fact assertion below except the header count. Verified by
    hand during development, then restored — see report."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om)
    trigger = {"delivered": False, "high": TRIGGER_HIGH, "target": LIMIT_PRICE,
               "entry": ENTRY_PRICE, "r_multiple": 2}
    ok = await _run(om, h, trigger=trigger)

    assert ok is True
    assert trigger["delivered"] is True, "Step 3 must flip this before it sends"
    h["telegram"].assert_awaited_once()   # exactly ONE Telegram for the whole event
    msg = h["telegram"].call_args.args[0]

    # fact 1: the trigger and the price that fired it
    assert f"traded ${TRIGGER_HIGH:.2f} >= ${LIMIT_PRICE:.2f}" in msg
    assert f"2R above ${ENTRY_PRICE:.2f}" in msg
    # fact 2: what was sold, how many of how many, at what price
    assert f"{SHARES} of {FULL_REMAINING} sh" in msg
    assert f"${LIMIT_PRICE:.2f}" in msg
    # fact 3: freed shares rest as a paired order that can never be unprotected
    assert "Whichever side fills cancels the other" in msg
    assert f"{SHARES} sh" in msg and "never without a stop" in msg
    # fact 4: where the remaining shares' stop now sits, and what a fill means
    assert f"Remaining {NEW_REMAINING} sh" in msg
    assert f"${BREAKEVEN_PRICE:.2f}" in msg
    assert "scratch" in msg
    # fact 5: reads as ONE event — one header, no leftover "three stitched together"
    assert msg.count("*Profit target hit") == 1
    assert "Profit-take resting" not in msg, "the old separate header must be absorbed, not appended"

    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_stop_telegram_pending" in events, (
        "the WS safety-net suppression evidence must be written")
    pending = next(d for e, s, d in h["audited"] if e == "partial_exit_stop_telegram_pending")
    detail = json.loads(pending)
    assert detail["trade_id"] == TRADE_ID
    assert detail["new_stop_id"] == "be_stop_id", (
        "must name the BREAKEVEN replace's id — the reduced-qty replace's id "
        "('new_stop_id' the broker order, not the trigger dict) would never "
        "match what the WS event actually sees cancelled")
    assert detail["new_stop_price"] == BREAKEVEN_PRICE


@pytest.mark.asyncio
async def test_no_trigger_renders_unchanged_and_writes_no_evidence():
    """agent.py's /partialnow and live_tracker.py's partials pass trigger=None.
    Step 3 must render EXACTLY as before this change (proves the merge is
    additive, not a rewrite of the default path), and must NOT write the new
    evidence row — else the WS safety net would wrongly suppress for a call
    that never actually told the operator about the breakeven stop.

    MUTATION-PROVEN: removing the `if trigger is not None:` gate around the
    evidence-row write (making it unconditional) turns this green-to-red on
    the evidence assertion — verified by hand, then restored."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om)
    ok = await _run(om, h, trigger=None)

    assert ok is True
    h["telegram"].assert_awaited_once()
    msg = h["telegram"].call_args.args[0]
    assert "📋 *Profit-take resting (OCO):*" in msg
    assert "Profit target hit" not in msg
    assert "Remaining" not in msg, "the breakeven-stop line is trigger-only, by design"

    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_stop_telegram_pending" not in events, (
        "no evidence row without `trigger` — the WS safety net must stay this "
        "call's only notice of the breakeven stop")


# ═══════════════════════════════════════════════════════════════════════════
# B. scan_profit_triggers — speaks only when execute_partial_exit didn't
# ═══════════════════════════════════════════════════════════════════════════

SCAN_ENTRY = 100.0
SCAN_STOP = 90.0
SCAN_R = 10.0
SCAN_TARGET = SCAN_ENTRY + 2 * SCAN_R    # PROFIT_TRIGGER_R = 2 -> 120.0
SCAN_HIGH = 121.0
SCAN_REMAINING = 30
SCAN_TRADE_ID = 900


def _scan_trade_row():
    return {
        "id": SCAN_TRADE_ID, "ticker": "AMLX", "entry_price": SCAN_ENTRY,
        "hard_stop": SCAN_STOP, "stop_price": SCAN_STOP, "orb_low": None,
        "signal_type": "9m_day2", "remaining_shares": SCAN_REMAINING,
        "partial_taken": False,
        "filled_at": datetime(2026, 8, 18, 9, 35, tzinfo=_ET),
        "account_mode": "live",
    }


def _scan_harness(om, *, delivered_by_execute: bool):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[_scan_trade_row()])
    conn.fetchval = AsyncMock(return_value=SCAN_HIGH)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)

    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    captured: dict = {}

    async def _fake_execute_partial_exit(trade_id, shares, *, force=False,
                                          limit_price=None, trigger=None):
        captured["trigger"] = trigger
        captured["shares"] = shares
        if trigger is not None and delivered_by_execute:
            trigger["delivered"] = True
        return True

    fixed_now = datetime(2026, 8, 18, 14, 0, tzinfo=_ET)  # safely after 9:30 ET
    mock_datetime = MagicMock()
    mock_datetime.now.return_value = fixed_now

    patches = [
        patch.object(om, "datetime", mock_datetime),
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=True)),
        patch.object(om, "_profit_trigger_already_announced", AsyncMock(return_value=False)),
        patch.object(om, "execute_partial_exit",
                     AsyncMock(side_effect=_fake_execute_partial_exit)),
        patch.object(om, "log_audit_event", AsyncMock()),
        patch.object(om, "send_telegram_message", _capture),
        patch("agents.market_intelligence.constants.PROFIT_TRIGGER_R", 2),
    ]
    return {"patches": patches, "sent": sent, "captured": captured}


async def _run_scan(om, h):
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        return await om.scan_profit_triggers()


@pytest.mark.asyncio
async def test_scan_suppresses_its_fallback_when_execute_partial_exit_delivered():
    """The common case: execute_partial_exit reached Step 3 and folded the
    trigger into its own merged message. scan_profit_triggers must NOT also
    speak — that is exactly the duplicate the operator complained about.

    MUTATION-PROVEN: deleting the `if _trigger_ctx is not None and not
    _trigger_ctx.get("delivered"):` guard (always sending the fallback)
    reddens this test — verified by hand, then restored."""
    from agents.market_intelligence.broker import order_manager as om

    h = _scan_harness(om, delivered_by_execute=True)
    results = await _run_scan(om, h)

    assert results and results[0]["action"] == "partial_submitted"
    assert h["sent"] == [], f"execute_partial_exit already told the operator: {h['sent']}"
    trigger = h["captured"]["trigger"]
    assert trigger is not None
    assert trigger["high"] == SCAN_HIGH and trigger["entry"] == SCAN_ENTRY
    assert trigger["target"] == SCAN_TARGET


@pytest.mark.asyncio
async def test_scan_speaks_its_own_fallback_when_execute_partial_exit_did_not_deliver():
    """Speak when in doubt: execute_partial_exit was paused / circuit-broken /
    aborted before Step 3 (simulated here by leaving trigger["delivered"]
    False) — the trigger fact must not be silently lost. Same text as before
    this merge shipped.

    MUTATION-PROVEN: same guard as above, but this direction — hard-coding
    the guard to `if False:` (never fall back) reddens this test instead —
    verified by hand, then restored."""
    from agents.market_intelligence.broker import order_manager as om

    h = _scan_harness(om, delivered_by_execute=False)
    results = await _run_scan(om, h)

    assert results and results[0]["action"] == "partial_submitted"
    assert len(h["sent"]) == 1, f"expected exactly one fallback: {h['sent']}"
    msg = h["sent"][0]
    assert "Profit target hit" in msg
    assert f"traded ${SCAN_HIGH:.2f} >= ${SCAN_TARGET:.2f}" in msg
    assert f"2R above ${SCAN_ENTRY:.2f}" in msg
    assert "stop moves to breakeven" in msg


# ═══════════════════════════════════════════════════════════════════════════
# C/D/E. trade_stream WS safety net — extends the #561 `_agrees` idiom
# ═══════════════════════════════════════════════════════════════════════════

from agents.market_intelligence.broker import trade_stream as ts  # noqa: E402
from tests.test_stop_reason_560 import (  # noqa: E402
    PLTR_ENTRY, PLTR_HARD_STOP, PLTR_NEW_STOP, PLTR_OLD_STOP, _make_ws_pool, _ws_data,
)


def _amlx_stop_row():
    return {
        "id": TRADE_ID, "ticker": TICKER, "remaining_shares": float(NEW_REMAINING),
        "stop_price": STOP_PRICE, "entry_price": ENTRY_PRICE, "hard_stop": STOP_PRICE,
    }


@pytest.mark.asyncio
async def test_new_evidence_type_suppresses_the_safety_net_and_audits_it(monkeypatch):
    """execute_partial_exit already wrote `partial_exit_stop_telegram_pending`
    naming this exact trade + this exact breakeven order id + price (the row
    Part A proved gets written). The WS handler must recognize it as
    conclusive — same discipline as `stop_update_retry_succeeded` — suppress,
    and write its own audit row saying so.

    MUTATION-PROVEN: reverting the SQL filter back to
    `event_type = 'stop_update_retry_succeeded'` (dropping the new type)
    reddens this test — verified by hand, then restored."""
    replacement = {"id": "be_stop_id", "stop_price": BREAKEVEN_PRICE}
    db_still_null = {"stop_order_id": None, "stop_price": STOP_PRICE}
    dup_rows = [{"detail": json.dumps({
        "trade_id": TRADE_ID, "ticker": TICKER,
        "new_stop_price": BREAKEVEN_PRICE, "new_stop_id": "be_stop_id",
    })}]
    pool, conn, audit, sent, capture = _make_ws_pool(
        _amlx_stop_row(), db_still_null, replacement, dup_rows=dup_rows)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(order_id="old_stop_id", symbol=TICKER),
                                       "canceled", "live")

    assert sent == [], f"the merged Telegram already covered this replacement: {sent}"
    silent = [c for c in audit.await_args_list
              if c.args[0] == "stop_replacement_confirmed_silent"]
    assert len(silent) == 1, f"must audit the suppression exactly once: {audit.await_args_list}"
    detail = json.loads(silent[0].args[2])
    assert detail["trade_id"] == TRADE_ID
    assert detail["audit_price_matched"] is True

    # The SQL itself must actually widen to include the new type (the mocked
    # .fetch() ignores its own WHERE clause, so the behavioural pass above does
    # not by itself prove the real query changed).
    query = conn.fetch.call_args.args[0]
    assert "stop_update_retry_succeeded" in query
    assert "partial_exit_stop_telegram_pending" in query


@pytest.mark.asyncio
async def test_mismatched_new_stop_id_on_the_new_type_still_speaks(monkeypatch):
    """Ambiguity speaks: a `partial_exit_stop_telegram_pending` row exists for
    this trade, but for a DIFFERENT order id (e.g. a stale row from an earlier
    attempt) — not conclusive proof about THIS replacement, and the DB
    re-read doesn't corroborate either. Must still alarm."""
    replacement = {"id": "be_stop_id", "stop_price": BREAKEVEN_PRICE}
    db_disagrees = {"stop_order_id": "old_stop_id", "stop_price": STOP_PRICE}
    dup_rows = [{"detail": json.dumps({
        "trade_id": TRADE_ID, "ticker": TICKER,
        "new_stop_price": BREAKEVEN_PRICE, "new_stop_id": "some_other_order_id",
    })}]
    pool, conn, audit, sent, capture = _make_ws_pool(
        _amlx_stop_row(), db_disagrees, replacement, dup_rows=dup_rows)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(order_id="old_stop_id", symbol=TICKER),
                                       "canceled", "live")

    assert any("Stop replaced" in m for m in sent), (
        f"a mismatched order id must not suppress: {sent}")
    assert not any(c.args[0] == "stop_replacement_confirmed_silent"
                   for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_safety_net_fires_alone_with_no_evidence_of_either_type(monkeypatch):
    """The core purpose, unbroken: agent.py's /partialnow or live_tracker.py's
    partial moved the breakeven stop (trigger=None -> no evidence row, per
    test_no_trigger_renders_unchanged_and_writes_no_evidence above), and no
    stop-retry-recovery row exists either. This handler must be the operator's
    ONLY notice, exactly like before this merge shipped."""
    replacement = {"id": "be_stop_id", "stop_price": BREAKEVEN_PRICE}
    db_disagrees = {"stop_order_id": "old_stop_id", "stop_price": STOP_PRICE}
    pool, conn, audit, sent, capture = _make_ws_pool(
        _amlx_stop_row(), db_disagrees, replacement, dup_rows=[])
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(order_id="old_stop_id", symbol=TICKER),
                                       "canceled", "live")

    replaced = [m for m in sent if "Stop replaced" in m]
    assert len(replaced) == 1, f"the safety net must still fire alone: {sent}"
    assert f"now ${BREAKEVEN_PRICE:.2f}" in replaced[0]
    assert "scratch" in replaced[0]
    assert not any(c.args[0] == "stop_replacement_confirmed_silent"
                   for c in audit.await_args_list)
