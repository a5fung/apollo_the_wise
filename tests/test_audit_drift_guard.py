"""Guard test for the L2 drift-vs-spike downgrade (`_is_slow_drift`, 2026-06-15).

theme_count_active is a SLOWLY-drifting metric (max daily step 5; a 55→38 decline over
~6 weeks). Its 30d MAD is ~1 on a median ~44, so a benign continuation of the drift
(38 vs 44) produced z=−6 and fired a daily L2 Telegram — drift mis-classified as a spike.

`_is_slow_drift` downgrades such an L2-via-z (band 3) to L3 (band 2, audit-only) ONLY when
the metric is stable (MAD < 5% of median) AND the move is immaterial (<20% of median) AND it
did not fire via the 5× ratio rule. These tests pin that it suppresses the benign case while
preserving detection of real declines, collapses, and dedup-death.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.market_intelligence.system_audit import _band_for, _is_slow_drift


def _classify(current, p50, mad, direction="low"):
    """Mirror _compute_anomaly's band path (z + ratio + the drift guard) — returns band."""
    use_z = mad >= 1.0
    z = ((current - p50) / mad) if use_z else 0.0
    ratio = (p50 / max(current, 1e-9)) if direction == "low" else (current / max(p50, 1e-9))
    band = _band_for(z, ratio)
    if _is_slow_drift(band, ratio, mad, p50, current):
        band = 2
    return band


def test_benign_slow_drift_downgraded_to_L3():
    # theme_count_active today: 38 vs p50 44, mad 1 → z=−6 but only 13.6% → L3 drift, NOT L2.
    assert _classify(38, 44, 1) == 2


def test_material_decline_stays_L2():
    # 20%+ move on the same tight-MAD metric is material → stays L2.
    assert _classify(35, 44, 1) == 3   # 20.5%
    assert _classify(30, 44, 1) == 3   # 31.8%


def test_dedup_death_stays_L2_via_ratio():
    # A real collapse trips the 5× ratio rule → exempt from the guard → L2.
    assert _classify(8, 44, 1) == 3    # ratio 5.5×


def test_healthy_variance_metric_unaffected():
    # MAD a healthy fraction of median (≥5%) → guard never applies; band is whatever z says.
    assert not _is_slow_drift(3, ratio=1.16, mad=4, p50=44, current=38)   # mad/p50=9%
    # a genuine band-3 on a healthy-variance metric is left as L2
    assert _classify(30, 44, 4) == 3   # z=−3.5, mad/p50=9% → not downgraded


def test_guard_is_pure_and_exempts_ratio_fires():
    # ratio ≥ 5 is never downgraded, regardless of materiality/MAD.
    assert not _is_slow_drift(3, ratio=5.0, mad=1, p50=44, current=8)
    # immaterial + tight MAD + sub-5× ratio → downgrade
    assert _is_slow_drift(3, ratio=1.16, mad=1, p50=44, current=38)
    # material move → no downgrade even on a tight-MAD metric
    assert not _is_slow_drift(3, ratio=1.47, mad=1, p50=44, current=30)
