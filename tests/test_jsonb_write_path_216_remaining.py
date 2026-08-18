"""#216 follow-up — the THREE writers fenced off from yesterday's fix, now closed.

Same bug class as #177/#179/#287/#216: `db.py::get_pool` registers a jsonb type codec
whose encoder is plain `json.dumps`, applied AUTOMATICALLY to every jsonb bind param.
A call site that ALSO `json.dumps()`s the value before binding it to a `$N::jsonb` (or
implicitly-jsonb, via INSERT-target-column inference) param double-encodes — the codec
re-serialises the already-serialised string, so the column lands as
`jsonb_typeof='string'` holding literal JSON text instead of a real array/object.

Yesterday's #216 fix (`tests/test_jsonb_write_path_216.py`) covered 9 db.py functions.
Three writers were fenced off as out of scope and kept corrupting:

  1. strategies/registry.py::update_strategy — mi_strategies.promotion_thresholds (dict)
  2. backtester/tracker.py — mi_paper_trades.entries / .exits / .running_closes (list)
  3. broker/order_manager.py, broker/trade_stream.py, broker/order_ingest.py —
     mi_live_orders.raw_response (dict) — confirmed re-corrupting live (275/280 rows,
     nightly guard caught 3 NEW string rows overnight 2026-08-17→18).

Fix: route every one of these through the same two helpers db.py already ships —
`_jsonb_param` (dict-shaped) / `_jsonb_list_param` (list-shaped) — instead of
`json.dumps()`. No SQL, no `::jsonb` cast, no order/sizing/stop/target logic changed
anywhere; this is serialisation only.

Mutation proof (2026-08-18): ran this file against `git stash`-ed changes (i.e. the
pre-fix code, still calling `json.dumps()` at every site below) — every dict/list-typed
assertion in this file failed with the corrupted `str` type. `git stash pop` restored
the fix and the full file passed again.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import make_mock_pool

# conftest STUBS agents.market_intelligence.backtester.tracker (it drags in heavy deps
# the suite deliberately mocks), so a plain import hands back a MagicMock and every
# assertion below would pass without executing one line of the real write path — a
# green test proving nothing. Same workaround as test_partial_visible_in_trades_549.py:
# compile just the functions under test, with their two tiny dependencies, into a
# private namespace, sourced from the real file so it cannot drift from what ships.
from agents.market_intelligence.db import _jsonb_list_param as _real_jsonb_list_param

_TRACKER_SRC = pathlib.Path(
    "agents/market_intelligence/backtester/tracker.py").read_text(encoding="utf-8")


def _extract_tracker_fn(name: str) -> str:
    key = f"async def {name}("
    i = _TRACKER_SRC.find(key)
    if i < 0:
        key = f"def {name}("
        i = _TRACKER_SRC.index(key)
    candidates = [x for x in (
        _TRACKER_SRC.find("\nasync def ", i + 1),
        _TRACKER_SRC.find("\ndef ", i + 1),
    ) if x > 0]
    end = min(candidates) if candidates else len(_TRACKER_SRC)
    return _TRACKER_SRC[i:end]


_tracker_ns: dict = {"json": json, "_jsonb_list_param": _real_jsonb_list_param}
for _fn in ("parse_json_list", "_insert_paper_trade",
            "_update_paper_trade_extras", "_update_paper_trade"):
    exec(_extract_tracker_fn(_fn), _tracker_ns)  # noqa: S102 — real source, not a fixture
parse_json_list = _tracker_ns["parse_json_list"]
_insert_paper_trade = _tracker_ns["_insert_paper_trade"]
_update_paper_trade_extras = _tracker_ns["_update_paper_trade_extras"]
_update_paper_trade = _tracker_ns["_update_paper_trade"]


# ═══════════════════════ 1. registry.py — promotion_thresholds (dict) ═══════════════


@pytest.mark.asyncio
async def test_update_strategy_promotion_thresholds_param_is_dict(monkeypatch):
    from agents.market_intelligence.strategies import registry

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"strategy_id": "magna53"})
    monkeypatch.setattr(registry, "get_pool", AsyncMock(return_value=pool))
    # get_strategy() re-load after the mutate — stub so the test doesn't need a
    # second full row shape; the mutation under test is the UPDATE's own param.
    monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=None))

    await registry.update_strategy(
        "magna53", promotion_thresholds={"shadow_to_paper": {"min_closed": 30}},
    )

    assert conn.fetchrow.await_count == 1
    sql, *args = conn.fetchrow.await_args[0]
    assert "promotion_thresholds = $1::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    pt_param = args[0]
    assert isinstance(pt_param, dict), (
        f"promotion_thresholds param must be a plain dict (codec encodes exactly "
        f"once) — got {type(pt_param)}. A json.dumps() pre-encode here double-encodes "
        "into jsonb_typeof='string' (#216) — this is the SECOND writer that explains "
        "mi_strategies.promotion_thresholds' 6/7 partial-corruption ratio."
    )
    assert not isinstance(pt_param, str)
    assert pt_param["shadow_to_paper"]["min_closed"] == 30


@pytest.mark.asyncio
async def test_load_all_tolerates_legacy_string_promotion_thresholds(monkeypatch):
    """Reader check: `_load_all` already guards with `isinstance(thresholds, str)` —
    confirm a legacy double-encoded row (written before this fix) still loads instead
    of raising or silently losing the thresholds."""
    from agents.market_intelligence.strategies import registry

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{
        "strategy_id": "magna53", "name": "MAGNA53 EP", "family": "ep",
        "phase": "live", "enabled": True, "signal_type": "magna53_ep",
        "outcomes_table": "mi_live_trades", "promotion_model": "paired_r",
        # double-encoded #216-shaped corruption: real JSON text, not a native object
        "promotion_thresholds": '{"shadow_to_paper": {"min_closed": 30}}',
        "notes": None, "live_real_enabled": True,
    }])
    monkeypatch.setattr(registry, "get_pool", AsyncMock(return_value=pool))

    out = await registry._load_all()

    assert out["magna53"].promotion_thresholds == {"shadow_to_paper": {"min_closed": 30}}


# ═══════════════════ 2. backtester/tracker.py — mi_paper_trades (list) ══════════════


@pytest.mark.asyncio
async def test_insert_paper_trade_entries_exits_running_closes_are_lists():
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _tracker_ns["get_pool"] = AsyncMock(return_value=pool)

    await _insert_paper_trade({
        "ticker": "TEST", "alert_date": date(2026, 8, 17), "ep_score": 90,
        "status": "open",
        "entries": [{"time": "2026-08-17T09:31:00", "price": 10.0, "attempt": 1}],
        "exits": [{"time": "2026-08-17T10:00:00", "price": 10.5, "reason": "partial"}],
        "running_closes": [10.0, 10.2],
    })

    assert conn.execute.await_count == 1
    sql, *args = conn.execute.await_args[0]
    assert "$8::jsonb" in sql and "$9::jsonb" in sql and "$22::jsonb" in sql, (
        "the ::jsonb casts must stay in the SQL"
    )
    entries_param, exits_param, running_closes_param = args[7], args[8], args[21]
    for name, param in (("entries", entries_param), ("exits", exits_param),
                        ("running_closes", running_closes_param)):
        assert isinstance(param, list), (
            f"{name} param must be a plain list (codec encodes exactly once) — got "
            f"{type(param)}. A json.dumps() pre-encode here double-encodes (#216)."
        )
        assert not isinstance(param, str)
    assert entries_param[0]["price"] == 10.0
    assert exits_param[0]["reason"] == "partial"
    assert running_closes_param == [10.0, 10.2]


@pytest.mark.asyncio
async def test_update_paper_trade_extras_running_closes_param_is_list():
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _tracker_ns["get_pool"] = AsyncMock(return_value=pool)

    await _update_paper_trade_extras(3, True, False, [10.0, 10.2, 10.5])

    assert conn.execute.await_count == 1
    sql, *args = conn.execute.await_args[0]
    assert "running_closes = $4::jsonb" in sql
    rc_param = args[3]
    assert isinstance(rc_param, list), (
        f"running_closes param must be a plain list — got {type(rc_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216)."
    )
    assert not isinstance(rc_param, str)
    assert rc_param == [10.0, 10.2, 10.5]


@pytest.mark.asyncio
async def test_update_paper_trade_exits_param_is_list():
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _tracker_ns["get_pool"] = AsyncMock(return_value=pool)

    await _update_paper_trade(3, {
        "status": "closed",
        "exits": [{"time": "2026-08-17T10:00:00", "price": 9.5, "reason": "stop_hit"}],
        "remaining_shares": 0, "stop_price": None, "total_pnl": -50.0, "hold_days": 1,
        "closed_at": None,
    })

    assert conn.execute.await_count == 1
    sql, *args = conn.execute.await_args[0]
    assert "exits = $3::jsonb" in sql
    exits_param = args[2]
    assert isinstance(exits_param, list), (
        f"exits param must be a plain list — got {type(exits_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216)."
    )
    assert not isinstance(exits_param, str)
    assert exits_param[0]["reason"] == "stop_hit"


def test_parse_json_list_tolerates_legacy_string():
    """Reader check: `parse_json_list` (used by every mi_paper_trades jsonb reader —
    format_trade_attempts, _attempt_count, update_open_positions) already tolerates a
    legacy double-encoded string instead of raising."""
    assert parse_json_list('[{"price": 10.0, "reason": "partial"}]') == (
        [{"price": 10.0, "reason": "partial"}]
    )
    assert parse_json_list([{"price": 10.0}]) == [{"price": 10.0}]
    assert parse_json_list(None) == []


# ═══════════════ 3. mi_live_orders.raw_response (dict) — three writers ══════════════


@pytest.mark.asyncio
async def test_upsert_stop_order_raw_response_param_is_dict():
    """order_ingest.py::_upsert_stop_order — no explicit ::jsonb cast in the SQL, but
    $9 resolves to raw_response's jsonb column type from the INSERT target list, so
    the codec still applies. Same bug, no cast needed to trigger it."""
    from agents.market_intelligence.broker import order_ingest as oi

    conn = MagicMock()
    conn.execute = AsyncMock()
    order = {
        "id": "stop-99", "symbol": "TEST", "side": "sell", "type": "stop",
        "qty": 100, "stop_price": 19.5, "status": "new",
    }

    await oi._upsert_stop_order(conn, 5, order)

    assert conn.execute.await_count == 1
    sql, *args = conn.execute.await_args[0]
    raw_response_param = args[-1]
    assert isinstance(raw_response_param, dict), (
        f"raw_response param must be a plain dict — got {type(raw_response_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216) even with no explicit "
        "::jsonb cast, because the INSERT target column type still resolves to jsonb."
    )
    assert not isinstance(raw_response_param, str)
    assert raw_response_param["id"] == "stop-99"


@pytest.mark.asyncio
async def test_execute_full_exit_raw_response_param_is_dict(monkeypatch):
    """order_manager.py::execute_full_exit — the LIVE full-exit raw_response writer."""
    from agents.market_intelligence.broker import order_manager as om

    pool, conn = make_mock_pool()
    trade_row = {
        "id": 9, "ticker": "TEST", "remaining_shares": 50.0,
        "account_mode": "live", "stop_order_id": "stop-1",
    }
    conn.fetchrow = AsyncMock(side_effect=[trade_row, None])  # trade, then no pending exit
    conn.execute = AsyncMock()
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om.alpaca, "cancel_order", AsyncMock(return_value=True))
    monkeypatch.setattr(
        om.alpaca, "close_position",
        AsyncMock(return_value={"id": "close-order-1", "status": "new"}),
    )
    monkeypatch.setattr(om, "send_telegram_message", AsyncMock(return_value=True))

    result = await om.execute_full_exit(9, "test_reason")

    assert result is True
    calls = [c for c in conn.execute.await_args_list if "raw_response" in c.args[0]]
    assert len(calls) == 1
    sql, *args = calls[0].args
    assert "$7::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    raw_response_param = args[-1]
    assert isinstance(raw_response_param, dict), (
        f"raw_response param must be a plain dict — got {type(raw_response_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216); this is the writer "
        "the nightly guard caught re-corrupting overnight (0 -> 3 string rows)."
    )
    assert not isinstance(raw_response_param, str)
    assert raw_response_param["id"] == "close-order-1"


@pytest.mark.asyncio
async def test_submit_entry_raw_response_params_are_dicts(monkeypatch):
    """order_manager.py::submit_entry — the ORB-open entry writer. This is the site
    with PROVEN live corruption: the nightly guard caught mi_live_orders.raw_response
    going 0 -> 3 string rows overnight as new orders were placed (2026-08-17->18),
    and submit_entry is what fires on every new ORB entry. Reuses the existing
    #500 fixture (test_500_price_aware_entry.py) so this exercises the SAME wiring
    already pinned for entry-order mechanics, not a bespoke stand-in."""
    from agents.market_intelligence.broker import order_manager as om
    from tests.test_500_price_aware_entry import _wire_submit_entry, _entry_insert_args

    fake, conn, _ = _wire_submit_entry(monkeypatch, {"price": 10.40})  # below ORB high -> bracket

    result = await om.submit_entry(7)

    assert result is not None
    fake.extract_stop_leg_id.assert_called()  # confirms the OTO stop-leg INSERT also fired

    entry_args = _entry_insert_args(conn)
    entry_raw_response = entry_args[-2]  # last positional is entry_type, not raw_response
    assert isinstance(entry_raw_response, dict), (
        f"entry-order raw_response param must be a plain dict — got "
        f"{type(entry_raw_response)}. This is the writer the nightly guard caught "
        "re-corrupting overnight (0 -> 3 string rows, #216)."
    )
    assert not isinstance(entry_raw_response, str)
    assert entry_raw_response["id"] == "ord-1"

    stop_leg_calls = [
        c for c in conn.execute.await_args_list
        if "INSERT INTO mi_live_orders" in c.args[0] and "'stop_loss'" in c.args[0]
    ]
    assert len(stop_leg_calls) == 1
    stop_leg_raw_response = stop_leg_calls[0].args[-1]
    assert isinstance(stop_leg_raw_response, dict), (
        f"OTO stop-leg raw_response param must be a plain dict — got "
        f"{type(stop_leg_raw_response)}."
    )
    assert not isinstance(stop_leg_raw_response, str)
    assert stop_leg_raw_response["parent_entry_order"] == "ord-1"


def _ws_data(order_id: str = "order-1", symbol: str = "TEST"):
    return SimpleNamespace(order=SimpleNamespace(id=order_id, symbol=symbol))


@pytest.mark.asyncio
async def test_process_entry_fill_remediation_stop_raw_response_param_is_dict(monkeypatch):
    """trade_stream.py::_process_entry_fill — the fill-path stop-remediation writer
    (fires when the OTO bracket's stop leg comes back missing)."""
    from agents.market_intelligence.broker import trade_stream as ts

    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)  # no DB-side stop_order_id either
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts.alpaca, "extract_stop_leg_id", lambda o: None)
    monkeypatch.setattr(
        ts.alpaca, "get_order",
        AsyncMock(return_value=SimpleNamespace(id="entry-1", legs=None)),
    )
    monkeypatch.setattr(
        ts.alpaca, "place_stop_order",
        AsyncMock(return_value={"id": "new-stop-77", "status": "new"}),
    )
    monkeypatch.setattr(ts, "log_audit_event", AsyncMock())
    monkeypatch.setattr(ts, "send_telegram_message", AsyncMock(return_value=True))

    trade = {"id": 41, "ticker": "TEST", "entry_shares": 100, "orb_low": 18.50,
              "entry_attempt": 1}
    order = SimpleNamespace(id="entry-1")

    await ts._process_entry_fill(trade, order, 20.00, 100.0, pool, "live")

    calls = [c for c in conn.execute.await_args_list if "raw_response" in c.args[0]]
    assert len(calls) == 1
    sql, *args = calls[0].args
    assert "$7::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    raw_response_param = args[-1]
    assert isinstance(raw_response_param, dict), (
        f"raw_response param must be a plain dict — got {type(raw_response_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216)."
    )
    assert not isinstance(raw_response_param, str)
    assert raw_response_param["id"] == "new-stop-77"


