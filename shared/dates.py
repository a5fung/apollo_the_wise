"""Date utilities shared across orchestrator and agent containers.

Pulled out of `agents.market_intelligence.collector` so the orchestrator
can import `last_trading_day` for slash-command handlers without
depending on the market-intelligence package (which is not present in
the orchestrator container by design).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytz

_ET = pytz.timezone("US/Eastern")


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
