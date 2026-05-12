"""
Weekly system self-audit.

Pulls 7 days from every tracking system, aggregates to summary statistics
(the LLM never sees raw rows — that's a token trap), hands the summary to
Claude Sonnet for synthesis, sends a Telegram digest, persists to
mi_system_reviews so next week's run can grade its own prior suggestions.

Entry points:
  run_weekly_review() — called by scheduler and on-demand route.
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from datetime import date, timedelta

import anthropic

from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.db import (
    get_active_cooldowns,
    get_audit_log,
    get_correlation_clusters,
    get_ep_outcomes,
    get_latest_regime,
    get_latest_system_review,
    get_paper_trade_stats,
    get_weekly_theme_churn,
    insert_system_review,
)

logger = logging.getLogger(__name__)

_WINDOW_DAYS = 7
_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1200

_SYSTEM_PROMPT = """You are Apollo's weekly self-auditor. You review metrics from \
a momentum/EP trading assistant and surface what's working, what's broken, and \
propose concrete tuning changes.

Methodology context (NON-NEGOTIABLE — proposals contradicting these get rejected):
- Pradeep Bonde / Qullamaggie momentum doctrine: lose-small / win-big.
  20% win rate × 10R per winner is excellent; win-rate alone is misleading.
  Edge is measured in R-expectancy and profit factor, not pos_rate.
- HOLD WINNERS, stop losers fast. Do NOT propose mandatory partials based
  on gap size — Pradeep methodology lets winners run; auto-partial on
  a +15% gap is a methodology violation regardless of how the math looks.
- Tight defined stop on Day 0; manage via SMA trail + breakeven, not
  time-based exits.
- N=3 trade samples are statistical noise — do not propose changes from
  single-week trade outcomes; require ≥30 closed trades or ≥60 days of
  telemetry for any cohort-driven recommendation.

Hygiene rules for proposed changes:
- Before proposing a "new" guardrail, check `recent_changes` in the metrics
  JSON. If the change shipped within the last 30 days, do NOT re-propose;
  instead note it shipped and observe whether the metric improved.
