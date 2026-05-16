"""Tests for _top_event_deltas (2026-05-15) — replaces _synthesize_hypothesis.

Replaces an LLM-generated hypothesis sentence with raw audit-event-delta
facts. The function reads mi_audit_log directly; tests use a stub conn.
"""
from __future__ import annotations

import pytest

from agents.market_intelligence import system_audit


class _StubConn:
    """Minimal asyncpg-compatible stub: stores two query-keyed result sets."""
    def __init__(self, today_rows: list[dict], history_rows: list[dict]):
        self._today = today_rows
        self._history = history_rows

    async def fetch(self, sql: str, *args):
        # Discriminate by SQL content rather than full match — robust to
        # whitespace / formatting changes in the production query.
        if "INTERVAL '24 hours'" in sql and "INTERVAL" in sql and "AT TIME ZONE" not in sql:
            return self._today
        return self._history


@pytest.mark.asyncio
async def test_today_cooldowns_dominate_deltas():
    """Today's biotech case: cooldowns spike to 13, splits up modestly.
    Top delta should be cooldowns, not splits (the LLM's wrong attribution)."""
    today_rows = [
        {"event_type": "ticker_revalidated_out", "n": 13},
        {"event_type": "validation_cooldown_triggered", "n": 13},
        {"event_type": "split_detected", "n": 6},
        {"event_type": "global_ticker_ban_active", "n": 1},  # always-1 event
    ]
    history_rows = [
        # ticker_revalidated_out: ~0.5/day baseline
        {"event_type": "ticker_revalidated_out", "day": "2026-05-01", "n": 1},
        # validation_cooldown_triggered: ~0.5/day baseline
        {"event_type": "validation_cooldown_triggered", "day": "2026-05-01", "n": 1},
        # split_detected: 3/day baseline (active period)
        *[{"event_type": "split_detected", "day": f"2026-05-{d:02d}", "n": 3}
          for d in range(1, 14)],
        # global_ticker_ban_active: 1/day every day
        *[{"event_type": "global_ticker_ban_active", "day": f"2026-05-{d:02d}", "n": 1}
          for d in range(1, 14)],
    ]
    conn = _StubConn(today_rows, history_rows)
    deltas = await system_audit._top_event_deltas(conn, top_n=3, window_days=14)

    assert len(deltas) == 3
    # Top delta is one of the cooldown events (largest ratio vs baseline)
    top_events = {d["event_type"] for d in deltas[:2]}
    assert "ticker_revalidated_out" in top_events
    assert "validation_cooldown_triggered" in top_events
    # split_detected is 3rd or absent (ratio 2× vs cooldowns' 26×)
    # global_ticker_ban_active is constant baseline → ratio = 1.0, should be lowest
    assert deltas[0]["ratio"] > deltas[-1]["ratio"]


@pytest.mark.asyncio
async def test_zero_baseline_event_marked_new():
    """Event types with no history within the window should be flagged is_new=True."""
    today_rows = [{"event_type": "brand_new_event", "n": 5}]
    history_rows = []  # no history
    conn = _StubConn(today_rows, history_rows)
    deltas = await system_audit._top_event_deltas(conn, top_n=3, window_days=14)
    assert len(deltas) == 1
    assert deltas[0]["is_new"] is True
    assert deltas[0]["baseline_median"] == 0


@pytest.mark.asyncio
async def test_floor_prevents_divide_by_zero():
    """Zero-baseline ratio must use max(median, 0.5) floor, not divide by zero."""
    today_rows = [{"event_type": "rare_event", "n": 3}]
    history_rows = []
    conn = _StubConn(today_rows, history_rows)
    deltas = await system_audit._top_event_deltas(conn, top_n=3, window_days=14)
    assert len(deltas) == 1
    # 3 / max(0, 0.5) = 6.0 (not inf, not zero-div)
    assert deltas[0]["ratio"] == 6.0


@pytest.mark.asyncio
async def test_top_n_limit():
    """Returns at most top_n results, sorted by ratio descending."""
    today_rows = [
        {"event_type": f"event_{i}", "n": 10 - i}  # 10, 9, 8, ...
        for i in range(8)
    ]
    history_rows = [
        # All have constant baseline = 1
        {"event_type": f"event_{i}", "day": f"2026-05-{d:02d}", "n": 1}
        for i in range(8) for d in range(1, 14)
    ]
    conn = _StubConn(today_rows, history_rows)
    deltas = await system_audit._top_event_deltas(conn, top_n=3, window_days=14)
    assert len(deltas) == 3
    # Ratios should be sorted desc
    assert deltas[0]["ratio"] >= deltas[1]["ratio"] >= deltas[2]["ratio"]
    # Top should be event_0 (today=10, baseline=1 → ratio 10)
    assert deltas[0]["event_type"] == "event_0"


@pytest.mark.asyncio
async def test_empty_today_returns_empty():
    """No audit events today → no deltas to report."""
    conn = _StubConn(today_rows=[], history_rows=[])
    deltas = await system_audit._top_event_deltas(conn, top_n=3, window_days=14)
    assert deltas == []
