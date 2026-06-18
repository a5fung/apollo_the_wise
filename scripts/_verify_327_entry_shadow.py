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

--settle-probe: a DELIBERATE settlement-UPDATE exercise (the settle job settles 0 real rows until a
row reaches the 12-bar window). Insert a synthetic OPEN row, settle it via the real
settle_consolidation_entry_shadow, assert outcome flips + the open-dedup FREES (a fresh insert on the
same key now succeeds), then DELETE both. Proves the UPDATE write-back + the dedup-free semantics.

--run-settle: run the real _consolidation_entry_settle_job once (confirms it runs clean on live data;
0 settled today is legitimate — nothing has 12 forward bars yet).
"""
import asyncio
import sys
from datetime import date

_PROBE_KW = dict(entry_price=10.0, stop_kind="coiled_low", stop_price=9.5, structural_low=9.4,
                 signal_n=3, rmv_5d=0.0, range_pct=0.02, vol_ratio=0.8, target_r=3.0,
                 origin="family_a")


async def probe_write():
    from agents.market_intelligence.db import insert_consolidation_entry_shadow, get_pool
    T, A = "_PROBE327", date(2099, 1, 1)
    kw = dict(entry_date=A, **_PROBE_KW)
    ok1 = await insert_consolidation_entry_shadow(T, A, **kw)
    ok2 = await insert_consolidation_entry_shadow(T, A, **kw)   # open-dedup → no-op
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM mi_consolidation_entry_shadow WHERE ticker=$1 AND anchor_date=$2", T, A)
    print(f"WRITE PROBE: first insert={ok1} (expect True), dedup re-insert={ok2} (expect False); row deleted.")
    assert ok1 is True and ok2 is False, "WRITE/DEDUP PATH FAILED"
    print("WRITE PROBE OK — insert + open-dedup + CHECK constraints + cleanup verified on real Postgres.")


async def settle_probe():
    from agents.market_intelligence.db import (
        insert_consolidation_entry_shadow, settle_consolidation_entry_shadow, get_pool)
    T, A = "_PROBE327S", date(2099, 1, 2)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await insert_consolidation_entry_shadow(T, A, entry_date=A, **_PROBE_KW)
        rid = await conn.fetchval(
            "SELECT id FROM mi_consolidation_entry_shadow WHERE ticker=$1 AND anchor_date=$2 "
            "AND outcome IS NULL", T, A)
        s1 = await settle_consolidation_entry_shadow(rid, outcome="stop", realized_r=-1.0, fwd_mfe_r=0.3)
        s2 = await settle_consolidation_entry_shadow(rid, outcome="stop", realized_r=-1.0, fwd_mfe_r=0.3)  # no-op
        # dedup must now be FREE (settled row no longer occupies the partial index)
        free = await insert_consolidation_entry_shadow(T, A, entry_date=A, **_PROBE_KW)
        await conn.execute(
            "DELETE FROM mi_consolidation_entry_shadow WHERE ticker=$1 AND anchor_date=$2", T, A)
    print(f"SETTLE PROBE: settle={s1} (expect True), double-settle={s2} (expect False), "
          f"dedup-free reinsert={free} (expect True); rows deleted.")
    assert s1 is True and s2 is False and free is True, "SETTLE/UPDATE/DEDUP-FREE PATH FAILED"
    print("SETTLE PROBE OK — UPDATE write-back + double-settle guard + open-dedup-free verified on real Postgres.")


async def run_settle():
    from agents.market_intelligence.scheduler import _consolidation_entry_settle_job
    print("Running _consolidation_entry_settle_job once (SHADOW)…")
    await _consolidation_entry_settle_job()
    print("settle job ran clean (see the log line 'N ripe-open considered, N settled').")


async def run_and_report():
    from agents.market_intelligence.scheduler import _consolidation_readiness_job
    from agents.market_intelligence.db import get_pool, get_consolidation_entry_shadow_summary
    print("Running _consolidation_readiness_job once (SHADOW)…")
    await _consolidation_readiness_job()
    s = await get_consolidation_entry_shadow_summary()
    print(f"\nREADOUT: {s['open_n']} open ({s['open_overdue_n']} OVERDUE) · {s['settled_n']} settled "
          f"(capture {s['capture_n']} / stop {s['stop_n']} / open {s['timeout_n']}) "
          f"| median realized {s['med_realized_r']} R · median mfe {s['med_fwd_mfe_r']} R "
          f"· total {s['total_realized_r']:+.1f} R")
    for o in s["by_origin"]:
        print(f"   {o['origin']:<9} settled {o['settled_n']} · capture {o['capture_n']} "
              f"· median realized {o['med_realized_r']} R")
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
    elif "--settle-probe" in sys.argv:
        await settle_probe()
    elif "--run-settle" in sys.argv:
        await run_settle()
    else:
        await run_and_report()


if __name__ == "__main__":
    asyncio.run(main())
