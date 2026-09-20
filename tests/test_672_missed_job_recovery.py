"""#672 — a job that should have run and did not is RE-RUN, with the date pinned to the day it was due.

THE FACT THAT DECIDES THE DESIGN, pinned first because it corrects what shipped before: APScheduler
emits NO `EVENT_JOB_MISSED` at boot for a slot that is already past. The in-memory jobstore sets
`next_run_time` to the NEXT fire and forgets the slot. On 2026-09-18 every intelligence job in the
17:13–00:16 window was dispatched on time, blocked on the pool before its start row, died with the
restart and was forgotten at boot — so the listener that shipped as the first half of #672 could
never have seen that shape. The only witness that survives a restart is the ledger, and the sweep
under test derives the gap set from it.

Every test here is behavioural: the real scheduler's job list (via the capturing scheduler), the
real `audit_wrap`, the real ContextVar pin, the real httpx hold, prod's REAL 09-16..09-20 ledger
(exported once, `tests/fixtures/672_mi_job_runs_2026-09-16_to_09-20.csv`). No source text is read.
Each states the mutation that reddens it; each was run RED before commit.
"""
from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import job_recovery as jr
from agents.market_intelligence import scheduler as sched
from shared import dates as sd

ET = ZoneInfo("America/New_York")
FIXTURE = Path(__file__).parent / "fixtures" / "672_mi_job_runs_2026-09-16_to_09-20.csv"
RESTART_PLUS_4 = datetime(2026, 9, 19, 0, 20, tzinfo=ET)     # the 00:16 restart, plus the boot delay

# The oracle is DERIVED from the fixture, never hand-named (the hand list is the defect this task
# ends, and one of the 23 job ids may not be spelled in tests/ at all — its own module's test treats
# any mention as a decision-path import): a job that ran Wednesday AND Thursday evening but has no
# Friday evening row is, by the ledger's own word, a Friday miss. PLAN #672 hand-named 23; this
# oracle is what the 23 were an incomplete transcription of.
def _fridays_misses_by_the_ledgers_own_word(rows_by_job: dict[str, list[dict]]) -> set[str]:
    def ran_evening(rows, day):
        return any(r["started_at"].astimezone(ET).date() == day and r["started_at"].astimezone(ET).hour >= 17
                   and r["status"] != "missed" for r in rows)
    wed, thu, fri = (datetime(2026, 9, d).date() for d in (16, 17, 18))
    return {jid for jid, rows in rows_by_job.items()
            if ran_evening(rows, wed) and ran_evening(rows, thu) and not ran_evening(rows, fri)}


# ── helpers ───────────────────────────────────────────────────────────────────────────────

def _real_job_list(monkeypatch):
    """The jobs start_scheduler ACTUALLY registers, with their real triggers, captured at the
    partition pass (before role removal) so both roles' classifications can be exercised."""
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
    return holder["scheduler"], holder["jobs"]


def _fixture_rows() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with FIXTURE.open() as f:
        for r in csv.DictReader(f):
            out.setdefault(r["job_id"], []).append({
                "job_id": r["job_id"],
                "started_at": datetime.fromisoformat(r["started_at"].replace(" ", "T")),
                "status": r["status"], "scheduled_for": None,
                "duration_s": float(r["duration_s"]) if r["duration_s"] else None,
                "error_message": ""})
    return out


class _Job:
    """The four attributes the sweep reads off an APScheduler Job."""
    def __init__(self, jid, func, trigger, grace=None):
        self.id, self.func, self.trigger, self.misfire_grace_time = jid, func, trigger, grace
        self.args, self.kwargs = (), {}


class _Sched:
    def __init__(self, jobs): self._jobs = list(jobs)
    def get_jobs(self): return list(self._jobs)


def _daily(hour, minute, dow="mon-fri"):
    from apscheduler.triggers.cron import CronTrigger
    return CronTrigger(hour=hour, minute=minute, day_of_week=dow, timezone="America/New_York")


# ── 1. the headline fact ──────────────────────────────────────────────────────────────────

