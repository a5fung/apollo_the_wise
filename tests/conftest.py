"""pytest shared fixtures + module stubbing.

Auto-loaded by pytest before any test module imports. Stubs the heavy
broker SDKs (alpaca-py) and the optional backtester.filters module so
tests can import market_intelligence modules in dev environments that
don't have those installed.

If a real installation IS present the stubs are no-ops (we use
`sys.modules.setdefault` for the top-level alpaca and a get-or-create
pattern for `filters` attributes so we never clobber a real impl).

Origin: 5 test files were repeating this ~30 LOC block at the top. Per
/simplify 2026-05-27 advisor review, the rule-of-four+ violation
warranted centralization here.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock


class _MockModule(types.ModuleType):
    """Module-like stub that materializes any attribute on first access as
    a MagicMock. Lets `from alpaca.x import Y` resolve to a Mock without
    enumerating every imported symbol in advance."""

    def __getattr__(self, name):
        v = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, v)
        return v


# Stub alpaca-py + anthropic SDKs (heavy installs, not required for unit
# tests of business logic). Use setdefault so a real install isn't
# clobbered.
for _mod_name in [
    "alpaca", "alpaca.trading", "alpaca.trading.client",
    "alpaca.trading.requests", "alpaca.trading.enums",
    "alpaca.trading.models", "alpaca.trading.stream",
    "alpaca.data", "alpaca.data.historical", "alpaca.data.requests",
    "alpaca.data.timeframe", "alpaca.data.enums",
    "alpaca.common", "alpaca.common.exceptions",
    "anthropic",
]:
    sys.modules.setdefault(_mod_name, _MockModule(_mod_name))

# backtester.filters stub: ep_detector imports specific names from it.
# Use get-or-create so multiple test runs in the same process don't
# overwrite real attributes (this conftest only runs once per pytest
# session, but defensive).
sys.modules.setdefault(
    "agents.market_intelligence.backtester",
    types.ModuleType("agents.market_intelligence.backtester"),
)
_filters_stub = sys.modules.get(
    "agents.market_intelligence.backtester.filters",
    types.ModuleType("agents.market_intelligence.backtester.filters"),
)
for _attr in ("validate_orb_entry", "check_filters"):
    if not hasattr(_filters_stub, _attr):
        setattr(_filters_stub, _attr, MagicMock(name=_attr))
sys.modules["agents.market_intelligence.backtester.filters"] = _filters_stub

_tracker_stub = sys.modules.get(
    "agents.market_intelligence.backtester.tracker",
    types.ModuleType("agents.market_intelligence.backtester.tracker"),
)
for _attr in ("run_paper_trade_tracker", "format_tracker_telegram"):
    if not hasattr(_tracker_stub, _attr):
        setattr(_tracker_stub, _attr, MagicMock(name=_attr))
sys.modules["agents.market_intelligence.backtester.tracker"] = _tracker_stub


# ─── Shared asyncpg pool mock builder ──────────────────────────────────────
# Origin: 3 test files rolling their own near-identical version
# (test_ep_scan_watchdog, test_downgrade_digest, test_sync_positions_safety_guard).
# Per /simplify 2026-05-28 advisor review, rule-of-three crossed.
def make_mock_pool():
    """Build a MagicMock asyncpg pool. Returns `(pool, conn)`.

    Caller configures `conn.fetch`, `conn.fetchval`, `conn.execute` etc. with
    their own AsyncMocks (return_value or side_effect). This helper owns only
    the acquire-context-manager wiring — the actual rule-of-three duplication.
    """
    conn = MagicMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool, conn

