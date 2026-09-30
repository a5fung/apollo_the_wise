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
    audit_wrap; the trading system keeps running on the existing resolution);
  * a NEW release must pass the pre-adoption canary (`_canary_model`: every production
    request shape, through shared/llm_client's adapter) before it is written to the
    cache — a refused release keeps the tier on its last working id, audit + Telegram
    with the exact error, re-tried nightly (2026-09-23, after opus-5-5 broke both judges);
  * then it must answer our OWN recent requests (#690, 2026-09-30, after sonnet-5-5 passed
    the canary and refused the real theme prompts): the latest captured request per call
    site (shared/llm_samples.py) is replayed 3× on it. A failure HOLDS that role on its
    current id (`role_is_held`, cache `role_holds`) while the rest of the tier moves; a
    changed answer only goes to the per-tier digest Telegram; an unfinished replay (10-minute
    budget) adopts nothing on that tier tonight. Holds are re-tested nightly and released
    once the role's requests pass.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from agents.market_intelligence.constants import runs_intelligence_jobs
from agents.market_intelligence.db import (
    audit_event_exists,
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

# Operator-facing. The mechanism detail (which gate parses what) belongs in the
# docstrings, not in his Telegram — he needs to know the grade surface moved and
# what guards it.
#
# ⚠ NO EVAL ASK, by his ruling. This note used to say the nightly check "will flag it until
# you re-run the eval or accept it as-is". He had already ruled on 2026-07-30 to track the
# newest model per tier with guardrails AFTER the switch — "go with the leaders, but have
# guardrails to make sure there's no major degradation … and we can always trace back to when
# they were updated" — and on 2026-09-22, when Opus 5 → 5.5 was announced and I proposed an
# eval: "Why eval? This is just normal model update, I thought we decided not to eval on model
# updates as that happens often." He KEPT the notice ("I like the alert noting that new model
# … just not the eval"). So the notice stays and names the real guardrail instead.
_JUDGE_MOVE_NOTE = (
    "No eval for a routine release — your 2026-07-30 rule. After the switch, the nightly "
    "check on how often the judge grades HIGH is the guardrail. Deploys are not blocked."
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


def _render_transitions(changes: list[tuple]) -> list[str]:
    """`[(role, prev_id, new_id), ...]` -> grouped operator-facing lines.

    One block per DISTINCT version transition, listing what runs on it in plain
    words. Eleven roles moving sonnet-4-6 -> sonnet-5 is ONE block, not eleven
    lines. Roles with no label degrade to a readable form of their own name
    (llm_models.label_for), so a role added later can never render blank.
    """
    from shared.llm_models import label_for, pretty_model, tier_of
    from shared.telegram_format import esc

    groups: dict[tuple, list[str]] = {}
    for role, prev, new in changes:
        groups.setdefault((prev, new), []).append(label_for(role))
    # Strongest tier first — the judge is the one that moves the grade surface, so
    # it must not sit under nine sonnet roles. Unknown families sort last, never
    # crash the render.
    rank = {"opus": 0, "sonnet": 1, "haiku": 2}
    def _order(item):
        (prev, new), _roles = item
        return (rank.get(tier_of(new) or "", 9), new)
    out: list[str] = []
    for (prev, new), roles in sorted(groups.items(), key=_order):
        out.append(f"<b>{esc(pretty_model(prev))} → {esc(pretty_model(new))}</b>")
        out.append(f"  {esc(' · '.join(sorted(roles)))}")
        out.append("")
    return out


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
            lines = ["🤖 <b>Models updated this restart</b>", ""]
            # GROUPED BY TRANSITION, not one line per role (operator 2026-07-31:
            # "could use some better formatting"). 11 roles moving between the same
            # two ids rendered as 11 near-identical SCREAMING_SNAKE lines; what he
            # actually needs is "these two versions changed, and here is what runs
            # on each".
            lines.extend(_render_transitions([(r, p, m) for r, p, m, _ in real]))
            lines.append("Watch grade rates over the next few days "
                         "(<code>judge_high_rate_daily</code>, L2 audit).")
            if any(r == "JUDGE_MODEL" for r, *_ in real):
                lines.append(esc(_JUDGE_MOVE_NOTE))
            # Output-ceiling sweep (2026-08-09, follow-up to #543): every max_tokens
            # ceiling is registered with the model it was sized on
            # (shared/output_ceilings.py). A role's model changing is THE event that
            # invalidates those numbers — both August truncation outages happened on a
            # role's first post-change calls — so name the exposed callers at the
            # moment the binding changes, not after the first cut-off response.
            from shared.output_ceilings import callers_for_role
            exposed = sorted({c for role, *_ in real for c in callers_for_role(role)})
            if exposed:
                await log_audit_event(
                    "output_ceilings_model_drift",
                    f"{len(exposed)} output ceiling(s) were sized on a model that just "
                    "changed: " + ", ".join(exposed),
                    "watch the live truncation alarm + nightly near-ceiling check; "
                    "re-evidence the entries in shared/output_ceilings.py",
                )
                lines.append(
                    f"⚠ {len(exposed)} output ceiling(s) were sized on the previous "
                    "model — the truncation alarms are watching these:")
                lines.append(f"<code>{esc(' · '.join(exposed))}</code>")
            lines.append("Undo: pin the tier in "
                         "<code>shared/llm_models.py</code> and redeploy.")
            await _send_telegram("\n".join(lines))
        elif changes:
            logger.info("model_resolution: baseline recorded for %d role(s)", len(changes))
    except Exception as e:
        # forensic-only path: never block boot, but never be silent either
        logger.error(f"model_resolution boot recorder failed (non-fatal): {e}")


# ── Fallback-pin staleness ───────────────────────────────────────────────────
# The resolver keeps the LIVE bindings current. The `*_PIN` literals in
# shared/llm_models.py are the OFFLINE FALLBACK — what every role degrades to if
# models.list is unreachable at boot. Nothing advances those; left alone they rot
# exactly like the hand-maintained bindings did (theme advisor on opus-4-6, the
# metrics extractor on a sonnet-4-5 pin flagged 2026-06-09 and never revisited).
# So the pin gets a path too (operator 2026-07-31: "all models need a path to
# upgrade, nothing shall remain stale"): once a tier has served a NEWER model for
# 30 days straight, say so — daily audit row, monthly Telegram nudge (day 30, 60,
# 90 …), so it is a standing reminder and not a daily nag.
_PIN_DRIFT_DAYS = 30


def stale_tier_pins(resolved: dict, changed_at: dict, now=None) -> list[tuple]:
    """(tier, pin, served_id, days_behind) for each tier whose fallback pin has
    sat behind the served model for >= _PIN_DRIFT_DAYS.

    A tier with no `changed_at` (baseline/first record) is NOT reported — we
    can't date the drift, and guessing would fabricate the age.
    """
    from datetime import datetime, timezone
    from shared import llm_models

    now = now or datetime.now(timezone.utc)
    out = []
    for tier, served in sorted(resolved.items()):
        pin = llm_models._TIER_PINS.get(tier)
        if not pin or served == pin:
            continue
        since = changed_at.get(tier)
        if not since:
            continue
        try:
            days = (now - datetime.fromisoformat(since)).days
        except (ValueError, TypeError):
            continue
        if days >= _PIN_DRIFT_DAYS:
            out.append((tier, pin, served, days))
    return out


# ── Nightly refresh ──────────────────────────────────────────────────────────

async def _list_model_ids() -> list[str]:
    from shared.llm_client import make_async_anthropic
    client = make_async_anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    try:
        return [m.id async for m in client.models.list()]
    finally:
        await client.close()


# ── Pre-adoption canary (2026-09-23) ─────────────────────────────────────────
# claude-opus-5-5 was adopted by this job on 09-22 and rejected every forced-tool call the
# judges make (HTTP 400) — the refresh had no idea, because it only ever asked models.list
# which ids EXIST, never whether OUR request shapes work on them. Now, before a new release
# becomes a tier's cached id, it must pass every production request shape THROUGH the
# transport adapter (shared/llm_client.run_canary): a forced tool, thinking disabled, a
# plain call, and "any" over two tools. Pass → adopted exactly as before (automatic, no eval —
# operator rulings 2026-07-30 and 2026-09-22). Fail → the tier KEEPS its last working id, an
# audit row + Telegram carry the exact error, and the id is re-tried at the next nightly run
# (so a fix on either side is picked up without anyone remembering to re-enable anything).
# Cost: four ~100-token calls per NEW release only; nothing on an ordinary night.
# ⚠ LIMIT, found 2026-09-28: the canary proves the SHAPES, not that the model will answer OUR
# prompts — claude-sonnet-5-5 passed it and then refused the real theme prompts. A release that
# passes the canary now also faces the replay of our own requests below (#690); the canary stays
# first because it is four cheap calls that catch a transport break before any real prompt is sent.

async def _canary_model(model_id: str) -> tuple[bool, str]:
    """(passed, failure_text) for `model_id`, via a factory client. Never raises."""
    from shared.llm_client import make_async_anthropic, run_canary
    try:
        client = make_async_anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    except Exception as e:  # loud-ok: reported as a failure, never a crash of the refresh
        return False, f"client construction failed: {type(e).__name__}: {e}"
    try:
        results = await run_canary(client, model_id)
    finally:
        try:
            await client.close()
        except Exception:  # loud-ok: nothing to do with the verdict
            pass
    failed = [r for r in results if not r.ok]
    if not failed:
        return True, ""
    return False, "; ".join(f"{r.check}: {r.detail}" for r in failed)


async def _report_rejected_release(tier: str, keep: str, new: str, error: str) -> None:
    """Audit + Telegram a release the canary refused — ONCE per (tier, new, keep) triple, so a
    release that stays broken does not page every weeknight. A dedupe-lookup failure SENDS
    (a skipped release must never be silent)."""
    from shared.llm_models import pretty_model
    from shared.telegram_format import code, esc

    summary = f"{tier}: {new} failed the pre-adoption canary — keeping {keep}"
    try:
        if await audit_event_exists("model_release_rejected", summary):
            logger.info("model_resolution: %s (already reported)", summary)
            return
    except Exception as e:  # loud-ok: fail toward SENDING
        logger.warning(f"_report_rejected_release: dedupe lookup failed, sending: {e}")
    await log_audit_event("model_release_rejected", summary, f"canary: {error[:900]}")
    await _send_telegram(
        "🚫 <b>New Claude model NOT adopted</b>\n"
        f"<b>{esc(pretty_model(new))}</b> ({code(esc(new))}) failed the request-shape check, so "
        f"the {esc(tier)} tier stays on {code(esc(keep))}.\n"
        f"Error: <code>{esc(error[:600])}</code>\n"
        "It is re-checked every night and adopts automatically once it passes. Nothing to do "
        "unless you want to force it: pin the tier in <code>_TIER_OVERRIDES</code> "
        "(shared/llm_models.py)."
    )


# ── Pre-adoption REPLAY of our own requests + per-role holds (#690, 2026-09-30) ──────────────
# The canary above proves the request SHAPES work; it cannot prove the model will ANSWER our
# prompts. On 2026-09-28 claude-sonnet-5-5 passed it and was adopted, then refused the real theme
# prompts (they asked it to write its reasoning out) — nobody knew until the night run failed. So
# a release that passes the canary is now also sent the LATEST real request each call site made
# (shared/llm_samples.py captures them; shared/llm_call_sites.py maps call site -> role), 3 times
# each, before the cache moves. The operator's ask (2026-09-29): "make sure nothing fails and we
# are aware of any major differences, good or bad".
#   * a FAILURE (see judge_replay_response / _classify_replay_error) HOLDS that role on its
#     current id — role_is_held is the one rule; the rest of the tier still moves;
#   * a CHANGED answer never holds; it goes to the per-tier digest Telegram (decision fields only);
#   * an unfinished replay (the 10-minute budget) adopts nothing on that tier tonight;
#   * holds live in the cache (`role_holds`), are re-tested every night and released once the
#     role's samples pass on the tier's model.
# Cost: per release event, at most (tracked call-site keys on that tier) x 3 calls on the new
# model; nothing on an ordinary night (no tier change and no hold → no replay).

REPLAY_RUNS = 3
REPLAY_CONCURRENCY = 3
REPLAY_CALL_TIMEOUT_S = 90.0
REPLAY_BUDGET_S = 600.0
_AUDIT_DETAIL_CAP = 7000

PASS, FAIL, UNJUDGED, BUDGET = "pass", "fail", "unjudged", "budget"
_TRANSIENT = "transient"   # internal only: retried once, then UNJUDGED — never a failure


@dataclass
class RunResult:
    verdict: str                  # PASS | FAIL | UNJUDGED | BUDGET
    error: str = ""
    answer: Optional[dict] = None


@dataclass
class KeyReplay:
    key: str
    role: str
    subject: str
    old_answer: dict
    runs: list[RunResult] = field(default_factory=list)


def role_is_held(runs: Iterable[RunResult]) -> bool:
    """THE HOLD RULE — proposed to the operator 2026-09-30, pending his confirm; change it HERE.

    A ROLE IS HELD if ANY run of ANY of its samples FAILS (refused, rejected, cut off, no tool
    call, a tool answer missing required fields, an empty answer). Changed answers NEVER hold —
    they go to the digest. Unjudged runs (rate limit, overload, timeout) never hold. Applies to the
    judge roles too; their ADR-0030 eval gate is separate and untouched."""
    return any(r.verdict == FAIL for r in runs)


def _first_failure(runs: Iterable[RunResult]) -> str:
    return next((r.error for r in runs if r.verdict == FAIL), "")


def _block_type(b: Any) -> str:
    return str(b.get("type") if isinstance(b, dict) else getattr(b, "type", "") or "")


def judge_replay_response(request: dict, resp: Any) -> RunResult:
    """PASS/FAIL for one replayed answer against what its caller needs from it."""
    from shared.llm_response import first_text, stop_reason
    from shared.llm_samples import answer_summary

    try:
        answer = answer_summary(resp)
    except Exception as e:  # loud-ok: an unreadable answer is reported, never raised
        logger.warning("model replay: could not summarize an answer: %s", e)
        answer = None
    sr = stop_reason(resp)
    if sr == "refusal":
        return RunResult(FAIL, "refused", answer)
    if sr == "max_tokens":
        return RunResult(FAIL, f"cut off at its own max_tokens ({request.get('max_tokens')})", answer)
    tools = {t.get("name"): t for t in request.get("tools") or [] if isinstance(t, dict)}
    tc = request.get("tool_choice") if isinstance(request.get("tool_choice"), dict) else {}
    uses = [b for b in getattr(resp, "content", None) or [] if _block_type(b) == "tool_use"]
    if tc.get("type") in ("tool", "any") and not uses:
        return RunResult(FAIL, "answered without the required tool call", answer)
    for b in uses:
        name = b.get("name") if isinstance(b, dict) else getattr(b, "name", None)
        inp = b.get("input") if isinstance(b, dict) else getattr(b, "input", None)
        schema = (tools.get(name) or {}).get("input_schema") or {}
        required = [k for k in schema.get("required") or [] if isinstance(k, str)]
        missing = [k for k in required if not isinstance(inp, dict) or k not in inp]
        if missing:
            return RunResult(FAIL, f"tool answer missing {', '.join(missing)}", answer)
    if not uses and not first_text(resp).strip():
        return RunResult(FAIL, "empty answer", answer)
    return RunResult(PASS, "", answer)


def _classify_replay_error(e: BaseException) -> RunResult:
    """An exception from a replayed call → FAIL (HTTP 4xx other than 429 after the adapter,
    unreadable/refused structured output) or TRANSIENT (429/5xx/529/timeout/connection). Anything
    else is UNJUDGED with its text — the hold rule is only the enumerated failure classes."""
    from shared.llm_client import StructuredOutputError

    text = str(getattr(e, "message", "") or e)
    if isinstance(e, StructuredOutputError):
        return RunResult(FAIL, "refused" if "refus" in text else f"unreadable answer: {text[:160]}")
    status = getattr(e, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        if status == 429 or status >= 500:
            return RunResult(_TRANSIENT, f"HTTP {status}")
        if 400 <= status < 500:
            return RunResult(FAIL, f"rejected (HTTP {status}): {text[:160]}")
    name = type(e).__name__
    if isinstance(e, TimeoutError) or any(w in name for w in ("Timeout", "Connection", "Overloaded")):
        return RunResult(_TRANSIENT, name)
    return RunResult(UNJUDGED, f"{name}: {text[:160]}")


def _replay_client():
    """A FRESH factory client (the adapter, so a replay re-adapts for the candidate model)."""
    from shared.llm_client import make_async_anthropic
    return make_async_anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


async def _log_replay_spend(model: str, resp: Any) -> None:
    from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
    await log_anthropic_call_safe(model=model, caller="model_replay", response=resp)


async def _replay_once(client, request: dict, deadline: float, sem: asyncio.Semaphore) -> RunResult:
    async with sem:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return RunResult(BUDGET, "the replay time budget ran out")
        timeout = min(REPLAY_CALL_TIMEOUT_S, remaining)
        try:
            resp = await asyncio.wait_for(client.messages.create(**copy.deepcopy(request)),
                                          timeout=timeout)
        except TimeoutError:
            if timeout < REPLAY_CALL_TIMEOUT_S:
                return RunResult(BUDGET, "the replay time budget ran out mid-call")
            return RunResult(_TRANSIENT, f"no answer within {int(REPLAY_CALL_TIMEOUT_S)}s")
        except Exception as e:  # loud-ok: every error is classified and reported, never raised
            return _classify_replay_error(e)
    await _log_replay_spend(str(request.get("model")), resp)
    return judge_replay_response(request, resp)


async def _replay_run(client, request: dict, deadline: float, sem: asyncio.Semaphore) -> RunResult:
    """One run: a transient error is retried ONCE, then counted UNJUDGED (never a failure)."""
    result = await _replay_once(client, request, deadline, sem)
    if result.verdict == _TRANSIENT:
        retry = await _replay_once(client, request, deadline, sem)
        if retry.verdict == _TRANSIENT:
            return RunResult(UNJUDGED, f"{retry.error} (twice)")
        return retry
    return result


def _replay_inventory(roles: set[str], recorded_model: str) -> tuple[list[tuple[str, str, dict]], dict[str, int]]:
    """([(key, role, latest replayable sample recorded on `recorded_model`)] for call sites whose
    role is in `roles`, {role: requests skipped as credential-like}) — role via the call-site map."""
    from shared.llm_call_sites import CALL_SITES
    from shared.llm_samples import load_all

    entries: list[tuple[str, str, dict]] = []
    skips: dict[str, int] = {}
    for data in load_all():
        key = data["key"]
        role = CALL_SITES.get(key)
        if role not in roles:
            continue
        sk = (data.get("skipped") or {}).get("credential_like")
        if isinstance(sk, dict) and sk.get("count"):
            skips[role] = skips.get(role, 0) + int(sk["count"])
        cands = [s for s in data["samples"] if isinstance(s, dict) and s.get("replayable")
                 and s.get("model") == recorded_model and isinstance(s.get("request"), dict)]
        if cands:
            latest = max(cands, key=lambda s: str(s.get("captured_at") or ""))
            entries.append((key, role, latest))
    return entries, skips


async def _replay_entries(entries: list[tuple[str, str, dict]], new_id: str,
                          deadline: float) -> list[KeyReplay]:
    """Each entry's request REPLAY_RUNS times on `new_id` (bounded concurrency, capture off)."""
    if not entries:
        return []
    from shared.llm_samples import capture_disabled

    def _blank(err: str) -> list[KeyReplay]:
        return [KeyReplay(k, r, s.get("subject") or "", s.get("answer") or {},
                          [RunResult(UNJUDGED, err)] * REPLAY_RUNS) for k, r, s in entries]
    try:
        client = _replay_client()
    except Exception as e:  # loud-ok: reported as unjudged runs, never a crash of the refresh
        logger.warning("model replay: client construction failed: %s", e)
        return _blank(f"client construction failed: {type(e).__name__}")
    sem = asyncio.Semaphore(REPLAY_CONCURRENCY)

    async def _one_key(key: str, role: str, sample: dict) -> KeyReplay:
        request = dict(sample["request"])
        request["model"] = new_id
        runs = await asyncio.gather(*[_replay_run(client, request, deadline, sem)
                                      for _ in range(REPLAY_RUNS)])
        return KeyReplay(key, role, sample.get("subject") or "", sample.get("answer") or {}, list(runs))

    try:
        with capture_disabled():   # tasks created here inherit it — no replay becomes a sample
            return list(await asyncio.gather(*[_one_key(*e) for e in entries]))
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                res = close()
                if inspect.isawaitable(res):
                    await res
            except Exception as e:  # loud-ok: closing has nothing to do with the verdicts
                logger.debug("model replay: client close failed: %s", e)


# ── Old-vs-new comparison on DECISION fields (the digest) ────────────────────
_FREE_TEXT_TOKENS = ("reason", "rationale", "analysis", "notes", "summary", "thesis",
                     "description", "story", "scratchpad")
_SHORT = 40
_MISSING = object()


def _decision_value(v: Any) -> Any:
    """A comparable form of a decision value, or _MISSING when the value is free text / nested."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        return v if len(v) <= _SHORT else _MISSING
    if isinstance(v, list):
        items = [_decision_value(x) for x in v]
        if any(x is _MISSING or isinstance(x, list) for x in items):
            return _MISSING
        return sorted(items, key=repr)
    return _MISSING


def _fmt(v: Any) -> str:
    if v is _MISSING or v is None:
        return "(none)"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def decision_diff(old: dict, new: dict) -> tuple[str, list[str]]:
    """("text" | "same" | "changed", [diff lines]) comparing two answer summaries on decision
    fields only: the tool name, then each top-level tool-input field that is a bool/number/short
    string (<= 40 chars) or a list of those. Free-text fields (reason, rationale, analysis, …) and
    long strings are skipped. Plain-text answers are not compared."""
    old_tool, new_tool = old.get("tool"), new.get("tool")
    if old_tool is None and new_tool is None:
        return "text", []
    if old_tool is None or new_tool is None:
        return "changed", ["answered in text" if new_tool is None else "answered with a tool call"]
    if old_tool != new_tool:
        return "changed", [f"tool {old_tool} → {new_tool}"]
    oi = old.get("tool_input") if isinstance(old.get("tool_input"), dict) else {}
    ni = new.get("tool_input") if isinstance(new.get("tool_input"), dict) else {}
    diffs = []
    for field_name in sorted(set(oi) | set(ni)):
        if any(tok in field_name.lower() for tok in _FREE_TEXT_TOKENS):
            continue
        ov = _decision_value(oi[field_name]) if field_name in oi else None
        nv = _decision_value(ni[field_name]) if field_name in ni else None
        if ov is _MISSING or nv is _MISSING:
            continue
        if ov != nv or type(ov) is not type(nv):
            diffs.append(f"{field_name} {_fmt(ov)} → {_fmt(nv)}")
    return ("changed" if diffs else "same"), diffs


def _first_answered(runs: list[RunResult]) -> Optional[RunResult]:
    return next((r for r in runs if r.verdict == PASS and r.answer is not None), None)


def _role_counts_line(label: str, replays: list[KeyReplay]) -> str:
    from shared.telegram_format import esc
    same = changed = text = unjudged = 0
    details: list[str] = []
    why_unjudged = ""
    for kr in replays:
        first = _first_answered(kr.runs)
        if first is None:
            unjudged += 1
            why_unjudged = why_unjudged or next((r.error for r in kr.runs if r.error), "")
            continue
        kind, diffs = decision_diff(kr.old_answer or {}, first.answer or {})
        if kind == "text":
            text += 1
        elif kind == "same":
            same += 1
        else:
            changed += 1
            if len(details) < 2:
                details.append("; ".join(diffs[:2]) + (f" on {kr.subject}" if kr.subject else ""))
    parts = []
    if same:
        parts.append(f"{same} same")
    if changed:
        parts.append(f"{changed} changed ({' | '.join(details)})")
    if text:
        parts.append(f"{text} text answer{'s' if text > 1 else ''}, not compared")
    if unjudged:
        parts.append(f"{unjudged} could not be checked ({why_unjudged[:80]})")
    return f"• {esc(label)}: {esc(', '.join(parts) or 'nothing to compare')}"


def _render_tier_digest(tier: str, old: Optional[str], new: str, current: str,
                        replays: list[KeyReplay], skips: dict[str, int],
                        new_holds: dict[str, dict], retests: dict[str, tuple[str, str]]) -> str:
    """ONE operator Telegram for a tier adoption: the move, then what each role's own recent
    requests did on the new model. `retests` = {role: ("released"|"held", text)} for roles that
    were already held on this tier."""
    from shared.llm_models import label_for, pretty_model
    from shared.llm_samples import EXCLUDED_ROLES
    from shared.telegram_format import esc

    roles = sorted(r for r, t in llm_models.RESOLVED_ROLES.items() if t == tier)
    lines = ["🆕 <b>New Claude model available</b>",
             f"<b>{esc(pretty_model(old or current))} → {esc(pretty_model(new))}</b> "
             f"({esc(tier)} tier)", ""]
    replayed_roles = {kr.role for kr in replays}
    held_lines, role_lines, no_sample, not_sampled = [], [], [], []
    for role in roles:
        label = label_for(role)
        if role in new_holds:
            held_lines.append(f"• {esc(label)}: <b>HELD</b> on {esc(pretty_model(new_holds[role]['model']))} "
                              f"— {esc(str(new_holds[role].get('error') or '')[:160])}")
        elif role in retests:
            state, text = retests[role]
            (held_lines if state == "held" else role_lines).append(f"• {esc(label)}: {esc(text)}")
        elif role in replayed_roles:
            role_lines.append(_role_counts_line(label, [kr for kr in replays if kr.role == role]))
        elif role in EXCLUDED_ROLES:
            not_sampled.append(label)
        else:
            n = skips.get(role, 0)
            no_sample.append(label + (f" ({n} not kept — they looked like they held a password)"
                                      if n else ""))
    if held_lines or role_lines:
        lines.append(f"Our own recent requests, replayed {REPLAY_RUNS}× on it:")
        lines.extend(held_lines + role_lines)
    if no_sample:
        lines.append(f"• no recent request to replay: {esc(' · '.join(no_sample))}")
    if not_sampled:
        lines.append(f"• never sampled (your chat / pings): {esc(' · '.join(not_sampled))}")
    lines.append("")
    held_note = (f" Held roles stay on {esc(pretty_model(current))} and are re-checked every night."
                 if new_holds else "")
    lines.append("Nothing changed yet — it takes effect at the <b>next deploy or restart</b>, "
                 f"never mid-session.{held_note}")
    if "JUDGE_MODEL" in roles and "JUDGE_MODEL" not in new_holds:
        lines.append(esc(_JUDGE_MOVE_NOTE))
    lines.append("Don't want it? One edit BEFORE the next deploy: pin the tier in "
                 "<code>_TIER_OVERRIDES</code> (shared/llm_models.py).")
    return "\n".join(lines)


def _digest_detail(tier: str, old: Optional[str], new: str, replays: list[KeyReplay],
                   holds: dict[str, dict]) -> str:
    """The full per-key results for the audit row (capped at the audit detail budget)."""
    rows = []
    for kr in replays:
        first = _first_answered(kr.runs)
        kind, diffs = decision_diff(kr.old_answer or {}, first.answer or {}) if first else ("unjudged", [])
        rows.append({"key": kr.key, "role": kr.role, "subject": kr.subject,
                     "runs": [{"verdict": r.verdict, "error": r.error[:200]} for r in kr.runs],
                     "compare": kind, "diffs": diffs[:10]})
    text = json.dumps({"tier": tier, "old": old, "new": new, "holds": holds, "keys": rows},
                      default=str, sort_keys=True)
    return text if len(text) <= _AUDIT_DETAIL_CAP else text[: _AUDIT_DETAIL_CAP - 12] + "…(capped)"


async def _report_replay_budget(tier: str, keep: str, new: str) -> None:
    """The replay ran out of time before this tier's requests were judged: nothing on the tier
    moved tonight. Audit row every night; Telegram ONCE per (tier, new, keep) — a lookup failure
    SENDS."""
    from shared.llm_models import pretty_model
    from shared.telegram_format import code, esc

    summary = (f"{tier}: {new} not adopted — the replay of our own requests ran out of time; "
               f"keeping {keep}")
    announced = False
    try:
        announced = await audit_event_exists("model_replay_budget_exhausted", summary)
    except Exception as e:  # loud-ok: fail toward SENDING
        logger.warning(f"_report_replay_budget: dedupe lookup failed, sending: {e}")
    await log_audit_event("model_replay_budget_exhausted", summary,
                          f"budget={int(REPLAY_BUDGET_S)}s; retried at the next nightly refresh")
    if announced:
        return
    await _send_telegram(
        "⏳ <b>New Claude model not adopted tonight</b>\n"
        f"Checking {esc(pretty_model(new))} ({code(esc(new))}) against our own recent requests ran "
        f"out of its {int(REPLAY_BUDGET_S // 60)}-minute budget, so the {esc(tier)} tier stays on "
        f"{code(esc(keep))}. It retries every night; nothing to do unless this repeats."
    )


def _valid_holds(prev: Optional[dict]) -> dict[str, dict]:
    holds = (prev or {}).get("role_holds")
    if not isinstance(holds, dict):
        return {}
    return {r: dict(h) for r, h in holds.items()
            if isinstance(h, dict) and isinstance(h.get("model"), str)}


async def refresh_model_resolution() -> int:
    """Refresh the resolution cache from `models.list`. Returns tiers written.

    Raises on API failure (audit_wrap records the failed run; the cache — and
    therefore the trading system's bindings — are left untouched)."""
    from shared.llm_models import label_for, pretty_model
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

    # PRE-ADOPTION CANARY — see _canary_model. Only tiers that would CHANGE are checked; a
    # refused release leaves the tier on its last working id (or the committed pin when there
    # is no prior record), so nothing downstream can ever bind to an id the judges cannot call.
    rejected: list[tuple[str, str, str, str]] = []  # (tier, keep, new, error)
    for tier, old_id, new_id in list(changes):
        passed, error = await _canary_model(new_id)
        if passed:
            continue
        keep = old_id or llm_models._TIER_PINS[tier]
        resolved[tier] = keep
        changes.remove((tier, old_id, new_id))
        rejected.append((tier, keep, new_id, error))
    for tier, keep, new_id, error in rejected:
        await _report_rejected_release(tier, keep, new_id, error)

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    # PRE-ADOPTION REPLAY (#690) — see role_is_held and the block comment above it. ONE budget
    # for the whole night: tier changes first, then the re-test of existing holds.
    deadline = time.monotonic() + REPLAY_BUDGET_S
    prev_holds = _valid_holds(prev)
    holds: dict[str, dict] = {r: dict(h) for r, h in prev_holds.items()}
    tier_replays: dict[str, tuple[str, list[KeyReplay], dict[str, int]]] = {}
    new_holds: dict[str, dict] = {}
    for tier, old_id, new_id in list(changes):
        current = old_id or llm_models._TIER_PINS[tier]
        # A role already held is re-tested below — its samples carry its held id, not `current`.
        roles = {r for r, t in llm_models.RESOLVED_ROLES.items() if t == tier and r not in prev_holds}
        entries, skips = _replay_inventory(roles, current)
        replays = await _replay_entries(entries, new_id, deadline)
        if any(r.verdict == BUDGET for kr in replays for r in kr.runs):
            resolved[tier] = current
            changes.remove((tier, old_id, new_id))
            await _report_replay_budget(tier, current, new_id)
            continue
        tier_replays[tier] = (current, replays, skips)
        for role in sorted({kr.role for kr in replays}):
            runs = [r for kr in replays if kr.role == role for r in kr.runs]
            if role_is_held(runs):
                holds[role] = new_holds[role] = {
                    "model": current, "since": now_iso, "error": _first_failure(runs)[:300],
                    "candidate": new_id}

    # HOLD RE-TEST — every existing hold, every night: released once its role's own requests
    # pass on the tier's model (or the hold is moot); kept while any run fails or none was judged.
    retests: dict[str, tuple[str, str]] = {}      # role -> ("released"|"held", operator text)
    released: list[tuple[str, str, str]] = []     # (role, held id, target id)
    for role, info in sorted(prev_holds.items()):
        tier = llm_models.RESOLVED_ROLES.get(role)
        target = resolved.get(tier) if tier else None
        held = info["model"]
        if not tier or not target or not is_newer(target, held):
            holds.pop(role, None)
            released.append((role, held, target or held))
            retests[role] = ("released", "hold released — its tier is back on the held model")
            continue
        entries, _skips = _replay_inventory({role}, held)
        if not entries:
            holds.pop(role, None)
            released.append((role, held, target))
            retests[role] = ("released", "hold released — no recent request to replay")
            continue
        runs = [r for kr in await _replay_entries(entries, target, deadline) for r in kr.runs]
        if any(r.verdict == BUDGET for r in runs):
            retests[role] = ("held", f"still HELD on {pretty_model(held)} — re-check ran out of time")
        elif role_is_held(runs):
            holds[role] = {**info, "error": _first_failure(runs)[:300], "candidate": target}
            retests[role] = ("held", f"still HELD on {pretty_model(held)} — {_first_failure(runs)[:160]}")
        elif any(r.verdict == PASS for r in runs):
            holds.pop(role, None)
            released.append((role, held, target))
            retests[role] = ("released", f"hold released — its requests pass on {pretty_model(target)}")
        else:
            retests[role] = ("held", f"still HELD on {pretty_model(held)} — nothing could be checked")

    changed_at = dict(prev_changed)
    for tier, _old, _new in changes:
        changed_at[tier] = now_iso

    candidates = {t: [i for i in ids if llm_models.tier_of(i) == t] for t in TIERS}
    path = write_cache(resolved, changed_at, candidates=candidates, role_holds=holds)
    logger.info("model_resolution: cache refreshed at %s — %s holds=%s", path, resolved, sorted(holds))

    for tier, old, new in changes:
        await log_audit_event(
            "model_release_detected",
            f"{tier}: {old or '(first record)'} -> {new}",
            f"takes effect at next boot; cache={path}",
        )
    for role, info in sorted(new_holds.items()):
        await log_audit_event(
            "model_role_held",
            f"{role}: held on {info['model']} — {info['candidate']} failed the replay of our own requests",
            str(info.get("error") or ""),
        )
    for role, held, target in released:
        await log_audit_event("model_role_hold_released",
                              f"{role}: released from {held}; moves to {target} at the next boot",
                              retests.get(role, ("", ""))[1])

    # ONE Telegram per tier adoption: the move + what each role's own requests did on it.
    digested: set[str] = set()
    for tier, old, new in changes:
        current, replays, skips = tier_replays.get(tier, (old or llm_models._TIER_PINS[tier], [], {}))
        tier_new_holds = {r: h for r, h in new_holds.items() if llm_models.RESOLVED_ROLES.get(r) == tier}
        tier_retests = {r: v for r, v in retests.items() if llm_models.RESOLVED_ROLES.get(r) == tier}
        await log_audit_event(
            "model_replay_digest",
            f"{tier}: {old or '(first record)'} -> {new}: {len(replays)} call site(s) replayed, "
            f"{len(tier_new_holds)} role(s) held",
            _digest_detail(tier, old, new, replays, tier_new_holds),
        )
        if old is None and not tier_new_holds:
            continue  # first-ever record: nothing to compare against, no Telegram on cold start
        digested.update(tier_retests)
        await _send_telegram(_render_tier_digest(tier, old, new, current, replays, skips,
                                                 tier_new_holds, tier_retests))
    late = [(r, h, t) for r, h, t in released if r not in digested]
    if late:
        lines = ["✅ <b>Model hold released</b>"]
        for role, held, target in late:
            lines.append(f"• {esc(label_for(role))}: moves from {esc(pretty_model(held))} to "
                         f"{esc(pretty_model(target))} at the next restart.")
        await _send_telegram("\n".join(lines))

    # the fallback pins get an upgrade path too — see stale_tier_pins()
    for tier, pin, served, days in stale_tier_pins(resolved, changed_at):
        # BOTH the row and the nudge are throttled to the monthly boundary. An
        # ungated audit write would insert one row per stale tier per weekday
        # FOREVER once a pin drifts, each restating an identical fact — unbounded
        # log growth carrying no new signal. Known gap: a missed run can step over
        # the boundary (29 -> 32) and skip a month; the condition persists, so the
        # next boundary reports it. That beats a daily row nobody reads.
        if days % _PIN_DRIFT_DAYS == 0:
            await log_audit_event(
                "model_pin_drift",
                f"{tier}: offline fallback pin {pin} is {days}d behind served {served}",
                "re-point the *_PIN literal in shared/llm_models.py — live bindings "
                "are already current; only a resolver outage would serve the pin",
            )
            await _send_telegram(
                f"🧷 <b>Fallback pin behind</b> — {esc(tier)} has served "
                f"{code(esc(served))} for {days}d while the offline fallback is "
                f"still {code(esc(pin))}.\nNo live impact (bindings resolve at "
                f"boot); it only bites during a models.list outage. Fix: "
                f"re-point <code>{esc(tier.upper())}_PIN</code> in "
                f"shared/llm_models.py."
            )
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

    A NOTICE, sent ONCE per (running, evaluated) pair — never a block, and never an eval
    demand. Never raises — a guardrail bug must not take the nightly chain down.

    ⚠ REWRITTEN 2026-09-22 ON HIS RULING, and the two halves of the change are separate:
    (1) **no eval ask.** This used to tell him that adopting a new judge id needs "a paid eval
    + operator sign-off (ADR-0030)" and to "run the judge robustness eval to confirm quality".
    He ruled 2026-07-30 to track the newest model per tier with guardrails AFTER the switch,
    and reaffirmed it 2026-09-22 — *"Why eval? This is just normal model update, I thought we
    decided not to eval on model updates as that happens often"* — while KEEPING the notice:
    *"I want to keep it to notify me when a model is updated, just not the eval."* ADR-0030's
    eval still gates RUBRIC / prompt / corpus changes at deploy (`preflight_judge_eval_gate`);
    a routine same-family model release is not one of those.
    (2) **once, not nightly.** It had no dedupe, so with no eval ever re-run the pass record
    never moves, and from the day a new release binds it would have paged him EVERY WEEKNIGHT
    indefinitely. It now looks for its own prior audit row for the SAME pair and stays quiet if
    it already said so. A NEW pair — the next release — announces again. If that lookup itself
    fails it SENDS rather than suppresses: a model change must never go silent (his guardrail
    #2), and a duplicate is cheaper than a missed change."""
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

        # ONE announcement per (running, evaluated) pair. The summary is built from the pair
        # alone, so an exact match on a prior row is an exact "already said this".
        summary = f"JUDGE_MODEL now on {running}; last evaluated model {evaluated}"
        try:
            from agents.market_intelligence.db import audit_event_exists
            if await audit_event_exists("judge_model_eval_divergence", summary):
                return  # already announced this exact change — once, not nightly
        except Exception as e:  # loud-ok: fail toward SENDING — a missed change is worse
            logger.warning(f"check_judge_eval_divergence: dedupe lookup failed, sending: {e}")

        await log_audit_event(
            "judge_model_eval_divergence",
            summary,
            f"eval run_at={record.get('run_at')}; routine release adopted on the tier, no eval "
            f"by operator ruling 2026-07-30 (reaffirmed 2026-09-22). Guardrail = the nightly "
            f"judge_high_rate_daily L2 check. Rollback = pin the tier in _TIER_OVERRIDES.",
        )
        await _send_telegram(
            "🔁 <b>Grading judge is running a new model</b>\n"
            f"Now: {code(esc(running))}\n"
            f"Last evaluated: {code(esc(evaluated))}\n"
            "No eval for a routine release — your 2026-07-30 rule. Watch how often it grades "
            "HIGH over the next few days. To roll back, pin the tier in "
            "<code>_TIER_OVERRIDES</code> (shared/llm_models.py) and redeploy.\n"
            "<i>Sent once per model change.</i>"
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
