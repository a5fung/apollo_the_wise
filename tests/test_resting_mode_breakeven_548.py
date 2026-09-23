"""#548 resting-mode breakeven — the coverage gap flagged in commit e6cafb5's own message:
all six tests in test_breakeven_at_broker_548.py exercise the `not resting_mode` fold-in,
which goes DORMANT the instant the `profit_take_resting_limit` toggle flips ON. This file
covers the OTHER branch — search "if (resting_mode and not abort_reprotect and new_stop_id
and stop_price" in order_manager.py — the atomic price-only replace of the reduced stop to
breakeven, run AFTER the +2R third rests as a GTC limit.

Four outcomes, each pinned BEHAVIOURALLY (call the real `execute_partial_exit` against a
faked alpaca client + faked db pool, not source-grepped):
  1. replace accepted + successor confirmed live  -> pointer + price + order row + audit.
  2. replace rejected + reduced stop still confirmed live -> deferred, protection UNCHANGED,
     pointer NOT nulled.
  3. replace rejected + reduced stop read back CONFIRMED dead -> pointer nulled, re-protect
     armed. Split 2026-08-10 (ADR 0008 fence, deploy [5l/7]): only an ACTUAL terminal status
     returned by the broker may null; an UNVERIFIABLE read (None / raised / still pending_*
     after the retry budget) must NOT null — see the Case A / Case B tests at the bottom.
  4. replace accepted but the successor never confirms inside the poll budget ("uncertain")
     -> pointer IS persisted, price is DELIBERATELY withheld. This is INTENTIONAL (the
     order_manager.py block comment says so explicitly: "do NOT record the breakeven price
     as fact") — the DB understating protection is the safe direction. Do not "fix" this.

Plus the two invariants that make the whole feature safe: breakeven can only ever RAISE the
stop, and the runtime toggles default OFF and fail CLOSED (an unreadable flag must not turn
resting mode, or breakeven, on).
"""
import asyncio
from contextlib import ExitStack, asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


TRADE_ID = 610
TICKER = "FIGS"
SHARES = 20
FULL_REMAINING = 60
NEW_REMAINING = FULL_REMAINING - SHARES
STOP_PRICE = 15.00
ENTRY_PRICE = 15.30          # above the resting stop -> breakeven RAISES it
BREAKEVEN_PRICE = max(STOP_PRICE, ENTRY_PRICE)
LIMIT_PRICE = 15.90          # the resting +2R target
ACCOUNT_MODE = "paper"


def _noop_lock():
    @asynccontextmanager
    async def _cm(trade_id):
        yield
    return _cm


def _trade(**overrides):
    t = {
        "id": TRADE_ID, "ticker": TICKER, "remaining_shares": FULL_REMAINING,
        "stop_price": STOP_PRICE, "hard_stop": STOP_PRICE, "stop_order_id": "old_stop_id",
        "account_mode": ACCOUNT_MODE, "signal_type": "magna53", "entry_price": ENTRY_PRICE,
    }
    t.update(overrides)
    return t


def _make_pool(trade):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[trade, None])  # trade lookup, then dedup-pending
    conn.execute = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool, conn


def _replace_order_fake(calls, *, be_result: str):
    """Fakes `alpaca.replace_order` for BOTH call sites this function makes:

    * Step 1 (qty given): the pre-existing stop-quantity reduction. Always accepted —
      not what this file tests.
    * Step 2b (qty is None, stop_price only): the #548 resting-mode breakeven price-only
      replace. `be_result` is either the new order id to accept with, or the literal
      string "reject" to raise.
    """
    async def _replace(order_id, *, qty=None, stop_price=None, limit_price=None,
                        account_mode=None, client_order_id=None):
        calls.append(("replace", order_id, qty, stop_price))
        if qty is not None:
            return {"id": "new_stop_id", "status": "accepted"}
        if be_result == "reject":
            raise RuntimeError("breakeven replace rejected (test)")
        return {"id": be_result, "status": "accepted"}
    return _replace


