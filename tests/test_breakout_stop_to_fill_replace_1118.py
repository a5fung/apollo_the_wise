"""2026-11-18 (paper, breakout v1, CAKE trade 788 — prod evidence scripts/probes/_pt_fail_1118/t.out).

1. After the resting third filled, the stop on the rest was moved to the fill through `update_stop`: CANCEL the
   old stop, then PLACE a new one. The broker still held the cancelled stop's 103 shares (40310000 "insufficient
   qty", held_for_orders 103); the 3-second retry was refused too -> `stop_update_failed`, ~20 s with no stop, and
   the stop then sat at the old level until 16:45. `_breakout_pp_stop_to_fill_after_third` now moves the LIVE stop
   with one atomic PRICE-ONLY `alpaca.replace_order` (the #548 `partial_exit_breakeven_armed` / #545
   `breakeven_armed` mechanism): same price (the fill), same share count, raise-only. `update_stop` is the fallback
   when the replace cannot be attempted or the broker refuses it — and is NEVER called after an accepted replace.

2. `scan_profit_triggers`: the +2R third was already RESTING at the broker, the next 5-minute poll re-selected the
   trade, `execute_partial_exit` stopped at its dedup guard, and the poll wrote `profit_trigger_failed` — which the
   nightly `*_failed` sweep paged on. That outcome is now `profit_trigger_resting`.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.market_intelligence.broker.order_manager as om
from tests import test_resting_mode_breakeven_548 as r548
from tests.conftest import make_mock_pool

TRADE_ID = 788
TICKER = "CAKE"
OLD_STOP = 109.63
FILL = 111.86
REST = 103
OLD_STOP_ID = "5424cc74-ae18-484b-a9e8-2c2e5f794227"
NEW_STOP_ID = "0f0f0f0f-aaaa-bbbb-cccc-121212121212"
THIRD_ORDER = "5376a9f7-0402-4680-b7e4-95a8c649d6cb"
HELD = ('{"available":"0","code":40310000,"existing_qty":"103","held_for_orders":"103",'
        '"message":"insufficient qty available for order (requested: 103, available: 0)"}')


def _row(**over):
    """The trade row as the finalizer leaves it: the third booked, 103 sh left, the stop still at the old level."""
    r = {"id": TRADE_ID, "ticker": TICKER, "account_mode": "paper", "remaining_shares": REST, "status": "filled",
         "exits": [], "entry_price": FILL, "stop_price": OLD_STOP, "stop_order_id": OLD_STOP_ID, "entry_attempt": 1,
         "exit_rule": "breakout_pp", "signal_type": "breakout_v1"}
    r.update(over)
    return r


class _H:
    pass


def _wire(monkeypatch, row, *, live_stop, replace=None, successor_status="new", pending_qty=0):
    """Drive `_breakout_pp_stop_to_fill_after_third` directly (what `finalize_partial_exit` calls after its lock)."""
    h = _H()
    pool, conn = make_mock_pool()
    order_row = {"qty": 51.0, "status": "filled"}

    async def _fetchrow(sql, *a):
        return row if "FROM mi_live_trades" in sql else order_row
    conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    conn.fetchval = AsyncMock(return_value=pending_qty)          # get_pending_exit_qty
    conn.execute = AsyncMock(return_value="UPDATE 1")
    h.conn, h.audited = conn, []

    async def _audit(evt, summary="", detail=""):
        h.audited.append((evt, summary, detail))

    async def _get_order(oid, account_mode=None, **kw):
        assert account_mode == "paper"
        if oid == OLD_STOP_ID:
            return live_stop
        if oid == NEW_STOP_ID:
            return {"id": NEW_STOP_ID, "status": successor_status, "stop_price": FILL, "qty": float(REST)}
        return None

    h.get_order = AsyncMock(side_effect=_get_order)
    h.replace = replace or AsyncMock(return_value={"id": NEW_STOP_ID, "status": "new", "qty": float(REST),
                                                   "stop_price": FILL})
    h.cancel = AsyncMock(return_value=True)
    h.place = AsyncMock(return_value={"id": "placed", "status": "new"})
    h.update_stop = AsyncMock(return_value=True)
    h.set_ptr = AsyncMock(return_value=True)
    h.ensure = AsyncMock(return_value="re-protected 103 sh")
    h.sent = AsyncMock(return_value=True)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", _audit)
    monkeypatch.setattr(om, "send_telegram_message", h.sent)
    monkeypatch.setattr(om, "update_stop", h.update_stop)
    monkeypatch.setattr(om, "set_stop_order_id", h.set_ptr)
    monkeypatch.setattr(om, "_ensure_stop_coverage", h.ensure)
    monkeypatch.setattr(om, "_BREAKEVEN_ARM_VERIFY_INTERVAL_S", 0)
    monkeypatch.setattr(om.alpaca, "get_order", h.get_order)
    monkeypatch.setattr(om.alpaca, "replace_order", h.replace)
    monkeypatch.setattr(om.alpaca, "cancel_order", h.cancel)
    monkeypatch.setattr(om.alpaca, "place_stop_order", h.place)
    monkeypatch.setattr(om.alpaca, "get_position", AsyncMock(return_value={"qty": float(REST)}))
    monkeypatch.setattr(om.alpaca, "make_client_order_id", lambda mode, sig, tkr: f"{mode}-{sig}-{tkr}-x")
    return h


LIVE = {"id": OLD_STOP_ID, "status": "new", "stop_price": OLD_STOP, "qty": float(REST)}


def _after_third(h):
    rows = [json.loads(d) for e, _s, d in h.audited if e == "breakout_pp_stop_to_fill_after_third"]
    assert len(rows) == 1
    return rows[0]


def _trade_writes(h):
    return [c for c in h.conn.execute.await_args_list if "UPDATE mi_live_trades" in c.args[0]]


# ── A (1): the move is a price-only replace on the live stop — nothing is cancelled, nothing is placed ──────────
def test_the_stop_moves_to_the_fill_by_a_price_only_replace_and_never_cancels_or_places(monkeypatch):
    h = _wire(monkeypatch, _row(), live_stop=LIVE)
    asyncio.run(om._breakout_pp_stop_to_fill_after_third(TRADE_ID, THIRD_ORDER, 51))
    h.replace.assert_awaited_once()
    assert h.replace.await_args.args == (OLD_STOP_ID,)
    kw = h.replace.await_args.kwargs
    assert kw["stop_price"] == FILL and kw["account_mode"] == "paper" and kw["client_order_id"]
    assert "qty" not in kw and "limit_price" not in kw, "PRICE-ONLY: the share count is never sent"
    h.cancel.assert_not_awaited()
    h.place.assert_not_awaited()
    h.update_stop.assert_not_awaited()
    # pointer + price follow the broker, in ONE statement, only after the successor read back live
    writes = _trade_writes(h)
    assert len(writes) == 1
    sql, tid, new_id, new_price = writes[0].args
    assert "stop_order_id = $2" in sql and "stop_price = $3" in sql
    assert (tid, new_id, new_price) == (TRADE_ID, NEW_STOP_ID, FILL)
    ins = [c for c in h.conn.execute.await_args_list if "INSERT INTO mi_live_orders" in c.args[0]]
    assert len(ins) == 1
    assert ins[0].args[1:6] == (TRADE_ID, NEW_STOP_ID, TICKER, float(REST), FILL)     # same share count as the live stop
    assert "'stop_loss'" in ins[0].args[0]
    d = _after_third(h)
    assert d["moved"] is True and d["mechanism"] == "price_only_replace"
    assert (d["old_stop"], d["new_stop"], d["old_stop_id"], d["new_stop_id"]) == (OLD_STOP, FILL, OLD_STOP_ID, NEW_STOP_ID)
    h.sent.assert_not_awaited()          # a confirmed move is silent, as a first-attempt update_stop success always was


# ── A (2): replace impossible / refused -> today's update_stop call, unchanged ────────────────────────────────────
@pytest.mark.parametrize("case", ["refused", "no_pointer", "qty_mismatch", "not_live", "unreadable", "pending_exit"])
def test_a_replace_that_cannot_be_made_or_is_refused_falls_back_to_update_stop(monkeypatch, case):
    row, live, replace, pending = _row(), dict(LIVE), None, 0
    if case == "refused":
        replace = AsyncMock(side_effect=RuntimeError(HELD))
    elif case == "no_pointer":
        row = _row(stop_order_id=None)
    elif case == "qty_mismatch":
        live["qty"] = 154.0
    elif case == "not_live":
        live["status"] = "pending_replace"
    elif case == "unreadable":
        live = None
    elif case == "pending_exit":
        pending = 20          # another exit order holds shares: the live stop is not the whole rest
    h = _wire(monkeypatch, row, live_stop=live, replace=replace, pending_qty=pending)
    asyncio.run(om._breakout_pp_stop_to_fill_after_third(TRADE_ID, THIRD_ORDER, 51))
    h.update_stop.assert_awaited_once_with(TRADE_ID, FILL, stop_source="breakeven")
    assert h.replace.await_count == (1 if case == "refused" else 0)
    assert not _trade_writes(h), "the fallback's writes are update_stop's own"
    h.set_ptr.assert_not_awaited()
    d = _after_third(h)
    assert d["moved"] is True and d["mechanism"] == "update_stop" and d["replace_skipped"]
    h.sent.assert_not_awaited()


def test_a_fallback_that_also_fails_is_recorded_not_moved_and_paged(monkeypatch):
    h = _wire(monkeypatch, _row(), live_stop=LIVE, replace=AsyncMock(side_effect=RuntimeError(HELD)))
    h.update_stop.return_value = False
    asyncio.run(om._breakout_pp_stop_to_fill_after_third(TRADE_ID, THIRD_ORDER, 51))
    d = _after_third(h)
    assert d["moved"] is False and d["mechanism"] == "update_stop"
    h.sent.assert_awaited_once()
    assert "could not be moved" in h.sent.await_args.args[0] and "$109.63" in h.sent.await_args.args[0]


def test_a_broker_stop_already_at_the_fill_is_never_replaced(monkeypatch):
    """Raise-only against the BROKER (the DB may understate): no replace; update_stop's own floor records it."""
    h = _wire(monkeypatch, _row(), live_stop={**LIVE, "stop_price": FILL})
    asyncio.run(om._breakout_pp_stop_to_fill_after_third(TRADE_ID, THIRD_ORDER, 51))
    h.replace.assert_not_awaited()
    h.update_stop.assert_awaited_once()


