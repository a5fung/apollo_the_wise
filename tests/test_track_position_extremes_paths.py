"""#306 (2026-07-25) — Intraday Path Recorder: `track_open_position_extremes` subsumed
to an Alpaca-sourced path recorder + extremes maintainer.

There is currently NO test covering this function at all — this is net-new coverage
establishing its baseline. Design: docs/design/306_intraday_path_recorder_2026-07-25.md

Two defects fixed together:
(1) Polygon `get_minute_bars` (~15-17 min delayed on our Starter plan) replaced with
    real-time Alpaca (`alpaca_client.get_minute_bars_range`).
(2) The selection predicate is open-OR-closed-today (not open-only) — a trade that
    fills and closes between two `*/5` polls is picked up via `closed_at` by the very
    next poll. This is the #310 bug class (`pivot_stop_shadow`'s `closed_at::date =
    today` exact match silently dropped 7 of 9 same-day round trips) — the fix must be
    a tz-aware TIMESTAMPTZ `>=` comparison, never a `::date` cast.

LOG-ONLY shadow: no order emission, no exit-path change. `highest_price_seen` IS read
by the time-stop scan (an operator-confirmed `/timestop` sell) — this design argues
(and does not re-litigate) that the provenance change is safe for that >=5-day-hold
population; these tests pin the COMPUTATION semantics (the two clamps), not that
argument.
"""
from __future__ import annotations

from datetime import date, datetime, time as datetime_time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import make_mock_pool
from agents.market_intelligence.broker import alpaca_client as alp
from agents.market_intelligence.broker import order_manager as om

_ET = ZoneInfo("America/New_York")


def _bar(t_et, o, h, l, c, v=1000, vwap=None):
    """A bar dict shaped like `alpaca_client.get_minute_bars_range`'s return."""
    return {"t_et": t_et, "open": o, "high": h, "low": l, "close": c, "volume": v, "vwap": vwap}


def _trade(id_, ticker, filled_at, closed_at=None):
    return {"id": id_, "ticker": ticker, "filled_at": filled_at, "closed_at": closed_at}


def _freeze_now(monkeypatch, fixed_now: datetime):
    """Patch order_manager's module-level `datetime` name so `datetime.now(_ET)`
    returns a fixed instant. Applied to every test that calls
    `track_open_position_extremes` — the function now short-circuits
    (`window_end_et <= today_open_et`) on any pre-open fire, so a test's behavior
    must not depend on the REAL wall-clock time the suite happens to run at."""
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is not None else fixed_now.replace(tzinfo=None)
    monkeypatch.setattr(om, "datetime", _Frozen)


# A safe mid-RTH instant (after 9:30 open, before the 16:00 window cap) for tests
# that don't care about the window-end boundary itself.
_MID_RTH = datetime(2026, 7, 24, 12, 0, tzinfo=_ET)


# ── 1. Selection predicate: open-OR-closed-today, structural #310 pin ──────────────


@pytest.mark.asyncio
async def test_selection_predicate_open_or_closed_today_310_safe(monkeypatch):
    """The WHERE clause must be `(status='filled' AND remaining_shares>0) OR
    closed_at >= $1` — open-OR-closed-today (defect #2) — and `$1` must be bound as a
    full tz-aware TIMESTAMPTZ instant (9:30 ET TODAY), never a bare `::date` cast (the
    #310 bug class). Pinned against the ACTUAL executed query/params, not a re-derived
    copy, so a future edit that reintroduces `::date` fails this immediately."""
    _freeze_now(monkeypatch, _MID_RTH)
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    n = await om.track_open_position_extremes()

    assert n == 0
    query, param = conn.fetch.await_args_list[0].args
    assert "::date" not in query  # never a calendar-date cast (#310 bug class)
    assert "status = 'filled'" in query and "remaining_shares > 0" in query  # open branch kept
    assert "closed_at >= $1" in query  # closed-today branch: instant `>=`, not `=`
    # $1 is a full tz-aware timestamp (9:30 ET today), not a bare date.
    assert param.tzinfo is not None
    assert (param.hour, param.minute, param.second, param.microsecond) == (9, 30, 0, 0)


