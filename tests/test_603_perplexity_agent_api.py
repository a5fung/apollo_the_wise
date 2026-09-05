"""#603 — the Perplexity migration, and the future-proofing the operator asked for.

Perplexity sunsets /chat/completions on 2026-09-27 ("Sonar Chat Completions is now Agent API.
Sonar will be supported until September 27, 2026"). Our calls fail OPEN, so the lapse would
have been silent: the catalyst second opinion (#233) and the brief's overnight section would
simply stop appearing, with no exception and no alert.

Operator, 2026-08-27: "Let's make sure when we migrate we make it future proof, auto updates
without needing to manual update or hardcode anywhere."

That is satisfied STRUCTURALLY, not by discipline: the Agent API takes a PRESET (a capability
tier) instead of a model name and routes to whatever model currently serves it — the probe
that day came back on `openai/gpt-5.6-luna` without us naming anything — and it REPORTS its own
actual cost, so the local rate table stops being load-bearing too. Both are hand-maintained
values that can no longer rot, because they no longer exist.
"""
import io
import json as _json

import httpx
import pytest

from agents.market_intelligence import collector, llm_health
from agents.market_intelligence.audit_events import PERPLEXITY_ENDPOINT_ERROR
from agents.market_intelligence.collector import _pplx_answer_text

_COLLECTOR_SRC = io.open("agents/market_intelligence/collector.py", encoding="utf-8").read()
_SPEND_SRC = io.open("agents/market_intelligence/spend_tracker.py", encoding="utf-8").read()


# ── nothing is hardcoded any more ────────────────────────────────────────────────────────
def test_no_model_string_is_hardcoded_anywhere_in_the_perplexity_path():
    """The old code pinned "sonar-pro" as a raw literal at four call sites, where
    preflight_model_registry could not see it — the exact rot the 2026-07-30 model-pinning
    ruling forbids. A preset is a capability tier, not a model, so there is nothing to update
    when Perplexity changes what serves it."""
    for line in _COLLECTOR_SRC.splitlines():
        if '"sonar' in line or "'sonar" in line:
            assert line.strip().startswith("#"), f"model literal is back: {line.strip()[:90]}"
    assert collector._PPLX_PRESET in ("fast", "low", "medium", "high", "xhigh")


def test_the_sunset_endpoint_is_gone():
    for line in _COLLECTOR_SRC.splitlines():
        if "chat/completions" in line:
            assert line.strip().startswith("#"), f"sunset endpoint still called: {line.strip()}"
    assert collector._PPLX_AGENT_URL == "https://api.perplexity.ai/v1/agent"


def test_the_cost_meter_prefers_the_cost_the_api_reports():
    """The rate table was the OTHER hand-maintained value. The Agent API returns
    usage.cost.total_cost, so the row records what was actually charged."""
    assert "total_cost" in _SPEND_SRC
    assert "_reported is not None" in _SPEND_SRC


# ── the response parser ──────────────────────────────────────────────────────────────────
def _agent(text, lead_search_items=2):
    out = [{"type": "search_results", "results": []} for _ in range(lead_search_items)]
    out.append({"type": "message", "content": [{"type": "output_text", "text": text}]})
    return {"status": "completed", "output": out}


@pytest.mark.parametrize("lead", [0, 1, 2, 5])
def test_the_answer_is_found_by_type_at_any_position(lead):
    """⚠ THE LATENT BUG THIS PREVENTS: the two 2026-08-27 probes returned the message at
    index 1 and index 2. An index-based parser would blank intermittently — and because the
    caller fails open on "", it would blank SILENTLY."""
    assert _pplx_answer_text(_agent("the answer", lead)) == "the answer"


