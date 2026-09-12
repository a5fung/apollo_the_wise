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
import json
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


# ── #633: the engagement must record ITSELF, distinguishably ────────────────
#
# The review `spiky_guard_first_engagement` used to key on `to_band == 2`, but an ordinary
# night that reaches band 2 on its own (never touching band 3 at all) writes the exact same
# `to_band`. These tests pin the fix: a real engagement stamps its own marker at the demotion
# site, carries the numbers the review's action_when_ready needs, and records itself even on a
# night that would otherwise be deduped as "nothing new" — without granting that same exception
# to ordinary drift.
#
# `current=9.0` (p50 2, mad 2, p95 19) is the real 09-09 false-positive number: z=3.5 -> band 3
# pre-guard, <= p95 -> demoted to band 2 (an ENGAGEMENT).
# `current=7.0` is constructed to land at band 2 organically (z=2.5, ratio=3.5, both under the
# band-3 thresholds) — it never touches band 3, so the guard's condition never even evaluates
# true. This is the ordinary night the fix must NOT treat as an engagement.

@pytest.mark.asyncio
async def test_engagement_is_marked_distinguishably(monkeypatch):
    """RED if the `spiky_guard_demoted = True` stamp at the demotion site (system_audit.py,
    ~line 1341) is deleted or never threaded into the detail dict — this then reads
    None/False and the review can never tell an engagement from ordinary drift again."""
    a = await _run(_spec(monkeypatch, current=9.0, last_band=0))
    assert a is not None and a.level == 3
    assert a.body["to_band"] == 2
    assert a.body.get("spiky_guard_demoted") is True


@pytest.mark.asyncio
async def test_organic_band2_is_not_marked_as_engagement(monkeypatch):
    """RED if `spiky_guard_demoted` were set whenever band==2 (or unconditionally) instead of
    only at the actual demotion site — this organic band-2 night (z=2.5, never reaches band 3)
    would then wrongly read as an engagement, recreating the non-discriminating defect from the
    other direction."""
    a = await _run(_spec(monkeypatch, current=7.0, last_band=0))
    assert a is not None
    assert a.body["to_band"] == 2, "sanity: byte-identical to_band to the engaged case above"
    assert not a.body.get("spiky_guard_demoted"), "organic band-2 must not read as an engagement"


@pytest.mark.asyncio
async def test_engagement_carries_baseline_p95_for_action_when_ready(monkeypatch):
    """RED if `detail["baseline_p95"] = p95` is dropped from the L3 branch's guard-only block —
    the review's action_when_ready instructs comparing `current` against `baseline_p95`, which
    would then be missing from the very rows it needs to read."""
    a = await _run(_spec(monkeypatch, current=9.0, p95=19.0, last_band=0))
    assert a.body.get("baseline_p95") == 19.0
    assert a.body["current"] == 9.0


@pytest.mark.asyncio
async def test_engagement_records_even_when_last_band_already_2(monkeypatch):
    """The #633 problem-2 fix: previously `if band == last_band: return None` swallowed an
    engagement whenever yesterday also sat at band 2 — leaving no row at all for the exact
    night the review exists to catch.

    RED if the dedup guard in the L3 branch is reverted from
    `if band == last_band and not spiky_guard_demoted:` back to `if band == last_band:` —
    this then returns None and the engagement leaves no trace, reproducing problem 2."""
    a = await _run(_spec(monkeypatch, current=9.0, last_band=2))
    assert a is not None, "the guard engaged again but wrote nothing — problem 2 is back"
    assert a.body.get("spiky_guard_demoted") is True
    assert a.level == 3, "an engagement must never become a Telegram page"


@pytest.mark.asyncio
async def test_ordinary_same_band_night_still_writes_nothing(monkeypatch):
    """THE LINE: only an actual engagement is new information — an ordinary night that lands on
    the same band as yesterday (no guard involved at all) must keep writing nothing, exactly as
    before #633.

    RED if the new bypass were made unconditional for spiky metrics rather than scoped to an
    actual demotion — e.g. `if band == last_band and not metric.spiky:` — this organic band-2
    repeat (last_band=2, current=7.0, never reaches band 3) would then wrongly gain a nightly
    row it did not have before."""
    a = await _run(_spec(monkeypatch, current=7.0, last_band=2))
    assert a is None, "an ordinary steady-drift night must not gain a new row"


# ── Write-path round trip: _emit_l3 must not silently drop the new fields ───
#
# `_emit_l3` builds its OWN detail dict via explicit `.get()` calls rather than forwarding
# `anomaly.body` wholesale (the same shape #352's L2 fix had to work around) — so a key added
# to `_compute_anomaly`'s detail dict but never threaded into `_emit_l3` never reaches
# `mi_audit_log` at all, even though every in-process test above only inspects `anomaly.body`
# and would stay green. This exercises the actual write.

@pytest.mark.asyncio
async def test_emit_l3_persists_spiky_guard_demoted_and_baseline_p95(monkeypatch):
    """RED if the `if anomaly.body.get("spiky_guard_demoted"): ...` block is removed from
    `_emit_l3` — the marker and baseline_p95 would still exist on `anomaly.body` in this
    process but never make it into the persisted JSON, exactly the silent-drop bug this test
    targets."""
    captured: list[str] = []

    async def _capture_audit(event_type, summary, detail=""):
        captured.append(detail)
    monkeypatch.setattr(sa, "log_audit_event", _capture_audit)

    spec = sa.MetricSpec(name="cooldowns_per_day", fetch_today=None, drill_sql="-- noop", spiky=True)
    body = {
        "current": 9.0, "baseline_p50": 2.0, "mad": 2.0, "sample_n": 21,
        "z_score": 3.5, "ratio": 4.5, "from_band": 0, "to_band": 2,
        "warming": False, "spiky_guard_demoted": True, "baseline_p95": 19.0,
    }
    anomaly = sa.Anomaly(3, spec.name, body)
    await sa._emit_l3(spec, anomaly)

    assert len(captured) == 1
    persisted = json.loads(captured[0])
    assert persisted["to_band"] == 2
    assert persisted.get("spiky_guard_demoted") is True
    assert persisted.get("baseline_p95") == 19.0


@pytest.mark.asyncio
async def test_emit_l3_omits_marker_for_an_ordinary_row(monkeypatch):
    """An ordinary (non-engaged) L3 row must not pick up the marker just by being persisted —
    RED if `_emit_l3` stamped it unconditionally instead of gating on
    `anomaly.body.get("spiky_guard_demoted")`."""
    captured: list[str] = []

    async def _capture_audit(event_type, summary, detail=""):
        captured.append(detail)
    monkeypatch.setattr(sa, "log_audit_event", _capture_audit)

    spec = sa.MetricSpec(name="theme_count_active", fetch_today=None, drill_sql="-- noop")
    body = {
        "current": 30.0, "baseline_p50": 44.0, "mad": 1.0, "sample_n": 21,
        "z_score": -14.0, "ratio": 1.47, "from_band": 0, "to_band": 2, "warming": False,
    }
    anomaly = sa.Anomaly(3, spec.name, body)
    await sa._emit_l3(spec, anomaly)

    persisted = json.loads(captured[0])
    assert "spiky_guard_demoted" not in persisted
    assert "baseline_p95" not in persisted
