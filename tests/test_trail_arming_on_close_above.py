"""2026-10-28 (operator, on live CLS): the trailing line governs only after the stock has CLOSED AT OR
ABOVE it on a held day — `apply_daily_exit_step(trail_arm_on_close_above=True)`, passed by the live
tracker's three calls. A trade entered BELOW its 10/20-day line (CLS: filled $272.01 under a $330.52
line on 2026-10-27) was "stopped" by the line on its first close; a trailing stop is a line under the
price. Default False is byte-identical (every non-live caller)."""
from datetime import date

import pytest

from agents.market_intelligence.broker.exit_logic import (
    _sma_10_20_line,
    _trail_armed_before_today,
    apply_daily_exit_step,
)

ALERT = date(2026, 10, 27)


def _state(running_closes, *, entry=272.005, hard=250.26, be=True, prior=None):
    return {
        "alert_date": ALERT, "remaining_shares": 2.0, "entry_price": entry, "hard_stop": hard,
        "partial_taken": False, "breakeven_active": be, "exits": [], "running_closes": list(running_closes),
        "prior_closes": prior,
    }


# the stock's history before entry: ran to ~350, then fell to ~265 (both averages far above the entry)
PRIOR = [340.0, 345.0, 350.0, 348.0, 352.0, 349.0, 344.0, 338.0, 335.0, 330.0,
         326.0, 320.0, 315.0, 309.0, 302.0, 296.0, 289.0, 281.0, 274.0, 266.0]


def _step(state, close, low, today, **kw):
    return apply_daily_exit_step(state, {"l": low, "c": close}, today, integer_partial_shares=True,
                                 skip_partial_decision=True, prior_closes=state["prior_closes"], **kw)


def test_cls_shape_day_one_below_the_line_is_not_a_trail_exit_when_arming_is_on():
    st = _state([], prior=PRIOR)
    line = _sma_10_20_line(PRIOR + [299.8])
    assert line is not None and line > 299.8                                   # the line sits above the price
    old = _step(st, 299.8, 286.0, date(2026, 10, 28))
    assert old.action == "sma_stopped"                                          # the behaviour he flagged
    new = _step(st, 299.8, 286.0, date(2026, 10, 28), trail_arm_on_close_above=True)
    assert new.action != "sma_stopped" and new.new_remaining == 2.0
    assert new.effective_stop == pytest.approx(272.005)                        # breakeven governs, not the line


def test_the_line_governs_once_a_held_day_closed_above_it():
    rising = [100.0 + i for i in range(20)]                                    # a stock above its averages
    held = [121.0, 125.0]                                                      # day 1 closes above its line
    assert _trail_armed_before_today(rising, held + [110.0], entry_price=95.0)   # bought under it, armed by day 1's close
    st = _state(held, entry=95.0, hard=90.0, be=False, prior=rising)
    step = _step(st, 112.0, 111.0, date(2026, 10, 30), trail_arm_on_close_above=True)
    assert step.action == "sma_stopped"                                        # armed: a close below the line still sells


def test_never_above_stays_unarmed_across_several_days_and_today_above_arms_without_an_exit():
    st = _state([290.0, 295.0], prior=PRIOR)                                   # two held days, both under their lines
    assert not _trail_armed_before_today(PRIOR, [290.0, 295.0, 298.0])
    step = _step(st, 298.0, 291.0, date(2026, 10, 30), trail_arm_on_close_above=True)
    assert step.action != "sma_stopped"
    st2 = _state([290.0, 295.0, 345.0], prior=PRIOR)                           # day 3 closes ABOVE its line ...
    assert _trail_armed_before_today(PRIOR, [290.0, 295.0, 345.0, 300.0])      # ... so day 4 is armed
    step2 = _step(st2, 300.0, 296.0, date(2026, 11, 2), trail_arm_on_close_above=True)
    assert step2.action == "sma_stopped"


def test_a_trade_bought_above_its_line_behaves_exactly_as_before():
    rising = [100.0 + i for i in range(20)]
    entry_line = _sma_10_20_line(rising)
    assert 120.0 >= entry_line                                                 # bought above the line it entered under
    assert _trail_armed_before_today(rising, [109.0], entry_price=120.0)       # armed from the fill
    st = _state([], entry=120.0, hard=105.0, be=False, prior=rising)
    old = _step(st, 109.0, 108.0, date(2026, 10, 28))                          # first close BELOW the line
    new = _step(st, 109.0, 108.0, date(2026, 10, 28), trail_arm_on_close_above=True)
    assert old.action == "sma_stopped" and new == old                          # same decision, same numbers


def test_default_off_is_byte_identical_and_other_modes_refuse_the_flag():
    st = _state([], prior=PRIOR)
    a = _step(st, 299.8, 286.0, date(2026, 10, 28))
    b = _step(st, 299.8, 286.0, date(2026, 10, 28), trail_arm_on_close_above=False)
    assert a == b
    with pytest.raises(ValueError):
        _step(st, 299.8, 286.0, date(2026, 10, 28), trail_mode="ema_10_20", trail_arm_on_close_above=True)


def test_the_live_tracker_passes_the_flag_on_all_three_calls():
    import ast
    import inspect
    # source-pin-ok: the population of live call sites — every apply_daily_exit_step call in the live tracker must carry the flag, which no single behaviour run can show for all three paths
    from agents.market_intelligence.broker import live_tracker
    tree = ast.parse(inspect.getsource(live_tracker))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "apply_daily_exit_step"]
    assert len(calls) == 3
    for c in calls:
        kw = {k.arg: k.value for k in c.keywords}
        assert "trail_arm_on_close_above" in kw and getattr(kw["trail_arm_on_close_above"], "value", None) is True
