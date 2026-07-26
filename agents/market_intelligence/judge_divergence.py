"""P1 ensemble-divergence SHADOW (#301) — zero-authority 2nd-model divergence monitor
on the HIGH-tier holistic judge (ep_grade_judge.py, ADR 0011) verdict.

ZERO AUTHORITY (THE LINE): this module can NEVER change a grade, an alert, an entry, or
an exit — it only LOGS. `launch_divergence_check` is called by the caller (ep_detector.py
`_judge_shadow`) strictly AFTER the primary judge's verdict has already been persisted
(`update_ep_alert_judge_result` succeeded) and `r` already mutated with it — this module
only reads a snapshot of that settled verdict, never touches `r`/`score_tier`, and is
scheduled as a fire-and-forget `asyncio.Task` the caller never awaits. If the 2nd-model
call fails, times out, or errors, the primary judge verdict and everything downstream are
UNAFFECTED, because they have already fully settled by the time this module even starts.

Design (PLAN #301, build-spec'd 2026-07-11, unblocked 2026-07-26 — the pre-cutover
grade-path-stability freeze this inherited a `blocked_by` from never actually applied to a
monitor that cannot alter a grade): trigger post-judge-HIGH persist · call
`ep_grade_judge.grade_holistic` again with the IDENTICAL payload the primary judge saw,
model-swapped to JUDGE_DIVERGENCE_MODEL (Sonnet — deliberately a DIFFERENT model/tier than
JUDGE_MODEL=Opus, so the 2nd opinion is genuinely independent, not just a cheaper rerun of
the same model) · fail-open (a None 2nd verdict logs one COUNTED audit event and returns —
no telemetry row, since there is no verdict to compare) · log agree/disagree plus the 2nd
model's full verdict + rationale to the append-only `mi_judge_divergence` table · surfaced
as ONE line in the existing weekly system review (system_review.py) — consolidate, do not
proliferate a new digest.

Dedup / cost control: the EP scan re-runs every 5 min (7:00-10:00 ET, ~36 ticks/morning),
and `_judge_shadow` re-grades every still-alerted candidate on each tick. The CALLER gates
the trigger on `_audit_dedupe_check(ticker, alert_date, "judge_divergence_check")`
(ep_detector.py — the same in-memory once-per-ticker-per-day guard the sibling axis
shadows use, e.g. `theme_axis_shadow_adjusted`), so a HIGH-tier alert that stays HIGH
across the whole scan window fires the 2nd-model call ONCE, not ~36 times — this is what
keeps the module at the designed ~2-5 calls/day instead of ~2-5 x 36/day.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Own semaphore, DELIBERATELY separate from ep_detector._JUDGE_SEMAPHORE (the primary
# judge's latency-critical Anthropic concurrency budget under the 9:45 ORB cutoff) — this
# zero-authority background check must never compete with it for API capacity. Low cap:
# this is a ~2-5 calls/day shadow, not a hot path.
_DIVERGENCE_SEMAPHORE = asyncio.Semaphore(2)

# Module-level strong-reference set for in-flight background tasks. REQUIRED: per the
# asyncio docs, `asyncio.create_task()` does not itself keep the task alive — with no
# retained reference, the event loop is free to garbage-collect (silently dropping) a task
# mid-run. Each task removes itself via the done-callback once finished, so this never
# grows unbounded across a session.
_BACKGROUND_TASKS: "set[asyncio.Task]" = set()

_claude = None


def _get_claude():
    """Lazily-cached Anthropic client, scoped to this module (mirrors the
    `_get_claude()` pattern in ep_detector.py) — a fresh client per background call would
    be wasteful and could leak connections across the ~2-5 calls/day this module makes."""
    global _claude
    if _claude is None:
        import anthropic
        _claude = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _claude


def launch_divergence_check(ticker: str, alert_date, payload: dict, primary_verdict: dict) -> None:
    """Fire-and-forget entry point. Call ONLY after the primary judge's HIGH-tier verdict
    has already been persisted (DB-first, same discipline as the rest of `_judge_shadow`).
    Schedules the 2nd-model check as a background task and returns immediately WITHOUT
    awaiting it — zero added latency to the EP scan loop / the 9:45 ORB cutoff, and zero
    risk to the primary verdict, which has already fully settled by this point.

    `primary_verdict` is copied defensively — it is the caller's live verdict dict, and
    this task may still be running well after the caller's loop iteration moves on."""
    task = asyncio.create_task(_run(ticker, alert_date, payload, dict(primary_verdict)))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def _run(ticker: str, alert_date, payload: dict, primary_verdict: dict) -> None:
    """The 2nd-model call + divergence log. FAIL-OPEN and fully self-contained: every
    exception is caught here and never propagates anywhere — this runs fully detached from
    the caller (via `launch_divergence_check`, never awaited), so there is nothing to fail
    open TO except a COUNTED audit event (the #173 silent-failure-class guard)."""
    try:
        from agents.market_intelligence.db import get_pool, log_audit_event
        from agents.market_intelligence.audit_events import (
            JUDGE_DIVERGENCE_CHECK_FAILED, JUDGE_DIVERGENCE_DETECTED,
        )
        from agents.market_intelligence.ep_grade_judge import grade_holistic
        from shared.llm_models import (
            JUDGE_MODEL as _PRIMARY_MODEL, JUDGE_DIVERGENCE_MODEL as _MODEL,
        )

        # IDENTICAL payload, model-swapped only (PLAN #301 build-spec). Own semaphore +
        # timeout, distinct log_caller so this ~2-5 calls/day Sonnet spend is attributable
        # separately from the primary Opus judge's spend in the cost envelope (#377).
        verdict = await grade_holistic(
            _get_claude(), payload,
            semaphore=_DIVERGENCE_SEMAPHORE, timeout=25, model=_MODEL,
            log_caller="judge_divergence",
        )
        if verdict is None:
            await log_audit_event(
                JUDGE_DIVERGENCE_CHECK_FAILED,
                f"{ticker} {alert_date}: 2nd-model call failed/timed out (model={_MODEL})",
            )
            return

        agree = verdict.get("tier") == primary_verdict.get("tier")
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO mi_judge_divergence (
                    ticker, alert_date,
                    primary_model, primary_tier, primary_grade,
                    primary_direction, primary_confidence,
                    secondary_model, secondary_tier, secondary_grade,
                    secondary_direction, secondary_confidence, secondary_rationale,
                    agree
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
                ticker, alert_date,
                _PRIMARY_MODEL, primary_verdict.get("tier"), primary_verdict.get("grade"),
                primary_verdict.get("direction_vs_floor"), primary_verdict.get("confidence"),
                _MODEL, verdict.get("tier"), verdict.get("grade"),
                verdict.get("direction_vs_floor"), verdict.get("confidence"),
                verdict.get("rationale"), agree,
            )

        if not agree:
            # Informational only — NEVER read by any grade/entry/exit path (THE LINE).
            # Purely a Telegram-free audit-log breadcrumb; the weekly review is the
            # operator-facing surface (system_review.py._judge_divergence_section).
            await log_audit_event(
                JUDGE_DIVERGENCE_DETECTED,
                f"{ticker} {alert_date}: primary({_PRIMARY_MODEL})={primary_verdict.get('tier')} "
                f"vs secondary({_MODEL})={verdict.get('tier')}",
            )
    except Exception as e:  # SHADOW: never disturb anything — the caller isn't even listening
        logger.warning(f"judge divergence check failed for {ticker}: {e}")
        try:
            from agents.market_intelligence.db import log_audit_event
            from agents.market_intelligence.audit_events import JUDGE_DIVERGENCE_CHECK_FAILED
            await log_audit_event(
                JUDGE_DIVERGENCE_CHECK_FAILED,
                f"{ticker} {alert_date}: {type(e).__name__}: {e}",
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — log_audit_event never raises
            # by its own contract, but if it somehow did there is nothing above this to hand
            # the failure to (this whole function runs detached, fire-and-forget); already
            # logged via logger.warning above, so the failure isn't silent, just unescalated
            pass