@pytest.mark.parametrize("bad", [
    None, {}, {"output": None}, {"output": []},
    {"output": [{"type": "search_results", "results": []}]},          # no message at all
    {"output": [{"type": "message", "content": []}]},                  # message, no content
    {"output": [{"type": "message", "content": [{"type": "output_text"}]}]},  # no text
    {"output": "not-a-list"},
    {"choices": [{"message": {"content": "legacy shape"}}]},           # the OLD shape
])
def test_every_shape_surprise_degrades_to_empty_rather_than_raising(bad):
    """The caller's contract is fail-open. A shape change must return "" — never raise into
    a scan tick."""
    assert _pplx_answer_text(bad) == ""


def test_a_blank_answer_is_never_cached():
    """Pre-existing behaviour that the migration must not lose: caching "" would serve the
    failure for the whole 15-minute TTL."""
    assert "if _answer:" in _COLLECTOR_SRC
    assert "_pplx_cache_put(_ck, _answer)" in _COLLECTOR_SRC


# ── the request keeps the behaviour the callers depend on ────────────────────────────────
def test_recency_still_reaches_the_search_and_the_system_prompt_survives():
    """`recency` moved into the web_search tool config and the system prompt became
    `instructions`. Both must still be sent, or every caller silently loses its time window.

    2026-09-04: `search_recency_filter` must be NESTED under a `filters` sub-object on the
    tool, not a direct sibling of `type` — the flat placement does not match Perplexity's
    documented web_search tool schema (docs.perplexity.ai/docs/agent-api/tools/web-search
    #filters, confirmed against 3 separate doc pages). Whether this specific defect is what
    produced the day's live HTTP 400s is UNCONFIRMED (the flat shape ran for 8 days without
    erroring and the failing calls' bodies weren't captured) — this fix ships on contract
    conformance regardless. This is still a source-text pin (see the structural test below
    for the real guard), but it must pin the DOCUMENTED shape, not the flat one."""
    assert '"filters": {"search_recency_filter": recency}' in _COLLECTOR_SRC
    assert '"search_recency_filter": recency}]' not in _COLLECTOR_SRC, \
        "search_recency_filter is back as a flat sibling of type, contradicting the documented schema"
    assert '"instructions": system_prompt or _PERPLEXITY_SYSTEM_DEFAULT' in _COLLECTOR_SRC
    assert '"input": query' in _COLLECTOR_SRC


@pytest.mark.asyncio
async def test_the_actual_wire_body_has_recency_nested_under_filters(monkeypatch):
    """2026-09-04: a source-text grep for `'"search_recency_filter": recency'` (the test
    above, pre-fix) is satisfied by EITHER the correct nested shape or the broken flat one —
    it only checks the value survives, never WHERE it lands. The flat shape shipped on
    2026-08-27 and ran for 8 days without erroring (real cost rows, 200s) before 3 live
    `api_failure_perplexity` http_4xx rows appeared on 2026-09-04 — whether this exact shape
    defect is what those 400s were is UNCONFIRMED (bodies weren't captured, no repro key was
    available at diagnosis time), but the flat shape contradicts Perplexity's documented
    schema regardless and is fixed on that basis alone.

    This test instead captures the REAL outgoing JSON body and checks its structure per
    Perplexity's documented web_search tool schema: `filters.search_recency_filter`, not a
    bare `search_recency_filter` key on the tool object. A future regression back to the flat
    shape fails THIS test even though the string-pin above could not tell the difference."""
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    import agents.market_intelligence.spend_tracker as spend_tracker
    monkeypatch.setattr(spend_tracker, "log_perplexity_call", _noop_meter)

    captured = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "completed",
                    "output": [{"type": "message",
                                "content": [{"type": "output_text", "text": "ok"}]}]}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda *a, **k: _Client())

    out = await collector.search_news_perplexity("query", recency="week", fresh=True)
    assert out == "ok"
    tool = captured["json"]["tools"][0]
    assert tool["type"] == "web_search"
    assert tool.get("filters", {}).get("search_recency_filter") == "week", (
        "search_recency_filter must be nested under tools[0]['filters'], not a top-level "
        f"key on the tool — got tool={tool!r}"
    )
    assert "search_recency_filter" not in tool, \
        "search_recency_filter must not ALSO be a flat sibling of type"


