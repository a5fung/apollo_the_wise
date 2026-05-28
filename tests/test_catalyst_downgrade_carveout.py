"""Regression tests for the catalyst-downgrade YoY-missing carve-out (2026-05-28).

Closes `data_gated_reviews.yaml::rubric_safety_net_yoy_required` with N=10
cohort evidence. The predicate `_should_apply_yoy_carveout(extracted)`
encapsulates the spec; tests pin behavior against the actual 10-case
cohort that triggered the ship.

Spec (from `docs/setups/catalyst_rubric.md` 2026-05-28 change-log entry):
  SKIP downgrade IF:
    q_revenue.beat_vs_est_pct > 0
    AND guidance.direction IN ("raised", "initiated", "reaffirmed")
    AND guidance.confidence IN ("high", "medium")
"""
import pytest

from agents.market_intelligence.ep_detector import _should_apply_yoy_carveout


# ── Cohort cases that SHOULD trigger the carve-out ──────────────────────────

@pytest.mark.parametrize("ticker, beat, direction, conf", [
    ("SNOW", 5.3, "raised", "high"),
    ("BBWI", 1.2, "raised", "high"),
    ("JOYY", 2.3, "raised", "medium"),
    ("RL",   7.1, "initiated", "medium"),
    ("TATT", 1.9, "reaffirmed", "medium"),
    ("KLAR", 5.8, "initiated", "high"),
])
def test_carveout_applies_to_real_cohort_cases(ticker, beat, direction, conf):
    """All 6 cohort cases with positive beat + guidance signal stay
    at their LLM grade — predicate returns True (skip the downgrade)."""
    extracted = {
        "q_revenue_usd": {"value": 1_000_000_000, "beat_vs_est_pct": beat, "yoy_pct": None},
        "guidance_change": {"direction": direction, "confidence": conf},
    }
    assert _should_apply_yoy_carveout(extracted), f"{ticker} should have carve-out applied"


# ── Cohort cases that should NOT trigger the carve-out (still downgrade) ────

@pytest.mark.parametrize("ticker, beat, direction, conf, reason", [
    ("QFIN", 5.1,   None, None, "no guidance signal extracted"),
    ("ESLT", 2.4,   None, None, "no guidance signal extracted"),
    ("LION", 11.9,  None, None, "big beat but no guidance — safety net still fires"),
    ("ROIV", -34.0, None, None, "negative beat (actual miss) — safety net must fire"),
])
def test_carveout_does_not_apply_to_no_guidance_or_miss_cases(ticker, beat, direction, conf, reason):
    extracted = {
        "q_revenue_usd": {"value": 1_000_000_000, "beat_vs_est_pct": beat, "yoy_pct": None},
        "guidance_change": {"direction": direction, "confidence": conf},
    }
    assert not _should_apply_yoy_carveout(extracted), f"{ticker} should still downgrade: {reason}"


# ── Edge cases ──────────────────────────────────────────────────────────────

def test_carveout_blocks_low_confidence_guidance():
    """Guidance present but confidence='low' → safety net still fires.
    (Not in 2026-05-28 cohort but future-proofs the spec.)"""
    extracted = {
        "q_revenue_usd": {"value": 1_000_000_000, "beat_vs_est_pct": 5.0, "yoy_pct": None},
        "guidance_change": {"direction": "raised", "confidence": "low"},
    }
    assert not _should_apply_yoy_carveout(extracted)


def test_carveout_blocks_lowered_guidance():
    """Guidance direction='lowered' → safety net still fires.
    Lowered guidance is the catch zone the safety net is designed for."""
    extracted = {
        "q_revenue_usd": {"value": 1_000_000_000, "beat_vs_est_pct": 5.0, "yoy_pct": None},
        "guidance_change": {"direction": "lowered", "confidence": "high"},
    }
    assert not _should_apply_yoy_carveout(extracted)


def test_carveout_blocks_zero_beat():
    """beat_vs_est_pct = 0 (in-line) → not a positive signal."""
    extracted = {
        "q_revenue_usd": {"value": 1_000_000_000, "beat_vs_est_pct": 0.0, "yoy_pct": None},
        "guidance_change": {"direction": "raised", "confidence": "high"},
    }
    assert not _should_apply_yoy_carveout(extracted)


def test_carveout_handles_missing_extraction_blocks_gracefully():
    """Missing keys → predicate returns False (defaults to safety-net firing)."""
    assert not _should_apply_yoy_carveout({})
    assert not _should_apply_yoy_carveout({"q_revenue_usd": None, "guidance_change": None})
    assert not _should_apply_yoy_carveout({"q_revenue_usd": {"beat_vs_est_pct": None}})


def test_carveout_handles_non_numeric_beat():
    """beat_vs_est_pct is a string (extraction bug) → predicate refuses, safety net fires."""
    extracted = {
        "q_revenue_usd": {"beat_vs_est_pct": "5.3"},  # str, not number
        "guidance_change": {"direction": "raised", "confidence": "high"},
    }
    assert not _should_apply_yoy_carveout(extracted)
