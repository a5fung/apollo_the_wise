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
import sqlite3
import sys
import types
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

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

        def get_order_by_id(self, oid):       # R1's read of the broker's cancel stamp
            seen.append(("get_order_by_id", self.mode))
            return types.SimpleNamespace(canceled_at=None)

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
    assert await env.cancelled_at("abc") is None
    for kind, tif, extra in (("market", "day", {}), ("limit", "gtc", {"limit": 99.0}),
                             ("stop", "gtc", {"stop": 60.0}), ("market", "cls", {}),
                             ("market", "opg", {})):
        await env.submit("KO", 1, "buy" if tif in ("cls", "opg") else "sell", kind=kind, tif=tif,
                         **extra)
    modes = [s[1] for s in seen]
    assert modes and set(modes) == {"paper"}, seen
    assert ("get_order_by_id", "paper") in seen
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
    want = {"A1", "A2", "A3", "B1", "B2", "B2b", "B3", "A5", "A6", "A6a", "A6b", "A6c",
            "A6d", "A6e", "A6f", "A7", "A8", "A9", "A9b", "D1r", "D1", "D2", "D3", "D3b", "D4", "D5",
            "CLEANUP"}
    assert want <= set(_steps(log, "PASS")), _steps(log)
    assert _steps(log)["A4"] == "INFO"                 # recorded, never judged (2026-10-06)
    assert {_steps(log)[s] for s in ("R1", "R1f", "R1c")} == {"INFO"}, _steps(log)
    # Day A left both positions for Day B — exactly one cleanup ran, at the END of Day B.
    cleanups = [r for r in log.results if r["step"] == "CLEANUP"]
    assert len(cleanups) == 1 and cleanups[0]["at"].date() == pr.date(2026, 10, 6)
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
    """A6f / A9b: a sale that WORKED leaves no replacement stop, so a stream without the planned-
    sale silent path pages 'unprotected' there. B2's restored stop takes the stream's REPLACEMENT
    branch instead — it never reaches the silent path, so B2b is judged on that branch and passes
    (its own FAIL arm is the next test)."""
    rc, _, log = await _dry(tmp_path, stream_silent=False)
    fails = _steps(log, "FAIL")
    assert rc == 1 and {"A6f", "A9b"} <= set(fails), fails
    assert _steps(log)["B2b"] == "PASS", _steps(log)


@pytest.mark.asyncio
async def test_b2b_fails_when_the_stream_neither_sees_the_restored_stop_nor_records_the_cancel(tmp_path):
    """The broken system B2b must catch: the pointer nulled, no replacement seen, no silent row —
    the stream paged 'unprotected'."""
    rc, _, log = await _dry(tmp_path, cmd="day-a", stream_silent=False,
                            stream_sees_replacement=False)
    b2b = [r for r in log.results if r["step"] == "B2b"][0]
    assert b2b["status"] == "FAIL" and "NONE of the three rows" in b2b["detail"], b2b
    assert rc == 1


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


@pytest.mark.asyncio
async def test_the_real_insert_writes_a_row_the_production_profit_trigger_cannot_select():
    """The fake above only MIRRORS the insert. This runs the REAL `RealEnv.insert_trade` statements
    (the INSERT and the account-mode read-back, as written for Postgres) on an in-memory SQLite
    stand-in for mi_live_trades whose `partial_taken` defaults FALSE as production's does, then
    asks production's own selection predicate about the row that landed.

    MUTATION TARGETS: write FALSE for partial_taken; drop the column from the INSERT."""
    db = sqlite3.connect(":memory:")
    db.create_function("NOW", 0, lambda: "2026-10-06T10:00:00")
    db.execute("""CREATE TABLE mi_live_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, alert_date TEXT, status TEXT,
        account_mode TEXT, signal_type TEXT, entry_shares REAL, remaining_shares REAL,
        entry_price REAL, stop_price REAL, hard_stop REAL, orb_low REAL, stop_order_id TEXT,
        hold_days INTEGER, partial_taken INTEGER NOT NULL DEFAULT 0, filled_at TEXT)""")

    async def fetchval(sql, *args):
        row = db.execute(sql, {str(i + 1): a for i, a in enumerate(args)}).fetchone()
        return row[0] if row else None
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=fetchval)
    env = pr.RealEnv()
    env.db = types.SimpleNamespace(get_pool=AsyncMock(return_value=pool))

    tid = await env.insert_trade(ticker="KO", shares=10, entry=60.0, stop=57.0, stop_id="stop-1",
                                 alert_date="2026-10-06")

    status, remaining, partial_taken, mode = db.execute(
        "SELECT status, remaining_shares, partial_taken, account_mode FROM mi_live_trades WHERE id = ?",
        (tid,)).fetchone()
    assert mode == pr.ACCOUNT_MODE and status == "filled" and remaining == 10.0
    assert not _selected_by_scan_profit_triggers(
        {"status": status, "remaining_shares": remaining, "partial_taken": bool(partial_taken)})