# ── A (3): an ACCEPTED replace that is not confirmed live never reaches update_stop ───────────────────────────────
def test_an_accepted_replace_not_confirmed_live_keeps_the_pointer_withholds_the_price_and_says_so(monkeypatch):
    h = _wire(monkeypatch, _row(), live_stop=LIVE, successor_status="pending_replace")
    asyncio.run(om._breakout_pp_stop_to_fill_after_third(TRADE_ID, THIRD_ORDER, 51))
    h.update_stop.assert_not_awaited()
    h.cancel.assert_not_awaited()
    h.place.assert_not_awaited()
    assert not _trade_writes(h), "the price is written only on a confirmed move"
    h.set_ptr.assert_awaited_once()
    assert h.set_ptr.await_args.args == (TRADE_ID, NEW_STOP_ID) and h.set_ptr.await_args.kwargs["account_mode"] == "paper"
    d = _after_third(h)
    assert d["moved"] is False and d["replace_outcome"] == "unverified"
    assert "not confirmed live" in h.sent.await_args.args[0]


def test_a_successor_that_reads_back_dead_nulls_the_pointer_and_re_protects_from_broker_truth(monkeypatch):
    h = _wire(monkeypatch, _row(), live_stop=LIVE, successor_status="rejected")
    asyncio.run(om._breakout_pp_stop_to_fill_after_third(TRADE_ID, THIRD_ORDER, 51))
    h.update_stop.assert_not_awaited()
    h.place.assert_not_awaited()
    assert h.set_ptr.await_args.args == (TRADE_ID, None)
    h.ensure.assert_awaited_once_with(TRADE_ID, TICKER, float(REST), OLD_STOP, "breakout_v1", "paper")
    assert not _trade_writes(h)
    assert _after_third(h)["moved"] is False
    assert "FAILED" in h.sent.await_args.args[0] and "re-protected 103 sh" in h.sent.await_args.args[0]


