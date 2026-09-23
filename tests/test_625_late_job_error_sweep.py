"""#625 — no job may be scheduled after the silent-error sweep.

The generic error surfacer (`_check_nightly_silent_errors`) used to run ONCE, at the end
of the 17:00 ET nightly pull, on a fixed 2-hour lookback. Every job registered later —
the four recorders at 18:04-18:15, the 21:00 position backstop — fired after the only
thing that would have shouted about their errors, so none of them had ever been covered.
That is how #593 errored on 95 of 95 candidates while its job reported success.

Two mechanisms now close it, and this file guards the second:
  1. a WATERMARK lookback, so an event can surface late but cannot fall between sweeps;
  2. a LATE sweep at 21:30 ET, after everything else — which only works while it really
     is last. This test fails the build the moment someone registers a later job.
"""
import re

import pytest


def _scheduler_source() -> str:
    with open("agents/market_intelligence/scheduler.py", encoding="utf-8") as fh:
        return fh.read()


_SWEEP_HOUR, _SWEEP_MIN = 21, 30


def _cron_jobs():
    """(hour, minute, id) for every ACTIVE scheduled cron job.

    Walks `_scheduler.add_job(` blocks rather than regex-scanning for CronTrigger. The
    first version of this helper used one regex with a trailing `.{0,200}` to find the
    job id, and that trailing group CONSUMED the next add_job block — so triggers were
    swallowed in pairs and a deliberately-planted 22:15 job went unseen. The guard passed
    while being unable to fail. Block-walking cannot do that: each block is bounded by the
    next `add_job(`, so every one is examined exactly once.
    """
    src = _scheduler_source()
    jobs = []
    blocks = src.split("_scheduler.add_job(")[1:]
    for block in blocks:
        head = block[:600]
        # a commented-out registration: every line of the trigger is behind a '#'
        cron = re.search(
            r"^(?P<indent>[^\S\n]*)(?P<hash>#?)\s*CronTrigger\(\s*hour=(?P<h>\d+)\s*,"
            r"\s*minute=(?P<m>\d+)",
            head, re.MULTILINE)
        if not cron or cron.group("hash"):
            continue
        jid = re.search(r"\n\s*id=(?P<id>[^,\n]+)", head)
        jobs.append((int(cron.group("h")), int(cron.group("m")),
                     (jid.group("id").strip() if jid else "?")))
    return jobs


def test_the_sweep_is_still_the_last_job_of_the_day():
    later = [
        (h, mi, jid) for (h, mi, jid) in _cron_jobs()
        if (h, mi) > (_SWEEP_HOUR, _SWEEP_MIN)
    ]
    assert not later, (
        "A job is now scheduled AFTER the #625 silent-error sweep "
        f"({_SWEEP_HOUR}:{_SWEEP_MIN:02d} ET), so its errors are invisible to the only "
        f"generic surfacer we have: {later}. Move the sweep later than the new job "
        "(and update _SWEEP_HOUR/_SWEEP_MIN here), or the #593 class returns."
    )


def test_the_sweep_is_actually_registered():
    src = _scheduler_source()
    assert "id=JOB_SILENT_ERROR_SWEEP" in src, "the late sweep is not registered"
    assert re.search(
        r"CronTrigger\(hour=21, minute=30[^)]*\)\s*,\s*\n\s*id=JOB_SILENT_ERROR_SWEEP", src
    ), "the late sweep is not at the 21:30 ET slot this test guards"


def test_we_found_a_plausible_number_of_cron_jobs():
    """Guard the guard: a regex that matches nothing would make the test above vacuous."""
    jobs = _cron_jobs()
    assert len(jobs) > 25, f"only found {len(jobs)} cron jobs — the parser is broken"


@pytest.mark.asyncio
async def test_the_lookback_is_a_watermark_not_a_fixed_window(monkeypatch):
    """The sweep must ask for 'everything since I last ran', clamped, not a fixed 2h."""
    from agents.market_intelligence import scheduler as sch

    seen: list[float] = []

    async def fake_hours(job_name, default_hours=24):
        return 9.0  # e.g. the previous evening's sweep

    async def fake_audit(limit=40, event_type=None, since_hours=48, event_type_like=None):
        seen.append(float(since_hours))
        return []

    monkeypatch.setattr("agents.market_intelligence.db.hours_since_job_last_ran", fake_hours)
    monkeypatch.setattr(sch, "get_audit_log", fake_audit)
    monkeypatch.setattr(sch, "log_job_run", lambda *a, **k: _noop())

    await sch._check_nightly_silent_errors()

    assert seen, "the sweep issued no audit queries"
    assert 10.0 in seen, f"expected a 9h watermark + 1h margin = 10h lookback, got {seen}"
    assert 2.0 not in seen, "still using the old fixed 2-hour window"


async def _noop():
    return None
