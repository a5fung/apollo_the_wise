"""#500 (2026-07-23, operator-signed) — price-aware initial ORB entry + broker-cancel
reason capture.

ARWR 2026-07-22 (live): a +19.6% gapper blew through its ORB high before the
9:31:00.8 stop-limit bracket landed — an in-the-money buy stop is invalid at the
broker, so Alpaca cancelled the entry (pending_new → cancelled) and the operator
saw "entry cancelled, no reason". Evidence + design:
docs/analysis/500_orb_entry_price_aware_proposal_2026-07-23.md.

Pins:
1. submit_entry below/at ORB high → the bracket, byte-identical (stop=orb_high,
   limit=stop_limit_buy_price) — the overwhelming-majority path must not move.
2. get_latest_trade None / no-price → bracket (fail-open: a data flake must
   never change entry mechanics).
3. Above ORB high → place_limit_buy_with_stop at round(latest*1.002, 2), stop
   unchanged; mi_live_orders records the ACTUAL order (type 'limit', no trigger,
   the real limit price).
4. Above the 1.5x chase cap → NO order, skip_reason setup:chase_cap_exceeded +
   Telegram via humanize (terminal-failure contract); exact-at-cap still admits.
5. The 5s retry re-decides the branch (price moves fast at 9:31).
6. place_limit_buy_with_stop hardening: OrderClass.OTO + StopLossRequest (the
   alpaca-py silently-dropped-stop_loss gotcha) + the naked-order guard
   (no stop leg back → cancel entry + raise). Latent re-entry bug — the branch
   had never fired in prod.
7. attempt_day1_reentry's price-aware branch (mirrored logic) exercised
   directly for the first time.
8. broker_terminal_reason: broker:* skip_reason with last-vs-trigger diagnosis;
   degrades to the bare prefix on any data problem. Wired into the WS
   cancel/reject handler (+ terminal order snapshot persisted, failure-isolated)
   and the check_fills polling backup.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import make_mock_pool
from agents.market_intelligence.broker import alpaca_client as alp
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts
from agents.market_intelligence.broker.skip_reasons import (
    BROKER_ENTRY_CANCELLED,
    BROKER_ENTRY_EXPIRED,
    BROKER_ENTRY_REJECTED,
    SETUP_CHASE_CAP_EXCEEDED,
    humanize,
)

_TRADE = {
    "id": 7, "ticker": "TSTX", "account_mode": "paper", "signal_type": "magna53",
    "orb_high": 10.5, "orb_low": 9.5, "stop_price": 9.5, "entry_shares": 100,
    "entry_price": 10.5, "remaining_shares": 100, "entry_attempt": 1,
    "exits": [], "atr_14": 0.4, "stop_order_id": None, "alert_date": None,
    "ep_score": 70, "catalyst_quality": "strong", "gap_pct": 8.0, "regime": "Bull",
}

_ORDER = {"id": "ord-1", "status": "accepted", "legs": []}


def _wire_submit_entry(monkeypatch, latest, trade=None):
    """Wire submit_entry's collaborators. Returns (fake_alpaca, conn, sent)."""
    pool, conn = make_mock_pool()
    # fetchrow #1 = the halt peek (paper → halt not consulted), #2 = the claim.
    trade = dict(trade or _TRADE)
    conn.fetchrow = AsyncMock(side_effect=[{"account_mode": trade["account_mode"]}, trade])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    fake_alpaca = MagicMock()
    fake_alpaca.get_latest_trade = AsyncMock(
        side_effect=latest if isinstance(latest, list) else [latest, latest],
    )
    fake_alpaca.place_bracket_order = AsyncMock(return_value=dict(_ORDER))
    fake_alpaca.place_limit_buy_with_stop = AsyncMock(return_value=dict(_ORDER))
    fake_alpaca.extract_stop_leg_id = MagicMock(return_value="stp-1")
    fake_alpaca.make_client_order_id = MagicMock(return_value="coid-1")
    monkeypatch.setattr(om, "alpaca", fake_alpaca)
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())

    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(om, "send_telegram_message", _capture)
    return fake_alpaca, conn, sent


def _entry_insert_args(conn):
    """The mi_live_orders entry INSERT is the 2nd execute (after the trade UPDATE)."""
    calls = conn.execute.await_args_list
    for c in calls:
        if "INSERT INTO mi_live_orders" in c.args[0] and "'buy'" in c.args[0]:
            return c.args
    raise AssertionError(f"entry INSERT not found in {[c.args[0][:60] for c in calls]}")


