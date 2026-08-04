"""#508 leg-safe partial exit (2026-08-04) — bracket-leg stop reduction.

THE BUG (PLTR trade 307, 2026-08-04, first live +2R profit-trigger fire):
every MAGNA53 entry is an OTO bracket, so its stop is an advanced-order LEG,
and Alpaca rejects ANY qty change on a leg with 42210000 "qty cannot be
changed for advanced orders". execute_partial_exit's replace-with-qty could
therefore structurally NEVER reduce a MAGNA53 stop — the profit-take could
never harvest (fail-safe: the rejected replace left the original stop live).

THE FIX (toggle `partial_exit_leg_safe`, default OFF): when the stop is an
advanced-order leg, reduce it via verified-cancel → reservation-release gate →
new reduced stop (_reduce_stop_via_cancel_new). The release gate on
qty_available is what closes the IBM 2026-05-27 cancel+new race (the May
incident submitted the new stop BEFORE held_for_orders cleared). Empirical
basis: scripts/probes/_508_oto_leg_probe.py (paper, 2026-08-04) — see the
block comment above the helper in order_manager.py.
"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


PLTR_LEG_REJECTION = Exception(
    '{"code":42210000,"message":"qty cannot be changed for advanced orders"}'
)


def _noop_blocking_lock():
    @asynccontextmanager
    async def _cm(trade_id):
        yield
    return _cm


def _make_harness(om, *, calls: list):
    """Shared mock choreography for a 6-share PLTR-like trade selling 2.

    get_order is STATEFUL on the old leg: order_class 'oto' + status 'new'
    until cancel_order has been called, 'canceled' after — so the tests can
    assert the never-naked ordering (cancel CONFIRMED before the new stop is
    placed, new stop VERIFIED before the sell).
    """
    trade = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 6,
        "stop_price": 143.28, "hard_stop": 143.28, "stop_order_id": "old_leg_id",
        "account_mode": "paper", "signal_type": "magna53", "entry_price": 150.86,
    }
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[trade, None])  # trade lookup, dedup
    conn.execute = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)

    audited: list = []

    async def _audit(evt, *a, **k):
        audited.append(evt)

    cancel_mock = AsyncMock(return_value=True)

    async def _cancel(order_id, account_mode=None):
        calls.append(("cancel", order_id))
        return await cancel_mock(order_id, account_mode=account_mode)

    async def _get_order(order_id, account_mode=None):
        if order_id == "old_leg_id":
            if any(c[0] == "cancel" for c in calls):
                calls.append(("old_leg_status", "canceled"))
                return {"id": "old_leg_id", "status": "canceled",
                        "order_class": "oto", "filled_qty": 0}
            calls.append(("old_leg_status", "new"))
            return {"id": "old_leg_id", "status": "new",
                    "order_class": "oto", "filled_qty": 0}
        calls.append(("get_order", order_id))
        return {"id": order_id, "status": "accepted"}

    async def _get_position(ticker, account_mode=None):
        calls.append(("get_position", ticker))
        return {"qty": 6.0, "qty_available": 6.0}

    async def _place_stop(ticker, qty, stop_price, account_mode=None,
                          client_order_id=None):
        calls.append(("place_stop", qty, stop_price))
        return {"id": "new_stop_id", "status": "accepted"}

    async def _sell(ticker, qty, account_mode=None, client_order_id=None):
        calls.append(("sell", qty))
        return {"id": "sell_id", "status": "new"}

    replace_mock = AsyncMock(side_effect=PLTR_LEG_REJECTION)
    set_stop_mock = AsyncMock()
    ensure_cov_mock = AsyncMock(return_value="repaired")
    telegram_mock = AsyncMock(return_value=True)

    patches = [
        patch.object(om, "_PARTIAL_EXIT_PAUSED", False),
        patch.object(om, "_consecutive_partial_exit_failures", AsyncMock(return_value=0)),
        patch.object(om, "_trade_advisory_lock", _noop_blocking_lock()),
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "send_telegram_message", telegram_mock),
        patch.object(om, "set_stop_order_id", set_stop_mock),
        patch.object(om, "_ensure_stop_coverage", ensure_cov_mock),
        patch.object(om, "get_runtime_toggle", AsyncMock(return_value=True), create=True),
        # fast polls in tests
        patch.object(om, "_LEG_SAFE_POLL_S", 0.0, create=True),
        patch.object(om, "_LEG_SAFE_CANCEL_CONFIRM_BUDGET_S", 0.3, create=True),
        patch.object(om, "_LEG_SAFE_RELEASE_BUDGET_S", 0.3, create=True),
        patch.object(om.alpaca, "replace_order", replace_mock),
        patch.object(om.alpaca, "cancel_order", _cancel),
        patch.object(om.alpaca, "get_order", _get_order),
        patch.object(om.alpaca, "get_position", _get_position),
        patch.object(om.alpaca, "place_stop_order", _place_stop),
        patch.object(om.alpaca, "place_market_sell", _sell),
        patch.object(om.alpaca, "make_client_order_id",
                     lambda m, s, t: f"apollo_{m}_{s}_{t}_x"),
    ]
    return {
        "patches": patches, "audited": audited, "replace": replace_mock,
        "cancel": cancel_mock, "set_stop": set_stop_mock,
        "ensure_cov": ensure_cov_mock, "telegram": telegram_mock,
        "get_order_fn": _get_order, "trade": trade,
    }


def _run(om, h, shares=2, trade_id=307):
    from contextlib import ExitStack
    async def _go():
        with ExitStack() as stack:
            for p in h["patches"]:
                stack.enter_context(p)
            return await om.execute_partial_exit(trade_id, shares, force=True)
    return asyncio.get_event_loop().run_until_complete(_go()) \
        if False else asyncio.run(_go())


# ── THE bracket-leg case (fails against pre-#508 code) ────────────────────────

@pytest.mark.asyncio
async def test_leg_stop_reduced_via_cancel_new_when_toggle_on():
    """A bracket-leg stop (order_class=oto) with the toggle ON must be reduced
    via cancel→release-gate→new — NOT via the qty replace Alpaca rejects — and
    the partial must complete: reduced 4-share stop up, 2-share sell placed.
    Pre-#508 code calls replace_order, eats the 42210000, and aborts (False)."""
    from agents.market_intelligence.broker import order_manager as om
    from contextlib import ExitStack

    calls: list = []
    h = _make_harness(om, calls=calls)
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        ok = await om.execute_partial_exit(307, 2, force=True)

    assert ok is True, f"partial must SUCCEED on a bracket leg; calls={calls}"
    # The doomed qty-replace was never sent against the leg.
    assert not h["replace"].called, "qty replace on an advanced-order leg is structurally rejected — must not be attempted"
    # NEVER-NAKED ORDERING: cancel confirmed → new reduced stop → verified → sell.
    idx_cancel = calls.index(("cancel", "old_leg_id"))
    idx_confirm = calls.index(("old_leg_status", "canceled"))
    idx_place = next(i for i, c in enumerate(calls) if c[0] == "place_stop")
    idx_sell = next(i for i, c in enumerate(calls) if c[0] == "sell")
    assert idx_cancel < idx_confirm < idx_place < idx_sell
    # Release gate ran between cancel-confirm and the new stop (the IBM fix).
    assert any(c[0] == "get_position" for c in calls[idx_confirm:idx_place]), \
        "new stop must be gated on the broker's qty_available release signal"
    # Reduced stop is for the REMAINDER at the UNCHANGED stop price (THE LINE:
    # mechanism fix only — level and fraction untouched).
    assert ("place_stop", 4, 143.28) in calls
    assert ("sell", 2) in calls
    # New stop id persisted for the reconciler.
    h["set_stop"].assert_any_call(307, "new_stop_id", reason="partial_replacement",
                                  account_mode="paper")


