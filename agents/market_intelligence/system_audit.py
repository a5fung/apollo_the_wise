"""
Apollo's resilience & self-audit layer.

Three scheduled entry points + one on-demand:

    run_post_eod_audit()       16:15 ET — invariants + trade-side metrics
    run_post_nightly_audit()   17:30 ET — theme/cooldown/regime metrics
    run_baseline_refresh()     02:00 ET — recompute mi_metric_baselines
    run_topic_audit(topic)     /audit <topic> — same logic, ad-hoc subset

Severity ladder:
  L1 — invariant breach (audit_invariants.py library) → Telegram + audit row
  L2 — metric outside trimmed baseline (z>3 OR >5× median) → Telegram + audit row
  L3 — drift inside 1–3σ band; threshold-crossing only → audit row, no Telegram

Auto-remediation is off by design. Apollo detects, the user judges, Opus
mitigates. Every L1/L2 Telegram is built to be pasteable into Claude Code
with drill-down SQL + code pointers + a Sonnet hypothesis line.

See `~/.claude/plans/shiny-mapping-locket.md` for design rationale.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

import anthropic

from agents.market_intelligence.audit_invariants import all_invariants
from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import (
    add_baseline_reset,  # noqa: F401  re-exported for callers
    count_today_anomalies,
    get_baseline_reset,
    get_metric_baseline,
    get_pool,
    log_audit_event,
    upsert_metric_baseline,
)

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

# Per-metric loud-floor / loud-ceiling thresholds used when sample_n < 7.
# Conservative safe-mode limits, NOT steady-state baselines.
#
# Direction tag dictates how the threshold is interpreted AND how the warm
# (sample_n ≥ 14) multiplier rule is applied:
#   "high" — current > threshold fires L2; warm path uses current/p50 ≥ 5×.
#   "low"  — current < threshold fires L2; warm path uses p50/current ≥ 5×.
# The z-score check is direction-agnostic (uses abs(z)), so it catches drops
# automatically once sample_n is large enough; the asymmetric multiplier
# rule and the cold-start gate are the parts that need direction.
_COLD_START_CEILINGS: dict[str, tuple[float, str]] = {
    "cooldowns_per_day":              (20,   "high"),
    "9m_alerts_per_day":              (30,   "high"),
    "audit_errors_per_day":           (5,    "high"),
    "skip_count_infra":               (5,    "high"),
    "skip_count_filter":              (30,   "high"),
    "skip_count_setup":               (20,   "high"),
    "skip_count_block":               (5,    "high"),
    "skip_count_window":              (10,   "high"),
    # HIGH_ep_entry_rate: scanner-crash class — entered / actionable_detected
    # for HIGH-tier alerts. Denominator excludes as-designed blocks (safeguards,
    # timing, filters) so the rate stays high (0.8-1.0) under normal operation
    # and only drops when pipeline genuinely fails. Floor of 0.5 means "fewer
    # than half of actionable HIGHs reached broker = pipeline issue."
    "HIGH_ep_entry_rate":             (0.5,  "low"),   # < 0.5 entry rate = warning
    "theme_count_active":             (5,    "low"),   # < 5 themes = dedup death
    "validation_rate_limited_count":  (3,    "high"),
    "bar_stream_disconnect_count_24h": (5,   "high"),
}

_MIN_FULL_SAMPLE = 14
_WARMING_MIN = 7
# Minimum denominator before rate-style metrics emit a sample. On low-detection
# days a single skipped HIGH collapses entered/detected to 0.0 or 0.33, which
# trips the cold-start floor and pollutes the baseline with structural zeros.
# See 2026-05-03 changelog (5 false L2 fires from quiet-detection days).
_MIN_DETECTED_FOR_GATE = 5
_BASELINE_TRIM_PCT = 0.10
_BASELINE_LOOKBACK_DAYS = 30
_REGIME_BASELINE_DAYS = 10  # in-Crisis-only window for regime-conditional swap
_REGIME_CONDITIONAL_METRICS = {"HIGH_ep_entry_rate", "9m_alerts_per_day"}
_MAD_FALLBACK_THRESHOLD = 1.0  # below → 5×median rule only
_Z_THRESHOLD = 3.0
_MULTIPLIER_THRESHOLD = 5.0

_AUDIT_EVENT = "anomaly_detected"

# Token-bounded Sonnet hypothesis call. Single-flight (sequential) to avoid
# stacking org rate-limit budget on top of theme validation fan-outs.
_HYPOTHESIS_SEMAPHORE = asyncio.Semaphore(1)
_anthropic_client: anthropic.AsyncAnthropic | None = None


def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )
    return _anthropic_client


# ── Metric specs ─────────────────────────────────────────────────────────────


@dataclass
class MetricSpec:
    name: str
    fetch_today: Callable[..., Awaitable[float | None]]
    drill_sql: str
    code_pointers: list[str] = field(default_factory=list)
    # scale_invariant: True for ratios, percentages, counts that don't scale with
    # account equity. False for $-absolute metrics (P&L $, position $, etc.) whose
    # baselines must be reset on paper→live $ flip (or any equity step-change).
    # All current metrics are scale-invariant; flip to False when adding $-absolute.
    scale_invariant: bool = True


async def _today_cooldowns(conn) -> float:
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS n FROM mi_validation_cooldowns "
        "WHERE removed_at::date = CURRENT_DATE"
    )
    return float(row["n"] or 0)


async def _today_audit_errors(conn) -> float:
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS n FROM mi_audit_log
        WHERE event_type LIKE '%_error'
          AND (created_at AT TIME ZONE 'America/New_York')::date
              = (NOW() AT TIME ZONE 'America/New_York')::date
        """
    )
    return float(row["n"] or 0)


