"""Fix-3 (2026-07-14) — deprecated 9M Day 2: no scan, no skip-digest.

The 9m_day2 strategy is operator-DEPRECATED (#424, terminal). The entry
pipeline already blocks each candidate (block:strategy_deprecated), but the
9:31 ET `_9m_day2_orb_job` kept scanning, skipping everything, and Telegramming
a daily "⏭️ 9M Day2 skips" digest for a retired strategy — pure noise. The gate
short-circuits the WHOLE job when the strategy registry reports
phase == 'deprecated', and is FAIL-OPEN: a registry error runs the job as
before (the pipeline's deprecated block is the noisy-but-safe backstop).

Scope pin: ONLY `_9m_day2_orb_job` is gated — the intraday 9M scan
(`_9m_scan_job`), the sugar-babies cohort refresh, and every MAGNA53 path are
untouched (verified here by the control test exercising the same job with a
non-deprecated phase).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

# Alpaca SDK + backtester.filters stubbing handled by tests/conftest.py.


@pytest.fixture
def wire(monkeypatch):
    """Common wiring: trading day + live trading enabled + spies on the
    candidate scan, Telegram, and job-failure notifier."""
    import agents.market_intelligence.scheduler as sched
    import agents.market_intelligence.constants as constants
    import agents.market_intelligence.db as db_mod

    monkeypatch.setattr(constants, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(sched, "get_market_status",
                        lambda d: SimpleNamespace(is_trading_day=True))

    calls = {"scan": [], "telegram": [], "job_failure": []}

    async def _fake_pending(day):
        calls["scan"].append(day)
        return []   # control path: no candidates → job exits right after

    async def _fake_send(msg, *a, **k):
        calls["telegram"].append(msg)
        return True

    async def _fake_notify(job, err):
        calls["job_failure"].append((job, err))

    monkeypatch.setattr(db_mod, "get_pending_9m_sugar_babies", _fake_pending)
    monkeypatch.setattr(sched, "send_telegram_message", _fake_send)
    monkeypatch.setattr(sched, "notify_job_failure", _fake_notify)
    return calls


def _set_strategy(monkeypatch, phase_or_exc):
    import agents.market_intelligence.strategies.registry as registry

    async def _get_strategy(strategy_id):
        assert strategy_id == "9m_day2"   # the gate must look up THIS strategy
        if isinstance(phase_or_exc, Exception):
            raise phase_or_exc
        if phase_or_exc is None:
            return None
        return SimpleNamespace(phase=phase_or_exc)

    monkeypatch.setattr(registry, "get_strategy", _get_strategy)


@pytest.mark.asyncio
async def test_deprecated_9m_day2_no_scan_no_digest(wire, monkeypatch):
    # THE fix: deprecated → the job short-circuits BEFORE the candidate scan;
    # nothing is fetched, nothing is Telegrammed (no skip-digest, no
    # reserved-for-HIGH-EPs message), and the gate itself never errors.
    import agents.market_intelligence.scheduler as sched
    _set_strategy(monkeypatch, "deprecated")

    await sched._9m_day2_orb_job()

    assert wire["scan"] == []          # candidate scan never ran
    assert wire["telegram"] == []      # no digest / no reserve Telegram
    assert wire["job_failure"] == []   # clean short-circuit, not a crash


@pytest.mark.asyncio
async def test_non_deprecated_9m_day2_still_scans(wire, monkeypatch):
    # Control: any non-terminal phase runs the job exactly as before —
    # the gate must not block a live/paper/shadow strategy.
    import agents.market_intelligence.scheduler as sched
    _set_strategy(monkeypatch, "live")

    await sched._9m_day2_orb_job()

    assert len(wire["scan"]) == 1      # job proceeded to the candidate fetch
    assert wire["telegram"] == []      # no candidates → nothing sent (as before)


@pytest.mark.asyncio
async def test_registry_error_fails_open_to_running(wire, monkeypatch):
    # FAIL-OPEN: a registry lookup failure must NEVER block the job — the
    # entry pipeline's own deprecated block remains the backstop.
    import agents.market_intelligence.scheduler as sched
    _set_strategy(monkeypatch, RuntimeError("registry down"))

    await sched._9m_day2_orb_job()

    assert len(wire["scan"]) == 1


@pytest.mark.asyncio
async def test_missing_strategy_row_fails_open_to_running(wire, monkeypatch):
    # No mi_strategies row (get_strategy → None) → run as before; only a
    # POSITIVE 'deprecated' phase short-circuits.
    import agents.market_intelligence.scheduler as sched
    _set_strategy(monkeypatch, None)

    await sched._9m_day2_orb_job()

    assert len(wire["scan"]) == 1
