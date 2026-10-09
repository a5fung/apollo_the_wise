"""A column declared and never once written was invisible to every check we had (#543).

Operator found `crypto_btc_dominance.slope_30d`: 97 rows since 2026-04-27, every one NULL,
three months unnoticed. Then: *"we need better dq checks for our tables and data, null checks at
the very least, anomaly detection, row counts, etc."*

**Most of that already existed** — `run_null_rate_sweep` (a populated column going null),
`run_job_liveness_sweep` (a job producing no rows), the #340 row-count drift sweep, and the
L1/L2/L3 anomaly system. `slope_30d` went through two specific holes:

1. `_evaluate_column` SKIPS always-null columns **by design** — its own docstring says
   *"always-null → None (never met the populated bar)"*. Correct for its job (catching a column
   that BROKE), and exactly why it cannot see one that was never wired.
2. `_NULL_SWEEP_TABLES` covers five tables. `crypto_btc_dominance` is not one of them.

So this sweep is the COMPLEMENT, not a replacement. A numeric column 100% NULL across its whole
history on a table with real rows is dead or unwired — **binary, not a rate**.

⚠ **"Near-impossible to false-positive" was WRONG (2026-10-05).** The sweep runs at 17:30 ET and a
column's writer can run minutes later the same evening: 32 of the first 40 pages were that race
(`mi_anticipation_consolidation.orderliness`: paged 17:30:04, its writer filled 106/106 rows at
17:35). It is now a two-step rule — a quiet `dead_column_suspect` row on first sighting, announced
only when a later sweep still sees the column all-NULL on a table written since. The behavioural
tests at the bottom of this file drive that rule through a fake connection across several nights.

First live run: **6 dead columns across 65 tables**, including `mi_stock_scores.market_cap` on
**455,506 rows**.
"""
import pathlib
import re

SRC = pathlib.Path("agents/market_intelligence/health_checks.py").read_text(encoding="utf-8")
SCHED = pathlib.Path("agents/market_intelligence/scheduler.py").read_text(encoding="utf-8")


def _fn() -> str:
    i = SRC.find("async def run_dead_column_sweep")
    assert i > 0, "the dead-column sweep is gone"
    return SRC[i:]


def test_it_detects_NEVER_populated_not_merely_sparse():
    """`count(col)` counts NON-NULL rows. Zero across the whole table is the definition of
    never-written — and it is a different question from the null-RATE sweep's."""
    body = _fn()
    assert re.search(r'count\("\{col\}"\)|count\(\\"', body) or 'count("{col}")' in body, (
        "the sweep no longer counts non-null values per column")


def test_the_audit_log_IS_the_dedupe_state():
    """No new table, and the state survives a restart. Same pattern as `cost_new_lane`."""
    body = _fn()
    assert "FROM mi_audit_log WHERE event_type = 'dead_column_detected'" in body


def test_a_young_table_is_not_judged():
    """A table with a handful of rows has not had a chance to populate anything yet — flagging
    it would be a false positive on day one of any new feature."""
    assert "_DEAD_COL_MIN_ROWS" in SRC
    body = _fn()
    assert "< _DEAD_COL_MIN_ROWS" in body


def test_one_bad_table_cannot_kill_the_sweep():
    """A health guard that dies on the first permission error is a health guard that is off."""
    body = _fn()
    assert "except Exception" in body and 'out["errors"].append' in body


def test_it_actually_runs_nightly():
    """An inert detector is worse than none — this repo has shipped one before."""
    assert "run_dead_column_sweep" in SCHED, "the sweep is not wired into any job"
    seg = SCHED.split("run_dead_column_sweep")[-1][:500]
    assert "except Exception" in seg, (
        "the sweep is not isolated — a failure in it would take down the audit chain it shares "
        "a job with")


def test_the_alert_tells_you_what_to_DO():
    """'Dead column' with no instruction is a puzzle, not an alert."""
    body = _fn()
    assert "wire the writer or drop the column" in body


def test_it_does_not_duplicate_the_null_RATE_sweep():
    """The two answer different questions and both must survive: this one finds NEVER-written,
    the other finds WAS-written-and-broke. Collapsing either into the other reopens a hole."""
    assert "def _evaluate_column" in SRC, "the null-rate evaluator was removed"
    assert "always-null" in SRC, (
        "the null-rate sweep no longer documents that it skips always-null columns — that "
        "comment is the reason this second sweep exists")


