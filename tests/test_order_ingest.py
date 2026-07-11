"""#184(b) — broker-order INGEST (ADR 0008 inc-2b). Pins the safety-critical behavior of the DARK
mutation module: COID parse/validate truth table, the FAIL-CLOSED toggle, R1 repair-when-live vs
dry-run-writes-nothing vs no-overwrite-a-live-pointer, the per-cycle cap, and foreign-COID-never.
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
    pool, conn = make_mock_pool()
    monkeypatch.setattr(oi, "get_pool", AsyncMock(return_value=pool))

    conn.fetchrow = AsyncMock(return_value={"state": "live_r1"})
    assert await oi.get_ingest_mode() == "live_r1"          # a valid state passes through

    conn.fetchrow = AsyncMock(return_value={"state": "garbage"})
    assert await oi.get_ingest_mode() == "off"              # unrecognized → OFF (fail closed)

    conn.fetchrow = AsyncMock(side_effect=RuntimeError("db down"))
    assert await oi.get_ingest_mode() == "off"              # DB error → OFF (fail closed, THE LINE)


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


def _wire_conn(conn, update_returns=42):
    """Route conn.fetchval by SQL: strategy exists / not-already-proposed / UPDATE succeeds."""
    async def _fv(sql, *a):
        if "mi_strategies" in sql:
            return True
        if "mi_audit_log" in sql:
            return None                      # not already proposed
        if "UPDATE mi_live_trades" in sql:
            return update_returns            # RETURNING id → repair applied
        return None
    conn.fetchval = AsyncMock(side_effect=_fv)
    conn.execute = AsyncMock(return_value="OK")


async def _run(conn, mode, db_rows, open_orders, positions=None, monkeypatch=None):
    from tests.conftest import make_mock_pool
    pool, _ = make_mock_pool()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    with patch.object(oi, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(oi, "log_audit_event", AsyncMock()) as audit, \
         patch.object(oi, "send_telegram_message", AsyncMock()) as tg:
        n = await oi.run_ingest("live", positions or [], open_orders, db_rows, mode=mode)
    return n, conn.fetchval, audit, tg


@pytest.mark.asyncio
async def test_r1_repairs_null_pointer_when_live():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    orders = [_stop("STOP123", "AAPL", "apollo_live_magna53_AAPL_1715450123456")]
    n, fv, audit, tg = await _run(conn, "live_r1", [_dbrow("AAPL", None)], orders)
    assert n == 1
    sqls = [c.args[0] for c in fv.await_args_list]
    assert any("UPDATE mi_live_trades" in s for s in sqls)   # the live repair ran
    # a RECONSTRUCTED audit was emitted (live mutation), not just a proposal
    assert any(c.args[0] == oi.INGEST_RECONSTRUCTED for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_r1_dry_run_proposes_but_never_mutates():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    orders = [_stop("STOP123", "AAPL", "apollo_live_magna53_AAPL_1715450123456")]
    n, fv, audit, tg = await _run(conn, "dry_run", [_dbrow("AAPL", None)], orders)
    assert n == 1
    sqls = [c.args[0] for c in fv.await_args_list]
    assert not any("UPDATE mi_live_trades" in s for s in sqls)   # ZERO mutation in dry-run
    assert any(c.args[0] == oi.INGEST_PROPOSED for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_r1_never_overwrites_a_live_pointer():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    # DB pointer is STOP123, which IS in the live book → not a candidate, no touch.
    orders = [_stop("STOP123", "AAPL", "apollo_live_magna53_AAPL_1715450123456")]
    n, fv, audit, tg = await _run(conn, "live_r1", [_dbrow("AAPL", "STOP123")], orders)
    assert n == 0
    assert not any("UPDATE mi_live_trades" in c.args[0] for c in fv.await_args_list)


@pytest.mark.asyncio
async def test_foreign_coid_never_ingested():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    # a manual/foreign SELL stop (no apollo_live_ prefix) — must never be proposed or repaired.
    orders = [_stop("MANUAL1", "AAPL", "someone_elses_order")]
    n, fv, audit, tg = await _run(conn, "live_r1", [_dbrow("AAPL", None)], orders)
    assert n == 0
    assert not any(c.args[0] in (oi.INGEST_PROPOSED, oi.INGEST_RECONSTRUCTED)
                   for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_per_cycle_cap_bounds_r1():
    from tests.conftest import make_mock_pool
    _, conn = make_mock_pool()
    _wire_conn(conn)
    orders = [_stop(f"S{i}", f"T{i}", f"apollo_live_magna53_T{i}_171545012345{i}") for i in range(3)]
    rows = [_dbrow(f"T{i}", None, trade_id=i) for i in range(3)]
    n, fv, audit, tg = await _run(conn, "live_r1", rows, orders)
    assert n == oi.PER_CYCLE_CAP   # 3 candidates, capped at 2