def test_apscheduler_forgets_a_past_slot_at_boot_and_emits_no_miss():
    """The reason the #672 listener could not have caught 09-18: a job whose slot passed while the
    process was down (or blocked, then killed) is simply rescheduled for tomorrow at boot.
    `EVENT_JOB_MISSED` never fires for it. Real APScheduler, real trigger, grace 3600.

    This is the empirical basis for deriving gaps from the ledger. If a future APScheduler DOES
    emit the miss at boot, this reddens — and the sweep still holds, because the flush would then
    write a 'missed' row the sweep already treats as a gap."""
    from apscheduler.events import EVENT_JOB_MISSED
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    async def _go():
        s = AsyncIOScheduler(timezone="America/New_York")
        seen = []
        s.add_listener(lambda e: seen.append(e.job_id), EVENT_JOB_MISSED)
        past = datetime.now(ET) - timedelta(hours=2)

        async def job(): pass
        s.add_job(job, _daily(past.hour, past.minute, dow="mon-sun"), id="past", misfire_grace_time=3600)
        s.start()
        nxt = s.get_job("past").next_run_time
        await asyncio.sleep(0.5)
        s.shutdown(wait=False)
        return seen, nxt, past

    seen, nxt, past = asyncio.run(_go())
    assert seen == [], f"APScheduler DID emit a miss at boot ({seen}) — the premise changed; re-read the design"
    assert nxt > datetime.now(ET), f"next_run_time {nxt} is not in the future — the slot 2h ago was {past:%H:%M}"


# ── 2. the derivation, replayed on the REAL incident ledger ───────────────────────────────

def test_the_derivation_reproduces_fridays_gap_set_from_the_real_ledger(monkeypatch):
    """prod's mi_job_runs for 09-16..09-20, the real job list, now = 4 min after the restart.

    The PLAN line hand-named 23 (its 17:13–18:10 window). The derivation finds every one of them
    AND the 18:10–21:30 slots the hand list stopped short of — the population, not the window.
    The 09-16 and 09-17 slots of the same jobs must all read `done` (the matcher works both ways).

    MUTATION: widening `MATCH_BEFORE_S` to a day makes Thursday's run satisfy Friday's slot and
    the gap set collapses — verified RED. Dropping the `scheduled_for is None` guard in
    classify_slot does not change THIS replay (the fixture predates the column) — the
    scheduled_for path is proven in test 5."""
    scheduler, _ = _real_job_list(monkeypatch)
    eligible, excluded = jr.eligible_jobs(scheduler, sched.EXECUTION_OWNED_JOB_IDS)
    rows_by_job = _fixture_rows()
    plan = jr.plan_recovery(eligible, rows_by_job, RESTART_PLUS_4)

    fri = {d.job_id for d in plan if d.kind == "gap" and d.slot.astimezone(ET).date() == datetime(2026, 9, 18).date()}
    oracle = _fridays_misses_by_the_ledgers_own_word(rows_by_job)
    assert len(oracle) >= 20, f"the fixture-derived oracle is only {len(oracle)} — the fixture is not the incident ledger"
    missing = oracle - fri
    assert not missing, f"the ledger says these missed Friday and the derivation did not find them: {sorted(missing)}"
    assert len(fri) >= 30, f"only {len(fri)} Friday gaps — the derivation is narrower than the incident"
    # the derivation may exceed the oracle only with jobs that do not run every weekday (a weekly
    # Friday job, a job added this week) — never with a job that DID run Friday evening.
    ran_friday = {jid for jid, rows in rows_by_job.items()
                  if any(r["started_at"].astimezone(ET).date() == datetime(2026, 9, 18).date()
                         and r["started_at"].astimezone(ET).hour >= 17 and r["status"] != "missed" for r in rows)}
    assert not (fri & ran_friday), f"derived as gap but the ledger shows a Friday run: {sorted(fri & ran_friday)}"

    earlier = [d for d in plan if d.slot.astimezone(ET).date() in
               (datetime(2026, 9, 16).date(), datetime(2026, 9, 17).date())]
    not_done = [d.label for d in earlier if d.kind != "done"]
    assert earlier and not not_done, f"Wed/Thu slots that ran read as something other than done: {not_done[:8]}"


# ── 3. the population is derived, and the three exclusions hold ───────────────────────────

