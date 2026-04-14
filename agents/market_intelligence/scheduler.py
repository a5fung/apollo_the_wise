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
from agents.market_intelligence.trading_calendar import get_market_status
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
from agents.market_intelligence.backtester.tracker import (
    run_paper_trade_tracker,
    format_tracker_telegram,
)
from core.notifications import notify_job_failure, notify_job_success

logger = logging.getLogger(__name__)

# Job name constants — used in mi_job_log; must match exactly
JOB_NIGHTLY_DATA_PULL = "nightly_data_pull"
JOB_EVENING_BRIEFING = "evening_briefing"
JOB_MORNING_BRIEFING = "morning_briefing"

_scheduler: AsyncIOScheduler | None = None
_ep_scan_active = False  # Legacy — no longer gates scanning. Kept for /status display.
_ep_scans_completed_today: int = 0  # Tracks successful scan runs for watchdog


async def _nightly_data_pull():
    """
    Run at 4:30 PM ET (right after market close).
    Order: ingest → RS → regime → sector → themes → fundamentals → outcomes → state alerts.
    Regime runs after RS so breadth_full() can use stored mi_stock_scores.
    """
    logger.info("Nightly data pull starting...")
    from agents.market_intelligence.collector import et_today
    _today = et_today()
    today_str = _today.strftime("%Y-%m-%d")
    failures = []
    summary_parts = []
    ingested = 0
    scored = 0
    top_for_sector = None

    # 0. Skip on NYSE holidays — the 0-ingest guardrail below handles genuine Polygon failures.
    market_status = get_market_status(_today)
    if not market_status.is_trading_day:
        logger.info(
            f"Nightly pull skipped — {market_status.reason}. "
            f"No alert sent. To audit skipped days, grep logs for '[trading_calendar]'."
        )
        return

    # 1. Ingest today's daily closes
    # Try grouped daily first; if it fails/returns 0 (Polygon same-day restriction),
    # fall back to snapshot endpoint which works on Starter plan.
    try:
        ingested = await ingest_daily(_today)
        if ingested == 0 and _today.weekday() < 5:
            logger.warning("Grouped daily returned 0 on a weekday — falling back to snapshot")
            from agents.market_intelligence.rs_engine import ingest_from_snapshot
            ingested = await ingest_from_snapshot(_today)
        logger.info(f"Daily closes ingested: {ingested} tickers")
        await check_ingest_quality(ingested, _today)
    except Exception as e:
        logger.error(f"Daily close ingestion failed: {e}")
        failures.append(f"Daily ingestion: {e}")

    # GUARDRAIL: if no data ingested on a confirmed trading day, abort the pipeline.
    # The calendar check above already handled holidays — if we reach here with 0
    # tickers, it's a genuine Polygon failure or data issue.
    if ingested == 0 and _today.weekday() < 5:
        msg = f"Aborting nightly pull: 0 tickers ingested for {today_str} (confirmed trading day per NYSE calendar). Stale data would produce wrong signals."
        logger.error(msg)
        await notify_job_failure(JOB_NIGHTLY_DATA_PULL, msg)
        return

    # 1b. Refresh security types (weekly — classifies CS vs ETF/warrant/SPAC/etc.)
    try:
        from agents.market_intelligence.db import get_security_types_count, upsert_security_types_batch
        types_count = await get_security_types_count()
        # Bootstrap on first run, then refresh weekly (Monday)
        if types_count == 0 or _today.weekday() == 0:
            from agents.market_intelligence.collector import fetch_all_ticker_types
            ticker_types = await fetch_all_ticker_types()
            if ticker_types:
                stored = await upsert_security_types_batch(ticker_types)
                logger.info(f"Security types: stored {stored} tickers")
    except Exception as e:
        logger.error(f"Security types refresh failed: {e}")

    # 2. RS engine — scores, SMAs, raw returns
    try:
        rs_result = await run_rs_engine(_today)
        scored = rs_result.get("stocks_scored", 0)
        logger.info(f"RS engine: scored {scored} stocks")
        summary_parts.append(f"{scored} stocks scored")
        await check_rs_quality(scored, _today)
    except Exception as e:
        logger.error(f"RS engine failed: {e}")
        failures.append(f"RS engine: {e}")

    # 3. Regime engine — now can use full-universe breadth from stored data
    try:
        regime_result = await run_regime_engine(_today)
        regime = regime_result.get("regime", "?")
        logger.info(f"Regime: {regime}")
        summary_parts.append(f"regime={regime}")
    except Exception as e:
        logger.error(f"Regime engine failed: {e}")
        failures.append(f"Regime: {e}")

    # 4. Sector enrichment — fetch sector + industry for top RS stocks
    profile_cache: dict[str, dict] = {}  # shared across steps 4 and 4a
    try:
        from agents.market_intelligence.collector import get_fmp_profile
        from agents.market_intelligence.db import upsert_ticker_override
        from agents.market_intelligence.universe import get_description
        top_for_sector = await get_rs_leaders(today_str, limit=200, min_adv=0, min_price=0)
        sector_sem = asyncio.Semaphore(5)
        sector_map: dict[str, str] = {}
        desc_updates: dict[str, str] = {}
        async def _fetch_sector(ticker: str):
            async with sector_sem:
                profile = await get_fmp_profile(ticker)
                profile_cache[ticker] = profile
                s = profile.get("sector")
                if s:
                    sector_map[ticker] = s
                # Save industry as description for stocks without a curated one
                industry = profile.get("industry")
                if industry and not get_description(ticker):
                    desc_updates[ticker] = industry
        await asyncio.gather(*[_fetch_sector(s["ticker"]) for s in top_for_sector if not s.get("sector")])
        if sector_map:
            updated = await update_sectors_batch(_today, sector_map)
            logger.info(f"Sector enrichment: updated {updated} tickers")
            summary_parts.append(f"{updated} sectors")
        if desc_updates:
            for tk, desc in desc_updates.items():
                await upsert_ticker_override(tk, desc)
            from agents.market_intelligence.universe import apply_overrides
            apply_overrides(desc_updates)
            logger.info(f"Description enrichment: {len(desc_updates)} industry descriptions saved")

        # Data quality: sector coverage check (count pre-existing + newly fetched)
        with_sector = sum(1 for s in top_for_sector if s.get("sector") or s["ticker"] in sector_map)
        total_top = len(top_for_sector)
        if total_top > 0:
            await check_sector_quality(with_sector, total_top, _today)
    except Exception as e:
        logger.error(f"Sector enrichment failed: {e}")

    # 4a. Claude description generation — upgrade generic industry names to trading-relevant descriptions
    try:
        from agents.market_intelligence.universe import UNIVERSE_WITH_DESC, get_description
        from agents.market_intelligence.db import upsert_ticker_overrides_batch
        from agents.market_intelligence.universe import apply_overrides as _apply_overrides

        # Curated tickers from universe.py — skip these
        curated_tickers = {t for t, _ in UNIVERSE_WITH_DESC}

        # Find top RS stocks needing better descriptions
        # top_for_sector is from step 4 — if it failed, fall back to fresh query
        if top_for_sector is None:
            top_for_sector = await get_rs_leaders(today_str, limit=200, min_adv=0, min_price=0)
        candidates = []
        for s in top_for_sector:
            tk = s["ticker"]
            if tk in curated_tickers:
                continue
            desc = get_description(tk)
            # Skip if already has a trading-quality description (contains comma = multi-part = likely curated)
            if desc and "," in desc:
                continue
            candidates.append(s)

        if candidates[:40]:
            # Fetch company info — reuse profiles cached by step 4, only fetch missing ones
            from agents.market_intelligence.collector import get_fmp_profile
            profile_sem = asyncio.Semaphore(5)
            profiles: dict[str, dict] = {tk: p for tk, p in profile_cache.items()}
            need_fetch = [c["ticker"] for c in candidates[:40] if c["ticker"] not in profiles]
            async def _fetch_profile(ticker: str):
                async with profile_sem:
                    profiles[ticker] = await get_fmp_profile(ticker)
            if need_fetch:
                await asyncio.gather(*[_fetch_profile(tk) for tk in need_fetch])

            # Build batch prompt for Claude
            stock_lines = []
            tickers_to_describe = []
            for c in candidates[:40]:
                tk = c["ticker"]
                p = profiles.get(tk, {})
                name = p.get("companyName", tk)
                industry = p.get("industry", "")
                biz = p.get("description", "")[:200]
                if not (name or industry or biz):
                    continue
                tickers_to_describe.append(tk)
                stock_lines.append(f"- {tk}: {name}. Industry: {industry}. {biz}")

            if stock_lines:
                import os
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

                prompt = (
                    "Generate concise trading-relevant descriptions for these stocks. "
                    "Each description should be 3-8 words describing what the company actually does, "
                    "focused on the business that drives the stock price. Use the style of these examples:\n"
                    "- NVDA: AI/data center GPUs, inference & training chips\n"
                    "- MU: DRAM & NAND memory, HBM for AI GPUs\n"
                    "- AMAT: Semiconductor equipment, deposition & etch\n"
                    "- LLY: Pharma, GLP-1 obesity/diabetes drugs\n"
                    "- FCX: Copper & gold mining\n"
                    "- VST: Power generation, nuclear fleet\n\n"
                    "Return ONLY a JSON object mapping ticker to description. No markdown, no explanation.\n"
                    "Example: {\"ACME\": \"Industrial automation, robotics\"}\n\n"
                    "Stocks:\n" + "\n".join(stock_lines)
                )

                resp = await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}],
                )
                import json
                raw = resp.content[0].text.strip()
                # Strip markdown code fences if present
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                    if raw.endswith("```"):
                        raw = raw[:-3]
                    raw = raw.strip()

                try:
                    desc_map = json.loads(raw)
                    if isinstance(desc_map, dict):
                        valid = {tk.upper(): desc for tk, desc in desc_map.items()
                                 if isinstance(desc, str) and desc and tk.upper() in tickers_to_describe}
                        if valid:
                            await upsert_ticker_overrides_batch(valid)
                        _apply_overrides(desc_map)
                        logger.info(f"Claude descriptions: generated {len(valid)} trading-relevant descriptions")
                        summary_parts.append(f"{len(valid)} descriptions")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Claude description parse failed: {e}")
    except Exception as e:
        logger.error(f"Claude description enrichment failed: {e}")

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
        alerts, today_themes, prior_themes = await detect_state_changes(_today)
        if alerts or theme_changelog:
            await send_state_alerts(alerts, theme_changelog, today_themes, prior_themes)
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
        # Run EP scan first so alerts are in DB before briefing reads them
        await _ep_scan_job()
        await send_morning_briefing()
        await log_job_run(JOB_MORNING_BRIEFING)
    except Exception as e:
        import traceback
        logger.error(f"Morning briefing failed: {e}\n{traceback.format_exc()}")
        await notify_job_failure(JOB_MORNING_BRIEFING, str(e))


