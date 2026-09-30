"""shared/llm_samples — real-request capture for the pre-adoption replay (#690).

Pins, through the REAL transport (shared/llm_client.wrap_client over a fake SDK client):
  1. a tracked call site's request is stored as the caller wrote it (pre-adaptation), with the
     answer callers parse; the last 3 are kept and at most one per key per 60 minutes;
  2. nothing is stored while capture is disabled — inside run_canary, inside the replay, or under
     capture_disabled();
  3. a request redact_secrets would change is dropped AND counted in the key's file;
  4. an image block is stored as a marker (never the bytes) and the sample is not replayable;
     a signed thinking block in the history also makes it not replayable;
  5. operator chat / refusals / truncations are never stored; an unwritable directory is silent;
  6. the key is the first frame past the transport AND the pass-through wrappers — judge_transport
     + grade_holistic (via chart_axis.grade_one, a real production key), theme_engine's
     _assignment_turn and theme_merge_arm's _create_with_backoff.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared import llm_call_sites, llm_client, llm_samples
from shared.llm_client import wrap_client


class Block:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class Resp:
    def __init__(self, content, stop_reason="end_turn", model="m"):
        self.content = content
        self.stop_reason = stop_reason
        self.model = model
        self.usage = SimpleNamespace(input_tokens=1, output_tokens=1,
                                     cache_creation_input_tokens=0, cache_read_input_tokens=0)

    def model_copy(self, update=None):
        new = Resp(self.content, self.stop_reason, self.model)
        for k, v in (update or {}).items():
            setattr(new, k, v)
        return new


class FakeMessages:
    """Answers with a tool call when the request forces one, else with text."""

    def __init__(self, stop="end_turn", tool_input=None):
        self.calls: list[dict] = []
        self.stop = stop
        self.tool_input = tool_input if tool_input is not None else {"tier": "HIGH", "grade": 80}

    async def create(self, **kw):
        self.calls.append(kw)
        tc = kw.get("tool_choice") or {}
        if tc.get("type") == "tool":
            return Resp([Block("tool_use", id="t1", name=tc["name"], input=dict(self.tool_input))],
                        stop_reason="tool_use" if self.stop == "end_turn" else self.stop,
                        model=kw["model"])
        if tc.get("type") == "any":
            name = kw["tools"][0]["name"]
            return Resp([Block("tool_use", id="t1", name=name, input=dict(self.tool_input))],
                        stop_reason="tool_use", model=kw["model"])
        return Resp([Block("text", text="pong")], stop_reason=self.stop, model=kw["model"])


def _client(messages=None):
    return wrap_client(SimpleNamespace(messages=messages or FakeMessages()))


def _run(coro):
    return asyncio.run(coro)


KEY = f"{__name__}:_tracked_caller"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_LLM_SAMPLE_DIR", str(tmp_path / "samples"))
    monkeypatch.setitem(llm_call_sites.CALL_SITES, KEY, "THEME_MODEL")
    llm_samples.reset_throttle()
    llm_client.reset_adaptations()
    yield
    llm_samples.reset_throttle()


async def _tracked_caller(client, **kw):
    """Stands in for a production call site; its key is mapped to THEME_MODEL by the fixture."""
    request = dict(model="claude-sonnet-5", max_tokens=100,
                   messages=[{"role": "user", "content": "Ticker: ABCD — classify it"}])
    request.update(kw)
    return await client.messages.create(**request)


def _files():
    return llm_samples.load_all()


def _only_file():
    files = _files()
    assert len(files) == 1, [f["key"] for f in files]
    return files[0]


# ── 1. stored as the caller wrote it; last 3; throttle ───────────────────────

def test_a_tracked_request_is_stored_as_the_caller_wrote_it():
    tool = {"name": "classify", "input_schema": {"type": "object", "properties": {}}}
    _run(_tracked_caller(_client(), tools=[tool], tool_choice={"type": "tool", "name": "classify"},
                         thinking={"type": "disabled"}))
    data = _only_file()
    assert data["key"] == KEY and data["role"] == "THEME_MODEL"
    s = data["samples"][0]
    # pre-adaptation: the caller's own forced tool + thinking-off are what was kept
    assert s["request"]["tool_choice"] == {"type": "tool", "name": "classify"}
    assert s["request"]["thinking"] == {"type": "disabled"}
    assert s["model"] == "claude-sonnet-5" and s["replayable"] is True
    assert s["answer"] == {"stop_reason": "tool_use", "tool": "classify",
                           "tool_input": {"tier": "HIGH", "grade": 80}}
    assert s["subject"] == "ABCD"


def test_a_text_answer_keeps_the_first_500_characters():
    msgs = FakeMessages()

    async def long_text(**kw):
        return Resp([Block("text", text="x" * 900)], model=kw["model"])
    msgs.create = long_text
    _run(_tracked_caller(_client(msgs)))
    ans = _only_file()["samples"][0]["answer"]
    assert ans["stop_reason"] == "end_turn" and len(ans["text"]) == 500 and "tool" not in ans


def test_last_three_are_kept_and_one_per_key_per_hour(monkeypatch):
    clock = {"t": 1_800_000_000.0}
    monkeypatch.setattr(llm_samples.time, "time", lambda: clock["t"])
    client = _client()
    for i in range(5):
        _run(_tracked_caller(client, max_tokens=100 + i))
        # a second call inside the hour is throttled — never a fourth write for the same hour
        _run(_tracked_caller(client, max_tokens=999))
        clock["t"] += 61 * 60
    samples = _only_file()["samples"]
    assert [s["request"]["max_tokens"] for s in samples] == [102, 103, 104]


def test_the_throttle_survives_a_restart_by_reading_the_file(monkeypatch):
    clock = {"t": 1_800_000_000.0}
    monkeypatch.setattr(llm_samples.time, "time", lambda: clock["t"])
    _run(_tracked_caller(_client()))
    llm_samples.reset_throttle()            # a new process: the in-memory throttle is gone
    clock["t"] += 10 * 60
    _run(_tracked_caller(_client(), max_tokens=555))
    assert len(_only_file()["samples"]) == 1


# ── 2. capture disabled: canary, replay, explicit block ──────────────────────

def test_nothing_is_stored_inside_capture_disabled():
    async def go():
        with llm_samples.capture_disabled():
            await _tracked_caller(_client())
    _run(go())
    assert _files() == []


async def _canary_from_a_tracked_site(client):
    return await llm_client.run_canary(client, "claude-sonnet-5")


def test_the_canary_never_becomes_a_sample(monkeypatch):
    monkeypatch.setitem(llm_call_sites.CALL_SITES, f"{__name__}:_canary_from_a_tracked_site",
                        "THEME_MODEL")
    results = _run(_canary_from_a_tracked_site(_client()))
    assert all(r.ok for r in results)       # the calls really went through the transport
    assert _files() == []


def test_the_replay_never_becomes_a_sample(monkeypatch):
    from agents.market_intelligence import model_resolution as mr
    # Even if the replay's own frame were a mapped call site, its calls must not be recorded.
    monkeypatch.setitem(llm_call_sites.CALL_SITES,
                        "agents.market_intelligence.model_resolution:_replay_once", "THEME_MODEL")
    monkeypatch.setattr(mr, "_replay_client", lambda: _client())
    monkeypatch.setattr(mr, "_log_replay_spend", AsyncMock())
    sample = {"request": {"model": "claude-sonnet-5", "max_tokens": 50,
                          "messages": [{"role": "user", "content": "hi"}]},
              "answer": {"stop_reason": "end_turn", "text": "pong"}, "subject": ""}
    out = _run(mr._replay_entries([("k", "THEME_MODEL", sample)], "claude-sonnet-5-5",
                                  deadline=__import__("time").monotonic() + 60))
    assert [r.verdict for r in out[0].runs] == ["pass"] * mr.REPLAY_RUNS
    assert _files() == []


# ── 3. credential-like → dropped and counted ─────────────────────────────────

def test_a_request_redaction_would_change_is_dropped_and_counted():
    client = _client()
    _run(_tracked_caller(client, messages=[{"role": "user", "content": "url?apikey=SECRET123"}]))
    data = _only_file()
    assert data["samples"] == []
    assert data["skipped"]["credential_like"]["count"] == 1
    assert "SECRET123" not in json.dumps(data)


# ── 4. images and signed thinking ────────────────────────────────────────────

def test_an_image_is_stored_as_a_marker_and_not_replayable():
    png_b64 = "iVBORw0KGgo" + "A" * 400
    content = [{"type": "text", "text": "grade this"},
               {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                            "data": png_b64}}]
    _run(_tracked_caller(_client(), messages=[{"role": "user", "content": content}]))
    s = _only_file()["samples"][0]
    assert s["replayable"] is False and s["unreplayable_reason"] == "image"
    block = s["request"]["messages"][0]["content"][1]
    assert block == {"type": "image", "omitted": True, "media_type": "image/png",
                     "chars": len(png_b64)}
    assert png_b64 not in json.dumps(s)


def test_a_signed_thinking_block_in_history_is_not_replayable():
    history = [{"role": "user", "content": "q"},
               {"role": "assistant", "content": [Block("thinking", thinking="…", signature="sig")]},
               {"role": "user", "content": "go on"}]
    history[1]["content"][0].model_dump = lambda **k: {"type": "thinking", "thinking": "…",
                                                      "signature": "sig"}
    _run(_tracked_caller(_client(), messages=history))
    s = _only_file()["samples"][0]
    assert s["replayable"] is False and s["unreplayable_reason"] == "signed thinking in history"


# ── 5. never stored / never raises ───────────────────────────────────────────

@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refusals_and_truncations_are_not_answers(stop):
    _run(_tracked_caller(_client(FakeMessages(stop=stop))))
    assert _files() == []


def test_operator_chat_is_never_captured(monkeypatch):
    monkeypatch.setitem(llm_call_sites.CALL_SITES, KEY, "ORCHESTRATOR_MODEL")
    _run(_tracked_caller(_client()))
    assert _files() == []


def test_an_unmapped_call_site_is_not_captured():
    async def not_in_the_map(client):
        return await client.messages.create(model="claude-sonnet-5", max_tokens=5,
                                            messages=[{"role": "user", "content": "x"}])
    _run(not_in_the_map(_client()))
    assert _files() == []


def test_an_unwritable_directory_is_silent_and_the_call_still_returns(monkeypatch, tmp_path):
    blocker = tmp_path / "a_file"
    blocker.write_text("not a directory")
    monkeypatch.setenv("APOLLO_LLM_SAMPLE_DIR", str(blocker / "samples"))
    resp = _run(_tracked_caller(_client()))
    assert resp.content[0].text == "pong"


def test_an_unserializable_request_never_breaks_the_call():
    resp = _run(_tracked_caller(_client(), metadata={"obj": object()}))
    assert resp.content[0].text == "pong"
    assert _files() == []


# ── 6. key derivation through the pass-through wrappers ──────────────────────

def test_key_skips_judge_transport_and_grade_holistic(monkeypatch):
    """chart_axis.grade_one → ep_grade_judge.grade_holistic → judge_transport (asyncio.wait_for,
    the nested _call) → the transport. The key must be the REAL production call site."""
    import agents.market_intelligence.db as db
    import agents.market_intelligence.spend_tracker as st
    from agents.market_intelligence import chart_axis
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(st, "log_anthropic_call_safe", AsyncMock())
    key = "agents.market_intelligence.chart_axis:grade_one"
    assert llm_call_sites.CALL_SITES[key] == "JUDGE_MODEL"
    png = b"\x89PNG fake bytes"
    _run(chart_axis.grade_one(_client(), asyncio.Semaphore(1), {"ticker": "ABCD"}, png,
                              "chart note", log_caller="test"))
    data = _only_file()
    assert data["key"] == key and data["role"] == "JUDGE_MODEL"
    assert data["samples"][0]["replayable"] is False          # the chart image


async def _via_assignment_turn(client):
    from agents.market_intelligence import theme_engine
    tool = {"name": "assign_stocks_to_themes", "input_schema": {"type": "object", "properties": {}}}
    return await theme_engine._assignment_turn(
        client, [{"role": "user", "content": "assign"}], tools=[tool],
        tool_choice={"type": "tool", "name": "assign_stocks_to_themes"}, caller="test")


async def _via_create_with_backoff(client):
    from agents.market_intelligence import theme_merge_arm
    return await theme_merge_arm._create_with_backoff(client, "same catalyst?", "claude-sonnet-5", None)


@pytest.mark.parametrize("caller", [_via_assignment_turn, _via_create_with_backoff])
def test_key_skips_the_theme_wrappers(monkeypatch, caller):
    import agents.market_intelligence.spend_tracker as st
    monkeypatch.setattr(st, "log_anthropic_call_safe", AsyncMock())
    key = f"{__name__}:{caller.__name__}"
    monkeypatch.setitem(llm_call_sites.CALL_SITES, key, "THEME_MODEL")
    _run(caller(_client()))
    assert _only_file()["key"] == key