def test_execution_owned_and_sub_daily_jobs_are_never_eligible(monkeypatch):
    """THE LINE and the slot rule, over the real registrations.

    MUTATION: making `fires_at_most_daily` return True unconditionally admits `ep_scan` (*/5) —
    verified RED. Dropping the `owned` check admits `morning_stop_refresh` — verified RED."""
    scheduler, _ = _real_job_list(monkeypatch)
    eligible, excluded = jr.eligible_jobs(scheduler, sched.EXECUTION_OWNED_JOB_IDS)
    ids = {j.id for j in eligible}
    assert not (ids & sched.EXECUTION_OWNED_JOB_IDS), f"execution-owned jobs are eligible: {sorted(ids & sched.EXECUTION_OWNED_JOB_IDS)}"
    for sub_daily in ("ep_scan", "telegram_poll_watchdog", "ecosystem_grace_sweep", "hud_refresh", "missed_job_recovery"):
        assert sub_daily not in ids, f"{sub_daily} fires more than once a day and must not be re-run"
        assert sub_daily in excluded
    for daily in ("evening_briefing", "flag_continuation_scan", "theme_synthesis", "friday_watchlist"):
        assert daily in ids, f"{daily} is a daily intelligence job and must be eligible"
    # PAUSED (registered with next_run_time=None, operator 2026-08-02 "do NOT resurrect a 2-a-day
    # cron"): its trigger still yields a slot every weekday and its ledger has been silent since
    # 07-31 — the replay found it as a "gap" on every day of the fixture. Re-running it would
    # resurrect what he stopped. MUTATION: dropping the `next_run_time is None` branch admits it.
    assert "chart_axis_shadow" not in ids and "paused" in excluded["chart_axis_shadow"]
    assert len(eligible) >= 60


def test_a_job_that_writes_no_ledger_row_is_not_eligible():
    """A miss is undecidable for a job that never records itself. Derived by closure introspection
    of the registered callable, not by name.

    MUTATION: making `writes_ledger` return True admits `bare` here — verified RED."""
    from core.job_audit import audit_wrap

    async def bare(): pass
    async def real(): pass

    s = _Sched([_Job("bare", bare, _daily(17, 0)), _Job("wrapped", audit_wrap(real, "wrapped"), _daily(17, 1))])
    eligible, excluded = jr.eligible_jobs(s, ())
    assert [j.id for j in eligible] == ["wrapped"]
    assert "not audit-wrapped" in excluded["bare"]


# ── 4. the sweep is wired: registered, owned, boot task ───────────────────────────────────

def test_the_sweep_is_registered_intelligence_owned_and_started_at_boot(monkeypatch):
    """MUTATION: deleting the `add_job(... id="missed_job_recovery")` block reddens the first
    assert; deleting `asyncio.create_task(_recovery_sweep_boot())` reddens the last."""
    created = []
    real_create = asyncio.create_task

    def _spy(coro, **kw):
        created.append(getattr(coro, "__name__", repr(coro)))
        return real_create(coro, **kw)

    monkeypatch.setattr(asyncio, "create_task", _spy)
    monkeypatch.setattr(sched, "_RECOVERY_BOOT_DELAY_S", 0)
    monkeypatch.setattr(jr, "run_recovery_sweep",
                        lambda *a, **k: asyncio.sleep(0, result={"eligible": 0, "plan": [], "ran": []}))
    _, jobs = _real_job_list(monkeypatch)
    ids = {j.id for j in jobs}
    assert "missed_job_recovery" in ids, "the periodic recovery sweep is not registered"
    assert "missed_job_recovery" in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert "_recovery_sweep_boot" in created, f"no boot-time recovery task was created; tasks: {created}"


# ── 5. the re-run: the registered callable, through the REAL audit_wrap, pinned ───────────

