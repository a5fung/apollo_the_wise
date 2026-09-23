"""EP Phase 5 prep: catalyst-tier forward-return analysis vs Pradeep's hierarchy.

Per `user_pradeep_catalyst_hierarchy.md` (Pradeep Bonde 2026-05-17):
  Tier 1: Theme (most powerful)
  Tier 2: Government policy change
  Tier 3: Shortages
  Tier 4: Sales acceleration / new products / management change

This script:
  1. Pulls last 90d HIGH EP alerts with forward returns (5d / 20d)
  2. Keyword-classifies catalyst prose into tier 2/3/4 buckets
     (Tier 1 = theme membership; cross-referenced via mi_themes)
  3. Aggregates forward-return medians + win rates by tier
  4. Tests hypothesis: does empirical ranking match Pradeep's order?

Limitations:
  - Keyword classifier is naive; operator validation needed for ~10 cases
  - Theme tier requires `mi_themes` join — included for tier 1 estimate
  - One LLM-grader call per alert (Phase 5 final ship) would be more accurate;
    this is the empirical-baseline-first prep step.

Output: prints summary table + writes per-alert classification to
        analysis/2026-05-18/pradeep_catalyst_tiers.csv for operator review.

Run: docker exec apollo-market python -m scripts.ep_pradeep_catalyst_tier_analysis
"""
from __future__ import annotations

import asyncio
import csv
import re
from collections import defaultdict
from pathlib import Path

from agents.market_intelligence.db import get_pool


# Keyword patterns per tier (lowercase, regex-friendly)
TIER_PATTERNS = {
    2: [  # Government policy change
        r"\btariff",
        r"\bfda (approval|clearance|approved)",
        r"\bregulatory (approval|change|filing)",
        r"\bsubsidy",
        r"\bexecutive order",
        r"\bpolicy (change|reform|shift)",
        r"\b(treasury|federal reserve|fed) ",
        r"\bgovernment contract",
        r"\blegislation",
        r"\binflation reduction act",
        r"\bchips act",
        r"\bsanction",
        r"\bgeopolitical",
    ],
    3: [  # Shortages
        r"\bshortage",
        r"\bsupply (constraint|tight|squeeze)",
        r"\bcapacity (expansion|constraint|tight)",
        r"\bbacklog",
        r"\bdemand (exceeds|outstrips)",
        r"\bbottleneck",
        r"\bsold out",
        r"\bdemand surge",
        r"\bsupply chain",
        r"\bscarcity",
    ],
    4: [  # Operational (sales accel / new products / management / earnings)
        r"\b(earnings|q[1-4]|fy26|fiscal)",
        r"\bbeat (expectations|estimates|consensus)",
        r"\b(raised|increased|upgraded) guidance",
        r"\b(revenue|sales) (growth|acceleration|beat)",
        r"\bnew product (launch|announcement)",
        r"\b(ceo|cfo|management) (change|appointment|hire)",
        r"\bproduct launch",
        r"\beps beat",
        r"\bquarterly (results|earnings)",
        r"\bcontract (win|award|expansion)",
        r"\b(buyback|share repurchase)",
        r"\bdividend (increase|raise)",
    ],
}


