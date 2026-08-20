"""News-source quality scoring and drift detection.

Per user 2026-05-21: "we should at least have a way to eval this over
time, again, no silent failures, even if it's not explicit error like
API, quality signals degrading should be loud too."

Each EP extraction persists raw per-source corpus + attribution. This
module rolls that up to quality metrics per source over time + emits
drift alerts when a source's contribution materially degrades.

Three quality dimensions per source:
  - Coverage: % of extractions where source returned ≥1 item
  - Density:  median items per extraction (when source returned anything)
  - Attribution: % of extractions where `q_revenue_usd.sources` cited this source

Drift detection: current 7d vs trailing 30d (excluding current 7d).
Emit `news_source_quality_drift` audit + Telegram when ANY source's
coverage OR attribution drops >40% (absolute pp) week-over-week, AND
the baseline had ≥10 extractions (so we have signal, not noise).

Used by:
  - `_weekly_system_review_job` (Sunday digest) — section in the report
  - Daily-ish drift detector (TBD: wire into a job if needed)
  - On-demand: `python -m agents.market_intelligence.news_source_quality`
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# Sources tracked. Keys are the raw_*_json/text column names; display
# names below are operator-facing. fmp/yfinance is the same column post
# 2026-05-21 ship (FMP paywalled, yfinance fallback only).
SOURCES = [
    ("raw_polygon_news_json",   "Polygon",         "array"),
    ("raw_alpaca_news_json",    "Alpaca/Benzinga", "array"),
    ("raw_fmp_news_json",       "yfinance (legacy 'fmp')", "array"),
    ("raw_perplexity_text",     "Perplexity",      "text"),
    ("raw_claude_analysis_text", "Claude analysis", "text"),
]


# Canonical INGESTED-FEED aliases (#265) — substrings that identify a feed we
# already ingest when it appears in FREE TEXT (e.g. a Perplexity answer naming
# where a story was first published). This module owns "what do we ingest";
# the source-gap finder imports this and adds its SEC form-type aliases.
# WHEN THE OPERATOR ONBOARDS A NEW FEED: add its aliases here (one place) or
# the gap finder keeps re-recommending the now-covered source weekly.
# (Perplexity/Claude deliberately absent — they're discovery layers, not
# direct feeds; a gap-finder answer naming them is not "already covered".)
INGESTED_FEED_ALIASES = ("benzinga", "polygon", "alpaca")


# Source name as it appears in extraction's q_revenue_usd.sources field.
# Maps display name → list of strings the extraction might use.
ATTRIBUTION_KEYS = {
    "Polygon":               ["polygon"],
    "Alpaca/Benzinga":       ["alpaca", "benzinga", "alpaca/benzinga"],
    "yfinance (legacy 'fmp')": ["fmp", "yfinance"],
    "Perplexity":            ["perplexity"],
    "Claude analysis":       ["claude", "claude_analysis"],
}


async def collect_source_stats(
    start_date: date,
    end_date: date,
) -> dict[str, dict]:
    """Aggregate quality stats per source over the given date window.

    Returns:
      {source_display_name: {coverage_pct, density_median, attribution_pct, n_extractions}}
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT raw_json, raw_polygon_news_json, raw_alpaca_news_json,
                   raw_fmp_news_json, raw_perplexity_text, raw_claude_analysis_text
            FROM mi_ep_catalyst_metrics
            WHERE alert_date >= $1 AND alert_date <= $2
        """, start_date, end_date)

    if not rows:
        return {}

    n = len(rows)
    out: dict[str, dict] = {}

    for col, display, kind in SOURCES:
        coverage_count = 0
        densities: list[int] = []
        for r in rows:
            val = r[col]
            if kind == "array":
                # JSONB array; count length
                if val is not None:
                    items = val if isinstance(val, list) else []
                    if len(items) > 0:
                        coverage_count += 1
                        densities.append(len(items))
            else:  # text
                if val and isinstance(val, str) and len(val) > 50:
                    coverage_count += 1
                    densities.append(len(val))

        # Attribution: count extractions where q_revenue_usd.sources cites this source
        attribution_count = 0
        keys = ATTRIBUTION_KEYS.get(display, [])
        for r in rows:
            raw = r["raw_json"]
            if isinstance(raw, str):
                import json as _json
                try:
                    raw = _json.loads(raw)
                except Exception:
                    raw = None
            if not isinstance(raw, dict):
                continue
            qrv = raw.get("q_revenue_usd") or {}
            sources = qrv.get("sources") or []
            if any(k in (s or "").lower() for s in sources for k in keys):
                attribution_count += 1

        coverage_pct = (coverage_count / n) * 100
        attribution_pct = (attribution_count / n) * 100
        density_median = statistics.median(densities) if densities else 0

        out[display] = {
            "coverage_pct": round(coverage_pct, 1),
            "density_median": int(density_median),
            "attribution_pct": round(attribution_pct, 1),
            "n_extractions": n,
            "coverage_count": coverage_count,
            "attribution_count": attribution_count,
        }
    return out


# Drift-event policy thresholds — ONE policy, named together (recalibrate as a set):
# minimum |delta| in percentage points to count as drift at all; minimum baseline
# extractions for the comparison to mean anything; and (#264) the current-window
# extraction floor for a TELEGRAM-worthy event — below it, per-source percentages
# swing wildly with cohort composition (earnings-season PRs vs thin-tape
# missed-EP names), so the event is audit-only.
_DRIFT_DELTA_PP = 40
_MIN_BASELINE_N = 10
_MIN_CURRENT_N = 15
# An attribution swing is only a SOURCE problem if the source stopped DELIVERING.
# 2026-08-20: Benzinga attribution read 87% -> 44% and alerted, but the feed was
# healthy — 4.6 articles per extraction against a baseline of 4.5. What changed
# was the WEEK: off earnings season there is no earnings press release carrying a
# revenue figure, so the extractor cites FMP/Perplexity instead. Attribution
# measures which source the revenue number came from; it is confounded by the
# cohort. Delivery is not. So an attribution drift whose delivery is intact is
# audit-only. A significance test would NOT have caught this (z=-4.6, the shift
# is statistically real) — the alert was confounded, not noisy.
_DELIVERY_DENSITY_FLOOR = 0.6   # fraction of baseline items-per-extraction


async def detect_drift() -> dict[str, Any]:
    """Compare current 7d vs trailing 30d baseline (excluding current 7d).

    Returns dict with `drift_events` list, each entry:
      {source, metric, current_pct, baseline_pct, delta_pp}
    where delta_pp is current - baseline in percentage points.

    Threshold: drift_event when |delta_pp| >= _DRIFT_DELTA_PP AND baseline had
    >= _MIN_BASELINE_N extractions AND the current window has >= _MIN_CURRENT_N
    extractions (#264 — below the floor the event lands in `low_n_events`:
    audit-only, no Telegram, because a thin week's cohort composition
    masquerades as source degradation).
    """
    from agents.market_intelligence.collector import et_today
    today_d = et_today()
    current_start = today_d - timedelta(days=6)
    current_end = today_d
    baseline_start = today_d - timedelta(days=29)
    baseline_end = today_d - timedelta(days=7)

    current = await collect_source_stats(current_start, current_end)
    baseline = await collect_source_stats(baseline_start, baseline_end)

    drift_events = []
    if not current or not baseline:
        return {
            "drift_events": [],
            "current_window": f"{current_start}..{current_end}",
            "baseline_window": f"{baseline_start}..{baseline_end}",
            "current_n": (current.get(next(iter(current), ""), {}).get("n_extractions", 0) if current else 0),
            "baseline_n": (baseline.get(next(iter(baseline), ""), {}).get("n_extractions", 0) if baseline else 0),
        }

    def _delivery_intact(cur: dict, base: dict) -> bool:
        """True when the source is still delivering normally — coverage has not
        itself drifted and article density holds. See _DELIVERY_DENSITY_FLOOR."""
        if (base.get("coverage_pct", 0) - cur.get("coverage_pct", 0)) >= _DRIFT_DELTA_PP:
            return False
        base_d = base.get("density_median", 0) or 0
        cur_d = cur.get("density_median", 0) or 0
        if base_d <= 0:
            return True
        return (cur_d / base_d) >= _DELIVERY_DENSITY_FLOOR

    low_n_events = []
    suppressed_events = []
    for source in current:
        cur = current[source]
        base = baseline.get(source, {})
        base_n = base.get("n_extractions", 0)
        if base_n < _MIN_BASELINE_N:
            # Not enough baseline to compare
            continue
        for metric in ("coverage_pct", "attribution_pct"):
            cur_v = cur.get(metric, 0)
            base_v = base.get(metric, 0)
            delta = cur_v - base_v
            if abs(delta) >= _DRIFT_DELTA_PP:
                event = {
                    "source": source,
                    "metric": metric,
                    "current_pct": cur_v,
                    "baseline_pct": base_v,
                    "delta_pp": round(delta, 1),
                    "current_n": cur["n_extractions"],
                    "baseline_n": base_n,
                }
                # #264 min-N floor: a thin current window (n=10 vs a 50-row
                # earnings-season baseline) reads COMPOSITION shifts as source
                # degradation — the 6/9 'Benzinga 68%→20%' false alarm. Below
                # the floor the event is audit-only (low_n_events), no Telegram.
                if cur["n_extractions"] < _MIN_CURRENT_N:
                    event["suppressed_reason"] = "low_n"
                    low_n_events.append(event)
                elif metric == "attribution_pct" and _delivery_intact(cur, base):
                    # Confounded by cohort composition, not a source failure.
                    event["suppressed_reason"] = "delivery_intact"
                    event["current_density"] = cur.get("density_median", 0)
                    event["baseline_density"] = base.get("density_median", 0)
                    suppressed_events.append(event)
                else:
                    drift_events.append(event)
    return {
        "drift_events": drift_events,
        "low_n_events": low_n_events,
        "suppressed_events": suppressed_events,
        "current_window": f"{current_start}..{current_end}",
        "baseline_window": f"{baseline_start}..{baseline_end}",
        "current_stats": current,
        "baseline_stats": baseline,
    }


def format_quality_report(stats: dict[str, dict], window_label: str) -> str:
    """Format a quality table for Telegram digest."""
    if not stats:
        return f"_News source quality ({window_label}): no extractions in window._"
    n = stats.get(next(iter(stats)), {}).get("n_extractions", 0)
    lines = [
        f"📰 *News source quality* ({window_label}, N={n} extractions)",
        "```",
        f"{'Source':<22} {'Coverage':>10} {'Density':>9} {'Cited':>10}",
        "-" * 56,
    ]
    for source, s in stats.items():
        coverage = f"{s['coverage_pct']:.0f}%"
        density = f"{s['density_median']}"
        attr = f"{s['attribution_pct']:.0f}%"
        lines.append(f"{source:<22} {coverage:>10} {density:>9} {attr:>10}")
    lines.append("```")
    return "\n".join(lines)


def format_drift_alert(drift_report: dict) -> str | None:
    """Format a drift alert if events present. Returns None if no drift."""
    events = drift_report.get("drift_events") or []
    if not events:
        return None
    lines = [
        "🔻 *News source quality DRIFT detected*",
        f"_Current 7d ({drift_report.get('current_window')}) "
        f"vs trailing baseline ({drift_report.get('baseline_window')})_",
        "",
    ]
    for e in events:
        arrow = "↓" if e["delta_pp"] < 0 else "↑"
        lines.append(
            f"{arrow} *{e['source']}* {e['metric']}: "
            f"{e['baseline_pct']:.0f}% → {e['current_pct']:.0f}% "
            f"({e['delta_pp']:+.0f}pp, n={e['current_n']} vs baseline n={e['baseline_n']})"
        )
    lines.append("")
    lines.append(
        "_Investigate: source API outage? rate-limiting? content degraded? "
        "Check cohort composition first — an earnings-light week shifts "
        "attribution without any source being broken (6/9 false-alarm class)._"
    )
    return "\n".join(lines)


async def _drift_telegram_already_sent_recently() -> bool:
    """24h DB-dedup so daily quality-check job doesn't re-Telegram the
    same persistent drift every day. Audit event still fires (durable
    telemetry); Telegram is suppressed when one was sent in last 24h.
    Same pattern as the CAVA rubric-downgrade dedup and other 24h windows.
    """
    try:
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 1 FROM mi_audit_log
                WHERE event_type = 'news_source_quality_drift'
                  AND created_at > NOW() - INTERVAL '24 hours'
                  AND created_at < NOW() - INTERVAL '1 second'
                LIMIT 1
            """)
            return row is not None
    except Exception:
        return False  # fail-open: send Telegram on DB error


