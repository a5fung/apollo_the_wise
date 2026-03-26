"""
Relative Strength Engine — Full Universe.

Calculates 1M / 3M / 6M momentum scores for ALL US stocks using stored
daily closes from mi_daily_closes (populated via grouped daily endpoint).

RS composite = 40% × 1M rank + 30% × 3M rank + 30% × 6M rank
Final RS score = percentile rank 0-100 across full universe (~8K+ stocks).

Nightly flow:
1. ingest_daily() — fetch grouped daily for today (1 Polygon call, all stocks)
2. run_rs_engine() — read from mi_daily_closes, rank all stocks, store results

Bootstrap: bootstrap_daily_closes() fetches ~200 days of history on first run.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.collector import (
    get_grouped_daily,
    get_index_history,
    prev_trading_days,
    trading_date_n_months_ago,
)
from agents.market_intelligence.db import (
    get_daily_closes_all,
    get_daily_closes_count,
    ingest_daily_closes,
    upsert_stock_score,
    upsert_stock_scores_batch,
    get_active_tracked_stocks,
    upsert_tracked_stock,
    upsert_tracked_stocks_batch,
    mark_tracked_stock_weak,
    mark_tracked_stocks_weak_batch,
    get_pool,
    _to_date,
)

# RS composite threshold below which a stock is considered "weak" (bottom 40%)
RS_WEAK_THRESHOLD = 40.0
# Top N leaders to add/refresh in tracked stocks after each run
RS_LEADER_CUTOFF = 50
# Minimum price to score — filters penny stocks
MIN_PRICE = 5.0
# Maximum ticker length — filters warrants/units
MAX_TICKER_LEN = 5
# Max 1-day return before flagging as corporate action (reverse split, etc.)
# Real stocks rarely move >100% in a day; reverse splits create 200-5000% phantom jumps
MAX_1D_RETURN = 1.0  # 100%
# Max multi-month return (in %) before flagging as reverse split with stale history.
# Real stocks rarely 4x in 6 months; reverse splits create phantom 500-5000% returns
# because Polygon adjusts recent prices but older history may lag.
MAX_PERIOD_RETURN = 300.0  # 300% (i.e., 4x price increase)

# Tickers to exclude from RS scoring entirely (manual overrides).
RS_EXCLUDE_TICKERS: set[str] = set()

# Volatility crush detection — auto-detects M&A pinning, halts, etc.
# If recent volatility (10d) is < 25% of historical volatility (50d),
# and the stock has RS ≥ 80, it's likely pinned at a deal price.
VOL_CRUSH_THRESHOLD = 0.25  # ratio of recent/historical vol
VOL_CRUSH_RS_MIN = 80       # only flag high-RS stocks (low-RS with low vol = just boring)

logger = logging.getLogger(__name__)


def _closest_close(closes: dict[str, float], target_date: str) -> Optional[float]:
    """Get close on or just before target_date (handles holidays/weekends)."""
    if target_date in closes:
        return closes[target_date]
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
    sorted_closes = sorted(closes.items())
    if len(sorted_closes) < n:
        return None
    last_n = [c for _, c in sorted_closes[-n:]]
    return round(sum(last_n) / n, 4)


def _volatility_ratio(closes: dict[str, float], short: int = 10, long: int = 50) -> Optional[float]:
    """
    Ratio of recent vs historical close-to-close volatility.
    Uses median absolute deviation (MAD) — robust to outlier gap days
    that inflate stdev and cause false positives on normal stocks.
    < 0.25 = volatility crushed (M&A pinning, halt, etc.)
    ~ 1.0  = normal
    Returns None if insufficient data.
    """
    sorted_prices = [c for _, c in sorted(closes.items()) if c and c > 0]
    if len(sorted_prices) < long + 1:
        return None
    # Daily returns as absolute values
    abs_returns = [abs(sorted_prices[i] / sorted_prices[i - 1] - 1.0)
                   for i in range(1, len(sorted_prices))]
    recent = abs_returns[-short:]
    historical = abs_returns[-long:]
    import statistics
    mad_recent = statistics.median(recent)
    mad_hist = statistics.median(historical)
    if mad_hist < 0.0001:
        return None
    return mad_recent / mad_hist


def _percentile_ranks(values: list[Optional[float]]) -> list[Optional[float]]:
    """Convert raw values to percentile ranks (0-100). None stays None."""
    valid = [(i, v) for i, v in enumerate(values) if v is not None]
    if not valid:
        return values[:]
    sorted_vals = sorted(valid, key=lambda x: x[1])
    n = len(sorted_vals)
    rank_map = {i: round(pos / max(n - 1, 1) * 100.0, 1) for pos, (i, _) in enumerate(sorted_vals)}
    return [rank_map.get(i) for i in range(len(values))]


async def ingest_daily(trade_date: date | None = None) -> int:
    """
    Fetch grouped daily data for one date and store in mi_daily_closes.
    Returns number of tickers stored.
    """
    td = trade_date or et_today()
    td_str = td.strftime("%Y-%m-%d")

    # Never ingest weekend data — markets are closed
    if td.weekday() >= 5:
        logger.info(f"Skipping ingestion for {td_str} (weekend)")
        return 0

    # Skip if already ingested
    existing = await get_daily_closes_count(td)
    if existing > 1000:
        logger.info(f"Daily closes already ingested for {td_str}: {existing} tickers")
        return existing

    logger.info(f"Ingesting grouped daily for {td_str}...")
    bars = await get_grouped_daily(td_str)
    if not bars:
        logger.warning(f"No grouped daily data for {td_str} — market may have been closed")
        return 0

    count = await ingest_daily_closes(td, bars)
    logger.info(f"Ingested {count} tickers for {td_str}")
    return count


async def ingest_from_snapshot(trade_date: date | None = None) -> int:
    """
    Fallback ingestion using Polygon snapshot endpoint (works on Starter for same-day data).
    Converts snapshot format to daily close format and stores in mi_daily_closes.
    """
    from agents.market_intelligence.collector import get_snapshot_all

    td = trade_date or et_today()
    td_str = td.strftime("%Y-%m-%d")

    # Never ingest weekend data
    if td.weekday() >= 5:
        logger.info(f"Skipping snapshot ingestion for {td_str} (weekend)")
        return 0

    # Skip if already ingested
    existing = await get_daily_closes_count(td)
    if existing > 1000:
        logger.info(f"Daily closes already ingested for {td_str}: {existing} tickers")
        return existing

    logger.info(f"Ingesting from snapshot for {td_str}...")
    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning(f"No snapshot data for {td_str}")
        return 0

    # Convert snapshot format to grouped-daily format expected by ingest_daily_closes
    bars: dict[str, dict] = {}
    for ticker, snap in snapshots.items():
        day = snap.get("day", {})
        if not day or not day.get("c"):
            continue
        bars[ticker] = {
            "T": ticker,
            "o": day.get("o", 0),
            "h": day.get("h", 0),
            "l": day.get("l", 0),
            "c": day["c"],
            "v": day.get("v", 0),
            "vw": day.get("vw", 0),
        }

    if not bars:
        logger.warning(f"Snapshot had no usable day data for {td_str}")
        return 0

    count = await ingest_daily_closes(td, bars)
    logger.info(f"Ingested {count} tickers from snapshot for {td_str}")
    return count


async def bootstrap_daily_closes(days: int = 200) -> int:
    """
    Backfill mi_daily_closes with historical grouped daily data.
    Fetches one day at a time (1 Polygon call each).
    Run once on setup, then daily ingestion keeps it current.
    """
    today = et_today()
    total_ingested = 0

    # Get approximate trading days going back
    trading_dates = prev_trading_days(days, today)
    trading_dates.reverse()  # oldest first

    for td in trading_dates:
        existing = await get_daily_closes_count(td)
        if existing > 1000:
            continue  # already have this day

        td_str = td.strftime("%Y-%m-%d")
        bars = await get_grouped_daily(td_str)
        if not bars:
            continue

        count = await ingest_daily_closes(td, bars)
        total_ingested += count
        logger.info(f"Bootstrap: {td_str} — {count} tickers")

    logger.info(f"Bootstrap complete: {total_ingested} total rows ingested")
    return total_ingested


async def run_rs_engine(trade_date: date | None = None) -> dict:
    """
    Calculate RS scores for the full universe from stored daily closes.
    Stores results in mi_stock_scores.
    Returns summary dict.
    """
    today = trade_date or et_today()
    today_str = today.strftime("%Y-%m-%d")
    from_date = today - timedelta(days=200)

    date_1m = trading_date_n_months_ago(1)
    date_3m = trading_date_n_months_ago(3)
    date_6m = trading_date_n_months_ago(6)

    logger.info(f"RS Engine: loading daily closes from DB ({from_date} to {today_str})...")

    # Load common stock tickers to filter out ETFs, warrants, SPACs, etc.
    from agents.market_intelligence.db import get_common_stock_tickers
    cs_tickers = await get_common_stock_tickers()

    # Load all daily closes from DB (one query, all tickers)
    all_closes = await get_daily_closes_all(from_date, today)

    if not all_closes:
        logger.error("No daily closes in DB — run bootstrap_daily_closes() first")
        return {"stocks_scored": 0, "date": today_str, "error": "No daily closes — run bootstrap first"}

    logger.info(f"RS Engine: loaded {len(all_closes)} tickers from DB")

    # Compute RS for each ticker
    stock_data: list[dict] = []
    for ticker, closes in all_closes.items():
        # Skip excluded tickers (M&A targets, etc.)
        if ticker in RS_EXCLUDE_TICKERS:
            continue
        # Skip non-common-stock securities (ETFs, warrants, SPACs, etc.)
        if cs_tickers and ticker not in cs_tickers:
            continue
        # Skip long symbols and penny stocks
        if len(ticker) > MAX_TICKER_LEN:
            continue

        current = _closest_close(closes, today_str)
        if not current or current < MIN_PRICE:
            continue

        # Detect reverse splits: if today's close is >100% above yesterday's,
        # the price history is inconsistent (Polygon adjusts latest day only).
        # Skip these tickers entirely — they'll re-enter once history normalizes.
        sorted_dates = sorted(closes.keys(), reverse=True)
        if len(sorted_dates) >= 2:
            prev_close = closes[sorted_dates[1]]
            if prev_close and prev_close > 0:
                day_return = (current / prev_close) - 1.0
                if day_return > MAX_1D_RETURN:
                    continue

        price_1m = _closest_close(closes, date_1m)
        price_3m = _closest_close(closes, date_3m)
        price_6m = _closest_close(closes, date_6m)

        # Detect reverse splits with stale history: if any period return is absurdly high,
        # the price history is inconsistent (e.g., FUBO reverse split makes 6M look +500%).
        raw_1m = _pct_return(current, price_1m)
        raw_3m = _pct_return(current, price_3m)
        raw_6m = _pct_return(current, price_6m)
        if any(r is not None and r > MAX_PERIOD_RETURN for r in (raw_1m, raw_3m, raw_6m)):
            continue

        stock_data.append({
            "ticker": ticker,
            "current": current,
            "rs_1m_raw": raw_1m,
            "rs_3m_raw": raw_3m,
            "rs_6m_raw": raw_6m,
            "sma_10": _compute_sma(closes, 10),
            "sma_20": _compute_sma(closes, 20),
            "sma_40": _compute_sma(closes, 40),
            "sma_50": _compute_sma(closes, 50),
            "vol_ratio": _volatility_ratio(closes),
        })

    if not stock_data:
        return {"stocks_scored": 0, "date": today_str, "error": "No valid stock data"}

    # Clear stale scores for this date before writing new ones.
    # Prevents filtered-out stocks (reverse splits, non-CS) from persisting.
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM mi_stock_scores WHERE score_date = $1", today)
    logger.info(f"RS Engine: cleared old scores for {today_str}")

    logger.info(f"RS Engine: computing ranks for {len(stock_data)} stocks")

    # Rank each period across the FULL universe
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

    # Detect M&A / deal-price pinning via volatility crush.
    # High-RS stocks with crushed volatility are likely trading at a fixed deal price.
    # Zero out their composite so they don't appear as RS leaders.
    vol_crush_count = 0
    for i, s in enumerate(stock_data):
        vr = s.get("vol_ratio")
        comp = composite_ranks[i] or 0
        if vr is not None and vr < VOL_CRUSH_THRESHOLD and comp >= VOL_CRUSH_RS_MIN:
            logger.info(
                f"Vol crush: {s['ticker']} RS {comp:.0f} vol_ratio {vr:.2f} — likely M&A pinning, zeroing RS"
            )
            composite_ranks[i] = 0
            rs_1m_ranks[i] = 0
            rs_3m_ranks[i] = 0
            rs_6m_ranks[i] = 0
            vol_crush_count += 1
    if vol_crush_count:
        logger.info(f"RS Engine: {vol_crush_count} stocks zeroed for volatility crush (likely M&A)")

    # Compute ADV-20 from daily closes for each stock
    from agents.market_intelligence.db import get_adv_from_daily_closes
    adv_map = await get_adv_from_daily_closes(today)

    # Batch upsert all scores
    db_records = [
        {
            "ticker": s["ticker"],
            "score_date": today,
            "rs_1m": round(rs_1m_ranks[i] or 0, 1),
            "rs_3m": round(rs_3m_ranks[i] or 0, 1),
            "rs_6m": round(rs_6m_ranks[i] or 0, 1),
            "rs_composite": round(composite_ranks[i] or 0, 1),
            "rs_rank": rank_position[i],
            "sector": None,
            "adv_20": adv_map.get(s["ticker"]),
            "market_cap": None,
            "sma_10": s.get("sma_10"),
            "sma_20": s.get("sma_20"),
            "sma_40": s.get("sma_40"),
            "sma_50": s.get("sma_50"),
            "close": s["current"],
            "raw_1m": round(s["rs_1m_raw"], 2) if s.get("rs_1m_raw") is not None else None,
            "raw_3m": round(s["rs_3m_raw"], 2) if s.get("rs_3m_raw") is not None else None,
            "raw_6m": round(s["rs_6m_raw"], 2) if s.get("rs_6m_raw") is not None else None,
        }
        for i, s in enumerate(stock_data)
    ]

    # Insert in chunks to avoid memory issues with 8K+ records
    CHUNK = 2000
    for start in range(0, len(db_records), CHUNK):
        await upsert_stock_scores_batch(db_records[start:start + CHUNK])
    logger.info(f"RS Engine: stored {len(db_records)} scores")

    # Update tracked stocks: add leaders, mark weak
    tracked = await get_active_tracked_stocks()
    tracked_set = set(tracked)
    leader_records: list[tuple[str, date, float]] = []
    weak_records: list[tuple[str, date]] = []

    for i, s in enumerate(stock_data):
        rs = round(composite_ranks[i] or 0, 1)
        rank = rank_position[i]
        ticker = s["ticker"]
        if rank <= RS_LEADER_CUTOFF:
            leader_records.append((ticker, today, rs))
        elif ticker in tracked_set and rs < RS_WEAK_THRESHOLD:
            weak_records.append((ticker, today))

    await upsert_tracked_stocks_batch(leader_records)
    await mark_tracked_stocks_weak_batch(weak_records)

    logger.info(
        f"RS Engine complete: scored {len(stock_data)} stocks for {today_str} "
        f"({len(leader_records)} tracked leaders)"
    )
    return {"stocks_scored": len(stock_data), "date": today_str}


async def score_single_ticker(ticker: str, trade_date: date | None = None) -> dict:
    """
    Score one ticker on demand against today's existing RS distribution.
    1 Polygon API call. Ranks the ticker's raw returns against stored raw returns
    from today's full run. Requires at least one full RS run to have completed.
    """
    today = trade_date or et_today()
    today_str = today.strftime("%Y-%m-%d")
    from_date = (today - timedelta(days=200)).strftime("%Y-%m-%d")

    date_1m = trading_date_n_months_ago(1)
    date_3m = trading_date_n_months_ago(3)
    date_6m = trading_date_n_months_ago(6)

    ticker = ticker.upper()
    logger.info(f"Single-ticker RS score: {ticker}")

    # Try DB first, fall back to API
    from agents.market_intelligence.db import get_daily_closes_all as _get_closes
    closes_map = await _get_closes(today - timedelta(days=200), today)
    closes = closes_map.get(ticker, {})
    if not closes:
        # Fallback: fetch from Polygon
        from agents.market_intelligence.collector import get_index_history
        from datetime import datetime, timezone
        bars = await get_index_history(ticker, from_date, today_str)
        for b in bars:
            if "c" in b and "t" in b:
                d = datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date()
                closes[d.strftime("%Y-%m-%d")] = b["c"]

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
    sma_40 = _compute_sma(closes, 40)
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
        "sma_40": sma_40,
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
