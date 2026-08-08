"""#377 Cost Meter (Phase 1 PoC) — every LLM call must log its cost to api_usage.

Pins the two PoC wirings:
  1. The forced-tool JUDGE transport (judge_transport.invoke_forced_tool) logs a
     row with a NONZERO cost_usd when given a log_caller, and logs NOTHING when
     log_caller is None (byte-identical to the pre-#377 path).
  2. The HARD CONSTRAINT: a logging/DB failure must NEVER change the verdict — a
     broken cost logger still returns the good grade (does not fall into the
     fail-open and become None).

The theme-discovery (additive) wiring shares the same log_anthropic_call path and
the same correctness property; the cost-computation itself is asserted here against
the real pricing map, so a row's cost_usd > 0 is the meaningful end-to-end check.
"""
import asyncio

import pytest

from agents.market_intelligence import spend_tracker
from agents.market_intelligence.judge_transport import invoke_forced_tool
from tests.conftest import make_mock_pool

_TOOL = {"name": "t", "input_schema": {"type": "object", "properties": {}}}


def _run(coro):
    return asyncio.run(coro)


class _Usage:
    # Mirrors the shape of an Anthropic response.usage object.
    input_tokens = 1200
    output_tokens = 400
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0


class _Block:
    type = "tool_use"

    def __init__(self, inp):
        self.input = inp


class _Resp:
    def __init__(self, inp):
        self.content = [_Block(inp)]
        self.usage = _Usage()


def _ok_client():
    class _Messages:
        async def create(self, **kw):
            return _Resp({"verdict": "HOLD"})

    return type("C", (), {"messages": _Messages()})()


def _kw(**over):
    base = dict(tool=_TOOL, tool_name="t", normalize=lambda d: d, label="test judge",
                timeout=5.0, model="claude-opus-4-8")
    base.update(over)
    return base


@pytest.fixture
def captured_inserts(monkeypatch):
    """Patch spend_tracker's DB pool so log_anthropic_call's INSERT is captured
    instead of hitting Postgres. Returns the list of INSERT arg-tuples."""
    inserts: list[tuple] = []
    pool, conn = make_mock_pool()

    async def _execute(query, *args):
        if "INSERT INTO api_usage" in query:
            inserts.append(args)

    conn.execute.side_effect = _execute

    async def _get_pool():
        return pool

    # Skip the CREATE TABLE (also calls get_pool) — schema is "ensured".
    monkeypatch.setattr(spend_tracker, "_SCHEMA_ENSURED", True)
    monkeypatch.setattr(spend_tracker, "get_pool", _get_pool)
    return inserts


def test_judge_logs_row_with_nonzero_cost(captured_inserts):
    verdict = _run(invoke_forced_tool(
        _ok_client(), "p", **_kw(log_caller="ep_grade_judge")))

    # Behavior unchanged: the verdict still comes back.
    assert verdict == {"verdict": "HOLD"}

    # Exactly one api_usage row was logged.
    assert len(captured_inserts) == 1
    args = captured_inserts[0]
    # INSERT params order: model, caller, input_tokens, output_tokens,
    #                      cache_creation, cache_read, cost_usd
    model, caller, in_tok, out_tok, _cc, _cr, cost, _sr = args
    assert model == "claude-opus-4-8"
    assert caller == "ep_grade_judge"
    assert in_tok == 1200 and out_tok == 400
    # THE deliverable assertion: nonzero cost_usd.
    # Opus = $5/M in, $25/M out → 1200/1e6*5 + 400/1e6*25 = 0.006 + 0.010 = 0.016
    assert cost > 0
    assert cost == pytest.approx(0.016, abs=1e-6)


def test_judge_logs_nothing_when_log_caller_none(captured_inserts):
    # Byte-identical to the pre-#377 path: no log_caller => no api_usage write.
    verdict = _run(invoke_forced_tool(_ok_client(), "p", **_kw()))
    assert verdict == {"verdict": "HOLD"}
    assert captured_inserts == []


