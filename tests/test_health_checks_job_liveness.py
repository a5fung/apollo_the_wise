"""JOB → OUTPUT-LIVENESS sweep — the ran-but-produced-nothing catcher (PLAN #370 increment 3).

The bar here is HIGHER than usual (asymmetric failure): a BUGGY guard gives FALSE CONFIDENCE that
you'll be alerted when you won't. So we prove, mock-free, that:
  (1) a job that RAN ('success') but whose output table got 0 new rows IS flagged — the
      theme-synthesis-truncation / theme-shadow-0-rows (#173) class. This is the DoD scenario and
      MUST fire (mirrors test_200ma_null_fires in the null-sweep tests);
  (2) a job that did NOT run is NOT flagged (no-run = heartbeat = increment 4, deliberately ours-not);
  (3) a legitimately-sometimes-empty job (K=3) is NOT flagged on a SINGLE zero, but IS flagged on K
      CONSECUTIVE zeros (the noise calibration — quiet-day vs structural break);
  (4) the sweep survives a missing / erroring table without crashing.

Mirrors test_health_checks_null_sweep.py: the PURE decision (`_evaluate_job_liveness`) is tested
directly first with zero mocking, then integration tests drive the real SQL-shaped path via a fake conn.
"""
from __future__ import annotations

import pytest

from agents.market_intelligence import health_checks
from agents.market_intelligence.health_checks import (
    _evaluate_job_liveness,
    run_job_liveness_sweep,
)


# ── Pure decision: _evaluate_job_liveness (no mocking) ────────────────────────


def test_always_on_single_empty_run_is_flagged():
    # K=1 always-on (mi_themes): the latest successful run wrote 0 rows → structurally broken → flag.
    # per_date_counts is MOST-RECENT-FIRST, so the latest run is index 0.
    verdict = _evaluate_job_liveness([0, 50, 48, 51], min_expected_rows=1, k=1)
    assert verdict is not None, "an always-on table empty on the latest successful run MUST flag"
    assert verdict["empty_runs"] == 1


def test_always_on_latest_has_rows_not_flagged():
    # The job produced output on its latest run → nothing broke.
    assert _evaluate_job_liveness([50, 0, 0, 48], min_expected_rows=1, k=1) is None


def test_quiet_job_single_zero_not_flagged():
    # K=3 legit-quiet (ep_scan / theme_synthesis): ONE empty run-date is a normal slow day → NOT a
    # flag. This is the false-positive class the guard must NOT raise (the muted-guard death).
    assert _evaluate_job_liveness([0, 4, 2, 0, 3], min_expected_rows=1, k=3) is None


def test_quiet_job_two_consecutive_zeros_not_flagged():
    # Two consecutive zeros still under the K=3 cadence → not yet a structural break → no flag.
    assert _evaluate_job_liveness([0, 0, 4, 2, 3], min_expected_rows=1, k=3) is None


def test_quiet_job_k_consecutive_zeros_is_flagged():
    # K=3 consecutive empty run-dates (the headline "0 rows for 3 runs" theme-synthesis case) →
    # structural break → flag. The sample alert in the spec is exactly this.
    verdict = _evaluate_job_liveness([0, 0, 0, 4, 2], min_expected_rows=1, k=3)
    assert verdict is not None, "K consecutive empty runs MUST flag a quiet job"
    assert verdict["empty_runs"] == 3
    assert verdict["window_counts"] == [0, 0, 0]


def test_quiet_job_recovers_within_window_not_flagged():
    # The most-recent k window is what matters: even with older zeros, if the latest run produced
    # rows the job is alive again → no flag (we don't re-nag a recovered job).
    assert _evaluate_job_liveness([5, 0, 0, 0], min_expected_rows=1, k=3) is None


def test_too_few_run_dates_not_flagged():
    # Fewer than k successful run-dates → not enough history to judge (a no/low-run situation is the
    # heartbeat's job, increment 4) → skip, never flag.
    assert _evaluate_job_liveness([0], min_expected_rows=1, k=3) is None
    assert _evaluate_job_liveness([], min_expected_rows=1, k=1) is None


