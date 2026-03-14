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
from agents.market_intelligence.db import (
    upsert_stock_score,
    get_active_tracked_stocks,
    upsert_tracked_stock,
    mark_tracked_stock_weak,
    get_pool,
    _to_date,
)
from agents.market_intelligence.universe import UNIVERSE

# RS composite threshold below which a stock is considered "weak" (bottom 40%)
RS_WEAK_THRESHOLD = 40.0
# Top N leaders to add/refresh in tracked stocks after each run
RS_LEADER_CUTOFF = 50

logger = logging.getLogger(__name__)


async def _fetch_closes(ticker: str, from_date: str, to_date: str) -> dict[str, float]:
    """Fetch daily closes for a ticker. Returns {date_str: close}."""
    from datetime import datetime, timezone
    bars = await get_index_history(ticker, from_date, to_date)
    result = {}
    for b in bars:
        if "c" in b and "t" in b:
            d = datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date()
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


def _compute_sma(closes: dict[str, float], n: int) -> Optional[float]:
    """Compute simple moving average of last N trading days."""
    sorted_closes = sorted(closes.items())  # [(date_str, close), ...]
    if len(sorted_closes) < n:
        return None
    last_n = [c for _, c in sorted_closes[-n:]]
    return round(sum(last_n) / n, 4)


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

    # Expand universe with actively tracked stocks (RS leaders from prior days)
    tracked = await get_active_tracked_stocks()
    full_universe = list(dict.fromkeys(UNIVERSE + tracked))  # deduplicate, preserve order
    if len(tracked) > 0:
        logger.info(f"RS Engine: base universe {len(UNIVERSE)}, +{len(tracked)} tracked = {len(full_universe)} total")

    logger.info(f"RS Engine: fetching {len(full_universe)} stocks from {from_date} to {today_str}")
    logger.info(f"Lookback dates: 1M={date_1m}, 3M={date_3m}, 6M={date_6m}")

    # Fetch price history for each stock (1 Polygon call per stock, rate-limited)
    stock_data: list[dict] = []
    for i, ticker in enumerate(full_universe):
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
                "sma_10": _compute_sma(closes, 10),
                "sma_20": _compute_sma(closes, 20),
                "sma_50": _compute_sma(closes, 50),
            })

            if (i + 1) % 10 == 0:
                logger.info(f"RS Engine: {i + 1}/{len(full_universe)} stocks fetched")

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
            "sma_10": s.get("sma_10"),
            "sma_20": s.get("sma_20"),
            "sma_50": s.get("sma_50"),
            "close": s["current"],
            "raw_1m": round(s["rs_1m_raw"], 2) if s.get("rs_1m_raw") is not None else None,
            "raw_3m": round(s["rs_3m_raw"], 2) if s.get("rs_3m_raw") is not None else None,
            "raw_6m": round(s["rs_6m_raw"], 2) if s.get("rs_6m_raw") is not None else None,
        }
        await upsert_stock_score(db_record)

    # Update tracked stocks: add leaders, mark weak stocks
    scored_map = {
        s["ticker"]: round(composite_ranks[i] or 0, 1)
        for i, s in enumerate(stock_data)
    }
    tracked_set = set(tracked)
    added_to_tracking = 0

    for i, s in enumerate(stock_data):
        rs = round(composite_ranks[i] or 0, 1)
        rank = rank_position[i]
        ticker = s["ticker"]
        if rank <= RS_LEADER_CUTOFF:
            await upsert_tracked_stock(ticker, today, rs)
            added_to_tracking += 1
        elif ticker in tracked_set and rs < RS_WEAK_THRESHOLD:
            await mark_tracked_stock_weak(ticker, today)

    logger.info(
        f"RS Engine complete: scored {len(stock_data)} stocks for {today_str} "
        f"({added_to_tracking} tracked leaders)"
    )
    return {"stocks_scored": len(stock_data), "date": today_str}


