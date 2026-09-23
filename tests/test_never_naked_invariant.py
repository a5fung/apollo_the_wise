"""#151 never-naked coverage invariant — deterministic unit tests.

The race that produces a LIVE-but-UNDER-COVERING stop (a partial-exit that
reduced/replaced the stop, then aborted before restoring it) CANNOT be
reproduced against live Alpaca — the broker accepts the cancel/replace
synchronously but clears the share reservation asynchronously, and the window
is sub-100ms. So the qty math is proven HERE with a mocked broker + DB.

The invariant (sync_positions, after the orphan/adopt loop): for each filled
position with a remaining broker qty, guarantee EXACTLY ONE live sell-stop at
`target = broker_qty − pending_exit_qty(trade_id)`. The orphan loop only acts
on NULL/dead stops; this closes the live-but-under-covering gap so any
partial-exit failure leaves the position "no profit trimmed", never naked.

These call `_ensure_stop_coverage` directly (the extracted helper) — same
pattern as `_try_adopt_existing_stop` — so the qty arithmetic + branch
selection are tested without threading through the two prior sync loops.
"""
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Reuse the auto-loaded alpaca-SDK stub from conftest.py.


def _fake_try_lock(acquired: bool):
    """Build a stand-in for order_manager._trade_advisory_try_lock that yields
    `acquired` WITHOUT touching a real Postgres pool. The real helper acquires a
    pooled connection + runs pg_try_advisory_lock; these unit tests don't have a
    pool, so we patch it. acquired=True → coverage proceeds (the prior behaviour
    these tests assert); acquired=False → reconciler defers to an in-flight
    partial and returns None."""
    @asynccontextmanager
    async def _cm(trade_id):
        yield acquired
    return _cm


def _live_stop(order_id, qty, stop_price=95.0, status="new", order_class=None):
    """An open sell-stop order dict as get_open_orders / _order_to_dict returns it.

    order_class defaults to None (a "simple" stop, as every pre-#523 test in
    this file assumes) — pass "oto"/"oco"/"otoco"/"bracket" for the #523
    leg-widen tests."""
    return {
        "id": order_id, "side": "OrderSide.SELL", "type": "OrderType.STOP",
        "qty": qty, "filled_qty": 0, "stop_price": stop_price,
        "status": status, "client_order_id": None, "order_class": order_class,
    }


def _patches(open_orders, pending_qty, *, replace=None, place=None, lock_acquired=True,
             leg_safe=False, cancel_order=None, get_order=None, get_position=None,
             stop_pointer=None):
    """Patch the broker + DB surface _ensure_stop_coverage touches.

    open_orders: list returned by alpaca.get_open_orders (broker truth for the
                 live stop). Can be a list (static) or a callable (stateful, for
                 idempotency — invoked per call).
    pending_qty: value returned by get_pending_exit_qty.
    replace / place: AsyncMock side-effects/returns for the two submit paths.
    leg_safe: value get_runtime_toggle("partial_exit_leg_safe", ...) returns —
              default False (today's ship state; every pre-#523 test relies on
              this so it never touches the leg-widen path or a real DB read).
    cancel_order / get_order / get_position: AsyncMock overrides for the
              leg-safe cancel→release-gate→new mechanism (#523 widen tests
              only — irrelevant, and never called, when leg_safe=False or the
              live stop's order_class isn't advanced).
    stop_pointer: what `_current_stop_pointer` (the #600 re-protect floor's
              fresh DB read of stop_order_id) returns on the place branch.
              Default None → no pointer → no floor → placed at the DB price,
              which is every pre-#600 test's assumption. Patched here so the
              tests never fall through to the helper's fail-open path on a
              real (absent) pool by accident.
    Returns (context-managers-applied-via-ExitStack-less) — we just return the
    individual patch objects in a dict so the test asserts on them.
    """
    from agents.market_intelligence.broker import order_manager as om

    audited = []
    audit_details = []  # (evt, summary, parsed-detail-dict-or-None) — full record

    async def _audit(evt, summary=None, detail=None):
        audited.append(evt)
        try:
            parsed = json.loads(detail) if detail else None
        except (TypeError, ValueError):
            parsed = None
        audit_details.append((evt, summary, parsed))

    if callable(open_orders):
        get_open = AsyncMock(side_effect=lambda *a, **k: open_orders())
    else:
        get_open = AsyncMock(return_value=open_orders)

    replace_mock = replace if replace is not None else AsyncMock(
        return_value={"id": "new_stop_id"}
    )
    place_mock = place if place is not None else AsyncMock(
        return_value={"id": "placed_stop_id"}
    )
    cancel_mock = cancel_order if cancel_order is not None else AsyncMock(return_value=True)
    get_order_mock = get_order if get_order is not None else AsyncMock(
        return_value={"status": "canceled", "order_class": "oto", "filled_qty": 0})
    get_position_mock = get_position if get_position is not None else AsyncMock(
        return_value={"qty_available": 10**6, "qty": 10**6})

    coid_calls = []

    def _make_coid(account_mode, signal_type, ticker):
        coid_calls.append((account_mode, signal_type, ticker))
        return f"apollo_{account_mode}_{signal_type}_{ticker}_123"

    set_stop_mock = AsyncMock()

    ctx = [
        # #151: patch the cross-process advisory try-lock so unit tests don't hit
        # a real pool. Default True → coverage proceeds (asserts the repair logic);
        # False → reconciler defers to an in-flight partial.
        patch.object(om, "_trade_advisory_try_lock", _fake_try_lock(lock_acquired)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "get_pending_exit_qty", AsyncMock(return_value=pending_qty)),
        patch.object(om, "set_stop_order_id", set_stop_mock),
        # #523: leg-widen toggle + broker surface. Defaults keep every existing
        # (pre-#523) test byte-identical — order_class=None on _live_stop means
        # stop_is_leg is False regardless of what this toggle reads, and no
        # real DB read ever happens because get_runtime_toggle is mocked here.
        patch.object(om, "get_runtime_toggle", AsyncMock(return_value=leg_safe), create=True),
        # #600: the place branch's fresh pointer read — see `stop_pointer` above.
        patch.object(om, "_current_stop_pointer", AsyncMock(return_value=stop_pointer)),
        patch.object(om.alpaca, "get_open_orders", get_open),
        patch.object(om.alpaca, "replace_order", replace_mock),
        patch.object(om.alpaca, "place_stop_order", place_mock),
        patch.object(om.alpaca, "cancel_order", cancel_mock),
        patch.object(om.alpaca, "get_order", get_order_mock),
        patch.object(om.alpaca, "get_position", get_position_mock),
        patch.object(om.alpaca, "make_client_order_id", _make_coid),
        # fast polls if a test does exercise the leg-safe path
        patch.object(om, "_LEG_SAFE_POLL_S", 0.0, create=True),
        patch.object(om, "_LEG_SAFE_CANCEL_CONFIRM_BUDGET_S", 0.3, create=True),
        patch.object(om, "_LEG_SAFE_RELEASE_BUDGET_S", 0.3, create=True),
    ]
    return {
        "ctx": ctx, "audited": audited, "audit_details": audit_details,
        "replace": replace_mock, "place": place_mock, "set_stop": set_stop_mock,
        "coid_calls": coid_calls, "get_open": get_open, "cancel": cancel_mock,
        "get_position": get_position_mock,
    }