async def _get_order_all_live(order_id, account_mode=None):
    """Every order (reduced stop, breakeven successor) reads back as live/resting."""
    return {"id": order_id, "status": "accepted", "order_class": "simple"}


async def _get_order_uncertain(order_id, account_mode=None):
    """The reduced stop is live; the breakeven successor never settles to a terminal
    or confirmed-live status inside the poll budget."""
    if order_id == "new_stop_id":
        return {"id": order_id, "status": "accepted", "order_class": "simple"}
    return {"id": order_id, "status": "pending_replace", "order_class": "simple"}


def _make_get_order_reduced_dies():
    """The reduced stop reads LIVE the first time (Step 1b, pre-sell verify), then DEAD
    every time after (the post-breakeven-rejection verify check)."""
    state = {"n": 0}

    async def _get_order(order_id, account_mode=None):
        if order_id == "new_stop_id":
            state["n"] += 1
            if state["n"] == 1:
                return {"id": order_id, "status": "accepted", "order_class": "simple"}
            return {"id": order_id, "status": "canceled", "order_class": "simple"}
        return {"id": order_id, "status": "accepted", "order_class": "simple"}
    return _get_order


def _harness(om, *, be_result: str, get_order_fake, trade_overrides: dict | None = None):
    trade = _trade(**(trade_overrides or {}))
    pool, conn = _make_pool(trade)
    calls: list = []
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    set_stop_mock = AsyncMock()
    telegram_mock = AsyncMock(return_value=True)
    ensure_cov_mock = AsyncMock(return_value="repaired")
    get_position_mock = AsyncMock(
        return_value={"qty": float(NEW_REMAINING), "qty_available": float(NEW_REMAINING)})

    patches = [
        patch.object(om, "_PARTIAL_EXIT_PAUSED", False),
        patch.object(om, "_consecutive_partial_exit_failures", AsyncMock(return_value=0)),
        patch.object(om, "_trade_advisory_lock", _noop_lock()),
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "send_telegram_message", telegram_mock),
        patch.object(om, "set_stop_order_id", set_stop_mock),
        patch.object(om, "_ensure_stop_coverage", ensure_cov_mock),
        patch.object(om, "get_runtime_toggle", AsyncMock(return_value=False)),
        patch.object(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=True)),
        patch.object(om, "_breakeven_at_broker_enabled", AsyncMock(return_value=True)),
        patch.object(om.asyncio, "sleep", AsyncMock()),  # fast polls — no real 0.25s waits
        patch.object(om.alpaca, "replace_order", _replace_order_fake(calls, be_result=be_result)),
        patch.object(om.alpaca, "get_order", get_order_fake),
        patch.object(om.alpaca, "get_position", get_position_mock),
        patch.object(om.alpaca, "place_limit_sell", AsyncMock(
            return_value={"id": "sell_id", "status": "new"})),
        patch.object(om.alpaca, "place_market_sell", AsyncMock(
            return_value={"id": "market_sell_id", "status": "new"})),
        patch.object(om.alpaca, "make_client_order_id",
                     lambda m, s, t: f"apollo_{m}_{s}_{t}_x"),
    ]
    return {
        "patches": patches, "calls": calls, "audited": audited,
        "set_stop": set_stop_mock, "telegram": telegram_mock,
        "ensure_cov": ensure_cov_mock, "conn": conn, "trade": trade,
    }


async def _run(om, h):
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        return await om.execute_partial_exit(
            TRADE_ID, SHARES, force=True, limit_price=LIMIT_PRICE)


# ── Outcome 1: replace accepted, successor confirmed live ─────────────────────────────

