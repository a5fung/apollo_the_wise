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
from datetime import datetime, time as _dt_time, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

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
from agents.market_intelligence import close_digest
from agents.market_intelligence.constants import mode_prefix, active_account_modes
from agents.market_intelligence.backtester.tracker import (
    run_paper_trade_tracker,
    format_tracker_telegram,
)
from core.notifications import notify_job_failure, notify_job_success
from core.job_audit import audit_wrap
from shared.llm_models import DESCRIPTION_MODEL
from shared.llm_response import first_text

logger = logging.getLogger(__name__)

# Job name constants — used in mi_job_log; must match exactly
JOB_NIGHTLY_DATA_PULL = "nightly_data_pull"
JOB_EVENING_BRIEFING = "evening_briefing"
JOB_MORNING_BRIEFING = "morning_briefing"
JOB_PARABOLIC_SCAN = "parabolic_scan"
JOB_WICK_FORWARD_RETURNS = "wick_forward_returns"
JOB_FLAG_SCAN = "flag_continuation_scan"
JOB_SUGAR_BABIES_COHORT_REFRESH = "sugar_babies_cohort_refresh"
JOB_TIME_STOP_SCAN = "time_stop_scan"
JOB_FLAG_BREAK_SCAN = "flag_break_scan"
JOB_SUPPORT_TEST_SCAN = "support_test_scan"
JOB_MA_PULLBACK_SCAN = "ma_pullback_scan"
JOB_LOW_VOL_REST_SCAN = "low_vol_rest_scan"
JOB_UNDERCUT_RALLY_SCAN = "undercut_rally_scan"
JOB_BACKUP_HEALTH_CHECK = "backup_health_check"
JOB_ORDER_STATUS_RECONCILE = "order_status_reconcile"
JOB_9M_PACE_DIGEST = "9m_pace_digest"
JOB_CATALYST_DOWNGRADE_DIGEST = "catalyst_downgrade_digest"
JOB_JUDGE_DELTA_DIGEST = "judge_delta_digest"
JOB_MODEL_RESOLUTION_REFRESH = "model_resolution_refresh"
JOB_JUDGE_EVAL_DIVERGENCE_CHECK = "judge_eval_divergence_check"

# ── Service-split job partition (#256 W2, 2026-06-13) ────────────────────────
# The EXECUTION service owns broker / streams / safeguards / trade-state jobs;
# the INTELLIGENCE service owns detection / themes / judge / briefings. Until
# cutover the single process runs SERVICE_ROLE=combined = BOTH sets (this set is
# inert at combined default). Source of truth = the W2 partition table in
# ~/.claude/plans/execution-intelligence-split-256.md (operator-approved).
# NB: the post-start conditional `order_status_reconcile_boot` job is gated on
# runs_execution_jobs() at its own registration site (it is added AFTER the
# partition pass), so it is intentionally NOT in this main-body set.
#
# Fallback fill-checker fires (HH, MM ET): the WebSocket trade-stream is primary,
# these poll Alpaca for fills only when it goes unhealthy. SSoT for BOTH the
# scheduler registration AND the execution partition so a new fire time can't
# register without auto-joining the execution set (the omission the W2 audit
# caught 2026-06-13: the 7 ids were registered but absent here, so the split
# would have dropped the broker fallback from execution AND handed it to the
# credential-less intelligence service).
_FILL_CHECK_TIMES = [(10, 0), (10, 30), (11, 0), (12, 0), (13, 0), (14, 0), (15, 0)]
_CHECK_FILLS_JOB_IDS = frozenset(
    f"check_fills_{h:02d}{m:02d}" for h, m in _FILL_CHECK_TIMES
)

EXECUTION_OWNED_JOB_IDS = frozenset({
    # ORB / entry
    "orb_window_cleanup", "shadow_orb_entry", "shadow_orb_exit",
    "orb_reclassify_eod", "bar_stream_cleanup",
    # lifecycle / reconcile / safeguards
    "paper_trade_tracker", "morning_stop_refresh", "post_close_stop_refresh",
    "position_coverage_check",  # #527 — market-hours broker-truth coverage detector
    "live_position_update",
    "partial_exit_scan",  # #361 — 3:45 PM market-hours partial-profit (split from 4:45)
    "evening_position_backstop", JOB_ORDER_STATUS_RECONCILE,
    JOB_ORDER_STATUS_RECONCILE + "_open", "track_position_extremes",
    "position_path_eod_sweep",  # #306 — 16:10 ET path-recorder EOD completion sweep
    "stuck_fill_watchdog", "stop_ack_timeout_watchdog", "stream_health_watchdog",
    "eod_cleanup", JOB_TIME_STOP_SCAN, "account_equity_snapshot",
    "unified_allocator_shadow",
}) | _CHECK_FILLS_JOB_IDS

# Declared INTELLIGENCE jobs — detection / themes / judge / briefings / audits /
# data. Routing still treats intelligence as "everything not execution-owned"
# (byte-identical), so this manifest is NOT a routing input; it is the
# COMPLETENESS ORACLE for the omission guard in `_apply_role_partition`. Without
# it, the existing fail-loud guards only catch a de-registered or leaked
# execution id — NOT a NEW execution job simply never added to
# EXECUTION_OWNED_JOB_IDS, which would silently route to intelligence (exactly
# the check_fills class the 6/13 audit caught). A registered job in NEITHER set
# fails the split-role boot loudly. Keep disjoint from EXECUTION_OWNED (the
# verify script + a test assert this). Conditionally-registered jobs (e.g.
# crypto) belong here too — for THIS manifest the guard is one-directional
# (registered ⊆ classified), so a classified-but-unregistered intelligence id is
# harmless. EXECUTION_OWNED is stricter: checked BIDIRECTIONALLY in both split
# roles (#279) — a stale execution entry fails boot, so execution jobs must stay
# unconditionally registered.
INTELLIGENCE_OWNED_JOB_IDS = frozenset({
    # detection scans
    "ep_scan", "ep_scan_open", "ep_scan_start", "ep_scan_stop",
    "ep_scan_watchdog", "9m_ep_scan", "parabolic_scan", "flag_break_scan",
    "flag_continuation_scan", "low_vol_rest_scan",
    "ma_pullback_scan", "support_test_scan", "undercut_rally_scan",
    "anticipation_readiness", "anticipation_3b", "consolidation_readiness",
    "htf_management_shadow",  # #396 HTF Phase 4 — pure compute + DB/audit-log only, no broker calls
    "giveback_shadow",  # ADR 0023 F1 — peak-lock counterfactual on the live book; pure compute + DB, no broker calls
    "pivot_stop_shadow",  # ADR 0031 — pivot/character-stop counterfactuals on closed trades; pure compute + DB, no broker calls
    "sell_discipline_recorder",  # #508 WS1 — reached-vs-kept record per closed trade; pure compute + DB/audit, no broker calls, no rule
    "theme_axis_co_move_refresh",  # #329 STEP-0 — EOD co-movement backfill for the theme-axis shadow; pure compute + DB/audit, no broker calls
    "book_concentration",  # #452 R1 Stage 1 — correlated-book telemetry (premortem TOP risk); read-only + audit, Telegram only when flagged
    "spend_alarm",  # #378 Phase 2 — daily LLM-spend alarm (budget cap + 2x-median anomaly); read-only, Telegram only on breach
    "delayed_residual",  # #489 — EOD delayed-feed residual tracker; read-only (Polygon replay + DB/audit), no broker calls
    "rt_miss_digest",  # #489 — 10:00 ET residual real-time-miss morning digest; read-only (mi_audit_log + Telegram)
    # themes / validation
    "theme_synthesis", "theme_round_trip_validator", "post_validation_check",
    "coverage_probe",  # S2 coverage loop — zero-LLM EOD blind-spot probe; shadow tables + audit only, no broker calls
    # judge / digests / briefings
    "judge_delta_digest", "catalyst_downgrade_digest", "9m_pace_digest",
    "intraday_signals_eod_digest", "eod_ep_recap", "morning_briefing",
    "close_digest",  # #479 — 16:55 ET consolidated Market Close Digest flush
    "premarket_gap_risk",  # ADR 0023 Card 5 — read-only 9:00 ET gap-through heads-up, no broker calls
    "evening_briefing", "friday_watchlist", "hud_refresh",
    "sugar_babies_cohort_refresh", "position_mgmt_judge",
    "chart_axis_shadow", "chart_axis_shadow_weekly_digest", "kill_scale_band_eval",
    # data / RS / regime / crypto
    "nightly_data_pull", "baseline_refresh", "minute_volume_curves_refresh",
    "wick_forward_returns", "crypto_category_refresh", "crypto_nightly_ingest",
    # audits / health / methodology
    "post_eod_audit", "post_nightly_audit", "weekly_system_review",
    "monthly_backward_check_sweep", "news_quality_drift_check",
    "source_gap_finder", "backup_health_check", "telegram_poll_watchdog",
    "weekly_cleanup",
    # model registry (#509) — INTELLIGENCE, and deliberately not execution: both
    # only read models.list + write the resolution cache/audit rows, and the boot
    # recorder is already `runs_intelligence_jobs()`-gated, so running them on
    # execution too would double-record and double-Telegram every release.
    "model_resolution_refresh", "judge_eval_divergence_check",
})


def _job_belongs_to_role(job_id: str, role: str) -> bool:
    """Does a job with `job_id` run under `role`? combined runs everything;
    execution runs only the execution-owned set; intelligence runs the rest."""
    if role == "combined":
        return True
    if role == "execution":
        return job_id in EXECUTION_OWNED_JOB_IDS
    # intelligence
    return job_id not in EXECUTION_OWNED_JOB_IDS


