"""#560 (2026-08-12) — informative stop-move Telegram text.

Operator got two content-free stop messages for PLTR ("Stop confirmed @ $150.15" /
"Stop replaced") and had to ask why. Answer: the 10/20-day moving-average trail
rose above his $149.05 entry and overtook the earlier breakeven stop. This pins:

1. exit_logic.ExitStep.stop_source correctly labels WHICH ladder input set
   effective_stop (hard_stop / trail / breakeven), and — the load-bearing
   invariant — effective_stop's VALUE is unaffected by adding the label (proven
   by diffing against the pre-existing exit_logic assertions, which still pass
   unmodified after this change).
2. describe_stop_move() (broker/order_manager.py) turns that label + the real
   PLTR numbers into the plain-English text the operator asked for, and infers
   the same conclusion when stop_source isn't available (trade_stream's WS path).
3. update_stop's retry-recovered "Stop confirmed" Telegram carries the reason
   and never a raw broker order id.
4. trade_stream's "Stop replaced" Telegram carries a reason too and never a raw
   broker order id (the prior text sliced `replacement['id'][:8]` into the
   operator-facing line — dropped per CLAUDE.md: internal ids are audit-only).
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.market_intelligence.broker import trade_stream as ts
from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step
from agents.market_intelligence.broker.order_manager import describe_stop_move
from tests.conftest import make_mock_pool

# Real PLTR numbers pulled from prod (trade id 307, 2026-08-12):
PLTR_ENTRY = 149.0545
PLTR_HARD_STOP = 143.28
PLTR_OLD_STOP = 149.05   # breakeven, set on an earlier partial
PLTR_NEW_STOP = 150.15   # what actually landed — the 10/20-day trail


def base_state(**overrides):
    state = {
        "alert_date": date(2026, 4, 1),
        "remaining_shares": 90,
        "entry_price": 100.0,
        "hard_stop": 95.0,
        "partial_taken": False,
        "breakeven_active": False,
        "exits": [],
        "running_closes": [],
    }
    state.update(overrides)
    return state


def bar(low, close):
    return {"l": low, "c": close, "h": max(low, close), "o": close}


# ── 1. exit_logic stop_source labels the winner without moving the number ────


def test_stop_source_hard_stop_when_nothing_else_beats_it():
    state = base_state(running_closes=[])
    step = apply_daily_exit_step(state, bar(96.0, 96.0), date(2026, 4, 2))
    assert step.stop_source == "hard_stop"
    assert step.effective_stop == 95.0  # unchanged arithmetic


def test_stop_source_trail_when_sma_wins():
    # 20 rising closes push SMA20 above both hard_stop and (inactive) breakeven.
    closes = [100.0 + i * 0.5 for i in range(20)]
    state = base_state(running_closes=closes, breakeven_active=False)
    step = apply_daily_exit_step(state, bar(109.0, 111.0), date(2026, 4, 2))
    assert step.stop_source == "trail"
    assert step.effective_stop == step.active_sma  # same value the old code returned


def test_stop_source_breakeven_when_entry_beats_a_lower_trail():
    # Trail below entry, breakeven active -> entry wins, labeled 'breakeven'.
    state = base_state(entry_price=100.0, hard_stop=95.0,
                        breakeven_active=True, running_closes=[98.0] * 12)
    step = apply_daily_exit_step(state, bar(97.0, 98.0), date(2026, 4, 2))
    assert step.stop_source == "breakeven"
    assert step.effective_stop == 100.0


def test_stop_source_trail_overtakes_breakeven_pltr_shape():
    """The PLTR case: breakeven is already active (entry=stop from an earlier
    partial), and TODAY's close pushes the trail above entry — trail should win
    and be labeled 'trail', not 'breakeven', even though breakeven is armed."""
    entry = 149.0545
    hard_stop = 143.28
    # 20 closes rising just enough that SMA20 lands above entry.
    closes = [148.0 + i * 0.2 for i in range(20)]
    state = base_state(entry_price=entry, hard_stop=hard_stop,
                        breakeven_active=True, running_closes=closes)
    step = apply_daily_exit_step(state, bar(151.5, 152.0), date(2026, 4, 2))
    assert step.active_sma > entry, "test setup must actually put the trail above entry"
    assert step.stop_source == "trail"
    assert step.effective_stop == step.active_sma


def test_effective_stop_arithmetic_is_byte_identical_across_all_sources():
    """The field is a label riding on the pre-existing max() chain — assert the
    VALUE for a few mixed scenarios matches hand computation regardless of which
    source wins, proving the label never feeds back into the number."""
    # hard_stop wins
    s1 = apply_daily_exit_step(base_state(running_closes=[]), bar(96.0, 96.0), date(2026, 4, 2))
    assert (s1.effective_stop, s1.stop_source) == (95.0, "hard_stop")
    # breakeven wins over a lower trail and a lower hard_stop
    s2 = apply_daily_exit_step(
        base_state(entry_price=100.0, hard_stop=90.0, breakeven_active=True,
                   running_closes=[96.0] * 12),
        bar(95.0, 96.0), date(2026, 4, 2),
    )
    assert (s2.effective_stop, s2.stop_source) == (100.0, "breakeven")


# ── 2. describe_stop_move — full context (live_tracker's path) ───────────────


def test_describe_stop_move_names_trail_and_states_locked_gain_pltr():
    text = describe_stop_move(
        entry_price=PLTR_ENTRY, hard_stop=PLTR_HARD_STOP,
        old_stop_price=PLTR_OLD_STOP, new_stop_price=PLTR_NEW_STOP,
        stop_source="trail",
    )
    assert "moving-average trail" in text
    assert f"${PLTR_ENTRY:.2f}" in text
    assert "if this stop fills" in text  # tied to the stop, not an absolute guarantee
    assert "win, not a loss" in text
    assert "R" in text  # R-multiple banked, in the operator's own terms
    # no raw ids, no pipe tables, no ticket-speak
    assert "|" not in text
    assert "`" not in text
    assert text[0].isupper()  # not a lowercase sentence fragment


def test_describe_stop_move_breakeven_source():
    text = describe_stop_move(
        entry_price=100.0, hard_stop=95.0, old_stop_price=95.0,
        new_stop_price=100.0, stop_source="breakeven",
    )
    assert "breakeven" in text
    assert "scratch" in text  # can't lose, can't yet be called a gain


# ── 3. describe_stop_move — inferred (trade_stream's decoupled WS path) ──────


def test_describe_stop_move_infers_trail_without_stop_source():
    text = describe_stop_move(
        entry_price=PLTR_ENTRY, hard_stop=PLTR_HARD_STOP,
        old_stop_price=PLTR_OLD_STOP, new_stop_price=PLTR_NEW_STOP,
        stop_source=None,
    )
    assert "moving-average trail" in text
    assert "win, not a loss" in text


def test_describe_stop_move_infers_refresh_when_price_unchanged():
    text = describe_stop_move(
        entry_price=100.0, hard_stop=90.0, old_stop_price=95.0,
        new_stop_price=95.0, stop_source=None,
    )
    assert "reissued" in text


def test_describe_stop_move_unchanged_price_above_entry_is_refresh_not_trail():
    """#560 advisor catch: a same-price morning re-issue whose price already sits
    ABOVE entry (from an earlier trail/breakeven move) must NOT be reported as
    "the trail just rose" — that move did not happen on this call. Checking
    unchanged-price first (see _infer_stop_source) is what this pins; before the
    fix this returned 'trail' text here because the entry-relative check ran
    first and 150.15 > 149.05 matched before the equal-price check did."""
    text = describe_stop_move(
        entry_price=PLTR_ENTRY, hard_stop=PLTR_HARD_STOP,
        old_stop_price=PLTR_NEW_STOP, new_stop_price=PLTR_NEW_STOP,  # old == new
        stop_source=None,
    )
    assert "reissued" in text
    assert "moving-average trail" not in text, (
        "an unchanged price must not be reported as a fresh trail move"
    )


def test_describe_stop_move_degrades_gracefully_with_no_new_price():
    # Mirrors the existing test mocks in test_475_... whose `replacement` dict
    # has no 'stop_price' key at all — must never raise.
    text = describe_stop_move(
        entry_price=None, hard_stop=None, old_stop_price=25.10, new_stop_price=None,
    )
    assert isinstance(text, str) and text


def test_describe_stop_move_brief_is_short_and_distinct_from_full():
    full = describe_stop_move(
        entry_price=PLTR_ENTRY, hard_stop=PLTR_HARD_STOP,
        old_stop_price=PLTR_OLD_STOP, new_stop_price=PLTR_NEW_STOP,
        stop_source="trail",
    )
    brief = describe_stop_move(
        entry_price=PLTR_ENTRY, hard_stop=PLTR_HARD_STOP,
        old_stop_price=PLTR_OLD_STOP, new_stop_price=PLTR_NEW_STOP,
        stop_source="trail", brief=True,
    )
    assert brief != full
    assert len(brief) < len(full), "the safety-net confirmation must not repeat the full explanation"
    assert f"${PLTR_ENTRY:.2f}" in brief  # still stands alone if it's the only message
    assert "win, not a loss" in brief
    assert "R banked" not in brief  # the R-multiple detail stays in the full (first) message only


# ── 4. update_stop's retry-recovered Telegram carries the reason, no raw id ──


TRADE_ID = 307
TICKER = "PLTR"


def _pltr_trade(**overrides):
    t = {
        "id": TRADE_ID, "ticker": TICKER, "remaining_shares": 4,
        "stop_price": PLTR_OLD_STOP, "stop_order_id": "old_leg_id",
        "account_mode": "live", "signal_type": "magna53",
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    t.update(overrides)
    return t


def _make_pool(trade):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=trade)
    conn.fetchval = AsyncMock(return_value=0)  # get_pending_exit_qty -> 0 held
    conn.execute = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool


@pytest.mark.asyncio
async def test_update_stop_retry_recovered_telegram_names_the_trail_no_raw_id():
    import agents.market_intelligence.broker.order_manager as om

    trade = _pltr_trade()
    pool = _make_pool(trade)
    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    place_calls = {"n": 0}

    async def _place_fake(**kwargs):
        place_calls["n"] += 1
        if place_calls["n"] == 1:
            raise RuntimeError("insufficient qty available for order")
        return {"id": "dd9ed021-a657-473a-abec-0aeec464fa80", "status": "accepted"}

    async def _get_order_fake(order_id, account_mode=None):
        # Old leg still live, below the new price -> raise-only floor lets the move through.
        return {"id": order_id, "status": "accepted", "stop_price": PLTR_OLD_STOP}

    with ExitStack() as stack:
        for p in [
            patch.object(om, "get_pool", AsyncMock(return_value=pool)),
            patch.object(om, "log_audit_event", AsyncMock()),
            patch.object(om, "send_telegram_message", _capture),
            patch.object(om, "set_stop_order_id", AsyncMock()),
            patch.object(om.asyncio, "sleep", AsyncMock()),
            patch.object(om.alpaca, "get_order", _get_order_fake),
            patch.object(om.alpaca, "cancel_order", AsyncMock(return_value=True)),
            patch.object(om.alpaca, "place_stop_order", _place_fake),
            patch.object(om.alpaca, "make_client_order_id",
                         lambda m, s, t: f"apollo_{m}_{s}_{t}_x"),
        ]:
            stack.enter_context(p)

        ok = await om.update_stop(TRADE_ID, PLTR_NEW_STOP, stop_source="trail")

    assert ok is True
    confirmed = [m for m in sent if "Stop confirmed" in m]
    assert len(confirmed) == 1, f"expected exactly one confirm Telegram, got: {sent}"
    msg = confirmed[0]
    assert "moving-average trail" in msg
    assert "win, not a loss" in msg
    assert f"${PLTR_NEW_STOP:.2f}" in msg
    assert "dd9ed021" not in msg, "raw broker order id must not reach the operator"
    assert "|" not in msg


# ── 5. trade_stream's WS safety-net "Stop replaced" Telegram ─────────────────


def _ws_data(order_id: str = "stop-old-1", symbol: str = "PLTR"):
    return SimpleNamespace(order=SimpleNamespace(id=order_id, symbol=symbol))


@pytest.mark.asyncio
async def test_stop_replaced_telegram_has_reason_and_no_raw_id(monkeypatch):
    """Mirrors tests/test_475_alert_noise_and_rejection_telemetry.py's harness
    (which this change must not break — pinned there separately) but with
    entry_price/hard_stop present, and a replacement carrying a real stop_price,
    to check the NEW content this card adds."""
    pool, conn = make_mock_pool()
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    conn.fetchrow = AsyncMock(side_effect=[None, stop_row])
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)

    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "send_telegram_message", _capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    replaced = [m for m in sent if "Stop replaced" in m]
    assert len(replaced) == 1, f"expected exactly one, got: {sent}"
    msg = replaced[0]
    assert "moving-average trail" in msg
    assert "win, not a loss" in msg
    assert "dd9ed021" not in msg, "raw broker order id must not reach the operator"
    assert "safety check" in msg.lower() or "safety-net" in msg.lower() or \
        "confirms" in msg.lower(), "message should say why THIS check exists"
    assert "unprotected" not in msg.lower()
    # #560 review: A and B must not duplicate a whole paragraph verbatim — B's
    # reason line is the brief form (short, no R-multiple, no repeated "if this
    # stop fills" clause structure identical to A's).
    assert "R banked" not in msg
    assert "banked beyond breakeven" not in msg
