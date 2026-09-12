"""#646 (e) (2026-09-11) — this handler clears a pointer to a LIVE stop and nothing
puts it back.

THE RACE, and it is ours. `execute_full_exit` (#646 b, shipped hours earlier the
same evening) cancels the resting stop, tries to sell, and on a rejection
re-places the stop and writes the new order id. OKTA's live sequence on
2026-09-11 did all three inside ONE second, with the broker's cancel event for
the OLD stop arriving afterwards. This handler NULLs `stop_order_id`
unconditionally, so the null landed on the REPLACEMENT's id: the position was
protected at the broker and the database said unprotected.

WHAT WAS NEVER THE EXPOSURE, stated because the obvious reading is wrong: the
operator does not get a false "unprotected" page from here. #433/#475 already ask
the broker whether a different live stop covers the position and downgrade the
alarm when it does. The damage is the WRONG POINTER — and the codebase already
documented it, because #566's naked branch had to corroborate between two
immutable audit rows rather than read a column "THIS SAME HANDLER unconditionally
NULLS ... a few lines above".

⚠ WHY THE FIX IS NOT A GUARD ON THE NULL — the first version of this was, and the
#600 suite killed it within the minute. `test_600_reprotect_floor` pins that null
as byte-for-byte unchanged ON PURPOSE: assume-naked is a fail-safe, and a
compare-and-set on it would leave a stale non-live id in place in the one case the
fail-safe exists for. So the null stays exactly as it was and the pointer is
REPAIRED afterwards, on the branch where the broker has POSITIVELY confirmed a
live stop — #433's own invariant, and the only place the null is known to be wrong.

Pinned here:
  - the null is still unconditional (no `expected_prior`) — the fail-safe is intact;
  - on a CONFIRMED replacement the pointer is refilled with that order's id;
  - the repair is `expected_prior=None`: a FILL, never an overwrite, so a
    concurrent writer always wins;
  - no confirmed replacement -> no repair attempt at all (the naked path is untouched);
  - a deferred or failing repair is recorded / survived, never silent.

MUTATION-PROVEN, each against the test it reddens:
  - delete the repair block -> reddens THREE (refilled / fill-never-overwrite /
    deferred-is-recorded), measured, not assumed;
  - omit `expected_prior=None` -> reddens exactly one, the fill-never-overwrite pin.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts

from tests.conftest import make_mock_pool

CANCELLED_STOP = "stop-1-cancelled-by-full-exit"
REPLACEMENT_STOP = "stop-2-restored-after-failed-exit"
TRADE_ID = 382


def _stop_row():
    return {"id": TRADE_ID, "ticker": "OKTA", "remaining_shares": 2,
            "stop_price": 165.57, "entry_price": 171.20, "hard_stop": 150.52}


def _cancel_event(order_id=CANCELLED_STOP):
    order = SimpleNamespace(
        id=order_id, symbol="OKTA", status="canceled", side="sell", type="stop",
        qty=2.0, filled_qty=0.0, filled_avg_price=None, stop_price=165.57,
        limit_price=None, canceled_at=None, failed_at=None, expired_at=None,
        updated_at=None,
    )
    return SimpleNamespace(order=order, event="canceled", reason=None)


def _wire(monkeypatch, *, replacement, set_stop_returns=True):
    """Drive branch 2 (stop-leg cancel) with the broker read under our control."""
    pool, conn = make_mock_pool()
    # fetchrow order in the handler: entry-trade lookup, then the stop-trade lookup.
    conn.fetchrow = AsyncMock(side_effect=[None, _stop_row()])
    conn.fetchval = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value="UPDATE 1")

    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    sent: list = []

    async def _tg(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", _audit)
    monkeypatch.setattr(ts, "send_telegram_message", _tg)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    confirm = AsyncMock(return_value=replacement)
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(om, "_preserve_dead_stop_price", AsyncMock())
    set_stop = AsyncMock(return_value=set_stop_returns)
    monkeypatch.setattr(om, "set_stop_order_id", set_stop)

    return {"set_stop": set_stop, "audited": audited, "sent": sent,
            "confirm": confirm, "conn": conn}


def _calls(set_stop):
    return [(c.args, c.kwargs) for c in set_stop.await_args_list]


CONFIRMED = {"id": REPLACEMENT_STOP, "stop_price": 165.57}


@pytest.mark.asyncio
async def test_the_pointer_is_refilled_with_the_confirmed_stop(monkeypatch):
    """THE FIX. Broker says a live stop covers the position, so the null this
    handler just wrote is known to be wrong — put the real order id back."""
    h = _wire(monkeypatch, replacement=CONFIRMED)

    await ts._handle_cancel_or_reject(_cancel_event(), "canceled", "live")

    repairs = [(a, k) for a, k in _calls(h["set_stop"])
               if k.get("reason") == "cancel_or_reject_restored"]
    assert len(repairs) == 1, f"expected exactly one repair: {_calls(h['set_stop'])}"
    args, kwargs = repairs[0]
    assert args == (TRADE_ID, REPLACEMENT_STOP)
    assert kwargs["account_mode"] == "live"


@pytest.mark.asyncio
async def test_the_null_above_is_still_unconditional(monkeypatch):
    """#600 fork 2's constraint, re-pinned from this side: the assume-naked null
    takes no guard. A compare-and-set there would leave a stale non-live id in
    place in exactly the case the fail-safe exists for."""
    h = _wire(monkeypatch, replacement=CONFIRMED)

    await ts._handle_cancel_or_reject(_cancel_event(), "canceled", "live")

    nulls = [(a, k) for a, k in _calls(h["set_stop"])
             if k.get("reason") == "cancel_or_reject_null"]
    assert len(nulls) == 1
    args, kwargs = nulls[0]
    assert args == (TRADE_ID, None)
    assert "expected_prior" not in kwargs


@pytest.mark.asyncio
async def test_the_repair_is_a_fill_never_an_overwrite(monkeypatch):
    """`expected_prior=None` is the whole safety property: the repair writes only
    while the column is still the NULL we wrote, so any concurrent writer wins and
    this can never clobber a pointer someone else has set."""
    h = _wire(monkeypatch, replacement=CONFIRMED)

    await ts._handle_cancel_or_reject(_cancel_event(), "canceled", "live")

    repair = next(k for a, k in _calls(h["set_stop"])
                  if k.get("reason") == "cancel_or_reject_restored")
    assert "expected_prior" in repair, "an unguarded repair could clobber a live pointer"
    assert repair["expected_prior"] is None


@pytest.mark.asyncio
async def test_no_confirmed_replacement_means_no_repair(monkeypatch):
    """POSITIVE EVIDENCE ONLY (#433). Genuinely naked: the broker found nothing,
    so the pointer stays NULL and the alarm fires exactly as before."""
    h = _wire(monkeypatch, replacement=None)

    await ts._handle_cancel_or_reject(_cancel_event(), "canceled", "live")

    assert not [k for _a, k in _calls(h["set_stop"])
                if k.get("reason") == "cancel_or_reject_restored"]
    assert any("unprotected" in m.lower() for m in h["sent"])


@pytest.mark.asyncio
async def test_a_deferred_repair_is_recorded_not_silent(monkeypatch):
    """Another writer set a pointer first — we defer to it, and say so. A no-repair
    that leaves no trace is indistinguishable from never having tried."""
    h = _wire(monkeypatch, replacement=CONFIRMED, set_stop_returns=False)

    await ts._handle_cancel_or_reject(_cancel_event(), "canceled", "live")

    rows = [r for r in h["audited"] if r[0] == "stop_pointer_repair_deferred"]
    assert len(rows) == 1
    payload = json.loads(rows[0][2])
    assert payload["trade_id"] == TRADE_ID
    assert payload["confirmed_replacement_id"] == REPLACEMENT_STOP
    assert payload["cancelled_order_id"] == CANCELLED_STOP


@pytest.mark.asyncio
async def test_a_successful_repair_writes_no_deferred_row(monkeypatch):
    """The ordinary path stays quiet, or the row is noise on every stop cycle
    instead of evidence of a real race."""
    h = _wire(monkeypatch, replacement=CONFIRMED)

    await ts._handle_cancel_or_reject(_cancel_event(), "canceled", "live")

    assert not [r for r in h["audited"] if r[0] == "stop_pointer_repair_deferred"]


@pytest.mark.asyncio
async def test_a_failing_repair_never_blocks_the_operator_message(monkeypatch):
    """The repair is bookkeeping. If it raises, the handler must still finish the
    move it was telling the operator about — the #501 lesson about an alarm that
    cannot render."""
    h = _wire(monkeypatch, replacement=CONFIRMED)

    async def _boom(*a, **k):
        if k.get("reason") == "cancel_or_reject_restored":
            raise RuntimeError("pointer write failed")
        return True

    monkeypatch.setattr(om, "set_stop_order_id", _boom)

    await ts._handle_cancel_or_reject(_cancel_event(), "canceled", "live")

    h["confirm"].assert_awaited()


# ── set_stop_order_id's own guard, in the direction this fix relies on ─────────


@pytest.mark.asyncio
async def test_set_stop_order_id_fill_blocks_when_the_column_is_no_longer_null(monkeypatch):
    """`expected_prior=None` compiles to `IS NOT DISTINCT FROM NULL` — no row back
    means someone filled the column first, and nothing was written."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)   # guard blocked
    conn.execute = AsyncMock()
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append(evt)

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", _audit)

    applied = await om.set_stop_order_id(
        TRADE_ID, REPLACEMENT_STOP, reason="cancel_or_reject_restored",
        account_mode="live", expected_prior=None,
    )

    assert applied is False
    assert "stop_order_id_changed" not in audited, (
        "a blocked write must not claim the pointer changed"
    )
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_set_stop_order_id_fill_writes_while_the_column_is_still_null(monkeypatch):
    """The ordinary repair: the column is the NULL we wrote, so the fill lands and
    is announced like any other pointer change."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=TRADE_ID)  # RETURNING id
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append(evt)

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", _audit)

    applied = await om.set_stop_order_id(
        TRADE_ID, REPLACEMENT_STOP, reason="cancel_or_reject_restored",
        account_mode="live", expected_prior=None,
    )

    assert applied is True
    assert audited == ["stop_order_id_changed"]