# ── BEHAVIOUR: the two-step rule, driven across several nights through a fake connection ──────
#
# The fake is a small stateful stand-in for asyncpg: tables, an audit log, and a clock the test
# advances. The sweep's REAL audit writer (`log_audit_event(..., conn=c)`) runs against it, so a
# suspect row really lands in the same log the next sweep reads back — which is the whole point:
# the bug this rule prevents is a state-machine one (a suspect row mistaken for an announcement).
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import health_checks

_ET = ZoneInfo("America/New_York")
_NIGHT_1 = datetime(2026, 10, 5, 21, 30, tzinfo=timezone.utc)   # Mon 17:30 ET — the sweep's slot
_SOFT = "mi_anticipation_consolidation"
_KEY = f"{_SOFT}.orderliness"


class _FakeDB:
    """tables: {name: {"rows": int, "nonnull": {col: n}, "ts_col": str|None, "last_write": dt|None}}"""

    def __init__(self, tables: dict, now: datetime = _NIGHT_1):
        self.tables, self.now, self.audit = tables, now, []

    def advance(self, **delta):
        self.now += timedelta(**delta)

    async def fetch(self, sql, *args):
        if "FROM information_schema.tables" in sql:
            return [{"table_name": t} for t in sorted(self.tables)]
        if "event_type = 'dead_column_detected'" in sql:
            return [{"summary": s} for (e, s, _d, _t) in self.audit if e == "dead_column_detected"]
        if "event_type = 'dead_column_suspect'" in sql:
            first: dict = {}
            for (e, s, _d, t) in self.audit:
                if e == "dead_column_suspect":
                    first[s] = min(t, first.get(s, t))
            return [{"summary": s, "first_seen": t} for s, t in first.items()]
        if "data_type = ANY" in sql:     # the numeric-columns query
            return [{"column_name": c} for c in self.tables[args[0]]["nonnull"]]
        if "column_name::text = ANY" in sql:   # the write-timestamp-column query
            ts = self.tables[args[0]]["ts_col"]
            return [{"column_name": ts}] if ts else []
        raise AssertionError(f"unexpected fetch: {sql[:90]}")

    async def fetchval(self, sql, *args):
        if sql.startswith("SELECT count(*)") and " WHERE " in sql:   # event-gated: rows in the event state
            return self.tables[sql.split('"')[1]].get("gate_rows", 0)
        if sql.startswith("SELECT count(*)"):
            t = self.tables[sql.split('"')[1]]
            if t.get("boom"):
                raise RuntimeError("permission denied")
            return t["rows"]
        if sql.startswith("SELECT count("):
            return self.tables[sql.split('"')[3]]["nonnull"][sql.split('"')[1]]
        if "SELECT EXISTS" in sql:
            last = self.tables[sql.split('"')[1]]["last_write"]
            return last is not None and last > args[0]
        raise AssertionError(f"unexpected fetchval: {sql[:90]}")

    async def execute(self, sql, *args, timeout=None):
        assert "INSERT INTO mi_audit_log" in sql
        self.audit.append((args[0], args[1], args[2], self.now))

    def events(self, kind=None):
        return [(e, s) for (e, s, _d, _t) in self.audit if kind is None or e == kind]


def _soft_table(**over):
    """The 2026-10-05 table: 106 rows, `orderliness` all NULL, stamped by `created_at`."""
    t = {"rows": 106, "nonnull": {"orderliness": 0}, "ts_col": "created_at", "last_write": None}
    t.update(over)
    return {_SOFT: t}


@pytest.fixture
def telegram(monkeypatch):
    sent: list[str] = []

    async def _send(text, *a, **k):
        sent.append(text)
        return True

    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    return sent


def _run(db, monkeypatch):
    # The no-timestamp rule compares ET calendar days; pin "today" to the fake clock.
    monkeypatch.setattr(health_checks, "et_today", lambda: db.now.astimezone(_ET).date())
    return health_checks.run_dead_column_sweep(db)


