"""#617 Step 2 (2026-09-03) gap-floor near-miss replay tests.

Pure compute (near_miss_lo_pct / gap_band / touch_and_sustain / n_trading_days_back) +
orchestration against mocked db/lfc/srr calls (no real DB — the build session has no prod
access; these prove the WIRING, not a live number).

THE LINE — the properties this file proves at the code layer:
  1. NOTHING LIVE READS IT: no module under agents/ except the scheduler imports the recorder.
  2. TOTAL FAILURE: one candidate raising is counted and audited; the others proceed.
  3. SURVIVORSHIP: a still-open walk is WRITTEN (not dropped) with a mark-to-market mark_r,
     and the guarded UPSERT only refreshes an 'open' row, never a terminal one.
  4. SUBMIT TIME is always 09:31 ET — the most optimistic detection time (never derived from
     an event tick, unlike #593 — there is no reject event here, only an open-gap population).
  5. THE BAND TRACKS THE LIVE FLOOR: gap_band / near_miss_lo_pct read ep_detector.MIN_GAP_PCT,
     never a hardcoded copy.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import db
from agents.market_intelligence import gap_near_miss_replay as gnm
from agents.market_intelligence import rule_eras

_ET = ZoneInfo("America/New_York")
_REPO = Path(__file__).resolve().parent.parent
_MODULE = _REPO / "agents" / "market_intelligence" / "gap_near_miss_replay.py"

SESSION_DATE = date(2026, 8, 20)   # Thursday, era C, a real NYSE trading day
TODAY = date(2026, 9, 3)


@pytest.fixture(autouse=True)
def _real_orb_validation(monkeypatch):
    """tests/conftest.py stubs agents.market_intelligence.backtester.filters with
    MagicMocks (the real module drags heavy deps into the test env), so the recorder's
    imported validate_orb_entry is a mock under pytest. Patch in a faithful copy of the real
    contract (backtester/filters.py::validate_orb_entry) so these tests exercise real
    admission behaviour — the same fixture test_sustain_reject_replay.py uses for the same
    reason."""
    def _validate(orb_high, orb_low, atr_14):
        orb_range = orb_high - orb_low
        if orb_range <= 0:
            return False, "setup:zero_range"
        if atr_14 and atr_14 > 0 and orb_range > 1.5 * atr_14:
            return False, f"setup:stop_too_wide: {orb_range:.2f} > 1.5x ATR {atr_14:.2f}"
        return True, None
    monkeypatch.setattr(gnm, "validate_orb_entry", _validate)


def _m(hh, mm, o, h, l, c, d=SESSION_DATE):
    return {"m": datetime(d.year, d.month, d.day, hh, mm, tzinfo=_ET), "o": o, "h": h, "l": l, "c": c}


def _daily_row(d, o, h, l, c, v):
    return {"trade_date": d, "open_price": o, "high_price": h, "low_price": l, "close": c, "volume": v}


PRIOR_ROWS = [_daily_row(SESSION_DATE - timedelta(days=i), 10.0, 10.6, 9.4, 10.0, 1_000_000)
             for i in range(15, 0, -1)]


# ── Pure compute ────────────────────────────────────────────────────────────────────────


def test_near_miss_lo_pct_is_two_points_below_the_floor():
    assert gnm.near_miss_lo_pct(9.0) == pytest.approx(7.0)
    assert gnm.near_miss_lo_pct(10.0) == pytest.approx(8.0)   # tracks a different floor, never hardcoded


def test_gap_band_bisects_the_near_miss_band():
    assert gnm.gap_band(7.2, floor_pct=9.0) == "7_8"
    assert gnm.gap_band(7.99, floor_pct=9.0) == "7_8"
    assert gnm.gap_band(8.0, floor_pct=9.0) == "8_9"
    assert gnm.gap_band(8.99, floor_pct=9.0) == "8_9"


def test_gap_band_tracks_a_different_floor_without_a_code_change():
    """If MIN_GAP_PCT ever moves (Step 3, operator-only), the band must slide with it — never
    require a second hardcoded update (the P15 fork class)."""
    assert gnm.gap_band(8.5, floor_pct=10.0) == "8_9"
    assert gnm.gap_band(9.5, floor_pct=10.0) == "9_10"


def test_touch_and_sustain_touch_only():
    window = [_m(9, 30, 100.0, 109.5, 99.0, 100.0),   # touches +9.5% high, closes flat
             _m(9, 31, 100.0, 100.2, 99.8, 100.1)]
    touch, sustain = gnm.touch_and_sustain(window, prev_close=100.0, floor_pct=9.0)
    assert touch is True and sustain is False


def test_touch_and_sustain_needs_three_consecutive_closes():
    prev_close = 100.0
    window = [_m(9, 30, 109.0, 109.5, 108.5, 109.2),
             _m(9, 31, 109.2, 109.5, 108.9, 109.3),
             _m(9, 32, 109.3, 109.6, 109.0, 109.4)]     # 3 consecutive closes >= 109 (9%)
    touch, sustain = gnm.touch_and_sustain(window, prev_close, floor_pct=9.0)
    assert touch is True and sustain is True


def test_touch_and_sustain_a_broken_streak_never_sustains():
    prev_close = 100.0
    window = [_m(9, 30, 109.0, 109.5, 108.5, 109.2),
             _m(9, 31, 108.0, 108.2, 107.5, 107.9),      # drops below the floor — resets the run
             _m(9, 32, 109.3, 109.6, 109.0, 109.4)]
    touch, sustain = gnm.touch_and_sustain(window, prev_close, floor_pct=9.0)
    assert touch is True and sustain is False


def test_touch_and_sustain_none_without_prev_close_or_bars():
    assert gnm.touch_and_sustain([], prev_close=100.0) == (None, None)
    assert gnm.touch_and_sustain([_m(9, 30, 100, 101, 99, 100)], prev_close=None) == (None, None)


def test_touch_and_sustain_only_reads_the_0930_0944_window():
    prev_close = 100.0
    # a huge print at 09:45 (outside the window) must not count
    window = [_m(9, 30, 100.0, 100.1, 99.9, 100.0), _m(9, 45, 100.0, 130.0, 99.9, 129.0)]
    touch, sustain = gnm.touch_and_sustain(window, prev_close, floor_pct=9.0)
    assert touch is False and sustain is False


def test_n_trading_days_back_skips_weekends():
    assert gnm.n_trading_days_back(date(2026, 8, 20), 3) == date(2026, 8, 17)


# ── Reuse, not reimplementation — proves the module imports rather than mirrors a 6th copy ──


def test_entry_walk_and_bracket_helpers_are_the_sustain_reject_replay_module_objects():
    """The #617 card: 'Reuse live_fill_counterfactuals.walk_arm... do not write a fifth
    walker.' entry_walk / entry_cancel_asof / current_era_stop / mark_pnl_per_share are all
    imported from sustain_reject_replay (the closest sibling), never re-mirrored here."""
    import agents.market_intelligence.sustain_reject_replay as srr
    assert gnm.srr.entry_walk is srr.entry_walk
    assert gnm.srr.entry_cancel_asof is srr.entry_cancel_asof
    assert gnm.srr.current_era_stop is srr.current_era_stop
    assert gnm.srr.mark_pnl_per_share is srr.mark_pnl_per_share
    assert gnm.walk_arm is __import__(
        "agents.market_intelligence.live_fill_counterfactuals", fromlist=["walk_arm"]).walk_arm


# ── Orchestration (mocked db + lfc/srr — no real DB in this sandbox) ──────────────────────


def _pop_row(ticker="ABCD", trade_date=SESSION_DATE, prev_close=10.0, prev_volume=1_000_000.0,
            open_gap_pct=7.5, open_price=None):
    """open_price defaults to the day0 fixtures' own ORB-bar open (10.0) rather than
    prev_close*(1+gap%) — most tests below hand-craft day0 bars independently of prev_close/
    gap%, and the split-adjustment guard compares open_price against the RAW 09:30 print, so
    an unrelated test must not accidentally diverge (>5%) from it. Tests exercising the guard
    itself pass open_price explicitly."""
    if open_price is None:
        open_price = 10.0
    return {"ticker": ticker, "trade_date": trade_date, "prev_close": prev_close,
           "prev_volume": prev_volume, "open_price": open_price, "open_gap_pct": open_gap_pct}


def _fake_pool_getter():
    from unittest.mock import MagicMock
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)

    async def get_pool():
        return pool
    return get_pool


@pytest.mark.asyncio
async def test_settled_loser_writes_realized_r_and_both_meets_flags_false():
    """A clean day-0 stop-out: fill at orb_high 10.5, stop 2x9.5-10.5=8.5 (entry_minus_2r),
    a violent same-day drop stops it at EXACTLY 8.5 (no gap-through) -> realized_r = -1.0."""
    day0 = [_m(9, 30, 10.0, 10.5, 9.5, 10.3),
           _m(9, 31, 10.3, 10.4, 10.2, 10.35),
           _m(9, 32, 10.4, 10.6, 10.3, 10.55),   # fill bar: crosses orb_high 10.5
           _m(9, 33, 10.5, 10.55, 8.0, 8.2)]     # stops the WHOLE position at 8.5
    written = []

    async def _fake_upsert(fields):
        written.append(dict(fields))
        return True

    with patch.object(gnm, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS)), \
        patch.object(gnm, "get_intraday_bars_window", AsyncMock(return_value=day0)), \
        patch.object(gnm.lfc, "_assemble_sessions", AsyncMock(return_value=[])), \
        patch.object(gnm, "upsert_gap_near_miss_replay", _fake_upsert):
        out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
              "pending": 0, "errors": 0, "candidates": 0, "written": 0}
        await gnm._record_one_near_miss(conn=object(), row=_pop_row(), last_session=TODAY,
                                        run_date=TODAY, out=out)

    assert out["errors"] == 0 and len(written) == 1
    f = written[0]
    assert f["entry_status"] == "filled" and f["entry_price"] == pytest.approx(10.5)
    assert f["stop_price"] == pytest.approx(8.5)
    assert f["outcome"] == "settled"
    assert f["realized_r"] == pytest.approx(-1.0)
    assert f["meets_4r"] is False and f["meets_positive"] is False
    assert f["gap_band"] == "7_8"
    assert f["admission_era"] == rule_eras.admission_era_as_of(SESSION_DATE)
    assert f["replay_exit_era"] == rule_eras.exit_era_label(TODAY)
    assert f["submit_time_et"] == time(9, 31)
    assert out["settled"] == 1 and out["written"] == 1


@pytest.mark.asyncio
async def test_still_open_position_is_written_not_dropped_survivorship_fix():
    day0 = [_m(9, 30, 10.0, 10.5, 9.5, 10.3),
           _m(9, 31, 10.3, 10.4, 10.2, 10.35),
           _m(9, 32, 10.4, 10.6, 10.3, 10.55),
           _m(9, 33, 10.55, 10.6, 10.5, 10.58)]     # never approaches the 8.5 stop
    sessions = [(SESSION_DATE + timedelta(days=1), {"o": 10.6, "h": 10.7, "l": 10.55, "c": 10.65})]
    calls = []

    async def _fake_upsert(fields):
        calls.append(dict(fields))
        return True

    with patch.object(gnm, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS)), \
        patch.object(gnm, "get_intraday_bars_window", AsyncMock(return_value=day0)), \
        patch.object(gnm.lfc, "_assemble_sessions", AsyncMock(return_value=sessions)), \
        patch.object(gnm, "upsert_gap_near_miss_replay", _fake_upsert):
        out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
              "pending": 0, "errors": 0, "candidates": 0, "written": 0}
        await gnm._record_one_near_miss(conn=object(), row=_pop_row(), last_session=TODAY,
                                        run_date=TODAY, out=out)

    assert out["errors"] == 0
    assert len(calls) == 1, "an open, still-running walk must be WRITTEN, not skipped"
    f = calls[0]
    assert f["outcome"] == "open"
    assert f["mark_r"] is not None
    stop, entry = 8.5, 10.5
    expected_mark = (10.65 - entry) / (entry - stop)
    assert f["mark_r"] == pytest.approx(expected_mark)
    assert out["open"] == 1


@pytest.mark.asyncio
async def test_orb_invalid_writes_no_trade_and_never_walks():
    """A zero-range ORB bar (open==high==low==close) must never simulate an entry."""
    day0 = [_m(9, 30, 10.0, 10.0, 10.0, 10.0), _m(9, 31, 10.0, 10.0, 10.0, 10.0)]
    written = []

    async def _fake_upsert(fields):
        written.append(dict(fields))
        return True

    with patch.object(gnm, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS)), \
        patch.object(gnm, "get_intraday_bars_window", AsyncMock(return_value=day0)), \
        patch.object(gnm.lfc, "_assemble_sessions", AsyncMock(return_value=[])), \
        patch.object(gnm, "upsert_gap_near_miss_replay", _fake_upsert):
        out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
              "pending": 0, "errors": 0, "candidates": 0, "written": 0}
        await gnm._record_one_near_miss(conn=object(), row=_pop_row(), last_session=TODAY,
                                        run_date=TODAY, out=out)

    assert out["errors"] == 0 and len(written) == 1
    assert written[0]["outcome"] == "no_trade" and written[0]["entry_status"] == "orb_invalid"
    assert out["no_trade"] == 1


@pytest.mark.asyncio
async def test_split_adjusted_daily_row_is_abstained_never_walked():
    """Step 1 §7 item 3 (LGCL: $118.94 in the capture, traded $0.95 on the day). A candidate
    whose mi_daily_closes row was retroactively split-adjusted (prev_close/open_price ~100x
    the RAW price mi_intraday_bars actually printed) must be abstained BEFORE the walk —
    never priced in cents against a $100+ adjusted open (the R-inflation class that produced
    Step 1's phantom MIN_PREV_CLOSE 'winners')."""
    day0 = [_m(9, 30, 1.075, 1.10, 1.05, 1.08),   # the REAL raw 09:30 print, ~100x smaller
           _m(9, 31, 1.08, 1.09, 1.07, 1.085)]
    # the daily row's ADJUSTED open (107.5, ~100x the raw 09:30 print above) — the LGCL shape
    row = _pop_row(prev_close=100.0, open_gap_pct=7.5, open_price=107.5)
    written = []

    async def _fake_upsert(fields):
        written.append(dict(fields))
        return True

    with patch.object(gnm, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS)), \
        patch.object(gnm, "get_intraday_bars_window", AsyncMock(return_value=day0)), \
        patch.object(gnm.lfc, "_assemble_sessions", AsyncMock(return_value=[])), \
        patch.object(gnm, "upsert_gap_near_miss_replay", _fake_upsert):
        out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
              "pending": 0, "errors": 0, "candidates": 0, "written": 0}
        await gnm._record_one_near_miss(conn=object(), row=row, last_session=TODAY,
                                        run_date=TODAY, out=out)

    assert out["errors"] == 0 and len(written) == 1
    assert written[0]["outcome"] == "unscoreable"
    assert written[0]["entry_status"] == "daily_row_split_adjusted"
    assert written[0]["entry_price"] is None            # never walked
    assert out["unscoreable"] == 1


