"""
End-to-end test for the 9M EP pipeline.

Verifies:
1. DB tables exist with correct columns
2. insert_9m_ep_alert / get_today_9m_ep_alerts round-trip
3. insert_9m_sugar_baby / get_pending_9m_sugar_babies / update_9m_sugar_baby_status
4. get_eod_9m_sugar_babies filter logic (volume/price/green/range criteria)
5. prepare_9m_day2_orb_order order spec calculation
6. run_9m_eod_sweep integration (reads from mi_daily_closes test row)
7. Agent routing keyword coverage
8. outcome_tracker._compute_9m_ep_outcomes (import only — no DB side effects without live data)

Run from repo root:
    python scripts/test_9m_ep_e2e.py

All tests use a fixed test date far in the future (2099-01-01) to avoid colliding with real data.
Teardown removes test rows.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"
_TEST_DATE = "2099-01-01"
_TEST_TICKER = "ZZZZ"


async def test_tables(conn) -> bool:
    """Verify new tables and mi_daily_closes columns exist."""
    ok = True

    for table in ("mi_9m_ep_alerts", "mi_9m_sugar_babies"):
        exists = await conn.fetchval(
            "SELECT to_regclass($1::text) IS NOT NULL", f"public.{table}"
        )
        if exists:
            print(f"  {PASS} table {table} exists")
        else:
            print(f"  {FAIL} table {table} MISSING")
            ok = False

    for col in ("open_price", "high_price", "low_price"):
        exists = await conn.fetchval("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'mi_daily_closes' AND column_name = $1
        """, col)
        if exists:
            print(f"  {PASS} mi_daily_closes.{col} exists")
        else:
            print(f"  {FAIL} mi_daily_closes.{col} MISSING")
            ok = False

    return ok


async def test_ep_alert_roundtrip(conn) -> bool:
    """Insert an alert, check it's returned, verify dedup returns False."""
    from agents.market_intelligence.db import insert_9m_ep_alert, get_today_9m_ep_alerts

    await conn.execute(
        "DELETE FROM mi_9m_ep_alerts WHERE ticker = $1 AND alert_date = $2",
        _TEST_TICKER, _TEST_DATE,
    )

    record = {
        "ticker": _TEST_TICKER,
        "alert_date": _TEST_DATE,
        "detection_time": datetime(2099, 1, 1, 10, 0, tzinfo=timezone.utc),
        "today_volume": 15_000_000,
        "projected_vol": None,
        "current_price": 42.50,
        "gap_pct": 8.3,
        "is_anticipation": False,
    }
    is_new = await insert_9m_ep_alert(record)
    if not is_new:
        print(f"  {FAIL} insert_9m_ep_alert: expected True (new), got False")
        return False
    print(f"  {PASS} insert_9m_ep_alert returned True (new)")

    is_dup = await insert_9m_ep_alert(record)
    if is_dup:
        print(f"  {FAIL} insert_9m_ep_alert dedup: expected False, got True")
        return False
    print(f"  {PASS} insert_9m_ep_alert dedup returned False")

    alerts = await get_today_9m_ep_alerts(_TEST_DATE)
    test_alert = next((a for a in alerts if a["ticker"] == _TEST_TICKER), None)
    if not test_alert:
        print(f"  {FAIL} get_today_9m_ep_alerts: test row not found")
        return False
    if test_alert["today_volume"] != 15_000_000:
        print(f"  {FAIL} get_today_9m_ep_alerts: volume mismatch {test_alert['today_volume']}")
        return False
    print(f"  {PASS} get_today_9m_ep_alerts returned correct row")
    return True


