"""2026-08-16 exit-path shadow recorder tests. Pure compute (compute_day_row / _sma_trail /
compute_realized_r) + the DB write half (mocked pool — the #173 0-rows lesson). Every
assertion checks a computed VALUE, never a comment/label string (the "assertion matched a
comment, not behaviour" lesson named in the task). THE LINE: this recorder must never write
outside mi_exit_path_shadow / mi_audit_log, and must never call the broker — pinned below.
"""
import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import exit_path_shadow as eps
from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step, seed_exit_state

_ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh=16, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=_ET)


# ── compute_day_row — pure ────────────────────────────────────────────────────────────────


def test_adverse_excursion_is_entry_minus_low_over_r():
    """R=2 (entry 20, stop 18). Day low 17 -> adverse = (20-17)/2 = 1.5R.
    A flipped subtraction (day_low - entry) would give -1.5, a different sign and a
    different number — this pins both."""
    row = eps.compute_day_row(
        is_day_zero=True, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=20.0, day_high=20.5, day_low=17.0, day_close=19.0,
        prior_close=None, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row["adverse_excursion_r"] == pytest.approx(1.5)


def test_favourable_excursion_is_high_minus_entry_over_r():
    row = eps.compute_day_row(
        is_day_zero=True, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=20.0, day_high=24.0, day_low=19.5, day_close=23.0,
        prior_close=None, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row["favourable_excursion_r"] == pytest.approx(2.0)


def test_minus_2r_threshold_is_inclusive_at_the_boundary():
    """day_low sits EXACTLY at entry - 2R. A '>' mutant would read this as untouched;
    the live rule (§0c) counts an exact touch."""
    row = eps.compute_day_row(
        is_day_zero=True, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=20.0, day_high=20.5, day_low=16.0, day_close=19.0,  # 16.0 = 20 - 2*2
        prior_close=None, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row["touched_minus_2r"] is True
    assert row["touched_minus_1r"] is True
    assert row["touched_minus_3r"] is False
    assert row["touched_minus_5r"] is False


def test_running_worst_takes_the_max_across_days_not_just_today():
    """Day 2 dips to -3R (worse than day 1's -1R); day 3 only dips to -0.5R. The running
    worst on day 3 must still reflect day 2's -3R — a mutant that drops the running max
    and uses only today's value would report day 3's worst as 0.5, not 3.0."""
    r1 = eps.compute_day_row(
        is_day_zero=True, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=20.0, day_high=20.5, day_low=18.0, day_close=19.5,
        prior_close=None, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    r2 = eps.compute_day_row(
        is_day_zero=False, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=19.5, day_high=19.6, day_low=14.0, day_close=15.0,  # -3R low
        prior_close=19.5, prior_worst_adverse_r=r1["worst_adverse_excursion_r"],
        prior_best_favourable_r=r1["best_favourable_excursion_r"],
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    r3 = eps.compute_day_row(
        is_day_zero=False, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=15.0, day_high=16.0, day_low=19.0, day_close=19.5,  # only -0.5R today
        prior_close=15.0, prior_worst_adverse_r=r2["worst_adverse_excursion_r"],
        prior_best_favourable_r=r2["best_favourable_excursion_r"],
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert r2["worst_adverse_excursion_r"] == pytest.approx(3.0)
    assert r3["worst_adverse_excursion_r"] == pytest.approx(3.0)  # carried forward, not reset


def test_running_best_takes_the_max_across_days():
    r1 = eps.compute_day_row(
        is_day_zero=True, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=20.0, day_high=26.0, day_low=20.0, day_close=25.0,  # +3R
        prior_close=None, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    r2 = eps.compute_day_row(
        is_day_zero=False, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=25.0, day_high=25.5, day_low=24.0, day_close=24.5,  # +2.25R today, lower than peak
        prior_close=25.0, prior_worst_adverse_r=r1["worst_adverse_excursion_r"],
        prior_best_favourable_r=r1["best_favourable_excursion_r"],
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert r2["best_favourable_excursion_r"] == pytest.approx(3.0)  # carried, not overwritten downward


def test_closed_above_stop_ref_uses_stop_ref_not_a_later_raised_stop():
    """stop_ref = the ORB-low (18.0), fixed at entry. Close sits at 18.5 — ABOVE stop_ref
    but this is the exact shape where a live trail could have raised hard_stop to 19.0;
    a mutant that compared against a raised stop would flip this to False."""
    row = eps.compute_day_row(
        is_day_zero=False, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=18.6, day_high=19.0, day_low=15.6, day_close=18.5,  # dipped through -2R, closed above stop_ref
        prior_close=19.0, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row["touched_minus_2r"] is True
    assert row["closed_above_stop_ref"] is True


def test_gap_r_divides_by_risk_per_share_not_entry_price():
    """R=4 (entry 40, stop 36) so R != entry_price. Prior close 40, today's open 36 ->
    gap = (36-40)/4 = -1.0R. Dividing by entry_price (40) instead would give -0.1, a
    visibly different number this pins."""
    row = eps.compute_day_row(
        is_day_zero=False, entry_price=40.0, stop_ref=36.0, risk_per_share=4.0,
        day_open=36.0, day_high=37.0, day_low=35.0, day_close=36.5,
        prior_close=40.0, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row["gap_r"] == pytest.approx(-1.0)
    assert row["gap_through_stop_ref"] is False  # open 36.0 == stop_ref 36.0, not strictly below


def test_gap_through_stop_ref_is_strict_less_than():
    row_equal = eps.compute_day_row(
        is_day_zero=False, entry_price=40.0, stop_ref=36.0, risk_per_share=4.0,
        day_open=36.0, day_high=37.0, day_low=35.0, day_close=36.5,
        prior_close=40.0, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row_equal["gap_through_stop_ref"] is False  # open == stop_ref is not a gap THROUGH it
    row_through = eps.compute_day_row(
        is_day_zero=False, entry_price=40.0, stop_ref=36.0, risk_per_share=4.0,
        day_open=35.5, day_high=37.0, day_low=35.0, day_close=36.5,
        prior_close=40.0, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row_through["gap_through_stop_ref"] is True


def test_gap_r_is_null_on_day_zero_even_with_a_prior_close():
    """Day 0 gets a prior_close (the EP gap, informational) but gap_r itself must stay
    NULL — there is no overnight gap into a same-day entry."""
    row = eps.compute_day_row(
        is_day_zero=True, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=19.8, day_high=20.5, day_low=19.5, day_close=20.2,
        prior_close=17.0, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row["gap_r"] is None
    assert row["gap_through_stop_ref"] is None
    assert row["prior_close"] == 17.0  # still recorded


def test_touched_plus_2r_is_a_high_touch_regardless_of_close():
    row = eps.compute_day_row(
        is_day_zero=False, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=20.0, day_high=24.01, day_low=19.9, day_close=20.5,  # high touches +2.005R, closes flat
        prior_close=20.0, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row["touched_plus_2r"] is True


def test_close_below_trail_is_none_until_trail_exists():
    row = eps.compute_day_row(
        is_day_zero=True, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=20.0, day_high=20.5, day_low=19.5, day_close=19.0,
        prior_close=None, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=None, trail_sma20=None, trail_price=None,
    )
    assert row["close_below_trail"] is None


def test_close_below_trail_compares_close_to_trail_price():
    row = eps.compute_day_row(
        is_day_zero=False, entry_price=20.0, stop_ref=18.0, risk_per_share=2.0,
        day_open=21.0, day_high=21.2, day_low=20.4, day_close=20.5,
        prior_close=21.0, prior_worst_adverse_r=0.0, prior_best_favourable_r=0.0,
        breakeven_armed=False, trail_sma10=21.0, trail_sma20=None, trail_price=21.0,
    )
    assert row["close_below_trail"] is True  # 20.5 < 21.0


# ── compute_realized_r — pure ──────────────────────────────────────────────────────────────


def test_realized_r_denominator_includes_entry_shares():
    """total_pnl=$100, R=$2/share, 10 shares -> realized_r = 100 / (2*10) = 5.0. Dropping
    entry_shares from the denominator would give 50.0, a 10x-different number."""
    assert eps.compute_realized_r(100.0, 2.0, 10.0) == pytest.approx(5.0)


def test_realized_r_none_on_missing_inputs():
    assert eps.compute_realized_r(None, 2.0, 10.0) is None
    assert eps.compute_realized_r(100.0, 0.0, 10.0) is None
    assert eps.compute_realized_r(100.0, 2.0, None) is None
    assert eps.compute_realized_r(100.0, 2.0, 0.0) is None


# ── _sma_trail — pure, and byte-parity against the LIVE formula ───────────────────────────


def test_sma_trail_none_below_ten_closes():
    sma10, sma20, trail = eps._sma_trail([float(i) for i in range(9)])
    assert (sma10, sma20, trail) == (None, None, None)


def test_sma_trail_picks_the_max_of_sma10_and_sma20():
    """20 closes trending up: SMA10 (recent) > SMA20 (older-weighted). A 'min' mutant
    would pick the SMA20 value instead — this pins the actual numbers, not just which
    branch ran."""
    closes = [float(i) for i in range(1, 21)]  # 1..20, strictly increasing
    sma10, sma20, trail = eps._sma_trail(closes)
    assert sma10 == pytest.approx(sum(range(11, 21)) / 10)   # 15.5
    assert sma20 == pytest.approx(sum(range(1, 21)) / 20)    # 10.5
    assert trail == pytest.approx(sma10)                      # max(15.5, 10.5) = 15.5
    assert trail != pytest.approx(sma20)


def test_sma_trail_matches_exit_logic_active_sma_byte_for_byte():
    """Parity pin against the LIVE formula (broker/exit_logic.py apply_daily_exit_step,
    default 'sma' trail_mode) — guards against silent drift between this module's
    duplicate and the formula it must match."""
    prior_closes = [float(10 + i) for i in range(15)]  # 15 pre-entry closes
    running = [24.0, 23.5, 22.0, 21.0, 20.5, 26.0]      # 6 held-period closes
    _, _, mine = eps._sma_trail(prior_closes + running)

    state = seed_exit_state(
        alert_date=date(2026, 1, 1), entry_price=100.0, hard_stop=None,
        remaining_shares=1,
    )
    step = None
    for i, c in enumerate(running):
        step = apply_daily_exit_step(
            state, {"l": c - 0.01, "c": c}, date(2026, 1, 2) + timedelta(days=i),
            integer_partial_shares=True, skip_partial_decision=True,
            skip_hard_stop_close=True, prior_closes=prior_closes,
        )
        state.update(remaining_shares=1, partial_taken=step.new_partial_taken,
                      breakeven_active=False, exits=step.new_exits,
                      running_closes=step.new_running_closes)
    assert mine == pytest.approx(step.active_sma)


# ── the write half: mocked pool ────────────────────────────────────────────────────────────


def _mk_trade(**overrides):
    base = dict(
        id=501, ticker="ABCL", account_mode="live", signal_type="magna53",
        alert_date=date(2026, 8, 10), entry_price=8.96, orb_low=8.40, hard_stop=8.40,
        entry_shares=57, filled_at=_et(2026, 8, 10, 9, 31), closed_at=None,
        breakeven_active=False, exits=[], total_pnl=0.0, pnl_attribution=None,
        max_recorded_day=None,
    )
    base.update(overrides)
    return base


def _daily_row(o, h, l, c):
    return {"open_price": o, "high_price": h, "low_price": l, "close": c}


@pytest.mark.asyncio
async def test_record_writes_one_row_per_trading_day_and_only_to_the_shadow_table(monkeypatch):
    """THE LINE: the only table this orchestrator INSERT/UPDATE/DELETEs is
    mi_exit_path_shadow (plus mi_audit_log via the shared log_audit_event helper).
    Never mi_live_trades, mi_live_orders, or any order/position table."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()

    conn.fetch = AsyncMock(side_effect=[
        [_mk_trade()],   # eligible-trades scan
        [],              # prior_closes (none before an entirely fresh fixture)
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_row(8.96, 9.20, 8.70, 9.00),   # day 0 daily bar
        {"lo": 8.75, "hi": 9.15, "n": 200},   # day 0 minute HL restriction
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append((sql, args))
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(eps, "get_pool", AsyncMock(return_value=pool))
    audited = []

    async def _audit(event_type, summary, detail=""):
        audited.append(event_type)
    monkeypatch.setattr(eps, "log_audit_event", _audit)

    n = await eps.record_exit_path_shadow(date(2026, 8, 10))
    assert n == 1
    assert len(executed) == 1
    sql, args = executed[0]
    assert "INSERT INTO mi_exit_path_shadow" in sql
    assert "mi_live_trades" not in sql and "mi_live_orders" not in sql
    assert args[eps._UPSERT_COLS.index("trading_day_index")] == 0
    assert args[eps._UPSERT_COLS.index("bar_source")] == "daily+minute_hl"
    # minute-restricted low/high used, not the full daily bar's 8.70/9.20
    assert args[eps._UPSERT_COLS.index("day_low")] == 8.75
    assert args[eps._UPSERT_COLS.index("day_high")] == 9.15
    assert "exit_path_shadow_recorded" in audited


@pytest.mark.asyncio
async def test_stop_ref_prefers_orb_low_over_hard_stop(monkeypatch):
    """The task's own wording is 'the ORB-low stop' — orb_low is the R-unit anchor;
    hard_stop (which the live trail can raise over time) is only a fallback when
    orb_low is unavailable. A distinct fixture (orb_low != hard_stop) is required to
    catch a priority swap — every other fixture in this file sets them equal."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    trade = _mk_trade(orb_low=8.20, hard_stop=8.60)  # raised by a trail, orb_low untouched
    conn.fetch = AsyncMock(side_effect=[[trade], []])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_row(8.96, 9.20, 8.70, 9.00),
        {"lo": 8.75, "hi": 9.15, "n": 200},
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(eps, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(eps, "log_audit_event", AsyncMock())

    await eps.record_exit_path_shadow(date(2026, 8, 10))
    args = executed[0]
    assert args[eps._UPSERT_COLS.index("stop_ref")] == 8.20
    assert args[eps._UPSERT_COLS.index("risk_per_share")] == pytest.approx(8.96 - 8.20)


@pytest.mark.asyncio
async def test_day_zero_falls_back_to_full_daily_high_low_when_no_minute_bars(monkeypatch):
    """When mi_intraday_bars has nothing for the fill window, day 0 uses the FULL daily
    bar's high/low (less precise, never silently wrong) — bar_source says so."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[_mk_trade()], []])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_row(8.96, 9.20, 8.70, 9.00),
        {"lo": None, "hi": None, "n": 0},   # no minute bars
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(eps, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(eps, "log_audit_event", AsyncMock())

    await eps.record_exit_path_shadow(date(2026, 8, 10))
    args = executed[0]
    assert args[eps._UPSERT_COLS.index("bar_source")] == "daily"
    assert args[eps._UPSERT_COLS.index("day_low")] == 8.70
    assert args[eps._UPSERT_COLS.index("day_high")] == 9.20


@pytest.mark.asyncio
async def test_already_recorded_through_window_end_is_skipped(monkeypatch):
    """A closed trade already backfilled through its own close day costs nothing on a
    re-run — no fetch, no write.

    ⚠ The mocks below are wired so that if the guard were REMOVED the walk would
    actually complete and call fetchrow/execute (prior_closes + one full day-0 bar
    are queued) — a starved mock (StopIteration masked by the per-trade try/except)
    would make this test pass whether or not the guard exists, which is exactly the
    "passes both ways" trap. Mutation-proven: removing the guard flips n to 1 and
    both assert_not_called()s fail (see task report)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    trade = _mk_trade(
        closed_at=_et(2026, 8, 10, 15, 0), max_recorded_day=date(2026, 8, 10),
    )
    conn.fetch = AsyncMock(side_effect=[[trade], []])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_row(8.96, 9.20, 8.70, 9.00),
        {"lo": 8.75, "hi": 9.15, "n": 200},
    ])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(eps, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(eps, "log_audit_event", AsyncMock())

    n = await eps.record_exit_path_shadow(date(2026, 8, 11))
    assert n == 0
    conn.fetchrow.assert_not_called()
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_no_valid_r_frame_is_skipped_and_logged(monkeypatch):
    """stop_ref >= entry_price (no valid R frame, the CRMD-class defect) — skip and
    audit, never a fabricated/negative R."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    trade = _mk_trade(orb_low=9.50, hard_stop=9.50)  # stop above entry (8.96)
    conn.fetch = AsyncMock(side_effect=[[trade]])
    conn.fetchrow = AsyncMock()
    conn.execute = AsyncMock()
    monkeypatch.setattr(eps, "get_pool", AsyncMock(return_value=pool))
    audited = []

    async def _audit(event_type, summary, detail=""):
        audited.append((event_type, summary))
    monkeypatch.setattr(eps, "log_audit_event", _audit)

    n = await eps.record_exit_path_shadow(date(2026, 8, 10))
    assert n == 0
    conn.execute.assert_not_called()
    assert any(e == "exit_path_shadow_skipped" for e, _ in audited)


@pytest.mark.asyncio
async def test_exit_day_row_carries_price_reason_and_realized_r(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    trade = _mk_trade(
        closed_at=_et(2026, 8, 10, 9, 51),
        exits=[{"time": "2026-08-10T13:51:00+00:00", "price": 8.40,
                "reason": "stop_hit", "shares": 57, "pnl": -31.92}],
        total_pnl=-31.92,
    )
    conn.fetch = AsyncMock(side_effect=[[trade], []])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_row(8.96, 9.05, 8.35, 8.40),
        {"lo": 8.35, "hi": 9.00, "n": 40},
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(eps, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(eps, "log_audit_event", AsyncMock())

    await eps.record_exit_path_shadow(date(2026, 8, 10))
    args = executed[0]
    assert args[eps._UPSERT_COLS.index("is_exit_day")] is True
    assert args[eps._UPSERT_COLS.index("exit_price")] == 8.40
    assert args[eps._UPSERT_COLS.index("exit_reason")] == "stop_hit"
    # risk_per_share = 8.96 - 8.40 = 0.56; realized_r = -31.92 / (0.56 * 57)
    assert args[eps._UPSERT_COLS.index("realized_r")] == pytest.approx(-31.92 / (0.56 * 57))


@pytest.mark.asyncio
async def test_breakeven_armed_flips_true_on_the_day_a_partial_fired(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    trade = _mk_trade(
        alert_date=date(2026, 8, 5), filled_at=_et(2026, 8, 5, 9, 31),
        closed_at=_et(2026, 8, 8, 16, 0),
        exits=[{"time": "2026-08-07T20:00:00+00:00", "price": 9.60,
                "reason": "partial_profit", "shares": 19, "pnl": 12.16},
               {"time": "2026-08-08T20:00:00+00:00", "price": 9.55,
                "reason": "stop_hit", "shares": 38, "pnl": 22.42}],
        total_pnl=34.58,
    )
    conn.fetch = AsyncMock(side_effect=[[trade], []])
    # 3 trading days: 8/5, 8/6, 8/7 is a Fri, 8/8 is a Sat -> not a trading day; 8/10 Mon.
    # Use a window that lands cleanly on weekdays: 8/5(Wed) 8/6(Thu) 8/7(Fri).
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_row(8.96, 9.10, 8.80, 9.00),   # 8/5 day 0
        {"lo": 8.85, "hi": 9.05, "n": 50},
        _daily_row(9.00, 9.30, 8.95, 9.20),   # 8/6 day 1
        _daily_row(9.20, 9.70, 9.10, 9.60),   # 8/7 day 2 — partial fires here (per exits[0])
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(eps, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(eps, "log_audit_event", AsyncMock())

    await eps.record_exit_path_shadow(date(2026, 8, 7))
    be_idx = eps._UPSERT_COLS.index("breakeven_armed")
    day_idx = eps._UPSERT_COLS.index("trading_day")
    by_day = {a[day_idx]: a[be_idx] for a in executed}
    assert by_day[date(2026, 8, 5)] is False
    assert by_day[date(2026, 8, 6)] is False
    assert by_day[date(2026, 8, 7)] is True


@pytest.mark.asyncio
async def test_a_missing_day_nulls_the_next_days_gap_instead_of_mislabelling_it(monkeypatch):
    """A day with no bar (mi_daily_closes AND Polygon both empty — POLYGON_API_KEY is
    unset in this test env, so the fallback fails naturally) is skipped. The FOLLOWING
    recorded day's gap must come out NULL, never a two-day gap silently reported as
    overnight (found in review — the exact column the -2R-hold stop-fork decision reads).
    """
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    trade = _mk_trade(
        alert_date=date(2026, 8, 5), filled_at=_et(2026, 8, 5, 9, 31), closed_at=None,
    )
    conn.fetch = AsyncMock(side_effect=[[trade], []])
    # 8/5 Wed (day 0, recorded) -> 8/6 Thu (no bar anywhere, skipped) -> 8/7 Fri (recorded).
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_row(8.96, 9.10, 8.80, 9.00),   # 8/5 daily bar
        {"lo": 8.85, "hi": 9.05, "n": 50},    # 8/5 minute HL
        None,                                  # 8/6 mi_daily_closes: no row -> Polygon fallback (fails, no key)
        _daily_row(9.20, 9.70, 9.10, 9.60),   # 8/7 daily bar
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(eps, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(eps, "log_audit_event", AsyncMock())

    await eps.record_exit_path_shadow(date(2026, 8, 7))
    assert len(executed) == 2  # 8/6 never wrote a row
    day_idx = eps._UPSERT_COLS.index("trading_day")
    gap_idx = eps._UPSERT_COLS.index("gap_r")
    pc_idx = eps._UPSERT_COLS.index("prior_close")
    by_day = {a[day_idx]: (a[gap_idx], a[pc_idx]) for a in executed}
    assert by_day[date(2026, 8, 7)] == (None, None)  # NOT a mislabelled 2-day gap


# ── retention ───────────────────────────────────────────────────────────────────────────


def test_purge_old_data_never_deletes_the_exit_path_shadow():
    from unittest.mock import patch
    import agents.market_intelligence.db as db_module

    executed_sqls = []

    async def fake_execute(sql, cutoff):
        executed_sqls.append(sql.strip())
        return "DELETE 0"

    mock_conn = MagicMock()
    mock_conn.execute = fake_execute
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(db_module, "get_pool", AsyncMock(return_value=mock_pool)):
        asyncio.run(db_module.purge_old_data())

    tables_deleted = {sql.split("FROM")[1].split("WHERE")[0].strip() for sql in executed_sqls if "DELETE" in sql}
    assert "mi_exit_path_shadow" not in tables_deleted
