"""#312 (2026-10-15/16) — a job that did not exist yet has no slots to miss.

THE INCIDENT. `ladder_watchdog` was registered for the first time by a Thursday-night deploy (empty
ledger, mon-fri 16:17). The #672 sweep read four days of 16:17 slots with nothing near any of them as
four gaps: it re-ran Thursday's and paged Mon-Wed as `unrecoverable`, days before the job existed.

THE FIX under test: the first boot stamps each new job (`mi_audit_log`, event `job_first_seen`) and
`plan_recovery` skips every slot earlier than the stamp. Existing #672 tests model a missed job with an
EMPTY ledger and no stamp — they are the "long-standing" half and are untouched.

Every positive here has its control: the same scenario WITHOUT the stamp must still show the bug, so a
test that passes only because the scenario is vacuous cannot hide behind a green run.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import job_recovery as jr
from agents.market_intelligence import scheduler as sched
from agents.market_intelligence.audit_events import JOB_FIRST_SEEN
from tests.test_672_missed_job_recovery import _Job, _Sched, _daily, _real_job_list

ET = ZoneInfo("America/New_York")
# Thursday 2026-10-15 21:17 ET: the after-hours deploy window the incident booted in.
BOOT = datetime(2026, 10, 15, 21, 17, tzinfo=ET)
NOW = BOOT + timedelta(minutes=2)                     # the boot sweep, 120 s later


def _plan(job, rows=None, first_seen=None, now=NOW):
    return jr.plan_recovery([job], {job.id: rows or []}, now, first_seen=first_seen)


def _kinds(plan):
    return [(d.slot.astimezone(ET).strftime("%a %H:%M"), d.kind) for d in plan]


# ── the planner (pure) ────────────────────────────────────────────────────────────────────

def test_a_new_job_with_no_ledger_is_not_backfilled_for_slots_before_its_first_seen():
    """CONTROL first: with no stamp, the empty-ledger job is the incident — Thursday's 16:17 is a gap
    and Mon-Wed are unrecoverable. With the boot stamp, none of those slots exist for it.
    MUTATION: deleting the `slot < born` skip in plan_recovery reddens the second half."""
    job = _Job("newjob", lambda: None, _daily(16, 17))
    control = _plan(job)
    by_kind = {k for _, k in _kinds(control)}
    assert "gap" in by_kind and "unrecoverable" in by_kind, \
        f"the control no longer reproduces the incident ({_kinds(control)}) - this test proves nothing"

    stamped = _plan(job, first_seen={"newjob": BOOT})
    assert stamped == [], f"slots from before the job existed were still judged: {_kinds(stamped)}"


def test_a_job_first_seen_before_a_slot_is_still_recovered():
    """The stamp only removes slots BEFORE it. A job first seen Monday morning that then missed
    Thursday's 16:17 has a real gap, and Mon-Wed (after the stamp) are judged as ever."""
    job = _Job("newjob", lambda: None, _daily(16, 17))
    monday = datetime(2026, 10, 12, 8, 0, tzinfo=ET)
    plan = _plan(job, first_seen={"newjob": monday})
    kinds = dict(_kinds(plan))
    assert kinds["Thu 16:17"] == "gap", _kinds(plan)
    assert [k for s, k in _kinds(plan) if s.startswith(("Mon", "Tue", "Wed"))] == ["unrecoverable"] * 3, _kinds(plan)


def test_a_slot_exactly_at_the_first_seen_instant_is_kept():
    """Strictly EARLIER is skipped, so the boundary slot (a job registered at its own slot) stays."""
    job = _Job("newjob", lambda: None, _daily(16, 17))
    at_slot = datetime(2026, 10, 15, 16, 17, tzinfo=ET)
    assert _kinds(_plan(job, first_seen={"newjob": at_slot})) == [("Thu 16:17", "gap")]


def test_a_stamp_for_one_job_does_not_touch_another_and_a_missing_stamp_means_long_standing():
    stamped = _Job("a", lambda: None, _daily(16, 17))
    other = _Job("b", lambda: None, _daily(16, 17))
    plan = jr.plan_recovery([stamped, other], {}, NOW, first_seen={"a": BOOT})
    assert {d.job_id for d in plan} == {"b"} and len(plan) == 4, _kinds(plan)


