"""
Telegram channel — receives messages from users and sends responses.
Uses python-telegram-bot in webhook mode (no polling).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ExtBot,
    MessageHandler,
    filters,
)

from core.confirmations import parse_confirmation_reply, resolve_confirmation
from shared.llm_models import HEALTHCHECK_MODEL
from shared.models import MemoryEntry
from shared.secrets import get_secrets

# ── Onboarding states ─────────────────────────────────────────────────────────
# Stored in Redis as apollo:onboarding:{user_id}
_ONBOARD_AWAITING_NAME = "awaiting_name"
_ONBOARD_AWAITING_PERSONA = "awaiting_persona"

if TYPE_CHECKING:
    from core.orchestrator import Apollo

logger = logging.getLogger(__name__)

# How long (seconds) to wait between "typing..." indicator updates
TYPING_INTERVAL = 4

# ── Polling-health heartbeat (#153) ──────────────────────────────────────────
# A persistent NetworkError can wedge PTB's long-poll loop silently — updates
# stop arriving with no error surfaced (the 2026-05-22→05-29 7-day outage). The
# market-agent watchdog (separate container) alarms if this Redis key goes
# stale. The signal is written on each SUCCESSFUL get_updates return — an empty
# poll still returns successfully, so the heartbeat advances even with zero user
# traffic, and it stays stale if the poll loop wedges/retries-forever (which a
# plain event-loop timer would NOT catch). Missing key (webhook mode / pre-boot)
# is treated as "not polling" by the watchdog, never an alarm.
POLL_HEARTBEAT_KEY = "apollo:telegram:poll_heartbeat"


async def _write_poll_heartbeat() -> None:
    """Fire-and-forget Redis heartbeat. Swallows every error so a Redis blip
    can never break the poll loop."""
    try:
        import time
        from core.confirmations import get_redis
        r = await get_redis()
        await r.set(POLL_HEARTBEAT_KEY, int(time.time()))
    except Exception:
        pass


class HeartbeatExtBot(ExtBot):
    """ExtBot that records a polling-liveness heartbeat on each successful
    get_updates return (#153). Class-level override (PTB 22.x Bot uses
    __slots__, so instance monkeypatch is blocked). Injected via
    ApplicationBuilder().bot(...) in build_application."""

    async def get_updates(self, *args, **kwargs):
        updates = await super().get_updates(*args, **kwargs)
        try:
            asyncio.create_task(_write_poll_heartbeat())
        except Exception:
            pass
        return updates


def _safe(s: str) -> str:
    """Strip Markdown special chars from dynamic/error strings."""
    return re.sub(r"[*_`\[\]]", "", s)


def _format_market_pipeline(status: dict) -> str:
    """Format the market pipeline section for /status."""
    from zoneinfo import ZoneInfo
    from datetime import date, datetime as dt, timedelta

    REGIME_EMOJI = {"Bull": "🟢", "Choppy": "🟡", "Correcting": "🔴", "Crisis": "🚨", "Unknown": "⚫"}

    et = ZoneInfo("America/New_York")
    pt = ZoneInfo("America/Los_Angeles")
    now_et = dt.now(et)

    jobs = status.get("jobs", {})
    data = status.get("data", {})
    scheduler = status.get("scheduler", {})

    _JOB_DISPLAY = {
        "nightly_data_pull": "Data pull",
        "evening_briefing":  "Evening brief",
        "morning_briefing":  "Morning brief",
    }

    def _last_expected_run_date() -> date:
        """Most recent weekday where jobs should have completed.
        Before 5 PM ET, use previous weekday (today's jobs haven't run yet)."""
        d = now_et.date()
        if now_et.hour < 17:  # before 5 PM ET — today's jobs haven't fired
            d -= timedelta(days=1)
        while d.weekday() >= 5:  # skip weekends
            d -= timedelta(days=1)
        return d

    def _fmt_time(iso: str) -> str:
        """Return time string in PT, e.g. '1:32 PM PT'."""
        d = dt.fromisoformat(iso).astimezone(pt)
        return d.strftime("%I:%M %p PT").lstrip("0")

    def _job_line(job_name: str, extra: str = "") -> str:
        label = f"{_JOB_DISPLAY.get(job_name, job_name)}:".ljust(14)
        job = jobs.get(job_name)
        if not job:
            return f"{label} ⚠️ never run"
        last_ran = dt.fromisoformat(job["last_ran"])
        last_ran_date = last_ran.astimezone(et).date()
        expected = _last_expected_run_date()
        # Healthy if it ran on the last expected weekday (or more recently)
        healthy = last_ran_date >= expected
        icon = "✅" if healthy else "⚠️"
        time_str = _fmt_time(job["last_ran"])
        return f"{label} {icon} {time_str}{extra}"

    lines = ["*Market Pipeline*"]

    # Data pull line — include data freshness summary
    extra = ""
    if data.get("stocks_scored"):
        regime = data.get("regime", "?")
        regime_icon = REGIME_EMOJI.get(regime, "⚪")
        extra = f" · {data['stocks_scored']} stocks · {regime_icon} {regime} · {data['active_themes']} themes"
    lines.append(_job_line("nightly_data_pull", extra))
    lines.append(_job_line("evening_briefing"))
    lines.append(_job_line("morning_briefing"))

    # EP scan — healthy if scheduler is running (scan activates automatically during market hours)
    scheduler_running = scheduler.get("scheduler_running", False)
    if scheduler_running:
        lines.append(f"{'EP scan:'.ljust(14)} ✅ scheduled · 4–6:30 AM PT weekdays")
    else:
        lines.append(f"{'EP scan:'.ljust(14)} 🔴 scheduler offline")

    # Next scheduled job
    next_jobs = scheduler.get("next_jobs", [])
    if next_jobs:
        nj = next_jobs[0]
        next_label = _JOB_DISPLAY.get(nj["id"], nj["id"])
        nj_dt = dt.fromisoformat(nj["next_run"]).astimezone(pt)
        day_str = nj_dt.strftime("%a")
        time_str = nj_dt.strftime("%I:%M %p PT").lstrip("0")
        lines.append(f"{'Next:'.ljust(14)} {next_label} {day_str} {time_str}")

    return "\n".join(lines)


class TelegramChannel:
    """Telegram bot interface for Apollo."""

    def __init__(self, apollo: "Apollo") -> None:
        self._apollo = apollo
        self._secrets = get_secrets()
        self._app: Optional[Application] = None

    def _is_allowed(self, user_id: int) -> bool:
        """Check if a user is in the allowlist."""
        return user_id in self._secrets.telegram_allowed_user_ids

    async def send_message(self, user_id: int, text: str) -> None:
        """Send a message to a user. Called by the orchestrator for confirmations."""
        if self._app is None:
            logger.error("Telegram app not initialized — cannot send message")
            return
        # Use HTML for messages with code blocks (Markdown v1 doesn't support ```)
        if "```" in text:
            try:
                html = self._md_to_html(text)
                await self._app.bot.send_message(
                    chat_id=user_id, text=html, parse_mode=ParseMode.HTML,
                )
                return
            except Exception:
                pass  # fall through
        try:
            await self._app.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {user_id}: {e}")
            # Fallback: try without markdown
            try:
                plain = re.sub(r"[*_`\[\]]", "", text)
                await self._app.bot.send_message(chat_id=user_id, text=plain)
            except Exception as e2:
                logger.error(f"Fallback send also failed: {e2}")

    async def send_plain_message(self, user_id: int, text: str) -> None:
        """Send a plain-text message (no Markdown parsing)."""
        if self._app is None:
            return
        await self._app.bot.send_message(chat_id=user_id, text=text)

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming user messages."""
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        text = update.message.text or ""

        if not self._is_allowed(user_id):
            logger.warning(f"Unauthorized access attempt from user_id={user_id}")
            await update.message.reply_text("Unauthorized.")
            return

        if not text.strip():
            return

        logger.info(f"Message from {user_id}: {text[:80]}")

        # Check if we're mid-onboarding
        onboarding_state = await self._get_onboarding_state(user_id)
        if onboarding_state:
            await self._handle_onboarding_reply(update, user_id, text, onboarding_state)
            return

        # Check if this is a YES/NO confirmation reply
        confirmation_result = parse_confirmation_reply(text)
        if confirmation_result is not None:
            handled = await self._try_resolve_confirmation(
                user_id, confirmation_result, update
            )
            if handled:
                return

        # Fast-path: known market commands bypass the LLM router entirely
        fast_response = await self._try_fast_path(text)
        if fast_response is not None:
            await self._reply(update, fast_response)
            return

        # Send typing indicator while processing
        typing_task = asyncio.create_task(
            self._send_typing_indicator(update, context)
        )

        try:
            response = await self._apollo.handle_message(
                user_id=user_id,
                text=text,
                conversation_id=str(user_id),
            )
        except Exception as e:
            logger.exception(f"Error handling message from {user_id}")
            response = "Sorry, I encountered an unexpected error. Please try again."
        finally:
            typing_task.cancel()

        await self._reply(update, response)

    async def _try_fast_path(self, text: str) -> str | None:
        """
        Bypass the LLM router for known market commands.
        Returns a response string if handled, None if the message should go through Claude.
        """
        from core.router import get_agent_url
        import httpx

        t = text.strip().lower()

        # Evening brief
        if any(k in t for k in ["send brief", "send evening brief", "evening brief", "send briefing"]):
            url = get_agent_url("market_intelligence")
            if url:
                try:
                    secret = get_secrets().internal_api_secret
                    async with httpx.AsyncClient(timeout=5) as client:
                        await client.post(f"{url}/briefing/evening", headers={"X-Apollo-Secret": secret})
                except Exception:
                    pass
            return "Check Telegram. 🐢"

        return None

    async def _handle_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start — launch onboarding if not yet configured, else greet."""
        if not update.effective_user:
            return
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            await update.message.reply_text("Unauthorized.")
            return

        # Check if persona is already configured
        if await self._is_persona_configured(user_id):
            assistant_name, persona = await self._load_persona(user_id)
            await update.message.reply_text(
                f"Hey, I'm {assistant_name}. What do you need?"
            )
        else:
            await self._start_onboarding(update, user_id)

    async def _handle_setup(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """`/setup TICKER [days]` — reverse-lookup detector chronology.

        Forwards to the market agent, which sends the timeline directly via
        Bot API and returns a status ack.
        """
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        import httpx
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        args = " ".join(context.args) if context.args else ""
        if not args.strip():
            await update.message.reply_text("Usage: `/setup TICKER [days]`", parse_mode=ParseMode.MARKDOWN)
            return

        url = get_agent_url("market_intelligence")
        if not url:
            await update.message.reply_text("Market agent not available.")
            return

        req = AgentRequest(
            task=f"/setup {args}",
            user_id=update.effective_user.id,
            conversation_id=str(update.effective_user.id),
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}/task",
                    json=req.model_dump(),
                    headers={"X-Apollo-Secret": self._secrets.internal_api_secret},
                )
                resp.raise_for_status()
                ack = resp.json().get("result") or "(no response)"
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
            return

        # Market agent sends the timeline itself; only echo the ack if it's
        # a fallback body (delivery failed) or a usage hint.
        if not ack.startswith("📬"):
            await update.message.reply_text(ack, parse_mode=ParseMode.MARKDOWN)

    # ── Onboarding helpers ────────────────────────────────────────────────────

    async def _start_onboarding(self, update: Update, user_id: int) -> None:
        """Begin the name+persona setup flow."""
        await self._set_onboarding_state(user_id, _ONBOARD_AWAITING_NAME)
        await update.message.reply_text(
            "👋 Let's get set up.\n\n"
            "What would you like to call your assistant?\n\n"
            "_(Default: Apollo — just send a period to keep it)_",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _handle_onboarding_reply(
        self, update: Update, user_id: int, text: str, state: str
    ) -> bool:
        """
        Handle a reply during the onboarding flow.
        Returns True if the message was consumed by onboarding.
        """
        from core.memory import save_memory, search_memories

        if state == _ONBOARD_AWAITING_NAME:
            name = text.strip() if text.strip() not in {".", "-", ""} else "Apollo"

            # Save name as a special persona memory
            await save_memory(MemoryEntry(
                user_id=user_id,
                category="persona:name",
                content=name,
            ))

            await self._set_onboarding_state(user_id, _ONBOARD_AWAITING_PERSONA)
            await update.message.reply_text(
                f"Got it — I'm *{name}*. ✅\n\n"
                "Now, how should I behave? Describe my personality and tone.\n\n"
                "_Examples:_\n"
                "• `Concise and direct. No filler words.`\n"
                "• `Detailed and thorough. Explain your reasoning.`\n"
                "• `Casual and friendly, like talking to a smart friend.`\n"
                "• `Professional and formal at all times.`\n\n"
                "_(Send a period to use the default: concise and proactive)_",
                parse_mode=ParseMode.MARKDOWN,
            )
            return True

        if state == _ONBOARD_AWAITING_PERSONA:
            default_persona = "Precise, concise, and proactive. Lead with the answer. No padding."
            persona = text.strip() if text.strip() not in {".", "-", ""} else default_persona

            # Load the name we just saved
            from core.memory import search_memories
            memories = await search_memories(user_id, category="persona:name", limit=1)
            assistant_name = memories[0].content if memories else "Apollo"

            # Save personality
            await save_memory(MemoryEntry(
                user_id=user_id,
                category="persona:personality",
                content=persona,
            ))

            await self._clear_onboarding_state(user_id)

            await update.message.reply_text(
                f"✅ All set.\n\n"
                f"*Name:* {assistant_name}\n"
                f"*Personality:* {persona}\n\n"
                f"I'm ready. What do you need?",
                parse_mode=ParseMode.MARKDOWN,
            )
            return True

        return False

    async def _is_persona_configured(self, user_id: int) -> bool:
        """Return True if name + personality have been saved for this user."""
        try:
            from core.memory import search_memories
            name_memories = await search_memories(user_id, category="persona:name", limit=1)
            return len(name_memories) > 0
        except Exception:
            return False

    async def _load_persona(self, user_id: int) -> tuple[str, str | None]:
        """Load (assistant_name, persona) from memory."""
        try:
            from core.memory import search_memories
            name_mems = await search_memories(user_id, category="persona:name", limit=1)
            persona_mems = await search_memories(user_id, category="persona:personality", limit=1)
            name = name_mems[0].content if name_mems else "Apollo"
            persona = persona_mems[0].content if persona_mems else None
            return name, persona
        except Exception:
            return "Apollo", None

    # ── Onboarding state (Redis) ──────────────────────────────────────────────

    async def _get_onboarding_state(self, user_id: int) -> str | None:
        try:
            from core.confirmations import get_redis
            r = await get_redis()
            return await r.get(f"apollo:onboarding:{user_id}")
        except Exception:
            return None

    async def _set_onboarding_state(self, user_id: int, state: str) -> None:
        try:
            from core.confirmations import get_redis
            r = await get_redis()
            await r.setex(f"apollo:onboarding:{user_id}", 3600, state)
        except Exception:
            pass

    async def _clear_onboarding_state(self, user_id: int) -> None:
        try:
            from core.confirmations import get_redis
            r = await get_redis()
            await r.delete(f"apollo:onboarding:{user_id}")
        except Exception:
            pass

    async def _handle_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help — full capabilities and command reference."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        assistant_name, _ = await self._load_persona(update.effective_user.id)

        text = (
            f"*{assistant_name} — Quick Reference*\n"
            "\n"
            "*Daily commands*\n"
            "/hud — pinned snapshot; buttons for Regime/Themes/9M/Clusters/Watchlist\n"
            "/pregame — trade-ready shortlist (themes, HIGH EPs, MA pullbacks, sugar babies)\n"
            "/ep — EP alerts today (MAGNA53) · buttons: [HIGH] [MODERATE]\n"
            "/trades — positions + P&L · buttons: [Closed] [Skipped] [Paper]\n"
            "/status — system health + API spend\n"
            "/help — this reference\n"
            "\n"
            "*Diagnostics*\n"
            "`/why TICKER [YYYY-MM-DD]` — detection + entry diagnosis (alert, skip-reason, fill)\n"
            "`/trade TICKER [YYYY-MM-DD]` — full trade anatomy (entries, stops, exits)\n"
            "`/missed [days]` — top EPs we didn't enter, ranked by forward return\n"
            "`/missed by reason` — same data, grouped by skip category\n"
            "`show errors 7d` — recent engine errors (validation, broker, feed)\n"
            "`weekly review` — on-demand system self-audit (also Sun 8 AM)\n"
            "\n"
            "*Ask naturally*\n"
            '• "EPs today" · "9M alerts" · "sugar babies"\n'
            '• "Market regime" · "top RS stocks" · "active themes"\n'
            '• "Score AXTI" · "Fundamentals CIEN" · "RS history LITE COHR"\n'
            '• "Optical stocks near 20MA" · "Screen RS>70 EPS growth>25"\n'
            "\n"
            "*Briefings & jobs*\n"
            '📊 `Send evening briefing` — regime + RS + themes + pullbacks\n'
            '☀️ `Send morning briefing` — EPs + overnight + regime\n'
            '🔄 `Run data refresh` — nightly pull (RS, regime, themes, 9M EOD)\n'
            '⚡ `Run theme engine` — themes only (no RS/regime recompute)\n'
            "\n"
            "*Trading journal*\n"
            '📝 `journal: <note>` — log a trade observation\n'
            '📖 `show journal` / `journal this week`\n'
            "\n"
            "*Theme management*\n"
            '🚫 `exclude CAR from [exact theme name]` — permanent ban\n'
            '📋 `list exclusions` · ↩️ `remove exclusion CAR from [theme]`\n'
            '🧊 `show cooldowns` — 14d soft blocks from validation removals\n'
            '   `bypass cooldown TICKER [theme] [reason]` — override\n'
            "\n"
            "*Overnight watchlist* (macro instruments — oil, BTC, gold, VIX…)\n"
            '🔔 `show watchlist` · 📌 `track bitcoin with 5%` · ❌ `drop oil`\n'
            "\n"
            "*EP Trading Rules (Qullamaggie v2)*\n"
            "• Filters: score >= 70 (HIGH) · ADV >= $1M · ATR% <= 15% · MCap >= $500M\n"
            "• Entry: 1-min ORB at 9:31 ET · Stop = ORB low · bracket auto-submitted\n"
            "• Skip if ORB range > 1.5x ATR-14 or ORB high never broken\n"
            "• Day 1: hold full · Day 2+: trail 10/20-SMA · stop floor = Day 1 low\n"
            "• Partial 1/3 Day 3-5; stop → breakeven after partial\n"
            "• 9M Day 2: prior-day-low stop; shape-tag filter (uptrend/pullback)\n"
            "• Safeguards: max 4 open · 2% daily loss · 5-loss circuit breaker\n"
            "_Full doc: EP_TRADING_RULES.md_\n"
            "\n"
            "_Still-working but off-menu: /9m /themes /clusters /spend /rules /eps_"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _handle_rules(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /rules — EP trading rules summary."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        text = (
            "*EP Trading Rules (Qullamaggie v2)*\n"
            "\n"
            "*Pre-Trade Filters*\n"
            "• EP Score >= 70 (HIGH tier)\n"
            "• ADV >= $1M · ATR% <= 15% · MCap >= $500M\n"
            "\n"
            "*Entry — Opening Range Breakout*\n"
            "• Opening Range = first 5-min bar (9:30-9:35)\n"
            "• Buy when price breaks above ORB High\n"
            "• Entry price = ORB High · Stop = ORB Low\n"
            "• Skip if ORB range > 1.5x ATR-14 (stop too wide)\n"
            "• Skip if ORB High never broken (no breakout)\n"
            "• Max 3 entry attempts per day\n"
            "\n"
            "*Day 1*\n"
            "• Hold full position through close (no partial)\n"
            "• Hard stop = ORB Low (bar low breach)\n"
            "\n"
            "*Day 2+ Position Management*\n"
            "• Hard stop floor = Day 1 intraday low (never raised)\n"
            "• Trail: 10-SMA if 10 > 20, else 20-SMA\n"
            "• Exit on daily close < effective stop\n"
            "• effective stop = max(hard stop, SMA, breakeven)\n"
            "\n"
            "*Partial Profit (Day 3-5)*\n"
            "• Day 3-4: sell 1/3 if in profit\n"
            "• Day 5: sell 1/3 regardless\n"
            "• After partial: stop floor moves to breakeven\n"
            "\n"
            "Full doc: EP_TRADING_RULES.md"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _handle_trades(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /trades — show live (Alpaca) + paper trade positions and P&L."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        try:
            from core.router import get_agent_url
            import httpx

            url = get_agent_url("market_intelligence")
            if not url:
                await update.message.reply_text("Market agent not available.")
                return

            secret = self._secrets.internal_api_secret
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{url}/trades/summary",
                    headers={"X-Apollo-Secret": secret},
                )
                resp.raise_for_status()
                data = resp.json()

            lines = []

            # ── Live (Alpaca) trades ──
            live = data.get("live")
            if live and not live.get("error"):
                lines.append("*Alpaca Paper Trading*")
                lines.append("")

                # Open positions
                open_pos = live.get("open_positions", [])
                if open_pos:
                    lines.append(f"*Open ({len(open_pos)}):*")
                    for p in open_pos:
                        ticker = p["ticker"]
                        entry = p.get("entry_price")
                        current = p.get("current_price")
                        stop = p.get("stop_price")
                        shares = p.get("remaining_shares", 0)
                        hold = p.get("hold_days", 0)
                        unrealized = p.get("unrealized_pnl", 0)
                        mkt_val = p.get("market_value", 0)
                        realized = p.get("total_pnl", 0)
                        partial = " (partial taken)" if p.get("partial_taken") else ""

                        entry_str = f"${entry:.2f}" if entry else "?"
                        current_str = f"${current:.2f}" if current else "?"
                        pnl_emoji = "🟢" if unrealized > 0 else "🔴" if unrealized < 0 else "⚪"

                        lines.append(
                            f"  {pnl_emoji} *{ticker}* · {hold}d{partial}\n"
                            f"      Entry: {entry_str} → Now: {current_str}\n"
                            f"      {shares:.0f} shares · ${mkt_val:,.0f} position\n"
                            f"      Stop: ${stop:.2f} · Unreal: ${unrealized:+,.2f}"
                        )
                        if realized:
                            lines[-1] += f" · Real: ${realized:+,.2f}"
                    lines.append("")
                else:
                    lines.append("No open positions\n")

                # Last 3 closed
                closed_trades = live.get("recent_closed", [])
                if closed_trades:
                    lines.append("*Last 3 closed:*")
                    for t in closed_trades:
                        pnl = t.get("total_pnl", 0)
                        emoji = "✅" if pnl > 0 else "❌"
                        entry = t.get("entry_price")
                        hold = t.get("hold_days", 0)
                        score = t.get("ep_score", 0)
                        # Get exit price from exits JSON
                        exits = t.get("exits", [])
                        if isinstance(exits, str):
                            import json
                            exits = json.loads(exits or "[]")
                        last_exit = exits[-1] if exits else {}
                        exit_price = last_exit.get("price")
                        exit_reason = last_exit.get("reason", "?")

                        entry_str = f"${entry:.2f}" if entry else "?"
                        exit_str = f"${exit_price:.2f}" if exit_price else "?"
                        lines.append(
                            f"  {emoji} *{t['ticker']}* ${pnl:+,.2f} ({hold}d)\n"
                            f"      {entry_str} → {exit_str} · {exit_reason} · score {score:.0f}"
                        )
                    lines.append("")

                # Totals
                closed_count = live.get("winners", 0) + live.get("losers", 0)
                lines.append("*Totals:*")
                lines.append(f"  Trades: {live.get('total', 0)} ({live.get('open_count', 0)} open)")
                if closed_count > 0:
                    lines.append(f"  W/L: {live['winners']}/{live['losers']} ({live['win_rate']:.0f}% win)")
                    lines.append(f"  Realized P&L: ${live['realized_pnl']:+,.2f}")
            elif live and live.get("error"):
                lines.append(f"*Alpaca:* error — {live['error']}\n")

            # ── Paper (backtester) trades ──
            paper = data.get("paper")
            if paper and not paper.get("error"):
                has_activity = (paper.get("closed_trades", 0) > 0
                                or paper.get("open_positions", 0) > 0)
                if has_activity:
                    lines.append("")
                    lines.append("━━━━━━━━━━━━━━━━━━━━")
                    lines.append("*Paper Trades (EOD sim)*")
                    lines.append("")

                    # Open positions
                    p_open = paper.get("open_details", [])
                    if p_open:
                        lines.append(f"*Open ({len(p_open)}):*")
                        for p in p_open:
                            ticker = p.get("ticker", "?")
                            entry = p.get("last_entry_price")
                            stop = p.get("stop_price")
                            shares = p.get("remaining_shares", 0)
                            hold = p.get("hold_days", 0)
                            score = p.get("ep_score", 0)
                            pnl = p.get("total_pnl", 0)
                            pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"

                            entry_str = f"${entry:.2f}" if entry else "?"
                            stop_str = f"${stop:.2f}" if stop else "?"
                            lines.append(
                                f"  {pnl_emoji} *{ticker}* · {hold}d\n"
                                f"      Entry: {entry_str} · Stop: {stop_str}\n"
                                f"      {shares:.0f} shares · Score: {score:.0f}\n"
                                f"      Unreal P&L: ${pnl:+,.2f}"
                            )
                        lines.append("")
                    else:
                        lines.append("No open positions\n")

                    # Recent closed
                    p_recent = paper.get("recent_trades", [])
                    p_closed_list = [t for t in p_recent if t.get("status") == "closed"]
                    if p_closed_list:
                        def _parse_json_list(raw) -> list:
                            import json
                            try:
                                return json.loads(raw) if isinstance(raw, str) else (raw or [])
                            except Exception:
                                return []
                        def _attempt_count(entries_raw) -> int:
                            entries = _parse_json_list(entries_raw)
                            if not entries:
                                return 0
                            return max(e.get("attempt", i + 1) for i, e in enumerate(entries))
                        def _fmt_attempts(entries_raw, exits_raw, prefix="      ") -> list:
                            entries = _parse_json_list(entries_raw)
                            exits = _parse_json_list(exits_raw)
                            if not entries:
                                return []
                            out = []
                            e0 = entries[0]
                            ep = e0.get("price", e0.get("entry_price", 0))
                            es = e0.get("stop", e0.get("stop_price", 0))
                            out.append(f"{prefix}ORB entry=${ep:.2f} stop=${es:.2f}")
                            exits_by_att = {ex.get("attempt", i+1): ex for i, ex in enumerate(exits)}
                            for e in entries:
                                att = e.get("attempt", "?")
                                in_str = (e.get("time","") or "")[:16][11:16] or "?"
                                ex = exits_by_att.get(att, {})
                                out_str = ((ex.get("time","") or "")[:16][11:16]) or "open"
                                reason = ex.get("reason", "open")
                                pnl = ex.get("pnl", 0)
                                out.append(f"{prefix}#{att} {in_str}→{out_str} ({reason}) ${pnl:+.0f}")
                            return out
                        lines.append("*Last closed:*")
                        for t in p_closed_list[:3]:
                            pnl = t.get("total_pnl", 0)
                            emoji = "✅" if pnl > 0 else "❌"
                            score = t.get("ep_score", 0)
                            gap = t.get("gap_pct")
                            gap_str = f" +{gap:.1f}%" if gap else ""
                            num_att = _attempt_count(t.get("entries"))
                            att_str = f" {num_att}x" if num_att > 1 else ""
                            lines.append(
                                f"  {emoji} *{t['ticker']}*{gap_str} score={score:.0f}{att_str} "
                                f"${pnl:+,.2f} ({t.get('hold_days', 0)}d)"
                            )
                            lines += _fmt_attempts(t.get("entries"), t.get("exits"))
                        lines.append("")

                    # Totals
                    p_closed_count = paper.get("closed_trades", 0)
                    lines.append("*Totals:*")
                    lines.append(f"  Trades: {paper['total_trades']} ({paper['open_positions']} open)")
                    if p_closed_count > 0:
                        lines.append(f"  W/L: {paper['winners']}/{paper['losers']} ({paper['win_rate']:.0f}% win)")
                        lines.append(f"  Realized P&L: ${paper['realized_pnl']:+,.2f}")
                    skipped = paper.get("skipped", 0)
                    if skipped:
                        lines.append(f"  Filtered: {skipped}")

            if not lines:
                lines.append("No trades yet.")

            await self._reply(update, "\n".join(lines))
        except Exception as e:
            logger.error(f"/trades failed: {e}")
            await update.message.reply_text(f"Error loading trades: {e}")

    # ── Market-intelligence slash commands ───────────────────────────────────

    _MARKET_SLASH_COMMANDS = {
        "/hud", "/ep", "/eps", "/9m", "/themes", "/clusters", "/regime",
    }

    async def _dispatch_market_slash(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Generic handler for all market-intelligence slash commands."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return
        # Extract command + any trailing args. e.g. "/crypto AI" -> task="/crypto AI"
        # so handlers like _handle_crypto_query can route on the category arg.
        # Strip the @botname suffix from the command token only.
        full = (update.message.text or "").strip()
        parts = full.split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        task = (cmd + " " + args).strip() if args else cmd

        import uuid, httpx
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        url = get_agent_url("market_intelligence")
        if not url:
            await update.message.reply_text("Market agent not available.")
            return

        req = AgentRequest(
            task=task,
            user_id=update.effective_user.id,
            conversation_id=str(update.effective_user.id),
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}/task",
                    json=req.model_dump(),
                    headers={"X-Apollo-Secret": self._secrets.internal_api_secret},
                )
                resp.raise_for_status()
                data = resp.json()
            if "result" in data:
                result = data["result"] or ""
            else:
                result = data.get("error") or "No response."
        except Exception as e:
            logger.error(f"{cmd} failed: {e}")
            result = f"Error: {e}"

        # Handlers that already delivered the response via Telegram (e.g.
        # /why, /setup — body sent through send_telegram_message + inline
        # keyboard) return result="" so we don't echo a redundant
        # "Lifecycle for X sent." trailer.
        if not result.strip():
            return
        await self._reply(update, result)

    async def _handle_ep_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/ep — all EP alerts in one message (2026-05-29: dropped the summary +
        [View HIGH]/[View MODERATE] drill-down step per operator; the extra tap
        wasn't needed). Renders via the shared EP block (`/eps_detail ALL`).
        (/eps routes here too as a silent alias for back-compat with pinned messages.)"""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        import httpx
        from shared.dates import last_trading_day
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        today_str = last_trading_day().isoformat()
        url = get_agent_url("market_intelligence")
        if not url:
            await update.message.reply_text("Market agent not available.")
            return

        req = AgentRequest(
            task=f"/eps_detail ALL {today_str}",
            user_id=update.effective_user.id,
            conversation_id=str(update.effective_user.id),
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}/task",
                    json=req.model_dump(),
                    headers={"X-Apollo-Secret": self._secrets.internal_api_secret},
                )
                resp.raise_for_status()
                ep_text = resp.json().get("result") or "No EP data."
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
            return

        await update.message.reply_text(ep_text, parse_mode=ParseMode.MARKDOWN)

    async def _handle_themes_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/themes — compact summary with stage drill-down buttons."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        import httpx
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        url = get_agent_url("market_intelligence")
        if not url:
            await update.message.reply_text("Market agent not available.")
            return

        req = AgentRequest(
            task="/themes_detail SUMMARY",
            user_id=update.effective_user.id,
            conversation_id=str(update.effective_user.id),
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}/task",
                    json=req.model_dump(),
                    headers={"X-Apollo-Secret": self._secrets.internal_api_secret},
                )
                resp.raise_for_status()
                summary_text = resp.json().get("result") or "No theme data."
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Accelerating", callback_data="themes:Accelerating"),
                InlineKeyboardButton("Nascent", callback_data="themes:Nascent"),
                InlineKeyboardButton("All Active", callback_data="themes:All"),
            ]
        ])
        await update.message.reply_text(summary_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    async def _handle_trades_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/trades — compact summary with [Live Positions] [Paper Trades] [Closed Today] buttons."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        import httpx
        from shared.dates import last_trading_day
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        today_str = last_trading_day().isoformat()
        url = get_agent_url("market_intelligence")
        if not url:
            await update.message.reply_text("Market agent not available.")
            return

        req = AgentRequest(
            task=f"/trades_detail summary {today_str}",
            user_id=update.effective_user.id,
            conversation_id=str(update.effective_user.id),
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}/task",
                    json=req.model_dump(),
                    headers={"X-Apollo-Secret": self._secrets.internal_api_secret},
                )
                resp.raise_for_status()
                summary_text = resp.json().get("result") or "No trade data."
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Closed Trades", callback_data=f"trades:closed:{today_str}"),
                InlineKeyboardButton("Skipped", callback_data="trades:skipped"),
            ],
            [
                InlineKeyboardButton("Paper (legacy)", callback_data="trades:paper"),
            ],
        ])
        try:
            await update.message.reply_text(summary_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Exception as markdown_err:
            # Any unmatched `_` or `*` in dynamic content (e.g. exit reasons like `stop_hit`)
            # makes Telegram reject the whole message. Fall back to plain text so the user
            # always sees something instead of silence.
            logger.warning(f"/trades markdown send failed, retrying as plain text: {markdown_err}")
            await update.message.reply_text(summary_text, reply_markup=keyboard)

    async def _handle_hud_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/hud — sends HUD, pins it, and stores the message ID for hourly auto-refresh."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        import uuid, httpx
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        url = get_agent_url("market_intelligence")
        if not url:
            await update.message.reply_text("Market agent not available.")
            return

        req = AgentRequest(
            task="/hud",
            user_id=update.effective_user.id,
            conversation_id=str(update.effective_user.id),
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}/task",
                    json=req.model_dump(),
                    headers={"X-Apollo-Secret": self._secrets.internal_api_secret},
                )
                resp.raise_for_status()
                result = resp.json().get("result") or "No response."
        except Exception as e:
            logger.error(f"/hud failed: {e}")
            await update.message.reply_text(f"Error: {e}")
            return

        # Drill-down buttons: one tap per /hud section. Survive the hourly
        # refresh because editMessageText without reply_markup leaves the
        # existing keyboard intact.
        hud_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Regime",    callback_data="hud:regime"),
                InlineKeyboardButton("Themes",    callback_data="hud:themes"),
                InlineKeyboardButton("EP",        callback_data="hud:ep"),
            ],
            [
                InlineKeyboardButton("9M",        callback_data="hud:9m"),
                InlineKeyboardButton("Clusters",  callback_data="hud:clusters"),
                InlineKeyboardButton("Watchlist", callback_data="hud:watchlist"),
            ],
        ])
        sent_msg = await update.message.reply_text(
            result, parse_mode=ParseMode.MARKDOWN, reply_markup=hud_keyboard
        )

        # Pin the message (shows system notification in chat — expected)
        try:
            await self._app.bot.pin_chat_message(
                update.effective_chat.id, sent_msg.message_id, disable_notification=True
            )
        except Exception as e:
            logger.warning(f"/hud pin failed (non-fatal): {e}")

        # Store IDs in market agent so hourly job can edit the message
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{url}/hud/pin",
                    json={"chat_id": update.effective_chat.id, "message_id": sent_msg.message_id},
                    headers={"X-Apollo-Secret": self._secrets.internal_api_secret},
                )
        except Exception as e:
            logger.warning(f"/hud/pin store failed (non-fatal): {e}")

    async def _handle_agents(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /agents — alias for /status."""
        await self._handle_status(update, context)

    async def _handle_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status — system-level health (DB, Redis, agents, market pipeline)."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        from core.router import health_check_all_agents, get_market_pipeline_status
        # return_exceptions=True so a single sub-check raising doesn't kill
        # the entire /status response (2026-05-13 incident: _check_account_mode
        # raised ModuleNotFoundError in orchestrator container that lacks
        # market-agent code; whole /status returned nothing).
        results = await asyncio.gather(
            health_check_all_agents(),
            get_market_pipeline_status(),
            self._check_db(),
            self._check_redis(),
            self._check_claude(),
            self._check_account_mode(),
            return_exceptions=True,
        )
        def _unwrap(idx, default):
            r = results[idx]
            if isinstance(r, BaseException):
                logger.warning(f"/status sub-check {idx} raised: {r!r}")
                return default
            return r

        agent_health = _unwrap(0, {})
        market_status = _unwrap(1, None)
        db_ok, db_err = _unwrap(2, (False, "check failed"))
        redis_ok, redis_err = _unwrap(3, (False, "check failed"))
        claude_ok, claude_err = _unwrap(4, (False, "check failed"))
        account_info = _unwrap(5, ["⚠️ Account check failed"])

        lines = ["*System Status*\n"]

        # Infrastructure
        lines.append("*Infrastructure*")
        lines.append(f"{'🟢' if db_ok else '🔴'} PostgreSQL — {'ok' if db_ok else f'down: {_safe(db_err)} — is Docker running?'}")
        lines.append(f"{'🟢' if redis_ok else '🔴'} Redis — {'ok' if redis_ok else f'down: {_safe(redis_err)} — is Docker running?'}")
        lines.append(f"{'🟢' if claude_ok else '🔴'} Claude API — {'ok' if claude_ok else _safe(claude_err)}")

        # Agents
        lines.append("\n*Agents*")
        agent_hints = {
            "market_intelligence": "restart: bash start.sh",
        }
        for agent_name, (is_healthy, reason) in agent_health.items():
            display = agent_name.replace("_", " ").title()
            if is_healthy:
                lines.append(f"🟢 {display} Agent — running")
            else:
                hint = agent_hints.get(agent_name, "")
                lines.append(f"🔴 {display} Agent — {_safe(reason)}" + (f"\n    {hint}" if hint else ""))

        # Account (paper vs live $, equity)
        if account_info:
            lines.append("")
            lines.append("*Account*")
            for line in account_info:
                lines.append(line)

        # Market pipeline
        if market_status:
            lines.append("")
            lines.append(_format_market_pipeline(market_status))

        # API spend (merged from retired /spend)
        try:
            from core.spend import get_spend_summary
            spend_text = await get_spend_summary()
            if spend_text:
                lines.append("")
                lines.append(spend_text)
        except Exception as e:
            logger.warning(f"Spend section in /status failed (non-fatal): {e}")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _check_db(self) -> tuple[bool, str]:
        try:
            from core.memory import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True, ""
        except Exception as e:
            return False, str(e)[:120]

    async def _check_redis(self) -> tuple[bool, str]:
        try:
            from core.confirmations import get_redis
            r = await get_redis()
            await r.ping()
            return True, ""
        except Exception as e:
            return False, str(e)[:120]

    async def _check_claude(self) -> tuple[bool, str]:
        try:
            import anthropic
            from shared.secrets import get_secrets
            client = anthropic.Anthropic(api_key=get_secrets().anthropic_api_key)
            client.messages.create(
                model=HEALTHCHECK_MODEL,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True, ""
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                return False, "Overloaded — Anthropic is having an outage, check status.anthropic.com"
            if e.status_code == 401:
                return False, "Invalid API key — check ANTHROPIC_API_KEY in .env"
            if e.status_code == 400 and "credit" in str(e).lower():
                return False, "Out of credits — add credits at console.anthropic.com"
            return False, f"API error {e.status_code}: {str(e)[:100]}"
        except Exception as e:
            return False, str(e)[:120]

    async def _check_account_mode(self) -> list[str]:
        """Render per-mode account block for /status.

        Calls market-agent's GET /account/status endpoint via HTTP. The
        orchestrator container can't import agents.market_intelligence
        directly (only agents/base.py is bundled per Dockerfile.orchestrator),
        so all account/strategy info routes through the market-agent
        service the same way all other market-side data does.
        """
        import httpx
        from shared.registry import get_agent_url
        from shared.secrets import get_secrets

        url = get_agent_url("market_intelligence")
        if not url:
            return ["⚠️ Account block unavailable — market-agent URL not set"]

        try:
            secret = get_secrets().internal_api_secret
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{url}/account/status",
                    headers={"X-Apollo-Secret": secret},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return [f"⚠️ Account fetch failed: {str(e)[:120]}"]

        if not data.get("live_trading_enabled", False):
            return ["⚪ Trading: DISABLED (LIVE_TRADING_ENABLED=false)"]

        lines: list[str] = []
        for block in data.get("modes", []):
            mode = block.get("mode", "?")
            icon = "📄" if mode == "paper" else "💰"
            label = "PAPER" if mode == "paper" else "LIVE-$ (real money)"
            routed_strats = block.get("routed_strategies", [])
            # Wrap each strategy ID in backticks — IDs like "9m_day2" contain
            # underscores that Telegram MarkdownV1 interprets as italic start
            # markers. Backticks render as monospace AND skip Markdown parsing
            # inside, so any underscore-containing strategy_id is safe.
            if routed_strats:
                routed = " · routed: " + ", ".join(f"`{s}`" for s in routed_strats)
            else:
                routed = " · (no strategies routed)"
            lines.append(f"{icon} *{label}*{routed}")

            account = block.get("account")
            err = block.get("error")
            if account:
                equity = account.get("equity", 0.0)
                buying_power = account.get("buying_power", 0.0)
                lines.append(f"  Equity: ${equity:,.2f}")
                lines.append(f"  Buying power: ${buying_power:,.2f}")
            elif err:
                lines.append(f"  ⚠️ Account fetch failed: {err[:100]}")
            lines.append("")

        while lines and not lines[-1]:
            lines.pop()
        return lines

    async def _handle_memory(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /memory command — show stored memories."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        try:
            user_id = update.effective_user.id
            from core.memory import search_memories
            memories = await search_memories(user_id, limit=20)

            if not memories:
                await update.message.reply_text("No memories stored yet.")
                return

            lines = ["**Your memories**\n"]
            for m in memories:
                lines.append(f"[{m.category}] {m.content}")

            await update.message.reply_text("\n".join(lines))
        except Exception as e:
            logger.error(f"/memory command failed: {e}")
            await update.message.reply_text(f"Error loading memories: {e}")

    async def _handle_spend(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /spend command — show API spend summary."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        try:
            from core.spend import get_spend_summary
            summary = await get_spend_summary()
            await update.message.reply_text(summary, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"Error fetching spend data: {e}")

    # ── Trade callback handler ────────────────────────────────────────────────

    async def _handle_callback_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle inline keyboard button presses (trade confirm/skip)."""
        query = update.callback_query
        if not query or not query.data:
            return

        user_id = query.from_user.id if query.from_user else None
        if user_id not in self._secrets.telegram_allowed_user_ids:
            await query.answer("Unauthorized")
            return

        # Acknowledge immediately — Telegram times out the spinner after ~5s
        await query.answer()

        callback_data = query.data

        # Forward trade callbacks to market agent
        if callback_data.startswith("trade_confirm:") or callback_data.startswith("trade_skip:"):
            try:
                from agents.market_intelligence.broker.telegram_confirm import handle_callback
                result = await handle_callback(callback_data, user_id=user_id)
                if "confirm" in callback_data or "skip" in callback_data:
                    await query.edit_message_reply_markup(reply_markup=None)
            except Exception as e:
                logger.error(f"Callback handling failed: {e}")

        elif callback_data.startswith(("eps:", "themes:", "trades:")):
            await self._handle_drill_down_callback(query, callback_data)

        elif callback_data.startswith("hud:"):
            await self._handle_hud_drill_down(query, callback_data)

        else:
            pass  # query already answered above

    # ── Inline keyboard drill-down callbacks ──────────────────────────────────

    async def _handle_drill_down_callback(self, query, callback_data: str) -> None:
        """Handle eps:/themes:/trades: drill-down button presses."""
        import httpx
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        url = get_agent_url("market_intelligence")
        if not url:
            await query.edit_message_text("Market agent not available.")
            return

        parts = callback_data.split(":", 2)
        prefix = parts[0]  # eps, themes, trades

        # Determine the sub-command task to send to the market agent
        if prefix == "eps":
            tier = parts[1] if len(parts) > 1 else "HIGH"
            date_str = parts[2] if len(parts) > 2 else ""
            task = f"/eps_detail {tier} {date_str}".strip()
        elif prefix == "themes":
            stage = parts[1] if len(parts) > 1 else "All"
            task = f"/themes_detail {stage}"
        else:  # trades
            view = parts[1] if len(parts) > 1 else "summary"
            date_str = parts[2] if len(parts) > 2 else ""
            task = f"/trades_detail {view} {date_str}".strip()

        user_id = query.from_user.id if query.from_user else 0
        req = AgentRequest(task=task, user_id=user_id, conversation_id=str(user_id))
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}/task",
                    json=req.model_dump(),
                    headers={"X-Apollo-Secret": self._secrets.internal_api_secret},
                )
                resp.raise_for_status()
                result = resp.json().get("result") or "No data."
        except Exception as e:
            logger.error(f"Drill-down callback failed: {e}")
            result = f"Error: {e}"

        # Keep full button set on drill-downs so user can switch views in-place.
        if prefix == "trades":
            from shared.dates import et_today
            today_str = et_today().isoformat()  # ET trading day (UTC date is tomorrow after 8pm ET)
            markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Closed Trades", callback_data=f"trades:closed:{today_str}"),
                    InlineKeyboardButton("Skipped", callback_data="trades:skipped"),
                ],
                [
                    InlineKeyboardButton("Paper (legacy)", callback_data="trades:paper"),
                ],
                [InlineKeyboardButton("← Summary", callback_data="trades:summary")],
            ])
        elif prefix == "eps" and parts[1] != "SUMMARY":
            date_str = parts[2] if len(parts) > 2 else ""
            back_data = f"eps:SUMMARY:{date_str}"
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("← Summary", callback_data=back_data)]])
        elif prefix == "themes" and parts[1] != "All":
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("← All Themes", callback_data="themes:All")]])
        else:
            markup = None

        try:
            await query.edit_message_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
        except Exception as e:
            logger.warning(f"edit_message_text failed, sending new: {e}")
            # Fallback without Markdown — covers both edit-failed (message deleted/old)
            # and parse-error cases. Plain text is better than silence.
            try:
                await query.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
            except Exception:
                await query.message.reply_text(result, reply_markup=markup)

    async def _handle_hud_drill_down(self, query, callback_data: str) -> None:
        """Handle hud: drill-down button presses — sends a new message per section
        so the pinned /hud snapshot stays intact and auto-refreshes."""
        import httpx
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        url = get_agent_url("market_intelligence")
        if not url:
            await query.message.reply_text("Market agent not available.")
            return

        section = callback_data.split(":", 1)[1]
        task_map = {
            "regime":    "/regime",
            "themes":    "/themes_detail All",
            "ep":        "/eps",
            "9m":        "/9m",
            "clusters":  "/clusters",
            "watchlist": "show watchlist",
        }
        task = task_map.get(section)
        if not task:
            return

        user_id = query.from_user.id if query.from_user else 0
        req = AgentRequest(task=task, user_id=user_id, conversation_id=str(user_id))
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}/task",
                    json=req.model_dump(),
                    headers={"X-Apollo-Secret": self._secrets.internal_api_secret},
                )
                resp.raise_for_status()
                result = resp.json().get("result") or "No data."
        except Exception as e:
            logger.error(f"HUD drill-down ({section}) failed: {e}")
            result = f"Error: {e}"

        try:
            await query.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
        except Exception as markdown_err:
            logger.warning(f"HUD drill-down markdown send failed, retrying plain: {markdown_err}")
            await query.message.reply_text(result)

    # ── Confirmation resolution ────────────────────────────────────────────────

    async def _try_resolve_confirmation(
        self,
        user_id: int,
        approved: bool,
        update: Update,
    ) -> bool:
        """
        Try to resolve a pending confirmation with this YES/NO reply.
        Returns True if a confirmation was found and resolved.
        """
        from core.memory import get_pending_confirmations_for_user
        pending = await get_pending_confirmations_for_user(user_id)

        if not pending:
            return False

        # Resolve the most recent pending confirmation
        latest = pending[0]
        confirmation_id = latest["confirmation_id"]

        resolved = await resolve_confirmation(confirmation_id, approved)
        if resolved:
            action = "approved ✅" if approved else "cancelled ❌"
            await update.message.reply_text(f"Action {action}.")
            return True

        return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _reply(self, update: Update, text: str) -> None:
        """Send a reply, splitting into chunks if over Telegram's 4096-char limit."""
        chunks = self._split_message(text)
        for chunk in chunks:
            await self._send_chunk(update, chunk)

    def _split_message(self, text: str, limit: int = 4000) -> list[str]:
        """Split text into chunks at section boundaries (double newline)."""
        if len(text) <= limit:
            return [text]
        chunks: list[str] = []
        remaining = text
        while len(remaining) > limit:
            split_at = remaining.rfind("\n\n", 0, limit)
            if split_at == -1:
                split_at = remaining.rfind("\n", 0, limit)
            if split_at == -1:
                split_at = limit
            chunks.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks

    async def _send_chunk(self, update: Update, text: str) -> None:
        """Send a single chunk, falling back to plain text if Markdown fails."""
        # Strip Markdown headings — Telegram doesn't render them
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        if "```" in text:
            html = self._md_to_html(text)
            try:
                await update.message.reply_text(html, parse_mode=ParseMode.HTML)
                return
            except Exception:
                pass  # fall through to markdown/plain attempts
        try:
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            # Markdown parse error — strip v1 formatting chars and retry
            try:
                plain = re.sub(r"[*_`\[\]]", "", text)
                await update.message.reply_text(plain)
            except Exception as e:
                logger.error(f"Failed to send reply: {e}")

    @staticmethod
    def _md_to_html(text: str) -> str:
        """Convert Markdown-ish text with ``` blocks to Telegram HTML."""
        import html as html_mod
        parts = text.split("```")
        result = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # Inside code block — wrap in <pre>
                result.append(f"<pre>{html_mod.escape(part)}</pre>")
            else:
                # Outside code block — convert *bold* to <b>, escape HTML
                escaped = html_mod.escape(part)
                # Restore bold: *text* → <b>text</b>
                escaped = re.sub(r"\*([^*]+)\*", r"<b>\1</b>", escaped)
                result.append(escaped)
        return "".join(result)

    async def _send_typing_indicator(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Periodically send 'typing...' indicator while processing."""
        chat_id = update.effective_chat.id
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except asyncio.CancelledError:
                return
            except Exception:
                pass  # Non-fatal — skip this tick, try again next interval
            try:
                await asyncio.sleep(TYPING_INTERVAL)
            except asyncio.CancelledError:
                return

    # ── Application setup ─────────────────────────────────────────────────────

    def build_application(self) -> Application:
        """Build and configure the python-telegram-bot Application."""
        # Inject the heartbeat-writing bot so the poll loop emits a liveness
        # signal the market-agent watchdog can monitor (#153). Behaviour is
        # otherwise identical to a default-token ExtBot.
        app = (
            Application.builder()
            .bot(HeartbeatExtBot(self._secrets.telegram_bot_token))
            .build()
        )

        app.add_handler(CommandHandler("start", self._handle_start))
        app.add_handler(CommandHandler("help", self._handle_help))
        app.add_handler(CommandHandler("agents", self._handle_agents))
        app.add_handler(CommandHandler("setup", self._handle_setup))
        app.add_handler(CommandHandler("status", self._handle_status))
        app.add_handler(CommandHandler("spend", self._handle_spend))
        app.add_handler(CommandHandler("rules", self._handle_rules))
        app.add_handler(CommandHandler("trades", self._handle_trades_command))
        # /hud gets a specialized handler — it pins the message and stores the ID
        app.add_handler(CommandHandler("hud", self._handle_hud_command))
        # /ep (primary) + /eps (silent alias for back-compat) and /themes send summary + drill-down
        app.add_handler(CommandHandler("ep", self._handle_ep_command))
        app.add_handler(CommandHandler("eps", self._handle_ep_command))
        app.add_handler(CommandHandler("themes", self._handle_themes_command))
        # Other market-intelligence slash commands — bypass orchestrator LLM.
        # Kept as handlers so old pinned messages and muscle memory still work,
        # but removed from the bot menu to keep the command surface lean.
        for _cmd in ("9m", "clusters", "regime", "pregame", "audit", "crypto", "altseason", "parabolic",
                     "strategy", "watchlist", "wick", "why", "setup", "flags", "flag", "fishhook", "dryrun",
                     "missed", "trade",
                     # 2026-05-22+ new commands — must be registered here AND have a
                     # BotCommand entry above. Missing this list = silent drop in Telegram
                     # (BotCommand only affects autocomplete; CommandHandler is the actual route).
                     "sugarbabies", "sugarbaby", "timestop",
                     # 5 shadow entry-technique detectors consolidated into /detectors
                     # (#218, operator command review 2026-06-06).
                     "detectors", "unknownrate",
                     # /breadth retired 2026-06-14 → merged into /regime (operator).
                     "watch", "rubric",
                     # 2026-05-28 #138 operator-confirm commands
                     "partialnow", "syncnow",
                     # 2026-06-09 #254 operator ground-truth corpus
                     "review", "reviews", "spotted"):
            app.add_handler(CommandHandler(_cmd, self._dispatch_market_slash))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )
        app.add_handler(CallbackQueryHandler(self._handle_callback_query))

        self._app = app
        return app

    async def set_webhook(self, webhook_url: str) -> None:
        """Register the webhook URL with Telegram and set the bot command menu."""
        if self._app is None:
            raise RuntimeError("Application not built yet. Call build_application() first.")
        await self._app.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"],
        )
        await self._register_commands()
        logger.info(f"Telegram webhook set to: {webhook_url}")

    async def _register_commands(self) -> None:
        """Register bot commands with BotFather so they appear in the / menu."""
        from telegram import BotCommand
        # Lean menu. Hidden but still-working commands (kept as handlers
        # for back-compat / muscle memory): /eps, /9m, /themes, /clusters,
        # /spend, /rules, /setup, /agents. (/regime promoted to the menu 2026-06-14;
        # /breadth retired → merged into /regime.)
        commands = [
            BotCommand("hud",          "Snapshot: regime, EPs, 9M, themes, clusters — drill-down buttons"),
            BotCommand("pregame",      "Daily trade shortlist"),
            BotCommand("ep",           "EP alerts (MAGNA53 + 9M) — tap to drill down"),
            BotCommand("trades",       "Positions + P&L — tap to drill down"),
            BotCommand("watchlist",    "Friday curated chart-review list (cross-source aggregator)"),
            BotCommand("setup",        "/setup TICKER [days] — reverse-lookup detector chronology"),
            BotCommand("why",          "/why TICKER [date] — detection + entry diagnosis"),
            BotCommand("trade",        "/trade TICKER [date] — full trade anatomy (entry/stops/exits)"),
            BotCommand("flags",        "Continuation flag scan — TRIGGERED/COILED/TIGHTENING"),
            BotCommand("detectors",    "🔭 Intraday entry-technique detectors (shadow) — today + 7d roll-up"),
            BotCommand("unknownrate", "🕳 Source-coverage KPI (#211) — unknown-rate on EP movers"),
            BotCommand("regime",       "📊 Market condition + Stockbee breadth matrix (MAs · VIX · T2108 · cluster)"),
            BotCommand("fishhook",     "Fishhook anchors — armed/triggered breakout candidates"),
            BotCommand("sugarbabies",  "🍬 Persistent Sugar Baby cohort (Pradeep watchlist)"),
            BotCommand("watch",        "Stocks to watch — /watch = actionable tight-range · /watch all = full universe"),
            BotCommand("timestop",     "/timestop TICKER — confirm time-stop exit of 9M Day 2 meanderer"),
            BotCommand("partialnow",   "/partialnow TICKER — operator-confirm immediate partial exit (1/3 sell)"),
            BotCommand("syncnow",      "/syncnow [paper|live] — operator-confirm DB↔broker sync_positions"),
            BotCommand("review",       "/review TICKER <agree|toohigh|toolow|notep> — label a grade (bare /review lists corpus)"),
            BotCommand("spotted",      "/spotted TICKER <grade> <narrative> — inject a real EP you spotted (e.g. a tweet)"),
            BotCommand("missed",       "Missed EPs — top winners we didn't enter (opportunity cost)"),
            BotCommand("strategy",     "Strategy registry — phases, KPIs, enable/disable/promote"),
            BotCommand("status",       "System health + API spend"),
            BotCommand("help",         "Capabilities, rules, command reference"),
            BotCommand("start",        "Restart / re-introduce"),
        ]
        await self._app.bot.set_my_commands(commands)
        logger.info("Bot commands registered with Telegram")
