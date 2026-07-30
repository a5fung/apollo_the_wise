"""Model auto-resolution runtime — refresh job + boot recorder (operator-ruled 2026-07-30).

The policy ("track the leaders; guardrails + traceability provide the safety")
is implemented in three moving parts; this module is the two runtime ones:

  1. `refresh_model_resolution` — nightly intelligence-side job (18:05 ET).
     Calls the API's `models.list`, computes the newest concrete id per tier
     (shared/model_resolver.py ordering), and atomically rewrites the
     resolution cache (`logs/model_resolution.json`, bind-mounted so the
     execution container and the host deploy gates see the same file). A tier
     change is NEVER silent: audit event `model_release_detected` + Telegram,
     BEFORE the change takes effect — the new id only binds at the next
     process boot, so the operator has a window to set the one-edit override
     in shared/llm_models.py if they don't want it.

  2. `record_boot_resolution` — boot hook (intelligence/combined role only, so
     the execution container never double-writes). Persists what every LLM
     ROLE is *effectively* running this process into `mi_model_resolution`
     (insert-on-change, effective-dated in ET) and Telegrams + audit-logs any
     change (`model_resolution_change`). This table answers "what was the
     judge running on 2026-08-14?" (db.get_model_resolution_asof) and joins by
     `effective_date` to the grade metrics — `judge_high_rate_daily` /
     `judge_demote_share_daily` read `ep_grade_decision` audit rows keyed by
     the same ET date, so a grade anomaly is attributable to a model change:

       SELECT g.et_date, c.model
       FROM (SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_date
             FROM mi_audit_log WHERE event_type = 'ep_grade_decision'
             GROUP BY 1) g
       LEFT JOIN mi_model_resolution c
         ON c.role = 'JUDGE_MODEL' AND c.effective_date <= g.et_date
       ...  -- (shape exercised on prod 2026-07-30)

Part 3 (the resolve itself) lives in shared/model_resolver.py and runs at
import of shared/llm_models.py — cache-file read only, fail-safe to the pins.

Guardrails in the refresh (fail-safe by construction):
  * unparseable ids are never candidates (can't order → can't adopt);
  * a tier is never DOWNGRADED by a refresh unless its cached id has actually
    disappeared from `models.list` (protects against a transiently truncated
    listing yanking a tier backwards);
  * a tier absent from the listing keeps its cached value (loud, not silent);
  * any API failure leaves the cache untouched (the job fails loud via
    audit_wrap; the trading system keeps running on the existing resolution).
"""
from __future__ import annotations

import logging
import os

from agents.market_intelligence.constants import runs_intelligence_jobs
from agents.market_intelligence.db import (
    get_latest_model_resolution,
    insert_model_resolution,
    log_audit_event,
)
from shared import llm_models
from shared.model_resolver import (
    TIERS,
    is_newer,
    newest_per_tier,
    read_cache,
    write_cache,
)

logger = logging.getLogger(__name__)

_JUDGE_EVAL_NOTE = (
    "ADR-0030: the judge robustness eval is DUE on the new id — deploys warn "
    "for 14 days, then the judge-eval gate blocks."
)


def current_role_bindings() -> dict[str, str]:
    """ROLE constant → concrete model id, from the registry (this process)."""
    return {
        name: value
        for name, value in vars(llm_models).items()
        if name.endswith("_MODEL") and isinstance(value, str)
    }


def _role_source(model_id: str) -> tuple[str, str]:
    """(source, note) for a bound id: how the registry arrived at it."""
    tier = llm_models.tier_of(model_id)
    if tier is None:
        return "static", "static legacy pin (not tier-resolved)"
    res = llm_models.TIER_RESOLUTIONS[tier]
    return res.source, res.note or f"tier={tier}"


async def _send_telegram(text: str) -> None:
    from agents.market_intelligence.briefing import send_telegram_message
    ok = await send_telegram_message(text, parse_mode="HTML")
    if not ok:
        logger.warning("model_resolution: Telegram notification failed to send")


# ── Boot recorder ────────────────────────────────────────────────────────────

