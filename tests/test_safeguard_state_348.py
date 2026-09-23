"""#348 — the generic `mi_safeguard_state` get/set helpers (db.get_safeguard_state /
db.set_safeguard_state), and the two real-DB-path callers that previously had NO
test coverage of their own internals (drawdown_breaker.read_breaker_state,
kill_scale_bands.get_last_band).

Design under test: `get_safeguard_state` does the bare SELECT and returns the row
(or None) — it does NOT catch exceptions or pick a fail-direction. Every caller
keeps its OWN try/except (or lack of one) unchanged. These tests pin that contract
directly, since it's the one property that makes the whole consolidation safe.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock

from agents.market_intelligence import db
from agents.market_intelligence.broker import drawdown_breaker as dd
from agents.market_intelligence import kill_scale_bands as ksb

from tests.conftest import make_mock_pool


# ── db.get_safeguard_state — generic read, no fail-direction of its own ──────


def test_get_safeguard_state_returns_row_on_hit(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"state": "on", "last_transition_at": None})
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    row = asyncio.run(db.get_safeguard_state("some_toggle", "paper"))

    assert row == {"state": "on", "last_transition_at": None}
    args = conn.fetchrow.await_args[0]
    assert "SELECT * FROM mi_safeguard_state" in args[0]
    assert args[1:] == ("some_toggle", "paper")


def test_get_safeguard_state_returns_none_on_missing_row(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    assert asyncio.run(db.get_safeguard_state("some_toggle", "paper")) is None


def test_get_safeguard_state_propagates_errors_uncaught(monkeypatch):
    # The whole safety argument: this helper must NOT swallow — every caller's
    # own try/except (or absence of one) is what determines the fail-direction.
    async def _boom():
        raise RuntimeError("db unreachable")
    monkeypatch.setattr(db, "get_pool", _boom)
    with pytest.raises(RuntimeError):
        asyncio.run(db.get_safeguard_state("some_toggle", "paper"))


# ── db.set_safeguard_state — always-bump (default) ────────────────────────────


def test_set_safeguard_state_always_bump_issues_the_shared_upsert(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    result = asyncio.run(db.set_safeguard_state("some_toggle", "paper", "on"))

    assert result is None
    args = conn.execute.await_args[0]
    assert "INSERT INTO mi_safeguard_state" in args[0]
    assert "ON CONFLICT (safeguard, account_mode) DO UPDATE" in args[0]
    assert "SET state = EXCLUDED.state, last_transition_at = NOW(), updated_at = NOW()" in args[0]
    assert args[1:] == ("some_toggle", "paper", "on")


def test_set_safeguard_state_always_bump_does_not_swallow_errors(monkeypatch):
    async def _boom():
        raise RuntimeError("db unreachable")
    monkeypatch.setattr(db, "get_pool", _boom)
    with pytest.raises(RuntimeError):
        asyncio.run(db.set_safeguard_state("some_toggle", "paper", "on"))


# ── db.set_safeguard_state — conditional-bump (bump_on_change=True) ──────────


def test_set_safeguard_state_bump_on_change_delegates_to_claim(monkeypatch):
    # #348 finding: this path is NOT used by any migrated caller today (the two
    # existing conditional-bump callers — drawdown_breaker.recompute_drawdown_state,
    # kill_scale_bands.set_last_band — already share claim_safeguard_state_transition
    # directly, since 2026-07-03, and were deliberately left untouched). This test
    # pins that the kwarg, if a future caller uses it, correctly delegates and
    # returns the bool contract instead of the always-bump None.
    calls = []

    async def fake_claim(safeguard, account_mode, new_state):
        calls.append((safeguard, account_mode, new_state))
        return True

    monkeypatch.setattr(db, "claim_safeguard_state_transition", fake_claim)
    result = asyncio.run(
        db.set_safeguard_state("some_toggle", "live", "TRIPPED", bump_on_change=True)
    )
    assert result is True
    assert calls == [("some_toggle", "live", "TRIPPED")]


# ── drawdown_breaker.read_breaker_state — previously untested real path ──────
#
# NOTE (a #348 testability nuance, not a runtime behavior change): read_breaker_state
# now reaches the DB through db.get_safeguard_state, whose OWN function body resolves
# `get_pool` in db.py's module namespace — NOT drawdown_breaker's imported binding. So
# intercepting the DB call for THIS function requires patching db.get_pool (as below),
# not dd.get_pool. dd.get_pool is still the right patch target for recompute_drawdown_state
# (unchanged by this refactor, still calls get_pool() directly) — see test_drawdown_tiered.py.


def test_read_breaker_state_fail_open_ok_on_db_error(monkeypatch):
    async def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "get_pool", _boom)
    assert asyncio.run(dd.read_breaker_state("live")) == dd._STATE_OK


def test_read_breaker_state_fail_open_ok_on_missing_row(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    assert asyncio.run(dd.read_breaker_state("live")) == dd._STATE_OK


def test_read_breaker_state_returns_persisted_tier(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"state": "REDUCE"})
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    assert asyncio.run(dd.read_breaker_state("live")) == "REDUCE"


# ── kill_scale_bands.get_last_band — previously untested real path ───────────


def test_get_last_band_missing_row_returns_none_none(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    assert asyncio.run(ksb.get_last_band("live")) == (None, None)


def test_get_last_band_returns_state_and_since(monkeypatch):
    import datetime as _dt
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={
        "state": "SCALE",
        "last_transition_at": _dt.datetime(2026, 7, 1, 12, 0, tzinfo=_dt.timezone.utc),
    })
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    assert asyncio.run(ksb.get_last_band("live")) == ("SCALE", "2026-07-01")


def test_get_last_band_propagates_errors_uncaught(monkeypatch):
    # get_last_band has no try/except today — a DB error must still propagate,
    # not resolve to a silent (None, None).
    async def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "get_pool", _boom)
    with pytest.raises(RuntimeError):
        asyncio.run(ksb.get_last_band("live"))