# ─── 1+2. Below / fail-open → the bracket, byte-identical ────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("latest", [
    {"price": 10.40},   # below ORB high
    {"price": 10.50},   # AT ORB high (not strictly above → bracket)
    {"price": None},    # feed returned no price
    None,               # feed down
])
async def test_below_or_no_price_places_bracket_byte_identical(monkeypatch, latest):
    fake, conn, _ = _wire_submit_entry(monkeypatch, latest)

    result = await om.submit_entry(7)

    assert result is not None
    fake.place_limit_buy_with_stop.assert_not_awaited()
    fake.place_bracket_order.assert_awaited_once()
    kw = fake.place_bracket_order.await_args.kwargs
    assert kw["stop_price"] == 10.5
    assert kw["limit_price"] == om.stop_limit_buy_price(10.5)
    assert kw["stop_loss_price"] == 9.5
    assert kw["client_order_id"] == "coid-1"
    # mi_live_orders records the bracket exactly as before #500
    args = _entry_insert_args(conn)
    assert "stop_limit" in args
    assert 10.5 in args and om.stop_limit_buy_price(10.5) in args


# ─── 3. Above ORB high → bounded limit fallback ──────────────────────────────


@pytest.mark.asyncio
async def test_above_orb_high_places_limit_at_latest_x_1002(monkeypatch):
    fake, conn, _ = _wire_submit_entry(monkeypatch, {"price": 10.63})

    result = await om.submit_entry(7)

    assert result is not None
    fake.place_bracket_order.assert_not_awaited()
    fake.place_limit_buy_with_stop.assert_awaited_once()
    kw = fake.place_limit_buy_with_stop.await_args.kwargs
    assert kw["limit_price"] == round(10.63 * 1.002, 2)  # 10.65
    assert kw["stop_loss_price"] == 9.5                  # stop UNCHANGED
    assert kw["qty"] == 100                              # sizing UNCHANGED
    assert kw["client_order_id"] == "coid-1"
    # mi_live_orders records the ACTUAL order: type limit, no trigger price
    args = _entry_insert_args(conn)
    assert "limit" in args and "stop_limit" not in args
    assert None in args                                  # stop_price column
    assert round(10.63 * 1.002, 2) in args               # the real limit