def test_the_finalizer_still_reaches_the_move_and_a_raise_never_escapes(monkeypatch):
    h = _wire(monkeypatch, _row(remaining_shares=154), live_stop=LIVE)     # pre-commit row: 154 -> 103 after the third
    monkeypatch.setattr(om, "_trade_advisory_lock", lambda tid: r548._noop_lock()(tid))
    h.get_order.side_effect = RuntimeError("broker down")
    h.update_stop.side_effect = RuntimeError("broker down")
    asyncio.run(om.finalize_partial_exit(TRADE_ID, 51, 116.39, THIRD_ORDER))
    assert any(e == "breakout_pp_stop_to_fill_failed" for e, *_ in h.audited)


# ── B: a resting partial re-selected by the poll is not a failure ─────────────────────────────────────────────────
class _NoonET(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 11, 18, 12, 0, tzinfo=tz)


def _scan_row():
    return {
        "id": TRADE_ID, "ticker": TICKER, "entry_price": 111.86,
        "hard_stop": 109.63, "stop_price": 109.63, "orb_low": 109.63,
        "signal_type": "magna53",          # the generic frame; the label logic is setup-agnostic
        "remaining_shares": 154.0, "partial_taken": False,
        "filled_at": datetime(2026, 11, 17, 14, 46, tzinfo=timezone.utc),
        "account_mode": "paper",
    }


