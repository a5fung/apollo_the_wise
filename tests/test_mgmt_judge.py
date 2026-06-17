"""P3 Management Judge (ADR 0014) — unit tests for the pure pieces: the R-math (the advisor's
trailed-stop trap), the bounded-enum fail-open, and the payload assembly. The LLM call itself is
fail-open and mirrors the grade-judge; the value here is pinning the correctness traps."""
from agents.market_intelligence.mgmt_judge import (
    VERDICTS, _normalize_mgmt_verdict, assemble_mgmt_inputs, compute_position_metrics,
)


# ── R-math: the trailed-stop trap (advisor A, 2026-06-17) ──

def test_r_uses_orb_low_not_trailed_stop():
    # FPS-shape: trailed stop (59.03) sits ABOVE entry (53.79) — using it as the denominator would
    # give a NEGATIVE risk and garbage R. R must use orb_low (52.67), the original entry risk.
    pos = {"entry_price": 53.79, "orb_low": 52.67, "stop_price": 59.03}
    m = compute_position_metrics(pos, current_price=56.0)
    # R = (56 - 53.79) / (53.79 - 52.67) = 2.21 / 1.12 ≈ 1.97  (POSITIVE, off the original risk)
    assert m["r_multiple"] is not None and m["r_multiple"] > 0
    assert abs(m["r_multiple"] - 1.97) < 0.05
    assert m["stop_above_entry"] is True          # profit locked — surfaced descriptively
    assert abs(m["pct_from_entry"] - (56 - 53.79) / 53.79) < 1e-4   # stored rounded to 4dp


def test_r_none_when_orb_low_at_or_above_entry():
    # No valid initial-risk reference (e.g. a 9M Day-2 stop on the prior-day low, or bad data) → None,
    # NOT a divide-by-zero or a negative R.
    assert compute_position_metrics({"entry_price": 44.69, "orb_low": 44.69}, 46.0)["r_multiple"] is None
    assert compute_position_metrics({"entry_price": 44.69, "orb_low": 45.0}, 46.0)["r_multiple"] is None


def test_r_none_when_orb_low_missing_but_pct_still_computed():
    m = compute_position_metrics({"entry_price": 44.69, "orb_low": None}, 46.0)
    assert m["r_multiple"] is None
    assert m["pct_from_entry"] is not None         # %-move is still well-defined


def test_metrics_none_safe_when_price_missing():
    m = compute_position_metrics({"entry_price": 44.69, "orb_low": 42.5}, None)
    assert m["pct_from_entry"] is None and m["r_multiple"] is None


def test_qure_shape_positive_r():
    # QURE-shape: entry 44.69, orb_low 42.50 (risk 2.19/sh), px 47 → R = 2.31/2.19 ≈ 1.05
    m = compute_position_metrics({"entry_price": 44.69, "orb_low": 42.5, "stop_price": 42.5}, 47.0)
    assert abs(m["r_multiple"] - 1.05) < 0.05
    assert m["stop_above_entry"] is False


# ── bounded-enum fail-open ──

def test_normalize_accepts_valid_verdict():
    out = _normalize_mgmt_verdict({"verdict": "TRAIL_TIGHTEN", "rationale": "profit locked, momentum stalling", "confidence": 0.7})
    assert out["verdict"] == "TRAIL_TIGHTEN" and out["confidence"] == 0.7


def test_normalize_rejects_out_of_enum():
    assert _normalize_mgmt_verdict({"verdict": "SELL_HALF", "rationale": "x"}) is None


def test_normalize_rejects_missing_rationale():
    assert _normalize_mgmt_verdict({"verdict": "HOLD", "rationale": ""}) is None
    assert _normalize_mgmt_verdict({"verdict": "HOLD"}) is None


def test_normalize_rejects_non_dict():
    assert _normalize_mgmt_verdict(None) is None
    assert _normalize_mgmt_verdict("HOLD") is None


def test_all_verdicts_normalize():
    for v in VERDICTS:
        assert _normalize_mgmt_verdict({"verdict": v, "rationale": "r"})["verdict"] == v


# ── payload assembly ──

def test_assemble_carries_metrics_thesis_and_posture():
    pos = {"ticker": "FPS", "entry_price": 53.79, "orb_low": 52.67, "stop_price": 59.03,
           "hold_days": 15, "remaining_shares": 109, "account_mode": "paper",
           "partial_taken": False, "time_stop_eligible": True}
    thesis = {"catalyst": "FDA approval", "score_tier": "HIGH", "ep_score": 72, "catalyst_quality": "strong"}
    p = assemble_mgmt_inputs(pos, current_price=56.0, thesis=thesis)
    assert p["ticker"] == "FPS" and p["hold_days"] == 15
    assert p["r_multiple"] > 0 and p["stop_above_entry"] is True   # from compute_position_metrics
    assert p["time_stop_eligible"] is True and p["partial_taken"] is False
    assert p["entry_grade_tier"] == "HIGH" and "FDA approval" in p["catalyst"]
