"""The 09:00 ET EP scan runs ONCE per weekday, not twice (operator "Ok" 2026-10-17).

THE BUG. `_morning_briefing_job` (CronTrigger 09:00 ET) calls `_ep_scan_job()` first so the brief
reads a fresh scan; the `ep_scan` job's old `CronTrigger(hour="7-9", minute="*/5")` ALSO fired at
09:00:00. Two full scans at the same instant: duplicate API/LLM work, and both read `already_alerted`
before either scan has written. The brief keeps its scan; the cron
tick is dropped (`scheduler._ep_scan_trigger`: an OrTrigger of 07:00-08:55 and 09:05-09:55).

WHAT IS PINNED, all off the jobs `start_scheduler` ACTUALLY registers (never a reconstructed
trigger):
  1. the full weekday fire set of `ep_scan` - 35 ticks, no 09:00, no 10:00, 09:30-09:55 intact
  2. exactly ONE scan starts at 09:00 - DERIVED from the registered jobs whose callable is
     `_ep_scan_job` plus the morning brief (which calls it), never a hand list
  3. the consumers that read the schedule stay correct: the missed-job recovery population
     (`fires_at_most_daily` is False for an OrTrigger - no `.fields`), slot derivation (no 09:00
     slot exists to be "missed"), and the 10:05 watchdog (counts `ep_scan` success rows - 35 remain)

MUTATION (verified RED): restoring `hour="7-9", minute="*/5"` in `_ep_scan_trigger` fails (1), (2)
and the 35-tick count; making `fires_at_most_daily` admit an OrTrigger fails (3a).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import job_recovery as jr
from agents.market_intelligence import scheduler as sched
from tests.conftest import make_mock_pool

ET = ZoneInfo("America/New_York")

# A Monday in EDT and a Monday in EST - the ticks must stay on the ET wall clock across the DST
# change (a UTC-keyed trigger would shift by an hour in one of them).
MON_EDT = datetime(2026, 10, 19, tzinfo=ET)
MON_EST = datetime(2026, 11, 2, tzinfo=ET)
SAT = datetime(2026, 10, 17, tzinfo=ET)

_EXPECTED_HHMM = (
    [(h, m) for h in (7, 8) for m in range(0, 60, 5)]
    + [(9, m) for m in range(5, 60, 5)]
)


def _registered_jobs(monkeypatch):
    """The jobs start_scheduler registers, with their real triggers (captured at the partition
    pass, before any role removal) - the same capture test_672 uses."""
    from tests.test_job_partition import _CapturingScheduler
    monkeypatch.setattr(sched, "AsyncIOScheduler", _CapturingScheduler)
    holder = {}
    real = sched._apply_role_partition

    def _spy(scheduler, role):
        holder["jobs"] = list(scheduler.get_jobs())
        holder["scheduler"] = scheduler
        return real(scheduler, role)

    monkeypatch.setattr(sched, "_apply_role_partition", _spy)

    async def _go():
        sched.start_scheduler()

    asyncio.run(_go())
    return holder["scheduler"], {j.id: j for j in holder["jobs"]}


def _fires(trigger, day: datetime, start=(0, 0), end=(23, 59)) -> list[datetime]:
    """The trigger's own fire times on `day` within [start, end] ET - its arithmetic, not ours."""
    lo = day.replace(hour=start[0], minute=start[1]) - timedelta(seconds=1)
    hi = day.replace(hour=end[0], minute=end[1], second=59)
    out, cursor = [], lo
    while True:
        n = trigger.get_next_fire_time(None, cursor)
        if n is None or n > hi:
            return out
        out.append(n)
        cursor = n + timedelta(seconds=1)


def _hhmm(ts: list[datetime]) -> list[tuple[int, int]]:
    return [(t.astimezone(ET).hour, t.astimezone(ET).minute) for t in ts]


# ── 1. the full weekday fire set ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("day", [MON_EDT, MON_EST], ids=["EDT", "EST"])
def test_ep_scan_fires_35_times_every_five_minutes_except_0900(monkeypatch, day):
    _, jobs = _registered_jobs(monkeypatch)
    ts = _fires(jobs["ep_scan"].trigger, day)
    got = _hhmm(ts)
    assert got == _EXPECTED_HHMM, f"ep_scan ticks differ from 07:00-08:55 + 09:05-09:55: {got}"
    assert len(ts) == 35
    assert (9, 0) not in got, "a 09:00 ep_scan tick is the duplicate of the morning brief's own scan"
    assert (10, 0) not in got and (9, 30) in got and (9, 35) in got and (9, 55) in got
    assert all(t.second == 0 and t.microsecond == 0 for t in ts)
    assert all(t.utcoffset() == day.replace(hour=t.hour, minute=t.minute).utcoffset() for t in ts), "ticks are not on the ET wall clock"


