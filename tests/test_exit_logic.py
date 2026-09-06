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

from agents.market_intelligence.broker.exit_logic import (
    apply_daily_exit_step,
    ema,
    giveback_floor,
)


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


# ── apply_daily_exit_step opt-in params (#396 HTF Phase 4 — trail_mode / scale_fraction) ───


def test_unknown_trail_mode_raises():
    with pytest.raises(ValueError):
        apply_daily_exit_step(base_state(), bar(99, 101), date(2026, 4, 5), trail_mode="wma")


def test_ema_trail_mode_uses_ema_not_sma():
    # 20 closes: first 10 at 120, last 10 at 100 (mirrors test_sma_uses_max_of_10_and_20's
    # fixture) — but under EMA, the recency-weighted EMA10/EMA20 differ from the SMA10/20 in
    # the equal-weight test, proving the ema_10_20 branch is actually driving active_sma (not
    # silently falling back to SMA).
    closes = [120.0] * 10 + [100.0] * 10
    state = base_state(running_closes=closes, hard_stop=80.0,
                       alert_date=date(2026, 3, 1))
    step = apply_daily_exit_step(state, bar(105.0, 109.0), date(2026, 4, 5),
                                 trail_mode="ema_10_20")
    # SMA branch (existing test) computes active_sma == 109.45 exactly. The EMA branch must
    # differ (EMA lags less on the last 10 105-ish closes than an equal-weight SMA20 would).
    assert step.active_sma is not None
    assert step.active_sma != pytest.approx(109.45)


def test_ema_trail_mode_default_none_before_enough_data():
    # Only 5 running closes -> both ema(.,10) and ema(.,20) are None -> active_sma stays None,
    # mirroring the SMA branch's < 10-close behavior.
    state = base_state(running_closes=[100.0] * 4, hard_stop=80.0)
    step = apply_daily_exit_step(state, bar(101.0, 102.0), date(2026, 4, 5),
                                 trail_mode="ema_10_20")
    assert step.active_sma is None


def test_scale_fraction_none_preserves_exact_default_arithmetic():
    # scale_fraction=None (the default) must reproduce test_partial_integer_shares_for_live_path
    # EXACTLY — the byte-identical-default proof for the new param.
    state = base_state(remaining_shares=100, alert_date=date(2026, 4, 1),
                       running_closes=[105.0] * 3)
    step = apply_daily_exit_step(state, bar(106.0, 108.0), date(2026, 4, 5),
                                 integer_partial_shares=True, scale_fraction=None)
    assert step.partial_shares == 33
    assert step.new_remaining == 67


def test_scale_fraction_opt_in_variable_scale():
    # scale_fraction=0.40 (sourced 0.33-0.50 range) on remaining=100 -> 40 shares scaled out,
    # 60 remain — proves the opt-in branch is wired and DIFFERENT from the hardcoded 1/3.
    state = base_state(remaining_shares=100, alert_date=date(2026, 4, 1),
                       running_closes=[105.0] * 3)
    step = apply_daily_exit_step(state, bar(106.0, 108.0), date(2026, 4, 5),
                                 integer_partial_shares=True, scale_fraction=0.40)
    assert step.partial_shares == 40
    assert step.new_remaining == 60


# ── ADR 0023 Card 1 — peak-lock giveback floor (A3), DEFAULT-OFF ─────────────
# giveback_floor() helper: arm-boundary, floor math, guards, fail-loud config.


def test_giveback_off_when_floor_frac_none():
    # The default — no floor_frac → None, nothing computed (byte-identical guarantee).
    assert giveback_floor([120.0], 100.0) is None
    assert giveback_floor([120.0], 100.0, arm_gain=0.08) is None  # arm alone still off


def test_giveback_floor_math_gain_arm():
    # entry=100, peak=120, arm_gain=0.08 (arm_price=108, armed), floor_frac=0.50
    # → floor = 100 + 0.50*(120-100) = 110.0
    assert giveback_floor([110.0, 120.0, 118.0], 100.0,
                          arm_gain=0.08, floor_frac=0.50) == 110.0


