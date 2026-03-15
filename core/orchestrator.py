"""
Apollo Orchestrator — the main brain.

Uses Claude's tool-use loop to:
1. Understand user intent
2. Route to appropriate sub-agents
3. Synthesize results
4. Gate irreversible actions behind confirmation
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, Optional

import anthropic
import httpx

from core.confirmations import request_confirmation
from core.context import build_system_prompt, compress_history, messages_to_claude_format
from core.memory import (
    get_recent_messages,
    save_memory,
    save_message,
    search_memories,
)
from core.router import call_agent, get_orchestrator_tools
from shared.audit import log_action
from shared.models import (
    AgentName,
    AgentRequest,
    ConversationMessage,
    MemoryEntry,
    MessageRole,
)
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

# Max Claude iterations per user message (prevents infinite loops)
MAX_TOOL_ITERATIONS = 10

# Regimes where extension risk is elevated (used by Anti-FOMO gatekeeper)
RISKY_REGIMES = {"Choppy", "Correcting", "Crisis"}

# Which model to use for the main orchestrator
ORCHESTRATOR_MODEL = "claude-sonnet-4-6"


class Apollo:
    """
    Apollo orchestrator instance.
    One instance per application; handles messages from multiple users.
    """

    def __init__(self, send_message_fn: Callable[[int, str], Any]) -> None:
        """
        Args:
            send_message_fn: Async function (user_id, text) -> None
                             Used to send Telegram messages (confirmations, etc.)
        """
        self._client = anthropic.Anthropic(api_key=get_secrets().anthropic_api_key)
        self._send_message = send_message_fn
        self._tools = get_orchestrator_tools()

    async def handle_message(
        self,
        user_id: int,
        text: str,
        conversation_id: Optional[str] = None,
    ) -> str:
        """
        Process a user message and return Apollo's response.

        Args:
            user_id: Telegram user ID
            text: User's message text
            conversation_id: Stable ID for this conversation thread

        Returns:
            Apollo's response as a string (Markdown)
        """
        if conversation_id is None:
            conversation_id = str(user_id)  # Default: one conversation per user

        # Save user message to DB
        user_msg = ConversationMessage(
            conversation_id=conversation_id,
            user_id=user_id,
            role=MessageRole.USER,
            content=text,
        )
        await save_message(user_msg)

        # Load conversation history
        history = await get_recent_messages(user_id, limit=50)

        # Compress if needed
        history = await compress_history(history)

        # Load relevant long-term memories
        memories = await search_memories(user_id, limit=10)

        # Extract persona settings (name + personality) from memories
        assistant_name = "Apollo"
        persona = None
        general_memories: list[str] = []
        for m in memories:
            if m.category == "persona:name":
                assistant_name = m.content
            elif m.category == "persona:personality":
                persona = m.content
            else:
                general_memories.append(m.content)

        # Build system prompt with persona + memories injected
        system_prompt = build_system_prompt(
            user_memories=general_memories,
            assistant_name=assistant_name,
            persona=persona,
        )

        # Format messages for Claude
        claude_messages = messages_to_claude_format(history)

        # Ensure the current message is included (it may already be if just saved)
        if not claude_messages or claude_messages[-1].get("content") != text:
            claude_messages.append({"role": "user", "content": text})

        # Run the tool-use loop
        response_text = await self._tool_use_loop(
            user_id=user_id,
            conversation_id=conversation_id,
            system_prompt=system_prompt,
            messages=claude_messages,
        )

        # Save assistant response to DB
        assistant_msg = ConversationMessage(
            conversation_id=conversation_id,
            user_id=user_id,
            role=MessageRole.ASSISTANT,
            content=response_text,
            agent=AgentName.ORCHESTRATOR,
        )
        await save_message(assistant_msg)

        return response_text

    async def _tool_use_loop(
        self,
        user_id: int,
        conversation_id: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> str:
        """
        Run the Claude tool-use loop until a final text response is produced
        or MAX_TOOL_ITERATIONS is reached.
        """
        current_messages = list(messages)
        iteration = 0

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1
            logger.debug(f"Tool loop iteration {iteration} for user {user_id}")

            response = self._client.messages.create(
                model=ORCHESTRATOR_MODEL,
                max_tokens=4096,
                system=system_prompt,
                tools=self._tools,
                messages=current_messages,
            )

            # If Claude wants to use tools
            if response.stop_reason == "tool_use":
                # Add Claude's response to message history
                current_messages.append({
                    "role": "assistant",
                    "content": response.content,
                })

                # Process each tool call
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool_result = await self._handle_tool_call(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        tool_name=block.name,
                        tool_input=block.input,
                        tool_use_id=block.id,
                    )
                    tool_results.append(tool_result)

                # Add tool results to message history
                current_messages.append({
                    "role": "user",
                    "content": tool_results,
                })

            elif response.stop_reason == "end_turn":
                # Claude produced a final text response
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(text_blocks) if text_blocks else "(no response)"

            else:
                logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
                break

        return "I hit my reasoning limit for this request. Please try rephrasing or breaking it into smaller steps."

    async def _handle_tool_call(
        self,
        user_id: int,
        conversation_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
    ) -> dict[str, Any]:
        """Execute a tool call and return the result in Anthropic's tool_result format."""
        logger.info(f"Tool call: {tool_name} for user {user_id}")

        try:
            result = await self._dispatch_tool(
                user_id=user_id,
                conversation_id=conversation_id,
                tool_name=tool_name,
                tool_input=tool_input,
            )
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result,
            }
        except Exception as e:
            logger.exception(f"Tool {tool_name} raised exception")
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": f"Error executing {tool_name}: {e}",
                "is_error": True,
            }

    async def _dispatch_tool(
        self,
        user_id: int,
        conversation_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> str:
        """Map tool name to its handler."""
        agent_tool_map = {
            "call_finance_agent": AgentName.FINANCE,
            "call_calendar_agent": AgentName.CALENDAR,
            "call_research_agent": AgentName.RESEARCH,
            "call_browser_agent": AgentName.BROWSER,
            "call_travel_agent": AgentName.TRAVEL,
            "call_market_agent": AgentName.MARKET_INTELLIGENCE,
        }

        if tool_name == "teach_market_agent":
            return await self._teach_market_agent(
                user_id=user_id,
                conversation_id=conversation_id,
                tool_input=tool_input,
            )

        if tool_name in agent_tool_map:
            agent_name = agent_tool_map[tool_name]
            return await self._call_sub_agent(
                agent=agent_name,
                user_id=user_id,
                conversation_id=conversation_id,
                task=tool_input.get("task", ""),
                context=tool_input.get("context", {}),
            )

        if tool_name == "store_memory":
            return await self._store_memory(
                user_id=user_id,
                category=tool_input.get("category", "fact"),
                content=tool_input.get("content", ""),
            )

        return f"Unknown tool: {tool_name}"

    async def _call_sub_agent(
        self,
        agent: AgentName,
        user_id: int,
        conversation_id: str,
        task: str,
        context: dict[str, Any],
    ) -> str:
        """Call a sub-agent via the router and return its result as a string."""
        request = AgentRequest(
            task=task,
            context=context,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        await log_action(
            user_id=user_id,
            agent=AgentName.ORCHESTRATOR,
            action=f"delegate_to_{agent.value}",
            details={"task": task[:200], "context_keys": list(context.keys())},
        )

        response = await call_agent(agent, request)

        if not response.success:
            return f"The {agent.value} agent encountered an error: {response.error}"

        # If agent requires confirmation before completing action
        if response.requires_confirmation and response.confirmation_id:
            # The confirmation was already set up by the sub-agent
            # We just need to report the current status
            return (
                f"{response.result or ''}\n\n"
                f"⚠️ This action requires your confirmation. "
                f"Please reply YES to confirm or NO to cancel."
            )

        return response.result or f"Task completed by {agent.value} agent."

    async def _teach_market_agent(
        self,
        user_id: int,
        conversation_id: str,
        tool_input: dict[str, Any],
    ) -> str:
        """
        Call /teach on the market agent, then optionally store an observation as memory.
        Checks for extended stocks before teaching — warns if any ticker is >15% above
        its 20MA in a non-Bull regime. The user can override by confirming.
        """
        from shared.registry import get_agent_url

        url = get_agent_url(AgentName.MARKET_INTELLIGENCE.value)
        if not url:
            return "Market Intelligence Agent is not running."

        tickers = tool_input.get("tickers", [])
        override = tool_input.get("override", False)

        # ── Anti-FOMO gatekeeper ──────────────────────────────────────────────
        if tickers and not override:
            warning = await self._check_extension_warning(tickers, url)
            if warning:
                return warning  # Returns to Claude, which presents it to the user
        # ─────────────────────────────────────────────────────────────────────

        payload = {
            "tickers": tickers,
            "theme_name": tool_input.get("theme_name", ""),
            "theme_thesis": tool_input.get("theme_thesis", ""),
            "observation": tool_input.get("observation", ""),
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{url}/teach",
                    json=payload,
                    headers={"X-Apollo-Secret": get_secrets().internal_api_secret},
                )
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            return f"Failed to reach market agent: {e}"

        observation = tool_input.get("observation", "")
        if observation:
            entry = MemoryEntry(
                user_id=user_id,
                category="market_observation",
                content=observation,
            )
            await save_memory(entry)

        await log_action(
            user_id=user_id,
            agent=AgentName.ORCHESTRATOR,
            action="teach_market_agent",
            details={"tickers": payload["tickers"], "theme": payload["theme_name"]},
        )

        parts = [v for v in [data.get("tracked"), data.get("theme")] if v]
        return "\n".join(parts) if parts else "Done."

    async def _check_extension_warning(self, tickers: list[str], market_url: str) -> str | None:
        """
        Check if any tickers are extended >15% above 20MA in a risky regime.
        Returns a warning string if so, or None if all clear.
        """
        EXTENSION_THRESHOLD = 15.0  # % above 20MA

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{market_url}/stocks/extension",
                    json={"tickers": tickers},
                    headers={"X-Apollo-Secret": get_secrets().internal_api_secret},
                )
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            logger.warning(f"Extension check failed (skipping gatekeeper): {e}")
            return None  # Fail open — don't block the teach if check itself fails

        regime = data.get("regime", "Unknown")
        extensions = data.get("extensions", [])

        extended = [
            e for e in extensions
            if e.get("extension_pct") is not None and e["extension_pct"] > EXTENSION_THRESHOLD
        ]

        if not extended:
            return None  # All clear

        # Format warning
        lines = []
        for e in extended:
            lines.append(
                f"• `{e['ticker']}` is *{e['extension_pct']:+.1f}%* above its 20MA "
                f"(close {e.get('close', 0):.2f}, 20MA {e.get('sma_20', 0):.2f})"
            )

        regime_note = (
            f"Current regime is *{regime}* — the bar for new entries is higher."
            if regime in RISKY_REGIMES
            else f"Current regime is *{regime}* — extended entries carry more pullback risk."
        )

        warning = (
            f"⚠️ *Extension warning* before tracking:\n\n"
            + "\n".join(lines)
            + f"\n\n{regime_note}\n\n"
            + "_Still want to add to tracking? Reply yes and I'll proceed._"
        )
        return warning

    async def _store_memory(
        self,
        user_id: int,
        category: str,
        content: str,
    ) -> str:
        """Store a long-term memory entry."""
        entry = MemoryEntry(
            user_id=user_id,
            category=category,
            content=content,
        )
        await save_memory(entry)
        logger.info(f"Stored memory for user {user_id}: [{category}] {content[:60]}")
        return f"Memory stored: [{category}] {content}"
