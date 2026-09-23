"""Every caller of the exit-rule lookup names the strategy it is pricing (2026-09-22).

Since the 2026-09-06 per-strategy flip (#545) a date alone no longer names an exit bracket:
`exit_rules_as_of(d)` / `exit_era_label(d)` without a `signal_type` return the GLOBAL stack, which
MAGNA53 left that day. Two shadow lanes that exist to price declined MAGNA53 candidates under
"the CURRENT-era MAGNA53 bracket" (their own words) kept calling without one and walked 95 rows
(85 settled; 37 sustain-reject, 58 gap-near-miss) under the retired +2R-partial stack for two
weeks — nothing failed, the rows were simply priced under a rule nobody trades. And the stamp was
only half of it: all three lanes also pinned a +2R partial and never passed the breakeven arm, so
fixing the stamp alone would have written era D labels on era C walks.

The populations are DERIVED (one AST pass over every production package), never hand-listed, so a
new caller is covered the day it is written — and the members that must be in them are named.
"""
from __future__ import annotations

import ast
from datetime import date
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGES = ("agents", "shared", "broker", "channels", "core", "scripts")
LOOKUPS = {"exit_rules_as_of", "exit_era_label"}
LANES = ("agents/market_intelligence/gap_near_miss_replay.py",
         "agents/market_intelligence/sustain_reject_replay.py",
         "agents/market_intelligence/lowcap_lane_replay.py")


@lru_cache(maxsize=None)
def _calls() -> tuple[tuple[str, int, str, ast.Call], ...]:
    """(file, line, callee name, node) for every call in every production module — one parse."""
    found = []
    for pkg in PACKAGES:
        root = REPO / pkg
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            rel = str(path.relative_to(REPO))
            for node in ast.walk(ast.parse(path.read_text(), filename=rel)):
                if isinstance(node, ast.Call):
                    fn = node.func
                    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                    found.append((rel, node.lineno, name, node))
    return tuple(found)


def _calls_to(*names: str) -> list[tuple[str, int, ast.Call]]:
    return [(f, ln, c) for f, ln, n, c in _calls() if n in names]


def test_the_populations_are_real():
    """Name the members rather than floor the count — a floor cannot catch a walk that goes
    blind to a package (the 09-20 lesson)."""
    lookup_files = {f for f, _, _ in _calls_to(*LOOKUPS)}
    walk_files = {f for f, _, _ in _calls_to("walk_arm")}
    assert set(LANES) | {"agents/market_intelligence/system_review.py"} <= lookup_files
    assert set(LANES) | {"agents/market_intelligence/live_fill_counterfactuals.py"} <= walk_files


def test_every_exit_rule_lookup_names_its_strategy():
    bare = [f"{f}:{ln}" for f, ln, c in _calls_to(*LOOKUPS)
            if not (len(c.args) >= 2 or any(k.arg == "signal_type" for k in c.keywords))]
    assert not bare, (
        "exit-rule lookup without a signal_type — since 2026-09-06 that silently returns the "
        "GLOBAL stack, not the bracket the strategy trades:\n  " + "\n  ".join(bare))


def test_every_walk_passes_a_breakeven_arm_or_a_derived_stack():
    """A walk either passes `breakeven_at_r` itself or unpacks the kwargs `stack_walk_inputs`
    derived from the stamped stack — never neither, which is how the lanes walked +2R under an
    era D stamp."""
    bad = [f"{f}:{ln}" for f, ln, c in _calls_to("walk_arm")
           if not any(k.arg == "breakeven_at_r" or k.arg is None for k in c.keywords)]
    assert not bad, "walk_arm with no breakeven arm and no derived stack:\n  " + "\n  ".join(bad)


def test_the_lanes_stamp_and_walk_magna53s_current_stack():
    """Wiring: each lane looks up the "magna53" stack for both the stamp and the walk inputs.
    The walk semantics are exercised directly below and in test_624's era D walks."""
    for lane in LANES:
        lookups = [c for f, _, c in _calls_to(*LOOKUPS) if f == lane]
        assert [getattr(c.args[1], "value", None) for c in lookups] == ["magna53", "magna53"], lane
        derived = [c for f, _, c in _calls_to("stack_walk_inputs") if f == lane]
        assert len(derived) == 1 and getattr(derived[0].args[0], "id", None) == "replay_exit_rules", lane


def test_stack_walk_inputs_walks_the_stack_it_is_given():
    """Behaviour: era D gives an 8R target and the +3R arm in the ORB frame; the global stack
    gives the old 2R target and no arm. No ORB frame -> no target and no frame, never a guess."""
    from agents.market_intelligence.live_fill_counterfactuals import stack_walk_inputs
    from agents.market_intelligence.rule_eras import exit_rules_as_of
    d = date(2026, 9, 22)
    target, kw = stack_walk_inputs(exit_rules_as_of(d, "magna53"), 10.5, 9.5)
    assert target == 18.5 and kw["breakeven_at_r"] == 3.0 and kw["r_frame_ps"] == 1.0
    target, kw = stack_walk_inputs(exit_rules_as_of(d), 10.5, 9.5)
    assert target == 12.5 and kw["breakeven_at_r"] is None
    target, kw = stack_walk_inputs(exit_rules_as_of(d, "magna53"), 10.5, 10.5)
    assert target is None and kw["r_frame_ps"] is None