@pytest.mark.asyncio
async def test_a_row_left_eligible_for_the_profit_trigger_fails_A1_and_B1(tmp_path):
    rc, _, log = await _dry(tmp_path, cmd="day-a", partial_taken_false=True)
    assert rc == 1 and {"A1", "B1"} <= set(_steps(log, "FAIL")), _steps(log)


# ── #687 2026-10-06 (i) SPACING: never fire a step against a pending_new order ───────────────────

async def _day_a_from(tmp_path, start, **kw):
    env = pr.FakeEnv(start=start, **kw)
    log = pr.StepLog(str(tmp_path / "r.log"), env.now)
    rc = await pr.Rehearsal(env, log, TICKERS).day_a()
    return rc, env, log


MON_0920 = pr.datetime(2026, 10, 5, 9, 20, tzinfo=pr._ET)
MON_1300 = pr.datetime(2026, 10, 5, 13, 0, tzinfo=pr._ET)   # past the spec times: back to back


@pytest.mark.asyncio
async def test_a2_waits_until_the_p1_stop_is_routed_not_pending_new(tmp_path):
    """10-06: A2 fired 2 s after A1 while A1's stop was `pending_new`; the production partial exit
    read it as not live and aborted. Started past the spec times the steps run back to back — and
    every stop the script places still waits for `new` before the next step."""
    rc, env, log = await _day_a_from(tmp_path, MON_1300, pending_new_s=3.0)
    assert env.partial_exit_saw == "new", env.partial_exit_saw
    assert _steps(log)["A2"] == "PASS" and _steps(log)["B1"] == "PASS", _steps(log)
    assert rc == 0, log.failed()


@pytest.mark.asyncio
async def test_the_pending_new_check_discriminates(tmp_path, monkeypatch):
    """Negative control: waiting on the OLD set (which includes pending_new) reproduces 10-06's A2."""
    monkeypatch.setattr(pr, "STOP_LIVE", pr.LIVE_STATUSES)
    rc, env, log = await _day_a_from(tmp_path, MON_1300, pending_new_s=3.0)
    assert env.partial_exit_saw == "pending_new"
    assert _steps(log)["A2"] == "FAIL"


@pytest.mark.asyncio
async def test_the_morning_steps_run_no_earlier_than_their_spec_times(tmp_path):
    rc, env, log = await _day_a_from(tmp_path, MON_0920)
    at = {r["step"]: r["at"].timetz().replace(tzinfo=None) for r in log.results}
    assert at["A1"] >= pr.T_A1 and at["A2"] >= pr.T_A2 and at["A3"] >= pr.T_A3, at
    assert at["B1"] >= pr.T_B1, at
    assert pr.T_R1 <= at["R1"] <= at["R1f"] < pr.T_A1, at       # R1 flat before A1's 10:00
    assert env.partial_exit_at.timetz().replace(tzinfo=None) >= pr.T_A2
    assert rc == 0, log.failed()


# ── B2 with the restore retry (#687 2026-10-06, the order_manager fix) ──────────────────────────

def _step(log, sid):
    return [r for r in log.results if r["step"] == sid][-1]


