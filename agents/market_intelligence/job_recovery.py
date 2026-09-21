"""#672 — a job that should have run and did not is RE-RUN, with the date pinned to the day it was due.

THE INCIDENT THIS ENDS. On 2026-09-18 `nightly_data_pull` deadlocked at 17:00 ET and held every
pool connection until a deploy restarted the container at 00:16. Every intelligence job due in the
17:13–18:10 chain was dispatched on time, blocked on the pool before `audit_wrap` could write its
start row, died with the process, and — this is the part that decides the design — WAS FORGOTTEN AT
BOOT. APScheduler's in-memory jobstore knows nothing of a slot that is already past when it starts:
it sets `next_run_time` to tomorrow and emits NO `EVENT_JOB_MISSED` (measured, not inferred: a job
whose cron slot was two hours earlier, grace 3600, started with `events at boot: []`). So the
listener that shipped first under this task could never have seen 09-18's shape. The only witness
that survives a restart is the LEDGER, `mi_job_runs`, and that is what this module reads.

TWO EARLIER RECOVERIES WERE HAND-DRIVEN AND BOTH WERE INCOMPLETE, because the missed set was
hand-listed. Nothing here is listed. The population is DERIVED from the scheduler itself and from
classifications that already exist and are already gated:

  ELIGIBLE  = a registered job (this process's `get_jobs()`, post-partition)
              whose trigger fires AT MOST ONCE A DAY (single fixed hour and minute — a 5-minute
              scan has no "slot" worth re-running; its next run supersedes)
              that is NOT execution-owned (`EXECUTION_OWNED_JOB_IDS` — THE LINE: a job that reads
              the broker or touches trade state is never re-run by a machine)
              and that WRITES THE LEDGER (audit-wrapped — otherwise "did it run" is undecidable).
  SLOTS     = the trigger's OWN past fire times over a 4-day lookback (its arithmetic, its
              weekday mask, its timezone — nothing re-implemented here).
  GAP       = a slot with NO ledger row near it (any real attempt counts: success, failed,
              empty_result, interrupted, running are NOT gaps — they ran, and their own failure
              surfaces already paged) and no terminal disposition from an earlier pass.
  RE-RUN    = only while NO MARKET SESSION HAS OPENED since the slot. Friday's chain is
              recoverable until Monday 09:30 ET; after that the world the job would describe has
              moved on (positions, equity, "today's" leaders), so the slot is recorded
              `unrecoverable` and NAMED for the operator instead of silently written with the
              wrong state. One rule, stated once, applied to every job alike.

THE DATE PIN. 17 of the 21 jobs missed on 09-18 read `et_today()`; re-run on Saturday they record
Saturday. Each re-run executes inside `shared.dates.pinned_recovery(job_id, slot)` — a ContextVar
that makes `et_today()` return the slot's date for THIS task and its children only (a global
rebinding would pin the intraday scans and the order path running beside it). Before every re-run
`assert_every_binding_pinned` walks `sys.modules` and calls EVERY `et_today` binding the production
graph holds — the check the 09-19 probe proved necessary (ten modules hold their own binding) —
and REFUSES the run if one still answers the wall clock. A half-applied pin writes rows that look
right until someone checks their date; refusing is the point.

TELEGRAMS. A re-run's sends are HELD, not delivered, by `shared.telegram_hold` at the httpx layer
(seven modules post to the Bot API directly — no list). The summary names every withheld message.
Sending late is the operator's flip (`APOLLO_RECOVERY_SEND_LATE=1`), off by default, after Friday's
watchlist reached him twice on 09-20 from a probe that said it could not.

WHAT IS EXERCISED vs ASSUMED: the derivation is replayed against prod's real 09-16..09-20 ledger in
`tests/test_672_missed_job_recovery.py` and must reproduce the incident's gap set; the re-run path
is driven through the real `audit_wrap` with the real listener and a real-scheduler job list; the
probe `scripts/probes/_672_exercise_recovery.py` runs the same scenario end to end and prints it.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable

from shared.dates import _ET, pinned_recovery

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 4                 # covers a long weekend plus the Friday chain
YOUNG_S = 120                     # a slot is judged from grace + this; a job blocked in _record_start is
                                  # already in flight (core.job_audit._IN_FLIGHT), so this only covers dispatch lag
MATCH_AFTER_S = 30 * 60           # an ordinary run's started_at may trail its slot by grace + this
MAX_ATTEMPTS = 3                  # per slot, derived from ledger rows, so it survives a restart
BOUND_MIN_S = 10 * 60             # a re-run is bounded at max(BOUND_MIN, 3 × p95 duration) ≤ BOUND_MAX
BOUND_MAX_S = 3 * 3600
BOUND_DEFAULT_S = 30 * 60         # no history to size it from
ORB_QUIET = (time(9, 25), time(10, 5))   # no re-runs while the pool feeds the ORB entry window
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
# A slot INSIDE the session is a MOMENT, not a day: the 09:31 open scan, the 10:00 digests, the
# 15:55 pre-close check describe the market as it was right then, and one of them (ep_scan_open)
# feeds the entry path. Re-running any of them later in the same session reads a different market
# under the same label. Pre-open and after-close slots are the recoverable classes.
MATCH_BEFORE_S = 120              # an ordinary run's started_at may precede its slot by clock skew
ATTEMPTED = frozenset({"running", "success", "failed", "empty_result", "interrupted"})
TERMINAL = frozenset({"unrecoverable"})
# 'missed' (written by the EVENT_JOB_MISSED listener) is neither: a recorded gap, still open.


# ── population ────────────────────────────────────────────────────────────────────────────

def fires_at_most_daily(trigger) -> bool:
    """A CronTrigger with ONE fixed hour and ONE fixed minute (no ranges, lists, steps or `*`).
    Everything else — hourly, every-5-minutes, the ORB-window ticker — has no re-runnable slot."""
    fields = getattr(trigger, "fields", None)
    if not fields:
        return False
    by_name = {f.name: f for f in fields}
    for name in ("hour", "minute"):
        f = by_name.get(name)
        if f is None or f.is_default or len(f.expressions) != 1:
            return False
        e = f.expressions[0]
        first, last, step = getattr(e, "first", None), getattr(e, "last", None), getattr(e, "step", None)
        if first is None or first != last or step not in (None, 1):
            return False
    sec = by_name.get("second")
    if sec is not None and not sec.is_default:
        return False
    return True


def writes_ledger(func: Callable) -> bool:
    """Does this callable record itself in `mi_job_runs`? Runtime introspection of the closure
    `audit_wrap` builds (it references `audit_run` by name), or of a job that opens `audit_run`
    itself — never source text."""
    seen: set[int] = set()
    stack = [func]
    while stack:
        f = stack.pop()
        if id(f) in seen:
            continue
        seen.add(id(f))
        code = getattr(f, "__code__", None)
        if code is not None and "audit_run" in code.co_names:
            return True
        for cell in (getattr(f, "__closure__", None) or ()):
            try:
                v = cell.cell_contents
            except ValueError:
                continue
            if callable(v):
                stack.append(v)
    return False


def eligible_jobs(scheduler, execution_owned: Iterable[str]) -> tuple[list, dict[str, str]]:
    """(eligible jobs, {job_id: why excluded}) — derived from what the scheduler holds NOW."""
    owned = frozenset(execution_owned)
    eligible, excluded = [], {}
    for job in scheduler.get_jobs():
        if job.id in owned:
            excluded[job.id] = "execution-owned (THE LINE: never machine re-run)"
        elif getattr(job, "next_run_time", "unset") is None:
            # A PAUSED job (registered with `next_run_time=None` — chart_axis_shadow since
            # 2026-08-02, "do NOT resurrect a 2-a-day cron"). Its trigger still yields slots; its
            # ledger is silent by design. Re-running it would resurrect what the operator stopped.
            excluded[job.id] = "paused (next_run_time=None) — a slot that is not meant to run is not a gap"
        elif not fires_at_most_daily(job.trigger):
            excluded[job.id] = "fires more than once a day — the next run supersedes"
        elif not writes_ledger(job.func):
            excluded[job.id] = "not audit-wrapped — a run leaves no ledger row, so a miss is undecidable"
        else:
            eligible.append(job)
    return eligible, excluded


def past_slots(trigger, now: datetime, lookback_days: int | None = None) -> list[datetime]:
    """The trigger's own fire times in (now − lookback, now]. Its arithmetic, not ours."""
    out: list[datetime] = []
    cursor = now - timedelta(days=LOOKBACK_DAYS if lookback_days is None else lookback_days)
    while True:
        n = trigger.get_next_fire_time(None, cursor)
        if n is None or n > now:
            break
        out.append(n)
        cursor = n + timedelta(seconds=1)
    return out