- Do NOT speculate on bugs from circumstantial data (e.g. "this loss might
  be a duplicate-exit bug"). Only flag bugs that are SUPPORTED by audit
  events in `audit_errors`. If audit log is silent on a behavior, the
  behavior was nominal.
- Distinguish skipped/blocked alerts from actual trade attempts. If `36`
  EPs were 33 max_positions blocks + 3 actual entries, the cohort is N=3,
  not N=36. Cite the active cohort, not the alert volume.

Output exactly this structure, in this order, with these exact section headers:

✅ *Working*
• 3 bullets, each grounded in a specific number from the data

⚠️ *Broken*
• 3 bullets, each grounded in a specific number

💡 *Proposed changes*
1. First concrete change (threshold, rule, or behavior — be specific)
2. Second concrete change (optional — only include if warranted)

🔁 *Last week:*
One sentence comparing last week's proposed changes to this week's metrics. \
If the relevant metric improved, say so with the delta. If unchanged, assume \
the change was not implemented. Do NOT claim you know whether code was deployed.

Rules:
- No fluff, no filler headers beyond the four above.
- Max 350 words total.
- Every bullet must cite a number from the metrics JSON.
- Keep Telegram Markdown: *bold*, `code`, no tables.
- When `postmortem_best` or `postmortem_worst` is present, weave one concrete insight from each into the ✅/⚠️ sections (e.g. "{ticker}'s exit followed through {pnl}…"). Do not paste the full postmortem — extract the takeaway.
- When `anomalies.l3_drifts.count > 0`, append a "📉 *Drift:*" line after 🔁 listing up to 3 metrics whose from_band → to_band transition this week (silent during the week, surfaces here only). Use the format `metric_name: from_band→to_band (current vs p50)`. Do not invent transitions if the count is 0; omit the line entirely.
- `anomalies.l1_invariants` and `anomalies.l2_anomalies` already pinged Telegram during the week — cite their counts in ⚠️ *Broken* if non-zero so the user sees the week's invariant/anomaly footprint at a glance.
- The `crypto` field in the metrics is surfaced separately as a deterministic appendix below your output. Do NOT mention crypto in the four sections above — that surface is handled.
- When `strategy_promotions.checks` is non-empty AND any entry has `next_phase` != null, append a "📈 *Strategy promotion check:*" line after 🔁 listing each non-top-of-ladder strategy on its own indented bullet: `<strategy_id>: <eligible '✓ ready' OR top blocking_reason>` (e.g. `shadow_orb_5m: need 30 paired closed (have 12)`). Skip strategies already at the top of the ladder. Omit the section entirely if every strategy is at top-of-ladder.
- When `shadow_orb.paired_closed_total >= 10`, append a "📐 *Shadow ORB:*" line after 🔁 summarizing 5-min vs 1-min ORB telemetry. Cite `entered` / `no_entry` counts and the top `by_shape` entry's `per_alert_delta` (e.g. "12 5m entries, 4 no-entry; bounce 9m delta +0.4 R over 8 paired"). Note: by-shape deltas are 9M-cohort only — `shape_tag` is NULL on MAGNA53 rows. If `paired_closed_total < 10`, omit the line entirely (insufficient signal).
- When `wick.n_settled >= 10`, append a "🪝 *Wick:*" line after 🔁 summarizing wick-fill telemetry. Cite `n_total` candidates, `fill_rate`, and the gap between `median_fwd_3d_from_high` (filled cohort, conditional drift after fill) and `median_fwd_3d_from_close` (all-settled drift baseline) — the gap is the strategy's actual edge. Format: `12 candidates, 58% fill rate; +1.2% 3d post-fill vs +0.4% baseline drift`. If `n_settled < 10`, omit the line entirely (insufficient signal).
- When `fishhook.n_settled >= 10`, append a "🪝 *Fishhook:*" line after 🔁 summarizing gap-up undercut & reclaim telemetry. Cite `n_total` anchors, `n_settled`, `median_r`, `hit_rate`, and the shallow-vs-deep slice when both have data: `45 anchors, 12 settled; R 1.18, hit 17%; shallow R 1.31 (n=8) vs deep R 0.61 (n=4)`. The shallow-vs-deep gap matters — Stage-0 evidence said deeper drift inverts the edge; if deep starts winning, threshold revisit. If `n_settled < 10`, omit the line entirely.
- When `pending_reviews.ready` is non-empty, append a "📅 *Reviews ready:*" section after 🔁 listing each ready entry on its own line: `<title> — <action_when_ready first sentence>`. These are data-gated reviews from `data_gated_reviews.yaml` whose threshold flipped this week — the user needs to act. If `pending_reviews.ready` is empty, omit the section entirely.
- When `audit_errors.total > 0`, append a "🔴 *Silent failures (7d):*" section after 🔁 listing each `top_types` entry on its own line: `<event_type> ×<count>`. These are non-fatal errors caught by try/except in jobs that didn't crash hard but indicate something silently broken (e.g. EP scan outcomes typo lurked weeks before surfacing). Even 1 fire merits inclusion — silent failures compound. If `audit_errors.total == 0`, omit the section entirely.
- When `strategy_promotions.checks` includes a strategy with `eligible=false` AND its top blocking_reason references a 0-count metric (e.g. "have 0"), the line MUST include the diagnostic context from `metrics.cohort_breakdown` if present (e.g. `shadow_orb_5m: have 0 paired closed (1 shadow vs 3 live, zero overlap)`). The 0-count number alone forces a follow-up question; the breakdown answers it inline.
"""


async def run_weekly_review(window_days: int = _WINDOW_DAYS) -> dict:
    """Execute the weekly review: gather, aggregate, synthesize, persist, send."""
    today = date.today()
    window_start = today - timedelta(days=window_days)

    metrics = await _gather_and_aggregate(window_start, today, window_days)
    prior = await get_latest_system_review(window_days=window_days)

    summary = await _synthesize(metrics, prior)

    review = {
        "review_date": today.isoformat(),
        "window_days": window_days,
        "regime": metrics.get("regime", {}).get("current"),
        "summary": summary,
        "metrics": metrics,
        "suggestions": _extract_suggestions(summary),
    }
    await insert_system_review(review)

    header = f"🧠 *Weekly System Review — {window_start.strftime('%b')} {window_start.day}–{today.day}*"
    regime_label = metrics.get("regime", {}).get("current") or "Unknown"
    message = f"{header}\n*Regime:* {regime_label}\n\n{summary}"

    # Losers post-mortem (#76, 2026-05-11) — deterministic appendix above
    # crypto so the methodology-tuning signals land near the top of the
    # appendix block, right where the eye looks after reading the LLM
    # summary. Empty string if no losing trades in window (skipped clean).
    loser_section = _format_loser_section(metrics.get("loser_breakdown") or {})
    if loser_section:
        message = f"{message}\n\n{loser_section}"

    # Crypto RS readiness — deterministic appendix (not LLM-interpreted).
    # Surfaces "ready to flip" verdict so the user doesn't forget about
    # the shadow-mode module accumulating in the background.
    crypto_section = _format_crypto_section(metrics.get("crypto") or {})
    if crypto_section:
        message = f"{message}\n\n{crypto_section}"

    await send_telegram_message(message)

    logger.info(f"Weekly review complete: {window_start}..{today}")
    return review


# ── Gather + aggregate ────────────────────────────────────────────────────────


async def _gather_and_aggregate(
    window_start: date, today: date, window_days: int
) -> dict:
    """Pull from every tracking table, aggregate to summary stats only."""
    ep = await _aggregate_ep_outcomes(window_days)
    nine_m = await _aggregate_9m_outcomes(window_days)
    paper = await _aggregate_paper_trades(window_start)
    errors = await _aggregate_audit_errors(window_days)
    churn = await _aggregate_theme_churn(window_days)
    cooldowns = await _aggregate_cooldowns(window_start)
    clusters = await _aggregate_clusters(today)
    regime = await _aggregate_regime(window_days)
    postmortems = await _aggregate_trade_postmortems(window_start)
    loser_breakdown = await _aggregate_loser_breakdown(window_start)
    anomalies = await _aggregate_anomalies(window_days)
    crypto = await _aggregate_crypto_readiness(window_days)
    shadow_orb = await _aggregate_shadow_orb_outcomes(window_days)
    wick = await _aggregate_wick_outcomes(window_days)
    fishhook = await _aggregate_fishhook_outcomes(window_days)
    strategy_promotions = await _aggregate_promotion_checks()
    pending_reviews = await _aggregate_pending_reviews(today)

    return {
        "window": {"start": window_start.isoformat(), "end": today.isoformat(), "days": window_days},
        "ep_outcomes": ep,
        "nine_m_outcomes": nine_m,
        "paper_trades": paper,
        "audit_errors": errors,
        "theme_churn": churn,
        "cooldowns": cooldowns,
        "clusters": clusters,
        "regime": regime,
        "anomalies": anomalies,
        "postmortem_best": postmortems.get("best"),
        "postmortem_worst": postmortems.get("worst"),
        "loser_breakdown": loser_breakdown,
        "crypto": crypto,
        "shadow_orb": shadow_orb,
        "wick": wick,
        "fishhook": fishhook,
        "strategy_promotions": strategy_promotions,
        "pending_reviews": pending_reviews,
    }


async def _aggregate_pending_reviews(today: date) -> dict:
    """Walk data_gated_reviews.yaml; surface entries whose data threshold
    has flipped to ready. Surfaces in the Sunday digest as a 📅 line."""
    try:
        from agents.market_intelligence.data_gated_reviews import check_pending_reviews
        return await check_pending_reviews(today)
    except Exception:
        logger.exception("pending_reviews aggregator failed")
        return {"ready": [], "pending_count": 0, "pending_summary": []}


async def _aggregate_promotion_checks() -> dict:
    """Per-strategy promotion eligibility snapshot for the weekly digest.

    Returns one entry per registered strategy with current phase, model,
    eligibility, headline metric, and blocking reasons (if any). The
    weekly review prompt cites this so the user sees which strategies
    are accumulating signal vs ready to graduate.
    """
    try:
        from agents.market_intelligence.strategies.promotion import check_all_strategies
        verdicts = await check_all_strategies()
    except Exception:
        logger.exception("promotion aggregator failed")
        return {"checks": []}
    out: list[dict] = []
    for v in verdicts:
        out.append({
            "strategy_id": v.strategy_id,
            "current_phase": v.current_phase,
            "next_phase": v.next_phase,
            "model": v.model,
            "eligible": v.eligible,
            "metrics": v.metrics,
            "blocking_reasons": v.blocking_reasons[:3],
        })
    return {"checks": out}


async def _aggregate_anomalies(days: int) -> dict:
    """Roll up the week's L1/L2/L3 anomaly_detected audit rows.

    L1/L2 already pinged Telegram during the week. L3 drift was silent —
    Sunday digest is the only place it surfaces. Body shape mirrors what
    system_audit._emit_l1/l2/l3 writes.
    """
    since_hours = days * 24
    rows = await get_audit_log(
        limit=500, since_hours=since_hours, event_type="anomaly_detected"
    )
    by_level: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    for r in rows:
        raw = r.get("detail") or "{}"
        try:
            body = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        lvl = int(body.get("level") or 0)
        if lvl not in by_level:
            continue
        by_level[lvl].append({
            "key": body.get("key"),
            "current": body.get("current"),
            "p50": body.get("baseline_p50"),
            "from_band": body.get("from_band"),
            "to_band": body.get("to_band"),
        })

    def _summarize(items: list[dict]) -> dict:
        keys = Counter(i["key"] for i in items if i.get("key"))
        return {
            "count": len(items),
            "by_key": [{"key": k, "count": c} for k, c in keys.most_common(8)],
        }

    l3_drifts = [
        {
            "key": i["key"],
            "from_band": i.get("from_band"),
            "to_band": i.get("to_band"),
            "current": i.get("current"),
            "p50": i.get("p50"),
        }
        for i in by_level[3]
        if i.get("from_band") != i.get("to_band")
    ]
    return {
        "l1_invariants": _summarize(by_level[1]),
        "l2_anomalies": _summarize(by_level[2]),
        "l3_drifts": {
            "count": len(l3_drifts),
            "transitions": l3_drifts[:10],
        },
    }


async def _aggregate_trade_postmortems(window_start: date) -> dict:
    """
    Pick the window's best and worst closed trade (by total_pnl) and generate
    one-paragraph postmortem narratives. Sources mi_live_trades when available,
    falls back to mi_paper_trades. Returns {} if neither has closed trades.
    """
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.postmortem import generate_postmortem_narrative

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, alert_date, total_pnl FROM mi_live_trades
            WHERE status = 'closed' AND alert_date >= $1 AND total_pnl IS NOT NULL
            ORDER BY alert_date DESC
        """, window_start)
        if not rows:
            rows = await conn.fetch("""
                SELECT ticker, alert_date, total_pnl FROM mi_paper_trades
                WHERE status = 'closed' AND alert_date >= $1 AND total_pnl IS NOT NULL
                ORDER BY alert_date DESC
            """, window_start)

    if not rows:
        return {}

    best = max(rows, key=lambda r: float(r["total_pnl"]))
    worst = min(rows, key=lambda r: float(r["total_pnl"]))

    out: dict = {}
    try:
        out["best"] = {
            "ticker": best["ticker"],
            "alert_date": best["alert_date"].isoformat(),
            "pnl": round(float(best["total_pnl"]), 2),
            "narrative": await generate_postmortem_narrative(
                best["ticker"], best["alert_date"]
            ),
        }
    except Exception as e:
        logger.warning(f"Weekly postmortem (best) failed: {e}")
    if worst["ticker"] != best["ticker"] or worst["alert_date"] != best["alert_date"]:
        try:
            out["worst"] = {
                "ticker": worst["ticker"],
                "alert_date": worst["alert_date"].isoformat(),
                "pnl": round(float(worst["total_pnl"]), 2),
                "narrative": await generate_postmortem_narrative(
                    worst["ticker"], worst["alert_date"]
                ),
            }
        except Exception as e:
            logger.warning(f"Weekly postmortem (worst) failed: {e}")
    return out


