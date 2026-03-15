"""
Research Agent — web search and summarization.

Routing:
- Stock/catalyst queries  → Gemini with Google Search grounding (better recency + reasoning)
- General research        → Tavily + Claude synthesis
- Gemini unavailable      → fallback to Tavily + Claude
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import Any

import anthropic
import httpx

from agents.base import BaseAgent
from shared.models import AgentName, AgentRequest, AgentResponse
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
SUMMARIZE_MODEL = "claude-sonnet-4-6"
GEMINI_SEARCH_MODEL = "gemini-2.0-flash"

# Default recency window for Tavily searches (days). Caller can override via context["days"].
DEFAULT_SEARCH_DAYS = 14

# Patterns that signal a stock/market catalyst query → route to Gemini Search
_STOCK_QUERY_PATTERNS = re.compile(
    r"\b("
    r"why is .{1,10} (up|down|surging|falling|moving|running)"
    r"|catalyst"
    r"|what.s driving"
    r"|stock (news|move|surge|drop|rally)"
    r"|analyst (upgrade|downgrade|target)"
    r"|earnings|guidance|beat|miss"
    r"|\$[A-Z]{1,5}\b"
    r"|[A-Z]{2,5} stock"
    r")\b",
    re.IGNORECASE,
)


def _is_stock_query(text: str) -> bool:
    return bool(_STOCK_QUERY_PATTERNS.search(text))


def _get_gemini_client():
    """Return Gemini client if configured, else None."""
    try:
        from google import genai  # type: ignore
        api_key = get_secrets().gemini_api_key
        if not api_key:
            return None
        return genai.Client(api_key=api_key)
    except ImportError:
        logger.warning("google-genai not installed — Gemini search unavailable")
        return None


class ResearchAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentName.RESEARCH)
        self._anthropic = anthropic.Anthropic(api_key=get_secrets().anthropic_api_key)

    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        task = request.task
        context = request.context
        search_query = context.get("query") or task
        days = int(context.get("days", DEFAULT_SEARCH_DAYS))

        # Route stock/catalyst queries to Gemini Search for better recency + reasoning
        if _is_stock_query(task):
            result = await self._research_with_gemini(search_query)
            if result:
                return self._ok(request, result=result, data={"source": "gemini_search"})
            logger.info("Gemini search unavailable or failed — falling back to Tavily")

        # General research (or Gemini fallback): Tavily + Claude
        search_results = await self._search_tavily(search_query, days=days)
        if not search_results:
            return self._error(request, "No search results found for the query.")

        summary = await self._summarize_tavily(task, search_results)
        return self._ok(
            request,
            result=summary,
            data={"query": search_query, "result_count": len(search_results), "source": "tavily"},
        )

    async def _research_with_gemini(self, query: str) -> str | None:
        """
        Use Gemini with Google Search grounding for stock/catalyst research.
        Returns the grounded answer with sources, or None if unavailable.
        """
        client = _get_gemini_client()
        if not client:
            return None

        today = date.today().strftime("%B %d, %Y")
        prompt = (
            f"Today is {today}.\n\n"
            f"Research question: {query}\n\n"
            "Search for the most recent and specific information. "
            "Focus on concrete events, announcements, catalysts, and data from the last 2-3 weeks. "
            "Cite specific dates, companies, and numbers where available. "
            "If the move has multiple drivers, rank them by importance. "
            "Format your answer for Telegram (Markdown). Be specific — no generic explanations."
        )

        try:
            from google.genai import types  # type: ignore

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=GEMINI_SEARCH_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                    ),
                ),
            )

            text = response.text or ""
            if not text.strip():
                return None

            # Append grounding sources if available
            sources = _extract_sources(response)
            if sources:
                text += f"\n\n*Sources: {', '.join(sources[:4])}*"

            return text

        except Exception as e:
            logger.warning(f"Gemini search failed: {e}")
            return None

    async def _search_tavily(self, query: str, days: int = DEFAULT_SEARCH_DAYS) -> list[dict[str, Any]]:
        """Call Tavily Search API."""
        api_key = get_secrets().tavily_api_key
        if not api_key:
            logger.error("TAVILY_API_KEY not set")
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(
                    TAVILY_API_URL,
                    json={
                        "api_key": api_key,
                        "query": query,
                        "search_depth": "advanced",
                        "max_results": 8,
                        "include_answer": True,
                        "include_raw_content": False,
                        "days": days,
                    },
                )
                response.raise_for_status()
                return response.json().get("results", [])
            except httpx.HTTPError as e:
                logger.error(f"Tavily API error: {e}")
                return []

    async def _summarize_tavily(
        self, original_task: str, results: list[dict[str, Any]]
    ) -> str:
        """Synthesize Tavily results into a useful answer via Claude."""
        today = date.today().strftime("%B %d, %Y")
        results_text = "\n\n".join(
            f"**{r.get('title', 'Untitled')}** ({r.get('url', '')})\n{r.get('content', '')}"
            for r in results[:6]
        )

        response = self._anthropic.messages.create(
            model=SUMMARIZE_MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Today is {today}.\n\n"
                        f"Research task: {original_task}\n\n"
                        f"Search results:\n{results_text}\n\n"
                        "Synthesize a clear, accurate answer based ONLY on the search results above. "
                        "Rules:\n"
                        "- Cite specific events, dates, and sources from the results\n"
                        "- Do NOT speculate or add general knowledge not supported by the results\n"
                        "- If the results don't fully explain the question, say so explicitly\n"
                        "- Lead with the most specific, recent catalyst if one is present\n"
                        "- Use bullet points for lists. Format for Telegram (Markdown)."
                    ),
                }
            ],
        )
        return response.content[0].text


def _extract_sources(response: Any) -> list[str]:
    """Extract source URLs from Gemini grounding metadata."""
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
        return [
            c.web.uri
            for c in chunks
            if hasattr(c, "web") and c.web and c.web.uri
        ]
    except Exception:
        return []


# FastAPI app entry point
_agent = ResearchAgent()
app = _agent.app
