"""#679 (2026-09-21) — a Perplexity blip must not page the operator, and must never be
recorded as the factual verdict "no catalysts found".

TWO DEFECTS, ONE MORNING. The operator got a Telegram reading "PERPLEXITY DATA-API FAILURE
(http_4xx HTTP 429) ... Check the provider status + our API key/plan". Every clause after the
status code was wrong:

  1. IT WAS NOT OUR KEY OR OUR PLAN. The body we had already captured into the audit row read
     {"error":{"message":"upstream model is overloaded","type":"overloaded","code":429}} —
     provider-side capacity. 22 of 25 calls that morning returned 200.

  2. IT ONLY PAGED BECAUSE ONE CALL SITE HAD NO RETRY. `collector.search_news_perplexity` has
     had a bounded 429 retry since 2026-08-12; `ep_detector._validate_catalyst_perplexity`
     had none. At 08:15:07 ET the news path took a 429, waited 6.4s and succeeded; 1.3s later
     the catalyst path took the same 429 and hard-failed. `llm_health` classifies 429 as
     ACTIONABLE on the stated ground "429-after-retries" — which was false here.

  3. THE ONE THAT COST SOMETHING. `search_news_perplexity` swallows every exception and
     returns "", so `theme_engine._news_check`'s `except` arm — which returns api_err=True so
     the caller can substitute a neutral news score of 15 instead of 0, its comment reading
     "don't penalize the theme with score=0" — had NEVER ONCE EXECUTED for a provider failure.
     An outage was scored as a fact. On 2026-09-04 four themes were capped Mainstream ->
     Nascent 17-27ms after their own Perplexity failure row, and
     `ep_theme_belonging.THEME_BONUS_STAGES` is ("Accelerating", "Mainstream") — so every
     member ticker lost the EP theme-belonging bonus because a news API timed out.

⚠ WHAT IS **NOT** CLAIMED, because the adversarial pass caught the overclaim: a zero news
score is NOT a reliable marker of an outage. `_is_garbage(answer)` returns the byte-identical
`(0, "", False)` from a SUCCESSFUL call whose answer said there is no news, and 2026-07-21 is a
zero-news theme row on a day with no provider failure at all. Outage and genuine-no-news were
indistinguishable in the DB; that indistinguishability is what this fix removes going forward,
and it does NOT retroactively reinterpret history.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import httpx
import pytest

import agents.market_intelligence.collector as collector
from agents.market_intelligence import ep_detector, llm_health

_REQ = httpx.Request("POST", "https://api.perplexity.ai/v1/agent")

# Captured BEFORE the autouse fixture stubs it out, so the assembled-message test can exercise
# the real thing. (The first draft asserted on a message the stub never sent — len(sent)==0.)
_REAL_ALERT_API_FAILURE = llm_health.alert_api_failure


def _status_error(code: int, body: str = "", headers: dict | None = None) -> httpx.HTTPStatusError:
    resp = httpx.Response(code, headers=headers or {}, text=body, request=_REQ)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e
    raise AssertionError("expected raise_for_status to raise")


class _GradeResp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"status": "completed",
                "output": [{"type": "message",
                            "content": [{"type": "output_text", "text": "STRONG"}]}],
                "usage": {}}


def _install(monkeypatch, _module, behaviors: list) -> list:
    """Patch `httpx.AsyncClient` on the REAL httpx module.

    ⚠ `ep_detector._validate_catalyst_perplexity` does `import httpx` INSIDE the function
    (ep_detector.py:1429), so `monkeypatch.setattr(ep_detector, "httpx", ...)` never takes —
    the function re-imports the genuine module on every call and the stub is silently ignored.
    Patching the module object itself covers both call sites, since `collector.httpx` is the
    same object. The first draft of this file patched the attribute and the retry tests failed
    with AttributeError, which is the honest failure; a subtler variant would have passed while
    testing nothing."""
    calls: list[int] = []

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            b = behaviors[min(len(calls), len(behaviors) - 1)]
            calls.append(1)
            if isinstance(b, Exception):
                raise b
            return b

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())
    return calls


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    collector._PPLX_CACHE.clear()
    import agents.market_intelligence.spend_tracker as spend_tracker

    async def _noop(**kw): return None
    monkeypatch.setattr(spend_tracker, "log_perplexity_call", _noop)

    async def _no_sleep(_s): return None
    monkeypatch.setattr(collector.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(ep_detector.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(collector.random, "uniform", lambda a, b: 1.0)

    async def _quiet(*a, **k): return None
    monkeypatch.setattr(llm_health, "alert_api_failure", _quiet)
    monkeypatch.setattr(llm_health, "alert_credit_exhausted", _quiet, raising=False)
    # ⚠ THE CLOCK IS AN INPUT TO THIS FILE NOW (2026-09-21 simplify review). The retry is
    # SUPPRESSED inside the 9:30-9:45 ET ORB-submission window, so every retry test above
    # would flip RED for 15 minutes each weekday morning if it ran on the wall clock. Pinned
    # pre-market by default — which is also where the 08:15 failure that motivated #679 landed.
    _pin_clock(monkeypatch, 8, 15)


def _pin_clock(monkeypatch, hour: int, minute: int) -> None:
    """Freeze `ep_detector`'s view of ET wall-clock time. It reads it as `datetime.now(_ET)`
    against the module-level `from datetime import datetime`, so the class is what we replace."""
    from datetime import datetime as _dt
    _fixed = _dt(2026, 9, 21, hour, minute, tzinfo=ZoneInfo("America/New_York"))

    class _Clock(_dt):
        @classmethod
        def now(cls, tz=None):
            return _fixed if tz is None else _fixed.astimezone(tz)

    monkeypatch.setattr(ep_detector, "datetime", _Clock)


# ── (1) the retry that was missing ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_catalyst_grader_retries_a_429_and_recovers(monkeypatch):
    """The exact 2026-09-21 08:15 ET shape: one 429, then a normal answer. Before #679 this
    returned None on the first 429 and paged the operator."""
    calls = _install(monkeypatch, ep_detector,
                     [_status_error(429, '{"error":{"message":"upstream model is overloaded",'
                                         '"type":"overloaded","code":429}}'), _GradeResp()])
    out = await ep_detector._validate_catalyst_perplexity("ARHS", "Beat and raised guidance.")
    assert len(calls) == 2, f"no retry happened — the call site is single-attempt again ({len(calls)} call)"
    assert out == "strong", f"the recovered answer was dropped: {out!r}"


@pytest.mark.asyncio
async def test_the_retry_is_bounded_at_one(monkeypatch):
    """A retry loop with no bound is its own outage. Two 429s in a row must give up, not spin."""
    calls = _install(monkeypatch, ep_detector, [_status_error(429), _status_error(429)])
    out = await ep_detector._validate_catalyst_perplexity("ARHS", "Beat and raised guidance.")
    assert len(calls) == 2, f"expected exactly 2 attempts, got {len(calls)}"
    assert out is None


@pytest.mark.asyncio
async def test_a_non_429_is_not_retried(monkeypatch):
    """Only 429 earns the second attempt — a 500 or a 401 must fail fast, as before #679."""
    for code in (500, 401):
        collector._PPLX_CACHE.clear()
        calls = _install(monkeypatch, ep_detector, [_status_error(code), _GradeResp()])
        out = await ep_detector._validate_catalyst_perplexity("ARHS", "Beat and raised.")
        assert len(calls) == 1, f"HTTP {code} was retried; only 429 should be ({len(calls)} calls)"
        assert out is None