def test_310_utc_rollover_predicate_math_proof():
    """Concrete #310 scenario: a trade closes at 20:00 ET (= 00:00 UTC the NEXT
    calendar day). The bug this design explicitly avoids (`closed_at::date = today`,
    which under a UTC session timezone compares TOMORROW's UTC date against TODAY's ET
    date) would silently EXCLUDE this trade even though it unambiguously closed TODAY
    in ET wall-clock terms — exactly the class that dropped 7 of 9 same-day round trips
    pre-#310-fix.

    Our predicate (`closed_at >= today_open_et`) is a pure UTC-instant comparison.
    Python's aware-datetime `>=` and Postgres's TIMESTAMPTZ `>=` compute this
    IDENTICALLY (both instant-based, neither depends on a session/calendar timezone),
    so evaluating it in Python here is a faithful proxy for what Postgres computes for
    this exact operator — unlike a `::date` cast, which is session-timezone-dependent
    and is exactly the bug class this design forbids.

    FAILS without the fix: `_pre_310_predicate` below reproduces the OLD buggy
    comparison and gets the late-close case wrong (excludes what must be included).
    """
    today = date(2026, 7, 24)
    today_open_et = datetime(2026, 7, 24, 9, 30, tzinfo=_ET)

    closed_today_late_et = datetime(2026, 7, 24, 20, 0, tzinfo=_ET)   # -> 2026-07-25 00:00 UTC
    closed_today_early_et = datetime(2026, 7, 24, 9, 39, tzinfo=_ET)  # -> same UTC calendar day
    closed_yesterday_et = datetime(2026, 7, 23, 19, 59, tzinfo=_ET)

    # The FIXED predicate (byte-identical direction to `closed_at >= $1`):
    assert (closed_today_late_et >= today_open_et) is True
    assert (closed_today_early_et >= today_open_et) is True
    assert (closed_yesterday_et >= today_open_et) is False

    # Fail-without-fix proof: the OLD `closed_at::date = today` bug, reproduced —
    # an exact calendar-date match cast under a UTC session timezone.
    def _pre_310_predicate(closed_at_et: datetime, today_et_date: date) -> bool:
        return closed_at_et.astimezone(timezone.utc).date() == today_et_date

    assert _pre_310_predicate(closed_today_late_et, today) is False  # BUG: wrongly excluded
    assert _pre_310_predicate(closed_today_early_et, today) is True
    assert _pre_310_predicate(closed_yesterday_et, today) is False


# ── 2. Fast-trade capture (defect #2, end-to-end) ───────────────────────────────────


@pytest.mark.asyncio
async def test_fast_trade_captured_within_one_poll(monkeypatch):
    """A trade that fills 09:36 and closes 09:39 — dead entirely between two `*/5`
    polls under the OLD open-only selection — is picked up by the very next poll via
    `closed_at`, and its in-hold bars are both persisted (path) and folded into
    extremes in that SAME run."""
    _freeze_now(monkeypatch, _MID_RTH)
    pool, conn = make_mock_pool()
    trade = _trade(501, "FAST", datetime(2026, 7, 24, 9, 36, tzinfo=_ET),
                    datetime(2026, 7, 24, 9, 39, tzinfo=_ET))
    conn.fetch = AsyncMock(return_value=[trade])
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    bars = [
        _bar(datetime(2026, 7, 24, 9, 36, tzinfo=_ET), 10.0, 10.2, 9.9, 10.1),
        _bar(datetime(2026, 7, 24, 9, 37, tzinfo=_ET), 10.1, 10.5, 10.0, 10.4),
        _bar(datetime(2026, 7, 24, 9, 38, tzinfo=_ET), 10.4, 10.6, 10.3, 9.85),
    ]
    fake_alpaca = MagicMock()
    fake_alpaca.get_minute_bars_range = AsyncMock(return_value=bars)
    fake_alpaca.persist_intraday_bars = AsyncMock()
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    n = await om.track_open_position_extremes()

    assert n == 1
    fake_alpaca.persist_intraday_bars.assert_awaited_once_with("FAST", bars)
    rows = conn.executemany.await_args.args[1]
    assert rows == [(501, 9.9, 10.6)]  # min(low)/max(high) over all 3 in-hold bars