# ── the freshness rule ────────────────────────────────────────────────────────────────────

def _session_opens_on(d: date) -> bool:
    """Weekends never; weekdays per the NYSE calendar; if the calendar cannot answer, YES — an
    extra counted session skips a re-run, which is the safe direction."""
    if d.weekday() >= 5:
        return False
    try:
        from agents.market_intelligence.trading_calendar import get_market_status
        return bool(get_market_status(d).is_trading_day)
    except Exception as e:                           # loud-ok: fail-SAFE — counting a session skips a re-run
        logger.warning(f"recovery: calendar lookup failed for {d}, counting it as a session: {e}")
        return True


def sessions_opened_between(a: datetime, b: datetime) -> int:
    """How many market sessions opened (09:30 ET) strictly after `a` and at or before `b`."""
    a_et, b_et = a.astimezone(_ET), b.astimezone(_ET)
    n, d = 0, a_et.date()
    while d <= b_et.date():
        open_at = datetime.combine(d, SESSION_OPEN, tzinfo=_ET)
        if a_et < open_at <= b_et and _session_opens_on(d):
            n += 1
        d += timedelta(days=1)
    return n


def in_orb_quiet_window(now: datetime) -> bool:
    et = now.astimezone(_ET)
    return et.weekday() < 5 and ORB_QUIET[0] <= et.time() < ORB_QUIET[1]


