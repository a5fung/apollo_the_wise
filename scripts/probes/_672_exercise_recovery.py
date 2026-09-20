"""#672 — EXERCISE the missed-job recovery, two ways. A guard that has never fired is not proven.

  python3 scripts/probes/_672_exercise_recovery.py simulate
      Off-prod, no DB, no network. Builds a real APScheduler-shaped job list with three real
      `audit_wrap`-wrapped jobs and ONE that posts to api.telegram.org through its own httpx client
      (the shape that reached the operator twice on 09-20), deletes the ledger rows for a Friday
      slot to simulate the 09-18 stall, and runs the REAL sweep with the REAL pin and the REAL httpx
      hold. Prints what re-ran, what date each job saw, the `scheduled_for` each ledger row
      carries, and what was withheld. Every Telegram attempt is refused at the wire by
      `scripts/probes/_muzzle.py` when present, in addition to the hold.

  docker exec apollo-market python3 scripts/probes/_672_exercise_recovery.py dry-run
      IN PROD, READ-ONLY. Derives the eligible population from the running process's own job
      registrations and classifies every slot in the lookback against the live ledger. Executes
      NOTHING, writes NOTHING. This is the verify-live tool: the day it deploys it should list the
      registered sweep, 60+ eligible jobs, and every slot as `done` — and after any real stall it
      shows exactly what the next pass would re-run.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root, so `core`/`shared` import from anywhere
ET = ZoneInfo("America/New_York")


# ── simulate ──────────────────────────────────────────────────────────────────────────────

async def simulate() -> int:
    try:
        from scripts.probes._muzzle import muzzle_telegram   # belt: refuse at the wire if it is there
        muzzle_telegram([])
    except Exception:
        pass
    import httpx
    from apscheduler.triggers.cron import CronTrigger
    from core import job_audit
    from core.job_audit import audit_wrap
    from shared import dates as sd
    from shared import telegram_hold as th
    from agents.market_intelligence import job_recovery as jr
    import agents.market_intelligence.db as dbmod

    # an in-memory ledger standing in for mi_job_runs
    ledger: list[dict] = []
    starts: list[tuple] = []

    class _Conn:
        async def fetchrow(self, sql, *args):
            starts.append(args)
            ledger.append({"job_id": args[0], "started_at": datetime.now(ET), "status": "running",
                           "scheduled_for": args[2], "duration_s": None, "error_message": None})
            return {"id": len(ledger)}
        async def execute(self, sql, *args):
            if "UPDATE mi_job_runs" in sql:
                ledger[args[0] - 1].update(status=args[2], duration_s=args[1])

    class _Pool:
        def acquire(self):
            class _Ctx:
                async def __aenter__(s): return _Conn()
                async def __aexit__(s, *a): return False
            return _Ctx()

    dbmod.get_pool = lambda: asyncio.sleep(0, result=_Pool())
    saw: dict[str, object] = {}

    def data_job(name):
        async def f():
            saw[name] = (sd.et_today(), sd.last_trading_day())
            return 5
        f.__name__ = name
        return audit_wrap(f, name)

    async def sender():
        saw["friday_watchlist"] = (sd.et_today(), sd.last_trading_day())
        async with httpx.AsyncClient(timeout=5) as c:      # its OWN client, like _send_with_keyboard
            r = await c.post("https://api.telegram.org/bot0:x/sendMessage",
                             json={"chat_id": 1, "text": "📋 Friday watchlist — 12 names"})
            saw["send_status"] = r.status_code

    class J:
        def __init__(self, jid, func, h, m, dow="mon-fri", grace=1):
            self.id, self.func, self.misfire_grace_time = jid, func, grace
            self.trigger = CronTrigger(hour=h, minute=m, day_of_week=dow, timezone="America/New_York")
            self.next_run_time, self.args, self.kwargs = "scheduled", (), {}

    class S:
        def __init__(self, jobs): self._j = jobs
        def get_jobs(self): return list(self._j)

    jobs = [J("flag_continuation_scan", data_job("flag_continuation_scan"), 17, 25),
            J("evening_briefing", data_job("evening_briefing"), 18, 0),
            J("friday_watchlist", audit_wrap(sender, "friday_watchlist"), 18, 0, dow="fri", grace=3600),
            J("ran_fine", data_job("ran_fine"), 17, 0)]
    fri = datetime(2026, 9, 18, tzinfo=ET)
    # the stall: ran_fine has its row; the other three have NOTHING (09-18's exact reading)
    pre = {"ran_fine": [{"job_id": "ran_fine", "started_at": fri.replace(hour=17, minute=0, second=1),
                         "status": "success", "scheduled_for": None, "duration_s": 12.0, "error_message": None}]}
    jr.fetch_ledger = lambda ids, days=60: asyncio.sleep(0, result=pre)
    jr.record_terminal = lambda *a, **k: asyncio.sleep(0)
    pages, audits = [], []

    async def page(t, **k): pages.append(t)
    async def audit(ev, msg, *a): audits.append((ev, msg))

    now = datetime(2026, 9, 19, 0, 20, tzinfo=ET)
    print(f"now = {now:%a %Y-%m-%d %H:%M} ET (the 09-18 restart + 4 min); live et_today() = {sd.et_today()}")
    plan = await jr.run_recovery_sweep(S(jobs), {"morning_stop_refresh"}, reason="boot", now=now,
                                       dry_run=True, notify=page, audit=audit)
    print("\nDRY-RUN PLAN:")
    for d in plan["plan"]:
        print(f"  {d.label:42s} {d.kind:14s} {d.detail}")
    out = await jr.run_recovery_sweep(S(jobs), {"morning_stop_refresh"}, reason="boot", now=now,
                                      notify=page, audit=audit)
    print("\nRE-RUN:")
    ok = True
    for d in out["ran"]:
        seen = saw.get(d.job_id)
        row = next((r for r in ledger if r["job_id"] == d.job_id), None)
        good = d.result == "ok" and seen and seen[0] == fri.date() and row and row["scheduled_for"] == d.slot
        ok &= bool(good)
        print(f"  {'✓' if good else '✗'} {d.label:42s} result={d.result:8s} job saw et_today={seen[0] if seen else None} "
              f"last_trading_day={seen[1] if seen else None}  ledger row: status={row['status'] if row else None} "
              f"scheduled_for={row['scheduled_for'].strftime('%a %m-%d %H:%M') if row else None}")
        for _, _, method, text in d.held:
            print(f"      📵 withheld {method}: {text!r}")
    print(f"\nafter the sweep: et_today() = {sd.et_today()} (pin gone), in flight = {sorted(job_audit.jobs_in_flight())}")
    print(f"pages sent by the sweep: {len(pages)}; audit rows: {[e for e, _ in audits]}")
    print("\n" + pages[-1] if pages else "\n(no summary page)")
    held_ok = any(d.held for d in out["ran"]) and saw.get("send_status") == 200
    print(f"\nTelegram hold: {'✓ held at the wire, job carried on (200)' if held_ok else '✗ NOT HELD'}")
    print("\nVERDICT:", "PASS" if ok and held_ok and len(pages) == 1 else "FAIL")
    return 0 if ok and held_ok else 1


# ── dry-run in prod ───────────────────────────────────────────────────────────────────────

async def dry_run() -> int:
    from agents.market_intelligence import scheduler as sched
    from agents.market_intelligence import job_recovery as jr
    from agents.market_intelligence.constants import SERVICE_ROLE
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    # the process's own registrations, partitioned for THIS role, never started
    sched.AsyncIOScheduler = lambda *a, **k: AsyncIOScheduler(timezone="America/New_York")
    real_start = AsyncIOScheduler.start
    AsyncIOScheduler.start = lambda self, *a, **k: None
    try:
        s = sched.start_scheduler()
    finally:
        AsyncIOScheduler.start = real_start
    jobs = s.get_jobs()
    print(f"role={SERVICE_ROLE}: {len(jobs)} registered; sweep registered: {'missed_job_recovery' in {j.id for j in jobs}}")
    out = await jr.run_recovery_sweep(s, sched.EXECUTION_OWNED_JOB_IDS, reason="dry-run", dry_run=True,
                                      notify=lambda t, **k: asyncio.sleep(0), audit=lambda *a, **k: asyncio.sleep(0))
    from collections import Counter
    print(f"eligible: {out['eligible']}; excluded: {Counter(out['excluded'].values())}")
    print(f"slots: {len(out['plan'])}; by kind: {Counter(d.kind for d in out['plan'])}")
    for d in out["plan"]:
        if d.kind != "done":
            print(f"  {d.label:42s} {d.kind:14s} {d.detail}")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "simulate"
    sys.exit(asyncio.run(simulate() if mode == "simulate" else dry_run()))