# ── 3. Recording window != extremes window (clamp A) ───────────────────────────────


@pytest.mark.asyncio
async def test_recording_window_does_not_contaminate_extremes(monkeypatch):
    """Post-exit same-day bars ARE persisted to mi_intraday_bars (recording window =
    the full fetch window, for offline review context) but must NEVER enter
    highest_price_seen / lowest_price_seen (extremes window = filled_at..closed_at
    only) — the HUT post-stop re-cross class the parent analysis relied on excluding."""
    _freeze_now(monkeypatch, _MID_RTH)
    pool, conn = make_mock_pool()
    trade = _trade(601, "HUT", datetime(2026, 7, 24, 9, 31, tzinfo=_ET),
                    datetime(2026, 7, 24, 9, 39, tzinfo=_ET))
    conn.fetch = AsyncMock(return_value=[trade])
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    in_hold_bar = _bar(datetime(2026, 7, 24, 9, 35, tzinfo=_ET), 10.0, 10.3, 9.9, 10.2)
    post_exit_spike = _bar(datetime(2026, 7, 24, 9, 45, tzinfo=_ET), 11.0, 15.0, 10.9, 14.5)
    bars = [in_hold_bar, post_exit_spike]

    fake_alpaca = MagicMock()
    fake_alpaca.get_minute_bars_range = AsyncMock(return_value=bars)
    fake_alpaca.persist_intraday_bars = AsyncMock()
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    n = await om.track_open_position_extremes()

    assert n == 1
    # PATH: both bars persisted — recording window is the full fetch window.
    fake_alpaca.persist_intraday_bars.assert_awaited_once_with("HUT", bars)
    # EXTREMES: only the in-hold bar counted — the 15.0 post-exit spike must never
    # reach highest_price_seen.
    rows = conn.executemany.await_args.args[1]
    assert rows == [(601, 9.9, 10.3)]


# ── 4. SC-1 boundary preserved (clamp B) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_hold_lower_bound_inclusive_of_filled_at(monkeypatch):
    """The in-hold filter stays `t >= filled_at` exactly as pre-#306 (was `t >=
    filled_ms` against epoch-ms Polygon bars — same inclusive semantic, now compared
    as tz-aware datetimes): a bar at EXACTLY filled_at is included; a bar before
    filled_at is excluded."""
    _freeze_now(monkeypatch, _MID_RTH)
    pool, conn = make_mock_pool()
    filled_at = datetime(2026, 7, 24, 9, 31, tzinfo=_ET)
    trade = _trade(701, "SC1", filled_at, None)  # still open
    conn.fetch = AsyncMock(return_value=[trade])
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    before_fill_bar = _bar(datetime(2026, 7, 24, 9, 30, tzinfo=_ET), 4.0, 4.2, 3.9, 4.1)
    at_fill_bar = _bar(filled_at, 5.0, 5.5, 4.8, 5.2)
    bars = [before_fill_bar, at_fill_bar]

    fake_alpaca = MagicMock()
    fake_alpaca.get_minute_bars_range = AsyncMock(return_value=bars)
    fake_alpaca.persist_intraday_bars = AsyncMock()
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    n = await om.track_open_position_extremes()

    assert n == 1
    rows = conn.executemany.await_args.args[1]
    # Only the t == filled_at bar counted — the pre-fill 9:30 bar's 3.9 low/4.2 high
    # must NOT appear (pre-fill dip must never contaminate extremes, #74's original
    # concern, preserved under the new source).
    assert rows == [(701, 4.8, 5.5)]


# ── 5. Monotonicity lives in the SQL, not this code ─────────────────────────────────


