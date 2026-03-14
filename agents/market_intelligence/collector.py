"""
Data collection layer.

Polygon.io — EOD OHLCV, pre-market snapshots, ticker details.
FMP — company profiles, earnings, analyst ratings.

Rate limits:
- Polygon free: 5 calls/minute → 1 call every 12s minimum
- FMP free: 250 calls/day → use sparingly, cache aggressively
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io"
FMP_BASE = "https://financialmodelingprep.com/api"

# Polygon free tier: 5 req/min → sleep 12s between calls
_polygon_lock = asyncio.Semaphore(1)
_polygon_last_call: float = 0.0
POLYGON_RATE_DELAY = 12.0  # seconds


async def _polygon_get(path: str, params: dict | None = None) -> Any:
    """Rate-limited GET request to Polygon API."""
    global _polygon_last_call
    api_key = os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY not set")

    async with _polygon_lock:
        # Enforce rate limit
        now = asyncio.get_event_loop().time()
        elapsed = now - _polygon_last_call
        if elapsed < POLYGON_RATE_DELAY:
            await asyncio.sleep(POLYGON_RATE_DELAY - elapsed)

        all_params = {"apiKey": api_key, **(params or {})}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{POLYGON_BASE}{path}", params=all_params)
            _polygon_last_call = asyncio.get_event_loop().time()
            r.raise_for_status()
            return r.json()


async def _fmp_get(path: str, params: dict | None = None) -> Any:
    """GET request to FMP API."""
    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key:
        raise RuntimeError("FMP_API_KEY not set")

    all_params = {"apikey": api_key, **(params or {})}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{FMP_BASE}{path}", params=all_params)
        r.raise_for_status()
        return r.json()


# ── Polygon endpoints ──────────────────────────────────────────────────────────

async def get_grouped_daily(trade_date: str) -> dict[str, dict]:
    """
    Get all US stock OHLCV for a given date.
    Returns: {ticker: {o, h, l, c, v, vw, t}} or empty dict if market closed.
    trade_date: "YYYY-MM-DD"
    """
    try:
        data = await _polygon_get(
            f"/v2/aggs/grouped/locale/us/market/stocks/{trade_date}",
            {"adjusted": "true", "include_otc": "false"},
        )
        results = data.get("results", [])
        return {r["T"]: r for r in results if "T" in r}
    except Exception as e:
        logger.error(f"Grouped daily failed for {trade_date}: {e}")
        return {}


async def get_snapshot_all() -> dict[str, dict]:
    """
    Get current snapshot for all tickers (includes pre-market data).
    Returns: {ticker: snapshot_dict}
    Pre-market price is in snapshot["lastTrade"]["p"] or snapshot["day"]["o"]
    """
    try:
        data = await _polygon_get(
            "/v2/snapshot/locale/us/markets/stocks/tickers",
            {"include_otc": "false"},
        )
        tickers = data.get("tickers", [])
        return {t["ticker"]: t for t in tickers if "ticker" in t}
    except Exception as e:
        logger.error(f"Snapshot fetch failed: {e}")
        return {}


async def get_ticker_details(ticker: str) -> dict:
    """Get company details: name, sector, shares outstanding, etc."""
    try:
        data = await _polygon_get(f"/v3/reference/tickers/{ticker}")
        return data.get("results", {})
    except Exception as e:
        logger.warning(f"Ticker details failed for {ticker}: {e}")
        return {}


async def get_index_history(ticker: str, from_date: str, to_date: str) -> list[dict]:
    """
    Get daily bars for a ticker over a date range.
    Used for SPY/QQQ/VIX regime calculations.
    """
    try:
        data = await _polygon_get(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}",
            {"adjusted": "true", "sort": "asc", "limit": 300},
        )
        return data.get("results", [])
    except Exception as e:
        logger.error(f"History failed for {ticker}: {e}")
        return []


def prev_trading_days(n: int, from_date: date | None = None) -> list[date]:
    """
    Return a list of n approximate trading dates going back from from_date.
    Approximation: skips weekends only (not holidays). Good enough for RS calc.
    """
    d = from_date or date.today()
    days = []
    while len(days) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
    return days


def trading_date_n_months_ago(months: int) -> str:
    """Approximate trading date n months ago (skip weekends)."""
    d = date.today() - timedelta(days=months * 21)  # ~21 trading days/month
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


# ── FMP endpoints ──────────────────────────────────────────────────────────────

async def get_fmp_profile(ticker: str) -> dict:
    """
    Company profile: sector, industry, market cap, float, description.
    Returns first element of list or empty dict.
    """
    try:
        data = await _fmp_get(f"/v3/profile/{ticker}")
        return data[0] if data else {}
    except Exception as e:
        logger.warning(f"FMP profile failed for {ticker}: {e}")
        return {}


async def get_fmp_earnings(ticker: str) -> list[dict]:
    """Recent earnings surprises."""
    try:
        data = await _fmp_get(f"/v3/earnings-surprises/{ticker}")
        return data[:4] if data else []  # last 4 quarters
    except Exception as e:
        logger.warning(f"FMP earnings failed for {ticker}: {e}")
        return []


async def get_fmp_analyst_ratings(ticker: str) -> list[dict]:
    """Recent analyst rating changes."""
    try:
        data = await _fmp_get(f"/v3/analyst-stock-recommendations/{ticker}")
        return data[:10] if data else []
    except Exception as e:
        logger.warning(f"FMP analyst ratings failed for {ticker}: {e}")
        return []


async def get_fmp_news(ticker: str, limit: int = 5) -> list[dict]:
    """Recent news for a ticker."""
    try:
        data = await _fmp_get("/v3/stock_news", {"tickers": ticker, "limit": limit})
        return data if data else []
    except Exception as e:
        logger.warning(f"FMP news failed for {ticker}: {e}")
        return []


async def search_news_tavily(query: str) -> list[dict]:
    """Use Tavily for news search when available."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "search_depth": "basic", "max_results": 5},
            )
            r.raise_for_status()
            return r.json().get("results", [])
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}")
        return []
