"""
Data collection layer.

Polygon.io (Massive) — EOD OHLCV, pre-market snapshots, ticker details.
FMP — company profiles, earnings, analyst ratings.

Rate limits:
- Polygon Starter: unlimited calls (snapshot returns all US tickers in one call)
- FMP free: 250 calls/day → use sparingly, cache aggressively
"""
from __future__ import annotations

import asyncio
import logging
import os
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx
import pytz

logger = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io"
FMP_BASE = "https://financialmodelingprep.com/api"

# Polygon Starter: unlimited calls, but keep a small delay to be polite
_polygon_lock = asyncio.Semaphore(1)
_polygon_last_call: float = 0.0
POLYGON_RATE_DELAY = 0.2  # seconds — minimal courtesy delay


async def _polygon_get(path: str, params: dict | None = None) -> Any:
    """GET request to Polygon API with retry on 429."""
    global _polygon_last_call
    api_key = os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY not set")

    async with _polygon_lock:
        # Minimal courtesy delay between calls
        now = asyncio.get_event_loop().time()
        elapsed = now - _polygon_last_call
        if elapsed < POLYGON_RATE_DELAY:
            await asyncio.sleep(POLYGON_RATE_DELAY - elapsed)

        all_params = {"apiKey": api_key, **(params or {})}
        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(3):
                r = await client.get(f"{POLYGON_BASE}{path}", params=all_params)
                _polygon_last_call = asyncio.get_event_loop().time()
                if r.status_code == 429:
                    wait = 15 * (attempt + 1)  # 15s, 30s, 45s
                    logger.warning(f"Polygon 429 — waiting {wait}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            r.raise_for_status()  # raise on final attempt
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


async def fetch_all_ticker_types() -> dict[str, dict]:
    """
    Fetch security type + exchange for all US stock tickers from Polygon Reference API.
    Returns: {ticker: {"type": "CS"|"ETF"|..., "exchange": "XNYS"|...}}
    Paginated — typically 3-4 API calls for ~14K tickers.
    """
    result: dict[str, dict] = {}
    cursor = None
    page = 0
    while True:
        params = {"market": "stocks", "active": "true", "limit": "1000"}
        if cursor:
            params["cursor"] = cursor
        try:
            data = await _polygon_get("/v3/reference/tickers", params)
        except Exception as e:
            logger.error(f"Ticker types fetch failed (page {page}): {e}")
            break

        for t in data.get("results", []):
            ticker = t.get("ticker")
            if ticker:
                result[ticker] = {
                    "type": t.get("type", ""),
                    "exchange": t.get("primary_exchange", ""),
                }

        next_url = data.get("next_url")
        if not next_url:
            break
        # Extract cursor from next_url
        parsed = urllib.parse.urlparse(next_url)
        qs = urllib.parse.parse_qs(parsed.query)
        cursor = qs.get("cursor", [None])[0]
        if not cursor:
            break
        page += 1

    logger.info(f"Fetched types for {len(result)} tickers ({page + 1} pages)")
    return result


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
    d = from_date or et_today()
    days = []
    while len(days) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
    return days


def trading_date_n_months_ago(months: int) -> str:
    """Approximate trading date n months ago (skip weekends)."""
    d = et_today() - timedelta(days=months * 21)  # ~21 trading days/month
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


_ET = pytz.timezone("US/Eastern")


def et_today() -> date:
    """Return today's date in US/Eastern timezone."""
    return datetime.now(_ET).date()


# ── yfinance — company profile, analyst ratings (free, no API key) ────────────

async def get_fmp_profile(ticker: str) -> dict:
    """
    Company profile via yfinance: sector, float, market cap, 52W high, description.
    Normalised to match the field names the EP scorer expects.
    """
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info)
        return {
            "companyName":   info.get("longName", ticker),
            "sector":        info.get("sector", ""),
            "industry":      info.get("industry", ""),
            "description":   info.get("longBusinessSummary", "")[:500],
            "floatShares":   info.get("floatShares"),
            "marketCap":     info.get("marketCap"),
            "52WeekHigh":    info.get("fiftyTwoWeekHigh"),
            "price":         info.get("currentPrice") or info.get("regularMarketPrice"),
        }
    except Exception as e:
        logger.warning(f"yfinance profile failed for {ticker}: {e}")
        return {}


async def get_fmp_earnings(ticker: str) -> list[dict]:
    """Earnings history via yfinance."""
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        t = yf.Ticker(ticker)
        hist = await loop.run_in_executor(None, lambda: t.earnings_history)
        if hist is None or hist.empty:
            return []
        return hist.head(4).to_dict("records")
    except Exception as e:
        logger.warning(f"yfinance earnings failed for {ticker}: {e}")
        return []


