"""
APScheduler jobs for Market Intelligence Agent.

Schedule (US Eastern Time / Pacific Time):
- 4:30 PM ET (1:30 PM PT): Nightly data pull — RS engine + market regime + themes
- 6:00 PM ET (3:00 PM PT): Evening briefing — regime + RS leaders + themes + MA pullbacks
- 7:00 AM – 10:00 AM ET (4:00 – 7:00 AM PT): EP scan every 5 minutes; HIGH alerts sent immediately
- 9:00 AM ET (6:00 AM PT): Morning briefing — EP recap + regime context (30 min before open)
- 10:00 AM ET (7:00 AM PT): Stop EP scanning
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.market_intelligence.db import (
    purge_old_data, log_job_run, job_ran_today, upsert_fundamental_flags_batch,
    get_rs_leaders, update_sectors_batch,
)
from agents.market_intelligence.rs_engine import run_rs_engine, ingest_daily
from agents.market_intelligence.regime import run_regime_engine
from agents.market_intelligence.theme_engine import run_theme_engine
from agents.market_intelligence.ep_detector import run_ep_scan
from agents.market_intelligence.fundamentals import compute_fundamental_flags
from agents.market_intelligence.data_quality import (
    check_ingest_quality,
    check_rs_quality,
    check_sector_quality,
)
from agents.market_intelligence.outcome_tracker import run_outcome_tracker
from agents.market_intelligence.state_alerts import detect_state_changes, send_state_alerts
from agents.market_intelligence.briefing import (
    send_morning_briefing,
    send_evening_briefing,
    send_ep_alert,
    send_telegram_message,
)
from core.notifications import notify_job_failure, notify_job_success

logger = logging.getLogger(__name__)

# Job name constants — used in mi_job_log; must match exactly
JOB_NIGHTLY_DATA_PULL = "nightly_data_pull"
JOB_EVENING_BRIEFING = "evening_briefing"
JOB_MORNING_BRIEFING = "morning_briefing"

_scheduler: AsyncIOScheduler | None = None
_ep_scan_active = False


async def _nightly_data_pull():
    """
    Run at 4:30 PM ET (right after market close).
    Order: ingest → RS → regime → sector → themes → fundamentals → outcomes → state alerts.
    Regime runs after RS so breadth_full() can use stored mi_stock_scores.
    """
    logger.info("Nightly data pull starting...")
    from datetime import date as _date_cls
    _today = _date_cls.today()
    today_str = _today.strftime("%Y-%m-%d")
    failures = []
    summary_parts = []
    ingested = 0
    scored = 0

    # 1. Ingest today's daily closes (1 Polygon call → all stocks)
    try:
        ingested = await ingest_daily()
        logger.info(f"Daily closes ingested: {ingested} tickers")
        await check_ingest_quality(ingested, _today)
    except Exception as e:
        logger.error(f"Daily close ingestion failed: {e}")
        failures.append(f"Daily ingestion: {e}")

    # 2. RS engine — scores, SMAs, raw returns
    try:
        rs_result = await run_rs_engine()
        scored = rs_result.get("stocks_scored", 0)
        logger.info(f"RS engine: scored {scored} stocks")
        summary_parts.append(f"{scored} stocks scored")
        await check_rs_quality(scored, _today)
    except Exception as e:
        logger.error(f"RS engine failed: {e}")
        failures.append(f"RS engine: {e}")

    # 3. Regime engine — now can use full-universe breadth from stored data
    try:
        regime_result = await run_regime_engine()
        regime = regime_result.get("regime", "?")
        logger.info(f"Regime: {regime}")
        summary_parts.append(f"regime={regime}")
    except Exception as e:
        logger.error(f"Regime engine failed: {e}")
        failures.append(f"Regime: {e}")

    # 4. Sector enrichment — fetch sector for top RS stocks so biotech/pharma filter works
    try:
        from agents.market_intelligence.collector import get_fmp_profile
        top_for_sector = await get_rs_leaders(today_str, limit=200, min_adv=0, min_price=0)
        sector_sem = asyncio.Semaphore(5)
        sector_map: dict[str, str] = {}
        async def _fetch_sector(ticker: str):
            async with sector_sem:
                profile = await get_fmp_profile(ticker)
                s = profile.get("sector")
                if s:
                    sector_map[ticker] = s
        await asyncio.gather(*[_fetch_sector(s["ticker"]) for s in top_for_sector if not s.get("sector")])
        if sector_map:
            updated = await update_sectors_batch(_today, sector_map)
            logger.info(f"Sector enrichment: updated {updated} tickers")
            summary_parts.append(f"{updated} sectors")

        # Data quality: sector coverage check
        with_sector = sum(1 for s in top_for_sector if s.get("sector"))
        total_top = len(top_for_sector)
        if total_top > 0:
            await check_sector_quality(with_sector, total_top, _today)
    except Exception as e:
        logger.error(f"Sector enrichment failed: {e}")

    # 4b. Quote type enrichment — classify tracked stocks as EQUITY/ETF/etc.
    try:
        from agents.market_intelligence.db import (
            get_tracked_tickers_missing_quote_type, update_quote_types_batch,
        )
        missing_qt = await get_tracked_tickers_missing_quote_type(limit=50)
        if missing_qt:
            from agents.market_intelligence.collector import get_fmp_profile
            qt_map: dict[str, str] = {}
            qt_sem = asyncio.Semaphore(5)
            async def _fetch_qt(ticker: str):
                async with qt_sem:
                    try:
                        import yfinance as yf
                        loop = asyncio.get_event_loop()
                        info = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info)
                        qt = info.get("quoteType", "EQUITY")
                        qt_map[ticker] = qt
                    except Exception:
                        qt_map[ticker] = "EQUITY"  # assume equity if lookup fails
            await asyncio.gather(*[_fetch_qt(tk) for tk in missing_qt])
            if qt_map:
                await update_quote_types_batch(qt_map)
                n_etf = sum(1 for v in qt_map.values() if v != "EQUITY")
                logger.info(f"Quote type enrichment: classified {len(qt_map)} tickers ({n_etf} non-equity)")
    except Exception as e:
        logger.error(f"Quote type enrichment failed: {e}")

    # 5. Theme engine
    theme_changelog: list[dict] = []
    try:
        themes, theme_changelog = await run_theme_engine()
        logger.info(f"Theme engine: {len(themes)} themes identified, {len(theme_changelog)} changes")
        summary_parts.append(f"{len(themes)} themes")
    except Exception as e:
        logger.error(f"Theme engine failed: {e}")
        failures.append(f"Theme engine: {e}")

    # 6. Fundamental flags — fetch for top RS stocks + theme constituents
    try:
        from agents.market_intelligence.db import get_active_themes
        rs_leaders = await get_rs_leaders(today_str, limit=40)
        fund_tickers = {s["ticker"] for s in rs_leaders}
        try:
            active_themes = await get_active_themes()
            for t in active_themes:
                for tk in (t.get("tickers") or []):
                    fund_tickers.add(tk)
        except Exception:
            pass
        fund_list = list(fund_tickers)[:80]
        if fund_list:
            flag_records = await compute_fundamental_flags(fund_list, _today)
            await upsert_fundamental_flags_batch(flag_records)
            logger.info(f"Fundamental flags: cached {len(flag_records)} tickers")
            summary_parts.append(f"{len(flag_records)} fund flags")
    except Exception as e:
        logger.error(f"Fundamental flags failed: {e}")

    # 7. Signal outcome tracker
    try:
        outcome_result = await run_outcome_tracker(_today)
        total_outcomes = outcome_result.get("total", 0)
        if total_outcomes:
            logger.info(f"Outcome tracker: {total_outcomes} outcomes computed")
            summary_parts.append(f"{total_outcomes} outcomes")
    except Exception as e:
        logger.error(f"Outcome tracker failed: {e}")

    # 8. State-change alerts (sent immediately via Telegram)
    try:
        alerts = await detect_state_changes(_today)
        if alerts or theme_changelog:
            await send_state_alerts(alerts, theme_changelog)
            total_alerts = len(alerts) + len(theme_changelog)
            logger.info(f"State alerts: {total_alerts} alerts sent")
            summary_parts.append(f"{total_alerts} state alerts")
    except Exception as e:
        logger.error(f"State alerts failed: {e}")

    if failures:
        await notify_job_failure(JOB_NIGHTLY_DATA_PULL, " | ".join(failures))
    else:
        await log_job_run(JOB_NIGHTLY_DATA_PULL)
        await notify_job_success(JOB_NIGHTLY_DATA_PULL, ", ".join(summary_parts))

    logger.info("Nightly data pull complete")


async def _evening_briefing_job():
    """Run at 8:00 PM ET (5:00 PM PT). Send evening briefing — full EOD review package."""
    logger.info("Sending evening briefing...")
    try:
        await send_evening_briefing()
        await log_job_run(JOB_EVENING_BRIEFING)
    except Exception as e:
        import traceback
        logger.error(f"Evening briefing failed: {e}\n{traceback.format_exc()}")
        await notify_job_failure(JOB_EVENING_BRIEFING, str(e))


async def _morning_briefing_job():
    """Run at 9:00 AM ET (6:00 AM PT). Send morning briefing — EP recap + regime context."""
    logger.info("Sending morning briefing...")
    try:
        await send_morning_briefing()
        await log_job_run(JOB_MORNING_BRIEFING)
    except Exception as e:
        import traceback
        logger.error(f"Morning briefing failed: {e}\n{traceback.format_exc()}")
        await notify_job_failure(JOB_MORNING_BRIEFING, str(e))


async def _ep_scan_job():
    """Run every 5 minutes 7:00–9:30 AM ET. Scan for EP gaps; HIGH alerts sent immediately."""
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


async def _weekly_cleanup():
    """Run Sunday 2:00 AM ET. Purge old rows per retention policy."""
    logger.info("Weekly DB cleanup starting...")
    try:
        deleted = await purge_old_data()
        summary = "  ".join(f"{t.split('_',1)[1]}: -{n}" for t, n in deleted.items())
        await notify_job_success("weekly_cleanup", summary or "nothing to purge")
    except Exception as e:
        logger.error(f"Weekly cleanup failed: {e}")
        await notify_job_failure("weekly_cleanup", str(e))


async def _start_ep_scanning():
    global _ep_scan_active
    _ep_scan_active = True
    logger.info("EP scanning activated")


async def _stop_ep_scanning():
    global _ep_scan_active
    _ep_scan_active = False
    logger.info("EP scanning deactivated")


async def check_missed_jobs() -> None:
    """
    On startup, send any briefings that were missed while the machine was off.

    Catch-up windows (ET):
    - Morning briefing:  09:00 – 12:00  (fires if missed and we start in that window)
    - Nightly data pull: 16:30 – 18:00  (fires if missed and we start in that window)
    - Evening briefing:  18:00 – 23:59  (fires if missed and we start in that window)

    Each job is only caught up once per day (guarded by mi_job_log).
    Weekdays only.
    """
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)

    if now.weekday() >= 5:  # Saturday / Sunday
        return

    hour = now.hour

    # Morning briefing: 9 AM – noon ET
    if 9 <= hour < 12:
        if not await job_ran_today(JOB_MORNING_BRIEFING):
            logger.info("Catch-up: sending missed morning briefing")
            await send_telegram_message("_(Missed briefing — sending now)_")
            await _morning_briefing_job()

    # Nightly data pull: 4:30 PM – 6 PM ET
    if (hour == 16 and now.minute >= 30) or (hour == 17):
        if not await job_ran_today(JOB_NIGHTLY_DATA_PULL):
            logger.info("Catch-up: running missed nightly data pull")
            await _nightly_data_pull()

    # Evening briefing: 6 PM – midnight ET
    if 18 <= hour < 24:
        # Check both jobs concurrently before deciding what to run
        data_ran, brief_ran = await asyncio.gather(
            job_ran_today(JOB_NIGHTLY_DATA_PULL),
            job_ran_today(JOB_EVENING_BRIEFING),
        )
        if not data_ran:
            logger.info("Catch-up: running missed nightly data pull before evening briefing")
            await _nightly_data_pull()
        if not brief_ran:
            logger.info("Catch-up: sending missed evening briefing")
            await send_telegram_message("_(Missed briefing — sending now)_")
            await _evening_briefing_job()


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="America/New_York")

    # Data pull: 4:30 PM ET (right after market close), Mon-Fri
    _scheduler.add_job(
        _nightly_data_pull,
        CronTrigger(hour=16, minute=30, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_NIGHTLY_DATA_PULL,
        replace_existing=True,
    )

    # Evening briefing: 6:00 PM ET (3:00 PM PT), Mon-Fri
    _scheduler.add_job(
        _evening_briefing_job,
        CronTrigger(hour=18, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_EVENING_BRIEFING,
        replace_existing=True,
    )

    # Start EP scanning at 7:00 AM ET (4:00 AM PT)
    _scheduler.add_job(
        _start_ep_scanning,
        CronTrigger(hour=7, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="ep_scan_start",
        replace_existing=True,
    )

    # EP scan: every 5 minutes 7:00–10:00 AM ET (covers 15-min delayed open gaps)
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

    # Morning briefing: 9:00 AM ET (6:00 AM PT), 30 min before open
    _scheduler.add_job(
        _morning_briefing_job,
        CronTrigger(hour=9, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_MORNING_BRIEFING,
        replace_existing=True,
    )

    # Stop EP scanning at 10:00 AM ET (7:00 AM PT) — extended past open to catch
    # at-open gaps with 15-min delayed data (Polygon Starter)
    _scheduler.add_job(
        _stop_ep_scanning,
        CronTrigger(hour=10, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="ep_scan_stop",
        replace_existing=True,
    )

    # Weekly cleanup: Sunday 2:00 AM ET
    _scheduler.add_job(
        _weekly_cleanup,
        CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="America/New_York"),
        id="weekly_cleanup",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Market Intelligence scheduler started (ET timezone)")
    return _scheduler


def get_scheduler_status() -> dict:
    """Return scheduler state: EP scan active flag and next fire times for key jobs."""
    next_jobs = []
    scheduler_running = _scheduler is not None and _scheduler.running
    if scheduler_running:
        for job_id in [JOB_NIGHTLY_DATA_PULL, JOB_EVENING_BRIEFING, JOB_MORNING_BRIEFING]:
            job = _scheduler.get_job(job_id)
            if job and job.next_run_time:
                next_jobs.append({
                    "id": job_id,
                    "next_run": job.next_run_time.isoformat(),
                })
    return {
        "ep_scan_active": _ep_scan_active,
        "scheduler_running": scheduler_running,
        "next_jobs": next_jobs,
    }


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("Scheduler stopped")