def would_cross_orb_window(now: datetime, bound_s: int) -> bool:
    """A re-run that could still be holding connections at 09:25 ET on a weekday — e.g. a Monday
    09:20 pass starting a 50-minute job — is deferred. Per re-run, not per pass: a pass that began
    clear of the window can walk into it."""
    et = now.astimezone(_ET)
    if et.weekday() >= 5:
        return False
    start = datetime.combine(et.date(), ORB_QUIET[0], tzinfo=_ET)
    return et < start <= et + timedelta(seconds=bound_s)


def slot_is_in_session(slot: datetime) -> bool:
    et = slot.astimezone(_ET)
    return SESSION_OPEN <= et.time() < SESSION_CLOSE and _session_opens_on(et.date())


# ── classification (pure) ─────────────────────────────────────────────────────────────────

@dataclass
class Disposition:
    job_id: str
    slot: datetime
    kind: str                      # done | gap | young | unrecoverable | exhausted | in_flight | too_close
    attempts: int = 0
    detail: str = ""
    result: str = ""               # filled by the executor: ok | failed | timeout | refused | held-only
    held: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.job_id}@{self.slot.astimezone(_ET):%a %m-%d %H:%M}"


def _same_instant(a, b, tol_s: float = 1.0) -> bool:
    return a is not None and b is not None and abs((a - b).total_seconds()) <= tol_s


