"""Persistence dedup for L2 anomalies (2026-06-21).

A band-3 result fires an L2 Telegram on the TRANSITION into band 3. But a benign-but-material
level shift can SIT in band 3 for days — its 30d median is slow to catch up — so it re-fired the
Telegram every nightly run. (theme_count_active -32% across the 2026-06-21 Choppy regime fired L2
four nights running: 38 -> 33 -> 30 -> 30 vs p50 44; the decline is real + material, so the
magnitude guard `_is_slow_drift` correctly leaves it at band 3.)

`_persistent_l2_downgrade` handles the PERSISTENCE axis: fire L2 once on the transition, then
downgrade a persisting band 3 to L3 (audit-only, still in the weekly digest). SCOPED (advisor
2026-06-21) to the STABLE slow-drift class (tight-MAD, non-collapse) so a genuine spike/collapse
or a HIGH-VARIANCE metric's persistent breach (a real pipeline failure / stream disconnect) KEEPS
re-firing daily — you want the day-2 nag there. Mirrors the L3 same-band dedup.
"""
from collections import namedtuple
from datetime import date

import pytest

from agents.market_intelligence import system_audit
from agents.market_intelligence.system_audit import _persistent_l2_downgrade

_FakeStatus = namedtuple("FakeStatus", ["is_trading_day", "reason"])

# theme_count_active-shaped: current 30 vs p50 44, mad 1 -> band 3, ratio 1.47 (material, NOT a
# 5x collapse, tight-MAD). A healthy-variance metric uses mad 4 (9% of p50).
_STABLE = dict(mad=1.0, p50=44.0, ratio=1.47)
_HEALTHY = dict(mad=4.0, p50=44.0, ratio=1.47)
_COLLAPSE = dict(mad=1.0, p50=44.0, ratio=5.5)


# ── Pure decision ────────────────────────────────────────────────────────────

def test_fresh_band3_fires_l2():
    # a transition INTO band 3 (from steady / a lower band) is a fresh alert
    assert _persistent_l2_downgrade(3, 0, **_STABLE) is False
    assert _persistent_l2_downgrade(3, 1, **_STABLE) is False
    assert _persistent_l2_downgrade(3, 2, **_STABLE) is False


def test_persisting_stable_band3_downgrades():
    assert _persistent_l2_downgrade(3, 3, **_STABLE) is True   # tight-MAD slow drift -> L3


def test_persisting_healthy_variance_keeps_firing():
    # the advisor case: a HIGH-variance metric's persistent band-3 is NOT slow drift -> keep nagging
    assert _persistent_l2_downgrade(3, 3, **_HEALTHY) is False


def test_persisting_collapse_keeps_firing():
    # a 5x collapse (real dedup-death / spike) must keep re-firing even when it persists
    assert _persistent_l2_downgrade(3, 3, **_COLLAPSE) is False


def test_non_band3_never_downgrades():
    assert _persistent_l2_downgrade(2, 2, **_STABLE) is False
    assert _persistent_l2_downgrade(1, 3, **_STABLE) is False
    assert _persistent_l2_downgrade(0, 0, **_STABLE) is False


# ── Integration: _compute_anomaly fires once, then downgrades (stable only) ──

def _setup(monkeypatch, *, last_band, current=30.0, mad=1.0):
    monkeypatch.setattr(system_audit, "get_market_status", lambda d: _FakeStatus(True, "t"))
    monkeypatch.setattr(system_audit, "et_today", lambda: date(2026, 6, 21))

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(system_audit, "_record_metric_sample", _noop)

    async def _baseline(*a, **k):
        return {"p50": 44.0, "p95": 54.0, "mad": mad, "sample_n": 21}
    monkeypatch.setattr(system_audit, "get_metric_baseline", _baseline)

    async def _last(*a, **k):
        return last_band
    monkeypatch.setattr(system_audit, "_last_band_for", _last)

    async def _fetch(_conn):
        return current
    return system_audit.MetricSpec(name="theme_count_active", fetch_today=_fetch, drill_sql="-- noop")


@pytest.mark.asyncio
async def test_transition_into_band3_fires_l2(monkeypatch):
    spec = _setup(monkeypatch, last_band=0)
    a = await system_audit._compute_anomaly(conn=None, metric=spec, current_regime=None)
    assert a is not None and a.level == 2                 # L2 Telegram on the transition
    assert a.body["to_band"] == 3                         # recorded so tomorrow can dedup
    assert "persistent_l2_downgrade" not in a.body


@pytest.mark.asyncio
async def test_persisting_stable_band3_downgrades_to_l3(monkeypatch):
    spec = _setup(monkeypatch, last_band=3)
    a = await system_audit._compute_anomaly(conn=None, metric=spec, current_regime=None)
    assert a is not None and a.level == 3                 # downgraded -> no repeat Telegram
    assert a.body.get("persistent_l2_downgrade") is True
    assert a.body["to_band"] == 3


@pytest.mark.asyncio
async def test_persisting_healthy_variance_still_fires_l2(monkeypatch):
    # mad 4 on p50 44 (9%) -> NOT a tight-MAD slow drift. band-3 still by z (-3.5), and it
    # KEEPS firing L2 on day 2 — a real persistent breach should keep nagging.
    spec = _setup(monkeypatch, last_band=3, mad=4.0)
    a = await system_audit._compute_anomaly(conn=None, metric=spec, current_regime=None)
    assert a is not None and a.level == 2
    assert "persistent_l2_downgrade" not in a.body
