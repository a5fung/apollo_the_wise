"""Tests for the #455 R4 stage-1 intraday drawdown-crossing check (2026-07-16).

ALERT-ONLY piggyback on the 15-min order-status-reconcile cycle. Pins:
  - a WATCH/REDUCE crossing fires ONE Telegram + ONE audit row, once per
    (tier, ET day) — the audit log is the dedup state
  - a deeper crossing (WATCH → REDUCE same day) still alerts; recovery back
    into a shallower band after a deeper alert does NOT (subsumption)
  - the persisted breaker state suppresses same-or-shallower "crossings"
    (a multi-day WATCH drawdown must not re-alert every morning)
  - no crossing / insufficient history / paper-only deployment → silent
  - failure isolation: run_intraday_drawdown_check never raises; repeated
    consecutive failures emit ONE intraday_drawdown_check_failed audit row;
    an exception in the piggyback never breaks the reconcile job

Run: pytest tests/test_intraday_drawdown.py -v
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.audit_events import (
    INTRADAY_DRAWDOWN_CHECK_FAILED,
    INTRADAY_DRAWDOWN_CROSSING,
)
from agents.market_intelligence.broker import intraday_drawdown as idd
from agents.market_intelligence.broker.drawdown_breaker import DrawdownState
from tests.conftest import make_mock_pool


def _dd_state(drawdown_pct: float, sufficient_history: bool = True) -> DrawdownState:
    return DrawdownState(
        current=100_000.0 * (1 + drawdown_pct),
        peak=100_000.0,
        peak_date=date(2026, 7, 1),
        drawdown_pct=drawdown_pct,
        snapshots_count=30,
        most_recent_snapshot_date=date(2026, 7, 15),
        sufficient_history=sufficient_history,
    )


@pytest.fixture(autouse=True)
def _reset_failure_counter():
    idd._consecutive_failures = 0
    yield
    idd._consecutive_failures = 0


class _Harness:
    """Fake audit log + telegram around run_intraday_drawdown_check.

    The audit store backs BOTH log_audit_event (writes) and the dedup
    query's conn.fetch (reads) — exercising the audit-log-as-state design
    for real instead of mocking _already_alerted_today.
    """

    def __init__(self, drawdown_pct=0.0, persisted_state="OK",
                 sufficient_history=True, modes=("paper", "live")):
        self.audit_rows: list[dict] = []
        self.sent: list[str] = []
        self.drawdown_pct = drawdown_pct
        self.persisted_state = persisted_state
        self.sufficient_history = sufficient_history
        self.modes = list(modes)
        self.compute_calls = 0

    async def fake_compute(self, mode):
        assert mode == "live"  # stage-1 scope pin
        self.compute_calls += 1
        return _dd_state(self.drawdown_pct, self.sufficient_history)

    async def fake_read_state(self, mode):
        return self.persisted_state

    async def fake_audit(self, event_type, summary, detail=""):
        self.audit_rows.append(
            {"event_type": event_type, "summary": summary, "detail": detail})

    async def fake_send(self, msg, **kwargs):
        self.sent.append(msg)
        return True

    def crossing_rows(self):
        return [r for r in self.audit_rows
                if r["event_type"] == INTRADAY_DRAWDOWN_CROSSING]

    async def run(self):
        pool, conn = make_mock_pool()

        async def fake_fetch(query, event_type, today):
            # Dedup read: same-ET-day crossing rows (store is one day).
            return [{"summary": r["summary"]} for r in self.audit_rows
                    if r["event_type"] == event_type]

        conn.fetch = AsyncMock(side_effect=fake_fetch)

        with patch.object(idd, "compute_drawdown_state", self.fake_compute), \
             patch.object(idd, "read_breaker_state", self.fake_read_state), \
             patch.object(idd, "log_audit_event", self.fake_audit), \
             patch.object(idd, "get_pool", AsyncMock(return_value=pool)), \
             patch.object(idd, "active_account_modes", lambda: self.modes), \
             patch("agents.market_intelligence.briefing.send_telegram_message",
                   self.fake_send):
            return await idd.run_intraday_drawdown_check()


# ── Crossing fires once per day per tier ─────────────────────────────────


@pytest.mark.asyncio
async def test_watch_crossing_fires_once_per_day():
    h = _Harness(drawdown_pct=-0.05)  # crosses WATCH (-4%), not REDUCE (-7%)
    assert await h.run() == "WATCH"
    assert len(h.sent) == 1 and "WATCH" in h.sent[0]
    assert len(h.crossing_rows()) == 1
    assert "tier=WATCH" in h.crossing_rows()[0]["summary"]

    # Same tier, same day → silent (audit row is the dedup state).
    assert await h.run() is None
    assert len(h.sent) == 1
    assert len(h.crossing_rows()) == 1


@pytest.mark.asyncio
async def test_deepening_to_reduce_alerts_after_watch_same_day():
    h = _Harness(drawdown_pct=-0.05)
    assert await h.run() == "WATCH"

    h.drawdown_pct = -0.08  # deepens across the REDUCE trip
    assert await h.run() == "REDUCE"
    assert len(h.sent) == 2 and "REDUCE" in h.sent[1]
    assert len(h.crossing_rows()) == 2

    # REDUCE re-read same day → silent.
    assert await h.run() is None
    assert len(h.sent) == 2


@pytest.mark.asyncio
async def test_reduce_alert_subsumes_later_watch_band_reading():
    """Recovery direction is not a crossing: after a REDUCE alert, drifting
    back up into the WATCH band the same day stays silent."""
    h = _Harness(drawdown_pct=-0.08)
    assert await h.run() == "REDUCE"

    h.drawdown_pct = -0.05  # back inside the WATCH band
    assert await h.run() is None
    assert len(h.sent) == 1
    assert len(h.crossing_rows()) == 1


@pytest.mark.asyncio
async def test_block_depth_drawdown_surfaces_as_reduce_tier():
    """Stage-1 vocabulary is WATCH/REDUCE only; a BLOCK-depth intraday dd
    alerts as a REDUCE crossing carrying the raw dd% in the message."""
    h = _Harness(drawdown_pct=-0.15)
    assert await h.run() == "REDUCE"
    assert "-15.00%" in h.sent[0]


# ── Silent paths ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_crossing_silent():
    h = _Harness(drawdown_pct=-0.02)  # inside OK band
    assert await h.run() is None
    assert h.sent == [] and h.audit_rows == []


@pytest.mark.asyncio
async def test_insufficient_history_silent():
    """Mirrors the breaker's min-history / stale-snapshot fail-open."""
    h = _Harness(drawdown_pct=-0.09, sufficient_history=False)
    assert await h.run() is None
    assert h.sent == [] and h.audit_rows == []