def classify_slot(job_id: str, slot: datetime, grace_s: int, rows: list[dict], now: datetime,
                  in_flight: Iterable[str] = (), next_fire: datetime | None = None,
                  bound_s: int = BOUND_DEFAULT_S, slot_end: datetime | None = None) -> Disposition:
    """One slot against its job's ledger rows. Pure — the dry-run and the fixture replay call it.

    `slot_end` is the trigger's NEXT fire after this slot. An ordinary row anywhere in
    [slot − 2 min, min(now, slot_end − 2 min)] satisfies the slot — derived from the trigger, not a
    constant, because a job dispatched on time but BLOCKED in `_record_start` lands its row with
    `started_at = NOW()` whenever the pool frees (the 45-minute pull cap produces exactly this: 27
    blocked INSERTs landing at 17:46 for 17:15 slots). A 30-minute window read those as gaps and the
    next pass re-ran them — the one thing a recovery must never do. `st <= now` stays explicit so a
    replay with a pinned `now` never accepts a row from its own future."""
    if (now - slot).total_seconds() < (grace_s or 0) + YOUNG_S:
        return Disposition(job_id, slot, "young", detail="slot too recent to judge")
    lo = slot - timedelta(seconds=MATCH_BEFORE_S)
    if slot_end is not None and slot_end > slot:
        hi = min(now, slot_end - timedelta(seconds=MATCH_BEFORE_S))
    else:
        hi = min(now, slot + timedelta(seconds=(grace_s or 0) + MATCH_AFTER_S))
    attempts = 0
    for r in rows:
        st, sched, status = r.get("started_at"), r.get("scheduled_for"), r.get("status")
        if sched is not None and _same_instant(sched, slot):
            if status in TERMINAL:
                return Disposition(job_id, slot, "unrecoverable", detail=r.get("error_message") or "")
            if status == "success":
                return Disposition(job_id, slot, "done", attempts=attempts + 1, detail="recovered earlier")
            if status in ATTEMPTED:
                attempts += 1
            continue                                   # a 'missed' row for this slot: still a gap
        if sched is None and st is not None and lo <= st <= hi and status in ATTEMPTED:
            return Disposition(job_id, slot, "done", detail=f"ran at {st.astimezone(_ET):%H:%M} ({status})")
    if attempts >= MAX_ATTEMPTS:
        return Disposition(job_id, slot, "exhausted", attempts=attempts,
                           detail=f"{attempts} recovery attempts, none succeeded")
    if slot_is_in_session(slot):
        return Disposition(job_id, slot, "unrecoverable", attempts=attempts,
                           detail="slot is inside market hours — a moment, not a day; never re-run")
    n = sessions_opened_between(slot, now)
    if n:
        return Disposition(job_id, slot, "unrecoverable", attempts=attempts,
                           detail=f"{n} market session(s) opened since — the state it would record has moved on")
    if job_id in set(in_flight):
        return Disposition(job_id, slot, "in_flight", attempts=attempts, detail="job is running or blocked right now")
    if next_fire is not None and (next_fire - now).total_seconds() < bound_s:
        return Disposition(job_id, slot, "too_close", attempts=attempts,
                           detail=f"its next real run is at {next_fire.astimezone(_ET):%H:%M}; deferred")
    return Disposition(job_id, slot, "gap", attempts=attempts)


def bound_for(rows: list[dict]) -> int:
    """max(10 min, 3 × p95 of successful durations) capped at 3 h; 30 min with no history."""
    durs = sorted(float(r["duration_s"]) for r in rows
                  if r.get("status") == "success" and r.get("duration_s") is not None)
    if not durs:
        return BOUND_DEFAULT_S
    p95 = durs[min(len(durs) - 1, int(round(0.95 * (len(durs) - 1))))]
    return int(min(BOUND_MAX_S, max(BOUND_MIN_S, 3 * p95)))


