"""Date utilities shared across orchestrator and agent containers.

Pulled out of `agents.market_intelligence.collector` so the orchestrator
can import `last_trading_day` for slash-command handlers without
depending on the market-intelligence package (which is not present in
the orchestrator container by design).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# CANONICAL ET zone for the whole codebase (imported as `from shared.dates import _ET`).
# MUST be ZoneInfo, never pytz: pytz timezones attached via `tzinfo=` (constructor /
# datetime.combine / .replace) silently apply the historical LMT offset (-04:56 for
# New York) instead of EDT/EST, which shifted the ORB window +56 min and recurred for
# weeks (#180/#183, 2026-06-05). ZoneInfo computes the correct offset for the wall-clock
# time in EVERY construction path, so `tzinfo=_ET` is always safe. pytz is banned in
# app code by scripts/preflight_datetime_hygiene.py (deploy gate).
_ET = ZoneInfo("America/New_York")


def et_hhmm(ts) -> str | None:
    """`HH:MM` in ET for a stored timestamp — datetime OR ISO string. None if unparseable.

    Lives HERE, beside `_ET`, because three separate surfaces in TWO containers were each
    slicing `ts[11:16]` straight out of a stored ISO string — which is **UTC**. FIGS's 09:35 ET
    profit-take and 09:51 ET stop rendered as 13:35 and 13:51 on the trade timeline the
    operator uses to reconstruct the ORB window (his words, 2026-08-08: *"we need to fix the
    timezone"*). Four hours off, in three places, none of which knew about the others.

    Every site that already HAS a datetime uses the house idiom `.astimezone(_ET)` directly and
    should keep doing so — this exists for the JSONB case, where the timestamp arrives as text
    and the parse is the part people get wrong.

    Naive input is treated as UTC: that is what the containers write. The zone is attached
    explicitly rather than via a bare `.astimezone()`, which the deploy gate bans.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        dt = ts
    else:
        s = str(ts).strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_ET).strftime("%H:%M")


# ── #672: a RECOVERY re-run pins the market date to the day the job was DUE ──────────────
# A job that never ran on Friday and is re-run on Saturday must record FRIDAY: 17 of the 21
# jobs missed on 2026-09-18 take no date parameter and read `et_today()`, so a bare re-run
# writes Saturday-dated rows — worse than the gap. The pin is a ContextVar, not a rebinding:
# `et_today` is RE-EXPORTED by ten modules, each holding its own reference to THIS function
# object, so changing what the function RETURNS reaches all ten, while rebinding
# `collector.et_today` reached one (the first recovery draft did exactly that). And it is
# task-LOCAL by construction — in the live process an intraday scan or the order path running
# beside a recovery must keep reading the real clock, which a global rebinding would break.
# `last_trading_day()` calls through here, so it follows the pin; `operator_today()` is the
# OPERATOR's clock and is deliberately untouched.
from contextlib import contextmanager
from contextvars import ContextVar
from typing import NamedTuple


class RecoveryPin(NamedTuple):
    """What a recovery re-run is standing in for: the job, the slot it was due, its market date."""
    job_id: str
    slot: datetime          # the scheduled fire time that never ran (tz-aware, ET)
    market_date: date       # what `et_today()` returns inside the pinned context


_RECOVERY_PIN: "ContextVar[RecoveryPin | None]" = ContextVar("apollo_recovery_pin", default=None)


def recovery_pin() -> "RecoveryPin | None":
    """The active recovery pin, or None on the ordinary (live-clock) path."""
    return _RECOVERY_PIN.get()


@contextmanager
def pinned_recovery(job_id: str, slot: datetime):
    """Run a job AS IF it were the `slot` it missed: `et_today()` returns the slot's ET date,
    `mi_job_runs` rows carry `scheduled_for = slot`, and every Telegram it sends is bannered
    LATE. Scoped to the current task and whatever it spawns; reset on exit even on error."""
    pin = RecoveryPin(job_id=job_id, slot=slot, market_date=slot.astimezone(_ET).date())
    token = _RECOVERY_PIN.set(pin)
    try:
        yield pin
    finally:
        _RECOVERY_PIN.reset(token)


def late_banner(now: "datetime | None" = None) -> str:
    """The line a Telegram sent from INSIDE a recovery re-run is prefixed with, or "" on the
    ordinary path. Data-driven by construction: any message any job sends while pinned gets it —
    there is no list of "jobs that send", which is the hand-list that made both earlier
    recoveries incomplete. Plain text on purpose (no markup), so it survives both senders'
    parse modes and the plain-text retry unchanged."""
    pin = _RECOVERY_PIN.get()
    if pin is None:
        return ""
    now = now or datetime.now(_ET)
    return (f"⏪ LATE RE-RUN — this is {pin.job_id} for {pin.slot.astimezone(_ET):%a %m-%d %H:%M} ET, "
            f"which never ran; sent {now.astimezone(_ET):%a %m-%d %H:%M} ET.\n")


def et_today() -> date:
    """Return today's date in US/Eastern timezone. MARKET/trading logic ONLY (trading day, ORB, hours).

    Inside `pinned_recovery(...)` (#672) it returns the pinned slot's date instead — see above."""
    pin = _RECOVERY_PIN.get()
    if pin is not None:
        return pin.market_date
    return datetime.now(_ET).date()


# CANONICAL operator timezone (Pacific). The operator PLANS + reads dates in PT; the harness date is UTC
# and the trading rule above is ET — three frames whose conflation recurred ~100x. Now mechanical:
# check_plan.py compares PLAN ETAs in PT, scripts/operator_now.py is the clock. Use operator_today() for
# OPERATOR-FACING dates (briefings, planning, "today"); et_today() is for MARKET logic only.
OPERATOR_TZ = ZoneInfo("America/Los_Angeles")


def operator_today() -> date:
    """Today's date in the OPERATOR's timezone (PT) — operator-facing / planning dates, NOT market logic."""
    return datetime.now(OPERATOR_TZ).date()


def last_trading_day(from_date: date | None = None) -> date:
    """Most recent trading day on or before from_date (default: today ET).

    Saturday/Sunday rolls back to Friday so weekend queries fall back to
    the last available data instead of returning empty results.
    Approximation: weekends only, not holidays.
    """
    d = from_date or et_today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
