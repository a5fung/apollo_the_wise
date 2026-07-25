"""#490 §9.4 O-9 disposition (operator-signed 2026-07-24): the escalation trigger is RETIRED
(the full-RT question is decided) and re-pointed as the RT-4 regression monitor —
`residual_regression_stats` reports the rolling residual count + (cross-basis) median fwd-5d,
with NO 'triggered' verdict and NO escalation Telegram. Post-cutover the count should read ~0;
a sustained nonzero = the overlay is leaking (read by `scheduler._delayed_residual_job`)."""
import pytest

from agents.market_intelligence import ep_delayed_residual as er


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, q, *a):
        return self._rows


class _FakeAcq:
    def __init__(self, conn):
        self._c = conn

    async def __aenter__(self):
        return self._c

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, rows):
        self._rows = rows

    def acquire(self):
        return _FakeAcq(_FakeConn(self._rows))


def _rows(vals):
    return [{"fwd_5d_pct": v} for v in vals]


def _wire(monkeypatch, vals):
    async def _pool():
        return _FakePool(_rows(vals))
    monkeypatch.setattr(er.db, "get_pool", _pool)


@pytest.mark.asyncio
async def test_regression_stats_reports_count_and_median(monkeypatch):
    _wire(monkeypatch, [10.0, 12.0, 9.0, 8.0, 15.0])
    out = await er.residual_regression_stats()
    assert out == {"count": 5, "median_fwd5d": 10.0}


@pytest.mark.asyncio
async def test_regression_stats_empty_is_safe(monkeypatch):
    # RT-4 healthy state: ~0 residual misses post-cutover.
    _wire(monkeypatch, [])
    out = await er.residual_regression_stats()
    assert out == {"count": 0, "median_fwd5d": None}


def test_o9_trigger_is_retired():
    # §9.4: the trigger must NOT come back — no 'triggered' verdict, no threshold constants.
    # (It kept Telegramming "not triggered" on a dead basis against a decided question.)
    assert not hasattr(er, "evaluate_o9_escalation")
    assert not hasattr(er, "O9_MIN_MISSES")
    assert not hasattr(er, "O9_MEDIAN_FWD5D_MIN")


class _JoinConn:
    """rt_shadow_capture_join does two fetches: residual tickers, then catch-event details."""

    def __init__(self, residual, catch_details):
        self._residual = residual
        self._catch = catch_details
        self._calls = 0

    async def fetch(self, q, *a):
        self._calls += 1
        if "mi_ep_delayed_residual" in q:
            return [{"ticker": t} for t in self._residual]
        return [{"detail": d} for d in self._catch]


class _JoinPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcq(self._conn)


@pytest.mark.asyncio
async def test_rt_shadow_capture_join(monkeypatch):
    # 2 residual crossers; only NVVE has a same-day ep_rt_universe_catch -> TRAX is MISSING.
    import json
    conn = _JoinConn(["NVVE", "TRAX"],
                     [json.dumps({"ticker": "NVVE", "rt_gap": 31.8}), "not-json"])

    async def _pool():
        return _JoinPool(conn)
    monkeypatch.setattr(er.db, "get_pool", _pool)
    out = await er.rt_shadow_capture_join("2026-07-24")
    assert out == {"residual_total": 2, "caught_by_rt": 1, "missing": ["TRAX"]}
