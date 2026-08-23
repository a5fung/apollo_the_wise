"""#533 RESCALE (2026-08-22) — THE IDENTICAL-ALERT-SET PROOF.

The separation change fixed the score's ORDERING but left the NUMBERS
unreadable: every score fell, the bar dropped to raw 40 — below the legacy 50
cutline — and the bands went incoherent. The fix is ONE strictly-increasing
affine transform on the FINAL score (presented = 1.25 x raw + 15, applied
after the conviction floor AND the regime multiplier), with the bar expressed
through the SAME function (65 = T(40)). No component weight, tier cut, or raw
threshold moved.

THE INVARIANT THIS FILE PROVES, per the card — not asserts, PROVES on a
representative cohort: for every candidate, `alerts_before == alerts_after` —
same tickers, same days, same tiers. The cohort is three-fold:

  1. The 69-case stage-2 boundary fixture's captured kwargs (every gap /
     liquidity / catalyst / float / vol_conviction / floor / regime boundary
     the rubric has), re-scored on the LIVE table.
  2. The 26-member must-not-miss fixture (#577 — the labelled REAL EPs,
     MRNA included) at every catalyst grade x regime multiplier x liquidity
     scenario: the names whose alerts must never move.
  3. A ~2,700-shape systematic grid over the full scoring input space, plus
     an exhaustive 0.1-step numeric sweep of the raw score axis through the
     bar boundary (the rounding proof).

"Before" = the live table with `output_scale` stripped (byte-identical to the
pre-rescale SCORE_WEIGHTS — asserted below, not assumed), decided at the raw
bar 40. "After" = the live table as shipped, decided at the presented bar 65.
The legacy / revert side carries NO transform (`output_scale: None`) — flag
OFF still presents the old raw scale byte-identically (the 69-case baseline in
test_ep_score_stage2_refactor.py keeps pinning that side; here we pin only
that the rescale did not touch it).
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from agents.market_intelligence.ep_detector import _score_ep
from agents.market_intelligence.ep_rubric import (
    LEGACY_MODERATE_CUTLINE, SCORE_WEIGHTS, SCORE_WEIGHTS_LEGACY,
    SEPARATION_BAR, SEPARATION_BAR_RAW, apply_output_scale,
    resolve_moderate_cutline,
)
from tests.fixtures import must_not_miss_eps as fx

_FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "ep_score_stage2_baseline.json"

# The pre-rescale live table: identical to SCORE_WEIGHTS except the transform.
_RAW_WEIGHTS = {**SCORE_WEIGHTS, "output_scale": None}

_SCALE = SCORE_WEIGHTS["output_scale"]


def _decide_before(raw_score: float) -> str:
    """Pre-rescale separation semantics: HIGH iff score >= raw bar 40; below is
    a silent skip (the 50 cutline sat ABOVE the bar, so `< 50 and < 40` == `< 40`
    and MODERATE was empty every day)."""
    if raw_score >= SEPARATION_BAR_RAW:
        return "HIGH"
    if raw_score < 50 and raw_score < SEPARATION_BAR_RAW:
        return "skip"
    return "MODERATE"  # unreachable — proven below


def _decide_after(presented_score: float) -> str:
    """Post-rescale separation semantics: HIGH iff presented >= 65; the
    separation side has no MODERATE cutline (resolve_moderate_cutline -> None)."""
    cut = resolve_moderate_cutline(True)
    if presented_score >= SEPARATION_BAR:
        return "HIGH"
    if presented_score < SEPARATION_BAR and (cut is None or presented_score < cut):
        return "skip"
    return "MODERATE"  # unreachable — proven below


def _assert_identical(case_id: str, kwargs: dict) -> tuple[float, float]:
    """Score one candidate on both sides of the rescale; assert the decision
    (alert or not, and which tier) is IDENTICAL, and the presented number is
    exactly the raw one through the one transform."""
    raw, bd_raw = _score_ep(**kwargs, weights=_RAW_WEIGHTS)
    pres, bd_pres = _score_ep(**kwargs, weights=SCORE_WEIGHTS)
    assert bd_raw == bd_pres, f"{case_id}: breakdown must not change — presentation only"
    assert pres == apply_output_scale(raw, _SCALE), (
        f"{case_id}: presented {pres} is not the transform of raw {raw}")
    before, after = _decide_before(raw), _decide_after(pres)
    assert before == after, (
        f"{case_id}: DECISION FLIPPED {before} -> {after} (raw {raw}, presented {pres}) "
        f"— the transform changed the alerting set; it is wrong.")
    assert before != "MODERATE", f"{case_id}: MODERATE must be empty on both sides"
    return raw, pres


# ── pins: the transform's constants and the bar arithmetic ────────────────────────────


def test_transform_constants_and_bar_arithmetic():
    """mult is exactly 5/4 (binary-exact — the rounding proof depends on it);
    the presented bar is exactly the raw 40 policy through the same map."""
    assert _SCALE["mult"] == 1.25 and _SCALE["offset"] == 15
    assert SEPARATION_BAR_RAW == 40
    assert SEPARATION_BAR == 65 == apply_output_scale(40.0, _SCALE)


def test_the_raw_side_used_here_is_the_live_table_minus_only_the_transform():
    """The 'before' scorer must differ from the shipped table in NOTHING but
    output_scale — otherwise this file would be proving the wrong invariant."""
    assert set(_RAW_WEIGHTS) == set(SCORE_WEIGHTS)
    for k in SCORE_WEIGHTS:
        if k == "output_scale":
            continue
        assert _RAW_WEIGHTS[k] is SCORE_WEIGHTS[k]
    assert _RAW_WEIGHTS["output_scale"] is None


def test_legacy_revert_side_carries_no_transform():
    """Flag OFF must present the OLD RAW SCALE byte-identically — the 69-case
    stage-2 baseline pins the numbers; this pins that the rescale can never
    leak into that side via the {**SCORE_WEIGHTS} spread."""
    assert SCORE_WEIGHTS_LEGACY["output_scale"] is None
    assert resolve_moderate_cutline(False) == LEGACY_MODERATE_CUTLINE == 50
    # spot proof: a legacy scoring is numerically the old raw scale
    score, _ = _score_ep(
        gap_pct=20.5, rel_volume=1.8, catalyst_quality="strong", profile={},
        regime_multiplier=1.2, adv_dollar=300_000_000,
        weights=SCORE_WEIGHTS_LEGACY)
    assert score == 96.0  # floor 80 x 1.2 — untransformed, exactly as before


# ── cohort 1: the 69-case boundary fixture, re-scored on the live table ───────────────

_BASELINE = json.loads(_FIXTURE_PATH.read_text())


@pytest.mark.parametrize("case_name", sorted(_BASELINE.keys()))
def test_alert_set_identical_on_the_69_case_boundary_cohort(case_name):
    _assert_identical(case_name, _BASELINE[case_name]["kwargs"])


# ── cohort 2: the labelled real EPs (must-not-miss, MRNA included) ───────────────────

_MEMBERS = [m for m in fx.MUST_NOT_MISS if m.gap_pct is not None]
assert len(_MEMBERS) >= 25  # the fixture carries the full #577 cohort


@pytest.mark.parametrize("member", _MEMBERS, ids=lambda m: f"{m.ticker}_{m.alert_date}")
def test_alert_set_identical_on_every_labelled_real_ep(member):
    """Every real EP, every grade the lattice could award it, every regime
    multiplier, liquid and ADV-unknown: the same days alert before and after."""
    for grade in ("routine", "strong", "game_changer"):
        for mult in (1.0, 1.2, 1.44):  # non-Bull / Bull / Bull + agreement
            for adv in (None, 600_000_000):
                _assert_identical(
                    f"{member.ticker} {member.alert_date} @{grade} x{mult}",
                    dict(gap_pct=member.gap_pct, rel_volume=1.8,
                         catalyst_quality=grade, profile={},
                         regime_multiplier=mult, adv_dollar=adv))


def test_mrna_guard_case_alerts_on_both_sides_of_the_transform():
    """THE reference EP at its operational read: raw 72 / presented 105 — HIGH
    either way, in every regime (raw 60 / presented 90 non-Bull)."""
    kw = dict(gap_pct=10.04, rel_volume=1.8, catalyst_quality="game_changer",
              profile={}, adv_dollar=600_000_000)
    raw, pres = _assert_identical("MRNA bull", dict(kw, regime_multiplier=1.2))
    assert (raw, pres) == (72.0, 105.0)
    raw, pres = _assert_identical("MRNA non-bull", dict(kw, regime_multiplier=1.0))
    assert (raw, pres) == (60.0, 90.0)


# ── cohort 3: systematic grid over the scoring input space ────────────────────────────

_GAPS = (5.0, 7.9, 8.0, 8.5, 9.5, 9.99, 10.0, 10.04, 12.0, 14.9, 15.0,
         19.9, 20.0, 25.0, 35.0)
_CATALYSTS = ("routine", "strong", "game_changer", "mna", "unrecognized")
_ADVS = (None, 60_000_000, 600_000_000)
_MULTS = (1.0, 1.2, 1.44)


def test_alert_set_identical_on_the_full_grid():
    n = 0
    for gap in _GAPS:
        for cat in _CATALYSTS:
            for adv in _ADVS:
                for mult in _MULTS:
                    for theme in (False, True):
                        for float_sh in (30_000_000, 100_000_000):
                            _assert_identical(
                                f"grid g{gap} {cat} adv{adv} x{mult} t{theme} f{float_sh}",
                                dict(gap_pct=gap, rel_volume=3.0,
                                     catalyst_quality=cat,
                                     profile={"floatShares": float_sh},
                                     regime_multiplier=mult, adv_dollar=adv,
                                     vol_percentile=92.0 if theme else 40.0,
                                     in_active_theme=theme))
                            n += 1
    assert n == len(_GAPS) * len(_CATALYSTS) * len(_ADVS) * len(_MULTS) * 4


# ── the rounding / monotonicity proof on the raw score axis ───────────────────────────


def test_transform_is_strictly_increasing_and_bar_equivalent_at_0p1_grain():
    """Exhaustive over every 1-decimal raw score 0.0..130.0 (the grain
    `_score_ep` emits): (raw >= 40) <-> (presented >= 65) — no rounding flip
    at the boundary — and strictly increasing, so ordering (allocator ranks,
    top-N) is preserved everywhere, floor-forced scores included."""
    prev = None
    for i in range(0, 1301):
        r = round(i / 10, 1)
        p = apply_output_scale(r, _SCALE)
        assert (r >= SEPARATION_BAR_RAW) == (p >= SEPARATION_BAR), (
            f"boundary flip at raw {r}: presented {p}")
        if prev is not None:
            assert p > prev, f"not strictly increasing at raw {r}"
        prev = p


def test_boundary_neighbourhood_exact_values():
    """The knife edge, by value: 39.9 -> 64.9 (skip), 40.0 -> 65.0 (HIGH),
    40.1 -> 65.1 (HIGH). 1.25 = 5/4 is binary-exact, so 40.0 maps to exactly
    65.0 — no epsilon at the bar."""
    assert apply_output_scale(39.9, _SCALE) == 64.9
    assert apply_output_scale(40.0, _SCALE) == 65.0
    assert apply_output_scale(40.1, _SCALE) == 65.1
