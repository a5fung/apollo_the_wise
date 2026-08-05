"""The +2R partial deadlocked on live money, and told the operator it was safe (2026-08-05).

PLTR 307, the first real fire of the trigger. Two distinct defects, one sequence:

  09:30:00  partial_exit_started        sell 2 of 6
  09:30:00  partial_exit_stop_replaced  stop reduced 6 -> 4 @ $143.28   <- SUCCEEDED
  09:30:03  partial_exit_aborted        "shares not free (qty_available=0.0 < 2)"
  09:35:00  replace attempt 1 failed    42210000 "order parameters are not changed"
  09:35:01  replace attempt 2 failed    same
  09:35:01  replacement stop failed     -> abort, stage=place_new_stop (BREAKER-COUNTED)

DEFECT 1 — the abort said the wrong thing and left a real gap. Its premise was "shares still
held ⇒ the OLD full-size stop is still resting ⇒ over-covered ⇒ safe". That is one of two
worlds with an identical symptom. Here the NEW 4-share stop was already confirmed live on a
6-share position, so the same reading meant UNDER-covered — and the Telegram said "position
protected" while 2 shares had no stop behind them. Nothing repairs that until the 16:05 sync.

DEFECT 2 — a DEADLOCK. Every later retry tried to reduce a stop that was already reduced.
Alpaca correctly rejects a no-op replace, so the partial could never get past a step it had
already completed, and each attempt logged a `place_new_stop` abort, which the circuit breaker
COUNTS. Three of those and the trigger would have been shut off permanently.

The shared root: both branches DEDUCED broker state instead of reading it.
"""
import ast
import pathlib

SRC = pathlib.Path("agents/market_intelligence/broker/order_manager.py").read_text()
TREE = ast.parse(SRC)


def _fn(name):
    return next(n for n in ast.walk(TREE)
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)


# ── Defect 2: the deadlock ────────────────────────────────────────────────────

def test_a_noop_replace_rejection_is_recognised_as_ALREADY_DONE():
    from agents.market_intelligence.broker.order_manager import _is_stop_already_at_target
    assert _is_stop_already_at_target(
        Exception('{"code":42210000,"message":"order parameters are not changed"}'))


def test_it_does_NOT_swallow_the_advanced_order_leg_rejection():
    """Same 42210000 code, different meaning. Conflating them would make a real leg rejection
    look like success and skip the leg-safe path entirely."""
    from agents.market_intelligence.broker.order_manager import (
        _is_stop_already_at_target, _is_advanced_qty_rejection)
    leg = Exception('{"code":42210000,"message":"qty cannot be changed for advanced orders"}')
    assert not _is_stop_already_at_target(leg)
    assert _is_advanced_qty_rejection(leg)


def test_it_does_not_match_unrelated_broker_errors():
    from agents.market_intelligence.broker.order_manager import _is_stop_already_at_target
    for other in ("insufficient qty available", "order not found", "connection reset"):
        assert not _is_stop_already_at_target(Exception(other))


def test_the_already_reduced_stop_is_ADOPTED_from_the_broker_not_assumed():
    """It must re-read open orders and confirm the live stop really is at target. Assuming it
    is what the error implies would be the same deduce-instead-of-read mistake."""
    src = ast.get_source_segment(SRC, _fn("execute_partial_exit"))
    i = src.index("_is_stop_already_at_target")
    block = src[i:i + 1800]
    assert "get_open_orders" in block, "must re-read the broker"
    assert "_live_sell_stops" in block, "must use the shared live-stop definition"
    assert "new_remaining" in block, "must confirm the live qty equals the target"
    assert "new_stop_order = _cur[0]" in block, "adopt the real order, not a fabricated one"


def test_a_mismatch_ABORTS_rather_than_guessing():
    src = ast.get_source_segment(SRC, _fn("execute_partial_exit"))
    i = src.index("_is_stop_already_at_target")
    assert "aborting rather than guessing" in src[i:i + 2400]


# ── Defect 1: the abort that claimed safety it had not established ────────────

def test_the_abort_READS_broker_coverage_instead_of_inferring_it():
    src = ast.get_source_segment(SRC, _fn("execute_partial_exit"))
    i = src.index("verify_shares_free")
    block = src[max(0, i - 2600):i + 2600]
    assert "fully_covered" in block
    assert "_live_sell_stops" in block, "coverage is a broker fact, not a deduction"


def test_unreadable_broker_counts_as_UNDER_covered():
    """The failure being fixed was assuming safety without establishing it. An unreadable
    broker must therefore re-protect, never walk away."""
    src = ast.get_source_segment(SRC, _fn("execute_partial_exit"))
    i = src.index("assuming UNDER-covered")
    assert i > 0
    j = src.index("fully_covered = (")
    assert "covered is not None and _pos_qty is not None" in src[j:j + 260]


def test_the_under_covered_branch_does_NOT_claim_the_position_is_protected():
    """The original Telegram said 'position protected' while 2 of 6 shares were naked."""
    src = ast.get_source_segment(SRC, _fn("execute_partial_exit"))
    i = src.index("RE-PROTECTING to full size now")
    block = src[max(0, i - 900):i + 200]
    assert "position protected" not in block


def test_the_under_covered_branch_FALLS_THROUGH_and_never_returns_early():
    """`abort_reprotect` is consumed AFTER the advisory lock releases. Returning inside the
    lock would skip the re-protect and make the whole fix inert — which is the exact shape of
    the bug it repairs, so it is pinned."""
    src = ast.get_source_segment(SRC, _fn("execute_partial_exit"))
    i = src.index("RE-PROTECTING to full size now")
    tail = src[i:i + 900]
    assert "abort_reprotect = True" in tail
    before_flag = tail[:tail.index("abort_reprotect = True")]
    assert "return False" not in before_flag, "must not return before setting the flag"


def test_the_fully_covered_branch_still_aborts_cleanly():
    """When the stop genuinely still covers the whole position, walking away IS correct — the
    fix must not turn every abort into an order-placing path."""
    src = ast.get_source_segment(SRC, _fn("execute_partial_exit"))
    i = src.index("if fully_covered:")
    assert "return False" in src[i:i + 700]
