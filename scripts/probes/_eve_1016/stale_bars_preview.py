"""READ-ONLY preview of the #701(c) stale-bar skip on tonight's real keys (2026-10-16). Writes nothing.
Skip rule under review: latest bar older than the 3rd NYSE session before the scan date (cutoff 10-13 for 10-16)."""
import asyncio
from datetime import date
from agents.market_intelligence import anticipation as de
from agents.market_intelligence.db import get_anticipation_universe, get_anticipation_ohlcv, get_consolidation_state_map

TODAY, CUTOFF = date(2026, 10, 16), date(2026, 10, 13)

async def main():
    universe = await get_anticipation_universe(TODAY)
    sm = await get_consolidation_state_map()
    existing = {}
    for (tk, anc), v in sm.items():
        if v["state"] != "aged":
            existing.setdefault(tk, []).append({"anchor_date": anc, "runup_high": v["runup_high"], "dvol_med": v["dvol_med"]})
    keys = de.select_consolidation_keys(universe, existing)
    seen, stale = {}, {}
    for k in keys:
        tk = k["ticker"]
        if tk in seen:
            continue
        bars = de.db_rows_to_bars(await get_anticipation_ohlcv(tk, TODAY))
        if len(bars) < 60:
            seen[tk] = None; continue
        last = date.fromisoformat(str(bars[-1]["date"])[:10])
        seen[tk] = last
        if last < CUTOFF:
            stale[tk] = last
    print(f"keys={len(keys)} tickers={len(seen)} with>=60 bars={sum(1 for v in seen.values() if v)} would_skip={len(stale)}")
    for tk, d in sorted(stale.items(), key=lambda x: x[1]):
        print(f"  {tk} last bar {d}")

asyncio.run(main())