def test_below_min_expected_counts_as_empty():
    # "produced nothing" is < min_expected_rows, not strictly 0 — a degenerate-floor min catches the
    # near-empty case too. min=5, latest run wrote 2 → below floor → flag (K=1).
    verdict = _evaluate_job_liveness([2, 50, 48], min_expected_rows=5, k=1)
    assert verdict is not None


# ── Integration: real SQL-shaped path via a fake conn ─────────────────────────


class _FakeConn:
    """Stand-in for an asyncpg conn. Routes the two query shapes the sweep issues:
      - mi_job_runs DISTINCT run_date  → returns the job's most-recent successful ET run-dates
      - COUNT(*) FROM "<table>" WHERE  → returns the new-row count for that table on a run_date
    Per-job behaviour is supplied by `jobs`: {job_id: (run_dates, {run_date: row_count})}.
    Per-table the COUNT routes by the table name in the FROM clause via `table_for_job`.
    A job whose value is the sentinel "ERROR" raises, to exercise the try/except robustness.
    """

    def __init__(self, jobs: dict, table_for_job: dict):
        self._jobs = jobs
        self._table_for_job = table_for_job  # job_id -> table name (for COUNT routing)

    async def fetch(self, sql, *args):
        # The run-dates query.
        assert "mi_job_runs" in sql
        job_id = args[0]
        entry = self._jobs.get(job_id)
        if entry == "ERROR":
            raise RuntimeError(f"boom on {job_id}")
        run_dates, _counts = entry
        limit = args[1]
        return [{"run_date": d} for d in run_dates[:limit]]

    async def fetchval(self, sql, *args):
        # The per-date COUNT(*) query. Identify the job by the table named in the FROM clause.
        run_date = args[0]
        for job_id, table in self._table_for_job.items():
            if f'FROM "{table}"' in sql:
                entry = self._jobs.get(job_id)
                if entry == "ERROR":
                    raise RuntimeError(f"boom counting {table}")
                _dates, counts = entry
                return counts.get(run_date, 0)
        raise AssertionError(f"unexpected count query: {sql[:80]}")


@pytest.fixture
def _captured_telegram(monkeypatch):
    sent: list[str] = []

    async def _send(text, *a, **k):
        sent.append(text)
        return True

    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    return sent


@pytest.fixture
def _captured_audit(monkeypatch):
    events: list[tuple] = []

    async def _audit(event_type, summary, detail=""):
        events.append((event_type, summary, detail))

    monkeypatch.setattr(health_checks, "log_audit_event", _audit)
    return events


@pytest.mark.asyncio
async def test_ran_but_empty_fires_telegram_and_audit(_captured_telegram, _captured_audit, monkeypatch):
    # THE DoD SCENARIO (case 1): nightly_data_pull RAN ('success') today but mi_themes got 0 rows →
    # the truncation / theme-shadow-0-rows (#173) silent failure → MUST flag + Telegram + audit.
    monkeypatch.setattr(
        health_checks,
        "_JOB_OUTPUT_CHECKS",
        [("nightly_data_pull", "nightly theme snapshot", "mi_themes", "theme_date", 1, 1)],
    )
    conn = _FakeConn(
        jobs={
            # ran on 3 recent dates; the LATEST run-date wrote 0 rows to mi_themes
            "nightly_data_pull": (
                ["2026-06-25", "2026-06-24", "2026-06-23"],
                {"2026-06-25": 0, "2026-06-24": 15, "2026-06-23": 16},
            ),
        },
        table_for_job={"nightly_data_pull": "mi_themes"},
    )

    summary = await run_job_liveness_sweep(conn)

    # The flag fired on the ran-but-empty job.
    flagged = {f["job_id"] for f in summary["flags"]}
    assert "nightly_data_pull" in flagged
    assert len(summary["flags"]) == 1
    assert summary["flags"][0]["table"] == "mi_themes"

    # ONE grouped Telegram, naming the job + the produced-nothing condition.
    assert len(_captured_telegram) == 1
    assert "JOB PRODUCED NOTHING" in _captured_telegram[0]
    assert "nightly_data_pull" in _captured_telegram[0]
    assert "mi_themes" in _captured_telegram[0]

    # Audit row written with the flagged event type.
    assert any(e[0] == "health_job_liveness_flagged" for e in _captured_audit)


