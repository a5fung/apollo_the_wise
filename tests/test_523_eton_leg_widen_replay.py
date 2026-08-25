"""#523 — replay of the ETON 2026-08-14 coverage gap against `_ensure_stop_coverage`.

WHY THIS FILE EXISTS: the leg-WIDEN path shipped 2026-08-18 and has never fired in
production (`stop_coverage_repaired` rows all predate the deploy; `stop_coverage_repair_failed`
has zero rows ever). A repair path that has never run is indistinguishable from a broken
one, so it is driven here against the REAL recorded incident rather than an invented one.

THE REAL ROWS (`scripts/probes/_591_eton_orders_out.psv`, read-only prod capture 2026-08-24,
trade 367, live account, 17 shares):
  id 292  09:31:02  buy limit 17 @ 55.56, order_class **oto**, filled 09:32
  id 293  09:31:02  sell stop 17 @ 53.01 — the OTO **leg**, CANCELLED 09:36
  id 294  09:35:00  sell stop 12 @ 53.01, order_class **simple**, status replaced
  id 295  09:35:01  sell limit 5 @ 59.58, purpose partial_exit — RESTING until 15:58
  id 296  09:35:01  sell stop 12 @ 55.2012, order_class **simple**, filled

⚠ CORRECTION THE ROWS FORCE: at 09:45, when `check_position_coverage` logged
`position_unprotected: live stop qty 12 < 17 shares held`, the surviving stop (id 296) was
`order_class: simple` — NOT an advanced-order leg. So the ETON incident is NOT a #523 case:
`_ensure_stop_coverage` would not have widened it, and would not even have repaired it
(test 1). The +2R carve-out had already cancelled the leg (id 293) and replaced it with
simple stops, which is what #508's leg-safe reduce always produces. The detector and the
repairer legitimately disagree: the detector compares against `remaining_shares` (17) and
deliberately does not count a bare sell limit as protection, while the repairer subtracts
pending exits (the resting 5) because shares held by another order cannot carry a stop
(broker rejects 40310000 — `_508_oto_leg_probe_output.json` T4).

The ETON shape only becomes a #523 case when the stop that under-covers is still an
advanced-order LEG. Tests 2-6 hold every ETON number fixed (17 held, 12 covered, the leg's
own price 55.2012, the stale DB price 53.01) and change ONLY that, which is the smallest
faithful mutation of the real incident that reaches the widen branch.

READ-ONLY: no broker call, no trade-state write, no toggle change. The harness is the one
`test_never_naked_invariant.py` already uses.
"""
import pytest

from tests.test_never_naked_invariant import _live_stop, _patches, _run

# The real numbers, from the prod capture above.
ETON_TRADE_ID = 367
ETON_HELD = 17           # broker position qty at 09:45
ETON_STOP_QTY = 12       # the surviving stop's qty
ETON_CARVE_OUT = 5       # id 295, purpose partial_exit, resting
ETON_LIVE_STOP_PX = 55.2012   # id 296 — the breakeven-moved stop actually resting
ETON_DB_STOP_PX = 53.01       # mi_live_trades.stop_price — stale vs the live stop
ETON_LEG_ID = "11b25e11-5b14-4b60-afd5-2a48db9ea783"


def _eton(harness, **kw):
    """Drive `_ensure_stop_coverage` with ETON's real identity + prices."""
    return _run(harness, broker_qty=kw.pop("broker_qty", ETON_HELD),
                stop_price=ETON_DB_STOP_PX, signal_type="magna53",
                account_mode="live", trade_id=ETON_TRADE_ID, ticker="ETON", **kw)


@pytest.mark.asyncio
async def test_eton_as_it_really_happened_is_a_noop_not_a_widen():
    """THE REAL INCIDENT, exactly as the prod rows record it: 17 held, a SIMPLE
    12-share stop resting, the 5-share carve-out limit still working.

    target = 17 − 5 = 12 = the live stop → no-op. Nothing is replaced, nothing
    cancelled, nothing placed. This is correct, not a miss: the 5 shares are
    reserved by the resting limit and a stop on them would be rejected 40310000.
    It also pins that the incident could never have exercised #523 — the stop
    was not a leg."""
    h = _patches(
        [_live_stop(ETON_LEG_ID, ETON_STOP_QTY, stop_price=ETON_LIVE_STOP_PX,
                    order_class="simple")],
        pending_qty=ETON_CARVE_OUT, leg_safe=True,
    )
    result = await _eton(h)

    assert result is None, f"must be a no-op on the real ETON shape, got: {result!r}"
    h["replace"].assert_not_called()
    h["cancel"].assert_not_called()
    h["place"].assert_not_called()
    h["set_stop"].assert_not_called()
    assert h["audited"] == []


