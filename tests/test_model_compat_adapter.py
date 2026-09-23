"""shared/llm_client — the model-compat transport adapter (2026-09-23) + the refresh job's
pre-adoption canary.

Pins, against a fake client that raises the EXACT 400 messages claude-opus-5-5 returned:
  1. forced tool_choice rejected → structured-output rewrite (tools/tool_choice gone,
     output_config.format carries the tool's schema), retried ONCE, and the response comes back
     with a synthesized tool_use block (type/name/input/id), stop_reason mapped to "tool_use",
     usage + model untouched — so judge_transport's tool_use extraction works unchanged.
  2. the rewrite is CACHED per model: the second call goes straight to the working form (one
     API call, no 400), and a different model is unaffected.
  3. "any" over SEVERAL tools → the discriminated-union schema; the chosen variant becomes the
     synthesized tool_use, and an unknown tool name fails open.
  4. thinking {"type":"disabled"} rejected → thinking dropped, max_tokens raised by the headroom
     rule (never lowered, capped).
  5. unparseable structured output → StructuredOutputError (a ValueError) → judge_transport's
     fail-open returns None, exactly as it did on the 400.
  6. a truncated rewritten response passes through untouched (is_truncated still fires).
  7. an unrelated 400 / a 400 on a request with nothing to rewrite is re-raised as-is.
  8. the sync adapter behaves the same (channels/telegram's health check).
  9. refresh_model_resolution: canary pass → adopted; canary fail → tier keeps the last working
     id, `model_release_rejected` audit + Telegram carrying the exact error, deduped.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared import llm_client as lc
from shared.llm_client import (
    REWRITE_FORCED_TOOL,
    REWRITE_THINKING_DISABLED,
    StructuredOutputError,
    thinking_headroom,
    wrap_client,
)

TOOL_CHOICE_400 = ('Error code: 400 - {\'type\': \'error\', \'error\': {\'type\': '
                   '\'invalid_request_error\', \'message\': \'tool_choice: type "tool" and "any" '
                   'are not supported for this model.\'}}')
THINKING_400 = ('Error code: 400 - {\'type\': \'error\', \'error\': {\'type\': '
                '\'invalid_request_error\', \'message\': \'"thinking.type.disabled" is not '
                'supported for this model. Use "thinking.type.adaptive" and '
                '"output_config.effort" to control thinking behavior.\'}}')

GRADE_TOOL = {
    "name": "grade_ep",
    "description": "Grade an EP.",
    "input_schema": {
        "type": "object",
        "properties": {
            "grade": {"type": "integer", "minimum": 0, "maximum": 100},
            "tier": {"type": "string", "enum": ["HIGH", "MODERATE", "LOW"]},
            "rationale": {"type": "string", "maxLength": 400},
        },
        "required": ["grade", "tier"],
    },
}
ADVISOR_TOOL = {
    "name": "consult_advisor",
    "description": "Ask the advisor.",
    "input_schema": {"type": "object", "properties": {"question": {"type": "string"}},
                     "required": ["question"]},
}


class FakeBadRequest(Exception):
    """Shape of anthropic.BadRequestError as the adapter sees it: .status_code + .message."""

    def __init__(self, message: str):
        super().__init__(message)
        self.status_code = 400
        self.message = message


class Block:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class Resp:
    """Pydantic-free stand-in for anthropic.types.Message with model_copy."""

    def __init__(self, content, stop_reason="end_turn", model="m", usage=None):
        self.content = content
        self.stop_reason = stop_reason
        self.model = model
        self.usage = usage or SimpleNamespace(input_tokens=11, output_tokens=7,
                                              cache_creation_input_tokens=0,
                                              cache_read_input_tokens=0)

    def model_copy(self, update=None):
        new = Resp(self.content, self.stop_reason, self.model, self.usage)
        for k, v in (update or {}).items():
            setattr(new, k, v)
        return new


def _json_text(obj, stop="end_turn", with_thinking=True):
    blocks = ([Block("thinking", thinking="")] if with_thinking else []) + \
             [Block("text", text=json.dumps(obj))]
    return Resp(blocks, stop_reason=stop, model="claude-opus-5-5")


class FakeOpus55:
    """Behaves like claude-opus-5-5: 400 on forced tools and on thinking=disabled; answers
    structured-output requests with schema JSON in a text block (after a thinking block)."""

    def __init__(self, answer=None, stop="end_turn", text_override=None):
        self.calls: list[dict] = []
        self.answer = answer if answer is not None else {"grade": 80, "tier": "HIGH", "rationale": "x"}
        self.stop = stop
        self.text_override = text_override

    async def create(self, **kw):
        self.calls.append(kw)
        tc = kw.get("tool_choice") or {}
        if tc.get("type") in ("tool", "any"):
            raise FakeBadRequest(TOOL_CHOICE_400)
        if (kw.get("thinking") or {}).get("type") == "disabled":
            raise FakeBadRequest(THINKING_400)
        fmt = (kw.get("output_config") or {}).get("format")
        if fmt:
            if self.text_override is not None:
                return Resp([Block("thinking", thinking=""), Block("text", text=self.text_override)],
                            stop_reason=self.stop, model=kw["model"])
            return _json_text(self.answer, stop=self.stop)
        return Resp([Block("thinking", thinking=""), Block("text", text="pong")], model=kw["model"])


def _client(messages):
    return wrap_client(SimpleNamespace(messages=messages))


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _fresh_cache():
    lc.reset_adaptations()
    yield
    lc.reset_adaptations()


# ─── 1. forced tool → structured output → synthesized tool_use ──────────────

def test_forced_tool_rewrite_synthesizes_tool_use_and_keeps_meter_fields():
    fake = FakeOpus55()
    resp = _run(_client(fake).messages.create(
        model="claude-opus-5-5", max_tokens=1500, tools=[GRADE_TOOL],
        tool_choice={"type": "tool", "name": "grade_ep"},
        messages=[{"role": "user", "content": "grade"}]))

    # two API calls: the original (400) and the rewritten one
    assert len(fake.calls) == 2
    first, second = fake.calls
    assert first["tool_choice"] == {"type": "tool", "name": "grade_ep"}
    assert "tools" not in second and "tool_choice" not in second
    fmt = second["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert set(fmt["schema"]["properties"]) == {"grade", "tier", "rationale"}
    # unsupported constraints stripped, additionalProperties pinned — on the COPY only
    assert "minimum" not in fmt["schema"]["properties"]["grade"]
    assert "maxLength" not in fmt["schema"]["properties"]["rationale"]
    assert fmt["schema"]["additionalProperties"] is False
    assert GRADE_TOOL["input_schema"]["properties"]["grade"]["minimum"] == 0

    # the synthesized block is what every caller reads
    tool_block = next(b for b in resp.content if b.type == "tool_use")
    assert tool_block.name == "grade_ep"
    assert tool_block.input == {"grade": 80, "tier": "HIGH", "rationale": "x"}
    assert tool_block.id.startswith("toolu_synth_")
    # the JSON text is GONE (silent-stop readers scan text), the thinking block stays
    assert [b.type for b in resp.content] == ["thinking", "tool_use"]
    # cost-meter fields preserved; stop_reason mapped so is_truncated / tool_use checks pass
    assert resp.stop_reason == "tool_use"
    assert resp.model == "claude-opus-5-5"
    assert resp.usage.output_tokens == 7
    from shared.llm_response import is_truncated, usage_tokens
    assert not is_truncated(resp)
    assert usage_tokens(resp)["input_tokens"] == 11


def test_schema_sanitizer_keeps_properties_named_like_keywords():
    """A property called `pattern` / `maximum` is the caller's name, not a constraint: it must
    survive, while real constraints are stripped; a bare object is not forced to {}."""
    from shared.llm_client import _sanitize_schema
    schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "pattern": "^[A-Z]+$", "maxLength": 12},
            "maximum": {"type": "number", "maximum": 100},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            "free": {"type": "object"},
        },
        "required": ["pattern", "maximum"],
    }
    out = _sanitize_schema(schema)
    assert set(out["properties"]) == {"pattern", "maximum", "tags", "free"}
    assert out["properties"]["pattern"] == {"type": "string"}
    assert out["properties"]["maximum"] == {"type": "number"}
    assert out["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}
    assert out["properties"]["free"] == {"type": "object"}          # not pinned to {}
    assert out["additionalProperties"] is False and out["required"] == ["pattern", "maximum"]
    assert "pattern" in schema["properties"]["pattern"]              # caller's dict untouched


def test_no_text_block_survives_synthesis_even_with_several():
    """theme_engine's silent-stop path reads text blocks; after synthesis there must be none."""
    class TwoTexts(FakeOpus55):
        async def create(self, **kw):
            self.calls.append(kw)
            if (kw.get("tool_choice") or {}).get("type") == "tool":
                raise FakeBadRequest(TOOL_CHOICE_400)
            return Resp([Block("thinking", thinking=""),
                         Block("text", text=json.dumps({"grade": 1, "tier": "LOW"})),
                         Block("text", text="trailing commentary")], model=kw["model"])
    resp = _run(_client(TwoTexts()).messages.create(
        model="claude-opus-5-5", max_tokens=500, tools=[GRADE_TOOL],
        tool_choice={"type": "tool", "name": "grade_ep"},
        messages=[{"role": "user", "content": "x"}]))
    assert [b.type for b in resp.content] == ["thinking", "tool_use"]
    from shared.llm_response import first_text
    assert first_text(resp) == ""