def test_giveback_arm_boundary_is_inclusive():
    # Arming is >= (inclusive). Use exactly-representable arm prices so the boundary isn't
    # float noise: arm_r=2.0×risk 5 → 100+10 = 110.0 exact; arm_gain=0.25 → 125.0 exact.
    # (With real market prices peak==threshold never lands on a float edge; >= is right.)
    assert giveback_floor([110.0], 100.0, arm_r=2.0, risk_per_share=5.0,
                          floor_frac=0.50) == 105.0                      # peak == arm → armed
    assert giveback_floor([109.99], 100.0, arm_r=2.0, risk_per_share=5.0,
                          floor_frac=0.50) is None                        # just below → not
    assert giveback_floor([125.0], 100.0, arm_gain=0.25, floor_frac=0.50) == 112.5
    assert giveback_floor([124.99], 100.0, arm_gain=0.25, floor_frac=0.50) is None


def test_giveback_arm_r_uses_risk_per_share():
    # arm_r=2.0, risk/share=5 → arm_price = 100 + 2*5 = 110. peak=115 arms;
    # floor_frac=0.40 → floor = 100 + 0.40*(115-100) = 106.0. peak=109 stays disarmed.
    assert giveback_floor([115.0], 100.0, arm_r=2.0, risk_per_share=5.0,
                          floor_frac=0.40) == 106.0
    assert giveback_floor([109.0], 100.0, arm_r=2.0, risk_per_share=5.0,
                          floor_frac=0.40) is None


def test_giveback_floor_always_above_entry_when_armed():
    # By construction (arm needs peak>entry): the locked floor sits above entry.
    floor = giveback_floor([130.0], 100.0, arm_gain=0.06, floor_frac=0.40)
    assert floor is not None and floor > 100.0


def test_giveback_data_guards_return_none_not_raise():
    # Missing entry / empty closes = data gap, graceful None (NOT a config error).
    assert giveback_floor([120.0], None, arm_gain=0.08, floor_frac=0.5) is None
    assert giveback_floor([], 100.0, arm_gain=0.08, floor_frac=0.5) is None


def test_giveback_config_errors_fail_loud():
    # Inconsistent CONFIG raises (mirrors the trail_mode fail-loud guard).
    with pytest.raises(ValueError):  # neither arm
        giveback_floor([120.0], 100.0, floor_frac=0.5)
    with pytest.raises(ValueError):  # both arms
        giveback_floor([120.0], 100.0, arm_gain=0.08, arm_r=2.0,
                       risk_per_share=5.0, floor_frac=0.5)
    with pytest.raises(ValueError):  # arm_r without risk_per_share
        giveback_floor([120.0], 100.0, arm_r=2.0, floor_frac=0.5)
    with pytest.raises(ValueError):  # floor_frac out of (0, 1]
        giveback_floor([120.0], 100.0, arm_gain=0.08, floor_frac=0.0)
    with pytest.raises(ValueError):  # floor_frac > 1
        giveback_floor([120.0], 100.0, arm_gain=0.08, floor_frac=1.5)
    with pytest.raises(ValueError):  # non-positive arm_gain
        giveback_floor([120.0], 100.0, arm_gain=0.0, floor_frac=0.5)


# ── ADR 0023 Card 1 — giveback wired into apply_daily_exit_step (step 4b) ─────


def test_giveback_default_off_byte_identical():
    # Passing all giveback params as None must reproduce the baseline (no-giveback) call
    # EXACTLY — the default-off proof at the integration layer.
    st1 = base_state(running_closes=[100.0] * 10)
    st2 = base_state(running_closes=[100.0] * 10)
    baseline = apply_daily_exit_step(st1, bar(101.0, 102.0), date(2026, 4, 3))
    withnone = apply_daily_exit_step(
        st2, bar(101.0, 102.0), date(2026, 4, 3),
        giveback_arm_gain=None, giveback_arm_r=None,
        giveback_floor_frac=None, giveback_risk_per_share=None,
    )
    assert withnone.effective_stop == baseline.effective_stop
    assert withnone.action == baseline.action
    assert withnone.new_remaining == baseline.new_remaining


