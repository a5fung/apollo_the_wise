"""#687 paper rehearsal (scripts/probes/_687/paper_rehearsal.py) — the SAFETY GUARDS and the step logic.

The rehearsal places real orders on the PAPER account, so what must be proven before it ever runs:
  * it refuses when the paper account is (or might be) the live one, and a tripwire makes any
    non-paper client lookup raise for the rest of the process;
  * it refuses a ticker the paper account already holds, has orders in, or has trade rows for;
  * every broker call it makes — through the REAL environment adapter — carries account_mode='paper'
    and a mode-bound client order id;
  * its checks DISCRIMINATE: a stream that pages instead of recording, or a sale sent without its
    share count, turns the matching step red (a check the broken system also passes is worthless);
  * cleanup never flattens a ticker that carries someone else's paper row.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types

import pytest

_PATH = os.path.join(os.path.dirname(__file__), "..", "scripts", "probes", "_687", "paper_rehearsal.py")


def _load():
    spec = importlib.util.spec_from_file_location("paper_rehearsal_687", _PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["paper_rehearsal_687"] = mod
    spec.loader.exec_module(mod)
    return mod


pr = _load()
TICKERS = pr.DEFAULT_TICKERS


def _steps(log, status=None):
    return {r["step"]: r["status"] for r in log.results if status is None or r["status"] == status}


async def _dry(tmp_path, cmd="all", **kw):
    return await pr.run_dry(cmd, TICKERS, log_dir=str(tmp_path), **kw)


# ── refuses live ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refuses_when_the_paper_account_is_the_live_account(tmp_path):
    with pytest.raises(pr.RehearsalRefused, match="SAME"):
        await _dry(tmp_path, same_account=True)


def test_account_check_refuses_a_live_endpoint_and_shared_keys():
    with pytest.raises(pr.RehearsalRefused, match="paper endpoint"):
        pr.check_account_ids({"paper_id": "A", "live_id": "B",
                              "paper_base_url": "https://api.alpaca.markets"})
    with pytest.raises(pr.RehearsalRefused, match="equals"):
        pr.check_account_ids({"paper_id": "A", "live_id": "B", "same_keys": True})
    with pytest.raises(pr.RehearsalRefused, match="could not be read"):
        pr.check_account_ids({"paper_id": None, "live_id": "B"})
    assert "!=" in pr.check_account_ids({"paper_id": "A", "live_id": "B",
                                         "paper_base_url": "https://paper-api.alpaca.markets"})



def test_the_endpoint_check_reads_a_REAL_trading_client():
    """alpaca-py stores the endpoint as BaseURL(str, Enum): str() of it is 'BaseURL.TRADING_PAPER',
    which the endpoint check refused — every real run would have stopped at preflight. Literal URL
    strings in the test above could not see that. conftest stubs alpaca with MagicMocks, so this
    builds the REAL client (no network) in a clean interpreter."""
    import json
    import subprocess
    code = (
        "import importlib.util, json, sys\n"
        "from alpaca.trading.client import TradingClient\n"
        f"spec = importlib.util.spec_from_file_location('pr', {_PATH!r})\n"
        "pr = importlib.util.module_from_spec(spec); spec.loader.exec_module(pr)\n"
        "paper = pr.client_base_url(TradingClient('PK' + 'X' * 18, 's' * 40, paper=True))\n"
        "live = pr.client_base_url(TradingClient('AK' + 'X' * 18, 's' * 40, paper=False))\n"
        "pr.check_account_ids({'paper_id': 'A', 'live_id': 'B', 'paper_base_url': paper})\n"
        "try:\n"
        "    pr.check_account_ids({'paper_id': 'A', 'live_id': 'B', 'paper_base_url': live})\n"
        "    refused = None\n"
        "except pr.RehearsalRefused as e:\n"
        "    refused = str(e)\n"
        "print(json.dumps({'paper': paper, 'live': live, 'refused': refused}))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    if "No module named 'alpaca'" in out.stderr:
        pytest.skip("alpaca-py not installed")
    assert out.returncode == 0, out.stderr[-2000:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["paper"] == "https://paper-api.alpaca.markets"
    assert got["live"] == "https://api.alpaca.markets"
    assert got["refused"] and "paper endpoint" in got["refused"]


def test_the_tripwire_refuses_every_non_paper_lookup(monkeypatch):
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "k")
    monkeypatch.setenv("ALPACA_LIVE_SECRET_KEY", "s")
    fake = types.SimpleNamespace(
        _TRADING_CLIENTS={"paper": "P", "live": "L"},
        _resolve_account_mode=lambda m: m if m is not None else "live",   # process default = live
    )
    fake.get_trading_client = lambda m=None: f"client:{fake._resolve_account_mode(m)}"
    fake._get_trading_client = fake.get_trading_client
    pr.arm_live_tripwire(fake)
    assert fake.get_trading_client("paper") == "client:paper"
    with pytest.raises(pr.LiveTouched):
        fake.get_trading_client("live")
    with pytest.raises(pr.LiveTouched):
        fake.get_trading_client(None)          # a caller that passes no mode and resolves live
    with pytest.raises(pr.LiveTouched):
        fake._get_trading_client("live")       # the legacy alias too
    assert "live" not in fake._TRADING_CLIENTS
    assert "ALPACA_LIVE_API_KEY" not in os.environ and "ALPACA_LIVE_SECRET_KEY" not in os.environ


# ── refuses a held ticker ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("kw,match", [
    ({"held": {"KO": 5}}, "already holds KO"),
    ({"open_orders": {"PEP": 1}}, "open order"),
    ({"held": {"PG": 1}}, "already holds PG"),          # the cutoff-probe ticker must be flat too
    ({"foreign_rows": {"KO": 1}}, "open paper trade row"),
])
async def test_refuses_a_ticker_the_paper_account_already_has(tmp_path, kw, match):
    with pytest.raises(pr.RehearsalRefused, match=match):
        await _dry(tmp_path, **kw)


@pytest.mark.asyncio
async def test_a_refusal_places_nothing(tmp_path):
    env = pr.FakeEnv(start=pr.datetime(2026, 10, 5, 13, 0, tzinfo=pr._ET), held={"KO": 5})
    log = pr.StepLog(str(tmp_path / "r.log"), env.now)
    with pytest.raises(pr.RehearsalRefused):
        await pr.Rehearsal(env, log, TICKERS).day_a()
    assert not [c for c in env.calls if c[0] == "submit_order"]
    assert env.trades == {}


# ── every call paper ──────────────────────────────────────────────────────────────────────────────

class _RecordingAlpaca(types.SimpleNamespace):
    """Stands in for alpaca_client under the REAL adapter; records the mode of every call."""


def _recording_alpaca(seen):
    def rec(name, ret=None):
        async def f(*a, **k):
            seen.append((name, k.get("account_mode")))
            return ret
        return f

    class _Client:
        def __init__(self, mode):
            self.mode = mode

        def submit_order(self, req):          # the request classes are mocked in the test env
            seen.append(("submit_order", self.mode))
            return types.SimpleNamespace(id="x")

    def get_trading_client(mode=None):
        seen.append(("get_trading_client", mode))
        return _Client(mode)

    def make_client_order_id(mode, strat, t):
        coid = f"apollo_{mode}_{strat}_{t}_{len(seen)}"
        seen.append(("make_client_order_id", mode, coid))
        return coid

    return _RecordingAlpaca(
        get_position=rec("get_position"), get_open_orders=rec("get_open_orders", []),
        get_order=rec("get_order"), cancel_order=rec("cancel_order", True),
        get_trading_client=get_trading_client,
        make_client_order_id=make_client_order_id,
        _order_to_dict=lambda o: {"id": o.id},
    )


@pytest.mark.asyncio
async def test_every_broker_call_through_the_real_adapter_is_paper():
    env = pr.RealEnv(send_pages=False, state_path=os.devnull)
    seen: list = []
    env.alpaca = _recording_alpaca(seen)
    await env.position("KO")
    await env.open_orders("KO")
    await env.get_order("abc")
    await env.cancel("abc")
    for kind, tif, extra in (("market", "day", {}), ("limit", "gtc", {"limit": 99.0}),
                             ("stop", "gtc", {"stop": 60.0}), ("market", "cls", {}),
                             ("market", "opg", {})):
        await env.submit("KO", 1, "buy" if tif in ("cls", "opg") else "sell", kind=kind, tif=tif,
                         **extra)
    modes = [s[1] for s in seen]
    assert modes and set(modes) == {"paper"}, seen
    assert len([s for s in seen if s[0] == "submit_order"]) == 5
    coids = [s[2] for s in seen if s[0] == "make_client_order_id"]
    assert len(coids) == 5 and all(c.startswith("apollo_paper_integration_test_KO_") for c in coids)
    assert len(set(coids)) == 5                     # never two orders with one client order id


@pytest.mark.asyncio
async def test_every_call_in_the_whole_two_day_sequence_is_paper(tmp_path):
    rc, env, log = await _dry(tmp_path)
    assert env.calls and {m for _, m in env.calls} == {"paper"}
    assert rc == 0, log.failed()


# ── the sequence and what its checks can tell apart ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_dry_run_passes_end_to_end_and_cleans_up(tmp_path):
    rc, env, log = await _dry(tmp_path)
    assert rc == 0, log.failed()
    want = {"A1", "A2", "A3", "B1", "B2", "B2b", "B3", "A4", "A5", "A6", "A6a", "A6b", "A6c",
            "A6d", "A6e", "A6f", "A7", "A8", "A9", "A9b", "D1r", "D1", "D2", "D3", "D3b", "D4", "D5",
            "CLEANUP"}
    assert want <= set(_steps(log, "PASS")), _steps(log)
    assert env.trades == {}
    assert all(not q for q in env.positions.values())
    assert not [o for o in env.orders.values() if o["status"] in pr.LIVE_STATUSES]
    assert any(e["event_type"] == pr.END_EVENT for e in env.audit)


@pytest.mark.asyncio
async def test_rows_are_tagged_paper_and_integration_test_on_the_et_date(tmp_path):
    rc, env, log = await _dry(tmp_path, cmd="day-a")
    assert rc == 0, log.failed()
    assert len(env.trades) == 2
    for r in env.trades.values():
        assert r["signal_type"] == "integration_test" and r["account_mode"] == "paper"
        assert r["alert_date"] == pr.date(2026, 10, 5)


@pytest.mark.asyncio
async def test_a_stream_that_pages_instead_of_recording_fails_the_no_page_steps(tmp_path):
    rc, _, log = await _dry(tmp_path, stream_silent=False)
    fails = _steps(log, "FAIL")
    assert rc == 1 and {"A6f", "B2b", "A9b"} <= set(fails), fails


@pytest.mark.asyncio
async def test_a_sale_sent_without_its_share_count_fails_A6c(tmp_path):
    rc, _, log = await _dry(tmp_path, broken_close_qty=True)
    assert rc == 1 and "A6c" in _steps(log, "FAIL")


@pytest.mark.asyncio
async def test_the_rehearsal_drives_the_opening_auction_sale_itself_if_the_19_01_job_did_not(tmp_path):
    rc, _, log = await _dry(tmp_path, prod_depth_job=False)
    a9 = [r for r in log.results if r["step"] == "A9"][0]
    assert rc == 0 and a9["status"] == "PASS" and "THIS process" in a9["detail"]


@pytest.mark.asyncio
async def test_a_row_an_overnight_job_closed_fails_before_the_open(tmp_path):
    """D3 ('closed by the stream after the fill') would also read true if the 21:00 sync had closed
    the row — so D1r pins both rows OPEN at 3 sh before the open."""
    rc, env, log = await _dry(tmp_path, cmd="day-a")
    assert rc == 0
    p2 = [r for r in env.trades.values() if r["ticker"] == "PEP"][0]
    p2.update(status="closed", remaining_shares=0.0)            # an overnight resolver closed it
    env.clock = pr.datetime(2026, 10, 6, 9, 0, tzinfo=pr._ET)
    assert await pr.Rehearsal(env, log, TICKERS).day_b() == 1
    d1r = [r for r in log.results if r["step"] == "D1r" and "PEP" in r["title"]]
    assert d1r and d1r[0]["status"] == "FAIL"


def test_a_cutoff_probe_rejected_for_quantity_proves_nothing():
    assert pr.WRONG_REASON.search('{"message":"insufficient qty available for order"}')
    assert pr.WRONG_REASON.search("potential wash trade detected")
    assert not pr.WRONG_REASON.search('{"message":"market on close orders must be submitted '
                                      'before 15:50"}')


def test_pages_read_as_a_paper_rehearsal():
    for raw in ("📄 PAPER ⚠️ Full exit FAILED for KO", "⚠️ Full exit FAILED for KO"):
        out = pr.route_page(raw)
        assert out.startswith("📄 PAPER " + pr.REHEARSAL_TAG) and out.endswith("Full exit FAILED for KO")


# ── cleanup ──────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleanup_never_flattens_a_ticker_carrying_someone_elses_paper_row(tmp_path):
    rc, env, log = await _dry(tmp_path, cmd="day-a")
    assert rc == 0
    env.foreign_rows = {"KO": 1}                       # a paper strategy entered KO overnight
    env.clock = pr.datetime(2026, 10, 6, 10, 0, tzinfo=pr._ET)   # cleanup in market hours
    reh = pr.Rehearsal(env, log, TICKERS)
    assert await reh.cleanup() == 1
    assert env.positions.get("KO")                     # KO left alone
    assert not env.positions.get("PEP")                # PEP (no foreign row) flattened
    assert "KO" in [r for r in log.results if r["step"] == "CLEANUP"][-1]["detail"]


@pytest.mark.asyncio
async def test_cleanup_still_deletes_the_rows_when_a_flatten_is_refused(tmp_path):
    """A refused flatten (a re-protect stop holding the shares) used to raise out of cleanup before
    the rows were deleted — leaving them counting toward the paper position cap."""
    rc, env, log = await _dry(tmp_path, cmd="day-a")
    assert rc == 0
    env.clock = pr.datetime(2026, 10, 6, 10, 0, tzinfo=pr._ET)
    real_submit = env.submit

    async def refusing(t, qty, side, **kw):
        if side == "sell" and kw.get("kind") == "market":
            raise RuntimeError('{"message":"insufficient qty available for order"}')
        return await real_submit(t, qty, side, **kw)

    env.submit = refusing
    assert await pr.Rehearsal(env, log, TICKERS).cleanup() == 1
    assert env.trades == {}
    assert any(e["event_type"] == pr.END_EVENT for e in env.audit)
    assert "FAILED" in [r for r in log.results if r["step"] == "CLEANUP"][-1]["detail"]


# ── production's +2R profit trigger must not reach the rehearsal rows ─────────────────────────────

def _selected_by_scan_profit_triggers(row) -> bool:
    """order_manager.scan_profit_triggers' own WHERE clause (no signal_type filter)."""
    return (row["status"] == "filled" and float(row["remaining_shares"]) > 0
            and not row.get("partial_taken"))


