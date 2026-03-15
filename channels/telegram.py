"""
Telegram channel — receives messages from users and sends responses.
Uses python-telegram-bot in webhook mode (no polling).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.confirmations import parse_confirmation_reply, resolve_confirmation
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
        try:
            await self._app.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {user_id}: {e}")
            # Fallback: try without markdown
            try:
                plain = re.sub(r"[*_`\[\]()~>#+\-=|{}.!\\]", "", text)
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
        """Handle /setup — redo the name/persona setup."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return
        user_id = update.effective_user.id
        await self._clear_onboarding_state(user_id)
        await self._start_onboarding(update, user_id)

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
            f"*{assistant_name} — Capabilities & Commands*\n"
            "\n"
            "*💬 Just talk to me naturally* — I'll figure out what you need and route it to the right agent.\n"
            "\n"
            "*📈 Market Intelligence*\n"
            "• Evening briefing (5 PM PT) — regime + RS leaders + themes + MA pullbacks for EOD review\n"
            "• Morning briefing (6 AM PT) — EP recap + regime context, 30 min before open\n"
            "• EP alerts — HIGH EPs sent in real-time 4–6:30 AM PT (MAGNA53 scoring)\n"
            "• Market regime — Bull / Choppy / Correcting / Crisis with EP filter threshold\n"
            "• RS leaders — top momentum stocks ranked by 1M/3M/6M relative strength\n"
            "• Theme health — what sectors the market is rotating into right now\n"
            "• MA pullbacks — RS stocks testing 10/20/50 MA (potential entry points)\n"
            "• Score any ticker — 'Score AXTI' → instant RS rank vs today's universe\n"
            "• Teach me — tell me about stocks/themes you've spotted; I'll track them\n"
            "_Example: 'Send evening briefing' · 'Any EPs today?' · 'What's the market regime?'_\n"
            "_Example: 'Top RS stocks' · 'What themes are active?' · 'Optical stocks near 20MA?'_\n"
            "_Example: 'Score AXTI' · 'AXTI is working, it's a photonics play' → I'll add it_\n"
            "\n"
            "*📊 Finance*\n"
            "• View your IBKR portfolio, positions, P&L\n"
            "• Get stock quotes, fundamentals, chart data (via TradingView)\n"
            "• Run stock screeners\n"
            "• Receive real-time TradingView price alerts → pushed to this chat\n"
            "_Example: 'Show me my portfolio' · 'What's AAPL trading at?'_\n"
            "\n"
            "*📅 Calendar*\n"
            "• View upcoming events across Google Calendar & iCloud\n"
            "• Create, reschedule, or cancel events (requires your confirmation)\n"
            "• Get a morning briefing of today's schedule\n"
            "_Example: 'What's on my calendar this week?' · 'Schedule dentist Thursday 2pm'_\n"
            "\n"
            "*🔍 Research*\n"
            "• Web search with synthesized answers\n"
            "• Summarise articles, news, or topics\n"
            "_Example: 'Research the best S&P 500 ETFs' · 'Summarise the latest Fed meeting'_\n"
            "\n"
            "*✈️ Travel*\n"
            "• Flight & hotel research\n"
            "• Full trip itinerary planning\n"
            "• Amex Platinum perks optimiser — FHR hotels, lounge access, which card to use\n"
            "_Example: 'Plan 5 days in Tokyo in October' · 'Which lounge can I use at JFK?'_\n"
            "\n"
            "*🌐 Browser*\n"
            "• Automate any website interaction\n"
            "_Example: 'Extract the pricing table from [url]'_\n"
            "\n"
            "━━━━━━━━━━━━━━━━\n"
            "*Commands*\n"
            "/help — this message\n"
            "/agents — live status of all sub-agents\n"
            "/setup — change my name or personality\n"
            "/memory — view what I remember about you\n"
            "/audit — recent action log\n"
            "/status — system health check\n"
            "/start — restart"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _handle_agents(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /agents — show each agent's role and live health."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        from core.router import health_check_all_agents
        health = await health_check_all_agents()

        agent_descriptions = {
            "market_intelligence": "📈 RS leaders, EP alerts, regime, themes",
            "finance":  "📊 Portfolio, quotes, TradingView alerts",
            "calendar": "📅 Google Calendar & iCloud events",
            "research": "🔍 Web search & summarisation",
            "browser":  "🌐 Playwright browser automation",
            "travel":   "✈️ Flights, hotels, Amex Platinum perks",
        }

        lines = ["*Sub-Agents*\n"]
        # Only show agents that are enabled (present in health dict)
        for agent_name, (is_healthy, _reason) in health.items():
            description = agent_descriptions.get(agent_name, "")
            display = agent_name.replace("_", " ").title()
            icon = "🟢" if is_healthy else "🔴"
            lines.append(f"{icon} *{display}* — {description}")

        if not health:
            lines.append("_No agents enabled_")

        lines.append("\n🟢 online  🔴 offline/unreachable")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _handle_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status — system-level health (DB, Redis, agents)."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        from core.router import health_check_all_agents
        agent_health = await health_check_all_agents()

        # Check DB + Redis + Claude API
        db_ok, db_err = await self._check_db()
        redis_ok, redis_err = await self._check_redis()
        claude_ok, claude_err = await self._check_claude()

        def _safe(s: str) -> str:
            """Strip Markdown special chars from dynamic/error strings."""
            return re.sub(r"[*_`\[\]]", "", s)

        lines = ["*System Status*\n"]

        # Infrastructure
        lines.append("*Infrastructure*")
        lines.append(f"{'🟢' if db_ok else '🔴'} PostgreSQL — {'storing memories & audit log' if db_ok else f'down: {_safe(db_err)} — is Docker running?'}")
        lines.append(f"{'🟢' if redis_ok else '🔴'} Redis — {'caching & confirmations' if redis_ok else f'down: {_safe(redis_err)} — is Docker running?'}")
        lines.append(f"{'🟢' if claude_ok else '🔴'} Claude API — {'responding' if claude_ok else _safe(claude_err)}")

        # Agents
        lines.append("\n*Agents*")
        agent_hints = {
            "finance": "start with: uvicorn agents.finance.agent:app --port 8001",
            "calendar": "start with: uvicorn agents.calendar.agent:app --port 8002",
            "research": "start with: uvicorn agents.research.agent:app --port 8003",
            "browser": "start with: uvicorn agents.browser.agent:app --port 8004",
            "travel": "start with: uvicorn agents.travel.agent:app --port 8005",
        }
        for agent_name, (is_healthy, reason) in agent_health.items():
            display = agent_name.replace("_", " ").title()
            if is_healthy:
                lines.append(f"🟢 {display} Agent — running")
            else:
                hint = agent_hints.get(agent_name, "")
                lines.append(f"🔴 {display} Agent — {_safe(reason)}" + (f"\n    {hint}" if hint else ""))

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
                model="claude-haiku-4-5-20251001",
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

    async def _handle_memory(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /memory command — show stored memories."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

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

    async def _handle_audit(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /audit command — show recent audit log entries."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        user_id = update.effective_user.id
        from shared.audit import read_audit_log
        entries = read_audit_log(limit=10, user_id=user_id)

        if not entries:
            await update.message.reply_text("No audit log entries yet.")
            return

        lines = ["**Recent actions**\n"]
        for e in entries:
            ts = e.timestamp.strftime("%m/%d %H:%M")
            confirmed = " ✅" if e.confirmed_by_user else ""
            lines.append(f"`{ts}` [{e.agent.value}] {e.action}{confirmed}")

        await update.message.reply_text("\n".join(lines))

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
        """Send a reply, falling back to plain text if Markdown fails."""
        try:
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            # Markdown parse error — strip formatting and retry
            try:
                plain = re.sub(r"[*_`\[\]()~>#+\-=|{}.!\\]", "", text)
                await update.message.reply_text(plain)
            except Exception as e:
                logger.error(f"Failed to send reply: {e}")

    async def _send_typing_indicator(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Periodically send 'typing...' indicator while processing."""
        while True:
            try:
                await update.message.chat.send_action("typing")
                await asyncio.sleep(TYPING_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    # ── Application setup ─────────────────────────────────────────────────────

    def build_application(self) -> Application:
        """Build and configure the python-telegram-bot Application."""
        app = (
            Application.builder()
            .token(self._secrets.telegram_bot_token)
            .build()
        )

        app.add_handler(CommandHandler("start", self._handle_start))
        app.add_handler(CommandHandler("help", self._handle_help))
        app.add_handler(CommandHandler("agents", self._handle_agents))
        app.add_handler(CommandHandler("setup", self._handle_setup))
        app.add_handler(CommandHandler("status", self._handle_status))
        app.add_handler(CommandHandler("memory", self._handle_memory))
        app.add_handler(CommandHandler("audit", self._handle_audit))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        self._app = app
        return app

    async def set_webhook(self, webhook_url: str) -> None:
        """Register the webhook URL with Telegram and set the bot command menu."""
        if self._app is None:
            raise RuntimeError("Application not built yet. Call build_application() first.")
        await self._app.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message"],
        )
        await self._register_commands()
        logger.info(f"Telegram webhook set to: {webhook_url}")

    async def _register_commands(self) -> None:
        """Register bot commands with BotFather so they appear in the / menu."""
        from telegram import BotCommand
        commands = [
            BotCommand("help",   "Capabilities & command reference"),
            BotCommand("agents", "Live status of all sub-agents"),
            BotCommand("status", "System health (DB, Redis, agents)"),
            BotCommand("setup",  "Change assistant name or personality"),
            BotCommand("memory", "View what I remember about you"),
            BotCommand("audit",  "Recent action log"),
            BotCommand("start",  "Restart / re-introduce"),
        ]
        await self._app.bot.set_my_commands(commands)
        logger.info("Bot commands registered with Telegram")
