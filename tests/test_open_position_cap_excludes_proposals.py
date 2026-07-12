"""#436 fork B — inert `pending_confirmation` proposals must NOT count as open positions.

A staged-paper proposal (phase='live', live_real_enabled=False) holds no broker order and cannot
be submitted (#364 removed the in-chat confirm path), so it is not a position. The 4 sites that
count "open" trades share ONE constant (`db.OPEN_POSITION_STATUSES`) so the cap safeguard and the
coverage-drift detector can never drift. These pins keep `pending_confirmation` out of that vocab
and verify both the cap query and the coverage-drift query use it — so a phantom can never again
consume a live slot (ABSI/FCEL/SNX/ACAD, 6/24-26) or trip D3 noise.
"""
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool
from agents.market_intelligence.db import OPEN_POSITION_STATUSES
from agents.market_intelligence.broker import coverage_drift


def test_open_position_statuses_excludes_pending_confirmation():
    assert "pending_confirmation" not in OPEN_POSITION_STATUSES
    assert set(OPEN_POSITION_STATUSES) == {"filled", "order_placed", "confirmed"}


def test_coverage_drift_shares_the_cap_vocabulary():
    # The detector's "open" set must BE the shared constant so it can never drift
    # from the cap safeguard (the invariant the coverage_drift comment demands).
    assert coverage_drift._OPEN_TRADE_STATUSES is OPEN_POSITION_STATUSES
    assert "pending_confirmation" not in coverage_drift._OPEN_TRADE_STATUSES


@pytest.mark.asyncio
async def test_get_open_position_count_query_excludes_proposals(monkeypatch):
    from agents.market_intelligence import db
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"n": 3})
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    n = await db.get_open_position_count()

    assert n == 3
    # the status param bound to the query must be exactly the 3-status open set
    passed = conn.fetchrow.call_args.args[1]
    assert "pending_confirmation" not in passed
    assert set(passed) == {"filled", "order_placed", "confirmed"}


@pytest.mark.asyncio
async def test_coverage_drift_open_query_excludes_proposals():
    # _fetch_open_db_trades builds the IN() list from the shared vocab — the resulting
    # query text must not admit pending_confirmation (else a stale proposal re-trips D3).
    from agents.market_intelligence.broker.coverage_drift import _fetch_open_db_trades
    _pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])

    await _fetch_open_db_trades(conn, "live")

    query = conn.fetch.call_args.args[0]
    assert "pending_confirmation" not in query
    assert "'filled'" in query and "'order_placed'" in query and "'confirmed'" in query


@pytest.mark.asyncio
async def test_check_safeguards_cap_queries_exclude_proposals(monkeypatch):
    """The ACTUAL real-money enforcement point (advisor 2026-07-11): both
    live_tracker._check_safeguards cap queries — per-mode AND per-strategy —
    must bind the shared 3-status open set, so a regression that hardcodes the
    old 4-tuple back into either query is caught here (the shared-constant import
    alone would not trip the other pins). account_mode='paper' skips the /pause
    halt branch; blocking on the per-strategy cap returns before the drawdown
    machinery, so both cap fetchvals fire with no further mocking.
    """
    from agents.market_intelligence.broker import live_tracker
    pool, conn = make_mock_pool()
    # fetchval order: open_count (per-mode, passes 0<5), strat_cap (=1), strat_open (=1 → blocks)
    conn.fetchval = AsyncMock(side_effect=[0, 1, 1])
    monkeypatch.setattr(live_tracker, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(live_tracker, "LIVE_TRADING_ENABLED", True)

    ok, reason, _mult = await live_tracker._check_safeguards(
        account_mode="paper", signal_type="magna53"
    )

    assert ok is False  # per-strategy cap blocked → both cap queries ran
    calls = conn.fetchval.call_args_list
    per_mode_status = calls[0].args[2]       # fetchval(query, account_mode, status_list)
    per_strategy_status = calls[2].args[3]   # fetchval(query, account_mode, signal_type, status_list)
    for status in (per_mode_status, per_strategy_status):
        assert "pending_confirmation" not in status
        assert set(status) == {"filled", "order_placed", "confirmed"}
