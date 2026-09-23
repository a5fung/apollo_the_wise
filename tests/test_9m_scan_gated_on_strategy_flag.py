"""9M's intraday scan must honour its own strategy switch.

Operator, 2026-09-08, on an L2 anomaly paging him about 9M alert volume: "fix it".

`mi_strategies.9m_day2` has been phase='deprecated', enabled=false for weeks, and he has
ruled repeatedly that 9M is gone. The scan job ran every five minutes regardless and wrote
17 rows into mi_9m_ep_alerts that day — enough to trip the anomaly detector and page him
about a lane that cannot place an order.

The defect is structural rather than 9M-specific: a detector ignoring its strategy's master
switch. `should_run` fails OPEN for an unregistered strategy, so gating cannot silently
disable anything else.
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_a_disabled_strategy_means_no_scan():
    """The bug: enabled=false and it scanned anyway."""
    from agents.market_intelligence import scheduler as sch
    ran = AsyncMock()
    with patch.object(sch, "get_market_status", return_value=type("S", (), {"is_trading_day": True})()), \
         patch("agents.market_intelligence.strategies.registry.should_run",
               new=AsyncMock(return_value=False)), \
         patch("agents.market_intelligence.ninem_detector.run_9m_scan", new=ran):
        await sch._9m_scan_job()
    ran.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_enabled_strategy_still_scans():
    """Reviving 9M must revive the scan by data alone — no code change."""
    from agents.market_intelligence import scheduler as sch
    ran = AsyncMock(return_value=[])
    with patch.object(sch, "get_market_status", return_value=type("S", (), {"is_trading_day": True})()), \
         patch("agents.market_intelligence.strategies.registry.should_run",
               new=AsyncMock(return_value=True)), \
         patch("agents.market_intelligence.ninem_detector.run_9m_scan", new=ran):
        await sch._9m_scan_job()
    ran.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_non_trading_day_still_short_circuits_first():
    """The pre-existing guard must keep precedence — the gate is additive."""
    from agents.market_intelligence import scheduler as sch
    ran = AsyncMock()
    with patch.object(sch, "get_market_status", return_value=type("S", (), {"is_trading_day": False})()), \
         patch("agents.market_intelligence.ninem_detector.run_9m_scan", new=ran):
        await sch._9m_scan_job()
    ran.assert_not_awaited()