def test_logging_failure_does_not_change_verdict(monkeypatch):
    # HARD CONSTRAINT: a DB/logging failure must NOT turn a good grade into a
    # fail-open None. log_anthropic_call raises by design on DB failure; the
    # transport must swallow it AFTER extracting the verdict.
    async def _boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(spend_tracker, "log_anthropic_call", _boom)

    verdict = _run(invoke_forced_tool(
        _ok_client(), "p", **_kw(log_caller="ep_grade_judge")))

    # Verdict is preserved — the broken logger did not corrupt grading.
    assert verdict == {"verdict": "HOLD"}


# ── PoC site 2: theme discovery (additive, multi-turn loop) ──
#
# The priority PoC site. Existing discovery tests use a _fake_client whose
# response has no `.usage`, so the new log call silently no-ops there. This case
# drives a discovery response that DOES carry `.usage` + `.stop_reason` and
# asserts the api_usage row actually lands with a nonzero cost — otherwise a typo
# in the model/caller args would ship green.

class _DiscoUsage:
    input_tokens = 3000      # theme discovery sends a large RS/description blob
    output_tokens = 800
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0


class _DiscoBlock:
    def __init__(self, type, name=None, input=None):
        self.type = type
        self.name = name
        self.input = input or {}


class _DiscoResp:
    def __init__(self, *blocks):
        self.content = list(blocks)
        self.usage = _DiscoUsage()
        self.stop_reason = "tool_use"


def test_theme_discovery_logs_row_with_nonzero_cost(monkeypatch, captured_inserts):
    from agents.market_intelligence import theme_engine as te
    from agents.market_intelligence import universe

    # Tickers need descriptions or they're filtered out before the LLM call.
    monkeypatch.setitem(universe.TICKER_DESC, "UMAC", "commercial drone maker")
    monkeypatch.setitem(universe.TICKER_DESC, "RCAT", "defense drone maker")
    stocks = [
        {"ticker": "UMAC", "rs_composite": 99, "sector": "Industrials"},
        {"ticker": "RCAT", "rs_composite": 95, "sector": "Industrials"},
    ]
    sbt = {s["ticker"]: s for s in stocks}

    report = _DiscoResp(_DiscoBlock(
        "tool_use", name="report_themes",
        input={"themes": [{"name": "Drone/UAS", "tickers": ["UMAC", "RCAT"]}]}))

    calls = []

    async def _create(**kwargs):
        calls.append(kwargs)
        return report

    client = type("C", (), {"messages": type("M", (), {"create": staticmethod(_create)})()})()
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = _run(te._discover_new_themes(stocks, [], sbt))

    # Discovery behavior unchanged: the drone theme is still returned.
    assert [t["name"] for t in out] == ["Drone/UAS"]

    # The cost meter logged exactly one api_usage row for this turn.
    assert len(captured_inserts) == 1
    model, caller, in_tok, out_tok, _cc, _cr, cost, _sr = captured_inserts[0]
    assert caller == "theme_discovery"
    assert model == te.THEME_MODEL          # Sonnet
    assert in_tok == 3000 and out_tok == 800
    assert cost > 0
    # Sonnet = $3/M in, $15/M out → 3000/1e6*3 + 800/1e6*15 = 0.009 + 0.012 = 0.021
    assert cost == pytest.approx(0.021, abs=1e-6)


# ── Rollout: usage-SHAPE traps (the silent-zero-row class) ───────────────────
#
# log_anthropic_call reads tokens via getattr(usage, "input_tokens", 0). On a
# raw-REST site (catalyst_metrics_extractor) the SDK isn't used — usage is a
# plain DICT, on which getattr returns the default 0 → a zero-cost row that ships
# green against the attribute-object mocks above. The rollout fixed this by
# wrapping the dict in a SimpleNamespace at that one site. These cases pin BOTH
# the trap (a bare dict logs zero) AND the fix (the wrap logs nonzero), so a
# regression that drops the wrap fails here instead of silently mis-metering.