async def _today_skip_count(conn, *, category: str) -> float:
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS n FROM mi_live_trades
        WHERE alert_date = CURRENT_DATE
          AND status = 'skipped'
          AND split_part(skip_reason, ':', 1) = $1
        """,
        category,
    )
    return float(row["n"] or 0)


async def _today_high_entry_rate(conn) -> float | None:
    """For HIGHs the entry pipeline could actually act on, what fraction
    reached the broker?

    Denominator (`actionable`) excludes HIGHs blocked BEFORE pipeline entry
    by as-designed safeguards / filters / timing — those aren't pipeline
    failures. Without this exclusion (rewritten 2026-05-09), the metric fired
    L2 daily because most days have HIGHs blocked by max_positions, circuit
    breaker, or out_of_orb timing — entirely expected operational state.
    Numerator counts HIGHs that placed an order (status != 'skipped'); a
    cancelled-unfilled is pipeline success, just the price never triggered.

    Returns None when actionable < _MIN_DETECTED_FOR_GATE — quiet days lack
    the resolution to distinguish noise from breakage.

    Skip-reason classification (mirrors broker/skip_reasons.py):
      As-designed (excluded from denominator):
        - block:*        — safeguards (max_positions, circuit_breaker, etc.)
        - window:*       — timing (out_of_orb, duplicate)
        - filter:*       — pre-trade quality (ADV/ATR/mcap/RVOL)
        - setup:faded_from_orb / stop_too_wide / price_exceeds_cap /
          size_too_small — pre-entry quality gates
      Pipeline-failure (counted in actionable, NOT entered):
        - infra:*        — bar/subscribe/order-submit failures
        - setup:zero_range / account_fetch_failed — Alpaca/data outage
    """
    row = await conn.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (
            WHERE a.score_tier='HIGH'
              AND (
                lt.id IS NULL                 -- still in flight, no live_trades row yet
                OR lt.status != 'skipped'     -- entered pipeline (filled/cancelled/order_placed/etc.)
                OR lt.skip_reason ~ '^(infra:|setup:zero_range|setup:account_fetch_failed)'
              )
          ) AS actionable,
          COUNT(*) FILTER (
            WHERE a.score_tier='HIGH'
              AND lt.id IS NOT NULL
              AND lt.status != 'skipped'
          ) AS entered
        FROM mi_ep_alerts a
        LEFT JOIN mi_live_trades lt
          ON lt.ticker=a.ticker AND lt.alert_date=a.alert_date
        WHERE a.alert_date = CURRENT_DATE
        """
    )
    actionable = int(row["actionable"] or 0)
    entered = int(row["entered"] or 0)
    if actionable < _MIN_DETECTED_FOR_GATE:
        return None
    return entered / actionable


async def _today_active_themes(conn) -> float:
    row = await conn.fetchrow(
        """
        SELECT COUNT(DISTINCT name) AS n FROM mi_themes
        WHERE stage != 'Retired'
          AND theme_date >= CURRENT_DATE - INTERVAL '7 days'
        """
    )
    return float(row["n"] or 0)


async def _today_9m_alerts(conn) -> float:
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS n FROM mi_9m_ep_alerts WHERE alert_date = CURRENT_DATE"
    )
    return float(row["n"] or 0)


async def _accel_dropout_count_7d(conn) -> float:
    """Themes whose latest snapshot was 'Accelerating' AND last appeared 3–7
    days ago AND had ≥5 days at 'Accelerating' in their history. Captures
    "real" Accelerating themes that vanished without graduating to
    Mainstream — potential theme-engine quality signal (over-promotion to
    Accelerating, or genuine market churn).

    L1 doesn't fire on this (recency-cap design doesn't promise these
    survive); L2 alerts when count > p95 + 3 MAD."""
    row = await conn.fetchrow(
        """
        WITH latest AS (
            SELECT name, MAX(theme_date) AS last_seen
            FROM mi_themes
            GROUP BY name
        ),
        latest_stage AS (
            SELECT t.name, t.theme_date AS last_seen, t.stage
            FROM mi_themes t
            JOIN latest l
              ON t.name = l.name AND t.theme_date = l.last_seen
        ),
        accel_days AS (
            SELECT name, COUNT(DISTINCT theme_date) AS n_accel
            FROM mi_themes
            WHERE stage = 'Accelerating'
            GROUP BY name
        )
        SELECT COUNT(*) AS n
        FROM latest_stage ls
        JOIN accel_days ad ON ad.name = ls.name
        WHERE ls.stage = 'Accelerating'
          AND ls.last_seen <= CURRENT_DATE - INTERVAL '3 days'
          AND ls.last_seen >= CURRENT_DATE - INTERVAL '7 days'
          AND ad.n_accel  >= 5
        """
    )
    return float(row["n"] or 0)


async def _today_validation_rate_limited(conn) -> float:
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS n FROM mi_audit_log
        WHERE event_type = 'validation_rate_limited'
          AND (created_at AT TIME ZONE 'America/New_York')::date
              = (NOW() AT TIME ZONE 'America/New_York')::date
        """
    )
    return float(row["n"] or 0)


async def _today_bar_stream_disconnect_24h(conn) -> float:
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS n FROM mi_audit_log
        WHERE event_type = 'bar_stream_disconnect'
          AND created_at >= NOW() - INTERVAL '24 hours'
        """
    )
    return float(row["n"] or 0)


# Tagged by which scan owns them — post_eod (trade-side) vs post_nightly
# (theme/cooldown/regime). Topic command maps onto the same tags.
_TRADE_METRICS: list[MetricSpec] = [
    MetricSpec(
        "audit_errors_per_day", _today_audit_errors,
        "SELECT event_type, summary, detail FROM mi_audit_log "
        "WHERE event_type LIKE '%_error' "
        "  AND (created_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE "
        "ORDER BY created_at DESC LIMIT 50;",
        ["agents/market_intelligence/scheduler.py", "agents/market_intelligence/db.py::log_audit_event"],
    ),
    MetricSpec(
        "skip_count_infra", lambda conn: _today_skip_count(conn, category="infra"),
        "SELECT skip_reason, COUNT(*) FROM mi_live_trades "
        "WHERE alert_date=CURRENT_DATE AND status='skipped' "
        "  AND skip_reason LIKE 'infra:%' GROUP BY 1 ORDER BY 2 DESC;",
        ["agents/market_intelligence/broker/bar_stream.py", "agents/market_intelligence/broker/order_manager.py"],
    ),
    MetricSpec(
        "skip_count_filter", lambda conn: _today_skip_count(conn, category="filter"),
        "SELECT skip_reason, COUNT(*) FROM mi_live_trades "
        "WHERE alert_date=CURRENT_DATE AND status='skipped' "
        "  AND skip_reason LIKE 'filter:%' GROUP BY 1 ORDER BY 2 DESC;",
        ["agents/market_intelligence/backtester/filters.py"],
    ),
    MetricSpec(
        "skip_count_setup", lambda conn: _today_skip_count(conn, category="setup"),
        "SELECT skip_reason, COUNT(*) FROM mi_live_trades "
        "WHERE alert_date=CURRENT_DATE AND status='skipped' "
        "  AND skip_reason LIKE 'setup:%' GROUP BY 1 ORDER BY 2 DESC;",
        ["agents/market_intelligence/broker/order_manager.py::prepare_orb_order"],
    ),
    MetricSpec(
        "skip_count_block", lambda conn: _today_skip_count(conn, category="block"),
        "SELECT skip_reason, COUNT(*) FROM mi_live_trades "
        "WHERE alert_date=CURRENT_DATE AND status='skipped' "
        "  AND skip_reason LIKE 'block:%' GROUP BY 1 ORDER BY 2 DESC;",
        ["agents/market_intelligence/broker/live_tracker.py::_check_safeguards"],
    ),
    MetricSpec(
        "skip_count_window", lambda conn: _today_skip_count(conn, category="window"),
        "SELECT skip_reason, COUNT(*) FROM mi_live_trades "
        "WHERE alert_date=CURRENT_DATE AND status='skipped' "
        "  AND skip_reason LIKE 'window:%' GROUP BY 1 ORDER BY 2 DESC;",
        ["agents/market_intelligence/scheduler.py::_ep_scan_job"],
    ),
    MetricSpec(
        "HIGH_ep_entry_rate", _today_high_entry_rate,
        # Drill-down splits today's HIGHs by skip-reason category. Pipeline-failure
        # buckets (infra:* / setup:zero_range / setup:account_fetch_failed) are the
        # ones that should trigger investigation. As-designed buckets
        # (block:* / window:* / filter:*) explain why rate may look low without
        # the pipeline being broken — denominator already excludes them.
        "SELECT COALESCE(split_part(lt.skip_reason, ':', 1), "
        "  CASE WHEN lt.id IS NULL THEN 'no_row' "
        "       WHEN lt.status != 'skipped' THEN 'entered' "
        "       ELSE 'unknown' END) AS bucket, "
        "COUNT(*) AS n, array_agg(a.ticker ORDER BY a.ep_score DESC) AS tickers "
        "FROM mi_ep_alerts a "
        "LEFT JOIN mi_live_trades lt ON lt.ticker=a.ticker AND lt.alert_date=a.alert_date "
        "WHERE a.alert_date=CURRENT_DATE AND a.score_tier='HIGH' "
        "GROUP BY 1 ORDER BY 2 DESC;",
        ["agents/market_intelligence/broker/live_tracker.py::process_new_alerts_live",
         "agents/market_intelligence/broker/entry_pipeline.py::submit_trade_entry"],
    ),
    MetricSpec(
        "9m_alerts_per_day", _today_9m_alerts,
        "SELECT ticker, alert_date, current_price, projected_vol "
        "FROM mi_9m_ep_alerts WHERE alert_date=CURRENT_DATE ORDER BY current_price DESC;",
        ["agents/market_intelligence/ninem_detector.py"],
    ),
    MetricSpec(
        "bar_stream_disconnect_count_24h", _today_bar_stream_disconnect_24h,
        "SELECT created_at, summary, detail FROM mi_audit_log "
        "WHERE event_type='bar_stream_disconnect' "
        "  AND created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC;",
        ["agents/market_intelligence/broker/bar_stream.py::_run_stream"],
    ),
]

