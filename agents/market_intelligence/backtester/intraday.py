"""Polygon 1-min bar fetching with DB cache."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from agents.market_intelligence.collector import _polygon_get
from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)


async def get_intraday_bars(ticker: str, trade_date: date) -> list[dict]:
    """
    Get 1-min bars for a ticker on a trading day (9:30-16:00 ET).
    Checks DB cache first, fetches from Polygon if missing.
    Returns list of dicts with keys: bar_time, open, high, low, close, volume, vwap
    sorted by bar_time ascending.
    """
    cached = await _get_cached_bars(ticker, trade_date)
    if cached:
        return cached

    bars = await _fetch_polygon_bars(ticker, trade_date)
    if bars:
        await _cache_bars(ticker, bars)
    return bars


async def _get_cached_bars(ticker: str, trade_date: date) -> list[dict]:
    """Check mi_intraday_bars cache for existing data."""
    pool = await get_pool()
    # Build ET date range for the trading day
    day_start = datetime.combine(trade_date, MARKET_OPEN, tzinfo=ET)
    day_end = datetime.combine(trade_date, MARKET_CLOSE, tzinfo=ET)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT bar_time, open, high, low, close, volume, vwap
            FROM mi_intraday_bars
            WHERE ticker = $1
              AND bar_time >= $2
              AND bar_time <= $3
            ORDER BY bar_time ASC
        """, ticker, day_start, day_end)

    if not rows:
        return []

    return [dict(r) for r in rows]


async def _fetch_polygon_bars(ticker: str, trade_date: date) -> list[dict]:
    """Fetch 1-min bars from Polygon for a single trading day."""
    from_str = trade_date.strftime("%Y-%m-%d")
    to_str = from_str  # single day

    try:
        data = await _polygon_get(
            f"/v2/aggs/ticker/{ticker}/range/1/minute/{from_str}/{to_str}",
            {"adjusted": "true", "sort": "asc", "limit": 5000},
        )
    except Exception as e:
        logger.warning(f"Intraday fetch failed for {ticker} on {trade_date}: {e}")
        return []

    results = data.get("results", [])
    if not results:
        return []

    bars = []
    for r in results:
        # Polygon returns Unix ms timestamps
        ts = r.get("t", 0)
        bar_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).astimezone(ET)

        # Filter to market hours only
        bar_time = bar_dt.time()
        if bar_time < MARKET_OPEN or bar_time >= MARKET_CLOSE:
            continue

        bars.append({
            "bar_time": bar_dt,
            "open": r["o"],
            "high": r["h"],
            "low": r["l"],
            "close": r["c"],
            "volume": int(r.get("v", 0)),
            "vwap": r.get("vw"),
        })

    logger.debug(f"Fetched {len(bars)} intraday bars for {ticker} on {trade_date}")
    return bars


async def _cache_bars(ticker: str, bars: list[dict]) -> None:
    """Write bars to mi_intraday_bars cache."""
    if not bars:
        return
    pool = await get_pool()
    records = [
        (ticker, b["bar_time"], b["open"], b["high"], b["low"],
         b["close"], b["volume"], b.get("vwap"))
        for b in bars
    ]
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_intraday_bars (ticker, bar_time, open, high, low, close, volume, vwap)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (ticker, bar_time) DO NOTHING
        """, records)


async def ensure_intraday_table() -> None:
    """Create the mi_intraday_bars table if it doesn't exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_intraday_bars (
                ticker TEXT NOT NULL,
                bar_time TIMESTAMPTZ NOT NULL,
                open FLOAT NOT NULL,
                high FLOAT NOT NULL,
                low FLOAT NOT NULL,
                close FLOAT NOT NULL,
                volume BIGINT NOT NULL,
                vwap FLOAT,
                PRIMARY KEY (ticker, bar_time)
            );
            CREATE INDEX IF NOT EXISTS idx_intraday_bars_ticker
                ON mi_intraday_bars(ticker);
        """)
