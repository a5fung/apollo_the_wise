"""Regime classification recalibration — #372 (flat != bull) + #373 (whipsaw), operator 2026-06-24.

The net-signal-count classifier was over-Bull on flat/choppy tapes: SPY flat ON its 50MA scored
+1 bull, a balanced ~1.0x +/-4% ratio scored +1 bull, and there was no choppiness signal at all.
Recalibration: flat-ON/above-the-line and 1.0-1.25x ratio score 0 (NEUTRAL, not bull) — but a
ONE-SIDED band, so BELOW the line keeps its caution (a two-sided band wrongly un-counted that and
flipped 6/16-18 Choppy->Bull in the backtest). Plus a whipsaw signal: +1 bear when the index holds
up while recent breadth narrows (5d +/-4% < 1.0 and < the 10d). Validated against 22 days of stored
regime history before deploy (all reclassifications conservative-direction; genuine uptrends stay
Bull).
"""
from agents.market_intelligence.regime import _determine_regime

_TIER = {"Bull": 3, "Choppy": 2, "Correcting": 1, "Crisis": 0}


def test_today_flat_tape_is_choppy_not_bull():
    # 2026-06-24 actual signals: SPY flat on its 50MA, +6% on its 200MA, low VIX, 60% breadth, but
    # the 5d +/-4% (0.83) is narrowing below the 10d (1.03) under a flat index — the over-Bull case.
    regime, _, _ = _determine_regime(
        spy_vs_50ma=0.04, spy_vs_200ma=6.31, qqq_vs_50ma=1.57, vix=18.63,
        breadth_pct=None, pct4_ratio_5d=0.83, pct4_ratio_10d=1.03, t2108=60.2)
    assert regime == "Choppy"


def test_clear_uptrend_still_bull():
    # the recalibration must NOT over-bearish a genuine trend.
    regime, _, _ = _determine_regime(
        spy_vs_50ma=4.0, spy_vs_200ma=8.0, qqq_vs_50ma=5.0, vix=14.0,
        breadth_pct=None, pct4_ratio_5d=2.5, pct4_ratio_10d=2.2, t2108=65.0)
    assert regime == "Bull"


def test_flat_spy_is_neutral_not_bull():
    # flat (+0.4%) vs clearly above (+3%), same tape: flat must be no MORE bullish, and on its own
    # must not reach Bull from middling signals (it used to, via the flat=+1-bull bug).
    base = dict(spy_vs_200ma=3.0, qqq_vs_50ma=1.0, vix=19.0, breadth_pct=None,
                pct4_ratio_5d=1.1, pct4_ratio_10d=1.1, t2108=50.0)
    flat, _, _ = _determine_regime(spy_vs_50ma=0.4, **base)
    above, _, _ = _determine_regime(spy_vs_50ma=3.0, **base)
    assert _TIER[flat] <= _TIER[above]
    assert flat != "Bull"


def test_below_50ma_keeps_caution():
    # the one-sided-band fix (the 6/16-18 regression): BELOW the line stays bearish, not neutral.
    base = dict(spy_vs_200ma=5.0, qqq_vs_50ma=2.5, vix=15.0, breadth_pct=None,
                pct4_ratio_5d=1.1, pct4_ratio_10d=1.1, t2108=65.0)
    flat, _, _ = _determine_regime(spy_vs_50ma=0.3, **base)
    below, _, _ = _determine_regime(spy_vs_50ma=-1.5, **base)
    assert _TIER[below] < _TIER[flat]  # below-the-line is strictly more conservative than flat


def test_whipsaw_divergence_is_more_conservative():
    # index up + 5d breadth narrowing below 1.0 AND below the 10d -> +1 bear nudge toward Choppy.
    base = dict(spy_vs_50ma=1.5, spy_vs_200ma=5.0, qqq_vs_50ma=1.0, vix=18.0,
                breadth_pct=None, t2108=55.0)
    no_div, _, _ = _determine_regime(**base, pct4_ratio_5d=1.5, pct4_ratio_10d=1.4)
    with_div, _, _ = _determine_regime(**base, pct4_ratio_5d=0.7, pct4_ratio_10d=1.1)
    assert _TIER[with_div] < _TIER[no_div]
