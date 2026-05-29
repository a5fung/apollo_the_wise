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
import json
import logging
import re
from datetime import datetime, time as _dt_time, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.market_intelligence.db import (
    purge_old_data, log_job_run, job_ran_today, upsert_fundamental_flags_batch,
    get_rs_leaders, update_sectors_batch, get_audit_log, get_pool, log_audit_event,
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
from agents.market_intelligence.constants import mode_prefix
from agents.market_intelligence.backtester.tracker import (
    run_paper_trade_tracker,
    format_tracker_telegram,
)
from core.notifications import notify_job_failure, notify_job_success
from core.job_audit import audit_wrap

logger = logging.getLogger(__name__)

# Job name constants — used in mi_job_log; must match exactly
JOB_NIGHTLY_DATA_PULL = "nightly_data_pull"
JOB_EVENING_BRIEFING = "evening_briefing"
JOB_MORNING_BRIEFING = "morning_briefing"
JOB_PARABOLIC_SCAN = "parabolic_scan"
JOB_WICK_FORWARD_RETURNS = "wick_forward_returns"
JOB_FISHHOOK_EOD = "fishhook_eod_pass"
JOB_FLAG_SCAN = "flag_continuation_scan"
JOB_SUGAR_BABIES_COHORT_REFRESH = "sugar_babies_cohort_refresh"
JOB_TIME_STOP_SCAN = "time_stop_scan"
JOB_FLAG_BREAK_SCAN = "flag_break_scan"
JOB_SUPPORT_TEST_SCAN = "support_test_scan"
JOB_MA_PULLBACK_SCAN = "ma_pullback_scan"
JOB_BACKUP_HEALTH_CHECK = "backup_health_check"
JOB_ORDER_STATUS_RECONCILE = "order_status_reconcile"
JOB_9M_PACE_DIGEST = "9m_pace_digest"
JOB_CATALYST_DOWNGRADE_DIGEST = "catalyst_downgrade_digest"

_scheduler: AsyncIOScheduler | None = None
_ep_scan_active = False  # Legacy — no longer gates scanning. Kept for /status display.


async def _nightly_data_pull():
    """
    Run at 5:00 PM ET (30 min after tape settles).
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

    # 0b. Splits ingest — fetch new Polygon split records + re-fetch affected
    # tickers' history with adjusted=true so cached close/volume reflect the
    # post-split denomination BEFORE today's grouped daily writes new bars.
    # Failure here is logged but non-fatal — the heuristic-free RS engine will
    # still score, and unapplied splits stay queued for the next run.
    try:
        from agents.market_intelligence.splits_ingest import run_splits_ingest
        splits_summary = await run_splits_ingest()
        if splits_summary["splits_applied_ok"] or splits_summary["splits_detected_new"]:
            summary_parts.append(
                f"splits new={splits_summary['splits_detected_new']} "
                f"applied={splits_summary['splits_applied_ok']}"
            )
    except Exception as e:
        logger.error(f"Splits ingest failed: {e}")
        failures.append(f"Splits ingest: {e}")

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

    # 4.5. Correlation clustering — statistical pre-pass for theme discovery
    correlation_clusters: list[dict] = []
    try:
        from agents.market_intelligence.correlation_engine import run_correlation_clustering
        correlation_clusters = await run_correlation_clustering(_today)
        logger.info(f"Correlation clustering: {len(correlation_clusters)} clusters found")
        if correlation_clusters:
            summary_parts.append(f"{len(correlation_clusters)} corr clusters")
    except Exception as e:
        logger.warning(f"Correlation clustering failed (non-fatal): {e}")

    # 4.5. 9M EP EOD sweep — runs after data ingestion, before theme engine
    try:
        from agents.market_intelligence.ninem_detector import run_9m_eod_sweep
        _9m_count = await run_9m_eod_sweep(_today)
        if _9m_count:
            summary_parts.append(f"{_9m_count} 9M sugar babies")
    except Exception as e:
        logger.warning(f"9M EOD sweep failed (non-fatal): {e}")

    # 4.6. Wick-fill (P22) EOD sweep — same 9M data, mid-range close branch
    try:
        from agents.market_intelligence.wick_tracker import run_wick_sweep
        _wick_count = await run_wick_sweep(_today)
        if _wick_count:
            summary_parts.append(f"{_wick_count} wick candidates")
    except Exception as e:
        logger.warning(f"Wick EOD sweep failed (non-fatal): {e}")

    # 5. Theme engine
    theme_changelog: list[dict] = []
    try:
        themes, theme_changelog = await run_theme_engine(clusters=correlation_clusters)
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

    # 7b. Missed-EP opportunity-cost telemetry — rebuild the 30-day rolling
    # window of filtered / MODERATE / HIGH-unentered alerts with forward
    # returns from mi_daily_closes. Slots after outcome tracker so all
    # daily closes are settled. Failure non-fatal: stale rows freeze.
    try:
        from agents.market_intelligence.missed_outcomes import refresh_missed_outcomes
        missed_summary = await refresh_missed_outcomes(window_days=30)
        await log_audit_event(
            "missed_outcomes_refreshed",
            f"window {missed_summary['window_start']}..{missed_summary['window_end']}: "
            f"scan_filter={missed_summary.get('scan_filter', 0)}, "
            f"moderate_alert={missed_summary.get('moderate_alert', 0)}, "
            f"high_unentered={missed_summary.get('high_unentered', 0)}",
            detail=str(missed_summary)[:500],
        )
        total = sum(v for k, v in missed_summary.items() if isinstance(v, int))
        if total:
            summary_parts.append(f"{total} missed-EP rows")
    except Exception as e:
        logger.error(f"Missed-outcomes refresh failed: {e}")

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

    # 9. ORB-extension shadow settlement — re-evaluate every still-open
    # counterfactual position via apply_daily_exit_step. Runs after
    # mi_daily_closes is refreshed (ingest_daily completed earlier above).
    # Failure non-fatal: rows stay open, settle next night.
    try:
        from agents.market_intelligence.broker.orb_extension_shadow import (
            settle_open_shadows,
        )
        shadow_summary = await settle_open_shadows(_today)
        if shadow_summary["reviewed"]:
            logger.info(f"orb_ext_shadow settlement: {shadow_summary}")
            await log_audit_event(
                "orb_extension_shadow_settled",
                f"reviewed={shadow_summary['reviewed']} settled={shadow_summary['settled']} "
                f"still_open={shadow_summary['still_open']} errors={shadow_summary['errors']}",
            )
    except Exception as e:
        logger.error(f"ORB-extension shadow settlement failed: {e}", exc_info=True)

    # Check for silent engine errors (parse failures, API errors that didn't hard-fail).
    # Bucket by category so a flood of one type (e.g. Anthropic 5xx burst) collapses
    # to a single line and doesn't drown out genuinely novel errors.
    try:
        error_rows = await get_audit_log(limit=40, event_type_like="%error%", since_hours=2)
        rate_rows = await get_audit_log(limit=40, event_type_like="%rate_limited%", since_hours=2)
        api_rows = await get_audit_log(limit=40, event_type_like="%api_failure%", since_hours=2)
        rate_limited_types = {"validation_rate_limited", "anthropic_rate_limited",
                              "assignment_rate_limited", "discovery_rate_limited"}
        api_failure_types  = {"validation_api_failure", "assignment_api_failure",
                              "discovery_api_failure"}
        parse_error_types  = {"validation_error"}
        buckets: dict[str, list] = {"rate_limited": [], "api_failure": [],
                                     "validation_error": [], "other": []}
        seen_ids: set = set()
        for r in (error_rows + rate_rows + api_rows):
            row_id = r.get("id") or id(r)
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            evt = r.get("event_type") or ""
            if evt in rate_limited_types:
                buckets["rate_limited"].append(r)
            elif evt in api_failure_types:
                buckets["api_failure"].append(r)
            elif evt in parse_error_types:
                buckets["validation_error"].append(r)
            elif "error" in evt:
                buckets["other"].append(r)
        total = sum(len(v) for v in buckets.values())
        if total:
            lines = [f"⚠️ *{total} engine event(s) during nightly run:*"]
            if buckets["rate_limited"]:
                lines.append(
                    f"  🟠 {len(buckets['rate_limited'])} Anthropic rate-limited call(s) — tickers unchanged"
                )
            if buckets["api_failure"]:
                lines.append(
                    f"  🔵 {len(buckets['api_failure'])} transient Anthropic API failure(s) — will retry next run"
                )
            if buckets["validation_error"]:
                lines.append(
                    f"  🟡 {len(buckets['validation_error'])} theme validation parse error(s) — tickers unchanged"
                )
            for r in buckets["other"][:5]:
                lines.append(f"  🔴 {r['summary']}")
            if len(buckets["other"]) > 5:
                lines.append(f"  …{len(buckets['other']) - 5} more")
            lines.append("Type 'show errors' for details.")
            await send_telegram_message("\n".join(lines))
            logger.warning(f"Nightly run had {total} silent events — alerted via Telegram")
    except Exception as e:
        logger.error(f"Error check after nightly run failed: {e}")

    if failures:
        await notify_job_failure(JOB_NIGHTLY_DATA_PULL, " | ".join(failures))
    else:
        await log_job_run(JOB_NIGHTLY_DATA_PULL)
        await notify_job_success(JOB_NIGHTLY_DATA_PULL, ", ".join(summary_parts))

    logger.info("Nightly data pull complete")
    return int(scored or 0)


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
    """Run every 5 minutes 7:00–10:00 AM ET. Scan for EP gaps; HIGH alerts sent immediately.

    Pre-market new HIGHs: subscribed to bar stream for real-time first-bar ORB entry.
    Post-open new HIGHs: bar already closed, ORB entry triggered inline immediately."""
    logger.info("EP scan starting...")
    try:
        from agents.market_intelligence.collector import et_today, _ET
        from agents.market_intelligence.broker import bar_stream
        today = et_today()
        # get_pool already imported at module level (line 24); local import
        # here would shadow + cause UnboundLocalError in later refs (e.g.
        # the except handler) if a prior line raised first.
        pool = await get_pool()
        async with pool.acquire() as conn:
            already_alerted = {
                r["ticker"] for r in await conn.fetch(
                    "SELECT DISTINCT ticker FROM mi_ep_alerts WHERE alert_date = $1",
                    today,
                )
            }
        eps = await run_ep_scan()
        high_count = sum(1 for ep in eps if ep.get("score_tier") == "HIGH")
        logger.info(f"EP scan complete: {len(eps)} candidates, {high_count} HIGH")

        now_et = datetime.now(_ET)
        market_open = now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 31)
        # ORB bracket orders are only valid in the first 14 min of the session
        # (9:31–9:44 AM ET). A HIGH first surfacing at 9:55 against a 9:30–9:31
        # ORB bar is typically placing a stop-limit buy at a level the tape has
        # already faded from; fills come hours later on dead-cat-bounce retests.
        # Matches the 15-min gate already used for EP projection.
        within_orb_window = market_open and now_et.hour == 9 and now_et.minute < 45
        new_highs_post_open = []

        for ep in eps:
            if ep.get("score_tier") == "HIGH" and ep["ticker"] not in already_alerted:
                await send_ep_alert(ep)
                already_alerted.add(ep["ticker"])
                logger.info(f"Sent HIGH EP alert: {ep['ticker']}")
                try:
                    # log_audit_event already imported at module level (line 24)
                    # — local import here would shadow + cause UnboundLocalError
                    # in any later-in-function ref that runs when this branch
                    # is skipped (e.g. the except handler at end of function).
                    await log_audit_event(
                        "ep_alert",
                        summary=f"HIGH EP: {ep['ticker']} gap={ep.get('gap_pct', 0):.1f}% score={ep['ep_score']:.0f}",
                        detail=f"Catalyst: {ep.get('catalyst', '')[:300]}\nAnalysis: {ep.get('claude_analysis', '')[:200]}",
                    )
                except Exception:
                    pass

                if within_orb_window:
                    # First bar already closed — trigger ORB inline, no bar stream needed
                    new_highs_post_open.append(ep["ticker"])
                elif not market_open:
                    # Pre-market — subscribe to bar stream; ORB fires when first bar closes
                    await bar_stream.subscribe_ep_candidate(ep["ticker"])
                else:
                    # HIGH arrived after ORB window closed — no order possible. Persist a
                    # skipped-trade row + audit event + Telegram so every HIGH alert has a
                    # durable terminal state for evening brief / `/why`.
                    from agents.market_intelligence.broker.live_tracker import _insert_skipped_trade
                    from agents.market_intelligence.broker.skip_reasons import WINDOW_OUT_OF_ORB
                    from agents.market_intelligence.collector import et_today
                    skip_msg = f"{WINDOW_OUT_OF_ORB}: detected {now_et.strftime('%H:%M')} ET"
                    try:
                        await _insert_skipped_trade(
                            ep["ticker"], et_today(), ep, None, skip_msg,
                            signal_type="magna53",
                        )
                    except Exception as ins_e:
                        logger.error(f"Could not insert out-of-ORB skip for {ep['ticker']}: {ins_e}")
                    try:
                        # NOTE: do NOT `from ... import log_audit_event` here —
                        # it's imported at module level + referenced earlier in
                        # this function, so a local import would shadow and
                        # cause UnboundLocalError (2026-05-20 ep_detector bug).
                        await log_audit_event("orb_out_of_window", f"{ep['ticker']} — {skip_msg}")
                    except Exception:
                        pass
                    await send_telegram_message(
                        f"{mode_prefix()}⏰ *{ep['ticker']}* HIGH EP arrived {now_et.strftime('%H:%M')} ET — "
                        f"ORB window closed, no order"
                    )
                    logger.info(f"EP {ep['ticker']}: outside ORB window ({now_et.strftime('%H:%M')} ET) — alert sent, no order")

        if new_highs_post_open:
            logger.info(f"Post-open new HIGHs {new_highs_post_open} — triggering ORB entry inline")
            await _orb_monitor_job(trigger="post_open_new_high")
        elif within_orb_window and now_et.minute == 31:
            # 9:31 open scan: always run ORB as fallback for pre-market HIGHs
            # bar_stream handles them in real-time, but if stream was unhealthy or missed
            # a subscription, process_new_alerts_live skips already-processed tickers safely.
            logger.info("9:31 ORB fallback: checking for unprocessed pre-market HIGHs")
            await _orb_monitor_job(trigger="cron_9_31")

    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(f"EP scan failed: {e}\n{tb_str}")

        # Durable audit-log record FIRST — guarantees a DB row even if
        # Telegram fails (silent-failure class fix: don't rely on a single
        # surfacing channel for trading-path failures).
        # 2026-05-20: morning EP-scan UnboundLocalError fired 17× over
        # 1h21m. Operator noticed via missing-alerts symptom, not via the
        # existing notify_job_failure call. Adding redundant durable
        # surfacing + escalated framing + dedup.
        exc_type = type(e).__name__
        try:
            await log_audit_event(
                "ep_scan_failed",
                f"{exc_type}: {str(e)[:300]}",
                # detail param accepts JSON string
                __import__('json').dumps({
                    "exception_type": exc_type,
                    "traceback_tail": tb_str[-1500:],
                }),
            )
        except Exception as audit_e:
            logger.error(f"audit_log write also failed: {audit_e}")

        # Dedup Telegram: identical-exception failures within the last 1h
        # → audit-only (no Telegram spam). FIRST occurrence is LOUD with
        # escalated framing. EP-scan failure = no alerts fire = missed
        # trades. Trading-path class, treated like CRMD.
        _suppress_tg = False
        try:
            pool_d = await get_pool()
            async with pool_d.acquire() as conn_d:
                prior = await conn_d.fetchrow("""
                    SELECT 1 FROM mi_audit_log
                    WHERE event_type = 'ep_scan_failed'
                      AND summary LIKE $1
                      AND created_at > NOW() - INTERVAL '1 hour'
                      AND created_at < NOW() - INTERVAL '1 second'
                    LIMIT 1
                """, f"{exc_type}:%")
                _suppress_tg = prior is not None
        except Exception:
            _suppress_tg = False  # fail-open

        if not _suppress_tg:
            try:
                await send_telegram_message(
                    f"🚨 *EP SCAN DOWN — TRADING IMPACTED*\n"
                    f"`{exc_type}`: {str(e)[:200]}\n"
                    f"_No HIGH EP alerts will fire until this is fixed._\n"
                    f"_Logs: `docker logs apollo-market --since 5m`_"
                )
            except Exception as tg_e:
                # Telegram itself failed — log loud. The audit-log row above
                # is the durable record either way.
                logger.error(f"EP_SCAN_DOWN Telegram alert also failed: {tg_e}")
        # NOTE: not calling notify_job_failure here — the escalated TG above
        # IS the failure notification, with explicit trading-impact framing.
        # notify_job_failure was the previous (less loud) version; adding it
        # AGAIN would produce a second un-deduped Telegram per scan tick
        # (3-message spam pattern observed during synthetic test 2026-05-20).


async def _paper_trade_tracker_job():
    """Run at 4:45 PM ET. Simulate Day 1 for new EPs, update trailing stops on open positions.
    Skipped when LIVE_TRADING_ENABLED=true — the live Alpaca path is the single source of truth."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if LIVE_TRADING_ENABLED:
        logger.info("Paper trade tracker: skipped (live trading enabled — Alpaca is source of truth)")
        return
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


async def _orb_monitor_job(trigger: str = "cron"):
    """Process HIGH EP alerts: fetch first bar, place buy stop at ORB high.
    Called from two paths:
    - 9:31 AM fallback (trigger="cron_9_31"): pre-market HIGH alerts, bar just closed
    - Inline from _ep_scan_job (trigger="post_open_new_high"): at-open upgrades"""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    logger.info(f"ORB monitor starting [{trigger}]...")
    try:
        from agents.market_intelligence.broker.live_tracker import process_new_alerts_live
        results = await process_new_alerts_live(trigger=trigger)
        entered = sum(1 for r in results if r.get("action") in ("auto_entered", "proposed"))
        skipped = sum(1 for r in results if r.get("action") in ("filtered", "skipped", "blocked"))
        logger.info(f"ORB monitor [{trigger}]: {entered} entered, {skipped} skipped, {len(results)} total")
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


async def _time_stop_scan_job():
    """Run at 4:55 PM ET (Mon-Fri). Identify 9M Day 2 meanderers eligible
    for operator-confirm time-stop and Telegram-alert them.

    Discriminator (#91, 2026-05-23):
      - signal_type = '9m_day2' (narrow scope; MAGNA53 has different
        hold-time dynamics — BW at day 11 still working)
      - trading days since fill >= 5 (gives the slow-runner shape
        room to start, e.g. GOOGL +6.8% peak at later days)
      - highest_price_seen excursion < +3% (excludes positions that
        had a real run — PURR-class +13% spike followed by fade is
        a partial-take/breakeven-trail issue, not a meanderer issue)
      - status = 'filled' (only currently-open positions)

    No actual exit fired — operator confirms via /timestop TICKER
    command (operator_only automation_class per ADR 0004).

    Slots after live_position_update (4:45) + shadow_orb_exit (4:50)
    + before data_pull (5:00). Single-pass query; lightweight.
    """
    pool = await get_pool()
    candidates: list[dict] = []
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ticker, alert_date, filled_at::date AS filled_d,
                   entry_price, stop_price, remaining_shares,
                   highest_price_seen, lowest_price_seen,
                   -- Compute trading-days-since-fill explicitly (hold_days
                   -- is calendar days, weekends inflate it).
                   (SELECT COUNT(*)::int FROM generate_series(
                        filled_at::date + 1, CURRENT_DATE, '1 day') s
                    WHERE EXTRACT(DOW FROM s) BETWEEN 1 AND 5) AS trading_days
            FROM mi_live_trades
            WHERE status = 'filled'
              AND signal_type = '9m_day2'
              AND filled_at IS NOT NULL
              AND entry_price > 0
              AND highest_price_seen IS NOT NULL
        """)
        for r in rows:
            entry = float(r["entry_price"])
            high = float(r["highest_price_seen"]) if r["highest_price_seen"] is not None else None
            if high is None or entry <= 0:
                continue
            high_excur_pct = (high - entry) / entry * 100.0
            trading_days = r["trading_days"] or 0
            # Discriminator gate: >=5 trading days AND high excursion <+3%
            if trading_days >= 5 and high_excur_pct < 3.0:
                candidates.append({
                    "id": r["id"],
                    "ticker": r["ticker"],
                    "trading_days": trading_days,
                    "entry": entry,
                    "stop": float(r["stop_price"]) if r["stop_price"] else None,
                    "shares": float(r["remaining_shares"]) if r["remaining_shares"] else 0,
                    "high_excur_pct": high_excur_pct,
                    "low_excur_pct": (
                        (float(r["lowest_price_seen"]) - entry) / entry * 100.0
                        if r["lowest_price_seen"] else None
                    ),
                })

    if not candidates:
        logger.info("time_stop_scan: no candidates")
        return 0

    # Same-day audit dedup pattern (#85/#89 shape) — log time_stop_candidate
    # once per (ticker, ET date). Re-runs of the EOD scan don't inflate the
    # audit count and don't re-Telegram the same set.
    new_candidates: list[dict] = []
    async with pool.acquire() as conn:
        for c in candidates:
            prior = await conn.fetchrow("""
                SELECT 1 FROM mi_audit_log
                WHERE event_type = 'time_stop_candidate'
                  AND summary LIKE $1
                  AND (created_at AT TIME ZONE 'America/New_York')::date
                      = (NOW() AT TIME ZONE 'America/New_York')::date
                LIMIT 1
            """, f"{c['ticker']} 9m_day2%")
            if prior is None:
                await log_audit_event(
                    "time_stop_candidate",
                    f"{c['ticker']} 9m_day2 — "
                    f"trading_days={c['trading_days']} "
                    f"high_excur={c['high_excur_pct']:+.2f}% "
                    f"low_excur={c['low_excur_pct']:+.2f}%"
                    if c['low_excur_pct'] is not None else
                    f"{c['ticker']} 9m_day2 — "
                    f"trading_days={c['trading_days']} "
                    f"high_excur={c['high_excur_pct']:+.2f}%"
                )
                new_candidates.append(c)

    # Telegram alert (one consolidated message). Even if all candidates
    # were already audit-deduped today (e.g. job re-fires), do not spam
    # the Telegram channel. send_telegram_message imported at module
    # level (line 39-43) per preflight [5d/5] import-shadowing rule.
    if new_candidates:
        lines = [
            f"⏱️ *Time-Stop Candidates — 9M Day 2 meanderers ({len(new_candidates)})*",
            "_Held ≥5 trading days, peak excursion <+3% — failed to confirm continuation._",
            "",
        ]
        for c in new_candidates:
            stop_dist_pct = (
                (c['stop'] - c['entry']) / c['entry'] * 100.0
                if c['stop'] else None
            )
            notional = c['shares'] * c['entry']
            lines.append(
                f"• `{c['ticker']}` day {c['trading_days']} · "
                f"entry ${c['entry']:.2f} · peak {c['high_excur_pct']:+.1f}%"
            )
            if c['low_excur_pct'] is not None:
                lines.append(
                    f"   trough {c['low_excur_pct']:+.1f}% · "
                    f"sized ${notional:,.0f}"
                    + (f" · stop {stop_dist_pct:+.1f}% away" if stop_dist_pct else "")
                )
            lines.append(f"   `/timestop {c['ticker']}` to exit at market on open")
            lines.append("")
        lines.append(
            "_Operator-only: /timestop submits TimeInForce.OPG to Alpaca; "
            "fills at next regular-session open. Submission window: "
            "7 PM ET prior day → 9:25 AM ET next day._"
        )
        await send_telegram_message("\n".join(lines))
        logger.info(f"time_stop_scan: alerted on {len(new_candidates)} candidates")

    return len(new_candidates)


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


async def _account_equity_snapshot_job():
    """Run at 4:12 PM ET. Snapshot Alpaca account.equity to mi_account_equity_snapshots
    and recompute the drawdown breaker state machine (#39).

    Sequenced after eod_cleanup (16:05) which syncs positions — by 16:12 equity
    reflects settled MTM. State transitions emit one audit event each
    (drawdown_breaker_tripped / drawdown_breaker_released). Active phase reads
    the persisted state via cheap PK lookup in _check_safeguards.

    Failure-safe: snapshot failures emit drawdown_check_unavailable audit event;
    state recompute is skipped (don't transition without fresh data). Stale-data
    fail-open guard inside compute_drawdown_state covers the case where this
    job has been failing silently for >48h.
    """
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    try:
        from agents.market_intelligence.broker.drawdown_breaker import (
            snapshot_account_equity, recompute_drawdown_state,
        )
        from agents.market_intelligence.constants import ENABLE_LIVE_MODE
        # Dual-account #66: snapshot + recompute per mode. Each mode has its
        # own equity, peak, drawdown state — paper drift doesn't trip the
        # live breaker and vice versa.
        modes = ["paper", "live"] if ENABLE_LIVE_MODE else ["paper"]
        for mode in modes:
            try:
                snap = await snapshot_account_equity(account_mode=mode)
                if snap:
                    await recompute_drawdown_state(mode)
                # else: snapshot_account_equity already audit-logged drawdown_check_unavailable
            except Exception as e:
                logger.error(
                    f"Account equity snapshot/recompute for mode={mode} failed: {e}"
                )
    except Exception as e:
        logger.error(f"Account equity snapshot/recompute failed: {e}")
        await notify_job_failure("account_equity_snapshot", str(e))


async def _stuck_fill_watchdog_job():
    """Gate 5 deliverable D (2026-05-14): surface stuck-filling trade rows.

    If an entry order is placed but the WS fill handler errored (e.g. CRMD
    AmbiguousParameter), the trade row stays at status='filling' indefinitely.
    Today's naked-position remediation in _process_entry_fill submits a
    fallback stop, but the row's state still needs operator attention.

    Predicate: entry_order_id IS NOT NULL AND status='filling' AND
    filled_at IS NULL AND created_at < NOW() - INTERVAL '2 minutes'.

    Runs every 60s during market hours. Fires `stuck_fill_detected` audit
    event + escalated Telegram on first detection per trade (dedup via
    audit log presence).
    """
    from agents.market_intelligence.db import get_pool, log_audit_event
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.constants import mode_prefix
    pool = await get_pool()
    async with pool.acquire() as conn:
        stuck = await conn.fetch(
            """
            SELECT id, ticker, account_mode, entry_order_id, created_at
            FROM mi_live_trades
            WHERE entry_order_id IS NOT NULL
              AND status = 'filling'
              AND filled_at IS NULL
              AND created_at < NOW() - INTERVAL '2 minutes'
            """
        )
        for row in stuck:
            already = await conn.fetchval(
                "SELECT 1 FROM mi_audit_log WHERE event_type='stuck_fill_detected' "
                "AND summary LIKE $1 AND created_at > NOW() - INTERVAL '1 day' LIMIT 1",
                f"{row['ticker']} #{row['id']}%",
            )
            if already:
                continue
            await log_audit_event(
                "stuck_fill_detected",
                f"{row['ticker']} #{row['id']} ({row['account_mode']}): "
                f"status='filling' with no filled_at for >2 min — WS handler likely threw",
            )
            await send_telegram_message(
                f"{mode_prefix(row['account_mode'])}🚨 *STUCK FILL DETECTED:* {row['ticker']}\n"
                f"Trade #{row['id']} stuck in status='filling' since "
                f"{row['created_at']:%H:%M:%S ET}.\n"
                f"WS handler likely threw — check broker for naked position and Apollo logs."
            )


async def _stop_ack_timeout_watchdog_job():
    """Stop-ACK timeout gate (2026-05-17, MRAM-class). Sibling of Gate 5 D
    stuck-fill watchdog.

    Gate 5 A (2026-05-14) covers the EXCEPTION case — when entry-fill
    UPDATE raises (CRMD AmbiguousParameter), submit a fallback stop
    immediately. Gate 5 A does NOT cover the SILENT case where the entry
    UPDATE succeeds normally but `stop_order_id` stays NULL because the
    OTO bracket's child stop leg either never ACK'd from Alpaca or its
    acceptance event was missed by the WS handler. MRAM #120
    (2026-05-11) is the canonical example: entry filled, stop_order_id
    persisted as NULL, position closed via WS-only path with phantom
    double-exit logged.

    Predicate: status='filled' AND filled_at IS NOT NULL AND
    stop_order_id IS NULL AND filled_at < NOW() - INTERVAL '30 seconds'.

    Runs every 30s during market hours. On detection, submits a fallback
    stop-market at trade['orb_low'] (mirroring Gate 5 A pattern). On
    fallback failure: escalates to CRITICAL Telegram + audit event.

    Env flag STOP_ACK_TIMEOUT_GATE_ENABLED=false disables the gate for
    fast rollback (default true).
    """
    import os
    if os.environ.get("STOP_ACK_TIMEOUT_GATE_ENABLED", "true").lower() != "true":
        return
    import json as _json
    from agents.market_intelligence.db import get_pool, log_audit_event
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.constants import mode_prefix
    from agents.market_intelligence.broker import alpaca_client as alpaca
    pool = await get_pool()
    async with pool.acquire() as conn:
        stuck = await conn.fetch(
            """
            SELECT id, ticker, account_mode, orb_low, entry_shares,
                   remaining_shares, filled_at, entry_order_id
            FROM mi_live_trades
            WHERE status = 'filled'
              AND filled_at IS NOT NULL
              AND stop_order_id IS NULL
              AND filled_at < NOW() - INTERVAL '30 seconds'
            """
        )
        for row in stuck:
            ticker = row["ticker"]
            account_mode = row["account_mode"]
            trade_id = row["id"]
            # Dedup — one remediation attempt per (trade_id, day). If a
            # prior attempt already fired we don't re-fire (the prior
            # action either succeeded or escalated to CRITICAL).
            already = await conn.fetchval(
                "SELECT 1 FROM mi_audit_log "
                "WHERE event_type IN ('stop_ack_timeout_remediated', "
                "                     'stop_ack_remediation_failed', "
                "                     'stop_ack_broker_covered') "
                "AND summary LIKE $1 "
                "AND created_at > NOW() - INTERVAL '1 day' LIMIT 1",
                f"{ticker} #{trade_id}%",
            )
            if already:
                continue

            qty = float(row["remaining_shares"] or row["entry_shares"] or 0)
            stop_target = float(row["orb_low"]) if row["orb_low"] is not None else None

            # Broker-side coverage check (#128, 2026-05-27): DB stop_order_id
            # being NULL is a flawed proxy for "naked". After partial-exit
            # cycles or stop-replacement timing gaps, DB can show NULL while
            # broker has a working sell order covering the position. Before
            # placing a redundant stop (which Alpaca rejects with
            # `insufficient qty available`, surfacing as the BW #119 false
            # CRITICAL on 2026-05-27), confirm with the broker.
            try:
                existing = await alpaca.get_open_orders(
                    ticker, account_mode=account_mode,
                )
            except Exception as get_err:
                existing = []
                logger.warning(
                    f"stop_ack_watchdog: get_open_orders({ticker}) failed: "
                    f"{get_err} — proceeding with remediation (fail-open)"
                )
            sell_orders = [
                o for o in existing
                if str(o.get("side", "")).lower().endswith("sell")
            ]
            # Use REMAINING unfilled qty, not original order qty. A
            # partially-filled stop (388 of 776 already sold) has already
            # reduced the position to 388 shares; only 388 are still
            # broker-protected. Summing original qty would falsely classify
            # a half-naked position as fully covered.
            covered = sum(
                max(
                    float(o.get("qty") or 0) - float(o.get("filled_qty") or 0),
                    0.0,
                )
                for o in sell_orders
            )
            if qty > 0 and covered >= qty:
                stop_o = next(
                    (o for o in sell_orders
                     if "stop" in str(o.get("type", "")).lower()
                     or o.get("stop_price") is not None),
                    None,
                )
                if stop_o:
                    from agents.market_intelligence.broker.order_manager import (
                        set_stop_order_id,
                    )
                    await set_stop_order_id(
                        trade_id, stop_o["id"],
                        reason="watchdog_synced_from_broker",
                        account_mode=account_mode,
                    )
                await log_audit_event(
                    "stop_ack_broker_covered",
                    f"{ticker} #{trade_id}: broker has {covered} sh covering "
                    f"{qty} remaining "
                    f"(stop_order_id={'synced' if stop_o else 'no_stop_only_market'})",
                    detail=_json.dumps({
                        "trade_id": trade_id,
                        "ticker": ticker,
                        "account_mode": account_mode,
                        "remaining_shares": qty,
                        "broker_covered": covered,
                        "synced_stop_order_id": stop_o["id"] if stop_o else None,
                        "open_sell_orders": [
                            {"id": o["id"], "type": str(o.get("type")),
                             "qty": o.get("qty"), "stop_price": o.get("stop_price")}
                            for o in sell_orders
                        ],
                    }),
                )
                continue

            if qty <= 0 or stop_target is None:
                await log_audit_event(
                    "stop_ack_remediation_failed",
                    f"{ticker} #{trade_id}: cannot remediate — qty={qty}, orb_low={stop_target}",
                    detail=_json.dumps({
                        "trade_id": trade_id,
                        "ticker": ticker,
                        "account_mode": account_mode,
                        "filled_at": str(row["filled_at"]),
                        "reason": "missing_qty_or_orb_low",
                    }),
                )
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🚨🚨 *CRITICAL: STOP-ACK TIMEOUT + NO FALLBACK* {ticker}\n"
                    f"Trade #{trade_id} filled at {row['filled_at']:%H:%M:%S} ET, "
                    f"no stop_order_id, can't remediate (qty={qty}, orb_low={stop_target}).\n"
                    f"MANUAL INTERVENTION REQUIRED on Alpaca dashboard."
                )
                continue

            try:
                fallback = await alpaca.place_stop_order(
                    ticker, qty, stop_target, account_mode=account_mode,
                )
                # Update the row so subsequent watchdog runs don't re-fire
                from agents.market_intelligence.broker.order_manager import set_stop_order_id
                await set_stop_order_id(
                    trade_id, fallback["id"],
                    reason="stop_ack_timeout",
                    account_mode=account_mode,
                )
                await log_audit_event(
                    "stop_ack_timeout_remediated",
                    f"{ticker} #{trade_id}: stop-ACK timeout (filled_at "
                    f"{row['filled_at']:%H:%M:%S} ET, stop_order_id NULL >30s); "
                    f"fallback stop placed at ${stop_target:.2f} order={fallback['id']}",
                    detail=_json.dumps({
                        "trade_id": trade_id,
                        "ticker": ticker,
                        "account_mode": account_mode,
                        "filled_at": str(row["filled_at"]),
                        "qty": qty,
                        "stop_target": stop_target,
                        "fallback_order_id": fallback["id"],
                    }),
                )
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🛡 *STOP-ACK TIMEOUT — REMEDIATED:* {ticker}\n"
                    f"Trade #{trade_id} filled at {row['filled_at']:%H:%M:%S} ET, "
                    f"stop_order_id never populated.\n"
                    f"Fallback stop placed at ${stop_target:.2f}. Original OTO child "
                    f"stop-leg likely failed silently on Alpaca side."
                )
            except Exception as stop_err:
                await log_audit_event(
                    "stop_ack_remediation_failed",
                    f"{ticker} #{trade_id}: stop-ACK timeout AND fallback stop submit failed",
                    detail=_json.dumps({
                        "trade_id": trade_id,
                        "ticker": ticker,
                        "account_mode": account_mode,
                        "stop_target": stop_target,
                        "stop_error": f"{type(stop_err).__name__}: {str(stop_err)[:200]}",
                    }),
                )
                await send_telegram_message(
                    f"{mode_prefix(account_mode)}🚨🚨 *CRITICAL: POSITION NAKED, REMEDIATION FAILED* {ticker}\n"
                    f"Trade #{trade_id} filled at {row['filled_at']:%H:%M:%S} ET, "
                    f"no stop, fallback also failed: {stop_err}\n"
                    f"MANUAL INTERVENTION REQUIRED on Alpaca dashboard NOW."
                )


async def _track_open_position_extremes_job():
    """Run every 5 min during market hours (9:30 AM - 4:00 PM ET, mon-fri).

    Polls Polygon for minute bars per open ticker, then updates each open
    trade's lowest_price_seen / highest_price_seen via monotonic
    LEAST/GREATEST. Feeds setup-quality analytics — does this setup let
    trades run high before exit (good edge to keep) or drag toward stop
    (tighten or drop)?
    """
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    try:
        from agents.market_intelligence.broker.order_manager import (
            track_open_position_extremes,
        )
        n = await track_open_position_extremes()
        if n:
            logger.info(f"track_position_extremes: updated {n} open trade rows")
    except Exception as e:
        logger.error(f"track_position_extremes failed: {e}")


async def _evening_position_backstop_job():
    """Run at 9:00 PM ET. Backstop sync_positions catching late EXPIRED events
    or earlier remediation failures — market closed, no other jobs running, so
    a fresh orphan scan + retry costs nothing and closes the gap before next day's open."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    logger.info("Evening position backstop starting...")
    try:
        from agents.market_intelligence.broker.order_manager import sync_positions
        discrepancies = await sync_positions()
        logger.info(f"Evening backstop: {len(discrepancies)} discrepancies")
    except Exception as e:
        logger.error(f"Evening position backstop failed: {e}")
        await notify_job_failure("evening_position_backstop", str(e))


async def _shadow_orb_entry_job():
    """Run at 10:00 AM ET. 5-min shadow ORB entry pass — telemetry only.

    Records would-be 5-min ORB entries for every live MAGNA53 HIGH + 9M
    Day-2 candidate so we can compare 1m vs 5m bar-size outcomes. No
    Alpaca submits, no new alerts.
    """
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.broker.shadow_orb_tracker import run_shadow_pass
    today = et_today()
    if not get_market_status(today).is_trading_day:
        return None
    logger.info("Shadow ORB entry pass starting...")
    try:
        counts = await run_shadow_pass(today)
        logger.info(f"Shadow ORB entry pass complete: {counts}")
        return counts.get("open", 0)
    except Exception as e:
        logger.error(f"Shadow ORB entry pass failed: {e}")
        await notify_job_failure("shadow_orb_entry", str(e))
        return None


async def _shadow_orb_exit_job():
    """Run at 4:30 PM ET. Apply daily exit step to every open shadow row."""
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.broker.shadow_orb_tracker import update_shadow_positions
    today = et_today()
    if not get_market_status(today).is_trading_day:
        return None
    logger.info("Shadow ORB exit pass starting...")
    try:
        counts = await update_shadow_positions(today)
        logger.info(f"Shadow ORB exit pass complete: {counts}")
        return counts.get("closed", 0) + counts.get("updated", 0)
    except Exception as e:
        logger.error(f"Shadow ORB exit pass failed: {e}")
        await notify_job_failure("shadow_orb_exit", str(e))
        return None


async def _orb_window_cleanup_job():
    """Run at 10:00 AM ET. Cancel unfilled ORB entries that haven't triggered.
    If the stop-limit buy hasn't filled in the first 29 min, the ORB high wasn't
    broken during the window — the setup is invalid and the pending order should
    not sit for six more hours waiting for a failed-gap-reclaim bounce."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    logger.info("ORB window cleanup starting (10:00 AM cancel)...")
    try:
        from agents.market_intelligence.broker.order_manager import cancel_unfilled_entries
        cancelled = await cancel_unfilled_entries(reason="ORB window unfilled")
        logger.info(f"ORB window cleanup: {cancelled} cancelled")
    except Exception as e:
        logger.error(f"ORB window cleanup failed: {e}")
        await notify_job_failure("orb_window_cleanup", str(e))


async def _eod_ep_recap_job():
    """Run at 4:10 PM ET. One-shot Telegram summary of today's HIGH EP outcomes.

    Fires after _eod_cleanup_job (4:05 PM) so trade rows reflect the settled state.
    On zero-HIGH days: still posts a short feed-telemetry recap when any
    bar-fetch or feed-failure events occurred, so silent SIP degradation
    (subscription lapse, auth failure) surfaces even without HIGH activity.
    Fully silent only when the day had zero HIGH alerts AND zero feed events.
    """
    logger.info("EOD EP recap starting...")
    try:
        from agents.market_intelligence.db import get_ep_outcomes, get_sip_feed_telemetry
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.broker.alpaca_client import get_data_feed
        today = et_today()
        today_str = str(today)
        outcomes = await get_ep_outcomes(days_back=1, tier="HIGH")
        today_outcomes = [o for o in outcomes if str(o.get("alert_date")) == today_str]

        feed_tel = await get_sip_feed_telemetry(today)
        feed = get_data_feed().value.lower()
        feed_line = (
            f"📡 Feed ({feed}): {feed_tel['bars_fetched']} bars · "
            f"{feed_tel['zero_range']} zero-range · "
            f"{feed_tel['subscribe_failed']} subscribe-fail · "
            f"{feed_tel['stream_disconnect']} disconnect"
        )
        feed_alert = (
            feed_tel["subscribe_failed"] > 0
            or (feed == "sip" and feed_tel["zero_range"] > 0 and feed_tel["bars_fetched"] > 0)
        )

        if not today_outcomes:
            # Still report feed health — the silent-feed case is exactly why this exists.
            if feed_alert or feed_tel["bars_fetched"] > 0:
                prefix = "⚠️ " if feed_alert else ""
                await send_telegram_message(
                    f"{prefix}*EP EOD Recap — {today_str}*\n"
                    f"No HIGH EPs today.\n{feed_line}"
                )
            logger.info("EOD EP recap: no HIGH EPs today")
            return

        entered_states = {"filled", "closed", "order_placed", "pending_confirmation", "confirmed", "submitting"}
        entered = [o for o in today_outcomes if o.get("pt_status") in entered_states]
        missed = [o for o in today_outcomes if o not in entered]

        lines = [
            f"📊 *EP EOD Recap — {today_str}*",
            f"HIGH: {len(today_outcomes)} detected → {len(entered)} entered · {len(missed)} missed",
        ]
        for o in entered[:5]:
            pnl = o.get("total_pnl")
            pnl_str = f" ${float(pnl):+,.0f}" if pnl is not None else ""
            lines.append(f"  • `{o['ticker']}` entered{pnl_str}")
        from agents.market_intelligence.broker.skip_reasons import humanize
        for o in missed[:8]:
            lines.append(f"  • `{o['ticker']}` — {humanize(o.get('skip_reason'))}")
        dropped = max(0, len(missed) - 8)
        if dropped:
            lines.append(f"  • …{dropped} more missed")

        lines.append(feed_line)
        if feed_alert:
            lines.insert(0, "⚠️ *Feed health flagged — see 📡 line below*")

        await send_telegram_message("\n".join(lines))
        logger.info("EOD EP recap sent")
    except Exception as e:
        logger.error(f"EOD EP recap failed: {e}")
        await notify_job_failure("eod_ep_recap", str(e))


async def _post_eod_audit_job():
    """Run at 4:15 PM ET. Trade-side invariants + metrics scan post-EOD cleanup.

    Reads settled `mi_live_trades` rows after 4:05 EOD cleanup and 4:10 recap.
    L1 invariant breaches and L2 metric anomalies fire Telegram immediately;
    L3 drift is silent (rolled up in Sunday digest).
    """
    logger.info("Post-EOD audit starting...")
    try:
        from agents.market_intelligence.system_audit import run_post_eod_audit
        result = await run_post_eod_audit()
        logger.info(f"Post-EOD audit: {result}")
    except Exception as e:
        logger.error(f"Post-EOD audit failed: {e}", exc_info=True)
        await notify_job_failure("post_eod_audit", str(e))


async def _crypto_nightly_ingest_job():
    """Run at 6:00 PM ET. Crypto RS shadow-mode ingest pipeline.

    See agents/market_intelligence/crypto/ingest.py::run_nightly for details.
    Always-on data collection regardless of CRYPTO_RS_ENABLED flag — the flag
    only gates Telegram surfaces, not ingest itself.
    """
    logger.info("Crypto RS nightly ingest starting...")
    try:
        from agents.market_intelligence.crypto.ingest import run_nightly
        result = await run_nightly()
        logger.info(f"Crypto RS ingest: {result}")
        return int(result.get("coins_scored") or 0)
    except Exception as e:
        logger.error(f"Crypto RS ingest failed: {e}", exc_info=True)
        await notify_job_failure("crypto_nightly_ingest", str(e))
        return None


async def _crypto_category_refresh_job():
    """Run Sundays at 19:00 ET. Refresh CG category membership for all
    universe coins -> crypto_categories table.

    Heavy CG fanout (~250 /coins/{id} calls); rate-limited to 30/min.
    Daily would burn the budget for no benefit since taxonomy is low-churn.
    """
    logger.info("Crypto category refresh starting...")
    try:
        from agents.market_intelligence.crypto.categories import refresh_category_membership
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT coin_id FROM crypto_universe ORDER BY mcap_rank NULLS LAST LIMIT 250"
            )
        coin_ids = [r["coin_id"] for r in rows]
        n = await refresh_category_membership(coin_ids)
        logger.info(f"Crypto category refresh: {n} (coin, category) pairs")
        return int(n or 0)
    except Exception as e:
        logger.error(f"Crypto category refresh failed: {e}", exc_info=True)
        await notify_job_failure("crypto_category_refresh", str(e))
        return None


async def _parabolic_scan_job():
    """Run at 5:15 PM ET. Scan universe for parabolic-short candidates.

    Slots between 5:00 PM nightly_data_pull (which refreshes mi_daily_closes)
    and 5:30 PM post_nightly_audit. Persists every scored ticker (incl.
    `unqualified`) to mi_parabolic_candidates so thresholds can be tuned
    against historical scans. Telegram digest only fires on non-empty results
    (parabolas are rare — silence is the expected daily state).
    """
    logger.info("Parabolic scan starting...")
    try:
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.parabolic_detector import (
            run_parabolic_scan, send_parabolic_digest,
        )
        by_stage = await run_parabolic_scan(et_today())
        await send_parabolic_digest(by_stage)
    except Exception as e:
        logger.error(f"Parabolic scan failed: {e}", exc_info=True)
        await notify_job_failure(JOB_PARABOLIC_SCAN, str(e))


async def _sugar_babies_cohort_refresh_job():
    """Run at 5:18 PM ET. Rebuild persistent Sugar Babies cohort (Pradeep-class
    watchlist): tickers that printed 9M+ EOD volume ≥3 times in trailing 180d.

    Pure observability — no trade impact. Surfaced via `/sugarbabies` Telegram
    command and the evening briefing 🍬 Persistent Sugar Babies section.

    Slots between 5:15 parabolic_scan and 5:20 fishhook_eod. Fast aggregation
    query (~24 rows) — runs in milliseconds. mi_daily_closes volume is the
    ground truth (catches confirmed + materialized-anticipation alert days
    uniformly; the 12% of anticipations that didn't pan out are excluded by
    the join on actual EOD volume).
    """
    logger.info("Sugar Babies cohort refresh starting...")
    try:
        from agents.market_intelligence.collector import et_today
        today = et_today()
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                WITH eligible AS (
                    -- Ground truth: alert fired AND EOD volume actually hit
                    -- 9M+. Joins to mi_daily_closes for confirmation.
                    -- Catches confirmed prints AND materialized anticipations.
                    SELECT DISTINCT ON (a.ticker, a.alert_date)
                           a.ticker, a.alert_date, a.today_volume, a.gap_pct
                    FROM mi_9m_ep_alerts a
                    JOIN mi_daily_closes d
                        ON d.ticker = a.ticker
                       AND d.trade_date = a.alert_date
                    WHERE a.alert_date >= $1::date - INTERVAL '180 days'
                      AND d.volume >= 9000000
                    -- Prefer confirmed row over anticipation when both exist
                    ORDER BY a.ticker, a.alert_date, a.is_anticipation ASC
                ),
                grouped AS (
                    SELECT ticker,
                           COUNT(*) AS n,
                           MIN(alert_date) AS first_in_win,
                           MAX(alert_date) AS last_in_win
                    FROM eligible
                    GROUP BY ticker
                    HAVING COUNT(*) >= 3
                ),
                latest AS (
                    SELECT DISTINCT ON (e.ticker)
                           e.ticker, e.today_volume, e.gap_pct
                    FROM eligible e
                    JOIN grouped g ON g.ticker = e.ticker
                    ORDER BY e.ticker, e.alert_date DESC
                )
                INSERT INTO mi_sugar_babies_cohort
                    (ticker, cohort_date, count_9m_alerts_180d,
                     first_9m_alert_in_window, last_9m_alert,
                     latest_volume, latest_gap_pct)
                SELECT g.ticker, $1::date, g.n,
                       g.first_in_win, g.last_in_win,
                       l.today_volume, l.gap_pct
                FROM grouped g
                JOIN latest l ON l.ticker = g.ticker
                ON CONFLICT (ticker, cohort_date) DO UPDATE SET
                    count_9m_alerts_180d     = EXCLUDED.count_9m_alerts_180d,
                    first_9m_alert_in_window = EXCLUDED.first_9m_alert_in_window,
                    last_9m_alert            = EXCLUDED.last_9m_alert,
                    latest_volume            = EXCLUDED.latest_volume,
                    latest_gap_pct           = EXCLUDED.latest_gap_pct
            """, today)
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM mi_sugar_babies_cohort WHERE cohort_date = $1",
                today,
            )
        await log_audit_event(
            "sugar_babies_cohort_refreshed",
            f"Cohort size: {n} tickers (≥3 9M EOD prints in trailing 180d)",
        )

        # Stocks-in-Play dual-write (#99, ADR 0004 Phase 1 first migration,
        # 2026-05-23). For each cohort member, upsert into mi_stocks_in_play
        # as 'sugar_baby_cohort' methodology-presence signal with
        # automation_class='informational'. Failure here MUST NOT break
        # the upstream sugar_babies_cohort write (telemetry decoupling).
        try:
            from agents.market_intelligence.db import upsert_stocks_in_play
            from agents.market_intelligence.stocks_in_play_sources import (
                SOURCE_SUGAR_BABY_COHORT, CLASS_INFORMATIONAL,
            )
            # Expiry: 4-day TTL covers long weekends (Memorial Day Mon
            # refresh skipped → Friday rows must stay valid through Tuesday).
            # Per ADR 0004 §3 expiry policy.
            expires_at = datetime.combine(today + timedelta(days=4),
                                          _dt_time(23, 59), tzinfo=_ET)
            # NOTE: the original `async with pool.acquire() as conn` block
            # exits at the previous fetchval — `conn` is stale here. Open
            # a fresh connection for the dual-write fetch.
            async with pool.acquire() as conn2:
                cohort_rows = await conn2.fetch("""
                    SELECT ticker, count_9m_alerts_180d, first_9m_alert_in_window, last_9m_alert
                    FROM mi_sugar_babies_cohort
                    WHERE cohort_date = $1
                """, today)
            sip_count = 0
            for r in cohort_rows:
                await upsert_stocks_in_play(
                    ticker=r["ticker"],
                    source_detector=SOURCE_SUGAR_BABY_COHORT,
                    automation_class=CLASS_INFORMATIONAL,
                    reason=f"Pradeep persistent cohort — {r['count_9m_alerts_180d']}× 9M+ EOD prints in trailing 180d",
                    readiness_signal={
                        "count_9m_alerts_180d": r["count_9m_alerts_180d"],
                        "first_9m_alert_in_window": str(r["first_9m_alert_in_window"]),
                        "last_9m_alert": str(r["last_9m_alert"]),
                    },
                    expires_at=expires_at,
                    entry_date=today,
                )
                sip_count += 1
            logger.info(f"mi_stocks_in_play: upserted {sip_count} sugar_baby_cohort rows")
        except Exception as e:
            logger.warning(f"mi_stocks_in_play dual-write failed (non-critical): {e}")

        logger.info(f"Sugar Babies cohort refreshed: {n} tickers")
        return int(n) if n is not None else None
    except Exception as e:
        logger.error(f"Sugar Babies cohort refresh failed: {e}", exc_info=True)
        await notify_job_failure(JOB_SUGAR_BABIES_COHORT_REFRESH, str(e))
        return None


async def _flag_break_scan_job():
    """Run every 5 min during market hours. Intraday flag-break detector
    (#94, ADR 0005, 2026-05-23 ship Commit 1).

    Cron fires hourly minute=*/5 9-15 (Mon-Fri); this function gates
    internally to 9:35 AM – 3:55 PM ET so we skip pre-9:35 (opening
    range settles) and post-3:55 (closing-auction noise). Pattern
    matches run_9m_scan's internal time gate.

    Telemetry-only first ship: writes mi_flag_breaks rows + audit events +
    Telegram alert. No entry execution. Forward-return validation gated
    on N>=10 settled breaks (data_gated_reviews.yaml::intraday_flag_break
    review, filed in Commit 2).
    """
    now_et = datetime.now(_ET)
    if not (_dt_time(9, 35) <= now_et.time() <= _dt_time(15, 55)):
        return 0
    try:
        from agents.market_intelligence.flag_detector import run_intraday_flag_break_scan
        n = await run_intraday_flag_break_scan(now_et)
        return int(n) if n is not None else 0
    except Exception as e:
        logger.error(f"intraday_flag_break_scan failed: {e}", exc_info=True)
        await notify_job_failure(JOB_FLAG_BREAK_SCAN, str(e))
        return None


async def _support_test_scan_job():
    """Run every 5 min during market hours. Intraday support-test detector
    (#95, entry-technique #2, 2026-05-24 ship).

    Counter-trend mechanic — detects when price tests base_low and bounces.
    Cron fires minute=*/5 9-15 (Mon-Fri); function gates internally to
    9:35 AM – 3:55 PM ET. NO volume gate per Morales methodology.
    Telemetry-only shadow phase; N>=10 settled before paper.
    """
    now_et = datetime.now(_ET)
    if not (_dt_time(9, 35) <= now_et.time() <= _dt_time(15, 55)):
        return 0
    try:
        from agents.market_intelligence.flag_detector import run_intraday_support_test_scan
        n = await run_intraday_support_test_scan(now_et)
        return int(n) if n is not None else 0
    except Exception as e:
        logger.error(f"intraday_support_test_scan failed: {e}", exc_info=True)
        await notify_job_failure(JOB_SUPPORT_TEST_SCAN, str(e))
        return None


async def _ma_pullback_scan_job():
    """Run every 5 min during market hours. Intraday MA-pullback detector
    (#96, entry-technique #3, 2026-05-24 ship).

    Classic VCP/Minervini pullback to SMA10 or SMA20 inside the range.
    LIGHT-VOLUME gate (today_pace ≤ ADV) — the defining characteristic.
    Telemetry-only shadow phase; N>=10 settled before paper.
    """
    now_et = datetime.now(_ET)
    if not (_dt_time(9, 35) <= now_et.time() <= _dt_time(15, 55)):
        return 0
    try:
        from agents.market_intelligence.flag_detector import run_intraday_ma_pullback_scan
        n = await run_intraday_ma_pullback_scan(now_et)
        return int(n) if n is not None else 0
    except Exception as e:
        logger.error(f"intraday_ma_pullback_scan failed: {e}", exc_info=True)
        await notify_job_failure(JOB_MA_PULLBACK_SCAN, str(e))
        return None


# Machine reason → human prose map (#143/#148 2026-05-28). Used by the
# downgrade digest so operator-facing lines read as English instead of
# `rubric_composite_11.0_below_22_label_weak`.
_DOWNGRADE_REASON_STATIC = {
    "q_rev_yoy_missing_no_prior_year_comparable": "Q-rev YoY missing (no prior-year comparable)",
    "news_corpus_sparse_no_q_rev": "news corpus sparse, no Q-rev data",
    "extraction_quality_low": "catalyst extraction confidence low",
}

_DOWNGRADE_REASON_RUBRIC_RE = re.compile(
    r"^rubric_composite_(?P<score>[\d.]+)_below_(?P<thresh>\d+)_label_(?P<label>\w+)$"
)


def _md_escape(s: str) -> str:
    """Escape Telegram Markdown V1 control chars (`_`, `*`) in dynamic content.

    Filed as #148, 2026-05-28: the downgrade digest's reason strings
    (e.g. `news_corpus_sparse_no_q_rev`) and `from_quality` values
    (e.g. `game_changer`) contain `_` which Markdown V1 reads as italic
    delimiters. Unbalanced `_` count → Telegram 400. send_telegram_message
    has a plain-text fallback but the cosmetic gap is visible.

    Backticks deliberately NOT escaped — code spans are useful and
    they're already escaped at template time when present.
    """
    if not s:
        return ""
    return s.replace("_", r"\_").replace("*", r"\*")


def _humanize_downgrade_reason(reason: str) -> str:
    """Convert machine reason code to operator-facing prose.

    Examples:
    - `rubric_composite_11.0_below_22_label_weak` → `rubric 11/39 below 22 floor (weak)`
    - `q_rev_yoy_missing_no_prior_year_comparable` → `Q-rev YoY missing (no prior-year comparable)`
    - unrecognized → reason verbatim with underscores spaced
    """
    if not reason:
        return ""
    if reason in _DOWNGRADE_REASON_STATIC:
        return _DOWNGRADE_REASON_STATIC[reason]
    m = _DOWNGRADE_REASON_RUBRIC_RE.match(reason)
    if m:
        score = m.group("score").rstrip("0").rstrip(".") or m.group("score")
        return f"rubric {score}/39 below {m.group('thresh')} floor ({m.group('label')})"
    # Fallback: replace underscores with spaces so the raw reason is at
    # least readable, even if we don't have a templated translation.
    return reason.replace("_", " ")


async def _catalyst_downgrade_digest_job():
    """Morning roll-up of catalyst-downgrade alerts (#143, 2026-05-28).

    Queries mi_audit_log for today's `catalyst_earnings_revenue_weak_downgrade`
    events and renders them into a compact digest at 10:10 ET (5 min
    after EP scan window closes at 10:00). Empty day → no Telegram.

    2026-05-28 ship-day bug: original implementation drained an
    in-process accumulator in ep_detector, which got reset on the
    10:04:31 container restart and lost the morning's 9 downgrades.
    Same in-process-state-vs-restart bug class as the IBM `sync_positions`
    fix (#137) and the EP watchdog (commit 99f66f1). The audit row is
    the source of truth; sourcing the digest from it survives any
    restart, deploy, or process-recycle event.

    Audit log retains per-ticker rows for `/rubric TICKER` drilldown.
    """
    from agents.market_intelligence.collector import _ET
    from agents.market_intelligence.audit_events import (
        CATALYST_EARNINGS_REVENUE_WEAK_DOWNGRADE,
    )
    now_et = datetime.now(_ET)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT summary, detail, created_at
            FROM mi_audit_log
            WHERE event_type = $2
              AND (created_at AT TIME ZONE 'America/New_York')::date = $1
            ORDER BY created_at ASC
            """,
            now_et.date(),
            CATALYST_EARNINGS_REVENUE_WEAK_DOWNGRADE,
        )

    if not rows:
        return 0

    lines = [
        f"📉 *Catalyst downgrades — morning digest ({len(rows)})*",
        "_LLM-graded narrative strong, methodology rubric disagrees._",
        "",
    ]
    for r in rows:
        # Summary shape from ep_detector audit emit:
        #   "{TICKER}: {from_quality} → routine (earnings catalyst, {reason})"
        # Markdown-escape the dynamic content — `from_quality` (e.g.
        # `game_changer`) and the humanized reason can both contain `_`
        # which Markdown V1 parses as italic delimiters (#148).
        summary = r["summary"] or ""
        inner = summary.split("(earnings catalyst, ", 1)
        if len(inner) == 2:
            head = inner[0].rstrip(" (")
            reason_raw = inner[1].rstrip(")")
            reason_human = _humanize_downgrade_reason(reason_raw)
            lines.append(f"• {_md_escape(head)} — {_md_escape(reason_human)}")
        else:
            lines.append(f"• {_md_escape(summary)}")
    lines.append("")
    lines.append("_Drilldown: `/rubric TICKER` for full breakdown._")
    try:
        await send_telegram_message("\n".join(lines))
    except Exception as e:
        logger.error(f"catalyst_downgrade_digest Telegram failed: {e}")
    return len(rows)


async def _9m_pace_digest_job():
    """Hourly rollup of 9M EP pace (anticipation) alerts (#133, 2026-05-27).

    Pace alerts are projection-based — "this ticker is on track to hit 9M
    by close" — not realtime-actionable. They were 89% of yesterday's
    pinged 9M volume (16/18). Removed from the per-5-min digest in
    ninem_detector; this job rolls them up at top of hour for 10/11/12
    ET, querying mi_9m_ep_alerts for the prior 60-min ET window.

    Dedup: skip tickers that ALSO fired as actual in the same hour (they
    already got a realtime ping). Cap at 10 lines (rare, but avoids
    runaway digest).

    Empty hour → no Telegram.
    """
    pool = await get_pool()
    now_et = datetime.now(_ET)
    window_end = now_et.replace(minute=0, second=0, microsecond=0)
    window_start = window_end - timedelta(hours=1)

    # `created_at` is TIMESTAMPTZ — compare directly against tz-aware
    # datetime params. Original SQL applied `AT TIME ZONE 'America/New_York'`
    # to the column (yielding naive TIMESTAMP) while passing tz-aware params,
    # which asyncpg refuses with "can't subtract offset-naive and offset-aware
    # datetimes" — caught 2026-05-28 first-fire, job failed in 89ms.
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, projected_vol, current_price, gap_pct
            FROM mi_9m_ep_alerts
            WHERE is_anticipation = TRUE
              AND created_at >= $1
              AND created_at <  $2
            """,
            window_start, window_end,
        )
        actual_tickers_row = await conn.fetch(
            """
            SELECT DISTINCT ticker
            FROM mi_9m_ep_alerts
            WHERE is_anticipation = FALSE
              AND created_at >= $1
              AND created_at <  $2
            """,
            window_start, window_end,
        )

    if not rows:
        return 0

    actual_set = {r["ticker"] for r in actual_tickers_row}
    seen: dict[str, dict] = {}
    for r in rows:
        if r["ticker"] in actual_set:
            continue
        # Most-recent row per ticker wins (highest projection within window)
        prior = seen.get(r["ticker"])
        if prior is None or (r["projected_vol"] or 0) > (prior["projected_vol"] or 0):
            seen[r["ticker"]] = dict(r)

    if not seen:
        return 0

    ranked = sorted(
        seen.values(),
        key=lambda r: (r["projected_vol"] or 0),
        reverse=True,
    )[:10]

    clock_start = window_start.strftime("%H:%M")
    clock_end = window_end.strftime("%H:%M")
    parts = [
        f"🏦 *9M EP Pace — {clock_start}–{clock_end} ET ({len(ranked)})*",
    ]
    for r in ranked:
        proj_m = (r["projected_vol"] or 0) / 1_000_000
        parts.append(
            f"• `{r['ticker']}` ~{proj_m:.1f}M proj "
            f"${r['current_price']:.2f} +{(r['gap_pct'] or 0):.1f}%"
        )
    try:
        await send_telegram_message("\n".join(parts))
    except Exception as e:
        logger.error(f"9m_pace_digest Telegram failed: {e}")
    return len(ranked)


async def _order_status_reconcile_job():
    """Periodic DB↔Alpaca order-status reconciliation (#123, 2026-05-26).

    Catches silent stops (Apollo never sees the trade_update stream event)
    and stuck PENDING_NEW/new/accepted orders that diverge from Alpaca's
    authoritative state. Runs every 15 min during market hours +
    one-shot on container boot.

    Audit-only — no Telegram (advisor 2026-05-26: retroactive 'stop fired
    hours ago' alerts are operationally confusing; operator drills via
    `/audit order_status_reconciled`).
    """
    try:
        from agents.market_intelligence.broker.order_manager import reconcile_all_modes
        result = await reconcile_all_modes()
        if result.get("updated", 0) > 0 or result.get("errors", 0) > 0:
            logger.info(
                f"order_status_reconcile: examined={result['examined']} "
                f"updated={result['updated']} errors={result['errors']}"
            )
        return result.get("updated", 0)
    except Exception as e:
        logger.error(f"order_status_reconcile_job failed: {e}", exc_info=True)
        await notify_job_failure(JOB_ORDER_STATUS_RECONCILE, str(e))
        return None


async def _backup_health_check_job():
    """Daily check that off-site backup completed within last 36h.

    Cron runs nightly at 02:00 ET (host-level /home/apollo/backup.sh).
    Success writes `gdrive_backup_success` audit row; failure writes
    `gdrive_backup_failed` + Telegrams from the bash script directly.
    This check is the BACKSTOP: if the cron itself stops firing (host
    reboot, cron daemon down), no audit row gets written at all —
    silent failure. This job alerts on absence.

    Fires at 04:30 ET (2.5 hours after backup runs at 02:00 ET) so a
    slow upload has time to complete. Stale threshold: 36h covers
    weekend + Memorial-Day-class gaps without flapping.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
              MAX(CASE WHEN event_type='gdrive_backup_success'  THEN created_at END) AS last_pg,
              MAX(CASE WHEN event_type='gdrive_secrets_success' THEN created_at END) AS last_secrets,
              MAX(CASE WHEN event_type IN (
                  'gdrive_backup_failed','gdrive_secrets_failed',
                  'backup_failed','secrets_backup_skipped'
              ) THEN created_at END) AS last_failure
            FROM mi_audit_log
        """)
    last_pg, last_secrets, last_failure = row["last_pg"], row["last_secrets"], row["last_failure"]

    now = datetime.now(_ET)

    if last_pg is None:
        await send_telegram_message(
            "🚨 *Apollo off-site backup MISSING*\n"
            "No `gdrive_backup_success` event ever recorded.\n"
            "Run `/home/apollo/backup.sh` manually to surface the failure mode.",
            parse_mode="Markdown",
        )
        return

    pg_hours = (now - last_pg.astimezone(_ET)).total_seconds() / 3600.0
    secrets_hours = (
        (now - last_secrets.astimezone(_ET)).total_seconds() / 3600.0
        if last_secrets else None
    )

    fail_note = ""
    if last_failure and last_failure > last_pg:
        fail_note = f"\nLast failure: {last_failure.astimezone(_ET).strftime('%Y-%m-%d %H:%M ET')}"

    if pg_hours > 36:
        await send_telegram_message(
            f"🚨 *Apollo off-site backup STALE*\n"
            f"Last `gdrive_backup_success`: {last_pg.astimezone(_ET).strftime('%Y-%m-%d %H:%M ET')} "
            f"({pg_hours:.1f}h ago){fail_note}\n"
            f"Check `/home/apollo/backups/gdrive.log` on prod.",
            parse_mode="Markdown",
        )
    elif secrets_hours is None or secrets_hours > 36:
        # pg_dump fresh but encrypted secrets blob stale → passphrase file
        # probably missing or GPG failing. Defense in depth per advisor 2026-05-23.
        secrets_summary = (
            "never recorded" if secrets_hours is None
            else f"last {last_secrets.astimezone(_ET).strftime('%Y-%m-%d %H:%M ET')} ({secrets_hours:.1f}h ago)"
        )
        await send_telegram_message(
            f"🚨 *Apollo secrets backup STALE*\n"
            f"pg_dump is current ({pg_hours:.1f}h ago) but encrypted secrets blob is {secrets_summary}.\n"
            f"Recreate `/home/apollo/.backup-passphrase` per `docs/ops/disaster_recovery.md` Phase 6.{fail_note}",
            parse_mode="Markdown",
        )


