"""A zero-inflated count metric must clear its own P95 before it pages the operator.

WHY (2026-09-09). `cooldowns_per_day` fired an L2 at 9 against median 2 / MAD 2 (z=3.5). But 9
was the SIXTH HIGHEST value of the previous 35 days and had already occurred twice in that
window — 24, 19, 13, 10, 10, 9, 9, 9. The arithmetic was right and the model was wrong: on a
series whose ordinary days are 0-2 and whose ordinary weeks contain spikes, a MAD of 2 makes
every busy night a three-sigma event.

This was the SECOND false page of that week; the 9M lane had been retired the day before for the
same class of defect. The guard is deliberately narrow — it withholds only the PAGE, downgrading
band 3 to band 2, so the value is still recorded and still visible on the drift surface.

⚠ THESE TESTS DRIVE `_compute_anomaly` ITSELF. The first version of this file re-implemented the
guard's condition as a local `_guard()` helper and asserted against that — so deleting the real
guard from `system_audit.py` would have left every test green. That is the same defect the file
is about, and `_classify_band` was extracted in June for exactly this reason ("the test previously
re-implemented this loop"). Baseline numbers below are the REAL stored baseline for
`cooldowns_per_day` on 2026-09-09 (p50 2, p95 19, MAD 2, n 21), read from `mi_metric_baselines`.
"""
from collections import namedtuple
from datetime import date

import pytest

from agents.market_intelligence import system_audit as sa

_FakeStatus = namedtuple("FakeStatus", ["is_trading_day", "reason"])


def _spec(monkeypatch, *, current, p95=19.0, spiky=True, name="cooldowns_per_day",
          p50=2.0, mad=2.0, last_band=0):
    """A MetricSpec wired to the real `_compute_anomaly` with only I/O stubbed."""
    monkeypatch.setattr(sa, "get_market_status", lambda d: _FakeStatus(True, "t"))
    monkeypatch.setattr(sa, "et_today", lambda: date(2026, 9, 9))

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(sa, "_record_metric_sample", _noop)

    async def _baseline(*a, **k):
        return {"p50": p50, "p95": p95, "mad": mad, "sample_n": 21}
    monkeypatch.setattr(sa, "get_metric_baseline", _baseline)

    async def _last(*a, **k):
        return last_band
    monkeypatch.setattr(sa, "_last_band_for", _last)

    async def _recent(*a, **k):
        return False
    monkeypatch.setattr(sa, "_recent_window_stable", _recent)

    async def _fetch(_conn):
        return current
    return sa.MetricSpec(name=name, fetch_today=_fetch, drill_sql="-- noop", spiky=spiky)


async def _run(spec):
    return await sa._compute_anomaly(conn=None, metric=spec, current_regime=None)


# ── The flag itself ──────────────────────────────────────────────────────────

def test_metricspec_defaults_to_not_spiky():
    """Opt-in only. A new metric must not silently inherit page-suppression."""
    assert sa.MetricSpec("x", None, "SELECT 1").spiky is False


def test_cooldowns_per_day_is_marked_spiky():
    spec = next(m for m in sa._NIGHTLY_METRICS if m.name == "cooldowns_per_day")
    assert spec.spiky is True, (
        "cooldowns_per_day is zero-inflated and lumpy; without the P95 guard it pages on an "
        "ordinary busy night (the 2026-09-09 false positive)")


# ── The guard, through the real decision path ────────────────────────────────

@pytest.mark.asyncio
async def test_the_real_false_positive_would_no_longer_page(monkeypatch):
    """The actual numbers from 2026-09-09: 9 against p50 2 / MAD 2 / P95 19."""
    a = await _run(_spec(monkeypatch, current=9.0))
    assert a is not None and a.level == 3, "the 09-09 page would still fire as an L2"


@pytest.mark.asyncio
async def test_the_suppressed_value_is_still_recorded(monkeypatch):
    """The guard withholds the PAGE, not the observation — the drift surface must still see it."""
    a = await _run(_spec(monkeypatch, current=9.0))
    assert a.body["current"] == 9.0
    assert a.body["to_band"] == 2, "the value vanished from the drift surface entirely"


@pytest.mark.asyncio
async def test_a_genuine_spike_still_pages(monkeypatch):
    """Above P95 it pages exactly as before — the guard must not mute a real anomaly."""
    a = await _run(_spec(monkeypatch, current=40.0))
    assert a is not None and a.level == 2, "a genuine spike was muted — the guard is too wide"


@pytest.mark.asyncio
async def test_exactly_at_p95_is_suppressed(monkeypatch):
    """The boundary is `<=`: at the P95 itself there is no evidence of an unusual day."""
    a = await _run(_spec(monkeypatch, current=19.0))
    assert a.level == 3


@pytest.mark.asyncio
async def test_one_above_p95_pages(monkeypatch):
    """…and one step past it does page, so the boundary cannot silently widen."""
    a = await _run(_spec(monkeypatch, current=19.5))
    assert a.level == 2


@pytest.mark.asyncio
async def test_non_spiky_metrics_are_untouched(monkeypatch):
    """A metric that never opted in pages at 9 exactly as it did before the guard existed."""
    a = await _run(_spec(monkeypatch, current=9.0, spiky=False))
    assert a is not None and a.level == 2, "the guard leaked onto a metric that never opted in"


@pytest.mark.asyncio
async def test_a_missing_p95_does_not_suppress(monkeypatch):
    """No baseline P95 means no evidence to suppress on — it must still page."""
    a = await _run(_spec(monkeypatch, current=9.0, p95=None))
    assert a is not None and a.level == 2, "a missing baseline silently muted the pager"


@pytest.mark.asyncio
async def test_low_direction_is_not_suppressed(monkeypatch):
    """The guard reasons about upside spikes only; a collapse must still page.

    `theme_count_active` resolves to direction 'low' via _COLD_START_CEILINGS, so a value far
    BELOW its median is the anomaly — and it sits under the P95 by construction.
    """
    a = await _run(_spec(monkeypatch, current=2.0, name="theme_count_active",
                         p50=44.0, mad=1.0, p95=54.0))
    assert a is not None and a.level == 2, "a collapse was muted by an upside guard"
