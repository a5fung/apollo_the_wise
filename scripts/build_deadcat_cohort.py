"""#267 (W4) — build the REJECT-side (dead-cat) cohort for the chart-vision eval (#341, sibling of
build_clean_breakout_cohort.py).

The chart-vision axis needs a TWO-sided eval. clean_breakout_cohort.csv is the KEEP side (HIGH alerts
that WON); this is the REJECT side — HIGH-floor EP alerts that FAILED hard (strong NEGATIVE forward
return, the "dead cats"). A chart axis that KEEPS everything scores perfectly on the keep side, so it
takes this reject set to catch FALSE keeps. The operator can prune the list before the run; the point
is a two-sided eval, not a perfect oracle.

READ-ONLY. Runs on the server (needs prod DB). Output: deadcat_cohort.csv (ticker,date,fwd).

  docker exec apollo-market python /app/scripts/build_deadcat_cohort.py \
      --max-fwd -8 --limit 40 --out /app/deadcat_cohort.csv
"""
import argparse
import asyncio
import csv

from agents.market_intelligence.db import get_pool

# Dead-cat = HIGH floor + a hard forward LOSS. Exclude names already in the keep cohort so the two
# sides stay disjoint. fwd_5d_pct lives in mi_ep_scan_outcomes keyed (ticker, scan_date).
_SQL = """
SELECT a.ticker, a.alert_date, o.fwd_5d_pct
FROM mi_ep_alerts a
JOIN mi_ep_scan_outcomes o
  ON o.ticker = a.ticker AND o.scan_date = a.alert_date
WHERE COALESCE(a.baseline_floor_tier, a.score_tier) = 'HIGH'
  AND o.fwd_5d_pct <= $1
  AND o.n_sessions_5d >= 4
ORDER BY o.fwd_5d_pct ASC
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


async def main(max_fwd: float, limit: int, out: str, exclude: str | None):
    excl = _load_exclude(exclude)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, max_fwd, limit + len(excl))
    kept = [r for r in rows if f"{r['ticker']}|{r['alert_date'].isoformat()}" not in excl][:limit]
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        for r in kept:
            w.writerow([r["ticker"], r["alert_date"].isoformat(), f"{r['fwd_5d_pct']:.1f}"])
    print(f"wrote {len(kept)} dead-cat rejects (fwd_5d ≤ {max_fwd}%) → {out}")
    if kept:
        print("  sample:", ", ".join(f"{r['ticker']}({r['fwd_5d_pct']:.0f}%)" for r in kept[:8]))
    else:
        # LOUD on empty (mirror of the keep-side guard): an empty reject side reverts the chart eval
        # to ONE-sided (keep-only) so it can't catch false KEEPS. Likely cause is the (ticker,
        # alert_date=scan_date) join not aligning, or too few HIGH alerts below --max-fwd.
        print("  ⚠️  EMPTY reject-side — the chart eval would be ONE-SIDED (can't catch false keeps). "
              "Check the alert_date↔scan_date join, loosen --max-fwd, or hand-source a reject cohort, "
              "BEFORE running eval_chart_judge.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-fwd", type=float, default=-8.0,
                    help="max fwd_5d_pct %% to count as a dead-cat reject (negative; e.g. -8)")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--out", type=str, default="deadcat_cohort.csv")
    ap.add_argument("--exclude", type=str, default="clean_breakout_cohort.csv",
                    help="cohort CSV to exclude overlaps with (keeps the two sides disjoint)")
    args = ap.parse_args()
    asyncio.run(main(args.max_fwd, args.limit, args.out, args.exclude))
