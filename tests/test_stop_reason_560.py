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

import json
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
    assert "a fill here" in text  # tied to the stop, not an absolute guarantee
    assert "banks" in text
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
    assert "banks" in text


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
    assert "banks" in brief
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
    assert "banks" in msg
    assert f"${PLTR_NEW_STOP:.2f}" in msg
    assert "dd9ed021" not in msg, "raw broker order id must not reach the operator"
    assert "|" not in msg


# ── 5. trade_stream's WS safety-net "Stop replaced" Telegram ─────────────────


def _ws_data(order_id: str = "stop-old-1", symbol: str = "PLTR"):
    return SimpleNamespace(order=SimpleNamespace(id=order_id, symbol=symbol))


def _make_ws_pool(stop_row, db_match_row, replacement, dup_rows=None):
    """Shared harness: entry-lookup miss (fetchrow #1), stop-leg lookup hit
    (#2), then `db_match_row` feeds the agreement re-check's mi_live_trades
    re-read (fetchrow #3) — the DB-match half of the agreement test.
    `db_match_row` may be an Exception instance — AsyncMock's side_effect
    raises it in place, exercising the re-check's own fail-safe path.
    `dup_rows` (only consulted when `db_match_row` matches `replacement`)
    feeds `conn.fetch`, modelling the mi_audit_log duplicate-evidence rows
    as raw {"detail": <json text>} dicts — the shape the real handler reads
    and parses in Python. Pass a callable instead of a list to make the
    `.fetch()` call itself raise."""
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=[None, stop_row, db_match_row])
    if callable(dup_rows):
        conn.fetch = AsyncMock(side_effect=dup_rows)
    else:
        conn.fetch = AsyncMock(return_value=dup_rows or [])
    conn.execute = AsyncMock()
    audit = AsyncMock()
    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    return pool, conn, audit, sent, _capture


@pytest.mark.asyncio
async def test_stop_replaced_telegram_has_reason_and_no_raw_id(monkeypatch):
    """Mirrors tests/test_475_alert_noise_and_rejection_telemetry.py's harness
    (which this change must not break — pinned there separately) but with
    entry_price/hard_stop present, and a replacement carrying a real stop_price,
    to check the NEW content this card adds.

    The DB's fresh agreement re-check (3rd fetchrow) intentionally returns the
    OLD stop still on file — order_manager's own write has not landed yet. This
    is the clean-race path where the WS safety-net message is the operator's
    ONLY notice of the move, so it must still speak."""
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    not_yet_updated = {"stop_order_id": "old_leg_id", "stop_price": PLTR_OLD_STOP}
    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    pool, conn, audit, sent, capture = _make_ws_pool(stop_row, not_yet_updated, replacement)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    replaced = [m for m in sent if "Stop replaced" in m]
    assert len(replaced) == 1, f"expected exactly one, got: {sent}"
    msg = replaced[0]
    assert "moving-average trail" in msg
    assert "banks" in msg
    assert "dd9ed021" not in msg, "raw broker order id must not reach the operator"
    assert "safety check" in msg.lower() or "safety-net" in msg.lower() or \
        "confirms" in msg.lower(), "message should say why THIS check exists"
    assert "unprotected" not in msg.lower()
    # #560 review: A and B must not duplicate a whole paragraph verbatim — B's
    # reason line is the brief form (short, no R-multiple, no repeated "if this
    # stop fills" clause structure identical to A's).
    assert "R banked" not in msg
    assert "beyond breakeven" not in msg
    assert not any(c.args[0] == "stop_replacement_confirmed_silent"
                   for c in audit.await_args_list), "disagreement must not log the silent event"


# ── 6. WS safety-net SUPPRESSED when it agrees with the DB (the duplicate fix)

# Operator: "can we combine these two msg? I get two Everytime stop moves."
# order_manager's retry-recovered "Stop confirmed" and this WS safety-net's
# "Stop replaced" fire independently for the SAME move. Fix: do not merge the
# text — suppress the WS one when a duplicate genuinely exists: the trade's
# OWN row already carries this exact order id + price AND a
# stop_update_retry_succeeded audit row proves order_manager's Telegram-
# sending branch actually fired for this exact order (review catch: DB
# agreement ALONE is not enough — the ordinary happy-path stop move commits
# the same DB write but order_manager sends NO Telegram at all, so matching
# only the DB would silence the operator's ONLY message on that path). Any
# daylight — DB not caught up, a different price, a mismatched/missing order
# id, no matching retry-succeeded row, or the re-check itself erroring — must
# still speak (fail-safe, never a silent swallow of real news).