def test_judge_transport_works_unchanged_through_the_adapter():
    from agents.market_intelligence.judge_transport import invoke_forced_tool
    fake = FakeOpus55()
    verdict = _run(invoke_forced_tool(
        _client(fake), "grade this", tool=GRADE_TOOL, tool_name="grade_ep",
        normalize=lambda d: d, label="test judge", timeout=5.0, model="claude-opus-5-5"))
    assert verdict == {"grade": 80, "tier": "HIGH", "rationale": "x"}


def test_any_with_exactly_one_tool_is_a_forced_tool():
    fake = FakeOpus55(answer={"themes": [{"name": "Energy Infra"}]})
    resp = _run(_client(fake).messages.create(
        model="claude-opus-5-5", max_tokens=800, tools=[GRADE_TOOL], tool_choice={"type": "any"},
        messages=[{"role": "user", "content": "x"}]))
    block = next(b for b in resp.content if b.type == "tool_use")
    assert block.name == "grade_ep" and block.input == {"themes": [{"name": "Energy Infra"}]}
    assert "anyOf" not in json.dumps(fake.calls[1]["output_config"])


# ─── 2. the per-model cache ─────────────────────────────────────────────────

def test_rewrite_is_remembered_per_model_and_other_models_untouched():
    fake = FakeOpus55()
    client = _client(fake)
    kw = dict(model="claude-opus-5-5", max_tokens=500, tools=[GRADE_TOOL],
              tool_choice={"type": "tool", "name": "grade_ep"},
              messages=[{"role": "user", "content": "x"}])
    _run(client.messages.create(**kw))
    assert lc.adopted_rewrites("claude-opus-5-5") == {REWRITE_FORCED_TOOL}
    n_before = len(fake.calls)
    _run(client.messages.create(**kw))
    assert len(fake.calls) == n_before + 1          # straight to the working form, no 400
    assert "tool_choice" not in fake.calls[-1]
    assert lc.adopted_rewrites("claude-opus-5") == frozenset()

    # a model that accepts forced tools is never rewritten
    class Opus5:
        def __init__(self): self.calls = []
        async def create(self, **kw):
            self.calls.append(kw)
            return Resp([Block("tool_use", id="toolu_1", name="grade_ep", input={"grade": 1})],
                        stop_reason="tool_use", model="claude-opus-5")
    ok = Opus5()
    resp = _run(_client(ok).messages.create(**{**kw, "model": "claude-opus-5"}))
    assert ok.calls[0]["tool_choice"] == {"type": "tool", "name": "grade_ep"}
    assert resp.content[0].id == "toolu_1"


