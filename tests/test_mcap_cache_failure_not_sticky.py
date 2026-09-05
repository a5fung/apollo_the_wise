"""A failed market-cap read must not exempt the ticker until restart.

Before 2026-09-05 `_check_market_cap` cached `None` on an FMP exception. `None` means
"let it through", and the cache hit on every later tick skipped the re-read — so ONE
transient error removed that ticker from the $500M floor for the life of the process,
logged at debug only. The fail-open on the FAILING tick is intended and preserved here;
the stickiness was not.

⚠ `tests/conftest.py` replaces `agents.market_intelligence.backtester.filters` with a
stub for the whole suite (ep_detector imports names from it). This test therefore loads
the REAL file off disk under a private module name — importing it the normal way would
silently test the stub and pass no matter what the source says.
"""
import importlib.util
import pathlib
import sys
import types

import pytest

_SRC = pathlib.Path(__file__).resolve().parents[1] / \
    "agents/market_intelligence/backtester/filters.py"


def _load_real_filters(monkeypatch):
    """Load filters.py itself, stubbing only its two external imports."""
    collector = types.ModuleType("agents.market_intelligence.collector")
    collector.get_fmp_profile = None  # replaced per-test below
    db = types.ModuleType("agents.market_intelligence.db")

    async def _no_pool():
        raise AssertionError("_check_market_cap must not touch the DB")

    db.get_pool = _no_pool
    monkeypatch.setitem(sys.modules, "agents.market_intelligence.collector", collector)
    monkeypatch.setitem(sys.modules, "agents.market_intelligence.db", db)

    spec = importlib.util.spec_from_file_location("_real_filters_under_test", _SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.asyncio
async def test_a_failed_read_is_retried_on_the_next_tick(monkeypatch):
    filters = _load_real_filters(monkeypatch)
    calls = []

    async def flaky(ticker):
        calls.append(ticker)
        if len(calls) == 1:
            raise RuntimeError("FMP timeout")
        return {"marketCap": 134_000_000}  # CHPT-sized: under the $500M floor

    monkeypatch.setattr(filters, "get_fmp_profile", flaky)

    # Tick 1 — the read fails. Fail-OPEN is deliberate: an admission floor must not
    # block the whole scan on a data outage. No skip reason.
    assert await filters._check_market_cap("CHPT") is None

    # Tick 2 — MUST re-read rather than serve a cached failure...
    reason = await filters._check_market_cap("CHPT")
    assert len(calls) == 2, \
        "the failed read was cached — this ticker is exempt from the floor until restart"
    # ...and the floor now actually applies.
    assert reason is not None and "mcap_too_small" in reason


@pytest.mark.asyncio
async def test_a_successful_read_is_still_cached(monkeypatch):
    """The fix must not turn the hot scan path into an FMP call per ticker per tick."""
    filters = _load_real_filters(monkeypatch)
    calls = []

    async def ok(ticker):
        calls.append(ticker)
        return {"marketCap": 9_000_000_000}

    monkeypatch.setattr(filters, "get_fmp_profile", ok)
    assert await filters._check_market_cap("MSFT") is None
    assert await filters._check_market_cap("MSFT") is None
    assert len(calls) == 1, "a good read must still be cached"