@pytest.mark.asyncio
async def test_outcome1_replace_accepted_and_confirmed_live_arms_breakeven():
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, be_result="be_stop_id", get_order_fake=_get_order_all_live)
    ok = await _run(om, h)

    assert ok is True
    h["set_stop"].assert_any_call(
        TRADE_ID, "be_stop_id", reason="breakeven_replacement", account_mode=ACCOUNT_MODE)

    update_calls = [c for c in h["conn"].execute.call_args_list
                     if "SET stop_price" in c.args[0]]
    assert any(c.args[1:] == (TRADE_ID, BREAKEVEN_PRICE) for c in update_calls), (
        f"mi_live_trades.stop_price must be updated to the breakeven price; got {update_calls}")

    be_inserts = [c for c in h["conn"].execute.call_args_list
                  if c.args[0].strip().startswith("INSERT INTO mi_live_orders")
                  and len(c.args) >= 3 and c.args[2] == "be_stop_id"]
    assert be_inserts, "no mi_live_orders row inserted for the breakeven successor"
    assert BREAKEVEN_PRICE in be_inserts[0].args, "breakeven price missing from the inserted row"

    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_breakeven_armed" in events


# ── Outcome 2: replace rejected, reduced stop still confirmed live ────────────────────

@pytest.mark.asyncio
async def test_outcome2_replace_rejected_but_reduced_stop_still_live_defers():
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, be_result="reject", get_order_fake=_get_order_all_live)
    ok = await _run(om, h)

    assert ok is True
    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_breakeven_deferred" in events
    assert "partial_exit_breakeven_armed" not in events

    update_calls = [c for c in h["conn"].execute.call_args_list
                     if "SET stop_price" in c.args[0]]
    assert not update_calls, "protection must stay UNCHANGED when the breakeven replace is rejected"

    null_calls = [c for c in h["set_stop"].call_args_list if c.args[1] is None]
    assert not null_calls, "the pointer must NOT be nulled — the reduced stop is still live"

    sent = " ".join(str(c.args[0]) for c in h["telegram"].call_args_list)
    assert "breakeven" in sent.lower() and "rejected" in sent.lower()


# ── Outcome 3: replace rejected, reduced stop read back confirmed DEAD ────────────────

@pytest.mark.asyncio
async def test_outcome3_replace_rejected_and_reduced_stop_dead_nulls_pointer():
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, be_result="reject", get_order_fake=_make_get_order_reduced_dies())
    ok = await _run(om, h)

    # The partial itself (the resting limit) still stands — only breakeven degraded.
    assert ok is True
    h["set_stop"].assert_any_call(
        TRADE_ID, None, reason="breakeven_replace_failed", account_mode=ACCOUNT_MODE)
    h["ensure_cov"].assert_called_once()

    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_breakeven_armed" not in events
    assert "partial_exit_breakeven_deferred" not in events


# ── Outcome 4: replace accepted, successor never confirms in-budget ("uncertain") ─────

@pytest.mark.asyncio
async def test_outcome4_uncertain_successor_pointer_persisted_but_price_withheld():
    """INTENTIONAL (#548 design), not a bug: the replace was ACCEPTED and the successor
    id is the best broker truth available, so the pointer is written — but its live-ness
    was never confirmed inside the poll budget, so the price is deliberately withheld.
    Writing stop_price here would turn a safe UNDER-statement of protection into a
    possible OVER-statement (the DB claiming breakeven while the broker might not have
    it) — order_manager.py's own comment on this branch says so explicitly ("do NOT
    record the breakeven price as fact"). A future reader must not "fix" this by writing
    the price anyway.
    """
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, be_result="be_stop_id_unconfirmed", get_order_fake=_get_order_uncertain)
    ok = await _run(om, h)

    assert ok is True
    h["set_stop"].assert_any_call(
        TRADE_ID, "be_stop_id_unconfirmed", reason="breakeven_replacement",
        account_mode=ACCOUNT_MODE)

    update_calls = [c for c in h["conn"].execute.call_args_list
                     if "SET stop_price" in c.args[0]]
    assert not update_calls, (
        "stop_price must NOT be written when the successor never confirmed live — this "
        "is deliberate (DB understates protection, never overstates it); do not fix it")

    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_breakeven_unverified" in events
    assert "partial_exit_breakeven_armed" not in events

    sent = " ".join(str(c.args[0]) for c in h["telegram"].call_args_list)
    assert "not confirmed live" in sent.lower()


