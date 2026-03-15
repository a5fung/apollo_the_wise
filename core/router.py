"""
Task router — determines which sub-agent(s) should handle a given request.
Apollo calls this to route tasks; the router calls sub-agent HTTP APIs.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from shared.models import AgentName, AgentRequest, AgentResponse
from shared.registry import get_agent_url
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

# Timeout for sub-agent calls (seconds)
AGENT_TIMEOUT = 120


def _auth_headers() -> dict[str, str]:
    return {"X-Apollo-Secret": get_secrets().internal_api_secret}


async def call_agent(
    agent: AgentName,
    request: AgentRequest,
) -> AgentResponse:
    """
    Send a task to a sub-agent via its internal HTTP API.
    Returns an AgentResponse (success or error).
    """
    url = get_agent_url(agent.value)
    if not url:
        return AgentResponse(
            request_id=request.request_id,
            agent=agent,
            success=False,
            error=f"Agent '{agent.value}' is not enabled or configured.",
        )

    endpoint = f"{url}/task"
    logger.info(f"Routing task to {agent.value}: {request.task[:80]}...")

    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            response = await client.post(
                endpoint,
                json=request.model_dump(),
                headers=_auth_headers(),
            )
            response.raise_for_status()
            return AgentResponse(**response.json())
    except httpx.TimeoutException:
        logger.error(f"Agent {agent.value} timed out after {AGENT_TIMEOUT}s")
        return AgentResponse(
            request_id=request.request_id,
            agent=agent,
            success=False,
            error=f"Agent timed out after {AGENT_TIMEOUT}s.",
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"Agent {agent.value} returned HTTP {e.response.status_code}")
        return AgentResponse(
            request_id=request.request_id,
            agent=agent,
            success=False,
            error=f"Agent returned HTTP {e.response.status_code}: {e.response.text[:200]}",
        )
    except Exception as e:
        logger.exception(f"Unexpected error calling {agent.value}")
        return AgentResponse(
            request_id=request.request_id,
            agent=agent,
            success=False,
            error=str(e),
        )


async def health_check_all_agents() -> dict[str, tuple[bool, str]]:
    """Ping all configured agents and return (is_healthy, reason) for each."""
    from shared.registry import get_active_agents

    results: dict[str, tuple[bool, str]] = {}
    for agent_name in get_active_agents():
        url = get_agent_url(agent_name)
        if not url:
            results[agent_name] = (False, "Not configured in integrations.yaml")
            continue
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{url}/health", headers=_auth_headers())
                if r.status_code == 200:
                    results[agent_name] = (True, "")
                else:
                    results[agent_name] = (False, f"HTTP {r.status_code}")
        except httpx.ConnectError:
            results[agent_name] = (False, f"Not running (expected at {url})")
        except httpx.TimeoutException:
            results[agent_name] = (False, "Timed out")
        except Exception as e:
            results[agent_name] = (False, str(e))
    return results


# ── Tool definitions for the orchestrator ────────────────────────────────────

def get_orchestrator_tools() -> list[dict[str, Any]]:
    """
    Returns Claude tool definitions that Apollo uses to route to sub-agents.
    These are passed to the Anthropic API as tools in the tool_use loop.
    """
    return [
        {
            "name": "call_finance_agent",
            "description": (
                "Delegate a task to the Finance Agent. Use for: "
                "IBKR portfolio/positions/P&L, TradingView market data (quotes, charts, fundamentals), "
                "stock screener, watchlist management, price alerts. "
                "For read-only operations only — no trading."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Clear description of what financial data or action is needed",
                    },
                    "context": {
                        "type": "object",
                        "description": "Any relevant context (symbols, date ranges, etc.)",
                    },
                },
                "required": ["task"],
            },
        },
        {
            "name": "call_calendar_agent",
            "description": (
                "Delegate a task to the Calendar Agent. Use for: "
                "reading events, creating/updating/deleting events across Google Calendar and iCloud. "
                "IMPORTANT: creating or modifying events requires user confirmation."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Clear description of the calendar task",
                    },
                    "context": {
                        "type": "object",
                        "description": "Event details (title, date, time, location, etc.)",
                    },
                },
                "required": ["task"],
            },
        },
        {
            "name": "call_research_agent",
            "description": (
                "Delegate a research task to the Research Agent. Use for: "
                "web search, article summarization, news lookup, topic research, "
                "factual questions requiring up-to-date information."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Research question or topic to investigate",
                    },
                    "context": {
                        "type": "object",
                        "description": "Any guiding context (focus areas, date ranges, etc.)",
                    },
                },
                "required": ["task"],
            },
        },
        {
            "name": "call_browser_agent",
            "description": (
                "Delegate a task requiring browser automation to the Browser Agent. "
                "Use for: tasks that require navigating websites, filling forms, or extracting "
                "data from pages that require JavaScript rendering. Prefer Research Agent for "
                "pure information lookup."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Browser automation task description",
                    },
                    "url": {
                        "type": "string",
                        "description": "Starting URL if known",
                    },
                    "context": {
                        "type": "object",
                        "description": "Additional context for the browser task",
                    },
                },
                "required": ["task"],
            },
        },
        {
            "name": "call_travel_agent",
            "description": (
                "Delegate a travel planning task to the Travel Agent. Use for: "
                "flight search, hotel research, trip itinerary planning, "
                "credit card perks optimization (Amex Platinum, etc.), "
                "lounge access, booking recommendations."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Travel planning task",
                    },
                    "context": {
                        "type": "object",
                        "description": "Trip details (dates, origin, destination, preferences, budget, etc.)",
                    },
                },
                "required": ["task"],
            },
        },
        {
            "name": "call_market_agent",
            "description": (
                "Delegate a task to the Market Intelligence Agent. "
                "ALWAYS call this agent before answering ANY stock, sector, or investment question. "
                "It has live data: RS leaders (momentum rankings), EP alerts (gap-up stocks with "
                "game-changing catalysts), market regime (bull/choppy/correcting/crisis), and "
                "active themes (what sectors the market is rotating into right now). "
                "Use for: stock picks or ideas, dividend stock questions, sector analysis, "
                "EP/gap-up alerts, market conditions, top momentum stocks, morning briefing, "
                "theme health, 'what's the market doing?', 'any good setups?'. "
                "Ground every investment answer in this live data."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Market intelligence query",
                    },
                    "context": {
                        "type": "object",
                        "description": "Optional context (ticker, date range, sector, etc.)",
                    },
                },
                "required": ["task"],
            },
        },
        {
            "name": "teach_market_agent",
            "description": (
                "Teach the Market Intelligence Agent about stocks or themes you've spotted. "
                "Use this after gathering enough information from the user to: "
                "(1) add specific tickers to RS tracking so they're scored nightly, "
                "(2) seed a named theme with its constituent stocks and thesis. "
                "Before calling this tool, ask the user: which stocks, is it a new theme or "
                "extension of an existing one, and a brief thesis for why it's working. "
                "After calling, tell the user their stocks are now tracked and offer to "
                "trigger a data refresh to score them immediately."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ticker symbols to add to RS tracking (e.g. ['AXTI', 'AAOI', 'IIVI'])",
                    },
                    "theme_name": {
                        "type": "string",
                        "description": "Name for the theme to seed (e.g. 'Photonics & Laser Components'). Leave empty to just add tickers without a theme.",
                    },
                    "theme_thesis": {
                        "type": "string",
                        "description": "2-3 sentence thesis explaining what's driving this theme and why now.",
                    },
                    "observation": {
                        "type": "string",
                        "description": "Free-form observation from the user to store as a market memory.",
                    },
                    "override": {
                        "type": "boolean",
                        "description": "Set to true if the user has explicitly confirmed they want to proceed despite an extension/risk warning. Never set this on the first call — only after the user says 'yes anyway' or similar.",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "store_memory",
            "description": (
                "Store an important fact or preference about the user for future reference. "
                "Use when the user mentions preferences, important facts, or context "
                "that should be remembered across conversations."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category: 'preference', 'fact', 'goal', 'contact', 'travel_pref', etc.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The memory content to store",
                    },
                },
                "required": ["category", "content"],
            },
        },
    ]