# ── who gets stamped, and only once ───────────────────────────────────────────────────────

def test_only_a_job_with_no_stamp_and_no_pre_boot_ledger_row_is_stamped():
    """History (a row older than the boot) is never new. A row that landed AFTER the boot is not
    history: a job added by this deploy whose real slot falls inside the 120 s boot delay writes a
    ledger row before the sweep runs, and must still be stamped or its pre-deploy slots are paged.
    MUTATION: testing "any ledger row" instead of "a row before boot_at" reddens the race case."""
    row = lambda at: {"started_at": at, "status": "success"}
    rows = {
        "history": [row(BOOT - timedelta(days=3))],
        "race": [row(BOOT + timedelta(seconds=40))],
        "fresh": [],
        "stamped": [],
    }
    got = jr.jobs_needing_first_seen(["history", "race", "fresh", "stamped"], rows,
                                     {"stamped": BOOT - timedelta(days=1)}, BOOT)
    assert got == ["race", "fresh"], got


def test_stamps_read_back_from_audit_rows_take_the_earliest_and_survive_a_bad_detail():
    first, later = BOOT, BOOT + timedelta(days=2)
    rows = [
        {"summary": "a", "detail": later.isoformat(), "created_at": later},
        {"summary": "a", "detail": first.isoformat(), "created_at": first},
        {"summary": "b", "detail": "not a timestamp", "created_at": BOOT},      # falls back to created_at
        {"summary": "c", "detail": "2026-10-15T21:17:00", "created_at": BOOT},  # naive -> created_at
        {"summary": "", "detail": first.isoformat(), "created_at": first},      # no job id -> ignored
    ]
    assert jr.parse_first_seen(rows) == {"a": first, "b": BOOT, "c": BOOT}


def _store(monkeypatch):
    """An in-memory stand-in for the audit table behind the two I/O seams."""
    db, writes = {}, []

    async def fetch():
        return dict(db)

    async def record(job_id, boot_at):
        writes.append((job_id, boot_at))
        db[job_id] = boot_at

    monkeypatch.setattr(jr, "fetch_first_seen", fetch)
    monkeypatch.setattr(jr, "record_first_seen", record)
    return db, writes


def test_the_boot_stamp_is_written_once_and_a_reboot_never_moves_it(monkeypatch):
    """Boot 1 stamps the new job. Boot 2 (same job, still no ledger row, a later boot time) reads the
    stamp and writes nothing; the returned stamp is boot 1's. MUTATION: dropping the `jid in known`
    guard in jobs_needing_first_seen rewrites it at boot 2 and reddens both asserts."""
    db, writes = _store(monkeypatch)
    first, new1 = asyncio.run(jr.ensure_first_seen(["newjob"], {}, BOOT))
    assert new1 == ["newjob"] and first == {"newjob": BOOT} and writes == [("newjob", BOOT)]

    boot2 = BOOT + timedelta(days=1)
    second, new2 = asyncio.run(jr.ensure_first_seen(["newjob"], {}, boot2))
    assert new2 == [] and second == {"newjob": BOOT}, "a reboot moved the first-seen stamp"
    assert writes == [("newjob", BOOT)], f"the stamp was written again: {writes}"


def test_a_failed_stamp_write_still_protects_this_pass_and_is_retried_by_the_next(monkeypatch):
    """`log_audit_event` swallows write errors. The pass must not fall back to back-filling because
    the row did not persist: it carries its own stamp, and the next pass (same process, same boot_at)
    tries again."""
    attempts = []

    async def fetch():
        return {}

    async def failing_record(job_id, boot_at):
        attempts.append(job_id)
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(jr, "fetch_first_seen", fetch)
    monkeypatch.setattr(jr, "record_first_seen", failing_record)
    got, new = asyncio.run(jr.ensure_first_seen(["newjob"], {}, BOOT))
    assert got == {"newjob": BOOT} and new == ["newjob"], "a failed write dropped this pass's protection"
    asyncio.run(jr.ensure_first_seen(["newjob"], {}, BOOT))
    assert attempts == ["newjob", "newjob"], attempts