# ── (2) the guard that could never fire ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_provider_failure_now_reaches_the_theme_engines_own_guard(monkeypatch):
    """THE ONE THAT COST SOMETHING. `_news_check` must report api_err=True on a provider
    failure so the caller substitutes the neutral 15 its own comment promises. Before #679 the
    exception was swallowed in the collector and this returned (0, "", False) — scored as a
    factual 'no catalysts found'."""
    from agents.market_intelligence import theme_engine
    _install(monkeypatch, collector, [_status_error(500), _status_error(500)])
    news_score, desc, api_err = await theme_engine._news_check("Some Theme", ["AAA", "BBB"])
    assert api_err is True, (
        "a provider failure still reads as api_err=False, so the caller scores it 0 and the "
        "neutral-15 guard stays unreachable — exactly the 2026-09-04 defect."
    )
    assert news_score == 0 and desc == ""   # the caller is what substitutes 15


@pytest.mark.asyncio
async def test_a_genuine_empty_answer_is_still_a_real_zero(monkeypatch):
    """The other direction, so the fix above cannot be satisfied by calling everything an
    outage: a 200 that yields no text is a real finding, not a failure."""
    from agents.market_intelligence import theme_engine

    class _Empty(_GradeResp):
        def json(self): return {"status": "completed", "output": [], "usage": {}}

    _install(monkeypatch, collector, [_Empty()])
    news_score, desc, api_err = await theme_engine._news_check("Some Theme", ["AAA"])
    assert api_err is False, "a successful empty answer was misread as a provider outage"
    assert news_score == 0 and desc == ""


