"""#445 — the canonical replay driver pins (characterization vs the old copy-paste loop).

The reference loop below IS the pattern that was copy-pasted 4× (giveback_shadow /
_306_harvest_sweep / _htf_management_replay / orb_extension settle). The driver must be
byte-identical to it in carried state, yielded steps, and stop-after-close semantics,
across plain / trail+scale / giveback kwargs.
"""
from datetime import date, timedelta

from agents.market_intelligence.broker.exit_logic import (
    apply_daily_exit_step, iter_exit_ladder, seed_exit_state,
)

ALERT = date(2026, 6, 1)


def _bars(closes, lows=None):
    lows = lows or closes
    return [(ALERT + timedelta(days=i + 1), {"l": lows[i], "c": closes[i]})
            for i in range(len(closes))]


def _reference(seed, bars, **kw):
    """The OLD pattern, verbatim shape (state.update carry + break on closed)."""
    state = dict(seed, exits=list(seed["exits"]), running_closes=list(seed["running_closes"]))
    steps = []
    for i, (day, bar) in enumerate(bars):
        step = apply_daily_exit_step(state, bar, day, integer_partial_shares=True, **kw)
        state.update(remaining_shares=step.new_remaining, partial_taken=step.new_partial_taken,
                     breakeven_active=step.new_breakeven_active,
                     exits=step.new_exits, running_closes=step.new_running_closes)
        steps.append((i, day, step))
        if step.closed:
            break
    return state, steps


def _driver(seed, bars, **kw):
    state = dict(seed, exits=list(seed["exits"]), running_closes=list(seed["running_closes"]))
    steps = list(iter_exit_ladder(state, bars, **kw))
    return state, steps


def _assert_identical(seed, bars, **kw):
    ref_state, ref_steps = _reference(seed, bars, **kw)
    drv_state, drv_steps = _driver(seed, bars, **kw)
    assert drv_state == ref_state
    assert len(drv_steps) == len(ref_steps)
    for (ri, rd, rs), (di, dd, ds) in zip(ref_steps, drv_steps):
        assert (ri, rd) == (di, dd)
        assert rs == ds  # NamedTuple equality = every field byte-identical


SEED = dict(alert_date=ALERT, entry_price=10.0, hard_stop=9.0, remaining_shares=100,
            partial_taken=False, breakeven_active=False, exits=[], running_closes=[])


def test_plain_run_to_end_identical():
    _assert_identical(SEED, _bars([10.2, 10.5, 10.8, 11.0, 11.2, 11.5, 11.8, 12.0]))


def test_hard_stop_close_identical_and_stops_after_close():
    bars = _bars([10.2, 8.5, 12.0, 13.0], lows=[10.0, 8.4, 11.0, 12.0])
    ref_state, ref_steps = _reference(SEED, bars)
    drv_state, drv_steps = _driver(SEED, bars)
    assert drv_state == ref_state
    assert drv_steps[-1][2].closed
    assert len(drv_steps) == len(ref_steps) < len(bars)  # halted at the close, not the end


def test_trail_and_scale_kwargs_identical():
    closes = [10.2, 10.6, 11.0, 11.4, 11.8, 11.5, 11.2, 10.9, 10.6, 10.2, 9.9, 9.6]
    _assert_identical(SEED, _bars(closes), trail_mode="ema_10_20", scale_fraction=0.4)


def test_giveback_kwargs_identical():
    closes = [10.4, 10.9, 11.5, 12.0, 11.0, 10.4, 10.1]
    _assert_identical(SEED, _bars(closes), giveback_arm_gain=0.06, giveback_floor_frac=0.60)


def test_seed_exit_state_shape_and_resume():
    s = seed_exit_state(alert_date=ALERT, entry_price=10.0, hard_stop=9.0, remaining_shares=100)
    assert set(s) == {"alert_date", "entry_price", "hard_stop", "remaining_shares",
                      "partial_taken", "breakeven_active", "exits", "running_closes"}
    # persisted-state resume: mutable fields pass through, lists are copied
    prior_exits = [{"reason": "partial", "pnl": 5.0}]
    s2 = seed_exit_state(alert_date=ALERT, entry_price=10.0, hard_stop=9.0,
                         remaining_shares=60, partial_taken=True,
                         breakeven_active=True, exits=prior_exits, running_closes=[10.5])
    assert s2["exits"] == prior_exits and s2["exits"] is not prior_exits
    assert s2["partial_taken"] is True and s2["remaining_shares"] == 60


def test_driver_mutates_caller_state_in_place():
    state = seed_exit_state(alert_date=ALERT, entry_price=10.0, hard_stop=9.0,
                            remaining_shares=100)
    list(iter_exit_ladder(state, _bars([10.5, 11.0, 11.5])))
    assert state["running_closes"] == [10.5, 11.0, 11.5]  # the persisted-state contract
