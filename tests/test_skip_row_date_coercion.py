"""Regression test for the LZB invariant breach (2026-06-13).

`high_ep_no_terminal_state` fired: a HIGH EP (LZB) arrived after the ORB window,
the scheduler called `record_skipped_trade(ticker, et_today(), ...)`, and that
dispatched over the intelligence→execution HTTP wire. `_wire_default` serialized
the `date` to an ISO string; `_insert_skipped_trade` then handed the *string*
straight to asyncpg, which raised `'str' object has no attribute 'toordinal'`
(date_encode) → 500. The skip row never landed, so the HIGH alert sat with no
terminal mi_live_trades row for ~4 days until the daily invariant caught it.

Fix: coerce str→date at the DB-write boundary in `_insert_skipped_trade` — the
same `_dd` idiom every other dated write in db.py already uses. This pins that
a wire-shaped (string) alert_date reaches asyncpg as a real `date`.
"""
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool


async def _call_insert(today_value):
    """Run _insert_skipped_trade with a mocked pool; return the args tuple the
    INSERT was executed with (so we can inspect the alert_date that hit asyncpg)."""
    from agents.market_intelligence.broker import live_tracker

    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    with patch.object(live_tracker, "get_pool", new=AsyncMock(return_value=pool)), patch(
        "agents.market_intelligence.constants.current_account_mode",
        new=lambda: "paper",
    ):
        await live_tracker._insert_skipped_trade(
            "LZB", today_value, {"ep_score": 54.0, "gap_pct": 26.5},
            None, "window:out_of_orb_window: detected 09:50 ET",
            signal_type="magna53",
        )
    assert conn.execute.await_count == 1
    return conn.execute.await_args.args


@pytest.mark.asyncio
async def test_string_alert_date_is_coerced_to_date():
    # `today` as it arrives over the HTTP wire: an ISO string. The bug let this
    # reach asyncpg unchanged and 500'd.
    args = await _call_insert("2026-06-13")
    alert_date = args[2]  # INSERT positional $2
    assert isinstance(alert_date, date), f"alert_date must be a date, got {type(alert_date)}"
    assert alert_date == date(2026, 6, 13)


@pytest.mark.asyncio
async def test_native_date_passes_through_unchanged():
    # In-process callers still pass a real date — must not be disturbed.
    args = await _call_insert(date(2026, 6, 13))
    assert args[2] == date(2026, 6, 13)


@pytest.mark.asyncio
async def test_full_wire_roundtrip_reaches_asyncpg_as_date():
    """The across-the-wire proof (advisor 2026-06-17): drive a real `date`
    through the ACTUAL `_wire_default` JSON serializer + a json round-trip
    (what `_http_call` sends), then through `_record_skipped_trade_inprocess`
    (what the execution route invokes on the receiving side). The date must
    leave as a string and arrive at asyncpg as a real `date` — closing the
    exact LZB seam, not a mocked stand-in for it."""
    import json

    from agents.market_intelligence import execution_client as ec
    from agents.market_intelligence.broker import live_tracker

    call_args = ["LZB", date(2026, 6, 13), {"ep_score": 54.0, "gap_pct": 26.5},
                 None, "window:out_of_orb_window: detected 09:50 ET"]
    call_kwargs = {"signal_type": "magna53"}

    # 1) the real send side — _wire_default turns the date into an ISO string
    body = json.dumps({"args": call_args, "kwargs": call_kwargs}, default=ec._wire_default)
    decoded = json.loads(body)
    assert decoded["args"][1] == "2026-06-13", "wire must carry alert_date as a string"
    assert isinstance(decoded["args"][1], str)

    # 2) the real receive side — the execution route splats decoded args into
    #    _record_skipped_trade_inprocess. Mock only the pool (the DB boundary).
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    with patch.object(live_tracker, "get_pool", new=AsyncMock(return_value=pool)), patch(
        "agents.market_intelligence.constants.current_account_mode",
        new=lambda: "paper",
    ):
        await ec._record_skipped_trade_inprocess(*decoded["args"], **decoded["kwargs"])

    alert_date = conn.execute.await_args.args[2]
    assert isinstance(alert_date, date), (
        f"after the full wire round-trip, asyncpg must receive a date — got {type(alert_date)}"
    )
    assert alert_date == date(2026, 6, 13)
