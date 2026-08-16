"""2026-08-15 capture audit, items 1-3 + the disk-growth guard.

WHY THIS EXISTS. The alert flow ends with earnings season, and the capture layer was
quietly destroying its own evidence: `mi_ep_alerts` purged at 90d (the 08-04..08-09
earnings window would have deleted 2026-11-08 — the week a next-quarter comparison
test begins), `mi_intraday_bars` purged at 120d (this quarter's minute paths die
12-06), and minute bars were only written for names we took a position in — 43 of 98
alert ticker-days since 07-28 (44%), so skips and moderates (the plan's own outcome
unit) had no stored intraday path.

Three changes pinned here:
  1. `purge_old_data` EXEMPTS mi_ep_alerts (kept forever) — a DELETE against it is a
     regression (also asserted in test_recent_changes.TestPurgeOldData).
  2. `mi_intraday_bars` retention 120d → 1825d (5 years).
  3. `order_manager.persist_alert_day_paths` — EOD persist of day-of minute bars for
     EVERY alert ticker-day: mi_ep_alerts UNION the day's ep_rt_universe_catch audit
     rows; already-covered names skip without an API call; thin days log
     `path_coverage_gap`; one bad name never kills the day's capture.
Plus the guard the retention relaxation was conditioned on:
  4. `health_checks.run_db_growth_check` / `_evaluate_db_growth` — nightly audit row
     of DB size + largest tables, Telegram ONLY when pro-rated weekly growth is ~10x
     the planned ~30 MB/wk or total size crosses the ceiling. A guard that always
     fires is not a guard.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import make_mock_pool
from agents.market_intelligence import health_checks as hc
from agents.market_intelligence.broker import order_manager as om

_ET = ZoneInfo("America/New_York")
_DAY = date(2026, 8, 14)


# ── persist_alert_day_paths (item 3) ─────────────────────────────────────────────


def _wire_om(monkeypatch, *, population_rows, bar_counts, fetched_bars):
    """Wire order_manager's pool + alpaca + audit log for persist_alert_day_paths.

    `bar_counts`: dict ticker -> existing mi_intraday_bars count for the day.
    `fetched_bars`: dict ticker -> list of bars get_minute_bars_range returns.
    Returns (calls, persisted, logged, conn) recorders.
    """
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=population_rows)

    async def _fetchval(sql, ticker, *a):
        return bar_counts.get(ticker, 0)
    conn.fetchval = _fetchval

    async def _pool():
        return pool
    monkeypatch.setattr(om, "get_pool", _pool)

    calls, persisted, logged = [], [], []

    async def _get_range(ticker, start, end):
        calls.append((ticker, start, end))
        if isinstance(fetched_bars.get(ticker), Exception):
            raise fetched_bars[ticker]
        return fetched_bars.get(ticker, [])

    async def _persist(ticker, bars):
        persisted.append((ticker, len(bars)))

    monkeypatch.setattr(om.alpaca, "get_minute_bars_range", _get_range)
    monkeypatch.setattr(om.alpaca, "persist_intraday_bars", _persist)

    async def _log(event_type, summary, detail=""):
        logged.append((event_type, summary))
    monkeypatch.setattr(om, "log_audit_event", _log)
    return calls, persisted, logged, conn


def _full_day(ticker):
    """390 bars — a full RTH day."""
    base = datetime(2026, 8, 14, 9, 30, tzinfo=_ET)
    return [{"t_et": base + timedelta(minutes=i), "open": 1, "high": 1, "low": 1,
             "close": 1, "volume": 100, "vwap": None} for i in range(390)]


def test_population_is_alerts_union_rt_catches(monkeypatch):
    """The audit's population, verbatim: mi_ep_alerts (skips/moderates included — they are
    rows in that table) UNION the day's rt-catch audit tickers. Dropping either half is
    the 44%-coverage failure this function exists to close."""
    rows = [{"ticker": "AAA"}, {"ticker": "BBB"}, {"ticker": None}]
    calls, persisted, _, conn = _wire_om(
        monkeypatch, population_rows=rows, bar_counts={},
        fetched_bars={"AAA": _full_day("AAA"), "BBB": _full_day("BBB")})
    out = asyncio.run(om.persist_alert_day_paths(target_date=_DAY))
    assert out["population"] == 2                      # None ticker filtered
    assert sorted(t for t, _, _ in calls) == ["AAA", "BBB"]
    assert sorted(persisted) == [("AAA", 390), ("BBB", 390)]
    assert out["fetched"] == 2 and out["errors"] == 0

    # The population SQL actually SENT to the DB must read BOTH sources — the union
    # is the point (behavioral, not source-text: a docstring mentioning the event
    # name must not be able to satisfy this — caught by mutation testing 2026-08-15).
    population_sql = conn.fetch.call_args[0][0]
    assert "mi_ep_alerts" in population_sql
    assert "ep_rt_universe_catch" in population_sql
    assert "UNION" in population_sql


def test_already_covered_names_skip_without_api_call(monkeypatch):
    """Traded names were already recorded by #306 — refetching them would double the
    API budget for nothing. >= _PATH_MIN_DAY_BARS existing bars -> no fetch."""
    rows = [{"ticker": "COVERED"}, {"ticker": "MISSING"}]
    calls, persisted, _, _c = _wire_om(
        monkeypatch, population_rows=rows,
        bar_counts={"COVERED": om._PATH_MIN_DAY_BARS},
        fetched_bars={"MISSING": _full_day("MISSING")})
    out = asyncio.run(om.persist_alert_day_paths(target_date=_DAY))
    assert [t for t, _, _ in calls] == ["MISSING"]
    assert out["already_covered"] == 1 and out["fetched"] == 1


def test_thin_day_logs_coverage_gap_audit_only(monkeypatch):
    """A halted/illiquid name returning few bars is recorded as a path_coverage_gap
    audit row (the #306 sweep's idiom) — never a Telegram."""
    rows = [{"ticker": "THIN"}]
    _, persisted, logged, _c = _wire_om(
        monkeypatch, population_rows=rows, bar_counts={},
        fetched_bars={"THIN": _full_day("THIN")[:40]})
    out = asyncio.run(om.persist_alert_day_paths(target_date=_DAY))
    assert persisted == [("THIN", 40)]                 # partial data still kept
    assert out["thin"] == 1
    assert any(ev == "path_coverage_gap" and "THIN" in s for ev, s in logged)


def test_one_bad_name_does_not_kill_the_days_capture(monkeypatch):
    rows = [{"ticker": "BAD"}, {"ticker": "GOOD"}]
    _, persisted, _, _c = _wire_om(
        monkeypatch, population_rows=rows, bar_counts={},
        fetched_bars={"BAD": RuntimeError("api down"),
                      "GOOD": _full_day("GOOD")})
    out = asyncio.run(om.persist_alert_day_paths(target_date=_DAY))
    assert ("GOOD", 390) in persisted
    assert out["errors"] == 1 and out["fetched"] == 1


def test_fetch_window_is_930_to_1600_et(monkeypatch):
    """The stored path must match the recorder's boundary (through 16:00, never
    after-hours prints) so alert-day rows stay comparable with traded-day rows."""
    rows = [{"ticker": "AAA"}]
    calls, _, _, _c = _wire_om(monkeypatch, population_rows=rows, bar_counts={},
                           fetched_bars={"AAA": _full_day("AAA")})
    asyncio.run(om.persist_alert_day_paths(target_date=_DAY))
    (_, start, end), = calls
    assert (start.hour, start.minute) == (9, 30)
    assert (end.hour, end.minute) == (16, 0)
    assert start.tzinfo is not None and end.tzinfo is not None


def test_scheduler_registers_alert_day_path_persist_as_execution_owned():
    """The job needs Alpaca data creds, which live ONLY in apollo-execution — an
    unclassified or intelligence-routed registration is the silent-dark class the
    W2 partition guards exist for."""
    from agents.market_intelligence import scheduler as sched
    assert "alert_day_path_persist" in sched.EXECUTION_OWNED_JOB_IDS
    import inspect
    src = inspect.getsource(sched.start_scheduler)
    assert 'id="alert_day_path_persist"' in src


# ── _evaluate_db_growth: the pure decision (the guard's noise calibration) ───────

_MB = 1024 ** 2
_GB = 1024 ** 3


def test_no_baseline_is_silent():
    assert hc._evaluate_db_growth(2 * _GB, None, None) is None


def test_on_plan_growth_is_silent():
    """Planned rate is ~30 MB/wk — the guard must NOT fire on the retention plan it
    was shipped alongside, or it becomes wallpaper and gets muted."""
    assert hc._evaluate_db_growth(int(1.2 * _GB) + 35 * _MB, int(1.2 * _GB), 7.0) is None


def test_out_of_line_weekly_growth_speaks():
    flag = hc._evaluate_db_growth(int(1.2 * _GB) + 400 * _MB, int(1.2 * _GB), 7.0)
    assert flag is not None and flag["kind"] == "growth"
    assert flag["weekly_growth_bytes"] > hc._DB_GROWTH_ALERT_BYTES


def test_growth_is_pro_rated_not_absolute():
    """400 MB over six weeks is ~67 MB/wk — on-plan-ish, must stay silent. The same
    400 MB over one week fires (previous test). Removing the pro-rating makes these
    two cases indistinguishable."""
    assert hc._evaluate_db_growth(int(1.2 * _GB) + 400 * _MB, int(1.2 * _GB), 42.0) is None


def test_ceiling_speaks_regardless_of_rate():
    flag = hc._evaluate_db_growth(hc._DB_SIZE_CEILING_BYTES + 1, None, None)
    assert flag is not None and flag["kind"] == "ceiling"


def test_stale_baseline_is_silent():
    """A baseline older than the max age (long downtime) is not evidence — measure,
    re-arm, stay silent rather than alert off a months-old comparison."""
    age = hc._DB_GROWTH_MAX_BASELINE_AGE_DAYS + 10.0
    assert hc._evaluate_db_growth(3 * _GB, 1 * _GB, age) is None


# ── run_db_growth_check: recording + announce/dedupe wiring ──────────────────────


def _wire_hc(monkeypatch, *, db_bytes, tables, baseline_row, dedupe_count=0):
    pool, conn = make_mock_pool()

    async def _fetchval(sql, *a):
        if "pg_database_size" in sql:
            return db_bytes
        return dedupe_count                            # the db_growth_alert dedupe read
    conn.fetchval = _fetchval
    conn.fetch = AsyncMock(return_value=[{"t": k, "b": v} for k, v in tables.items()])
    conn.fetchrow = AsyncMock(return_value=baseline_row)

    async def _pool():
        return pool
    monkeypatch.setattr(hc, "get_pool", _pool)

    logged, sent = [], []

    async def _log(event_type, summary, detail=""):
        logged.append((event_type, summary, detail))
    monkeypatch.setattr(hc, "log_audit_event", _log)

    import agents.market_intelligence.briefing as briefing

    async def _send(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    return logged, sent


def test_first_run_records_baseline_and_stays_silent(monkeypatch):
    logged, sent = _wire_hc(monkeypatch, db_bytes=int(1.2 * _GB),
                            tables={"mi_daily_closes": 550 * _MB},
                            baseline_row=None)
    out = asyncio.run(hc.run_db_growth_check())
    assert out["flag"] is None and sent == []
    # the measurement row must ALWAYS be written — it is next week's baseline
    assert [e for e, _, _ in logged] == ["db_growth_check"]
    payload = json.loads(logged[0][2])
    assert payload["db_bytes"] == int(1.2 * _GB)
    assert payload["tables"]["mi_daily_closes"] == 550 * _MB


def _baseline_row(db_bytes, age_days, tables=None):
    return {"created_at": datetime.now(_ET) - timedelta(days=age_days),
            "detail": json.dumps({"db_bytes": db_bytes, "tables": tables or {}})}


def test_out_of_line_growth_sends_one_telegram_and_alert_row(monkeypatch):
    logged, sent = _wire_hc(
        monkeypatch, db_bytes=int(1.2 * _GB) + 500 * _MB,
        tables={"mi_intraday_bars": 560 * _MB},
        baseline_row=_baseline_row(int(1.2 * _GB), 7.0,
                                   tables={"mi_intraday_bars": 68 * _MB}))
    out = asyncio.run(hc.run_db_growth_check())
    assert out["flag"] is not None and out["flag"]["kind"] == "growth"
    assert len(sent) == 1 and "mi_intraday_bars" in sent[0]
    assert [e for e, _, _ in logged] == ["db_growth_check", "db_growth_alert"]


def test_persisting_condition_is_deduped_to_weekly(monkeypatch):
    """The ceiling condition persists forever once crossed — without the dedupe this
    would fire nightly and become wallpaper (the muted-guard failure mode)."""
    logged, sent = _wire_hc(
        monkeypatch, db_bytes=hc._DB_SIZE_CEILING_BYTES + 1,
        tables={}, baseline_row=None, dedupe_count=1)
    out = asyncio.run(hc.run_db_growth_check())
    assert out["flag"] is not None and out["flag"]["kind"] == "ceiling"
    assert sent == []                                   # suppressed by the recent alert row
    assert [e for e, _, _ in logged] == ["db_growth_check"]  # measurement still recorded


def test_nightly_audit_wires_the_growth_check():
    from agents.market_intelligence import scheduler as sched
    import inspect
    src = inspect.getsource(sched._post_nightly_audit_job)
    assert "run_db_growth_check" in src


def test_alert_day_path_population_includes_consolidation_entries():
    """2026-08-16: the minute-path job must also cover Family A entry days.

    Audited 08-16: `mi_consolidation_entry_shadow` carries realized_r/fwd_mfe_r and is
    fine for DAILY eval, but 0 of 294 entry dates had minute bars — so no
    stop-placement, intraday-shakeout or entry-timing study could run on consolidation,
    which are exactly the analyses that produced the weekend's EP findings. The tactics
    transfer between setups, so the capture must too.

    MUTATION-PROVEN: drop the UNION and this fails.
    """
    import inspect
    from agents.market_intelligence.broker import order_manager

    src = inspect.getsource(order_manager.persist_alert_day_paths)
    # ⚠ assert on the SQL STATEMENT, not on any mention of the table — the explanatory
    # comment above the line also contains the table name, so a name-only assertion
    # passes with the query removed. (Caught by mutation: the first version of this
    # test passed both ways, which makes it not a test.)
    assert "FROM mi_consolidation_entry_shadow WHERE entry_date" in src, (
        "consolidation entry days dropped from the alert-day minute-path population")
    assert src.count("UNION") >= 2, "consolidation must be UNIONed into the population query"