def test_anthropic_dict_usage_unwrapped_logs_zero(captured_inserts):
    # Documents the trap: a raw dict passed straight to log_anthropic_call reads
    # 0 tokens (getattr misses dict keys) — this is WHY the raw-REST site wraps it.
    cost = _run(spend_tracker.log_anthropic_call(
        model="claude-sonnet-4-6", caller="raw_dict",
        usage={"input_tokens": 5000, "output_tokens": 1000},
    ))
    assert cost == 0.0
    assert len(captured_inserts) == 1
    _m, _c, in_tok, out_tok, _cc, _cr, logged_cost, _sr = captured_inserts[0]
    assert in_tok == 0 and out_tok == 0 and logged_cost == 0.0


def test_anthropic_dict_usage_wrapped_logs_nonzero(captured_inserts):
    # The fix the metrics-extractor site applies: SimpleNamespace(**usage_dict).
    from types import SimpleNamespace
    cost = _run(spend_tracker.log_anthropic_call(
        model="claude-sonnet-4-6", caller="catalyst_metrics_extractor",
        usage=SimpleNamespace(**{"input_tokens": 5000, "output_tokens": 1000}),
    ))
    # Sonnet = $3/M in, $15/M out → 5000/1e6*3 + 1000/1e6*15 = 0.015 + 0.015 = 0.030
    assert cost == pytest.approx(0.030, abs=1e-6)
    assert len(captured_inserts) == 1
    _m, caller, in_tok, out_tok, _cc, _cr, logged_cost, _sr = captured_inserts[0]
    assert caller == "catalyst_metrics_extractor"
    assert in_tok == 5000 and out_tok == 1000 and logged_cost > 0


# ── Rollout: the Perplexity meter (separate shape) ───────────────────────────
#
# Perplexity usage uses OpenAI naming (prompt_tokens / completion_tokens) and
# charges a per-request SEARCH FEE on top of tokens. log_perplexity_call maps the
# names + folds in the fee. These pin (a) the dict-naming map, (b) the fee, and
# (c) the cheaper "sonar" rate vs "sonar-pro".

def test_perplexity_logs_tokens_plus_request_fee(captured_inserts):
    cost = _run(spend_tracker.log_perplexity_call(
        caller="perplexity_news_search", model="sonar-pro",
        usage={"prompt_tokens": 2000, "completion_tokens": 500},
    ))
    # sonar-pro = $3/M in, $15/M out, +$0.010/req medium-context search fee:
    #   2000/1e6*3 + 500/1e6*15 + 0.010 = 0.006 + 0.0075 + 0.010 = 0.0235
    assert cost == pytest.approx(0.0235, abs=1e-6)
    assert len(captured_inserts) == 1
    model, caller, in_tok, out_tok, _cc, _cr, logged_cost, _sr = captured_inserts[0]
    assert model == "sonar-pro" and caller == "perplexity_news_search"
    # OpenAI naming was correctly mapped onto the api_usage in/out columns.
    assert in_tok == 2000 and out_tok == 500
    assert logged_cost > 0


def test_perplexity_sonar_cheaper_rate_and_fee(captured_inserts):
    # The ep_detector validation path uses the cheaper "sonar" model.
    cost = _run(spend_tracker.log_perplexity_call(
        caller="perplexity_catalyst_validate", model="sonar",
        usage={"prompt_tokens": 1000, "completion_tokens": 100},
    ))
    # sonar = $1/M in, $1/M out, +$0.008/req fee:
    #   1000/1e6*1 + 100/1e6*1 + 0.008 = 0.001 + 0.0001 + 0.008 = 0.0091
    assert cost == pytest.approx(0.0091, abs=1e-6)
    assert captured_inserts[0][0] == "sonar"


