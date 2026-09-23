"""Three-signal alt-season trigger evaluator.

Each signal answers a distinct question; single-signal triggers conflate them
and produce false positives:

  (1) Stablecoin total mcap 30d slope > 0   -> capital ENTERING ecosystem
  (2) BTC.D 30d slope < 0 (5+ days) AND
      BTC.D < 55%                            -> rotating OUT of core
  (3) TOTAL3 30d slope > 0 (5+ days) AND
      TOTAL3 > 90d SMA                       -> reaching LONG TAIL

ALL must hold + 30-day cooldown to fire. Each gate alone misfires:
- (1) alone: capital can enter and pile into BTC (2024 ETF flows)
- (2) alone: pure BTC -> ETH rotation, alts flat
- (3) alone: noise spike or top of base about to roll over

Pure-logic module — no I/O. Caller supplies time-series; module evaluates.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Configurable thresholds — overrideable in unit tests / replay scripts.
BTC_DOMINANCE_CEILING_PCT = 55.0
SLOPE_PERSISTENCE_DAYS = 5
COOLDOWN_DAYS = 30
SLOPE_WINDOW_DAYS = 30
SMA_WINDOW_DAYS = 90


def _linear_slope(series: list[tuple[date, float]]) -> Optional[float]:
    """Simple least-squares slope (units: value/day). None if too few points."""
    if len(series) < 5:
        return None
    n = len(series)
    # x = days from first observation
    base = series[0][0]
    xs = [(d - base).days for d, _ in series]
    ys = [v for _, v in series]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


def _slope_persistence_days(series: list[tuple[date, float]], direction: str) -> int:
    """Return how many of the last days had a slope in the requested direction.

    direction: 'positive' or 'negative'. Computes a rolling 5-day slope at each
    of the last 10 days and counts consecutive matching ones from the most recent.
    """
    if len(series) < SLOPE_PERSISTENCE_DAYS + 1:
        return 0
    consec = 0
    for end in range(len(series) - 1, len(series) - SLOPE_PERSISTENCE_DAYS - 5, -1):
        if end - 5 < 0:
            break
        window = series[end - 5: end + 1]
        s = _linear_slope(window)
        if s is None:
            break
        if direction == "positive" and s > 0:
            consec += 1
        elif direction == "negative" and s < 0:
            consec += 1
        else:
            break
    return consec


def _sma(series: list[tuple[date, float]], n: int) -> Optional[float]:
    if len(series) < n:
        return None
    return statistics.fmean(v for _, v in series[-n:])


def evaluate_alt_season(
    btc_dominance_history: list[tuple[date, float]],
    total3_history: list[tuple[date, float]],
    stablecoin_history: list[tuple[date, float]],
    last_alert_at: Optional[date],
    today: date,
) -> dict:
    """Evaluate the three-signal trigger.

    Each history is sorted ascending: list of (date, value).
    Returns dict with:
        - fired: bool
        - cooldown_active: bool
        - signals: dict of per-signal evaluation (each True/False with values)
        - reason: human-readable summary if not fired
    """
    cooldown_active = (
        last_alert_at is not None
        and (today - last_alert_at).days < COOLDOWN_DAYS
    )

    # Signal 1: Stablecoin slope > 0 over last 30 days.
    stable_slope = _linear_slope(stablecoin_history[-SLOPE_WINDOW_DAYS:])
    signal_stable = (stable_slope is not None and stable_slope > 0)

    # Signal 2a: BTC.D slope < 0 with 5+ day persistence.
    btc_slope = _linear_slope(btc_dominance_history[-SLOPE_WINDOW_DAYS:])
    btc_persistence = _slope_persistence_days(
        btc_dominance_history[-(SLOPE_PERSISTENCE_DAYS + 5):], "negative"
    )
    btc_current = btc_dominance_history[-1][1] if btc_dominance_history else None
    signal_btc_dominance = (
        btc_slope is not None
        and btc_slope < 0
        and btc_persistence >= SLOPE_PERSISTENCE_DAYS
        and btc_current is not None
        and btc_current < BTC_DOMINANCE_CEILING_PCT
    )

    # Signal 3: TOTAL3 slope > 0 (5+ day persistence) AND TOTAL3 > 90d SMA.
    total3_slope = _linear_slope(total3_history[-SLOPE_WINDOW_DAYS:])
    total3_persistence = _slope_persistence_days(
        total3_history[-(SLOPE_PERSISTENCE_DAYS + 5):], "positive"
    )
    total3_current = total3_history[-1][1] if total3_history else None
    total3_sma = _sma(total3_history, SMA_WINDOW_DAYS)
    signal_total3 = (
        total3_slope is not None
        and total3_slope > 0
        and total3_persistence >= SLOPE_PERSISTENCE_DAYS
        and total3_current is not None
        and total3_sma is not None
        and total3_current > total3_sma
    )

    fired = (
        signal_stable
        and signal_btc_dominance
        and signal_total3
        and not cooldown_active
    )

    # Optional pre-arm telemetry: capital arriving, but not yet rotating.
    pre_arm = signal_stable and not signal_btc_dominance and not signal_total3

    reasons = []
    if not signal_stable:
        reasons.append("stablecoin slope not positive")
    if not signal_btc_dominance:
        reasons.append(
            f"BTC.D not breaking down (slope={btc_slope}, persist={btc_persistence}d, "
            f"current={btc_current})"
        )
    if not signal_total3:
        reasons.append(
            f"TOTAL3 not breaking out (slope={total3_slope}, persist={total3_persistence}d, "
            f"current={total3_current}, sma90={total3_sma})"
        )
    if cooldown_active:
        days_remaining = COOLDOWN_DAYS - (today - last_alert_at).days
        reasons.append(f"cooldown active ({days_remaining}d remaining)")

    return {
        "fired": fired,
        "cooldown_active": cooldown_active,
        "pre_arm": pre_arm,
        "signals": {
            "stable_slope_positive": {
                "passed": signal_stable,
                "slope": stable_slope,
            },
            "btc_dominance_breakdown": {
                "passed": signal_btc_dominance,
                "slope": btc_slope,
                "persistence_days": btc_persistence,
                "current_pct": btc_current,
                "ceiling_pct": BTC_DOMINANCE_CEILING_PCT,
            },
            "total3_breakout": {
                "passed": signal_total3,
                "slope": total3_slope,
                "persistence_days": total3_persistence,
                "current": total3_current,
                "sma_90d": total3_sma,
            },
        },
        "reason": "; ".join(reasons) if reasons else "all signals firing",
    }