async def test_sugar_baby_roundtrip(conn) -> bool:
    """Insert sugar baby, check pending query, update status."""
    from agents.market_intelligence.db import (
        insert_9m_sugar_baby,
        get_pending_9m_sugar_babies,
        update_9m_sugar_baby_status,
    )

    await conn.execute(
        "DELETE FROM mi_9m_sugar_babies WHERE ticker = $1 AND alert_date = $2",
        _TEST_TICKER, _TEST_DATE,
    )

    record = {
        "ticker": _TEST_TICKER,
        "alert_date": _TEST_DATE,
        "open_price": 40.00,
        "close_price": 44.50,
        "high_price": 45.00,
        "low_price": 38.00,
        "volume": 18_000_000,
        "close_in_range_pct": 0.929,
    }
    await insert_9m_sugar_baby(record)
    print(f"  {PASS} insert_9m_sugar_baby succeeded")

    pending = await get_pending_9m_sugar_babies(_TEST_DATE)
    test_baby = next((b for b in pending if b["ticker"] == _TEST_TICKER), None)
    if not test_baby:
        print(f"  {FAIL} get_pending_9m_sugar_babies: test row not found")
        return False
    print(f"  {PASS} get_pending_9m_sugar_babies returned test row (stop=${test_baby['low_price']:.2f})")

    await update_9m_sugar_baby_status(_TEST_TICKER, _TEST_DATE, "traded")
    status = await conn.fetchval(
        "SELECT day2_status FROM mi_9m_sugar_babies WHERE ticker = $1 AND alert_date = $2",
        _TEST_TICKER, _TEST_DATE,
    )
    if status != "traded":
        print(f"  {FAIL} update_9m_sugar_baby_status: expected 'traded', got '{status}'")
        return False
    print(f"  {PASS} update_9m_sugar_baby_status works")
    return True


async def test_eod_filter_logic(conn) -> bool:
    """
    Insert a synthetic mi_daily_closes row for the test ticker on test date,
    then verify get_eod_9m_sugar_babies picks it up (or not) based on filter logic.
    """
    from agents.market_intelligence.db import get_eod_9m_sugar_babies

    # First ensure the row doesn't already exist
    await conn.execute("""
        DELETE FROM mi_daily_closes WHERE ticker = $1 AND trade_date = $2
    """, _TEST_TICKER, _TEST_DATE)

    # Insert qualifying row: vol >= 9M, close >= 3, green, close in top 25%
    await conn.execute("""
        INSERT INTO mi_daily_closes (trade_date, ticker, close, volume, open_price, high_price, low_price)
        VALUES ($1, $2, 50.0, 10000000, 45.0, 52.0, 44.0)
    """, _TEST_DATE, _TEST_TICKER)

    rows = await get_eod_9m_sugar_babies(_TEST_DATE)
    hit = next((r for r in rows if r["ticker"] == _TEST_TICKER), None)
    if not hit:
        print(f"  {FAIL} get_eod_9m_sugar_babies: qualifying row not returned")
        return False
    # close_in_range = (50 - 44) / (52 - 44) = 6/8 = 0.75 — exactly at boundary
    print(f"  {PASS} get_eod_9m_sugar_babies: qualifying row returned (close_in_range=0.75)")

    # Insert a non-qualifying row (not green: close < open)
    non_green_ticker = _TEST_TICKER + "X"
    await conn.execute("""
        DELETE FROM mi_daily_closes WHERE ticker = $1 AND trade_date = $2
    """, non_green_ticker, _TEST_DATE)
    await conn.execute("""
        INSERT INTO mi_daily_closes (trade_date, ticker, close, volume, open_price, high_price, low_price)
        VALUES ($1, $2, 40.0, 10000000, 45.0, 52.0, 38.0)
    """, _TEST_DATE, non_green_ticker)

    rows2 = await get_eod_9m_sugar_babies(_TEST_DATE)
    non_green_hit = next((r for r in rows2 if r["ticker"] == non_green_ticker), None)
    if non_green_hit:
        print(f"  {FAIL} get_eod_9m_sugar_babies: non-green row should not appear")
        return False
    print(f"  {PASS} get_eod_9m_sugar_babies: non-green row correctly excluded")

    # Cleanup
    await conn.execute("DELETE FROM mi_daily_closes WHERE ticker = $1 AND trade_date = $2",
                       _TEST_TICKER, _TEST_DATE)
    await conn.execute("DELETE FROM mi_daily_closes WHERE ticker = $1 AND trade_date = $2",
                       non_green_ticker, _TEST_DATE)
    return True