@pytest.mark.asyncio
async def test_ordinary_feed_noise_under_five_percent_is_not_flagged_as_a_split():
    """A few-percent difference between the daily row's open and the raw 09:30 print is
    ordinary cross-feed noise, not a split — must NOT be abstained on that basis alone."""
    day0 = [_m(9, 30, 10.2, 10.5, 9.5, 10.3),      # raw open 10.2 vs daily row's 10.0 (2%)
           _m(9, 31, 10.3, 10.4, 10.2, 10.35),
           _m(9, 32, 10.4, 10.6, 10.3, 10.55),
           _m(9, 33, 10.5, 10.55, 8.0, 8.2)]
    row = _pop_row(open_price=10.0)                              # 2% off the raw 10.2 open
    written = []

    async def _fake_upsert(fields):
        written.append(dict(fields))
        return True

    with patch.object(gnm, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS)), \
        patch.object(gnm, "get_intraday_bars_window", AsyncMock(return_value=day0)), \
        patch.object(gnm.lfc, "_assemble_sessions", AsyncMock(return_value=[])), \
        patch.object(gnm, "upsert_gap_near_miss_replay", _fake_upsert):
        out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
              "pending": 0, "errors": 0, "candidates": 0, "written": 0}
        await gnm._record_one_near_miss(conn=object(), row=row, last_session=TODAY,
                                        run_date=TODAY, out=out)

    assert out["errors"] == 0 and len(written) == 1
    assert written[0]["entry_status"] != "daily_row_split_adjusted"


