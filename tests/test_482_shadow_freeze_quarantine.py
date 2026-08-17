"""#482 — evidence-quarantine for the #216 resumed-from-freeze rows in
`mi_orb_shadow_trades` (bar_size_minutes=5 lane).

Background: `update_shadow_trade` double-encoded jsonb writes for months
(#216); `_row_to_state` raised on the corrupted string column on a row's
NEXT update, and `update_shadow_positions`'s per-row `except` silently
swallowed it, freezing the row after its first successful step. The
2026-08-17 #216 fix's first exit pass then RESUMED every frozen row with
ONE step spanning the whole frozen gap — fabricating an outcome (a
~100-day price jump evaluated as if it were the next trading day).

Fixture values below are pinned to the ACTUAL prod-measured rows
(2026-08-17 read-only query) so the gap/staleness thresholds are validated
against real data, not a hand-picked number:
  - QCOM  alert 2026-04-30, hold_days=109, 2 recorded closes  -> gapped
  - EROC  alert 2026-08-12, hold_days=5,   2 recorded closes  -> NOT gapped
    (clean; this row's gap=1 was the largest "clean" gap observed)
  - ABCL  alert 2026-08-10, hold_days=7,   2 recorded closes  -> gapped
    (gap=3, the smallest gap observed among freeze-affected rows)
"""
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import system_review
from agents.market_intelligence.broker import shadow_orb_tracker
from agents.market_intelligence.strategies import adapters as strategy_adapters
from agents.market_intelligence import db as db_module

from tests.conftest import make_mock_pool

ET = ZoneInfo("America/New_York")


def _et_midnight_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=ET).timestamp() * 1000)


def _open_row(**overrides) -> dict:
    row = {
        "id": 1,
        "ticker": "TEST",
        "alert_date": date(2026, 8, 3),
        "bar_size_minutes": 5,
        "status": "open",
        "remaining_shares": 300.0,
        "entry_price": 100.0,
        "hard_stop": 90.0,
        "entry_shares": 300.0,
        "partial_taken": False,
        "breakeven_active": False,
        "exits": [],
        "running_closes": [],
        "hold_days": None,
        "total_pnl": None,
        "stop_price": None,
        "closed_at": None,
    }
    row.update(overrides)
    return row


# ─── detect_path_gap — classifies EXISTING rows (offline remediation) ──────


def test_detect_path_gap_flags_qcom_shaped_freeze_row():
    gapped, reason = shadow_orb_tracker.detect_path_gap(
        alert_date=date(2026, 4, 30), hold_days=109,
        running_closes=[219.09, 162.18],
    )
    assert gapped is True
    assert reason is not None
    assert "#216" in reason


def test_detect_path_gap_flags_abcl_shaped_freeze_row_at_the_margin():
    """gap=3 — the SMALLEST gap observed among prod freeze-affected rows.
    Pins the threshold from the low end, not just the dramatic QCOM case."""
    gapped, _ = shadow_orb_tracker.detect_path_gap(
        alert_date=date(2026, 8, 10), hold_days=7,
        running_closes=[10.0, 10.5],
    )
    assert gapped is True


def test_detect_path_gap_does_not_flag_eroc_shaped_clean_row():
    """gap=1 — the LARGEST gap observed among prod rows judged clean
    (a fresh row whose first-ever step landed the day the fix ran)."""
    gapped, reason = shadow_orb_tracker.detect_path_gap(
        alert_date=date(2026, 8, 12), hold_days=5,
        running_closes=[10.0, 10.2],
    )
    assert gapped is False
    assert reason is None


def test_detect_path_gap_does_not_flag_normal_single_step_close():
    """A trade that hit its hard stop on day 1 (hold_days=1, one recorded
    close) is a real, correctly-computed outcome — not a freeze artifact."""
    gapped, _ = shadow_orb_tracker.detect_path_gap(
        alert_date=date(2026, 8, 13), hold_days=1, running_closes=[9.5],
    )
    assert gapped is False


def test_detect_path_gap_ignores_rows_never_stepped():
    gapped, reason = shadow_orb_tracker.detect_path_gap(
        alert_date=date(2026, 8, 17), hold_days=None, running_closes=[],
    )
    assert gapped is False
    assert reason is None


# ─── detect_stale_for_step — the LIVE pre-step guard ────────────────────────


def test_detect_stale_for_step_flags_a_frozen_row_before_it_would_be_stepped():
    """This is the #482 item-4 case: a row last stepped 2026-05-01, about
    to be stepped again on 2026-08-17 (109 days of missed sessions).
    update_shadow_positions must catch this BEFORE calling
    apply_daily_exit_step — never silently step a stale row."""
    stale, reason = shadow_orb_tracker.detect_stale_for_step(
        alert_date=date(2026, 4, 30), hold_days=1, as_of=date(2026, 8, 17),
    )
    assert stale is True
    assert reason is not None


