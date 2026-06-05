"""Date utilities shared across orchestrator and agent containers.

Pulled out of `agents.market_intelligence.collector` so the orchestrator
can import `last_trading_day` for slash-command handlers without
depending on the market-intelligence package (which is not present in
the orchestrator container by design).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# CANONICAL ET zone for the whole codebase (imported as `from shared.dates import _ET`).
# MUST be ZoneInfo, never pytz: pytz timezones attached via `tzinfo=` (constructor /
# datetime.combine / .replace) silently apply the historical LMT offset (-04:56 for
# New York) instead of EDT/EST, which shifted the ORB window +56 min and recurred for
# weeks (#180/#183, 2026-06-05). ZoneInfo computes the correct offset for the wall-clock
# time in EVERY construction path, so `tzinfo=_ET` is always safe. pytz is banned in
# app code by scripts/preflight_datetime_hygiene.py (deploy gate).
_ET = ZoneInfo("America/New_York")


def et_today() -> date:
    """Return today's date in US/Eastern timezone."""
    return datetime.now(_ET).date()


def last_trading_day(from_date: date | None = None) -> date:
    """Most recent trading day on or before from_date (default: today ET).

    Saturday/Sunday rolls back to Friday so weekend queries fall back to
    the last available data instead of returning empty results.
    Approximation: weekends only, not holidays.
    """
    d = from_date or et_today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