def classify_catalyst(catalyst_text: str) -> tuple[int, list[str]]:
    """Return (tier, matched_keywords) for a catalyst string.

    Multi-tier text picks the LOWEST tier number (highest power) per Pradeep's
    hierarchy. Ties resolved by first match.

    Returns (4, ['default']) if no specific pattern matched (assume operational).
    """
    if not catalyst_text:
        return (4, ["no_text"])
    text = catalyst_text.lower()
    matches_by_tier: dict[int, list[str]] = {}
    for tier, patterns in TIER_PATTERNS.items():
        hits = []
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                hits.append(m.group(0)[:40])
        if hits:
            matches_by_tier[tier] = hits
    if not matches_by_tier:
        return (4, ["default_operational"])
    # Pick lowest tier (highest power)
    lowest = min(matches_by_tier.keys())
    return (lowest, matches_by_tier[lowest])


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH ep AS (
                SELECT a.ticker, a.alert_date, a.catalyst_quality, a.catalyst,
                       a.ep_score, a.gap_pct, a.pm_rvol
                FROM mi_ep_alerts a
                WHERE a.alert_date >= CURRENT_DATE - 90
                  AND a.score_tier = 'HIGH'
            )
            SELECT ep.*,
                   o.fwd_5d_pct / 100.0 AS ret_5d,
                   o.fwd_10d_pct / 100.0 AS ret_10d,
                   m.ret_20d, m.max_high_5d
            FROM ep
            LEFT JOIN mi_ep_scan_outcomes o
              ON o.ticker = ep.ticker AND o.scan_date = ep.alert_date
            LEFT JOIN mi_ep_missed_outcomes m
              ON m.ticker = ep.ticker AND m.alert_date = ep.alert_date
            ORDER BY ep.alert_date DESC
        """)

    print(f"Loaded {len(rows)} HIGH EP alerts (90d window)")

    # Classify each
    classified = []
    for r in rows:
        tier, kws = classify_catalyst(r["catalyst"] or "")
        classified.append({
            "ticker": r["ticker"],
            "alert_date": r["alert_date"],
            "tier": tier,
            "tier_label": {2: "policy", 3: "shortage", 4: "operational"}[tier],
            "matched_keywords": "|".join(kws[:3]),
            "catalyst_quality": r["catalyst_quality"],
            "ep_score": r["ep_score"],
            "gap_pct": float(r["gap_pct"]) if r["gap_pct"] else None,
            "ret_5d": float(r["ret_5d"]) if r["ret_5d"] is not None else None,
            "max_high_5d": float(r["max_high_5d"]) if r["max_high_5d"] is not None else None,
            "ret_20d": float(r["ret_20d"]) if r["ret_20d"] is not None else None,
            "catalyst_short": (r["catalyst"] or "")[:100],
        })

    # Aggregate per tier
    by_tier = defaultdict(list)
    for c in classified:
        by_tier[c["tier"]].append(c)

    print("\n" + "=" * 80)
    print("CATALYST TIER FORWARD-RETURN ANALYSIS (Pradeep's hierarchy: 1=Theme, 2=Policy, 3=Shortage, 4=Operational)")
    print("=" * 80)
    print(f"\nNote: Tier 1 (Theme) is membership-derived from mi_themes — not catalyst prose")
    print(f"      and is NOT included in this prose-based pass.\n")

    def median(xs):
        if not xs:
            return None
        s = sorted(xs)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    print(f"{'Tier':<6} {'Label':<14} {'N':>4} {'Median 5d':>10} {'Win 5d':>8} {'Median MFE 5d':>14} {'Median 20d':>11}")
    print("-" * 80)
    for tier in sorted(by_tier.keys()):
        cohort = by_tier[tier]
        ret_5d = [c["ret_5d"] for c in cohort if c["ret_5d"] is not None]
        mfe_5d = [c["max_high_5d"] for c in cohort if c["max_high_5d"] is not None]
        ret_20d = [c["ret_20d"] for c in cohort if c["ret_20d"] is not None]
        wins = sum(1 for r in ret_5d if r > 0)
        win_rate = wins / len(ret_5d) if ret_5d else 0
        m5 = median(ret_5d)
        mfe5 = median(mfe_5d)
        m20 = median(ret_20d)
        label = cohort[0]["tier_label"]
        print(
            f"{tier:<6} {label:<14} {len(cohort):>4} "
            f"{f'{m5:+.2%}' if m5 is not None else '   n/a':>10} "
            f"{win_rate:>7.0%} "
            f"{f'{mfe5:+.2%}' if mfe5 is not None else '   n/a':>13} "
            f"{f'{m20:+.2%}' if m20 is not None else '   n/a':>11}"
        )

    # Predicted Pradeep ranking: Tier 1 > Tier 2 > Tier 3 > Tier 4
    # Empirical test: do Tier 2/3 cohort medians exceed Tier 4?
    print("\nHypothesis test (Pradeep: lower-tier-number = higher expected return):")
    tier_med_5d = {t: median([c["ret_5d"] for c in by_tier[t] if c["ret_5d"] is not None]) for t in by_tier}
    sorted_tiers = sorted([(t, m) for t, m in tier_med_5d.items() if m is not None], key=lambda x: x[0])
    if len(sorted_tiers) >= 2:
        print(f"  Empirical median 5d return by tier:")
        for t, m in sorted_tiers:
            print(f"    Tier {t}: {m:+.2%}")
        empirical_order = [t for t, m in sorted(sorted_tiers, key=lambda x: -x[1])]
        pradeep_order = sorted(by_tier.keys())
        print(f"  Pradeep order   : {pradeep_order}")
        print(f"  Empirical order : {empirical_order} (sorted by descending median return)")
        if empirical_order == pradeep_order:
            print(f"  ✓ Empirical matches Pradeep's hierarchy")
        else:
            print(f"  ✗ Empirical DIFFERS — investigate")

    # Sample 10 classifications for operator review (mix of tiers)
    print("\n" + "=" * 80)
    print("SAMPLE CLASSIFICATIONS FOR OPERATOR REVIEW")
    print("=" * 80)
    sample = []
    for tier in sorted(by_tier.keys()):
        sample.extend(by_tier[tier][:4])  # 4 per tier max
    sample = sample[:12]
    for c in sample:
        ret_str = f"{c['ret_5d']:+.2%}" if c["ret_5d"] is not None else "n/a"
        print(f"  [{c['tier_label']:<11}] {c['ticker']:<6} {c['alert_date']} "
              f"5d={ret_str:<8} kw='{c['matched_keywords'][:35]}' "
              f"catalyst='{c['catalyst_short'][:60]}...'")

    # Write CSV
    out_dir = Path("/app/analysis/2026-05-18") if Path("/app").exists() else Path("analysis/2026-05-18")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "pradeep_catalyst_tiers.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(classified[0].keys()) if classified else [])
        w.writeheader()
        w.writerows(classified)
    print(f"\nWrote {len(classified)} rows to {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