@pytest.mark.asyncio
async def test_job_did_not_run_not_flagged(_captured_telegram, _captured_audit, monkeypatch):
    # CASE 2: the job has NO successful run-dates in history (didn't run) → NOT flagged here. A
    # non-running job is the heartbeat's concern (increment 4); flagging it here would false-fire on
    # holidays / weekends / a genuinely-down job.
    monkeypatch.setattr(
        health_checks,
        "_JOB_OUTPUT_CHECKS",
        [("nightly_data_pull", "nightly theme snapshot", "mi_themes", "theme_date", 1, 1)],
    )
    conn = _FakeConn(
        jobs={"nightly_data_pull": ([], {})},  # no successful run-dates at all
        table_for_job={"nightly_data_pull": "mi_themes"},
    )

    summary = await run_job_liveness_sweep(conn)

    assert summary["flags"] == []
    assert _captured_telegram == []  # no run → no flag → no Telegram
    assert any(e[0] == "health_job_liveness_clean" for e in _captured_audit)


@pytest.mark.asyncio
async def test_quiet_job_single_zero_then_k_zeros(_captured_telegram, _captured_audit, monkeypatch):
    # CASE 3: a legit-quiet K=3 job (theme_synthesis). A SINGLE zero must NOT flag (slow day); K
    # consecutive zeros MUST flag (structural break). We exercise the real SQL path for both.
    monkeypatch.setattr(
        health_checks,
        "_JOB_OUTPUT_CHECKS",
        [("theme_synthesis", "theme synthesis", "mi_theme_candidates_shadow", "run_date", 1, 3)],
    )

    # 3a: single zero (latest), prior runs produced → NOT flagged.
    conn_single = _FakeConn(
        jobs={
            "theme_synthesis": (
                ["2026-06-25", "2026-06-24", "2026-06-23", "2026-06-22", "2026-06-20"],
                {"2026-06-25": 0, "2026-06-24": 2, "2026-06-23": 3, "2026-06-22": 1, "2026-06-20": 2},
            ),
        },
        table_for_job={"theme_synthesis": "mi_theme_candidates_shadow"},
    )
    summary_single = await run_job_liveness_sweep(conn_single)
    assert summary_single["flags"] == [], "a single quiet-day zero must NOT flag a K=3 job"
    assert _captured_telegram == []

    # 3b: K=3 consecutive zeros → structural break → flagged.
    conn_k = _FakeConn(
        jobs={
            "theme_synthesis": (
                ["2026-06-25", "2026-06-24", "2026-06-23", "2026-06-22", "2026-06-20"],
                {"2026-06-25": 0, "2026-06-24": 0, "2026-06-23": 0, "2026-06-22": 2, "2026-06-20": 3},
            ),
        },
        table_for_job={"theme_synthesis": "mi_theme_candidates_shadow"},
    )
    summary_k = await run_job_liveness_sweep(conn_k)
    flagged = {f["job_id"] for f in summary_k["flags"]}
    assert "theme_synthesis" in flagged, "K=3 consecutive zeros MUST flag a quiet job"
    assert summary_k["flags"][0]["empty_runs"] == 3
    assert len(_captured_telegram) == 1  # the K-zero case fired exactly one Telegram


@pytest.mark.asyncio
async def test_erroring_job_does_not_kill_sweep(_captured_telegram, _captured_audit, monkeypatch):
    # CASE 4: one job's query raises (missing/erroring table); a healthy ran-but-empty job after it
    # still gets checked and its real flag still fires. The guard must not itself fail silently.
    monkeypatch.setattr(
        health_checks,
        "_JOB_OUTPUT_CHECKS",
        [
            ("bad_job", "bad", "mi_bad_table", "bad_date", 1, 1),
            ("nightly_data_pull", "nightly theme snapshot", "mi_themes", "theme_date", 1, 1),
        ],
    )
    conn = _FakeConn(
        jobs={
            "bad_job": "ERROR",
            "nightly_data_pull": (
                ["2026-06-25", "2026-06-24", "2026-06-23"],
                {"2026-06-25": 0, "2026-06-24": 15, "2026-06-23": 16},
            ),
        },
        table_for_job={"bad_job": "mi_bad_table", "nightly_data_pull": "mi_themes"},
    )

    summary = await run_job_liveness_sweep(conn)

    # The sweep survived: the bad job is recorded as an error, the good job still flagged.
    assert any(err.get("job_id") == "bad_job" for err in summary["errors"])
    assert any(f["job_id"] == "nightly_data_pull" for f in summary["flags"])


