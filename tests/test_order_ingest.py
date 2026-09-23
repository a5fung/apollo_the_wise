"""#184(b) — broker-order INGEST (ADR 0008 inc-2b). Pins the safety-critical behavior of the DARK
mutation module: COID parse/validate truth table, the FAIL-CLOSED toggle, R1 repair-when-live vs
dry-run-writes-nothing vs no-overwrite-a-live-pointer, the per-cycle cap, foreign-COID-never, and
the cleanup-race guards (CLSK 2026-07-14: a row mid-10:00-ORB-cleanup must never be read as an
untracked order/position — while a genuinely untracked one must STILL propose).
"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence.broker import order_ingest as oi


# ─────────────────────────── pure: parse + class-enable ───────────────────────────
def test_parse_coid_good_and_strategy_with_underscore():
    p = oi.parse_coid("apollo_live_9m_day2_AAPL_1715450123456")
    assert p["mode"] == "live" and p["ticker"] == "AAPL" and p["strategy"] == "9m_day2"
    assert p["ms"] == 1715450123456 and isinstance(p["alert_date"], date)


def test_parse_coid_rejects_malformed():
    for bad in ["", "notapollo_live_x_AAPL_1", "apollo_live_AAPL", "apollo_live_s_AAPL_notms",
                "apollo_bogusmode_s_AAPL_123"]:
        assert oi.parse_coid(bad) is None


def test_class_enabled_cumulative():
    assert not any(oi._class_enabled(m, "r1") for m in ("off", "dry_run"))
    assert oi._class_enabled("live_r1", "r1") and not oi._class_enabled("live_r1", "r2")
    assert oi._class_enabled("live_r2", "r1") and oi._class_enabled("live_r2", "r2")
    assert oi._class_enabled("live_r3", "r3")


# ─────────────────────────── fail-CLOSED toggle ───────────────────────────
@pytest.mark.asyncio
async def test_get_ingest_mode_fail_closed(monkeypatch):
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import db
    pool, conn = make_mock_pool()
    # #449: get_ingest_mode now reaches the DB through db.get_safeguard_state, whose OWN
    # function body resolves get_pool in db.py's module namespace — NOT order_ingest's
    # imported binding. Both are patched with the SAME mock pool so this test is valid
    # unchanged both before and after that refactor (mirrors the drawdown_breaker /
    # kill_scale_bands precedent documented in test_safeguard_state_348.py).
    monkeypatch.setattr(oi, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    conn.fetchrow = AsyncMock(return_value={"state": "live_r1"})
    assert await oi.get_ingest_mode() == "live_r1"          # a valid state passes through (ON case)

    conn.fetchrow = AsyncMock(return_value={"state": "garbage"})
    assert await oi.get_ingest_mode() == "off"              # unrecognized → OFF (fail closed)

    conn.fetchrow = AsyncMock(side_effect=RuntimeError("db down"))
    assert await oi.get_ingest_mode() == "off"              # DB error → OFF (fail closed, THE LINE)


@pytest.mark.asyncio
async def test_get_ingest_mode_missing_row_falls_back_to_env(monkeypatch):
    """No row (toggle never flipped) → the BROKER_ORDER_INGEST_MODE env var, NOT a hardcoded
    'off' — this is DIFFERENT from the DB-error and unrecognized-DB-state cases above, which
    DO hard-fail to 'off'. An invalid env value coerces to 'off' the same way an invalid DB
    state does; no env at all also lands on 'off' (its own hardcoded env default)."""
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import db
    pool, conn = make_mock_pool()
    monkeypatch.setattr(oi, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    conn.fetchrow = AsyncMock(return_value=None)

    monkeypatch.setenv("BROKER_ORDER_INGEST_MODE", "dry_run")
    assert await oi.get_ingest_mode() == "dry_run"           # missing row → env (NOT 'off')

    monkeypatch.setenv("BROKER_ORDER_INGEST_MODE", "not_a_real_mode")
    assert await oi.get_ingest_mode() == "off"               # invalid env also coerces to off

    monkeypatch.delenv("BROKER_ORDER_INGEST_MODE", raising=False)
    assert await oi.get_ingest_mode() == "off"               # no env either → off (its hardcoded default)


# ─────────────────────────── validate_coid truth table ───────────────────────────
@pytest.mark.asyncio
async def test_validate_coid_truth_table(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    monkeypatch.setattr(oi, "get_pool", AsyncMock(return_value=pool))
    conn.fetchval = AsyncMock(return_value=True)   # strategy exists
    good = {"mode": "live", "strategy": "magna53", "ticker": "AAPL", "ms": 1, "alert_date": date(2026, 4, 1)}

    assert (await oi.validate_coid(good, account_mode="live", symbol="AAPL"))[0] is True
    assert (await oi.validate_coid(good, account_mode="paper", symbol="AAPL"))[0] is False  # mode
    assert (await oi.validate_coid(good, account_mode="live", symbol="MSFT"))[0] is False   # ticker

    conn.fetchval = AsyncMock(return_value=False)  # strategy NOT in registry
    assert (await oi.validate_coid(good, account_mode="live", symbol="AAPL"))[0] is False


# ─────────────────────────── R1 behavior ───────────────────────────
def _stop(oid, ticker, coid, side="sell", otype="stop"):
    return {"id": oid, "symbol": ticker, "side": side, "type": otype,
            "client_order_id": coid, "stop_price": 95.0, "qty": 100, "status": "new"}


def _dbrow(ticker, stop_order_id, trade_id=1):
    return {"id": trade_id, "ticker": ticker, "stop_order_id": stop_order_id}


def _wire_conn(conn):
    """Route conn.fetchval by SQL: strategy exists (mi_strategies) / not-already-seen (mi_audit_log).
    R1's live write goes through the mocked order_manager.set_stop_order_id, not conn.
    conn.fetch defaults to [] (no claimed order ids, no recently-closed tickers) — the race-guard
    tests override it via _wire_fetch."""
    async def _fv(sql, *a):
        return True if "mi_strategies" in sql else None
    conn.fetchval = AsyncMock(side_effect=_fv)
    conn.execute = AsyncMock(return_value="OK")
    conn.fetch = AsyncMock(return_value=[])


def _wire_fetch(conn, *, trade_refs=None, live_order_ids=None, recently_closed=None):
    """Route conn.fetch by SQL shape onto the three race-guard reads:
    - coverage_drift._fetch_all_known_order_ids (any-status entry/stop pointers) ← trade_refs
      [(entry_id, stop_id), ...] — the REAL shared helper runs against this mock, so the test
      exercises the exact set D2 detection uses;
    - mi_live_orders.alpaca_order_id ← live_order_ids;
    - recently-closed tickers (closed_at window) ← recently_closed."""
    async def _f(sql, *a):
        if "mi_live_orders" in sql:
            return [{"alpaca_order_id": i} for i in (live_order_ids or [])]
        if "closed_at" in sql:
            return [{"ticker": t} for t in (recently_closed or [])]
        if "entry_order_id" in sql:
            return [{"entry_order_id": e, "stop_order_id": s} for e, s in (trade_refs or [])]
        return []
    conn.fetch = AsyncMock(side_effect=_f)


async def _run(conn, mode, db_rows, open_orders, positions=None, ssid_applied=True):
    from tests.conftest import make_mock_pool
    from agents.market_intelligence.broker import order_manager
    pool, _ = make_mock_pool()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    with patch.object(oi, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(oi, "log_audit_event", AsyncMock()) as audit, \
         patch.object(oi, "send_telegram_message", AsyncMock()) as tg, \
         patch.object(order_manager, "set_stop_order_id",
                      AsyncMock(return_value=ssid_applied)) as ssid:
        n = await oi.run_ingest("live", positions or [], open_orders, db_rows, mode=mode)
    return n, conn.fetchval, audit, tg, ssid


@pytest.mark.asyncio
async def test_r1_repairs_null_pointer_when_live():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    orders = [_stop("STOP123", "AAPL", "apollo_live_magna53_AAPL_1715450123456")]
    n, fv, audit, tg, ssid = await _run(conn, "live_r1", [_dbrow("AAPL", None)], orders)
    assert n == 1
    # the repair routed through the AUTHORIZED writer with the no-overwrite guard (expected_prior)
    ssid.assert_awaited_once()
    assert ssid.await_args.kwargs["expected_prior"] is None       # the prior NULL pointer
    assert ssid.await_args.kwargs["reason"] == "ingest_r1_repair"
    # a RECONSTRUCTED audit was emitted (live mutation), not just a proposal
    assert any(c.args[0] == oi.INGEST_RECONSTRUCTED for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_r1_dry_run_proposes_but_never_mutates():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    orders = [_stop("STOP123", "AAPL", "apollo_live_magna53_AAPL_1715450123456")]
    n, fv, audit, tg, ssid = await _run(conn, "dry_run", [_dbrow("AAPL", None)], orders)
    assert n == 1
    ssid.assert_not_awaited()   # ZERO mutation in dry-run — the authorized writer is never called
    assert any(c.args[0] == oi.INGEST_PROPOSED for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_r1_never_overwrites_a_live_pointer():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    # DB pointer is STOP123, which IS in the live book → not a candidate, no touch.
    orders = [_stop("STOP123", "AAPL", "apollo_live_magna53_AAPL_1715450123456")]
    n, fv, audit, tg, ssid = await _run(conn, "live_r1", [_dbrow("AAPL", "STOP123")], orders)
    assert n == 0
    ssid.assert_not_awaited()   # live pointer → not a candidate → authorized writer never called


@pytest.mark.asyncio
async def test_foreign_coid_never_ingested():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    # a manual/foreign SELL stop (no apollo_live_ prefix) — must never be proposed or repaired.
    orders = [_stop("MANUAL1", "AAPL", "someone_elses_order")]
    n, fv, audit, tg, ssid = await _run(conn, "live_r1", [_dbrow("AAPL", None)], orders)
    assert n == 0
    ssid.assert_not_awaited()
    assert not any(c.args[0] in (oi.INGEST_PROPOSED, oi.INGEST_RECONSTRUCTED)
                   for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_per_cycle_cap_bounds_r1():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    orders = [_stop(f"S{i}", f"T{i}", f"apollo_live_magna53_T{i}_171545012345{i}") for i in range(3)]
    rows = [_dbrow(f"T{i}", None, trade_id=i) for i in range(3)]
    n, fv, audit, tg, ssid = await _run(conn, "live_r1", rows, orders)
    assert n == oi.PER_CYCLE_CAP   # 3 candidates, capped at 2


# ─────────────────────────── R2 / R3i — dry-run proposals only ───────────────────────────
@pytest.mark.asyncio
async def test_r2_proposes_untracked_buy_without_mutation():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    # a broker apollo BUY order for a ticker with NO db row → R2 dry-run proposal (never a live write)
    buy = {"id": "BUY9", "symbol": "MSFT", "side": "buy", "type": "stop_limit",
           "client_order_id": "apollo_live_magna53_MSFT_1715450123456", "stop_price": 200.0, "qty": 50}
    n, fv, audit, tg, ssid = await _run(conn, "live_r1", [], [buy])  # R1 nothing → R2 proposes
    assert n == 1
    ssid.assert_not_awaited()   # R2 has NO live write path — proposal only
    props = [c for c in audit.await_args_list if c.args[0] == oi.INGEST_PROPOSED]
    assert props and '"class": "r2"' in props[0].args[2]


@pytest.mark.asyncio
async def test_r3i_proposes_untracked_position_dry_run():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    pos = {"symbol": "NVDA", "qty": 10, "avg_entry_price": 500.0}
    n, fv, audit, tg, ssid = await _run(conn, "live_r1", [], [], positions=[pos])
    assert n == 1
    ssid.assert_not_awaited()   # R3i has NO live write path (zero-observation case) — proposal only
    assert any(c.args[0] == oi.INGEST_PROPOSED and '"class": "r3i"' in c.args[2]
               for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_r2_foreign_coid_never_proposed():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    buy = {"id": "BUYX", "symbol": "MSFT", "side": "buy", "type": "stop_limit",
           "client_order_id": "someone_elses_buy", "stop_price": 200.0, "qty": 50}
    n, fv, audit, tg, ssid = await _run(conn, "live_r1", [], [buy])
    assert n == 0
    assert not any(c.args[0] == oi.INGEST_PROPOSED for c in audit.await_args_list)


# ─────────────── cleanup-race guards (the CLSK 2026-07-14 false positive) ───────────────
def _buy(oid="96c48f58", ticker="CLSK", coid="apollo_live_magna53_CLSK_1784035864776"):
    return {"id": oid, "symbol": ticker, "side": "buy", "type": "stop_limit",
            "client_order_id": coid, "stop_price": 15.1, "qty": 44}


@pytest.mark.asyncio
async def test_r2_clsk_cleanup_race_not_proposed():
    """The CLSK 2026-07-14 10:00:00 scenario, verbatim from prod: the 10:00 ORB cleanup flipped
    trade 257 order_placed→cancelled at .324s while the broker order (same id, existed since
    9:31) sat pending_cancel — so db_rows (OPEN only) no longer lists CLSK, but the cancelled
    row STILL references the order id. Must NOT propose reconstruction."""
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    _wire_fetch(conn, trade_refs=[("96c48f58", "c5f23062")])  # the cancelled row's pointers
    n, fv, audit, tg, ssid = await _run(conn, "dry_run", [], [_buy()])
    assert n == 0
    assert not any(c.args[0] == oi.INGEST_PROPOSED for c in audit.await_args_list)
    tg.assert_not_awaited()


@pytest.mark.asyncio
async def test_r2_nulled_trade_pointer_still_claimed_via_live_orders():
    """The cleanup's prior-fills branch (Day-1 re-entry) NULLs mi_live_trades.entry_order_id —
    the any-status trades set loses the id, but the mi_live_orders row written at submission
    survives and must still claim it. Must NOT propose."""
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    _wire_fetch(conn, trade_refs=[], live_order_ids=["96c48f58"])
    n, fv, audit, tg, ssid = await _run(conn, "dry_run", [], [_buy()])
    assert n == 0
    assert not any(c.args[0] == oi.INGEST_PROPOSED for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_r2_genuinely_untracked_still_proposed_alongside_claims():
    """The guard must not blind the detector: with OTHER orders claimed, an order referenced
    NOWHERE (the a41e7c6a submit-crash class writes neither table) still proposes."""
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    _wire_fetch(conn, trade_refs=[("OTHER_ENTRY", "OTHER_STOP")], live_order_ids=["OTHER_ORD"])
    n, fv, audit, tg, ssid = await _run(conn, "dry_run", [], [_buy()])
    assert n == 1
    props = [c for c in audit.await_args_list if c.args[0] == oi.INGEST_PROPOSED]
    assert props and '"class": "r2"' in props[0].args[2]
    ssid.assert_not_awaited()  # still proposal-only — no mutation path


@pytest.mark.asyncio
async def test_r3i_mid_close_race_not_proposed():
    """R3i shares the race class (no order id to match, so the claim is the recently-closed
    ticker): a broker position whose row closed inside the claim window is a close transition
    racing the scan, NOT an untracked position. Must NOT propose."""
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    _wire_fetch(conn, recently_closed=["NVDA"])
    pos = {"symbol": "NVDA", "qty": 10, "avg_entry_price": 500.0}
    n, fv, audit, tg, ssid = await _run(conn, "dry_run", [], [], positions=[pos])
    assert n == 0
    assert not any(c.args[0] == oi.INGEST_PROPOSED for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_r3i_unrelated_recent_close_does_not_blind():
    """A recent close on a DIFFERENT ticker claims nothing — the untracked NVDA position still
    proposes (the claim is per-ticker, and it expires; delayed, never blinded)."""
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    _wire_fetch(conn, recently_closed=["OTHR"])
    pos = {"symbol": "NVDA", "qty": 10, "avg_entry_price": 500.0}
    n, fv, audit, tg, ssid = await _run(conn, "dry_run", [], [], positions=[pos])
    assert n == 1
    assert any(c.args[0] == oi.INGEST_PROPOSED and '"class": "r3i"' in c.args[2]
               for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_r1_behavior_unchanged_by_race_guards():
    """R1 is LIVE — its matcher keys on rows PRESENT in db_rows (a mid-cleanup row simply drops
    out and R1 takes no action), so the race guards must not touch it: a null-pointer repair
    still routes through the authorized writer even when the claim sets are populated."""
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    _wire_fetch(conn, trade_refs=[("SOME_ENTRY", "STOP123")], live_order_ids=["STOP123"],
                recently_closed=["AAPL"])
    orders = [_stop("STOP123", "AAPL", "apollo_live_magna53_AAPL_1715450123456")]
    n, fv, audit, tg, ssid = await _run(conn, "live_r1", [_dbrow("AAPL", None)], orders)
    assert n == 1
    ssid.assert_awaited_once()
    assert any(c.args[0] == oi.INGEST_RECONSTRUCTED for c in audit.await_args_list)