def test_no_ep_scan_on_a_weekend(monkeypatch):
    _, jobs = _registered_jobs(monkeypatch)
    sat_sun = _fires(jobs["ep_scan"].trigger, SAT) + _fires(jobs["ep_scan"].trigger, SAT + timedelta(days=1))
    assert sat_sun == []
    nxt = jobs["ep_scan"].trigger.get_next_fire_time(None, SAT)
    assert nxt == datetime(2026, 10, 19, 7, 0, tzinfo=ET)


def test_registration_keeps_id_grace_and_et_timezones(monkeypatch):
    _, jobs = _registered_jobs(monkeypatch)
    job = jobs["ep_scan"]
    assert job.misfire_grace_time == 300
    assert "ep_scan" in sched.INTELLIGENCE_OWNED_JOB_IDS and "ep_scan" not in sched.EXECUTION_OWNED_JOB_IDS
    children = job.trigger.triggers
    assert len(children) == 2
    assert all(str(c.timezone) == "America/New_York" for c in children)
    assert all("day_of_week='mon-fri'" in str(c) for c in children)


def test_the_open_and_stop_boundaries_are_untouched(monkeypatch):
    """ep_scan_open 09:31, ep_scan_stop 10:00, the watchdog 10:05 - and the ep_scan ticks inside the
    ORB window / the 09:45-09:59 out-of-window span are exactly the pre-change ones."""
    _, jobs = _registered_jobs(monkeypatch)
    one = lambda jid: _hhmm(_fires(jobs[jid].trigger, MON_EDT))
    assert one("ep_scan_open") == [(9, 31)]
    assert one("ep_scan_stop") == [(10, 0)]
    assert one("ep_scan_watchdog") == [(10, 5)]
    assert _hhmm(_fires(jobs["ep_scan"].trigger, MON_EDT, (9, 30), (9, 59))) == [
        (9, 30), (9, 35), (9, 40), (9, 45), (9, 50), (9, 55)]
    assert _hhmm(_fires(jobs["ep_scan"].trigger, MON_EDT, (9, 56), (23, 59))) == []


# ── 2. exactly one scan starts at 09:00 - DERIVED, not hand-listed ────────────────────────

def test_exactly_one_scan_starts_at_0900(monkeypatch):
    """Scan starters = every registered job whose callable IS `_ep_scan_job` (audit_wrap keeps the
    wrapped function's __name__) + the morning brief, which calls it inline. Derived from the
    registrations so a NEW job that also scans at 09:00 reddens this."""
    _, jobs = _registered_jobs(monkeypatch)
    direct = {jid for jid, j in jobs.items() if getattr(j.func, "__name__", "") == "_ep_scan_job"}
    assert {"ep_scan", "ep_scan_open"} <= direct
    # the brief's own call to `_ep_scan_job` is exercised by test_the_brief_runs_exactly_one_scan_...
    assert getattr(jobs["morning_briefing"].func, "__name__", "") == "_morning_briefing_job"
    starters = direct | {"morning_briefing"}

    at_0900 = sorted(
        jid for jid in starters
        if (9, 0) in _hhmm(_fires(jobs[jid].trigger, MON_EDT, (9, 0), (9, 0)))
    )
    assert at_0900 == ["morning_briefing"], (
        f"{at_0900} all start an EP scan at 09:00 ET - the same instant, so the scan runs more than once")


@pytest.mark.asyncio
async def test_the_brief_runs_exactly_one_scan_before_it_sends():
    """The other half of "one scan at 09:00": with the cron tick gone, the brief's own scan is the
    09:00 scan. Behavioural - the brief is RUN with its collaborators replaced, and must call
    `_ep_scan_job` once, before it sends (so it reads fresh alerts).

    MUTATION: deleting the `await _ep_scan_job()` line from `_morning_briefing_job` reddens this
    (and the 09:00 scan silently disappears, since the cron no longer fires it)."""
    order = []

    async def _scan():
        order.append("scan")

    async def _send():
        order.append("send")

    ok = AsyncMock(return_value={"status": "ok"})
    with patch.object(sched, "_ep_scan_job", new=_scan), \
         patch.object(sched, "send_morning_briefing", new=_send), \
         patch.object(sched, "log_job_run", new=AsyncMock()), \
         patch("agents.market_intelligence.health_checks.run_health_heartbeat", new=ok), \
         patch("agents.market_intelligence.health_checks.run_evening_verify_heartbeat", new=ok):
        await sched._morning_briefing_job()
    assert order == ["scan", "send"], f"the brief's 09:00 scan sequence is {order}"


# ── 3. the consumers of the schedule stay correct ─────────────────────────────────────────

