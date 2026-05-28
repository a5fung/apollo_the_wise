"""Regression tests for the naked-position alert taxonomy (#140, 2026-05-28).

Pre-fix: any DB row with status='filled' AND stop_order_id IS NULL fired
🚨 INVARIANT BREACH, identically severe whether the broker had a stop or
not. Post-IBM-cascade 2026-05-27: after manual SQL re-sync mismatched
DB↔broker state, this alerted operator with full 🚨 severity even though
broker had stops in place. The 5/27 incident triggered #140.

Post-fix: classify_naked_positions queries broker per-ticker for open
stop orders. Real-naked → 🚨. DB-drift → ⚠️. Formatter renders two
distinct sections (or omits one when empty).
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_real_naked_when_broker_has_no_stop():
    """Broker returns empty open_orders → row goes to real_naked bucket."""
    from agents.market_intelligence.audit_invariants import classify_naked_positions
    from agents.market_intelligence.broker import alpaca_client

    body = {
        "offending_rows": [
            {"ticker": "AAPL", "alert_date": "2026-05-28", "stop_order_id": None,
             "status": "filled", "filled_at": None},
        ]
    }
    with patch.object(alpaca_client, "get_open_orders", new=AsyncMock(return_value=[])):
        result = await classify_naked_positions(body)

    assert len(result["real_naked"]) == 1
    assert result["real_naked"][0]["ticker"] == "AAPL"
    assert result["db_drift"] == []


@pytest.mark.asyncio
async def test_db_drift_when_broker_has_stop():
    """Broker returns sell-side stop order → row goes to db_drift bucket."""
    from agents.market_intelligence.audit_invariants import classify_naked_positions
    from agents.market_intelligence.broker import alpaca_client

    body = {
        "offending_rows": [
            {"ticker": "IBM", "alert_date": "2026-05-28", "stop_order_id": None,
             "status": "filled", "filled_at": None},
        ]
    }
    broker_orders = [{
        "id": "stop-123",
        "symbol": "IBM",
        "side": "sell",
        "type": "stop",
        "stop_price": 250.0,
        "status": "accepted",
    }]
    with patch.object(alpaca_client, "get_open_orders", new=AsyncMock(return_value=broker_orders)):
        result = await classify_naked_positions(body)

    assert len(result["db_drift"]) == 1
    assert result["db_drift"][0]["ticker"] == "IBM"
    assert result["real_naked"] == []


@pytest.mark.asyncio
async def test_broker_error_fails_open_to_real_naked():
    """When broker query raises, default to REAL NAKED (safer over-alert)."""
    from agents.market_intelligence.audit_invariants import classify_naked_positions
    from agents.market_intelligence.broker import alpaca_client

    body = {
        "offending_rows": [
            {"ticker": "FAIL", "alert_date": "2026-05-28", "stop_order_id": None,
             "status": "filled", "filled_at": None},
        ]
    }

    async def _broken_get(**kwargs):
        raise RuntimeError("alpaca timeout")

    with patch.object(alpaca_client, "get_open_orders", new=_broken_get):
        result = await classify_naked_positions(body)

    assert len(result["real_naked"]) == 1
    assert result["real_naked"][0]["ticker"] == "FAIL"
    assert result["db_drift"] == []


@pytest.mark.asyncio
async def test_mixed_cohort_partitions_correctly():
    """3 tickers: 1 naked, 1 drift, 1 broker-error (defaults naked)."""
    from agents.market_intelligence.audit_invariants import classify_naked_positions
    from agents.market_intelligence.broker import alpaca_client

    body = {
        "offending_rows": [
            {"ticker": "NAKD", "alert_date": "2026-05-28", "stop_order_id": None,
             "status": "filled", "filled_at": None},
            {"ticker": "DRIFT", "alert_date": "2026-05-28", "stop_order_id": None,
             "status": "filled", "filled_at": None},
            {"ticker": "ERR", "alert_date": "2026-05-28", "stop_order_id": None,
             "status": "filled", "filled_at": None},
        ]
    }
    stop_order = [{"id": "s1", "symbol": "DRIFT", "side": "sell", "type": "stop",
                   "stop_price": 100.0, "status": "accepted"}]

    async def _get(*, ticker, account_mode=None):
        if ticker == "NAKD":
            return []
        if ticker == "DRIFT":
            return stop_order
        raise RuntimeError("alpaca timeout")

    with patch.object(alpaca_client, "get_open_orders", new=_get):
        result = await classify_naked_positions(body)

    real_naked_tickers = {r["ticker"] for r in result["real_naked"]}
    db_drift_tickers = {r["ticker"] for r in result["db_drift"]}
    assert real_naked_tickers == {"NAKD", "ERR"}
    assert db_drift_tickers == {"DRIFT"}


def test_formatter_real_naked_only():
    """Render: only NAKED section, no DB-drift section."""
    from agents.market_intelligence.system_audit import _format_naked_position_alert
    text = _format_naked_position_alert({
        "real_naked": [{"ticker": "AAPL", "alert_date": "2026-05-28", "filled_at": None}],
        "db_drift": [],
        "drill_sql": "SELECT * FROM mi_live_trades;",
    })
    assert "🚨 *NAKED POSITION" in text
    assert "AAPL" in text
    assert "DB-DRIFT" not in text
    assert "operator action" in text.lower()


def test_formatter_db_drift_only():
    """Render: only DB-DRIFT section, no NAKED section."""
    from agents.market_intelligence.system_audit import _format_naked_position_alert
    text = _format_naked_position_alert({
        "real_naked": [],
        "db_drift": [{"ticker": "IBM", "alert_date": "2026-05-28", "filled_at": None}],
        "drill_sql": "",
    })
    assert "⚠️ *DB-DRIFT" in text
    assert "IBM" in text
    assert "NAKED POSITION" not in text
    assert "sync_positions" in text  # recovery guidance


def test_formatter_renders_both_sections():
    """Mixed cohort: render both sections with divider."""
    from agents.market_intelligence.system_audit import _format_naked_position_alert
    text = _format_naked_position_alert({
        "real_naked": [{"ticker": "RISK", "alert_date": "2026-05-28", "filled_at": None}],
        "db_drift": [{"ticker": "OK", "alert_date": "2026-05-28", "filled_at": None}],
        "drill_sql": "",
    })
    assert "🚨 *NAKED POSITION" in text
    assert "⚠️ *DB-DRIFT" in text
    assert "RISK" in text
    assert "OK" in text
    # Real naked section should come first (more severe)
    assert text.index("NAKED POSITION") < text.index("DB-DRIFT")