def _p2_rows(env, event):
    p2 = [tid for tid, r in env.trades.items() if r["ticker"] == "PEP"]
    return [a for a in env.audit if a["event_type"] == event and a["detail"].get("trade_id") in p2]


@pytest.mark.asyncio
async def test_b2_passes_when_the_restore_lands_on_a_retry(tmp_path):
    rc, _, log = await _dry(tmp_path, cmd="day-a", restore_retries=3)
    b2 = _step(log, "B2")
    assert b2["status"] == "PASS", b2
    assert "4 (3 refused)" in b2["detail"] and "stop_restore_retried rows 1" in b2["detail"], b2
    assert "path: RETRY" in b2["detail"] and "retry PROVEN live" in b2["detail"], b2


@pytest.mark.asyncio
async def test_b2_first_attempt_passes_and_says_the_retry_was_not_exercised(tmp_path):
    """Review 2026-10-06, MUST-FIX 2: Thursday's spacing likely settles the cancel before the sale,
    so the FIRST restore attempt works. B2 passes on the spec's 5 s bar and SAYS the retry was not
    exercised live — it must not fail for want of a `stop_restore_retried` row."""
    rc, _, log = await _dry(tmp_path, cmd="day-a")
    b2 = _step(log, "B2")
    assert b2["status"] == "PASS", b2
    assert "path: FIRST ATTEMPT" in b2["detail"] and "NOT exercised live" in b2["detail"], b2
    assert "stop_restore_retried rows 0" in b2["detail"], b2


@pytest.mark.asyncio
async def test_b2_fails_a_retry_slower_than_its_bar(tmp_path):
    """40 refusals 0.5 s apart = 20 s from the first refused attempt > RETRY_BAR_S."""
    assert pr.RETRY_BAR_S < 40 * 0.5
    rc, _, log = await _dry(tmp_path, cmd="day-a", restore_retries=40)
    b2 = _step(log, "B2")
    assert b2["status"] == "FAIL" and "path: RETRY" in b2["detail"], b2


@pytest.mark.asyncio
async def test_b2_fails_a_retry_that_wrote_no_retried_row(tmp_path, monkeypatch):
    """On the retry path the `stop_restore_retried` row IS the live proof the DONE-WHEN reads —
    a retried placement without it is a FAIL, not a pass."""
    real = pr.FakeEnv._audit

    def _drop(self, event, detail, summary=""):
        if event != "stop_restore_retried":
            real(self, event, detail, summary)

    monkeypatch.setattr(pr.FakeEnv, "_audit", _drop)
    rc, _, log = await _dry(tmp_path, cmd="day-a", restore_retries=2)
    b2 = _step(log, "B2")
    assert b2["status"] == "FAIL" and "NO stop_restore_retried row" in b2["detail"], b2


def test_the_retry_bar_tracks_the_production_window():
    from agents.market_intelligence.broker import order_manager as om
    assert pr.RESTORE_RETRY_WINDOW_S == om._RESTORE_RETRY_WINDOW_S
    assert pr.RESTORE_RETRY_WINDOW_S == om._RESTORE_RETRY_POLLS * om._RESTORE_RETRY_SLEEP_S


# ── B2b: the stream's three no-page outcomes (review 2026-10-06, MUST-FIX 1) ────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("retries", [0, 3])
async def test_b2b_passes_on_the_deferred_repair_when_the_stream_nulled_first(tmp_path, retries):
    """The likeliest shape for a restore that WORKS: the stream nulls the pointer as the cancel
    lands, the restore writes its own, the stream's re-check finds the restored stop and its #646
    (e) fill defers. NO silent row is written — the old B2b, keyed on that row alone, FAILED here."""
    rc, env, log = await _dry(tmp_path, cmd="day-a", restore_retries=retries)
    b2b = _step(log, "B2b")
    assert b2b["status"] == "PASS" and "stop_pointer_repair_deferred" in b2b["detail"], b2b
    assert not [a for a in _p2_rows(env, "stop_cancel_by_planned_sale_silent")
                if a["at"].hour < 12], "a working restore takes the replacement branch, not silent"
    assert rc == 0, log.failed()