@pytest.mark.asyncio
async def test_every_other_caller_keeps_the_fail_open_contract(monkeypatch):
    """~12 production callers rely on `search_news_perplexity` returning "" rather than
    raising. The opt-in must not change them."""
    _install(monkeypatch, collector, [_status_error(500), _status_error(500)])
    assert await collector.search_news_perplexity("q", recency="week") == ""


# ── (3) the alert that guessed over the answer it already had ─────────────────────────────

def test_the_alert_quotes_the_provider_instead_of_blaming_our_key():
    said = llm_health.provider_said(_status_error(
        429, '{"error":{"message":"upstream model is overloaded","type":"overloaded","code":429}}'))
    assert said == ("upstream model is overloaded", "overloaded"), said


@pytest.mark.asyncio
async def test_the_ASSEMBLED_telegram_carries_the_body_and_asserts_nothing_past_it(monkeypatch):
    """⚠ The unit above only exercises `provider_said()`. This reads the message the operator
    actually receives — the surface that was wrong on 2026-09-21.

    It also pins the SECOND overclaim, caught in review before it shipped: a first draft
    appended "that is the provider's own words — not our key or plan". A 403
    `permission_error` reaches this same path, so that caption would have denied a key problem
    while the provider was reporting one. Quote and stop."""
    from tests.test_api_failure_guard import _DBStub, _patch_db_and_telegram
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)
    monkeypatch.setattr(llm_health, "alert_api_failure", _REAL_ALERT_API_FAILURE)
    await llm_health.alert_api_failure("perplexity", _status_error(
        429, '{"error":{"message":"upstream model is overloaded","type":"overloaded","code":429}}'))
    assert len(sent) == 1
    msg = sent[0]
    assert "upstream model is overloaded" in msg, f"the body we captured never reached him: {msg}"
    assert "api key" not in msg.lower() and "key/plan" not in msg.lower(), (
        f"still telling him to check our key over a provider-capacity 429: {msg}")
    assert "not our key" not in msg.lower(), (
        f"the caption asserts past the body — a 403 permission_error takes this same path: {msg}")


def test_an_unparseable_body_costs_the_operator_nothing():
    """Best-effort by construction: the alert itself is the durable signal and must survive a
    body that is HTML, truncated, or absent."""
    for body in ("", "<html>502 Bad Gateway</html>", '{"nope":', '{"error":"a string"}'):
        assert llm_health.provider_said(_status_error(500, body)) is None, body


# ── (4) the ORB-window latency guard (2026-09-21 simplify review) ─────────────────────────
#
# The retry #679 added is correct everywhere EXCEPT 9:30-9:45 ET. `_validate_catalyst_perplexity`
# is awaited inside the sequential `for c in candidates[:SHORTLIST_SIZE]` grading loop, so one
# 429 costs up to 7.5s of sleep PLUS a second 15s attempt — on a path where this file's own
# precedent (advisor 6/28, the prior-year YoY fetch) already forbids a 4s fetch, because
# "a few x 4s serially could push the scan past 9:45 -> WINDOW_OUT_OF_ORB on the GOOD names
# that needed to submit." MEASURED: 38 catalyst validations ran inside that window over the
# 60 days to 2026-09-21, so it is a real population, not a hypothetical one.


