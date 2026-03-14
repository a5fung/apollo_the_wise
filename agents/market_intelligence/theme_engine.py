"""
Theme Intelligence Engine — Marios Stamatoudis methodology.

Key insight: themes emerge bottom-up from price action, not top-down from hypothesis.
Apollo discovers themes by clustering top RS stocks, not by guessing in advance.

Nightly process:
1. Pull top 40 RS stocks from today's scores
2. Enrich with sector/industry from yfinance (cached)
3. Claude clusters into 3-6 named themes with thesis
4. Tavily confirms/challenges each theme with news
5. Score: momentum 40% + breadth 30% + news confirmation 30%
6. Classify lifecycle: Nascent / Accelerating / Mainstream / Fading
7. Store in mi_themes, surface in morning briefing

Lifecycle detection:
- Nascent:       new theme not seen in last 3 days
- Accelerating:  score up vs yesterday, RS of constituents strengthening
- Mainstream:    stable high score, 5+ days old, widely known
- Fading:        score down vs yesterday, RS deteriorating
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, timedelta
from typing import Any

import anthropic

from agents.market_intelligence.collector import get_fmp_profile, search_news_tavily
from agents.market_intelligence.db import get_pool, get_rs_leaders

logger = logging.getLogger(__name__)

THEME_MODEL = "claude-sonnet-4-6"

# Cache yfinance sector lookups to avoid repeated calls
_sector_cache: dict[str, str] = {}


async def _get_sector(ticker: str) -> str:
    """Get sector for a ticker, cached."""
    if ticker in _sector_cache:
        return _sector_cache[ticker]
    profile = await get_fmp_profile(ticker)  # uses yfinance under the hood
    sector = profile.get("sector") or profile.get("industry") or "Unknown"
    _sector_cache[ticker] = sector
    return sector


async def _get_yesterday_themes(today: date) -> list[dict]:
    """Get themes from yesterday for lifecycle comparison."""
    yesterday = today - timedelta(days=1)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM mi_themes WHERE theme_date = $1",
            yesterday,
        )
        return [dict(r) for r in rows]


async def _save_themes(themes: list[dict]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Clear today's themes first (idempotent)
        await conn.execute(
            "DELETE FROM mi_themes WHERE theme_date = $1",
            themes[0]["theme_date"] if themes else date.today(),
        )
        for t in themes:
            await conn.execute("""
                INSERT INTO mi_themes (theme_date, name, stage, score, description, tickers)
                VALUES ($1, $2, $3, $4, $5, $6)
            """,
                t["theme_date"], t["name"], t["stage"],
                t["score"], t["description"], t["tickers"],
            )


async def _cluster_themes_claude(stocks: list[dict]) -> list[dict]:
    """
    Use Claude to cluster top RS stocks into named themes.
    Returns list of {name, thesis, tickers, sectors}
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    stock_lines = "\n".join(
        f"- {s['ticker']} (RS {s.get('rs_composite', 0):.0f}, rank #{s.get('rs_rank', '?')}, sector: {s.get('sector', 'Unknown')})"
        for s in stocks
    )

    prompt = f"""You are a market intelligence analyst using Marios Stamatoudis's theme discovery methodology.

Below are today's top relative strength stocks, ranked by momentum (1M/3M/6M composite).
Themes emerge BOTTOM-UP from price action — you're discovering what the market is rotating into,
not imposing a top-down hypothesis.

TOP RS STOCKS TODAY:
{stock_lines}

Task: Identify 3-6 distinct investment themes from these stocks.

Rules:
- A theme needs at least 2 stocks. Single-stock moves are not themes.
- Name themes specifically (not "Technology" — instead "AI Inference Infrastructure" or "Edge CDN Acceleration")
- Each stock should belong to at most one theme
- Some stocks may not fit any theme — that's fine, leave them out
- Focus on what the MARKET is pricing in, based on which stocks are moving together

Return ONLY valid JSON in this exact format:
{{
  "themes": [
    {{
      "name": "Theme Name",
      "thesis": "2-3 sentence explanation of what's driving this theme and why now.",
      "tickers": ["TICK1", "TICK2", "TICK3"]
    }}
  ]
}}"""

    try:
        response = client.messages.create(
            model=THEME_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        return data.get("themes", [])
    except Exception as e:
        logger.error(f"Claude theme clustering failed: {e}")
        return []


async def _score_theme(
    theme: dict,
    stocks_by_ticker: dict[str, dict],
    yesterday_themes: list[dict],
) -> dict:
    """
    Score a theme and determine its lifecycle stage.

    Score = 40% momentum + 30% breadth + 30% news confirmation
    """
    tickers = theme.get("tickers", [])
    if not tickers:
        return {**theme, "score": 0.0, "stage": "Nascent"}

    # Momentum score (40%): avg RS composite of constituents
    rs_scores = [stocks_by_ticker[t].get("rs_composite", 0) for t in tickers if t in stocks_by_ticker]
    momentum = (sum(rs_scores) / len(rs_scores)) if rs_scores else 0
    momentum_score = min(momentum / 100 * 40, 40)

    # Breadth score (30%): number of distinct sectors represented
    sectors = set(stocks_by_ticker[t].get("sector", "Unknown") for t in tickers if t in stocks_by_ticker)
    breadth_score = min(len(sectors) * 10, 30)

    # News confirmation (30%): Tavily search for theme evidence
    news_score = 0
    try:
        results = await search_news_tavily(f"{theme['name']} stocks sector momentum 2026")
        if results:
            news_score = min(len(results) * 6, 30)
    except Exception:
        pass

    total_score = round(momentum_score + breadth_score + news_score, 1)

    # Lifecycle stage
    name = theme["name"]
    prev = next((t for t in yesterday_themes if t["name"] == name), None)

    if prev is None:
        stage = "Nascent"
    else:
        prev_score = prev.get("score") or 0
        delta = total_score - prev_score
        # Also check how old this theme is
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mi_themes WHERE name = $1", name
            )
        if delta > 3:
            stage = "Accelerating"
        elif delta < -5:
            stage = "Fading"
        elif count >= 5:
            stage = "Mainstream"
        else:
            stage = "Accelerating"

    return {
        "name": name,
        "thesis": theme.get("thesis", ""),
        "tickers": tickers,
        "score": total_score,
        "stage": stage,
        "momentum_score": momentum_score,
        "breadth_score": breadth_score,
        "news_score": news_score,
    }


