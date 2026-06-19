"""#345 — manual real-money trading halt (`/pause`). This gate is load-bearing
safety, so the tests pin the contract that makes it trustworthy:
  (a) block the LIVE path when the operator has halted;
  (b) FAIL-SAFE — block the LIVE path when the halt flag can't be read (DB error),
      under a DISTINCT reason so the operator is never told "you paused" wrongly;
  (c) never consult or block the paper/shadow path (telemetry keeps running).
"""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import agents.market_intelligence.db as db
from agents.market_intelligence.broker import live_tracker
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_TRADING_PAUSED,
    INFRA_HALT_STATE_UNREADABLE,
)


def _mock_get_pool(fetchrow_return=None, fetchrow_raises=None):
    """A get_pool() stand-in whose acquired conn.fetchrow returns/raises as configured."""
    conn = MagicMock()
    if fetchrow_raises is not None:
        conn.fetchrow = AsyncMock(side_effect=fetchrow_raises)
    else:
        conn.fetchrow = AsyncMock(return_value=fetchrow_return)

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = _acquire

    async def _get_pool():
        return pool

    return _get_pool


# ── get_manual_halt_state fail-direction (the load-bearing contract) ──────────

def test_halt_state_on():
    with patch.object(db, "get_pool", _mock_get_pool(fetchrow_return={"state": "on"})):
        assert asyncio.run(db.get_manual_halt_state()) == "on"


def test_halt_state_off_when_no_row():
    with patch.object(db, "get_pool", _mock_get_pool(fetchrow_return=None)):
        assert asyncio.run(db.get_manual_halt_state()) == "off"


def test_halt_state_off_when_state_off():
    with patch.object(db, "get_pool", _mock_get_pool(fetchrow_return={"state": "off"})):
        assert asyncio.run(db.get_manual_halt_state()) == "off"


def test_halt_state_unreadable_on_db_error_is_failsafe():
    # The contract: a read error must NOT silently resolve to "off" (which would
    # let real money trade during the very failure the halt exists to survive).
    with patch.object(db, "get_pool", _mock_get_pool(fetchrow_raises=RuntimeError("db down"))):
        assert asyncio.run(db.get_manual_halt_state()) == "unreadable"


# ── the _check_safeguards gate ────────────────────────────────────────────────

def _run_safeguards(halt_state, account_mode):
    with patch.object(live_tracker, "LIVE_TRADING_ENABLED", True), \
         patch.object(live_tracker, "get_manual_halt_state", AsyncMock(return_value=halt_state)):
        return asyncio.run(live_tracker._check_safeguards(account_mode=account_mode))


def test_gate_blocks_live_when_halted():
    ok, reason, mult = _run_safeguards("on", "live")
    assert ok is False
    assert reason == BLOCK_TRADING_PAUSED
    assert mult == 0.0


def test_gate_failsafe_blocks_live_when_unreadable():
    ok, reason, mult = _run_safeguards("unreadable", "live")
    assert ok is False
    assert reason == INFRA_HALT_STATE_UNREADABLE  # distinct reason, NOT "you paused"
    assert mult == 0.0


def test_gate_skips_halt_for_paper_mode():
    # Paper/shadow must be UNAFFECTED — the halt is consulted only for the live path.
    # Even with the flag 'on', a paper entry must not consult it; it should fall
    # through to the pool work (which we trip with a sentinel to prove flow passed).
    sentinel = RuntimeError("reached pool — halt gate correctly skipped for paper")
    halt_mock = AsyncMock(return_value="on")

    async def _boom():
        raise sentinel

    with patch.object(live_tracker, "LIVE_TRADING_ENABLED", True), \
         patch.object(live_tracker, "get_manual_halt_state", halt_mock), \
         patch.object(live_tracker, "get_pool", _boom):
        raised = None
        try:
            asyncio.run(live_tracker._check_safeguards(account_mode="paper"))
        except RuntimeError as e:
            raised = e
    assert raised is sentinel       # flow passed the halt block to the pool
    halt_mock.assert_not_awaited()  # the halt was never consulted for paper
