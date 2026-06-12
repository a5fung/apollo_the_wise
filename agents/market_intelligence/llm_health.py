"""#273 — LLM billing/credit exhaustion detection (the 6/11 Phase B lesson).

When the Anthropic account runs out of credits, every LLM call starts failing
— and Apollo's fail-open design converts that into SILENT degradation: the
judge falls back to floor, the catalyst grader returns "routine", and nothing
alerts. On 6/11 this produced 2,122 silent judge fail-opens in the replay
(initially misdiagnosed as rate limiting) and would have degraded a LIVE
trading morning identically.

Credit exhaustion is TERMINAL + ACTIONABLE (operator must refill) — exactly
the class the alerting rules say must Telegram, never just log. This module
gives the swallow-points a cheap detector + a deduped alarm.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_ALERT_INTERVAL_S = 3600  # one Telegram per hour max — the condition persists
_last_alert_ts: float = 0.0

_CREDIT_MARKERS = (
    "credit balance",          # "Your credit balance is too low …"
    "billing",                 # generic billing failures
    "purchase credits",
)


def is_credit_error(exc: BaseException) -> bool:
    """True when an Anthropic call failed for billing/credit reasons."""
    msg = str(exc).lower()
    return any(m in msg for m in _CREDIT_MARKERS)


async def alert_credit_exhausted(context: str, exc: BaseException) -> None:
    """Audit row always; Telegram at most once per hour per process.
    Never raises — callers are already in fail-open except blocks."""
    global _last_alert_ts
    try:
        from agents.market_intelligence.db import log_audit_event
        await log_audit_event(
            "anthropic_credit_exhausted",
            f"{context}: LLM call failed on CREDITS — judge/grader silently at floor until refill",
            str(exc)[:400],
        )
    except Exception:
        pass
    now = time.monotonic()
    if now - _last_alert_ts < _ALERT_INTERVAL_S:
        return
    _last_alert_ts = now
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        from shared.telegram_format import b, esc
        await send_telegram_message(
            f"🔴 {b('ANTHROPIC CREDITS EXHAUSTED')} — detected in {esc(context)}.\n"
            "The judge and catalyst grader are silently failing open to the "
            "floor/'routine' until the balance is refilled. Refill, then verify "
            "the next scan's <code>ep_grade_decision</code> rows.",
            parse_mode="HTML")
    except Exception:
        pass
