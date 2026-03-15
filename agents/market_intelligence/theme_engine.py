"""
Theme Intelligence Engine — Marios Stamatoudis methodology.

Key insight: themes emerge bottom-up from price action, not top-down from hypothesis.

Daily process:
1. Load existing active themes from DB (re-scored, not re-clustered)
2. Find top RS stocks NOT covered by active themes
3. Claude discovers new themes from uncovered stocks (with existing themes as context)
4. Merge: updated existing themes + new discoveries
5. Lifecycle: Nascent → Accelerating → Mainstream → Fading → Retired

Themes persist for weeks. They evolve as constituent stocks change.
A Fading theme retires after 5 consecutive fading days.
New sub-themes can always emerge from uncovered RS leaders.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Any

import anthropic

from agents.market_intelligence.collector import get_fmp_profile, search_news_tavily
from agents.market_intelligence.db import get_pool, get_rs_leaders, get_active_themes

logger = logging.getLogger(__name__)

THEME_MODEL = "claude-sonnet-4-6"

# Min RS composite for a stock to "count" as strong within a theme
THEME_RS_MIN = 50.0
# A theme is "well-covered" if >= this many of its stocks still show strong RS
THEME_COVERAGE_MIN = 2
# Retire a theme after this many consecutive fading days
FADING_RETIRE_AFTER = 5
# Min uncovered RS leaders needed to attempt new theme discovery
NEW_THEME_MIN_STOCKS = 3

# Cache yfinance sector lookups
_sector_cache: dict[str, str] = {}


async def _get_sector(ticker: str) -> str:
    if ticker in _sector_cache:
        return _sector_cache[ticker]
    profile = await get_fmp_profile(ticker)
    sector = profile.get("sector") or profile.get("industry") or "Unknown"
    _sector_cache[ticker] = sector
    return sector


async def _get_theme_history(name: str, days: int = 10) -> list[dict]:
    """Get recent daily snapshots for a named theme."""
    pool = await get_pool()
    cutoff = date.today() - timedelta(days=days)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM mi_themes WHERE name = $1 AND theme_date >= $2 ORDER BY theme_date DESC",
            name, cutoff,
        )
        return [dict(r) for r in rows]


async def _count_consecutive_fading(name: str) -> int:
    """Count how many consecutive recent days this theme has been Fading."""
    history = await _get_theme_history(name, days=10)
    count = 0
    for row in history:
        if row["stage"] == "Fading":
            count += 1
        else:
            break
    return count


async def _save_themes(themes: list[dict]) -> None:
    if not themes:
        return
    today = themes[0]["theme_date"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM mi_themes WHERE theme_date = $1", today
        )
        for t in themes:
            await conn.execute("""
                INSERT INTO mi_themes (theme_date, name, stage, score, description, tickers)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, t["theme_date"], t["name"], t["stage"],
                t["score"], t["description"], t["tickers"])


