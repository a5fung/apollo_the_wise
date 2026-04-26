"""CoinGecko free-tier client — universe, history, categories, macro indicators.

Four roles:
1. /coins/markets       — top-N universe by mcap (1 call/day, returns 250 per page)
2. /coins/{id}/market_chart — historical daily OHLC for backfill + long-tail
3. /coins/categories    — pre-tagged taxonomy (weekly refresh)
4. /global              — total mcap + BTC/ETH dominance (TOTAL3 derived)

Free tier: 30 calls/min, ~10K calls/month. Self-throttle at 2.1s between calls.
Optional `COINGECKO_API_KEY` env var for the free demo key — slightly higher
limits but anonymous works.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date, datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"
_TIMEOUT = httpx.Timeout(20.0)
_THROTTLE_LOCK = asyncio.Lock()
_MIN_INTERVAL_SEC = 2.1  # 30 req/min ceiling -> 2s headroom
_last_call_at: Optional[float] = None


def _headers() -> dict[str, str]:
    key = os.environ.get("COINGECKO_API_KEY")
    return {"x-cg-demo-api-key": key} if key else {}


async def _throttle() -> None:
    global _last_call_at
    async with _THROTTLE_LOCK:
        now = time.monotonic()
        if _last_call_at is not None:
            elapsed = now - _last_call_at
            if elapsed < _MIN_INTERVAL_SEC:
                await asyncio.sleep(_MIN_INTERVAL_SEC - elapsed)
        _last_call_at = time.monotonic()


async def _get(path: str, params: Optional[dict] = None) -> dict | list:
    await _throttle()
    url = f"{_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers()) as client:
        # 429 retry with exponential backoff (Retry-After header respected).
        # 30/min ceiling means category-sync bursts can chain 429s; one retry
        # is insufficient. Three attempts with 2x backoff covers a ~30s rate-limit window.
        delay = 5.0
        for attempt in range(3):
            resp = await client.get(url, params=params or {})
            if resp.status_code != 429:
                break
            retry_after = float(resp.headers.get("Retry-After", str(delay)))
            logger.warning("CoinGecko 429 attempt %d; sleeping %.1fs", attempt + 1, retry_after)
            await asyncio.sleep(retry_after)
            delay *= 2
        resp.raise_for_status()
        return resp.json()


async def get_top_universe(per_page: int = 250, page: int = 1) -> list[dict]:
    """Top-N coins by mcap. One row per coin with id, symbol, name, mcap_rank,
    market_cap, total_volume, current_price."""
    result = await _get("/coins/markets", {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": page,
        "sparkline": "false",
        "price_change_percentage": "24h",
    })
    return result if isinstance(result, list) else []


async def get_market_chart(coin_id: str, days: int = 365) -> dict:
    """Daily OHLC + volume + mcap for a single coin.

    Returns CG's native shape: {prices: [[ts_ms, price], ...], market_caps: [...],
    total_volumes: [...]}. Caller bucketizes into daily bars.

    Free tier: max 365 days. days=365 returns daily granularity automatically.
    """
    result = await _get(f"/coins/{coin_id}/market_chart", {
        "vs_currency": "usd",
        "days": days,
    })
    return result if isinstance(result, dict) else {}


def _bucket_by_utc_date(series: list[list]) -> dict[date, float]:
    """CG returns [[ts_ms, value], ...]. Bucket by UTC date; last entry wins."""
    out: dict[date, float] = {}
    for entry in series or []:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        ts_ms, value = entry[0], entry[1]
        try:
            d = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).date()
            out[d] = float(value) if value is not None else None
        except (ValueError, TypeError):
            continue
    return out


def market_chart_to_daily_bars(chart: dict) -> list[dict]:
    """Convert CG market_chart payload to list of {date, close_usd, volume_usd, mcap_usd}.

    All three CG series (prices, total_volumes, market_caps) are bucketed by UTC
    date independently, then joined on date. Joining by raw ms timestamp would
    silently drop volume/mcap because CG occasionally has off-by-ms drift.
    """
    prices_by_date = _bucket_by_utc_date(chart.get("prices") or [])
    volumes_by_date = _bucket_by_utc_date(chart.get("total_volumes") or [])
    mcaps_by_date = _bucket_by_utc_date(chart.get("market_caps") or [])

    # Sanity: if days requested implies daily granularity, the price-series row
    # count should be close to the day count. Excess rows mean CG returned hourly
    # (silent free-tier reversion); the bucketing still produces one bar/day but
    # close = last hour, not daily close.
    if len(prices_by_date) > 0 and len(chart.get("prices") or []) > len(prices_by_date) * 2:
        logger.warning(
            "CoinGecko market_chart returned %d points but only %d unique dates "
            "— likely hourly granularity; daily close approximated by last hour",
            len(chart.get("prices") or []), len(prices_by_date),
        )

    bars: list[dict] = []
    for d in sorted(prices_by_date.keys()):
        close = prices_by_date.get(d)
        if close is None:
            continue
        bars.append({
            "date": d,
            "close_usd": close,
            "volume_usd": volumes_by_date.get(d),
            "mcap_usd": mcaps_by_date.get(d),
        })
    return bars


async def get_categories() -> list[dict]:
    """Returns CG's category list with id, name, market_cap, top_3_coins.
    Refresh weekly — taxonomy is low-churn."""
    result = await _get("/coins/categories")
    return result if isinstance(result, list) else []


async def get_coin_detail(coin_id: str) -> dict:
    """Full coin metadata, used for chain/contract resolution and category membership.
    Returns {id, symbol, name, platforms: {<chain>: <contract_addr>}, categories: [...]}.
    """
    result = await _get(f"/coins/{coin_id}", {
        "localization": "false",
        "tickers": "false",
        "market_data": "false",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    })
    return result if isinstance(result, dict) else {}


async def get_global_macro() -> dict:
    """Daily macro snapshot: total mcap + dominance percentages.

    Returns {total_market_cap_usd, btc_dominance_pct, eth_dominance_pct,
             btc_mcap_usd, eth_mcap_usd, total3_mcap_usd}.
    TOTAL3 is derived: total_mcap × (1 − btc_pct/100 − eth_pct/100).
    """
    result = await _get("/global")
    if not isinstance(result, dict):
        return {}
    data = result.get("data") or {}
    total_mcap_map = data.get("total_market_cap") or {}
    dominance_map = data.get("market_cap_percentage") or {}
    total_mcap = float(total_mcap_map.get("usd") or 0.0)
    btc_pct = float(dominance_map.get("btc") or 0.0)
    eth_pct = float(dominance_map.get("eth") or 0.0)
    btc_mcap = total_mcap * btc_pct / 100.0
    eth_mcap = total_mcap * eth_pct / 100.0
    # Clamp at 0: CG cache lag could in principle return btc+eth > 100 on a
    # flash-crash boundary, which would yield a negative TOTAL3.
    total3_mcap = max(0.0, total_mcap - btc_mcap - eth_mcap)
    return {
        "total_market_cap_usd": total_mcap,
        "btc_dominance_pct": btc_pct,
        "eth_dominance_pct": eth_pct,
        "btc_mcap_usd": btc_mcap,
        "eth_mcap_usd": eth_mcap,
        "total3_mcap_usd": total3_mcap,
    }