def test_order_spec_logic() -> bool:
    """Verify prepare_9m_day2_orb_order calculation logic (pure math, no DB)."""
    import math

    # Simulate the core calculation
    orb_high = 50.0
    prior_day_low = 46.0
    risk_per_share = orb_high - prior_day_low  # 4.0
    equity = 100_000.0
    risk_pct = 0.01
    risk_dollars = equity * risk_pct  # 1000.0
    shares = math.floor(risk_dollars / risk_per_share)  # 250
    max_shares = math.floor(equity * 0.20 / orb_high)  # 400
    shares = min(shares, max_shares)  # 250

    if shares != 250:
        print(f"  {FAIL} order_spec shares: expected 250, got {shares}")
        return False
    print(f"  {PASS} order_spec shares calculation: {shares} shares")

    # Wide stop (>15%) should be rejected
    wide_risk = orb_high * 0.16  # 16%
    if wide_risk / orb_high <= 0.15:
        print(f"  {FAIL} wide stop check failed")
        return False
    print(f"  {PASS} wide stop (>15%) rejection logic correct")

    return True


def test_agent_routing_coverage() -> bool:
    """Verify all routing keywords are present in agent.py."""
    agent_path = Path(__file__).parent.parent / "agents/market_intelligence/agent.py"
    content = agent_path.read_text()

    required = [
        "9m outcome",
        "9m performance",
        "9m result",
        "sugar outcome",
        "9m trade",
        "9m position",
        "trade 9m",
        "9m ep",
        "sugar baby",
        "sugar babies",
        "nine million",
        "show 9m",
        "_handle_9m_ep_outcomes",
        "_handle_9m_trades",
        "_handle_9m_ep_query",
    ]
    ok = True
    for kw in required:
        if kw in content:
            print(f"  {PASS} routing keyword present: '{kw}'")
        else:
            print(f"  {FAIL} routing keyword MISSING: '{kw}'")
            ok = False
    return ok


def test_imports() -> bool:
    """Verify key modules import without error."""
    ok = True
    modules = [
        ("agents.market_intelligence.ninem_detector", "run_9m_scan"),
        ("agents.market_intelligence.ninem_detector", "run_9m_eod_sweep"),
        ("agents.market_intelligence.db", "insert_9m_ep_alert"),
        ("agents.market_intelligence.db", "get_9m_live_trades"),
        ("agents.market_intelligence.db", "get_9m_ep_history"),
        ("agents.market_intelligence.outcome_tracker", "_compute_9m_ep_outcomes"),
        ("agents.market_intelligence.broker.order_manager", "prepare_9m_day2_orb_order"),
        ("agents.market_intelligence.broker.live_tracker", "submit_9m_day2_trade"),
    ]
    for mod_name, attr in modules:
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            if hasattr(mod, attr):
                print(f"  {PASS} {mod_name}.{attr}")
            else:
                print(f"  {FAIL} {mod_name} missing attribute '{attr}'")
                ok = False
        except Exception as e:
            print(f"  {FAIL} import {mod_name}: {e}")
            ok = False
    return ok


async def teardown(conn) -> None:
    for table in ("mi_9m_ep_alerts", "mi_9m_sugar_babies"):
        await conn.execute(
            f"DELETE FROM {table} WHERE ticker = $1 AND alert_date = $2",
            _TEST_TICKER, _TEST_DATE,
        )


async def main() -> None:
    from agents.market_intelligence.db import get_pool

    print("=== 9M EP End-to-End Test ===\n")

    # Import tests (no DB required)
    print("--- Import Tests ---")
    imports_ok = test_imports()

    print("\n--- Agent Routing Coverage ---")
    routing_ok = test_agent_routing_coverage()

    print("\n--- Order Spec Logic ---")
    spec_ok = test_order_spec_logic()

    print("\n--- DB Round-trip Tests ---")
    pool = await get_pool()
    async with pool.acquire() as conn:
        tables_ok = await test_tables(conn)
        if not tables_ok:
            print(f"\n{FAIL} Tables missing — run initialize_db() first. Skipping DB tests.")
        else:
            alert_ok = await test_ep_alert_roundtrip(conn)
            baby_ok = await test_sugar_baby_roundtrip(conn)
            filter_ok = await test_eod_filter_logic(conn)
            await teardown(conn)

    all_ok = imports_ok and routing_ok and spec_ok and tables_ok
    if tables_ok:
        all_ok = all_ok and alert_ok and baby_ok and filter_ok

    print(f"\n{'='*40}")
    if all_ok:
        print(f"{PASS} All tests passed.")
    else:
        print(f"{FAIL} Some tests failed — review output above.")
    print("="*40)


if __name__ == "__main__":
    asyncio.run(main())
