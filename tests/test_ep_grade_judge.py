"""EP Holistic Grade Judge (#240 / ADR 0011) — schema validation, fail-open, and the
bidirectional verdict plumbing. The judge is load-bearing at Wave 2, so the FAIL-OPEN
contract (None on any error/timeout → caller uses the floor) is the locked invariant.
"""
import asyncio

from agents.market_intelligence.ep_grade_judge import (
    assemble_judge_inputs, grade_holistic, _normalize_verdict, _build_judge_prompt,
)


# ── fake Anthropic async client (tool-use shaped) ────────────────────────────
class _ToolBlock:
    type = "tool_use"

    def __init__(self, inp):
        self.input = inp


class _Resp:
    def __init__(self, inp):
        self.content = [_ToolBlock(inp)]


class _Msgs:
    def __init__(self, inp=None, exc=None, delay=0.0):
        self.inp, self.exc, self.delay, self.calls = inp, exc, delay, 0

    async def create(self, **kw):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return _Resp(self.inp)


class _Client:
    def __init__(self, inp=None, exc=None, delay=0.0):
        self.messages = _Msgs(inp, exc, delay)


def _run(coro):
    return asyncio.run(coro)


_VALID = {
    "grade": "game_changer", "tier": "HIGH", "direction_vs_floor": "promote",
    "materiality_tier": "transformative", "fire_axes": ["catalyst", "theme"],
    "rationale": "Transformative deal vs a micro-cap.", "confidence": 0.9,
}


# ── _normalize_verdict ───────────────────────────────────────────────────────
def test_normalize_valid():
    v = _normalize_verdict(dict(_VALID))
    assert v["grade"] == "game_changer" and v["tier"] == "HIGH"
    assert v["direction_vs_floor"] == "promote"
    assert v["materiality_tier"] == "transformative"
    assert v["fire_axes"] == ["catalyst", "theme"]


def test_normalize_rejects_bad_grade():
    bad = dict(_VALID, grade="amazing")
    assert _normalize_verdict(bad) is None


def test_normalize_rejects_bad_tier_and_direction():
    assert _normalize_verdict(dict(_VALID, tier="MEGA")) is None
    assert _normalize_verdict(dict(_VALID, direction_vs_floor="sideways")) is None


def test_normalize_drops_unknown_materiality_and_axes():
    v = _normalize_verdict(dict(_VALID, materiality_tier="huge", fire_axes=["catalyst", "moon"]))
    assert v["materiality_tier"] is None          # unknown tier → None, not invented
    assert v["fire_axes"] == ["catalyst"]          # unknown axis filtered out


def test_normalize_handles_non_dict():
    assert _normalize_verdict(None) is None
    assert _normalize_verdict("not a dict") is None


# ── grade_holistic: happy path + FAIL-OPEN ───────────────────────────────────
def test_grade_happy_path():
    client = _Client(inp=dict(_VALID))
    v = _run(grade_holistic(client, {"ticker": "NRIX"}))
    assert v["tier"] == "HIGH" and v["direction_vs_floor"] == "promote"
    assert client.messages.calls == 1


def test_grade_demote_verdict_passes_through():
    client = _Client(inp=dict(_VALID, grade="routine", tier="none", direction_vs_floor="demote",
                              materiality_tier="immaterial", fire_axes=[]))
    v = _run(grade_holistic(client, {"ticker": "BIGCO"}))
    assert v["direction_vs_floor"] == "demote" and v["tier"] == "none"


def test_grade_none_client_fails_open():
    assert _run(grade_holistic(None, {"ticker": "X"})) is None


def test_grade_api_error_fails_open():
    client = _Client(exc=RuntimeError("503"))
    assert _run(grade_holistic(client, {"ticker": "X"})) is None


def test_grade_malformed_output_fails_open():
    client = _Client(inp={"grade": "nonsense"})  # missing required + bad enum
    assert _run(grade_holistic(client, {"ticker": "X"})) is None


def test_grade_timeout_fails_open():
    client = _Client(inp=dict(_VALID), delay=0.2)
    assert _run(grade_holistic(client, {"ticker": "X"}, timeout=0.05)) is None


def test_grade_respects_semaphore():
    client = _Client(inp=dict(_VALID))
    sem = asyncio.Semaphore(1)
    v = _run(grade_holistic(client, {"ticker": "X"}, semaphore=sem))
    assert v["tier"] == "HIGH"


# ── assemble_judge_inputs + prompt ───────────────────────────────────────────
def test_assemble_pulls_from_result_dict():
    r = {"ticker": "NRIX", "catalyst": "Q1 beat", "claude_analysis": "strong quarter",
         "in_active_theme": True, "in_narrative_cohort": False, "gap_pct": 12.0,
         "pm_rvol": 4.2, "vol_percentile": 88, "ep_score": 80, "score_tier": "HIGH",
         "catalyst_quality": "game_changer"}
    p = assemble_judge_inputs(r, grounded_text="SEC 8-K ... beat", materiality_tier="material",
                              market_cap=2.0e9, sector="Healthcare", revenue_stage=True,
                              has_direct_source=True)
    assert p["ticker"] == "NRIX"
    assert p["floor_tier"] == "HIGH" and p["floor_catalyst_quality"] == "game_changer"
    assert p["in_active_theme"] is True and p["in_narrative_cohort"] is False
    assert p["materiality_tier"] == "material" and p["has_direct_source"] is True
    assert p["grounded_text"].startswith("SEC 8-K")


def test_assemble_falls_back_to_catalyst_when_no_grounded_text():
    r = {"ticker": "X", "catalyst": "some catalyst text"}
    p = assemble_judge_inputs(r)
    assert p["grounded_text"] == "some catalyst text"


def test_prompt_includes_floor_and_corpus():
    p = assemble_judge_inputs({"ticker": "NRIX", "score_tier": "HIGH", "catalyst": "deal"},
                              grounded_text="SEC body text", market_cap=1.0e8)
    prompt = _build_judge_prompt(p)
    assert "NRIX" in prompt and "Floor grade" in prompt and "SEC body text" in prompt
    assert "$100M" in prompt  # market cap formatted into the materiality context