class _ScanPool:
    def __init__(self, rows, hi):
        self._rows, self._hi = rows, hi

    def acquire(self):
        pool = self

        class _Conn:
            async def fetch(self, sql, *a):
                return pool._rows

            async def fetchval(self, sql, *a):
                return pool._hi

        class _Ctx:
            async def __aenter__(self):
                return _Conn()

            async def __aexit__(self, *a):
                return False

        return _Ctx()


async def _run_scan(monkeypatch, *, exec_ok, pending, announced=True):
    import agents.market_intelligence.constants as constants
    monkeypatch.setattr(constants, "PROFIT_TRIGGER_R", 2.0)
    audit, sent = AsyncMock(), AsyncMock(return_value=True)
    fake_exec = AsyncMock(return_value=exec_ok)
    with patch.object(om, "get_pool", AsyncMock(return_value=_ScanPool([_scan_row()], 116.54))), \
         patch.object(om, "datetime", _NoonET), \
         patch.object(om, "execute_partial_exit", fake_exec), \
         patch.object(om, "_pending_exit_order_for", AsyncMock(return_value=pending), create=True), \
         patch.object(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=True)), \
         patch.object(om, "_profit_trigger_already_announced", AsyncMock(return_value=announced)), \
         patch.object(om, "send_telegram_message", sent), \
         patch.object(om, "log_audit_event", audit):
        results = await om.scan_profit_triggers()
    return results, audit, fake_exec, sent


PENDING = {"alpaca_order_id": THIRD_ORDER, "purpose": "partial_exit"}


@pytest.mark.asyncio
async def test_a_resting_partial_reselected_by_the_poll_is_not_recorded_as_failed(monkeypatch):
    """CAKE 09:45:01: the third already rests at the broker, `execute_partial_exit` returns False at its dedup
    guard. MUTATION: drop the pending read -> `profit_trigger_failed`."""
    results, audit, fake_exec, sent = await _run_scan(monkeypatch, exec_ok=False, pending=PENDING)
    names = [c.args[0] for c in audit.call_args_list]
    assert names == ["profit_trigger_resting"]
    fake_exec.assert_awaited_once()                       # the money call is unchanged — its guard stays the authority
    assert fake_exec.call_args.args[0] == TRADE_ID
    detail = json.loads(audit.call_args.args[2])
    assert detail["trade_id"] == TRADE_ID                 # the announce dedupe keys on this
    assert detail["pending_order_id"] == PENDING["alpaca_order_id"]
    assert detail["pending_purpose"] == "partial_exit"
    assert results == [{"ticker": TICKER, "action": "partial_resting", "shares": 51}]
    sent.assert_not_awaited()                             # already announced -> stays quiet


@pytest.mark.asyncio
async def test_a_real_failure_with_no_working_exit_order_is_still_profit_trigger_failed(monkeypatch):
    results, audit, _e, _s = await _run_scan(monkeypatch, exec_ok=False, pending=None)
    assert [c.args[0] for c in audit.call_args_list] == ["profit_trigger_failed"]
    assert results[0]["action"] == "partial_failed"


@pytest.mark.asyncio
async def test_a_partial_that_was_placed_is_still_profit_trigger_fired(monkeypatch):
    """`ok` wins: a pending row read a moment earlier never relabels a placement that went out."""
    results, audit, _e, _s = await _run_scan(monkeypatch, exec_ok=True, pending=PENDING)
    assert [c.args[0] for c in audit.call_args_list] == ["profit_trigger_fired"]
    assert results[0]["action"] == "partial_submitted"


@pytest.mark.asyncio
async def test_the_resting_event_is_invisible_to_the_nightly_failed_sweep_and_counted_by_the_dedupe():
    """The name must match neither nightly pattern (`_failed`, `error`), and the announce dedupe must count it —
    otherwise the 'Profit target hit' message would repeat every 5 minutes. Behavioural: the query the dedupe
    actually SENDS is captured and read."""
    assert om.PROFIT_TRIGGER_RESTING == "profit_trigger_resting"
    assert "_failed" not in om.PROFIT_TRIGGER_RESTING and "error" not in om.PROFIT_TRIGGER_RESTING
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=1)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om._profit_trigger_already_announced(TRADE_ID) is True
    sql, tid = conn.fetchval.call_args.args
    assert tid == str(TRADE_ID)
    for name in ("profit_trigger_fired", "profit_trigger_failed", om.PROFIT_TRIGGER_RESTING):
        assert f"'{name}'" in sql, f"the dedupe must count {name}"


