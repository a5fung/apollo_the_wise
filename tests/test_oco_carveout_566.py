"""#566 — the +2R carve-out OCO (operator-signed 2026-08-14, built 2026-08-15).

DEFECT 1 (protection): the resting-limit shape left the freed 1/3 with NO stop —
a limit above the market covers nothing on a decline (ETON 2026-08-14: 5 shares
uncovered for hours). The fix: in resting mode, behind the new default-OFF
`profit_take_oco` toggle, the 1/3 is sold with ONE OCO — GTC limit at the +2R
target + sibling GTC stop at BREAKEVEN — whichever side fills cancels the other.
Broker facts are BANKED (paper probe 2026-08-14 09:51 ET,
docs/analysis/548_oco_probe_run_2026-08-14.log): the OCO is accepted alongside
the separate plain 2/3 stop, every share is reserved (40310000 on any further
sell), and `order_class=oco` REQUIRES take_profit.limit_price.

This file pins:
  - the OCO placement (one OCO, limit at target, stop at breakeven, both legs
    recorded in mi_live_orders: parent purpose='partial_exit', leg
    purpose='stop_loss' so the WS router owns each side's fill);
  - toggle discipline (default OFF, fails CLOSED, requires resting mode);
  - the breakeven floor (the OCO stop is max(stop, entry) — never below the
    stop the shares already had);
  - the anchor fallback (no stop/entry to price the sibling → plain resting
    limit + loud audit, today's behaviour, never a broken OCO);
  - `place_oco_sell`'s request shape (probe shape B verbatim) + its
    naked-third guard (a parent with no stop leg is cancelled + raised);
  - the coverage DETECTOR regression (#566 build flag 2): `get_open_orders`
    HIDES the held OCO stop leg, so `check_position_coverage` counts the OCO
    PARENT's reservation as stop coverage — while a PLAIN sell limit still
    counts for NOTHING (that limit-is-not-protection reading IS defect 1).

Mutation checks are recorded per test in each docstring.
"""
import asyncio
from contextlib import ExitStack, asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


TRADE_ID = 731
TICKER = "ETON"
SHARES = 5
FULL_REMAINING = 17
NEW_REMAINING = FULL_REMAINING - SHARES
STOP_PRICE = 54.10           # current stop (below entry -> breakeven raises)
ENTRY_PRICE = 55.20
BREAKEVEN_PRICE = max(STOP_PRICE, ENTRY_PRICE)
LIMIT_PRICE = 59.58          # the +2R target
ACCOUNT_MODE = "live"


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


async def _replace_ok(order_id, *, qty=None, stop_price=None, limit_price=None,
                      account_mode=None, client_order_id=None):
    return {"id": "new_stop_id", "status": "accepted"}


async def _get_order_all_live(order_id, account_mode=None):
    return {"id": order_id, "status": "accepted", "order_class": "simple"}


OCO_LEG_ID = "oco_leg_1"


def _oco_parent_response():
    return {
        "id": "oco_parent_1", "status": "new", "order_class": "oco",
        "type": "limit", "side": "sell", "qty": float(SHARES),
        "limit_price": LIMIT_PRICE,
        "legs": [{"id": OCO_LEG_ID, "type": "stop", "status": "held",
                  "qty": float(SHARES), "stop_price": BREAKEVEN_PRICE}],
    }


