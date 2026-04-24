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
    # HIGH_ep_entry_rate: scanner-crash class — a drop to 0 on a day with
    # detected HIGHs means the entry pipeline broke. Fires when 0 detected
    # is also a degenerate case but `_today_high_entry_rate` returns 0.0
    # there too; that's why the regime-conditional + sample-driven path
    # carries the real load. The cold-start floor is just a safety net.
    "HIGH_ep_entry_rate":             (0.5,  "low"),   # < 0.5 entry rate = warning
    "theme_count_active":             (5,    "low"),   # < 5 themes = dedup death
    "validation_rate_limited_count":  (3,    "high"),
    "bar_stream_disconnect_count_24h": (5,   "high"),
}

_MIN_FULL_SAMPLE = 14
_WARMING_MIN = 7
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
    fetch_today: Callable[..., Awaitable[float]]
    drill_sql: str
    code_pointers: list[str] = field(default_factory=list)


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


async def _today_high_entry_rate(conn) -> float:
    """entered / detected for HIGH-tier alerts today. URI class blind spot."""
    row = await conn.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE a.score_tier='HIGH') AS detected,
          COUNT(*) FILTER (
            WHERE a.score_tier='HIGH'
              AND lt.status IN ('filled','closed','order_placed','pending_confirmation')
          ) AS entered
        FROM mi_ep_alerts a
        LEFT JOIN mi_live_trades lt
          ON lt.ticker=a.ticker AND lt.alert_date=a.alert_date
        WHERE a.alert_date = CURRENT_DATE
        """
    )
    detected = int(row["detected"] or 0)
    entered = int(row["entered"] or 0)
    if detected == 0:
        return 0.0  # no signal today — not an anomaly, baseline handles
    return entered / detected


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
        "SELECT a.ticker, a.score_tier, lt.status, lt.skip_reason FROM mi_ep_alerts a "
        "LEFT JOIN mi_live_trades lt ON lt.ticker=a.ticker AND lt.alert_date=a.alert_date "
        "WHERE a.alert_date=CURRENT_DATE AND a.score_tier='HIGH';",
        ["agents/market_intelligence/broker/live_tracker.py::process_new_alerts_live"],
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
]

_ALL_METRICS = _TRADE_METRICS + _NIGHTLY_METRICS

_TOPIC_MAP: dict[str, list[MetricSpec]] = {
    "cooldowns": [m for m in _ALL_METRICS if m.name == "cooldowns_per_day"],
    "themes":    [m for m in _ALL_METRICS if m.name in {"theme_count_active", "cooldowns_per_day"}],
    "skips":     [m for m in _ALL_METRICS if m.name.startswith("skip_count_")],
    "positions": [m for m in _ALL_METRICS if m.name in {"HIGH_ep_entry_rate"}],
    "feed":      [m for m in _ALL_METRICS if m.name in {"bar_stream_disconnect_count_24h", "skip_count_infra"}],
    "9m":        [m for m in _ALL_METRICS if m.name == "9m_alerts_per_day"],
    "all":       _ALL_METRICS,
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


async def run_baseline_refresh() -> None:
    """02:00 ET nightly job. Rebuilds `mi_metric_baselines` from trailing
    samples. Idempotent — safe to re-run.
    """
    today = et_today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        for metric in _ALL_METRICS:
            history = await _fetch_history(conn, metric)
            p50, p95, mad, n = _trimmed_median_mad(history)
            await upsert_metric_baseline(
                metric.name, today,
                p50=p50, p95=p95, mad=mad, sample_n=n,
            )
    logger.info(f"system_audit: baselines refreshed for {len(_ALL_METRICS)} metrics")


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
        l1 = await _check_invariants(conn, since=since, since_dt=since_dt, now_et=datetime.now())
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


async def run_topic_audit(topic: str, *, baseline_as_of: date | None = None) -> dict:
    """`/audit <topic>` ad-hoc entry. Same scan logic, scoped to topic."""
    metrics = _TOPIC_MAP.get(topic.lower())
    if metrics is None:
        return {"error": f"unknown topic '{topic}'", "valid": sorted(_TOPIC_MAP.keys())}
    today = et_today()
    since = today - timedelta(days=_BASELINE_LOOKBACK_DAYS)
    since_dt = datetime.combine(since, datetime.min.time())
    pool = await get_pool()
    async with pool.acquire() as conn:
        l1 = 0
        if topic == "all":
            l1 = await _check_invariants(conn, since=since, since_dt=since_dt, now_et=datetime.now())
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