async def get_fmp_analyst_ratings(ticker: str) -> list[dict]:
    """Analyst upgrades/recommendations via yfinance."""
    try:
        import pandas as pd
        import yfinance as yf
        loop = asyncio.get_event_loop()
        t = yf.Ticker(ticker)
        recs = await loop.run_in_executor(None, lambda: t.recommendations)
        if recs is None or (isinstance(recs, pd.DataFrame) and recs.empty):
            return []
        if not isinstance(recs, pd.DataFrame):
            return []  # yfinance API changed — bail gracefully
        recent = recs.tail(10).copy()
        # Find the grade column — yfinance has changed this across versions
        grade_col = None
        for col_name in ("To Grade", "toGrade", "strongBuy"):
            if col_name in recent.columns:
                grade_col = col_name
                break
        if grade_col:
            recent["analystRatingsStrongBuy"] = recent[grade_col].apply(
                lambda g: 1 if str(g).lower() in ("strong buy", "buy", "outperform", "overweight") else 0
            )
        else:
            recent["analystRatingsStrongBuy"] = 0
        return recent.to_dict("records")
    except Exception as e:
        logger.warning(f"yfinance analyst ratings failed for {ticker}: {e}")
        return []


async def get_fmp_news(ticker: str, limit: int = 5) -> list[dict]:
    """Recent news via yfinance."""
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        t = yf.Ticker(ticker)
        news = await loop.run_in_executor(None, lambda: t.news)
        if not news:
            return []
        return [{"title": n.get("content", {}).get("title", ""),
                 "text":  n.get("content", {}).get("summary", "")}
                for n in news[:limit]]
    except Exception as e:
        logger.warning(f"yfinance news failed for {ticker}: {e}")
        return []


async def get_premarket_futures() -> dict[str, float]:
    """
    Pre-market futures snapshot via Polygon.
    Returns overnight % change for ES (S&P 500) and NQ (Nasdaq 100).

    Uses SPY/QQQ snapshots from Polygon:
      - prevDay.c  = confirmed 4 PM regular-session close (reliable reference)
      - min.c      = latest minute bar close (updates in pre-market)
    This gives the true overnight change vs the equity close — the same
    reference point a trader would use looking at futures vs yesterday's close.

    Fails gracefully — returns empty dict on any error.
    """
    try:
        data = await _polygon_get(
            "/v2/snapshot/locale/us/markets/stocks/tickers",
            {"tickers": "SPY,QQQ"},
        )
        snaps = {t["ticker"]: t for t in data.get("tickers", []) if "ticker" in t}
        result = {}
        for ticker, key in (("SPY", "es_pct"), ("QQQ", "nq_pct")):
            snap = snaps.get(ticker, {})
            prev = snap.get("prevDay", {}).get("c")
            current = (
                snap.get("min", {}).get("c")
                or snap.get("lastTrade", {}).get("p")
                or snap.get("day", {}).get("o")
            )
            if prev and current and prev != 0:
                pct = (current - prev) / prev * 100
                result[key] = pct
                logger.debug(f"Futures proxy {ticker}: current={current:.2f} prevDay.c={prev:.2f} → {pct:+.2f}%")
        return result
    except Exception as e:
        logger.warning(f"Futures snapshot failed: {e}")
        return {}


async def get_overnight_snapshot(watchlist: list[dict]) -> list[dict]:
    """
    Fetch overnight price changes for all watchlist instruments via yfinance.
    Returns list of dicts with symbol, name, pct_change, price, threshold, triggered.
    """
    if not watchlist:
        return []
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()

        def _fetch() -> list[dict]:
            results = []
            for item in watchlist:
                symbol = item["symbol"]
                try:
                    fi = yf.Ticker(symbol).fast_info
                    price = getattr(fi, "last_price", None)
                    prev = getattr(fi, "previous_close", None)
                    if price is not None and prev is not None and prev != 0:
                        pct = (price - prev) / prev * 100
                        threshold = item.get("threshold_pct", 0.5)
                        results.append({
                            "symbol": symbol,
                            "name": item.get("display_name", symbol),
                            "price": round(price, 2),
                            "pct_change": round(pct, 2),
                            "threshold": threshold,
                            "category": item.get("category", "other"),
                            "triggered": abs(pct) >= threshold,
                        })
                except Exception:
                    pass
            return results

        return await loop.run_in_executor(None, _fetch)
    except Exception as e:
        logger.warning(f"Overnight snapshot failed: {e}")
        return []


_PERPLEXITY_SYSTEM_DEFAULT = (
    "You are a financial market analyst. Give direct, specific answers "
    "about current market catalysts. "
    "Never include citation numbers like [1] or [2]. "
    "Never say 'search results show' or 'I cannot find'. "
    "Plain text only — no markdown, no bullets."
)


async def search_news_perplexity(
    query: str, recency: str = "month", system_prompt: str | None = None,
) -> str:
    """Use Perplexity Sonar for news search. Returns a synthesized answer string.

    recency: "day" | "week" | "month" | "year" — use "week" for EP catalysts.
    system_prompt: override the default system prompt for specialized callers.
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return ""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "sonar-pro",
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt or _PERPLEXITY_SYSTEM_DEFAULT,
                        },
                        {"role": "user", "content": query},
                    ],
                    "search_recency_filter": recency,
                    "return_citations": False,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Perplexity search failed: {e}")
        return ""


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