async def _today_shadow_orb_entries(conn) -> float:
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS n FROM mi_orb_shadow_trades "
        "WHERE alert_date = CURRENT_DATE AND status IN ('open', 'closed')"
    )
    return float(row["n"] or 0)


async def _today_shadow_orb_no_entry_rate(conn) -> float | None:
    """Share of today's shadow rows that never triggered (no 1-min bar high
    >= 5-min ORB high in the 9:35-10:00 window). Steady state should sit
    well below 100% — if it spikes, the 5-min ORB is too wide vs price
    action that day, or the bar fetch is silently failing.

    Returns None when total < _MIN_DETECTED_FOR_GATE (denominator too small
    for the rate to be informative; same structural-zero class as
    _today_high_entry_rate).
    """
    row = await conn.fetchrow(
        """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE status = 'no_entry') AS no_entry
        FROM mi_orb_shadow_trades
        WHERE alert_date = CURRENT_DATE
        """
    )
    total = int(row["total"] or 0)
    no_entry = int(row["no_entry"] or 0)
    if total < _MIN_DETECTED_FOR_GATE:
        return None
    return no_entry / total


async def _shadow_vs_live_r_delta_30d(conn) -> float:
    """Mean (r_5m - r_1m) over the last 30 days, on alert_dates where both
    a closed shadow row and a closed live trade exist for the same ticker.
    Positive → 5-min ORB beating 1-min on average; negative → live wins.
    Returns 0 when fewer than 5 paired closed trades exist (not enough
    signal to form a baseline)."""
    row = await conn.fetchrow(
        """
        WITH paired AS (
          SELECT
            shadow.total_pnl   / NULLIF(shadow.risk_dollars, 0) AS r_5m,
            live.total_pnl     / NULLIF(live.risk_dollars,   0) AS r_1m
          FROM mi_orb_shadow_trades shadow
          JOIN mi_live_trades live
            ON live.ticker = shadow.ticker
           AND live.alert_date = shadow.alert_date
          WHERE shadow.bar_size_minutes = 5
            AND shadow.alert_date >= CURRENT_DATE - INTERVAL '30 days'
            AND shadow.status = 'closed'
            AND live.status   = 'closed'
            AND shadow.risk_dollars > 0
            AND live.risk_dollars > 0
        )
        SELECT COUNT(*) AS n, AVG(r_5m - r_1m) AS delta FROM paired
        """
    )
    n = int(row["n"] or 0)
    if n < 5:
        return 0.0
    return float(row["delta"] or 0)


_SHADOW_ORB_METRICS: list[MetricSpec] = [
    MetricSpec(
        "shadow_orb_entries_per_day", _today_shadow_orb_entries,
        "SELECT ticker, signal_type, status, trigger_minute_et, orb_high, orb_low "
        "FROM mi_orb_shadow_trades WHERE alert_date = CURRENT_DATE "
        "ORDER BY status, ticker;",
        ["agents/market_intelligence/broker/shadow_orb_tracker.py::run_shadow_pass"],
    ),
    MetricSpec(
        "shadow_orb_no_entry_rate", _today_shadow_orb_no_entry_rate,
        "SELECT status, COUNT(*) FROM mi_orb_shadow_trades "
        "WHERE alert_date=CURRENT_DATE GROUP BY 1 ORDER BY 2 DESC;",
        ["agents/market_intelligence/broker/shadow_orb_tracker.py::_process_candidate"],
    ),
    MetricSpec(
        "shadow_vs_live_r_delta_30d", _shadow_vs_live_r_delta_30d,
        "WITH paired AS ( "
        "  SELECT shadow.ticker, shadow.alert_date, "
        "    shadow.total_pnl / NULLIF(shadow.risk_dollars, 0) AS r_5m, "
        "    live.total_pnl   / NULLIF(live.risk_dollars,   0) AS r_1m "
        "  FROM mi_orb_shadow_trades shadow "
        "  JOIN mi_live_trades live ON live.ticker=shadow.ticker "
        "    AND live.alert_date=shadow.alert_date "
        "  WHERE shadow.bar_size_minutes=5 "
        "    AND shadow.alert_date >= CURRENT_DATE - INTERVAL '30 days' "
        "    AND shadow.status='closed' AND live.status='closed') "
        "SELECT * FROM paired ORDER BY alert_date DESC;",
        ["agents/market_intelligence/broker/exit_logic.py::apply_daily_exit_step"],
    ),
]


async def _today_fishhook_anchors(conn) -> float:
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS n FROM mi_fishhook_anchors WHERE anchor_date = CURRENT_DATE"
    )
    return float(row["n"] or 0)