# ── Guard: breakeven must never run when the sell itself failed (abort_reprotect) ─────

@pytest.mark.asyncio
async def test_breakeven_never_runs_when_the_resting_sell_itself_failed():
    """The block's own entry condition (order_manager.py) is `resting_mode and not
    abort_reprotect and new_stop_id and stop_price and ...`. If the limit sell raised
    after the stop was already reduced, abort_reprotect is set and the standard
    re-protect path owns remediation — breakeven must not touch the stop at all."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, be_result="reject", get_order_fake=_get_order_all_live)
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        with patch.object(om.alpaca, "place_limit_sell",
                           AsyncMock(side_effect=RuntimeError("sell rejected"))):
            ok = await om.execute_partial_exit(
                TRADE_ID, SHARES, force=True, limit_price=LIMIT_PRICE)

    assert ok is False
    replace_calls = [c for c in h["calls"] if c[0] == "replace"]
    assert len(replace_calls) == 1, (
        f"breakeven must never attempt a replace when the sell itself failed "
        f"(abort_reprotect); calls={replace_calls}")
    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_breakeven_armed" not in events
    assert "partial_exit_breakeven_deferred" not in events
    assert "partial_exit_breakeven_unverified" not in events
    h["ensure_cov"].assert_called_once()


# ── Invariant: breakeven can only ever RAISE the stop ──────────────────────────────────

@pytest.mark.asyncio
async def test_breakeven_never_lowers_the_stop_when_entry_is_below_it():
    """A trailed / gapped-up position can already sit ABOVE entry. Breakeven must be a
    no-op there — never move the stop DOWN toward entry. Uses entry BELOW the resting
    stop: if `max()` were dropped (or replaced with an unconditional `_entry`), this
    would replace the stop at a LOWER price — strictly worse than doing nothing."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, be_result="reject", get_order_fake=_get_order_all_live,
                 trade_overrides={"entry_price": 14.50})  # entry below the 15.00 stop
    ok = await _run(om, h)

    assert ok is True
    replace_calls = [c for c in h["calls"] if c[0] == "replace"]
    assert len(replace_calls) == 1, (
        f"breakeven must not attempt a replace at all when it would not raise the stop "
        f"(entry below stop); calls={replace_calls}")
    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_breakeven_armed" not in events
    assert "partial_exit_breakeven_deferred" not in events
    assert "partial_exit_breakeven_unverified" not in events


# ── Invariant: profit_take_resting_limit defaults OFF and fails CLOSED ─────────────────

