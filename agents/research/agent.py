"""
Research Agent — web search and summarization using Tavily API.
"""
from __future__ import annotations

import logging
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

# Default recency window for searches (days). Caller can override via context["days"].
DEFAULT_SEARCH_DAYS = 14


class ResearchAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentName.RESEARCH)
        self._anthropic = anthropic.Anthropic(api_key=get_secrets().anthropic_api_key)

    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        task = request.task
        context = request.context

        search_query = context.get("query") or task
        days = int(context.get("days", DEFAULT_SEARCH_DAYS))

        search_results = await self._search(search_query, days=days)
        if not search_results:
            return self._error(request, "No search results found for the query.")

        summary = await self._summarize(task, search_results)

        return self._ok(
            request,
            result=summary,
            data={"query": search_query, "result_count": len(search_results)},
        )

    async def _search(self, query: str, days: int = DEFAULT_SEARCH_DAYS) -> list[dict[str, Any]]:
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
                        "max_results": 10,
                        "include_answer": False,
                        "include_raw_content": False,
                        "days": days,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
            except httpx.HTTPError as e:
                logger.error(f"Tavily API error: {e}")
                return []

    async def _summarize(
        self, original_task: str, results: list[dict[str, Any]]
    ) -> str:
        """Synthesize search results into a useful answer."""
        today = date.today().strftime("%B %d, %Y")
        results_text = "\n\n".join(
            f"Source: {r.get('title', 'Untitled')} ({r.get('url', '')})\n{r.get('content', '')}"
            for r in results[:8]
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
                        "- If the results don't fully explain the question, say so explicitly: "
                        "'The search results don't clearly explain X — here's what I found:'\n"
                        "- Lead with the most specific, recent catalyst if one is present\n"
                        "- Use bullet points for lists. Format for Telegram (plain text, no --- dividers)."
                    ),
                }
            ],
        )
        return response.content[0].text


# FastAPI app entry point
_agent = ResearchAgent()
app = _agent.app