async def _flag_scan_job():
    """Run at 5:25 PM ET. Continuation-flag detector daily pass.

    Slots between 5:20 fishhook_eod and 5:30 post_nightly_audit. Persists
    every scored ticker (incl. `unqualified`) to mi_flag_candidates so
    thresholds can be retuned offline. TRIGGERED rows fire single-ticker
    Telegram alerts as found; daily digest summarizes the rest with
    zero-suppression on quiet days.
    """
    logger.info("Flag scan starting...")
    try:
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.flag_detector import run_flag_scan
        by_stage = await run_flag_scan(et_today())
        # send_flag_digest is invoked from within run_flag_scan (same pattern
        # as parabolic_detector — keeps the per-ticker TRIGGERED alerts
        # ordered before the digest).
        n_total = sum(len(v) for v in by_stage.values())
        return int(n_total)
    except Exception as e:
        logger.error(f"Flag scan failed: {e}", exc_info=True)
        await notify_job_failure(JOB_FLAG_SCAN, str(e))
        return None


async def _wick_forward_returns_job():
    """Run at 5:45 PM ET. Walk unsettled wick rows whose 10-trading-session
    horizon has elapsed and write filled_wick + fwd_Nd_from_{high,close}.

    Slots after 5:30 post_nightly_audit so the audit window doesn't collide.
    Idempotent — `get_unsettled_wick_candidates` returns only rows with
    fwd_10d_from_close_pct IS NULL within a bounded 20-day lookback.
    """
    logger.info("Wick forward-returns starting...")
    try:
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.wick_tracker import update_forward_returns
        n = await update_forward_returns(et_today())
        logger.info(f"Wick forward-returns: settled {n} rows")
        return None
    except Exception as e:
        logger.error(f"Wick forward-returns failed: {e}", exc_info=True)
        await notify_job_failure(JOB_WICK_FORWARD_RETURNS, str(e))
        return None


