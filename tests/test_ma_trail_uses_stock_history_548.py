"""The MA trail averaged OUR HOLDING PERIOD, not the stock (#548, operator 2026-08-08).

His question: *"10d MA exists regardless of how long we traded it, it's just the moving average
of the stock over time with or without our trades, if it closes below 10 or 20SMA then we sell,
isn't that the rule?"*

**It is the rule** — `EP_TRADING_RULES.md` §B4, his own file: *"Trail your stop with the 10- or
20-day moving average… Exit on first daily close below the active MA."*

**It was not the code.** `exit_logic` computed `sum(running_closes[-10:]) / 10`, and
`running_closes` starts EMPTY at fill and gains one entry per day WE held. Measured in prod:
BW held 15d → 10 closes, GOOGL 17d → 11, FPS 23d → 16, **every live trade → 0**. So the trail
could not exist until ~10 trading days in, and on a book whose longest hold is 2 days it was
structurally dead: **0 fires in 17 live trades; 2 fires ever, both paper, both at exactly 10
closes — it fired the first day it was permitted to exist.**

A bug fix, not a criteria change: the rubric is unchanged, the implementation read the wrong
series.
"""
from datetime import date

from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step


def _state(**over):
    s = {
        "alert_date": date(2026, 6, 1),
        "remaining_shares": 100.0,
        "entry_price": 100.0,
        "hard_stop": 90.0,
        "partial_taken": False,
        "breakeven_active": False,
        "exits": [],
        "running_closes": [],
    }
    s.update(over)
    return s


def test_the_trail_exists_on_DAY_ONE_when_the_stock_has_history():
    """The whole point. One held close, but the stock has 20 of its own — the MA is real."""
    prior = [100.0] * 20
    step = apply_daily_exit_step(
        _state(), {"l": 104.0, "c": 105.0}, date(2026, 6, 2), prior_closes=prior)
    assert step.active_sma is not None, (
        "the trail is still None on day one — it is averaging our holding period again, so a "
        "trade that never reaches ~10 held days can never be trailed")
    # trail series = twenty 100s + today's 105. SMA10 = (100*9 + 105)/10 = 100.5;
    # SMA20 = (100*19 + 105)/20 = 100.25; max() picks SMA10, per §B4.
    assert abs(step.active_sma - 100.5) < 1e-9, step.active_sma


def test_without_history_it_degrades_to_the_OLD_behavior_exactly():
    """`prior_closes=None` must be byte-identical to pre-#548 for every existing caller —
    backtester, shadow trackers, and the sweep harnesses all still pass nothing."""
    a = apply_daily_exit_step(_state(), {"l": 104.0, "c": 105.0}, date(2026, 6, 2))
    b = apply_daily_exit_step(
        _state(), {"l": 104.0, "c": 105.0}, date(2026, 6, 2), prior_closes=None)
    c = apply_daily_exit_step(
        _state(), {"l": 104.0, "c": 105.0}, date(2026, 6, 2), prior_closes=[])
    assert a.active_sma is None and b.active_sma is None and c.active_sma is None
    assert a.effective_stop == b.effective_stop == c.effective_stop


def test_it_matches_the_STOCK_s_moving_average_not_our_mean():
    """The arithmetic that distinguishes the two. Prior closes 1..20, one held close of 200.
    SMA20 over the stock's series = the real average; the old code would have returned None
    (one close) or 200 (the mean of what we held)."""
    prior = [float(i) for i in range(1, 21)]          # 1..20, mean 10.5
    step = apply_daily_exit_step(
        _state(), {"l": 199.0, "c": 200.0}, date(2026, 6, 2), prior_closes=prior)
    # trail series = 1..20 + [200]; SMA10 = last 10 = (12..20 + 200)/10, SMA20 = last 20
    sma_10 = (sum(range(12, 21)) + 200) / 10
    sma_20 = (sum(range(2, 21)) + 200) / 20
    assert abs(step.active_sma - max(sma_10, sma_20)) < 1e-9


def test_max_SMA10_SMA20_is_FAITHFUL_to_the_rule_and_must_not_be_touched():
    """§B4: *"Use 10-SMA when 10 > 20 (strong uptrend, tighter trail); use 20-SMA otherwise."*
    `max()` picks exactly that. It was NOT part of the bug and must survive any future fix."""
    # hard_stop is set BELOW the whole series in each case — otherwise the step exits at its
    # step-1 hard-stop branch and never reaches the trail at all (which is what made the first
    # version of this test fail on a $20 stock carrying a $90 stop).
    rising = [float(i) for i in range(1, 21)]   # SMA10 > SMA20
    step = apply_daily_exit_step(
        _state(entry_price=15.0, hard_stop=0.5), {"l": 19.0, "c": 20.0},
        date(2026, 6, 2), prior_closes=rising)
    sma_10 = (sum(range(12, 21)) + 20) / 10
    sma_20 = (sum(range(2, 21)) + 20) / 20
    assert sma_10 > sma_20
    assert abs(step.active_sma - sma_10) < 1e-9, "not using SMA10 in an uptrend"

    falling = [float(i) for i in range(20, 0, -1)]   # SMA20 > SMA10
    step2 = apply_daily_exit_step(
        _state(entry_price=5.0, hard_stop=0.1), {"l": 0.5, "c": 1.0},
        date(2026, 6, 2), prior_closes=falling)
    s10 = (sum(range(9, 0, -1)) + 1) / 10
    s20 = (sum(range(19, 0, -1)) + 1) / 20
    assert s20 > s10
    assert abs(step2.active_sma - s20) < 1e-9, "not using SMA20 in a downtrend"


# ── the trap: prior closes must NOT leak into the peak / giveback logic ────────────────────

def test_prior_closes_do_NOT_pollute_the_peak_used_by_the_giveback_floor():
    """`giveback_floor` arms off `max(running_closes)` — the peak the position ACTUALLY
    reached. A pre-entry high is not a gain we ever had; folding it in would arm the floor
    against a peak we never saw and could force an exit on a trade that had done nothing.

    This is the trap in the obvious implementation — seeding `running_closes` itself would
    have fixed the trail and silently broken this."""
    prior = [500.0] * 20          # the stock was much higher before we bought
    with_prior = apply_daily_exit_step(
        _state(), {"l": 104.0, "c": 105.0}, date(2026, 6, 2), prior_closes=prior,
        giveback_arm_gain=0.02, giveback_floor_frac=0.5)
    without = apply_daily_exit_step(
        _state(), {"l": 104.0, "c": 105.0}, date(2026, 6, 2),
        giveback_arm_gain=0.02, giveback_floor_frac=0.5)
    # the trail differs (it should), the giveback-derived peak must not
    assert with_prior.new_running_closes == without.new_running_closes == [105.0], (
        "prior closes leaked into running_closes — the peak/giveback logic now sees prices "
        "from before we owned the stock")


def test_the_trail_can_only_RAISE_the_stop_never_lower_it():
    """§B4: the trail activates only once it surpasses the hard-stop floor, and the effective
    stop is max(hard_stop, active_sma, entry). So a correct MA is PROTECTIVE — it can never
    exit earlier than the hard stop already would. This is the property that makes the fix
    safe to ship, so it is pinned rather than assumed."""
    low_ma = [1.0] * 20           # MA far below the hard stop
    step = apply_daily_exit_step(
        _state(), {"l": 104.0, "c": 105.0}, date(2026, 6, 2), prior_closes=low_ma)
    assert step.effective_stop == 90.0, (
        f"a below-stop trail moved the effective stop to {step.effective_stop} — the trail "
        "must never lower protection")
