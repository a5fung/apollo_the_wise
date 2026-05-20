"""
Per-ticker earnings-day check via yfinance.

Combines two yfinance surfaces because each has gaps:
- `Ticker.earnings_dates` — historical, but lags fresh announcements (DOCN 5/05 missing on scan day).
- `Ticker.calendar` — forward-looking next event; caught DOCN 5/05 when earnings_dates didn't.

A match counts ONLY if the announcement is on yesterday (AMC) or today (BMO) — the two gap-
creating cases that would produce same-day price action. Tomorrow's earnings can't have
caused today's gap; matching them was over-permissive (tightened 2026-05-08 per user req).

Returns `(matched, source)` where source ∈ {"earnings_dates", "calendar", "no_match", "unavailable"}.
The detector branches on source for audit telemetry: distinguishes "yfinance said no" from "yfinance was broken."

In-process cache `(ticker, scan_date) → (bool, str)` because the EP scan fires every 5 min from
7:00–10:00 ET; without it the same ticker would hit yfinance ~36× per morning.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Per-process cache. Cleared on first call when the date rolls over.
_CACHE: dict[tuple[str, date], tuple[bool, str]] = {}
_CACHE_DATE: Optional[date] = None


def _within_window(announce_dt, scan_date: date) -> bool:
    """True if announcement is yesterday (AMC) or today (BMO).

    Tightened 2026-05-08 from ±1 day to {yesterday, today} only. Earnings on
    `scan_date + 1` cannot have produced today's gap — matching them was
    over-permissive and could surface false-positive boost candidates whose
    catalyst is unrelated (sector sympathy, rumor, etc.) but happen to have
    earnings expected later in the week.
    """
    if announce_dt is None:
        return False
    if hasattr(announce_dt, "date"):
        announce_d = announce_dt.date()
    elif isinstance(announce_dt, date):
        announce_d = announce_dt
    else:
        return False
    diff = (announce_d - scan_date).days
    return diff in (-1, 0)  # yesterday or today; NOT tomorrow


def _check_earnings_dates_sync(ticker: str, scan_date: date) -> bool:
    import yfinance as yf
    t = yf.Ticker(ticker)
    df = t.earnings_dates
    if df is None or df.empty:
        return False
    for idx in df.index:
        if _within_window(idx, scan_date):
            return True
    return False


def _check_calendar_sync(ticker: str, scan_date: date) -> bool:
    import yfinance as yf
    t = yf.Ticker(ticker)
    cal = t.calendar
    if not cal:
        return False
    earnings = cal.get("Earnings Date") if isinstance(cal, dict) else None
    if not earnings:
        return False
    if isinstance(earnings, list):
        candidates = earnings
    else:
        candidates = [earnings]
    return any(_within_window(d, scan_date) for d in candidates)


def _check_revenue_stage_sync(ticker: str) -> bool:
    """True if company has non-zero expected revenue (revenue-stage business),
    False if pre-revenue (clinical-stage biotech, SPAC, blank-check, etc.).

    Reads yfinance's Ticker.calendar.Revenue Average. Pre-revenue companies
    have Revenue Average = 0 because no analyst expects revenue.

    Fail-soft to True (assume revenue-stage) on any error — the earnings
    boost is methodology-defensive, better to over-boost on data outage
    than miss a real earnings EP.

    2026-05-20: shipped after IMVT (clinical-stage biotech, $0 revenue)
    got boosted strong→downgraded routine, producing confusing operator
    message 'Q-rev YoY un-extractable from news'. Real issue was the
    earnings boost shouldn't have fired for a pre-revenue company.
    """
    import yfinance as yf
    try:
        cal = yf.Ticker(ticker).calendar
        if not isinstance(cal, dict):
            return True
        rev_avg = cal.get("Revenue Average", None)
        if rev_avg is None:
            return True
        return float(rev_avg) > 0
    except Exception:
        return True


# Per-process cache for revenue-stage lookup. Cleared with main _CACHE
# when scan_date rolls over (same lifecycle).
_REV_STAGE_CACHE: dict[str, bool] = {}


async def is_revenue_stage(ticker: str) -> bool:
    """Async wrapper for revenue-stage check. Cached per-ticker per-day."""
    if ticker in _REV_STAGE_CACHE:
        return _REV_STAGE_CACHE[ticker]
    try:
        result = await asyncio.to_thread(_check_revenue_stage_sync, ticker)
    except Exception:
        result = True  # fail-soft
    _REV_STAGE_CACHE[ticker] = result
    return result


async def is_earnings_day(ticker: str, scan_date: date) -> tuple[bool, str]:
    """
    Returns (matched, source). Source is one of:
      - "earnings_dates": matched in historical earnings_dates surface
      - "calendar": matched in forward-looking calendar surface
      - "no_match": both surfaces returned data but neither matched the window
      - "unavailable": yfinance raised or returned empty for both surfaces
    """
    global _CACHE_DATE
    if _CACHE_DATE != scan_date:
        _CACHE.clear()
        _REV_STAGE_CACHE.clear()
        _CACHE_DATE = scan_date

    key = (ticker, scan_date)
    if key in _CACHE:
        return _CACHE[key]

    earnings_dates_ok = False
    earnings_dates_failed = False
    try:
        earnings_dates_ok = await asyncio.to_thread(_check_earnings_dates_sync, ticker, scan_date)
    except Exception as e:
        earnings_dates_failed = True
        logger.debug(f"earnings_dates lookup failed for {ticker}: {e}")

    if earnings_dates_ok:
        result = (True, "earnings_dates")
        _CACHE[key] = result
        return result

    calendar_ok = False
    calendar_failed = False
    try:
        calendar_ok = await asyncio.to_thread(_check_calendar_sync, ticker, scan_date)
    except Exception as e:
        calendar_failed = True
        logger.debug(f"calendar lookup failed for {ticker}: {e}")

    if calendar_ok:
        result = (True, "calendar")
    elif earnings_dates_failed and calendar_failed:
        result = (False, "unavailable")
    else:
        result = (False, "no_match")

    _CACHE[key] = result
    return result
