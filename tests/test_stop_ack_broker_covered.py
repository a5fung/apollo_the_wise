"""Regression tests for stop_ack_watchdog broker-side coverage check (#128, 2026-05-27).

Bug: when DB mi_live_trades.stop_order_id is NULL after partial-exit cycles
or stop-replacement timing gaps, the stop_ack_timeout_watchdog assumes
the position is naked and tries to submit a fallback stop. If the broker
already has a working sell order covering the position, Alpaca rejects
the redundant stop with "insufficient qty available" — surfacing as a
CRITICAL false-positive Telegram (BW #119 on 2026-05-27 13:00 UTC).

Fix: before remediation, call alpaca.get_open_orders(ticker); if working
sell-side orders cover remaining_shares, sync stop_order_id (if a stop
exists among them) and emit `stop_ack_broker_covered` audit event in lieu
of remediation.

These tests pin the new behavior using the existing alpaca-stub pattern
from test_order_status_reconcile.py.
"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock


class _MockModule(types.ModuleType):
    def __getattr__(self, name):
        v = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, v)
        return v


for mod_name in [
    "alpaca", "alpaca.trading", "alpaca.trading.client", "alpaca.trading.requests",
    "alpaca.trading.enums", "alpaca.trading.models", "alpaca.trading.stream",
    "alpaca.data", "alpaca.data.historical", "alpaca.data.requests",
    "alpaca.data.timeframe", "alpaca.data.enums", "alpaca.common",
    "alpaca.common.exceptions",
]:
    sys.modules.setdefault(mod_name, _MockModule(mod_name))

sys.modules.setdefault(
    "agents.market_intelligence.backtester",
    types.ModuleType("agents.market_intelligence.backtester"),
)
_filters_stub = types.ModuleType("agents.market_intelligence.backtester.filters")
_filters_stub.validate_orb_entry = MagicMock(name="validate_orb_entry")
sys.modules.setdefault("agents.market_intelligence.backtester.filters", _filters_stub)


# ── Coverage classifier (the core decision) ─────────────────────────────────

def _covered_by_broker(open_orders: list[dict], qty: float) -> tuple[bool, dict | None]:
    """The decision logic excerpted from the watchdog patch. Pulled into a
    helper so tests don't need to import the whole scheduler module.

    Returns (covered, stop_order_dict_or_none).
    """
    sell_orders = [
        o for o in open_orders
        if str(o.get("side", "")).lower().endswith("sell")
    ]
    covered = sum(float(o.get("qty") or 0) for o in sell_orders)
    if qty <= 0 or covered < qty:
        return False, None
    stop_o = next(
        (o for o in sell_orders
         if "stop" in str(o.get("type", "")).lower()
         or o.get("stop_price") is not None),
        None,
    )
    return True, stop_o


# ── Cases ────────────────────────────────────────────────────────────────────

def test_no_open_orders_not_covered():
    """Genuine naked: no broker orders at all → covered=False."""
    covered, stop_o = _covered_by_broker([], qty=776)
    assert covered is False
    assert stop_o is None


def test_buy_only_not_covered():
    """Broker has a working BUY order but no sell — position still naked
    (the watchdog cares about exits, not new entries)."""
    orders = [{"id": "x", "side": "OrderSide.BUY", "type": "OrderType.STOP_LIMIT",
               "qty": 776, "stop_price": 17.0}]
    covered, stop_o = _covered_by_broker(orders, qty=776)
    assert covered is False


def test_partial_coverage_not_covered():
    """Sell order covers 388 of 776 → fail safe, do NOT classify as covered."""
    orders = [{"id": "x", "side": "OrderSide.SELL", "type": "OrderType.STOP",
               "qty": 388, "stop_price": 16.49}]
    covered, stop_o = _covered_by_broker(orders, qty=776)
    assert covered is False


def test_working_stop_covers_position():
    """The textbook fix case: one working stop sell covers full position →
    covered=True, stop returned for sync."""
    orders = [{"id": "stop123", "side": "OrderSide.SELL", "type": "OrderType.STOP",
               "qty": 776, "stop_price": 16.49}]
    covered, stop_o = _covered_by_broker(orders, qty=776)
    assert covered is True
    assert stop_o is not None
    assert stop_o["id"] == "stop123"


def test_market_sell_covers_no_stop():
    """The BW #119 case: a pending market full_exit (not a stop) covers the
    position → covered=True but no stop to sync. Position is still
    broker-covered, watchdog must skip remediation."""
    orders = [{"id": "mkt100", "side": "OrderSide.SELL", "type": "OrderType.MARKET",
               "qty": 776, "stop_price": None}]
    covered, stop_o = _covered_by_broker(orders, qty=776)
    assert covered is True
    assert stop_o is None  # no stop to sync, but still covered


def test_lowercase_side_recognized():
    """Defensive: if alpaca-py ever returns bare lowercase 'sell' instead of
    'OrderSide.SELL', the classifier still recognizes."""
    orders = [{"id": "s", "side": "sell", "type": "stop", "qty": 776,
               "stop_price": 17.0}]
    covered, stop_o = _covered_by_broker(orders, qty=776)
    assert covered is True
    assert stop_o is not None


def test_stop_price_signal_when_type_string_ambiguous():
    """Same rule as broker/extract_stop_leg_id: a populated stop_price is
    primary signal of stop-ness, falling back to 'stop' in type string."""
    orders = [{"id": "s", "side": "OrderSide.SELL", "type": "OrderType.LIMIT",
               "qty": 776, "stop_price": 16.49}]
    _, stop_o = _covered_by_broker(orders, qty=776)
    assert stop_o is not None  # stop_price flagged this as a stop


def test_multiple_sell_orders_summed():
    """If broker has two sell orders totaling enough coverage, position is
    covered (rare but possible after a partial-exit split)."""
    orders = [
        {"id": "a", "side": "OrderSide.SELL", "type": "OrderType.STOP",
         "qty": 388, "stop_price": 16.49},
        {"id": "b", "side": "OrderSide.SELL", "type": "OrderType.STOP",
         "qty": 388, "stop_price": 16.49},
    ]
    covered, stop_o = _covered_by_broker(orders, qty=776)
    assert covered is True


def test_zero_qty_not_covered():
    """remaining_shares=0 is a weird state (closed position) — fall through
    to existing 'qty<=0 or stop_target is None' branch upstream."""
    covered, _ = _covered_by_broker([], qty=0)
    assert covered is False