from agents.market_intelligence.prose_markers import NEGATIVE_CATALYST_MARKERS_BASE

# Post-mortem loser grading adds retrospective signals (litigation language,
# "or catalyst" tail) that the live EP downgrade gate intentionally doesn't fire on.
_LOSER_NEGATIVE_PROSE_MARKERS = NEGATIVE_CATALYST_MARKERS_BASE + (
    "no specific news or catalyst",
    "class action",
    "lawsuit",
)


async def _aggregate_loser_breakdown(window_start: date) -> dict:
    """Per-loser systematic post-mortem for the weekly digest (#76, 2026-05-11).

    For each closed losing trade in the window, joins to mi_ep_alerts +
    mi_orb_shadow_trades + mi_audit_log to surface methodology-tuning
    signals invisible in aggregate P&L: catalyst-prose vs grade mismatch,
    1-min vs 5-min ORB comparison, gap-through severity, time-to-stop,
    re-entry compound-loss pattern.

    Returns {"losers": [...], "aggregates": {...}}. Empty dict when no
    losing closed trades in window.
    """
    from agents.market_intelligence.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        losers = await conn.fetch("""
            SELECT
                t.id, t.ticker, t.alert_date, t.signal_type, t.entry_attempt,
                t.account_mode, t.total_pnl, t.entry_price, t.stop_price,
                t.orb_high, t.orb_low, t.filled_at, t.closed_at, t.exits,
                a.ep_score, a.catalyst_quality, a.catalyst AS catalyst_prose,
                a.pm_rvol, a.gap_pct
            FROM mi_live_trades t
            LEFT JOIN mi_ep_alerts a
                ON a.ticker = t.ticker AND a.alert_date = t.alert_date
            WHERE t.status = 'closed'
              AND t.alert_date >= $1
              AND t.total_pnl < 0
            ORDER BY t.total_pnl ASC
        """, window_start)

        if not losers:
            return {}

        # 5-min ORB shadow for the same (ticker, alert_date) pairs.
        shadow_rows = await conn.fetch("""
            SELECT ticker, alert_date,
                   orb_high::numeric AS s5_orb_high,
                   orb_low::numeric AS s5_orb_low,
                   status AS s5_status,
                   skip_reason AS s5_skip_reason
            FROM mi_orb_shadow_trades
            WHERE bar_size_minutes = 5
              AND alert_date >= $1
        """, window_start)
        shadow_idx = {
            (r["ticker"], r["alert_date"]): dict(r) for r in shadow_rows
        }

        # Earnings-boost audit events keyed by ticker+alert_date.
        boost_rows = await conn.fetch("""
            SELECT summary, (created_at AT TIME ZONE 'America/New_York')::date AS et_date
            FROM mi_audit_log
            WHERE event_type = 'catalyst_earnings_boost'
              AND created_at::date >= $1
        """, window_start)
        # Summary format: "MNDY: routine → strong (earnings_day, source=...)"
        boosted: set[tuple] = set()
        for r in boost_rows:
            summary = r["summary"] or ""
            tick = summary.split(":")[0].strip()
            if tick:
                boosted.add((tick, r["et_date"]))

    def _negative_prose(prose: str | None) -> list[str]:
        if not prose:
            return []
        lower = prose.lower()
        hits = []
        for marker in _LOSER_NEGATIVE_PROSE_MARKERS:
            if marker in lower:
                hits.append(marker)
        return hits

    losers_out: list[dict] = []
    n_blocked_by_5m = 0
    n_wider_stop_5m = 0
    n_prose_mismatch = 0
    n_fast_stop = 0
    n_compound_attempt2 = 0
    gap_through_cents: list[float] = []

    for row in losers:
        trade = dict(row)
        ticker = trade["ticker"]
        alert_d = trade["alert_date"]

        # Parse exits[] for stop fill details.
        exits = trade["exits"]
        if isinstance(exits, str):
            try:
                exits = json.loads(exits)
            except Exception:
                exits = []
        if not isinstance(exits, list):
            exits = []
        # Pair the stop with its OWN attempt. The trade's filled_at reflects
        # the CURRENT (latest) attempt's fill — so for time-to-stop and
        # gap-through we want the stop_hit that BELONGS to that attempt,
        # not attempt 1's stop on a re-entered trade. exits[] is chronological;
        # the last stop_hit corresponds to the most recent attempt and
        # therefore pairs with the current filled_at.
        stop_hits = [e for e in exits if e.get("reason") == "stop_hit"]
        last_stop = stop_hits[-1] if stop_hits else None

        # Gap-through severity: fill price vs stop price (positive = past stop).
        stop_price = float(trade["stop_price"]) if trade.get("stop_price") else None
        gap_through_dollars: float | None = None
        if last_stop and stop_price:
            try:
                gap_through_dollars = round(
                    float(stop_price) - float(last_stop.get("price") or 0), 4
                )
                if gap_through_dollars > 0:
                    gap_through_cents.append(gap_through_dollars)
            except Exception:
                pass

        # Time-to-stop: filled_at → matching attempt's stop_hit time.
        time_to_stop_min: float | None = None
        if last_stop and trade.get("filled_at"):
            try:
                from datetime import datetime as _dt
                ts_raw = last_stop.get("time")
                if ts_raw:
                    ts = _dt.fromisoformat(ts_raw.replace("Z", "+00:00")) if isinstance(ts_raw, str) else ts_raw
                    if ts.tzinfo is None:
                        from datetime import timezone as _tz
                        ts = ts.replace(tzinfo=_tz.utc)
                    fa = trade["filled_at"]
                    if fa.tzinfo is None:
                        from datetime import timezone as _tz
                        fa = fa.replace(tzinfo=_tz.utc)
                    time_to_stop_min = round((ts - fa).total_seconds() / 60.0, 1)
                    if time_to_stop_min < 10:
                        n_fast_stop += 1
            except Exception:
                pass

        # Catalyst prose vs grade.
        prose_markers = _negative_prose(trade.get("catalyst_prose"))
        earnings_boosted = (ticker, alert_d) in boosted
        # Mismatch flag: graded strong but prose has negative markers AND
        # no earnings backstop fired. The earnings boost is a legitimate
        # reason for "strong" without specific-news prose, so excluding
        # boosted tickers avoids false positives (MNDY 5/11 class).
        prose_mismatch = (
            trade.get("catalyst_quality") == "strong"
            and bool(prose_markers)
            and not earnings_boosted
        )
        if prose_mismatch:
            n_prose_mismatch += 1

        # 5-min ORB comparison.
        s5 = shadow_idx.get((ticker, alert_d))
        s5_verdict = "no_shadow_data"
        if s5:
            s5_status = (s5.get("s5_status") or "").lower()
            if s5_status == "gate_blocked":
                s5_verdict = "would_block"
                n_blocked_by_5m += 1
            elif s5.get("s5_orb_low") is not None and trade.get("orb_low") is not None:
                if float(s5["s5_orb_low"]) + 0.01 < float(trade["orb_low"]):
                    s5_verdict = "wider_stop"
                    n_wider_stop_5m += 1
                else:
                    s5_verdict = "similar_stop"
            else:
                s5_verdict = "shadow_no_levels"

        # Compound-loss check: if attempt 2 exists, are the two stop losses
        # within 15% of each other (i.e., paid the same loss twice)?
        is_compound = False
        if int(trade.get("entry_attempt") or 1) >= 2:
            stop_hits = [e for e in exits if e.get("reason") == "stop_hit"]
            if len(stop_hits) >= 2:
                p1 = float(stop_hits[0].get("pnl") or 0)
                p2 = float(stop_hits[1].get("pnl") or 0)
                if p1 < 0 and p2 < 0:
                    ratio = abs((p2 - p1) / p1) if p1 != 0 else 1.0
                    if ratio < 0.15:
                        is_compound = True
                        n_compound_attempt2 += 1

        losers_out.append({
            "ticker": ticker,
            "alert_date": alert_d.isoformat(),
            "signal_type": trade.get("signal_type"),
            "account_mode": trade.get("account_mode"),
            "entry_attempt": int(trade.get("entry_attempt") or 1),
            "total_pnl": round(float(trade["total_pnl"]), 2),
            "entry_price": float(trade["entry_price"]) if trade.get("entry_price") else None,
            "stop_price": stop_price,
            "ep_score": float(trade["ep_score"]) if trade.get("ep_score") else None,
            "catalyst_quality": trade.get("catalyst_quality"),
            "earnings_boost_fired": earnings_boosted,
            "prose_negative_markers": prose_markers,
            "prose_mismatch": prose_mismatch,
            "orb1_low": float(trade["orb_low"]) if trade.get("orb_low") else None,
            "orb1_high": float(trade["orb_high"]) if trade.get("orb_high") else None,
            "orb5_low": float(s5["s5_orb_low"]) if s5 and s5.get("s5_orb_low") is not None else None,
            "orb5_high": float(s5["s5_orb_high"]) if s5 and s5.get("s5_orb_high") is not None else None,
            "orb5_verdict": s5_verdict,
            "orb5_skip_reason": s5.get("s5_skip_reason") if s5 else None,
            "gap_through_dollars": gap_through_dollars,
            "time_to_stop_min": time_to_stop_min,
            "is_compound_loss": is_compound,
        })

    n = len(losers_out)
    total_loss = sum(L["total_pnl"] for L in losers_out)
    aggregates = {
        "n_losers": n,
        "total_loss": round(total_loss, 2),
        "pct_5m_would_block": round(100.0 * n_blocked_by_5m / n, 1) if n else 0.0,
        "pct_5m_wider_stop": round(100.0 * n_wider_stop_5m / n, 1) if n else 0.0,
        "pct_prose_mismatch": round(100.0 * n_prose_mismatch / n, 1) if n else 0.0,
        "pct_fast_stop_lt_10min": round(100.0 * n_fast_stop / n, 1) if n else 0.0,
        "n_compound_attempt2": n_compound_attempt2,
        "median_gap_through_dollars": (
            round(sorted(gap_through_cents)[len(gap_through_cents) // 2], 4)
            if gap_through_cents else None
        ),
    }
    return {"losers": losers_out, "aggregates": aggregates}


async def _aggregate_ep_outcomes(days: int) -> dict:
    rows = await get_ep_outcomes(days_back=days)
    by_tier: dict[str, dict] = defaultdict(lambda: {"total": 0, "green": 0, "fwd_1w_sum": 0.0, "fwd_1w_n": 0})
    by_catalyst: dict[str, dict] = defaultdict(lambda: {"total": 0, "green": 0})
    trade_status_counts: Counter = Counter()
    for r in rows:
        tier = r.get("score_tier") or "unknown"
        catalyst = r.get("catalyst_quality") or "unknown"
        fwd = r.get("fwd_1w_pct")
        green = fwd is not None and fwd > 0
        by_tier[tier]["total"] += 1
        by_catalyst[catalyst]["total"] += 1
        trade_status_counts[r.get("trade_status") or "unknown"] += 1
        if green:
            by_tier[tier]["green"] += 1
            by_catalyst[catalyst]["green"] += 1
        if fwd is not None:
            by_tier[tier]["fwd_1w_sum"] += float(fwd)
            by_tier[tier]["fwd_1w_n"] += 1
    return {
        "total": len(rows),
        "by_tier": {t: _finalize_bucket(b) for t, b in by_tier.items()},
        "by_catalyst": {c: _finalize_bucket(b) for c, b in by_catalyst.items()},
        "trade_status": dict(trade_status_counts),
    }


async def _aggregate_9m_outcomes(days: int) -> dict:
    # 9M outcomes live in mi_signal_outcomes with signal_type='9m_ep'.
    # Reuse get_ep_outcomes shape by querying the joined table inline via the
    # audit log? No — simpler: reuse the history endpoint + outcomes join.
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT a.ticker, a.alert_date, a.is_anticipation,
                   o.fwd_1d_pct, o.fwd_1w_pct
            FROM mi_9m_ep_alerts a
            LEFT JOIN mi_signal_outcomes o
                ON o.signal_type = '9m_ep'
                AND o.signal_date = a.alert_date
                AND o.identifier = a.ticker
            WHERE a.alert_date >= CURRENT_DATE - $1::int
        """, days)
    total = len(rows)
    with_outcome = [r for r in rows if r["fwd_1w_pct"] is not None]
    green = sum(1 for r in with_outcome if r["fwd_1w_pct"] > 0)
    avg_1w = (sum(float(r["fwd_1w_pct"]) for r in with_outcome) / len(with_outcome)) if with_outcome else None
    return {
        "total": total,
        "with_outcome": len(with_outcome),
        "green": green,
        "win_rate": (green / len(with_outcome)) if with_outcome else None,
        "avg_fwd_1w_pct": round(avg_1w, 2) if avg_1w is not None else None,
    }


async def _aggregate_paper_trades(window_start: date) -> dict:
    all_rows = await get_paper_trade_stats()
    rows = [r for r in all_rows if r.get("alert_date") and r["alert_date"] >= window_start]
    if not rows:
        return {"total_closed": 0, "win_rate": None, "avg_pnl_pct": None, "best": None, "worst": None}
    pnls = [float(r["total_pnl"]) for r in rows if r.get("total_pnl") is not None]
    wins = [p for p in pnls if p > 0]
    best = max(rows, key=lambda r: float(r.get("total_pnl") or 0))
    worst = min(rows, key=lambda r: float(r.get("total_pnl") or 0))
    return {
        "total_closed": len(rows),
        "win_rate": round(len(wins) / len(pnls), 3) if pnls else None,
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 2) if pnls else None,
        "best": {"ticker": best["ticker"], "pnl": round(float(best.get("total_pnl") or 0), 2)},
        "worst": {"ticker": worst["ticker"], "pnl": round(float(worst.get("total_pnl") or 0), 2)},
    }


async def _aggregate_audit_errors(days: int) -> dict:
    """Silent-failure surface — captures *_error AND *_failed event types
    across the past `days`. The 2026-05-10 EP scan outcomes typo lurked
    for weeks because it logged only via logger.error and never hit
    audit. Going forward, any try/except path that catches a job-level
    failure must emit an audit event ending in _error or _failed —
    this aggregator surfaces them unconditionally in the weekly digest."""
    since_hours = days * 24
    err_rows = await get_audit_log(limit=500, since_hours=since_hours, event_type_like="%error%")
    failed_rows = await get_audit_log(limit=500, since_hours=since_hours, event_type_like="%_failed%")
    # Merge + de-dup (a single event_type matching both globs counts once)
    merged: dict[str, int] = {}
    for r in err_rows:
        merged[r["event_type"]] = merged.get(r["event_type"], 0) + 1
    for r in failed_rows:
        # Avoid double-counting events that match both filters
        if r["event_type"] not in {er["event_type"] for er in err_rows}:
            merged[r["event_type"]] = merged.get(r["event_type"], 0) + 1
    top5 = sorted(merged.items(), key=lambda kv: -kv[1])[:5]
    return {
        "total": sum(merged.values()),
        "top_types": [{"event_type": t, "count": c} for t, c in top5],
    }


async def _aggregate_theme_churn(days: int) -> dict:
    rows = await get_weekly_theme_churn(days=days)
    return {
        "total_high_churn_pairs": len(rows),
        "top": [
            {
                "ticker": r["ticker"],
                "theme": r["theme_name"],
                "adds": r["add_count"],
                "removes": r["remove_count"],
                "events": r["event_count"],
            }
            for r in rows[:10]
        ],
    }


async def _aggregate_cooldowns(window_start: date) -> dict:
    active = await get_active_cooldowns()
    recent = [
        c for c in active
        if c.get("removed_at") and c["removed_at"].date() >= window_start
    ]
    return {
        "active_count": len(active),
        "triggered_this_week": len(recent),
        "recent": [
            {
                "ticker": r["ticker"],
                "theme": r["theme_name"],
                "reason": (r.get("removal_reason") or "")[:120],
            }
            for r in recent[:3]
        ],
    }


async def _aggregate_clusters(today: date) -> dict:
    rows = await get_correlation_clusters(today)
    if not rows:
        return {"count_today": 0, "avg_cohesion": None}
    cohesions = [float(r["mean_corr"]) for r in rows if r.get("mean_corr") is not None]
    return {
        "count_today": len({r["cluster_hash"] for r in rows}),
        "avg_cohesion": round(sum(cohesions) / len(cohesions), 3) if cohesions else None,
    }


async def _aggregate_regime(days: int) -> dict:
    current = await get_latest_regime()
    since_hours = days * 24
    transitions = await get_audit_log(
        limit=50, since_hours=since_hours, event_type="regime_transition"
    )
    return {
        "current": (current or {}).get("regime"),
        "ep_threshold": (current or {}).get("ep_threshold"),
        "transitions_this_week": len(transitions),
    }


async def _aggregate_crypto_readiness(window_days: int) -> dict:
    """Deterministic readiness audit of the crypto RS shadow-mode module.

    Returns a dict consumed by both Sonnet (for context) and the deterministic
    `_format_crypto_section` appendix. Verdict computed here, not by the LLM —
    "ready to flip" is binary; LLM judgment would muddy it.

    Returns empty dict if crypto schema isn't installed (graceful degradation
    for environments where the module hasn't been deployed yet).
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            schema_check = await conn.fetchval(
                "SELECT to_regclass('public.crypto_universe')"
            )
            if schema_check is None:
                return {}

            from agents.market_intelligence.constants import CRYPTO_RS_ENABLED

            universe_size = await conn.fetchval("SELECT COUNT(*) FROM crypto_universe")
            watchlist_total = await conn.fetchval("SELECT COUNT(*) FROM crypto_watchlist")
            watchlist_unresolved = await conn.fetchval(
                "SELECT COUNT(*) FROM crypto_watchlist WHERE coin_id LIKE '_unresolved_%'"
            )
            categories_pairs = await conn.fetchval("SELECT COUNT(*) FROM crypto_categories")
            rs_history_days = await conn.fetchval(
                "SELECT COUNT(DISTINCT score_date) FROM crypto_rs_scores"
            ) or 0
            macro_history_days = await conn.fetchval(
                "SELECT COUNT(DISTINCT date) FROM crypto_total3"
            ) or 0
            stablecoin_history_days = await conn.fetchval(
                "SELECT COUNT(DISTINCT date) FROM crypto_stablecoin_flows"
            ) or 0

            ingest_attempts_7d = await conn.fetchval(
                """
                SELECT COUNT(*) FROM mi_audit_log
                WHERE event_type = 'crypto_ingest_completed'
                  AND created_at >= NOW() - INTERVAL '7 days'
                """
            ) or 0
            ingest_errors_7d = await conn.fetchval(
                """
                SELECT COUNT(*) FROM mi_audit_log
                WHERE event_type = 'crypto_ingest_error'
                  AND created_at >= NOW() - INTERVAL '7 days'
                """
            ) or 0
            last_trigger_row = await conn.fetchrow(
                """
                SELECT triggered_at, alert_type FROM crypto_dominance_alerts
                ORDER BY triggered_at DESC LIMIT 1
                """
            )
            pre_arm_7d = await conn.fetchval(
                """
                SELECT COUNT(*) FROM mi_audit_log
                WHERE event_type = 'crypto_trigger_pre_arm'
                  AND created_at >= NOW() - INTERVAL '7 days'
                """
            ) or 0
    except Exception as e:
        logger.exception("crypto readiness audit failed")
        # Write to mi_audit_log so the daily error-check surface picks it up;
        # otherwise a dropped table or schema rename makes this section silently
        # disappear from weekly digests forever.
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "crypto_readiness_audit_error",
                f"weekly review crypto aggregator crashed: {type(e).__name__}",
                str(e)[:4000],
            )
        except Exception:
            pass  # double-failure: nothing more we can do
        return {}

    # Hard gates for "ready to flip"
    blockers: list[str] = []
    if rs_history_days < 30:
        blockers.append(f"need {30 - rs_history_days} more days of RS history (have {rs_history_days}d)")
    if macro_history_days < 90:
        blockers.append(f"need {90 - macro_history_days} more days of macro history for trigger SMA90 (have {macro_history_days}d)")
    if watchlist_unresolved and watchlist_unresolved > 0:
        blockers.append(f"{watchlist_unresolved} watchlist coin(s) still unresolved")
    if categories_pairs == 0:
        blockers.append("crypto_categories empty (Sunday refresh hasn't populated yet)")
    if ingest_errors_7d > 0:
        blockers.append(f"{ingest_errors_7d} crypto_ingest_error events in last 7d")
    if ingest_attempts_7d < 6:
        blockers.append(f"only {ingest_attempts_7d}/7 nightly ingests succeeded (job may not be registered or running)")

    is_live = bool(CRYPTO_RS_ENABLED)
    if blockers:
        verdict_emoji = "⚠️" if (ingest_errors_7d > 0 or watchlist_unresolved > 0) else "⏳"
        verdict = f"{verdict_emoji} not ready: " + "; ".join(blockers)
    elif is_live:
        # Already flipped; gates clean = ongoing health, not a call to action.
        verdict = "✅ live; gates clean"
    else:
        verdict = "✅ ready to flip CRYPTO_RS_ENABLED=true"

    return {
        "shadow_mode": not CRYPTO_RS_ENABLED,
        "universe_size": universe_size,
        "watchlist_total": watchlist_total,
        "watchlist_unresolved": watchlist_unresolved,
        "categories_pairs": categories_pairs,
        "rs_history_days": rs_history_days,
        "macro_history_days": macro_history_days,
        "stablecoin_history_days": stablecoin_history_days,
        "ingest_attempts_7d": ingest_attempts_7d,
        "ingest_errors_7d": ingest_errors_7d,
        "pre_arm_7d": pre_arm_7d,
        "last_trigger_at": last_trigger_row["triggered_at"].isoformat() if last_trigger_row else None,
        "blockers": blockers,
        "verdict": verdict,
    }


async def _aggregate_shadow_orb_outcomes(window_days: int) -> dict:
    """Compare 5-min shadow ORB outcomes to live 1-min ORB on the same alerts.

    Joins `mi_orb_shadow_trades` (5m ORB, telemetry-only) to `mi_live_trades`
    on `(ticker, alert_date)` so per-alert R deltas surface — population
    averages would mask "5m wins on bounce, loses on extended" because
    bucket-level dilutes the per-alert truth.

    Returns empty dict if `mi_orb_shadow_trades` doesn't exist (graceful
    degradation for environments where the schema migration hasn't run).

    Slice caveat: `shape_tag` is populated only on `signal_type='9m_day2'`
    rows. MAGNA53 rows store NULL — by-shape deltas are 9M-cohort only.
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            schema_check = await conn.fetchval(
                "SELECT to_regclass('public.mi_orb_shadow_trades')"
            )
            if schema_check is None:
                return {}

            counts = await conn.fetchrow(
                """
                SELECT
                  COUNT(*) FILTER (WHERE status='open' OR status='closed') AS entered,
                  COUNT(*) FILTER (WHERE status='no_entry')                AS no_entry,
                  COUNT(*) FILTER (WHERE status='gate_blocked')            AS gate_blocked
                FROM mi_orb_shadow_trades
                WHERE bar_size_minutes = 5
                  AND alert_date >= CURRENT_DATE - ($1::int * INTERVAL '1 day')
                """,
                window_days,
            )

            paired = await conn.fetch(
                """
                WITH paired AS (
                  SELECT
                    shadow.ticker,
                    shadow.alert_date,
                    shadow.signal_type,
                    shadow.shape_tag,
                    live.total_pnl   / NULLIF(live.risk_dollars,   0) AS r_1m,
                    shadow.total_pnl / NULLIF(shadow.risk_dollars, 0) AS r_5m
                  FROM mi_orb_shadow_trades shadow
                  JOIN mi_live_trades live
                    ON live.ticker = shadow.ticker
                   AND live.alert_date = shadow.alert_date
                  WHERE shadow.bar_size_minutes = 5
                    AND shadow.alert_date >= CURRENT_DATE - ($1::int * INTERVAL '1 day')
                    AND shadow.status = 'closed'
                    AND live.status   = 'closed'
                    AND shadow.risk_dollars > 0
                    AND live.risk_dollars > 0
                )
                SELECT
                  signal_type,
                  shape_tag,
                  COUNT(*)            AS n_paired,
                  AVG(r_1m)           AS avg_r_1m,
                  AVG(r_5m)           AS avg_r_5m,
                  AVG(r_5m - r_1m)    AS per_alert_delta
                FROM paired
                GROUP BY signal_type, shape_tag
                ORDER BY per_alert_delta DESC NULLS LAST
                """,
                window_days,
            )
    except Exception:
        logger.exception("shadow_orb aggregator failed")
        return {}

    paired_rows = [dict(r) for r in paired]
    total_paired = sum(int(r["n_paired"] or 0) for r in paired_rows)

    by_shape = [
        {
            "signal_type": r["signal_type"],
            "shape_tag": r["shape_tag"],
            "n": int(r["n_paired"] or 0),
            "avg_r_1m": round(float(r["avg_r_1m"] or 0), 2),
            "avg_r_5m": round(float(r["avg_r_5m"] or 0), 2),
            "per_alert_delta": round(float(r["per_alert_delta"] or 0), 2),
        }
        for r in paired_rows
        if (r["n_paired"] or 0) >= 5
    ]

    return {
        "entered": int(counts["entered"] or 0),
        "no_entry": int(counts["no_entry"] or 0),
        "gate_blocked": int(counts["gate_blocked"] or 0),
        "paired_closed_total": total_paired,
        "by_shape": by_shape[:5],
    }


async def _aggregate_wick_outcomes(window_days: int) -> dict:
    """Wick-fill (P22) telemetry roll-up — pure forward-return cohort stats.

    Two anchors per candidate (see wick_tracker.update_forward_returns):
      * `fwd_3d_from_high_pct`  — close − prior_high, conditional on fill
        (NULL on rows that never broke prior_high in the 10-session window)
      * `fwd_3d_from_close_pct` — close − Day1 close, unconditional
        (the all-settled drift baseline)

    The gap between the two medians IS the strategy's edge. If filled cohort
    drift ≈ baseline drift, wick-fill isn't doing anything special.

    Returns empty dict if `mi_wick_candidates` doesn't exist.
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            schema_check = await conn.fetchval(
                "SELECT to_regclass('public.mi_wick_candidates')"
            )
            if schema_check is None:
                return {}

            row = await conn.fetchrow(
                """
                SELECT
                  COUNT(*)                                                AS n_total,
                  COUNT(*) FILTER (WHERE fwd_10d_from_close_pct IS NOT NULL) AS n_settled,
                  COUNT(*) FILTER (WHERE filled_wick = TRUE)              AS n_filled,
                  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fwd_3d_from_high_pct)
                    FILTER (WHERE fwd_3d_from_high_pct IS NOT NULL)       AS median_fwd_3d_from_high,
                  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fwd_3d_from_close_pct)
                    FILTER (WHERE fwd_3d_from_close_pct IS NOT NULL)      AS median_fwd_3d_from_close
                FROM mi_wick_candidates
                WHERE alert_date >= CURRENT_DATE - ($1::int * INTERVAL '1 day')
                """,
                window_days,
            )
    except Exception:
        logger.exception("wick aggregator failed")
        return {}

    n_total = int(row["n_total"] or 0)
    n_settled = int(row["n_settled"] or 0)
    n_filled = int(row["n_filled"] or 0)
    fill_rate = round(n_filled / n_settled, 3) if n_settled else None
    med_high = row["median_fwd_3d_from_high"]
    med_close = row["median_fwd_3d_from_close"]
    return {
        "n_total": n_total,
        "n_settled": n_settled,
        "n_filled": n_filled,
        "fill_rate": fill_rate,
        "median_fwd_3d_from_high": round(float(med_high), 2) if med_high is not None else None,
        "median_fwd_3d_from_close": round(float(med_close), 2) if med_close is not None else None,
    }


async def _aggregate_fishhook_outcomes(window_days: int) -> dict:
    """Fishhook V3 (TI3) telemetry roll-up — gap-up undercut & reclaim.

    Reframed post-Stage-0 as a base-rate harvester (R≈1.1, hit≈13-19%),
    NOT the original "deep-drift = explosive reclaim" thesis. Surfaces:
      * state distribution (anchor count, promotion/reclaim/settle rates)
      * R + hit-rate on settled rows (settled = reclaimed and held 5d)
      * shallow vs deep drift slice — confirms the inverted-edge finding
        as data accrues; if deep drift starts winning, threshold revisit.

    Returns empty dict if `mi_fishhook_anchors` doesn't exist.
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            schema_check = await conn.fetchval(
                "SELECT to_regclass('public.mi_fishhook_anchors')"
            )
            if schema_check is None:
                return {}

            row = await conn.fetchrow(
                """
                WITH w AS (
                    SELECT * FROM mi_fishhook_anchors
                    WHERE anchor_date >= CURRENT_DATE - ($1::int * INTERVAL '1 day')
                ),
                settled AS (
                    SELECT * FROM w
                    WHERE state IN ('settled','invalidated') AND r_5d IS NOT NULL
                ),
                shallow AS (
                    SELECT r_5d FROM settled WHERE drift_pct_max > -0.05
                ),
                deep AS (
                    SELECT r_5d FROM settled WHERE drift_pct_max <= -0.08
                )
                SELECT
                  (SELECT COUNT(*) FROM w)                                        AS n_total,
                  (SELECT COUNT(*) FROM w WHERE state='pending')                  AS n_pending,
                  (SELECT COUNT(*) FROM w WHERE state='promoted')                 AS n_promoted,
                  (SELECT COUNT(*) FROM w WHERE state='reclaimed')                AS n_reclaimed,
                  (SELECT COUNT(*) FROM w WHERE state='settled')                  AS n_settled,
                  (SELECT COUNT(*) FROM w WHERE state='invalidated')              AS n_invalidated,
                  (SELECT COUNT(*) FROM w WHERE state='expired_no_promotion')     AS n_no_promotion,
                  (SELECT COUNT(*) FROM w WHERE state='expired_no_reclaim')       AS n_no_reclaim,
                  (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r_5d) FROM settled) AS median_r,
                  (SELECT 1.0 * COUNT(*) FILTER (WHERE r_5d > 0) / NULLIF(COUNT(*), 0) FROM settled) AS hit_rate,
                  (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r_5d) FROM shallow) AS shallow_median_r,
                  (SELECT COUNT(*) FROM shallow)                                  AS n_shallow,
                  (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r_5d) FROM deep)    AS deep_median_r,
                  (SELECT COUNT(*) FROM deep)                                     AS n_deep
                """,
                window_days,
            )
    except Exception:
        logger.exception("fishhook aggregator failed")
        return {}

    n_total = int(row["n_total"] or 0)
    n_settled = int(row["n_settled"] or 0)
    return {
        "n_total": n_total,
        "n_pending": int(row["n_pending"] or 0),
        "n_promoted": int(row["n_promoted"] or 0),
        "n_reclaimed": int(row["n_reclaimed"] or 0),
        "n_settled": n_settled,
        "n_invalidated": int(row["n_invalidated"] or 0),
        "n_no_promotion": int(row["n_no_promotion"] or 0),
        "n_no_reclaim": int(row["n_no_reclaim"] or 0),
        "median_r": round(float(row["median_r"]), 2) if row["median_r"] is not None else None,
        "hit_rate": round(float(row["hit_rate"]), 3) if row["hit_rate"] is not None else None,
        "shallow_median_r": round(float(row["shallow_median_r"]), 2) if row["shallow_median_r"] is not None else None,
        "n_shallow": int(row["n_shallow"] or 0),
        "deep_median_r": round(float(row["deep_median_r"]), 2) if row["deep_median_r"] is not None else None,
        "n_deep": int(row["n_deep"] or 0),
    }


def _format_loser_section(loser_breakdown: dict) -> str:
    """Deterministic per-loser breakdown for the weekly digest (#76).

    Surfaces methodology-tuning signals (catalyst-prose mismatch, 1m vs
    5m ORB, gap-through, fast stops, compound losses) verbatim — no LLM
    paraphrasing so exact stop prices and verdicts land in the digest.
    """
    if not loser_breakdown:
        return ""
    losers = loser_breakdown.get("losers") or []
    agg = loser_breakdown.get("aggregates") or {}
    if not losers:
        return ""

    lines = [
        f"❌ *Losers post-mortem ({agg.get('n_losers', 0)} trades · "
        f"${agg.get('total_loss', 0):+,.0f})*",
    ]
    # Per-trade rows — most recent / largest loss first (already sorted ASC by pnl).
    # Cap to top 10 to keep digest scannable; aggregates capture the tail.
    for L in losers[:10]:
        flags = []
        if L.get("prose_mismatch"):
            flags.append("📰 prose↔grade")
        if L.get("orb5_verdict") == "would_block":
            flags.append("⛔ 5m blocked")
        elif L.get("orb5_verdict") == "wider_stop":
            flags.append(f"🪜 5m stop ${L['orb5_low']:.2f}")
        if (L.get("time_to_stop_min") or 999) < 10:
            flags.append(f"⏱ {L['time_to_stop_min']:.1f}m")
        if L.get("is_compound_loss"):
            flags.append("🔁 compound")
        if (L.get("gap_through_dollars") or 0) > 0.05:
            flags.append(f"⚡ gap-thru ${L['gap_through_dollars']:.2f}")
        if L.get("earnings_boost_fired"):
            flags.append("📅 earnings")
        attempt_marker = f" att{L['entry_attempt']}" if L.get("entry_attempt", 1) > 1 else ""
        flag_str = (" · " + " · ".join(flags)) if flags else ""
        lines.append(
            f"• `{L['ticker']}` {L['alert_date']}{attempt_marker} "
            f"${L['total_pnl']:+,.0f}{flag_str}"
        )
    if len(losers) > 10:
        lines.append(f"_(+ {len(losers) - 10} more losers, see DB row)_")

    # Aggregate roll-up — the methodology signals worth tracking week-over-week.
    n = agg.get("n_losers", 0)
    median_gt = agg.get("median_gap_through_dollars")
    agg_bits = [
        f"5m-blocked: {agg.get('pct_5m_would_block', 0):.0f}%",
        f"5m-wider: {agg.get('pct_5m_wider_stop', 0):.0f}%",
        f"prose-mismatch: {agg.get('pct_prose_mismatch', 0):.0f}%",
        f"fast-stop<10m: {agg.get('pct_fast_stop_lt_10min', 0):.0f}%",
    ]
    if median_gt is not None:
        agg_bits.append(f"med gap-thru ${median_gt:.2f}")
    if agg.get("n_compound_attempt2", 0):
        agg_bits.append(f"compound att2: {agg['n_compound_attempt2']}")
    lines.append("_" + " · ".join(agg_bits) + "_")
    lines.append(
        f"_Legend: 📰=catalyst grade vs prose mismatch · ⛔=5m ORB would block · "
        f"🪜=5m ORB stop wider · ⏱=stopped <10m post-fill · 🔁=att2 loss within 15% "
        f"of att1 · ⚡=fill past stop · 📅=earnings backstop fired_"
    )
    return "\n".join(lines)


def _format_crypto_section(crypto: dict) -> str:
    """Render the deterministic crypto-readiness appendix for the weekly digest.

    Returns empty string if the module isn't installed (skips the section
    entirely rather than emitting a misleading "0 days" line).
    """
    if not crypto:
        return ""

    # Telegram parse_mode="Markdown" (legacy) does NOT support `**bold**` — use
    # single asterisks. Unbalanced ** would also break the whole appendix.
    mode = "shadow mode" if crypto.get("shadow_mode") else "LIVE"
    universe = crypto.get("universe_size") or 0
    wl_total = crypto.get("watchlist_total") or 0
    wl_unresolved = crypto.get("watchlist_unresolved") or 0
    wl_marker = "all resolved ✓" if wl_unresolved == 0 else f"{wl_unresolved} unresolved ⚠"
    cats = crypto.get("categories_pairs") or 0
    cats_marker = "" if cats > 0 else " ⚠"
    rs_days = crypto.get("rs_history_days") or 0
    macro_days = crypto.get("macro_history_days") or 0
    attempts = crypto.get("ingest_attempts_7d") or 0
    errors = crypto.get("ingest_errors_7d") or 0
    pre_arm = crypto.get("pre_arm_7d") or 0

    lines = [
        f"🪙 *Crypto RS — {mode}*",
        f"History: {rs_days}d RS · {macro_days}d macro",
        f"Universe: {universe} coins · {wl_total} watchlist ({wl_marker})",
        f"Categories: {cats} pairs{cats_marker}",
        f"Last 7d: {attempts}/7 ingests · {errors} errors",
    ]
    if pre_arm > 0:
        lines.append(f"Pre-arm: stables flowing in but alts not rotating ({pre_arm} of last 7 days)")
    if crypto.get("last_trigger_at"):
        lines.append(f"Last trigger fire: {crypto['last_trigger_at'][:10]}")
    lines.append(f"Verdict: {crypto.get('verdict') or '(unknown)'}")
    return "\n".join(lines)


def _finalize_bucket(b: dict) -> dict:
    total = b["total"]
    out = {"total": total, "green": b["green"]}
    if total:
        out["win_rate"] = round(b["green"] / total, 3)
    if b.get("fwd_1w_n"):
        out["avg_fwd_1w_pct"] = round(b["fwd_1w_sum"] / b["fwd_1w_n"], 2)
    return out


# ── LLM synthesis ─────────────────────────────────────────────────────────────


async def _synthesize(metrics: dict, prior: dict | None) -> str:
    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    prior_block = ""
    if prior:
        prior_block = (
            f"\n\nPREVIOUS REVIEW ({prior['review_date']}, window={prior['window_days']}d):\n"
            f"Suggestions last week: {prior.get('suggestions')}\n"
            f"Metrics last week: {prior.get('metrics')}\n"
        )
    user_prompt = (
        f"THIS WEEK'S METRICS (window={metrics['window']['days']}d, "
        f"{metrics['window']['start']} → {metrics['window']['end']}):\n"
        f"{json.dumps(metrics, default=str, indent=2)}"
        f"{prior_block}"
    )
    resp = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in resp.content if hasattr(block, "text")).strip()


def _extract_suggestions(summary: str) -> list[str]:
    """Parse the '💡 Proposed changes' block — numbered list of 1-2 lines."""
    out: list[str] = []
    in_block = False
    for line in summary.splitlines():
        stripped = line.strip()
        if "Proposed changes" in stripped:
            in_block = True
            continue
        if in_block:
            if stripped.startswith(("🔁", "⚠️", "✅")) or not stripped:
                if out:  # end of block
                    break
                continue
            # Strip leading "1.", "2.", "-", "•"
            cleaned = stripped.lstrip("0123456789.•- \t")
            if cleaned:
                out.append(cleaned)
    return out