@pytest.mark.asyncio
async def test_eton_shape_on_a_leg_widens_to_the_full_position():
    """THE #523 CASE, ETON's numbers: 17 held, the carve-out limit now TERMINAL
    (pending 0), and the 12-share stop still the entry's OTO **leg**. target = 17
    vs a leg covering 12 → 5 shares naked.

    Alpaca rejects every qty replace on a leg (probe T1/T3), so the repair must go
    cancel → confirm → reservation-release gate → new stop, at the LEG'S OWN price
    (55.2012), never the stale DB price (53.01). Quantity only, never the level."""
    from unittest.mock import AsyncMock

    calls: list = []
    # Broker truth: the leg holds 12 of the 17, so 5 are available BEFORE the
    # cancel and all 17 after it — the real reservation behaviour probe T6 timed.
    state = {"avail": float(ETON_HELD - ETON_STOP_QTY)}

    async def _cancel(order_id, account_mode=None):
        calls.append(("cancel", order_id))
        state["avail"] = float(ETON_HELD)
        return True

    async def _get_order(order_id, account_mode=None):
        cancelled = any(c[0] == "cancel" for c in calls)
        calls.append(("get_order", "canceled" if cancelled else "new"))
        return {"id": order_id, "status": "canceled" if cancelled else "new",
                "order_class": "oto", "filled_qty": 0}

    async def _get_position(ticker, account_mode=None):
        calls.append(("get_position", state["avail"]))
        return {"qty": float(ETON_HELD), "qty_available": state["avail"]}

    async def _place_stop(ticker, qty, stop_price, account_mode=None, client_order_id=None):
        calls.append(("place_stop", qty, stop_price))
        return {"id": "widened_stop_id", "status": "accepted"}

    h = _patches(
        [_live_stop(ETON_LEG_ID, ETON_STOP_QTY, stop_price=ETON_LIVE_STOP_PX,
                    order_class="oto")],
        pending_qty=0, leg_safe=True,
        cancel_order=_cancel, get_order=_get_order, get_position=_get_position,
        place=AsyncMock(side_effect=_place_stop),
    )
    result = await _eton(h)

    assert result is not None and "repaired" in result.lower(), f"got: {result!r}"
    h["replace"].assert_not_called()          # structurally rejected on a leg
    # The resulting stop covers ALL 17 shares, at the leg's own accepted price.
    assert ("place_stop", ETON_HELD, ETON_LIVE_STOP_PX) in calls
    assert not any(c[0] == "place_stop" and c[2] == ETON_DB_STOP_PX for c in calls), (
        "a widen may never move the stop level — least of all to a stale DB price")
    # Never-naked ordering: cancel → confirmed dead → shares released → new stop.
    i_cancel = calls.index(("cancel", ETON_LEG_ID))
    i_confirm = next(i for i, c in enumerate(calls) if c == ("get_order", "canceled"))
    i_release = next(i for i, c in enumerate(calls)
                     if c[0] == "get_position" and c[1] == float(ETON_HELD))
    i_place = next(i for i, c in enumerate(calls) if c[0] == "place_stop")
    assert i_cancel < i_confirm < i_release < i_place
    h["set_stop"].assert_called_once_with(
        ETON_TRADE_ID, "widened_stop_id", reason="sync_coverage_repair",
        account_mode="live")
    repaired = next(d for evt, _, d in h["audit_details"] if evt == "stop_coverage_repaired")
    assert repaired["mechanism"] == "leg_safe_cancel_new"
    assert repaired["live_stop_qty"] == ETON_STOP_QTY and repaired["target_qty"] == ETON_HELD


@pytest.mark.asyncio
async def test_widen_is_idempotent_a_second_pass_places_nothing():
    """A repaired position must not be repaired again. Broker state is STATEFUL:
    the 12-share leg is replaced by the 17-share simple stop the widen placed, so
    the next reconciler pass sees coverage met and issues no order at all."""
    from unittest.mock import AsyncMock

    book = {"stop": _live_stop(ETON_LEG_ID, ETON_STOP_QTY,
                               stop_price=ETON_LIVE_STOP_PX, order_class="oto")}

    async def _cancel(order_id, account_mode=None):
        return True

    async def _get_order(order_id, account_mode=None):
        return {"id": order_id, "status": "canceled", "order_class": "oto", "filled_qty": 0}

    async def _get_position(ticker, account_mode=None):
        return {"qty": float(ETON_HELD), "qty_available": float(ETON_HELD)}

    async def _place_stop(ticker, qty, stop_price, account_mode=None, client_order_id=None):
        # The widen's product: a SIMPLE stop covering the full position.
        book["stop"] = _live_stop("widened_stop_id", qty, stop_price=stop_price,
                                  order_class="simple")
        return {"id": "widened_stop_id", "status": "accepted"}

    place_mock = AsyncMock(side_effect=_place_stop)
    cancel_mock = AsyncMock(side_effect=_cancel)
    h = _patches(
        lambda: [book["stop"]], pending_qty=0, leg_safe=True,
        cancel_order=cancel_mock, get_order=_get_order, get_position=_get_position,
        place=place_mock,
    )
    first = await _eton(h)
    second = await _eton(h)

    assert first is not None and "repaired" in first.lower()
    assert second is None, f"second pass must be a no-op, got: {second!r}"
    assert place_mock.await_count == 1 and cancel_mock.await_count == 1
    assert h["set_stop"].await_count == 1
    assert h["audited"].count("stop_coverage_repaired") == 1