def _harness(om, *, oco_enabled=True, resting_enabled=True,
             trade_overrides: dict | None = None):
    trade = _trade(**(trade_overrides or {}))
    pool, conn = _make_pool(trade)
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    telegram_mock = AsyncMock(return_value=True)
    oco_sell_mock = AsyncMock(return_value=_oco_parent_response())
    limit_sell_mock = AsyncMock(return_value={"id": "limit_sell_id", "status": "new"})
    market_sell_mock = AsyncMock(return_value={"id": "market_sell_id", "status": "new"})

    patches = [
        patch.object(om, "_PARTIAL_EXIT_PAUSED", False),
        patch.object(om, "_consecutive_partial_exit_failures", AsyncMock(return_value=0)),
        patch.object(om, "_trade_advisory_lock", _noop_lock()),
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "send_telegram_message", telegram_mock),
        patch.object(om, "set_stop_order_id", AsyncMock()),
        patch.object(om, "_ensure_stop_coverage", AsyncMock(return_value="repaired")),
        patch.object(om, "get_runtime_toggle", AsyncMock(return_value=False)),
        patch.object(om, "_profit_take_resting_limit_enabled",
                     AsyncMock(return_value=resting_enabled)),
        patch.object(om, "_profit_take_oco_enabled", AsyncMock(return_value=oco_enabled)),
        # breakeven replace on the 2/3 stop is out of scope here — keep it off
        # so the OCO assertions stay sharp.
        patch.object(om, "_breakeven_at_broker_enabled", AsyncMock(return_value=False)),
        patch.object(om.asyncio, "sleep", AsyncMock()),
        patch.object(om.alpaca, "replace_order", AsyncMock(side_effect=_replace_ok)),
        patch.object(om.alpaca, "get_order", _get_order_all_live),
        patch.object(om.alpaca, "get_position", AsyncMock(
            return_value={"qty": float(FULL_REMAINING),
                          "qty_available": float(FULL_REMAINING)})),
        patch.object(om.alpaca, "place_oco_sell", oco_sell_mock),
        patch.object(om.alpaca, "place_limit_sell", limit_sell_mock),
        patch.object(om.alpaca, "place_market_sell", market_sell_mock),
        patch.object(om.alpaca, "make_client_order_id",
                     lambda m, s, t: f"apollo_{m}_{s}_{t}_x"),
    ]
    return {
        "patches": patches, "audited": audited, "telegram": telegram_mock,
        "oco_sell": oco_sell_mock, "limit_sell": limit_sell_mock,
        "market_sell": market_sell_mock, "conn": conn, "trade": trade,
    }


async def _run(om, h, limit_price=LIMIT_PRICE):
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        return await om.execute_partial_exit(
            TRADE_ID, SHARES, force=True, limit_price=limit_price)


# ── 1. The OCO is placed: limit at the target, stop at breakeven, both recorded ─────