def plan_recovery(jobs: list, rows_by_job: dict[str, list[dict]], now: datetime,
                  in_flight: Iterable[str] = ()) -> list[Disposition]:
    """Every eligible job × every past slot → a disposition. Pure; slot order."""
    out: list[Disposition] = []
    for job in jobs:
        rows = rows_by_job.get(job.id, [])
        grace = getattr(job, "misfire_grace_time", None) or 0
        try:
            next_fire = job.trigger.get_next_fire_time(None, now)
        except Exception as e:                       # loud-ok: only the too-close guard loses precision
            logger.warning(f"recovery: {job.id} next fire time unavailable ({e}); too-close guard off for it")
            next_fire = None
        bound = bound_for(rows)                  # per JOB, not per slot — `rows` never changes here
        for slot in past_slots(job.trigger, now):
            try:
                slot_end = job.trigger.get_next_fire_time(None, slot + timedelta(seconds=1))
            except Exception:                        # loud-ok: falls back to the grace window below
                slot_end = None
            out.append(classify_slot(job.id, slot, grace, rows, now, in_flight, next_fire, bound,
                                     slot_end=slot_end))
    out.sort(key=lambda d: d.slot)
    return out


# ── the runtime refusal guard (the 09-19 probe's walk, kept) ─────────────────────────────

PRODUCTION_PREFIXES = ("shared", "agents", "core", "channels")


def assert_every_binding_pinned(expected: date) -> dict[str, Any]:
    """Call EVERY `et_today` binding the production graph holds; return the ones that do not answer
    `expected`. Empty dict = safe to run. Ten modules hold their own binding (measured 09-19); the
    ContextVar reaches them all because they share one function object — this proves it each time
    rather than trusting it, and catches a module that grew its own copy."""
    bad: dict[str, Any] = {}
    for name, mod in list(sys.modules.items()):
        if mod is None or not name.startswith(PRODUCTION_PREFIXES):
            continue
        f = getattr(mod, "et_today", None)
        if not callable(f):
            continue
        try:
            v = f()
        except Exception as e:                       # loud-ok: reported as a bad binding below
            v = f"ERR {type(e).__name__}: {e}"
        if v != expected:
            bad[name] = v
    return bad


# ── ledger I/O ────────────────────────────────────────────────────────────────────────────

async def fetch_ledger(job_ids: list[str], days: int = 60) -> dict[str, list[dict]]:
    """This job's ledger rows, grouped by job_id, oldest first.

    #678 (2026-09-20): the SQL lives in `db.get_job_runs_for` — one SELECT against `mi_job_runs`
    for the whole codebase, so a column added there is found once. This is the grouping half.
    The 60-day default is NOT the classification window (that is LOOKBACK_DAYS=4); `bound_for`
    needs the longer history to compute a meaningful p95 duration for the re-run timeout."""
    from agents.market_intelligence.db import get_job_runs_for
    out: dict[str, list[dict]] = {}
    for r in await get_job_runs_for(job_ids, since_hours=days * 24):
        out.setdefault(r["job_id"], []).append(r)
    return out


async def record_terminal(job_id: str, slot: datetime, status: str, reason: str) -> None:
    """A slot the sweep will not examine again: 'unrecoverable' (sessions elapsed, attempts
    exhausted, pin refused) — written with scheduled_for so it is never counted as a gap again."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO mi_job_runs (job_id, started_at, finished_at, status, error_message, scheduled_for)
               VALUES ($1, $2, NOW(), $3, $4, $2)""",
            job_id, slot, status, reason[:500])


# ── execution ─────────────────────────────────────────────────────────────────────────────

async def rerun_one(job, disp: Disposition, bound_s: int) -> Disposition:
    """Execute ONE gap: the REGISTERED callable, through the real audit_wrap, pinned to its slot,
    bounded, with its Telegrams held. Mutates and returns `disp`."""
    from shared.telegram_hold import drain_held, install_recovery_hold
    install_recovery_hold()
    with pinned_recovery(job.id, disp.slot) as pin:
        bad = assert_every_binding_pinned(pin.market_date)
        if bad:
            disp.result = "refused"
            disp.detail = f"pin did not reach {len(bad)} et_today binding(s): {sorted(bad)[:5]}"
            logger.error(f"recovery REFUSED for {disp.label}: {disp.detail}")
            return disp
        try:
            await asyncio.wait_for(job.func(*getattr(job, "args", ()) or (), **(getattr(job, "kwargs", None) or {})),
                                   timeout=bound_s)
            disp.result = "ok"
        except asyncio.TimeoutError:
            disp.result = "timeout"
            disp.detail = f"cut off at {bound_s // 60} min"
        except Exception as e:                       # loud-ok: audit_wrap already recorded + paged it
            disp.result = "failed"
            disp.detail = f"{type(e).__name__}: {str(e)[:160]}"
        finally:
            disp.held = drain_held(job.id)
    return disp