async def _rescore_existing_theme(
    theme: dict,
    stocks_by_ticker: dict[str, dict],
    today: date,
) -> dict | None:
    """
    Re-score an existing theme using today's RS data.
    Returns None if the theme should be retired.
    """
    name = theme["name"]
    tickers = list(theme.get("tickers") or [])

    # Check how many constituent stocks still show strong RS today
    strong_stocks = [t for t in tickers if t in stocks_by_ticker
                     and stocks_by_ticker[t].get("rs_composite", 0) >= THEME_RS_MIN]

    if len(strong_stocks) < THEME_COVERAGE_MIN:
        # Theme is losing its RS base — mark Fading
        fading_days = await _count_consecutive_fading(name)
        if fading_days >= FADING_RETIRE_AFTER:
            logger.info(f"Theme '{name}' retired after {fading_days} fading days")
            return None  # retire it

        return {
            "theme_date": today,
            "name": name,
            "stage": "Fading",
            "score": max(0.0, (theme.get("score") or 0) * 0.8),
            "description": theme.get("description", ""),
            "tickers": tickers,
        }

    # Momentum score (40%): avg RS composite of strong constituents
    rs_scores = [stocks_by_ticker[t].get("rs_composite", 0) for t in strong_stocks]
    momentum = sum(rs_scores) / len(rs_scores)
    momentum_score = min(momentum / 100 * 40, 40)

    # Breadth score (30%): distinct sectors
    sectors = set(stocks_by_ticker[t].get("sector", "Unknown") for t in strong_stocks if t in stocks_by_ticker)
    breadth_score = min(len(sectors) * 10, 30)

    # News confirmation (30%)
    news_score = 0
    try:
        results = await search_news_tavily(f"{name} stocks sector momentum 2026")
        if results:
            news_score = min(len(results) * 6, 30)
    except Exception:
        pass

    total_score = round(momentum_score + breadth_score + news_score, 1)
    prev_score = theme.get("score") or 0

    # Lifecycle
    history = await _get_theme_history(name, days=7)
    age_days = len(history)
    delta = total_score - prev_score

    if delta > 3:
        stage = "Accelerating"
    elif delta < -5:
        stage = "Fading"
    elif age_days >= 5 and total_score >= 50:
        stage = "Mainstream"
    else:
        stage = theme.get("stage", "Nascent")
        if stage == "Fading" and delta >= 0:
            stage = "Accelerating"  # recovering

    return {
        "theme_date": today,
        "name": name,
        "stage": stage,
        "score": total_score,
        "description": theme.get("description", ""),
        "tickers": list(set(tickers) | set(strong_stocks)),  # keep known + add strong
    }


_THEME_DISCOVERY_TOOL = {
    "name": "report_themes",
    "description": "Report newly discovered investment themes from RS leader stocks.",
    "input_schema": {
        "type": "object",
        "properties": {
            "themes": {
                "type": "array",
                "description": "List of newly discovered themes. Empty array if none found.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Specific theme name e.g. 'Edge AI Inference', not 'Technology'",
                        },
                        "thesis": {
                            "type": "string",
                            "description": "2-3 sentences on what's driving this theme and why now.",
                        },
                        "tickers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ticker symbols belonging to this theme (min 2).",
                        },
                    },
                    "required": ["name", "thesis", "tickers"],
                },
            }
        },
        "required": ["themes"],
    },
}


async def _discover_new_themes(
    uncovered_stocks: list[dict],
    existing_themes: list[dict],
) -> list[dict]:
    """
    Ask Claude to identify new themes from uncovered RS leaders.
    Uses structured tool use — output is schema-guaranteed, no JSON parsing.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    stock_lines = "\n".join(
        f"- {s['ticker']} (RS {s.get('rs_composite', 0):.0f}, rank #{s.get('rs_rank', '?')}, sector: {s.get('sector', 'Unknown')})"
        for s in uncovered_stocks
    )

    existing_block = ""
    if existing_themes:
        existing_lines = "\n".join(
            f"- {t['name']} [{t.get('stage')}] (score {t.get('score', 0):.0f}): {', '.join(t.get('tickers') or [])}"
            for t in existing_themes
        )
        existing_block = f"\nEXISTING ACTIVE THEMES (for context — do NOT re-create these):\n{existing_lines}\n"

    prompt = f"""You are a market intelligence analyst using Marios Stamatoudis's theme discovery methodology.

Themes emerge BOTTOM-UP from price action. You're discovering what the market is rotating into.
{existing_block}
NEW RS LEADERS NOT YET IN ANY ACTIVE THEME:
{stock_lines}

Task: Identify NEW distinct investment themes from the uncovered stocks above.
Do NOT recreate or rename existing themes — only identify genuinely new emerging groups.