@pytest.mark.asyncio
async def test_oco_mode_places_one_oco_and_records_parent_plus_leg():
    """MUTATION-PROVEN: (a) reverting the sell branch to always place_limit_sell
    in resting mode reddens the place_oco_sell assertion; (b) deleting the leg
    INSERT reddens the leg-row assertion (run during development, then restored)."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om)
    ok = await _run(om, h)

    assert ok is True
    h["oco_sell"].assert_awaited_once()
    args, kwargs = h["oco_sell"].call_args
    assert args[0] == TICKER and int(args[1]) == SHARES
    assert float(args[2]) == LIMIT_PRICE, "OCO limit must sit AT the +2R target"
    assert float(args[3]) == BREAKEVEN_PRICE, "OCO stop must sit at BREAKEVEN"
    assert kwargs["account_mode"] == ACCOUNT_MODE
    assert kwargs["client_order_id"].startswith(f"apollo_{ACCOUNT_MODE}_")
    h["limit_sell"].assert_not_called()
    h["market_sell"].assert_not_called()

    inserts = [c for c in h["conn"].execute.call_args_list
               if c.args[0].strip().startswith("INSERT INTO mi_live_orders")]
    parent_rows = [c for c in inserts if "oco_parent_1" in c.args]
    leg_rows = [c for c in inserts if OCO_LEG_ID in c.args]
    assert parent_rows, "OCO parent must be recorded in mi_live_orders"
    assert "'partial_exit'" in parent_rows[0].args[0], \
        "parent rides purpose='partial_exit' so its fill routes to finalize_partial_exit"
    assert leg_rows, ("the sibling stop leg must be recorded — it is HIDDEN from "
                      "get_open_orders while held; this row is the mirror's only "
                      "record and what routes its fill to finalize_stop_fill")
    assert "'stop_loss'" in leg_rows[0].args[0]
    assert BREAKEVEN_PRICE in leg_rows[0].args, "leg row must carry the breakeven stop price"

    sent = " ".join(str(c.args[0]) for c in h["telegram"].call_args_list)
    assert "OCO" in sent, "the operator must be told this is an OCO, not a bare limit"


# ── 2-4. Toggle discipline ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oco_toggle_off_keeps_plain_resting_limit_byte_for_byte():
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, oco_enabled=False)
    ok = await _run(om, h)

    assert ok is True
    h["limit_sell"].assert_awaited_once()
    h["oco_sell"].assert_not_called()


@pytest.mark.asyncio
async def test_oco_toggle_unreadable_fails_closed_to_plain_limit():
    """The REAL `_profit_take_oco_enabled` runs against a broken db read — it must
    fail CLOSED (plain resting limit), never enable a money-path change on a
    hiccup. MUTATION-PROVEN: flipping the helper's except-return to True reddens
    this test."""
    from agents.market_intelligence.broker import order_manager as om
    from agents.market_intelligence import db as mi_db

    h = _harness(om)
    # un-mock the OCO toggle; break the db underneath it
    h["patches"] = [p for p in h["patches"]
                    if getattr(p, "attribute", None) != "_profit_take_oco_enabled"]
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        with patch.object(mi_db, "get_safeguard_state",
                          AsyncMock(side_effect=RuntimeError("db down"))):
            ok = await om.execute_partial_exit(
                TRADE_ID, SHARES, force=True, limit_price=LIMIT_PRICE)

    assert ok is True
    # resting toggle is mocked ON in the harness, so the sell is a plain limit
    h["limit_sell"].assert_awaited_once()
    h["oco_sell"].assert_not_called()


@pytest.mark.asyncio
async def test_oco_requires_resting_mode_market_path_untouched():
    """OCO ON but resting OFF -> the partial is a MARKET sell exactly as today;
    the OCO only upgrades the resting third (there is no resting third without
    resting mode)."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, resting_enabled=False)
    ok = await _run(om, h)

    assert ok is True
    h["market_sell"].assert_awaited_once()
    h["oco_sell"].assert_not_called()
    h["limit_sell"].assert_not_called()


@pytest.mark.asyncio
async def test_profit_take_oco_default_off_when_no_row():
    """Ships dark — a deploy changes nothing until the operator flips the row."""
    from agents.market_intelligence.broker import order_manager as om
    from agents.market_intelligence import db as mi_db

    with patch.object(mi_db, "get_safeguard_state", AsyncMock(return_value=None)):
        assert await om._profit_take_oco_enabled("live") is False
    with patch.object(mi_db, "get_safeguard_state",
                      AsyncMock(return_value={"state": "on"})):
        assert await om._profit_take_oco_enabled("live") is True
    with patch.object(mi_db, "get_safeguard_state",
                      AsyncMock(return_value={"state": "observe"})):
        assert await om._profit_take_oco_enabled("live") is False


# ── 5. The OCO stop can only ever sit AT or ABOVE the current stop ─────────────────


@pytest.mark.asyncio
async def test_oco_stop_never_below_current_stop_when_entry_is_lower():
    """A trailed/gapped position's stop can already sit ABOVE entry. The OCO
    sibling must use the HIGHER anchor — protecting the third LESS than it
    already was is never acceptable. MUTATION-PROVEN: swapping max() for min()
    in the anchor pick reddens this test."""
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, trade_overrides={"entry_price": 50.00})  # entry BELOW the stop
    ok = await _run(om, h)

    assert ok is True
    args, _ = h["oco_sell"].call_args
    assert float(args[3]) == STOP_PRICE, (
        "with entry below the stop, breakeven is a no-op — the OCO stop stays at "
        "the current stop, never drops to entry")


# ── 6. No anchor at all → plain limit + loud audit (never a broken OCO) ────────────


@pytest.mark.asyncio
async def test_oco_without_any_stop_anchor_falls_back_to_plain_limit():
    from agents.market_intelligence.broker import order_manager as om

    h = _harness(om, trade_overrides={
        "stop_price": None, "hard_stop": None, "entry_price": None,
        "stop_order_id": None,
    })
    ok = await _run(om, h)

    assert ok is True
    h["limit_sell"].assert_awaited_once()
    h["oco_sell"].assert_not_called()
    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_oco_fallback" in events, \
        "the downgrade must be RECORDED — a silent fallback hides a mispriced state"


