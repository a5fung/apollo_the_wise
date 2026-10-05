"""2026-10-05 read-only adversarial re-check of the 'orderliness dead column' verdict.
(1) full-dated job runs, (2) was any row touched between the column shipping and tonight's 17:35,
(3) what the /anticipation board read would show now (NULL orderliness on shown rows?),
(4) RECOMPUTE orderliness for a sample of tonight's rows with the live functions and compare to
the stored value (does the writer store the RIGHT number, not just a non-null one).
No writes: only SELECTs + pure functions."""
import asyncio
import random
from agents.market_intelligence.db import get_pool, get_anticipation_ohlcv
from agents.market_intelligence import anticipation as de

T = "AT TIME ZONE 'America/New_York'"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval(f"SELECT (now() {T})::text"))
        print("== job runs, last 8 days (full timestamps ET)")
        for r in await c.fetch(f"""SELECT job_id, status, (started_at {T})::text s, (finished_at {T})::text f
                                   FROM mi_job_runs WHERE job_id IN ('post_nightly_audit','consolidation_readiness')
                                   AND started_at > now() - interval '8 days' ORDER BY started_at"""):
            print("  ", r["job_id"], r["status"], r["s"], "->", r["f"])
        print("== dead_column audit rows today (any event_type like dead_column%)")
        for r in await c.fetch(f"""SELECT event_type, (created_at {T})::text t, summary, detail FROM mi_audit_log
                                   WHERE event_type LIKE 'dead_column%' AND (created_at {T})::date = (now() {T})::date
                                   ORDER BY created_at"""):
            print("  ", dict(r))
        print("== rows updated between Fri 10-02 18:00 ET and Mon 10-05 17:34 ET (writer runs before tonight)")
        print("  ", await c.fetchval(f"""SELECT count(*) FROM mi_anticipation_consolidation
              WHERE (updated_at {T}) > '2026-10-02 18:00' AND (updated_at {T}) < '2026-10-05 17:34'"""))
        print("== table totals now")
        print("  ", dict(await c.fetchrow(f"""SELECT count(*) n, count(orderliness) n_ord,
              max(last_eval) max_eval, max(updated_at {T})::text last_upd FROM mi_anticipation_consolidation""")))
        print("== what the board read (get_consolidation_board WHERE) would show now")
        print("  ", dict(await c.fetchrow("""SELECT count(*) n, count(orderliness) n_ord
              FROM mi_anticipation_consolidation
              WHERE state <> 'aged' AND mna_screened_on IS NULL
                AND last_eval = (SELECT max(last_eval) FROM mi_anticipation_consolidation)""")))
        print("== mis-mapping check: orderliness vs atr14_pct / rmv_5d on tonight's rows (should differ)")
        print("  ", dict(await c.fetchrow("""SELECT count(*) n,
              count(*) FILTER (WHERE orderliness = atr14_pct) eq_atr,
              count(*) FILTER (WHERE orderliness = rmv_5d) eq_rmv5,
              count(DISTINCT round(orderliness::numeric,4)) n_distinct
              FROM mi_anticipation_consolidation WHERE last_eval = (now() AT TIME ZONE 'America/New_York')::date""")))
        rows = await c.fetch("""SELECT ticker, anchor_date, state, orderliness, last_eval
              FROM mi_anticipation_consolidation WHERE last_eval = (now() AT TIME ZONE 'America/New_York')::date
              ORDER BY ticker""")
    today = rows[0]["last_eval"] if rows else None
    random.seed(1005)
    sample = random.sample(list(rows), min(15, len(rows)))
    print(f"== recompute orderliness for {len(sample)} of {len(rows)} tonight rows (today={today})")
    match = mism = 0
    for r in sample:
        bars = de.db_rows_to_bars(await get_anticipation_ohlcv(r["ticker"], today))
        cons, why = de.evaluate_coil_consolidation(bars)
        recomputed = cons.get("orderliness") if cons else None
        stored = r["orderliness"]
        ok = (recomputed is not None and stored is not None and abs(recomputed - stored) < 1e-9)
        match += ok
        mism += (not ok)
        print(f"   {r['ticker']:6s} {r['state']:10s} stored={stored!r:22s} recomputed={recomputed!r} "
              f"{'OK' if ok else 'DIFF'} (cons={'None:'+str(why) if cons is None else 'ok'})")
    print(f"  match={match} mismatch={mism}")


asyncio.run(main())