@pytest.mark.asyncio
async def test_preflight_one_share_short_refuses_and_never_cancels_the_leg():
    """THE DANGEROUS DIRECTION. A widen's new qty is larger than the leg's own, so
    the release gate is not guaranteed to clear — if the leg were cancelled first
    and the shares turned out to be held elsewhere, today's SAFE failure
    (under-covered, old stop alive) would become a genuinely naked position.

    One share short of the target: 4 available + 12 on the leg = 16 < 17. The leg
    must survive untouched, the operator must be told, and the audit row must carry
    NO `mechanism` key (nothing was widened)."""
    from unittest.mock import AsyncMock

    async def _get_position(ticker, account_mode=None):
        return {"qty": float(ETON_HELD), "qty_available": 4.0}

    cancel_mock = AsyncMock(return_value=True)
    h = _patches(
        [_live_stop(ETON_LEG_ID, ETON_STOP_QTY, stop_price=ETON_LIVE_STOP_PX,
                    order_class="oto")],
        pending_qty=0, leg_safe=True,
        cancel_order=cancel_mock, get_position=_get_position,
    )
    result = await _eton(h)

    assert result is not None and "failed to widen" in result.lower(), f"got: {result!r}"
    assert "zero" not in result.lower(), (
        "nothing was cancelled — the message must not imply coverage is gone")
    cancel_mock.assert_not_called()
    h["replace"].assert_not_called()
    h["place"].assert_not_called()
    h["set_stop"].assert_not_called()
    refused = next(d for evt, _, d in h["audit_details"]
                   if evt == "stop_coverage_repair_failed")
    assert "mechanism" not in refused and "widen_outcome" not in refused


@pytest.mark.asyncio
async def test_preflight_passes_when_headroom_exactly_meets_the_target():
    """The other side of the same boundary: 5 available + 12 on the leg = exactly
    17. The gate must not be conservative by an off-by-one either — a refusal here
    would leave a repairable position under-covered forever."""
    from unittest.mock import AsyncMock

    async def _get_position(ticker, account_mode=None):
        return {"qty": float(ETON_HELD), "qty_available": float(ETON_HELD - ETON_STOP_QTY)}

    cancel_mock = AsyncMock(return_value=True)
    h = _patches(
        [_live_stop(ETON_LEG_ID, ETON_STOP_QTY, stop_price=ETON_LIVE_STOP_PX,
                    order_class="oto")],
        pending_qty=0, leg_safe=True,
        cancel_order=cancel_mock, get_position=_get_position,
        place=AsyncMock(return_value={"id": "widened_stop_id"}),
    )
    result = await _eton(h)

    assert result is not None and "repaired" in result.lower(), f"got: {result!r}"
    cancel_mock.assert_called_once()


@pytest.mark.asyncio
async def test_a_leg_that_partly_filled_is_cancelled_and_left_with_no_stop():
    """KNOWN RESIDUAL — reported, not fixed here (verify task; a money-path edit
    is the operator's call).

    `partially_filled` is a live-stop status, so a leg whose stop has partly filled
    reaches this branch. The pre-flight sizes headroom off the leg's ORDER qty (12),
    not its unfilled remainder (8), so it passes; the shared mechanism then detects
    the fill only AFTER the cancel and returns `naked` rather than placing a stop off
    a now-stale qty. Net: the leg is gone and no replacement exists. The event-driven
    callers (partial-exit abort, the #566 OCO-cancel handler) re-protect immediately if
    one of them fires; the SCHEDULED path does not — `sync_positions` runs at 16:05 and
    21:00 ET only, and the 15-minute `check_position_coverage` job merely DETECTS. The
    message says so plainly (it must not reuse 'failed to widen', which would imply the
    old stop is alive)."""
    from unittest.mock import AsyncMock

    partly_filled_leg = _live_stop(ETON_LEG_ID, ETON_STOP_QTY,
                                   stop_price=ETON_LIVE_STOP_PX, order_class="oto",
                                   status="partially_filled")
    partly_filled_leg["filled_qty"] = 4

    async def _get_order(order_id, account_mode=None):
        return {"id": order_id, "status": "canceled", "order_class": "oto", "filled_qty": 4}

    async def _get_position(ticker, account_mode=None):
        # 4 of the 17 already sold by the stop → 13 held, 8 still on the dying leg.
        return {"qty": 13.0, "qty_available": 5.0}

    cancel_mock = AsyncMock(return_value=True)
    place_mock = AsyncMock(return_value={"id": "should_never_be_placed"})
    h = _patches(
        [partly_filled_leg], pending_qty=0, leg_safe=True,
        cancel_order=cancel_mock, get_order=_get_order, get_position=_get_position,
        place=place_mock,
    )
    result = await _eton(h, broker_qty=13)

    cancel_mock.assert_called_once(), "the pre-flight passed on the leg's order qty"
    place_mock.assert_not_called()
    h["set_stop"].assert_not_called()
    assert result is not None and "zero" in result.lower(), (
        f"an irreversible cancel with no replacement must say so: {result!r}")
    failed = next(d for evt, _, d in h["audit_details"]
                  if evt == "stop_coverage_repair_failed")
    assert failed["widen_outcome"] == "naked"
