"""ADR 0029 D1 — `morning_stop_refresh` must skip SAME-DAY (entry-day) trades.

Signed 2026-07-12 ("rides the NEXT execution deploy"), then never landed; found
unshipped 2026-07-24 and again by the 2026-07-26 LIKELY-BUILT sweep. Shipped
2026-07-26.

THE BUG: the docstring always claimed "Day 2+", but the query selected EVERY
filled position — including one that filled this morning, whose stop is an OTO
child placed atomically with the entry. The 9:35 refresh then raced the broker's
own child order and produced the WULF `insufficient qty available` self-conflict.

WHAT THESE TESTS CAN AND CANNOT CHECK, stated honestly: the exclusion lives in
SQL, so with a mocked connection the database does not actually filter anything —
a test that fed rows through a fake `conn.fetch` and asserted on the output would
be testing the fake, not the code. So these assert on the QUERY the function
issues and the parameter it binds. That is structural, but it is exactly where
the logic lives, and each assertion was checked to fail against the pre-fix code.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import live_tracker as lt
from tests.conftest import make_mock_pool


async def _capture_query(monkeypatch):
    """Run morning_stop_refresh with an empty result set; return (sql, params)."""
    pool, conn = make_mock_pool()
    captured: dict = {}

    async def fake_fetch(sql, *params):
        captured["sql"] = sql
        captured["params"] = params
        return []          # no trades -> the loop body never runs

    conn.fetch = AsyncMock(side_effect=fake_fetch)
    with patch.object(lt, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(lt, "et_today", lambda: date(2026, 7, 27)):
        await lt.morning_stop_refresh()
    return captured["sql"], captured["params"]


@pytest.mark.asyncio
async def test_query_excludes_the_current_et_day(monkeypatch):
    """The D1 contract: entry-day trades are owned by their OTO child."""
    sql, params = await _capture_query(monkeypatch)
    assert "alert_date <> $1" in sql, (
        "morning_stop_refresh no longer excludes same-day trades — ADR 0029 D1 "
        "regressed, and the 9:35 vs OTO-child collision (WULF insufficient-qty) "
        "is live again."
    )
    assert params and params[0] == date(2026, 7, 27), (
        "the same-day exclusion is not bound to the ET trading day"
    )


@pytest.mark.asyncio
async def test_day2_selection_is_otherwise_unchanged(monkeypatch):
    """D1 NARROWS this job — it must not also change which Day 2+ rows qualify."""
    sql, _ = await _capture_query(monkeypatch)
    assert "status = 'filled'" in sql
    assert "remaining_shares > 0" in sql


@pytest.mark.asyncio
async def test_uses_et_day_not_a_naive_or_utc_date(monkeypatch):
    """Container runs UTC; after 8pm ET a naive date is already tomorrow, which
    would exclude the WRONG day's cohort. Pin that et_today() is the source."""
    calls = []

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])

    def spy_et_today():
        calls.append(1)
        return date(2026, 7, 27)

    with patch.object(lt, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(lt, "et_today", spy_et_today):
        await lt.morning_stop_refresh()
    assert calls, "morning_stop_refresh did not resolve the day via et_today()"


def test_sync_positions_still_reaches_same_day_naked_trades():
    """ADR 0029 D1 pin 3 — the exclusion must not create a permanent blind spot.

    D1 is only safe because a genuinely-naked same-day trade is still healed
    elsewhere: 3-source capture at fill, sync_positions Path-C naked remediation,
    and #184b R1 ingest repointing. If the remediation stack ever grew its own
    same-day exclusion, D1 would turn a race into an unprotected position — so
    pin that order_manager's sync/naked path carries no alert_date filter.
    """
    src = (
        __import__("pathlib").Path(lt.__file__).parent / "order_manager.py"
    ).read_text()
    start = src.index("async def _sync_positions_for_mode")
    body = src[start:start + 20000]
    assert "alert_date" not in body, (
        "sync_positions grew an alert_date filter — combined with ADR 0029 D1's "
        "same-day refresh exclusion, a naked entry-day position could go "
        "unremediated. Re-check D1's safety argument before allowing this."
    )
