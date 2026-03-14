"""
Relative Strength Engine.

Calculates 1M / 3M / 6M momentum scores using individual Polygon ticker
aggregates (free tier compatible). Uses a pre-defined universe of ~150 stocks.

RS composite = 40% × 1M rank + 30% × 3M rank + 30% × 6M rank
Final RS score = percentile rank 0-100 across universe.

Nightly run: ~150 stocks × 1 call each = ~30 min at free tier rate limit.
Run at 6 AM ET so it completes before the 7 AM briefing.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from agents.market_intelligence.collector import get_index_history, trading_date_n_months_ago
from agents.market_intelligence.db import upsert_stock_score
from agents.market_intelligence.universe import UNIVERSE

logger = logging.getLogger(__name__)


async def _fetch_closes(ticker: str, from_date: str, to_date: str) -> dict[str, float]:
    """Fetch daily closes for a ticker. Returns {date_str: close}."""
    bars = await get_index_history(ticker, from_date, to_date)
    result = {}
    for b in bars:
        if "c" in b and "t" in b:
            # Polygon returns timestamp in ms
            d = date.fromtimestamp(b["t"] / 1000)
            result[d.strftime("%Y-%m-%d")] = b["c"]
    return result


def _closest_close(closes: dict[str, float], target_date: str) -> Optional[float]:
    """Get close on or just before target_date (handles holidays/weekends)."""
    if target_date in closes:
        return closes[target_date]
    # Walk back up to 5 days to find nearest trading day
    d = date.fromisoformat(target_date)
    for _ in range(5):
        d -= timedelta(days=1)
        key = d.strftime("%Y-%m-%d")
        if key in closes:
            return closes[key]
    return None


def _pct_return(current: float, past: Optional[float]) -> Optional[float]:
    if not past or past <= 0 or not current:
        return None
    return (current - past) / past * 100.0


def _percentile_ranks(values: list[Optional[float]]) -> list[Optional[float]]:
    """Convert raw values to percentile ranks (0-100). None stays None."""
    valid = [(i, v) for i, v in enumerate(values) if v is not None]
    if not valid:
        return values[:]
    sorted_vals = sorted(valid, key=lambda x: x[1])
    n = len(sorted_vals)
    rank_map = {i: round(pos / max(n - 1, 1) * 100.0, 1) for pos, (i, _) in enumerate(sorted_vals)}
    return [rank_map.get(i) for i in range(len(values))]


async def run_rs_engine(trade_date: date | None = None) -> dict:
    """
    Calculate RS scores for the configured universe.
    Stores results in mi_stock_scores.
    Returns summary dict.
    """
    today = trade_date or date.today()
    today_str = today.strftime("%Y-%m-%d")
    from_date = (today - timedelta(days=200)).strftime("%Y-%m-%d")  # 6M+ history

    date_1m = trading_date_n_months_ago(1)
    date_3m = trading_date_n_months_ago(3)
    date_6m = trading_date_n_months_ago(6)

    logger.info(f"RS Engine: fetching {len(UNIVERSE)} stocks from {from_date} to {today_str}")
    logger.info(f"Lookback dates: 1M={date_1m}, 3M={date_3m}, 6M={date_6m}")

    # Fetch price history for each stock (1 Polygon call per stock, rate-limited)
    stock_data: list[dict] = []
    for i, ticker in enumerate(UNIVERSE):
        try:
            closes = await _fetch_closes(ticker, from_date, today_str)
            if not closes:
                continue

            current = _closest_close(closes, today_str)
            price_1m = _closest_close(closes, date_1m)
            price_3m = _closest_close(closes, date_3m)
            price_6m = _closest_close(closes, date_6m)

            if not current:
                continue

            stock_data.append({
                "ticker": ticker,
                "current": current,
                "rs_1m_raw": _pct_return(current, price_1m),
                "rs_3m_raw": _pct_return(current, price_3m),
                "rs_6m_raw": _pct_return(current, price_6m),
            })

            if (i + 1) % 10 == 0:
                logger.info(f"RS Engine: {i + 1}/{len(UNIVERSE)} stocks fetched")

        except Exception as e:
            logger.warning(f"RS fetch failed for {ticker}: {e}")

    if not stock_data:
        return {"stocks_scored": 0, "date": today_str, "error": "No data fetched"}

    logger.info(f"RS Engine: computing ranks for {len(stock_data)} stocks")

    # Rank each period
    rs_1m_vals = [s["rs_1m_raw"] for s in stock_data]
    rs_3m_vals = [s["rs_3m_raw"] for s in stock_data]
    rs_6m_vals = [s["rs_6m_raw"] for s in stock_data]

    rs_1m_ranks = _percentile_ranks(rs_1m_vals)
    rs_3m_ranks = _percentile_ranks(rs_3m_vals)
    rs_6m_ranks = _percentile_ranks(rs_6m_vals)

    # Compute composite rank
    composites = []
    for r1, r3, r6 in zip(rs_1m_ranks, rs_3m_ranks, rs_6m_ranks):
        r1 = r1 or 0
        r3 = r3 or r1
        r6 = r6 or r1
        composites.append(0.40 * r1 + 0.30 * r3 + 0.30 * r6)

    composite_ranks = _percentile_ranks(composites)

    # Sort by composite descending for rank position
    indexed = list(enumerate(composite_ranks))
    indexed.sort(key=lambda x: x[1] or 0, reverse=True)
    rank_position = {orig_idx: pos + 1 for pos, (orig_idx, _) in enumerate(indexed)}

    # Upsert to DB
    for i, s in enumerate(stock_data):
        db_record = {
            "ticker": s["ticker"],
            "score_date": today,
            "rs_1m": round(rs_1m_ranks[i] or 0, 1),
            "rs_3m": round(rs_3m_ranks[i] or 0, 1),
            "rs_6m": round(rs_6m_ranks[i] or 0, 1),
            "rs_composite": round(composite_ranks[i] or 0, 1),
            "rs_rank": rank_position[i],
            "sector": None,
            "adv_20": None,
            "market_cap": None,
        }
        await upsert_stock_score(db_record)

    logger.info(f"RS Engine complete: scored {len(stock_data)} stocks for {today_str}")
    return {"stocks_scored": len(stock_data), "date": today_str}


async def get_top_rs_by_sector(score_date: str, top_n: int = 5) -> dict[str, list[dict]]:
    from agents.market_intelligence.db import get_rs_leaders
    leaders = await get_rs_leaders(score_date, limit=200)
    by_sector: dict[str, list] = {}
    for stock in leaders:
        sector = stock.get("sector") or "Unknown"
        if sector not in by_sector:
            by_sector[sector] = []
        if len(by_sector[sector]) < top_n:
            by_sector[sector].append(stock)
    return by_sector
