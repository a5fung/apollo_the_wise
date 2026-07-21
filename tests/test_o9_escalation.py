"""#490 O-9 escalation trigger (operator-pinned 2026-07-20: ≥5 residual misses / median fwd-5d ≥ +8%).
The auto-trigger that turns the pre-built cutover runbook from 'armed' into 'fires on evidence'."""
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
async def test_o9_triggers_at_bar(monkeypatch):
    # 5 winning misses, median 10 >= 8 -> TRIGGER
    _wire(monkeypatch, [10.0, 12.0, 9.0, 8.0, 15.0])
    out = await er.evaluate_o9_escalation()
    assert out["count"] == 5 and out["median_fwd5d"] == 10.0 and out["triggered"] is True


@pytest.mark.asyncio
async def test_o9_no_trigger_below_count(monkeypatch):
    # only 4 misses (< O9_MIN_MISSES=5) even though they're big winners -> no trigger
    _wire(monkeypatch, [20.0, 20.0, 20.0, 20.0])
    out = await er.evaluate_o9_escalation()
    assert out["count"] == 4 and out["triggered"] is False


@pytest.mark.asyncio
async def test_o9_no_trigger_faders(monkeypatch):
    # 6 misses but median negative (faders — today's actual state) -> no trigger
    _wire(monkeypatch, [-7.0, -10.0, -3.0, 2.0, -8.0, -5.0])
    out = await er.evaluate_o9_escalation()
    assert out["count"] == 6 and out["median_fwd5d"] < 0 and out["triggered"] is False


@pytest.mark.asyncio
async def test_o9_empty_is_safe(monkeypatch):
    _wire(monkeypatch, [])
    out = await er.evaluate_o9_escalation()
    assert out == {"count": 0, "median_fwd5d": None, "triggered": False}


def test_o9_bar_matches_operator_pin():
    assert er.O9_MIN_MISSES == 5          # operator 2026-07-20: 5, not 10 (EPs are rare)
    assert er.O9_MEDIAN_FWD5D_MIN == 8.0
