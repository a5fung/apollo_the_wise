"""Read-only evidence pull for #197/#198 — should the safeguard admit top-tier
setups it blocked? Queries mi_ep_missed_outcomes for the safeguard-block cohorts
(cap_blocked = max_positions #197; breaker_blocked = circuit_breaker #198;
high_unentered = HIGH that never entered) and reports tier/quality + forward
outcomes. NO writes. NOT a criteria decision — evidence for operator sign-off
(CHANGE_PROCESS rule 1 N>=10 + rule 3 HARD-gate).

  docker exec apollo-market python scripts/_evidence_shouldve_entered_197.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.market_intelligence.db import get_pool

COHORTS = ("cap_blocked", "breaker_blocked", "high_unentered")


def _wr(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return "—", "—", 0
    win = sum(1 for x in v if x > 0) / len(v) * 100
    return f"{sum(v)/len(v)*100:+.1f}%", f"{win:.0f}%", len(v)


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT ticker, alert_date, skip_category, ep_score, catalyst_quality,
                   ret_5d, max_high_5d
            FROM mi_ep_missed_outcomes
            WHERE skip_category = ANY($1::text[])
            ORDER BY alert_date DESC
        """, list(COHORTS))

    print(f"\n#197/#198 evidence — safeguard-blocked cohort (N={len(rows)}, all history)\n")
    if not rows:
        print("  (no rows — telemetry #199 may not have accrued yet)")
        return

    for cat in COHORTS:
        crows = [r for r in rows if r["skip_category"] == cat]
        if not crows:
            print(f"## {cat}: N=0")
            continue
        topt = [r for r in crows if (r["catalyst_quality"] in ("game_changer", "strong"))
                or (r["ep_score"] or 0) >= 70]
        ret_avg, ret_wr, n5 = _wr([r["ret_5d"] for r in crows])
        mfe_avg, _, _ = _wr([r["max_high_5d"] for r in crows])
        t_ret_avg, t_ret_wr, t_n5 = _wr([r["ret_5d"] for r in topt])
        t_mfe_avg, _, _ = _wr([r["max_high_5d"] for r in topt])
        print(f"## {cat}: N={len(crows)} (top-tier: {len(topt)})")
        print(f"   ALL       ret5d avg {ret_avg} win {ret_wr} (n={n5}) · MFE5d avg {mfe_avg}")
        print(f"   TOP-TIER  ret5d avg {t_ret_avg} win {t_ret_wr} (n={t_n5}) · MFE5d avg {t_mfe_avg}")
        print(f"   top-tier names:")
        for r in sorted(topt, key=lambda x: -(x["max_high_5d"] or -9))[:12]:
            print(f"     {r['ticker']:<7}{str(r['alert_date']):<12}"
                  f"score={r['ep_score'] or 0:>3.0f} {r['catalyst_quality'] or '?':<12}"
                  f"ret5d={'—' if r['ret_5d'] is None else f'{r['ret_5d']*100:+.0f}%':>6}"
                  f"  MFE5d={'—' if r['max_high_5d'] is None else f'{r['max_high_5d']*100:+.0f}%':>6}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
