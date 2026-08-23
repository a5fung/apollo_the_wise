"""Stage 2 boundary-sweep baseline — since the #533 SEPARATION change
(2026-08-22, operator-signed) this pins the LEGACY / REVERT side.

`tests/fixtures/ep_score_stage2_baseline.json` was captured by
`scripts/probes/_stage2_capture_baseline.py` run ONCE against the
pre-refactor `_score_ep` (inline if/elif ladders, no `ep_rubric` import) —
i.e. it IS the pre-2026-08-22 scoring behaviour, byte for byte.

The operator-signed separation change made `SCORE_WEIGHTS` the live side
(flat gap credit, branch-4-only floor) and moved the old values to
`SCORE_WEIGHTS_LEGACY` — the side the `ep_score_separation` revert flag
restores. This test therefore re-runs the exact same 69-case sweep against
`_score_ep(weights=SCORE_WEIGHTS_LEGACY)` and asserts `final_score` AND the
full `breakdown` dict are byte-identical to the pinned baseline for every
case: the revert flag provably restores EXACTLY the old scoring (every gap
tier boundary, all four conviction-floor branches, every other component).
The separation side's own behaviour is pinned in
`tests/test_533_separation_flip.py`.

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

If ANY case here fails, the revert side has drifted from the true old
behaviour — the flag would no longer restore what it claims to. Per
CLAUDE.md THE LINE, do not "fix" it by adjusting the fixture. Stop and
report it.
"""
import json
from pathlib import Path

import pytest

from agents.market_intelligence.ep_detector import _score_ep
from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS_LEGACY

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ep_score_stage2_baseline.json"
_BASELINE = json.loads(_FIXTURE_PATH.read_text())


@pytest.mark.parametrize("case_name", sorted(_BASELINE.keys()))
def test_score_ep_matches_pre_refactor_baseline(case_name):
    expected = _BASELINE[case_name]
    final_score, breakdown = _score_ep(
        **expected["kwargs"], weights=SCORE_WEIGHTS_LEGACY)

    assert final_score == expected["final_score"], (
        f"{case_name}: final_score changed from {expected['final_score']} "
        f"to {final_score} — the revert side no longer matches the true pre-change behaviour."
    )
    assert breakdown == expected["breakdown"], (
        f"{case_name}: breakdown changed from {expected['breakdown']} "
        f"to {breakdown} — the revert side no longer matches the true pre-change behaviour."
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
