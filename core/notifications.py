"""
System notifications — sent directly to the owner via Telegram.

Used for:
- Apollo startup (with agent health summary)
- Scheduled job failures (nightly data pull, morning briefing)
- Critical errors that need attention

Sends to TELEGRAM_ALLOWED_USER_IDS[0] (the owner).
Bypasses the orchestrator — direct Bot API call so it works even if
the main app is partially broken.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


async def notify_owner(text: str) -> None:
    """Send a message directly to the owner via Telegram Bot API."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    ids = [x.strip() for x in allowed.split(",") if x.strip()]

    if not bot_token or not ids:
        logger.warning("notify_owner: TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_USER_IDS not set")
        return

    chat_id = int(ids[0])
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_notification": True,  # silent — don't buzz the phone
                },
            )
    except Exception as e:
        logger.error(f"notify_owner failed: {e}")


async def notify_startup(agent_statuses: dict[str, tuple[bool, str]]) -> None:
    """
    Send startup notification with agent health summary.
    Deduplicated via Redis — only fires once per 60-second window to prevent
    spam when uvicorn reload restarts the process on file changes.
    """
    # Dedup: skip if we already sent a startup notification recently
    try:
        from core.confirmations import get_redis
        r = await get_redis()
        key = "apollo:last_startup_notify"
        if await r.get(key):
            logger.info("Startup notification suppressed (sent within last 60s)")
            return
        await r.setex(key, 60, "1")
    except Exception as e:
        logger.warning(f"Redis dedup check failed (sending anyway): {e}")

    healthy = [a for a, (ok, _) in agent_statuses.items() if ok]
    unhealthy = [(a, reason) for a, (ok, reason) in agent_statuses.items() if not ok]

    if not unhealthy:
        agents_str = "  ".join(f"`{a}`" for a in healthy)
        text = f"✅ *Apollo online*\n{agents_str}"
    else:
        ok_str = "  ".join(f"`{a}`" for a in healthy) or "none"
        bad_str = "\n".join(f"  ✗ `{a}` — {r}" for a, r in unhealthy)
        text = f"⚠️ *Apollo online — degraded*\n✓ {ok_str}\n{bad_str}"

    await notify_owner(text)


async def notify_job_failure(job_name: str, error: str) -> None:
    """Alert owner when a scheduled job fails."""
    text = f"🚨 *Scheduled job failed*: `{job_name}`\n_{error[:200]}_"
    await notify_owner(text)


async def notify_job_success(job_name: str, summary: str) -> None:
    """Job completed OK — LOG-ONLY (#479 2026-07-17). The docstring always said
    'silent — just for peace of mind', but it actually Telegrammed every nightly
    job's completion (the verbose 'nightly_data_pull complete — 2456 stocks
    scored…' line the operator flagged as post-market noise). A successful
    routine job is not actionable — house rule: reserve Telegram for
    terminal/actionable events. Failures still Telegram via notify_job_failure."""
    logger.info(f"✓ {job_name} complete — {summary}")
