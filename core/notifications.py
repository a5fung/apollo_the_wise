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
import re

import httpx

from shared.telegram_format import code, esc, md_to_html, to_plain

logger = logging.getLogger(__name__)


_BACKTICK_SPAN = re.compile(r"`([^`]+)`")


def error_html(s: str) -> str:
    """An exception / error text as Telegram HTML: free text `esc()`d, and a backtick pair the
    error ITSELF used to quote an identifier (asyncpg: ``column `rs_rank` does not exist``)
    rendered as a `<code>` span. An unpaired backtick stays a literal character.

    Why this builds HTML instead of escaping legacy Markdown (#121 review, 2026-10-01): the old
    `md_escape` backslash-escaped `_ * ` [` and the result then went through `md_to_html`, which
    stashes code spans BEFORE it honours backslash escapes - so a quoted identifier came out as
    `\\<code>rs\\_rank\\</code>` with literal backslashes. And `md_escape` no longer doubled
    a literal backslash, so a text ENDING in one (`C:\\data\\`) escaped the closing `_` of its
    own italics wrapper and printed literal underscores. `md_to_html` is a faithful v1 mirror
    (v1 has no `\\\\` escape either), so neither is its bug: dynamic text must not take a Markdown
    round trip at all. `esc()` is total and has no failure mode to guard."""
    out: list[str] = []
    pos = 0
    for m in _BACKTICK_SPAN.finditer(s):
        out.append(esc(s[pos:m.start()]))
        out.append(code(m.group(1)))
        pos = m.end()
    out.append(esc(s[pos:]))
    return "".join(out)


# ── #635 (operator-approved 2026-09-13): which job-DEATH pages buzz the phone ──
# Every page through `notify_owner` is silent (`disable_notification`) — a job
# failure is telemetry and must not wake him. He was offered three options (leave
# all silent · make every job-failure page buzz · split the naked-position and
# stop-ack watchdog pages onto a loud path) and chose the split. Membership rule:
# LOUD iff the job's death removes the LAST DETECTION of a bare live position.
# A REPAIR job's death (stop refresh, the 21:00 backstop, the retry re-driver) is
# caught by a detector that is still alive — and every alert those detectors
# EMIT already buzzes, because `briefing.send_telegram_message` sends no
# `disable_notification` at all. Only the page saying the detector itself DIED
# was silent; that is what this set fixes.
#
# Keyed on the job id, not a per-call flag, because the two watchdogs with no
# handler of their own (stop-ack, stuck-fill) page from `audit_run`'s generic
# exception branch via `record_job_failure` — there is no call site to flag.
# One reviewable hunk; widening it is the operator's decision, not a default.
LOUD_FAILURE_JOBS: frozenset[str] = frozenset({
    # the stop-ack watchdog — every 30s in market hours; places the fallback stop
    # when a fill's OTO stop leg never ACKed (MRAM-class)
    "stop_ack_timeout_watchdog",
    # its sibling — a row stuck 'filling' means the WS fill handler threw before
    # the stop was known; its own page says "check broker for naked position"
    "stuck_fill_watchdog",
    # the broker-truth coverage detectors: the 15-min intraday check (#527), the
    # three bare-window slots 17:00/19:00/21:10 (#646/#649), and the L1
    # naked_position checks at 15:55/16:27 (#604)
    "position_coverage_check",
    "coverage_watch_post_close", "coverage_watch_late", "coverage_watch_evening",
    "naked_position_pre_close_check", "naked_position_post_refresh_check",
})


async def notify_owner(text: str, *, silent: bool = True, html: bool = False) -> None:
    """Send a message directly to the owner via Telegram Bot API.

    `silent` maps to Telegram's `disable_notification` — the Bot API's ONLY
    sound lever (there is no priority or sound choice beyond on/off). Default
    True keeps every existing caller byte-identical; `notify_job_failure` passes
    False for the jobs in `LOUD_FAILURE_JOBS` (#635). The plain-text retry
    carries the same flag, so a loud page that 400s on its first send still buzzes.

    The caller's text is legacy Markdown (`*bold*`, `` `code` ``, `_italic_`) and is converted
    ONCE here (`md_to_html`) and sent as HTML (#121, 2026-10-01), so a job id or an exception
    message carrying a bare `_` can no longer 400 the page. A caller that already holds
    Telegram HTML - one that builds it with `shared.telegram_format` / `error_html` because it
    carries dynamic text - passes `html=True` and the text is sent as-is (never converted twice,
    the same contract as `send_telegram_message(parse_mode="HTML")`).

    On a 400 (a parse failure) the same text is re-sent as plain text so the alert
    still LANDS — mirrors `briefing.send_telegram_message`, with the same `to_plain`
    backstop (tags removed, entities unescaped; it cannot touch an identifier).
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
    html_text = text if html else md_to_html(text)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": html_text,
                    "parse_mode": "HTML",
                    "disable_notification": silent,  # default True — don't buzz the phone
                },
            )
            status = getattr(r, "status_code", 200)
            if status == 400:
                logger.warning(
                    f"notify_owner: Telegram 400 on HTML send — re-sending as plain text "
                    f"({getattr(r, 'text', '')[:200]})"
                )
                r = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": to_plain(html_text),
                        "disable_notification": silent,
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

    Built as HTML (`error_html`, #121 review 2026-10-01): the error text is `esc()`d inside
    `<i>…</i>` - no Markdown escaping, so an underscore, an asterisk, a backslash anywhere in
    it (including as its LAST character) or a backtick-quoted identifier all render as written.
    The words are the same as before: bold title, the job id as code, the error in italics.

    Silent unless `job_name` is in `LOUD_FAILURE_JOBS` (#635) — the wording, the
    dedup and the trigger are untouched; only whether the phone buzzes changes."""
    flat = " ".join(str(error).split())   # italics cannot span a newline
    text = f"🚨 <b>Scheduled job failed</b>: {code(job_name)}\n<i>{error_html(flat[:200])}</i>"
    await notify_owner(text, silent=job_name not in LOUD_FAILURE_JOBS, html=True)


async def notify_job_success(job_name: str, summary: str) -> None:
    """Job completed OK — LOG-ONLY (#479 2026-07-17). The docstring always said
    'silent — just for peace of mind', but it actually Telegrammed every nightly
    job's completion (the verbose 'nightly_data_pull complete — 2456 stocks
    scored…' line the operator flagged as post-market noise). A successful
    routine job is not actionable — house rule: reserve Telegram for
    terminal/actionable events. Failures still Telegram via notify_job_failure."""
    logger.info(f"✓ {job_name} complete — {summary}")
