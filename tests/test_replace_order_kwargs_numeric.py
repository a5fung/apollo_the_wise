"""Regression test for replace_order str-vs-numeric kwargs bug (IBM 2026-05-28).

Pre-fix: `replace_order` wrapped qty/stop_price/limit_price as `str(x)` before
building the alpaca-py ReplaceOrderRequest. Pydantic validators inside
ReplaceOrderRequest expect numbers; the `str` value raises
`TypeError: '<=' not supported between instances of 'str' and 'int'`
during validation — BEFORE the HTTP call to Alpaca. Effect:
  - replace_order_by_id never reaches Alpaca
  - Original order stays alive broker-side
  - Caller catches TypeError, clears stop_order_id, fires "naked position"
    Telegram — but broker is still protected (DB-drift, not naked)

IBM trade #167 partial-take at 16:45 ET 2026-05-28 hit this exact path.

Post-fix: pass numerics as numbers. Test pins the kwargs shape by
inspecting what `ReplaceOrderRequest` receives.
"""
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_replace_order_passes_numeric_kwargs():
    """Replace_order must pass qty/stop_price/limit_price as numbers,
    not str. The bug fired in alpaca-py Pydantic validation when these
    were stringified."""
    from agents.market_intelligence.broker import alpaca_client

    captured: dict = {}

    class _FakeReplaceRequest:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_client = MagicMock()
    fake_order = MagicMock()
    fake_order.id = "new-id"
    fake_order.symbol = "IBM"
    fake_order.side = "sell"
    fake_order.type = "stop"
    fake_order.qty = 18
    fake_order.filled_qty = 0
    fake_order.filled_avg_price = None
    fake_order.stop_price = 230.94
    fake_order.limit_price = None
    fake_order.status = "accepted"
    fake_order.created_at = None
    fake_order.filled_at = None
    fake_order.client_order_id = "test-coid"
    fake_order.legs = []
    fake_client.replace_order_by_id.return_value = fake_order

    with patch.object(alpaca_client, "ReplaceOrderRequest", new=_FakeReplaceRequest), \
         patch.object(alpaca_client, "get_trading_client", return_value=fake_client):
        await alpaca_client.replace_order(
            "old-order-id",
            qty=18,
            stop_price=230.94,
            account_mode="paper",
            client_order_id="apollo_paper_magna53_IBM_123",
        )

    # The crux: numerics must remain numerics. Bug shipped them as str(x).
    assert captured.get("qty") == 18
    assert not isinstance(captured.get("qty"), str), (
        f"qty must be numeric (alpaca-py Pydantic validates `<= 0`); "
        f"got {type(captured.get('qty')).__name__}({captured.get('qty')!r})"
    )
    assert captured.get("stop_price") == 230.94
    assert not isinstance(captured.get("stop_price"), str), (
        f"stop_price must be numeric; "
        f"got {type(captured.get('stop_price')).__name__}"
    )
    assert captured.get("client_order_id") == "apollo_paper_magna53_IBM_123"


@pytest.mark.asyncio
async def test_replace_order_with_limit_price_also_numeric():
    """Limit price has the same numeric-vs-str invariant as stop_price."""
    from agents.market_intelligence.broker import alpaca_client

    captured: dict = {}

    class _FakeReplaceRequest:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_client = MagicMock()
    fake_order = MagicMock()
    fake_order.id = "new-id"
    fake_order.symbol = "X"
    fake_order.side = "buy"
    fake_order.type = "limit"
    fake_order.qty = 5
    fake_order.filled_qty = 0
    fake_order.filled_avg_price = None
    fake_order.stop_price = None
    fake_order.limit_price = 99.5
    fake_order.status = "accepted"
    fake_order.created_at = None
    fake_order.filled_at = None
    fake_order.client_order_id = "test"
    fake_order.legs = []
    fake_client.replace_order_by_id.return_value = fake_order

    with patch.object(alpaca_client, "ReplaceOrderRequest", new=_FakeReplaceRequest), \
         patch.object(alpaca_client, "get_trading_client", return_value=fake_client):
        await alpaca_client.replace_order(
            "id", qty=5, limit_price=99.5, account_mode="paper",
        )

    assert captured.get("limit_price") == 99.5
    assert not isinstance(captured.get("limit_price"), str)


