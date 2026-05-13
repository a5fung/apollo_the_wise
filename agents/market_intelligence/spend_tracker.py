"""
Market-agent local spend tracker — mirrors core.spend (orchestrator) but
writes to the shared `api_usage` table via market-agent's own DB pool.

Architectural note (2026-05-13): `core.spend` lives in the orchestrator
container and imports `core.memory.get_pool`. Market-agent's Docker image
does NOT include `core/memory.py`, so `from core.spend import log_api_usage`
raises ModuleNotFoundError when called from any market-agent module —
silently caught by the upstream except, leaving the market-agent's
Anthropic costs unlogged. This file is the bridge: same row schema, same
pricing function, but uses market-agent's `db.get_pool` directly.

Use from any market-agent module that makes an Anthropic call:

    from agents.market_intelligence.spend_tracker import log_anthropic_call
    response = await client.messages.create(...)
    await log_anthropic_call(
        model="claude-haiku-4-5-20251001",
        caller="theme_advisor",
        usage=response.usage,
    )
"""
from __future__ import annotations

import logging
from typing import Any

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6":           {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5":           {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001":   {"input": 0.80, "output": 4.00},
    "claude-opus-4-7":             {"input": 15.00, "output": 75.00},
    "claude-opus-4-6":             {"input": 15.00, "output": 75.00},
}
_DEFAULT_PRICING = {"input": 3.00, "output": 15.00}


def _cost_for_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    prices = _PRICING.get(model, _DEFAULT_PRICING)
    base_input = prices["input"]
    regular_input = max(input_tokens - cache_creation_tokens - cache_read_tokens, 0)
    cost = (
        (regular_input / 1_000_000) * base_input
        + (cache_creation_tokens / 1_000_000) * base_input * 1.25
        + (cache_read_tokens / 1_000_000) * base_input * 0.10
        + (output_tokens / 1_000_000) * prices["output"]
    )
    return round(cost, 6)


async def log_anthropic_call(
    *,
    model: str,
    caller: str,
    usage: Any,
) -> float:
    """Log an Anthropic API call. `usage` is the response.usage object from
    the SDK. Returns the computed cost in USD. Raises on DB failure
    (callers should wrap if they want fail-soft semantics).

    Why no fail-soft default: spend-tracker silently swallowing errors is
    exactly how the May 2026 outage hid for 12 days. Surface failures
    loudly at the call site; the call site can choose try/except + WARNING.
    """
    if usage is None:
        logger.warning(f"log_anthropic_call({caller}): usage is None — skipping")
        return 0.0

    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

    cost = _cost_for_call(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation,
        cache_read_tokens=cache_read,
    )

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO api_usage
                (model, caller, input_tokens, output_tokens,
                 cache_creation, cache_read, cost_usd)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            model, caller, input_tokens, output_tokens,
            cache_creation, cache_read, cost,
        )
    return cost