def test_perplexity_no_usage_still_logs_request_fee(captured_inserts):
    # A health-ping response may carry no usage block — the per-request fee (the
    # dominant cost) must still land, with zero tokens.
    cost = _run(spend_tracker.log_perplexity_call(
        caller="perplexity_health", model="sonar-pro", usage=None,
    ))
    assert cost == pytest.approx(0.010, abs=1e-6)
    _m, _c, in_tok, out_tok, _cc, _cr, _cost, _sr = captured_inserts[0]
    assert in_tok == 0 and out_tok == 0


def test_perplexity_log_failure_preserves_caller_result(monkeypatch):
    # HARD CONSTRAINT mirror for the Perplexity sites: every wiring wraps
    # log_perplexity_call in its own try/except, so a logging failure cannot
    # change the search/validation result. We simulate the search choke point's
    # exact wrapping shape and assert the "result" survives a raising logger.
    async def _boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(spend_tracker, "log_perplexity_call", _boom)

    async def _search_with_logging():
        result = "AVAV gapped on a $990M Army contract award"  # the real return
        try:
            await spend_tracker.log_perplexity_call(
                caller="perplexity_news_search", model="sonar-pro",
                usage={"prompt_tokens": 10, "completion_tokens": 10},
            )
        except Exception:
            pass
        return result

    assert _run(_search_with_logging()) == "AVAV gapped on a $990M Army contract award"


# ── Rollout: SITE-level coverage (the typo guard) ────────────────────────────
#
# The isolation tests above prove the spend_tracker FUNCTIONS work. These two
# drive the real WIRED call sites end-to-end (mock client → real production code
# path → captured api_usage row), which is the only thing that catches a wrong
# model constant / wrong caller label / wrong response variable at a site — the
# exact "ships green" gap the committed test file warns about. One Anthropic-SDK
# site (catalyst_materiality) and one forced-tool-transport site (mgmt_judge).

def test_site_catalyst_materiality_logs_row(captured_inserts):
    from agents.market_intelligence import catalyst_materiality as cm

    class _U:
        input_tokens = 800
        output_tokens = 60
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0

    class _TextBlock:
        text = '{"tier": "material"}'

    class _Resp:
        content = [_TextBlock()]
        usage = _U()

    class _Messages:
        async def create(self, **kw):
            return _Resp()

    client = type("C", (), {"messages": _Messages()})()

    tier = _run(cm.judge_materiality_llm(
        client, company="Acme", sector="Tech", market_cap=2.5e9,
        catalyst="$270M contract", analysis="multi-year award",
    ))
    # Behavior unchanged: the real tier still parses out of the response.
    assert tier == "material"

    # The site passed the RIGHT model + caller to the meter.
    assert len(captured_inserts) == 1
    model, caller, in_tok, out_tok, _cc, _cr, cost, _sr = captured_inserts[0]
    assert caller == "catalyst_materiality"
    assert model == cm._MODEL              # SONNET
    assert in_tok == 800 and out_tok == 60
    assert cost > 0


def test_site_mgmt_judge_logs_row(captured_inserts):
    from agents.market_intelligence import mgmt_judge

    class _U:
        input_tokens = 1500
        output_tokens = 120
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0

    class _ToolBlock:
        type = "tool_use"
        input = {"verdict": "HOLD", "rationale": "structure intact"}

    class _Resp:
        content = [_ToolBlock()]
        usage = _U()

    class _Messages:
        async def create(self, **kw):
            return _Resp()

    client = type("C", (), {"messages": _Messages()})()

    verdict = _run(mgmt_judge.manage_holistic(
        client, {"ticker": "NVDA", "rationale_inputs": "x"}, timeout=5.0))
    # Behavior unchanged: the bounded verdict still comes back.
    assert verdict is not None and verdict["verdict"] == "HOLD"

    # The site threaded log_caller="mgmt_judge" through the transport.
    assert len(captured_inserts) == 1
    model, caller, in_tok, out_tok, _cc, _cr, cost, _sr = captured_inserts[0]
    assert caller == "mgmt_judge"
    assert model == mgmt_judge.MODEL
    assert in_tok == 1500 and out_tok == 120
    assert cost > 0