@pytest.mark.asyncio
async def test_monotonic_update_sql_uses_least_greatest_coalesce(monkeypatch):
    """This function never compares against a previous poll's value itself —
    monotonicity is enforced entirely by the UPDATE's LEAST/GREATEST + COALESCE
    against the STORED column value. Pin the SQL text (a future edit could silently
    drop the DB-side clamp) and show a second, NARROWER poll still submits its OWN
    period low/high as-is — the SQL is what prevents loosening, not this code."""
    _freeze_now(monkeypatch, _MID_RTH)
    pool, conn = make_mock_pool()
    trade = _trade(801, "MONO", datetime(2026, 7, 24, 9, 31, tzinfo=_ET), None)
    conn.fetch = AsyncMock(return_value=[trade])
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    fake_alpaca = MagicMock()
    fake_alpaca.persist_intraday_bars = AsyncMock()
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    wide_bars = [_bar(datetime(2026, 7, 24, 9, 31, tzinfo=_ET), 10, 20, 5, 15)]
    fake_alpaca.get_minute_bars_range = AsyncMock(return_value=wide_bars)
    await om.track_open_position_extremes()
    sql_1, rows_1 = conn.executemany.await_args.args
    assert rows_1 == [(801, 5, 20)]

    narrow_bars = [_bar(datetime(2026, 7, 24, 9, 36, tzinfo=_ET), 10, 15, 8, 12)]
    fake_alpaca.get_minute_bars_range = AsyncMock(return_value=narrow_bars)
    await om.track_open_position_extremes()
    sql_2, rows_2 = conn.executemany.await_args.args
    assert rows_2 == [(801, 8, 15)]  # this poll's own period, submitted as-is

    for sql in (sql_1, sql_2):
        assert "LEAST(COALESCE(lowest_price_seen, $2), $2)" in sql
        assert "GREATEST(COALESCE(highest_price_seen, $3), $3)" in sql


# ── 6. Per-ticker isolation ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_per_ticker_isolation_on_fetch_failure(monkeypatch):
    """A fetch exception for one ticker must not abort the batch — the existing job's
    exact isolation pattern (per-ticker try/except, continue)."""
    _freeze_now(monkeypatch, _MID_RTH)
    pool, conn = make_mock_pool()
    trade_a = _trade(901, "BADX", datetime(2026, 7, 24, 9, 31, tzinfo=_ET), None)
    trade_b = _trade(902, "GOODY", datetime(2026, 7, 24, 9, 31, tzinfo=_ET), None)
    conn.fetch = AsyncMock(return_value=[trade_a, trade_b])
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    good_bars = [_bar(datetime(2026, 7, 24, 9, 31, tzinfo=_ET), 10, 11, 9, 10.5)]

    async def _fetch(ticker, start, end):
        if ticker == "BADX":
            raise RuntimeError("Alpaca fetch exploded")
        return good_bars

    fake_alpaca = MagicMock()
    fake_alpaca.get_minute_bars_range = AsyncMock(side_effect=_fetch)
    fake_alpaca.persist_intraday_bars = AsyncMock()
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    n = await om.track_open_position_extremes()

    assert n == 1
    rows = conn.executemany.await_args.args[1]
    assert rows == [(902, 9, 11)]  # BADX skipped, GOODY still processed


# ── 7. Idempotency (ON CONFLICT DO NOTHING) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_persist_intraday_bars_idempotent_on_conflict_do_nothing(monkeypatch):
    """Re-polling the same window twice must be a harmless no-op by construction — the
    batch upsert's `ON CONFLICT (ticker, bar_time) DO NOTHING`, not a Python-side
    de-dup, is what makes it idempotent. No exception on the repeat call."""
    import agents.market_intelligence.db as db_mod
    pool, conn = make_mock_pool()
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(db_mod, "get_pool", AsyncMock(return_value=pool))

    bars = [_bar(datetime(2026, 7, 24, 9, 31, tzinfo=_ET), 10, 11, 9, 10.5)]

    await alp.persist_intraday_bars("DUPE", bars)
    await alp.persist_intraday_bars("DUPE", bars)  # identical re-poll — must not raise

    assert conn.executemany.await_count == 2
    for call in conn.executemany.await_args_list:
        sql = call.args[0]
        assert "INSERT INTO mi_intraday_bars" in sql
        assert "ON CONFLICT (ticker, bar_time) DO NOTHING" in sql


