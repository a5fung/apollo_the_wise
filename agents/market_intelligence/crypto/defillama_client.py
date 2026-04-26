"""DefiLlama client — stablecoin total mcap ONLY.

DefiLlama's API is scoped to TVL/protocols/stablecoins/DEX volumes/yields.
It does NOT expose global market-cap dominance — those come from CoinGecko's
/global endpoint instead (see coingecko_client.get_global_macro).

Endpoint used:
- /stablecoins?includePrices=true   — list of all stablecoins with current
                                       circulating supply
- /stablecoincharts/all              — historical daily total stablecoin mcap

Free tier, no key, no documented rate limit (be conservative — 1 call/sec).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://stablecoins.llama.fi"
_TIMEOUT = httpx.Timeout(20.0)
_THROTTLE_LOCK = asyncio.Lock()
_MIN_INTERVAL_SEC = 1.0
_last_call_at: Optional[float] = None

# Symbols counted toward "real" stablecoin supply. Excludes algorithmic and
# wrapped variants that distort the inflow signal.
MAJOR_STABLES = frozenset({"USDT", "USDC", "DAI", "FDUSD", "TUSD", "PYUSD"})


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
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params=params or {})
        resp.raise_for_status()
        return resp.json()


async def get_current_stablecoin_supply() -> dict:
    """Latest stablecoin circulating supply, restricted to MAJOR_STABLES.

    Returns {major_stables_mcap, usdt_mcap, usdc_mcap, dai_mcap}.
    Note: `major_stables_mcap` sums only the symbols in MAJOR_STABLES — NOT the
    universe of all stablecoins. Naming is deliberate: trigger math wants a
    consistent series, not the long tail of niche stablecoins that come and go.
    `circulating.peggedUSD` is taken at face value (USD-equivalent dollar amount)
    even on rows whose primary peg is non-USD; rows without that key are skipped.
    """
    result = await _get("/stablecoins", {"includePrices": "true"})
    if not isinstance(result, dict):
        return {}

    rows = result.get("peggedAssets") or []
    total = 0.0
    by_symbol: dict[str, float] = {}
    for row in rows:
        symbol = (row.get("symbol") or "").upper()
        if symbol not in MAJOR_STABLES:
            continue
        circ_dict = row.get("circulating") or {}
        circulating = circ_dict.get("peggedUSD")
        if circulating is None:
            continue
        try:
            circ_f = float(circulating)
        except (ValueError, TypeError):
            continue
        total += circ_f
        by_symbol[symbol] = by_symbol.get(symbol, 0.0) + circ_f

    return {
        "major_stables_mcap": total,
        "usdt_mcap": by_symbol.get("USDT", 0.0),
        "usdc_mcap": by_symbol.get("USDC", 0.0),
        "dai_mcap": by_symbol.get("DAI", 0.0),
    }


async def get_stablecoin_history(days: int = 90) -> list[dict]:
    """Daily total stablecoin mcap series for the last N days.

    Returns [{date, total_stable_mcap}, ...] sorted ascending. Last entry per
    date wins on duplicates. `total_stable_mcap` here is the total across ALL
    peg types (DefiLlama's `totalCirculatingUSD` is already USD-denominated for
    every key — peggedUSD, peggedEUR, etc. are dollar-equivalent amounts), so
    this differs from `get_current_stablecoin_supply.major_stables_mcap` which
    is symbol-filtered. Both series move together; the trigger uses slope only.
    """
    result = await _get("/stablecoincharts/all")
    if not isinstance(result, list):
        return []

    by_date: dict[date, float] = {}
    for entry in result:
        ts_raw = entry.get("date")
        if ts_raw is None:
            continue
        try:
            ts = int(ts_raw)
        except (ValueError, TypeError):
            continue
        bar_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        total_circ = entry.get("totalCirculatingUSD") or {}
        total_usd = 0.0
        for v in total_circ.values():
            try:
                total_usd += float(v)
            except (ValueError, TypeError):
                continue
        # Last entry per date wins (defensive against backfill duplicates).
        by_date[bar_date] = total_usd

    rows = [{"date": d, "total_stable_mcap": v} for d, v in sorted(by_date.items())]
    return rows[-days:] if len(rows) > days else rows
