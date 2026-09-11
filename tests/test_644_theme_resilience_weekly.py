"""#644 — the weekly SHADOW recorder for theme down-day resilience.

`agents/market_intelligence/theme_resilience_shadow.py` writes one
`mi_theme_resilience_weekly` row per currently-active theme per week, carrying its as-of
down-day resilience (db.get_down_day_resilience — already built and tested in
tests/test_644_down_day_resilience.py, frozen and NOT reimplemented here). Exists so the
November forward test (PLAN.md #644, decision rule frozen 2026-09-11) reads a value that was
CAPTURED AT THE TIME, never reconstructed later from closes (the #629 defect class).

Three things this test file exists to prove, per the task's own DoD:
  1. A theme the measure can't be computed for gets a row with a NULL resilience + a stated
     reason — never gets skipped.
  2. Re-running the job for a week that already has rows does not duplicate them.
  3. The writer's SQL is registered in the deploy-time preflight gate
     (scripts/preflight_db_updates.py SHADOW_WRITER_STATEMENTS) — the #606 lesson: a silent
     recorder is exactly where a type-deduction bug hides longest.

Plus: THE LINE (nothing outside this module + its writer + its scheduler registration reads
mi_theme_resilience_weekly), the scheduler-partition classification, and the deploy-window
placement.
"""
from __future__ import annotations

import asyncio
import contextlib
import re
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

import agents.market_intelligence.db as db
import agents.market_intelligence.theme_resilience_shadow as trs
from agents.market_intelligence import scheduler as sched

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PY = REPO_ROOT / "agents" / "market_intelligence" / "db.py"


def _run(coro):
    return asyncio.run(coro)


# ── week_start_for: pure, no DB ──────────────────────────────────────────────────────────

def test_week_start_for_returns_the_monday_of_the_week():
    # 2026-09-11 is a Friday; its week's Monday is 2026-09-07.
    assert trs.week_start_for(date(2026, 9, 11)) == date(2026, 9, 7)
    # A Monday maps to itself.
    assert trs.week_start_for(date(2026, 9, 7)) == date(2026, 9, 7)
    # A Sunday maps back to the PRIOR Monday (Python's Mon=0..Sun=6 week model).
    assert trs.week_start_for(date(2026, 9, 13)) == date(2026, 9, 7)


def test_lookback_is_frozen_at_the_measures_own_default():
    """#644's task line: 'Do not change ... the measure. They are frozen.' Pin the
    recorder's lookback to get_down_day_resilience's own default so a future change to
    either can't silently drift the other without a test noticing."""
    import inspect
    sig = inspect.signature(db.get_down_day_resilience)
    assert trs.DOWN_DAY_RESILIENCE_LOOKBACK == sig.parameters["lookback"].default == 20


# ── (1) not-computable cases write a NULL row with a reason, never skip ─────────────────

def test_theme_with_no_tickers_is_not_computable_with_a_reason(monkeypatch):
    theme = {"name": "Empty Cohort Theme", "stage": "Nascent",
              "theme_date": date(2026, 9, 10), "tickers": []}
    fields = _run(trs.compute_theme_resilience_fields(theme, date(2026, 9, 14)))
    assert fields["resilience"] is None
    assert fields["resilience_computable"] is False
    assert fields["not_computable_reason"]  # a REASON, not blank
    assert "ticker" in fields["not_computable_reason"].lower()
    assert fields["n_tickers_covered"] == 0
    # every other field is still populated — this is a ROW, not a skip
    assert fields["theme_stage"] == "Nascent"
    assert fields["theme_snapshot_date"] == date(2026, 9, 10)
    assert fields["as_of_date"] == date(2026, 9, 14)
    assert fields["lookback_days"] == 20


def test_theme_whose_tickers_have_no_down_day_coverage_is_not_computable_with_a_reason(
    monkeypatch,
):
    theme = {"name": "No Coverage Theme", "stage": "Accelerating",
              "theme_date": date(2026, 9, 10), "tickers": ["ZZZZ"]}
    monkeypatch.setattr(trs, "get_down_day_resilience", AsyncMock(return_value=[]))
    fields = _run(trs.compute_theme_resilience_fields(theme, date(2026, 9, 14)))
    assert fields["resilience"] is None
    assert fields["resilience_computable"] is False
    assert fields["not_computable_reason"]
    assert fields["not_computable_reason"] != trs._NO_TICKERS_REASON  # a DIFFERENT reason
    assert fields["n_tickers_covered"] == 0


