"""Research market data — POST /data/bars (execution) + research_data.fetch_bars (market container).

Covers: the route's JSON shape with the Alpaca data client mocked; every cap -> a named 400;
the read-only guarantee derived by AST (and shown non-vacuous on planted violations); the
client-side paging; the wiring that keeps the route off the /exec/* dispatcher and inside the
execution deploy scope.
"""
from __future__ import annotations

import ast
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.base import verify_internal_secret
from agents.market_intelligence import execution_client as ec
from agents.market_intelligence import execution_routes as er
from agents.market_intelligence import research_data as rd
from agents.market_intelligence.broker import research_bars as rb

ROOT = Path(__file__).resolve().parent.parent
MI = ROOT / "agents" / "market_intelligence"
UTC = timezone.utc


def _bar(ts, o=1.0, h=2.0, l=0.5, c=1.5, v=100):
    return SimpleNamespace(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)


class _FakeDataClient:
    """Stands in for alpaca's StockHistoricalDataClient: it HAS only get_stock_bars, so any
    other call in the code path would raise AttributeError."""

    def __init__(self, data=None, raises=None):
        self.data, self.raises, self.requests = data or {}, raises, []

    def get_stock_bars(self, request):
        self.requests.append(request)
        if self.raises:
            raise self.raises
        return SimpleNamespace(data=self.data)