@pytest.mark.asyncio
async def test_a_gap_is_rerun_through_audit_wrap_with_the_date_pinned_and_the_slot_recorded(monkeypatch):
    """The whole path for one gap: the job sees Friday from `et_today()` (and from
    `last_trading_day()`), its ledger row carries `scheduled_for = slot`, the pin is gone
    afterwards, and the job is no longer in flight.

    MUTATIONS, each verified RED: removing the ContextVar read from `shared.dates.et_today`
    (the job records Sunday); dropping `scheduled_for` from `_record_start`'s INSERT (the
    start row carries None)."""
    from core import job_audit
    from core.job_audit import audit_wrap

    seen, starts = {}, []

    async def friday_job():
        seen["et_today"] = sd.et_today()
        seen["ltd"] = sd.last_trading_day()
        seen["in_flight"] = "friday_job" in job_audit.jobs_in_flight()
        return 7

    class _Conn:
        async def fetchrow(self, sql, *args):
            starts.append(args); return {"id": 1}
        async def execute(self, *a): pass

    class _Pool:
        def acquire(self):
            class _Ctx:
                async def __aenter__(s): return _Conn()
                async def __aexit__(s, *a): return False
            return _Ctx()

    import agents.market_intelligence.db as dbmod
    monkeypatch.setattr(dbmod, "get_pool", lambda: asyncio.sleep(0, result=_Pool()))
    slot = datetime(2026, 9, 18, 17, 25, tzinfo=ET)
    job = _Job("friday_job", audit_wrap(friday_job, "friday_job"), _daily(17, 25))
    disp = jr.Disposition("friday_job", slot, "gap")

    out = await jr.rerun_one(job, disp, bound_s=30)

    assert out.result == "ok", out.detail
    assert seen["et_today"] == slot.date() == seen["ltd"], f"the job read {seen} — not the slot's date"
    assert seen["in_flight"] is True, "audit_run did not register the job as in flight"
    assert starts and starts[-1][2] == slot, f"the start row does not carry scheduled_for=slot: {starts}"
    assert sd.et_today() != slot.date() and sd.recovery_pin() is None, "the pin leaked past the re-run"
    assert "friday_job" not in job_audit.jobs_in_flight()


@pytest.mark.asyncio
async def test_the_pin_reaches_every_binding_the_production_graph_holds_and_refuses_otherwise():
    """The 09-19 probe measured ten modules holding their own `et_today`. Under the pin, every one
    must answer the slot's date — proven each time by calling them, not trusted. A module that
    grew its own copy is caught and the re-run is REFUSED rather than half-pinned.

    MUTATION: removing the ContextVar read from `et_today` makes `bad` non-empty — verified RED."""
    import sys, types
    for m in ("agents.market_intelligence.collector", "agents.market_intelligence.rs_engine",
              "agents.market_intelligence.theme_engine", "agents.market_intelligence.ep_detector"):
        __import__(m)
    holders = [n for n, mod in list(sys.modules.items())
               if n.startswith(jr.PRODUCTION_PREFIXES) and callable(getattr(mod, "et_today", None))]
    assert len(holders) >= 5, f"the walk found only {holders} — it is not looking at the real graph"

    slot = datetime(2026, 9, 18, 17, 25, tzinfo=ET)
    with sd.pinned_recovery("x", slot):
        assert jr.assert_every_binding_pinned(slot.date()) == {}, "a production binding still answers the wall clock"

    rogue = types.ModuleType("agents.market_intelligence._rogue_for_test")
    rogue.et_today = lambda: datetime(2026, 1, 1).date()
    sys.modules[rogue.__name__] = rogue
    try:
        with sd.pinned_recovery("x", slot):
            bad = jr.assert_every_binding_pinned(slot.date())
        assert rogue.__name__ in bad, "a binding that ignores the pin was not caught"

        async def never(): raise AssertionError("must not run under a refused pin")
        disp = await jr.rerun_one(_Job("j", never, _daily(17, 25)), jr.Disposition("j", slot, "gap"), 5)
        assert disp.result == "refused" and "_rogue_for_test" in disp.detail
    finally:
        del sys.modules[rogue.__name__]


# ── 6. Telegrams are HELD at the httpx layer, by default; the flip sends with a banner ────

