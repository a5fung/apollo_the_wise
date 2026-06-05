"""
API spend tracker — logs token usage per Anthropic call and provides
daily/monthly aggregation + budget alerts.

Pricing (as of 2026-03):
  Claude Sonnet 4.6:  $3.00/M input,  $15.00/M output
  Claude Haiku 4.5:   $0.80/M input,   $4.00/M output
  Cache write:        1.25× base input price
  Cache read:         0.10× base input price
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Pricing per million tokens ────────────────────────────────────────────────

_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}

# Fallback for unknown models
_DEFAULT_PRICING = {"input": 3.00, "output": 15.00}


def _cost_for_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Compute dollar cost for a single API call."""
    prices = _PRICING.get(model, _DEFAULT_PRICING)
    base_input = prices["input"]

    # Regular input tokens (exclude cached portions)
    regular_input = input_tokens - cache_creation_tokens - cache_read_tokens
    regular_input = max(regular_input, 0)

    cost = (
        (regular_input / 1_000_000) * base_input
        + (cache_creation_tokens / 1_000_000) * base_input * 1.25
        + (cache_read_tokens / 1_000_000) * base_input * 0.10
        + (output_tokens / 1_000_000) * prices["output"]
    )
    return round(cost, 6)


# ── Database ──────────────────────────────────────────────────────────────────

async def _get_pool():
    from core.memory import get_pool
    return await get_pool()


async def initialize_spend_schema() -> None:
    """Create api_usage table if it doesn't exist."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id              SERIAL PRIMARY KEY,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                model           TEXT NOT NULL,
                caller          TEXT NOT NULL,
                input_tokens    INT NOT NULL DEFAULT 0,
                output_tokens   INT NOT NULL DEFAULT 0,
                cache_creation  INT NOT NULL DEFAULT 0,
                cache_read      INT NOT NULL DEFAULT 0,
                cost_usd        DOUBLE PRECISION NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_api_usage_created
                ON api_usage(created_at);
        """)


async def log_api_usage(
    model: str,
    caller: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """
    Log a single API call's token usage.  Returns computed cost in USD.

    Args:
        model: Model ID (e.g. "claude-sonnet-4-6")
        caller: Where the call originated (e.g. "orchestrator", "context_compression")
        input_tokens: Total input tokens from response.usage
        output_tokens: Total output tokens from response.usage
        cache_creation_tokens: Tokens written to cache
        cache_read_tokens: Tokens read from cache
    """
    cost = _cost_for_call(
        model, input_tokens, output_tokens,
        cache_creation_tokens, cache_read_tokens,
    )

    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_usage
                    (model, caller, input_tokens, output_tokens,
                     cache_creation, cache_read, cost_usd)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                model, caller, input_tokens, output_tokens,
                cache_creation_tokens, cache_read_tokens, cost,
            )
    except Exception as e:
        logger.warning(f"Failed to log API usage: {e}")

    # Check budget alert (fire-and-forget)
    try:
        await _check_budget_alert(cost)
    except Exception:
        pass

    return cost


# ── Queries ───────────────────────────────────────────────────────────────────

async def get_spend_today() -> dict[str, Any]:
    """Return today's spend breakdown."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                caller,
                COUNT(*) AS calls,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(cache_read) AS cache_read,
                SUM(cost_usd) AS cost
            FROM api_usage
            WHERE created_at >= CURRENT_DATE
            GROUP BY caller
            ORDER BY cost DESC
        """)
        total = await conn.fetchrow("""
            SELECT
                COUNT(*) AS calls,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(cache_read) AS cache_read,
                SUM(cost_usd) AS cost
            FROM api_usage
            WHERE created_at >= CURRENT_DATE
        """)
    return {
        "date": date.today().isoformat(),  # tz-ok: paired with SQL CURRENT_DATE (server UTC) above
        "by_caller": [dict(r) for r in rows],
        "total": dict(total) if total else {},
    }


async def get_spend_month() -> dict[str, Any]:
    """Return current month's spend breakdown."""
    pool = await _get_pool()
    first_of_month = date.today().replace(day=1)  # tz-ok: month-boundary for server-relative cost query ($1 below)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                caller,
                COUNT(*) AS calls,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(cache_read) AS cache_read,
                SUM(cost_usd) AS cost
            FROM api_usage
            WHERE created_at >= $1
            GROUP BY caller
            ORDER BY cost DESC
        """, datetime(first_of_month.year, first_of_month.month, first_of_month.day))
        total = await conn.fetchrow("""
            SELECT
                COUNT(*) AS calls,
                SUM(cost_usd) AS cost
            FROM api_usage
            WHERE created_at >= $1
        """, datetime(first_of_month.year, first_of_month.month, first_of_month.day))
    return {
        "month": first_of_month.strftime("%B %Y"),
        "by_caller": [dict(r) for r in rows],
        "total": dict(total) if total else {},
    }


async def get_spend_summary() -> str:
    """Format a human-readable spend summary for Telegram."""
    today = await get_spend_today()
    month = await get_spend_month()

    budget = float(os.environ.get("ANTHROPIC_MONTHLY_BUDGET", "0"))

    today_cost = today["total"].get("cost") or 0
    today_calls = today["total"].get("calls") or 0
    today_cache = today["total"].get("cache_read") or 0
    month_cost = month["total"].get("cost") or 0
    month_calls = month["total"].get("calls") or 0

    lines = [f"💰 *API Spend*\n"]

    # Today
    lines.append(f"*Today* — ${today_cost:.2f} ({today_calls} calls)")
    if today_cache and today_cache > 0:
        lines.append(f"  Cache hits: {today_cache:,} tokens")
    for row in today.get("by_caller", []):
        cost = row.get("cost") or 0
        calls = row.get("calls") or 0
        caller = row["caller"].replace("_", " ")
        lines.append(f"  {caller}: ${cost:.3f} ({calls} calls)")

    # Month
    lines.append(f"\n*{month['month']}* — ${month_cost:.2f} ({month_calls} calls)")
    for row in month.get("by_caller", []):
        cost = row.get("cost") or 0
        calls = row.get("calls") or 0
        caller = row["caller"].replace("_", " ")
        lines.append(f"  {caller}: ${cost:.3f} ({calls} calls)")

    # Budget
    if budget > 0:
        pct = (month_cost / budget) * 100
        remaining = budget - month_cost
        lines.append(f"\n*Budget:* ${month_cost:.2f} / ${budget:.0f} ({pct:.0f}%)")
        lines.append(f"  Remaining: ${remaining:.2f}")

    return "\n".join(lines)


# ── Budget alerts ─────────────────────────────────────────────────────────────

_ALERT_THRESHOLDS = [0.50, 0.80, 1.00]  # 50%, 80%, 100%


async def _check_budget_alert(latest_cost: float) -> None:
    """Send Telegram alert if monthly spend crosses a threshold."""
    budget = float(os.environ.get("ANTHROPIC_MONTHLY_BUDGET", "0"))
    if budget <= 0:
        return

    month = await get_spend_month()
    month_cost = month["total"].get("cost") or 0
    pct = month_cost / budget

    # Check which threshold we just crossed
    prev_cost = month_cost - latest_cost
    prev_pct = prev_cost / budget

    for threshold in _ALERT_THRESHOLDS:
        if prev_pct < threshold <= pct:
            from core.notifications import notify_owner
            label = f"{int(threshold * 100)}%"
            await notify_owner(
                f"⚠️ *API spend alert*: ${month_cost:.2f} / ${budget:.0f} ({label})\n"
                f"You've used {label} of your monthly Anthropic budget."
            )
            break  # Only alert for the highest crossed threshold
