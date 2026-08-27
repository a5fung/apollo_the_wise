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

import pytest

from agents.market_intelligence import collector
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
    `instructions`. Both must still be sent, or every caller silently loses its time window."""
    body = _COLLECTOR_SRC.split("_PPLX_AGENT_URL,", 1)[1].split(")", 1)[0]
    body += _COLLECTOR_SRC.split("_PPLX_AGENT_URL,", 2)[2].split(")", 1)[0]
    assert '"search_recency_filter": recency' in _COLLECTOR_SRC
    assert '"instructions": system_prompt or _PERPLEXITY_SYSTEM_DEFAULT' in _COLLECTOR_SRC
    assert '"input": query' in _COLLECTOR_SRC


def test_the_health_probe_does_not_buy_a_search():
    """A liveness ping proves the endpoint and the key. Attaching the web_search tool would
    add a per-search fee to every probe."""
    # Bound the slice to this function only — the next top-level def is the news search,
    # which DOES attach the tool, so a loose slice would read it as the probe's.
    probe = _COLLECTOR_SRC.split("async def check_perplexity_health", 1)[1]
    probe = probe.split("async def search_news_perplexity", 1)[0]
    assert '"preset"' in probe and '"input": "ping"' in probe
    # No tools block at all on the ping — attaching web_search would add a per-search fee
    # to every liveness probe. (Assert on the request BODY, not the whole function: the
    # comment above it names the tool it deliberately omits.)
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
        "this path grades text we already hold — it must not buy a search per candidate"


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
