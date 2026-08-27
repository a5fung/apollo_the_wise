"""
Market-agent local spend tracker — mirrors core.spend (orchestrator) but
writes to the shared `api_usage` table via market-agent's own DB pool.

Architectural note (2026-05-13): `core.spend` lives in the orchestrator
container and imports `core.memory.get_pool`. Market-agent's Docker image
does NOT include `core/memory.py`, so `from core.spend import log_api_usage`
raises ModuleNotFoundError when called from any market-agent module —
silently caught by the upstream except, leaving the market-agent's
Anthropic costs unlogged. This file is the bridge: same row schema, same
pricing function, but uses market-agent's `db.get_pool` directly.

Use from any market-agent module that makes an Anthropic call:

    from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
    from shared.llm_models import effective_model
    model = effective_model("THEME_ADVISOR_MODEL")   # never a hardcoded id
    response = await client.messages.create(model=model, ...)
    await log_anthropic_call_safe(
        model=model,
        caller="theme_advisor",
        response=response,
    )

THE CONTRACT IS THE RAW RESPONSE, NOT ITS PIECES (#543, 2026-08-08). These
functions take `response=` and derive token usage AND stop_reason internally
(via `shared.llm_response`) — a call site structurally CANNOT report cost
without also reporting why the model stopped. The old `usage=`/`stop_reason=`
kwargs are REMOVED, not deprecated: `stop_reason` was hand-threaded as
`getattr(resp, "stop_reason", None)` at ~22 sites, the identical copy-paste
shape the paragraph below warns about, and a silently-optional kwarg is how
the 2026-08-07 truncation outage could only be DETECTED next-morning (the
nightly NULL arm) instead of PREVENTED. A site that genuinely aggregates
hand-built counts (none exist today) must construct a response-shaped dict
`{"usage": {...}, "stop_reason": ...}` — an explicit, reviewable act, never
an omittable kwarg. The nightly NULL/truncation check stays as defence in
depth.

`log_anthropic_call_safe` is the SANCTIONED call-site wrapper (S2/F9, post-#377).
Call sites must call it directly and must NOT re-wrap it in their own
`try/except ... pass` — that ~16-site copy-paste pattern is exactly how spend
telemetry could go dark with zero signal if the tracker ever broke (the May 2026
outage class this file exists to prevent). Use the bare `log_anthropic_call`
below only from within `spend_tracker.py` itself (or from a caller that has its
own bespoke fail-soft/fail-loud handling, e.g. a forced-tool transport isolating
the cost-log path from its verdict path).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.market_intelligence.db import get_pool
from shared.llm_models import (
    DEFAULT_PERPLEXITY_REQUEST_FEE_USD as _DEFAULT_PPLX_FEE,
    PERPLEXITY_REQUEST_FEE_USD as _PPLX_FEE,
)
from shared.llm_models import pricing_for as _pricing_for
from shared.llm_response import (
    perplexity_finish_reason as _pplx_finish_reason,
    perplexity_usage_tokens as _pplx_usage_tokens,
    stop_reason as _stop_reason_of,
    usage_tokens as _usage_tokens_of,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Telegram dedup for the LIVE truncation alarm: one message per (caller, ET day).
# Process-local by design — worst case after a restart is one repeat message.
# The audit row is written on EVERY truncated call (never deduped).
_TRUNCATION_TELEGRAMMED: dict[str, str] = {}


async def _measured_history(caller: str) -> tuple[float | None, int | None]:
    """(mean, typical/clean-call max) of `caller`'s COMPLETED — i.e. non-truncated
    — output tokens, all-time. This is the evidence `diagnose_truncation` needs to
    tell "no headroom" from "one outlier" apart, read fresh at alert time rather
    than guessed.

    Swallows every failure and returns (None, None): the live alarm this feeds
    must still fire (caller/model/cap) even when this read fails — a
    diagnosis-only query must never be able to take the whole alert down with it.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT avg(output_tokens) AS mean_completed,
                       max(output_tokens) AS max_completed
                  FROM api_usage
                 WHERE caller = $1
                   AND stop_reason IS NOT NULL
                   AND stop_reason <> 'max_tokens'
                """,
                caller,
            )
    except Exception as e:
        logger.warning(f"truncation diagnosis history read failed for {caller}: {e}")
        return None, None
    if row is None or row["mean_completed"] is None:
        return None, None
    return float(row["mean_completed"]), int(row["max_completed"])


async def _maybe_alert_truncation(*, caller: str, model: str, output_tokens: int) -> None:
    """LIVE truncation alarm (2026-08-09, follow-up to #543; diagnosis added
    2026-08-19).

    The nightly cost_board check detects a bound ceiling NEXT-nightly; this fires
    the moment a truncated response flows through the spend tracker — the one
    chokepoint every instrumented call already passes (#543 contract), so every
    call site gets a live alarm with zero per-site changes. Audit row per event;
    Telegram deduped per (caller, ET day). NEVER raises into the logging path.

    2026-08-19: the old advice here — "raise the ceiling" — was wrong for both
    real cases it fired on the same week: theme_discovery is on the do-not-raise
    list (a straight raise had already re-pegged it within days), and
    theme_validation truncated with ~1000 tokens of headroom over a 31-token mean
    (one oversized-input call, not a tight cap). `diagnose_truncation` reads the
    caller's own measured history from shared/output_ceilings.py and says which
    of three situations this actually is, instead of prescribing one fix for
    every caller.
    """
    try:
        from shared.output_ceilings import TRUNCATION_BY_DESIGN
        if caller in TRUNCATION_BY_DESIGN:
            return
        from shared.output_ceilings import diagnose_truncation, max_tokens_for
        try:
            cap = max_tokens_for(caller)
        except KeyError:
            cap = None
        if cap is None:
            diagnosis = (
                f"{caller} is not registered in shared/output_ceilings.py — cannot "
                "judge headroom.")
        else:
            mean_completed, typical_max = await _measured_history(caller)
            diagnosis = diagnose_truncation(
                caller, cap=cap, this_call_tokens=output_tokens,
                mean_completed=mean_completed, typical_max_completed=typical_max)

        from agents.market_intelligence.db import log_audit_event
        await log_audit_event(
            "llm_truncation_live",
            f"{caller} response TRUNCATED at {output_tokens} output tokens (model {model})",
            diagnosis,
        )
        today = datetime.now(_ET).date().isoformat()
        if _TRUNCATION_TELEGRAMMED.get(caller) == today:
            return
        _TRUNCATION_TELEGRAMMED[caller] = today
        cap_text = f"/{cap}" if cap is not None else ""
        from agents.market_intelligence.briefing import send_telegram_message
        # Caller names and the diagnosis text both carry snake_case / underscored paths
        # (e.g. shared/output_ceilings.py) — #477 parity: EVERYTHING with a bare
        # underscore must sit inside the SAME code fence, or Telegram Markdown V1 reads
        # the underscores as italic markers and mangles the message.
        await send_telegram_message(
            "🔴 *TRUNCATED (live)* — a response was just cut off by its output ceiling:\n"
            f"```\n{caller}  at {output_tokens}{cap_text} tokens  ({model})\n\n"
            f"{diagnosis}\n```\n"
            "The nightly check repeats until fixed.")
    except Exception as e:  # loud-ok: the alarm must never break the spend-logging path
        logger.warning(f"live truncation alarm failed for {caller}: {e}")


def _cost_for_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """`pricing_for` (not a raw dict `.get`) so an auto-resolved RESOLVED_ROLES
    id not yet in PRICING_PER_MTOK prices at its tier's rate instead of the
    flat default (#509)."""
    prices = _pricing_for(model)
    base_input = prices["input"]
    regular_input = max(input_tokens - cache_creation_tokens - cache_read_tokens, 0)
    cost = (
        (regular_input / 1_000_000) * base_input
        + (cache_creation_tokens / 1_000_000) * base_input * 1.25
        + (cache_read_tokens / 1_000_000) * base_input * 0.10
        + (output_tokens / 1_000_000) * prices["output"]
    )
    return round(cost, 6)


_SCHEMA_ENSURED = False


async def _ensure_schema() -> None:
    """Ensure api_usage table exists. Idempotent. Cached after first success.

    Advisor 2026-05-13 caught: spend_tracker assumed api_usage existed
    because orchestrator's core.spend.initialize_spend_schema() creates it.
    On any cold-restart that brings up market-agent first, INSERTs would
    silently fail — exactly the silent-failure pattern this file fixes.
    """
    global _SCHEMA_ENSURED
    if _SCHEMA_ENSURED:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id              SERIAL PRIMARY KEY,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                model           TEXT NOT NULL,
                caller          TEXT NOT NULL,
                input_tokens    INT NOT NULL DEFAULT 0,
                output_tokens   INT NOT NULL DEFAULT 0,
                cache_creation  INT NOT NULL DEFAULT 0,
                cache_read      INT NOT NULL DEFAULT 0,
                cost_usd        DOUBLE PRECISION NOT NULL DEFAULT 0
            );
            -- stop_reason (#543, 2026-08-07): the model's OWN report of why it stopped.
            -- 'max_tokens' = the response was TRUNCATED by the ceiling. Without this column
            -- truncation could only be INFERRED (output_tokens == a cap we don't store), which
            -- is how theme_assignment burned exactly 4000 tokens nightly for 10 days while
            -- reading as "proposed 0 assignments" — a telemetry line, not an error. ALTER (not
            -- just CREATE) because the table already exists everywhere.
            ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS stop_reason TEXT;
            CREATE INDEX IF NOT EXISTS idx_api_usage_created
                ON api_usage(created_at);
        """)
    _SCHEMA_ENSURED = True


async def log_anthropic_call(
    *,
    model: str,
    caller: str,
    response: Any,
) -> float:
    """Log an Anthropic API call. `response` is the RAW response — the SDK object
    or the raw-HTTP JSON dict; token usage and stop_reason are both derived from
    it here. Returns the computed cost in USD. Raises on DB failure (callers
    should wrap if they want fail-soft semantics).

    Why no fail-soft default: spend-tracker silently swallowing errors is
    exactly how the May 2026 outage hid for 12 days. Surface failures
    loudly at the call site; the call site can choose try/except + WARNING.

    Why `response=` and not `usage=` + `stop_reason=` (#543): the split kwargs
    made stop_reason omittable, and an omitted stop_reason means truncation at
    that site can only be DETECTED next morning (the nightly NULL arm), not
    prevented — the 2026-08-07 outage shape. Taking the response once makes
    passing one without the other impossible. The old kwargs are gone, not
    deprecated: a leftover old-style call raises TypeError instead of quietly
    writing NULLs, and the AST scan in test_truncation_self_reporting_543
    fails the build before it could ever run.
    """
    usage = _usage_tokens_of(response)
    if usage is None:
        logger.warning(f"log_anthropic_call({caller}): response carries no usage — skipping")
        return 0.0
    stop = _stop_reason_of(response)
    if stop is None:
        # A completed SDK response always carries stop_reason; a raw-HTTP dict should too.
        # Reaching here means the response SHAPE changed under us — warn now, and the row's
        # NULL is surfaced by the nightly truncation check (defence in depth, #543).
        logger.warning(
            f"log_anthropic_call({caller}): response carries no stop_reason — truncation at "
            "this call site cannot be detected (#543)")

    cost = _cost_for_call(
        model=model,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cache_creation_tokens=usage["cache_creation_input_tokens"],
        cache_read_tokens=usage["cache_read_input_tokens"],
    )

    await _ensure_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO api_usage
                (model, caller, input_tokens, output_tokens,
                 cache_creation, cache_read, cost_usd, stop_reason)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            model, caller, usage["input_tokens"], usage["output_tokens"],
            usage["cache_creation_input_tokens"], usage["cache_read_input_tokens"],
            cost, stop,
        )
    if stop == "max_tokens":
        await _maybe_alert_truncation(
            caller=caller, model=model, output_tokens=usage["output_tokens"])
    return cost


async def log_anthropic_call_safe(
    *,
    model: str,
    caller: str,
    response: Any,
) -> None:
    """The SANCTIONED call-site wrapper for `log_anthropic_call` (S2/F9, 2026-07-03).

    Calls `log_anthropic_call` and, on ANY Exception, logs exactly ONE WARNING
    and returns — it never raises into the caller's real work.

    This exists because the #377 cost meter was wired by copy-pasting
    `try: ... await log_anthropic_call(...) except Exception: pass` at ~16 call
    sites across the codebase. Most of those swallowed silently: if the tracker
    broke, ALL spend telemetry went dark with zero signal — the exact class of
    outage (12 days, May 2026) the tracker itself was built to catch. Call sites
    MUST call this wrapper directly and must NOT re-wrap it in their own
    try/except-pass; that reintroduces the same blind spot this fixes.
    """
    try:
        await log_anthropic_call(model=model, caller=caller, response=response)
    except Exception as e:  # loud-ok: sanctioned single warning sink for #377 cost-meter call sites (S2/F9) — the one place allowed to swallow a tracker failure, and it does so loudly
        logger.warning(f"spend tracking failed at {caller}: {e}")


async def log_perplexity_call(
    *,
    caller: str,
    response: Any,
    model: str | None = None,
) -> float:
    """Log a Perplexity (#377 cost meter) call to api_usage. Separate shape from
    Anthropic because Perplexity (a) names its usage fields OpenAI-style
    (`prompt_tokens`/`completion_tokens`, NOT `input_tokens`/`output_tokens`) and
    (b) charges a per-request SEARCH FEE on top of the token cost. Both are folded
    into one `cost_usd` row here.

    `response` is the RAW Perplexity JSON (the `r.json()` dict) — tokens and
    finish_reason are derived from it here, same #543 contract as
    `log_anthropic_call`: a site cannot report cost without reporting why the
    model stopped. Tokens default to 0 when the usage block is absent (the
    per-request fee still lands, which is the dominant cost anyway). `model`
    selects the token + fee rates ("sonar-pro" default, "sonar" for the cheaper
    validation path). Returns the computed cost in USD. Raises on DB failure —
    callers wrap in try/except for fail-soft (mirrors log_anthropic_call).
    """
    # #603 (2026-08-27) — Agent API shape, with the legacy Sonar shape still handled so
    # historical replays and any straggler caller keep working.
    _u = (response or {}).get("usage") if isinstance(response, dict) else None
    _agent = isinstance(_u, dict) and ("input_tokens" in _u or "cost" in _u)
    if _agent:
        # 🔒 NO MODEL NAME IS PASSED BY CALLERS ANY MORE. The Agent API picks the model from
        # the PRESET and REPORTS which one it used, so the row records what actually ran
        # instead of a literal we would have to hand-maintain (2026-08-27 probe: the "fast"
        # preset came back on `openai/gpt-5.6-luna`). Fallback string only if it is absent.
        model = model or (response.get("model") if isinstance(response, dict) else None) \
            or "perplexity-agent"
        input_tokens = int(_u.get("input_tokens") or 0)
        output_tokens = int(_u.get("output_tokens") or 0)
        # `status`/`incomplete_details` replace finish_reason. Never NULL (#543).
        _inc = (response.get("incomplete_details") or {}) if isinstance(response, dict) else {}
        reason = (_inc.get("reason") if isinstance(_inc, dict) and _inc.get("reason")
                  else response.get("status") if isinstance(response, dict) else None)
    else:
        model = model or "sonar-pro"
        usage = _pplx_usage_tokens(response)
        input_tokens = usage["prompt_tokens"]
        output_tokens = usage["completion_tokens"]
        reason = _pplx_finish_reason(response)
    # Perplexity names it finish_reason and says 'length' for truncation. Normalised
    # to Anthropic's vocabulary so ONE health check covers both providers. Never NULL:
    # NULL is reserved to mean "a call site forgot to report" (#543).
    stop = (
        "max_tokens" if str(reason) == "length"
        else (str(reason) if reason is not None else "n/a")
    )

    # 💰 THE AGENT API REPORTS ITS OWN ACTUAL COST — use it rather than recomputing from a
    # rate table we would have to keep in step with their pricing page (the same
    # hand-maintenance the model pin had). `usage.cost.total_cost` already folds tokens,
    # cache creation and the per-search tool fee into one USD figure (2026-08-27 probe:
    # $0.01119 = 0.00003 input + 0.00063 output + 0.00553 cache + 0.005 search).
    _reported = None
    if _agent and isinstance(_u.get("cost"), dict):
        try:
            _reported = float(_u["cost"]["total_cost"])
        except (KeyError, TypeError, ValueError):
            _reported = None
    if _reported is not None:
        cost = round(_reported, 6)
    else:
        # Legacy Sonar rows, and the fail-safe if they ever stop reporting cost: the old
        # estimate. Never leaves a call uncosted.
        prices = _pricing_for(model)
        request_fee = _PPLX_FEE.get(model, _DEFAULT_PPLX_FEE)
        token_cost = (
            (input_tokens / 1_000_000) * prices["input"]
            + (output_tokens / 1_000_000) * prices["output"]
        )
        cost = round(token_cost + request_fee, 6)

    await _ensure_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO api_usage
                (model, caller, input_tokens, output_tokens,
                 cache_creation, cache_read, cost_usd, stop_reason)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            model, caller, input_tokens, output_tokens, 0, 0, cost, stop,
        )
    if stop == "max_tokens":
        await _maybe_alert_truncation(
            caller=caller, model=model, output_tokens=output_tokens)
    return cost