@pytest.mark.asyncio
async def test_the_pending_exit_read_uses_the_shared_terminal_set_and_fails_to_none():
    """Same read as `execute_partial_exit`'s dedup guard; a failed read returns None, which keeps the old
    `profit_trigger_failed` label (the louder direction)."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"alpaca_order_id": "o1", "purpose": "full_exit", "qty": 5})
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om._pending_exit_order_for(7) == {"alpaca_order_id": "o1", "purpose": "full_exit"}
        sql, tid, terminal = conn.fetchrow.call_args.args
        assert tid == 7 and terminal == list(om.PENDING_EXIT_TERMINAL_STATUSES)
        assert "purpose IN ('partial_exit', 'full_exit')" in sql
        conn.fetchrow = AsyncMock(return_value=None)
        assert await om._pending_exit_order_for(7) is None
    with patch.object(om, "get_pool", AsyncMock(side_effect=RuntimeError("db down"))):
        assert await om._pending_exit_order_for(7) is None


# ── review follow-ups (2026-11-18): a raised replace is not proof of a refusal ──────────────────

@pytest.mark.asyncio
async def test_raised_replace_with_old_stop_consumed_never_falls_back_to_cancel_place(monkeypatch):
    from agents.market_intelligence.broker import order_manager as om
    trade = {"id": 1, "ticker": "CAKE", "account_mode": "paper", "signal_type": "breakout_v1",
             "stop_order_id": "old", "remaining_shares": 103, "stop_price": 109.63}
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    reads = iter([{"status": "new", "stop_price": 109.63, "qty": 103},   # pre-replace: live
                  {"status": "replaced", "stop_price": 109.63}])          # read-back: consumed
    monkeypatch.setattr(om.alpaca, "get_order", AsyncMock(side_effect=lambda *a, **k: next(reads)))
    monkeypatch.setattr(om.alpaca, "replace_order", AsyncMock(side_effect=TimeoutError("write timeout")))
    out = await om._breakout_pp_replace_stop_price(trade, 111.86)
    assert out["outcome"] == "unverified" and out["replace_outcome"] == "raised_ambiguous"


@pytest.mark.asyncio
async def test_raised_replace_with_old_stop_still_live_is_a_real_refusal(monkeypatch):
    from agents.market_intelligence.broker import order_manager as om
    trade = {"id": 1, "ticker": "CAKE", "account_mode": "paper", "signal_type": "breakout_v1",
             "stop_order_id": "old", "remaining_shares": 103, "stop_price": 109.63}
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    monkeypatch.setattr(om.alpaca, "get_order",
                        AsyncMock(return_value={"status": "new", "stop_price": 109.63, "qty": 103}))
    monkeypatch.setattr(om.alpaca, "replace_order", AsyncMock(side_effect=RuntimeError("422")))
    out = await om._breakout_pp_replace_stop_price(trade, 111.86)
    assert out["outcome"] == "fallback"


@pytest.mark.asyncio
async def test_verify_read_raising_after_an_accepted_replace_points_at_the_successor(monkeypatch):
    from agents.market_intelligence.broker import order_manager as om
    trade = {"id": 1, "ticker": "CAKE", "account_mode": "paper", "signal_type": "breakout_v1",
             "stop_order_id": "old", "remaining_shares": 103, "stop_price": 109.63}
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    calls = {"n": 0}
    async def _get(oid, **k):
        calls["n"] += 1
        if oid == "old":
            return {"status": "new", "stop_price": 109.63, "qty": 103}
        raise ConnectionError("broker down")
    monkeypatch.setattr(om.alpaca, "get_order", _get)
    monkeypatch.setattr(om.alpaca, "replace_order", AsyncMock(return_value={"id": "new", "status": "new"}))
    setp = AsyncMock()
    monkeypatch.setattr(om, "set_stop_order_id", setp)
    out = await om._breakout_pp_replace_stop_price(trade, 111.86)
    assert out["outcome"] == "unverified"
    assert setp.await_args.args[:2] == (1, "new")
