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
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


from agents.market_intelligence.audit_invariants import all_invariants
from agents.market_intelligence.collector import et_today
from agents.market_intelligence.trading_calendar import get_market_status
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
    # T2c judge drift metrics (2026-07-12): generous by design — the band takes
    # over at n>=14 days; these only catch egregious day-one drift.
    "judge_high_rate_daily":          (0.85, "high"),
    "judge_demote_share_daily":       (0.90, "high"),
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
# Drift-vs-spike guard (2026-06-15): a STABLE metric (MAD tiny vs its median) drifting
# slowly past its 30d median produces a large z on a TINY day-to-day step — that is DRIFT
# (L3, weekly digest), not a sudden anomaly (L2 Telegram). So an L2-via-z (NOT via the 5×
# ratio rule) on such a metric also requires a minimum MATERIALITY; else it downgrades to L3.
# Calibrated on theme_count_active: MAD 1 on median 44 (2.3%) = a slow 55→38 decline,
# max daily step 5, that was firing daily L2 on z=−6. The 5× ratio rule + cold-start ceiling
# still catch genuine collapses, so this never hides a real drop.
_TIGHT_MAD_FRAC = 0.05         # MAD < 5% of median ⇒ a "stable" metric (z on a tiny step = drift)
_MIN_L2_MATERIALITY = 0.20     # …so its L2-via-z also needs ≥20% deviation from median

_AUDIT_EVENT = "anomaly_detected"

# Note (2026-05-15): the prior Sonnet-based hypothesis was removed in favor
# of raw audit-event-delta facts. See `_top_event_deltas` below. Today's
# wrong attribution (cooldowns spike blamed on splits) motivated the
# simplification — operator reads facts, no LLM inference.


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
    # `removed_at` is TIMESTAMPTZ and the container runs UTC, so both
    # `removed_at::date` and CURRENT_DATE resolve to the UTC day. The nightly
    # job fires 17:30 ET (same UTC date) so the metric was right in practice,
    # but an on-demand /audit after 8 PM ET read the NEXT day and returned 0.
    # ET-anchor both sides per the CLAUDE.md TIMESTAMPTZ rule.
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS n FROM mi_validation_cooldowns "
        "WHERE (removed_at AT TIME ZONE 'America/New_York')::date "
        "    = (now() AT TIME ZONE 'America/New_York')::date"
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


async def _today_market_hours_boots(conn) -> float:
    """Count container boots during regular market hours today (#147).

    A regular operator-deploy day will be 0 — deploys happen pre-market or
    post-market. Boots during 9:30–16:00 ET signal one of: emergency
    deploy, healthcheck restart, OOM kill, host event. Each one is a
    candidate for missing a scheduled cron tick (the 2026-05-26 10:04
    RDW failure shape)."""
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS n FROM mi_audit_log
        WHERE event_type = 'dual_account_boot_verified'
          AND (created_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE
          AND (created_at AT TIME ZONE 'America/New_York')::time
              BETWEEN '09:30' AND '16:00'
        """
    )
    return float(row["n"] or 0)


async def _judge_decision_rows_today(conn) -> list[dict]:
    """Today's ep_grade_decision payloads, parsed PYTHON-SIDE (mi_audit_log.detail
    is TEXT and can hold malformed rows — the ->>-in-SQL approach failed once,
    7/11 corpus mine). Malformed rows are SKIPPED, never crash the metric."""
    rows = await conn.fetch(
        """
        SELECT detail FROM mi_audit_log
        WHERE event_type = 'ep_grade_decision'
          AND (created_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE
        """
    )
    out = []
    for r in rows:
        try:
            d = json.loads(r["detail"]) if isinstance(r["detail"], str) else r["detail"]
            if isinstance(d, dict):
                out.append(d)
        except (ValueError, TypeError):
            continue
    return out


async def _today_judge_high_rate(conn) -> float | None:
    """T2c / premortem R5 (2026-07-11): the runtime drift tripwire for the judge —
    fraction of today's judge verdicts with tier=HIGH. The [5m/7] gate catches
    grade-surface changes at DEPLOY; this catches silent drift in PRODUCTION
    (model snapshot updates, corpus-mix shifts). NOT regime-conditional initially
    (establish the unconditional baseline first).

    N-floor (2026-07-20): None below _MIN_DETECTED_FOR_GATE decisions — a rate
    over a tiny denominator can't tell drift from a single legit game_changer
    (mirrors _today_high_entry_rate). The original 'no N-floor, 0→0.0' shape fired
    a false L2 on 2026-07-20: 2 decisions, BOTH the same HIGH game_changer EP (HUT)
    → rate 1.0 vs a median-0/MAD-0 baseline that was itself an artifact of the
    structural-zero no-decision days. Returning None skips the meaningless-rate
    alarm AND stops those structural zeros polluting the baseline — the 'promote
    only on evidenced false breaches' escalation this docstring anticipated."""
    rows = await _judge_decision_rows_today(conn)
    if len(rows) < _MIN_DETECTED_FOR_GATE:
        return None
    high = sum(1 for d in rows if d.get("judge_tier") == "HIGH")
    return high / len(rows)


async def _today_judge_demote_share(conn) -> float | None:
    """T2c sibling: share of today's judge verdicts with direction=demote — the
    OVER-SKEPTICISM drift direction (the D08/positive-control failure mode, live).
    Same N-floor as _today_judge_high_rate (2026-07-20): None below
    _MIN_DETECTED_FOR_GATE decisions — a share over a tiny denominator is noise."""
    rows = await _judge_decision_rows_today(conn)
    if len(rows) < _MIN_DETECTED_FOR_GATE:
        return None
    demote = sum(1 for d in rows if d.get("judge_direction") == "demote")
    return demote / len(rows)


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
    MetricSpec(
        # Market-hours container boots (#147, 2026-05-28). The 2026-05-26
        # 10:04:31 ET unexplained restart misfired the 10:00 cron tick that
        # would have cancelled RDW's stuck pending_new. Defensive metric:
        # baseline + L2 detection so the NEXT mid-market-hours restart is
        # surfaced immediately instead of being noticed via downstream
        # symptoms days later.
        "market_hours_boot_count", _today_market_hours_boots,
        "SELECT created_at AT TIME ZONE 'America/New_York' AS et "
        "FROM mi_audit_log "
        "WHERE event_type = 'dual_account_boot_verified' "
        "  AND (created_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE "
        "  AND (created_at AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '16:00' "
        "ORDER BY created_at;",
        ["docker-compose / host healthcheck / OOM kills"],
    ),
    MetricSpec(
        "judge_high_rate_daily", _today_judge_high_rate,
        "SELECT created_at, detail FROM mi_audit_log "
        "WHERE event_type='ep_grade_decision' "
        "  AND (created_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE "
        "ORDER BY created_at DESC;",
        ["agents/market_intelligence/ep_grade_judge.py",
         "agents/market_intelligence/ep_detector.py::_emit_grade_decision"],
    ),
    MetricSpec(
        "judge_demote_share_daily", _today_judge_demote_share,
        "SELECT created_at, detail FROM mi_audit_log "
        "WHERE event_type='ep_grade_decision' "
        "  AND (created_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE "
        "ORDER BY created_at DESC;",
        ["agents/market_intelligence/ep_grade_judge.py",
         "agents/market_intelligence/ep_detector.py::_emit_grade_decision"],
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
            -- #482/#216: rows whose path was fabricated by the 2026-08-17
            -- freeze-resume (one daily step across ~75 missed sessions) are
            -- marked, not deleted. They must never enter an evidence read.
            AND NOT shadow.quarantined
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
        "    AND shadow.status='closed' AND live.status='closed' "
        "    AND NOT shadow.quarantined) "
        "SELECT * FROM paired ORDER BY alert_date DESC;",
        ["agents/market_intelligence/broker/exit_logic.py::apply_daily_exit_step"],
    ),
]