@pytest.mark.asyncio
async def test_stop_replaced_telegram_silenced_when_db_and_telegram_evidence_agree(monkeypatch):
    """order_manager already wrote this exact order id + price to the trade's
    row AND left the stop_update_retry_succeeded audit trail proving its own
    'Stop confirmed' Telegram fired for this exact order — the WS safety-net
    must send NOTHING, only an audit row."""
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    already_recorded = {"stop_order_id": replacement["id"], "stop_price": PLTR_NEW_STOP}
    # The real audit row order_manager writes at order_manager.py:1591-1599,
    # immediately before its own "Stop confirmed" Telegram.
    dup_rows = [{"detail": json.dumps({
        "trade_id": 307, "ticker": "PLTR",
        "new_stop_price": PLTR_NEW_STOP, "new_stop_id": replacement["id"],
    })}]
    pool, conn, audit, sent, capture = _make_ws_pool(
        stop_row, already_recorded, replacement, dup_rows=dup_rows)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    assert sent == [], f"agreeing safety-net check must send nothing, got: {sent}"
    silent_events = [c for c in audit.await_args_list
                      if c.args[0] == "stop_replacement_confirmed_silent"]
    assert len(silent_events) == 1, f"must log exactly one silent-confirm audit row: {audit.await_args_list}"
    detail = json.loads(silent_events[0].args[2])
    assert detail["trade_id"] == 307
    assert detail["replacement_order_id"] == replacement["id"]
    assert detail["replacement_stop_price"] == PLTR_NEW_STOP