@pytest.mark.asyncio
async def test_a_send_from_inside_a_rerun_is_held_named_and_never_reaches_telegram(monkeypatch):
    """Any sender — this one nobody listed — posting to api.telegram.org through httpx during a
    re-run is captured, answered with a 200 so the job finishes its data, and NAMED in the summary.
    Outside a pin the same call passes straight through.

    MUTATION: dropping the `pin is None or TELEGRAM_HOST not in url` early-return holds an
    unpinned send too — the pass-through assert reddens. Verified RED."""
    import httpx
    from shared import telegram_hold as th

    th.install_recovery_hold()
    real = httpx.AsyncClient.post.__wrapped__
    posted = []

    async def _fake_real(self, url, *a, **kw):
        posted.append((str(url), kw.get("json")))
        class R: status_code = 200; text = "{}"
        return R()

    monkeypatch.setattr(th, "_HELD", [])
    monkeypatch.setattr(httpx.AsyncClient.post, "__wrapped__", _fake_real, raising=False)
    # the wrapper closed over `real_post`; swap the underlying by re-installing over a stub
    monkeypatch.setattr(httpx.AsyncClient, "_apollo_recovery_hold", False)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_real)
    th.install_recovery_hold()

    async def a_sender_nobody_listed(text):
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post("https://api.telegram.org/bot1:x/sendMessage", json={"chat_id": 1, "text": text})
            return r.status_code

    slot = datetime(2026, 9, 18, 18, 0, tzinfo=ET)
    monkeypatch.delenv(th.SEND_LATE_ENV, raising=False)
    with sd.pinned_recovery("friday_watchlist", slot):
        assert await a_sender_nobody_listed("Friday watchlist body") == 200
    assert posted == [], f"a held send reached the wire: {posted}"
    held = th.drain_held("friday_watchlist")
    assert held and held[0][2] == "sendMessage" and "Friday watchlist body" in held[0][3]

    assert await a_sender_nobody_listed("live alert") == 200
    assert posted and posted[-1][1]["text"] == "live alert", "an UNPINNED send was held — the hold is not context-scoped"

    posted.clear()
    monkeypatch.setenv(th.SEND_LATE_ENV, "1")
    with sd.pinned_recovery("friday_watchlist", slot):
        await a_sender_nobody_listed("Friday watchlist body")
    assert posted and posted[-1][1]["text"].startswith("⏪ LATE RE-RUN"), posted
    assert "friday_watchlist" in posted[-1][1]["text"] and "Fri 09-18 18:00" in posted[-1][1]["text"]

    d = jr.Disposition("friday_watchlist", slot, "gap", result="ok", held=held)
    text = jr.summary_text([d], [], datetime(2026, 9, 19, 0, 21, tzinfo=ET))
    assert "WITHHELD" in text and "Friday watchlist body" in text and "APOLLO_RECOVERY_SEND_LATE" in text


# ── 7. the one freshness rule, and the guards around a re-run ─────────────────────────────

def test_a_slot_is_recoverable_until_the_next_market_session_opens_and_not_after():
    """Friday 17:35 → recoverable Saturday, Sunday and Monday 08:00; unrecoverable Monday 10:00.
    A Monday 17:35 miss found Tuesday 08:00 is recoverable; found Tuesday 10:00 it is not.

    MUTATION: deleting the `sessions_opened_between` check in classify_slot turns every
    'unrecoverable' below into 'gap' — verified RED."""
    fri = datetime(2026, 9, 18, 17, 35, tzinfo=ET)
    for now, kind in ((datetime(2026, 9, 19, 0, 20, tzinfo=ET), "gap"),
                      (datetime(2026, 9, 20, 15, 0, tzinfo=ET), "gap"),
                      (datetime(2026, 9, 21, 8, 0, tzinfo=ET), "gap"),
                      (datetime(2026, 9, 21, 10, 0, tzinfo=ET), "unrecoverable")):
        d = jr.classify_slot("j", fri, 1, [], now)
        assert d.kind == kind, f"{now:%a %H:%M}: {d.kind} — {d.detail}"
    mon = datetime(2026, 9, 21, 17, 35, tzinfo=ET)
    assert jr.classify_slot("j", mon, 1, [], datetime(2026, 9, 22, 8, 0, tzinfo=ET)).kind == "gap"
    assert jr.classify_slot("j", mon, 1, [], datetime(2026, 9, 22, 10, 0, tzinfo=ET)).kind == "unrecoverable"
    assert jr.sessions_opened_between(fri, datetime(2026, 9, 25, 12, 0, tzinfo=ET)) == 5


