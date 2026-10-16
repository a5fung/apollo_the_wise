"""READ-ONLY replay of the coil scan's CONFIRM fire, 2026-09-14..2026-10-16 (#543 'detector quiet' alert 10-16).

Runs inside apollo-market-agent. Uses only read functions (universe, state map, OHLCV) and the pure
coil-finder + confirm_signal_at. Writes NOTHING. Positive control: the replay must reproduce the
recorded September fires; then it shows whether October had fires the job never wrote.
Caveat: the carry-forward state map is TODAY's (not point-in-time), so keys are approximate.
"""
import asyncio
from datetime import date, timedelta

from agents.market_intelligence import anticipation as de
from agents.market_intelligence.db import (
    get_anticipation_universe, get_anticipation_ohlcv, get_consolidation_state_map, get_pool,
)


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        recorded = await conn.fetch(
            "SELECT entry_date, ticker FROM mi_consolidation_entry_shadow "
            "WHERE entry_mode='confirm' AND entry_date >= '2026-09-14' ORDER BY 1")
        days = [r["d"] for r in await conn.fetch(
            "SELECT DISTINCT trade_date AS d FROM mi_daily_closes WHERE ticker='SPY' "
            "AND trade_date BETWEEN '2026-09-14' AND '2026-10-16' ORDER BY 1")]
    rec = {}
    for r in recorded:
        rec.setdefault(r["entry_date"], set()).add(r["ticker"])
    state_map = await get_consolidation_state_map()
    existing = {}
    for (tk, anc), v in state_map.items():
        if v["state"] != "aged":
            existing.setdefault(tk, []).append(
                {"anchor_date": anc, "runup_high": v["runup_high"], "dvol_med": v["dvol_med"]})
    for d in days:
        universe = await get_anticipation_universe(d)
        keys = de.select_consolidation_keys(universe, existing)
        n_cand = 0
        fires = set()
        for k in keys:
            bars = de.db_rows_to_bars(await get_anticipation_ohlcv(k["ticker"], d))
            bars = [b for b in bars if str(b["date"]) <= d.isoformat()]
            if len(bars) < 60:
                continue
            cons, _ = de.evaluate_coil_consolidation(bars)
            if cons is None:
                continue
            n_cand += 1
            ai = next((j for j, b in enumerate(bars) if b["date"] == cons["anchor_date"]), None)
            if ai is not None and de.confirm_signal_at(bars, len(bars) - 1, ai):
                fires.add(k["ticker"])
        r = rec.get(d, set())
        print(f"{d} universe={len(universe)} keys={len(keys)} candidates={n_cand} "
              f"replay_fires={sorted(fires)} recorded={sorted(r)} "
              f"recorded_reproduced={len(r & fires)}/{len(r)}", flush=True)


asyncio.run(main())