def test_giveback_raises_effective_stop_and_locks_the_round_tripper():
    # Prior peak 120 (running_closes carries it), today gives back to 108. Armed at +8%,
    # floor_frac=0.50 → floor = 110. effective_stop=max(hard_stop 95, 110)=110 > close 108
    # → the lock FIRES (the SMCI/PURR round-trip class), closing at the bar_close.
    state = base_state(running_closes=[120.0])  # <10 closes → active_sma None
    step = apply_daily_exit_step(
        state, bar(107.0, 108.0), date(2026, 4, 3),  # hold_days=2 → no partial branch
        giveback_arm_gain=0.08, giveback_floor_frac=0.50,
    )
    assert step.closed is True
    assert step.effective_stop == 110.0
    assert step.close_price == 108.0


def test_giveback_stays_open_when_close_above_floor():
    # Same peak/arm but today's close (118) is still above the 109 floor → position holds.
    state = base_state(running_closes=[110.0])
    step = apply_daily_exit_step(
        state, bar(116.0, 118.0), date(2026, 4, 3),  # hold_days=2 → no partial branch
        giveback_arm_gain=0.08, giveback_floor_frac=0.50,
    )
    assert step.closed is False
    assert step.effective_stop == 109.0  # 100 + 0.50*(118-100)


def test_giveback_never_lowers_effective_stop():
    # hard_stop (106) already sits ABOVE the giveback floor (104) → effective_stop stays 106.
    # The floor is a max() input; it can only raise. Compare with/without giveback.
    st_with = base_state(hard_stop=106.0, running_closes=[110.0])
    st_without = base_state(hard_stop=106.0, running_closes=[110.0])
    with_gb = apply_daily_exit_step(
        st_with, bar(107.0, 108.0), date(2026, 4, 3),  # hold_days=2 → no partial branch
        giveback_arm_gain=0.05, giveback_floor_frac=0.40,  # floor = 104
    )
    without_gb = apply_daily_exit_step(st_without, bar(107.0, 108.0), date(2026, 4, 3))
    assert with_gb.effective_stop == 106.0
    assert with_gb.effective_stop == without_gb.effective_stop


# ── ADR 0023 Card 2 — sma_10_20_handoff trail mode (Axis B), OPT-IN ──────────
# SMA10 until partial_taken, then SMA20. (running_closes length is a synthetic
# trail input, independent of hold_days here — we isolate the indicator branch.)


def test_handoff_post_partial_uses_sma20_not_max():
    # 20 closes: last-10 mean = 120 (sma10), full-20 mean = 110 (sma20). partial already
    # taken → handoff trails SMA20 (110), NOT the max(sma10,sma20)=120 that 'sma' would use.
    state = base_state(partial_taken=True, breakeven_active=False,
                       running_closes=[100.0] * 10 + [120.0] * 9)
    step = apply_daily_exit_step(state, bar(119.0, 120.0), date(2026, 5, 1),
                                 trail_mode="sma_10_20_handoff")
    assert step.active_sma == 110.0            # SMA20
    # 'sma' mode on the same state would pick max = 120.0 → different indicator.
    sma_step = apply_daily_exit_step(
        base_state(partial_taken=True, running_closes=[100.0] * 10 + [120.0] * 9),
        bar(119.0, 120.0), date(2026, 5, 1), trail_mode="sma")
    assert sma_step.active_sma == 120.0


def test_handoff_pre_partial_uses_sma10_not_max():
    # Downtrend: last-10 mean = 100 (sma10), full-20 mean = 110 (sma20). NOT yet partialed →
    # handoff trails SMA10 (100); 'sma' would trail max = SMA20 (110) and close the bar.
    state = base_state(partial_taken=False, running_closes=[120.0] * 10 + [100.0] * 9)
    step = apply_daily_exit_step(state, bar(100.0, 100.0), date(2026, 4, 3),  # hold_days=2
                                 trail_mode="sma_10_20_handoff")
    assert step.active_sma == 100.0            # SMA10
    assert step.closed is False               # 100 is not < effective_stop 100