def test_detect_stale_for_step_allows_the_normal_next_session_step():
    # Entered Monday 8/10 -> first step Tuesday 8/11 (hold_days recorded
    # only after a successful step, so this simulates the very first one).
    stale, _ = shadow_orb_tracker.detect_stale_for_step(
        alert_date=date(2026, 8, 10), hold_days=None, as_of=date(2026, 8, 11),
    )
    assert stale is False


def test_detect_stale_for_step_allows_a_normal_weekend_gap():
    # Last step Friday, stepping again Monday — the ordinary daily cadence.
    stale, _ = shadow_orb_tracker.detect_stale_for_step(
        alert_date=date(2026, 8, 3), hold_days=4,  # last step = 8/7 (Fri)
        as_of=date(2026, 8, 10),  # Monday
    )
    assert stale is False


def test_detect_stale_for_step_tolerates_one_holiday_weekday_gap():
    # Last step Fri 8/21, stepping again Tue 8/25 — Monday 8/24 stands in
    # for a market holiday (a weekday the cron would fire on but the
    # market is closed, so no bar/step happens): 1 skipped weekday is
    # within the tolerance, must NOT be flagged stale.
    stale, _ = shadow_orb_tracker.detect_stale_for_step(
        alert_date=date(2026, 8, 17), hold_days=4,  # last step = 8/21 (Fri)
        as_of=date(2026, 8, 25),  # Tuesday, one weekday (8/24) skipped
    )
    assert stale is False


def test_detect_stale_for_step_flags_two_genuinely_missed_sessions():
    # Last step Friday, next step the FOLLOWING Tuesday with no holiday
    # excuse available in a plain Mon-Fri week — 2 sessions skipped.
    stale, _ = shadow_orb_tracker.detect_stale_for_step(
        alert_date=date(2026, 8, 3), hold_days=4,  # last step = 8/7 (Fri)
        as_of=date(2026, 8, 12),  # following Wednesday: 8/10,8/11 skipped
    )
    assert stale is True


# ─── update_shadow_positions — the live guard actually wires in ────────────


@pytest.mark.asyncio
async def test_update_shadow_positions_quarantines_stale_row_without_stepping(monkeypatch):
    """The mandatory item-4 test: a stale row must be quarantined, and
    apply_daily_exit_step (via get_index_history) must NEVER be called for
    it — no step, no fabricated outcome."""
    stale_row = _open_row(
        id=1, ticker="QCOM", alert_date=date(2026, 4, 30), hold_days=1,
        running_closes=[172.05],
    )

    get_index_history_mock = AsyncMock(return_value=[])
    update_shadow_trade_mock = AsyncMock()
    log_audit_event_mock = AsyncMock()

    monkeypatch.setattr(shadow_orb_tracker, "get_open_shadow_trades",
                         AsyncMock(return_value=[stale_row]))
    monkeypatch.setattr(shadow_orb_tracker, "get_index_history", get_index_history_mock)
    monkeypatch.setattr(shadow_orb_tracker, "update_shadow_trade", update_shadow_trade_mock)
    monkeypatch.setattr(db_module, "log_audit_event", log_audit_event_mock)

    counts = await shadow_orb_tracker.update_shadow_positions(date(2026, 8, 17))

    assert counts["quarantined_stale"] == 1
    assert counts["closed"] == 0
    assert counts["updated"] == 0
    get_index_history_mock.assert_not_awaited()  # never fetched a bar to step with

    assert update_shadow_trade_mock.await_count == 1
    call_id, call_fields = update_shadow_trade_mock.await_args[0]
    assert call_id == 1
    assert call_fields["quarantined"] is True
    assert "running_closes" not in call_fields  # never wrote a fabricated step
    assert "total_pnl" not in call_fields
    log_audit_event_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_shadow_positions_still_steps_a_normal_row(monkeypatch):
    """Regression: a genuinely fresh/current row (not stale) must still be
    stepped exactly as before — the new guard must not swallow healthy rows."""
    normal_row = _open_row(
        id=2, ticker="FRESH", alert_date=date(2026, 8, 16), hold_days=1,
        entry_price=50.0, hard_stop=45.0, remaining_shares=100.0,
        running_closes=[51.0],
    )

    # 2026-08-17 daily bar: close stays comfortably above every stop input.
    get_index_history_mock = AsyncMock(return_value=[{"l": 49.0, "c": 52.0}])
    update_shadow_trade_mock = AsyncMock()

    monkeypatch.setattr(shadow_orb_tracker, "get_open_shadow_trades",
                         AsyncMock(return_value=[normal_row]))
    monkeypatch.setattr(shadow_orb_tracker, "get_index_history", get_index_history_mock)
    monkeypatch.setattr(shadow_orb_tracker, "update_shadow_trade", update_shadow_trade_mock)

    counts = await shadow_orb_tracker.update_shadow_positions(date(2026, 8, 17))

    assert counts["quarantined_stale"] == 0
    assert counts["updated"] == 1
    get_index_history_mock.assert_awaited_once()
    assert update_shadow_trade_mock.await_count == 1
    _id, fields = update_shadow_trade_mock.await_args[0]
    assert fields["running_closes"] == [51.0, 52.0]


