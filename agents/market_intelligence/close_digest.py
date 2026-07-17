"""Market Close Digest — in-process contribution buffer (#479 half-1, operator-ruled).

Folds the ~6 routine post-close Telegram digests (16:00–16:45 ET) into ONE
"Market Close Digest" sent at 16:55 ET. Render target = the mock in
docs/analysis/479_telegram_noise_proposal_2026-07-17.md §2: one monospace
block, sections ordered BOOK / EP / 9M / JUDGE / SIGNALS (then any others),
empty sections OMITTED — a quiet day is a few lines. Deprecated strategies
get NO line (contributors already suppress them).

Mechanics: the folded jobs call `contribute(section, text)` with the SAME
render text they used to pass to send_telegram_message; the 16:55
`close_digest` scheduler job calls `flush_and_send()`, which assembles the
one message, sends it, clears the buffer, and writes ONE
`market_close_digest_sent` audit row (json detail lists included sections).
Empty buffer → nothing is sent (no audit row either — a no-op flush is not
an operator event).

Scope: observability only — no strategy / trade-state / entry-path change.
Real-time alerts (fills, stops, errors, L1/L2, concentration, spend,
graduation) are NOT routed here.

Process model: a module-level dict is sufficient because the same scheduler
process (SERVICE_ROLE=combined) runs all the 16:00–16:50 contributors AND the
16:55 flush. If the #256 execution/intelligence split ever goes live, the
execution-side BOOK contribution (live_position_update) would land in a
different process from the intelligence-side flush — revisit then.

Markdown V1 rules (CLAUDE.md Telegram Formatting): every dynamic token lives
inside the ``` block; the fence is stripped from formatting via `_strip_md`
so contributed Markdown decoration (* ` _) can't break the pre-block; nothing
— in particular no italics — is emitted after the closing fence.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

logger = logging.getLogger(__name__)

# Canonical section order (the mock's shape). Unknown sections (e.g. NEWS)
# render after these, in first-contribution order.
SECTION_ORDER = ("BOOK", "EP", "9M", "JUDGE", "SIGNALS")

# Telegram hard limit is 4096; send_telegram_message splits >4000 at blank
# lines, which would orphan the ``` fence across chunks. Below this budget we
# wrap in one fence; above it we send the (already markdown-stripped) text
# plain so the splitter stays safe.
_FENCE_BUDGET = 3900

# section -> list of contributed render texts (verbatim from the folded jobs).
_buffer: dict[str, list[str]] = {}
# ET calendar date the buffer belongs to — a contribution on a NEW date drops
# any stale leftovers (e.g. the 16:55 flush never ran because the container
# was down), so yesterday's book state can't leak into today's digest.
_buffer_date: str | None = None


def contribute(section: str, text: str) -> None:
    """Buffer one section contribution for the 16:55 close digest.

    Called by the folded 16:00–16:45 jobs with the exact text they previously
    sent via send_telegram_message. Empty/whitespace text is ignored (the
    contributors already suppress their empty days; this is belt-and-braces).
    Never raises — a digest-buffer problem must not fail the contributing job.
    """
    global _buffer_date
    try:
        if not text or not text.strip():
            return
        today = datetime.now(_ET).date().isoformat()
        if _buffer_date != today:
            if _buffer:
                logger.warning(
                    f"close_digest: dropping {sum(len(v) for v in _buffer.values())} "
                    f"stale contribution(s) from {_buffer_date} (unflushed)"
                )
            _buffer.clear()
            _buffer_date = today
        _buffer.setdefault(section, []).append(text.rstrip())
        logger.info(f"close_digest: buffered {section} contribution ({len(text)} chars)")
    except Exception as e:  # loud-ok: never break the contributing job
        logger.error(f"close_digest: contribute({section}) failed: {e}")


def clear() -> None:
    """Drop all buffered contributions (flush does this after assembling)."""
    _buffer.clear()


def _strip_md(text: str) -> str:
    """Strip Markdown V1 decoration for the monospace block.

    The contributed texts carry legacy-Markdown tokens (*bold*, `code`,
    _italic_). Inside a ``` pre-block those render as literal characters
    (noise), and stray backticks can terminate the fence early. Remove
    * and ` outright; remove _ only at word boundaries so snake_case
    machine tokens (e.g. audit event names) survive.
    """
    text = text.replace("*", "").replace("`", "")
    return re.sub(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])", "", text)


def _ordered_sections() -> list[str]:
    return [s for s in SECTION_ORDER if s in _buffer] + [
        s for s in _buffer if s not in SECTION_ORDER
    ]


def _render(now_et: datetime) -> str:
    """Assemble the single digest message (buffer must be non-empty)."""
    parts = [f"🔔 CLOSE — {now_et.strftime('%a')} {now_et.month}/{now_et.day}"]
    for section in _ordered_sections():
        parts.append("")
        parts.append(section)
        for text in _buffer[section]:
            parts.append(_strip_md(text))
    body = "\n".join(parts)
    if len(body) + 8 > _FENCE_BUDGET:
        # Oversized day: plain text (markdown already stripped) so the >4000
        # chunk-splitter can't orphan a ``` fence mid-message.
        return body
    return f"```\n{body}\n```"


async def flush_and_send() -> int:
    """16:55 ET job body: send the assembled digest, clear the buffer, write
    ONE market_close_digest_sent audit row. Empty buffer → send nothing.

    Returns the number of contributions flushed (audit_wrap rows_written).
    """
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.db import log_audit_event

    if not _buffer:
        logger.info("close_digest: buffer empty — no digest sent")
        return 0

    now_et = datetime.now(_ET)
    sections = _ordered_sections()
    n_contribs = sum(len(v) for v in _buffer.values())
    msg = _render(now_et)
    clear()  # clear before the network call — a retry must not double-send

    sent = await send_telegram_message(msg)
    if not sent:
        logger.error("close_digest: Telegram send failed (send returned False)")

    await log_audit_event(
        "market_close_digest_sent",
        f"Market Close Digest: {n_contribs} contribution(s) across "
        f"{len(sections)} section(s)",
        json.dumps({
            "sections": sections,
            "contributions": n_contribs,
            "sent": bool(sent),
            "chars": len(msg),
        }),
    )
    logger.info(
        f"close_digest: flushed {n_contribs} contribution(s) "
        f"[{', '.join(sections)}] sent={bool(sent)}"
    )
    return n_contribs