# ── 8. EOD sweep gap-heal ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_eod_sweep_heals_thin_day_and_logs_persistent_gap(monkeypatch):
    """Open multi-day position with a thin prior-day bar count (a restart-day hole) —
    the 16:10 sweep (sweep=True) refetches that day; if the refetch is STILL thin (a
    real gap, not a restart artifact), it logs `path_coverage_gap` to the audit log
    ONLY — never Telegram (a shadow coverage heal is not an alertable condition)."""
    now_et = datetime(2026, 7, 24, 16, 10, tzinfo=_ET)  # the sweep's actual fire time
    _freeze_now(monkeypatch, now_et)
    filled_at = (now_et - timedelta(days=5)).replace(hour=9, minute=31, second=0, microsecond=0)
    thin_day = (now_et - timedelta(days=3)).date()

    pool, conn = make_mock_pool()
    trade = _trade(1101, "MULTI", filled_at, None)  # still open, multi-day
    day_row = {"d": thin_day, "n": 120}
    conn.fetch = AsyncMock(side_effect=[[trade], [day_row]])
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    audit = AsyncMock()
    monkeypatch.setattr(om, "log_audit_event", audit)
    telegram = AsyncMock()
    monkeypatch.setattr(om, "send_telegram_message", telegram)

    today_bars = [_bar(now_et.replace(second=0, microsecond=0), 10, 10.5, 9.8, 10.2)]
    thin_refetch = [
        _bar(datetime.combine(thin_day, datetime_time(9, 30), tzinfo=_ET), 5, 5.2, 4.9, 5.1)
        for _ in range(150)
    ]

    fake_alpaca = MagicMock()
    fake_alpaca.persist_intraday_bars = AsyncMock()
    fake_alpaca.get_minute_bars_range = AsyncMock(side_effect=[today_bars, thin_refetch])
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    await om.track_open_position_extremes(sweep=True)

    assert fake_alpaca.get_minute_bars_range.await_count == 2  # today window + thin-day refetch
    day_call_args = fake_alpaca.get_minute_bars_range.await_args_list[1].args
    assert day_call_args[0] == "MULTI"
    assert day_call_args[1].date() == thin_day

    audit.assert_awaited_once()
    ev_type, summary = audit.await_args.args[:2]
    assert ev_type == "path_coverage_gap"
    assert "MULTI" in summary and str(thin_day) in summary and "150/390" in summary
    telegram.assert_not_awaited()


# ── extra: fetch window (recording + extremes) capped at 16:00 ET ──────────────────
# Not one of the design's numbered ~9, added post-advisor-review 2026-07-25: clamp A
# says an OPEN position's extremes upper bound is "unbounded" — but that must mean
# "now, within the trading day," not literally unbounded. At the 16:10 sweep, now_et
# is 16:10; without a 16:00 cap on the FETCH window itself, any 16:00-16:10 print
# would (a) leak into highest/lowest_price_seen for every still-open position and
# (b) violate §2b's recording boundary ("through 16:00 ... never further").


