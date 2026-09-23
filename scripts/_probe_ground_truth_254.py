"""Synthetic write→readback probe for the operator ground-truth pipeline (#254).

Validates the DB writers against the LIVE schema with a clearly-synthetic ticker
(ZZ254), then deletes its rows — so it never pollutes the real corpus. Telemetry
table only; READ-ONLY re trade state (no mi_live_trades / broker touch).

Run: docker exec apollo-market python /app/scripts/_probe_ground_truth_254.py
"""
import asyncio

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import (
    ensure_ep_ground_truth_table, get_pool, get_recent_ground_truth,
    snapshot_system_tier, upsert_ep_ground_truth,
)

_T = "ZZ254"  # synthetic — guaranteed not a real ticker


async def main() -> None:
    today = et_today()
    await ensure_ep_ground_truth_table()
    fails = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    try:
        # 1. review write → readback
        r1 = await upsert_ep_ground_truth(
            ticker=_T, event_date=today, kind="review", verdict="agree",
            system_tier="HIGH", root_cause="judge_correct", narrative="probe note",
            source="review", reviewed_by="probe")
        check("review insert returns row", r1["ticker"] == _T and r1["kind"] == "review")
        check("review verdict stored", r1["verdict"] == "agree")
        check("review root_cause stored", r1["root_cause"] == "judge_correct")

        # 2. re-review UPSERT-latest-wins + COALESCE preserves omitted fields
        r2 = await upsert_ep_ground_truth(
            ticker=_T, event_date=today, kind="review", verdict="toohigh")
        check("re-review updates verdict in place", r2["verdict"] == "toohigh")
        # verdict+root_cause are plain-SET (coupled current statement): a toohigh re-review
        # with no cause CLEARS the prior judge_correct — no sticky contradictory row.
        check("re-review SETs root_cause (no sticky judge_correct)", r2["root_cause"] is None)
        check("re-review COALESCE keeps prior narrative", r2["narrative"] == "probe note")
        check("re-review COALESCE keeps prior system_tier", r2["system_tier"] == "HIGH")

        # 3. injected row is SEPARATE (kind in the unique key — hindsight segregation)
        r3 = await upsert_ep_ground_truth(
            ticker=_T, event_date=today, kind="injected", operator_grade="game_changer",
            narrative="probe injected", source="tweet:@probe", reviewed_by="probe")
        check("injected row coexists with review (kind in PK)", r3["kind"] == "injected")
        check("injected operator_grade stored", r3["operator_grade"] == "game_changer")

        # 4. both rows visible in the read surface
        recent = await get_recent_ground_truth(50)
        mine = [x for x in recent if x["ticker"] == _T]
        check("both kinds present in get_recent", {x["kind"] for x in mine} == {"review", "injected"})

        # 5. snapshot_system_tier tolerates an uncaught ticker (NULL, no crash)
        tier = await snapshot_system_tier(_T, today)
        check("snapshot_system_tier NULL on uncaught synthetic", tier is None)

    finally:
        # cleanup — never leave synthetic rows behind
        pool = await get_pool()
        async with pool.acquire() as conn:
            deleted = await conn.execute("DELETE FROM mi_ep_ground_truth WHERE ticker = $1", _T)
        print(f"  cleanup: {deleted}")

    print("\n" + ("ALL PASS" if not fails else f"FAILURES: {fails}"))


if __name__ == "__main__":
    asyncio.run(main())
