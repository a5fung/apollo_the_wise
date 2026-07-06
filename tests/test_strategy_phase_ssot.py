"""Drift guard for the strategy-phase vocabulary (2026-07-06 /simplify altitude).

The #424 'deprecated' rollout hardcoded the phase set in 5+ places and MISSED
two — the DB CHECK constraint (market-agent boot-crash) and the preflight walk
(deploy-gate crash). constants.VALID_STRATEGY_PHASES / NO_SUBMIT_PHASES are now
the SSoT; these tests fail if a site drifts from them, so a new phase value is a
single edit + a red test until every site is updated — not a grep-and-pray.
"""
import re
from pathlib import Path

from agents.market_intelligence.constants import (
    NO_SUBMIT_PHASES, VALID_STRATEGY_PHASES,
)

_REPO = Path(__file__).resolve().parents[1]


def test_no_submit_is_a_subset_of_valid():
    assert NO_SUBMIT_PHASES <= VALID_STRATEGY_PHASES
    # paper + live must be able to submit — never in the no-submit set.
    assert "paper" not in NO_SUBMIT_PHASES
    assert "live" not in NO_SUBMIT_PHASES


def test_db_check_constraint_matches_valid_phases():
    """SQL can't import Python — this test bridges the drift. Every
    `CHECK (phase IN (...))` literal in db.py must equal VALID_STRATEGY_PHASES.
    This is the guard that would have caught the 7/6 boot-crash (the ALTER +
    CREATE constraints missing 'deprecated')."""
    src = (_REPO / "agents" / "market_intelligence" / "db.py").read_text(encoding="utf-8")
    checks = re.findall(r"CHECK \(phase IN \(([^)]*)\)\)", src)
    assert checks, "no phase CHECK constraint found in db.py — did the schema move?"
    for raw in checks:
        values = {v.strip().strip("'\"") for v in raw.split(",")}
        assert values == set(VALID_STRATEGY_PHASES), (
            f"db.py phase CHECK {values} != VALID_STRATEGY_PHASES "
            f"{set(VALID_STRATEGY_PHASES)} — update both together (constants SSoT)."
        )


def test_entry_gate_and_preflight_consult_the_shared_set():
    """The two gates must reference NO_SUBMIT_PHASES, not re-hardcode the literals
    (the re-hardcoding is what drifted and boot-crashed)."""
    gate = (_REPO / "agents" / "market_intelligence" / "broker" / "entry_pipeline.py").read_text(encoding="utf-8")
    preflight = (_REPO / "scripts" / "preflight_check.py").read_text(encoding="utf-8")
    assert "NO_SUBMIT_PHASES" in gate
    assert "NO_SUBMIT_PHASES" in preflight
