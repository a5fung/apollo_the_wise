"""PLAN #543 — detector-liveness check (2026-08-16).

WHY THIS EXISTS. The 2026-08-15 review-registry sweep found detectors that produced
nothing for months and nothing told anyone: mi_anticipation_lifecycle (last write
2026-06-16, the #270 pin rejects every candidate), mi_flag_undercut_rally (4 rows
all-time, last 2026-06-18). The only watcher was a data-gated review predicate gated
on the same dead counter, so it never fired either.

health_checks.run_detector_liveness_check / _evaluate_table_liveness derive a
per-table cadence from each table's own write history and alarm only when the
current silence exceeds it — see the header comment above
`_DETECTOR_LIVENESS_TABLES` in health_checks.py for the full rule.

MUTATION DISCIPLINE (operator, repeated): a test that passes whether or not the
behaviour it names is present is not a test. Every assertion below is on BEHAVIOUR
(the returned flag, the threshold value, the exact SQL sent, the exact Telegram
contents) — never on a comment or docstring string. Test numbers below are chosen
so each targeted mutation flips exactly ONE test in this file (verified by hand,
mutation results reported alongside the change).
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from tests.conftest import make_mock_pool
from agents.market_intelligence import health_checks as hc

_ET = ZoneInfo("America/New_York")
_TODAY = date(2026, 8, 16)


def _spaced_days(start: date, n: int, gap: int) -> list:
    return [start + timedelta(days=i * gap) for i in range(n)]


# ── _evaluate_table_liveness: the pure decision (mock-free) ──────────────────────


def test_never_fired_flags_unconditionally():
    """A table with zero rows ever (MAX(date_col) IS NULL) has no cadence to be
    silent relative to — flag it outright, regardless of the (empty) active-days
    list.
    MUTATION TARGET: removing the `last_write is None` branch. It would crash on
    `today - None` instead of returning the flag; no other test passes None."""
    flag = hc._evaluate_table_liveness([], None, _TODAY)
    assert flag == {"kind": "never_fired"}


def test_healthy_cadence_stays_silent():
    """Baseline sanity, not a mutation target: a table writing on-cadence must
    stay silent."""
    days = _spaced_days(date(2026, 6, 1), 6, 10)
    last = days[-1]
    today = last + timedelta(days=5)
    assert hc._evaluate_table_liveness(days, last, today) is None


def test_quiet_fortnight_does_not_alarm_a_twice_monthly_detector():
    """The task's own acceptance example: a detector that legitimately fires ~twice
    a month (median gap ~15d) must not alarm on a quiet fortnight (14d silence).
    Not a mutation target (invariant under every mutation below by construction —
    3x15=45 already equals the absolute cap, so multiplier/floor/cap changes don't
    move this case)."""
    days = _spaced_days(date(2026, 1, 1), 6, 15)
    last = days[-1]
    today = last + timedelta(days=14)
    assert hc._evaluate_table_liveness(days, last, today) is None


def test_cadence_multiplier_sets_the_threshold():
    """median gap = 10d -> threshold = 3x10 = 30d (neither the 14d floor nor the
    45d cap binds at this median, so the multiplier alone sets the line — chosen
    so floor/cap mutations can't move this test's outcome).
    MUTATION TARGET: multiplier 3.0 -> 1.0. Then threshold=max(10,14)=14 instead
    of 30: silence=20 flips from silent to firing, AND a firing case's reported
    threshold_days flips from 30.0 to 14.0."""
    days = _spaced_days(date(2026, 1, 1), 6, 10)
    last = days[-1]

    silent = hc._evaluate_table_liveness(days, last, last + timedelta(days=20))
    assert silent is None

    fires = hc._evaluate_table_liveness(days, last, last + timedelta(days=31))
    assert fires is not None and fires["kind"] == "cadence"
    assert fires["threshold_days"] == 30.0
    assert fires["median_gap_days"] == 10


def test_min_threshold_floor_protects_a_near_daily_table():
    """median gap = 1d -> multiplier alone gives 3d, but the 14d floor applies
    (chosen so mult*median=3 stays below the floor even if the multiplier were
    cut to 1.0, and so the cap never binds — isolated to the floor alone).
    MUTATION TARGET: floor removed (effectively 0). Then threshold=max(3,0)=3:
    silence=10 flips from silent to firing, AND a firing case's reported
    threshold_days flips from 14.0 to 3.0."""
    days = _spaced_days(date(2026, 8, 1), 6, 1)
    last = days[-1]

    silent = hc._evaluate_table_liveness(days, last, last + timedelta(days=10))
    assert silent is None

    fires = hc._evaluate_table_liveness(days, last, last + timedelta(days=15))
    assert fires is not None and fires["threshold_days"] == 14.0


def test_cadence_ceiling_caps_a_high_variance_median():
    """median gap = 50d -> multiplier alone gives 150d, capped to the 45d
    absolute ceiling (chosen so mult*median stays far above 45 even under the
    multiplier or floor mutations above — isolated to the cap alone: real
    cadence data can only TIGHTEN the alarm, never loosen it past what a
    totally-unknown detector gets).
    MUTATION TARGET: cap removed. Then threshold=max(150,14)=150 (uncapped):
    silence=50 flips from firing to silent."""
    days = _spaced_days(date(2026, 1, 1), 6, 50)
    last = days[-1]
    flag = hc._evaluate_table_liveness(days, last, last + timedelta(days=50))
    assert flag is not None and flag["threshold_days"] == 45.0


def test_sparse_history_uses_the_flat_fallback():
    """Fewer than MIN_ACTIVE_DAYS fire-days -> no reliable median, flat 45d floor
    applies. Covers both mi_flag_undercut_rally's real shape (4 rows all-time)
    and the exact PLAN #543 mi_anticipation_lifecycle fact pattern (last write
    2026-06-16, 61 days silent by 2026-08-16).
    MUTATION TARGET: sparse-path fallback replaced with `return None` (skip the
    sparse case entirely, treat as healthy). Then ALL THREE of these flip from
    firing/silent-as-designed to uniformly None."""
    days = [date(2026, 6, 1), date(2026, 6, 18)]
    last = days[-1]
    assert hc._evaluate_table_liveness(days, last, last + timedelta(days=40)) is None

    fires = hc._evaluate_table_liveness(days, last, last + timedelta(days=46))
    assert fires is not None and fires["kind"] == "sparse" and fires["threshold_days"] == 45.0

    plan_case_days = [date(2026, 6, 14), date(2026, 6, 15), date(2026, 6, 16)]
    plan_case_last = date(2026, 6, 16)
    plan_flag = hc._evaluate_table_liveness(plan_case_days, plan_case_last, _TODAY)
    assert plan_flag is not None
    assert plan_flag["silence_days"] == (_TODAY - plan_case_last).days == 61


def test_day_bucketing_ignores_same_day_bursts():
    """A burst of SAME-day rows must not drag the median down (a raw-row gap
    reads as near-zero for the busiest tables). 7 duplicate entries on day 0
    plus 5 distinct 10-apart days must compute the median off the DISTINCT days
    (10), not the raw list. silence is set past the absolute cap (45) so the
    assertion is insensitive to the multiplier/floor/cap mutations above —
    isolated purely to the dedup step.
    MUTATION TARGET: `sorted(set(active_days))` -> `sorted(active_days)` (dedup
    removed). The duplicate day-0 entries create six 0-day gaps that dominate an
    11-value sorted list, dropping the median from 10 to 0."""
    distinct = _spaced_days(date(2026, 1, 1), 6, 10)
    bursty = [distinct[0]] * 7 + distinct[1:]
    last = distinct[-1]
    flag = hc._evaluate_table_liveness(bursty, last, last + timedelta(days=100))
    assert flag is not None
    assert flag["median_gap_days"] == 10


def test_module_constant_covers_the_required_tables():
    """2026-08-16 cleanup review finding 1 Fix B added mi_exit_path_shadow /
    mi_alert_rank_shadow — the two shadow recorders that can fail 100% silently were
    themselves excluded from the registry that exists to catch exactly that."""
    covered = {t for t, *_ in hc._DETECTOR_LIVENESS_TABLES}
    assert covered == {
        "mi_flag_undercut_rally", "mi_flag_breaks",
        "mi_htf_breakout_shadow", "mi_consolidation_entry_shadow",
        "mi_9m_ep_alerts", "mi_ep_alerts",
        "mi_exit_path_shadow", "mi_alert_rank_shadow",
        # 2026-08-22: the shortlist pre-score counterfactual recorder — same
        # can-fail-100%-silently class (fire-and-forget writer, read by nothing
        # on the scan path).
        "mi_ep_shortlist_shadow",
        # 2026-08-30 (#327): the delayed-entry watch lane — SILENT by operator
        # ruling (no Telegram even on job failure), so this registry is its ONLY
        # watchdog. The trigger table is deliberately absent (rungs legitimately
        # go quiet; the watch table covers the writer).
        "mi_delayed_entry_watch",
        # 2026-08-30 (#533): the slot-ranking watch — a SILENT fire-and-forget
        # writer on the ORB entry path (no Telegram on any path), the exact
        # can-fail-100%-silently class this registry exists for.
        "mi_ep_slot_rank_shadow",
        # 2026-08-31 (#606): the D-1 universe floor dollar-volume shadow — another
        # fire-and-forget writer read by nothing on the scan path, same
        # can-fail-100%-silently class.
        "mi_universe_floor_shadow",
        # 2026-08-31 (#333): the analyst-estimates recorder — SILENT by the
        # data-capture contract (no Telegram even on job failure), so this registry
        # is its ONLY watchdog; a dead writer silently stops the >=60-day accrual
        # clock that gates the durability axis.
        "mi_analyst_estimates",
        # 2026-09-03 (#482): the live-fill counterfactual recorder — SILENT by design
        # (no Telegram on any path), fire-and-forget beside every MAGNA53 fill, read by
        # nothing on any live path; this registry is its only watchdog.
        "mi_live_fill_counterfactuals",
    }


def test_new_tables_key_off_a_date_column_not_a_timestamp():
    """MUTATION TARGET: registering the two new tables against `computed_at` instead of
    their own business-date column. `_detector_liveness_col_is_timestamp` is NAME-based
    (`== "created_at"`) — a timestamptz column under any other name silently mis-keys as
    a plain DATE, `MAX(computed_at)` returns a datetime, and `(today - last_write).days`
    raises inside the per-table try/except: the table would just never get checked, the
    exact failure class this registry exists to prevent (2026-08-16 cleanup review)."""
    by_table = {t: date_col for t, _label, date_col, _where in hc._DETECTOR_LIVENESS_TABLES}
    assert by_table["mi_exit_path_shadow"] == "trading_day"
    assert by_table["mi_alert_rank_shadow"] == "alert_date"
    # #327 (2026-08-30): session_date is the lane's plain-DATE business column —
    # created_at/updated_at here are timestamptz and would silently never be checked.
    assert by_table["mi_delayed_entry_watch"] == "session_date"
    # #533 (2026-08-30): alert_date is the watch's plain-DATE business column —
    # recorded_at/created_at are timestamptz and would silently never be checked.
    assert by_table["mi_ep_slot_rank_shadow"] == "alert_date"
    # #606 (2026-08-31): scan_date is the shadow's plain-DATE business column —
    # created_at is timestamptz and would silently never be checked.
    assert by_table["mi_universe_floor_shadow"] == "scan_date"
    # #333 (2026-08-31): as_of_date is the recorder's plain-DATE business column
    # (the date each estimate was READ) — created_at is timestamptz and would
    # silently never be checked.
    assert by_table["mi_analyst_estimates"] == "as_of_date"


# ── run_detector_liveness_check: orchestration + wiring ───────────────────────
#
# Mock design note: `_fetchval` decides whether to wrap the configured `last_write`
# date as a tz-aware datetime purely off whether the SQL TEXT references
# `"created_at"` — mirroring what asyncpg actually returns per COLUMN TYPE, not per
# table. This means a mutation that changes WHICH column a table queries changes
# the SQL text (caught by the dedicated SQL-spy tests below) without also crashing
# or silently changing outcomes in the other orchestration tests — keeping each
# mutation isolated to its one dedicated test.

def _wire(monkeypatch, *, per_table, dedupe_rows=None, history_rows=None):
    """per_table: dict table -> (last_write: date|None, active_day_rows: list[dict d=date]], raises: Exception|None).
    history_rows: rows the #543-follow-up history read (prior calendar days' own
    detector_liveness_check audit rows) should return — default [] (no prior sighting
    of any table, i.e. every table's never_fired state, if any, is brand new today)."""
    pool, conn = make_mock_pool()

    async def _fetchval(sql, *a):
        for table, (last_write, _rows, raises) in per_table.items():
            if f'"{table}"' in sql and "MAX(" in sql:
                if raises:
                    raise raises
                if last_write is None:
                    return None
                if '"created_at"' in sql:
                    return datetime(last_write.year, last_write.month, last_write.day,
                                     12, 0, tzinfo=_ET)
                return last_write
        raise AssertionError(f"unexpected fetchval SQL: {sql}")
    conn.fetchval = _fetchval

    async def _fetch(sql, *a):
        if "event_type = 'detector_liveness_check'" in sql:
            return history_rows or []
        for table, (_last_write, rows, raises) in per_table.items():
            if f'"{table}"' in sql and "DISTINCT" in sql:
                if raises:
                    raise raises
                return rows
        if "detector_liveness_alert" in sql:
            return dedupe_rows or []
        raise AssertionError(f"unexpected fetch SQL: {sql}")
    conn.fetch = _fetch

    async def _pool():
        return pool
    monkeypatch.setattr(hc, "get_pool", _pool)
    monkeypatch.setattr(hc, "_now_et", lambda: datetime(2026, 8, 16, 17, 30, tzinfo=_ET))

    logged, sent = [], []

    async def _log(event_type, summary, detail=""):
        logged.append((event_type, summary, detail))
    monkeypatch.setattr(hc, "log_audit_event", _log)

    import agents.market_intelligence.briefing as briefing

    async def _send(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    return conn, logged, sent


def _days_ending(end: date, n: int, gap: int) -> list:
    """n dates spaced `gap` apart, ENDING exactly at `end` — so a fixture's
    last_write is always consistent with (is the max of) its own active-days list,
    the state a real MAX(date_col) + a windowed DISTINCT query would actually
    produce together. An inconsistent fixture (last_write outside the active-days
    list) can mask a broken active-days fetch, since the flag would still key off
    last_write alone."""
    return [end - timedelta(days=(n - 1 - i) * gap) for i in range(n)]


_HEALTHY_TABLES = {
    "mi_flag_breaks": (date(2026, 8, 15), [{"d": d} for d in _days_ending(date(2026, 8, 15), 8, 5)], None),
    "mi_htf_breakout_shadow": (date(2026, 8, 14), [{"d": d} for d in _days_ending(date(2026, 8, 14), 8, 5)], None),
    "mi_consolidation_entry_shadow": (date(2026, 8, 15), [{"d": d} for d in _days_ending(date(2026, 8, 15), 8, 5)], None),
    "mi_9m_ep_alerts": (date(2026, 8, 16), [{"d": d} for d in _days_ending(date(2026, 8, 16), 8, 2)], None),
    "mi_ep_alerts": (date(2026, 8, 16), [{"d": d} for d in _days_ending(date(2026, 8, 16), 8, 2)], None),
    "mi_flag_undercut_rally": (date(2026, 8, 15), [{"d": d} for d in _days_ending(date(2026, 8, 15), 8, 5)], None),
    "mi_exit_path_shadow": (date(2026, 8, 15), [{"d": d} for d in _days_ending(date(2026, 8, 15), 8, 1)], None),
    "mi_alert_rank_shadow": (date(2026, 8, 15), [{"d": d} for d in _days_ending(date(2026, 8, 15), 8, 1)], None),
}


def test_clean_run_is_silent_audit_only(monkeypatch):
    """Baseline sanity: every table healthy -> no flags, no Telegram, one audit
    row. Not a mutation target (invariant under every mutation below — every
    configured silence here is 1 day or less, far under any threshold any
    mutation could produce)."""
    _conn, logged, sent = _wire(monkeypatch, per_table=dict(_HEALTHY_TABLES))
    out = asyncio.run(hc.run_detector_liveness_check())
    assert out["flags"] == [] and sent == []
    assert [e for e, _, _ in logged] == ["detector_liveness_check"]
    assert out["tables_scanned"] == 8


# These orchestration-level "dark" fixtures deliberately use >= MIN_ACTIVE_DAYS active
# days (the CADENCE path, not the sparse fallback) so they stay dark under EVERY mutation
# in this file's matrix except the one each test specifically targets — the sparse-path
# mutation is exercised only by the dedicated pure-function test above
# (test_sparse_history_uses_the_flat_fallback), not indirectly through these fixtures.
# The second dark table. It WAS mi_anticipation_lifecycle until that entry was retired
# 2026-08-31 (superseded by #327, whose mi_delayed_entry_watch is registered instead) —
# these tests need any two dark tables to prove batching/dedupe/error isolation, not that
# specific one. Repointed at a still-registered shadow recorder, same fixture shape.
_DARK_HTF_BREAKOUT = (date(2026, 6, 16),
                      [{"d": d} for d in _spaced_days(date(2026, 5, 22), 6, 5)], None)  # median gap 5d
_DARK_UNDERCUT_RALLY = (date(2026, 6, 18),
                        [{"d": d} for d in _spaced_days(date(2026, 6, 3), 6, 3)], None)  # median gap 3d


def test_cold_start_batches_every_dark_table_into_one_telegram(monkeypatch):
    """Day one: several tables are ALREADY dark (per PLAN #543). One grouped
    Telegram, not a stream.
    MUTATION TARGET: the fetched active-days rows silently going unused (a
    swallowed error, a wrong column at runtime, an empty result) — every table
    would then fall through to the flat 45d sparse floor. A dark fixture still
    FIRES either way (both configured silences exceed 45d), so `len(flags)`
    alone can't catch this; the median_gap_days/kind assertion on
    mi_flag_undercut_rally (real fire-days Jun3..Jun18, gap 3) is what proves
    the fetched active-days actually drove the cadence math, not just a flat
    floor wearing the same "fires" outcome."""
    tables = dict(_HEALTHY_TABLES)
    tables["mi_htf_breakout_shadow"] = _DARK_HTF_BREAKOUT
    tables["mi_flag_undercut_rally"] = _DARK_UNDERCUT_RALLY
    _conn, logged, sent = _wire(monkeypatch, per_table=tables)
    out = asyncio.run(hc.run_detector_liveness_check())
    assert len(out["flags"]) == 2
    assert len(sent) == 1  # ONE message, not one per table
    assert "mi_htf_breakout_shadow" in sent[0]
    assert "mi_flag_undercut_rally" in sent[0]
    ur_flag = next(f for f in out["flags"] if f["table"] == "mi_flag_undercut_rally")
    assert ur_flag["kind"] == "cadence" and ur_flag["median_gap_days"] == 3
    alert_events = [e for e, _, _ in logged if e == "detector_liveness_alert"]
    assert len(alert_events) == 2  # one audit row per table (the dedupe key)


def test_per_table_dedupe_does_not_suppress_a_different_fresh_table(monkeypatch):
    """Table A was already announced within the dedupe window; table B goes dark
    fresh this run. B must still speak — A must not be re-announced.
    MUTATION TARGET: a single GLOBAL dedupe count (skip the whole run if ANYTHING
    was recently announced) instead of per-table filtering. Only this test
    configures a non-empty `dedupe_rows`, so only this test is sensitive."""
    tables = dict(_HEALTHY_TABLES)
    tables["mi_htf_breakout_shadow"] = _DARK_HTF_BREAKOUT
    tables["mi_flag_undercut_rally"] = _DARK_UNDERCUT_RALLY
    _conn, logged, sent = _wire(
        monkeypatch, per_table=tables,
        dedupe_rows=[{"t": "mi_htf_breakout_shadow"}],
    )
    out = asyncio.run(hc.run_detector_liveness_check())
    assert len(out["flags"]) == 2  # both still MEASURED
    assert len(sent) == 1
    assert "mi_flag_undercut_rally" in sent[0]
    assert "mi_htf_breakout_shadow" not in sent[0]  # suppressed by its own recent alert


def _history_row(d: date, table: str) -> dict:
    """One prior-night detector_liveness_check audit row showing `table` as never_fired
    on calendar day `d` — the shape `_wire`'s history_rows mock returns."""
    return {"d": d, "detail": json.dumps([{
        "kind": "never_fired", "table": table, "label": "exit-path shadow",
    }])}


def test_never_fired_table_not_reported_on_first_sighting(monkeypatch):
    """2026-08-16 incident: this whole check runs at 17:30 ET inside
    post_nightly_audit, TWENTY MINUTES BEFORE mi_exit_path_shadow's own writer job
    (17:50 ET) and mi_alert_rank_shadow's (17:53 ET) — both fired 🩺 "0 rows ever"
    on deploy night despite being perfectly healthy, because neither had been given
    its first chance to write by the time the check ran. A same-day clock/cron
    comparison can't fix this (the checker precedes the writer EVERY evening,
    forever); the fix instead derives from this check's OWN run history: a table
    is silenced from Telegram while inside its 45-day first-sighting grace window
    (the SAME tolerance the sparse-cadence path already grants a table with too
    little history — see test_cadence_ceiling_caps_a_high_variance_median).
    MUTATION TARGET: reverting the in_grace suppression (i.e. a never_fired flag
    always speaks, as before the fix). Then `sent` is non-empty and names
    mi_exit_path_shadow — reproducing tonight's false alarm deterministically."""
    tables = dict(_HEALTHY_TABLES)
    tables["mi_exit_path_shadow"] = (None, [], None)  # zero rows, ever
    _conn, logged, sent = _wire(monkeypatch, per_table=tables)  # history_rows=None -> no prior sighting
    out = asyncio.run(hc.run_detector_liveness_check())

    flagged = next(f for f in out["flags"] if f["table"] == "mi_exit_path_shadow")
    assert flagged["kind"] == "never_fired"
    assert flagged["in_grace"] is True
    assert flagged["first_seen_date"] == _TODAY.isoformat()
    assert sent == []  # nothing else is dark in this fixture -> no Telegram at all

    # Still PERSISTED (unconditionally, flagged or not) so a later night's history
    # read can find it — in_grace suppresses speaking, not recording.
    check_details = [d for e, _, d in logged if e == "detector_liveness_check"]
    assert any(
        '"table": "mi_exit_path_shadow"' in d and '"kind": "never_fired"' in d
        for d in check_details
    )


def test_never_fired_table_stays_silent_deep_inside_the_grace_window(monkeypatch):
    """mi_exit_path_shadow writes one row per LIVE trade per day — with zero
    eligible live trades on a given day it correctly writes NOTHING (see
    record_exit_path_shadow's population/written counters), and that is NORMAL,
    not broken. So a table seen never_fired on just ONE prior day (a single quiet
    day, not 45 of them) must NOT alarm yet — the exact "day 2" cry-wolf a bare
    one-night grace would still produce.
    MUTATION TARGET: shrinking or dropping the grace window (e.g. any history at
    all ends the grace, as an earlier draft of this fix did). Then this table
    would speak after just one prior sighting."""
    tables = dict(_HEALTHY_TABLES)
    tables["mi_exit_path_shadow"] = (None, [], None)  # still zero rows, ever
    history_rows = [_history_row(_TODAY - timedelta(days=1), "mi_exit_path_shadow")]
    _conn, logged, sent = _wire(monkeypatch, per_table=tables, history_rows=history_rows)
    out = asyncio.run(hc.run_detector_liveness_check())

    flagged = next(f for f in out["flags"] if f["table"] == "mi_exit_path_shadow")
    assert flagged["in_grace"] is True
    assert flagged["first_seen_date"] == (_TODAY - timedelta(days=1)).isoformat()
    assert sent == []


def test_never_fired_table_alarms_once_the_grace_window_elapses(monkeypatch):
    """Same table, still zero rows — but this check's own history shows its
    EARLIEST never_fired sighting was 45+ days ago (matching
    `_DETECTOR_LIVENESS_ABSOLUTE_FALLBACK_DAYS`, the same flat floor the
    sparse-cadence path already uses). A detector with zero output for that long
    is genuinely dark and must alarm, exactly like mi_anticipation_lifecycle
    (retired 2026-08-31, silent 62 days at the time) and mi_flag_undercut_rally
    (silent 60 days) still do in the cold-start test above.
    MUTATION TARGET: suppressing in_grace flags FOREVER instead of only within
    the window (e.g. always treating a table as in_grace, or letting TODAY's own
    row count as the earliest sighting instead of the true history minimum).
    Either mutation leaves this table silent forever — the exact months-long
    blind spot #543 was built to close."""
    tables = dict(_HEALTHY_TABLES)
    tables["mi_exit_path_shadow"] = (None, [], None)  # still zero rows, ever
    history_rows = [
        _history_row(_TODAY - timedelta(days=45), "mi_exit_path_shadow"),
        _history_row(_TODAY - timedelta(days=1), "mi_exit_path_shadow"),
    ]
    _conn, logged, sent = _wire(monkeypatch, per_table=tables, history_rows=history_rows)
    out = asyncio.run(hc.run_detector_liveness_check())

    flagged = next(f for f in out["flags"] if f["table"] == "mi_exit_path_shadow")
    assert "in_grace" not in flagged  # anchored to the EARLIEST sighting (45d ago), not the latest (1d ago)
    assert len(sent) == 1
    assert "mi_exit_path_shadow" in sent[0]


def test_history_read_failure_fails_open_toward_silence_not_alarm(monkeypatch):
    """The #543-follow-up history read can itself fail (DB hiccup). It must fail
    OPEN toward treating every table as newly-first-seen (grace restarts, one
    extra silent stretch for a genuinely-dead table) — never toward fabricating a
    false alarm out of a lost read, mirroring the announce-dedupe fail-open a few
    lines below it.
    MUTATION TARGET: letting the history-read exception propagate uncaught (would
    abort the whole run — `out["errors"]` would carry a `pool` failure and NO
    table would get scanned) instead of being swallowed locally."""
    tables = dict(_HEALTHY_TABLES)
    tables["mi_exit_path_shadow"] = (None, [], None)
    _conn, logged, sent = _wire(monkeypatch, per_table=tables)

    async def _boom(sql, *a):
        if "event_type = 'detector_liveness_check'" in sql:
            raise RuntimeError("db hiccup")
        raise AssertionError(f"unexpected fetch SQL: {sql}")
    # Patch just the history query; delegate everything else to the normal mock.
    orig_fetch = _conn.fetch

    async def _fetch_with_history_failure(sql, *a):
        if "event_type = 'detector_liveness_check'" in sql:
            return await _boom(sql, *a)
        return await orig_fetch(sql, *a)
    _conn.fetch = _fetch_with_history_failure

    out = asyncio.run(hc.run_detector_liveness_check())
    assert out["tables_scanned"] == 8  # sweep proceeded despite the failed history read
    flagged = next(f for f in out["flags"] if f["table"] == "mi_exit_path_shadow")
    assert flagged["in_grace"] is True  # failed open -> treated as newly first-seen -> silent
    assert sent == []


def test_one_bad_table_does_not_kill_the_sweep(monkeypatch):
    """MUTATION TARGET: removing the per-table try/except lets one table's
    exception abort the whole loop via the outer catch — tables_scanned would
    stop short at the failure point and later tables never get evaluated. Only
    this test configures a `raises`, so only this test is sensitive."""
    tables = dict(_HEALTHY_TABLES)
    tables["mi_htf_breakout_shadow"] = (None, [], RuntimeError("db exploded"))
    tables["mi_flag_undercut_rally"] = _DARK_UNDERCUT_RALLY
    _conn, logged, sent = _wire(monkeypatch, per_table=tables)
    out = asyncio.run(hc.run_detector_liveness_check())
    assert out["tables_scanned"] == 7  # 8 tables minus the one that raised
    assert any(e.get("table") == "mi_htf_breakout_shadow" for e in out["errors"])
    assert any(f["table"] == "mi_flag_undercut_rally" for f in out["flags"])


def test_ep_alerts_filters_to_live_rows(monkeypatch):
    """mi_ep_alerts carries replay/backtest rows (source='historical_scan', #268)
    sharing the table across a ~12-month span — an unfiltered read could see a
    replay batch and miss a genuinely dead live detector.
    MUTATION TARGET: dropping the registry's extra-WHERE for mi_ep_alerts. Only
    this test inspects the SQL text sent for that table, so only this test is
    sensitive — the mock's returned VALUES don't depend on the WHERE clause, so
    no other test's outcome moves under this mutation."""
    seen_sql = {}
    tables = dict(_HEALTHY_TABLES)
    conn, _logged, _sent = _wire(monkeypatch, per_table=tables)

    orig_fetch, orig_fetchval = conn.fetch, conn.fetchval

    async def _fetch_spy(sql, *a):
        if '"mi_ep_alerts"' in sql and "DISTINCT" in sql:
            seen_sql["active_days_sql"] = sql
        return await orig_fetch(sql, *a)
    conn.fetch = _fetch_spy

    async def _fetchval_spy(sql, *a):
        if '"mi_ep_alerts"' in sql and "MAX(" in sql:
            seen_sql["last_write_sql"] = sql
        return await orig_fetchval(sql, *a)
    conn.fetchval = _fetchval_spy

    asyncio.run(hc.run_detector_liveness_check())
    assert "COALESCE(source, 'live') = 'live'" in seen_sql["active_days_sql"]
    assert "COALESCE(source, 'live') = 'live'" in seen_sql["last_write_sql"]


def test_no_registry_entry_can_be_silently_mis_keyed_on_a_timestamp_column():
    """The registry's date-column rule is NAME-BASED (`_detector_liveness_col_is_timestamp`
    is literally `date_col == "created_at"`), which means a timestamptz column registered
    under ANY other name — `recorded_at`, `fired_at`, `scanned_at` — is treated as a plain
    DATE and silently mis-keys: the check would compare a timestamp to a date and read the
    table as never firing, or never check it at all. Five registry comments cite this rule
    when explaining their column choice; this pins it.

    Replaces test_anticipation_lifecycle_keys_off_created_at_not_business_date, which
    mutation-tested the single registry entry that used `created_at` — retired 2026-08-31
    when #327 superseded the #270 machine. The rule outlived the entry, so the test is now
    an invariant over the WHOLE registry rather than a probe of one row: it cannot rot the
    next time an entry is added or removed.

    MUTATION TARGETS: (a) registering a new table on an `*_at` timestamptz column other than
    created_at; (b) broadening the predicate so some other name also routes to the timestamp
    branch, which would make the registry's stated contract untrue."""
    assert hc._detector_liveness_col_is_timestamp("created_at") is True
    for other in ("recorded_at", "fired_at", "scanned_at", "session_date", "alert_date"):
        assert hc._detector_liveness_col_is_timestamp(other) is False, (
            f"{other} must NOT route to the timestamp branch — the rule is name-based and "
            f"only `created_at` is contracted")

    for table, _label, date_col, _extra in hc._DETECTOR_LIVENESS_TABLES:
        if date_col.endswith("_at"):
            assert date_col == "created_at", (
                f"{table} is registered on `{date_col}`, a timestamp-shaped name the "
                f"name-based rule does not recognise — it would be silently mis-keyed. "
                f"Use a plain DATE business column, or `created_at` if the table is "
                f"UPSERT-style and its business dates get rewritten in place.")


def test_nightly_audit_wires_the_detector_liveness_check():
    """MUTATION TARGET: deleting the scheduler call. A comment merely NAMING the
    function would satisfy a bare substring check — assert on the actual awaited
    call so a comment-only survivor can't pass this test."""
    from agents.market_intelligence import scheduler as sched
    import inspect
    src = inspect.getsource(sched._post_nightly_audit_job)
    assert "await run_detector_liveness_check()" in src