async def _run_terminal_snapshot(monkeypatch):
    from agents.market_intelligence.broker import trade_stream as ts
    from agents.market_intelligence.broker import order_manager as om

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={
        "id": 7, "ticker": "TEST", "gap_pct": 20.0, "ep_score": 80.0,
        "entry_price": 10.0, "stop_price": 9.0, "regime": "Uptrend",
        "signal_type": "magna53",
    })
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", AsyncMock())
    monkeypatch.setattr(
        om, "alpaca", MagicMock(get_latest_trade=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(ts, "send_telegram_message", AsyncMock(return_value=True))

    await ts._handle_cancel_or_reject(_ws_data(order_id="ord-1", symbol="TEST"),
                                      "rejected", "live")
    return conn


@pytest.mark.asyncio
async def test_terminal_order_snapshot_merge_param_is_dict(monkeypatch):
    """trade_stream.py::_handle_cancel_or_reject — the terminal-snapshot
    jsonb_build_object merge into raw_response on an entry cancel/reject."""
    conn = await _run_terminal_snapshot(monkeypatch)

    calls = [c for c in conn.execute.await_args_list if "raw_response" in c.args[0]]
    assert len(calls) == 1
    sql, order_id, event_norm, snapshot_param = calls[0].args
    assert "jsonb_build_object('terminal', $3::jsonb)" in sql, (
        "the ::jsonb cast must stay in the SQL"
    )
    assert isinstance(snapshot_param, dict), (
        f"terminal snapshot param must be a plain dict — got {type(snapshot_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216) inside the "
        "jsonb_build_object merge, nesting a STRING under 'terminal' instead of an "
        "object."
    )
    assert not isinstance(snapshot_param, str)
    assert "status" in snapshot_param


@pytest.mark.asyncio
async def test_partial_exit_restore_stop_raw_response_param_is_dict(monkeypatch):
    """trade_stream.py::_handle_cancel_or_reject — the stop-restore writer that fires
    when a partial-exit sell is cancelled/rejected before it fills."""
    from agents.market_intelligence.broker import trade_stream as ts
    from agents.market_intelligence.broker import order_manager as om

    pool, conn = make_mock_pool()
    pending_exit_row = {
        "trade_id": 77, "purpose": "partial_exit",
        "raw_response": {"order_class": "limit"},
    }
    trade_row = {
        "id": 77, "ticker": "TEST", "remaining_shares": 60.0,
        "stop_price": 21.0, "stop_order_id": "old-stop-5",
    }
    conn.fetchrow = AsyncMock(side_effect=[
        None,               # 1. entry-order lookup — miss
        None,               # 2. stop-leg lookup — miss
        pending_exit_row,   # 3. pending managed-exit UPDATE...RETURNING
        trade_row,          # 4. mi_live_trades lookup for the restore
    ])
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts.alpaca, "cancel_order", AsyncMock(return_value=True))
    monkeypatch.setattr(
        ts.alpaca, "place_stop_order",
        AsyncMock(return_value={"id": "restored-stop-1", "status": "new"}),
    )
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())
    monkeypatch.setattr(ts, "send_telegram_message", AsyncMock(return_value=True))

    order = SimpleNamespace(id="sell-order-1", symbol="TEST")
    data = SimpleNamespace(order=order)
    await ts._handle_cancel_or_reject(data, "canceled", "live")

    calls = [c for c in conn.execute.await_args_list if "raw_response" in c.args[0]]
    assert len(calls) == 1
    sql, *args = calls[0].args
    assert "$7::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    raw_response_param = args[-1]
    assert isinstance(raw_response_param, dict), (
        f"raw_response param must be a plain dict — got {type(raw_response_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216)."
    )
    assert not isinstance(raw_response_param, str)
    assert raw_response_param["id"] == "restored-stop-1"