@pytest.mark.asyncio
async def test_b2b_passes_on_the_stream_repair_when_its_null_landed_after_the_restore(tmp_path):
    """The race (b) ordering: the stream nulled the pointer AFTER the restore's write; its own
    #646 (e) fill writes the restored stop back at once (`cancel_or_reject_restored`)."""
    rc, env, log = await _dry(tmp_path, cmd="day-a", restore_retries=1, stream_null_late=True)
    b2, b2b = _step(log, "B2"), _step(log, "B2b")
    assert b2b["status"] == "PASS" and "cancel_or_reject_restored" in b2b["detail"], b2b
    assert b2["status"] == "PASS" and "row points at it" in b2["detail"], b2
    assert rc == 0, log.failed()


@pytest.mark.asyncio
async def test_b2b_passes_on_the_silent_row_when_the_stream_misses_the_restored_stop(tmp_path):
    rc, _, log = await _dry(tmp_path, cmd="day-a", stream_sees_replacement=False)
    b2b = _step(log, "B2b")
    assert b2b["status"] == "PASS" and "SILENT path" in b2b["detail"], b2b


@pytest.mark.asyncio
async def test_b2_reads_the_restored_stop_by_its_id_when_the_stream_nulled_the_pointer(tmp_path):
    """The race (b) ordering with the stream's broker check MISSING the restored stop: the pointer
    stays NULL while the stop is live. B2 reads it by the id the placement returned, passes, and
    NAMES the null; the stop-ACK watchdog re-adopts it, so P2 is ready by evening."""
    rc, env, log = await _dry(tmp_path, cmd="day-a", restore_retries=1, stream_null_late=True,
                              stream_sees_replacement=False)
    b2 = _step(log, "B2")
    assert b2["status"] == "PASS" and "row pointer NULL" in b2["detail"], b2
    assert "#646 (e)" in b2["detail"], b2
    assert _steps(log)["A8"] == "PASS" and rc == 0, log.failed()     # re-adopted by evening


@pytest.mark.asyncio
async def test_b2_still_fails_when_the_restore_never_lands(tmp_path):
    """The 10-06 shape: one refused restore, the watchdog's fallback 45 s later."""
    rc, _, log = await _dry(tmp_path, cmd="day-a", restore_lost_watchdog_s=45)
    assert _steps(log)["B2"] == "FAIL" and rc == 1


@pytest.mark.asyncio
async def test_b2b_skips_when_the_restore_repointed_the_row_before_the_stream_saw_the_cancel(tmp_path):
    """A restore that lands at the moment the cancel settles can re-point the row before the stream
    handles the cancel; the stream (lookup by the cancelled stop's id) then matches nothing and can
    neither record nor page — B2b has nothing to prove, so it SKIPs instead of failing."""
    rc, _, log = await _dry(tmp_path, cmd="day-a", restore_retries=2, stream_missed_cancel=True)
    b2b = [r for r in log.results if r["step"] == "B2b"][0]
    assert b2b["status"] == "SKIP" and "re-pointed" in b2b["detail"], b2b
    assert rc == 0, log.failed()


# ── (ii) A4 is informational ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a4_records_an_accepted_market_on_close_as_info_never_fail(tmp_path):
    rc, env, log = await _dry(tmp_path, cmd="day-a", cls_accepted=True)
    a4 = [r for r in log.results if r["step"] == "A4"][0]
    assert a4["status"] == "INFO" and "ACCEPTED" in a4["detail"], a4
    assert rc == 0 and "A4" not in [f["step"] for f in log.failed()]
    probe = [o for o in env.orders.values() if o["symbol"] == "PG" and o["tif"] == "cls"]
    assert probe and probe[0]["status"] == "canceled"


@pytest.mark.asyncio
async def test_a4_records_a_rejected_market_on_close_as_info(tmp_path):
    rc, _, log = await _dry(tmp_path, cmd="day-a")
    a4 = [r for r in log.results if r["step"] == "A4"][0]
    assert a4["status"] == "INFO" and "rejected" in a4["detail"], a4