def test_recovery_still_treats_ep_scan_as_sub_daily_and_has_no_0900_slot(monkeypatch):
    scheduler, jobs = _registered_jobs(monkeypatch)
    job = jobs["ep_scan"]
    # (a) an OrTrigger has no `.fields` -> not "at most daily" -> never in the re-run population
    assert not hasattr(job.trigger, "fields")
    assert jr.fires_at_most_daily(job.trigger) is False
    eligible, excluded = jr.eligible_jobs(scheduler, sched.EXECUTION_OWNED_JOB_IDS)
    assert "ep_scan" not in {j.id for j in eligible}
    assert "more than once a day" in excluded["ep_scan"]
    # (b) even if it WERE swept, the trigger derives no 09:00 slot, so no 09:00 gap can be named
    now = datetime(2026, 10, 19, 9, 30, tzinfo=ET)
    slots = _hhmm(jr.past_slots(job.trigger, now, lookback_days=1))
    assert (9, 0) not in slots and (8, 55) in slots and (9, 5) in slots and (9, 30) in slots
    plan = jr.plan_recovery([job], {}, now)
    assert (9, 0) not in [(d.slot.astimezone(ET).hour, d.slot.astimezone(ET).minute) for d in plan]


def test_the_scheduler_cannot_catch_up_into_a_0900_run(monkeypatch):
    """EVENT_JOB_MISSED is raised for a scheduled run time that is past its grace. The run times
    APScheduler derives for ep_scan never include 09:00, however it asks."""
    _, jobs = _registered_jobs(monkeypatch)
    trig = jobs["ep_scan"].trigger
    nine_05 = datetime(2026, 10, 19, 9, 5, tzinfo=ET)
    assert trig.get_next_fire_time(None, datetime(2026, 10, 19, 8, 59, 59, tzinfo=ET)) == nine_05
    assert trig.get_next_fire_time(datetime(2026, 10, 19, 8, 55, tzinfo=ET), datetime(2026, 10, 19, 9, 2, tzinfo=ET)) == nine_05
    assert trig.get_next_fire_time(None, datetime(2026, 10, 19, 9, 0, tzinfo=ET)) == nine_05
    assert trig.get_next_fire_time(datetime(2026, 10, 19, 9, 55, tzinfo=ET), datetime(2026, 10, 19, 9, 56, tzinfo=ET)) \
        == datetime(2026, 10, 20, 7, 0, tzinfo=ET)


def _watchdog_ledger(day: datetime) -> list[dict]:
    """A weekday's mi_job_runs as the post-change schedule writes it: the 35 ep_scan ticks (all
    success - `_ep_scan_job` swallows its own errors), ep_scan_open, and the brief's own row
    (the brief's inline scan is NOT an `ep_scan` ledger row; it records under `morning_briefing`)."""
    rows = [{"job_id": "ep_scan", "status": "success", "started_at": t}
            for t in _fires(_real_ep_scan_trigger(), day)]
    rows.append({"job_id": "ep_scan_open", "status": "success", "started_at": day.replace(hour=9, minute=31)})
    rows.append({"job_id": "morning_briefing", "status": "success", "started_at": day.replace(hour=9, minute=0)})
    return rows


def _real_ep_scan_trigger():
    return sched._ep_scan_trigger()


@pytest.mark.asyncio
async def test_watchdog_stays_silent_on_the_post_change_ledger():
    """The 10:05 watchdog counts `ep_scan` success rows today. With no 09:00 tick the day still
    holds 35, so a normal morning does not page - the dropped slot is not read as a missed run."""
    rows = _watchdog_ledger(MON_EDT)
    seen = {}

    async def _fetchval(sql, *args):
        if "FROM mi_job_runs" in sql and "job_id = 'ep_scan'" in sql:
            n = sum(1 for r in rows if r["job_id"] == "ep_scan" and r["status"] == "success"
                    and r["started_at"].astimezone(ET).date() == args[0])
            seen["scan_count"] = n
            return n
        return 0                                    # alert_count: a quiet morning

    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=_fetchval)
    conn.fetch = AsyncMock(return_value=[])
    sent = []

    async def _fake_send(text, *a, **k):
        sent.append(text)

    market_status = MagicMock(is_trading_day=True, reason="open")
    with patch.object(sched, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(sched, "send_telegram_message", new=_fake_send), \
         patch.object(sched, "log_audit_event", new=AsyncMock()), \
         patch.object(sched, "get_market_status", return_value=market_status), \
         patch.object(sched, "datetime") as _dt:
        _dt.now.return_value = datetime(2026, 10, 19, 10, 5, tzinfo=ET)
        await sched._ep_scan_watchdog()

    assert seen["scan_count"] == 35, "the watchdog should see the 35 cron ticks, not 36"
    assert sent == [], f"the watchdog paged on a normal post-change morning: {sent}"
