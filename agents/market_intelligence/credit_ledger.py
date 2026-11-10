"""Proactive LOW-CREDIT warning for the Anthropic API balance (2026-11-10).

WHY: on 2026-11-10 the balance ran out at 07:01 ET mid pre-market EP scan and 11 candidates were
silently graded "routine". `llm_health.py` (#273) only alerts AFTER exhaustion (reactive).

Anthropic has NO API that returns the credit balance (Console billing page only), so this is a
LEDGER: the operator records the Console balance with `/credits <usd>` (an audit row), and Apollo
subtracts its own logged Claude spend (`api_usage`, written by spend_tracker / core.spend) made after
that moment. A scheduled check (08:00 + 18:00 ET Mon-Fri) Telegrams ONE warning per ET day when the
estimate runs low. Telemetry: every check writes one audit row. Fail-open: never raises.

Read-only on api_usage; writes only audit rows; no trade state, no broker.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

EVENT_BALANCE_RECORDED = "anthropic_balance_recorded"   # /credits <usd> — detail {"usd", "as_of"}
EVENT_CREDIT_CHECK = "anthropic_credit_check"           # one telemetry row per scheduled run
EVENT_LOW_WARNED = "anthropic_credits_low_warned"       # the Telegram dedup token (one per ET day)

MIN_FLOOR_USD = 10.0        # warn below this regardless of burn
BURN_DAYS_MULTIPLE = 5.0    # ...or below this many days of burn
BURN_WINDOW_DAYS = 7        # complete ET days WITH spend averaged into the burn


# ── pure helpers ─────────────────────────────────────────────────────────────

def parse_credits_arg(task: str) -> tuple[str, float | str | None]:
    """`/credits` -> ("show", None); `/credits 42.50` -> ("set", 42.5);
    anything else -> ("error", plain message)."""
    parts = (task or "").strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return ("show", None)
    raw = parts[1].strip().lstrip("$").replace(",", "")
    msg = "That is not a number. Send the balance in dollars, e.g. /credits 42.50"
    try:
        val = float(raw)
    except ValueError:
        return ("error", msg)
    if math.isnan(val) or math.isinf(val):
        return ("error", msg)
    if val < 0:
        return ("error", "The balance cannot be negative. Send e.g. /credits 42.50")
    return ("set", val)


def compute_estimate(recorded_usd: float, spent_since_usd: float,
                     daily_spend: list[float]) -> dict:
    """est_usd = recorded - Claude spend since the recording.

    burn = mean Claude $/day over the supplied COMPLETE ET days that HAD spend (caller passes up to
    the last 7). Days with no spend are excluded on purpose: a quiet weekend (~$0.15) would otherwise
    drag the average down and make the runway look longer than a market week will actually burn.
    days_left = est / burn (None when burn is 0)."""
    est = float(recorded_usd) - float(spent_since_usd)
    days = [float(x) for x in daily_spend if x and float(x) > 0]
    burn = sum(days) / len(days) if days else 0.0
    days_left = (est / burn) if burn > 0 else None
    return {"recorded_usd": float(recorded_usd), "spent_since_usd": float(spent_since_usd),
            "est_usd": est, "burn_per_day": burn, "burn_days_used": len(days),
            "days_left": days_left}


def warning_reason(est: dict) -> str | None:
    """None | "used_up" (est <= 0) | "low" (est < max($10, 5 x burn))."""
    e = est["est_usd"]
    if e <= 0:
        return "used_up"
    if e < max(MIN_FLOOR_USD, BURN_DAYS_MULTIPLE * est["burn_per_day"]):
        return "low"
    return None


def format_estimate(est: dict, as_of: str | None = None) -> str:
    dl = est["days_left"]
    runway = f", roughly {dl:.1f} days at the current spend" if dl is not None else ""
    base = f"Estimated Anthropic balance: about ${est['est_usd']:.2f}{runway}."
    if as_of:
        base += (f" (${est['recorded_usd']:.2f} recorded {as_of}, "
                 f"minus ${est['spent_since_usd']:.2f} logged spend since.)")
    return base


def warning_text(reason: str, est: dict) -> str:
    if reason == "used_up":
        return ("Anthropic credits: the estimate says the balance is used up "
                f"(about ${est['est_usd']:.2f}). Top up in the Console, then send /credits <new balance>.")
    dl = est["days_left"]
    days = f"roughly {dl:.1f} days at the current spend" if dl is not None else "at the current spend"
    return (f"Anthropic credits low: about ${est['est_usd']:.2f} left, {days}. "
            "Top up in the Console, then send /credits <new balance>.")


# ── DB access ────────────────────────────────────────────────────────────────

def _detail_dict(detail) -> dict:
    if isinstance(detail, dict):
        return detail
    try:
        d = json.loads(detail or "{}")
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


async def get_recorded_balance() -> dict | None:
    """Latest `/credits` recording -> {"usd": float, "as_of": aware datetime}, or None."""
    from agents.market_intelligence.db import get_audit_log
    rows = await get_audit_log(event_type=EVENT_BALANCE_RECORDED, since_hours=24 * 365, limit=1)
    if not rows:
        return None
    d = _detail_dict(rows[0].get("detail"))
    try:
        as_of = datetime.fromisoformat(str(d["as_of"]))
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=_ET)
        return {"usd": float(d["usd"]), "as_of": as_of}
    except (KeyError, TypeError, ValueError):
        return None


async def fetch_spend_since(as_of: datetime) -> float:
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        v = await conn.fetchval(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM api_usage "
            "WHERE model ILIKE 'claude%' AND created_at > $1", as_of)
    return float(v or 0)


async def fetch_daily_spend(today) -> list[float]:
    """Claude $ per COMPLETE ET day (before `today`) that had spend; newest 7 of the last 30 days."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, SUM(cost_usd) AS s
            FROM api_usage
            WHERE model ILIKE 'claude%'
              AND (created_at AT TIME ZONE 'America/New_York')::date >= $1::date - 30
              AND (created_at AT TIME ZONE 'America/New_York')::date < $1::date
            GROUP BY 1 HAVING SUM(cost_usd) > 0
            ORDER BY 1 DESC LIMIT $2
            """, today, BURN_WINDOW_DAYS)
    return [float(r["s"]) for r in rows]


async def current_estimate(now: datetime | None = None) -> tuple[dict, dict] | None:
    """(estimate, recorded) or None when no balance was ever recorded. Raises on DB error."""
    now = now or datetime.now(_ET)
    rec = await get_recorded_balance()
    if rec is None:
        return None
    spent = await fetch_spend_since(rec["as_of"])
    daily = await fetch_daily_spend(now.astimezone(_ET).date())
    return compute_estimate(rec["usd"], spent, daily), rec


async def record_balance(usd: float, now: datetime | None = None) -> dict:
    from agents.market_intelligence.db import log_audit_event
    now = (now or datetime.now(_ET)).astimezone(_ET)
    detail = {"usd": float(usd), "as_of": now.isoformat()}
    await log_audit_event(EVENT_BALANCE_RECORDED,
                          f"Anthropic balance recorded: ${usd:.2f}", json.dumps(detail))
    return detail


async def _warned_today(now: datetime) -> bool:
    from agents.market_intelligence.db import get_audit_log
    rows = await get_audit_log(event_type=EVENT_LOW_WARNED, since_hours=48, limit=20)
    today = now.astimezone(_ET).date()
    return any(r["created_at"].astimezone(_ET).date() == today for r in rows)


async def run_credit_check(now: datetime | None = None, send=None) -> dict | None:
    """Scheduled check. Fail-open: never raises. Returns the result dict (None when nothing ledgered)."""
    now = now or datetime.now(_ET)
    try:
        got = await current_estimate(now)
        if got is None:
            return None  # no balance recorded: silent, by design
        est, rec = got
        reason = warning_reason(est)
        from agents.market_intelligence.db import log_audit_event
        warned = False
        if reason is not None and not await _warned_today(now):
            if send is None:
                from agents.market_intelligence.briefing import send_telegram_message as send
            # Audit row FIRST (the dedup token), then the Telegram — the llm_health order.
            await log_audit_event(EVENT_LOW_WARNED,
                                  f"Anthropic credits {reason}: est ${est['est_usd']:.2f}",
                                  json.dumps({**est, "reason": reason}))
            await send(warning_text(reason, est), parse_mode=None)
            warned = True
        result = {**est, "reason": reason, "warned": warned, "as_of": rec["as_of"].isoformat()}
        await log_audit_event(EVENT_CREDIT_CHECK,
                              f"Anthropic credit check: est ${est['est_usd']:.2f}"
                              f"{' - WARNED' if warned else ''}", json.dumps(result))
        return result
    except Exception as e:  # fail-open
        logger.warning("credit check failed: %s", e, exc_info=True)
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(EVENT_CREDIT_CHECK, "Anthropic credit check FAILED",
                                  json.dumps({"error": f"{type(e).__name__}: {e}"[:300]}))
        except Exception as e2:
            logger.warning("credit check failure-audit write also failed: %s", e2)
        return None
