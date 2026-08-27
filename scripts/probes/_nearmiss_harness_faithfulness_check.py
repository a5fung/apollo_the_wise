"""Advisor-requested faithfulness check for _nearmiss_533followon_replay.py: replay the SAME
captured candidates through SCORE_WEIGHTS_LEGACY (+ the per-regime bar) — the rubric that
ACTUALLY produced the stored `old_ep_score` on these historical rows — and compare row-by-row
against the stored value. If the harness (missing float/vol_conviction/theme_bonus/
confidence_multiplier — none of which are in mi_ep_scan_log) reproduces stored scores closely,
the live-side near-miss replay is trustworthy. If it systematically under-scores, the omitted
inputs dominate and the near-miss volume estimate must be treated as a lower bound, not a
correction of the cited 2.3/day.
"""
import sys
from pathlib import Path
from statistics import median

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS_LEGACY
from agents.market_intelligence.ep_detector import _score_ep

SCAN = REPO / "scripts/probes/_nearmiss_scan_capture_2026-08-22.psv"
REGIME = REPO / "scripts/probes/_nearmiss_regime_capture_2026-08-22.psv"

regime_by_date = {}
for line in open(REGIME, encoding="utf-8"):
    line = line.rstrip("\n")
    if "|" not in line:
        continue
    d, r = line.split("|")
    regime_by_date[d] = r

EP_THRESHOLD_BY_REGIME = {"Bull": 65, "Choppy": 70, "Correcting": 75, "Crisis": 80}

rows = []
for line in open(SCAN, encoding="utf-8"):
    line = line.rstrip("\n")
    if not line:
        continue
    p = line.split("|")
    if len(p) != 13:
        continue
    (scan_date, ticker, gap_pct, catalyst_quality, adv, adv_source, prev_close,
     proj_vol, rel_volume, pm_rvol, ep_score, score_tier, filter_reason) = p

    def f(x):
        return float(x) if x else None

    if not ep_score:
        continue
    rows.append({
        "scan_date": scan_date, "ticker": ticker,
        "gap_pct": f(gap_pct) or 0.0,
        "catalyst_quality": catalyst_quality or "routine",
        "adv": f(adv), "prev_close": f(prev_close),
        "proj_vol": f(proj_vol), "rel_volume": f(rel_volume) or 0.0,
        "stored_ep_score": f(ep_score), "stored_tier": score_tier,
    })

diffs = []
under = 0
close = 0  # within 5 points
over = 0
print(f"{'date':10s} {'ticker':7s} {'stored':>7s} {'replay':>7s} {'diff':>7s}  tier")
shown = 0
for r in rows:
    regime = regime_by_date.get(r["scan_date"], "Choppy")
    mult = 1.2 if regime == "Bull" else 1.0
    bar = EP_THRESHOLD_BY_REGIME.get(regime, 70)
    adv_dollar = (r["adv"] * r["prev_close"]) if (r["adv"] and r["prev_close"]) else None
    replay, _ = _score_ep(
        gap_pct=r["gap_pct"], rel_volume=r["rel_volume"],
        catalyst_quality=r["catalyst_quality"], profile={},
        regime_multiplier=mult, projected_vol_multiple=r["proj_vol"],
        adv_dollar=adv_dollar, weights=SCORE_WEIGHTS_LEGACY,
    )
    diff = replay - r["stored_ep_score"]
    diffs.append(diff)
    if diff < -5:
        under += 1
    elif diff > 5:
        over += 1
    else:
        close += 1
    if shown < 15:
        print(f"{r['scan_date']:10s} {r['ticker']:7s} {r['stored_ep_score']:7.1f} "
              f"{replay:7.1f} {diff:7.1f}  {r['stored_tier']}")
        shown += 1

n = len(diffs)
print(f"\nn={n}")
print(f"median diff (replay - stored): {median(diffs):.1f}")
print(f"mean diff: {sum(diffs)/n:.1f}")
print(f"within +/-5 pts: {close} ({close/n:.0%})")
print(f"replay UNDER stored by >5: {under} ({under/n:.0%})")
print(f"replay OVER stored by >5: {over} ({over/n:.0%})")