def test_the_health_probe_does_not_buy_a_search():
    """A liveness ping proves the endpoint and the key. Attaching the web_search tool would
    add a per-search fee to every probe."""
    # Bound the slice to this function only — the next top-level def is the news search,
    # which DOES attach the tool, so a loose slice would read it as the probe's.
    probe = _COLLECTOR_SRC.split("async def check_perplexity_health", 1)[1]
    probe = probe.split("async def search_news_perplexity", 1)[0]
    assert '"preset"' in probe and '"input": "ping"' in probe
    # No tools block on the ping. ⚠ Measured 2026-08-27: this does NOT make it free — a
    # preset request searches anyway. The assertion is about not CONFIGURING a search, which
    # is all we control. (Assert on the request BODY: the comment above names the tool.)
    body = probe.split("json={", 1)[1].split("},", 1)[0]
    body = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    assert '"tools"' not in body and "web_search" not in body


# ── SAFETY: a Perplexity problem is an UNAVAILABLE INPUT, never a judgement ──────────────
# Operator 2026-08-27: "make sure any issue with perplexity doesn't affect live trades, just
# render as no-op or unavailable input."
_DET_SRC = io.open("agents/market_intelligence/ep_detector.py", encoding="utf-8").read()


def test_an_unparseable_answer_is_unavailable_not_routine():
    """THE DEFECT THIS FIXES. `_validate_catalyst_perplexity` used to end `else: return
    "routine"` — so an empty, truncated or garbled answer became a real grade, and the LOWEST
    one. That mattered more after #233: "routine" against a strong/game_changer label counts
    as a disagreement, which renders the second-opinion block to the judge. A degraded
    provider could therefore argue every catalyst down. Unrecognised text is now None."""
    fn = _DET_SRC.split("async def _validate_catalyst_perplexity", 1)[1]
    fn = fn.split("\ndef ", 1)[0]
    assert 'else:\n            return "routine"' not in fn, \
        "a failed/garbled Perplexity answer must not become a grade"
    assert '"ROUTINE" in text' in fn, "routine is returned only when the model SAYS routine"
    assert "treating as unavailable, not as 'routine'" in fn


def test_the_third_call_site_was_migrated_too():
    """The catalyst validator is the site that actually produces the second opinion; it lives
    in ep_detector.py and was missed by the first pass over collector.py."""
    fn = _DET_SRC.split("async def _validate_catalyst_perplexity", 1)[1].split("\ndef ", 1)[0]
    # Comments name the sunset endpoint deliberately (that is the record of what moved);
    # what must not survive is a CALL to it.
    code = "\n".join(l for l in fn.splitlines() if not l.strip().startswith("#"))
    assert "chat/completions" not in code
    assert "collector._PPLX_AGENT_URL" in fn
    assert '"model"' not in fn, "no model literal on this path either"
    body = fn.split("json={", 1)[1].split("},", 1)[0]
    body = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    assert '"tools"' not in body and "web_search" not in body, \
        "no search tool is configured on this path (note: measured 2026-08-27, that does " \
        "NOT suppress search — the Agent API searches under a preset regardless)"


def test_every_consumer_treats_an_absent_second_opinion_as_a_no_op():
    """None must flow through the whole chain without becoming a decision anywhere."""
    from agents.market_intelligence.briefing import format_grade_provenance
    from agents.market_intelligence.ep_grade_judge import _build_judge_prompt

    # the judge sees no second-opinion block at all
    p = {"ticker": "T", "gap_pct": 10.0, "second_opinion": None,
         "floor_catalyst_quality": "strong", "analysis": "a"}
    assert "--- SECOND OPINION" not in _build_judge_prompt(p)
    # the alert prints no Perplexity voice line
    assert format_grade_provenance({"catalyst_quality": "strong", "gemini_validation": None}) == ""
    # and the disagreement flag is False, not True-by-absence
    assert "bool(pplx_quality and pplx_quality != catalyst_quality)" in _DET_SRC