@pytest.mark.asyncio
async def test_no_day0_bars_is_unscoreable_never_guessed():
    written = []

    async def _fake_upsert(fields):
        written.append(dict(fields))
        return True

    with patch.object(gnm, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS)), \
        patch.object(gnm, "get_intraday_bars_window", AsyncMock(return_value=[])), \
        patch.object(gnm.lfc, "_assemble_sessions", AsyncMock(return_value=[])), \
        patch.object(gnm, "upsert_gap_near_miss_replay", _fake_upsert):
        out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
              "pending": 0, "errors": 0, "candidates": 0, "written": 0}
        await gnm._record_one_near_miss(conn=object(), row=_pop_row(), last_session=TODAY,
                                        run_date=TODAY, out=out)

    assert written[0]["outcome"] == "unscoreable"
    assert written[0]["entry_status"] == "no_day0_minute_bars"
    assert out["unscoreable"] == 1


@pytest.mark.asyncio
async def test_run_skips_terminal_rows_and_revisits_open_ones():
    rows = [_pop_row("NEWX"), _pop_row("OPENX"), _pop_row("DONEX")]
    existing = {("OPENX", SESSION_DATE): "open", ("DONEX", SESSION_DATE): "settled"}
    processed = []

    async def _fake_record(conn, row, last_session, run_date, out):
        processed.append(row["ticker"])

    with patch.object(gnm, "get_gap_near_miss_population", AsyncMock(return_value=rows)), \
        patch.object(gnm, "get_gap_near_miss_existing", AsyncMock(return_value=existing)), \
        patch.object(gnm, "get_pool", _fake_pool_getter()), \
        patch.object(gnm, "_record_one_near_miss", _fake_record):
        out = await gnm.run_gap_near_miss_replay(TODAY, now_et=datetime(2026, 9, 3, 18, 14, tzinfo=_ET))

    assert set(processed) == {"NEWX", "OPENX"}
    assert "DONEX" not in processed
    assert out["population"] == 3


