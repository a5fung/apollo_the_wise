"""Regression tests for #136 partial-exit replace_order race fix (2026-05-27).

Bug: execute_partial_exit cancelled the existing stop then submitted a
new stop with reduced qty. Alpaca accepts the cancel synchronously but
the share-reservation system clears asynchronously — at ~43ms between
the cancel and new-submit (IBM 2026-05-27), Alpaca rejected the new
stop with "insufficient qty available" because held_for_orders still
showed the full position. Position left with stop_order_id=NULL.

Fix: use Alpaca's atomic replace_order_by_id (no share release window).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Reuse the existing alpaca-SDK stub from conftest.py (auto-loaded).


def _make_order_dict(order_id, qty, stop_price=None):
    return {
        "id": order_id, "side": "OrderSide.SELL", "type": "OrderType.STOP",
        "qty": qty, "filled_qty": 0, "stop_price": stop_price,
        "status": "new", "client_order_id": None,
    }


@pytest.mark.asyncio
async def test_replace_order_passes_qty_and_stop_price():
    """replace_order() must forward both qty and stop_price to the broker
    via ReplaceOrderRequest. The IBM bug was that the partial flow used
    cancel+new; the fix uses replace + must carry both fields atomically."""
    from agents.market_intelligence.broker import alpaca_client

    fake_client = MagicMock()
    fake_returned = MagicMock(
        id="new_order_id", client_order_id=None, symbol="IBM",
        side="sell", type="stop", qty="18", filled_qty="0",
        filled_avg_price=None, stop_price="230.94", limit_price=None,
        status="new", created_at=None, filled_at=None, legs=None,
    )
    fake_client.replace_order_by_id.return_value = fake_returned

    captured: dict = {}
    def _stub_request_ctor(**kwargs):
        captured.update(kwargs)
        return MagicMock(**kwargs)

    with patch.object(
        alpaca_client, "get_trading_client", return_value=fake_client,
    ), patch.object(
        alpaca_client, "ReplaceOrderRequest", side_effect=_stub_request_ctor,
    ):
        result = await alpaca_client.replace_order(
            "old_stop_id_xyz",
            qty=18,
            stop_price=230.94,
            account_mode="paper",
        )

    # Numerics stay numeric — the #136 str(x) wrapping was the bug (fixed
    # 2026-05-28; see test_replace_order_kwargs_numeric.py). These assertions
    # were stale on the old str contract.
    assert captured["qty"] == 18
    assert captured["stop_price"] == 230.94
    fake_client.replace_order_by_id.assert_called_once()
    assert fake_client.replace_order_by_id.call_args.args[0] == "old_stop_id_xyz"
    assert result["id"] == "new_order_id"


@pytest.mark.asyncio
async def test_partial_exit_paused_takes_no_action():
    """#151 HARD PAUSE (2026-06-22, operator): while _PARTIAL_EXIT_PAUSED, execute_partial_exit
    returns False and touches NOTHING — it never reaches the breaker query, the stop replace, or
    the sell — so the position keeps its FULL stop + size. Applies even to force=True (/partialnow),
    since the pending_replace-race breaks that path too. The breaker mock raises if reached."""
    from agents.market_intelligence.broker import order_manager

    audited = []
    async def _audit(evt, *a, **k):
        audited.append(evt)
        return None

    with patch.object(order_manager, "_PARTIAL_EXIT_PAUSED", True), \
         patch.object(order_manager, "log_audit_event", _audit), \
         patch.object(order_manager, "_consecutive_partial_exit_failures",
                      AsyncMock(side_effect=AssertionError("breaker reached PAST the pause guard"))):
        ok = await order_manager.execute_partial_exit(221, 66, force=True)
    assert ok is False
    assert audited == ["partial_exit_paused"]


@pytest.mark.asyncio
async def test_replace_order_propagates_broker_errors():
    """If the broker rejects the replace (e.g., order already filled), the
    exception must propagate so execute_partial_exit's outer try/except can
    fall through to the partial_exit_aborted path."""
    from agents.market_intelligence.broker import alpaca_client

    fake_client = MagicMock()
    fake_client.replace_order_by_id.side_effect = RuntimeError(
        "order already filled"
    )

    with patch.object(
        alpaca_client, "get_trading_client", return_value=fake_client,
    ):
        with pytest.raises(RuntimeError, match="order already filled"):
            await alpaca_client.replace_order(
                "old_stop_id", qty=18, stop_price=230.94,
                account_mode="paper",
            )


@pytest.mark.asyncio
async def test_replace_order_omits_unset_fields():
    """qty-only replace (no stop_price change) should omit stop_price from
    the request — avoids accidentally overriding the broker's stop with
    None."""
    from agents.market_intelligence.broker import alpaca_client

    fake_client = MagicMock()
    fake_returned = MagicMock(
        id="x", client_order_id=None, symbol="IBM",
        side="sell", type="stop",
        qty="10", filled_qty="0", filled_avg_price=None,
        stop_price="100.0", limit_price=None,
        status="new", created_at=None, filled_at=None, legs=None,
    )
    fake_client.replace_order_by_id.return_value = fake_returned

    captured: dict = {}
    def _stub_request_ctor(**kwargs):
        captured.update(kwargs)
        return MagicMock(**kwargs)

    with patch.object(
        alpaca_client, "get_trading_client", return_value=fake_client,
    ), patch.object(
        alpaca_client, "ReplaceOrderRequest", side_effect=_stub_request_ctor,
    ):
        await alpaca_client.replace_order(
            "old", qty=10, account_mode="paper",
        )

    assert captured.get("qty") == 10  # numeric (stale str assertion fixed)
    assert "stop_price" not in captured  # not passed, must not appear


def test_round_stop_to_tick_floors_away_from_trigger():
    """RCAT 2026-06-01: the partial-exit replace submitted a 3-decimal stop
    (11.955, from the ORB low) raw → Alpaca rejected it (42210000 sub-penny)
    → atomic replace failed, the old stop stayed live, but the abort handler
    fired a false-naked alert. _round_stop_to_tick floors to Alpaca's tick
    (>$1 → $0.01; <=$1 → $0.0001), away from the trigger so a protective
    sell-stop never rounds toward current price."""
    from agents.market_intelligence.broker.alpaca_client import _round_stop_to_tick
    assert _round_stop_to_tick(11.955) == 11.95     # the RCAT case
    assert _round_stop_to_tick(8.40) == 8.40        # already valid — untouched
    assert _round_stop_to_tick(230.94) == 230.94    # already valid — untouched
    assert _round_stop_to_tick(5.001) == 5.00       # floors to penny
    assert _round_stop_to_tick(0.50055) == 0.5005   # sub-$1 keeps 4 decimals


@pytest.mark.asyncio
async def test_replace_order_rounds_subpenny_stop_before_submit():
    """The submission-boundary guard: replace_order must round stop_price to
    the tick BEFORE building ReplaceOrderRequest, so a sub-penny value can
    never reach Alpaca (which rejects it, failing the atomic replace)."""
    from agents.market_intelligence.broker import alpaca_client

    fake_client = MagicMock()
    fake_client.replace_order_by_id.return_value = MagicMock(
        id="new_id", client_order_id=None, symbol="RCAT",
        side="sell", type="stop", qty="1020", filled_qty="0",
        filled_avg_price=None, stop_price="11.95", limit_price=None,
        status="new", created_at=None, filled_at=None, legs=None,
    )

    captured: dict = {}
    def _stub_request_ctor(**kwargs):
        captured.update(kwargs)
        return MagicMock(**kwargs)

    with patch.object(
        alpaca_client, "get_trading_client", return_value=fake_client,
    ), patch.object(
        alpaca_client, "ReplaceOrderRequest", side_effect=_stub_request_ctor,
    ):
        await alpaca_client.replace_order(
            "old_stop_id", qty=1020, stop_price=11.955, account_mode="paper",
        )

    assert captured["stop_price"] == 11.95, (
        f"sub-penny 11.955 must be floored to 11.95 before submit; "
        f"got {captured['stop_price']!r}"
    )
    assert not isinstance(captured["stop_price"], str)


def test_is_share_reservation_lag_matches_only_clean_rejection():
    """#150: the sell-retry must fire on Alpaca's share-reservation lag
    ('insufficient qty available' / held_for_orders) — a clean rejection where
    NO order was placed (safe to retry) — but NOT on ambiguous errors like a
    network timeout (which may have placed the order → retry would oversell)."""
    from agents.market_intelligence.broker.order_manager import (
        _is_share_reservation_lag,
    )
    # Retryable: clean broker rejection, no order placed.
    assert _is_share_reservation_lag(Exception("insufficient qty available")) is True
    assert _is_share_reservation_lag(
        Exception('{"code":40310000,"message":"insufficient qty available for RCAT"}')
    ) is True
    assert _is_share_reservation_lag(Exception("held_for_orders: 26")) is True
    # NOT retryable: ambiguous/hard errors must fall through to rollback so we
    # never re-submit a sell that might have already been accepted.
    assert _is_share_reservation_lag(Exception("Read timed out")) is False
    assert _is_share_reservation_lag(Exception("connection reset by peer")) is False
    assert _is_share_reservation_lag(Exception("order already filled")) is False


# ─── #151 DURABLE fix: converge-hardening + in-process abort re-protect ───────

from contextlib import asynccontextmanager  # noqa: E402


def _noop_blocking_lock():
    """Stand-in for order_manager._trade_advisory_lock that holds no real PG lock
    (unit tests have no pool). Just an async-CM that yields."""
    @asynccontextmanager
    async def _cm(trade_id):
        yield
    return _cm


async def _drive_partial_to_sell_then_fail(monkeypatch_targets):
    """Drive execute_partial_exit all the way through a successful stop-reduce +
    verify + shares-free, then make the market sell RAISE. Returns the order_manager
    module + a dict of the spy mocks so the caller can assert on the abort path.

    Trade: 200 shares, selling 66, reduced stop to 134; sell then fails.
    """
    from agents.market_intelligence.broker import order_manager as om

    trade = {
        "id": 221, "ticker": "IBM", "remaining_shares": 200,
        "stop_price": 95.0, "hard_stop": 95.0, "stop_order_id": "old_stop_id",
        "account_mode": "paper", "signal_type": "magna53", "entry_price": 100.0,
    }

    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[trade, None])  # trade lookup, then dedup=None
    conn.execute = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)

    audited = []

    async def _audit(evt, *a, **k):
        audited.append(evt)

    # Broker calls along the happy path up to the sell:
    replace_mock = AsyncMock(return_value={"id": "new_stop_id", "status": "new"})
    # get_order: verify-stop-live poll → live ("new")
    get_order_mock = AsyncMock(return_value={"id": "new_stop_id", "status": "new"})
    # get_position: (1) shares-free poll → qty_available covers; (2) abort re-protect
    #   → total qty. Make ONE mock serve both (qty + qty_available both present).
    get_position_mock = AsyncMock(return_value={"qty": 200.0, "qty_available": 200.0})
    # the market sell RAISES — the failure under test.
    sell_mock = AsyncMock(side_effect=RuntimeError("Read timed out"))
    cancel_mock = AsyncMock()
    place_stop_mock = AsyncMock(return_value={"id": "should_not_be_called", "status": "new"})
    set_stop_mock = AsyncMock()
    ensure_cov_mock = AsyncMock(return_value="🛡 Coverage repaired IBM: stop 134→200")
    telegram_mock = AsyncMock(return_value=True)

    def _make_coid(account_mode, signal_type, ticker):
        return f"apollo_{account_mode}_{signal_type}_{ticker}_123"

    patches = [
        patch.object(om, "_PARTIAL_EXIT_PAUSED", False),
        patch.object(om, "_consecutive_partial_exit_failures", AsyncMock(return_value=0)),
        patch.object(om, "_trade_advisory_lock", _noop_blocking_lock()),
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "send_telegram_message", telegram_mock),
        patch.object(om, "set_stop_order_id", set_stop_mock),
        patch.object(om, "_ensure_stop_coverage", ensure_cov_mock),
        patch.object(om.alpaca, "replace_order", replace_mock),
        patch.object(om.alpaca, "get_order", get_order_mock),
        patch.object(om.alpaca, "get_position", get_position_mock),
        patch.object(om.alpaca, "place_market_sell", sell_mock),
        patch.object(om.alpaca, "cancel_order", cancel_mock),
        patch.object(om.alpaca, "place_stop_order", place_stop_mock),
        patch.object(om.alpaca, "make_client_order_id", _make_coid),
    ]
    return om, {
        "patches": patches, "audited": audited, "replace": replace_mock,
        "sell": sell_mock, "cancel": cancel_mock, "place_stop": place_stop_mock,
        "set_stop": set_stop_mock, "ensure_cov": ensure_cov_mock,
        "telegram": telegram_mock, "get_position": get_position_mock,
    }


@pytest.mark.asyncio
async def test_abort_immediately_reprotects_in_process():
    """#151 POST-ABORT IMMEDIATE RE-PROTECT (MUST PASS): when the market sell
    fails after the stop was reduced, the function — AFTER releasing the advisory
    lock — calls _ensure_stop_coverage DIRECTLY (in-process) to re-protect to
    broker truth, instead of waiting for the next sync cron. broker_qty passed
    must be the live TOTAL position qty (200.0), never DB remaining or
    qty_available."""
    from contextlib import ExitStack
    om, h = await _drive_partial_to_sell_then_fail(None)
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        ok = await om.execute_partial_exit(221, 66, force=True)

    assert ok is False
    # The sell was attempted and failed.
    assert h["sell"].called
    # IMMEDIATE re-protect: _ensure_stop_coverage called directly on the abort path.
    h["ensure_cov"].assert_called_once()
    args = h["ensure_cov"].call_args.args
    assert args[0] == 221           # trade_id
    assert args[1] == "IBM"         # ticker
    assert args[2] == 200.0, (      # broker_qty = live TOTAL qty, NOT DB / qty_available
        f"re-protect must size off broker TOTAL qty 200.0 — got {args[2]}"
    )
    # stop_price is never-naked-critical: None here → _ensure_stop_coverage's place
    # branch can't place a stop ("no stop_price → manual intervention") → naked.
    assert args[3] == 95.0, f"re-protect must carry the DB stop_price 95.0 — got {args[3]}"


@pytest.mark.asyncio
async def test_abort_does_not_rollback_or_null_stop():
    """#151 ROLLBACK GONE + NEVER-NULL: the sell-failure abort path must NOT
    cancel the reduced stop (cancelling a pending_replace is the move that left
    positions naked) and must NOT null stop_order_id (no set_stop_order_id(...,
    None)). It converges: leaves the reduced stop live, re-protects via coverage."""
    from contextlib import ExitStack
    om, h = await _drive_partial_to_sell_then_fail(None)
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        await om.execute_partial_exit(221, 66, force=True)

    # ROLLBACK GONE: no cancel of the reduced stop, no additive full-qty stop place.
    h["cancel"].assert_not_called()
    h["place_stop"].assert_not_called()
    # NEVER-NULL: set_stop_order_id is never called with None on this path.
    for call in h["set_stop"].call_args_list:
        # positional or kw — assert no None second arg
        if len(call.args) >= 2:
            assert call.args[1] is not None, "must never null stop_order_id on abort"
        assert call.kwargs.get("stop_order_id", "x") is not None
    # The legacy rollback audit events must NOT be emitted.
    assert "partial_exit_rolled_back" not in h["audited"]
    assert "partial_exit_rollback_failed" not in h["audited"]
    # ONE failure audit (sell_failed), not a rollback cascade.
    assert "partial_exit_sell_failed" in h["audited"]


@pytest.mark.asyncio
async def test_abort_sends_single_telegram():
    """#151 ONE Telegram: the abort path folds the sell-failure + re-protect
    outcome into a SINGLE message — the except block does not send its own alert
    and the success 'order placed' message is suppressed."""
    from contextlib import ExitStack
    om, h = await _drive_partial_to_sell_then_fail(None)
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        await om.execute_partial_exit(221, 66, force=True)

    assert h["telegram"].call_count == 1, (
        f"abort must send exactly ONE telegram, got {h['telegram'].call_count}"
    )
    msg = h["telegram"].call_args.args[0]
    assert "ABORTED" in msg
    assert "Coverage repaired" in msg  # the folded-in _ensure_stop_coverage outcome


# ─── #151 (2026-06-23) extend in-process re-protect to the OTHER two abort ────
# paths in execute_partial_exit: (1) replacement-rejected + old-stop-confirmed-dead
# and (2) verify-stop-dead-before-sell. Both previously nulled stop_order_id and
# returned inside the advisory lock, leaning on the slow EOD sync cron to
# re-protect. They now route through the SAME post-lock _ensure_stop_coverage call
# the sell-failure path uses — closing the naked window in-process.
#
# NOTE (conscious coverage gap): `ensure_cov_mock` is mocked, so these tests verify
# the re-protect CALL (with broker-truth TOTAL qty 200.0) and that the stale stop
# was nulled BEFORE that call — not the actual stop_order_id write-back inside
# _ensure_stop_coverage. The real write-back (place branch persists the new id) is
# covered by tests/test_never_naked_invariant.py.


async def _build_partial_exit_harness(*, replace_side_effect, get_order_return):
    """Shared harness builder for the two stop-failure abort paths.

    replace_side_effect → alpaca.replace_order behavior (raise → path #1;
        return a live new order → path #2 reaches Step 1b verify).
    get_order_return → alpaca.get_order behavior. Path #1: the old-stop verify
        read in the except returns DEAD. Path #2: the new-stop verify poll
        returns DEAD.

    Trade: 200 shares, selling 66. The MARKET SELL mock RAISES if reached so any
    test that accidentally falls through to a sell fails loudly (guard regression
    tripwire).
    """
    from agents.market_intelligence.broker import order_manager as om

    trade = {
        "id": 221, "ticker": "IBM", "remaining_shares": 200,
        "stop_price": 95.0, "hard_stop": 95.0, "stop_order_id": "old_stop_id",
        "account_mode": "paper", "signal_type": "magna53", "entry_price": 100.0,
    }

    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[trade, None])  # trade lookup, then dedup=None
    conn.execute = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)

    audited = []

    async def _audit(evt, *a, **k):
        audited.append(evt)

    replace_mock = AsyncMock(**replace_side_effect)
    get_order_mock = AsyncMock(**get_order_return)
    # post-lock re-protect reads the live TOTAL position qty.
    get_position_mock = AsyncMock(return_value={"qty": 200.0, "qty_available": 200.0})
    # MUST NOT be reached on either stop-failure abort path.
    sell_mock = AsyncMock(side_effect=AssertionError(
        "place_market_sell reached on a stop-failure abort path — guard regression!"
    ))
    cancel_mock = AsyncMock()
    place_stop_mock = AsyncMock(return_value={"id": "should_not_be_called", "status": "new"})
    set_stop_mock = AsyncMock()
    ensure_cov_mock = AsyncMock(return_value="🛡 Coverage placed IBM: stop 200 @ $95.00")
    telegram_mock = AsyncMock(return_value=True)

    def _make_coid(account_mode, signal_type, ticker):
        return f"apollo_{account_mode}_{signal_type}_{ticker}_123"

    patches = [
        patch.object(om, "_PARTIAL_EXIT_PAUSED", False),
        patch.object(om, "_consecutive_partial_exit_failures", AsyncMock(return_value=0)),
        patch.object(om, "_trade_advisory_lock", _noop_blocking_lock()),
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "send_telegram_message", telegram_mock),
        patch.object(om, "set_stop_order_id", set_stop_mock),
        patch.object(om, "_ensure_stop_coverage", ensure_cov_mock),
        patch.object(om.alpaca, "replace_order", replace_mock),
        patch.object(om.alpaca, "get_order", get_order_mock),
        patch.object(om.alpaca, "get_position", get_position_mock),
        patch.object(om.alpaca, "place_market_sell", sell_mock),
        patch.object(om.alpaca, "cancel_order", cancel_mock),
        patch.object(om.alpaca, "place_stop_order", place_stop_mock),
        patch.object(om.alpaca, "make_client_order_id", _make_coid),
    ]
    return om, {
        "patches": patches, "audited": audited, "replace": replace_mock,
        "get_order": get_order_mock, "sell": sell_mock, "cancel": cancel_mock,
        "place_stop": place_stop_mock, "set_stop": set_stop_mock,
        "ensure_cov": ensure_cov_mock, "telegram": telegram_mock,
        "get_position": get_position_mock,
    }


async def _drive_replace_failed_old_stop_dead():
    """Path #1: replace_order RAISES (both attempts); the except verifies the OLD
    stop and the broker reports it DEAD ('rejected') → old_stop_live=False → null +
    abort_reprotect. new_stop_id stays None so Step 1b is skipped."""
    return await _build_partial_exit_harness(
        replace_side_effect={"side_effect": RuntimeError("replace boom")},
        # except-block verify of old_stop_id → DEAD.
        get_order_return={"return_value": {"id": "old_stop_id", "status": "rejected"}},
    )


async def _drive_verify_stop_dead():
    """Path #2: replace_order SUCCEEDS (new_stop_id assigned) → Step 1b verify polls
    get_order(new_stop_id) → DEAD ('canceled') → verify_outcome='dead' → null +
    abort_reprotect."""
    return await _build_partial_exit_harness(
        replace_side_effect={"return_value": {"id": "new_stop_id", "status": "new"}},
        # Step 1b verify poll of new_stop_id → DEAD.
        get_order_return={"return_value": {"id": "new_stop_id", "status": "canceled"}},
    )


@pytest.mark.asyncio
async def test_old_stop_dead_abort_immediately_reprotects():
    """#151 Path #1 (replacement rejected + old stop confirmed dead): re-protects
    IN-PROCESS via _ensure_stop_coverage with broker-truth TOTAL qty 200.0 (not DB
    remaining, not qty_available), AFTER the advisory lock releases. The market sell
    is NEVER reached."""
    from contextlib import ExitStack
    om, h = await _drive_replace_failed_old_stop_dead()
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        ok = await om.execute_partial_exit(221, 66, force=True)

    assert ok is False
    h["sell"].assert_not_called()             # guard held: no sell after stop failure
    h["place_stop"].assert_not_called()       # no inline rollback place
    h["ensure_cov"].assert_called_once()      # immediate in-process re-protect
    args = h["ensure_cov"].call_args.args
    assert args[0] == 221                      # trade_id
    assert args[1] == "IBM"                    # ticker
    assert args[2] == 200.0, (                 # broker TOTAL qty, not DB/qty_available
        f"re-protect must size off broker TOTAL qty 200.0 — got {args[2]}"
    )
    assert args[3] == 95.0, f"re-protect must carry the DB stop_price 95.0 — got {args[3]}"


@pytest.mark.asyncio
async def test_old_stop_dead_nulls_then_reprotects_no_naked_alert():
    """#151 Path #1: the stale (dead) stop pointer IS nulled (the invariant is
    'stop_order_id never points at a dead order'), but the null is FOLLOWED by the
    in-process re-protect — never left nulled-without-reprotect. The inline 🚨 naked
    alert + 'sync_positions will remediate' audit are gone; one folded post-lock
    Telegram remains."""
    from contextlib import ExitStack
    om, h = await _drive_replace_failed_old_stop_dead()
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        await om.execute_partial_exit(221, 66, force=True)

    # Stale dead pointer nulled (path #1 SHOULD null — opposite of the sell-fail path
    # which keeps its live reduced stop).
    null_calls = [c for c in h["set_stop"].call_args_list
                  if (len(c.args) >= 2 and c.args[1] is None)]
    assert null_calls, "path #1 must null the dead stop pointer"
    # …and re-protect ran after it (not left nulled-without-reprotect).
    h["ensure_cov"].assert_called_once()
    # The stale 'sync_positions will remediate' surface is gone; re-protect is now
    # the remediator.
    assert "naked_position_detected" not in h["audited"]
    assert "partial_exit_aborted" in h["audited"]
    # ONE folded Telegram, and it does NOT claim a sell happened.
    assert h["telegram"].call_count == 1, (
        f"path #1 must send exactly ONE telegram, got {h['telegram'].call_count}"
    )
    msg = h["telegram"].call_args.args[0]
    assert "ABORTED" in msg
    assert "sell failed" not in msg.lower()   # no sell ran → comms must not say so


@pytest.mark.asyncio
async def test_verify_stop_dead_abort_immediately_reprotects():
    """#151 Path #2 (replacement verified DEAD before sell): re-protects IN-PROCESS
    via _ensure_stop_coverage with broker-truth TOTAL qty 200.0, AFTER the lock
    releases. The market sell is NEVER reached."""
    from contextlib import ExitStack
    om, h = await _drive_verify_stop_dead()
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        ok = await om.execute_partial_exit(221, 66, force=True)

    assert ok is False
    h["sell"].assert_not_called()
    h["place_stop"].assert_not_called()
    h["ensure_cov"].assert_called_once()
    args = h["ensure_cov"].call_args.args
    assert args[0] == 221
    assert args[1] == "IBM"
    assert args[2] == 200.0, (
        f"re-protect must size off broker TOTAL qty 200.0 — got {args[2]}"
    )
    assert args[3] == 95.0, f"re-protect must carry the DB stop_price 95.0 — got {args[3]}"


@pytest.mark.asyncio
async def test_verify_stop_dead_nulls_then_reprotects_no_naked_alert():
    """#151 Path #2: the dead new stop pointer IS nulled, but FOLLOWED by the
    in-process re-protect (never nulled-without-reprotect). Inline 🚨 alert +
    'sync_positions will remediate' audit gone; one folded post-lock Telegram."""
    from contextlib import ExitStack
    om, h = await _drive_verify_stop_dead()
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        await om.execute_partial_exit(221, 66, force=True)

    null_calls = [c for c in h["set_stop"].call_args_list
                  if (len(c.args) >= 2 and c.args[1] is None)]
    assert null_calls, "path #2 must null the dead stop pointer"
    h["ensure_cov"].assert_called_once()
    assert "naked_position_detected" not in h["audited"]
    assert "partial_exit_aborted" in h["audited"]
    assert h["telegram"].call_count == 1, (
        f"path #2 must send exactly ONE telegram, got {h['telegram'].call_count}"
    )
    msg = h["telegram"].call_args.args[0]
    assert "ABORTED" in msg
    assert "sell failed" not in msg.lower()


@pytest.mark.asyncio
async def test_verify_stop_uncertain_still_returns_inside_lock_no_reprotect():
    """#151 GUARDRAIL: the 'uncertain' verify outcome (stop still pending after the
    budget, NOT dead) is UNCHANGED — it keeps its stop, returns False inside the
    lock, and does NOT trigger the in-process re-protect (the position is
    over-covered/safe, nothing to fix). Confirms the dead/uncertain split."""
    from contextlib import ExitStack
    # replace succeeds; verify poll never confirms live nor dead → 'uncertain'.
    om, h = await _build_partial_exit_harness(
        replace_side_effect={"return_value": {"id": "new_stop_id", "status": "new"}},
        get_order_return={"return_value": {"id": "new_stop_id", "status": "pending_replace"}},
    )
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        ok = await om.execute_partial_exit(221, 66, force=True)

    assert ok is False
    h["sell"].assert_not_called()
    h["ensure_cov"].assert_not_called()       # uncertain → NO re-protect (stop kept)
    # uncertain path keeps the stop → never nulls.
    for c in h["set_stop"].call_args_list:
        if len(c.args) >= 2:
            assert c.args[1] is not None, "uncertain path must NOT null the stop"
    msg = h["telegram"].call_args.args[0]
    assert "SKIPPED" in msg
