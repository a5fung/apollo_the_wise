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
