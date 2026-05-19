"""Regression tests for the tiered drawdown breaker state machine (2026-05-18).

Locks the 4-state transition semantics:
  OK / WATCH / REDUCE / BLOCK with asymmetric hysteresis at each boundary.
  Trip-side: jump to deepest applicable tier in one snapshot.
  Release-side: step up one tier per evaluation.

Run: pytest tests/test_drawdown_tiered.py -v
"""
from __future__ import annotations

import pytest

from agents.market_intelligence.broker.drawdown_breaker import (
    _next_state, get_tier_multiplier,
    _STATE_OK, _STATE_WATCH, _STATE_REDUCE, _STATE_BLOCK,
)
from agents.market_intelligence.constants import (
    DRAWDOWN_WATCH_TRIP_PCT,
    DRAWDOWN_REDUCE_TRIP_PCT,
    DRAWDOWN_BLOCK_TRIP_PCT,
    DRAWDOWN_TIER_MULTIPLIER,
)


# ── Trip-side: jump to deepest applicable tier ────────────────────────


def test_ok_stays_ok_when_drawdown_above_watch_threshold():
    # Drawdown -3% (less than -4% WATCH trip) → stay OK
    assert _next_state(_STATE_OK, -0.03) == _STATE_OK


def test_ok_to_watch_at_minus_4pct():
    assert _next_state(_STATE_OK, DRAWDOWN_WATCH_TRIP_PCT) == _STATE_WATCH
    # Just below the boundary
    assert _next_state(_STATE_OK, -0.05) == _STATE_WATCH


def test_ok_jumps_to_reduce_at_minus_7pct():
    """Trip-side: skip WATCH on a deep one-snapshot drop."""
    assert _next_state(_STATE_OK, DRAWDOWN_REDUCE_TRIP_PCT) == _STATE_REDUCE
    assert _next_state(_STATE_OK, -0.10) == _STATE_REDUCE


def test_ok_jumps_to_block_at_minus_12pct():
    """Trip-side: -15% one-day drop from OK lands directly in BLOCK."""
    assert _next_state(_STATE_OK, DRAWDOWN_BLOCK_TRIP_PCT) == _STATE_BLOCK
    assert _next_state(_STATE_OK, -0.15) == _STATE_BLOCK


def test_watch_jumps_to_block_on_deep_drop():
    """From WATCH, a snapshot at -15% skips REDUCE and lands in BLOCK."""
    assert _next_state(_STATE_WATCH, -0.15) == _STATE_BLOCK


def test_reduce_to_block_at_minus_12():
    assert _next_state(_STATE_REDUCE, -0.13) == _STATE_BLOCK


# ── Release-side: step up at most one tier per evaluation ──────────────


def test_watch_releases_to_ok_at_minus_2_5pct():
    """WATCH → OK only when drawdown ≥ -2.5%."""
    assert _next_state(_STATE_WATCH, -0.02) == _STATE_OK
    # At the exact boundary
    assert _next_state(_STATE_WATCH, -0.025) == _STATE_OK


def test_watch_stays_in_hysteresis_band():
    """Between -4% and -2.5%, WATCH stays WATCH."""
    assert _next_state(_STATE_WATCH, -0.035) == _STATE_WATCH


def test_reduce_releases_to_watch_at_minus_4pct():
    """REDUCE → WATCH (one tier up), NOT skipping to OK."""
    assert _next_state(_STATE_REDUCE, -0.035) == _STATE_WATCH
    # Even at -2% which is also above WATCH release, only step ONE tier
    assert _next_state(_STATE_REDUCE, -0.02) == _STATE_WATCH


def test_reduce_stays_in_hysteresis_band():
    """Between -7% and -4%, REDUCE stays REDUCE."""
    assert _next_state(_STATE_REDUCE, -0.055) == _STATE_REDUCE


def test_block_releases_to_reduce_at_minus_7pct():
    """BLOCK → REDUCE (one tier up)."""
    assert _next_state(_STATE_BLOCK, -0.065) == _STATE_REDUCE
    # Even at -2% (full recovery), only step one tier per eval
    assert _next_state(_STATE_BLOCK, -0.02) == _STATE_REDUCE


def test_block_stays_in_hysteresis_band():
    """Between -12% and -7%, BLOCK stays BLOCK."""
    assert _next_state(_STATE_BLOCK, -0.10) == _STATE_BLOCK


# ── Legacy migration ──────────────────────────────────────────────────


def test_legacy_tripped_treated_as_reduce_for_transitions():
    """Pre-2026-05-18 'TRIPPED' state in DB rows migrates via _next_state.

    Mapped to REDUCE for transition computation: same drawdown that would
    have kept TRIPPED stays REDUCE; release at -4% steps up to WATCH
    (matching the new REDUCE→WATCH boundary).
    """
    # -5% drawdown: legacy stayed TRIPPED, now stays REDUCE
    assert _next_state("TRIPPED", -0.05) == _STATE_REDUCE
    # -3.5% drawdown: legacy released to OK, now steps up to WATCH
    assert _next_state("TRIPPED", -0.035) == _STATE_WATCH
    # -15% drawdown: legacy stayed TRIPPED, now jumps to BLOCK
    assert _next_state("TRIPPED", -0.15) == _STATE_BLOCK


def test_legacy_tripped_multiplier_maps_to_reduce():
    """get_tier_multiplier('TRIPPED') returns REDUCE multiplier (0.5)."""
    assert get_tier_multiplier("TRIPPED") == DRAWDOWN_TIER_MULTIPLIER[_STATE_REDUCE]


# ── Sizing multiplier per state ───────────────────────────────────────


def test_tier_multipliers():
    assert get_tier_multiplier(_STATE_OK) == 1.0
    assert get_tier_multiplier(_STATE_WATCH) == 1.0
    assert get_tier_multiplier(_STATE_REDUCE) == 0.5
    assert get_tier_multiplier(_STATE_BLOCK) == 0.0


def test_unknown_state_returns_safe_default():
    """Defensive: an unexpected state value returns 1.0 multiplier (don't block)."""
    assert get_tier_multiplier("NONEXISTENT") == 1.0


# ── Today's actual case ───────────────────────────────────────────────


def test_todays_minus_6pct_lands_in_watch():
    """2026-05-18 paper account: -6.06% drawdown from $99,271 peak.
    Under binary design: TRIPPED (would block entries for ~30 days).
    Under tiered design: WATCH (informational only).
    """
    assert _next_state(_STATE_OK, -0.0606) == _STATE_WATCH
    # And from legacy TRIPPED: migrates to REDUCE (still alerts but allows
    # half-sized entries — not full block).
    # Wait, that's incorrect: -6.06% from TRIPPED legacy → REDUCE (treated
    # as REDUCE start; -6.06% is in REDUCE hysteresis band so stays REDUCE)
    assert _next_state("TRIPPED", -0.0606) == _STATE_REDUCE
