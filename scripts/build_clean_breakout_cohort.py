"""#267 (W4) — build the KEEP-side cohort for the chart-vision eval (advisor Gap B, 2026-06-17).

deadcat_cohort.csv is an adversarial REJECT set; a chart axis that rejects everything scores
perfectly on it. To catch the chart causing FALSE rejections we also need known-good clean
breakouts where "keep" is the right call. This pulls HIGH-floor EP alerts that WON — strong forward
return — and writes them as the keep-side cohort. The operator can prune the list before the run;
the point is a two-sided eval, not a perfect oracle.

READ-ONLY. Runs on the server (needs prod DB). Output: clean_breakout_cohort.csv (ticker,date,fwd).

  docker exec apollo-market python /app/scripts/build_clean_breakout_cohort.py \
      --min-fwd 8 --limit 40 --out /app/clean_breakout_cohort.csv
"""
import argparse
import asyncio
import csv

from agents.market_intelligence.db import get_pool

# Known-good = HIGH floor + a clean forward move. Exclude names already in the reject cohort so the
# two sides don't overlap. fwd_5d_pct lives in mi_ep_scan_outcomes keyed (ticker, scan_date).
_SQL = """
SELECT a.ticker, a.alert_date, o.fwd_5d_pct
FROM mi_ep_alerts a
JOIN mi_ep_scan_outcomes o
  ON o.ticker = a.ticker AND o.scan_date = a.alert_date
WHERE COALESCE(a.baseline_floor_tier, a.score_tier) = 'HIGH'
  AND o.fwd_5d_pct >= $1
  AND o.n_sessions_5d >= 4
ORDER BY o.fwd_5d_pct DESC
LIMIT $2
"""


def _load_exclude(path: str | None) -> set[str]:
    if not path:
        return set()
    keys = set()
    try:
        with open(path, newline="") as f:
            for rec in csv.reader(f):
                if len(rec) >= 2 and rec[0].strip():
                    keys.add(f"{rec[0].strip().upper()}|{rec[1].strip()}")
    except FileNotFoundError:
        pass
    return keys


async def main(min_fwd: float, limit: int, out: str, exclude: str | None):
    excl = _load_exclude(exclude)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, min_fwd, limit + len(excl))
    kept = [r for r in rows if f"{r['ticker']}|{r['alert_date'].isoformat()}" not in excl][:limit]
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        for r in kept:
            w.writerow([r["ticker"], r["alert_date"].isoformat(), f"{r['fwd_5d_pct']:.1f}"])
    print(f"wrote {len(kept)} known-good clean breakouts (fwd_5d ≥ {min_fwd}%) → {out}")
    if kept:
        print("  sample:", ", ".join(f"{r['ticker']}({r['fwd_5d_pct']:.0f}%)" for r in kept[:8]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-fwd", type=float, default=8.0, help="min fwd_5d_pct %% to count as a clean win")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--out", type=str, default="clean_breakout_cohort.csv")
    ap.add_argument("--exclude", type=str, default="deadcat_cohort.csv",
                    help="cohort CSV to exclude overlaps with (keeps the two sides disjoint)")
    args = ap.parse_args()
    asyncio.run(main(args.min_fwd, args.limit, args.out, args.exclude))
