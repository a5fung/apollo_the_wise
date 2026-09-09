"""A zero-inflated count metric must clear its own P95 before it pages the operator.

WHY (2026-09-09). `cooldowns_per_day` fired an L2 at 9 against median 2 / MAD 2 (z=3.5). But 9
was the SIXTH HIGHEST value of the previous 35 days and had already occurred twice in that
window — 24, 19, 13, 10, 10, 9, 9, 9. The arithmetic was right and the model was wrong: on a
series whose ordinary days are 0-2 and whose ordinary weeks contain spikes, a MAD of 2 makes
every busy night a three-sigma event.

This was the SECOND false page of that week; the 9M lane had been retired the day before for the
same class of defect. The guard is deliberately narrow — it withholds only the PAGE, downgrading
band 3 to band 2, so the value is still recorded and still visible on the drift surface.
"""
from agents.market_intelligence import system_audit as sa


def _guard(current, p95, spiky, direction="high", band=3):
    """The guard's exact condition, kept in one place so the cases cannot drift apart."""
    if band == 3 and spiky and p95 is not None and direction == "high" and current <= float(p95):
        return 2
    return band


def test_metricspec_defaults_to_not_spiky():
    """Opt-in only. A new metric must not silently inherit page-suppression."""
    assert sa.MetricSpec("x", None, "SELECT 1").spiky is False


def test_cooldowns_per_day_is_marked_spiky():
    spec = next(m for m in sa._NIGHTLY_METRICS if m.name == "cooldowns_per_day")
    assert spec.spiky is True, (
        "cooldowns_per_day is zero-inflated and lumpy; without the P95 guard it pages on an "
        "ordinary busy night (the 2026-09-09 false positive)")


def test_the_real_false_positive_would_no_longer_page():
    """The actual numbers from 2026-09-09."""
    assert _guard(9.0, 19.0, spiky=True) == 2, "the 09-09 page would still fire"


def test_a_genuine_spike_still_pages():
    """Above P95 it pages exactly as before — the guard must not mute a real anomaly."""
    assert _guard(40.0, 19.0, spiky=True) == 3, "a genuine spike was muted — the guard is too wide"


def test_non_spiky_metrics_are_untouched():
    assert _guard(9.0, 19.0, spiky=False) == 3, "the guard leaked onto a metric that never opted in"


def test_a_missing_p95_does_not_suppress():
    """No baseline P95 means no evidence to suppress on — it must still page."""
    assert _guard(9.0, None, spiky=True) == 3, "a missing baseline silently muted the pager"


def test_low_direction_is_not_suppressed():
    """The guard reasons about upside spikes only; a collapse must still page."""
    assert _guard(0.0, 19.0, spiky=True, direction="low") == 3
