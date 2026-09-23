"""Read-only: dig into the partial-exit FAILURE events (#151 cutover blocker). Pulls the
full partial_exit_* sequence for the last 12 days so we see, per ticker, what failed + why.
"""
import asyncio

from agents.market_intelligence import db


async def main():
    pool = await db.get_pool()
    async with pool.acquire() as c:
        # The failure events first — full detail.
        print("══ FAILURE events (partial_exit_sell_failed / rollback_failed / aborted) ══\n")
        rows = await c.fetch("""
            SELECT created_at, event_type, summary, detail
            FROM mi_audit_log
            WHERE created_at >= NOW() - INTERVAL '12 days'
              AND event_type IN ('partial_exit_sell_failed','partial_exit_rollback_failed',
                                 'partial_exit_aborted')
            ORDER BY created_at
        """)
        for r in rows:
            print(f"[{r['created_at']}] {r['event_type']}")
            print(f"   summary: {r['summary']}")
            if r['detail']:
                print(f"   detail : {str(r['detail'])[:500]}")
            print()

        # Full per-ticker sequence around those days (what led in / out).
        print("══ Full partial_exit_* timeline (last 12d) ══\n")
        rows = await c.fetch("""
            SELECT created_at, event_type, summary
            FROM mi_audit_log
            WHERE created_at >= NOW() - INTERVAL '12 days'
              AND event_type ILIKE 'partial_exit%'
            ORDER BY created_at
        """)
        for r in rows:
            print(f"[{r['created_at']}] {r['event_type']:<34} {(r['summary'] or '')[:90]}")


asyncio.run(main())
