"""W2c (#243) pre-flip write-check — exercise update_ep_alert_grade_override against the
real mi_ep_alerts schema BEFORE the flip (its first execution must not be the live flip,
same discipline as the W1 'B' check). Synthetic non-colliding ticker; reads back to prove
score_tier + grade_engine_authority both moved; cleans up.

Run: docker exec apollo-market python scripts/_w2c_override_writecheck.py
"""
import asyncio

from agents.market_intelligence import db
from agents.market_intelligence.collector import et_today

TICKER = "ZZOVR"


async def main():
    d = et_today()
    # Seed a floor-HIGH row (authority 'floor', as the in-loop insert would write).
    await db.insert_ep_alert({
        "ticker": TICKER, "alert_date": d, "gap_pct": 16.0, "ep_score": 80,
        "score_tier": "HIGH", "catalyst": "W2c override write-check", "catalyst_quality": "strong",
        "source": "w2c_writecheck", "baseline_floor_tier": "HIGH",
        "grade_engine_authority": "floor",
    })
    print(f"[1] seeded floor-HIGH row ({TICKER} {d})")

    # Simulate a judge DEMOTE to 'none' (the dangerous direction) via the override path.
    await db.update_ep_alert_grade_override(
        TICKER, d, score_tier="none", grade_engine_authority="judge")
    print("[2] update_ep_alert_grade_override(score_tier='none', authority='judge') OK")

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT score_tier, baseline_floor_tier, grade_engine_authority "
            "FROM mi_ep_alerts WHERE ticker=$1 AND alert_date=$2", TICKER, d)
    print("[3] READ-BACK:")
    print(f"      score_tier            = {row['score_tier']!r}   (expect 'none' — demoted/suppressed)")
    print(f"      baseline_floor_tier   = {row['baseline_floor_tier']!r}   (expect 'HIGH' — counterfactual preserved)")
    print(f"      grade_engine_authority= {row['grade_engine_authority']!r}   (expect 'judge')")

    ok = (row["score_tier"] == "none" and row["baseline_floor_tier"] == "HIGH"
          and row["grade_engine_authority"] == "judge")

    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM mi_ep_alerts WHERE ticker=$1 AND alert_date=$2", TICKER, d)
    print("[4] cleanup: synthetic row deleted")
    print(f"\n=== W2c OVERRIDE WRITE-CHECK: {'PASS' if ok else 'FAIL — investigate'} ===")


asyncio.run(main())