@pytest.mark.asyncio
async def test_paper_only_deployment_noop():
    """ENABLE_LIVE_MODE=false deployments never touch the account."""
    h = _Harness(drawdown_pct=-0.09, modes=("paper",))
    assert await h.run() is None
    assert h.compute_calls == 0
    assert h.sent == [] and h.audit_rows == []


# ── Persisted breaker state suppresses known tiers ───────────────────────


@pytest.mark.asyncio
async def test_persisted_watch_suppresses_watch_crossing():
    """The EOD breaker already holds WATCH → an intraday WATCH-band reading
    is not a crossing (prevents daily re-alerts through a multi-day dd)."""
    h = _Harness(drawdown_pct=-0.05, persisted_state="WATCH")
    assert await h.run() is None
    assert h.sent == [] and h.audit_rows == []


@pytest.mark.asyncio
async def test_persisted_watch_still_alerts_deeper_reduce():
    h = _Harness(drawdown_pct=-0.08, persisted_state="WATCH")
    assert await h.run() == "REDUCE"
    assert len(h.sent) == 1


@pytest.mark.asyncio
async def test_legacy_tripped_state_suppresses_reduce():
    """Legacy 'TRIPPED' maps to REDUCE depth (same as _next_state's
    migration) — a REDUCE-band reading under it is not a crossing."""
    h = _Harness(drawdown_pct=-0.08, persisted_state="TRIPPED")
    assert await h.run() is None
    assert h.sent == []