def test_handoff_post_partial_falls_back_to_sma10_before_20_closes():
    # Post-partial but only 10 closes → SMA20 undefined; handoff keeps a trail via SMA10
    # (never drops protection) rather than going None.
    state = base_state(partial_taken=True, breakeven_active=False,
                       running_closes=[100.0] * 9)
    step = apply_daily_exit_step(state, bar(99.0, 100.0), date(2026, 5, 1),
                                 trail_mode="sma_10_20_handoff")
    assert step.active_sma == 100.0           # SMA10 fallback, not None


def test_handoff_is_a_valid_trail_mode():
    # Sanity: the new mode is accepted (doesn't hit the fail-loud ValueError guard).
    step = apply_daily_exit_step(base_state(running_closes=[100.0] * 5),
                                 bar(99.0, 101.0), date(2026, 4, 3),
                                 trail_mode="sma_10_20_handoff")
    assert step.action in ("updated", "partial_only")


# ── 2026-09-06 (#545 trail sweep, OPT-IN): single-MA and no-trail modes ──────
# Operator: "make sense to look into the sma stops too?" These modes are evidence-only —
# no live caller passes them — but they are LIVE-FILE code, so each branch is pinned here.


def test_trail_mode_none_leaves_only_the_hard_stop():
    """MUTATION TARGET: a 'none' that silently fell through to the max(SMA10,SMA20) default
    would make the control arm identical to the live arm, and 'the trail earns its keep'
    unfalsifiable. 20 prior closes at 120 put both SMAs above the 101 close, so the live
    trail exits on this bar and the control must not. skip_partial_decision keeps the day-3/5
    ladder partial (and the breakeven it arms) out of the comparison."""
    prior = [120.0] * 20
    kw = dict(prior_closes=prior, skip_partial_decision=True)
    step = apply_daily_exit_step(base_state(), bar(99, 101), date(2026, 4, 20),
                                 trail_mode="none", **kw)
    assert step.active_sma is None
    assert step.effective_stop == pytest.approx(95.0)      # the hard stop alone
    assert step.stop_source == "hard_stop" and not step.closed
    live = apply_daily_exit_step(base_state(), bar(99, 101), date(2026, 4, 20),
                                 trail_mode="sma", **kw)
    assert live.closed and live.close_reason == "sma_trail_stop"   # the arms really differ


def test_single_ma_trail_modes_use_one_average_not_the_max_of_two():
    """MUTATION TARGET: the live 'sma' mode takes max(SMA10, SMA20), which is the TIGHTER
    line — when a stock rolls over, SMA20 sits ABOVE SMA10 and that max() hands the position
    a stop above recent price. A single-MA mode must track ITS OWN window only."""
    prior = [100.0 + i for i in range(30)]          # rising, so SMA10 > SMA20
    closes = prior + [151.0]                        # today's close joins running_closes
    got = {tm: apply_daily_exit_step(base_state(), bar(150, 151), date(2026, 4, 20),
                                     trail_mode=tm, prior_closes=prior,
                                     skip_partial_decision=True).active_sma
           for tm in ("sma", "sma10", "sma20", "sma50", "none")}
    assert got["sma10"] == pytest.approx(sum(closes[-10:]) / 10)
    assert got["sma20"] == pytest.approx(sum(closes[-20:]) / 20)
    assert got["sma10"] > got["sma20"]
    assert got["sma"] == pytest.approx(got["sma10"])   # the live max() picks the higher line
    assert got["sma50"] is None                        # only 31 closes — no 50-day line yet
    assert got["none"] is None


def test_unknown_trail_mode_still_fails_loud():
    with pytest.raises(ValueError, match="unknown trail_mode"):
        apply_daily_exit_step(base_state(), bar(99, 101), date(2026, 4, 5),
                              trail_mode="sma100")
