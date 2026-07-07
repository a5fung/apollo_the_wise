"""#183 (2026-07-06/07) — wire-boundary enum normalization + the two site
hardenings + the two dead-fallback-path revival pins.

Bug class (verified live 7/6): `alpaca_client._order_to_dict` stringified
alpaca-py enums raw — on Python 3.12, `str(OrderStatus.NEW)` == "OrderStatus.NEW",
so every wire dict carried qualified strings for status/side/type. Sites
comparing against plain literals (order_manager.check_fills, _check_day1_reentry,
the :396 cancel-like tuple, audit_invariants' never-naked coverage fallback)
silently never matched. The WS stream (raw payloads) masked it — the casualties
were all FALLBACK paths.

Fix: `_enum_value()` normalizes once at the `_order_to_dict`/`_position_to_dict`
boundary. Two sites additionally needed hardening (boundary alone wasn't
enough): the :396 cancel/expired/rejected tuple (missing one-L "canceled") and
audit_invariants' sell-side coverage check (hardened to `.endswith("sell")`,
the #128 idiom, as defense-in-depth).

The one real risk (audit §5): the fix brings DEAD fallback paths back to life.
Tests 3 and 6 pin that the revival is safe — the dedup/attempt-count guards
that were always there (but never exercised, because the paths were dead)
actually hold once the paths go live.

Full spec: docs/analysis/183_enum_boundary_audit_2026-07-06.md
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.market_intelligence.broker.alpaca_client import _enum_value, _order_to_dict
from agents.market_intelligence.broker.order_manager import (
    _CANCEL_LIKE_ORDER_STATUSES,
    MAX_ENTRY_ATTEMPTS,
    check_fills,
    _check_day1_reentry,
)


# ── shared pool stub (mirrors tests/test_order_status_reconcile.py's _stub_pool /
#    conftest.make_mock_pool, but conn.fetch needs per-query routing here since
#    check_fills issues two different SELECTs in one call) ──────────────────────

class _FakeRow(dict):
    """asyncpg.Record stand-in — supports both bracket access and .get()."""
    def __getitem__(self, k):
        return super().__getitem__(k)


def _stub_pool_with_fetch(fetch_fn):
    """Build a stub pool whose acquire() yields a conn with fetch()/execute()
    routed through `fetch_fn(query, *args)`."""
    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=fetch_fn)
    conn.execute = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = conn
    ctx.__aexit__.return_value = None
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx)
    return pool, conn


# ── 1. _enum_value both-forms table ─────────────────────────────────────────


def test_enum_value_both_forms_table():
    assert _enum_value("OrderStatus.NEW") == "new"
    assert _enum_value("new") == "new"
    assert _enum_value(None) is None
    assert _enum_value("OrderSide.BUY") == "buy"
    assert _enum_value("buy") == "buy"
    assert _enum_value("OrderType.STOP_LIMIT") == "stop_limit"


def test_enum_value_real_alpaca_enum_if_available():
    """Real alpaca-py enum instances, only if a real (non-stubbed) install is
    present in this env — conftest.py stubs the package (any attribute access
    materializes a MagicMock) for dev machines that don't have alpaca-py
    installed, so skip cleanly when only the stub is in play."""
    from unittest.mock import Mock
    try:
        from alpaca.trading.enums import OrderStatus
        if isinstance(OrderStatus.NEW, Mock):
            pytest.skip("alpaca-py not installed; conftest stub in use")
    except Exception:
        pytest.skip("alpaca-py not installed")
    assert _enum_value(OrderStatus.NEW) == "new"


# ── 2. Wire-contract pin: _order_to_dict yields plain lowercase values ──────


class _FakeEnumRepr:
    """Mimics alpaca-py's Python 3.11+ Enum str() repr: 'ClassName.MEMBER'."""
    def __init__(self, s: str):
        self._s = s

    def __str__(self) -> str:
        return self._s


class _StubOrder:
    """Enum-shaped stub order — attrs whose str() gives the qualified repr,
    exactly like a real alpaca-py Order on Python 3.12."""
    def __init__(self, status="OrderStatus.NEW", side="OrderSide.BUY",
                 type_="OrderType.STOP_LIMIT", legs=None):
        self.id = "order-abc123"
        self.client_order_id = "coid-1"
        self.symbol = "AAPL"
        self.side = _FakeEnumRepr(side)
        self.type = _FakeEnumRepr(type_)
        self.qty = 100
        self.filled_qty = 0
        self.filled_avg_price = None
        self.stop_price = 10.5
        self.limit_price = None
        self.status = _FakeEnumRepr(status)
        self.created_at = None
        self.filled_at = None
        self.legs = legs or []


def test_order_to_dict_wire_contract_plain_lowercase():
    d = _order_to_dict(_StubOrder())
    assert d["status"] == "new"
    assert d["side"] == "buy"
    assert d["type"] == "stop_limit"