def test_a_perplexity_outage_can_only_stop_the_theme_engine_never_a_trade():
    """The one hard-abort on a Perplexity failure is scoped to the theme engine and fails in
    the SAFE direction (it prevents mass Fading). Nothing in the EP scan, the entry pipeline
    or the broker aborts on it — pin that, so a future edit cannot widen the blast radius."""
    th = io.open("agents/market_intelligence/theme_engine.py", encoding="utf-8").read()
    assert "PerplexityUnavailableError" in th
    for path in ("agents/market_intelligence/entry_pipeline.py",
                 "agents/market_intelligence/broker/order_manager.py"):
        try:
            src = io.open(path, encoding="utf-8").read()
        except FileNotFoundError:
            continue
        assert "perplexity" not in src.lower(), f"{path} must not depend on Perplexity"


# ── THE BLIND SPOT: a spurious grade from a SUCCESSFUL call ──────────────────────────────
# Operator 2026-08-27: "when perplexity returned routine (instead of unavailable) the judge
# can still tell it didn't actually evaluate anything given no other input text, is that
# right? I just want to see how robust our judge is in case we have blind spots."
#
# It could not. The disagreement block hands the judge a GRADE WITH NO PROVENANCE — it says
# another model graded this routine, and nothing about what that model was given. The judge
# has no way to know it was handed an empty string. So the fix cannot live in the judge; it
# has to live where the emptiness is known.
@pytest.mark.asyncio
@pytest.mark.parametrize("summary", [
    "", "   ", "\n\t ",
    "I couldn't find any recent news for this ticker.",
    "Search results don't contain information about this company.",
    "No recent news available.",
])
async def test_nothing_to_validate_returns_unavailable_without_paying_for_a_call(
        summary, monkeypatch):
    """A model asked to pick one of three words about nothing comes back ROUTINE — a
    SUCCESSFUL call returning a spurious grade, which the unrecognised-text guard cannot
    catch. It must not reach the wire at all."""
    import httpx

    from agents.market_intelligence import ep_detector

    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    called = []

    class _NoCalls:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            called.append(1)
            raise AssertionError("a call went out for an empty catalyst summary")

    monkeypatch.setattr(httpx, "AsyncClient", _NoCalls)
    assert await ep_detector._validate_catalyst_perplexity("AAA", summary) is None
    assert not called


def test_the_hedge_phrases_have_exactly_one_definition():
    """Two readers — the hedge-downgrade and the nothing-to-validate guard. Two copies would
    drift on what "no news" looks like."""
    assert _DET_SRC.count("_PPLX_HEDGE_PHRASES = (") == 1


def test_the_judge_is_told_the_second_opinion_is_not_independent():
    """The residual robustness question: even with real input, the block must not read as a
    corroborating vote — the judge already has that model's text in its evidence."""
    from agents.market_intelligence.ep_grade_judge import _RUBRIC, _build_judge_prompt
    out = _build_judge_prompt({"ticker": "T", "gap_pct": 10.0, "second_opinion": "routine",
                               "floor_catalyst_quality": "game_changer", "analysis": "a"})
    assert "NOT independent corroboration" in out
    assert "re-read the EVIDENCE" in out
    assert "never as a vote" in _RUBRIC


# ══════════════════════════════════════════════════════════════════════════════════════════
# #603 DoD (3) — the post-deadline canary: a future endpoint sunset must be LOUD.
#
# `search_news_perplexity` already alerts on 5xx/timeout/connect/401/402 (the exception
# path) — that was never the gap. The gap is the THREE shapes a sunset can take that never
# raise a classifiable provider-health exception at all: a 200 with nothing extractable, a
# 200 that isn't even JSON, and a 404 on a FIXED URL (unlike Polygon's per-ticker 404s,
# which legitimately carve out to "no alert" — Perplexity has no per-item 404 case).
# ══════════════════════════════════════════════════════════════════════════════════════════