# ── 7. place_oco_sell — the banked probe shape, verbatim ───────────────────────────


class _FakeLeg:
    def __init__(self):
        self.id = "leg-uuid-1"
        self.client_order_id = "x"
        self.symbol = TICKER
        self.side = "sell"
        self.type = "stop"
        self.qty = SHARES
        self.filled_qty = 0
        self.filled_avg_price = None
        self.stop_price = BREAKEVEN_PRICE
        self.limit_price = None
        self.status = "held"
        self.order_class = "oco"
        self.created_at = None
        self.filled_at = None
        self.legs = None


class _FakeParent:
    def __init__(self, with_leg=True):
        self.id = "parent-uuid-1"
        self.client_order_id = "x"
        self.symbol = TICKER
        self.side = "sell"
        self.type = "limit"
        self.qty = SHARES
        self.filled_qty = 0
        self.filled_avg_price = None
        self.stop_price = None
        self.limit_price = LIMIT_PRICE
        self.status = "new"
        self.order_class = "oco"
        self.created_at = None
        self.filled_at = None
        self.legs = [_FakeLeg()] if with_leg else []


@pytest.mark.asyncio
async def test_place_oco_sell_request_shape_matches_the_banked_probe():
    """The probe's accepted shape B, verbatim: order_class=OCO, GTC, top-level
    limit_price AND take_profit.limit_price (a bare limit_price is rejected
    40010001 — banked broker fact), stop_loss.stop_price tick-rounded.
    MUTATION-PROVEN: deleting the take_profit kwarg reddens this test."""
    from agents.market_intelligence.broker import alpaca_client as ac

    captured: dict = {}

    class _CapReq:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    async def _fake_sdk(fn, *args, timeout=None):
        captured["request"] = args[0]
        return _FakeParent()

    with patch.object(ac, "get_trading_client", MagicMock()), \
         patch.object(ac, "LimitOrderRequest", _CapReq), \
         patch.object(ac, "TakeProfitRequest", _CapReq), \
         patch.object(ac, "StopLossRequest", _CapReq), \
         patch.object(ac, "_sdk", AsyncMock(side_effect=_fake_sdk)):
        out = await ac.place_oco_sell(
            TICKER, SHARES, 59.579, 55.204,  # deliberately un-tick prices
            account_mode="live", client_order_id="apollo_live_magna53_ETON_1")

    req = captured["request"].kwargs
    from agents.market_intelligence.broker.alpaca_client import OrderClass, TimeInForce
    assert req["order_class"] is OrderClass.OCO
    assert req["time_in_force"] is TimeInForce.GTC
    assert req["limit_price"] == 59.58
    assert "take_profit" in req and req["take_profit"].kwargs["limit_price"] == 59.58, (
        "order_class=oco REQUIRES take_profit.limit_price — a bare limit_price "
        "returns 40010001 (banked probe fact); dropping this re-creates the reject")
    assert "stop_loss" in req and req["stop_loss"].kwargs["stop_price"] == 55.20, \
        "stop tick-rounded, flooring away from the trigger"
    assert req["client_order_id"] == "apollo_live_magna53_ETON_1"
    assert out["id"] == "parent-uuid-1"
    assert out["legs"] and out["legs"][0]["id"] == "leg-uuid-1"