async def _fishhook_promotion_rate_30d(conn) -> float:
    """Share of anchors with anchor_date ≥ T-25 that escaped 'pending' (i.e.
    drifted below anchor in the watch window). Bounded to 30d so steady
    state is interpretable; cold-start returns 0 when n < 5."""
    row = await conn.fetchrow(
        """
        WITH eligible AS (
          SELECT state FROM mi_fishhook_anchors
          WHERE anchor_date BETWEEN CURRENT_DATE - INTERVAL '30 days'
                              AND CURRENT_DATE - INTERVAL '11 days'
        )
        SELECT
          COUNT(*) AS n_total,
          COUNT(*) FILTER (WHERE state IN ('promoted','reclaimed','settled',
                                            'invalidated','expired_no_reclaim')) AS n_promoted
        FROM eligible
        """
    )
    n_total = int(row["n_total"] or 0)
    if n_total < 5:
        return 0.0
    return float(row["n_promoted"] or 0) / n_total


async def _fishhook_reclaim_rate_30d(conn) -> float:
    """Share of promoted anchors (anchor_date ≥ T-26) that reached reclaim
    within T+25 — i.e. escaped both the watch window and the reclaim
    window. Cold-start returns 0 when n_promoted < 5."""
    row = await conn.fetchrow(
        """
        WITH eligible AS (
          SELECT state FROM mi_fishhook_anchors
          WHERE anchor_date BETWEEN CURRENT_DATE - INTERVAL '30 days'
                              AND CURRENT_DATE - INTERVAL '26 days'
            AND state IN ('promoted','reclaimed','settled',
                           'invalidated','expired_no_reclaim')
        )
        SELECT
          COUNT(*) AS n_promoted,
          COUNT(*) FILTER (WHERE state IN ('reclaimed','settled','invalidated')) AS n_reclaimed
        FROM eligible
        """
    )
    n_promoted = int(row["n_promoted"] or 0)
    if n_promoted < 5:
        return 0.0
    return float(row["n_reclaimed"] or 0) / n_promoted


_FISHHOOK_METRICS: list[MetricSpec] = [
    MetricSpec(
        "fishhook_anchors_per_day", _today_fishhook_anchors,
        "SELECT ticker, gap_pct, in_top2000, in_ep_alerts FROM mi_fishhook_anchors "
        "WHERE anchor_date = CURRENT_DATE ORDER BY gap_pct DESC;",
        ["agents/market_intelligence/fishhook_detector.py::_fetch_today_anchors"],
    ),
    MetricSpec(
        "fishhook_promotion_rate_30d", _fishhook_promotion_rate_30d,
        "SELECT state, COUNT(*) FROM mi_fishhook_anchors "
        "WHERE anchor_date BETWEEN CURRENT_DATE - INTERVAL '30 days' "
        "                    AND CURRENT_DATE - INTERVAL '11 days' "
        "GROUP BY 1 ORDER BY 2 DESC;",
        ["agents/market_intelligence/fishhook_detector.py::_advance_state"],
    ),
    MetricSpec(
        "fishhook_reclaim_rate_30d", _fishhook_reclaim_rate_30d,
        "SELECT state, COUNT(*) FROM mi_fishhook_anchors "
        "WHERE anchor_date BETWEEN CURRENT_DATE - INTERVAL '30 days' "
        "                    AND CURRENT_DATE - INTERVAL '26 days' "
        "  AND state IN ('promoted','reclaimed','settled','invalidated','expired_no_reclaim') "
        "GROUP BY 1 ORDER BY 2 DESC;",
        ["agents/market_intelligence/fishhook_detector.py::_advance_state"],
    ),
]


_NIGHTLY_METRICS: list[MetricSpec] = [
    MetricSpec(
        "cooldowns_per_day", _today_cooldowns,
        "SELECT theme_name, COUNT(*) FROM mi_validation_cooldowns "
        "WHERE removed_at::date = CURRENT_DATE GROUP BY 1 ORDER BY 2 DESC LIMIT 15;",
        ["agents/market_intelligence/db.py::get_active_themes",
         "agents/market_intelligence/theme_engine.py::_validate_theme_membership"],
    ),
    MetricSpec(
        "theme_count_active", _today_active_themes,
        "SELECT name, MAX(theme_date), stage FROM mi_themes "
        "WHERE stage != 'Retired' GROUP BY name, stage ORDER BY MAX(theme_date) DESC;",
        ["agents/market_intelligence/db.py::get_active_themes"],
    ),
    MetricSpec(
        "validation_rate_limited_count", _today_validation_rate_limited,
        "SELECT created_at, summary, detail FROM mi_audit_log "
        "WHERE event_type='validation_rate_limited' "
        "  AND (created_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE;",
        ["agents/market_intelligence/theme_engine.py::_validate_theme_membership"],
    ),
    MetricSpec(
        "accel_dropout_count_7d", _accel_dropout_count_7d,
        "WITH latest AS (SELECT name, MAX(theme_date) AS last_seen FROM mi_themes GROUP BY name), "
        "accel_days AS (SELECT name, COUNT(DISTINCT theme_date) AS n_accel FROM mi_themes "
        "  WHERE stage='Accelerating' GROUP BY name) "
        "SELECT t.name, l.last_seen, ad.n_accel FROM mi_themes t "
        "  JOIN latest l ON t.name=l.name AND t.theme_date=l.last_seen "
        "  JOIN accel_days ad ON ad.name=t.name "
        "  WHERE t.stage='Accelerating' "
        "    AND l.last_seen BETWEEN CURRENT_DATE - INTERVAL '7 days' AND CURRENT_DATE - INTERVAL '3 days' "
        "    AND ad.n_accel >= 5 "
        "  ORDER BY ad.n_accel DESC;",
        ["agents/market_intelligence/theme_engine.py::_promote_to_accelerating",
         "agents/market_intelligence/db.py::get_active_themes"],
    ),
]

_ALL_METRICS = _TRADE_METRICS + _NIGHTLY_METRICS + _SHADOW_ORB_METRICS + _FISHHOOK_METRICS

_TOPIC_MAP: dict[str, list[MetricSpec]] = {
    "cooldowns":  [m for m in _ALL_METRICS if m.name == "cooldowns_per_day"],
    "themes":     [m for m in _ALL_METRICS if m.name in {"theme_count_active", "cooldowns_per_day", "accel_dropout_count_7d"}],
    "skips":      [m for m in _ALL_METRICS if m.name.startswith("skip_count_")],
    "positions":  [m for m in _ALL_METRICS if m.name in {"HIGH_ep_entry_rate"}],
    "feed":       [m for m in _ALL_METRICS if m.name in {"bar_stream_disconnect_count_24h", "skip_count_infra"}],
    "9m":         [m for m in _ALL_METRICS if m.name == "9m_alerts_per_day"],
    "shadow_orb": _SHADOW_ORB_METRICS,
    "fishhook":   _FISHHOOK_METRICS,
    "all":        _ALL_METRICS,
}


# ── Baselines ────────────────────────────────────────────────────────────────


