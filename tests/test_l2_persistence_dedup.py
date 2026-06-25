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
import json
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

def _setup(monkeypatch, *, last_band, current=30.0, mad=1.0, recent_stable=False):
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

    async def _recent(*a, **k):
        return recent_stable
    monkeypatch.setattr(system_audit, "_recent_window_stable", _recent)

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


# ── Write-path round-trip: _emit_l2 persists to_band, _last_band_for reads it (#352) ──
#
# The decision-level tests above mock `_last_band_for` to return last_band directly, so they
# never touch `_emit_l2` — the actual bug surface. #352: the L2 audit row's `detail` JSON was
# missing `to_band` (only the L3 path wrote it), so the next nightly run's `_last_band_for`
# read the prior L2 row, found no `to_band`, returned 0, and the persistence dedup could never
# recognize a still-same-band L2 -> it re-fired the Telegram every night (6/12->6/22 in prod).
# This test exercises the real write -> store -> read round trip end to end.


class _FakeConn:
    """Stand-in for an asyncpg conn: returns the most-recent captured audit row to
    `_last_band_for`, mirroring `SELECT detail ... ORDER BY created_at DESC LIMIT 1`."""

    def __init__(self, rows):
        self._rows = rows  # list of detail-JSON strings, oldest-first

    async def fetchrow(self, *_args, **_kwargs):
        if not self._rows:
            return None
        return {"detail": self._rows[-1]}


def _l2_spec():
    async def _fetch(_conn):
        return 30.0
    return system_audit.MetricSpec(
        name="theme_count_active", fetch_today=_fetch, drill_sql="-- noop"
    )


@pytest.mark.asyncio
async def test_emit_l2_persists_to_band_then_last_band_reads_it(monkeypatch):
    # 1) Fire a fresh band-3 L2 (transition into band 3): _emit_l2 must write to_band=3.
    captured: list[str] = []

    async def _capture_audit(event_type, summary, detail=""):
        captured.append(detail)
    monkeypatch.setattr(system_audit, "log_audit_event", _capture_audit)

    async def _zero(*a, **k):
        return 0
    monkeypatch.setattr(system_audit, "count_today_anomalies", _zero)

    async def _send_ok(_text):
        return True

    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _send_ok)

    spec = _l2_spec()
    body = {
        "current": 30.0, "baseline_p50": 44.0, "baseline_p95": 54.0,
        "mad": 1.0, "sample_n": 21, "z_score": -14.0, "ratio": 1.47,
        "regime_conditional": False,
        "to_band": 3,  # set by _compute_anomaly's band-3 branch — must survive into the row
    }
    anomaly = system_audit.Anomaly(2, spec.name, body)
    await system_audit._emit_l2(spec, anomaly, event_deltas=[])

    assert len(captured) == 1
    persisted = json.loads(captured[0])
    assert persisted["level"] == 2
    assert persisted["key"] == "theme_count_active"
    assert persisted["to_band"] == 3, "L2 audit row must carry to_band for the dedup to work"

    # 2) The next nightly run reads that row back via the REAL _last_band_for parse and must
    #    recover band 3 — proving written + read line up on the same key.
    conn = _FakeConn(captured)
    last = await system_audit._last_band_for(conn, spec.name)
    assert last == 3

    # 3) End to end: with last_band=3 recovered, a still-band-3 L2 downgrades to L3 (no repeat
    #    Telegram). This is the fire-once-then-quiet behavior the missing to_band defeated.
    monkeypatch.setattr(system_audit, "get_market_status", lambda d: _FakeStatus(True, "t"))
    monkeypatch.setattr(system_audit, "et_today", lambda: date(2026, 6, 22))

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(system_audit, "_record_metric_sample", _noop)

    async def _baseline(*a, **k):
        return {"p50": 44.0, "p95": 54.0, "mad": 1.0, "sample_n": 21}
    monkeypatch.setattr(system_audit, "get_metric_baseline", _baseline)

    async def _recent_noop(*a, **k):
        return False
    monkeypatch.setattr(system_audit, "_recent_window_stable", _recent_noop)

    a2 = await system_audit._compute_anomaly(conn=conn, metric=spec, current_regime=None)
    assert a2 is not None and a2.level == 3
    assert a2.body.get("persistent_l2_downgrade") is True
    assert a2.body["to_band"] == 3


