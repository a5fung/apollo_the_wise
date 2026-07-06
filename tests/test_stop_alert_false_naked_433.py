"""#433 (2026-07-06, WULF live) — the two false naked-stop alarm sources.

WULF filled + protected, but the operator got "STOP ORDER FAILED / NO stop
protection" (order_manager first-attempt failure, retry succeeded 4s later with
no retraction) AND "Position unprotected, remediation 4:05" (trade_stream fired
on the OLD OTO leg being canceled while the NEW stop was already live). Both
were FALSE — the position was continuously protected.

This pins the replacement-stop classifier (`_find_replacement_stop`) that the
trade_stream cancel handler uses to decide "stop replaced / protected" vs the
genuine "unprotected" alarm. HARD INVARIANT: it only ever returns a match (=>
downgrade) on POSITIVE broker evidence of a SELL stop covering the position;
None / empty / read-failure / wrong-side / partial-coverage => alarm. Mirrors
the #128 `_covered_by_broker` broker-authoritative precedent (sell-side first,
qty coverage, then the stop). The sell-side filter is load-bearing: a stop-limit
BUY carries a stop_price and must NOT read as protection for a long.
"""
from agents.market_intelligence.broker.trade_stream import _find_replacement_stop

CANCELED = "e1775b04-old-oto-leg"
QTY = 40


def test_live_sell_replacement_stop_found_downgrades():
    """The WULF shape: old OTO leg canceled, a new SELL stop covers the position."""
    open_orders = [
        {"id": "6640a645", "symbol": "WULF", "side": "sell", "type": "stop",
         "qty": 40, "filled_qty": 0, "stop_price": 23.80},
    ]
    r = _find_replacement_stop(open_orders, "WULF", CANCELED, QTY)
    assert r is not None and r["id"] == "6640a645"


def test_BUY_stop_limit_does_NOT_count_as_protection():
    """LOAD-BEARING invariant: a stop-limit BUY (entry / Day-1 re-entry) carries a
    stop_price but protects nothing on a long — must NOT suppress the alarm."""
    open_orders = [
        {"id": "entry-99505796", "symbol": "WULF", "side": "buy",
         "type": "stop_limit", "qty": 40, "filled_qty": 0, "stop_price": 24.61},
    ]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED, QTY) is None


def test_partial_sell_coverage_does_NOT_count():
    """A sell stop covering only part of the position is not full protection."""
    open_orders = [
        {"id": "s", "symbol": "WULF", "side": "sell", "type": "stop",
         "qty": 25, "filled_qty": 0, "stop_price": 23.8},
    ]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED, QTY) is None


def test_no_orders_returns_none_so_caller_alarms():
    """Genuinely naked: broker has nothing → None → caller must alarm."""
    assert _find_replacement_stop([], "WULF", CANCELED, QTY) is None
    assert _find_replacement_stop(None, "WULF", CANCELED, QTY) is None


def test_unknown_remaining_shares_returns_none():
    """Ambiguous qty must fall through to alarm, never claim protection."""
    open_orders = [{"id": "s", "symbol": "WULF", "side": "sell", "type": "stop",
                    "qty": 40, "filled_qty": 0, "stop_price": 23.8}]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED, None) is None


def test_the_canceled_order_itself_is_never_the_replacement():
    """A stale copy of the just-canceled order must not count as protection."""
    open_orders = [{"id": CANCELED, "symbol": "WULF", "side": "sell", "type": "stop",
                    "qty": 40, "filled_qty": 0, "stop_price": 23.8}]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED, QTY) is None


def test_other_symbol_sell_stop_does_not_count():
    """A live sell stop on a DIFFERENT symbol is not protection for this one."""
    open_orders = [{"id": "z", "symbol": "NVDA", "side": "sell", "type": "stop",
                    "qty": 40, "filled_qty": 0, "stop_price": 100.0}]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED, QTY) is None


def test_sell_limit_covers_qty_but_a_stop_must_exist():
    """Sell-side coverage from a plain limit sell (no stop) is not a stop → None."""
    open_orders = [{"id": "lim", "symbol": "WULF", "side": "sell", "type": "limit",
                    "qty": 40, "filled_qty": 0, "stop_price": None}]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED, QTY) is None
