"""Data source router — picks the right client per coin based on coverage.

Routing strategy:
1. Majors with Kraken USD pair       -> Kraken (deep history, free, no limit)
2. Long-tail with CoinGecko id       -> CoinGecko historical + DexScreener current
3. Long-tail without CoinGecko id    -> DexScreener only (current quote, no history)
                                        — caller must wait for accumulation

The Kraken-supported set is discovered once at module init (cached) so the
nightly ingest doesn't burn an API call deciding routing per coin.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

from agents.market_intelligence.crypto import (
    coingecko_client as cg,
    defillama_client as llama,
    dexscreener_client as ds,
    kraken_client as kraken,
)

logger = logging.getLogger(__name__)

_kraken_supported_cache: Optional[set[str]] = None
_kraken_cache_loaded_at: Optional[float] = None
_KRAKEN_CACHE_TTL_SEC = 24 * 3600  # refresh daily so newly-listed Kraken pairs become routable


async def _ensure_kraken_universe() -> set[str]:
    global _kraken_supported_cache, _kraken_cache_loaded_at
    now = time.monotonic()
    expired = (
        _kraken_cache_loaded_at is None
        or (now - _kraken_cache_loaded_at) > _KRAKEN_CACHE_TTL_SEC
    )
    if _kraken_supported_cache is None or expired:
        try:
            pairs = await kraken.list_supported_pairs(quote="USD")
            _kraken_supported_cache = {p.upper() for p in pairs}
            _kraken_cache_loaded_at = now
            logger.info("Kraken universe cached: %d USD pairs", len(_kraken_supported_cache))
        except Exception:
            logger.exception("Kraken universe fetch failed; routing all to CoinGecko")
            if _kraken_supported_cache is None:
                _kraken_supported_cache = set()
            # On refresh failure keep the stale cache; better than empty.
    return _kraken_supported_cache


async def fetch_daily_history(
    coin_id: Optional[str],
    symbol: str,
    days: int = 365,
) -> list[dict]:
    """Get daily bars for a coin. Routes by source preference.

    Returns list of {date, close_usd, volume_usd, mcap_usd}.
    Empty list = no historical data available (DEX-only coin; await accumulation).
    """
    supported = await _ensure_kraken_universe()
    sym_upper = symbol.upper()

    if sym_upper in supported:
        try:
            bars = await kraken.get_daily_ohlc(sym_upper, "USD")
            if bars:
                return [
                    {
                        "date": b["date"],
                        "close_usd": b["close"],
                        "volume_usd": b["volume"] * b["close"],  # Kraken returns base volume
                        "mcap_usd": None,  # Kraken doesn't supply mcap
                        "source": "kraken",
                    }
                    for b in bars
                ]
        except Exception:
            logger.exception("Kraken history failed for %s; falling back to CG", sym_upper)

    if coin_id and not coin_id.startswith("_unresolved_"):
        try:
            chart = await cg.get_market_chart(coin_id, days=days)
            bars = cg.market_chart_to_daily_bars(chart)
            for b in bars:
                b["source"] = "coingecko"
            return bars
        except Exception:
            logger.exception("CoinGecko history failed for %s (%s)", symbol, coin_id)

    # DEX-only fallback: no historical depth available from this source.
    # Caller continues with current snapshot only; RS unavailable until
    # ~30 days of daily snapshots accumulate.
    return []


async def fetch_current_quote(
    coin_id: Optional[str],
    symbol: str,
    chain: Optional[str] = None,
    contract_address: Optional[str] = None,
) -> Optional[dict]:
    """Get current snapshot. Routes to DexScreener if chain+contract supplied,
    else falls through to Kraken (majors) or CoinGecko universe data.

    Returns {price_usd, volume_24h_usd, mcap_usd, source} or None.
    """
    if chain and contract_address:
        quote = await ds.get_token_quote(chain, contract_address)
        if quote and quote.get("price_usd"):
            return {
                "price_usd": quote["price_usd"],
                "volume_24h_usd": quote.get("volume_24h_usd"),
                "mcap_usd": quote.get("mcap_usd"),
                "source": "dexscreener",
            }

    supported = await _ensure_kraken_universe()
    if symbol.upper() in supported:
        price = await kraken.get_current_price(symbol.upper(), "USD")
        if price is not None:
            return {
                "price_usd": price,
                "volume_24h_usd": None,
                "mcap_usd": None,
                "source": "kraken",
            }

    # No current-quote fallback to CoinGecko `/coins/{id}` here — that endpoint
    # is heavy. The /coins/markets call in get_top_universe gives current price
    # for the whole universe in one go and is the right tool for nightly batch.
    return None


async def fetch_macro_indicators() -> dict:
    """Fetch the three macro signals: BTC.D, TOTAL3, total stablecoin mcap.

    Returns merged dict. `sources_ok` lists which sources succeeded —
    trigger evaluator MUST require both `coingecko` and `defillama` present
    before firing, otherwise an absent BTC.D could be silently treated as 0%
    and produce a false alert.
    """
    out: dict = {"sources_ok": []}
    try:
        cg_macro = await cg.get_global_macro()
        if cg_macro:
            out.update(cg_macro)
            out["sources_ok"].append("coingecko")
    except Exception:
        logger.exception("CoinGecko /global failed")

    try:
        stable = await llama.get_current_stablecoin_supply()
        if stable:
            out.update(stable)
            out["sources_ok"].append("defillama")
    except Exception:
        logger.exception("DefiLlama /stablecoins failed")

    out["snapshot_date"] = datetime.now(_ET).date()
    return out