# ─── 4. Chase cap ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_above_cap_skips_no_order_and_telegrams(monkeypatch):
    # planned risk 1.0; latest 12.00 → limit 12.02 → actual 2.52 > 1.5x cap
    fake, conn, sent = _wire_submit_entry(monkeypatch, {"price": 12.00})
    upd = AsyncMock()
    monkeypatch.setattr(om, "_update_trade_status", upd)

    result = await om.submit_entry(7)

    assert result is None
    fake.place_bracket_order.assert_not_awaited()
    fake.place_limit_buy_with_stop.assert_not_awaited()
    upd.assert_awaited_once()
    args, kwargs = upd.await_args
    assert args[0] == 7 and args[1] == "cancelled"
    assert kwargs["skip_reason"].startswith(SETUP_CHASE_CAP_EXCEEDED)
    # terminal-failure contract: Telegram via humanize()
    assert any("Ran too far past ORB high to chase" in m for m in sent)
    audit = om.log_audit_event
    assert any(c.args[0] == "entry_chase_cap_skipped" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_exactly_at_cap_still_admits(monkeypatch):
    # planned 1.0; latest 10.978 → limit round(10.999956, 2) = 11.00 →
    # actual 1.50 == 1.5 x 1.0 → admitted (<= is inclusive)
    fake, _, _ = _wire_submit_entry(monkeypatch, {"price": 10.978})

    result = await om.submit_entry(7)

    assert result is not None
    fake.place_limit_buy_with_stop.assert_awaited_once()
    assert fake.place_limit_buy_with_stop.await_args.kwargs["limit_price"] == 11.0


# ─── 5. Retry re-decides the branch ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_redecides_branch_after_first_submit_fails(monkeypatch):
    # 1st look: below → bracket → raises; 2nd look (after "5s"): above → limit.
    fake, _, _ = _wire_submit_entry(
        monkeypatch, [{"price": 10.40}, {"price": 10.63}],
    )
    fake.place_bracket_order = AsyncMock(side_effect=RuntimeError("transient"))
    monkeypatch.setattr(om.asyncio, "sleep", AsyncMock())

    result = await om.submit_entry(7)

    assert result is not None
    fake.place_bracket_order.assert_awaited_once()        # attempt 1 only
    fake.place_limit_buy_with_stop.assert_awaited_once()  # attempt 2, re-decided
    assert fake.get_latest_trade.await_count == 2
    assert fake.make_client_order_id.call_count == 2      # fresh COID on retry


# ─── 6. place_limit_buy_with_stop hardening (OTO + naked-guard) ─────────────


def _mk_limit_order(with_stop_leg: bool):
    leg = SimpleNamespace(
        id="leg-1", client_order_id="c-leg", symbol="TSTX", side="sell",
        type="stop", qty=100, filled_qty=0, filled_avg_price=None,
        stop_price=9.5, limit_price=None, status="new",
        created_at=None, filled_at=None, legs=None,
    )
    return SimpleNamespace(
        id="ord-9", client_order_id="c-0", symbol="TSTX", side="buy",
        type="limit", qty=100, filled_qty=0, filled_avg_price=None,
        stop_price=None, limit_price=10.65, status="accepted",
        created_at=None, filled_at=None, legs=[leg] if with_stop_leg else None,
    )


@pytest.mark.asyncio
async def test_limit_buy_passes_oto_and_stop_loss_request(monkeypatch):
    """The alpaca-py gotcha: without order_class=OTO the stop_loss kwarg is
    silently dropped → a NAKED limit buy. Pin the request construction."""
    client = MagicMock()
    client.submit_order = MagicMock(return_value=_mk_limit_order(with_stop_leg=True))
    monkeypatch.setattr(alp, "get_trading_client", MagicMock(return_value=client))
    lim_req = MagicMock(name="LimitOrderRequest")
    sl_req = MagicMock(name="StopLossRequest")
    monkeypatch.setattr(alp, "LimitOrderRequest", lim_req)
    monkeypatch.setattr(alp, "StopLossRequest", sl_req)

    result = await alp.place_limit_buy_with_stop(
        ticker="TSTX", qty=100, limit_price=10.65, stop_loss_price=9.5,
        account_mode="paper", client_order_id="coid-1",
    )

    sl_req.assert_called_once_with(stop_price=9.5)
    kw = lim_req.call_args.kwargs
    assert kw["order_class"] is alp.OrderClass.OTO
    assert kw["stop_loss"] is sl_req.return_value
    assert kw["limit_price"] == 10.65
    assert kw["client_order_id"] == "coid-1"
    assert result["id"] == "ord-9"
    assert result["legs"] and result["legs"][0]["id"] == "leg-1"


@pytest.mark.asyncio
async def test_limit_buy_naked_guard_cancels_and_raises(monkeypatch):
    client = MagicMock()
    client.submit_order = MagicMock(return_value=_mk_limit_order(with_stop_leg=False))
    monkeypatch.setattr(alp, "get_trading_client", MagicMock(return_value=client))
    monkeypatch.setattr(alp, "LimitOrderRequest", MagicMock())
    monkeypatch.setattr(alp, "StopLossRequest", MagicMock())

    with pytest.raises(RuntimeError, match="no stop_loss leg"):
        await alp.place_limit_buy_with_stop(
            ticker="TSTX", qty=100, limit_price=10.65, stop_loss_price=9.5,
            account_mode="paper",
        )

    client.cancel_order_by_id.assert_called_once_with("ord-9")


# ─── 7. The re-entry price-aware branch, exercised directly ─────────────────


@pytest.mark.asyncio
async def test_reentry_above_orb_high_uses_limit_buy(monkeypatch):
    import datetime as _dt

    class _FrozenDT(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            base = _dt.datetime(2026, 7, 23, 13, 45, tzinfo=_dt.timezone.utc)  # 9:45 ET
            return base.astimezone(tz) if tz else base.replace(tzinfo=None)

    monkeypatch.setenv("R3_DAY1_REENTRY_ENABLED", "true")
    monkeypatch.setattr(om, "datetime", _FrozenDT)
    monkeypatch.setattr(om, "LIVE_TRADING_ENABLED", True)

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=dict(_TRADE))
    conn.execute = AsyncMock()
    # #588: attempt_day1_reentry now nets `get_pending_exit_qty` off the recorded
    # stop-leg shares. 0 = nothing resting, which is this test's case — the
    # re-entry branch it asserts on is unaffected either way.
    conn.fetchval = AsyncMock(return_value=0)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "send_telegram_message", AsyncMock(return_value=True))

    fake_alpaca = MagicMock()
    fake_alpaca.get_latest_trade = AsyncMock(return_value={"price": 10.63})
    fake_alpaca.place_limit_buy_with_stop = AsyncMock(return_value=dict(_ORDER))
    fake_alpaca.place_bracket_order = AsyncMock(return_value=dict(_ORDER))
    fake_alpaca.extract_stop_leg_id = MagicMock(return_value="stp-2")
    fake_alpaca.make_client_order_id = MagicMock(return_value="coid-2")
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    # stop_fill == stop (no gap-through), 9:45 ET (before 11), R3 enabled
    result = await om.attempt_day1_reentry(7, 9.5, source="polling")

    assert result["action"] == "reentry"
    assert result["order_type"] == "limit"
    fake_alpaca.place_bracket_order.assert_not_awaited()
    kw = fake_alpaca.place_limit_buy_with_stop.await_args.kwargs
    assert kw["limit_price"] == round(10.63 * 1.002, 2)
    assert kw["stop_loss_price"] == 9.5