_PPLX_REQ = httpx.Request("POST", "https://api.perplexity.ai/v1/agent")


def _pplx_http_status_error(code: int) -> httpx.HTTPStatusError:
    resp = httpx.Response(code, request=_PPLX_REQ)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e
    raise AssertionError("expected raise_for_status to raise")


class _EmptyAgentResp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"status": "completed", "output": []}


class _BadJsonResp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        raise _json.JSONDecodeError("Expecting value", "not json", 0)


def _install_single_shot_client(monkeypatch, behavior, module=None):
    """Stub AsyncClient whose post() always returns/raises `behavior` — the canary paths
    never retry (they aren't timeout/429)."""
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            if isinstance(behavior, Exception):
                raise behavior
            return behavior

    target = module or collector.httpx
    monkeypatch.setattr(target, "AsyncClient", lambda *a, **k: _Client())


async def _noop_meter(**kwargs):
    return None


def test_health_probe_not_extended_for_shape_assertion():
    """The health ping's `max_output_tokens=5` is registered TRUNCATION BY DESIGN ("text
    unused") in shared/output_ceilings.py — under a preset that searches before answering, 5
    tokens can plausibly end before any `message` output item exists at all. Asserting on
    this ping's text would cry wolf on ordinary truncation, not catch a real anomaly. The
    canary's heartbeat is the real call path only; check_perplexity_health is unchanged."""
    from shared.output_ceilings import TRUNCATION_BY_DESIGN
    assert "perplexity_health" in TRUNCATION_BY_DESIGN
    probe_src = _COLLECTOR_SRC.split("async def check_perplexity_health", 1)[1]
    probe_src = probe_src.split("\nasync def search_news_perplexity", 1)[0]
    assert "_pplx_answer_text" not in probe_src


@pytest.mark.asyncio
async def test_empty_answer_on_200_fires_the_shape_canary(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    import agents.market_intelligence.spend_tracker as spend_tracker
    monkeypatch.setattr(spend_tracker, "log_perplexity_call", _noop_meter)
    _install_single_shot_client(monkeypatch, _EmptyAgentResp())

    fired = []

    async def _spy(provider, event_type, reason, detail=""):
        fired.append((provider, event_type, reason))

    monkeypatch.setattr(llm_health, "alert_endpoint_shape_anomaly", _spy)

    out = await collector.search_news_perplexity("what moved AAA?", fresh=True)

    assert out == ""
    assert fired == [("perplexity", PERPLEXITY_ENDPOINT_ERROR, "empty_answer_on_200")]


@pytest.mark.asyncio
async def test_invalid_json_on_200_fires_the_shape_canary_not_silently(monkeypatch):
    """Today `classify_api_failure` treats a JSONDecodeError as a code bug and returns None
    — no audit row, no alert. A vendor endpoint change (e.g. an HTML body under a 200) would
    be invisible without this."""
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    import agents.market_intelligence.spend_tracker as spend_tracker
    monkeypatch.setattr(spend_tracker, "log_perplexity_call", _noop_meter)
    _install_single_shot_client(monkeypatch, _BadJsonResp())

    fired = []

    async def _spy(provider, event_type, reason, detail=""):
        fired.append((provider, event_type, reason))

    monkeypatch.setattr(llm_health, "alert_endpoint_shape_anomaly", _spy)

    out = await collector.search_news_perplexity("what moved BBB?", fresh=True)

    assert out == ""
    assert len(fired) == 1
    assert fired[0][:2] == ("perplexity", PERPLEXITY_ENDPOINT_ERROR)
    assert fired[0][2] == "invalid_json"


@pytest.mark.asyncio
async def test_404_fires_the_shape_canary_not_the_generic_data_api_guard(monkeypatch):
    """`classify_api_failure`'s 404 carve-out is CORRECT for Polygon's per-ticker lookups
    (an unknown/delisted symbol legitimately 404s — a per-call data condition, not a
    provider outage) and must stay untouched. Perplexity's Agent URL is fixed — there is no
    per-item 404 case — so a 404 here can only mean the endpoint is gone; it must route to
    the shape canary instead of falling through the generic guard's silent None."""
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    _install_single_shot_client(monkeypatch, _pplx_http_status_error(404))

    shape_fired = []
    generic_fired = []

    async def _shape_spy(provider, event_type, reason, detail=""):
        shape_fired.append(reason)

    async def _generic_spy(provider, exc, context=""):
        generic_fired.append(provider)

    monkeypatch.setattr(llm_health, "alert_endpoint_shape_anomaly", _shape_spy)
    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _generic_spy)

    out = await collector.search_news_perplexity("what moved CCC?", fresh=True)

    assert out == ""
    assert shape_fired == ["http_404"]
    assert generic_fired == []


