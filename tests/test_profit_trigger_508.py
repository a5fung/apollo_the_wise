"""#508 — intraday profit trigger (operator-signed 2026-08-01).

Pins the properties that make this safe to run on live money:
  1. OFF by default. The shipped constant is None; the trigger is inert until the
     operator sets it. Reversion for this change is that constant, not a revert.
  2. It does NOT live inside track_open_position_extremes. That recorder is
     name-registered in the column-write authority gate; folding a money action
     into it would trip Gate 5 G and blur a pure recorder (the #500 class).
  3. It reuses execute_partial_exit — which reduces the stop BEFORE selling — so
     there is never a window where the stop over-covers the position.
  4. Detection is BAR-based (in-hold high), not spot, so a spike between 5-minute
     polls is still caught.
  5. A notification failure can never abort the sell.
"""
import ast
import pathlib

SRC = pathlib.Path("agents/market_intelligence/broker/order_manager.py").read_text()
TREE = ast.parse(SRC)


def _fn(name):
    return next(n for n in ast.walk(TREE)
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)


def test_trigger_is_OFF_by_default():
    from agents.market_intelligence import constants
    assert constants.PROFIT_TRIGGER_R in (None, 0), (
        "shipped default must be OFF — this constant IS the reversion path")


def test_trigger_returns_immediately_when_off():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    head = src[:src.index("pool = await get_pool()")]
    assert "if not PROFIT_TRIGGER_R" in head and "return []" in head, (
        "the off-switch must short-circuit BEFORE any DB or broker work")


def test_money_action_is_NOT_inside_the_recorder():
    """Gate 5 G / #500 class: the recorder owns highest/lowest_price_seen by name."""
    rec = ast.get_source_segment(SRC, _fn("track_open_position_extremes"))
    assert "execute_partial_exit" not in rec, (
        "a partial inside the name-registered recorder would trip the column-write gate")


def test_it_reuses_execute_partial_exit_not_a_raw_sell():
    """execute_partial_exit reduces the stop FIRST under an advisory lock. Any
    bespoke sell here would re-introduce the unprotected window the design avoids."""
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    assert "await execute_partial_exit(" in src
    for forbidden in ("place_market_sell", "submit_order", "close_position"):
        assert forbidden not in src, f"{forbidden} bypasses the stop-first sequence"


def test_detection_uses_the_bar_HIGH_not_a_spot_price():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    assert "MAX(high)" in src, "spot sampling would miss a spike between 5-minute polls"
    assert "bar_time >= $2" in src, "must scan only IN-HOLD bars"


def test_notify_failure_cannot_abort_the_sell():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    notify = src.index("send_telegram_message")
    sell = src.index("await execute_partial_exit(")
    assert notify < sell, "operator is told before the money moves"
    assert "except Exception" in src[notify:sell], "a notify failure must not abort the sell"


def test_it_never_fires_twice_on_one_trade():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    assert "partial_taken" in src and "FALSE" in src, (
        "must exclude trades whose partial already fired — the 3:45 job may also act")
