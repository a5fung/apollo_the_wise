"""
Browser Agent — general Playwright browser automation.
Used for tasks requiring JavaScript-rendered pages or form interaction.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import anthropic

from agents.base import BaseAgent
from shared.models import AgentName, AgentRequest, AgentResponse
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

BROWSER_MODEL = "claude-sonnet-4-6"

try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentName.BROWSER)
        self._anthropic = anthropic.Anthropic(api_key=get_secrets().anthropic_api_key)

    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        if not PLAYWRIGHT_AVAILABLE:
            return self._error(
                request,
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )

        task = request.task
        url = request.context.get("url")

        try:
            result = await self._run_browser_task(task, url)
            return self._ok(request, result=result)
        except Exception as e:
            logger.exception(f"Browser task failed: {e}")
            return self._error(request, f"Browser automation failed: {e}")

    async def _run_browser_task(self, task: str, url: str | None = None) -> str:
        """Execute a browser task using Playwright + Claude vision."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = await browser.new_page(
                viewport={"width": 1920, "height": 1080},
            )

            try:
                if url:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await asyncio.sleep(2)

                # Extract page content for Claude to analyze
                content = await page.evaluate("""() => {
                    // Remove scripts/styles, get readable text
                    const clone = document.cloneNode(true);
                    clone.querySelectorAll('script, style, nav, footer, aside').forEach(e => e.remove());
                    return {
                        title: document.title,
                        url: window.location.href,
                        text: clone.body?.innerText?.slice(0, 8000) || ''
                    };
                }""")

                # Ask Claude to interpret the page and answer the task
                response = self._anthropic.messages.create(
                    model=BROWSER_MODEL,
                    max_tokens=2048,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"Browser task: {task}\n\n"
                                f"Page title: {content.get('title', 'N/A')}\n"
                                f"URL: {content.get('url', url or 'N/A')}\n\n"
                                f"Page content:\n{content.get('text', '(empty)')}\n\n"
                                "Complete the task based on the page content above. "
                                "Be concise and focused."
                            ),
                        }
                    ],
                )
                return response.content[0].text

            finally:
                await browser.close()


# FastAPI app entry point
_agent = BrowserAgent()
app = _agent.app