@pytest.mark.asyncio
async def test_fetch_window_end_capped_at_1600_et_not_raw_now(monkeypatch):
    """At the 16:10 EOD sweep (now_et = 16:10), the fetch window end passed to
    get_minute_bars_range must be capped at 16:00 ET, never the raw now_et — this is
    what keeps an OPEN position's "unbounded" extremes upper bound from silently
    including after-hours prints, and keeps the recorded path from extending past
    16:00 (design §2b)."""
    _freeze_now(monkeypatch, datetime(2026, 7, 24, 16, 10, tzinfo=_ET))

    pool, conn = make_mock_pool()
    trade = _trade(1301, "OPENX", datetime(2026, 7, 24, 9, 31, tzinfo=_ET), None)  # still open
    conn.fetch = AsyncMock(return_value=[trade])
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    bars = [_bar(datetime(2026, 7, 24, 9, 31, tzinfo=_ET), 10, 10.5, 9.8, 10.2)]
    fake_alpaca = MagicMock()
    fake_alpaca.get_minute_bars_range = AsyncMock(return_value=bars)
    fake_alpaca.persist_intraday_bars = AsyncMock()
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    await om.track_open_position_extremes()

    ticker, start_arg, end_arg = fake_alpaca.get_minute_bars_range.await_args.args
    assert ticker == "OPENX"
    assert end_arg == datetime(2026, 7, 24, 16, 0, tzinfo=_ET)  # capped, NOT 16:10


@pytest.mark.asyncio
async def test_fetch_window_end_uses_now_during_regular_rth_poll(monkeypatch):
    """During a normal */5 poll (now_et well inside RTH), the cap is a no-op — the
    window end is exactly now_et, unchanged from pre-fix behavior."""
    _freeze_now(monkeypatch, datetime(2026, 7, 24, 10, 5, tzinfo=_ET))

    pool, conn = make_mock_pool()
    trade = _trade(1302, "RTHX", datetime(2026, 7, 24, 9, 31, tzinfo=_ET), None)
    conn.fetch = AsyncMock(return_value=[trade])
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    bars = [_bar(datetime(2026, 7, 24, 9, 31, tzinfo=_ET), 10, 10.5, 9.8, 10.2)]
    fake_alpaca = MagicMock()
    fake_alpaca.get_minute_bars_range = AsyncMock(return_value=bars)
    fake_alpaca.persist_intraday_bars = AsyncMock()
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    await om.track_open_position_extremes()

    _, _, end_arg = fake_alpaca.get_minute_bars_range.await_args.args
    assert end_arg == datetime(2026, 7, 24, 10, 5, tzinfo=_ET)  # == now_et, uncapped


@pytest.mark.asyncio
async def test_pre_open_fire_short_circuits_before_any_query(monkeypatch):
    """The `*/5` cron slot starts at hour=9 (9:00-9:25 fire before the 9:30 open) —
    at those times window_end_et <= today_open_et, so the job must return 0 WITHOUT
    querying mi_live_trades or calling Alpaca at all: pre-#306 this case couldn't
    arise (Polygon's whole-day fetch had no start/end window to invert), so without
    this guard a pre-open fire would request an INVERTED [09:30, 09:05] window from
    Alpaca for any already-open multi-day position — fails safe, but noisy. This also
    guards `sweep=True`: a manual pre-open invocation would silently skip the gap-heal
    too (the 16:10 registration itself can never hit this path)."""
    _freeze_now(monkeypatch, datetime(2026, 7, 24, 9, 5, tzinfo=_ET))
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    fake_alpaca = MagicMock()
    fake_alpaca.get_minute_bars_range = AsyncMock(return_value=[])
    monkeypatch.setattr(om, "alpaca", fake_alpaca)

    assert await om.track_open_position_extremes() == 0
    conn.fetch.assert_not_awaited()
    fake_alpaca.get_minute_bars_range.assert_not_awaited()


# ── 9. LIVE_TRADING_ENABLED gate ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_trading_disabled_gate_skips_both_jobs(monkeypatch):
    """The gate lives at the scheduler job-wrapper level (order_manager.
    track_open_position_extremes itself has no gate — matches every sibling job in
    scheduler.py). Both the 5-min poll job and the new 16:10 EOD sweep job must
    short-circuit before ever touching the DB."""
    import agents.market_intelligence.scheduler as sched
    import agents.market_intelligence.constants as constants

    monkeypatch.setattr(constants, "LIVE_TRADING_ENABLED", False)
    spy = AsyncMock()
    monkeypatch.setattr(om, "track_open_position_extremes", spy)

    await sched._track_open_position_extremes_job()
    await sched._position_path_eod_sweep_job()

    spy.assert_not_awaited()