async def _run(harness, *, broker_qty, stop_price=95.0, signal_type="magna53",
               account_mode="paper", trade_id=221, ticker="IBM"):
    from agents.market_intelligence.broker.order_manager import _ensure_stop_coverage
    from contextlib import ExitStack
    with ExitStack() as stack:
        for cm in harness["ctx"]:
            stack.enter_context(cm)
        return await _ensure_stop_coverage(
            trade_id, ticker, broker_qty, stop_price, signal_type, account_mode,
        )


@pytest.mark.asyncio
async def test_case1_reconciler_fires_mid_partial_does_nothing():
    """CASE 1 (CANNOT BE SKIPPED): reconciler fires MID-partial.
    broker position 200, live stop 134, pending-exit 66 → target = 200 − 66 = 134.
    Sees a live 134-share stop == target → DOES NOTHING. The pending partial of
    66 fully explains the 134 stop; touching it would fight the in-flight exit."""
    h = _patches([_live_stop("stop_134", 134)], pending_qty=66)
    result = await _run(h, broker_qty=200)

    assert result is None, "must be a no-op when live stop already == target"
    h["replace"].assert_not_called()
    h["place"].assert_not_called()
    h["set_stop"].assert_not_called()


@pytest.mark.asyncio
async def test_case2_post_failed_partial_reprotects_to_full():
    """CASE 2: POST-failed/aborted partial. broker position 200, live stop 134,
    pending-exit 0 → target = 200. Sees a live 134-share stop < target → the 66
    un-covered shares are NAKED → re-protect to 200 via an atomic qty-only
    replace of the SINGLE existing stop (never an additive 2nd order)."""
    h = _patches([_live_stop("stop_134", 134)], pending_qty=0)
    result = await _run(h, broker_qty=200)

    assert result is not None and "repaired" in result.lower()
    h["replace"].assert_called_once()
    # replace targets the existing stop id, qty-only widened to 200
    assert h["replace"].call_args.args[0] == "stop_134"
    assert h["replace"].call_args.kwargs["qty"] == 200
    # SINGLE-STOP: a new stop is NEVER additively placed when one exists
    h["place"].assert_not_called()
    # the new order id is persisted
    h["set_stop"].assert_called_once()


@pytest.mark.asyncio
async def test_single_stop_no_duplicate_when_under_covered():
    """SINGLE-STOP: under-covered with one live stop → replace, never place a
    2nd. (A duplicate has no cleanup path; Phase 2b dedup is deferred.)"""
    h = _patches([_live_stop("stop_100", 100)], pending_qty=0)
    await _run(h, broker_qty=163)
    h["replace"].assert_called_once()
    h["place"].assert_not_called()