# ─── 8. broker_terminal_reason + the two capture paths ──────────────────────


@pytest.mark.asyncio
async def test_reason_above_trigger_flags_in_the_money_stop(monkeypatch):
    fake = MagicMock(get_latest_trade=AsyncMock(return_value={"price": 89.06}))
    monkeypatch.setattr(om, "alpaca", fake)

    r = await om.broker_terminal_reason("cancelled", "ARWR", 87.92)

    assert r == (
        f"{BROKER_ENTRY_CANCELLED}: last $89.06 above trigger $87.92 at event "
        f"— in-the-money stop (#500 class)"
    )
    # And it humanizes into an operator-readable phrase
    assert humanize(r).startswith("Broker cancelled the entry order (last $89.06")


@pytest.mark.asyncio
async def test_reason_below_trigger_no_500_flag(monkeypatch):
    fake = MagicMock(get_latest_trade=AsyncMock(return_value={"price": 102.36}))
    monkeypatch.setattr(om, "alpaca", fake)

    r = await om.broker_terminal_reason("rejected", "AEHR", 102.46)

    assert r.startswith(f"{BROKER_ENTRY_REJECTED}: last $102.36 at/below trigger $102.46")
    assert "#500 class" not in r


@pytest.mark.asyncio
@pytest.mark.parametrize("event,prefix", [
    ("cancelled", BROKER_ENTRY_CANCELLED),
    ("canceled", BROKER_ENTRY_CANCELLED),   # Alpaca's one-L spelling
    ("rejected", BROKER_ENTRY_REJECTED),
    ("expired", BROKER_ENTRY_EXPIRED),
    ("weird_event", BROKER_ENTRY_CANCELLED),  # unknown → safe default
])
async def test_reason_degrades_to_bare_prefix_on_data_problems(monkeypatch, event, prefix):
    fake = MagicMock(get_latest_trade=AsyncMock(side_effect=RuntimeError("feed down")))
    monkeypatch.setattr(om, "alpaca", fake)
    assert await om.broker_terminal_reason(event, "TSTX", 10.5) == prefix
    # None trigger also degrades (never raises)
    fake.get_latest_trade = AsyncMock(return_value={"price": 10.0})
    assert await om.broker_terminal_reason(event, "TSTX", None) == prefix


def _ws_data(order_id="ord-arwr-1", symbol="ARWR"):
    return SimpleNamespace(order=SimpleNamespace(
        id=order_id, symbol=symbol, status="canceled",
        canceled_at=None, failed_at=None, expired_at=None, updated_at=None,
        filled_qty=0, type="stop_limit", limit_price=88.36, stop_price=87.92,
    ))


_ARWR_ROW = {
    "id": 270, "ticker": "ARWR", "gap_pct": 19.57, "ep_score": 80.0,
    "entry_price": 87.92, "stop_price": 84.34, "regime": "Uptrend",
    "signal_type": "magna53",
}


