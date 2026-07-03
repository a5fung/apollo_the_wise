"""#256 W2 commit 5a — execution_client HTTP transport + apollo-execution routes.

The transport flip (inprocess→http) must be invisible to call sites, and a wire
failure must FAIL LOUD (ExecutionUnreachable) — NEVER collapse into a broker-empty
default, which a caller would read as "flat" (no_silent_trading_failures +
ground_truth_verification). These pin: dispatch routing, the fail-loud contract,
the local-only classification (advisor #2), the boot coherence check (advisor #4),
and route↔client parity.
"""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import constants
from agents.market_intelligence import execution_client as ec


@pytest.mark.asyncio
async def test_inprocess_is_default(monkeypatch):
    monkeypatch.setattr(constants, "EXECUTION_MODE", "inprocess")
    inproc = AsyncMock(return_value={"equity": 1.0})
    http = AsyncMock(return_value={"equity": 999.0})
    monkeypatch.setattr(ec, "_get_account_inprocess", inproc)
    monkeypatch.setattr(ec, "_http_call", http)

    out = await ec.get_account(account_mode="paper")

    assert out == {"equity": 1.0}
    inproc.assert_awaited_once_with(account_mode="paper")
    http.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_mode_dispatches_over_wire(monkeypatch):
    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    inproc = AsyncMock(return_value="local")
    http = AsyncMock(return_value="wire")
    monkeypatch.setattr(ec, "_get_all_positions_inprocess", inproc)
    monkeypatch.setattr(ec, "_http_call", http)

    out = await ec.get_all_positions(account_mode="paper")

    assert out == "wire"
    http.assert_awaited_once_with("get_all_positions", (), {"account_mode": "paper"})
    inproc.assert_not_awaited()


@pytest.mark.asyncio
async def test_wire_failure_raises_not_empty(monkeypatch):
    # THE point: an unreachable execution service must RAISE, never return [] /
    # {} (which a caller would read as "flat" → silent false-flat).
    import httpx

    import shared.secrets as secrets

    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8007")
    monkeypatch.setattr(
        secrets, "get_secrets",
        lambda: type("S", (), {"internal_api_secret": "x"})())

    class _Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", _Boom)

    with pytest.raises(ec.ExecutionUnreachable):
        await ec.get_all_positions(account_mode="paper")


@pytest.mark.asyncio
@pytest.mark.parametrize("name,expect_read", [
    ("trigger_orb_entry", ec._HTTP_COMMAND_TIMEOUT_SECONDS),   # heavy: runs orb monitor
    ("execute_partial_exit", ec._HTTP_COMMAND_TIMEOUT_SECONDS),  # heavy: broker mutation
    ("get_all_positions", ec._HTTP_READ_TIMEOUT_SECONDS),       # fast read
    ("get_account", ec._HTTP_READ_TIMEOUT_SECONDS),            # fast read
])
async def test_http_timeout_is_split_by_call_weight(monkeypatch, name, expect_read):
    # The trade-critical handoffs (trigger_orb_entry et al.) run heavy synchronous
    # work on execution; a flat 15s read would false-raise ExecutionUnreachable on the
    # order path. They get the long read budget; fast reads keep the tight one. Connect
    # stays short either way so "execution down" fails fast.
    import httpx

    import shared.secrets as secrets

    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8007")
    monkeypatch.setattr(
        secrets, "get_secrets",
        lambda: type("S", (), {"internal_api_secret": "x"})())

    captured = {}

    class _Client:
        def __init__(self, *a, timeout=None, **k):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            class _R:
                status_code = 200
                def raise_for_status(self_):
                    pass

                def json(self_):
                    return {"result": None}
            return _R()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    await ec._http_call(name, (), {})

    t = captured["timeout"]
    assert t.read == expect_read
    assert t.connect == ec._HTTP_CONNECT_TIMEOUT_SECONDS
    # the slow set never silently grows past the trade-state mutators
    assert ec._SLOW_COMMAND_FNS <= ec._CROSS_FNS


def test_get_data_feed_name_is_pure_config_local(monkeypatch):
    monkeypatch.setenv("ALPACA_DATA_FEED", "sip")
    assert ec.get_data_feed_name() == "sip"
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    assert ec.get_data_feed_name() == "iex"
    monkeypatch.setenv("ALPACA_DATA_FEED", "garbage")
    assert ec.get_data_feed_name() == "iex"
    monkeypatch.delenv("ALPACA_DATA_FEED", raising=False)
    assert ec.get_data_feed_name() == "iex"
    # pure config — must never be routed over the wire
    assert "get_data_feed_name" not in ec._CROSS_FNS


def test_alpaca_get_data_feed_delegates_to_single_resolver(monkeypatch):
    # #279: alpaca_client.get_data_feed no longer re-parses ALPACA_DATA_FEED —
    # it derives the enum from the ONE resolver (ec.get_data_feed_name). Pin
    # the delegation (resolver output drives the enum) and one end-to-end env
    # case so the two can't silently diverge again.
    from agents.market_intelligence.broker import alpaca_client as ac

    monkeypatch.setattr(ec, "get_data_feed_name", lambda: "sip")
    assert ac.get_data_feed() is ac.DataFeed.SIP
    monkeypatch.setattr(ec, "get_data_feed_name", lambda: "iex")
    assert ac.get_data_feed() is ac.DataFeed.IEX

    monkeypatch.undo()
    monkeypatch.setenv("ALPACA_DATA_FEED", "garbage")  # resolver coerces → iex
    assert ac.get_data_feed() is ac.DataFeed.IEX