@pytest.mark.asyncio
async def test_non_404_http_failure_still_uses_the_generic_guard(monkeypatch):
    """Parity check: the 404 carve-out must not swallow every status — a 500 (a real
    provider outage) still goes through the existing, unchanged data-API alarm."""
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    _install_single_shot_client(monkeypatch, _pplx_http_status_error(500))

    shape_fired = []
    generic_fired = []

    async def _shape_spy(provider, event_type, reason, detail=""):
        shape_fired.append(reason)

    async def _generic_spy(provider, exc, context=""):
        generic_fired.append(provider)

    monkeypatch.setattr(llm_health, "alert_endpoint_shape_anomaly", _shape_spy)
    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _generic_spy)

    out = await collector.search_news_perplexity("what moved DDD?", fresh=True)

    assert out == ""
    assert shape_fired == []
    assert generic_fired == ["perplexity"]


# ── the same three trip points on the THIRD call site (ep_detector.py) ──────────────────
@pytest.mark.asyncio
async def test_validate_catalyst_perplexity_empty_answer_fires_the_canary(monkeypatch):
    from agents.market_intelligence import ep_detector
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    import agents.market_intelligence.spend_tracker as spend_tracker
    monkeypatch.setattr(spend_tracker, "log_perplexity_call", _noop_meter)
    _install_single_shot_client(monkeypatch, _EmptyAgentResp(), module=httpx)

    fired = []

    async def _spy(provider, event_type, reason, detail=""):
        fired.append(reason)

    monkeypatch.setattr(llm_health, "alert_endpoint_shape_anomaly", _spy)

    out = await ep_detector._validate_catalyst_perplexity("AAA", "A real catalyst summary.")

    assert out is None
    assert fired == ["empty_answer_on_200"]


@pytest.mark.asyncio
async def test_validate_catalyst_perplexity_invalid_json_fires_the_canary(monkeypatch):
    from agents.market_intelligence import ep_detector
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    _install_single_shot_client(monkeypatch, _BadJsonResp(), module=httpx)

    fired = []

    async def _spy(provider, event_type, reason, detail=""):
        fired.append(reason)

    monkeypatch.setattr(llm_health, "alert_endpoint_shape_anomaly", _spy)

    out = await ep_detector._validate_catalyst_perplexity("BBB", "A real catalyst summary.")

    assert out is None
    assert fired == ["invalid_json"]


@pytest.mark.asyncio
async def test_validate_catalyst_perplexity_404_fires_the_canary(monkeypatch):
    from agents.market_intelligence import ep_detector
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    _install_single_shot_client(monkeypatch, _pplx_http_status_error(404), module=httpx)

    shape_fired = []
    generic_fired = []

    async def _shape_spy(provider, event_type, reason, detail=""):
        shape_fired.append(reason)

    async def _generic_spy(provider, exc, context=""):
        generic_fired.append(provider)

    monkeypatch.setattr(llm_health, "alert_endpoint_shape_anomaly", _shape_spy)
    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _generic_spy)

    out = await ep_detector._validate_catalyst_perplexity("CCC", "A real catalyst summary.")

    assert out is None
    assert shape_fired == ["http_404"]
    assert generic_fired == []


