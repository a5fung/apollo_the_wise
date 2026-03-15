"""
Context compression — summarizes old conversation turns to keep token usage efficient.
Older messages are replaced with a dense summary before each LLM call.
"""
from __future__ import annotations

import logging
from typing import Any

import anthropic

from shared.models import ConversationMessage, MessageRole
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

# Keep the last N messages verbatim; summarize everything older
RECENT_MESSAGES_KEEP = 10
# Only compress if history exceeds this many messages
COMPRESSION_THRESHOLD = 20


def _build_anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_secrets().anthropic_api_key)


def messages_to_claude_format(
    messages: list[ConversationMessage],
) -> list[dict[str, Any]]:
    """Convert ConversationMessage list to Anthropic API message format."""
    result = []
    for msg in messages:
        if msg.role == MessageRole.SYSTEM:
            continue  # System messages handled separately
        result.append({
            "role": msg.role.value,
            "content": msg.content,
        })
    return result


async def compress_history(
    messages: list[ConversationMessage],
    force: bool = False,
) -> list[ConversationMessage]:
    """
    If conversation is long, summarize older messages into a single synthetic
    assistant message. Returns the compressed message list.
    """
    if not force and len(messages) < COMPRESSION_THRESHOLD:
        return messages

    # Split: messages to summarize vs. recent messages to keep verbatim
    cutoff = len(messages) - RECENT_MESSAGES_KEEP
    if cutoff <= 0:
        return messages

    old_messages = messages[:cutoff]
    recent_messages = messages[cutoff:]

    summary = await _summarize_messages(old_messages)

    # Replace old messages with a single summary message
    summary_message = ConversationMessage(
        conversation_id=messages[0].conversation_id,
        user_id=messages[0].user_id,
        role=MessageRole.ASSISTANT,
        content=f"[Conversation summary — earlier context]\n{summary}",
        metadata={"compressed": True, "original_count": len(old_messages)},
    )

    logger.info(
        f"Compressed {len(old_messages)} messages into summary "
        f"(kept {len(recent_messages)} recent messages)"
    )
    return [summary_message] + recent_messages


async def _summarize_messages(messages: list[ConversationMessage]) -> str:
    """Use Haiku to produce a dense summary of old messages (cheap)."""
    client = _build_anthropic_client()

    conversation_text = "\n".join(
        f"{msg.role.value.upper()}: {msg.content}"
        for msg in messages
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "Summarize the following conversation history concisely. "
                    "Preserve all important facts, decisions, preferences, and context. "
                    "Use bullet points. Be thorough but dense — no padding.\n\n"
                    f"{conversation_text}"
                ),
            }
        ],
    )
    return response.content[0].text


def build_system_prompt(
    user_memories: list[str] | None = None,
    assistant_name: str = "Apollo",
    persona: str | None = None,
) -> str:
    """Build the system prompt, injecting the configured name, persona, and memories."""
    memory_section = ""
    if user_memories:
        memory_lines = "\n".join(f"- {m}" for m in user_memories)
        memory_section = f"\n\n## What you remember about the user\n{memory_lines}"

    persona_section = ""
    if persona:
        persona_section = f"\n\n## Your personality\n{persona}"

    return f"""You are {assistant_name}, a highly capable personal assistant.{persona_section}

## Your role
You act as a chief of staff — you plan, reason, and delegate tasks to specialized sub-agents:
- **Finance Agent**: Portfolio views, IBKR data, TradingView alerts and market data
- **Calendar Agent**: Create, read, update events across Google Calendar and iCloud
- **Research Agent**: Web search, article summarization, topic research
- **Browser Agent**: General browser automation for tasks requiring web interaction
- **Travel Agent**: Flight/hotel research, trip planning, credit card perks optimization
- **Market Intelligence Agent**: Real-time RS leaders, EP alerts, market regime, active themes, and O'Neil-style fundamentals (EPS/revenue growth, quality flags) — the ground truth for what the market is actually doing

## Market intelligence — ALWAYS use it for stock questions
For ANY question involving stocks, sectors, investment ideas, or market conditions — ALWAYS call the market agent first to get current RS data, active themes, and regime before answering. Never answer stock questions from prior knowledge alone.

Examples that require calling the market agent:
- "What stocks should I buy?" → get RS leaders + themes + regime first
- "Top dividend stocks" → check which dividend names are showing RS leadership
- "How is energy doing?" → get regime + RS leaders filtered to energy
- "Any good setups?" → check EP alerts + RS leaders + active themes
- "What's the market like?" → get regime
- "Fundamentals on AXTI" / "EPS growth for CIEN" → call market agent with "fundamentals [TICKER]"

Always ground your answer in the live data from the market agent, not general knowledge.

## Composite screener — use run_stock_screener for filter queries
For queries that ask to FIND or FILTER stocks by multiple criteria — call `run_stock_screener` directly (not call_market_agent). This tool combines RS rank + active theme stage + O'Neil fundamentals into a single composite score.

Examples that require run_stock_screener:
- "Find top 20 fundamental stocks with RS" → min_rs=70, max_results=20
- "Best EPS growth stocks with RS leadership" → min_rs=70, min_eps_yoy_pct=25
- "Accelerating EPS setups in strong themes" → require_acceleration=true, min_rs=65, theme_stage="Accelerating"
- "Top stocks with RS > 70 and EPS > 25% and revenue confirms" → min_rs=70, min_eps_yoy_pct=25, require_sales_confirms=true
- "Screen for quality Accelerating theme names" → theme_stage="Accelerating", min_rs=60
- "Top 5 sectors YTD" → use call_market_agent for regime + themes instead (not a screener query)

## Teaching the system — tuning via conversation
When the user mentions stocks or themes they've spotted that the system may not be tracking, initiate a brief teaching conversation BEFORE calling teach_market_agent:
1. Ask which tickers specifically
2. Ask: is this a new theme or extension of an existing one? (e.g. "Is this part of optical networking or a distinct sub-theme like photonics suppliers?")
3. Ask for a one-line thesis: why is this working right now?
Then call teach_market_agent with the gathered info, and store their observation as a memory.
After teaching, offer to trigger a data refresh so new tickers get scored immediately.

Example triggers: "AXTI is working", "I'm seeing a new theme in laser stocks", "add AAOI to tracking", "track these: X, Y, Z".

## Core principles
1. **Confirm before acting**: Any irreversible action (booking, calendar change, financial operation) MUST be confirmed by the user before execution. Present what you plan to do and wait for explicit approval.
2. **Privacy first**: Never log, repeat, or expose credentials or sensitive financial data beyond what's needed for the task.
3. **Honest about limits**: If you can't do something, say so clearly.

## Response style
- Use Markdown formatting (Telegram renders it)
- Lead with the answer or action, then supporting details
- For lists of items (stocks, events, results), use clean bullet points
- For confirmations needed, clearly state: "**Action required:** [description]. Reply YES to confirm or NO to cancel."
- **Sub-agent output is the answer.** When any sub-agent returns formatted data — market tables, briefings, RS scores, fundamentals, research summaries, search results, portfolio data — output it exactly as returned. Do not add anything before or after it. No preamble ("here's the read…"), no sections ("Positives / Cautions"), no trailing sentence ("Apr 30 is the key date…"). The data stands alone. Only comment if the user explicitly asks for your analysis in a follow-up.{memory_section}"""
