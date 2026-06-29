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


# ─────────────────────────────────────────────────────────────────────────────
# #380 / #370 — DATA-API loud-failure guard (extends the #273 credit pattern to
# the data-fetch layer: Polygon, FMP, Perplexity-news).
#
# THE GAP this closes: the data-API wrappers RAISE on an HTTP/transport error,
# but their callers SWALLOW it (fail-open: except → fallback → empty). So a
# provider going dark (FMP's deprecated /api/v3/ → 403 on everything, a Polygon
# outage, a Perplexity 5xx) degrades the catalyst grade / RS universe / news
# corpus SILENTLY — exactly the "how did an API call fail silently?" class the
# operator flagged on 2026-06-25. The FMP 403 sat invisible for months precisely
# because nothing surfaced it (0 FMP errors in 72h of logs).
#
# THE FIX: a deduped operator alert fired AT THE WRAPPER's catch point, BEFORE
# the exception propagates to the swallowing caller. The wrapper's existing
# propagation is PRESERVED — `_fmp_get`/`_polygon_get` still re-raise (so the
# caller's fallback runs), `search_news_perplexity` still returns "" — the
# loudness comes from the ALERT, not from changing the contract. Graceful
# degradation, but LOUD.
#
# This is REACTIVE (alerts on observed failure), the same shape as the #273
# credit alarm. It does NOT alert on a code bug (JSONDecodeError/KeyError) — only
# on a genuine network/HTTP failure (positive classification below).
# ─────────────────────────────────────────────────────────────────────────────

# Per-process pre-gate for the data-API alarm. Keyed by (provider, error_class)
# so a 500 right after a 403 is NOT suppressed for 6h (the credit pre-gate keys
# by provider alone because a single provider has ONE exhaustion condition; a
# data API can flap across distinct failure modes). NON-authoritative — the
# audit-log lookback below is the durable, restart-proof dedup.
_last_api_alert_ts: dict[tuple[str, str], float] = {}

# Providers we surface a data-API alarm for. Anything else routes to "other"
# (still alerts — better a generic loud row than a silent swallow).
_API_PROVIDERS = ("polygon", "fmp", "perplexity")


def classify_api_failure(exc: BaseException) -> str | None:
    """Bucket a data-API exception into a coarse error-CLASS, or None when the
    exception is NOT a network/HTTP failure (so we never alert on a code bug).

    Returns one of: "http_4xx" | "http_5xx" | "timeout" | "connect" | "transport"
    — or None for anything that isn't a PROVIDER-HEALTH failure: a non-network
    code bug (JSONDecodeError / KeyError, which must NOT masquerade as "the
    provider is down"), OR an HTTP 404 (see below).

    404 CARVE-OUT (load-bearing): a 404 is "this ITEM doesn't exist," a per-CALL
    data condition — NOT a provider outage. Polygon's per-ticker endpoints
    (`/v3/reference/tickers/{ticker}`, the I:VIX index, per-ticker aggregates)
    routinely 404 on unknown/delisted tickers; alerting on those would fire a
    misleading "Polygon DOWN" several times a day (the 6h dedup can't save it —
    there's always SOME delisted ticker), training the operator to ignore the
    alarm. The actual failure this guard exists for — FMP's deprecated-API block
    and an auth/plan revocation — is 401/403, which stays loud. So 404 → None
    (no alert); 401/403/429/other-4xx/5xx/timeout/connect → loud.

    Positive classification by httpx type name (duck-typed so a stubbed httpx in
    tests still classifies). 429 IS included for the data layer (Polygon already
    retries 3× internally, so a 429 that reaches the except is SUSTAINED rate-
    limiting worth surfacing; the 6h dedup bounds the spam) — this is the
    deliberate inverse of the credit classifier, which excludes 429 because LLM
    429s self-heal and are handled by separate backoff.
    """
    try:
        name = type(exc).__name__
        # Timeouts: httpx.TimeoutException + subclasses (ConnectTimeout,
        # ReadTimeout, WriteTimeout, PoolTimeout) all end in "Timeout"/"TimeoutException".
        if "Timeout" in name:
            return "timeout"
        if name in ("ConnectError",):
            return "connect"
        # alpaca-py's retry-exhausted wrapper carries no status code, but a RetryException means the
        # underlying transport/API failure exhausted retries — a genuine persistent outage → alert.
        if name in ("RetryException", "RetryError"):
            return "transport"
        # HTTP status error (from raise_for_status()): bucket by status family.
        code = _status_code(exc)
        if name == "HTTPStatusError" or (code is not None and 400 <= code < 600):
            # 404 = item-not-found (per-call data condition), NOT provider health.
            if code == 404:
                return None
            if code is not None and 500 <= code < 600:
                return "http_5xx"
            if code is not None and 400 <= code < 500:
                return "http_4xx"
            return "http_error"
        # Other httpx transport failures (ConnectError handled above):
        # NetworkError, ReadError, RemoteProtocolError, ProxyError, etc. The
        # httpx base for these is TransportError.
        if name.endswith(("Error",)) and (
            "httpx" in type(exc).__module__
            or name in ("TransportError", "NetworkError", "ReadError",
                        "RemoteProtocolError", "ProxyError", "ProtocolError",
                        "ConnectError")
        ):
            return "transport"
        return None
    except Exception:  # classifier must never raise into a fail-open path
        return None


