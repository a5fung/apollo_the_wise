"""
Finance Agent — portfolio data, market quotes, TradingView integration.
READ-ONLY. No trading operations.
"""
from __future__ import annotations

import logging
from typing import Any

import anthropic

from agents.base import BaseAgent
from agents.finance.ibkr import IBKRClient
from agents.finance.tv_browser import TradingViewBrowser
from shared.models import AgentName, AgentRequest, AgentResponse
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

FINANCE_MODEL = "claude-sonnet-4-6"


class FinanceAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentName.FINANCE)
        self._ibkr = IBKRClient()
        self._tv_browser: TradingViewBrowser | None = None
        self._anthropic = anthropic.Anthropic(api_key=get_secrets().anthropic_api_key)

    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        task = request.task.lower()
        context = request.context

        # Route to appropriate handler based on task keywords
        if any(k in task for k in ["portfolio", "positions", "holdings", "ibkr", "p&l", "pnl"]):
            return await self._handle_portfolio(request)

        if any(k in task for k in ["quote", "price", "chart", "stock", "ticker", "symbol"]):
            symbol = context.get("symbol") or self._extract_symbol(request.task)
            return await self._handle_quote(request, symbol)

        if any(k in task for k in ["screener", "scan", "screen"]):
            return await self._handle_screener(request)

        if any(k in task for k in ["fundamental", "financial", "pe ratio", "earnings"]):
            symbol = context.get("symbol") or self._extract_symbol(request.task)
            return await self._handle_fundamentals(request, symbol)

        # Fall back to Claude-guided routing
        return await self._handle_general(request)

    async def _handle_portfolio(self, request: AgentRequest) -> AgentResponse:
        """Fetch and summarize IBKR portfolio."""
        if not await self._ibkr.is_authenticated():
            return self._error(
                request,
                "IBKR Client Portal Gateway is not authenticated. "
                "Please open the gateway and log in via the IBKR mobile app."
            )

        try:
            positions = await self._ibkr.get_positions()
            summary = await self._ibkr.get_account_summary()
            formatted = self._ibkr.format_portfolio_summary(positions, summary)
            return self._ok(
                request,
                result=formatted,
                data={"position_count": len(positions)},
            )
        except Exception as e:
            logger.error(f"IBKR portfolio fetch failed: {e}")
            return self._error(request, f"Failed to fetch portfolio: {e}")

    async def _handle_quote(
        self, request: AgentRequest, symbol: str | None
    ) -> AgentResponse:
        """Get market quote for a symbol."""
        if not symbol:
            return self._error(request, "No ticker symbol specified in the task.")

        symbol = symbol.upper()

        try:
            tv = await self._get_tv_browser()
            quote = await tv.get_quote(symbol)

            price = quote.get("price", "N/A")
            change = quote.get("change", "")
            change_pct = quote.get("change_pct", "")

            result = (
                f"📈 *{symbol}*\n"
                f"Price: `{price}`"
                + (f"\nChange: `{change}` ({change_pct})" if change else "")
            )
            return self._ok(request, result=result, data=quote)
        except Exception as e:
            logger.error(f"Quote fetch failed for {symbol}: {e}")
            return self._error(request, f"Failed to get quote for {symbol}: {e}")

    async def _handle_screener(self, request: AgentRequest) -> AgentResponse:
        """Run TradingView screener."""
        try:
            tv = await self._get_tv_browser()
            results = await tv.run_screener(limit=10)

            if not results:
                return self._ok(request, result="Screener returned no results.")

            lines = ["📊 *Screener Results*\n"]
            for r in results:
                ticker = r.get("ticker", "?")
                price = r.get("price", "")
                change = r.get("change", "")
                lines.append(f"• `{ticker}` — {price} ({change})")

            return self._ok(
                request,
                result="\n".join(lines),
                data={"results": results},
            )
        except Exception as e:
            logger.error(f"Screener failed: {e}")
            return self._error(request, f"Screener failed: {e}")

    async def _handle_fundamentals(
        self, request: AgentRequest, symbol: str | None
    ) -> AgentResponse:
        """Get fundamental data for a symbol."""
        if not symbol:
            return self._error(request, "No ticker symbol specified.")

        try:
            tv = await self._get_tv_browser()
            data = await tv.get_fundamentals(symbol.upper())

            if len(data) <= 1:
                return self._error(request, f"No fundamental data found for {symbol}.")

            lines = [f"📊 *{symbol.upper()} Fundamentals*\n"]
            for k, v in list(data.items())[:15]:
                if k != "symbol":
                    lines.append(f"• {k}: `{v}`")

            return self._ok(
                request,
                result="\n".join(lines),
                data=data,
            )
        except Exception as e:
            logger.error(f"Fundamentals fetch failed: {e}")
            return self._error(request, f"Failed to get fundamentals: {e}")

    async def _handle_general(self, request: AgentRequest) -> AgentResponse:
        """Use Claude to interpret and handle general finance queries."""
        system = (
            "You are a finance assistant with access to IBKR portfolio data "
            "and TradingView market data. Answer financial questions concisely. "
            "Format for Telegram Markdown. Only provide read-only information — "
            "never suggest or execute trades."
        )

        response = self._anthropic.messages.create(
            model=FINANCE_MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": request.task}],
        )
        return self._ok(request, result=response.content[0].text)

    def _extract_symbol(self, text: str) -> str | None:
        """Extract a stock ticker from free-form text."""
        import re
        # Look for uppercase 1-5 letter words (typical tickers)
        matches = re.findall(r"\b([A-Z]{1,5})\b", text.upper())
        # Filter common English words
        exclude = {"A", "I", "OR", "AND", "THE", "FOR", "IN", "AT", "BE", "IF", "ON"}
        for m in matches:
            if m not in exclude:
                return m
        return None

    async def _get_tv_browser(self) -> TradingViewBrowser:
        """Get or create TradingView browser instance."""
        if self._tv_browser is None:
            self._tv_browser = TradingViewBrowser()
            await self._tv_browser.start(headless=True)
        return self._tv_browser


# FastAPI app entry point
_agent = FinanceAgent()
app = _agent.app
