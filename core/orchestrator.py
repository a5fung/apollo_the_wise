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
from core.router import auth_headers, call_agent, get_orchestrator_tools
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
MAX_TOOL_ITERATIONS = 20

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
        self._client = anthropic.AsyncAnthropic(api_key=get_secrets().anthropic_api_key)
        self._send_message = send_message_fn
        self._tools = get_orchestrator_tools()
        self._cached_tools: list[dict[str, Any]] | None = None

    def _tools_with_cache_control(self) -> list[dict[str, Any]]:
        """Return tools list with cache_control on the last tool.

        Placing the breakpoint on the final tool means the entire
        prefix (system prompt + all tool definitions) is covered by
        a single cache entry.  Built once and reused.
        """
        if self._cached_tools is None:
            import copy
            tools = copy.deepcopy(self._tools)
            if tools:
                tools[-1]["cache_control"] = {"type": "ephemeral"}
            self._cached_tools = tools
        return self._cached_tools

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

            try:
                # Prompt caching: system prompt + tools are static per
                # conversation and cacheable.  The last tool gets the
                # cache_control breakpoint so the entire prefix
                # (system + all tools) is cached together.
                cached_tools = self._tools_with_cache_control()
                response = await asyncio.wait_for(
                    self._client.messages.create(
                        model=ORCHESTRATOR_MODEL,
                        max_tokens=4096,
                        system=[{
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }],
                        tools=cached_tools,
                        messages=current_messages,
                    ),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                logger.error(f"Claude API timed out after 60s for user {user_id}")
                return "Sorry, I timed out waiting for a response. Please try again."

            # Log token usage for spend tracking
            try:
                from core.spend import log_api_usage
                usage = response.usage
                await log_api_usage(
                    model=ORCHESTRATOR_MODEL,
                    caller="orchestrator",
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                )
            except Exception as e:
                # WARNING not DEBUG — this hid the May 2026 spend-logger
                # outage for ~12 days. Per feedback_silent_failures, any
                # observability gap must surface at WARNING+ so future
                # regressions are visible without manual inspection.
                logger.warning(f"Spend tracking failed: {e}")

            # If Claude wants to use tools
            if response.stop_reason == "tool_use":
                # Add Claude's response to message history
                current_messages.append({
                    "role": "assistant",
                    "content": response.content,
                })

                # Process tool calls concurrently
                tool_blocks = [b for b in response.content if b.type == "tool_use"]
                tool_results = list(await asyncio.gather(*[
                    self._handle_tool_call(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        tool_name=block.name,
                        tool_input=block.input,
                        tool_use_id=block.id,
                    )
                    for block in tool_blocks
                ]))

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
            "call_market_agent": AgentName.MARKET_INTELLIGENCE,
        }

        if tool_name == "tweet_message":
            return await self._post_tweet(tool_input)

        if tool_name == "run_stock_screener":
            return await self._run_stock_screener(tool_input)

        if tool_name == "teach_market_agent":
            return await self._teach_market_agent(
                user_id=user_id,
                conversation_id=conversation_id,
                tool_input=tool_input,
            )

        if tool_name == "update_stock_info":
            return await self._update_stock_info(tool_input)

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

    async def _call_market_endpoint(
        self,
        endpoint: str,
        payload: dict[str, Any],
        timeout: int = 30,
        error_prefix: str = "Market agent error",
    ) -> dict[str, Any]:
        """Shared HTTP POST to the market intelligence agent. Raises on failure."""
        from shared.registry import get_agent_url

        url = get_agent_url(AgentName.MARKET_INTELLIGENCE.value)
        if not url:
            raise RuntimeError("Market Intelligence Agent is not running.")

        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{url}{endpoint}",
                json=payload,
                headers=auth_headers(),
            )
            r.raise_for_status()
            return r.json()

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
        tickers = tool_input.get("tickers", [])
        override = tool_input.get("override", False)

        # ── Anti-FOMO gatekeeper ──────────────────────────────────────────────
        if tickers and not override:
            warning = await self._check_extension_warning(tickers)
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
            data = await self._call_market_endpoint("/teach", payload)
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

    async def _check_extension_warning(self, tickers: list[str]) -> str | None:
        """
        Check if any tickers are extended >15% above 20MA in a risky regime.
        Returns a warning string if so, or None if all clear.
        """
        EXTENSION_THRESHOLD = 15.0  # % above 20MA

        try:
            data = await self._call_market_endpoint(
                "/stocks/extension", {"tickers": tickers}, timeout=10,
            )
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

    async def _run_stock_screener(self, tool_input: dict[str, Any]) -> str:
        """Call /screener on the market agent with structured filter params."""
        payload = {
            "min_rs": tool_input.get("min_rs", 60.0),
            "min_eps_yoy_pct": tool_input.get("min_eps_yoy_pct"),
            "min_rev_yoy_pct": tool_input.get("min_rev_yoy_pct"),
            "require_acceleration": tool_input.get("require_acceleration", False),
            "require_sales_confirms": tool_input.get("require_sales_confirms", False),
            "theme_stage": tool_input.get("theme_stage"),
            "max_results": min(int(tool_input.get("max_results", 20)), 50),
        }

        try:
            data = await self._call_market_endpoint("/screener", payload, timeout=90)
        except Exception as e:
            return f"Screener failed: {e}"

        return data.get("result", "No screener results returned.")

    async def _update_stock_info(self, tool_input: dict[str, Any]) -> str:
        """Call /stocks/update_info on the market agent to override a ticker description."""
        payload = {
            "ticker": tool_input.get("ticker", ""),
            "description": tool_input.get("description", ""),
            "notes": tool_input.get("notes", ""),
        }

        try:
            data = await self._call_market_endpoint("/stocks/update_info", payload)
        except Exception as e:
            return f"Failed to update stock info: {e}"

        ticker = data.get("ticker", tool_input.get("ticker", "?"))
        desc = data.get("description", "")
        return (
            f"Updated {ticker}'s description to: \"{desc}\"\n"
            f"The theme engine will now use this description for clustering. "
            f"This change is permanent until overridden again."
        )

    async def _post_tweet(self, tool_input: dict[str, Any]) -> str:
        """Post a custom tweet via the market agent's /tweet endpoint."""
        text = tool_input.get("text", "")
        if not text:
            return "No tweet text provided."

        try:
            data = await self._call_market_endpoint("/tweet", {"text": text})
        except Exception as e:
            return f"Tweet failed: {e}"

        if data.get("success"):
            tweet_ids = data.get("tweet_ids", [])
            count = len(tweet_ids)
            return f"Tweet posted successfully ({count} tweet{'s' if count > 1 else ''}). https://x.com/Apollo_Trends/status/{tweet_ids[0]}"
        return f"Tweet failed: {data.get('error', 'unknown error')}"

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
