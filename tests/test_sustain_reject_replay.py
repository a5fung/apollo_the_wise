"""#593 (2026-09-03) sustain-reject bracket replay tests.

Pure compute (entry_walk / _stop_limit_buy_price / submit_time_and_window /
entry_cancel_asof / current_era_stop / old_basis_breaches / mark_pnl_per_share /
n_trading_days_back) + orchestration against mocked db/lfc calls (no real DB — the build
session has no prod access; these prove the WIRING, not a live number).

THE LINE — the properties this file proves at the code layer:
  1. NOTHING LIVE READS IT: no module under agents/ except the scheduler imports the recorder.
  2. TOTAL FAILURE: one candidate raising is counted and audited; the others proceed.
  3. SURVIVORSHIP: a still-open walk is WRITTEN (not dropped) with a mark-to-market mark_r,
     and the guarded UPSERT only refreshes an 'open' row, never a terminal one.
  4. SUBMIT TIME comes from the reject's own tick, never a fixed 09:31.
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
from agents.market_intelligence import rule_eras
from agents.market_intelligence import sustain_reject_replay as srr

_ET = ZoneInfo("America/New_York")
_REPO = Path(__file__).resolve().parent.parent
_MODULE = _REPO / "agents" / "market_intelligence" / "sustain_reject_replay.py"

DECLINE_DATE = date(2026, 8, 20)   # Thursday, era C, a real NYSE trading day
TODAY = date(2026, 9, 3)


@pytest.fixture(autouse=True)
def _real_orb_validation(monkeypatch):
    """tests/conftest.py stubs agents.market_intelligence.backtester.filters with
    MagicMocks (the real module drags heavy deps into the test env), so the recorder's
    imported validate_orb_entry is a mock under pytest. Patch in a faithful copy of the
    real contract (backtester/filters.py::validate_orb_entry — zero-range reject, range >
    1.5x ATR reject) so these tests exercise real admission behaviour — the SAME fixture
    tests/test_ep_replay.py uses for the same reason."""
    def _validate(orb_high, orb_low, atr_14):
        orb_range = orb_high - orb_low
        if orb_range <= 0:
            return False, "setup:zero_range"
        if atr_14 and atr_14 > 0 and orb_range > 1.5 * atr_14:
            return False, f"setup:stop_too_wide: {orb_range:.2f} > 1.5x ATR {atr_14:.2f}"
        return True, None
    monkeypatch.setattr(srr, "validate_orb_entry", _validate)


def _m(hh, mm, o, h, l, c, d=DECLINE_DATE):
    return {"m": datetime(d.year, d.month, d.day, hh, mm, tzinfo=_ET), "o": o, "h": h, "l": l, "c": c}


def _daily_row(d, o, h, l, c, v):
    return {"trade_date": d, "open_price": o, "high_price": h, "low_price": l, "close": c, "volume": v}


PRIOR_ROWS = [_daily_row(DECLINE_DATE - timedelta(days=i), 10.0, 10.6, 9.4, 10.0, 1_000_000)
             for i in range(15, 0, -1)]
D0_ROW = _daily_row(DECLINE_DATE, 10.0, 10.6, 8.0, 8.2, 10_000_000)


# ── Pure compute ────────────────────────────────────────────────────────────────────────


def test_stop_limit_buy_price_matches_order_manager_two_floor_formula():
    assert srr._stop_limit_buy_price(100.0) == pytest.approx(100.5)     # 0.5% buffer wins
    assert srr._stop_limit_buy_price(1.00) == pytest.approx(1.02)       # $0.02 floor wins
    assert srr._stop_limit_buy_price(5.49) == pytest.approx(5.52)       # matches the docstring's own worked example (rounded to the cent)


def test_entry_walk_intrabar_cross_fills_at_orb_high():
    bars = [_m(9, 30, 10.0, 10.5, 9.5, 10.3), _m(9, 32, 10.4, 10.6, 10.3, 10.55)]
    fill = srr.entry_walk(bars, 10.5, time(9, 32), time(10, 0))
    assert fill == {"status": "filled", "px": 10.5, "minute": bars[1]["m"]}


def test_entry_walk_open_above_limit_arms_then_fills_at_the_limit():
    bars = [_m(9, 32, 11.0, 11.2, 10.9, 11.0), _m(9, 33, 11.0, 11.1, 10.5, 10.9)]
    # limit = _stop_limit_buy_price(10.5) = 10.552; bar0 opens (11.0) above orb_high AND
    # above the limit -> armed, not filled at the open; bar1's low 10.5 <= limit -> fills there.
    fill = srr.entry_walk(bars, 10.5, time(9, 32), time(10, 0))
    assert fill["status"] == "filled"
    assert fill["px"] == pytest.approx(srr._stop_limit_buy_price(10.5))
    assert fill["minute"] == bars[1]["m"]


def test_entry_walk_no_entry_with_full_window_coverage():
    submit, cancel = time(9, 31), time(9, 33)
    bars = [_m(9, 31, 10.0, 10.1, 9.9, 10.0), _m(9, 32, 10.0, 10.2, 9.9, 10.1)]  # never reaches 10.5
    fill = srr.entry_walk(bars, 10.5, submit, cancel)
    assert fill == {"status": "no_entry", "reason": "never_crossed_orb_high"}


def test_entry_walk_abstains_on_a_gapped_window():
    submit, cancel = time(9, 31), time(9, 40)     # 9 minutes expected
    bars = [_m(9, 31, 10.0, 10.1, 9.9, 10.0)]      # only 1 of 9 minutes present
    fill = srr.entry_walk(bars, 10.5, submit, cancel)
    assert fill["status"] == "abstain" and "entry_window_gaps" in fill["reason"]


def test_entry_walk_is_byte_identical_to_ep_replays_own(monkeypatch):
    """This module's docstring claims entry_walk MIRRORS scripts/ep_replay.entry_walk's
    exact logic rather than a fifth copy. Prove it: same bar sets through both, same result,
    across every branch (intra-bar cross, open-above-limit-armed, no_entry, abstain)."""
    import scripts.ep_replay as ep

    # ep_replay's own validate_orb_entry is a MagicMock under pytest (conftest stub) — not
    # exercised by entry_walk itself, so no patch needed here.
    scenarios = [
        ([_m(9, 30, 10.0, 10.5, 9.5, 10.3), _m(9, 32, 10.4, 10.6, 10.3, 10.55)],
         10.5, time(9, 32), time(10, 0)),
        ([_m(9, 32, 11.0, 11.2, 10.9, 11.0), _m(9, 33, 11.0, 11.1, 10.5, 10.9)],
         10.5, time(9, 32), time(10, 0)),
        ([_m(9, 31, 10.0, 10.1, 9.9, 10.0), _m(9, 32, 10.0, 10.2, 9.9, 10.1)],
         10.5, time(9, 31), time(9, 33)),
        ([_m(9, 31, 10.0, 10.1, 9.9, 10.0)], 10.5, time(9, 31), time(9, 40)),
    ]
    for bars, orb_high, submit, cancel in scenarios:
        assert srr.entry_walk(bars, orb_high, submit, cancel) == ep.entry_walk(bars, orb_high, submit, cancel)


def test_submit_time_floors_up_to_0931_and_keeps_a_later_tick():
    submit, window_out = srr.submit_time_and_window(datetime(2026, 8, 20, 8, 15))
    assert submit == time(9, 31) and window_out is False          # pre-market floors up
    submit, window_out = srr.submit_time_and_window(datetime(2026, 8, 20, 9, 38, 47))
    assert submit == time(9, 38) and window_out is False          # a later tick keeps ITS OWN minute


def test_submit_time_at_or_after_0945_is_window_out_of_orb():
    submit, window_out = srr.submit_time_and_window(datetime(2026, 8, 20, 9, 45, 1))
    assert submit is None and window_out is True


def test_entry_cancel_asof_the_partial_live_switch():
    assert srr.entry_cancel_asof(rule_eras.PARTIAL_LIVE_DATE - timedelta(days=1)) is None
    assert srr.entry_cancel_asof(rule_eras.PARTIAL_LIVE_DATE) == time(10, 0)
    assert srr.entry_cancel_asof(TODAY) == time(10, 0)


def test_current_era_stop_both_modes():
    assert srr.current_era_stop("orb_low", orb_high=10.5, orb_low=9.5) == 9.5
    assert srr.current_era_stop("entry_minus_2r", orb_high=10.5, orb_low=9.5) == pytest.approx(8.5)


def test_old_basis_breaches_mfe_and_settled_close():
    fwd = [(DECLINE_DATE + timedelta(days=1), {"h": 12.0, "c": 11.0}),
          (DECLINE_DATE + timedelta(days=2), {"h": 13.0, "c": 11.5}),
          (DECLINE_DATE + timedelta(days=3), {"h": 10.0, "c": 9.5}),
          (DECLINE_DATE + timedelta(days=4), {"h": 9.0, "c": 8.5}),
          (DECLINE_DATE + timedelta(days=5), {"h": 8.0, "c": 7.9})]     # settled close on d0+5
    declined_level = 10.0
    breach_mfe, breach_settled = srr.old_basis_breaches(11.0, fwd, declined_level)
    assert breach_mfe is True         # peak high 13.0 >= 10 x 1.20 = 12.0
    assert breach_settled is False    # d0+5 close 7.9 < 12.0


def test_old_basis_breaches_settled_is_none_when_d0_plus_5_has_not_happened_yet():
    fwd = [(DECLINE_DATE + timedelta(days=1), {"h": 12.5, "c": 12.0})]   # only 1 forward session so far
    breach_mfe, breach_settled = srr.old_basis_breaches(11.0, fwd, 10.0)
    assert breach_mfe is True          # 12.5 >= 12.0
    assert breach_settled is None      # genuinely unknown yet, not a non-breach


def test_old_basis_breaches_uses_the_daily_high_never_a_minute_bar_high():
    """d0_high is d0's own DAILY high (mi_daily_closes.high_price) — the retired funnel's
    OWN basis. A minute-bar high must never leak in here (that was the pre-fix bug)."""
    breach_mfe, _ = srr.old_basis_breaches(11.9, [], 10.0)
    assert breach_mfe is False     # 11.9 < 10 x 1.20 = 12.0 -- would be True at 12.0+


def test_old_basis_breaches_none_without_a_declined_level():
    assert srr.old_basis_breaches(None, [], None) == (None, None)
    assert srr.old_basis_breaches(11.0, [], None) == (None, None)


def test_mark_pnl_per_share_matches_walk_arms_own_horizon_formula():
    res = {"exits": [{"pnl": 1.0}], "remaining": 2 / 3}
    sessions = [(DECLINE_DATE + timedelta(days=1), {"c": 12.0}),
               (DECLINE_DATE + timedelta(days=2), None)]     # a later gap must not win over the real close
    mark = srr.mark_pnl_per_share(res, [_m(9, 30, 10, 11, 9.5, 10.5)], sessions, entry=10.0)
    assert mark == pytest.approx(1.0 + (12.0 - 10.0) * (2 / 3))


def test_mark_pnl_per_share_falls_back_to_day0_close_with_no_forward_sessions():
    res = {"exits": [], "remaining": 1.0}
    mark = srr.mark_pnl_per_share(res, [_m(9, 30, 10, 11, 9.5, 10.8)], [], entry=10.0)
    assert mark == pytest.approx(0.0 + (10.8 - 10.0) * 1.0)


def test_n_trading_days_back_skips_weekends():
    # 2026-08-20 is a Thursday; 3 trading days back is Monday 2026-08-17 (Fri 08-21 is AFTER
    # the anchor, not before it — walking BACKWARD from Thu: Wed 19, Tue 18, Mon 17).
    assert srr.n_trading_days_back(date(2026, 8, 20), 3) == date(2026, 8, 17)


# ── Orchestration (mocked db + lfc — no real DB in this sandbox) ──────────────────────


def _pop_row(ticker="ABCD", decline_date=DECLINE_DATE, rt_gap=15.0, tick=datetime(2026, 8, 20, 9, 32)):
    return {"ticker": ticker, "decline_date": decline_date, "rt_gap": rt_gap, "decline_ts_et": tick}


def _fake_pool_getter():
    """A minimal `get_pool` replacement whose acquire() yields a placeholder conn — used
    only by tests that mock `_record_one_reject` itself and never touch conn for real."""
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

    with patch.object(srr, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS + [D0_ROW])), \
        patch.object(srr, "get_intraday_bars_window", AsyncMock(return_value=day0)), \
        patch.object(srr.lfc, "_assemble_sessions", AsyncMock(return_value=[])), \
        patch.object(srr, "upsert_sustain_reject_replay", _fake_upsert):
        out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
              "pending": 0, "errors": 0, "candidates": 0, "written": 0}
        await srr._record_one_reject(conn=object(), row=_pop_row(), last_session=TODAY,
                                     run_date=TODAY, out=out)

    assert out["errors"] == 0 and len(written) == 1
    f = written[0]
    assert f["entry_status"] == "filled" and f["entry_price"] == pytest.approx(10.5)
    assert f["stop_price"] == pytest.approx(8.5)
    assert f["outcome"] == "settled"
    assert f["realized_r"] == pytest.approx(-1.0)
    assert f["meets_4r"] is False and f["meets_positive"] is False
    assert f["admission_era"] == rule_eras.admission_era_as_of(DECLINE_DATE)
    assert f["replay_exit_era"] == rule_eras.exit_era_label(TODAY)
    assert out["settled"] == 1 and out["written"] == 1


@pytest.mark.asyncio
async def test_still_open_position_is_written_not_dropped_survivorship_fix():
    """The walk never hits the stop or target and runs out of AVAILABLE forward sessions —
    walk_arm returns 'pending'/open_walk_not_definitive (NOT a data gap: every session bar
    the sessions list carries is present). The recorder must WRITE this as outcome='open'
    with a mark-to-market mark_r, never silently drop it (the survivorship-bias fix)."""
    day0 = [_m(9, 30, 10.0, 10.5, 9.5, 10.3),
           _m(9, 31, 10.3, 10.4, 10.2, 10.35),
           _m(9, 32, 10.4, 10.6, 10.3, 10.55),
           _m(9, 33, 10.55, 10.6, 10.5, 10.58)]     # never approaches the 8.5 stop
    sessions = [(DECLINE_DATE + timedelta(days=1), {"o": 10.6, "h": 10.7, "l": 10.55, "c": 10.65})]

    async def _fake_upsert(fields):
        _fake_upsert.calls.append(dict(fields))
        return True
    _fake_upsert.calls = []

    with patch.object(srr, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS + [D0_ROW])), \
        patch.object(srr, "get_intraday_bars_window", AsyncMock(return_value=day0)), \
        patch.object(srr.lfc, "_assemble_sessions", AsyncMock(return_value=sessions)), \
        patch.object(srr, "upsert_sustain_reject_replay", _fake_upsert):
        out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
              "pending": 0, "errors": 0, "candidates": 0, "written": 0}
        await srr._record_one_reject(conn=object(), row=_pop_row(), last_session=TODAY,
                                     run_date=TODAY, out=out)

    assert out["errors"] == 0
    assert len(_fake_upsert.calls) == 1, "an open, still-running walk must be WRITTEN, not skipped"
    f = _fake_upsert.calls[0]
    assert f["outcome"] == "open"
    assert f["mark_r"] is not None
    stop, entry = 8.5, 10.5
    expected_mark = (10.65 - entry) / (entry - stop)   # no exits fired; mark-to-market only
    assert f["mark_r"] == pytest.approx(expected_mark)
    assert out["open"] == 1


@pytest.mark.asyncio
async def test_window_out_of_orb_never_simulates_an_entry():
    row = _pop_row(tick=datetime(2026, 8, 20, 9, 46))
    written = []

    async def _fake_upsert(fields):
        written.append(dict(fields))
        return True

    with patch.object(srr, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS + [D0_ROW])), \
        patch.object(srr, "get_intraday_bars_window", AsyncMock()) as mock_bars, \
        patch.object(srr.lfc, "_assemble_sessions", AsyncMock(return_value=[])), \
        patch.object(srr, "upsert_sustain_reject_replay", _fake_upsert):
        out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
              "pending": 0, "errors": 0, "candidates": 0, "written": 0}
        await srr._record_one_reject(conn=object(), row=row, last_session=TODAY,
                                     run_date=TODAY, out=out)

    mock_bars.assert_not_called()      # never even reads minute bars — the window rules it out first
    assert written[0]["outcome"] == "no_trade" and written[0]["entry_status"] == "window_out_of_orb"
    assert out["no_trade"] == 1
    # the OLD-basis columns are populated even on a name our OWN bracket never simulated an
    # entry for — the retired funnel never simulated an entry either (the survivorship-
    # comparability fix): declined_level = 10 x 1.15 = 11.5, d0 daily high 10.6 < 11.5.
    f = written[0]
    assert f["declined_level"] == pytest.approx(11.5)
    assert f["entry_reachable"] is False
    assert f["breach_mfe_20"] is False


@pytest.mark.asyncio
async def test_run_skips_terminal_rows_and_revisits_open_ones():
    rows = [_pop_row("NEWX"), _pop_row("OPENX"), _pop_row("DONEX")]
    existing = {("OPENX", DECLINE_DATE): "open", ("DONEX", DECLINE_DATE): "settled"}
    processed = []

    async def _fake_record(conn, row, last_session, run_date, out):
        processed.append(row["ticker"])

    with patch.object(srr, "get_sustain_reject_population", AsyncMock(return_value=rows)), \
        patch.object(srr, "get_sustain_replay_existing", AsyncMock(return_value=existing)), \
        patch.object(srr, "get_pool", _fake_pool_getter()), \
        patch.object(srr, "_record_one_reject", _fake_record):
        out = await srr.run_sustain_reject_replay(TODAY, now_et=datetime(2026, 9, 3, 18, 13, tzinfo=_ET))

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

    with patch.object(srr, "get_sustain_reject_population", AsyncMock(return_value=rows)), \
        patch.object(srr, "get_sustain_replay_existing", AsyncMock(return_value={})), \
        patch.object(srr, "get_pool", _fake_pool_getter()), \
        patch.object(srr, "log_audit_event", AsyncMock()) as mock_audit, \
        patch.object(srr, "_record_one_reject", _fake_record):
        out = await srr.run_sustain_reject_replay(TODAY, now_et=datetime(2026, 9, 3, 18, 13, tzinfo=_ET))

    assert out["errors"] == 1 and out["settled"] == 1 and out["written"] == 1
    assert any("sustain_reject_replay_error" in c.args for c in mock_audit.call_args_list)


# ── Registration / schema / boundary ───────────────────────────────────────────────────


def test_nothing_live_imports_the_recorder():
    """No module under agents/ except the scheduler (the job registration) may import the
    recorder — comparison telemetry only."""
    importers = []
    for py in sorted((_REPO / "agents").rglob("*.py")):
        if py == _MODULE:
            continue
        if re.search(r"^\s*(from|import)\s+[\w.]*sustain_reject_replay\b", py.read_text(), re.M):
            importers.append(str(py.relative_to(_REPO)))
    assert importers == ["agents/market_intelligence/scheduler.py"], importers
    for py in (_REPO / "agents" / "market_intelligence").rglob("*.py"):
        if py.name in ("db.py", "health_checks.py", "sustain_reject_replay.py"):
            continue
        assert "mi_sustain_reject_replays" not in py.read_text(), py.relative_to(_REPO)


def test_recorder_imports_no_broker_module():
    src = _MODULE.read_text()
    import_lines = [l for l in src.splitlines() if re.match(r"\s*(from|import)\s", l)]
    for banned in ("broker", "alpaca_client", "order_manager", "live_tracker",
                  "entry_pipeline", "execution_client", "telegram", "briefing"):
        assert not any(banned in l for l in import_lines), banned


def test_registrations_job_liveness_preflight_schema():
    from agents.market_intelligence import scheduler as sched, health_checks as hc
    import scripts.preflight_db_updates as pf
    assert "sustain_reject_replay" in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert "sustain_reject_replay" not in sched.EXECUTION_OWNED_JOB_IDS
    assert any(t[0] == "mi_sustain_reject_replays" and t[2] == "settled_session"
              for t in hc._DETECTOR_LIVENESS_TABLES)
    assert any(sql is db.SUSTAIN_REJECT_REPLAY_UPSERT_SQL for _, sql in pf.SHADOW_WRITER_STATEMENTS)
    src = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()
    block = re.search(r"CREATE TABLE IF NOT EXISTS mi_sustain_reject_replays \((.*?)\n\s*\);",
                      src, re.S).group(1)
    assert "UNIQUE (ticker, decline_date)" in block
    for col in db.SUSTAIN_REJECT_REPLAY_COLS:
        assert re.search(rf"^\s*{col}\s+", block, re.M), f"column {col} missing from CREATE"
    assert "mi_sustain_reject_replays" not in (_REPO / "scripts" / "exec_loaded_modules.txt").read_text()
    assert "sustain_reject_replay" not in (_REPO / "scripts" / "exec_loaded_modules.txt").read_text()


def test_upsert_sql_guards_terminal_rows_and_binds_two_jsonb_params():
    sql = db.SUSTAIN_REJECT_REPLAY_UPSERT_SQL
    assert "ON CONFLICT (ticker, decline_date) DO UPDATE SET" in sql
    assert "WHERE mi_sustain_reject_replays.outcome = 'open'" in sql
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
    assert executed and not any("mi_sustain_reject_replays" in s for s in executed)


def test_gated_review_reads_the_stored_replay_and_guards_the_table():
    import yaml
    reg = yaml.safe_load((_REPO / "data_gated_reviews.yaml").read_text())
    entries = reg["reviews"] if isinstance(reg, dict) else reg
    e = next(x for x in entries if x.get("review_id") == "sustain_reject_tradeable_miss_rate_593")
    assert e["threshold"] == 1 and e["status"] == "pending" and e["kind"] == "tripwire"
    assert "to_regclass('mi_sustain_reject_replays')" in e["predicate_sql"]
    assert "mi_sustain_reject_replays" in e["predicate_sql"]
    assert "meets_4r" in e["predicate_sql"] and "mark_meets_4r" in e["predicate_sql"]
    assert "mi_sustain_reject_replays.admission_era" in e["discriminates_on"]