DRY_RUN_ENV = "APOLLO_RECOVERY_DRY_RUN"     # operator: plan + heartbeat + page, execute NOTHING
_SWEEP_LOCK: "asyncio.Lock | None" = None   # one sweep at a time — boot, periodic and the miss-kick overlap


def _lock() -> asyncio.Lock:
    global _SWEEP_LOCK
    if _SWEEP_LOCK is None:
        _SWEEP_LOCK = asyncio.Lock()
    return _SWEEP_LOCK


def dry_run_enabled() -> bool:
    from shared.env_flags import env_flag_on
    return env_flag_on(DRY_RUN_ENV)


async def run_recovery_sweep(scheduler, execution_owned: Iterable[str], *, reason: str,
                             now: datetime | None = None, dry_run: bool = False,
                             notify: Callable | None = None, audit: Callable | None = None) -> dict:
    """Derive → classify → re-run gaps in slot order → ONE summary. Returns what it did.

    SERIALISED under one lock: the boot pass, the :20/:50 pass and the miss-kick can overlap, and
    two plans computed from the same ledger would both call the same slot a gap. The in-flight set
    is re-checked immediately before EACH re-run (not only at plan time), which also covers
    APScheduler dispatching a job's real slot while a pass is walking its list.

    `notify`/`audit` default to the live senders; tests and the probe pass captures. `now` pins the
    clock for replays; live passes read it fresh before each re-run so a long pass cannot walk into
    the ORB window unnoticed."""
    async with _lock():
        return await _run_recovery_sweep_locked(scheduler, execution_owned, reason=reason, now=now,
                                                dry_run=dry_run, notify=notify, audit=audit)