async def _fishhook_eod_job():
    """Run at 5:20 PM ET. Fishhook V3 (gap-up undercut & reclaim) state-machine pass.

    Slots between 5:15 parabolic_scan and 5:30 post_nightly_audit. Detects
    today's gap-up anchors (gap≥8%, close>open) and walks every open anchor
    forward to advance state (pending → promoted → reclaimed → settled).
    Shadow phase — no orders, no Telegram alerts; rows accrue in
    mi_fishhook_anchors for promotion review.
    """
    logger.info("Fishhook EOD pass starting...")
    try:
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.fishhook_detector import run_eod_pass
        n = await run_eod_pass(et_today())
        logger.info(f"Fishhook EOD pass: {n} rows touched")
        return None
    except Exception as e:
        logger.error(f"Fishhook EOD pass failed: {e}", exc_info=True)
        await notify_job_failure(JOB_FISHHOOK_EOD, str(e))
        return None


async def _post_nightly_audit_job():
    """Run at 5:30 PM ET. Theme/cooldown/regime invariants + metrics scan post-data-pull.

    Fires after _nightly_data_pull (5:00 PM) so themes/cooldowns/regime reflect
    tonight's run. Critical for catching zombie themes, cooldown floods,
    9M alert regressions before the next morning's briefing.
    """
    logger.info("Post-nightly audit starting...")
    try:
        from agents.market_intelligence.system_audit import run_post_nightly_audit
        result = await run_post_nightly_audit()
        logger.info(f"Post-nightly audit: {result}")
    except Exception as e:
        logger.error(f"Post-nightly audit failed: {e}", exc_info=True)
        await notify_job_failure("post_nightly_audit", str(e))