@pytest.mark.asyncio
async def test_a7_is_still_judged(tmp_path):
    rc, _, log = await _dry(tmp_path, cmd="day-a")
    assert _steps(log)["A7"] == "PASS"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,ready", [("new", True), ("accepted", True), ("held", True),
                                          ("pending_new", False)])
async def test_a8_takes_a_stop_re_placed_after_the_close(tmp_path, status, ready):
    """Review 2026-10-06 (NICE 6): at 18:50 a stop re-placed after the close reads `accepted`, not
    `new` — it still protects P2 at the open. Only an unrouted `pending_new` stop is not ready."""
    env = pr.FakeEnv(start=pr.datetime(2026, 10, 5, 18, 50, tzinfo=pr._ET))
    env.positions["PEP"] = 3.0
    stop = env._new("PEP", 3, "sell", "stop", "gtc", status=status, stop=140.0)
    tid = await env.insert_trade(ticker="PEP", shares=3, entry=150.0, stop=140.0,
                                 stop_id=stop["id"], alert_date=pr.date(2026, 10, 5))
    reh = pr.Rehearsal(env, pr.StepLog(str(tmp_path / "r.log"), env.now), TICKERS)
    reh.state = {"p2": {"trade_id": tid}}
    ok, detail = await reh._p2_ready()
    assert ok is ready, detail


# ── (iii) the end of Day A cleans up only when Day B has nothing left to test ────────────────────

def _day_a_cleaned(log):
    return [r for r in log.results if r["step"] == "CLEANUP" and r["at"].date() == pr.date(2026, 10, 5)]


@pytest.mark.asyncio
async def test_the_10_06_shape_leaves_p2_for_day_b(tmp_path):
    """10-06: B2 and B3 FAILED on the restore's timing, but the watchdog's fallback stop left P2
    3 sh under a live stop by evening. A8 re-reads that itself → P2 is marked, its opening-auction
    sale queues, and Day A no longer wipes it."""
    rc, env, log = await _dry(tmp_path, cmd="day-a", restore_lost_watchdog_s=45)
    st = _steps(log)
    assert st["B2"] == "FAIL" and st["B3"] == "FAIL", st
    assert st["A8"] == "PASS" and st["A9"] == "PASS", st
    assert not _day_a_cleaned(log) and len(env.trades) == 2
    env.clock = pr.datetime(2026, 10, 6, 9, 0, tzinfo=pr._ET)
    await pr.Rehearsal(env, log, TICKERS).day_b()
    assert _steps(log)["D3"] == "PASS"             # P2's opening-auction sale filled, row closed


@pytest.mark.asyncio
async def test_a_broken_p1_chain_leaves_p2_and_day_b_skips_p1s_checks(tmp_path):
    rc, env, log = await _dry(tmp_path, partial_exit_fails=True)
    st = _steps(log)
    assert st["A2"] == "FAIL" and st["A9"] == "PASS", st
    assert not _day_a_cleaned(log)
    assert st["D3"] == "PASS" and st["D3b"] == "SKIP" and st["D4"] == "SKIP", st
    assert st["CLEANUP"] == "PASS" and env.trades == {}
    assert {f["step"] for f in log.failed()} == {"A2"}, log.failed()


@pytest.mark.asyncio
async def test_day_a_cleans_up_when_every_position_lost_a_dependency(tmp_path):
    rc, env, log = await _dry(tmp_path, cmd="day-a", partial_taken_false=True)
    assert {"A1", "B1"} <= set(_steps(log, "FAIL"))
    assert _day_a_cleaned(log) and env.trades == {}
    with open(log.path, encoding="utf-8") as fh:
        note = [line for line in fh if "Day B has nothing to test" in line]
    assert note and "P1: A1 FAIL" in note[0] and "P2: B1 FAIL" in note[0], note


