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
import re
import time
from datetime import datetime, timezone

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
    except Exception:  # loud-ok: pure classifier over an arbitrary exception object —
        # attribute access (getattr-guarded above) is the only thing that can raise
        # here, and "not a credit error" is the correct safe default, not a swallowed
        # failure. Never let the classifier itself raise into a fail-open path.
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
    except Exception as e:
        # DB unavailable — fall through and alert (better a possible dup than a
        # silently-swallowed credit outage, which is the whole bug class #273).
        logger.warning("alert_credit_exhausted dedup lookback failed for %s "
                        "(falling through to alert): %s", provider, e)

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
    except Exception as e:
        logger.warning("alert_credit_exhausted audit-row write failed for %s: %s",
                        provider, e)

    # Then the operator Telegram (terminal + actionable). "CREDITS / AUTH"
    # because a 401 is a revoked/invalid-key state as much as a no-credits one.
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        from shared.telegram_format import b, esc
        await send_telegram_message(
            f"⚠️ {b(f'{label.upper()} LLM CREDITS / AUTH FAILURE')} — detected in "
            f"{esc(context)}.\n"
            f"LLM grading / synthesis / validation is silently degrading "
            f"(catalyst grades → 'routine', the judge stops reviewing so our own score's "
            f"alert tier stands, Perplexity → empty) "
            f"until the {esc(label)} balance is refilled / key is fixed.\n"
            f"Check billing + the API key, then verify the next scan's grade rows.",
            parse_mode="HTML",
        )
    except Exception as e:
        # Last step, nothing above can handle it further — the audit row (if it
        # landed) is still the durable record even if this Telegram send failed.
        logger.warning("alert_credit_exhausted Telegram send failed for %s: %s",
                        provider, e)


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
# (still alerts — better a generic loud row than a silent swallow). 'alpaca' is
# the BROKER (real-money-critical reads: get_account / get_open_orders /
# get_all_positions in broker/alpaca_client.py) — added #406. It was wired at
# the alpaca_client call sites on 6/29 (maybe_alert_api_failure("alpaca", ...))
# but never registered here, so every alpaca failure silently fell through to
# "other" (mis-bucketed dedup/query event_type) AND inherited the data-API
# consequence sentence below — wrong DOMAIN for a broker outage (which degrades
# position-sync/trade-state, not the catalyst grade / RS universe / news
# corpus). Still loud either way, but a mislabeled wrong-domain alert on a
# real-money path trains the operator to dismiss it.
_API_PROVIDERS = ("polygon", "fmp", "perplexity", "alpaca")

# Alarm copy varies by provider CLASS, not per-provider — a small mapping, not
# an if-chain. Data-APIs (polygon/fmp/perplexity/unlisted-"other") degrade the
# catalyst grade / RS universe / news corpus; alpaca is the BROKER — its reads
# feed position sync and trade state, a different domain entirely (#406).
# Providers absent from `_PROVIDER_CLASS` default to "data" (the historical
# sentence, and correct for "other").
_PROVIDER_CLASS = {"alpaca": "broker"}

_ALARM_COPY_BY_CLASS = {
    "data": {
        "kind": "DATA-API",
        "consequence": "the catalyst grade / RS universe / news corpus that depends on it",
    },
    "broker": {
        "kind": "BROKER-API",
        "consequence": "position sync / trade state that depends on it",
    },
}


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
    except Exception:  # loud-ok: pure classifier over an arbitrary exception object —
        # attribute access (getattr-guarded above) is the only thing that can raise
        # here, and "not a network/HTTP failure" is the correct safe default, not a
        # swallowed failure. Classifier must never raise into a fail-open path.
        return None