@pytest.mark.asyncio
async def test_one_candidates_failure_is_isolated_and_counted():
    rows = [_pop_row("BAD"), _pop_row("GOOD")]

    async def _fake_record(conn, row, last_session, run_date, out):
        if row["ticker"] == "BAD":
            raise RuntimeError("boom")
        out["settled"] += 1
        out["written"] += 1

    with patch.object(gnm, "get_gap_near_miss_population", AsyncMock(return_value=rows)), \
        patch.object(gnm, "get_gap_near_miss_existing", AsyncMock(return_value={})), \
        patch.object(gnm, "get_pool", _fake_pool_getter()), \
        patch.object(gnm, "log_audit_event", AsyncMock()) as mock_audit, \
        patch.object(gnm, "_record_one_near_miss", _fake_record):
        out = await gnm.run_gap_near_miss_replay(TODAY, now_et=datetime(2026, 9, 3, 18, 14, tzinfo=_ET))

    assert out["errors"] == 1 and out["settled"] == 1 and out["written"] == 1
    assert any("gap_near_miss_replay_error" in c.args for c in mock_audit.call_args_list)


@pytest.mark.asyncio
async def test_a_broken_population_query_never_raises():
    with patch.object(gnm, "get_gap_near_miss_population", AsyncMock(side_effect=RuntimeError("db down"))), \
        patch.object(gnm, "log_audit_event", AsyncMock()) as mock_audit:
        out = await gnm.run_gap_near_miss_replay(TODAY, now_et=datetime(2026, 9, 3, 18, 14, tzinfo=_ET))
    assert out["errors"] == 1
    assert any("gap_near_miss_replay_error" in c.args for c in mock_audit.call_args_list)


