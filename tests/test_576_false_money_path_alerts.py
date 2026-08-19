"""#576 (2026-08-19, MRNA) -- two false money-path alerts in one morning.

Operator: "it's very confusing and adds noise." Both fired on MRNA, both were
WRONG, neither cost money -- which is exactly why they are corrosive: a
money-path alert that cries wolf trains him to discount the ones that matter.
Messaging-only fixes; no stop/size/order/entry/safeguard logic changed.

(a) A FILLED position reported as SKIPPED for a full book.
    `entry_pipeline.submit_trade_entry` STEP 6 (the #461 authoritative
    recount under the per-mode advisory cap lock) reads `open_count` and, if
    it is at cap, blocks with `cap_block_reason` ("Max open positions
    reached") -- WITHOUT checking whether the row that filled the cap is
    THIS candidate's own sibling. A same-ticker racer whose bar-fetch stalls
    (the #475 dual bar_stream/cron ORB trigger) can reach STEP 6 AFTER its
    own earlier attempt has already filled the last slot -- and the losing
    racer then reads "max positions reached" on a name we already own. Fix:
    check for a same-ticker/alert_date/account_mode row BEFORE the cap
    short-circuit, so a self-duplicate always falls through to the INSERT's
    own `ON CONFLICT DO NOTHING` -> silent WINDOW_DUPLICATE (excluded from
    the ORB-skips digest), exactly like the "cap has room" sibling race
    already resolves (test_461_cap_toctou_race.py::
    test_same_ticker_conflict_still_window_duplicate_no_lock_leak). A cap
    block for a genuinely DIFFERENT ticker is completely unaffected.

(b) A 327-millisecond race reported as an unprotected position.
    `trade_stream._handle_cancel_or_reject`'s naked-position branch fires
    unconditionally whenever `_broker_confirm_replacement_stop` finds nothing
    -- and #566 recorded at ship time that `get_open_orders` HIDES a held OCO
    stop leg, so that broker-listing check can structurally miss a real, live
    replacement. The 2026-08-18 message merge fixed the sibling "Stop
    replaced" branch (`_agrees`) but not this one. Fix: extend the same
    positive-evidence idiom -- when `partial_exit_stop_telegram_pending`
    names this exact trade AND mi_live_trades' CURRENT stop_order_id/price
    corroborate that row's own claimed new stop, suppress; any doubt
    (missing evidence, wrong trade, stale/mismatched DB, a failed read)
    still alarms. THE CONSTRAINT THAT MATTERS MOST: a genuinely uncovered
    position must still alert -- proven below with zero evidence present.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import trade_stream as ts
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_MAX_POSITIONS,
    WINDOW_DUPLICATE,
)
from tests.test_461_cap_toctou_race import FakeDB, _wire, _submit
from tests.test_stop_reason_560 import _make_ws_pool, _ws_data
from unittest.mock import AsyncMock


# ═══════════════════════════════════════════════════════════════════════════
# (a) entry_pipeline STEP 6 -- a self-race duplicate must never read as a
#     position-cap skip
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_self_race_duplicate_never_renders_as_cap_reached(monkeypatch):
    """4 seeded live positions (cap=5) + 2 racers for the SAME ticker,
    synchronized past STEP 1's dedup check by the shared bar-fetch barrier
    (mirrors test_461's own same-ticker race, but with the cap EXACTLY
    exhausted by the winning racer instead of having room to spare). The
    winner fills the last slot; the loser is a duplicate of ITSELF and must
    resolve WINDOW_DUPLICATE (silent, excluded from the ORB-skips digest),
    never BLOCK_MAX_POSITIONS -- that reads as a missed trade on a stock
    already in the book, which is the exact MRNA complaint.

    MUTATION-PROOF: swapping the fix's `if _self_row_exists: pass elif
    open_count >= CAP: ...` back to the pre-fix `if open_count >= CAP: ...`
    (dropping the self-row check entirely) turns the loser's action back
    into ACTION_BLOCKED with `block:max_positions: 5/5 (mode=live)` --
    verified by hand, then restored (see report)."""
    db = FakeDB()
    db.seed(4, mode="live")
    sent, audit = _wire(monkeypatch, db, n_racers=2)

    results = await asyncio.wait_for(
        asyncio.gather(_submit("MRNA"), _submit("MRNA")), timeout=10,
    )

    assert len(db.countable("live")) == 5, "cap must still hold at exactly 5"
    actions = sorted(r["action"] for r in results)
    assert actions == sorted([ep.ACTION_AUTO_ENTERED, ep.ACTION_SKIPPED]), (
        f"the losing MRNA racer must resolve as a silent duplicate, not a "
        f"cap block: {results}"
    )
    dup = next(r for r in results if r["action"] == ep.ACTION_SKIPPED)
    assert dup["reason"] == WINDOW_DUPLICATE
    assert not any(
        isinstance(r.get("reason"), str) and r["reason"].startswith(BLOCK_MAX_POSITIONS)
        for r in results
    ), f"MRNA must never see its own fill reported back as a cap block: {results}"


@pytest.mark.asyncio
async def test_genuinely_different_ticker_still_blocked_at_cap(monkeypatch):
    """Control: a real cap block for a DIFFERENT ticker must be completely
    unaffected by the #576 fix -- this is not a loosening of the cap."""
    db = FakeDB()
    db.seed(5, mode="live")  # already full
    sent, audit = _wire(monkeypatch, db, n_racers=1)

    result = await asyncio.wait_for(_submit("ZZZZ"), timeout=5)

    assert result["action"] == ep.ACTION_BLOCKED
    assert result["reason"] == f"{BLOCK_MAX_POSITIONS}: 5/5 (mode=live)"


# ═══════════════════════════════════════════════════════════════════════════
# (b) trade_stream naked branch -- positive-evidence suppression
#
# Corroborates between TWO independently-written, IMMUTABLE mi_audit_log
# rows (`partial_exit_breakeven_armed` + `partial_exit_stop_telegram_pending`)
# rather than a live re-read of mi_live_trades.stop_order_id -- THIS SAME
# HANDLER unconditionally nulls that column a few lines above
# (`cancel_or_reject_null`, no compare-and-set) the instant the cancel event
# arrives, so a DB-anchored corroboration could be silently clobbered by the
# handler's own earlier write depending on WS-delivery timing. Two audit
# rows this handler never writes to can't be self-clobbered.
# ═══════════════════════════════════════════════════════════════════════════

TRADE_ID = 850
TICKER = "MRNA"
NEW_STOP_ID = "b09cf0c5-be-stop"
NEW_STOP_PRICE = 120.75
OLD_STOP_ID = "old-4sh-stop"


def _mrna_stop_row(remaining=4.0):
    return {
        "id": TRADE_ID, "ticker": TICKER, "remaining_shares": remaining,
        "stop_price": 118.00, "entry_price": 119.50, "hard_stop": 115.00,
    }


def _pending_row(trade_id=TRADE_ID, new_stop_id=NEW_STOP_ID, new_stop_price=NEW_STOP_PRICE):
    """The `partial_exit_stop_telegram_pending` audit row, written right
    before the merged Telegram that already covers this replacement."""
    return {"event_type": "partial_exit_stop_telegram_pending", "detail": json.dumps({
        "trade_id": trade_id, "new_stop_id": new_stop_id, "new_stop_price": new_stop_price,
    })}


def _armed_row(trade_id=TRADE_ID, new_stop_id=NEW_STOP_ID, stop_price=NEW_STOP_PRICE):
    """The `partial_exit_breakeven_armed` audit row, written ONLY after the
    broker POSITIVELY CONFIRMED the new stop is live (order_manager.py
    ~3465-3520's polling loop) -- note the field is `stop_price`, not
    `new_stop_price` (matches order_manager.py:3514-3519 exactly)."""
    return {"event_type": "partial_exit_breakeven_armed", "detail": json.dumps({
        "trade_id": trade_id, "new_stop_id": new_stop_id, "stop_price": stop_price,
    })}


async def _fire_naked_branch(monkeypatch, *, dup_rows):
    """Wires the WS handler so `_broker_confirm_replacement_stop` finds
    nothing on EITHER try (immediate + the #475 recheck) -- the exact
    condition that reaches the naked `else` branch. `dup_rows` feeds
    conn.fetch() -- the ONE query this branch now makes (both evidence
    event types in one SELECT); a callable makes the fetch itself raise
    (see tests/test_stop_reason_560.py::_make_ws_pool docstring)."""
    pool, conn, audit, sent, capture = _make_ws_pool(
        _mrna_stop_row(), None, None, dup_rows=dup_rows)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=[None, None])  # immediate + recheck both miss
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(
        _ws_data(order_id=OLD_STOP_ID, symbol=TICKER), "canceled", "live",
    )
    return sent, audit


@pytest.mark.asyncio
async def test_naked_alarm_suppressed_when_both_evidence_rows_agree(monkeypatch):
    """The MRNA shape: execute_partial_exit wrote BOTH its own
    broker-confirmed `partial_exit_breakeven_armed` row and the Telegram-
    pending row, naming the SAME new stop id + price -- two independently-
    written records agreeing with each other. Must suppress and audit the
    suppression exactly once."""
    sent, audit = await _fire_naked_branch(
        monkeypatch, dup_rows=[_pending_row(), _armed_row()])

    assert sent == [], f"agreeing evidence must suppress the naked alarm: {sent}"
    silent = [c for c in audit.await_args_list if c.args[0] == "naked_alarm_suppressed_silent"]
    assert len(silent) == 1, f"must audit the suppression exactly once: {audit.await_args_list}"
    detail = json.loads(silent[0].args[2])
    assert detail["trade_id"] == TRADE_ID
    assert detail["pending_new_stop_id"] == NEW_STOP_ID
    assert detail["armed_new_stop_id"] == NEW_STOP_ID
    assert detail["cancelled_order_id"] == OLD_STOP_ID


@pytest.mark.asyncio
async def test_genuinely_naked_position_still_alarms_with_no_evidence(monkeypatch):
    """THE CONSTRAINT THAT MATTERS MOST: no evidence rows exist at all (no
    partial exit ever ran for this trade) -- a real naked position. Must
    alarm exactly as before this fix, unconditionally."""
    sent, audit = await _fire_naked_branch(monkeypatch, dup_rows=[])

    unprotected = [m for m in sent if "unprotected" in m.lower()]
    assert len(unprotected) == 1, f"a genuinely naked position must still alarm: {sent}"
    assert "MRNA" in unprotected[0]
    assert not any(c.args[0] == "naked_alarm_suppressed_silent" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_naked_alarm_still_fires_with_only_the_pending_row(monkeypatch):
    """Only the Telegram-pending row exists -- the OTHER independently-
    written record (`partial_exit_breakeven_armed`) is missing, so there is
    nothing to corroborate against. A single uncorroborated row must not
    suppress."""
    sent, audit = await _fire_naked_branch(monkeypatch, dup_rows=[_pending_row()])

    assert any("unprotected" in m.lower() for m in sent), (
        f"an uncorroborated single row must still alarm: {sent}")
    assert not any(c.args[0] == "naked_alarm_suppressed_silent" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_naked_alarm_still_fires_with_only_the_armed_row(monkeypatch):
    """Only the breakeven-armed row exists -- the Telegram-pending row is
    missing (e.g. a non-triggered partial exit, which never writes it). Must
    still alarm -- one record alone is not the agreement this fix requires."""
    sent, audit = await _fire_naked_branch(monkeypatch, dup_rows=[_armed_row()])

    assert any("unprotected" in m.lower() for m in sent), (
        f"an uncorroborated single row must still alarm: {sent}")
    assert not any(c.args[0] == "naked_alarm_suppressed_silent" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_naked_alarm_still_fires_when_stop_ids_disagree_between_rows(monkeypatch):
    """Both rows exist for this trade, but name DIFFERENT new_stop_id values
    (e.g. a stale armed row from an earlier partial on the same trade) --
    not proof about THIS replacement. Must still alarm."""
    sent, audit = await _fire_naked_branch(
        monkeypatch,
        dup_rows=[_pending_row(), _armed_row(new_stop_id="some-earlier-stop-id")])

    assert any("unprotected" in m.lower() for m in sent), (
        f"disagreeing stop ids between the two records must still alarm: {sent}")
    assert not any(c.args[0] == "naked_alarm_suppressed_silent" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_naked_alarm_still_fires_when_prices_disagree_between_rows(monkeypatch):
    """Same stop id in both rows, but the prices disagree -- must still
    alarm; a price mismatch inside otherwise-matching records is not
    conclusive."""
    sent, audit = await _fire_naked_branch(
        monkeypatch,
        dup_rows=[_pending_row(), _armed_row(stop_price=NEW_STOP_PRICE - 5.00)])

    assert any("unprotected" in m.lower() for m in sent), (
        f"a price mismatch between the two records must still alarm: {sent}")
    assert not any(c.args[0] == "naked_alarm_suppressed_silent" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_naked_alarm_still_fires_when_evidence_is_for_a_different_trade(monkeypatch):
    """Both rows exist and agree with each other, but for a DIFFERENT
    trade_id -- not proof about THIS position. Must still alarm."""
    sent, audit = await _fire_naked_branch(
        monkeypatch,
        dup_rows=[_pending_row(trade_id=999), _armed_row(trade_id=999)])

    assert any("unprotected" in m.lower() for m in sent), (
        f"evidence for a different trade must not suppress: {sent}")
    assert not any(c.args[0] == "naked_alarm_suppressed_silent" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_naked_alarm_still_fires_when_evidence_lookup_errors(monkeypatch):
    """The mi_audit_log lookup itself raises (transient DB blip) -- fail-safe
    means still alarm, exactly like the sibling #433/#561 checks."""
    sent, audit = await _fire_naked_branch(
        monkeypatch, dup_rows=RuntimeError("db connection reset"))

    assert any("unprotected" in m.lower() for m in sent), (
        f"a failed evidence re-check must still alarm: {sent}")
    assert not any(c.args[0] == "naked_alarm_suppressed_silent" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_naked_alarm_still_fires_on_malformed_evidence_row(monkeypatch):
    """Only malformed rows sit in the window (bad JSON, unrelated trade) --
    must not crash and must still alarm, never silently swallowed."""
    sent, audit = await _fire_naked_branch(
        monkeypatch,
        dup_rows=[
            {"event_type": "partial_exit_stop_telegram_pending", "detail": "not json at all"},
            {"event_type": "partial_exit_breakeven_armed",
             "detail": json.dumps({"trade_id": 999, "new_stop_id": "unrelated", "stop_price": 1.0})},
        ])

    assert any("unprotected" in m.lower() for m in sent), (
        f"malformed/unrelated evidence rows must not crash and must still alarm: {sent}")
    assert not any(c.args[0] == "naked_alarm_suppressed_silent" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_naked_alarm_suppressed_despite_unrelated_malformed_rows_alongside(monkeypatch):
    """A real, agreeing pair sits ALONGSIDE malformed/unrelated rows in the
    same window -- one bad row must not block finding the real match next to
    it (mirrors the sibling branch's own robustness test)."""
    sent, audit = await _fire_naked_branch(
        monkeypatch,
        dup_rows=[
            {"event_type": "partial_exit_stop_telegram_pending", "detail": ""},
            {"event_type": "partial_exit_breakeven_armed",
             "detail": json.dumps({"trade_id": 999, "new_stop_id": "unrelated", "stop_price": 1.0})},
            _pending_row(),
            _armed_row(),
        ])

    assert sent == [], f"a real match beside unrelated/malformed rows must still suppress: {sent}"
    assert any(c.args[0] == "naked_alarm_suppressed_silent" for c in audit.await_args_list)