def test_adoption_is_announced_once(monkeypatch):
    seen = []
    monkeypatch.setattr(lc, "_audit_best_effort", lambda ev, s, d: seen.append((ev, s)))
    fake = FakeOpus55()
    client = _client(fake)
    kw = dict(model="claude-opus-5-5", max_tokens=500, tools=[GRADE_TOOL],
              tool_choice={"type": "tool", "name": "grade_ep"},
              messages=[{"role": "user", "content": "x"}])
    _run(client.messages.create(**kw))
    _run(client.messages.create(**kw))
    assert seen == [("llm_request_rewrite_adopted", f"claude-opus-5-5: {REWRITE_FORCED_TOOL}")]


# ─── 3. "any" over SEVERAL tools ────────────────────────────────────────────

def test_any_over_two_tools_uses_a_union_and_synthesizes_the_chosen_tool():
    fake = FakeOpus55(answer={"call": {"tool": "consult_advisor", "input": {"question": "which?"}}})
    resp = _run(_client(fake).messages.create(
        model="claude-opus-5-5", max_tokens=8000, thinking={"type": "disabled"},
        tools=[GRADE_TOOL, ADVISOR_TOOL], tool_choice={"type": "any"},
        messages=[{"role": "user", "content": "x"}]))
    schema = fake.calls[-1]["output_config"]["format"]["schema"]
    variants = schema["properties"]["call"]["anyOf"]
    assert [v["properties"]["tool"]["const"] for v in variants] == ["grade_ep", "consult_advisor"]
    assert variants[1]["properties"]["input"]["properties"] == {"question": {"type": "string"}}
    block = next(b for b in resp.content if b.type == "tool_use")
    assert block.name == "consult_advisor" and block.input == {"question": "which?"}
    # BOTH rejections handled on the same request (one retry per feature), both remembered
    assert lc.adopted_rewrites("claude-opus-5-5") == {REWRITE_FORCED_TOOL, REWRITE_THINKING_DISABLED}
    assert "thinking" not in fake.calls[-1] and fake.calls[-1]["max_tokens"] == 16_000


