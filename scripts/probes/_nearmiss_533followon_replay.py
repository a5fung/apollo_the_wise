"""#533 follow-on — $0 replay to check the "~2.3 names/day" near-miss estimate cited in
docs/setups/magna53_ep.md (the #533 rescale entry). That number has no saved derivation
artifact (grep across docs/analysis found nothing); this reproduces it independently.

Method: pull every candidate that reached _score_ep under the OLD (currently-live-in-prod)
rubric in the trailing 90 days (mi_ep_scan_log, last-seen row per ticker/day, ep_score NOT
NULL — i.e. it cleared every upstream gate the #533 change never touched), then re-score
each one through the REAL, currently-committed `_score_ep` + `ep_rubric.SCORE_WEIGHTS`
(imported, never reimplemented) to get the PRESENTED score, and count how many land in the
near-miss band [50, 65).

Known imprecision (disclosed, not smoothed):
- catalyst_quality is the OLD (pre-lattice-flip) classifier grade — the #533 Change 6 lattice
  flip cut the game_changer rate ~43%->18%, so this replay's catalyst points likely run HIGH
  vs what the shipped lattice would actually grade these candidates today (points the estimate
  UP, not down).
- float / vol_conviction / theme_bonus default to their zero-point default (those fields
  aren't in scan_log) — same "understates both variants equally" caveat the original
  score_separation_533 study used.
- confidence_multiplier (Claude+Perplexity agreement boost) defaults to 1.0 (no boost) — not
  stored on skip rows.
- regime_multiplier uses the REAL regime_date->regime table for the row's scan_date.
$0 — no LLM calls, no prod writes, reads already-captured PSV files.
"""
import sys
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS, SEPARATION_BAR
from agents.market_intelligence.ep_detector import _score_ep

SCAN = REPO / "scripts/probes/_nearmiss_scan_capture_2026-08-22.psv"
REGIME = REPO / "scripts/probes/_nearmiss_regime_capture_2026-08-22.psv"

regime_by_date = {}
for line in open(REGIME, encoding="utf-8"):
    line = line.rstrip("\n")
    if not line or "|" not in line:
        continue
    d, r = line.split("|")
    regime_by_date[d] = r

rows = []
for line in open(SCAN, encoding="utf-8"):
    line = line.rstrip("\n")
    if not line:
        continue
    parts = line.split("|")
    if len(parts) != 13:
        continue
    (scan_date, ticker, gap_pct, catalyst_quality, adv, adv_source, prev_close,
     proj_vol, rel_volume, pm_rvol, ep_score, score_tier, filter_reason) = parts

    def f(x):
        return float(x) if x else None

    rows.append({
        "scan_date": scan_date, "ticker": ticker,
        "gap_pct": f(gap_pct) or 0.0,
        "catalyst_quality": catalyst_quality or "routine",
        "adv": f(adv), "prev_close": f(prev_close),
        "proj_vol": f(proj_vol), "rel_volume": f(rel_volume) or 0.0,
        "old_ep_score": f(ep_score), "old_tier": score_tier,
    })

print(f"Loaded {len(rows)} scored candidates across {len(set(r['scan_date'] for r in rows))} "
      f"trading days (trailing 90d, last-seen state per ticker/day, ep_score NOT NULL "
      f"under the OLD/currently-live rubric).")

by_day = defaultdict(list)
band_lo, band_hi = 50, 65
near_miss_ct = 0
high_ct = 0
skip_ct = 0
for r in rows:
    regime = regime_by_date.get(r["scan_date"], "Choppy")
    regime_mult = 1.2 if regime == "Bull" else 1.0
    adv_dollar = (r["adv"] * r["prev_close"]) if (r["adv"] and r["prev_close"]) else None
    presented, breakdown = _score_ep(
        gap_pct=r["gap_pct"],
        rel_volume=r["rel_volume"],
        catalyst_quality=r["catalyst_quality"],
        profile={},
        regime_multiplier=regime_mult,  # confidence_multiplier defaults to 1.0 (folded in)
        projected_vol_multiple=r["proj_vol"],
        adv_dollar=adv_dollar,
        weights=SCORE_WEIGHTS,
    )
    r["new_presented"] = presented
    if presented >= SEPARATION_BAR:
        tier = "HIGH"
        high_ct += 1
    elif presented >= band_lo:
        tier = "NEAR_MISS"
        near_miss_ct += 1
    else:
        tier = "SKIP"
        skip_ct += 1
    r["new_tier"] = tier
    by_day[r["scan_date"]].append(r)

n_days = len(by_day)
print(f"\nUnder the LIVE (separation+rescale) rubric, replayed over the same candidate pool:")
print(f"  HIGH:      {high_ct} ({high_ct/n_days:.2f}/day)")
print(f"  NEAR_MISS [{band_lo},{SEPARATION_BAR}): {near_miss_ct} ({near_miss_ct/n_days:.2f}/day)")
print(f"  SKIP (<{band_lo}): {skip_ct} ({skip_ct/n_days:.2f}/day)")
print(f"  trading days: {n_days}")

# Distribution sanity: how many days have 0 / 1-3 / 4+ near-misses
buckets = defaultdict(int)
for d, items in by_day.items():
    nm = sum(1 for r in items if r["new_tier"] == "NEAR_MISS")
    if nm == 0:
        buckets["0"] += 1
    elif nm <= 3:
        buckets["1-3"] += 1
    else:
        buckets["4+"] += 1
print(f"\nDay distribution of near-miss count: {dict(buckets)}")

# Show a handful of examples
print("\nSample near-miss rows (first 10):")
shown = 0
for d in sorted(by_day):
    for r in by_day[d]:
        if r["new_tier"] == "NEAR_MISS" and shown < 10:
            print(f"  {d} {r['ticker']:6s} gap={r['gap_pct']:.1f}% cat={r['catalyst_quality']:12s} "
                  f"presented={r['new_presented']:.1f}  (old ep_score={r['old_ep_score']} old_tier={r['old_tier']})")
            shown += 1
