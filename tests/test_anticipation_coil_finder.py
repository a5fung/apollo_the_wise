"""#391 coil-finder unit tests — anticipation.find_coil_setup.

The detector: RUNUP (>=15% leg) -> consolidation give-back (retrace of the runup leg) -> recent-coil
tightness. The HOLD gate (<= COIL_HOLD_LIMIT) is applied by the JOB, not the detector, so these tests
assert the detector RETURNS the retrace and the job's filter would act on it.
"""
from datetime import date, timedelta

from agents.market_intelligence.anticipation import (
    find_coil_setup, evaluate_coil_consolidation, coil_pin_reject_reason, COIL_HOLD_LIMIT,
)

_D0 = date(2026, 1, 1)


def _bars(closes, *, hl_frac=0.01):
    """Replay bars from a close series; h/l a tight +/-hl_frac band around each close."""
    return [{
        "date": (_D0 + timedelta(days=k)).isoformat(),
        "o": c, "h": c * (1 + hl_frac), "l": c * (1 - hl_frac), "c": c, "v": 1_000_000.0,
    } for k, c in enumerate(closes)]


_BASE = [100.0] * 30                                   # prior swing-low region
_RUNUP = [100.0 + 3.0 * (k + 1) for k in range(10)]    # 103..130 (a +30% leg; peak = 130 at idx 39)


def _series(coil_close):
    return _bars(_BASE + _RUNUP + [coil_close] * 15)   # 55 bars; peak idx 39, consolidation idx 40..54


def test_shallow_hold_tight_coil_is_found():
    bars = _series(125.0)                              # holds ~125 of the 100->130 leg (shallow give-back)
    s = find_coil_setup(bars, len(bars) - 1)
    assert s is not None
    assert s["peak_date"] == bars[39]["date"]         # the runup top, not a coil bar
    assert s["runup"] > 1.15
    assert s["retrace"] <= COIL_HOLD_LIMIT            # held the runup -> the job keeps it
    assert s["band"] < 0.05                           # tight coil


def test_deep_pullback_exceeds_hold_limit():
    bars = _series(108.0)                              # gives back most of the 100->130 leg
    s = find_coil_setup(bars, len(bars) - 1)
    # the runup is real so the detector still returns a setup; the JOB's filter drops it on retrace
    assert s is None or s["retrace"] > COIL_HOLD_LIMIT


def test_no_runup_flat_series_is_none():
    bars = _bars([100.0] * 55)                         # flat -> no >=15% leg
    assert find_coil_setup(bars, len(bars) - 1) is None


# ── evaluate_coil_consolidation: the LIVE #327 base detector (coil-finder + hold gate +
#    consolidation-shaped output anchored on the corrected coil peak) ──

def test_evaluate_coil_consolidation_held_coil_returns_row_anchored_on_peak():
    bars = _series(125.0)                              # shallow hold of the 100->130 leg
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is not None
    assert reject_reason is None
    assert row["anchor_date"] == bars[39]["date"]      # anchored on the runup PEAK, not a coil bar
    assert row["runup_ratio"] > 1.15
    assert row["state"] in ("coiled", "post_runup", "aged")
    assert row["hold_retrace"] <= COIL_HOLD_LIMIT
    # consolidation-shaped: the fields upsert_consolidation + the board consume are present
    for key in ("runup_high", "coil_days", "last_close", "rmv_15d", "pullback_shape",
                "fresh_tightening", "tight_close_streak"):
        assert key in row


def test_evaluate_coil_consolidation_deep_pullback_is_none():
    bars = _series(108.0)                              # gave back > half the leg -> hold gate drops it
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is None
    assert reject_reason is None                       # plain miss, not a pin-guard reject


def test_evaluate_coil_consolidation_no_runup_is_none():
    row, reject_reason = evaluate_coil_consolidation(_bars([100.0] * 55))
    assert row is None
    assert reject_reason is None


# ── #410 buyout/deal-PIN shape guard — NUVL 6/30 FP: gapped ~37% to the acquisition price and
#    flatlined; the coil-finder read the post-deal PIN as a tight coil (buy 123.50/stop 123.43 =
#    0.06% stop distance, the giveaway). ────────────────────────────────────────────────────────

def test_normal_coil_is_not_pin_rejected():
    """Sanity: the existing organic-coil fixture (shallow hold, ~1% daily range) must NOT trip the
    buyout-pin guard — the guard only fires on the deal-pin flatness signature (<0.5% median range)."""
    bars = _series(125.0)
    coil = find_coil_setup(bars, len(bars) - 1)
    assert coil is not None
    assert coil_pin_reject_reason(bars, coil) is None
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is not None   # unaffected — still a valid candidate
    assert reject_reason is None


def _nuvl_series():
    """Buyout-PIN fixture (NUVL 6/30-shaped): 40 flat days at 100 (pre-deal base), ONE gap day to
    137 (+37%, the entire leg lands in a SINGLE bar — a deal-price jump, not an organic runup),
    then 15 near-dead-flat days at 137 (the post-deal PIN, hl_frac=0.0003 -> ~0.06% daily range,
    matching NUVL's actual buy 123.50/stop 123.43 giveaway)."""
    closes = [100.0] * 40 + [137.0] * 16   # index 40 = the gap day; 41..55 = the 15-day flat PIN
    return _bars(closes, hl_frac=0.0003)


def test_buyout_pin_gap_to_flat_rejected():
    bars = _nuvl_series()
    coil = find_coil_setup(bars, len(bars) - 1)
    assert coil is not None                       # a real runup->coil STRUCTURE is found...
    assert coil["retrace"] <= COIL_HOLD_LIMIT      # ...and it "held" — deceptively: it's the deal pin
    assert coil_pin_reject_reason(bars, coil) == "gap_to_flat"
    # the qualifier rejects it outright — NOT a silent drop; evaluate_coil_consolidation now
    # RETURNS this exact reason (no re-derivation) so the job layer (scheduler.
    # _consolidation_readiness_job) can audit it (anticipation_coil_buyout_pin_rejected) rather
    # than letting it surface as a false coil.
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is None
    assert reject_reason == "gap_to_flat"


def test_buyout_pin_stop_floor_rejected_without_single_bar_gap():
    """A pin that reads flat (<0.5% range) but whose runup was an ORGANIC multi-day climb (not a
    single-bar gap) still trips the guard — via the plain stop_floor reason, not gap_to_flat."""
    base = [100.0] * 30
    runup = [100.0 + 3.0 * (k + 1) for k in range(10)]   # 103..130, a +30% MULTI-DAY leg
    closes = base + runup + [129.5] * 15                  # flat pin just under the peak
    bars = _bars(closes, hl_frac=0.0003)
    coil = find_coil_setup(bars, len(bars) - 1)
    assert coil is not None
    assert coil["retrace"] <= COIL_HOLD_LIMIT
    assert coil_pin_reject_reason(bars, coil) == "stop_floor"
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is None
    assert reject_reason == "stop_floor"
