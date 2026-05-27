"""Regression tests for reconcile_order_states (#123, 2026-05-26).

Periodic DB↔Alpaca reconcile catches silent stops and stuck PENDING_NEW.
Pins:
  - canonicalizes Python SDK enum repr ('OrderStatus.PENDING_NEW') to lowercase
  - skips already-terminal DB rows
  - updates DB to Alpaca status when divergent + writes audit row
  - leaves DB alone when statuses match
  - tolerates alpaca.get_order returning None (treats as transient + audits)
"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub the `alpaca` SDK so module imports don't fail in dev env without the
# real broker SDK installed (CI/prod both have it; this only affects local).
# Use a `__getattr__`-backed module so any `from alpaca.x import Y` resolves
# to a MagicMock without enumerating each symbol.
class _MockModule(types.ModuleType):
    def __getattr__(self, name):
        v = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, v)
        return v

for mod_name in [
    "alpaca", "alpaca.trading", "alpaca.trading.client", "alpaca.trading.requests",
    "alpaca.trading.enums", "alpaca.trading.models", "alpaca.trading.stream",
    "alpaca.data", "alpaca.data.historical", "alpaca.data.requests",
    "alpaca.data.timeframe", "alpaca.data.enums", "alpaca.common",
    "alpaca.common.exceptions",
]:
    sys.modules[mod_name] = _MockModule(mod_name)

# Stub the validate_orb_entry filter (pulls a heavy import chain via numpy/pandas
# that may not be installed locally).
sys.modules.setdefault(
    "agents.market_intelligence.backtester",
    types.ModuleType("agents.market_intelligence.backtester"),
)
_filters_stub = types.ModuleType("agents.market_intelligence.backtester.filters")
_filters_stub.validate_orb_entry = MagicMock(name="validate_orb_entry")
sys.modules.setdefault("agents.market_intelligence.backtester.filters", _filters_stub)

from agents.market_intelligence.broker.order_manager import (
    _canonical_order_status,
    _TERMINAL_ORDER_STATUSES,
    reconcile_order_states,
)


# ── canonical status helper ─────────────────────────────────────────────

def test_canonical_handles_python_enum_repr():
    assert _canonical_order_status("OrderStatus.PENDING_NEW") == "pending_new"
    assert _canonical_order_status("OrderStatus.FILLED") == "filled"


def test_canonical_handles_bare_lowercase():
    assert _canonical_order_status("new") == "new"
    assert _canonical_order_status("filled") == "filled"


def test_canonical_handles_uppercase():
    assert _canonical_order_status("PENDING_NEW") == "pending_new"


def test_canonical_returns_none_for_empty():
    assert _canonical_order_status(None) is None
    assert _canonical_order_status("") is None


def test_terminal_set_includes_canonical_values():
    assert "filled" in _TERMINAL_ORDER_STATUSES
    assert "canceled" in _TERMINAL_ORDER_STATUSES
    assert "expired" in _TERMINAL_ORDER_STATUSES


# ── reconcile_order_states integration ──────────────────────────────────


class _FakeRow(dict):
    """asyncpg.Record stand-in — supports both bracket access and .get()."""
    def __getitem__(self, k):
        return super().__getitem__(k)


def _stub_pool(rows):
    """Build a stub pool whose acquire() yields a conn with fetch() returning rows."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    conn.execute = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = conn
    ctx.__aexit__.return_value = None
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx)
    return pool, conn


@pytest.mark.asyncio
async def test_status_match_no_update():
    """DB says 'new', Alpaca says 'new' → no UPDATE, no audit."""
    rows = [_FakeRow({
        "alpaca_order_id": "o1",
        "ticker": "ABC",
        "status": "new",
        "trade_id": 1,
        "purpose": "entry",
    })]
    pool, conn = _stub_pool(rows)
    with patch("agents.market_intelligence.broker.order_manager.get_pool",
               new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.broker.order_manager.alpaca.get_order",
               new=AsyncMock(return_value={"status": "new"})), \
         patch("agents.market_intelligence.broker.order_manager.log_audit_event",
               new=AsyncMock()) as audit:
        result = await reconcile_order_states("paper")
    assert result["examined"] == 1
    assert result["updated"] == 0
    assert result["errors"] == 0
    conn.execute.assert_not_called()
    audit.assert_not_called()


