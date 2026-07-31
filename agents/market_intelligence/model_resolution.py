"""Model auto-resolution runtime — refresh job + boot recorder + eval-divergence
guardrail (operator-ruled 2026-07-30). See shared/llm_models.py's AUTO-RESOLUTION
docstring for the full design (why the module-level constants there MUST stay
static, and why this file is where the actual dynamic behavior lives instead).

Four moving parts, all here except the resolve-itself (shared/model_resolver.py,
imported by shared/llm_models.py at import time — cache-file read only):

  1. `refresh_model_resolution` — nightly intelligence-side job. Calls the API's
     `models.list`, computes the newest concrete id per tier (shared/model_resolver.py
     ordering), and atomically rewrites the resolution cache
     (`logs/model_resolution.json`, bind-mounted so the execution container and the
     host deploy gates could read the same file — though the deploy gate deliberately
     does not; see shared/llm_models.py). A tier change is NEVER silent: audit event
     `model_release_detected` + Telegram, BEFORE the change takes effect — the new id
     only binds at the next process boot (shared.llm_models.RESOLVED_ROLES /
     effective_model), so the operator has a window to set an override in
     shared/llm_models.py `_TIER_OVERRIDES` if they don't want it.

  2. `record_boot_resolution` — boot hook (intelligence/combined role only, so the
     execution container never double-writes). Persists what every LLM ROLE is
     *effectively* running this process — via `shared.llm_models.effective_model`,
     so a RESOLVED_ROLES role (today: JUDGE_MODEL) reports its TRUE live value, not
     the static constant — into `mi_model_resolution` (insert-on-change,
     effective-dated in ET) and Telegrams + audit-logs any change
     (`model_resolution_change`). This answers "what was the judge running on
     2026-08-14?":

       SELECT model FROM mi_model_resolution
       WHERE role = 'JUDGE_MODEL'
         AND resolved_at < (('2026-08-14'::date + 1)::timestamp
                            AT TIME ZONE 'America/New_York')
       ORDER BY resolved_at DESC LIMIT 1;
       -- (db.get_model_resolution_asof; the timestamptz `<`-vs-`(date+1) AT TIME
       -- ZONE` cast pattern verified read-only against prod's mi_audit_log
       -- 2026-07-31 — mi_model_resolution itself does not exist in prod yet, this
       -- branch is unshipped)

     Joins BY DATE to the grade metrics: `judge_high_rate_daily` (system_audit.py)
     reads `mi_audit_log` rows with `event_type='ep_grade_decision'`, grouped by
     `(created_at AT TIME ZONE 'America/New_York')::date` — same ET-date key. The
     per-day payload is TEXT (can hold malformed rows; a raw SQL `->>` cast crashed
     on this exact table once, 7/11 corpus mine) so, mirroring
     `system_audit._judge_decision_rows_today`'s established safety pattern,
     `db.get_judge_grade_decisions_for_date(on_date)` fetches + parses it
     Python-side. So the correlated answer to "what was the judge running on date X,
     and how did its grades look" is two calls joined by the same `on_date`:

       asof   = await db.get_model_resolution_asof("JUDGE_MODEL", on_date)
       rows   = await db.get_judge_grade_decisions_for_date(on_date)
       high_rate = (sum(r["judge_tier"] == "HIGH" for r in rows) / len(rows)
                    if rows else None)

     — `asof["model"]` answers even on a quiet day with zero decisions (boot-driven,
     not decision-driven); `rows` gives the SAME malformed-row safety
     `judge_high_rate_daily` itself relies on, rather than duplicating a SQL JSON
     cast that has already broken production once on this table.

  3. `check_judge_eval_divergence` — NEW nightly WARN (never a block, item 2 of the
     #509 design): compares what THIS process is actually running the judge on
     (`shared.llm_models.effective_model("JUDGE_MODEL")`) against the model recorded
     in the last PASSING judge-robustness eval
     (`scripts/evals/judge_eval_pass_record.json`). This is exactly the comparison
     `scripts/preflight_judge_eval_gate.py` structurally cannot make — that gate runs
     on the HOST at deploy with no API/DB access and only ever re-parses this repo's
     COMMITTED source (the static `JUDGE_MODEL` pin), so a cache-resolved runtime
     value is invisible to it by construction. Loud WARN only (audit + Telegram):
     upgrading the judge needs a paid eval + operator sign-off (ADR-0030); a hard
     deploy block would hold every unrelated change hostage over a model release.

Part 4 (the resolve itself) lives in shared/model_resolver.py + is consumed by
shared/llm_models.py's `RESOLVED_ROLES`/`effective_model` at import — cache-file
read only, fail-safe to the pin, never a network call in that path.

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

import json
import logging
import os
from pathlib import Path

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

# scripts/evals/judge_eval_pass_record.json — same repo-relative path
# preflight_judge_eval_gate.py uses (REPO / "scripts" / "evals" / ...).
_EVAL_RECORD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "evals" / "judge_eval_pass_record.json"

_JUDGE_EVAL_NOTE = (
    "ADR-0030's preflight_judge_eval_gate blocks a DEPLOY only when the COMMITTED "
    "JUDGE_MODEL pin changes without a fresh passing eval — it cannot see this "
    "runtime auto-resolution (shared/llm_models.py AUTO-RESOLUTION docstring). "
    "The nightly check_judge_eval_divergence WARNs when the two drift apart; run "
    "the judge robustness eval on the resolved id, then bump JUDGE's pin, to "
    "formally adopt it."
)


def current_role_bindings() -> dict[str, str]:
    """ROLE constant name -> the model id THIS PROCESS is EFFECTIVELY running for
    that role. For a `llm_models.RESOLVED_ROLES` role (today: JUDGE_MODEL) this is
    the cache-resolved value (`llm_models.effective_model`) — the id
    `ep_grade_judge.py` actually binds its default `model=` to at import, which can
    differ from the plain registry constant. Every other role is its static
    constant, unchanged."""
    bindings = {
        name: value
        for name, value in vars(llm_models).items()
        if name.endswith("_MODEL") and isinstance(value, str)
    }
    for role in llm_models.RESOLVED_ROLES:
        bindings[role] = llm_models.effective_model(role)
    return bindings


def _role_source(role: str, model_id: str) -> tuple[str, str]:
    """(source, note) for a bound id: how the registry arrived at it. Role-driven
    (not a value->tier reverse lookup) — a role not in RESOLVED_ROLES is always
    "static" regardless of whether its id happens to parse into a known family
    (e.g. THEME_ADVISOR_MODEL's literal OPUS pin is static, not tier-tracked)."""
    res = llm_models.role_resolution(role)
    if res is not None:
        tier = llm_models.RESOLVED_ROLES.get(role, "?")
        return res.source, res.note or f"tier={tier}"
    return "static", "static registry pin (not in RESOLVED_ROLES)"


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
            source, note = _role_source(role, model)
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

    candidates = {t: [i for i in ids if llm_models.tier_of(i) == t] for t in TIERS}
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
        changed_tiers = {t for t, _o, _n in real}
        # RESOLVED_ROLES-driven, not a value->tier reverse lookup: which auto-
        # tracked roles sit on a tier that just moved (today: JUDGE_MODEL/opus).
        affected_roles = sorted(
            role for role, tier in llm_models.RESOLVED_ROLES.items() if tier in changed_tiers
        )
        lines = ["🆕 <b>New Claude release detected</b> (models.list)"]
        for tier, old, new in real:
            lines.append(f"{esc(tier)}: {code(esc(old))} → {code(esc(new))}")
        lines.append("Takes effect at the <b>next deploy/restart</b> of each "
                     "service — nothing changed mid-session.")
        if affected_roles:
            lines.append(f"⚠ These roles auto-track this release and will move at "
                         f"next boot: {esc(', '.join(affected_roles))}.")
            if "JUDGE_MODEL" in affected_roles:
                lines.append(esc(_JUDGE_EVAL_NOTE))
        lines.append("Don't want it? One edit BEFORE the next deploy: pin the "
                     "tier in <code>_TIER_OVERRIDES</code> "
                     "(shared/llm_models.py).")
        await _send_telegram("\n".join(lines))
    return len(resolved)


# ── Nightly eval-divergence guardrail ────────────────────────────────────────

async def check_judge_eval_divergence() -> None:
    """NEW nightly in-container guardrail (item 2 of the #509 design): compares
    the model this process is ACTUALLY running the judge on
    (`llm_models.effective_model("JUDGE_MODEL")`) against the model recorded in
    the last PASSING judge-robustness eval
    (`scripts/evals/judge_eval_pass_record.json`). Sees exactly what
    `scripts/preflight_judge_eval_gate.py` structurally cannot: that gate runs on
    the HOST at deploy with no API/DB access, re-parsing this repo's COMMITTED
    source only — a cache-resolved runtime value is invisible to it by
    construction (see shared/llm_models.py AUTO-RESOLUTION docstring).

    Loud WARN only (audit event `judge_model_eval_divergence` + Telegram) —
    NEVER a block. Adopting a new judge id needs a paid eval + operator sign-off
    (ADR-0030); a hard block here would hold every unrelated deploy hostage over
    a model release the operator hasn't even decided to adopt yet. Never raises —
    a guardrail bug must not take the nightly chain down."""
    from shared.telegram_format import code, esc

    try:
        running = llm_models.effective_model("JUDGE_MODEL")
        try:
            record = (
                json.loads(_EVAL_RECORD_PATH.read_text(encoding="utf-8"))
                if _EVAL_RECORD_PATH.exists() else None
            )
        except Exception as e:
            await log_audit_event(
                "model_resolution_eval_check_error",
                f"could not read judge eval pass record: {e}",
                f"path={_EVAL_RECORD_PATH}",
            )
            return

        evaluated = record.get("judge_model") if isinstance(record, dict) else None
        if not evaluated:
            await log_audit_event(
                "model_resolution_eval_check_error",
                "no judge eval pass record found (or record missing 'judge_model') "
                "— cannot compare",
                f"path={_EVAL_RECORD_PATH}",
            )
            return

        if running == evaluated:
            return  # in sync — no news, nothing to log or send

        await log_audit_event(
            "judge_model_eval_divergence",
            f"JUDGE_MODEL running {running} but last PASSING eval was on {evaluated}",
            f"eval run_at={record.get('run_at')}; not blocking — run the judge "
            f"robustness eval on {running} and get it green to make it the new "
            f"evaluated baseline (ADR-0030).",
        )
        await _send_telegram(
            "⚠️ <b>Judge model diverged from its last evaluated baseline</b>\n"
            f"Running: {code(esc(running))}\n"
            f"Last evaluated (passing): {code(esc(evaluated))}\n"
            "Not blocking deploys — but live grades are running on an UNEVALUATED "
            "id. Run the judge robustness eval to confirm quality (then bump "
            "JUDGE's pin), or set an override in <code>_TIER_OVERRIDES</code> "
            "(shared/llm_models.py) to hold it back."
        )
    except Exception as e:
        logger.error(f"check_judge_eval_divergence failed (non-fatal): {e}")
        try:
            await log_audit_event(
                "model_resolution_eval_check_error",
                f"check_judge_eval_divergence crashed: {type(e).__name__}: {e}",
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — log_audit_event
            # never raises by its own contract, but if it somehow did, logger.error
            # above already surfaced the original failure loudly; nothing above
            # this can handle a SECOND failure in the error-reporting path itself.
            pass
