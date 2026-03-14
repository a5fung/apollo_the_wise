"""
APScheduler jobs for Market Intelligence Agent.

Schedule (US Eastern Time):
- 6:00 AM ET: Nightly data pull — RS engine + market regime
- 7:00 AM ET: Morning briefing delivery
- 7:00 AM – 9:30 AM ET: EP scan every 5 minutes
- 9:35 AM ET: Stop EP scanning
"""
from __future__ import annotations

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.market_intelligence.rs_engine import run_rs_engine
from agents.market_intelligence.regime import run_regime_engine
from agents.market_intelligence.ep_detector import run_ep_scan
from agents.market_intelligence.briefing import send_morning_briefing, send_ep_alert

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_ep_scan_active = False


async def _nightly_data_pull():
    """Run at 6:00 AM ET. Pull EOD data, calculate RS + regime."""
    logger.info("Nightly data pull starting...")
    try:
        regime_result = await run_regime_engine()
        logger.info(f"Regime: {regime_result.get('regime')}")
    except Exception as e:
        logger.error(f"Regime engine failed: {e}")

    try:
        rs_result = await run_rs_engine()
        logger.info(f"RS engine: scored {rs_result.get('stocks_scored')} stocks")
    except Exception as e:
        logger.error(f"RS engine failed: {e}")

    logger.info("Nightly data pull complete")


async def _morning_briefing_job():
    """Run at 7:00 AM ET. Send morning briefing to Telegram."""
    logger.info("Sending morning briefing...")
    try:
        await send_morning_briefing()
    except Exception as e:
        logger.error(f"Morning briefing failed: {e}")


async def _ep_scan_job():
    """Run every 5 minutes 7:00–9:30 AM ET. Scan for EP gaps."""
    if not _ep_scan_active:
        return
    try:
        eps = await run_ep_scan()
        for ep in eps:
            if ep.get("score_tier") == "HIGH":
                await send_ep_alert(ep)
                logger.info(f"Sent HIGH EP alert: {ep['ticker']}")
    except Exception as e:
        logger.error(f"EP scan failed: {e}")


async def _start_ep_scanning():
    global _ep_scan_active
    _ep_scan_active = True
    logger.info("EP scanning activated")


async def _stop_ep_scanning():
    global _ep_scan_active
    _ep_scan_active = False
    logger.info("EP scanning deactivated")


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="America/New_York")

    # Nightly data pull: 6:00 AM ET (runs on last night's data, Mon-Fri)
    _scheduler.add_job(
        _nightly_data_pull,
        CronTrigger(hour=6, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="nightly_data_pull",
        replace_existing=True,
    )

    # Morning briefing: 7:00 AM ET
    _scheduler.add_job(
        _morning_briefing_job,
        CronTrigger(hour=7, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="morning_briefing",
        replace_existing=True,
    )

    # Start EP scanning at 7:00 AM ET
    _scheduler.add_job(
        _start_ep_scanning,
        CronTrigger(hour=7, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="ep_scan_start",
        replace_existing=True,
    )

    # EP scan: every 5 minutes 7:00–9:30 AM ET
    _scheduler.add_job(
        _ep_scan_job,
        CronTrigger(
            hour="7-9",
            minute="*/5",
            day_of_week="mon-fri",
            timezone="America/New_York",
        ),
        id="ep_scan",
        replace_existing=True,
    )

    # Stop EP scanning at 9:35 AM ET
    _scheduler.add_job(
        _stop_ep_scanning,
        CronTrigger(hour=9, minute=35, day_of_week="mon-fri", timezone="America/New_York"),
        id="ep_scan_stop",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Market Intelligence scheduler started (ET timezone)")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("Scheduler stopped")
