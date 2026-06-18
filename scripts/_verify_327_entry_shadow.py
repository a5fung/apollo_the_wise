#!/usr/bin/env python3
"""#327 forward-shadow VERIFY-LIVE — run INSIDE the market-agent container:

    docker exec apollo-market-agent python scripts/_verify_327_entry_shadow.py [--probe-write]

SHADOW / telemetry only (no trade state) — acceptable via docker exec (feedback_no_docker_exec_for
_trade_state applies to trade-state mutators, not this shadow table). Confirms the insert path the
unit tests CANNOT reach (the ON CONFLICT partial-index inference, the two CHECK constraints, asyncpg
type mapping) works end-to-end against real Postgres.

Default: runs the REAL _consolidation_readiness_job once (universe → keys → evaluate → upsert →
the #327 entry-watch), then SELECTs mi_consolidation_entry_shadow. A 0-row result is reported as
DISTINCT from a broken write (the silent-0 class — disambiguate via the job's 'N #327 entry-shadows
fired' log line).

--probe-write: a DELIBERATE insert-path exercise (advisor 6/18 — prove the write even if nothing
fires naturally): insert a synthetic OPEN row, assert the open-dedup makes a re-insert a no-op, then
DELETE it (leaves the table as found). Proves the ON CONFLICT + CHECK + types in isolation.
"""
import asyncio
import sys
from datetime import date


async def probe_write():
    from agents.market_intelligence.db import insert_consolidation_entry_shadow, get_pool
    T, A = "_PROBE327", date(2099, 1, 1)
    kw = dict(entry_date=A, entry_price=10.0, stop_kind="coiled_low", stop_price=9.5,
              structural_low=9.4, signal_n=3, rmv_5d=0.0, range_pct=0.02, vol_ratio=0.8,
              target_r=3.0, origin="family_a")
    ok1 = await insert_consolidation_entry_shadow(T, A, **kw)
    ok2 = await insert_consolidation_entry_shadow(T, A, **kw)   # open-dedup → no-op
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM mi_consolidation_entry_shadow WHERE ticker=$1 AND anchor_date=$2", T, A)
    print(f"WRITE PROBE: first insert={ok1} (expect True), dedup re-insert={ok2} (expect False); row deleted.")
    assert ok1 is True and ok2 is False, "WRITE/DEDUP PATH FAILED"
    print("WRITE PROBE OK — insert + open-dedup + CHECK constraints + cleanup verified on real Postgres.")


async def run_and_report():
    from agents.market_intelligence.scheduler import _consolidation_readiness_job
    from agents.market_intelligence.db import get_pool
    print("Running _consolidation_readiness_job once (SHADOW)…")
    await _consolidation_readiness_job()
    pool = await get_pool()
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM mi_consolidation_entry_shadow")
        rows = await conn.fetch("""
            SELECT ticker, anchor_date, entry_date, entry_price, stop_price, structural_low,
                   signal_n, rmv_5d, range_pct, vol_ratio, origin, outcome
            FROM mi_consolidation_entry_shadow
            ORDER BY entry_date DESC, ticker LIMIT 25
        """)
    print(f"\nmi_consolidation_entry_shadow: {n} total row(s)")
    for r in rows:
        print(f"  {r['ticker']:<6} anc {r['anchor_date']} entry {r['entry_date']} "
              f"px {r['entry_price']:.2f} stop {r['stop_price']:.2f} struct {r['structural_low']} "
              f"n{r['signal_n']} rmv{(r['rmv_5d'] or 0):.0f} rng{(r['range_pct'] or 0)*100:.1f}% "
              f"vol{r['vol_ratio']} [{r['origin']}] {r['outcome'] or 'open'}")
    if n == 0:
        print("\n⚠ 0 rows — either NO name is at a tight coil apex today (legitimate, common) OR the "
              "insert path failed silently. Disambiguate with the job log 'N #327 entry-shadows "
              "fired', and run --probe-write to confirm the write path in isolation.")


async def main():
    if "--probe-write" in sys.argv:
        await probe_write()
    else:
        await run_and_report()


if __name__ == "__main__":
    asyncio.run(main())
