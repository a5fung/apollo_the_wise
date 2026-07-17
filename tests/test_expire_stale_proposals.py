"""#436 self-heal — expire_stale_proposals pins.

The staged-paper path leaves unconfirmed `pending_confirmation` rows with no
broker order; nothing expired them (the ABSI/FCEL/SNX/ACAD class sat 10-12d
until a 7/06 hand cleanup). Pins: (1) the UPDATE targets exactly the phantom
shape (pending_confirmation + NULL entry_order_id + proposed_at before today
ET) and flips to 'expired' with the bounded WINDOW_PROPOSAL_EXPIRED reason;
(2) one audit row per expired proposal; (3) NO broker calls; (4) never raises
(fail-quiet 0 on DB error — the cleanup jobs go on).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker.skip_reasons import WINDOW_PROPOSAL_EXPIRED


@pytest.mark.asyncio
async def test_expires_phantoms_and_audits_each(monkeypatch):
    pool, conn = make_mock_pool()
    import datetime as dt
    conn.fetch = AsyncMock(return_value=[
        {"id": 232, "ticker": "ABSI", "account_mode": "live",
         "proposed_at": dt.datetime(2026, 6, 24, 13, 31)},
        {"id": 233, "ticker": "FCEL", "account_mode": "live",
         "proposed_at": dt.datetime(2026, 6, 24, 13, 32)},
    ])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(om, "log_audit_event", audit)
    cancel = AsyncMock()
    monkeypatch.setattr(om.alpaca, "cancel_order", cancel, raising=False)

    n = await om.expire_stale_proposals()

    assert n == 2
    sql = conn.fetch.await_args.args[0]
    assert "status = 'pending_confirmation'" in sql
    assert "entry_order_id IS NULL" in sql
    assert "SET status = 'expired'" in sql
    assert WINDOW_PROPOSAL_EXPIRED in sql          # bounded skip-reason vocabulary
    assert "America/New_York" in sql               # ET day boundary, not container UTC
    assert audit.await_count == 2
    assert "ABSI" in audit.await_args_list[0].args[1]
    cancel.assert_not_awaited()                    # zero broker calls — no orders exist


@pytest.mark.asyncio
async def test_never_raises_on_db_error(monkeypatch):
    monkeypatch.setattr(om, "get_pool", AsyncMock(side_effect=RuntimeError("pool down")))
    n = await om.expire_stale_proposals()
    assert n == 0                                  # cleanup jobs proceed
