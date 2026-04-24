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
    anomalies = await _aggregate_anomalies(window_days)

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
    }


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
    since_hours = days * 24
    rows = await get_audit_log(limit=500, since_hours=since_hours, event_type_like="%error%")
    counts = Counter(r["event_type"] for r in rows)
    top5 = counts.most_common(5)
    return {
        "total": sum(counts.values()),
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
