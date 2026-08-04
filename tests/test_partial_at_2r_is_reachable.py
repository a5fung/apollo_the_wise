"""The 2R partial must be able to actually fire — on any day of the hold (2026-08-04).

⚖ Operator, 2026-08-04: *"We buy a stock, it reaches 2R (i don't care if it's same day or
10 days later, we take partial profit at 2R)."* This file pins the second half of that
sentence: not that the rule EXISTS, but that nothing structurally prevents it from
executing.

Three things had to be true and only one was:
  1. The stop reduction must work whatever KIND of stop it is. On a Day-1 position the
     stop is an OTO bracket LEG and Alpaca rejects every qty change on one (42210000) —
     so the partial could never fire same-day. Fixed by the leg-safe path (#508).
  2. The circuit breaker must be escapable. It only closed on a SUCCESSFUL partial, and
     after the leg defect every partial failed — so the breaker opened by the bug also
     blocked the fix from proving itself. Deadlock. Fixed by an audited reset row.
  3. The trigger must not be time-gated. It never was (bar-high based, every 5 minutes).
"""
import ast
import pathlib

SRC = pathlib.Path("agents/market_intelligence/broker/order_manager.py").read_text()
TREE = ast.parse(SRC)


def _fn(name):
    return next(n for n in ast.walk(TREE)
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)


def test_the_breaker_can_be_closed_WITHOUT_a_successful_partial():
    """The deadlock. Before this, the ONLY close condition was partial_exit_committed —
    unreachable while the very defect that opened the breaker was blocking every partial."""
    src = ast.get_source_segment(SRC, _fn("_consecutive_partial_exit_failures"))
    assert "partial_exit_breaker_reset" in src
    assert "partial_exit_committed" in src, "a real success must still close it"


def test_the_reset_is_an_AUDIT_ROW_not_a_flag_or_a_deletion():
    """It must be visible after the fact and it must not erase the failures. A reset that
    deletes history is indistinguishable from the bug never happening."""
    src = ast.get_source_segment(SRC, _fn("_consecutive_partial_exit_failures"))
    assert "mi_audit_log" in src
    assert "DELETE" not in src.upper() and "UPDATE " not in src.upper()


def test_the_reset_only_moves_the_WINDOW_it_does_not_lower_the_threshold():
    """Failures AFTER a reset must count normally — otherwise one reset disarms the
    breaker permanently, which is the opposite of a safeguard."""
    src = ast.get_source_segment(SRC, _fn("_consecutive_partial_exit_failures"))
    assert "created_at > COALESCE(" in src
    assert "_PARTIAL_EXIT_BREAKER_THRESHOLD" not in src, "threshold stays at the caller"


def test_the_threshold_itself_is_unchanged():
    import agents.market_intelligence.broker.order_manager as om
    assert om._PARTIAL_EXIT_BREAKER_THRESHOLD == 3


def test_a_bracket_LEG_stop_no_longer_dead_ends_the_partial():
    """The Day-1 case. Every MAGNA53 entry's stop is an OTO leg on its entry day, and a
    qty replace on one is rejected — so 'same day' was structurally impossible."""
    src = ast.get_source_segment(SRC, _fn("execute_partial_exit"))
    assert "_reduce_stop_via_cancel_new" in src
    assert "_is_advanced_qty_rejection" in src, "the broker's own rejection must route, too"


def test_the_trigger_is_not_gated_on_hold_days():
    """'10 days later' must work identically to 'same day'. The trigger tests the in-hold
    bar HIGH against entry + R x risk — no calendar term anywhere."""
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    for calendarish in ("hold_days", "days_held", "alert_date >", "alert_date <"):
        assert calendarish not in src


def test_it_fires_once_per_trade_not_once_per_hold_day():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    assert "partial_taken" in src
