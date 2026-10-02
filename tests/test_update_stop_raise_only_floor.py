"""update_stop raise-only floor against the CURRENT BROKER stop (bug fix 2026-08-10).

THE DEFECT. `update_stop` cancelled the live stop and re-placed at whatever price the
caller computed, with no reference to the stop actually resting at the broker — its only
reference was `mi_live_trades.stop_price`. But the DB is deliberately allowed to UNDERSTATE
protection: the #548 resting-mode "uncertain" branch persists the breakeven successor's
POINTER while withholding `stop_price` (pinned in test_resting_mode_breakeven_548.py — the
safe direction, do not "fix" it). A later EOD trail pass whose effective_stop landed between
the stale DB value and the real broker stop would then cancel a good breakeven stop and
re-place it LOWER — protection silently loosened.

THE FIX. Before cancelling, `update_stop` reads the live stop from the broker:
  * live (non-terminal) broker stop + requested price NOT strictly above it -> refuse:
    no cancel, no place, `stop_update_aborted` audit row (reason=raise_only_floor).
  * broker stop UNREADABLE (get_order None / no stop_price on a non-terminal order) ->
    refuse the same way (reason=broker_stop_unreadable). FAIL DIRECTION, deliberate: an
    unreadable stop means we cannot prove the move is a raise; leaving the existing stop
    untouched keeps protection unchanged, and proceeding blind is exactly how the defect
    loosens it. Never silent — always audited.
  * TERMINAL old stop (cancelled/expired/rejected/replaced/done_for_day/filled) or no
    pointer at all -> no floor. This is the legitimate re-protect path (_stop_refresh
    re-placing at the DB price after a stop died) and must keep working.

This is a BUG FIX enforcing already-signed intent (a protective long stop is raise-only —
the production comment on the `_be_outcome == "live"` branch is the signed intent), not a
strategy or detection-criterion change.
"""
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


TRADE_ID = 777
TICKER = "FIGS"
DB_STOP = 15.00           # what mi_live_trades.stop_price says
BROKER_STOP = 15.30       # what is actually resting at the broker (breakeven)
OLD_STOP_ID = "old_stop_id"
ACCOUNT_MODE = "paper"


def _trade(**overrides):
    t = {
        "id": TRADE_ID, "ticker": TICKER, "remaining_shares": 60,
        "stop_price": DB_STOP, "stop_order_id": OLD_STOP_ID,
        "account_mode": ACCOUNT_MODE, "signal_type": "magna53",
    }
    t.update(overrides)
    return t


def _make_pool(trade):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=trade)     # the trade lookup
    conn.fetchval = AsyncMock(return_value=0)         # get_pending_exit_qty -> 0 held
    conn.execute = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool, conn


def _harness(om, trade, get_order_fake):
    pool, conn = _make_pool(trade)
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    cancel_mock = AsyncMock(return_value=True)
    place_mock = AsyncMock(return_value={"id": "new_stop_xyz", "status": "accepted"})
    get_order_mock = AsyncMock(side_effect=get_order_fake)

    patches = [
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "send_telegram_message", AsyncMock(return_value=True)),
        patch.object(om, "set_stop_order_id", AsyncMock()),
        patch.object(om.asyncio, "sleep", AsyncMock()),
        patch.object(om.alpaca, "get_order", get_order_mock),
        patch.object(om.alpaca, "cancel_order", cancel_mock),
        patch.object(om.alpaca, "place_stop_order", place_mock),
        patch.object(om.alpaca, "make_client_order_id",
                     lambda m, s, t: f"apollo_{m}_{s}_{t}_x"),
    ]
    return {
        "patches": patches, "audited": audited, "conn": conn,
        "cancel": cancel_mock, "place": place_mock, "get_order": get_order_mock,
    }


async def _run(om, h, new_price):
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        return await om.update_stop(TRADE_ID, new_price)


def _aborts(h, reason):
    return [(e, s, d) for e, s, d in h["audited"]
            if e == "stop_update_aborted" and f'"{reason}"' in d]


def _stop_price_updates(h):
    return [c for c in h["conn"].execute.call_args_list if "stop_price = $3" in c.args[0]]


async def _broker_stop_live(order_id, account_mode=None):
    return {"id": order_id, "status": "accepted", "stop_price": BROKER_STOP}


# ── 1. A legitimate raise still goes through ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_legitimate_raise_above_broker_stop_still_goes_through():
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, _trade(), _broker_stop_live)
    ok = await _run(om, h, 15.50)  # above the 15.30 broker stop

    assert ok is True
    h["cancel"].assert_awaited_once_with(OLD_STOP_ID, account_mode=ACCOUNT_MODE)
    assert h["place"].await_args.kwargs["stop_price"] == 15.50
    assert _stop_price_updates(h), "the DB stop_price must follow the placed stop"
    events = [e for e, *_ in h["audited"]]
    assert "stop_updated" in events
    assert "stop_update_aborted" not in events


