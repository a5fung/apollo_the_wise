#!/usr/bin/env python3
"""#343 chart-vision SHADOW VERIFY-LIVE — run INSIDE the market-agent container:

    docker exec <market-container> python scripts/_verify_chart_axis_shadow.py --cohort-only
    docker exec <market-container> python scripts/_verify_chart_axis_shadow.py --run

SHADOW / read-only telemetry (writes only mi_audit_log + delta PNGs, never trade state) — acceptable
via docker exec. The first real cron fire is Mon 6/22 (Fri 6/19 is a holiday); this proves the
machinery TODAY so "Done = VERIFIED-LIVE" doesn't slip 4 days. Any delta emitted before 2026-06-19
is UNCOUNTED by the registry predicate (created_at >= '2026-06-19'), so a 6/18 run can't pollute the
decision N — a clean same-day machinery check with zero downside (advisor 6/18).

--cohort-only : print today's HIGH+MODERATE shadow cohort (the get_chart_axis_shadow_cohort SQL).
                ZERO Anthropic spend — proves the cohort selection + the prior-day chart render only.
--run         : run the REAL _chart_axis_shadow_job once (grades B/C ×3, emits the audit rows), then
                SELECT today's chart_axis_shadow_* events. A 0-cohort day is a legitimate clean no-op.
"""
import argparse
import asyncio
import sys


async def _cohort_only():
    from agents.market_intelligence import chart_axis as ca
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.db import (
        get_chart_axis_shadow_cohort, get_chart_axis_shadow_processed_tickers,
    )
    today = et_today()
    cohort = await get_chart_axis_shadow_cohort(today, limit=8)
    already = await get_chart_axis_shadow_processed_tickers(today)
    print(f"== chart-axis shadow cohort {today} ==  {len(cohort)} candidate(s), "
          f"{len(already)} already processed")
    for r in cohort:
        png, n_daily = await ca.render_prior_day_chart(r["ticker"], r["alert_date"])
        flag = "✓chart" if png else f"✗no-chart(n_daily={n_daily})"
        mark = " [processed]" if r["ticker"] in already else ""
        print(f"  {r['ticker']:6} {r['alert_date']}  floor={r['floor_tier']:8} "
              f"score={r['score_tier']:8} ep={r['ep_score']}  {flag}{mark}")
    if not cohort:
        print("  (empty — no HIGH/MODERATE EP alerts today; the EOD job is a clean no-op)")


async def _run():
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.db import get_audit_log
    from agents.market_intelligence.scheduler import _chart_axis_shadow_job
    print("== running _chart_axis_shadow_job once (real grade calls) ==")
    await _chart_axis_shadow_job()
    print(f"\n== today's chart_axis_shadow_* audit events ({et_today()}) ==")
    for et in ("chart_axis_shadow_graded", "chart_axis_shadow_delta", "chart_axis_shadow_norender"):
        rows = await get_audit_log(event_type=et, since_hours=24, limit=50)
        print(f"\n  [{et}] {len(rows)}")
        for r in rows:
            print(f"    {r['created_at']:%H:%M}  {r['summary']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort-only", action="store_true",
                    help="print today's cohort + render check; ZERO spend")
    ap.add_argument("--run", action="store_true",
                    help="run the real EOD shadow job once, then dump today's audit rows")
    args = ap.parse_args()
    if not (args.cohort_only or args.run):
        ap.error("pass --cohort-only (free) or --run (grades)")
    asyncio.run(_cohort_only() if args.cohort_only else _run())


if __name__ == "__main__":
    sys.exit(main())
