"""Shared transport for the forced-tool "judge" LLM calls.

The grade judge (`ep_grade_judge.grade_holistic`, ADR 0011 — load-bearing on entry) and the
management judge (`mgmt_judge.manage_holistic`, ADR 0014 — shadow) had byte-identical call
envelopes: a semaphore-gated `messages.create` forced onto one tool, a `wait_for` timeout, the
`tool_use` block extraction, and a fail-open `except` that ALERTS on credit exhaustion before
returning None. That credit-exhaustion branch is incident-hardened (#273 — 6/11 produced 2,122
SILENT judge nulls when credits ran out), so keeping two copies risked one silently regressing past
a future fix. This is the one source; the prompt, tool schema, and per-judge `normalize` stay with
each judge (they are genuinely different).
"""
import asyncio
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


async def invoke_forced_tool(
    client,
    prompt: str,
    *,
    tool: dict,
    tool_name: str,
    normalize: Callable[[dict], Optional[dict]],
    label: str,
    subject: str = "",
    semaphore: Optional[asyncio.Semaphore] = None,
    timeout: float,
    model: str,
    max_tokens: int = 500,
) -> Optional[dict]:
    """One forced-tool judge call. Returns `normalize(tool_input)`, or None on any error/timeout
    (FAIL-OPEN — the caller falls back to its floor / writes nothing, never raises). `semaphore`
    bounds total Anthropic concurrency; `wait_for` bounds total time. `label`/`subject` name the
    judge + ticker in logs/alerts. Credit exhaustion ALERTS (terminal + actionable), never vanishes
    into the fail-open (#273)."""
    if client is None:
        return None

    async def _call():
        kwargs = dict(
            model=model, max_tokens=max_tokens, tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": prompt}],
        )
        if semaphore is not None:
            async with semaphore:
                return await client.messages.create(**kwargs)
        return await client.messages.create(**kwargs)

    try:
        resp = await asyncio.wait_for(_call(), timeout=timeout)
        tool_block = next(b for b in resp.content if getattr(b, "type", None) == "tool_use")
        return normalize(tool_block.input)
    except Exception as e:  # noqa: BLE001 — fail-open is the contract
        # #273: credit exhaustion must ALERT (terminal + actionable), never vanish into the
        # fail-open — 6/11 produced 2,122 silent judge nulls.
        try:
            from agents.market_intelligence.llm_health import (
                alert_credit_exhausted, is_credit_error)
            if is_credit_error(e):
                await alert_credit_exhausted(label, e)
        except Exception:
            pass
        logger.warning(f"{label} failed/timeout for {subject}: {e}")
        return None
