"""Pre-trade filters for EP gap trading backtest."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from agents.market_intelligence.broker.skip_reasons import (
    FILTER_ADV_NO_DATA,
    FILTER_ADV_TOO_LOW,
    FILTER_ATR_TOO_HIGH,
    FILTER_MCAP_TOO_SMALL,
    SETUP_STOP_TOO_WIDE,
    SETUP_ZERO_RANGE,
)
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
        return FILTER_ADV_NO_DATA

    adv_dollar = float(row["adv_dollar"])
    if adv_dollar < MIN_ADV_DOLLAR_VOLUME:
        return f"{FILTER_ADV_TOO_LOW}: ${adv_dollar:,.0f}"

    return None


async def compute_atr_14(ticker: str, as_of_date: date) -> tuple[float | None, float | None]:
    """
    14-day ATR using Wilder true range:
        TR = max(H-L, |H-prev_close|, |L-prev_close|)
        ATR-14 = simple mean of the last 14 TRs (SSoT with flag_detector._atr_14).

    Reads OHLC from mi_daily_closes (backfilled 2026-04-25). Close-to-close
    approximations silently understate ATR on volatile/gappy stocks — STRL
    2026-05-05 was the canonical miss: Wilder TR $24.52 vs close-only $13.55
    (1.5× gate $36.78 vs $20.33; ORB $35.02 now passes).

    Note on backtest/live asymmetry: this reads `as_of_date` H/L too, so
    backtests include the alert-day's gap TR. The 9:31 AM live path only
    has through prev close (today's bar not in mi_daily_closes yet). TV's
    realtime $43.25 reflects today's gap; Apollo's pre-open ATR cannot.
    Kept as-is (matches flag_detector SSoT); revisit if 30d skip replay
    shows gap-day false positives that would have been winners.
    """
    pool = await get_pool()
    lookback_start = as_of_date - timedelta(days=35)  # ~20 trading days, covers 15-bar window

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT trade_date, high_price, low_price, close
            FROM mi_daily_closes
            WHERE ticker = $1
              AND trade_date <= $2
              AND trade_date >= $3
              AND high_price IS NOT NULL
              AND low_price IS NOT NULL
            ORDER BY trade_date ASC
        """, ticker, as_of_date, lookback_start)

    if len(rows) < 10:
        return None, None

    trs = []
    for i in range(1, len(rows)):
        h = float(rows[i]["high_price"])
        l = float(rows[i]["low_price"])
        pc = float(rows[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

    if not trs:
        return None, None

    window = trs[-14:]
    atr_14 = sum(window) / len(window)
    last_close = float(rows[-1]["close"])
    atr_pct = (atr_14 / last_close * 100) if last_close > 0 else None
    return atr_14, atr_pct


# ── W2 study #2 — stop-geometry knob (#276). The live MAGNA53 day-1 stop is ORB low; this resolver
# lets the offline replay vary ONLY that geometry (held constant: selection, entry, exit, sizing-
# rule). It is threaded into BOTH the risk-based sizing AND the exit so each arm risks the same $
# (else R is not comparable — advisor 6/18). lower price = WIDER stop. OFFLINE/backtester only.
def resolve_entry_stop(
    entry_price: float, orb_low: float, atr_14: float | None,
    prior_day_low: float | None, stop_model: str, stop_atr_k: float,
) -> float:
    """Day-1 entry stop per `stop_model`:
      orb_low   = the live baseline (the ORB low).
      atr_floor = WIDEN too-tight ORBs to >= k*ATR below entry (min ⇒ the wider of orb_low / the
                  ATR-distance stop) — only ever widens; the motivated arm (noise-stopout fix).
      atr_cap   = TIGHTEN wide ORBs to <= k*ATR below entry (max) — the SUSPECT direction (the
                  1-min sim under-counts intra-bar stop-outs → flatters tighter stops; discount).
      day_low   = the prior trading day's low (structural, 9M-analog wider stop).
    Degenerate results (≤0 or ≥ entry) fall back to orb_low — never a non-positive risk."""
    stop = orb_low
    if atr_14 is not None and atr_14 > 0:
        if stop_model == "atr_floor":
            stop = min(orb_low, entry_price - stop_atr_k * atr_14)
        elif stop_model == "atr_cap":
            stop = max(orb_low, entry_price - stop_atr_k * atr_14)
    if stop_model == "day_low" and prior_day_low is not None:
        stop = prior_day_low
    if stop <= 0 or stop >= entry_price:
        return orb_low
    return stop


async def get_prior_day_low(ticker: str, alert_date: date) -> float | None:
    """Low of the most recent trading day STRICTLY before `alert_date` (mi_daily_closes) — the
    structural-stop source for the day_low arm. None if absent. OFFLINE/backtester only."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT low_price FROM mi_daily_closes
               WHERE ticker = $1 AND trade_date < $2 AND low_price IS NOT NULL
               ORDER BY trade_date DESC LIMIT 1""",
            ticker, alert_date)
    return float(row["low_price"]) if row and row["low_price"] is not None else None


async def _check_atr_pct(ticker: str, trade_date: date) -> str | None:
    """Check 14-day ATR% <= 15%. Returns skip reason or None."""
    _atr_14, atr_pct = await compute_atr_14(ticker, trade_date)
    if atr_pct is None:
        return None  # not enough data — let it through

    if atr_pct > MAX_ATR_PCT:
        return f"{FILTER_ATR_TOO_HIGH}: {atr_pct:.1f}% > {MAX_ATR_PCT}%"

    return None


def validate_orb_entry(
    orb_high: float,
    orb_low: float,
    atr_14: float | None,
) -> tuple[bool, str | None]:
    """
    Single authoritative ORB entry validation rule.
    Called by both EOD sim (engine.py) and live path (order_manager.py).
    Returns (passed, skip_reason).
    """
    orb_range = orb_high - orb_low
    if orb_range <= 0:
        return False, SETUP_ZERO_RANGE
    if atr_14 and atr_14 > 0 and orb_range > 1.5 * atr_14:
        return False, f"{SETUP_STOP_TOO_WIDE}: {orb_range:.2f} > 1.5x ATR {atr_14:.2f}"
    return True, None


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
        return f"{FILTER_MCAP_TOO_SMALL}: ${mcap / 1e6:.0f}M < ${MIN_MARKET_CAP / 1e6:.0f}M"

    return None