@pytest.mark.asyncio
async def test_status_divergence_updates_db_and_audits():
    """DB says 'new', Alpaca says 'filled' → UPDATE + audit."""
    rows = [_FakeRow({
        "alpaca_order_id": "o2",
        "ticker": "XYZ",
        "status": "new",
        "trade_id": 5,
        "purpose": "entry",
    })]
    pool, conn = _stub_pool(rows)
    with patch("agents.market_intelligence.broker.order_manager.get_pool",
               new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.broker.order_manager.alpaca.get_order",
               new=AsyncMock(return_value={
                   "status": "OrderStatus.FILLED",
                   "filled_qty": 100,
                   "filled_avg_price": 15.42,
               })), \
         patch("agents.market_intelligence.broker.order_manager.log_audit_event",
               new=AsyncMock()) as audit:
        result = await reconcile_order_states("paper")
    assert result["examined"] == 1
    assert result["updated"] == 1
    assert result["errors"] == 0
    conn.execute.assert_called_once()
    # UPDATE arg[0] should be canonical 'filled', not raw enum repr
    update_call = conn.execute.call_args
    assert update_call.args[1] == "filled"
    audit.assert_called_once()
    assert audit.call_args.args[0] == "order_status_reconciled"


@pytest.mark.asyncio
async def test_already_terminal_row_skipped():
    """DB row already 'filled' → don't even call Alpaca."""
    rows = [_FakeRow({
        "alpaca_order_id": "o3",
        "ticker": "FOO",
        "status": "filled",
        "trade_id": 7,
        "purpose": "entry",
    })]
    pool, _conn = _stub_pool(rows)
    get_order_mock = AsyncMock()
    with patch("agents.market_intelligence.broker.order_manager.get_pool",
               new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.broker.order_manager.alpaca.get_order",
               new=get_order_mock):
        result = await reconcile_order_states("paper")
    assert result["examined"] == 0  # terminal rows don't count toward examined
    get_order_mock.assert_not_called()


@pytest.mark.asyncio
async def test_alpaca_returns_none_audits_and_counts_error():
    """alpaca.get_order returns None (swallowed error) → audit + errors += 1."""
    rows = [_FakeRow({
        "alpaca_order_id": "o4",
        "ticker": "BAR",
        "status": "new",
        "trade_id": 9,
        "purpose": "stop_loss",
    })]
    pool, conn = _stub_pool(rows)
    with patch("agents.market_intelligence.broker.order_manager.get_pool",
               new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.broker.order_manager.alpaca.get_order",
               new=AsyncMock(return_value=None)), \
         patch("agents.market_intelligence.broker.order_manager.log_audit_event",
               new=AsyncMock()) as audit:
        result = await reconcile_order_states("paper")
    assert result["errors"] == 1
    assert result["updated"] == 0
    conn.execute.assert_not_called()
    audit.assert_called_once()
    assert audit.call_args.args[0] == "order_status_reconcile_failed"


@pytest.mark.asyncio
async def test_alpaca_raises_logs_audit():
    """alpaca.get_order raises → audit row + count error, don't crash loop."""
    rows = [
        _FakeRow({"alpaca_order_id": "o5", "ticker": "A", "status": "new",
                  "trade_id": 1, "purpose": "entry"}),
        _FakeRow({"alpaca_order_id": "o6", "ticker": "B", "status": "new",
                  "trade_id": 2, "purpose": "entry"}),
    ]
    pool, _conn = _stub_pool(rows)
    # First raises, second succeeds
    get_order = AsyncMock(side_effect=[RuntimeError("503"), {"status": "filled"}])
    with patch("agents.market_intelligence.broker.order_manager.get_pool",
               new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.broker.order_manager.alpaca.get_order",
               new=get_order), \
         patch("agents.market_intelligence.broker.order_manager.log_audit_event",
               new=AsyncMock()):
        result = await reconcile_order_states("paper")
    # Both examined, one errored, one updated
    assert result["examined"] == 2
    assert result["errors"] == 1
    assert result["updated"] == 1


@pytest.mark.asyncio
async def test_empty_rowset_returns_zeros():
    pool, _ = _stub_pool([])
    with patch("agents.market_intelligence.broker.order_manager.get_pool",
               new=AsyncMock(return_value=pool)):
        result = await reconcile_order_states("paper")
    assert result == {"examined": 0, "updated": 0, "errors": 0}