# ── Fix-1 (2026-07-14) — TRANSIENT vs ACTIONABLE triage for the Telegram send ──
#
# The #380 guard Telegrammed EVERY classified data-API failure (deduped 6h).
# In practice two failure shapes are TRANSIENT / self-healing and were paging
# the operator daily against the alert-vs-audit rule ("Reserve Telegram for
# terminal/actionable events. Self-healing/transient → mi_audit_log only"):
#   - Perplexity `timeout` — the caller fails open and the next scan recovers;
#   - FMP per-symbol HTTP 402 — a plan-tier gate on SOME symbols (most work),
#     fail-open per symbol; NOT account-wide payment exhaustion.
# New contract:
#   AUDIT ROW: written for EVERY classified failure (visibility to the morning
#     banner / `show errors` / sweeps is unconditional — this is the durable
#     record). Rows carry ` tg=<0|1>` marking whether a Telegram accompanied
#     them; only tg=1 rows count as the alert-dedup token.
#   TELEGRAM:
#     ACTIONABLE (auth 401/403, 5xx, 429-after-retries, other 4xx, transport
#       classes on the BROKER) → immediate, deduped per (provider,class) per 6h
#       — unchanged from #380.
#     TRANSIENT (timeout / connect / transport on DATA providers; per-symbol
#       402) → NO immediate Telegram. Escalates to a Telegram ONLY when
#       SUSTAINED: ≥ _SUSTAINED_COUNT same-(provider,class) failures within the
#       6h window AND spanning ≥ _SUSTAINED_MIN_SPREAD_S (a tight burst inside
#       one fetch loop is one blip; failures persisting across scan cycles are
#       a real outage and MUST still page — that's the whole point).
#   BROKER CARVE-OUT: provider "alpaca" is real-money-critical — NOTHING is
#     demoted; every classified alpaca failure keeps the immediate Telegram.
_TRANSIENT_CLASSES = frozenset({"timeout", "connect", "transport"})
_TRANSIENT_HTTP_STATUS = frozenset({402})  # per-symbol plan-gate (FMP), fail-open
_SUSTAINED_COUNT = 3            # current failure + ≥2 prior rows in the window
_SUSTAINED_MIN_SPREAD_S = 30 * 60  # failures must SPAN ≥30 min (≈6+ scan cycles)
_SUSTAINED_LOOKBACK_LIMIT = 50  # rows fetched for the sustained/dedup lookback

_SUMMARY_CLASS_RE = re.compile(r"class=([a-z0-9_]+)")
_SUMMARY_CODE_RE = re.compile(r"HTTP (\d{3})")


def is_transient_api_failure(provider: str, cls: str | None, code: int | None) -> bool:
    """True when a classified data-API failure is TRANSIENT/self-healing (audit
    row only, no immediate Telegram). Broker (alpaca) failures are NEVER
    transient — real-money domain, everything stays immediately loud."""
    try:
        if provider == "alpaca":
            return False
        if cls in _TRANSIENT_CLASSES:
            return True
        if cls == "http_4xx" and code in _TRANSIENT_HTTP_STATUS:
            return True
        return False
    except Exception:  # loud-ok: pure classifier; "not transient" (= alert) is the safe default
        return False


def is_transient_api_failure_row(row: dict) -> bool:
    """Classify an `api_failure_<provider>` mi_audit_log row as transient from
    its summary markers (`class=<cls>`, optional `HTTP <code>`). Used by the
    morning-brief banner to render self-healing blips as one quiet line instead
    of per-row 🔴 entries. Unparseable rows → False (stay loud)."""
    try:
        event_type = str(row.get("event_type") or "")
        if not event_type.startswith("api_failure_"):
            return False
        provider = event_type[len("api_failure_"):]
        summary = str(row.get("summary") or "")
        m = _SUMMARY_CLASS_RE.search(summary)
        cls = m.group(1) if m else None
        mc = _SUMMARY_CODE_RE.search(summary)
        code = int(mc.group(1)) if mc else None
        return is_transient_api_failure(provider, cls, code)
    except Exception:  # loud-ok: parser over an arbitrary row; loud is the safe default
        return False


