"""#273 — LLM credit / quota-EXHAUSTION alerting (silent-failure hardening).

THE GAP this closes: when an LLM provider's credits/quota run out, every API
call fails — and Apollo's fail-open design converts that into SILENT
degradation. The EP catalyst grade falls back to "routine", the holistic judge
fails open to the floor, theme synthesis/validation keeps all tickers, and the
Perplexity #186A cross-check returns "". Nothing tells the operator the LLM
layer has gone dark, so trades grade wrong until someone notices by hand. On
2026-06-11 (Phase B replay) Anthropic credit exhaustion produced 2,122 silent
judge fail-opens, initially misdiagnosed as rate limiting.

Credit exhaustion is TERMINAL + ACTIONABLE (the operator must refill) — the
exact class the alerting rules say must Telegram, never just log. This module
gives every swallow-point a cheap CLASSIFIER + a DB-deduped alarm.

THE KEY DISTINCTION (make-or-break): a rate-limit (HTTP 429) self-heals on
retry and is ALREADY handled elsewhere (`anthropic_rate_limited` /
`validation_rate_limited` audit + backoff) — it must NEVER credit-alert. Credit
exhaustion (Anthropic 400 "credit balance too low" / 403 billing_error;
Perplexity 402 / 401) means the feature is DOWN until refilled. The classifier
excludes 429 FIRST, then positive-matches exhaustion.

DEFERRED (separate, harder piece — NOT built here): proactive spend telemetry /
low-balance warning via the provider billing/usage endpoints. This module is the
REACTIVE exhaustion alert.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Telegram dedup window. The exhausted condition PERSISTS (every call keeps
# failing until refill) — one alert per provider per window, not one per failed
# call. 6h is long enough to not re-nag mid-trading-day, short enough to re-
# surface if the operator missed it. Authoritative dedup is the AUDIT-LOG
# lookback (container-restart-proof, per feedback_scheduler_aggregators_db_sourced
# — module state resets on restart and would spam). The in-process timestamp
# below is a NON-AUTHORITATIVE pre-gate (an accelerator that suppresses a
# same-process stampede before the first audit row commits — it is never the
# source of truth, so a restart simply falls through to the DB layer).
_ALERT_WINDOW_HOURS = 6
_ALERT_WINDOW_S = _ALERT_WINDOW_HOURS * 3600

# Per-process pre-gate: {provider: monotonic_ts_of_last_alert}. Not durable by
# design — the DB lookback is the real dedup; this only collapses a burst of
# near-simultaneous failures in ONE process before the row lands.
_last_alert_ts: dict[str, float] = {}

# Provider → audit event_type (exact-match dedup lookback keys on this).
_EVENT_BY_PROVIDER = {
    "anthropic": "anthropic_credits_exhausted",
    "perplexity": "perplexity_credits_exhausted",
}

# Anthropic credit-exhaustion message markers. The Anthropic 400 credit error is
# a BadRequestError whose .type is "invalid_request_error" — SAME type as a
# malformed request — so for the 400 path the MESSAGE marker is load-bearing; a
# bare 400 is NOT exhaustion (do not widen to all 400s). The clean typed signal
# is .type == "billing_error" (the 403 case), checked first below.
_ANTHROPIC_CREDIT_MARKERS = (
    "credit balance",       # "Your credit balance is too low to access the API …"
    "purchase credits",     # "… go to Plans & Billing to upgrade or purchase credits"
    "billing",              # generic billing failures
)


def _status_code(exc: BaseException) -> int | None:
    """Best-effort HTTP status from an Anthropic APIStatusError (.status_code)
    or an httpx.HTTPStatusError (.response.status_code). All getattr-guarded so
    this never raises on an arbitrary exception."""
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    return code if isinstance(code, int) else None


def is_credit_error(exc: BaseException) -> bool:
    """True ONLY for a billing/credit-EXHAUSTION failure — never for a transient
    rate-limit. Total: every access is getattr-guarded, so it can be called from
    any fail-open except block without ever raising.

    Order is load-bearing:
      1. RATE-LIMIT EXCLUSION FIRST. A 429 (anthropic.RateLimitError, or any exc
         with status_code 429) self-heals on retry and is handled elsewhere —
         return False unconditionally before any positive match. This is the
         make-or-break distinction (#273).
      2. Anthropic typed billing signal: .type == "billing_error" (the 403 case;
         APIStatusError exposes .type). Cleanest, no string matching.
      3. Anthropic 400/403 WITH a credit message marker — the 400 credit error
         shares .type "invalid_request_error" with malformed requests, so the
         marker is required (don't classify a bare 400 as exhaustion).
      4. Perplexity (httpx.HTTPStatusError from raise_for_status()): 402 Payment
         Required or 401 (no credits / invalid key). str(exc) contains no credit
         words ("Client error '402 Payment Required' …"), so this MUST go by
         status code, not message.
    """
    try:
        code = _status_code(exc)

        # (1) Rate-limit exclusion — must come first.
        if code == 429:
            return False
        if type(exc).__name__ == "RateLimitError":  # defensive: stubbed/proxied SDK
            return False

        msg = str(exc).lower()
        etype = getattr(exc, "type", None)  # APIStatusError.type, e.g. "billing_error"

        # (2) Anthropic typed billing signal (403 billing_error).
        if etype == "billing_error":
            return True

        # (3) Anthropic 400/403 with an explicit credit/billing message marker.
        if code in (400, 403) and any(m in msg for m in _ANTHROPIC_CREDIT_MARKERS):
            return True

        # (4) Quota / auth exhaustion by status code (message has no markers).
        #     402 Payment Required = credits exhausted; 401 = no credits / revoked
        #     or invalid key. Both are TERMINAL, operator-actionable "LLM-dark"
        #     states — the exact silent-degradation class #273 targets — so we
        #     alert conservatively (alert-not-swallow) rather than risk missing a
        #     real outage. NOTE: 401 is auth as much as credit; the alert copy
        #     says "CREDITS / AUTH" so the wording isn't misleading. (This branch
        #     is provider-agnostic, so an Anthropic 401/403-without-marker also
        #     trips it — intentional, same terminal class.)
        if code in (402, 401):
            return True

        return False
    except Exception:  # never let the classifier itself raise into a fail-open path
        return False


async def alert_credit_exhausted(context: str, exc: BaseException,
                                 provider: str = "anthropic") -> None:
    """One deduped operator alert that an LLM provider's credits are exhausted.

    ALWAYS safe to call from a fail-open except block — never raises.

    Dedup (per provider per ~6h): the AUDIT ROW is the dedup token. We look back
    `_ALERT_WINDOW_HOURS` for an existing `<provider>_credits_exhausted` row; if
    one exists, we suppress BOTH the new row and the Telegram. The audit-log
    lookback is container-restart-proof (the durable dedup source). A
    non-authoritative in-process pre-gate collapses a same-process stampede
    before the first row commits. The audit row is written BEFORE the Telegram
    send so the dedup token exists as early as possible.
    """
    provider = provider if provider in _EVENT_BY_PROVIDER else "anthropic"
    event_type = _EVENT_BY_PROVIDER[provider]
    now = time.monotonic()

    # In-process pre-gate (accelerator only — NOT the source of truth).
    last = _last_alert_ts.get(provider)
    if last is not None and (now - last) < _ALERT_WINDOW_S:
        return

    # Authoritative dedup: has a row for this provider landed within the window?
    try:
        from agents.market_intelligence.db import get_audit_log
        recent = await get_audit_log(
            event_type=event_type, since_hours=_ALERT_WINDOW_HOURS, limit=1,
        )
        if recent:
            _last_alert_ts[provider] = now  # keep the pre-gate honest
            return
    except Exception:
        # DB unavailable — fall through and alert (better a possible dup than a
        # silently-swallowed credit outage, which is the whole bug class #273).
        pass

    # Claim the window in-process before any await that could interleave.
    _last_alert_ts[provider] = now

    label = provider.capitalize()
    # Audit row FIRST (the durable dedup token + a queryable record).
    try:
        from agents.market_intelligence.db import log_audit_event
        await log_audit_event(
            event_type,
            f"{label} LLM CREDITS/AUTH EXHAUSTED — detected in {context}; "
            f"grading/synthesis/validation degraded until refilled",
            str(exc)[:400],
        )
    except Exception:
        pass

    # Then the operator Telegram (terminal + actionable). "CREDITS / AUTH"
    # because a 401 is a revoked/invalid-key state as much as a no-credits one.
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        from shared.telegram_format import b, esc
        await send_telegram_message(
            f"⚠️ {b(f'{label.upper()} LLM CREDITS / AUTH FAILURE')} — detected in "
            f"{esc(context)}.\n"
            f"LLM grading / synthesis / validation is silently degrading "
            f"(catalyst grades → 'routine', judge → floor, Perplexity → empty) "
            f"until the {esc(label)} balance is refilled / key is fixed.\n"
            f"Check billing + the API key, then verify the next scan's grade rows.",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def maybe_alert_credit_exhausted(context: str, exc: BaseException,
                                       provider: str = "anthropic") -> None:
    """Single home for the is_credit_error -> alert_credit_exhausted -> swallow contract that was
    hand-copied at the LLM call sites. ALWAYS safe in a fail-open except block — never raises (the
    point is to ADD an alert to a path that already degrades gracefully, not turn it into a crash)."""
    try:
        if is_credit_error(exc):
            await alert_credit_exhausted(context, exc, provider=provider)
    except Exception as _e:  # noqa: BLE001 — swallow-by-design; never raise into a fail-open caller
        logger.debug("maybe_alert_credit_exhausted swallowed for %s: %s", context, _e)