def _trimmed_median_mad(values: list[float], trim_pct: float = _BASELINE_TRIM_PCT) -> tuple[float, float, float, int]:
    """Return (p50, p95, mad, sample_n) on a trimmed sample.

    Drops top and bottom `trim_pct` of values before computing median + MAD.
    Single-day spikes don't propagate into the reference distribution.
    """
    n = len(values)
    if n == 0:
        return (0.0, 0.0, 0.0, 0)
    sorted_v = sorted(values)
    trim = int(n * trim_pct)
    kept = sorted_v[trim: n - trim] if trim and n - 2 * trim >= 1 else sorted_v
    p50 = statistics.median(kept)
    # p95 from full distribution (more robust signal of 'high' than trimmed)
    idx95 = max(int(round(0.95 * (n - 1))), 0)
    p95 = sorted_v[idx95]
    deviations = [abs(v - p50) for v in kept]
    mad = statistics.median(deviations) if deviations else 0.0
    return (float(p50), float(p95), float(mad), n)


async def _fetch_history(conn, metric: MetricSpec, *, lookback_days: int = _BASELINE_LOOKBACK_DAYS) -> list[float]:
    """Read trailing daily samples for `metric` from `mi_audit_log`.

    The baseline refresh job writes one `metric_sample` row per metric per
    day so we don't have to re-run every metric query for every historical
    day. Falls back to recomputing today's value only when called fresh.
    """
    reset_at = await get_baseline_reset(metric.name)
    if reset_at is not None:
        # Drop history older than the latest epoch reset.
        rows = await conn.fetch(
            """
            SELECT detail FROM mi_audit_log
            WHERE event_type = 'metric_sample'
              AND summary = $1
              AND created_at >= $2
              AND created_at >= NOW() - ($3 || ' days')::INTERVAL
            ORDER BY created_at DESC
            """,
            metric.name, reset_at, str(lookback_days),
        )
    else:
        rows = await conn.fetch(
            """
            SELECT detail FROM mi_audit_log
            WHERE event_type = 'metric_sample'
              AND summary = $1
              AND created_at >= NOW() - ($2 || ' days')::INTERVAL
            ORDER BY created_at DESC
            """,
            metric.name, str(lookback_days),
        )
    out: list[float] = []
    for r in rows:
        try:
            payload = json.loads(r["detail"] or "{}")
            v = payload.get("value")
            if v is not None:
                out.append(float(v))
        except (ValueError, TypeError):
            continue
    return out


async def _record_metric_sample(metric_name: str, value: float) -> None:
    """Persist today's value as a `metric_sample` audit event so future
    baseline refreshes can compute against history without re-running every
    metric query for every historical day."""
    await log_audit_event(
        "metric_sample",
        summary=metric_name,
        detail=json.dumps({"value": float(value), "as_of": str(et_today())}),
    )


async def run_baseline_refresh() -> int:
    """02:00 ET nightly job. Rebuilds `mi_metric_baselines` from trailing
    samples. Idempotent — safe to re-run. Returns count of baselines refreshed
    so the audit_wrap empty-result invariant can fire if zero are written.
    """
    today = et_today()
    refreshed = 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        for metric in _ALL_METRICS:
            history = await _fetch_history(conn, metric)
            p50, p95, mad, n = _trimmed_median_mad(history)
            await upsert_metric_baseline(
                metric.name, today,
                p50=p50, p95=p95, mad=mad, sample_n=n,
            )
            refreshed += 1
    logger.info(f"system_audit: baselines refreshed for {refreshed} metrics")
    return refreshed


async def _regime_conditional_baseline(conn, metric: MetricSpec, current_regime: str) -> tuple[float, float, float, int] | None:
    """Compute a baseline using only the last N trading days the system was in
    `current_regime`. Returns None if there isn't a `_REGIME_BASELINE_DAYS`-day
    sample of the regime to compare against.
    """
    rows = await conn.fetch(
        """
        WITH regime_dates AS (
          SELECT regime_date FROM mi_market_regime
          WHERE regime = $1
          ORDER BY regime_date DESC LIMIT $2
        )
        SELECT al.detail FROM mi_audit_log al
        JOIN regime_dates rd
          ON (al.created_at AT TIME ZONE 'America/New_York')::date = rd.regime_date
        WHERE al.event_type = 'metric_sample' AND al.summary = $3
        """,
        current_regime, _REGIME_BASELINE_DAYS, metric.name,
    )
    values: list[float] = []
    for r in rows:
        try:
            v = json.loads(r["detail"] or "{}").get("value")
            if v is not None:
                values.append(float(v))
        except (ValueError, TypeError):
            continue
    if len(values) < _REGIME_BASELINE_DAYS:
        return None
    return _trimmed_median_mad(values)


# ── Recent context (for Sonnet hypothesis injection) ─────────────────────────


_CLAUDEMD_HEADER_RE = re.compile(r"^## Changes Made (\d{4}-\d{2}-\d{2})", re.MULTILINE)


def _recent_changes_context(repo_root: Path | None = None, limit: int = 5) -> list[str]:
    """Last N `## Changes Made YYYY-MM-DD` headers from CLAUDE.md, plus the
    first ~80 chars of body text following each header. Used to ground the
    Sonnet hypothesis call in what the user actually shipped recently.
    """
    if repo_root is None:
        # this file is at agents/market_intelligence/system_audit.py
        repo_root = Path(__file__).resolve().parents[2]
    md_path = repo_root / "CLAUDE.md"
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    matches = list(_CLAUDEMD_HEADER_RE.finditer(text))
    out: list[str] = []
    for m in matches[:limit]:
        date_str = m.group(1)
        body_start = m.end()
        # Grab the first non-blank line within ~250 chars after the header.
        snippet = text[body_start: body_start + 250].strip().splitlines()
        first_line = next((s.strip("# ").strip() for s in snippet if s.strip() and not s.startswith("##")), "")
        out.append(f"{date_str}: {first_line[:80]}")
    return out


