"""Investigate QURE 6/17 — catalyst section says 'no fresh catalyst' but judge summary says
FDA-confirmation game-changer. Root cause: judge hallucination vs catalyst-extraction miss vs
display mismatch. Read-only."""
import asyncio
from datetime import date
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        cols = [r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_alerts' ORDER BY ordinal_position")]
        print("mi_ep_alerts cols:", ", ".join(cols))
        pick = [x for x in ("ticker","alert_date","created_at","score","score_tier","gap_pct",
                            "catalyst","catalyst_quality","claude_analysis",
                            "judge_grade","judge_tier","judge_rationale","judge_outcome",
                            "has_direct_source","fire_axes","materiality_tier","grade_authority") if x in cols]
        rows = await c.fetch(
            f"SELECT {', '.join(pick)} FROM mi_ep_alerts WHERE ticker='QURE' ORDER BY created_at DESC LIMIT 2")
        for r in rows:
            print("\n=== QURE alert ===")
            for k in pick:
                v = r[k]
                if isinstance(v, str) and len(v) > 600:
                    v = v[:600] + " …"
                print(f"  {k}: {v}")

        print("\n=== judge / provenance audit (QURE, last 36h) ===")
        for r in await c.fetch("""
            SELECT created_at, event_type, left(coalesce(detail,''), 700) AS d
            FROM mi_audit_log
            WHERE created_at >= now() - INTERVAL '36 hours'
              AND (event_type IN ('ep_grade_decision','ep_catalyst_provenance','ep_alert')
                   AND detail ILIKE '%QURE%')
            ORDER BY created_at"""):
            print(f"\n  [{r['created_at']:%m-%d %H:%M}] {r['event_type']}\n    {r['d']}")


if __name__ == "__main__":
    asyncio.run(main())