# ── Registration / schema / boundary ───────────────────────────────────────────────────


def test_nothing_live_imports_the_recorder():
    """No module under agents/ except the scheduler (the job registration) may import the
    recorder — comparison telemetry only."""
    importers = []
    for py in sorted((_REPO / "agents").rglob("*.py")):
        if py == _MODULE:
            continue
        if re.search(r"^\s*(from|import)\s+[\w.]*gap_near_miss_replay\b", py.read_text(), re.M):
            importers.append(str(py.relative_to(_REPO)))
    assert importers == ["agents/market_intelligence/scheduler.py"], importers
    for py in (_REPO / "agents" / "market_intelligence").rglob("*.py"):
        if py.name in ("db.py", "health_checks.py", "gap_near_miss_replay.py"):
            continue
        assert "mi_gap_near_miss_replays" not in py.read_text(), py.relative_to(_REPO)


def test_recorder_imports_no_broker_module():
    src = _MODULE.read_text()
    import_lines = [l for l in src.splitlines() if re.match(r"\s*(from|import)\s", l)]
    for banned in ("broker", "alpaca_client", "order_manager", "live_tracker",
                  "entry_pipeline", "execution_client", "telegram", "briefing"):
        assert not any(banned in l for l in import_lines), banned


def test_it_never_touches_min_gap_pct_it_only_reads_it():
    """This module observes universe admission; it must never assign to (only import) the
    live gap floor or the two D-1 floors."""
    src = _MODULE.read_text()
    assert re.search(r"^\s*(MIN_GAP_PCT|MIN_PREV_CLOSE|MIN_PREV_DAY_VOLUME)\s*=", src, re.M) is None
    assert "ep_detector import" in src


