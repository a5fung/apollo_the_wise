"""#170 cooldown re-setup shadow classifier (telemetry-only, fail-open).

The 60-day EP cooldown is catalyst- + structure-blind: it suppresses a fresh,
weeks-later gap (a re-setup, e.g. FLNC 2026-06-01 NVDA deal +35.7% / 25d after
its prior alert) the same as a next-day continuation. Backward-check 2026-06-01
showed the weeks-later re-setups ran ~2x the alerted cohort. `_is_cooldown_resetup`
is the telemetry classifier that flags the re-setup subset (shadow only — it does
NOT change suppression). Alpaca/backtester stubbing handled by tests/conftest.py.
"""
from agents.market_intelligence.ep_detector import (
    _is_cooldown_resetup,
    EP_COOLDOWN_RESETUP_MIN_DAYS,
)


def test_resetup_true_for_hard_gap_weeks_later():
    # FLNC 2026-06-01 shape: +35.7% gap, 25 days after the prior alert.
    assert _is_cooldown_resetup(35.7, 25) is True


def test_resetup_true_at_boundary():
    # Exactly at the min-days + 15% gap floor.
    assert _is_cooldown_resetup(15.0, EP_COOLDOWN_RESETUP_MIN_DAYS) is True


def test_not_resetup_for_next_day_continuation():
    # CRSR 5/28 / FLNC 5/08 shape: hard gap but 1 day after -> still extended.
    assert _is_cooldown_resetup(33.8, 1) is False


def test_not_resetup_just_inside_continuation_window():
    # 1 day below the threshold is still a continuation, not a re-setup.
    assert _is_cooldown_resetup(38.6, EP_COOLDOWN_RESETUP_MIN_DAYS - 1) is False


def test_not_resetup_for_small_gap():
    # Weeks later but the gap is below the 15% floor -> not a re-setup signal.
    assert _is_cooldown_resetup(9.0, 30) is False


def test_no_prior_alert_date_is_not_resetup():
    # Fail-open: missing days_since (date fetch failed) -> shadow no-ops.
    assert _is_cooldown_resetup(20.0, None) is False