# ── 2. A request NOT above the live broker stop is refused, stop left alone ──────────


@pytest.mark.asyncio
@pytest.mark.parametrize("requested", [15.10, BROKER_STOP], ids=["below", "equal"])
async def test_request_not_above_live_broker_stop_is_refused(requested):
    """THE defect scenario: DB says 15.00 (stale — #548 uncertain branch withheld the
    breakeven price), broker actually rests at 15.30. The trail computes 15.10 — above
    the DB, below the broker — and pre-fix would cancel the good stop and re-place
    LOWER. Equal is refused too: cancel + re-place at the same price buys nothing and
    opens a no-stop window (the #444 shape)."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, _trade(), _broker_stop_live)
    ok = await _run(om, h, requested)

    assert ok is False
    h["cancel"].assert_not_awaited()          # the live broker stop is left untouched
    h["place"].assert_not_awaited()
    assert not _stop_price_updates(h), "DB stop_price must not move on a refusal"
    assert _aborts(h, "raise_only_floor"), (
        f"expected a stop_update_aborted audit row with reason=raise_only_floor; "
        f"got {h['audited']}")


# ── 3. Unreadable broker stop -> refuse (fail direction: leave protection unchanged) ─


@pytest.mark.asyncio
async def test_unreadable_broker_stop_aborts_and_leaves_stop_untouched():
    """get_order returns None (alpaca_client swallows every read error into None).
    We cannot prove the move is a raise, so we must not act — and it must be visible
    in the audit log, never a silent swallow."""
    from agents.market_intelligence.broker import order_manager as om

    async def _unreadable(order_id, account_mode=None):
        return None

    h = _harness(om, _trade(), _unreadable)
    ok = await _run(om, h, 15.50)

    assert ok is False
    h["cancel"].assert_not_awaited()
    h["place"].assert_not_awaited()
    assert not _stop_price_updates(h)
    assert _aborts(h, "broker_stop_unreadable"), (
        f"the unreadable-broker abort must leave a durable audit row; got {h['audited']}")


@pytest.mark.asyncio
async def test_nonterminal_order_with_no_stop_price_is_treated_as_unreadable():
    """A live order that somehow carries no stop_price proves nothing either."""
    from agents.market_intelligence.broker import order_manager as om

    async def _no_price(order_id, account_mode=None):
        return {"id": order_id, "status": "accepted", "stop_price": None}

    h = _harness(om, _trade(), _no_price)
    ok = await _run(om, h, 15.50)

    assert ok is False
    h["place"].assert_not_awaited()
    assert _aborts(h, "broker_stop_unreadable")


# ── 4. Re-protect paths keep working: dead broker stop / no pointer -> no floor ──────


@pytest.mark.asyncio
@pytest.mark.parametrize("dead_status", ["expired", "canceled", "filled"])
async def test_reprotect_after_dead_broker_stop_has_no_floor(dead_status):
    """_stop_refresh re-places at the DB price (NOT a raise) after the broker stop
    died overnight (DAY leg expiry). A terminal old stop means there is nothing live
    to floor against — the re-place must go through exactly as before the fix."""
    from agents.market_intelligence.broker import order_manager as om

    async def _dead(order_id, account_mode=None):
        return {"id": order_id, "status": dead_status, "stop_price": DB_STOP}

    h = _harness(om, _trade(), _dead)
    ok = await _run(om, h, DB_STOP)  # same price as the DB — the re-protect idiom

    assert ok is True
    assert h["place"].await_args.kwargs["stop_price"] == DB_STOP
    events = [e for e, *_ in h["audited"]]
    assert "stop_updated" in events
    assert "stop_update_aborted" not in events


@pytest.mark.asyncio
async def test_reprotect_with_no_stop_pointer_skips_the_broker_read_entirely():
    """stop_order_id NULL (nulled after a failure; sync remediation pending). There is
    no order to read — the floor must not apply and get_order must not be called."""
    from agents.market_intelligence.broker import order_manager as om

    async def _would_abort_if_called(order_id, account_mode=None):
        return None  # if the floor consulted this, the fail-safe would refuse

    h = _harness(om, _trade(stop_order_id=None), _would_abort_if_called)
    ok = await _run(om, h, DB_STOP)

    assert ok is True
    h["get_order"].assert_not_awaited()
    h["cancel"].assert_not_awaited()  # nothing to cancel
    assert h["place"].await_args.kwargs["stop_price"] == DB_STOP
