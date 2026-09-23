"""v2.0-P2 / #299 SLICE B — pure tape-feature compute. Behavior-neutral: build_tape returns None
when no feature is present (so the load-bearing judge prompt stays byte-identical). compute_or_atr
is cross-checked against the canonical flag_detector._atr_14 (no re-implementation of ATR)."""
import agents.market_intelligence.tape_features as tf
from agents.market_intelligence.flag_detector import _atr_14


def _daily(n=20, h=10.4, l=9.6, c=10.0):
    """Ascending mi_daily_closes-shaped rows with a stable ~0.8 true range → ATR-14 ≈ 0.8."""
    return [{"high_price": h, "low_price": l, "close": c} for _ in range(n)]


# ── compute_or_atr ────────────────────────────────────────────────────────────
def test_or_atr_matches_atr14_denominator():
    rows = _daily(20)
    atr = _atr_14(rows, len(rows) - 1)
    assert atr and atr > 0
    # OR height 1.2 over ATR ~0.8 → ~1.5
    assert tf.compute_or_atr(or_high=11.2, or_low=10.0, prior_daily_rows=rows) == round(1.2 / atr, 3)


def test_or_atr_none_when_inputs_bad():
    rows = _daily(20)
    assert tf.compute_or_atr(None, 10.0, rows) is None
    assert tf.compute_or_atr(10.0, 11.0, rows) is None          # high < low
    assert tf.compute_or_atr(11.0, 10.0, _daily(10)) is None     # < 14 bars → ATR None


def test_or_atr_flags_violent_open():
    rows = _daily(20)                                            # ATR ~0.8
    # a 0.4-wide OR → ~0.5 ratio = violent (>0.30)
    assert tf.compute_or_atr(10.4, 10.0, rows) > 0.30


# ── compute_pm_vol_curve ──────────────────────────────────────────────────────
def test_pm_vol_curve_renders_multiple_and_clock():
    rvol = {"anchor": "pm", "et_clock_minute": 9 * 60 + 15, "rvol_at_time": 2.34, "baseline_n": 30}
    s = tf.compute_pm_vol_curve(rvol)
    assert "2.3x" in s and "premarket" in s and "09:15 ET" in s and "n=30" in s


def test_pm_vol_curve_session_anchor():
    rvol = {"anchor": "session", "et_clock_minute": 9 * 60 + 45, "rvol_at_time": 1.8, "baseline_n": 12}
    assert "session baseline by 09:45 ET" in tf.compute_pm_vol_curve(rvol)


def test_pm_vol_curve_none_when_no_baseline():
    assert tf.compute_pm_vol_curve(None) is None
    assert tf.compute_pm_vol_curve({"anchor": "pm", "rvol_at_time": None}) is None


# ── compute_liquidity_tag ─────────────────────────────────────────────────────
def test_liquidity_tag_parts():
    assert tf.compute_liquidity_tag(dollar_vol=80e6) == "$80M traded"
    assert tf.compute_liquidity_tag(dollar_vol=80e6, spread_bps=4) == "$80M traded, ~4bps spread"
    assert tf.compute_liquidity_tag() is None


# ── build_tape — behavior-neutral when empty ──────────────────────────────────
def test_build_tape_none_when_all_absent():
    assert tf.build_tape() is None                              # → judge prompt byte-identical


def test_build_tape_includes_present_features_only():
    t = tf.build_tape(or_atr=0.41, pm_vol_curve="2.3x the premarket baseline by 09:15 ET (baseline n=30)")
    assert t == {"opening_range_atr": 0.41,
                 "pm_vol_curve": "2.3x the premarket baseline by 09:15 ET (baseline n=30)"}
    assert "liquidity" not in t


def test_build_tape_keys_match_judge_prompt_contract():
    # SLICE A renders t.get('opening_range_atr') / t.get('pm_vol_curve') / t.get('liquidity').
    t = tf.build_tape(or_atr=0.5, pm_vol_curve="x", liquidity="$50M traded")
    assert set(t) <= {"opening_range_atr", "pm_vol_curve", "liquidity"}