# ── Settled level-shift (#352 fix-2): a DECLINING metric whose wide 30d MAD masks a TIGHT ──
# ── recent window has settled at a new normal -> downgrade, even when the stable gate fails. ──


@pytest.mark.asyncio
async def test_settled_level_shift_downgrades_to_l3(monkeypatch):
    # mad 4 (wide full-window -> _persistent_l2_downgrade=False) BUT recent window is settled.
    # This is the theme_count #286/#325 case: declined, full-window MAD grew, recent is tight.
    spec = _setup(monkeypatch, last_band=3, mad=4.0, recent_stable=True)
    a = await system_audit._compute_anomaly(conn=None, metric=spec, current_regime=None)
    assert a is not None and a.level == 3
    assert a.body.get("settled_level_shift") is True
    assert a.body.get("persistent_l2_downgrade") is True


@pytest.mark.asyncio
async def test_settled_but_transition_still_fires_l2(monkeypatch):
    # recent-stable but FIRST fire (last_band != 3): the transition INTO band 3 still alerts once.
    spec = _setup(monkeypatch, last_band=0, mad=4.0, recent_stable=True)
    a = await system_audit._compute_anomaly(conn=None, metric=spec, current_regime=None)
    assert a is not None and a.level == 2
    assert "settled_level_shift" not in a.body


@pytest.mark.asyncio
async def test_settled_but_collapse_still_fires_l2(monkeypatch):
    # recent-stable + persisting, but a collapse (current 5 vs p50 44 -> ratio ~8.8) is NOT
    # downgraded — a real collapse keeps re-firing even if the recent window happens to be tight.
    spec = _setup(monkeypatch, last_band=3, current=5.0, mad=4.0, recent_stable=True)
    a = await system_audit._compute_anomaly(conn=None, metric=spec, current_regime=None)
    assert a is not None and a.level == 2
    assert "settled_level_shift" not in a.body


# ── _recent_window_stable unit (mocks _fetch_history's recent window) ──


@pytest.mark.asyncio
async def test_recent_window_stable_true_on_tight_settled(monkeypatch):
    async def _hist(_conn, _metric, *, lookback_days):
        return [17.0, 18.0, 17.0, 16.0, 18.0, 17.0]  # settled ~17, tight
    monkeypatch.setattr(system_audit, "_fetch_history", _hist)
    assert await system_audit._recent_window_stable(None, _l2_spec()) is True


@pytest.mark.asyncio
async def test_recent_window_unstable_on_wide(monkeypatch):
    async def _hist(_conn, _metric, *, lookback_days):
        return [42.0, 17.0, 50.0, 15.0, 40.0, 20.0]  # still swinging -> wide
    monkeypatch.setattr(system_audit, "_fetch_history", _hist)
    assert await system_audit._recent_window_stable(None, _l2_spec()) is False


@pytest.mark.asyncio
async def test_recent_window_stuck_at_zero_not_stable(monkeypatch):
    async def _hist(_conn, _metric, *, lookback_days):
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # a real outage -> p50==0 -> keeps alerting
    monkeypatch.setattr(system_audit, "_fetch_history", _hist)
    assert await system_audit._recent_window_stable(None, _l2_spec()) is False


@pytest.mark.asyncio
async def test_recent_window_too_few_samples(monkeypatch):
    async def _hist(_conn, _metric, *, lookback_days):
        return [17.0, 17.0, 18.0]  # < 5 -> not enough to call it settled
    monkeypatch.setattr(system_audit, "_fetch_history", _hist)
    assert await system_audit._recent_window_stable(None, _l2_spec()) is False
