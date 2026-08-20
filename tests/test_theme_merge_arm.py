"""ADR 0025 Arm B (#274) — Stage A pure pairing + Stage B adjudicator pins (C2).

Covers the C2 card's test list: family assignment · anchor pairing + the one-side-<4 /
family-≥3 gate · never-pair-two-established · cooldown-respected · sub-theme guard ·
nightly pair cap — plus the toggle, the pair-key normalization, and the Stage-B
adjudicator hardening pins (temp=0 / forced tool_choice / scratchpad-first schema /
parse-retry-then-ERROR).
"""
from __future__ import annotations

import asyncio

import pytest

from agents.market_intelligence import theme_merge_arm as arm


def _t(name, n, parent=None, tickers=None, score=0):
    return {
        "name": name,
        "tickers": tickers if tickers is not None else [f"{name[:3].upper()}{i}" for i in range(n)],
        "parent_theme": parent,
        "score": score,
        "description": f"{name} description",
    }


# ── toggle ───────────────────────────────────────────────────────────────────

def test_merge_arm_default_off(monkeypatch):
    monkeypatch.delenv("THEME_MERGE_ARM", raising=False)
    assert arm.merge_arm_enabled() is False


@pytest.mark.parametrize("val,expect", [
    ("1", True), ("true", True), ("ON", True), ("yes", True),
    ("0", False), ("false", False), ("", False), ("off", False),
])
def test_merge_arm_toggle_values(monkeypatch, val, expect):
    monkeypatch.setenv("THEME_MERGE_ARM", val)
    assert arm.merge_arm_enabled() is expect


# ── Stage A: families ────────────────────────────────────────────────────────

def test_family_of_stems():
    assert arm.family_of("Property & Casualty Insurance Underwriters") == "insurance"
    assert arm.family_of("Multifamily Apartment REITs") == "reit"
    assert arm.family_of("Pure-Play Quantum Computing Hardware") == "quantum"
    assert arm.family_of("Totally Unrelated Consumer Theme") is None


def test_pair_key_normalized():
    assert arm.pair_key("B Theme", "A Theme") == ("A Theme", "B Theme")
    assert arm.pair_key("A Theme", "B Theme") == arm.pair_key("B Theme", "A Theme")


# ── Stage A: pairing gates ───────────────────────────────────────────────────

def test_anchor_pairing_family_of_three():
    """A ≥3-theme family pairs every theme against the anchor (largest)."""
    themes = [
        _t("Quantum Hardware Leaders", 6),
        _t("Quantum Annealing Systems", 4),
        _t("Quantum Networking", 2),
    ]
    pairs = arm.propose_merge_pairs(themes)
    assert [(a["name"], o["name"]) for a, o in pairs] == [
        ("Quantum Hardware Leaders", "Quantum Annealing Systems"),
        ("Quantum Hardware Leaders", "Quantum Networking"),
    ]


def test_never_pair_two_established_in_two_theme_family():
    """ADR gate 2: two ≥4-member themes in a 2-theme family are NEVER auto-paired
    (a legitimate parallel pair, not a flood)."""
    themes = [_t("Quantum Hardware Leaders", 6), _t("Quantum Annealing Systems", 4)]
    assert arm.propose_merge_pairs(themes) == []


def test_small_side_pairs_in_two_theme_family():
    """One side <4 members → paired even in a 2-theme family."""
    themes = [_t("Quantum Hardware Leaders", 6), _t("Quantum Networking", 2)]
    pairs = arm.propose_merge_pairs(themes)
    assert [(a["name"], o["name"]) for a, o in pairs] == [
        ("Quantum Hardware Leaders", "Quantum Networking"),
    ]


def test_cooldown_pairs_respected():
    """A live merge_distinct cooldown suppresses re-adjudication of the pair."""
    themes = [
        _t("Quantum Hardware Leaders", 6),
        _t("Quantum Annealing Systems", 4),
        _t("Quantum Networking", 2),
    ]
    cd = {arm.pair_key("Quantum Hardware Leaders", "Quantum Networking")}
    pairs = arm.propose_merge_pairs(themes, cooldown_pairs=cd)
    assert [(a["name"], o["name"]) for a, o in pairs] == [
        ("Quantum Hardware Leaders", "Quantum Annealing Systems"),
    ]


def test_subtheme_never_paired_with_parent():
    """ADR gate 3: parent/sub coexistence stays — never pair a child with its parent."""
    themes = [
        _t("Quantum Hardware Leaders", 6),
        _t("Quantum Networking", 2, parent="Quantum Hardware Leaders"),
        _t("Quantum Annealing Systems", 2),
    ]
    pairs = arm.propose_merge_pairs(themes)
    assert [(a["name"], o["name"]) for a, o in pairs] == [
        ("Quantum Hardware Leaders", "Quantum Annealing Systems"),
    ]


def test_nightly_pair_cap_and_uncapped_replay_mode():
    """≤8 pairs per night (ADR cap); max_pairs=None returns the full replay map."""
    themes = [_t("Quantum Anchor Theme", 10)] + [_t(f"Quantum Sub {i:02d}", 2) for i in range(10)]
    assert len(arm.propose_merge_pairs(themes)) == arm.MAX_PAIRS_PER_NIGHT == 8
    assert len(arm.propose_merge_pairs(themes, max_pairs=None)) == 10


