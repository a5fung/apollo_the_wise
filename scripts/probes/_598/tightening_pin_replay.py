"""#598 follow-up (2026-10-04) — $0 read-only replay: would the Layer-3 deal-pin PRICE backstop
(mature 10-session median pin, fresh band+volume-spike pin, sticky carry) have downgraded past
TIGHTENING flag rows? It was only ever measured on COILED/TRIGGERED. Calls the live
`flag_detector._check_deal_pin_signatures_batch` (SELECT only) per scan date. Writes nothing.

Run inside apollo-market:  python scripts/probes/_598/tightening_pin_replay.py [days]
"""
import asyncio
import sys
from collections import defaultdict
from datetime import timedelta

from agents.market_intelligence import flag_detector as fd
from agents.market_intelligence.db import get_pool
from shared.dates import et_today


async def main(days: int) -> None:
    since = et_today() - timedelta(days=days)
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT DISTINCT ticker, scan_date FROM mi_flag_candidates "
            "WHERE stage = 'TIGHTENING' AND scan_date >= $1 ORDER BY scan_date", since)
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["scan_date"]].append(r["ticker"])
    hits, n = [], 0
    for d, tickers in sorted(by_date.items()):
        n += len(tickers)
        sig = await fd._check_deal_pin_signatures_batch(tickers, d)
        for t in tickers:
            s = sig.get(t) or {}
            if s.get("is_pin") or s.get("is_fresh_pin"):
                kind = ("mature" if s.get("is_pin") else
                        "sticky" if s.get("sticky_from_session") else "fresh")
                hits.append((str(d), t, kind, {k: s.get(k) for k in (
                    "median_range_pct", "band_pct", "vol_spike_x", "sticky_from_session")}))
    names = sorted({t for _, t, _, _ in hits})
    print(f"TIGHTENING ticker-days since {since}: {n} over {len(by_date)} scan dates; "
          f"distinct tickers {len({t for ts in by_date.values() for t in ts})}")
    print(f"backstop would downgrade {len(hits)} ticker-days, {len(names)} distinct: {names}")
    for h in hits:
        print("  ", h)


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 90))
