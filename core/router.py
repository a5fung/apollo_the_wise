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

# Timeout for sub-agent calls (seconds).
# Theme engine can take 3-4 min on first run; set high enough to not cut it off.
AGENT_TIMEOUT = 360


def auth_headers() -> dict[str, str]:
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
                headers=auth_headers(),
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
                r = await client.get(f"{url}/health", headers=auth_headers())
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


async def get_market_pipeline_status() -> dict | None:
    """Fetch market pipeline status from the market intelligence agent. Returns None if unreachable."""
    url = get_agent_url("market_intelligence")
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{url}/market/status", headers=auth_headers())
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return None


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
                "It also has HISTORICAL data: RS history for any ticker over time (weekly snapshots, "
                "90-day retention), theme history with stage transitions and peak scores (60-day retention). "
                "Use for: stock picks or ideas, dividend stock questions, sector analysis, "
                "EP/gap-up alerts, market conditions, top momentum stocks, morning briefing, "
                "theme health, 'what's the market doing?', 'any good setups?', "
                "'when did X theme peak?', 'RS history for CIEN', 'how has gold miners theme evolved?'. "
                "For history queries, pass from_date/to_date and optional theme_name in the context object. "
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
            "name": "update_stock_info",
            "description": (
                "Update a stock's business description when a material change happens — "
                "e.g. a company pivots into a new product, wins a transformative contract, "
                "or enters a new market. This overrides the static description used by the "
                "theme engine for clustering. Use sparingly — only for genuine business "
                "pivots or material catalysts that change what the company does, not for "
                "routine earnings beats or price moves. "
                "Example: 'GLW is now an optical datacenter components play after the Meta deal' "
                "→ update description to reflect the new business driver."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "The ticker symbol (e.g. 'GLW')",
                    },
                    "description": {
                        "type": "string",
                        "description": "New one-line business description reflecting the material change (e.g. 'Optical datacenter components, precision glass for AI infrastructure — Meta partnership')",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Why this was updated — the catalyst or context (e.g. 'Meta deal announced 2026-03, pivoted from specialty glass')",
                    },
                },
                "required": ["ticker", "description"],
            },
        },
        {
            "name": "run_stock_screener",
            "description": (
                "Run a composite stock screener: RS leadership + active theme stage + "
                "O'Neil fundamentals (EPS/revenue YoY growth, acceleration). "
                "Use for queries like: 'find top fundamental stocks with RS leadership', "
                "'best setups with accelerating EPS', 'top Accelerating theme stocks with EPS growth', "
                "'screen for RS > 70 and EPS growth > 25%'. "
                "Always call this instead of call_market_agent for screener/filter queries. "
                "Results are ranked by composite score (RS + theme bonus + EPS bonus + accel bonus)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "min_rs": {
                        "type": "number",
                        "description": "Minimum RS composite score (default 60). Use 70+ for high-quality setups.",
                    },
                    "min_eps_yoy_pct": {
                        "type": "number",
                        "description": "Minimum latest-quarter EPS YoY growth % (e.g. 25 for ≥25%). Omit to not filter.",
                    },
                    "min_rev_yoy_pct": {
                        "type": "number",
                        "description": "Minimum latest-quarter revenue YoY growth % (e.g. 15 for ≥15%). Omit to not filter.",
                    },
                    "require_acceleration": {
                        "type": "boolean",
                        "description": "If true, only include stocks where latest EPS YoY > prior quarter EPS YoY.",
                    },
                    "require_sales_confirms": {
                        "type": "boolean",
                        "description": "If true, only include stocks where revenue YoY ≥ 15% (sales confirms earnings).",
                    },
                    "theme_stage": {
                        "type": "string",
                        "enum": ["Nascent", "Accelerating", "Mainstream", "Fading"],
                        "description": "Filter to stocks in a specific active theme stage. Omit for all stages.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max number of results to return (default 20, max 50).",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "tweet_message",
            "description": (
                "Post a tweet to the @Apollo_Trends Twitter/X account. "
                "Use when the user asks to tweet, share on Twitter, or post something to X. "
                "The user may say 'tweet that', 'share this on Twitter', or 'post that to X' — "
                "in that case, condense your previous response into a compelling tweet (max 280 chars). "
                "If the content is too long for one tweet, it will automatically be split into a thread. "
                "Include relevant hashtags. Format for maximum engagement — concise, punchy, data-driven. "
                "Always show the user the draft tweet text before posting and get their confirmation."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The tweet text to post. Max 280 chars for a single tweet; longer text will be split into a thread.",
                    },
                },
                "required": ["text"],
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