def test_a_failure_outside_the_dependencies_breaks_no_chain(tmp_path):
    env = pr.FakeEnv(start=pr.datetime(2026, 10, 5, 13, 0, tzinfo=pr._ET))
    log = pr.StepLog(str(tmp_path / "r.log"), env.now)
    reh = pr.Rehearsal(env, log, TICKERS)
    reh.state = {"p1": {"sale_id": "s1"}, "p2": {"sale_id": "s2"}}
    for sid in ("A1", "A2", "A6", "B1", "A8", "A9"):
        log.step(sid, sid, True)
    for sid in ("A3", "A5", "A6b", "B2", "B2b", "B3", "A7", "A9b"):
        log.step(sid, sid, False)
    log.step("A4", "A4", None, status="INFO")
    assert reh._day_b_broken_chains() == {}
    log.step("A9", "A9 again", False)                  # the LAST status of a step decides
    assert set(reh._day_b_broken_chains()) == {"p2"}


# ── R1: the 10-06 timing on its own ticker — INFORMATIONAL (#687, operator "Ok" 2026-10-06) ──────
# B2 now waits for routed orders, so its restore most likely works on the FIRST attempt and never
# exercises the held-shares retry against the real broker. R1 re-creates 10-06's unrouted shape on
# a dedicated ticker. Whatever it sees it is INFO: never a FAIL, never in Day A's tally, never a
# Day B dependency, never the reason Day A cleans up (or does not).

def _non_r1(log):
    return {r["step"]: r["status"] for r in log.results if not r["step"].startswith("R1")}


def _cl_left(env):
    return (env.positions.get("CL"),
            [o["id"] for o in env.orders.values()
             if o["symbol"] == "CL" and o["status"] in pr.LIVE_STATUSES],
            [tid for tid, r in env.trades.items() if r["ticker"] == "CL"])


@pytest.mark.asyncio
async def test_r1_says_the_retry_was_proven_live_when_the_retry_placed_the_stop(tmp_path):
    rc, env, log = await _dry(tmp_path, cmd="day-a", restore_retries=3)
    r1 = _step(log, "R1")
    assert r1["status"] == "INFO" and "retry PROVEN live" in r1["detail"], r1
    assert "stop_restore_retried: attempt 4" in r1["detail"], r1
    for when in ("cancel requested 13:", "broker confirmed the cancel 13:", "placed 13:"):
        assert when in r1["detail"], (when, r1["detail"])
    assert "STOP NOT RESTORED page: no" in r1["detail"], r1
    r1f = _step(log, "R1f")
    assert r1f["status"] == "INFO" and "CL flat" in r1f["detail"], r1f
    assert _cl_left(env) == (0.0, [], []), _cl_left(env)
    assert rc == 0, log.failed()


@pytest.mark.asyncio
async def test_r1_says_the_retry_was_not_exercised_when_the_first_attempt_worked(tmp_path):
    rc, env, log = await _dry(tmp_path, cmd="day-a")
    r1 = _step(log, "R1")
    assert r1["status"] == "INFO" and "retry NOT exercised" in r1["detail"], r1
    assert "PROVEN" not in r1["detail"]
    assert _cl_left(env) == (0.0, [], []) and rc == 0


@pytest.mark.asyncio
async def test_r1_records_the_unrestored_page_the_retry_end_and_the_watchdog_fallback(tmp_path):
    """The restore never lands: R1 records the retry's end, the STOP NOT RESTORED page and the
    stop-ACK watchdog's fallback — and R1f still cancels that fallback and leaves CL flat."""
    rc, env, log = await _dry(tmp_path, cmd="day-a", restore_lost_watchdog_s=45)
    r1 = _step(log, "R1")
    assert r1["status"] == "INFO", r1
    assert "stop_restore_retry_ended 'failed'" in r1["detail"], r1
    assert "STOP NOT RESTORED page: YES" in r1["detail"], r1
    assert "stop_ack_timeout_remediated: YES" in r1["detail"], r1
    assert _step(log, "R1f")["status"] == "INFO" and _cl_left(env) == (0.0, [], [])
    assert "R1" not in [f["step"] for f in log.failed()]      # B2 FAILs here; R1 never does