@pytest.mark.asyncio
async def test_idempotency_second_run_is_noop():
    """IDEMPOTENCY: run twice → 2nd is a no-op. get_open_orders is STATEFUL:
    first call returns the under-covering 134 stop, after the replace it returns
    the widened 200 stop → 2nd run sees target met → no further orders."""
    state = {"qty": 134}

    def _open_orders():
        return [_live_stop("stop_x", state["qty"])]

    async def _replace(order_id, *, qty, account_mode=None, client_order_id=None):
        state["qty"] = qty  # broker now reflects the widened stop
        return {"id": "new_stop_id"}

    h = _patches(_open_orders, pending_qty=0, replace=AsyncMock(side_effect=_replace))

    r1 = await _run(h, broker_qty=200)
    assert r1 is not None and h["replace"].call_count == 1

    r2 = await _run(h, broker_qty=200)
    assert r2 is None, "2nd run must be a no-op (coverage already == target)"
    assert h["replace"].call_count == 1, "no new replace on the idempotent 2nd run"
    h["place"].assert_not_called()


@pytest.mark.asyncio
async def test_mode_bound_coid_on_reprotect_submit():
    """MODE-BOUND COID: the re-protect submit uses make_client_order_id with the
    loop's account_mode (here 'live') + the trade's signal_type + ticker."""
    h = _patches([_live_stop("stop_134", 134)], pending_qty=0)
    await _run(h, broker_qty=200, account_mode="live", signal_type="9m_day2",
               ticker="LZB")
    assert h["coid_calls"], "make_client_order_id must be invoked for the submit"
    mode, sig, tkr = h["coid_calls"][0]
    assert mode == "live"
    assert sig == "9m_day2"
    assert tkr == "LZB"
    # and the COID is threaded into the replace submit
    assert h["replace"].call_args.kwargs["client_order_id"] == "apollo_live_9m_day2_LZB_123"


@pytest.mark.asyncio
async def test_mode_bound_coid_on_place_submit():
    """MODE-BOUND COID on the PLACE branch (no live stop): place_stop_order
    receives the mode-bound COID built from the loop's account_mode."""
    h = _patches([], pending_qty=0)  # no live stop at all → place branch
    await _run(h, broker_qty=200, account_mode="live", ticker="IBM")
    h["place"].assert_called_once()
    assert h["place"].call_args.kwargs["client_order_id"].startswith("apollo_live_")


@pytest.mark.asyncio
async def test_breach_stop_above_market_alerts_no_loop_no_order():
    """BREACH: intended stop_price > market. No live stop exists (place branch),
    place_stop_order raises Alpaca's 'must be less than current price'. The
    invariant emits ONE alert (discrepancy + audit), does NOT retry, does NOT
    place an order, and does NOT write stop_order_id (breach-exit is the
    operator's call, not the reconciler's)."""
    place_mock = AsyncMock(side_effect=Exception(
        '{"code":42210000,"message":"stop price must be less than current price"}'
    ))
    h = _patches([], pending_qty=0, place=place_mock)
    result = await _run(h, broker_qty=200, stop_price=120.0)

    # ONE clear alert surfaced (batched-Telegram discrepancy string)
    assert result is not None
    assert "ABOVE market" in result or "breach" in result.lower()
    # exactly ONE attempt — no retry loop
    assert place_mock.call_count == 1
    # breach audit emitted
    assert "stop_coverage_breach" in h["audited"]
    # converge: no stop_order_id write (operator decides the exit)
    h["set_stop"].assert_not_called()
    # never falls back to a replace
    h["replace"].assert_not_called()


@pytest.mark.asyncio
async def test_over_covered_is_noop():
    """A stop that covers MORE than target (e.g. pending exit already filled but
    stop not yet down-sized) is left alone — shrinking coverage is Phase 2b, and
    over-coverage is never naked."""
    h = _patches([_live_stop("stop_200", 200)], pending_qty=66)  # target=134, stop=200
    result = await _run(h, broker_qty=200)
    assert result is None
    h["replace"].assert_not_called()
    h["place"].assert_not_called()


@pytest.mark.asyncio
async def test_multiple_live_stops_ambiguous_noop():
    """>1 live sell-stop → ambiguous (a duplicate has no cleanup path). Flag via
    audit + discrepancy, but place/replace NOTHING (Phase 2b dedup deferred)."""
    h = _patches(
        [_live_stop("stop_a", 100), _live_stop("stop_b", 100)], pending_qty=0,
    )
    result = await _run(h, broker_qty=200)
    assert result is not None and "ambiguous" in result.lower()
    assert "stop_coverage_ambiguous" in h["audited"]
    h["replace"].assert_not_called()
    h["place"].assert_not_called()
    h["set_stop"].assert_not_called()