def test_would_fail_if_a_not_computable_theme_were_silently_skipped():
    """Proves the guard actually discriminates: a caller that special-cased 'not
    computable' into `None` (skip, no row) instead of a dict would fail this — the field
    contract itself (a dict with resilience_computable=False and a reason) is the thing
    under test, not just its values."""
    theme = {"name": "T", "stage": None, "theme_date": None, "tickers": None}
    fields = _run(trs.compute_theme_resilience_fields(theme, date(2026, 9, 14)))
    assert isinstance(fields, dict)
    assert fields["resilience_computable"] is False
    assert fields["not_computable_reason"] is not None


def test_computable_theme_uses_median_of_covered_members(monkeypatch):
    theme = {"name": "Real Theme", "stage": "Mainstream",
              "theme_date": date(2026, 9, 10), "tickers": ["AAA", "BBB", "CCC"]}
    canned = [
        {"ticker": "AAA", "resilience": 0.02},
        {"ticker": "BBB", "resilience": 0.05},
        {"ticker": "CCC", "resilience": -0.01},
    ]  # median = 0.02
    fetch_mock = AsyncMock(return_value=canned)
    monkeypatch.setattr(trs, "get_down_day_resilience", fetch_mock)
    fields = _run(trs.compute_theme_resilience_fields(theme, date(2026, 9, 14)))
    assert fields["resilience"] == pytest.approx(0.02)
    assert fields["resilience_computable"] is True
    assert fields["not_computable_reason"] is None
    assert fields["n_tickers_covered"] == 3
    # the frozen measure is CALLED, not reimplemented — same tickers, same lookback, same d
    fetch_mock.assert_awaited_once_with(
        date(2026, 9, 14), tickers=["AAA", "BBB", "CCC"], lookback=20)


# ── (2) idempotent — re-running a week does not duplicate rows ──────────────────────────

class _ResilienceStore:
    def __init__(self):
        self.rows: dict[tuple[str, "date"], tuple] = {}
        self.executed: list[tuple] = []


class _ResilienceConn:
    def __init__(self, store: _ResilienceStore):
        self.store = store

    async def execute(self, sql, *args):
        self.store.executed.append((" ".join(sql.split()), args))
        if "INSERT INTO mi_theme_resilience_weekly" in sql:
            week_start, theme_name = args[0], args[1]
            # mirrors the real SQL's ON CONFLICT (theme_name, week_start) DO UPDATE — the
            # SQL text itself is pinned separately below so the fake is not the only proof.
            self.store.rows[(theme_name, week_start)] = args
            return "INSERT 0 1"
        return "OK"


class _ResiliencePool:
    def __init__(self, store: _ResilienceStore):
        self.store = store

    @contextlib.asynccontextmanager
    async def acquire(self):
        yield _ResilienceConn(self.store)


def test_rerunning_the_same_week_overwrites_instead_of_duplicating():
    store = _ResilienceStore()
    conn = _ResilienceConn(store)
    ws = date(2026, 9, 14)

    _run(db.write_theme_resilience_weekly_row(
        conn, week_start=ws, theme_name="Widgets", theme_stage="Nascent",
        theme_snapshot_date=date(2026, 9, 13), tickers=["AAA"], n_tickers_covered=1,
        resilience=0.01, as_of_date=date(2026, 9, 14), lookback_days=20,
        resilience_computable=True, not_computable_reason=None,
    ))
    assert len(store.rows) == 1

    # Re-run for the SAME week — recomputed value differs (a real re-run would recompute
    # from fresh data) — must overwrite, not add a second row.
    _run(db.write_theme_resilience_weekly_row(
        conn, week_start=ws, theme_name="Widgets", theme_stage="Accelerating",
        theme_snapshot_date=date(2026, 9, 13), tickers=["AAA", "BBB"], n_tickers_covered=2,
        resilience=0.03, as_of_date=date(2026, 9, 14), lookback_days=20,
        resilience_computable=True, not_computable_reason=None,
    ))
    assert len(store.rows) == 1  # still one row, not two
    saved = store.rows[("Widgets", ws)]
    assert saved[2] == "Accelerating"  # the SECOND call's value won
    assert saved[5] == 2