async def alert_api_failure(provider: str, exc: BaseException,
                            context: str = "") -> None:
    """Audit-always + triaged operator alert that a DATA API (Polygon/FMP/
    Perplexity) or the broker (Alpaca) is failing. ALWAYS safe to call from a
    fail-open/except block — never raises.

    Caller contract: call this at the wrapper's catch point, THEN let the
    wrapper propagate as it already does (re-raise or return its fallback). This
    function only ALERTS — it never re-raises, never swallows the caller's flow.

    Behavior (Fix-1, 2026-07-14 — see the triage block above):
      1. The `api_failure_<provider>` AUDIT ROW is written for EVERY classified
         failure (summary carries `class=<cls>` + ` tg=<0|1>`).
      2. The TELEGRAM is gated: actionable classes fire immediately (deduped
         per (provider,class) per ~6h via tg=1 rows — legacy rows without a
         tg marker predate the split and were alert-carrying, so they count);
         transient classes fire only when SUSTAINED (count + time-spread).
      3. The in-process pre-gate collapses a same-process stampede of TELEGRAM
         decisions only — it never suppresses the audit row.
    """
    try:
        cls = classify_api_failure(exc)
        if cls is None:
            return  # not a network/HTTP failure — don't cry wolf on a code bug

        provider = provider if provider in _API_PROVIDERS else "other"
        event_type = f"api_failure_{provider}"
        key = (provider, cls)
        now = time.monotonic()
        code = _status_code(exc)
        transient = is_transient_api_failure(provider, cls, code)

        # ── Telegram decision (the audit row below is written EITHER WAY) ──
        send_telegram = False
        last = _last_api_alert_ts.get(key)
        pregate_open = last is None or (now - last) >= _ALERT_WINDOW_S
        if pregate_open:
            already_alerted = False
            lookback_ok = False
            same_cls_rows: list[dict] = []
            try:
                from agents.market_intelligence.db import get_audit_log
                recent = await get_audit_log(
                    event_type=event_type, since_hours=_ALERT_WINDOW_HOURS,
                    limit=_SUSTAINED_LOOKBACK_LIMIT,
                )
                lookback_ok = True
                for row in (recent or []):
                    summary = row.get("summary") or ""
                    if f"class={cls}" not in summary:
                        continue
                    same_cls_rows.append(row)
                    # tg=1 = row that carried a Telegram; legacy rows (no tg=
                    # marker, pre-split format) were only written when a
                    # Telegram fired → also count as alerted.
                    if "tg=1" in summary or "tg=" not in summary:
                        already_alerted = True
            except Exception as e:
                # DB unavailable — for ACTIONABLE classes fall through and alert
                # (better a possible dup than a silently-swallowed API outage,
                # the whole bug class #380/#370). TRANSIENT classes stay quiet:
                # sustained-detection needs the DB, and a self-healing blip must
                # not page just because the lookback flaked.
                logger.warning("alert_api_failure dedup lookback failed for %s/%s "
                                "(actionable falls through to alert): %s",
                                provider, cls, e)

            if not transient:
                send_telegram = not already_alerted
            else:
                sustained = False
                if lookback_ok and len(same_cls_rows) + 1 >= _SUSTAINED_COUNT:
                    times = []
                    for row in same_cls_rows:
                        ts = row.get("created_at")
                        if isinstance(ts, datetime):
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                            times.append(ts)
                    if times:
                        spread_s = (datetime.now(timezone.utc) - min(times)).total_seconds()
                        sustained = spread_s >= _SUSTAINED_MIN_SPREAD_S
                send_telegram = sustained and not already_alerted

            if already_alerted:
                _last_api_alert_ts[key] = now  # keep the pre-gate honest

        if send_telegram:
            # Claim the window in-process before any await that could interleave.
            _last_api_alert_ts[key] = now

        code_str = f" HTTP {code}" if code is not None else ""
        label = provider.upper()
        copy = _ALARM_COPY_BY_CLASS[_PROVIDER_CLASS.get(provider, "data")]
        kind = copy["kind"]
        consequence = copy["consequence"]

        # Audit row FIRST, ALWAYS (durable record + queryable; visible to the
        # morning banner / `show errors` / sweeps even when no Telegram fires).
        # `class=<cls>` + ` tg=<0|1>` markers are load-bearing — the lookback
        # above matches on them.
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                event_type,
                f"{label} API FAILURE class={cls}{code_str} tg={1 if send_telegram else 0}"
                + (f" — {context}" if context else ""),
                str(exc)[:400],
            )
        except Exception as e:
            logger.warning("alert_api_failure audit-row write failed for %s/%s: %s",
                            provider, cls, e)

        if not send_telegram:
            return  # transient blip / already-alerted window — audit-only

        # Then the operator Telegram — a source going dark IS actionable.
        # Consequence copy is provider-CLASS-specific (#406): a data source
        # going dark degrades the grade/universe/news corpus; the broker
        # (alpaca) going dark degrades position sync / trade state instead —
        # a different domain, so the alert must say so. A transient class that
        # escalated is labeled SUSTAINED so the operator knows this is not a
        # single blip but a failure persisting across scan cycles.
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            from shared.telegram_format import b, esc
            sustained_tag = "SUSTAINED " if transient else ""
            await send_telegram_message(
                f"⚠️ {b(f'{label} {kind} FAILURE')} ({sustained_tag}{esc(cls)}{esc(code_str)})"
                + (f" in {esc(context)}" if context else "")
                + ".\n"
                + f"The {esc(label)} fetch is failing — {consequence} is "
                + "silently degrading until it recovers.\n"
                + "Check the provider status + our API key/plan, then verify the "
                + "next scan's data.",
                parse_mode="HTML",
            )
        except Exception as e:
            # Last step, nothing above can handle it further — the audit row (if
            # it landed) is still the durable record even if this send failed.
            logger.warning("alert_api_failure Telegram send failed for %s/%s: %s",
                            provider, cls, e)
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
