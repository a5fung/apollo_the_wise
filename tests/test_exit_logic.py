"""Unit tests for the pure exit-step decision function.

Asserts every branch of broker/exit_logic.py produces the exact arithmetic
both call sites (backtester/tracker.py and broker/live_tracker.py) used to
compute inline. Run with: python -m pytest tests/test_exit_logic.py -v
"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step, ema


def base_state(**overrides):
    state = {
        "alert_date": date(2026, 4, 1),
        "remaining_shares": 90,
        "entry_price": 100.0,
        "hard_stop": 95.0,
        "partial_taken": False,
        "breakeven_active": False,
        "exits": [],
        "running_closes": [],
    }
    state.update(overrides)
    return state


def bar(low, close):
    return {"l": low, "c": close, "h": max(low, close), "o": close}


# ── Pre-alert and no-data skips ──────────────────────────────────────────────


def test_skip_pre_alert_when_today_equals_alert_date():
    step = apply_daily_exit_step(base_state(), bar(99, 101), date(2026, 4, 1))
    assert step.action == "skip_pre_alert"
    assert step.new_remaining == 90


def test_skip_when_remaining_zero():
    state = base_state(remaining_shares=0)
    step = apply_daily_exit_step(state, bar(99, 101), date(2026, 4, 5))
    assert step.action == "skip_pre_alert"


def test_no_data_when_bar_none():
    step = apply_daily_exit_step(base_state(), None, date(2026, 4, 5))
    assert step.action == "no_data"
    assert not step.closed


# ── Hard-stop branch ─────────────────────────────────────────────────────────


def test_hard_stop_fires_when_bar_low_breaches():
    step = apply_daily_exit_step(base_state(), bar(94.0, 96.0), date(2026, 4, 5))
    assert step.action == "stopped_out"
    assert step.closed
    assert step.close_reason == "stop_hit"
    assert step.close_price == 95.0
    assert step.close_shares == 90
    assert step.close_pnl == pytest.approx((95.0 - 100.0) * 90)
    assert step.new_remaining == 0
    assert step.new_running_closes == [96.0]
    assert len(step.new_exits) == 1
    assert step.new_exits[0]["reason"] == "stop_hit"


def test_hard_stop_skip_close_flag_falls_through_with_floor_preserved():
    # bar_low touches hard_stop; with skip_hard_stop_close, function should
    # NOT close, but effective_stop should still floor at hard_stop.
    # Use day 2 (no partial branch) to isolate hard_stop floor.
    state = base_state(alert_date=date(2026, 4, 3))  # today=4/5 → day 2
    step = apply_daily_exit_step(
        state, bar(94.0, 105.0), date(2026, 4, 5),
        skip_hard_stop_close=True,
    )
    assert not step.closed
    assert step.effective_stop == 95.0  # hard_stop floor preserved


# ── SMA trail close ──────────────────────────────────────────────────────────


def test_sma_trail_close_with_10sma_only():
    # 10 closes building toward 100 average; today's close drops below floor
    closes = [100.0] * 10
    state = base_state(running_closes=closes, hard_stop=80.0)
    step = apply_daily_exit_step(state, bar(95.0, 95.0), date(2026, 4, 18))
    # 10sma over [100*10, 95] last 10 = (100*9 + 95)/10 = 99.5
    # bar_close 95 < 99.5 → SMA trail
    assert step.action == "sma_stopped"
    assert step.close_reason == "sma_trail_stop"
    assert step.close_price == 95.0


def test_sma_uses_max_of_10_and_20_when_history_sufficient():
    # 20 closes; latest 10 average lower than latest 20 → uses 20-sma
    closes = [120.0] * 10 + [100.0] * 10
    state = base_state(running_closes=closes, hard_stop=80.0,
                       alert_date=date(2026, 3, 1))
    step = apply_daily_exit_step(state, bar(105.0, 109.0), date(2026, 4, 5))
    # After append, running_closes len=21. Last 10 = [100*9, 109], avg=100.9.
    # Last 20 = positions 1..20 = [120*9, 100*10, 109], avg = (1080+1000+109)/20 = 109.45.
    # active_sma = max = 109.45; bar_close 109 < 109.45 → close.
    assert step.action == "sma_stopped"
    assert step.active_sma == pytest.approx(109.45)


# ── Partial profit Day 3-5 ───────────────────────────────────────────────────


def test_partial_fires_on_day_4_when_close_above_entry():
    state = base_state(alert_date=date(2026, 4, 1),
                       running_closes=[105.0, 106.0, 107.0])
    step = apply_daily_exit_step(state, bar(106.0, 108.0),
                                 date(2026, 4, 5))  # hold_days = 4
    assert step.partial_fired
    assert step.partial_shares == pytest.approx(30.0)  # 90/3 fractional
    assert step.new_partial_taken
    assert step.new_breakeven_active
    assert step.new_remaining == pytest.approx(60.0)


def test_partial_does_not_fire_day_4_when_close_below_entry():
    state = base_state(alert_date=date(2026, 4, 1),
                       running_closes=[105.0, 106.0, 107.0])
    step = apply_daily_exit_step(state, bar(95.5, 99.0),
                                 date(2026, 4, 5))
    assert not step.partial_fired
    assert step.action == "updated"


def test_partial_forced_on_day_5_even_if_close_below_entry():
    state = base_state(alert_date=date(2026, 4, 1),
                       running_closes=[105.0] * 4, hard_stop=80.0)
    step = apply_daily_exit_step(state, bar(95.5, 96.0),
                                 date(2026, 4, 6))  # hold_days = 5
    assert step.partial_fired


def test_partial_integer_shares_for_live_path():
    state = base_state(remaining_shares=100, alert_date=date(2026, 4, 1),
                       running_closes=[105.0] * 3)
    step = apply_daily_exit_step(state, bar(106.0, 108.0),
                                 date(2026, 4, 5),
                                 integer_partial_shares=True)
    assert step.partial_shares == 33  # int(100)//3
    assert step.new_remaining == 67


def test_skip_partial_decision_bypasses_branch():
    state = base_state(alert_date=date(2026, 4, 1),
                       running_closes=[105.0] * 3)
    step = apply_daily_exit_step(state, bar(106.0, 108.0),
                                 date(2026, 4, 5),
                                 skip_partial_decision=True)
    assert not step.partial_fired
    assert not step.new_partial_taken
    assert step.new_remaining == 90


def test_partial_then_sma_close_same_day():
    # Day 5, partial forced; effective_stop becomes max(hard_stop=80,
    # sma=105ish, breakeven=100); bar_close below entry → SMA close.
    state = base_state(alert_date=date(2026, 4, 1),
                       running_closes=[105.0] * 4, hard_stop=80.0)
    step = apply_daily_exit_step(state, bar(96.0, 99.0),
                                 date(2026, 4, 6))  # hold_days=5
    assert step.partial_fired
    assert step.action == "sma_stopped"
    # Two exit rows: partial_profit + sma_trail_stop
    reasons = [e["reason"] for e in step.new_exits]
    assert "partial_profit" in reasons
    assert "sma_trail_stop" in reasons


# ── Breakeven floor ──────────────────────────────────────────────────────────


def test_breakeven_active_floors_effective_stop_at_entry():
    state = base_state(breakeven_active=True, hard_stop=80.0,
                       running_closes=[100.0] * 10)
    step = apply_daily_exit_step(state, bar(99.0, 99.5),
                                 date(2026, 4, 5))
    # hard_stop=80, sma~99.95, entry_price=100 → effective=100
    # bar_close 99.5 < 100 → SMA trail close
    assert step.action == "sma_stopped"
    assert step.effective_stop == 100.0


# ── Still-open update ────────────────────────────────────────────────────────


def test_still_open_updates_running_closes_and_effective_stop():
    # Day 2 — no partial branch. bar_close > effective_stop → still open.
    state = base_state(alert_date=date(2026, 4, 3),  # today=4/5 → day 2
                       running_closes=[100.0] * 10)
    step = apply_daily_exit_step(state, bar(101.0, 102.0),
                                 date(2026, 4, 5))
    assert step.action == "updated"
    assert not step.closed
    assert 102.0 in step.new_running_closes
    assert step.new_remaining == 90
    # No partial, no breakeven; effective_stop = max(95, sma~100.2) ≈ 100.2
    assert step.effective_stop > 95.0


def test_state_input_not_mutated():
    state = base_state(running_closes=[100.0])
    snapshot_running = list(state["running_closes"])
    snapshot_exits = list(state["exits"])
    apply_daily_exit_step(state, bar(101.0, 102.0), date(2026, 4, 5))
    assert state["running_closes"] == snapshot_running
    assert state["exits"] == snapshot_exits


# ── ema() helper (#396 HTF Phase 4 — the EMA-trail input) ───────────────────


def test_ema_hand_computed_seed_then_one_recursive_step():
    # window=3, closes=[1,2,3,4,5]. seed = avg(1,2,3) = 2.0; multiplier = 2/(3+1) = 0.5.
    # step c=4: value = (4-2)*0.5 + 2 = 3.0
    # step c=5: value = (5-3)*0.5 + 3 = 4.0
    assert ema([1.0, 2.0, 3.0, 4.0, 5.0], 3) == pytest.approx(4.0)


def test_ema_exactly_window_length_equals_seed_sma():
    # No values past the seed window -> ema == the plain SMA of those `window` closes.
    closes = [10.0] * 10
    assert ema(closes, 10) == pytest.approx(10.0)


def test_ema_hand_computed_one_step_past_seed():
    # seed = avg([10]*10) = 10.0; multiplier = 2/11; one more close of 20.
    # value = (20-10)*(2/11) + 10 = 11.818181818181818
    closes = [10.0] * 10 + [20.0]
    assert ema(closes, 10) == pytest.approx(11.818181818181818)


def test_ema_none_when_insufficient_data():
    assert ema([1.0, 2.0, 3.0], 5) is None
    assert ema([], 1) is None