def test_union_output_naming_an_unknown_tool_fails_open():
    fake = FakeOpus55(answer={"call": {"tool": "not_a_tool", "input": {}}})
    with pytest.raises(StructuredOutputError):
        _run(_client(fake).messages.create(
            model="claude-opus-5-5", max_tokens=800, tools=[GRADE_TOOL, ADVISOR_TOOL],
            tool_choice={"type": "any"}, messages=[{"role": "user", "content": "x"}]))


# ─── 4. thinking disabled → dropped + headroom ──────────────────────────────

def test_thinking_disabled_rewrite_drops_param_and_adds_headroom():
    fake = FakeOpus55()
    resp = _run(_client(fake).messages.create(
        model="claude-opus-5-5", max_tokens=1000, thinking={"type": "disabled"},
        messages=[{"role": "user", "content": "x"}]))
    assert len(fake.calls) == 2
    assert fake.calls[0]["thinking"] == {"type": "disabled"}
    assert "thinking" not in fake.calls[1]
    assert fake.calls[1]["max_tokens"] == thinking_headroom(1000) == 2024
    from shared.llm_response import first_text
    assert first_text(resp) == "pong"
    assert lc.adopted_rewrites("claude-opus-5-5") == {REWRITE_THINKING_DISABLED}


@pytest.mark.parametrize("mt,expected", [
    (5, 1029),          # tiny ceilings: the floor dominates (thinking has a fixed cost)
    (400, 1424),
    (1000, 2024),       # +1024 beats doubling up to 1024
    (1500, 3000),       # above 1024: doubling (thinking ≈ answer, per the 176/400 measurement)
    (8000, 16000),
    (12000, 16000),     # capped
    (20000, 20000),     # never LOWERED below what the caller asked for
])
def test_thinking_headroom_rule(mt, expected):
    assert thinking_headroom(mt) == expected


# ─── 5/6. fail-open + truncation pass-through ───────────────────────────────

def test_unparseable_structured_output_raises_valueerror_family_and_judge_fails_open():
    from agents.market_intelligence.judge_transport import invoke_forced_tool
    fake = FakeOpus55(text_override="I would rather explain in prose.")
    with pytest.raises(StructuredOutputError) as ei:
        _run(_client(fake).messages.create(
            model="claude-opus-5-5", max_tokens=500, tools=[GRADE_TOOL],
            tool_choice={"type": "tool", "name": "grade_ep"},
            messages=[{"role": "user", "content": "x"}]))
    assert isinstance(ei.value, ValueError)
    from agents.market_intelligence.llm_health import is_credit_error
    assert not is_credit_error(ei.value)
    verdict = _run(invoke_forced_tool(
        _client(FakeOpus55(text_override="nope")), "p", tool=GRADE_TOOL, tool_name="grade_ep",
        normalize=lambda d: d, label="t", timeout=5.0, model="claude-opus-5-5"))
    assert verdict is None


def test_truncated_rewritten_response_passes_through_untouched():
    from shared.llm_response import is_truncated
    fake = FakeOpus55(stop="max_tokens", text_override='{"grade": 80, "tier": "HI')
    resp = _run(_client(fake).messages.create(
        model="claude-opus-5-5", max_tokens=500, tools=[GRADE_TOOL],
        tool_choice={"type": "tool", "name": "grade_ep"},
        messages=[{"role": "user", "content": "x"}]))
    assert is_truncated(resp)
    assert not any(b.type == "tool_use" for b in resp.content)