@pytest.mark.asyncio
async def test_validate_catalyst_perplexity_5xx_now_alerts_instead_of_silent(monkeypatch):
    """Parity fix: this call site used to alert on credit exhaustion ONLY — a 5xx/timeout was
    entirely silent, even though this is the site that actually PRODUCES the #233 second
    opinion (per the PLAN.md finding). It now goes through the same generic guard as the
    other two call sites."""
    from agents.market_intelligence import ep_detector
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    _install_single_shot_client(monkeypatch, _pplx_http_status_error(500), module=httpx)

    generic_fired = []

    async def _generic_spy(provider, exc, context=""):
        generic_fired.append((provider, context))

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _generic_spy)

    out = await ep_detector._validate_catalyst_perplexity("DDD", "A real catalyst summary.")

    assert out is None
    assert generic_fired == [("perplexity", "catalyst validation")]


# ── the canary function itself: sustained-window Telegram + its own visibility ──────────
def _shape_rows(n, tg1_at=None, provider="perplexity"):
    return [
        {"summary": f"ENDPOINT SHAPE ANOMALY provider={provider} reason=x count={i + 1} "
                    f"tg={1 if tg1_at == i else 0}"}
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_shape_canary_stays_quiet_below_sustained_threshold(monkeypatch):
    from agents.market_intelligence import briefing, db
    monkeypatch.setattr(llm_health, "_last_shape_alert_ts", {})

    async def _get(event_type=None, since_hours=72, limit=50):
        return _shape_rows(1)

    written = []

    async def _log(event_type, summary, detail=""):
        written.append(summary)

    sent = []

    async def _send(text, **kw):
        sent.append(text)
        return True

    monkeypatch.setattr(db, "get_audit_log", _get)
    monkeypatch.setattr(db, "log_audit_event", _log)
    monkeypatch.setattr(briefing, "send_telegram_message", _send)

    await llm_health.alert_endpoint_shape_anomaly("perplexity", PERPLEXITY_ENDPOINT_ERROR, "x")

    assert sent == []
    assert "count=2 tg=0" in written[-1]


@pytest.mark.asyncio
async def test_shape_canary_pages_once_sustained(monkeypatch):
    """N-1 (2 prior rows -> count 2, see the quiet test above) stays quiet; N (2 prior -> this
    makes 3) pages exactly once."""
    from agents.market_intelligence import briefing, db
    monkeypatch.setattr(llm_health, "_last_shape_alert_ts", {})

    async def _get(event_type=None, since_hours=72, limit=50):
        return _shape_rows(2)

    written = []

    async def _log(event_type, summary, detail=""):
        written.append(summary)

    sent = []

    async def _send(text, **kw):
        sent.append(text)
        return True

    monkeypatch.setattr(db, "get_audit_log", _get)
    monkeypatch.setattr(db, "log_audit_event", _log)
    monkeypatch.setattr(briefing, "send_telegram_message", _send)

    await llm_health.alert_endpoint_shape_anomaly("perplexity", PERPLEXITY_ENDPOINT_ERROR, "x")

    assert len(sent) == 1
    assert "count=3 tg=1" in written[-1]


@pytest.mark.asyncio
async def test_shape_canary_never_double_pages_the_same_window(monkeypatch):
    """DB-level dedup: a prior row already carries tg=1 (a page already went out for this
    run of failures) — a new one over threshold must not page again."""
    from agents.market_intelligence import briefing, db
    monkeypatch.setattr(llm_health, "_last_shape_alert_ts", {})

    async def _get(event_type=None, since_hours=72, limit=50):
        return _shape_rows(3, tg1_at=1)

    written = []

    async def _log(event_type, summary, detail=""):
        written.append(summary)

    sent = []

    async def _send(text, **kw):
        sent.append(text)
        return True

    monkeypatch.setattr(db, "get_audit_log", _get)
    monkeypatch.setattr(db, "log_audit_event", _log)
    monkeypatch.setattr(briefing, "send_telegram_message", _send)

    await llm_health.alert_endpoint_shape_anomaly("perplexity", PERPLEXITY_ENDPOINT_ERROR, "x")

    assert sent == []
    assert "tg=0" in written[-1]


@pytest.mark.asyncio
async def test_shape_canary_pregate_collapses_a_same_process_stampede(monkeypatch):
    """Concurrent callers hitting a freshly-dead endpoint at once must not each independently
    re-query the DB and each decide to page — the in-process pre-gate collapses that."""
    from agents.market_intelligence import briefing, db
    monkeypatch.setattr(llm_health, "_last_shape_alert_ts", {})

    lookback_calls = []

    async def _get(event_type=None, since_hours=72, limit=50):
        lookback_calls.append(1)
        return _shape_rows(2)

    async def _log(event_type, summary, detail=""):
        pass

    sent = []

    async def _send(text, **kw):
        sent.append(text)
        return True

    monkeypatch.setattr(db, "get_audit_log", _get)
    monkeypatch.setattr(db, "log_audit_event", _log)
    monkeypatch.setattr(briefing, "send_telegram_message", _send)

    await llm_health.alert_endpoint_shape_anomaly("perplexity", PERPLEXITY_ENDPOINT_ERROR, "x")
    await llm_health.alert_endpoint_shape_anomaly("perplexity", PERPLEXITY_ENDPOINT_ERROR, "x")

    assert len(sent) == 1            # only the first call paged
    assert len(lookback_calls) == 1  # the second never re-queried the DB


@pytest.mark.asyncio
async def test_shape_canary_audit_write_failure_is_logged_not_silent(monkeypatch, caplog):
    """The canary itself must not be a new silent failure: if the DB write fails, that must
    be visible (a warning, not a swallowed debug line)."""
    from agents.market_intelligence import db
    monkeypatch.setattr(llm_health, "_last_shape_alert_ts", {})

    async def _get(event_type=None, since_hours=72, limit=50):
        return []

    async def _log(event_type, summary, detail=""):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "get_audit_log", _get)
    monkeypatch.setattr(db, "log_audit_event", _log)

    with caplog.at_level("WARNING"):
        await llm_health.alert_endpoint_shape_anomaly("perplexity", PERPLEXITY_ENDPOINT_ERROR, "x")

    assert any("audit-row write failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_shape_canary_lookback_failure_stays_quiet_but_logs_and_still_records(monkeypatch, caplog):
    """If the sustained-count lookback itself fails, don't guess and don't page — but this
    occurrence must still land as its own audit row (best-effort), and the failure must be
    logged, not swallowed."""
    from agents.market_intelligence import db
    monkeypatch.setattr(llm_health, "_last_shape_alert_ts", {})

    async def _get(event_type=None, since_hours=72, limit=50):
        raise RuntimeError("db down")

    written = []

    async def _log(event_type, summary, detail=""):
        written.append(summary)

    monkeypatch.setattr(db, "get_audit_log", _get)
    monkeypatch.setattr(db, "log_audit_event", _log)

    with caplog.at_level("WARNING"):
        await llm_health.alert_endpoint_shape_anomaly("perplexity", PERPLEXITY_ENDPOINT_ERROR, "x")

    assert any("lookback failed" in r.message for r in caplog.records)
    assert written and "tg=0" in written[-1]


def test_the_canary_event_name_is_swept_automatically():
    """Naming discipline check: the sweep (`_check_nightly_silent_errors`) and `show errors`
    key off `%error%` — the new event must be caught by that pattern with zero extra
    wiring, exactly like every other unnamed-but-'error'-containing event type."""
    assert "error" in PERPLEXITY_ENDPOINT_ERROR
