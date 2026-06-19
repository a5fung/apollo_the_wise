"""#275 — kill/scale band evaluator (pure-function unit tests).

The load-bearing property: the SIGNED bands must NOT fire on the normal variance of the
healthy +0.95R/30% year (#268 Phase B envelope — trailing-20 p5 −0.63R / min −1.03R,
worst streak 15, maxDD −24.1R). These tests pin each band's boundary against that envelope.
"""
from agents.market_intelligence.kill_scale_bands import (
    evaluate_kill_scale_bands, current_losing_streak, is_transition,
    _SAMPLE_FLOOR, _SCALE_MIN_TRADES,
)


def _rs(value, n):
    return [value] * n


# ── losing-streak convention ──

def test_streak_counts_breakeven_as_loss():
    # r <= 0 is a loss (matches the calibration's worst-streak=15 convention).
    assert current_losing_streak([1.0, -1.0, 0.0, -1.0]) == 3
    assert current_losing_streak([-1.0, -1.0, 2.0]) == 0   # last trade was a win
    assert current_losing_streak([]) == 0


# ── sample-size floor: no strategy-health band before 20 trades ──

def test_below_floor_holds_even_with_ugly_rs():
    # 19 brutal trades — still HOLD (only equity guards bind pre-floor).
    v = evaluate_kill_scale_bands(_rs(-1.0, _SAMPLE_FLOOR - 1), equity_above_start=False)
    assert v.band == "HOLD"
    assert "sample floor" in v.reasons[0]


def test_below_floor_block_tier_still_kills():
    # The drawdown-breaker BLOCK equity guard binds from day 1, floor or not.
    v = evaluate_kill_scale_bands(_rs(-1.0, 5), equity_above_start=False, drawdown_tier="BLOCK")
    assert v.band == "KILL"
    assert "BLOCK" in v.reasons[0]


# ── KILL must NOT fire on the healthy envelope; fires just beyond it ──

def test_worst_healthy_t20_is_reduce_not_kill():
    # The worst healthy trailing-20 window was −1.03R → REDUCE, NOT KILL (kill band −1.05).
    v = evaluate_kill_scale_bands(_rs(-1.03, 20), equity_above_start=False)
    assert v.band == "REDUCE"


def test_t20_at_kill_threshold_kills():
    v = evaluate_kill_scale_bands(_rs(-1.05, 20), equity_above_start=False)
    assert v.band == "KILL"
    assert any("trailing-20" in r for r in v.reasons)


def test_healthy_maxdd_cum_r_does_not_kill():
    # −24R cumulative (the healthy maxDD) must not KILL; −30R does.
    # 24 trades averaging −1R = −24R cum, t20 = −1R (≤ −0.70 → REDUCE, not KILL via t20).
    v24 = evaluate_kill_scale_bands(_rs(-1.0, 24), equity_above_start=False)
    assert v24.band == "REDUCE"            # cum −24 alone is not a KILL
    assert all("cumulative" not in r for r in v24.reasons)
    # 30 trades averaging −1R = −30R cum AND t20 −1R → KILL (both cum and... t20 −1 > −1.05,
    # so KILL is driven by the cumulative −30R guard specifically).
    v30 = evaluate_kill_scale_bands(_rs(-1.0, 30), equity_above_start=False)
    assert v30.band == "KILL"
    assert any("cumulative" in r for r in v30.reasons)


# ── REDUCE boundary vs healthy p5 ──

def test_healthy_p5_t20_holds_not_reduce():
    # Healthy p5 trailing-20 = −0.63R; REDUCE band is −0.70R → −0.63 stays HOLD. End the
    # window with a win so the streak is cleared and we isolate the t20 mean (−12.6/20).
    v = evaluate_kill_scale_bands(_rs(-1.0, 19) + [6.4], equity_above_start=False)
    assert round(v.trailing_20, 2) == -0.63
    assert v.band == "HOLD"


def test_t20_below_reduce_threshold_reduces():
    # trailing-20 exactly at −0.70 (−14.0/20), streak cleared by the trailing win → the
    # REDUCE is driven by the t20 threshold, not the streak.
    v = evaluate_kill_scale_bands(_rs(-1.0, 19) + [5.0], equity_above_start=False)
    assert round(v.trailing_20, 2) == -0.70
    assert v.band == "REDUCE"
    assert any("trailing-20" in r for r in v.reasons)


def test_streak_15_holds_streak_16_reduces():
    # Worst observed healthy streak = 15 → HOLD; 16 exceeds it → REDUCE.
    base = _rs(1.0, 6)  # wins to keep t20 healthy so only the streak can trigger
    assert evaluate_kill_scale_bands(base + _rs(-1.0, 15), equity_above_start=False).band == "HOLD"
    v16 = evaluate_kill_scale_bands(base + _rs(-1.0, 16), equity_above_start=False)
    assert v16.band == "REDUCE"
    assert any("streak" in r for r in v16.reasons)


# ── SCALE ──

def test_scale_requires_40_trades_positive_t40_and_equity_up():
    rs = _rs(0.6, _SCALE_MIN_TRADES)       # trailing-40 = +0.6 ≥ +0.5
    assert evaluate_kill_scale_bands(rs, equity_above_start=True).band == "SCALE"
    # equity not above start → no scale
    assert evaluate_kill_scale_bands(rs, equity_above_start=False).band == "HOLD"
    # only 39 trades → no trailing-40 → HOLD
    assert evaluate_kill_scale_bands(_rs(0.6, 39), equity_above_start=True).band == "HOLD"
    # t40 just under +0.5 → HOLD
    assert evaluate_kill_scale_bands(_rs(0.49, 40), equity_above_start=True).band == "HOLD"


def test_healthy_year_expectancy_holds():
    # A +0.95R-ish steady cohort with normal variance sits in HOLD (not SCALE unless the
    # explicit scale conditions are met; here equity flat so HOLD).
    import random
    random.seed(7)
    rs = [random.choice([-1.0, -1.0, -1.0, 3.0, 5.0]) for _ in range(60)]  # ~+0.6R/30%-ish
    v = evaluate_kill_scale_bands(rs, equity_above_start=False)
    assert v.band in ("HOLD", "SCALE")     # never REDUCE/KILL on healthy variance
    assert v.band == "HOLD"                # equity flat → not scaling


# ── transitions ──

def test_is_transition():
    assert is_transition(None, "HOLD") is True       # first observation
    assert is_transition("HOLD", "HOLD") is False
    assert is_transition("HOLD", "REDUCE") is True
    assert is_transition("REDUCE", "KILL") is True
    assert is_transition("REDUCE", "HOLD") is True    # recovery is a transition too
