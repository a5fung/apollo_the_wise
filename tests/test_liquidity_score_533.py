"""The EP score ranks on LIQUIDITY, not on relative volume (operator-signed 2026-08-22).

The old `rel_volume` ladder scored "how unusual is today's volume for this stock".
Real EPs do not look like that: the labelled cohort's median is 1.8x, which earned
ZERO, while a sleepy micro-cap at 3x scored 10. Measured on 26 labelled real EPs vs
1,074 ordinary gap days, ex-ante 20-day ADV$ separates at AUC 0.72 against
day-RVOL's 0.31 — the old component ran BACKWARDS.
"""
import pytest

from agents.market_intelligence.ep_detector import _score_ep

_BASE = dict(gap_pct=12.0, catalyst_quality="strong", profile={},
             regime_multiplier=1.0, vol_percentile=50.0)


def _bd(**kw):
    _, breakdown = _score_ep(**{**_BASE, **kw})
    return breakdown


def test_liquidity_tiers_reward_dollar_volume():
    assert _bd(rel_volume=1.0, adv_dollar=600_000_000)["liquidity"] == 15
    assert _bd(rel_volume=1.0, adv_dollar=300_000_000)["liquidity"] == 12
    assert _bd(rel_volume=1.0, adv_dollar=150_000_000)["liquidity"] == 10
    assert _bd(rel_volume=1.0, adv_dollar=60_000_000)["liquidity"] == 7
    assert _bd(rel_volume=1.0, adv_dollar=10_000_000)["liquidity"] == 0


def test_FAILS_WITHOUT_FIX_a_typical_real_EP_no_longer_scores_zero():
    """The cohort median is 1.8x RVOL on a large, liquid name — 0 under the old ladder."""
    assert _bd(rel_volume=1.8, adv_dollar=600_000_000)["liquidity"] == 15


def test_a_sleepy_microcap_spiking_no_longer_outranks_a_liquid_name():
    micro = _bd(rel_volume=3.0, adv_dollar=5_000_000)["liquidity"]
    liquid = _bd(rel_volume=1.8, adv_dollar=600_000_000)["liquidity"]
    assert micro == 0 and liquid == 15, "the old ladder scored these 10 and 0 — backwards"


def test_unknown_ADV_falls_back_to_the_old_ladder_not_to_zero():
    """A data gap must never silently sink a candidate — P1: a false exclusion is invisible."""
    assert _bd(rel_volume=3.0, adv_dollar=None)["liquidity"] == 10
    assert _bd(rel_volume=12.0, adv_dollar=None)["liquidity"] == 15
    assert _bd(rel_volume=1.0, adv_dollar=0)["liquidity"] == 0  # 0 ADV -> falls back, 1.0x -> 0


def test_the_stale_rel_volume_key_is_gone():
    """The breakdown must not keep a label that no longer describes what it measures."""
    assert "rel_volume" not in _bd(rel_volume=5.0, adv_dollar=600_000_000)


def test_projected_multiple_still_used_in_the_fallback_path():
    assert _bd(rel_volume=1.0, projected_vol_multiple=6.0, adv_dollar=None)["liquidity"] == 12


# ── The two backwards-running components, deleted 2026-08-22 (operator-signed) ──

def test_the_neglect_component_is_gone():
    """It scored 'beaten down 30%+ from the 52w high' — MRNA, the operator's own textbook
    EP, sits AT its high and scored ZERO on the component named after his thesis."""
    bd = _bd(rel_volume=1.8, adv_dollar=600_000_000,
             profile={"price": 100.0, "52WeekHigh": 100.0})
    assert "neglect" not in bd


def test_a_stock_at_its_52w_high_is_no_longer_penalised_versus_a_beaten_down_one():
    at_high = _score_ep(**{**_BASE, "rel_volume": 1.8, "adv_dollar": 600_000_000,
                           "profile": {"price": 100.0, "52WeekHigh": 100.0}})[0]
    beaten = _score_ep(**{**_BASE, "rel_volume": 1.8, "adv_dollar": 600_000_000,
                          "profile": {"price": 40.0, "52WeekHigh": 100.0}})[0]
    assert at_high == beaten, "the beaten-down bonus must no longer separate these"


def test_the_prior_momentum_penalty_is_gone():
    """It fired on real EPs and junk at the same rate (31% vs 32%) and drove ARM to -12."""
    bd = _bd(rel_volume=1.8, adv_dollar=600_000_000, prior_3m_change=80.0)
    assert "prior_momentum" not in bd


def test_a_stock_up_80pct_in_3_months_scores_the_same_as_a_flat_one():
    ran = _score_ep(**{**_BASE, "rel_volume": 1.8, "adv_dollar": 600_000_000,
                       "prior_3m_change": 80.0})[0]
    flat = _score_ep(**{**_BASE, "rel_volume": 1.8, "adv_dollar": 600_000_000,
                        "prior_3m_change": 2.0})[0]
    assert ran == flat, "a 25-point penalty that separates nothing must not survive"
