"""Monday 6/8 verify-cluster probe — read-only. Throwaway."""
import asyncio


async def main():
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.collector import et_today
    p = await get_pool()
    async with p.acquire() as c:
        t = et_today()
        rows = await c.fetch(
            "SELECT event_type, COUNT(*) n FROM mi_audit_log "
            "WHERE created_at AT TIME ZONE 'America/New_York' >= $1::date "
            "  AND created_at AT TIME ZONE 'America/New_York' < $1::date + 1 "
            "GROUP BY event_type ORDER BY n DESC", t)
        print("=== audit events today ===")
        for r in rows:
            print(f"{r['n']:4}  {r['event_type']}")
        print("\n=== alerts today (advisory cols) ===")
        a = await c.fetch(
            "SELECT ticker, score_tier, catalyst_quality, theme_gated_tier, "
            "theme_gated_score, in_active_theme, in_narrative_cohort, fire_status, "
            "fire_axes FROM mi_ep_alerts WHERE alert_date=$1", t)
        for r in a:
            print(dict(r))


if __name__ == "__main__":
    asyncio.run(main())