async def alert_api_failure(provider: str, exc: BaseException,
                            context: str = "") -> None:
    """One deduped operator alert that a DATA API (Polygon/FMP/Perplexity) is
    failing. ALWAYS safe to call from a fail-open/except block — never raises.

    Caller contract: call this at the wrapper's catch point, THEN let the
    wrapper propagate as it already does (re-raise or return its fallback). This
    function only ALERTS — it never re-raises, never swallows the caller's flow.

    Dedup (per (provider, error-class) per ~6h): mirrors alert_credit_exhausted.
    The audit row `api_failure_<provider>` is the durable dedup token; we look
    back `_ALERT_WINDOW_HOURS` for a row of the SAME provider AND error-class
    (the class is recorded in the row summary as `class=<cls>` and matched on
    read) and suppress a repeat. A non-authoritative in-process pre-gate keyed
    by (provider, class) collapses a same-process stampede before the row lands.
    """
    try:
        cls = classify_api_failure(exc)
        if cls is None:
            return  # not a network/HTTP failure — don't cry wolf on a code bug

        provider = provider if provider in _API_PROVIDERS else "other"
        event_type = f"api_failure_{provider}"
        key = (provider, cls)
        now = time.monotonic()

        # In-process pre-gate (accelerator only — NOT the source of truth).
        last = _last_api_alert_ts.get(key)
        if last is not None and (now - last) < _ALERT_WINDOW_S:
            return

        # Authoritative dedup: a SAME-(provider,class) row within the window?
        try:
            from agents.market_intelligence.db import get_audit_log
            recent = await get_audit_log(
                event_type=event_type, since_hours=_ALERT_WINDOW_HOURS, limit=20,
            )
            for row in (recent or []):
                if f"class={cls}" in (row.get("summary") or ""):
                    _last_api_alert_ts[key] = now  # keep the pre-gate honest
                    return
        except Exception:
            # DB unavailable — fall through and alert (better a possible dup than
            # a silently-swallowed API outage, the whole bug class #380/#370).
            pass

        # Claim the window in-process before any await that could interleave.
        _last_api_alert_ts[key] = now

        code = _status_code(exc)
        code_str = f" HTTP {code}" if code is not None else ""
        label = provider.upper()

        # Audit row FIRST (durable dedup token + queryable record). The
        # `class=<cls>` marker is load-bearing — the lookback matches on it.
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                event_type,
                f"{label} API FAILURE class={cls}{code_str}"
                + (f" — {context}" if context else ""),
                str(exc)[:400],
            )
        except Exception:
            pass

        # Then the operator Telegram (a data source going dark IS actionable —
        # it degrades the grade / universe / news corpus until fixed).
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            from shared.telegram_format import b, esc
            await send_telegram_message(
                f"⚠️ {b(f'{label} DATA-API FAILURE')} ({esc(cls)}{esc(code_str)})"
                + (f" in {esc(context)}" if context else "")
                + ".\n"
                + f"The {esc(label)} fetch is failing — the catalyst grade / RS "
                + "universe / news corpus that depends on it is silently "
                + "degrading until it recovers.\n"
                + "Check the provider status + our API key/plan, then verify the "
                + "next scan's data.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as _e:  # absolute belt-and-suspenders — never raise upward
        logger.debug("alert_api_failure swallowed for %s: %s", provider, _e)


async def maybe_alert_api_failure(provider: str, exc: BaseException,
                                  context: str = "") -> None:
    """Convenience wrapper: classify-then-alert, fully swallow-safe. Identical in
    spirit to maybe_alert_credit_exhausted but for the data-API layer. Safe to
    call from any wrapper's except block; it only ALERTS (the caller keeps full
    control of propagation)."""
    try:
        await alert_api_failure(provider, exc, context=context)
    except Exception as _e:  # noqa: BLE001 — swallow-by-design
        logger.debug("maybe_alert_api_failure swallowed for %s: %s", provider, _e)