@pytest.mark.asyncio
async def test_42210000_net_routes_to_leg_safe_when_order_class_unreadable():
    """If the order_class pre-read fails, the first replace attempt's 42210000
    rejection must route to the leg-safe path (no blind second retry of a
    deterministic rejection) and the partial must still complete."""
    from agents.market_intelligence.broker import order_manager as om
    from contextlib import ExitStack

    calls: list = []
    h = _make_harness(om, calls=calls)

    # Pre-read raises ONCE; later get_order calls behave normally.
    base_get_order = h["get_order_fn"]
    state = {"first": True}

    async def _get_order_flaky(order_id, account_mode=None):
        if state["first"] and order_id == "old_leg_id":
            state["first"] = False
            raise RuntimeError("api down")
        return await base_get_order(order_id, account_mode=account_mode)

    h["patches"] = [p for p in h["patches"]]
    with patch.object(om.alpaca, "get_order", _get_order_flaky):
        from contextlib import ExitStack as _ES
        with _ES() as stack:
            for p in h["patches"]:
                if getattr(p, "attribute", None) == "get_order":
                    continue
                stack.enter_context(p)
            stack.enter_context(patch.object(om.alpaca, "get_order", _get_order_flaky))
            ok = await om.execute_partial_exit(307, 2, force=True)

    assert ok is True, f"42210000 net must recover via leg-safe; calls={calls}"
    assert h["replace"].call_count == 1, \
        "a deterministic 42210000 must not be retried blind (no 1.5s second attempt)"
    assert any(c[0] == "place_stop" for c in calls)
    assert any(c[0] == "sell" for c in calls)


