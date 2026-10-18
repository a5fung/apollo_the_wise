"""#314 / ADR 0020 card B3 - the READ-ONLY `get_asset(symbol, account_mode)` seam.

`alpaca_client.get_asset` is the broker wrapper (the field exists in alpaca-py's Asset model; our client had no
accessor). Intelligence-side code reaches it ONLY through `execution_client.get_asset` (the #256 W1 facade). Pinned:
the wrapper's contract (a plain dict, 404 -> None, any other failure RAISES), both transports, the route that
apollo-execution serves, and that a wire failure is never collapsed into a borrow answer.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_intelligence import constants
from agents.market_intelligence import execution_client as ec
from agents.market_intelligence.broker import alpaca_client as ac


class _NotFound(Exception):
    status_code = 404


class _Server(Exception):
    status_code = 503


def _client_returning(asset=None, exc=None):
    c = MagicMock()
    if exc is not None:
        c.get_asset = MagicMock(side_effect=exc)
    else:
        c.get_asset = MagicMock(return_value=asset)
    return c


class AssetStatus(str, Enum):             # alpaca-py's enums are (str, Enum): str() is 'AssetStatus.ACTIVE'
    ACTIVE = "active"


class AssetExchange(str, Enum):
    NASDAQ = "NASDAQ"


class AssetClass(str, Enum):
    US_EQUITY = "us_equity"


def _real_asset(**over):
    """A stand-in with alpaca-py's Asset attribute names and enum types (the SDK itself is stubbed in the unit
    suite - tests/conftest.py - so the real field names are pinned separately, in a clean interpreter, below)."""
    base = dict(id=uuid.uuid4(), asset_class=AssetClass.US_EQUITY, exchange=AssetExchange.NASDAQ, symbol="ZZZ",
                name="Zed Corp", status=AssetStatus.ACTIVE, tradable=True, marginable=True, shortable=True,
                easy_to_borrow=True, fractionable=True)
    base.update(over)
    return SimpleNamespace(**base)


def test_the_wrapper_reads_fields_the_real_alpaca_asset_model_has():
    """The unit suite stubs alpaca-py, so run a CLEAN interpreter against the installed SDK. Skipped where the
    SDK is not installed (the production image has it)."""
    code = ("from alpaca.trading.models import Asset; import json; "
            "print(json.dumps(sorted(Asset.model_fields)))")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parent.parent)
    if r.returncode != 0:
        pytest.skip(f"alpaca-py not importable in a clean interpreter: {r.stderr.strip()[-120:]}")
    fields = set(json.loads(r.stdout))
    assert {"symbol", "status", "tradable", "shortable", "easy_to_borrow", "marginable", "fractionable",
            "exchange", "asset_class"} <= fields


# ── the broker wrapper ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestBrokerWrapper:
    async def test_a_real_alpaca_asset_becomes_a_plain_json_dict(self, monkeypatch):
        import json
        c = _client_returning(_real_asset())
        monkeypatch.setattr(ac, "get_trading_client", lambda mode=None: c)
        out = await ac.get_asset("ZZZ", account_mode="paper")
        assert out == {"symbol": "ZZZ", "status": "active", "tradable": True, "shortable": True,
                       "easy_to_borrow": True, "marginable": True, "fractionable": True,
                       "exchange": "nasdaq", "asset_class": "us_equity"}
        json.dumps(out)                                   # it crosses the execution wire
        c.get_asset.assert_called_once_with("ZZZ")

    async def test_hard_to_borrow_is_reported_as_it_is(self, monkeypatch):
        monkeypatch.setattr(ac, "get_trading_client",
                            lambda mode=None: _client_returning(_real_asset(easy_to_borrow=False)))
        out = await ac.get_asset("ZZZ", account_mode="paper")
        assert out["shortable"] is True and out["easy_to_borrow"] is False

    async def test_the_borrow_flags_stay_tri_state(self, monkeypatch):
        bare = MagicMock(spec=["symbol", "status"])       # an asset object that simply lacks the borrow fields
        bare.symbol, bare.status = "ZZZ", "active"
        monkeypatch.setattr(ac, "get_trading_client", lambda mode=None: _client_returning(bare))
        out = await ac.get_asset("ZZZ")
        assert out["shortable"] is None and out["easy_to_borrow"] is None   # "did not say", never coerced to False

    async def test_the_per_mode_client_is_the_one_asked_for(self, monkeypatch):
        seen = []
        monkeypatch.setattr(ac, "get_trading_client",
                            lambda mode=None: seen.append(mode) or _client_returning(_real_asset()))
        await ac.get_asset("ZZZ", account_mode="paper")
        assert seen == ["paper"]

    @pytest.mark.parametrize("exc", [_NotFound("asset not found"), RuntimeError("HTTP 404: asset not found"),
                                     Exception("could not find asset \"ZZZ\"")])
    async def test_a_404_is_the_brokers_answer_so_none_not_a_raise(self, monkeypatch, exc):
        monkeypatch.setattr(ac, "get_trading_client", lambda mode=None: _client_returning(exc=exc))
        assert await ac.get_asset("ZZZ") is None

    @pytest.mark.parametrize("exc", [_Server("503 service unavailable"), TimeoutError(), RuntimeError("boom"),
                                     RuntimeError("Required Alpaca credential env var 'ALPACA_PAPER_API_KEY' is not set")])
    async def test_any_other_failure_raises_never_a_default(self, monkeypatch, exc):
        monkeypatch.setattr(ac, "get_trading_client", lambda mode=None: _client_returning(exc=exc))
        with pytest.raises(type(exc)):
            await ac.get_asset("ZZZ")

    async def test_a_missing_credential_raises_from_client_construction(self, monkeypatch):
        def no_creds(mode=None):
            raise RuntimeError("Required Alpaca credential env var 'ALPACA_PAPER_API_KEY' is not set")
        monkeypatch.setattr(ac, "get_trading_client", no_creds)
        with pytest.raises(RuntimeError, match="credential"):
            await ac.get_asset("ZZZ", account_mode="paper")

    async def test_the_blocking_sdk_call_is_offloaded_through_sdk(self, monkeypatch):
        c = _client_returning(_real_asset())
        monkeypatch.setattr(ac, "get_trading_client", lambda mode=None: c)
        spied = []
        real_sdk = ac._sdk

        async def spy(fn, *a, **k):
            spied.append(fn)
            return await real_sdk(fn, *a, **k)
        monkeypatch.setattr(ac, "_sdk", spy)
        await ac.get_asset("ZZZ")
        assert spied == [c.get_asset]

    async def test_it_never_pages_on_its_own(self, monkeypatch):
        alert = AsyncMock()
        monkeypatch.setattr("agents.market_intelligence.llm_health.maybe_alert_api_failure", alert)
        monkeypatch.setattr(ac, "get_trading_client", lambda mode=None: _client_returning(exc=_Server("503")))
        with pytest.raises(_Server):
            await ac.get_asset("ZZZ")
        alert.assert_not_awaited()


# ── the facade, both transports ──────────────────────────────────────────────────────────────────

def test_get_asset_is_a_fast_cross_boundary_read():
    assert "get_asset" in ec._CROSS_FNS
    assert "get_asset" not in ec._SLOW_COMMAND_FNS          # a GET gets the tight read budget, not the command one


@pytest.mark.asyncio
async def test_inprocess_calls_the_broker_wrapper_directly(monkeypatch):
    monkeypatch.setattr(constants, "EXECUTION_MODE", "inprocess")
    broker = AsyncMock(return_value={"symbol": "ZZZ", "shortable": True})
    http = AsyncMock()
    monkeypatch.setattr(ac, "get_asset", broker)
    monkeypatch.setattr(ec, "_http_call", http)

    out = await ec.get_asset("ZZZ", account_mode="paper")

    assert out == {"symbol": "ZZZ", "shortable": True}
    broker.assert_awaited_once_with("ZZZ", account_mode="paper")
    http.assert_not_awaited()


@pytest.mark.asyncio
async def test_inprocess_a_broker_error_propagates_unchanged(monkeypatch):
    monkeypatch.setattr(constants, "EXECUTION_MODE", "inprocess")
    monkeypatch.setattr(ac, "get_asset", AsyncMock(side_effect=_Server("503")))
    with pytest.raises(_Server):
        await ec.get_asset("ZZZ", account_mode="paper")


@pytest.mark.asyncio
async def test_http_mode_posts_the_symbol_and_mode_over_the_wire(monkeypatch):
    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    inproc = AsyncMock(return_value="local")
    http = AsyncMock(return_value={"symbol": "ZZZ", "easy_to_borrow": False})
    monkeypatch.setattr(ec, "_get_asset_inprocess", inproc)
    monkeypatch.setattr(ec, "_http_call", http)

    out = await ec.get_asset("ZZZ", account_mode="paper")

    assert out == {"symbol": "ZZZ", "easy_to_borrow": False}
    http.assert_awaited_once_with("get_asset", ("ZZZ",), {"account_mode": "paper"})
    inproc.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_a_404_crosses_the_wire_as_none_not_as_unreachable(monkeypatch):
    from tests.conftest import fake_httpx_client
    import httpx

    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8007")
    monkeypatch.setattr("shared.secrets.get_secrets", lambda: type("S", (), {"internal_api_secret": "x"})())
    monkeypatch.setattr(ec, "_client", None)
    monkeypatch.setattr(ec, "_client_loop", None)
    monkeypatch.setattr(httpx, "AsyncClient", fake_httpx_client(status_code=200, json_body={"result": None}))
    assert await ec.get_asset("ZZZ", account_mode="paper") is None


@pytest.mark.asyncio
async def test_http_an_unreachable_execution_service_raises_never_a_borrow_answer(monkeypatch):
    import httpx

    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8007")
    monkeypatch.setattr("shared.secrets.get_secrets", lambda: type("S", (), {"internal_api_secret": "x"})())
    monkeypatch.setattr(ec, "_client", None)
    monkeypatch.setattr(ec, "_client_loop", None)

    class _Boom:
        def __init__(self, *a, **k):
            pass

        async def post(self, *a, **k):
            raise httpx.ConnectError("connection refused")
    monkeypatch.setattr(httpx, "AsyncClient", _Boom)

    with pytest.raises(ec.ExecutionUnreachable):
        await ec.get_asset("ZZZ", account_mode="paper")


@pytest.mark.asyncio
async def test_http_a_broker_error_inside_execution_is_call_failed_with_the_original_reason(monkeypatch):
    import httpx
    from tests.conftest import fake_httpx_client

    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8007")
    monkeypatch.setattr("shared.secrets.get_secrets", lambda: type("S", (), {"internal_api_secret": "x"})())
    monkeypatch.setattr(ec, "_client", None)
    monkeypatch.setattr(ec, "_client_loop", None)
    monkeypatch.setattr(httpx, "AsyncClient", fake_httpx_client(
        status_code=500,
        json_body={"detail": {"execution_error": True, "error_type": "APIError", "error_message": "503 upstream"}},
        raise_on_status=True))
    with pytest.raises(ec.ExecutionCallFailed) as ei:
        await ec.get_asset("ZZZ", account_mode="paper")
    assert "APIError" in str(ei.value) and "503 upstream" in str(ei.value)


@pytest.mark.asyncio
async def test_http_uses_the_tight_read_timeout(monkeypatch):
    import httpx

    monkeypatch.setattr(constants, "EXECUTION_MODE", "http")
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8007")
    monkeypatch.setattr("shared.secrets.get_secrets", lambda: type("S", (), {"internal_api_secret": "x"})())
    monkeypatch.setattr(ec, "_client", None)
    monkeypatch.setattr(ec, "_client_loop", None)
    captured = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def post(self, *a, timeout=None, **k):
            captured["timeout"] = timeout

            class _R:
                status_code = 200

                def raise_for_status(self_):
                    pass

                def json(self_):
                    return {"result": {"symbol": "ZZZ"}}
            return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    await ec.get_asset("ZZZ", account_mode="paper")
    assert captured["timeout"].read == ec._HTTP_READ_TIMEOUT_SECONDS


# ── the route apollo-execution serves ────────────────────────────────────────────────────────────

def test_the_route_is_derived_and_serves_the_inprocess_body(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agents.base import verify_internal_secret
    from agents.market_intelligence import execution_routes as er

    assert er._EXEC_HANDLERS["get_asset"] is ec._get_asset_inprocess       # never the dispatcher (no http loop)
    assert er._EXEC_HANDLERS["get_asset"] is not ec.get_asset

    broker = AsyncMock(return_value={"symbol": "ZZZ", "shortable": True, "easy_to_borrow": True})
    monkeypatch.setattr(ac, "get_asset", broker)
    app = FastAPI()
    er.register_execution_routes(app)
    app.dependency_overrides[verify_internal_secret] = lambda: "ok"
    r = TestClient(app).post("/exec/get_asset", json={"args": ["ZZZ"], "kwargs": {"account_mode": "paper"}})
    assert r.status_code == 200
    assert r.json() == {"result": {"symbol": "ZZZ", "shortable": True, "easy_to_borrow": True}}
    broker.assert_awaited_once_with("ZZZ", account_mode="paper")


def test_a_broker_failure_in_the_route_is_a_typed_500_the_client_can_name(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agents.base import verify_internal_secret
    from agents.market_intelligence import execution_routes as er

    monkeypatch.setattr(ac, "get_asset", AsyncMock(side_effect=_Server("503 service unavailable")))
    app = FastAPI()
    er.register_execution_routes(app)
    app.dependency_overrides[verify_internal_secret] = lambda: "ok"
    r = TestClient(app, raise_server_exceptions=False).post(
        "/exec/get_asset", json={"args": ["ZZZ"], "kwargs": {"account_mode": "paper"}})
    assert r.status_code == 500
    d = r.json()["detail"]
    assert d["execution_error"] is True and d["error_type"] == "_Server" and "503" in d["error_message"]
