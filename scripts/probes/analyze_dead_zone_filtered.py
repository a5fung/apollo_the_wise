"""Re-analyze dead_zone_backfill.csv filtered to CS+ADRC only.

Drops leveraged ETNs/ETFs that were polluting cohort B with shape-noise
(USAX/USGG/OKTG/RKLX/SOUX etc. — 8 of 12 suspicious tickers were ETFs).
"""
from __future__ import annotations

import asyncio
import csv

from agents.market_intelligence.db import get_pool


async def main() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ticker, security_type FROM mi_security_types")
    sec = {r["ticker"]: r["security_type"] for r in rows}

    with open("/tmp/dead_zone_backfill.csv") as f:
        reader = list(csv.DictReader(f))
    print(f"Total rows: {len(reader)}")

    keep = [r for r in reader if sec.get(r["ticker"]) in ("CS", "ADRC")]
    drop = [r for r in reader if sec.get(r["ticker"]) not in ("CS", "ADRC")]
    print(f"Kept (CS/ADRC): {len(keep)}  Dropped: {len(drop)}")

    for cohort in ("high", "deadzone"):
        sub = [r for r in keep if r["cohort"] == cohort and r["rvol_at_14"]]
        pos = [r for r in sub if r["label"] == "positive"]
        neg = [r for r in sub if r["label"] == "negative"]
        print(f"\nCOHORT {cohort.upper()} (CS-only): n={len(sub)} pos={len(pos)} neg={len(neg)}")
        if pos:
            ps = sorted(float(r["rvol_at_14"]) for r in pos)
            print(f"  pos median rvol@14: {ps[len(ps)//2]:.2f}  p25={ps[len(ps)//4]:.2f}  p75={ps[(3*len(ps))//4]:.2f}")
        if neg:
            ns = sorted(float(r["rvol_at_14"]) for r in neg)
            print(f"  neg median rvol@14: {ns[len(ns)//2]:.2f}  p25={ns[len(ns)//4]:.2f}  p75={ns[(3*len(ns))//4]:.2f}")

    cb = [r for r in keep if r["cohort"] == "deadzone" and r["rvol_at_14"]]
    total_pos = sum(1 for r in cb if r["label"] == "positive")
    base_rate = (total_pos / len(cb) * 100) if cb else 0
    print(f"\nCohort B (CS-only): n={len(cb)} positives={total_pos} base_rate={base_rate:.1f}%")
    print(f"{'thresh':>8} {'flagged':>8} {'tp':>4} {'prec':>8} {'recall':>8}")
    for thresh in (1.0, 1.5, 2.0, 3.0):
        flagged = [r for r in cb if float(r["rvol_at_14"]) >= thresh]
        tp = sum(1 for r in flagged if r["label"] == "positive")
        prec = tp / len(flagged) if flagged else 0
        rec = tp / total_pos if total_pos else 0
        print(f"{thresh:>8.1f} {len(flagged):>8} {tp:>4} {prec*100:>7.1f}% {rec*100:>7.1f}%")

    print("\nDropped non-CS tickers (top 10 by fwd_5d_pct):")
    def _fwd(r):
        try:
            return -float(r["fwd_5d_pct"])
        except Exception:
            return 0.0
    drop_sorted = sorted(drop, key=_fwd)[:10]
    for r in drop_sorted:
        t = r["ticker"]
        print(f"  {t:6s} {sec.get(t,'?'):4s} {r['alert_date']} fwd={r['fwd_5d_pct']:>7s}% rvol14={r['rvol_at_14']}")

    print("\nTop 10 cohort B (CS-only) by fwd_5d_pct:")
    cb_sorted = sorted(cb, key=_fwd)[:10]
    for r in cb_sorted:
        t = r["ticker"]
        print(f"  {t:6s} {r['alert_date']} fwd={r['fwd_5d_pct']:>7s}% rvol14={r['rvol_at_14']:>5s} gap={r['gap_pct']:>6s}%")


if __name__ == "__main__":
    asyncio.run(main())
