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
from shared.dates import et_hhmm

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

        args = " ".join(context.args) if context.args else ""
        if not args.strip():
            await update.message.reply_text("Usage: `/setup TICKER [days]`", parse_mode=ParseMode.MARKDOWN)
            return

        ack = await self._post_market_task_or_reply(
            update, f"/setup {args}", update.effective_user.id, "(no response)"
        )
        if ack is None:
            return

        # Market agent sends the timeline itself; only echo the ack if it's
        # a fallback body (delivery failed) or a usage hint.
        if not ack.startswith("📬"):
            await self._reply_with_fallback(update, ack)

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
                            # Two fixes, 2026-08-08, both already made on the market-agent copy
                            # in backtester/tracker.py — this orchestrator-side duplicate still
                            # had both:
                            #  (1) TIME WAS UTC. `[11:16]` slices the stored ISO string raw, so
                            #      a 09:35 ET fill printed as 13:35. `et_hhmm` (shared.dates) is
                            #      the one helper; three surfaces across two containers each had
                            #      this same slice.
                            #  (2) LEGS COLLIDED. A dict keyed on `attempt` dropped the earlier
                            #      leg: a partial profit-take carries no `attempt` (defaults to
                            #      1) and the stop carries an explicit `attempt: 1`, so the stop
                            #      silently overwrote the profit-take — the operator saw a plain
                            #      loss on a trade that had banked money first.
                            exits_by_att: dict = {}
                            for i, ex in enumerate(exits):
                                exits_by_att.setdefault(ex.get("attempt", i + 1), []).append(ex)
                            for e in entries:
                                att = e.get("attempt", "?")
                                in_str = et_hhmm(e.get("time")) or "?"
                                legs = exits_by_att.get(att) or [{}]
                                for j, ex in enumerate(legs):
                                    out_str = et_hhmm(ex.get("time")) or "open"
                                    reason = ex.get("reason", "open")
                                    pnl = ex.get("pnl", 0)
                                    lead = (f"{prefix}#{att} {in_str}→" if j == 0
                                            else f"{prefix}    ↳ ")
                                    out.append(f"{lead}{out_str} ({reason}) ${pnl:+.0f}")
                                if len(legs) > 1:
                                    net = sum(float(x.get("pnl") or 0) for x in legs)
                                    out.append(f"{prefix}    = net ${net:+.0f}")
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

    # /ideas front door (ADR 0004): per-strategy buttons, each drilling into the
    # strategy's existing board as an edit-in-place deep-dive. SINGLE source for the
    # keyboard AND the callback task-map so they can never drift (key, label, task).
    # #270's /anticipation (Pradeep anticipation play) is in. No "Stocks in Play" button — the summary's
    # Stocks-in-Play SECTION already shows the substrate (the button just re-showed it); the
    # full board stays reachable via the standalone /watch command. As ADR-0004 Phase 2-5
    # migrate the other detectors into mi_stocks_in_play, each line reads from the substrate.
    _IDEAS_STRATEGIES = [
        ("magna53",  "🎯 MAGNA53",   "/eps"),
        ("9m",       "🏦 9M",        "/9m"),
        ("flags",    "🚩 HTF",       "/htf"),
        ("anticipation", "⏱️ Anticipation", "/anticipation"),
    ]

    # ── S3/F13: single funnel for AgentRequest -> POST {url}/task -> reply ─────
    # This boilerplate used to be hand-copied at 6+ call sites (/setup, /ep,
    # /themes [both branches], /trades, /hud, /ideas, /dispatch_market_slash) and
    # had already diverged: the /themes-arg lookup had NO plain-text retry on a
    # Telegram Markdown-400 (an underscore-heavy theme name -> hard "Error:"
    # reply) while /ideas degraded gracefully. These two helpers are the single
    # source now; callers keep their own site-specific defaults/timeouts/error
    # text, only the POST + the Markdown->plain fallback are shared.
    async def _post_market_task(
        self, task: str, user_id: int, timeout: float = 30
    ) -> Optional[str]:
        """POST an AgentRequest to the market agent, return the result text.
        Delegates the actual POST + error handling to `core.router.call_agent`
        (simplify GROUP 3, 2026-07-03 — this used to hand-roll its own
        POST {url}/task + headers, duplicating what call_agent already does for
        the orchestrator). Returns None if the market agent isn't registered
        (caller shows its own "Market agent not available." message — kept out
        of this helper so callers preserve their exact pre-refactor text).
        Raises RuntimeError on transport/HTTP/agent-side failure — every
        existing call site already catches broadly and surfaces
        `f"Error: {e}"`, so this simply funnels into that existing path."""
        from core.router import call_agent
        from shared.models import AgentName, AgentRequest
        from shared.registry import get_agent_url

        if not get_agent_url("market_intelligence"):
            return None

        req = AgentRequest(task=task, user_id=user_id, conversation_id=str(user_id))
        resp = await call_agent(AgentName.MARKET_INTELLIGENCE, req, timeout=timeout)
        if not resp.success:
            raise RuntimeError(resp.error or "market agent call failed")
        return resp.result or ""

    async def _post_market_task_or_reply(
        self, update: Update, task: str, user_id: int, default_text: str,
    ) -> Optional[str]:
        """Second-layer funnel over `_post_market_task` (simplify GROUP 3,
        2026-07-03) — 6 call sites (/ep, /themes [both branches], /trades,
        /hud, /ideas) each pasted the same try/except -> None-check ->
        default-text boilerplate around `_post_market_task`. This sends the
        "Error: {e}" / "Market agent not available." replies itself and
        returns None (caller should return immediately without sending
        anything else); on success it returns the result text — substituted
        with `default_text` if empty — for the caller to send with its own
        formatting (`_reply_with_fallback` + any keyboard). Restores the
        None-check the /hud site had silently dropped (it showed "No
        response." instead of "Market agent not available.")."""
        try:
            result = await self._post_market_task(task, user_id)
        except Exception as e:
            logger.error(f"{task} failed: {e}")
            await update.message.reply_text(f"Error: {e}")
            return None
        if result is None:
            await update.message.reply_text("Market agent not available.")
            return None
        return result or default_text

    async def _reply_with_fallback(
        self,
        update: Update,
        text: str,
        *,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ):
        """Send a market-agent result with Markdown, retrying as PLAIN TEXT on a
        Telegram 400 (an unmatched `_`/`*` in dynamic content — e.g. an
        underscore-heavy ticker or theme name — makes Telegram reject the whole
        Markdown-parsed message). Mirrors /ideas' pre-existing degrade-gracefully
        pattern so every market-slash site gets it, not just the ones that
        happened to add it by hand. Returns the sent Message (callers like /hud
        need the message_id to pin/store)."""
        try:
            return await update.message.reply_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )
        except Exception as e:
            logger.warning(f"Markdown send failed, retrying plain text: {e}")
            return await update.message.reply_text(text, reply_markup=reply_markup)

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

        try:
            result = await self._post_market_task(task, update.effective_user.id)
        except Exception as e:
            logger.error(f"{cmd} failed: {e}")
            result = f"Error: {e}"
        else:
            # None = market agent not registered; "" (result key present but
            # empty) is the deliberate /why, /setup already-delivered signal
            # (body sent through send_telegram_message + inline keyboard) —
            # preserved below so we don't echo a redundant trailer.
            if result is None:
                result = "Market agent not available."

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

        from shared.dates import last_trading_day

        today_str = last_trading_day().isoformat()
        ep_text = await self._post_market_task_or_reply(
            update, f"/eps_detail ALL {today_str}", update.effective_user.id, "No EP data."
        )
        if ep_text is None:
            return

        await self._reply_with_fallback(update, ep_text)

    async def _handle_themes_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/themes — full ecosystem board (ADR 0032); with an arg, two-way
        ticker/theme lookup via /themes_lookup."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        # Two-way lookup: `/themes TICKER` (its themes) or `/themes <name>` (its stocks). With an
        # arg, forward it for the lookup + reply directly (no drill-down buttons); bare `/themes`
        # falls through to the stage-summary below.
        _args = " ".join(context.args).strip() if context.args else ""
        if _args:
            lookup_text = await self._post_market_task_or_reply(
                update, f"/themes_lookup {_args}", update.effective_user.id, "No match."
            )
            if lookup_text is None:
                return
            # S3/F13 fix: this used to send Markdown with no fallback — an
            # underscore-heavy theme name 400'd Telegram and fell straight into
            # a hard "Error: ..." reply. _reply_with_fallback gives it the same
            # plain-text retry /ideas already had.
            await self._reply_with_fallback(update, lookup_text)
            return

        # ADR 0032 (operator 2026-07-14): bare /themes shows the full ecosystem
        # board directly — no stage drill-down buttons. Forwards "/themes" -> the
        # market agent's _handle_theme_query (format_ecosystem_board: ecosystems
        # ranked by boosted D3 score, sub-themes nested). _reply splits across
        # messages since the hierarchical board exceeds Telegram's 4096-char limit.
        board_text = await self._post_market_task_or_reply(
            update, "/themes", update.effective_user.id, "No theme data."
        )
        if board_text is None:
            return
        await self._reply(update, board_text)

    async def _handle_trades_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/trades — compact summary with [Live Positions] [Paper Trades] [Closed Today] buttons."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        from shared.dates import last_trading_day

        today_str = last_trading_day().isoformat()

        # `/trades FIGS` — a TICKER argument (operator 2026-08-08: *"the /trades FIGS command
        # just return /trades"*). This handler HARDCODED the summary task and never read
        # `context.args`, so the ticker was discarded here, in the Telegram layer, before the
        # agent could ever see it. The agent-side routing for `/trades TICKER` was added and
        # verified earlier the same day by calling `execute_task` directly — which passes the
        # string straight through and therefore could not catch this. The command a human types
        # was still broken.
        # ⚠ That is the verify-the-operator-facing-surface rule: the only proof that a command
        # works is the command, not the function behind it.
        _args = getattr(context, "args", None) or []
        _tk = _args[0].strip().upper() if _args else ""
        if _tk.isalpha() and 2 <= len(_tk) <= 5:
            detail = await self._post_market_task_or_reply(
                update, f"/trades_detail {_tk} {today_str}", update.effective_user.id,
                f"No trades found for {_tk}.",
            )
            if detail is not None:
                # No drill-down keyboard here: those buttons are summary views, and attaching
                # them to a single-ticker answer would offer navigation that ignores the ticker.
                await self._reply_with_fallback(update, detail)
            return

        summary_text = await self._post_market_task_or_reply(
            update, f"/trades_detail summary {today_str}", update.effective_user.id, "No trade data."
        )
        if summary_text is None:
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
        # Any unmatched `_` or `*` in dynamic content (e.g. exit reasons like `stop_hit`)
        # makes Telegram reject the whole message; _reply_with_fallback retries plain
        # text so the user always sees something instead of silence.
        await self._reply_with_fallback(update, summary_text, reply_markup=keyboard)

    async def _handle_hud_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/hud — sends HUD, pins it, and stores the message ID for hourly auto-refresh."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        import httpx
        from shared.registry import get_agent_url

        # url is still needed below for the separate /hud/pin store POST
        # (a different endpoint/payload shape than the AgentRequest funnel).
        url = get_agent_url("market_intelligence")
        if not url:
            await update.message.reply_text("Market agent not available.")
            return

        # #hud parity fix (simplify GROUP 3, 2026-07-03): routing through the shared
        # helper restores the "Market agent not available." reply this site had
        # silently dropped (it fell back to "No response." for BOTH the unregistered
        # case and an empty result, losing the distinction).
        result = await self._post_market_task_or_reply(
            update, "/hud", update.effective_user.id, "No response."
        )
        if result is None:
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
        sent_msg = await self._reply_with_fallback(update, result, reply_markup=hud_keyboard)

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

    def _ideas_keyboard(self) -> InlineKeyboardMarkup:
        """Per-strategy drill-down grid for /ideas, built from _IDEAS_STRATEGIES so it
        can't drift from the callback task-map. Each taps to an edit-in-place deep-dive
        (callback ideas:<key>). Mirrors the /hud keyboard pattern."""
        btns = [InlineKeyboardButton(label, callback_data=f"ideas:{key}")
                for key, label, _task in self._IDEAS_STRATEGIES]
        # 3 per row
        rows = [btns[i:i + 3] for i in range(0, len(btns), 3)]
        return InlineKeyboardMarkup(rows)

    async def _handle_ideas_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/ideas — unified trade-ideas front door (substrate Stocks-in-Play + top NAMED
        ideas per strategy) with per-strategy drill-down buttons. On-demand (no pin)."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        result = await self._post_market_task_or_reply(
            update, "/ideas", update.effective_user.id, "No response."
        )
        if result is None:
            return

        await self._reply_with_fallback(update, result, reply_markup=self._ideas_keyboard())

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
            resp = client.messages.create(
                model=HEALTHCHECK_MODEL,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            try:  # #377 cost meter — additive, never alters the health verdict.
                # ORCHESTRATOR container: use core.spend (market-agent's
                # spend_tracker imports agents.market_intelligence.db, which is
                # NOT in the orchestrator image — that import would silently fail).
                from core.spend import log_api_usage
                _u = getattr(resp, "usage", None)
                if _u is not None:
                    await log_api_usage(
                        model=HEALTHCHECK_MODEL, caller="healthcheck",
                        input_tokens=getattr(_u, "input_tokens", 0) or 0,
                        output_tokens=getattr(_u, "output_tokens", 0) or 0,
                        stop_reason=getattr(resp, "stop_reason", None),
                    )
            except Exception:
                pass
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
        """Handle inline keyboard button presses (drill-downs)."""
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

        # trade_confirm:/trade_skip: branch REMOVED 2026-07-03 (#364/F17): the
        # staged-proposal buttons are gone — that branch imported broker code
        # DIRECTLY into this orchestrator process (execution-seam violation) and
        # wedged trades at 'confirmed' on the creds-less container. A stale
        # button press on an old message now just gets the answer() ack above.
        # themes:* branch REMOVED 2026-07-16 (#473): its only producer (the
        # /themes stage drill-down buttons) died in 393b980; a stale button
        # press on an old message falls through to the `else: pass` below.
        if callback_data.startswith(("eps:", "trades:")):
            await self._handle_drill_down_callback(query, callback_data)

        elif callback_data.startswith("hud:"):
            await self._handle_hud_drill_down(query, callback_data)

        elif callback_data.startswith("ideas:"):
            await self._handle_ideas_drill_down(query, callback_data)

        else:
            pass  # query already answered above

    # ── Inline keyboard drill-down callbacks ──────────────────────────────────

    async def _handle_drill_down_callback(self, query, callback_data: str) -> None:
        """Handle eps:/trades: drill-down button presses."""
        import httpx
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        url = get_agent_url("market_intelligence")
        if not url:
            await query.edit_message_text("Market agent not available.")
            return

        parts = callback_data.split(":", 2)
        prefix = parts[0]  # eps, trades

        # Determine the sub-command task to send to the market agent
        if prefix == "eps":
            tier = parts[1] if len(parts) > 1 else "HIGH"
            date_str = parts[2] if len(parts) > 2 else ""
            task = f"/eps_detail {tier} {date_str}".strip()
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

        # Split long sections (the Themes ecosystem board exceeds Telegram's
        # 4096-char limit, #473) — short results stay a single message.
        for chunk in self._split_message(result):
            try:
                await query.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
            except Exception as markdown_err:
                logger.warning(f"HUD drill-down markdown send failed, retrying plain: {markdown_err}")
                await query.message.reply_text(chunk)

    async def _handle_ideas_drill_down(self, query, callback_data: str) -> None:
        """ideas: drill-down — edit the SAME message in place into a strategy's board
        with a ← Ideas back button; ideas:summary re-renders the front door + restores
        the strategy keyboard. Mirrors _handle_drill_down_callback (edit + back), so the
        operator stays on one message instead of a growing stack."""
        import httpx
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        url = get_agent_url("market_intelligence")
        if not url:
            await query.edit_message_text("Market agent not available.")
            return

        key = callback_data.split(":", 1)[1]
        task_map = {key: task for key, _label, task in self._IDEAS_STRATEGIES}
        task_map["summary"] = "/ideas"
        task = task_map.get(key)
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
            logger.error(f"ideas drill-down ({key}) failed: {e}")
            result = f"Error: {e}"

        # summary restores the full strategy grid; a deep-dive carries ← Ideas back.
        if key == "summary":
            markup = self._ideas_keyboard()
        else:
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Ideas", callback_data="ideas:summary")]]
            )
        try:
            await query.edit_message_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
        except Exception as e:
            logger.warning(f"ideas edit_message_text failed, sending new: {e}")
            try:
                await query.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
            except Exception:
                await query.message.reply_text(result, reply_markup=markup)

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
                # Outside code block — escape HTML, then restore inline markup.
                escaped = html_mod.escape(part)
                # Bold: *text* → <b>text</b>
                escaped = re.sub(r"\*([^*]+)\*", r"<b>\1</b>", escaped)
                # Italic: _text_ → <i>text</i>.
                # ⚠ MISSING until 2026-08-02 — the operator saw raw underscores in Telegram.
                # ANY message containing ``` takes this HTML path (Markdown v1 cannot do code
                # blocks), so every `_italic_` in every digest rendered as literal underscores.
                # Not a crypto bug: it hit every fenced surface.
                # The lookarounds are load-bearing — they stop intra-word underscores
                # (`rs_overall`, `mcap_bucket`, `total_pnl`) from being eaten as italic markers,
                # which would swallow the text between two unrelated identifiers.
                escaped = re.sub(r"(?<![\w\\])_([^_\n]+)_(?!\w)", r"<i>\1</i>", escaped)
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
        # /ideas — unified trade-ideas front door (summary + per-strategy drill-down buttons)
        app.add_handler(CommandHandler("ideas", self._handle_ideas_command))
        # /ep (primary) + /eps (silent alias for back-compat) and /themes send summary + drill-down
        app.add_handler(CommandHandler("ep", self._handle_ep_command))
        app.add_handler(CommandHandler("eps", self._handle_ep_command))
        app.add_handler(CommandHandler("themes", self._handle_themes_command))
        # Other market-intelligence slash commands — bypass orchestrator LLM.
        # Kept as handlers so old pinned messages and muscle memory still work,
        # but removed from the bot menu to keep the command surface lean.
        for _cmd in ("9m", "clusters", "regime", "pregame", "audit", "crypto", "altseason", "parabolic",
                     "strategy", "watchlist", "wick", "why", "setup", "htf", "flags", "flag", "dryrun",
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
                     "review", "reviews", "spotted",
                     # 2026-06-16 #54 Prong B data-gated-review board
                     "datareviews",
                     # 2026-07-16 #378 cost board (variable LLM + flat subs vs budget)
                     "cost",
                     # 2026-06-16 #270 anticipation play board (SHADOW, Pradeep)
                     "anticipation",
                     # 2026-06-29 operator one-tap theme promotion (decision-alerts carry the action)
                     "promotetheme",
                     # 2026-06-19 #345 one-command real-money trading halt
                     "pause", "resume"):
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
        # AGGRESSIVE CULL 2026-07-20 (operator: "too confusing, remove as many as
        # possible, add back later"). Menu trimmed 33 → 11: safety + core-trade +
        # ONE front door (/hud). All the removed commands' HANDLERS still work if
        # typed (this only hides them from the / menu) — re-adding any is a one-line
        # BotCommand entry. Hidden-but-working: ideas, pregame, watch (/watch all =
        # the mi_stocks_in_play board, operator ruled it garbage), watchlist, setup,
        # themes, promotetheme, why(=setup dup), trade, htf, anticipation, detectors,
        # unknownrate, regime, sugarbabies, review, spotted, datareviews,
        # cost, missed, start(=help dup). RS accel / rotation-recovery move back into
        # the evening brief (#492), NOT a new command.
        commands = [
            BotCommand("hud",          "Snapshot: regime, EPs, 9M, themes — the one front door, drill-down buttons"),
            BotCommand("ep",           "EP alerts (MAGNA53 + 9M) — tap to drill down"),
            BotCommand("trades",       "Positions + P&L — tap to drill down"),
            BotCommand("strategy",     "Strategy registry — phases, KPIs, enable/disable/promote"),
            BotCommand("timestop",     "/timestop TICKER — confirm time-stop exit of 9M Day 2 meanderer"),
            BotCommand("partialnow",   "/partialnow TICKER — operator-confirm immediate partial exit (1/3 sell)"),
            BotCommand("syncnow",      "/syncnow [paper|live] — operator-confirm DB↔broker sync_positions"),
            BotCommand("pause",        "⏸️ HALT all new real-money entries (instant kill switch)"),
            BotCommand("resume",       "▶️ Resume real-money entries after /pause"),
            # #513 (operator-approved 2026-08-02). 32 commands were DISPATCHED but absent from
            # this list, so they worked only if you already knew to type them — the May-2026
            # invisible-command class at 5x the size. Curated, not exhaustive: a 40-item menu is
            # the same overwhelm #513 exists to fix. Aliases deduped (/flag, /reviews,
            # /sugarbaby, /trade). Continuation surfaces (/watch, /flags) deliberately EXCLUDED —
            # Continuation Flag is phase=deprecated, and it is a FAMILY not a setup (see the
            # SETUP vs FAMILY definition in CLAUDE.md). /positions excluded too: it maps to
            # _handle_watchlist, so its NAME lies — /trades is the real positions+P&L surface.
            BotCommand("crypto",       "Crypto RS — alt-season state + big/small-cap boards"),
            BotCommand("audit",        "/audit <topic> — full backward-check tables on demand"),
            BotCommand("why",          "/why TICKER — one day deep: detection → entry → exit"),
            BotCommand("setup",        "/setup TICKER — every detector hit, dated timeline"),
            BotCommand("regime",       "Market regime + breadth"),
            BotCommand("themes",       "Active themes — what is leading"),
            BotCommand("htf",          "Higher-timeframe setups"),
            BotCommand("status",       "System health + API spend"),
            BotCommand("help",         "Capabilities, rules, command reference"),
        ]
        await self._app.bot.set_my_commands(commands)
        logger.info("Bot commands registered with Telegram")
