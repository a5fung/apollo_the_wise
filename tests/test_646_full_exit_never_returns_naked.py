"""A failed full exit may leave the position OPEN. It may never leave it UNPROTECTED.

WHY (2026-09-11, OKTA, LIVE MONEY). The SMA trail fired at the close, `execute_full_exit` cancelled
the protective stop, and the sell was rejected — all inside one second:

    16:45:00  Full exit: cancelled stop 2f5ac5cb... (success=True)
    16:45:00  Failed to close position: available 0, held_for_orders 2
    16:45:00  WS event: canceled | OKTA          <- the cancel CONFIRMATION lands after

Alpaca acknowledges a cancel immediately but does not release `held_for_orders` until it settles,
so the very next call is rejected for insufficient quantity. **The cancel did not fail; the sell
raced it.** The function then sent one Telegram and returned False with the stop gone: 2 shares
naked from Friday 16:45, with no scheduled repair until Monday 09:31 — about 64 hours.

⚠ The #600 WS restore did NOT cover this. It keys off a PENDING exit order, and an exit that was
rejected never creates one — so the safety net cannot see the case that needs it most. The fix
belongs where the failure is known: inside `execute_full_exit`.

Alpaca has no atomic cancel-and-close for a single symbol (`close_position` takes no
`cancel_orders` flag; only `close_all_positions` does, and closing the whole book is not an option),
so cancel → wait → sell is the only available shape.
"""
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import order_manager as om

STOP_PRICE = 165.57
SHARES = 2


def _wire(monkeypatch, *, close_raises, available=SHARES, place_ok=True):
    """Minimal harness: a trade with a live stop, and an alpaca whose close either works or not."""
    trade = {"id": 382, "ticker": "OKTA", "remaining_shares": SHARES,
             "stop_price": STOP_PRICE, "stop_order_id": "stop-1", "account_mode": "live"}

    class _Conn:
        async def fetchrow(self, q, *a):
            return trade if "mi_live_trades" in q else None
        async def execute(self, *a, **k):
            return "UPDATE 1"
        async def fetchval(self, *a, **k):
            return None

    class _Acq:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self, *a, **k): return _Acq()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(om, "current_account_mode", lambda: "live")
    sent = []
    monkeypatch.setattr(om, "send_telegram_message",
                        AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "mode_prefix", lambda m: "")

    cancel = AsyncMock(return_value=True)
    close = AsyncMock(side_effect=Exception("insufficient qty available") if close_raises
                      else None, return_value={"id": "sell-1"})
    place = AsyncMock(return_value={"id": "stop-2"} if place_ok else {})
    position = AsyncMock(return_value={"qty": SHARES, "qty_available": available})
    monkeypatch.setattr(om.alpaca, "cancel_order", cancel)
    monkeypatch.setattr(om.alpaca, "close_position", close)
    monkeypatch.setattr(om.alpaca, "place_stop_order", place)
    monkeypatch.setattr(om.alpaca, "get_position", position)
    monkeypatch.setattr(om, "_EXIT_RELEASE_SLEEP_S", 0)
    return {"cancel": cancel, "close": close, "place": place, "pos": position, "sent": sent}


@pytest.mark.asyncio
async def test_the_okta_case_a_rejected_sell_restores_the_stop(monkeypatch):
    """THE REGRESSION. Before the fix this returned False with nothing in place."""
    h = _wire(monkeypatch, close_raises=True)
    ok = await om.execute_full_exit(382, "sma_trail_stop")
    assert ok is False, "a rejected sell must still report failure"
    h["place"].assert_awaited_once()
    assert h["place"].await_args.args[2] == STOP_PRICE, "restored at the wrong price"
    assert h["place"].await_args.args[1] == SHARES