def test_a_slot_inside_market_hours_is_a_moment_and_is_never_rerun():
    """The 09:31 open scan (which feeds the entry path), the 10:00 digests, the 15:55 pre-close
    check: no session opens AFTER them until tomorrow, so the freshness rule alone would re-run
    them later the same day against a different market. A pre-open 09:00 slot found at 09:20 and
    an after-close 16:12 slot found at 20:00 are still gaps.

    MUTATION: deleting the `slot_is_in_session` branch in classify_slot turns the 09:31 case
    into 'gap' — verified RED."""
    fri = datetime(2026, 9, 18, tzinfo=ET)
    for hh, mm, at, kind in ((9, 31, (10, 20), "unrecoverable"), (10, 0, (11, 0), "unrecoverable"),
                             (15, 55, (16, 30), "unrecoverable"), (9, 0, (9, 20), "gap"), (16, 12, (20, 0), "gap")):
        d = jr.classify_slot("j", fri.replace(hour=hh, minute=mm), 1, [], fri.replace(hour=at[0], minute=at[1]))
        assert d.kind == kind, f"{hh}:{mm:02d} seen at {at}: {d.kind} — {d.detail}"
    assert "moment" in jr.classify_slot("j", fri.replace(hour=9, minute=31), 1, [], fri.replace(hour=10, minute=20)).detail
    sat = datetime(2026, 9, 19, 10, 0, tzinfo=ET)
    assert not jr.slot_is_in_session(sat), "a weekend 10:00 slot is not inside a session"


def test_attempts_in_flight_recent_and_terminal_rows_each_stop_a_rerun():
    """MUTATION: dropping `attempts >= MAX_ATTEMPTS` makes the exhausted case a gap; dropping the
    in-flight check makes that case a gap; dropping the TERMINAL check re-examines an
    'unrecoverable' row forever. Each verified RED."""
    slot = datetime(2026, 9, 18, 17, 35, tzinfo=ET)
    now = datetime(2026, 9, 19, 0, 20, tzinfo=ET)
    failed = [{"started_at": now - timedelta(minutes=i), "status": "failed", "scheduled_for": slot}
              for i in (1, 2, 3)]
    assert jr.classify_slot("j", slot, 1, failed, now).kind == "exhausted"
    assert jr.classify_slot("j", slot, 1, failed[:2], now).kind == "gap"
    assert jr.classify_slot("j", slot, 1, failed[:2] + [{"started_at": now, "status": "success", "scheduled_for": slot}], now).kind == "done"
    assert jr.classify_slot("j", slot, 1, [], now, in_flight={"j"}).kind == "in_flight"
    assert jr.classify_slot("j", slot, 1, [{"started_at": now, "status": "unrecoverable", "scheduled_for": slot,
                                            "error_message": "x"}], now).kind == "unrecoverable"
    assert jr.classify_slot("j", slot, 1, [{"started_at": slot + timedelta(seconds=3), "status": "running",
                                            "scheduled_for": None}], now).kind == "done"
    assert jr.classify_slot("j", slot, 1, [], slot + timedelta(seconds=90)).kind == "young"
    assert jr.classify_slot("j", slot, 3600, [], slot + timedelta(minutes=30)).kind == "young", "grace counts toward young"
    assert jr.classify_slot("j", slot, 1, [], slot + timedelta(minutes=5)).kind == "gap"
    assert jr.classify_slot("j", slot, 1, [], now, next_fire=now + timedelta(minutes=5), bound_s=600).kind == "too_close"
    assert jr.classify_slot("j", slot, 1, [{"started_at": slot, "status": "missed", "scheduled_for": slot}], now).kind == "gap"


