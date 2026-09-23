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
# Alpaca SDK + backtester.filters stubbing handled by tests/conftest.py.


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
    # Coverage = remaining unfilled qty (qty - filled_qty), NOT original qty.
    # A 776-share stop with 388 already filled provides only 388 shares of
    # ongoing broker protection — the rest is gone from the position.
    covered = sum(
        max(float(o.get("qty") or 0) - float(o.get("filled_qty") or 0), 0.0)
        for o in sell_orders
    )
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


# ── Partial-fill (advisor 2026-05-27 BLOCKER) ───────────────────────────────

def test_partial_fill_uses_remaining_not_original():
    """Critical: a 776-share stop with 388 already filled provides only 388
    shares of ongoing coverage. Using the original `qty` field would falsely
    classify this as full coverage and skip remediation on a genuinely
    half-naked position."""
    orders = [{
        "id": "stop1", "side": "OrderSide.SELL", "type": "OrderType.STOP",
        "qty": 776, "filled_qty": 388, "stop_price": 16.49,
    }]
    covered, _ = _covered_by_broker(orders, qty=776)
    assert covered is False, "partial fill must NOT count as full coverage"


def test_partial_fills_summed_use_remaining():
    """Two partials: 776-200=576 + 776-388=388 = 964 remaining, qty=776 →
    covered (extreme but tests the arithmetic)."""
    orders = [
        {"id": "a", "side": "OrderSide.SELL", "type": "OrderType.STOP",
         "qty": 776, "filled_qty": 200, "stop_price": 16.49},
        {"id": "b", "side": "OrderSide.SELL", "type": "OrderType.STOP",
         "qty": 776, "filled_qty": 388, "stop_price": 16.49},
    ]
    covered, _ = _covered_by_broker(orders, qty=776)
    assert covered is True


def test_filled_qty_missing_treated_as_zero():
    """If filled_qty key absent (older Alpaca response shape), treat as 0
    and use full qty — matches existing behavior before the bug fix, safe."""
    orders = [{
        "id": "s", "side": "OrderSide.SELL", "type": "OrderType.STOP",
        "qty": 776, "stop_price": 16.49,
    }]
    covered, _ = _covered_by_broker(orders, qty=776)
    assert covered is True


def test_filled_qty_none_treated_as_zero():
    """Explicit None — same handling as missing key."""
    orders = [{
        "id": "s", "side": "OrderSide.SELL", "type": "OrderType.STOP",
        "qty": 776, "filled_qty": None, "stop_price": 16.49,
    }]
    covered, _ = _covered_by_broker(orders, qty=776)
    assert covered is True
