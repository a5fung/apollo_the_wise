"""#452 / regime sizing — the freshness test must be HOLIDAY-aware.

WHY THIS EXISTS. On 2026-09-08, the Tuesday after Labor Day, the regime-sizing
staleness gate floored BOTH books to 25% and fired its fail-loud alert twice. Nothing
was broken: Friday 09-04's regime row was the correct most-recent one, because the
regime nightly computes from the prior close and Monday was a market holiday. The gate
used `last_trading_day(today - 1)`, which is weekend-aware but holiday-blind, so it
demanded a Monday row that could never exist.

It cost real size on two live fills (PHVS 3 shares, SEI 2 shares — $12.35 of risk each
against the ~$37 that Choppy's 0.75 multiplier alone would have allowed), and it was a
documented "accepted" limitation at ~9 occurrences a year.

The fix reads the last session we actually HOLD closes for. `mi_daily_closes` has a row
per ticker per session, so a holiday produces none — the table carries the trading
calendar without anyone maintaining one.
"""
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import order_manager as om


def _pool_returning(value):
    """A pool whose fetchval yields `value` — exercises the REAL function, not a stub of it."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=value)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = AsyncMock()
    pool.acquire = lambda *a, **k: ctx
    return pool


@pytest.mark.asyncio
async def test_the_labor_day_case_no_longer_reads_as_stale():
    """The exact 2026-09-08 case, through the real read: the closes table holds Friday
    (no Labor Day row exists), so Friday's regime row is FRESH and nothing floors."""
    with patch.object(om, "get_pool",
               new=AsyncMock(return_value=_pool_returning(date(2026, 9, 4)))):
        threshold = await om._last_ingested_session(date(2026, 9, 8))
    assert threshold == date(2026, 9, 4)
    assert not (date(2026, 9, 4) < threshold), "Friday's row must not read as stale"


def test_the_calendar_fallback_is_what_produced_the_false_positive():
    """Pins the old behaviour as the FALLBACK, so the regression is visible if it returns."""
    # Labor Day 2026-09-07 is a Monday, so the weekend-only helper hands back Monday.
    assert om._regime_sizing_freshness_threshold(date(2026, 9, 8)) == date(2026, 9, 7)
    # ...and Friday's row is older than Monday, which is the false positive.
    assert date(2026, 9, 4) < om._regime_sizing_freshness_threshold(date(2026, 9, 8))


@pytest.mark.asyncio
async def test_a_genuinely_stale_feed_is_still_caught():
    """The fix must not blind the gate: if we hold Monday's closes and the regime row is
    still Friday's, the nightly really did fail and it must floor."""
    with patch.object(om, "get_pool",
               new=AsyncMock(return_value=_pool_returning(date(2026, 9, 8)))):
        threshold = await om._last_ingested_session(date(2026, 9, 9))
    assert date(2026, 9, 4) < threshold, "a real feed failure must still read as stale"


@pytest.mark.asyncio
async def test_an_unreadable_closes_table_falls_back_to_flooring():
    """Safe direction: if we cannot tell, we floor rather than assume fresh."""
    pool = AsyncMock()
    pool.acquire.side_effect = RuntimeError("pool saturated")
    with patch.object(om, "get_pool", new=AsyncMock(return_value=pool)):
        assert await om._last_ingested_session(date(2026, 9, 8)) is None