@pytest.mark.asyncio
async def test_resting_limit_toggle_unreadable_falls_back_to_market_mode():
    """`_profit_take_resting_limit_enabled` is left UNMOCKED here — the real function
    runs, and its underlying db read is broken. It must fail CLOSED (False), which means
    execute_partial_exit falls back to the ordinary market-sell path — never resting-limit
    — even though the caller supplied a limit_price."""
    from agents.market_intelligence.broker import order_manager as om
    from agents.market_intelligence import db as mi_db

    trade = _trade()
    pool, conn = _make_pool(trade)
    calls: list = []
    market_sell_mock = AsyncMock(return_value={"id": "market_sell_id", "status": "new"})
    limit_sell_mock = AsyncMock(return_value={"id": "limit_sell_id", "status": "new"})

    patches = [
        patch.object(om, "_PARTIAL_EXIT_PAUSED", False),
        patch.object(om, "_consecutive_partial_exit_failures", AsyncMock(return_value=0)),
        patch.object(om, "_trade_advisory_lock", _noop_lock()),
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", AsyncMock()),
        patch.object(om, "send_telegram_message", AsyncMock(return_value=True)),
        patch.object(om, "set_stop_order_id", AsyncMock()),
        patch.object(om, "_ensure_stop_coverage", AsyncMock(return_value="repaired")),
        patch.object(om, "get_runtime_toggle", AsyncMock(return_value=False)),
        patch.object(om, "_breakeven_at_broker_enabled", AsyncMock(return_value=False)),
        patch.object(om.asyncio, "sleep", AsyncMock()),
        patch.object(mi_db, "get_safeguard_state", AsyncMock(side_effect=RuntimeError("db down"))),
        patch.object(om.alpaca, "replace_order", _replace_order_fake(calls, be_result="reject")),
        patch.object(om.alpaca, "get_order", _get_order_all_live),
        patch.object(om.alpaca, "get_position", AsyncMock(return_value={"qty": float(NEW_REMAINING)})),
        patch.object(om.alpaca, "place_limit_sell", limit_sell_mock),
        patch.object(om.alpaca, "place_market_sell", market_sell_mock),
        patch.object(om.alpaca, "make_client_order_id",
                     lambda m, s, t: f"apollo_{m}_{s}_{t}_x"),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        ok = await om.execute_partial_exit(TRADE_ID, SHARES, force=True, limit_price=LIMIT_PRICE)

    assert ok is True
    assert market_sell_mock.called, "an unreadable resting-limit toggle must fall back to a market sell"
    assert not limit_sell_mock.called, "resting mode must NOT activate when the toggle read raises"
    # Only the Step-1 stop-quantity replace should have run — no resting-mode breakeven replace.
    assert len(calls) == 1, f"resting-mode breakeven must never run when resting mode failed off; calls={calls}"


# ── Direct unit coverage of the toggle itself (default OFF, on-state, fail-closed) ────

@pytest.fixture()
def om():
    from agents.market_intelligence.broker import order_manager
    return order_manager


@pytest.mark.asyncio
async def test_profit_take_resting_limit_default_off_when_no_row(om, monkeypatch):
    """Ships dark. A deploy must change nothing until the operator flips it."""
    from agents.market_intelligence import db

    async def _none(*a, **k):
        return None
    monkeypatch.setattr(db, "get_safeguard_state", _none)
    assert await om._profit_take_resting_limit_enabled("paper") is False


@pytest.mark.asyncio
async def test_profit_take_resting_limit_on_only_for_the_literal_on_state(om, monkeypatch):
    from agents.market_intelligence import db

    for state, expected in (("on", True), ("ON", True), ("off", False),
                             ("observe", False), ("", False)):
        async def _row(*a, _s=state, **k):
            return {"state": _s}
        monkeypatch.setattr(db, "get_safeguard_state", _row)
        assert await om._profit_take_resting_limit_enabled("paper") is expected, state


@pytest.mark.asyncio
async def test_profit_take_resting_limit_fails_closed_when_read_raises(om, monkeypatch):
    """An unreadable flag must never silently enable a resting-limit money-path change."""
    from agents.market_intelligence import db

    async def _boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "get_safeguard_state", _boom)
    assert await om._profit_take_resting_limit_enabled("paper") is False


# ── ADR 0008 split (2026-08-10): a failed replace's verify read has THREE outcomes ─────
#
# The pre-split code folded "the broker READ a terminal status" (confirmed — may null)
# and "the read itself FAILED" (nothing confirmed — must NOT null) into one demotion.
# The second shape is the 2026-06-04 FPS false-naked incident verbatim and is what the
# deploy fence [5l/7] (scripts/audit_trade_state_demotions.py) blocked. Trap pinned
# here: alpaca_client.get_order swallows errors and returns None, so a None read is a
# FAILED read, not a status — it must never count as broker evidence of death.

def _make_get_order_flaky_then_dead():
    """Step 1b reads the reduced stop LIVE; after the failed breakeven replace the
    FIRST retry read fails (None — get_order's real error contract) and the SECOND
    returns a genuine terminal status. The bounded retry must convert the transient
    failure into a CONFIRMED dead read (Case B -> Case A) and only then demote."""
    state = {"n": 0}

    async def _get_order(order_id, account_mode=None):
        if order_id == "new_stop_id":
            state["n"] += 1
            if state["n"] == 1:
                return {"id": order_id, "status": "accepted", "order_class": "simple"}
            if state["n"] == 2:
                return None
            return {"id": order_id, "status": "rejected", "order_class": "simple"}
        return {"id": order_id, "status": "accepted", "order_class": "simple"}
    return _get_order