async def score_single_ticker(ticker: str, trade_date: date | None = None) -> dict:
    """
    Score one ticker on demand against today's existing RS distribution.
    1 Polygon API call. Ranks the ticker's raw returns against stored raw returns
    from today's full run. Requires at least one full RS run to have completed.
    """
    today = trade_date or date.today()
    today_str = today.strftime("%Y-%m-%d")
    from_date = (today - timedelta(days=200)).strftime("%Y-%m-%d")

    date_1m = trading_date_n_months_ago(1)
    date_3m = trading_date_n_months_ago(3)
    date_6m = trading_date_n_months_ago(6)

    ticker = ticker.upper()
    logger.info(f"Single-ticker RS score: {ticker}")

    closes = await _fetch_closes(ticker, from_date, today_str)
    if not closes:
        return {"error": f"No price data found for {ticker}"}

    current = _closest_close(closes, today_str)
    if not current:
        return {"error": f"No recent close for {ticker}"}

    raw_1m = _pct_return(current, _closest_close(closes, date_1m))
    raw_3m = _pct_return(current, _closest_close(closes, date_3m))
    raw_6m = _pct_return(current, _closest_close(closes, date_6m))

    # Load today's raw return distribution for proper percentile ranking
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, raw_1m, raw_3m, raw_6m FROM mi_stock_scores WHERE score_date = $1 AND raw_1m IS NOT NULL",
            _to_date(today_str),
        )

    existing = [dict(r) for r in rows]
    if not existing:
        return {"error": "No raw return data for today — run a full data refresh first, then retry"}

    n = len(existing)
    dist_1m = [r["raw_1m"] for r in existing if r["raw_1m"] is not None]
    dist_3m = [r["raw_3m"] for r in existing if r["raw_3m"] is not None]
    dist_6m = [r["raw_6m"] for r in existing if r["raw_6m"] is not None]

    def _pct_rank(val: Optional[float], dist: list[float]) -> float:
        if val is None or not dist:
            return 50.0
        return round(sum(1 for x in dist if x < val) / len(dist) * 100, 1)

    r1 = raw_1m or 0.0
    r3 = raw_3m or r1
    r6 = raw_6m or r1

    rank_1m = _pct_rank(r1, dist_1m)
    rank_3m = _pct_rank(r3, dist_3m)
    rank_6m = _pct_rank(r6, dist_6m)
    composite = round(0.40 * rank_1m + 0.30 * rank_3m + 0.30 * rank_6m, 1)

    # Rank position vs universe
    async with pool.acquire() as conn:
        existing_composites = [r["rs_composite"] async for r in await conn.cursor(
            "SELECT rs_composite FROM mi_stock_scores WHERE score_date = $1 AND rs_composite IS NOT NULL",
            _to_date(today_str),
        )]
    rank_pos = sum(1 for c in existing_composites if c > composite) + 1

    sma_10 = _compute_sma(closes, 10)
    sma_20 = _compute_sma(closes, 20)
    sma_50 = _compute_sma(closes, 50)

    db_record = {
        "ticker": ticker,
        "score_date": today,
        "rs_1m": rank_1m,
        "rs_3m": rank_3m,
        "rs_6m": rank_6m,
        "rs_composite": composite,
        "rs_rank": rank_pos,
        "sector": None,
        "adv_20": None,
        "market_cap": None,
        "sma_10": sma_10,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "close": current,
        "raw_1m": round(r1, 2),
        "raw_3m": round(r3, 2),
        "raw_6m": round(r6, 2),
    }
    await upsert_stock_score(db_record)
    await upsert_tracked_stock(ticker, today, composite)

    ma_lines = []
    for sma, label in [(sma_10, "10MA"), (sma_20, "20MA"), (sma_50, "50MA")]:
        if sma:
            pct = (current / sma - 1) * 100
            sign = "+" if pct >= 0 else ""
            ma_lines.append(f"{label} {sign}{pct:.1f}%")

    logger.info(f"Single-ticker score: {ticker} composite={composite} rank=#{rank_pos}/{n+1}")
    return {
        "ticker": ticker,
        "rs_composite": composite,
        "rs_rank": rank_pos,
        "universe_size": n + 1,
        "rs_1m": rank_1m,
        "rs_3m": rank_3m,
        "rs_6m": rank_6m,
        "raw_1m": round(r1, 2),
        "raw_3m": round(r3, 2),
        "raw_6m": round(r6, 2),
        "close": current,
        "sma_10": sma_10,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "ma_context": ma_lines,
    }


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