def test_order_to_dict_legs_recurse_through_same_normalization():
    """Legs are built via a recursive _order_to_dict call — verify the
    recursion actually re-applies _enum_value, not a raw str() copy."""
    leg = _StubOrder(status="OrderStatus.NEW", side="OrderSide.SELL", type_="OrderType.STOP")
    parent = _StubOrder(status="OrderStatus.NEW", side="OrderSide.BUY",
                         type_="OrderType.STOP_LIMIT", legs=[leg])
    d = _order_to_dict(parent)
    assert len(d["legs"]) == 1
    assert d["legs"][0]["side"] == "sell"
    assert d["legs"][0]["type"] == "stop"
    assert d["legs"][0]["status"] == "new"


# ── 3. check_fills dedup pin (§5's one real risk) ───────────────────────────


@pytest.mark.asyncio
async def test_check_fills_fires_on_plain_filled_and_ws_processed_trade_not_reprocessed():
    """The revival-safety pin: check_fills' SELECT filters `WHERE status =
    'order_placed'` — a trade already transitioned to 'filled' by the WS
    handler is excluded from the fetch entirely (real Postgres semantics),
    so polling never reprocesses it / never double-Telegrams. We EXERCISE
    that exclusion (not just assert the filter-clause string is present):
    the stub's candidate pool holds both an order_placed row AND a
    WS-already-filled row, and `_fetch` applies the real WHERE-clause
    filter itself, so the already-filled row is never handed back — and
    we assert alpaca.get_order/Telegram were never invoked for it."""
    pool_rows = [
        _FakeRow({
            "id": 501, "ticker": "ZZZ", "entry_order_id": "eo-1",
            "entry_shares": 100, "orb_low": 9.0, "stop_price": 9.5,
            "entry_attempt": 1, "account_mode": "paper",
            "_db_status": "order_placed",  # test-fixture only; not a real column
        }),
        _FakeRow({
            "id": 599, "ticker": "WSD", "entry_order_id": "eo-9",
            "entry_shares": 50, "orb_low": 4.0, "stop_price": 4.5,
            "entry_attempt": 1, "account_mode": "paper",
            "_db_status": "filled",  # already transitioned by the WS handler
        }),
    ]
    captured_queries = []

    async def _fetch(query, *args):
        captured_queries.append(query)
        if "entry_order_id IS NOT NULL" in query:
            # Mirror the real WHERE status = 'order_placed' filter: the
            # already-WS-filled row is excluded here, exactly like Postgres
            # would exclude it — this IS the dedup mechanism under test.
            return [r for r in pool_rows if r["_db_status"] == "order_placed"]
        # _check_day1_reentry's SELECT — no candidates in this test.
        return []

    pool, conn = _stub_pool_with_fetch(_fetch)

    order_dict = {
        "status": "filled",  # plain, post-boundary-fix contract
        "filled_avg_price": 12.5,
        "filled_qty": 100,
        "legs": [],
    }

    with patch("agents.market_intelligence.broker.order_manager.get_pool",
               new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.broker.order_manager.alpaca.get_order",
               new=AsyncMock(return_value=order_dict)) as get_order_mock, \
         patch("agents.market_intelligence.broker.order_manager.send_telegram_message",
               new=AsyncMock(return_value=True)) as tg:
        results = await check_fills()

    # (a) the select-filter semantics that provide the dedup are present
    assert any("status = 'order_placed'" in q for q in captured_queries)

    # (b) the exclusion is actually EXERCISED: the WS-processed trade (eo-9)
    # was never even queried — get_order was called exactly once, and only
    # for the still-order_placed trade.
    get_order_mock.assert_called_once_with("eo-1", account_mode="paper")

    # (c) the previously-dead 'filled' comparison now fires correctly for the
    # one trade the filtered SELECT actually returned, and only once
    filled_results = [r for r in results if r["action"] == "filled"]
    assert len(filled_results) == 1
    assert filled_results[0]["ticker"] == "ZZZ"
    tg.assert_called_once()  # no dup Telegram for the already-processed WSD trade
    # DB transition happened exactly once (entry UPDATE + orders-audit UPDATE)
    assert conn.execute.call_count == 2


# ── 4. :396 recognizes one-L "canceled" via _CANCEL_LIKE_ORDER_STATUSES ─────


def test_cancel_like_constant_has_both_spellings():
    assert "canceled" in _CANCEL_LIKE_ORDER_STATUSES  # Alpaca's canonical one-L spelling
    assert "cancelled" in _CANCEL_LIKE_ORDER_STATUSES
    assert "expired" in _CANCEL_LIKE_ORDER_STATUSES
    assert "rejected" in _CANCEL_LIKE_ORDER_STATUSES