# ── Failure taxonomy on the leg-safe path ─────────────────────────────────────

@pytest.mark.asyncio
async def test_naked_placement_failure_reprotects_to_broker_truth():
    """Cancel confirmed but the reduced stop can't be placed (non-lag error):
    the position IS naked → pointer nulled + in-process _ensure_stop_coverage
    re-protect off broker TOTAL qty. No sell may ever happen."""
    from agents.market_intelligence.broker import order_manager as om
    from contextlib import ExitStack

    calls: list = []
    h = _make_harness(om, calls=calls)

    async def _place_stop_boom(*a, **k):
        calls.append(("place_stop_failed",))
        raise RuntimeError("boom")  # non-lag → no retry loop

    with ExitStack() as stack:
        for p in h["patches"]:
            if getattr(p, "attribute", None) == "place_stop_order":
                continue
            stack.enter_context(p)
        stack.enter_context(patch.object(om.alpaca, "place_stop_order", _place_stop_boom))
        ok = await om.execute_partial_exit(307, 2, force=True)

    assert ok is False
    assert not any(c[0] == "sell" for c in calls), "no sell after a stop failure"
    h["set_stop"].assert_any_call(307, None, reason="partial_naked", account_mode="paper")
    h["ensure_cov"].assert_called_once()
    args = h["ensure_cov"].call_args.args
    assert args[0] == 307 and args[1] == "PLTR"
    assert args[2] == 6.0, "re-protect sizes off broker TOTAL qty"
    assert args[3] == 143.28, "re-protect must carry the DB stop price"


@pytest.mark.asyncio
async def test_cancel_uncertain_reprotects_and_never_places_blind():
    """Cancel accepted but the leg never leaves pending_cancel within budget:
    a second stop must NOT be placed blind (duplicate hazard) — route to the
    re-protect machinery, which resolves against broker truth."""
    from agents.market_intelligence.broker import order_manager as om
    from contextlib import ExitStack

    calls: list = []
    h = _make_harness(om, calls=calls)

    async def _get_order_stuck(order_id, account_mode=None):
        if order_id == "old_leg_id":
            if any(c[0] == "cancel" for c in calls):
                return {"id": order_id, "status": "pending_cancel",
                        "order_class": "oto", "filled_qty": 0}
            return {"id": order_id, "status": "new",
                    "order_class": "oto", "filled_qty": 0}
        return {"id": order_id, "status": "accepted"}

    with ExitStack() as stack:
        for p in h["patches"]:
            if getattr(p, "attribute", None) == "get_order":
                continue
            stack.enter_context(p)
        stack.enter_context(patch.object(om.alpaca, "get_order", _get_order_stuck))
        ok = await om.execute_partial_exit(307, 2, force=True)

    assert ok is False
    assert not any(c[0] == "place_stop" for c in calls), \
        "must never place a 2nd stop while the old one may still be live"
    assert not any(c[0] == "sell" for c in calls)
    h["ensure_cov"].assert_called_once()