@pytest.mark.asyncio
async def test_first_sighting_is_a_QUIET_suspect_row_not_a_page(telegram, monkeypatch):
    """The 10-05 incident: sweep at 17:30:04, writer at 17:35. First sight must not page — and
    the row it leaves must be `dead_column_suspect`, never `dead_column_detected`."""
    db = _FakeDB(_soft_table())
    out = await _run(db, monkeypatch)
    assert db.events() == [("dead_column_suspect", _KEY)]
    assert telegram == []
    assert out["dead"] == [] and [(s["table"], s["column"]) for s in out["suspect"]] == [
        (_SOFT, "orderliness")]


@pytest.mark.asyncio
async def test_still_null_with_a_write_since_is_announced_exactly_once(telegram, monkeypatch):
    """Night 2: column still NULL AND the table took rows after the suspect row → announce. This
    also proves the suspect row does not count as an announcement (the silent-drop bug)."""
    db = _FakeDB(_soft_table())
    await _run(db, monkeypatch)
    db.tables[_SOFT]["last_write"] = db.now + timedelta(minutes=5)   # rows written, column not
    db.advance(days=1)
    out = await _run(db, monkeypatch)
    assert db.events("dead_column_detected") == [("dead_column_detected", _KEY)]
    assert len(telegram) == 1 and _KEY in telegram[0] and "106 rows" in telegram[0]
    assert [d["new"] for d in out["dead"]] == [True] and out["suspect"] == []
    # Night 3: announced on an earlier night — no new row, no second page.
    db.advance(days=1)
    out = await _run(db, monkeypatch)
    assert len(db.events("dead_column_detected")) == 1 and len(telegram) == 1
    assert [d["new"] for d in out["dead"]] == [False]


@pytest.mark.asyncio
async def test_no_rows_written_since_stays_quiet_but_keeps_rechecking(telegram, monkeypatch):
    """'No new rows' is never a final state: quiet tonight, and it announces the night a write
    finally lands without the column."""
    db = _FakeDB(_soft_table(last_write=_NIGHT_1 - timedelta(days=3)))
    await _run(db, monkeypatch)
    for _ in range(3):                                   # three quiet nights, nothing written
        db.advance(days=1)
        out = await _run(db, monkeypatch)
        assert db.events("dead_column_detected") == [] and telegram == []
        assert len(out["suspect"]) == 1 and out["dead"] == []
    assert len(db.events("dead_column_suspect")) == 1    # still ONE suspect row, not one a night
    db.tables[_SOFT]["last_write"] = db.now + timedelta(minutes=5)
    db.advance(days=1)
    await _run(db, monkeypatch)
    assert len(db.events("dead_column_detected")) == 1 and len(telegram) == 1


@pytest.mark.asyncio
async def test_a_column_filled_before_announcement_never_alerts(telegram, monkeypatch):
    """The writer ran at 17:35 and filled all 106 rows (row writes included) — no alert, ever."""
    db = _FakeDB(_soft_table())
    await _run(db, monkeypatch)
    db.tables[_SOFT]["nonnull"]["orderliness"] = 106
    db.tables[_SOFT]["last_write"] = db.now + timedelta(minutes=5)
    for _ in range(3):
        db.advance(days=1)
        out = await _run(db, monkeypatch)
        assert out["dead"] == [] and out["suspect"] == []
    assert db.events("dead_column_detected") == [] and telegram == []


@pytest.mark.asyncio
async def test_a_table_with_no_write_timestamp_announces_on_a_later_ET_day(telegram, monkeypatch):
    """No `updated_at`/`created_at`/… to show a write: one full later sweep is the wait. A re-run
    the same evening (ET) must NOT announce — that is the race all over again."""
    db = _FakeDB(_soft_table(ts_col=None))
    await _run(db, monkeypatch)
    db.advance(minutes=10)                               # same ET evening, 17:40
    await _run(db, monkeypatch)
    assert db.events("dead_column_detected") == [] and telegram == []
    db.advance(days=1)                                   # next ET day
    out = await _run(db, monkeypatch)
    assert db.events("dead_column_detected") == [("dead_column_detected", _KEY)]
    assert len(telegram) == 1 and [d["new"] for d in out["dead"]] == [True]


@pytest.mark.asyncio
async def test_an_already_announced_column_is_never_re_announced(telegram, monkeypatch):
    """Announced once EVER: a pre-existing `dead_column_detected` row suppresses everything —
    no page, and no fresh suspect row either."""
    db = _FakeDB(_soft_table(last_write=_NIGHT_1 + timedelta(days=1)))
    db.audit.append(("dead_column_detected", _KEY, "{}", _NIGHT_1 - timedelta(days=30)))
    out = await _run(db, monkeypatch)
    assert len(db.audit) == 1 and telegram == []
    assert [d["new"] for d in out["dead"]] == [False] and out["suspect"] == []


