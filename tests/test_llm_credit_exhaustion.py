"""#273 — LLM credit/quota-exhaustion alerting.

The make-or-break property: the classifier must distinguish a CREDIT-EXHAUSTION
failure (terminal — refill needed) from a transient RATE-LIMIT (429, self-heals
on retry, already handled elsewhere). Confusing the two would either spam the
operator on every 429 or silently swallow a real outage.

Covers:
  (1) credit exhaustion (Anthropic 400 credit-balance + 403 billing + Perplexity
      402/401) → is_credit_error True, and alert_credit_exhausted fires the
      audit row + Telegram.
  (2) a transient 429 rate-limit → is_credit_error False (NO credit-alert).
  (3) a generic non-credit Anthropic 400 → is_credit_error False (the classifier
      does NOT widen to all 400s).
  (4) dedup: a second exhaustion within the 6h window does NOT re-alert (audit-
      log lookback is the durable dedup token; container-restart-proof).
"""
from __future__ import annotations

import httpx
import pytest

from agents.market_intelligence import llm_health


# ── exception fixtures ──
#
# NOTE: `anthropic` is stubbed to a MagicMock in tests (tests/conftest.py), and
# the production classifier is built to NOT depend on the real SDK exception
# CLASSES — it reads DUCK-TYPED attributes (`status_code`, `.type`, message) so
# it survives the stubbed-SDK env (the `_real_types()` pattern, theme_engine.py
# #246). These fakes mirror the live SDK's exception SHAPE exactly — the same
# attributes `is_credit_error` reads at runtime — which is the faithful contract
# under test. (Verified out-of-band against real anthropic 0.84.0:
# BadRequestError/PermissionDeniedError/RateLimitError expose `.status_code`
# from the response, `str(e)` is the message, `.type` is the API error type.)

_REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