async def _theme_round_trip_validator_job():
    """Run daily at 6:00 AM ET (Area 2, 2026-05-15).

    Defense-in-depth secondary catch for the class of bugs where an LLM-
    generated theme has most of its members stripped by validation soon
    after creation. Area 1's carryforward filter handles the "stale
    members persist" case; this catches the "brand new theme born bad"
    case — a theme created/modified on day D where ≥50% of its members
    were stripped within the next 3 days.

    Today's biotech case (had Area 1 been in place) wouldn't have caught
    the FIRST-day-of-cycle hallucination — only its persistence. This job
    closes that gap by firing immediately on the day the strip rate
    crosses 50%.

    Pure observability — no new schema, no LLM calls, no write authorities.
    SQL + audit event + Telegram line. Dedup by (theme_name, day) via
    audit-log presence so same theme doesn't re-alarm.
    """
    from agents.market_intelligence.db import get_pool, log_audit_event
    from agents.market_intelligence.briefing import send_telegram_message

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH recent_themes AS (
                SELECT
                    name,
                    theme_date,
                    tickers,
                    created_at,
                    array_length(tickers, 1) AS member_count
                FROM mi_themes
                WHERE created_at >= NOW() - INTERVAL '7 days'
            ),
            strips AS (
                SELECT theme_name, ticker, removed_at
                FROM mi_validation_cooldowns
                WHERE removed_at >= NOW() - INTERVAL '10 days'
            )
            SELECT
                t.name,
                t.theme_date,
                t.created_at,
                t.member_count,
                COUNT(DISTINCT s.ticker) FILTER (
                    WHERE s.ticker = ANY(t.tickers)
                      AND s.removed_at BETWEEN t.created_at
                                          AND t.created_at + INTERVAL '3 days'
                ) AS stripped_within_3d
            FROM recent_themes t
            LEFT JOIN strips s ON s.theme_name = t.name
            WHERE t.member_count >= 2
            GROUP BY t.name, t.theme_date, t.created_at, t.tickers, t.member_count
            HAVING COUNT(DISTINCT s.ticker) FILTER (
                       WHERE s.ticker = ANY(t.tickers)
                         AND s.removed_at BETWEEN t.created_at
                                             AND t.created_at + INTERVAL '3 days'
                   ) >= GREATEST(2, (t.member_count * 0.5)::int)
            ORDER BY t.created_at DESC
        """)
        # Dedup: skip if we've already alarmed for this (theme, theme_date)
        for row in rows:
            already = await conn.fetchval(
                """
                SELECT 1 FROM mi_audit_log
                WHERE event_type='theme_high_strip_rate'
                  AND summary LIKE $1
                  AND created_at > NOW() - INTERVAL '7 days'
                LIMIT 1
                """,
                f"%{row['name']}%{row['theme_date']}%",
            )
            if already:
                continue
            stripped = row["stripped_within_3d"]
            count = row["member_count"]
            pct = (stripped / count * 100) if count else 0
            summary = (
                f"'{row['name']}' ({row['theme_date']}): {stripped}/{count} members "
                f"stripped within 3d of creation ({pct:.0f}%)"
            )
            await log_audit_event(
                "theme_high_strip_rate",
                summary=summary,
                detail=(
                    f"theme={row['name']} theme_date={row['theme_date']} "
                    f"created_at={row['created_at']} "
                    f"member_count={count} stripped_within_3d={stripped} "
                    f"strip_pct={pct:.1f}"
                ),
            )
            await send_telegram_message(
                f"🟡 *Theme high strip rate*\n"
                f"`{row['name']}` ({row['theme_date']})\n"
                f"{stripped}/{count} members stripped within 3d of creation ({pct:.0f}%).\n"
                f"Likely a hallucinated theme or wrong member assignment — review."
            )
        logger.info(
            f"Theme round-trip validator: scanned 7d window, "
            f"{len(rows)} theme(s) flagged for ≥50% strip rate"
        )


async def _baseline_refresh_job():
    """Run at 2:00 AM ET daily. Recompute mi_metric_baselines from trailing 30d.

    Trimmed median + MAD per metric; respects mi_baseline_resets epochs so
    deploy/fix points correctly invalidate pre-fix history.
    """
    logger.info("Baseline refresh starting...")
    refreshed = 0
    try:
        from agents.market_intelligence.system_audit import run_baseline_refresh
        refreshed = await run_baseline_refresh()
        logger.info(f"Baseline refresh complete: {refreshed} metrics")
    except Exception as e:
        logger.error(f"Baseline refresh failed: {e}", exc_info=True)
        await notify_job_failure("baseline_refresh", str(e))
    return refreshed


async def _minute_volume_curves_refresh_job():
    """Run at 6:30 PM ET. Rebuild per-minute cumulative-volume baselines for
    the top-dollar-volume universe. Powers the RVOL@T pre-9:45 gate in
    `ep_detector` — a like-for-like comparison of today's minute-cumulative
    volume against the 20-day mean at the same clock-time, replacing the
    apples-to-oranges raw_vol/daily_ADV ratio for early-session entries.

    Slot: after 18:00 evening_briefing so its DB writes don't contend, well
    before midnight. Lookback ends at yesterday so we only baseline closed
    sessions. Polygon minute-bar fetch is gated by the global `_polygon_lock`
    so runtime scales linearly with universe size — ~500 tickers × ~0.2s
    courtesy delay ≈ 100s typical, +misfire_grace_time of 30 min for restart
    overlap. No Telegram on success; failures notify via job_failure path.
    """
    logger.info("Minute volume curves refresh starting...")
    try:
        from agents.market_intelligence.minute_volume import refresh_curves
        summary = await refresh_curves()
        logger.info(f"Minute volume curves refresh complete: {summary}")
        return int(summary.get("rows_written") or 0)
    except Exception as e:
        logger.error(f"Minute volume curves refresh failed: {e}", exc_info=True)
        await notify_job_failure("minute_volume_curves_refresh", str(e))
        return None


async def _post_validation_check_job():
    """Run Sat 8:00 AM ET. Recap Friday's theme validation run.

    Theme validation fans out Mon/Wed/Fri nightly. The 2026-04-22 session-2
    fix (semaphore + split exception handling) should route 429s to the
    `validation_rate_limited` bucket instead of mislabeling them as
    `validation_error`. This job confirms the fix is holding: it counts
    yesterday's validation_error / validation_rate_limited / anthropic_rate_limited /
    ticker_revalidated_out events and sends a single Telegram line. Silent when
    yesterday was zero-activity (e.g. the validation job didn't run).
    """
    logger.info("Post-validation check starting...")
    try:
        from agents.market_intelligence.collector import et_today
        # timedelta imported at module level per preflight [5d/5]

        yesterday = et_today() - timedelta(days=1)
        y_str = str(yesterday)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                  COUNT(*) FILTER (WHERE event_type = 'validation_error')         AS errors,
                  COUNT(*) FILTER (WHERE event_type = 'validation_rate_limited')  AS rate_limited,
                  COUNT(*) FILTER (WHERE event_type = 'anthropic_rate_limited')   AS retries,
                  COUNT(*) FILTER (WHERE event_type = 'ticker_revalidated_out')   AS removals
                FROM mi_audit_log
                WHERE created_at >= ($1::date AT TIME ZONE 'America/New_York')
                  AND created_at <  (($1::date + INTERVAL '1 day')::date AT TIME ZONE 'America/New_York')
                """,
                yesterday,
            )
        errors = int(row["errors"] or 0)
        rate_limited = int(row["rate_limited"] or 0)
        retries = int(row["retries"] or 0)
        removals = int(row["removals"] or 0)

        if errors + rate_limited + retries + removals == 0:
            logger.info("Post-validation check: no validation activity yesterday")
            return

        if errors > 0:
            icon = "🔴"
            verdict = f"{errors} validation_error"
        elif rate_limited > 0:
            icon = "🟠"
            verdict = f"{rate_limited} rate-limited (fix working — correctly classified)"
        else:
            icon = "✅"
            verdict = "clean"

        await send_telegram_message(
            f"{icon} *Post-validation check — {y_str}*\n"
            f"{verdict}\n"
            f"retries: {retries} · removals: {removals}"
        )
        logger.info("Post-validation check sent")
    except Exception as e:
        logger.error(f"Post-validation check failed: {e}")
        await notify_job_failure("post_validation_check", str(e))


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