def test_registrations_job_liveness_preflight_schema():
    from agents.market_intelligence import scheduler as sched, health_checks as hc
    import scripts.preflight_db_updates as pf
    assert "gap_near_miss_replay" in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert "gap_near_miss_replay" not in sched.EXECUTION_OWNED_JOB_IDS
    assert any(t[0] == "mi_gap_near_miss_replays" and t[2] == "settled_session"
              for t in hc._DETECTOR_LIVENESS_TABLES)
    assert any(sql is db.GAP_NEAR_MISS_REPLAY_UPSERT_SQL for _, sql in pf.SHADOW_WRITER_STATEMENTS)
    src = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()
    block = re.search(r"CREATE TABLE IF NOT EXISTS mi_gap_near_miss_replays \((.*?)\n\s*\);",
                      src, re.S).group(1)
    assert "UNIQUE (ticker, session_date)" in block
    for col in db.GAP_NEAR_MISS_REPLAY_COLS:
        assert re.search(rf"^\s*{col}\s+", block, re.M), f"column {col} missing from CREATE"
    assert "mi_gap_near_miss_replays" not in (_REPO / "scripts" / "exec_loaded_modules.txt").read_text()
    assert "gap_near_miss_replay" not in (_REPO / "scripts" / "exec_loaded_modules.txt").read_text()


def test_upsert_sql_guards_terminal_rows_and_binds_two_jsonb_params():
    sql = db.GAP_NEAR_MISS_REPLAY_UPSERT_SQL
    assert "ON CONFLICT (ticker, session_date) DO UPDATE SET" in sql
    assert "WHERE mi_gap_near_miss_replays.outcome = 'open'" in sql
    assert sql.count("::jsonb") == 2


@pytest.mark.asyncio
async def test_purge_old_data_never_deletes_the_replay_table():
    from unittest.mock import MagicMock

    executed = []

    async def fake_execute(sql, *a):
        executed.append(sql)
        return "DELETE 0"

    conn = MagicMock()
    conn.execute = fake_execute
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch.object(db, "get_pool", AsyncMock(return_value=pool)):
        await db.purge_old_data()
    assert executed and not any("mi_gap_near_miss_replays" in s for s in executed)


def test_gated_review_carries_the_operator_set_rate_and_its_evidence():
    """The threshold is the OPERATOR's, set 2026-09-03, and it must stay auditable.

    This test previously pinned the OPPOSITE — that no rate was embedded — because when the
    recorder was built the number had not been ruled on and inventing one would have been the
    agent picking a live-adjacent threshold for him. He then ruled: >=5% of DECIDED names
    reaching >=4R, with >=100 decided. Both halves are backed by measurement, and the predicate
    carries that evidence inline so a future reader cannot mistake it for a round number
    somebody liked:
      * background >=4R rate in ANY gap band is ~1.5% (6-7%: 5/290; 5-6%: 6/490), so a lower
        bar fires on noise;
      * the 8-9% band loses -0.24R per settled name, so at 4R a winner you need about 1 in 17
        (6%) merely to break even on admitting it.
    5% is four times background and just under break-even: it fires BEFORE the band is worth
    admitting rather than after.
    """
    import yaml
    reg = yaml.safe_load((_REPO / "data_gated_reviews.yaml").read_text())
    entries = reg["reviews"] if isinstance(reg, dict) else reg
    e = next(x for x in entries if x.get("review_id") == "gap_near_miss_tradeable_miss_rate_617")
    assert e["kind"] == "accrual" and e["status"] == "pending"
    sql = e["predicate_sql"]
    # YAML block scalars re-wrap, so compare on whitespace-collapsed text rather than the
    # author's line breaks — an assertion that depends on formatting fails for the wrong reason.
    flat = " ".join(sql.split())
    assert "to_regclass('mi_gap_near_miss_replays')" in sql
    assert e["threshold"] == 1, "the predicate returns ready/not-ready, so the threshold is 1"

    # the rate, expressed as integer arithmetic so no float rounding decides a live-adjacent gate
    assert "20 * COUNT(*) FILTER (WHERE reached_4r)" in flat, "the 5% rate gate is gone"
    assert ">= 100" in flat, "the minimum sample is gone — one lucky name would trip 5%"

    # the evidence must travel WITH the number
    for token in ("OPERATOR-SET", "1.5%", "-0.24R", "break even"):
        assert token.lower() in flat.lower(), (
            f"the predicate no longer records why the threshold is what it is: {token}")

    assert "mi_gap_near_miss_replays.gap_band" in e["discriminates_on"]
    assert "mi_gap_near_miss_replays.admission_era" in e["discriminates_on"]