async def _run_ws_cancel(monkeypatch, latest, exec_side_effect=None):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=[dict(_ARWR_ROW)])
    conn.execute = AsyncMock(side_effect=exec_side_effect)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(ts, "log_audit_event", audit)
    monkeypatch.setattr(om, "alpaca", MagicMock(get_latest_trade=latest))

    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "send_telegram_message", _capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")
    return sent, audit, conn


@pytest.mark.asyncio
async def test_ws_cancel_writes_diagnosis_and_terminal_snapshot(monkeypatch):
    sent, audit, conn = await _run_ws_cancel(
        monkeypatch, AsyncMock(return_value={"price": 89.06}),
    )

    execs = conn.execute.await_args_list
    trades_upd = [c for c in execs if "mi_live_trades" in c.args[0]]
    assert len(trades_upd) == 1
    reason = trades_upd[0].args[2]
    assert reason.startswith(f"{BROKER_ENTRY_CANCELLED}: last $89.06 above trigger $87.92")
    assert "#500 class" in reason

    orders_upd = [c for c in execs if "mi_live_orders" in c.args[0]]
    assert len(orders_upd) == 1
    assert orders_upd[0].args[1] == "ord-arwr-1"
    # #216 (2026-08-18): get_pool's jsonb codec already encodes this param — the
    # snapshot must be bound as a plain dict, NOT a pre-dumped JSON string (that
    # double-encodes and lands as jsonb_typeof='string' nested under 'terminal').
    snapshot = orders_upd[0].args[3]
    assert isinstance(snapshot, dict), (
        f"terminal snapshot param must be a plain dict — got {type(snapshot)}"
    )
    assert snapshot["status"] == "canceled"
    assert snapshot["limit_price"] == "88.36"

    # The #475 audit row carries the diagnosis
    from agents.market_intelligence.audit_events import ENTRY_ORDER_REJECTED
    calls = [c for c in audit.await_args_list if c.args[0] == ENTRY_ORDER_REJECTED]
    assert len(calls) == 1
    assert json.loads(calls[0].args[2])["skip_reason"] == reason

    # Operator Telegram carries the humanized reason — never a bare "cancelled"
    assert any("Broker cancelled the entry order" in m and "$89.06" in m for m in sent)


@pytest.mark.asyncio
async def test_ws_cancel_diagnosis_fetch_failure_degrades_gracefully(monkeypatch):
    sent, _, conn = await _run_ws_cancel(
        monkeypatch, AsyncMock(side_effect=RuntimeError("feed down")),
    )
    trades_upd = [c for c in conn.execute.await_args_list if "mi_live_trades" in c.args[0]]
    assert trades_upd[0].args[2] == BROKER_ENTRY_CANCELLED  # bare prefix, still broker:*
    assert any("Broker cancelled the entry order" in m for m in sent)


@pytest.mark.asyncio
async def test_ws_cancel_snapshot_persist_failure_never_blocks_telegram(monkeypatch):
    # 1st execute (trades UPDATE) fine; 2nd (orders snapshot) blows up.
    sent, audit, _ = await _run_ws_cancel(
        monkeypatch, AsyncMock(return_value={"price": 89.06}),
        exec_side_effect=[None, RuntimeError("db hiccup")],
    )
    assert any("Entry CANCELLED" in m for m in sent)
    from agents.market_intelligence.audit_events import ENTRY_ORDER_REJECTED
    assert any(c.args[0] == ENTRY_ORDER_REJECTED for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_check_fills_polling_cancel_writes_broker_reason(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[{
        "id": 7, "ticker": "TSTX", "entry_order_id": "ent-1", "entry_shares": 100,
        "orb_low": 9.5, "orb_high": 10.5, "stop_price": 9.5, "entry_attempt": 1,
        "account_mode": "paper",
    }], []])  # 2nd fetch = Day-1 stop-out poll → empty
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    fake = MagicMock()
    fake.get_order = AsyncMock(return_value={"status": "canceled"})
    fake.get_latest_trade = AsyncMock(return_value={"price": 10.63})
    monkeypatch.setattr(om, "alpaca", fake)
    upd = AsyncMock()
    monkeypatch.setattr(om, "_update_trade_status", upd)

    results = await om.check_fills()

    assert results == [{"ticker": "TSTX", "action": "canceled"}]
    upd.assert_awaited_once()
    args, kwargs = upd.await_args
    assert args[1] == "cancelled"
    assert kwargs["skip_reason"].startswith(f"{BROKER_ENTRY_CANCELLED}: last $10.63 above trigger $10.50")