# ── Failure isolation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_never_raises_and_audits_after_repeated_failures():
    audited = []

    async def fake_audit(event_type, summary, detail=""):
        audited.append(event_type)

    async def boom(mode):
        raise RuntimeError("alpaca exploded")

    with patch.object(idd, "compute_drawdown_state", boom), \
         patch.object(idd, "log_audit_event", fake_audit), \
         patch.object(idd, "active_account_modes", lambda: ["paper", "live"]):
        # Never raises; log-only below the threshold.
        assert await idd.run_intraday_drawdown_check() is None
        assert await idd.run_intraday_drawdown_check() is None
        assert audited == []
        # 3rd consecutive failure → ONE audit row, counter resets.
        assert await idd.run_intraday_drawdown_check() is None
        assert audited == [INTRADAY_DRAWDOWN_CHECK_FAILED]
        assert idd._consecutive_failures == 0


@pytest.mark.asyncio
async def test_compute_returning_none_counts_as_failure_not_raise():
    """compute_drawdown_state returns None on an account-fetch failure (it
    doesn't raise) — the check treats that as a failure, silently."""
    async def fake_compute(mode):
        return None

    with patch.object(idd, "compute_drawdown_state", fake_compute), \
         patch.object(idd, "log_audit_event", AsyncMock()), \
         patch.object(idd, "active_account_modes", lambda: ["paper", "live"]):
        assert await idd.run_intraday_drawdown_check() is None
        assert idd._consecutive_failures == 1


@pytest.mark.asyncio
async def test_success_resets_failure_counter():
    h = _Harness(drawdown_pct=-0.02)
    idd._consecutive_failures = 2
    assert await h.run() is None  # clean no-crossing evaluation
    assert idd._consecutive_failures == 0


@pytest.mark.asyncio
async def test_reconcile_job_survives_piggyback_failure():
    """An exception from the intraday check must never break the 15-min
    reconcile job (job-level belt-and-braces try/except)."""
    from agents.market_intelligence import scheduler

    async def boom():
        raise RuntimeError("piggyback exploded")

    reconcile_result = {"examined": 3, "updated": 1, "errors": 0}
    notify = AsyncMock()

    with patch("agents.market_intelligence.broker.order_manager.reconcile_all_modes",
               AsyncMock(return_value=reconcile_result)), \
         patch("agents.market_intelligence.broker.coverage_drift.detect_coverage_drift",
               AsyncMock(return_value=None)), \
         patch("agents.market_intelligence.broker.intraday_drawdown.run_intraday_drawdown_check",
               boom), \
         patch.object(scheduler, "notify_job_failure", notify):
        result = await scheduler._order_status_reconcile_job(lookback_days=1)

    assert result == 1  # the reconcile's own result survives the piggyback failure
    notify.assert_not_called()


@pytest.mark.asyncio
async def test_open_window_variant_skips_intraday_check():
    """The #150 1-minute open-window variant (run_coverage_drift=False) must
    not run the intraday check (~10 extra get_account calls each morning)."""
    from agents.market_intelligence import scheduler

    check = AsyncMock()
    with patch("agents.market_intelligence.broker.order_manager.reconcile_all_modes",
               AsyncMock(return_value={"examined": 0, "updated": 0, "errors": 0})), \
         patch("agents.market_intelligence.broker.intraday_drawdown.run_intraday_drawdown_check",
               check):
        await scheduler._order_status_reconcile_job(
            lookback_days=1, run_coverage_drift=False)

    check.assert_not_called()