@pytest.mark.asyncio
async def test_target_fully_covered_by_pending_is_noop():
    """target <= 0 (pending exits cover the whole position) → no-op; the orphan
    loop's own pending-exit guard owns the no-stop variant of this."""
    h = _patches([_live_stop("stop_x", 50)], pending_qty=200)  # target = 200-200 = 0
    result = await _run(h, broker_qty=200)
    assert result is None
    h["replace"].assert_not_called()
    h["place"].assert_not_called()


@pytest.mark.asyncio
async def test_integration_coverage_uses_broker_qty_not_stale_db():
    """INTEGRATION (locks the 109-vs-28 incident fix at the loop boundary):
    _sync_positions_for_mode must pass _ensure_stop_coverage the BROKER qty
    (post the :2523 qty-sync), NEVER the stale DB remaining_shares. DB says 109,
    Alpaca says 28 → the coverage call must receive broker_qty=28.0. A refactor
    that reverts to remaining_shares would pass every unit test above but
    silently reintroduce the wrong-size-order incident — this catches it."""
    from agents.market_intelligence.broker import order_manager as om
    from tests.conftest import make_mock_pool

    db_trade = {
        "id": 221, "ticker": "IBM", "remaining_shares": 109, "entry_price": 100.0,
        "status": "filled", "stop_order_id": "live_stop_xyz", "stop_price": 95.0,
        "orb_low": 95.0, "signal_type": "magna53",
    }
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[db_trade])
    conn.execute = AsyncMock()

    # Alpaca position truth: 28 shares (DB's 109 is stale post a partial stop-fill).
    alpaca_positions = [{
        "symbol": "IBM", "qty": 28.0, "qty_available": 28.0,
        "avg_entry_price": 100.0, "market_value": 2800.0, "cost_basis": 2800.0,
        "unrealized_pl": 0.0, "unrealized_plpc": 0.0, "current_price": 100.0,
        "side": "long",
    }]

    # A live stop already exists (stop_order_id resolves to a live order), so the
    # orphan loop leaves it alone and the coverage loop is what acts.
    live_order = {"id": "live_stop_xyz", "status": "new", "side": "OrderSide.SELL",
                  "type": "OrderType.STOP", "qty": 28, "stop_price": 95.0}

    ensure_mock = AsyncMock(return_value=None)

    async def _noop_audit(*a, **k):
        pass

    with patch.object(om, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(om, "log_audit_event", _noop_audit), \
         patch.object(om, "send_telegram_message", AsyncMock()), \
         patch.object(om, "set_stop_order_id", AsyncMock()), \
         patch.object(om, "_try_adopt_existing_stop", AsyncMock(return_value=None)), \
         patch.object(om, "_ensure_stop_coverage", ensure_mock), \
         patch.object(om.alpaca, "get_all_positions",
                      AsyncMock(return_value=alpaca_positions)), \
         patch.object(om.alpaca, "get_order", AsyncMock(return_value=live_order)):
        await om._sync_positions_for_mode("paper")

    ensure_mock.assert_called_once()
    # 4th positional arg is broker_qty — MUST be the broker truth 28.0, not 109.
    args = ensure_mock.call_args.args
    assert args[0] == 221          # trade_id
    assert args[1] == "IBM"        # ticker
    assert args[2] == 28.0, (
        f"broker_qty must be Alpaca truth 28.0, not stale DB 109 — got {args[2]}"
    )
    assert args[5] == "paper"      # account_mode (loop's mode)


@pytest.mark.asyncio
async def test_reconciler_skips_when_partial_holds_lock():
    """#151 cross-process lock: when a partial-exit holds the advisory lock on
    this trade_id, pg_try_advisory_lock returns FALSE → _ensure_stop_coverage
    SKIPS the trade entirely: returns None and places/replaces NOTHING (the
    in-flight partial owns coverage; its own abort path re-protects). Without
    this skip, the reconciler would 'repair' a stop the partial is mid-reducing
    — the exact cross-process race the lock exists to kill."""
    # lock_acquired=False → the try-lock yields False inside _ensure_stop_coverage.
    # The position LOOKS under-covered (live 134 stop, target 200) — the case that
    # WOULD trigger a replace if the lock were free — so this proves the skip is
    # the lock, not a coincidental no-op branch.
    h = _patches([_live_stop("stop_134", 134)], pending_qty=0, lock_acquired=False)
    result = await _run(h, broker_qty=200)

    assert result is None, "must skip (return None) while a partial holds the lock"
    h["replace"].assert_not_called()
    h["place"].assert_not_called()
    h["set_stop"].assert_not_called()
    # get_open_orders is never even reached — we bail before any broker read.
    h["get_open"].assert_not_called()


# ── #401: LIVE-specific naked-position loud alarm ────────────────────────────


def _stale_stop_sync_ctx(om, send_mock):
    """Shared mock scaffold: DB trade whose stop_order_id resolves to a DEAD
    (canceled) broker order → the stale-stop branch fires naked_position_detected."""
    from unittest.mock import AsyncMock, patch
    from tests.conftest import make_mock_pool

    db_trade = {
        "id": 401, "ticker": "IBM", "remaining_shares": 5, "entry_price": 100.0,
        "status": "filled", "stop_order_id": "dead_stop_401", "stop_price": 95.0,
        "orb_low": 95.0, "signal_type": "magna53",
    }
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[db_trade])
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=0)   # get_pending_exit_qty path
    conn.fetchrow = AsyncMock(return_value=None)
    alpaca_positions = [{
        "symbol": "IBM", "qty": 5.0, "qty_available": 5.0,
        "avg_entry_price": 100.0, "market_value": 500.0, "cost_basis": 500.0,
        "unrealized_pl": 0.0, "unrealized_plpc": 0.0, "current_price": 100.0,
        "side": "long",
    }]
    dead_order = {"id": "dead_stop_401", "status": "canceled",
                  "side": "OrderSide.SELL", "type": "OrderType.STOP",
                  "qty": 5, "stop_price": 95.0}

    async def _noop_audit(*a, **k):
        pass

    return patch.object(om, "get_pool", AsyncMock(return_value=pool)), \
        patch.object(om, "log_audit_event", _noop_audit), \
        patch.object(om, "send_telegram_message", send_mock), \
        patch.object(om, "set_stop_order_id", AsyncMock()), \
        patch.object(om, "_try_adopt_existing_stop", AsyncMock(return_value=None)), \
        patch.object(om, "_ensure_stop_coverage", AsyncMock(return_value=None)), \
        patch.object(om.alpaca, "get_all_positions",
                     AsyncMock(return_value=alpaca_positions)), \
        patch.object(om.alpaca, "get_order", AsyncMock(return_value=dead_order))


