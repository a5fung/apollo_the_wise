"""2026-10-05 read-only: the Monday-night live checks for #687, #580, #693, #598, #466/#635 (audit rows)."""
import asyncio
from agents.market_intelligence.db import get_pool

T = "created_at >= (date_trunc('day', now() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York')"


async def ev(c, names, limit=12):
    rows = await c.fetch(f"""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary, 230) s
                             FROM mi_audit_log WHERE event_type = ANY($1) AND {T} ORDER BY created_at LIMIT {limit}""", names)
    for r in rows:
        print(f"  {r['t']:%H:%M:%S} {r['event_type']:<34} {r['s']}")
    if not rows:
        print("  (none)", names)


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("== #687 jobs + coverage slot")
        await ev(c, ["depth_open_auction_sale", "coverage_skipped_broker_flat", "restore_skipped_broker_flat",
                     "stop_breach_market_sale", "unprotected_position_check", "coverage_repair"], 20)
        for r in await c.fetch(f"""SELECT event_type, count(*) n FROM mi_audit_log WHERE {T} AND
                                   (event_type ILIKE '%coverage%' OR event_type ILIKE '%depth%' OR event_type ILIKE '%close_below%'
                                    OR event_type ILIKE 'job_%' AND summary ILIKE '%16:45%') GROUP BY 1 ORDER BY 1"""):
            print(f"  {r['event_type']}: {r['n']}")
        print("  depth-stamped trades:", await c.fetchval("SELECT count(*) FROM mi_live_trades WHERE exit_rule='depth'"))
        for r in await c.fetch(f"""SELECT event_type, LEFT(summary,160) s, created_at AT TIME ZONE 'America/New_York' t FROM mi_audit_log
                                   WHERE {T} AND event_type ILIKE '%job%' AND (summary ILIKE '%error%' OR summary ILIKE '%fail%')
                                   ORDER BY created_at LIMIT 10"""):
            print(f"  JOBERR {r['t']:%H:%M} {r['event_type']} {r['s']}")
        print("== #580 breadth: live themes by stage with 0% / NULL breadth (latest theme_date)")
        d = await c.fetchval("SELECT max(theme_date) FROM mi_themes")
        print("  latest theme_date:", d)
        for r in await c.fetch("""SELECT stage, count(*) n, count(*) FILTER (WHERE pct_above_20sma = 0) zero,
                                  count(*) FILTER (WHERE pct_above_20sma IS NULL) nul FROM mi_themes WHERE theme_date=$1
                                  GROUP BY 1 ORDER BY 1""", d):
            print("  ", dict(r))
        for r in await c.fetch("""SELECT name, stage, pct_above_20sma FROM mi_themes WHERE theme_date=$1 AND stage IN
                                  ('Accelerating','Mainstream') AND (pct_above_20sma = 0 OR pct_above_20sma IS NULL)""", d):
            print("   0%/NULL paying:", dict(r))
        await ev(c, ["theme_breadth_fade", "theme_faded_breadth", "theme_birth"], 30)
        print("== #693 rewrite + jobs")
        await ev(c, ["llm_request_rewrite_adopted", "theme_synthesis_run", "theme_parent_pass_ran", "llm_refusal",
                     "theme_validation_run", "narrative_discovery_run"], 20)
        for r in await c.fetch(f"""SELECT event_type, count(*) n FROM mi_audit_log WHERE {T} AND
                                   (event_type ILIKE '%refus%' OR event_type ILIKE '%parse_fail%' OR event_type ILIKE '%rewrite%')
                                   GROUP BY 1"""):
            print(f"  {r['event_type']}: {r['n']}")
        print("== #598 flag board")
        await ev(c, ["flag_stage_transition", "mna_filter_fired"], 20)
        print("== #635 / #466 error rows today")
        await ev(c, ["ep_repoll_upgrade_error", "ep_candidate_parse_error", "drawdown_breaker_read_error"], 20)


asyncio.run(main())