# ─── 7. non-matching errors are re-raised ───────────────────────────────────

def test_unrelated_400_is_reraised_and_not_cached():
    class Bad:
        async def create(self, **kw):
            raise FakeBadRequest("Error code: 400 - messages: first message must use the user role")
    with pytest.raises(FakeBadRequest):
        _run(_client(Bad()).messages.create(
            model="claude-opus-5-5", max_tokens=5, tools=[GRADE_TOOL],
            tool_choice={"type": "tool", "name": "grade_ep"}, messages=[]))
    assert lc.adopted_rewrites("claude-opus-5-5") == frozenset()


def test_feature_400_with_nothing_to_rewrite_is_reraised():
    class Bad:
        async def create(self, **kw):
            raise FakeBadRequest(TOOL_CHOICE_400)
    with pytest.raises(FakeBadRequest):   # tool_choice auto → nothing we can rewrite
        _run(_client(Bad()).messages.create(
            model="claude-opus-5-5", max_tokens=5, tools=[GRADE_TOOL],
            tool_choice={"type": "auto"}, messages=[]))


def test_persistent_rejection_after_rewrite_is_reraised_not_looped():
    class AlwaysBad:
        def __init__(self): self.n = 0
        async def create(self, **kw):
            self.n += 1
            raise FakeBadRequest(TOOL_CHOICE_400)
    bad = AlwaysBad()
    with pytest.raises(FakeBadRequest):
        _run(_client(bad).messages.create(
            model="claude-opus-5-5", max_tokens=5, tools=[GRADE_TOOL],
            tool_choice={"type": "tool", "name": "grade_ep"}, messages=[]))
    assert bad.n == 2   # original + exactly one retry


# ─── 8. sync twin ───────────────────────────────────────────────────────────

def test_sync_adapter_rewrites_too():
    class SyncOpus55:
        def __init__(self): self.calls = []
        def create(self, **kw):
            self.calls.append(kw)
            if (kw.get("thinking") or {}).get("type") == "disabled":
                raise FakeBadRequest(THINKING_400)
            return Resp([Block("text", text="pong")], model=kw["model"])
    fake = SyncOpus55()
    client = wrap_client(SimpleNamespace(messages=fake))
    resp = client.messages.create(model="claude-opus-5-5", max_tokens=5,
                                  thinking={"type": "disabled"}, messages=[])
    assert resp.content[0].text == "pong" and len(fake.calls) == 2
    assert fake.calls[1]["max_tokens"] == 1029


def test_adapter_delegates_everything_but_create():
    inner = SimpleNamespace(create=AsyncMock(), count_tokens="ct", stream="st")
    client = wrap_client(SimpleNamespace(messages=inner))
    assert client.messages.count_tokens == "ct" and client.messages.stream == "st"


# ─── canary checks themselves ───────────────────────────────────────────────

def test_run_canary_passes_on_an_opus55_shaped_model():
    class Opus55Canary(FakeOpus55):
        async def create(self, **kw):
            fmt = (kw.get("output_config") or {}).get("format")
            if fmt and "anyOf" in json.dumps(fmt["schema"]):
                return _json_text({"call": {"tool": "canary_echo", "input": {"word": "pong"}}})
            if fmt:
                return _json_text({"word": "pong"})
            return await super().create(**kw)
    results = _run(lc.run_canary(_client(Opus55Canary()), "claude-opus-5-5"))
    assert [r.check for r in results] == ["forced_tool", "thinking_disabled", "plain", "any_of_two_tools"]
    assert all(r.ok for r in results), results


def test_run_canary_reports_the_exact_error_and_never_raises():
    class Broken:
        async def create(self, **kw):
            raise FakeBadRequest("Error code: 400 - something entirely new is not supported for this model.")
    results = _run(lc.run_canary(_client(Broken()), "claude-opus-6"))
    assert not any(r.ok for r in results)
    assert "something entirely new" in results[0].detail


# ─── 9. refresh job: adopt vs refuse ────────────────────────────────────────

LIVE_IDS = ["claude-opus-5-5", "claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"]