@pytest.mark.asyncio
async def test_401_naked_live_position_fires_dedicated_alarm():
    """#401: account_mode='live' + confirmed-dead stop → a DEDICATED
    '🚨 NAKED LIVE POSITION' Telegram fires (not just the generic digest)."""
    from unittest.mock import AsyncMock
    from agents.market_intelligence.broker import order_manager as om

    send_mock = AsyncMock(return_value=True)
    ctxs = _stale_stop_sync_ctx(om, send_mock)
    from contextlib import ExitStack
    with ExitStack() as stack:
        for c in ctxs:
            stack.enter_context(c)
        await om._sync_positions_for_mode("live")

    naked_alarms = [c.args[0] for c in send_mock.call_args_list
                    if "NAKED LIVE POSITION" in str(c.args[0])]
    assert len(naked_alarms) == 1, (
        f"expected exactly one dedicated naked-live alarm, got {len(naked_alarms)}; "
        f"all sends: {[str(c.args[0])[:60] for c in send_mock.call_args_list]}"
    )
    assert "IBM" in naked_alarms[0] and "canceled" in naked_alarms[0]


@pytest.mark.asyncio
async def test_401_paper_mode_no_dedicated_alarm():
    """#401: the SAME dead-stop scenario in paper mode must NOT fire the
    live-only alarm (the generic digest still covers it)."""
    from unittest.mock import AsyncMock
    from agents.market_intelligence.broker import order_manager as om

    send_mock = AsyncMock(return_value=True)
    ctxs = _stale_stop_sync_ctx(om, send_mock)
    from contextlib import ExitStack
    with ExitStack() as stack:
        for c in ctxs:
            stack.enter_context(c)
        await om._sync_positions_for_mode("paper")

    assert not any("NAKED LIVE POSITION" in str(c.args[0])
                   for c in send_mock.call_args_list), \
        "paper-mode sync must not fire the live-only naked alarm"


# ── F16: broker-read ambiguity must DEFER, never drive the place branch ──────


@pytest.mark.asyncio
async def test_f16_broker_read_failure_defers_no_stop_placed():
    """F16 (7/2 review): a get_open_orders failure in _ensure_stop_coverage must
    DEFER (return None) — pre-fix, the [] fallback made 'API down' look like
    'no live stop' and the place branch fired on a false premise."""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, patch
    from agents.market_intelligence.broker import order_manager as om

    @asynccontextmanager
    async def _lock_ok(_tid):
        yield True

    place_spy = AsyncMock()
    with patch.object(om, "_trade_advisory_try_lock", _lock_ok), \
         patch.object(om, "get_pending_exit_qty", AsyncMock(return_value=0)), \
         patch.object(om.alpaca, "get_open_orders",
                      AsyncMock(side_effect=RuntimeError("api down"))), \
         patch.object(om.alpaca, "place_stop_order", place_spy):
        out = await om._ensure_stop_coverage(1, "IBM", 5.0, 95.0, "magna53", "live")
    assert out is None, "broker-unreadable must defer, not act"
    place_spy.assert_not_called()