@pytest.mark.asyncio
async def test_check_fills_recognizes_one_l_canceled_end_to_end():
    """Before the fix, the inline tuple ('cancelled', 'expired', 'rejected')
    was missing Alpaca's canonical one-L 'canceled' — a canceled order would
    fall through neither branch. Pin the :396 site end-to-end."""
    pending_row = _FakeRow({
        "id": 502, "ticker": "YYY", "entry_order_id": "eo-2",
        "entry_shares": 50, "orb_low": 5.0, "stop_price": 5.5,
        "entry_attempt": 1, "account_mode": "paper",
    })

    async def _fetch(query, *args):
        if "entry_order_id IS NOT NULL" in query:
            return [pending_row]
        return []

    pool, conn = _stub_pool_with_fetch(_fetch)
    order_dict = {"status": "canceled", "legs": []}  # one-L, plain (post-boundary-fix)

    with patch("agents.market_intelligence.broker.order_manager.get_pool",
               new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.broker.order_manager.alpaca.get_order",
               new=AsyncMock(return_value=order_dict)):
        results = await check_fills()

    cancel_results = [r for r in results if r["action"] == "canceled"]
    assert len(cancel_results) == 1
    assert cancel_results[0]["ticker"] == "YYY"
    # _update_trade_status wrote status='cancelled' + skip_reason='canceled'
    conn.execute.assert_called_once_with(
        "UPDATE mi_live_trades SET status = $2, skip_reason = $3 WHERE id = $1",
        502, "cancelled", "canceled",
    )


# ── 5. audit_invariants coverage check: plain + qualified sell forms ───────


@pytest.mark.asyncio
async def test_naked_coverage_recognizes_plain_sell_stop():
    from agents.market_intelligence.audit_invariants import classify_naked_positions
    from agents.market_intelligence.broker import alpaca_client

    body = {"offending_rows": [
        {"ticker": "AAA", "alert_date": "2026-07-06", "stop_order_id": None,
         "status": "filled", "filled_at": None},
    ]}
    plain_orders = [{"id": "s1", "symbol": "AAA", "side": "sell", "type": "stop",
                      "stop_price": 10.0}]
    with patch.object(alpaca_client, "get_open_orders", new=AsyncMock(return_value=plain_orders)):
        result = await classify_naked_positions(body)

    assert len(result["db_drift"]) == 1
    assert result["db_drift"][0]["ticker"] == "AAA"
    assert result["real_naked"] == []


@pytest.mark.asyncio
async def test_naked_coverage_endswith_hardening_tolerates_qualified_sell():
    """Defense-in-depth: even if a qualified enum repr ever leaked through
    (shouldn't, post-boundary-fix, but this site now has its own hardening
    too), .endswith('sell') still recognizes it — unlike the old == 'sell'."""
    from agents.market_intelligence.audit_invariants import classify_naked_positions
    from agents.market_intelligence.broker import alpaca_client

    body = {"offending_rows": [
        {"ticker": "BBB", "alert_date": "2026-07-06", "stop_order_id": None,
         "status": "filled", "filled_at": None},
    ]}
    qualified_orders = [{"id": "s2", "symbol": "BBB", "side": "OrderSide.SELL",
                          "type": "stop", "stop_price": 10.0}]
    with patch.object(alpaca_client, "get_open_orders", new=AsyncMock(return_value=qualified_orders)):
        result = await classify_naked_positions(body)

    assert len(result["db_drift"]) == 1
    assert result["db_drift"][0]["ticker"] == "BBB"
    assert result["real_naked"] == []


# ── 6. _check_day1_reentry attempt-count guard pin (§5's other real risk) ──


@pytest.mark.asyncio
async def test_day1_reentry_attempt_count_guard_holds():
    """Revival-safety pin: the SQL SELECT filters `entry_attempt < $2`
    (MAX_ENTRY_ATTEMPTS). A trade already at the attempt ceiling must never
    be returned/re-attempted, even though the (now-live) status comparison
    downstream would otherwise fire on a plain 'filled' stop-order status."""
    eligible = _FakeRow({
        "id": 601, "ticker": "AAA", "stop_order_id": "so-1",
        "stop_price": 10.0, "account_mode": "paper",
    })
    candidates = {
        601: {"entry_attempt": 1},  # < MAX(2) → eligible
        602: {"entry_attempt": 2},  # == MAX(2), not < → NOT eligible
    }
    at_ceiling = _FakeRow({
        "id": 602, "ticker": "BBB", "stop_order_id": "so-2",
        "stop_price": 10.0, "account_mode": "paper",
    })

    async def _fetch(query, *args):
        assert "entry_attempt < $2" in query
        max_attempts = args[-1]
        rows = {601: eligible, 602: at_ceiling}
        return [rows[tid] for tid, meta in candidates.items()
                if meta["entry_attempt"] < max_attempts]

    pool, _conn = _stub_pool_with_fetch(_fetch)
    stop_order_dict = {"status": "filled", "filled_avg_price": 9.9}  # plain, boundary-fixed

    with patch("agents.market_intelligence.broker.order_manager.get_pool",
               new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.broker.order_manager.alpaca.get_order",
               new=AsyncMock(return_value=stop_order_dict)), \
         patch("agents.market_intelligence.broker.order_manager.attempt_day1_reentry",
               new=AsyncMock(return_value={"ticker": "AAA", "action": "reentry"})) as reentry_mock:
        results = await _check_day1_reentry()

    assert MAX_ENTRY_ATTEMPTS == 2
    # Only the eligible (attempt < MAX) trade was ever fetched or re-entered —
    # the at-ceiling trade never reached the alpaca.get_order / re-entry call.
    reentry_mock.assert_called_once()
    assert reentry_mock.call_args.args[0] == 601
    assert len(results) == 1