@pytest.mark.asyncio
@pytest.mark.parametrize("kw,r1_ticker,why", [
    ({"held": {"CL": 5}}, "CL", "already holds CL"),
    ({"open_orders": {"CL": 1}}, "CL", "open order"),
    ({"foreign_rows": {"CL": 1}}, "CL", "open paper trade row"),
    ({}, "PEP", "no other step uses"),
    ({}, "", "no R1 ticker"),
])
async def test_r1_is_skipped_as_info_when_its_ticker_is_not_clean(tmp_path, kw, r1_ticker, why):
    """A ticker that fails the start-of-day checks skips R1 (INFO) — Day A is NOT refused, and
    cleanup never adds a ticker R1 never touched (a held CL is left exactly as it was)."""
    rc, env, log = await _dry(tmp_path, r1_ticker=r1_ticker, **kw)
    r1 = _step(log, "R1")
    assert r1["status"] == "INFO" and "skipped" in r1["detail"] and why in r1["detail"], r1
    assert "R1f" not in _steps(log) and "R1c" not in _steps(log)
    assert not [o for o in env.orders.values() if o["symbol"] == "CL" and o["client_order_id"]]
    assert rc == 0, log.failed()
    if kw.get("held"):
        assert env.positions["CL"] == 5                       # untouched through Day B's cleanup


SHAPES = [{}, {"restore_retries": 3}, {"restore_lost_watchdog_s": 45},
          {"partial_taken_false": True}, {"partial_exit_fails": True}]


@pytest.mark.asyncio
@pytest.mark.parametrize("kw", SHAPES, ids=[",".join(k) or "default" for k in SHAPES])
async def test_r1_never_changes_day_as_tally_or_its_cleanup_decision(tmp_path, kw):
    """The same Day A with R1 and with R1 skipped: every other step's status, the exit code and
    whether Day A cleaned up at its end are identical; R1's own lines are INFO."""
    (tmp_path / "with").mkdir()
    (tmp_path / "without").mkdir()
    rc1, _, with_r1 = await pr.run_dry("day-a", TICKERS, log_dir=str(tmp_path / "with"), **kw)
    rc0, _, without = await pr.run_dry("day-a", TICKERS, log_dir=str(tmp_path / "without"),
                                       r1_ticker=None, **kw)
    assert _non_r1(with_r1) == _non_r1(without), (_non_r1(with_r1), _non_r1(without))
    assert rc1 == rc0
    assert bool(_day_a_cleaned(with_r1)) == bool(_day_a_cleaned(without))
    assert {r["status"] for r in with_r1.results if r["step"].startswith("R1")} == {"INFO"}
    assert {r["step"] for r in with_r1.results if r["step"].startswith("R1")} >= {"R1", "R1f"}


@pytest.mark.asyncio
async def test_r1_crashing_is_info_and_still_leaves_its_ticker_flat(tmp_path):
    env = pr.FakeEnv(start=MON_1300)
    real = env.full_exit

    async def boom(tid, reason):
        if env.trades[tid]["ticker"] == "CL":
            raise RuntimeError("broker 500")
        return await real(tid, reason)

    env.full_exit = boom
    log = pr.StepLog(str(tmp_path / "r.log"), env.now)
    rc = await pr.Rehearsal(env, log, TICKERS).day_a()
    r1 = _step(log, "R1")
    assert r1["status"] == "INFO" and "R1 raised RuntimeError" in r1["detail"], r1
    assert _step(log, "R1f")["status"] == "INFO" and _cl_left(env) == (0.0, [], [])
    assert rc == 0 and not log.failed(), log.failed()