@pytest.mark.asyncio
async def test_f16_get_open_orders_raise_on_error_contract():
    """F16: raise_on_error=True re-raises (after the #370 alert); the default
    keeps the [] fallback for every legacy caller."""
    from unittest.mock import AsyncMock, patch
    from agents.market_intelligence.broker import alpaca_client as ac

    with patch.object(ac, "get_trading_client", side_effect=RuntimeError("auth down")), \
         patch("agents.market_intelligence.llm_health.maybe_alert_api_failure",
               AsyncMock()) as alert:
        assert await ac.get_open_orders("IBM", account_mode="paper") == []
        with pytest.raises(RuntimeError):
            await ac.get_open_orders("IBM", account_mode="paper", raise_on_error=True)
    assert alert.await_count == 2, "the #370 alert fires on BOTH paths"


@pytest.mark.asyncio
async def test_f16_sibling_adopt_read_failure_defers_no_placement():
    """F16-sibling (7/3 altitude pass): a broker-read failure inside
    _try_adopt_existing_stop must DEFER the trade (no placement) — pre-fix it
    returned None ('nothing to adopt') and sync fell through to
    place_stop_order while a real stop may have existed."""
    from unittest.mock import AsyncMock, patch
    from agents.market_intelligence.broker import order_manager as om
    from tests.conftest import make_mock_pool

    db_trade = {
        "id": 501, "ticker": "IBM", "remaining_shares": 5, "entry_price": 100.0,
        "status": "filled", "stop_order_id": None, "stop_price": 95.0,
        "orb_low": 95.0, "signal_type": "magna53",
    }
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[db_trade])
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=0)
    conn.fetchrow = AsyncMock(return_value=None)
    alpaca_positions = [{
        "symbol": "IBM", "qty": 5.0, "qty_available": 5.0,
        "avg_entry_price": 100.0, "market_value": 500.0, "cost_basis": 500.0,
        "unrealized_pl": 0.0, "unrealized_plpc": 0.0, "current_price": 100.0,
        "side": "long",
    }]

    async def _noop_audit(*a, **k):
        pass

    place_spy = AsyncMock()
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(om, "log_audit_event", _noop_audit), \
         patch.object(om, "send_telegram_message", AsyncMock(return_value=True)), \
         patch.object(om, "set_stop_order_id", AsyncMock()), \
         patch.object(om, "_ensure_stop_coverage", AsyncMock(return_value=None)), \
         patch.object(om.alpaca, "get_all_positions",
                      AsyncMock(return_value=alpaca_positions)), \
         patch.object(om.alpaca, "get_open_orders",
                      AsyncMock(side_effect=RuntimeError("api down"))), \
         patch.object(om.alpaca, "place_stop_order", place_spy):
        await om._sync_positions_for_mode("live")

    place_spy.assert_not_called()


# ── #523: leg-safe WIDEN of an under-covering bracket-LEG stop ───────────────
#
# `_ensure_stop_coverage`'s under-covered branch used to do a qty-only
# `replace_order` unconditionally. Alpaca REJECTS every qty change on an
# advanced-order (OTO/bracket) LEG (42210000 — the same rejection #508 fixed
# on the partial-exit REDUCE side), so whenever the surviving stop was a leg,
# this branch could never repair it. The fix routes the leg case through the
# SAME verified-cancel → reservation-release-gate → new-stop mechanism
# (`_widen_stop_via_cancel_new`, sharing `_replace_stop_leg_via_cancel_new`
# with the #508 reduce side), gated by the same `partial_exit_leg_safe`
# toggle, with a pre-flight broker-headroom check before the leg is ever
# cancelled (widening's new qty is NOT bounded by what the cancel itself
# frees, unlike reducing — see `_replace_stop_leg_via_cancel_new`'s docstring).


PLTR_LEG_REJECTION_527 = Exception(
    '{"code":42210000,"message":"qty cannot be changed for advanced orders"}'
)