@pytest.fixture(autouse=True)
def _sdk_request_recorder(monkeypatch):
    """conftest stubs the alpaca SDK, so pin what we SEND by name: the request becomes a plain
    namespace of its kwargs, and the enum tables map to their own names."""
    monkeypatch.setattr(rb, "StockBarsRequest", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(rb, "_TIMEFRAMES", {k: f"tf:{k}" for k in rb._TIMEFRAMES})
    monkeypatch.setattr(rb, "_FEEDS", {k: f"feed:{k}" for k in rb._FEEDS})
    monkeypatch.setattr(rb, "_ADJUSTMENTS", {k: f"adj:{k}" for k in rb._ADJUSTMENTS})
    monkeypatch.setattr(rb, "_page", None)


@pytest.fixture
def client():
    app = FastAPI()
    er.register_execution_routes(app)
    app.dependency_overrides[verify_internal_secret] = lambda: "ok"
    return TestClient(app)


def _body(**over):
    body = {"symbols": ["SPY"], "timeframe": "1Min",
            "start": "2026-11-13T14:30:00+00:00", "end": "2026-11-13T15:30:00+00:00"}
    body.update(over)
    return body


# ── (a) the route: data client mocked -> JSON shape ──────────────────────────

def test_route_returns_compact_bars(client, monkeypatch):
    t0 = datetime(2026, 11, 13, 14, 30, tzinfo=UTC)
    fake = _FakeDataClient({
        "TLT": [_bar(t0, v=250.5)],
        "SPY": [_bar(t0 + timedelta(minutes=1), 10, 11, 9, 10.5, 300), _bar(t0, 9, 10, 8, 9.5, 200.0),
                _bar(t0 + timedelta(hours=1))],          # exactly `end` -> outside the half-open window
    })
    monkeypatch.setattr(rb, "_get_data_client", lambda: fake)
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")

    r = client.post("/data/bars", json=_body(symbols=["tlt", "SPY", "spy"],
                                              start="2026-11-13T09:30:00-05:00",
                                              end="2026-11-13T10:30:00-05:00"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["bars"] == [
        {"symbol": "SPY", "ts": "2026-11-13T14:30:00+00:00", "o": 9.0, "h": 10.0, "l": 8.0, "c": 9.5, "v": 200},
        {"symbol": "SPY", "ts": "2026-11-13T14:31:00+00:00", "o": 10.0, "h": 11.0, "l": 9.0, "c": 10.5, "v": 300},
        {"symbol": "TLT", "ts": "2026-11-13T14:30:00+00:00", "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 250.5},
    ]
    assert out["count"] == 3 and out["symbols"] == ["TLT", "SPY"]
    assert out["feed"] == "iex" and out["timeframe"] == "1Min" and out["adjustment"] == "raw"
    assert out["start"] == "2026-11-13T14:30:00+00:00" and out["end"] == "2026-11-13T15:30:00+00:00"

    (req,) = fake.requests                              # ONE upstream call, with the row cap pushed down
    assert req.symbol_or_symbols == ["TLT", "SPY"]
    assert req.limit == ec.RESEARCH_BARS_MAX_ROWS + 1
    assert (req.feed, req.timeframe, req.adjustment) == ("feed:iex", "tf:1Min", "adj:raw")
    assert (req.start, req.end) == (t0, t0 + timedelta(hours=1))


def test_route_feed_and_timeframe_are_passed_through(client, monkeypatch):
    fake = _FakeDataClient()
    monkeypatch.setattr(rb, "_get_data_client", lambda: fake)
    r = client.post("/data/bars", json=_body(timeframe="15Min", feed="SIP", adjustment="split"))
    assert r.status_code == 200 and r.json()["bars"] == [] and r.json()["feed"] == "sip"
    (req,) = fake.requests
    assert (req.feed, req.timeframe, req.adjustment) == ("feed:sip", "tf:15Min", "adj:split")


def test_route_requires_the_internal_secret(monkeypatch):
    from shared.secrets import get_secrets
    monkeypatch.setenv("INTERNAL_API_SECRET", "right-secret")
    get_secrets.cache_clear()
    app = FastAPI()
    er.register_execution_routes(app)
    fake = _FakeDataClient()
    monkeypatch.setattr(rb, "_get_data_client", lambda: fake)
    http = TestClient(app)
    assert http.post("/data/bars", json=_body(), headers={"X-Apollo-Secret": "wrong-secret"}).status_code == 401
    assert http.post("/data/bars", json=_body()).status_code in (401, 403)
    assert fake.requests == []                            # nothing fetched without the secret
    assert http.post("/data/bars", json=_body(), headers={"X-Apollo-Secret": "right-secret"}).status_code == 200
    get_secrets.cache_clear()


def test_route_runs_on_its_own_thread_not_the_shared_pools(client, monkeypatch):
    seen = {}

    class _C(_FakeDataClient):
        def get_stock_bars(self, request):
            seen["thread"] = threading.current_thread().name
            return super().get_stock_bars(request)

    monkeypatch.setattr(rb, "_get_data_client", lambda: _C())
    assert client.post("/data/bars", json=_body()).status_code == 200
    assert seen["thread"].startswith(rb.RESEARCH_BARS_THREAD_PREFIX)


# ── (b) caps and violations -> a named 400; upstream / busy keep their own status ──

@pytest.mark.parametrize("over, code", [
    ({"symbols": [f"S{i}" for i in range(51)]}, "too_many_symbols"),
    ({"symbols": []}, "bad_symbols"),
    ({"symbols": "SPY"}, "bad_symbols"),
    ({"symbols": ["SPY; DROP"]}, "bad_symbols"),
    ({"timeframe": "2Min"}, "bad_timeframe"),
    ({"start": "2026-11-13T09:30:00"}, "naive_time"),
    ({"end": "not-a-time"}, "bad_time"),
    ({"start": "2026-11-13T15:30:00+00:00"}, "bad_range"),
    ({"start": "2026-11-05T14:30:00+00:00"}, "range_too_long"),               # 8 days at 1Min
    ({"timeframe": "5Min", "start": "2026-10-01T14:30:00+00:00"}, "range_too_long"),
    ({"timeframe": "1Day", "start": "2016-01-01T00:00:00+00:00"}, "range_too_long"),
    ({"feed": "otc"}, "bad_feed"),
    ({"adjustment": "magic"}, "bad_adjustment"),
    ({"account_mode": "live"}, "unknown_field"),
])
def test_violations_are_a_named_400_and_never_reach_alpaca(client, monkeypatch, over, code):
    monkeypatch.setattr(rb, "_get_data_client", lambda: pytest.fail("Alpaca reached on a bad request"))
    r = client.post("/data/bars", json=_body(**over))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == code and r.json()["detail"]["message"]


def test_longest_allowed_range_passes(client, monkeypatch):
    monkeypatch.setattr(rb, "_get_data_client", lambda: _FakeDataClient())
    assert client.post("/data/bars", json=_body(start="2026-11-06T15:30:00+00:00")).status_code == 200   # 7 days
    assert client.post("/data/bars", json=_body(symbols=[f"S{i}" for i in range(50)])).status_code == 200


def test_row_cap_is_a_400(client, monkeypatch):
    monkeypatch.setattr(rb, "RESEARCH_BARS_MAX_ROWS", 3)
    t0 = datetime(2026, 11, 13, 14, 30, tzinfo=UTC)
    fake = _FakeDataClient({"SPY": [_bar(t0 + timedelta(minutes=i)) for i in range(4)]})
    monkeypatch.setattr(rb, "_get_data_client", lambda: fake)
    r = client.post("/data/bars", json=_body())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "row_cap"
    assert fake.requests[0].limit == 4                   # cap + 1 asked upstream, never the whole range

    fake.data = {"SPY": fake.data["SPY"][:3]}            # exactly the cap is fine
    assert client.post("/data/bars", json=_body()).json()["count"] == 3


def test_row_cap_is_judged_before_the_half_open_filter(client, monkeypatch):
    """Alpaca's `end` is inclusive. A fetch cut off at cap+1 whose last bar sits exactly ON `end`
    must still be `row_cap` — filtered first, it would drop to the cap and return 200 with the
    later symbols silently missing."""
    monkeypatch.setattr(rb, "RESEARCH_BARS_MAX_ROWS", 3)
    t0 = datetime(2026, 11, 13, 14, 30, tzinfo=UTC)
    fake = _FakeDataClient({"SPY": [_bar(t0), _bar(t0 + timedelta(minutes=1)), _bar(t0 + timedelta(minutes=2)),
                                    _bar(t0 + timedelta(hours=1))]})        # 4 fetched; the 4th is exactly `end`
    monkeypatch.setattr(rb, "_get_data_client", lambda: fake)
    r = client.post("/data/bars", json=_body(symbols=["SPY", "TLT"]))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "row_cap"


def test_the_answer_is_encoded_on_the_research_thread(client, monkeypatch):
    """A 50,000-row answer must not be JSON-encoded on the execution event loop: the body leaves
    the research thread as bytes and the route hands them back untouched."""
    import json as _json
    seen = {}
    real = _json.dumps

    def spy(obj, **kw):
        if isinstance(obj, dict) and "bars" in obj:
            seen["thread"] = threading.current_thread().name
        return real(obj, **kw)

    monkeypatch.setattr(rb.json, "dumps", spy)
    monkeypatch.setattr(rb, "_get_data_client", lambda: _FakeDataClient())
    r = client.post("/data/bars", json=_body())
    assert r.status_code == 200 and r.headers["content-type"] == "application/json"
    assert seen["thread"].startswith(rb.RESEARCH_BARS_THREAD_PREFIX)


def test_alpaca_error_is_a_502_with_the_message(client, monkeypatch):
    monkeypatch.setattr(rb, "_get_data_client",
                        lambda: _FakeDataClient(raises=RuntimeError("subscription does not permit SIP")))
    r = client.post("/data/bars", json=_body(feed="sip"))
    assert r.status_code == 502 and r.json()["detail"]["code"] == "upstream"
    assert "subscription does not permit SIP" in r.json()["detail"]["message"]


def test_busy_while_a_fetch_is_still_on_the_thread(client, monkeypatch):
    monkeypatch.setattr(rb, "_page", SimpleNamespace(done=lambda: False))
    monkeypatch.setattr(rb, "_get_data_client", lambda: pytest.fail("queued behind a running fetch"))
    r = client.post("/data/bars", json=_body())
    assert r.status_code == 429 and r.json()["detail"]["code"] == "busy"


# ── (c) READ-ONLY, derived by AST ────────────────────────────────────────────

_ALPACA_CLIENT = "agents.market_intelligence.broker.alpaca_client"
_DATA_ONLY_FROM_ALPACA_CLIENT = {"_get_data_client"}
_ALLOWED_ALPACA_SDK = ("alpaca.data.",)
# research_bars may import these project modules and nothing else from the project.
_RESEARCH_BARS_PROJECT_IMPORTS = {_ALPACA_CLIENT, "agents.market_intelligence.execution_client"}
# research_data runs in the market container: no broker module at all.
_RESEARCH_DATA_PROJECT_IMPORTS = {"agents.market_intelligence.execution_client",
                                  "agents.market_intelligence.constants", "shared.secrets"}
# Names that are REST verbs / dict methods as well as SDK-base methods — not trading calls.
_GENERIC = {"get", "post", "put", "patch", "delete"}


def _sdk_trading_client_methods() -> set[str]:
    """Public methods of alpaca's TradingClient, read from the installed package's SOURCE
    (conftest stubs the import, so `dir()` would see a mock). Empty when alpaca-py is not on disk
    — the module's deny-by-default call set below is the guarantee that never depends on it."""
    import importlib.machinery
    spec = importlib.machinery.PathFinder.find_spec("alpaca")
    if spec is None or not spec.submodule_search_locations:
        return set()
    path = Path(list(spec.submodule_search_locations)[0]) / "trading" / "client.py"
    if not path.exists():
        return set()
    out: set[str] = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.ClassDef) and node.name == "TradingClient":
            out |= {n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")}
    return out


def _trading_surface() -> set[str]:
    """Every name that can reach an account, an order or a position — DERIVED, not hand-listed:
    every top-level function of our alpaca_client module except the data-client accessor, plus
    every public TradingClient method of the installed SDK."""
    tree = ast.parse((MI / "broker" / "alpaca_client.py").read_text())
    ours = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return ((ours | _sdk_trading_client_methods() | {"TradingClient", "TradingStream"})
            - _DATA_ONLY_FROM_ALPACA_CLIENT - _GENERIC)


def _called_names(tree) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            out.add(fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "<expr>"))
    return out


def _read_only_violations(source: str, project_imports: set[str]) -> list[str]:
    """Why `source` is not provably market-data-only. Empty = clean."""
    tree = ast.parse(source)
    surface = _trading_surface()
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [(a.name, None) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [(node.module or "", [a.name for a in node.names])]
        else:
            mods = []
        for mod, names in mods:
            if mod == "alpaca" or mod.startswith("alpaca."):
                if not (mod + ".").startswith(_ALLOWED_ALPACA_SDK):
                    out.append(f"alpaca SDK import outside alpaca.data: {mod}")
            elif mod.split(".")[0] in ("agents", "shared", "core", "channels"):
                if mod not in project_imports:
                    out.append(f"project import not on the allowlist: {mod}")
                elif mod == _ALPACA_CLIENT:
                    extra = set(names or ["<whole module>"]) - _DATA_ONLY_FROM_ALPACA_CLIENT
                    if extra:
                        out.append(f"alpaca_client names beyond the data client: {sorted(extra)}")
        if isinstance(node, (ast.Attribute, ast.Name)):
            name = node.attr if isinstance(node, ast.Attribute) else node.id
            if name in surface:
                out.append(f"reference to trading-surface name: {name}")
    for called in _called_names(tree) & {"__import__", "import_module", "getattr", "eval", "exec"}:
        out.append(f"dynamic lookup: {called}")
    return out


def test_trading_surface_is_derived_and_covers_the_obvious():
    # source-pin-ok: the trading surface is derived from module source by AST; conftest stubs the SDK, so there is no object to introspect
    surface = _trading_surface()
    assert {"place_bracket_order", "cancel_order", "get_position", "get_open_orders", "get_account",
            "get_all_positions", "close_position", "place_market_sell", "replace_order",
            "get_trading_client", "_get_trading_client"} <= surface          # our module, by AST
    sdk = _sdk_trading_client_methods()
    if sdk:                                                                   # the SDK source, when on disk
        assert {"submit_order", "cancel_orders", "cancel_order_by_id", "close_all_positions",
                "replace_order_by_id", "get_orders", "get_open_position"} <= sdk <= surface | _GENERIC
    assert not (_DATA_ONLY_FROM_ALPACA_CLIENT & surface)


def test_research_bars_module_is_market_data_only():
    # source-pin-ok: a read-only guarantee is the ABSENCE of a call path — no behaviour run can show that no order call exists
    src = (MI / "broker" / "research_bars.py").read_text()
    assert _read_only_violations(src, _RESEARCH_BARS_PROJECT_IMPORTS) == []
    tree = ast.parse(src)
    # DENY BY DEFAULT: every name the module calls, pinned. A new call fails here until reviewed —
    # so the guarantee does not rest on a list of forbidden names being complete.
    assert _called_names(tree) == {
        "_get_data_client", "get_stock_bars",                                   # the ONLY Alpaca reach
        "StockBarsRequest", "TimeFrame", "get_data_feed_name", "ResearchBarsRequestError",
        "ThreadPoolExecutor", "submit", "wait_for", "wrap_future", "done",       # its own thread
        "_bad", "_parse_ts", "_num", "type", "validate_request", "research_bars_in_flight",
        "dumps", "encode", "sum",
        "compile", "match", "getLogger", "error", "fromisoformat", "astimezone", "utcoffset",
        "isoformat", "total_seconds", "timedelta", "is_integer", "strip", "upper", "lower", "endswith",
        "get", "append", "sort", "isinstance", "hasattr", "len", "set", "sorted", "list", "float", "int", "str",
    }
    # ...and the only method ever called on the data client object is get_stock_bars.
    on_client = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                 and n.func.value.id == "client"}
    assert on_client == {"get_stock_bars"}


def test_research_data_helper_is_market_data_only_and_broker_free():
    # source-pin-ok: the ABSENCE of any broker import / other endpoint cannot be shown by running the helper
    src = (MI / "research_data.py").read_text()
    assert _read_only_violations(src, _RESEARCH_DATA_PROJECT_IMPORTS) == []
    urls = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.JoinedStr):               # every f-string that builds a service URL
            if any(isinstance(v, ast.FormattedValue) and getattr(v.value, "id", "") == "base_url"
                   for v in node.values):
                urls.add("".join(v.value for v in node.values if isinstance(v, ast.Constant)))
    assert urls == {"/data/bars"}                         # the one endpoint it knows
    assert "/exec/" not in src


def _function_source(path: Path, name: str) -> str:
    src = path.read_text()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name} not found in {path}")


def test_the_seam_and_the_route_handler_reach_only_the_research_module():
    seam = _function_source(MI / "execution_client.py", "_research_bars_inprocess")
    assert _read_only_violations(
        seam, {"agents.market_intelligence.broker.research_bars"}) == []
    imports = [n for n in ast.walk(ast.parse(seam)) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert [(n.module, [a.name for a in n.names]) for n in imports] == [
        ("agents.market_intelligence.broker.research_bars", ["fetch_research_bars"])]

    handler = _function_source(MI / "execution_routes.py", "_research_bars")
    assert _read_only_violations(handler, set()) == []
    ec_attrs = {n.attr for n in ast.walk(ast.parse(handler))
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "_ec"}
    assert ec_attrs == {"_research_bars_inprocess", "ResearchBarsRequestError"}


@pytest.mark.parametrize("planted", [
    "from alpaca.trading.client import TradingClient\n",
    "import alpaca.trading.client\n",
    "from agents.market_intelligence.broker.alpaca_client import get_account\n",
    "from agents.market_intelligence.broker.alpaca_client import _get_data_client, get_trading_client\n",
    "from agents.market_intelligence.broker.alpaca_client import place_bracket_order\n",
    "from agents.market_intelligence.broker import alpaca_client\n",
    "import agents.market_intelligence.broker.alpaca_client as ac\n",
    "from agents.market_intelligence.broker import order_manager\n",
    "def f(c):\n    return c.cancel_order('x')\n",
    "def f(c):\n    return c.get_all_positions()\n",
    "def f(c):\n    return c.get_account()\n",
    "def f(c):\n    return c.close_position('SPY')\n",
    "def f(m):\n    return getattr(m, 'sub' + 'mit_order')\n",
    "def f():\n    return __import__('alpaca.trading.client')\n",
    "x = _get_trading_client\n",
])
def test_the_guard_flags_a_planted_violation(planted):
    # source-pin-ok: non-vacuity proof for the AST guard itself — its input IS source text
    """Non-vacuity: the same checker that passes the real files must fail on each of these."""
    clean = (MI / "broker" / "research_bars.py").read_text()
    assert _read_only_violations(clean + "\n" + planted, _RESEARCH_BARS_PROJECT_IMPORTS) != []


@pytest.mark.parametrize("planted", ["submit_order", "cancel_orders", "close_all_positions"])
def test_the_guard_flags_an_sdk_order_call(planted):
    # source-pin-ok: non-vacuity proof for the AST guard itself — its input IS source text
    """SDK-only names: caught by the SDK-source surface when alpaca-py is on disk, and ALWAYS by
    the pinned call set (deny by default)."""
    clean = (MI / "broker" / "research_bars.py").read_text()
    dirty = clean + f"\ndef f(c):\n    return c.{planted}()\n"
    assert planted in _called_names(ast.parse(dirty)) - _called_names(ast.parse(clean))
    if _sdk_trading_client_methods():
        assert _read_only_violations(dirty, _RESEARCH_BARS_PROJECT_IMPORTS) != []


# ── (d) research_data.fetch_bars: paging, seams, retry ───────────────────────

def _row(sym, ts, c=1.0):
    return {"symbol": sym, "ts": ts.isoformat(), "o": 1.0, "h": 1.0, "l": 1.0, "c": c, "v": 1}


@pytest.fixture
def wire(monkeypatch):
    """Replace the HTTP hop with a recorder; sleeps are recorded, not slept."""
    state = SimpleNamespace(calls=[], sleeps=[], handler=None)

    def _post(body):
        state.calls.append(body)
        return state.handler(body)

    from agents.market_intelligence import constants
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8006")
    monkeypatch.setattr(rd, "_post", _post)
    monkeypatch.setattr(rd, "_sleep", state.sleeps.append)
    return state


def test_fetch_bars_pages_in_allowed_chunks_and_stitches_in_order(wire):
    start, end = datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 18, tzinfo=UTC)   # 17 days of 1Min

    def handler(body):
        s, e = datetime.fromisoformat(body["start"]), datetime.fromisoformat(body["end"])
        assert e - s <= timedelta(days=ec.RESEARCH_BARS_MAX_RANGE_DAYS["1Min"])
        rows = [_row(sym, s + timedelta(hours=h)) for sym in reversed(body["symbols"]) for h in (5, 1)]
        if s > start:                                     # a bar the previous chunk already returned (seam)
            rows.append(_row(body["symbols"][0], s - timedelta(days=7) + timedelta(hours=1), c=99.0))
        return {"bars": rows}

    wire.handler = handler
    rows = rd.fetch_bars(["tlt", "SPY"], "1Min", start, end.isoformat(), as_frame=False)

    spans = [(c["start"], c["end"]) for c in wire.calls]
    assert spans == [("2026-11-01T00:00:00+00:00", "2026-11-08T00:00:00+00:00"),
                     ("2026-11-08T00:00:00+00:00", "2026-11-15T00:00:00+00:00"),
                     ("2026-11-15T00:00:00+00:00", "2026-11-18T00:00:00+00:00")]         # contiguous, no gap/overlap
    assert all(c["symbols"] == ["TLT", "SPY"] and "feed" not in c for c in wire.calls)
    keys = [(r["symbol"], r["ts"]) for r in rows]
    assert keys == sorted(keys) and len(keys) == len(set(keys)) == 12                    # 2 symbols x 3 chunks x 2
    assert all(r["c"] == 1.0 for r in rows)                                              # the seam duplicate was dropped
    assert wire.sleeps == [rd.PAUSE_SECONDS] * 2                                         # a pause between pages


def test_fetch_bars_returns_a_dataframe(wire):
    pd = pytest.importorskip("pandas")
    t0 = datetime(2026, 11, 13, 14, 30, tzinfo=UTC)
    wire.handler = lambda body: {"bars": [_row("SPY", t0 + timedelta(minutes=1)), _row("SPY", t0)]}
    df = rd.fetch_bars("SPY", "1Min", t0, t0 + timedelta(hours=1), feed="sip")
    assert list(df.columns) == ["symbol", "ts", "o", "h", "l", "c", "v"]
    assert list(df["ts"]) == [pd.Timestamp(t0), pd.Timestamp(t0 + timedelta(minutes=1))]
    assert str(df["ts"].dt.tz) == "UTC" and wire.calls[0]["feed"] == "sip"


def test_fetch_bars_batches_symbols_by_the_route_limit(wire):
    wire.handler = lambda body: {"bars": []}
    names = [f"S{i}" for i in range(120)]
    t0 = datetime(2026, 11, 13, tzinfo=UTC)
    assert rd.fetch_bars(names, "1Day", t0, t0 + timedelta(days=30), as_frame=False) == []
    assert [len(c["symbols"]) for c in wire.calls] == [50, 50, 20]
    assert [s for c in wire.calls for s in c["symbols"]] == names


def test_fetch_bars_halves_a_chunk_over_the_row_cap(wire):
    t0 = datetime(2026, 11, 9, tzinfo=UTC)

    def handler(body):
        s, e = datetime.fromisoformat(body["start"]), datetime.fromisoformat(body["end"])
        if e - s > timedelta(days=2):
            raise ec.ResearchBarsRequestError(400, "row_cap", "too many rows")
        return {"bars": [_row("SPY", s)]}

    wire.handler = handler
    rows = rd.fetch_bars("SPY", "1Min", t0, t0 + timedelta(days=7), as_frame=False)
    got = [(datetime.fromisoformat(c["start"]) - t0, datetime.fromisoformat(c["end"]) - t0) for c in wire.calls]
    d = timedelta
    assert got == [(d(0), d(days=7)), (d(0), d(days=3.5)), (d(0), d(days=1.75)), (d(days=1.75), d(days=3.5)),
                   (d(days=3.5), d(days=5.25)), (d(days=5.25), d(days=7))]
    assert [r["ts"] for r in rows] == [(t0 + x).isoformat() for x in (d(0), d(days=1.75), d(days=3.5), d(days=5.25))]


def test_fetch_bars_retries_busy_and_upstream_with_backoff_then_succeeds(wire):
    t0 = datetime(2026, 11, 13, tzinfo=UTC)
    failures = [ec.ResearchBarsRequestError(429, "busy", ""), ec.ExecutionUnreachable("down"),
                ec.ResearchBarsRequestError(502, "upstream", "")]

    def handler(body):
        if failures:
            raise failures.pop(0)
        return {"bars": [_row("SPY", t0)]}

    wire.handler = handler
    assert len(rd.fetch_bars("SPY", "1Min", t0, t0 + timedelta(hours=1), as_frame=False)) == 1
    assert len(wire.calls) == 4 and wire.sleeps == [2.0, 4.0, 8.0]


def test_fetch_bars_does_not_retry_a_bad_request_and_gives_up_loudly(wire):
    t0 = datetime(2026, 11, 13, tzinfo=UTC)

    def bad(body):
        raise ec.ResearchBarsRequestError(400, "bad_feed", "no")

    wire.handler = bad
    with pytest.raises(ec.ResearchBarsRequestError, match="bad_feed"):
        rd.fetch_bars("SPY", "1Min", t0, t0 + timedelta(hours=1))
    assert len(wire.calls) == 1 and wire.sleeps == []

    def down(body):
        raise ec.ExecutionUnreachable("down")

    wire.calls.clear()
    wire.handler = down
    with pytest.raises(ec.ExecutionUnreachable):
        rd.fetch_bars("SPY", "1Min", t0, t0 + timedelta(hours=1))
    assert len(wire.calls) == rd.MAX_ATTEMPTS


def test_fetch_bars_rejects_naive_times_and_an_unset_url(monkeypatch):
    with pytest.raises(ValueError, match="timezone"):
        rd.fetch_bars("SPY", "1Min", "2026-11-13T09:30:00", "2026-11-13T10:30:00-05:00")
    from agents.market_intelligence import constants
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "")
    slept = []
    monkeypatch.setattr(rd, "_sleep", slept.append)
    with pytest.raises(RuntimeError, match="EXECUTION_SERVICE_URL"):       # a config error: at once, no retries
        rd.fetch_bars("SPY", "1Min", "2026-11-13T09:30:00-05:00", "2026-11-13T10:30:00-05:00")
    with pytest.raises(RuntimeError, match="EXECUTION_SERVICE_URL"):
        rd._post({})
    assert slept == []


