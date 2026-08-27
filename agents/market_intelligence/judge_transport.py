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
from shared.llm_response import is_truncated

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
    log_caller: Optional[str] = None,
) -> Optional[dict]:
    """One forced-tool judge call. Returns `normalize(tool_input)`, or None on any error/timeout
    (FAIL-OPEN — the caller falls back to its floor / writes nothing, never raises). `semaphore`
    bounds total Anthropic concurrency; `wait_for` bounds total time. `label`/`subject` name the
    judge + ticker in logs/alerts. Credit exhaustion ALERTS (terminal + actionable), never vanishes
    into the fail-open (#273).

    `image_png` (optional, #267 chart-vision) attaches a rendered daily chart as a multimodal
    image block; None keeps the call byte-identical to the text-only path. The judge model must
    support vision (Opus does).

    `log_caller` (optional, #377 cost meter): when set, the call's token cost is logged to
    api_usage under this caller label. None = no logging (byte-identical to the pre-#377 path).
    The logging is isolated in its own try/except AFTER the verdict is extracted — a DB/logging
    failure can NEVER alter the verdict nor get misclassified as credit exhaustion by the
    fail-open except below (that would change grading behavior, which the cost meter must not)."""
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
        # A TRUNCATED response is a judge FAILURE and must take the fail-open path (#543,
        # 2026-08-07). MEASURED, and it is not what anyone assumed: when `max_tokens` cuts a
        # forced-tool call off, the SDK still hands back a `tool_use` block with PARTIALLY
        # populated input. `grade`/`tier`/`direction` come first in the JSON and survive;
        # `rationale` and `confidence` are what get cut. `_normalize_verdict` reads those with
        # `.get()`, so it happily returned a COMPLETE-LOOKING VERDICT built from an incomplete
        # answer. Over the 7 days to 08-07: 7 of 49 ep_grade_judge verdicts had NULL confidence
        # (exactly the 7 at-cap calls) and TWO — AMRC and RDW — promoted to HIGH with a
        # ZERO-LENGTH rationale. HIGH drives the alert and the ORB entry.
        #
        # This is a BUG FIX restoring ADR 0011's signed intent, not a new rule: that ADR already
        # says "judge error/timeout -> conviction-floor grade". A response we cut off IS a judge
        # error; we simply had no way to see it until stop_reason was recorded. Raising the
        # ceiling makes truncation rare — this makes it HARMLESS when it happens anyway.
        if is_truncated(resp):
            logger.warning(
                f"{label} TRUNCATED for {subject} (max_tokens={max_tokens}) — failing open to "
                "the floor rather than grading on a partial verdict (#543)")
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event(
                    "judge_verdict_truncated",
                    subject or label,
                    f"{label} hit max_tokens={max_tokens}; verdict discarded, "
                    f"our score's alert tier kept",
                )
            except Exception as _te:
                # Telemetry must never change the fail-open outcome, but it must not vanish
                # either — the WARNING above already carried the actionable fact.
                logger.warning(f"{label}: truncation audit row failed to write: {_te}")
            return None
        tool_block = next(b for b in resp.content if getattr(b, "type", None) == "tool_use")
        verdict = normalize(tool_block.input)
        # COST METER (#377). Isolated from the verdict path: this runs AFTER the
        # verdict is extracted, so a logging/DB failure cannot fall into the
        # fail-open `except` below (which would run the error through
        # is_credit_error and return None, i.e. turn a good grade into a
        # fail-open — a behavior change the cost meter must never cause).
        # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
        if log_caller:
            from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
            await log_anthropic_call_safe(model=model, caller=log_caller, response=resp)
        return verdict
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