def _apply_role_partition(scheduler, role: str) -> dict:
    """Remove jobs this service role does NOT own, fail LOUD on a partition
    mistake (#256 W2). combined = no-op (byte-identical to pre-split).

    Three fail-loud guards (a partition bug must never silently drop a safety
    job or run a broker job in the wrong service):
      - omission (both split roles): every REGISTERED job must be classified in
        EXECUTION_OWNED_JOB_IDS or INTELLIGENCE_OWNED_JOB_IDS. An unclassified
        job would silently route to intelligence (the check_fills class) — this
        guard turns that into a loud boot failure at the cutover where it bites.
      - stale-entry (both split roles — was execution-only pre-#279): every id
        in EXECUTION_OWNED_JOB_IDS must be REGISTERED. Together with the
        omission guard this makes the partition check BIDIRECTIONAL: a renamed
        job whose partition entry went stale fails as loudly as an
        unpartitioned one, at whichever split service boots first (in execution
        the stale id would silently DROP a trade/safeguard job; in intelligence
        it's a dangling manifest entry that must not wait for the next
        execution deploy to surface). Safe in both roles because every
        execution-owned registration is unconditional by design — conditional
        jobs (order_status_reconcile_boot, added post-partition) are
        deliberately outside the set.
      - intelligence: NO execution-owned id may survive the removal.
    """
    registered = {j.id for j in scheduler.get_jobs()}
    if role == "combined":
        logger.info(f"Job partition: role=combined — all {len(registered)} jobs kept")
        return {"role": role, "kept": list(registered), "removed": []}

    # Omission guard (registered ⊆ classified). Runs only in split roles, so it
    # can never break combined-mode production boot.
    unclassified = registered - EXECUTION_OWNED_JOB_IDS - INTELLIGENCE_OWNED_JOB_IDS
    if unclassified:
        raise RuntimeError(
            f"Job partition FAILED (role={role}): unclassified registered jobs: "
            f"{sorted(unclassified)} — classify each in EXECUTION_OWNED_JOB_IDS or "
            f"INTELLIGENCE_OWNED_JOB_IDS before boot. An unclassified job would "
            f"silently route to intelligence (the check_fills omission class). "
            f"Refusing to boot."
        )

    # Stale-entry guard (EXECUTION_OWNED ⊆ registered) — the reverse direction
    # of the omission guard, in BOTH split roles (#279; execution-only before).
    missing = EXECUTION_OWNED_JOB_IDS - registered
    if missing:
        raise RuntimeError(
            f"Job partition FAILED (role={role}): expected execution jobs "
            f"not registered: {sorted(missing)} — a stale partition entry "
            f"(renamed/removed job?). In execution role a missing id would "
            f"silently DROP a trade/safeguard job. Refusing to boot."
        )

    removed = []
    for jid in registered:
        if not _job_belongs_to_role(jid, role):
            scheduler.remove_job(jid)
            removed.append(jid)
    kept = sorted(registered - set(removed))

    if role == "intelligence":
        leaked = set(kept) & EXECUTION_OWNED_JOB_IDS
        if leaked:
            raise RuntimeError(
                f"Job partition FAILED (role=intelligence): execution-owned jobs "
                f"survived: {sorted(leaked)} — a broker job must NOT run in "
                f"intelligence. Refusing to boot."
            )

    logger.info(
        f"Job partition: role={role} — kept {len(kept)}, removed {len(removed)}. "
        f"removed={sorted(removed)}"
    )
    return {"role": role, "kept": kept, "removed": sorted(removed)}


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
                from agents.market_intelligence.theme_engine import FUND_EXPOSURE_PROMPT_RULE
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
                    + FUND_EXPOSURE_PROMPT_RULE + "\n\n"
                    "Return ONLY a JSON object mapping ticker to description. No markdown, no explanation.\n"
                    "Example: {\"ACME\": \"Industrial automation, robotics\"}\n\n"
                    "Stocks:\n" + "\n".join(stock_lines)
                )

                resp = await client.messages.create(
                    model=DESCRIPTION_MODEL,
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}],
                )
                # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
                from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
                await log_anthropic_call_safe(model=DESCRIPTION_MODEL,
                                               caller="description_backfill",
                                               usage=getattr(resp, "usage", None),
                                               stop_reason=getattr(resp, "stop_reason", None))
                import json
                raw = first_text(resp).strip()  # #544: never content[0]
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
        # #376: alert on credit exhaustion (deduped) before the fail-open.
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("description backfill", e)
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
                    except Exception as e:
                        logger.debug(f"quote-type lookup failed for {ticker}, defaulting to EQUITY: {e}")
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

    # 5b. Theme-discovery SHADOW pass (ADR 0007) — runs the new nascent-discovery
    # selectors (a/a2) on the widened assembly (c/c2) into mi_theme_candidates_shadow,
    # WITHOUT touching live mi_themes / the brief. ERROR-WRAPPED + non-fatal: a failure
    # here must NEVER break the live theme run above. Shadow-only until the N-night diff
    # validates promotion (ADR 0007 §5). Skips non-trading days with the rest of this job.
    #
    # Theme consolidation Phase 1 (operator-ruled 2026-07-27, decision 1): in mode
    # 'on' the shadow_v2 STREAM IS RETIRED — its a/a2 selectors were ported INTO
    # run_theme_engine's discovery pool first (5a above runs them), so skipping here
    # loses nothing. Fail-closed mode read: 'off'/'observe'/error ⇒ the pass runs
    # exactly as today (byte-identical — observe must change NOTHING behavioral).
    # Audited nightly when retired, never silent.
    try:
        from agents.market_intelligence.db import get_theme_birth_gate_mode
        if (await get_theme_birth_gate_mode()) == "on":
            logger.info("Theme shadow pass (ADR 0007) SKIPPED — shadow_v2 stream retired (birth-gate ON)")
            await log_audit_event(
                "shadow_v2_stream_retired",
                summary="shadow_v2 discovery stream retired (theme_birth_gate mode 'on') — "
                        "a/a2 selectors run inside Lane-1 discovery",
                detail="run_theme_discovery_shadow skipped; no source='shadow_v2' rows written tonight",
            )
            summary_parts.append("shadow:retired")
        else:
            from agents.market_intelligence.theme_engine import run_theme_discovery_shadow
            shadow_summary = await run_theme_discovery_shadow(_today, clusters=correlation_clusters)
            logger.info(f"Theme shadow pass (ADR 0007): {shadow_summary}")
            summary_parts.append(f"shadow:{shadow_summary.get('shadow_themes', 0)}")
    except Exception as e:
        logger.warning(f"Theme shadow pass failed (non-fatal, ADR 0007): {e}")
        # Audit the swallowed failure — a bare logger.warning let #173 die silently for
        # days (it rotates out on container restart; the DB row persists + is queryable).
        # log_audit_event is module-level (line 28); a function-local re-import here would
        # shadow it and trip the [5d] UnboundLocalError guard (refs at 452/488 precede it).
        try:
            await log_audit_event(
                "theme_discovery_shadow_failed",
                summary="Theme discovery shadow raised (non-fatal)",
                detail=f"{type(e).__name__}: {e}",
            )
        except Exception:  # loud-ok: audit-of-audit best-effort; outer logger.warning above already surfaced the real error
            pass

    # 5c. #167 NARRATIVE-theme discovery (C2/C3 rung-1, shadow) — groups same-day EP
    # alerts by SHARED CATALYST-NARRATIVE via one Sonnet call; catches cross-sector /
    # govt-policy themes the RS+correlation engine structurally misses (validated 6/2:
    # drone cohort step-b + §5 PASS). discover_narrative_themes is itself fully
    # error-wrapped; this hook is belt-and-suspenders so it can NEVER break the pull.
    try:
        from agents.market_intelligence.theme_engine import discover_narrative_themes
        narr = await discover_narrative_themes(_today)
        logger.info(f"Narrative-theme discovery (#167): {narr}")
        summary_parts.append(f"narrative:{narr.get('themes', 0)}")
    except Exception as e:
        logger.warning(f"Narrative-theme discovery failed (non-fatal, #167): {e}")

    # 5d. #226 GRADUATION — promote qualifying shadow cohorts (5b shadow_v2 + 5c narrative) into the
    # LIVE mi_themes table (operator 2026-06-28: "graduate this ASAP" — the missing promo path was the
    # gap that let cohorts sit idle). Runs AFTER the live theme save (5a; its DELETE is now
    # source='live'-scoped so it can't clobber promoted rows) and AFTER the shadow lanes write, so it
    # reads today's fresh cohorts. Error-wrapped + non-fatal: a promote failure must NEVER break the pull.
    try:
        from agents.market_intelligence.theme_engine import promote_shadow_themes
        n_promoted = await promote_shadow_themes(_today)
        logger.info(f"Shadow->live graduation (#226): promoted {n_promoted}")
        summary_parts.append(f"promoted:{n_promoted}")
    except Exception as e:
        logger.warning(f"Shadow->live graduation failed (non-fatal, #226): {e}")
        try:
            await log_audit_event(
                "shadow_promotion_failed",
                summary="Shadow->live graduation raised (non-fatal)",
                detail=f"{type(e).__name__}: {e}",
            )
        except Exception:  # loud-ok: outer logger.warning already surfaced the real error; audit is best-effort
            pass

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
        except Exception as e:
            logger.warning(
                f"fundamental flags: active-themes fetch failed, falling back to "
                f"RS-leaders-only ticker set: {e}"
            )
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
        # #197 cap+1 shadow ledger — persist every cap_blocked decision durably
        # (the missed-outcomes window rolls; the ledger must not). Telemetry-only.
        from agents.market_intelligence.missed_outcomes import record_cap_plus_one_shadow
        cap_led = await record_cap_plus_one_shadow()
        await log_audit_event(
            "cap_plus_one_shadow_recorded",
            f"ledger: {cap_led['total_ledger']} total "
            f"({cap_led['recent_window']} in 30d window)",
        )
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
        from agents.market_intelligence.broker.orb_extension_shadow import (  # exec-boundary-ok: moves-with-job (W2)
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

    # Check for silent engine errors (parse failures, API errors that didn't
    # hard-fail). Body lives in _check_nightly_silent_errors (extracted
    # 2026-07-12 RED-3b so the alert wiring is unit-testable — same behavior).
    try:
        await _check_nightly_silent_errors()
    except Exception as e:
        logger.error(f"Error check after nightly run failed: {e}")

    if failures:
        await notify_job_failure(JOB_NIGHTLY_DATA_PULL, " | ".join(failures))
    else:
        await log_job_run(JOB_NIGHTLY_DATA_PULL)
        await notify_job_success(JOB_NIGHTLY_DATA_PULL, ", ".join(summary_parts))

    logger.info("Nightly data pull complete")
    return int(scored or 0)


async def _check_nightly_silent_errors() -> None:
    """Post-nightly silent-failure surfacer (called at the end of
    _nightly_data_pull; extracted 2026-07-12 RED-3b for testability).

    Buckets by category so a flood of one type (e.g. Anthropic 5xx burst)
    collapses to a single line and doesn't drown out genuinely novel errors.

    RED-3b: `drawdown_check_unavailable` matches NONE of the LIKE patterns
    below (no "error"/"rate_limited"/"api_failure" in the name), so a
    FAIL-OPEN drawdown-breaker check was invisible here. It is now fetched
    explicitly — with a 6h window, not 2h, because the event fires at the
    16:12 ET equity-snapshot job while this check runs at the END of the
    nightly pull (17:30–18:30+); a 2h window can straddle past it.
    """
    from agents.market_intelligence.audit_events import DRAWDOWN_CHECK_UNAVAILABLE

    error_rows = await get_audit_log(limit=40, event_type_like="%error%", since_hours=2)
    rate_rows = await get_audit_log(limit=40, event_type_like="%rate_limited%", since_hours=2)
    api_rows = await get_audit_log(limit=40, event_type_like="%api_failure%", since_hours=2)
    safeguard_rows = await get_audit_log(
        limit=40, event_type=DRAWDOWN_CHECK_UNAVAILABLE, since_hours=6,
    )
    rate_limited_types = {"validation_rate_limited", "anthropic_rate_limited",
                          "assignment_rate_limited", "discovery_rate_limited"}
    api_failure_types  = {"validation_api_failure", "assignment_api_failure",
                          "discovery_api_failure"}
    parse_error_types  = {"validation_error"}
    buckets: dict[str, list] = {"rate_limited": [], "api_failure": [],
                                 "validation_error": [], "safeguard_unavailable": [],
                                 "other": []}
    seen_ids: set = set()
    for r in (error_rows + rate_rows + api_rows + safeguard_rows):
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
        elif evt == DRAWDOWN_CHECK_UNAVAILABLE:
            buckets["safeguard_unavailable"].append(r)
        elif "error" in evt:
            buckets["other"].append(r)
    total = sum(len(v) for v in buckets.values())
    if total:
        lines = [f"⚠️ *{total} engine event(s) during nightly run:*"]
        if buckets["safeguard_unavailable"]:
            # Static text only (no dynamic summary echo — an unpaired `_` in
            # legacy-Markdown 400s the send, 2026-07-05 lesson); the event
            # name is backtick-fenced for the same reason.
            lines.append(
                f"  🔴 {len(buckets['safeguard_unavailable'])} "
                f"`drawdown_check_unavailable` event(s) — drawdown breaker "
                f"FAIL-OPEN; verify 16:12 equity snapshot / Alpaca API"
            )
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


async def _evening_briefing_job():
    """Run at 6:00 PM ET (3:00 PM PT) — CronTrigger hour=18 below is authoritative. Send evening
    briefing — full EOD review package. (Was mislabeled '8:00 PM' here for a while; the actual
    fire time is 18:00 ET — #479 moved/confirmed it, and assuming 8PM caused a bad deploy-timing
    call 2026-07-20. Update this string with the cron, never independently.)"""
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

    # Health-guard HEARTBEAT (#370 increment 4): runs HERE (the 9 AM brief), independent of the 17:30
    # audit that hosts the null-rate + job-liveness sweeps — if THAT job dies, this still fires. OWN
    # try/except so an EP-scan or briefing failure above can't suppress the guard's own liveness check.
    try:
        from agents.market_intelligence.health_checks import run_health_heartbeat
        hb = await run_health_heartbeat()
        logger.info(f"Health heartbeat: {hb.get('status')}")
    except Exception as e:
        logger.error(f"Health heartbeat failed: {e}", exc_info=True)
        await notify_job_failure("health_heartbeat", str(e))


async def _ep_scan_job():
    """Run every 5 minutes 7:00–10:00 AM ET. Scan for EP gaps; HIGH alerts sent immediately.

    Pre-market new HIGHs: subscribed to bar stream for real-time first-bar ORB entry.
    Post-open new HIGHs: bar already closed, ORB entry triggered inline immediately."""
    logger.info("EP scan starting...")
    try:
        from agents.market_intelligence.collector import et_today, _ET
        from agents.market_intelligence.execution_client import subscribe_orb_candidate
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

        # #444 mode-label sweep: both the pre-market bar-stream subscribe path
        # (below) and the out-of-ORB-window skip path (further down) attribute
        # to magna53's account — resolved lazily (at most once per scan tick,
        # only if a HIGH actually needs it) rather than unconditionally so a
        # no-HIGH scan tick costs no extra strategy lookup.
        _ep_mode_fetched = False
        _ep_account_mode: str | None = None

        async def _magna53_account_mode() -> str | None:
            nonlocal _ep_mode_fetched, _ep_account_mode
            if not _ep_mode_fetched:
                # Shared fail-open resolver (review 7/17 dedup): never aborts
                # the subscribe/skip paths; a failure emits
                # strategy_mode_resolve_error (morning error banner) instead of
                # a silent container-log line — mode_prefix(None) then falls
                # back to the legacy global default.
                from agents.market_intelligence.constants import resolve_strategy_mode_nonfatal
                _ep_account_mode = await resolve_strategy_mode_nonfatal("magna53")
                _ep_mode_fetched = True
            return _ep_account_mode

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
                    # Pre-market — subscribe to bar stream; ORB fires when first bar closes.
                    # Threaded account_mode (#444): so a per-ticker subscribe-failure alert
                    # (bar_stream._record_subscribe_failure) labels correctly for a live HIGH.
                    await subscribe_orb_candidate(ep["ticker"], account_mode=await _magna53_account_mode())
                else:
                    # HIGH arrived after ORB window closed — no order possible. Persist a
                    # skipped-trade row + audit event + Telegram so every HIGH alert has a
                    # durable terminal state for evening brief / `/why`.
                    from agents.market_intelligence.execution_client import record_skipped_trade
                    from agents.market_intelligence.broker.skip_reasons import WINDOW_OUT_OF_ORB
                    from agents.market_intelligence.collector import et_today
                    # Attribute this skip + its alerts to the OWNING strategy's Alpaca
                    # account (magna53 = the EP strategy). Was defaulting to the legacy
                    # paper mode, so a live-money EP HIGH read as PAPER + its skip row
                    # landed under paper in the EOD summary (operator 7/8).
                    ep_mode = await _magna53_account_mode()
                    skip_msg = f"{WINDOW_OUT_OF_ORB}: detected {now_et.strftime('%H:%M')} ET"
                    try:
                        await record_skipped_trade(
                            ep["ticker"], et_today(), ep, None, skip_msg,
                            signal_type="magna53", account_mode=ep_mode,
                        )
                    except Exception as ins_e:
                        # NON-NEGOTIABLE (feedback_no_silent_trading_failures): a
                        # logger.error-only swallow here is EXACTLY what hid the
                        # LZB gap for ~4 days — the daily invariant caught it, we
                        # didn't. Make the write-failure LOUD. The immediate
                        # Telegram below is the real-time alert; the audit row
                        # (named `*_error` so it matches the '%error%' surfacer)
                        # is the durable backstop for `show errors` + the Sunday
                        # weekly review (7d window).
                        logger.error(f"Could not insert out-of-ORB skip for {ep['ticker']}: {ins_e}")
                        try:
                            await log_audit_event(
                                "skip_row_write_error",
                                f"{ep['ticker']} out-of-ORB skip row NOT persisted — "
                                f"{type(ins_e).__name__}: {ins_e}",
                            )
                        except Exception:
                            pass
                        await send_telegram_message(
                            f"{mode_prefix(ep_mode)}🚨 *{ep['ticker']}* skip-row write FAILED "
                            f"({type(ins_e).__name__}) — HIGH alert has no terminal "
                            f"state; check execution service"
                        )
                    try:
                        # NOTE: do NOT `from ... import log_audit_event` here —
                        # it's imported at module level + referenced earlier in
                        # this function, so a local import would shadow and
                        # cause UnboundLocalError (2026-05-20 ep_detector bug).
                        await log_audit_event("orb_out_of_window", f"{ep['ticker']} — {skip_msg}")
                    except Exception:
                        pass
                    await send_telegram_message(
                        f"{mode_prefix(ep_mode)}⏰ *{ep['ticker']}* HIGH EP arrived {now_et.strftime('%H:%M')} ET — "
                        f"ORB window closed, no order"
                    )
                    logger.info(f"EP {ep['ticker']}: outside ORB window ({now_et.strftime('%H:%M')} ET) — alert sent, no order")

        # ORB entry is EXECUTION-owned (#256 W2): route through the facade so
        # the split hands it to the execution service without changing this site
        # again. inprocess = byte-identical direct call to _orb_monitor_job.
        from agents.market_intelligence.execution_client import trigger_orb_entry
        if new_highs_post_open:
            logger.info(f"Post-open new HIGHs {new_highs_post_open} — triggering ORB entry via execution facade")
            await trigger_orb_entry(trigger="post_open_new_high")
        elif within_orb_window and now_et.minute == 31:
            # 9:31 open scan: always run ORB as fallback for pre-market HIGHs
            # bar_stream handles them in real-time, but if stream was unhealthy or missed
            # a subscription, process_new_alerts_live skips already-processed tickers safely.
            logger.info("9:31 ORB fallback: checking for unprocessed pre-market HIGHs")
            await trigger_orb_entry(trigger="cron_9_31")

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


async def _delayed_residual_job():
    """#489 — EOD delayed-feed residual tracker. Records the QUALITY in-window (9:31-9:44) 10%-crossers
    the ~16-min Polygon detection delay made us miss + whether the 5% hybrid would catch each.

    #490 §9.4 (operator-signed 2026-07-24): the O-9 escalation trigger is RETIRED — its question
    ("escalate to full-RT?") was consumed by the #490 ruling, and its metric ran on the wrong (close)
    basis. This job now (a) stamps CROSS-basis forward outcomes, (b) runs the RT-2/RT-4 proof-join
    (every hybrid_caught=false row on a shadow/cutover day must have a same-day
    `ep_rt_universe_catch`), and (c) logs the regression-monitor stats (post-cutover the residual
    count should trend ~0 — a sustained nonzero = the overlay is leaking)."""
    from agents.market_intelligence.ep_delayed_residual import (
        run_delayed_residual_scan, backfill_residual_outcomes,
        residual_regression_stats, rt_shadow_capture_join)
    run_date = datetime.now(_ET).strftime("%Y-%m-%d")
    missed, residual = await run_delayed_residual_scan(run_date)
    logger.info(f"delayed_residual_job {run_date}: {missed} missed, {residual} residual beyond hybrid")
    # G3: stamp forward outcomes on settled misses (cross-basis since #490 §9.4).
    await backfill_residual_outcomes()
    stats = await residual_regression_stats()
    logger.info(f"residual regression monitor: count={stats['count']} median_fwd5d={stats['median_fwd5d']}")
    # #490 RT-2/RT-4 proof-join — only meaningful once the Pass-0 overlay is fetching (the master
    # env flag); before that there are no catch events and 0-coverage would be pure noise.
    from agents.market_intelligence.ep_detector import EP_RT_UNIVERSE_ENABLED
    if EP_RT_UNIVERSE_ENABLED:
        join = await rt_shadow_capture_join(run_date)
        await log_audit_event(
            "ep_rt_shadow_capture",
            f"{run_date}: {join['caught_by_rt']}/{join['residual_total']} residual crossers had a "
            f"same-day ep_rt_universe_catch"
            + (f" — MISSING: {', '.join(join['missing'])}" if join["missing"] else ""),
            json.dumps({"run_date": run_date, **join}))
        if join["missing"]:
            # In shadow this is an RT-2 gate-1 miss to explain; post-flip (RT-4) it is the
            # regression alarm — the overlay leaked a catchable name. Audit-only here; the
            # existing 🔴 residual Telegram in run_delayed_residual_scan already surfaces
            # miss days loudly (digest-only surfacing per the 7/21 noise ruling).
            from agents.market_intelligence.db import get_runtime_toggle
            if await get_runtime_toggle("ep_rt_universe_authoritative",
                                        "EP_RT_UNIVERSE_AUTHORITATIVE", default=False):
                await log_audit_event(
                    "ep_rt_postcutover_residual_regression",
                    f"{run_date}: {len(join['missing'])} residual crosser(s) with NO rt catch under "
                    f"AUTHORITATIVE overlay — the overlay is leaking: {', '.join(join['missing'])}",
                    json.dumps({"run_date": run_date, "missing": join["missing"]}))


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
        from agents.market_intelligence.broker.live_tracker import process_new_alerts_live  # exec-boundary-ok: moves-with-job (W2)
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
        from agents.market_intelligence.broker.trade_stream import get_stream_status  # exec-boundary-ok: moves-with-job (W2)
        status = get_stream_status()
        if status["healthy"] and status["task_alive"]:
            logger.debug("Stream healthy, skipping polling fill check")
            return
    except ImportError:
        pass  # trade_stream not available — always poll

    logger.warning("Stream unhealthy, running fallback fill check")
    try:
        from agents.market_intelligence.broker.order_manager import check_fills  # exec-boundary-ok: moves-with-job (W2)
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
        from agents.market_intelligence.broker.trade_stream import get_stream_status, start_trade_stream  # exec-boundary-ok: moves-with-job (W2)
        status = get_stream_status()
        if not status["task_alive"]:
            logger.warning("Stream watchdog: task not alive, restarting")
            await send_telegram_message("⚠️ Trade stream died, restarting...")
            asyncio.create_task(start_trade_stream())
    except Exception as e:
        logger.error(f"Stream watchdog error: {e}")


async def _post_close_stop_refresh_job():
    """Run at 4:20 PM ET. Put a GTC stop on every open position for the next session.

    ⚖ Operator 2026-08-04: *"do we have a stop always during market hours"* — until
    this job the answer was no for the first five minutes of every session. The entry
    bracket's stop leg is DAY and dies at the 16:00 close; the morning refresh only
    re-placed it at 09:35. Placing it now means the position arrives at the open
    already protected. Slotted at 16:20 — after eod_cleanup (16:05) and the order
    reconcile (16:15), so the expired leg is already known dead.
    """
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    try:
        from agents.market_intelligence.broker.live_tracker import post_close_stop_refresh  # exec-boundary-ok: moves-with-job (W2)
        count = await post_close_stop_refresh()
        logger.info(f"Post-close stop refresh: {count} stops placed")
    except Exception as e:
        logger.error(f"Post-close stop refresh failed: {e}")
        await notify_job_failure("post_close_stop_refresh", str(e))


async def _morning_stop_refresh_job():
    """Run at 9:35 AM ET. Refresh stop orders for Day 2+ positions."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    try:
        from agents.market_intelligence.broker.live_tracker import morning_stop_refresh  # exec-boundary-ok: moves-with-job (W2)
        count = await morning_stop_refresh()
        logger.info(f"Morning stop refresh: {count} stops refreshed")
    except Exception as e:
        logger.error(f"Morning stop refresh failed: {e}")
        await notify_job_failure("morning_stop_refresh", str(e))


async def _position_coverage_check_job():
    """Run every ~15 min, 09:31-15:55 ET (#527 DoD's stated window). #527 market-hours
    coverage DETECTOR — reads BROKER truth for every LIVE open position and confirms a
    live sell-stop covers it. DETECTOR ONLY: never places/cancels/repairs an order
    (`_ensure_stop_coverage` owns repair). Silent on a normally-covered book; Telegrams
    + writes `position_unprotected` on a real gap, deduped to once per trade per
    session. See `order_manager.check_position_coverage` for the full contract.

    ⚠ The cron slot below (`hour="9-15", minute="*/15"`) follows `track_position_extremes`'s
    REGISTRATION idiom, but fires wider than 09:31-15:55 — at 9:00/9:15 a Day-2+
    position genuinely EXISTS in mi_live_trades (unlike track_position_extremes, whose
    early fires ARE no-ops for lack of intraday bar data). The guard below enforces the
    DoD's stated window explicitly rather than relying on the cron slot alone (advisor
    review, #527) — so a 9:00/9:15 tick no-ops here, in code, not by accident of what
    data happens to exist yet.
    """
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    now_et = datetime.now(_ET)
    if not (
        (now_et.hour == 9 and now_et.minute >= 31)
        or (10 <= now_et.hour <= 14)
        or (now_et.hour == 15 and now_et.minute <= 55)
    ):
        return
    try:
        from agents.market_intelligence.broker.order_manager import (  # exec-boundary-ok: moves-with-job (W2)
            check_position_coverage,
        )
        result = await check_position_coverage()
        if result["gaps"] or result["check_failed"]:
            logger.warning(
                f"position_coverage_check: examined {result['examined']}, "
                f"gaps {len(result['gaps'])}, check_failed {len(result['check_failed'])}"
            )
    except Exception as e:
        logger.error(f"Position coverage check failed: {e}")
        await notify_job_failure("position_coverage_check", str(e))


async def _premarket_gap_risk_job():
    """Run at 9:00 AM ET (pre-market). Heads-up if an open position is trading BELOW its
    stop pre-market (may gap THROUGH at the open). Read-only telemetry, no order action —
    ADR 0023 Card 5. NOT gated on LIVE_TRADING_ENABLED (the heads-up is useful even when
    submits are paused; it reads positions, never trades)."""
    try:
        from agents.market_intelligence.briefing import premarket_gap_risk_scan
        n = await premarket_gap_risk_scan()
        logger.info(f"Premarket gap-risk scan: {n} at-risk position(s) alerted")
    except Exception as e:
        logger.error(f"Premarket gap-risk scan failed: {e}")
        await notify_job_failure("premarket_gap_risk", str(e))


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


async def _partial_exit_scan_job():
    """Run at 3:45 PM ET (DURING market hours). Day 3-5 partial-profit exits.

    #361 (2026-06-23): the partial-profit decision was SPLIT OUT of the 4:45 PM
    `_live_position_update_job` into this dedicated market-hours trigger. WHY:
    the 4:45 job fires AFTER the 16:00 ET close, so a partial's stop-replace
    parked in `pending_replace` until the next session open — both old+new stops
    reserved the shares (qty_available=0) and the partial aborted. At 3:45, the
    stop-replace settles in ~0.2s and the sell fills. The partial decision LOGIC
    is unchanged (single source of truth in apply_daily_exit_step); only the
    trigger time moved. Execution-side job (partials touch the broker) →
    registered in EXECUTION_OWNED_JOB_IDS. Guards mirror _live_position_update_job
    exactly (LIVE_TRADING_ENABLED gate, try/except + notify_job_failure, the
    moves-with-job import pattern).
    """
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    logger.info("Partial-exit scan starting (3:45 PM market-hours)...")
    try:
        from agents.market_intelligence.broker.live_tracker import (  # exec-boundary-ok: moves-with-job (W2)
            run_partial_exits,
        )
        results = await run_partial_exits()
        logger.info(f"Partial-exit scan complete: {len(results)} positions scanned")
    except Exception as e:
        import traceback
        logger.error(f"Partial-exit scan failed: {e}\n{traceback.format_exc()}")
        await notify_job_failure("partial_exit_scan", str(e))


async def _live_position_update_job():
    """Run at 4:45 PM ET (EOD, on the close). SMA10/20 trail + stop updates for
    live positions + daily summary.

    #361 (2026-06-23): partials NO LONGER run here — the Day 3-5 partial-profit
    decision was split into `_partial_exit_scan_job` (3:45 PM, market-hours) so
    the partial's stop-replace settles intraday instead of parking in
    `pending_replace` after the close. This job keeps ONLY the SMA-trail +
    stop-update + daily-summary (which correctly run on the settled close), and
    passes skip_partial_decision=True into update_open_positions_live so the
    partial can never double-fire here.
    """
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    logger.info("Live position update starting...")
    try:
        from agents.market_intelligence.broker.live_tracker import (  # exec-boundary-ok: moves-with-job (W2)
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
        from agents.market_intelligence.broker.order_manager import cancel_unfilled_entries, expire_stale_proposals, sync_positions  # exec-boundary-ok: moves-with-job (W2)
        cancelled = await cancel_unfilled_entries()
        expired = await expire_stale_proposals()   # #436 — dead staged proposals, no broker calls
        discrepancies = await sync_positions()
        logger.info(f"EOD cleanup: {cancelled} cancelled, {expired} proposal(s) expired, "
                    f"{len(discrepancies)} discrepancies")
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
        from agents.market_intelligence.broker.drawdown_breaker import (  # exec-boundary-ok: moves-with-job (W2)
            snapshot_account_equity, recompute_drawdown_state,
        )
        # Dual-account #66: snapshot + recompute per mode. Each mode has its
        # own equity, peak, drawdown state — paper drift doesn't trip the
        # live breaker and vice versa.
        for mode in active_account_modes():
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


async def _kill_scale_band_job():
    """Run at 4:13 PM ET — right after the 16:12 equity snapshot + drawdown recompute, when
    the band inputs (cohort R, equity, drawdown tier) are freshest. Evaluate the SIGNED
    live-money kill/scale bands (#268b/#275) and Telegram on a band TRANSITION only (deduped
    via mi_safeguard_state — mirrors the drawdown-tier alert). DB-sourced + fully error-wrapped
    inside run_band_evaluation, so a band-eval hiccup can never break the EOD chain. Pre-launch
    (no live closed trades) it HOLDs below the sample floor and stays silent."""
    from agents.market_intelligence.kill_scale_bands import run_band_evaluation
    await run_band_evaluation("live", send=True)


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
                f"{row['ticker']} #{row['id']} %",
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

        # ── stop_processing sibling (money-path audit 2026-07-12 R5) ─────────
        # 'filling' had this watchdog; 'stop_processing' (the stop-fill claim in
        # trade_stream) had NONE — a crash inside _process_stop_fill strands the
        # row invisibly. No claim-timestamp column exists, so two sightings:
        # first sighting writes a marker audit row; still stuck on a sighting
        # >2 min after the marker → alert (legitimate processing lasts seconds).
        stuck_sp = await conn.fetch(
            "SELECT id, ticker, account_mode FROM mi_live_trades WHERE status = 'stop_processing'"
        )
        for row in stuck_sp:
            marker = await conn.fetchval(
                "SELECT created_at FROM mi_audit_log "
                "WHERE event_type='stop_processing_seen' AND summary LIKE $1 "
                "ORDER BY created_at DESC LIMIT 1",
                f"{row['ticker']} #{row['id']} %",
            )
            age = None if marker is None else await conn.fetchval(
                "SELECT NOW() - $1::timestamptz", marker
            )
            # A marker >10 min old belongs to a PREVIOUS stop_processing episode
            # (a Day-1 re-entry trade can enter this state twice in one day:
            # stop → re-entry → second stop). Treat it as absent — else episode
            # 2's FIRST sighting would false-alert instantly off episode 1's
            # marker. Genuine stuck-ness re-alerts within 2-10 min regardless.
            if marker is None or (age is not None and age.total_seconds() > 600):
                await log_audit_event(
                    "stop_processing_seen",
                    f"{row['ticker']} #{row['id']} ({row['account_mode']}): first sighting",
                )
                continue
            if age is None or age.total_seconds() < 120:
                continue
            already = await conn.fetchval(
                "SELECT 1 FROM mi_audit_log WHERE event_type='stuck_stop_processing_detected' "
                "AND summary LIKE $1 AND created_at > NOW() - INTERVAL '1 day' LIMIT 1",
                f"{row['ticker']} #{row['id']} %",
            )
            if already:
                continue
            await log_audit_event(
                "stuck_stop_processing_detected",
                f"{row['ticker']} #{row['id']} ({row['account_mode']}): "
                f"status='stop_processing' across two watchdog sightings >2 min apart — "
                f"stop-fill handler likely threw",
            )
            await send_telegram_message(
                f"{mode_prefix(row['account_mode'])}🚨 *STUCK STOP-PROCESSING:* {row['ticker']}\n"
                f"Trade #{row['id']} stuck in status='stop_processing' >2 min.\n"
                f"Stop-fill handler likely threw — verify the position/stop state on Alpaca."
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
    from agents.market_intelligence.broker import alpaca_client as alpaca  # exec-boundary-ok: moves-with-job (W2)
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
                    ticker, account_mode=account_mode, raise_on_error=True,
                )
            except Exception as get_err:
                # DEFER on an unreadable broker (#456, operator-ruled 2026-07-26).
                # This branch became reachable in the same card's F16 sweep
                # (raise_on_error=True above; get_open_orders' own [] fallback
                # used to swallow the failure internally). It previously fell
                # through with existing=[] and placed a stop BLIND — which
                # defeats the very check it sits inside: the broker query exists
                # because a REDUNDANT stop is rejected with `insufficient qty
                # available`, i.e. the BW #119 false CRITICAL of 2026-05-27
                # (see the #128 comment above). Acting on an unreadable broker
                # re-creates exactly that bug.
                # Now matches the sibling policy (_try_adopt_existing_stop's
                # _BROKER_UNREADABLE sentinel, _ensure_stop_coverage's early
                # return None): skip this trade, retry next cycle. Cheap — this
                # job runs every 30s during market hours — and a genuinely naked
                # position is independently covered by _ensure_stop_coverage and
                # the 15-min order-status reconcile.
                # The audit event_type is deliberately NOT one of the three the
                # dedup above matches, so deferring does NOT burn the
                # once-per-day remediation attempt; its own 1-hour dedup keeps a
                # sustained outage from flooding the log at 2 rows/minute.
                logger.warning(
                    f"stop_ack_watchdog: get_open_orders({ticker}) failed: "
                    f"{get_err} — DEFERRING to next cycle (fail-safe)"
                )
                recently_logged = await conn.fetchval(
                    "SELECT 1 FROM mi_audit_log "
                    "WHERE event_type = 'stop_ack_broker_unreadable' "
                    "AND summary LIKE $1 "
                    "AND created_at > NOW() - INTERVAL '1 hour' LIMIT 1",
                    f"{ticker} #{trade_id}%",
                )
                if not recently_logged:
                    await log_audit_event(
                        "stop_ack_broker_unreadable",
                        f"{ticker} #{trade_id}: broker unreadable "
                        f"({get_err}) — deferred, retrying next cycle",
                        detail=_json.dumps({
                            "trade_id": trade_id,
                            "ticker": ticker,
                            "account_mode": account_mode,
                            "error": str(get_err),
                        }),
                    )
                continue
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
                    from agents.market_intelligence.broker.order_manager import (  # exec-boundary-ok: moves-with-job (W2)
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
                from agents.market_intelligence.broker.order_manager import set_stop_order_id  # exec-boundary-ok: moves-with-job (W2)
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

    #306 (2026-07-25): subsumed into the Alpaca-sourced intraday path recorder
    — same job id, same cron slot. Fetches real-time Alpaca minute bars per
    ticker with an open-OR-closed-today position (the #310-class fix that
    captures fast trades' final minutes), upserts the full path into
    mi_intraday_bars, then updates each trade's lowest_price_seen /
    highest_price_seen via monotonic LEAST/GREATEST over the in-hold window
    only. Feeds setup-quality analytics (does this setup let trades run high
    before exit, or drag toward stop?) AND the offline intraday
    partial-profit sweep. Full contract — the two correctness clamps, the
    #310-class selection predicate, the time-stop provenance note — lives on
    order_manager.track_open_position_extremes's docstring; don't duplicate
    it here, keep it in sync if either changes.
    """
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    try:
        from agents.market_intelligence.broker.order_manager import (  # exec-boundary-ok: moves-with-job (W2)
            track_open_position_extremes,
        )
        n = await track_open_position_extremes()
        if n:
            logger.info(f"track_position_extremes: updated {n} open trade rows")

        # #508 — profit trigger runs IMMEDIATELY AFTER, on the bars the recorder
        # just persisted. Deliberately a separate function (not a branch inside
        # the recorder, which is name-registered in the column-write authority
        # gate) and deliberately sequential (not its own cron) so it can never
        # read a poll's bars before they land. OFF unless PROFIT_TRIGGER_R is set.
        from agents.market_intelligence.broker.order_manager import (  # exec-boundary-ok: moves-with-job (W2)
            scan_profit_triggers,
        )
        fired = await scan_profit_triggers()
        if fired:
            logger.info(f"profit trigger: {fired}")
    except Exception as e:
        logger.error(f"track_position_extremes failed: {e}")


async def _position_path_eod_sweep_job():
    """Run once at 16:10 ET, mon-fri (#306, 2026-07-25).

    The last `*/5` poll of `_track_open_position_extremes_job` fires at
    15:55, so bars 15:55-16:00 and any position closed in that window need
    one final pass. Also heals restart-day `mi_intraday_bars` coverage holes
    for open multi-day positions (`sweep=True` — see
    order_manager.track_open_position_extremes / _sweep_multi_day_coverage).
    DB-write only (log_audit_event on a persistent gap, never Telegram) —
    scheduled off :00-:05 so it stays clear of the EOD digest chain, and
    before the 16:15 post-EOD audit.
    """
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    try:
        from agents.market_intelligence.broker.order_manager import (  # exec-boundary-ok: moves-with-job (W2)
            track_open_position_extremes,
        )
        n = await track_open_position_extremes(sweep=True)
        if n:
            logger.info(f"position_path_eod_sweep: updated {n} trade rows")
    except Exception as e:
        logger.error(f"position_path_eod_sweep failed: {e}")


async def _evening_position_backstop_job():
    """Run at 9:00 PM ET. Backstop sync_positions catching late EXPIRED events
    or earlier remediation failures — market closed, no other jobs running, so
    a fresh orphan scan + retry costs nothing and closes the gap before next day's open."""
    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        return
    logger.info("Evening position backstop starting...")
    try:
        from agents.market_intelligence.broker.order_manager import sync_positions  # exec-boundary-ok: moves-with-job (W2)
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
    from agents.market_intelligence.broker.shadow_orb_tracker import run_shadow_pass  # exec-boundary-ok: moves-with-job (W2)
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
    from agents.market_intelligence.broker.shadow_orb_tracker import update_shadow_positions  # exec-boundary-ok: moves-with-job (W2)
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
        from agents.market_intelligence.broker.order_manager import cancel_unfilled_entries, expire_stale_proposals  # exec-boundary-ok: moves-with-job (W2)
        cancelled = await cancel_unfilled_entries(reason="ORB window unfilled")
        expired = await expire_stale_proposals()   # #436 — dead staged proposals, no broker calls
        logger.info(f"ORB window cleanup: {cancelled} cancelled, {expired} proposal(s) expired")
    except Exception as e:
        logger.error(f"ORB window cleanup failed: {e}")
        await notify_job_failure("orb_window_cleanup", str(e))


async def _rt_miss_digest_job():
    """Run at 10:00 AM ET. ONE morning digest of the residual real-time EP misses the watchdog recorded
    audit-only during the 9:31-9:44 ORB window (operator 7/21 — replaces the per-ticker Telegram blast).
    Intelligence-side, read-only (mi_audit_log + Telegram); no broker calls, no LIVE gate (observability)."""
    from agents.market_intelligence.ep_detector import send_rt_miss_digest
    n = await send_rt_miss_digest()
    logger.info(f"rt_miss_digest_job: {n} residual real-time miss(es) summarized")


async def _eod_ep_recap_job():
    """Run at 4:10 PM ET. One-shot summary of today's HIGH EP outcomes.
    #479: no longer Telegrams directly — the render text goes to
    close_digest.contribute("EP", ...) and lands in the 16:55 Market Close
    Digest. Detection, DB reads, and logs unchanged.

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
        from agents.market_intelligence.execution_client import get_data_feed_name
        today = et_today()
        today_str = str(today)
        outcomes = await get_ep_outcomes(days_back=1, tier="HIGH")
        today_outcomes = [o for o in outcomes if str(o.get("alert_date")) == today_str]

        feed_tel = await get_sip_feed_telemetry(today)
        feed = get_data_feed_name()
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

        # Judge demotes (operator request 2026-06-10, judge load-bearing same
        # day): "No HIGH EPs" is ambiguous — none detected, or floor-HIGHs
        # demoted away? Count floor-HIGH demotes explicitly (always shown, so
        # 0 is an answer, not silence). Per-delta detail stays in the 16:25
        # judge digest; this is the headline count.
        pool = await get_pool()
        async with pool.acquire() as conn:
            _demoted = await conn.fetch("""
                SELECT ticker, score_tier FROM mi_ep_alerts
                WHERE alert_date = $1 AND judge_direction = 'demote'
                  AND baseline_floor_tier = 'HIGH'
                  AND COALESCE(source, 'live') = 'live'
            """, today)
        if _demoted:
            _dt = ", ".join(
                f"`{r['ticker']}`→{r['score_tier'] or '?'}" for r in _demoted[:6])
            judge_line = f"⚖️ Judge demoted {len(_demoted)} floor-HIGH: {_dt}"
        else:
            judge_line = "⚖️ Judge demoted 0 floor-HIGHs"

        # Vol-profile Slice 1 (V4, docs/analysis/volume_profile_alert_context_2026-07-27.md):
        # alert-day volume landmark, EOD truth — rendered HERE and not on the alert because
        # 128/196 alerts fire pre-9:45 where "on pace for #1" is premarket noise. All tiers
        # (the ~23% fire rate was measured all-tier). Display + telemetry only (THE LINE);
        # the pass never raises — [] on any failure (audited inside).
        from agents.market_intelligence.vol_profile import eod_vol_landmark_pass
        landmark_lines = await eod_vol_landmark_pass(today)
        landmark_block = ""
        if landmark_lines:
            landmark_block = ("📊 Vol landmark" + ("s" if len(landmark_lines) > 1 else "")
                              + ":\n" + "\n".join(f"  • {l}" for l in landmark_lines))

        if not today_outcomes:
            # Still report feed health — the silent-feed case is exactly why this exists.
            if feed_alert or feed_tel["bars_fetched"] > 0 or _demoted or landmark_lines:
                prefix = "⚠️ " if feed_alert else ""
                # #479: folded into the 16:55 Market Close Digest (same render text).
                close_digest.contribute(
                    "EP",
                    f"{prefix}*EP EOD Recap — {today_str}*\n"
                    f"No HIGH EPs today.\n{judge_line}\n"
                    + (landmark_block + "\n" if landmark_block else "")
                    + feed_line
                )
            logger.info("EOD EP recap: no HIGH EPs today")
            return

        entered_states = {"filled", "closed", "order_placed", "pending_confirmation", "confirmed", "submitting"}
        entered = [o for o in today_outcomes if o.get("pt_status") in entered_states]
        missed = [o for o in today_outcomes if o not in entered]

        lines = [
            f"📊 *EP EOD Recap — {today_str}*",
            f"HIGH: {len(today_outcomes)} detected → {len(entered)} entered · {len(missed)} missed",
            judge_line,
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

        if landmark_block:
            lines.append(landmark_block)
        lines.append(feed_line)
        if feed_alert:
            lines.insert(0, "⚠️ *Feed health flagged — see 📡 line below*")

        # #479: folded into the 16:55 Market Close Digest (same render text).
        close_digest.contribute("EP", "\n".join(lines))
        logger.info("EOD EP recap contributed to close digest")
    except Exception as e:
        logger.error(f"EOD EP recap failed: {e}")
        await notify_job_failure("eod_ep_recap", str(e))


async def _orb_reclassify_eod_job():
    """Run at 4:25 PM ET (#183). Re-classify today's cancelled ORB entries on
    COMPLETE bars over the canonical 9:31–10:00 window, correcting the intraday
    classifier's lag-corrupted `clean_miss` labels (AVAV-class). Audit-only —
    writes `orb_cancellation_reclassified`; no trade-state mutation, no
    retroactive Telegram (#123 discipline). Bars from the morning ORB window are
    long settled by now."""
    from agents.market_intelligence.broker.gap_through_telemetry import (  # exec-boundary-ok: moves-with-job (W2)
        reclassify_orb_cancellations_eod,
    )
    from agents.market_intelligence.collector import et_today
    res = await reclassify_orb_cancellations_eod(et_today())
    logger.info(f"ORB reclassify EOD: {res['summary']}; {len(res['flips'])} flip(s)")


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

    Slots between 5:15 parabolic_scan and 5:25 flag_scan. Fast aggregation
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


async def _intraday_signals_eod_digest_job():
    """16:00 ET — ONE consolidated digest of the day's 5 intraday entry-technique
    shadow detectors (#168 noise fix, 2026-06-07). Replaces the ~23/day per-tick
    pings (now default-off) with a single roll-up; reads the persisted tables, so
    detection + telemetry are untouched. Suppressed entirely on zero-fire days."""
    now_et = datetime.now(_ET)
    if not get_market_status(now_et.date()).is_trading_day:
        logger.info("intraday signals digest: non-trading day — skip")
        return 0
    from agents.market_intelligence.flag_detector import run_intraday_signals_eod_digest
    n = await run_intraday_signals_eod_digest(now_et.date())
    logger.info(f"intraday signals EOD digest: {n} signals surfaced")
    return int(n) if n is not None else 0


async def _low_vol_rest_scan_job():
    """Run every 5 min during market hours. Intraday low-volume-rest detector
    (#97, entry-technique #4). A quiet tight coil INSIDE the base on dried-up
    volume (no test/bounce — the calm is the signal). Telemetry-only shadow
    phase; N>=10 settled before paper.
    """
    now_et = datetime.now(_ET)
    if not (_dt_time(9, 35) <= now_et.time() <= _dt_time(15, 55)):
        return 0
    try:
        from agents.market_intelligence.flag_detector import run_intraday_low_vol_rest_scan
        n = await run_intraday_low_vol_rest_scan(now_et)
        return int(n) if n is not None else 0
    except Exception as e:
        logger.error(f"intraday_low_vol_rest_scan failed: {e}", exc_info=True)
        await notify_job_failure(JOB_LOW_VOL_REST_SCAN, str(e))
        return None


async def _undercut_rally_scan_job():
    """Run every 5 min during market hours. Intraday U&R (Undercut & Rally)
    detector (#98, entry-technique #5, Morales/OWL, 2026-05-31 ship).

    A shallow stop-run BELOW base_low (deeper than the support-test ≤2% band)
    that then reclaims back above it. NO volume gate (Morales). Telemetry-only
    shadow phase; N>=10 settled before paper.
    """
    now_et = datetime.now(_ET)
    if not (_dt_time(9, 35) <= now_et.time() <= _dt_time(15, 55)):
        return 0
    try:
        from agents.market_intelligence.flag_detector import run_intraday_undercut_rally_scan
        n = await run_intraday_undercut_rally_scan(now_et)
        return int(n) if n is not None else 0
    except Exception as e:
        logger.error(f"intraday_undercut_rally_scan failed: {e}", exc_info=True)
        await notify_job_failure(JOB_UNDERCUT_RALLY_SCAN, str(e))
        return None


# Telegram formatting helpers (`_md_escape`, `_humanize_downgrade_reason`, the
# `_DOWNGRADE_REASON_*` maps, and `_build_judge_delta_message`) were re-homed to
# briefing.py (#121, 2026-06-23) — a scheduler shouldn't own message formatting.
# Imported lazily at the call sites below to avoid pulling briefing at module load.


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
    from agents.market_intelligence.briefing import (
        _md_escape, _humanize_downgrade_reason,
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
        # #321 self-verify: today's LIVE YoY-recoveries (a wrongly-downgraded name rescued by the
        # prior-year comparable). Surfaced here so the operator SEES the fix firing, not infers from silence.
        rescued = await conn.fetch(
            """
            SELECT summary FROM mi_audit_log
            WHERE event_type = 'catalyst_yoy_recovered_live'
              AND (created_at AT TIME ZONE 'America/New_York')::date = $1
            ORDER BY created_at ASC
            """,
            now_et.date(),
        )
        if not rows and not rescued:
            return 0
        # Defer to the load-bearing judge (#249): a catalyst the FLOOR downgraded but the JUDGE
        # promoted to an authoritative HIGH should not read as a bare downgrade contradicting the
        # HIGH alert 20 min earlier (LZB 6/17). Annotate those lines so the digest is coherent
        # with the alert rather than fighting it. (Only queried when there ARE downgrades.)
        judge_rows = await conn.fetch(
            "SELECT ticker, score_tier, grade_engine_authority FROM mi_ep_alerts WHERE alert_date = $1",
            now_et.date(),
        )
    judge_map = {jr["ticker"]: jr for jr in judge_rows}

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
        ticker = summary.split(":", 1)[0].strip()
        jr = judge_map.get(ticker)
        judge_promoted = bool(jr and jr["grade_engine_authority"] == "judge"
                              and jr["score_tier"] == "HIGH")
        inner = summary.split("(earnings catalyst, ", 1)
        if len(inner) == 2:
            head = inner[0].rstrip(" (")
            reason_raw = inner[1].rstrip(")")
            reason_human = _humanize_downgrade_reason(reason_raw)
            line = f"• {_md_escape(head)} — {_md_escape(reason_human)}"
        else:
            line = f"• {_md_escape(summary)}"
        if judge_promoted:
            line += "  _(↑ judge promoted to HIGH — authoritative)_"
        lines.append(line)
    if rescued:
        _rtix = ", ".join(_md_escape((rs["summary"] or "").split(":", 1)[0].strip()) for rs in rescued)
        lines.append("")
        lines.append(f"🟢 *{len(rescued)} rescued* — wrongly downgraded for a missing YoY, prior-year recovered (#321): {_rtix}")
    lines.append("")
    lines.append("_Drilldown: `/rubric TICKER` for full breakdown._")
    try:
        await send_telegram_message("\n".join(lines))
    except Exception as e:
        logger.error(f"catalyst_downgrade_digest Telegram failed: {e}")
    return len(rows)


async def _9m_pace_digest_job():
    """End-of-day rollup of 9M EP pace (anticipation) alerts (#133; EOD
    consolidation 2026-06-07).

    Pace alerts are projection-based — "on track to hit 9M by close" — not
    realtime-actionable (they were ~89% of pinged 9M volume). Moved from 3×
    hourly (10/11/12 ET) to ONE 16:00 ET roll-up of the whole trading day,
    matching the entry-technique EOD digest (#168). Actual 9M crossings still
    ride the prompt per-tick digest in ninem_detector.

    Dedup: skip tickers that ALSO fired as actual today (already pinged
    realtime). Ranked by projected volume, capped with overflow. Empty day →
    no Telegram.
    """
    now_et = datetime.now(_ET)
    if not get_market_status(now_et.date()).is_trading_day:
        # Mirror the entry-technique digest sibling + #120 precedent: don't query
        # or fire on weekday market holidays (mon-fri cron alone doesn't exclude them).
        logger.info("9m pace digest: non-trading day — skip")
        return 0
    pool = await get_pool()
    window_start = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = now_et

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

    ranked_all = sorted(
        seen.values(),
        key=lambda r: (r["projected_vol"] or 0),
        reverse=True,
    )
    ranked = ranked_all[:20]

    date_str = now_et.strftime("%b %d")
    parts = [
        f"🏦 *9M EP Pace — EOD {date_str} ({len(ranked_all)})*",
        "_Projection-based anticipations · watchlist, not entries._",
    ]
    for r in ranked:
        proj_m = (r["projected_vol"] or 0) / 1_000_000
        parts.append(
            f"• `{r['ticker']}` ~{proj_m:.1f}M proj "
            f"${r['current_price']:.2f} +{(r['gap_pct'] or 0):.1f}%"
        )
    if len(ranked_all) > 20:
        parts.append(f"…+{len(ranked_all) - 20} more")
    # #479: folded into the 16:55 Market Close Digest (same render text).
    # Detection-layer pace only, non-empty days only (empty returns above) —
    # the deprecated 9M Day 2 STRATEGY gets no line anywhere (operator 7/17).
    close_digest.contribute("9M", "\n".join(parts))
    return len(ranked)


async def _position_mgmt_judge_job():
    """ADR 0014 / #300 P3 — the 16:00-class daily SHADOW management-judge pass over open live
    positions. ZERO execution authority: one bounded verdict (HOLD/PARTIAL_TAKE/TRAIL_TIGHTEN/
    FORCE_EXIT) + rationale per position, persisted to mi_position_mgmt_decisions + a digest line,
    accruing the agree/disagree-with-mechanical evidence the load-bearing P3 will need (graduation
    = post-launch + own evidence + CHANGE_PROCESS + sign-off). DB-sourced ground truth; current
    price from a LIVE snapshot (never mi_daily_closes — the part-1 QURE stale-close artifact);
    per-position fail-open. Skips non-trading days."""
    now_et = datetime.now(_ET)
    if not get_market_status(now_et.date()).is_trading_day:
        logger.info("position mgmt judge: non-trading day — skip")
        return 0
    from agents.market_intelligence.mgmt_judge import run_position_mgmt_judge
    await run_position_mgmt_judge(send=True)
    return 1


async def _judge_delta_digest_job():
    """EOD push of the EP Holistic Grade Judge's bidirectional deltas (#240 / W3,
    2026-06-09). The judge_delta_review.py / unjustified_demotion_sweep.py surfaces
    are PULL (operator runs them); this is the PUSH complement — once a day, the names
    the judge moved UP or DOWN vs the conviction floor land in Telegram so the
    judgment-correctness review doesn't depend on remembering to run a script.

    DB-sourced (feedback_scheduler_aggregators_db_sourced): reads today's judged rows
    straight from mi_ep_alerts — never module state. Empty day → no Telegram (the judge
    is shadow until the W2 flip + most days have 0 deltas; build-ahead-of-data). The
    subtitle reflects the LIVE authority toggle so the operator always knows whether the
    deltas DROVE entries (toggle ON) or are advisory (OFF)."""
    now_et = datetime.now(_ET)
    if not get_market_status(now_et.date()).is_trading_day:
        logger.info("judge delta digest: non-trading day — skip")
        return 0
    from agents.market_intelligence.db import get_holistic_judge_enabled
    from agents.market_intelligence.briefing import _build_judge_delta_message
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, baseline_floor_tier, judge_tier, judge_direction,
                   judge_materiality_tier, gap_pct, judge_rationale
            FROM mi_ep_alerts
            WHERE alert_date = $1
              AND judge_tier IS NOT NULL
              AND judge_direction IN ('promote', 'demote')
            ORDER BY CASE judge_direction WHEN 'promote' THEN 0 ELSE 1 END,
                     gap_pct DESC NULLS LAST
            """,
            now_et.date(),
        )
    if not rows:
        return 0

    authority_on = False
    try:
        authority_on = await get_holistic_judge_enabled()
    except Exception:  # loud-ok: display-only; default to the safe "advisory" framing, no state change
        pass

    msg = _build_judge_delta_message(rows, authority_on, now_et.strftime("%b %d"))
    # #479: folded into the 16:55 Market Close Digest (same render text).
    close_digest.contribute("JUDGE", msg)
    return len(rows)


async def _close_digest_job():
    """16:55 ET — flush the Market Close Digest (#479 half-1, operator-ruled).

    Assembles the ONE post-close message from the contribution buffer the
    16:00–16:45 folded jobs filled (intraday_signals 16:00 · eod_ep_recap
    16:10 · 9m_pace 16:20 · judge_delta 16:25 · news_quality_drift 16:30 ·
    live_position_update 16:45), sends it, clears the buffer, writes one
    market_close_digest_sent audit row. Empty buffer (quiet day / holiday —
    every contributor already gates on trading days) → nothing is sent.
    Observability only; real-time alerts are untouched.
    """
    return await close_digest.flush_and_send()


async def _order_status_reconcile_job(lookback_days: int = 90, run_coverage_drift: bool = True):
    """Periodic DB↔Alpaca order-status reconciliation (#123, 2026-05-26).

    Catches silent stops (Apollo never sees the trade_update stream event)
    and stuck PENDING_NEW/new/accepted orders that diverge from Alpaca's
    authoritative state. Runs every 15 min during market hours +
    one-shot on container boot.

    Audit-only — no Telegram (advisor 2026-05-26: retroactive 'stop fired
    hours ago' alerts are operationally confusing; operator drills via
    `/audit order_status_reconciled`).

    #184 ADR 0008 increment 2 (2026-07-05): right after the order-status
    reconcile, runs the READ-ONLY DB↔broker coverage-drift detector
    (positions + open orders vs mi_live_trades) for each active account
    mode — same 15-min cadence, consolidated onto this existing job rather
    than a new one (per the consolidate-surfaces rule). Coverage-drift is
    strictly observe-only (audit rows + Telegram; no mutation) but still
    runs under its own per-mode try/except — an exception there must never
    break this reconcile job (loud: logged + audited, never silently
    swallowed). `run_coverage_drift=False` on the #150 1-minute open-window
    variant below.
    """
    try:
        from agents.market_intelligence.broker.order_manager import reconcile_all_modes  # exec-boundary-ok: moves-with-job (W2)
        result = await reconcile_all_modes(lookback_days=lookback_days)
        if result.get("updated", 0) > 0 or result.get("errors", 0) > 0:
            logger.info(
                f"order_status_reconcile: examined={result['examined']} "
                f"updated={result['updated']} errors={result['errors']}"
            )

        if run_coverage_drift:
            from agents.market_intelligence.broker.coverage_drift import detect_coverage_drift  # exec-boundary-ok: moves-with-job (W2)
            for mode in active_account_modes():
                try:
                    await detect_coverage_drift(mode)
                except Exception as e:
                    from agents.market_intelligence.audit_events import COVERAGE_DRIFT_CHECK_FAILED
                    logger.exception(f"coverage_drift_check[{mode}] failed: {e}")
                    await log_audit_event(
                        COVERAGE_DRIFT_CHECK_FAILED,
                        f"coverage-drift check crashed for {mode}: {e}",
                        f"account_mode={mode}",
                    )

            # #455 R4 stage-1 (2026-07-16): ALERT-ONLY intraday drawdown-crossing
            # check on the LIVE book — piggybacked on this 15-min cycle per the
            # consolidate-surfaces rule (the 16:12 EOD breaker still owns ALL
            # state/sizing; this only closes the intraday VISIBILITY gap). Gated
            # on run_coverage_drift like coverage-drift so the #150 1-minute
            # open-window variant doesn't add ~10 get_account calls each morning.
            # run_intraday_drawdown_check never raises by contract; wrapped
            # anyway — a failure here must never break the reconcile cycle.
            try:
                from agents.market_intelligence.broker.intraday_drawdown import run_intraday_drawdown_check  # exec-boundary-ok: moves-with-job (W2)
                await run_intraday_drawdown_check()
            except Exception as e:
                logger.exception(f"intraday_drawdown_check failed: {e}")

        return result.get("updated", 0)
    except Exception as e:
        logger.error(f"order_status_reconcile_job failed: {e}", exc_info=True)
        await notify_job_failure(JOB_ORDER_STATUS_RECONCILE, str(e))
        return None


async def _order_status_reconcile_job_open():
    """#150 open-window variant — 1-day lookback only. The 9:31-9:40 every-minute
    cadence exists to time TODAY's pending_new->new transition; a 90-day sweep would
    re-poll every stale non-terminal order ~10x/morning for nothing (/simplify
    efficiency finding 2026-06-02).

    run_coverage_drift=False (#184): the 15-min job above already runs the
    coverage-drift check on its own cadence — running it 10x every morning on
    this tight timing-only cadence would be redundant noise on top of that.
    """
    return await _order_status_reconcile_job(lookback_days=1, run_coverage_drift=False)


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

    Slots between 5:22 sugar_babies cohort refresh and 5:30 post_nightly_audit. Persists
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


async def _source_gap_finder_job():
    """Sun 08:45 ET — weekly gap-discovery pass (#235 Wave E / #211). Asks
    where the week's unsourced real movers WERE reported; surfaces a
    source-onboarding queue to the operator. Bounded ≤8 Perplexity calls,
    audit-deduped per (ticker, alert_date). Telemetry only."""
    from agents.market_intelligence.source_gap_finder import run_source_gap_finder
    res = await run_source_gap_finder(days=7)
    logger.info(
        f"source gap finder: {res['n_cohort']} unknowns → "
        f"{res['n_found']} findings"
    )
    return res["n_found"]


async def _theme_synthesis_job():
    """6:05 PM ET — cross-ticker emerging-theme synthesis (#240 advisory feed).
    Top-down LLM pass over the coordinated-RS-slope candidates (velocity +
    turners): propose 0-3 emerging cross-sector narrative cohorts, mechanically
    validated, written to mi_theme_candidates_shadow (source='rs_slope_synthesis')
    where the operator reviews them and the judge's narrative axis reads them.
    Augment-not-automate: never writes live mi_themes."""
    now_et = datetime.now(_ET)
    if not get_market_status(now_et.date()).is_trading_day:
        logger.info("theme synthesis: non-trading day — skip")
        return 0
    from agents.market_intelligence.theme_synthesis import run_theme_synthesis
    res = await run_theme_synthesis(now_et.date())
    logger.info(
        f"theme synthesis: {res['n_candidates']} candidates → "
        f"{res['n_proposed']} proposed → {res['n_kept']} kept"
    )
    return res["n_kept"]


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

    # Systematic anti-silent-failure NULL-RATE sweep (#370, operator 6/24): a normally-populated
    # column that silently goes null (the spy_vs_200ma-for-3-weeks class) → ONE grouped Telegram.
    # Own try/except so a sweep failure can't break the audit; the sweep is internally robust too.
    try:
        from agents.market_intelligence.health_checks import run_null_rate_sweep
        sweep = await run_null_rate_sweep()
        logger.info(
            f"Null-rate sweep: {sweep['tables_scanned']} tables, "
            f"{len(sweep['flags'])} flag(s), {len(sweep['errors'])} error(s)")
    except Exception as e:
        logger.error(f"Null-rate sweep failed: {e}", exc_info=True)
        await notify_job_failure("null_rate_sweep", str(e))

    # Row-count DRIFT sweep (#340): a hand-pinned `expected_min_rows` rots silently — when the real
    # distribution steps down legitimately the job sits `empty_result` forever and the red light
    # stops meaning anything (#286: nightly_data_pull red EVERY market day for 2+ weeks). Flags a
    # >25% drop vs the trailing median AND pins that have gone stale. Own try/except — a health
    # guard that dies silently is the failure it exists to prevent.
    try:
        from agents.market_intelligence.health_checks import run_row_count_drift_sweep
        drift = await run_row_count_drift_sweep()
        logger.info(
            f"Row-count drift sweep: {drift['jobs_scanned']} jobs, "
            f"{len(drift['drops'])} drop(s), {len(drift['stale_floors'])} stale floor(s), "
            f"{len(drift['errors'])} error(s)")
    except Exception as e:
        logger.error(f"Row-count drift sweep failed: {e}", exc_info=True)
        await notify_job_failure("row_count_drift_sweep", str(e))

    # Job-liveness sweep (#370 increment 3): a scheduled job that RAN successfully but produced
    # NOTHING (theme synthesis truncating to 0 cohorts; theme-shadow 0 rows #173) — reads each output
    # table's real new-row count, NOT the lying self-report. Own try/except; internally robust.
    # #521 INERT-SWEEP CHECK (2026-08-03): a study that varies a parameter must produce variation.
    # `mi_orb_extension_shadow` swept six cutoffs for 91 days and every one returned an identical
    # result for every trade — a one-word bug (fill threshold read the STOP, not the LIMIT) that
    # nobody could see until the review's N>=20 threshold tripped. Operator: "disappointing to have
    # bad data for months, need to prevent this going forward." Own try/except — a health guard that
    # dies silently is the failure it exists to prevent.
    try:
        from agents.market_intelligence.health_checks import run_inert_sweep_check
        inert = await run_inert_sweep_check()
        logger.info(
            f"Inert-sweep check: {inert['lanes_scanned']} lane(s), "
            f"{len(inert['inert'])} inert, {len(inert['skipped'])} skipped, "
            f"{len(inert['errors'])} error(s)")
        # ANNOUNCE ONCE PER LANE, not nightly. The condition persists until someone recomputes the
        # stored rows, so an un-deduped alert would repeat every night about a defect already known
        # and already filed — which is how a real signal becomes wallpaper. Same idiom as the
        # new-lane detector and the 7/17 budget-alarm re-fire fix: the audit log IS the state.
        _already = set()
        try:
            from agents.market_intelligence.db import get_pool as _pool_for_dedupe
            _p = await _pool_for_dedupe()
            async with _p.acquire() as _c:
                _already = {r["t"] for r in await _c.fetch(
                    "SELECT DISTINCT split_part(summary, ':', 1) AS t FROM mi_audit_log "
                    "WHERE event_type = 'inert_sweep_detected'")}
        except Exception as e:  # loud-ok: logged, and failing OPEN here only risks a duplicate alert, never a missed one
            logger.warning(f"inert-sweep dedupe read failed (will re-announce): {e}")
        fresh = [l for l in inert["inert"] if l["table"] not in _already]
        for lane in fresh:
            await log_audit_event(
                "inert_sweep_detected", f"{lane['table']}: {lane['swept']} sweep is measuring nothing",
                json.dumps(lane))
        inert["inert"] = fresh
        if inert["inert"]:
            # NO function-local import here: `send_telegram_message` is bound at MODULE level, and a
            # local `from ... import` would make the name local to this whole function — the
            # 2026-05-20 UnboundLocalError outage class, caught by preflight [import-shadowing].
            lines = ["🔴 *SWEEP IS MEASURING NOTHING* — a study that varies a setting produced",
                     "identical results across every variant, so the setting is not reaching the code:",
                     "```"]
            for lane in inert["inert"][:3]:
                lines.append(f"{lane['table']}  ({lane['multi_variant_subjects']} subjects, 0 varied)")
            lines.append("```")
            await send_telegram_message("\n".join(lines))
    except Exception as e:  # loud-ok: logger.error + notify_job_failure — a health guard that dies silently is the failure it exists to prevent
        logger.error(f"Inert-sweep check failed: {e}", exc_info=True)
        await notify_job_failure("inert_sweep_check", str(e))

    # THEME QUALITY check (#531, operator 2026-08-04: "quality checks regularly to make sure our
    # themes are solid without me needing to check it and review manually"). Two signatures,
    # measured against 97 days of real prod mi_themes before shipping: (A) a theme retired while
    # its last-known state was healthy (the #368/F2 regression guard) and (B) a member pruned
    # while its RS was rising (the #368/F3 regression guard). Dedupe + Telegram + audit rows all
    # happen inside run_theme_quality_check (mirrors the null/job-liveness sweeps' internal
    # persistence, same idiom as run_inert_sweep_check's dedupe: mi_audit_log IS the state, no new
    # table, fails OPEN). Own try/except — a health guard that dies silently is the failure it
    # exists to prevent.
    try:
        from agents.market_intelligence.health_checks import run_theme_quality_check
        tq = await run_theme_quality_check()
        logger.info(
            f"Theme quality check: {len(tq['retired_while_healthy'])} retirement flag(s), "
            f"{len(tq['pruned_while_rising'])} prune flag(s), {len(tq['errors'])} error(s)")
    except Exception as e:
        logger.error(f"Theme quality check failed: {e}", exc_info=True)
        await notify_job_failure("theme_quality_check", str(e))

    # ECOSYSTEM REACTIVATION detector (#534 D3(b), 2026-08-05 — design §5b of
    # docs/analysis/534_theme_universe_expansion_2026-08-05.md): a DORMANT ecosystem (no live
    # theme / all-Fading at the alert window's start) collecting >=3 distinct HIGH EP tickers
    # within 5 sessions against a quiet 15-session baseline — the deterministic $0 aggregation
    # of the wake-up that prod expressed on 08-04 as five duplicate defense births nobody
    # aggregated. Thresholds derived from a 66-session replay (health_checks.py #534 header).
    # Output: operator line + a discovery seed (source='ecosystem_reactivation', allowlist-
    # excluded from auto-promote — the birth gate owns promotion; NEVER births a theme itself).
    # Runs HERE (17:30 ET) deliberately: after the 17:00 theme engine, so tonight's board and
    # its ecosystem mappings exist when the detector reads them. Dedupe/audit/Telegram live
    # inside run_ecosystem_reactivation_check (mi_audit_log IS the state, fails OPEN). Own
    # try/except — a health guard that dies silently is the failure it exists to prevent.
    try:
        from agents.market_intelligence.health_checks import run_ecosystem_reactivation_check
        er = await run_ecosystem_reactivation_check()
        logger.info(
            f"Ecosystem reactivation check: {len(er['flags'])} firing(s), "
            f"{len(er['skipped'])} skipped, {len(er['errors'])} error(s) "
            f"over {er['sessions_used']} sessions")
    except Exception as e:
        logger.error(f"Ecosystem reactivation check failed: {e}", exc_info=True)
        await notify_job_failure("ecosystem_reactivation_check", str(e))

    try:
        from agents.market_intelligence.health_checks import run_job_liveness_sweep
        jl = await run_job_liveness_sweep()
        logger.info(
            f"Job-liveness sweep: {jl['jobs_checked']} jobs, "
            f"{len(jl['flags'])} flag(s), {len(jl['errors'])} error(s)")
    except Exception as e:
        logger.error(f"Job-liveness sweep failed: {e}", exc_info=True)
        await notify_job_failure("job_liveness_sweep", str(e))

    # Data-gated-review escalation (#54 RMV-miss mitigation, Prong B). A review that's been
    # READY — or whose predicate has been ERRORING (a silently-broken locked query, the exact
    # #54 class) — beyond the grace window gets its OWN deterministic Telegram instead of rotting
    # in the LLM-narrated Sunday digest. DB-sourced + deduped via mi_review_escalation_state.
    try:
        from agents.market_intelligence.data_gated_reviews import escalate_overdue_reviews
        from agents.market_intelligence.briefing import _md_escape
        escalations = await escalate_overdue_reviews()
        if escalations:
            # send_telegram_message (module line 46) + log_audit_event (line 27) are module-level;
            # a function-local re-import here shadows them (the gate-5d / 2026-05-20 UnboundLocalError
            # anti-pattern, #295). Legacy-Markdown-safe: review_ids / blocked_by / titles are underscore-heavy and
            # desync Telegram's parser — escape the free-text fields via the canonical _md_escape
            # (#148; re-homed to briefing.py #121) and drop inline backticks. Ints (age/count/threshold) need no escape.
            lines = ["⏰ *Overdue data-gated reviews* (ready/erroring past grace — run it or update the entry):"]
            for esc in escalations:
                if esc["kind"] == "ready":
                    lines.append(
                        f"  • {_md_escape(esc['review_id'])} READY {esc['age_days']}d "
                        f"(count {esc.get('current_count')}≥{esc.get('threshold')}) — {_md_escape(esc.get('title'))}"
                    )
                else:
                    lines.append(
                        f"  • {_md_escape(esc['review_id'])} predicate ERRORING {esc['age_days']}d "
                        f"(likely broken: {_md_escape(esc.get('blocked_by'))}) — {_md_escape(esc.get('title'))}"
                    )
            lines.append("/datareviews for the full board.")
            await send_telegram_message("\n".join(lines))
            for esc in escalations:
                await log_audit_event(
                    "review_escalation",
                    f"{esc['review_id']} {esc['kind']} {esc['age_days']}d",
                    detail=esc.get("title") or "",
                )
    except Exception as e:
        logger.error(f"Review escalation failed: {e}", exc_info=True)


async def _feed_anticipation_sip(*, ticker, gap_day, state, entry_tactic=None,
                               entry_price=None, stop_price=None,
                               base_run=None, rmv_5d=None) -> None:
    """Fail-open: mirror a anticipation ready/triggered row into mi_stocks_in_play so
    /watch surfaces it alongside every other detector (ADR 0004; /sip stays the
    drill-down). SHADOW → operator_only — never apollo_eligible (only that class
    auto-routes, and nothing reads this table for routing anyway: it is display-only).
    A failed write NEVER breaks the lifecycle jobs (ADR 0004 §11 fail-open-everywhere)."""
    try:
        from agents.market_intelligence import anticipation as de
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.db import upsert_stocks_in_play
        from agents.market_intelligence.stocks_in_play_sources import (
            SOURCE_ANTICIPATION_REENTRY, CLASS_OPERATOR_ONLY,
        )
        reason, signal = de.sip_payload(
            state=state, gap_day_iso=gap_day.isoformat(), entry_tactic=entry_tactic,
            entry_price=entry_price, stop_price=stop_price,
            base_run=base_run, rmv_5d=rmv_5d)
        # ~5 trading sessions ≈ 7 calendar days (ADR 0004 §3 flag-stage TTL).
        expires_at = datetime.combine(et_today() + timedelta(days=7),
                                      _dt_time(23, 59), tzinfo=_ET)
        await upsert_stocks_in_play(
            ticker=ticker, source_detector=SOURCE_ANTICIPATION_REENTRY,
            automation_class=CLASS_OPERATOR_ONLY, reason=reason,
            readiness_signal=signal, source_phase="shadow", expires_at=expires_at)
    except Exception as e:
        logger.error(f"anticipation SiP feed {ticker}/{gap_day}: {e}", exc_info=True)


async def _anticipation_readiness_job():
    """#270 Step 3 SHADOW — derive the anticipation re-entry lifecycle nightly + alert ARMED
    transitions. 17:35 ET, after the 17:00 nightly_data_pull refreshes mi_daily_closes.

    DB-sourced ground truth only (no module state — containers restart): seed gap candidates
    from mi_daily_closes, CONFIRM + derive each via the pure anticipation.evaluate_candidate over
    full bars, settle a triggered anticipation entry once its forward window completes, UPSERT,
    and Telegram the watched→armed TRANSITIONS (deduped via the prior-state map — only rows that
    crossed into armed+ this run). SHADOW: observes + alerts, never submits.
    """
    from datetime import date as _date
    from agents.market_intelligence import anticipation as de
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.db import (
        get_anticipation_gap_seeds, get_anticipation_ohlcv, get_anticipation_state_map,
        upsert_anticipation_lifecycle,
    )
    _MINUTE_TACTICS = ("first5_break", "gdl_reclaim")
    try:
        today = et_today()
        seeds = await get_anticipation_gap_seeds(today)
        state_map = await get_anticipation_state_map()
        keys = {(s["ticker"], s["gap_day"]) for s in seeds}
        keys |= {k for k, v in state_map.items()
                 if v["state"] != "expired" and not v["settled"]}

        written, transitions = 0, []
        for ticker, gap_day in sorted(keys):
            prior = state_map.get((ticker, gap_day))
            if prior and prior.get("entry_tactic") in _MINUTE_TACTICS:
                continue  # 3b/execution owns a minute-tactic entry — never clobber it
            try:
                bars = de.db_rows_to_bars(await get_anticipation_ohlcv(ticker, today))
                if len(bars) < 30:
                    continue
                row = de.evaluate_candidate(bars, gap_day.isoformat())
                if row is None:
                    continue  # replay didn't confirm the coarse seed as a WATCHED gap
                realized_r = fwd_mfe = None
                settled = False
                if row["state"] == "triggered" and row.get("_entry_idx") is not None:
                    days_since = (today - _date.fromisoformat(row["triggered_date"])).days
                    st = de.settle_row(
                        entry_tactic="anticipation", entry_price=row["entry_price"],
                        stop_price=row["stop_price"], bars=bars,
                        entry_idx=row["_entry_idx"], days_since_trigger=days_since)
                    if st:
                        realized_r, fwd_mfe, settled = st["realized_r"], st["fwd_mfe_pct"], st["settled"]
                await upsert_anticipation_lifecycle(
                    ticker, gap_day, state=row["state"], gap_day_low=row["gap_day_low"],
                    gap_day_vol=row["gap_day_vol"], sma200_at_gap=row["sma200_at_gap"],
                    armed_date=row["armed_date"], coiled_date=row["coiled_date"],
                    ready_date=row["ready_date"], triggered_date=row["triggered_date"],
                    entry_tactic=row["entry_tactic"], entry_price=row["entry_price"],
                    stop_price=row["stop_price"], reenter_count=row["reenter_count"],
                    base_run=row["base_run"], rmv_5d=row["rmv_5d"], rmv_15d=row["rmv_15d"],
                    tight_close_pct=row["tight_close_pct"], fwd_mfe_pct=fwd_mfe,
                    realized_r=realized_r, settled=settled, last_eval=today,
                    pullback_shape=row.get("pullback_shape"),
                    pullback_shapes=row.get("pullback_shapes"),
                    armed_shape=row.get("armed_shape"),
                    fresh_tightening=row.get("fresh_tightening"),
                    fresh_2bar_tr_pct=row.get("fresh_2bar_tr_pct"),
                    atr14_pct=row.get("atr14_pct"),
                    tight_close_streak=row.get("tight_close_streak"))
                written += 1
                if row["state"] in ("ready", "triggered"):
                    await _feed_anticipation_sip(
                        ticker=ticker, gap_day=gap_day, state=row["state"],
                        entry_tactic=row["entry_tactic"], entry_price=row["entry_price"],
                        stop_price=row["stop_price"], base_run=row["base_run"],
                        rmv_5d=row["rmv_5d"])
                prior_state = prior["state"] if prior else None
                if (prior_state in (None, "watched")
                        and row["state"] in ("armed", "coiled", "ready", "triggered")):
                    transitions.append((ticker, gap_day, row["state"]))
            except Exception as e:
                logger.error(f"anticipation readiness {ticker}/{gap_day}: {e}", exc_info=True)

        logger.info(f"anticipation readiness: {written} rows, {len(transitions)} armed transitions")
        if transitions:
            lines = ["⏱️ *Anticipation (SHADOW) — newly ARMED* "
                     "(gap-low undercut → watch for the reclaim):"]
            for ticker, gap_day, st in transitions[:12]:
                lines.append(f"  • {ticker} gap {gap_day.isoformat()} → {st}")
            lines.append("/anticipation for the full lifecycle board.")
            await send_telegram_message("\n".join(lines))
    except Exception as e:
        logger.error(f"anticipation readiness job failed: {e}", exc_info=True)


async def _anticipation_3b_job():
    """#270 Step 3 SHADOW — 3b FIRST5/gdl intraday-confirmation watch + fill-sim. 16:20 ET.

    INTELLIGENCE-role (a considered deviation from the plan's 'execution'): a SHADOW EOD pass
    needs only Polygon REST minute bars via collector.get_minute_bars, NOT execution's live
    stream — so it runs creds-LESS, which makes structural-shadow STRUCTURAL BY SERVICE (no
    submit path exists in intelligence at all), strictly safer than an import guard inside the
    creds-bearing service. Imports only db + collector(data) + briefing + the pure anticipation.

    (A) DETECT: for each watch-set name (armed/ready/coiled), fetch today's RTH minute bars and
        run FIRST5-break (primary) / GDL-reclaim (fallback); record a 'triggered' first5/gdl
        entry + alert. (B) FILL-SIM: for first5/gdl entries whose forward window has completed,
        harvest realized_r over the FAITHFUL day-0-minute + daily path and settle. No submit.
    """
    from agents.market_intelligence import anticipation as de
    from agents.market_intelligence.collector import et_today, get_minute_bars
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.db import (
        get_anticipation_watch_set, record_anticipation_3b_entry,
        get_anticipation_3b_unsettled, settle_anticipation_3b, get_anticipation_ohlcv,
    )
    try:
        today = et_today()
        today_iso = today.isoformat()

        # (A) DETECT today's intraday FIRST5/gdl breaks among the watch set
        fired = []
        for w in await get_anticipation_watch_set():
            try:
                gdl = w.get("gap_day_low")
                if gdl is None:
                    continue
                mb = de.polygon_to_rth_minutes(
                    await get_minute_bars(w["ticker"], today_iso, today_iso), today_iso)
                if len(mb) < 6:
                    continue
                det, tactic = de.detect_first5_break(mb, float(gdl)), "first5_break"
                if det is None:
                    det, tactic = de.detect_gdl_reclaim(mb, float(gdl)), "gdl_reclaim"
                if det is None:
                    continue
                entry, stop, _idx = det
                if await record_anticipation_3b_entry(
                        w["ticker"], w["gap_day"], entry_tactic=tactic,
                        entry_price=entry, stop_price=stop, triggered_date=today):
                    fired.append((w["ticker"], w["gap_day"], tactic, entry, stop))
                    await _feed_anticipation_sip(
                        ticker=w["ticker"], gap_day=w["gap_day"], state="triggered",
                        entry_tactic=tactic, entry_price=entry, stop_price=stop)
            except Exception as e:
                logger.error(f"anticipation 3b detect {w['ticker']}: {e}", exc_info=True)

        # (B) FILL-SIM: settle first5/gdl entries whose forward window has completed
        settled_n = 0
        for r in await get_anticipation_3b_unsettled():
            try:
                tdate = r["triggered_date"]
                if tdate is None or r.get("gap_day_low") is None:
                    continue
                daily = de.db_rows_to_bars(await get_anticipation_ohlcv(r["ticker"], today))
                fwd = [b for b in daily if b["date"] > tdate.isoformat()]
                if len(fwd) < de.SETTLE_FORWARD_BARS:
                    continue   # forward window not complete → re-eval a later run
                mb = de.polygon_to_rth_minutes(
                    await get_minute_bars(r["ticker"], tdate.isoformat(), tdate.isoformat()),
                    tdate.isoformat())
                det = (de.detect_first5_break(mb, float(r["gap_day_low"]))
                       if r["entry_tactic"] == "first5_break"
                       else de.detect_gdl_reclaim(mb, float(r["gap_day_low"])))
                if det is None:
                    continue
                entry, stop, bidx = det
                sim = de.simulate_first5(entry, stop, mb, bidx, fwd[:de.SETTLE_FORWARD_BARS])
                if sim is None:
                    continue
                await settle_anticipation_3b(
                    r["ticker"], r["gap_day"], realized_r=sim["realized_r"],
                    fwd_mfe_pct=sim["fwd_mfe_pct"], day0_fills=sim["fills"])
                settled_n += 1
            except Exception as e:
                logger.error(f"anticipation 3b fillsim {r['ticker']}: {e}", exc_info=True)

        logger.info(f"anticipation 3b: {len(fired)} new entries, {settled_n} settled")
        if fired:
            lines = ["🎯 *Anticipation (SHADOW) — 3b intraday entry fired* (FIRST5/gdl break, derisk fast):"]
            for tk, gd, tac, e, s in fired[:12]:
                lines.append(f"  • {tk} gap {gd.isoformat()} "
                             f"{'first5' if tac == 'first5_break' else 'gdl'} "
                             f"entry {e:.2f} stop {s:.2f}")
            lines.append("/anticipation for the board.")
            await send_telegram_message("\n".join(lines))
    except Exception as e:
        logger.error(f"anticipation 3b job failed: {e}", exc_info=True)


# ── #327 readiness-scan robustness bounds (blocker fix, operator-signed 2026-07-14) ──────────
# The 7/13 Monday run HUNG >2h inside the SCAN section and was watchdog-killed, so the INLINE
# settlement (DB-fast) never ran → 170 rows stuck past-ripe. Suspect: the #387 M&A guard's Polygon
# calls under sustained rate-limiting — _polygon_get is firm PER CALL (30s httpx timeout, ≤3
# attempts, 429 backoff 15/30/45s → worst ~3 min/call) but UNBOUNDED cumulatively across coil
# candidates. Two bounds, both fail-OPEN (SHADOW-only — a partial scan is safe: the open-dedup pins
# re-fires, upserted rows stand, tomorrow's run re-scans the full universe):
_CONS_SCAN_BUDGET_S = 900        # per-run time budget for the SCAN section ONLY (15 min);
                                 # the settlement runs AFTER, unconditionally
_CONS_MNA_CHECKS_CAP = 40        # max Polygon-backed M&A checks per run (defense in depth under
                                 # the budget; overflow candidates pass UNchecked + one audit row)


async def _consolidation_readiness_job():
    """FAMILY A — "consolidation plays post a runup" (ADR 0013, signed §2) SHADOW RECORDER +
    the #327 forward-shadow settlement, ONE job → ONE daily digest (operator 6/18). 17:35 ET
    mon-fri, after the 17:00 nightly_data_pull refreshes mi_daily_closes. SHADOW: records +
    settles telemetry, never submits.

    STRUCTURE (#327 blocker fix, operator-signed 2026-07-14): the SCAN section
    (_consolidation_readiness_scan — universe → coil-finder → M&A guard → entry-watch → upsert)
    runs under asyncio.wait_for(_CONS_SCAN_BUDGET_S) and FAILS OPEN on timeout (log + a
    consolidation_readiness_scan_timeout audit event, partial results kept); the SETTLEMENT
    (_run_entry_shadow_settlement) then runs UNCONDITIONALLY — on 7/13 a >2h scan hang starved it
    and 170 ripe rows sat unsettled until the watchdog kill. The settlement is idempotent
    (abstains on short bars, retries next run), so settling after a partial scan is safe."""
    from agents.market_intelligence import anticipation as de
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.audit_events import CONSOLIDATION_READINESS_SCAN_TIMEOUT
    from agents.market_intelligence.db import get_open_shadow_tickers
    try:
        today = et_today()
        # Accumulators are passed INTO the scan so a budget timeout keeps the PARTIAL results —
        # rows already upserted / entry-shadows already fired before the cancel still reach the
        # digest instead of vanishing with the cancelled coroutine.
        stats = {"universe": 0, "written": 0}
        transitions, entries_fired = [], []
        scan_timed_out = False
        try:
            await asyncio.wait_for(
                _consolidation_readiness_scan(today, stats, transitions, entries_fired),
                timeout=_CONS_SCAN_BUDGET_S)
        except asyncio.TimeoutError:
            # FAIL-OPEN (#327 blocker fix): a hung/slow scan must never take the settlement down
            # with it. SHADOW-only, so a partial scan loses nothing durable — the open-dedup pins
            # re-fires and tomorrow's run re-scans the full universe.
            scan_timed_out = True
            logger.error(
                f"consolidation readiness SCAN timed out after {_CONS_SCAN_BUDGET_S}s — fail-open: "
                f"partial scan kept ({stats['written']} rows written, {len(entries_fired)} entry "
                f"fires, {len(transitions)} transitions); settlement proceeds")
            try:
                await log_audit_event(
                    CONSOLIDATION_READINESS_SCAN_TIMEOUT,
                    f"scan exceeded its {_CONS_SCAN_BUDGET_S}s budget — kept partial results "
                    f"({stats['written']} rows, {len(entries_fired)} fires); settlement still ran",
                    detail=str({"budget_s": _CONS_SCAN_BUDGET_S, **stats})[:500],
                )
            except Exception as _ae:   # the audit write must not block the settlement either
                logger.error(f"scan-timeout audit write failed: {_ae}")

        # ── #327 forward-shadow SETTLEMENT — ALWAYS runs, scan outcome irrespective (the 7/13
        #    lesson: 170 rows stuck past-ripe because the scan hung first). Folded in so the WHOLE
        #    Family-A lifecycle is ONE job → ONE daily digest (operator 6/18 — consolidate, don't
        #    add surfaces; no cross-job ordering). ──
        just_settled = await _run_entry_shadow_settlement(today)
        # #356 Phase 3 — HTF breakout-shadow settlement folded into the SAME daily Family-A job (NOT a
        # new surface). Never submits; the settled count is surfaced in the digest below so the operator
        # SEES it firing (advisor: don't infer a live shadow from silence).
        try:
            htf_settled = await _htf_breakout_settle_job(today)
        except Exception as _he:   # loud-ok: shadow settlement, must not break the Family-A digest job
            logger.warning(f"htf_breakout_settle folded-call failed (non-critical): {_he}")
            htf_settled = []

        logger.info(f"consolidation readiness: {stats['universe']} universe, {stats['written']} rows, "
                    f"{len(transitions)} newly coiled, {len(entries_fired)} entries fired, "
                    f"{len(just_settled)} settled"
                    + (" [SCAN TIMED OUT — partial]" if scan_timed_out else ""))

        digest = []
        if scan_timed_out:
            digest.append(f"⚠️ Readiness SCAN hit its {_CONS_SCAN_BUDGET_S // 60}-min budget — "
                          f"partial board today ({stats['written']} evaluated); settlement ran in full.")
            digest.append("")
        if just_settled:
            cap = sum(1 for _, s in just_settled if s["outcome"] == "capture")
            digest.append(f"📐 *Settled today* ({len(just_settled)} · {cap} capture)")
            for ticker, s in just_settled[:12]:
                digest.append(de.format_entry_settled_row(ticker, s["outcome"], s["realized_r"]))
            digest.append("")
        if htf_settled:
            hcap = sum(1 for _, s in htf_settled if s["outcome"] == "capture")
            digest.append(f"🚩 *HTF breakouts settled* ({len(htf_settled)} · {hcap} capture) — SHADOW (#356)")
            digest.append("")
        # Both Family-A entry modes surface, SEPARATELY tagged (#327 shadow-fix §3 — never blended):
        ant_fired = [x for x in entries_fired if x[2] == "anticipate"]
        conf_fired = [x for x in entries_fired if x[2] == "confirm"]
        if ant_fired:
            digest.append(f"🎯 *Anticipate entry fired today* ({len(ant_fired)}) — in-coil (N≥{de.ENTRY_TIGHT_N} tight days at apex)")
            for ticker, origin, _m, sig in ant_fired[:12]:
                digest.append(de.format_entry_fired_row(ticker, sig["entry_price"],
                                                        sig["stop_price"], origin))
            digest.append("")
        if conf_fired:
            digest.append(f"✅ *Confirm entry fired today* ({len(conf_fired)}) — base-high breakout + volume (control arm, SHADOW)")
            for ticker, origin, _m, sig in conf_fired[:12]:
                digest.append(de.format_entry_fired_row(ticker, sig["entry_price"],
                                                        sig["stop_price"], origin))
            digest.append("")
        # a name with ANY open entry-shadow (today's OR a prior day's) has graduated past "newly
        # coiled" — show it once. Use the UNCAPPED open set so a prior-day fire still suppresses it
        # (else the lifecycle runs backward in the feed; altitude review 6/18).
        graduated = await get_open_shadow_tickers()
        newly_coiled = [x for x in transitions if x[0] not in graduated]
        # #479 (2026-07-17): the newly-coiled roster is a lifecycle telemetry
        # tail (a name entering "coiling" isn't actionable) — record the count
        # but keep the full roster on /anticipation, off the push.
        coiled_count = len(newly_coiled)
        # #479: push this SHADOW board only on a NOTABLE night — an entry fired
        # (ant/conf), a shadow SETTLED (the graduation-relevant events the
        # operator watches), or a scan-timeout WARNING (actionable — something
        # went wrong). Coiling-only nights → /anticipation on demand, no push
        # (a shadow board isn't a terminal/actionable event — house rule).
        notable = bool(scan_timed_out or just_settled or htf_settled
                       or ant_fired or conf_fired)
        if notable:
            if coiled_count:
                digest.append(f"🪙 +{coiled_count} newly coiling (`/anticipation`)")
            head = ["🪙 *Anticipation plays* (Family A · SHADOW) — today", ""]
            digest.append("/anticipation for the full board.")
            await send_telegram_message("\n".join(head + digest))
        elif coiled_count:
            logger.info(f"anticipation: coiling-only night ({coiled_count} newly "
                        f"coiled, no fires/settles) — Telegram suppressed (#479)")
    except Exception as e:
        logger.error(f"consolidation readiness job failed: {e}", exc_info=True)


async def _entry_shadow_fire_kwargs(ticker, sig, bars, *, mode, non_stock, regime_label, today):
    """Build insert_consolidation_entry_shadow kwargs for ONE #327 entry-shadow fire (anticipate
    OR confirm), applying the operator-signed 2026-07-14 shadow-fix pack. RECORDS readings + flags
    only — NEVER filters the write (A/B doctrine: both would-pass and would-fail cohorts accrue).

      §1 quality flag: stocks-only (mi_security_types complement; unknown type = pass, the
         codebase convention) + above-50SMA + RS≥65 + dollar-ADV≥$5M, via the pure
         anticipation.quality_readings / would_pass_quality_flag; raw components recorded so any
         floor can be re-cut offline (the diagnostic's ETF magnitude was unverified — flag only).
      §2 stop geometry (anticipate): structural_low becomes the HEADLINE stop
         (stop_kind/stop_price — what settlement settles); the validated fire-bar low keeps
         accruing in coiled_low so the legacy bet stays re-derivable. sub1pct_reject flags a
         sub-1% coiled_low risk (min observed 0.06% — noise stops that poison R math). Confirm
         fires keep base_low (its structural stop already) and flag on that same geometry.
      §4 regime_at_entry: the mi_market_regime label as-of the run (fetched once by the scan).

    The single RS lookup is this helper's only I/O; everything else is pure reads on `bars`."""
    from agents.market_intelligence import anticipation as de
    from agents.market_intelligence.db import get_rs_for_tickers
    q = de.quality_readings(bars, len(bars) - 1)
    rs_row = (await get_rs_for_tickers(today, [ticker])).get(ticker) or {}
    rs = rs_row.get("rs_composite")
    is_cs = ticker not in non_stock
    entry = sig["entry_price"]
    if mode == "anticipate":
        stop_kind, stop_price = "structural_low", sig["structural_low"]
        coiled_low = sig["stop_price"]           # the fire-bar low — recorded for continuity
    else:                                        # confirm: stop = base_low (already structural)
        stop_kind, stop_price = sig["stop_kind"], sig["stop_price"]
        coiled_low = None
    tightest_pct = de.stop_pct_of_entry(entry, coiled_low if coiled_low is not None else stop_price)
    return dict(
        entry_date=sig["entry_date"], entry_price=entry,
        stop_kind=stop_kind, stop_price=stop_price, structural_low=sig["structural_low"],
        signal_n=sig["signal_n"], rmv_5d=sig["rmv_5d"], rmv_15d=sig.get("rmv_15d"),
        range_pct=sig["range_pct"], vol_ratio=sig["vol_ratio"],
        vol_sma_3=sig.get("vol_sma_3"), vol_sma_15=sig.get("vol_sma_15"),
        vol_dryup_ratio=sig.get("vol_dryup_ratio"), target_r=sig["target_r"], entry_mode=mode,
        coiled_low=coiled_low,
        stop_pct=de.stop_pct_of_entry(entry, stop_price),
        sub1pct_reject=(tightest_pct is not None and tightest_pct < de.STOP_FLOOR_MIN_PCT),
        would_pass_quality=de.would_pass_quality_flag(
            is_common_stock=is_cs, above_50sma=q["above_50sma"],
            rs_composite=rs, adv20_dollar=q["adv20_dollar"]),
        is_common_stock=is_cs, above_50sma=q["above_50sma"],
        rs_at_entry=rs, adv20_dollar=q["adv20_dollar"], regime_at_entry=regime_label,
    )


async def _consolidation_readiness_scan(today, stats, transitions, entries_fired):
    """The SCAN section of _consolidation_readiness_job, split out so the caller can bound it with
    asyncio.wait_for(_CONS_SCAN_BUDGET_S) — a hung/slow scan (the 7/13 >2h M&A-guard hang) fails
    open instead of starving the inline settlement. MUTATES the caller's accumulators
    (stats / transitions / entries_fired) so a mid-scan cancel keeps the partial results.
    SHADOW: records the shortlist + tightness telemetry + entry-shadow fires, never submits.

    DB-sourced ground truth only (no module state — containers restart): the universe PROPOSER
    (get_anticipation_universe) pre-filters to the signed §2 set; select_consolidation_keys UNIONS
    it with the existing non-aged rows (CARRY-FORWARD — keeps a base's ORIGINAL key when its
    rolling-window anchor would otherwise drift to a lesser peak); the pure
    anticipation.evaluate_coil_consolidation re-confirms the runup per key (the authoritative gate — the
    COO canary) + records the coil/tightness telemetry; UPSERT keyed on (ticker, anchor_date);
    Telegram (via the caller's digest) the newly-COILED transitions (deduped via the prior-state map).

    UN-PAUSED 2026-06-17 (carry-forward verified by tests/test_anticipation_consolidation.py — the
    7 real 6/15→6/16 drift names carry their original anchor). Registered at 17:35 ET mon-fri.

    #327 FORWARD SHADOW (operator "wire it", 6/18): per key, after the coil evaluation, fire the
    validated entry signal (anticipation.entry_signal_at — N≥ENTRY_TIGHT_N tight days at the
    coil apex) AS OF the latest bar and record one shadow row per OPEN coil
    (insert_consolidation_entry_shadow; open-dedup pins the first fire). SHADOW — no execution.

    #327 shadow-fix pack (operator-signed 2026-07-14 —
    docs/analysis/327_shadow_fix_proposal_2026-07-14.md): every fire is enriched via
    _entry_shadow_fire_kwargs (§1 quality flag RECORDED never gated · §2 structural_low headline
    stop + sub-1% flag · §4 regime_at_entry), and the CONFIRM control arm is RE-WIRED (§3 —
    REVERSES the operator's 6/29 anticipate-only un-wire, per the signed proposal; obsoletes the
    #404 removal task): confirm_signal_at (enter ON the confirmed base_high breakout + volume,
    stop = base_low) records a SEPARATELY-TAGGED entry_mode='confirm' row on the same coil — the
    3-col open-dedup lets both modes coexist; both settle through the same settlement step. The
    diagnostic's key head-to-head: 85% of anticipated coils never broke out; Confirm is
    structurally shielded from paying for false coils — measured forward as the control.

    #387/#410 buyout/M&A GUARDS (operator-filed 2026-06-30, NUVL FP — gapped ~37% to the deal
    price and flatlined; the coil-finder read the post-deal PIN as a tight coil, buy 123.50/stop
    123.43 = 0.06% the giveaway): #410 is a pure price-SHAPE check baked into
    anticipation.evaluate_coil_consolidation (coil_pin_reject_reason — reuses flag_detector's
    proven deal-pin primitive); a reject is re-derived + audited here
    (anticipation_coil_buyout_pin_rejected) since the pure function can't do I/O. #387 re-applies
    the SAME news-backed single-source filter (ma_filter.is_likely_ma) the EP/flag/9M paths use,
    on the surviving coil candidates only (cost control) — a hit excludes + audits
    (anticipation_mna_excluded), now CAPPED at _CONS_MNA_CHECKS_CAP Polygon-backed checks per run
    (#327 blocker fix — the unbounded cumulative Polygon time was the prime hang suspect; overflow
    candidates pass UNchecked, fail-open + anticipation_mna_check_capped audit). Neither guard
    touches the #327 gates themselves (runup / hold / tightness) — additive exclusions only, per
    THE LINE (SHADOW-only, zero execution authority)."""
    from datetime import date, timedelta
    from agents.market_intelligence import anticipation as de
    from agents.market_intelligence.ma_filter import is_likely_ma
    from agents.market_intelligence.audit_events import (
        ANTICIPATION_MNA_EXCLUDED, ANTICIPATION_COIL_BUYOUT_PIN_REJECTED,
        ANTICIPATION_MNA_CHECK_CAPPED,
    )
    from agents.market_intelligence.db import (
        get_anticipation_universe, get_anticipation_ohlcv, get_consolidation_state_map,
        upsert_consolidation, insert_consolidation_entry_shadow, get_recent_9m_tickers,
        get_non_common_stock_tickers, get_latest_regime,
    )
    universe = await get_anticipation_universe(today)
    stats["universe"] = len(universe)
    state_map = await get_consolidation_state_map()
    nine_m = await get_recent_9m_tickers(today - timedelta(days=90))  # #327 origin tag
    # #327 shadow-fix per-run context (fetched ONCE): the regime label stamped on every fire (§4)
    # + the non-CS/ADRC set for the quality flag's stocks-only component (§1; a ticker absent
    # from mi_security_types passes — the codebase's unknown-type convention).
    regime_row = await get_latest_regime()
    regime_label = (regime_row or {}).get("regime")
    non_stock = await get_non_common_stock_tickers()

    # CARRY-FORWARD: union the fresh §2 proposer with existing non-aged rows so a base whose
    # rolling-window anchor drifts (peak aging out) keeps its ORIGINAL key (no duplicate rows).
    existing = {}
    for (tk, anc), v in state_map.items():
        if v["state"] != "aged":
            existing.setdefault(tk, []).append(
                {"anchor_date": anc, "runup_high": v["runup_high"], "dvol_med": v["dvol_med"]})
    keys = de.select_consolidation_keys(universe, existing)

    mna_checks, mna_cap_logged = 0, False
    for k in keys:
        ticker, anchor_date, dvol_med = k["ticker"], k["anchor_date"], k["dvol_med"]
        try:
            bars = de.db_rows_to_bars(await get_anticipation_ohlcv(ticker, today))
            if len(bars) < 60:
                continue
            # #327 LIVE base detection: the COIL-FINDER (runup leg → hold-≤50% → tight) REPLACES
            # the old peak-anchored evaluate_consolidation (which swallowed the post-runup
            # pullback — CRWD read a 24% "base"). It finds the TRUE coil + its peak; the
            # carry-forward key's anchor_date is just the candidate SEED now. A name with no held
            # coil (runup gate / hold-≤50% gate) is simply not a candidate — skip, same as today.
            cons, pin_reason = de.evaluate_coil_consolidation(bars)
            if cons is None:
                # #410 buyout/deal-pin shape guard (NUVL 6/30 FP): evaluate_coil_consolidation
                # now RETURNS the reject reason directly (simplify GROUP 2, 2026-07-03) instead
                # of bare None — no re-derivation (no second find_coil_setup / hold-check /
                # coil_pin_reject_reason call). pin_reason is only set for the #410 pin guard
                # ('stop_floor' | 'gap_to_flat'); a plain non-candidate (no runup→coil, or hold
                # exceeded) leaves it None and is silently skipped, same as before.
                if pin_reason:
                    await log_audit_event(
                        ANTICIPATION_COIL_BUYOUT_PIN_REJECTED,
                        f"{ticker} coil rejected — {pin_reason}",
                        detail=str({"ticker": ticker, "reason": pin_reason})[:500],
                    )
                continue

            # #387 M&A exclusion (operator-filed 6/30 post-NUVL FP): a coil-shaped candidate whose
            # "tight days at the apex" turn out to be the post-acquisition PIN. Re-applies the SAME
            # single-source filter (ma_filter.is_likely_ma) the EP/flag/9M paths use, gated on the
            # coil candidate subset only (cost control). CAPPED per run (#327 blocker fix): past
            # _CONS_MNA_CHECKS_CAP the remaining candidates pass UNCHECKED (fail-open — dropping
            # real candidates to an infra cap would bias the shadow; a rare deal-pin fire is
            # shadow-only noise and the #410 shape guard above still runs). One audit row marks
            # the capped run so a systematic cap-hit is visible, not silent.
            if mna_checks < _CONS_MNA_CHECKS_CAP:
                mna_checks += 1
                is_mna, mna_meta = await is_likely_ma(
                    ticker, check_polygon=True, on_or_before=today, polygon_lookback_days=21,
                )
            else:
                is_mna, mna_meta = False, None
                if not mna_cap_logged:                       # log the cap ONCE per run
                    mna_cap_logged = True
                    await log_audit_event(
                        ANTICIPATION_MNA_CHECK_CAPPED,
                        f"M&A checks capped at {_CONS_MNA_CHECKS_CAP} this run — remaining coil "
                        f"candidates pass unchecked (fail-open, shadow-only)",
                    )
            if is_mna:
                await log_audit_event(
                    ANTICIPATION_MNA_EXCLUDED,
                    f"{ticker} excluded from coil candidacy via "
                    f"{(mna_meta or {}).get('source', 'unknown')} (anchor {cons['anchor_date']})",
                    detail=str({"ticker": ticker, "anchor_date": cons["anchor_date"],
                                **(mna_meta or {})})[:500],
                )
                continue

            anchor_date = date.fromisoformat(cons["anchor_date"])   # the coil peak = the anchor now

            # #327 FORWARD SHADOW: fire the entry signals AS OF the latest bar. SHADOW recorder;
            # the open-dedup pins one row per mode to the first fire day. anchor_idx from the coil
            # peak (guaranteed in-bars). Both modes are recorded into the ONE shadow lifecycle,
            # tagged by entry_mode (#354 ADR 0013 §1 · re-wired dual-mode per the signed 7/14
            # proposal §3): Anticipate = the validated in-coil signal; Confirm = the base-high
            # breakout on the SAME §2 universe (NOT the live #94 path).
            anchor_idx = next((j for j, b in enumerate(bars)
                               if b["date"] == cons["anchor_date"]), None)
            if anchor_idx is not None:
                origin = "9m" if ticker in nine_m else "family_a"
                sig = de.entry_signal_at(bars, len(bars) - 1, anchor_idx)
                if sig:
                    kw = await _entry_shadow_fire_kwargs(
                        ticker, sig, bars, mode="anticipate", non_stock=non_stock,
                        regime_label=regime_label, today=today)
                    if await insert_consolidation_entry_shadow(ticker, anchor_date,
                                                               origin=origin, **kw):
                        # overlay the HEADLINE stop so the digest shows what settlement settles
                        entries_fired.append((ticker, origin, "anticipate",
                                              {**sig, "stop_price": kw["stop_price"]}))
                csig = de.confirm_signal_at(bars, len(bars) - 1, anchor_idx)
                if csig:
                    kw = await _entry_shadow_fire_kwargs(
                        ticker, csig, bars, mode="confirm", non_stock=non_stock,
                        regime_label=regime_label, today=today)
                    if await insert_consolidation_entry_shadow(ticker, anchor_date,
                                                               origin=origin, **kw):
                        entries_fired.append((ticker, origin, "confirm", csig))

            await upsert_consolidation(
                ticker, anchor_date, state=cons["state"], runup_ratio=cons["runup_ratio"],
                runup_high=cons["runup_high"], coil_days=cons["coil_days"],
                last_close=cons["last_close"], today_pct=cons["today_pct"],
                rmv_5d=cons["rmv_5d"], rmv_15d=cons["rmv_15d"],
                pullback_shape=cons["pullback_shape"], pullback_shapes=cons["pullback_shapes"],
                fresh_tightening=cons["fresh_tightening"],
                fresh_2bar_tr_pct=cons["fresh_2bar_tr_pct"], atr14_pct=cons["atr14_pct"],
                tight_close_streak=cons["tight_close_streak"], dvol_med=dvol_med,
                last_eval=today)
            stats["written"] += 1
            prior = state_map.get((ticker, anchor_date))
            prior_state = prior["state"] if prior else None
            if prior_state in (None, "post_runup") and cons["state"] == "coiled":
                transitions.append((ticker, anchor_date, cons))
        except Exception as e:
            logger.error(f"consolidation readiness {ticker}/{anchor_date}: {e}", exc_info=True)


async def _run_entry_shadow_settlement(today):
    """FAMILY A — #327 forward-shadow SETTLEMENT step. Called INLINE by _consolidation_readiness_job
    (so the lifecycle is one job → one digest; operator 6/18 — not a separate scheduled job). For
    each OPEN mi_consolidation_entry_shadow row with ≥ENTRY_SETTLE_WINDOW forward trading bars,
    settle outcome (capture/stop/open) + fwd_mfe_r (the validated bet under coiled_low) + the
    bankable realized_r and write it back — flipping outcome non-NULL also frees the open-dedup.
    Returns the just-settled [(ticker, res), ...] for the caller's unified digest. SHADOW — no exec.

    DB-sourced ground truth (no module state): a coarse entry_date pre-filter bounds the bars-fetch;
    the pure de.settle_entry_shadow re-checks the EXACT forward-bar count and ABSTAINS if short
    (re-tried next run). Logs ripe-considered vs settled so a silent-0 is distinguishable from
    'nothing ripe yet'.

    MODE-AGNOSTIC: anticipate AND confirm rows settle identically off the row's own recorded
    stop_price (headline stop) + target_r — both are close-of-bar entries (#327 shadow-fix §3;
    the re-wired Confirm control arm needs no settle branch). §5 write-back: bound_conflict +
    realized_r_h12 thread through from settle_entry_shadow (NULL-safe for pre-fix rows)."""
    from datetime import timedelta
    from agents.market_intelligence import anticipation as de
    from agents.market_intelligence.db import (
        get_settleable_consolidation_entry_shadows, get_anticipation_ohlcv,
        settle_consolidation_entry_shadow,
    )
    # ENTRY_SETTLE_WINDOW=12 trading bars ≈ 17 calendar days; the exact bar-count gate lives in
    # settle_entry_shadow, so this floor only needs to be a safe over-include.
    ripe = await get_settleable_consolidation_entry_shadows(today - timedelta(days=17))
    settled = []
    for r in ripe:
        try:
            bars = de.db_rows_to_bars(await get_anticipation_ohlcv(r["ticker"], today))
            entry_idx = next((j for j, b in enumerate(bars)
                              if b["date"] == r["entry_date"].isoformat()), None)
            if entry_idx is None:
                continue  # entry day not in the fetched window (shouldn't happen at 340d lookback)
            res = de.settle_entry_shadow(bars, entry_idx, float(r["stop_price"]),
                                         target_r=float(r["target_r"]))
            if res is None:
                continue  # not enough forward bars yet — abstain, retry next run
            if await settle_consolidation_entry_shadow(
                    r["id"], outcome=res["outcome"], realized_r=res["realized_r"],
                    fwd_mfe_r=res["fwd_mfe_r"], bound_conflict=res.get("bound_conflict"),
                    realized_r_h12=res.get("realized_r_h12")):
                settled.append((r["ticker"], res))
        except Exception as e:
            logger.error(f"entry-shadow settle {r['ticker']}/{r['id']}: {e}", exc_info=True)
    logger.info(f"entry-shadow settlement: {len(ripe)} ripe considered, {len(settled)} settled")
    return settled


async def _htf_breakout_settle_job(today):
    """#356 Phase 3 — settle ripe HTF breakout-shadow rows from daily bars. Mirrors the #327 entry-shadow
    settle job, but the HTF entry FILLS at base_high (a stop-limit-buy), NOT the bar close — so the R-math
    uses flag_detector._htf_settle_from_bars (entry=base_high, break-day-inclusive). SHADOW telemetry;
    never submits. Logs ripe-considered vs settled so a silent-0 is distinguishable from 'nothing ripe'."""
    from datetime import timedelta
    from agents.market_intelligence import anticipation as de
    from agents.market_intelligence.flag_detector import _htf_settle_from_bars
    from agents.market_intelligence.db import (
        get_settleable_htf_breakout_shadows, get_anticipation_ohlcv, settle_htf_breakout_shadow,
    )
    ripe = await get_settleable_htf_breakout_shadows(today - timedelta(days=24))
    settled = []
    for r in ripe:
        try:
            bars = de.db_rows_to_bars(await get_anticipation_ohlcv(r["ticker"], today))
            entry_idx = next((j for j, b in enumerate(bars)
                              if b["date"] == r["break_date"].isoformat()), None)
            if entry_idx is None:
                continue  # break day not in the fetched window
            res = _htf_settle_from_bars(bars, entry_idx, entry_price=float(r["entry_price"]),
                                        stop=float(r["stop_loss_price"]), target_r=float(r["target_r"]))
            if res is None:
                continue  # not enough forward bars yet — abstain, retry next run
            if await settle_htf_breakout_shadow(r["id"], outcome=res["outcome"],
                                                realized_r=res["realized_r"], fwd_mfe_r=res["fwd_mfe_r"]):
                settled.append((r["ticker"], res))
        except Exception as e:
            logger.error(f"htf-breakout-shadow settle {r['ticker']}/{r['id']}: {e}", exc_info=True)
    logger.info(f"htf-breakout-shadow settlement: {len(ripe)} ripe considered, {len(settled)} settled")
    return settled


async def _htf_management_shadow_job():
    """#396 HTF Phase 4 — MANAGEMENT shadow (SEPARATE from Phase 3's fixed-3R bet settlement
    above). For every clean Phase-3 breakout-shadow row still open (or never yet replayed),
    replays the SOURCED management protocol (docs/setups/htf.md "Management, Phase 4, shadow":
    scale 33-50% day 3-5 -> breakeven -> trail the 10/20 EMA -> exit on close-below) forward from
    daily bars via flag_detector._htf_management_replay, and UPSERTs the current full lifecycle
    snapshot. DB-SOURCED, restart-safe (feedback_scheduler_aggregators_db_sourced): every row is
    a FULL recompute from mi_daily_closes each run — no incremental cross-run state is trusted,
    so a container restart mid-lifecycle loses nothing (the next run just recomputes from bars +
    the immutable Phase-3 entry spec). INTELLIGENCE-side — no broker calls, matches how the other
    HTF shadow jobs (flag_continuation_scan / the Phase 3 settle folded into
    consolidation_readiness) are classified. Audit-log only (CLAUDE.md: transient shadow
    telemetry -> mi_audit_log, never a new Telegram surface) — never submits an order."""
    from datetime import timedelta
    from agents.market_intelligence import anticipation as de
    from agents.market_intelligence.flag_detector import (
        _htf_management_replay, _HTF_MGMT_SCALE_FRACTION, _HTF_MGMT_TRAIL_MODE,
    )
    from agents.market_intelligence.db import (
        get_htf_management_shadow_candidates, get_anticipation_ohlcv,
        upsert_htf_management_shadow, log_audit_event,
    )
    from agents.market_intelligence.collector import et_today
    today = et_today()
    candidates = await get_htf_management_shadow_candidates()
    updated = newly_trail_exit = newly_hard_stop = 0
    for r in candidates:
        try:
            bars = de.db_rows_to_bars(
                await get_anticipation_ohlcv(r["ticker"], today, lookback_days=340))
            entry_idx = next((j for j, b in enumerate(bars)
                              if b["date"] == r["break_date"].isoformat()), None)
            if entry_idx is None:
                continue  # break day not yet in the fetched window (shouldn't happen at 340d)
            res = _htf_management_replay(
                bars, entry_idx, entry_price=float(r["entry_price"]),
                initial_stop=float(r["stop_loss_price"]), shares=float(r["shares"] or 0))
            if res is None:
                continue  # degenerate spec (risk<=0 / no shares) — nothing to replay
            await upsert_htf_management_shadow(
                r["shadow_id"], r["ticker"], r["break_date"],
                entry_price=float(r["entry_price"]), initial_stop=float(r["stop_loss_price"]),
                initial_shares=float(r["shares"] or 0),
                scale_fraction=_HTF_MGMT_SCALE_FRACTION, trail_mode=_HTF_MGMT_TRAIL_MODE,
                status=res["status"], remaining_shares=res["remaining_shares"],
                partial_taken=res["partial_taken"], breakeven_active=res["breakeven_active"],
                events=res["events"], realized_r=res["realized_r"],
                last_bar_date=res["last_bar_date"])
            updated += 1
            if res["status"] == "closed_trail_exit":
                newly_trail_exit += 1
            elif res["status"] == "closed_hard_stop":
                newly_hard_stop += 1
        except Exception as e:   # loud-ok: per-row shadow telemetry, must not drop the rest of the run
            logger.error(f"htf-management-shadow replay {r.get('ticker')}/{r.get('shadow_id')}: {e}",
                        exc_info=True)
    logger.info(f"htf-management-shadow: {len(candidates)} candidates, {updated} upserted "
                f"({newly_trail_exit} trail-exit, {newly_hard_stop} hard-stop this run)")
    if candidates:
        await log_audit_event(
            "htf_management_shadow_run",
            f"{len(candidates)} candidates, {updated} upserted, "
            f"{newly_trail_exit} trail-exit, {newly_hard_stop} hard-stop")
    return updated


async def _spend_alarm_job():
    """Run at 17:52 ET (after the EOD LLM-heavy chain). #378 Phase 2 — Telegram
    WARN only when MTD variable spend breaches ANTHROPIC_MONTHLY_BUDGET or
    today's spend is a >2× trailing-30d-median anomaly; silent otherwise
    (/cost is the on-demand board). Read-only on api_usage."""
    try:
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.cost_board import run_daily_spend_alarm
        fired = await run_daily_spend_alarm(et_today())
        logger.info(f"spend-alarm: {'FIRED' if fired else 'quiet'}")
    except Exception as e:
        logger.error(f"spend-alarm job failed: {e}", exc_info=True)
        await notify_job_failure("spend_alarm", str(e))
    # #379 Phase 3 — THE WATCHDOG. Own try/except so a watchdog failure never
    # blots out the (already-vetted) #378 spend alarm above; named separately
    # in notify_job_failure so an operator can tell which sub-check broke.
    try:
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.cost_board import run_cost_watchdog
        watchdog = await run_cost_watchdog(et_today())
        logger.info(f"cost-watchdog: {'FIRED' if watchdog else 'quiet'}")
    except Exception as e:
        logger.error(f"cost-watchdog job failed: {e}", exc_info=True)
        await notify_job_failure("cost_watchdog", str(e))
    # #543 TRUNCATION CHECK. Rides this job because it reads the same table, but it is a
    # CORRECTNESS check, not a cost one: a response cut off by max_tokens is silent data
    # corruption (theme_assignment was dead for ten days that way). Own try/except so it can
    # never blot out the two vetted checks above, and named separately in notify_job_failure.
    try:
        from agents.market_intelligence.cost_board import run_truncation_check
        trunc = await run_truncation_check()
        logger.info(f"truncation-check: {'FIRED' if trunc else 'quiet'}")
    except Exception as e:
        logger.error(f"truncation-check job failed: {e}", exc_info=True)
        await notify_job_failure("truncation_check", str(e))


async def _book_concentration_job():
    """Run at 16:18 ET (after the close, after the 16:12 equity snapshot so the
    %-of-equity line is same-day). #452 R1 Stage 1 — correlated-book telemetry:
    audit row every run, Telegram ONLY when ≥2 open live positions share an
    ADR-0025 Stage-A family. READ-ONLY on trade state, no broker calls
    (THE LINE; the Stage-2 entry gate is operator-gated CHANGE_PROCESS)."""
    try:
        from agents.market_intelligence.book_concentration import (
            run_book_concentration_snapshot,
        )
        res = await run_book_concentration_snapshot("live")
        logger.info(
            f"book-concentration: {res['n_open']} open, "
            f"{len(res['flagged'])} flagged famil(ies)")
    except Exception as e:
        logger.error(f"book-concentration job failed: {e}", exc_info=True)
        await notify_job_failure("book_concentration", str(e))


async def _giveback_shadow_job():
    """Run at 17:38 ET (EOD, after positions close). Log the peak-lock (giveback) SHADOW for
    live MAGNA53 trades that closed today — ADR 0023 F1 forward measurement (operator 7/9).
    Pure compute + DB/audit, NO broker calls, NO live-exit change (THE LINE)."""
    try:
        from agents.market_intelligence.giveback_shadow import run_giveback_shadow
        from agents.market_intelligence.collector import et_today
        n = await run_giveback_shadow(et_today())
        logger.info(f"giveback-shadow: logged {n} live giveback-shadow row(s)")
    except Exception as e:
        logger.error(f"giveback-shadow job failed: {e}", exc_info=True)
        await notify_job_failure("giveback_shadow", str(e))


async def _pivot_stop_shadow_job():
    """Run at 17:42 ET (EOD, after the giveback shadow). Log the ADR 0031 pivot-stop SHADOW
    (baseline vs P1 swing-pivot vs P2 character-MA counterfactuals) for live MAGNA53 trades
    that closed today. Pure compute + DB/audit, NO broker calls, NO live-exit change (THE LINE;
    live flip queues strictly behind giveback F1 — ADR 0031 §0)."""
    try:
        from agents.market_intelligence.pivot_stop_shadow import run_pivot_stop_shadow
        from agents.market_intelligence.collector import et_today
        n = await run_pivot_stop_shadow(et_today())
        logger.info(f"pivot-stop-shadow: logged {n} row(s)")
    except Exception as e:
        logger.error(f"pivot-stop-shadow job failed: {e}", exc_info=True)
        await notify_job_failure("pivot_stop_shadow", str(e))


async def _sell_discipline_recorder_job():
    """Run at 17:46 ET (EOD, after the 17:00 nightly close pull + the 17:38/17:42 shadows).
    #508 WS1: write one durable sell-discipline record per newly-closed trade (ALL setups,
    both account modes) — what it REACHED (intraday + daily-close axes, with WHEN) vs what
    it KEPT — BEFORE mi_intraday_bars' 120d retention purges the minute-level peak timing.
    Catch-up window (the #310 lesson), idempotent. RECORD ONLY — no exit rule, no broker
    calls, no live-trade mutation (THE LINE). Surfaces on the 16:02 mgmt-judge Telegram
    (records for a trade closed today appear on the NEXT day's digest; same-day closes
    show as provisional lines meanwhile)."""
    try:
        from agents.market_intelligence.sell_discipline import record_sell_discipline
        from agents.market_intelligence.collector import et_today
        n = await record_sell_discipline(et_today())
        logger.info(f"sell-discipline recorder: wrote {n} record(s)")
    except Exception as e:
        logger.error(f"sell-discipline recorder job failed: {e}", exc_info=True)
        await notify_job_failure("sell_discipline_recorder", str(e))


# ── #343 chart-vision judge-axis SHADOW (operator-approved 6/18, ~$30/6wk, HIGH+MODERATE) ──────
# Decision-window start: the registry predicate counts `chart_axis_shadow_delta` rows with
# created_at >= this date, so only the SCHEDULED accrual (first counted fire Mon 6/22) feeds N — a
# manual smoke before it stays out of the decision. Backstop: N>=10 deltas OR the 7-31 date.
# ⚠️ THESE TWO DATES ARE HAND-SYNCED with data_gated_reviews.yaml → review_id
# `chart_vision_axis_shadow_decision` (predicate_sql: created_at >= '2026-06-19', CURRENT_DATE >=
# '2026-07-31'). YAML SQL can't import a Python constant — if you bump either date, change BOTH.
_CHART_AXIS_SHADOW_START = "2026-06-19"
_CHART_AXIS_SHADOW_BACKSTOP = "2026-07-31"
_CHART_AXIS_SHADOW_DAILY_CAP = 8   # per-day candidate cap (cost guard ~ HIGH+MODERATE/day)
_CHART_AXIS_SHADOW_REPLICATES = 3  # per arm, for the judge noise floor


async def _chart_axis_shadow_job():
    """#343 chart-vision judge-axis SHADOW recorder. EOD (17:50 ET mon-fri) — grades TODAY's cohort.
    Thin wrapper over _run_chart_axis_shadow so the verify one-shot can drive the SAME emit path
    against a prior trading day (the scheduled fire is always et_today())."""
    from agents.market_intelligence.collector import et_today
    await _run_chart_axis_shadow(et_today())


async def _run_chart_axis_shadow(today):
    """Date-parameterized core, entirely OFF the live 9:45 grade path. For each of `today`'s EP
    HIGH+MODERATE alerts (capped), re-grades through the holistic judge TWICE — arm B (the candidate
    text-only axis note, NO chart) and arm C (the same note + a point-in-time prior-day daily chart)
    — FRESH ×3 each, and emits a `chart_axis_shadow_delta` audit row when BOTH arms are modal-stable
    and the verdict DIFFERS (the chart changed the call = the labelable signal). The operator labels
    the deltas at N>=10 / 7-31 (data_gated_reviews `chart_vision_axis_shadow_decision`); promotion
    into the live rubric axis is the separate sign-off step (ADR 0011).

    SHADOW INVARIANT: writes ONLY mi_audit_log (`chart_axis_shadow_*`) — never mi_ep_alerts /
    mi_safeguard_state / anything the EP/judge path reads, and NO files. Delta charts are RE-RENDERED
    at digest time from the audit row's ticker+alert_date (render is deterministic — mi_daily_closes
    < alert_date), so there is no ephemeral container-disk dependency to survive deploys.
    `grade_holistic` is pure (no DB writes). Own AsyncAnthropic client + own semaphore (never the
    live grader's). Fail-open: any error logs + continues; an empty cohort (e.g. the 6/19 holiday) is
    a clean no-op.

    IDEMPOTENT: a same-day re-run skips tickers already marked graded/norender; an API-failed
    candidate leaves NO marker, so it retries on a same-day re-run. Cohort is today-only by design.
    """
    import os
    import anthropic
    from agents.market_intelligence import chart_axis as ca
    from agents.market_intelligence.db import (
        get_chart_axis_shadow_cohort, get_chart_axis_shadow_processed_tickers, log_audit_event,
    )
    from agents.market_intelligence.judge_replay_common import (
        build_judge_payload, fetch_profile, resolve_grounded_text,
    )
    client = None
    try:
        cohort, already = await asyncio.gather(  # independent reads
            get_chart_axis_shadow_cohort(today, limit=_CHART_AXIS_SHADOW_DAILY_CAP),
            get_chart_axis_shadow_processed_tickers(today),
        )
        pending = [r for r in cohort if r["ticker"] not in already]
        if not pending:
            logger.info(f"chart-axis shadow: {len(cohort)} cohort, 0 pending (all processed / "
                        f"empty {today}) — no-op")
            return

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("chart-axis shadow: no ANTHROPIC_API_KEY — skip")
            return
        client = anthropic.AsyncAnthropic(api_key=api_key)
        sem = asyncio.Semaphore(3)  # OWN bound; never the live grader's semaphore

        graded = deltas = norender = 0
        for row in pending:
            ticker, alert_date = row["ticker"], row["alert_date"]
            try:
                png, n_daily = await ca.render_prior_day_chart(ticker, alert_date)
                if png is None:
                    # data shortfall (too few prior bars) — won't change on re-run; mark handled.
                    # summary = ticker|alert_date so dedup keys on the COHORT, not write wall-clock.
                    await log_audit_event("chart_axis_shadow_norender",
                                          f"{ticker}|{alert_date.isoformat()}",
                                          f"no chart (n_daily={n_daily})")
                    norender += 1
                    continue
                mc, sector, company = await fetch_profile(ticker)
                grounded_text, _ = await resolve_grounded_text(dict(row), company, grounded=False)
                payload, _ = build_judge_payload(dict(row), grounded_text, mc, sector)

                bc = await ca.grade_b_c(client, sem, payload, png, _CHART_AXIS_SHADOW_REPLICATES,
                                        log_caller="chart_axis_shadow")
                if bc["b_verdict"] is None or bc["c_verdict"] is None:
                    # an arm fully failed (API) — leave NO marker so a same-day re-run retries.
                    logger.warning(f"chart-axis shadow {ticker}: arm produced no verdict — retry")
                    continue

                # grading COMPLETED (both arms ran; instability is itself a finding) → mark graded.
                # summary = ticker|alert_date so dedup keys on the COHORT, not write wall-clock.
                await log_audit_event(
                    "chart_axis_shadow_graded", f"{ticker}|{alert_date.isoformat()}",
                    f"floor={row['floor_tier']} B={bc['b_tiers']} C={bc['c_tiers']} "
                    f"stable={bc['both_stable']}")
                graded += 1

                if bc["visual_changed"]:
                    bv, cv = bc["b_verdict"], bc["c_verdict"]
                    # detail is SELF-CONTAINED: the chart is re-rendered at digest time from
                    # ticker+alert_date (deterministic) — no saved-PNG dependency across deploys.
                    detail = json.dumps({
                        "ticker": ticker, "alert_date": alert_date.isoformat(),
                        "floor_tier": row["floor_tier"],
                        "b_modal": bc["b_modal"], "c_modal": bc["c_modal"],
                        "direction": cv.get("direction_vs_floor"),
                        "b_rationale": (bv.get("rationale") or "")[:600],
                        "c_rationale": (cv.get("rationale") or "")[:600],
                    })
                    await log_audit_event(
                        "chart_axis_shadow_delta",
                        f"{ticker} {bc['b_modal']}→{bc['c_modal']} (chart moved the verdict)",
                        detail)
                    deltas += 1
            except Exception as e:
                logger.error(f"chart-axis shadow {ticker}/{alert_date}: {e}", exc_info=True)

        logger.info(f"chart-axis shadow: {len(pending)} pending, {graded} graded, "
                    f"{deltas} deltas, {norender} no-render")
    except Exception as e:
        logger.error(f"chart-axis shadow job failed: {e}", exc_info=True)
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:  # loud-ok: best-effort HTTP client cleanup on job exit, nothing to remediate
                pass


async def _coverage_probe_job():
    """S2 coverage probe (EP↔theme coverage loop, design 2026-07-13 §3) — EOD, zero-LLM.
    Probes TODAY's themeless EP HIGH+MODERATE alerts for blind-spot theme cohorts via
    deterministic evidence (peer-name match in the catalyst corpus + same-day co-gap +
    market-adjusted co-movement) and logs every row to mi_coverage_probe; §3.3-confirmed
    cohorts feed mi_theme_candidates_shadow (source='coverage_probe', SURFACE-ONLY — the
    nightly auto-promote carve-out in get_shadow_theme_candidates keeps them off the
    promote lane; /promotetheme is the only graduation path). run_coverage_probe is
    fully defensively wrapped — a probe failure can never break the EOD chain.

    Theme consolidation Phase 1 (operator-ruled 2026-07-27, decision 2): in mode
    'on' this JOB IS RETIRED — 0 confirmed cohorts / 0 candidates lifetime; its
    P3 market-adjusted co-movement primitive survives as the birth gate's
    evidence annotation (theme_birth_gate._p3_annotation, importing the same
    coverage_probe helpers). Fail-closed mode read: 'off'/'observe'/error ⇒ the
    probe runs exactly as today (observe changes nothing behavioral). Audited
    on skip, never silent."""
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.db import get_theme_birth_gate_mode
    if (await get_theme_birth_gate_mode()) == "on":
        logger.info("coverage probe SKIPPED — job retired (birth-gate mode 'on'); P3 lives on in theme_birth_gate")
        await log_audit_event(
            "coverage_probe_retired",
            summary="coverage_probe job retired (theme_birth_gate mode 'on') — "
                    "P3 co-movement survives as the birth gate's evidence annotation",
            detail="run_coverage_probe skipped; mi_coverage_probe/mi_theme_candidates_shadow untouched",
        )
        return
    from agents.market_intelligence.coverage_probe import run_coverage_probe
    await run_coverage_probe(et_today())


async def _theme_axis_co_move_refresh_job():
    """#329 STEP-0 — EOD recompute of the theme-axis shadow's INDEPENDENT co-movement check
    for TODAY's themed rows. The shadow writer rides the 7:00–10:00 AM EP scan, when today's
    mi_daily_closes rows don't exist yet (the 17:00 nightly pull ingests them) — so the live
    path logged co_moving=NULL on every row, permanently; the #367 health read's ~90%
    not-computable was largely this instrumentation artifact, not signal absence. SHADOW:
    writes ONLY mi_theme_axis_shadow's three co-movement columns + mi_audit_log; the theme
    cohort is re-derived STRICTLY-PRIOR (no lookahead, no born-today-theme circularity — see
    refresh_co_movement_for_date's docstring). Never raises past the wrapper."""
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.theme_axis_shadow import refresh_co_movement_for_date
    pool = await get_pool()
    async with pool.acquire() as conn:
        out = await refresh_co_movement_for_date(conn, et_today())
    logger.info(f"theme-axis co-movement EOD refresh: {out}")


async def _chart_axis_shadow_weekly_digest_job():
    """#343 — Sunday push of the week's new chart-axis SHADOW deltas for OPERATOR labeling. RE-RENDERS
    each delta's chart from the audit row's ticker+alert_date (render is deterministic — no saved-PNG
    dependency, survives deploys) and sends it inline (Telegram sendPhoto) with the no-chart→with-chart
    caption + the with-chart rationale, plus the running delta count and days to the 7-31 backstop so
    the decision never arrives by surprise. Empty week → quiet (no Telegram). Read-only; the operator
    owns the label + the eventual promote/hold call (ADR 0011)."""
    from datetime import date as _date
    from agents.market_intelligence import chart_axis as ca
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.db import get_audit_log, get_chart_axis_shadow_delta_count
    from agents.market_intelligence.briefing import send_telegram_message, send_telegram_photo
    try:
        rows, total = await asyncio.gather(  # independent reads
            get_audit_log(event_type="chart_axis_shadow_delta", since_hours=168, limit=50),
            get_chart_axis_shadow_delta_count(_date.fromisoformat(_CHART_AXIS_SHADOW_START)),
        )
        days_left = (_date.fromisoformat(_CHART_AXIS_SHADOW_BACKSTOP) - et_today()).days
        if not rows:
            logger.info("chart-axis weekly digest: 0 new deltas — quiet")
            return
        head = (f"📈 *Chart-vision shadow — {len(rows)} new delta(s) to label* (#343)\n"
                f"Running N={total}/10 · decision by {_CHART_AXIS_SHADOW_BACKSTOP} "
                f"({days_left}d) — label each: did the chart move it the RIGHT way?\n"
                "(label when you can — the decision gate re-pulls every delta, nothing's lost.)")
        await send_telegram_message(head)
        for r in rows:
            try:
                d = json.loads(r.get("detail") or "{}")
            except (ValueError, TypeError):
                d = {}
            caption = (f"{d.get('ticker','?')} {d.get('alert_date','')}  "
                       f"floor={d.get('floor_tier')}\n"
                       f"no-chart={d.get('b_modal')} → +chart={d.get('c_modal')} "
                       f"({d.get('direction')})\n"
                       f"why(+chart): {(d.get('c_rationale') or '')[:300]}")
            ticker, ad = d.get("ticker"), d.get("alert_date")
            sent = False
            if ticker and ad:
                try:  # re-render the SAME point-in-time chart the judge saw (deterministic)
                    png, _ = await ca.render_prior_day_chart(ticker, _date.fromisoformat(ad))
                    if png:
                        sent = await send_telegram_photo(png, caption=caption,
                                                         filename=f"{ticker}_{ad}.png")
                except Exception as e:
                    logger.warning(f"chart-axis digest re-render {ticker}: {e}")
            if not sent:  # render unavailable — still surface the text so it's labelable
                await send_telegram_message(caption + "\n(chart re-render unavailable)")
    except Exception as e:
        logger.error(f"chart-axis weekly digest failed: {e}", exc_info=True)


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

                # #210 Wave A/B verify + #211 daily KPI seed: confirm the catalyst
                # corpus path emitted source-provenance, and record the unknown-rate
                # (graded strong/gc with NO direct source). Telegram ONLY on the
                # broken case (alerts graded but zero provenance = path silently
                # dead — the #173 silent-death class); the healthy summary is an
                # audit row only (alert-vs-audit discipline). DB-sourced, no module
                # state (feedback-scheduler-aggregators-db-sourced).
                try:
                    prov_rows = await conn.fetch(
                        "SELECT detail FROM mi_audit_log "
                        "WHERE event_type = 'ep_catalyst_provenance' AND created_at >= $1",
                        now.replace(hour=0, minute=0, second=0, microsecond=0),
                    )
                    n_prov = len(prov_rows)
                    n_direct = n_unknown = 0
                    by_class: dict[str, int] = {}
                    for r in prov_rows:
                        try:
                            d = json.loads(r["detail"] or "{}")
                        except (ValueError, TypeError):
                            continue
                        if d.get("has_direct_source"):
                            n_direct += 1
                        elif d.get("catalyst_quality") in ("strong", "game_changer"):
                            n_unknown += 1
                        for cls in (d.get("sources") or {}):
                            by_class[cls] = by_class.get(cls, 0) + 1
                    if alert_count and n_prov == 0:
                        await send_telegram_message(
                            "🔴 *EP Catalyst Provenance*\n"
                            f"{alert_count} EP alert(s) today but 0 provenance rows — the "
                            "#210 Benzinga/grade-corpus path may not be firing. Check the "
                            "`ep_catalyst_provenance` audit + EP scan logs."
                        )
                    else:
                        await log_audit_event(
                            "ep_provenance_daily",
                            f"{n_prov} graded · {n_direct} direct · {n_unknown} unknown(strong/gc,no-direct)",
                            json.dumps({
                                "date": now.date().isoformat(),
                                "graded": n_prov, "direct_sourced": n_direct,
                                "unknown_cohort": n_unknown, "by_source_class": by_class,
                            }),
                        )
                        logger.info(f"EP provenance: {n_prov} graded, {n_direct} direct, "
                                    f"{n_unknown} unknown, classes={by_class}")
                except Exception as _pe:
                    logger.warning(f"EP provenance check skipped: {_pe}")
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


# 9M Day 2 ORB job REMOVED 2026-08-02 (#515, operator: "9m day2 is dead and needs to be gone
# period"). The 9M CHARACTER detection stays — only the Day-2 ENTRY strategy is retired.


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

    # Equity comes from the broker (creds live in the execution role). Skip the
    # call entirely in the intelligence role — no creds, and the boot marker is
    # forensic-only (#256 W2 seam item 2: was a non-fatal fetch_failed degrade).
    from agents.market_intelligence.constants import runs_execution_jobs
    equity_str = "unknown"
    if not runs_execution_jobs():
        equity_str = "n/a (intelligence role — no broker creds)"
    else:
        try:
            from agents.market_intelligence.broker import alpaca_client as alpaca  # exec-boundary-ok: moves-with-job (W2)
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

    # #509 model auto-resolution: record what every LLM role is EFFECTIVELY
    # running this boot (traceability — "what was the judge running on date X").
    # Intelligence/combined role only internally guarded inside the function
    # (runs_intelligence_jobs()) — the execution container shares the DB/
    # registry and would otherwise double-write.
    from agents.market_intelligence.model_resolution import record_boot_resolution
    asyncio.create_task(record_boot_resolution())

    # Data pull: 5:00 PM ET (30 min after tape settles), Mon-Fri.
    # expected_min_rows recalibrated 5000→3500 (#263, 2026-06-10), then
    # 3500→2200 (2026-07-02): #286 (dd4eeb4, 6/15, operator-signed) added the
    # $10M/day liquidity floor which INTENTIONALLY shrank the scored universe
    # 3,888–4,008 → 2,467–2,530 (9 runs observed) — the stale 3500 floor had
    # the job stuck on empty_result every market day since, a permanently-red
    # dead signal (the second instance of this class after #263; #340's
    # delta-vs-trailing-median design is the durable fix — this is evidence).
    # 2200 ≈ 10% below the new observed band floor: still catches a genuine
    # universe/writer drop without alarming on the steady state.
    _scheduler.add_job(
        audit_wrap(_nightly_data_pull, JOB_NIGHTLY_DATA_PULL, expected_min_rows=2200),
        CronTrigger(hour=17, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_NIGHTLY_DATA_PULL,
        replace_existing=True,
    )

    # FAMILY B — gap-anchored anticipation readiness + 3b (SHADOW) — PAUSED 2026-06-16 (ADR-0013).
    # Root cause (root-caused 2026-06-16): the universe seed `get_anticipation_gap_seeds`
    # hard-gates on a +40% one-day gap (`close >= 1.40*prev_close`) reverse-engineered from
    # ONE stock (MNTS), never the operator's methodology, never sign-off-surfaced. Both jobs
    # write `mi_anticipation_lifecycle` off that phantom universe nightly, contaminating the
    # shadow telemetry. The matched pair is UN-REGISTERED to stop active contamination. The
    # gap-anchored machine (`replay`/`evaluate_candidate` + `mi_anticipation_lifecycle`) now
    # belongs to FAMILY B / #297 (delayed-EP rework) to reclaim — it is NOT the
    # Family-A consolidation rebuild. Its phantom rows are #297's to archive/clean (decoupled
    # from this Phase 1, per advisor 6/17). IDs remain in INTELLIGENCE_OWNED_JOB_IDS
    # (classified-but-unregistered is harmless) so #297 re-registration is a one-block uncomment.
    #   _scheduler.add_job(
    #       audit_wrap(_anticipation_readiness_job, "anticipation_readiness"),
    #       CronTrigger(hour=17, minute=35, day_of_week="mon-fri", timezone="America/New_York"),
    #       id="anticipation_readiness",
    #       replace_existing=True,
    #   )
    #   _scheduler.add_job(
    #       audit_wrap(_anticipation_3b_job, "anticipation_3b"),
    #       CronTrigger(hour=16, minute=20, day_of_week="mon-fri", timezone="America/New_York"),
    #       id="anticipation_3b",
    #       replace_existing=True,
    #   )

    # FAMILY A — "consolidation plays post a runup" (ADR 0013, signed §2) SHADOW RECORDER.
    # The #270 rebuild on the SIGNED universe (runup MAX/MIN≥1.15 → coil → shortlist). Keyed on
    # (ticker, anchor_date), kept stable by select_consolidation_keys' CARRY-FORWARD (the live probe
    # showed the raw rolling-window anchor drifts 7/71 names/day; carry-forward absorbs it — proven
    # in tests/test_anticipation_consolidation.py::test_carry_forward_*). UN-PAUSED 2026-06-17
    # (operator decision 4 fast-follow — collect data asap, observe-only). 17:35 ET after the 17:00
    # nightly_data_pull. Surfaces via /anticipation (now reads mi_anticipation_consolidation).
    # 17:35 ET runs the WHOLE Family-A lifecycle: scan/coil + the #327 entry-watch + the
    # forward-shadow settlement (folded in via _run_entry_shadow_settlement) + ONE unified daily
    # digest. After the 17:00 nightly_data_pull. SHADOW, observe-only.
    # The base detection is now the COIL-FINDER (anticipation.evaluate_coil_consolidation: runup leg
    # → hold-≤50% → tight), which REPLACED the peak-anchored evaluate_consolidation on 2026-06-27
    # (the old one swallowed the post-runup pullback — CRWD read 24%). Same job, same digest, same
    # /anticipation board + entry-signals + settlement; only the base detector changed. ADR 0013.
    _scheduler.add_job(
        audit_wrap(_consolidation_readiness_job, "consolidation_readiness"),
        CronTrigger(hour=17, minute=35, day_of_week="mon-fri", timezone="America/New_York"),
        id="consolidation_readiness",
        replace_existing=True,
    )

    # #396 HTF Phase 4 — MANAGEMENT shadow, 17:36 ET mon-fri (right after consolidation_readiness,
    # which folds in Phase 3's HTF settle — keeps the whole HTF shadow family scheduled adjacently).
    # Needs today's daily-close bar (from nightly_data_pull @ 17:00) + the Phase 3 breakout-shadow
    # rows (populated intraday by the live #94 scan, not EOD-gated). INTELLIGENCE-side — pure
    # compute + DB/audit-log only, no broker calls (matches flag_continuation_scan/
    # consolidation_readiness's classification below).
    _scheduler.add_job(
        audit_wrap(_htf_management_shadow_job, "htf_management_shadow"),
        CronTrigger(hour=17, minute=36, day_of_week="mon-fri", timezone="America/New_York"),
        id="htf_management_shadow",
        replace_existing=True,
    )

    # #378 Phase 2 — daily spend alarm, 17:52 ET mon-fri (after the EOD LLM
    # chain). Telegram only on budget breach / 2×-median anomaly; /cost is the
    # on-demand board. Read-only on api_usage. Same job also runs the #379
    # Phase 3 watchdog (per-caller cost anomaly + reduction surfacing).
    _scheduler.add_job(
        audit_wrap(_spend_alarm_job, "spend_alarm"),
        # DAILY incl. weekends (review 7/17): mon-fri left Sat/Sun spend
        # permanently outside the day-scoped 2×-median trigger — a weekend
        # runaway loop (Sun 8AM self-audit, Fable blocks) would never fire it.
        CronTrigger(hour=17, minute=52, timezone="America/New_York"),
        id="spend_alarm",
        replace_existing=True,
    )

    # #452 R1 Stage 1 — book-concentration telemetry, 16:18 ET mon-fri (after the
    # close + the 16:12 equity snapshot). Audit row every run; Telegram only when
    # ≥2 open live positions share a Stage-A family. Read-only, no broker calls.
    _scheduler.add_job(
        audit_wrap(_book_concentration_job, "book_concentration"),
        CronTrigger(hour=16, minute=18, day_of_week="mon-fri", timezone="America/New_York"),
        id="book_concentration",
        replace_existing=True,
    )

    # Peak-lock (giveback) SHADOW — 17:38 ET mon-fri, EOD after positions close. Logs what the
    # ADR 0023 peak-lock (arm +6% / floor 60%) WOULD have done on today's closed live MAGNA53
    # trades vs actual (F1 forward measurement, operator 7/9). Pure compute + DB, no broker calls.
    _scheduler.add_job(
        audit_wrap(_giveback_shadow_job, "giveback_shadow"),
        CronTrigger(hour=17, minute=38, day_of_week="mon-fri", timezone="America/New_York"),
        id="giveback_shadow",
        replace_existing=True,
    )

    # ADR 0031 pivot-stop SHADOW — 17:42 ET mon-fri (after the giveback shadow's 17:38; both are
    # read-only counterfactuals on closed trades, disjoint tables — they coexist by design §0).
    _scheduler.add_job(
        audit_wrap(_pivot_stop_shadow_job, "pivot_stop_shadow"),
        CronTrigger(hour=17, minute=42, day_of_week="mon-fri", timezone="America/New_York"),
        id="pivot_stop_shadow",
        replace_existing=True,
    )

    # #508 WS1 sell-discipline RECORDER — 17:46 ET mon-fri, after the 17:00 nightly close pull
    # (close-day daily rows exist) and the 17:38/17:42 counterfactual shadows. One durable
    # reached-vs-kept record per newly-closed trade; record + display only, no exit rule.
    _scheduler.add_job(
        audit_wrap(_sell_discipline_recorder_job, "sell_discipline_recorder"),
        CronTrigger(hour=17, minute=46, day_of_week="mon-fri", timezone="America/New_York"),
        id="sell_discipline_recorder",
        replace_existing=True,
    )

    # #343 chart-vision judge-axis SHADOW — 17:50 ET mon-fri, EOD (scan idle since 10:00, after the
    # 17:00 nightly pull). Grades today's EP HIGH+MODERATE B (text-axis) vs C (+chart) and logs the
    # deltas the operator labels. SHADOW: audit-only writes, never the live grade path. (#267/#343)
    _scheduler.add_job(
        audit_wrap(_chart_axis_shadow_job, "chart_axis_shadow"),
        # ⚠ PAUSED 2026-08-02 (operator): the DAILY drip is off; the CAPABILITY is kept.
        # Measured: 56 rows over 24 days (~2.3/day against a cap of 8), 336 judge calls,
        # ~$11/mo — about 85% of all ep_grade_judge spend — for 5 verdict changes, 1 clean
        # delta, and ZERO influence on any trade (verified: the shadow never writes a grade
        # back, and of its 5 flagged names only NNE reached a trade row, which never filled —
        # skipped window:out_of_orb). #343 was signed "hold, no promotion" on 8/01, so it was
        # collecting for a decision already made.
        #
        # NOTHING IS LOST BY STOPPING. `render_prior_day_chart` builds the chart point-in-time
        # from stored daily OHLCV, so any historical alert can be re-graded on demand — and the
        # offline corpus is ALREADY 4x larger (227 graded alerts with settled outcomes vs 56
        # shadow rows), with a better scorer available: 43 closed trades carry realized R, which
        # is what actually happened to money rather than a 5-day drift.
        #
        # Operator 2026-08-02: "i want chart reading to play a role but maybe not just the
        # current way where it's not bringing value; however, i still want to leverage all the
        # data/trades we're collecting to eval and test chart reading separately, once we can
        # refine it properly to be valuable, we can introduce back into trading process."
        # ⇒ the deliberate tool is `scripts/eval_chart_judge.py` (read-only, point-in-time, no
        # lookahead, two-sided cohorts, replicate noise floor). Run it on purpose, with the spend
        # authorised, over a real sample — do NOT resurrect a 2-a-day cron.
        CronTrigger(hour=17, minute=50, day_of_week="mon-fri", timezone="America/New_York"),
        id="chart_axis_shadow",
        replace_existing=True,
        # ⚠ CORRECTED 2026-08-02 (the /simplify altitude pass caught the rationale, not the code):
        # an earlier comment here claimed de-registering would trip the role-partition guard. It
        # would NOT — for INTELLIGENCE_OWNED ids that guard is ONE-DIRECTIONAL (registered ⊆
        # classified, scheduler.py:~218), so a classified-but-unregistered intelligence job is
        # explicitly harmless; only EXECUTION_OWNED is checked bidirectionally. The REAL reason to
        # keep these registered is that the pause is TEMPORARY, pending the #519 offline eval:
        # resuming is deleting one kwarg, with the job body, the audit dedupe and the digest all
        # still wired. Contrast `9m_day2_orb`, RETIRED the same day and correctly de-registered
        # outright — park is for paused, deletion is for retired.
        next_run_time=None,
    )
    # Sunday 19:30 ET — push the week's new chart-axis deltas (chart inline) for operator labeling
    # + the running N vs the 7/31 backstop. Empty week → quiet.
    _scheduler.add_job(
        audit_wrap(_chart_axis_shadow_weekly_digest_job, "chart_axis_shadow_weekly_digest"),
        CronTrigger(day_of_week="sun", hour=19, minute=30, timezone="America/New_York"),
        id="chart_axis_shadow_weekly_digest",
        replace_existing=True,
        # ⚠ PAUSED with the shadow (2026-08-02). It was asking the operator to label deltas for
        # #343 — a decision SIGNED "hold, no promotion" on 8/01 — and even said so itself:
        # "decision by 2026-07-31 (-2d)". A nag for a closed decision is pure noise.
        next_run_time=None,
    )

    # S2 coverage probe: 5:55 PM ET mon-fri — after the 17:00 nightly pull has refreshed
    # today's mi_daily_closes (P3 co-movement) + mi_themes (the 7d-bounded themeless test)
    # and AFTER the pull's own promote pass (5d), so a probe cohort written tonight cannot
    # ride tonight's auto-promote even in ordering terms (the source carve-out is the real
    # wall). Zero-LLM, shadow tables + audit only; slots between chart_axis_shadow (17:50)
    # and the 18:00 evening briefing.
    _scheduler.add_job(
        audit_wrap(_coverage_probe_job, "coverage_probe"),
        CronTrigger(hour=17, minute=55, day_of_week="mon-fri", timezone="America/New_York"),
        id="coverage_probe",
        replace_existing=True,
        misfire_grace_time=900,
    )

    # #329 STEP-0 theme-axis co-movement EOD refresh: 5:58 PM ET mon-fri — same dependency
    # the 17:55 coverage probe rides (the 17:00 nightly pull must have ingested TODAY's
    # mi_daily_closes). The intraday shadow writer can never compute same-day co-movement
    # (closes don't exist at scan time), so without this the independent check beside the
    # structural attributor stays permanently NULL on the live path. Shadow-table-only
    # writes (mi_theme_axis_shadow + mi_audit_log) — never a grade/theme/trade table.
    _scheduler.add_job(
        audit_wrap(_theme_axis_co_move_refresh_job, "theme_axis_co_move_refresh"),
        CronTrigger(hour=17, minute=58, day_of_week="mon-fri", timezone="America/New_York"),
        id="theme_axis_co_move_refresh",
        replace_existing=True,
        misfire_grace_time=900,
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

    # Reset bar stream daily state + start EP scanning at 7:00 AM ET. The bar
    # stream lives in the EXECUTION service, so the reset routes through the
    # facade (inprocess = byte-identical; http = reaches execution's live stream).
    # _start_ep_scanning is intelligence-local (#256 W2 seam item 1).
    async def _ep_scan_start_job():
        from agents.market_intelligence.execution_client import reset_bar_stream_daily_state
        await reset_bar_stream_daily_state()
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
        from agents.market_intelligence.broker import bar_stream  # exec-boundary-ok: moves-with-job (W2)
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

    # #489 delayed-feed residual tracker: 4:35 PM ET — post-close; records the QUALITY in-window
    # 10%-crossers the detection delay missed + whether the 5% hybrid would have caught them.
    _scheduler.add_job(
        audit_wrap(_delayed_residual_job, "delayed_residual"),
        CronTrigger(hour=16, minute=35, day_of_week="mon-fri", timezone="America/New_York"),
        id="delayed_residual",
        replace_existing=True,
    )

    # #489 residual real-time-miss morning digest: 10:00 AM ET — ONE summary of the misses the watchdog
    # recorded audit-only during the ORB window (operator 7/21; replaces the per-ticker Telegram blast).
    _scheduler.add_job(
        audit_wrap(_rt_miss_digest_job, "rt_miss_digest"),
        CronTrigger(hour=10, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="rt_miss_digest",
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

    # Source-gap finder: Sunday 8:45 AM ET (#235 Wave E — after the weekly
    # review so its digest lands in the same operator reading window). Bounded
    # ≤8 Perplexity calls over the week's unknown cohort; output = operator
    # source-onboarding queue (source_gap_candidate audit rows + Telegram only
    # when an actionable non-covered finding exists). Telemetry — never grades.
    _scheduler.add_job(
        audit_wrap(_source_gap_finder_job, "source_gap_finder"),
        CronTrigger(day_of_week="sun", hour=8, minute=45, timezone="America/New_York"),
        id="source_gap_finder",
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
    # Runs every 30 min; skips if WebSocket stream is healthy. Times come from
    # the module-level _FILL_CHECK_TIMES SSoT (shared with EXECUTION_OWNED_JOB_IDS).
    for hour, minute in _FILL_CHECK_TIMES:
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

    # Pre-market gap-risk heads-up: 9:00 AM ET — warn if an open position is trading below
    # its stop pre-market (may gap through at the open). Read-only telemetry (ADR 0023 Card 5).
    _scheduler.add_job(
        audit_wrap(_premarket_gap_risk_job, "premarket_gap_risk"),
        CronTrigger(hour=9, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="premarket_gap_risk",
        replace_existing=True,
    )

    # Morning stop refresh: 9:35 AM ET — re-place stops for Day 2+ positions
    _scheduler.add_job(
        audit_wrap(_morning_stop_refresh_job, "morning_stop_refresh"),
        CronTrigger(hour=9, minute=35, day_of_week="mon-fri", timezone="America/New_York"),
        id="morning_stop_refresh",
        replace_existing=True,
    )

    # Position coverage check: every ~15 min, 09:31-15:55 ET (#527) — DETECTOR ONLY,
    # reads broker truth and confirms a live sell-stop covers every LIVE open
    # position. Cron slot uses the same hour="9-15" REGISTRATION idiom as
    # track_position_extremes below, but — unlike that job — a Day-2+ position
    # genuinely exists at 9:00/9:15, so the DoD's 09:31-15:55 window is enforced
    # explicitly inside _position_coverage_check_job, not left to the cron slot.
    _scheduler.add_job(
        audit_wrap(_position_coverage_check_job, "position_coverage_check"),
        CronTrigger(hour="9-15", minute="*/15", day_of_week="mon-fri", timezone="America/New_York"),
        id="position_coverage_check",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Post-close stop refresh: 4:20 PM ET — place the next session's GTC stop the
    # evening before, so a position is never unprotected during market hours.
    # Closes the 9:30-9:35 hole left by the DAY-lifetime bracket leg (operator
    # 2026-08-04: "as long as during market hours there's a stop in place").
    _scheduler.add_job(
        audit_wrap(_post_close_stop_refresh_job, "post_close_stop_refresh"),
        CronTrigger(hour=16, minute=20, day_of_week="mon-fri", timezone="America/New_York"),
        id="post_close_stop_refresh",
        replace_existing=True,
        misfire_grace_time=1800,
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

    # Kill/scale band EOD evaluation: 4:13 PM ET — one minute after the equity
    # snapshot/drawdown recompute so the band inputs are fresh. Telegram on a band
    # TRANSITION only (#275 / signed #268b bands). Intelligence-owned, DB-sourced.
    _scheduler.add_job(
        audit_wrap(_kill_scale_band_job, "kill_scale_band_eval"),
        CronTrigger(hour=16, minute=13, day_of_week="mon-fri", timezone="America/New_York"),
        id="kill_scale_band_eval",
        replace_existing=True,
    )

    # ORB cancellation EOD reclassify: 4:25 PM ET (#183) — corrects the intraday
    # classifier's lag-corrupted clean_miss labels on complete bars. Audit-only.
    _scheduler.add_job(
        audit_wrap(_orb_reclassify_eod_job, "orb_reclassify_eod"),
        CronTrigger(hour=16, minute=25, day_of_week="mon-fri", timezone="America/New_York"),
        id="orb_reclassify_eod",
        replace_existing=True,
    )

    # Intraday path recorder + worst-price/best-price tracking for open
    # positions: every 5 min from 9:30 AM to 4:00 PM ET (2026-05-10; subsumed
    # to Alpaca-sourced path recording #306, 2026-07-25 — same id, same cron
    # slot). Fetches real-time Alpaca minute bars per ticker with an
    # open-OR-closed-today position (#310-class fix), upserts the path into
    # mi_intraday_bars, then monotonic LEAST/GREATEST updates
    # lowest_price_seen + highest_price_seen on mi_live_trades over the
    # in-hold window only. Powers setup-quality analytics (does this setup
    # let trades run high before exit, or drag near stop?) AND the offline
    # intraday partial-profit sweep (docs/design/306_intraday_path_recorder_2026-07-25.md).
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

    # Intraday path recorder EOD completion sweep: once at 16:10 PM ET (#306,
    # 2026-07-25). The last */5 poll above fires 15:55, so this catches bars
    # 15:55-16:00 + any position closed in that window, and heals restart-day
    # mi_intraday_bars coverage holes for open multi-day positions. DB-write
    # only, no Telegram.
    _scheduler.add_job(
        audit_wrap(_position_path_eod_sweep_job, "position_path_eod_sweep"),
        CronTrigger(
            hour=16, minute=10,
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id="position_path_eod_sweep",
        replace_existing=True,
        misfire_grace_time=600,
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

    # Sugar Babies cohort refresh: 5:22 PM ET — slots between 5:15 parabolic_scan
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

    # Continuation-flag scan: 5:25 PM ET — slots between 5:22 sugar_babies cohort
    # refresh and 5:30 post_nightly_audit. Telemetry-only (phase=shadow); persists all
    # stages, Telegrams TRIGGERED + COILED + new-tightening on non-empty days.
    _scheduler.add_job(
        audit_wrap(_flag_scan_job, JOB_FLAG_SCAN),
        CronTrigger(hour=17, minute=25, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_FLAG_SCAN,
        replace_existing=True,
        misfire_grace_time=900,
    )

    # Cross-ticker emerging-theme synthesis: 6:05 PM ET — after the 5:00 nightly
    # pull has refreshed RS + themes (parabolic at 5:15 already relies on that),
    # before the 8:00 evening briefing. ADVISORY (#240): proposals go to
    # mi_theme_candidates_shadow (source='rs_slope_synthesis') for operator
    # review + the judge's narrative axis; never live mi_themes. Telegram only
    # on non-empty proposals; silent runs are audit-only.
    _scheduler.add_job(
        audit_wrap(_theme_synthesis_job, "theme_synthesis"),
        CronTrigger(hour=18, minute=5, day_of_week="mon-fri", timezone="America/New_York"),
        id="theme_synthesis",
        replace_existing=True,
        misfire_grace_time=900,
    )

    # #509 model auto-resolution — nightly refresh: 6:08 PM ET, calls
    # models.list and writes logs/model_resolution.json. expected_min_rows=3:
    # TIERS is always (opus, sonnet, haiku) — fewer than 3 resolved tiers is a
    # genuine anomaly (models.list came back missing a whole family), not a
    # quiet day. A new release is never silent (Telegram + audit inside the
    # job); this job only ever WRITES the cache — no role's live binding
    # changes until that role's process next boots (shared/llm_models.py
    # RESOLVED_ROLES / effective_model).
    from agents.market_intelligence.model_resolution import (
        check_judge_eval_divergence, refresh_model_resolution,
    )
    _scheduler.add_job(
        audit_wrap(refresh_model_resolution, JOB_MODEL_RESOLUTION_REFRESH, expected_min_rows=3),
        CronTrigger(hour=18, minute=8, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_MODEL_RESOLUTION_REFRESH,
        replace_existing=True,
        misfire_grace_time=900,
    )

    # #509 guardrail — 6:09 PM ET, right after the refresh above (though
    # logically independent: it compares THIS PROCESS's boot-time judge
    # binding, fixed since last boot, against the last passing eval — not
    # anything the refresh just wrote). WARN only, never blocks (see
    # model_resolution.py::check_judge_eval_divergence docstring).
    _scheduler.add_job(
        audit_wrap(check_judge_eval_divergence, JOB_JUDGE_EVAL_DIVERGENCE_CHECK),
        CronTrigger(hour=18, minute=9, day_of_week="mon-fri", timezone="America/New_York"),
        id=JOB_JUDGE_EVAL_DIVERGENCE_CHECK,
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

    # Intraday low-volume-rest scan: every 5 min during market hours (gate
    # internally 9:35-15:55 ET). Entry-technique #4 (#97) per
    # memory/user_tight_range_entry_techniques.md. A quiet tight coil inside the
    # base on dried-up volume. Telemetry-only shadow phase.
    _scheduler.add_job(
        audit_wrap(_low_vol_rest_scan_job, JOB_LOW_VOL_REST_SCAN),
        CronTrigger(
            hour="9-15", minute="*/5",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_LOW_VOL_REST_SCAN,
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Intraday entry-technique EOD digest: 16:00 ET — ONE consolidated roll-up of
    # the day's 5 shadow detectors (#168 noise fix; replaces ~23/day per-tick
    # pings, now default-off). Runs after the 15:55 scan stop.
    _scheduler.add_job(
        audit_wrap(_intraday_signals_eod_digest_job, "intraday_signals_eod_digest"),
        CronTrigger(hour=16, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="intraday_signals_eod_digest",
        replace_existing=True,
    )

    # P3 management-judge SHADOW pass (ADR 0014 / #300): 16:02 ET — one bounded EXIT verdict per
    # open live position, telemetry-only (zero execution authority). Staggered 2 min after the
    # 16:00 entry-technique digest so the two snapshot/LLM passes don't fire the same tick; still
    # "16:00-class", before the 17:00 nightly pull (so the snapshot is today's live price, not a
    # stale close — the part-1 QURE caveat). INTELLIGENCE-owned.
    _scheduler.add_job(
        audit_wrap(_position_mgmt_judge_job, "position_mgmt_judge"),
        CronTrigger(hour=16, minute=2, day_of_week="mon-fri", timezone="America/New_York"),
        id="position_mgmt_judge",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # Materiality SHADOW writer (16:25 ET) RETIRED 2026-06-10 (#249): the holistic
    # judge (ADR 0011, load-bearing since 2026-06-10) computes materiality on every
    # graded alert (rule_materiality input + its own Sonnet soft-tier), so the
    # offline would-be-fire_status accrual is subsumed. Historical shadow columns
    # (materiality_tier / materiality_source / fire_status_mat_shadow) remain in
    # mi_ep_alerts, frozen.

    # Intraday U&R (Undercut & Rally) scan: every 5 min during market hours
    # (gate internally 9:35-15:55 ET). Entry-technique #5 per
    # memory/user_tight_range_entry_techniques.md (Morales/OWL). Depth band is
    # adjacent to support-test (deeper undercut). Telemetry-only shadow phase.
    _scheduler.add_job(
        audit_wrap(_undercut_rally_scan_job, JOB_UNDERCUT_RALLY_SCAN),
        CronTrigger(
            hour="9-15", minute="*/5",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_UNDERCUT_RALLY_SCAN,
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

    # #150 open-window FINE reconcile: every minute 9:31-9:40 ET (mon-fri). The
    # 15-min cadence above can't resolve WHETHER a stop-limit was WORKING ('new')
    # during the ~9:31-9:33 fillable window vs still PENDING_NEW. That fork —
    # paper fill-engine fail (paper-only) vs acceptance-latency (#142-family, may
    # carry live) — decides #150's live-carry + whether the stop-market mitigation
    # is needed. Reuses the SAME reconcile job (zero order-handling logic touched);
    # the tight cadence times the pending_new->new transition via the
    # order_status_reconciled audit rows. Audit-only, ~10 extra 1-day-scoped polls/day.
    _scheduler.add_job(
        audit_wrap(_order_status_reconcile_job_open, JOB_ORDER_STATUS_RECONCILE + "_open"),
        CronTrigger(
            hour="9", minute="31-40",
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_ORDER_STATUS_RECONCILE + "_open",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # 9M EP Pace digest: hourly rollup at 10/11/12 ET (#133, 2026-05-27).
    # Pace alerts (89% of pinged 9M volume on 2026-05-27) aren't realtime
    # actionable — roll them up ONCE at 16:00 ET (whole-day window), matching
    # the entry-technique EOD digest (#168 noise fix, 2026-06-07). Was 3× hourly
    # (10/11/12); operator: anticipation → 1/day EOD. Actual 9M still rides the
    # prompt per-5-min digest in ninem_detector.
    _scheduler.add_job(
        audit_wrap(_9m_pace_digest_job, JOB_9M_PACE_DIGEST),
        CronTrigger(
            # 16:20 — staggered off the 16:00 entry-technique digest so the two
            # EOD rollups don't land the same second (the 16:xx family is spaced).
            hour=16, minute=20,
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_9M_PACE_DIGEST,
        replace_existing=True,
        misfire_grace_time=300,
    )

    # EP Judge delta digest: 16:25 ET (#240 / W3, 2026-06-09). PUSH complement to the
    # pull-only judge_delta_review.py / unjustified_demotion_sweep.py — once a day, the
    # names the holistic judge moved UP or DOWN vs the floor land in Telegram for the
    # judgment-correctness review. Staggered after the 16:20 9m_pace digest (the 16:xx
    # family is spaced). Empty day → no Telegram (shadow until the W2 flip).
    _scheduler.add_job(
        audit_wrap(_judge_delta_digest_job, JOB_JUDGE_DELTA_DIGEST),
        CronTrigger(
            hour=16, minute=25,
            day_of_week="mon-fri", timezone="America/New_York",
        ),
        id=JOB_JUDGE_DELTA_DIGEST,
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Market Close Digest flush: 16:55 ET (#479 half-1, operator-ruled fold).
    # The single post-close message — assembles every contribution buffered by
    # the folded 16:00–16:45 jobs (see _close_digest_job) and sends ONE
    # monospace digest. Fires after the LAST contributor (16:45
    # live_position_update); shares the 16:55 slot with time_stop_scan
    # (independent async jobs). Empty buffer → no message.
    _scheduler.add_job(
        audit_wrap(_close_digest_job, "close_digest"),
        CronTrigger(hour=16, minute=55, day_of_week="mon-fri",
                    timezone="America/New_York"),
        id="close_digest",
        replace_existing=True,
        misfire_grace_time=900,
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
    # 2026-07-01 moved 08:00 -> 18:00 ET (after close) per operator — this heavy
    # telemetry digest was landing on the market-day MORNING. It reads historical
    # backward-check data (no fresh-EOD dependency), so any post-close slot works;
    # runs after the 4:05-5:30 PM EOD jobs and before the 8 PM evening briefing.
    from agents.market_intelligence.quarterly_review import quarterly_backward_check_sweep_job
    _scheduler.add_job(
        audit_wrap(quarterly_backward_check_sweep_job, "monthly_backward_check_sweep"),
        CronTrigger(day=1, hour=18, minute=0, timezone="America/New_York"),
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

    # Partial-exit scan: 3:45 PM ET (DURING market hours) — Day 3-5
    # partial-profit exits. #361 (2026-06-23): SPLIT OUT of the 4:45 PM
    # live_position_update job. The 4:45 job fires after the 16:00 close, so a
    # partial's stop-replace parked in `pending_replace` until next-session open
    # (both old+new stops reserved the shares → qty_available=0 → partial
    # aborted). At 3:45 the stop-replace settles in ~0.2s and the sell fills.
    # The partial decision LOGIC is unchanged (single source of truth in
    # apply_daily_exit_step); only the trigger time moved. No double-fire: the
    # 4:45 job passes skip_partial_decision=True. Execution-owned (partials
    # touch the broker) → in EXECUTION_OWNED_JOB_IDS. ZoneInfo per #-tz rule
    # (pytz banned).
    # misfire_grace_time=600 (10 min): 3:45 is now the ONLY partial window (the
    # 4:45 job can no longer backstop it, #361). APScheduler's ~1s default would
    # silently DROP the day's partial if the scheduler were briefly busy at
    # 15:45:00. A 10-min grace still fires the partial well within market hours
    # (before the 16:00 close, so the stop-replace settles intraday — the whole
    # point of the split). Cap it at 600s so a long-after-close misfire (which
    # would reintroduce the pending_replace problem) is NOT honored.
    _scheduler.add_job(
        audit_wrap(_partial_exit_scan_job, "partial_exit_scan"),
        CronTrigger(hour=15, minute=45, day_of_week="mon-fri",
                    timezone=ZoneInfo("America/New_York")),
        id="partial_exit_scan",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Live position update: 4:45 PM ET — SMA trail + stop updates + summary.
    # #361 (2026-06-23): partials MOVED to partial_exit_scan (3:45 PM) — see
    # the registration above. This job no longer takes partials.
    # PAUSED 2026-05-29 (#151, advisor Option D) after 2 days of automated
    # partial-take failures; RE-ENABLED 2026-06-01 once the restoration
    # conditions were substantively met:
    #   (a) verify-broker-state between steps — SHIPPED as execute_partial_exit
    #       Step-1b verify-stop-live (poll-confirm replacement stop live before
    #       the sell). The "architectural split" refactor was cosmetic; the
    #       safety substance is in. Plus 2026-06-01: sub-penny stop rounding at
    #       the replace boundary + false-naked-on-replace-failure fix + #150
    #       share-reservation sell-retry.
    #   (b) Preflight Gate G6 — replace_order paper-Alpaca smoke in deploy. OK
    #   (c) Outcome-history circuit breaker — the cron calls execute_partial_exit
    #       with force=False (default), so the breaker guards this UNATTENDED
    #       path (vs /partialnow's force=True attended bypass). OK
    # Validated 2026-06-01: 2 paper integration-test passes + CRSR/RCAT
    # /partialnow clean. Watch the first unattended automated partial (~FPS Day 3).
    _scheduler.add_job(
        audit_wrap(_live_position_update_job, "live_position_update"),
        CronTrigger(hour=16, minute=45, day_of_week="mon-fri", timezone="America/New_York"),
        id="live_position_update",
        replace_existing=True,
    )

    # 9M EP intraday scan: every 5 min, 9:30 AM – 4:00 PM ET (regular session)
    _scheduler.add_job(
        audit_wrap(_9m_scan_job, "9m_ep_scan"),
        CronTrigger(hour="9-15", minute="*/5", day_of_week="mon-fri", timezone="America/New_York"),
        id="9m_ep_scan",
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

    # Apply the service-role job partition BEFORE the scheduler runs (#256 W2).
    # combined (default) = no-op; execution/intelligence drop the jobs they don't
    # own, fail-loud on a partition mistake. Read role here (not at import) so
    # tests can exercise both sides.
    from agents.market_intelligence.constants import SERVICE_ROLE as _ROLE
    _apply_role_partition(_scheduler, _ROLE)

    _scheduler.start()
    logger.info("Market Intelligence scheduler started (ET timezone)")

    # One-shot post-boot order reconcile (#123, 2026-05-26): closes the
    # deploy-during-market-hours gap where a container restart loses live
    # WebSocket trade_update events. Runs 60 seconds after boot to let
    # Alpaca clients finish their dual-account verification first.
    # Boot reconcile is EXECUTION-owned (#256 W2) and registered AFTER the
    # partition pass + .start(), so gate it on role directly here rather than
    # relying on removal. combined/execution add it; intelligence skips it.
    from agents.market_intelligence.constants import runs_execution_jobs as _runs_exec
    now_et_for_boot = datetime.now(_ET)
    if (_runs_exec() and now_et_for_boot.weekday() < 5
            and _dt_time(9, 30) <= now_et_for_boot.time() <= _dt_time(16, 5)):
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