def test_the_sql_itself_declares_the_idempotency_key():
    assert "ON CONFLICT (theme_name, week_start) DO UPDATE" in db.THEME_RESILIENCE_WEEKLY_INSERT_SQL


def test_end_to_end_rerun_of_record_theme_resilience_weekly_does_not_duplicate(monkeypatch):
    """The full job path (record_theme_resilience_weekly), called twice for the same
    as_of_date, must leave exactly one row per theme."""
    store = _ResilienceStore()
    pool = _ResiliencePool(store)
    themes = [
        {"name": "Theme A", "stage": "Nascent", "theme_date": date(2026, 9, 13),
         "tickers": ["AAA"]},
        {"name": "Theme B", "stage": "Fading", "theme_date": date(2026, 9, 13),
         "tickers": []},
    ]
    monkeypatch.setattr(trs, "get_active_themes", AsyncMock(return_value=themes))
    monkeypatch.setattr(
        trs, "get_down_day_resilience",
        AsyncMock(return_value=[{"ticker": "AAA", "resilience": 0.04}]))
    monkeypatch.setattr(trs, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(trs, "log_audit_event", AsyncMock(return_value=None))

    out1 = _run(trs.record_theme_resilience_weekly(date(2026, 9, 14)))
    out2 = _run(trs.record_theme_resilience_weekly(date(2026, 9, 14)))

    assert out1 == out2 == {"themes": 2, "written": 2, "computable": 1, "not_computable": 1}
    assert len(store.rows) == 2  # two themes, two rows — NOT four after two runs


# ── never skips a theme, even when one theme's row blows up ─────────────────────────────

def test_one_themes_failure_does_not_drop_the_rest_of_the_week(monkeypatch):
    store = _ResilienceStore()
    pool = _ResiliencePool(store)
    themes = [
        {"name": "Before", "stage": "Nascent", "theme_date": date(2026, 9, 13),
         "tickers": ["AAA"]},
        {"name": "Boom", "stage": "Nascent", "theme_date": date(2026, 9, 13),
         "tickers": ["BBB"]},
        {"name": "After", "stage": "Nascent", "theme_date": date(2026, 9, 13),
         "tickers": ["CCC"]},
    ]
    monkeypatch.setattr(trs, "get_active_themes", AsyncMock(return_value=themes))

    async def _fetch(d, tickers, lookback):
        if tickers == ["BBB"]:
            raise RuntimeError("simulated DB hiccup")
        return [{"ticker": tickers[0], "resilience": 0.01}]
    monkeypatch.setattr(trs, "get_down_day_resilience", _fetch)
    monkeypatch.setattr(trs, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(trs, "log_audit_event", AsyncMock(return_value=None))

    out = _run(trs.record_theme_resilience_weekly(date(2026, 9, 14)))
    assert out["themes"] == 3
    assert out["written"] == 2  # Boom's row never got written...
    assert any(k[0] == "Before" for k in store.rows)
    assert any(k[0] == "After" for k in store.rows)  # ...but Before and After still ran
    assert not any(k[0] == "Boom" for k in store.rows)


def test_get_active_themes_failure_degrades_to_zero_without_raising(monkeypatch):
    monkeypatch.setattr(
        trs, "get_active_themes", AsyncMock(side_effect=RuntimeError("pool exhausted")))
    monkeypatch.setattr(trs, "log_audit_event", AsyncMock(return_value=None))
    out = _run(trs.record_theme_resilience_weekly(date(2026, 9, 14)))
    assert out == {"themes": 0, "written": 0, "computable": 0, "not_computable": 0}


# ── (3) the writer statement is registered in the deploy-time preflight gate ────────────

def test_the_writer_is_registered_in_the_deploy_gate():
    from scripts.preflight_db_updates import SHADOW_WRITER_STATEMENTS
    assert any(
        sql is db.THEME_RESILIENCE_WEEKLY_INSERT_SQL for _, sql in SHADOW_WRITER_STATEMENTS)


def test_would_fail_if_unregistered():
    """Prove the guard above actually discriminates — a statement genuinely absent from
    the list must fail it (it is not vacuously true from `any([])`)."""
    from scripts.preflight_db_updates import SHADOW_WRITER_STATEMENTS
    fake_sql = "SELECT 1"
    assert not any(sql is fake_sql for _, sql in SHADOW_WRITER_STATEMENTS)


# ── schema: CREATE carries the columns + the idempotency key (#258 parity) ──────────────

def test_create_table_declares_unique_key_and_never_null_guard_columns():
    src = DB_PY.read_text()
    start = src.index("CREATE TABLE IF NOT EXISTS mi_theme_resilience_weekly")
    block = src[start:src.index(");", start)]
    assert "UNIQUE (theme_name, week_start)" in block
    assert "resilience_computable BOOLEAN NOT NULL DEFAULT TRUE" in block
    assert "not_computable_reason TEXT" in block
    assert "as_of_date DATE NOT NULL" in block
    assert "resilience FLOAT" in block
    assert "tickers TEXT[]" in block


def test_schema_alter_create_parity_has_nothing_to_check_for_a_brand_new_table():
    """This table is NEW — every column ships in the CREATE on day one, so there is no
    ALTER TABLE ... ADD COLUMN for it (the #258 parity gap only exists for columns added
    to an ALREADY-LIVE table after the fact). Pin that: if a later change adds an ALTER
    for this table without also touching CREATE, tests/test_schema_alter_create_parity.py
    (the generic #258 gate) catches it — this just documents why there's nothing here yet."""
    src = DB_PY.read_text()
    assert "ALTER TABLE mi_theme_resilience_weekly" not in src


# ── scheduler: partition classification + slot placement ────────────────────────────────

def test_job_is_intelligence_owned_not_execution_owned():
    assert "theme_resilience_weekly" in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert "theme_resilience_weekly" not in sched.EXECUTION_OWNED_JOB_IDS


_FORBIDDEN_ET_WINDOWS = [((9, 25), (10, 5)), ((16, 0), (17, 0))]


def _in_forbidden_window(hour: int, minute: int) -> bool:
    t = (hour, minute)
    return any(start <= t < end for start, end in _FORBIDDEN_ET_WINDOWS)


def test_scheduled_slot_avoids_the_two_restricted_et_windows():
    src = Path(REPO_ROOT / "agents" / "market_intelligence" / "scheduler.py").read_text()
    m = re.search(
        r'audit_wrap\(_theme_resilience_weekly_job, "theme_resilience_weekly"\),\s*'
        r'CronTrigger\(day_of_week="(\w+)", hour=(\d+), minute=(\d+)',
        src,
    )
    assert m, "theme_resilience_weekly registration not found in the expected shape"
    day, hour, minute = m.group(1), int(m.group(2)), int(m.group(3))
    assert day == "sun"  # weekly, matching the task's other weekly-shadow slot
    assert not _in_forbidden_window(hour, minute), (
        f"scheduled {day} {hour:02d}:{minute:02d} ET falls inside a deploy-restricted window")


def test_forbidden_window_helper_actually_discriminates():
    assert _in_forbidden_window(9, 31)   # inside the ORB window
    assert _in_forbidden_window(16, 30)  # inside the EOD digest window
    assert not _in_forbidden_window(9, 0)
    assert not _in_forbidden_window(10, 5)  # exclusive upper bound


# ── THE LINE: nothing outside recorder + writer + registration reads this table ─────────

_ALLOWED_REFERRERS = {
    "agents/market_intelligence/db.py",
    "agents/market_intelligence/theme_resilience_shadow.py",
    "agents/market_intelligence/scheduler.py",
    "scripts/preflight_db_updates.py",
    "tests/test_644_theme_resilience_weekly.py",
}


_EXCLUDED_DIR_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def test_nothing_outside_the_recorder_reads_or_writes_the_table():
    hits = []
    for path in REPO_ROOT.rglob("*.py"):
        if _EXCLUDED_DIR_PARTS & set(path.parts):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("tests/") and rel != "tests/test_644_theme_resilience_weekly.py":
            continue
        if rel in _ALLOWED_REFERRERS:
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if "mi_theme_resilience_weekly" in text or "theme_resilience_shadow" in text:
            hits.append(rel)
    assert not hits, (
        f"unexpected reference(s) to the #644 resilience shadow outside its recorder — "
        f"THE LINE says records only, nothing may wire it into ranking/scoring/admission: "
        f"{hits}"
    )