async def record_boot_resolution() -> None:
    """Persist + announce what every LLM role is effectively running.

    Intelligence/combined role only — the execution container shares the DB and
    the registry, so a second writer would double-record and double-Telegram.
    Insert-on-change: a boot with no binding changes writes nothing. First-ever
    boot writes a baseline row per role (audit-logged, not Telegram'd — a
    baseline is not a change). Never raises — forensic path must not block boot.
    """
    from shared.telegram_format import code, esc

    if not runs_intelligence_jobs():
        return
    try:
        changes: list[tuple[str, str | None, str, str]] = []
        for role, model in sorted(current_role_bindings().items()):
            last = await get_latest_model_resolution(role)
            prev = last["model"] if last else None
            if prev == model:
                continue
            source, note = _role_source(model)
            await insert_model_resolution(role, model, source, prev, detail=note)
            changes.append((role, prev, model, source))
            event = "model_resolution_change" if prev else "model_resolution_baseline"
            await log_audit_event(
                event,
                f"{role}: {prev or '(none)'} -> {model} [{source}]",
                f"note={note}",
            )
        real = [c for c in changes if c[1] is not None]
        if real:
            lines = ["🤖 <b>LLM model change took effect this boot</b>"]
            for role, prev, model, source in real:
                lines.append(f"{code(esc(role))}: {code(esc(prev))} → "
                             f"{code(esc(model))} ({esc(source)})")
            lines.append("Watch <code>judge_high_rate_daily</code> / grade metrics "
                         "across this change (L2 audit).")
            if any(r == "JUDGE_MODEL" for r, *_ in real):
                lines.append(esc(_JUDGE_EVAL_NOTE))
            lines.append("Rollback (one edit): set the tier in "
                         "<code>_TIER_OVERRIDES</code> in shared/llm_models.py "
                         "and redeploy.")
            await _send_telegram("\n".join(lines))
        elif changes:
            logger.info("model_resolution: baseline recorded for %d role(s)", len(changes))
    except Exception as e:
        # forensic-only path: never block boot, but never be silent either
        logger.error(f"model_resolution boot recorder failed (non-fatal): {e}")


# ── Nightly refresh ──────────────────────────────────────────────────────────

async def _list_model_ids() -> list[str]:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    try:
        return [m.id async for m in client.models.list()]
    finally:
        await client.close()


async def refresh_model_resolution() -> int:
    """Refresh the resolution cache from `models.list`. Returns tiers written.

    Raises on API failure (audit_wrap records the failed run; the cache — and
    therefore the trading system's bindings — are left untouched)."""
    from shared.telegram_format import code, esc

    ids = await _list_model_ids()
    if not ids:
        raise RuntimeError("models.list returned no models — refusing to touch the cache")

    computed = newest_per_tier(ids)
    prev = read_cache()
    prev_resolved: dict[str, str] = dict((prev or {}).get("resolved", {}))
    prev_changed: dict[str, str] = dict((prev or {}).get("changed_at", {}))

    resolved: dict[str, str] = {}
    changes: list[tuple[str, str | None, str]] = []  # (tier, old, new)
    for tier in TIERS:
        new_id = computed.get(tier)
        old_id = prev_resolved.get(tier)
        if new_id is None:
            # tier vanished from the listing — keep what we had, loudly
            if old_id:
                resolved[tier] = old_id
                await log_audit_event(
                    "model_resolution_refresh_anomaly",
                    f"{tier}: no parseable candidate in models.list — keeping {old_id}",
                    f"listing={','.join(ids)}",
                )
            continue
        if old_id and new_id != old_id and not is_newer(new_id, old_id):
            if old_id in ids:
                # would be a downgrade while the old id is still served —
                # a truncated/odd listing; refuse it, loudly.
                await log_audit_event(
                    "model_resolution_refresh_anomaly",
                    f"{tier}: computed {new_id} is not newer than cached {old_id} "
                    f"(still served) — keeping {old_id}",
                    f"listing={','.join(ids)}",
                )
                resolved[tier] = old_id
                continue
            # the cached id disappeared from the API — accept the move, loudly.
            await log_audit_event(
                "model_resolution_refresh_anomaly",
                f"{tier}: cached {old_id} no longer served — moving to {new_id}",
                f"listing={','.join(ids)}",
            )
        resolved[tier] = new_id
        if new_id != old_id:
            changes.append((tier, old_id, new_id))

    changed_at = dict(prev_changed)
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    for tier, _old, _new in changes:
        changed_at[tier] = now_iso

    candidates = {t: [i for i in ids if llm_models.tier_of(i) == t or t in i] for t in TIERS}
    path = write_cache(resolved, changed_at, candidates=candidates)
    logger.info("model_resolution: cache refreshed at %s — %s", path, resolved)

    real = [c for c in changes if c[1] is not None]
    for tier, old, new in changes:
        await log_audit_event(
            "model_release_detected",
            f"{tier}: {old or '(first record)'} -> {new}",
            f"takes effect at next boot; cache={path}",
        )
    if real:
        bindings = current_role_bindings()
        lines = ["🆕 <b>New Claude release detected</b> (models.list)"]
        for tier, old, new in real:
            lines.append(f"{esc(tier)}: {code(esc(old))} → {code(esc(new))}")
        lines.append("Takes effect at the <b>next deploy/restart</b> of each "
                     "service — nothing changed mid-session.")
        judge_tier = llm_models.tier_of(bindings.get("JUDGE_MODEL", ""))
        if any(t == judge_tier for t, _o, _n in real):
            lines.append(f"⚠ The JUDGE (currently "
                         f"{code(esc(bindings.get('JUDGE_MODEL', '?')))}) will move "
                         f"at next boot. {esc(_JUDGE_EVAL_NOTE)}")
        lines.append("Don't want it? One edit BEFORE the next deploy: pin the "
                     "tier in <code>_TIER_OVERRIDES</code> "
                     "(shared/llm_models.py).")
        await _send_telegram("\n".join(lines))
    return len(resolved)