async def _friday_watchlist_job():
    """Friday 6:00 PM ET. Curated weekly watchlist for chart-review."""
    from agents.market_intelligence.friday_watchlist import run_friday_watchlist
    logger.info("Friday watchlist starting...")
    try:
        result = await run_friday_watchlist(window_days=7, persist=True)
        await notify_job_success(
            "friday_watchlist",
            f"watchlist sent ({result['row_count']} tickers, delivered={result['delivered']})",
        )
    except Exception as e:
        logger.exception(f"Friday watchlist failed: {e}")
        await notify_job_failure("friday_watchlist", str(e))


async def _weekly_system_review_job():
    """Sunday 8:00 AM ET. Synthesize last 7 days of system metrics via Claude + Telegram digest."""
    from agents.market_intelligence.system_review import run_weekly_review
    logger.info("Weekly system review starting...")
    try:
        review = await run_weekly_review(window_days=7)
        suggestion_count = len(review.get("suggestions") or [])
        await notify_job_success(
            "weekly_system_review",
            f"review sent (regime={review.get('regime')}, suggestions={suggestion_count})",
        )
    except Exception as e:
        logger.exception(f"Weekly system review failed: {e}")
        await notify_job_failure("weekly_system_review", str(e))


async def _start_ep_scanning():
    """Kept for /status display. Scanning is controlled by cron window, not this flag."""
    logger.info("EP scan window open (7:00 AM ET)")


async def _stop_ep_scanning():
    """Kept for /status display. Scanning is controlled by cron window, not this flag."""
    logger.info("EP scan window closed (10:00 AM ET)")


async def _ep_scan_watchdog():
    """Run at 10:05 AM ET. Alert if scans failed to run. No alert for zero EPs (normal).

    Ground-truth check against `mi_job_runs` (NOT the in-process
    `_ep_scans_completed_today` counter). 2026-05-28 false-positive
    incident: container restarted at 10:04:31 ET (29s before watchdog),
    in-process counter reset to 0 on module reload while morning scans
    had all run successfully in the prior container — same bug class
    as the IBM cascade `sync_positions` mass-close (#137 fix pattern).
    """
    from agents.market_intelligence.collector import _ET
    now = datetime.now(_ET)
    if now.weekday() >= 5:
        return
    market_status = get_market_status(now.date())
    if not market_status.is_trading_day:
        logger.info(f"EP scan watchdog: skipping — {market_status.reason}")
        return
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            scan_count = await conn.fetchval(
                """SELECT COUNT(*) FROM mi_job_runs
                   WHERE job_id = 'ep_scan'
                     AND status = 'success'
                     AND (started_at AT TIME ZONE 'America/New_York')::date = $1""",
                now.date(),
            ) or 0
            if scan_count == 0:
                logger.warning("EP scan watchdog: NO scans completed today!")
                await send_telegram_message(
                    "⚠️ *EP Scan Watchdog*\n"
                    "No EP scan completed today. The scanner may have failed or "
                    "the container restarted after the scan window.\n"
                    "Run manually: tell Apollo \"run EP scan\""
                )
            else:
                alert_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM mi_ep_alerts WHERE alert_date = $1",
                    now.date(),
                )
                logger.info(f"EP scan watchdog: {scan_count} scans ran, {alert_count} alerts — OK")
    except Exception as e:
        logger.error(f"EP scan watchdog failed: {e}")