@pytest.mark.asyncio
async def test_inside_the_orb_window_a_429_is_not_retried(monkeypatch):
    """The latency half. In-window we take ONE attempt — byte-identical to pre-#679."""
    _pin_clock(monkeypatch, 9, 35)
    calls = _install(monkeypatch, ep_detector, [_status_error(429), _GradeResp()])
    out = await ep_detector._validate_catalyst_perplexity("ARHS", "Beat and raised guidance.")
    assert len(calls) == 1, (
        f"the retry ran inside the 9:30-9:45 ORB window ({len(calls)} attempts). Worst case it "
        f"adds ~22.5s to a call awaited inside the sequential grading loop, which is exactly "
        f"what pushes a good name past 9:45 into WINDOW_OUT_OF_ORB."
    )
    assert out is None


@pytest.mark.asyncio
async def test_an_in_window_429_STILL_ALERTS_instead_of_vanishing(monkeypatch):
    """⚠ THE BUG THE GUARD ALMOST INTRODUCED, and the reason this test exists. The retry arm
    read `if _attempt == 1 and _wait is not None: continue`. With the window guard making
    `_attempts` the single-element `(1,)`, an in-window 429 satisfied `== 1`, hit `continue`,
    fell off the end of the loop and returned None having alerted NOBODY — strictly worse than
    the pre-#679 behaviour the guard was written to restore. Suppressing a RETRY must never
    suppress the TRIAGE. Reinstating `== 1` turns this red."""
    _pin_clock(monkeypatch, 9, 35)
    seen: list = []

    async def _capture(exc, **kw):
        seen.append(exc)

    monkeypatch.setattr(llm_health, "triage_perplexity_exception", _capture, raising=False)
    _install(monkeypatch, ep_detector, [_status_error(429), _GradeResp()])
    out = await ep_detector._validate_catalyst_perplexity("ARHS", "Beat and raised guidance.")
    assert out is None
    assert len(seen) == 1, (
        "an in-window 429 was swallowed silently — no triage, no alert. The retry is suppressed "
        "in the ORB window for LATENCY; the failure still has to be reported."
    )


@pytest.mark.asyncio
async def test_the_window_is_the_orb_window_and_not_all_morning(monkeypatch):
    """The boundary, exercised rather than read off the source. 9:29 and 9:46 retry; 9:30 and
    9:45 do not — the guard must not quietly become "no retries before 10am"."""
    for hh, mm, want in ((9, 29, 2), (9, 30, 1), (9, 45, 1), (9, 46, 2), (8, 15, 2), (15, 0, 2)):
        _pin_clock(monkeypatch, hh, mm)
        calls = _install(monkeypatch, ep_detector, [_status_error(429), _GradeResp()])
        await ep_detector._validate_catalyst_perplexity("ARHS", "Beat and raised guidance.")
        assert len(calls) == want, f"at {hh:02d}:{mm:02d} ET expected {want} attempt(s), got {len(calls)}"


@pytest.mark.asyncio
async def test_the_retry_reads_the_SHARED_orb_predicate_not_its_own_copy(monkeypatch):
    """One definition of the 9:30-9:45 boundary, proved by BEHAVIOUR rather than by grepping the
    source. `_in_orb_cutoff` was a bare local beside the prior-year YoY fetch until this retry
    became its second caller, and two copies of a money-path latency boundary is the drift this
    repo keeps paying for. Redirecting the shared predicate must move THIS call site: re-inline a
    private copy here and the patch stops reaching it, so the retry runs and this goes red."""
    _pin_clock(monkeypatch, 8, 15)                      # pre-market: the retry WOULD run
    monkeypatch.setattr(ep_detector, "_in_orb_cutoff", lambda _now: True)
    calls = _install(monkeypatch, ep_detector, [_status_error(429), _GradeResp()])
    await ep_detector._validate_catalyst_perplexity("ARHS", "Beat and raised guidance.")
    assert len(calls) == 1, (
        "redirecting the shared `_in_orb_cutoff` did not change this call site — it is reading a "
        "second, private copy of the ORB-window rule."
    )
