"""#433 (2026-07-06, WULF live) — the two false naked-stop alarm sources.

WULF filled + protected, but the operator got "STOP ORDER FAILED / NO stop
protection" (order_manager first-attempt failure, retry succeeded 4s later with
no retraction) AND "Position unprotected, remediation 4:05" (trade_stream fired
on the OLD OTO leg being canceled while the NEW stop was already live). Both
were FALSE — the position was continuously protected.

This pins the replacement-stop classifier (`_find_replacement_stop`) that the
trade_stream cancel handler uses to decide "stop replaced / protected" vs the
genuine "unprotected" alarm. HARD INVARIANT: it only ever returns a match (=>
downgrade) on POSITIVE broker evidence; None / empty / read-failure => alarm.
Mirrors the #128 `_covered_by_broker` broker-authoritative precedent.
"""
from agents.market_intelligence.broker.trade_stream import _find_replacement_stop

CANCELED = "e1775b04-old-oto-leg"


def test_live_replacement_stop_found_downgrades():
    """The WULF shape: old OTO leg canceled, a new stop is live at the broker."""
    open_orders = [
        {"id": "6640a645-new-stop", "symbol": "WULF", "type": "stop", "stop_price": 23.80},
    ]
    r = _find_replacement_stop(open_orders, "WULF", CANCELED)
    assert r is not None and r["id"] == "6640a645-new-stop"


def test_stop_price_only_type_counts_as_stop():
    """A stop identified by stop_price even if type string is generic."""
    open_orders = [{"id": "x", "symbol": "WULF", "type": "limit", "stop_price": 23.8}]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED) is not None


def test_no_orders_returns_none_so_caller_alarms():
    """Genuinely naked: broker has nothing → None → caller must alarm."""
    assert _find_replacement_stop([], "WULF", CANCELED) is None
    assert _find_replacement_stop(None, "WULF", CANCELED) is None


def test_the_canceled_order_itself_is_never_the_replacement():
    """A stale copy of the just-canceled order must not count as protection."""
    open_orders = [{"id": CANCELED, "symbol": "WULF", "type": "stop", "stop_price": 23.8}]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED) is None


def test_other_symbol_stop_does_not_count():
    """A live stop on a DIFFERENT symbol is not protection for this one."""
    open_orders = [{"id": "z", "symbol": "NVDA", "type": "stop", "stop_price": 100.0}]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED) is None


def test_non_stop_order_same_symbol_does_not_count():
    """An open BUY/limit on the same symbol is not stop protection."""
    open_orders = [{"id": "b", "symbol": "WULF", "type": "limit", "stop_price": None}]
    assert _find_replacement_stop(open_orders, "WULF", CANCELED) is None