Rules:
- A theme needs at least 2 stocks from the uncovered list
- Name themes specifically ("Edge AI Inference" not "Technology")
- Each stock should belong to at most one new theme
- Some stocks may not fit any theme — leave them out
- Focus on what the market is pricing in RIGHT NOW based on which stocks move together"""

    try:
        response = client.messages.create(
            model=THEME_MODEL,
            max_tokens=1500,
            tools=[_THEME_DISCOVERY_TOOL],
            tool_choice={"type": "tool", "name": "report_themes"},
            messages=[{"role": "user", "content": prompt}],
        )
        tool_block = next(b for b in response.content if b.type == "tool_use")
        return tool_block.input.get("themes", [])
    except Exception as e:
        logger.error(f"Claude new theme discovery failed: {e}")
        return []


async def _score_new_theme(
    theme: dict,
    stocks_by_ticker: dict[str, dict],
    today: date,
) -> dict:
    """Score a newly discovered theme."""
    tickers = theme.get("tickers", [])

    rs_scores = [stocks_by_ticker[t].get("rs_composite", 0) for t in tickers if t in stocks_by_ticker]
    momentum = (sum(rs_scores) / len(rs_scores)) if rs_scores else 0
    momentum_score = min(momentum / 100 * 40, 40)

    sectors = set(stocks_by_ticker[t].get("sector", "Unknown") for t in tickers if t in stocks_by_ticker)
    breadth_score = min(len(sectors) * 10, 30)

    news_score = 0
    try:
        results = await search_news_tavily(f"{theme['name']} stocks sector momentum 2026")
        if results:
            news_score = min(len(results) * 6, 30)
    except Exception:
        pass

    return {
        "theme_date": today,
        "name": theme["name"],
        "stage": "Nascent",
        "score": round(momentum_score + breadth_score + news_score, 1),
        "description": theme.get("thesis", ""),
        "tickers": tickers,
    }


async def run_theme_engine(trade_date: date | None = None) -> list[dict]:
    """
    Run the full theme update cycle:
    1. Re-score existing active themes
    2. Discover new themes from uncovered RS leaders
    3. Persist results
    """
    today = trade_date or date.today()
    today_str = today.strftime("%Y-%m-%d")

    logger.info("Theme engine: fetching top RS stocks...")
    leaders = await get_rs_leaders(today_str, limit=60)

    if not leaders:
        logger.warning("Theme engine: no RS data — run RS engine first")
        return []

    # Enrich with sector data
    logger.info(f"Theme engine: enriching {len(leaders)} stocks with sector data...")
    for stock in leaders:
        if not stock.get("sector"):
            stock["sector"] = await _get_sector(stock["ticker"])
            await asyncio.sleep(0.2)

    stocks_by_ticker = {s["ticker"]: s for s in leaders}

    # --- Step 1: Re-score existing themes ---
    existing = await get_active_themes()
    logger.info(f"Theme engine: re-scoring {len(existing)} existing themes...")

    updated_themes: list[dict] = []
    covered_tickers: set[str] = set()

    for theme in existing:
        result = await _rescore_existing_theme(theme, stocks_by_ticker, today)
        if result is not None:
            updated_themes.append(result)
            if result["stage"] != "Fading":
                covered_tickers.update(result.get("tickers") or [])
        await asyncio.sleep(1)  # Tavily rate limit

    # --- Step 2: Find uncovered RS leaders ---
    uncovered = [
        s for s in leaders[:40]
        if s["ticker"] not in covered_tickers
        and s.get("rs_composite", 0) >= THEME_RS_MIN
    ]
    logger.info(f"Theme engine: {len(uncovered)} uncovered RS leaders for new theme discovery")

    # --- Step 3: Discover new themes ---
    new_raw: list[dict] = []
    if len(uncovered) >= NEW_THEME_MIN_STOCKS:
        new_raw = await _discover_new_themes(uncovered, updated_themes)
        logger.info(f"Theme engine: {len(new_raw)} new themes discovered")

    new_themes: list[dict] = []
    for raw in new_raw:
        scored = await _score_new_theme(raw, stocks_by_ticker, today)
        new_themes.append(scored)
        await asyncio.sleep(1)

    # --- Step 4: Merge, sort, persist ---
    all_themes = updated_themes + new_themes
    all_themes.sort(key=lambda t: t["score"], reverse=True)

    if all_themes:
        await _save_themes(all_themes)

    logger.info(
        f"Theme engine complete: {len(updated_themes)} updated, {len(new_themes)} new, "
        f"{len(existing) - len(updated_themes)} retired — {today_str}"
    )
    return all_themes


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
