"""#211 decisive eyeball — read-only. Throwaway.

Pull every source-coverage UNKNOWN since Wave B started logging provenance
(6/7): graded strong/game_changer with has_direct_source=False. Provenance
lives as event_type='ep_catalyst_provenance' rows in mi_audit_log (detail = the
JSON payload). For each, print the grade + the grade's analysis snippet so we
can judge by hand: would the new Wave A (Benzinga) / Wave D (8-K EX-99 / 6-K)
sourcing path NOW catch the catalyst, or is it a genuine still-open gap?
"""
import asyncio
import json


async def main():
    from agents.market_intelligence.db import get_pool
    p = await get_pool()
    async with p.acquire() as c:
        rows = await c.fetch(
            """
            SELECT created_at AT TIME ZONE 'America/New_York' AS ts, detail
            FROM mi_audit_log
            WHERE event_type = 'ep_catalyst_provenance'
            ORDER BY created_at DESC
            """)
        print(f"=== ALL ep_catalyst_provenance rows since Wave B: N={len(rows)} ===\n")
        unknowns = []
        all_grades = {}
        for r in rows:
            try:
                d = json.loads(r["detail"])
            except Exception:
                continue
            q = d.get("catalyst_quality")
            all_grades[q] = all_grades.get(q, 0) + 1
            if q in ("strong", "game_changer") and not d.get("has_direct_source"):
                unknowns.append((r["ts"], d))
        print(f"grade distribution of provenance rows: {all_grades}\n")
        print(f"=== source-coverage UNKNOWNS (strong/gc, has_direct_source=False): N={len(unknowns)} ===\n")
        for ts, d in unknowns:
            tkr = d.get("ticker")
            ad = d.get("alert_date")
            srcs = d.get("sources")
            print(f"{ad}  {tkr:6}  quality={d.get('catalyst_quality'):>12}  sources={srcs}")
            # pull the alert's tier + analysis snippet for the eyeball
            a = await c.fetchrow(
                "SELECT score_tier, LEFT(COALESCE(claude_analysis,''), 360) AS an "
                "FROM mi_ep_alerts WHERE ticker=$1 AND alert_date=$2::date", tkr, ad)
            if a:
                print(f"    tier={a['score_tier']}  analysis: {a['an']}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