def _refresh_deps(monkeypatch, tmp_path, canary):
    from agents.market_intelligence import model_resolution as mr
    from shared.model_resolver import write_cache
    monkeypatch.setenv("APOLLO_MODEL_RESOLUTION_CACHE", str(tmp_path / "cache.json"))
    write_cache({"opus": "claude-opus-5", "sonnet": "claude-sonnet-5",
                 "haiku": "claude-haiku-4-5-20251001"}, {}, cache_path=tmp_path / "cache.json")

    async def fake_ids():
        return list(LIVE_IDS)
    monkeypatch.setattr(mr, "_list_model_ids", fake_ids)
    audit, tg = AsyncMock(), AsyncMock()
    monkeypatch.setattr(mr, "log_audit_event", audit)
    monkeypatch.setattr(mr, "_send_telegram", tg)
    monkeypatch.setattr(mr, "audit_event_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(mr, "_canary_model", canary)
    return mr, audit, tg


def test_refresh_adopts_a_release_that_passes_the_canary(monkeypatch, tmp_path):
    from shared.model_resolver import read_cache
    canary = AsyncMock(return_value=(True, ""))
    mr, audit, tg = _refresh_deps(monkeypatch, tmp_path, canary)
    _run(mr.refresh_model_resolution())
    canary.assert_awaited_once_with("claude-opus-5-5")     # only the CHANGING tier is checked
    assert read_cache(tmp_path / "cache.json")["resolved"]["opus"] == "claude-opus-5-5"
    fired = [c.args[0] for c in audit.await_args_list]
    assert "model_release_detected" in fired and "model_release_rejected" not in fired
    assert "New Claude model available" in tg.await_args.args[0]


def test_refresh_refuses_a_release_that_fails_the_canary(monkeypatch, tmp_path):
    from shared.model_resolver import read_cache
    err = 'forced_tool: FakeBadRequest: tool_choice: type "tool" and "any" are not supported for this model.'
    canary = AsyncMock(return_value=(False, err))
    mr, audit, tg = _refresh_deps(monkeypatch, tmp_path, canary)
    n = _run(mr.refresh_model_resolution())
    assert n == 3                                            # the tier is still written (kept)
    cache = read_cache(tmp_path / "cache.json")
    assert cache["resolved"]["opus"] == "claude-opus-5"      # last working id kept
    assert "opus" not in cache["changed_at"]                 # no change recorded
    fired = {c.args[0]: c for c in audit.await_args_list}
    assert "model_release_rejected" in fired and "model_release_detected" not in fired
    assert "keeping claude-opus-5" in fired["model_release_rejected"].args[1]
    assert err in fired["model_release_rejected"].args[2]
    tg.assert_awaited_once()
    text = tg.await_args.args[0]
    assert "NOT adopted" in text and "claude-opus-5-5" in text and "not supported for this model" in text


def test_refresh_refusal_is_reported_once(monkeypatch, tmp_path):
    canary = AsyncMock(return_value=(False, "forced_tool: boom"))
    mr, audit, tg = _refresh_deps(monkeypatch, tmp_path, canary)
    monkeypatch.setattr(mr, "audit_event_exists", AsyncMock(return_value=True))
    _run(mr.refresh_model_resolution())
    tg.assert_not_awaited()
    assert "model_release_rejected" not in [c.args[0] for c in audit.await_args_list]


def test_refresh_first_record_refusal_falls_back_to_the_pin(monkeypatch, tmp_path):
    from shared import llm_models
    from shared.model_resolver import read_cache
    canary = AsyncMock(return_value=(False, "plain: kaput"))
    mr, audit, tg = _refresh_deps(monkeypatch, tmp_path, canary)
    (tmp_path / "cache.json").unlink()                       # no prior record at all
    _run(mr.refresh_model_resolution())
    cache = read_cache(tmp_path / "cache.json")
    assert cache["resolved"]["opus"] == llm_models._TIER_PINS["opus"]
    assert canary.await_count == 3                           # every first-record tier is checked


def test_canary_model_reports_failures_from_run_canary(monkeypatch):
    from agents.market_intelligence import model_resolution as mr

    class Broken:
        async def create(self, **kw):
            raise FakeBadRequest(TOOL_CHOICE_400)
    fake_client = SimpleNamespace(messages=Broken(), close=AsyncMock())
    monkeypatch.setattr(lc, "make_async_anthropic", lambda **kw: wrap_client(fake_client))
    ok, err = _run(mr._canary_model("claude-opus-9"))
    assert ok is False and "forced_tool" in err and "not supported for this model" in err
    fake_client.close.assert_awaited_once()
