"""#256 W2 — the ORB-entry handoff seam (2026-06-13).

`trigger_orb_entry` is the facade wrapper that pre-split ran INLINE inside the
intelligence ep_scan job (scheduler.py:701-709). It is the single most
trade-critical cross-boundary call. inprocess mode MUST route, byte-identically,
to the scheduler's _orb_monitor_job with the same `trigger` — these pin that.
"""
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import execution_client


@pytest.mark.asyncio
async def test_trigger_orb_entry_routes_to_monitor_inprocess(monkeypatch):
    import agents.market_intelligence.scheduler as scheduler
    fake = AsyncMock(return_value="ok")
    monkeypatch.setattr(scheduler, "_orb_monitor_job", fake)

    out = await execution_client.trigger_orb_entry(trigger="post_open_new_high")

    fake.assert_awaited_once_with(trigger="post_open_new_high")
    assert out == "ok"


@pytest.mark.asyncio
async def test_trigger_orb_entry_passes_cron_fallback_trigger(monkeypatch):
    import agents.market_intelligence.scheduler as scheduler
    fake = AsyncMock(return_value=None)
    monkeypatch.setattr(scheduler, "_orb_monitor_job", fake)

    await execution_client.trigger_orb_entry(trigger="cron_9_31")

    fake.assert_awaited_once_with(trigger="cron_9_31")