def test_post_maps_the_route_error_body(monkeypatch):
    import httpx

    from agents.market_intelligence import constants
    monkeypatch.setattr(constants, "EXECUTION_SERVICE_URL", "http://exec:8006")
    monkeypatch.setattr("shared.secrets.get_secrets", lambda: SimpleNamespace(internal_api_secret="s3"))
    sent = {}

    def fake_post(url, json, timeout, headers):
        sent.update(url=url, headers=headers)
        return httpx.Response(400, json={"detail": {"code": "range_too_long", "message": "page it"}})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(ec.ResearchBarsRequestError) as ei:
        rd._post({"symbols": ["SPY"]})
    assert (ei.value.status, ei.value.code) == (400, "range_too_long")
    assert sent == {"url": "http://exec:8006/data/bars", "headers": {"X-Apollo-Secret": "s3"}}


# ── (e) wiring: off the /exec dispatcher, inside the execution deploy scope ──

def test_research_bars_is_not_an_exec_function():
    assert "research_bars" not in ec._CROSS_FNS and "research_bars" not in er._EXEC_HANDLERS
    assert set(er._EXEC_HANDLERS) == set(ec._CROSS_FNS)


def test_execution_serves_exactly_the_two_post_routes():
    app = FastAPI()
    er.register_execution_routes(app)
    posts = sorted(r.path for r in app.routes if "POST" in (getattr(r, "methods", None) or ()))
    assert posts == ["/data/bars", "/exec/{name}"]


def test_caps_are_single_sourced_in_the_seam():
    assert set(ec.RESEARCH_BARS_MAX_RANGE_DAYS) == set(rb._TIMEFRAMES) == {"1Min", "5Min", "15Min", "1Hour", "1Day"}
    assert rb.RESEARCH_BARS_MAX_RANGE_DAYS is ec.RESEARCH_BARS_MAX_RANGE_DAYS
    assert rd.RESEARCH_BARS_MAX_SYMBOLS == ec.RESEARCH_BARS_MAX_SYMBOLS == 50
    assert rd._READ_TIMEOUT_SECONDS > rb.RESEARCH_BARS_TIMEOUT_S


def test_deploy_routes_the_change_to_execution():
    listed = {ln.strip() for ln in (ROOT / "scripts" / "exec_loaded_modules.txt").read_text().splitlines()}
    assert "agents/market_intelligence/broker/research_bars.py" in listed
    assert "agents/market_intelligence/execution_client.py" in listed
    assert "agents/market_intelligence/execution_routes.py" in listed