@pytest.mark.asyncio
@pytest.mark.parametrize("still_refused", [False, True])
async def test_the_cleanup_command_covers_r1s_ticker_when_its_flatten_failed(tmp_path, still_refused):
    """R1f's sale refused → INFO, the row and the shares are LEFT, R1's ticker and ids stay in the
    state. The ordinary `cleanup` then flattens CL and deletes the row; what it cannot clear on CL
    is INFO (R1c), never the CLEANUP verdict — but `cleanup` still exits 1 so it is re-run."""
    env = pr.FakeEnv(start=MON_1300)
    real_submit = env.submit
    refuse = {"on": True}

    async def refusing(t, qty, side, **kw):
        if refuse["on"] and t == "CL" and side == "sell" and kw.get("kind") == "market":
            raise RuntimeError('{"message":"insufficient qty available for order"}')
        return await real_submit(t, qty, side, **kw)

    env.submit = refusing
    log = pr.StepLog(str(tmp_path / "r.log"), env.now)
    rc = await pr.Rehearsal(env, log, TICKERS).day_a()
    r1f = _step(log, "R1f")
    assert r1f["status"] == "INFO" and "REFUSED" in r1f["detail"], r1f
    assert "`cleanup` covers CL" in r1f["detail"], r1f
    assert rc == 0 and not log.failed(), log.failed()           # Day A's result is untouched
    assert not _day_a_cleaned(log)                               # ...and so is its cleanup decision
    pos, live, rows = _cl_left(env)
    assert pos == 4 and rows, _cl_left(env)
    assert env.state["r1"]["ticker"] == "CL" and env.state["r1"]["buy_id"] in env.state["order_ids"]
    assert "CL" not in env.state["tickers"]                      # Day B's P1/P2/probe unpack stays 3

    refuse["on"] = still_refused
    env.clock = pr.datetime(2026, 10, 6, 10, 0, tzinfo=pr._ET)   # `cleanup` in market hours
    rc_clean = await pr.Rehearsal(env, log, TICKERS).cleanup()
    assert _step(log, "CLEANUP")["status"] == "PASS", _step(log, "CLEANUP")
    r1c = _step(log, "R1c")
    assert r1c["status"] == "INFO"
    assert env.trades == {}
    if still_refused:
        assert rc_clean == 1 and "CL: flatten of 4.0 sh FAILED" in r1c["detail"], r1c
    else:
        assert rc_clean == 0 and r1c["detail"] == "clean", r1c
        assert _cl_left(env) == (0.0, [], [])


@pytest.mark.asyncio
async def test_r1_rechecks_its_ticker_right_before_it_places(tmp_path):
    """Day A checks at launch (~09:24) but R1 places at 09:35:30, inside the ORB window: a paper
    entry that took CL in between skips R1 and leaves that position exactly as it was."""
    env = pr.FakeEnv(start=MON_0920)

    def _paper_entry():
        env.positions["CL"] = 7.0
        env.foreign_rows["CL"] = 1

    env._timers.append((pr.datetime(2026, 10, 5, 9, 33, tzinfo=pr._ET), _paper_entry))
    log = pr.StepLog(str(tmp_path / "r.log"), env.now)
    rc = await pr.Rehearsal(env, log, TICKERS).day_a()
    r1 = _step(log, "R1")
    assert r1["status"] == "INFO" and "skipped — at 09:35:30" in r1["detail"], r1
    assert "R1f" not in _steps(log) and env.positions["CL"] == 7.0
    assert not (env.state.get("r1") or {}).get("ticker")          # cleanup will not touch CL
    assert rc == 0, log.failed()


@pytest.mark.asyncio
async def test_a_failing_auxiliary_read_never_costs_r1_its_verdict(tmp_path):
    """The verdict comes from the spy and the retry rows; the broker-stamp read (a call only R1
    makes) failing live degrades that one time to '?' and is named — the verdict stays."""
    env = pr.FakeEnv(start=MON_1300, restore_retries=2)

    async def broken(oid):
        raise RuntimeError("APIError 500")

    env.cancelled_at = broken
    log = pr.StepLog(str(tmp_path / "r.log"), env.now)
    rc = await pr.Rehearsal(env, log, TICKERS).day_a()
    r1 = _step(log, "R1")
    assert r1["status"] == "INFO" and "retry PROVEN live" in r1["detail"], r1
    assert "broker confirmed the cancel ?" in r1["detail"], r1
    assert "auxiliary reads that failed (verdict unaffected)" in r1["detail"], r1
    assert _cl_left(env) == (0.0, [], []) and rc == 0
