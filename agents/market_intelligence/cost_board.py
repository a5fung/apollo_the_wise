"""#378 Cost-observability Phase 2 — THE TOTAL + THE ALARM (operator 6/25).

The #377 meter (spend_tracker → api_usage) counts every metered LLM call;
the weekly review's spend appendix (S-C, FL-6) shows MTD once a week. This
module adds the two missing operator surfaces:

- **/cost board** (on demand): full operating total = metered VARIABLE spend
  (Claude + Perplexity, from api_usage) + the FLAT subscriptions, with MTD,
  month projection, budget headroom and top callers.
- **THE ALARM** (daily 17:52 ET job): Telegram WARN when (a) MTD variable
  spend exceeds ANTHROPIC_MONTHLY_BUDGET (the operator's cap on the VARIABLE
  half — flat is fixed, no alarm on it, operator 6/25), or (b) today's spend
  is a >2× trailing-30d-median daily anomaly. Silent otherwise (the series
  already lives in api_usage); an audit row records every fired alarm.

Flat numbers are the operator's 6/25 figures. OPEN QUESTION carried on the
board verbatim (operator 6/25): does Massive include/replace Polygon+FMP, or
are those separate lines? The board says what it knows and names the gap.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta

from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

# Operator-stated flat subscriptions (2026-06-25), USD/month.
FLAT_SUBS_MONTHLY: dict[str, float] = {
    "Hetzner": 15.0,
    "Massive (market data)": 33.0,
    "Alpaca Algo Trader Plus": 100.0,
}
FLAT_TOTAL = sum(FLAT_SUBS_MONTHLY.values())

# Daily-anomaly floor: below this, a "2× median" trip is noise, not signal.
ANOMALY_MIN_USD = 1.00


def _budget() -> float:
    try:
        return float(os.environ.get("ANTHROPIC_MONTHLY_BUDGET", "0") or 0)
    except ValueError:
        return 0.0


async def compute_cost_board(today: date) -> dict:
    """One read of api_usage → the full picture. All date math in ET (the
    operator's billing mental model), via AT TIME ZONE on the TIMESTAMPTZ."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Raw-timestamp prefilter (review 7/17): the ET-date conversion inside
        # WHERE defeats idx_api_usage_created and scanned the WHOLE unboundedly-
        # growing table on every /cost + daily alarm. 46 days generously covers
        # month-start AND the 31-day daily window under any ET/UTC skew; the
        # exact ET-date logic applies AFTER the indexed cut.
        row = await conn.fetchrow("""
            WITH et AS (
                SELECT cost_usd, model, caller,
                       (created_at AT TIME ZONE 'America/New_York')::date AS d
                FROM api_usage
                WHERE created_at >= $1::date - INTERVAL '46 days'
            )
            SELECT
              COALESCE(SUM(cost_usd) FILTER (WHERE d >= date_trunc('month', $1::date)), 0) AS mtd,
              COALESCE(SUM(cost_usd) FILTER (WHERE d >= date_trunc('month', $1::date)
                                             AND model ILIKE 'perplexity%'), 0)            AS mtd_pplx,
              COALESCE(SUM(cost_usd) FILTER (WHERE d = $1::date), 0)                       AS today,
              COUNT(*)  FILTER (WHERE d >= date_trunc('month', $1::date))                  AS mtd_calls
            FROM et
        """, today)
        daily = await conn.fetch("""
            SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d,
                   SUM(cost_usd) AS spend
            FROM api_usage
            WHERE created_at >= $1::date - INTERVAL '32 days'
              AND (created_at AT TIME ZONE 'America/New_York')::date
                  BETWEEN $1::date - 30 AND $1::date - 1
            GROUP BY 1 ORDER BY 1
        """, today)
        callers = await conn.fetch("""
            SELECT caller, SUM(cost_usd) AS spend
            FROM api_usage
            WHERE created_at >= $1::date - INTERVAL '46 days'
              AND (created_at AT TIME ZONE 'America/New_York')::date
                  >= date_trunc('month', $1::date)
            GROUP BY caller ORDER BY spend DESC LIMIT 3
        """, today)

    # True median over ALL 30 trailing days — quiet days count as $0 (review
    # 7/17: active-days-only + upper-middle-element inflated the baseline and
    # desensitized the 2× anomaly trigger).
    import statistics
    spend_by_day = {r["d"]: float(r["spend"]) for r in daily}
    series = [spend_by_day.get(today - timedelta(days=k), 0.0) for k in range(1, 31)]
    median30 = statistics.median(series) if series else 0.0
    mtd = float(row["mtd"])
    day_of_month = today.day
    days_in_month = (date(today.year + (today.month == 12), (today.month % 12) + 1, 1)
                     - date(today.year, today.month, 1)).days
    projected = mtd / day_of_month * days_in_month if day_of_month else mtd
    return {
        "today": today.isoformat(),
        "mtd_variable": round(mtd, 2),
        "mtd_perplexity": round(float(row["mtd_pplx"]), 2),
        "mtd_claude": round(mtd - float(row["mtd_pplx"]), 2),
        "mtd_calls": int(row["mtd_calls"]),
        "today_spend": round(float(row["today"]), 2),
        "median30_daily": round(median30, 2),
        "projected_variable": round(projected, 2),
        "budget": _budget(),
        "flat_total": FLAT_TOTAL,
        "top_callers": [(r["caller"], round(float(r["spend"]), 2)) for r in callers],
    }


def render_cost_board(d: dict) -> str:
    """Operator-facing /cost board. Dynamic tokens (caller names are
    snake_case) go inside a code block — the #477 parity class."""
    b = d["budget"]
    headroom = (f"${b - d['mtd_variable']:.2f} headroom"
                if b and d["mtd_variable"] <= b else
                f"⚠️ OVER by ${d['mtd_variable'] - b:.2f}" if b else
                "no budget set (ANTHROPIC-MONTHLY-BUDGET)")
    lines = [
        f"*💰 COST BOARD — {d['today']}*",
        "```",
        f"VARIABLE (metered)   MTD ${d['mtd_variable']:.2f} / {d['mtd_calls']} calls",
        f"  Claude             ${d['mtd_claude']:.2f}",
        f"  Perplexity         ${d['mtd_perplexity']:.2f}",
        f"  today ${d['today_spend']:.2f} · 30d median ${d['median30_daily']:.2f}/day",
        f"  projected month    ${d['projected_variable']:.2f}"
        + (f" vs budget ${b:.0f}" if b else ""),
        f"FLAT (subscriptions) ${d['flat_total']:.0f}/mo",
    ]
    for name, amt in FLAT_SUBS_MONTHLY.items():
        lines.append(f"  {name:<22} ${amt:.0f}")
    lines.append(f"FULL MONTH ≈ ${d['projected_variable'] + d['flat_total']:.2f} "
                 f"(variable proj + flat)")
    if d["top_callers"]:
        lines.append("top callers MTD:")
        for c, amt in d["top_callers"]:
            lines.append(f"  {c:<28} ${amt:.2f}")
    lines.append("```")
    lines.append(f"_{headroom} · flat: Massive-vs-Polygon/FMP overlap = open Q (6/25)_")
    return "\n".join(lines)


async def run_daily_spend_alarm(today: date) -> dict | None:
    """17:52 ET job. Fires Telegram + audit ONLY on breach (house rule:
    actionable-only). Two triggers, operator-ruled 6/25: monthly budget cap on
    the variable half AND a 2× trailing-30d-median daily anomaly."""
    d = await compute_cost_board(today)
    reasons = []
    if d["budget"] and d["mtd_variable"] > d["budget"]:
        # Once-per-month (review 7/17): without state this re-fired every
        # weekday for the rest of the month after the first breach — repeated
        # non-actionable Telegram. The audit log IS the state. (The 2×-median
        # anomaly below is naturally day-scoped and needs no dedupe. NB: the
        # orchestrator-side core/spend.py has its own 50/80/100%-crossing
        # alerts on the same table — this alarm is the market-agent EOD net.)
        pool = await get_pool()
        async with pool.acquire() as conn:
            already = await conn.fetchval("""
                SELECT COUNT(*) FROM mi_audit_log
                WHERE event_type = 'spend_alarm_fired'
                  AND summary LIKE '%budget%'
                  AND (created_at AT TIME ZONE 'America/New_York')::date
                      >= date_trunc('month', $1::date)
            """, today)
        if not already:
            reasons.append(f"MTD variable ${d['mtd_variable']:.2f} > budget ${d['budget']:.0f}")
    if (d["today_spend"] > ANOMALY_MIN_USD
            and d["median30_daily"] > 0
            and d["today_spend"] > 2 * d["median30_daily"]):
        reasons.append(f"today ${d['today_spend']:.2f} > 2× 30d median "
                       f"(${d['median30_daily']:.2f}/day)")
    if not reasons:
        return None
    await log_audit_event(
        "spend_alarm_fired",
        summary=f"LLM spend alarm: {'; '.join(reasons)}",
        detail=json.dumps(d),
    )
    from agents.market_intelligence.briefing import send_telegram_message
    await send_telegram_message(
        "🔴 *SPEND ALARM* — " + "; ".join(reasons) + "\n/cost for the full board")
    return d
