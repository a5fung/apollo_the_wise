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

    from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
    from shared.llm_models import effective_model
    model = effective_model("THEME_ADVISOR_MODEL")   # never a hardcoded id
    response = await client.messages.create(model=model, ...)
    await log_anthropic_call_safe(
        model=model,
        caller="theme_advisor",
        usage=response.usage,
    )

`log_anthropic_call_safe` is the SANCTIONED call-site wrapper (S2/F9, post-#377).
Call sites must call it directly and must NOT re-wrap it in their own
`try/except ... pass` — that ~16-site copy-paste pattern is exactly how spend
telemetry could go dark with zero signal if the tracker ever broke (the May 2026
outage class this file exists to prevent). Use the bare `log_anthropic_call`
below only from within `spend_tracker.py` itself (or from a caller that has its
own bespoke fail-soft/fail-loud handling, e.g. a forced-tool transport isolating
the cost-log path from its verdict path).
"""
from __future__ import annotations

import logging
from typing import Any

from agents.market_intelligence.db import get_pool
from shared.llm_models import (
    DEFAULT_PERPLEXITY_REQUEST_FEE_USD as _DEFAULT_PPLX_FEE,
    PERPLEXITY_REQUEST_FEE_USD as _PPLX_FEE,
)
from shared.llm_models import pricing_for as _pricing_for

logger = logging.getLogger(__name__)


def _cost_for_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """`pricing_for` (not a raw dict `.get`) so an auto-resolved RESOLVED_ROLES
    id not yet in PRICING_PER_MTOK prices at its tier's rate instead of the
    flat default (#509)."""
    prices = _pricing_for(model)
    base_input = prices["input"]
    regular_input = max(input_tokens - cache_creation_tokens - cache_read_tokens, 0)
    cost = (
        (regular_input / 1_000_000) * base_input
        + (cache_creation_tokens / 1_000_000) * base_input * 1.25
        + (cache_read_tokens / 1_000_000) * base_input * 0.10
        + (output_tokens / 1_000_000) * prices["output"]
    )
    return round(cost, 6)


_SCHEMA_ENSURED = False


async def _ensure_schema() -> None:
    """Ensure api_usage table exists. Idempotent. Cached after first success.

    Advisor 2026-05-13 caught: spend_tracker assumed api_usage existed
    because orchestrator's core.spend.initialize_spend_schema() creates it.
    On any cold-restart that brings up market-agent first, INSERTs would
    silently fail — exactly the silent-failure pattern this file fixes.
    """
    global _SCHEMA_ENSURED
    if _SCHEMA_ENSURED:
        return
    pool = await get_pool()
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
    _SCHEMA_ENSURED = True


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

    await _ensure_schema()
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


async def log_anthropic_call_safe(
    *,
    model: str,
    caller: str,
    usage: Any,
) -> None:
    """The SANCTIONED call-site wrapper for `log_anthropic_call` (S2/F9, 2026-07-03).

    Calls `log_anthropic_call` and, on ANY Exception, logs exactly ONE WARNING
    and returns — it never raises into the caller's real work.

    This exists because the #377 cost meter was wired by copy-pasting
    `try: ... await log_anthropic_call(...) except Exception: pass` at ~16 call
    sites across the codebase. Most of those swallowed silently: if the tracker
    broke, ALL spend telemetry went dark with zero signal — the exact class of
    outage (12 days, May 2026) the tracker itself was built to catch. Call sites
    MUST call this wrapper directly and must NOT re-wrap it in their own
    try/except-pass; that reintroduces the same blind spot this fixes.
    """
    try:
        await log_anthropic_call(model=model, caller=caller, usage=usage)
    except Exception as e:  # loud-ok: sanctioned single warning sink for #377 cost-meter call sites (S2/F9) — the one place allowed to swallow a tracker failure, and it does so loudly
        logger.warning(f"spend tracking failed at {caller}: {e}")


async def log_perplexity_call(
    *,
    caller: str,
    usage: Any = None,
    model: str = "sonar-pro",
) -> float:
    """Log a Perplexity (#377 cost meter) call to api_usage. Separate shape from
    Anthropic because Perplexity (a) names its usage fields OpenAI-style
    (`prompt_tokens`/`completion_tokens`, NOT `input_tokens`/`output_tokens`) and
    (b) charges a per-request SEARCH FEE on top of the token cost. Both are folded
    into one `cost_usd` row here.

    `usage` is the `usage` object from the Perplexity JSON response — a plain dict
    OR an attribute object. We accept either via _get(); tokens default to 0 if
    absent (the per-request fee still lands, which is the dominant cost anyway).
    `model` selects the token + fee rates ("sonar-pro" default, "sonar" for the
    cheaper validation path). Returns the computed cost in USD. Raises on DB
    failure — callers wrap in try/except for fail-soft (mirrors log_anthropic_call).
    """
    def _get(u: Any, key: str) -> int:
        if u is None:
            return 0
        if isinstance(u, dict):
            return int(u.get(key) or 0)
        return int(getattr(u, key, 0) or 0)

    input_tokens = _get(usage, "prompt_tokens")
    output_tokens = _get(usage, "completion_tokens")

    prices = _pricing_for(model)
    request_fee = _PPLX_FEE.get(model, _DEFAULT_PPLX_FEE)
    token_cost = (
        (input_tokens / 1_000_000) * prices["input"]
        + (output_tokens / 1_000_000) * prices["output"]
    )
    cost = round(token_cost + request_fee, 6)

    await _ensure_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO api_usage
                (model, caller, input_tokens, output_tokens,
                 cache_creation, cache_read, cost_usd)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            model, caller, input_tokens, output_tokens, 0, 0, cost,
        )
    return cost