@pytest.mark.asyncio
async def test_no_rehearsal_row_is_eligible_for_the_production_profit_trigger(tmp_path):
    """On the rehearsal's R frame the +2R target sits 1% above the fill; with partial_taken FALSE the
    5-minute production scan would sell a third of P2 on an ordinary day and break every Day B step."""
    rc, env, log = await _dry(tmp_path, cmd="day-a")
    assert rc == 0, log.failed()
    assert env.trades and not [r for r in env.trades.values() if _selected_by_scan_profit_triggers(r)]
    # ...and the REAL insert writes TRUE (the fake above only mirrors it).
    # source-pin-ok: the real INSERT runs only against Postgres (no DB in unit tests); A1/B1 read the
    # column back from the DB at run time, which is the behavioural check on the real path.
    import inspect
    import re
    src = inspect.getsource(pr.RealEnv.insert_trade)
    assert re.search(r"partial_taken, filled_at\)\s*VALUES \(.*, 0, TRUE, NOW\(\)\)", src, re.S), src


@pytest.mark.asyncio
async def test_a_row_left_eligible_for_the_profit_trigger_fails_A1_and_B1(tmp_path):
    rc, _, log = await _dry(tmp_path, cmd="day-a", partial_taken_false=True)
    assert rc == 1 and {"A1", "B1"} <= set(_steps(log, "FAIL")), _steps(log)
