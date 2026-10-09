"""#693 — scripts/probes/_693/measure_thinking_off.py, the A-vs-B measurement the operator pipes into
the prod container. It cannot be dry-run against the real API from here, so this pins everything
around the call: which requests it picks, that variant A is today's drop + headroom and variant B
is `between_tools` with max_tokens unchanged, that the cost estimate is printed and enforced
BEFORE any call, and that a refusal or a bad answer is counted as not parsed.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
from types import SimpleNamespace

import pytest

from agents.market_intelligence.theme_merge_arm import CONTAINMENT_ADJUDICATION_TOOL
from shared import llm_samples
from shared.llm_client import thinking_headroom

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "probes" / "_693" / "measure_thinking_off.py"
PARENT_KEY = "agents.market_intelligence.theme_merge_arm:adjudicate_containment_pair"
VALIDATION_KEY = "agents.market_intelligence.theme_engine:_validate_theme_membership"
ECO_KEY = "agents.market_intelligence.ecosystem_discovery:propose_ecosystem_via_llm"
M55 = "claude-sonnet-5-5"
DISABLED = {"type": "disabled"}


def _load():
    spec = importlib.util.spec_from_file_location("measure_693", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(dirpath, key, role, request, captured="2026-10-01T20:00:00+00:00", answer=None):
    data = {"schema": 1, "key": key, "role": role, "skipped": {}, "samples": [{
        "captured_at": captured, "model": M55, "role": role, "replayable": True,
        "request": request, "answer": answer or {}, "subject": ""}]}
    llm_samples._file_for(key, dirpath).write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def samples(tmp_path, monkeypatch):
    d = tmp_path / "samples"
    d.mkdir()
    monkeypatch.setenv("APOLLO_LLM_SAMPLE_DIR", str(d))
    # theme_validation left the registry 2026-10-09 (#693 replay); this probe's behaviour is pinned on
    # the two-job registry it measured on 10-02, so the fixture restores that membership.
    from shared import llm_thinking
    monkeypatch.setattr(llm_thinking, "THINKING_DISABLED",
                        frozenset(llm_thinking.THINKING_DISABLED | {"theme_validation"}))
    _write(d, PARENT_KEY, "THEME_PARENT_ADJUDICATION_MODEL", {
        "model": M55, "max_tokens": 1000, "thinking": DISABLED,
        "tools": [CONTAINMENT_ADJUDICATION_TOOL],
        "tool_choice": {"type": "tool", "name": CONTAINMENT_ADJUDICATION_TOOL["name"]},
        "messages": [{"role": "user", "content": "CANDIDATE CHILD: a\nCANDIDATE PARENT: b"}]})
    _write(d, VALIDATION_KEY, "THEME_MODEL", {
        "model": M55, "max_tokens": 1000, "thinking": DISABLED,
        "system": "You are a JSON API.", "messages": [{"role": "user", "content": "validate"}]})
    # captured with thinking off but NOT a registry job: listed, not measured by default
    _write(d, ECO_KEY, "SYNTHESIS_MODEL", {
        "model": M55, "max_tokens": 2000, "thinking": DISABLED,
        "messages": [{"role": "user", "content": "propose"}]})
    return d


def _resp(text, out_tokens=40, stop="end_turn", thinking=0):
    blocks = [SimpleNamespace(type="thinking", thinking="") for _ in range(thinking)]
    blocks.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(content=blocks, stop_reason=stop, model=M55,
                           usage=SimpleNamespace(input_tokens=1200, output_tokens=out_tokens))


class FakeClient:
    def __init__(self, reply):
        self.calls, self._reply = [], reply
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return self._reply(kw)


def _good_reply(kw):
    """What 5.5 returns: structured-output JSON for the forced job, a JSON object for validation.
    A (no thinking param) comes back WITH thinking blocks and more output tokens; B without."""
    thinks = 0 if kw.get("thinking") == {"type": "between_tools"} else 2
    toks = 90 if thinks == 0 else 400
    if "output_config" in kw:
        return _resp(json.dumps({"verdict": "PEERS", "reason": "r", "analysis_scratchpad": "n"}), toks, thinking=thinks)
    return _resp('{"remove": []}', toks, thinking=thinks)


def _run(argv, client=None):
    mod = _load()
    lines: list[str] = []
    code = mod.run(argv, client=client, out=lines.append)
    return code, "\n".join(lines)


def test_dry_run_prints_the_plan_and_the_estimate_and_calls_nothing(samples):
    code, text = _run(["--dry-run", "--model", M55], FakeClient(_good_reply))
    assert code == 0
    assert "CALLS: 4" in text and "WORST-CASE COST: $" in text
    assert "dry run - nothing called" in text
    assert "theme_parent_adjudication" in text and "theme_validation" in text
    # the third captured disabled-thinking site is surfaced, not silently measured
    assert "propose_ecosystem_via_llm" in text and "--include-others" in text


def test_variant_a_is_todays_drop_plus_headroom_and_b_is_between_tools_unchanged(samples):
    client = FakeClient(_good_reply)
    code, text = _run(["--model", M55], client)
    assert code == 0 and len(client.calls) == 4
    by = {}
    for kw in client.calls:
        job = "parent" if "output_config" in kw else "validation"
        var = "B" if kw.get("thinking") == {"type": "between_tools"} else "A"
        by[(job, var)] = kw
    assert set(by) == {("parent", "A"), ("parent", "B"), ("validation", "A"), ("validation", "B")}
    for job in ("parent", "validation"):
        a, b = by[(job, "A")], by[(job, "B")]
        assert "thinking" not in a and a["max_tokens"] == thinking_headroom(1000) == 2024     # today
        assert b["thinking"] == {"type": "between_tools"} and b["max_tokens"] == 1000          # the fix
        assert a["model"] == b["model"] == M55
    # forced tool: both variants go as structured output (5.5 rejects a forced tool_choice)
    for var in ("A", "B"):
        kw = by[("parent", var)]
        assert "tools" not in kw and "tool_choice" not in kw
        assert kw["output_config"]["format"]["type"] == "json_schema"
    assert by[("validation", "A")]["system"] == "You are a JSON API."
    # the table the operator reads
    assert "B-A=" in text and "parsed A=1/1 B=1/1" in text
    assert "B vs A output tokens: -620 (-78%)" in text      # (90+90) - (400+400)
    assert "RESULT_JSON " in text
    parsed = json.loads(text.split("RESULT_JSON ", 1)[1])
    assert parsed["totals"]["A"]["calls"] == 2 and parsed["totals"]["B"]["out_tokens"] == 180


def test_the_estimate_is_enforced_before_any_call(samples):
    client = FakeClient(_good_reply)
    code, text = _run(["--model", M55, "--max-usd", "0.0000001"], client)
    assert code == 3 and client.calls == []
    assert "ABORT: worst case" in text and "Nothing was spent" in text


def test_a_job_bound_to_another_model_aborts_before_any_spend(samples):
    client = FakeClient(_good_reply)
    code, text = _run([], client)     # no --model: the test env binds THEME_MODEL to a pre-5.5 id
    assert code == 3 and client.calls == []
    assert "between_tools exists only on claude-sonnet-5-5" in text


def test_xhigh_effort_skips_variant_b_because_it_would_be_a_400(samples):
    _write(samples, VALIDATION_KEY, "THEME_MODEL", {
        "model": M55, "max_tokens": 1000, "thinking": DISABLED, "output_config": {"effort": "xhigh"},
        "messages": [{"role": "user", "content": "validate"}]})
    client = FakeClient(_good_reply)
    code, text = _run(["--model", M55], client)
    assert code == 0 and len(client.calls) == 3
    assert not any(kw.get("thinking") == {"type": "between_tools"} and kw.get("output_config", {}).get("effort") == "xhigh"
                   for kw in client.calls)
    assert "n/a (effort xhigh)" in text


def test_a_refusal_or_a_missing_field_is_counted_as_not_parsed(samples, monkeypatch):
    # The script runs in the prod container BEFORE this branch deploys: it may use nothing that
    # only exists here. refusal_category was added to shared.llm_response by #693 — take it away.
    from shared import llm_response
    monkeypatch.delattr(llm_response, "refusal_category")

    def reply(kw):
        if kw.get("thinking") == {"type": "between_tools"}:
            if "output_config" in kw:
                r = _resp("", 0, stop="refusal")
                r.stop_details = SimpleNamespace(type="refusal", category="reasoning_extraction")
                return r
            return _resp("not json at all")
        if "output_config" in kw:
            return _resp(json.dumps({"verdict": "PEERS"}))            # required fields missing
        return _resp('{"remove": []}')
    code, text = _run(["--model", M55], FakeClient(reply))
    assert code == 0
    assert "refusal (reasoning_extraction)" in text
    assert "not JSON" in text and "missing reason,analysis_scratchpad" in text
    assert "parsed=1/2" in text or "parsed=0/2" in text


def test_an_api_error_is_a_result_not_a_crash(samples):
    def reply(kw):
        raise RuntimeError("HTTP 400 boom")
    code, text = _run(["--model", M55], FakeClient(reply))
    assert code == 0 and "RuntimeError: HTTP 400 boom" in text and "errors=2" in text


def test_include_others_adds_the_unregistered_disabled_site(samples):
    client = FakeClient(_good_reply)
    code, _ = _run(["--model", M55, "--include-others"], client)
    assert code == 0 and len(client.calls) == 6
