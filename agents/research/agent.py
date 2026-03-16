"""
Research Agent — web search and summarization using Perplexity Sonar API.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from agents.base import BaseAgent
from shared.models import AgentName, AgentRequest, AgentResponse
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Default recency window. Caller can override via context["recency"].
DEFAULT_RECENCY = "month"


class ResearchAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentName.RESEARCH)

    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        task = request.task
        context = request.context

        query = context.get("query") or task
        recency = context.get("recency", DEFAULT_RECENCY)

        answer = await self._search(query, recency=recency)
        if not answer:
            return self._error(request, "No results found for the query.")

        return self._ok(request, result=answer, data={"query": query})

    async def _search(self, query: str, recency: str = DEFAULT_RECENCY) -> str:
        """Call Perplexity Sonar — returns a grounded, cited answer."""
        api_key = get_secrets().perplexity_api_key
        if not api_key:
            logger.error("PERPLEXITY_API_KEY not set")
            return ""

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(
                    PERPLEXITY_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "sonar",
                        "messages": [{"role": "user", "content": query}],
                        "search_recency_filter": recency,
                    },
                )
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"]
                # Strip markdown HR dividers that don't render in Telegram
                return "\n".join(
                    line for line in text.splitlines() if line.strip() not in ("---", "***", "___")
                ).strip()
            except httpx.HTTPError as e:
                logger.error(f"Perplexity API error: {e}")
                return ""


# FastAPI app entry point
_agent = ResearchAgent()
app = _agent.app