async def _ep_scan_job():
    """Run every 5 minutes 7:00–9:30 AM ET. Scan for EP gaps; HIGH alerts sent immediately."""
    global _ep_scans_completed_today
    logger.info("EP scan starting...")
    try:
        # Snapshot already-alerted tickers BEFORE scan (scan inserts new rows)
        from agents.market_intelligence.collector import et_today
        today = et_today()
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            already_alerted = {
                r["ticker"] for r in await conn.fetch(
                    "SELECT DISTINCT ticker FROM mi_ep_alerts WHERE alert_date = $1",
                    today,
                )
            }
        eps = await run_ep_scan()
        _ep_scans_completed_today += 1
        high_count = sum(1 for ep in eps if ep.get("score_tier") == "HIGH")
        logger.info(f"EP scan complete: {len(eps)} candidates, {high_count} HIGH")
        for ep in eps:
            if ep.get("score_tier") == "HIGH" and ep["ticker"] not in already_alerted:
                await send_ep_alert(ep)
                already_alerted.add(ep["ticker"])
                logger.info(f"Sent HIGH EP alert: {ep['ticker']}")
                try:
                    from agents.market_intelligence.db import log_audit_event
                    await log_audit_event(
                        "ep_alert",
                        summary=f"HIGH EP: {ep['ticker']} gap={ep.get('gap_pct', 0):.1f}% score={ep['ep_score']:.0f}",
                        detail=f"Catalyst: {ep.get('catalyst', '')[:300]}\nAnalysis: {ep.get('claude_analysis', '')[:200]}",
                    )
                except Exception:
                    pass
    except Exception as e:
        import traceback
        logger.error(f"EP scan failed: {e}\n{traceback.format_exc()}")
        await notify_job_failure("ep_scan", str(e))