_NIGHTLY_METRICS: list[MetricSpec] = [
    MetricSpec(
        "cooldowns_per_day", _today_cooldowns,
        # ET-anchored to match _today_cooldowns — this string is pasted into the
        # Telegram anomaly alert and run by hand, often late ET, where a
        # UTC CURRENT_DATE silently returns the next day (i.e. zero rows).
        "SELECT theme_name, COUNT(*) FROM mi_validation_cooldowns "
        "WHERE (removed_at AT TIME ZONE 'America/New_York')::date "
        "    = (now() AT TIME ZONE 'America/New_York')::date "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 15;",
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

_ALL_METRICS = _TRADE_METRICS + _NIGHTLY_METRICS + _SHADOW_ORB_METRICS

_TOPIC_MAP: dict[str, list[MetricSpec]] = {
    "cooldowns":  [m for m in _ALL_METRICS if m.name == "cooldowns_per_day"],
    "themes":     [m for m in _ALL_METRICS if m.name in {"theme_count_active", "cooldowns_per_day", "accel_dropout_count_7d"}],
    "skips":      [m for m in _ALL_METRICS if m.name.startswith("skip_count_")],
    "positions":  [m for m in _ALL_METRICS if m.name in {"HIGH_ep_entry_rate"}],
    "feed":       [m for m in _ALL_METRICS if m.name in {"bar_stream_disconnect_count_24h", "skip_count_infra"}],
    "9m":         [m for m in _ALL_METRICS if m.name == "9m_alerts_per_day"],
    "shadow_orb": _SHADOW_ORB_METRICS,
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


def _values_from_metric_sample_rows(rows) -> list[float]:
    """Parse `metric_sample` audit rows → list of numeric values. Defense in
    depth: drops samples whose `as_of` falls on a non-trading day so older
    history written before the holiday-gate landed can't contaminate the
    baseline (#120)."""
    out: list[float] = []
    for r in rows:
        try:
            payload = json.loads(r["detail"] or "{}")
            v = payload.get("value")
            if v is None:
                continue
            as_of_str = payload.get("as_of")
            if as_of_str:
                try:
                    if _is_non_trading_day(date.fromisoformat(as_of_str)):
                        continue
                except (ValueError, TypeError):
                    pass
            out.append(float(v))
        except (ValueError, TypeError):
            continue
    return out


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
    return _values_from_metric_sample_rows(rows)


def _is_non_trading_day(d: date) -> bool:
    """Wraps trading_calendar.get_market_status as a holiday-aware skip gate
    for the L2/L3 anomaly detector. Returns True on weekends + market holidays.

    Used to avoid recording structurally-zero samples on closed days and to
    short-circuit the classifier — a baseline trained on Memorial Day's 0
    fires false-positive L2 the next trading day (#120). exchange_calendars
    is the same source used by trading_calendar; failure path is fail-open
    (treat as trading day) so genuine breakage still alerts.
    """
    try:
        return not get_market_status(d).is_trading_day
    except Exception as e:
        logger.warning(f"_is_non_trading_day({d}) failed: {e}; treating as trading day")
        return False


async def _record_metric_sample(metric_name: str, value: float) -> None:
    """Persist today's value as a `metric_sample` audit event so future
    baseline refreshes can compute against history without re-running every
    metric query for every historical day.

    Skips on non-trading days (#120, 2026-05-26) so a 0-value Memorial Day
    doesn't contaminate the 30d trimmed-median baseline.
    """
    today = et_today()
    if _is_non_trading_day(today):
        logger.debug(
            f"_record_metric_sample skipped for {metric_name}: {today} non-trading"
        )
        return
    await log_audit_event(
        "metric_sample",
        summary=metric_name,
        detail=json.dumps({"value": float(value), "as_of": str(today)}),
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
    values = _values_from_metric_sample_rows(rows)
    if len(values) < _REGIME_BASELINE_DAYS:
        return None
    return _trimmed_median_mad(values)


# ── Recent context (for Sonnet hypothesis injection) ─────────────────────────


_CLAUDEMD_HEADER_RE = re.compile(
    r"^### (\d{4}-\d{2}-\d{2})(?:\s*\([^)]+\))?\s*(?:—\s*)?(.*)$",
    re.MULTILINE,
)


def _recent_changes_context(repo_root: Path | None = None, limit: int = 5) -> list[str]:
    """Last N `### YYYY-MM-DD` change entries from CLAUDE.md "Changes Made
    — Recent" section. Each entry's header line is captured (date + the
    title text after the em-dash). Used to ground the Sonnet hypothesis
    call AND the L3 drift "may be intentional" disambiguation (#112) in
    what the user actually shipped recently.

    Pre-2026-05-24 the regex looked for "## Changes Made YYYY-MM-DD" which
    didn't match the actual CLAUDE.md format ("### YYYY-MM-DD (Day) — title").
    Returned empty list silently; downstream hypothesis calls got no
    recent context. Fixed in #112.
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
        title = m.group(2).strip()
        # Header alone is usually informative enough. If empty, fall back
        # to the next non-blank body line (older entries without em-dash titles).
        if not title:
            body_start = m.end()
            snippet = text[body_start: body_start + 250].strip().splitlines()
            title = next(
                (s.strip("# ").strip() for s in snippet if s.strip() and not s.startswith("##")),
                "",
            )
        out.append(f"{date_str}: {title[:120]}")
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


async def _today_skip_breakdown(conn) -> str:
    """Today's mi_live_trades skip_reason category counts — context for the
    Sonnet hypothesis call. Without this, hypotheses on entry-rate / skip
    metrics fire blind and tend to over-correlate with whatever audit-event
    type happens to be loud (e.g. 5/8 wrongly blamed split_apply_failed=190
    for HIGH_ep_entry_rate=0 when the actual cause was 4 circuit_breaker +
    5 out_of_orb skips). Returns "(none)" on quiet days.
    """
    rows = await conn.fetch(
        """
        SELECT split_part(skip_reason, ':', 1) AS cat, COUNT(*) AS n
        FROM mi_live_trades
        WHERE alert_date = CURRENT_DATE
          AND status = 'skipped'
          AND skip_reason IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC
        """
    )
    if not rows:
        return "(none)"
    return ", ".join(f"{r['cat']}={r['n']}" for r in rows)


async def _today_skip_top_reasons(conn, limit: int = 5) -> str:
    """Top N skip_reason prefixes today, with up-to-3 sample tickers each.
    Distinguishes block:max_positions vs block:circuit_breaker etc. — the
    level the operator typically wants for triage."""
    rows = await conn.fetch(
        """
        SELECT
            split_part(skip_reason, ':', 1) || ':' || split_part(skip_reason, ':', 2) AS prefix,
            COUNT(*) AS n,
            (array_agg(ticker ORDER BY ticker))[1:3] AS sample_tickers
        FROM mi_live_trades
        WHERE alert_date = CURRENT_DATE
          AND status = 'skipped'
          AND skip_reason IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC LIMIT $1
        """,
        limit,
    )
    if not rows:
        return "(none)"
    parts = []
    for r in rows:
        sample = ",".join(r["sample_tickers"] or [])
        parts.append(f"{r['prefix']}={r['n']} [{sample}]")
    return "; ".join(parts)


# ── Sonnet hypothesis ────────────────────────────────────────────────────────


async def _top_event_deltas(
    conn, top_n: int = 3, window_days: int = 14,
) -> list[dict]:
    """Return the top N audit event types whose 24h count today most
    exceeds their trailing window_days trimmed-median baseline.

    Replaces the prior `_synthesize_hypothesis` Sonnet call (2026-05-15).
    Today's L2 anomaly had a wrong LLM hypothesis (attributed
    cooldowns_per_day=13 spike to splits when the actual cause was theme
    assignment). Operator preferred raw facts over LLM guess — gets the
    same actionable signal without the LLM failure mode.

    Returns: list of {event_type, today_count, baseline_median, ratio,
    is_new} sorted by ratio (highest first). is_new=True when baseline=0
    (event hasn't fired in the window — clearer signal than infinite
    ratio).

    Reuses `_trimmed_median_mad` for baseline math. Uses `max(median, 0.5)`
    floor for ratio to avoid division-by-zero on rare events.
    """
    # Today's per-event counts (last 24h ET)
    today_rows = await conn.fetch("""
        SELECT event_type, COUNT(*)::int AS n
        FROM mi_audit_log
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY event_type
    """)
    if not today_rows:
        return []

    # Per-day counts over the trailing window, EXCLUDING last 24h so
    # today's spike doesn't contaminate its own baseline
    history_rows = await conn.fetch(f"""
        SELECT event_type,
               (created_at AT TIME ZONE 'America/New_York')::date AS day,
               COUNT(*)::int AS n
        FROM mi_audit_log
        WHERE created_at > NOW() - INTERVAL '{window_days} days'
          AND created_at <= NOW() - INTERVAL '24 hours'
        GROUP BY event_type, day
    """)

    history_by_type: dict[str, list[float]] = {}
    for row in history_rows:
        history_by_type.setdefault(row["event_type"], []).append(float(row["n"]))

    expected_days = max(window_days - 1, 1)

    results: list[dict] = []
    for row in today_rows:
        event_type = row["event_type"]
        today_n = row["n"]
        # Firing-day counts (one entry per day the event fired, pre-padding)
        firing_day_counts = history_by_type.get(event_type, [])
        firing_days = len(firing_day_counts)
        total_window_count = sum(firing_day_counts)

        # `is_new` should mean "truly never fired in the window", not
        # "median is zero". The latter triggers for sparse-firing events
        # (Mon/Wed/Fri theme validation, weekly cron jobs) that fire
        # regularly but on fewer than half the days. 2026-05-19 bug:
        # ticker_revalidated_out fired 129×/14d but reported as NEW
        # because median=0 from zero-pad dominating sparse firings.
        is_new = total_window_count == 0

        # Baseline: switch between median-of-all-days and
        # mean-of-firing-days based on firing density.
        # - Daily-ish event (fires on ≥half the days): trimmed median
        #   captures normal day-to-day variation; spike-detection works.
        # - Sparse event (Mon/Wed/Fri pattern, weekly cron): median is
        #   structurally 0 from zero-pad; use mean of firing days as
        #   "expected magnitude when it does fire" — today's count is
        #   anomalous only if it deviates from typical firing magnitude.
        sparse = firing_days < expected_days / 2 and firing_days > 0
        if sparse:
            baseline = total_window_count / firing_days
            baseline_label = "firing_day_mean"
        else:
            # Pad to expected_days for the median calculation. Padding
            # zeros is correct here — the event fires most days, so a
            # zero day IS a real signal of "below normal."
            padded = list(firing_day_counts)
            while len(padded) < expected_days:
                padded.append(0.0)
            p50, _, _, _ = _trimmed_median_mad(padded)
            baseline = p50
            baseline_label = "median"
        # Floor at 0.5 to handle zero-baseline events without div-by-zero
        # and to dampen the "infinite ratio" effect on very-rare events
        ratio = today_n / max(baseline, 0.5)
        results.append({
            "event_type": event_type,
            "today_count": today_n,
            "baseline_median": baseline,
            "baseline_label": baseline_label,
            "firing_days": firing_days,
            "window_total": int(total_window_count),
            "ratio": ratio,
            "is_new": is_new,
        })

    results.sort(key=lambda r: (r["ratio"], r["today_count"]), reverse=True)
    return results[:top_n]


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


def _is_slow_drift(band: int, ratio: float, mad: float, p50: float, current: float) -> bool:
    """True when a band-3 (L2) fire is actually slow DRIFT on a STABLE metric, not a spike:
    the MAD is tiny vs the median (so a large z rides a tiny day-to-day step) AND the move
    is immaterial in % terms AND it did NOT fire via the 5× ratio rule. Such a fire belongs
    in L3 (drift, weekly digest), not L2 (Telegram). Pure → unit-tested. (2026-06-15:
    theme_count_active, MAD 1 on median 44, a 55→38 slow decline mis-firing daily L2.)"""
    return (
        band == 3
        and ratio < _MULTIPLIER_THRESHOLD                   # not a 5× collapse/spike
        and p50 > 0 and mad > 0
        and (mad / p50) < _TIGHT_MAD_FRAC                    # stable metric
        and (abs(current - p50) / p50) < _MIN_L2_MATERIALITY  # immaterial % move
    )


def _directional_ratio(current: float, p50: float, direction: str) -> float:
    """Direction-aware ratio for the multiplier rule.

    "high" metrics anomalies are spikes (current/p50). "low" metrics
    anomalies are drops (p50/current). Epsilon-guarded against div-by-zero.
    """
    eps = 1e-9
    if direction == "low":
        return (p50 / max(current, eps)) if p50 > 0 else 0.0
    return (current / p50) if p50 > 0 else 0.0


# Band value the slow-drift downgrade routes to: must be >0 (so it reaches the L3
# threshold-crossing record) and != 3 (so it skips the L2 emit). Names the bare `2`.
_BAND_L3_DRIFT = 2


def _classify_band(
    current: float, p50: float, mad: float, direction: str
) -> tuple[int, float, float]:
    """The complete band-routing path used by `_compute_anomaly`: MAD<1 z-fallback ->
    directional ratio -> `_band_for` -> slow-drift L2->L3 downgrade. Returns (band, z, ratio).
    SINGLE source of the routing so the drift-guard test pins the REAL path, not a hand-synced
    replica (extracted 2026-06-15 /simplify — the test previously re-implemented this loop)."""
    use_z = mad >= _MAD_FALLBACK_THRESHOLD
    z = ((current - p50) / mad) if use_z else 0.0
    ratio = _directional_ratio(current, p50, direction)
    band = _band_for(z, ratio)
    if _is_slow_drift(band, ratio, mad, p50, current):
        band = _BAND_L3_DRIFT  # slow drift on a stable metric -> L3 drift path, not L2
    return band, z, ratio


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


def _persistent_l2_downgrade(band: int, last_band: int, *, mad: float, p50: float, ratio: float) -> bool:
    """A persisting band-3 (L2) that should fire ONCE on the transition, then quiet — the
    PERSISTENCE axis (`_is_slow_drift` is the MAGNITUDE axis). A benign-but-material level shift
    can sit in band 3 for days as its 30d median catches up — e.g. theme_count_active −32% across
    the 2026-06-21 Choppy regime fired L2 four nights running.

    SCOPE (advisor 2026-06-21): ONLY the stable (tight-MAD), non-collapse class is deduped — the
    same class `_is_slow_drift` targets, MINUS its immateriality clause (here the move IS material,
    which is why it reaches L2 at all). A genuine spike/collapse (≥5× ratio) or a HIGH-VARIANCE
    metric's persistent breach KEEPS re-firing daily — you want the day-2 nag on a real pipeline
    failure / stream disconnect (HIGH_ep_entry_rate, bar_stream_disconnect), not one-and-done.
    Downgrades to L3 (audit-only, weekly digest); mirrors the L3 same-band dedup. Requires
    `to_band` on the L2 payload so `_last_band_for` sees yesterday's band 3."""
    if band != 3 or last_band != 3:
        return False
    stable = p50 > 0 and mad > 0 and (mad / p50) < _TIGHT_MAD_FRAC
    not_collapse = ratio < _MULTIPLIER_THRESHOLD
    return stable and not_collapse


async def _recent_window_stable(conn, metric: "MetricSpec", days: int = 10) -> bool:
    """Settled level-shift detector (#352 fix-2). The full-window (30d) MAD can be wide ONLY
    because the baseline window spans a STRUCTURAL shift — e.g. theme_count_active across the
    #286 universe cut + the #325 decline — which trips the `stable` gate in
    `_persistent_l2_downgrade` (mad/p50 grows as the metric declines) so a persisting band-3
    keeps re-firing L2 forever. A TIGHT *recent* window means the metric has SETTLED at a new
    normal, not that it's still drifting. Returns True iff ≥5 recent samples and
    recent_mad/recent_p50 < _TIGHT_MAD_FRAC. Safety: a stuck-at-zero outage has recent_p50==0
    (not stable → keeps alerting); a spike/collapse has a wide recent window (not stable)."""
    recent = await _fetch_history(conn, metric, lookback_days=days)
    if len(recent) < 5:
        return False
    rp50, _, rmad, _ = _trimmed_median_mad(recent)
    return rp50 > 0 and rmad > 0 and (rmad / rp50) < _TIGHT_MAD_FRAC


async def _compute_anomaly(
    conn,
    metric: MetricSpec,
    current_regime: str | None,
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
    # Non-trading-day short-circuit (#120, 2026-05-26): structurally-zero
    # values on holidays/weekends are not anomalies. Skip fetch + record +
    # classify entirely. The `as_of` arg pins to a historical date (backfill
    # harness) so honor that when present; otherwise check today.
    check_date = as_of if as_of is not None else et_today()
    if _is_non_trading_day(check_date):
        logger.debug(
            f"_compute_anomaly skipped for {metric.name}: {check_date} non-trading"
        )
        return None

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

    # Band routing — MAD<1 z-fallback, directional ratio, _band_for, and the slow-drift
    # L2->L3 downgrade — all live in _classify_band (the SINGLE source the drift-guard test pins).
    band, z, ratio = _classify_band(current, p50, mad, direction)

    if band == 3 and not warming:
        last_band = await _last_band_for(conn, metric.name)
        detail = {
            "current": current,
            "baseline_p50": p50, "baseline_p95": (baseline or {}).get("p95"),
            "mad": mad, "sample_n": sample_n,
            "z_score": round(z, 2), "ratio": round(ratio, 2),
            "regime_conditional": (baseline or {}).get("regime_conditional", False),
            "to_band": band,  # 3 — recorded so _last_band_for can dedup a persisting L2
        }
        persistent = _persistent_l2_downgrade(band, last_band, mad=mad, p50=p50, ratio=ratio)
        # Settled level-shift (#352 fix-2): when a persisting band-3's full-window MAD is wide
        # only because the 30d baseline spans a structural shift (#286 cut + #325 decline), the
        # stable gate above misses it — but a tight RECENT window means it has settled at a new
        # normal. Quiet it the same way. (A stuck-at-zero outage or a spike is NOT recent-stable
        # → keeps alerting.) Only applies to a PERSISTING band-3 (last_band==3); the transition
        # INTO band-3 still fires L2 once.
        settled = (
            last_band == 3
            and ratio < _MULTIPLIER_THRESHOLD
            and await _recent_window_stable(conn, metric)
        )
        if persistent or settled:
            # Already alerted on the transition INTO band 3; a persisting/settled band 3 logs L3
            # (audit-only, weekly digest) instead of re-firing the Telegram every nightly run.
            detail["from_band"] = last_band
            detail["warming"] = warming
            detail["persistent_l2_downgrade"] = True
            detail["settled_level_shift"] = bool(settled)
            return Anomaly(3, metric.name, detail)
        return Anomaly(2, metric.name, detail)

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


def _format_naked_position_alert(body: dict) -> str:
    """Render naked-position L1 alert with DB-drift vs real-naked partition.

    Spec (#140, 2026-05-28):
      - 🚨 NAKED POSITION (real $ risk): broker has NO stop order
      - ⚠️ DB-DRIFT (operational): broker HAS a stop order; Apollo's DB
        just lost track of stop_order_id

    Real-naked is the original severe alert. DB-drift is a quieter
    operational warning prompting sync_positions reconciliation, not
    emergency intervention.
    """
    real_naked = body.get("real_naked") or []
    db_drift = body.get("db_drift") or []
    drill = body.get("drill_sql", "")

    sections = []
    if real_naked:
        sections.append(
            f"🚨 *NAKED POSITION [L1]* — broker confirms NO stop order "
            f"({len(real_naked)} rows)"
        )
        sections.append("")
        sections.append("These positions have real $ exposure with no broker-side stop:")
        for r in real_naked[:6]:
            # Backtick the row — alert_date=/filled_at= are underscore identifiers, same
            # Markdown-italics break class as _format_l1_alert (2026-08-17 fix).
            sections.append(
                f"  • `{r.get('ticker')} alert_date={r.get('alert_date')} "
                f"filled_at={r.get('filled_at')}`"
            )
        sections.append("")
        # #507 (2026-07-28): the ask must match what the operator can actually
        # DO right now. Outside 09:00-16:00 ET a stop cannot execute anyway, and
        # the stop-ack watchdog (cron hour="9-15") auto-replaces at 09:00 —
        # before the open. On 2026-07-27 this alarm fired at 16:28 demanding
        # "immediate action" on a position that was never at risk and would have
        # been covered automatically; the operator placed one by hand for
        # nothing. Detection was right; the INSTRUCTION was wrong.
        # Still surfaced either way — silence would be worse — but the after-
        # hours form says what is true instead of manufacturing urgency.
        _now_et = datetime.now(_ET)
        _market_hours = (_now_et.weekday() < 5 and time(9, 30) <= _now_et.time() <= time(16, 0))
        if _market_hours:
            sections.append("Immediate operator action: place stop via Alpaca web UI.")
        else:
            sections.append(
                "⏸️ Outside market hours — a stop cannot execute now, and the "
                "stop-ack watchdog auto-replaces at 9:00 AM ET, before the open. "
                "No action needed unless it is still bare after 9:00."
            )

    if db_drift:
        if sections:
            sections.append("")
            sections.append("─" * 30)
            sections.append("")
        sections.append(
            f"⚠️ *DB-DRIFT [L1]* — broker has stop but Apollo's DB lost track "
            f"({len(db_drift)} rows)"
        )
        sections.append("")
        sections.append("These positions are broker-protected; only Apollo's DB is wrong:")
        for r in db_drift[:6]:
            sections.append(
                f"  • `{r.get('ticker')} alert_date={r.get('alert_date')}`"
            )
        sections.append("")
        sections.append(
            "Recovery: next `sync_positions` should re-attach the stop_order_id. "
            "No emergency intervention needed."
        )

    if drill:
        sections.append("")
        sections.append("Drill-down:")
        # Fence the SQL — same rationale as _format_l1_alert/_format_l2_alert: table/column
        # names here (mi_live_trades, stop_order_id, filled_at) are underscore identifiers.
        sections.append(f"```\n{drill}\n```")
    return "\n".join(sections)


def _format_l1_alert(name: str, body: dict) -> str:
    """Render L1 Telegram alert.

    All identifier-bearing content is backtick/fenced (2026-08-17 fix): every field here
    can carry underscore identifiers (invariant name, `'*_error'`-style summaries,
    `event_type: n` offending rows, table/column names in drill SQL, `module.py::func`
    code pointers) and Telegram Markdown treats a bare `_` as an italics delimiter. With
    plain interpolation, underscores across the WHOLE message pair up arbitrarily and get
    consumed as formatting — `silent_audit_error_window` rendered as `silentauditerrorwindow`
    and the drill SQL came through with every underscore stripped, unpasteable into psql.
    Same fix class as `_format_l2_alert` (metric name backticked, drill SQL fenced,
    #121) — L1 predates that fix and was never brought in line with it.
    """
    summary = body.get("summary", "")
    offending = body.get("offending") or []
    drill = body.get("drill_sql", "")
    pointers = body.get("code_pointers") or []
    lines = [
        f"🚨 INVARIANT BREACH [L1] · `{name}`",
        "",
        f"`{summary}`" if summary else summary,
    ]
    if offending:
        lines.append("")
        for s in offending[:6]:
            lines.append(f"  • `{s}`")
    if drill:
        lines.append("")
        lines.append("Drill-down:")
        # Fence the SQL — identical rationale to _format_l2_alert: makes `*` and `_` literal.
        lines.append(f"```\n{drill}\n```")
    if pointers:
        lines.append("")
        lines.append("Code pointers:")
        for p in pointers:
            lines.append(f"  `{p}`")
    return "\n".join(lines)


def _format_l2_alert(
    metric: MetricSpec, current: float, baseline: dict,
    event_deltas: list[dict], body: dict,
) -> str:
    """Render L2 Telegram alert.

    Replaces the prior `Hypothesis: <Sonnet sentence>` line with structured
    audit-event-delta facts (2026-05-15). Operator interprets cause from
    raw signal — no LLM inference.
    """
    p50 = baseline.get("p50") or 0
    mad = baseline.get("mad") or 0
    z = body.get("z_score")
    ratio = body.get("ratio")
    regime_tag = " (regime-conditional)" if body.get("regime_conditional") else ""
    lines = [
        # Backtick the metric name — identifiers like `HIGH_ep_entry_rate` /
        # `cooldowns_per_day` contain underscores that break Markdown italics
        # → Telegram 400 → plaintext fallback (7 of the 51 fallbacks/30d, #121).
        f"🟠 ANOMALY [L2] · `{metric.name}`{regime_tag}",
        "",
        f"Today: {current} · 30d median: {p50} · MAD: {mad}"
        + (f" · z={z}" if z is not None else "")
        + (f" · ratio={ratio}×" if ratio else ""),
        "",
    ]
    if event_deltas:
        lines.append("Top audit event deltas today vs 14d baseline:")
        for d in event_deltas:
            event_type = d["event_type"]
            today_n = d["today_count"]
            base = d["baseline_median"]
            label = d.get("baseline_label", "median")
            firing_days = d.get("firing_days", 0)
            window_total = d.get("window_total", 0)
            if d["is_new"]:
                tag = f"window_total=0, NEW today"
            elif label == "firing_day_mean":
                # Sparse-firing event — disclose firing pattern so 'baseline'
                # number reads correctly (mean on firing days, not on all
                # days). Fix shipped 2026-05-19 after ticker_revalidated_out
                # falsely flagged as NEW due to Mon/Wed/Fri firing pattern.
                # 13d trailing window matches _top_event_deltas expected_days
                # (window_days=14 default, minus today).
                tag = (
                    f"firing-day mean {base:.1f} "
                    f"(fired {firing_days}/13d, total {window_total}), "
                    f"{d['ratio']:.1f}× normal"
                )
            else:
                tag = f"median {base:.1f}, {d['ratio']:.1f}× normal"
            # Backtick the event_type (underscore identifier) — same Markdown
            # break class as metric.name above.
            lines.append(f"  • `{event_type:30s}` {today_n:4d}  ({tag})")
        lines.append("")
    lines.append("Drill-down:")
    # Fence the SQL — it contains `*` (SELECT *) and `_` that otherwise break
    # Markdown; a code block makes them literal and reads as monospace.
    lines.append(f"```\n{metric.drill_sql}\n```")
    if metric.code_pointers:
        lines.append("")
        lines.append("Code pointers:")
        for p in metric.code_pointers:
            lines.append(f"  `{p}`")
    return "\n".join(lines)


# ── Persistence + Telegram ───────────────────────────────────────────────────


async def _emit_l1(name: str, body: dict) -> None:
    if await count_today_anomalies(name) > 0:
        return
    # Naked-position invariant (#140): classify each suspect row by querying
    # broker for actual stop coverage. Real-naked → 🚨 keeps the severe
    # alert. DB-drift → ⚠️ downgrades to operational warning. Operator
    # severity is now informative, not uniform.
    if name == "naked_position":
        from agents.market_intelligence.audit_invariants import classify_naked_positions
        body = await classify_naked_positions(body)
        text = _format_naked_position_alert(body)
    else:
        text = _format_l1_alert(name, body)
    _detail = {
        "level": 1, "key": name,
        "summary": body.get("summary"),
        "count": body.get("count"),
        "drill_sql": body.get("drill_sql"),
        "code_pointers": body.get("code_pointers"),
        "offending": (body.get("offending") or [])[:6],
    }
    # #140 follow-up (2026-08-02): PERSIST the naked-position classification.
    # It was computed above and rendered into the Telegram text — then DROPPED, because this
    # detail dict wrote a fixed key set. So the severity that distinguishes 🚨 REAL-NAKED (real $
    # unprotected) from ⚠️ DB-DRIFT (broker HAS the stop, only our column is empty) existed for
    # exactly one message and then evaporated.
    #
    # Consequence, found on the 2026-07-27 QBTS alert: every later review is STRUCTURALLY unable
    # to tell the two apart — the weekly system review flagged it "UNVERIFIED", and answering it
    # took reconstructing the exit from `mi_live_trades.exits` (reason=stop_hit ⇒ a stop existed
    # ⇒ DB drift, no exposure). An alert whose severity cannot be recovered afterwards cannot be
    # triaged afterwards.
    if name == "naked_position":
        _detail["real_naked"] = body.get("real_naked") or []
        _detail["db_drift"] = body.get("db_drift") or []
        _detail["classified"] = ("real_naked" in body) or ("db_drift" in body)
    await log_audit_event(
        _AUDIT_EVENT,
        summary=f"L1 {name}",
        # default=str (codebase idiom, e.g. ep_detector.py/order_ingest.py log_audit_event
        # calls): naked_position's offending_rows/real_naked/db_drift carry raw asyncpg
        # Record->dict values (alert_date: date, filled_at: datetime) that plain json.dumps
        # cannot serialize. This was the 2026-08-10 incident — the highest-severity L1
        # (naked_position) raised TypeError here and the breach was never written.
        detail=json.dumps(_detail, default=str),
    )
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(text)
    except Exception:
        logger.exception(f"system_audit: L1 Telegram send failed for {name} (audit row written)")


async def _emit_l2(metric: MetricSpec, anomaly: Anomaly, event_deltas: list[dict]) -> None:
    if await count_today_anomalies(metric.name) > 0:
        return
    baseline = {
        "p50": anomaly.body.get("baseline_p50"),
        "mad": anomaly.body.get("mad"),
    }
    text = _format_l2_alert(metric, anomaly.body["current"], baseline, event_deltas, anomaly.body)
    await log_audit_event(
        _AUDIT_EVENT,
        summary=f"L2 {metric.name}",
        # default=str: same class as the L1 fix above — a metric body carrying a raw date/
        # datetime must not blow up the write.
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
            # to_band (the band the L2 is firing at, = 3) — same key the L3 path writes
            # and _last_band_for/_persistent_l2_downgrade read, so tomorrow's run sees the
            # prior band and dedups a persisting L2 (fire-once-then-quiet, #352).
            "to_band": anomaly.body.get("to_band"),
            "event_deltas": event_deltas,
            "drill_sql": metric.drill_sql,
            "code_pointers": metric.code_pointers,
        }, default=str),
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
        # default=str: same class as the L1/L2 fixes above.
        detail=json.dumps({
            "level": 3, "key": metric.name,
            "current": anomaly.body.get("current"),
            "baseline_p50": anomaly.body.get("baseline_p50"),
            "z_score": anomaly.body.get("z_score"),
            "ratio": anomaly.body.get("ratio"),
            "from_band": anomaly.body.get("from_band"),
            "to_band": anomaly.body.get("to_band"),
            "warming": anomaly.body.get("warming", False),
        }, default=str),
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
            # _emit_l1 gets its OWN try/except (2026-08-10 incident): it was previously
            # outside this function's try, so one invariant's emit failure (naked_position's
            # unserializable date/datetime detail) propagated out of the loop and silently
            # killed every LATER invariant in the sweep for the night — including this
            # function's own remaining iterations. A failing emit must be loud (logged with
            # the invariant name) but must never abort the sweep.
            try:
                await _emit_l1(name, body)
            except Exception:
                logger.exception(f"system_audit: _emit_l1 failed for invariant {name} (breach not recorded)")
                continue
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
    l2_count = 0
    l3_count = 0
    for metric in metrics:
        try:
            anomaly = await _compute_anomaly(
                conn, metric, current_regime,
                as_of=as_of,
            )
        except Exception:
            logger.exception(f"system_audit: metric {metric.name} failed")
            continue
        if anomaly is None:
            continue
        if anomaly.level == 2:
            event_deltas = await _top_event_deltas(conn)
            # Same emit-outside-the-try shape as _check_invariants (2026-08-10 incident):
            # an _emit_l2/_emit_l3 failure must not abort the metric sweep either.
            try:
                await _emit_l2(metric, anomaly, event_deltas)
            except Exception:
                logger.exception(f"system_audit: _emit_l2 failed for metric {metric.name}")
                continue
            l2_count += 1
        elif anomaly.level == 3:
            try:
                await _emit_l3(metric, anomaly)
            except Exception:
                logger.exception(f"system_audit: _emit_l3 failed for metric {metric.name}")
                continue
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
              AND status IN ('failed', 'empty_result', 'interrupted')
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
            elif r["status"] == "interrupted":
                # #528/#512 — never render this as FAILED: the process died, work outcome unknown.
                err = (r["error_message"] or "")[:120]
                parts.append(f"  {ts} {r['job_id']} INTERRUPTED: {err}")
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