@pytest.mark.asyncio
async def test_the_page_says_the_position_is_protected_again(monkeypatch):
    """He acts on the Telegram, so the Telegram must say which state he is in."""
    h = _wire(monkeypatch, close_raises=True)
    await om.execute_full_exit(382, "sma_trail_stop")
    # ⚠ "RESTORED" alone is a substring of "STOP NOT RESTORED" — asserting it passes in BOTH
    # states, which is a test that cannot fail. Assert the positive sentence.
    assert any("Stop RESTORED" in m and "NOT RESTORED" not in m for m in h["sent"]), h["sent"]
    assert any("protected" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_failed_restore_says_UNPROTECTED_loudly(monkeypatch):
    """The one case where he must act himself — it may never be reported as routine."""
    h = _wire(monkeypatch, close_raises=True, place_ok=False)
    await om.execute_full_exit(382, "sma_trail_stop")
    assert any("UNPROTECTED" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_successful_exit_does_not_re_place_a_stop(monkeypatch):
    """The fix must not resurrect a stop on a position that actually closed."""
    h = _wire(monkeypatch, close_raises=False)
    await om.execute_full_exit(382, "sma_trail_stop")
    h["place"].assert_not_awaited()


@pytest.mark.asyncio
async def test_it_waits_for_the_broker_to_free_the_shares_before_selling(monkeypatch):
    """The race itself: the shares are held when the cancel returns, so do not sell yet."""
    h = _wire(monkeypatch, close_raises=False, available=0)
    await om.execute_full_exit(382, "sma_trail_stop")
    assert h["pos"].await_count >= om._EXIT_RELEASE_ATTEMPTS, (
        "it sold without waiting for the shares to be released")


@pytest.mark.asyncio
async def test_the_wait_is_an_optimisation_never_a_gate(monkeypatch):
    """A broker that reports oddly must NOT be able to block an exit — still try the sell."""
    h = _wire(monkeypatch, close_raises=False, available=0)
    await om.execute_full_exit(382, "sma_trail_stop")
    h["close"].assert_awaited_once()


# ── A rejected exit must leave a ROW, not just a Telegram (#646 (d), 2026-09-11) ──────────────
#
# Reconstructing tonight's incident meant reading container logs an hour later and inferring the
# rest, because the rejection wrote nothing to mi_audit_log. A money-path failure that exists only
# in a chat message is the same recording gap as #184's four unexplained June cancels — those are
# permanently unknowable now, because container logs rotate.

@pytest.mark.asyncio
async def test_a_rejected_exit_writes_an_audit_row(monkeypatch):
    rows = []
    monkeypatch.setattr(om, "log_audit_event",
                        AsyncMock(side_effect=lambda e, s, d=None, **k: rows.append((e, s, d))))
    _wire(monkeypatch, close_raises=True)
    await om.execute_full_exit(382, "sma_trail_stop")
    assert any(e == "full_exit_rejected" for e, *_ in rows), [r[0] for r in rows]


@pytest.mark.asyncio
async def test_the_row_carries_what_a_diagnosis_needs(monkeypatch):
    """Ticker, reason, shares and the broker's own error — so the next one is one query, not an hour."""
    import json as _json
    rows = []
    monkeypatch.setattr(om, "log_audit_event",
                        AsyncMock(side_effect=lambda e, s, d=None, **k: rows.append((e, s, d))))
    _wire(monkeypatch, close_raises=True)
    await om.execute_full_exit(382, "sma_trail_stop")
    detail = _json.loads(next(d for e, _s, d in rows if e == "full_exit_rejected"))
    assert detail["ticker"] == "OKTA"
    assert detail["reason"] == "sma_trail_stop"
    assert detail["shares"] == SHARES
    assert detail["stop_price"] == STOP_PRICE
    assert "insufficient qty" in detail["error"]


@pytest.mark.asyncio
async def test_a_failed_audit_write_does_not_swallow_the_restore(monkeypatch):
    """The row is the diagnosis; the restore is the money. The row may never cost the restore."""
    monkeypatch.setattr(om, "log_audit_event", AsyncMock(side_effect=Exception("db down")))
    h = _wire(monkeypatch, close_raises=True)
    await om.execute_full_exit(382, "sma_trail_stop")
    h["place"].assert_awaited_once()
