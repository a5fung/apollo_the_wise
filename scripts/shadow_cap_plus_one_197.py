"""#197 SHADOW — quality-aware slot admission, policy (a): cap+1 for game_changer.

Read-only. No writes, no entry-pipeline change, no trade-state risk. The
cap_blocked categorisation in mi_ep_missed_outcomes (#199) already encodes
"max_positions was at the cap when this setup's entry was attempted" — so
reading those rows back is decision-time-faithful; a hot-path shadow hook would
only add a cosmetic real-time audit emit. This tracker is the shadow.

Policy (a) (operator decision 2026-06-06): when a **game_changer** HIGH is
blocked by the flat max_positions cap (5), a cap+1 rule WOULD admit it in a 6th
slot. This script measures what that cohort's forward outcome WOULD have been,
accruing toward the promotion gate.

Promotion (live cap+1) is GATED: N>=30 admitted-cohort + operator sign-off +
CHANGE_PROCESS change-log on safeguards.md. Until then this is observe-only.

Caveats baked into the output:
  - First-order only: measures the would-be-admitted names' forward returns. It
    does NOT price the second-order exposure cost of carrying a 6th concurrent
    position (correlation / drawdown-breaker interaction). Weigh at promotion.
  - game_changer is a narrow class → slow accrual. Honest, not a bug.

  docker exec apollo-market python scripts/shadow_cap_plus_one_197.py
  (auto-re-runs monthly via quarterly_review.py backward-check sweep.)
"""
from __future__ import annotations

import asyncio
import statistics as _stats
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.market_intelligence.db import get_pool

# Policy (a) admit class. game_changer only (operator 2026-06-06); 'strong'
# tracked as a SENSITIVITY line for a possible future widen, not the policy.
_ADMIT_QUALITY = ("game_changer",)
_SENSITIVITY_QUALITY = ("game_changer", "strong")
_PROMOTION_N = 30


def _stat_line(rows) -> str:
    r5 = [r["ret_5d"] for r in rows if r["ret_5d"] is not None]
    mfe = [r["max_high_5d"] for r in rows if r["max_high_5d"] is not None]
    if not r5:
        return f"N={len(rows)} (no settled 5d returns yet)"
    win = sum(1 for x in r5 if x > 0) / len(r5) * 100
    return (f"N={len(rows)} settled={len(r5)}  "
            f"ret5d avg {_stats.mean(r5)*100:+.1f}% win {win:.0f}%  "
            f"MFE5d avg {(_stats.mean(mfe)*100 if mfe else 0):+.1f}%  "
            f"totalR-proxy {sum(r5)*100:+.0f}%")


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, alert_date, ep_score, catalyst_quality, ret_5d, max_high_5d
            FROM mi_ep_missed_outcomes
            WHERE skip_category = 'cap_blocked'
            ORDER BY alert_date DESC
        """)
    admit = [r for r in rows if r["catalyst_quality"] in _ADMIT_QUALITY]
    sens = [r for r in rows if r["catalyst_quality"] in _SENSITIVITY_QUALITY]
    settled = len([r for r in admit if r["ret_5d"] is not None])

    print("\n#197 cap+1 (game_changer) shadow — policy (a), SHADOW/observe-only")
    ready = "READY for sign-off review" if settled >= _PROMOTION_N else \
            f"ACCRUING ({settled}/{_PROMOTION_N} settled)"
    print(f"TL;DR: admit-cohort {_stat_line(admit)}")
    print(f"       promotion gate: {ready}  (live cap+1 needs N>={_PROMOTION_N} "
          f"+ operator sign-off + CHANGE_PROCESS)\n")

    print(f"Policy-(a) admit cohort (cap_blocked AND game_changer):")
    print(f"  {_stat_line(admit)}")
    for r in sorted(admit, key=lambda x: -(x["max_high_5d"] or -9)):
        print(f"    {r['ticker']:<7}{str(r['alert_date']):<12}"
              f"score={r['ep_score'] or 0:>3.0f}  "
              f"ret5d={'—' if r['ret_5d'] is None else f'{r['ret_5d']*100:+.0f}%':>6}"
              f"  MFE5d={'—' if r['max_high_5d'] is None else f'{r['max_high_5d']*100:+.0f}%':>6}")
    print(f"\nSENSITIVITY (game_changer + strong — NOT the policy, a future-widen probe):")
    print(f"  {_stat_line(sens)}")
    print("\nCaveat: first-order only (would-be-admitted names' returns); does NOT")
    print("price the exposure cost of a 6th concurrent position. Weigh at promotion.\n")


if __name__ == "__main__":
    asyncio.run(main())
