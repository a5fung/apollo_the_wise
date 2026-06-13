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


def test_routes_cover_cross_fns_exactly():
    from agents.market_intelligence import execution_routes as er
    assert set(er._EXEC_HANDLERS) == set(ec._CROSS_FNS)


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