@pytest.mark.asyncio
async def test_523_leg_widen_via_cancel_new_when_toggle_on():
    """THE bracket-leg coverage-repair case. Broker position 150, live LEG
    stop 100 (order_class=oto), pending-exit 0 → target=150, under-covered by
    50. Toggle ON must widen via cancel→release-gate→new — NEVER via the qty
    replace Alpaca structurally rejects on a leg.

    FAILS AGAINST TODAY'S CODE: pre-#523, this branch calls replace_order
    unconditionally; against a real leg that raises the 42210000 rejection
    below, and the function returns 'failed to widen' having never cancelled
    or placed anything — the opposite of every assertion here."""
    from agents.market_intelligence.broker import order_manager as om

    calls: list = []

    async def _cancel(order_id, account_mode=None):
        calls.append(("cancel", order_id))
        return True

    async def _get_order(order_id, account_mode=None):
        # STATEFUL on the leg: 'new' until cancel_order has been called,
        # 'canceled' after — proves cancel-confirmed-before-new-stop ordering.
        if any(c[0] == "cancel" for c in calls):
            calls.append(("get_order", "canceled"))
            return {"id": order_id, "status": "canceled", "order_class": "oto", "filled_qty": 0}
        calls.append(("get_order", "new"))
        return {"id": order_id, "status": "new", "order_class": "oto", "filled_qty": 0}

    async def _get_position(ticker, account_mode=None):
        calls.append(("get_position", ticker))
        return {"qty_available": 150.0, "qty": 150.0}

    async def _place_stop(ticker, qty, stop_price, account_mode=None, client_order_id=None):
        calls.append(("place_stop", qty, stop_price))
        return {"id": "widened_stop_id", "status": "accepted"}

    # If the (pre-fix) code ever calls replace_order on this leg, it must be
    # rejected exactly as Alpaca rejects it for real — proving the test fails
    # for the RIGHT reason against unfixed code, not by accident.
    replace_mock = AsyncMock(side_effect=PLTR_LEG_REJECTION_527)

    h = _patches(
        # live stop's OWN broker-confirmed price is 95.0; db_stop_price below
        # is deliberately DIFFERENT (93.50, a stale/drifted DB value) so the
        # test can prove the widen uses the leg's own price, never db's.
        [_live_stop("leg_id", 100, stop_price=95.0, order_class="oto")],
        pending_qty=0, leg_safe=True, replace=replace_mock,
        cancel_order=_cancel, get_order=_get_order, get_position=_get_position,
        place=AsyncMock(side_effect=_place_stop),
    )
    result = await _run(h, broker_qty=150, stop_price=93.50)

    assert result is not None and "repaired" in result.lower(), f"got: {result!r}"
    assert not h["replace"].called, (
        "qty replace on an advanced-order leg is structurally rejected — must not be attempted")
    # NEVER-NAKED ORDERING: cancel confirmed → release gate → new stop placed.
    idx_cancel = calls.index(("cancel", "leg_id"))
    idx_confirm = next(i for i, c in enumerate(calls) if c == ("get_order", "canceled"))
    idx_pos = next(i for i, c in enumerate(calls[idx_confirm:]) if c[0] == "get_position") + idx_confirm
    idx_place = next(i for i, c in enumerate(calls) if c[0] == "place_stop")
    assert idx_cancel < idx_confirm < idx_pos < idx_place
    # Widened to the FULL target, at the leg's OWN unchanged price (THE LINE:
    # mechanism only — level untouched, and never the stale db_stop_price).
    assert ("place_stop", 150, 95.0) in calls
    assert not any(c[0] == "place_stop" and c[2] == 93.50 for c in calls), (
        "widen must use the leg's own already-accepted price, never db_stop_price")
    h["set_stop"].assert_called_once_with(
        221, "widened_stop_id", reason="sync_coverage_repair", account_mode="paper")
    assert "stop_coverage_repaired" in h["audited"]
    # The audit row is the verify-live evidence (same contract #508 shipped for
    # partial_exit_stop_replaced): mechanism tag + measured cancel/release/accept
    # timings, so a live firing is distinguishable from a plain replace.
    repaired = next(d for evt, _, d in h["audit_details"] if evt == "stop_coverage_repaired")
    assert repaired["mechanism"] == "leg_safe_cancel_new"
    assert "timings_ms" in repaired and repaired["timings_ms"], (
        "leg-safe widen must carry measured timings, same as the #508 reduce side")


@pytest.mark.asyncio
async def test_523_toggle_off_keeps_atomic_replace_and_fails_safe_on_a_leg():
    """Toggle OFF (ship state): a bracket-LEG stop still takes the atomic
    replace path, eats 42210000 exactly as before #523, and fails CLEANLY —
    the old leg stays live, untouched, and the operator is told. No cancel,
    no new stop. This is the byte-identical-behind-the-toggle pin."""
    from agents.market_intelligence.broker import order_manager as om

    replace_mock = AsyncMock(side_effect=PLTR_LEG_REJECTION_527)
    h = _patches(
        [_live_stop("leg_id", 100, stop_price=95.0, order_class="oto")],
        pending_qty=0, leg_safe=False, replace=replace_mock,
    )
    result = await _run(h, broker_qty=150, stop_price=95.0)

    assert result is not None and "failed to widen" in result.lower(), f"got: {result!r}"
    h["replace"].assert_called_once()
    assert h["replace"].call_args.args[0] == "leg_id"
    assert h["replace"].call_args.kwargs["qty"] == 150
    h["cancel"].assert_not_called()
    h["place"].assert_not_called()
    h["set_stop"].assert_not_called()
    assert "stop_coverage_repair_failed" in h["audited"]