@pytest.mark.asyncio
async def test_the_sweep_defers_inside_the_orb_window_and_re_runs_gaps_in_slot_order(monkeypatch):
    """End to end over a tiny scheduler: two gaps, one done, one execution-owned; the ORB window
    defers everything; outside it the two gaps run oldest first, each pinned, and ONE summary goes
    out. MUTATION: removing `in_orb_quiet_window` from run_recovery_sweep reddens the first half;
    removing the `plan.sort` runs them out of order — both verified RED."""
    from core.job_audit import audit_wrap
    order, pages, audits = [], [], []

    def mk(name):
        async def f():
            order.append((name, sd.et_today()))
        return audit_wrap(f, name)

    async def exec_job(): order.append(("exec", None))
    jobs = [_Job("late", mk("late"), _daily(17, 50)), _Job("early", mk("early"), _daily(17, 15)),
            _Job("ran", mk("ran"), _daily(17, 0)), _Job("stop_refresh", audit_wrap(exec_job, "stop_refresh"), _daily(9, 35))]
    fri = datetime(2026, 9, 18, tzinfo=ET)
    rows = {"ran": [{"started_at": fri.replace(hour=17, minute=0, second=2), "status": "success", "scheduled_for": None, "duration_s": 3}]}
    monkeypatch.setattr(jr, "fetch_ledger", lambda ids, days=60: asyncio.sleep(0, result=rows))
    monkeypatch.setattr(jr, "record_terminal", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr(jr, "LOOKBACK_DAYS", 1)
    import core.job_audit as ja
    monkeypatch.setattr(ja, "_record_start", lambda *a, **k: asyncio.sleep(0, result=None))
    monkeypatch.setattr(ja, "_record_finish", lambda *a, **k: asyncio.sleep(0))

    async def page(t, **k): pages.append(t)
    async def audit(ev, msg, *a): audits.append((ev, msg))

    quiet = await jr.run_recovery_sweep(_Sched(jobs), {"stop_refresh"}, reason="periodic",
                                        now=datetime(2026, 9, 18, 9, 40, tzinfo=ET), notify=page, audit=audit)
    assert quiet["quiet"] and not order, "a re-run happened inside the ORB window"

    out = await jr.run_recovery_sweep(_Sched(jobs), {"stop_refresh"}, reason="boot",
                                      now=datetime(2026, 9, 19, 0, 20, tzinfo=ET), notify=page, audit=audit)
    assert [n for n, _ in order] == ["early", "late"], order
    assert all(d == fri.date() for _, d in order), f"a re-run saw the wrong date: {order}"
    assert "stop_refresh" in out["excluded"]
    assert len(pages) == 1 and "2 re-run OK" in pages[0], pages
    assert [e for e, _ in audits] == ["job_recovery_sweep", "jobs_recovered"], audits
    assert "1 eligible" not in audits[0][1] and "3 eligible" in audits[0][1]


@pytest.mark.asyncio
async def test_recording_a_burst_of_misses_kicks_the_sweep(monkeypatch):
    """The listener's flush no longer stops at recording. MUTATION: deleting the
    `_kick_recovery_sweep("missed")` line in `_flush_missed_jobs` reddens this."""
    kicked = []
    monkeypatch.setattr(sched, "_kick_recovery_sweep", lambda reason: kicked.append(reason))
    monkeypatch.setattr(sched, "_MISSED_FLUSH_DELAY_S", 0)
    import agents.market_intelligence.db as dbmod
    monkeypatch.setattr(dbmod, "get_pool", lambda: asyncio.sleep(0, result=None))   # rows fail loud, alert still goes
    monkeypatch.setattr(dbmod, "log_audit_event", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr(sched, "notify_owner", lambda m, **k: asyncio.sleep(0))
    sched._missed_buffer[:] = [("evening_briefing", datetime(2026, 9, 18, 18, 0, tzinfo=ET))]
    await sched._flush_missed_jobs()
    assert kicked == ["missed"]


def test_bound_is_sized_from_history_never_below_ten_minutes():
    rows = [{"status": "success", "duration_s": d} for d in (700, 800, 900, 1000, 1070)]
    assert jr.bound_for(rows) == 3 * 1070
    assert jr.bound_for([{"status": "success", "duration_s": 2}]) == jr.BOUND_MIN_S
    assert jr.bound_for([]) == jr.BOUND_DEFAULT_S
    assert jr.bound_for([{"status": "success", "duration_s": 99999}]) == jr.BOUND_MAX_S