@pytest.mark.asyncio
async def test_stop_filled_during_cancel_aborts_without_new_stop():
    """The stop FILLS while we try to cancel it: the position is exiting via
    the stop — no partial, no new stop, no re-protect (the stop-fill WS flow
    owns finalization)."""
    from agents.market_intelligence.broker import order_manager as om
    from contextlib import ExitStack

    calls: list = []
    h = _make_harness(om, calls=calls)

    async def _get_order_filled(order_id, account_mode=None):
        if order_id == "old_leg_id":
            if any(c[0] == "cancel" for c in calls):
                return {"id": order_id, "status": "filled",
                        "order_class": "oto", "filled_qty": 6}
            return {"id": order_id, "status": "new",
                    "order_class": "oto", "filled_qty": 0}
        return {"id": order_id, "status": "accepted"}

    with ExitStack() as stack:
        for p in h["patches"]:
            if getattr(p, "attribute", None) == "get_order":
                continue
            stack.enter_context(p)
        stack.enter_context(patch.object(om.alpaca, "get_order", _get_order_filled))
        ok = await om.execute_partial_exit(307, 2, force=True)

    assert ok is False
    assert not any(c[0] == "place_stop" for c in calls)
    assert not any(c[0] == "sell" for c in calls)
    assert not h["ensure_cov"].called, "stop-fill exit owns the position — no re-protect"
    assert not h["set_stop"].called, "pointer stays for the stop-fill finalizer"
    sent = " ".join(str(c.args[0]) for c in h["telegram"].call_args_list)
    assert "FILLED" in sent


# ── Toggle OFF: byte-identical to today (regression pin) ──────────────────────

@pytest.mark.asyncio
async def test_toggle_off_keeps_replace_path_and_fails_safe():
    """Toggle OFF (the ship state): a bracket leg still takes the replace path,
    eats 42210000, and aborts CLEANLY with the original stop intact — exactly
    the PLTR 2026-08-04 behavior. No cancel, no new stop, nothing sold."""
    from agents.market_intelligence.broker import order_manager as om
    from contextlib import ExitStack

    calls: list = []
    h = _make_harness(om, calls=calls)

    with ExitStack() as stack:
        for p in h["patches"]:
            if getattr(p, "attribute", None) == "get_runtime_toggle":
                continue
            stack.enter_context(p)
        stack.enter_context(patch.object(
            om, "get_runtime_toggle", AsyncMock(return_value=False), create=True))
        ok = await om.execute_partial_exit(307, 2, force=True)

    assert ok is False
    assert h["replace"].call_count == 2, "toggle OFF keeps the 2-attempt replace"
    assert not any(c[0] == "cancel" for c in calls), "toggle OFF must never cancel the leg"
    assert not any(c[0] == "place_stop" for c in calls)
    assert not any(c[0] == "sell" for c in calls)
    assert not h["ensure_cov"].called, "old stop verified live — protected abort, no re-protect"
    sent = " ".join(str(c.args[0]) for c in h["telegram"].call_args_list)
    assert "position protected" in sent


# ── Unit: the matcher + the order_class wire field ────────────────────────────

def test_advanced_qty_rejection_matcher():
    from agents.market_intelligence.broker.order_manager import (
        _is_advanced_qty_rejection,
    )
    assert _is_advanced_qty_rejection(PLTR_LEG_REJECTION) is True
    assert _is_advanced_qty_rejection(
        Exception("qty cannot be changed for advanced orders")) is True
    # Must NOT match the reservation-lag rejection (different handling).
    assert _is_advanced_qty_rejection(
        Exception('{"code":40310000,"message":"insufficient qty available"}')) is False
    assert _is_advanced_qty_rejection(Exception("Read timed out")) is False
    assert _is_advanced_qty_rejection(Exception("order already filled")) is False


def test_order_to_dict_includes_order_class():
    """get_order must surface order_class on the wire dict — leg detection is
    impossible without it (pre-#508 _order_to_dict dropped the field)."""
    from agents.market_intelligence.broker.alpaca_client import _order_to_dict

    o = SimpleNamespace(
        id="x", client_order_id=None, symbol="PLTR", side="sell", type="stop",
        qty="6", filled_qty="0", filled_avg_price=None, stop_price="143.28",
        limit_price=None, status="new", order_class="OrderClass.OTO",
        created_at=None, filled_at=None, legs=None,
    )
    assert _order_to_dict(o)["order_class"] == "oto"

    o2 = SimpleNamespace(
        id="y", client_order_id=None, symbol="F", side="sell", type="stop",
        qty="6", filled_qty="0", filled_avg_price=None, stop_price="9.96",
        limit_price=None, status="new",
        created_at=None, filled_at=None, legs=None,
    )  # no order_class attr at all → None, never a crash
    assert _order_to_dict(o2)["order_class"] is None
