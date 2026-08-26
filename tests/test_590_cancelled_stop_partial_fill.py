"""#590 — a cancelled STOP LEG's partial fill must reach `exits`.

THE DEFECT, from the book-wide audit (`scripts/probes/_588_exit_share_audit.sql`,
read-only prod capture 2026-08-24): FPS (paper, trade 183, 2026-06-01) entered 163
shares and records ONE 28-share exit leg. 135 shares — an 81-share fill on a
CANCELLED stop plus a 54-share reduction — never reached `exits`, under-stating the
trade by at least $273.

THE WRITE SITE. `_handle_cancel_or_reject` section 2 is the stop-leg cancel path:
it nulls `stop_order_id`, decides whether to alarm, and returns — never once
reading `order.filled_qty`. `partially_filled` is a LIVE stop status, and our own
machinery cancels live stops routinely (the #508 leg-safe reduce, the #523 widen,
the breakeven replace, EOD cleanup), so a stop that has partly filled at the moment
it is cancelled is an ordinary shape. #566 added exactly this commit for a
cancelled PARTIAL-EXIT order (section 3) and not for the stop leg — which is the
primary cancel path for every live trade, paper and live alike.

⚠ ORDERING IS LOAD-BEARING. Everything after the commit reasons about how many
shares are still exposed. `remaining_shares` captured before the commit is stale,
so the "Position unprotected (N sh)" alarm would name shares that were just sold —
or alarm at all on a position the fill closed. The commit happens FIRST and the row
is re-read.

`finalize_stop_fill` is idempotent per `order_id`, so a racing terminal-fill event
cannot double-commit, and it DECREMENTS rather than closing (the #566 accounting
fix) unless the fill exhausts the position.

Mocking mirrors `tests/test_oco_cancel_handler_566.py`.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import json
import pytest

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts

from tests.conftest import make_mock_pool


# FPS's real numbers: 163 entered, the stop cancelled carrying an 81-share fill.
FPS_TRADE_ID = 183
FPS_STOP_ID = "fps-stop-1"
FPS_FILLED = 81.0
FPS_FILL_PX = 59.50


def _cancel_data(*, filled_qty=FPS_FILLED, avg=FPS_FILL_PX, order_id=FPS_STOP_ID):
    order = SimpleNamespace(
        id=order_id, symbol="FPS", status="canceled",
        filled_qty=filled_qty, filled_avg_price=avg, qty=109.0, side="sell",
        type="stop", limit_price=None, stop_price=51.0,
        canceled_at=None, failed_at=None, expired_at=None, updated_at=None,
    )
    return SimpleNamespace(order=order, event="canceled", reason=None)


def _stop_trade(remaining=109.0):
    return {"id": FPS_TRADE_ID, "ticker": "FPS", "remaining_shares": remaining,
            "stop_price": 51.0, "entry_price": 53.79, "hard_stop": 51.0}


def _after(remaining, status="filled"):
    return {"id": FPS_TRADE_ID, "ticker": "FPS", "remaining_shares": remaining,
            "stop_price": 51.0, "entry_price": 53.79, "hard_stop": 51.0,
            "status": status}


def _wire(monkeypatch, *, stop_trade_row, after_row):
    """fetchrow order in section 2: entry-trade lookup (None), stop-trade lookup,
    then — only once #590's commit fires — the post-commit re-read."""
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=[None, stop_trade_row, after_row])
    conn.fetch = AsyncMock(return_value=[])       # the naked-alarm evidence pool
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
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0.0)
    # No replacement stop exists — the genuinely-unprotected branch, which is
    # where the stale share count would have been printed.
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop",
                        AsyncMock(return_value=None))

    finalize_mock = AsyncMock()
    set_stop_mock = AsyncMock()
    monkeypatch.setattr(om, "finalize_stop_fill", finalize_mock)
    monkeypatch.setattr(om, "set_stop_order_id", set_stop_mock)

    return {"conn": conn, "audited": audited, "sent": sent,
            "finalize": finalize_mock, "set_stop": set_stop_mock}


@pytest.mark.asyncio
async def test_cancelled_stop_partial_fill_is_committed_to_exits(monkeypatch):
    """FPS's 81 shares. The cancel event carries them; the handler must commit
    them through `finalize_stop_fill` (which appends the exit leg and decrements
    remaining_shares) instead of dropping them on the floor.

    MUTATION PROOF: delete the `_cancel_filled > 0` commit block in
    `_handle_cancel_or_reject` section 2 and this test goes red."""
    h = _wire(monkeypatch, stop_trade_row=_stop_trade(109.0),
              after_row=_after(28.0))

    await ts._handle_cancel_or_reject(_cancel_data(), "canceled", "paper")

    h["finalize"].assert_awaited_once_with(
        FPS_TRADE_ID, int(FPS_FILLED), FPS_FILL_PX, FPS_STOP_ID)
    committed = next(d for e, _, d in h["audited"]
                     if e == "stop_cancel_partial_fill_committed")
    assert json.loads(committed)["filled_qty"] == FPS_FILLED


@pytest.mark.asyncio
async def test_the_alarm_names_the_shares_left_after_the_commit_not_before(monkeypatch):
    """ORDERING. 109 shares were exposed before the fill, 28 after it. An alarm
    quoting 109 would send the operator looking for shares that had just been
    sold — the same stale-count class as the MRNA 'Position unprotected' that
    showed a pre-partial share count."""
    h = _wire(monkeypatch, stop_trade_row=_stop_trade(109.0),
              after_row=_after(28.0))

    await ts._handle_cancel_or_reject(_cancel_data(), "canceled", "paper")

    unprotected = [m for m in h["sent"] if "unprotected" in m.lower()]
    assert unprotected, f"expected the naked alarm, got: {h['sent']!r}"
    assert "28 sh" in unprotected[0], unprotected[0]
    assert "109 sh" not in unprotected[0]


@pytest.mark.asyncio
async def test_a_fill_that_closes_the_position_raises_no_naked_alarm(monkeypatch):
    """When the cancelled stop's fill exhausts the position there is nothing left
    to protect. Alarming here would be a false 'unprotected' on a flat book, and
    nulling the stop pointer on a closed row is pointless churn."""
    h = _wire(monkeypatch, stop_trade_row=_stop_trade(81.0),
              after_row=_after(0.0, status="closed"))

    await ts._handle_cancel_or_reject(_cancel_data(), "canceled", "paper")

    h["finalize"].assert_awaited_once()
    h["set_stop"].assert_not_awaited()
    assert not [m for m in h["sent"] if "unprotected" in m.lower()], h["sent"]


@pytest.mark.asyncio
async def test_an_unfilled_cancelled_stop_behaves_exactly_as_before(monkeypatch):
    """The ordinary case — a stop cancelled having sold nothing — must be
    byte-for-byte unchanged: no commit, no extra audit row, the pointer nulled and
    the alarm raised off the row as read."""
    h = _wire(monkeypatch, stop_trade_row=_stop_trade(163.0), after_row=None)

    await ts._handle_cancel_or_reject(
        _cancel_data(filled_qty=0.0, avg=None), "canceled", "paper")

    h["finalize"].assert_not_awaited()
    assert not any(e == "stop_cancel_partial_fill_committed" for e, *_ in h["audited"])
    h["set_stop"].assert_awaited_once()
    unprotected = [m for m in h["sent"] if "unprotected" in m.lower()]
    assert unprotected and "163 sh" in unprotected[0]