@pytest.mark.asyncio
async def test_a_young_table_is_not_judged_at_all(telegram, monkeypatch):
    """Under `_DEAD_COL_MIN_ROWS` rows: no suspect row, no page, not even counted as scanned."""
    db = _FakeDB(_soft_table(rows=health_checks._DEAD_COL_MIN_ROWS - 1))
    out = await _run(db, monkeypatch)
    assert db.audit == [] and telegram == [] and out["tables_scanned"] == 0


@pytest.mark.asyncio
async def test_one_bad_table_does_not_stop_the_others_being_checked(telegram, monkeypatch):
    tables = {"mi_aaa_broken": {"rows": 99, "nonnull": {"x": 0}, "ts_col": None,
                                "last_write": None, "boom": True}, **_soft_table()}
    db = _FakeDB(tables)
    out = await _run(db, monkeypatch)
    assert len(out["errors"]) == 1 and "mi_aaa_broken" in out["errors"][0]
    assert db.events() == [("dead_column_suspect", _KEY)]


# ── #695: EVENT-GATED columns (wired, but only filled while a rare event is live) ──────────────
_GATED = "mi_live_fill_counterfactuals"
_GATED_KEY = f"{_GATED}.mark_r"


def _gated_table(**over):
    t = {"rows": 140, "nonnull": {"mark_r": 0}, "ts_col": "created_at", "last_write": None,
         "gate_rows": 0}
    t.update(over)
    return {_GATED: t}


@pytest.mark.asyncio
async def test_an_event_gated_column_is_neither_suspect_nor_dead_while_its_event_is_absent(
        telegram, monkeypatch):
    """`mark_r` is wired (filled only on a 40-session `horizon` arm). With no horizon row, an
    all-NULL column is exactly what a healthy system holds: no audit row, no page, not dead — on
    every night, however many the table has been written since."""
    db = _FakeDB(_gated_table())
    for _ in range(3):
        db.tables[_GATED]["last_write"] = db.now + timedelta(minutes=5)
        out = await _run(db, monkeypatch)
        db.advance(days=1)
        assert out["dead"] == [] and out["suspect"] == []
        assert [(g["table"], g["column"]) for g in out["event_gated"]] == [(_GATED, "mark_r")]
    assert db.audit == [] and telegram == []


@pytest.mark.asyncio
async def test_an_event_gated_column_with_its_event_live_and_still_null_is_a_broken_writer(
        telegram, monkeypatch):
    """The exemption is not a mute: once a `horizon` row exists and `mark_r` is STILL all-NULL,
    the writer is broken — the column goes through the normal two-step and is announced."""
    db = _FakeDB(_gated_table(gate_rows=2))
    out = await _run(db, monkeypatch)
    assert out["event_gated"] == [] and db.events() == [("dead_column_suspect", _GATED_KEY)]
    db.tables[_GATED]["last_write"] = db.now + timedelta(minutes=5)
    db.advance(days=1)
    await _run(db, monkeypatch)
    assert db.events("dead_column_detected") == [("dead_column_detected", _GATED_KEY)]
    assert len(telegram) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("key", sorted(health_checks._DEAD_COL_EVENT_GATED))
async def test_every_event_gated_entry_is_exempt_only_while_its_event_is_absent(
        key, telegram, monkeypatch):
    """Each registered column behaves the same way: exempt with no event rows, counted the moment an
    event row exists and the column is still NULL. An entry cannot become a blanket mute."""
    table, col = key.split(".")
    quiet = _FakeDB({table: {"rows": 100, "nonnull": {col: 0}, "ts_col": None, "last_write": None,
                             "gate_rows": 0}})
    out = await _run(quiet, monkeypatch)
    assert [(g["table"], g["column"]) for g in out["event_gated"]] == [(table, col)]
    assert quiet.audit == [] and out["suspect"] == []
    live = _FakeDB({table: {"rows": 100, "nonnull": {col: 0}, "ts_col": None, "last_write": None,
                            "gate_rows": 1}})
    out = await _run(live, monkeypatch)
    assert out["event_gated"] == [] and live.events() == [("dead_column_suspect", key)]