@pytest.mark.asyncio
async def test_place_oco_sell_cancels_and_raises_when_no_stop_leg_returned():
    """NAKED-THIRD GUARD: a parent accepted WITHOUT a stop leg would rest
    limit-only — exactly the ETON hole this order exists to close. Cancel the
    parent + raise so the caller's abort path re-protects. MUTATION-PROVEN:
    deleting the extract_stop_leg_id guard reddens this test (no raise)."""
    from agents.market_intelligence.broker import alpaca_client as ac

    sdk_calls = []

    async def _fake_sdk(fn, *args, timeout=None):
        sdk_calls.append(getattr(fn, "__name__", str(fn)))
        if len(sdk_calls) == 1:
            return _FakeParent(with_leg=False)
        return None  # the cancel

    fake_client = MagicMock()
    with patch.object(ac, "get_trading_client", MagicMock(return_value=fake_client)), \
         patch.object(ac, "_sdk", AsyncMock(side_effect=_fake_sdk)):
        with pytest.raises(RuntimeError, match="no stop leg"):
            await ac.place_oco_sell(TICKER, SHARES, LIMIT_PRICE, BREAKEVEN_PRICE,
                                    account_mode="live")

    assert len(sdk_calls) == 2, "the stop-less parent must be CANCELLED, not left resting"


# ── 8. Coverage detector (#566 build flag 2) — the regression, explicitly ──────────

from tests.test_position_coverage_check_527 import (  # noqa: E402
    _trade as _cov_trade, _live_stop, _wire, _run_coverage_check,
)


def _oco_open_parent(qty, filled=0.0):
    return {"id": "oco-parent-x", "side": "sell", "type": "limit",
            "order_class": "oco", "qty": qty, "filled_qty": filled, "status": "new"}


@pytest.mark.asyncio
async def test_coverage_detector_counts_oco_parent_as_stop_coverage():
    """17 held = plain stop 12 + OCO parent 5 (its held stop leg is INVISIBLE to
    get_open_orders — banked probe fact). The detector must read this as COVERED;
    before the fix it false-alarmed 'Position unprotected' every session, the
    same wrong-reading class that produced this whole task. MUTATION-PROVEN:
    deleting the oco_stop_qty term reddens this test."""
    trades = [_cov_trade(9, "ETON", 17.0)]
    orders = {"ETON": [_live_stop("s23", 12.0), _oco_open_parent(5.0)]}
    ctx, audited, telegram_mock, _ = _wire(trades, orders)

    result = await _run_coverage_check(ctx)

    assert result["gaps"] == [], "OCO-covered position must NOT read as a gap"
    assert result["covered"] == 1
    telegram_mock.assert_not_called()
    assert audited == []


@pytest.mark.asyncio
async def test_coverage_detector_still_flags_a_plain_resting_limit_as_naked():
    """DEFECT-1 SEMANTICS PRESERVED: a PLAIN sell limit is NOT protection — a
    limit above the market covers nothing on a decline (the ETON incident
    itself). Only an OCO parent counts. MUTATION-PROVEN: widening the counting
    to all sell limits (dropping the order_class=='oco' condition) reddens this
    test."""
    trades = [_cov_trade(9, "ETON", 17.0)]
    plain_limit = {"id": "plain-limit-x", "side": "sell", "type": "limit",
                   "order_class": "simple", "qty": 5.0, "filled_qty": 0.0,
                   "status": "new"}
    orders = {"ETON": [_live_stop("s23", 12.0), plain_limit]}
    ctx, audited, telegram_mock, _ = _wire(trades, orders)

    result = await _run_coverage_check(ctx)

    assert len(result["gaps"]) == 1, (
        "a bare resting limit must still read as a 5-share GAP — counting it as "
        "coverage would blind the detector to the exact ETON defect")
    assert result["gaps"][0]["live_qty"] == 12.0
    assert any(evt == "position_unprotected" for evt, _, _ in audited)


@pytest.mark.asyncio
async def test_coverage_detector_counts_only_the_unfilled_part_of_a_partial_oco():
    """A partially-filled OCO parent (2 of 5 sold) reserves only its remainder;
    position also shrank by the fill. 15 held = stop 12 + OCO remainder 3 ->
    covered. Counting the parent's FULL qty would overstate protection by the
    filled part."""
    trades = [_cov_trade(9, "ETON", 15.0)]
    orders = {"ETON": [_live_stop("s23", 12.0), _oco_open_parent(5.0, filled=2.0)]}
    ctx, audited, telegram_mock, _ = _wire(trades, orders)

    result = await _run_coverage_check(ctx)

    assert result["gaps"] == [] and result["covered"] == 1