async def _paper_trade_tracker_job():
    """Run at 4:45 PM ET. Simulate Day 1 for new EPs, update trailing stops on open positions."""
    logger.info("Paper trade tracker starting...")
    try:
        summary = await run_paper_trade_tracker()
        msg = format_tracker_telegram(summary)
        await send_telegram_message(msg)
        logger.info("Paper trade tracker complete")
    except Exception as e:
        import traceback
        logger.error(f"Paper trade tracker failed: {e}\n{traceback.format_exc()}")
        await notify_job_failure("paper_trade_tracker", str(e))


async def _orb_monitor_job():
    """Run at 9:31 AM ET. Process today's HIGH EP alerts, send trade proposals."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    logger.info("ORB monitor starting...")
    try:
        from agents.market_intelligence.broker.live_tracker import process_new_alerts_live
        results = await process_new_alerts_live()
        proposed = sum(1 for r in results if r.get("action") == "proposed")
        logger.info(f"ORB monitor complete: {proposed} proposals out of {len(results)} alerts")
    except Exception as e:
        import traceback
        logger.error(f"ORB monitor failed: {e}\n{traceback.format_exc()}")
        await notify_job_failure("orb_monitor", str(e))


async def _check_fills_job():
    """Fallback fill checker — only runs if WebSocket stream is unhealthy."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return

    # Skip if WebSocket stream is handling fills
    try:
        from agents.market_intelligence.broker.trade_stream import get_stream_status
        status = get_stream_status()
        if status["healthy"] and status["task_alive"]:
            logger.debug("Stream healthy, skipping polling fill check")
            return
    except ImportError:
        pass  # trade_stream not available — always poll

    logger.warning("Stream unhealthy, running fallback fill check")
    try:
        from agents.market_intelligence.broker.order_manager import check_fills
        results = await check_fills()
        if results:
            logger.info(f"Fallback fill check: {len(results)} updates")
    except Exception as e:
        import traceback
        logger.error(f"Fallback fill check failed: {e}\n{traceback.format_exc()}")