def test_wire_default_encodes_dates():
    assert ec._wire_default(date(2026, 6, 13)) == "2026-06-13"
    with pytest.raises(TypeError):
        ec._wire_default(object())


def test_http_intelligence_without_url_fails_loud(monkeypatch):
    monkeypatch.setattr(constants, "SERVICE_ROLE", "intelligence")
    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "")
    with pytest.raises(RuntimeError, match="EXECUTION_SERVICE_URL"):
        constants.assert_service_role_coherent()


def test_http_intelligence_with_url_is_coherent(monkeypatch):
    monkeypatch.setattr(constants, "SERVICE_ROLE", "intelligence")
    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8007")
    constants.assert_service_role_coherent()  # must not raise


@pytest.mark.asyncio
async def test_reset_bar_stream_routes_to_execution_inprocess(monkeypatch):
    # Seam item 1: the 7 AM bar-stream daily reset must reach the execution
    # bar stream. inprocess routes byte-identically to bar_stream.reset_daily_state.
    monkeypatch.setattr(constants, "EXECUTION_MODE", "inprocess")
    import agents.market_intelligence.broker.bar_stream as bar_stream
    from unittest.mock import MagicMock
    fake = MagicMock(return_value=None)
    monkeypatch.setattr(bar_stream, "reset_daily_state", fake)

    await ec.reset_bar_stream_daily_state()

    fake.assert_called_once_with()
    assert "reset_bar_stream_daily_state" in ec._CROSS_FNS


def test_routes_derive_from_cross_fns_by_convention():
    # #279: _EXEC_HANDLERS is DERIVED from _CROSS_FNS via the `_<name>_inprocess`
    # naming convention (set equality now holds trivially by construction), so
    # pin the CONVENTION instead: every wire name maps to exactly the
    # execution_client `_<name>_inprocess` body — never the public dispatcher
    # (or an inbound http request could loop back out as another http call).
    from agents.market_intelligence import execution_routes as er
    assert set(er._EXEC_HANDLERS) == set(ec._CROSS_FNS)
    for name, fn in er._EXEC_HANDLERS.items():
        assert fn is getattr(ec, f"_{name}_inprocess"), name
        assert fn is not getattr(ec, name, None), name


def test_exec_route_invokes_handler_and_unknown_404(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agents.base import verify_internal_secret
    from agents.market_intelligence import execution_routes as er

    app = FastAPI()
    er.register_execution_routes(app)
    app.dependency_overrides[verify_internal_secret] = lambda: "ok"

    fake = AsyncMock(return_value={"equity": 5.0})
    monkeypatch.setitem(er._EXEC_HANDLERS, "get_account", fake)

    client = TestClient(app)
    r = client.post("/exec/get_account",
                    json={"args": [], "kwargs": {"account_mode": "paper"}})
    assert r.status_code == 200
    assert r.json() == {"result": {"equity": 5.0}}
    fake.assert_awaited_once_with(account_mode="paper")

    r404 = client.post("/exec/nonexistent", json={"args": [], "kwargs": {}})
    assert r404.status_code == 404


# ── F18: "execution answered with an error" ≠ "unreachable" ──────────────────


@pytest.mark.asyncio
async def test_f18_execution_side_error_raises_call_failed(monkeypatch):
    """A typed 500 (the routes-side execution_error marker) must surface as
    ExecutionCallFailed carrying the ORIGINAL type+message — pre-F18 it
    collapsed into ExecutionUnreachable, discarding the reason (an Alpaca
    rejection mid-ORB read as a network blip)."""
    import httpx

    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8007")
    monkeypatch.setattr(
        "shared.secrets.get_secrets",
        lambda: type("S", (), {"internal_api_secret": "x"})(),
    )

    class _Resp:
        status_code = 500

        def json(self):
            return {"detail": {"execution_error": True,
                               "error_type": "ValueError",
                               "error_message": "alpaca rejected: insufficient qty"}}

        def raise_for_status(self):
            raise httpx.HTTPStatusError("500", request=None, response=None)

    class _Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    with pytest.raises(ec.ExecutionCallFailed) as ei:
        await ec._http_call("trigger_orb_entry", (), {})
    assert "ValueError" in str(ei.value)
    assert "insufficient qty" in str(ei.value)


@pytest.mark.asyncio
async def test_f18_bare_500_still_unreachable(monkeypatch):
    """A 500 WITHOUT the marker (proxy error, crash-before-handler) stays
    ExecutionUnreachable — the distinction must not over-classify."""
    import httpx

    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8007")
    monkeypatch.setattr(
        "shared.secrets.get_secrets",
        lambda: type("S", (), {"internal_api_secret": "x"})(),
    )

    class _Resp:
        status_code = 500

        def json(self):
            return {"detail": "internal server error"}

        def raise_for_status(self):
            raise httpx.HTTPStatusError("500", request=None, response=None)

    class _Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    with pytest.raises(ec.ExecutionUnreachable):
        await ec._http_call("get_account", (), {})