async def _9m_scan_job() -> None:
    """Run every 5 min, 9:30 AM – 4:00 PM ET. Detect 9M EP volume events."""
    from agents.market_intelligence.collector import et_today
    today = et_today()
    if not get_market_status(today).is_trading_day:
        return
    try:
        from agents.market_intelligence.ninem_detector import run_9m_scan
        alerts = await run_9m_scan()
        if alerts:
            logger.info(f"9M scan: {len(alerts)} new alert(s)")
    except Exception as e:
        import traceback
        logger.error(f"9M EP scan error: {e}\n{traceback.format_exc()}")
        await notify_job_failure("9m_scan", str(e))


async def _9m_day2_orb_job() -> None:
    """Run at 9:31 AM ET. Place Day 2 ORB entries for yesterday's confirmed 9M sugar babies.

    MAGNA53-priority reserve (Path C, 2026-05-08): MAGNA53 HIGH EPs and 9M
    Day 2 entries fire from independent crons at 9:31 ET and race for the
    same MAX_CONCURRENT_LIVE_POSITIONS slots. Without coordination, 9M Day 2
    typically wins on cron-fire-order regardless of relative quality. This
    hack reserves slots for today's HIGH MAGNA53 EPs by reading
    mi_ep_alerts BEFORE submitting sugar babies. Stripped-down stand-in
    until cross-strategy ranking Phase 1 (#31, locked spec) ships.
    """
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    from agents.market_intelligence.collector import et_today
    today = et_today()
    if not get_market_status(today).is_trading_day:
        return
    try:
        from agents.market_intelligence.broker.live_tracker import submit_9m_day2_trade
        from agents.market_intelligence.db import get_pending_9m_sugar_babies
        from agents.market_intelligence.collector import prev_trading_days
        from agents.market_intelligence.constants import MAX_CONCURRENT_LIVE_POSITIONS
        yesterday = prev_trading_days(1, from_date=today)[0]
        candidates = await get_pending_9m_sugar_babies(yesterday)
        if not candidates:
            return

        # Cross-strategy allocator (#31) Phase 1A — shadow enqueue.
        # Every sugar baby competing for a slot today goes onto the queue.
        # Path C reservation logic + actual submission run unchanged below;
        # the 9:35 AM shadow allocator scores the queue and emits an audit
        # event comparing its picks to actual fills. UPSERT — re-runs of
        # the cron refresh the score in-place.
        try:
            from agents.market_intelligence.cross_strategy_allocator import score_9m_day2
            from agents.market_intelligence.db import enqueue_pending_allocation, get_latest_regime, get_pool as _gp
            regime_ = await get_latest_regime()
            regime_lbl = (regime_ or {}).get("regime", "Bull")
            # Fetch ADV-20 for all candidate tickers in one query so the
            # volume dimension is real, not a placeholder. Uses sugar baby
            # day (yesterday) as the cutoff so adv covers the same window
            # the sugar-baby qualification used.
            cand_tickers = [c["ticker"] for c in candidates]
            pool_ = await _gp()
            async with pool_.acquire() as conn:
                adv_rows = await conn.fetch("""
                    SELECT ticker, AVG(volume)::FLOAT AS adv20 FROM (
                        SELECT ticker, volume,
                               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                        FROM mi_daily_closes
                        WHERE ticker = ANY($1) AND trade_date <= $2
                    ) t WHERE rn <= 20
                    GROUP BY ticker
                """, cand_tickers, yesterday)
            adv_map_alloc = {r["ticker"]: float(r["adv20"]) for r in adv_rows}
            for c in candidates:
                op = c.get("open_price") or 0
                cl = c.get("close_price") or 0
                gap_proxy = ((cl - op) / op * 100) if op else 0.0
                vol = float(c.get("volume") or 0)
                adv20 = adv_map_alloc.get(c["ticker"]) or 0.0
                vol_ratio = (vol / adv20) if adv20 > 0 else 5.0
                cand = score_9m_day2(
                    ticker=c["ticker"],
                    alert_date=today,
                    close_in_range_pct=c.get("close_in_range_pct") or 0,
                    gap_proxy_pct=gap_proxy,
                    vol_ratio_adv=vol_ratio,
                    regime_label=regime_lbl,
                )
                await enqueue_pending_allocation(
                    ticker=c["ticker"], alert_date=today, strategy="9m_day2",
                    composite_score=cand.composite,
                    raw_dimensions=cand.raw_dimensions,
                )
        except Exception as e:
            logger.warning(f"9M Day 2 allocator enqueue failed: {e}")

        # Slot budget: count currently-active/pending positions + reserve
        # for today's HIGH MAGNA53 EPs that haven't been submitted yet.
        # 9M Day 2 takes only the leftover slots, top-N sorted by quality.
        pool_ = await get_pool()
        async with pool_.acquire() as conn:
            active_count = await conn.fetchval("""
                SELECT COUNT(*) FROM mi_live_trades
                WHERE (status = 'filled' AND remaining_shares > 0)
                   OR status = 'order_placed'
            """)
            high_ep_pending = await conn.fetchval("""
                SELECT COUNT(*) FROM mi_ep_alerts a
                WHERE a.alert_date = $1 AND a.score_tier = 'HIGH'
                  AND NOT EXISTS (
                      SELECT 1 FROM mi_live_trades t
                      WHERE t.ticker = a.ticker
                        AND t.alert_date = a.alert_date
                        AND t.signal_type = 'magna53'
                  )
            """, today)
        active_count = active_count or 0
        high_ep_pending = high_ep_pending or 0
        budget = MAX_CONCURRENT_LIVE_POSITIONS - active_count - high_ep_pending

        if budget <= 0:
            skipped_tickers = ", ".join(c["ticker"] for c in candidates[:5])
            if len(candidates) > 5:
                skipped_tickers += f" + {len(candidates) - 5} more"
            await log_audit_event(
                "9m_day2_all_skipped_high_ep_reserve",
                f"All {len(candidates)} 9M Day 2 candidates skipped — slots reserved "
                f"({active_count} active, {high_ep_pending} HIGH EPs pending)",
                json.dumps({
                    "active_count": active_count,
                    "high_ep_pending": high_ep_pending,
                    "max_positions": MAX_CONCURRENT_LIVE_POSITIONS,
                    "skipped_count": len(candidates),
                    "skipped_tickers": [c["ticker"] for c in candidates],
                }),
            )
            await send_telegram_message(
                f"{mode_prefix()}🎯 *9M Day 2 reserved-for-HIGH-EPs*\n"
                f"Slots: {active_count} active + {high_ep_pending} HIGH EPs pending = "
                f"{active_count + high_ep_pending}/{MAX_CONCURRENT_LIVE_POSITIONS}.\n"
                f"Skipped {len(candidates)} sugar baby candidate(s): {skipped_tickers}"
            )
            return

        # Sort by quality, take top-{budget}. cirp (close-in-range-pct) DESC
        # is the canonical 9M Day 2 quality metric — higher cirp = stronger
        # close = better setup. Tie-break by volume.
        candidates_sorted = sorted(
            candidates,
            key=lambda c: (
                -(c.get("close_in_range_pct") or 0),
                -(c.get("volume") or 0),
            ),
        )
        to_process = candidates_sorted[:budget]
        to_skip = candidates_sorted[budget:]

        if to_skip:
            # NOTE: log_audit_event imported at module level + referenced earlier
            # in this function. Local import would shadow → UnboundLocalError on
            # prior refs (2026-05-20 ep_detector bug class).
            await log_audit_event(
                "9m_day2_partial_skipped_high_ep_reserve",
                f"Took top-{budget} of {len(candidates)} sugar babies; "
                f"skipped {len(to_skip)} for HIGH EP reserve "
                f"({active_count} active + {high_ep_pending} HIGH pending)",
                json.dumps({
                    "active_count": active_count,
                    "high_ep_pending": high_ep_pending,
                    "budget": budget,
                    "processed": [c["ticker"] for c in to_process],
                    "skipped": [c["ticker"] for c in to_skip],
                }),
            )
            await send_telegram_message(
                f"{mode_prefix()}🎯 *9M Day 2 partial reserve*\n"
                f"Took top-{budget} (by close-in-range): "
                f"{', '.join(c['ticker'] for c in to_process)}\n"
                f"Skipped {len(to_skip)} for HIGH EP reserve: "
                f"{', '.join(c['ticker'] for c in to_skip)}"
            )

        candidates = to_process
        # Parallel fan-out (mirrors MAGNA53 pattern in live_tracker.py). Sequential
        # for-loop here was the TEAM 5/04 root cause: SOUN's 60s bar-retry blocked
        # all subsequent candidates. Semaphore(5) caps concurrent submits; each
        # ticker keeps its own try/except so one crash never strands the rest.
        sem = asyncio.Semaphore(5)

        async def _process_candidate(candidate):
            async with sem:
                try:
                    return await submit_9m_day2_trade(candidate)
                except Exception as ce:
                    tkr = candidate.get("ticker", "<unknown>")
                    logger.exception(f"9M Day2 {tkr}: per-candidate crash — {ce}")
                    try:
                        await log_audit_event(
                            "9m_day2_pipeline_crash",
                            f"{tkr} — {type(ce).__name__}: {ce}",
                        )
                    except Exception:
                        logger.exception(f"9M Day2 {tkr}: audit_log write also failed")
                    await send_telegram_message(
                        f"{mode_prefix()}🚨 *{tkr}* 9M Day2 pipeline crashed — {type(ce).__name__}: {ce}"
                    )

        results = await asyncio.gather(
            *(_process_candidate(c) for c in candidates),
            return_exceptions=True,
        )

        # Grouped skip digest — one Telegram for the whole cron-run instead
        # of per-ticker. Mirrors the MAGNA53 ORB monitor digest.
        from agents.market_intelligence.broker.entry_pipeline import (
            ACTION_SKIPPED, ACTION_BLOCKED,
        )
        from agents.market_intelligence.broker.skip_reasons import humanize
        skipped_results = [
            r for r in results
            if isinstance(r, dict) and r.get("action") in (ACTION_SKIPPED, ACTION_BLOCKED)
        ]
        if skipped_results:
            bullets = "\n".join(
                f"• `{r['ticker']}` — {humanize(r.get('reason'))}"
                for r in skipped_results
            )
            try:
                await send_telegram_message(
                    f"{mode_prefix()}⏭️ *9M Day2 skips ({today}, {len(skipped_results)})*\n{bullets}"
                )
            except Exception as e:
                logger.error(f"9M Day2 grouped-skip Telegram failed — {e}")
    except Exception as e:
        import traceback
        logger.error(f"9M Day2 ORB job error: {e}\n{traceback.format_exc()}")
        await notify_job_failure("9m_day2_orb", str(e))


async def _unified_allocator_shadow_job() -> None:
    """Cross-strategy allocator (#31) Phase 1A — shadow.

    Runs at 9:35 ET after MAGNA53 ORB monitor (9:30) and 9M Day 2 cron (9:31)
    have populated mi_pending_allocations. Drains today's queue, scores each
    candidate via cross_strategy_allocator.run_shadow_allocation, marks
    shadow_rank + shadow_allocated, emits `unified_allocation_decided` audit.

    Does NOT submit. Phase 1B (active) will move this to 9:28 ET pre-market
    and replace the legacy submission paths. Compare actual fills today's
    morning vs the audit event's `winners` field to validate the design.
    """
    from agents.market_intelligence.collector import et_today
    today = et_today()
    if not get_market_status(today).is_trading_day:
        return
    try:
        from agents.market_intelligence.cross_strategy_allocator import run_shadow_allocation
        result = await run_shadow_allocation(today)
        logger.info(
            f"unified_allocator_shadow: {result['n_winners']}/{result['n_candidates']} "
            f"winners (slots={result.get('slots', 0)}); top_picks={result['top_picks']}"
        )
    except Exception as e:
        import traceback
        logger.error(f"unified_allocator_shadow error: {e}\n{traceback.format_exc()}")
        await notify_job_failure("unified_allocator_shadow", str(e))