async def _stream_health_watchdog():
    """Check if the trade stream is alive. Restart if dead."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    try:
        from agents.market_intelligence.broker.trade_stream import get_stream_status, start_trade_stream
        status = get_stream_status()
        if not status["task_alive"]:
            logger.warning("Stream watchdog: task not alive, restarting")
            await send_telegram_message("⚠️ Trade stream died, restarting...")
            asyncio.create_task(start_trade_stream())
    except Exception as e:
        logger.error(f"Stream watchdog error: {e}")


async def _morning_stop_refresh_job():
    """Run at 9:35 AM ET. Refresh stop orders for Day 2+ positions."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    try:
        from agents.market_intelligence.broker.live_tracker import morning_stop_refresh
        count = await morning_stop_refresh()
        logger.info(f"Morning stop refresh: {count} stops refreshed")
    except Exception as e:
        logger.error(f"Morning stop refresh failed: {e}")
        await notify_job_failure("morning_stop_refresh", str(e))


async def _live_position_update_job():
    """Run at 4:45 PM ET. SMA trail, partials, stop updates for live positions. Send daily summary."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    logger.info("Live position update starting...")
    try:
        from agents.market_intelligence.broker.live_tracker import (
            update_open_positions_live,
            send_live_trade_summary,
        )
        results = await update_open_positions_live()
        await send_live_trade_summary()
        logger.info(f"Live position update complete: {len(results)} positions processed")
    except Exception as e:
        import traceback
        logger.error(f"Live position update failed: {e}\n{traceback.format_exc()}")
        await notify_job_failure("live_position_update", str(e))


async def _eod_cleanup_job():
    """Run at 4:05 PM ET. Cancel unfilled orders, sync positions with Alpaca."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    logger.info("EOD cleanup starting...")
    try:
        from agents.market_intelligence.broker.order_manager import cancel_unfilled_entries, sync_positions
        cancelled = await cancel_unfilled_entries()
        discrepancies = await sync_positions()
        logger.info(f"EOD cleanup: {cancelled} cancelled, {len(discrepancies)} discrepancies")
    except Exception as e:
        logger.error(f"EOD cleanup failed: {e}")
        await notify_job_failure("eod_cleanup", str(e))


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
    """Kept for /status display. Scanning is controlled by cron window, not this flag."""
    global _ep_scans_completed_today
    _ep_scans_completed_today = 0
    logger.info("EP scan window open (7:00 AM ET)")


async def _stop_ep_scanning():
    """Kept for /status display. Scanning is controlled by cron window, not this flag."""
    logger.info("EP scan window closed (10:00 AM ET)")