async def _run_recovery_sweep_locked(scheduler, execution_owned, *, reason, now, dry_run, notify, audit) -> dict:
    pinned_now = now
    clock = (lambda: pinned_now) if pinned_now is not None else (lambda: datetime.now(_ET))
    now = clock()
    dry_run = dry_run or dry_run_enabled()
    if audit is None:
        from agents.market_intelligence.db import log_audit_event as audit
    if notify is None:
        from core.notifications import notify_owner as notify
    from core.job_audit import jobs_in_flight

    jobs, excluded = eligible_jobs(scheduler, execution_owned)
    out: dict[str, Any] = {"reason": reason, "now": now.isoformat(), "eligible": len(jobs),
                           "excluded": excluded, "plan": [], "ran": [], "quiet": False, "dry_run": dry_run}
    if in_orb_quiet_window(now):
        out["quiet"] = True
        logger.info("recovery sweep: inside the ORB quiet window — deferred")
        return out
    rows_by_job = await fetch_ledger([j.id for j in jobs])
    plan = plan_recovery(jobs, rows_by_job, now, jobs_in_flight())
    out["plan"] = plan
    gaps = [d for d in plan if d.kind == "gap"]
    stale = [d for d in plan if d.kind in ("unrecoverable", "exhausted")]
    # only the ones NOT already carrying a terminal row need writing — `to_terminate` below is the
    # ONLY dedup. (A `not d.detail.startswith("recorded")` clause used to sit on the line above; no
    # producer writes such a detail and none of the 33 live terminal rows matched it. Verified both
    # ways 2026-09-20 before removing it — it read as dedup and did nothing.)
    to_terminate = [d for d in stale if not any(
        r.get("status") in TERMINAL and _same_instant(r.get("scheduled_for"), d.slot)
        for r in rows_by_job.get(d.job_id, []))]
    if reason == "boot":
        mode = "DRY-RUN (APOLLO_RECOVERY_DRY_RUN) — nothing executed" if dry_run else "live"
        await _safe(audit, "job_recovery_sweep",
                    f"boot [{mode}]: {len(jobs)} eligible job(s), {len(plan)} slot(s) examined, "
                    f"{len(gaps)} gap(s), {len(to_terminate)} unrecoverable"
                    + (f"; would re-run: {', '.join(d.label for d in gaps)}" if gaps else ""))
        if dry_run and (gaps or to_terminate):
            await _safe(notify, "⏪ *Missed-job recovery — DRY RUN, nothing executed*\n"
                        f"Would re-run {len(gaps)}: " + ", ".join(d.label for d in gaps)
                        + (f"\nUnrecoverable {len(to_terminate)}: " + ", ".join(d.label for d in to_terminate)
                           if to_terminate else "")
                        + "\nUnset APOLLO_RECOVERY_DRY_RUN to enable.", silent=False)
    if dry_run:
        return out
    by_id = {j.id: j for j in jobs}
    for d in gaps:
        job = by_id[d.job_id]
        bound = bound_for(rows_by_job.get(d.job_id, []))
        tick = clock()
        if d.job_id in jobs_in_flight():             # re-checked NOW, not at plan time
            d.kind, d.detail = "in_flight", "started (or blocked) since this pass was planned; skipped"
            continue
        if in_orb_quiet_window(tick) or would_cross_orb_window(tick, bound):
            d.kind, d.detail = "deferred", f"a {bound // 60}-min re-run would overlap the 09:25–10:05 ORB window; next pass"
            continue
        await rerun_one(job, d, bound)
        out["ran"].append(d)
        if d.result == "refused":
            await _safe(record_terminal, d.job_id, d.slot, "unrecoverable", f"pin refused: {d.detail}")
    for d in to_terminate:
        await _safe(record_terminal, d.job_id, d.slot, "unrecoverable", d.detail)
    if out["ran"] or to_terminate:
        text = summary_text(out["ran"], to_terminate, clock())
        await _safe(audit, "jobs_recovered", " ".join(text.split())[:300])
        # a clean recovery whispers; anything that failed, or cannot be recovered, buzzes
        loud = bool(to_terminate) or any(d.result != "ok" for d in out["ran"])
        await _safe(notify, text, silent=not loud)
    return out


async def _safe(fn, *a, **kw):
    try:
        return await fn(*a, **kw)
    except Exception as e:                           # loud-ok: the sweep must finish its list
        logger.error(f"recovery sweep: {getattr(fn, '__name__', fn)} failed (non-fatal): {e}")


def summary_text(ran: list[Disposition], stale: list[Disposition], now: datetime) -> str:
    """ONE message. What ran and how it ended, what was withheld, what cannot be recovered."""
    ok = [d for d in ran if d.result == "ok"]
    bad = [d for d in ran if d.result != "ok"]
    lines = [f"⏪ *Missed-job recovery* — {len(ok)} re-run OK, {len(bad)} not, {len(stale)} unrecoverable"]
    if ok:
        lines.append("Re-run with the date pinned to the day they were due: " + ", ".join(d.label for d in ok))
    for d in bad:
        lines.append(f"✗ {d.label}: {d.result} — {d.detail}")
    held = [(d, h) for d in ran for h in d.held]
    if held:
        lines.append(f"📵 {len(held)} Telegram(s) WITHHELD (a late send is your flip, APOLLO_RECOVERY_SEND_LATE=1):")
        for d, (_, _, method, text) in held[:12]:
            first = " ".join(text.split())[:90]
            lines.append(f"  • {d.job_id} {method}: {first}")
        if len(held) > 12:
            lines.append(f"  … and {len(held) - 12} more")
    for d in stale:
        lines.append(f"⛔ {d.label}: {d.detail} — re-run by hand if the data gap matters")
    return "\n".join(lines)