# ─── replay_stale_open_row — faithful re-replay for the offline pass ───────


@pytest.mark.asyncio
async def test_replay_stale_open_row_walks_every_missed_session_and_closes_honestly(monkeypatch):
    row = _open_row(
        id=3, ticker="REPLAY", alert_date=date(2026, 8, 3),
        entry_price=100.0, hard_stop=90.0, entry_shares=300.0,
        # pre-replay (corrupted, freeze-shaped) state being overwritten:
        status="open", hold_days=1, running_closes=[101.0], total_pnl=None,
    )

    day_bars = [
        (date(2026, 8, 4), {"l": 98.0, "c": 101.0}),
        (date(2026, 8, 5), {"l": 97.0, "c": 102.0}),
        (date(2026, 8, 6), {"l": 96.0, "c": 103.0}),   # hold_days=3, partial fires
        (date(2026, 8, 7), {"l": 101.0, "c": 99.0}),   # closes below breakeven stop
        (date(2026, 8, 10), {"l": 95.0, "c": 96.0}),   # must NOT be processed (closed already)
    ]
    fake_bars = [
        {"t": _et_midnight_ms(d), "l": b["l"], "c": b["c"]} for d, b in day_bars
    ]
    get_index_history_mock = AsyncMock(return_value=fake_bars)
    monkeypatch.setattr(shadow_orb_tracker, "get_index_history", get_index_history_mock)

    fields = await shadow_orb_tracker.replay_stale_open_row(row, date(2026, 8, 17))

    assert "_replay_unavailable" not in fields
    assert fields["status"] == "closed"
    assert fields["hold_days"] == 4  # 2026-08-07 - 2026-08-03
    assert fields["remaining_shares"] == 0
    assert fields["partial_taken"] is True
    # partial: (103-100)*100 = 300; close: (99-100)*200 = -200 -> net 100
    assert fields["total_pnl"] == pytest.approx(100.0)
    assert len(fields["exits"]) == 2
    assert fields["exits"][0]["reason"] == "partial_profit"
    assert fields["exits"][1]["reason"] == "sma_trail_stop"
    # replay stopped at the close — the 8/10 bar must never have been consumed.
    assert len(fields["running_closes"]) == 4

    # evidence preserved alongside, not erased:
    snapshot = fields["pre_replay_snapshot"]
    assert snapshot["status"] == "open"
    assert snapshot["hold_days"] == 1
    assert snapshot["running_closes"] == [101.0]
    assert fields["replayed_at"] is not None


@pytest.mark.asyncio
async def test_replay_stale_open_row_falls_back_when_no_history_available(monkeypatch):
    row = _open_row(id=4, ticker="DELISTED", alert_date=date(2026, 5, 1))
    monkeypatch.setattr(shadow_orb_tracker, "get_index_history", AsyncMock(return_value=[]))

    fields = await shadow_orb_tracker.replay_stale_open_row(row, date(2026, 8, 17))

    assert set(fields.keys()) == {"_replay_unavailable"}
    assert "DELISTED" in fields["_replay_unavailable"]


# ─── Evidence-aggregating readers exclude quarantined rows ────────────────


@pytest.mark.asyncio
async def test_get_shadow_outcomes_window_excludes_quarantined_rows(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(db_module, "get_pool", AsyncMock(return_value=pool))

    await db_module.get_shadow_outcomes_window(window_days=30, bar_size_minutes=5)

    sql = conn.fetch.await_args[0][0]
    assert "NOT shadow.quarantined" in sql


@pytest.mark.asyncio
async def test_get_open_shadow_trades_excludes_quarantined_rows(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(db_module, "get_pool", AsyncMock(return_value=pool))

    await db_module.get_open_shadow_trades(bar_size_minutes=5)

    sql = conn.fetch.await_args[0][0]
    assert "NOT quarantined" in sql


@pytest.mark.asyncio
async def test_adapter_shadow_orb_5m_excludes_quarantined_rows(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(strategy_adapters, "get_pool", AsyncMock(return_value=pool))

    await strategy_adapters._adapter_shadow_orb_5m(window_days=90)

    sql = conn.fetch.await_args[0][0]
    assert "NOT quarantined" in sql


@pytest.mark.asyncio
async def test_aggregate_shadow_orb_outcomes_excludes_quarantined_rows(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value="mi_orb_shadow_trades")  # schema_check passes
    counts_row = {"entered": 0, "no_entry": 0, "gate_blocked": 0}
    conn.fetchrow = AsyncMock(return_value=counts_row)
    conn.fetch = AsyncMock(return_value=[])
    # _aggregate_shadow_orb_outcomes imports get_pool locally from db — patch there.
    monkeypatch.setattr(db_module, "get_pool", AsyncMock(return_value=pool))

    await system_review._aggregate_shadow_orb_outcomes(window_days=90)

    counts_sql = conn.fetchrow.await_args[0][0]
    paired_sql = conn.fetch.await_args[0][0]
    assert "NOT quarantined" in counts_sql
    assert "NOT shadow.quarantined" in paired_sql
