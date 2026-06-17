"""Throwaway read-only probe v2 for the theme_count_active decline (42->15 over 10d).
Decisive question: are NEW themes still being born, or has discovery stopped saving?"""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("=== NEW theme births per day (first-ever appearance of a name) last 16d ===")
        rows = await c.fetch("""
            SELECT first_seen, COUNT(*) n FROM (
                SELECT name, MIN(theme_date) first_seen FROM mi_themes GROUP BY name
            ) f WHERE first_seen >= CURRENT_DATE - INTERVAL '16 days'
            GROUP BY first_seen ORDER BY first_seen DESC
        """)
        if not rows:
            print("  *** ZERO new theme names born in the last 16 days ***")
        for r in rows:
            print(f"  {r['first_seen']}  new_names={r['n']}")

        print("\n=== the 15 currently-active themes (latest row per name, non-Retired, <=7d) ===")
        rows = await c.fetch("""
            SELECT name, stage, theme_date FROM (
                SELECT DISTINCT ON (name) name, stage, theme_date
                FROM mi_themes WHERE theme_date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY name, theme_date DESC
            ) l WHERE stage != 'Retired' ORDER BY theme_date DESC, name
        """)
        for r in rows:
            print(f"  {r['theme_date']}  {r['stage']:13} {r['name'][:52]}")

        print("\n=== last 3 nights: theme discovery/synthesis audit SUMMARIES ===")
        rows = await c.fetch("""
            SELECT created_at, event_type, LEFT(COALESCE(summary, detail, ''), 160) txt
            FROM mi_audit_log
            WHERE created_at > NOW() - INTERVAL '76 hours'
              AND event_type IN ('theme_discovery_shadow_ran','narrative_theme_discovery_ran',
                                 'theme_synthesis_run','theme_birth_validated','theme_load_state',
                                 'discovery_error','theme_discovered','themes_saved')
            ORDER BY created_at DESC LIMIT 20
        """)
        for r in rows:
            print(f"  {str(r['created_at'])[:19]} {r['event_type']:30} {r['txt']}")

        print("\n=== was a nightly theme run logged the last 3 nights? (mi_job_runs) ===")
        rows = await c.fetch("""
            SELECT job_id, MAX(run_at) last, COUNT(*) n FROM mi_job_runs
            WHERE run_at > NOW() - INTERVAL '76 hours'
              AND (job_id ILIKE '%theme%' OR job_id ILIKE '%nightly%' OR job_id ILIKE '%data_pull%')
            GROUP BY job_id ORDER BY last DESC
        """)
        for r in rows:
            print(f"  {r['job_id']:34} last={str(r['last'])[:19]} runs={r['n']}")


asyncio.run(main())