@pytest.mark.asyncio
async def test_523_naked_after_confirmed_cancel_says_coverage_may_be_zero():
    """Cancel confirmed (the old leg is verifiably GONE) but the new stop
    can't be placed (non-lag broker error): the fallback must NOT reuse the
    'failed to widen X→Y' phrasing (that implies the old stop is still live —
    false here) and must NOT place a stop off the now-stale target (a fill
    could have preceded this). Alert plainly, change nothing else, and let
    the next reconciler pass re-protect off fresh broker truth."""
    from agents.market_intelligence.broker import order_manager as om

    async def _cancel(order_id, account_mode=None):
        return True

    async def _get_order(order_id, account_mode=None):
        return {"id": order_id, "status": "canceled", "order_class": "oto", "filled_qty": 0}

    async def _get_position(ticker, account_mode=None):
        return {"qty_available": 150.0, "qty": 150.0}

    async def _place_stop_boom(*a, **k):
        raise RuntimeError("boom")  # non-lag → no retry loop

    h = _patches(
        [_live_stop("leg_id", 100, stop_price=95.0, order_class="oto")],
        pending_qty=0, leg_safe=True,
        cancel_order=_cancel, get_order=_get_order, get_position=_get_position,
        place=AsyncMock(side_effect=_place_stop_boom),
    )
    result = await _run(h, broker_qty=150, stop_price=95.0)

    assert result is not None
    assert "zero" in result.lower(), f"must say coverage may be zero, got: {result!r}"
    assert "failed to widen" not in result.lower(), (
        "must not reuse the phrasing that implies the old stop is still live")
    h["set_stop"].assert_not_called(), "no order to persist — nothing was placed"
    assert "stop_coverage_repair_failed" in h["audited"]
    failed = next(d for evt, _, d in h["audit_details"] if evt == "stop_coverage_repair_failed")
    assert failed["widen_outcome"] == "naked", (
        "the audit row must distinguish naked from a plain replace failure")


@pytest.mark.asyncio
async def test_523_preflight_blocks_the_cancel_when_headroom_is_insufficient():
    """A widen's new qty is LARGER than the leg's own qty by construction —
    unlike reducing, the release gate is not guaranteed to clear on qty
    alone. If broker truth shows insufficient headroom, the leg must NEVER
    be cancelled — the failure must happen BEFORE the irreversible step, not
    be recovered from after it. Coverage stays exactly at today's safe
    under-covered state (old leg untouched)."""
    from agents.market_intelligence.broker import order_manager as om

    async def _get_position(ticker, account_mode=None):
        # Some other reservation this function doesn't know about holds
        # everything: 0 available, even though the leg itself holds 100.
        return {"qty_available": 0.0, "qty": 150.0}

    cancel_mock = AsyncMock(return_value=True)
    h = _patches(
        [_live_stop("leg_id", 100, stop_price=95.0, order_class="oto")],
        pending_qty=0, leg_safe=True,
        cancel_order=cancel_mock, get_position=_get_position,
    )
    result = await _run(h, broker_qty=150, stop_price=95.0)

    assert result is not None and "failed to widen" in result.lower()
    cancel_mock.assert_not_called(), "must never cancel a leg it can't safely replace"
    h["replace"].assert_not_called()
    h["place"].assert_not_called()
    # A preflight refusal never reached the widen mechanism, so the audit
    # payload must stay byte-identical to today's toggle-off shape — no
    # "mechanism" key pinned onto a repair that never actually widened.
    refused = next(d for evt, _, d in h["audit_details"] if evt == "stop_coverage_repair_failed")
    assert "mechanism" not in refused
    h["set_stop"].assert_not_called()


@pytest.mark.asyncio
async def test_523_toggle_on_simple_stop_still_uses_atomic_replace():
    """Toggle ON alone must not force cancel+new — only a genuine advanced-
    order LEG does. A simple stop (order_class=None) under toggle ON must
    take the SAME atomic-replace path as toggle OFF."""
    from agents.market_intelligence.broker import order_manager as om

    h = _patches([_live_stop("stop_134", 134)], pending_qty=0, leg_safe=True)
    result = await _run(h, broker_qty=200)

    assert result is not None and "repaired" in result.lower()
    h["replace"].assert_called_once()
    assert h["replace"].call_args.args[0] == "stop_134"
    assert h["replace"].call_args.kwargs["qty"] == 200
    h["cancel"].assert_not_called()
    h["place"].assert_not_called()


@pytest.mark.asyncio
async def test_523_unreadable_live_qty_on_a_leg_falls_back_to_atomic_replace_not_a_crash():
    """A live stop whose `qty` field is missing/unparseable (live_qty=None,
    pre-existing possibility — see the `qty` parse above) must NOT reach the
    leg-safe pre-flight arithmetic (`_avail + live_qty` on a None crashes).
    Even on an advanced-order leg with the toggle ON, this must fall back to
    the atomic replace — exactly the pre-#523 behavior for this edge case —
    not raise."""
    from agents.market_intelligence.broker import order_manager as om

    h = _patches(
        [_live_stop("leg_id", None, order_class="oto")],  # qty missing
        pending_qty=0, leg_safe=True,
    )
    result = await _run(h, broker_qty=200)  # must not raise

    assert result is not None and "repaired" in result.lower(), f"got: {result!r}"
    h["replace"].assert_called_once()
    assert h["replace"].call_args.kwargs["qty"] == 200
    h["cancel"].assert_not_called()
    h["place"].assert_not_called()
