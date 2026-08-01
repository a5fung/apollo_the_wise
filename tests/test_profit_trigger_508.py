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


def test_time_gate_stands_down_when_the_trigger_is_on():
    """Exactly one owner per decision. With PROFIT_TRIGGER_R set, the 3:45 time gate
    must not also take a partial — and with it None, the old rule must still run."""
    src = pathlib.Path("agents/market_intelligence/broker/live_tracker.py").read_text()
    i = src.index("async def run_partial_exits")
    seg = src[i:i + 9000]
    assert "skip_partial_decision=bool(PROFIT_TRIGGER_R)" in seg, (
        "the 3:45 job must stand down when the intraday trigger owns the partial")


def test_exit_logic_stays_pure_no_config_dependency():
    """exit_logic is the shared decision SSoT for live, paper and shadow. A config
    import there would make the same inputs produce different outputs per process."""
    src = pathlib.Path("agents/market_intelligence/broker/exit_logic.py").read_text()
    assert "PROFIT_TRIGGER_R" not in src, "keep the flag at the caller, not in pure logic"


def test_skip_flag_genuinely_suppresses_the_day5_branch():
    """BEHAVIOURAL, not a string match. Day 5 and underwater is the exact case the
    old rule fires on unconditionally — the one the operator ruled out. Prove the
    flag governs it in both directions, so 'stands down' is a fact not a comment."""
    from datetime import date
    from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step
    state = {"alert_date": date(2026, 7, 20), "remaining_shares": 300, "entry_price": 100.0,
             "hard_stop": 95.0, "partial_taken": False, "breakeven_active": False,
             "exits": [], "running_closes": [99.0] * 12}
    bar = {"close": 98.0, "high": 99.0, "low": 97.0}          # underwater
    day = date(2026, 7, 25)                                    # calendar day 5
    on = apply_daily_exit_step(state, bar, day, integer_partial_shares=True,
                               skip_hard_stop_close=True, skip_partial_decision=True)
    off = apply_daily_exit_step(state, bar, day, integer_partial_shares=True,
                                skip_hard_stop_close=True, skip_partial_decision=False)
    assert off.partial_fired is True, "day-5 unconditional branch should fire when NOT skipped"
    assert on.partial_fired is False, "trigger ON must suppress the time gate entirely"
