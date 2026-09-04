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
for _attr in ("validate_orb_entry", "check_filters", "compute_atr_14"):
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


# ─── Shared fake httpx.AsyncClient builder ─────────────────────────────────
# Origin: test_execution_transport.py's two F18 pairs + test_telegram_market_task_
# fallback.py's fake each hand-rolled a near-identical `async with httpx.AsyncClient
# () as client: ... client.post(...)` stand-in. Per /simplify 2026-07-03 review,
# collapsed to one builder (mirrors make_mock_pool's role for the DB pool side).
def fake_httpx_client(status_code=200, json_body=None, raise_on_status=False):
    """Build a fake httpx.AsyncClient CLASS whose `.post()` returns a canned response.

    `raise_on_status=True` makes `.raise_for_status()` raise `httpx.HTTPStatusError` —
    `json_body` stays readable off the response afterward either way (the F18 marker
    a typed execution-side error carries lives in a 500 response's BODY, read via
    `.json()` AFTER `.raise_for_status()` raises).

    Returns the CLASS (not an instance) — pass it straight to
    `monkeypatch.setattr(httpx, "AsyncClient", ...)`; a fresh instance is built per
    `async with httpx.AsyncClient(...) as client:` call site, matching real usage.
    The class records the most recent `.post(...)` call's args/kwargs on the class
    attribute `last_post` (a class attr since instances are transient) so a caller can
    assert on what was sent, e.g. `FakeClient.last_post["kwargs"]["json"]["task"]`.
    """
    import httpx as _httpx

    class _FakeResp:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return json_body if json_body is not None else {}

        def raise_for_status(self):
            if raise_on_status:
                raise _httpx.HTTPStatusError(str(status_code), request=None, response=None)

    class _FakeAsyncClient:
        last_post: dict = {}

        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            _FakeAsyncClient.last_post = {"args": a, "kwargs": k}
            return _FakeResp()

    return _FakeAsyncClient


# ─── #577 must-not-miss debt summary — always printed, no -v needed ────────────────────────────
# P1 (docs/roadmap/ep_profitability_program.md § THE PRINCIPLES, operator 2026-08-19): "a real EP
# must never be missed." tests/fixtures/must_not_miss_eps.py pins today's KNOWN exclusions as a
# recorded debt (BASELINE_DEBT) so tests/test_577_must_not_miss_eps.py can be green without hiding
# them — but a debt that only shows up under -v is functionally hidden. pytest_terminal_summary
# runs unconditionally at the end of every session regardless of verbosity flags, so this is the
# one place a "print" is guaranteed visible in normal `pytest` output. Deliberately defensive:
# a broken import here must never take down an unrelated test run's summary.
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    try:
        from tests.fixtures import must_not_miss_eps as _mnm
    except Exception:
        return
    debt_members = [
        m for m in _mnm.MUST_NOT_MISS
        if not m.excluded and (m.ticker, m.alert_date) in _mnm.BASELINE_DEBT
    ]
    if not debt_members:
        return
    total = sum(1 for m in _mnm.MUST_NOT_MISS if not m.excluded)
    gates = sorted({g for m in debt_members for g in _mnm.BASELINE_DEBT[(m.ticker, m.alert_date)]})
    terminalreporter.write_line("")
    terminalreporter.write_line(
        f"[#577 must-not-miss] {len(debt_members)} of {total} labelled real EPs are currently "
        f"EXCLUDED by the live selection stack (all {', '.join(gates)}) — recorded debt against "
        f"P1 (docs/roadmap/ep_profitability_program.md § THE PRINCIPLES), recorded "
        f"{_mnm.BASELINE_RECORDED_DATE}. See tests/fixtures/must_not_miss_eps.py::BASELINE_DEBT.",
        yellow=True,
    )
    # #622, 2026-09-04 — an ABSTAINED member is invisible in the count above (it is excluded from
    # `total` by design), and an abstention nobody sees is the same as a quiet drop. The whole
    # justification for abstaining rather than asserting is that it stays VISIBLE, so print it.
    abstained = [m for m in _mnm.MUST_NOT_MISS if m.excluded and m.label_source == "operator"]
    for m in abstained:
        terminalreporter.write_line(
            f"[#577 must-not-miss] ⚠ {m.ticker} {m.alert_date} is OPERATOR-NAMED, is excluded by "
            f"the live stack, and is NOT being asserted — awaiting his ruling on the gate that "
            f"drops it. This is a declared abstention, not an accepted state: "
            f"{(m.exclude_reason or '').split(':')[0]}. See must_not_miss_eps.py.",
            yellow=True,
        )

