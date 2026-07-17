"""#436 self-heal — expire_stale_proposals pins (per-mode shape, review 7/17).

The staged-paper path leaves unconfirmed `pending_confirmation` rows with no
broker order; nothing expired them (the ABSI/FCEL/SNX/ACAD class sat 10-12d
until a 7/06 hand cleanup). Pins: (1) the UPDATE targets exactly the phantom
shape (pending_confirmation + NULL entry_order_id + prior-ET-day) WITH the
account_mode filter (dual-account backbone invariant), iterating only the
modes this container is authoritative for; (2) one audit row per expired
proposal; (3) NO broker calls; (4) RAISES on DB failure — the callers'
notify_job_failure is the alarm (an internal swallow hid reaper breakage,
the exact #436 class); (5) ENABLE_LIVE_MODE=false never touches live rows.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker.skip_reasons import WINDOW_PROPOSAL_EXPIRED


def _row(i, tk, mode):
    return {"id": i, "ticker": tk, "account_mode": mode,
            "proposed_at": dt.datetime(2026, 6, 24, 13, 31)}


@pytest.mark.asyncio
async def test_expires_per_mode_and_audits_each(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_MODE", "true")
    import agents.market_intelligence.constants as consts
    monkeypatch.setattr(consts, "ENABLE_LIVE_MODE", True)
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[
        [],                                        # paper: nothing stale
        [_row(232, "ABSI", "live"), _row(233, "FCEL", "live")],  # live: 2 phantoms
    ])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(om, "log_audit_event", audit)
    cancel = AsyncMock()
    monkeypatch.setattr(om.alpaca, "cancel_order", cancel, raising=False)

    n = await om.expire_stale_proposals()

    assert n == 2
    assert conn.fetch.await_count == 2                 # one query per mode
    sql = conn.fetch.await_args_list[0].args[0]
    assert "account_mode = $1" in sql                  # the backbone invariant
    assert "status = 'pending_confirmation'" in sql
    assert "entry_order_id IS NULL" in sql
    assert "SET status = 'expired'" in sql
    assert WINDOW_PROPOSAL_EXPIRED in sql              # bounded skip-reason vocabulary
    assert "America/New_York" in sql                   # ET day boundary
    modes_queried = [c.args[1] for c in conn.fetch.await_args_list]
    assert modes_queried == ["paper", "live"]
    assert audit.await_count == 2
    assert "ABSI" in audit.await_args_list[0].args[1]
    cancel.assert_not_awaited()                        # zero broker calls


@pytest.mark.asyncio
async def test_paper_only_container_never_touches_live(monkeypatch):
    import agents.market_intelligence.constants as consts
    monkeypatch.setattr(consts, "ENABLE_LIVE_MODE", False)
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())

    n = await om.expire_stale_proposals()

    assert n == 0
    assert conn.fetch.await_count == 1
    assert conn.fetch.await_args.args[1] == "paper"    # live rows untouchable


@pytest.mark.asyncio
async def test_raises_on_db_error_so_callers_notify(monkeypatch):
    monkeypatch.setattr(om, "get_pool", AsyncMock(side_effect=RuntimeError("pool down")))
    with pytest.raises(RuntimeError, match="pool down"):
        await om.expire_stale_proposals()              # callers' except -> notify_job_failure