async def _recent_audit_event_types(conn, hours: int = 48, limit: int = 10) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT event_type, COUNT(*) AS n FROM mi_audit_log
        WHERE created_at >= NOW() - ($1 || ' hours')::INTERVAL
        GROUP BY event_type ORDER BY n DESC LIMIT $2
        """,
        str(hours), limit,
    )
    return [f"{r['event_type']}({r['n']})" for r in rows]


# ── Sonnet hypothesis ────────────────────────────────────────────────────────


async def _synthesize_hypothesis(
    metric_name: str,
    current: float,
    baseline: dict | None,
    recent_changes: list[str],
    recent_events: list[str],
) -> str:
    """One Sonnet call per anomaly. Token-bounded; on 429 returns a fallback
    string so the alert still fires — never silently drops.
    """
    try:
        client = _get_anthropic_client()
    except Exception:
        return "(no anthropic client — see drill-down SQL)"

    base_p50 = baseline.get("p50") if baseline else None
    base_mad = baseline.get("mad") if baseline else None
    sample_n = baseline.get("sample_n") if baseline else None

    prompt = (
        f"You are debugging a momentum-trading system. A metric has gone outside its "
        f"normal range. Give ONE short sentence (under 30 words) hypothesizing the most "
        f"likely cause. Be specific. Reference recent changes if any look related.\n\n"
        f"Metric: {metric_name}\n"
        f"Today's value: {current}\n"
        f"30d trimmed median: {base_p50}\n"
        f"30d MAD: {base_mad}\n"
        f"Sample size: {sample_n}\n\n"
        f"Recent system changes (CLAUDE.md): {', '.join(recent_changes) or '(none)'}\n"
        f"Recent audit event types (48h): {', '.join(recent_events) or '(none)'}\n"
    )

    try:
        async with _HYPOTHESIS_SEMAPHORE:
            for attempt in range(2):
                try:
                    resp = await client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=120,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    break
                except anthropic.RateLimitError:
                    if attempt == 1:
                        return "(rate-limited — see drill-down SQL)"
                    wait = 8 + random.random() * 4
                    await log_audit_event(
                        "anthropic_rate_limited",
                        summary=f"Hypothesis call rate-limited for '{metric_name}' — retry in {wait:.0f}s",
                        detail="429 on claude-sonnet-4-6 in system_audit",
                    )
                    await asyncio.sleep(wait)
        if not resp.content:
            return "(empty response)"
        block = resp.content[0]
        return (getattr(block, "text", "") or "").strip()[:240]
    except Exception as e:
        logger.warning(f"system_audit: hypothesis call failed for {metric_name}: {e}")
        return f"(hypothesis call failed: {type(e).__name__})"


# ── Anomaly detection ────────────────────────────────────────────────────────


@dataclass
class Anomaly:
    level: int  # 1 / 2 / 3
    key: str
    body: dict


def _band_for(z: float, ratio: float) -> int:
    """Return 0 (steady), 1, 2, 3 — the band today's value sits in.

    `ratio` is direction-aware: caller passes current/p50 for "high" metrics
    and p50/current for "low" metrics, so the >=5× rule fires symmetrically.
    """
    abs_z = abs(z)
    if abs_z >= _Z_THRESHOLD or ratio >= _MULTIPLIER_THRESHOLD:
        return 3
    if abs_z >= 2.0:
        return 2
    if abs_z >= 1.0:
        return 1
    return 0


def _directional_ratio(current: float, p50: float, direction: str) -> float:
    """Direction-aware ratio for the multiplier rule.

    "high" metrics anomalies are spikes (current/p50). "low" metrics
    anomalies are drops (p50/current). Epsilon-guarded against div-by-zero.
    """
    eps = 1e-9
    if direction == "low":
        return (p50 / max(current, eps)) if p50 > 0 else 0.0
    return (current / p50) if p50 > 0 else 0.0


def _direction_for(metric_name: str) -> str:
    spec = _COLD_START_CEILINGS.get(metric_name)
    if spec is None:
        return "high"
    return spec[1]


async def _last_band_for(conn, metric_name: str, lookback_days: int = 14) -> int:
    """Most recent L3 band recorded for `metric_name`. Used for
    threshold-crossing dedup so an 8-day drift in band 1 only writes once."""
    row = await conn.fetchrow(
        """
        SELECT detail FROM mi_audit_log
        WHERE event_type = $1
          AND detail LIKE $2
          AND created_at >= NOW() - ($3 || ' days')::INTERVAL
        ORDER BY created_at DESC LIMIT 1
        """,
        _AUDIT_EVENT, f'%"key": "{metric_name}"%', str(lookback_days),
    )
    if not row:
        return 0
    try:
        payload = json.loads(row["detail"] or "{}")
        return int(payload.get("to_band", 0))
    except (ValueError, TypeError):
        return 0


async def _compute_anomaly(
    conn,
    metric: MetricSpec,
    current_regime: str | None,
    recent_changes: list[str],
    recent_events: list[str],
    *,
    as_of: date | None = None,
) -> Anomaly | None:
    """Decide L1/L2/L3 (or no-op) for `metric` given today's value vs
    baseline, with cold-start tiering, MAD<1 fallback, and regime-conditional
    swap. Caller handles dedup + Telegram + persistence.

    `as_of` pins the baseline to a historical date — used by the
    --baseline-as-of backfill harness so today's spike isn't already in the
    reference distribution.
    """
    current = await metric.fetch_today(conn)
    # None signals "denominator too small / not informative today" — skip
    # both sample recording (would pollute the baseline) and anomaly check.
    if current is None:
        return None
    # Always record the daily sample so future baselines have it.
    await _record_metric_sample(metric.name, current)

    baseline = await get_metric_baseline(metric.name, as_of_date=as_of)

    # Regime-conditional swap (NOT muting): in Crisis, compare against a
    # Crisis-only baseline so a stuck-Crisis regime doesn't blind us to a
    # scanner crash. Falls back to the global baseline if the regime sample
    # is too small.
    if (
        current_regime
        and current_regime.lower() == "crisis"
        and metric.name in _REGIME_CONDITIONAL_METRICS
    ):
        regime_b = await _regime_conditional_baseline(conn, metric, current_regime)
        if regime_b is not None:
            p50, p95, mad, n = regime_b
            baseline = {"p50": p50, "p95": p95, "mad": mad, "sample_n": n,
                        "regime_conditional": True}

    sample_n = (baseline or {}).get("sample_n", 0)
    p50 = (baseline or {}).get("p50", 0.0) or 0.0
    mad = (baseline or {}).get("mad", 0.0) or 0.0
    direction = _direction_for(metric.name)

    # Cold-start gate.
    if sample_n < _WARMING_MIN:
        spec = _COLD_START_CEILINGS.get(metric.name)
        if spec is None:
            return None  # no defined floor/ceiling — wait for warm-up
        threshold, dir_ = spec
        breached = (current > threshold) if dir_ == "high" else (current < threshold)
        if breached:
            cmp = ">" if dir_ == "high" else "<"
            return Anomaly(2, metric.name, {
                "current": current,
                "baseline_p50": p50, "baseline_p95": (baseline or {}).get("p95"),
                "mad": mad, "sample_n": sample_n,
                "rule": f"cold_start ({dir_}): current {current} {cmp} threshold {threshold}",
            })
        return None

    # Warming tier: compute but only emit L3 (silent).
    warming = sample_n < _MIN_FULL_SAMPLE

    # MAD<1 fallback — z-score is meaningless on near-zero variance, so use
    # the multiplier rule alone.
    use_z = mad >= _MAD_FALLBACK_THRESHOLD
    z = ((current - p50) / mad) if use_z else 0.0
    ratio = _directional_ratio(current, p50, direction)
    band = _band_for(z, ratio)

    if band == 3 and not warming:
        return Anomaly(2, metric.name, {
            "current": current,
            "baseline_p50": p50, "baseline_p95": (baseline or {}).get("p95"),
            "mad": mad, "sample_n": sample_n,
            "z_score": round(z, 2), "ratio": round(ratio, 2),
            "regime_conditional": (baseline or {}).get("regime_conditional", False),
        })

    # L3: drift band, threshold-crossing only.
    if band > 0:
        last_band = await _last_band_for(conn, metric.name)
        if band == last_band:
            return None  # steady drift within same band — already recorded
        return Anomaly(3, metric.name, {
            "current": current,
            "baseline_p50": p50, "mad": mad, "sample_n": sample_n,
            "z_score": round(z, 2), "ratio": round(ratio, 2),
            "from_band": last_band, "to_band": band,
            "warming": warming,
        })
    return None


# ── Formatters ───────────────────────────────────────────────────────────────


def _format_l1_alert(name: str, body: dict) -> str:
    summary = body.get("summary", "")
    offending = body.get("offending") or []
    drill = body.get("drill_sql", "")
    pointers = body.get("code_pointers") or []
    lines = [
        f"🚨 INVARIANT BREACH [L1] · {name}",
        "",
        summary,
    ]
    if offending:
        lines.append("")
        for s in offending[:6]:
            lines.append(f"  • {s}")
    if drill:
        lines.append("")
        lines.append("Drill-down:")
        lines.append(drill)
    if pointers:
        lines.append("")
        lines.append("Code pointers:")
        for p in pointers:
            lines.append(f"  {p}")
    return "\n".join(lines)


def _format_l2_alert(metric: MetricSpec, current: float, baseline: dict, hypothesis: str, body: dict) -> str:
    p50 = baseline.get("p50") or 0
    mad = baseline.get("mad") or 0
    z = body.get("z_score")
    ratio = body.get("ratio")
    regime_tag = " (regime-conditional)" if body.get("regime_conditional") else ""
    lines = [
        f"🟠 ANOMALY [L2] · {metric.name}{regime_tag}",
        "",
        f"Today: {current} · 30d median: {p50} · MAD: {mad}"
        + (f" · z={z}" if z is not None else "")
        + (f" · ratio={ratio}×" if ratio else ""),
        "",
        f"Hypothesis: {hypothesis or '(none)'}",
        "",
        "Drill-down:",
        metric.drill_sql,
    ]
    if metric.code_pointers:
        lines.append("")
        lines.append("Code pointers:")
        for p in metric.code_pointers:
            lines.append(f"  {p}")
    return "\n".join(lines)


# ── Persistence + Telegram ───────────────────────────────────────────────────


async def _emit_l1(name: str, body: dict) -> None:
    if await count_today_anomalies(name) > 0:
        return
    text = _format_l1_alert(name, body)
    await log_audit_event(
        _AUDIT_EVENT,
        summary=f"L1 {name}",
        detail=json.dumps({
            "level": 1, "key": name,
            "summary": body.get("summary"),
            "count": body.get("count"),
            "drill_sql": body.get("drill_sql"),
            "code_pointers": body.get("code_pointers"),
            "offending": (body.get("offending") or [])[:6],
        }),
    )
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(text)
    except Exception:
        logger.exception(f"system_audit: L1 Telegram send failed for {name} (audit row written)")


async def _emit_l2(metric: MetricSpec, anomaly: Anomaly, hypothesis: str) -> None:
    if await count_today_anomalies(metric.name) > 0:
        return
    baseline = {
        "p50": anomaly.body.get("baseline_p50"),
        "mad": anomaly.body.get("mad"),
    }
    text = _format_l2_alert(metric, anomaly.body["current"], baseline, hypothesis, anomaly.body)
    await log_audit_event(
        _AUDIT_EVENT,
        summary=f"L2 {metric.name}",
        detail=json.dumps({
            "level": 2, "key": metric.name,
            "current": anomaly.body.get("current"),
            "baseline_p50": anomaly.body.get("baseline_p50"),
            "baseline_p95": anomaly.body.get("baseline_p95"),
            "mad": anomaly.body.get("mad"),
            "sample_n": anomaly.body.get("sample_n"),
            "z_score": anomaly.body.get("z_score"),
            "ratio": anomaly.body.get("ratio"),
            "regime_conditional": anomaly.body.get("regime_conditional", False),
            "hypothesis": hypothesis,
            "drill_sql": metric.drill_sql,
            "code_pointers": metric.code_pointers,
        }),
    )
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(text)
    except Exception:
        logger.exception(f"system_audit: L2 Telegram send failed for {metric.name} (audit row written)")


async def _emit_l3(metric: MetricSpec, anomaly: Anomaly) -> None:
    """L3 is audit-only — no Telegram. Sunday digest rolls these up."""
    await log_audit_event(
        _AUDIT_EVENT,
        summary=f"L3 {metric.name}",
        detail=json.dumps({
            "level": 3, "key": metric.name,
            "current": anomaly.body.get("current"),
            "baseline_p50": anomaly.body.get("baseline_p50"),
            "z_score": anomaly.body.get("z_score"),
            "ratio": anomaly.body.get("ratio"),
            "from_band": anomaly.body.get("from_band"),
            "to_band": anomaly.body.get("to_band"),
            "warming": anomaly.body.get("warming", False),
        }),
    )


# ── Drivers ──────────────────────────────────────────────────────────────────


async def _check_invariants(conn, *, since: date, since_dt: datetime, now_et: datetime) -> int:
    """Run the L1 invariant sweep. Returns count of breaches Telegram-fired."""
    fired = 0
    for name, fn, kwargs in all_invariants(since=since, since_dt=since_dt, now_et=now_et):
        try:
            ok, body = await fn(conn, **kwargs)
        except Exception as e:
            logger.exception(f"system_audit: invariant {name} raised: {e}")
            continue
        if not ok:
            await _emit_l1(name, body)
            fired += 1
    return fired


async def _scan_metrics(
    conn,
    metrics: list[MetricSpec],
    current_regime: str | None,
    *,
    as_of: date | None = None,
) -> tuple[int, int, int]:
    """Run the L2/L3 metric sweep over `metrics`. Returns (l1, l2, l3) counts.
    L1 is always 0 here — invariants own L1."""
    recent_changes = _recent_changes_context()
    recent_events = await _recent_audit_event_types(conn)

    l2_count = 0
    l3_count = 0
    for metric in metrics:
        try:
            anomaly = await _compute_anomaly(
                conn, metric, current_regime, recent_changes, recent_events,
                as_of=as_of,
            )
        except Exception:
            logger.exception(f"system_audit: metric {metric.name} failed")
            continue
        if anomaly is None:
            continue
        if anomaly.level == 2:
            hypothesis = await _synthesize_hypothesis(
                metric.name, anomaly.body["current"],
                {"p50": anomaly.body.get("baseline_p50"),
                 "mad": anomaly.body.get("mad"),
                 "sample_n": anomaly.body.get("sample_n")},
                recent_changes, recent_events,
            )
            await _emit_l2(metric, anomaly, hypothesis)
            l2_count += 1
        elif anomaly.level == 3:
            await _emit_l3(metric, anomaly)
            l3_count += 1
    return (0, l2_count, l3_count)


async def _current_regime(conn) -> str | None:
    row = await conn.fetchrow(
        "SELECT regime FROM mi_market_regime ORDER BY regime_date DESC LIMIT 1"
    )
    return (row["regime"] if row else None) or None


async def run_post_eod_audit(*, baseline_as_of: date | None = None) -> dict:
    """16:15 ET — invariants + trade-side metrics."""
    today = et_today()
    since = today - timedelta(days=_BASELINE_LOOKBACK_DAYS)
    since_dt = datetime.combine(since, datetime.min.time())
    pool = await get_pool()
    async with pool.acquire() as conn:
        l1 = await _check_invariants(conn, since=since, since_dt=since_dt, now_et=datetime.now(_ET))
        regime = await _current_regime(conn)
        _, l2, l3 = await _scan_metrics(conn, _TRADE_METRICS, regime, as_of=baseline_as_of)
    summary = {"job": "post_eod", "l1": l1, "l2": l2, "l3": l3}
    logger.info(f"system_audit (post_eod): {l1} L1, {l2} L2, {l3} L3 drift")
    return summary


async def run_post_nightly_audit(*, baseline_as_of: date | None = None) -> dict:
    """17:30 ET — theme/cooldown/regime metrics.

    `baseline_as_of` pins the historical baseline date (used for the
    2026-04-24 backfill verification — see the verification section of the
    plan). When None, uses the latest baseline row (today).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        regime = await _current_regime(conn)
        _, l2, l3 = await _scan_metrics(conn, _NIGHTLY_METRICS, regime, as_of=baseline_as_of)
    summary = {"job": "post_nightly", "l1": 0, "l2": l2, "l3": l3}
    logger.info(f"system_audit (post_nightly): 0 L1, {l2} L2, {l3} L3 drift")
    return summary