async def run_quality_check() -> dict:
    """Run from the 16:30 scheduler job — returns full report dict + surfaces
    drift if events present. 24h dedup on the operator surface (audit always
    fires). #479: the drift alert no longer Telegrams directly — the render
    text goes to close_digest.contribute("NEWS", ...) and lands in the 16:55
    Market Close Digest (this runner is job-exclusive to
    news_quality_drift_check).
    """
    drift_report = await detect_drift()
    drift_alert = format_drift_alert(drift_report)
    low_n = drift_report.get("low_n_events") or []
    suppressed = drift_report.get("suppressed_events") or []
    if drift_alert:
        try:
            from agents.market_intelligence.db import log_audit_event
            # Always log audit (durable telemetry, even if surface dedup'd)
            await log_audit_event(
                "news_source_quality_drift",
                f"{len(drift_report['drift_events'])} drift event(s) detected",
            )
            # 24h dedup on the operator surface only
            if not await _drift_telegram_already_sent_recently():
                from agents.market_intelligence.close_digest import contribute
                contribute("NEWS", drift_alert)
        except Exception as e:
            logger.warning(f"drift alert handling failed: {e}")
    # Both audit-only buckets write UNCONDITIONALLY — not in an elif behind the
    # drift branch. A suppressed event is still evidence and must stay findable
    # even on a day that also produced a real drift; the old `elif` silently
    # dropped it whenever anything else fired.
    if low_n:
        # #264: drift shape present but the current window is too thin to
        # distinguish source degradation from cohort composition — durable
        # audit row only, NO Telegram (the 6/9 false-alarm class).
        try:
            import json as _json
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "news_source_quality_drift_low_n",
                f"{len(low_n)} drift-shaped event(s) below n={_MIN_CURRENT_N} floor — audit-only",
                _json.dumps(low_n),
            )
        except Exception as e:
            logger.warning(f"low-n drift audit failed: {e}")
    if suppressed:
        # Attribution moved but the source kept delivering — cohort composition,
        # not degradation (2026-08-20 Benzinga 87%->44% at 4.6 vs 4.5 articles
        # per extraction). Durable audit row, NO Telegram.
        try:
            import json as _json
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "news_source_quality_drift_delivery_intact",
                f"{len(suppressed)} attribution drift(s) suppressed — the source is still "
                f"delivering, so the swing is cohort composition, not degradation",
                _json.dumps(suppressed),
            )
        except Exception as e:
            logger.warning(f"delivery-intact drift audit failed: {e}")
    return drift_report