def test_fetch_first_seen_reads_through_the_existing_audit_reader(monkeypatch):
    seen = {}

    async def fake_get_audit_log(limit=30, event_type=None, since_hours=48, event_type_like=None):
        seen.update(limit=limit, event_type=event_type, since_hours=since_hours)
        return [{"summary": "newjob", "detail": BOOT.isoformat(), "created_at": BOOT}]

    import agents.market_intelligence.db as dbmod
    monkeypatch.setattr(dbmod, "get_audit_log", fake_get_audit_log)
    assert asyncio.run(jr.fetch_first_seen()) == {"newjob": BOOT}
    assert seen["event_type"] == JOB_FIRST_SEEN == "job_first_seen"
    assert seen["since_hours"] >= 5 * 365 * 24, (
        "a stamp records existence, not a run - a bounded read lets it age out, and a job silent past "
        "the window is then stamped a SECOND time (its last four days of slots silently skipped)")


def test_record_first_seen_writes_job_id_and_boot_time_through_log_audit_event(monkeypatch):
    written = []

    async def fake_log(event_type, summary, detail="", **kw):
        written.append((event_type, summary, detail))

    import agents.market_intelligence.db as dbmod
    monkeypatch.setattr(dbmod, "log_audit_event", fake_log)
    asyncio.run(jr.record_first_seen("newjob", BOOT))
    assert written == [(JOB_FIRST_SEEN, "newjob", BOOT.isoformat())]
    assert jr.parse_first_seen([{"summary": "newjob", "detail": written[0][2], "created_at": None}]) == {"newjob": BOOT}


# ── the sweep, end to end ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_sweep_skips_a_new_jobs_earlier_slots_and_says_so(monkeypatch):
    """Whole path with the real audit_wrap: a new daily job, empty ledger, booted Thursday night.
    CONTROL (no boot_at - the long-standing reading): the job IS re-run for Thursday's 16:17 and the
    earlier slots are paged unrecoverable. With boot_at: nothing runs, nothing is terminated, no page,
    and the boot audit row names the job as first seen.
    MUTATION: not passing first_seen into plan_recovery reddens the second half."""
    from core import job_audit
    from core.job_audit import audit_wrap
    ran, terminals, pages, audits = [], [], [], []

    async def f():
        ran.append(1)
    job = _Job("newjob", audit_wrap(f, "newjob"), _daily(16, 17))
    db, writes = _store(monkeypatch)
    monkeypatch.setattr(jr, "fetch_ledger", lambda ids, days=60: asyncio.sleep(0, result={}))

    async def term(job_id, slot, status, reason):
        terminals.append((job_id, status))
    monkeypatch.setattr(jr, "record_terminal", term)
    monkeypatch.setattr(job_audit, "_record_start", lambda *a, **k: asyncio.sleep(0, result=None))
    monkeypatch.setattr(job_audit, "_record_finish", lambda *a, **k: asyncio.sleep(0))

    async def page(t, **k): pages.append(t)
    async def audit(ev, msg, *a): audits.append((ev, msg))

    # control: the incident
    await jr.run_recovery_sweep(_Sched([job]), (), reason="boot", now=NOW, notify=page, audit=audit)
    assert ran == [1] and {s for _, s in terminals} == {"unrecoverable"} and len(terminals) == 3, (ran, terminals)
    assert not writes, "the control (no boot_at) must not touch the stamp store"

    ran.clear(); terminals.clear(); pages.clear(); audits.clear()
    out = await jr.run_recovery_sweep(_Sched([job]), (), reason="boot", now=NOW, notify=page, audit=audit,
                                      boot_at=BOOT)
    assert ran == [] and terminals == [] and pages == [], (ran, terminals, pages)
    assert out["plan"] == [] and out["first_seen_new"] == ["newjob"]
    assert writes == [("newjob", BOOT)]
    assert [e for e, _ in audits] == ["job_recovery_sweep"]
    assert "first seen" in audits[0][1] and "newjob" in audits[0][1], audits

    # the next pass of the same boot: stamp on file, still nothing, nothing re-written
    audits.clear()
    again = await jr.run_recovery_sweep(_Sched([job]), (), reason="periodic", now=NOW + timedelta(minutes=30),
                                        notify=page, audit=audit, boot_at=BOOT)
    assert again["plan"] == [] and again["first_seen_new"] == [] and len(writes) == 1


