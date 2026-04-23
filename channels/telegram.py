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


def _safe(s: str) -> str:
    """Strip Markdown special chars from dynamic/error strings."""
    return re.sub(r"[*_`\[\]]", "", s)


def _format_market_pipeline(status: dict) -> str:
    """Format the market pipeline section for /status."""
    import pytz
    from datetime import date, datetime as dt, timedelta

    REGIME_EMOJI = {"Bull": "🟢", "Choppy": "🟡", "Correcting": "🔴", "Crisis": "🚨", "Unknown": "⚫"}

    et = pytz.timezone("America/New_York")
    pt = pytz.timezone("America/Los_Angeles")
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
            f"*{assistant_name} — Quick Reference*\n"
            "\n"
            "*Market Intelligence*\n"
            "📊 `Send evening briefing` — RS leaders + theme scorecard + EPS flags\n"
            "☀️ `Send morning briefing` — pre-market + overnight news + EPs\n"
            "⚡ `Run theme engine` — refresh themes now (returns full scorecard)\n"
            "🔄 `Run data refresh` — full nightly pull (RS + regime + themes + fundamentals)\n"
            "\n"
            "Ask naturally:\n"
            '• "Any EPs today?" · "Market regime?"\n'
            '• "Top RS stocks" · "Active themes?"\n'
            '• "Score AXTI" · "Fundamentals on CIEN"\n'
            '• "Optical stocks near 20MA?"\n'
            '• "Screen RS > 70 with EPS growth > 25%"\n'
            "\n"
            "*History*\n"
            '🕐 "RS history CIEN, LITE, COHR" — weekly RS over 90 days\n'
            '📈 "When did metals/miners theme peak?"\n'
            '📉 "How has optical networking theme evolved?"\n'
            "\n"
            "*Teach & Update*\n"
            '📌 "AXTI is working, track it" — add stocks + seed themes\n'
            '📝 "GLW got a Meta deal for optical" — updates company description\n'
            '   _(Apollo recognizes business pivots and asks to confirm)_\n'
            "\n"
            "*Theme Management*\n"
            '🚫 `Exclude CAR from [exact theme name]` — permanently ban ticker from theme\n'
            '📋 `List exclusions` — show all active theme bans\n'
            '↩️ `Remove exclusion CAR from [theme name]` — undo a ban\n'
            "\n"
            "*Audit & Diagnostics*\n"
            '🔍 `Audit log` — last 20 engine events (48h)\n'
            '🤖 `Advisor log` — Opus advisor calls + full verdicts\n'
            '📅 `Show logs 7d` — extend window to 7 days\n'
            '   _Filter: "show logs advisor/discover/retired/excluded"_\n'
            "\n"
            "*Overnight Watchlist*\n"
            '🔔 `Show watchlist` — tracked instruments\n'
            '📌 `Track bitcoin with 5%` — add instrument\n'
            '❌ `Drop oil` — remove instrument\n'
            "\n"
            "*Other*\n"
            "💰 Portfolio · Quotes · TradingView alerts\n"
            "📅 Calendar · Events · Scheduling\n"
            "🔍 Web search · Summarization\n"
            "✈️ Travel · Flights · Hotels · Amex perks\n"
            "\n"
            "/agents · /status · /spend · /trades · /rules · /setup"
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
        "/hud", "/eps", "/9m", "/themes", "/clusters", "/regime", "/positions",
    }

    async def _dispatch_market_slash(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Generic handler for all market-intelligence slash commands."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return
        cmd_raw = (update.message.text or "").strip().split()[0]
        cmd = cmd_raw.split("@")[0].lower()  # strip @botname suffix if present

        import uuid, httpx
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        url = get_agent_url("market_intelligence")
        if not url:
            await update.message.reply_text("Market agent not available.")
            return

        req = AgentRequest(
            task=cmd,
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
            result = data.get("result") or data.get("error") or "No response."
        except Exception as e:
            logger.error(f"{cmd} failed: {e}")
            result = f"Error: {e}"

        await self._reply(update, result)

    async def _handle_eps_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/eps — compact summary with [View HIGH] [View MODERATE] drill-down buttons."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        import httpx
        from datetime import date
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        today_str = date.today().isoformat()
        url = get_agent_url("market_intelligence")
        if not url:
            await update.message.reply_text("Market agent not available.")
            return

        req = AgentRequest(
            task=f"/eps_detail SUMMARY {today_str}",
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
                summary_text = resp.json().get("result") or "No EP data."
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("View HIGH", callback_data=f"eps:HIGH:{today_str}"),
                InlineKeyboardButton("View MODERATE", callback_data=f"eps:MODERATE:{today_str}"),
            ]
        ])
        await update.message.reply_text(summary_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

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
        from datetime import date
        from shared.models import AgentRequest
        from shared.registry import get_agent_url

        today_str = date.today().isoformat()
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

        sent_msg = await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)

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
        (
            agent_health,
            market_status,
            (db_ok, db_err),
            (redis_ok, redis_err),
            (claude_ok, claude_err),
        ) = await asyncio.gather(
            health_check_all_agents(),
            get_market_pipeline_status(),
            self._check_db(),
            self._check_redis(),
            self._check_claude(),
        )

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

        # Market pipeline
        if market_status:
            lines.append("")
            lines.append(_format_market_pipeline(market_status))

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

    async def _handle_audit(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /audit command — show recent audit log entries."""
        if not update.effective_user or not self._is_allowed(update.effective_user.id):
            return

        await update.message.reply_text(
            "The /audit command has been retired.\n"
            "Use /trades for trading activity or check Docker logs for system events."
        )

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
            from datetime import date as _date
            today_str = _date.today().isoformat()
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
        app.add_handler(CommandHandler("spend", self._handle_spend))
        app.add_handler(CommandHandler("rules", self._handle_rules))
        app.add_handler(CommandHandler("trades", self._handle_trades_command))
        # /hud gets a specialized handler — it pins the message and stores the ID
        app.add_handler(CommandHandler("hud", self._handle_hud_command))
        # /eps and /themes send compact summary + drill-down buttons
        app.add_handler(CommandHandler("eps", self._handle_eps_command))
        app.add_handler(CommandHandler("themes", self._handle_themes_command))
        # All other market-intelligence slash commands — bypass orchestrator LLM
        for _cmd in ("9m", "clusters", "regime", "positions", "pregame"):
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
        commands = [
            BotCommand("hud",       "Status snapshot: regime, EPs, 9M, themes, clusters"),
            BotCommand("pregame",   "Trade shortlist: regime, hot themes, HIGH EPs, watchlist MAs"),
            BotCommand("eps",       "Today's EP alerts (MAGNA53) — tap to drill down"),
            BotCommand("9m",        "9M EP alerts and Day 2 sugar babies"),
            BotCommand("themes",    "Active theme summary — tap to drill down by stage"),
            BotCommand("clusters",  "Correlation clusters (beta-adjusted)"),
            BotCommand("regime",    "Current market regime and breadth"),
            BotCommand("positions", "Watchlist and tracked positions"),
            BotCommand("trades",    "Trade positions + P&L — tap to drill down"),
            BotCommand("status",    "System health, agents, market pipeline"),
            BotCommand("spend",     "API spend today & this month"),
            BotCommand("rules",     "EP trading rules (Qullamaggie v2)"),
            BotCommand("help",      "Capabilities & command reference"),
            BotCommand("setup",     "Change assistant name or personality"),
            BotCommand("start",     "Restart / re-introduce"),
        ]
        await self._app.bot.set_my_commands(commands)
        logger.info("Bot commands registered with Telegram")
