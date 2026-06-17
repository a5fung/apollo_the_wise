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
import base64
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _user_content(prompt: str, image_png: Optional[bytes]):
    """Text-only → the plain string (byte-identical to the pre-vision path).
    With a chart image → a multimodal content list (text + base64 PNG block).
    Isolated + pure so the image-shaping is unit-testable without an API call."""
    if not image_png:
        return prompt
    return [
        {"type": "text", "text": prompt},
        {"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.standard_b64encode(image_png).decode("ascii"),
        }},
    ]


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
    image_png: Optional[bytes] = None,
) -> Optional[dict]:
    """One forced-tool judge call. Returns `normalize(tool_input)`, or None on any error/timeout
    (FAIL-OPEN — the caller falls back to its floor / writes nothing, never raises). `semaphore`
    bounds total Anthropic concurrency; `wait_for` bounds total time. `label`/`subject` name the
    judge + ticker in logs/alerts. Credit exhaustion ALERTS (terminal + actionable), never vanishes
    into the fail-open (#273).

    `image_png` (optional, #267 chart-vision) attaches a rendered daily chart as a multimodal
    image block; None keeps the call byte-identical to the text-only path. The judge model must
    support vision (Opus does)."""
    if client is None:
        return None

    async def _call():
        kwargs = dict(
            model=model, max_tokens=max_tokens, tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": _user_content(prompt, image_png)}],
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