class _FakeAnthropicError(Exception):
    """Mimics an anthropic.APIStatusError: `.status_code`, `.type`, str = message."""

    def __init__(self, message: str, status_code: int, err_type: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.type = err_type
        # An APIStatusError also carries a `.response`; some code reads
        # response.status_code — populate it so the fallback path is exercised.
        self.response = httpx.Response(status_code, request=_REQ)


class RateLimitError(_FakeAnthropicError):
    """Named exactly `RateLimitError` on purpose: the classifier's defensive
    fallback checks type(exc).__name__ == 'RateLimitError' for stubbed/proxied
    SDKs that don't expose a usable status_code."""


# Real Anthropic credit error: 400 whose .type is "invalid_request_error" (SAME
# as a malformed request) — so the credit MESSAGE marker is what classifies it.
def anthropic_credit_400():
    return _FakeAnthropicError(
        "Your credit balance is too low to access the Anthropic API. Please go "
        "to Plans & Billing to upgrade or purchase credits.",
        status_code=400, err_type="invalid_request_error",
    )


def anthropic_billing_403():
    # The clean typed signal: .type == "billing_error" (403).
    return _FakeAnthropicError(
        "Your account has a billing issue; access is restricted.",
        status_code=403, err_type="billing_error",
    )


def anthropic_rate_limit_429():
    return RateLimitError(
        "Number of requests has exceeded your rate limit.",
        status_code=429, err_type="rate_limit_error",
    )


class _NameOnlyRateLimit(Exception):
    """A rate-limit-shaped exc whose class is named RateLimitError but exposes
    NO status_code (the stubbed/proxied-SDK case). Renamed at construction so the
    name-fallback in the classifier is what must catch it."""


_NameOnlyRateLimit.__name__ = "RateLimitError"


def anthropic_generic_400():
    # A normal malformed-request 400 — NOT exhaustion (no credit marker, and
    # .type is invalid_request_error not billing_error).
    return _FakeAnthropicError(
        "messages: roles must alternate between 'user' and 'assistant'.",
        status_code=400, err_type="invalid_request_error",
    )


def perplexity_402():
    # Perplexity raises httpx.HTTPStatusError from raise_for_status(); str(exc)
    # contains NO credit words, so classification must go by status code.
    resp = httpx.Response(402, request=_REQ)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e


def perplexity_401():
    resp = httpx.Response(401, request=_REQ)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e


# ── classifier: exhaustion vs rate-limit (the make-or-break distinction) ──

def test_classifier_recognizes_anthropic_credit_exhaustion():
    assert llm_health.is_credit_error(anthropic_credit_400()) is True
    assert llm_health.is_credit_error(anthropic_billing_403()) is True


def test_classifier_recognizes_perplexity_quota_exhaustion():
    assert llm_health.is_credit_error(perplexity_402()) is True
    assert llm_health.is_credit_error(perplexity_401()) is True


def test_classifier_does_not_flag_transient_rate_limit():
    # THE critical test: a 429 must NEVER be classified as credit exhaustion.
    e = anthropic_rate_limit_429()
    assert e.status_code == 429                     # sanity: it really is a 429
    assert type(e).__name__ == "RateLimitError"
    assert llm_health.is_credit_error(e) is False


def test_classifier_excludes_rate_limit_by_class_name_without_status():
    # Stubbed/proxied SDK: no usable status_code, but the class is RateLimitError.
    # The name-based fallback must still exclude it.
    e = _NameOnlyRateLimit("rate limited")
    assert getattr(e, "status_code", None) is None
    assert type(e).__name__ == "RateLimitError"
    assert llm_health.is_credit_error(e) is False


def test_classifier_does_not_widen_to_all_400s():
    # A generic malformed-request 400 is NOT exhaustion (no credit marker).
    assert llm_health.is_credit_error(anthropic_generic_400()) is False


def test_classifier_never_raises_on_arbitrary_exception():
    # Must be safe to call from any fail-open except block.
    assert llm_health.is_credit_error(ValueError("nope")) is False
    assert llm_health.is_credit_error(TimeoutError()) is False


# ── alert path: audit row + Telegram, with dedup ──

@pytest.fixture(autouse=True)
def _reset_pregate(monkeypatch):
    # Clear the in-process pre-gate so each test starts clean.
    monkeypatch.setattr(llm_health, "_last_alert_ts", {})


class _DBStub:
    """Stands in for db.get_audit_log + db.log_audit_event. `existing` controls
    what the dedup lookback returns; `written` records audit rows."""

    def __init__(self, existing=None):
        self.existing = existing or []
        self.written: list[tuple] = []

    async def get_audit_log(self, *, event_type=None, since_hours=None, limit=None):
        # Return a pre-existing row only when the queried event_type matches.
        return [r for r in self.existing if r.get("event_type") == event_type][:limit or 1]

    async def log_audit_event(self, event_type, summary, detail=""):
        self.written.append((event_type, summary, detail))


def _patch_db_and_telegram(monkeypatch, db):
    import agents.market_intelligence.db as db_mod
    monkeypatch.setattr(db_mod, "get_audit_log", db.get_audit_log)
    monkeypatch.setattr(db_mod, "log_audit_event", db.log_audit_event)

    sent: list[str] = []

    async def fake_send(msg, parse_mode=None):
        sent.append(msg)
        return True

    import agents.market_intelligence.briefing as briefing_mod
    monkeypatch.setattr(briefing_mod, "send_telegram_message", fake_send)
    return sent


@pytest.mark.asyncio
async def test_exhaustion_fires_audit_and_telegram(monkeypatch):
    db = _DBStub(existing=[])            # no prior alert in the window
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_credit_exhausted("catalyst grader", anthropic_credit_400())

    assert len(db.written) == 1
    assert db.written[0][0] == "anthropic_credits_exhausted"
    assert len(sent) == 1
    assert "CREDITS" in sent[0] and "AUTH" in sent[0]
    assert "catalyst grader" in sent[0]


@pytest.mark.asyncio
async def test_perplexity_exhaustion_uses_provider_event(monkeypatch):
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_credit_exhausted(
        "Perplexity news search", perplexity_402(), provider="perplexity")

    assert db.written[0][0] == "perplexity_credits_exhausted"
    assert len(sent) == 1
    assert "PERPLEXITY" in sent[0].upper()


@pytest.mark.asyncio
async def test_dedup_suppresses_second_alert_in_window(monkeypatch):
    # A prior row exists within the 6h window → suppress BOTH row and Telegram.
    db = _DBStub(existing=[{"event_type": "anthropic_credits_exhausted"}])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_credit_exhausted("judge", anthropic_credit_400())

    assert db.written == []              # no new audit row
    assert sent == []                   # no Telegram


@pytest.mark.asyncio
async def test_dedup_is_per_provider(monkeypatch):
    # An anthropic row in the window must NOT suppress a perplexity alert.
    db = _DBStub(existing=[{"event_type": "anthropic_credits_exhausted"}])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_credit_exhausted(
        "Perplexity news search", perplexity_402(), provider="perplexity")

    assert db.written[0][0] == "perplexity_credits_exhausted"
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_inproc_pregate_suppresses_same_process_burst(monkeypatch):
    # Even with an empty DB lookback, a second call in the same process within
    # the window is collapsed by the in-process pre-gate (stampede guard).
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_credit_exhausted("grader", anthropic_credit_400())
    await llm_health.alert_credit_exhausted("grader", anthropic_credit_400())

    assert len(sent) == 1               # only the first burst member alerts
    assert len(db.written) == 1
