"""One-shot capture of _score_ep's CURRENT (pre-refactor) outputs across a
boundary sweep. Run ONCE against the unmodified ep_detector.py, dump to JSON.
The refactor is then proven byte-identical by re-running the same sweep
against the refactored code and diffing against this pinned fixture.

Not a test file itself — tests/test_ep_score_stage2_refactor.py loads the
JSON this produces (tests/fixtures/ep_score_stage2_baseline.json) and
re-asserts it post-refactor.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agents.market_intelligence.ep_detector import _score_ep  # noqa: E402

_BASE = dict(
    gap_pct=12.0,
    rel_volume=1.0,
    catalyst_quality="routine",
    profile={},
    regime_multiplier=1.0,
    vol_percentile=50.0,
    prior_3m_change=None,
    projected_vol_multiple=None,
    in_active_theme=False,
    adv_dollar=None,
)


def case(name, **overrides):
    kwargs = {**_BASE, **overrides}
    return name, kwargs


CASES = [
    # ── gap tiers + boundaries (catalyst=routine -> no conviction floor,
    #    adv_dollar=None + rel_volume=1.0 -> liquidity 0, isolates gap) ──
    case("gap_ge20", gap_pct=20.0),
    case("gap_19_9", gap_pct=19.9),
    case("gap_15", gap_pct=15.0),
    case("gap_14_9", gap_pct=14.9),
    case("gap_10", gap_pct=10.0),
    case("gap_9_9", gap_pct=9.9),
    case("gap_8", gap_pct=8.0),
    case("gap_7_9", gap_pct=7.9),

    # ── liquidity: known ADV$ tiers + boundaries ──
    case("liq_adv_500m", adv_dollar=500_000_000),
    case("liq_adv_499_999_999", adv_dollar=499_999_999),
    case("liq_adv_250m", adv_dollar=250_000_000),
    case("liq_adv_249_999_999", adv_dollar=249_999_999),
    case("liq_adv_100m", adv_dollar=100_000_000),
    case("liq_adv_99_999_999", adv_dollar=99_999_999),
    case("liq_adv_50m", adv_dollar=50_000_000),
    case("liq_adv_49_999_999", adv_dollar=49_999_999),
    case("liq_adv_0", adv_dollar=0),  # falls into fallback path (not >0)
    case("liq_adv_negative", adv_dollar=-5.0),  # falls into fallback path

    # ── liquidity: unknown-ADV fallback ladder (rel_volume-driven, premarket) ──
    case("liq_fallback_rvol_10", adv_dollar=None, rel_volume=10.0),
    case("liq_fallback_rvol_9_9", adv_dollar=None, rel_volume=9.9),
    case("liq_fallback_rvol_5", adv_dollar=None, rel_volume=5.0),
    case("liq_fallback_rvol_4_9", adv_dollar=None, rel_volume=4.9),
    case("liq_fallback_rvol_3", adv_dollar=None, rel_volume=3.0),
    case("liq_fallback_rvol_2_9", adv_dollar=None, rel_volume=2.9),
    case("liq_fallback_rvol_2", adv_dollar=None, rel_volume=2.0),
    case("liq_fallback_rvol_1_9", adv_dollar=None, rel_volume=1.9),

    # ── liquidity: unknown-ADV fallback ladder, post-open projected_vol_multiple
    #    overrides rel_volume ──
    case("liq_fallback_proj_10", adv_dollar=None, rel_volume=1.0, projected_vol_multiple=10.0),
    case("liq_fallback_proj_9_9", adv_dollar=None, rel_volume=1.0, projected_vol_multiple=9.9),
    case("liq_fallback_proj_5", adv_dollar=None, rel_volume=1.0, projected_vol_multiple=5.0),
    case("liq_fallback_proj_4_9", adv_dollar=None, rel_volume=1.0, projected_vol_multiple=4.9),
    case("liq_fallback_proj_3", adv_dollar=None, rel_volume=1.0, projected_vol_multiple=3.0),
    case("liq_fallback_proj_2_9", adv_dollar=None, rel_volume=1.0, projected_vol_multiple=2.9),
    case("liq_fallback_proj_2", adv_dollar=None, rel_volume=1.0, projected_vol_multiple=2.0),
    case("liq_fallback_proj_1_9", adv_dollar=None, rel_volume=1.0, projected_vol_multiple=1.9),
    # premarket: projected_vol_multiple explicitly None -> must use rel_volume
    case("liq_fallback_premarket_none_proj", adv_dollar=None, rel_volume=6.0, projected_vol_multiple=None),

    # ── catalyst tiers ──
    case("catalyst_game_changer", catalyst_quality="game_changer"),
    case("catalyst_strong", catalyst_quality="strong"),
    case("catalyst_routine", catalyst_quality="routine"),
    case("catalyst_unexpected_mna", catalyst_quality="mna"),

    # ── float present/absent/zero + boundary ──
    case("float_absent_key", profile={}),
    case("float_zero", profile={"floatShares": 0}),
    case("float_below_50m", profile={"floatShares": 10_000_000}),
    case("float_at_50m_boundary", profile={"floatShares": 50_000_000}),
    case("float_above_50m", profile={"floatShares": 100_000_000}),
    case("float_negative", profile={"floatShares": -1}),
    case("float_none_value", profile={"floatShares": None}),

    # ── vol_conviction tiers + boundaries ──
    case("vol_conv_90", vol_percentile=90.0),
    case("vol_conv_89_9", vol_percentile=89.9),
    case("vol_conv_70", vol_percentile=70.0),
    case("vol_conv_69_9", vol_percentile=69.9),
    case("vol_conv_default_50", vol_percentile=50.0),

    # ── theme_bonus true/false ──
    case("theme_true", in_active_theme=True),
    case("theme_false", in_active_theme=False),

    # ── conviction_floor: 4 branches + the boundaries/transitions between them ──
    case("floor_r1_ge15_gamechanger_at15", gap_pct=15.0, catalyst_quality="game_changer"),
    case("floor_r1_ge15_gamechanger_high", gap_pct=25.0, catalyst_quality="game_changer"),
    case("floor_r1_to_r4_boundary_14_9_gamechanger", gap_pct=14.9, catalyst_quality="game_changer"),
    case("floor_r2_ge20_strong_at20", gap_pct=20.0, catalyst_quality="strong"),
    case("floor_r2_to_r3_boundary_19_9_strong", gap_pct=19.9, catalyst_quality="strong"),
    case("floor_r3_ge15_strong_at15", gap_pct=15.0, catalyst_quality="strong"),
    case("floor_r3_to_none_boundary_14_9_strong", gap_pct=14.9, catalyst_quality="strong"),
    case("floor_r4_ge10_gamechanger_at10", gap_pct=10.0, catalyst_quality="game_changer"),
    case("floor_r4_to_none_boundary_9_9_gamechanger", gap_pct=9.9, catalyst_quality="game_changer"),
    case("floor_none_high_gap_routine", gap_pct=25.0, catalyst_quality="routine"),
    case("floor_none_high_gap_weak", gap_pct=25.0, catalyst_quality="weak"),

    # ── regime multiplier, both live values ──
    case("regime_1_0", regime_multiplier=1.0),
    case("regime_1_2_bull", regime_multiplier=1.2),

    # ── combined realistic scenarios (multiple components + floor + multiplier) ──
    case(
        "combo_high_conviction_bull",
        gap_pct=22.0, rel_volume=2.0, catalyst_quality="game_changer",
        profile={"floatShares": 20_000_000}, regime_multiplier=1.2,
        vol_percentile=95.0, projected_vol_multiple=None,
        in_active_theme=True, adv_dollar=600_000_000,
    ),
    case(
        "combo_moderate_unknown_adv_premarket",
        gap_pct=9.0, rel_volume=4.0, catalyst_quality="strong",
        profile={"floatShares": 80_000_000}, regime_multiplier=1.0,
        vol_percentile=72.0, projected_vol_multiple=None,
        in_active_theme=False, adv_dollar=None,
    ),
    case(
        "combo_thin_liquidity_no_catalyst",
        gap_pct=8.5, rel_volume=1.2, catalyst_quality="routine",
        profile={}, regime_multiplier=1.0,
        vol_percentile=40.0, projected_vol_multiple=1.5,
        in_active_theme=False, adv_dollar=5_000_000,
    ),
]


def main():
    results = {}
    seen = set()
    for name, kwargs in CASES:
        assert name not in seen, f"duplicate case name {name}"
        seen.add(name)
        final_score, breakdown = _score_ep(**kwargs)
        results[name] = {
            "kwargs": {k: v for k, v in kwargs.items()},
            "final_score": final_score,
            "breakdown": breakdown,
        }

    out_path = REPO_ROOT / "tests" / "fixtures" / "ep_score_stage2_baseline.json"
    out_path.write_text(json.dumps(results, indent=2, sort_keys=True, default=str))
    print(f"wrote {len(results)} cases to {out_path}")


if __name__ == "__main__":
    main()