async def _run_job_runs_report(window_hours: int = 24) -> str:
    """Build the `/audit job_runs` text report from `mi_job_runs`.

    Sections: status counts, empty_result/failed details, slowest 5 jobs vs
    their 30d p95. Returns plain text; caller wraps for Telegram.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        status_counts = await conn.fetch(
            """
            SELECT status, COUNT(*) AS n
            FROM mi_job_runs
            WHERE started_at >= NOW() - ($1 || ' hours')::INTERVAL
            GROUP BY status ORDER BY status
            """,
            str(window_hours),
        )
        problem_rows = await conn.fetch(
            """
            SELECT job_id, started_at, status, rows_written,
                   expected_min_rows, error_message
            FROM mi_job_runs
            WHERE started_at >= NOW() - ($1 || ' hours')::INTERVAL
              AND status IN ('failed', 'empty_result')
            ORDER BY started_at DESC LIMIT 20
            """,
            str(window_hours),
        )
        slowest = await conn.fetch(
            """
            WITH recent AS (
                SELECT job_id, duration_s
                FROM mi_job_runs
                WHERE started_at >= NOW() - ($1 || ' hours')::INTERVAL
                  AND duration_s IS NOT NULL AND status = 'success'
            ),
            baseline AS (
                SELECT job_id,
                       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_s) AS p95_30d
                FROM mi_job_runs
                WHERE started_at >= NOW() - INTERVAL '30 days'
                  AND duration_s IS NOT NULL AND status = 'success'
                GROUP BY job_id
            )
            SELECT r.job_id, r.duration_s, b.p95_30d
            FROM recent r LEFT JOIN baseline b USING (job_id)
            ORDER BY r.duration_s DESC LIMIT 5
            """,
            str(window_hours),
        )

    counts = {r["status"]: r["n"] for r in status_counts}
    total = sum(counts.values())
    parts = [f"Job runs (last {window_hours}h): {total} total"]
    if total:
        parts.append("  " + " / ".join(f"{n} {s}" for s, n in counts.items()))
    if problem_rows:
        parts.append("")
        parts.append("⚠️ Problem runs:")
        for r in problem_rows:
            ts = r["started_at"].strftime("%m-%d %H:%M")
            if r["status"] == "empty_result":
                parts.append(
                    f"  {ts} {r['job_id']}: {r['rows_written'] or 0} rows "
                    f"(expected ≥ {r['expected_min_rows']})"
                )
            else:
                err = (r["error_message"] or "")[:120]
                parts.append(f"  {ts} {r['job_id']} FAILED: {err}")
    if slowest:
        parts.append("")
        parts.append("Slowest runs:")
        for r in slowest:
            d = float(r["duration_s"] or 0)
            p95 = r["p95_30d"]
            if p95:
                parts.append(f"  {r['job_id']}: {d:.1f}s vs p95 {float(p95):.1f}s")
            else:
                parts.append(f"  {r['job_id']}: {d:.1f}s (no 30d baseline yet)")
    return "\n".join(parts)


async def run_topic_audit(topic: str, *, baseline_as_of: date | None = None) -> dict:
    """`/audit <topic>` ad-hoc entry. Same scan logic, scoped to topic."""
    topic_lower = topic.lower()
    if topic_lower == "job_runs":
        report = await _run_job_runs_report()
        return {"job": "topic:job_runs", "report": report, "l1": 0, "l2": 0, "l3": 0}
    metrics = _TOPIC_MAP.get(topic_lower)
    if metrics is None:
        valid = sorted(list(_TOPIC_MAP.keys()) + ["job_runs"])
        return {"error": f"unknown topic '{topic}'", "valid": valid}
    today = et_today()
    since = today - timedelta(days=_BASELINE_LOOKBACK_DAYS)
    since_dt = datetime.combine(since, datetime.min.time())
    pool = await get_pool()
    async with pool.acquire() as conn:
        l1 = 0
        if topic == "all":
            l1 = await _check_invariants(conn, since=since, since_dt=since_dt, now_et=datetime.now(_ET))
        regime = await _current_regime(conn)
        _, l2, l3 = await _scan_metrics(conn, metrics, regime, as_of=baseline_as_of)
    return {"job": f"topic:{topic}", "l1": l1, "l2": l2, "l3": l3}


# ── CLI entry for backfill harness ──────────────────────────────────────────


def _cli() -> None:
    """`python -m agents.market_intelligence.system_audit` driver.

    Used by the 2026-04-24 backfill verification:
        python -m agents.market_intelligence.system_audit \\
            --job nightly --baseline-as-of 2026-04-23
    """
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--job", choices=["eod", "nightly", "topic", "baseline"], required=True)
    p.add_argument("--topic", default="all", help="when --job=topic")
    p.add_argument("--baseline-as-of", type=str, default=None,
                   help="YYYY-MM-DD; pin baseline to this historical date")
    args = p.parse_args()

    as_of = date.fromisoformat(args.baseline_as_of) if args.baseline_as_of else None

    async def _go():
        if args.job == "eod":
            r = await run_post_eod_audit(baseline_as_of=as_of)
        elif args.job == "nightly":
            r = await run_post_nightly_audit(baseline_as_of=as_of)
        elif args.job == "topic":
            r = await run_topic_audit(args.topic, baseline_as_of=as_of)
        else:
            await run_baseline_refresh()
            r = {"job": "baseline_refresh", "ok": True}
        print(json.dumps(r, default=str, indent=2))

    asyncio.run(_go())


if __name__ == "__main__":
    _cli()