async def check_missed_jobs() -> None:
    """
    On startup, send any briefings that were missed while the machine was off.

    Catch-up windows (ET):
    - Morning briefing:  09:00 – 12:00  (fires if missed and we start in that window)
    - Nightly data pull: 17:00 – 18:00  (fires if missed and we start in that window)
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

    # Nightly data pull: 5:00 PM – 6 PM ET
    if hour == 17:
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


async def _hud_refresh_job() -> None:
    """Edit the pinned HUD message in-place with fresh data (market hours only)."""
    from agents.market_intelligence.db import get_hud_state, set_hud_state
    from agents.market_intelligence.briefing import edit_telegram_message
    from agents.market_intelligence.agent import _build_hud_text

    chat_id_str = await get_hud_state("hud_chat_id")
    message_id_str = await get_hud_state("hud_message_id")
    if not chat_id_str or not message_id_str:
        return

    try:
        text = await _build_hud_text()
        ok = await edit_telegram_message(int(chat_id_str), int(message_id_str), text)
        if not ok:
            # Message was deleted — clear stored IDs so next /hud command re-pins
            await set_hud_state("hud_chat_id", "")
            await set_hud_state("hud_message_id", "")
    except Exception as e:
        logger.error(f"HUD refresh failed: {e}", exc_info=True)


async def _emit_boot_audit_marker() -> None:
    """Emit `account_mode_active` audit event on scheduler startup.

    Forensic anchor for live $ migration: any later ambiguity about which
    Alpaca account a `mi_live_trades` row was written against can be resolved
    by walking back to the nearest preceding boot marker. Records the
    resolved env (alpaca_paper, live_trading_enabled), the broker-reported
    equity, and the derived account mode label. Equity fetch is best-effort —
    Alpaca outages or missing keys must not block startup.
    """
    import os
    from agents.market_intelligence.constants import current_account_mode
    paper_env = os.environ.get("ALPACA_PAPER", "true")
    live_env = os.environ.get("LIVE_TRADING_ENABLED", "false")
    mode = current_account_mode()

    equity_str = "unknown"
    try:
        from agents.market_intelligence.broker import alpaca_client as alpaca
        account = await alpaca.get_account()
        equity_str = f"${float(account.get('equity', 0)):,.2f}"
    except Exception as e:
        logger.warning(f"Boot marker: equity fetch failed (non-fatal): {e}")
        equity_str = f"fetch_failed: {str(e)[:80]}"

    summary = f"mode={mode} equity={equity_str}"
    detail = (
        f"alpaca_paper_env={paper_env} live_trading_enabled_env={live_env} "
        f"equity={equity_str}"
    )
    try:
        await log_audit_event("account_mode_active", summary, detail)
        logger.info(f"Boot marker: {summary} | {detail}")
    except Exception as e:
        logger.error(f"Boot marker audit write failed: {e}", exc_info=True)


async def _reap_stale_running_runs() -> None:
    """Mark any mi_job_runs row stuck at status='running' for >2h as 'aborted'.

    Process kills (SIGTERM during deploy, OOM, real hang) leave the audit row
    behind because audit_run's finally-equivalent path never reaches the DB
    UPDATE. No legitimate job in this codebase runs >1h, so 2h is safe margin.
    Surfaces as `stale_runs_reaped` audit event — climb in count is a leading
    indicator of something other than deploys (real hangs, DB locks).
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                UPDATE mi_job_runs
                   SET status='aborted',
                       finished_at=NOW(),
                       error_message='started_at exceeded 2h threshold (likely killed mid-run or hung)'
                 WHERE status='running' AND started_at < NOW() - INTERVAL '2 hours'
             RETURNING job_id, started_at
            """)
        if rows:
            detail = ", ".join(f"{r['job_id']}@{r['started_at']:%Y-%m-%d %H:%M}Z" for r in rows)
            await log_audit_event("stale_runs_reaped", f"reaped {len(rows)} rows: {detail}")
            logger.warning(f"Reaped {len(rows)} stale mi_job_runs rows: {detail}")
    except Exception as e:
        logger.error(f"Stale-run reap failed: {e}", exc_info=True)


# ── Telegram polling-bot health watchdog (#153) ──────────────────────────────
# The orchestrator's PTB long-poll loop can wedge on a persistent NetworkError
# and silently stop receiving updates (the 2026-05-22→05-29 7-day outage). The
# orchestrator writes a Redis heartbeat (apollo:telegram:poll_heartbeat) on each
# successful get_updates. This watchdog runs in the MARKET-AGENT — a separate
# container, so it survives an orchestrator poll-wedge — and alarms if the
# heartbeat goes stale. Missing key = not polling / pre-boot (never alarm);
# stale key = poll loop died (alarm). Detection latency drops from days to mins.
_TG_POLL_HEARTBEAT_KEY = "apollo:telegram:poll_heartbeat"
_TG_POLL_ALERT_KEY = "apollo:telegram:poll_watchdog_alerted"
_TG_POLL_STALE_SECONDS = 300       # ≈30 missed ~10s polls — unambiguous
_TG_POLL_ALERT_COOLDOWN = 1800     # ≤1 Telegram + audit per 30 min during outage
_tg_watchdog_redis = None


async def _telegram_poll_watchdog_job():
    """Alarm if the orchestrator's Telegram poll heartbeat is stale (#153).
    Alerts via sendMessage — a different Bot API call than the wedged
    getUpdates, on the market-agent's own network path, so it gets through —
    plus a durable audit row as backstop if the whole Telegram path is down."""
    global _tg_watchdog_redis
    try:
        import time
        if _tg_watchdog_redis is None:
            import redis.asyncio as _redis
            from shared.secrets import get_secrets
            _tg_watchdog_redis = _redis.from_url(
                get_secrets().redis_url, decode_responses=True,
            )
        r = _tg_watchdog_redis
        raw = await r.get(_TG_POLL_HEARTBEAT_KEY)
        if raw is None:
            return  # not polling / pre-boot — never alarm on a missing key
        age = int(time.time()) - int(raw)
        if age <= _TG_POLL_STALE_SECONDS:
            await r.delete(_TG_POLL_ALERT_KEY)  # healthy → reset dedup for next outage
            return
        if await r.get(_TG_POLL_ALERT_KEY):
            return  # already alerted this outage (cooldown active)
        await log_audit_event(
            "telegram_poll_stale",
            f"Telegram poll heartbeat stale {age}s (>{_TG_POLL_STALE_SECONDS}s) — "
            f"bot may have silently stopped receiving",
            json.dumps({"age_seconds": age, "stale_threshold": _TG_POLL_STALE_SECONDS}),
        )
        await send_telegram_message(
            f"🚨 *Telegram bot health alert*\n"
            f"Polling heartbeat is *{age // 60}m {age % 60}s* stale — the bot may have "
            f"silently stopped receiving messages (the 7-day-outage class).\n\n"
            f"If commands/alerts aren't flowing, restart `apollo-orchestrator`."
        )
        await r.set(_TG_POLL_ALERT_KEY, int(time.time()), ex=_TG_POLL_ALERT_COOLDOWN)
    except Exception as e:
        logger.warning(f"telegram poll watchdog error: {e}")


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="America/New_York")

    # Reap stale 'running' rows from prior process kills before any new job fires.
    asyncio.create_task(_reap_stale_running_runs())

    # Boot marker: forensic anchor for paper/live $ mode at process start.
    asyncio.create_task(_emit_boot_audit_marker())

    # Data pull: 5:00 PM ET (30 min after tape settles), Mon-Fri
    _scheduler.add_job(
        audit_wrap(_nightly_data_pull, JOB_NIGHTLY_DATA_PULL, expected_min_rows=5000),
        CronTrigger(hour=17, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_NIGHTLY_DATA_PULL,
        replace_existing=True,
    )

    # Telegram polling-bot health watchdog: every 2 min, 24/7 (#153). Raw (not
    # audit_wrap'd) — it's a high-frequency liveness check that self-guards and
    # would otherwise spam mi_job_runs. Telegram is not market-hours gated.
    _scheduler.add_job(
        _telegram_poll_watchdog_job,
        CronTrigger(minute="*/2", timezone="America/New_York"),
        id="telegram_poll_watchdog",
        replace_existing=True,
    )

    # Evening briefing: 6:00 PM ET (3:00 PM PT), Mon-Fri
    _scheduler.add_job(
        audit_wrap(_evening_briefing_job, JOB_EVENING_BRIEFING),
        CronTrigger(hour=18, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_EVENING_BRIEFING,
        replace_existing=True,
    )

    # Reset bar stream daily state + start EP scanning at 7:00 AM ET
    async def _ep_scan_start_job():
        from agents.market_intelligence.broker import bar_stream
        bar_stream.reset_daily_state()
        await _start_ep_scanning()

    _scheduler.add_job(
        audit_wrap(_ep_scan_start_job, "ep_scan_start"),
        CronTrigger(hour=7, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="ep_scan_start",
        replace_existing=True,
    )

    # EP scan: every 5 minutes 7:00–10:00 AM ET
    # Pre-market HIGHs → bar stream subscription (ORB fires on first bar close)
    # Post-open HIGHs  → ORB entry inline immediately after scan
    _scheduler.add_job(
        audit_wrap(_ep_scan_job, "ep_scan"),
        CronTrigger(
            hour="7-9",
            minute="*/5",
            day_of_week="mon-fri",
            timezone="America/New_York",
        ),
        id="ep_scan",
        replace_existing=True,
        misfire_grace_time=300,  # skip if restart fires this >5 min late
    )

    # EP scan at 9:31 AM — first complete bar just closed, catches at-open volume upgrades
    _scheduler.add_job(
        audit_wrap(_ep_scan_job, "ep_scan_open"),
        CronTrigger(hour=9, minute=31, day_of_week="mon-fri", timezone="America/New_York"),
        id="ep_scan_open",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Unsubscribe bar stream at 9:35 AM — ORB window closed
    async def _bar_stream_cleanup():
        from agents.market_intelligence.broker import bar_stream
        await bar_stream.unsubscribe_all()

    _scheduler.add_job(
        audit_wrap(_bar_stream_cleanup, "bar_stream_cleanup"),
        CronTrigger(hour=9, minute=35, day_of_week="mon-fri", timezone="America/New_York"),
        id="bar_stream_cleanup",
        replace_existing=True,
    )

    # Morning briefing: 9:00 AM ET (6:00 AM PT), 30 min before open
    _scheduler.add_job(
        audit_wrap(_morning_briefing_job, JOB_MORNING_BRIEFING),
        CronTrigger(hour=9, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_MORNING_BRIEFING,
        replace_existing=True,
    )

    # Stop EP scanning at 10:00 AM ET (7:00 AM PT) — extended past open to catch
    # at-open gaps with 15-min delayed data (Polygon Starter)
    _scheduler.add_job(
        audit_wrap(_stop_ep_scanning, "ep_scan_stop"),
        CronTrigger(hour=10, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="ep_scan_stop",
        replace_existing=True,
    )

    # EP scan watchdog: 10:05 AM ET — alert if no scan ran today
    _scheduler.add_job(
        audit_wrap(_ep_scan_watchdog, "ep_scan_watchdog"),
        CronTrigger(hour=10, minute=5, day_of_week="mon-fri", timezone="America/New_York"),
        id="ep_scan_watchdog",
        replace_existing=True,
    )

    # Paper trade tracker: 4:45 PM ET — after nightly data pull, simulate new EPs + update stops
    _scheduler.add_job(
        audit_wrap(_paper_trade_tracker_job, "paper_trade_tracker"),
        CronTrigger(hour=16, minute=45, day_of_week="mon-fri", timezone="America/New_York"),
        id="paper_trade_tracker",
        replace_existing=True,
    )

    # Weekly cleanup: Sunday 2:00 AM ET
    _scheduler.add_job(
        audit_wrap(_weekly_cleanup, "weekly_cleanup"),
        CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="America/New_York"),
        id="weekly_cleanup",
        replace_existing=True,
    )

    # Weekly system review: Sunday 8:00 AM ET — self-audit digest via Claude
    _scheduler.add_job(
        audit_wrap(_weekly_system_review_job, "weekly_system_review"),
        CronTrigger(day_of_week="sun", hour=8, minute=0, timezone="America/New_York"),
        id="weekly_system_review",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Friday watchlist: Friday 6:00 PM ET — curated chart-review aggregator
    _scheduler.add_job(
        audit_wrap(_friday_watchlist_job, "friday_watchlist"),
        CronTrigger(day_of_week="fri", hour=18, minute=0, timezone="America/New_York"),
        id="friday_watchlist",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Post-validation check: Saturday 8:00 AM ET — recap Fri's theme validation run
    _scheduler.add_job(
        audit_wrap(_post_validation_check_job, "post_validation_check"),
        CronTrigger(day_of_week="sat", hour=8, minute=0, timezone="America/New_York"),
        id="post_validation_check",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Live trading jobs (only fire if LIVE_TRADING_ENABLED) ──────────────

    # Fill checker — fallback polling (WebSocket is primary, this is safety net)
    # Runs every 30 min; skips if WebSocket stream is healthy
    fill_check_times = [(10, 0), (10, 30), (11, 0), (12, 0), (13, 0), (14, 0), (15, 0)]
    for hour, minute in fill_check_times:
        check_id = f"check_fills_{hour:02d}{minute:02d}"
        _scheduler.add_job(
            # Single audit job_id "check_fills" (not per-time) so all 7 fires/day
            # aggregate into one baseline — fragmenting per HHMM gives only 30
            # samples/month per id, too thin for L2 detection.
            audit_wrap(_check_fills_job, "check_fills"),
            CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri", timezone="America/New_York"),
            id=check_id,
            replace_existing=True,
        )

    # Stream health watchdog: every 5 min during market hours
    _scheduler.add_job(
        audit_wrap(_stream_health_watchdog, "stream_health_watchdog"),
        CronTrigger(hour="9-15", minute="*/5", day_of_week="mon-fri", timezone="America/New_York"),
        id="stream_health_watchdog",
        replace_existing=True,
    )

    # Morning stop refresh: 9:35 AM ET — re-place stops for Day 2+ positions
    _scheduler.add_job(
        audit_wrap(_morning_stop_refresh_job, "morning_stop_refresh"),
        CronTrigger(hour=9, minute=35, day_of_week="mon-fri", timezone="America/New_York"),
        id="morning_stop_refresh",
        replace_existing=True,
    )

    # ORB window cleanup: 10:00 AM ET — cancel unfilled entries once ORB window
    # closes. Prevents stop-limit buys sitting for hours and filling on
    # dead-cat-bounce retests well outside the setup's validity window.
    _scheduler.add_job(
        audit_wrap(_orb_window_cleanup_job, "orb_window_cleanup"),
        CronTrigger(hour=10, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="orb_window_cleanup",
        replace_existing=True,
    )

    # Shadow ORB entry: 10:00 AM ET — 5-min ORB telemetry. Shares the slot
    # with orb_window_cleanup (distinct job_id). Reads 9:30-10:00 1-min bars,
    # writes mi_orb_shadow_trades rows. No Alpaca submits.
    _scheduler.add_job(
        audit_wrap(_shadow_orb_entry_job, "shadow_orb_entry"),
        CronTrigger(hour=10, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="shadow_orb_entry",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Shadow ORB exit: 4:30 PM ET — daily exit step on every open shadow row.
    # 4:50 PM ET — after live_position_update (4:45) which already chose
    # this slot to let Polygon daily aggregate settle. Exit logic walks
    # daily bars; pre-aggregate run would see partial/zero data.
    _scheduler.add_job(
        audit_wrap(_shadow_orb_exit_job, "shadow_orb_exit"),
        CronTrigger(hour=16, minute=50, day_of_week="mon-fri", timezone="America/New_York"),
        id="shadow_orb_exit",
        replace_existing=True,
        misfire_grace_time=900,
    )

    # Time-stop candidate scan: 4:55 PM ET — after live_position_update
    # (4:45) + shadow_orb_exit (4:50), before data_pull (5:00). Identifies
    # 9M Day 2 meanderers eligible for operator-confirm time-stop. Pure
    # observability + Telegram alert; operator confirms via /timestop
    # TICKER which submits TimeInForce.OPG sell for next-open fill.
    # #91 ship 2026-05-23.
    _scheduler.add_job(
        audit_wrap(_time_stop_scan_job, JOB_TIME_STOP_SCAN),
        CronTrigger(hour=16, minute=55, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_TIME_STOP_SCAN,
        replace_existing=True,
        misfire_grace_time=900,
    )

    # EOD cleanup: 4:05 PM ET — cancel unfilled, sync positions
    _scheduler.add_job(
        audit_wrap(_eod_cleanup_job, "eod_cleanup"),
        CronTrigger(hour=16, minute=5, day_of_week="mon-fri", timezone="America/New_York"),
        id="eod_cleanup",
        replace_existing=True,
    )

    # Evening position backstop: 9:00 PM ET — second sync_positions pass after
    # extended hours close (8 PM) and all nightly jobs are done. Catches late
    # WS EXPIRED events and earlier remediation failures before next-day open.
    _scheduler.add_job(
        audit_wrap(_evening_position_backstop_job, "evening_position_backstop"),
        CronTrigger(hour=21, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="evening_position_backstop",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # EOD EP recap: 4:10 PM ET — one-line Telegram summary of today's HIGH outcomes.
    # Fires after eod_cleanup so trade rows have settled (cancel unfilled, sync fills).
    _scheduler.add_job(
        audit_wrap(_eod_ep_recap_job, "eod_ep_recap"),
        CronTrigger(hour=16, minute=10, day_of_week="mon-fri", timezone="America/New_York"),
        id="eod_ep_recap",
        replace_existing=True,
    )

    # Account equity snapshot + drawdown breaker recompute: 4:12 PM ET — runs
    # after eod_cleanup (16:05) and recap (16:10) so equity reflects settled
    # MTM. Single source for daily peak tracking + drawdown state machine (#39).
    _scheduler.add_job(
        audit_wrap(_account_equity_snapshot_job, "account_equity_snapshot"),
        CronTrigger(hour=16, minute=12, day_of_week="mon-fri", timezone="America/New_York"),
        id="account_equity_snapshot",
        replace_existing=True,
    )

    # Worst-price / best-price tracking for open positions: every 5 min from
    # 9:30 AM to 4:00 PM ET (2026-05-10). Polls Polygon minute bars per open
    # ticker, monotonic LEAST/GREATEST updates lowest_price_seen +
    # highest_price_seen on mi_live_trades. Powers setup-quality analytics
    # (does this setup let trades run high before exit, or drag near stop?).
    _scheduler.add_job(
        audit_wrap(_track_open_position_extremes_job, "track_position_extremes"),
        CronTrigger(
            hour="9-15", minute="*/5",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id="track_position_extremes",
        replace_existing=True,
        misfire_grace_time=180,
    )

    # Stuck-fill watchdog (Gate 5 deliverable D, 2026-05-14). Every 60s
    # during market hours, surface trade rows that show status='filling'
    # with no filled_at for >2 min — symptom of a WS handler exception
    # like the CRMD AmbiguousParameter case.
    _scheduler.add_job(
        audit_wrap(_stuck_fill_watchdog_job, "stuck_fill_watchdog"),
        CronTrigger(
            hour="9-15", minute="*",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id="stuck_fill_watchdog",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # Stop-ACK timeout watchdog (2026-05-17, MRAM-class). Every 30s
    # during market hours, detect filled trades where stop_order_id is
    # NULL >30 seconds after fill — symptom of silent OTO bracket
    # child-leg failure not caught by Gate 5 A (which only handles the
    # entry-fill UPDATE exception path). MRAM #120 2026-05-11 is the
    # canonical case: stop_order_id persisted as NULL, position closed
    # via WS-only path with phantom double-exit logged. Fallback stop
    # at trade['orb_low'] mirrors Gate 5 A pattern.
    _scheduler.add_job(
        audit_wrap(_stop_ack_timeout_watchdog_job, "stop_ack_timeout_watchdog"),
        CronTrigger(
            hour="9-15", minute="*", second="0,30",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id="stop_ack_timeout_watchdog",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # Post-EOD audit: 4:15 PM ET — trade-side invariants + metrics, runs after
    # 4:05 cleanup and 4:10 recap so trade rows reflect settled state.
    _scheduler.add_job(
        audit_wrap(_post_eod_audit_job, "post_eod_audit"),
        CronTrigger(hour=16, minute=15, day_of_week="mon-fri", timezone="America/New_York"),
        id="post_eod_audit",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Parabolic-short scan: 5:15 PM ET — slots after 5:00 nightly_data_pull
    # (fresh mi_daily_closes) and before 5:30 post_nightly_audit. Telemetry-only
    # per TI1; persists all stages, Telegrams only anticipation/climax.
    _scheduler.add_job(
        audit_wrap(_parabolic_scan_job, JOB_PARABOLIC_SCAN),
        CronTrigger(hour=17, minute=15, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_PARABOLIC_SCAN,
        replace_existing=True,
        misfire_grace_time=900,
    )

    # Fishhook V3 EOD: 5:20 PM ET — slots between 5:15 parabolic_scan and 5:30
    # post_nightly_audit. Shadow-phase telemetry (expected_min_rows=None — many
    # zero-anchor days expected; no L2 alarm on empty result).
    _scheduler.add_job(
        audit_wrap(_fishhook_eod_job, JOB_FISHHOOK_EOD),
        CronTrigger(hour=17, minute=20, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_FISHHOOK_EOD,
        replace_existing=True,
        misfire_grace_time=900,
    )

    # Sugar Babies cohort refresh: 5:22 PM ET — slots between 5:20 fishhook_eod
    # and 5:25 flag_scan. Pure observability — refreshes Pradeep-class
    # persistent watchlist from trailing-180d 9M EOD prints. Fast aggregation
    # (~24 rows, ~ms). Surfaced via /sugarbabies + evening briefing section.
    _scheduler.add_job(
        audit_wrap(_sugar_babies_cohort_refresh_job, JOB_SUGAR_BABIES_COHORT_REFRESH),
        CronTrigger(hour=17, minute=22, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_SUGAR_BABIES_COHORT_REFRESH,
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Continuation-flag scan: 5:25 PM ET — slots between 5:20 fishhook_eod and
    # 5:30 post_nightly_audit. Telemetry-only (phase=shadow); persists all
    # stages, Telegrams TRIGGERED + COILED + new-tightening on non-empty days.
    _scheduler.add_job(
        audit_wrap(_flag_scan_job, JOB_FLAG_SCAN),
        CronTrigger(hour=17, minute=25, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_FLAG_SCAN,
        replace_existing=True,
        misfire_grace_time=900,
    )

    # Intraday flag-break scan: every 5 min, 9-15 hour (cron product-set),
    # Mon-Fri. The job function gates internally to 9:35 AM – 3:55 PM ET to
    # skip pre-9:35 (opening range settles) and post-3:55 (closing-auction
    # noise). #94 ship Commit 1 — telemetry-only shadow phase per ADR 0005.
    _scheduler.add_job(
        audit_wrap(_flag_break_scan_job, JOB_FLAG_BREAK_SCAN),
        CronTrigger(
            hour="9-15", minute="*/5",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_FLAG_BREAK_SCAN,
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Intraday support-test scan: every 5 min during market hours
    # (gate internally 9:35-15:55 ET). Entry-technique #2 per
    # memory/user_tight_range_entry_techniques.md. Telemetry-only
    # shadow phase; N>=10 settled before paper.
    _scheduler.add_job(
        audit_wrap(_support_test_scan_job, JOB_SUPPORT_TEST_SCAN),
        CronTrigger(
            hour="9-15", minute="*/5",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_SUPPORT_TEST_SCAN,
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Intraday MA-pullback scan: every 5 min during market hours
    # (gate internally 9:35-15:55 ET). Entry-technique #3 per
    # memory/user_tight_range_entry_techniques.md. Light-volume gate
    # is the defining characteristic. Telemetry-only shadow phase.
    _scheduler.add_job(
        audit_wrap(_ma_pullback_scan_job, JOB_MA_PULLBACK_SCAN),
        CronTrigger(
            hour="9-15", minute="*/5",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_MA_PULLBACK_SCAN,
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Order-status reconcile: every 15 min during market hours (mon-fri).
    # Polls Alpaca for orders in non-terminal DB status; updates rows where
    # broker state has diverged. Catches silent stops + stuck PENDING_NEW
    # (#123, 2026-05-26). Audit-only — no Telegram. Misfire grace short
    # since the next cycle is only 15 min away.
    _scheduler.add_job(
        audit_wrap(_order_status_reconcile_job, JOB_ORDER_STATUS_RECONCILE),
        CronTrigger(
            hour="9-16", minute="*/15",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_ORDER_STATUS_RECONCILE,
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 9M EP Pace digest: hourly rollup at 10/11/12 ET (#133, 2026-05-27).
    # Pace alerts (89% of pinged 9M volume on 2026-05-27) aren't realtime
    # actionable — bundle them at top of hour. Actual 9M still rides the
    # per-5-min digest in ninem_detector. Afternoon hours skipped: pace
    # signal value drops after midday (no Day-2 setup window).
    _scheduler.add_job(
        audit_wrap(_9m_pace_digest_job, JOB_9M_PACE_DIGEST),
        CronTrigger(
            hour="10-12", minute=0,
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_9M_PACE_DIGEST,
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Catalyst-downgrade morning digest: 10:10 ET (#143, 2026-05-28).
    # Drains the in-process accumulator from ep_detector. Bundles all the
    # morning's downgrades into one Telegram instead of 5-10 per-ticker
    # alerts. 10:10 vs 10:00 to clear the last EP scan tick in-flight.
    # Audit log retains per-ticker rows for `/rubric` drilldown.
    _scheduler.add_job(
        audit_wrap(_catalyst_downgrade_digest_job, JOB_CATALYST_DOWNGRADE_DIGEST),
        CronTrigger(
            hour=10, minute=10,
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_CATALYST_DOWNGRADE_DIGEST,
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Backup health check: 4:30 AM ET daily — 2.5h after host cron backup
    # (02:00 ET). Telegrams if no `gdrive_backup_success` audit row in the
    # last 36h. Backstops the case where the host cron itself stops firing.
    _scheduler.add_job(
        audit_wrap(_backup_health_check_job, JOB_BACKUP_HEALTH_CHECK),
        CronTrigger(hour=4, minute=33, timezone="America/New_York"),
        id=JOB_BACKUP_HEALTH_CHECK,
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Wick-fill forward returns: 5:45 PM ET — slots after post_nightly_audit
    # (5:30) so it doesn't collide with the audit window. Telemetry-only
    # (expected_min_rows=None — empty days are normal during shadow phase).
    _scheduler.add_job(
        audit_wrap(_wick_forward_returns_job, JOB_WICK_FORWARD_RETURNS),
        CronTrigger(hour=17, minute=45, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_WICK_FORWARD_RETURNS,
        replace_existing=True,
        misfire_grace_time=900,
    )

    # Post-nightly audit: 5:30 PM ET — theme/cooldown/regime invariants + metrics,
    # after 5:00 nightly data pull so tonight's themes/cooldowns are visible.
    _scheduler.add_job(
        audit_wrap(_post_nightly_audit_job, "post_nightly_audit"),
        CronTrigger(hour=17, minute=30, day_of_week="mon-fri", timezone="America/New_York"),
        id="post_nightly_audit",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # Baseline refresh: 2:00 AM ET daily — rebuild mi_metric_baselines from
    # trailing 30 days. Idempotent; loss → next refresh recomputes from scratch.
    _scheduler.add_job(
        audit_wrap(_baseline_refresh_job, "baseline_refresh"),
        CronTrigger(hour=2, minute=0, timezone="America/New_York"),
        id="baseline_refresh",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Monthly backward-check sweep — regime-shift monitor.
    # 2026-05-20 originally shipped at quarterly cadence (#62).
    # 2026-05-22 converted to monthly per user — backward checks ARE the
    # regime-change-detection mechanism, not just methodology tuning.
    # Same scripts as before + #77 Pradeep rally bands. Per-band WR
    # shifts month-over-month surface regime inflections that quarterly
    # would miss by ~60 days. Methodology ship still requires N≥10-30
    # per script per the existing sample-size discipline.
    from agents.market_intelligence.quarterly_review import quarterly_backward_check_sweep_job
    _scheduler.add_job(
        audit_wrap(quarterly_backward_check_sweep_job, "monthly_backward_check_sweep"),
        CronTrigger(day=1, hour=8, minute=0, timezone="America/New_York"),
        id="monthly_backward_check_sweep",
        replace_existing=True,
        misfire_grace_time=86400,  # 24h grace — missed once isn't critical
    )

    # News source quality drift check (2026-05-21 #71/#72 trigger):
    # Daily 4:30 PM ET (post-market-close, pre-EOD-cleanup at 5pm). Runs
    # the drift detector; emits news_source_quality_drift audit + Telegram
    # when any source's coverage/attribution drops >40pp week-over-week.
    # 24h Telegram dedup so persistent drift doesn't spam — audit row
    # writes daily regardless for durable telemetry.
    # Sunday weekly review also surfaces current 7d quality stats.
    # Quarterly sweep (Feb/May/Aug/Nov 1st) surfaces 90d quarter-wide view.
    async def _news_quality_drift_check_job():
        from agents.market_intelligence.news_source_quality import run_quality_check
        await run_quality_check()

    _scheduler.add_job(
        audit_wrap(_news_quality_drift_check_job, "news_quality_drift_check"),
        CronTrigger(hour=16, minute=30, day_of_week="mon-fri",
                    timezone="America/New_York"),
        id="news_quality_drift_check",
        replace_existing=True,
        misfire_grace_time=3600,  # 1h grace; missed once is fine, next day runs
    )

    # Theme round-trip outcome validator: 6:00 AM ET daily (Area 2,
    # 2026-05-15). Defense-in-depth secondary catch for hallucinated
    # themes where ≥50% of members are stripped within 3 days of
    # creation. Pure observability; emits theme_high_strip_rate audit
    # + Telegram on first detection per (theme, day).
    _scheduler.add_job(
        audit_wrap(_theme_round_trip_validator_job, "theme_round_trip_validator"),
        CronTrigger(hour=6, minute=0, timezone="America/New_York"),
        id="theme_round_trip_validator",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # Crypto RS nightly ingest: 6:00 PM ET mon-sun (crypto trades 24/7; daily
    # cadence is sufficient for our RS surveillance use case). Slots after
    # post_nightly_audit (17:30) so equity ingestion is settled first.
    # Shadow mode (CRYPTO_RS_ENABLED=false) by default — pipeline runs and
    # collects data, but Telegram surfaces stay quiet.
    _scheduler.add_job(
        audit_wrap(_crypto_nightly_ingest_job, "crypto_nightly_ingest", expected_min_rows=10),
        CronTrigger(hour=18, minute=0, timezone="America/New_York"),
        id="crypto_nightly_ingest",
        replace_existing=True,
        misfire_grace_time=3600,  # 1h: history fetch + RS + macro can take 20+ min
    )

    # Crypto category-membership refresh: Sundays 19:00 ET. Hits CG /coins/{id}
    # per universe coin to pull `categories` array — ~250 calls throttled to
    # 30/min = ~10 min of work. Low churn (categories rarely change), so weekly
    # is plenty. Slots after the Sunday nightly_ingest at 18:00.
    _scheduler.add_job(
        audit_wrap(_crypto_category_refresh_job, "crypto_category_refresh", expected_min_rows=50),
        CronTrigger(hour=19, minute=0, day_of_week="sun", timezone="America/New_York"),
        id="crypto_category_refresh",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Minute volume curves refresh: 6:30 PM ET — rebuild RVOL@T baselines for
    # the top-500 dollar-volume universe. Slots after 6:00 evening briefing.
    # Idempotent; if missed, next run recomputes from scratch.
    _scheduler.add_job(
        audit_wrap(_minute_volume_curves_refresh_job, "minute_volume_curves_refresh", expected_min_rows=50000),
        CronTrigger(hour=18, minute=30, day_of_week="mon-fri", timezone="America/New_York"),
        id="minute_volume_curves_refresh",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # Live position update: 4:45 PM ET — SMA trail, partials, stop updates
    # PAUSED 2026-05-29 per task #151 (advisor decision Option D). Two consecutive
    # days of automated partial-take failure on IBM via distinct bug classes
    # (5/27 cancel→new race fixed by #136; 5/28 str→numeric in #136's fix; today
    # surfaced 4th class: replace_order_by_id non-atomic on Alpaca paper,
    # share-hold release lags ~10ms after API returns successfully).
    #
    # Restoration gated on #151:
    #   (a) execute_partial_exit architectural split with verify-broker-state
    #       between each step (specifically: verify old_stop_id released before
    #       submit_partial_sell)
    #   (b) Preflight Gate G6 — integration test against paper Alpaca in deploy
    #   (c) Outcome-history circuit breaker — auto-halt on N=2 consecutive fails
    #
    # In the meantime: operator uses /partialnow TICKER for any qualifying
    # partial-take. Each invocation is a single explicit confirmation, not an
    # automated batch hitting 3+ trades simultaneously.
    #
    # _scheduler.add_job(
    #     audit_wrap(_live_position_update_job, "live_position_update"),
    #     CronTrigger(hour=16, minute=45, day_of_week="mon-fri", timezone="America/New_York"),
    #     id="live_position_update",
    #     replace_existing=True,
    # )

    # 9M EP intraday scan: every 5 min, 9:30 AM – 4:00 PM ET (regular session)
    _scheduler.add_job(
        audit_wrap(_9m_scan_job, "9m_ep_scan"),
        CronTrigger(hour="9-15", minute="*/5", day_of_week="mon-fri", timezone="America/New_York"),
        id="9m_ep_scan",
        replace_existing=True,
    )

    # 9M Day 2 ORB: 9:31 AM ET — place ORB entries for yesterday's sugar babies
    _scheduler.add_job(
        audit_wrap(_9m_day2_orb_job, "9m_day2_orb"),
        CronTrigger(hour=9, minute=31, day_of_week="mon-fri", timezone="America/New_York"),
        id="9m_day2_orb",
        replace_existing=True,
    )

    # Cross-strategy unified allocator (#31) Phase 1A — SHADOW.
    # Runs at 9:35 ET (after MAGNA53 ORB monitor + 9M Day 2 cron have populated
    # mi_pending_allocations). Scores every queued candidate, marks shadow_rank
    # + shadow_allocated, emits `unified_allocation_decided` audit event with
    # full ranking. Does NOT submit. Phase 1B (active) will move this to 9:28
    # ET pre-market and replace the legacy submission paths.
    _scheduler.add_job(
        audit_wrap(_unified_allocator_shadow_job, "unified_allocator_shadow"),
        CronTrigger(hour=9, minute=35, day_of_week="mon-fri", timezone="America/New_York"),
        id="unified_allocator_shadow",
        replace_existing=True,
    )

    # HUD auto-refresh: hourly during market hours — edits the pinned message in-place.
    # Weekdays only; outside market hours /hud works on-demand but the scheduler doesn't push.
    _scheduler.add_job(
        audit_wrap(_hud_refresh_job, "hud_refresh"),
        CronTrigger(hour="9-15", minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="hud_refresh",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Market Intelligence scheduler started (ET timezone)")

    # One-shot post-boot order reconcile (#123, 2026-05-26): closes the
    # deploy-during-market-hours gap where a container restart loses live
    # WebSocket trade_update events. Runs 60 seconds after boot to let
    # Alpaca clients finish their dual-account verification first.
    now_et_for_boot = datetime.now(_ET)
    if now_et_for_boot.weekday() < 5 and _dt_time(9, 30) <= now_et_for_boot.time() <= _dt_time(16, 5):
        _scheduler.add_job(
            audit_wrap(_order_status_reconcile_job, JOB_ORDER_STATUS_RECONCILE + "_boot"),
            "date",
            run_date=now_et_for_boot + timedelta(seconds=60),
            id=JOB_ORDER_STATUS_RECONCILE + "_boot",
            replace_existing=True,
            misfire_grace_time=600,
        )

    # SIGTERM handler — wait for in-flight jobs to reach their finally path
    # before exiting. Without this, Docker stop/restart kills `await` inside
    # audit_run mid-job → mi_job_runs row stuck at status='running' (the
    # stale-row reaper at startup catches these but it's hygiene; this is
    # prevention).
    #
    # Registration order (advisor flag 2026-05-08): try asyncio loop's
    # add_signal_handler first — composes with uvicorn's own signal
    # handling instead of competing via signal.signal which uvicorn
    # may overwrite. Falls back to signal.signal on Windows / no running
    # loop. Stale-row reaper at startup is the backup if both fail.
    import signal
    import asyncio as _asyncio

    def _trigger_shutdown():
        logger.info("SIGTERM received — graceful shutdown (waiting for in-flight jobs)")
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=True)
            logger.info("Scheduler shutdown complete")

    try:
        loop = _asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, _trigger_shutdown)
        logger.info("SIGTERM handler registered via asyncio.add_signal_handler")
    except (RuntimeError, NotImplementedError) as e:
        # No running loop (e.g. called from sync context) or Windows.
        # Fall back to signal.signal — works in main thread of main interpreter.
        try:
            signal.signal(signal.SIGTERM, lambda signum, frame: _trigger_shutdown())
            logger.info(f"SIGTERM handler registered via signal.signal (loop unavailable: {e})")
        except (ValueError, OSError) as e2:
            logger.warning(
                f"Could not register SIGTERM handler "
                f"(asyncio: {e}; signal: {e2}). Stale-row reaper is the backup."
            )

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
