"""
NYSE trading calendar utilities.

Uses exchange_calendars (rule-based, offline) to determine whether a given
date is a US market trading day. This drives the nightly data pull guardrail:
  - Regular weekday with no data → real failure, fire alert
  - Market holiday / early close → skip silently, log clearly

Holidays are computed from NYSE ruleset, not a hardcoded list, so they
are correct for future years without annual maintenance.

To audit skipped days (e.g. if you suspect a holiday was wrong):
  grep "market holiday" logs/market_agent.log
  grep "early close" logs/market_agent.log
  grep "skipping nightly pull" logs/market_agent.log
"""
from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from typing import NamedTuple

logger = logging.getLogger(__name__)


class MarketStatus(NamedTuple):
    is_trading_day: bool
    reason: str          # Human-readable explanation — always logged


@lru_cache(maxsize=1)
def _get_nyse_calendar():
    """Load the NYSE calendar once and cache it. Import is deferred so startup
    isn't slowed if the library isn't installed yet."""
    import exchange_calendars as xcals
    return xcals.get_calendar("XNYS")


def get_market_status(d: date) -> MarketStatus:
    """
    Return whether `d` is a NYSE trading day.

    Handles:
    - Weekends
    - US market holidays (New Year's, MLK Day, Presidents Day, Good Friday,
      Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving,
      Christmas — plus observed dates when they fall on weekends)
    - Early closes are noted but still counted as trading days

    Logs the result at INFO level every time so there's always a paper trail.
    """
    try:
        cal = _get_nyse_calendar()

        # Weekends
        if d.weekday() >= 5:
            status = MarketStatus(False, f"{d} is a weekend ({d.strftime('%A')})")
            logger.info(f"[trading_calendar] {status.reason} — skipping nightly pull")
            return status

        # Check if session exists
        d_str = d.strftime("%Y-%m-%d")
        is_session = cal.is_session(d_str)

        if not is_session:
            # Identify the holiday name if possible
            holiday_name = _get_holiday_name(cal, d)
            reason = (
                f"{d} is a market holiday ({holiday_name})"
                if holiday_name
                else f"{d} is a market holiday (NYSE closed)"
            )
            status = MarketStatus(False, reason)
            logger.info(
                f"[trading_calendar] {status.reason} — skipping nightly pull. "
                f"If this is wrong, check exchange_calendars version and file a bug at "
                f"https://github.com/rsheftel/pandas_market_calendars/issues"
            )
            return status

        # Trading day — check for early close
        early_close_note = _check_early_close(cal, d_str)
        reason = f"{d} is a trading day" + (f" ({early_close_note})" if early_close_note else "")
        status = MarketStatus(True, reason)
        logger.info(f"[trading_calendar] {status.reason}")
        return status

    except Exception as e:
        # Fail open: if the library errors, assume it's a trading day so we
        # don't silently skip real data. The existing 0-ingest guardrail will
        # catch genuine problems.
        logger.error(
            f"[trading_calendar] Failed to check calendar for {d}: {e}. "
            f"Assuming trading day (fail-open) — existing guardrail still active."
        )
        return MarketStatus(True, f"calendar check failed ({e}), assuming trading day")


def _get_holiday_name(cal, d: date) -> str | None:
    """Try to find the holiday name for a closed date."""
    try:
        import pandas as pd
        holidays = cal.adhoc_holidays
        # Check regular holidays
        regular = cal.regular_holidays
        if regular is not None:
            d_ts = pd.Timestamp(d)
            if d_ts in regular:
                return str(regular[d_ts]) if hasattr(regular, '__getitem__') else None
        return None
    except Exception as e:
        # Cosmetic-only (the caller falls back to a generic "NYSE closed" reason
        # string) — but still log so a real exchange_calendars integration break
        # leaves a trace instead of just silently losing the holiday name.
        logger.debug(f"[trading_calendar] _get_holiday_name failed for {d}: {e}")
        return None


def is_market_hours_now_et(end_buffer_minutes: int = 0) -> bool:
    """True iff `now` is inside the regular-session window in America/New_York,
    on a trading day (weekday + not a holiday).

    Extracted 2026-05-28 /simplify pass — three call sites had emerged
    (`/partialnow`, `_maybe_alert_stuck_pending_new`, `_today_market_hours_boots`
    SQL) each with slightly different windows and inconsistent holiday handling.

    Args:
        end_buffer_minutes: tail buffer past 16:00 ET. e.g. `50` for the
            `/partialnow` 16:50 cutoff that covers the 16:45 ET partial-
            take cron. Default 0 = strict 9:30–16:00 ET.

    Returns False on calendar-library failure (fail-closed: don't claim
    market is open if we can't prove it).
    """
    from datetime import datetime, time as _time
    from zoneinfo import ZoneInfo
    try:
        now_et = datetime.now(ZoneInfo("America/New_York"))
        if not get_market_status(now_et.date()).is_trading_day:
            return False
        end_mins = 16 * 60 + end_buffer_minutes
        cur_mins = now_et.hour * 60 + now_et.minute
        return (9 * 60 + 30) <= cur_mins <= end_mins
    except Exception as e:
        logger.warning(f"[trading_calendar] is_market_hours_now_et failed: {e}. "
                       f"Fail-closed — treating as market-closed (caller may skip "
                       f"a time-gated action).")
        return False


def _check_early_close(cal, d_str: str) -> str | None:
    """Return a note if the market closes early on this day, else None."""
    try:
        import pandas as pd
        early = cal.early_closes
        if early is not None and d_str in early.index.strftime("%Y-%m-%d"):
            close_time = early.loc[d_str]
            return f"early close at {close_time}"
        return None
    except Exception as e:
        # Cosmetic-only (the caller just omits the early-close note) — logged so
        # an exchange_calendars integration break isn't invisible.
        logger.debug(f"[trading_calendar] _check_early_close failed for {d_str}: {e}")
        return None
