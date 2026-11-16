"""Methodology reads of trade P&L exclude bug-attributed trades (operator ruling 2026-11-15).

`mi_live_trades.pnl_attribution` non-NULL = the P&L on that row came from a defect, not from the setup (the flawed
pre-fix breakout_v1 paper trades were ruled out of strategy measurement on 11-15). Every read that MEASURES a strategy
filters `pnl_attribution IS NULL`; account-accounting reads and row listings deliberately do not.

The population is DERIVED: every SQL string in the measured modules that selects P&L off `mi_live_trades` either
carries the filter or is named below with its reason. A new reader fails here until it is classified."""
import ast
import glob
import re
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db as db_module
from agents.market_intelligence import system_review
from agents.market_intelligence.strategies import adapters as strategy_adapters
from agents.market_intelligence.strategies import promotion
from tests.conftest import make_mock_pool

REPO = Path(__file__).resolve().parents[1]
FILTER = "pnl_attribution IS NULL"

# function -> why its read of mi_live_trades P&L is NOT a methodology read
NOT_METHODOLOGY = {
    "get_closed_pnl_by_account_mode": "account accounting, by design (its docstring)",
    "get_live_trading_summary": "all-time account summary (realized dollars + counts); mixed, no caller - left as is",
    "get_ticker_setup_timeline": "a per-ticker row listing for display, not a measurement",
    "get_9m_live_trades": "a row listing for a setup that is gone",
    "get_open_position_count": "open-position count (COUNT(*)), no P&L",
    "get_open_live_trades": "open rows for the exit loop, no measurement",
    "get_ep_scanned_day": "a day's scan read-back, no P&L measurement",
    "<module>:_LOWCAP_PAPER_LANE_DAY_ORDERED_SQL": "a count of orders placed, no P&L",
    # the fill recorders STAMP every fill and copy `pnl_attribution` onto the recorded row; the cohort reads of
    # those rows filter it (db.py DDL comments) — dropping the fill here would lose the record
    "<module>:_COUNTERFACTUAL_FILLS_SQL": "recorder input: carries pnl_attribution per row, filtered at the cohort read",
    "<module>:_BOOK_ARM_FILLS_SQL": "recorder input: carries pnl_attribution per row, filtered at the cohort read",
}


def _pnl_readers():
    """[(file, function, sql)] for every SELECT off mi_live_trades that touches P&L (or counts rows) in the modules
    that measure strategies."""
    files = ["agents/market_intelligence/db.py", "agents/market_intelligence/system_review.py",
             "agents/market_intelligence/kill_scale_bands.py"]
    files += sorted(glob.glob(str(REPO / "agents/market_intelligence/ladder_*.py")))
    files += sorted(glob.glob(str(REPO / "agents/market_intelligence/strategies/*.py")))
    out = []
    for f in files:
        path = Path(f) if Path(f).is_absolute() else REPO / f
        tree = ast.parse(path.read_text())
        funcs = [(n.lineno, n.end_lineno, n.name) for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        names = {n.value.lineno: n.targets[0].id for n in ast.walk(tree)
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
        inside_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in inside_fstring:
                sql = n.value
            elif isinstance(n, ast.JoinedStr):
                sql = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)
            else:
                continue
            if not (re.search(r"\b(FROM|JOIN)\s+mi_live_trades\b", sql, re.I) and re.search(r"\bSELECT\b", sql, re.I)):
                continue
            if not re.search(r"pnl|realized_r|exit_price|\*", sql, re.I):
                continue
            inside = [x for x in funcs if x[0] <= n.lineno <= x[1]]
            fn = max(inside)[2] if inside else f"<module>:{names.get(n.lineno, '?')}"
            out.append((path.name, fn, sql))
    return out


def test_every_methodology_read_of_trade_pnl_filters_bug_attributed_trades():
    readers = _pnl_readers()
    found = {fn for _f, fn, _s in readers}
    # the walk sees the population (named members, not a count floor)
    assert {"_adapter_live_trades", "_eval_paired_r", "get_shadow_outcomes_window", "_aggregate_shadow_orb_outcomes",
            "assemble_band_inputs", "get_setup_performance_review", "get_closed_pnl_by_account_mode"} <= found
    missing = sorted({f"{f}:{fn}" for f, fn, sql in readers if FILTER not in sql and fn not in NOT_METHODOLOGY})
    assert not missing, f"trade-P&L readers without `{FILTER}` and not classified as non-methodology: {missing}"
    stale = sorted(set(NOT_METHODOLOGY) - found)
    assert not stale, f"NOT_METHODOLOGY names a reader that no longer exists: {stale}"


def test_account_accounting_keeps_every_closed_trade():
    sql = [s for _f, fn, s in _pnl_readers() if fn == "get_closed_pnl_by_account_mode"]
    assert sql and all("pnl_attribution" not in s for s in sql)


@pytest.mark.asyncio
async def test_the_promotion_ladder_adapter_excludes_bug_attributed_trades(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(strategy_adapters, "get_pool", AsyncMock(return_value=pool))
    await strategy_adapters._adapter_live_trades(90, signal_type="breakout_v1")
    assert FILTER in conn.fetch.await_args[0][0]


@pytest.mark.asyncio
async def test_the_paired_r_gate_excludes_bug_attributed_live_trades(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=0)
    monkeypatch.setattr(promotion, "get_pool", AsyncMock(return_value=pool))
    row = strategy_adapters.OutcomeRow(strategy_id="shadow_orb_5m", ticker="AAA", alert_date=date(2026, 11, 2),
                                       status="closed", r_multiple=1.0, pnl=10.0, hold_days=1, closed_at=None)
    await promotion._eval_paired_r("shadow_orb_5m", [row], {})
    assert FILTER in conn.fetch.await_args[0][0]
    await promotion._eval_paired_r("shadow_orb_5m", [], {})                 # the zero-paired diagnostic counts too
    assert FILTER in conn.fetchval.await_args[0][0] and FILTER in conn.fetch.await_args[0][0]


@pytest.mark.asyncio
async def test_the_shadow_vs_live_readers_drop_the_live_side_not_the_shadow_row(monkeypatch):
    """Both are joins FROM the shadow table. The LEFT JOIN keeps the shadow row and blanks a bug-attributed live
    side (filter in ON); the inner-join pairing drops the pair."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value="mi_orb_shadow_trades")
    conn.fetchrow = AsyncMock(return_value={"entered": 0, "no_entry": 0, "gate_blocked": 0})
    monkeypatch.setattr(db_module, "get_pool", AsyncMock(return_value=pool))
    await db_module.get_shadow_outcomes_window(window_days=30, bar_size_minutes=5)
    sql = conn.fetch.await_args[0][0]
    on_clause = sql[sql.index("LEFT JOIN mi_live_trades"):sql.index("WHERE")]
    assert "live.pnl_attribution IS NULL" in on_clause
    await system_review._aggregate_shadow_orb_outcomes(window_days=90)
    assert "live.pnl_attribution IS NULL" in conn.fetch.await_args[0][0]