@pytest.mark.asyncio
async def test_a_new_job_that_then_misses_a_real_slot_is_recovered(monkeypatch):
    """The stamp must not blind the sweep for good: Friday 16:17 comes after the stamp, so a Friday
    miss by the same job is a gap that IS re-run (and the earlier-than-stamp slots still are not)."""
    from core import job_audit
    from core.job_audit import audit_wrap
    ran = []

    async def f():
        ran.append(1)
    job = _Job("newjob", audit_wrap(f, "newjob"), _daily(16, 17))
    _store(monkeypatch)
    monkeypatch.setattr(jr, "fetch_ledger", lambda ids, days=60: asyncio.sleep(0, result={}))
    monkeypatch.setattr(jr, "record_terminal", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr(job_audit, "_record_start", lambda *a, **k: asyncio.sleep(0, result=None))
    monkeypatch.setattr(job_audit, "_record_finish", lambda *a, **k: asyncio.sleep(0))
    quiet = lambda *a, **k: asyncio.sleep(0)

    # boot Thu 21:17 (stamp), then Friday's 16:17 passes with no row; Saturday 02:00 sweep (a weekend
    # day: no session has opened since Friday's slot).
    await jr.run_recovery_sweep(_Sched([job]), (), reason="boot", now=NOW, notify=quiet, audit=quiet, boot_at=BOOT)
    assert ran == []
    sat = datetime(2026, 10, 17, 2, 0, tzinfo=ET)
    out = await jr.run_recovery_sweep(_Sched([job]), (), reason="periodic", now=sat, notify=quiet, audit=quiet,
                                      boot_at=BOOT)
    assert ran == [1], f"the Friday slot after the stamp was not recovered: {[(d.label, d.kind) for d in out['plan']]}"
    assert [d.slot.astimezone(ET).strftime("%a") for d in out["plan"]] == ["Fri"], out["plan"]


def test_the_incident_replays_on_the_real_registered_ladder_watchdog(monkeypatch):
    """The 10-15 shape on the REAL job: the real trigger, an empty ledger, the Thursday-night boot.
    Without the stamp the real job reads as four missed slots; with it, none."""
    scheduler, _ = _real_job_list(monkeypatch)
    eligible, _ = jr.eligible_jobs(scheduler, sched.EXECUTION_OWNED_JOB_IDS)
    job = next(j for j in eligible if j.id == "ladder_watchdog")
    control = _plan(job)
    assert sum(1 for d in control if d.kind in ("gap", "unrecoverable")) >= 4, _kinds(control)
    assert _plan(job, first_seen={"ladder_watchdog": BOOT}) == []


# ── the production wiring ─────────────────────────────────────────────────────────────────

def test_start_scheduler_records_a_tz_aware_boot_time(monkeypatch):
    """`_boot_at` is what the sweep stamps new jobs with. MUTATION: removing the assignment in
    start_scheduler leaves it None and the production sweep silently reverts to the incident."""
    monkeypatch.setattr(sched, "_boot_at", None)
    _real_job_list(monkeypatch)
    assert sched._boot_at is not None and sched._boot_at.tzinfo is not None
    assert abs((datetime.now(ET) - sched._boot_at).total_seconds()) < 600


def test_the_production_wrapper_passes_the_boot_time_to_the_sweep(monkeypatch):
    """MUTATION: dropping `boot_at=_boot_at` from `_run_recovery_sweep` reddens this - and nothing
    else would, because the sweep's default is the old long-standing reading."""
    got = {}

    async def fake_sweep(scheduler, owned, **kw):
        got.update(kw)
        return {}

    monkeypatch.setattr(jr, "run_recovery_sweep", fake_sweep)
    monkeypatch.setattr(sched, "_scheduler", object())
    monkeypatch.setattr(sched, "_boot_at", BOOT)
    asyncio.run(sched._run_recovery_sweep("boot"))
    assert got["boot_at"] == BOOT and got["reason"] == "boot", got