def _make_get_order_reduced_unverifiable(mode: str):
    """Step 1b reads the reduced stop LIVE; every read after the failed breakeven
    replace is unverifiable in one of the three real-world ways: 'none' (get_order
    swallowed the error and returned None), 'raise' (the read raised through), or
    'transitional' (reads fine but never leaves pending_replace in-budget)."""
    state = {"n": 0}

    async def _get_order(order_id, account_mode=None):
        if order_id == "new_stop_id":
            state["n"] += 1
            if state["n"] == 1:
                return {"id": order_id, "status": "accepted", "order_class": "simple"}
            if mode == "none":
                return None
            if mode == "raise":
                raise RuntimeError("broker read failed (test)")
            return {"id": order_id, "status": "pending_replace", "order_class": "simple"}
        return {"id": order_id, "status": "accepted", "order_class": "simple"}
    return _get_order


@pytest.mark.asyncio
async def test_case_a_bounded_retry_converts_transient_failure_into_confirmed_dead():
    """Case A: the demotion is allowed ONLY off a confirmed broker read. Here the
    first post-failure read fails (None) and the retry then reads a genuine terminal
    status — the bounded retry must rescue the confirmation, and the pointer is then
    nulled + re-protect armed. If the retry loop is shortened to a single read, the
    transient failure is never converted and this test reddens (mutation-proven)."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, be_result="reject", get_order_fake=_make_get_order_flaky_then_dead())
    ok = await _run(om, h)

    assert ok is True
    h["set_stop"].assert_any_call(
        TRADE_ID, None, reason="breakeven_replace_failed", account_mode=ACCOUNT_MODE)
    h["ensure_cov"].assert_called_once()
    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_breakeven_unverifiable" not in events, (
        "a read that settled to a CONFIRMED terminal status must take the "
        "broker-confirmed demotion path, not the unverifiable one")
    assert "partial_exit_breakeven_deferred" not in events
    assert "partial_exit_breakeven_armed" not in events


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["none", "raise", "transitional"])
async def test_case_b_unverifiable_read_never_nulls_the_pointer(failure_mode):
    """Case B: the replace raised AND the verify read failed every retry (None /
    raised / never left pending_*). NOTHING was broker-confirmed, so ADR 0008 rule 1
    forbids the demotion: the pointer (last confirmed broker truth, written by Step
    1's verified replace) is KEPT, re-protect still arms so _ensure_stop_coverage
    re-checks protection from BROKER truth in-process, an audit row records the
    unverifiable state, and the operator is alerted. Re-adding the old
    null-on-unconfirmed write in the unknown branch (the FPS 6/04 shape) must redden
    this test (mutation-proven)."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, be_result="reject",
                 get_order_fake=_make_get_order_reduced_unverifiable(failure_mode))
    ok = await _run(om, h)

    assert ok is True
    null_calls = [c for c in h["set_stop"].call_args_list if c.args[1] is None]
    assert not null_calls, (
        "an UNVERIFIABLE broker read must never null stop_order_id (ADR 0008 rule 1: "
        f"no demotion without a confirmed broker read/event); got {null_calls}")
    h["ensure_cov"].assert_called_once()  # protection re-check from broker truth still arms
    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_breakeven_unverifiable" in events
    assert "partial_exit_breakeven_armed" not in events
    assert "partial_exit_breakeven_deferred" not in events
    sent = " ".join(str(c.args[0]) for c in h["telegram"].call_args_list)
    assert "breakeven move failed" in sent.lower(), (
        "keeping the pointer is only safe because the failure is ALERTED — the "
        "post-lock Telegram must still fire")