@pytest.mark.asyncio
async def test_stop_replaced_telegram_speaks_when_db_agrees_but_no_telegram_was_sent(monkeypatch):
    """THE REGRESSION CASE (review catch): DB shows this exact order id + price
    (order_manager's ordinary, non-retry write landed) but there is NO
    stop_update_retry_succeeded audit row — meaning order_manager took the
    SILENT happy-path branch and sent no Telegram at all. This WS message is
    the operator's ONLY notice of the move and must still speak; DB agreement
    alone must never suppress it."""
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    already_recorded = {"stop_order_id": replacement["id"], "stop_price": PLTR_NEW_STOP}
    pool, conn, audit, sent, capture = _make_ws_pool(
        stop_row, already_recorded, replacement, dup_rows=[])  # no matching audit row found
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    assert any("Stop replaced" in m for m in sent), (
        f"DB agreement without proof a Telegram was sent must still speak "
        f"(the ordinary happy-path move has no other message): {sent}"
    )
    assert not any(c.args[0] == "stop_replacement_confirmed_silent"
                   for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_stop_replaced_telegram_speaks_when_price_differs_from_db(monkeypatch):
    """Same order id, but the DB's recorded price does not match what the
    broker just confirmed — a genuine mismatch, must still speak (never
    silently swallowed)."""
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    # Same order id, price clearly off (well outside the cent-level epsilon) —
    # pins that price is actually compared, not just the order id.
    mismatched = {"stop_order_id": replacement["id"], "stop_price": PLTR_NEW_STOP - 0.05}
    pool, conn, audit, sent, capture = _make_ws_pool(stop_row, mismatched, replacement)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    assert any("Stop replaced" in m for m in sent), f"price mismatch must still speak: {sent}"
    assert not any(c.args[0] == "stop_replacement_confirmed_silent"
                   for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_stop_replaced_telegram_speaks_when_order_id_differs(monkeypatch):
    """Same price, but a DIFFERENT order id on file — not proof this is the
    order the trade actually depends on. Must still speak."""
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    other_order = {"stop_order_id": "some-other-order-id", "stop_price": PLTR_NEW_STOP}
    pool, conn, audit, sent, capture = _make_ws_pool(stop_row, other_order, replacement)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    assert any("Stop replaced" in m for m in sent), f"order-id mismatch must still speak: {sent}"


@pytest.mark.asyncio
async def test_stop_replaced_telegram_speaks_when_agreement_recheck_errors(monkeypatch):
    """The fresh DB re-read itself fails (transient DB blip) — fail-safe means
    still notify, exactly like #433's broker-read fail-safe above it."""
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    pool, conn, audit, sent, capture = _make_ws_pool(
        stop_row, RuntimeError("db connection reset"), replacement)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    assert any("Stop replaced" in m for m in sent), f"a failed re-check must still speak: {sent}"
    assert not any(c.args[0] == "stop_replacement_confirmed_silent"
                   for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_stop_replaced_telegram_speaks_when_dup_evidence_fetch_errors(monkeypatch):
    """The DB half of the check agrees, but the mi_audit_log lookup itself
    raises (transient DB blip on the SECOND query) — fail-safe still speaks."""
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    already_recorded = {"stop_order_id": replacement["id"], "stop_price": PLTR_NEW_STOP}
    pool, conn, audit, sent, capture = _make_ws_pool(
        stop_row, already_recorded, replacement,
        dup_rows=RuntimeError("db connection reset"))
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    assert any("Stop replaced" in m for m in sent), f"a failed audit-log read must still speak: {sent}"
    assert not any(c.args[0] == "stop_replacement_confirmed_silent"
                   for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_stop_replaced_telegram_silenced_despite_unrelated_malformed_audit_rows(monkeypatch):
    """Pins the robustness reason for matching in Python: the 5-minute window
    can contain OTHER event types whose `detail` is '' (the log_audit_event
    2-arg default) or otherwise not JSON. One bad row must not block finding
    the real match sitting alongside it — it is skipped, not fatal."""
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    already_recorded = {"stop_order_id": replacement["id"], "stop_price": PLTR_NEW_STOP}
    dup_rows = [
        {"detail": ""},                       # a bar_stream_disconnect-shaped row
        {"detail": "not json at all"},         # defensive: any other garbage
        {"detail": json.dumps({"trade_id": 999, "new_stop_id": "unrelated"})},
        {"detail": json.dumps({
            "trade_id": 307, "ticker": "PLTR",
            "new_stop_price": PLTR_NEW_STOP, "new_stop_id": replacement["id"],
        })},
    ]
    pool, conn, audit, sent, capture = _make_ws_pool(
        stop_row, already_recorded, replacement, dup_rows=dup_rows)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    assert sent == [], (
        f"a real match sitting alongside malformed/unrelated rows must still "
        f"suppress: {sent}"
    )
    assert any(c.args[0] == "stop_replacement_confirmed_silent"
               for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_stop_replaced_telegram_speaks_when_retry_evidence_is_for_a_different_order(monkeypatch):
    """Same trade_id, but the ONLY stop_update_retry_succeeded row in the
    window names a DIFFERENT new_stop_id — an earlier, unrelated stop move on
    the same trade. That is not proof the operator was told about THIS
    replacement; must still speak (pins that new_stop_id is actually checked,
    not just trade_id)."""
    stop_row = {
        "id": 307, "ticker": "PLTR", "remaining_shares": 4.0,
        "stop_price": PLTR_OLD_STOP,
        "entry_price": PLTR_ENTRY, "hard_stop": PLTR_HARD_STOP,
    }
    replacement = {"id": "dd9ed021-a657-473a-abec-0aeec464fa80",
                   "stop_price": PLTR_NEW_STOP}
    already_recorded = {"stop_order_id": replacement["id"], "stop_price": PLTR_NEW_STOP}
    dup_rows = [{"detail": json.dumps({
        "trade_id": 307, "ticker": "PLTR",
        "new_stop_price": 148.00, "new_stop_id": "some-earlier-unrelated-order-id",
    })}]
    pool, conn, audit, sent, capture = _make_ws_pool(
        stop_row, already_recorded, replacement, dup_rows=dup_rows)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[replacement])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")

    assert any("Stop replaced" in m for m in sent), (
        f"a retry-succeeded row for a DIFFERENT order must not suppress: {sent}"
    )
    assert not any(c.args[0] == "stop_replacement_confirmed_silent"
                   for c in audit.await_args_list)
