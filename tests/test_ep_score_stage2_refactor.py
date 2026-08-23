"""Stage 2 of the score-tunability plan (2026-08-22): `_score_ep`'s inline
literals moved to `ep_rubric.SCORE_WEIGHTS` — pure refactor, no behaviour
change. THIS is the primary deliverable, not the refactor itself.

`tests/fixtures/ep_score_stage2_baseline.json` was captured by
`scripts/probes/_stage2_capture_baseline.py` run ONCE against the
pre-refactor `_score_ep` (inline if/elif ladders, no `ep_rubric` import).
This test re-runs the exact same sweep against the current (refactored)
`_score_ep` and asserts `final_score` AND the full `breakdown` dict are
byte-identical to that pinned baseline for every case.

Coverage (see the case names / `scripts/probes/_stage2_capture_baseline.py`
for the full list): every gap tier boundary, every liquidity ADV$ tier
boundary, the unknown/zero/negative-ADV fallback path (both rel_volume- and
projected_vol_multiple-driven, including premarket `projected_vol_multiple
=None`), every catalyst tier (+ an unrecognized label), float
present/absent/zero/negative/None + the 50M boundary, every vol_conviction
tier boundary, `in_active_theme` true/false, all four conviction_floor
branches and the transitions between them, both regime multipliers, and a
few combined realistic scenarios exercising several components + the floor
+ the multiplier at once.

If ANY case here fails, that is a live scoring change hiding in the
refactor — per CLAUDE.md THE LINE, do not "fix" it by adjusting the
fixture. Stop and report it.
"""
import json
from pathlib import Path

import pytest

from agents.market_intelligence.ep_detector import _score_ep

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ep_score_stage2_baseline.json"
_BASELINE = json.loads(_FIXTURE_PATH.read_text())


@pytest.mark.parametrize("case_name", sorted(_BASELINE.keys()))
def test_score_ep_matches_pre_refactor_baseline(case_name):
    expected = _BASELINE[case_name]
    final_score, breakdown = _score_ep(**expected["kwargs"])

    assert final_score == expected["final_score"], (
        f"{case_name}: final_score changed from {expected['final_score']} "
        f"to {final_score} — a live scoring change, not a refactor artifact."
    )
    assert breakdown == expected["breakdown"], (
        f"{case_name}: breakdown changed from {expected['breakdown']} "
        f"to {breakdown} — a live scoring change, not a refactor artifact."
    )


def test_baseline_fixture_has_full_coverage():
    """Guard against the fixture silently shrinking (e.g. a bad regen)."""
    assert len(_BASELINE) >= 60, (
        f"only {len(_BASELINE)} cases in the baseline fixture — expected the "
        f"full boundary sweep (69 cases as of authoring)."
    )
    required_prefixes = [
        "gap_", "liq_adv_", "liq_fallback_", "catalyst_", "float_",
        "vol_conv_", "theme_", "floor_r1_", "floor_r2_", "floor_r3_",
        "floor_r4_", "regime_",
    ]
    for prefix in required_prefixes:
        assert any(k.startswith(prefix) for k in _BASELINE), (
            f"no baseline case with prefix {prefix!r} — a required boundary "
            f"class is missing from coverage."
        )
