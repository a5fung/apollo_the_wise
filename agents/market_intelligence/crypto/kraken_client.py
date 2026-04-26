"""Kraken public REST client — majors price feed.

US-VPS-safe (Kraken is US-regulated and accepts US IPs).
Public endpoints require no API key. Rate limit is generous for public data
(~1 call/sec sustained); we throttle conservatively.

Endpoints used:
- /0/public/AssetPairs   — list of supported pairs (universe discovery)
- /0/public/OHLC         — daily OHLC, up to 720 bars per request
- /0/public/Ticker       — current quote

Kraken quirk: BTC is `XBT` in pair codes (e.g., `XBTUSD`, not `BTCUSD`). The
client normalizes this transparently — callers pass `BTC` and the wire layer
substitutes.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.kraken.com"
_TIMEOUT = httpx.Timeout(15.0)
_THROTTLE_LOCK = asyncio.Lock()
_MIN_INTERVAL_SEC = 1.1  # Kraken public tier: ~1 req/sec

_last_call_at: Optional[float] = None


def _normalize_symbol(symbol: str) -> str:
    """Kraken uses XBT for Bitcoin in pair codes; normalize."""
    s = symbol.upper()
    return "XBT" if s == "BTC" else s


def _pair_code(base: str, quote: str = "USD") -> str:
    return f"{_normalize_symbol(base)}{quote}"


async def _throttle() -> None:
    global _last_call_at
    async with _THROTTLE_LOCK:
        now = time.monotonic()
        if _last_call_at is not None:
            elapsed = now - _last_call_at
            if elapsed < _MIN_INTERVAL_SEC:
                await asyncio.sleep(_MIN_INTERVAL_SEC - elapsed)
        _last_call_at = time.monotonic()


async def _get(path: str, params: Optional[dict] = None) -> dict:
    await _throttle()
    url = f"{_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params=params or {})
        resp.raise_for_status()
        payload = resp.json()
    errors = payload.get("error") or []
    if errors:
        raise RuntimeError(f"Kraken API error on {path}: {errors}")
    return payload.get("result") or {}


async def list_supported_pairs(quote: str = "USD") -> list[str]:
    """Return base symbols for which a `<base><quote>` spot pair exists.

    Used to decide which watchlist coins Kraken can serve (vs. routing to
    DexScreener/CoinGecko fallback).
    """
    result = await _get("/0/public/AssetPairs")
    bases: list[str] = []
    for _, info in result.items():
        wsname = info.get("wsname") or ""
        if wsname.endswith(f"/{quote}"):
            base = wsname.split("/")[0]
            # Kraken WS uses XBT; expose canonical BTC to callers.
            bases.append("BTC" if base == "XBT" else base)
    return sorted(set(bases))


async def get_daily_ohlc(
    base: str, quote: str = "USD", since: Optional[date] = None
) -> list[dict]:
    """Fetch daily OHLC bars for `<base>/<quote>`.

    Returns list of dicts with keys: date, open, high, low, close, volume.
    Up to 720 most recent bars; pass `since` to fetch from a specific date forward.
    Returns [] if the pair doesn't exist on Kraken (caller routes to fallback).
    """
    pair = _pair_code(base, quote)
    params = {"pair": pair, "interval": 1440}  # 1440 min = daily
    if since is not None:
        # Kraken expects unix seconds.
        ts = int(datetime(since.year, since.month, since.day, tzinfo=timezone.utc).timestamp())
        params["since"] = ts

    try:
        result = await _get("/0/public/OHLC", params)
    except RuntimeError as e:
        msg = str(e)
        if "Unknown asset pair" in msg:
            logger.info("Kraken: pair %s not supported, skipping", pair)
            return []
        raise

    # Result has one key per pair (Kraken's canonical name, not the requested code).
    # Pull the first non-`last` key.
    bars_raw: list[list] = []
    for k, v in result.items():
        if k == "last":
            continue
        if isinstance(v, list):
            bars_raw = v
            break

    bars: list[dict] = []
    for row in bars_raw:
        # Row format: [time, open, high, low, close, vwap, volume, count]
        try:
            ts = int(row[0])
            bars.append({
                "date": datetime.fromtimestamp(ts, tz=timezone.utc).date(),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[6]),
            })
        except (ValueError, IndexError, TypeError):
            continue
    return bars


async def get_current_price(base: str, quote: str = "USD") -> Optional[float]:
    """Return last trade price for `<base>/<quote>`, or None if pair unsupported."""
    pair = _pair_code(base, quote)
    try:
        result = await _get("/0/public/Ticker", {"pair": pair})
    except RuntimeError as e:
        if "Unknown asset pair" in str(e):
            return None
        raise

    for _, info in result.items():
        last = (info.get("c") or [None])[0]
        if last is not None:
            try:
                return float(last)
            except (ValueError, TypeError):
                return None
    return None
