"""Pre-trade filters for EP gap trading backtest."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from agents.market_intelligence.collector import get_fmp_profile
from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

# Filter thresholds
MIN_ADV_DOLLAR_VOLUME = 1_000_000  # $1M median daily dollar volume
MAX_ATR_PCT = 15.0                 # 14-day ATR / close
MIN_MARKET_CAP = 500_000_000       # $500M

# Market cap cache — avoids repeated yfinance calls
_mcap_cache: dict[str, float | None] = {}


async def check_filters(
    ticker: str,
    alert_date: date,
    skip_mcap: bool = False,
) -> tuple[bool, str | None]:
    """
    Apply pre-trade filters. Returns (passed, skip_reason).
    Checks: ADV dollar volume, ATR%, market cap.
    skip_mcap: skip market cap check (for historical scans where current mcap != historical).
    """
    # 1. ADV dollar volume check
    adv_check = await _check_adv_dollar_volume(ticker, alert_date)
    if adv_check:
        return False, adv_check

    # 2. ATR% check
    atr_check = await _check_atr_pct(ticker, alert_date)
    if atr_check:
        return False, atr_check

    # 3. Market cap check
    if not skip_mcap:
        mcap_check = await _check_market_cap(ticker)
        if mcap_check:
            return False, mcap_check

    return True, None


async def _check_adv_dollar_volume(ticker: str, trade_date: date) -> str | None:
    """Check median 20-day dollar volume >= $1M. Returns skip reason or None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY close * volume) as adv_dollar
            FROM mi_daily_closes
            WHERE ticker = $1
              AND trade_date <= $2
              AND trade_date >= $2 - INTERVAL '30 days'
              AND volume > 0
            HAVING COUNT(*) >= 10
        """, ticker, trade_date)

    if not row or row["adv_dollar"] is None:
        return f"adv_no_data"

    adv_dollar = float(row["adv_dollar"])
    if adv_dollar < MIN_ADV_DOLLAR_VOLUME:
        return f"adv_too_low (${adv_dollar:,.0f})"

    return None


async def compute_atr_14(ticker: str, as_of_date: date) -> tuple[float | None, float | None]:
    """
    Compute 14-day ATR (close-to-close approx).
    Returns (atr_dollars, atr_pct) or (None, None).
    atr_pct = ATR / last close — the percentage form needed for stop validation.
    """
    pool = await get_pool()
    lookback_start = as_of_date - timedelta(days=30)  # calendar days for ~14 trading days

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT trade_date, close
            FROM mi_daily_closes
            WHERE ticker = $1
              AND trade_date <= $2
              AND trade_date >= $3
            ORDER BY trade_date ASC
        """, ticker, as_of_date, lookback_start)

    if len(rows) < 10:
        return None, None

    closes = [float(r["close"]) for r in rows]

    # ATR approximation from closes (no intraday H/L stored in daily_closes)
    # Use absolute daily returns as TR proxy
    true_ranges = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    if not true_ranges:
        return None, None

    atr_14 = sum(true_ranges[-14:]) / min(14, len(true_ranges[-14:]))
    last_close = closes[-1]
    atr_pct = (atr_14 / last_close * 100) if last_close > 0 else None
    return atr_14, atr_pct


async def _check_atr_pct(ticker: str, trade_date: date) -> str | None:
    """Check 14-day ATR% <= 15%. Returns skip reason or None."""
    _atr_14, atr_pct = await compute_atr_14(ticker, trade_date)
    if atr_pct is None:
        return None  # not enough data — let it through

    if atr_pct > MAX_ATR_PCT:
        return f"atr_too_high ({atr_pct:.1f}%)"

    return None


async def _check_market_cap(ticker: str) -> str | None:
    """Check market cap >= $500M. Returns skip reason or None."""
    if ticker in _mcap_cache:
        mcap = _mcap_cache[ticker]
    else:
        try:
            profile = await get_fmp_profile(ticker)
            mcap = profile.get("marketCap")
            _mcap_cache[ticker] = mcap
        except Exception as e:
            logger.debug(f"Market cap check failed for {ticker}: {e}")
            _mcap_cache[ticker] = None
            return None  # let it through if we can't check

    if mcap is None:
        return None  # no data — let it through

    if mcap < MIN_MARKET_CAP:
        return f"mcap_too_low (${mcap / 1e6:.0f}M)"

    return None