# ── #687 (d), 2026-10-01: the same class of bug on `close_position(qty=...)` ────────────────
#
# A partial close handed alpaca-py a plain dict as `close_options`. alpaca-py 0.43.2's
# `TradingClient.close_position` calls `close_options.to_request_fields()` on it, so EVERY
# `qty=` close raised AttributeError before any HTTP call. No caller passed a qty until the
# #687 OCO-case sale, so it had never run. These tests drive the REAL SDK method on a real
# (offline) `TradingClient` and capture what reaches its HTTP layer — the fake is the network,
# not the SDK, so a request object the SDK cannot use fails here exactly as it would live.

class _HttpReached(Exception):
    """Raised by the fake HTTP layer once it has recorded the request."""


_ALPACA_CLIENT = "agents.market_intelligence.broker.alpaca_client"


@pytest.fixture
def real_alpaca_client():
    """`alpaca_client` imported against the REAL alpaca-py (conftest stubs the SDK with
    MagicMocks, under which any request shape "works"). Same swap-and-restore shape as
    `test_broker_reject_reason_540.real_models`."""
    import importlib

    def _keys():
        return [k for k in sys.modules
                if k == "alpaca" or k.startswith("alpaca.") or k == _ALPACA_CLIENT]

    saved = {k: sys.modules[k] for k in _keys()}
    for k in saved:
        del sys.modules[k]
    try:
        try:
            mod = importlib.import_module(_ALPACA_CLIENT)
        except Exception:
            pytest.skip("real alpaca-py not installed")
        if not hasattr(mod.ClosePositionRequest, "model_fields"):
            pytest.skip("real alpaca-py not installed (stub resolved instead)")
        yield mod
    finally:
        for k in _keys():
            del sys.modules[k]
        sys.modules.update(saved)


def _offline_client(captured: list):
    from alpaca.trading.client import TradingClient

    client = TradingClient("test-key", "test-secret", paper=True)

    def _fake_delete(path, data=None):
        captured.append((path, data))
        raise _HttpReached()

    client.delete = _fake_delete
    return client


@pytest.mark.asyncio
async def test_close_position_with_qty_reaches_the_broker_with_the_qty_as_a_string(
        real_alpaca_client):
    alpaca_client = real_alpaca_client

    captured: list = []
    client = _offline_client(captured)
    with patch.object(alpaca_client, "get_trading_client", return_value=client):
        with pytest.raises(_HttpReached):
            await alpaca_client.close_position("KOD", qty=2.0, account_mode="paper")

    assert captured == [("/positions/KOD", {"qty": "2"})], (
        "the partial close never reached the HTTP layer with qty='2' — the request object "
        f"alpaca-py builds from it is wrong (captured {captured!r})")


@pytest.mark.asyncio
async def test_close_position_without_qty_still_closes_the_whole_position(real_alpaca_client):
    """The unchanged path: no qty → no close options at all (Alpaca liquidates everything)."""
    alpaca_client = real_alpaca_client

    captured: list = []
    client = _offline_client(captured)
    with patch.object(alpaca_client, "get_trading_client", return_value=client):
        with pytest.raises(_HttpReached):
            await alpaca_client.close_position("KOD", account_mode="paper")

    assert captured == [("/positions/KOD", {})]


def test_close_qty_keeps_fractional_shares():
    from agents.market_intelligence.broker.alpaca_client import _close_qty_str

    assert _close_qty_str(3) == "3"
    assert _close_qty_str(3.0) == "3"
    assert _close_qty_str(1.5) == "1.5"
