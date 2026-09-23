"""RED-3 sizing-multiplier clamp (operator-ruled 2026-07-12, rulings-pack R5).

The composite multiplier (per-strategy × drawdown; the ADR-0022 allocator will write the
per-strategy leg) applies AFTER the builders' 20%-capital / VIX-scaled-risk caps. Pre-clamp,
a >1.0 step sized straight through every safeguard (composition_redteam RED-1..3, RED-3).
The clamp: shares may never exceed the builder's cap-maximal baseline — down freely, up never.
"""
from agents.market_intelligence.broker.entry_pipeline import _apply_composite_multiplier


def test_downsize_passes_through_floored():
    # 0.5× on 14 → 7, no clamp — the existing ramp semantics are untouched.
    assert _apply_composite_multiplier(14, 0.5) == (7, False)
    assert _apply_composite_multiplier(10, 0.25) == (2, False)


def test_upsize_clamps_to_baseline():
    # The RED-3 case: a >1.0 allocator step must NOT breach the builder's caps.
    assert _apply_composite_multiplier(14, 2.0) == (14, True)
    assert _apply_composite_multiplier(14, 1.3) == (14, True)   # floor(18.2)=18 > 14 → clamp


def test_fractional_upsize_that_floors_to_baseline_is_not_a_clamp():
    # 1.05× on 10 → floor(10.5)=10 == baseline: allowed, not flagged as a clamp.
    assert _apply_composite_multiplier(10, 1.05) == (10, False)


def test_downsize_to_zero_reaches_caller_skip():
    # 0.5× on 1 → 0; the caller's existing size_too_small skip handles it (unchanged).
    assert _apply_composite_multiplier(1, 0.5) == (0, False)


def test_identity_multiplier_is_exact():
    assert _apply_composite_multiplier(37, 1.0) == (37, False)
