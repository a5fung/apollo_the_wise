"""EP Holistic Grade Judge (#240 / ADR 0011) — schema validation, fail-open, and the
bidirectional verdict plumbing. The judge is load-bearing at Wave 2, so the FAIL-OPEN
contract (None on any error/timeout → caller uses the floor) is the locked invariant.
"""
import asyncio

from agents.market_intelligence.ep_grade_judge import (
    assemble_judge_inputs, grade_holistic, _normalize_verdict, _build_judge_prompt,
    _judge_tool, _JUDGE_TOOL,
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


def test_normalize_omitted_axes_stay_none_not_empty():
    # OMITTED fire_axes (despite the schema's required) must NOT become [] —
    # [] persists as '{}' = "judge saw no fire", a different claim entirely.
    omitted = {k: v for k, v in _VALID.items() if k != "fire_axes"}
    v = _normalize_verdict(omitted)
    assert v is not None and v["fire_axes"] is None
    # Explicit empty list stays an explicit no-fire verdict.
    assert _normalize_verdict(dict(_VALID, fire_axes=[]))["fire_axes"] == []


# ── grade_holistic: happy path + FAIL-OPEN ───────────────────────────────────
def test_grade_happy_path():
    client = _Client(inp=dict(_VALID))
    v = _run(grade_holistic(client, {"ticker": "NRIX"}, log_caller="ep_grade_judge"))
    assert v["tier"] == "HIGH" and v["direction_vs_floor"] == "promote"
    assert client.messages.calls == 1


def test_grade_demote_verdict_passes_through():
    client = _Client(inp=dict(_VALID, grade="routine", tier="none", direction_vs_floor="demote",
                              materiality_tier="immaterial", fire_axes=[]))
    v = _run(grade_holistic(client, {"ticker": "BIGCO"}, log_caller="ep_grade_judge"))
    assert v["direction_vs_floor"] == "demote" and v["tier"] == "none"


def test_grade_none_client_fails_open():
    assert _run(grade_holistic(None, {"ticker": "X"}, log_caller="ep_grade_judge")) is None


def test_grade_api_error_fails_open():
    client = _Client(exc=RuntimeError("503"))
    assert _run(grade_holistic(client, {"ticker": "X"}, log_caller="ep_grade_judge")) is None


def test_grade_malformed_output_fails_open():
    client = _Client(inp={"grade": "nonsense"})  # missing required + bad enum
    assert _run(grade_holistic(client, {"ticker": "X"}, log_caller="ep_grade_judge")) is None


def test_grade_timeout_fails_open():
    client = _Client(inp=dict(_VALID), delay=0.2)
    assert _run(grade_holistic(client, {"ticker": "X"}, timeout=0.05, log_caller="ep_grade_judge")) is None


def test_grade_respects_semaphore():
    client = _Client(inp=dict(_VALID))
    sem = asyncio.Semaphore(1)
    v = _run(grade_holistic(client, {"ticker": "X"}, semaphore=sem, log_caller="ep_grade_judge"))
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


def test_prompt_frames_materiality_as_deterministic_ratio():
    # W4 (#245): when a deterministic deal/cap tier is fed, the prompt presents it as an
    # EXACT computation (so the judge weights it), not a soft pre-pass opinion.
    p = assemble_judge_inputs({"ticker": "RUM"}, materiality_tier="material", market_cap=2.5e9)
    prompt = _build_judge_prompt(p)
    assert "deterministic ratio" in prompt and "material" in prompt


def test_prompt_invites_judge_to_decide_materiality_when_no_ratio():
    # None ratio (no parseable deal value) → the judge owns the materiality call.
    p = assemble_judge_inputs({"ticker": "X"}, materiality_tier=None)
    prompt = _build_judge_prompt(p)
    assert "judge materiality yourself" in prompt


# ── Lane-2 active narratives → theme axis (plan lane2-judge-theme-axis) ──────
_R_BASE = {"ticker": "RCAT", "score_tier": "HIGH", "catalyst_quality": "strong",
           "catalyst": "Japan MoD drone contract", "claude_analysis": "note",
           "in_active_theme": False, "in_narrative_cohort": False,
           "gap_pct": 18.0, "pm_rvol": 6.0, "vol_percentile": 99, "ep_score": 80}

_DRONE_COHORT = {"run_date": "2026-05-26", "name": "Defense drone and UAS expansion",
                 "tickers": ["RDW", "ASPI"], "thesis": "Gov't drone funding wave"}


def test_payload_carries_trimmed_narratives():
    p = assemble_judge_inputs(dict(_R_BASE), active_narratives=[_DRONE_COHORT] * 9)
    assert len(p["active_narratives"]) == 5  # capped
    c = p["active_narratives"][0]
    assert c["name"] == "Defense drone and UAS expansion"
    assert c["tickers"] == ["RDW", "ASPI"]


def test_prompt_byte_identical_when_no_narratives():
    # Shipping this change is behavior-neutral until cohorts are passed in.
    p_none = assemble_judge_inputs(dict(_R_BASE))
    p_empty = assemble_judge_inputs(dict(_R_BASE), active_narratives=[])
    assert _build_judge_prompt(p_none) == _build_judge_prompt(p_empty)
    legacy = dict(p_none)
    legacy.pop("active_narratives")
    assert _build_judge_prompt(legacy) == _build_judge_prompt(p_none)


def test_prompt_renders_narratives_and_join_instruction():
    p = assemble_judge_inputs(dict(_R_BASE), active_narratives=[_DRONE_COHORT])
    prompt = _build_judge_prompt(p)
    assert "ACTIVE NARRATIVE COHORTS" in prompt
    assert '"Defense drone and UAS expansion" (RDW, ASPI)' in prompt
    # The Gap-B instruction: new joiners light the axis without set membership.
    assert "EVEN IF this ticker is not listed as a cohort member" in prompt
    # Boolean stays for telemetry continuity and still renders.
    assert "In narrative cohort (Lane 2): no" in prompt


def test_narrative_fields_truncated():
    fat = {"run_date": "2026-06-01", "name": "N" * 200, "tickers": [f"T{i}" for i in range(30)],
           "thesis": "x" * 999}
    p = assemble_judge_inputs(dict(_R_BASE), active_narratives=[fat])
    c = p["active_narratives"][0]
    assert len(c["name"]) == 80 and len(c["tickers"]) == 12 and len(c["thesis"]) == 200


# ── v2.0-P2 / #299 tape-feature payload (STRUCTURE only — wire-in is eval-gated) ──
_TAPE = {"opening_range_atr": 0.41, "pm_vol_curve": "front-loaded, 2.3x baseline by 9:30",
         "liquidity": "tight spread, $80M/day"}


def test_payload_carries_tape_passthrough():
    assert assemble_judge_inputs(dict(_R_BASE), tape=_TAPE)["tape"] == _TAPE
    assert assemble_judge_inputs(dict(_R_BASE))["tape"] is None


def test_prompt_byte_identical_when_no_tape():
    # Behavior-neutral: shipping the structure does NOT change the load-bearing judge
    # until the scan passes a tape dict (eval-gated wire-in).
    p_none = assemble_judge_inputs(dict(_R_BASE))
    legacy = dict(p_none)
    legacy.pop("tape")
    assert _build_judge_prompt(legacy) == _build_judge_prompt(p_none)


def test_prompt_renders_tape_when_present():
    prompt = _build_judge_prompt(assemble_judge_inputs(dict(_R_BASE), tape=_TAPE))
    assert "TAPE / INTRADAY CHARACTER" in prompt
    assert "0.41" in prompt and "front-loaded, 2.3x baseline by 9:30" in prompt
    assert "violent open" in prompt  # the OR-vs-ATR guidance the judge weighs


# ── #329 Path A — theme HEAT into the payload (byte-identical when absent) ───
def test_payload_carries_theme_heat():
    p = assemble_judge_inputs(dict(_R_BASE), theme_stage="Accelerating", theme_score=92.0)
    assert p["theme_stage"] == "Accelerating" and p["theme_score"] == 92.0


def test_prompt_byte_identical_when_no_theme_heat():
    # Behavior-neutral: the theme-heat plumbing does NOT change the live judge until the scan
    # passes theme_stage in (eval arm + #335 flip — the judge is load-bearing).
    p_none = assemble_judge_inputs(dict(_R_BASE))
    p_explicit_none = assemble_judge_inputs(dict(_R_BASE), theme_stage=None, theme_score=None)
    assert _build_judge_prompt(p_none) == _build_judge_prompt(p_explicit_none)
    legacy = dict(p_none)
    legacy.pop("theme_stage")
    legacy.pop("theme_score")
    assert _build_judge_prompt(legacy) == _build_judge_prompt(p_none)


def test_prompt_renders_theme_heat_when_present():
    p = assemble_judge_inputs(dict(_R_BASE, in_active_theme=True),
                              theme_stage="Accelerating", theme_score=92.0)
    prompt = _build_judge_prompt(p)
    assert "In active theme (Lane 1): yes (stage Accelerating, score 92)" in prompt


def test_prompt_theme_heat_without_score():
    p = assemble_judge_inputs(dict(_R_BASE, in_active_theme=True), theme_stage="Fading")
    assert "(stage Fading)" in _build_judge_prompt(p)


# ── #329 Path A — axis_reads diagnostic (eval-only; live tool byte-identical) ─
def test_judge_tool_byte_identical_when_axis_reads_off():
    assert _judge_tool(False) is _JUDGE_TOOL  # same object → live tool def unchanged
    assert "axis_reads" not in _JUDGE_TOOL["input_schema"]["properties"]


def test_judge_tool_adds_axis_reads_when_on():
    tool = _judge_tool(True)
    assert "axis_reads" in tool["input_schema"]["properties"]
    # Still NOT required → fail-open (a model omission never fails the verdict).
    assert "axis_reads" not in tool["input_schema"]["required"]
    # The base tool was NOT mutated by the deepcopy variant.
    assert "axis_reads" not in _JUDGE_TOOL["input_schema"]["properties"]


def test_normalize_passes_axis_reads_through():
    reads = [{"axis": "theme", "lit": True, "direction": "promote", "note": "hot cohort"}]
    v = _normalize_verdict(dict(_VALID, axis_reads=reads))
    assert v["axis_reads"] == reads
    assert _normalize_verdict(dict(_VALID))["axis_reads"] is None      # absent → None, not fabricated
    assert _normalize_verdict(dict(_VALID, axis_reads="nope"))["axis_reads"] is None  # non-list ignored


def test_grade_holistic_preserves_axis_reads():
    reads = [{"axis": "structure", "lit": False, "direction": "hold", "note": "extended"}]
    client = _Client(inp=dict(_VALID, axis_reads=reads))
    v = _run(grade_holistic(client, {"ticker": "X"}, include_axis_reads=True, log_caller="ep_grade_judge"))
    assert v["axis_reads"] == reads


# ─── #332 (ADR 0028 C1) — setup_class rides the payload, NEVER the prompt (THE LINE) ───────

def test_payload_carries_setup_class_passthrough():
    p = assemble_judge_inputs(dict(_R_BASE), setup_class="pradeep_explosive")
    assert p["setup_class"] == "pradeep_explosive"
    assert assemble_judge_inputs(dict(_R_BASE))["setup_class"] is None


def test_prompt_byte_identical_regardless_of_setup_class():
    """P0 hard guarantee: unlike theme_stage/tape (byte-identical only when ABSENT), setup_class
    must NEVER change the rendered prompt even when PRESENT — the classifier is visibility-only
    and must be structurally incapable of moving the judge's verdict in P0."""
    p_none = assemble_judge_inputs(dict(_R_BASE))
    p_pradeep = assemble_judge_inputs(dict(_R_BASE), setup_class="pradeep_explosive")
    p_mature = assemble_judge_inputs(dict(_R_BASE), setup_class="mature_leader")
    p_unclassified = assemble_judge_inputs(dict(_R_BASE), setup_class="unclassified")
    prompt_none = _build_judge_prompt(p_none)
    assert _build_judge_prompt(p_pradeep) == prompt_none
    assert _build_judge_prompt(p_mature) == prompt_none
    assert _build_judge_prompt(p_unclassified) == prompt_none
    legacy = dict(p_none)
    legacy.pop("setup_class")
    assert _build_judge_prompt(legacy) == prompt_none


def test_build_judge_prompt_source_never_references_setup_class():
    """Static pin, cheap and durable against refactors: the prompt builder must never even
    reference the key, so a future edit can't accidentally start rendering it."""
    import inspect
    src = inspect.getsource(_build_judge_prompt)
    assert "setup_class" not in src
