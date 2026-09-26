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
from zoneinfo import ZoneInfo
from typing import Any, Optional

from shared.llm_models import pricing_for as _pricing_for

_ET = ZoneInfo("America/New_York")
from shared.llm_response import (
    stop_reason as _stop_reason_of,
    usage_tokens as _usage_tokens_of,
)

logger = logging.getLogger(__name__)


def _cost_for_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Compute dollar cost for a single API call. `pricing_for` (not a raw dict
    `.get`) so an auto-resolved RESOLVED_ROLES id not yet in PRICING_PER_MTOK
    prices at its tier's rate instead of silently falling to the flat default
    (#509 — a resolved id could otherwise be mispriced)."""
    prices = _pricing_for(model)
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
            -- stop_reason (#543, 2026-08-07): the model's OWN report of why it stopped.
            -- 'max_tokens' = TRUNCATED. Kept in parity with the market-agent's
            -- spend_tracker._ensure_schema — BOTH containers write this one table, and
            -- the daily truncation check reports any caller whose stop_reason is always
            -- NULL, so an orchestrator-side omission would make that guard fire every
            -- night forever.
            ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS stop_reason TEXT;

            CREATE INDEX IF NOT EXISTS idx_api_usage_created
                ON api_usage(created_at);
        """)


async def log_api_usage(
    *,
    model: str,
    caller: str,
    response: Any,
) -> float:
    """
    Log a single API call's token usage.  Returns computed cost in USD.

    Args:
        model: Model ID (e.g. "claude-sonnet-4-6")
        caller: Where the call originated (e.g. "orchestrator", "context_compression")
        response: The RAW Anthropic response (SDK object or raw-HTTP dict). Token
            usage AND stop_reason are derived from it here — same #543 contract as
            the market-agent's spend_tracker, which writes the SAME api_usage table:
            a call site structurally cannot report cost without also reporting why
            the model stopped ('max_tokens' = TRUNCATED). The old per-token +
            `stop_reason=` kwargs are removed, not deprecated — hand-threading
            stop_reason at every site is how one site forgets, writes NULL forever,
            and the nightly NULL arm fires until someone traces it (which stays on
            as defence in depth, not as the primary mechanism).
    """
    usage = _usage_tokens_of(response)
    if usage is None:
        # Mirrors spend_tracker: no usage object → nothing meterable → no row.
        logger.warning(f"log_api_usage({caller}): response carries no usage — skipping")
        return 0.0

    cost = _cost_for_call(
        model, usage["input_tokens"], usage["output_tokens"],
        usage["cache_creation_input_tokens"], usage["cache_read_input_tokens"],
    )

    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_usage
                    (model, caller, input_tokens, output_tokens,
                     cache_creation, cache_read, cost_usd, stop_reason)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                model, caller, usage["input_tokens"], usage["output_tokens"],
                usage["cache_creation_input_tokens"], usage["cache_read_input_tokens"],
                cost, _stop_reason_of(response),
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
            WHERE (created_at AT TIME ZONE 'America/New_York')::date
                  = (NOW() AT TIME ZONE 'America/New_York')::date
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
            WHERE (created_at AT TIME ZONE 'America/New_York')::date
                  = (NOW() AT TIME ZONE 'America/New_York')::date
        """)
    return {
        # ET day, the same day the spend alarm uses (2026-09-25): the old CURRENT_DATE was the
        # server's UTC day, so after 20:00 ET "Today" rolled over and read $0.00.
        "date": datetime.now(_ET).date().isoformat(),
        "by_caller": [dict(r) for r in rows],
        "total": dict(total) if total else {},
    }


async def get_spend_month() -> dict[str, Any]:
    """Return current month's spend breakdown."""
    pool = await _get_pool()
    first_of_month = datetime.now(_ET).date().replace(day=1)
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
            WHERE (created_at AT TIME ZONE 'America/New_York')::date >= $1
            GROUP BY caller
            ORDER BY cost DESC
        """, first_of_month)
        total = await conn.fetchrow("""
            SELECT
                COUNT(*) AS calls,
                SUM(cost_usd) AS cost
            FROM api_usage
            WHERE (created_at AT TIME ZONE 'America/New_York')::date >= $1
        """, first_of_month)
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

    # Short by design (operator 2026-09-25: "hard to read"): totals first, then the few callers
    # that carry the money, the long tail summed into one line.
    def _top(rows, n):
        out = []
        for row in rows[:n]:
            out.append(f"  {row['caller'].replace('_', ' ')} ${float(row.get('cost') or 0):.2f}")
        rest = rows[n:]
        if rest:
            out.append(f"  {len(rest)} others ${sum(float(r.get('cost') or 0) for r in rest):.2f}")
        return out

    lines = ["💰 *API spend*", f"*Today* ${today_cost:.2f} ({today_calls} calls, ET day)"]
    lines += _top(today.get("by_caller", []), 3)
    head = f"*{month['month']}* ${month_cost:.2f}"
    if budget > 0:
        head += f" of ${budget:.0f} budget ({(month_cost / budget) * 100:.0f}%), ${budget - month_cost:.2f} left"
    lines += ["", head]
    lines += _top(month.get("by_caller", []), 5)
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