@pytest.mark.asyncio
async def test_pending_exit_raw_response_read_tolerates_legacy_string(monkeypatch):
    """Reader check: `_handle_cancel_or_reject`'s pending-exit branch already guards
    `pending_exit["raw_response"]` with `isinstance(_raw, str): json.loads(...)`
    (trade_stream.py ~1763-1772) BEFORE checking order_class. Drive the real function
    with a legacy double-encoded STRING raw_response (as a pre-fix row would read back)
    and confirm it parses through to the restore branch instead of raising or
    mis-reading the string as an OCO parent."""
    from agents.market_intelligence.broker import trade_stream as ts
    from agents.market_intelligence.broker import order_manager as om

    pool, conn = make_mock_pool()
    pending_exit_row = {
        "trade_id": 77, "purpose": "partial_exit",
        # legacy #216-shaped corruption: real JSON text, not a native object
        "raw_response": '{"order_class": "limit"}',
    }
    trade_row = {
        "id": 77, "ticker": "TEST", "remaining_shares": 60.0,
        "stop_price": 21.0, "stop_order_id": "old-stop-5",
    }
    conn.fetchrow = AsyncMock(side_effect=[None, None, pending_exit_row, trade_row])
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts.alpaca, "cancel_order", AsyncMock(return_value=True))
    monkeypatch.setattr(
        ts.alpaca, "place_stop_order",
        AsyncMock(return_value={"id": "restored-stop-1", "status": "new"}),
    )
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())
    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "send_telegram_message", _capture)

    order = SimpleNamespace(id="sell-order-1", symbol="TEST")
    data = SimpleNamespace(order=order)
    await ts._handle_cancel_or_reject(data, "canceled", "live")  # must NOT raise

    # A string "limit" raw_response must NOT be mistaken for an OCO parent — it
    # must reach the plain-partial stop-restore branch (proof: the restore Telegram
    # fired, not the OCO-parent-cancel path, which sends a different message).
    assert any("Stop restored" in m for m in sent)
