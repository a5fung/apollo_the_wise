"""#414 HEARTBEAT — `morning_stop_refresh`'s same-day exclusion (ADR 0029 D1)
now COUNTS what it excludes instead of staying silent about it.

THE BUG (as filed): the 09:35 morning pass excludes same-day fills in the SQL
itself (`alert_date <> $1`), so an excluded row never reaches `examined` and the
`stop_refresh_ran` audit line said nothing about what the exclusion removed.
Measured on the live book: 15 of the last 17 fills landed before 09:35, so the
exclusion had fired plenty — it just was never counted, which is why #414's
verify sat stuck since August ("cannot be manufactured").

Mirrors the #452 exposure_family fix (tests/test_exposure_family_452.py):
same idea, applied here. Telemetry only — none of these pins may ever assert
on which rows get REFRESHED changing; only on what the audit row records.
"""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import live_tracker as lt
from tests.conftest import make_mock_pool


def _wire(monkeypatch, *, same_day_rows=None, trades=None, same_day_raises=None):
    """Wire `_stop_refresh`'s pool + audit collaborators.

    `same_day_rows` / `trades` feed the two sequential conn.fetch() calls the
    include_same_day=False branch makes (same-day-excluded query, then the
    main Day-2+ query). `same_day_raises`, if given, makes the FIRST call raise
    instead of returning `same_day_rows`.
    """
    pool, conn = make_mock_pool()
    first = same_day_raises if same_day_raises is not None else (same_day_rows or [])
    conn.fetch = AsyncMock(side_effect=[first, trades or []])

    audited: list[tuple] = []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "et_today", lambda: date(2026, 9, 8))
    monkeypatch.setattr(lt, "log_audit_event", _audit)
    return audited


def _ran_row(audited):
    rows = [(s, d) for evt, s, d in audited if evt == "stop_refresh_ran"]
    assert len(rows) == 1, "stop_refresh_ran must fire exactly once per run"
    return rows[0]


@pytest.mark.asyncio
async def test_morning_pass_reports_same_day_excluded_count_and_tickers(monkeypatch):
    audited = _wire(monkeypatch, same_day_rows=[{"ticker": "AAA"}, {"ticker": "BBB"}])

    await lt.morning_stop_refresh()

    summary, detail = _ran_row(audited)
    assert "same-day excluded 2 (AAA, BBB)" in summary
    parsed = json.loads(detail)
    assert parsed["same_day_excluded"] == 2
    assert parsed["same_day_excluded_tickers"] == ["AAA", "BBB"]


@pytest.mark.asyncio
async def test_morning_pass_reports_truthful_zero_when_none_excluded(monkeypatch):
    """The other case #414 needed: no same-day fill this morning must still say
    so explicitly (a real, checked zero) — not just fall silent again."""
    audited = _wire(monkeypatch, same_day_rows=[])

    await lt.morning_stop_refresh()

    summary, detail = _ran_row(audited)
    assert "same-day excluded 0 (none)" in summary
    parsed = json.loads(detail)
    assert parsed["same_day_excluded"] == 0
    assert parsed["same_day_excluded_tickers"] == []


@pytest.mark.asyncio
async def test_post_close_pass_emits_no_exclusion_figure(monkeypatch):
    """post_close_stop_refresh (include_same_day=True) excludes nothing by
    construction — it must never write a same_day_excluded figure (a 0 there
    would misleadingly imply the concept applies to this pass)."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    audited: list[tuple] = []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "et_today", lambda: date(2026, 9, 8))
    monkeypatch.setattr(lt, "log_audit_event", _audit)

    await lt.post_close_stop_refresh()

    summary, detail = _ran_row(audited)
    assert "same-day excluded" not in summary
    parsed = json.loads(detail)
    assert "same_day_excluded" not in parsed
    assert "same_day_excluded_tickers" not in parsed


@pytest.mark.asyncio
async def test_same_day_excluded_read_failure_does_not_block_the_real_refresh(monkeypatch):
    """A telemetry-read failure must never block the actual stop-refresh — the
    money-path query (the second conn.fetch call) still runs and the function
    still returns normally; the audit row just omits the figure it could not
    get (None, distinct from an honest zero)."""
    covered_trade = {
        "id": 1, "ticker": "COVR", "remaining_shares": 4.0, "stop_price": 10.0,
        "stop_order_id": "order-1", "account_mode": "live",
    }
    audited = _wire(
        monkeypatch, same_day_raises=RuntimeError("boom"), trades=[covered_trade],
    )

    async def _get_order(order_id, account_mode=None):
        return {"status": "new"}  # still-active stop -> already-covered

    with patch.object(lt.alpaca, "get_order", AsyncMock(side_effect=_get_order)):
        count = await lt.morning_stop_refresh()

    assert count == 0
    summary, detail = _ran_row(audited)
    assert "examined 1" in summary and "already-covered 1" in summary
    assert "same-day excluded" not in summary
    parsed = json.loads(detail)
    assert "same_day_excluded" not in parsed
