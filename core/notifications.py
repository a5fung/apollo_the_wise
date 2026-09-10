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


def md_escape(s: str) -> str:
    """Backslash-escape the four legacy-Markdown control characters so a dynamic
    value (an exception message, a job id) cannot break the parse of the message
    it is embedded in.

    #501 F1 (2026-09-10): `notify_job_failure` wraps its error text in `_..._`
    italics. An ODD number of `_` inside that text — e.g. asyncpg quoting
    `stop_order_id` — makes Telegram answer 400 and the alert is dropped on the
    floor (health_checks.py's recorder-failure guard documents the same trap and
    works around it by hand). A job-failure page that cannot render the errors
    it is most likely to carry is not an alarm, so the escape lives here, once.
    """
    return (str(s).replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*")
            .replace("`", "\\`").replace("[", "\\["))


def _strip_md(text: str) -> str:
    """Plain-text fallback: drop the Markdown markers this module's own templates
    use (`*bold*`, `` `code` ``, one `_italic_` line) and undo `md_escape`, so the
    operator reads words — never `\\_` litter, never a word with its underscores
    eaten (`stuck_fill_watchdog` must survive; a naive `_..._` regex eats it)."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n and text[i + 1] in "_*`[\\":
            out.append(text[i + 1])      # escaped → literal
            i += 2
            continue
        if c in "*`":
            i += 1                        # unescaped marker → drop
            continue
        out.append(c)
        i += 1
    lines = []
    for ln in "".join(out).split("\n"):
        if len(ln) >= 2 and ln.startswith("_") and ln.endswith("_"):
            ln = ln[1:-1]                 # the italics-wrapped error line
        lines.append(ln)
    return "\n".join(lines)


async def notify_owner(text: str) -> None:
    """Send a message directly to the owner via Telegram Bot API.

    On a 400 (almost always a Markdown parse failure) the same text is re-sent
    as plain text so the alert still LANDS — mirrors `briefing.send_telegram_message`.
    Before #501 F1 the response was never inspected: a 400 was indistinguishable
    from success and the page silently vanished."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    ids = [x.strip() for x in allowed.split(",") if x.strip()]

    if not bot_token or not ids:
        logger.warning("notify_owner: TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_USER_IDS not set")
        return

    chat_id = int(ids[0])
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_notification": True,  # silent — don't buzz the phone
                },
            )
            status = getattr(r, "status_code", 200)
            if status == 400:
                logger.warning(
                    f"notify_owner: Telegram 400 on Markdown send — re-sending as plain text "
                    f"({getattr(r, 'text', '')[:200]})"
                )
                r = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": _strip_md(text),
                        "disable_notification": True,
                    },
                )
                status = getattr(r, "status_code", 200)
            if status != 200:
                logger.error(f"notify_owner: Telegram returned {status} — alert NOT delivered")
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
    """Alert owner when a scheduled job fails.

    The error text is Markdown-escaped (#501 F1) — see `md_escape`. The job name
    is backtick-fenced, so an underscore in it was never the problem; the free
    text between the italics markers was."""
    flat = " ".join(str(error).split())   # italics cannot span a newline
    text = f"🚨 *Scheduled job failed*: `{job_name}`\n_{md_escape(flat[:200])}_"
    await notify_owner(text)


async def notify_job_success(job_name: str, summary: str) -> None:
    """Job completed OK — LOG-ONLY (#479 2026-07-17). The docstring always said
    'silent — just for peace of mind', but it actually Telegrammed every nightly
    job's completion (the verbose 'nightly_data_pull complete — 2456 stocks
    scored…' line the operator flagged as post-market noise). A successful
    routine job is not actionable — house rule: reserve Telegram for
    terminal/actionable events. Failures still Telegram via notify_job_failure."""
    logger.info(f"✓ {job_name} complete — {summary}")
