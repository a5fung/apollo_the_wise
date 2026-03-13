"""
TradingView browser automation — uses Playwright to interact with TradingView.

Capabilities:
- Read price quotes, charts data, and fundamentals
- Run stock screener
- Manage watchlists (add/remove symbols)
- Set/modify price alerts

Note: TradingView has rate limits and anti-bot measures.
Use respectfully with reasonable delays.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy import Playwright to avoid startup errors if not installed
try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed — TV browser automation unavailable")

TV_BASE_URL = "https://www.tradingview.com"


class TradingViewBrowser:
    """
    Playwright-based TradingView automation.
    Manages a persistent browser session.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional["Browser"] = None
        self._page: Optional["Page"] = None

    async def start(self, headless: bool = True) -> None:
        """Launch browser and navigate to TradingView."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed. Run: playwright install chromium")

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await context.new_page()

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get current price and basic data for a symbol."""
        if not self._page:
            raise RuntimeError("Browser not started")

        url = f"{TV_BASE_URL}/symbols/{symbol.upper()}/"
        await self._page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        data: dict[str, Any] = {"symbol": symbol.upper()}

        try:
            # Extract price
            price_el = await self._page.query_selector('[data-field="last_price"]')
            if price_el:
                data["price"] = await price_el.inner_text()

            # Extract change
            change_el = await self._page.query_selector('[data-field="change"]')
            if change_el:
                data["change"] = await change_el.inner_text()

            change_pct_el = await self._page.query_selector('[data-field="change_percent"]')
            if change_pct_el:
                data["change_pct"] = await change_pct_el.inner_text()

        except Exception as e:
            logger.error(f"Error extracting quote for {symbol}: {e}")

        return data

    async def run_screener(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Run TradingView stock screener with given filters.
        Returns list of matching stocks.
        """
        if not self._page:
            raise RuntimeError("Browser not started")

        await self._page.goto(
            f"{TV_BASE_URL}/screener/",
            wait_until="networkidle",
            timeout=30000,
        )
        await asyncio.sleep(3)

        results = []
        try:
            rows = await self._page.query_selector_all(".screener-table-row")
            for row in rows[:limit]:
                cells = await row.query_selector_all("td")
                if len(cells) >= 3:
                    ticker_el = await cells[0].query_selector(".symbol-description-component")
                    ticker = await ticker_el.inner_text() if ticker_el else ""
                    price = await cells[1].inner_text() if len(cells) > 1 else ""
                    change = await cells[2].inner_text() if len(cells) > 2 else ""
                    results.append({
                        "ticker": ticker.strip(),
                        "price": price.strip(),
                        "change": change.strip(),
                    })
        except Exception as e:
            logger.error(f"Error running screener: {e}")

        return results

    async def add_to_watchlist(self, symbol: str, watchlist_name: str = "Default") -> bool:
        """Add a symbol to a TradingView watchlist (requires login)."""
        logger.info(f"Adding {symbol} to watchlist '{watchlist_name}'")
        # Implementation requires TradingView login session
        # TODO: Implement with saved session cookies
        raise NotImplementedError(
            "Watchlist management requires TradingView login. "
            "Set up session cookies in configuration."
        )

    async def set_price_alert(
        self,
        symbol: str,
        condition: str,
        price: float,
        message: str = "",
    ) -> bool:
        """Set a price alert on TradingView (requires login)."""
        logger.info(f"Setting alert: {symbol} {condition} {price}")
        raise NotImplementedError(
            "Alert management requires TradingView login. "
            "Set up session cookies in configuration."
        )

    async def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Get fundamental data for a symbol from TradingView."""
        if not self._page:
            raise RuntimeError("Browser not started")

        url = f"{TV_BASE_URL}/symbols/{symbol.upper()}/financials-overview/"
        await self._page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        data: dict[str, Any] = {"symbol": symbol.upper()}

        try:
            fundamentals_els = await self._page.query_selector_all(
                ".financial-data-row"
            )
            for el in fundamentals_els[:20]:
                label_el = await el.query_selector(".label")
                value_el = await el.query_selector(".value")
                if label_el and value_el:
                    label = await label_el.inner_text()
                    value = await value_el.inner_text()
                    data[label.strip()] = value.strip()
        except Exception as e:
            logger.error(f"Error extracting fundamentals for {symbol}: {e}")

        return data