async def run_theme_engine(trade_date: date | None = None) -> list[dict]:
    """
    Run the full theme discovery process.
    Returns list of scored themes, stored in DB.
    """
    today = trade_date or date.today()
    today_str = today.strftime("%Y-%m-%d")

    logger.info("Theme engine: fetching top RS stocks...")
    leaders = await get_rs_leaders(today_str, limit=40)

    if not leaders:
        logger.warning("Theme engine: no RS data — run RS engine first")
        return []

    # Enrich with sector data (sample to save API calls)
    logger.info(f"Theme engine: enriching {len(leaders)} stocks with sector data...")
    for stock in leaders:
        if not stock.get("sector"):
            stock["sector"] = await _get_sector(stock["ticker"])
            await asyncio.sleep(0.2)  # avoid hammering yfinance

    stocks_by_ticker = {s["ticker"]: s for s in leaders}

    # Claude clusters into themes
    logger.info("Theme engine: clustering themes with Claude...")
    raw_themes = await _cluster_themes_claude(leaders)
    logger.info(f"Theme engine: {len(raw_themes)} themes identified")

    if not raw_themes:
        return []

    # Get yesterday's themes for lifecycle comparison
    yesterday_themes = await _get_yesterday_themes(today)

    # Score each theme
    logger.info("Theme engine: scoring themes...")
    scored_themes = []
    for raw in raw_themes:
        scored = await _score_theme(raw, stocks_by_ticker, yesterday_themes)
        scored_themes.append(scored)
        await asyncio.sleep(1)  # Tavily rate limiting

    # Sort by score descending
    scored_themes.sort(key=lambda t: t["score"], reverse=True)

    # Persist to DB
    db_records = []
    for t in scored_themes:
        db_records.append({
            "theme_date": today,
            "name": t["name"],
            "stage": t["stage"],
            "score": t["score"],
            "description": t["thesis"],
            "tickers": t["tickers"],
        })

    if db_records:
        await _save_themes(db_records)

    logger.info(f"Theme engine complete: {len(scored_themes)} themes for {today_str}")
    return scored_themes


async def get_today_themes(d: "str | date | None" = None) -> list[dict]:
    """Fetch today's themes from DB."""
    from datetime import date as date_type
    if d is None:
        target = date_type.today()
    elif isinstance(d, str):
        target = date_type.fromisoformat(d)
    else:
        target = d

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM mi_themes WHERE theme_date = $1 ORDER BY score DESC",
            target,
        )
        return [dict(r) for r in rows]
