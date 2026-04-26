"""DexScreener client — long-tail current quotes via on-chain DEX data.

Free, no API key. Generous 300 req/min limit on /tokens/v1.

Used for the $15M-$500M long-tail band where Kraken and CoinGecko coverage
thins out (Solana ecosystem memes, new launches, DEX-only Ethereum tokens
like KnoxNet). Provides current price + 24h volume + liquidity, NOT
historical OHLC depth — historical bars come from CoinGecko.

Trusted-chain whitelist applied to ALL DexScreener paths (including watchlist
lookups). Coins outside trusted chains return None and the caller falls through
to symbol-based search or skips the coin. To add a chain, edit TRUSTED_CHAINS
deliberately rather than per-call override.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.dexscreener.com"
_TIMEOUT = httpx.Timeout(15.0)
_THROTTLE_LOCK = asyncio.Lock()
_MIN_INTERVAL_SEC = 0.25  # 300 req/min ceiling -> ~240 effective with 250ms gap
_last_call_at: Optional[float] = None

TRUSTED_CHAINS = frozenset({"ethereum", "solana", "base", "arbitrum"})


async def _throttle() -> None:
    global _last_call_at
    async with _THROTTLE_LOCK:
        now = time.monotonic()
        if _last_call_at is not None:
            elapsed = now - _last_call_at
            if elapsed < _MIN_INTERVAL_SEC:
                await asyncio.sleep(_MIN_INTERVAL_SEC - elapsed)
        _last_call_at = time.monotonic()


async def _get(path: str) -> dict | list:
    await _throttle()
    url = f"{_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def _pick_best_pair(pairs: list[dict]) -> Optional[dict]:
    """From a list of pairs for one token, pick the most liquid USD-quoted pair.

    DexScreener returns multiple pairs per token (different DEXes, different quote
    assets). We rank by 24h liquidity USD, prefer USD/USDC/USDT-quoted pairs to
    avoid noise from token-token pairs like KNX/WETH where price requires double
    conversion. Returns a sorted copy — does not mutate the input list.
    """
    if not pairs:
        return None
    usd_quoted = [
        p for p in pairs
        if (p.get("quoteToken", {}).get("symbol") or "").upper() in {"USD", "USDC", "USDT", "DAI"}
    ]
    candidates = sorted(
        usd_quoted or list(pairs),
        key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0.0),
        reverse=True,
    )
    return candidates[0] if candidates else None


async def get_token_quote(chain: str, contract_address: str) -> Optional[dict]:
    """Current quote for one token on one chain.

    Returns {price_usd, volume_24h_usd, liquidity_usd, fdv_usd, mcap_usd, pair_url}
    or None if no pair found / chain untrusted.
    """
    if chain not in TRUSTED_CHAINS:
        logger.warning("DexScreener: chain %s not in trusted set, skipping", chain)
        return None

    try:
        result = await _get(f"/tokens/v1/{chain}/{contract_address}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise

    pairs = result if isinstance(result, list) else []
    best = _pick_best_pair(pairs)
    if not best:
        return None

    return {
        "price_usd": float(best.get("priceUsd") or 0.0) or None,
        "volume_24h_usd": float((best.get("volume") or {}).get("h24") or 0.0) or None,
        "liquidity_usd": float((best.get("liquidity") or {}).get("usd") or 0.0) or None,
        "fdv_usd": float(best.get("fdv") or 0.0) or None,
        "mcap_usd": float(best.get("marketCap") or 0.0) or None,
        "pair_url": best.get("url"),
        "base_symbol": (best.get("baseToken") or {}).get("symbol"),
    }


async def search_token_by_symbol(symbol: str) -> list[dict]:
    """Symbol-based search across all DEXes — used for fallback resolution when a
    coin has no CoinGecko id. Returns raw pair list; caller filters to trusted
    chains and applies wash-trade gate.
    """
    try:
        result = await _get_with_params("/latest/dex/search", {"q": symbol})
    except httpx.HTTPStatusError:
        return []
    if not isinstance(result, dict):
        return []
    return result.get("pairs") or []


async def _get_with_params(path: str, params: dict) -> dict | list:
    await _throttle()
    url = f"{_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
