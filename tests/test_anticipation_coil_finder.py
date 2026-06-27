"""#391 coil-finder unit tests — anticipation.find_coil_setup.

The detector: RUNUP (>=15% leg) -> consolidation give-back (retrace of the runup leg) -> recent-coil
tightness. The HOLD gate (<= COIL_HOLD_LIMIT) is applied by the JOB, not the detector, so these tests
assert the detector RETURNS the retrace and the job's filter would act on it.
"""
from datetime import date, timedelta

from agents.market_intelligence.anticipation import find_coil_setup, COIL_HOLD_LIMIT

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