@pytest.mark.asyncio
async def test_holiday_success_run_with_zero_output_not_flagged(
    _captured_telegram, _captured_audit, monkeypatch
):
    # THE HOLIDAY FALSE-FIRE GUARD (advisor-required). On a weekday market holiday, nightly_data_pull
    # RUNS, early-returns BEFORE the theme step, and STILL records status='success' (PLAN #325:
    # "success = the clean holiday-skip" on Juneteenth) → that run-date has 0 mi_themes rows. Without
    # the trading-day filter, the K=1 always-on entry would FALSE-FIRE ~9-10×/yr and get the guard
    # muted. With the filter, the holiday run-date is DROPPED and the real trading-day runs (which DID
    # produce rows) are evaluated → NOT flagged.
    monkeypatch.setattr(
        health_checks,
        "_JOB_OUTPUT_CHECKS",
        [("nightly_data_pull", "nightly theme snapshot", "mi_themes", "theme_date", 1, 1)],
    )
    holiday = "2026-06-19"  # Juneteenth — a weekday holiday with a 0-row success run

    # Force the calendar verdict deterministically (local env lacks exchange_calendars → fail-open).
    def _fake_trading(d):
        return d != holiday

    monkeypatch.setattr(health_checks, "_is_trading_day", _fake_trading)

    conn = _FakeConn(
        jobs={
            "nightly_data_pull": (
                # latest run-date IS the holiday (0 rows); the real trading-day runs before it produced.
                [holiday, "2026-06-18", "2026-06-17", "2026-06-16"],
                {holiday: 0, "2026-06-18": 15, "2026-06-17": 16, "2026-06-16": 15},
            ),
        },
        table_for_job={"nightly_data_pull": "mi_themes"},
    )

    summary = await run_job_liveness_sweep(conn)

    # The holiday's zero-output run was dropped → the evaluated trading-day run produced rows → no flag.
    assert summary["flags"] == [], "a holiday success-run with 0 output must NOT flag (false-fire guard)"
    assert _captured_telegram == []
    assert any(e[0] == "health_job_liveness_clean" for e in _captured_audit)


@pytest.mark.asyncio
async def test_clean_run_no_telegram_audit_only(_captured_telegram, _captured_audit, monkeypatch):
    # All jobs produced output on their latest runs → nothing broke → NO Telegram, audit-only
    # (Telegram reserved for real failures, like the null-sweep clean path).
    monkeypatch.setattr(
        health_checks,
        "_JOB_OUTPUT_CHECKS",
        [
            ("nightly_data_pull", "nightly theme snapshot", "mi_themes", "theme_date", 1, 1),
            ("theme_synthesis", "theme synthesis", "mi_theme_candidates_shadow", "run_date", 1, 3),
        ],
    )
    conn = _FakeConn(
        jobs={
            "nightly_data_pull": (
                ["2026-06-25", "2026-06-24", "2026-06-23"],
                {"2026-06-25": 15, "2026-06-24": 15, "2026-06-23": 16},
            ),
            "theme_synthesis": (
                ["2026-06-25", "2026-06-24", "2026-06-23"],
                {"2026-06-25": 2, "2026-06-24": 0, "2026-06-23": 1},
            ),
        },
        table_for_job={
            "nightly_data_pull": "mi_themes",
            "theme_synthesis": "mi_theme_candidates_shadow",
        },
    )

    summary = await run_job_liveness_sweep(conn)

    assert summary["flags"] == []
    assert _captured_telegram == []
    assert any(e[0] == "health_job_liveness_clean" for e in _captured_audit)
    assert summary["jobs_checked"] == 2