def test_sector_fallback_family_for_stemless_themes():
    """Stem-less themes with a strict majority-member sector form a sector:: family;
    stem families keep pair-budget priority."""
    sectors = {"AAA0": "Utilities", "AAA1": "Utilities", "BBB0": "Utilities", "BBB1": "Utilities",
               "BBB2": "Utilities"}
    themes = [
        _t("Grid Modernization Leaders", 2, tickers=["AAA0", "AAA1"]),
        _t("Power Producers Momentum", 3, tickers=["BBB0", "BBB1", "BBB2"]),
        # stem family too — should come FIRST in the pair list
        _t("Quantum Hardware Leaders", 6),
        _t("Quantum Networking", 2),
    ]
    pairs = arm.propose_merge_pairs(themes, sectors_by_ticker=sectors)
    names = [(a["name"], o["name"]) for a, o in pairs]
    assert names[0] == ("Quantum Hardware Leaders", "Quantum Networking")   # stems first
    assert ("Power Producers Momentum", "Grid Modernization Leaders") in names


def test_sector_fallback_requires_strict_majority():
    """Half-unknown memberships never form a sector family (fail-quiet)."""
    sectors = {"AAA0": "Utilities"}  # 1 of 3 known
    themes = [
        _t("Grid Modernization Leaders", 3, tickers=["AAA0", "AAA1", "AAA2"]),
        _t("Power Producers Momentum", 2, tickers=["BBB0", "BBB1"]),
    ]
    assert arm.propose_merge_pairs(themes, sectors_by_ticker=sectors) == []


# ── Stage B: adjudicator pins ────────────────────────────────────────────────

def test_tool_schema_scratchpad_first_required():
    """House discipline: analysis_scratchpad is the FIRST required field."""
    required = arm.MERGE_ADJUDICATION_TOOL["input_schema"]["required"]
    assert required[0] == "analysis_scratchpad"
    assert "verdict" in required
    props = arm.MERGE_ADJUDICATION_TOOL["input_schema"]["properties"]
    assert props["verdict"]["enum"] == ["MERGE", "DISTINCT", "PARENT_CHILD"]


def test_prompt_carries_negative_exemplars():
    """The ADR's load-bearing anchors must stay in the prompt verbatim-ish."""
    p = arm.ADJUDICATION_PROMPT
    assert "specialty-catastrophe" in p
    assert "multifamily/apartment REITs" in p
    assert "NOT a shared sector label" in p


class _ToolBlock:
    type = "tool_use"

    def __init__(self, data):
        self.input = data


class _Resp:
    def __init__(self, blocks):
        self.content = blocks
        self.usage = None


class _FakeClient:
    """Captures create kwargs; returns queued responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

        outer = self

        class _Messages:
            async def create(self, **kw):
                outer.calls.append(kw)
                return outer._responses.pop(0)

        self.messages = _Messages()


def test_adjudicate_happy_path_pins_tool_choice_and_passes_no_temperature():
    client = _FakeClient([_Resp([_ToolBlock({
        "analysis_scratchpad": "same driver", "verdict": "MERGE",
        "driver_a": "x", "driver_b": "x", "reason": "same trade",
        "merged_name": "Unified Theme",
    })])])
    v = asyncio.run(arm.adjudicate_merge_pair(
        {"name": "A", "description": "a"}, {"name": "B", "description": "b"}, client=client))
    assert v["verdict"] == "MERGE"
    assert v["merged_name"] == "Unified Theme"
    kw = client.calls[0]
    # 2026-08-20: `temperature` was the C4 caveat's determinism leg, but the
    # anthropic 1.0 SDK REMOVED it from messages.create and carries no **kwargs,
    # so passing it raised TypeError on every call and the arm returned
    # verdict=ERROR for 100% of pairs. Asserting its ABSENCE is what keeps a
    # well-meaning revert from killing the arm again.
    assert "temperature" not in kw, "anthropic 1.0 rejects temperature — see arm docstring"
    # The remaining two hardening legs now carry the C4 load alone; pin them hard.
    assert kw["tool_choice"] == {"type": "tool", "name": "adjudicate_theme_merge"}
    assert kw["tools"] == [arm.MERGE_ADJUDICATION_TOOL]


def test_adjudicate_retries_parse_failure_then_errors():
    """Missing/invalid tool verdict → ONE retry, then a non-raising ERROR verdict."""
    client = _FakeClient([
        _Resp([]),                                       # no tool block
        _Resp([_ToolBlock({"verdict": "MAYBE"})]),        # invalid verdict
    ])
    v = asyncio.run(arm.adjudicate_merge_pair(
        {"name": "A", "description": "a"}, {"name": "B", "description": "b"}, client=client))
    assert v["verdict"] == "ERROR"
    assert len(client.calls) == 2                        # exactly one retry


def test_adjudicate_recovers_on_retry():
    client = _FakeClient([
        _Resp([]),
        _Resp([_ToolBlock({"analysis_scratchpad": "s", "verdict": "DISTINCT",
                           "driver_a": "a", "driver_b": "b", "reason": "r"})]),
    ])
    v = asyncio.run(arm.adjudicate_merge_pair(
        {"name": "A", "description": "a"}, {"name": "B", "description": "b"}, client=client))
    assert v["verdict"] == "DISTINCT"


def test_member_lines_included_when_present_and_omitted_for_corpus_pairs():
    with_members = arm.build_adjudication_prompt(
        {"name": "A", "description": "a", "tickers": ["NVDA", "AMD"]},
        {"name": "B", "description": "b"},
        sectors_by_ticker={"NVDA": "Technology"},
    )
    assert "Members: NVDA (Technology), AMD" in with_members
    corpus_style = arm.build_adjudication_prompt(
        {"name": "A", "description": "a"}, {"name": "B", "description": "b"})
    assert "Members:" not in corpus_style