async def print_quarterly_summary() -> None:
    """Quarter-wide (90d) per-source quality summary + drift detection.
    Called by the quarterly sweep job alongside the 3 backward-check
    scripts. Prints to stdout for the sweep's aggregation step.
    """
    from agents.market_intelligence.collector import et_today
    today_d = et_today()
    window_start = today_d - timedelta(days=89)
    print("=" * 60)
    print(f"News source quality — quarter-wide (90d, {window_start}..{today_d})")
    print("=" * 60)
    stats = await collect_source_stats(window_start, today_d)
    print(format_quality_report(stats, "quarter (90d)"))
    print()
    drift = await detect_drift()
    alert = format_drift_alert(drift)
    if alert:
        print(alert)
    else:
        print("✅ No drift events detected (current 7d vs trailing 23d baseline).")


if __name__ == "__main__":
    import asyncio
    import sys
    from agents.market_intelligence.collector import et_today

    mode = sys.argv[1] if len(sys.argv) > 1 else "weekly"

    async def _weekly():
        today_d = et_today()
        print(f"News source quality — current 7d ({today_d - timedelta(days=6)}..{today_d})")
        print()
        current = await collect_source_stats(today_d - timedelta(days=6), today_d)
        print(format_quality_report(current, "current 7d"))
        print()
        drift = await detect_drift()
        alert = format_drift_alert(drift)
        if alert:
            print(alert)
        else:
            print("✅ No drift events detected.")

    if mode == "quarterly":
        asyncio.run(print_quarterly_summary())
    else:
        asyncio.run(_weekly())
