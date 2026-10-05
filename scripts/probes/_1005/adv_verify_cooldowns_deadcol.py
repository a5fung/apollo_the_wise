"""2026-10-05 adversarial verify (read-only, NO writes): (1) which columns the dead-column sweep
still counts as dead tonight (it logged '3 dead (1 new)'); (2) did tonight's validator removals
cascade into same-night theme retirements via #655 rule B; (3) is tonight the first re-homing
cooldown night; (4) mass-removal tripwire rows tonight."""
import asyncio, json
from agents.market_intelligence.db import get_pool

ET = "AT TIME ZONE 'America/New_York'"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval(f"SELECT (now() {ET})::text"))

        print("\n== 1. previously-announced dead columns: populated now?")
        for t, col in [("mi_stock_scores", "market_cap"), ("mi_live_fill_counterfactuals", "mark_r"),
                       ("mi_gap_near_miss_replays", "mark_r"), ("mi_flag_candidates", "low_after_breakout"),
                       ("mi_anticipation_consolidation", "orderliness")]:
            try:
                r = await c.fetchrow(f'SELECT count(*) n, count("{col}") nn FROM "{t}"')
                print(f"   {t}.{col}: rows={r['n']} populated={r['nn']}")
            except Exception as e:
                print(f"   {t}.{col}: ERR {e}")

        print("\n== 2a. tonight's theme_retired_small_fading rows (time, theme)")
        ret = {}
        for r in await c.fetch(f"""SELECT (created_at {ET})::time::text t, detail FROM mi_audit_log
                                    WHERE event_type='theme_retired_small_fading'
                                      AND (created_at {ET})::date=(now() {ET})::date ORDER BY created_at"""):
            d = json.loads(r["detail"]) if r["detail"] and r["detail"].startswith("{") else {}
            ret[d.get("theme")] = (r["t"], d.get("members"), d.get("tickers"))
        for k, v in ret.items():
            print(f"   {v[0]}  {k}  members={v[1]} {v[2]}")
        print("   first small-fading retirement ever:",
              await c.fetchval(f"SELECT min(created_at {ET})::text FROM mi_audit_log WHERE event_type='theme_retired_small_fading'"))

        print("\n== 2b. tonight's cooldowns whose theme was retired/dissolved tonight")
        rows = await c.fetch(f"""SELECT ticker, theme_name, (removed_at {ET})::time::text t, left(removal_reason,30) r
                                  FROM mi_validation_cooldowns
                                 WHERE (removed_at {ET})::date=(now() {ET})::date ORDER BY removed_at""")
        stage = {r["name"]: r["stage"] for r in await c.fetch(
            "SELECT DISTINCT ON (name) name, stage FROM mi_themes WHERE name = ANY($1::text[]) ORDER BY name, theme_date DESC",
            list({r["theme_name"] for r in rows}))}
        n_dead = 0
        for r in rows:
            st = stage.get(r["theme_name"])
            tag = "RETIRED-SMALL-FADING" if r["theme_name"] in ret else ""
            if st == "Retired":
                n_dead += 1
            print(f"   {r['t'][:8]} {r['ticker']:5} stage_now={st or '?':10} {tag:22} {r['theme_name'][:60]} | {r['r']}")
        print(f"   -> {n_dead} of {len(rows)} cooldowns sit on a theme that is Retired now")

        print("\n== 3. rehome cooldowns by day (all time)")
        for r in await c.fetch(f"""SELECT (removed_at {ET})::date d, count(*) n FROM mi_validation_cooldowns
                                    WHERE removal_reason LIKE 'rehome:%' GROUP BY 1 ORDER BY 1"""):
            print("   ", r["d"], r["n"])
        print("   theme_rehome_pass_ran rows by day:")
        for r in await c.fetch(f"""SELECT (created_at {ET})::date d, count(*) n FROM mi_audit_log
                                    WHERE event_type='theme_rehome_pass_ran' GROUP BY 1 ORDER BY 1"""):
            print("   ", r["d"], r["n"])

        print("\n== 4. mass-removal tripwire + dissolve events tonight")
        for r in await c.fetch(f"""SELECT event_type, count(*) n, string_agg(left(summary,90), ' || ') s FROM mi_audit_log
                                    WHERE (created_at {ET})::date=(now() {ET})::date
                                      AND (event_type LIKE 'validation_mass%' OR event_type LIKE '%dissolv%')
                                    GROUP BY 1"""):
            print("   ", dict(r))

asyncio.run(main())