async def _ep_scan_watchdog():
    """Run at 10:05 AM ET. Alert if scans failed to run. No alert for zero EPs (normal)."""
    from agents.market_intelligence.collector import _ET
    now = datetime.now(_ET)
    if now.weekday() >= 5:
        return
    market_status = get_market_status(now.date())
    if not market_status.is_trading_day:
        logger.info(f"EP scan watchdog: skipping — {market_status.reason}")
        return
    try:
        if _ep_scans_completed_today == 0:
            logger.warning("EP scan watchdog: NO scans completed today!")
            await send_telegram_message(
                "⚠️ *EP Scan Watchdog*\n"
                "No EP scan completed today. The scanner may have failed or "
                "the container restarted after the scan window.\n"
                "Run manually: tell Apollo \"run EP scan\""
            )
        else:
            from agents.market_intelligence.db import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                alert_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM mi_ep_alerts WHERE alert_date = $1",
                    now.date(),
                )
            logger.info(f"EP scan watchdog: {_ep_scans_completed_today} scans ran, {alert_count} alerts — OK")
    except Exception as e:
        logger.error(f"EP scan watchdog failed: {e}")


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
    from agents.market_intelligence.collector import _ET
    now = datetime.now(_ET)

    if now.weekday() >= 5:  # Saturday / Sunday
        return

    market_status = get_market_status(now.date())
    if not market_status.is_trading_day:
        logger.info(f"check_missed_jobs: skipping catch-up — {market_status.reason}")
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

    # EP scan watchdog: 10:05 AM ET — alert if no scan ran today
    _scheduler.add_job(
        _ep_scan_watchdog,
        CronTrigger(hour=10, minute=5, day_of_week="mon-fri", timezone="America/New_York"),
        id="ep_scan_watchdog",
        replace_existing=True,
    )

    # Paper trade tracker: 4:45 PM ET — after nightly data pull, simulate new EPs + update stops
    _scheduler.add_job(
        _paper_trade_tracker_job,
        CronTrigger(hour=16, minute=45, day_of_week="mon-fri", timezone="America/New_York"),
        id="paper_trade_tracker",
        replace_existing=True,
    )

    # Weekly cleanup: Sunday 2:00 AM ET
    _scheduler.add_job(
        _weekly_cleanup,
        CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="America/New_York"),
        id="weekly_cleanup",
        replace_existing=True,
    )

    # ── Live trading jobs (only fire if LIVE_TRADING_ENABLED) ──────────────
    # ORB monitor pass 1: 9:32 AM ET — process pre-market HIGH alerts
    # (9:32 not 9:31 to ensure first 1-min bar is finalized)
    _scheduler.add_job(
        _orb_monitor_job,
        CronTrigger(hour=9, minute=32, day_of_week="mon-fri", timezone="America/New_York"),
        id="orb_monitor",
        replace_existing=True,
    )

    # ORB monitor pass 2: 9:37 AM ET — catch at-open EP upgrades from the 9:35 scan
    # EPs that were near-miss pre-market but confirmed volume on the first bar are
    # inserted by the 9:35 scan. ON CONFLICT DO NOTHING prevents double-processing
    # of stocks already handled at 9:32.
    _scheduler.add_job(
        _orb_monitor_job,
        CronTrigger(hour=9, minute=37, day_of_week="mon-fri", timezone="America/New_York"),
        id="orb_monitor_pass2",
        replace_existing=True,
    )

    # Fill checker — fallback polling (WebSocket is primary, this is safety net)
    # Runs every 30 min; skips if WebSocket stream is healthy
    fill_check_times = [(10, 0), (10, 30), (11, 0), (12, 0), (13, 0), (14, 0), (15, 0)]
    for hour, minute in fill_check_times:
        _scheduler.add_job(
            _check_fills_job,
            CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri", timezone="America/New_York"),
            id=f"check_fills_{hour:02d}{minute:02d}",
            replace_existing=True,
        )

    # Stream health watchdog: every 5 min during market hours
    _scheduler.add_job(
        _stream_health_watchdog,
        CronTrigger(hour="9-15", minute="*/5", day_of_week="mon-fri", timezone="America/New_York"),
        id="stream_health_watchdog",
        replace_existing=True,
    )

    # Morning stop refresh: 9:35 AM ET — re-place stops for Day 2+ positions
    _scheduler.add_job(
        _morning_stop_refresh_job,
        CronTrigger(hour=9, minute=35, day_of_week="mon-fri", timezone="America/New_York"),
        id="morning_stop_refresh",
        replace_existing=True,
    )

    # EOD cleanup: 4:05 PM ET — cancel unfilled, sync positions
    _scheduler.add_job(
        _eod_cleanup_job,
        CronTrigger(hour=16, minute=5, day_of_week="mon-fri", timezone="America/New_York"),
        id="eod_cleanup",
        replace_existing=True,
    )

    # Live position update: 4:45 PM ET — SMA trail, partials, stop updates
    _scheduler.add_job(
        _live_position_update_job,
        CronTrigger(hour=16, minute=45, day_of_week="mon-fri", timezone="America/New_York"),
        id="live_position_update",
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
    # EP scan window is 7-10 AM ET, controlled by cron (not a flag)
    from agents.market_intelligence.collector import _ET
    now_et = datetime.now(_ET)
    in_scan_window = 7 <= now_et.hour < 10 and now_et.weekday() < 5
    return {
        "ep_scan_active": in_scan_window,
        "scheduler_running": scheduler_running,
        "next_jobs": next_jobs,
    }


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("Scheduler stopped")
